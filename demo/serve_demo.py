"""Keep the PayMesh marketplace node + provider running for the dashboard/demo.

Starts the node (facilitator + registry + ledger), registers a provider agent
that serves a paid risk-score API, and seeds a few real x402 payments so the
dashboard has live data immediately. Stays up so the dashboard can poll it.

    python demo/serve_demo.py
    # then: cd dashboard && npm run dev
"""

from __future__ import annotations

import logging
import os
import random
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdk", "python"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import uvicorn

from paymesh import HttpContractBackend, PayMeshClient, generate_account
from x402.node import create_paymesh_node_app
from x402.provider import create_provider_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("serve-demo")

NODE_PORT = 8001
PROVIDER_PORT = 8002


def _wait(port, t=20.0):
    deadline = time.time() + t
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), 0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"port {port} not ready")


def _serve(app, port):
    threading.Thread(target=uvicorn.run, args=(app,), kwargs={"host": "127.0.0.1", "port": port, "log_level": "warning"}, daemon=True).start()


def main():
    log.info("starting PayMesh node on :%d …", NODE_PORT)
    _serve(create_paymesh_node_app(), NODE_PORT)
    _wait(NODE_PORT)
    node_url = f"http://127.0.0.1:{NODE_PORT}"

    # provider
    prov_acct = generate_account("provider")
    prov_client = PayMeshClient(account=prov_acct, backend=HttpContractBackend(node_url), facilitator_url=node_url)
    endpoint = f"http://127.0.0.1:{PROVIDER_PORT}/risk-score"
    try:
        prov_client.register_service("risk-score-api", "DeFi Wallet Risk Score API", endpoint, 0.05, 5.0)
    except Exception:
        pass
    prov_client.stake("risk-score-api", 5.0)

    prov_app = create_provider_app(prov_acct, facilitator_url=node_url)

    @prov_app.paid_route("/risk-score", price_motes=50_000_000, service_id="risk-score-api", description="DeFi risk score")
    def risk_score(request):
        import hashlib

        w = request.query_params.get("wallet") or "0x" + "00" * 20
        base = int(hashlib.sha256(w.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
        score = round(min(0.99, max(0.01, 0.05 + base * 0.9 + random.uniform(-0.02, 0.02))), 3)
        return {"service": "risk-score-api", "wallet": w, "risk_score": score, "label": "low" if score < 0.33 else "moderate" if score < 0.66 else "high", "model": "paymesh-risk-v1"}

    log.info("starting provider on :%d …", PROVIDER_PORT)
    _serve(prov_app, PROVIDER_PORT)
    _wait(PROVIDER_PORT)

    # seed a few paid calls + a rating so the dashboard is alive
    con_acct = generate_account("consumer")
    import requests

    requests.post(f"{node_url}/registry/deposit", json={"account": con_acct.public_account_hex, "amount_cspr": 10.0}, timeout=10)
    con_client = PayMeshClient(account=con_acct, backend=HttpContractBackend(node_url), facilitator_url=node_url)
    for i in range(3):
        try:
            con_client.call_service("risk-score-api", wallet="0x" + "".join(random.choice("0123456789abcdef") for _ in range(40)))
        except Exception as e:
            log.warning("seed call %d failed: %s", i, e)
    con_client.rate_service("risk-score-api", 5, "fast & accurate risk scoring")
    log.info("seeded 3 payments + rating. Dashboard data ready.")
    log.info("node: %s  |  provider: %s", node_url, endpoint)
    log.info("dashboard: cd dashboard && npm run dev   (VITE_NODE_URL defaults to %s)", node_url)
    log.info("press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        log.info("bye")


if __name__ == "__main__":
    main()
