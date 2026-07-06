"""PayMesh x402 — HTTP-native payments for the agent marketplace.

Public API::

    from x402 import x402_fetch, generate_account
    from x402 import create_facilitator_app, create_provider_app
"""

from .client import PaidResponse, PaymentError, x402_fetch
from .crypto import (
    Account,
    account_from_private_key,
    canonical_authorization,
    generate_account,
    sign_message,
    verify_signature,
)
from .facilitator import create_facilitator_app
from .ledger import LocalLedger, get_ledger, set_ledger
from .provider import create_provider_app
from .types import (
    PaymentPayload,
    PaymentRequiredError,
    PaymentRequirements,
    SettleResponse,
)

__all__ = [
    "x402_fetch",
    "PaidResponse",
    "PaymentError",
    "Account",
    "generate_account",
    "account_from_private_key",
    "canonical_authorization",
    "sign_message",
    "verify_signature",
    "create_facilitator_app",
    "create_provider_app",
    "LocalLedger",
    "get_ledger",
    "set_ledger",
    "PaymentPayload",
    "PaymentRequiredError",
    "PaymentRequirements",
    "SettleResponse",
]

__version__ = "1.0.0"
