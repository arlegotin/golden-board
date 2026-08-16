"""Independent, bounded source-v0 compiler and binary codecs."""

from __future__ import annotations

from dataclasses import dataclass
from collections import OrderedDict
import re
from typing import NoReturn

from . import chess
from . import constants as C


__all__ = (
    "CompiledGame",
    "GameRecord",
    "SourceCandidate",
    "SourceReject",
    "compile_source",
    "decode_game",
    "decode_game_set",
    "encode_game",
    "encode_game_set",
    "validate_anthology",
)


_AUTHORITY = object()
_SCORES = frozenset((C.SCORE_FIRST_WIN, C.SCORE_SECOND_WIN, C.SCORE_DRAW))
_SEMANTIC_CACHE: OrderedDict[
    tuple[tuple[bytes, ...], bytes],
    tuple[tuple[chess.Move, ...], tuple[tuple[str, str, int], ...]],
] = OrderedDict()
_SEMANTIC_CACHE_LIMIT = 256


class SourceReject(ValueError):
    """The complete stable source-v0 rejection value."""

    __slots__ = ("code", "raw_start", "raw_end")

    def __init__(self, code: int, raw_start: int, raw_end: int):
        self.code = code
        self.raw_start = raw_start
        self.raw_end = raw_end
        super().__init__(code, raw_start, raw_end)


def _reject(code: int, start: int, end: int) -> NoReturn:
    raise SourceReject(code, start, end)


@dataclass(frozen=True, slots=True, init=False)
class GameRecord:
    moves: tuple[chess.Move, ...]
    score: int

    def __new__(cls, *, _token: object | None = None) -> GameRecord:
        if _token is not _AUTHORITY:
            raise TypeError("GameRecord is created by source validation")
        return object.__new__(cls)

    def __init__(self, *, _token: object | None = None) -> None:
        del _token


@dataclass(frozen=True, slots=True, init=False)
class CompiledGame:
    source_ordinal: int
    opener_span: tuple[int, int]
    rows: tuple[tuple[int, int, str, str, int], ...]
    record: GameRecord

    def __new__(cls, *, _token: object | None = None) -> CompiledGame:
        if _token is not _AUTHORITY:
            raise TypeError("CompiledGame is created by compile_source")
        return object.__new__(cls)

    def __init__(self, *, _token: object | None = None) -> None:
        del _token


@dataclass(frozen=True, slots=True, init=False)
class SourceCandidate:
    games: tuple[CompiledGame, ...]
    game_set_bytes: bytes

    def __new__(cls, *, _token: object | None = None) -> SourceCandidate:
        if _token is not _AUTHORITY:
            raise TypeError("SourceCandidate is created by compile_source")
        return object.__new__(cls)

    def __init__(self, *, _token: object | None = None) -> None:
        del _token


def _make(cls: type, **fields: object):
    value = cls(_token=_AUTHORITY)
    for name, field in fields.items():
        object.__setattr__(value, name, field)
    return value


def _record(moves: tuple[chess.Move, ...], score: int) -> GameRecord:
    return _make(GameRecord, moves=moves, score=score)


def _validate_semantics(moves: tuple[chess.Move, ...], score: int, offset: int) -> None:
    replay = chess.replay_from_start(())
    for index, move in enumerate(moves):
        try:
            replay = chess.apply_move(replay, move)
        except chess.ChessReject:
            _reject(C.SOURCE_GAME_SEMANTIC, offset + index * 2, offset + index * 2 + 2)
    try:
        chess.validate_source_record(moves, score)
    except chess.ChessReject:
        _reject(C.SOURCE_GAME_SEMANTIC, offset + len(moves) * 2, offset + len(moves) * 2 + 1)


def encode_game(record: GameRecord) -> bytes:
    if type(record) is not GameRecord:
        raise TypeError("expected GameRecord")
    return (
        len(record.moves).to_bytes(2, "big")
        + b"".join(chess.encode_move(move) for move in record.moves)
        + bytes((record.score,))
    )


def _decode_game_at(data: bytes, start: int, end: int) -> GameRecord:
    if end - start < 2:
        _reject(C.SOURCE_GAME_TRUNCATED, end, end)
    count = int.from_bytes(data[start : start + 2], "big")
    if not 1 <= count <= C.SOURCE_MAX_GAME_PLIES:
        _reject(C.SOURCE_GAME_COUNT, start, start + 2)
    expected = 2 + 2 * count + 1
    if end - start < expected:
        _reject(C.SOURCE_GAME_TRUNCATED, end, end)
    exact_end = start + expected
    moves: list[chess.Move] = []
    for offset in range(start + 2, start + 2 + count * 2, 2):
        try:
            moves.append(chess.decode_move(data[offset : offset + 2]))
        except chess.ChessReject:
            _reject(C.SOURCE_GAME_MOVE, offset, offset + 2)
    score_at = start + 2 + count * 2
    score = data[score_at]
    if score not in _SCORES:
        _reject(C.SOURCE_GAME_SCORE, score_at, score_at + 1)
    if exact_end < end:
        _reject(C.SOURCE_GAME_TRAILING, exact_end, exact_end + 1)
    immutable = tuple(moves)
    _validate_semantics(immutable, score, start + 2)
    return _record(immutable, score)


def decode_game(data: bytes) -> GameRecord:
    if type(data) is not bytes:
        raise TypeError("expected bytes")
    return _decode_game_at(data, 0, len(data))


def validate_anthology(records: tuple[GameRecord, ...]) -> tuple[GameRecord, ...]:
    if type(records) is not tuple:
        raise TypeError("expected immutable GameRecordSlice")
    if len(records) != C.SOURCE_ANTHOLOGY_GAME_COUNT:
        _reject(C.SOURCE_ANTHOLOGY_COUNT, 0, 0)
    if any(type(record) is not GameRecord for record in records):
        raise TypeError("expected immutable GameRecordSlice")
    streams: set[bytes] = set()
    for record in records:
        stream = b"".join(chess.encode_move(move) for move in record.moves)
        if stream in streams:
            _reject(C.SOURCE_ANTHOLOGY_DUPLICATE_STREAM, 0, 0)
        streams.add(stream)
    return records


def encode_game_set(records: tuple[GameRecord, ...]) -> bytes:
    if type(records) is not tuple:
        raise TypeError("expected immutable GameRecordSlice")
    if not 1 <= len(records) <= C.SOURCE_MAX_GAME_SET_GAMES:
        _reject(C.SOURCE_GAME_SET_COUNT, 0, 0)
    total = 0
    for record in records:
        if type(record) is not GameRecord:
            raise TypeError("expected immutable GameRecordSlice")
        total += len(record.moves)
        if total > C.SOURCE_MAX_GAME_SET_PLIES:
            _reject(C.SOURCE_GAME_SET_TOTAL_PLIES, 0, 0)
    games = [encode_game(record) for record in records]
    games.sort()
    if any(left == right for left, right in zip(games, games[1:])):
        _reject(C.SOURCE_GAME_SET_DUPLICATE, 0, 0)
    return len(games).to_bytes(2, "big") + b"".join(games)


def decode_game_set(data: bytes) -> tuple[GameRecord, ...]:
    if type(data) is not bytes:
        raise TypeError("expected bytes")
    if len(data) > C.SOURCE_MAX_GAME_SET_BYTES:
        _reject(C.SOURCE_GAME_SET_SIZE, C.SOURCE_MAX_GAME_SET_BYTES, C.SOURCE_MAX_GAME_SET_BYTES + 1)
    if len(data) < 2:
        _reject(C.SOURCE_GAME_SET_TRUNCATED, len(data), len(data))
    count = int.from_bytes(data[:2], "big")
    if not 1 <= count <= C.SOURCE_MAX_GAME_SET_GAMES:
        _reject(C.SOURCE_GAME_SET_COUNT, 0, 2)
    spans: list[tuple[int, int]] = []
    offset = 2
    total = 0
    for _ in range(count):
        if len(data) - offset < 2:
            _reject(C.SOURCE_GAME_SET_TRUNCATED, len(data), len(data))
        plies = int.from_bytes(data[offset : offset + 2], "big")
        if not 1 <= plies <= C.SOURCE_MAX_GAME_PLIES:
            _reject(C.SOURCE_GAME_COUNT, offset, offset + 2)
        total += plies
        if total > C.SOURCE_MAX_GAME_SET_PLIES:
            _reject(C.SOURCE_GAME_SET_TOTAL_PLIES, offset, offset + 2)
        game_end = offset + 2 + plies * 2 + 1
        if game_end > len(data):
            _reject(C.SOURCE_GAME_SET_TRUNCATED, len(data), len(data))
        spans.append((offset, game_end))
        offset = game_end
    records: list[GameRecord] = []
    previous: bytes | None = None
    for start, end in spans:
        game_bytes = data[start:end]
        record = _decode_game_at(data, start, end)
        if previous is not None and game_bytes < previous:
            _reject(C.SOURCE_GAME_SET_ORDER, start, end)
        if game_bytes == previous:
            _reject(C.SOURCE_GAME_SET_DUPLICATE, start, end)
        previous = game_bytes
        records.append(record)
    if offset < len(data):
        _reject(C.SOURCE_GAME_SET_TRAILING, offset, offset + 1)
    return tuple(records)


@dataclass(frozen=True, slots=True)
class _Line:
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class _Block:
    opener: _Line
    content: tuple[_Line, ...]
    fence_end: int


@dataclass(frozen=True, slots=True)
class _Parsed:
    block: _Block
    result: bytes
    tokens: tuple[tuple[int, int], ...]
    sans: tuple[tuple[int, int], ...]
    marker: tuple[int, int]


def _best(candidates: list[tuple[int, int, int]]) -> None:
    if candidates:
        start, code, end = min(candidates)
        _reject(code, start, end)


def _profile(data: bytes) -> tuple[_Line, ...]:
    if data.startswith(b"\xef\xbb\xbf"):
        _reject(C.SOURCE_UTF8_BOM, 0, 3)
    invalid: tuple[int, int] | None = None
    controls: list[int] = []
    at = 0
    while at < len(data):
        byte = data[at]
        if byte < 0x80:
            size = 1
        elif 0xC2 <= byte <= 0xDF:
            size = 2
        elif 0xE0 <= byte <= 0xEF:
            size = 3
        elif 0xF0 <= byte <= 0xF4:
            size = 4
        else:
            invalid = (at, at + 1)
            break
        if at + size > len(data):
            invalid = (at, len(data))
            break
        tail = data[at + 1 : at + size]
        if (
            any(not 0x80 <= continuation <= 0xBF for continuation in tail)
            or byte == 0xE0 and tail[0] < 0xA0
            or byte == 0xED and tail[0] > 0x9F
            or byte == 0xF0 and tail[0] < 0x90
            or byte == 0xF4 and tail[0] > 0x8F
        ):
            invalid = (at, at + 1)
            break
        if byte < 0x20 and byte not in (9, 10, 13) or byte == 0x7F:
            controls.append(at)
        at += size
    newline_kind: bytes | None = None
    bare: list[int] = []
    mixed: list[tuple[int, int]] = []
    lines: list[_Line] = []
    line_start = 0
    at = 0
    while at < len(data):
        if data[at] == 13:
            if at + 1 >= len(data) or data[at + 1] != 10:
                bare.append(at)
                at += 1
                continue
            kind = b"\r\n"
            end = at + 2
        elif data[at] == 10:
            kind = b"\n"
            end = at + 1
        else:
            at += 1
            continue
        if newline_kind is None:
            newline_kind = kind
        elif kind != newline_kind:
            mixed.append((at, end))
        lines.append(_Line(line_start, at))
        line_start = end
        at = end
    candidates: list[tuple[int, int, int]] = []
    if invalid is not None:
        candidates.append((invalid[0], C.SOURCE_UTF8_INVALID, invalid[1]))
    candidates.extend((at, C.SOURCE_CONTROL, at + 1) for at in controls)
    candidates.extend((at, C.SOURCE_NEWLINE_BARE_CR, at + 1) for at in bare)
    candidates.extend((start, C.SOURCE_NEWLINE_MIXED, end) for start, end in mixed)
    if not data.endswith((b"\n",)):
        candidates.append((len(data), C.SOURCE_NEWLINE_FINAL_MISSING, len(data)))
    _best(candidates)
    return tuple(lines)


def _fences(data: bytes, lines: tuple[_Line, ...]) -> tuple[_Block, ...]:
    candidates: list[tuple[int, int, int]] = []
    blocks: list[_Block] = []
    opener: _Line | None = None
    content: list[_Line] = []
    for line in lines:
        raw = data[line.start : line.end]
        opened = raw.startswith(b"```pgn") and all(byte in (9, 32) for byte in raw[6:])
        closed = raw.startswith(b"```") and all(byte in (9, 32) for byte in raw[3:])
        stripped = raw.lstrip(b" \t")
        fenceish = raw.startswith(b"```") or len(stripped) != len(raw) and stripped.startswith(b"```")
        if fenceish and not opened and not closed:
            candidates.append((line.start, C.SOURCE_FENCE_SHAPE, line.end))
            if opener is not None:
                content.append(line)
            continue
        if opened:
            if opener is not None:
                candidates.append((line.start, C.SOURCE_FENCE_NESTED_OPEN, line.end))
                content.append(line)
            else:
                opener = line
                content = []
            continue
        if closed:
            if opener is None:
                candidates.append((line.start, C.SOURCE_FENCE_ORPHAN_CLOSE, line.end))
            else:
                fence_end = line.end + (2 if data[line.end : line.end + 2] == b"\r\n" else 1)
                if fence_end - opener.start > C.SOURCE_MAX_FENCE_BYTES:
                    excess = opener.start + C.SOURCE_MAX_FENCE_BYTES
                    candidates.append((excess, C.SOURCE_FENCE_BLOCK_BYTES, excess + 1))
                blocks.append(_Block(opener, tuple(content), fence_end))
                if len(blocks) > C.SOURCE_ANTHOLOGY_GAME_COUNT:
                    extra = blocks[C.SOURCE_ANTHOLOGY_GAME_COUNT].opener
                    candidates.append((extra.start, C.SOURCE_FENCE_COUNT, extra.end))
                    _best(candidates)
                opener = None
                content = []
            continue
        if opener is not None:
            content.append(line)
            if line.end - opener.start >= C.SOURCE_MAX_FENCE_BYTES:
                excess = opener.start + C.SOURCE_MAX_FENCE_BYTES
                candidates.append((excess, C.SOURCE_FENCE_BLOCK_BYTES, excess + 1))
    if opener is not None:
        if len(data) - opener.start > C.SOURCE_MAX_FENCE_BYTES:
            excess = opener.start + C.SOURCE_MAX_FENCE_BYTES
            candidates.append((excess, C.SOURCE_FENCE_BLOCK_BYTES, excess + 1))
        candidates.append((len(data), C.SOURCE_FENCE_UNCLOSED, len(data)))
    if len(blocks) < C.SOURCE_ANTHOLOGY_GAME_COUNT:
        candidates.append((len(data), C.SOURCE_FENCE_COUNT, len(data)))
    elif len(blocks) > C.SOURCE_ANTHOLOGY_GAME_COUNT:
        extra = blocks[C.SOURCE_ANTHOLOGY_GAME_COUNT].opener
        candidates.append((extra.start, C.SOURCE_FENCE_COUNT, extra.end))
    _best(candidates)
    return tuple(blocks)


def _parse_tag(data: bytes, line: _Line) -> tuple[bytes, bytes, tuple[int, int], tuple[int, int]] | tuple[None, tuple[int, int]]:
    raw = data[line.start : line.end]
    if not raw.startswith(b"["):
        return None, (line.start, line.end)
    match = re.fullmatch(rb'\[([A-Za-z][A-Za-z0-9_]*) "(.*)"\]', raw)
    if match is None:
        return None, (line.start, line.end)
    name = match.group(1)
    value = match.group(2)
    name_start = line.start + 1
    value_start = line.start + match.start(2)
    return name, value, (name_start, name_start + len(name)), (value_start, value_start + len(value))


def _tags(data: bytes, blocks: tuple[_Block, ...]) -> tuple[tuple[bytes, int], ...]:
    results: list[tuple[bytes, int]] = []
    candidates: list[tuple[int, int, int]] = []
    for block in blocks:
        seen: set[bytes] = set()
        result: bytes | None = None
        index = 0
        while index < len(block.content) and data[block.content[index].start : block.content[index].end].startswith(b"["):
            line = block.content[index]
            if index >= C.SOURCE_MAX_TAG_LINES:
                candidates.append((line.start, C.SOURCE_TAG_COUNT, line.end))
                _best(candidates)
            parsed = _parse_tag(data, line)
            if parsed[0] is None:
                candidates.append((line.start, C.SOURCE_TAG_SYNTAX, line.end))
                index += 1
                continue
            name, raw_value, name_span, value_span = parsed
            if len(name) > C.SOURCE_MAX_TAG_NAME_BYTES:
                excess = name_span[0] + C.SOURCE_MAX_TAG_NAME_BYTES
                candidates.append((excess, C.SOURCE_TAG_NAME_LENGTH, excess + 1))
            if len(raw_value) > C.SOURCE_MAX_TAG_VALUE_BYTES:
                excess = value_span[0] + C.SOURCE_MAX_TAG_VALUE_BYTES
                candidates.append((excess, C.SOURCE_TAG_VALUE_LENGTH, excess + 1))
            decoded = bytearray()
            at = 0
            while at < len(raw_value):
                if raw_value[at] == 92:
                    if at + 1 >= len(raw_value) or raw_value[at + 1] not in (34, 92):
                        end = value_span[0] + min(at + 2, len(raw_value))
                        candidates.append((value_span[0] + at, C.SOURCE_TAG_ESCAPE, end))
                        break
                    decoded.append(raw_value[at + 1])
                    at += 2
                elif raw_value[at] == 34:
                    candidates.append((line.start, C.SOURCE_TAG_SYNTAX, line.end))
                    break
                else:
                    decoded.append(raw_value[at])
                    at += 1
            if name in seen:
                candidates.append((name_span[0], C.SOURCE_TAG_DUPLICATE, name_span[1]))
            seen.add(name)
            if name in (b"SetUp", b"FEN", b"Variant"):
                candidates.append((name_span[0], C.SOURCE_TAG_FORBIDDEN, name_span[1]))
            if name == b"Result":
                result = bytes(decoded)
                if result not in (b"1-0", b"0-1", b"1/2-1/2"):
                    candidates.append((value_span[0], C.SOURCE_TAG_RESULT_VALUE, value_span[1]))
            index += 1
        if index == 0:
            start = block.content[0].start if block.content else block.opener.end + 1
            end = block.content[0].end if block.content else start
            candidates.append((start, C.SOURCE_TAG_SYNTAX, end))
        separator = block.content[index] if index < len(block.content) else None
        missing_at = separator.start if separator is not None else block.content[-1].end if block.content else block.opener.end + 1
        if result is None:
            candidates.append((missing_at, C.SOURCE_TAG_RESULT_MISSING, missing_at))
        results.append((result or b"", index))
    _best(candidates)
    return tuple(results)


def _framing(data: bytes, blocks: tuple[_Block, ...], tagged: tuple[tuple[bytes, int], ...]) -> tuple[_Parsed, ...]:
    candidates: list[tuple[int, int, int]] = []
    parsed: list[_Parsed] = []
    total_plies = 0
    for block, (result, index) in zip(blocks, tagged):
        separator: _Line | None = None
        if index >= len(block.content) or block.content[index].start != block.content[index].end:
            at = block.content[index].start if index < len(block.content) else block.opener.end + 1
            candidates.append((at, C.SOURCE_SEPARATOR_MISSING, at))
            lines = block.content[index:]
        else:
            separator = block.content[index]
            lines = block.content[index + 1 :]
            if lines and lines[0].start == lines[0].end:
                candidates.append((lines[0].start, C.SOURCE_SEPARATOR_EXTRA, lines[0].end))
        if not lines:
            if separator is not None:
                at = separator.end + (2 if data[separator.end : separator.end + 2] == b"\r\n" else 1)
            else:
                at = block.content[-1].end if block.content else block.opener.end + 1
            candidates.append((at, C.SOURCE_MOVETEXT_MISSING, at))
        tokens: list[tuple[int, int]] = []
        token_count = 0
        potential = 0
        for line in lines:
            raw = data[line.start : line.end]
            if not raw:
                candidates.append((line.start, C.SOURCE_MOVETEXT_EMPTY_LINE, line.end))
                continue
            if raw.startswith(b"["):
                candidates.append((line.start, C.SOURCE_MOVETEXT_TAG_LINE, line.end))
            if raw[:1] in (b" ", b"\t"):
                candidates.append((line.start, C.SOURCE_MOVETEXT_LEADING_HWS, line.end))
            if raw[-1:] in (b" ", b"\t"):
                candidates.append((line.start, C.SOURCE_MOVETEXT_TRAILING_HWS, line.end))
            for match in re.finditer(rb"[^ \t]+", raw):
                span = (line.start + match.start(), line.start + match.end())
                token_count += 1
                if token_count > C.SOURCE_MAX_TOKENS_PER_BLOCK:
                    candidates.append((span[0], C.SOURCE_RESOURCE_TOKEN_COUNT, span[1]))
                    _best(candidates)
                token = data[span[0] : span[1]]
                if not re.fullmatch(rb"[0-9]+\.", token) and token not in (b"1-0", b"0-1", b"1/2-1/2"):
                    potential += 1
                    total_plies += 1
                    if potential > C.SOURCE_MAX_PLIES_PER_BLOCK:
                        candidates.append((span[0], C.SOURCE_RESOURCE_RECORD_PLIES, span[1]))
                        _best(candidates)
                    if total_plies > C.SOURCE_MAX_TOTAL_PLIES:
                        candidates.append((span[0], C.SOURCE_RESOURCE_TOTAL_PLIES, span[1]))
                        _best(candidates)
                tokens.append(span)
        parsed.append(_Parsed(block, result, tuple(tokens), (), (0, 0)))
    _best(candidates)
    return tuple(parsed)


def _structure(data: bytes, records: tuple[_Parsed, ...]) -> tuple[_Parsed, ...]:
    candidates: list[tuple[int, int, int]] = []
    output: list[_Parsed] = []
    markers = (b"1-0", b"0-1", b"1/2-1/2")
    for record in records:
        sans: list[tuple[int, int]] = []
        marker: tuple[int, int] | None = None
        expected_number = 1
        state = "number"
        for span in record.tokens:
            token = data[span[0] : span[1]]
            if marker is not None:
                candidates.append((span[0], C.SOURCE_TOKEN_AFTER_RESULT, span[1]))
                continue
            if token == b"*":
                candidates.append((span[0], C.SOURCE_RESULT_TOKEN, span[1]))
                continue
            if token in markers:
                if not sans or state == "first":
                    candidates.append((span[0], C.SOURCE_RESULT_TOO_EARLY, span[1]))
                else:
                    marker = span
                    if token != record.result:
                        candidates.append((span[0], C.SOURCE_RESULT_MISMATCH, span[1]))
                continue
            number = re.fullmatch(rb"[0-9]+\.", token)
            if state == "number":
                if number is None:
                    candidates.append((span[0], C.SOURCE_MOVE_NUMBER_SHAPE, span[1]))
                    continue
                digits = token[:-1]
                valid = not digits.startswith(b"0") and len(digits) <= 10
                value = int(digits) if valid else -1
                if not valid or value > 0xFFFFFFFF or value != expected_number:
                    candidates.append((span[0], C.SOURCE_MOVE_NUMBER_VALUE, span[1]))
                state = "first"
            elif number is not None:
                candidates.append((span[0], C.SOURCE_MOVE_NUMBER_POSITION, span[1]))
            else:
                sans.append(span)
                if state == "first":
                    state = "second"
                else:
                    state = "number"
                    expected_number += 1
        if marker is None:
            at = record.tokens[-1][1] if record.tokens else record.block.content[-1].end
            candidates.append((at, C.SOURCE_RESULT_MISSING, at))
            marker = (at, at)
        output.append(_Parsed(record.block, record.result, record.tokens, tuple(sans), marker))
    _best(candidates)
    return tuple(output)


_PIECE_KIND = {
    C.SQUARE_FIRST_PAWN: 1, C.SQUARE_FIRST_KNIGHT: 2, C.SQUARE_FIRST_BISHOP: 3,
    C.SQUARE_FIRST_ROOK: 4, C.SQUARE_FIRST_QUEEN: 5, C.SQUARE_FIRST_KING: 6,
    C.SQUARE_SECOND_PAWN: 1, C.SQUARE_SECOND_KNIGHT: 2, C.SQUARE_SECOND_BISHOP: 3,
    C.SQUARE_SECOND_ROOK: 4, C.SQUARE_SECOND_QUEEN: 5, C.SQUARE_SECOND_KING: 6,
}
_PIECE_LETTER = {2: b"N", 3: b"B", 4: b"R", 5: b"Q", 6: b"K"}
_PROMOTION = {b"Q": C.PROMOTION_QUEEN, b"R": C.PROMOTION_ROOK, b"B": C.PROMOTION_BISHOP, b"N": C.PROMOTION_KNIGHT}
_PROMOTION_LETTER = {value: key for key, value in _PROMOTION.items()}


def _square(raw: bytes) -> int:
    return raw[0] - 97 + 8 * (raw[1] - 49)


def _san_shape(token: bytes) -> tuple[int, int, int, int | None, int | None, bool, int] | None:
    suffix = C.SUFFIX_NONE
    stem = token
    if token.endswith(b"+"):
        suffix, stem = C.SUFFIX_CHECK, token[:-1]
    elif token.endswith(b"#"):
        suffix, stem = C.SUFFIX_MATE, token[:-1]
    if not stem or stem.endswith((b"+", b"#")):
        return None
    if stem in (b"O-O", b"O-O-O"):
        return 6, 6 if stem == b"O-O" else 2, C.PROMOTION_NONE, None, None, False, suffix
    match = re.fullmatch(rb"([a-h])x([a-h][1-8])(?:=([QRBN]))?", stem)
    if match:
        return 1, _square(match.group(2)), _PROMOTION.get(match.group(3), C.PROMOTION_NONE), match.group(1)[0] - 97, None, True, suffix
    match = re.fullmatch(rb"([a-h][1-8])(?:=([QRBN]))?", stem)
    if match:
        return 1, _square(match.group(1)), _PROMOTION.get(match.group(2), C.PROMOTION_NONE), None, None, False, suffix
    match = re.fullmatch(rb"([KQRBN])([a-h]?)([1-8]?)(x?)([a-h][1-8])", stem)
    if not match:
        return None
    kind = {b"N": 2, b"B": 3, b"R": 4, b"Q": 5, b"K": 6}[match.group(1)]
    file_hint = match.group(2)[0] - 97 if match.group(2) else None
    rank_hint = match.group(3)[0] - 49 if match.group(3) else None
    if kind == 6 and (file_hint is not None or rank_hint is not None):
        return None
    return kind, _square(match.group(5)), C.PROMOTION_NONE, file_hint, rank_hint, bool(match.group(4)), suffix


def _capture(position: chess.WirePosition, move: chess.Move, kind: int) -> bool:
    return position.squares[move.destination] != C.SQUARE_EMPTY or (
        kind == 1 and move.origin % 8 != move.destination % 8
    )


def _canonical_stem(replay: chess.ReplayState, move: chess.Move, legal: tuple[chess.Move, ...]) -> bytes:
    position = replay.position
    kind = _PIECE_KIND[position.squares[move.origin]]
    if kind == 6 and (move.origin, move.destination) in ((4, 6), (60, 62)):
        return b"O-O"
    if kind == 6 and (move.origin, move.destination) in ((4, 2), (60, 58)):
        return b"O-O-O"
    destination = bytes((97 + move.destination % 8, 49 + move.destination // 8))
    promotion = b"=" + _PROMOTION_LETTER[move.promotion] if move.promotion else b""
    capture = _capture(position, move, kind)
    if kind == 1:
        prefix = bytes((97 + move.origin % 8,)) + b"x" if capture else b""
        return prefix + destination + promotion
    same = [
        other for other in legal
        if other.destination == move.destination
        and _PIECE_KIND[position.squares[other.origin]] == kind
    ]
    disambiguation = b""
    if kind != 6 and len(same) > 1:
        same_file = any(other.origin % 8 == move.origin % 8 for other in same if other != move)
        same_rank = any(other.origin // 8 == move.origin // 8 for other in same if other != move)
        if not same_file:
            disambiguation = bytes((97 + move.origin % 8,))
        elif not same_rank:
            disambiguation = bytes((49 + move.origin // 8,))
        else:
            disambiguation = bytes((97 + move.origin % 8, 49 + move.origin // 8))
    return _PIECE_LETTER[kind] + disambiguation + (b"x" if capture else b"") + destination


def _semantics(data: bytes, records: tuple[_Parsed, ...]) -> tuple[CompiledGame, ...]:
    by_stage: dict[int, list[tuple[int, int, int]]] = {7: [], 8: [], 9: [], 10: []}
    compiled: list[CompiledGame] = []
    score_by_result = {b"1-0": C.SCORE_FIRST_WIN, b"0-1": C.SCORE_SECOND_WIN, b"1/2-1/2": C.SCORE_DRAW}
    for ordinal, record in enumerate(records):
        cache_key = (tuple(data[start:end] for start, end in record.sans), record.result)
        cached = _SEMANTIC_CACHE.get(cache_key)
        if cached is not None:
            cached_moves, facts = cached
            rows = tuple(
                (span[0], span[1], fact[0], fact[1], fact[2])
                for span, fact in zip(record.sans, facts)
            )
            compiled.append(
                _make(
                    CompiledGame,
                    source_ordinal=ordinal,
                    opener_span=(record.block.opener.start, record.block.opener.end),
                    rows=rows,
                    record=_record(cached_moves, score_by_result[record.result]),
                )
            )
            _SEMANTIC_CACHE.move_to_end(cache_key)
            continue
        game = chess.new_game()
        moves: list[chess.Move] = []
        rows: list[tuple[int, int, str, str, int]] = []
        token_indices = {span: index for index, span in enumerate(record.tokens)}
        knowable = True
        for span in record.sans:
            if not knowable:
                break
            if game.status != C.GAME_STATUS_ACTIVE:
                by_stage[7].append((span[0], C.SOURCE_GAME_AFTER_TERMINAL, span[1]))
                break
            token = data[span[0] : span[1]]
            shaped = _san_shape(token)
            if shaped is None:
                by_stage[8].append((span[0], C.SOURCE_SAN_SHAPE, span[1]))
                break
            kind, destination, promotion, file_hint, rank_hint, _capture_written, supplied_suffix = shaped
            if kind == 6 and token.removesuffix(b"+").removesuffix(b"#") in (b"O-O", b"O-O-O"):
                destination += 56 * game.replay.position.side_to_move
            if kind == 1 and destination // 8 in (0, 7) and promotion == C.PROMOTION_NONE:
                by_stage[8].append((span[0], C.SOURCE_SAN_SHAPE, span[1]))
                break
            if promotion and destination // 8 not in (0, 7):
                by_stage[8].append((span[0], C.SOURCE_SAN_SHAPE, span[1]))
                break
            legal = chess.legal_moves(game.replay)
            matches = [
                move for move in legal
                if _PIECE_KIND[game.replay.position.squares[move.origin]] == kind
                and move.destination == destination
                and move.promotion == promotion
                and (file_hint is None or move.origin % 8 == file_hint)
                and (rank_hint is None or move.origin // 8 == rank_hint)
            ]
            if not matches:
                by_stage[8].append((span[0], C.SOURCE_SAN_NO_MATCH, span[1]))
                break
            if len(matches) > 1:
                by_stage[8].append((span[0], C.SOURCE_SAN_AMBIGUOUS, span[1]))
                break
            move = matches[0]
            suffix_length = 1 if supplied_suffix else 0
            supplied_stem = token[:-suffix_length] if suffix_length else token
            canonical = _canonical_stem(game.replay, move, legal)
            stem_ok = supplied_stem == canonical
            if not stem_ok:
                by_stage[8].append((span[0], C.SOURCE_SAN_NONCANONICAL, span[1]))
            event = chess.decode_event(bytes((C.EVENT_MOVE,)) + chess.encode_move(move))
            game = chess.apply_event(game, event)
            checked = chess.king_in_check(chess.validate_local(game.replay.position), game.replay.position.side_to_move)
            truth = C.SUFFIX_MATE if game.status == C.GAME_STATUS_CHECKMATE else C.SUFFIX_CHECK if checked else C.SUFFIX_NONE
            suffix_ok = supplied_suffix == truth
            if not suffix_ok:
                if supplied_suffix:
                    by_stage[9].append((span[1] - 1, C.SOURCE_SAN_SUFFIX, span[1]))
                else:
                    by_stage[9].append((span[1], C.SOURCE_SAN_SUFFIX, span[1]))
            moves.append(move)
            if stem_ok and suffix_ok:
                rows.append((span[0], span[1], chess.encode_move(move).hex(), chess.encode_position(game.replay.position).hex(), truth))
            token_index = token_indices[span]
            if game.status != C.GAME_STATUS_ACTIVE and token_index + 1 < len(record.tokens):
                following = record.tokens[token_index + 1]
                if following != record.marker:
                    by_stage[7].append((following[0], C.SOURCE_GAME_AFTER_TERMINAL, following[1]))
                    break
        immutable = tuple(moves)
        score = score_by_result[record.result]
        score_ok = True
        if len(immutable) == len(record.sans) and game.status in (
            C.GAME_STATUS_CHECKMATE,
            C.GAME_STATUS_STALEMATE,
            C.GAME_STATUS_COMMON_DEAD,
        ):
            if score != game.score:
                score_ok = False
                by_stage[10].append((record.marker[0], C.SOURCE_TERMINAL_SCORE, record.marker[1]))
        record_value = _record(immutable, score)
        compiled.append(_make(CompiledGame, source_ordinal=ordinal, opener_span=(record.block.opener.start, record.block.opener.end), rows=tuple(rows), record=record_value))
        if len(rows) == len(record.sans) and score_ok:
            _SEMANTIC_CACHE[cache_key] = (
                immutable,
                tuple((row[2], row[3], row[4]) for row in rows),
            )
            _SEMANTIC_CACHE.move_to_end(cache_key)
            if len(_SEMANTIC_CACHE) > _SEMANTIC_CACHE_LIMIT:
                _SEMANTIC_CACHE.popitem(last=False)
    for stage in (7, 8, 9, 10):
        _best(by_stage[stage])
    return tuple(compiled)


def compile_source(raw_bytes: bytes) -> SourceCandidate:
    if type(raw_bytes) is not bytes:
        raise TypeError("expected bytes")
    if len(raw_bytes) > C.SOURCE_MAX_INPUT_BYTES:
        _reject(C.SOURCE_INPUT_TOO_LARGE, C.SOURCE_MAX_INPUT_BYTES, C.SOURCE_MAX_INPUT_BYTES + 1)
    lines = _profile(raw_bytes)
    blocks = _fences(raw_bytes, lines)
    tagged = _tags(raw_bytes, blocks)
    framed = _framing(raw_bytes, blocks, tagged)
    structured = _structure(raw_bytes, framed)
    compiled = _semantics(raw_bytes, structured)
    streams: dict[bytes, int] = {}
    for game in compiled:
        stream = b"".join(chess.encode_move(move) for move in game.record.moves)
        if stream in streams:
            start, end = game.opener_span
            _reject(C.SOURCE_DUPLICATE_MOVE_STREAM, start, end)
        streams[stream] = game.source_ordinal
    records = validate_anthology(tuple(game.record for game in compiled))
    return _make(SourceCandidate, games=compiled, game_set_bytes=encode_game_set(records))
