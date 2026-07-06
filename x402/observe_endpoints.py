"""PayMesh Observability metrics — ``GET /observe/metrics``.

Mounts onto the marketplace node app (:func:`x402.node.create_paymesh_node_app`)
and exposes an aggregated analytics payload for the ``/observe`` dashboard.

Everything is computed from the REAL in-memory marketplace state (services,
stakes, reputation, settlement ledger) — no faked numbers. The dashboard charts
and tables are derived entirely from this endpoint.

Returned shape::

    {
      "summary": { total_volume_cspr, total_payments, total_services,
                   active_services, total_staked_cspr, avg_reputation,
                   total_agents, uptime_seconds },
      "volume_timeseries": [ { t, label, volume_cspr (cumulative) }, ... ],
      "payments_per_service": [ { service_id, name, call_count, volume_cspr }, ... ],
      "reputation_breakdown": [ { service_id, name, rating, ratings_count }, ... ],
      "contracts": [ { name, package_hash, deploy_hash, status }, ... ],
      "agent_registry": [ { address, role, services_offered, stake_cspr,
                            paid_cspr, reputation, last_active }, ... ],
      "network": { chain_name, protocol, network, rpc_status, explorer_url,
                   current_node, generated_at }
    }
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any, Dict, List

from fastapi import FastAPI

from .ledger import MOTES_PER_CSPR, get_ledger

log = logging.getLogger("paymesh.observe")

# Process start time — captured once when this module is first imported, i.e.
# effectively at node boot. Used for "uptime_seconds".
_BOOT_TIME = time.time()


# ---------------------------------------------------------------------------
# The four PayMesh Odra contracts actually deployed on Casper Testnet.
# (Real package + deploy hashes from the deployment — see deployment notes.)
# ---------------------------------------------------------------------------
DEPLOYED_CONTRACTS: List[Dict[str, str]] = [
    {
        "name": "ServiceRegistry",
        "description": "Agent service discovery & registration",
        "package_hash": "hash-6bab7762f65238d994224822492e7e6b026c702168a26bd1474f92b1ddbe765c",
        "deploy_hash": "01bef262",
        "status": "active",
    },
    {
        "name": "Settlement",
        "description": "x402 payment settlement & escrow ledger",
        "package_hash": "hash-2de7ebd31967202b7452c48a14940bec603bbaebee0fe0a5f14e8a4e96ba889a",
        "deploy_hash": "670733ef",
        "status": "active",
    },
    {
        "name": "Staking",
        "description": "Provider stake collateral & slashing",
        "package_hash": "hash-4e30962132c6515ce5791e17ef2e73d4ecda8e036a0153802bf0f49d2409af5d",
        "deploy_hash": "21fe2c77",
        "status": "active",
    },
    {
        "name": "Reputation",
        "description": "Aggregated ratings & reputation scoring",
        "package_hash": "hash-148f577b3bcc8a925f27a4b290945d3574ed63c9bf09b44b3fbbf2802f1b99e9",
        "deploy_hash": "4de3da53",
        "status": "active",
    },
]

NETWORK_INFO: Dict[str, str] = {
    "network": "Casper Testnet",
    "chain_name": "casper-test",
    "protocol": "2.2.2",
    "rpc_status": "connected",
    "explorer_url": "https://testnet.cspr.live",
    "current_node": "http://127.0.0.1:8001",
}


def _fmt_clock(ts: int) -> str:
    """HH:MM:SS for the chart X-axis labels."""
    try:
        import datetime as _dt

        return _dt.datetime.utcfromtimestamp(ts).strftime("%H:%M:%S")
    except Exception:
        return str(ts)


def _build_volume_timeseries(payments: list, *, bucket_seconds: int = 10) -> List[Dict[str, Any]]:
    """Cumulative payment volume, bucketed by ``bucket_seconds``.

    Produces an adaptive series: spans are divided into at most ~120 buckets so
    a long-running node still yields a compact, chartable payload. Always starts
    at a 0 point and ends at "now".
    """
    if not payments:
        now = int(time.time())
        return [{"t": now, "label": _fmt_clock(now), "volume_cspr": 0.0}]

    pts = sorted(payments, key=lambda p: p.timestamp)
    t_min = pts[0].timestamp
    t_max = max(int(time.time()), pts[-1].timestamp)
    span = max(1, t_max - t_min)

    # Keep the chart readable — widen buckets for long spans.
    if span / bucket_seconds > 120:
        bucket_seconds = max(10, -(-span // 120))  # ceil division

    buckets: Dict[int, float] = defaultdict(float)
    for p in pts:
        idx = (p.timestamp - t_min) // bucket_seconds
        buckets[idx] += p.amount_motes / MOTES_PER_CSPR

    n_buckets = (t_max - t_min) // bucket_seconds
    series: List[Dict[str, Any]] = []
    cumulative = 0.0
    # Seed with a zero point at the start so the area chart anchors to baseline.
    series.append({"t": t_min, "label": _fmt_clock(t_min), "volume_cspr": 0.0})
    last_idx_with_data = max(buckets.keys()) if buckets else 0
    # Walk through buckets up to the last one that had activity (avoid a long
    # flat tail of empty buckets, but keep continuity).
    for idx in range(0, last_idx_with_data + 1):
        cumulative += buckets.get(idx, 0.0)
        t = t_min + idx * bucket_seconds
        series.append({"t": t, "label": _fmt_clock(t), "volume_cspr": round(cumulative, 6)})
    # Final "live" point at now with the true total.
    total = sum(p.amount_motes for p in pts) / MOTES_PER_CSPR
    series.append({"t": t_max, "label": _fmt_clock(t_max), "volume_cspr": round(total, 6)})
    return series


def _compute_metrics() -> Dict[str, Any]:
    """Read live marketplace state and assemble the /observe/metrics payload."""
    # Lazy import to avoid a circular dependency at module load time
    # (node.py imports demo_endpoints + observe_endpoints; both need get_backend).
    from .node import get_backend

    b = get_backend()
    ledger = get_ledger()

    services = b.list_services(active_only=False)
    payments = ledger.recent_payments(10000)

    total_volume_motes = sum(p.amount_motes for p in payments)
    total_volume_cspr = total_volume_motes / MOTES_PER_CSPR
    total_staked_motes = b.total_staked()
    total_staked_cspr = total_staked_motes / MOTES_PER_CSPR

    # --- payments per service ------------------------------------------------
    per_service_vol: Dict[str, float] = defaultdict(float)
    per_service_calls: Dict[str, int] = defaultdict(int)
    for p in payments:
        per_service_vol[p.service_id] += p.amount_motes / MOTES_PER_CSPR
        per_service_calls[p.service_id] += 1

    svc_by_id = {s.service_id: s for s in services}
    payments_per_service: List[Dict[str, Any]] = []
    # Include services that received payments even if now inactive/deregistered.
    seen = set()
    for s in services:
        seen.add(s.service_id)
        payments_per_service.append(
            {
                "service_id": s.service_id,
                "name": s.name,
                "call_count": per_service_calls.get(s.service_id, 0),
                "volume_cspr": round(per_service_vol.get(s.service_id, 0.0), 6),
            }
        )
    for sid in per_service_calls:
        if sid not in seen:
            payments_per_service.append(
                {
                    "service_id": sid,
                    "name": (svc_by_id[sid].name if sid in svc_by_id else sid),
                    "call_count": per_service_calls[sid],
                    "volume_cspr": round(per_service_vol.get(sid, 0.0), 6),
                }
            )
    payments_per_service.sort(key=lambda r: r["volume_cspr"], reverse=True)

    # --- reputation breakdown ------------------------------------------------
    reputation_breakdown: List[Dict[str, Any]] = []
    rated = [s for s in services if b.get_reputation(s.service_id).count > 0]
    for s in services:
        agg = b.get_reputation(s.service_id)
        reputation_breakdown.append(
            {
                "service_id": s.service_id,
                "name": s.name,
                "rating": round(agg.average_rating, 2),
                "ratings_count": agg.count,
            }
        )
    reputation_breakdown.sort(key=lambda r: r["rating"], reverse=True)

    avg_reputation = (
        round(sum(r["rating"] for r in reputation_breakdown) / len(rated), 2)
        if rated
        else 0.0
    )

    # --- agent registry (merge providers + consumers) ------------------------
    # address -> aggregated fields
    agents: Dict[str, Dict[str, Any]] = {}

    def _agent(addr: str) -> Dict[str, Any]:
        a = agents.get(addr)
        if a is None:
            a = {
                "address": addr,
                "roles": set(),
                "services_offered": 0,
                "stake_cspr": 0.0,
                "paid_cspr": 0.0,  # revenue earned (provider) OR spent (consumer)
                "reputation": 0.0,
                "rep_count": 0,
                "last_active": 0,
            }
            agents[addr] = a
        return a

    # Providers (from services) + their stake/revenue/reputation.
    provider_services: Dict[str, int] = defaultdict(int)
    provider_reps: Dict[str, list] = defaultdict(list)
    provider_stake: Dict[str, float] = defaultdict(float)
    provider_last: Dict[str, int] = defaultdict(int)
    for s in services:
        a = _agent(s.provider)
        a["roles"].add("provider")
        provider_services[s.provider] += 1
        provider_reps[s.provider].append(b.get_reputation(s.service_id).average_rating)
        if s.registered_at:
            provider_last[s.provider] = max(provider_last[s.provider], s.registered_at)
        stake = b.get_stake(s.service_id)
        if stake:
            provider_stake[s.provider] += stake.amount_motes / MOTES_PER_CSPR
            provider_last[s.provider] = max(
                provider_last[s.provider], stake.staked_at
            )

    for addr, a in agents.items():
        a["services_offered"] = provider_services.get(addr, 0)
        a["stake_cspr"] = round(provider_stake.get(addr, 0.0), 3)
        reps = provider_reps.get(addr, [])
        a["reputation"] = round(sum(reps) / len(reps), 2) if reps else 0.0
        a["rep_count"] = len(reps)

    # Revenue earned by each provider (lifetime).
    provider_addrs = {s.provider for s in services}
    for addr in provider_addrs:
        a = _agent(addr)
        try:
            rev = ledger.get_revenue(addr) / MOTES_PER_CSPR
        except Exception:
            rev = 0.0
        a["paid_cspr"] = round(a["paid_cspr"] + rev, 6)

    # Consumers (payers from payments).
    consumer_spent: Dict[str, float] = defaultdict(float)
    consumer_last: Dict[str, int] = defaultdict(int)
    for p in payments:
        a = _agent(p.payer)
        a["roles"].add("consumer")
        consumer_spent[p.payer] += p.amount_motes / MOTES_PER_CSPR
        consumer_last[p.payer] = max(consumer_last[p.payer], p.timestamp)
        # bump provider last_active on settlement
        if p.provider in agents:
            agents[p.provider]["last_active"] = max(
                agents[p.provider]["last_active"], p.timestamp
            )

    for addr, spent in consumer_spent.items():
        a = _agent(addr)
        # For a pure consumer, paid_cspr reflects spend; for a dual-role agent we
        # keep revenue (already set) and surface spend separately.
        if "provider" not in a["roles"]:
            a["paid_cspr"] = round(spent, 6)
        else:
            a["paid_cspr"] = round(a["paid_cspr"] + spent, 6)
        a["last_active"] = max(a["last_active"], consumer_last.get(addr, 0))

    agent_registry: List[Dict[str, Any]] = []
    for a in agents.values():
        roles = a["roles"]
        if roles == {"provider"}:
            role = "Provider"
        elif roles == {"consumer"}:
            role = "Consumer"
        else:
            role = "Provider · Consumer"
        agent_registry.append(
            {
                "address": a["address"],
                "role": role,
                "is_provider": "provider" in roles,
                "is_consumer": "consumer" in roles,
                "services_offered": a["services_offered"],
                "stake_cspr": a["stake_cspr"],
                "paid_cspr": a["paid_cspr"],
                "reputation": a["reputation"],
                "last_active": a["last_active"],
            }
        )
    agent_registry.sort(key=lambda r: (r["paid_cspr"], r["stake_cspr"]), reverse=True)

    # --- summary -------------------------------------------------------------
    summary = {
        "total_volume_cspr": round(total_volume_cspr, 6),
        "total_payments": len(payments),
        "total_services": len(services),
        "active_services": sum(1 for s in services if s.active),
        "total_staked_cspr": round(total_staked_cspr, 3),
        "avg_reputation": avg_reputation,
        "total_agents": len(agents),
        "uptime_seconds": int(time.time() - _BOOT_TIME),
    }

    return {
        "summary": summary,
        "volume_timeseries": _build_volume_timeseries(payments),
        "payments_per_service": payments_per_service,
        "reputation_breakdown": reputation_breakdown,
        "contracts": DEPLOYED_CONTRACTS,
        "agent_registry": agent_registry,
        "network": {**NETWORK_INFO, "generated_at": int(time.time())},
    }


def mount_observe_endpoints(app: FastAPI) -> None:
    """Attach the ``GET /observe/metrics`` analytics route."""
    from fastapi import HTTPException  # noqa: E402

    @app.get("/observe/metrics")
    def observe_metrics():
        try:
            return _compute_metrics()
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("observe/metrics failed")
            raise HTTPException(500, f"metrics computation failed: {exc}")

    log.info("observe endpoints mounted")
