"""Bounded content-body storage; section and content admission stay separate.

Version 0 is raw bytes. Version 1 uses codec byte 3 and the finite token grammar
in spec/body-codec-v1.md. Both admitted payload and decoded body are at most
16384 bytes. Diagnostic encode_lzss can return an unselected candidate of at
most 18435 bytes; encode_body selects it only when shorter than the raw body.
"""
from __future__ import annotations


BODY_MAX = 16_384
LZSS_CANDIDATE_MAX = 3 + BODY_MAX + (BODY_MAX + 7) // 8

__all__ = ("encode_body", "decode_body", "encode_lzss", "decode_lzss")


def _bounded_bytes(raw: bytes) -> None:
    if type(raw) is not bytes or len(raw) > BODY_MAX:
        raise ValueError("body_bytes")


def encode_lzss(raw: bytes) -> bytes:
    """Encode longest/nearest greedy tokens; candidate bound is 18435 bytes.

    Candidates larger than BODY_MAX are diagnostic only and decode_lzss rejects
    them. encode_body returns raw version 0 whenever compression does not win.
    """

    _bounded_bytes(raw)
    encoded = bytearray(b"\x03" + len(raw).to_bytes(2, "big"))
    cursor = 0
    while cursor < len(raw):
        flag_offset = len(encoded)
        encoded.append(0)
        for bit in range(7, -1, -1):
            if cursor == len(raw):
                break
            best_length, best_distance = 0, 0
            maximum = min(18, len(raw) - cursor)
            if maximum >= 3:
                prefix = raw[cursor:cursor + 3]
                first = max(0, cursor - 4096)
                # The two look-ahead bytes allow a prefix starting at cursor-1
                # to overlap. Every candidate start remains strictly earlier.
                candidate = raw.rfind(prefix, first, cursor + 2)
                while candidate >= first:
                    length = 3
                    while (
                        length < maximum
                        and raw[candidate + length] == raw[cursor + length]
                    ):
                        length += 1
                    if length > best_length:
                        best_length = length
                        best_distance = cursor - candidate
                    if best_length == maximum:
                        break
                    # Search nearest first, preserving the nearest equal match.
                    candidate = raw.rfind(prefix, first, candidate + 2)
            if best_length >= 3:
                encoded[flag_offset] |= 1 << bit
                token = ((best_distance - 1) << 4) | (best_length - 3)
                encoded.extend(token.to_bytes(2, "big"))
                cursor += best_length
            else:
                encoded.append(raw[cursor])
                cursor += 1
    return bytes(encoded)


def decode_lzss(payload: bytes) -> bytes:
    """Atomically decode any admitted tokenization, without recompression."""

    _bounded_bytes(payload)
    if len(payload) < 3 or payload[0] != 3:
        raise ValueError("codec_header")
    target = int.from_bytes(payload[1:3], "big")
    if target > BODY_MAX:
        raise ValueError("decoded_length")
    cursor = 3
    output = bytearray()
    while len(output) < target:
        if cursor == len(payload):
            raise ValueError("missing_flags")
        flags = payload[cursor]
        cursor += 1
        for bit in range(7, -1, -1):
            if flags & (1 << bit):
                if cursor + 2 > len(payload):
                    raise ValueError("truncated_copy")
                token = int.from_bytes(payload[cursor:cursor + 2], "big")
                distance, length = (token >> 4) + 1, (token & 15) + 3
                if distance > len(output) or len(output) + length > target:
                    raise ValueError("copy_bounds")
                cursor += 2
                for _ in range(length):
                    output.append(output[-distance])
            else:
                if cursor == len(payload) or len(output) + 1 > target:
                    raise ValueError("literal_bounds")
                output.append(payload[cursor])
                cursor += 1
            if len(output) == target:
                if flags & ((1 << bit) - 1):
                    raise ValueError("unused_flags")
                if cursor != len(payload):
                    raise ValueError("trailing_bytes")
                return bytes(output)
    if cursor != len(payload):
        raise ValueError("trailing_bytes")
    return bytes(output)


def encode_body(raw: bytes) -> tuple[int, bytes]:
    """Choose compression only when its complete payload is strictly smaller."""

    candidate = encode_lzss(raw)
    return (1, candidate) if len(candidate) < len(raw) else (0, raw)


def decode_body(version: int, payload: bytes) -> bytes:
    """Dispatch only by explicit checked section version, never payload magic."""

    if type(version) is not int or version not in (0, 1):
        raise ValueError("body_version")
    _bounded_bytes(payload)
    return payload if version == 0 else decode_lzss(payload)
