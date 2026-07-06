"""
Deploy PayMesh contracts to Casper Testnet via CSPR.cloud RPC.

Uses pycspr Deploy V1 format with Odra required args.
Fresh key objects per deploy to avoid signing state issues.
"""
import sys
import json
import time
from pathlib import Path
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")

import requests
import pycspr
from pycspr import (
    create_deploy_parameters,
    create_standard_payment,
    create_deploy,
    read_wasm,
)
from pycspr.factory import create_private_key, create_public_key
from pycspr.crypto import get_key_pair_from_pem_file, KeyAlgorithm
from pycspr.types import ModuleBytes, DeployArgument, CL_String, CL_Bool

# ─── Configuration ───────────────────────────────────────────────────────────

RPC_URL = "https://node.testnet.cspr.cloud/rpc"
AUTH_TOKEN = "55f79117-fc4d-4d60-9956-65423f39a06a"
CHAIN_NAME = "casper-test"
KEY_PEM = str(Path(__file__).parent.parent / "keys" / "deployer_secret_key.pem")
WASM_DIR = Path(__file__).parent.parent / "wasm"
GAS_PAYMENT = 800_000_000_000  # 800 CSPR (block gas limit is 812.5 CSPR)

CONTRACTS = ["ServiceRegistry", "Settlement", "Staking", "Reputation"]

HEADERS = {"Authorization": AUTH_TOKEN, "Content-Type": "application/json"}


def load_keys():
    """Create FRESH key pair objects each time (avoids pycspr state bugs)."""
    algo = KeyAlgorithm.SECP256K1
    pvk_bytes, pbk_bytes = get_key_pair_from_pem_file(KEY_PEM, algo)
    pvk = create_private_key(algo, pvk_bytes, pbk_bytes)
    pbk = create_public_key(algo, pbk_bytes)
    account_hex = pycspr.crypto.get_account_key(algo, pbk_bytes).hex()
    return pvk, pbk, account_hex


def check_balance(account_hex):
    url = f"https://api.testnet.cspr.live/accounts/{account_hex}"
    r = requests.get(url, headers={"Accept": "application/json"}, timeout=15)
    if r.status_code == 200:
        balance = int(r.json().get("data", {}).get("balance", "0"))
        return balance
    return 0


def rpc(method, params=None):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params:
        payload["params"] = params
    return requests.post(RPC_URL, headers=HEADERS, json=payload, timeout=120).json()


def build_odra_args(contract_name):
    return [
        DeployArgument(
            "odra_cfg_package_hash_key_name",
            CL_String(contract_name.lower() + "_package_hash"),
        ),
        DeployArgument("odra_cfg_allow_key_override", CL_Bool(True)),
        DeployArgument("odra_cfg_is_upgradable", CL_Bool(True)),
        DeployArgument("odra_cfg_is_upgrade", CL_Bool(False)),
    ]


def deploy_contract(name, wasm_bytes, pbk, pvk):
    """Build, sign, and submit a contract deployment."""
    print(f"[{name}] Building deploy ({len(wasm_bytes):,} bytes WASM)...")

    # Fresh deploy params with current timestamp
    params = create_deploy_parameters(
        account=pbk,
        chain_name=CHAIN_NAME,
        ttl="30m",
        gas_price=1,
    )

    payment = create_standard_payment(GAS_PAYMENT)
    odra_args = build_odra_args(name)
    session = ModuleBytes(args=odra_args, module_bytes=wasm_bytes)

    deploy = create_deploy(params, payment, session)
    deploy_hash = deploy.hash.hex()
    print(f"  Deploy hash: {deploy_hash}")

    # Sign with fresh key
    deploy.approve(pvk)
    print(f"  Signed with secp256k1")

    # Serialize to JSON
    deploy_json = pycspr.to_json(deploy)
    if isinstance(deploy_json, str):
        deploy_json = json.loads(deploy_json)

    # Submit
    print(f"  Submitting to {CHAIN_NAME}...")
    result = rpc("account_put_deploy", {"deploy": deploy_json})

    if "result" in result:
        dhash = result["result"].get("deploy_hash", deploy_hash)
        print(f"  [OK] Submitted! Hash: {dhash}")
        return dhash
    elif "error" in result:
        err = result["error"]
        print(f"  [ERR] RPC error: {err.get('message', str(err))}")
        if "data" in err:
            print(f"        Detail: {str(err['data'])[:500]}")
        return None
    else:
        print(f"  [WARN] Unexpected: {json.dumps(result)[:300]}")
        return None


def check_deploy_status(dhash, timeout=180):
    """Poll CSPR.live REST API for deploy status."""
    url = f"https://api.testnet.cspr.live/deploys/{dhash}"
    start = time.time()
    while time.time() - start < timeout:
        r = requests.get(url, headers={"Accept": "application/json"}, timeout=15)
        if r.status_code == 200:
            data = r.json().get("data", {})
            status = data.get("status", "")
            if status == "processed":
                err = data.get("error_message", "")
                block = data.get("block_hash", "?")
                cost = data.get("cost", "?")
                gas = data.get("consumed_gas", "?")
                contract_hash = data.get("contract_hash")
                if err:
                    print(f"  [FAIL] Error: {err}")
                    if cost != "?":
                        print(f"         Cost: {int(cost)/1e9:.1f} CSPR (gas: {gas})")
                    return False, data
                else:
                    print(f"  [OK] Confirmed! Block: {block[:16]}...")
                    print(f"       Cost: {int(cost)/1e9:.1f} CSPR")
                    if contract_hash:
                        print(f"       Contract hash: {contract_hash}")
                    return True, data
            elif status in ("expired", "failed"):
                print(f"  [FAIL] Status: {status}")
                return False, data
        print(".", end="", flush=True)
        time.sleep(5)
    print(" [TIMEOUT]")
    return None, None


def main():
    pvk, pbk, account_hex = load_keys()
    print(f"Deployer account: {account_hex}")
    print(f"Algorithm:        secp256k1\n")

    print("=" * 60)
    print(f"PayMesh -> Casper Testnet ({GAS_PAYMENT/1e9:.0f} CSPR gas limit per contract)")
    print("=" * 60 + "\n")

    balance = check_balance(account_hex)
    print(f"Balance: {balance:,} motes = {balance/1e9:.0f} CSPR\n")

    needed = GAS_PAYMENT * len(CONTRACTS)
    if balance < needed:
        print(f"WARNING: Need {needed/1e9:.0f} CSPR for {len(CONTRACTS)} contracts, have {balance/1e9:.0f}")

    deployed = {}

    for name in CONTRACTS:
        wasm_path = WASM_DIR / f"{name}.wasm"
        if not wasm_path.exists():
            print(f"[{name}] WASM not found: {wasm_path}")
            continue

        # Recheck balance before each deploy
        bal = check_balance(account_hex)
        if bal < GAS_PAYMENT:
            print(f"[{name}] Skipping - balance too low ({bal/1e9:.0f} CSPR < {GAS_PAYMENT/1e9:.0f} CSPR)")
            break

        wasm_bytes = read_wasm(str(wasm_path))

        # Fresh keys for each deploy
        deploy_pvk, deploy_pbk, _ = load_keys()

        dhash = deploy_contract(name, wasm_bytes, deploy_pbk, deploy_pvk)

        if dhash:
            deployed[name] = {"deploy_hash": dhash}
            success, details = check_deploy_status(dhash)
            if details:
                deployed[name]["success"] = success
                deployed[name]["cost"] = details.get("cost")
                deployed[name]["gas"] = details.get("consumed_gas")
                deployed[name]["contract_hash"] = details.get("contract_hash")
        print()
        time.sleep(3)

    # Summary
    print("\n" + "=" * 60)
    print("DEPLOYMENT SUMMARY")
    print("=" * 60)
    for name in CONTRACTS:
        info = deployed.get(name)
        if info:
            success = info.get("success")
            chash = info.get("contract_hash")
            cost = info.get("cost")
            status = "[OK]" if success else "[FAIL]"
            print(f"  {status} {name}")
            print(f"      Deploy:  https://testnet.cspr.live/deploy/{info['deploy_hash']}")
            if cost:
                print(f"      Cost:    {int(cost)/1e9:.1f} CSPR")
            if chash:
                print(f"      Contract: {chash}")
        else:
            print(f"  [SKIP] {name}")

    # Save results
    results_file = Path(__file__).parent.parent / "keys" / "deployment_results.json"
    results_file.write_text(
        json.dumps(
            {
                "deployer": account_hex,
                "chain": CHAIN_NAME,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "gas_limit_per_contract": GAS_PAYMENT,
                "contracts": deployed,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nResults: {results_file}")


if __name__ == "__main__":
    main()
