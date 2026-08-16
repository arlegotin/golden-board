from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import unittest
from unittest import mock

from golden_board import chess


ROOT = Path(__file__).resolve().parents[2]
OWNER = (ROOT / "spec/curriculum-v0.toml").read_bytes()
CONTENT_BASE = bytes.fromhex(
    json.loads((ROOT / "conformance/content-v0.json").read_text())["bases"][0]["stream_hex"]
)
OBSERVABLE_FEATURES = (
    "visible_ordinal", "visible_option_octets", "region_area", "region_count",
    "highlight_count", "selectable_count", "record_payload_octets",
    "node_branch_count", "visible_schema_type_labels", "focus_order", "tab_order",
    "accessibility_attributes", "hover_cursor_clickability", "disabled_state",
    "acknowledgement_identity", "acknowledgement_schedule", "error_shape",
    "response_timing",
)
def _manifest(
    items: object,
    *,
    protocol: object = (),
    cue_forms: object = (),
) -> dict[str, object]:
    return {"items": items, "protocol": protocol, "cue_forms": cue_forms}


def _case(
    identifier: str = "a",
    *,
    split: str = "teaching",
    prompt_target: object = b"initial",
) -> dict[str, object]:
    initial = chess.new_game().replay.position
    return {
        "id": identifier,
        "family_id": "setup_turn",
        "split": split,
        "role_id": "practice" if split in {"practice", "pretest", "posttest", "delayed"} else "exact_rule",
        "primary_generator_id": {
            "teaching": "training", "practice": "formative", "pretest": "pretest",
            "posttest": "final_transfer", "delayed": "delayed",
        }[split],
        "response_shape": "single",
        "max_selections": 1,
        "stratum_ids": ("setup_turn.board_8x8",),
        "structural_template_id": "template",
        "authority_kind": "board_local_position",
        "authority": chess.encode_position(initial),
        "shown_move_bytes": (),
        "case_pattern_ids": ("setup_turn.board_8x8",),
        "owner_calls": ({
            "pattern_id": "setup_turn.board_8x8",
            "case_id": "initial",
            "call_id": "setup",
            "argument": chess.SetupInitialInput(initial),
        },),
        "prompt_target": {
            "type_id": "ByteSlice", "value": prompt_target,
        } if type(prompt_target) is bytes else prompt_target,
        "accepted_responses": (True,),
        "form_id": "f1",
        "integrated_task_id": None,
        "counterfactual_pair_id": None,
        "visible_index": 0,
        "observable_fingerprint": {key: 0 for key in OBSERVABLE_FEATURES},
        "relation_result": True,
        "result_bearing": split != "teaching",
        "public_fields": {},
        "concept_ids": ("setup_turn",),
        "authoring_slot": (
            "assessment" if split in {"pretest", "posttest", "delayed"}
            else "active" if split == "practice" else "grounding"
        ),
        "practice_node_id": f"node-{identifier}" if split == "practice" else None,
    }


def _option(ordinal: int, octets: int, area: int, highlighted: int) -> dict[str, object]:
    value = {key: 0 for key in OBSERVABLE_FEATURES}
    value.update(
        ordinal=ordinal, visible_ordinal=ordinal, visible_option_octets=octets,
        region_area=area, highlight_count=highlighted,
    )
    return value


def _posttest_pair() -> tuple[dict[str, object], dict[str, object]]:
    first = _case(
        "post-a", split="posttest", prompt_target={"type_id": "Square", "value": 17}
    )
    second = _case(
        "post-b", split="posttest", prompt_target={"type_id": "Square", "value": 24}
    )
    position = chess.new_game().replay.position
    for item, pattern, case_id, target, result in (
        (first, "escape_square_control.controlled", "controlled", 17, True),
        (second, "escape_square_control.uncontrolled", "uncontrolled", 24, False),
    ):
        item["family_id"] = "escape_square_control"
        item["concept_ids"] = ("escape_square_control",)
        item["stratum_ids"] = (pattern,)
        item["case_pattern_ids"] = (pattern,)
        item["owner_calls"] = ({
            "pattern_id": pattern, "case_id": case_id, "call_id": "control",
            "argument": chess.EscapeControlInput(position, 0, target),
        },)
        item["accepted_responses"] = (result,)
        item["relation_result"] = result
    first["counterfactual_pair_id"] = second["counterfactual_pair_id"] = "setup-pair"
    first["visible_index"] = 0
    second["visible_index"] = 2
    return first, second


def _learner(
    *,
    baseline: dict[str, str],
    posttest: dict[str, str],
    delayed: dict[str, str],
    hint: bool = False,
    reveal: bool = False,
) -> dict[str, object]:
    protocol = []
    for category in (
        ("semantic_hint", "invalidate_affected_result_bearing_run") if hint else (),
        ("answer_revelation", "invalidate_affected_result_bearing_run") if reveal else (),
    ):
        if category:
            protocol.append({
                "split": "delayed", "feedback": "neutral", "delay_hours": 48,
                "attempt": 1, "interruption": "none", "committed": True,
                "resume": "next", "state_unchanged": True, "outcome": "invalid",
                "retry_allowed": False, "feedback_window": "open",
                "delayed_effect": "fixed_denominator_delayed_failure",
                "help_category": category[0], "help_effect": category[1],
            })
    return {
        "baseline": baseline,
        "posttest": posttest,
        "delayed": delayed,
        "integrated": {
            "integrated_legal_sequence_post": "pass",
            "integrated_record_reading_post": "pass",
        },
        "protocol": tuple(protocol),
    }


class CurriculumRuntime(unittest.TestCase):
    def test_public_surface_is_present(self) -> None:
        from golden_board import curriculum

        self.assertEqual(
            set(curriculum.__all__),
            {
                "Blueprint",
                "CurriculumError",
                "GateResult",
                "evaluate_cue_strategy",
                "evaluate_gates",
                "lint_synthetic",
                "load_blueprint",
            },
        )

    def test_owner_loads_and_malformed_or_unresolved_blueprints_fail_closed(self) -> None:
        from golden_board import curriculum
        from golden_board.curriculum import Blueprint, CurriculumError, load_blueprint

        blueprint = load_blueprint(OWNER)
        self.assertIsInstance(blueprint, Blueprint)
        with self.assertRaises(AttributeError):
            blueprint._data = {}
        ceil = blueprint._data["formula"]["ceil75"]
        self.assertEqual(
            tuple(curriculum._ceil75(blueprint, value) for value in ceil["boundary_inputs"]),
            ceil["boundary_outputs"],
        )
        acquisition = blueprint._data["formula"]["family_acquisition"]
        self.assertEqual(
            tuple(
                "no_claim" if (value := curriculum._acquisition(blueprint, count)) is None else str(value)
                for count in acquisition["boundary_inputs"][:-1]
            ),
            acquisition["boundary_results"][:-1],
        )
        with self.assertRaises(CurriculumError):
            curriculum._acquisition(blueprint, acquisition["boundary_inputs"][-1])
        mutations = (
            OWNER + b"\nunknown = true\n",
            OWNER.replace(b'schema = "golden-board.curriculum/v0"', b'schema = "bad"'),
            OWNER.replace(b'concept_id = "setup_turn"', b'concept_id = "missing"', 1),
            OWNER.replace(b'requires = ["record_replay"]', b'requires = ["missing"]', 1),
            OWNER.replace(b'boundary_outputs = [0, 1, 2, 3, 3, 4, 5, 6, 6, 7, 8, 9]',
                          b'boundary_outputs = [0, 1, 2, 3, 3, 4, 5, 6, 6, 7, 8, 8]'),
            OWNER.replace(b'posttest_passes_min = 5', b'posttest_passes_min = 4', 1),
            OWNER.replace(b'[coverage]\n', b'[coverage]\nunknown = true\n', 1),
            OWNER.replace(b'grounded_rule_or_relation_per_concept = 1\n', b'', 1),
            OWNER.replace(b'  "king_safety.self_check",\n', b'', 1),
            OWNER.replace(b'score_mode = "exact_assertion_unscored"', b'score_mode = "nonsense"', 1),
            OWNER.replace(b'matrix = [1, 0, 0, 1]', b'matrix = [1, 1, 0, 1]', 1),
            OWNER.replace(b'  "hover_cursor_clickability",\n', b'', 1),
            OWNER.replace(b'above_domain_result = "invalid_protocol"', b'above_domain_result = "no_claim"', 1),
            OWNER.replace(
                b'instruction_coverage_any_of_splits = ["teaching", "practice"]',
                b'instruction_coverage_any_of_splits = ["nonsense"]', 1,
            ),
            OWNER.replace(b'active_role_id = "practice"', b'active_role_id = "exact_rule"', 1),
            OWNER.replace(b'same_form_may_serve_multiple_learners = true', b'same_form_may_serve_multiple_learners = false', 1),
            OWNER.replace(b'apply_all_listed_predicate_mappings = true', b'apply_all_listed_predicate_mappings = false', 1),
            OWNER.replace(b'  "accepted_option_ordinals",\n', b'', 1),
            OWNER.replace(b'delayed_window_min_hours = 36', b'delayed_window_min_hours = 0', 1),
            OWNER.replace(b'  "complete_core1",\n', b'', 1),
            OWNER.replace(b'minimum_per_form = 1', b'minimum_per_form = 0', 1),
            OWNER.replace(
                b'source_id = "authority.replay_state_exact_0_plies"',
                b'source_id = "authority.forged"', 1,
            ),
        )
        for raw in mutations:
            self.assertNotEqual(raw, OWNER)
            with self.subTest(raw=raw[-80:]), self.assertRaises(CurriculumError):
                load_blueprint(raw)

    def test_gate_arithmetic_uses_the_owner_and_fixed_six_denominator(self) -> None:
        from golden_board.curriculum import CurriculumError, evaluate_gates, load_blueprint

        blueprint = load_blueprint(OWNER)
        essential = blueprint.family_set("E")
        core3 = blueprint.family_set("C")
        all_families = essential | core3
        learners = []
        for index in range(6):
            baseline = {family: "fail" if index < 4 else "pass" for family in all_families}
            posttest = {family: "pass" for family in all_families}
            delayed = {family: "pass" for family in essential}
            learners.append(_learner(baseline=baseline, posttest=posttest, delayed=delayed))
        result = evaluate_gates(
            blueprint, {"combined_core3_claim": True, "learners": learners}
        )
        self.assertTrue(result.passed)
        self.assertEqual(
            (
                result.protocol_claimable,
                result.essential_family,
                result.essential_individual,
                result.core3_family,
                result.core3_combined,
                result.delayed,
                result.unhinted,
            ),
            (True, True, True, True, True, True, True),
        )

        missing = copy.deepcopy(learners)
        missing_family = next(iter(essential))
        del missing[0]["posttest"][missing_family]
        del missing[1]["posttest"][missing_family]
        self.assertFalse(
            evaluate_gates(
                blueprint, {"combined_core3_claim": True, "learners": missing}
            ).essential_family
        )
        unavailable = copy.deepcopy(learners)
        family = next(iter(essential))
        for learner in unavailable[:4]:
            learner["baseline"][family] = "unavailable"
        self.assertFalse(
            evaluate_gates(
                blueprint, {"combined_core3_claim": False, "learners": unavailable}
            ).protocol_claimable
        )
        hinted = copy.deepcopy(learners)
        hinted[0]["protocol"] = _learner(
            baseline={}, posttest={}, delayed={}, hint=True
        )["protocol"]
        self.assertFalse(
            evaluate_gates(
                blueprint, {"combined_core3_claim": False, "learners": hinted}
            ).unhinted
        )
        absent = copy.deepcopy(learners)
        for learner in absent:
            learner["protocol"] = ({
                "split": "delayed", "feedback": "neutral", "delay_hours": None,
                "attempt": 0, "interruption": "before_commit", "committed": False,
                "resume": "missing", "state_unchanged": True, "outcome": "absent",
                "retry_allowed": False, "feedback_window": "fallback_resolved",
                "delayed_effect": "fixed_denominator_delayed_failure",
                "help_category": "none", "help_effect": "none",
            },)
        self.assertFalse(
            evaluate_gates(
                blueprint, {"combined_core3_claim": False, "learners": absent}
            ).passed
        )
        mixed = copy.deepcopy(learners)
        for learner in mixed[4:]:
            learner["protocol"] = absent[0]["protocol"]
        affected = sorted(essential - {"king_safety"} - blueprint.family_set("S"))[:4]
        for index, learner in enumerate(mixed[:4]):
            for family in affected[:2] if index < 2 else affected[2:]:
                learner["delayed"][family] = "fail"
        self.assertFalse(
            evaluate_gates(
                blueprint, {"combined_core3_claim": False, "learners": mixed}
            ).delayed
        )
        with self.assertRaises(CurriculumError):
            evaluate_gates(blueprint, {"combined_core3_claim": False, "learners": learners[:5]})
        unknown = copy.deepcopy(learners)
        unknown[0]["integrated"]["invented"] = "pass"
        with self.assertRaises(CurriculumError):
            evaluate_gates(blueprint, {"combined_core3_claim": False, "learners": unknown})

    def test_total_cue_strategies_follow_visible_ties_caps_and_prior_fallbacks(self) -> None:
        from golden_board import curriculum
        from golden_board.curriculum import CurriculumError, evaluate_cue_strategy, lint_synthetic, load_blueprint

        blueprint = load_blueprint(OWNER)
        schedule = (
            {
                "shape": "set",
                "max_selections": 2,
                "repeat_allowed": False,
                "options": (
                    _option(2, 3, 4, 1),
                    _option(1, 3, 8, 2),
                    _option(3, 5, 8, 0),
                ),
                "prior_accepted_responses": None,
            },
            {
                "shape": "set",
                "max_selections": 2,
                "repeat_allowed": False,
                "options": (
                    _option(1, 4, 2, 0),
                    _option(2, 2, 2, 3),
                ),
                "prior_accepted_responses": ((2,), (1,)),
            },
            {
                "shape": "single",
                "max_selections": 0,
                "repeat_allowed": False,
                "options": (),
                "prior_accepted_responses": ((),),
            },
        )
        self.assertEqual(evaluate_cue_strategy(blueprint, "first", schedule), ((1,), (1,), ()))
        self.assertEqual(evaluate_cue_strategy(blueprint, "last", schedule), ((3,), (2,), ()))
        self.assertEqual(evaluate_cue_strategy(blueprint, "shortest", schedule), ((1,), (2,), ()))
        self.assertEqual(evaluate_cue_strategy(blueprint, "largest_region", schedule), ((1,), (1,), ()))
        self.assertEqual(evaluate_cue_strategy(blueprint, "most_highlighted", schedule), ((1,), (2,), ()))
        self.assertEqual(evaluate_cue_strategy(blueprint, "alternating", schedule), ((1,), (2,), ()))
        self.assertEqual(evaluate_cue_strategy(blueprint, "same_as_prior", schedule), ((1,), (1,), ()))
        unsorted_prior = dict(schedule[1])
        unsorted_prior["prior_accepted_responses"] = ((2, 1),)
        self.assertEqual(
            evaluate_cue_strategy(blueprint, "same_as_prior", (unsorted_prior,)),
            ((1, 2),),
        )
        oversized_prior = dict(schedule[1])
        oversized_prior["prior_accepted_responses"] = ((),) * 65_536
        with self.assertRaises(CurriculumError):
            evaluate_cue_strategy(blueprint, "same_as_prior", (oversized_prior,))
        oversized_observable = copy.deepcopy(schedule[0])
        oversized_observable["options"][0]["focus_order"] = tuple(range(65_536))
        with self.assertRaises(CurriculumError):
            evaluate_cue_strategy(blueprint, "first", (oversized_observable,))
        calls: list[int] = []
        original_options = curriculum._options

        def observed(item):
            calls.append(len(item["options"]))
            return original_options(item)

        with mock.patch.object(curriculum.C, "CONTENT_MAX_VECTOR_ATOMS", 1), mock.patch.object(
            curriculum, "_options", side_effect=observed
        ), self.assertRaises(CurriculumError):
            evaluate_cue_strategy(blueprint, "first", schedule[:2])
        self.assertEqual(calls, [])
        incomplete_visible = copy.deepcopy(schedule[0])
        del incomplete_visible["options"][0]["focus_order"]
        with self.assertRaises(CurriculumError):
            evaluate_cue_strategy(blueprint, "first", (incomplete_visible,))
        self.assertEqual(evaluate_cue_strategy(blueprint, "empty_commit", schedule), ((), (), ()))
        self.assertEqual(evaluate_cue_strategy(blueprint, "select_all_visible", schedule), ((1, 2), (1, 2), ()))

        audit_schedule = tuple(
            {
                "shape": "set",
                "max_selections": 2,
                "repeat_allowed": False,
                "options": (
                    _option(1, 1, 1, 0),
                    _option(2, 2, 2, 1),
                    _option(3, 3, 3, 2),
                ),
                "prior_accepted_responses": None,
            }
            for _ in range(2)
        )
        cue_form = {
            "family_id": "escape_square_control",
            "schedule": audit_schedule,
            "accepted_responses": (((2, 3),), ((2, 3),)),
        }
        curriculum._lint_items(blueprint, _posttest_pair())
        curriculum._lint_cues(blueprint, (cue_form,))
        leaking = dict(cue_form)
        leaking["accepted_responses"] = (((1,),), ((1,),))
        with self.assertRaises(CurriculumError):
            curriculum._lint_cues(blueprint, (leaking,))
        oversized_form = {
            "family_id": "setup_turn",
            "schedule": (audit_schedule[0],) * 5_121,
            "accepted_responses": (((2, 3),),) * 5_121,
        }
        calls.clear()
        with mock.patch.object(curriculum, "_options", side_effect=observed), self.assertRaises(
            CurriculumError
        ):
            curriculum._lint_cues(blueprint, (oversized_form,))
        self.assertEqual(calls, [])

    def test_synthetic_lint_recomputes_owners_and_rejects_leakage_or_reuse(self) -> None:
        from golden_board import curriculum
        from golden_board.curriculum import CurriculumError, lint_synthetic, load_blueprint

        blueprint = load_blueprint(OWNER)
        case = _case()
        content_case = _case("content", prompt_target=b"content-projection")
        content_case["family_id"] = "record_replay"
        content_case["authority_kind"] = "content_bytes"
        content_case["authority"] = CONTENT_BASE
        content_case["stratum_ids"] = ("record_replay.logical_record_valid",)
        content_case["case_pattern_ids"] = ("record_replay.logical_record_valid",)
        content_case["owner_calls"] = ({
            "pattern_id": "record_replay.logical_record_valid", "case_id": "valid",
            "call_id": "content", "argument": CONTENT_BASE,
        },)
        content_case["accepted_responses"] = ("accept",)
        content_case["relation_result"] = "accept"
        content_case["concept_ids"] = ("record_replay",)
        curriculum._lint_items(blueprint, (case, content_case))

        reused = dict(case)
        reused["id"] = "b"
        reused["split"] = "posttest"
        reused["result_bearing"] = True
        with self.assertRaises(CurriculumError):
            curriculum._lint_items(blueprint, (case, reused))

        leaked = dict(reused)
        leaked["prompt_target"] = b"case-b"
        leaked["public_fields"] = {"accepted_response_cardinality": 2}
        with self.assertRaises(CurriculumError):
            curriculum._lint_items(blueprint, (case, leaked))

        wrong = dict(case)
        wrong["relation_result"] = 1
        wrong["accepted_responses"] = (1,)
        with self.assertRaises(CurriculumError):
            curriculum._lint_items(blueprint, (wrong,))

        extra = dict(case)
        extra["accepted_responses"] = (True, "forged")
        with self.assertRaises(CurriculumError):
            curriculum._lint_items(blueprint, (extra,))

        unrelated = dict(case)
        unrelated["concept_ids"] = ("c3.material_heuristic", "setup_turn")
        unrelated["role_id"] = "heuristic"
        unrelated["authoring_slot"] = "heuristic"
        with self.assertRaises(CurriculumError):
            curriculum._lint_items(blueprint, (unrelated,))

        e2e4 = chess.decode_move(((12 << 10) | (28 << 4)).to_bytes(2, "big"))
        d2d4 = chess.decode_move(((11 << 10) | (27 << 4)).to_bytes(2, "big"))
        shown = _case(
            "shown-binding",
            prompt_target={"type_id": "Move", "value": chess.encode_move(e2e4)},
        )
        replay = chess.replay_from_start(())
        shown.update(
            family_id="ordinary_move_capture",
            concept_ids=("ordinary_move_capture",),
            authority_kind="complete_replay_moves",
            authority=(),
            stratum_ids=("ordinary_move_capture.pawn_forward_vs_capture",),
            case_pattern_ids=("ordinary_move_capture.pawn_forward_vs_capture",),
            shown_move_bytes=(chess.encode_move(d2d4),),
            owner_calls=({
                "pattern_id": "ordinary_move_capture.pawn_forward_vs_capture",
                "case_id": "quiet", "call_id": "legality",
                "argument": chess.MoveLegalityInput(replay, e2e4),
            },),
            accepted_responses=(chess.MoveLegalityResult("legal"),),
            relation_result=chess.MoveLegalityResult("legal"),
        )
        with self.assertRaises(CurriculumError):
            curriculum._lint_items(blueprint, (shown,))

        post_move = _case(
            "post-move-history",
            prompt_target={"type_id": "Move", "value": chess.encode_move(e2e4)},
        )
        after_e2e4 = chess.apply_move(replay, e2e4)
        history = chess.evaluate_predicate(
            b"chess.history_claim", chess.HistoryClaimInput(after_e2e4)
        )
        post_move.update(
            family_id="position_history_draw",
            concept_ids=("position_history_draw",),
            authority_kind="complete_replay_moves",
            authority=(),
            stratum_ids=("position_history_draw.halfmove_pawn_reset",),
            case_pattern_ids=("position_history_draw.halfmove_pawn_reset",),
            shown_move_bytes=(chess.encode_move(e2e4),),
            owner_calls=({
                "pattern_id": "position_history_draw.halfmove_pawn_reset",
                "case_id": "after", "call_id": "history",
                "argument": after_e2e4,
            },),
            accepted_responses=(history,),
            relation_result=history,
        )
        curriculum._lint_items(blueprint, (post_move,))
        wrong_post_move = dict(post_move)
        wrong_post_move["shown_move_bytes"] = (chess.encode_move(d2d4),)
        with self.assertRaises(CurriculumError):
            curriculum._lint_items(blueprint, (wrong_post_move,))
        reflected_post_move = dict(post_move)
        after_d2d4 = chess.apply_move(replay, d2d4)
        reflected_history = chess.evaluate_predicate(
            b"chess.history_claim", chess.HistoryClaimInput(after_d2d4)
        )
        reflected_post_move.update(
            id="post-move-history-reflected",
            prompt_target={"type_id": "Move", "value": chess.encode_move(d2d4)},
            shown_move_bytes=(chess.encode_move(d2d4),),
            owner_calls=({
                "pattern_id": "position_history_draw.halfmove_pawn_reset",
                "case_id": "after", "call_id": "history",
                "argument": after_d2d4,
            },),
            accepted_responses=(reflected_history,),
            relation_result=reflected_history,
        )
        curriculum._lint_items(blueprint, (reflected_post_move,))
        with self.assertRaises(CurriculumError):
            curriculum._lint_items(blueprint, (post_move, reflected_post_move))

        generic = _case(
            "material-heuristic",
            prompt_target={"type_id": "Move", "value": chess.encode_move(e2e4)},
        )
        legality = chess.MoveLegalityInput(replay, e2e4)
        legal = chess.evaluate_predicate(b"chess.move_legality", legality)
        generic.update(
            family_id=None,
            integrated_task_id=None,
            concept_ids=("c3.material_heuristic",),
            role_id="heuristic",
            authoring_slot="heuristic",
            authority_kind="complete_replay_moves",
            authority=(),
            stratum_ids=("ordinary_move_capture.pawn_forward_vs_capture",),
            case_pattern_ids=("ordinary_move_capture.pawn_forward_vs_capture",),
            shown_move_bytes=(chess.encode_move(e2e4),),
            owner_calls=({
                "pattern_id": "ordinary_move_capture.pawn_forward_vs_capture",
                "case_id": "quiet", "call_id": "legality", "argument": legality,
            },),
            accepted_responses=(legal,),
            relation_result=legal,
        )
        curriculum._lint_items(blueprint, (generic,))

        integrated = _case(
            "integrated-move",
            split="pretest",
            prompt_target={"type_id": "Move", "value": chess.encode_move(e2e4)},
        )
        decoded = chess.evaluate_predicate(
            b"chess.move_record_replay", chess.MoveBytesInput(chess.encode_move(e2e4))
        )
        integrated.update(
            family_id=None,
            integrated_task_id="integrated_legal_sequence_pre",
            concept_ids=("record_replay",),
            authoring_slot="integrated",
            authority_kind="complete_replay_moves",
            authority=(),
            stratum_ids=("record_replay.canonical_move_decode",),
            case_pattern_ids=("record_replay.canonical_move_decode",),
            shown_move_bytes=(chess.encode_move(e2e4),),
            owner_calls=({
                "pattern_id": "record_replay.canonical_move_decode",
                "case_id": "canonical", "call_id": "decode",
                "argument": chess.encode_move(e2e4),
            },),
            accepted_responses=(decoded,),
            relation_result=decoded,
        )
        curriculum._lint_items(blueprint, (integrated,))
        wrong_integrated = dict(integrated)
        wrong_integrated["integrated_task_id"] = "integrated_legal_sequence_post"
        with self.assertRaises(CurriculumError):
            curriculum._lint_items(blueprint, (wrong_integrated,))

        false_turn = _case("false-turn", prompt_target={"type_id": "Side", "value": 1})
        replay = chess.replay_from_start(())
        false_turn["authority_kind"] = "complete_replay_moves"
        false_turn["authority"] = ()
        false_turn["stratum_ids"] = ("setup_turn.initial_side_to_move",)
        false_turn["case_pattern_ids"] = ("setup_turn.initial_side_to_move",)
        false_turn["owner_calls"] = ({
            "pattern_id": "setup_turn.initial_side_to_move", "case_id": "initial",
            "call_id": "turn", "argument": chess.SetupCurrentSideInput(replay, 1),
        },)
        false_turn["accepted_responses"] = (False,)
        false_turn["relation_result"] = False
        with self.assertRaises(CurriculumError):
            curriculum._lint_items(blueprint, (false_turn,))

        self.assertEqual(
            curriculum._mapped_prompt(
                {"type_id": "Square", "value": 35},
                "rank_reflection_color_swap",
            ),
            {"type_id": "Square", "value": 27},
        )

        e2e4 = chess.decode_move(((12 << 10) | (28 << 4)).to_bytes(2, "big"))
        original_position = chess.replay_from_start((e2e4,)).position
        raw = bytearray(67)
        for square, code in enumerate(original_position.squares):
            mapped_code = code + 6 if 1 <= code <= 6 else code - 6 if 7 <= code <= 12 else code
            raw[(square % 8) + 8 * (7 - square // 8)] = mapped_code
        raw[64] = original_position.side_to_move ^ 1
        raw[65] = 15
        raw[66] = 45
        mapped_position = chess.decode_position(bytes(raw))
        chess.validate_local(mapped_position)

        def control_case(identifier: str, split: str, position, side: int, target: int, origin: int) -> dict[str, object]:
            item = _case(identifier, split=split, prompt_target=b"pawn-control")
            item["family_id"] = "control_vs_legal"
            item["concept_ids"] = ("control_vs_legal",)
            item["authority"] = chess.encode_position(position)
            item["stratum_ids"] = ("control_vs_legal.pawn_control",)
            item["case_pattern_ids"] = ("control_vs_legal.pawn_control",)
            calls = (
                {
                    "pattern_id": "control_vs_legal.pawn_control", "case_id": "pawn",
                    "call_id": "controllers", "argument": chess.ControlInput(position, side, target),
                },
                {
                    "pattern_id": "control_vs_legal.pawn_control", "case_id": "pawn",
                    "call_id": "controller_piece",
                    "argument": chess.OccupancyInput(
                        position, origin, chess.OccupancyMatch("exact", side, 1)
                    ),
                },
            )
            item["owner_calls"] = calls
            item["accepted_responses"] = (
                chess.evaluate_predicate(b"chess.control", calls[0]["argument"]), True,
            )
            return item

        transformed = (
            control_case("white", "teaching", original_position, 0, 35, 28),
            control_case("black", "teaching", mapped_position, 1, 27, 36),
        )
        transformed[0]["prompt_target"] = {"type_id": "Square", "value": 35}
        transformed[1]["prompt_target"] = {"type_id": "Square", "value": 27}
        curriculum._lint_items(blueprint, (transformed[0],))
        curriculum._lint_items(blueprint, (transformed[1],))
        with self.assertRaises(CurriculumError):
            curriculum._lint_items(blueprint, transformed)
        mismatched_prompt = control_case(
            "prompt", "teaching", original_position, 0, 35, 28
        )
        mismatched_prompt["prompt_target"] = {"type_id": "Square", "value": 63}
        with self.assertRaises(CurriculumError):
            curriculum._lint_items(blueprint, (mismatched_prompt,))

    def test_synthetic_caps_forms_privacy_and_counterfactual_splits_are_closed(self) -> None:
        from golden_board import curriculum
        from golden_board.curriculum import CurriculumError, lint_synthetic, load_blueprint

        blueprint = load_blueprint(OWNER)
        with self.assertRaises(CurriculumError):
            lint_synthetic(blueprint, _manifest((_case(),)))
        with self.assertRaises(CurriculumError):
            curriculum._lint_items(blueprint, ())

        over_family = tuple(
            _case(str(index), prompt_target=index.to_bytes(2, "big"))
            for index in range(257)
        )
        with self.assertRaises(CurriculumError):
            curriculum._lint_items(blueprint, over_family)

        four_forms = []
        for index in range(4):
            item = _case(str(index), prompt_target=bytes((index,)))
            item["form_id"] = f"f{index}"
            four_forms.append(item)
        with self.assertRaises(CurriculumError):
            curriculum._lint_items(blueprint, tuple(four_forms))

        leaked = _case()
        leaked["public_fields"] = {"candidate_bound_result_bearing_payload": b"x"}
        with self.assertRaises(CurriculumError):
            curriculum._lint_items(blueprint, (leaked,))

        paired = _case()
        paired["counterfactual_pair_id"] = "teaching-pair"
        with self.assertRaises(CurriculumError):
            curriculum._lint_items(blueprint, (paired,))

        tasks = {row["id"]: row for row in blueprint._data["integrated_task"]}
        counts = {
            (form, identifier): row["minimum_per_form"]
            for form in ("f1", "f2", "f3")
            for identifier, row in tasks.items()
        }
        curriculum._validate_integrated_forms(
            frozenset(("f1", "f2", "f3")), counts, tasks
        )
        del counts[("f2", next(iter(tasks)))]
        with self.assertRaises(CurriculumError):
            curriculum._validate_integrated_forms(
                frozenset(("f1", "f2", "f3")), counts, tasks
            )

    def test_protocol_feedback_delay_and_interruptions_fail_closed(self) -> None:
        from golden_board import curriculum
        from golden_board.curriculum import CurriculumError, lint_synthetic, load_blueprint

        blueprint = load_blueprint(OWNER)
        good = (
            {"split": "posttest", "feedback": "neutral", "delay_hours": None,
             "attempt": 1, "interruption": "none", "committed": True,
             "resume": "next", "state_unchanged": True, "outcome": "valid",
             "retry_allowed": False, "feedback_window": "open",
             "delayed_effect": "not_applicable", "help_category": "none",
             "help_effect": "none"},
            {"split": "delayed", "feedback": "neutral", "delay_hours": 48,
             "attempt": 1, "interruption": "none", "committed": True,
             "resume": "next", "state_unchanged": True, "outcome": "valid",
             "retry_allowed": False, "feedback_window": "normal_resolved",
             "delayed_effect": "pass", "help_category": "none",
             "help_effect": "none"},
            {"split": "practice", "feedback": "correctness", "delay_hours": None,
             "attempt": 1, "interruption": "after_commit", "committed": True,
             "resume": "next", "state_unchanged": True, "outcome": "valid",
             "retry_allowed": False, "feedback_window": "not_applicable",
             "delayed_effect": "not_applicable", "help_category": "procedural_reminder",
             "help_effect": "exclude_affected_item_from_unhinted_success"},
        )
        curriculum._lint_protocol(blueprint, good)
        for outcome, hours, attempt, window in (
            ("early", 35, 1, "open"),
            ("late", 61, 1, "open"),
            ("absent", None, 0, "fallback_resolved"),
        ):
            variant = copy.deepcopy(good)
            variant[1].update(
                outcome=outcome, delay_hours=hours, attempt=attempt,
                feedback_window=window, delayed_effect="fixed_denominator_delayed_failure",
            )
            if outcome == "absent":
                variant[1].update(
                    interruption="before_commit", committed=False, resume="missing"
                )
            curriculum._lint_protocol(blueprint, variant)
        for field, value in (
            ("feedback", "correctness"),
            ("delay_hours", 35),
            ("attempt", 2),
            ("state_unchanged", False),
            ("attempt", True),
        ):
            bad = copy.deepcopy(good)
            bad[1 if field != "feedback" else 0][field] = value
            with self.subTest(field=field), self.assertRaises(CurriculumError):
                curriculum._lint_protocol(blueprint, bad)

        contradictions = (
            {"outcome": "valid", "delayed_effect": "pass", "interruption": "before_commit",
             "committed": False, "resume": "missing"},
            {"outcome": "absent", "attempt": 0, "delay_hours": None,
             "feedback_window": "fallback_resolved",
             "delayed_effect": "fixed_denominator_delayed_failure",
             "interruption": "after_commit", "committed": True, "resume": "next"},
            {"help_category": "semantic_hint",
             "help_effect": "invalidate_affected_result_bearing_run"},
            {"outcome": "invalid", "delay_hours": object(),
             "feedback_window": "open",
             "delayed_effect": "fixed_denominator_delayed_failure"},
            {"outcome": "early", "delay_hours": 35,
             "feedback_window": "open",
             "delayed_effect": "fixed_denominator_delayed_failure",
             "interruption": "none", "committed": False, "resume": "missing"},
            {"outcome": "early", "delay_hours": math.nan,
             "feedback_window": "open",
             "delayed_effect": "fixed_denominator_delayed_failure"},
        )
        for changes in contradictions:
            bad = copy.deepcopy(good)
            bad[1].update(changes)
            with self.subTest(changes=changes), self.assertRaises(CurriculumError):
                curriculum._lint_protocol(blueprint, bad)


if __name__ == "__main__":
    unittest.main()
