"""Independent Python evidence for chess-v0."""

from __future__ import annotations

import importlib
import hashlib
import io
import json
from pathlib import Path
import random
import unittest
from unittest import mock

from golden_board import canonical_manifest
from golden_board import constants as C


ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_BYTE_CAP = canonical_manifest.MAX_BYTES
_RECIPE_FACTS = {
    "history-boundary-4095": (
        4095, "", 8190, "fe083157aff7dddf8ef1d7c55d14d74836351de95367107f2382c465ba670735",
        {"success": {"played_plies": 4095}},
    ),
    "history-boundary-4096": (
        4096, "", 8192, "39b9ad3d90be853994abbf8fba476816fcc15865f9fdf99f26a33673e0972616",
        {"success": {"played_plies": 4096}},
    ),
    "history-excess-4097": (
        4097, "4180", 8194, "b2b5803f901288658064cbd1c05ff36db5b6fe73f99d68941e85178b968c5abc",
        {"rejection": 35},
    ),
}


def _load_fixture(path: Path) -> object:
    with path.open("rb") as source:
        raw = source.read(_FIXTURE_BYTE_CAP + 1)
    if len(raw) > _FIXTURE_BYTE_CAP:
        raise ValueError("chess fixture exceeds repository byte cap")
    return canonical_manifest.validate_canonical_manifest(raw)


def _decode_moves(chess: object, raw: bytes) -> tuple[object, ...]:
    return tuple(chess.decode_move(raw[index : index + 2]) for index in range(0, len(raw), 2))


def _recipe_moves(chess: object, recipe: object) -> tuple[object, ...]:
    if type(recipe) is not dict or set(recipe) != {
        "count_cap", "expected", "input", "input_bytes", "input_sha256", "name", "recipe",
    }:
        raise AssertionError("closed recipe record")
    name = recipe["name"]
    if type(name) is not str or name not in _RECIPE_FACTS:
        raise AssertionError("closed recipe name")
    expected_count, expected_final, expected_bytes, expected_digest, expected_result = _RECIPE_FACTS[name]
    data = recipe["input"]
    if (
        type(recipe["recipe"]) is not str
        or recipe["recipe"] != "knight-cycle-history"
        or type(recipe["count_cap"]) is not int
        or recipe["count_cap"] != 4097
        or type(data) is not dict
        or set(data) != {"cycle_moves_hex", "final_move_hex", "ply_count"}
        or type(recipe["input_bytes"]) is not int
        or type(recipe["input_sha256"]) is not str
        or type(recipe["expected"]) is not dict
    ):
        raise AssertionError("closed recipe shape")
    count = data["ply_count"]
    cycle_hex = data["cycle_moves_hex"]
    final_hex = data["final_move_hex"]
    result = recipe["expected"]
    if "success" in expected_result:
        valid_result = (
            set(result) == {"success"}
            and type(result["success"]) is dict
            and set(result["success"]) == {"played_plies"}
            and type(result["success"]["played_plies"]) is int
        )
    else:
        valid_result = (
            set(result) == {"rejection"}
            and type(result["rejection"]) is int
        )
    if (
        type(count) is not int
        or count != expected_count
        or not 0 <= count <= recipe["count_cap"]
        or type(cycle_hex) is not str
        or cycle_hex != "1950fad05460b7e0"
        or type(final_hex) is not str
        or final_hex != expected_final
        or recipe["input_bytes"] != expected_bytes
        or recipe["input_bytes"] != count * 2
        or recipe["input_sha256"] != expected_digest
        or len(recipe["input_sha256"]) != 64
        or not valid_result
        or result != expected_result
    ):
        raise AssertionError("closed recipe values")
    cycle = bytes.fromhex(cycle_hex)
    final = bytes.fromhex(final_hex)
    if len(cycle) != 8 or len(final) not in (0, 2):
        raise AssertionError("bounded recipe atoms")
    cycle_plies = count - bool(final)
    if cycle_plies < 0 or cycle_plies * 2 + len(final) != recipe["input_bytes"]:
        raise AssertionError("bounded recipe derived length")
    raw = (cycle * ((cycle_plies + 3) // 4))[: cycle_plies * 2] + final
    if len(raw) != recipe["input_bytes"] or hashlib.sha256(raw).hexdigest() != recipe["input_sha256"]:
        raise AssertionError("recipe byte identity")
    return _decode_moves(chess, raw)


FIXTURE = _load_fixture(ROOT / "conformance/chess-v0.json")

_NEUTRAL_CYCLE_HEX = "1950fad05460b7e01950fad05460b7e0"
_NEUTRAL_POSITION_HEX = (
    "0402030506030204010101010101010100000000000000000000000000000000"
    "0000000000000000000000000000000007070707070707070a08090b0c09080a"
    "000f00"
)
_NEUTRAL_LEGAL_HEX = (
    "05000520195019702100218025102590292029a02d302db0314031c0355035d0"
    "396039e03d703df0"
)
_NEUTRAL_CHECKPOINTS = (
    (0, 0, 1, False),
    (4, 4, 2, False),
    (8, 8, 3, True),
)


def _neutral_cycle_observations() -> bool:
    chess = importlib.import_module("golden_board.chess")
    cycle = _decode_moves(chess, bytes.fromhex(_NEUTRAL_CYCLE_HEX))
    for plies, halfmove, occurrences, threefold in _NEUTRAL_CHECKPOINTS:
        replay = chess.replay_from_start(cycle[:plies])
        local = chess.validate_local(replay.position)
        history = chess.evaluate_predicate(
            b"chess.history_claim", chess.HistoryClaimInput(replay)
        )
        actual = {
            "position_hex": chess.encode_position(replay.position).hex(),
            "repetition_key_hex": chess.repetition_key(replay).hex(),
            "legal_moves_hex": b"".join(
                chess.encode_move(move) for move in chess.legal_moves(replay)
            ).hex(),
            "played_plies": history.played_plies,
            "halfmove_clock": history.halfmove_clock,
            "current_key_occurrences": history.current_key_occurrences,
            "threefold_available": history.threefold_available,
            "first_in_check": chess.king_in_check(local, C.SIDE_FIRST),
            "second_in_check": chess.king_in_check(local, C.SIDE_SECOND),
            "terminal": chess.board_terminal(replay).code,
        }
        expected = {
            "position_hex": _NEUTRAL_POSITION_HEX,
            "repetition_key_hex": _NEUTRAL_POSITION_HEX,
            "legal_moves_hex": _NEUTRAL_LEGAL_HEX,
            "played_plies": plies,
            "halfmove_clock": halfmove,
            "current_key_occurrences": occurrences,
            "threefold_available": threefold,
            "first_in_check": False,
            "second_in_check": False,
            "terminal": 0,
        }
        if actual != expected:
            return False
    return True


class ChessApi(unittest.TestCase):
    def test_public_api_is_present(self) -> None:
        chess = importlib.import_module("golden_board.chess")
        for name in (
            "decode_position",
            "encode_position",
            "decode_move",
            "encode_move",
            "decode_event",
            "encode_event",
            "validate_local",
            "controls_square",
            "king_in_check",
            "pseudo_legal_moves",
            "replay_from_start",
            "legal_moves",
            "apply_move",
            "repetition_key",
            "board_terminal",
            "common_dead",
            "new_game",
            "apply_event",
            "validate_source_record",
            "evaluate_predicate",
        ):
            with self.subTest(name=name):
                self.assertTrue(callable(getattr(chess, name)))
        public_callables = {
            name
            for name, value in vars(chess).items()
            if not name.startswith("_")
            and callable(value)
            and getattr(value, "__module__", None) == chess.__name__
        }
        self.assertEqual(set(chess.__all__), public_callables)
        self.assertEqual(len(chess.__all__), len(set(chess.__all__)))

    def test_neutral_cycle_convergence_recipe(self) -> None:
        self.assertTrue(_neutral_cycle_observations())

    def test_wire_and_local_fixture_cases(self) -> None:
        chess = importlib.import_module("golden_board.chess")
        operations = {
            "decode_position",
            "decode_move",
            "decode_event",
            "validate_local",
            "controls_square",
            "pseudo_legal_moves",
        }
        seen = 0
        for case in FIXTURE["cases"]:
            if case["operation"] not in operations:
                continue
            seen += 1
            with self.subTest(case=case["name"]):
                try:
                    actual = self._run_wire_local(chess, case)
                except chess.ChessReject as error:
                    self.assertEqual(case["expected"], {"rejection": error.code})
                else:
                    self.assertEqual(case["expected"], {"success": actual})
        self.assertEqual(seen, 59)

    def test_authority_values_cannot_be_forged(self) -> None:
        chess = importlib.import_module("golden_board.chess")
        for authority in (
            chess.WirePosition,
            chess.LocallyAdmissiblePosition,
            chess.ReplayState,
            chess.GameState,
        ):
            with self.subTest(authority=authority.__name__):
                with self.assertRaises(TypeError):
                    authority(b"\0" * 67)

    def test_replay_event_and_record_fixture_cases(self) -> None:
        chess = importlib.import_module("golden_board.chess")
        operations = {
            "replay_from_start",
            "legal_moves",
            "apply_move",
            "repetition_key",
            "apply_event",
            "validate_source_record",
        }
        seen = 0
        for case in FIXTURE["cases"]:
            if case["operation"] not in operations:
                continue
            seen += 1
            with self.subTest(case=case["name"]):
                try:
                    actual = self._run_replay(chess, case)
                except chess.ChessReject as error:
                    self.assertEqual(case["expected"], {"rejection": error.code})
                else:
                    self.assertEqual(case["expected"], {"success": actual})
        self.assertEqual(seen, 91)

    def test_rejected_transition_preserves_authority(self) -> None:
        chess = importlib.import_module("golden_board.chess")
        replay = chess.replay_from_start(self._moves(chess, ""))
        before = (chess.encode_position(replay.position), replay.played_plies, replay.halfmove_clock)
        with self.assertRaises(chess.ChessReject):
            chess.apply_move(replay, chess.decode_move(bytes.fromhex("0000")))
        self.assertEqual(
            before,
            (chess.encode_position(replay.position), replay.played_plies, replay.halfmove_clock),
        )

    def test_pseudo_legal_pawn_self_check_uses_final_family(self) -> None:
        chess = importlib.import_module("golden_board.chess")
        replay = chess.replay_from_start(
            self._moves(
                chess,
                "31c0c20039e0d6507240dae092c0ca201570f6f029a0bd40210051d02d3076f0"
                "1950ee900d10bf60b330",
            )
        )
        move = chess.decode_move(bytes.fromhex("8180"))
        self.assertIn(move, chess.pseudo_legal_moves(chess.validate_local(replay.position)))
        self.assertNotIn(move, chess.legal_moves(replay))
        with self.assertRaises(chess.ChessReject) as rejected:
            chess.apply_move(replay, move)
        self.assertEqual(rejected.exception.code, 55)

    def test_predicate_fixture_cases(self) -> None:
        chess = importlib.import_module("golden_board.chess")
        seen = 0
        for case in FIXTURE["cases"]:
            if case["operation"] != "evaluate_predicate":
                continue
            seen += 1
            with self.subTest(case=case["name"]):
                predicate_id = case["input"]["predicate_id"].encode("ascii")
                predicate_input = self._predicate_input(chess, predicate_id, case["input"]["input"])
                try:
                    result = chess.evaluate_predicate(predicate_id, predicate_input)
                except chess.ChessReject as error:
                    self.assertEqual(case["expected"], {"rejection": error.code})
                else:
                    self.assertEqual(
                        case["expected"],
                        {"success": {"result": self._predicate_result(chess, result)}},
                    )
        self.assertEqual(seen, 74)

    def test_bounded_history_recipes(self) -> None:
        chess = importlib.import_module("golden_board.chess")
        for recipe in FIXTURE["recipes"]:
            with self.subTest(recipe=recipe["name"]):
                try:
                    replay = chess.replay_from_start(_recipe_moves(chess, recipe))
                except chess.ChessReject as error:
                    actual = {"rejection": error.code}
                else:
                    actual = {"success": {"played_plies": replay.played_plies}}
                self.assertEqual(recipe["expected"], actual)

    def test_fixture_adapter_rejects_oversize_and_malformed_recipes_before_decode(self) -> None:
        with mock.patch.object(Path, "open", return_value=io.BytesIO(b"x" * (_FIXTURE_BYTE_CAP + 1))):
            with self.assertRaisesRegex(ValueError, "byte cap"):
                _load_fixture(Path("ignored"))

        for raw in (
            b'{"a":' * 32 + b"{}" + b"}" * 32 + b"\n",
            b'{"a": 1}\n',
        ):
            with self.subTest(adapter_bytes=raw[:16]):
                with mock.patch.object(Path, "open", return_value=io.BytesIO(raw)):
                    with self.assertRaises(canonical_manifest.ManifestError):
                        _load_fixture(Path("ignored"))

        class DecodeMustNotRun:
            @staticmethod
            def decode_move(data: bytes) -> object:
                raise AssertionError(f"decoded attacker bytes: {len(data)}")

        for mutation in (
            {"ply_count": 10**100},
            {"cycle_moves_hex": "00" * (_FIXTURE_BYTE_CAP + 1)},
            {"final_move_hex": []},
        ):
            recipe = json.loads(json.dumps(FIXTURE["recipes"][0]))
            recipe["input"].update(mutation)
            with self.subTest(mutation=next(iter(mutation))):
                with self.assertRaisesRegex(AssertionError, "recipe"):
                    _recipe_moves(DecodeMustNotRun(), recipe)

    def test_bounded_reachable_state_properties(self) -> None:
        chess = importlib.import_module("golden_board.chess")
        seed = 0x4742_5033
        generator = random.Random(seed)
        for case_index in range(64):
            moves: list[object] = []
            replay = chess.replay_from_start(())
            for _ in range(generator.randrange(25)):
                legal = chess.legal_moves(replay)
                if not legal:
                    break
                move = legal[generator.randrange(len(legal))]
                moves.append(move)
                replay = chess.apply_move(replay, move)
            diagnostic = f"seed={seed} case={case_index} moves={b''.join(map(chess.encode_move, moves)).hex()}"
            with self.subTest(seed=seed, case=case_index):
                encoded = chess.encode_position(replay.position)
                self.assertEqual(encoded, chess.encode_position(chess.decode_position(encoded)), diagnostic)
                local = chess.validate_local(replay.position)
                legal = chess.legal_moves(replay)
                values = tuple(int.from_bytes(chess.encode_move(move), "big") for move in legal)
                self.assertEqual(values, tuple(sorted(set(values))), diagnostic)
                pseudo_moves = chess.pseudo_legal_moves(local)
                pseudo_values = tuple(
                    int.from_bytes(chess.encode_move(move), "big") for move in pseudo_moves
                )
                self.assertEqual(pseudo_values, tuple(sorted(set(pseudo_values))), diagnostic)
                pseudo = set(pseudo_moves)
                for side in (0, 1):
                    for target in range(64):
                        controllers = chess.controls_square(replay.position, side, target)
                        self.assertEqual(controllers, tuple(sorted(set(controllers))), diagnostic)
                mover = replay.position.side_to_move
                for move in legal:
                    self.assertIn(move, pseudo, diagnostic)
                    self.assertNotIn(
                        replay.position.squares[move.destination],
                        (6, 12),
                        diagnostic,
                    )
                    after = chess.apply_move(replay, move)
                    self.assertEqual(after.position.side_to_move, 1 - mover, diagnostic)
                    self.assertFalse(
                        chess.king_in_check(chess.validate_local(after.position), mover),
                        diagnostic,
                    )
                replayed = chess.replay_from_start(tuple(moves))
                self.assertEqual(chess.encode_position(replayed.position), encoded, diagnostic)
                self.assertEqual(chess.repetition_key(replayed), chess.repetition_key(replay), diagnostic)
                self.assertEqual(replayed.halfmove_clock, replay.halfmove_clock, diagnostic)

    def test_named_chess_and_event_mutants_are_killed(self) -> None:
        chess = importlib.import_module("golden_board.chess")
        cases = {case["name"]: case for case in FIXTURE["cases"]}

        def observed(name: str) -> dict[str, object]:
            case = cases[name]
            try:
                if case["operation"] in {
                    "controls_square",
                    "pseudo_legal_moves",
                    "decode_position",
                    "decode_move",
                    "decode_event",
                    "validate_local",
                }:
                    value = self._run_wire_local(chess, case)
                elif case["operation"] == "apply_move":
                    data = case["input"]
                    replay = chess.replay_from_start(self._moves(chess, data["moves_hex"]))
                    replay = chess.apply_move(
                        replay, chess.decode_move(bytes.fromhex(data["move_hex"]))
                    )
                    complete = {
                        "position_hex": chess.encode_position(replay.position).hex(),
                        "halfmove_clock": replay.halfmove_clock,
                    }
                    expected = case["expected"].get("success")
                    value = complete if expected is None else {key: complete[key] for key in expected}
                else:
                    value = self._run_replay(chess, case)
            except chess.ChessReject as error:
                return {"rejection": error.code}
            return {"success": value}

        def forced_success(name: str, replacement_move_hex: str | None = None) -> dict[str, object]:
            data = cases[name]["input"]
            replay = chess.replay_from_start(self._moves(chess, data["moves_hex"]))
            move = chess.decode_move(
                bytes.fromhex(replacement_move_hex or data["move_hex"])
            )
            position, pawn, capture = chess._apply_position(replay.position, move)
            return {
                "success": {
                    "position_hex": chess.encode_position(position).hex(),
                    "halfmove_clock": 0 if pawn or capture else replay.halfmove_clock + 1,
                }
            }

        kills = (
            ("pinned pieces do not control", "geometry-pinned-piece-still-controls", {"success": {"squares": []}}),
            (
                "king safety checked before capture removal",
                "geometry-king-capture-removes-blocker-self-check",
                forced_success("geometry-king-capture-removes-blocker-self-check"),
            ),
            (
                "castling skips transit",
                "castling-failure-origin-safe-transit-attack",
                forced_success("castling-failure-origin-safe-transit-attack"),
            ),
            ("attacked rook forbids castle", "castling-attacked-rook-allowed", {"rejection": 47}),
            ("queenside b square forbids castle", "castling-queenside-b-square-attacked-allowed", {"rejection": 46}),
            (
                "en-passant pawn remains during self-check",
                "en-passant-pinned-self-exposing-capture",
                forced_success("en-passant-pinned-self-exposing-capture"),
            ),
            (
                "omitted promotion becomes queen",
                "promotion-missing",
                forced_success("promotion-missing", "c792"),
            ),
            ("stalemate tested as mate", "terminal-stalemate-fastest", {"success": {"common_dead": False, "terminal": 1}}),
            ("stalemate tested after dead", "terminal-stalemate-precedes-common-dead", {"success": {"common_dead": True, "terminal": 3}}),
            ("premature agreement allowed", "event-agreement-one-ply", {"success": {"status": 6}}),
        )
        for mutant, case_name, mutant_result in kills:
            with self.subTest(mutant=mutant):
                actual = observed(case_name)
                self.assertEqual(cases[case_name]["expected"], actual)
                self.assertNotEqual(mutant_result, actual)

        nominal = chess.replay_from_start(self._moves(chess, "31c0"))
        with self.subTest(mutant="nominal en-passant always enters repetition"):
            self.assertNotEqual(chess.repetition_key(nominal), chess.encode_position(nominal.position))
        one = chess.evaluate_predicate(
            b"chess.history_claim", chess.HistoryClaimInput(chess.replay_from_start(()))
        )
        with self.subTest(mutant="initial repetition occurrence omitted"):
            self.assertEqual(one.current_key_occurrences, 1)
            self.assertNotEqual(one.current_key_occurrences, 0)
        for case_name in ("history-pawn-move-resets-halfmove", "history-capture-resets-halfmove"):
            data = cases[case_name]["input"]["input"]
            result = chess.evaluate_predicate(
                b"chess.history_claim",
                chess.HistoryClaimInput(chess.replay_from_start(self._moves(chess, data["moves_hex"]))),
            )
            with self.subTest(mutant="halfmove fails to reset", case=case_name):
                self.assertEqual(result.halfmove_clock, 0)
                self.assertNotEqual(result.halfmove_clock, 100)

    def test_remaining_closed_predicate_variants(self) -> None:
        chess = importlib.import_module("golden_board.chess")
        replay = chess.replay_from_start(())
        self.assertTrue(
            chess.evaluate_predicate(
                b"chess.setup_turn", chess.SetupCurrentSideInput(replay, replay.position.side_to_move)
            )
        )
        record = chess.evaluate_predicate(
            b"chess.move_record_replay",
            chess.MoveRecordInput(self._moves(chess, "31c0"), 2),
        )
        self.assertEqual(record.kind, "replayed")
        self.assertEqual(record.record.score, 2)

    def test_predicate_field_shapes_fail_closed(self) -> None:
        chess = importlib.import_module("golden_board.chess")
        replay = chess.replay_from_start(())
        local = chess.validate_local(replay.position)
        move = chess.decode_move(bytes.fromhex("31c0"))
        malformed = (
            (b"chess.setup_turn", chess.SetupCurrentSideInput(replay, True)),
            (b"chess.control", chess.ControlInput(replay.position, 0, "e4")),
            (b"chess.defended", chess.DefendedInput(replay.position, "e2", chess.Defender("any"))),
            (b"chess.king_check", chess.KingCheckInput(local, "white")),
            (b"chess.absolute_pin", chess.AbsolutePinInput(local, "e2")),
            (b"chess.discovered_attack_check", chess.DiscoveredLineInput(replay, move, "c1", 47)),
            (b"chess.escape_square_control", chess.EscapeControlInput(replay.position, 0, "e4")),
            (b"chess.passed_pawn", chess.PassedPawnInput(local, "e2")),
            (b"chess.terminal_transition", chess.TerminalTransitionInput(replay, object())),
            (b"chess.declaration_event", chess.DeclarationEventInput(replay, object())),
            (b"chess.source_score_relation", chess.SourceScoreInput((object(),), 2)),
            (b"chess.move_record_replay", chess.MoveBytesInput(bytearray(b"\x31\xc0"))),
        )
        for predicate_id, value in malformed:
            with self.subTest(predicate_id=predicate_id):
                with self.assertRaises(chess.ChessReject) as rejected:
                    chess.evaluate_predicate(predicate_id, value)
                self.assertEqual(rejected.exception.code, 15)

        closed = chess.replay_from_start(self._moves(chess, "3550d24039e0edf0"))
        with self.assertRaises(chess.ChessReject) as rejected:
            chess.evaluate_predicate(
                b"chess.discovered_attack_check",
                chess.DiscoveredLineInput(closed, move, "c1", 47),
            )
        self.assertEqual(rejected.exception.code, 34)

        overlong = (move,) * 4097
        for predicate_id, value in (
            (b"chess.source_score_relation", chess.SourceScoreInput(overlong, 2)),
            (b"chess.move_record_replay", chess.MoveRecordInput(overlong, 2)),
        ):
            with self.subTest(predicate_id=predicate_id, boundary="move-slice-4097"):
                with self.assertRaises(chess.ChessReject) as rejected:
                    chess.evaluate_predicate(predicate_id, value)
                self.assertEqual(rejected.exception.code, 36)

    def test_transition_predicates_precheck_closure_and_resources(self) -> None:
        chess = importlib.import_module("golden_board.chess")
        closed = chess.replay_from_start(self._moves(chess, "3550d24039e0edf0"))
        game = chess.new_game()
        for move in self._moves(chess, "3550d24039e0edf0"):
            game = chess.apply_event(game, chess.decode_event(b"\x01" + chess.encode_move(move)))

        wrapped = chess.evaluate_predicate(
            b"chess.move_legality", chess.MoveLegalityInput(closed, object())
        )
        self.assertEqual((wrapped.kind, wrapped.code), ("illegal", 34))
        declaration = chess.evaluate_predicate(
            b"chess.declaration_event", chess.DeclarationEventInput(game, object())
        )
        self.assertEqual((declaration.kind, declaration.code), ("rejected", 34))
        for predicate_id, value in (
            (b"chess.fork_double_attack", chess.ForkDoubleAttackInput(closed, object(), ())),
            (
                b"chess.discovered_attack_check",
                chess.DiscoveredLineInput(closed, object(), object(), object()),
            ),
            (b"chess.terminal_transition", chess.TerminalTransitionInput(closed, object())),
        ):
            with self.subTest(predicate_id=predicate_id, precedence="closed"):
                with self.assertRaises(chess.ChessReject) as rejected:
                    chess.evaluate_predicate(predicate_id, value)
                self.assertEqual(rejected.exception.code, 34)

        cycle = "1950fad05460b7e0" * 1024
        full = chess.replay_from_start(self._moves(chess, cycle))
        wrapped = chess.evaluate_predicate(
            b"chess.move_legality", chess.MoveLegalityInput(full, object())
        )
        self.assertEqual((wrapped.kind, wrapped.code), ("illegal", 35))
        for predicate_id, value in (
            (b"chess.fork_double_attack", chess.ForkDoubleAttackInput(full, object(), ())),
            (
                b"chess.discovered_attack_check",
                chess.DiscoveredLineInput(full, object(), object(), object()),
            ),
            (b"chess.terminal_transition", chess.TerminalTransitionInput(full, object())),
        ):
            with self.subTest(predicate_id=predicate_id, precedence="history-resource"):
                with self.assertRaises(chess.ChessReject) as rejected:
                    chess.evaluate_predicate(predicate_id, value)
                self.assertEqual(rejected.exception.code, 35)

    def test_finite_tree_aggregate_resources_precede_row_shape(self) -> None:
        chess = importlib.import_module("golden_board.chess")
        initial = chess.replay_from_start(())
        oversized_nodes = (object(),) * 4097
        oversized_edges = (chess.PredicateNode((object(),) * 257),)
        oversized_total = tuple(chess.PredicateNode((object(),) * 256) for _ in range(16))
        for predicate_id, value in (
            (
                b"chess.finite_promotion_race",
                chess.FinitePromotionTree(object(), oversized_nodes),
            ),
            (
                b"chess.finite_mating_geometry",
                chess.FiniteMatingTree(initial, True, oversized_nodes),
            ),
            (
                b"chess.finite_promotion_race",
                chess.FinitePromotionTree(object(), oversized_edges),
            ),
            (
                b"chess.finite_mating_geometry",
                chess.FiniteMatingTree(initial, True, oversized_total),
            ),
        ):
            with self.subTest(predicate_id=predicate_id, nodes=len(value.nodes)):
                with self.assertRaises(chess.ChessReject) as rejected:
                    chess.evaluate_predicate(predicate_id, value)
                self.assertEqual(rejected.exception.code, 36)

    def test_predicate_primitives_reject_without_coercion_or_host_exceptions(self) -> None:
        chess = importlib.import_module("golden_board.chess")
        position = chess.replay_from_start(()).position

        class HostileEquality:
            def __eq__(self, other: object) -> bool:
                raise RuntimeError(f"unexpected equality with {other!r}")

        malformed = (
            (b"chess.setup_turn", chess.SetupCurrentSideInput(chess.replay_from_start(()), HostileEquality())),
            (b"chess.occupancy", chess.OccupancyInput(position, True, chess.OccupancyMatch("occupied"))),
            (b"chess.occupancy", chess.OccupancyInput(position, "e2", chess.OccupancyMatch("occupied"))),
            (b"chess.occupancy", chess.OccupancyInput(position, 0, chess.OccupancyMatch(HostileEquality()))),
            (b"chess.occupancy", chess.OccupancyInput(position, 0, chess.OccupancyMatch(True))),
            (b"chess.defended", chess.DefendedInput(position, 0, chess.Defender(HostileEquality()))),
            (b"chess.defended", chess.DefendedInput(position, 0, chess.Defender(True))),
            (b"chess.defended", chess.DefendedInput(position, 16, chess.Defender("unknown"))),
            (b"chess.defended", chess.DefendedInput(position, 16, chess.Defender("exact", "a1"))),
            (b"chess.control", chess.ControlInput(position, HostileEquality(), 0)),
            (
                b"chess.source_score_relation",
                chess.SourceScoreInput((), HostileEquality()),
            ),
        )
        for predicate_id, value in malformed:
            with self.subTest(predicate_id=predicate_id, value=value):
                with self.assertRaises(chess.ChessReject) as rejected:
                    chess.evaluate_predicate(predicate_id, value)
                self.assertEqual(rejected.exception.code, 15)

    def test_deterministic_update_properties(self) -> None:
        chess = importlib.import_module("golden_board.chess")
        initial = chess.replay_from_start(())
        knight = chess.apply_move(initial, chess.decode_move(bytes.fromhex("1950")))
        self.assertEqual(knight.position.castling_rights, initial.position.castling_rights)
        self.assertEqual(knight.position.nominal_en_passant, 0)
        self.assertEqual(knight.halfmove_clock, 1)
        pawn = chess.apply_move(initial, chess.decode_move(bytes.fromhex("31c0")))
        self.assertEqual(pawn.position.nominal_en_passant, 21)
        self.assertEqual(pawn.halfmove_clock, 0)
        cleared = chess.decode_position(chess.encode_position(pawn.position)[:66] + b"\0")
        self.assertEqual(chess.repetition_key(pawn), chess.encode_position(cleared))

        promotion_case = next(case for case in FIXTURE["cases"] if case["name"] == "promotion-quiet-queen")
        before_promotion = chess.replay_from_start(
            self._moves(chess, promotion_case["input"]["moves_hex"])
        )
        promotion_groups: dict[tuple[int, int], set[int]] = {}
        for move in chess.legal_moves(before_promotion):
            if move.promotion:
                promotion_groups.setdefault((move.origin, move.destination), set()).add(move.promotion)
        self.assertTrue(promotion_groups)
        self.assertTrue(all(promotions == {1, 2, 3, 4} for promotions in promotion_groups.values()))

        rights_case = next(
            case for case in FIXTURE["cases"]
            if case["name"] == "castling-right-does-not-restore-after-rook-return"
        )
        rights_replay = chess.replay_from_start(self._moves(chess, rights_case["input"]["moves_hex"]))
        self.assertEqual(rights_replay.position.squares[7], 4)
        self.assertEqual(rights_replay.position.castling_rights & 1, 0)

    def test_registered_position_and_repetition_identities(self) -> None:
        chess = importlib.import_module("golden_board.chess")
        identity = importlib.import_module("golden_board.identity")
        vectors = {
            vector["name"]: vector
            for vector in json.loads((ROOT / "conformance/identity-v0.json").read_bytes())["vectors"]
        }
        replay = chess.replay_from_start(())
        for name, payload in (
            ("initial-position", chess.encode_position(replay.position)),
            ("initial-repetition-key", chess.repetition_key(replay)),
        ):
            vector = vectors[name]
            with self.subTest(vector=name):
                self.assertEqual(payload.hex(), vector["fields_hex"][0])
                self.assertEqual(
                    identity.identity_hex(bytes.fromhex(vector["domain_hex"]), (payload,)),
                    vector["identity"],
                )

    def test_new_game_has_no_forgeable_closure_fields(self) -> None:
        chess = importlib.import_module("golden_board.chess")
        game = chess.new_game()
        self.assertEqual(game.status, 1)
        self.assertIsNone(game.closure_cause)
        self.assertIsNone(game.score)
        moved = chess.apply_event(game, chess.decode_event(bytes.fromhex("0131c0")))
        self.assertEqual(moved.status, 1)
        self.assertIsNone(moved.closure_cause)
        self.assertIsNone(moved.score)
        self.assertEqual(game.replay.played_plies, 0)

    def test_closed_predicate_registry_is_read_only(self) -> None:
        chess = importlib.import_module("golden_board.chess")
        with self.assertRaises(TypeError):
            chess._PREDICATE_TYPES[b"chess.injected"] = (object,)

    @staticmethod
    def _run_wire_local(chess: object, case: dict[str, object]) -> dict[str, object]:
        operation = case["operation"]
        data = case["input"]
        if operation == "decode_position":
            position = chess.decode_position(bytes.fromhex(data["position_hex"]))
            return {"position_hex": chess.encode_position(position).hex()}
        if operation == "decode_move":
            move = chess.decode_move(bytes.fromhex(data["move_hex"]))
            return {"move_hex": chess.encode_move(move).hex()}
        if operation == "decode_event":
            event = chess.decode_event(bytes.fromhex(data["event_hex"]))
            return {"event_hex": chess.encode_event(event).hex()}
        position = chess.decode_position(bytes.fromhex(data["position_hex"]))
        if operation == "validate_local":
            local = chess.validate_local(position)
            return {"position_hex": chess.encode_position(local.position).hex()}
        if operation == "controls_square":
            return {"squares": list(chess.controls_square(position, data["side"], data["target"]))}
        local = chess.validate_local(position)
        moves = b"".join(chess.encode_move(move) for move in chess.pseudo_legal_moves(local))
        return {"moves_hex": moves.hex()}

    @staticmethod
    def _moves(chess: object, moves_hex: str) -> tuple[object, ...]:
        data = bytes.fromhex(moves_hex)
        return _decode_moves(chess, data)

    @classmethod
    def _run_replay(cls, chess: object, case: dict[str, object]) -> dict[str, object]:
        operation = case["operation"]
        data = case["input"]
        if operation == "apply_event":
            game = chess.new_game()
            for event_hex in data["events_hex"]:
                game = chess.apply_event(game, chess.decode_event(bytes.fromhex(event_hex)))
            game = chess.apply_event(game, chess.decode_event(bytes.fromhex(data["event_hex"])))
            return cls._game_result(game)
        moves = cls._moves(chess, data["moves_hex"])
        if operation == "validate_source_record":
            record = chess.validate_source_record(moves, data["score"])
            result = {
                "score": record.score,
                "terminal": record.board_terminal.code,
            }
            expected = case["expected"].get("success", {})
            if "threefold_available" in expected:
                result["threefold_available"] = record.threefold_available
            if "fifty_move_available" in expected:
                result["fifty_move_available"] = record.fifty_move_available
            return result
        replay = chess.replay_from_start(moves)
        if operation == "legal_moves":
            return {"moves_hex": b"".join(map(chess.encode_move, chess.legal_moves(replay))).hex()}
        if operation == "repetition_key":
            return {"repetition_key_hex": chess.repetition_key(replay).hex()}
        if operation == "apply_move":
            replay = chess.apply_move(replay, chess.decode_move(bytes.fromhex(data["move_hex"])))
        expected = case["expected"].get("success", {})
        result: dict[str, object] = {}
        terminal = chess.board_terminal(replay)
        for key in expected:
            if key == "position_hex":
                result[key] = chess.encode_position(replay.position).hex()
            elif key == "halfmove_clock":
                result[key] = replay.halfmove_clock
            elif key == "king_in_check":
                result[key] = chess.king_in_check(chess.validate_local(replay.position), replay.position.side_to_move)
            elif key == "terminal":
                result[key] = terminal.code
            elif key == "common_dead":
                result[key] = chess.common_dead(replay)
            elif key == "winning_side":
                result[key] = terminal.winning_side
            else:
                raise AssertionError(f"unsupported replay result field: {key}")
        return result

    @staticmethod
    def _game_result(game: object) -> dict[str, object]:
        cause = game.closure_cause
        result: dict[str, object] = {"status": game.status, "score": game.score}
        if cause.kind == "board":
            value = {"kind": "board", "terminal": cause.terminal.code}
            if cause.terminal.winning_side is not None:
                value["winning_side"] = cause.terminal.winning_side
        elif cause.kind == "resignation":
            value = {"kind": "resignation", "side": cause.side}
        else:
            value = {"kind": cause.kind}
        result["cause"] = value
        return result

    @classmethod
    def _predicate_input(cls, chess: object, predicate_id: bytes, data: dict[str, object]) -> object:
        variant = data["variant"]
        if variant == "wrong":
            return object()
        position = (
            chess.decode_position(bytes.fromhex(data["position_hex"]))
            if "position_hex" in data
            else None
        )
        replay = (
            chess.replay_from_start(cls._moves(chess, data["moves_hex"]))
            if "moves_hex" in data
            else None
        )
        move = (
            chess.decode_move(bytes.fromhex(data["move_hex"]))
            if "move_hex" in data
            else None
        )
        if variant == "initial":
            return chess.SetupInitialInput(position)
        if variant == "occupancy":
            match = data["match"]
            return chess.OccupancyInput(
                position,
                data["square"],
                chess.OccupancyMatch(match["kind"], match.get("side"), match.get("piece")),
            )
        if variant == "move-legality":
            return chess.MoveLegalityInput(replay, move)
        if variant == "control":
            return chess.ControlInput(position, data["side"], data["target"])
        if variant == "defended":
            defender = data["defender"]
            return chess.DefendedInput(
                position,
                data["target"],
                chess.Defender(defender["kind"], defender.get("square")),
            )
        if variant == "king-check":
            return chess.KingCheckInput(chess.validate_local(position), data["side"])
        if variant == "absolute-pin":
            return chess.AbsolutePinInput(chess.validate_local(position), data["origin"])
        if variant == "fork-double-attack":
            return chess.ForkDoubleAttackInput(replay, move, tuple(data["targets"]))
        if variant == "discovered-line":
            return chess.DiscoveredLineInput(replay, move, data["slider_origin"], data["target"])
        if variant == "escape-control":
            return chess.EscapeControlInput(position, data["side"], data["candidate"])
        if variant == "passed-pawn":
            return chess.PassedPawnInput(chess.validate_local(position), data["pawn_square"])
        if variant == "open-file":
            return chess.OpenFileInput(position, data["file"])
        if variant == "semi-open-file":
            return chess.SemiOpenFileInput(position, data["side"], data["file"])
        if variant in ("finite-promotion-tree", "finite-mating-tree"):
            nodes = tuple(
                chess.PredicateNode(
                    tuple(
                        chess.PredicateEdge(
                            chess.decode_move(bytes.fromhex(edge["move_hex"])), edge["child"]
                        )
                        for edge in node["edges"]
                    )
                )
                for node in data["nodes"]
            )
            if variant == "finite-promotion-tree":
                return chess.FinitePromotionTree(replay, nodes)
            return chess.FiniteMatingTree(replay, data["mating_side"], nodes)
        if variant == "terminal-transition":
            return chess.TerminalTransitionInput(replay, move)
        if variant == "history-claim":
            return chess.HistoryClaimInput(replay)
        if variant == "declaration-event":
            game = chess.new_game()
            for event_hex in data["events_hex"]:
                game = chess.apply_event(game, chess.decode_event(bytes.fromhex(event_hex)))
            event = chess.decode_event(bytes.fromhex(data["event_hex"]))
            return chess.DeclarationEventInput(game, event)
        if variant == "source-score":
            return chess.SourceScoreInput(cls._moves(chess, data["moves_hex"]), data["score"])
        if variant == "move-bytes":
            return chess.MoveBytesInput(bytes.fromhex(data["move_hex"]))
        raise AssertionError(f"unhandled predicate variant {variant!r} for {predicate_id!r}")

    @staticmethod
    def _predicate_result(chess: object, result: object) -> dict[str, object]:
        if type(result) is bool:
            return {"value": result}
        if type(result) is tuple:
            return {"squares": list(result)}
        if isinstance(result, chess.MoveLegalityResult):
            value = {"kind": result.kind}
            if result.code is not None:
                value["code"] = result.code
            return value
        if isinstance(result, chess.FiniteRaceResult):
            return {"outcomes": list(result.outcomes)}
        if isinstance(result, chess.FiniteMatingResult):
            return {
                "mating_side": result.mating_side,
                "all_branches_mate": result.all_branches_mate,
                "max_plies": result.max_plies,
            }
        if isinstance(result, chess.BoardTerminal):
            value = {"terminal": result.code}
            if result.winning_side is not None:
                value["winning_side"] = result.winning_side
            return value
        if isinstance(result, chess.HistoryClaimResult):
            def ep(fact: object) -> dict[str, object]:
                return {"kind": "none"} if fact.square is None else {"kind": "square", "square": fact.square}
            return {
                "nominal_ep": ep(result.nominal_ep),
                "effective_ep": ep(result.effective_ep),
                "current_key_occurrences": result.current_key_occurrences,
                "halfmove_clock": result.halfmove_clock,
                "played_plies": result.played_plies,
                "threefold_available": result.threefold_available,
                "fifty_move_available": result.fifty_move_available,
            }
        if isinstance(result, chess.DeclarationEventResult):
            if result.kind == "rejected":
                return {"kind": "rejected", "code": result.code}
            value = {"kind": "accepted", "status": result.status}
            if result.cause is not None:
                value.update(ChessApi._game_result(type("G", (), {"status": result.status, "score": result.score, "closure_cause": result.cause})()))
            return value
        if isinstance(result, chess.SourceScoreResult):
            value = {"kind": result.kind}
            if result.kind == "accepted":
                value["terminal"] = result.terminal.code
            else:
                value["code"] = result.code
            return value
        if isinstance(result, chess.MoveRecordResult):
            value = {"kind": result.kind}
            if result.kind == "decoded":
                value["move_hex"] = chess.encode_move(result.move).hex()
            elif result.kind == "replayed":
                value["score"] = result.record.score
                value["terminal"] = result.record.board_terminal.code
            else:
                value["code"] = result.code
            return value
        raise AssertionError(f"unhandled predicate result: {result!r}")


if __name__ == "__main__":
    unittest.main()
