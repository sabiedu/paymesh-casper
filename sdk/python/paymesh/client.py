"""PayMeshClient — the typed entry point for the PayMesh agent marketplace.

Usage::

    from paymesh import PayMeshClient, generate_account

    account = generate_account("alice")
    pm = PayMeshClient(account=account, facilitator_url="http://127.0.0.1:8001")
    pm.deposit(10.0)                       # fund escrow (CSPR)

    # provider side
    pm.register_service("risk-api", "Risk API", "http://127.0.0.1:8002/risk", 0.05, 5.0)
    pm.stake("risk-api", 5.0)

    # consumer side
    services = pm.discover_services()
    result = pm.call_service("risk-api")   # pays per-call via x402 automatically
    pm.rate_service("risk-api", 5, "fast & accurate")
    print(pm.get_reputation("risk-api"))
"""

from __future__ import annotations

import logging
from typing import Optional

from .backends import CasperContractBackend, ContractBackend, LocalContractBackend
from .models import (
    CallResult,
    ReputationAggregate,
    Review,
    ServiceInfo,
    cspr_to_motes,
    motes_to_cspr,
)

log = logging.getLogger("paymesh")


class PayMeshClient:
    """Typed client for the PayMesh marketplace.

    Parameters
    ----------
    account:
        The caller's Casper :class:`x402.crypto.Account` (for signing payments
        and identifying the provider/consumer on-chain).
    backend:
        :class:`ContractBackend` — defaults to an in-process
        :class:`LocalContractBackend` (offline demo). Pass a
        :class:`CasperContractBackend` for live Testnet.
    facilitator_url:
        URL of the PayMesh x402 facilitator. Used for settlement reads/writes.
    """

    def __init__(
        self,
        account,
        backend: Optional[ContractBackend] = None,
        facilitator_url: str = "http://127.0.0.1:8001",
    ) -> None:
        self.account = account
        self.backend = backend or LocalContractBackend()
        self.facilitator_url = facilitator_url.rstrip("/")

    # --- identity helpers --------------------------------------------------
    @property
    def address(self) -> str:
        return self.account.public_account_hex

    # --- escrow balance (settlement layer) --------------------------------
    def deposit(self, amount_cspr: float) -> None:
        """Fund the caller's escrow balance (CSPR) for paying per-call."""
        from x402.ledger import get_ledger

        get_ledger().deposit(self.address, cspr_to_motes(amount_cspr))
        log.info("deposited %s CSPR for %s…", amount_cspr, self.address[:12])

    def balance(self) -> float:
        from x402.ledger import get_ledger

        return motes_to_cspr(get_ledger().balance_of(self.address))

    def revenue(self) -> float:
        from x402.ledger import get_ledger

        return motes_to_cspr(get_ledger().get_revenue(self.address))

    # --- ServiceRegistry ---------------------------------------------------
    def register_service(
        self,
        service_id: str,
        name: str,
        endpoint: str,
        price_per_call: float,
        stake_amount: float,
    ) -> ServiceInfo:
        """Register a service. ``price_per_call`` and ``stake_amount`` in CSPR."""
        self.backend.register_service(
            provider=self.address,
            service_id=service_id,
            name=name,
            endpoint=endpoint,
            price_per_call_motes=cspr_to_motes(price_per_call),
            staking_amount_motes=cspr_to_motes(stake_amount),
        )
        log.info("registered service %s (%s CSPR/call)", service_id, price_per_call)
        return self.backend.get_service(service_id)  # type: ignore[return-value]

    def deregister_service(self, service_id: str) -> None:
        self.backend.deregister_service(self.address, service_id)

    def discover_services(self, category: Optional[str] = None, active_only: bool = True) -> list[ServiceInfo]:
        """List marketplace services. ``category`` filters by name substring."""
        services = self.backend.list_services(active_only=active_only)
        if category:
            services = [s for s in services if category.lower() in s.name.lower()]
        return services

    def get_service(self, service_id: str) -> Optional[ServiceInfo]:
        return self.backend.get_service(service_id)

    # --- Staking -----------------------------------------------------------
    def stake(self, service_id: str, amount_cspr: float) -> None:
        """Lock CSPR behind a service (activates it once the minimum is met)."""
        self.backend.stake(self.address, service_id, cspr_to_motes(amount_cspr))
        log.info("staked %s CSPR on %s", amount_cspr, service_id)

    def get_stake(self, service_id: str):
        return self.backend.get_stake(service_id)

    # --- x402 paid call ----------------------------------------------------
    def call_service(self, service_id: str, **kwargs) -> CallResult:
        """Call a paid service, transparently paying per-call via x402.

        Resolves the service endpoint from the registry, performs the x402
        handshake (402 → sign → settle), and returns the resource. The settled
        payment is recorded on the Settlement layer and (on-chain mode) on the
        Casper ``Settlement`` contract.
        """
        from x402.client import x402_fetch

        svc = self.backend.get_service(service_id)
        if svc is None:
            raise KeyError(f"unknown service {service_id!r}")
        if not svc.active:
            raise RuntimeError(f"service {service_id!r} is not active (stake it first)")

        result = x402_fetch(
            svc.endpoint,
            self.account,
            method="POST" if kwargs else "GET",
            json_body=kwargs or None,
        )
        settlement = result.settlement
        return CallResult(
            service_id=service_id,
            data=result.data,
            amount_paid_motes=svc.price_per_call_motes,
            settlement_id=settlement.transaction if settlement else "",
            success=bool(settlement and settlement.success),
        )

    # --- Reputation --------------------------------------------------------
    def rate_service(self, service_id: str, rating: int, review: str = "") -> ReputationAggregate:
        """Rate a service 1–5 after using it."""
        self.backend.rate(self.address, service_id, rating, review)
        agg = self.backend.get_reputation(service_id)
        log.info(
            "rated %s %d/5 (avg %.2f over %d)",
            service_id, rating, agg.average_rating, agg.count,
        )
        return agg

    def get_reputation(self, service_id: str) -> ReputationAggregate:
        return self.backend.get_reputation(service_id)

    def get_reviews(self, service_id: str) -> list[Review]:
        return self.backend.get_reviews(service_id)
