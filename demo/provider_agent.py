"""PayMesh Provider Agent — registers & serves a paid "risk-score API".

This agent:
  1. Generates (or loads) a Casper Ed25519 identity.
  2. Registers a "risk-score-api" service on the marketplace node and stakes CSPR.
  3. Starts an x402 resource server: callers get HTTP 402 until they pay, then
     receive a computed DeFi wallet risk score.

Run (after the node is up)::

    python demo/provider_agent.py --node http://127.0.0.1:8001 --port 8002
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import random
import sys
import time

# Make the repo packages importable when run from the project root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdk", "python"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from paymesh import HttpContractBackend, PayMeshClient, generate_account  # noqa: E402
from x402.provider import create_provider_app  # noqa: E402

log = logging.getLogger("provider-agent")

SERVICE_ID = "risk-score-api"
SERVICE_NAME = "DeFi Wallet Risk Score API"
PRICE_PER_CALL_CSPR = 0.05
STAKE_CSPR = 5.0


def compute_risk_score(wallet_address: str) -> dict:
    """A deterministic-ish 'AI risk model' over a wallet address."""
    h = hashlib.sha256(wallet_address.encode()).hexdigest()
    base = int(h[:8], 16) / 0xFFFFFFFF  # 0..1
    score = round(0.05 + base * 0.9, 3)
    # tiny noise so repeat calls differ slightly (like a live model)
    score = round(min(0.99, max(0.01, score + random.uniform(-0.02, 0.02))), 3)
    factors = {
        "tx_volume": round(0.3 + (int(h[8:12], 16) / 0xFFFF) * 0.7, 3),
        "counterparty_risk": round(int(h[12:16], 16) / 0xFFFF, 3),
        "age_days": int(h[16:24], 16) % 1000,
    }
    label = "low" if score < 0.33 else "moderate" if score < 0.66 else "high"
    return {
        "service": SERVICE_ID,
        "wallet": wallet_address,
        "risk_score": score,
        "label": label,
        "factors": factors,
        "model": "paymesh-risk-v1",
        "computed_at": int(time.time()),
    }


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="PayMesh provider agent")
    parser.add_argument("--node", default="http://127.0.0.1:8001", help="PayMesh node URL")
    parser.add_argument("--host", default="127.0.0.1", help="provider server host")
    parser.add_argument("--port", type=int, default=8002, help="provider server port")
    parser.add_argument("--key", default=None, help="Ed25519 private key hex (else generated)")
    args = parser.parse_args()

    # 1. Identity
    from paymesh import account_from_private_key

    acct = account_from_private_key(args.key, "provider-agent") if args.key else generate_account("provider-agent")
    log.info("provider identity: %s", acct.public_account_hex)

    # 2. Register + stake on the marketplace node
    backend = HttpContractBackend(args.node)
    client = PayMeshClient(account=acct, backend=backend, facilitator_url=args.node)

    endpoint = f"http://{args.host}:{args.port}/risk-score"
    try:
        client.register_service(SERVICE_ID, SERVICE_NAME, endpoint, PRICE_PER_CALL_CSPR, STAKE_CSPR)
        log.info("registered %s @ %s CSPR/call", SERVICE_ID, PRICE_PER_CALL_CSPR)
    except Exception as e:
        log.warning("register skipped (%s) — service may already exist", e)

    client.stake(SERVICE_ID, STAKE_CSPR)
    svc = client.get_service(SERVICE_ID)
    log.info("service active=%s, stake=%s CSPR", svc.active, STAKE_CSPR)

    # 3. Start the x402 resource server
    app = create_provider_app(acct, facilitator_url=args.node)

    @app.paid_route(
        "/risk-score",
        price_motes=int(PRICE_PER_CALL_CSPR * 1_000_000_000),
        service_id=SERVICE_ID,
        description=SERVICE_NAME,
    )
    def risk_score(request):
        wallet = request.query_params.get("wallet") or "0x" + "00" * 20
        return compute_risk_score(wallet)

    log.info("serving risk-score on %s (pay %s CSPR/call via x402)", endpoint, PRICE_PER_CALL_CSPR)
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
