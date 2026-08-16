"""Independent Python evidence for chess-v0."""

from __future__ import annotations

import importlib
import hashlib
import json
from pathlib import Path
import random
import unittest


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / "conformance/chess-v0.json").read_bytes())


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
                cycle = bytes.fromhex(recipe["input"]["cycle_moves_hex"])
                count = recipe["input"]["ply_count"]
                final = bytes.fromhex(recipe["input"]["final_move_hex"])
                cycle_plies = count - bool(final)
                raw = (cycle * ((cycle_plies + 3) // 4))[: cycle_plies * 2] + final
                self.assertLessEqual(count, recipe["count_cap"])
                self.assertEqual(len(raw), recipe["input_bytes"])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), recipe["input_sha256"])
                try:
                    replay = chess.replay_from_start(self._moves(chess, raw.hex()))
                except chess.ChessReject as error:
                    actual = {"rejection": error.code}
                else:
                    actual = {"success": {"played_plies": replay.played_plies}}
                self.assertEqual(recipe["expected"], actual)

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
                pseudo = set(chess.pseudo_legal_moves(local))
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
                else:
                    value = self._run_replay(chess, case)
            except chess.ChessReject as error:
                return {"rejection": error.code}
            return {"success": value}

        kills = (
            ("pinned pieces do not control", "geometry-pinned-piece-still-controls", {"success": {"squares": []}}),
            ("king safety checked before capture removal", "geometry-king-capture-removes-blocker-self-check", {"success": {}}),
            ("castling skips transit", "castling-failure-origin-safe-transit-attack", {"success": {}}),
            ("attacked rook forbids castle", "castling-attacked-rook-allowed", {"rejection": 47}),
            ("queenside b square forbids castle", "castling-queenside-b-square-attacked-allowed", {"rejection": 46}),
            ("en-passant pawn remains during self-check", "en-passant-pinned-self-exposing-capture", {"success": {}}),
            ("omitted promotion becomes queen", "promotion-missing", {"success": {}}),
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
        return tuple(chess.decode_move(data[index : index + 2]) for index in range(0, len(data), 2))

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
