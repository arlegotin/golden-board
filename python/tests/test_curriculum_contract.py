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
    "cue_strategy", "finite_relation", "input_binding", "result_contract",
    "case_pattern",
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

VARIANT_ARGUMENT_TYPES = {
    "SetupTurnInput.initial": ["WirePosition"],
    "SetupTurnInput.current_side": ["ReplayState", "Side"],
    "OccupancyInput": ["WirePosition", "Square", "OccupancyMatch"],
    "MoveLegalityInput": ["ReplayState", "Move"],
    "ControlInput": ["WirePosition", "Side", "Square"],
    "DefendedInput": ["WirePosition", "Square", "Defender"],
    "KingCheckInput": ["LocallyAdmissiblePosition", "Side"],
    "AbsolutePinInput": ["LocallyAdmissiblePosition", "Square"],
    "AfterMoveNamedTargetsInput": ["ReplayState", "Move", "SquareSlice"],
    "DiscoveredLineInput": ["ReplayState", "Move", "Square", "Square"],
    "EscapeControlInput": ["WirePosition", "Side", "Square"],
    "PassedPawnInput": ["LocallyAdmissiblePosition", "Square"],
    "OpenFileInput": ["WirePosition", "File"],
    "SemiOpenFileInput": ["WirePosition", "Side", "File"],
    "FinitePromotionTree": ["FinitePromotionTree"],
    "FiniteMatingTree": ["FiniteMatingTree"],
    "TerminalTransitionInput": ["ReplayState", "Move"],
    "ReplayState": ["ReplayState"],
    "DeclarationEventInput": ["GameState", "Event"],
    "SourceScoreInput": ["MoveSlice", "Score"],
    "MoveRecordInput.move_bytes": ["ByteSlice"],
    "MoveRecordInput.record": ["MoveSlice", "Score"],
    "ByteSlice": ["ByteSlice"],
}

INPUT_ARGUMENTS = {
    "setup_initial_position": ["WirePosition@authority:authority.wire_position"],
    "initial_replay_and_side": ["ReplayState@derived:authority.replay_state_exact_0_plies", "Side@call_constant:call.input_constants[0]"],
    "replay_and_current_side": ["ReplayState@derived:authority.replay_state", "Side@call_constant:call.input_constants[0]"],
    "replay_move_legality": ["ReplayState@derived:authority.replay_state", "Move@bound:bound.shown_move"],
    "replay_terminal_transition": ["ReplayState@derived:authority.replay_state", "Move@bound:bound.shown_move"],
    "replay_move_origin_occupancy": ["WirePosition@derived:authority.replay_wire_position", "Square@bound_projection:bound.shown_move.origin", "OccupancyMatch@call_constant:call.input_constants[0]"],
    "board_control_with_bound_origin": ["WirePosition@authority:authority.wire_position", "Side@authority:authority.controlling_side", "Square@bound:bound.controller_origin"],
    "board_bound_origin_occupancy": ["WirePosition@authority:authority.wire_position", "Square@bound:bound.controller_origin", "OccupancyMatch@call_constant:call.input_constants[0]"],
    "board_defended": ["WirePosition@authority:authority.wire_position", "Square@authority:authority.target_square", "Defender@authority:authority.defender"],
    "board_pin_with_origin": ["LocallyAdmissiblePosition@derived:authority.locally_admissible_position", "Square@bound:bound.controller_origin"],
    "replay_move_destination_control_with_origin": ["WirePosition@derived:authority.replay_wire_position", "Side@derived:authority.replay_side_to_move", "Square@bound_projection:bound.shown_move.target"],
    "board_king_check": ["LocallyAdmissiblePosition@derived:authority.locally_admissible_position", "Side@authority:authority.checked_side"],
    "pre_move_moving_side_king_check": ["LocallyAdmissiblePosition@derived:authority.replay_local_position", "Side@derived:authority.replay_side_to_move"],
    "post_move_moving_side_king_check": ["LocallyAdmissiblePosition@derived:derived.post_move_local_position", "Side@derived:authority.replay_side_to_move"],
    "post_move_next_side_king_check": ["LocallyAdmissiblePosition@derived:derived.post_move_local_position", "Side@derived:derived.post_move_side_to_move"],
    "board_checked_king_control": ["WirePosition@authority:authority.wire_position", "Side@authority:authority.opposing_side", "Square@bound:bound.checked_king_square"],
    "replay_record_and_last_move": ["MoveSlice@authority:authority.move_slice_including_shown_move", "Score@authority:authority.case_score"],
    "canonical_shown_move_bytes": ["ByteSlice@derived:derived.shown_move_bytes"],
    "replay_history": ["ReplayState@derived:authority.replay_state"],
    "post_move_history": ["ReplayState@derived:derived.post_move_replay_state"],
    "source_derived_history": ["ReplayState@derived:derived.source_replay_state"],
    "game_state_and_event": ["GameState@derived:authority.game_state", "Event@authority:authority.event"],
    "source_move_slice_and_score": ["MoveSlice@derived:derived.source_move_slice", "Score@call_constant:call.input_constants[0]"],
    "source_move_slice_and_decoded_score": ["MoveSlice@derived:derived.source_move_slice", "Score@derived:derived.source_score"],
    "raw_content_bytes": ["ByteSlice@authority:authority.content_bytes"],
    "board_control": ["WirePosition@authority:authority.wire_position", "Side@authority:authority.controlling_side", "Square@authority:authority.target_square"],
    "board_escape_control": ["WirePosition@authority:authority.wire_position", "Side@authority:authority.controlling_side", "Square@authority:authority.candidate_square"],
    "board_passed_pawn": ["LocallyAdmissiblePosition@derived:authority.locally_admissible_position", "Square@authority:authority.pawn_square"],
    "board_open_file": ["WirePosition@authority:authority.wire_position", "File@authority:authority.file"],
    "board_semi_open_file": ["WirePosition@authority:authority.wire_position", "Side@authority:authority.side", "File@authority:authority.file"],
    "replay_fork_targets": ["ReplayState@derived:authority.replay_state", "Move@bound:bound.shown_move", "SquareSlice@authority:authority.named_target_squares"],
    "replay_discovered_line": ["ReplayState@derived:authority.replay_state", "Move@bound:bound.shown_move", "Square@authority:authority.slider_origin", "Square@bound:bound.line_target"],
    "post_move_discovered_target_occupancy": ["WirePosition@derived:derived.post_move_wire_position", "Square@bound:bound.line_target", "OccupancyMatch@call_constant:call.input_constants[0]"],
    "finite_promotion_tree_rooted_at_authority": ["FinitePromotionTree@authority:authority.finite_promotion_tree"],
    "finite_mating_tree_rooted_at_authority": ["FiniteMatingTree@authority:authority.finite_mating_tree"],
}

DERIVATIONS = {
    "setup_initial_position": [
        "owner_call:chess.validate_local(WirePosition@authority.wire_position)"
        "->LocallyAdmissiblePosition@authority.locally_admissible_position",
    ],
    "initial_replay_and_side": [
        "owner_call:chess.replay_from_start(MoveSlice@authority.move_slice_exact_0_plies)"
        "->ReplayState@authority.replay_state_exact_0_plies",
    ],
    "replay_and_current_side": [
        "owner_call:chess.replay_from_start(MoveSlice@authority.move_slice)"
        "->ReplayState@authority.replay_state",
    ],
    "replay_move_legality": [
        "owner_call:chess.replay_from_start(MoveSlice@authority.move_slice)"
        "->ReplayState@authority.replay_state",
    ],
    "replay_terminal_transition": [
        "owner_call:chess.replay_from_start(MoveSlice@authority.move_slice)"
        "->ReplayState@authority.replay_state",
    ],
    "replay_move_origin_occupancy": [
        "owner_call:chess.replay_from_start(MoveSlice@authority.move_slice)"
        "->ReplayState@authority.replay_state",
        "typed_projection:projection.replay_wire_position(ReplayState@authority.replay_state)"
        "->WirePosition@authority.replay_wire_position",
    ],
    "board_control_with_bound_origin": [
        "owner_call:chess.validate_local(WirePosition@authority.wire_position)"
        "->LocallyAdmissiblePosition@authority.locally_admissible_position",
    ],
    "board_bound_origin_occupancy": [
        "owner_call:chess.validate_local(WirePosition@authority.wire_position)"
        "->LocallyAdmissiblePosition@authority.locally_admissible_position",
    ],
    "board_defended": [
        "owner_call:chess.validate_local(WirePosition@authority.wire_position)"
        "->LocallyAdmissiblePosition@authority.locally_admissible_position",
    ],
    "board_pin_with_origin": [
        "owner_call:chess.validate_local(WirePosition@authority.wire_position)"
        "->LocallyAdmissiblePosition@authority.locally_admissible_position",
    ],
    "replay_move_destination_control_with_origin": [
        "owner_call:chess.replay_from_start(MoveSlice@authority.move_slice)"
        "->ReplayState@authority.replay_state",
        "typed_projection:projection.replay_wire_position(ReplayState@authority.replay_state)"
        "->WirePosition@authority.replay_wire_position",
        "typed_projection:projection.replay_side_to_move(ReplayState@authority.replay_state)"
        "->Side@authority.replay_side_to_move",
    ],
    "board_king_check": [
        "owner_call:chess.validate_local(WirePosition@authority.wire_position)"
        "->LocallyAdmissiblePosition@authority.locally_admissible_position",
    ],
    "pre_move_moving_side_king_check": [
        "owner_call:chess.replay_from_start(MoveSlice@authority.move_slice)"
        "->ReplayState@authority.replay_state",
        "typed_projection:projection.replay_local_position(ReplayState@authority.replay_state)"
        "->LocallyAdmissiblePosition@authority.replay_local_position",
        "typed_projection:projection.replay_side_to_move(ReplayState@authority.replay_state)"
        "->Side@authority.replay_side_to_move",
    ],
    "post_move_moving_side_king_check": [
        "owner_call:chess.replay_from_start(MoveSlice@authority.move_slice)"
        "->ReplayState@authority.replay_state",
        "owner_call:chess.apply_move(ReplayState@authority.replay_state, "
        "Move@bound.shown_move)->ReplayState@derived.post_move_replay_state",
        "typed_projection:projection.replay_local_position(ReplayState@derived.post_move_replay_state)"
        "->LocallyAdmissiblePosition@derived.post_move_local_position",
        "typed_projection:projection.replay_side_to_move(ReplayState@authority.replay_state)"
        "->Side@authority.replay_side_to_move",
    ],
    "post_move_next_side_king_check": [
        "owner_call:chess.replay_from_start(MoveSlice@authority.move_slice)"
        "->ReplayState@authority.replay_state",
        "owner_call:chess.apply_move(ReplayState@authority.replay_state, "
        "Move@bound.shown_move)->ReplayState@derived.post_move_replay_state",
        "typed_projection:projection.replay_local_position(ReplayState@derived.post_move_replay_state)"
        "->LocallyAdmissiblePosition@derived.post_move_local_position",
        "typed_projection:projection.replay_side_to_move(ReplayState@derived.post_move_replay_state)"
        "->Side@derived.post_move_side_to_move",
    ],
    "board_checked_king_control": [
        "owner_call:chess.validate_local(WirePosition@authority.wire_position)"
        "->LocallyAdmissiblePosition@authority.locally_admissible_position",
    ],
    "replay_record_and_last_move": [
        "owner_call:chess.replay_from_start(MoveSlice@authority.move_slice_including_shown_move)"
        "->ReplayState@derived.record_replay_state",
    ],
    "canonical_shown_move_bytes": [
        "owner_call:chess.replay_from_start(MoveSlice@authority.move_slice)"
        "->ReplayState@authority.replay_state",
        "owner_call:chess.encode_move(Move@bound.shown_move)"
        "->ByteSlice@derived.shown_move_bytes",
    ],
    "replay_history": [
        "owner_call:chess.replay_from_start(MoveSlice@authority.move_slice)"
        "->ReplayState@authority.replay_state",
    ],
    "post_move_history": [
        "owner_call:chess.replay_from_start(MoveSlice@authority.move_slice)"
        "->ReplayState@authority.replay_state",
        "owner_call:chess.apply_move(ReplayState@authority.replay_state, "
        "Move@bound.shown_move)->ReplayState@derived.post_move_replay_state",
    ],
    "source_derived_history": [
        "owner_call:source.decode_game(ByteSlice@authority.source_game_bytes)"
        "->GameRecord@derived.source_game_record",
        "typed_projection:projection.source_move_slice(GameRecord@derived.source_game_record)"
        "->MoveSlice@derived.source_move_slice",
        "owner_call:chess.replay_from_start(MoveSlice@derived.source_move_slice)"
        "->ReplayState@derived.source_replay_state",
    ],
    "game_state_and_event": [
        "owner_call:chess.new_game()->GameState@derived.initial_game_state",
        "owner_call:chess.apply_event(GameState@authority.prior_game_state, "
        "Event@authority.prior_event)->GameState@authority.game_state",
    ],
    "source_move_slice_and_score": [
        "owner_call:source.decode_game(ByteSlice@authority.source_game_bytes)"
        "->GameRecord@derived.source_game_record",
        "typed_projection:projection.source_move_slice(GameRecord@derived.source_game_record)"
        "->MoveSlice@derived.source_move_slice",
    ],
    "source_move_slice_and_decoded_score": [
        "owner_call:source.decode_game(ByteSlice@authority.source_game_bytes)"
        "->GameRecord@derived.source_game_record",
        "typed_projection:projection.source_move_slice(GameRecord@derived.source_game_record)"
        "->MoveSlice@derived.source_move_slice",
        "typed_projection:projection.source_score(GameRecord@derived.source_game_record)"
        "->Score@derived.source_score",
    ],
    "raw_content_bytes": [],
    "board_control": [
        "owner_call:chess.validate_local(WirePosition@authority.wire_position)"
        "->LocallyAdmissiblePosition@authority.locally_admissible_position",
    ],
    "board_escape_control": [
        "owner_call:chess.validate_local(WirePosition@authority.wire_position)"
        "->LocallyAdmissiblePosition@authority.locally_admissible_position",
    ],
    "board_passed_pawn": [
        "owner_call:chess.validate_local(WirePosition@authority.wire_position)"
        "->LocallyAdmissiblePosition@authority.locally_admissible_position",
    ],
    "board_open_file": [
        "owner_call:chess.validate_local(WirePosition@authority.wire_position)"
        "->LocallyAdmissiblePosition@authority.locally_admissible_position",
    ],
    "board_semi_open_file": [
        "owner_call:chess.validate_local(WirePosition@authority.wire_position)"
        "->LocallyAdmissiblePosition@authority.locally_admissible_position",
    ],
    "replay_fork_targets": [
        "owner_call:chess.replay_from_start(MoveSlice@authority.move_slice)"
        "->ReplayState@authority.replay_state",
    ],
    "replay_discovered_line": [
        "owner_call:chess.replay_from_start(MoveSlice@authority.move_slice)"
        "->ReplayState@authority.replay_state",
    ],
    "post_move_discovered_target_occupancy": [
        "owner_call:chess.replay_from_start(MoveSlice@authority.move_slice)"
        "->ReplayState@authority.replay_state",
        "owner_call:chess.apply_move(ReplayState@authority.replay_state, "
        "Move@bound.shown_move)->ReplayState@derived.post_move_replay_state",
        "typed_projection:projection.replay_wire_position(ReplayState@derived.post_move_replay_state)"
        "->WirePosition@derived.post_move_wire_position",
    ],
    "finite_promotion_tree_rooted_at_authority": [
        "owner_call:chess.replay_from_start("
        "MoveSlice@authority.finite_promotion_tree.root_move_slice)"
        "->ReplayState@authority.finite_promotion_tree.root",
    ],
    "finite_mating_tree_rooted_at_authority": [
        "owner_call:chess.replay_from_start("
        "MoveSlice@authority.finite_mating_tree.root_move_slice)"
        "->ReplayState@authority.finite_mating_tree.root",
    ],
}

DERIVATION_SIGNATURES = {
    "chess.validate_local": ("owner_call", ["WirePosition"], "LocallyAdmissiblePosition"),
    "chess.replay_from_start": ("owner_call", ["MoveSlice"], "ReplayState"),
    "chess.apply_move": ("owner_call", ["ReplayState", "Move"], "ReplayState"),
    "chess.encode_move": ("owner_call", ["Move"], "ByteSlice"),
    "chess.new_game": ("owner_call", [], "GameState"),
    "chess.apply_event": ("owner_call", ["GameState", "Event"], "GameState"),
    "source.decode_game": ("owner_call", ["ByteSlice"], "GameRecord"),
    "projection.replay_wire_position": ("typed_projection", ["ReplayState"], "WirePosition"),
    "projection.replay_local_position": ("typed_projection", ["ReplayState"], "LocallyAdmissiblePosition"),
    "projection.replay_side_to_move": ("typed_projection", ["ReplayState"], "Side"),
    "projection.source_move_slice": ("typed_projection", ["GameRecord"], "MoveSlice"),
    "projection.source_score": ("typed_projection", ["GameRecord"], "Score"),
}

RELATION_SHAPES = {
    "candidate_move_effect": (
        "case", "call_ids", (1, 2),
        frozenset({
            "replay_move_legality", "replay_terminal_transition",
            "replay_record_and_last_move", "post_move_history",
        }),
    ),
    "replay_relation": ("pattern", "case_ids", (2, 3), frozenset()),
    "en_passant_context": (
        "case", "call_ids", (1,), frozenset({"replay_move_legality"}),
    ),
    "material_class": (
        "case", "call_ids", (1,), frozenset({"replay_terminal_transition"}),
    ),
    "opposing_pawn_ahead": (
        "case", "call_ids", (1,), frozenset({"board_passed_pawn"}),
    ),
    "finite_mating_root_major_piece": (
        "case", "call_ids", (1,),
        frozenset({"finite_mating_tree_rooted_at_authority"}),
    ),
}

RELATION_FACT_DOMAINS = {
    "mover_kind": ("PieceKind", frozenset({"pawn", "king", "any"})),
    "move_kind": ("MoveKind", frozenset({
        "quiet", "capture", "initial_double", "castling", "en_passant",
        "promotion_quiet", "promotion_capture", "promotion", "any",
    })),
    "promotion_kind": ("PromotionKind", frozenset({
        "none", "any", "queen", "rook", "bishop", "knight",
    })),
    "ply_delta": ("i8", frozenset({"1"})),
    "shown_move_equal": ("bool", frozenset({"true"})),
    "position_difference": (
        "FieldSet", frozenset({"relevant_castling_right_only"}),
    ),
    "castling_entitlement_restored": ("bool", frozenset({"false"})),
    "final_position_equal": ("bool", frozenset({"true"})),
    "history_equal": ("bool", frozenset({"false"})),
    "ineffective_ep_key_equal": ("bool", frozenset({"true"})),
    "effective_ep_key_equal": ("bool", frozenset({"false"})),
    "intervening_legal_plies_min": ("u16", frozenset({"1"})),
    "nominal_target": ("EnPassantFact", frozenset({"none"})),
    "selected_common_dead_class": ("bool", frozenset({"true"})),
    "common_dead": ("bool", frozenset({"true", "false"})),
    "material_signature": (
        "MaterialSignature", frozenset({"king_two_knights_vs_king"}),
    ),
    "opposing_pawn_exists": ("bool", frozenset({"true"})),
    "relative_rank_relation": ("RankRelation", frozenset({"strictly_ahead"})),
    "absolute_file_delta_max": ("u8", frozenset({"1"})),
    "major_piece_kind": ("PieceKind", frozenset({"queen", "rook"})),
    "major_piece_count": ("u8", frozenset({"1"})),
    "other_nonking_count": ("u8", frozenset({"0"})),
    "major_piece_side_is_mating_side": ("bool", frozenset({"true"})),
}

# (pattern, scope/case, relation index, kind, exact operand IDs) maps to the
# only canonical result and ordered typed facts for those operands.
CANONICAL_RELATIONS = {
    ("setup_turn.alternating_turn", "pattern", 0, "replay_relation", ("before", "after")): ("one_legal_ply_extension", (("ply_delta", "i8", "1"),)),
    ("ordinary_move_capture.pawn_forward_vs_capture", "quiet", 0, "candidate_move_effect", ("legality",)): ("pawn_quiet", (("mover_kind", "PieceKind", "pawn"), ("move_kind", "MoveKind", "quiet"), ("promotion_kind", "PromotionKind", "none"))),
    ("ordinary_move_capture.pawn_forward_vs_capture", "capture", 0, "candidate_move_effect", ("legality",)): ("pawn_capture", (("mover_kind", "PieceKind", "pawn"), ("move_kind", "MoveKind", "capture"), ("promotion_kind", "PromotionKind", "none"))),
    ("ordinary_move_capture.pawn_initial_double", "double", 0, "candidate_move_effect", ("legality",)): ("pawn_initial_double", (("mover_kind", "PieceKind", "pawn"), ("move_kind", "MoveKind", "initial_double"), ("promotion_kind", "PromotionKind", "none"))),
    ("king_safety.king_capture_safety", "safe_capture", 0, "candidate_move_effect", ("legality",)): ("king_capture", (("mover_kind", "PieceKind", "king"), ("move_kind", "MoveKind", "capture"), ("promotion_kind", "PromotionKind", "none"))),
    ("king_safety.king_capture_safety", "unsafe_capture", 0, "candidate_move_effect", ("legality",)): ("king_capture", (("mover_kind", "PieceKind", "king"), ("move_kind", "MoveKind", "capture"), ("promotion_kind", "PromotionKind", "none"))),
    ("castling.rights", "pattern", 0, "replay_relation", ("right_present", "right_absent")): ("same_shown_move", (("shown_move_equal", "bool", "true"),)),
    ("castling.rights", "pattern", 1, "replay_relation", ("right_present", "right_absent")): ("same_position_except_relevant_castling_right", (("position_difference", "FieldSet", "relevant_castling_right_only"),)),
    ("castling.entitled_king_and_rook", "pattern", 0, "replay_relation", ("entitled", "replacement")): ("same_shown_move", (("shown_move_equal", "bool", "true"),)),
    ("castling.entitled_king_and_rook", "pattern", 1, "replay_relation", ("entitled", "replacement")): ("replacement_piece_does_not_restore_right", (("castling_entitlement_restored", "bool", "false"),)),
    ("castling.rook_relocation", "castle", 0, "candidate_move_effect", ("legality", "record")): ("castling", (("mover_kind", "PieceKind", "king"), ("move_kind", "MoveKind", "castling"), ("promotion_kind", "PromotionKind", "none"))),
    ("en_passant.immediate_window", "immediate", 0, "candidate_move_effect", ("legality",)): ("en_passant", (("mover_kind", "PieceKind", "pawn"), ("move_kind", "MoveKind", "en_passant"), ("promotion_kind", "PromotionKind", "none"))),
    ("en_passant.expiry", "expired", 0, "en_passant_context", ("legality",)): ("expired_after_intervening_move", (("intervening_legal_plies_min", "u16", "1"), ("nominal_target", "EnPassantFact", "none"))),
    ("en_passant.captured_pawn_removal", "capture", 0, "candidate_move_effect", ("legality", "record")): ("en_passant", (("mover_kind", "PieceKind", "pawn"), ("move_kind", "MoveKind", "en_passant"), ("promotion_kind", "PromotionKind", "none"))),
    ("en_passant.self_check", "self_check", 0, "candidate_move_effect", ("legality",)): ("en_passant", (("mover_kind", "PieceKind", "pawn"), ("move_kind", "MoveKind", "en_passant"), ("promotion_kind", "PromotionKind", "none"))),
    ("promotion.quiet_promotion", "quiet", 0, "candidate_move_effect", ("legality",)): ("promotion_quiet", (("mover_kind", "PieceKind", "pawn"), ("move_kind", "MoveKind", "promotion_quiet"), ("promotion_kind", "PromotionKind", "any"))),
    ("promotion.capture_promotion", "capture", 0, "candidate_move_effect", ("legality",)): ("promotion_capture", (("mover_kind", "PieceKind", "pawn"), ("move_kind", "MoveKind", "promotion_capture"), ("promotion_kind", "PromotionKind", "any"))),
    ("promotion.promote_queen", "queen", 0, "candidate_move_effect", ("legality",)): ("promote_queen", (("mover_kind", "PieceKind", "pawn"), ("move_kind", "MoveKind", "promotion"), ("promotion_kind", "PromotionKind", "queen"))),
    ("promotion.promote_rook", "rook", 0, "candidate_move_effect", ("legality",)): ("promote_rook", (("mover_kind", "PieceKind", "pawn"), ("move_kind", "MoveKind", "promotion"), ("promotion_kind", "PromotionKind", "rook"))),
    ("promotion.promote_bishop", "bishop", 0, "candidate_move_effect", ("legality",)): ("promote_bishop", (("mover_kind", "PieceKind", "pawn"), ("move_kind", "MoveKind", "promotion"), ("promotion_kind", "PromotionKind", "bishop"))),
    ("promotion.promote_knight", "knight", 0, "candidate_move_effect", ("legality",)): ("promote_knight", (("mover_kind", "PieceKind", "pawn"), ("move_kind", "MoveKind", "promotion"), ("promotion_kind", "PromotionKind", "knight"))),
    ("promotion.check_after_promotion", "check", 0, "candidate_move_effect", ("legality", "record")): ("promotion_any", (("mover_kind", "PieceKind", "pawn"), ("move_kind", "MoveKind", "promotion"), ("promotion_kind", "PromotionKind", "any"))),
    ("promotion.mate_after_promotion", "mate", 0, "candidate_move_effect", ("terminal",)): ("promotion_any", (("mover_kind", "PieceKind", "pawn"), ("move_kind", "MoveKind", "promotion"), ("promotion_kind", "PromotionKind", "any"))),
    ("position_history_draw.same_board_different_history", "pattern", 0, "replay_relation", ("history_a", "history_b")): ("same_final_position", (("final_position_equal", "bool", "true"),)),
    ("position_history_draw.same_board_different_history", "pattern", 1, "replay_relation", ("history_a", "history_b")): ("different_replay_history", (("history_equal", "bool", "false"),)),
    ("position_history_draw.repetition_key", "pattern", 0, "replay_relation", ("nominal_absent", "nominal_ineffective", "nominal_effective")): ("ineffective_ep_keys_equal_effective_ep_differs", (("ineffective_ep_key_equal", "bool", "true"), ("effective_ep_key_equal", "bool", "false"))),
    ("position_history_draw.halfmove_pawn_reset", "pattern", 0, "replay_relation", ("before", "after")): ("one_legal_ply_extension", (("ply_delta", "i8", "1"),)),
    ("position_history_draw.halfmove_pawn_reset", "after", 0, "candidate_move_effect", ("history",)): ("pawn_move", (("mover_kind", "PieceKind", "pawn"), ("move_kind", "MoveKind", "any"), ("promotion_kind", "PromotionKind", "any"))),
    ("position_history_draw.halfmove_capture_reset", "pattern", 0, "replay_relation", ("before", "after")): ("one_legal_ply_extension", (("ply_delta", "i8", "1"),)),
    ("position_history_draw.halfmove_capture_reset", "after", 0, "candidate_move_effect", ("history",)): ("capture", (("mover_kind", "PieceKind", "any"), ("move_kind", "MoveKind", "capture"), ("promotion_kind", "PromotionKind", "any"))),
    ("termination_score.common_dead_scope", "recognized", 0, "material_class", ("terminal",)): ("recognized_common_dead", (("selected_common_dead_class", "bool", "true"), ("common_dead", "bool", "true"))),
    ("termination_score.common_dead_scope", "two_knights", 0, "material_class", ("terminal",)): ("king_two_knights_vs_king", (("material_signature", "MaterialSignature", "king_two_knights_vs_king"), ("common_dead", "bool", "false"))),
    ("passed_pawn.opposing_pawn_same_or_adjacent_ahead", "blocked", 0, "opposing_pawn_ahead", ("passed",)): ("strictly_ahead_same_or_adjacent_file", (("opposing_pawn_exists", "bool", "true"), ("relative_rank_relation", "RankRelation", "strictly_ahead"), ("absolute_file_delta_max", "u8", "1"))),
    ("queen_or_rook_mating_geometry.queen_geometry", "queen", 0, "finite_mating_root_major_piece", ("mating",)): ("queen", (("major_piece_kind", "PieceKind", "queen"), ("major_piece_count", "u8", "1"), ("other_nonking_count", "u8", "0"), ("major_piece_side_is_mating_side", "bool", "true"))),
    ("queen_or_rook_mating_geometry.rook_geometry", "rook", 0, "finite_mating_root_major_piece", ("mating",)): ("rook", (("major_piece_kind", "PieceKind", "rook"), ("major_piece_count", "u8", "1"), ("other_nonking_count", "u8", "0"), ("major_piece_side_is_mating_side", "bool", "true"))),
}

CANONICAL_CALL_CONSTANTS = {
    ("setup_turn.initial_side_to_move", "initial", "turn"): ((1, "Side", "side", ("first",)),),
    ("setup_turn.alternating_turn", "before", "turn"): ((1, "Side", "side", ("first",)),),
    ("setup_turn.alternating_turn", "after", "turn"): ((1, "Side", "side", ("second",)),),
    ("ordinary_move_capture.king_identity_and_move", "legal", "piece"): ((2, "OccupancyMatch", "exact_piece", ("moving_side", "king")),),
    ("ordinary_move_capture.queen_identity_and_move", "legal", "piece"): ((2, "OccupancyMatch", "exact_piece", ("moving_side", "queen")),),
    ("ordinary_move_capture.rook_identity_and_move", "legal", "piece"): ((2, "OccupancyMatch", "exact_piece", ("moving_side", "rook")),),
    ("ordinary_move_capture.bishop_identity_and_move", "legal", "piece"): ((2, "OccupancyMatch", "exact_piece", ("moving_side", "bishop")),),
    ("ordinary_move_capture.knight_identity_and_move", "legal", "piece"): ((2, "OccupancyMatch", "exact_piece", ("moving_side", "knight")),),
    ("ordinary_move_capture.pawn_identity", "legal", "piece"): ((2, "OccupancyMatch", "exact_piece", ("moving_side", "pawn")),),
    ("ordinary_move_capture.knight_jump", "jump", "piece"): ((2, "OccupancyMatch", "exact_piece", ("moving_side", "knight")),),
    ("control_vs_legal.pawn_control", "pawn", "controller_piece"): ((2, "OccupancyMatch", "exact_piece", ("bound_controller_side", "pawn")),),
    ("control_vs_legal.king_adjacency", "adjacent", "controller_piece"): ((2, "OccupancyMatch", "exact_piece", ("bound_controller_side", "king")),),
    ("termination_score.score_vs_cause", "nonterminal_decisive_score", "source"): ((1, "Score", "score", ("first_win",)),),
    ("record_replay.score_atom", "first_win", "source"): ((1, "Score", "score", ("first_win",)),),
    ("record_replay.score_atom", "second_win", "source"): ((1, "Score", "score", ("second_win",)),),
    ("record_replay.score_atom", "draw", "source"): ((1, "Score", "score", ("draw",)),),
    ("discovered_attack_check.discovered_attack", "attack", "target"): ((2, "OccupancyMatch", "occupied", ()),),
    ("discovered_attack_check.discovered_check", "check", "target"): ((2, "OccupancyMatch", "exact_piece", ("opposing_side", "king")),),
}

# Complete result contract tuple: owner IDs, result variant, payload policy,
# constraint, reject code, and span class.
CANONICAL_RESULT_CONTRACTS = {
    "bool_true": (("chess.setup_turn", "chess.occupancy", "chess.defended", "chess.king_check", "chess.absolute_pin", "chess.fork_double_attack", "chess.discovered_attack_check", "chess.escape_square_control", "chess.passed_pawn", "chess.open_file", "chess.semi_open_file"), "bool_true", "complete_exact_typed_value", "exact", "", "none"),
    "bool_false": (("chess.setup_turn", "chess.occupancy", "chess.defended", "chess.king_check", "chess.absolute_pin", "chess.fork_double_attack", "chess.discovered_attack_check", "chess.escape_square_control", "chess.passed_pawn", "chess.open_file", "chess.semi_open_file"), "bool_false", "complete_exact_typed_value", "exact", "", "none"),
    "square_list_nonempty": (("chess.control",), "square_list", "complete_exact_typed_value", "nonempty", "", "none"),
    "square_list_contains_bound_origin": (("chess.control",), "square_list", "complete_exact_typed_value", "contains_bound_origin", "", "none"),
    "square_list_min_two": (("chess.control",), "square_list", "complete_exact_typed_value", "cardinality_at_least_two", "", "none"),
    "move_legal": (("chess.move_legality",), "move_legal", "complete_exact_typed_value", "exact", "", "none"),
    "move_illegal_blocked": (("chess.move_legality",), "move_illegal", "complete_exact_typed_value", "exact", "CHESS_MOVE_BLOCKED", "none"),
    "move_illegal_friendly_destination": (("chess.move_legality",), "move_illegal", "complete_exact_typed_value", "exact", "CHESS_MOVE_FRIENDLY_DESTINATION", "none"),
    "move_illegal_self_check": (("chess.move_legality",), "move_illegal", "complete_exact_typed_value", "exact", "CHESS_MOVE_SELF_CHECK", "none"),
    "move_illegal_castling_right": (("chess.move_legality",), "move_illegal", "complete_exact_typed_value", "exact", "CHESS_MOVE_CASTLING_RIGHT", "none"),
    "move_illegal_castling_path": (("chess.move_legality",), "move_illegal", "complete_exact_typed_value", "exact", "CHESS_MOVE_CASTLING_PATH", "none"),
    "move_illegal_castling_from_check": (("chess.move_legality",), "move_illegal", "complete_exact_typed_value", "exact", "CHESS_MOVE_CASTLING_FROM_CHECK", "none"),
    "move_illegal_castling_through_check": (("chess.move_legality",), "move_illegal", "complete_exact_typed_value", "exact", "CHESS_MOVE_CASTLING_THROUGH_CHECK", "none"),
    "move_illegal_castling_into_check": (("chess.move_legality",), "move_illegal", "complete_exact_typed_value", "exact", "CHESS_MOVE_CASTLING_INTO_CHECK", "none"),
    "move_illegal_en_passant_target": (("chess.move_legality",), "move_illegal", "complete_exact_typed_value", "exact", "CHESS_MOVE_EN_PASSANT_TARGET", "none"),
    "move_illegal_promotion_missing": (("chess.move_legality",), "move_illegal", "complete_exact_typed_value", "exact", "CHESS_MOVE_PROMOTION_MISSING", "none"),
    "move_illegal_promotion_unneeded": (("chess.move_legality",), "move_illegal", "complete_exact_typed_value", "exact", "CHESS_MOVE_PROMOTION_UNNEEDED", "none"),
    "terminal_none": (("chess.terminal_transition",), "terminal_none", "complete_exact_typed_value", "exact", "", "none"),
    "terminal_checkmate": (("chess.terminal_transition",), "terminal_checkmate", "complete_exact_typed_value", "exact", "", "none"),
    "terminal_stalemate": (("chess.terminal_transition",), "terminal_stalemate", "complete_exact_typed_value", "exact", "", "none"),
    "terminal_common_dead": (("chess.terminal_transition",), "terminal_common_dead", "complete_exact_typed_value", "exact", "", "none"),
    "history_exact": (("chess.history_claim",), "history_claim_fields", "complete_exact_typed_value", "exact", "", "none"),
    "history_nominal_absent": (("chess.history_claim",), "history_claim_fields", "complete_exact_typed_value", "nominal_ep_absent", "", "none"),
    "history_nominal_ineffective": (("chess.history_claim",), "history_claim_fields", "complete_exact_typed_value", "nominal_ep_present_effective_absent", "", "none"),
    "history_nominal_effective": (("chess.history_claim",), "history_claim_fields", "complete_exact_typed_value", "nominal_ep_present_equals_effective", "", "none"),
    "history_occurrence_two": (("chess.history_claim",), "history_claim_fields", "complete_exact_typed_value", "current_key_occurrences_2", "", "none"),
    "history_occurrence_three": (("chess.history_claim",), "history_claim_fields", "complete_exact_typed_value", "current_key_occurrences_3", "", "none"),
    "history_halfmove_99": (("chess.history_claim",), "history_claim_fields", "complete_exact_typed_value", "halfmove_99_claim_false", "", "none"),
    "history_halfmove_100": (("chess.history_claim",), "history_claim_fields", "complete_exact_typed_value", "halfmove_100_claim_true", "", "none"),
    "history_halfmove_nonzero": (("chess.history_claim",), "history_claim_fields", "complete_exact_typed_value", "halfmove_nonzero", "", "none"),
    "history_halfmove_zero": (("chess.history_claim",), "history_claim_fields", "complete_exact_typed_value", "halfmove_zero", "", "none"),
    "history_claim_available": (("chess.history_claim",), "history_claim_fields", "complete_exact_typed_value", "claim_available", "", "none"),
    "declaration_resigned": (("chess.declaration_event",), "declaration_accepted_game_status_resigned", "complete_exact_typed_value", "exact", "", "none"),
    "declaration_agreed": (("chess.declaration_event",), "declaration_accepted_game_status_agreed", "complete_exact_typed_value", "exact", "", "none"),
    "declaration_threefold": (("chess.declaration_event",), "declaration_accepted_game_status_claimed_threefold", "complete_exact_typed_value", "exact", "", "none"),
    "declaration_fifty": (("chess.declaration_event",), "declaration_accepted_game_status_claimed_50_move", "complete_exact_typed_value", "exact", "", "none"),
    "declaration_rejected_agreement_early": (("chess.declaration_event",), "declaration_rejected", "complete_exact_typed_value", "exact", "CHESS_EVENT_AGREEMENT_TOO_EARLY", "none"),
    "declaration_rejected_threefold": (("chess.declaration_event",), "declaration_rejected", "complete_exact_typed_value", "exact", "CHESS_EVENT_THREEFOLD_UNAVAILABLE", "none"),
    "declaration_rejected_fifty": (("chess.declaration_event",), "declaration_rejected", "complete_exact_typed_value", "exact", "CHESS_EVENT_50_MOVE_UNAVAILABLE", "none"),
    "declaration_rejected_game_closed": (("chess.declaration_event",), "declaration_rejected", "complete_exact_typed_value", "exact", "CHESS_GAME_CLOSED", "none"),
    "source_terminal_none": (("chess.source_score_relation",), "source_accepted_terminal_none", "complete_exact_typed_value", "exact", "", "none"),
    "move_decoded_exact": (("chess.move_record_replay",), "move_decoded", "complete_exact_typed_value", "exact", "", "none"),
    "record_replayed_exact": (("chess.move_record_replay",), "record_replayed", "complete_exact_typed_value", "exact", "", "none"),
    "content_accepted_exact": (("content.stream_validation",), "content_accepted", "complete_exact_typed_value", "exact", "", "none"),
    "content_bad_kind_exact_field": (("content.stream_validation",), "content_rejected", "complete_exact_typed_value", "exact", "CONTENT_BAD_RECORD_KIND", "exact_field"),
    "content_truncated_eof": (("content.stream_validation",), "content_rejected", "complete_exact_typed_value", "exact", "CONTENT_TRUNCATED", "eof"),
    "finite_race_exact": (("chess.finite_promotion_race",), "finite_race_result", "complete_exact_typed_value", "exact", "", "none"),
    "finite_mating_exact": (("chess.finite_mating_geometry",), "finite_mating_result", "complete_exact_typed_value", "exact", "", "none"),
}

CANONICAL_CALL_RESULTS = {
    ("setup_turn.board_8x8", "initial", "setup"): "bool_true",
    ("setup_turn.initial_piece_placement", "initial", "setup"): "bool_true",
    ("setup_turn.initial_side_to_move", "initial", "turn"): "bool_true",
    ("setup_turn.alternating_turn", "before", "turn"): "bool_true",
    ("setup_turn.alternating_turn", "after", "turn"): "bool_true",
    ("ordinary_move_capture.king_identity_and_move", "legal", "piece"): "bool_true",
    ("ordinary_move_capture.king_identity_and_move", "legal", "legality"): "move_legal",
    ("ordinary_move_capture.queen_identity_and_move", "legal", "piece"): "bool_true",
    ("ordinary_move_capture.queen_identity_and_move", "legal", "legality"): "move_legal",
    ("ordinary_move_capture.rook_identity_and_move", "legal", "piece"): "bool_true",
    ("ordinary_move_capture.rook_identity_and_move", "legal", "legality"): "move_legal",
    ("ordinary_move_capture.bishop_identity_and_move", "legal", "piece"): "bool_true",
    ("ordinary_move_capture.bishop_identity_and_move", "legal", "legality"): "move_legal",
    ("ordinary_move_capture.knight_identity_and_move", "legal", "piece"): "bool_true",
    ("ordinary_move_capture.knight_identity_and_move", "legal", "legality"): "move_legal",
    ("ordinary_move_capture.pawn_identity", "legal", "piece"): "bool_true",
    ("ordinary_move_capture.pawn_identity", "legal", "legality"): "move_legal",
    ("ordinary_move_capture.slider_blocking", "blocked", "legality"): "move_illegal_blocked",
    ("ordinary_move_capture.knight_jump", "jump", "piece"): "bool_true",
    ("ordinary_move_capture.knight_jump", "jump", "legality"): "move_legal",
    ("ordinary_move_capture.pawn_forward_vs_capture", "quiet", "legality"): "move_legal",
    ("ordinary_move_capture.pawn_forward_vs_capture", "capture", "legality"): "move_legal",
    ("ordinary_move_capture.pawn_initial_double", "double", "legality"): "move_legal",
    ("ordinary_move_capture.friendly_occupancy_rejection", "friendly", "legality"): "move_illegal_friendly_destination",
    ("control_vs_legal.pawn_control", "pawn", "controllers"): "square_list_contains_bound_origin",
    ("control_vs_legal.pawn_control", "pawn", "controller_piece"): "bool_true",
    ("control_vs_legal.defended_friendly_target", "defended", "defended"): "bool_true",
    ("control_vs_legal.pinned_piece_controls", "pinned", "pin"): "bool_true",
    ("control_vs_legal.pinned_piece_controls", "pinned", "controllers"): "square_list_contains_bound_origin",
    ("control_vs_legal.king_adjacency", "adjacent", "controllers"): "square_list_contains_bound_origin",
    ("control_vs_legal.king_adjacency", "adjacent", "controller_piece"): "bool_true",
    ("control_vs_legal.control_vs_move", "controlled_but_illegal", "controllers"): "square_list_contains_bound_origin",
    ("control_vs_legal.control_vs_move", "controlled_but_illegal", "legality"): "move_illegal_en_passant_target",
    ("king_safety.check", "checked", "check"): "bool_true",
    ("king_safety.check_evasion", "evasion", "before"): "bool_true",
    ("king_safety.check_evasion", "evasion", "legality"): "move_legal",
    ("king_safety.check_evasion", "evasion", "after"): "bool_false",
    ("king_safety.self_check", "self_check", "legality"): "move_illegal_self_check",
    ("king_safety.king_capture_safety", "safe_capture", "legality"): "move_legal",
    ("king_safety.king_capture_safety", "unsafe_capture", "legality"): "move_illegal_self_check",
    ("king_safety.double_check", "double", "check"): "bool_true",
    ("king_safety.double_check", "double", "controllers"): "square_list_min_two",
    ("mate_stalemate.checkmate_vs_check", "check_only", "terminal"): "terminal_none",
    ("mate_stalemate.checkmate_vs_check", "check_only", "check"): "bool_true",
    ("mate_stalemate.checkmate_vs_check", "checkmate", "terminal"): "terminal_checkmate",
    ("mate_stalemate.checkmate_vs_check", "checkmate", "check"): "bool_true",
    ("mate_stalemate.stalemate", "stalemate", "terminal"): "terminal_stalemate",
    ("mate_stalemate.legal_reply_exhaustiveness", "reply_exists", "terminal"): "terminal_none",
    ("mate_stalemate.legal_reply_exhaustiveness", "reply_exists", "check"): "bool_true",
    ("mate_stalemate.legal_reply_exhaustiveness", "no_reply", "terminal"): "terminal_checkmate",
    ("mate_stalemate.legal_reply_exhaustiveness", "no_reply", "check"): "bool_true",
    ("castling.rights", "right_present", "legality"): "move_legal",
    ("castling.rights", "right_absent", "legality"): "move_illegal_castling_right",
    ("castling.entitled_king_and_rook", "entitled", "legality"): "move_legal",
    ("castling.entitled_king_and_rook", "replacement", "legality"): "move_illegal_castling_right",
    ("castling.path_clear", "blocked_path", "legality"): "move_illegal_castling_path",
    ("castling.from_check", "from_check", "legality"): "move_illegal_castling_from_check",
    ("castling.through_check", "through_check", "legality"): "move_illegal_castling_through_check",
    ("castling.into_check", "into_check", "legality"): "move_illegal_castling_into_check",
    ("castling.lost_rights", "lost_right", "legality"): "move_illegal_castling_right",
    ("castling.rook_relocation", "castle", "legality"): "move_legal",
    ("castling.rook_relocation", "castle", "record"): "record_replayed_exact",
    ("en_passant.immediate_window", "immediate", "legality"): "move_legal",
    ("en_passant.expiry", "expired", "legality"): "move_illegal_en_passant_target",
    ("en_passant.captured_pawn_removal", "capture", "legality"): "move_legal",
    ("en_passant.captured_pawn_removal", "capture", "record"): "record_replayed_exact",
    ("en_passant.self_check", "self_check", "legality"): "move_illegal_self_check",
    ("en_passant.nominal_vs_effective", "ineffective", "history"): "history_nominal_ineffective",
    ("en_passant.nominal_vs_effective", "effective", "history"): "history_nominal_effective",
    ("promotion.quiet_promotion", "quiet", "legality"): "move_legal",
    ("promotion.capture_promotion", "capture", "legality"): "move_legal",
    ("promotion.promote_queen", "queen", "legality"): "move_legal",
    ("promotion.promote_rook", "rook", "legality"): "move_legal",
    ("promotion.promote_bishop", "bishop", "legality"): "move_legal",
    ("promotion.promote_knight", "knight", "legality"): "move_legal",
    ("promotion.check_after_promotion", "check", "legality"): "move_legal",
    ("promotion.check_after_promotion", "check", "record"): "record_replayed_exact",
    ("promotion.check_after_promotion", "check", "check"): "bool_true",
    ("promotion.mate_after_promotion", "mate", "terminal"): "terminal_checkmate",
    ("promotion.invalid_context", "missing", "legality"): "move_illegal_promotion_missing",
    ("promotion.invalid_context", "unneeded", "legality"): "move_illegal_promotion_unneeded",
    ("position_history_draw.same_board_different_history", "history_a", "history"): "history_exact",
    ("position_history_draw.same_board_different_history", "history_b", "history"): "history_exact",
    ("position_history_draw.repetition_key", "nominal_absent", "history"): "history_nominal_absent",
    ("position_history_draw.repetition_key", "nominal_ineffective", "history"): "history_nominal_ineffective",
    ("position_history_draw.repetition_key", "nominal_effective", "history"): "history_nominal_effective",
    ("position_history_draw.repetition_occurrence", "two", "history"): "history_occurrence_two",
    ("position_history_draw.repetition_occurrence", "three", "history"): "history_occurrence_three",
    ("position_history_draw.halfmove_99_100", "ninety_nine", "history"): "history_halfmove_99",
    ("position_history_draw.halfmove_99_100", "one_hundred", "history"): "history_halfmove_100",
    ("position_history_draw.halfmove_pawn_reset", "before", "history"): "history_halfmove_nonzero",
    ("position_history_draw.halfmove_pawn_reset", "after", "history"): "history_halfmove_zero",
    ("position_history_draw.halfmove_capture_reset", "before", "history"): "history_halfmove_nonzero",
    ("position_history_draw.halfmove_capture_reset", "after", "history"): "history_halfmove_zero",
    ("position_history_draw.claims_not_automatic", "available_but_nonterminal", "history"): "history_claim_available",
    ("position_history_draw.claims_not_automatic", "available_but_nonterminal", "source"): "source_terminal_none",
    ("termination_score.checkmate", "checkmate", "terminal"): "terminal_checkmate",
    ("termination_score.stalemate", "stalemate", "terminal"): "terminal_stalemate",
    ("termination_score.common_dead_scope", "recognized", "terminal"): "terminal_common_dead",
    ("termination_score.common_dead_scope", "two_knights", "terminal"): "terminal_none",
    ("termination_score.resignation", "resign", "event"): "declaration_resigned",
    ("termination_score.agreement", "too_early", "event"): "declaration_rejected_agreement_early",
    ("termination_score.agreement", "accepted", "event"): "declaration_agreed",
    ("termination_score.threefold_claim", "unavailable", "event"): "declaration_rejected_threefold",
    ("termination_score.threefold_claim", "accepted", "event"): "declaration_threefold",
    ("termination_score.fifty_move_claim", "unavailable", "event"): "declaration_rejected_fifty",
    ("termination_score.fifty_move_claim", "accepted", "event"): "declaration_fifty",
    ("termination_score.post_terminal_rejection", "closed", "event"): "declaration_rejected_game_closed",
    ("termination_score.score_vs_cause", "nonterminal_decisive_score", "source"): "source_terminal_none",
    ("record_replay.canonical_move_decode", "canonical", "decode"): "move_decoded_exact",
    ("record_replay.short_replay", "short", "record"): "record_replayed_exact",
    ("record_replay.score_atom", "first_win", "source"): "source_terminal_none",
    ("record_replay.score_atom", "second_win", "source"): "source_terminal_none",
    ("record_replay.score_atom", "draw", "source"): "source_terminal_none",
    ("record_replay.logical_record_valid", "valid", "content"): "content_accepted_exact",
    ("record_replay.logical_record_malformed", "malformed", "content"): "content_bad_kind_exact_field",
    ("record_replay.logical_record_truncated", "truncated", "content"): "content_truncated_eof",
    ("attacked_defended.attacked", "attacked", "controllers"): "square_list_nonempty",
    ("attacked_defended.defended", "defended", "defended"): "bool_true",
    ("absolute_pin.absolute_pin_to_king", "pinned", "pin"): "bool_true",
    ("fork_double_attack.two_named_targets_after_move", "fork", "fork"): "bool_true",
    ("discovered_attack_check.discovered_attack", "attack", "line"): "bool_true",
    ("discovered_attack_check.discovered_attack", "attack", "target"): "bool_true",
    ("discovered_attack_check.discovered_check", "check", "line"): "bool_true",
    ("discovered_attack_check.discovered_check", "check", "target"): "bool_true",
    ("escape_square_control.controlled", "controlled", "control"): "bool_true",
    ("escape_square_control.uncontrolled", "uncontrolled", "control"): "bool_false",
    ("passed_pawn.passed", "passed", "passed"): "bool_true",
    ("passed_pawn.opposing_pawn_same_or_adjacent_ahead", "blocked", "passed"): "bool_false",
    ("open_semi_open_file.open", "open", "open"): "bool_true",
    ("open_semi_open_file.semi_open", "semi_open", "semi_open"): "bool_true",
    ("finite_promotion_race.complete_legal_line_or_tree", "complete", "race"): "finite_race_exact",
    ("queen_or_rook_mating_geometry.queen_geometry", "queen", "mating"): "finite_mating_exact",
    ("queen_or_rook_mating_geometry.rook_geometry", "rook", "mating"): "finite_mating_exact",
    ("queen_or_rook_mating_geometry.all_relevant_replies", "all_replies", "mating"): "finite_mating_exact",
}

CANONICAL_POLICY = {
    "formula": {
        "ceil75": {
            "input_min": 0,
            "input_max": 11,
            "numerator": 3,
            "denominator": 4,
            "rounding": "ceil",
            "boundary_inputs": list(range(12)),
            "boundary_outputs": [0, 1, 2, 3, 3, 4, 5, 6, 6, 7, 8, 9],
        },
        "family_acquisition": {
            "input_min": 0,
            "baseline_failure_min": 3,
            "baseline_failure_max": 6,
            "allowed_misses": 1,
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
    },
    "assessment_minimums": {
        "claimed_family_set_ids": ["E", "C"],
        "pretest_items_per_claimed_family": 2,
        "posttest_items_per_family": 2,
        "posttest_counterfactual_pairs_per_family": 1,
        "delayed_items_per_essential_family": 1,
        "delayed_extra_only_for_otherwise_uncovered_stratum": True,
        "assessment_only_posttest_templates_per_family": 1,
        "counterfactual_pair_may_satisfy_posttest_minimum": True,
        "forced_third_posttest_item": False,
        "integrated_task_ids": [
            "integrated_legal_sequence_pre", "integrated_legal_sequence_post",
            "integrated_record_reading_post",
        ],
    },
    "gate": {
        "protocol": {
            "required_family_set_ids": ["E", "C"],
            "required_family_below_domain_result": "protocol_unclaimable",
            "cohort_count_above_six_result": "invalid_protocol",
            "prior_mastery_counts_for_acquisition": False,
            "prior_mastery_counts_for_attainment": True,
        },
        "essential_family": {
            "family_set_id": "E",
            "posttest_passes_min": 5,
            "acquisition_threshold_id": "family_acquisition",
            "quantifier": "every_family",
        },
        "essential_individual": {
            "learners_min": 4,
            "failed_family_set_id": "E",
            "acquired_fraction_threshold_id": "ceil75",
            "required_acquired_family_ids": ["king_safety"],
            "required_acquired_set_id": "S",
            "required_acquired_set_min": 2,
            "required_integrated_task_ids": [
                "integrated_legal_sequence_post", "integrated_record_reading_post",
            ],
        },
        "core3_family": {
            "family_set_id": "C",
            "posttest_passes_min": 4,
            "acquisition_threshold_id": "family_acquisition",
            "quantifier": "every_family",
            "baseline_coverage_unconditional": True,
        },
        "core3_combined_individual": {
            "optional_claim": True,
            "learners_min": 4,
            "failed_family_set_id": "C",
            "baseline_failed_min": 1,
            "acquired_fraction_threshold_id": "ceil75",
        },
        "delayed": {
            "family_set_id": "E",
            "family_passes_min": 4,
            "quantifier": "every_family",
            "learners_min": 4,
            "individual_pass_fraction_threshold_id": "ceil75",
            "required_passed_family_ids": ["king_safety"],
            "required_passed_set_id": "S",
            "required_passed_set_min": 2,
        },
        "unhinted": {
            "semantic_hint_allowed": False,
            "answer_revealing_behavior_allowed": False,
        },
    },
    "forms": {
        "forms_min": 1,
        "forms_max": 3,
        "same_form_may_serve_multiple_learners": True,
        "display_order_policy_owner": "later_private_assessment_manifest",
        "display_order_seed_required_later": True,
        "display_order_record_required_later": True,
        "display_order_or_seed_required_in_curriculum_v0": False,
        "display_order_or_seed_public_before_authorized_reveal": False,
        "equal_family_burden_fields": [
            "family_id", "split", "sorted_unique_stratum_ids",
            "response_shape", "max_selections",
        ],
        "pre_post_match_fields": [
            "family_id", "sorted_unique_stratum_ids", "response_shape",
            "max_selections",
        ],
        "integrated_tasks_excluded_from_family_burden": True,
        "integrated_equal_fields": [
            "integrated_task_id", "response_shape", "max_selections",
        ],
        "assessment_only_required_family_set_ids": ["E", "C"],
        "assessment_only_split": "posttest",
        "assessment_only_absent_from_splits": ["teaching", "practice"],
        "structural_template_blueprint_reuse_allowed": True,
        "structural_template_id_is_not_case_identity": True,
        "semantic_case_reuse_allowed": False,
    },
    "cue_audit": {
        "split": "posttest",
        "counterfactual_pairs_per_family_min": 1,
        "pair_adjacent_allowed": False,
        "pair_id_learner_visible": False,
        "pair_requires_relation_flip": True,
        "pair_requires_equal_observable_fingerprint": True,
        "strategy_errors_per_family_min": 1,
        "strategy_max_correct_numerator": 1,
        "strategy_max_correct_denominator": 2,
        "tie_break": "lowest_visible_ordinal",
        "missing_metric_fallback": "empty_commit",
        "no_selectable_region_fallback": "empty_commit",
        "cap_zero_fallback": "empty_commit",
        "whole_form_item_counting": "scheduled_item_once",
        "success_rule": "membership_in_complete_accepted_response_set",
        "response_timing_source": "declared_schedule_or_work_units",
        "wall_clock_timing_allowed": False,
        "observable_feature_ids": [
            "visible_ordinal", "visible_option_octets", "region_area",
            "region_count", "highlight_count", "selectable_count",
            "record_payload_octets", "node_branch_count",
            "visible_schema_type_labels", "focus_order", "tab_order",
            "accessibility_attributes", "hover_cursor_clickability",
            "disabled_state", "acknowledgement_identity",
            "acknowledgement_schedule", "error_shape", "response_timing",
        ],
        "private_feature_ids": [
            "accepted_option_ordinals", "accepted_response_cardinality",
            "answer_sequence",
        ],
    },
    "cut": {
        "future_validation_policy_only": True,
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
            "authoring_and_assessment_minimums", "mandatory_stratum_coverage",
            "passive_completeness", "never_cut",
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
PATTERN_DIGEST = "e45fe214fa950817e8c51e29803eaf23605533bd3c49d62a76fc726147d68b75"
FINITE_RULE_DIGEST = "dbd3e25aa767d9c8b877d1afbb2d7bebea4c0daad98958c2da5c9ea2d691cab1"
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
                            "input_constants": call["input_constants"],
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
    def canonical_arguments(binding: dict) -> list[str]:
        return [
            f"{argument['type_id']}@{argument['source_kind']}:"
            f"{argument['source_id']}"
            for argument in binding["arguments"]
        ]

    def canonical_derivations(binding: dict) -> list[str]:
        return [
            f"{row['kind_id']}:{row['operation_id']}("
            + ", ".join(
                f"{type_id}@{source_id}"
                for type_id, source_id in zip(
                    row["input_type_ids"], row["input_source_ids"], strict=True
                )
            )
            + f")->{row['output_type_id']}@{row['output_source_id']}"
            for row in binding["derivations"]
        ]

    def canonical_facts(facts: list[dict]) -> tuple[tuple[str, str, str], ...]:
        return tuple(
            (fact["id"], fact["type_id"], fact["value_id"])
            for fact in facts
        )

    def facts_are_in_domain(facts: tuple[tuple[str, str, str], ...]) -> bool:
        return all(
            fact_id in RELATION_FACT_DOMAINS
            and RELATION_FACT_DOMAINS[fact_id][0] == type_id
            and value_id in RELATION_FACT_DOMAINS[fact_id][1]
            for fact_id, type_id, value_id in facts
        )

    def canonical_constants(
        constants: list[dict],
    ) -> tuple[tuple[int, str, str, tuple[str, ...]], ...]:
        return tuple(
            (
                constant["argument_position"], constant["type_id"],
                constant["constructor_id"], tuple(constant["value_ids"]),
            )
            for constant in constants
        )

    def constant_is_valid(constant: dict, argument: dict) -> bool:
        if set(constant) != {
            "argument_position", "type_id", "constructor_id", "value_ids",
        }:
            return False
        if (
            constant["argument_position"] != argument["position"]
            or constant["type_id"] != argument["type_id"]
        ):
            return False
        constructor = constant["constructor_id"]
        values = constant["value_ids"]
        if constant["type_id"] == "Side":
            return constructor == "side" and values in (["first"], ["second"])
        if constant["type_id"] == "Score":
            return constructor == "score" and values in (
                ["first_win"], ["second_win"], ["draw"],
            )
        if constant["type_id"] != "OccupancyMatch":
            return False
        if constructor == "occupied":
            return values == []
        return (
            constructor == "exact_piece"
            and len(values) == 2
            and values[0] in {
                "moving_side", "bound_controller_side", "opposing_side",
            }
            and values[1] in {
                "pawn", "knight", "bishop", "rook", "queen", "king",
            }
        )

    try:
        bindings = by_id(data["input_binding"])
        contracts = by_id(data["result_contract"])
        patterns = by_id(data["case_pattern"])
        relation_rules = data["finite_relation"]
        if set(data) != ROOT_KEYS or REMOVED_DERIVED_KEYS & set(data):
            return False
        if {key: data[key] for key in CANONICAL_POLICY} != CANONICAL_POLICY:
            return False
        if set(patterns) != EXPECTED_PATTERN_IDS or len(patterns) != 88:
            return False
        if set(bindings) != set(INPUT_ARGUMENTS):
            return False
        if set(contracts) != set(CANONICAL_RESULT_CONTRACTS):
            return False
        if set(relation_rules) != set(RELATION_SHAPES):
            return False

        canonical_rules = {kind: {} for kind in RELATION_SHAPES}
        for key, canonical in CANONICAL_RELATIONS.items():
            kind = key[3]
            result_id, facts = canonical
            previous = canonical_rules[kind].setdefault(result_id, facts)
            if previous != facts or not facts_are_in_domain(facts):
                return False

        for kind in RELATION_SHAPES:
            rule_set = relation_rules[kind]
            if set(rule_set) != {"rule"}:
                return False
            rows = by_id([
                {"id": row["result_id"], **row} for row in rule_set["rule"]
            ])
            for result_id, row in rows.items():
                if set(row) != {"id", "result_id", "facts"}:
                    return False
                if row["id"] != row["result_id"]:
                    return False
                fact_ids = [fact["id"] for fact in row["facts"]]
                if len(fact_ids) != len(set(fact_ids)) or not fact_ids:
                    return False
                if any(set(fact) != {"id", "type_id", "value_id"}
                       for fact in row["facts"]):
                    return False
                facts = canonical_facts(row["facts"])
                if (
                    not facts_are_in_domain(facts)
                    or canonical_rules[kind].get(result_id) != facts
                ):
                    return False
            if set(rows) != set(canonical_rules[kind]):
                return False

        for binding_id, binding in bindings.items():
            if set(binding) != {
                "id", "authority_kind", "owner_id", "input_variant_id",
                "arguments", "derivations",
            }:
                return False
            owner_id, arity = VARIANT_OWNER_ARITY[binding["input_variant_id"]]
            if owner_id != binding["owner_id"] or arity != len(binding["arguments"]):
                return False
            if canonical_arguments(binding) != INPUT_ARGUMENTS[binding_id]:
                return False
            if [argument["position"] for argument in binding["arguments"]] != list(
                range(arity)
            ):
                return False
            if any(set(argument) != {
                "position", "type_id", "source_kind", "source_id",
            } for argument in binding["arguments"]):
                return False
            if [argument["type_id"] for argument in binding["arguments"]] != (
                VARIANT_ARGUMENT_TYPES[binding["input_variant_id"]]
            ):
                return False
            if any(argument["source_kind"] not in {
                "authority", "bound", "bound_projection", "derived",
                "call_constant",
            } for argument in binding["arguments"]):
                return False

            derivations = binding["derivations"]
            if [row["position"] for row in derivations] != list(range(len(derivations))):
                return False
            if canonical_derivations(binding) != DERIVATIONS[binding_id]:
                return False
            produced = {}
            for derivation in derivations:
                if set(derivation) != {
                    "position", "kind_id", "operation_id", "input_source_ids",
                    "input_type_ids", "output_source_id", "output_type_id",
                }:
                    return False
                kind_id, input_types, output_type = DERIVATION_SIGNATURES[
                    derivation["operation_id"]
                ]
                if (
                    derivation["kind_id"] != kind_id
                    or derivation["input_type_ids"] != input_types
                    or len(derivation["input_source_ids"]) != len(input_types)
                    or derivation["output_type_id"] != output_type
                    or derivation["output_source_id"] in produced
                ):
                    return False
                for source_id, type_id in zip(
                    derivation["input_source_ids"], input_types, strict=True
                ):
                    if source_id.startswith("derived.") and produced.get(source_id) != type_id:
                        return False
                produced[derivation["output_source_id"]] = output_type
            for argument in binding["arguments"]:
                if argument["source_kind"] == "derived":
                    if produced.get(argument["source_id"]) != argument["type_id"]:
                        return False

        for contract_id, contract in contracts.items():
            if set(contract) != {
                "id", "owner_ids", "result_variant_id", "payload_policy",
                "constraint_id", "reject_code_id", "span_class",
            }:
                return False
            canonical_contract = (
                tuple(contract["owner_ids"]), contract["result_variant_id"],
                contract["payload_policy"], contract["constraint_id"],
                contract["reject_code_id"], contract["span_class"],
            )
            if CANONICAL_RESULT_CONTRACTS[contract_id] != canonical_contract:
                return False

        def relation_is_valid(
            relation: dict, pattern_id: str, scope_id: str, relation_index: int,
            available: dict[str, dict], seen: set[tuple],
        ) -> bool:
            kind = relation["kind"]
            scope, operand_field, operand_counts, allowed_bindings = (
                RELATION_SHAPES[kind]
            )
            actual_scope = "pattern" if scope_id == "pattern" else "case"
            if actual_scope != scope:
                return False
            if set(relation) != {"kind", operand_field, "result_id", "facts"}:
                return False
            operand_ids = relation[operand_field]
            if (
                len(operand_ids) not in operand_counts
                or len(operand_ids) != len(set(operand_ids))
                or not set(operand_ids) <= set(available)
            ):
                return False
            facts = canonical_facts(relation["facts"])
            if not facts_are_in_domain(facts):
                return False
            key = (
                pattern_id, scope_id, relation_index, kind, tuple(operand_ids),
            )
            if CANONICAL_RELATIONS.get(key) != (relation["result_id"], facts):
                return False
            if actual_scope == "case":
                actual_bindings = {
                    available[operand_id]["input_binding_id"]
                    for operand_id in operand_ids
                }
                if not actual_bindings <= allowed_bindings:
                    return False
            seen.add(key)
            return True

        used_bindings = set()
        used_contracts = set()
        seen_relations = set()
        seen_calls = set()
        for pattern in patterns.values():
            if set(pattern) != {"id", "authority_kind", "relation", "case"}:
                return False
            cases = by_id(pattern["case"])
            if any(
                not relation_is_valid(
                    relation, pattern["id"], "pattern", relation_index,
                    cases, seen_relations,
                )
                for relation_index, relation in enumerate(pattern["relation"])
            ):
                return False
            for case in pattern["case"]:
                if set(case) != {"id", "call", "obligation"}:
                    return False
                calls = by_id(case["call"])
                for call in case["call"]:
                    if set(call) != {
                        "id", "owner_id", "input_binding_id",
                        "input_constants", "result_contract_id",
                    }:
                        return False
                    binding = bindings[call["input_binding_id"]]
                    contract = contracts[call["result_contract_id"]]
                    call_key = (pattern["id"], case["id"], call["id"])
                    seen_calls.add(call_key)
                    if CANONICAL_CALL_RESULTS.get(call_key) != (
                        call["result_contract_id"]
                    ):
                        return False
                    used_bindings.add(call["input_binding_id"])
                    used_contracts.add(call["result_contract_id"])
                    if call["owner_id"] != binding["owner_id"]:
                        return False
                    if call["owner_id"] not in contract["owner_ids"]:
                        return False
                    if binding["authority_kind"] != pattern["authority_kind"]:
                        return False
                    constant_positions = [
                        argument["position"] for argument in binding["arguments"]
                        if argument["source_kind"] in {
                            "call_constant",
                        }
                    ]
                    if [row["argument_position"] for row in call["input_constants"]] != (
                        constant_positions
                    ):
                        return False
                    for constant in call["input_constants"]:
                        argument = binding["arguments"][constant["argument_position"]]
                        if not constant_is_valid(constant, argument):
                            return False
                    if canonical_constants(call["input_constants"]) != (
                        CANONICAL_CALL_CONSTANTS.get(call_key, ())
                    ):
                        return False
                if any(
                    not relation_is_valid(
                        obligation, pattern["id"], case["id"], relation_index,
                        calls, seen_relations,
                    )
                    for relation_index, obligation in enumerate(case["obligation"])
                ):
                    return False
        if (
            used_bindings != set(bindings)
            or used_contracts != set(contracts)
            or seen_relations != set(CANONICAL_RELATIONS)
            or seen_calls != set(CANONICAL_CALL_RESULTS)
            or not set(CANONICAL_CALL_CONSTANTS) <= seen_calls
        ):
            return False
        return True
    except (IndexError, KeyError, TypeError, ValueError):
        return False


def admitted(data: dict) -> bool:
    return all((
        semantic_projection_is_valid(data),
        digest(pattern_projection(data)) == PATTERN_DIGEST,
        digest(data["finite_relation"]) == FINITE_RULE_DIGEST,
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
                actual = [
                    f"{argument['type_id']}@{argument['source_kind']}:"
                    f"{argument['source_id']}"
                    for argument in binding["arguments"]
                ]
                self.assertEqual(actual, expected)
                self.assertEqual(
                    [argument["type_id"] for argument in binding["arguments"]],
                    VARIANT_ARGUMENT_TYPES[binding["input_variant_id"]],
                )
                self.assertEqual(len(expected), arity)
        self.assertEqual(
            bindings["initial_replay_and_side"]["arguments"][0]["source_id"],
            "authority.replay_state_exact_0_plies",
        )

    def test_finite_relation_rules_are_executable(self) -> None:
        rules = self.data["finite_relation"]
        self.assertEqual(
            set(rules),
            {
                "candidate_move_effect", "replay_relation",
                "en_passant_context", "material_class",
                "opposing_pawn_ahead", "finite_mating_root_major_piece",
            },
        )
        for pattern in self.data["case_pattern"]:
            for relation in pattern["relation"]:
                self.assertIn("facts", relation)
                self.assertEqual(
                    RELATION_SHAPES[relation["kind"]][1], "case_ids"
                )
            for case in pattern["case"]:
                for obligation in case["obligation"]:
                    self.assertIn("facts", obligation)
                    self.assertEqual(
                        RELATION_SHAPES[obligation["kind"]][1],
                        "call_ids",
                    )
        self.assertTrue(semantic_projection_is_valid(self.data))
        self.assertEqual(digest(rules), FINITE_RULE_DIGEST)

        for relation_kind in rules:
            for field in ("id", "type_id", "value_id"):
                candidate = copy.deepcopy(self.data)
                instance = next(
                    relation
                    for pattern in candidate["case_pattern"]
                    for relation in (
                        pattern["relation"]
                        + [
                            obligation
                            for case in pattern["case"]
                            for obligation in case["obligation"]
                        ]
                    )
                    if relation["kind"] == relation_kind
                )
                instance["facts"][0][field] = "invented"
                with self.subTest(relation=relation_kind, fact_field=field):
                    self.assertFalse(semantic_projection_is_valid(candidate))

    def test_constants_and_derivations_are_typed_and_positional(self) -> None:
        bindings = by_id(self.data["input_binding"])
        for binding_id, binding in bindings.items():
            self.assertIn("arguments", binding)
            self.assertIn("derivations", binding)
            self.assertNotIn("argument_ids", binding)
            self.assertNotIn("derivation_ref_ids", binding)
            self.assertEqual(
                [argument["position"] for argument in binding["arguments"]],
                list(range(len(binding["arguments"]))),
            )
            actual_derivations = [
                f"{row['kind_id']}:{row['operation_id']}("
                + ", ".join(
                    f"{type_id}@{source_id}"
                    for type_id, source_id in zip(
                        row["input_type_ids"], row["input_source_ids"], strict=True
                    )
                )
                + f")->{row['output_type_id']}@{row['output_source_id']}"
                for row in binding["derivations"]
            ]
            self.assertEqual(actual_derivations, DERIVATIONS[binding_id])
        for pattern in self.data["case_pattern"]:
            for case in pattern["case"]:
                for call in case["call"]:
                    self.assertIn("input_constants", call)
                    self.assertNotIn("input_constant_ids", call)
        self.assertTrue(semantic_projection_is_valid(self.data))

    def _candidate_with_synchronized_mover(self, value_id: str) -> dict:
        candidate = copy.deepcopy(self.data)
        rule = next(
            row
            for row in candidate["finite_relation"]["candidate_move_effect"]["rule"]
            if row["result_id"] == "pawn_quiet"
        )
        next(fact for fact in rule["facts"] if fact["id"] == "mover_kind")[
            "value_id"
        ] = value_id
        for pattern in candidate["case_pattern"]:
            for case in pattern["case"]:
                for relation in case["obligation"]:
                    if (
                        relation["kind"] == "candidate_move_effect"
                        and relation["result_id"] == "pawn_quiet"
                    ):
                        next(
                            fact
                            for fact in relation["facts"]
                            if fact["id"] == "mover_kind"
                        )["value_id"] = value_id
        return candidate

    def test_synchronized_out_of_domain_relation_mutation_is_rejected(self) -> None:
        self.assertFalse(semantic_projection_is_valid(
            self._candidate_with_synchronized_mover("invented")
        ))

    def test_synchronized_in_domain_relation_mutation_is_rejected(self) -> None:
        self.assertFalse(semantic_projection_is_valid(
            self._candidate_with_synchronized_mover("king")
        ))

    def test_valid_alternative_initial_side_constant_is_rejected(self) -> None:
        candidate = copy.deepcopy(self.data)
        pattern = by_id(candidate["case_pattern"])["setup_turn.initial_side_to_move"]
        call = by_id(by_id(pattern["case"])["initial"]["call"])["turn"]
        call["input_constants"][0]["value_ids"] = ["second"]
        self.assertFalse(semantic_projection_is_valid(candidate))

    def test_valid_alternative_score_and_occupancy_constants_are_rejected(self) -> None:
        substitutions = (
            (
                "termination_score.score_vs_cause", "nonterminal_decisive_score",
                "source", ["second_win"],
            ),
            (
                "ordinary_move_capture.king_identity_and_move", "legal",
                "piece", ["moving_side", "queen"],
            ),
        )
        for pattern_id, case_id, call_id, value_ids in substitutions:
            candidate = copy.deepcopy(self.data)
            pattern = by_id(candidate["case_pattern"])[pattern_id]
            call = by_id(by_id(pattern["case"])[case_id]["call"])[call_id]
            call["input_constants"][0]["value_ids"] = value_ids
            with self.subTest(call=(pattern_id, case_id, call_id)):
                self.assertFalse(semantic_projection_is_valid(candidate))

    def _call_at(
        self, data: dict, pattern_id: str, case_id: str, call_id: str,
    ) -> dict:
        pattern = by_id(data["case_pattern"])[pattern_id]
        return by_id(by_id(pattern["case"])[case_id]["call"])[call_id]

    def test_policy_weakenings_are_rejected_semantically(self) -> None:
        mutations = (
            (("gate", "unhinted", "semantic_hint_allowed"), True),
            (("forms", "semantic_case_reuse_allowed"), True),
            (("cue_audit", "wall_clock_timing_allowed"), True),
        )
        for path, value in mutations:
            candidate = copy.deepcopy(self.data)
            target = candidate
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path):
                self.assertFalse(semantic_projection_is_valid(candidate))

    def test_policy_tables_reject_extra_keys_semantically(self) -> None:
        table_paths = (
            ("formula", "ceil75"),
            ("formula", "family_acquisition"),
            ("assessment_minimums",),
            *(("gate", gate_id) for gate_id in self.data["gate"]),
            ("forms",),
            ("cue_audit",),
            ("cut",),
        )
        for path in table_paths:
            candidate = copy.deepcopy(self.data)
            target = candidate
            for key in path:
                target = target[key]
            target["unexpected"] = True
            with self.subTest(path=path):
                self.assertFalse(semantic_projection_is_valid(candidate))

    def test_result_swaps_are_rejected_semantically(self) -> None:
        swaps = (
            (
                ("termination_score.checkmate", "checkmate", "terminal"),
                ("termination_score.stalemate", "stalemate", "terminal"),
            ),
            (
                ("escape_square_control.controlled", "controlled", "control"),
                ("escape_square_control.uncontrolled", "uncontrolled", "control"),
            ),
            (
                ("record_replay.logical_record_valid", "valid", "content"),
                ("record_replay.logical_record_malformed", "malformed", "content"),
            ),
        )
        for first, second in swaps:
            candidate = copy.deepcopy(self.data)
            first_call = self._call_at(candidate, *first)
            second_call = self._call_at(candidate, *second)
            first_call["result_contract_id"], second_call["result_contract_id"] = (
                second_call["result_contract_id"],
                first_call["result_contract_id"],
            )
            with self.subTest(calls=(first, second)):
                self.assertFalse(semantic_projection_is_valid(candidate))

    def test_result_contract_constraint_is_rejected_semantically(self) -> None:
        candidate = copy.deepcopy(self.data)
        by_id(candidate["result_contract"])["terminal_checkmate"][
            "constraint_id"
        ] = "invented"
        self.assertFalse(semantic_projection_is_valid(candidate))

    def test_all_88_irreducible_projections_are_frozen(self) -> None:
        self.assertTrue(semantic_projection_is_valid(self.data))
        self.assertEqual(digest(pattern_projection(self.data)), PATTERN_DIGEST)

    def test_result_compatibility_rejections_and_content_boundary(self) -> None:
        contracts = by_id(self.data["result_contract"])
        self.assertEqual(
            {cid: row["reject_code_id"] for cid, row in contracts.items()
             if row["reject_code_id"]},
            {
                contract_id: canonical[4]
                for contract_id, canonical in CANONICAL_RESULT_CONTRACTS.items()
                if canonical[4]
            },
        )
        self.assertEqual(
            {cid: row["span_class"] for cid, row in contracts.items()
             if row["span_class"] != "none"},
            {
                contract_id: canonical[5]
                for contract_id, canonical in CANONICAL_RESULT_CONTRACTS.items()
                if canonical[5] != "none"
            },
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
            by_id(self.data["input_binding"])["raw_content_bytes"]["arguments"],
            [{
                "position": 0,
                "type_id": "ByteSlice",
                "source_kind": "authority",
                "source_id": "authority.content_bytes",
            }],
        )

    def test_fixed_arithmetic_gates_forms_cues_and_cuts(self) -> None:
        self.assertEqual(
            {key: self.data[key] for key in CANONICAL_POLICY},
            CANONICAL_POLICY,
        )
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

        def binding(data: dict, binding_id: str) -> dict:
            return next(
                row for row in data["input_binding"] if row["id"] == binding_id
            )

        def initial_side_call(data: dict) -> dict:
            return pattern(data, "setup_turn.initial_side_to_move")["case"][0]["call"][0]

        def use_wrong_replay_operand_field(data: dict) -> None:
            relation = pattern(data, "setup_turn.alternating_turn")["relation"][0]
            relation["call_ids"] = relation.pop("case_ids")

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
            )["arguments"].reverse(),
            "initial_even_replay": lambda data: binding(
                data, "initial_replay_and_side"
            )["arguments"][0].__setitem__(
                "source_id", "authority.replay_state_even_plies"
            ),
            "finite_relation": lambda data: pattern(
                data, "en_passant.expiry"
            )["case"][0]["obligation"][0]["facts"][0].__setitem__(
                "value_id", "invented"
            ),
            "finite_rule_fact": lambda data: data["finite_relation"]
            ["candidate_move_effect"]["rule"][0]["facts"][0].__setitem__(
                "value_id", "invented"
            ),
            "replay_uses_call_ids": use_wrong_replay_operand_field,
            "constant_position": lambda data: initial_side_call(data)
            ["input_constants"][0].__setitem__("argument_position", 0),
            "constant_type": lambda data: initial_side_call(data)
            ["input_constants"][0].__setitem__("type_id", "Score"),
            "constant_constructor": lambda data: initial_side_call(data)
            ["input_constants"][0].__setitem__("constructor_id", "score"),
            "constant_value": lambda data: initial_side_call(data)
            ["input_constants"][0]["value_ids"].__setitem__(0, "draw"),
            "constant_missing": lambda data: initial_side_call(data)
            ["input_constants"].clear(),
            "constant_extra": lambda data: initial_side_call(data)
            ["input_constants"].append({
                "argument_position": 1,
                "type_id": "Side",
                "constructor_id": "side",
                "value_ids": ["first"],
            }),
            "derivation_order": lambda data: binding(
                data, "source_derived_history"
            )["derivations"].reverse(),
            "derivation_kind": lambda data: binding(
                data, "source_derived_history"
            )["derivations"][0].__setitem__("kind_id", "typed_projection"),
            "derivation_operation": lambda data: binding(
                data, "source_derived_history"
            )["derivations"][0].__setitem__("operation_id", "chess.validate_local"),
            "derivation_input_source": lambda data: binding(
                data, "source_derived_history"
            )["derivations"][0]["input_source_ids"].__setitem__(
                0, "authority.other_bytes"
            ),
            "derivation_input_type": lambda data: binding(
                data, "source_derived_history"
            )["derivations"][0]["input_type_ids"].__setitem__(0, "MoveSlice"),
            "derivation_output_source": lambda data: binding(
                data, "source_derived_history"
            )["derivations"][0].__setitem__(
                "output_source_id", "derived.other_record"
            ),
            "derivation_output_type": lambda data: binding(
                data, "source_derived_history"
            )["derivations"][0].__setitem__("output_type_id", "ReplayState"),
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
