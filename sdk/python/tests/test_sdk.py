"""End-to-end tests for the PayMesh SDK over the local backend.

Run with::

    cd paymesh-casper
    python -m pytest sdk/python/tests/test_sdk.py -v -s
"""

import os
import socket
import sys
import threading
import time

import pytest
import uvicorn

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from paymesh import PayMeshClient, generate_account
from x402.facilitator import create_facilitator_app
from x402.ledger import LocalLedger, set_ledger
from x402.provider import create_provider_app


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _ServerThread(threading.Thread):
    def __init__(self, app, host, port):
        super().__init__(daemon=True)
        self.server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))

    def run(self):
        self.server.run()

    def wait_until_ready(self, host, port, timeout=15.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with socket.create_connection((host, port), timeout=0.5):
                    return True
            except OSError:
                time.sleep(0.1)
        return False


@pytest.fixture(scope="module")
def stack():
    ledger = LocalLedger()
    set_ledger(ledger)

    provider_acct = generate_account("provider")
    consumer_acct = generate_account("consumer")

    fac_port = _free_port()
    prov_port = _free_port()
    fac_url = f"http://127.0.0.1:{fac_port}"

    fac_app = create_facilitator_app()
    prov_app = create_provider_app(provider_acct, facilitator_url=fac_url)

    @prov_app.paid_route("/risk-score", price_motes=50_000_000, service_id="risk-score-api", description="DeFi risk score")
    def risk_score(request):
        return {"risk_score": 0.73, "label": "moderate"}

    fac_thread = _ServerThread(fac_app, "127.0.0.1", fac_port)
    prov_thread = _ServerThread(prov_app, "127.0.0.1", prov_port)
    fac_thread.start()
    prov_thread.start()
    fac_thread.wait_until_ready("127.0.0.1", fac_port)
    prov_thread.wait_until_ready("127.0.0.1", prov_port)

    # shared local backend so both clients see the same registry state
    from paymesh import LocalContractBackend

    shared_backend = LocalContractBackend()
    provider = PayMeshClient(account=provider_acct, backend=shared_backend, facilitator_url=fac_url)
    consumer = PayMeshClient(account=consumer_acct, backend=shared_backend, facilitator_url=fac_url)

    yield {
        "provider": provider,
        "consumer": consumer,
        "provider_acct": provider_acct,
        "consumer_acct": consumer_acct,
        "prov_port": prov_port,
        "ledger": ledger,
    }


def test_register_stake_discover(stack):
    prov = stack["provider"]
    prov.register_service(
        "risk-score-api", "Risk Score API",
        f"http://127.0.0.1:{stack['prov_port']}/risk-score",
        price_per_call=0.05, stake_amount=5.0,
    )
    svc = prov.get_service("risk-score-api")
    assert svc.active is False
    prov.stake("risk-score-api", 5.0)
    svc = prov.get_service("risk-score-api")
    assert svc.active is True
    assert svc.price_per_call_cspr == pytest.approx(0.05)


def test_discover_and_call(stack):
    cons = stack["consumer"]
    cons.deposit(2.0)
    services = cons.discover_services()
    assert any(s.service_id == "risk-score-api" for s in services)

    result = cons.call_service("risk-score-api")
    assert result.success is True
    assert result.data["risk_score"] == 0.73
    assert cons.balance() == pytest.approx(1.95, abs=1e-6)
    assert stack["provider"].revenue() == pytest.approx(0.05, abs=1e-6)


def test_rate_and_reputation(stack):
    cons = stack["consumer"]
    agg = cons.rate_service("risk-score-api", 5, "great")
    assert agg.count == 1
    assert agg.average_rating == pytest.approx(5.0)
    rep = cons.get_reputation("risk-score-api")
    assert rep.count == 1
    svc = cons.get_service("risk-score-api")
    assert svc.average_rating == pytest.approx(5.0)


def test_rerate_replaces(stack):
    cons = stack["consumer"]
    agg = cons.rate_service("risk-score-api", 3, "changed my mind")
    assert agg.count == 1
    assert agg.average_rating == pytest.approx(3.0)
