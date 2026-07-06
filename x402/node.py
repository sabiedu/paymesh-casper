"""PayMesh node — a single process hosting the facilitator + marketplace state.

Combines the x402 :mod:`~x402.facilitator` with a REST API over a shared
:class:`~sdk.python.paymesh.backends.LocalContractBackend`, so the provider and
consumer demo agents (which run as separate processes) see the same registry,
staking, reputation and settlement state.

This is the offline-capable "local marketplace node" the demo runs against. For
live Testnet, the same agent code points at a :class:`~sdk.python.paymesh.backends.CasperContractBackend`.

Endpoints (in addition to the facilitator's /verify, /settle, /balances, …):

- ``POST /registry/services``      — register a service
- ``POST /registry/services/{id}/stake`` — stake CSPR
- ``GET  /registry/services``       — list (discover)
- ``GET  /registry/services/{id}``  — get one
- ``POST /registry/services/{id}/rate`` — rate 1–5
- ``GET  /registry/services/{id}/reputation``
- ``GET  /registry/services/{id}/reviews``
- ``GET  /registry/stats``          — marketplace stats for the dashboard

Run standalone::

    python -m x402.node --port 8001
"""

from __future__ import annotations

import argparse
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .facilitator import create_facilitator_app
from .ledger import LocalLedger, get_ledger, set_ledger

# Import via the sdk package path.
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdk", "python"))

from paymesh.backends import LocalContractBackend  # noqa: E402
from paymesh.models import cspr_to_motes, motes_to_cspr  # noqa: E402

log = logging.getLogger("paymesh.x402.node")

# Process-wide shared backends.
_ledger: Optional[LocalLedger] = None
_backend: Optional[LocalContractBackend] = None


def get_backend() -> LocalContractBackend:
    global _backend, _ledger
    if _backend is None:
        _ledger = LocalLedger()
        set_ledger(_ledger)
        _backend = LocalContractBackend()
    return _backend


class RegisterReq(BaseModel):
    provider: str
    service_id: str
    name: str
    endpoint: str
    price_per_call_cspr: float
    staking_amount_cspr: float


class StakeReq(BaseModel):
    provider: str
    amount_cspr: float


class RateReq(BaseModel):
    reviewer: str
    rating: int
    review: str = ""


class DepositReq(BaseModel):
    account: str
    amount_cspr: float


def create_paymesh_node_app() -> FastAPI:
    # Compose: facilitator (x402 verify/settle + ledger reads) + registry router.
    app = create_facilitator_app()
    app.title = "PayMesh Node"
    b = get_backend()

    @app.post("/registry/deposit")
    def deposit(req: DepositReq):
        get_ledger().deposit(req.account, cspr_to_motes(req.amount_cspr))
        return {"ok": True, "balance_cspr": motes_to_cspr(get_ledger().balance_of(req.account))}

    @app.post("/registry/services")
    def register(req: RegisterReq):
        b.register_service(
            provider=req.provider,
            service_id=req.service_id,
            name=req.name,
            endpoint=req.endpoint,
            price_per_call_motes=cspr_to_motes(req.price_per_call_cspr),
            staking_amount_motes=cspr_to_motes(req.staking_amount_cspr),
        )
        svc = b.get_service(req.service_id)
        return _svc_dict(svc)

    @app.post("/registry/services/{service_id}/stake")
    def stake(service_id: str, req: StakeReq):
        b.stake(req.provider, service_id, cspr_to_motes(req.amount_cspr))
        svc = b.get_service(service_id)
        return _svc_dict(svc)

    @app.get("/registry/services")
    def list_services(active_only: bool = True, category: Optional[str] = None):
        services = b.list_services(active_only=active_only)
        if category:
            services = [s for s in services if category.lower() in s.name.lower()]
        return {"services": [_svc_dict(s) for s in services]}

    @app.get("/registry/services/{service_id}")
    def get_service(service_id: str):
        svc = b.get_service(service_id)
        if svc is None:
            raise HTTPException(404, "service not found")
        return _svc_dict(svc)

    @app.post("/registry/services/{service_id}/rate")
    def rate(service_id: str, req: RateReq):
        b.rate(req.reviewer, service_id, req.rating, req.review)
        agg = b.get_reputation(service_id)
        return {"count": agg.count, "average_rating": agg.average_rating}

    @app.get("/registry/services/{service_id}/reputation")
    def reputation(service_id: str):
        agg = b.get_reputation(service_id)
        return {
            "count": agg.count,
            "average_rating": agg.average_rating,
            "reputation_score": agg.average,
        }

    @app.get("/registry/services/{service_id}/reviews")
    def reviews(service_id: str):
        rs = b.get_reviews(service_id)
        return {"reviews": [r.__dict__ for r in rs]}

    @app.get("/registry/stats")
    def registry_stats():
        services = b.list_services(active_only=False)
        staked = b.total_staked()
        ledger = get_ledger()
        recs = ledger.recent_payments(1000)
        return {
            "service_count": len(services),
            "active_services": sum(1 for s in services if s.active),
            "total_staked_cspr": round(motes_to_cspr(staked), 3),
            "total_payments": len(recs),
            "total_volume_cspr": round(motes_to_cspr(sum(p.amount_motes for p in recs)), 6),
            "services": [_svc_dict(s) for s in services],
        }

    return app


def _svc_dict(svc):
    if svc is None:
        return None
    stake = get_backend().get_stake(svc.service_id)
    stake_motes = stake.amount_motes if stake else 0
    return {
        **svc.to_dict(),
        "stake_amount_motes": stake_motes,
        "stake_amount_cspr": round(motes_to_cspr(stake_motes), 3),
    }


def main():
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="PayMesh marketplace node")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    get_backend()  # init
    uvicorn.run(create_paymesh_node_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
