"""Pydantic models for the PayMesh x402 payment protocol.

These mirror the x402 standard message shapes (``PaymentRequirements``,
``PaymentPayload``) and add the PayMesh-specific ``casper-exact`` scheme, where
value is settled in native CSPR and attested on the Casper ``Settlement``
contract.
"""

from __future__ import annotations

import time
from typing import Optional

from pydantic import BaseModel, Field


class PaymentRequirements(BaseModel):
    """Describes what a resource server will accept as payment.

    Returned in the body of an HTTP ``402`` response under ``accepts``.
    """

    scheme: str = "exact"
    network: str = "casper-testnet"
    # PayMesh extension: marks this as a native-Casper settlement.
    x402_network: str = "casper"
    asset: str = "CSPR"
    # Motes, encoded as a string (values can exceed JSON's safe integer range).
    maxAmountRequired: str
    resource: str
    description: str = ""
    pay_to: str
    mimeType: str = "application/json"
    created: int = Field(default_factory=lambda: int(time.time()))
    expires: int = Field(default_factory=lambda: int(time.time()) + 3600)
    metadata: dict = Field(default_factory=dict)


class PaymentPayloadInner(BaseModel):
    """The signed authorization inside a PaymentPayload."""

    sender: str = Field(alias="from")
    recipient: str = Field(alias="to")
    value: str
    service_id: str
    nonce: str
    authorization: str

    model_config = {"populate_by_name": True}


class PaymentPayload(BaseModel):
    """What the client sends back in the ``X-PAYMENT`` header (base64url)."""

    x402_version: int = 1
    scheme: str = "exact"
    network: str = "casper-testnet"
    payload: PaymentPayloadInner
    signature: str


class VerifyResponse(BaseModel):
    """Facilitator ``/verify`` response."""

    isValid: bool = False
    isVerified: bool = False
    error: Optional[str] = None


class SettleResponse(BaseModel):
    """Facilitator ``/settle`` response — the settlement receipt.

    ``transaction`` is a Casper deploy hash (on-chain mode) or a ledger sequence
    id (local mode). It is echoed back to the client as the
    ``X-PAYMENT-RESPONSE`` settlement proof.
    """

    success: bool = False
    network: str = "casper-testnet"
    transaction: str = ""
    payer: str = ""
    payee: str = ""
    error: Optional[str] = None


class PaymentRequiredError(BaseModel):
    """Body of the ``402`` response."""

    x402_version: int = 1
    error: str = "Payment required"
    accepts: list[PaymentRequirements]
