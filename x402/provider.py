"""PayMesh x402 provider middleware.

A resource server that charges per call. When a request arrives without payment
it responds ``402 Payment Required`` with a ``PaymentRequiredError`` body; when
the ``X-PAYMENT`` header carries a valid ``PaymentPayload`` it settles via the
facilitator and returns ``200`` with the resource plus an
``X-PAYMENT-RESPONSE`` settlement receipt.

Usage::

    app = create_provider_app(service_registry={...}, facilitator_url=...)
    @app.paid_route("/risk-score", price_motes=50_000_000, service_id="risk-score-api")
    def risk_score(req):
        return {"score": 0.87}

Run standalone::

    python -m x402.provider --port 8002
"""

from __future__ import annotations

import json
import logging
import time
from typing import Callable, Optional

import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .crypto import Account
from .encoding import b64url_decode, b64url_encode
from .ledger import get_ledger
from .types import (
    PaymentPayload,
    PaymentRequiredError,
    PaymentRequirements,
    SettleResponse,
)

log = logging.getLogger("paymesh.x402.provider")

X_PAYMENT_HEADER = "x-payment"
X_PAYMENT_RESPONSE_HEADER = "x-payment-response"
WWW_AUTHENTICATE = "www-authenticate"


class PaidRoute:
    __slots__ = ("path", "price_motes", "service_id", "description", "handler", "network")

    def __init__(
        self,
        path: str,
        price_motes: int,
        service_id: str,
        description: str,
        handler: Callable[[Request], object],
        network: str,
    ) -> None:
        self.path = path
        self.price_motes = price_motes
        self.service_id = service_id
        self.description = description
        self.handler = handler
        self.network = network


def create_provider_app(
    provider_account: Account,
    facilitator_url: str = "http://127.0.0.1:8001",
    network: str = "casper-testnet",
    base_url: str = "http://127.0.0.1:8002",
) -> FastAPI:
    """Create a FastAPI app that can host paid (x402) routes.

    Paid routes are registered via ``app.paid_route(...)`` (attached below) and
    are mounted dynamically.
    """
    app = FastAPI(title="PayMesh x402 Provider", version="1.0.0")
    app.state.paid_routes: dict[str, PaidRoute] = {}
    app.state.provider_account = provider_account
    app.state.facilitator_url = facilitator_url.rstrip("/")

    def paid_route(
        path: str,
        *,
        price_motes: int,
        service_id: str,
        description: str = "",
    ):
        def decorator(func: Callable[[Request], object]):
            route = PaidRoute(
                path=path,
                price_motes=price_motes,
                service_id=service_id,
                description=description or service_id,
                handler=func,
                network=network,
            )
            app.state.paid_routes[path] = route

            async def endpoint(request: Request):
                return await _handle_paid_request(request, route, app)

            app.add_api_route(path, endpoint, methods=["GET", "POST"])
            log.info("mounted paid route %s (%s motes)", path, price_motes)
            return func

        return decorator

    app.paid_route = paid_route  # type: ignore[attr-defined]

    @app.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "service": "paymesh-x402-provider",
            "provider": provider_account.public_account_hex,
            "paid_routes": [
                {
                    "path": r.path,
                    "price_motes": r.price_motes,
                    "service_id": r.service_id,
                }
                for r in app.state.paid_routes.values()
            ],
        }

    return app


def _requirements_for(route: PaidRoute, base_url: str, provider_hex: str) -> PaymentRequirements:
    return PaymentRequirements(
        scheme="exact",
        network=route.network,
        x402_network="casper",
        asset="CSPR",
        maxAmountRequired=str(route.price_motes),
        resource=f"{base_url}{route.path}",
        description=route.description,
        pay_to=provider_hex,
        created=int(time.time()),
        expires=int(time.time()) + 3600,
        metadata={"service_id": route.service_id},
    )


async def _handle_paid_request(
    request: Request, route: PaidRoute, app: FastAPI
) -> JSONResponse:
    provider_hex = app.state.provider_account.public_account_hex
    base_url = str(request.base_url).rstrip("/")
    reqs = _requirements_for(route, base_url, provider_hex)

    payment_header = request.headers.get(X_PAYMENT_HEADER)
    if not payment_header:
        # No payment → 402 challenge.
        return _payment_required(reqs)

    try:
        payload = PaymentPayload.model_validate_json(b64url_decode(payment_header))
    except Exception as exc:  # malformed header
        log.warning("malformed X-PAYMENT header: %s", exc)
        return _payment_required(reqs, error=f"malformed payment header: {exc}")

    # Ask the facilitator to verify + settle.
    settle = _settle_via_facilitator(
        app.state.facilitator_url, payload, reqs
    )
    if not settle or not settle.success:
        return _payment_required(
            reqs, error=(settle.error if settle else "facilitator unreachable")
        )

    # Paid — serve the resource.
    try:
        body = route.handler(request)
    except Exception as exc:  # pragma: no cover - provider bug
        log.exception("provider handler raised")
        return JSONResponse({"error": str(exc)}, status_code=500)

    receipt = b64url_encode(settle.model_dump_json().encode("utf-8"))
    return JSONResponse(
        _as_jsonable(body),
        headers={X_PAYMENT_RESPONSE_HEADER: receipt},
        status_code=200,
    )


def _as_jsonable(body):
    # FastAPI's JSONResponse already JSON-encodes; accept dicts/lists/primitives.
    return body


def _payment_required(reqs: PaymentRequirements, error: Optional[str] = None) -> JSONResponse:
    body = PaymentRequiredError(
        error=error or "Payment required",
        accepts=[reqs],
    )
    return JSONResponse(
        body.model_dump(),
        status_code=402,
        headers={WWW_AUTHENTICATE: "x402"},
    )


def _settle_via_facilitator(
    facilitator_url: str, payload: PaymentPayload, reqs: PaymentRequirements
) -> Optional[SettleResponse]:
    try:
        resp = requests.post(
            f"{facilitator_url}/settle",
            json={
                "paymentPayload": payload.model_dump(by_alias=True),
                "paymentRequirements": reqs.model_dump(),
            },
            timeout=10,
        )
        if resp.status_code != 200:
            log.error("facilitator /settle status %s: %s", resp.status_code, resp.text)
            return None
        return SettleResponse.model_validate(resp.json())
    except requests.RequestException as exc:
        log.error("facilitator unreachable: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Standalone runner for a demo provider (risk-score API).
# ---------------------------------------------------------------------------
def main() -> None:
    import argparse
    import random

    import uvicorn

    from .crypto import generate_account

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="PayMesh x402 demo provider")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--facilitator-url", default="http://127.0.0.1:8001")
    args = parser.parse_args()

    provider = generate_account(label="demo-provider")
    app = create_provider_app(provider, facilitator_url=args.facilitator_url)

    @app.paid_route("/risk-score", price_motes=50_000_000, service_id="risk-score-api", description="DeFi wallet risk score")
    def risk_score(request: Request):  # noqa: ARG001
        score = round(random.uniform(0.1, 0.95), 3)
        return {"service_id": "risk-score-api", "risk_score": score, "label": "high" if score > 0.7 else "moderate"}

    log.info("provider account: %s", provider.public_account_hex)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
