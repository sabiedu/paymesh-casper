"""PayMesh x402 client handler.

Wraps ``requests`` so that any ``402 Payment Required`` response is handled
automatically: the client reads the ``PaymentRequirements``, builds and signs a
``PaymentPayload`` with its Casper Ed25519 key, and retries the request with an
``X-PAYMENT`` header. On success it returns the resource plus the settlement
receipt from ``X-PAYMENT-RESPONSE``.

This is the single function the SDK and demo consumer agent use to call a paid
service.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import requests

from .crypto import Account, canonical_authorization, new_nonce, sign_message
from .encoding import b64url_decode, b64url_encode
from .types import PaymentPayload, PaymentRequiredError, PaymentRequirements, SettleResponse

log = logging.getLogger("paymesh.x402.client")

X_PAYMENT_HEADER = "x-payment"
X_PAYMENT_RESPONSE_HEADER = "x-payment-response"


class PaymentError(RuntimeError):
    """Raised when a paid resource cannot be obtained."""


@dataclass
class PaidResponse:
    """The result of a paid call: the resource body + settlement receipt."""

    status_code: int
    data: object
    settlement: Optional[SettleResponse] = None
    requirements: Optional[PaymentRequirements] = None


def x402_fetch(
    url: str,
    account: Account,
    *,
    method: str = "GET",
    json_body: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: float = 15.0,
    max_retries: int = 1,
) -> PaidResponse:
    """Call ``url``, transparently paying via x402 if a ``402`` is returned."""
    headers = dict(headers or {})
    resp = requests.request(method, url, json=json_body, headers=headers, timeout=timeout)

    if resp.status_code != 402:
        return _decode_ok(resp)

    attempts = 0
    while resp.status_code == 402 and attempts <= max_retries:
        challenge = _parse_challenge(resp)
        if challenge is None:
            raise PaymentError("server returned 402 but no usable payment requirements")

        reqs = challenge.accepts[0]
        payload = _build_payload(account, reqs)
        headers[X_PAYMENT_HEADER] = b64url_encode(
            payload.model_dump_json(by_alias=True).encode("utf-8")
        )
        log.info(
            "paying %s motes to %s… for %s",
            reqs.maxAmountRequired,
            reqs.pay_to[:12],
            url,
        )
        resp = requests.request(
            method, url, json=json_body, headers=headers, timeout=timeout
        )
        attempts += 1

    if resp.status_code == 402:
        challenge = _parse_challenge(resp)
        msg = challenge.error if challenge else "payment rejected"
        raise PaymentError(f"payment rejected after {attempts} attempt(s): {msg}")

    return _decode_ok(resp)


def _parse_challenge(resp: requests.Response) -> Optional[PaymentRequiredError]:
    try:
        body = resp.json()
    except ValueError:
        return None
    try:
        ch = PaymentRequiredError.model_validate(body)
    except Exception:
        return None
    if not ch.accepts:
        return None
    return ch


def _build_payload(account: Account, reqs: PaymentRequirements) -> PaymentPayload:
    from .types import PaymentPayloadInner

    sender = account.public_account_hex
    recipient = reqs.pay_to
    value = reqs.maxAmountRequired
    service_id = reqs.metadata.get("service_id", "")
    nonce = new_nonce()
    auth = canonical_authorization(sender, recipient, value, service_id, nonce)
    sig = sign_message(auth, account.private_key_hex)
    inner = PaymentPayloadInner(
        **{
            "from": sender,
            "to": recipient,
            "value": value,
            "service_id": service_id,
            "nonce": nonce,
            "authorization": auth,
        }
    )
    return PaymentPayload(
        x402_version=1,
        scheme=reqs.scheme,
        network=reqs.network,
        payload=inner,
        signature=sig,
    )


def _decode_ok(resp: requests.Response) -> PaidResponse:
    try:
        data = resp.json()
    except ValueError:
        data = resp.text
    settlement = None
    receipt = resp.headers.get(X_PAYMENT_RESPONSE_HEADER)
    if receipt:
        try:
            settlement = SettleResponse.model_validate_json(
                b64url_decode(receipt)
            )
        except Exception:
            settlement = None
    return PaidResponse(
        status_code=resp.status_code, data=data, settlement=settlement
    )
