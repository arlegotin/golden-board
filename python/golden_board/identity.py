"""Identity-v0 framing and SHA-256."""

from __future__ import annotations

from collections.abc import Sequence
import hashlib


class IdentityError(ValueError):
    """Input is outside identity-v0."""


def u16_be(value: int) -> bytes:
    if type(value) is not int or not 0 <= value <= 0xFFFF:
        raise IdentityError("u16 out of range")
    return value.to_bytes(2, "big")


def u32_be(value: int) -> bytes:
    if type(value) is not int or not 0 <= value <= 0xFFFF_FFFF:
        raise IdentityError("u32 out of range")
    return value.to_bytes(4, "big")


def _check_domain(domain: bytes) -> None:
    if type(domain) is not bytes:
        raise IdentityError("domain must be bytes")
    if not domain.endswith(b"\0") or b"\0" in domain[:-1]:
        raise IdentityError("domain must end in one NUL")
    try:
        domain[:-1].decode("ascii")
    except UnicodeDecodeError as error:
        raise IdentityError("domain must be ASCII") from error


def frame_preimage(domain: bytes, fields: Sequence[bytes]) -> bytes:
    _check_domain(domain)
    if isinstance(fields, (bytes, bytearray, str)):
        raise IdentityError("fields must be a sequence of bytes")
    try:
        count = len(fields)
    except TypeError as error:
        raise IdentityError("fields must have a bounded count") from error
    output = bytearray(domain)
    output.extend(u16_be(count))
    for field in fields:
        if type(field) is not bytes:
            raise IdentityError("field must be bytes")
        output.extend(u32_be(len(field)))
        output.extend(field)
    return bytes(output)


def identity_hex(domain: bytes, fields: Sequence[bytes]) -> str:
    return hashlib.sha256(frame_preimage(domain, fields)).hexdigest()
