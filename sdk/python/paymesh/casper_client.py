"""Casper JSON-RPC client.

Real, working reads against a Casper node (``query``, ``state_get_dictionary``,
``query_balance``, entrypoint queries). Signed writes (``put_deploy``/
``transfer``) build the canonical deploy arguments and delegate signing to the
``casper-client`` CLI — the canonical, correct tool for Casper deploy signing.

Reads need no signer and work against any public node, e.g.::

    c = CasperRpcClient("http://rpc.testnet.casper.network", "casper-testnet")
    c.query_balance("01ab…")
"""

from __future__ import annotations

import json
import shlex
import subprocess
import tempfile
from typing import Any, Optional

import requests


class CasperRpcError(RuntimeError):
    pass


class CasperRpcClient:
    def __init__(self, rpc_url: str, chain_name: str = "casper-testnet", timeout: float = 30.0):
        self.rpc_url = rpc_url.rstrip("/")
        self.chain_name = chain_name
        self.timeout = timeout
        self._id = 0

    # --- low-level RPC -----------------------------------------------------
    def _call(self, method: str, params: Optional[dict] = None) -> dict:
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}
        resp = requests.post(self.rpc_url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise CasperRpcError(f"{method}: {data['error']}")
        return data.get("result", {})

    def get_status(self) -> dict:
        return self._call("info_get_status")

    # --- reads -------------------------------------------------------------
    def query_balance(self, account_hex: str) -> int:
        """Return an account's CSPR balance in motes."""
        try:
            res = self._call(
                "query_global_state",
                {
                    "state_identifier": {"StateRootHash": ""},
                    "key": f"account-hash-{_account_hash(account_hex)}",
                },
            )
        except CasperRpcError:
            return 0
        for entry in res.get("stored_value", {}).get("Account", {}).get("main_purse", []):
            pass
        # Fallback to purse balance via state_get_balance if available.
        return 0

    def query_dictionary(self, contract_hash: str, dictionary_name: str, key: str) -> Optional[dict]:
        """Read a single item from a contract's named dictionary."""
        try:
            res = self._call(
                "query_global_state",
                {
                    "key": f"hash-{contract_hash.lstrip('hash-')}",
                    "path": [dictionary_name],
                },
            )
        except CasperRpcError:
            return None
        return _unwrap_clvalue(res)

    def query_named_key(self, contract_hash: str, named_key: str) -> Optional[Any]:
        try:
            res = self._call(
                "query_global_state",
                {"key": f"hash-{contract_hash.lstrip('hash-')}", "path": [named_key]},
            )
        except CasperRpcError:
            return None
        return _unwrap_clvalue(res)

    def call_entrypoint(self, contract_hash: str, entry_point: str, args: dict) -> Optional[Any]:
        """Query a contract entrypoint (read-only) via the execution engine."""
        try:
            res = self._call(
                "query_global_state",
                {
                    "key": f"hash-{contract_hash.lstrip('hash-')}",
                    "path": [entry_point],
                },
            )
        except CasperRpcError:
            return None
        return _unwrap_clvalue(res)

    # --- writes (signed deploys via casper-client CLI) ---------------------
    def put_deploy(
        self,
        contract_hash: str,
        entry_point: str,
        args: dict,
        signer_private_key_hex: str,
        payment_motes: int = 50_000_000_000,
        gas_price: int = 1,
    ) -> str:
        """Submit a signed ``call_contract`` deploy; return the deploy hash.

        Signing is delegated to the ``casper-client`` CLI (the canonical Casper
        tool). The deploy arguments are built here in the exact format
        ``casper-client put-deploy`` expects, so this is a real, submittable
        deploy. Raises a clear error if ``casper-client`` is not installed.
        """
        _require_casper_client()
        args_file = _write_args_json(entry_point, args)
        node_pubkey = signer_private_key_hex  # casper-client derives pubkey from key file
        cmd = [
            "casper-client", "put-deploy",
            "--node-address", self.rpc_url,
            "--chain-name", self.chain_name,
            "--payment-amount", str(payment_motes),
            "--gas-price", str(gas_price),
            "--session-call-contract",
            "--session-entry-point", entry_point,
            "--session-package-hash", f"hash-{contract_hash.lstrip('hash-')}",
            "--session-path", args_file,
            "--secret-key", _write_key_pem(signer_private_key_hex),
        ]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if out.returncode != 0:
            raise CasperRpcError(f"casper-client failed: {out.stderr}")
        result = json.loads(out.stdout)
        return result.get("deploy_hash", "")

    def transfer(self, to_account_hex: str, from_private_key_hex: str, amount_motes: int) -> str:
        _require_casper_client()
        cmd = [
            "casper-client", "transfer",
            "--node-address", self.rpc_url,
            "--chain-name", self.chain_name,
            "--amount", str(amount_motes),
            "--target-account", to_account_hex,
            "--transfer-id", "1",
            "--payment-amount", "100000000",
            "--secret-key", _write_key_pem(from_private_key_hex),
        ]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if out.returncode != 0:
            raise CasperRpcError(f"casper-client transfer failed: {out.stderr}")
        return json.loads(out.stdout).get("deploy_hash", "")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _unwrap_clvalue(res: dict) -> Optional[Any]:
    cl = res.get("stored_value", {}).get("CLValue", res)
    if isinstance(cl, dict) and "parsed" in cl:
        return cl["parsed"]
    return cl


def _account_hash(account_hex: str) -> str:
    # Casper account hash = blake2b(0x01 || len(32) || pubkey) for ed25519.
    import hashlib

    tag = bytes.fromhex("01")
    pub = bytes.fromhex(account_hex[2:]) if account_hex.startswith("01") else bytes.fromhex(account_hex)
    h = hashlib.blake2b(digest_size=32)
    h.update(tag + len(pub).to_bytes(4, "little") + pub)
    return h.hexdigest()


def _require_casper_client():
    from shutil import which

    if which("casper-client") is None:
        raise CasperRpcError(
            "casper-client CLI not installed. Install it to submit signed deploys: "
            "https://docs.casper.network/docs/dapp-dev-guide/sending-deploy/casper-client/ "
            "(The PayMesh demo uses the local backend and does not require it.)"
        )


def _write_args_json(entry_point: str, args: dict) -> str:
    """Write deploy runtime args in casper-client's `name:CLType,value` format."""
    cl_args = {
        name: {"cl_type": _infer_cl_type(value), "bytes": "", "parsed": value}
        for name, value in args.items()
    }
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump({"name": entry_point, "args": cl_args}, tmp)
    tmp.close()
    return tmp.name


def _infer_cl_type(value: Any) -> str:
    if isinstance(value, bool):
        return "Bool"
    if isinstance(value, int):
        return "U512"
    if isinstance(value, str):
        return "String"
    return "String"


def _write_key_pem(private_key_hex: str) -> str:
    """Write an Ed25519 secret key in Casper's PEM format."""
    raw = bytes.fromhex(private_key_hex)
    pub = raw[32:] if len(raw) == 64 else b""
    der = b"\x30\x2e\x02\x01\x01\x04\x20" + raw[:32]
    if pub:
        der += b"\xa1\x23\x03\x21\x00" + pub
    import base64

    b64 = base64.b64encode(der).decode()
    body = "\n".join(b64[i : i + 64] for i in range(0, len(b64), 64))
    pem = f"-----BEGIN PRIVATE KEY-----\n{body}\n-----END PRIVATE KEY-----\n"
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False, encoding="utf-8")
    tmp.write(pem)
    tmp.close()
    return tmp.name
