from __future__ import annotations

import os
from pathlib import Path
import re
import stat
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[2]
OWNER = ROOT / "spec" / "constants-v0.toml"
PYTHON_TARGET = ROOT / "python" / "golden_board" / "constants.py"
RUST_TARGET = ROOT / "crates" / "gb-foundation" / "src" / "constants.rs"
MAX_INPUT_BYTES = 1_048_576
MAX_OUTPUT_BYTES = 1_048_576
GROUP_NAME = re.compile(r"[a-z][a-z0-9_]*\Z")
SYMBOL_NAME = re.compile(r"[A-Z][A-Z0-9_]*\Z")
TYPE_MAX = {"u8": 255, "u16": 65_535, "u32": 4_294_967_295}


class ConstantsError(ValueError):
    pass


def _same_snapshot(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        stat.S_ISREG(left.st_mode)
        and stat.S_ISREG(right.st_mode)
        and (
            left.st_dev,
            left.st_ino,
            left.st_mode,
            left.st_size,
            left.st_mtime_ns,
            left.st_ctime_ns,
        )
        == (
            right.st_dev,
            right.st_ino,
            right.st_mode,
            right.st_size,
            right.st_mtime_ns,
            right.st_ctime_ns,
        )
    )


def _read(path: Path, limit: int | None = None) -> bytes:
    limit = MAX_INPUT_BYTES if limit is None else limit
    if not all(hasattr(os, flag) for flag in ("O_NOFOLLOW", "O_NONBLOCK")):
        raise ConstantsError("no no-follow support")
    try:
        metadata = os.stat(path, follow_symlinks=False)
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise ConstantsError("input is not a regular file")
        if metadata.st_size > limit:
            raise ConstantsError("input exceeds byte limit")
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        try:
            opened = os.fstat(descriptor)
            if not _same_snapshot(metadata, opened) or opened.st_size > limit:
                raise ConstantsError("input changed while opening")
            output = bytearray()
            while len(output) <= limit:
                chunk = os.read(descriptor, min(65_536, limit + 1 - len(output)))
                if not chunk:
                    break
                output.extend(chunk)
            if len(output) > limit:
                raise ConstantsError("input exceeds byte limit")
            finished = os.fstat(descriptor)
            current = os.stat(path, follow_symlinks=False)
            if (
                not _same_snapshot(opened, finished)
                or not _same_snapshot(finished, current)
                or len(output) != finished.st_size
            ):
                raise ConstantsError("input changed while reading")
            return bytes(output)
        finally:
            os.close(descriptor)
    except ConstantsError:
        raise
    except OSError as error:
        raise ConstantsError("cannot read input") from error


def _mapping(value: object, keys: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ConstantsError("invalid keys")
    return value


def _list(value: object, *, nonempty: bool = False) -> list[object]:
    if not isinstance(value, list) or (nonempty and not value):
        raise ConstantsError("invalid list")
    return value


def _integer(value: object, maximum: int) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ConstantsError("invalid unsigned integer")
    return value


def _name(value: object, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ConstantsError("invalid name")
    return value


def _parse(data: bytes) -> dict[str, object]:
    if len(data) > MAX_INPUT_BYTES:
        raise ConstantsError("owner exceeds byte limit")
    if data.startswith(b"\xef\xbb\xbf") or b"\r" in data or not data.endswith(b"\n"):
        raise ConstantsError("owner is not canonical UTF-8 text")
    try:
        document = tomllib.loads(data.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as error:
        raise ConstantsError("invalid constants TOML") from error
    model = _mapping(document, {"schema", "codes", "bits", "constant"})
    if model["schema"] != "golden-board.constants/v0":
        raise ConstantsError("unsupported constants schema")
    codes = _list(model["codes"], nonempty=True)
    bits = _list(model["bits"], nonempty=True)
    constants = _list(model["constant"], nonempty=True)
    group_names: set[str] = set()
    symbol_names: set[str] = set()

    def add_group(value: object) -> str:
        name = _name(value, GROUP_NAME)
        if name in group_names:
            raise ConstantsError("duplicate group name")
        group_names.add(name)
        return name

    def add_symbol(value: object) -> str:
        name = _name(value, SYMBOL_NAME)
        if name in symbol_names:
            raise ConstantsError("duplicate symbol name")
        symbol_names.add(name)
        return name

    for raw_group in codes:
        group = _mapping(
            raw_group,
            {"name", "type", "minimum", "maximum", "reserved", "values"},
        )
        add_group(group["name"])
        kind = group["type"]
        if not isinstance(kind, str) or kind not in {"u8", "u16"}:
            raise ConstantsError("invalid code type")
        type_max = TYPE_MAX[kind]
        minimum = _integer(group["minimum"], type_max)
        maximum = _integer(group["maximum"], type_max)
        if minimum > maximum:
            raise ConstantsError("invalid code domain")
        ranges: list[tuple[int, int]] = []
        previous_last: int | None = None
        for raw_range in _list(group["reserved"]):
            reserved = _mapping(raw_range, {"first", "last"})
            first = _integer(reserved["first"], type_max)
            last = _integer(reserved["last"], type_max)
            if (
                first > last
                or first < minimum
                or last > maximum
                or previous_last is not None
                and first <= previous_last + 1
            ):
                raise ConstantsError("invalid reserved range")
            ranges.append((first, last))
            previous_last = last
        member_intervals: list[tuple[int, int]] = []
        previous_value: int | None = None
        for raw_value in _list(group["values"], nonempty=True):
            value = _mapping(raw_value, {"name", "value"})
            add_symbol(value["name"])
            number = _integer(value["value"], type_max)
            if (
                number < minimum
                or number > maximum
                or previous_value is not None
                and number <= previous_value
            ):
                raise ConstantsError("invalid code member")
            member_intervals.append((number, number))
            previous_value = number
        expected = minimum
        for first, last in sorted(ranges + member_intervals):
            if first != expected:
                raise ConstantsError("code domain is not closed")
            expected = last + 1
        if expected != maximum + 1:
            raise ConstantsError("code domain is not closed")

    for raw_group in bits:
        group = _mapping(raw_group, {"name", "type", "reserved_mask", "values"})
        add_group(group["name"])
        kind = group["type"]
        if not isinstance(kind, str) or kind not in {"u8", "u16"}:
            raise ConstantsError("invalid bit type")
        type_max = TYPE_MAX[kind]
        reserved = _integer(group["reserved_mask"], type_max)
        named = 0
        previous_value = 0
        for raw_value in _list(group["values"], nonempty=True):
            value = _mapping(raw_value, {"name", "value"})
            add_symbol(value["name"])
            number = _integer(value["value"], type_max)
            if number == 0 or number & (number - 1) or number <= previous_value:
                raise ConstantsError("invalid named bit")
            if number & reserved or number & named:
                raise ConstantsError("overlapping named bit")
            named |= number
            if named > type_max:
                raise ConstantsError("bit arithmetic overflow")
            previous_value = number
        if named & reserved or named | reserved != type_max:
            raise ConstantsError("bit space is not closed")

    for raw_constant in constants:
        constant = _mapping(raw_constant, {"name", "type", "value"})
        add_symbol(constant["name"])
        if constant["type"] != "u32":
            raise ConstantsError("invalid scalar type")
        _integer(constant["value"], TYPE_MAX["u32"])
    return model


def _append(output: bytearray, line: str) -> None:
    encoded = (line + "\n").encode("ascii")
    if len(output) + len(encoded) > MAX_OUTPUT_BYTES:
        raise ConstantsError("projection exceeds byte limit")
    output.extend(encoded)


def _projection(model: dict[str, object], rust: bool) -> bytes:
    output = bytearray()
    _append(
        output,
        "//! Generated from spec/constants-v0.toml; do not edit."
        if rust
        else '"""Generated from spec/constants-v0.toml; do not edit."""',
    )
    for category in ("codes", "bits"):
        for group in model[category]:
            _append(output, "")
            for value in group["values"]:
                _append(
                    output,
                    f'pub const {value["name"]}: {group["type"]} = {value["value"]};'
                    if rust
                    else f'{value["name"]}: int = {value["value"]}',
                )
    _append(output, "")
    for value in model["constant"]:
        _append(
            output,
            f'pub const {value["name"]}: u32 = {value["value"]};'
            if rust
            else f'{value["name"]}: int = {value["value"]}',
        )
    return bytes(output)


def _render(data: bytes) -> tuple[bytes, bytes]:
    model = _parse(data)
    return _projection(model, False), _projection(model, True)


def _drift(
    owner: Path = OWNER,
    python_target: Path = PYTHON_TARGET,
    rust_target: Path = RUST_TARGET,
) -> list[Path]:
    expected = _render(_read(owner, MAX_INPUT_BYTES))
    return [
        path
        for path, wanted in zip((python_target, rust_target), expected, strict=True)
        if _read(path, MAX_OUTPUT_BYTES) != wanted
    ]


def main(arguments: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if arguments is None else arguments
    if arguments != ["check"]:
        print("usage: python -m golden_board.constants_codegen check", file=sys.stderr)
        return 2
    try:
        drift = _drift()
    except ConstantsError as error:
        print(f"constants: {error}", file=sys.stderr)
        return 1
    for path in drift:
        print(f"constants: drift: {path.relative_to(ROOT)}", file=sys.stderr)
    return bool(drift)


if __name__ == "__main__":
    raise SystemExit(main())
