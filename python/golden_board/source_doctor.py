"""Bounded, observational scanner for the locked source anthology."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from bisect import bisect_right
from collections import Counter, defaultdict
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tomllib
import unicodedata

from . import canonical_manifest


MAX_SOURCE_BYTES = 1_048_576
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


class LockError(ValueError):
    """The source lock is outside the closed M0 schema."""


class InputError(OSError):
    """The locked source cannot be read safely."""


class ReportLimit(ValueError):
    """The bounded input would produce an oversized canonical report."""


REPORT_LIMIT_BYTES = (
    b'{"error":"report_limit","limit":1048576,'
    b'"schema":"golden-board.source-doctor-error/v0"}\n'
)


@dataclass(frozen=True)
class LockedSource:
    path: str
    expected_bytes: int
    expected_sha256: str


@dataclass(frozen=True)
class OpenedSource:
    data: bytes
    locked: LockedSource
    observed_sha256: str
    lock_match: bool


_SOURCE_KEYS = {
    "id",
    "role",
    "path",
    "bytes",
    "sha256",
    "encoding",
    "newline",
}
_REFERENCE_KEYS = {
    "id",
    "role",
    "title",
    "version",
    "locator",
    "accessed",
    "bytes",
    "sha256",
    "retention",
    "redistribution",
}
_REFERENCE_ROLES = {
    "fide-laws-2023": "normative_future_input",
    "pgn-guide-1994": "historical_background",
    "nist-fips-180-4": "hash_definition",
    "nist-sha-byte-vectors-archive": "known_answer_container",
    "nist-sha256-short-message-vectors": "known_answer_source",
}


def _exact_keys(value: object, keys: set[str], label: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        raise LockError(f"invalid {label} fields")
    return value


def _text(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise LockError(f"invalid {label}")
    return value


def _size(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise LockError(f"invalid {label}")
    return value


def _digest(value: object, label: str) -> str:
    value = _text(value, label)
    if _SHA256.fullmatch(value) is None:
        raise LockError(f"invalid {label}")
    return value


def _contained_path(root: Path, value: object) -> str:
    text = _text(value, "source path")
    pure = PurePosixPath(text)
    if pure.is_absolute() or ".." in pure.parts or "\\" in text:
        raise LockError("source path escapes repository")
    resolved_root = root.resolve()
    if not (resolved_root.joinpath(*pure.parts).resolve(strict=False)).is_relative_to(
        resolved_root
    ):
        raise LockError("source path escapes repository")
    return text


def parse_source_lock(data: bytes, root: Path) -> LockedSource:
    try:
        document = tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise LockError("invalid source lock TOML") from error
    document = _exact_keys(document, {"schema", "source", "reference"}, "lock")
    if document["schema"] != "golden-board.source-lock/v0":
        raise LockError("unsupported source lock schema")

    sources = document["source"]
    references = document["reference"]
    if type(sources) is not list or len(sources) != 1 or type(references) is not list:
        raise LockError("invalid source/reference entries")
    source = _exact_keys(sources[0], _SOURCE_KEYS, "source")
    if source["id"] != "anthology" or source["role"] != "authoritative_input":
        raise LockError("invalid authoritative source")
    if source["encoding"] != "utf-8" or source["newline"] != "lf":
        raise LockError("invalid source encoding profile")

    ids = {"anthology"}
    seen_references: set[str] = set()
    for raw_reference in references:
        reference = _exact_keys(raw_reference, _REFERENCE_KEYS, "reference")
        identifier = _text(reference["id"], "reference id")
        if _ID.fullmatch(identifier) is None or identifier in ids:
            raise LockError("duplicate or invalid source id")
        ids.add(identifier)
        seen_references.add(identifier)
        if reference["role"] != _REFERENCE_ROLES.get(identifier):
            raise LockError("invalid reference class")
        for key in ("title", "version", "locator", "accessed"):
            _text(reference[key], f"reference {key}")
        _size(reference["bytes"], "reference bytes")
        _digest(reference["sha256"], "reference sha256")
        if reference["retention"] != "receipt_only":
            raise LockError("invalid reference retention")
        if reference["redistribution"] != "not_established":
            raise LockError("invalid reference redistribution status")
    if seen_references != set(_REFERENCE_ROLES):
        raise LockError("missing or unexpected M0 reference")

    return LockedSource(
        path=_contained_path(root, source["path"]),
        expected_bytes=_size(source["bytes"], "source bytes"),
        expected_sha256=_digest(source["sha256"], "source sha256"),
    )


def load_source_lock(root: Path) -> LockedSource:
    try:
        data = (root / "inputs/source-lock.toml").read_bytes()
    except OSError as error:
        raise LockError("cannot read source lock") from error
    return parse_source_lock(data, root)


def read_locked_source(root: Path, locked: LockedSource) -> OpenedSource:
    try:
        relative = _contained_path(root, locked.path)
    except LockError as error:
        raise InputError("source path escapes repository") from error
    path = root.joinpath(*PurePosixPath(relative).parts)
    try:
        before = path.lstat()
    except OSError as error:
        raise InputError("source is missing or unreadable") from error
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise InputError("source is not a regular non-symlink file")

    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise InputError("source cannot be opened safely") from error
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise InputError("opened source is not a regular file")
        chunks: list[bytes] = []
        total = 0
        while total <= MAX_SOURCE_BYTES:
            chunk = os.read(descriptor, min(65_536, MAX_SOURCE_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        data = b"".join(chunks)
    except OSError as error:
        raise InputError("source read failed") from error
    finally:
        os.close(descriptor)
    if len(data) > MAX_SOURCE_BYTES:
        raise InputError("source exceeds 1048576-byte limit")
    digest = hashlib.sha256(data).hexdigest()
    return OpenedSource(
        data=data,
        locked=locked,
        observed_sha256=digest,
        lock_match=len(data) == locked.expected_bytes and digest == locked.expected_sha256,
    )


@dataclass(frozen=True)
class _Line:
    start: int
    end: int
    body: bytes
    number: int

    @property
    def raw(self) -> bytes:
        return self.body + (b"\n" if self.end > self.start + len(self.body) else b"")


@dataclass(frozen=True)
class _Candidate:
    opener: _Line
    closer: _Line
    opener_index: int
    closer_index: int


class _Samples:
    def __init__(self, data: bytes, line_starts: list[int], kind: str) -> None:
        self.data = data
        self.line_starts = line_starts
        self.kind = kind
        self.count = 0
        self.examples: list[dict[str, object]] = []

    def add(
        self,
        start: int,
        length: int,
        region: str,
        line: int | None = None,
    ) -> None:
        self.count += 1
        if len(self.examples) == 32:
            return
        fragment = self.data[start : start + length]
        retained = fragment[:256]
        self.examples.append(
            {
                "byte_length": length,
                "byte_start": start,
                "bytes_hex": retained.hex(),
                "kind": self.kind,
                "line": line
                if line is not None
                else bisect_right(self.line_starts, start),
                "region": region,
                "sha256": hashlib.sha256(fragment).hexdigest(),
                "truncated": length > 256,
            }
        )

    def result(self) -> dict[str, object]:
        self.examples.sort(
            key=lambda item: (
                item["byte_start"],
                item["byte_length"],
                item["kind"],
                item["bytes_hex"],
            )
        )
        return {
            "count": self.count,
            "examples": self.examples,
            "omitted_count": self.count - len(self.examples),
        }


class _Budget:
    """Exact lower bound for cardinality-amplifying report arrays."""

    def __init__(self) -> None:
        self.used = 0
        self.counts: Counter[str] = Counter()

    def add(self, category: str, value: object) -> None:
        # Wrapping gives the exact canonical byte length of the value without a
        # second serializer. {"v":VALUE}\n adds seven bytes.
        try:
            size = len(canonical_manifest.serialize_manifest({"v": value})) - 7
        except canonical_manifest.ManifestError as error:
            raise ReportLimit("source-doctor report limit") from error
        self.used += size + (1 if self.counts[category] else 0)
        self.counts[category] += 1
        if self.used > canonical_manifest.MAX_BYTES:
            raise ReportLimit("source-doctor report limit")


def _physical_lines(data: bytes) -> list[_Line]:
    lines: list[_Line] = []
    start = 0
    number = 1
    while start < len(data):
        newline = data.find(b"\n", start)
        end = len(data) if newline < 0 else newline + 1
        body_end = end - 1 if newline >= 0 else end
        lines.append(_Line(start, end, data[start:body_end], number))
        start = end
        number += 1
    return lines


def _is_near_miss(line: _Line) -> bool:
    body = line.body.lstrip(b" \t")
    if not body or body[0] not in (ord("`"), ord("~")):
        return False
    marker = body[0]
    run = 0
    while run < len(body) and body[run] == marker:
        run += 1
    return run >= 3


def _range(values: list[int]) -> list[int]:
    return [] if not values else [min(values), max(values)]


def _histogram(counter: Counter[str], keys: list[str] | None = None) -> list[dict[str, object]]:
    names = sorted(counter) if keys is None else keys
    return [{"count": counter[name], "key": name} for name in names]


_TAG = re.compile(rb'^\[([A-Za-z][A-Za-z0-9_]*) "((?:[^"\\\r\n]|\\["\\])*)"\]$')
_MOVE_NUMBER = re.compile(rb"([1-9][0-9]{0,19})\.\Z")
_CASTLE = re.compile(rb"O-O(?:-O)?[+#]?\Z")
_PIECE = re.compile(rb"([KQRBN])([a-h]|[1-8]|[a-h][1-8])?(x?)[a-h][1-8][+#]?\Z")
_PAWN_CAPTURE = re.compile(rb"[a-h]x[a-h][1-8](?:=[QRBN])?[+#]?\Z")
_PAWN_QUIET = re.compile(rb"[a-h][1-8](?:=[QRBN])?[+#]?\Z")
_UCI = re.compile(rb"[a-h][1-8][a-h][1-8][qrbn]?\Z")
_LAN = re.compile(rb"[KQRBN]?[a-h][1-8][-x][a-h][1-8](?:=[QRBN])?[+#]?\Z")
_RESULTS = {b"1-0", b"0-1", b"1/2-1/2", b"*"}
_LINE_CLASSES = ["empty", "move_number", "result", "san", "unknown"]
_CONSTRUCT_KEYS = [
    "annotation_suffix_token",
    "brace_close_byte",
    "brace_open_byte",
    "double_check_token",
    "ellipsis_token",
    "en_passant_text_token",
    "escape_line",
    "lan_token",
    "nag",
    "parenthesis_close_byte",
    "parenthesis_open_byte",
    "semicolon_byte",
    "uci_token",
    "unfinished_result_token",
    "zero_castling_token",
]


def _decode_tag(raw: bytes) -> tuple[bytes, Counter[str]]:
    decoded = bytearray()
    escapes: Counter[str] = Counter()
    index = 0
    while index < len(raw):
        if raw[index] == ord("\\"):
            escaped = raw[index + 1]
            if escaped == ord("\\"):
                escapes["backslash"] += 1
            else:
                escapes["quote"] += 1
            decoded.append(escaped)
            index += 2
        else:
            decoded.append(raw[index])
            index += 1
    return bytes(decoded), escapes


def _token_projection(tokens: list[bytes]) -> bytes:
    output = bytearray(len(tokens).to_bytes(4, "big"))
    for token in tokens:
        output.extend(len(token).to_bytes(4, "big"))
        output.extend(token)
    return bytes(output)


def _classify(token: bytes) -> tuple[str, int | None, re.Match[bytes] | None]:
    move = _MOVE_NUMBER.fullmatch(token)
    if move is not None:
        value = int(move.group(1))
        if value <= 18_446_744_073_709_551_615:
            return "move_number", value, move
    if token in _RESULTS:
        return "result", None, None
    if _CASTLE.fullmatch(token):
        return "castle", None, None
    piece = _PIECE.fullmatch(token)
    if piece:
        return "piece", None, piece
    if _PAWN_CAPTURE.fullmatch(token):
        return "pawn_capture", None, None
    if _PAWN_QUIET.fullmatch(token):
        return "pawn_quiet", None, None
    return "unknown", None, None


def _line_wrap_class(primary: str) -> str:
    if primary in {"castle", "piece", "pawn_capture", "pawn_quiet"}:
        return "san"
    return primary


def _duplicate_groups(
    projections: dict[bytes, list[int]], budget: _Budget, category: str
) -> list[dict[str, object]]:
    groups: list[dict[str, object]] = []
    for projection, ordinals in projections.items():
        if len(ordinals) < 2:
            continue
        value = {
            "ordinals": sorted(ordinals),
            "projection_sha256": hashlib.sha256(projection).hexdigest(),
        }
        budget.add(category, value)
        groups.append(value)
    groups.sort(key=lambda item: (item["ordinals"][0], item["ordinals"]))
    return groups


def scan_source(data: bytes, locked: LockedSource) -> dict[str, object]:
    """Scan bounded bytes without consulting ambient state."""
    if len(data) > MAX_SOURCE_BYTES:
        raise InputError("source exceeds 1048576-byte limit")
    lines = _physical_lines(data)
    line_starts = [line.start for line in lines]
    budget = _Budget()

    fence_samples = {
        name: _Samples(data, line_starts, name)
        for name in ("near_miss", "nested_opener", "orphan_closer", "unclosed_opener")
    }
    candidates: list[_Candidate] = []
    opener: tuple[_Line, int] | None = None
    recognized_openers = 0
    recognized_closers = 0
    exact_fence_lines: set[int] = set()
    for index, line in enumerate(lines):
        exact_open = line.raw == b"```pgn\n"
        exact_close = line.raw == b"```\n"
        if exact_open:
            recognized_openers += 1
            exact_fence_lines.add(line.start)
            if opener is None:
                opener = (line, index)
            else:
                fence_samples["nested_opener"].add(
                    line.start, line.end - line.start, "fence", line.number
                )
        elif exact_close:
            recognized_closers += 1
            exact_fence_lines.add(line.start)
            if opener is None:
                fence_samples["orphan_closer"].add(
                    line.start, line.end - line.start, "fence", line.number
                )
            else:
                candidates.append(_Candidate(opener[0], line, opener[1], index))
                opener = None
        elif _is_near_miss(line):
            fence_samples["near_miss"].add(
                line.start, line.end - line.start, "fence", line.number
            )
    if opener is not None:
        fence_samples["unclosed_opener"].add(
            opener[0].start,
            opener[0].end - opener[0].start,
            "fence",
            opener[0].number,
        )

    try:
        decoded_source = data.decode("utf-8")
        utf8_valid = True
        nfc_state = (
            "valid_nfc"
            if unicodedata.normalize("NFC", decoded_source) == decoded_source
            else "valid_non_nfc"
        )
    except UnicodeDecodeError:
        utf8_valid = False
        nfc_state = "unavailable"

    malformed_tags = _Samples(data, line_starts, "malformed_tag")
    unknown_tokens = _Samples(data, line_starts, "unknown_token")
    move_anomalies = _Samples(data, line_starts, "move_number_sequence_anomaly")
    region_by_line: dict[int, str] = {start: "fence" for start in exact_fence_lines}

    recognized_tags = 0
    separator_states: Counter[str] = Counter()
    tag_escape_counts: Counter[str] = Counter()
    special_names: Counter[str] = Counter()
    tag_stats: dict[str, dict[str, object]] = {}
    tag_punctuation: dict[str, dict[str, object]] = {}
    tag_orders: dict[tuple[str, ...], list[int]] = {}
    duplicate_tag_blocks: list[dict[str, object]] = []

    primary_counts: Counter[str] = Counter()
    feature_counts: Counter[str] = Counter()
    final_slot_counts: Counter[str] = Counter()
    first_classes: Counter[str] = Counter()
    last_classes: Counter[str] = Counter()
    construct_counts: Counter[str] = Counter()
    result_agreements: Counter[str] = Counter()
    result_counts: Counter[str] = Counter()
    move_number_values: list[int] = []
    token_lengths: list[int] = []
    total_tokens = 0
    empty_lines = 0
    tab_lines = 0
    repeated_space_lines = 0
    trailing_space_lines = 0
    blocks: list[dict[str, object]] = []
    raw_projections: dict[bytes, list[int]] = defaultdict(list)
    token_projections: dict[bytes, list[int]] = defaultdict(list)
    range_values: dict[str, list[int]] = defaultdict(list)

    for ordinal, candidate in enumerate(candidates, 1):
        content_lines = lines[candidate.opener_index + 1 : candidate.closer_index]
        content_start = candidate.opener.end
        content_end = candidate.closer.start
        separator_index = next(
            (index for index, line in enumerate(content_lines) if line.raw == b"\n"),
            None,
        )
        if separator_index is None:
            tag_lines = content_lines
            move_lines: list[_Line] = []
            tag_span = [content_start, content_end]
            separator_span: list[int] = []
            movetext_span: list[int] = []
            separator_state = "missing"
            raw_movetext = b""
        else:
            separator = content_lines[separator_index]
            tag_lines = content_lines[:separator_index]
            move_lines = content_lines[separator_index + 1 :]
            tag_span = [content_start, separator.start]
            separator_span = [separator.start, separator.end]
            movetext_span = [separator.end, content_end]
            separator_state = "present"
            raw_movetext = data[separator.end:content_end]
            region_by_line.setdefault(separator.start, "separator")
        separator_states[separator_state] += 1
        for line in tag_lines:
            region_by_line.setdefault(line.start, "tags")
        for line in move_lines:
            region_by_line.setdefault(line.start, "movetext")

        block_tags: list[tuple[str, bytes, bytes | None]] = []
        block_names: list[str] = []
        name_counts: Counter[str] = Counter()
        for line in tag_lines:
            match = _TAG.fullmatch(line.body)
            if match is None:
                malformed_tags.add(
                    line.start, line.end - line.start, "tags", line.number
                )
                continue
            recognized_tags += 1
            name = match.group(1).decode("ascii")
            raw = match.group(2)
            decoded, escapes = _decode_tag(raw)
            tag_escape_counts.update(escapes)
            try:
                decoded.decode("utf-8")
                decoded_value: bytes | None = decoded if utf8_valid else None
            except UnicodeDecodeError:
                decoded_value = None
            block_tags.append((name, raw, decoded_value))
            block_names.append(name)
            name_counts[name] += 1
            if name in {"FEN", "SetUp", "Variant"}:
                special_names[name] += 1

            stats = tag_stats.setdefault(
                name,
                {
                    "count": 0,
                    "decoded_value_bytes_max": 0,
                    "decoded_values_valid": utf8_valid,
                    "name": name,
                    "raw_value_bytes_max": 0,
                },
            )
            stats["count"] += 1
            stats["raw_value_bytes_max"] = max(stats["raw_value_bytes_max"], len(raw))
            if decoded_value is None:
                stats["decoded_values_valid"] = False
                stats["decoded_value_bytes_max"] = 0
            elif stats["decoded_values_valid"]:
                stats["decoded_value_bytes_max"] = max(
                    stats["decoded_value_bytes_max"], len(decoded_value)
                )

            punctuation = tag_punctuation.setdefault(
                name,
                {
                    "ellipsis_value_count": 0,
                    "name": name,
                    "question_value_count": 0,
                    "suffix_counter": Counter(),
                },
            )
            punctuation["ellipsis_value_count"] += b"..." in raw
            punctuation["question_value_count"] += b"?" in raw
            suffix = re.search(rb"[!?]+\Z", raw)
            if suffix:
                punctuation["suffix_counter"][suffix.group().decode("ascii")] += 1

        order = tuple(block_names)
        if order in tag_orders:
            tag_orders[order][0] += 1
        else:
            tag_orders[order] = [1, ordinal]
        duplicate_names = sorted(name for name, count in name_counts.items() if count > 1)
        if duplicate_names:
            duplicate_tag_blocks.append({"block": ordinal, "names": duplicate_names})

        block_tokens: list[tuple[bytes, int, int, str, int | None, re.Match[bytes] | None]] = []
        expected_move_number = 1
        block_lexical_ply = 0
        for line in move_lines:
            if b"\t" in line.body:
                tab_lines += 1
            if b"  " in line.body:
                repeated_space_lines += 1
            if line.body.endswith((b" ", b"\t")):
                trailing_space_lines += 1
            construct_counts["escape_line"] += line.body.startswith(b"%")
            line_tokens = []
            position = line.start
            while position < line.end:
                if data[position] in (0x20, 0x0A):
                    position += 1
                    continue
                end = position + 1
                while end < line.end and data[end] not in (0x20, 0x0A):
                    end += 1
                token = data[position:end]
                primary, number, piece = _classify(token)
                block_tokens.append((token, position, line.number, primary, number, piece))
                line_tokens.append(primary)
                primary_counts[primary] += 1
                token_lengths.append(len(token))
                total_tokens += 1
                if primary == "unknown":
                    unknown_tokens.add(position, len(token), "movetext", line.number)
                if primary == "move_number":
                    move_number_values.append(number)
                    if number != expected_move_number:
                        move_anomalies.add(position, len(token), "movetext", line.number)
                    expected_move_number += 1
                if primary in {"castle", "piece", "pawn_capture", "pawn_quiet"}:
                    block_lexical_ply += 1
                    feature_counts["capture"] += b"x" in token
                    feature_counts["promotion"] += b"=" in token
                    feature_counts["check"] += token.endswith(b"+")
                    feature_counts["mate"] += token.endswith(b"#")
                if primary == "castle":
                    feature_counts[
                        "castle_queenside" if token.startswith(b"O-O-O") else "castle_kingside"
                    ] += 1
                if primary == "piece":
                    capture = piece.group(3) == b"x"
                    feature_counts["piece_capture" if capture else "piece_quiet"] += 1
                    disambiguation = piece.group(2) or b""
                    if len(disambiguation) == 2:
                        feature_counts["disambiguation_square"] += 1
                    elif disambiguation in b"abcdefgh":
                        feature_counts["disambiguation_file"] += bool(disambiguation)
                    elif disambiguation:
                        feature_counts["disambiguation_rank"] += 1

                construct_counts["annotation_suffix_token"] += bool(re.search(rb"[!?]+\Z", token))
                construct_counts["ellipsis_token"] += b"..." in token
                construct_counts["zero_castling_token"] += b"0-0" in token
                construct_counts["en_passant_text_token"] += token in {b"e.p.", b"ep"}
                construct_counts["double_check_token"] += b"++" in token
                construct_counts["uci_token"] += _UCI.fullmatch(token) is not None
                construct_counts["lan_token"] += _LAN.fullmatch(token) is not None
                construct_counts["unfinished_result_token"] += token == b"*"
                position = end
            if line_tokens:
                first_classes[_line_wrap_class(line_tokens[0])] += 1
                last_classes[_line_wrap_class(line_tokens[-1])] += 1
            else:
                empty_lines += 1
                first_classes["empty"] += 1
                last_classes["empty"] += 1

        construct_counts["brace_open_byte"] += raw_movetext.count(b"{")
        construct_counts["brace_close_byte"] += raw_movetext.count(b"}")
        construct_counts["parenthesis_open_byte"] += raw_movetext.count(b"(")
        construct_counts["parenthesis_close_byte"] += raw_movetext.count(b")")
        construct_counts["semicolon_byte"] += raw_movetext.count(b";")
        construct_counts["nag"] += len(re.findall(rb"\$[0-9]+", raw_movetext))

        token_values = [token[0] for token in block_tokens]
        result_tokens = [token for token in block_tokens if token[3] == "result"]
        result_tags = [tag for tag in block_tags if tag[0] == "Result"]
        singleton_final = (
            len(result_tags) == 1
            and len(result_tokens) == 1
            and bool(block_tokens)
            and result_tokens[0] is block_tokens[-1]
            and result_tags[0][2] is not None
        )
        if singleton_final:
            result_agreement = (
                "match" if result_tags[0][2] == result_tokens[0][0] else "mismatch"
            )
        else:
            result_agreement = "indeterminate"
        result_agreements[result_agreement] += 1
        if block_tokens and block_tokens[-1][3] == "result":
            result_counts[
                {
                    b"1-0": "white_win",
                    b"0-1": "black_win",
                    b"1/2-1/2": "draw",
                    b"*": "unfinished",
                }[block_tokens[-1][0]]
            ] += 1

        lexical_slot = (
            "none" if block_lexical_ply == 0 else "white" if block_lexical_ply % 2 else "black"
        )
        final_slot_counts[lexical_slot] += 1
        projection = _token_projection(token_values)
        raw_projections[raw_movetext].append(ordinal)
        token_projections[projection].append(ordinal)
        block = {
            "closer_line": candidate.closer.number,
            "content_span": [content_start, content_end],
            "fence_span": [candidate.opener.start, candidate.closer.end],
            "lexical_final_slot": lexical_slot,
            "lexical_ply_count": block_lexical_ply,
            "movetext_lines": len(move_lines),
            "movetext_span": movetext_span,
            "opener_line": candidate.opener.number,
            "ordinal": ordinal,
            "raw_movetext_sha256": hashlib.sha256(raw_movetext).hexdigest(),
            "result_agreement": result_agreement,
            "separator_span": separator_span,
            "separator_state": separator_state,
            "tag_count": len(block_tags),
            "tag_span": tag_span,
            "token_count": len(block_tokens),
            "token_projection_sha256": hashlib.sha256(projection).hexdigest(),
        }
        budget.add("blocks", block)
        blocks.append(block)
        for name, value in (
            ("candidate_bytes", candidate.closer.end - candidate.opener.start),
            ("content_bytes", content_end - content_start),
            ("lexical_ply", block_lexical_ply),
            ("movetext_bytes", len(raw_movetext)),
            ("movetext_lines", len(move_lines)),
            ("tokens_per_candidate", len(block_tokens)),
        ):
            range_values[name].append(value)

    trailing = {
        region: _Samples(data, line_starts, "trailing_horizontal_whitespace")
        for region in ("outer_markdown", "fence", "tags", "separator", "movetext")
    }
    for line in lines:
        match = re.search(rb"[ \t]+\Z", line.body)
        if match:
            region = region_by_line.get(line.start, "outer_markdown")
            trailing[region].add(
                line.start + match.start(), len(match.group()), region, line.number
            )

    unexpected_controls = _Samples(data, line_starts, "unexpected_control")
    for offset, byte in enumerate(data):
        if byte <= 0x08 or byte in (0x0B, 0x0C, 0x7F) or 0x0E <= byte <= 0x1F:
            line_index = bisect_right(line_starts, offset) - 1
            line_start = line_starts[line_index] if line_index >= 0 else 0
            region = region_by_line.get(line_start, "outer_markdown")
            unexpected_controls.add(offset, 1, region)

    name_stats = [tag_stats[name] for name in sorted(tag_stats)]
    for value in name_stats:
        budget.add("tag_name_stats", value)
    orders = [
        {"count": value[0], "first_ordinal": value[1], "names": list(names)}
        for names, value in tag_orders.items()
    ]
    orders.sort(key=lambda item: item["first_ordinal"])
    for value in orders:
        budget.add("tag_orders", value)
    punctuation_values = []
    for name in sorted(tag_punctuation):
        raw = tag_punctuation[name]
        value = {
            "ellipsis_value_count": raw["ellipsis_value_count"],
            "name": name,
            "question_value_count": raw["question_value_count"],
            "suffixes": _histogram(raw["suffix_counter"]),
        }
        budget.add("tag_punctuation", value)
        punctuation_values.append(value)

    duplicate_tag_blocks.sort(key=lambda item: item["block"])
    duplicate_count = len(duplicate_tag_blocks)
    duplicate_examples = duplicate_tag_blocks[:32]
    raw_duplicate_groups = _duplicate_groups(raw_projections, budget, "raw_duplicates")
    token_duplicate_groups = _duplicate_groups(
        token_projections, budget, "token_duplicates"
    )
    observed_sha256 = hashlib.sha256(data).hexdigest()
    crlf = data.count(b"\r\n")
    bare_cr = sum(
        byte == 0x0D and (index + 1 == len(data) or data[index + 1] != 0x0A)
        for index, byte in enumerate(data)
    )
    report = {
        "blocks": blocks,
        "duplicate_candidates": {
            "raw_movetext": raw_duplicate_groups,
            "token_sequence": token_duplicate_groups,
        },
        "fences": {
            "candidate_count": len(candidates),
            "near_misses": fence_samples["near_miss"].result(),
            "nested_openers": fence_samples["nested_opener"].result(),
            "orphan_closers": fence_samples["orphan_closer"].result(),
            "recognized_closers": recognized_closers,
            "recognized_openers": recognized_openers,
            "unclosed_openers": fence_samples["unclosed_opener"].result(),
        },
        "movetext": {
            "constructs": _histogram(construct_counts, _CONSTRUCT_KEYS),
            "feature_counts": {
                name: feature_counts[name]
                for name in (
                    "capture",
                    "castle_kingside",
                    "castle_queenside",
                    "check",
                    "disambiguation_file",
                    "disambiguation_rank",
                    "disambiguation_square",
                    "mate",
                    "piece_capture",
                    "piece_quiet",
                    "promotion",
                )
            },
            "final_slot_counts": {
                name: final_slot_counts[name] for name in ("black", "none", "white")
            },
            "line_wrap": {
                "empty_lines": empty_lines,
                "first_class": _histogram(first_classes, _LINE_CLASSES),
                "last_class": _histogram(last_classes, _LINE_CLASSES),
                "repeated_space_lines": repeated_space_lines,
                "tab_lines": tab_lines,
                "trailing_horizontal_whitespace_lines": trailing_space_lines,
            },
            "move_numbers": {
                "count": primary_counts["move_number"],
                "sequence_anomalies": move_anomalies.result(),
                "value_range": _range(move_number_values),
            },
            "primary_counts": {
                name: primary_counts[name]
                for name in (
                    "castle",
                    "move_number",
                    "pawn_capture",
                    "pawn_quiet",
                    "piece",
                    "result",
                    "unknown",
                )
            },
            "ranges": {
                name: _range(range_values[name])
                for name in (
                    "candidate_bytes",
                    "content_bytes",
                    "lexical_ply",
                    "movetext_bytes",
                    "movetext_lines",
                    "tokens_per_candidate",
                )
            },
            "result_agreement_counts": {
                name: result_agreements[name]
                for name in ("indeterminate", "match", "mismatch")
            },
            "result_counts": {
                name: result_counts[name]
                for name in ("black_win", "draw", "unfinished", "white_win")
            },
            "token_bytes": _range(token_lengths),
            "total_tokens": total_tokens,
            "unknown_tokens": unknown_tokens.result(),
        },
        "schema": "golden-board.source-doctor/v0",
        "scope": "lexical_observation",
        "source": {
            "bom": data.startswith(b"\xef\xbb\xbf"),
            "expected_bytes": locked.expected_bytes,
            "expected_sha256": locked.expected_sha256,
            "file_kind": "regular",
            "final_lf": data.endswith(b"\n"),
            "line_endings": {
                "bare_cr": bare_cr,
                "crlf": crlf,
                "lf": data.count(b"\n") - crlf,
            },
            "lock_match": len(data) == locked.expected_bytes
            and observed_sha256 == locked.expected_sha256,
            "nfc_state": nfc_state,
            "observed_bytes": len(data),
            "observed_sha256": observed_sha256,
            "path": locked.path,
            "symlink": False,
            "tab_count": data.count(b"\t"),
            "trailing_horizontal_whitespace": [
                {"region": region, **trailing[region].result()}
                for region in ("outer_markdown", "fence", "tags", "separator", "movetext")
            ],
            "unexpected_controls": unexpected_controls.result(),
            "utf8_valid": utf8_valid,
        },
        "tags": {
            "duplicate_blocks": {
                "count": duplicate_count,
                "examples": duplicate_examples,
                "omitted_count": duplicate_count - len(duplicate_examples),
            },
            "escape_counts": {
                "backslash": tag_escape_counts["backslash"],
                "quote": tag_escape_counts["quote"],
            },
            "malformed_lines": malformed_tags.result(),
            "name_stats": name_stats,
            "orders": orders,
            "punctuation": punctuation_values,
            "recognized_lines": recognized_tags,
            "separator_states": {
                "missing": separator_states["missing"],
                "present": separator_states["present"],
            },
            "special_name_counts": {
                name: special_names[name] for name in ("FEN", "SetUp", "Variant")
            },
        },
    }
    try:
        canonical_manifest.serialize_manifest(report)
    except canonical_manifest.ManifestError as error:
        raise ReportLimit("source-doctor report limit") from error
    return report


def generate_report_bytes(data: bytes, locked: LockedSource) -> bytes:
    try:
        return canonical_manifest.serialize_manifest(scan_source(data, locked))
    except ReportLimit:
        return REPORT_LIMIT_BYTES


def _gate_passes(report: dict[str, object]) -> bool:
    source = report["source"]
    fences = report["fences"]
    return bool(
        source["lock_match"]
        and source["utf8_valid"]
        and not source["bom"]
        and source["final_lf"]
        and source["line_endings"]["crlf"] == 0
        and source["line_endings"]["bare_cr"] == 0
        and source["unexpected_controls"]["count"] == 0
        and fences["candidate_count"] == 64
        and fences["orphan_closers"]["count"] == 0
        and fences["nested_openers"]["count"] == 0
        and fences["unclosed_openers"]["count"] == 0
    )


def _worktree_root() -> Path:
    try:
        output = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise InputError("not inside a Git worktree") from error
    try:
        return Path(output.decode("utf-8").strip())
    except UnicodeDecodeError as error:
        raise InputError("worktree path is not UTF-8") from error


def main(arguments: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if arguments is None else arguments
    if arguments:
        print("usage: python -m golden_board.source_doctor", file=sys.stderr)
        return 2
    try:
        root = _worktree_root()
        locked = load_source_lock(root)
        opened = read_locked_source(root, locked)
        report = scan_source(opened.data, locked)
        report_bytes = canonical_manifest.serialize_manifest(report)
    except (InputError, LockError) as error:
        print(f"source-doctor: input: {error}", file=sys.stderr)
        return 1
    except ReportLimit:
        sys.stdout.buffer.write(REPORT_LIMIT_BYTES)
        return 1
    sys.stdout.buffer.write(report_bytes)
    return 0 if _gate_passes(report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
