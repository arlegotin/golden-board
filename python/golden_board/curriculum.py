"""Bounded executable checks for the curriculum-v0 blueprint."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, fields, is_dataclass, replace
from functools import wraps
from hashlib import sha256
from math import isfinite
from types import MappingProxyType
import tomllib

from . import chess, content, source_compiler
from . import constants as C


__all__ = (
    "Blueprint",
    "CurriculumError",
    "GateResult",
    "evaluate_cue_strategy",
    "evaluate_gates",
    "lint_synthetic",
    "load_blueprint",
)

_AUTHORITY = object()
_BYTE_CAP = 1_048_576
_OWNER_SHA256 = bytes.fromhex(
    "601b61eb433e8128e39dd8c62baee6ed1f5461f3ac9a2d0182114861f2ddf263"
)
_ROOT_KEYS = frozenset(
    {
        "schema", "roadmap_mirror", "taxonomy", "sets", "coverage",
        "authoring_minimums", "assessment_minimums", "scoring", "formula",
        "gate", "forms", "leakage", "cue_audit", "capacity", "cut",
        "m1_scope", "concept", "role", "generator", "family",
        "integrated_task", "critical_label", "transform",
        "predicate_mapping", "cue_strategy", "finite_relation",
        "input_binding", "result_contract", "case_pattern",
    }
)
_ID_TABLES = {
    "concept": "id",
    "role": "id",
    "generator": "id",
    "family": "id",
    "integrated_task": "id",
    "critical_label": "id",
    "transform": "id",
    "predicate_mapping": "owner_id",
    "cue_strategy": "id",
    "input_binding": "id",
    "result_contract": "id",
    "case_pattern": "id",
}
_ROW_KEYS = {
    "concept": {"id", "tier", "family_concept", "requires"},
    "role": {"id", "score_mode", "may_define_scored_answer", "requires_predicate", "requires_limitation_or_counterexample", "passive_trace_policy"},
    "generator": {"id", "split", "orthogonal", "result_bearing"},
    "family": {"id", "tier", "concept_id"},
    "integrated_task": {"id", "split", "minimum_per_form", "predicate_ids", "evaluator_generated", "anthology_record_allowed"},
    "critical_label": {"id", "family_id", "wrong_response_id", "case_pattern_ids"},
    "transform": {"id", "matrix", "offset", "swap_colors_and_sides"},
    "predicate_mapping": {"owner_id", "authority_kinds", "transform_ids", "input_mapping", "result_mapping"},
    "cue_strategy": {
        "id", "kind", "direction", "metric", "first_scheduled_item", "prior_item",
        "map_every_prior_accepted_response", "set_mapping", "sequence_mapping",
        "adversarial_choice", "resolution_order", "empty_prior_response",
        "mechanically_valid_result", "first_item_result", "fallback", "fallback_causes",
        "first_item_requires_absent_prior", "empty_prior_requires_present_prior",
        "order", "cap_source",
    },
    "input_binding": {"id", "owner_id", "input_variant_id", "authority_kind", "arguments", "derivations"},
    "result_contract": {"id", "owner_ids", "result_variant_id", "reject_code_id", "span_class", "payload_policy", "constraint_id"},
    "case_pattern": {"id", "authority_kind", "case", "relation"},
}
_CUE_IDS = frozenset(
    {
        "first", "last", "shortest", "longest", "largest_region",
        "most_highlighted", "alternating", "same_as_prior", "empty_commit",
        "select_all_visible",
    }
)
_CUE_ROW_KEYS = {
    "one_by_visible_order": {"id", "kind", "direction"},
    "one_by_declared_metric": {"id", "kind", "direction", "metric"},
    "alternate_first_last_by_scheduled_posttest_index": {"id", "kind", "first_scheduled_item"},
    "prior_accepted_response_visible_ordinal_vectors": {
        "id", "kind", "prior_item", "map_every_prior_accepted_response", "set_mapping",
        "sequence_mapping", "adversarial_choice", "resolution_order", "empty_prior_response",
        "mechanically_valid_result", "first_item_result", "fallback", "fallback_causes",
        "first_item_requires_absent_prior", "empty_prior_requires_present_prior",
    },
    "empty_commit": {"id", "kind"},
    "all_selectable_visible_ordinals_up_to_cap": {"id", "kind", "order", "cap_source"},
}
_ITEM_KEYS = frozenset(
    {
        "id", "family_id", "split", "role_id", "primary_generator_id",
        "response_shape", "max_selections", "stratum_ids",
        "structural_template_id", "authority_kind", "authority",
        "shown_move_bytes", "case_pattern_ids", "owner_calls", "prompt_target",
        "accepted_responses", "form_id", "integrated_task_id",
        "counterfactual_pair_id", "visible_index", "observable_fingerprint",
        "relation_result", "result_bearing", "public_fields",
        "concept_ids", "authoring_slot", "practice_node_id",
    }
)
_PROTOCOL_KEYS = frozenset(
    {
        "split", "feedback", "delay_hours", "attempt", "interruption",
        "committed", "resume", "state_unchanged", "outcome", "retry_allowed",
        "feedback_window", "delayed_effect", "help_category", "help_effect",
    }
)
_GATES = {
    "protocol": {
        "required_family_set_ids": ["E", "C"],
        "required_family_below_domain_result": "protocol_unclaimable",
        "cohort_count_above_six_result": "invalid_protocol",
        "prior_mastery_counts_for_acquisition": False,
        "prior_mastery_counts_for_attainment": True,
    },
    "essential_family": {
        "family_set_id": "E", "posttest_passes_min": 5,
        "acquisition_threshold_id": "family_acquisition", "quantifier": "every_family",
    },
    "essential_individual": {
        "learners_min": 4, "failed_family_set_id": "E",
        "acquired_fraction_threshold_id": "ceil75",
        "required_acquired_family_ids": ["king_safety"],
        "required_acquired_set_id": "S", "required_acquired_set_min": 2,
        "required_integrated_task_ids": [
            "integrated_legal_sequence_post", "integrated_record_reading_post",
        ],
    },
    "core3_family": {
        "family_set_id": "C", "posttest_passes_min": 4,
        "acquisition_threshold_id": "family_acquisition", "quantifier": "every_family",
        "baseline_coverage_unconditional": True,
    },
    "core3_combined_individual": {
        "optional_claim": True, "learners_min": 4, "failed_family_set_id": "C",
        "baseline_failed_min": 1, "acquired_fraction_threshold_id": "ceil75",
    },
    "delayed": {
        "family_set_id": "E", "family_passes_min": 4, "quantifier": "every_family",
        "learners_min": 4, "individual_pass_fraction_threshold_id": "ceil75",
        "required_passed_family_ids": ["king_safety"], "required_passed_set_id": "S",
        "required_passed_set_min": 2,
    },
    "unhinted": {
        "semantic_hint_allowed": False, "answer_revealing_behavior_allowed": False,
    },
}
_TRANSFORMS = {
    "identity": ([1, 0, 0, 1], [0, 0], False),
    "file_reflection": ([-1, 0, 0, 1], [7, 0], False),
    "rank_reflection_color_swap": ([1, 0, 0, -1], [0, 7], True),
    "rotation_180_color_swap": ([-1, 0, 0, -1], [7, 7], True),
}
_POSTTEST_STRATA = (
    "king_safety.self_check", "castling.from_check", "castling.through_check",
    "castling.into_check", "en_passant.self_check",
    "termination_score.post_terminal_rejection", "termination_score.score_vs_cause",
)
_OBSERVABLE_FEATURES = (
    "visible_ordinal", "visible_option_octets", "region_area", "region_count",
    "highlight_count", "selectable_count", "record_payload_octets",
    "node_branch_count", "visible_schema_type_labels", "focus_order", "tab_order",
    "accessibility_attributes", "hover_cursor_clickability", "disabled_state",
    "acknowledgement_identity", "acknowledgement_schedule", "error_shape",
    "response_timing",
)
_CUT_ORDER = (
    "optional_alternate_presentations", "repeated_heuristic_examples",
    "nonessential_exact_relation_repetitions", "lowest_priority_heuristics",
    "optional_interaction_branches", "nonessential_navigation", "profile_revision",
)


class CurriculumError(ValueError):
    """A fail-closed curriculum blueprint or synthetic-evidence failure."""


class Blueprint:
    """Opaque, authority-created curriculum-v0 blueprint."""

    __slots__ = ("__data", "__ids")

    def __init__(self, data: dict[str, object], ids: dict[str, frozenset[str]], *, _token=None):
        if _token is not _AUTHORITY:
            raise TypeError("Blueprint is created by load_blueprint")
        object.__setattr__(self, "_Blueprint__data", _freeze(data))
        object.__setattr__(self, "_Blueprint__ids", MappingProxyType(dict(ids)))

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("Blueprint is immutable")

    @property
    def _data(self):
        return self.__data

    @property
    def _ids(self):
        return self.__ids

    def family_set(self, set_id: str) -> frozenset[str]:
        if type(set_id) is not str or set_id not in self._data["sets"]:
            raise CurriculumError("unknown family set")
        return frozenset(self._data["sets"][set_id])


@dataclass(frozen=True, slots=True)
class GateResult:
    protocol_claimable: bool
    essential_family: bool
    essential_individual: bool
    core3_family: bool
    core3_combined: bool
    delayed: bool
    unhinted: bool

    @property
    def passed(self) -> bool:
        return all(
            (
                self.protocol_claimable,
                self.essential_family,
                self.essential_individual,
                self.core3_family,
                self.core3_combined,
                self.delayed,
                self.unhinted,
            )
        )


def _fail(message: str) -> None:
    raise CurriculumError(message)


def _fail_closed(function):
    @wraps(function)
    def checked(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except CurriculumError:
            raise
        except (AttributeError, KeyError, OverflowError, TypeError) as error:
            raise CurriculumError("invalid synthetic value") from error

    return checked


def _freeze(value: object) -> object:
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


def _exact_int(value: object, minimum: int, maximum: int, name: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _fail(f"invalid {name}")
    return value


def _strings(value: object, name: str, *, unique: bool = True) -> tuple[str, ...]:
    if type(value) is not list or any(type(item) is not str or not item for item in value):
        _fail(f"invalid {name}")
    result = tuple(value)
    if unique and len(set(result)) != len(result):
        _fail(f"duplicate {name}")
    return result


def _rows(data: dict[str, object], table: str, id_key: str) -> tuple[dict[str, object], ...]:
    value = data.get(table)
    if type(value) is not list or not value:
        _fail(f"missing {table}")
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for row in value:
        if type(row) is not dict or type(row.get(id_key)) is not str or not row[id_key]:
            _fail(f"invalid {table} row")
        expected_keys = _CUE_ROW_KEYS.get(row.get("kind")) if table == "cue_strategy" else _ROW_KEYS[table]
        if expected_keys is None or set(row) != expected_keys:
            _fail(f"unknown {table} field")
        identifier = row[id_key]
        if identifier in seen:
            _fail(f"duplicate {table} ID")
        seen.add(identifier)
        rows.append(row)
    return tuple(rows)


def _validate_formulas(data: dict[str, object]) -> None:
    formula = data.get("formula")
    if type(formula) is not dict or set(formula) != {"ceil75", "family_acquisition"}:
        _fail("closed formula table")
    ceil = formula["ceil75"]
    if type(ceil) is not dict or set(ceil) != {
        "input_min", "input_max", "numerator", "denominator", "rounding",
        "boundary_inputs", "boundary_outputs",
    }:
        _fail("invalid ceil75")
    lower = _exact_int(ceil.get("input_min"), 0, 11, "ceil75 minimum")
    upper = _exact_int(ceil.get("input_max"), lower, 11, "ceil75 maximum")
    numerator = _exact_int(ceil.get("numerator"), 1, 0xFFFF, "ceil75 numerator")
    denominator = _exact_int(ceil.get("denominator"), 1, 0xFFFF, "ceil75 denominator")
    inputs = _strings_of_exact_ints(ceil.get("boundary_inputs"), lower, upper, "ceil75 inputs")
    outputs = _strings_of_exact_ints(ceil.get("boundary_outputs"), 0, upper, "ceil75 outputs")
    expected_inputs = tuple(range(lower, upper + 1))
    expected_outputs = tuple((numerator * value + denominator - 1) // denominator for value in expected_inputs)
    if ceil.get("rounding") != "ceil" or inputs != expected_inputs or outputs != expected_outputs:
        _fail("ceil75 boundary mismatch")

    acquisition = formula["family_acquisition"]
    if type(acquisition) is not dict or set(acquisition) != {
        "input_min", "baseline_failure_min", "baseline_failure_max", "allowed_misses",
        "negative_input_result", "below_domain_result", "inside_domain_operation",
        "above_domain_result", "boundary_inputs", "boundary_results",
    }:
        _fail("invalid acquisition formula")
    if (
        acquisition["input_min"] != 0
        or acquisition["negative_input_result"] != "invalid_protocol"
        or acquisition["below_domain_result"] != "no_claim"
        or acquisition["above_domain_result"] != "invalid_protocol"
    ):
        _fail("acquisition result domain")
    minimum = _exact_int(acquisition.get("baseline_failure_min"), 0, 6, "acquisition minimum")
    maximum = _exact_int(acquisition.get("baseline_failure_max"), minimum, 6, "acquisition maximum")
    misses = _exact_int(acquisition.get("allowed_misses"), 0, 6, "allowed misses")
    boundary_inputs = _strings_of_exact_ints(acquisition.get("boundary_inputs"), 0, 7, "acquisition inputs")
    boundary_results = acquisition.get("boundary_results")
    expected_results = tuple(
        "no_claim" if value < minimum else str(value - misses) if value <= maximum else "invalid_protocol"
        for value in boundary_inputs
    )
    if (
        boundary_inputs != tuple(range(8))
        or type(boundary_results) is not list
        or tuple(boundary_results) != expected_results
        or acquisition.get("inside_domain_operation") != "checked_b_minus_one"
    ):
        _fail("acquisition boundary mismatch")


def _strings_of_exact_ints(value: object, minimum: int, maximum: int, name: str) -> tuple[int, ...]:
    if type(value) is not list:
        _fail(f"invalid {name}")
    return tuple(_exact_int(item, minimum, maximum, name) for item in value)


def _acyclic(requirements: dict[str, tuple[str, ...]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(identifier: str) -> None:
        if identifier in visiting:
            _fail("cyclic concept dependency")
        if identifier in visited:
            return
        visiting.add(identifier)
        for dependency in requirements[identifier]:
            visit(dependency)
        visiting.remove(identifier)
        visited.add(identifier)

    for identifier in requirements:
        visit(identifier)


def _validate_references(data: dict[str, object], ids: dict[str, frozenset[str]]) -> None:
    taxonomy = data.get("taxonomy")
    sets = data.get("sets")
    if type(taxonomy) is not dict or type(sets) is not dict or set(sets) != {"E", "S", "C"}:
        _fail("closed taxonomy and family sets")
    tiers = frozenset(_strings(taxonomy.get("tier_ids"), "tier IDs"))
    splits = frozenset(_strings(taxonomy.get("split_ids"), "split IDs"))
    shapes = frozenset(_strings(taxonomy.get("response_shape_ids"), "response shapes"))
    authorities = frozenset(_strings(taxonomy.get("case_authority_kind_ids"), "authority kinds"))
    if not tiers or not splits or shapes != {"single", "set", "sequence"}:
        _fail("incomplete taxonomy")

    concepts = {row["id"]: row for row in data["concept"]}
    requirements: dict[str, tuple[str, ...]] = {}
    for identifier, row in concepts.items():
        if row.get("tier") not in tiers:
            _fail("unknown concept tier")
        requires = tuple(row.get("requires", ()))
        if type(row.get("requires")) is not list or any(item not in concepts for item in requires):
            _fail("unresolved concept dependency")
        requirements[identifier] = requires
    _acyclic(requirements)

    for row in data["family"]:
        if row.get("concept_id") not in ids["concept"] or row.get("tier") not in tiers:
            _fail("unresolved family")
    for set_id, members in sets.items():
        if any(member not in ids["family"] for member in _strings(members, f"set {set_id}")):
            _fail("unknown family in set")
    if len(sets["E"]) != 11 or len(sets["C"]) != 9 or not set(sets["S"]) <= set(sets["E"]):
        _fail("M1 family synopsis mismatch")

    for row in data["generator"]:
        if row.get("split") not in splits or type(row.get("orthogonal")) is not bool or type(row.get("result_bearing")) is not bool:
            _fail("invalid generator")
    role_modes = {
        "exact_rule": ("exact_assertion_unscored", False, True, False, "optional"),
        "observable_relation": ("exact_assertion_unscored", False, True, False, "optional"),
        "worked_example": ("exact_assertion_and_trace_unscored", False, True, False, "required"),
        "heuristic": ("limitation_recognition_only", False, False, True, "optional"),
        "practice": ("complete_accepted_response_membership", True, True, False, "packed_required_external_forbidden"),
        "feedback": ("derived_exact_relation", False, True, False, "not_applicable"),
        "passive_trace": ("deterministic_unscored", False, False, False, "not_applicable"),
    }
    if ids["role"] != frozenset(role_modes):
        _fail("role closure")
    for row in data["role"]:
        if (
            row.get("score_mode"), row.get("may_define_scored_answer"),
            row.get("requires_predicate"), row.get("requires_limitation_or_counterexample"),
            row.get("passive_trace_policy"),
        ) != role_modes[row["id"]]:
            _fail("invalid role semantics")
    if ids["transform"] != frozenset(_TRANSFORMS):
        _fail("transform closure")
    for row in data["transform"]:
        if (row.get("matrix"), row.get("offset"), row.get("swap_colors_and_sides")) != _TRANSFORMS[row["id"]]:
            _fail("invalid transform")
    for row in data["integrated_task"]:
        if row.get("split") not in splits:
            _fail("invalid integrated split")
        if any(owner not in ids["predicate_mapping"] for owner in _strings(row.get("predicate_ids"), "integrated predicates")):
            _fail("unresolved integrated predicate")
    for row in data["critical_label"]:
        if row.get("family_id") not in ids["family"]:
            _fail("unresolved critical family")
        if any(pattern not in ids["case_pattern"] for pattern in _strings(row.get("case_pattern_ids"), "critical patterns")):
            _fail("unresolved critical pattern")
    for row in data["predicate_mapping"]:
        if any(transform not in ids["transform"] for transform in _strings(row.get("transform_ids"), "predicate transforms")):
            _fail("unresolved transform")
        if any(authority not in authorities for authority in _strings(row.get("authority_kinds"), "predicate authorities")):
            _fail("unknown predicate authority")
    if ids["cue_strategy"] != _CUE_IDS:
        _fail("cue strategy closure")

    bindings = {row["id"]: row for row in data["input_binding"]}
    contracts = {row["id"]: row for row in data["result_contract"]}
    for row in bindings.values():
        if row.get("owner_id") not in ids["predicate_mapping"] or row.get("authority_kind") not in authorities:
            _fail("unresolved input binding")
        if type(row.get("arguments")) is not list or any(
            type(argument) is not dict
            or set(argument) != {"position", "type_id", "source_kind", "source_id"}
            for argument in row["arguments"]
        ):
            _fail("closed binding arguments")
        if type(row.get("derivations")) is not list or any(
            type(derivation) is not dict
            or set(derivation) != {
                "position", "kind_id", "operation_id", "input_source_ids",
                "input_type_ids", "output_source_id", "output_type_id",
            }
            for derivation in row["derivations"]
        ):
            _fail("closed binding derivations")
    for row in contracts.values():
        owners = _strings(row.get("owner_ids"), "result owners")
        if any(owner not in ids["predicate_mapping"] for owner in owners):
            _fail("unresolved result owner")
    for pattern in data["case_pattern"]:
        if pattern.get("authority_kind") not in authorities or type(pattern.get("case")) is not list or not pattern["case"]:
            _fail("invalid case pattern")
        case_ids: set[str] = set()
        for case in pattern["case"]:
            if type(case) is not dict or set(case) != {"id", "call", "obligation"} or type(case.get("id")) is not str or case["id"] in case_ids:
                _fail("invalid case ID")
            case_ids.add(case["id"])
            calls = case.get("call")
            if type(calls) is not list or not calls:
                _fail("missing owner call")
            call_ids: set[str] = set()
            for call in calls:
                if type(call) is not dict or set(call) != {
                    "id", "owner_id", "input_binding_id", "input_constants", "result_contract_id"
                } or type(call.get("id")) is not str or call["id"] in call_ids:
                    _fail("invalid call ID")
                call_ids.add(call["id"])
                binding = bindings.get(call.get("input_binding_id"))
                contract = contracts.get(call.get("result_contract_id"))
                if binding is None or contract is None or call.get("owner_id") != binding.get("owner_id") or call.get("owner_id") not in contract.get("owner_ids", ()):
                    _fail("unresolved owner call")
                if type(call["input_constants"]) is not list or any(
                    type(constant) is not dict
                    or set(constant) != {"argument_position", "type_id", "constructor_id", "value_ids"}
                    for constant in call["input_constants"]
                ):
                    _fail("closed call constants")
            for obligation in case.get("obligation", ()):
                if type(obligation) is not dict or set(obligation) != {"kind", "call_ids", "result_id", "facts"} or any(call not in call_ids for call in obligation.get("call_ids", ())):
                    _fail("unresolved call obligation")
                _facts(obligation.get("facts"))
        for relation in pattern.get("relation", ()):
            if type(relation) is not dict or set(relation) != {"kind", "case_ids", "result_id", "facts"} or any(case not in case_ids for case in relation.get("case_ids", ())):
                _fail("unresolved case relation")
            _facts(relation.get("facts"))

    finite = data.get("finite_relation")
    if type(finite) is not dict:
        _fail("invalid finite relations")
    for relation in finite.values():
        if type(relation) is not dict or set(relation) != {"rule"} or type(relation["rule"]) is not list:
            _fail("closed finite relation")
        for rule in relation["rule"]:
            if type(rule) is not dict or set(rule) != {"facts", "result_id"}:
                _fail("closed finite rule")
            _facts(rule["facts"])


def _facts(value: object) -> None:
    if type(value) is not list or any(
        type(fact) is not dict or set(fact) != {"id", "type_id", "value_id"}
        for fact in value
    ):
        _fail("closed finite facts")


def _validate_policy(data: dict[str, object]) -> None:
    roadmap = data.get("roadmap_mirror")
    if type(roadmap) is not dict or roadmap.get("kind") != "checked_mirror" or roadmap.get("owner") != "docs/roadmap.md":
        _fail("roadmap mirror owner")
    cohort = roadmap.get("cohort")
    if type(cohort) is not dict or cohort.get("selected_learners") != 6:
        _fail("fixed cohort synopsis")
    for table in (
        "coverage", "authoring_minimums", "assessment_minimums", "scoring",
        "gate", "forms", "leakage", "cue_audit", "capacity", "cut", "m1_scope",
    ):
        if type(data.get(table)) is not dict:
            _fail(f"missing {table}")
    coverage = data["coverage"]
    if set(coverage) != {
        "instruction_coverage_any_of_splits", "held_out_coverage_any_of_splits",
        "every_core3_stratum_split", "delayed_family_set_id", "multi_stratum_item_allowed",
        "multi_stratum_credit", "assessment_item_exactly_one_family",
        "integrated_task_has_no_family", "posttest_required_strata",
    } or tuple(coverage["posttest_required_strata"]) != _POSTTEST_STRATA:
        _fail("coverage closure")
    authoring = data["authoring_minimums"]
    if set(authoring) != {
        "applies_to", "grounded_rule_or_relation_per_concept",
        "contrasting_worked_boundary_or_counterexample_per_concept",
        "active_packed_prediction_with_immediate_feedback_per_concept",
        "distinct_held_out_practice_per_concept", "passive_trace_per_packed_practice_node",
        "active_and_held_out_practice_must_be_distinct", "grounding_role_any_of",
        "contrasting_role_id", "active_role_id", "feedback_role_id", "passive_role_id",
        "heuristic_role_required_concept_ids", "requires_concept_ids",
    } or any(
        authoring[key] != 1 for key in (
            "grounded_rule_or_relation_per_concept",
            "contrasting_worked_boundary_or_counterexample_per_concept",
            "active_packed_prediction_with_immediate_feedback_per_concept",
            "distinct_held_out_practice_per_concept",
            "passive_trace_per_packed_practice_node",
        )
    ):
        _fail("authoring minimum closure")
    if data["gate"] != _GATES:
        _fail("frozen gate policy")
    assessment = data["assessment_minimums"]
    if set(assessment) != {
        "claimed_family_set_ids", "pretest_items_per_claimed_family",
        "posttest_items_per_family", "posttest_counterfactual_pairs_per_family",
        "delayed_items_per_essential_family",
        "delayed_extra_only_for_otherwise_uncovered_stratum",
        "assessment_only_posttest_templates_per_family",
        "counterfactual_pair_may_satisfy_posttest_minimum", "forced_third_posttest_item",
        "integrated_task_ids",
    } or assessment != {
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
    }:
        _fail("assessment minimum closure")
    scoring = data["scoring"]
    if scoring != {
        "item_rule": "complete_accepted_response_membership_all_or_nothing",
        "family_pass_rule": "all_family_items_correct", "partial_credit": False,
        "preferred_accepted_response": False,
        "critical_applies_only_to_committed_incorrect": True,
        "critical_cross_family_veto": False,
        "postselection_missing_malformed_extra_uncommitted_out_of_window_is_incorrect": True,
    }:
        _fail("scoring closure")
    forms = data["forms"]
    if (
        forms.get("forms_min") != 1
        or forms.get("forms_max") != 3
        or set(forms) != {
            "forms_min", "forms_max", "same_form_may_serve_multiple_learners",
            "display_order_policy_owner", "display_order_seed_required_later",
            "display_order_record_required_later", "display_order_or_seed_required_in_curriculum_v0",
            "display_order_or_seed_public_before_authorized_reveal", "equal_family_burden_fields",
            "pre_post_match_fields", "integrated_tasks_excluded_from_family_burden",
            "integrated_equal_fields", "assessment_only_required_family_set_ids",
            "assessment_only_split", "assessment_only_absent_from_splits",
            "structural_template_blueprint_reuse_allowed",
            "structural_template_id_is_not_case_identity", "semantic_case_reuse_allowed",
        }
    ):
        _fail("invalid form range")
    cue = data["cue_audit"]
    if tuple(cue.get("observable_feature_ids", ())) != _OBSERVABLE_FEATURES:
        _fail("observable cue feature closure")
    numerator = _exact_int(cue.get("strategy_max_correct_numerator"), 0, 0xFFFF, "cue numerator")
    denominator = _exact_int(cue.get("strategy_max_correct_denominator"), 1, 0xFFFF, "cue denominator")
    if numerator * 2 > denominator or cue.get("strategy_errors_per_family_min") != 1:
        _fail("cue threshold")
    cut = data["cut"]
    if tuple(_strings(cut.get("order"), "cut order")) != _CUT_ORDER:
        _fail("cut order closure")
    _strings(cut.get("never_cut"), "never-cut list")
    _strings(cut.get("cut_must_preserve"), "cut preservation")
    scope = data["m1_scope"]
    if set(scope) != {
        "blueprint_and_synthetic_manifests_only", "concrete_assessment_artifacts_required",
        "forbidden_concrete_artifact_kinds", "future_private_assessment_manifest_required_in_m1",
    } or scope.get("blueprint_and_synthetic_manifests_only") is not True or scope.get("concrete_assessment_artifacts_required") is not False:
        _fail("M1 scope")
    capacity = data["capacity"]
    if capacity != {
        "kind": "initial_safety", "records_per_curriculum_family_max": 256,
        "multi_family_teaching_record_counts_against_each_family": True,
        "generic_untagged_grounding_records_excluded": True, "final_capacity_claim": False,
    }:
        _fail("capacity closure")


def load_blueprint(raw_toml: bytes) -> Blueprint:
    """Parse and close one curriculum-v0 owner document."""
    if type(raw_toml) is not bytes or len(raw_toml) > _BYTE_CAP:
        _fail("invalid blueprint bytes")
    if sha256(raw_toml).digest() != _OWNER_SHA256:
        _fail("unknown blueprint receipt")
    try:
        data = tomllib.loads(raw_toml.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise CurriculumError("invalid blueprint TOML") from error
    if set(data) != _ROOT_KEYS or data.get("schema") != "golden-board.curriculum/v0":
        _fail("closed curriculum root")
    ids: dict[str, frozenset[str]] = {}
    for table, id_key in _ID_TABLES.items():
        rows = _rows(data, table, id_key)
        ids[table] = frozenset(row[id_key] for row in rows)
    _validate_formulas(data)
    _validate_references(data, ids)
    _validate_policy(data)
    return Blueprint(data, ids, _token=_AUTHORITY)


def _blueprint(value: object) -> Blueprint:
    if type(value) is not Blueprint:
        _fail("invalid blueprint authority")
    return value


def _learner_maps(
    blueprint: Blueprint,
    learner: object,
    family_ids: frozenset[str],
    essential: frozenset[str],
) -> tuple[dict, dict, dict, dict, bool, bool, bool]:
    if type(learner) is not dict or set(learner) != {
        "baseline", "posttest", "delayed", "integrated", "protocol"
    }:
        _fail("closed learner result")
    baseline, posttest, delayed, integrated = (
        learner["baseline"], learner["posttest"], learner["delayed"], learner["integrated"]
    )
    for value, allowed, name in (
        (baseline, family_ids, "baseline"),
        (posttest, family_ids, "posttest"),
        (delayed, essential, "delayed"),
    ):
        if type(value) is not dict or not set(value) <= allowed or any(state not in {"pass", "fail", "unavailable"} for state in value.values()):
            _fail(f"invalid {name} results")
    if type(integrated) is not dict or not set(integrated) <= {
        "integrated_legal_sequence_pre", "integrated_legal_sequence_post",
        "integrated_record_reading_post",
    } or any(state not in {"pass", "fail", "unavailable"} for state in integrated.values()):
        _fail("invalid integrated results")
    semantic_hint, answer_revealing, delayed_protocol_ok = _lint_protocol(
        blueprint, learner["protocol"]
    )
    return (
        baseline, posttest, delayed, integrated, semantic_hint, answer_revealing,
        delayed_protocol_ok,
    )


def _ceil75(blueprint: Blueprint, value: int) -> int:
    row = blueprint._data["formula"]["ceil75"]
    _exact_int(value, row["input_min"], row["input_max"], "ceil75 input")
    return (row["numerator"] * value + row["denominator"] - 1) // row["denominator"]


def _acquisition(blueprint: Blueprint, failures: int) -> int | None:
    row = blueprint._data["formula"]["family_acquisition"]
    _exact_int(failures, 0, 6, "acquisition input")
    if failures < row["baseline_failure_min"]:
        return None
    return failures - row["allowed_misses"]


@_fail_closed
def evaluate_gates(blueprint: Blueprint, cohort_results: object) -> GateResult:
    """Evaluate the frozen family, individual, delayed, and hint gates."""
    blueprint = _blueprint(blueprint)
    if type(cohort_results) is not dict or set(cohort_results) != {"combined_core3_claim", "learners"}:
        _fail("closed cohort result")
    claim = cohort_results["combined_core3_claim"]
    learners = cohort_results["learners"]
    if type(claim) is not bool or type(learners) not in (list, tuple) or len(learners) != 6:
        _fail("fixed six-person cohort")
    essential = blueprint.family_set("E")
    special = blueprint.family_set("S")
    core3 = blueprint.family_set("C")
    family_ids = essential | core3
    rows = tuple(_learner_maps(blueprint, row, family_ids, essential) for row in learners)

    def count(family: str, phase: int, state: str = "pass") -> int:
        return sum(
            row[phase].get(family) == state and (phase != 2 or row[6])
            for row in rows
        )

    required = essential | core3
    thresholds = {family: _acquisition(blueprint, count(family, 0, "fail")) for family in required}
    protocol = all(threshold is not None for threshold in thresholds.values()) and all(
        row[0].get(family) in {"pass", "fail"} for row in rows for family in required
    )

    essential_family = protocol and all(
        count(family, 1) >= blueprint._data["gate"]["essential_family"]["posttest_passes_min"]
        and sum(row[0].get(family) == "fail" and row[1].get(family) == "pass" for row in rows) >= thresholds[family]
        for family in essential
    )
    acquired: list[frozenset[str]] = []
    core_acquired: list[frozenset[str]] = []
    for baseline, posttest, _delayed, _integrated, _hint, _reveal, _protocol_ok in rows:
        acquired.append(frozenset(family for family in essential if baseline.get(family) == "fail" and posttest.get(family) == "pass"))
        core_acquired.append(frozenset(family for family in core3 if baseline.get(family) == "fail" and posttest.get(family) == "pass"))
    essential_individual_count = sum(
        len(acquired[index]) >= _ceil75(blueprint, sum(rows[index][0].get(family) == "fail" for family in essential))
        and "king_safety" in acquired[index]
        and len(acquired[index] & special) >= blueprint._data["gate"]["essential_individual"]["required_acquired_set_min"]
        and all(rows[index][3].get(task) == "pass" for task in blueprint._data["gate"]["essential_individual"]["required_integrated_task_ids"])
        for index in range(6)
    )
    essential_individual = essential_individual_count >= blueprint._data["gate"]["essential_individual"]["learners_min"]

    core3_family = protocol and all(
        count(family, 1) >= blueprint._data["gate"]["core3_family"]["posttest_passes_min"]
        and sum(row[0].get(family) == "fail" and row[1].get(family) == "pass" for row in rows) >= thresholds[family]
        for family in core3
    )
    core3_combined = not claim or sum(
        (failed := sum(rows[index][0].get(family) == "fail" for family in core3))
        >= blueprint._data["gate"]["core3_combined_individual"]["baseline_failed_min"]
        and len(core_acquired[index]) >= _ceil75(blueprint, failed)
        for index in range(6)
    ) >= blueprint._data["gate"]["core3_combined_individual"]["learners_min"]

    delayed_family = all(
        count(family, 2) >= blueprint._data["gate"]["delayed"]["family_passes_min"]
        for family in essential
    )
    delayed_individual = sum(
        rows[index][6]
        and len(passed := frozenset(family for family in essential if rows[index][2].get(family) == "pass")) >= _ceil75(blueprint, len(essential))
        and "king_safety" in passed
        and len(passed & special) >= blueprint._data["gate"]["delayed"]["required_passed_set_min"]
        for index in range(6)
    ) >= blueprint._data["gate"]["delayed"]["learners_min"]
    unhinted = all(not row[4] and not row[5] for row in rows)
    return GateResult(
        protocol,
        essential_family,
        essential_individual,
        core3_family,
        core3_combined,
        delayed_family and delayed_individual,
        unhinted,
    )


def _options(item: object) -> tuple[tuple[dict[str, object], ...], int, str, bool, object]:
    if type(item) is not dict or set(item) != {
        "shape", "max_selections", "repeat_allowed", "options", "prior_accepted_responses"
    }:
        _fail("closed visible schedule item")
    shape = item["shape"]
    cap = _exact_int(item["max_selections"], 0, C.CONTENT_MAX_SELECTIONS, "selection cap")
    repeat = item["repeat_allowed"]
    raw_options = item["options"]
    if shape not in {"single", "set", "sequence"} or type(repeat) is not bool or type(raw_options) not in (list, tuple):
        _fail("invalid visible schedule item")
    _exact_int(len(raw_options), 0, C.CONTENT_MAX_SELECTIONS, "visible option count")
    options: list[dict[str, object]] = []
    ordinals: set[int] = set()
    allowed = {"ordinal", *_OBSERVABLE_FEATURES}
    integer_features = {
        "visible_option_octets", "region_area", "region_count", "highlight_count",
        "selectable_count", "record_payload_octets", "node_branch_count", "response_timing",
    }
    for option in raw_options:
        if type(option) is not dict or set(option) != allowed:
            _fail("invalid visible option")
        ordinal = _exact_int(option["ordinal"], 1, 0xFFFF, "visible ordinal")
        if ordinal in ordinals:
            _fail("duplicate visible ordinal")
        ordinals.add(ordinal)
        for key in integer_features:
            _exact_int(option[key], 0, 0xFFFFFFFF, key)
        for key in set(_OBSERVABLE_FEATURES) - integer_features:
            _bounded_observable_key(option[key])
        options.append(option)
    return tuple(sorted(options, key=lambda option: option["ordinal"])), cap, shape, repeat, item["prior_accepted_responses"]


def _bounded_observable_key(
    value: object, *, depth: int = 0, budget: list[int] | None = None
) -> tuple[object, ...]:
    if budget is not None:
        budget[0] += 1
        _exact_int(budget[0], 0, C.CONTENT_MAX_VECTOR_ATOMS, "cue aggregate work")
    if depth > 16:
        _fail("observable depth")
    if value is None or type(value) in (bool, int):
        return _value_key(value)
    if type(value) is str:
        if len(value.encode("utf-8")) > C.CONTENT_MAX_PAYLOAD_BYTES:
            _fail("observable text length")
        return _value_key(value)
    if type(value) is bytes:
        if len(value) > C.CONTENT_MAX_PAYLOAD_BYTES:
            _fail("observable byte length")
        return _value_key(value)
    if type(value) in (tuple, list):
        _exact_int(len(value), 0, C.CONTENT_MAX_SELECTIONS, "observable vector length")
        return (
            "sequence",
            *(
                _bounded_observable_key(item, depth=depth + 1, budget=budget)
                for item in value
            ),
        )
    if type(value) is dict:
        _exact_int(len(value), 0, C.CONTENT_MAX_SELECTIONS, "observable mapping length")
        if any(type(key) is not str for key in value):
            _fail("invalid observable mapping")
        return (
            "mapping",
            *(
                (key, _bounded_observable_key(value[key], depth=depth + 1, budget=budget))
                for key in sorted(value)
            ),
        )
    _fail("unsupported observable value")


def _schedule_work(schedule: object) -> int:
    if type(schedule) not in (list, tuple):
        _fail("invalid visible schedule")
    budget = [0]

    def spend(amount: int) -> None:
        budget[0] += amount
        _exact_int(budget[0], 0, C.CONTENT_MAX_VECTOR_ATOMS, "cue aggregate work")

    for item in schedule:
        if type(item) is not dict or set(item) != {
            "shape", "max_selections", "repeat_allowed", "options", "prior_accepted_responses"
        }:
            _fail("closed visible schedule item")
        options = item["options"]
        if type(options) not in (list, tuple):
            _fail("invalid visible options")
        _exact_int(len(options), 0, C.CONTENT_MAX_SELECTIONS, "visible option count")
        spend(len(options))
        prior = item["prior_accepted_responses"]
        if prior is not None:
            if type(prior) not in (list, tuple):
                _fail("invalid prior accepted responses")
            _exact_int(len(prior), 0, C.CONTENT_MAX_CASES_PER_NODE, "prior response count")
            for response in prior:
                if type(response) not in (list, tuple):
                    _fail("invalid prior accepted response")
                _exact_int(len(response), 0, C.CONTENT_MAX_SELECTIONS, "prior response length")
                spend(len(response) + 1)
        for option in options:
            if type(option) is dict:
                for feature in _OBSERVABLE_FEATURES:
                    if feature in option and feature not in {
                        "visible_option_octets", "region_area", "region_count", "highlight_count",
                        "selectable_count", "record_payload_octets", "node_branch_count", "response_timing",
                    }:
                        _bounded_observable_key(option[feature], budget=budget)
    return budget[0]


def _mechanical(response: tuple[int, ...], ordinals: frozenset[int], cap: int, shape: str, repeat: bool) -> bool:
    return (
        len(response) <= cap
        and all(type(value) is int and value in ordinals for value in response)
        and (shape != "single" or len(response) <= 1)
        and (shape != "set" or tuple(sorted(set(response))) == response)
        and (repeat or len(set(response)) == len(response))
    )


@_fail_closed
def evaluate_cue_strategy(blueprint: Blueprint, strategy_id: str, visible_schedule: object) -> tuple[tuple[int, ...], ...]:
    """Run one total, deterministic curriculum-v0 cue strategy."""
    blueprint = _blueprint(blueprint)
    if type(strategy_id) is not str or strategy_id not in blueprint._ids["cue_strategy"] or type(visible_schedule) not in (list, tuple):
        _fail("unknown cue strategy or schedule")
    _exact_int(
        len(visible_schedule), 0,
        blueprint._data["capacity"]["records_per_curriculum_family_max"] * len(blueprint._ids["family"]),
        "visible schedule length",
    )
    _schedule_work(visible_schedule)
    output: list[tuple[int, ...]] = []
    metrics = {
        "shortest": ("visible_option_octets", min),
        "longest": ("visible_option_octets", max),
        "largest_region": ("region_area", max),
        "most_highlighted": ("highlight_count", max),
    }
    for index, raw_item in enumerate(visible_schedule):
        options, cap, shape, repeat, prior = _options(raw_item)
        if not options or cap == 0 or strategy_id == "empty_commit":
            output.append(())
            continue
        ordinals = frozenset(option["ordinal"] for option in options)
        first = (options[0]["ordinal"],)
        last = (options[-1]["ordinal"],)
        if strategy_id == "first":
            response = first
        elif strategy_id == "last":
            response = last
        elif strategy_id in metrics:
            metric, chooser = metrics[strategy_id]
            values = [option[metric] for option in options if metric in option]
            if not values:
                response = ()
            else:
                target = chooser(values)
                response = (min(option["ordinal"] for option in options if option.get(metric) == target),)
        elif strategy_id == "alternating":
            response = first if index % 2 == 0 else last
        elif strategy_id == "select_all_visible":
            response = tuple(sorted(ordinals))[:cap]
            if shape == "single":
                response = response[:1]
        elif strategy_id == "same_as_prior":
            if prior is None:
                response = first
            elif type(prior) not in (list, tuple) or any(type(candidate) not in (list, tuple) for candidate in prior):
                _fail("invalid prior accepted responses")
            else:
                _exact_int(len(prior), 0, C.CONTENT_MAX_CASES_PER_NODE, "prior response count")
                candidates: list[tuple[int, ...]] = []
                for candidate in prior:
                    _exact_int(len(candidate), 0, C.CONTENT_MAX_SELECTIONS, "prior response length")
                    mapped = tuple(candidate)
                    if shape == "set":
                        mapped = tuple(sorted(set(mapped)))
                    if _mechanical(mapped, ordinals, cap, shape, repeat):
                        candidates.append(mapped)
                response = min(candidates) if candidates else first
        else:
            _fail("unimplemented cue strategy")
        output.append(response if _mechanical(response, ordinals, cap, shape, repeat) else first)
    return tuple(output)


def _owner_result(blueprint: Blueprint, owner: object, argument: object) -> object:
    if type(owner) is not str:
        _fail("invalid owner call")
    if owner in blueprint._ids["predicate_mapping"] and owner.startswith("chess."):
        if owner == "chess.history_claim" and type(argument) is chess.ReplayState:
            argument = chess.HistoryClaimInput(argument)
        elif owner == "chess.move_record_replay" and type(argument) is bytes:
            argument = chess.MoveBytesInput(argument)
        try:
            return chess.evaluate_predicate(owner.encode("ascii"), argument)
        except chess.ChessReject as error:
            return error.code
    if owner == "source.decode_game":
        if type(argument) is not bytes:
            _fail("invalid source owner call")
        try:
            source_compiler.decode_game(argument)
            return "accept"
        except source_compiler.SourceReject as error:
            return error.code
    if owner == "content.stream_validation":
        if type(argument) is not bytes:
            _fail("invalid content owner call")
        try:
            content.stream_validation(argument)
            return "accept"
        except content.ContentReject as error:
            return error.code
    _fail("unresolved executable owner")


def _value_key(value: object) -> tuple[object, ...]:
    """Full tagged structural identity; hashes and author keys are never authority."""
    if value is None:
        return ("none",)
    if type(value) in (bool, int, str, bytes):
        return (type(value).__name__, value)
    if type(value) in (tuple, list):
        return ("sequence", *(_value_key(item) for item in value))
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            _fail("invalid structural mapping")
        return ("mapping", *((key, _value_key(value[key])) for key in sorted(value)))
    if type(value) is chess.WirePosition:
        return ("WirePosition", chess.encode_position(value))
    if type(value) is chess.LocallyAdmissiblePosition:
        return ("LocallyAdmissiblePosition", chess.encode_position(value.position))
    if type(value) is chess.Move:
        return ("Move", chess.encode_move(value))
    if type(value) is chess.Event:
        return ("Event", chess.encode_event(value))
    if is_dataclass(value):
        return (
            type(value).__qualname__,
            *((field.name, _value_key(getattr(value, field.name))) for field in fields(value)),
        )
    _fail("unsupported structural value")


def _authority(kind: object, raw: object) -> tuple[object, tuple[object, ...]]:
    if kind == "board_local_position" and type(raw) is bytes:
        position = chess.decode_position(raw)
        chess.validate_local(position)
        return position, (kind, raw)
    if kind == "complete_replay_moves" and type(raw) in (list, tuple):
        _exact_int(len(raw), 0, C.SOURCE_MAX_GAME_PLIES, "replay authority plies")
        if any(type(value) is not bytes for value in raw):
            _fail("invalid replay authority")
        moves = tuple(chess.decode_move(value) for value in raw)
        return chess.replay_from_start(moves), (kind, *raw)
    if kind == "complete_game_events_status" and type(raw) in (list, tuple):
        _exact_int(len(raw), 0, C.SOURCE_MAX_GAME_PLIES + 1, "event authority length")
        if any(type(value) is not bytes for value in raw):
            _fail("invalid event authority")
        game = chess.new_game()
        for value in raw:
            game = chess.apply_event(game, chess.decode_event(value))
        return game, (kind, *raw)
    if kind == "source_game_bytes" and type(raw) is bytes:
        return source_compiler.decode_game(raw), (kind, raw)
    if kind == "content_bytes" and type(raw) is bytes:
        content.stream_validation(raw)
        return raw, (kind, raw)
    _fail("invalid case authority")


def _bound_to_authority(argument: object, kind: str, raw: object, authority_value: object) -> bool:
    if type(argument) is chess.WirePosition:
        position = authority_value.position if type(authority_value) is chess.ReplayState else (
            authority_value.replay.position if type(authority_value) is chess.GameState else authority_value
        )
        return type(position) is chess.WirePosition and chess.encode_position(argument) == chess.encode_position(position)
    if type(argument) is chess.LocallyAdmissiblePosition:
        return _bound_to_authority(argument.position, kind, raw, authority_value)
    if type(argument) is chess.ReplayState:
        replay = authority_value.replay if type(authority_value) is chess.GameState else authority_value
        return type(replay) is chess.ReplayState and _value_key(argument) == _value_key(replay)
    if type(argument) is chess.GameState:
        return type(authority_value) is chess.GameState and _value_key(argument) == _value_key(authority_value)
    if type(argument) is bytes:
        return kind in {"source_game_bytes", "content_bytes"} and argument == raw
    if type(argument) in (tuple, list):
        if argument and all(type(value) is chess.Move for value in argument):
            moves = tuple(chess.encode_move(value) for value in argument)
            expected = tuple(raw) if kind == "complete_replay_moves" else tuple(
                raw[offset : offset + 2] for offset in range(2, len(raw) - 1, 2)
            ) if kind == "source_game_bytes" else ()
            if moves == expected:
                return True
        return any(_bound_to_authority(value, kind, raw, authority_value) for value in argument)
    if is_dataclass(argument):
        return any(
            _bound_to_authority(getattr(argument, field.name), kind, raw, authority_value)
            for field in fields(argument)
        )
    return False


def _map_square(square: int, transform_id: str) -> int:
    matrix, offset, _swap = _TRANSFORMS[transform_id]
    file, rank = square % 8, square // 8
    return (matrix[0] * file + matrix[1] * rank + offset[0]) + 8 * (
        matrix[2] * file + matrix[3] * rank + offset[1]
    )


def _map_side(side: int, transform_id: str) -> int:
    return side ^ int(_TRANSFORMS[transform_id][2])


def _map_position(position: chess.WirePosition, transform_id: str) -> chess.WirePosition:
    raw = bytearray(C.CHESS_POSITION_BYTES)
    swap = _TRANSFORMS[transform_id][2]
    for square, code in enumerate(position.squares):
        if swap and C.SQUARE_FIRST_PAWN <= code <= C.SQUARE_FIRST_KING:
            code += 6
        elif swap and C.SQUARE_SECOND_PAWN <= code <= C.SQUARE_SECOND_KING:
            code -= 6
        raw[_map_square(square, transform_id)] = code
    raw[64] = _map_side(position.side_to_move, transform_id)
    rights = 0
    right_bits = (
        (C.SIDE_FIRST, True, C.CASTLING_FIRST_KINGSIDE),
        (C.SIDE_FIRST, False, C.CASTLING_FIRST_QUEENSIDE),
        (C.SIDE_SECOND, True, C.CASTLING_SECOND_KINGSIDE),
        (C.SIDE_SECOND, False, C.CASTLING_SECOND_QUEENSIDE),
    )
    output_bits = {
        (C.SIDE_FIRST, True): C.CASTLING_FIRST_KINGSIDE,
        (C.SIDE_FIRST, False): C.CASTLING_FIRST_QUEENSIDE,
        (C.SIDE_SECOND, True): C.CASTLING_SECOND_KINGSIDE,
        (C.SIDE_SECOND, False): C.CASTLING_SECOND_QUEENSIDE,
    }
    for side, kingside, bit in right_bits:
        if position.castling_rights & bit:
            rank = 0 if side == C.SIDE_FIRST else 7
            king = _map_square(rank * 8 + 4, transform_id)
            rook = _map_square(rank * 8 + (7 if kingside else 0), transform_id)
            rights |= output_bits[(_map_side(side, transform_id), rook % 8 > king % 8)]
    raw[65] = rights
    raw[66] = 0 if position.nominal_en_passant == 0 else _map_square(position.nominal_en_passant - 1, transform_id) + 1
    mapped = chess.decode_position(bytes(raw))
    chess.validate_local(mapped)
    return mapped


def _map_move(move: chess.Move, transform_id: str) -> chess.Move:
    value = (
        (_map_square(move.origin, transform_id) << C.CHESS_MOVE_ORIGIN_SHIFT)
        | (_map_square(move.destination, transform_id) << C.CHESS_MOVE_DESTINATION_SHIFT)
        | (move.promotion << C.CHESS_MOVE_PROMOTION_SHIFT)
    )
    return chess.decode_move(value.to_bytes(2, "big"))


def _map_event(event: chess.Event, transform_id: str) -> chess.Event:
    if event.kind == C.EVENT_MOVE:
        return chess.decode_event(bytes((event.kind,)) + chess.encode_move(_map_move(event.move, transform_id)))
    if event.kind == C.EVENT_RESIGNATION:
        return chess.decode_event(bytes((event.kind, _map_side(event.side, transform_id))))
    return chess.decode_event(chess.encode_event(event))


def _mapped_authority(kind: str, raw: object, transform_id: str) -> tuple[object, object, tuple[object, ...]]:
    if transform_id == "identity":
        value, key = _authority(kind, raw)
        return raw, value, key
    if kind == "board_local_position":
        mapped = _map_position(chess.decode_position(raw), transform_id)
        encoded = chess.encode_position(mapped)
        return encoded, mapped, (kind, encoded)
    if kind == "complete_replay_moves":
        encoded = tuple(chess.encode_move(_map_move(chess.decode_move(value), transform_id)) for value in raw)
        replay = chess.replay_from_start(tuple(chess.decode_move(value) for value in encoded))
        return encoded, replay, (kind, *encoded)
    if kind == "complete_game_events_status":
        encoded = tuple(chess.encode_event(_map_event(chess.decode_event(value), transform_id)) for value in raw)
        game = chess.new_game()
        for value in encoded:
            game = chess.apply_event(game, chess.decode_event(value))
        return encoded, game, (kind, *encoded)
    if kind == "source_game_bytes":
        record = source_compiler.decode_game(raw)
        moves = tuple(_map_move(move, transform_id) for move in record.moves)
        score = record.score
        if _TRANSFORMS[transform_id][2] and score in (C.SCORE_FIRST_WIN, C.SCORE_SECOND_WIN):
            score = C.SCORE_SECOND_WIN if score == C.SCORE_FIRST_WIN else C.SCORE_FIRST_WIN
        encoded = len(moves).to_bytes(2, "big") + b"".join(chess.encode_move(move) for move in moves) + bytes((score,))
        mapped_record = source_compiler.decode_game(encoded)
        return encoded, mapped_record, (kind, encoded)
    if kind == "content_bytes" and transform_id == "identity":
        return raw, raw, (kind, raw)
    _fail("inapplicable authority transform")


def _applicable_authority(kind: str, raw: object, transform_id: str):
    try:
        return _mapped_authority(kind, raw, transform_id)
    except (CurriculumError, chess.ChessReject, source_compiler.SourceReject, content.ContentReject):
        return None


def _mapped_value(value: object, transform_id: str, authority_value: object, name: str = "") -> object:
    swap = _TRANSFORMS[transform_id][2]
    if type(value) in (type(None), bool, bytes):
        return value
    if type(value) is int:
        if name in {"side", "controlling_side", "mating_side", "winning_side"} and value in (0, 1):
            return _map_side(value, transform_id)
        if name in {"square", "target", "origin", "candidate", "pawn_square", "slider_origin"} and 0 <= value < 64:
            return _map_square(value, transform_id)
        if name == "file" and 0 <= value < 8:
            return _map_square(value, transform_id) % 8
        if name == "score" and swap and value in (C.SCORE_FIRST_WIN, C.SCORE_SECOND_WIN):
            return C.SCORE_SECOND_WIN if value == C.SCORE_FIRST_WIN else C.SCORE_FIRST_WIN
        return value
    if type(value) is str:
        if not swap:
            return value
        return value.replace("first", "__side__").replace("second", "first").replace("__side__", "second")
    if type(value) in (tuple, list):
        mapped = tuple(_mapped_value(item, transform_id, authority_value, name) for item in value)
        if name in {"targets", "outcomes"}:
            mapped = tuple(sorted(mapped, key=_value_key))
        return mapped
    if type(value) is chess.WirePosition:
        return _map_position(value, transform_id)
    if type(value) is chess.LocallyAdmissiblePosition:
        return chess.validate_local(_map_position(value.position, transform_id))
    if type(value) is chess.Move:
        return _map_move(value, transform_id)
    if type(value) is chess.Event:
        return _map_event(value, transform_id)
    if type(value) is chess.ReplayState:
        if type(authority_value) is source_compiler.GameRecord:
            return chess.replay_from_start(authority_value.moves)
        if type(authority_value) is not chess.ReplayState:
            _fail("inapplicable replay transform")
        return authority_value
    if type(value) is chess.GameState:
        if type(authority_value) is not chess.GameState:
            _fail("inapplicable game transform")
        return authority_value
    if is_dataclass(value):
        return replace(
            value,
            **{
                field.name: _mapped_value(getattr(value, field.name), transform_id, authority_value, field.name)
                for field in fields(value)
            },
        )
    _fail("inapplicable typed transform")


def _mapped_result(value: object, mapping_id: str, transform_id: str, authority_value: object) -> object:
    if mapping_id == "transform_and_resort_square_list":
        if type(value) is not tuple or any(type(square) is not int or not 0 <= square < 64 for square in value):
            _fail("invalid square-list result")
        return tuple(sorted(_map_square(square, transform_id) for square in value))
    return _mapped_value(value, transform_id, authority_value)


def _prompt_value(prompt: object) -> tuple[str, object]:
    if type(prompt) is not dict or set(prompt) != {"type_id", "value"} or type(prompt["type_id"]) is not str:
        _fail("closed semantic prompt")
    type_id, value = prompt["type_id"], prompt["value"]
    if type_id == "ByteSlice":
        if type(value) is not bytes or len(value) > _BYTE_CAP:
            _fail("invalid byte prompt")
    elif type_id == "Text":
        if type(value) is not str or len(value.encode("utf-8")) > _BYTE_CAP:
            _fail("invalid text prompt")
    elif type_id == "Square":
        _exact_int(value, 0, 63, "prompt square")
    elif type_id == "Side":
        _exact_int(value, 0, 1, "prompt side")
    elif type_id == "File":
        _exact_int(value, 0, 7, "prompt file")
    elif type_id == "Score":
        if type(value) is not int or value not in {C.SCORE_FIRST_WIN, C.SCORE_SECOND_WIN, C.SCORE_DRAW}:
            _fail("invalid prompt score")
    elif type_id == "Move":
        if type(value) is not bytes:
            _fail("invalid move prompt")
        chess.decode_move(value)
    elif type_id == "SquareSlice":
        if (
            type(value) not in (list, tuple)
            or len(value) > C.CONTENT_MAX_SELECTIONS
            or any(type(square) is not int or not 0 <= square < 64 for square in value)
        ):
            _fail("invalid square-list prompt")
        value = tuple(value)
    elif type_id == "Boolean":
        if type(value) is not bool:
            _fail("invalid boolean prompt")
    else:
        _fail("unknown semantic prompt type")
    return type_id, value


def _mapped_prompt(prompt: object, transform_id: str) -> dict[str, object]:
    type_id, value = _prompt_value(prompt)
    if type_id == "Square":
        value = _map_square(value, transform_id)
    elif type_id == "Side":
        value = _map_side(value, transform_id)
    elif type_id == "File":
        value = _map_square(value, transform_id) % 8
    elif type_id == "Score" and _TRANSFORMS[transform_id][2] and value in {C.SCORE_FIRST_WIN, C.SCORE_SECOND_WIN}:
        value = C.SCORE_SECOND_WIN if value == C.SCORE_FIRST_WIN else C.SCORE_FIRST_WIN
    elif type_id == "Move":
        value = chess.encode_move(_map_move(chess.decode_move(value), transform_id))
    elif type_id == "SquareSlice":
        value = tuple(sorted(_map_square(square, transform_id) for square in value))
    return {"type_id": type_id, "value": value}


def _prompt_matches_calls(
    prompt: object, context_values: tuple[tuple[object, str, str], ...]
) -> bool:
    type_id, value = _prompt_value(prompt)
    if type_id not in {"Square", "Side", "File", "Score", "Move", "SquareSlice"}:
        return True
    candidates = tuple(
        candidate
        for candidate, candidate_type, _source_id in context_values
        if candidate_type == type_id
    )
    if type_id == "Move":
        candidates = tuple(chess.encode_move(candidate) for candidate in candidates)
    return any(type(candidate) is type(value) and candidate == value for candidate in candidates)


def _case_key(
    item: dict[str, object],
    authority_key: tuple[object, ...],
    calls: tuple[tuple[str, str, object, object], ...],
    *,
    shown: object | None = None,
    prompt: object | None = None,
    accepted: object | None = None,
) -> tuple[object, ...]:
    shown = item["shown_move_bytes"] if shown is None else shown
    patterns = item["case_pattern_ids"]
    accepted = item["accepted_responses"] if accepted is None else accepted
    prompt = item["prompt_target"] if prompt is None else prompt
    if type(shown) not in (list, tuple) or any(type(value) is not bytes for value in shown):
        _fail("invalid shown moves")
    if (
        type(patterns) not in (list, tuple)
        or any(type(value) is not str for value in patterns)
        or tuple(sorted(set(patterns))) != tuple(patterns)
    ):
        _fail("invalid case patterns")
    if type(accepted) not in (list, tuple):
        _fail("invalid accepted responses")
    _exact_int(len(accepted), 1, C.CONTENT_MAX_VECTOR_ATOMS, "accepted response count")
    accepted_keys = tuple(_value_key(value) for value in accepted)
    if len(set(accepted_keys)) != len(accepted_keys):
        _fail("duplicate accepted response")
    prompt_type, prompt_value = _prompt_value(prompt)
    return (
        authority_key,
        tuple(shown),
        tuple(patterns),
        tuple((identifier, _value_key(argument)) for identifier, _owner, argument, _actual in calls),
        _value_key({"type_id": prompt_type, "value": prompt_value}),
        tuple(sorted(accepted_keys)),
    )


def _matches_type(value: object, type_id: str) -> bool:
    classes = {
        "WirePosition": chess.WirePosition,
        "LocallyAdmissiblePosition": chess.LocallyAdmissiblePosition,
        "ReplayState": chess.ReplayState,
        "GameState": chess.GameState,
        "Move": chess.Move,
        "Event": chess.Event,
        "OccupancyMatch": chess.OccupancyMatch,
        "Defender": chess.Defender,
        "FinitePromotionTree": chess.FinitePromotionTree,
        "FiniteMatingTree": chess.FiniteMatingTree,
    }
    if type_id in classes:
        return type(value) is classes[type_id]
    if type_id == "Side":
        return type(value) is int and value in {C.SIDE_FIRST, C.SIDE_SECOND}
    if type_id == "Square":
        return type(value) is int and 0 <= value < 64
    if type_id == "File":
        return type(value) is int and 0 <= value < 8
    if type_id == "Score":
        return type(value) is int and value in {C.SCORE_FIRST_WIN, C.SCORE_SECOND_WIN, C.SCORE_DRAW}
    if type_id == "ByteSlice":
        return type(value) is bytes
    if type_id == "MoveSlice":
        return type(value) is tuple and all(type(move) is chess.Move for move in value)
    if type_id == "SquareSlice":
        return type(value) is tuple and all(type(square) is int and 0 <= square < 64 for square in value)
    return False


def _call_values(argument: object, binding: dict[str, object]) -> tuple[object, ...]:
    declarations = tuple(sorted(binding["arguments"], key=lambda row: row["position"]))
    if tuple(row["position"] for row in declarations) != tuple(range(len(declarations))):
        _fail("nonpositional input binding")
    if len(declarations) == 1 and _matches_type(argument, declarations[0]["type_id"]):
        values = (argument,)
    elif is_dataclass(argument):
        values = tuple(getattr(argument, field.name) for field in fields(argument))
    else:
        _fail("input binding variant mismatch")
    if len(values) != len(declarations) or any(
        not _matches_type(value, declaration["type_id"])
        for value, declaration in zip(values, declarations, strict=True)
    ):
        _fail("input binding type mismatch")
    return values


def _authority_side(value: object) -> int:
    if type(value) is chess.WirePosition:
        return value.side_to_move
    if type(value) is chess.LocallyAdmissiblePosition:
        return value.position.side_to_move
    if type(value) is chess.ReplayState:
        return value.position.side_to_move
    if type(value) is chess.GameState:
        return value.replay.position.side_to_move
    _fail("constant has no authority side")


def _constant_value(
    constant: dict[str, object],
    values: tuple[object, ...],
    declarations: tuple[dict[str, object], ...],
    authority_value: object,
    context_values: tuple[tuple[object, str, str], ...],
) -> object:
    constructor = constant["constructor_id"]
    value_ids = tuple(constant["value_ids"])
    if constructor == "side" and len(value_ids) == 1:
        return {"first": C.SIDE_FIRST, "second": C.SIDE_SECOND}.get(value_ids[0], object())
    if constructor == "score" and len(value_ids) == 1:
        return {
            "first_win": C.SCORE_FIRST_WIN,
            "second_win": C.SCORE_SECOND_WIN,
            "draw": C.SCORE_DRAW,
        }.get(value_ids[0], object())
    if constructor == "occupied" and not value_ids:
        return chess.OccupancyMatch("occupied")
    if constructor == "exact_piece" and len(value_ids) == 2:
        side_id, piece_id = value_ids
        if side_id == "bound_controller_side":
            side = next(
                (value for value, row in zip(values, declarations, strict=True) if row["type_id"] == "Side"),
                None,
            )
            if side is None:
                side = next(
                    (
                        value
                        for value, type_id, _source_id in context_values
                        if type_id == "Side"
                    ),
                    None,
                )
            if side is None:
                _fail("missing bound controller side")
        else:
            side = _authority_side(authority_value)
            if side_id == "opposing_side":
                side ^= 1
            elif side_id != "moving_side":
                _fail("unknown piece-side constant")
        piece = {
            "pawn": 1, "knight": 2, "bishop": 3,
            "rook": 4, "queen": 5, "king": 6,
        }.get(piece_id)
        if piece is not None:
            return chess.OccupancyMatch("exact", side, piece)
    _fail("unknown call constant")


def _contract_accepts(
    actual: object,
    contract: dict[str, object],
    values: tuple[object, ...],
    declarations: tuple[dict[str, object], ...],
    context_values: tuple[tuple[object, str, str], ...],
) -> bool:
    reject = contract["reject_code_id"]
    if reject:
        expected = getattr(C, reject, None)
        return expected is not None and (
            (type(actual) is int and actual == expected)
            or (is_dataclass(actual) and getattr(actual, "code", None) == expected)
        )
    variant = contract["result_variant_id"]
    if variant == "bool_true":
        return actual is True
    if variant == "bool_false":
        return actual is False
    if variant == "square_list":
        if type(actual) is not tuple or any(type(square) is not int or not 0 <= square < 64 for square in actual):
            return False
        constraint = contract["constraint_id"]
        bound_squares = {
            value
            for value, type_id, source_id in context_values
            if type_id == "Square" and source_id == "bound.controller_origin"
        }
        bound_squares.update(
            value.origin
            for value, type_id, source_id in context_values
            if type_id == "Move" and source_id == "bound.shown_move"
        )
        return (
            constraint == "nonempty" and bool(actual)
            or constraint == "contains_bound_origin"
            and len(bound_squares) == 1
            and next(iter(bound_squares)) in actual
            or constraint == "cardinality_at_least_two" and len(actual) >= 2
        )
    if variant == "move_legal":
        return type(actual) is chess.MoveLegalityResult and actual.kind == "legal"
    terminals = {
        "terminal_none": C.BOARD_TERMINAL_NONE,
        "terminal_checkmate": C.BOARD_TERMINAL_CHECKMATE,
        "terminal_stalemate": C.BOARD_TERMINAL_STALEMATE,
        "terminal_common_dead": C.BOARD_TERMINAL_COMMON_DEAD,
    }
    if variant in terminals:
        return type(actual) is chess.BoardTerminal and actual.kind == terminals[variant]
    if variant == "history_claim_fields":
        if type(actual) is not chess.HistoryClaimResult:
            return False
        constraint = contract["constraint_id"]
        checks = {
            "exact": True,
            "nominal_ep_absent": actual.nominal_ep.square is None,
            "nominal_ep_present_effective_absent": actual.nominal_ep.square is not None and actual.effective_ep.square is None,
            "nominal_ep_present_equals_effective": actual.nominal_ep.square is not None and actual.nominal_ep == actual.effective_ep,
            "current_key_occurrences_2": actual.current_key_occurrences == 2,
            "current_key_occurrences_3": actual.current_key_occurrences == 3,
            "halfmove_99_claim_false": actual.halfmove_clock == 99 and not actual.fifty_move_available,
            "halfmove_100_claim_true": actual.halfmove_clock == 100 and actual.fifty_move_available,
            "halfmove_nonzero": actual.halfmove_clock > 0,
            "halfmove_zero": actual.halfmove_clock == 0,
            "claim_available": actual.threefold_available or actual.fifty_move_available,
        }
        return checks.get(constraint, False)
    declaration_status = {
        "declaration_accepted_game_status_resigned": C.GAME_STATUS_RESIGNED,
        "declaration_accepted_game_status_agreed": C.GAME_STATUS_AGREED,
        "declaration_accepted_game_status_claimed_threefold": C.GAME_STATUS_CLAIMED_THREEFOLD,
        "declaration_accepted_game_status_claimed_50_move": C.GAME_STATUS_CLAIMED_50_MOVE,
    }
    if variant in declaration_status:
        return (
            type(actual) is chess.DeclarationEventResult
            and actual.kind == "accepted"
            and actual.status == declaration_status[variant]
        )
    if variant == "source_accepted_terminal_none":
        return (
            type(actual) is chess.SourceScoreResult and actual.kind == "accepted"
            and type(actual.terminal) is chess.BoardTerminal
            and actual.terminal.kind == C.BOARD_TERMINAL_NONE
        )
    if variant == "move_decoded":
        return type(actual) is chess.MoveRecordResult and actual.kind == "decoded"
    if variant == "record_replayed":
        return type(actual) is chess.MoveRecordResult and actual.kind == "replayed"
    if variant == "content_accepted":
        return actual == "accept"
    if variant == "finite_race_result":
        return type(actual) is chess.FiniteRaceResult
    if variant == "finite_mating_result":
        return type(actual) is chess.FiniteMatingResult
    return False


def _validate_declared_call(
    declared: dict[str, object],
    binding: dict[str, object],
    contract: dict[str, object],
    argument: object,
    actual: object,
    kind: str,
    raw: object,
    authority_value: object,
    context_values: tuple[tuple[object, str, str], ...],
) -> None:
    values = _call_values(argument, binding)
    declarations = tuple(sorted(binding["arguments"], key=lambda row: row["position"]))
    constants = tuple(declared["input_constants"])
    positions = {constant["argument_position"] for constant in constants}
    expected_positions = {
        declaration["position"]
        for declaration in declarations
        if declaration["source_kind"] == "call_constant"
    }
    if len(positions) != len(constants) or positions != expected_positions:
        _fail("duplicate call constant position")
    for constant in constants:
        position = constant["argument_position"]
        if type(position) is not int or not 0 <= position < len(values):
            _fail("invalid call constant position")
        if constant["type_id"] != declarations[position]["type_id"]:
            _fail("call constant type mismatch")
        expected = _constant_value(
            constant, values, declarations, authority_value, context_values
        )
        if type(values[position]) is not type(expected) or values[position] != expected:
            _fail("call constant mismatch")
    shown = next(
        (
            value for value, type_id, source_id in context_values
            if type_id == "Move" and source_id == "bound.shown_move"
        ),
        None,
    )
    derived_bound = (
        binding["id"] == "post_move_history"
        and type(authority_value) is chess.ReplayState
        and type(shown) is chess.Move
        and _value_key(values[0]) == _value_key(chess.apply_move(authority_value, shown))
        or binding["id"] == "canonical_shown_move_bytes"
        and type(shown) is chess.Move
        and values == (chess.encode_move(shown),)
        or binding["id"] == "source_derived_history"
        and type(authority_value) is source_compiler.GameRecord
        and _value_key(values[0]) == _value_key(chess.replay_from_start(authority_value.moves))
    )
    if not derived_bound and not any(
        _bound_to_authority(value, kind, raw, authority_value) for value in values
    ):
        _fail("owner call is not bound to authority")
    if not _contract_accepts(actual, contract, values, declarations, context_values):
        _fail("owner result contract mismatch")


def _lint_items(blueprint: Blueprint, items: object, *, complete: bool = False) -> None:
    if type(items) not in (list, tuple) or not items:
        _fail("invalid synthetic items")
    _exact_int(
        len(items), 0,
        blueprint._data["capacity"]["records_per_curriculum_family_max"] * len(blueprint._ids["family"]),
        "synthetic item count",
    )
    seen_ids: set[str] = set()
    semantic: set[tuple[object, ...]] = set()
    forms: dict[str, list[tuple[object, ...]]] = defaultdict(list)
    integrated_forms: dict[str, list[tuple[object, ...]]] = defaultdict(list)
    generic_forms: set[str] = set()
    pairs: dict[str, list[dict[str, object]]] = defaultdict(list)
    roles = {row["id"]: row for row in blueprint._data["role"]}
    generators = {row["id"]: row for row in blueprint._data["generator"]}
    patterns = {row["id"]: row for row in blueprint._data["case_pattern"]}
    bindings = {row["id"]: row for row in blueprint._data["input_binding"]}
    contracts = {row["id"]: row for row in blueprint._data["result_contract"]}
    pattern_calls = {
        (pattern["id"], case["id"], call["id"]): call
        for pattern in patterns.values()
        for case in pattern["case"]
        for call in case["call"]
    }
    protected = frozenset(blueprint._data["leakage"]["protected_splits"])
    forbidden_public = frozenset(
        blueprint._data["roadmap_mirror"]["privacy_reveal"]
        ["learner_public_forbidden_before_authorized_reveal"]
    ) | frozenset(blueprint._data["cue_audit"]["private_feature_ids"]) | {"correctness"}
    family_counts: Counter[str] = Counter()
    assessment_counts: Counter[tuple[str, str]] = Counter()
    concept_counts: Counter[tuple[str, str]] = Counter()
    stratum_splits: dict[str, set[str]] = defaultdict(set)
    integrated_counts: Counter[tuple[str, str]] = Counter()
    instruction_templates: dict[str, set[str]] = defaultdict(set)
    posttest_templates: dict[str, set[str]] = defaultdict(set)
    practice_nodes: dict[str, Counter[str]] = defaultdict(Counter)
    family_concepts = {row["id"]: row["concept_id"] for row in blueprint._data["family"]}
    concept_rows = {row["id"]: row for row in blueprint._data["concept"]}
    family_concept_ids = frozenset(family_concepts.values())
    integrated_tasks = {row["id"]: row for row in blueprint._data["integrated_task"]}

    def reaches(start: str, target: str) -> bool:
        pending = [start]
        seen: set[str] = set()
        while pending:
            current = pending.pop()
            if current == target:
                return True
            if current not in seen:
                seen.add(current)
                pending.extend(concept_rows[current]["requires"])
        return False

    def related_concept(concept: str, anchor: str) -> bool:
        return concept == anchor or (
            concept not in family_concept_ids
            and reaches(anchor, concept)
        )
    for item in items:
        if type(item) is not dict or set(item) != _ITEM_KEYS:
            _fail("closed synthetic item")
        identifier = item["id"]
        if type(identifier) is not str or not identifier or identifier in seen_ids:
            _fail("duplicate synthetic item")
        seen_ids.add(identifier)
        family = item["family_id"]
        integrated = item["integrated_task_id"]
        if family is not None and integrated is not None:
            _fail("item cannot bind both family and integrated task")
        if family is not None and family not in blueprint._ids["family"]:
            _fail("unknown item family")
        if family is not None:
            family_counts[family] += 1
            if family_counts[family] > blueprint._data["capacity"]["records_per_curriculum_family_max"]:
                _fail("family capacity exceeded")
            if item["split"] in {"pretest", "posttest", "delayed"}:
                assessment_counts[(family, item["split"])] += 1
        if integrated is not None and integrated not in integrated_tasks:
            _fail("unknown integrated task")
        split = item["split"]
        role = roles.get(item["role_id"])
        if split not in blueprint._data["taxonomy"]["split_ids"] or role is None:
            _fail("unknown split or role")
        generator = generators.get(item["primary_generator_id"])
        if (
            generator is None or generator["split"] != split
            or generator["orthogonal"] is not False
            or generator["result_bearing"] is not item["result_bearing"]
        ):
            _fail("invalid primary generator")
        if item["response_shape"] not in blueprint._data["taxonomy"]["response_shape_ids"]:
            _fail("unknown response shape")
        _exact_int(item["max_selections"], 0, 0xFFFF, "item selection cap")
        _exact_int(item["visible_index"], 0, 0xFFFFFFFF, "visible index")
        if type(item["result_bearing"]) is not bool or item["result_bearing"] and role.get("may_define_scored_answer") is not True:
            _fail("role cannot define scored answer")
        concept_ids = item["concept_ids"]
        if (
            type(concept_ids) not in (list, tuple)
            or not concept_ids
            or tuple(sorted(set(concept_ids))) != tuple(concept_ids)
            or any(concept not in blueprint._ids["concept"] for concept in concept_ids)
            or family is not None and family_concepts[family] not in concept_ids
            or family is not None
            and any(not related_concept(concept, family_concepts[family]) for concept in concept_ids)
            or family is None and integrated is None
            and any(concept in family_concept_ids for concept in concept_ids)
        ):
            _fail("invalid item concepts")
        slot = item["authoring_slot"]
        slot_rules = {
            "grounding": (split in {"teaching", "practice"} and item["role_id"] in {"exact_rule", "observable_relation"}),
            "contrasting": (split in {"teaching", "practice"} and item["role_id"] == "worked_example"),
            "heuristic": (split in {"teaching", "practice"} and item["role_id"] == "heuristic"),
            "active": (split == "practice" and item["role_id"] == "practice"),
            "held_out": (split == "practice" and item["role_id"] == "practice"),
            "feedback": (split == "practice" and item["role_id"] == "feedback"),
            "passive": (split == "practice" and item["role_id"] == "passive_trace"),
            "assessment": (split in {"pretest", "posttest", "delayed"} and family is not None),
            "integrated": (integrated is not None),
        }
        if type(slot) is not str or slot not in slot_rules or not slot_rules[slot]:
            _fail("invalid authoring slot")
        if integrated is not None and (
            split != integrated_tasks[integrated]["split"] or slot != "integrated"
        ):
            _fail("integrated task split mismatch")
        node = item["practice_node_id"]
        if slot in {"active", "feedback", "passive"}:
            if type(node) is not str or not node:
                _fail("missing practice-node link")
            practice_nodes[node][slot] += 1
        elif node is not None:
            _fail("unexpected practice-node link")
        for concept in concept_ids:
            concept_counts[(concept, slot)] += 1
        if (
            type(item["stratum_ids"]) not in (list, tuple)
            or tuple(sorted(set(item["stratum_ids"]))) != tuple(item["stratum_ids"])
        ):
            _fail("invalid strata")
        if type(item["public_fields"]) is not dict or set(item["public_fields"]) & forbidden_public:
            _fail("result-bearing field leakage")
        if type(item["observable_fingerprint"]) is not dict or set(item["observable_fingerprint"]) != set(_OBSERVABLE_FEATURES):
            _fail("incomplete observable fingerprint")
        observable_budget = [0]
        for value in item["observable_fingerprint"].values():
            _bounded_observable_key(value, budget=observable_budget)

        _authority_value, authority_key = _authority(item["authority_kind"], item["authority"])
        pattern_ids = item["case_pattern_ids"]
        if (
            tuple(item["stratum_ids"]) != tuple(pattern_ids)
            or any(
                pattern_id not in patterns
                or patterns[pattern_id]["authority_kind"] != item["authority_kind"]
                or (family is not None and pattern_id.split(".", 1)[0] != family)
                for pattern_id in pattern_ids
            )
        ):
            _fail("unresolved stratum authority")
        pattern_anchors = {
            family_concepts[pattern_id.split(".", 1)[0]] for pattern_id in pattern_ids
        }
        if family is None and integrated is None and any(
            not any(reaches(concept, anchor) or reaches(anchor, concept) for concept in concept_ids)
            for anchor in pattern_anchors
        ):
            _fail("unrelated generic concept")
        if integrated is not None and any(anchor not in concept_ids for anchor in pattern_anchors):
            _fail("integrated task concept mismatch")
        for pattern_id in pattern_ids:
            stratum_splits[pattern_id].add(split)
        if family is not None and split in {"teaching", "practice"}:
            instruction_templates[family].add(item["structural_template_id"])
        if family is not None and split == "posttest":
            posttest_templates[family].add(item["structural_template_id"])
        if type(item["owner_calls"]) not in (list, tuple):
            _fail("invalid owner calls")
        _exact_int(len(item["owner_calls"]), 1, len(blueprint._ids["input_binding"]), "owner call count")
        shown_raw = item["shown_move_bytes"]
        if type(shown_raw) not in (list, tuple) or any(type(value) is not bytes for value in shown_raw):
            _fail("invalid shown moves")
        shown_values = tuple(chess.decode_move(value) for value in shown_raw)
        context: list[tuple[object, str, str]] = []
        for call in item["owner_calls"]:
            if type(call) is not dict or set(call) != {"pattern_id", "case_id", "call_id", "argument"}:
                _fail("closed owner call")
            declared = pattern_calls.get((call["pattern_id"], call["case_id"], call["call_id"]))
            if declared is None or call["pattern_id"] not in pattern_ids:
                _fail("unresolved owner call")
            binding = bindings[declared["input_binding_id"]]
            values = _call_values(call["argument"], binding)
            declarations = tuple(sorted(binding["arguments"], key=lambda row: row["position"]))
            context.extend(
                (value, declaration["type_id"], declaration["source_id"])
                for value, declaration in zip(values, declarations, strict=True)
            )
            sources = {
                source
                for derivation in binding["derivations"]
                for source in derivation["input_source_ids"]
            }
            if "bound.shown_move" in sources:
                if len(shown_values) != 1:
                    _fail("derived shown move must be singular")
                context.append((shown_values[0], "Move", "bound.shown_move"))
        context_values = tuple(context)
        shown_moves: list[bytes] = []
        for value, type_id, source_id in context_values:
            if type_id == "Move" and source_id == "bound.shown_move":
                encoded = chess.encode_move(value)
                if encoded not in shown_moves:
                    shown_moves.append(encoded)
        if type(item["shown_move_bytes"]) not in (list, tuple) or tuple(shown_moves) != tuple(
            item["shown_move_bytes"]
        ):
            _fail("shown moves do not match bound owner calls")
        for value, type_id, source_id in context_values:
            if source_id == "bound.shown_move.origin" and (
                type_id != "Square"
                or not any(chess.decode_move(encoded).origin == value for encoded in shown_moves)
            ):
                _fail("shown-move origin projection mismatch")
            if source_id == "bound.shown_move.target" and (
                type_id != "Square"
                or not any(chess.decode_move(encoded).destination == value for encoded in shown_moves)
            ):
                _fail("shown-move target projection mismatch")
        if not _prompt_matches_calls(item["prompt_target"], context_values):
            _fail("semantic prompt is not bound to owner call")
        calls: list[tuple[str, str, object, object]] = []
        covered: set[str] = set()
        for call in item["owner_calls"]:
            if type(call) is not dict or set(call) != {"pattern_id", "case_id", "call_id", "argument"}:
                _fail("closed owner call")
            call_key = (call["pattern_id"], call["case_id"], call["call_id"])
            declared = pattern_calls.get(call_key)
            if declared is None or call["pattern_id"] not in pattern_ids:
                _fail("unresolved owner call")
            owner = declared["owner_id"]
            mapping = next(
                (row for row in blueprint._data["predicate_mapping"] if row["owner_id"] == owner),
                None,
            )
            if mapping is None or item["authority_kind"] not in mapping["authority_kinds"]:
                _fail("owner authority mismatch")
            actual = _owner_result(blueprint, owner, call["argument"])
            _validate_declared_call(
                declared,
                bindings[declared["input_binding_id"]],
                contracts[declared["result_contract_id"]],
                call["argument"],
                actual,
                item["authority_kind"],
                item["authority"],
                _authority_value,
                context_values,
            )
            calls.append(("/".join(call_key), owner, call["argument"], actual))
            covered.add(call["pattern_id"])
        if covered != set(pattern_ids):
            _fail("unrecomputed stratum")
        if integrated is not None and {
            owner for _identifier, owner, _argument, _actual in calls
        } != set(integrated_tasks[integrated]["predicate_ids"]):
            _fail("integrated task predicate mismatch")
        if not any(
            type(actual) is type(item["relation_result"]) and actual == item["relation_result"]
            for _identifier, _owner, _argument, actual in calls
        ):
            _fail("relation result mismatch")
        if {
            _value_key(actual) for _identifier, _owner, _argument, actual in calls
        } != {_value_key(value) for value in item["accepted_responses"]}:
            _fail("incomplete accepted semantic responses")

        identities = {_case_key(item, authority_key, tuple(calls))}
        for transform_id in blueprint._ids["transform"] - {"identity"}:
            mapped = _applicable_authority(item["authority_kind"], item["authority"], transform_id)
            if mapped is None:
                continue
            _raw, mapped_authority, mapped_key = mapped
            mapped_calls: list[tuple[str, str, object, object]] = []
            preserved = True
            for call_id, owner, argument, actual in calls:
                mapping = next(
                    row for row in blueprint._data["predicate_mapping"]
                    if row["owner_id"] == owner
                )
                if transform_id not in mapping["transform_ids"]:
                    _fail("inapplicable predicate transform")
                if (
                    owner == "chess.history_claim"
                    and type(argument) is chess.ReplayState
                    and type(_authority_value) is chess.ReplayState
                    and argument.played_plies == _authority_value.played_plies + 1
                    and len(shown_values) == 1
                ):
                    try:
                        mapped_argument = chess.apply_move(
                            mapped_authority, _map_move(shown_values[0], transform_id)
                        )
                    except chess.ChessReject:
                        preserved = False
                        break
                else:
                    mapped_argument = _mapped_value(argument, transform_id, mapped_authority)
                mapped_actual = _owner_result(blueprint, owner, mapped_argument)
                expected_actual = _mapped_result(
                    actual, mapping["result_mapping"], transform_id, mapped_authority
                )
                if type(mapped_actual) is not type(expected_actual) or mapped_actual != expected_actual:
                    preserved = False
                    break
                mapped_calls.append((call_id, owner, mapped_argument, mapped_actual))
            if not preserved:
                continue
            mapped_shown = tuple(
                chess.encode_move(_map_move(chess.decode_move(value), transform_id))
                for value in item["shown_move_bytes"]
            )
            mapped_accepted = []
            for value in item["accepted_responses"]:
                match = next(
                    (entry for entry in calls if type(entry[3]) is type(value) and entry[3] == value),
                    None,
                )
                if match is None:
                    _fail("unmapped accepted response")
                mapping = next(
                    row for row in blueprint._data["predicate_mapping"]
                    if row["owner_id"] == match[1]
                )
                mapped_accepted.append(
                    _mapped_result(value, mapping["result_mapping"], transform_id, mapped_authority)
                )
            mapped_prompt = _mapped_prompt(item["prompt_target"], transform_id)
            identities.add(
                _case_key(
                    item, mapped_key, tuple(mapped_calls), shown=mapped_shown,
                    prompt=mapped_prompt, accepted=tuple(mapped_accepted),
                )
            )
        if split in protected and semantic & identities:
            _fail("semantic case reuse")
        if split in protected:
            semantic.update(identities)

        form = item["form_id"]
        if form is not None:
            if type(form) is not str or not form:
                _fail("invalid form ID")
            if family is not None:
                forms[form].append((family, split, tuple(sorted(set(item["stratum_ids"]))), item["response_shape"], item["max_selections"]))
            elif integrated is not None:
                integrated_forms[form].append((integrated, item["response_shape"], item["max_selections"]))
                integrated_counts[(form, integrated)] += 1
            else:
                generic_forms.add(form)
        pair = item["counterfactual_pair_id"]
        if pair is not None:
            if type(pair) is not str or not pair:
                _fail("invalid counterfactual pair")
            pairs[pair].append(item)

    if len(forms) > 1:
        burdens = [Counter(values) for values in forms.values()]
        if any(value != burdens[0] for value in burdens[1:]):
            _fail("unequal per-family form burden")
    if len(integrated_forms) > 1:
        burdens = [Counter(values) for values in integrated_forms.values()]
        if any(value != burdens[0] for value in burdens[1:]):
            _fail("unequal integrated form burden")
    form_count = len(set(forms) | set(integrated_forms) | generic_forms)
    if not blueprint._data["forms"]["forms_min"] <= form_count <= blueprint._data["forms"]["forms_max"]:
        _fail("invalid form count")
    valid_pair_families: Counter[str] = Counter()
    for pair_items in pairs.values():
        if (
            len(pair_items) != 2
            or any(item["split"] != "posttest" for item in pair_items)
            or pair_items[0]["family_id"] != pair_items[1]["family_id"]
            or _value_key(pair_items[0]["observable_fingerprint"]) != _value_key(pair_items[1]["observable_fingerprint"])
            or pair_items[0]["relation_result"] == pair_items[1]["relation_result"]
            or abs(pair_items[0]["visible_index"] - pair_items[1]["visible_index"]) <= 1
        ):
            _fail("invalid counterfactual pair")
        valid_pair_families[pair_items[0]["family_id"]] += 1
    minimums = blueprint._data["assessment_minimums"]
    for (family, split), count in assessment_counts.items():
        required = {
            "pretest": minimums["pretest_items_per_claimed_family"],
            "posttest": minimums["posttest_items_per_family"],
            "delayed": minimums["delayed_items_per_essential_family"],
        }[split]
        if count < required:
            _fail("assessment family minimum")
        if split == "posttest" and valid_pair_families[family] < minimums["posttest_counterfactual_pairs_per_family"]:
            _fail("missing posttest counterfactual pair")
    if not complete:
        return

    authoring = blueprint._data["authoring_minimums"]
    for concept in blueprint._ids["concept"]:
        if (
            concept_counts[(concept, "grounding")] < authoring["grounded_rule_or_relation_per_concept"]
            or concept_counts[(concept, "contrasting")] < authoring["contrasting_worked_boundary_or_counterexample_per_concept"]
            or concept_counts[(concept, "active")] < authoring["active_packed_prediction_with_immediate_feedback_per_concept"]
            or concept_counts[(concept, "held_out")] < authoring["distinct_held_out_practice_per_concept"]
            or concept_counts[(concept, "feedback")] < concept_counts[(concept, "active")]
            or concept_counts[(concept, "passive")] < (
                concept_counts[(concept, "active")]
                * authoring["passive_trace_per_packed_practice_node"]
            )
        ):
            _fail("incomplete concept authoring inventory")
    if any(
        concept_counts[(concept, "heuristic")] == 0
        for concept in authoring["heuristic_role_required_concept_ids"]
    ):
        _fail("missing heuristic inventory")
    if any(
        counts["feedback"] < counts["active"]
        or counts["passive"] < counts["active"]
        for counts in practice_nodes.values()
    ):
        _fail("incomplete practice-node support")

    instruction_splits = set(blueprint._data["coverage"]["instruction_coverage_any_of_splits"])
    held_splits = set(blueprint._data["coverage"]["held_out_coverage_any_of_splits"])
    core3 = blueprint.family_set("C")
    required_posttest = frozenset(blueprint._data["coverage"]["posttest_required_strata"])
    for pattern_id in blueprint._ids["case_pattern"]:
        observed = stratum_splits[pattern_id]
        if not observed & instruction_splits or not observed & held_splits:
            _fail("incomplete stratum inventory")
        if (pattern_id.split(".", 1)[0] in core3 or pattern_id in required_posttest) and "posttest" not in observed:
            _fail("missing required posttest stratum")

    claimed = blueprint.family_set("E") | core3
    essential = blueprint.family_set("E")
    for family in claimed:
        if (
            assessment_counts[(family, "pretest")] < minimums["pretest_items_per_claimed_family"]
            or assessment_counts[(family, "posttest")] < minimums["posttest_items_per_family"]
            or valid_pair_families[family] < minimums["posttest_counterfactual_pairs_per_family"]
            or family in essential
            and assessment_counts[(family, "delayed")] < minimums["delayed_items_per_essential_family"]
            or len(posttest_templates[family] - instruction_templates[family])
            < minimums["assessment_only_posttest_templates_per_family"]
        ):
            _fail("incomplete family assessment inventory")
    _validate_integrated_forms(
        frozenset(forms) | frozenset(integrated_forms) | frozenset(generic_forms),
        integrated_counts,
        {row["id"]: row for row in blueprint._data["integrated_task"]},
    )


def _validate_integrated_forms(
    form_ids: frozenset[str],
    counts: dict[tuple[str, str], int] | Counter[tuple[str, str]],
    tasks: dict[str, object],
) -> None:
    if any(
        counts.get((form_id, identifier), 0) < row["minimum_per_form"]
        for form_id in form_ids
        for identifier, row in tasks.items()
    ):
        _fail("incomplete integrated task inventory")


def _lint_protocol(blueprint: Blueprint, events: object) -> tuple[bool, bool, bool]:
    if type(events) not in (list, tuple):
        _fail("invalid protocol evidence")
    _exact_int(len(events), 0, 0xFFFF, "protocol event count")
    timing = blueprint._data["roadmap_mirror"]["timing"]
    help_effects = {
        row["id"]: row["result_effect"]
        for row in blueprint._data["roadmap_mirror"]["help"]["category"]
    }
    help_effects["none"] = "none"
    used_help: set[str] = set()
    delayed_protocol_ok = True
    for event in events:
        if type(event) is not dict or set(event) != _PROTOCOL_KEYS:
            _fail("closed protocol event")
        split = event["split"]
        if split not in blueprint._data["taxonomy"]["split_ids"]:
            _fail("unknown protocol split")
        if event["feedback"] not in {"neutral", "correctness"}:
            _fail("unknown feedback")
        if split in {"pretest", "posttest", "delayed"} and event["feedback"] != "neutral":
            _fail("premature result-bearing feedback")
        if split == "practice" and event["feedback"] != "correctness":
            _fail("missing practice feedback")
        if split == "delayed":
            hours = event["delay_hours"]
            outcome = event["outcome"]
            if outcome == "valid":
                if (
                    type(hours) not in (int, float) or isinstance(hours, bool)
                    or not isfinite(hours)
                    or not timing["delayed_window_min_hours"] <= hours <= timing["delayed_window_max_hours"]
                    or event["feedback_window"] != "normal_resolved"
                    or event["delayed_effect"] != "pass"
                ):
                    _fail("invalid delayed completion")
            elif outcome == "early":
                if (
                    type(hours) not in (int, float) or isinstance(hours, bool)
                    or not isfinite(hours) or hours >= timing["delayed_window_min_hours"]
                ):
                    _fail("invalid early attempt")
            elif outcome == "late":
                if (
                    type(hours) not in (int, float) or isinstance(hours, bool)
                    or not isfinite(hours) or hours <= timing["delayed_window_max_hours"]
                ):
                    _fail("invalid late attempt")
            elif outcome == "absent":
                if hours is not None or event["attempt"] != 0 or event["feedback_window"] != "fallback_resolved":
                    _fail("invalid delayed absence")
            elif outcome == "invalid":
                if type(hours) not in (int, float) or isinstance(hours, bool) or not isfinite(hours):
                    _fail("invalid delayed timing")
            else:
                _fail("unknown delayed outcome")
            if outcome != "valid" and event["delayed_effect"] != "fixed_denominator_delayed_failure":
                _fail("invalid delayed failure effect")
            if outcome in {"early", "late", "invalid"} and event["feedback_window"] != "open":
                _fail("invalid delayed feedback window")
            expected_attempt = 0 if outcome == "absent" else 1
            if type(event["attempt"]) is not int or event["attempt"] != expected_attempt or event["retry_allowed"] is not False:
                _fail("delayed retry forbidden")
            delayed_protocol_ok &= outcome == "valid"
        elif event["delay_hours"] is not None:
            _fail("unexpected delayed timing")
        elif (
            type(event["attempt"]) is not int or event["attempt"] != 1
            or event["outcome"] != "valid" or event["retry_allowed"] is not False
            or event["delayed_effect"] != "not_applicable"
            or event["feedback_window"] not in {"open", "not_applicable"}
        ):
            _fail("invalid attempt")
        if event["help_category"] not in help_effects or event["help_effect"] != help_effects[event["help_category"]]:
            _fail("invalid help evidence")
        used_help.add(event["help_category"])
        if event["interruption"] not in {"none", "before_commit", "after_commit"} or type(event["committed"]) is not bool or type(event["state_unchanged"]) is not bool:
            _fail("invalid interruption evidence")
        if not event["state_unchanged"]:
            _fail("interruption mutated prior state")
        if event["interruption"] == "before_commit" and (event["committed"] or event["resume"] != "missing"):
            _fail("before-commit interruption semantics")
        if event["interruption"] == "after_commit" and (not event["committed"] or event["resume"] != "next"):
            _fail("after-commit interruption semantics")
        if event["interruption"] == "none" and event["resume"] != ("next" if event["committed"] else "missing"):
            _fail("uninterrupted resume semantics")
        if event["outcome"] != "absent" and (not event["committed"] or event["resume"] != "next"):
            _fail("attempt outcome was not committed")
        if event["outcome"] == "absent" and (event["committed"] or event["resume"] != "missing"):
            _fail("absent outcome was committed")
        if event["interruption"] == "before_commit" and event["outcome"] != "absent":
            _fail("interrupted item must be missing")
        if event["help_effect"] in {
            "invalidate_affected_result_bearing_run", "invalidate_affected_result_bearing_item"
        } and event["outcome"] == "valid":
            _fail("forbidden help cannot pass")
    return (
        "semantic_hint" in used_help,
        "answer_revelation" in used_help,
        delayed_protocol_ok,
    )


def _lint_cues(blueprint: Blueprint, forms: object) -> None:
    if type(forms) not in (list, tuple):
        _fail("invalid cue forms")
    _exact_int(
        len(forms), 0,
        blueprint._data["forms"]["forms_max"] * len(blueprint._ids["family"]),
        "cue form count",
    )
    audit = blueprint._data["cue_audit"]
    for form in forms:
        if type(form) is not dict or set(form) != {"family_id", "schedule", "accepted_responses"}:
            _fail("closed cue form")
        if form["family_id"] not in blueprint._ids["family"]:
            _fail("unknown cue family")
        schedule = form["schedule"]
        accepted = form["accepted_responses"]
        if type(schedule) not in (list, tuple) or type(accepted) not in (list, tuple) or not schedule or len(schedule) != len(accepted):
            _fail("invalid cue form length")
        _exact_int(
            len(schedule),
            1,
            blueprint._data["capacity"]["records_per_curriculum_family_max"]
            * len(blueprint._ids["family"]),
            "cue schedule length",
        )
        aggregate_work = _schedule_work(schedule)
        for raw_accepted in accepted:
            if type(raw_accepted) not in (list, tuple):
                _fail("invalid accepted responses")
            _exact_int(len(raw_accepted), 1, C.CONTENT_MAX_CASES_PER_NODE, "accepted response count")
            aggregate_work += len(raw_accepted)
            _exact_int(aggregate_work, 0, C.CONTENT_MAX_VECTOR_ATOMS, "cue aggregate work")
            for raw_response in raw_accepted:
                if type(raw_response) not in (list, tuple):
                    _fail("invalid accepted response")
                _exact_int(len(raw_response), 0, C.CONTENT_MAX_SELECTIONS, "accepted response length")
                aggregate_work += len(raw_response)
                _exact_int(aggregate_work, 0, C.CONTENT_MAX_VECTOR_ATOMS, "cue aggregate work")
        normalized: list[frozenset[tuple[int, ...]]] = []
        for raw_item, raw_accepted in zip(schedule, accepted, strict=True):
            options, cap, shape, repeat, _prior = _options(raw_item)
            ordinals = frozenset(option["ordinal"] for option in options)
            if type(raw_accepted) not in (list, tuple) or not raw_accepted:
                _fail("missing accepted response")
            responses: set[tuple[int, ...]] = set()
            for raw_response in raw_accepted:
                if type(raw_response) not in (list, tuple):
                    _fail("invalid accepted response")
                response = tuple(raw_response)
                if not _mechanical(response, ordinals, cap, shape, repeat):
                    _fail("nonmechanical accepted response")
                responses.add(response)
            normalized.append(frozenset(responses))
        for strategy in blueprint._ids["cue_strategy"]:
            responses = evaluate_cue_strategy(blueprint, strategy, schedule)
            correct = sum(response in normalized[index] for index, response in enumerate(responses))
            errors = len(responses) - correct
            if (
                errors < audit["strategy_errors_per_family_min"]
                or correct * audit["strategy_max_correct_denominator"]
                > len(responses) * audit["strategy_max_correct_numerator"]
            ):
                _fail("cue strategy leaks answers")


@_fail_closed
def lint_synthetic(blueprint: Blueprint, cases: object) -> None:
    """Validate small synthetic composition, leakage, and protocol evidence."""
    blueprint = _blueprint(blueprint)
    if type(cases) is not dict or set(cases) != {"items", "protocol", "cue_forms"}:
        _fail("closed synthetic evidence")
    _lint_items(blueprint, cases["items"], complete=True)
    _lint_protocol(blueprint, cases["protocol"])
    _lint_cues(blueprint, cases["cue_forms"])
    posttest_families = {
        item["family_id"] for item in cases["items"]
        if item["split"] == "posttest" and item["family_id"] is not None
    }
    cue_families = {form["family_id"] for form in cases["cue_forms"]}
    if cue_families != posttest_families:
        _fail("incomplete cue-family inventory")
