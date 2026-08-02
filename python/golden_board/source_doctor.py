import codecs
from hashlib import sha256
from pathlib import Path, PurePosixPath
import re

from golden_board.source_lock import (
    AnthologyLock,
    SafeFileError,
    SourceLock,
    read_regular_below,
)


DIAGNOSTIC_PRECEDENCE = (
    "source.path",
    "source.type",
    "source.size_limit",
    "source.changed",
    "source.lock_size",
    "source.lock_hash",
    "source.utf8",
    "source.bom",
    "source.control",
    "source.newline",
    "source.final_lf",
    "source.fence_structure",
    "source.fence_count",
)

MAX_SOURCE_BYTES = 16_777_216
MAX_RECORD_DETAILS = 65
MAX_SAMPLES = 32
MAX_TAG_NAMES = 4_096
MAX_TAG_NAME_BYTES = 128
MAX_DUPLICATE_GROUPS = 64

_LIMITATIONS = [
    "lexical-only",
    "no-san-or-chess-validation",
    "tag-values-untrusted-and-omitted",
    "no-canonical-game-bytes",
]
_OPENER = re.compile(rb"```pgn[ \t]*")
_CLOSER = re.compile(rb"```[ \t]*")
_HORIZONTAL = re.compile(rb"[ \t]*")
_TAG = re.compile(rb'\[([A-Za-z][A-Za-z0-9_]*)[ \t]+"(.*)"\][ \t]*')
_CONTROL = re.compile(rb"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MOVE_NUMBER = re.compile(rb"[0-9]+(?:\.\.\.|\.)")
_NAG = re.compile(rb"\$[0-9]+")
_LINE_END = re.compile(rb"\r\n|\r|\n")
_ASCII_WHITESPACE = frozenset(b" \t\r\n\v\f")


class SourceDoctorError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def snapshot_regular_file(
    root: Path,
    lock: AnthologyLock,
    max_bytes: int = 16_777_216,
) -> bytes:
    path = lock.path
    if (
        type(path) is not PurePosixPath
        or any(character in path.as_posix() for character in ("\0", "\\"))
        or path.is_absolute()
        or not path.parts
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise SourceDoctorError("source.path")
    try:
        return read_regular_below(root, path, max_bytes)
    except SafeFileError as error:
        code = {
            "safe_file.type": "source.type",
            "safe_file.limit": "source.size_limit",
            "safe_file.changed": "source.changed",
        }.get(str(error), "source.path")
        raise SourceDoctorError(code) from error


def _lines(raw: bytes, start: int, end: int):
    """Yield physical line and content ends without copying input bytes."""
    position = start
    for match in _LINE_END.finditer(raw, start, end):
        yield position, match.end(), match.start()
        position = match.end()
    if position < end:
        yield position, end, end


def _sample(bucket: dict[str, object], start: int, end: int) -> None:
    bucket["count"] = int(bucket["count"]) + 1
    samples = bucket["samples"]
    assert type(samples) is list
    if len(samples) < MAX_SAMPLES:
        samples.append([start, end])


def _bucket() -> dict[str, object]:
    return {"count": 0, "samples": []}


def _strict_utf8(raw: bytes) -> bool:
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    view = memoryview(raw)
    try:
        for start in range(0, len(raw), 65_536):
            decoder.decode(view[start : start + 65_536], final=False)
        decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        return False
    return True


def _newline_facts(raw: bytes) -> dict[str, object]:
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    bare_cr = raw.count(b"\r") - crlf
    if lf and not crlf and not bare_cr:
        profile = "lf"
    elif crlf and not lf and not bare_cr:
        profile = "crlf"
    elif bare_cr and not lf and not crlf:
        profile = "bare-cr"
    elif lf or crlf or bare_cr:
        profile = "mixed"
    else:
        profile = "none"
    return {
        "profile": profile,
        "lf_count": lf,
        "crlf_count": crlf,
        "bare_cr_count": bare_cr,
        "final_lf": raw.endswith(b"\n"),
    }


def _fences(raw: bytes, start: int) -> tuple[dict[str, object], list[list[int]]]:
    records: list[dict[str, object]] = []
    movetext_bounds: list[list[int]] = []
    recognized = 0
    malformed = _bucket()
    opener: tuple[int, int] | None = None

    def malformed_candidates(line_start: int, content_end: int) -> None:
        candidate = line_start
        while True:
            candidate = raw.find(b"```", candidate, content_end)
            if candidate < 0:
                return
            _sample(malformed, candidate, candidate + 3)
            candidate += 3

    for line_start, line_end, content_end in _lines(raw, start, len(raw)):
        valid_opener = _OPENER.fullmatch(raw, line_start, content_end) is not None
        valid_closer = _CLOSER.fullmatch(raw, line_start, content_end) is not None
        if opener is None:
            if valid_opener:
                opener = (line_start, line_end)
            else:
                malformed_candidates(line_start, content_end)
            continue
        if valid_closer:
            recognized += 1
            if len(records) < MAX_RECORD_DETAILS:
                item: dict[str, object] = {
                    "opener_span": [opener[0], opener[1]],
                    "body_span": [opener[1], line_start],
                    "closer_span": [line_start, line_end],
                }
                records.append(item)
                movetext_bounds.append([opener[1], line_start])
            opener = None
        else:
            malformed_candidates(line_start, content_end)

    if opener is not None:
        _sample(malformed, opener[0], opener[0] + 3)
    return (
        {
            "recognized_count": recognized,
            "malformed_count": malformed["count"],
            "malformed_samples": malformed["samples"],
            "records_truncated": recognized > len(records),
            "analyzed_count": len(records),
            "records": records,
        },
        movetext_bounds,
    )


def _span_range(values: list[int]) -> list[int]:
    return [] if not values else [min(values), max(values)]


def _token_is(raw: bytes, start: int, end: int, literal: bytes) -> bool:
    return end - start == len(literal) and raw.startswith(literal, start, end)


def _normalized_hash(raw: bytes, start: int, end: int) -> str:
    digest = sha256()
    view = memoryview(raw)
    position = start
    wrote = False
    pending_separator = False
    while position < end:
        if raw[position] in _ASCII_WHITESPACE:
            pending_separator = wrote
            position += 1
            continue
        if pending_separator:
            digest.update(b" ")
            pending_separator = False
        run_start = position
        while position < end and raw[position] not in _ASCII_WHITESPACE:
            position += 1
        digest.update(view[run_start:position])
        wrote = True
    return digest.hexdigest()


def _classify_san_like(
    raw: bytes,
    start: int,
    end: int,
    movetext: dict[str, object],
    constructs: dict[str, object],
) -> None:
    suffix = 0
    if end - start >= 2 and (
        raw.startswith(b"!!", end - 2, end)
        or raw.startswith(b"??", end - 2, end)
        or raw.startswith(b"!?", end - 2, end)
        or raw.startswith(b"?!", end - 2, end)
    ):
        suffix = 2
    elif end > start and raw[end - 1] in (33, 63):
        suffix = 1
    if suffix:
        bucket = constructs["annotation_suffixes"]
        assert type(bucket) is dict
        _sample(bucket, end - suffix, end)
        end -= suffix

    shapes = movetext["san_like_shapes"]
    assert type(shapes) is dict
    if raw.startswith(b"O-O", start, end) or raw.startswith(b"0-0", start, end):
        shape = "castle"
    elif raw.find(b"=", start, end) >= 0:
        shape = "promotion"
    elif start < end and raw[start] in b"KQRBN":
        shape = "piece"
    elif start < end and raw[start] in b"abcdefgh":
        shape = "pawn"
    else:
        shape = "other"
        bucket = constructs["unknown_tokens"]
        assert type(bucket) is dict
        _sample(bucket, start, end)
    shapes[shape] = int(shapes[shape]) + 1
    movetext["lexical_ply_count"] = int(movetext["lexical_ply_count"]) + 1


def _observe_tag_line(
    raw: bytes,
    line_start: int,
    line_end: int,
    content_end: int,
    tags: dict[str, object],
    names: dict[bytes, dict[str, int]],
    per_record: dict[bytes, int],
    constructs: dict[str, object],
) -> bool:
    match = _TAG.fullmatch(raw, line_start, content_end)
    if match is None:
        if line_start >= content_end or raw[line_start] != 91:
            return False
        tags["malformed_count"] = int(tags["malformed_count"]) + 1
        samples = tags["malformed_samples"]
        assert type(samples) is list
        if len(samples) < MAX_SAMPLES:
            samples.append([line_start, line_end])
        return True

    name_start, name_end = match.span(1)
    value_start, value_end = match.span(2)
    name_bytes = name_end - name_start
    tags["occurrence_count"] = int(tags["occurrence_count"]) + 1
    tags["max_name_bytes"] = max(int(tags["max_name_bytes"]), name_bytes)
    tags["max_value_bytes"] = max(
        int(tags["max_value_bytes"]), value_end - value_start
    )
    tags["max_line_bytes"] = max(
        int(tags["max_line_bytes"]), line_end - line_start
    )
    name: bytes | None = None
    if name_bytes <= MAX_TAG_NAME_BYTES:
        name = raw[name_start:name_end]
    if name is not None and (name in names or len(names) < MAX_TAG_NAMES):
        if name not in names:
            names[name] = {
                "count": 0,
                "duplicate_record_count": 0,
                "max_value_bytes": 0,
                "max_line_bytes": 0,
            }
        stats = names[name]
        stats["count"] += 1
        stats["max_value_bytes"] = max(
            stats["max_value_bytes"], value_end - value_start
        )
        stats["max_line_bytes"] = max(
            stats["max_line_bytes"], line_end - line_start
        )
        per_record[name] = per_record.get(name, 0) + 1
    else:
        tags["omitted_occurrence_count"] = (
            int(tags["omitted_occurrence_count"]) + 1
        )
        samples = tags["omitted_samples"]
        assert type(samples) is list
        if len(samples) < MAX_SAMPLES:
            samples.append([name_start, name_end])
        if name is None:
            tags["oversize_name_occurrence_count"] = (
                int(tags["oversize_name_occurrence_count"]) + 1
            )
            samples = tags["oversize_name_samples"]
            assert type(samples) is list
            if len(samples) < MAX_SAMPLES:
                samples.append([name_start, name_end])
    if name is not None and name in (b"SetUp", b"FEN", b"Variant"):
        bucket = constructs["alternate_start_tags"]
        assert type(bucket) is dict
        _sample(bucket, name_start, name_end)
    return True


def _scan_movetext(
    raw: bytes,
    start: int,
    end: int,
    movetext: dict[str, object],
    constructs: dict[str, object],
    tags: dict[str, object],
    names: dict[bytes, dict[str, int]],
    per_record: dict[bytes, int],
) -> int:
    position = start
    line_start = start
    rav_depth = 0
    result_seen = False
    lexical_plies_before = int(movetext["lexical_ply_count"])
    while position < end:
        byte = raw[position]
        if byte in _ASCII_WHITESPACE:
            if byte == 13:
                position += 1
                if position < end and raw[position] == 10:
                    position += 1
                line_start = position
            elif byte == 10:
                position += 1
                line_start = position
            else:
                position += 1
            continue
        if position == line_start and byte == 37:
            stop = position + 1
            while stop < end and raw[stop] not in b"\r\n":
                stop += 1
            bucket = constructs["escape_lines"]
            assert type(bucket) is dict
            _sample(bucket, position, stop)
            position = stop
            continue
        if position == line_start and byte == 91:
            terminator = _LINE_END.search(raw, position, end)
            if terminator is None:
                line_end = content_end = end
            else:
                line_end = terminator.end()
                content_end = terminator.start()
            if _observe_tag_line(
                raw,
                position,
                line_end,
                content_end,
                tags,
                names,
                per_record,
                constructs,
            ):
                position = line_end
                line_start = line_end
                continue
        if byte == 123:
            stop = raw.find(b"}", position + 1, end)
            stop = end if stop < 0 else stop + 1
            bucket = constructs["brace_comments"]
            assert type(bucket) is dict
            _sample(bucket, position, stop)
            position = stop
            continue
        if byte == 125:
            bucket = constructs["unknown_tokens"]
            assert type(bucket) is dict
            _sample(bucket, position, position + 1)
            position += 1
            continue
        if byte == 59:
            stop = position + 1
            while stop < end and raw[stop] not in b"\r\n":
                stop += 1
            bucket = constructs["semicolon_comments"]
            assert type(bucket) is dict
            _sample(bucket, position, stop)
            position = stop
            continue
        if byte == 40:
            rav_depth += 1
            bucket = constructs["ravs"]
            assert type(bucket) is dict
            _sample(bucket, position, position + 1)
            constructs["rav_max_depth"] = max(
                int(constructs["rav_max_depth"]), rav_depth
            )
            position += 1
            continue
        if byte == 41:
            rav_depth = max(0, rav_depth - 1)
            position += 1
            continue

        token_start = position
        while position < end and raw[position] not in b" \t\r\n\v\f{};()":
            position += 1
        token_end = position
        if _NAG.fullmatch(raw, token_start, token_end) is not None:
            bucket = constructs["nags"]
            assert type(bucket) is dict
            _sample(bucket, token_start, token_end)
            continue

        marker = ""
        if _token_is(raw, token_start, token_end, b"1-0"):
            marker = "white_win"
        elif _token_is(raw, token_start, token_end, b"0-1"):
            marker = "black_win"
        elif _token_is(raw, token_start, token_end, b"1/2-1/2"):
            marker = "draw"
        elif _token_is(raw, token_start, token_end, b"*"):
            marker = "unfinished"
        if marker:
            markers = movetext["result_markers"]
            assert type(markers) is dict
            markers[marker] = int(markers[marker]) + 1
            if marker == "unfinished":
                movetext["unfinished_result_count"] = (
                    int(movetext["unfinished_result_count"]) + 1
                )
            if result_seen:
                movetext["trailing_token_count"] = (
                    int(movetext["trailing_token_count"]) + 1
                )
                samples = movetext["trailing_samples"]
                assert type(samples) is list
                if len(samples) < MAX_SAMPLES:
                    samples.append([token_start, token_end])
            result_seen = True
            continue

        if result_seen:
            movetext["trailing_token_count"] = (
                int(movetext["trailing_token_count"]) + 1
            )
            samples = movetext["trailing_samples"]
            assert type(samples) is list
            if len(samples) < MAX_SAMPLES:
                samples.append([token_start, token_end])
            continue

        move_number = _MOVE_NUMBER.match(raw, token_start, token_end)
        if move_number is not None and move_number.start() == token_start:
            number_end = move_number.end()
            black = raw.startswith(b"...", number_end - 3, number_end)
            shapes = movetext["move_number_shapes"]
            assert type(shapes) is dict
            if number_end == token_end:
                shape = "black" if black else "white"
            else:
                shape = "attached_black" if black else "attached_white"
            shapes[shape] = int(shapes[shape]) + 1
            if number_end == token_end:
                continue
            token_start = number_end
        elif raw.find(b".", token_start, token_end) >= 0:
            shapes = movetext["move_number_shapes"]
            assert type(shapes) is dict
            shapes["other"] = int(shapes["other"]) + 1

        _classify_san_like(raw, token_start, token_end, movetext, constructs)
    return int(movetext["lexical_ply_count"]) - lexical_plies_before


def _analyze_records(
    raw: bytes,
    fences: dict[str, object],
    body_bounds: list[list[int]],
) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    names: dict[bytes, dict[str, int]] = {}
    tags: dict[str, object] = {
        "occurrence_count": 0,
        "names": [],
        "retained_name_count": 0,
        "omitted_occurrence_count": 0,
        "omitted_samples": [],
        "oversize_name_occurrence_count": 0,
        "oversize_name_samples": [],
        "inventory_truncated": False,
        "max_name_bytes": 0,
        "max_value_bytes": 0,
        "max_line_bytes": 0,
        "malformed_count": 0,
        "malformed_samples": [],
        "retained_duplicate_occurrence_count": 0,
    }
    movetext: dict[str, object] = {
        "separator_shapes": {
            "empty": 0,
            "horizontal_whitespace": 0,
            "multiple": 0,
            "missing": 0,
        },
        "move_number_shapes": {
            "white": 0,
            "black": 0,
            "attached_white": 0,
            "attached_black": 0,
            "other": 0,
        },
        "san_like_shapes": {
            "castle": 0,
            "piece": 0,
            "pawn": 0,
            "promotion": 0,
            "other": 0,
        },
        "result_markers": {
            "white_win": 0,
            "black_win": 0,
            "draw": 0,
            "unfinished": 0,
        },
        "lexical_ply_count": 0,
        "unfinished_result_count": 0,
        "trailing_token_count": 0,
        "trailing_samples": [],
        "analyzed_record_count": len(body_bounds),
    }
    constructs: dict[str, object] = {
        name: _bucket()
        for name in (
            "brace_comments",
            "semicolon_comments",
            "escape_lines",
            "ravs",
            "nags",
            "annotation_suffixes",
            "alternate_start_tags",
            "unknown_tokens",
        )
    }
    constructs["rav_max_depth"] = 0
    records = fences["records"]
    assert type(records) is list
    raw_hashes: dict[str, list[list[int]]] = {}
    normalized_hashes: dict[str, list[list[int]]] = {}
    record_sizes: list[int] = []
    ply_counts: list[int] = []

    for record, bounds in zip(records, body_bounds, strict=True):
        assert type(record) is dict
        body_start, body_end = bounds
        cursor = body_start
        blank_count = 0
        first_blank_empty = False
        per_record: dict[bytes, int] = {}
        movetext_start = body_start
        found_movetext = False
        for line_start, line_end, content_end in _lines(raw, body_start, body_end):
            if _HORIZONTAL.fullmatch(raw, line_start, content_end) is not None:
                if not blank_count:
                    first_blank_empty = content_end == line_start
                blank_count += 1
                cursor = line_end
                continue
            if blank_count:
                movetext_start = line_start
                found_movetext = True
                break
            if not _observe_tag_line(
                raw,
                line_start,
                line_end,
                content_end,
                tags,
                names,
                per_record,
                constructs,
            ):
                movetext_start = line_start
                found_movetext = True
                break
            cursor = line_end

        if not found_movetext:
            movetext_start = cursor
        separators = movetext["separator_shapes"]
        assert type(separators) is dict
        if not blank_count:
            separator_shape = "missing"
        elif blank_count > 1:
            separator_shape = "multiple"
        elif first_blank_empty:
            separator_shape = "empty"
        else:
            separator_shape = "horizontal_whitespace"
        separators[separator_shape] = int(separators[separator_shape]) + 1

        record["movetext_span"] = [movetext_start, body_end]
        ply_count = _scan_movetext(
            raw,
            movetext_start,
            body_end,
            movetext,
            constructs,
            tags,
            names,
            per_record,
        )
        for name, count in per_record.items():
            if count > 1:
                names[name]["duplicate_record_count"] += 1
                tags["retained_duplicate_occurrence_count"] = (
                    int(tags["retained_duplicate_occurrence_count"]) + count - 1
                )
        ply_counts.append(ply_count)
        opener_span = record["opener_span"]
        closer_span = record["closer_span"]
        assert type(opener_span) is list and type(closer_span) is list
        record_sizes.append(int(closer_span[1]) - int(opener_span[0]))
        span = [movetext_start, body_end]
        raw_digest = sha256(memoryview(raw)[movetext_start:body_end]).hexdigest()
        raw_hashes.setdefault(raw_digest, []).append(span)
        normalized_digest = _normalized_hash(raw, movetext_start, body_end)
        normalized_hashes.setdefault(normalized_digest, []).append(span)

    tags["retained_name_count"] = len(names)
    tags["inventory_truncated"] = bool(tags["omitted_occurrence_count"])
    tag_names = tags["names"]
    assert type(tag_names) is list
    for name in sorted(names):
        stats = names[name]
        tag_names.append(
            {
                "name": name.decode("ascii"),
                "count": stats["count"],
                "duplicate_record_count": stats["duplicate_record_count"],
                "max_value_bytes": stats["max_value_bytes"],
                "max_line_bytes": stats["max_line_bytes"],
            }
        )

    raw_groups = [
        (digest, spans)
        for digest, spans in raw_hashes.items()
        if len(spans) > 1
    ]
    normalized_groups = [
        (digest, spans)
        for digest, spans in normalized_hashes.items()
        if len(spans) > 1
    ]
    raw_groups.sort(key=lambda item: item[1][0][0])
    normalized_groups.sort(key=lambda item: item[1][0][0])
    all_groups = [
        {"kind": kind, "sha256": digest, "records": spans}
        for kind, groups in (
            ("raw", raw_groups),
            ("ascii-whitespace-normalized", normalized_groups),
        )
        for digest, spans in groups
    ]
    duplicates = {
        "raw_group_count": len(raw_groups),
        "normalized_group_count": len(normalized_groups),
        "groups_truncated": len(all_groups) > MAX_DUPLICATE_GROUPS,
        "groups": all_groups[:MAX_DUPLICATE_GROUPS],
    }
    ranges = {
        "record_bytes": _span_range(record_sizes),
        "lexical_plies": _span_range(ply_counts),
    }
    return tags, movetext, constructs, duplicates, ranges


def inspect_source(raw: bytes) -> dict[str, object]:
    if type(raw) is not bytes:
        raise TypeError("raw must be bytes")
    if len(raw) > MAX_SOURCE_BYTES:
        raise SourceDoctorError("source.size_limit")

    utf8 = _strict_utf8(raw)
    bom = raw.startswith(codecs.BOM_UTF8)
    controls = _bucket()
    for match in _CONTROL.finditer(raw):
        _sample(controls, match.start(), match.end())
    newlines = _newline_facts(raw)
    fences, body_bounds = _fences(raw, len(codecs.BOM_UTF8) if bom else 0)
    tags, movetext, constructs, duplicates, ranges = _analyze_records(
        raw, fences, body_bounds
    )

    selected = {
        "source.utf8": not utf8,
        "source.bom": bom,
        "source.control": bool(controls["count"]),
        "source.newline": newlines["profile"] not in ("lf", "crlf"),
        "source.final_lf": not bool(newlines["final_lf"]),
        "source.fence_structure": bool(fences["malformed_count"]),
        "source.fence_count": fences["recognized_count"] != 64,
    }
    diagnostics = [
        code for code in DIAGNOSTIC_PRECEDENCE if selected.get(code, False)
    ]
    return {
        "schema_version": 0,
        "source": {
            "byte_length": len(raw),
            "sha256": sha256(raw).hexdigest(),
        },
        "encoding": {
            "utf8": utf8,
            "bom": bom,
            "control_count": controls["count"],
            "control_samples": controls["samples"],
        },
        "newlines": newlines,
        "fences": fences,
        "tags": tags,
        "movetext": movetext,
        "constructs": constructs,
        "duplicates": duplicates,
        "ranges": ranges,
        "diagnostics": diagnostics,
        "g1_preflight": not diagnostics,
        "limitations": list(_LIMITATIONS),
    }


def build_source_report(root: Path, lock: SourceLock) -> dict[str, object]:
    raw = snapshot_regular_file(root, lock.anthology, MAX_SOURCE_BYTES)
    report = inspect_source(raw)
    module = read_regular_below(
        root,
        PurePosixPath("python/golden_board/source_doctor.py"),
        1_048_576,
    )

    source = report["source"]
    fences = report["fences"]
    newlines = report["newlines"]
    diagnostics = set(report["diagnostics"])
    assert type(source) is dict
    assert type(fences) is dict
    assert type(newlines) is dict
    source["path"] = lock.anthology.path.as_posix()
    if source["byte_length"] != lock.anthology.byte_length:
        diagnostics.add("source.lock_size")
    if source["sha256"] != lock.anthology.sha256:
        diagnostics.add("source.lock_hash")
    if newlines["profile"] != lock.anthology.newlines.lower():
        diagnostics.add("source.newline")

    report["diagnostics"] = [
        code for code in DIAGNOSTIC_PRECEDENCE if code in diagnostics
    ]
    report["g1_preflight"] = not report["diagnostics"]
    report["fence_count"] = fences["recognized_count"]
    report["raw_module_sha256"] = sha256(module).hexdigest()
    return report
