"""Live end-to-end x402 flow: real HTTP servers + a paying client.

Spins up the facilitator and a provider on real loopback ports, then drives the
full client flow (402 challenge → sign → settle → 200 + receipt) with
``x402_fetch``. This is the wire-level proof the protocol works.

Run with::

    python -m pytest x402/tests/test_e2e_live.py -v -s
"""

import os
import socket
import sys
import threading
import time

import pytest
import uvicorn

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from x402.client import x402_fetch
from x402.crypto import generate_account
from x402.facilitator import create_facilitator_app
from x402.ledger import LocalLedger, set_ledger
from x402.provider import create_provider_app


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _ServerThread(threading.Thread):
    def __init__(self, app, host: str, port: int):
        super().__init__(daemon=True)
        self.app = app
        self.host = host
        self.port = port
        self.config = uvicorn.Config(app, host=host, port=port, log_level="warning")
        self.server = uvicorn.Server(self.config)

    def run(self):
        self.server.run()

    def wait_until_ready(self, timeout=15.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with socket.create_connection((self.host, self.port), timeout=0.5):
                    return True
            except OSError:
                time.sleep(0.1)
        return False


@pytest.fixture(scope="module")
def live_stack():
    consumer = generate_account("consumer")
    provider = generate_account("provider")

    ledger = LocalLedger()
    ledger.deposit(consumer.public_account_hex, 1_000_000_000)  # 1 CSPR
    ledger.deposit(provider.public_account_hex, 0)
    set_ledger(ledger)

    fac_port, prov_port = _free_port(), _free_port()
    fac_url = f"http://127.0.0.1:{fac_port}"

    facilitator = create_facilitator_app()
    provider_app = create_provider_app(provider, facilitator_url=fac_url)

    @provider_app.paid_route("/risk-score", price_motes=50_000_000, service_id="risk-score-api", description="risk score")
    def risk_score(request):
        return {"service_id": "risk-score-api", "risk_score": 0.82, "label": "high"}

    fac_thread = _ServerThread(facilitator, "127.0.0.1", fac_port)
    prov_thread = _ServerThread(provider_app, "127.0.0.1", prov_port)
    fac_thread.start()
    prov_thread.start()
    assert fac_thread.wait_until_ready()
    assert prov_thread.wait_until_ready()

    yield {
        "consumer": consumer,
        "provider": provider,
        "provider_url": f"http://127.0.0.1:{prov_port}",
        "ledger": ledger,
    }


def test_full_x402_flow_live(live_stack):
    result = x402_fetch(f"{live_stack['provider_url']}/risk-score", live_stack["consumer"])
    assert result.status_code == 200
    assert result.data["service_id"] == "risk-score-api"
    assert result.data["risk_score"] == 0.82
    # Settlement receipt present
    assert result.settlement is not None
    assert result.settlement.success is True
    assert result.settlement.transaction.startswith("local-")
    # Ledger moved: consumer -0.05 CSPR, provider +0.05 CSPR
    ledger = live_stack["ledger"]
    assert ledger.balance_of(live_stack["consumer"].public_account_hex) == 950_000_000
    assert ledger.get_revenue(live_stack["provider"].public_account_hex) == 50_000_000


def test_second_call_records_second_payment(live_stack):
    # Another paid call → another settlement, revenue grows.
    x402_fetch(f"{live_stack['provider_url']}/risk-score", live_stack["consumer"])
    ledger = live_stack["ledger"]
    assert ledger.balance_of(live_stack["consumer"].public_account_hex) == 900_000_000
    assert ledger.get_revenue(live_stack["provider"].public_account_hex) == 100_000_000
    assert len(ledger.recent_payments(10)) >= 2
