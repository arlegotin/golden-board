from __future__ import annotations

import copy
import hashlib
import json
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OWNER = ROOT / "spec/curriculum-v0.toml"

ROOT_KEYS = {
    "schema", "roadmap_mirror", "taxonomy", "sets", "coverage",
    "authoring_minimums", "assessment_minimums", "scoring", "formula",
    "gate", "forms", "leakage", "cue_audit", "capacity", "cut",
    "m1_scope", "concept", "role", "generator", "family",
    "integrated_task", "critical_label", "transform", "predicate_mapping",
    "cue_strategy", "input_binding", "result_contract", "case_pattern",
}
REMOVED_DERIVED_KEYS = {
    "stratum", "evidence_registry", "checker_contract",
    "semantic_operation", "semantic_constants", "bound_value",
}

EXPECTED_PATTERN_IDS = set("""
setup_turn.board_8x8
setup_turn.initial_piece_placement
setup_turn.initial_side_to_move
setup_turn.alternating_turn
ordinary_move_capture.king_identity_and_move
ordinary_move_capture.queen_identity_and_move
ordinary_move_capture.rook_identity_and_move
ordinary_move_capture.bishop_identity_and_move
ordinary_move_capture.knight_identity_and_move
ordinary_move_capture.pawn_identity
ordinary_move_capture.slider_blocking
ordinary_move_capture.knight_jump
ordinary_move_capture.pawn_forward_vs_capture
ordinary_move_capture.pawn_initial_double
ordinary_move_capture.friendly_occupancy_rejection
control_vs_legal.pawn_control
control_vs_legal.defended_friendly_target
control_vs_legal.pinned_piece_controls
control_vs_legal.king_adjacency
control_vs_legal.control_vs_move
king_safety.check
king_safety.check_evasion
king_safety.self_check
king_safety.king_capture_safety
king_safety.double_check
mate_stalemate.checkmate_vs_check
mate_stalemate.stalemate
mate_stalemate.legal_reply_exhaustiveness
castling.rights
castling.entitled_king_and_rook
castling.path_clear
castling.from_check
castling.through_check
castling.into_check
castling.lost_rights
castling.rook_relocation
en_passant.immediate_window
en_passant.expiry
en_passant.captured_pawn_removal
en_passant.self_check
en_passant.nominal_vs_effective
promotion.quiet_promotion
promotion.capture_promotion
promotion.promote_queen
promotion.promote_rook
promotion.promote_bishop
promotion.promote_knight
promotion.check_after_promotion
promotion.mate_after_promotion
promotion.invalid_context
position_history_draw.same_board_different_history
position_history_draw.repetition_key
position_history_draw.repetition_occurrence
position_history_draw.halfmove_99_100
position_history_draw.halfmove_pawn_reset
position_history_draw.halfmove_capture_reset
position_history_draw.claims_not_automatic
termination_score.checkmate
termination_score.stalemate
termination_score.common_dead_scope
termination_score.resignation
termination_score.agreement
termination_score.threefold_claim
termination_score.fifty_move_claim
termination_score.post_terminal_rejection
termination_score.score_vs_cause
record_replay.canonical_move_decode
record_replay.short_replay
record_replay.score_atom
record_replay.logical_record_valid
record_replay.logical_record_malformed
record_replay.logical_record_truncated
attacked_defended.attacked
attacked_defended.defended
absolute_pin.absolute_pin_to_king
fork_double_attack.two_named_targets_after_move
discovered_attack_check.discovered_attack
discovered_attack_check.discovered_check
escape_square_control.controlled
escape_square_control.uncontrolled
passed_pawn.passed
passed_pawn.opposing_pawn_same_or_adjacent_ahead
open_semi_open_file.open
open_semi_open_file.semi_open
finite_promotion_race.complete_legal_line_or_tree
queen_or_rook_mating_geometry.queen_geometry
queen_or_rook_mating_geometry.rook_geometry
queen_or_rook_mating_geometry.all_relevant_replies
""".split())

OWNER_SIGNATURES = {
    "chess.setup_turn": (
        "SetupTurnInput := initial(WirePosition) | "
        "current_side(ReplayState, Side)"
    ),
    "chess.occupancy": "OccupancyInput(WirePosition, Square, OccupancyMatch)",
    "chess.move_legality": "MoveLegalityInput(ReplayState, Move)",
    "chess.control": "ControlInput(WirePosition, Side, Square)",
    "chess.defended": "DefendedInput(WirePosition, target, Defender)",
    "chess.king_check": "KingCheckInput(LocallyAdmissiblePosition, Side)",
    "chess.absolute_pin": "AbsolutePinInput(LocallyAdmissiblePosition, origin)",
    "chess.fork_double_attack": (
        "AfterMoveNamedTargetsInput(ReplayState, Move, targets: SquareSlice)"
    ),
    "chess.discovered_attack_check": (
        "DiscoveredLineInput(ReplayState, Move, slider_origin, target)"
    ),
    "chess.escape_square_control": (
        "EscapeControlInput(WirePosition, controlling_side, candidate)"
    ),
    "chess.passed_pawn": (
        "PassedPawnInput(LocallyAdmissiblePosition, pawn_square)"
    ),
    "chess.open_file": "OpenFileInput(WirePosition, File)",
    "chess.semi_open_file": "SemiOpenFileInput(WirePosition, Side, File)",
    "chess.finite_promotion_race": "FinitePromotionTree below",
    "chess.finite_mating_geometry": "FiniteMatingTree below",
    "chess.terminal_transition": "TerminalTransitionInput(ReplayState, Move)",
    "chess.history_claim": "ReplayState",
    "chess.declaration_event": "DeclarationEventInput(GameState, Event)",
    "chess.source_score_relation": "SourceScoreInput(MoveSlice, Score)",
    "chess.move_record_replay": (
        "MoveRecordInput := move_bytes(ByteSlice) | record(MoveSlice, Score)"
    ),
}

VARIANT_OWNER_ARITY = {
    "SetupTurnInput.initial": ("chess.setup_turn", 1),
    "SetupTurnInput.current_side": ("chess.setup_turn", 2),
    "OccupancyInput": ("chess.occupancy", 3),
    "MoveLegalityInput": ("chess.move_legality", 2),
    "ControlInput": ("chess.control", 3),
    "DefendedInput": ("chess.defended", 3),
    "KingCheckInput": ("chess.king_check", 2),
    "AbsolutePinInput": ("chess.absolute_pin", 2),
    "AfterMoveNamedTargetsInput": ("chess.fork_double_attack", 3),
    "DiscoveredLineInput": ("chess.discovered_attack_check", 4),
    "EscapeControlInput": ("chess.escape_square_control", 3),
    "PassedPawnInput": ("chess.passed_pawn", 2),
    "OpenFileInput": ("chess.open_file", 2),
    "SemiOpenFileInput": ("chess.semi_open_file", 3),
    "FinitePromotionTree": ("chess.finite_promotion_race", 1),
    "FiniteMatingTree": ("chess.finite_mating_geometry", 1),
    "TerminalTransitionInput": ("chess.terminal_transition", 2),
    "ReplayState": ("chess.history_claim", 1),
    "DeclarationEventInput": ("chess.declaration_event", 2),
    "SourceScoreInput": ("chess.source_score_relation", 2),
    "MoveRecordInput.move_bytes": ("chess.move_record_replay", 1),
    "MoveRecordInput.record": ("chess.move_record_replay", 2),
    "ByteSlice": ("content.stream_validation", 1),
}

INPUT_ARGUMENTS = {
    "setup_initial_position": ["authority.wire_position"],
    "initial_replay_and_side": [
        "authority.replay_state_exact_0_plies", "call.constant.side",
    ],
    "replay_and_current_side": [
        "authority.replay_state", "call.constant.side",
    ],
    "replay_move_legality": ["authority.replay_state", "bound.shown_move"],
    "replay_terminal_transition": [
        "authority.replay_state", "bound.shown_move",
    ],
    "replay_move_origin_occupancy": [
        "authority.replay_state.position", "bound.shown_move.origin",
        "call.constant.occupancy_match",
    ],
    "board_control_with_bound_origin": [
        "authority.wire_position", "authority.controlling_side",
        "bound.controller_origin",
    ],
    "board_bound_origin_occupancy": [
        "authority.wire_position", "bound.controller_origin",
        "call.constant.occupancy_match",
    ],
    "board_defended": [
        "authority.wire_position", "authority.target_square",
        "authority.defender",
    ],
    "board_pin_with_origin": [
        "authority.locally_admissible_position", "bound.controller_origin",
    ],
    "replay_move_destination_control_with_origin": [
        "authority.replay_state.position",
        "authority.replay_state.side_to_move", "bound.shown_move.target",
    ],
    "board_king_check": [
        "authority.locally_admissible_position", "authority.checked_side",
    ],
    "pre_move_moving_side_king_check": [
        "authority.replay_state.position",
        "authority.replay_state.side_to_move",
    ],
    "post_move_moving_side_king_check": [
        "derived.post_move_position", "authority.replay_state.side_to_move",
    ],
    "post_move_next_side_king_check": [
        "derived.post_move_position", "derived.post_move_side_to_move",
    ],
    "board_checked_king_control": [
        "authority.wire_position", "authority.opposing_side",
        "bound.checked_king_square",
    ],
    "replay_record_and_last_move": [
        "authority.move_slice_including_shown_move", "authority.score",
    ],
    "canonical_shown_move_bytes": [
        "derived.chess.encode_move.bound_shown_move",
    ],
    "replay_history": ["authority.replay_state"],
    "post_move_history": ["derived.post_move_replay_state"],
    "source_derived_history": [
        "derived.replay_state_from_source_move_slice",
    ],
    "game_state_and_event": ["authority.game_state", "authority.event"],
    "source_move_slice_and_score": [
        "derived.source.decode_game.move_slice", "derived.source.decode_game.score",
    ],
    "raw_content_bytes": ["authority.content_bytes"],
    "board_control": [
        "authority.wire_position", "authority.controlling_side",
        "authority.target_square",
    ],
    "board_escape_control": [
        "authority.wire_position", "authority.controlling_side",
        "authority.candidate_square",
    ],
    "board_passed_pawn": [
        "authority.locally_admissible_position", "authority.pawn_square",
    ],
    "board_open_file": ["authority.wire_position", "authority.file"],
    "board_semi_open_file": [
        "authority.wire_position", "authority.side", "authority.file",
    ],
    "replay_fork_targets": [
        "authority.replay_state", "bound.shown_move",
        "authority.named_target_squares",
    ],
    "replay_discovered_line": [
        "authority.replay_state", "bound.shown_move",
        "authority.slider_origin", "bound.line_target",
    ],
    "post_move_discovered_target_occupancy": [
        "derived.post_move_wire_position", "bound.line_target",
        "call.constant.occupancy_match",
    ],
    "finite_promotion_tree_rooted_at_authority": [
        "authority.finite_promotion_tree",
    ],
    "finite_mating_tree_rooted_at_authority": [
        "authority.finite_mating_tree",
    ],
}

OWNER_RESULTS = {
    "chess.setup_turn": {"bool_false", "bool_true"},
    "chess.occupancy": {"bool_false", "bool_true"},
    "chess.move_legality": {"move_illegal", "move_legal"},
    "chess.control": {"square_list"},
    "chess.defended": {"bool_false", "bool_true"},
    "chess.king_check": {"bool_false", "bool_true"},
    "chess.absolute_pin": {"bool_false", "bool_true"},
    "chess.fork_double_attack": {"bool_false", "bool_true"},
    "chess.discovered_attack_check": {"bool_false", "bool_true"},
    "chess.escape_square_control": {"bool_false", "bool_true"},
    "chess.passed_pawn": {"bool_false", "bool_true"},
    "chess.open_file": {"bool_false", "bool_true"},
    "chess.semi_open_file": {"bool_false", "bool_true"},
    "chess.finite_promotion_race": {"finite_race_result"},
    "chess.finite_mating_geometry": {"finite_mating_result"},
    "chess.terminal_transition": {
        "terminal_none", "terminal_checkmate", "terminal_stalemate",
        "terminal_common_dead",
    },
    "chess.history_claim": {"history_claim_fields"},
    "chess.declaration_event": {
        "declaration_accepted_game_status_agreed",
        "declaration_accepted_game_status_claimed_50_move",
        "declaration_accepted_game_status_claimed_threefold",
        "declaration_accepted_game_status_resigned", "declaration_rejected",
    },
    "chess.source_score_relation": {"source_accepted_terminal_none"},
    "chess.move_record_replay": {"move_decoded", "record_replayed"},
    "content.stream_validation": {"content_accepted", "content_rejected"},
}

REJECT_CODES = {
    "move_illegal_blocked": "CHESS_MOVE_BLOCKED",
    "move_illegal_friendly_destination": "CHESS_MOVE_FRIENDLY_DESTINATION",
    "move_illegal_self_check": "CHESS_MOVE_SELF_CHECK",
    "move_illegal_castling_right": "CHESS_MOVE_CASTLING_RIGHT",
    "move_illegal_castling_path": "CHESS_MOVE_CASTLING_PATH",
    "move_illegal_castling_from_check": "CHESS_MOVE_CASTLING_FROM_CHECK",
    "move_illegal_castling_through_check": "CHESS_MOVE_CASTLING_THROUGH_CHECK",
    "move_illegal_castling_into_check": "CHESS_MOVE_CASTLING_INTO_CHECK",
    "move_illegal_en_passant_target": "CHESS_MOVE_EN_PASSANT_TARGET",
    "move_illegal_promotion_missing": "CHESS_MOVE_PROMOTION_MISSING",
    "move_illegal_promotion_unneeded": "CHESS_MOVE_PROMOTION_UNNEEDED",
    "declaration_rejected_agreement_early": "CHESS_EVENT_AGREEMENT_TOO_EARLY",
    "declaration_rejected_threefold": "CHESS_EVENT_THREEFOLD_UNAVAILABLE",
    "declaration_rejected_fifty": "CHESS_EVENT_50_MOVE_UNAVAILABLE",
    "declaration_rejected_game_closed": "CHESS_GAME_CLOSED",
    "content_bad_kind_exact_field": "CONTENT_BAD_RECORD_KIND",
    "content_truncated_eof": "CONTENT_TRUNCATED",
}
REJECT_SPANS = {
    "content_bad_kind_exact_field": "exact_field",
    "content_truncated_eof": "eof",
}

FINITE_RELATIONS = {
    "candidate_move_effect": {
        value: {1, 2} for value in {
            "pawn_quiet", "pawn_capture", "pawn_initial_double",
            "king_capture", "castling", "en_passant", "promotion_quiet",
            "promotion_capture", "promotion_any", "promote_queen",
            "promote_rook", "promote_bishop", "promote_knight",
            "pawn_move", "capture",
        }
    },
    "replay_relation": {
        "one_legal_ply_extension": {2}, "same_shown_move": {2},
        "same_position_except_relevant_castling_right": {2},
        "same_final_position": {2},
        "replacement_piece_does_not_restore_right": {2},
        "different_replay_history": {2},
        "ineffective_ep_keys_equal_effective_ep_differs": {3},
    },
    "en_passant_context": {"expired_after_intervening_move": {1}},
    "material_class": {
        "recognized_common_dead": {1}, "king_two_knights_vs_king": {1},
    },
    "opposing_pawn_ahead": {
        "strictly_ahead_same_or_adjacent_file": {1},
    },
    "finite_mating_root_major_piece": {"queen": {1}, "rook": {1}},
}

FIXED_PROTOCOL = {
    "ceil75": {
        "input_min": 0, "input_max": 11, "numerator": 3,
        "denominator": 4, "rounding": "ceil",
        "boundary_inputs": list(range(12)),
        "boundary_outputs": [0, 1, 2, 3, 3, 4, 5, 6, 6, 7, 8, 9],
    },
    "family_acquisition": {
        "input_min": 0, "baseline_failure_min": 3,
        "baseline_failure_max": 6, "allowed_misses": 1,
        "negative_input_result": "invalid_protocol",
        "below_domain_result": "no_claim",
        "inside_domain_operation": "checked_b_minus_one",
        "above_domain_result": "invalid_protocol",
        "boundary_inputs": list(range(8)),
        "boundary_results": [
            "no_claim", "no_claim", "no_claim", "2", "3", "4", "5",
            "invalid_protocol",
        ],
    },
    "gates": {
        "essential_family": [5],
        "essential_individual": [4, ["king_safety"], "S", 2],
        "core3_family": [4],
        "core3_combined_individual": [4, 1],
        "delayed": [4, 4, ["king_safety"], "S", 2],
    },
    "assessment": [2, 2, 1, 1],
    "forms": [1, 3],
    "cue": [1, 1, 1, 2],
    "cut": {
        "order": [
            "optional_alternate_presentations", "repeated_heuristic_examples",
            "nonessential_exact_relation_repetitions",
            "lowest_priority_heuristics", "optional_interaction_branches",
            "nonessential_navigation", "profile_revision",
        ],
        "never_cut": [
            "shell_to_content_bootstrap", "complete_core1", "complete_core2",
            "all_four_promotions",
            "attack_self_check_castling_en_passant_history_boundaries",
            "score_vs_cause", "corruption_and_incomplete_record_teaching",
            "all_retained_core3_families",
            "passive_path_per_retained_concept",
            "exactly_sixty_four_complete_games", "final_reserve_and_headroom",
        ],
        "cut_must_preserve": [
            "authoring_and_assessment_minimums",
            "mandatory_stratum_coverage", "passive_completeness", "never_cut",
        ],
    },
}

TRANSFORMS = {
    "identity": ([1, 0, 0, 1], [0, 0], False),
    "file_reflection": ([-1, 0, 0, 1], [7, 0], False),
    "rank_reflection_color_swap": ([1, 0, 0, -1], [0, 7], True),
    "rotation_180_color_swap": ([-1, 0, 0, -1], [7, 7], True),
}

# These freeze human-readable TOML projections; direct checks below still own
# signatures, positional arguments, finite relations, bounds, and rejections.
PATTERN_DIGEST = "594dc68e0e8a8a31548bca0b7c75640715b39e65f802185b622e9c6c0de294de"
TRANSFORM_DIGEST = "80dac0d29304788ce8472313f0dff8e71f7e19bc01ffcfff8c4b12fb672a5f7b"
ROADMAP_DIGEST = "c57bf574c16764b40885fa41f458eea3fc00f998dcb836da5e6aff8b861b6fa5"
SUPPORTING_DIGEST = "f392721c0cc447a510615558a76a088a291c8a56385c49aac879a5981dbe9fde"


def digest(value: object) -> str:
    literal = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(literal.encode()).hexdigest()


def by_id(rows: list[dict]) -> dict[str, dict]:
    result = {row["id"]: row for row in rows}
    if len(result) != len(rows):
        raise ValueError("duplicate id")
    return result


def fixed_protocol(data: dict) -> dict:
    gate = data["gate"]
    assessment = data["assessment_minimums"]
    return {
        "ceil75": data["formula"]["ceil75"],
        "family_acquisition": data["formula"]["family_acquisition"],
        "gates": {
            "essential_family": [
                gate["essential_family"]["posttest_passes_min"],
            ],
            "essential_individual": [
                gate["essential_individual"]["learners_min"],
                gate["essential_individual"]["required_acquired_family_ids"],
                gate["essential_individual"]["required_acquired_set_id"],
                gate["essential_individual"]["required_acquired_set_min"],
            ],
            "core3_family": [gate["core3_family"]["posttest_passes_min"]],
            "core3_combined_individual": [
                gate["core3_combined_individual"]["learners_min"],
                gate["core3_combined_individual"]["baseline_failed_min"],
            ],
            "delayed": [
                gate["delayed"]["family_passes_min"],
                gate["delayed"]["learners_min"],
                gate["delayed"]["required_passed_family_ids"],
                gate["delayed"]["required_passed_set_id"],
                gate["delayed"]["required_passed_set_min"],
            ],
        },
        "assessment": [
            assessment["pretest_items_per_claimed_family"],
            assessment["posttest_items_per_family"],
            assessment["posttest_counterfactual_pairs_per_family"],
            assessment["delayed_items_per_essential_family"],
        ],
        "forms": [data["forms"]["forms_min"], data["forms"]["forms_max"]],
        "cue": [
            data["cue_audit"]["counterfactual_pairs_per_family_min"],
            data["cue_audit"]["strategy_errors_per_family_min"],
            data["cue_audit"]["strategy_max_correct_numerator"],
            data["cue_audit"]["strategy_max_correct_denominator"],
        ],
        "cut": {
            key: data["cut"][key]
            for key in ("order", "never_cut", "cut_must_preserve")
        },
    }


def pattern_projection(data: dict) -> list[dict]:
    bindings = by_id(data["input_binding"])
    contracts = by_id(data["result_contract"])
    return [
        {
            "id": pattern["id"],
            "authority_kind": pattern["authority_kind"],
            "relation": pattern["relation"],
            "case": [
                {
                    "id": case["id"],
                    "obligation": case["obligation"],
                    "call": [
                        {
                            "id": call["id"],
                            "owner_id": call["owner_id"],
                            "input_constant_ids": call["input_constant_ids"],
                            "input": bindings[call["input_binding_id"]],
                            "result": contracts[call["result_contract_id"]],
                        }
                        for call in case["call"]
                    ],
                }
                for case in pattern["case"]
            ],
        }
        for pattern in data["case_pattern"]
    ]


SUPPORTING_KEYS = (
    "taxonomy", "sets", "coverage", "authoring_minimums", "scoring",
    "leakage", "capacity", "m1_scope", "concept", "role", "generator",
    "family", "integrated_task", "critical_label", "cue_strategy",
)


def semantic_projection_is_valid(data: dict) -> bool:
    try:
        bindings = by_id(data["input_binding"])
        contracts = by_id(data["result_contract"])
        patterns = by_id(data["case_pattern"])
        if set(data) != ROOT_KEYS or REMOVED_DERIVED_KEYS & set(data):
            return False
        if set(patterns) != EXPECTED_PATTERN_IDS or len(patterns) != 88:
            return False
        if set(bindings) != set(INPUT_ARGUMENTS):
            return False
        for binding_id, binding in bindings.items():
            if set(binding) != {
                "id", "authority_kind", "owner_id", "input_variant_id",
                "argument_ids", "derivation_ref_ids",
            }:
                return False
            owner_id, arity = VARIANT_OWNER_ARITY[binding["input_variant_id"]]
            if owner_id != binding["owner_id"] or arity != len(binding["argument_ids"]):
                return False
            if binding["argument_ids"] != INPUT_ARGUMENTS[binding_id]:
                return False
        rejecting = {"move_illegal", "declaration_rejected", "content_rejected"}
        actual_rejects = {}
        for contract_id, contract in contracts.items():
            if set(contract) != {
                "id", "owner_ids", "result_variant_id", "payload_policy",
                "constraint_id", "reject_code_id", "span_class",
            }:
                return False
            if contract["payload_policy"] != "complete_exact_typed_value":
                return False
            if any(
                contract["result_variant_id"] not in OWNER_RESULTS[owner]
                for owner in contract["owner_ids"]
            ):
                return False
            if bool(contract["reject_code_id"]) != (
                contract["result_variant_id"] in rejecting
            ):
                return False
            if contract["reject_code_id"]:
                actual_rejects[contract_id] = contract["reject_code_id"]
            if contract["span_class"] != REJECT_SPANS.get(contract_id, "none"):
                return False
        if actual_rejects != REJECT_CODES:
            return False

        used_bindings = set()
        used_contracts = set()
        for pattern in patterns.values():
            if set(pattern) != {"id", "authority_kind", "relation", "case"}:
                return False
            case_ids = [case["id"] for case in pattern["case"]]
            if len(case_ids) != len(set(case_ids)):
                return False
            for relation in pattern["relation"]:
                refs = relation["case_ids"]
                if set(relation) != {"kind", "value", "case_ids"}:
                    return False
                if relation["kind"] != "replay_relation":
                    return False
                if relation["value"] not in FINITE_RELATIONS["replay_relation"]:
                    return False
                if len(refs) not in FINITE_RELATIONS["replay_relation"][relation["value"]]:
                    return False
                if len(refs) != len(set(refs)) or not set(refs) <= set(case_ids):
                    return False
            for case in pattern["case"]:
                if set(case) != {"id", "call", "obligation"}:
                    return False
                call_ids = [call["id"] for call in case["call"]]
                if len(call_ids) != len(set(call_ids)):
                    return False
                for call in case["call"]:
                    if set(call) != {
                        "id", "owner_id", "input_binding_id",
                        "input_constant_ids", "result_contract_id",
                    }:
                        return False
                    binding = bindings[call["input_binding_id"]]
                    contract = contracts[call["result_contract_id"]]
                    used_bindings.add(call["input_binding_id"])
                    used_contracts.add(call["result_contract_id"])
                    if call["owner_id"] != binding["owner_id"]:
                        return False
                    if call["owner_id"] not in contract["owner_ids"]:
                        return False
                    if binding["authority_kind"] != pattern["authority_kind"]:
                        return False
                for obligation in case["obligation"]:
                    refs = obligation["call_ids"]
                    if set(obligation) != {"kind", "value", "call_ids"}:
                        return False
                    if obligation["kind"] not in FINITE_RELATIONS:
                        return False
                    allowed = FINITE_RELATIONS[obligation["kind"]]
                    if obligation["value"] not in allowed:
                        return False
                    if len(refs) not in allowed[obligation["value"]]:
                        return False
                    if len(refs) != len(set(refs)) or not set(refs) <= set(call_ids):
                        return False
        if used_bindings != set(bindings) or used_contracts != set(contracts):
            return False
        return True
    except (KeyError, TypeError, ValueError):
        return False


def admitted(data: dict) -> bool:
    return all((
        semantic_projection_is_valid(data),
        fixed_protocol(data) == FIXED_PROTOCOL,
        digest(pattern_projection(data)) == PATTERN_DIGEST,
        digest([data["transform"], data["predicate_mapping"]]) == TRANSFORM_DIGEST,
        digest(data["roadmap_mirror"]) == ROADMAP_DIGEST,
        digest({key: data[key] for key in SUPPORTING_KEYS}) == SUPPORTING_DIGEST,
    ))


class CurriculumContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = OWNER.read_text()
        cls.data = tomllib.loads(cls.raw)

    def test_schema_has_no_derived_mirrors(self) -> None:
        self.assertEqual(set(self.data), ROOT_KEYS)
        self.assertFalse(REMOVED_DERIVED_KEYS & set(self.data))
        self.assertTrue(all(set(row) == {"id", "tier", "concept_id"}
                            for row in self.data["family"]))
        self.assertNotIn("predicate_ids", "\n".join(
            json.dumps(row, sort_keys=True) for row in self.data["family"]
        ))

    def test_owner_signatures_and_positional_arguments_are_exact(self) -> None:
        chess = (ROOT / "spec/chess-v0.md").read_text()
        canonical_chess = chess.replace("\\|", "|").replace("`", "")
        for owner_id, signature in OWNER_SIGNATURES.items():
            with self.subTest(owner=owner_id):
                self.assertIn(f"| {owner_id} | {signature} |", canonical_chess)
        self.assertIn(
            "content.stream_validation(raw_content_bytes: ByteSlice)",
            (ROOT / "spec/content-v0.md").read_text(),
        )
        self.assertIn(
            "decode_game(ByteSlice) -> GameRecord | SourceReject",
            (ROOT / "spec/source-v0.md").read_text(),
        )
        bindings = by_id(self.data["input_binding"])
        self.assertEqual(set(bindings), set(INPUT_ARGUMENTS))
        for binding_id, expected in INPUT_ARGUMENTS.items():
            with self.subTest(binding=binding_id):
                binding = bindings[binding_id]
                owner_id, arity = VARIANT_OWNER_ARITY[binding["input_variant_id"]]
                self.assertEqual(binding["owner_id"], owner_id)
                self.assertEqual(binding["argument_ids"], expected)
                self.assertEqual(len(expected), arity)
        self.assertEqual(
            bindings["initial_replay_and_side"]["argument_ids"][0],
            "authority.replay_state_exact_0_plies",
        )

    def test_all_88_irreducible_projections_are_frozen(self) -> None:
        self.assertTrue(semantic_projection_is_valid(self.data))
        self.assertEqual(digest(pattern_projection(self.data)), PATTERN_DIGEST)

    def test_result_compatibility_rejections_and_content_boundary(self) -> None:
        contracts = by_id(self.data["result_contract"])
        self.assertEqual(
            {cid: row["reject_code_id"] for cid, row in contracts.items()
             if row["reject_code_id"]},
            REJECT_CODES,
        )
        self.assertEqual(
            {cid: row["span_class"] for cid, row in contracts.items()
             if row["span_class"] != "none"},
            REJECT_SPANS,
        )
        logical = [
            row for row in self.data["case_pattern"]
            if row["id"].startswith("record_replay.logical_record_")
        ]
        self.assertEqual(
            {call["owner_id"] for row in logical for case in row["case"]
             for call in case["call"]},
            {"content.stream_validation"},
        )
        content_mapping = next(
            row for row in self.data["predicate_mapping"]
            if row["owner_id"] == "content.stream_validation"
        )
        self.assertEqual(content_mapping["transform_ids"], ["identity"])
        self.assertEqual(
            by_id(self.data["input_binding"])["raw_content_bytes"]["argument_ids"],
            ["authority.content_bytes"],
        )

    def test_fixed_arithmetic_gates_forms_cues_and_cuts(self) -> None:
        self.assertEqual(fixed_protocol(self.data), FIXED_PROTOCOL)
        ceil75 = self.data["formula"]["ceil75"]
        self.assertEqual(
            ceil75["boundary_outputs"],
            [(3 * value + 3) // 4 for value in range(12)],
        )
        acquisition = self.data["formula"]["family_acquisition"]
        self.assertEqual(
            acquisition["boundary_results"],
            ["no_claim" if value < 3 else str(value - 1) if value <= 6
             else "invalid_protocol" for value in range(8)],
        )

    def test_transform_and_checked_mirror_projections_are_frozen(self) -> None:
        actual = {
            row["id"]: (row["matrix"], row["offset"], row["swap_colors_and_sides"])
            for row in self.data["transform"]
        }
        self.assertEqual(actual, TRANSFORMS)
        self.assertEqual(
            digest([self.data["transform"], self.data["predicate_mapping"]]),
            TRANSFORM_DIGEST,
        )
        self.assertEqual(digest(self.data["roadmap_mirror"]), ROADMAP_DIGEST)
        self.assertEqual(
            digest({key: self.data[key] for key in SUPPORTING_KEYS}),
            SUPPORTING_DIGEST,
        )
        self.assertEqual(self.data["roadmap_mirror"]["kind"], "checked_mirror")
        self.assertEqual(self.data["roadmap_mirror"]["owner"], "docs/roadmap.md")

    def test_adversarial_contract_mutations_are_rejected(self) -> None:
        def pattern(data: dict, pattern_id: str) -> dict:
            return next(row for row in data["case_pattern"] if row["id"] == pattern_id)

        def swap_results(data: dict, first: tuple[str, int], second: tuple[str, int]) -> None:
            a = pattern(data, first[0])["case"][first[1]]["call"][0]
            b = pattern(data, second[0])["case"][second[1]]["call"][0]
            a["result_contract_id"], b["result_contract_id"] = (
                b["result_contract_id"], a["result_contract_id"]
            )

        mutations = {
            "terminal_mate_results_swapped": lambda data: swap_results(
                data, ("termination_score.checkmate", 0),
                ("termination_score.stalemate", 0),
            ),
            "escape_results_swapped": lambda data: swap_results(
                data, ("escape_square_control.controlled", 0),
                ("escape_square_control.uncontrolled", 0),
            ),
            "passed_pawn_results_swapped": lambda data: swap_results(
                data, ("passed_pawn.passed", 0),
                ("passed_pawn.opposing_pawn_same_or_adjacent_ahead", 0),
            ),
            "halfmove_99_100_results_swapped": lambda data: swap_results(
                data, ("position_history_draw.halfmove_99_100", 0),
                ("position_history_draw.halfmove_99_100", 1),
            ),
            "logical_valid_malformed_results_swapped": lambda data: swap_results(
                data, ("record_replay.logical_record_valid", 0),
                ("record_replay.logical_record_malformed", 0),
            ),
            "pattern_id": lambda data: data["case_pattern"][0].__setitem__("id", "x"),
            "authority": lambda data: data["case_pattern"][0].__setitem__(
                "authority_kind", "content_bytes"
            ),
            "case_order": lambda data: pattern(
                data, "position_history_draw.halfmove_99_100"
            )["case"].reverse(),
            "call_owner": lambda data: pattern(
                data, "king_safety.check_evasion"
            )["case"][0]["call"][0].__setitem__("owner_id", "chess.control"),
            "argument_order": lambda data: next(
                row for row in data["input_binding"]
                if row["id"] == "source_move_slice_and_score"
            )["argument_ids"].reverse(),
            "initial_even_replay": lambda data: next(
                row for row in data["input_binding"]
                if row["id"] == "initial_replay_and_side"
            )["argument_ids"].__setitem__(0, "authority.replay_state_even_plies"),
            "finite_relation": lambda data: pattern(
                data, "en_passant.expiry"
            )["case"][0]["obligation"][0].__setitem__("value", "invented"),
            "ceil75_numerator": lambda data: data["formula"]["ceil75"].__setitem__("numerator", 2),
            "ceil75_denominator": lambda data: data["formula"]["ceil75"].__setitem__("denominator", 3),
            "ceil75_rounding": lambda data: data["formula"]["ceil75"].__setitem__("rounding", "floor"),
            "ceil75_boundary": lambda data: data["formula"]["ceil75"]["boundary_outputs"].__setitem__(11, 8),
            "acquisition_input_domain": lambda data: data["formula"]["family_acquisition"].__setitem__("input_min", 1),
            "acquisition_min": lambda data: data["formula"]["family_acquisition"].__setitem__("baseline_failure_min", 2),
            "acquisition_max": lambda data: data["formula"]["family_acquisition"].__setitem__("baseline_failure_max", 7),
            "acquisition_allowed_misses": lambda data: data["formula"]["family_acquisition"].__setitem__("allowed_misses", 2),
            "acquisition_no_claim": lambda data: data["formula"]["family_acquisition"]["boundary_results"].__setitem__(2, "2"),
            "acquisition_invalid": lambda data: data["formula"]["family_acquisition"]["boundary_results"].__setitem__(7, "6"),
            "essential_family_passes": lambda data: data["gate"]["essential_family"].__setitem__("posttest_passes_min", 4),
            "essential_learners": lambda data: data["gate"]["essential_individual"].__setitem__("learners_min", 3),
            "essential_s_min": lambda data: data["gate"]["essential_individual"].__setitem__("required_acquired_set_min", 1),
            "essential_king_safety": lambda data: data["gate"]["essential_individual"].__setitem__("required_acquired_family_ids", []),
            "core3_family_passes": lambda data: data["gate"]["core3_family"].__setitem__("posttest_passes_min", 3),
            "core3_learners": lambda data: data["gate"]["core3_combined_individual"].__setitem__("learners_min", 3),
            "core3_baseline": lambda data: data["gate"]["core3_combined_individual"].__setitem__("baseline_failed_min", 0),
            "delayed_family_passes": lambda data: data["gate"]["delayed"].__setitem__("family_passes_min", 3),
            "delayed_learners": lambda data: data["gate"]["delayed"].__setitem__("learners_min", 3),
            "delayed_s_min": lambda data: data["gate"]["delayed"].__setitem__("required_passed_set_min", 1),
            "delayed_king_safety": lambda data: data["gate"]["delayed"].__setitem__("required_passed_family_ids", []),
            "pretest_minimum": lambda data: data["assessment_minimums"].__setitem__("pretest_items_per_claimed_family", 1),
            "posttest_minimum": lambda data: data["assessment_minimums"].__setitem__("posttest_items_per_family", 1),
            "delayed_minimum": lambda data: data["assessment_minimums"].__setitem__("delayed_items_per_essential_family", 0),
            "counterfactual_minimum": lambda data: data["assessment_minimums"].__setitem__("posttest_counterfactual_pairs_per_family", 0),
            "forms_min": lambda data: data["forms"].__setitem__("forms_min", 0),
            "forms_max": lambda data: data["forms"].__setitem__("forms_max", 4),
            "cue_pair_minimum": lambda data: data["cue_audit"].__setitem__("counterfactual_pairs_per_family_min", 0),
            "cue_errors_per_family": lambda data: data["cue_audit"].__setitem__("strategy_errors_per_family_min", 0),
            "cue_max_correct_numerator": lambda data: data["cue_audit"].__setitem__("strategy_max_correct_numerator", 2),
            "cue_max_correct_denominator": lambda data: data["cue_audit"].__setitem__("strategy_max_correct_denominator", 3),
            "cut_order": lambda data: data["cut"]["order"].reverse(),
            "cut_never_cut": lambda data: data["cut"]["never_cut"].pop(),
            "cut_preservation": lambda data: data["cut"]["cut_must_preserve"].pop(),
        }
        self.assertTrue(admitted(self.data))
        for name, mutate in mutations.items():
            with self.subTest(mutation=name):
                candidate = copy.deepcopy(self.data)
                mutate(candidate)
                self.assertFalse(admitted(candidate))


if __name__ == "__main__":
    unittest.main()
