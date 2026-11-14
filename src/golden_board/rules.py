"""Coherent replay for the explicitly selected practical orthodox profile."""
from collections import Counter
from dataclasses import dataclass
import re

import chess


@dataclass(frozen=True)
class Outcome:
    score: int
    reason: str


def _common_dead(board: chess.Board) -> bool:
    nonkings = [piece for piece in board.piece_map().values() if piece.piece_type != chess.KING]
    return not nonkings or (len(nonkings) == 1 and
                            nonkings[0].piece_type in (chess.BISHOP, chess.KNIGHT))


def board_ending(board: chess.Board) -> str:
    """Selected policy on a coherent valid board, shared with strict source import."""
    if board.is_checkmate():
        return 'checkmate'
    if board.is_stalemate():
        return 'stalemate'
    if _common_dead(board):
        return 'common-dead'
    return 'active'


def _role(actor) -> None:
    if type(actor) is not int or actor not in (0, 1):
        raise ValueError('A side must be the exact integer 0 or 1.')


class Replay:
    """A coherent standard-start replay; arbitrary boards cannot be injected."""

    def __init__(self):
        self._board = chess.Board()
        self._outcome = None
        self._events = []
        self._occurrences = Counter({self.repetition_key: 1})

    @property
    def outcome(self) -> Outcome | None:
        return self._outcome

    @property
    def closed(self) -> bool:
        return self._outcome is not None

    @property
    def events(self) -> tuple:
        return tuple(self._events)

    @property
    def side_to_move(self) -> int:
        return 0 if self._board.turn else 1

    @property
    def halfmove_clock(self) -> int:
        return self._board.halfmove_clock

    @property
    def repetition_key(self) -> tuple:
        return (self._board.board_fen(), self.side_to_move, self._board.castling_rights,
                self._board.ep_square if self._board.has_legal_en_passant() else None)

    @property
    def repetition_count(self) -> int:
        return self._occurrences[self.repetition_key]

    @property
    def available_claims(self) -> tuple[str, ...]:
        if self.closed:
            return ()
        return tuple(reason for reason, eligible in (
            ('threefold', self.repetition_count >= 3),
            ('fifty-move', self.halfmove_clock >= 100)) if eligible)

    @property
    def fen(self) -> str:
        return self._board.fen(en_passant='fen')

    @property
    def moves(self) -> tuple[str, ...]:
        return tuple(move.uci() for move in self._board.move_stack)

    @property
    def legal_moves(self) -> tuple[str, ...]:
        if self.closed:
            return ()
        return tuple(sorted(move.uci() for move in self._board.legal_moves))

    def _require_active(self) -> None:
        if self.closed:
            raise ValueError('The replay is closed.')

    def play(self, move: str) -> None:
        self._require_active()
        if not isinstance(move, str) or not re.fullmatch(r'[a-h][1-8][a-h][1-8][qrbn]?', move):
            raise ValueError(f'Invalid coordinate move {move!r}; promotion must be explicit.')
        parsed = chess.Move.from_uci(move)
        if parsed not in self._board.legal_moves:
            raise ValueError(f'Illegal move {move!r} at ply {len(self._board.move_stack) + 1}.')
        self._board.push(parsed)
        self._occurrences[self.repetition_key] += 1
        self._events.append(('move', move))
        ending = board_ending(self._board)
        if ending != 'active':
            score = 1 - self.side_to_move if ending == 'checkmate' else 2
            self._outcome = Outcome(score, ending)

    def claim_draw(self, actor: int, reason: str) -> None:
        self._require_active()
        _role(actor)
        if (actor != self.side_to_move or not isinstance(reason, str)
                or reason not in self.available_claims):
            raise ValueError('Only the side to move can claim an eligible current-state draw.')
        self._outcome = Outcome(2, reason)
        self._events.append(('claim', actor, reason))

    def resign(self, actor: int) -> None:
        self._require_active()
        _role(actor)
        self._outcome = Outcome(1 - actor, 'resignation')
        self._events.append(('resign', actor))

    def agree_draw(self, consenting_sides) -> None:
        self._require_active()
        if not isinstance(consenting_sides, (list, tuple)) or len(consenting_sides) != 2:
            raise ValueError('Agreement requires a list or tuple with both explicit consents.')
        for actor in consenting_sides:
            _role(actor)
        if consenting_sides[0] == consenting_sides[1] or len(self._board.move_stack) < 2:
            raise ValueError('Agreement requires both sides to consent after both have moved.')
        self._outcome = Outcome(2, 'agreement')
        self._events.append(('agree', 0, 1))


def _local_board(fen: str) -> chess.Board:
    if not isinstance(fen, str):
        raise ValueError('A local diagram requires a diagnostic FEN string.')
    board = chess.Board(fen)
    if not board.is_valid():
        raise ValueError(f'Invalid local board state: status {board.status()}.')
    return board


def local_deadness(fen: str) -> str:
    """Closed common classes only; other diagrams receive no general verdict."""
    return 'common-dead' if _common_dead(_local_board(fen)) else 'outside-profile'


def local_controls(fen: str, origin: str) -> set[str]:
    """Geometric control only; does not establish reachability or history."""
    board = _local_board(fen)
    square = chess.parse_square(origin)
    return {chess.square_name(target) for target in board.attacks(square)}
