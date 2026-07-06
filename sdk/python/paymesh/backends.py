"""Contract backends for the PayMesh SDK.

The SDK never talks to the chain directly; it goes through a
:class:`ContractBackend`. Two implementations ship:

- :class:`LocalContractBackend` — an in-process simulation that faithfully
  mirrors the semantics of the four on-chain Odra contracts (registry, staking,
  reputation, settlement). Powers the offline demo with **the same data shape**
  the chain produces.
- :class:`CasperContractBackend` — queries/mutates the real deployed contracts
  on Casper over JSON-RPC via :class:`sdk.python.paymesh.casper_client.CasperRpcClient`.

Both expose identical methods so the SDK works unchanged in either mode.
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from typing import Optional

from .models import (
    MOTES_PER_CSPR,
    ReputationAggregate,
    Review,
    ServiceInfo,
    StakeInfo,
)


class ContractBackend(ABC):
    """Abstract on-chain state access."""

    # --- ServiceRegistry ---
    @abstractmethod
    def register_service(
        self,
        provider: str,
        service_id: str,
        name: str,
        endpoint: str,
        price_per_call_motes: int,
        staking_amount_motes: int,
    ) -> None: ...

    @abstractmethod
    def deregister_service(self, provider: str, service_id: str) -> None: ...

    @abstractmethod
    def get_service(self, service_id: str) -> Optional[ServiceInfo]: ...

    @abstractmethod
    def list_services(self, active_only: bool = True) -> list[ServiceInfo]: ...

    # --- Staking ---
    @abstractmethod
    def stake(self, provider: str, service_id: str, amount_motes: int) -> None: ...

    @abstractmethod
    def get_stake(self, service_id: str) -> Optional[StakeInfo]: ...

    @abstractmethod
    def total_staked(self) -> int: ...

    # --- Reputation ---
    @abstractmethod
    def rate(
        self,
        reviewer: str,
        service_id: str,
        rating: int,
        review: str,
    ) -> None: ...

    @abstractmethod
    def get_reputation(self, service_id: str) -> ReputationAggregate: ...

    @abstractmethod
    def get_reviews(self, service_id: str) -> list[Review]: ...


class LocalContractBackend(ContractBackend):
    """In-process mirror of the four PayMesh contracts.

    Thread-safe. Mirrors the on-chain logic including the staking requirement:
    a service is only ``active`` once its declared ``staking_amount`` is met, and
    reputation is one-rating-per (reviewer, service).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._services: dict[str, ServiceInfo] = {}
        self._order: list[str] = []
        self._stakes: dict[str, StakeInfo] = {}
        self._aggregates: dict[str, ReputationAggregate] = {}
        self._reviews: list[Review] = []
        self._service_reviews: dict[str, list[int]] = {}
        self._rated: dict[tuple[str, str], int] = {}

    # ---- ServiceRegistry -------------------------------------------------
    def register_service(
        self,
        provider: str,
        service_id: str,
        name: str,
        endpoint: str,
        price_per_call_motes: int,
        staking_amount_motes: int,
    ) -> None:
        with self._lock:
            if not service_id or len(service_id) > 64:
                raise ValueError("invalid service_id")
            if service_id in self._services:
                raise ValueError(f"service {service_id!r} already registered")
            info = ServiceInfo(
                service_id=service_id,
                provider=provider,
                name=name,
                endpoint=endpoint,
                price_per_call_motes=price_per_call_motes,
                staking_amount_motes=staking_amount_motes,
                registered_at=int(time.time()),
                active=False,  # becomes active once staked
            )
            self._services[service_id] = info
            self._order.append(service_id)

    def deregister_service(self, provider: str, service_id: str) -> None:
        with self._lock:
            info = self._services.get(service_id)
            if info is None:
                raise KeyError(service_id)
            if info.provider != provider:
                raise PermissionError("not the provider")
            info.active = False

    def _refresh_active(self, service_id: str) -> None:
        info = self._services.get(service_id)
        stake = self._stakes.get(service_id)
        if info and stake and stake.amount_motes >= info.staking_amount_motes:
            info.active = True

    def get_service(self, service_id: str) -> Optional[ServiceInfo]:
        with self._lock:
            return self._services.get(service_id)

    def list_services(self, active_only: bool = True) -> list[ServiceInfo]:
        with self._lock:
            out = [self._services[sid] for sid in self._order if sid in self._services]
            return [s for s in out if (not active_only) or s.active]

    # ---- Staking ---------------------------------------------------------
    def stake(self, provider: str, service_id: str, amount_motes: int) -> None:
        with self._lock:
            if amount_motes <= 0:
                raise ValueError("must stake > 0")
            existing = self._stakes.get(service_id)
            if existing and existing.provider != provider:
                raise PermissionError("not the original staker")
            self._stakes[service_id] = StakeInfo(
                provider=provider,
                amount_motes=(existing.amount_motes if existing else 0) + amount_motes,
                staked_at=existing.staked_at if existing else int(time.time()),
                unlock_at=0,
                slashed_total_motes=existing.slashed_total_motes if existing else 0,
            )
            self._refresh_active(service_id)

    def get_stake(self, service_id: str) -> Optional[StakeInfo]:
        with self._lock:
            return self._stakes.get(service_id)

    def total_staked(self) -> int:
        with self._lock:
            return sum(s.amount_motes for s in self._stakes.values())

    # ---- Reputation ------------------------------------------------------
    def rate(self, reviewer: str, service_id: str, rating: int, review: str) -> None:
        with self._lock:
            if not 1 <= rating <= 5:
                raise ValueError("rating must be 1..5")
            if not service_id or service_id not in self._services:
                raise KeyError(service_id)
            if len(review) > 512:
                raise ValueError("review too long")
            now = int(time.time())
            key = (reviewer, service_id)
            agg = self._aggregates.get(
                service_id, ReputationAggregate(total_score=0, count=0, average=0)
            )
            prev_index = self._rated.get(key)
            if prev_index is not None:
                prev = self._reviews[prev_index]
                agg.total_score = agg.total_score - prev.rating + rating
                self._reviews[prev_index] = Review(
                    prev_index, service_id, reviewer, rating, review, now
                )
            else:
                index = len(self._reviews)
                agg.total_score += rating
                agg.count += 1
                self._reviews.append(
                    Review(index, service_id, reviewer, rating, review, now)
                )
                self._service_reviews.setdefault(service_id, []).append(index)
                self._rated[key] = index
            agg.average = int(agg.total_score * 10_000 / agg.count) if agg.count else 0
            self._aggregates[service_id] = agg
            # sync the denormalised snapshot on the registry record
            info = self._services.get(service_id)
            if info:
                info.reputation_score = agg.average
                info.total_ratings = agg.count

    def get_reputation(self, service_id: str) -> ReputationAggregate:
        with self._lock:
            return self._aggregates.get(
                service_id, ReputationAggregate(total_score=0, count=0, average=0)
            )

    def get_reviews(self, service_id: str) -> list[Review]:
        with self._lock:
            idxs = self._service_reviews.get(service_id, [])
            return [self._reviews[i] for i in idxs]


# ---------------------------------------------------------------------------
# Casper (real chain) backend — thin adapter over the RPC client.
# ---------------------------------------------------------------------------
class CasperContractBackend(ContractBackend):
    """Talks to the real deployed PayMesh contracts over Casper JSON-RPC.

    Construct with the four contract package hashes and a funded account. Read
    methods issue ``query``/``state_get_dictionary`` calls; write methods submit
    signed deploys.
    """

    def __init__(
        self,
        rpc_url: str,
        chain_name: str,
        registry_hash: str,
        staking_hash: str,
        settlement_hash: str,
        reputation_hash: str,
        signer_private_key_hex: Optional[str] = None,
    ) -> None:
        from .casper_client import CasperRpcClient

        self.client = CasperRpcClient(rpc_url, chain_name)
        self.registry_hash = registry_hash
        self.staking_hash = staking_hash
        self.settlement_hash = settlement_hash
        self.reputation_hash = reputation_hash
        self.signer_private_key_hex = signer_private_key_hex

    def _signer_or_raise(self):
        if not self.signer_private_key_hex:
            raise RuntimeError("this call requires a signer private key")
        return self.signer_private_key_hex

    # ---- registry ----
    def register_service(
        self, provider, service_id, name, endpoint, price_per_call_motes, staking_amount_motes
    ) -> None:
        self.client.put_deploy(
            self.registry_hash,
            "register_service",
            {
                "service_id": service_id,
                "name": name,
                "endpoint": endpoint,
                "price_per_call": str(price_per_call_motes),
                "staking_amount": str(staking_amount_motes),
            },
            self._signer_or_raise(),
        )

    def deregister_service(self, provider, service_id) -> None:
        self.client.put_deploy(
            self.registry_hash, "deregister_service", {"service_id": service_id}, self._signer_or_raise()
        )

    def get_service(self, service_id: str) -> Optional[ServiceInfo]:
        raw = self.client.call_entrypoint(self.registry_hash, "maybe_get_service", {"service_id": service_id})
        return _decode_service(raw) if raw else None

    def list_services(self, active_only: bool = True) -> list[ServiceInfo]:
        raw = self.client.call_entrypoint(self.registry_hash, "list_services", {})
        services = [_decode_service(r) for r in (raw or [])]
        return [s for s in services if (not active_only) or s.active]

    # ---- staking ----
    def stake(self, provider, service_id, amount_motes) -> None:
        self.client.put_deploy(
            self.staking_hash,
            "stake",
            {"service_id": service_id},
            self._signer_or_raise(),
            payment_motes=amount_motes,
        )

    def get_stake(self, service_id: str) -> Optional[StakeInfo]:
        raw = self.client.query_dictionary(self.staking_hash, "stakes", service_id)
        return _decode_stake(raw) if raw else None

    def total_staked(self) -> int:
        raw = self.client.query_named_key(self.staking_hash, "total_staked")
        return int(raw) if raw else 0

    # ---- reputation ----
    def rate(self, reviewer, service_id, rating, review) -> None:
        self.client.put_deploy(
            self.reputation_hash,
            "update_reputation",
            {"service_id": service_id, "rating": str(rating), "review": review},
            self._signer_or_raise(),
        )

    def get_reputation(self, service_id: str) -> ReputationAggregate:
        raw = self.client.query_dictionary(self.reputation_hash, "aggregates", service_id)
        if not raw:
            return ReputationAggregate(0, 0, 0)
        return ReputationAggregate(
            int(raw.get("total_score", 0)),
            int(raw.get("count", 0)),
            int(raw.get("average", 0)),
        )

    def get_reviews(self, service_id: str) -> list[Review]:
        raw = self.client.call_entrypoint(self.reputation_hash, "get_reviews", {"service_id": service_id})
        out = []
        for r in raw or []:
            out.append(
                Review(
                    int(r.get("index", 0)),
                    r.get("service_id", service_id),
                    r.get("reviewer", ""),
                    int(r.get("rating", 0)),
                    r.get("review", ""),
                    int(r.get("timestamp", 0)),
                )
            )
        return out


def _decode_service(raw: dict) -> ServiceInfo:
    def _pick(*names, default=0):
        for n in names:
            if n in raw and raw[n] not in (None, ""):
                return raw[n]
        return default

    return ServiceInfo(
        service_id=raw.get("service_id", ""),
        provider=raw.get("provider", ""),
        name=raw.get("name", ""),
        endpoint=raw.get("endpoint", ""),
        price_per_call_motes=int(_pick("price_per_call_motes", "price_per_call")),
        staking_amount_motes=int(_pick("staking_amount_motes", "staking_amount")),
        reputation_score=int(_pick("reputation_score")),
        total_ratings=int(_pick("total_ratings")),
        active=bool(raw.get("active", True)),
        registered_at=int(_pick("registered_at")),
    )


def _decode_stake(raw: dict) -> StakeInfo:
    return StakeInfo(
        provider=raw.get("provider", ""),
        amount_motes=int(raw.get("amount", 0)),
        staked_at=int(raw.get("staked_at", 0)),
        unlock_at=int(raw.get("unlock_at", 0)),
        slashed_total_motes=int(raw.get("slashed_total", 0)),
    )


# ---------------------------------------------------------------------------
# HTTP backend — talks to a PayMesh marketplace node (facilitator + registry).
# ---------------------------------------------------------------------------
class HttpContractBackend(ContractBackend):
    """Talks to a running PayMesh node (``x402.node``) over HTTP.

    Lets the provider and consumer demo agents share registry/staking/reputation
    state across processes. Settlement still flows through the same node's
    facilitator.
    """

    def __init__(self, node_url: str, timeout: float = 15.0) -> None:
        import requests

        self._requests = requests
        self.node_url = node_url.rstrip("/")
        self.timeout = timeout

    # --- registry ---
    def register_service(
        self, provider, service_id, name, endpoint, price_per_call_motes, staking_amount_motes
    ) -> None:
        self._post("/registry/services", {
            "provider": provider,
            "service_id": service_id,
            "name": name,
            "endpoint": endpoint,
            "price_per_call_cspr": motes_to_cspr(price_per_call_motes),
            "staking_amount_cspr": motes_to_cspr(staking_amount_motes),
        })

    def deregister_service(self, provider, service_id) -> None:
        raise NotImplementedError("deregister not exposed via HTTP backend")

    def get_service(self, service_id: str):
        raw = self._get(f"/registry/services/{service_id}")
        return _decode_service(raw) if raw else None

    def list_services(self, active_only: bool = True) -> list[ServiceInfo]:
        raw = self._get("/registry/services", params={"active_only": str(active_only).lower()})
        return [_decode_service(s) for s in (raw or {}).get("services", [])]

    # --- staking ---
    def stake(self, provider, service_id, amount_motes) -> None:
        self._post(f"/registry/services/{service_id}/stake", {
            "provider": provider, "amount_cspr": motes_to_cspr(amount_motes)
        })

    def get_stake(self, service_id: str):
        raw = self._get(f"/registry/services/{service_id}")
        if not raw:
            return None
        return StakeInfo(
            provider=raw.get("provider", ""),
            amount_motes=int(raw.get("stake_amount_motes", 0)),
            staked_at=0, unlock_at=0, slashed_total_motes=0,
        )

    def total_staked(self) -> int:
        stats = self._get("/registry/stats")
        return cspr_to_motes((stats or {}).get("total_staked_cspr", 0.0))

    # --- reputation ---
    def rate(self, reviewer, service_id, rating, review) -> None:
        self._post(f"/registry/services/{service_id}/rate", {
            "reviewer": reviewer, "rating": rating, "review": review
        })

    def get_reputation(self, service_id: str) -> ReputationAggregate:
        raw = self._get(f"/registry/services/{service_id}/reputation") or {}
        return ReputationAggregate(
            total_score=int(raw.get("count", 0)) * 3,
            count=int(raw.get("count", 0)),
            average=int(raw.get("reputation_score", 0)),
        )

    def get_reviews(self, service_id: str) -> list[Review]:
        raw = self._get(f"/registry/services/{service_id}/reviews") or {}
        out = []
        for r in raw.get("reviews", []):
            out.append(Review(
                int(r.get("index", 0)), r.get("service_id", service_id),
                r.get("reviewer", ""), int(r.get("rating", 0)),
                r.get("review", ""), int(r.get("timestamp", 0)),
            ))
        return out

    # --- http helpers ---
    def _get(self, path, params=None):
        r = self._requests.get(f"{self.node_url}{path}", params=params, timeout=self.timeout)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def _post(self, path, body):
        r = self._requests.post(f"{self.node_url}{path}", json=body, timeout=self.timeout)
        if r.status_code >= 400:
            raise RuntimeError(f"{path} -> {r.status_code}: {r.text}")
        return r.json()


# re-import unit helpers used by HttpContractBackend
from .models import cspr_to_motes, motes_to_cspr  # noqa: E402
