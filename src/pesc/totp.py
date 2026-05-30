"""RFC 6238 TOTP — HMAC-SHA1, 30-second period, 6 digits."""

import base64
import hashlib
import hmac
import struct
import time


def generate_totp(secret_base32: str, now_ms: int | None = None) -> str:
    if now_ms is None:
        now_ms = int(time.time() * 1000)

    key = _base32_decode(secret_base32)
    counter = now_ms // 1000 // 30
    counter_bytes = struct.pack(">Q", counter)

    mac = hmac.new(key, counter_bytes, hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    truncated = (
        ((mac[offset] & 0x7F) << 24)
        | ((mac[offset + 1] & 0xFF) << 16)
        | ((mac[offset + 2] & 0xFF) << 8)
        | (mac[offset + 3] & 0xFF)
    )
    return str(truncated % 1_000_000).zfill(6)


def _base32_decode(secret: str) -> bytes:
    cleaned = secret.upper().replace(" ", "").replace("-", "")
    if not cleaned:
        raise ValueError("TOTP secret is empty after normalisation")
    padding = (8 - len(cleaned) % 8) % 8
    return base64.b32decode(cleaned + "=" * padding)
