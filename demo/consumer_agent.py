"""PayMesh Consumer Agent — discovers, pays for, and rates a service.

This agent:
  1. Generates a Casper Ed25519 identity and funds its escrow balance.
  2. Discovers services on the marketplace node.
  3. Calls the "risk-score-api" — the SDK handles the x402 402 → pay → 200 flow
     automatically.
  4. Rates the service on-chain (reputation layer).

Run (after node + provider are up)::

    python demo/consumer_agent.py --node http://127.0.0.1:8001

Make several paid calls to build a transaction history + reputation::

    python demo/consumer_agent.py --node http://127.0.0.1:8001 --calls 5
"""

from __future__ import annotations

import argparse
import logging
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdk", "python"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from paymesh import HttpContractBackend, PayMeshClient, generate_account  # noqa: E402

log = logging.getLogger("consumer-agent")

SERVICE_ID = "risk-score-api"


def _wallet():
    return "0x" + "".join(random.choice("0123456789abcdef") for _ in range(40))


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="PayMesh consumer agent")
    parser.add_argument("--node", default="http://127.0.0.1:8001")
    parser.add_argument("--key", default=None, help="Ed25519 private key hex (else generated)")
    parser.add_argument("--fund", type=float, default=10.0, help="CSPR to fund escrow")
    parser.add_argument("--calls", type=int, default=3, help="paid calls to make")
    parser.add_argument("--service", default=SERVICE_ID)
    args = parser.parse_args()

    from paymesh import account_from_private_key

    acct = account_from_private_key(args.key, "consumer-agent") if args.key else generate_account("consumer-agent")
    log.info("consumer identity: %s", acct.public_account_hex)

    backend = HttpContractBackend(args.node)
    client = PayMeshClient(account=acct, backend=backend, facilitator_url=args.node)

    # 1. Fund escrow (so the facilitator can settle per-call payments)
    import requests

    requests.post(f"{args.node}/registry/deposit", json={"account": acct.public_account_hex, "amount_cspr": args.fund}, timeout=10)
    log.info("funded escrow with %s CSPR (balance: %s)", args.fund, client.balance())

    # 2. Discover
    services = client.discover_services()
    log.info("discovered %d service(s):", len(services))
    for s in services:
        star = "★" * round(s.average_rating)
        log.info(
            "  • %-18s %s CSPR/call  %s  stake=%s CSPR  %s",
            s.service_id, round(s.price_per_call_cspr, 4), star or "—",
            round(s.staking_amount_cspr, 2), s.name,
        )

    target = args.service
    svc = client.get_service(target)
    if svc is None or not svc.active:
        log.error("service %r not available — is the provider running?", target)
        sys.exit(1)

    # 3. Make N paid calls (each is a full x402 settlement)
    total_spent = 0.0
    for i in range(1, args.calls + 1):
        wallet = _wallet()
        result = client.call_service(target, wallet=wallet)
        if not result.success:
            log.error("call %d failed", i)
            continue
        data = result.data
        log.info(
            "call %d: paid %s CSPR → risk_score=%.3f (%s) for %s  [settle=%s]",
            i, round(result.amount_paid_motes / 1e9, 4),
            data.get("risk_score"), data.get("label"), wallet[:10] + "…",
            result.settlement_id,
        )
        total_spent += result.amount_paid_motes / 1e9
        time.sleep(0.3)

    # 4. Rate the service
    rating = 5 if total_spent <= args.fund * 0.5 else 4
    review = f"Processed {args.calls} calls cleanly via x402. Smooth."
    agg = client.rate_service(target, rating, review)
    log.info(
        "rated %s %d/5 — reputation: %.2f avg over %d rating(s)",
        target, rating, agg.average_rating, agg.count,
    )

    # 5. Summary
    log.info("=" * 60)
    log.info("CONSUMER SUMMARY")
    log.info("  calls made:    %d", args.calls)
    log.info("  total spent:   %s CSPR", round(total_spent, 6))
    log.info("  escrow balance:%s CSPR", round(client.balance(), 6))
    log.info("  provider revenue so far: %s CSPR", round(_provider_revenue(args.node, svc.provider), 6))
    log.info("=" * 60)


def _provider_revenue(node: str, provider: str) -> float:
    import requests

    try:
        r = requests.get(f"{node}/balances/{provider}", timeout=10)
        return r.json().get("balance_motes", 0) / 1e9
    except Exception:
        return 0.0


if __name__ == "__main__":
    main()
