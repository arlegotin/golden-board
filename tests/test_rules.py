"""Hand-derived boundaries for the selected practical profile, not tournament law."""
from pathlib import Path
import unittest

from golden_board.rules import Replay, local_controls


def played(text):
    replay = Replay()
    for move in text.split():
        replay.play(move)
    return replay


def snapshot(replay):
    return (replay.fen, replay.moves, replay.legal_moves, replay.events,
            replay.side_to_move, replay.halfmove_clock, replay.repetition_key,
            replay.repetition_count, replay.available_claims, replay.outcome, replay.closed)


CYCLE = 'g1f3 g8f6 f3g1 f6g8 '


class RuleTests(unittest.TestCase):
    def test_initial_legal_moves_and_illegal_move_is_atomic(self):
        replay = Replay()
        self.assertEqual(len(replay.legal_moves), 20)
        before = replay.fen
        for move in ('e2e5', 'a9a1', 'e2e4q', 'E2E4', 'e2e4 ', '0000'):
            with self.subTest(move=move), self.assertRaises(ValueError):
                replay.play(move)
            self.assertEqual(replay.fen, before)
            self.assertEqual(replay.moves, ())

    def test_pinned_knight_controls_squares_it_cannot_move_to(self):
        replay = played('e2e4 e7e5 g1f3 b8c6 f1b5 d7d6 a2a3')
        self.assertEqual(local_controls(replay.fen, 'c6'),
                         {'a5', 'a7', 'b4', 'b8', 'd4', 'd8', 'e5', 'e7'})
        self.assertFalse(any(move.startswith('c6') for move in replay.legal_moves))

    def test_king_cannot_capture_bishop_defended_by_open_queen_line(self):
        replay = played('e2e4 d7d5 d2d3 d5e4 d3e4 e7e6 g1f3 f8b4 c1d2 b4d2')
        before = replay.fen
        with self.assertRaises(ValueError):
            replay.play('e1d2')
        self.assertEqual(replay.fen, before)

    def test_castling_moves_rook_and_rejects_attacked_transit(self):
        replay = played('e2e4 e7e5 g1f3 b8c6 f1c4 f8c5 e1g1')
        self.assertEqual(replay.fen.split()[0].split('/')[-1], 'RNBQ1RK1')
        self.assertEqual(replay.fen.split()[1:3], ['b', 'kq'])
        transit = played('g2g3 b7b6 f1g2 c8a6 g1f3 e7e6 e2e4 b8c6')
        self.assertIn('f1', local_controls(transit.fen, 'a6'))
        with self.assertRaises(ValueError):
            transit.play('e1g1')

    def test_en_passant_removes_captured_pawn_and_self_check_is_illegal(self):
        replay = played('e2e4 a7a6 e4e5 d7d5 e5d6')
        self.assertEqual(replay.fen.split()[0],
                         'rnbqkbnr/1pp1pppp/p2P4/8/8/8/PPPP1PPP/RNBQKBNR')
        pinned = played('e2e4 e7e6 f2f4 g8f6 f4f5 e6f5 e4e5 f6g4 '
                        'g1f3 f8e7 d2d4 e8g8 b1c3 f8e8 f1d3 e7f8 d1d2 d7d5')
        self.assertNotIn('e5d6', pinned.legal_moves)
        before = pinned.fen
        with self.assertRaises(ValueError):
            pinned.play('e5d6')
        self.assertEqual(pinned.fen, before)

    def test_all_promotions_require_explicit_choice(self):
        prefix = 'a2a4 h7h5 a4a5 h5h4 a5a6 h4h3 a6b7 h3g2'
        for suffix, piece in [('q', 'Q'), ('r', 'R'), ('b', 'B'), ('n', 'N')]:
            with self.subTest(suffix=suffix):
                replay = played(prefix)
                with self.assertRaises(ValueError):
                    replay.play('b7a8')
                replay.play('b7a8' + suffix)
                self.assertTrue(replay.fen.startswith(piece + 'nbqkbnr/'))

    def test_local_diagram_rejects_invalid_state_and_square(self):
        with self.assertRaises(ValueError):
            local_controls('8/8/8/8/8/8/8/8 w - - 0 1', 'a1')
        with self.assertRaises(ValueError):
            local_controls(Replay().fen, 'a9')


class PracticalRuleTests(unittest.TestCase):
    def rejected(self, replay, operation, *args):
        before = snapshot(replay)
        with self.assertRaises(ValueError):
            operation(*args)
        self.assertEqual(snapshot(replay), before)

    def assert_closed(self, replay, score, reason):
        self.assertTrue(replay.closed)
        self.assertEqual((replay.outcome.score, replay.outcome.reason), (score, reason))
        self.assertEqual(replay.legal_moves, ())
        self.assertEqual(replay.available_claims, ())
        self.rejected(replay, replay.play, 'g1f3')
        self.rejected(replay, replay.resign, 0)
        self.rejected(replay, replay.agree_draw, [0, 1])
        self.rejected(replay, replay.claim_draw, replay.side_to_move, 'threefold')

    def test_current_third_occurrence_not_prospective_claim(self):
        replay = Replay()
        self.assertEqual(replay.repetition_count, 1)
        self.assertEqual(replay.side_to_move, 0)
        self.assertEqual(replay.available_claims, ())
        for move in (CYCLE * 2).split()[:-1]:
            replay.play(move)
        self.assertEqual(replay.repetition_count, 2)
        self.assertEqual(replay.side_to_move, 1)
        self.rejected(replay, replay.claim_draw, 1, 'threefold')
        replay.play('f6g8')
        self.assertEqual(replay.repetition_count, 3)
        self.assertEqual(replay.available_claims, ('threefold',))
        self.rejected(replay, replay.claim_draw, 1, 'threefold')
        replay.claim_draw(0, 'threefold')
        self.assertEqual(replay.events[-1], ('claim', 0, 'threefold'))
        self.assert_closed(replay, 2, 'threefold')

    def test_current_clock_boundary_resets_and_excluded_automatic_endings(self):
        replay = played(' '.join((CYCLE * 25).split()[:-1]))
        self.assertEqual(replay.halfmove_clock, 99)
        self.rejected(replay, replay.claim_draw, 1, 'fifty-move')
        replay.play('f6g8')
        self.assertEqual(replay.halfmove_clock, 100)
        self.assertEqual(replay.available_claims, ('threefold', 'fifty-move'))
        replay.claim_draw(0, 'fifty-move')
        self.assert_closed(replay, 2, 'fifty-move')

        continuing = played(CYCLE * 40)
        self.assertEqual(continuing.halfmove_clock, 160)
        self.assertEqual(continuing.repetition_count, 41)
        self.assertFalse(continuing.closed)
        continuing.play('e2e4')
        self.assertEqual(continuing.halfmove_clock, 0)
        self.assertEqual(continuing.repetition_count, 1)
        capture = played('e2e4 e7e5 g1f3 b8c6 f1b5 g8f6')
        self.assertEqual(capture.halfmove_clock, 4)
        capture.play('b5c6')
        self.assertEqual(capture.halfmove_clock, 0)

    def test_mate_has_priority_and_current_claim_can_be_made_in_check(self):
        first_side_mate = played('e2e4 f7f6 d2d4 g7g5 d1h5')
        self.assert_closed(first_side_mate, 0, 'checkmate')
        mate = played('f2f3 e7e5 g2g4 ' + 'b8c6 b1c3 c6b8 c3b1 ' * 25)
        self.assertIn('fifty-move', mate.available_claims)
        mate.play('d8h4')
        self.assertEqual(mate.halfmove_clock, 101)
        self.assert_closed(mate, 1, 'checkmate')
        checked = played('f2f3 e7e5 ' + 'b1c3 b8c6 c3b1 c6b8 ' * 25 + 'b1c3 d8h4')
        self.assertIn('e1', local_controls(checked.fen, 'h4'))
        self.assertTrue(checked.legal_moves)
        self.assertIn('fifty-move', checked.available_claims)
        checked.claim_draw(0, 'fifty-move')
        self.assert_closed(checked, 2, 'fifty-move')

    def test_repetition_ignores_unusable_and_pinned_ep_but_keeps_legal_ep(self):
        absent = played('e2e4')
        self.assertEqual(absent.fen.split()[3], 'e3')
        initial_key = absent.repetition_key
        for move in 'g8f6 g1f3 f6g8 f3g1'.split():
            absent.play(move)
        self.assertEqual(absent.fen.split()[3], '-')
        self.assertEqual(absent.repetition_key, initial_key)
        self.assertEqual(absent.repetition_count, 2)

        legal = played('e2e4 a7a6 e4e5 d7d5')
        initial_key = legal.repetition_key
        self.assertIn('e5d6', legal.legal_moves)
        for move in CYCLE.split():
            legal.play(move)
        self.assertNotEqual(legal.repetition_key, initial_key)
        self.assertEqual(legal.repetition_count, 1)
        self.rejected(legal, legal.play, 'e5d6')
        for move in CYCLE.split():
            legal.play(move)
        self.assertEqual(legal.repetition_count, 2)

        pinned = played('e2e4 e7e6 f2f4 g8f6 f4f5 e6f5 e4e5 f6g4 '
                        'g1f3 f8e7 d2d4 e8g8 b1c3 f8e8 f1d3 e7f8 d1d2 d7d5')
        self.assertEqual(pinned.fen.split()[3], 'd6')
        self.assertNotIn('e5d6', pinned.legal_moves)
        initial_key = pinned.repetition_key
        for move in 'c3b1 g4f6 b1c3 f6g4'.split():
            pinned.play(move)
        self.assertEqual(pinned.repetition_key, initial_key)
        self.assertEqual(pinned.repetition_count, 2)

    def test_repetition_distinguishes_lost_rights_and_side_to_move(self):
        initial = Replay().repetition_key
        rights = played('g1f3 g8f6 h1g1 f6g8 g1h1 g8f6 f3g1 f6g8')
        self.assertEqual(rights.fen.split()[0], Replay().fen.split()[0])
        self.assertNotEqual(rights.repetition_key, initial)
        self.assertEqual(rights.repetition_count, 1)
        for move in CYCLE.split():
            rights.play(move)
        self.assertEqual(rights.repetition_count, 2)

        side = played('f2f3 a7a6 e2e4 a6a5 e1e2 g8f6 e2e1 f6g8')
        initial_key = side.repetition_key
        initial_board = side.fen.split()[0]
        for move in 'e1e2 g8f6 e2f2 f6g8 f2e1'.split():
            side.play(move)
        self.assertEqual(side.fen.split()[0], initial_board)
        self.assertNotEqual(side.repetition_key, initial_key)
        self.assertEqual(side.repetition_count, 1)

    def test_declarations_are_explicit_atomic_and_require_valid_roles(self):
        replay = Replay()
        for actor in (True, False, None, '0', 0.0, -1, 2, [], {}):
            self.rejected(replay, replay.resign, actor)
            self.rejected(replay, replay.claim_draw, actor, 'threefold')
        for reason in (None, [], {}, 'THREEFOLD', 'agreement', 'fifty-moves'):
            self.rejected(replay, replay.claim_draw, 0, reason)
        for consenting in (None, 0, '01', {0, 1}, {0: 1}, [], [0], [0, 0],
                           [1, 1], [False, 1], [0, 1.0], [0, 2], [0, 1, 0]):
            self.rejected(replay, replay.agree_draw, consenting)
        self.rejected(replay, replay.agree_draw, [0, 1])
        replay.play('e2e4')
        self.rejected(replay, replay.agree_draw, (0, 1))
        replay.play('e7e5')
        replay.agree_draw([1, 0])
        self.assertEqual(replay.events, (('move', 'e2e4'), ('move', 'e7e5'), ('agree', 0, 1)))
        self.assert_closed(replay, 2, 'agreement')
        with self.assertRaises(AttributeError):
            replay.outcome.score = 0
        for actor in (0, 1):
            with self.subTest(actor=actor):
                resigning = Replay()
                resigning.resign(actor)
                self.assertEqual(resigning.events, (('resign', actor),))
                self.assert_closed(resigning, 1 - actor, 'resignation')

    def test_stalemate_from_complete_standard_start_history(self):
        replay = played('e2e3 a7a5 d1h5 a8a6 h5a5 h7h5 a5c7 a6h6 h2h4 f7f6 '
                        'c7d7 e8f7 d7b7 d8d3 b7b8 d3h7 b8c8 f7g6 c8e6')
        self.assert_closed(replay, 2, 'stalemate')

    def test_common_dead_closed_classes_and_outside_profile_are_distinct(self):
        from golden_board.rules import local_deadness
        for board in ('7k/8/8/8/8/8/8/K7', '7k/8/8/8/8/8/8/KB6',
                      '7k/8/8/8/8/8/8/KN6', '1b5k/8/8/8/8/8/8/K7',
                      '1n5k/8/8/8/8/8/8/K7'):
            with self.subTest(board=board):
                self.assertEqual(local_deadness(board + ' w - - 0 1'), 'common-dead')
        for board in ('5b1k/8/8/8/8/8/8/K1B5', '7k/8/8/8/8/8/8/KNN5',
                      '7k/8/8/8/8/8/8/KR6', '7k/8/8/8/8/8/P7/K7'):
            with self.subTest(board=board):
                self.assertEqual(local_deadness(board + ' w - - 0 1'), 'outside-profile')
        with self.assertRaises(ValueError):
            local_deadness('8/8/8/8/8/8/8/8 w - - 0 1')

    def test_common_dead_closes_coherent_source_prefix_plus_explicit_test_tail(self):
        from golden_board.source import source_spans
        from golden_board.source_game import parse_mainline
        root = Path(__file__).resolve().parents[1]
        span = source_spans(root)['records'][44]
        game = parse_mainline((root / 'inputs/anthology.pgn').read_bytes()[span['start']:span['end']])
        def square(index):
            return chr(97 + index % 8) + str(8 - index // 8)
        for tail in ('b3b4 h3b3 b4b3', 'b3b4 h3a3 b4b5 a3a4 b5a4'):
            with self.subTest(tail=tail):
                replay = Replay()
                for start, end, promotion in game['moves']:
                    replay.play(square(start) + square(end) + ('', 'q', 'r', 'b', 'n')[promotion])
                self.assertFalse(replay.closed)  # Source score does not declare a cause.
                for move in tail.split():
                    replay.play(move)
                self.assert_closed(replay, 2, 'common-dead')

    def test_both_castlings_both_colors_and_orthodox_rook_updates(self):
        short = played('e2e4 e7e5 g1f3 g8f6 f1c4 f8c5 e1g1 e8g8')
        self.assertEqual(short.fen.split()[0],
                         'rnbq1rk1/pppp1ppp/5n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQ1RK1')
        long = played('d2d4 d7d5 b1c3 b8c6 c1f4 c8f5 d1d2 d8d7 e1c1 e8c8')
        self.assertEqual(long.fen.split()[0],
                         '2kr1bnr/pppqpppp/2n5/3p1b2/3P1B2/2N5/PPPQPPPP/2KR1BNR')
        self.assertEqual(short.fen.split()[2], '-')
        self.assertEqual(long.fen.split()[2], '-')

    def test_castling_requires_safe_king_path_but_not_safe_rook_or_b_file(self):
        for prefix, attacker, target in (
            ('e2e4 e7e5 g1h3 b8c6 f1c4 a7a6 f2f3 d8h4', 'h4', 'e1'),
            ('g2g3 b7b6 f1g2 c8a6 g1f3 e7e6 e2e4 b8c6', 'a6', 'f1'),
            ('e2e4 e7e5 g1h3 b8c6 f1c4 f8c5 f2f3 g8f6', 'c5', 'g1')):
            with self.subTest(target=target):
                replay = played(prefix)
                self.assertIn(target, local_controls(replay.fen, attacker))
                self.rejected(replay, replay.play, 'e1g1')
        blocked = played('d2d4 d7d5 c1f4 c8f5 d1d2 d8d7')
        self.rejected(blocked, blocked.play, 'e1c1')  # b1 still occupied.
        for prefix, attacker, target in (
            ('d2d4 d7d5 c2c4 c8f5 b1c3 b8c6 c1f4 d8d7 d1d2 g8f6', 'f5', 'b1'),
            ('a2a4 b7b5 a4b5 a7a6 d2d4 a6b5 b1c3 g8f6 c1f4 f6g8 d1d2 g8f6', 'a8', 'a1')):
            replay = played(prefix)
            self.assertIn(target, local_controls(replay.fen, attacker))
            replay.play('e1c1')
            self.assertTrue(replay.fen.split()[0].endswith('2KR1BNR'))

    def test_ep_expires_and_second_side_promotions_clear_captured_rook_rights(self):
        expired = played('e2e4 a7a6 e4e5 d7d5 g1f3 a6a5')
        self.rejected(expired, expired.play, 'e5d6')
        prefix = 'a2a4 h7h5 a4a5 h5h4 a5a6 h4h3 a6b7 h3g2 b7a8q'
        for suffix, piece in (('q', 'q'), ('r', 'r'), ('b', 'b'), ('n', 'n')):
            with self.subTest(suffix=suffix):
                replay = played(prefix)
                self.rejected(replay, replay.play, 'g2h1')
                replay.play('g2h1' + suffix)
                self.assertTrue(replay.fen.split()[0].endswith('RNBQKBN' + piece))
                self.assertEqual(replay.fen.split()[2], 'Qk')


if __name__ == '__main__':
    unittest.main()
