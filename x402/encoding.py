"""base64url helpers used by the x402 wire format."""

from __future__ import annotations

import base64


def b64url_encode(data: bytes) -> str:
    """base64url-encode without padding (the x402 convention)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    """Decode a base64url string, tolerating missing padding."""
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)
