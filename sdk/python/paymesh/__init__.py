"""PayMesh Python SDK.

A typed client for the x402 agent marketplace on Casper.

    from paymesh import PayMeshClient, generate_account

    acct = generate_account("alice")
    pm = PayMeshClient(account=acct)
"""

from .backends import (
    CasperContractBackend,
    ContractBackend,
    HttpContractBackend,
    LocalContractBackend,
)
from .client import PayMeshClient
from .models import (
    CallResult,
    ReputationAggregate,
    Review,
    ServiceInfo,
    StakeInfo,
    cspr_to_motes,
    motes_to_cspr,
)

# Re-export x402 account helpers so consumers only import `paymesh`.
from x402.crypto import (  # noqa: E402,F401
    Account,
    account_from_private_key,
    generate_account,
)

__all__ = [
    "PayMeshClient",
    "ContractBackend",
    "LocalContractBackend",
    "HttpContractBackend",
    "CasperContractBackend",
    "ServiceInfo",
    "StakeInfo",
    "ReputationAggregate",
    "Review",
    "CallResult",
    "generate_account",
    "account_from_private_key",
    "Account",
    "cspr_to_motes",
    "motes_to_cspr",
]

__version__ = "1.0.0"
