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

    import requests

    # --- seed multiple services via the demo endpoint so dashboard is rich ---
    catalog = requests.get(f"{node_url}/demo/catalog", timeout=10).json()
    catalog = catalog.get("services", catalog) if isinstance(catalog, dict) else catalog
    log.info("seeding %d services from catalog…", len(catalog))

    for item in catalog[:4]:
        sid = requests.post(f"{node_url}/demo/register-provider", json={"service_id": item["service_id"]}, timeout=30).json()
        svc = sid.get("service", sid)
        real_id = svc.get("service_id", item["service_id"])
        n_calls = random.randint(3, 6)
        for _ in range(n_calls):
            try:
                requests.post(f"{node_url}/demo/consumer-call", json={"service_id": real_id}, timeout=15)
            except Exception as e:
                log.warning("seed call failed: %s", e)
        log.info("  ✓ %s — %d paid calls", item.get("name", real_id), n_calls)

    log.info("seeded marketplace with %d services + payments. Dashboard data ready.", len(catalog[:4]))
    log.info("node: %s  |  provider: %s", node_url, f"http://127.0.0.1:{NODE_PORT}/serve")
    log.info("dashboard: cd dashboard && npm run dev")
    log.info("press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        log.info("bye")


if __name__ == "__main__":
    main()
