"""TOTP tests using RFC 6238 test vectors (HMAC-SHA1, secret = "12345678901234567890")."""

import pytest
from src.pesc.totp import generate_totp, _base32_decode


# RFC 4648 base32 of b"12345678901234567890"
SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"

# (unix_seconds, expected_code) from RFC 6238 appendix B
RFC_VECTORS = [
    (59, "287082"),
    (1111111109, "081804"),
    (1111111111, "050471"),
    (1234567890, "005924"),
    (2000000000, "279037"),
]


@pytest.mark.parametrize("unix_s,expected", RFC_VECTORS)
def test_rfc_vectors(unix_s: int, expected: str) -> None:
    assert generate_totp(SECRET, unix_s * 1000) == expected


def test_output_is_six_digits() -> None:
    code = generate_totp(SECRET, 59_000)
    assert len(code) == 6
    assert code.isdigit()


def test_base32_decode_strips_spaces_and_dashes() -> None:
    clean = _base32_decode("GEZD GNBV-GY3T")
    noisy = _base32_decode("GEZDGNBVGY3T")
    assert clean == noisy


def test_base32_decode_empty_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        _base32_decode("   ")
