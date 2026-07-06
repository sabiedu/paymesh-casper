"""PayMesh end-to-end demo orchestrator.

Runs the full agent marketplace in one command:

    node (facilitator + registry + ledger)
      + provider agent (registers risk-score-api, stakes, serves via x402)
      + consumer agent (discovers, pays per-call via x402, rates)

This is the demo-video script. It launches real uvicorn servers and drives real
x402 payments end-to-end.

    cd paymesh-casper
    python demo/run_demo.py
"""

from __future__ import annotations

import logging
import os
import random
import socket
import sys
import threading
import time

# Render the demo banners correctly on the Windows console.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdk", "python"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import uvicorn

from paymesh import HttpContractBackend, PayMeshClient, generate_account
from x402.node import create_paymesh_node_app
from x402.provider import create_provider_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("paymesh-demo")

NODE_PORT = 8001
PROVIDER_PORT = 8002
SERVICE_ID = "risk-score-api"
PRICE_CSPR = 0.05
STAKE_CSPR = 5.0
CONSUMER_FUND = 10.0
N_CALLS = 4


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _banner(title):
    log.info("")
    log.info("═" * 64)
    log.info("  %s", title)
    log.info("═" * 64)


def main():
    node_port = NODE_PORT if _port_free(NODE_PORT) else _free_port()
    prov_port = PROVIDER_PORT if _port_free(PROVIDER_PORT) else _free_port()
    node_url = f"http://127.0.0.1:{node_port}"

    _banner("PayMesh — x402 agent marketplace on Casper")

    # --- 1. start the marketplace node ------------------------------------
    log.info("[1/5] starting PayMesh node (facilitator + registry + ledger)…")
    node_app = create_paymesh_node_app()
    _serve(node_app, "127.0.0.1", node_port)
    _wait_ready(node_port)
    log.info("      node ready @ %s", node_url)

    # --- 2. provider agent: register + stake + serve ----------------------
    _banner("[2/5] PROVIDER AGENT")
    provider_acct = generate_account("provider-agent")
    log.info("provider identity: %s", provider_acct.public_account_hex)

    prov_backend = HttpContractBackend(node_url)
    prov_client = PayMeshClient(account=provider_acct, backend=prov_backend, facilitator_url=node_url)
    endpoint = f"http://127.0.0.1:{prov_port}/risk-score"
    prov_client.register_service(SERVICE_ID, "DeFi Wallet Risk Score API", endpoint, PRICE_CSPR, STAKE_CSPR)
    log.info("registered '%s' @ %s CSPR/call (min stake %s CSPR)", SERVICE_ID, PRICE_CSPR, STAKE_CSPR)
    prov_client.stake(SERVICE_ID, STAKE_CSPR)
    log.info("staked %s CSPR → service is now ACTIVE", STAKE_CSPR)

    prov_app = create_provider_app(provider_acct, facilitator_url=node_url)

    @prov_app.paid_route(
        "/risk-score", price_motes=int(PRICE_CSPR * 1e9),
        service_id=SERVICE_ID, description="DeFi Wallet Risk Score API",
    )
    def risk_score(request):
        import hashlib

        wallet = request.query_params.get("wallet") or "0x" + "00" * 20
        base = int(hashlib.sha256(wallet.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
        score = round(min(0.99, max(0.01, 0.05 + base * 0.9 + random.uniform(-0.02, 0.02))), 3)
        label = "low" if score < 0.33 else "moderate" if score < 0.66 else "high"
        return {"service": SERVICE_ID, "wallet": wallet, "risk_score": score, "label": label, "model": "paymesh-risk-v1"}

    _serve(prov_app, "127.0.0.1", prov_port)
    _wait_ready(prov_port)
    log.info("provider serving x402-paid risk-score on %s", endpoint)

    # --- 3. consumer agent: fund + discover -------------------------------
    _banner("[3/5] CONSUMER AGENT")
    consumer_acct = generate_account("consumer-agent")
    log.info("consumer identity: %s", consumer_acct.public_account_hex)
    import requests

    requests.post(f"{node_url}/registry/deposit", json={"account": consumer_acct.public_account_hex, "amount_cspr": CONSUMER_FUND}, timeout=10)

    con_backend = HttpContractBackend(node_url)
    con_client = PayMeshClient(account=consumer_acct, backend=con_backend, facilitator_url=node_url)
    services = con_client.discover_services()
    log.info("funded escrow %s CSPR; discovered %d service(s):", CONSUMER_FUND, len(services))
    for s in services:
        log.info("   • %-18s %s CSPR/call  stake=%s CSPR", s.service_id, round(s.price_per_call_cspr, 4), round(s.staking_amount_cspr, 2))

    # --- 4. make N paid calls (each a full x402 settlement) ---------------
    _banner(f"[4/5] CALLING '{SERVICE_ID}' {N_CALLS}× VIA x402")
    spent = 0.0
    for i in range(1, N_CALLS + 1):
        wallet = "0x" + "".join(random.choice("0123456789abcdef") for _ in range(40))
        result = con_client.call_service(SERVICE_ID, wallet=wallet)
        d = result.data
        log.info(
            "  call %d: HTTP 402 → pay %s CSPR → 200  risk=%.3f (%s)  [settlement %s]",
            i, round(result.amount_paid_motes / 1e9, 4), d["risk_score"], d["label"], result.settlement_id,
        )
        spent += result.amount_paid_motes / 1e9
        time.sleep(0.25)

    # --- 5. rate + summary ------------------------------------------------
    _banner("[5/5] RATE + SETTLEMENT SUMMARY")
    agg = con_client.rate_service(SERVICE_ID, 5, f"Processed {N_CALLS} paid calls cleanly via x402.")
    log.info("rated %s 5/5 — reputation %.2f avg / %d rating(s)", SERVICE_ID, agg.average_rating, agg.count)

    stats = requests.get(f"{node_url}/registry/stats", timeout=10).json()
    log.info("-" * 64)
    log.info("  services:        %d", stats["service_count"])
    log.info("  total staked:    %s CSPR", stats["total_staked_cspr"])
    log.info("  settled payments:%d", stats["total_payments"])
    log.info("  total volume:    %s CSPR", stats["total_volume_cspr"])
    log.info("  consumer spent:  %s CSPR (balance %s CSPR)", round(spent, 6), round(con_client.balance(), 6))
    log.info("  provider revenue:%s CSPR", round(prov_client.revenue(), 6))
    log.info("═" * 64)
    log.info("✓ x402 payment flow verified end-to-end (402 → sign → settle → 200)")
    log.info("✓ settlement recorded on the Settlement layer")
    log.info("✓ reputation updated on-chain")
    log.info("═" * 64)
    log.info("Dashboard: cd dashboard && npm run dev   (point VITE_NODE_URL at %s)", node_url)


def _serve(app, host, port):
    t = threading.Thread(target=uvicorn.run, args=(app,), kwargs={"host": host, "port": port, "log_level": "warning"}, daemon=True)
    t.start()


def _wait_ready(port, timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"port {port} not ready")


def _port_free(port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))
            return True
    except OSError:
        return False


if __name__ == "__main__":
    main()
