"""End-to-end tests for the PayMesh x402 payment flow.

Run with::

    cd paymesh-casper
    python -m pytest x402/tests/test_x402.py -v
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from x402.client import _build_payload
from x402.crypto import (
    ED25519_PREFIX,
    canonical_authorization,
    generate_account,
    sign_message,
    verify_signature,
)
from x402.facilitator import create_facilitator_app
from x402.ledger import InsufficientBalance, LocalLedger, get_ledger, set_ledger
from x402.types import PaymentRequirements


def _seed_facilitator(consumer_hex: str, provider_hex: str, motes: int) -> LocalLedger:
    ledger = LocalLedger()
    ledger.deposit(consumer_hex, motes)
    ledger.deposit(provider_hex, 0)
    set_ledger(ledger)
    return ledger


def _make_reqs(provider_hex: str, amount="50000000") -> PaymentRequirements:
    return PaymentRequirements(
        scheme="exact",
        network="casper-testnet",
        x402_network="casper",
        asset="CSPR",
        maxAmountRequired=amount,
        resource="https://x/risk-score",
        description="risk score",
        pay_to=provider_hex,
        metadata={"service_id": "risk-score-api"},
    )


def test_crypto_sign_verify_roundtrip():
    acct = generate_account("alice")
    assert acct.public_account_hex.startswith(ED25519_PREFIX)
    assert len(acct.public_account_hex) == 66
    msg = canonical_authorization(acct.public_account_hex, "01" + "bb" * 32, "1000", "svc", "nonce1")
    sig = sign_message(msg, acct.private_key_hex)
    assert verify_signature(msg, sig, acct.public_account_hex) is True
    assert verify_signature(msg + "x", sig, acct.public_account_hex) is False
    other = generate_account("bob")
    assert verify_signature(msg, sig, other.public_account_hex) is False


def test_ledger_record_payment_moves_balance():
    ledger = LocalLedger()
    ledger.deposit("01aa", 1_000)
    ledger.deposit("01bb", 0)
    tx = ledger.record_payment("01aa", "01bb", "svc", 300, "sig")
    assert tx.startswith("local-")
    assert ledger.balance_of("01aa") == 700
    assert ledger.balance_of("01bb") == 300
    assert ledger.get_revenue("01bb") == 300
    hist = ledger.payment_history("svc")
    assert len(hist) == 1 and hist[0].amount_motes == 300
    assert ledger.recent_payments(5)[-1].amount_motes == 300


def test_ledger_insufficient_balance():
    ledger = LocalLedger()
    ledger.deposit("01aa", 100)
    try:
        ledger.record_payment("01aa", "01bb", "svc", 500, "sig")
        raise AssertionError("expected InsufficientBalance")
    except InsufficientBalance:
        pass


def test_facilitator_verify_and_settle_roundtrip():
    consumer = generate_account("consumer")
    provider = generate_account("provider")
    _seed_facilitator(consumer.public_account_hex, provider.public_account_hex, 1_000_000_000)

    reqs = _make_reqs(provider.public_account_hex)
    payload = _build_payload(consumer, reqs)
    client = TestClient(create_facilitator_app())

    r = client.post("/verify", json={"paymentPayload": payload.model_dump(by_alias=True), "paymentRequirements": reqs.model_dump()})
    assert r.status_code == 200
    assert r.json()["isVerified"] is True

    r = client.post("/settle", json={"paymentPayload": payload.model_dump(by_alias=True), "paymentRequirements": reqs.model_dump()})
    body = r.json()
    assert body["success"] is True
    assert body["payer"] == consumer.public_account_hex
    assert body["payee"] == provider.public_account_hex
    assert body["transaction"].startswith("local-")

    assert get_ledger().balance_of(consumer.public_account_hex) == 1_000_000_000 - 50_000_000
    assert get_ledger().get_revenue(provider.public_account_hex) == 50_000_000


def test_facilitator_rejects_bad_signature():
    consumer = generate_account("consumer")
    provider = generate_account("provider")
    _seed_facilitator(consumer.public_account_hex, provider.public_account_hex, 1_000_000_000)

    reqs = _make_reqs(provider.public_account_hex)
    payload = _build_payload(consumer, reqs)
    bad = payload.model_copy(update={"signature": "00" * 64})
    client = TestClient(create_facilitator_app())
    r = client.post("/settle", json={"paymentPayload": bad.model_dump(by_alias=True), "paymentRequirements": reqs.model_dump()})
    assert r.json()["success"] is False
    assert "signature" in r.json()["error"]


def test_facilitator_rejects_replay():
    consumer = generate_account("consumer")
    provider = generate_account("provider")
    _seed_facilitator(consumer.public_account_hex, provider.public_account_hex, 2_000_000_000)

    reqs = _make_reqs(provider.public_account_hex, amount="100000000")
    payload = _build_payload(consumer, reqs)
    client = TestClient(create_facilitator_app())
    r1 = client.post("/settle", json={"paymentPayload": payload.model_dump(by_alias=True), "paymentRequirements": reqs.model_dump()})
    assert r1.json()["success"] is True
    r2 = client.post("/settle", json={"paymentPayload": payload.model_dump(by_alias=True), "paymentRequirements": reqs.model_dump()})
    assert r2.json()["success"] is False
    assert "replay" in r2.json()["error"].lower()
