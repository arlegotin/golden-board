"""Canonical-manifest v0 parser and serializer."""

from __future__ import annotations

import json
from typing import Any


MAX_BYTES = 1_048_576
MAX_DEPTH = 32
MAX_U64 = 18_446_744_073_709_551_615


class ManifestError(ValueError):
    """Input is invalid or noncanonical under manifest-v0."""


def _check_input_depth(text: str) -> None:
    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
        elif character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > MAX_DEPTH:
                raise ManifestError("nesting depth exceeds 32")
        elif character in "]}":
            depth -= 1


def _parse_integer(token: str) -> int:
    if token.startswith("-"):
        raise ManifestError("negative integer")
    value = int(token)
    if value > MAX_U64:
        raise ManifestError("integer exceeds u64")
    return value


def _reject_number(_token: str) -> Any:
    raise ManifestError("unsupported number")


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ManifestError("duplicate object key")
        value[key] = item
    return value


def _scalar_string(value: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(value):
        code = ord(value[index])
        if 0xD800 <= code <= 0xDBFF:
            if index + 1 >= len(value):
                raise ManifestError("unpaired surrogate")
            low = ord(value[index + 1])
            if not 0xDC00 <= low <= 0xDFFF:
                raise ManifestError("unpaired surrogate")
            output.append(chr(0x10000 + ((code - 0xD800) << 10) + low - 0xDC00))
            index += 2
            continue
        if 0xDC00 <= code <= 0xDFFF:
            raise ManifestError("unpaired surrogate")
        output.append(value[index])
        index += 1
    return "".join(output)


def _validate_value(value: Any, depth: int = 1) -> Any:
    if isinstance(value, dict):
        if depth > MAX_DEPTH:
            raise ManifestError("nesting depth exceeds 32")
        normalized: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = _scalar_string(raw_key)
            if not key or any(not 0x20 <= ord(character) <= 0x7E for character in key):
                raise ManifestError("object key outside printable ASCII")
            normalized[key] = _validate_value(item, depth + 1)
        return normalized
    if isinstance(value, list):
        if depth > MAX_DEPTH:
            raise ManifestError("nesting depth exceeds 32")
        return [_validate_value(item, depth + 1) for item in value]
    if isinstance(value, str):
        return _scalar_string(value)
    if type(value) is bool:
        return value
    if type(value) is int and 0 <= value <= MAX_U64:
        return value
    raise ManifestError("value outside manifest-v0")


def parse_manifest(data: bytes) -> dict[str, Any]:
    if type(data) is not bytes:
        raise ManifestError("manifest input must be bytes")
    if len(data) > MAX_BYTES:
        raise ManifestError("manifest input exceeds byte limit")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ManifestError("manifest is not UTF-8") from error
    _check_input_depth(text)
    try:
        value = json.loads(
            text,
            object_pairs_hook=_object,
            parse_int=_parse_integer,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except ManifestError:
        raise
    except (json.JSONDecodeError, UnicodeError) as error:
        raise ManifestError("invalid JSON") from error
    if not isinstance(value, dict):
        raise ManifestError("top-level value must be an object")
    return _validate_value(value)


class _Writer:
    def __init__(self) -> None:
        self.output = bytearray()

    def add(self, value: bytes) -> None:
        if len(self.output) + len(value) > MAX_BYTES:
            raise ManifestError("manifest output exceeds byte limit")
        self.output.extend(value)


def _write_string(writer: _Writer, value: str) -> None:
    writer.add(b'"')
    for character in _scalar_string(value):
        code = ord(character)
        if character == '"':
            writer.add(b'\\"')
        elif character == "\\":
            writer.add(b"\\\\")
        elif character == "\b":
            writer.add(b"\\b")
        elif character == "\t":
            writer.add(b"\\t")
        elif character == "\n":
            writer.add(b"\\n")
        elif character == "\f":
            writer.add(b"\\f")
        elif character == "\r":
            writer.add(b"\\r")
        elif code < 0x20:
            writer.add(f"\\u00{code:02x}".encode("ascii"))
        elif code == 0x7F:
            writer.add(b"\x7f")
        else:
            writer.add(character.encode("utf-8"))
    writer.add(b'"')


def _write_value(writer: _Writer, value: Any, depth: int) -> None:
    if isinstance(value, dict):
        if depth > MAX_DEPTH:
            raise ManifestError("nesting depth exceeds 32")
        writer.add(b"{")
        for index, key in enumerate(sorted(value)):
            if index:
                writer.add(b",")
            _write_string(writer, key)
            writer.add(b":")
            _write_value(writer, value[key], depth + 1)
        writer.add(b"}")
    elif isinstance(value, list):
        if depth > MAX_DEPTH:
            raise ManifestError("nesting depth exceeds 32")
        writer.add(b"[")
        for index, item in enumerate(value):
            if index:
                writer.add(b",")
            _write_value(writer, item, depth + 1)
        writer.add(b"]")
    elif isinstance(value, str):
        _write_string(writer, value)
    elif type(value) is bool:
        writer.add(b"true" if value else b"false")
    elif type(value) is int and 0 <= value <= MAX_U64:
        writer.add(str(value).encode("ascii"))
    else:
        raise ManifestError("value outside manifest-v0")


def serialize_manifest(value: Any) -> bytes:
    value = _validate_value(value)
    if not isinstance(value, dict):
        raise ManifestError("top-level value must be an object")
    writer = _Writer()
    _write_value(writer, value, 1)
    writer.add(b"\n")
    return bytes(writer.output)


def canonicalize_manifest(data: bytes) -> bytes:
    return serialize_manifest(parse_manifest(data))


def validate_canonical_manifest(data: bytes) -> dict[str, Any]:
    value = parse_manifest(data)
    if serialize_manifest(value) != data:
        raise ManifestError("manifest is not canonical")
    return value
