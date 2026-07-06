"""PayMesh Demo Console — the interactive demo engine.

Mounts onto the marketplace node app (:func:`x402.node.create_paymesh_node_app`)
so the dashboard can trigger the FULL agent marketplace lifecycle from buttons:

    register provider → stake → consumer pays via x402 → settle → rate

…with a live activity log that streams each step. Every action exercises the
REAL SDK code paths (``PayMeshClient``, ``generate_account``, ``x402_fetch``)
so the resulting transactions land in the existing ``/registry/stats`` and
``/recent_payments`` feeds the dashboard already polls.

Endpoints
---------
``POST /demo/register-provider``
    Generate a provider agent identity, register + stake a random service from
    the preset catalog, and mount a callable x402 paid route for it.
``POST /demo/consumer-call``
    Generate/fund a consumer agent and make ONE real x402 paid call to a
    service (402 → pay → 200 → settle).
``POST /demo/run-full-flow``
    The one-click "wow" button — full lifecycle in a single call.
``GET  /demo/activity``
    Recent activity events (feeds the live console log in the UI).
``GET  /demo/catalog``
    The preset service catalog the demo picks from.
``GET | POST /serve/{service_id}``
    The x402 paid route that serves each demo service's payload.

The provider's paid route lives ON the node itself (no separate provider
process), so a freshly registered service is immediately callable.
"""

from __future__ import annotations

import hashlib
import logging
import random
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Callable, Deque, Dict, List, Optional

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .encoding import b64url_decode, b64url_encode
from .provider import _payment_required, _requirements_for, _settle_via_facilitator
from .types import PaymentPayload

log = logging.getLogger("paymesh.demo")

MOTES_PER_CSPR = 1_000_000_000

DEFAULT_NODE_BASE_URL = "http://127.0.0.1:8001"
DEFAULT_NETWORK = "casper-testnet"


# ---------------------------------------------------------------------------
# Preset service catalog — each entry knows how to generate a mock-ish payload.
# Payload realism is secondary; the x402 payment + settlement flow is the star.
# ---------------------------------------------------------------------------
@dataclass
class ServiceSpec:
    service_id: str
    name: str
    emoji: str
    tag: str
    price_cspr: float
    generator: Callable[[Request], dict]


def _rand_wallet() -> str:
    return "0x" + "".join(random.choice("0123456789abcdef") for _ in range(40))


def _wallet(request: Request) -> str:
    # Query params only — the sync /serve handler can't await request.json().
    # Matches the existing risk-score provider pattern; mock payload doesn't
    # depend on the exact wallet (the x402 flow is the point).
    w = request.query_params.get("wallet")
    if w:
        return w
    return _rand_wallet()


def _gen_sentiment(request: Request) -> dict:
    text = request.query_params.get("text") or _rand_wallet()
    h = int(hashlib.sha256((text + str(time.time())).encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    score = round(h, 3)
    label = "bullish" if score > 0.62 else "bearish" if score < 0.38 else "neutral"
    return {
        "service": "sentiment-analysis-api",
        "analyzed_text": text[:48],
        "sentiment": label,
        "score": score,
        "confidence": round(0.82 + random.uniform(0, 0.16), 3),
        "model": "paymesh-sentiment-v2",
    }


def _gen_price_oracle(request: Request) -> dict:
    symbol = request.query_params.get("symbol") or random.choice(["CSPR", "ETH", "BTC", "SOL", "USDC"])
    base = {"CSPR": 0.034, "ETH": 3120.4, "BTC": 61250.0, "SOL": 148.2, "USDC": 1.0}.get(symbol, 1.0)
    price = round(base * (1 + random.uniform(-0.04, 0.04)), 6)
    return {
        "service": "price-oracle-api",
        "symbol": symbol,
        "price_usd": price,
        "change_24h": f"{round(random.uniform(-7, 9), 2)}%",
        "source": "paymesh-oracle-aggregator",
        "timestamp": int(time.time()),
    }


def _gen_wallet_screening(request: Request) -> dict:
    w = _wallet(request)
    h = hashlib.sha256(w.encode()).hexdigest()
    score = round(0.05 + (int(h[:8], 16) / 0xFFFFFFFF) * 0.9, 3)
    label = "low" if score < 0.33 else "moderate" if score < 0.66 else "high"
    return {
        "service": "wallet-screening-api",
        "wallet": w,
        "risk_score": score,
        "label": label,
        "factors": {
            "tx_volume": round(int(h[8:12], 16) / 0xFFFF, 3),
            "counterparty_risk": round(int(h[12:16], 16) / 0xFFFF, 3),
            "age_days": int(h[16:24], 16) % 1000,
        },
        "model": "paymesh-risk-v1",
    }


def _gen_yield_optimizer(request: Request) -> dict:
    pool = random.choice(["CSPR/USDC", "ETH/USDC", "wCSPR/stCSPR", "BTC/ETH"])
    return {
        "service": "defi-yield-api",
        "pool": pool,
        "apy": round(random.uniform(4.2, 38.7), 2),
        "tvl_usd": round(random.uniform(1.2, 92.0) * 1_000_000, 0),
        "protocol": random.choice(["PayMesh", "Liquid", "CasperSwap"]),
        "recommendation": "allocate" if random.random() > 0.4 else "hold",
    }


def _gen_nft_valuation(request: Request) -> dict:
    collection = random.choice(["Casperlions", "Byte Birds", "CSPR Punks", "Hash Hounds"])
    floor = round(random.uniform(0.4, 12.5), 3)
    return {
        "service": "nft-valuation-api",
        "collection": collection,
        "floor_eth": floor,
        "estimated_value_eth": round(floor * random.uniform(0.9, 1.8), 3),
        "rarity_rank": random.randint(1, 9999),
        "model": "paymesh-nft-v1",
    }


CATALOG: List[ServiceSpec] = [
    ServiceSpec("sentiment-analysis-api", "AI Sentiment Analysis", "💬", "AI Model", 0.05, _gen_sentiment),
    ServiceSpec("price-oracle-api", "On-Chain Price Oracle", "📈", "Oracle", 0.05, _gen_price_oracle),
    ServiceSpec("wallet-screening-api", "Wallet Risk Screening", "🛡️", "Risk Engine", 0.05, _gen_wallet_screening),
    ServiceSpec("defi-yield-api", "DeFi Yield Optimizer", "🌾", "DeFi", 0.08, _gen_yield_optimizer),
    ServiceSpec("nft-valuation-api", "NFT Valuation Engine", "🖼️", "Valuation", 0.06, _gen_nft_valuation),
]


def _payload_summary(data: dict) -> str:
    """One-line human summary of a service payload, for the activity log."""
    sid = data.get("service", "")
    if "risk_score" in data:
        return f'Risk score: {data["risk_score"]} ({data.get("label", "")})'
    if "sentiment" in data:
        return f'Sentiment: {data["sentiment"]} (score {data.get("score")}, conf {data.get("confidence")})'
    if "price_usd" in data:
        return f'{data.get("symbol")} price: ${data["price_usd"]:,.4f} (24h {data.get("change_24h")})'
    if "apy" in data:
        return f'{data.get("pool")} APY: {data["apy"]}% — TVL ${data.get("tvl_usd"):,.0f}'
    if "floor_eth" in data:
        return f'{data.get("collection")} floor: {data["floor_eth"]} ETH (rank {data.get("rarity_rank")})'
    if sid:
        return f"Response received from {sid}"
    return ""


def _review_text(rating: int) -> str:
    return {
        5: "Lightning-fast x402 settlement. Exactly what PayMesh promises.",
        4: "Clean call, payment settled without friction.",
    }.get(rating, "Service worked as expected.")


# ---------------------------------------------------------------------------
# In-process demo state
# ---------------------------------------------------------------------------
@dataclass
class DemoService:
    service_id: str
    name: str
    emoji: str
    tag: str
    price_cspr: float
    generator: Callable[[Request], dict]
    provider_account: object  # x402.crypto.Account
    provider_hex: str
    price_motes: int
    stake_cspr: float
    network: str
    endpoint: str
    registered_at: int = field(default_factory=lambda: int(time.time()))


@dataclass
class ActivityEvent:
    id: int
    ts: float
    type: str  # provider | consumer | payment | settlement | rating | discover | system
    icon: str
    message: str
    run_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ts": self.ts,
            "type": self.type,
            "icon": self.icon,
            "message": self.message,
            "run_id": self.run_id,
        }


class DemoState:
    """Thread-safe demo console state: registered services + activity log."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.services: Dict[str, DemoService] = {}
        self._events: Deque[ActivityEvent] = deque(maxlen=300)
        self._next_id = 1
        self.node_base_url = DEFAULT_NODE_BASE_URL
        self.facilitator_url = DEFAULT_NODE_BASE_URL

    def log(self, type_: str, icon: str, message: str, run_id: Optional[str] = None) -> ActivityEvent:
        with self._lock:
            ev = ActivityEvent(id=self._next_id, ts=time.time(), type=type_, icon=icon, message=message, run_id=run_id)
            self._next_id += 1
            self._events.append(ev)
            return ev

    def activity_since(self, since_id: int = 0, limit: int = 200) -> List[ActivityEvent]:
        with self._lock:
            out = [e for e in self._events if e.id > since_id]
        return out[-limit:]

    def recent_activity(self, limit: int = 200) -> List[ActivityEvent]:
        with self._lock:
            return list(self._events)[-limit:]

    def register(self, svc: DemoService) -> None:
        with self._lock:
            self.services[svc.service_id] = svc

    def get(self, service_id: str) -> Optional[DemoService]:
        with self._lock:
            return self.services.get(service_id)


# Process-wide singleton (the node app is a single process).
_state = DemoState()


def get_demo_state() -> DemoState:
    return _state


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class ConsumerCallReq(BaseModel):
    service_id: str
    wallet: Optional[str] = None


# ---------------------------------------------------------------------------
# x402 paid route handler — mirrors x402.provider._handle_paid_request but is
# per-service so each demo service pays its OWN provider account.
# ---------------------------------------------------------------------------
def _serve_demo_route(service_id: str, request: Request) -> JSONResponse:
    # Registered as a SYNC route (see mount_demo_endpoints) so FastAPI runs it
    # in the threadpool. The handler performs a blocking facilitator /settle
    # HTTP call; keeping the node's event loop free is what lets the in-process
    # self-call succeed (provider route + facilitator share one loop in the demo
    # node — an async handler would deadlock on /settle).
    svc = _state.get(service_id)
    if svc is None:
        raise HTTPException(404, f"demo service {service_id!r} not found")

    provider_hex = svc.provider_hex
    base_url = str(request.base_url).rstrip("/")

    route_view = SimpleNamespace(
        path=f"/serve/{service_id}",
        price_motes=svc.price_motes,
        service_id=service_id,
        description=svc.name,
        network=svc.network,
    )
    reqs = _requirements_for(route_view, base_url, provider_hex)

    payment_header = request.headers.get("x-payment")
    if not payment_header:
        return _payment_required(reqs)  # 402 challenge

    try:
        payload = PaymentPayload.model_validate_json(b64url_decode(payment_header))
    except Exception as exc:
        return _payment_required(reqs, error=f"malformed payment header: {exc}")

    settle = _settle_via_facilitator(_state.facilitator_url, payload, reqs)
    if not settle or not settle.success:
        return _payment_required(reqs, error=(settle.error if settle else "facilitator unreachable"))

    try:
        body = svc.generator(request)
    except Exception as exc:  # pragma: no cover - generator bug
        log.exception("demo service generator raised")
        return JSONResponse({"error": str(exc)}, status_code=500)

    receipt = b64url_encode(settle.model_dump_json().encode("utf-8"))
    return JSONResponse(body, headers={"x-payment-response": receipt}, status_code=200)


# ---------------------------------------------------------------------------
# Core demo actions (shared by the HTTP endpoints + the full-flow runner)
# ---------------------------------------------------------------------------
def _new_run_id() -> str:
    return f"run-{int(time.time() * 1000)}-{random.randint(100, 999)}"


def _short(hex_addr: str, n: int = 8) -> str:
    return hex_addr[:n] + ("…" if len(hex_addr) > n else "")


def do_register_provider(run_id: Optional[str] = None) -> dict:
    """Generate a provider agent, register + stake a random catalog service."""
    from paymesh import HttpContractBackend, PayMeshClient, generate_account

    spec = random.choice(CATALOG)
    # Unique suffix per registration so judges can spin up many services.
    suffix = "".join(random.choice("0123456789abcdef") for _ in range(4))
    service_id = f"{spec.service_id}-{suffix}"

    run_id = run_id or _new_run_id()
    acct = generate_account(f"provider-{service_id}")
    _state.log("provider", "🤖", f"Provider agent generated: {_short(acct.public_account_hex, 12)}…", run_id)

    node_url = _state.node_base_url
    client = PayMeshClient(account=acct, backend=HttpContractBackend(node_url), facilitator_url=node_url)

    endpoint = f"{node_url}/serve/{service_id}"
    stake = round(random.uniform(3.0, 8.0), 2)
    client.register_service(service_id, spec.name, endpoint, spec.price_cspr, stake)
    _state.log("provider", "📋", f'Registered service: "{spec.name}" @ {spec.price_cspr:.2f} CSPR/call', run_id)

    client.stake(service_id, stake)
    _state.log("provider", "🔒", f"Staked {stake:.1f} CSPR — service is ACTIVE", run_id)

    demo_svc = DemoService(
        service_id=service_id,
        name=spec.name,
        emoji=spec.emoji,
        tag=spec.tag,
        price_cspr=spec.price_cspr,
        generator=spec.generator,
        provider_account=acct,
        provider_hex=acct.public_account_hex,
        price_motes=int(spec.price_cspr * MOTES_PER_CSPR),
        stake_cspr=stake,
        network=DEFAULT_NETWORK,
        endpoint=endpoint,
    )
    _state.register(demo_svc)

    return {
        "service_id": service_id,
        "name": spec.name,
        "emoji": spec.emoji,
        "tag": spec.tag,
        "price_cspr": spec.price_cspr,
        "stake_cspr": stake,
        "provider": acct.public_account_hex,
        "endpoint": endpoint,
        "run_id": run_id,
    }


def do_consumer_call(
    service_id: str,
    wallet: Optional[str] = None,
    run_id: Optional[str] = None,
    rate: bool = True,
) -> dict:
    """Generate/fund a consumer agent and make ONE real x402 paid call."""
    from paymesh import HttpContractBackend, PayMeshClient, generate_account

    run_id = run_id or _new_run_id()
    node_url = _state.node_base_url

    acct = generate_account(f"consumer-{service_id}")
    _state.log("consumer", "🛰️", f"Consumer agent generated: {_short(acct.public_account_hex, 12)}…", run_id)

    requests.post(
        f"{node_url}/registry/deposit",
        json={"account": acct.public_account_hex, "amount_cspr": 5.0},
        timeout=10,
    )

    client = PayMeshClient(account=acct, backend=HttpContractBackend(node_url), facilitator_url=node_url)

    services = client.discover_services()
    _state.log("discover", "🔍", f"Consumer discovered {len(services)} service(s) on the marketplace", run_id)

    svc = client.get_service(service_id)
    if svc is None or not svc.active:
        _state.log("system", "⚠️", f"Service {service_id!r} not active — call skipped", run_id)
        return {"service_id": service_id, "success": False, "error": "service not active"}

    wallet = wallet or _rand_wallet()
    price_cspr = svc.price_per_call_cspr
    _state.log("payment", "💸", f"HTTP 402 → paying {price_cspr:.2f} CSPR → 200 OK", run_id)

    result = client.call_service(service_id, wallet=wallet)
    if not result.success:
        _state.log("system", "⚠️", f"Payment failed for {service_id!r}", run_id)
        return {"service_id": service_id, "success": False}

    data = result.data if isinstance(result.data, dict) else {"data": result.data}
    _state.log("settlement", "✅", f"Settlement recorded: {result.settlement_id or 'local-tx'}", run_id)
    summary = _payload_summary(data)
    if summary:
        _state.log("consumer", "📊", summary, run_id)

    out: dict = {
        "service_id": service_id,
        "success": True,
        "amount_paid_cspr": round(result.amount_paid_motes / MOTES_PER_CSPR, 4),
        "settlement_id": result.settlement_id,
        "data": data,
        "wallet": wallet,
        "run_id": run_id,
    }

    if rate:
        rating = random.choice([5, 5, 5, 4])
        try:
            agg = client.rate_service(service_id, rating, _review_text(rating))
            _state.log("rating", "⭐", f"Rated {rating}/5 — reputation: {agg.average_rating:.2f} avg over {agg.count}", run_id)
            out["rating"] = rating
            out["reputation"] = round(agg.average_rating, 2)
            out["rating_count"] = agg.count
        except Exception as exc:  # pragma: no cover
            log.warning("rating failed: %s", exc)

    return out


def do_run_full_flow() -> dict:
    """One-click full lifecycle: register → stake → 3-4 paid calls → rate."""
    run_id = _new_run_id()
    _state.log("system", "🎬", "Full demo flow started — one-click marketplace lifecycle", run_id)

    prov = do_register_provider(run_id=run_id)
    service_id = prov["service_id"]
    time.sleep(0.4)

    n_calls = random.randint(3, 4)
    calls = []
    total = 0.0
    for i in range(n_calls):
        time.sleep(0.35)
        res = do_consumer_call(service_id, run_id=run_id, rate=(i == n_calls - 1))
        calls.append({
            "success": res.get("success", False),
            "amount_cspr": res.get("amount_paid_cspr", 0),
            "settlement_id": res.get("settlement_id"),
            "summary": _payload_summary(res.get("data", {})) if isinstance(res.get("data"), dict) else "",
        })
        total += res.get("amount_paid_cspr", 0)

    _state.log("system", "🏁", f"Full flow complete — {n_calls} calls, {total:.4f} CSPR settled via x402", run_id)

    return {
        "run_id": run_id,
        "service": prov,
        "calls": calls,
        "total_volume_cspr": round(total, 4),
        "events": [e.to_dict() for e in _state.activity_since(0) if e.run_id == run_id],
    }


# ---------------------------------------------------------------------------
# Mount onto the node app
# ---------------------------------------------------------------------------
def mount_demo_endpoints(
    app: FastAPI,
    *,
    node_base_url: str = DEFAULT_NODE_BASE_URL,
    facilitator_url: Optional[str] = None,
) -> None:
    """Attach all ``/demo/*`` routes + the ``/serve/{service_id}`` paid route."""
    _state.node_base_url = node_base_url.rstrip("/")
    _state.facilitator_url = (facilitator_url or node_base_url).rstrip("/")

    if not _state.recent_activity():
        _state.log("system", "🟢", "Demo Console ready — click a button to launch an agent", None)

    @app.api_route("/serve/{service_id}", methods=["GET", "POST"])
    def serve_paid_route(service_id: str, request: Request):
        return _serve_demo_route(service_id, request)

    @app.get("/demo/catalog")
    def demo_catalog():
        return {
            "services": [
                {"service_id": s.service_id, "name": s.name, "emoji": s.emoji, "tag": s.tag, "price_cspr": s.price_cspr}
                for s in CATALOG
            ]
        }

    @app.post("/demo/register-provider")
    def demo_register_provider():
        try:
            return do_register_provider()
        except Exception as exc:  # pragma: no cover
            log.exception("register-provider failed")
            _state.log("system", "⚠️", f"Register failed: {exc}", None)
            raise HTTPException(500, str(exc))

    @app.post("/demo/consumer-call")
    def demo_consumer_call(req: ConsumerCallReq):
        try:
            return do_consumer_call(req.service_id, wallet=req.wallet)
        except Exception as exc:  # pragma: no cover
            log.exception("consumer-call failed")
            _state.log("system", "⚠️", f"Consumer call failed: {exc}", None)
            raise HTTPException(500, str(exc))

    @app.post("/demo/run-full-flow")
    def demo_run_full_flow():
        try:
            return do_run_full_flow()
        except Exception as exc:  # pragma: no cover
            log.exception("run-full-flow failed")
            _state.log("system", "⚠️", f"Full flow failed: {exc}", None)
            raise HTTPException(500, str(exc))

    @app.get("/demo/activity")
    def demo_activity(since_id: int = 0, limit: int = 200):
        events = _state.activity_since(since_id=since_id, limit=limit) if since_id else _state.recent_activity(limit=limit)
        return {"events": [e.to_dict() for e in events]}

    log.info("demo console mounted: node=%s facilitator=%s", _state.node_base_url, _state.facilitator_url)
