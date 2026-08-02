from collections.abc import Sequence
import hashlib


class IdentityError(ValueError):
    """An identity prefix, count, or byte length is outside identity-v0."""


def _encode_u16(value: int) -> bytes:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 2**16:
        raise IdentityError("identity.length")
    return value.to_bytes(2, "big")


def _encode_u32(value: int) -> bytes:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 2**32:
        raise IdentityError("identity.length")
    return value.to_bytes(4, "big")


def validate_prefix(prefix: bytes) -> None:
    if not isinstance(prefix, bytes):
        raise IdentityError("identity.prefix")
    if not 2 <= len(prefix) <= 63 or prefix[-1:] != b"\x00":
        raise IdentityError("identity.prefix")
    body = prefix[:-1]
    if b"\x00" in body or any(byte < 0x20 or byte > 0x7E for byte in body):
        raise IdentityError("identity.prefix")


def scalar_preimage(prefix: bytes, payload: bytes) -> bytes:
    validate_prefix(prefix)
    if not isinstance(payload, bytes):
        raise IdentityError("identity.length")
    return prefix + _encode_u32(len(payload)) + payload


def list_preimage(prefix: bytes, items: Sequence[bytes]) -> bytes:
    validate_prefix(prefix)
    count = len(items)
    parts = [prefix, _encode_u16(count)]
    for item in items:
        if not isinstance(item, bytes):
            raise IdentityError("identity.length")
        parts.extend((_encode_u32(len(item)), item))
    return b"".join(parts)


def sha256_hex(preimage: bytes) -> str:
    if not isinstance(preimage, bytes):
        raise IdentityError("identity.length")
    return hashlib.sha256(preimage).hexdigest()
