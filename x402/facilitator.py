"""PayMesh x402 facilitator.

The facilitator is the trust-minimizing middle of the x402 flow: it verifies a
client's payment signature against the requested :class:`PaymentRequirements`
and, once valid, settles the payment by recording it on the
:class:`~x402.ledger.Ledger` (on-chain ``Settlement`` contract, or its local
mirror).

Endpoints (FastAPI):

- ``POST /verify``  — validate a ``PaymentPayload`` without settling.
- ``POST /settle``  — verify **and** settle; returns a settlement receipt.
- ``GET  /balances/{account}`` — read an escrow balance (dashboard).
- ``GET  /recent_payments``    — read the payment feed (dashboard).

Run standalone::

    python -m x402.facilitator --port 8001
"""

from __future__ import annotations

import argparse
import logging
import threading
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .crypto import canonical_authorization, verify_signature
from .ledger import (
    InsufficientBalance,
    LocalLedger,
    get_ledger,
    set_ledger,
)
from .types import (
    PaymentPayload,
    PaymentRequirements,
    SettleResponse,
    VerifyResponse,
)

log = logging.getLogger("paymesh.x402.facilitator")


# --- replay protection: single-use nonces ----------------------------------
_used_nonces: set[str] = set()
_nonce_lock = threading.Lock()


class VerifyRequest(BaseModel):
    paymentPayload: PaymentPayload
    paymentRequirements: PaymentRequirements


class SettleRequest(VerifyRequest):
    pass


def _verify(payload: PaymentPayload, reqs: PaymentRequirements) -> Optional[str]:
    """Return ``None`` if valid, else an error string."""
    inner = payload.payload
    # 1. network / scheme match
    if payload.network != reqs.network:
        return f"network mismatch: {payload.network} != {reqs.network}"
    if payload.scheme != reqs.scheme:
        return f"scheme mismatch: {payload.scheme} != {reqs.scheme}"
    # 2. value matches the required amount exactly (exact scheme)
    if int(inner.value) != int(reqs.maxAmountRequired):
        return (
            f"amount mismatch: {inner.value} != {reqs.maxAmountRequired}"
        )
    # 3. recipient matches the provider's account
    if inner.recipient != reqs.pay_to:
        return "recipient does not match pay_to"
    # 4. signature is valid for the sender's account
    auth = canonical_authorization(
        inner.sender, inner.recipient, inner.value, inner.service_id, inner.nonce
    )
    if auth != inner.authorization:
        return "authorization payload tampered (canonical string mismatch)"
    if not verify_signature(auth, payload.signature, inner.sender):
        return "invalid signature"
    # 5. freshness / expiry
    if int(reqs.expires) and int(reqs.expires) < __import__("time").time():
        return "payment requirements expired"
    return None


def _consume_nonce(nonce: str) -> Optional[str]:
    with _nonce_lock:
        if nonce in _used_nonces:
            return "nonce already used (replay)"
        _used_nonces.add(nonce)
    return None


def create_facilitator_app() -> FastAPI:
    app = FastAPI(title="PayMesh x402 Facilitator", version="1.0.0")

    # Allow the React dashboard (Vite dev server) and other browsers to call us.
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.post("/verify", response_model=VerifyResponse)
    def verify(req: VerifyRequest) -> VerifyResponse:
        err = _verify(req.paymentPayload, req.paymentRequirements)
        if err:
            return VerifyResponse(isValid=False, isVerified=False, error=err)
        return VerifyResponse(isValid=True, isVerified=True)

    @app.post("/settle", response_model=SettleResponse)
    def settle(req: SettleRequest) -> SettleResponse:
        payload = req.paymentPayload
        reqs = req.paymentRequirements
        err = _verify(payload, reqs)
        if err:
            return SettleResponse(success=False, error=err)
        err = _consume_nonce(payload.payload.nonce)
        if err:
            return SettleResponse(success=False, error=err)

        ledger = get_ledger()
        try:
            tx = ledger.record_payment(
                payer=payload.payload.sender,
                provider=payload.payload.recipient,
                service_id=payload.payload.service_id,
                amount_motes=int(payload.payload.value),
                payment_proof=payload.signature,
            )
        except InsufficientBalance as e:
            return SettleResponse(
                success=False, payer=payload.payload.sender, error=str(e)
            )

        log.info(
            "settled %s motes %s->%s for %s (%s)",
            payload.payload.value,
            payload.payload.sender[:12],
            payload.payload.recipient[:12],
            payload.payload.service_id,
            tx,
        )
        return SettleResponse(
            success=True,
            network=reqs.network,
            transaction=tx,
            payer=payload.payload.sender,
            payee=payload.payload.recipient,
        )

    # --- read endpoints for dashboard / SDK --------------------------------
    @app.get("/balances/{account}")
    def balance(account: str) -> dict:
        return {"account": account, "balance_motes": get_ledger().balance_of(account)}

    @app.get("/recent_payments")
    def recent(limit: int = 20) -> dict:
        recs = get_ledger().recent_payments(limit)
        return {
            "payments": [
                {
                    "index": r.index,
                    "payer": r.payer,
                    "provider": r.provider,
                    "service_id": r.service_id,
                    "amount_motes": r.amount_motes,
                    "payment_proof": r.payment_proof,
                    "timestamp": r.timestamp,
                }
                for r in recs
            ]
        }

    @app.get("/stats")
    def stats() -> dict:
        s = get_ledger().stats()
        return {
            "service_count": s.service_count,
            "total_payments": s.total_payments,
            "total_volume_motes": s.total_volume_motes,
            "total_staked_motes": s.total_staked_motes,
        }

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "paymesh-x402-facilitator"}

    return app


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="PayMesh x402 facilitator")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    # Default to the local ledger (offline-capable demo). On-chain mode is
    # selected by the demo/SDK constructing an OnChainLedger and calling
    # set_ledger() before importing the app — see README.
    if get_ledger() is None or not isinstance(get_ledger(), LocalLedger):
        pass  # respect an externally-installed ledger
    set_ledger(LocalLedger())

    app = create_facilitator_app()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
