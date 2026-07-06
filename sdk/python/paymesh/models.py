"""Typed data models for the PayMesh SDK.

These mirror the on-chain contract structs (``ServiceInfo``, ``StakeInfo``,
``RatingAggregate``, ``Review``) so the SDK returns the same data shape whether
it talks to the real Casper contracts or the local in-process backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MOTES_PER_CSPR = 1_000_000_000


def motes_to_cspr(motes: int | float) -> float:
    return float(motes) / MOTES_PER_CSPR


def cspr_to_motes(cspr: float) -> int:
    return int(cspr * MOTES_PER_CSPR)


@dataclass
class ServiceInfo:
    """A marketplace service (mirrors on-chain ``ServiceInfo``)."""

    service_id: str
    provider: str
    name: str
    endpoint: str
    price_per_call_motes: int
    staking_amount_motes: int
    reputation_score: int = 0  # basis points of a star (0–50000)
    total_ratings: int = 0
    active: bool = True
    registered_at: int = 0

    @property
    def price_per_call_cspr(self) -> float:
        return motes_to_cspr(self.price_per_call_motes)

    @property
    def staking_amount_cspr(self) -> float:
        return motes_to_cspr(self.staking_amount_motes)

    @property
    def average_rating(self) -> float:
        """Average rating 0.0–5.0."""
        return self.reputation_score / 10_000 if self.total_ratings else 0.0

    def to_dict(self) -> dict:
        return {
            "service_id": self.service_id,
            "provider": self.provider,
            "name": self.name,
            "endpoint": self.endpoint,
            "price_per_call_motes": self.price_per_call_motes,
            "price_per_call_cspr": round(self.price_per_call_cspr, 6),
            "staking_amount_motes": self.staking_amount_motes,
            "staking_amount_cspr": round(self.staking_amount_cspr, 3),
            "reputation_score": self.reputation_score,
            "average_rating": round(self.average_rating, 2),
            "total_ratings": self.total_ratings,
            "active": self.active,
            "registered_at": self.registered_at,
        }


@dataclass
class StakeInfo:
    provider: str
    amount_motes: int
    staked_at: int
    unlock_at: int
    slashed_total_motes: int

    @property
    def amount_cspr(self) -> float:
        return motes_to_cspr(self.amount_motes)


@dataclass
class ReputationAggregate:
    total_score: int
    count: int
    average: int  # basis points of a star

    @property
    def average_rating(self) -> float:
        return self.average / 10_000 if self.count else 0.0


@dataclass
class Review:
    index: int
    service_id: str
    reviewer: str
    rating: int
    review: str
    timestamp: int


@dataclass
class CallResult:
    """The outcome of a paid service call."""

    service_id: str
    data: object
    amount_paid_motes: int
    settlement_id: str
    success: bool = True
