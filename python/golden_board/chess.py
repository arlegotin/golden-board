"""Independent, bounded chess-v0 semantics."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import NoReturn

from . import constants as C


_AUTHORITY = object()
_INITIAL_BYTES = bytes.fromhex(
    "0402030506030204010101010101010100000000000000000000000000000000"
    "0000000000000000000000000000000007070707070707070a08090b0c09080a"
    "000f00"
)
_VALID_SQUARE_CODES = frozenset(range(C.SQUARE_EMPTY, C.SQUARE_SECOND_KING + 1))
_VALID_PROMOTIONS = frozenset(
    (
        C.PROMOTION_NONE,
        C.PROMOTION_QUEEN,
        C.PROMOTION_ROOK,
        C.PROMOTION_BISHOP,
        C.PROMOTION_KNIGHT,
    )
)
_VALID_SIDES = frozenset((C.SIDE_FIRST, C.SIDE_SECOND))
_CASTLING_MASK = (
    C.CASTLING_FIRST_KINGSIDE
    | C.CASTLING_FIRST_QUEENSIDE
    | C.CASTLING_SECOND_KINGSIDE
    | C.CASTLING_SECOND_QUEENSIDE
)


class ChessReject(ValueError):
    """The stable chess-v0 rejection datum."""

    __slots__ = ("code",)

    def __init__(self, code: int):
        self.code = code
        super().__init__(code)


def _reject(code: int) -> NoReturn:
    raise ChessReject(code)


@dataclass(frozen=True, slots=True, init=False)
class WirePosition:
    _bytes: bytes

    def __new__(cls, *, _token: object | None = None) -> WirePosition:
        if _token is not _AUTHORITY:
            raise TypeError("WirePosition is created by decode_position")
        return object.__new__(cls)

    def __init__(self, *, _token: object | None = None) -> None:
        del _token

    @property
    def squares(self) -> tuple[int, ...]:
        return tuple(self._bytes[:64])

    @property
    def side_to_move(self) -> int:
        return self._bytes[64]

    @property
    def castling_rights(self) -> int:
        return self._bytes[65]

    @property
    def nominal_en_passant(self) -> int:
        return self._bytes[66]


@dataclass(frozen=True, slots=True, init=False)
class LocallyAdmissiblePosition:
    position: WirePosition

    def __new__(cls, *, _token: object | None = None) -> LocallyAdmissiblePosition:
        if _token is not _AUTHORITY:
            raise TypeError("LocallyAdmissiblePosition is created by validate_local")
        return object.__new__(cls)

    def __init__(self, *, _token: object | None = None) -> None:
        del _token


@dataclass(frozen=True, slots=True, init=False)
class Move:
    _value: int

    def __new__(cls, *, _token: object | None = None) -> Move:
        if _token is not _AUTHORITY:
            raise TypeError("Move is created by decode_move")
        return object.__new__(cls)

    def __init__(self, *, _token: object | None = None) -> None:
        del _token

    @property
    def origin(self) -> int:
        return (self._value & C.CHESS_MOVE_ORIGIN_MASK) >> C.CHESS_MOVE_ORIGIN_SHIFT

    @property
    def destination(self) -> int:
        return (
            self._value & C.CHESS_MOVE_DESTINATION_MASK
        ) >> C.CHESS_MOVE_DESTINATION_SHIFT

    @property
    def promotion(self) -> int:
        return (
            self._value & C.CHESS_MOVE_PROMOTION_MASK
        ) >> C.CHESS_MOVE_PROMOTION_SHIFT


@dataclass(frozen=True, slots=True, init=False)
class Event:
    kind: int
    move: Move | None
    side: int | None

    def __new__(cls, *, _token: object | None = None) -> Event:
        if _token is not _AUTHORITY:
            raise TypeError("Event is created by decode_event")
        return object.__new__(cls)

    def __init__(self, *, _token: object | None = None) -> None:
        del _token


def _make(cls: type, **fields: object):
    value = cls(_token=_AUTHORITY)
    for name, field in fields.items():
        object.__setattr__(value, name, field)
    return value


def _wire(raw: bytes) -> WirePosition:
    return _make(WirePosition, _bytes=raw)


def _move(value: int) -> Move:
    return _make(Move, _value=value)


def decode_position(data: bytes) -> WirePosition:
    if type(data) is not bytes or len(data) != C.CHESS_POSITION_BYTES:
        _reject(C.CHESS_POSITION_LENGTH)
    for square_code in data[:64]:
        if square_code not in _VALID_SQUARE_CODES:
            _reject(C.CHESS_POSITION_SQUARE_CODE)
    if data[64] not in _VALID_SIDES:
        _reject(C.CHESS_POSITION_SIDE_CODE)
    if data[65] & ~_CASTLING_MASK:
        _reject(C.CHESS_POSITION_CASTLING_RESERVED)
    if data[66] > C.CHESS_SQUARE_COUNT:
        _reject(C.CHESS_POSITION_EN_PASSANT_CODE)
    return _wire(data)


def encode_position(position: WirePosition) -> bytes:
    if type(position) is not WirePosition:
        raise TypeError("expected WirePosition")
    return position._bytes


def decode_move(data: bytes) -> Move:
    if type(data) is not bytes or len(data) != C.CHESS_MOVE_BYTES:
        _reject(C.CHESS_MOVE_LENGTH)
    value = int.from_bytes(data, "big")
    if value & C.CHESS_MOVE_RESERVED_MASK:
        _reject(C.CHESS_MOVE_RESERVED)
    promotion = (value & C.CHESS_MOVE_PROMOTION_MASK) >> C.CHESS_MOVE_PROMOTION_SHIFT
    if promotion not in _VALID_PROMOTIONS:
        _reject(C.CHESS_MOVE_PROMOTION_CODE)
    origin = (value & C.CHESS_MOVE_ORIGIN_MASK) >> C.CHESS_MOVE_ORIGIN_SHIFT
    destination = (
        value & C.CHESS_MOVE_DESTINATION_MASK
    ) >> C.CHESS_MOVE_DESTINATION_SHIFT
    if origin == destination:
        _reject(C.CHESS_MOVE_SAME_SQUARE)
    return _move(value)


def encode_move(move: Move) -> bytes:
    if type(move) is not Move:
        raise TypeError("expected Move")
    return move._value.to_bytes(2, "big")


def decode_event(data: bytes) -> Event:
    if type(data) is not bytes or not data:
        _reject(C.CHESS_EVENT_LENGTH)
    kind = data[0]
    if kind not in (
        C.EVENT_MOVE,
        C.EVENT_RESIGNATION,
        C.EVENT_DRAW_AGREEMENT,
        C.EVENT_CLAIM_THREEFOLD,
        C.EVENT_CLAIM_50_MOVE,
    ):
        _reject(C.CHESS_EVENT_CODE)
    required = 3 if kind == C.EVENT_MOVE else 2 if kind == C.EVENT_RESIGNATION else 1
    if len(data) < required:
        _reject(C.CHESS_EVENT_LENGTH)
    move = decode_move(data[1:3]) if kind == C.EVENT_MOVE else None
    side = data[1] if kind == C.EVENT_RESIGNATION else None
    if side is not None and side not in _VALID_SIDES:
        _reject(C.CHESS_EVENT_SIDE_CODE)
    if len(data) > required:
        _reject(C.CHESS_EVENT_TRAILING)
    return _make(Event, kind=kind, move=move, side=side)


def encode_event(event: Event) -> bytes:
    if type(event) is not Event:
        raise TypeError("expected Event")
    if event.kind == C.EVENT_MOVE:
        return bytes((event.kind,)) + encode_move(event.move)
    if event.kind == C.EVENT_RESIGNATION:
        return bytes((event.kind, event.side))
    return bytes((event.kind,))


def _piece_side(code: int) -> int | None:
    if C.SQUARE_FIRST_PAWN <= code <= C.SQUARE_FIRST_KING:
        return C.SIDE_FIRST
    if C.SQUARE_SECOND_PAWN <= code <= C.SQUARE_SECOND_KING:
        return C.SIDE_SECOND
    return None


def _piece_kind(code: int) -> int | None:
    if code == C.SQUARE_EMPTY:
        return None
    return (code - 1) % 6 + 1


def _square_code(side: int, kind: int) -> int:
    return kind + (6 if side == C.SIDE_SECOND else 0)


def _require_side(side: int) -> None:
    if type(side) is not int or side not in _VALID_SIDES:
        raise TypeError("expected Side")


def _require_square(square: int) -> None:
    if type(square) is not int or not 0 <= square < C.CHESS_SQUARE_COUNT:
        raise TypeError("expected Square")


def _ray_step(origin: int, target: int) -> int | None:
    of, oor = origin % 8, origin // 8
    tf, tr = target % 8, target // 8
    df, dr = tf - of, tr - oor
    sf = (df > 0) - (df < 0)
    sr = (dr > 0) - (dr < 0)
    if df == 0 and dr != 0:
        return 8 * sr
    if dr == 0 and df != 0:
        return sf
    if abs(df) == abs(dr) and df:
        return 8 * sr + sf
    return None


def _controls(squares: bytes, origin: int, target: int) -> bool:
    code = squares[origin]
    side = _piece_side(code)
    kind = _piece_kind(code)
    of, oor = origin % 8, origin // 8
    tf, tr = target % 8, target // 8
    df, dr = tf - of, tr - oor
    if kind == 1:
        return dr == (1 if side == C.SIDE_FIRST else -1) and abs(df) == 1
    if kind == 2:
        return (abs(df), abs(dr)) in ((1, 2), (2, 1))
    if kind == 6:
        return max(abs(df), abs(dr)) == 1
    step = _ray_step(origin, target)
    if step is None:
        return False
    diagonal = abs(df) == abs(dr)
    if kind == 3 and not diagonal or kind == 4 and diagonal:
        return False
    if kind not in (3, 4, 5):
        return False
    square = origin + step
    while square != target:
        if squares[square] != C.SQUARE_EMPTY:
            return False
        square += step
    return True


def controls_square(position: WirePosition, side: int, target: int) -> tuple[int, ...]:
    if type(position) is not WirePosition:
        raise TypeError("expected WirePosition")
    _require_side(side)
    _require_square(target)
    squares = position._bytes[:64]
    return tuple(
        origin
        for origin, code in enumerate(squares)
        if _piece_side(code) == side and _controls(squares, origin, target)
    )


def _king_in_check_wire(position: WirePosition, side: int) -> bool:
    king = _square_code(side, 6)
    origin = position._bytes.index(king, 0, 64)
    return bool(controls_square(position, 1 - side, origin))


def validate_local(position: WirePosition) -> LocallyAdmissiblePosition:
    if type(position) is not WirePosition:
        raise TypeError("expected WirePosition")
    squares = position._bytes[:64]
    for code, rejection in (
        (C.SQUARE_FIRST_KING, C.CHESS_LOCAL_FIRST_KING_COUNT),
        (C.SQUARE_SECOND_KING, C.CHESS_LOCAL_SECOND_KING_COUNT),
    ):
        if squares.count(code) != 1:
            _reject(rejection)
    for code, rejection in (
        (C.SQUARE_FIRST_PAWN, C.CHESS_LOCAL_FIRST_PAWN_COUNT),
        (C.SQUARE_SECOND_PAWN, C.CHESS_LOCAL_SECOND_PAWN_COUNT),
    ):
        if squares.count(code) > C.CHESS_MAX_SIDE_PAWNS:
            _reject(rejection)
    for side, rejection in (
        (C.SIDE_FIRST, C.CHESS_LOCAL_FIRST_PIECE_COUNT),
        (C.SIDE_SECOND, C.CHESS_LOCAL_SECOND_PIECE_COUNT),
    ):
        if sum(_piece_side(code) == side for code in squares) > C.CHESS_MAX_SIDE_PIECES:
            _reject(rejection)
    for square in (*range(8), *range(56, 64)):
        if _piece_kind(squares[square]) == 1:
            _reject(C.CHESS_LOCAL_PAWN_ON_LAST_RANK)
    first_king = squares.index(C.SQUARE_FIRST_KING)
    second_king = squares.index(C.SQUARE_SECOND_KING)
    if max(abs(first_king % 8 - second_king % 8), abs(first_king // 8 - second_king // 8)) <= 1:
        _reject(C.CHESS_LOCAL_KINGS_ADJACENT)
    first_checked = _king_in_check_wire(position, C.SIDE_FIRST)
    second_checked = _king_in_check_wire(position, C.SIDE_SECOND)
    if first_checked and second_checked:
        _reject(C.CHESS_LOCAL_BOTH_KINGS_CHECKED)
    if (second_checked, first_checked)[position.side_to_move]:
        _reject(C.CHESS_LOCAL_INACTIVE_KING_CHECKED)
    rights = (
        (C.CASTLING_FIRST_KINGSIDE, 4, C.SQUARE_FIRST_KING, 7, C.SQUARE_FIRST_ROOK, C.CHESS_LOCAL_CASTLING_FIRST_KINGSIDE),
        (C.CASTLING_FIRST_QUEENSIDE, 4, C.SQUARE_FIRST_KING, 0, C.SQUARE_FIRST_ROOK, C.CHESS_LOCAL_CASTLING_FIRST_QUEENSIDE),
        (C.CASTLING_SECOND_KINGSIDE, 60, C.SQUARE_SECOND_KING, 63, C.SQUARE_SECOND_ROOK, C.CHESS_LOCAL_CASTLING_SECOND_KINGSIDE),
        (C.CASTLING_SECOND_QUEENSIDE, 60, C.SQUARE_SECOND_KING, 56, C.SQUARE_SECOND_ROOK, C.CHESS_LOCAL_CASTLING_SECOND_QUEENSIDE),
    )
    for bit, king_square, king, rook_square, rook, rejection in rights:
        if position.castling_rights & bit and (squares[king_square] != king or squares[rook_square] != rook):
            _reject(rejection)
    if position.nominal_en_passant:
        target = position.nominal_en_passant - 1
        if target // 8 != (5 if position.side_to_move == C.SIDE_FIRST else 2):
            _reject(C.CHESS_LOCAL_EN_PASSANT_RANK)
        if squares[target] != C.SQUARE_EMPTY:
            _reject(C.CHESS_LOCAL_EN_PASSANT_TARGET_OCCUPIED)
        pawn_square = target - 8 if position.side_to_move == C.SIDE_FIRST else target + 8
        pawn = C.SQUARE_SECOND_PAWN if position.side_to_move == C.SIDE_FIRST else C.SQUARE_FIRST_PAWN
        if squares[pawn_square] != pawn:
            _reject(C.CHESS_LOCAL_EN_PASSANT_PAWN)
        origin = target + 8 if position.side_to_move == C.SIDE_FIRST else target - 8
        if squares[origin] != C.SQUARE_EMPTY:
            _reject(C.CHESS_LOCAL_EN_PASSANT_ORIGIN_OCCUPIED)
    return _make(LocallyAdmissiblePosition, position=position)


def king_in_check(position: LocallyAdmissiblePosition, side: int) -> bool:
    if type(position) is not LocallyAdmissiblePosition:
        raise TypeError("expected LocallyAdmissiblePosition")
    _require_side(side)
    return _king_in_check_wire(position.position, side)


def _add_move(output: list[Move], origin: int, destination: int, promotion: int = 0) -> None:
    output.append(
        _move(
            origin << C.CHESS_MOVE_ORIGIN_SHIFT
            | destination << C.CHESS_MOVE_DESTINATION_SHIFT
            | promotion << C.CHESS_MOVE_PROMOTION_SHIFT
        )
    )


def _pawn_moves(position: WirePosition, origin: int, output: list[Move]) -> None:
    squares = position._bytes[:64]
    side = position.side_to_move
    direction = 8 if side == C.SIDE_FIRST else -8
    last_rank = 7 if side == C.SIDE_FIRST else 0
    start_rank = 1 if side == C.SIDE_FIRST else 6
    one = origin + direction
    if 0 <= one < 64 and squares[one] == C.SQUARE_EMPTY:
        if one // 8 == last_rank:
            for promotion in range(C.PROMOTION_QUEEN, C.PROMOTION_KNIGHT + 1):
                _add_move(output, origin, one, promotion)
        else:
            _add_move(output, origin, one)
            two = origin + 2 * direction
            if origin // 8 == start_rank and squares[two] == C.SQUARE_EMPTY:
                _add_move(output, origin, two)
    target_ep = position.nominal_en_passant - 1
    for file_step in (-1, 1):
        if not 0 <= origin % 8 + file_step < 8:
            continue
        destination = origin + direction + file_step
        if not 0 <= destination < 64:
            continue
        target_code = squares[destination]
        capture = _piece_side(target_code) == 1 - side and _piece_kind(target_code) != 6
        if not capture and destination == target_ep and target_code == C.SQUARE_EMPTY:
            captured = destination - direction
            capture = squares[captured] == _square_code(1 - side, 1)
        if capture:
            if destination // 8 == last_rank:
                for promotion in range(C.PROMOTION_QUEEN, C.PROMOTION_KNIGHT + 1):
                    _add_move(output, origin, destination, promotion)
            else:
                _add_move(output, origin, destination)


def _piece_moves(position: WirePosition, origin: int, output: list[Move]) -> None:
    squares = position._bytes[:64]
    side = position.side_to_move
    kind = _piece_kind(squares[origin])
    if kind == 1:
        _pawn_moves(position, origin, output)
        return
    of, oor = origin % 8, origin // 8
    if kind == 2:
        offsets = ((-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1))
        destinations = ((oor + dr) * 8 + of + df for df, dr in offsets if 0 <= of + df < 8 and 0 <= oor + dr < 8)
    elif kind == 6:
        destinations = (
            (oor + dr) * 8 + of + df
            for dr in (-1, 0, 1)
            for df in (-1, 0, 1)
            if (df or dr) and 0 <= of + df < 8 and 0 <= oor + dr < 8
        )
    else:
        directions = []
        if kind in (3, 5):
            directions.extend((-9, -7, 7, 9))
        if kind in (4, 5):
            directions.extend((-8, -1, 1, 8))
        ray_destinations: list[int] = []
        for step in directions:
            destination = origin + step
            while 0 <= destination < 64 and abs(destination % 8 - (destination - step) % 8) <= 1:
                ray_destinations.append(destination)
                if squares[destination] != C.SQUARE_EMPTY:
                    break
                destination += step
        destinations = iter(ray_destinations)
    for destination in destinations:
        target = squares[destination]
        if _piece_side(target) == side or _piece_kind(target) == 6:
            continue
        _add_move(output, origin, destination)
    if kind == 6:
        _pseudo_castles(position, origin, output)


def _pseudo_castles(position: WirePosition, origin: int, output: list[Move]) -> None:
    squares = position._bytes[:64]
    side = position.side_to_move
    entries = (
        (C.SIDE_FIRST, C.CASTLING_FIRST_KINGSIDE, 4, 7, (5, 6), 6),
        (C.SIDE_FIRST, C.CASTLING_FIRST_QUEENSIDE, 4, 0, (1, 2, 3), 2),
        (C.SIDE_SECOND, C.CASTLING_SECOND_KINGSIDE, 60, 63, (61, 62), 62),
        (C.SIDE_SECOND, C.CASTLING_SECOND_QUEENSIDE, 60, 56, (57, 58, 59), 58),
    )
    for castle_side, bit, king, rook, path, destination in entries:
        if (
            side == castle_side
            and origin == king
            and position.castling_rights & bit
            and squares[king] == _square_code(side, 6)
            and squares[rook] == _square_code(side, 4)
            and all(squares[square] == C.SQUARE_EMPTY for square in path)
        ):
            _add_move(output, origin, destination)


def pseudo_legal_moves(position: LocallyAdmissiblePosition) -> tuple[Move, ...]:
    if type(position) is not LocallyAdmissiblePosition:
        raise TypeError("expected LocallyAdmissiblePosition")
    wire = position.position
    output: list[Move] = []
    for origin, code in enumerate(wire._bytes[:64]):
        if _piece_side(code) == wire.side_to_move:
            _piece_moves(wire, origin, output)
    return tuple(sorted(output, key=lambda move: move._value))


@dataclass(frozen=True, slots=True, init=False)
class ReplayState:
    position: WirePosition
    _keys: tuple[bytes, ...]
    halfmove_clock: int

    def __new__(cls, *, _token: object | None = None) -> ReplayState:
        if _token is not _AUTHORITY:
            raise TypeError("ReplayState is created by replay_from_start or apply_move")
        return object.__new__(cls)

    def __init__(self, *, _token: object | None = None) -> None:
        del _token

    @property
    def played_plies(self) -> int:
        return len(self._keys) - 1


@dataclass(frozen=True, slots=True)
class BoardTerminal:
    code: int
    winning_side: int | None = None


@dataclass(frozen=True, slots=True)
class ClosureCause:
    kind: str
    terminal: BoardTerminal | None = None
    side: int | None = None


@dataclass(frozen=True, slots=True, init=False)
class GameState:
    replay: ReplayState
    status: int
    closure_cause: ClosureCause | None
    score: int | None

    def __new__(cls, *, _token: object | None = None) -> GameState:
        if _token is not _AUTHORITY:
            raise TypeError("GameState is created by new_game or apply_event")
        return object.__new__(cls)

    def __init__(self, *, _token: object | None = None) -> None:
        del _token


@dataclass(frozen=True, slots=True)
class RecordResult:
    final_replay: ReplayState
    score: int
    board_terminal: BoardTerminal
    threefold_available: bool
    fifty_move_available: bool


def _replay(position: WirePosition, keys: tuple[bytes, ...], halfmove: int) -> ReplayState:
    return _make(ReplayState, position=position, _keys=keys, halfmove_clock=halfmove)


def _game(
    replay: ReplayState,
    status: int = C.GAME_STATUS_ACTIVE,
    cause: ClosureCause | None = None,
    score: int | None = None,
) -> GameState:
    return _make(GameState, replay=replay, status=status, closure_cause=cause, score=score)


def _is_castle(move: Move, code: int) -> bool:
    return _piece_kind(code) == 6 and (move.origin, move.destination) in (
        (4, 2),
        (4, 6),
        (60, 58),
        (60, 62),
    )


def _apply_position(position: WirePosition, move: Move) -> tuple[WirePosition, bool, bool]:
    squares = bytearray(position._bytes[:64])
    moving = squares[move.origin]
    side = _piece_side(moving)
    kind = _piece_kind(moving)
    captured = squares[move.destination]
    capture = captured != C.SQUARE_EMPTY
    if (
        kind == 1
        and move.destination % 8 != move.origin % 8
        and captured == C.SQUARE_EMPTY
    ):
        ep_capture = move.destination - (8 if side == C.SIDE_FIRST else -8)
        squares[ep_capture] = C.SQUARE_EMPTY
        capture = True
    squares[move.origin] = C.SQUARE_EMPTY
    squares[move.destination] = moving
    if move.promotion:
        squares[move.destination] = _square_code(
            side,
            {
                C.PROMOTION_QUEEN: 5,
                C.PROMOTION_ROOK: 4,
                C.PROMOTION_BISHOP: 3,
                C.PROMOTION_KNIGHT: 2,
            }[move.promotion],
        )
    if _is_castle(move, moving):
        rook_origin, rook_destination = {
            (4, 6): (7, 5),
            (4, 2): (0, 3),
            (60, 62): (63, 61),
            (60, 58): (56, 59),
        }[(move.origin, move.destination)]
        squares[rook_destination] = squares[rook_origin]
        squares[rook_origin] = C.SQUARE_EMPTY
    rights = position.castling_rights
    if kind == 6:
        rights &= ~(
            (C.CASTLING_FIRST_KINGSIDE | C.CASTLING_FIRST_QUEENSIDE)
            if side == C.SIDE_FIRST
            else (C.CASTLING_SECOND_KINGSIDE | C.CASTLING_SECOND_QUEENSIDE)
        )
    home_rights = {
        0: C.CASTLING_FIRST_QUEENSIDE,
        7: C.CASTLING_FIRST_KINGSIDE,
        56: C.CASTLING_SECOND_QUEENSIDE,
        63: C.CASTLING_SECOND_KINGSIDE,
    }
    if kind == 4 and move.origin in home_rights:
        rights &= ~home_rights[move.origin]
    if captured in (C.SQUARE_FIRST_ROOK, C.SQUARE_SECOND_ROOK) and move.destination in home_rights:
        rights &= ~home_rights[move.destination]
    nominal = 0
    if kind == 1 and abs(move.destination - move.origin) == 16:
        nominal = (move.origin + move.destination) // 2 + 1
    raw = bytes(squares) + bytes((1 - position.side_to_move, rights, nominal))
    return _wire(raw), kind == 1, capture


def _castle_control_failure(position: WirePosition, move: Move) -> int | None:
    side = position.side_to_move
    if _king_in_check_wire(position, side):
        return C.CHESS_MOVE_CASTLING_FROM_CHECK
    transit = (move.origin + move.destination) // 2
    squares = bytearray(position._bytes[:64])
    squares[transit] = squares[move.origin]
    squares[move.origin] = C.SQUARE_EMPTY
    probe = _wire(bytes(squares) + position._bytes[64:])
    if _king_in_check_wire(probe, side):
        return C.CHESS_MOVE_CASTLING_THROUGH_CHECK
    applied, _, _ = _apply_position(position, move)
    if _king_in_check_wire(applied, side):
        return C.CHESS_MOVE_CASTLING_INTO_CHECK
    return None


def _mechanical_legal_moves(replay: ReplayState) -> tuple[Move, ...]:
    local = _make(LocallyAdmissiblePosition, position=replay.position)
    legal: list[Move] = []
    side = replay.position.side_to_move
    for move in pseudo_legal_moves(local):
        moving = replay.position._bytes[move.origin]
        if _is_castle(move, moving) and _castle_control_failure(replay.position, move):
            continue
        applied, _, _ = _apply_position(replay.position, move)
        if not _king_in_check_wire(applied, side):
            legal.append(move)
    return tuple(legal)


def _common_dead_position(position: WirePosition) -> bool:
    material = sorted(
        _piece_kind(code)
        for code in position._bytes[:64]
        if code != C.SQUARE_EMPTY and _piece_kind(code) != 6
    )
    return material in ([], [2], [3])


def common_dead(replay: ReplayState) -> bool:
    if type(replay) is not ReplayState:
        raise TypeError("expected ReplayState")
    return _common_dead_position(replay.position)


def board_terminal(replay: ReplayState) -> BoardTerminal:
    if type(replay) is not ReplayState:
        raise TypeError("expected ReplayState")
    moves = _mechanical_legal_moves(replay)
    if not moves:
        if _king_in_check_wire(replay.position, replay.position.side_to_move):
            return BoardTerminal(C.BOARD_TERMINAL_CHECKMATE, 1 - replay.position.side_to_move)
        return BoardTerminal(C.BOARD_TERMINAL_STALEMATE)
    if common_dead(replay):
        return BoardTerminal(C.BOARD_TERMINAL_COMMON_DEAD)
    return BoardTerminal(C.BOARD_TERMINAL_NONE)


def legal_moves(replay: ReplayState) -> tuple[Move, ...]:
    if board_terminal(replay).code != C.BOARD_TERMINAL_NONE:
        return ()
    return _mechanical_legal_moves(replay)


def _castle_entry(move: Move) -> tuple[int, tuple[int, ...], int] | None:
    return {
        (4, 6): (C.CASTLING_FIRST_KINGSIDE, (5, 6), 7),
        (4, 2): (C.CASTLING_FIRST_QUEENSIDE, (1, 2, 3), 0),
        (60, 62): (C.CASTLING_SECOND_KINGSIDE, (61, 62), 63),
        (60, 58): (C.CASTLING_SECOND_QUEENSIDE, (57, 58, 59), 56),
    }.get((move.origin, move.destination))


def _slider_geometry(origin: int, destination: int, kind: int) -> tuple[bool, bool]:
    step = _ray_step(origin, destination)
    if step is None:
        return False, False
    diagonal = abs(destination % 8 - origin % 8) == abs(destination // 8 - origin // 8)
    return (kind == 5 or kind == 3 and diagonal or kind == 4 and not diagonal), diagonal


def _diagnose_move(replay: ReplayState, move: Move) -> int:
    position = replay.position
    squares = position._bytes[:64]
    side = position.side_to_move
    moving = squares[move.origin]
    target = squares[move.destination]
    if moving == C.SQUARE_EMPTY:
        return C.CHESS_MOVE_EMPTY_ORIGIN
    if _piece_side(moving) != side:
        return C.CHESS_MOVE_WRONG_SIDE
    if _piece_side(target) == side:
        return C.CHESS_MOVE_FRIENDLY_DESTINATION
    if _piece_kind(target) == 6:
        return C.CHESS_MOVE_KING_CAPTURE
    kind = _piece_kind(moving)
    last_rank = 7 if side == C.SIDE_FIRST else 0
    if kind == 1 and move.destination // 8 == last_rank and move.promotion == C.PROMOTION_NONE:
        return C.CHESS_MOVE_PROMOTION_MISSING
    if move.promotion and (kind != 1 or move.destination // 8 != last_rank):
        return C.CHESS_MOVE_PROMOTION_UNNEEDED
    castle = _castle_entry(move) if kind == 6 else None
    if castle:
        right, path, rook = castle
        if not position.castling_rights & right:
            return C.CHESS_MOVE_CASTLING_RIGHT
        if (
            squares[rook] != _square_code(side, 4)
            or any(squares[square] != C.SQUARE_EMPTY for square in path)
        ):
            return C.CHESS_MOVE_CASTLING_PATH
        return _castle_control_failure(position, move) or C.CHESS_MOVE_SELF_CHECK
    if move in pseudo_legal_moves(_make(LocallyAdmissiblePosition, position=position)):
        return C.CHESS_MOVE_SELF_CHECK
    of, oor = move.origin % 8, move.origin // 8
    df = move.destination % 8 - of
    dr = move.destination // 8 - oor
    if kind == 1:
        forward = 1 if side == C.SIDE_FIRST else -1
        if abs(df) == 1 and target == C.SQUARE_EMPTY:
            if position.nominal_en_passant - 1 != move.destination:
                return C.CHESS_MOVE_EN_PASSANT_TARGET
            captured = move.destination - 8 * forward
            if dr != forward or squares[captured] != _square_code(1 - side, 1):
                return C.CHESS_MOVE_EN_PASSANT_GEOMETRY
        elif df == 0 and abs(dr) == 2:
            return C.CHESS_MOVE_PAWN_DOUBLE
        elif df == 0:
            return C.CHESS_MOVE_PAWN_ADVANCE
        elif abs(df) == 1:
            return C.CHESS_MOVE_PAWN_CAPTURE
        else:
            return C.CHESS_MOVE_PAWN_ADVANCE
    if kind == 2 and (abs(df), abs(dr)) not in ((1, 2), (2, 1)):
        return C.CHESS_MOVE_GEOMETRY
    if kind == 6 and max(abs(df), abs(dr)) != 1:
        return C.CHESS_MOVE_GEOMETRY
    if kind in (3, 4, 5):
        valid, _ = _slider_geometry(move.origin, move.destination, kind)
        if not valid:
            return C.CHESS_MOVE_GEOMETRY
        step = _ray_step(move.origin, move.destination)
        square = move.origin + step
        while square != move.destination:
            if squares[square] != C.SQUARE_EMPTY:
                return C.CHESS_MOVE_BLOCKED
            square += step
    return C.CHESS_MOVE_SELF_CHECK


def _repetition_bytes(position: WirePosition) -> bytes:
    if not position.nominal_en_passant:
        return position._bytes
    target = position.nominal_en_passant - 1
    temp = _replay(position, (b"",), 0)
    effective = any(
        move.destination == target
        and _piece_kind(position._bytes[move.origin]) == 1
        and move.origin % 8 != move.destination % 8
        for move in _mechanical_legal_moves(temp)
    )
    return position._bytes if effective else position._bytes[:66] + b"\0"


def repetition_key(replay: ReplayState) -> bytes:
    if type(replay) is not ReplayState:
        raise TypeError("expected ReplayState")
    return _repetition_bytes(replay.position)


def apply_move(replay: ReplayState, move: Move) -> ReplayState:
    if type(replay) is not ReplayState or type(move) is not Move:
        raise TypeError("expected ReplayState and Move")
    if board_terminal(replay).code != C.BOARD_TERMINAL_NONE:
        _reject(C.CHESS_GAME_CLOSED)
    if replay.played_plies >= C.MAX_HISTORY_PLIES:
        _reject(C.CHESS_RESOURCE_HISTORY_PLIES)
    if move not in _mechanical_legal_moves(replay):
        _reject(_diagnose_move(replay, move))
    position, pawn, capture = _apply_position(replay.position, move)
    halfmove = 0 if pawn or capture else replay.halfmove_clock + 1
    return _replay(position, replay._keys + (_repetition_bytes(position),), halfmove)


def replay_from_start(moves: tuple[Move, ...]) -> ReplayState:
    if type(moves) is not tuple or any(type(move) is not Move for move in moves[: C.MAX_HISTORY_PLIES + 1]):
        raise TypeError("expected immutable MoveSlice")
    position = decode_position(_INITIAL_BYTES)
    replay = _replay(position, (_INITIAL_BYTES,), 0)
    for move in moves[: C.MAX_HISTORY_PLIES + 1]:
        replay = apply_move(replay, move)
    return replay


def _claims(replay: ReplayState) -> tuple[bool, bool]:
    current = repetition_key(replay)
    return (
        replay._keys.count(current) >= C.CHESS_THREEFOLD_OCCURRENCES,
        replay.halfmove_clock >= C.CHESS_FIFTY_MOVE_PLIES,
    )


def new_game() -> GameState:
    return _game(replay_from_start(()))


def _closed_game(replay: ReplayState, terminal: BoardTerminal) -> GameState:
    status = {
        C.BOARD_TERMINAL_CHECKMATE: C.GAME_STATUS_CHECKMATE,
        C.BOARD_TERMINAL_STALEMATE: C.GAME_STATUS_STALEMATE,
        C.BOARD_TERMINAL_COMMON_DEAD: C.GAME_STATUS_COMMON_DEAD,
    }[terminal.code]
    score = (
        C.SCORE_DRAW
        if terminal.winning_side is None
        else C.SCORE_FIRST_WIN if terminal.winning_side == C.SIDE_FIRST else C.SCORE_SECOND_WIN
    )
    return _game(replay, status, ClosureCause("board", terminal=terminal), score)


def apply_event(game: GameState, event: Event) -> GameState:
    if type(game) is not GameState or type(event) is not Event:
        raise TypeError("expected GameState and Event")
    if game.status != C.GAME_STATUS_ACTIVE or board_terminal(game.replay).code != C.BOARD_TERMINAL_NONE:
        _reject(C.CHESS_GAME_CLOSED)
    if event.kind == C.EVENT_MOVE:
        replay = apply_move(game.replay, event.move)
        terminal = board_terminal(replay)
        return _game(replay) if terminal.code == C.BOARD_TERMINAL_NONE else _closed_game(replay, terminal)
    if event.kind == C.EVENT_RESIGNATION:
        score = C.SCORE_SECOND_WIN if event.side == C.SIDE_FIRST else C.SCORE_FIRST_WIN
        return _game(
            game.replay,
            C.GAME_STATUS_RESIGNED,
            ClosureCause("resignation", side=event.side),
            score,
        )
    if event.kind == C.EVENT_DRAW_AGREEMENT:
        if game.replay.played_plies < C.CHESS_AGREEMENT_MIN_PLIES:
            _reject(C.CHESS_EVENT_AGREEMENT_TOO_EARLY)
        return _game(game.replay, C.GAME_STATUS_AGREED, ClosureCause("draw-agreement"), C.SCORE_DRAW)
    threefold, fifty = _claims(game.replay)
    if event.kind == C.EVENT_CLAIM_THREEFOLD:
        if not threefold:
            _reject(C.CHESS_EVENT_THREEFOLD_UNAVAILABLE)
        return _game(game.replay, C.GAME_STATUS_CLAIMED_THREEFOLD, ClosureCause("claim-threefold"), C.SCORE_DRAW)
    if not fifty:
        _reject(C.CHESS_EVENT_50_MOVE_UNAVAILABLE)
    return _game(game.replay, C.GAME_STATUS_CLAIMED_50_MOVE, ClosureCause("claim-fifty-move"), C.SCORE_DRAW)


def validate_source_record(moves: tuple[Move, ...], score: int) -> RecordResult:
    if type(moves) is not tuple or type(score) is not int or score not in (
        C.SCORE_FIRST_WIN,
        C.SCORE_SECOND_WIN,
        C.SCORE_DRAW,
    ):
        raise TypeError("expected MoveSlice and Score")
    if not moves:
        _reject(C.CHESS_RECORD_EMPTY)
    replay = replay_from_start(moves)
    terminal = board_terminal(replay)
    if terminal.code == C.BOARD_TERMINAL_CHECKMATE:
        required = C.SCORE_FIRST_WIN if terminal.winning_side == C.SIDE_FIRST else C.SCORE_SECOND_WIN
        if score != required:
            _reject(C.CHESS_RECORD_CHECKMATE_SCORE)
    elif terminal.code in (C.BOARD_TERMINAL_STALEMATE, C.BOARD_TERMINAL_COMMON_DEAD) and score != C.SCORE_DRAW:
        _reject(C.CHESS_RECORD_DRAW_SCORE)
    threefold, fifty = _claims(replay)
    return RecordResult(replay, score, terminal, threefold, fifty)


@dataclass(frozen=True, slots=True)
class SetupInitialInput:
    position: WirePosition


@dataclass(frozen=True, slots=True)
class SetupCurrentSideInput:
    replay: ReplayState
    side: int


@dataclass(frozen=True, slots=True)
class OccupancyMatch:
    kind: str
    side: int | None = None
    piece: int | None = None


@dataclass(frozen=True, slots=True)
class OccupancyInput:
    position: WirePosition
    square: int
    match: OccupancyMatch


@dataclass(frozen=True, slots=True)
class MoveLegalityInput:
    replay: ReplayState
    move: Move


@dataclass(frozen=True, slots=True)
class ControlInput:
    position: WirePosition
    side: int
    target: int


@dataclass(frozen=True, slots=True)
class Defender:
    kind: str
    square: int | None = None


@dataclass(frozen=True, slots=True)
class DefendedInput:
    position: WirePosition
    target: int
    defender: Defender


@dataclass(frozen=True, slots=True)
class KingCheckInput:
    position: LocallyAdmissiblePosition
    side: int


@dataclass(frozen=True, slots=True)
class AbsolutePinInput:
    position: LocallyAdmissiblePosition
    origin: int


@dataclass(frozen=True, slots=True)
class ForkDoubleAttackInput:
    replay: ReplayState
    move: Move
    targets: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class DiscoveredLineInput:
    replay: ReplayState
    move: Move
    slider_origin: int
    target: int


@dataclass(frozen=True, slots=True)
class EscapeControlInput:
    position: WirePosition
    controlling_side: int
    candidate: int


@dataclass(frozen=True, slots=True)
class PassedPawnInput:
    position: LocallyAdmissiblePosition
    pawn_square: int


@dataclass(frozen=True, slots=True)
class OpenFileInput:
    position: WirePosition
    file: int


@dataclass(frozen=True, slots=True)
class SemiOpenFileInput:
    position: WirePosition
    side: int
    file: int


@dataclass(frozen=True, slots=True)
class PredicateEdge:
    move: Move
    child: int


@dataclass(frozen=True, slots=True)
class PredicateNode:
    edges: tuple[PredicateEdge, ...]


@dataclass(frozen=True, slots=True)
class FinitePromotionTree:
    root: ReplayState
    nodes: tuple[PredicateNode, ...]


@dataclass(frozen=True, slots=True)
class FiniteMatingTree:
    root: ReplayState
    mating_side: int
    nodes: tuple[PredicateNode, ...]


@dataclass(frozen=True, slots=True)
class TerminalTransitionInput:
    replay: ReplayState
    move: Move


@dataclass(frozen=True, slots=True)
class HistoryClaimInput:
    replay: ReplayState


@dataclass(frozen=True, slots=True)
class DeclarationEventInput:
    game: GameState
    event: Event


@dataclass(frozen=True, slots=True)
class SourceScoreInput:
    moves: tuple[Move, ...]
    score: int


@dataclass(frozen=True, slots=True)
class MoveBytesInput:
    data: bytes


@dataclass(frozen=True, slots=True)
class MoveRecordInput:
    moves: tuple[Move, ...]
    score: int


@dataclass(frozen=True, slots=True)
class MoveLegalityResult:
    kind: str
    code: int | None = None


@dataclass(frozen=True, slots=True)
class FiniteRaceResult:
    outcomes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FiniteMatingResult:
    mating_side: int
    all_branches_mate: bool
    max_plies: int


@dataclass(frozen=True, slots=True)
class EnPassantFact:
    square: int | None = None


@dataclass(frozen=True, slots=True)
class HistoryClaimResult:
    nominal_ep: EnPassantFact
    effective_ep: EnPassantFact
    current_key_occurrences: int
    halfmove_clock: int
    played_plies: int
    threefold_available: bool
    fifty_move_available: bool


@dataclass(frozen=True, slots=True)
class DeclarationEventResult:
    kind: str
    status: int | None = None
    cause: ClosureCause | None = None
    score: int | None = None
    code: int | None = None


@dataclass(frozen=True, slots=True)
class SourceScoreResult:
    kind: str
    terminal: BoardTerminal | None = None
    code: int | None = None


@dataclass(frozen=True, slots=True)
class MoveRecordResult:
    kind: str
    move: Move | None = None
    record: RecordResult | None = None
    code: int | None = None


_PREDICATE_TYPES = MappingProxyType({
    b"chess.setup_turn": (SetupInitialInput, SetupCurrentSideInput),
    b"chess.occupancy": (OccupancyInput,),
    b"chess.move_legality": (MoveLegalityInput,),
    b"chess.control": (ControlInput,),
    b"chess.defended": (DefendedInput,),
    b"chess.king_check": (KingCheckInput,),
    b"chess.absolute_pin": (AbsolutePinInput,),
    b"chess.fork_double_attack": (ForkDoubleAttackInput,),
    b"chess.discovered_attack_check": (DiscoveredLineInput,),
    b"chess.escape_square_control": (EscapeControlInput,),
    b"chess.passed_pawn": (PassedPawnInput,),
    b"chess.open_file": (OpenFileInput,),
    b"chess.semi_open_file": (SemiOpenFileInput,),
    b"chess.finite_promotion_race": (FinitePromotionTree,),
    b"chess.finite_mating_geometry": (FiniteMatingTree,),
    b"chess.terminal_transition": (TerminalTransitionInput,),
    b"chess.history_claim": (HistoryClaimInput,),
    b"chess.declaration_event": (DeclarationEventInput,),
    b"chess.source_score_relation": (SourceScoreInput,),
    b"chess.move_record_replay": (MoveBytesInput, MoveRecordInput),
})


def _predicate_signature(condition: bool) -> None:
    if not condition:
        _reject(C.CHESS_PREDICATE_SIGNATURE)


def _absolute_pin(value: AbsolutePinInput) -> bool:
    wire = value.position.position
    _require_square(value.origin)
    code = wire._bytes[value.origin]
    side = _piece_side(code)
    if side is None or _piece_kind(code) == 6 or _king_in_check_wire(wire, side):
        return False
    squares = bytearray(wire._bytes[:64])
    squares[value.origin] = C.SQUARE_EMPTY
    removed = _wire(bytes(squares) + wire._bytes[64:])
    king_square = squares.index(_square_code(side, 6))
    return any(
        _piece_kind(squares[origin]) in (3, 4, 5)
        for origin in controls_square(removed, 1 - side, king_square)
    )


def _fork(value: ForkDoubleAttackInput) -> bool:
    if board_terminal(value.replay).code != C.BOARD_TERMINAL_NONE:
        _reject(C.CHESS_GAME_CLOSED)
    if type(value.targets) is not tuple:
        _reject(C.CHESS_PREDICATE_SIGNATURE)
    if len(value.targets) > C.CHESS_MAX_FORK_TARGETS:
        _reject(C.CHESS_RESOURCE_PREDICATE_INPUT)
    if (
        len(value.targets) < C.CHESS_MIN_FORK_TARGETS
        or any(type(target) is not int or not 0 <= target < 64 for target in value.targets)
        or tuple(sorted(set(value.targets))) != value.targets
    ):
        _reject(C.CHESS_PREDICATE_SIGNATURE)
    side = value.replay.position.side_to_move
    replay = apply_move(value.replay, value.move)
    origin = value.move.destination
    squares = replay.position._bytes[:64]
    return all(
        _piece_side(squares[target]) == 1 - side and _controls(squares, origin, target)
        for target in value.targets
    )


def _discovered(value: DiscoveredLineInput) -> bool:
    _require_square(value.slider_origin)
    _require_square(value.target)
    before = value.replay.position
    side = before.side_to_move
    slider = before._bytes[value.slider_origin]
    kind = _piece_kind(slider)
    if _piece_side(slider) != side or kind not in (3, 4, 5) or value.slider_origin == value.move.origin:
        result = False
    else:
        valid, _ = _slider_geometry(value.slider_origin, value.target, kind)
        step = _ray_step(value.slider_origin, value.target) if valid else None
        square = value.slider_origin + step if step is not None else None
        result = False
        while square is not None and square != value.target:
            if before._bytes[square] != C.SQUARE_EMPTY:
                result = square == value.move.origin
                break
            square += step
    after = apply_move(value.replay, value.move)
    return result and _controls(after.position._bytes[:64], value.slider_origin, value.target)


def _passed_pawn(value: PassedPawnInput) -> bool:
    _require_square(value.pawn_square)
    wire = value.position.position
    code = wire._bytes[value.pawn_square]
    if _piece_kind(code) != 1:
        return False
    side = _piece_side(code)
    file = value.pawn_square % 8
    rank = value.pawn_square // 8
    opponent = _square_code(1 - side, 1)
    for square, other in enumerate(wire._bytes[:64]):
        if other != opponent or abs(square % 8 - file) > 1:
            continue
        if side == C.SIDE_FIRST and square // 8 > rank or side == C.SIDE_SECOND and square // 8 < rank:
            return False
    return True


def _tree_states(
    root: ReplayState, nodes: tuple[PredicateNode, ...]
) -> tuple[tuple[ReplayState, ...], tuple[int, ...], tuple[Move | None, ...]]:
    if type(nodes) is not tuple:
        _reject(C.CHESS_PREDICATE_SIGNATURE)
    if len(nodes) > C.CHESS_MAX_PREDICATE_NODES:
        _reject(C.CHESS_RESOURCE_PREDICATE_INPUT)
    if any(type(node) is not PredicateNode or type(node.edges) is not tuple for node in nodes):
        _reject(C.CHESS_PREDICATE_TREE)
    edge_counts = tuple(len(node.edges) for node in nodes)
    if any(count > C.CHESS_MAX_PREDICATE_EDGES_PER_NODE for count in edge_counts) or sum(edge_counts) > C.CHESS_MAX_PREDICATE_EDGES:
        _reject(C.CHESS_RESOURCE_PREDICATE_INPUT)
    if not nodes:
        _reject(C.CHESS_PREDICATE_TREE)
    parents = [-1] * len(nodes)
    parent_moves: list[Move | None] = [None] * len(nodes)
    for parent, node in enumerate(nodes):
        if any(type(edge) is not PredicateEdge or type(edge.move) is not Move or type(edge.child) is not int for edge in node.edges):
            _reject(C.CHESS_PREDICATE_TREE)
        move_values = tuple(edge.move._value for edge in node.edges)
        if tuple(sorted(set(move_values))) != move_values:
            _reject(C.CHESS_PREDICATE_TREE)
        for edge in node.edges:
            if not parent < edge.child < len(nodes) or parents[edge.child] != -1:
                _reject(C.CHESS_PREDICATE_TREE)
            parents[edge.child] = parent
            parent_moves[edge.child] = edge.move
    order: list[int] = []
    depths = [0] * len(nodes)
    stack = [(0, 0)]
    while stack:
        node_index, depth = stack.pop()
        if depth > C.CHESS_MAX_PREDICATE_DEPTH:
            _reject(C.CHESS_PREDICATE_TREE)
        order.append(node_index)
        depths[node_index] = depth
        for edge in reversed(nodes[node_index].edges):
            stack.append((edge.child, depth + 1))
    if order != list(range(len(nodes))) or any(parent == -1 for parent in parents[1:]):
        _reject(C.CHESS_PREDICATE_TREE)
    states: list[ReplayState] = [root]
    for index in range(1, len(nodes)):
        try:
            states.append(apply_move(states[parents[index]], parent_moves[index]))
        except ChessReject:
            _reject(C.CHESS_PREDICATE_TREE)
    return tuple(states), tuple(depths), tuple(parent_moves)


def _promotion_tree(value: FinitePromotionTree) -> FiniteRaceResult:
    states, _, parent_moves = _tree_states(value.root, value.nodes)
    outcomes: set[str] = set()
    for index, node in enumerate(value.nodes):
        move = parent_moves[index]
        promoted = move is not None and move.promotion != C.PROMOTION_NONE
        if promoted:
            if node.edges:
                _reject(C.CHESS_PREDICATE_TREE)
            mover = 1 - states[index].position.side_to_move
            outcomes.add("first-promotes" if mover == C.SIDE_FIRST else "second-promotes")
        elif not node.edges:
            outcomes.add("no-promotion-in-branch")
    order = ("first-promotes", "second-promotes", "no-promotion-in-branch")
    return FiniteRaceResult(tuple(outcome for outcome in order if outcome in outcomes))


def _mating_tree(value: FiniteMatingTree) -> FiniteMatingResult:
    _predicate_signature(type(value.mating_side) is int and value.mating_side in _VALID_SIDES)
    material = [
        (code, _piece_side(code), _piece_kind(code))
        for code in value.root.position._bytes[:64]
        if code != C.SQUARE_EMPTY
    ]
    if (
        sorted(kind for _, _, kind in material).count(6) != 2
        or len(material) != 3
        or not any(side == value.mating_side and kind in (4, 5) for _, side, kind in material)
    ):
        _reject(C.CHESS_PREDICATE_TREE)
    states, depths, _ = _tree_states(value.root, value.nodes)
    leaves: list[int] = []
    for index, (node, state) in enumerate(zip(value.nodes, states, strict=True)):
        terminal = board_terminal(state)
        if terminal.code != C.BOARD_TERMINAL_NONE:
            if node.edges:
                _reject(C.CHESS_PREDICATE_TREE)
            leaves.append(index)
        elif state.position.side_to_move == value.mating_side:
            if len(node.edges) != 1:
                _reject(C.CHESS_PREDICATE_TREE)
        elif tuple(edge.move for edge in node.edges) != legal_moves(state):
            _reject(C.CHESS_PREDICATE_TREE)
    all_mate = all(
        board_terminal(states[index]) == BoardTerminal(C.BOARD_TERMINAL_CHECKMATE, value.mating_side)
        for index in leaves
    )
    return FiniteMatingResult(value.mating_side, all_mate, max(depths[index] for index in leaves))


def _history_claim(replay: ReplayState) -> HistoryClaimResult:
    nominal = replay.position.nominal_en_passant
    key = repetition_key(replay)
    effective = key[66]
    threefold, fifty = _claims(replay)
    return HistoryClaimResult(
        EnPassantFact(None if nominal == 0 else nominal - 1),
        EnPassantFact(None if effective == 0 else effective - 1),
        replay._keys.count(key),
        replay.halfmove_clock,
        replay.played_plies,
        threefold,
        fifty,
    )


def evaluate_predicate(predicate_id: bytes, value: object) -> object:
    if (
        type(predicate_id) is not bytes
        or len(predicate_id) not in {len(identifier) for identifier in _PREDICATE_TYPES}
        or predicate_id not in _PREDICATE_TYPES
    ):
        _reject(C.CHESS_PREDICATE_UNKNOWN)
    if type(value) not in _PREDICATE_TYPES[predicate_id]:
        _reject(C.CHESS_PREDICATE_SIGNATURE)
    if isinstance(value, SetupInitialInput):
        _predicate_signature(type(value.position) is WirePosition)
        return value.position._bytes == _INITIAL_BYTES
    if isinstance(value, SetupCurrentSideInput):
        _predicate_signature(
            type(value.replay) is ReplayState
            and type(value.side) is int
            and value.side in _VALID_SIDES
        )
        return value.replay.position.side_to_move == value.side
    if isinstance(value, OccupancyInput):
        _predicate_signature(type(value.position) is WirePosition and 0 <= value.square < 64 and type(value.match) is OccupancyMatch)
        code = value.position._bytes[value.square]
        if value.match.kind == "empty":
            _predicate_signature(value.match.side is None and value.match.piece is None)
            return code == C.SQUARE_EMPTY
        if value.match.kind == "occupied":
            _predicate_signature(value.match.side is None and value.match.piece is None)
            return code != C.SQUARE_EMPTY
        _predicate_signature(
            value.match.kind == "exact"
            and type(value.match.side) is int
            and value.match.side in _VALID_SIDES
            and type(value.match.piece) is int
            and 1 <= value.match.piece <= 6
        )
        return code == _square_code(value.match.side, value.match.piece)
    if isinstance(value, MoveLegalityInput):
        _predicate_signature(type(value.replay) is ReplayState and type(value.move) is Move)
        try:
            apply_move(value.replay, value.move)
        except ChessReject as error:
            return MoveLegalityResult("illegal", error.code)
        return MoveLegalityResult("legal")
    if isinstance(value, ControlInput):
        _predicate_signature(
            type(value.position) is WirePosition
            and type(value.side) is int
            and value.side in _VALID_SIDES
            and type(value.target) is int
            and 0 <= value.target < 64
        )
        return controls_square(value.position, value.side, value.target)
    if isinstance(value, DefendedInput):
        _predicate_signature(
            type(value.position) is WirePosition
            and type(value.target) is int
            and 0 <= value.target < 64
            and type(value.defender) is Defender
        )
        code = value.position._bytes[value.target]
        if code == C.SQUARE_EMPTY:
            return False
        origins = tuple(origin for origin in controls_square(value.position, _piece_side(code), value.target) if origin != value.target)
        if value.defender.kind == "any":
            _predicate_signature(value.defender.square is None)
            return bool(origins)
        _predicate_signature(value.defender.kind == "exact" and type(value.defender.square) is int and 0 <= value.defender.square < 64)
        return value.defender.square in origins
    if isinstance(value, KingCheckInput):
        _predicate_signature(
            type(value.position) is LocallyAdmissiblePosition
            and type(value.side) is int
            and value.side in _VALID_SIDES
        )
        return king_in_check(value.position, value.side)
    if isinstance(value, AbsolutePinInput):
        _predicate_signature(
            type(value.position) is LocallyAdmissiblePosition
            and type(value.origin) is int
            and 0 <= value.origin < 64
        )
        return _absolute_pin(value)
    if isinstance(value, ForkDoubleAttackInput):
        _predicate_signature(type(value.replay) is ReplayState and type(value.move) is Move)
        return _fork(value)
    if isinstance(value, DiscoveredLineInput):
        _predicate_signature(type(value.replay) is ReplayState and type(value.move) is Move)
        if board_terminal(value.replay).code != C.BOARD_TERMINAL_NONE:
            _reject(C.CHESS_GAME_CLOSED)
        _predicate_signature(
            type(value.slider_origin) is int
            and 0 <= value.slider_origin < 64
            and type(value.target) is int
            and 0 <= value.target < 64
        )
        return _discovered(value)
    if isinstance(value, EscapeControlInput):
        _predicate_signature(
            type(value.position) is WirePosition
            and type(value.controlling_side) is int
            and value.controlling_side in _VALID_SIDES
            and type(value.candidate) is int
            and 0 <= value.candidate < 64
        )
        return bool(controls_square(value.position, value.controlling_side, value.candidate))
    if isinstance(value, PassedPawnInput):
        _predicate_signature(
            type(value.position) is LocallyAdmissiblePosition
            and type(value.pawn_square) is int
            and 0 <= value.pawn_square < 64
        )
        return _passed_pawn(value)
    if isinstance(value, OpenFileInput):
        _predicate_signature(type(value.position) is WirePosition and type(value.file) is int and 0 <= value.file < 8)
        return all(_piece_kind(value.position._bytes[square]) != 1 for square in range(value.file, 64, 8))
    if isinstance(value, SemiOpenFileInput):
        _predicate_signature(
            type(value.position) is WirePosition
            and type(value.side) is int
            and value.side in _VALID_SIDES
            and type(value.file) is int
            and 0 <= value.file < 8
        )
        pawns = tuple(_piece_side(value.position._bytes[square]) for square in range(value.file, 64, 8) if _piece_kind(value.position._bytes[square]) == 1)
        return value.side not in pawns and 1 - value.side in pawns
    if isinstance(value, FinitePromotionTree):
        _predicate_signature(type(value.root) is ReplayState)
        return _promotion_tree(value)
    if isinstance(value, FiniteMatingTree):
        _predicate_signature(type(value.root) is ReplayState)
        return _mating_tree(value)
    if isinstance(value, TerminalTransitionInput):
        _predicate_signature(type(value.replay) is ReplayState and type(value.move) is Move)
        return board_terminal(apply_move(value.replay, value.move))
    if isinstance(value, HistoryClaimInput):
        _predicate_signature(type(value.replay) is ReplayState)
        return _history_claim(value.replay)
    if isinstance(value, DeclarationEventInput):
        _predicate_signature(type(value.game) is GameState and type(value.event) is Event)
        try:
            game = apply_event(value.game, value.event)
        except ChessReject as error:
            return DeclarationEventResult("rejected", code=error.code)
        return DeclarationEventResult("accepted", game.status, game.closure_cause, game.score)
    if isinstance(value, SourceScoreInput):
        if type(value.moves) is tuple and len(value.moves) > C.MAX_HISTORY_PLIES:
            _reject(C.CHESS_RESOURCE_PREDICATE_INPUT)
        _predicate_signature(
            type(value.moves) is tuple
            and all(type(move) is Move for move in value.moves[: C.MAX_HISTORY_PLIES + 1])
            and type(value.score) is int
            and value.score in (C.SCORE_FIRST_WIN, C.SCORE_SECOND_WIN, C.SCORE_DRAW)
        )
        try:
            record = validate_source_record(value.moves, value.score)
        except ChessReject as error:
            return SourceScoreResult("rejected", code=error.code)
        return SourceScoreResult("accepted", record.board_terminal)
    if isinstance(value, MoveBytesInput):
        _predicate_signature(type(value.data) is bytes)
        try:
            move = decode_move(value.data)
        except ChessReject as error:
            return MoveRecordResult("rejected", code=error.code)
        return MoveRecordResult("decoded", move=move)
    if isinstance(value, MoveRecordInput):
        if type(value.moves) is tuple and len(value.moves) > C.MAX_HISTORY_PLIES:
            _reject(C.CHESS_RESOURCE_PREDICATE_INPUT)
        _predicate_signature(
            type(value.moves) is tuple
            and all(type(move) is Move for move in value.moves[: C.MAX_HISTORY_PLIES + 1])
            and type(value.score) is int
            and value.score in (C.SCORE_FIRST_WIN, C.SCORE_SECOND_WIN, C.SCORE_DRAW)
        )
        try:
            record = validate_source_record(value.moves, value.score)
        except ChessReject as error:
            return MoveRecordResult("rejected", code=error.code)
        return MoveRecordResult("replayed", record=record)
    raise AssertionError("closed predicate dispatch")
