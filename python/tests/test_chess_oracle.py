"""Isolated diagnostic overlap with pinned python-chess."""

import unittest

import chess

from golden_board import chess as gb
from golden_board import constants as C


_STALEMATE_HEX = (
    "3140c2000e70e2809e00de708320a2f03df0d6d0cb30f350cf10ed30c7904f70"
    "e7a0d6e0eac0"
)


def _project_move(uci: str) -> object:
    def square(name: str) -> int:
        return ord(name[0]) - ord("a") + 8 * (ord(name[1]) - ord("1"))

    promotion = {
        "": C.PROMOTION_NONE,
        "q": C.PROMOTION_QUEEN,
        "r": C.PROMOTION_ROOK,
        "b": C.PROMOTION_BISHOP,
        "n": C.PROMOTION_KNIGHT,
    }[uci[4:]]
    word = (
        (square(uci[:2]) << C.CHESS_MOVE_ORIGIN_SHIFT)
        | (square(uci[2:4]) << C.CHESS_MOVE_DESTINATION_SHIFT)
        | promotion
    )
    return gb.decode_move(word.to_bytes(2, "big"))


def _oracle_move(move: object) -> chess.Move:
    promotion = {
        C.PROMOTION_NONE: None,
        C.PROMOTION_QUEEN: chess.QUEEN,
        C.PROMOTION_ROOK: chess.ROOK,
        C.PROMOTION_BISHOP: chess.BISHOP,
        C.PROMOTION_KNIGHT: chess.KNIGHT,
    }[move.promotion]
    return chess.Move(move.origin, move.destination, promotion=promotion)


def _decoded_history(raw_hex: str) -> tuple[object, ...]:
    raw = bytes.fromhex(raw_hex)
    return tuple(gb.decode_move(raw[index:index + 2]) for index in range(0, len(raw), 2))


def _project_rights(board: chess.Board) -> int:
    rights = 0
    if board.has_kingside_castling_rights(chess.WHITE):
        rights |= C.CASTLING_FIRST_KINGSIDE
    if board.has_queenside_castling_rights(chess.WHITE):
        rights |= C.CASTLING_FIRST_QUEENSIDE
    if board.has_kingside_castling_rights(chess.BLACK):
        rights |= C.CASTLING_SECOND_KINGSIDE
    if board.has_queenside_castling_rights(chess.BLACK):
        rights |= C.CASTLING_SECOND_QUEENSIDE
    return rights


def _oracle_occupancy(board: chess.Board) -> bytes:
    return bytes(
        0 if (piece := board.piece_at(square)) is None else piece.piece_type + 6 * (not piece.color)
        for square in range(64)
    )


class ChessOracle(unittest.TestCase):
    def test_pinned_oracle_is_present(self) -> None:
        self.assertEqual(chess.__version__, "1.11.2")

    def test_normalized_overlap_only(self) -> None:
        knight_cycle = tuple(map(_project_move, ("g1f3", "g8f6", "f3g1", "f6g8")))
        scenarios = {
            "ordinary-castle": tuple(map(_project_move, (
                "e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6",
                "b5a4", "g8f6", "e1g1",
            ))),
            "en-passant": tuple(map(_project_move, (
                "g1f3", "d7d5", "f3g1", "d5d4", "e2e4", "d4e3",
            ))),
            "checkmate": tuple(map(_project_move, ("f2f3", "e7e5", "g2g4", "d8h4"))),
            "stalemate": _decoded_history(_STALEMATE_HEX),
            "repetition-halfmove-reset": knight_cycle * 25 + (_project_move("e2e4"),),
        }
        for name, moves in scenarios.items():
            board = chess.Board()
            for plies in range(len(moves) + 1):
                with self.subTest(scenario=name, plies=plies):
                    replay = gb.replay_from_start(moves[:plies])
                    position = gb.encode_position(replay.position)
                    self.assertEqual(position[:64], _oracle_occupancy(board))
                    self.assertEqual(position[64], C.SIDE_FIRST if board.turn else C.SIDE_SECOND)
                    self.assertEqual(position[65], _project_rights(board))
                    self.assertEqual(
                        position[66],
                        C.EN_PASSANT_NONE if board.ep_square is None else board.ep_square + 1,
                    )
                    self.assertEqual(
                        {str(_oracle_move(move)) for move in gb.legal_moves(replay)},
                        {str(move) for move in board.legal_moves},
                    )
                    local = gb.validate_local(replay.position)
                    side = C.SIDE_FIRST if board.turn else C.SIDE_SECOND
                    self.assertEqual(gb.king_in_check(local, side), board.is_check())
                    terminal = gb.board_terminal(replay).code
                    self.assertEqual(terminal == 1, board.is_checkmate())
                    self.assertEqual(terminal == 2, board.is_stalemate())
                    history = gb.evaluate_predicate(
                        b"chess.history_claim", gb.HistoryClaimInput(replay)
                    )
                    occurrences = max(
                        count for count in range(1, plies + 2) if board.is_repetition(count)
                    )
                    self.assertEqual(history.current_key_occurrences, occurrences)
                    self.assertEqual(history.halfmove_clock, board.halfmove_clock)
                    self.assertEqual(history.threefold_available, board.is_repetition(3))
                if plies < len(moves):
                    move = _oracle_move(moves[plies])
                    self.assertIn(move, board.legal_moves)
                    board.push(move)


if __name__ == "__main__":
    unittest.main()
