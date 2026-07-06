"""Casper Ed25519 key handling for x402 payment signatures.

A Casper *Ed25519* account public key is the single byte ``0x01`` followed by
the 32-byte raw Ed25519 public key, hex-encoded (66 hex chars). The PayMesh
``casper-exact`` x402 scheme signs a canonical authorization string with the
sender's Ed25519 private key; the facilitator verifies it against the ``from``
account.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.exceptions import InvalidSignature

ED25519_PREFIX = "01"  # Casper account-kind tag for Ed25519 keys.


@dataclass
class Account:
    """A Casper Ed25519 account, with its private key for signing."""

    private_key_hex: str
    public_account_hex: str  # "01" + 32-byte raw pubkey hex
    label: str = ""

    @property
    def public_key_hex(self) -> str:
        """Raw 32-byte public key hex (without the 0x01 tag)."""
        return self.public_account_hex[2:]


def generate_account(label: str = "") -> Account:
    """Create a fresh Ed25519 Casper account."""
    priv = Ed25519PrivateKey.generate()
    raw_pub = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    priv_hex = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    ).hex()
    return Account(
        private_key_hex=priv_hex,
        public_account_hex=ED25519_PREFIX + raw_pub.hex(),
        label=label,
    )


def account_from_private_key(private_key_hex: str, label: str = "") -> Account:
    """Reconstruct an :class:`Account` from a raw 64-byte private key hex."""
    priv = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex))
    raw_pub = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return Account(
        private_key_hex=private_key_hex,
        public_account_hex=ED25519_PREFIX + raw_pub.hex(),
        label=label,
    )


def canonical_authorization(
    sender: str, recipient: str, value: str, service_id: str, nonce: str
) -> str:
    """The exact string the sender signs."""
    return f"{sender}\n{recipient}\n{value}\n{service_id}\n{nonce}"


def sign_message(message: str, private_key_hex: str) -> str:
    """Sign ``message`` with a raw Ed25519 private key; return hex signature."""
    priv = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex))
    return priv.sign(message.encode("utf-8")).hex()


def verify_signature(
    message: str, signature_hex: str, public_account_hex: str
) -> bool:
    """Verify a signature against a Casper Ed25519 account (``01``-prefixed)."""
    try:
        raw_pub_hex = (
            public_account_hex[2:]
            if public_account_hex.startswith(ED25519_PREFIX)
            else public_account_hex
        )
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(raw_pub_hex))
        pub.verify(bytes.fromhex(signature_hex), message.encode("utf-8"))
        return True
    except (ValueError, InvalidSignature):
        return False


def new_nonce() -> str:
    """A fresh single-use nonce for replay protection."""
    return secrets.token_hex(16)
