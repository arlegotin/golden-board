import hashlib
import json
import os
from pathlib import Path
import re
import stat


_SOURCE = Path("spec/constants-v0.json")
_MAX_SOURCE_BYTES = 65_536
_DOMAIN_NAME = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*\Z")
_DIAGNOSTIC = re.compile(
    r"[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*(?:_[a-z0-9]+)*)+\Z"
)


def _invalid() -> ValueError:
    return ValueError("invalid constants source")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _invalid()
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise _invalid()


def _load_source(root: Path) -> tuple[bytes, dict[str, object]]:
    required = ("O_CLOEXEC", "O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK")
    if any(type(getattr(os, name, None)) is not int for name in required):
        raise _invalid()
    directory_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    descriptors: list[int] = []
    try:
        descriptor = os.open(root, directory_flags)
        descriptors.append(descriptor)
        descriptor = os.open(_SOURCE.parent.name, directory_flags, dir_fd=descriptor)
        descriptors.append(descriptor)
        descriptor = os.open(_SOURCE.name, file_flags, dir_fd=descriptor)
        descriptors.append(descriptor)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_SOURCE_BYTES:
            raise _invalid()
        data = bytearray()
        while len(data) <= _MAX_SOURCE_BYTES:
            chunk = os.read(descriptor, min(65_536, _MAX_SOURCE_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        after = os.fstat(descriptor)
    except (OSError, ValueError) as error:
        if isinstance(error, ValueError):
            raise
        raise _invalid() from error
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    facts = lambda value: (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )
    if len(data) > _MAX_SOURCE_BYTES or len(data) != after.st_size or facts(before) != facts(after):
        raise _invalid()
    raw = bytes(data)
    try:
        document = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as error:
        raise _invalid() from error
    if type(document) is not dict:
        raise _invalid()
    canonical = (
        json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode()
    if raw != canonical:
        raise _invalid()
    return raw, document


def _validate(document: dict[str, object]) -> tuple[list[tuple[str, bytes]], tuple[str, ...]]:
    if set(document) != {"diagnostics", "domains", "schema_version"}:
        raise _invalid()
    if type(document["schema_version"]) is not int or document["schema_version"] != 0:
        raise _invalid()

    raw_domains = document["domains"]
    raw_diagnostics = document["diagnostics"]
    if type(raw_domains) is not list or type(raw_diagnostics) is not list:
        raise _invalid()

    domains: list[tuple[str, bytes]] = []
    names: set[str] = set()
    for value in raw_domains:
        if type(value) is not dict or set(value) != {"ascii", "hex", "name"}:
            raise _invalid()
        name = value["name"]
        ascii_text = value["ascii"]
        hex_text = value["hex"]
        if not all(type(item) is str for item in (name, ascii_text, hex_text)):
            raise _invalid()
        if not _DOMAIN_NAME.fullmatch(name) or name in names:
            raise _invalid()
        if not 1 <= len(ascii_text) <= 62:
            raise _invalid()
        try:
            ascii_bytes = ascii_text.encode("ascii", "strict")
        except UnicodeError as error:
            raise _invalid() from error
        if any(byte < 0x20 or byte > 0x7E for byte in ascii_bytes):
            raise _invalid()
        if (
            not hex_text
            or len(hex_text) % 2
            or any(character not in "0123456789abcdef" for character in hex_text)
        ):
            raise _invalid()
        try:
            domain = bytes.fromhex(hex_text)
        except ValueError as error:
            raise _invalid() from error
        if domain != ascii_bytes + b"\0":
            raise _invalid()
        names.add(name)
        domains.append((name.upper(), domain))
    if [name for name, _ in domains] != sorted(name for name, _ in domains):
        raise _invalid()

    diagnostics: list[str] = []
    seen_diagnostics: set[str] = set()
    for value in raw_diagnostics:
        if type(value) is not str or not _DIAGNOSTIC.fullmatch(value):
            raise _invalid()
        if value in seen_diagnostics:
            raise _invalid()
        seen_diagnostics.add(value)
        diagnostics.append(value)
    if not diagnostics:
        raise _invalid()
    return domains, tuple(diagnostics)


def _python_output(
    source_hash: str, domains: list[tuple[str, bytes]], diagnostics: tuple[str, ...]
) -> bytes:
    lines = [
        "# Generated by golden_board.checks from spec/constants-v0.json.",
        f"# Source SHA-256: {source_hash}",
        "# Do not edit by hand.",
        "",
    ]
    lines.extend(f"{name} = {value!r}" for name, value in domains)
    lines.extend(("", "MANIFEST_DIAGNOSTICS = ("))
    lines.extend(f"    {value!r}," for value in diagnostics)
    lines.extend((")", ""))
    return "\n".join(lines).encode("ascii")


def _rust_bytes(value: bytes) -> str:
    body = value[:-1].decode("ascii").replace("\\", "\\\\").replace('"', '\\"')
    return f'b"{body}\\0"'


def _rust_output(
    source_hash: str, domains: list[tuple[str, bytes]], diagnostics: tuple[str, ...]
) -> bytes:
    lines = [
        "// Generated by golden_board.checks from spec/constants-v0.json.",
        f"// Source SHA-256: {source_hash}",
        "// Do not edit by hand.",
        "",
    ]
    lines.extend(f"pub const {name}: &[u8] = {_rust_bytes(value)};" for name, value in domains)
    lines.extend(("", "pub const MANIFEST_DIAGNOSTICS: &[&str] = &["))
    lines.extend(f'    "{value}",' for value in diagnostics)
    lines.extend(("];", ""))
    return "\n".join(lines).encode("ascii")


def render_constants(root: Path) -> dict[Path, bytes]:
    raw, document = _load_source(root)
    domains, diagnostics = _validate(document)
    source_hash = hashlib.sha256(raw).hexdigest()
    return {
        Path("python/golden_board/constants.py"): _python_output(
            source_hash, domains, diagnostics
        ),
        Path("crates/golden-board-core/src/constants.rs"): _rust_output(
            source_hash, domains, diagnostics
        ),
    }
