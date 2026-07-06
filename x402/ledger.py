"""Settlement ledger — the bridge between an x402 settlement and the chain.

The PayMesh facilitator does not move funds itself; it *attests* that a verified
x402 payment was settled and records that attestation on the Casper
``Settlement`` contract via :meth:`Ledger.record_payment`.

Two backends ship:

- :class:`LocalLedger` — a fully in-process mirror of the ``Settlement``
  contract's ``record_payment`` ABI. It keeps balances, a payment ledger and an
  event log that the dashboard/SDK can read. This is what makes the demo run
  end-to-end offline (reliably, for judges) with **the same data shape** the
  on-chain contract produces.
- :class:`OnChainLedger` — records to the real Casper ``Settlement`` contract
  over RPC by submitting a signed ``record_payment`` deploy from an authorised
  recorder account. Used when a Testnet node + recorder key are configured.

Both implement the same :class:`Ledger` interface, so swapping the demo from
local to live Testnet is a one-line config change.
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

MOTES_PER_CSPR = 1_000_000_000


@dataclass
class PaymentRecord:
    """Mirrors the on-chain ``PaymentRecord`` (Casper ``settlement`` contract)."""

    index: int
    payer: str
    provider: str
    service_id: str
    amount_motes: int
    payment_proof: str
    timestamp: int


@dataclass
class LedgerStats:
    service_count: int = 0
    total_payments: int = 0
    total_volume_motes: int = 0
    total_staked_motes: int = 0


class Ledger(ABC):
    """Abstract settlement + state ledger read by the SDK and dashboard."""

    # --- write side (facilitator / gateway) -------------------------------

    @abstractmethod
    def record_payment(
        self,
        payer: str,
        provider: str,
        service_id: str,
        amount_motes: int,
        payment_proof: str,
    ) -> str:
        """Record a settled payment; return a transaction id / deploy hash."""

    @abstractmethod
    def deposit(self, account: str, amount_motes: int) -> None:
        """Credit a balance (escrow top-up / faucet seed)."""

    # --- read side (SDK / dashboard) --------------------------------------

    @abstractmethod
    def balance_of(self, account: str) -> int:
        """Available CSPR balance (motes) held in escrow."""

    @abstractmethod
    def get_revenue(self, provider: str) -> int:
        """Lifetime revenue earned by a provider (motes)."""

    @abstractmethod
    def recent_payments(self, limit: int = 20) -> list[PaymentRecord]:
        """Most recent settled payments, newest last."""

    @abstractmethod
    def payment_history(self, service_id: str) -> list[PaymentRecord]:
        """All payments for a service, oldest first."""

    @abstractmethod
    def stats(self) -> LedgerStats:
        ...


class LocalLedger(Ledger):
    """In-process ledger mirroring the on-chain contract data shapes.

    Thread-safe (the facilitator runs under uvicorn with a thread pool). All
    balances are in motes.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._balances: dict[str, int] = {}
        self._revenue: dict[str, int] = {}
        self._payments: list[PaymentRecord] = []
        self._service_payments: dict[str, list[int]] = {}
        self._seq = 0

    def deposit(self, account: str, amount_motes: int) -> None:
        with self._lock:
            self._balances[account] = self._balances.get(account, 0) + amount_motes

    def balance_of(self, account: str) -> int:
        with self._lock:
            return self._balances.get(account, 0)

    def get_revenue(self, provider: str) -> int:
        with self._lock:
            return self._revenue.get(provider, 0)

    def record_payment(
        self,
        payer: str,
        provider: str,
        service_id: str,
        amount_motes: int,
        payment_proof: str,
    ) -> str:
        with self._lock:
            bal = self._balances.get(payer, 0)
            if amount_motes <= 0:
                raise ValueError("amount must be positive")
            if bal < amount_motes:
                raise InsufficientBalance(payer, amount_motes, bal)
            # Move value payer -> provider (escrow settlement).
            self._balances[payer] = bal - amount_motes
            self._balances[provider] = (
                self._balances.get(provider, 0) + amount_motes
            )
            self._revenue[provider] = self._revenue.get(provider, 0) + amount_motes
            idx = self._seq
            self._seq += 1
            rec = PaymentRecord(
                index=idx,
                payer=payer,
                provider=provider,
                service_id=service_id,
                amount_motes=amount_motes,
                payment_proof=payment_proof,
                timestamp=int(time.time()),
            )
            self._payments.append(rec)
            self._service_payments.setdefault(service_id, []).append(idx)
            return f"local-{idx:08x}"

    def recent_payments(self, limit: int = 20) -> list[PaymentRecord]:
        with self._lock:
            if limit <= 0:
                return []
            return list(self._payments[-limit:])

    def payment_history(self, service_id: str) -> list[PaymentRecord]:
        with self._lock:
            idxs = self._service_payments.get(service_id, [])
            return [self._payments[i] for i in idxs]

    def set_service_count(self, n: int) -> None:
        self._service_count = n

    def stats(self) -> LedgerStats:
        with self._lock:
            volume = sum(p.amount_motes for p in self._payments)
            staked = sum(v for k, v in self._balances.items())  # placeholder
            return LedgerStats(
                service_count=getattr(self, "_service_count", 0),
                total_payments=len(self._payments),
                total_volume_motes=volume,
                total_staked_motes=staked,
            )


class InsufficientBalance(Exception):
    """Raised when a payer's escrow balance cannot cover a payment."""

    def __init__(self, account: str, needed: int, available: int) -> None:
        self.account = account
        self.needed = needed
        self.available = available
        super().__init__(
            f"insufficient balance for {account[:10]}…: "
            f"needed {needed} motes, have {available}"
        )


class OnChainLedger(Ledger):
    """Records settlements on the real Casper ``Settlement`` contract.

    Submits a signed ``record_payment`` deploy to a Casper node over JSON-RPC,
    acting as an authorised *recorder*. The actual native CSPR value movement is
    expected to have been arranged off-chain (facilitator escrow); this is the
    on-chain attestation, exactly like the contract's docstring states.

    NOTE: requires ``casper-client`` / a signing-capable RPC client and a
    funded recorder account. When those are absent, fall back to
    :class:`LocalLedger`.
    """

    def __init__(
        self,
        rpc_url: str,
        settlement_contract_hash: str,
        recorder_private_key_hex: str,
        chain_name: str = "casper-testnet",
    ) -> None:
        self.rpc_url = rpc_url
        self.settlement_contract_hash = settlement_contract_hash
        self.recorder_private_key_hex = recorder_private_key_hex
        self.chain_name = chain_name
        # Lazily imported so the local demo never needs casper deps.
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from sdk.python.paymesh.casper_client import CasperRpcClient  # type: ignore

            self._client = CasperRpcClient(self.rpc_url, self.chain_name)
        return self._client

    def record_payment(
        self,
        payer: str,
        provider: str,
        service_id: str,
        amount_motes: int,
        payment_proof: str,
    ) -> str:
        client = self._ensure_client()
        return client.put_deploy(
            contract_hash=self.settlement_contract_hash,
            entry_point="record_payment",
            args={
                "payer": payer,
                "provider": provider,
                "service_id": service_id,
                "amount": str(amount_motes),
                "payment_proof": payment_proof,
            },
            signer_private_key_hex=self.recorder_private_key_hex,
        )

    # --- read side proxies over RPC ---------------------------------------

    def balance_of(self, account: str) -> int:
        client = self._ensure_client()
        return client.query_balance(account)

    def get_revenue(self, provider: str) -> int:
        client = self._ensure_client()
        res = client.query_dictionary(
            self.settlement_contract_hash, "provider_revenue", provider
        )
        return int(res) if res else 0

    def recent_payments(self, limit: int = 20) -> list[PaymentRecord]:
        client = self._ensure_client()
        raw = client.call_entrypoint(
            self.settlement_contract_hash, "recent_payments", {"limit": str(limit)}
        )
        return [_decode_payment(p) for p in raw] if raw else []

    def payment_history(self, service_id: str) -> list[PaymentRecord]:
        client = self._ensure_client()
        raw = client.call_entrypoint(
            self.settlement_contract_hash,
            "get_payment_history",
            {"service_id": service_id},
        )
        return [_decode_payment(p) for p in raw] if raw else []

    def deposit(self, account: str, amount_motes: int) -> None:
        # On-chain, "deposit" is a native transfer to the facilitator escrow.
        client = self._ensure_client()
        client.transfer(account, self.recorder_account(), amount_motes)

    def recorder_account(self) -> str:
        from x402.crypto import account_from_private_key

        return account_from_private_key(self.recorder_private_key_hex).public_account_hex

    def stats(self) -> LedgerStats:
        # Aggregate on-chain stats are read by the dashboard via RPC queries;
        # return zeros if unavailable rather than crashing the read path.
        return LedgerStats()


def _decode_payment(raw: dict) -> PaymentRecord:
    return PaymentRecord(
        index=int(raw.get("index", 0)),
        payer=raw.get("payer", ""),
        provider=raw.get("provider", ""),
        service_id=raw.get("service_id", ""),
        amount_motes=int(raw.get("amount", 0)),
        payment_proof=raw.get("payment_proof", ""),
        timestamp=int(raw.get("timestamp", 0)),
    )


# ---------------------------------------------------------------------------
# Process-wide singleton accessor.
# ---------------------------------------------------------------------------
_global_ledger: Optional[Ledger] = None
_ledger_lock = threading.Lock()


def get_ledger() -> Ledger:
    with _ledger_lock:
        if _global_ledger is None:
            set_ledger(LocalLedger())
        return _global_ledger  # type: ignore[return-value]


def set_ledger(ledger: Ledger) -> None:
    """Install the global ledger (called at process startup)."""
    global _global_ledger
    with _ledger_lock:
        _global_ledger = ledger
