"""Candidate-neutral M2 semantic-capacity derivation.

This module turns authority-created slice and curriculum values into the exact
logical work that every P4 transport policy must charge.  It deliberately has
no candidate codec, geometry, placement, damage, or selection dependency.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
from typing import NoReturn

from . import constants as C
from . import content, curriculum, m2_slice


__all__ = (
    "AuthoredRecordDemand",
    "CapacityBucket",
    "CapacityConcept",
    "CapacityEnvelope",
    "CapacityError",
    "CapacityFamily",
    "CapacityInputs",
    "CapacityIntegratedTask",
    "CapacityPolicyInput",
    "CapacitySection",
    "CapacitySlot",
    "LoadProbeFill",
    "PrototypeMaximum",
    "RealSliceSection",
    "ReservePlan",
    "RoleBundlePolicy",
    "SectionCharge",
    "SlotAssignment",
    "TierFrameInput",
    "assign_authored_records",
    "derive_capacity_envelope",
    "derive_capacity_inputs",
    "partition_probe_payload",
    "partition_residual_cells",
    "probe_fill_bytes",
    "reserve_requirement",
    "solve_reserve_fixed_point",
    "section_charge",
)


_U64_MAX = (1 << 64) - 1
_KIND_COUNT = 14
_MAX_SLOTS_PER_KIND = C.CONTENT_MAX_RECORDS_PER_NON_ROOT_KIND
_MAX_TOTAL_SLOTS = _KIND_COUNT * _MAX_SLOTS_PER_KIND
_MAX_SECTION_BYTES = 1_048_576
_COMMON_BLOCK_BYTES = 191
_FRAGMENT_PAYLOAD_BYTES = 157
_FILL_DOMAIN = b"GB-M2-FILL-v0\0"
_TIERS = ("core0", "core1", "core2", "core3", "core4")
_REPLICATED = "replicated-core0-2"
_NONREPLICATED = "nonreplicated-core3-4"
_ROLE_IDS = (
    "grounded_rule",
    "contrasting_worked",
    "active_prediction_feedback",
    "distinct_held_out",
    "passive_trace",
    "heuristic",
    "assessment_item",
    "integrated_item",
)
_CONCEPT_ROLE_IDS = _ROLE_IDS[:5]
_HEURISTIC_ROLE_ID = _ROLE_IDS[5]
_ASSESSMENT_ROLE_ID = _ROLE_IDS[6]
_INTEGRATED_ROLE_ID = _ROLE_IDS[7]


class CapacityError(ValueError):
    """One stable fail-closed capacity derivation failure."""

    __slots__ = ("_reason", "_path")

    def __init__(self, reason: str, path: str):
        if type(reason) is not str or type(path) is not str:
            raise TypeError("capacity error fields must be strings")
        self._reason = reason
        self._path = path
        super().__init__(reason, path)

    @property
    def reason(self) -> str:
        return self._reason

    @property
    def path(self) -> str:
        return self._path

    def __setattr__(self, name: str, value: object) -> None:
        if name in CapacityError.__slots__ and hasattr(self, name):
            raise AttributeError(f"{name} is read-only")
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if name in CapacityError.__slots__:
            raise AttributeError(f"{name} is read-only")
        super().__delattr__(name)


@dataclass(frozen=True, slots=True)
class PrototypeMaximum:
    kind: int
    prototype_id: str
    source_record_id: int
    frame_length: int


@dataclass(frozen=True, slots=True)
class CapacityConcept:
    concept_id: str
    tier: str
    heuristic_required: bool


@dataclass(frozen=True, slots=True)
class CapacityFamily:
    family_id: str
    tier: str
    delayed_required: bool


@dataclass(frozen=True, slots=True)
class CapacityIntegratedTask:
    task_id: str
    minimum_per_form: int


@dataclass(frozen=True, slots=True)
class RealSliceSection:
    section_id: int
    closure: str
    payload_length: int
    record_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class TierFrameInput:
    section_id: int
    closure: str
    logical_payload_length: int
    assembled_stream_length: int
    assembled_record_count: int
    body_section_ids: tuple[int, ...]
    root_record_frame_length: int


@dataclass(frozen=True, slots=True)
class CapacityInputs:
    slice_semantic_sha256: str
    prototypes: tuple[PrototypeMaximum, ...]
    concepts: tuple[CapacityConcept, ...]
    families: tuple[CapacityFamily, ...]
    integrated_tasks: tuple[CapacityIntegratedTask, ...]
    real_content_sections: tuple[RealSliceSection, ...]
    tier_frames: tuple[TierFrameInput, ...]


@dataclass(frozen=True, slots=True)
class RoleBundlePolicy:
    role_id: str
    record_kind_multiplicities: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CapacityPolicyInput:
    role_bundles: tuple[RoleBundlePolicy, ...]
    maximum_content_body_payload: int
    maximum_probe_payload: int
    generic_support_fraction_numerator: int
    generic_support_fraction_denominator: int
    generic_support_minimum_cycles: int


@dataclass(frozen=True, slots=True)
class CapacitySlot:
    bucket_id: str
    slot_ordinal: int
    role_ordinal: int
    role_id: str
    kind: int
    prototype_id: str
    frame_length: int


@dataclass(frozen=True, slots=True)
class CapacitySection:
    bucket_id: str
    section_ordinal: int
    tier: str
    protection_class: str
    first_slot_ordinal: int
    slot_count: int
    payload_length: int


@dataclass(frozen=True, slots=True)
class CapacityBucket:
    bucket_id: str
    tier: str
    protection_class: str
    slots: tuple[CapacitySlot, ...]
    sections: tuple[CapacitySection, ...]
    payload_length: int


@dataclass(frozen=True, slots=True)
class CapacityEnvelope:
    slice_semantic_sha256: str
    prototypes: tuple[PrototypeMaximum, ...]
    role_bundles: tuple[RoleBundlePolicy, ...]
    buckets: tuple[CapacityBucket, ...]
    concept_minima_bytes: int
    assessment_bytes: int
    integrated_bytes: int
    generic_shared_support_bytes: int
    authoring_payload_bytes: int
    slot_count_by_kind: tuple[int, ...]
    maximum_content_body_payload: int
    maximum_probe_payload: int


@dataclass(frozen=True, slots=True)
class SectionCharge:
    logical_payload_length: int
    dependency_count: int
    check_id: int
    semantic_copy_count: int
    envelope_length: int
    fragments_per_copy: int
    common_blocks: int
    common_block_bytes: int


@dataclass(frozen=True, slots=True)
class LoadProbeFill:
    whole_protected_units: int
    load_probe_cells: int
    fixed_pad_cells: int


@dataclass(frozen=True, slots=True)
class ReservePlan:
    content_capacity_before_reserve: int
    reserve_payload_length: int
    reserve_section_payloads: tuple[int, ...]
    inventory_payload_length: int


@dataclass(frozen=True, slots=True)
class AuthoredRecordDemand:
    record_id: int
    bucket_id: str
    kind: int
    frame_length: int


@dataclass(frozen=True, slots=True)
class SlotAssignment:
    record_id: int
    bucket_id: str
    slot_ordinal: int
    kind: int
    frame_length: int


def _fail(reason: str, path: str) -> NoReturn:
    raise CapacityError(reason, path)


def _u64(value: object, path: str) -> int:
    if type(value) is not int or not 0 <= value <= _U64_MAX:
        _fail("u64", path)
    return value


def _add(left: int, right: int, path: str) -> int:
    left = _u64(left, path)
    right = _u64(right, path)
    if right > _U64_MAX - left:
        _fail("overflow", path)
    return left + right


def _mul(left: int, right: int, path: str) -> int:
    left = _u64(left, path)
    right = _u64(right, path)
    if left and right > _U64_MAX // left:
        _fail("overflow", path)
    return left * right


def _ceil_div(value: int, divisor: int, path: str) -> int:
    value = _u64(value, path)
    if type(divisor) is not int or divisor <= 0:
        _fail("bad_value", path)
    return value // divisor + (value % divisor != 0)


def _frames(stream: bytes, path: str) -> dict[int, bytes]:
    if type(stream) is not bytes or len(stream) < 4:
        _fail("invalid_slice", path)
    count = int.from_bytes(stream[2:4], "big")
    offset = 4
    frames: dict[int, bytes] = {}
    for ordinal in range(count):
        start = offset
        if len(stream) - offset < 8:
            _fail("invalid_slice", f"{path}[{ordinal}]")
        record_id = int.from_bytes(stream[offset : offset + 2], "big")
        payload_length = int.from_bytes(stream[offset + 4 : offset + 8], "big")
        frame_length = _add(8, payload_length, f"{path}[{ordinal}]")
        if frame_length > len(stream) - offset:
            _fail("invalid_slice", f"{path}[{ordinal}]")
        offset += frame_length
        if record_id in frames:
            _fail("invalid_slice", f"{path}[{ordinal}]")
        frames[record_id] = stream[start:offset]
    if offset != len(stream):
        _fail("invalid_slice", path)
    return frames


def _protection(tier: str, path: str) -> str:
    if tier not in _TIERS:
        _fail("bad_tier", path)
    return _REPLICATED if tier in _TIERS[:3] else _NONREPLICATED


def derive_capacity_inputs(
    compiled: m2_slice.SliceCompilation,
    blueprint: curriculum.Blueprint,
) -> CapacityInputs:
    """Project exact candidate-neutral capacity inputs from checked owners."""

    if type(compiled) is not m2_slice.SliceCompilation:
        raise TypeError("expected SliceCompilation")
    if type(blueprint) is not curriculum.Blueprint:
        raise TypeError("expected Blueprint")

    try:
        accepted = content.stream_validation(compiled.content_bytes)
        required_accepted = content.stream_validation(compiled.required_content_bytes)
    except content.ContentReject:
        _fail("invalid_slice", "slice.content_bytes")
    if (
        content.projection_view(accepted) != compiled.projection
        or content.projection_view(required_accepted) != compiled.required_projection
        or hashlib.sha256(compiled.content_bytes).hexdigest()
        != compiled.content_sha256
        or hashlib.sha256(compiled.required_content_bytes).hexdigest()
        != compiled.required_content_sha256
    ):
        _fail("invalid_slice", "slice.content_bytes")
    all_frames = _frames(compiled.content_bytes, "slice.content_frames")
    required_frames = _frames(
        compiled.required_content_bytes, "slice.required_content_frames"
    )

    prototypes = tuple(
        PrototypeMaximum(
            item.kind,
            item.prototype_id,
            item.source_record_id,
            item.frame_length,
        )
        for item in compiled.capacity_prototypes
    )
    if (
        tuple(item.kind for item in prototypes) != tuple(range(1, _KIND_COUNT + 1))
        or len({item.prototype_id for item in prototypes}) != _KIND_COUNT
    ):
        _fail("prototype_coverage", "slice.capacity_prototypes")
    for index, item in enumerate(prototypes):
        try:
            actual = required_frames[item.source_record_id]
        except KeyError:
            _fail("prototype_reference", f"slice.capacity_prototypes[{index}]")
        if item.frame_length != len(actual) or item.frame_length <= 0:
            _fail("prototype_length", f"slice.capacity_prototypes[{index}]")

    real_sections = []
    assigned: list[int] = []
    for index, assignment in enumerate(compiled.atomic_assignments):
        try:
            length = sum(len(all_frames[value]) for value in assignment.record_ids)
        except KeyError:
            _fail("section_reference", f"slice.atomic_assignments[{index}]")
        if not assignment.record_ids or length > _MAX_SECTION_BYTES:
            _fail("section_length", f"slice.atomic_assignments[{index}]")
        assigned.extend(assignment.record_ids)
        real_sections.append(
            RealSliceSection(
                assignment.section_id,
                assignment.closure,
                length,
                assignment.record_ids,
            )
        )
    if tuple(assigned) != tuple(range(1, len(all_frames))):
        _fail("section_coverage", "slice.atomic_assignments")

    tier_frames = []
    for index, root in enumerate(compiled.tier_roots):
        stream = (
            compiled.required_content_bytes
            if root.closure == "m2_required"
            else compiled.content_bytes
        )
        frames = required_frames if root.closure == "m2_required" else all_frames
        body_ids = tuple(
            item.section_id
            for item in compiled.atomic_assignments
            if root.closure != "m2_required" or item.closure == "m2_required"
        )
        try:
            root_length = len(frames[root.record_id])
        except KeyError:
            _fail("tier_reference", f"slice.tier_roots[{index}]")
        tier_frames.append(
            TierFrameInput(
                root.section_id,
                root.closure,
                22 + 4 * len(body_ids) + root_length,
                len(stream),
                len(frames),
                body_ids,
                root_length,
            )
        )
    if tuple((item.section_id, item.closure) for item in tier_frames) != (
        (2, "m2_required"),
        (3, "m2_all"),
    ):
        _fail("tier_coverage", "slice.tier_roots")

    data = blueprint._data
    authoring = data["authoring_minimums"]
    if (
        authoring["applies_to"] != "every_registered_concept"
        or authoring["grounded_rule_or_relation_per_concept"] != 1
        or authoring[
            "contrasting_worked_boundary_or_counterexample_per_concept"
        ]
        != 1
        or authoring[
            "active_packed_prediction_with_immediate_feedback_per_concept"
        ]
        != 1
        or authoring["distinct_held_out_practice_per_concept"] != 1
        or authoring["passive_trace_per_packed_practice_node"] != 1
    ):
        _fail("curriculum_formula", "curriculum.authoring_minimums")
    heuristic_ids = frozenset(authoring["heuristic_role_required_concept_ids"])
    concepts = tuple(
        CapacityConcept(
            row["id"],
            row["tier"],
            row["id"] in heuristic_ids,
        )
        for row in data["concept"]
    )
    if not concepts or any(item.tier not in _TIERS for item in concepts):
        _fail("curriculum_formula", "curriculum.concept")
    if heuristic_ids != frozenset(
        item.concept_id for item in concepts if item.heuristic_required
    ):
        _fail("curriculum_formula", "curriculum.authoring_minimums")

    assessment = data["assessment_minimums"]
    if (
        assessment["pretest_items_per_claimed_family"] != 2
        or assessment["posttest_items_per_family"] != 2
        or assessment["delayed_items_per_essential_family"] != 1
        or assessment["posttest_counterfactual_pairs_per_family"] != 1
        or assessment["assessment_only_posttest_templates_per_family"] != 1
        or assessment["forced_third_posttest_item"] is not False
    ):
        _fail("curriculum_formula", "curriculum.assessment_minimums")
    delayed = blueprint.family_set("E")
    families = tuple(
        CapacityFamily(row["id"], row["tier"], row["id"] in delayed)
        for row in data["family"]
    )
    if (
        not families
        or any(item.tier not in _TIERS for item in families)
        or delayed
        != frozenset(item.family_id for item in families if item.delayed_required)
    ):
        _fail("curriculum_formula", "curriculum.family")

    integrated = tuple(
        CapacityIntegratedTask(row["id"], row["minimum_per_form"])
        for row in data["integrated_task"]
    )
    if (
        tuple(item.task_id for item in integrated)
        != tuple(assessment["integrated_task_ids"])
        or any(type(item.minimum_per_form) is not int or item.minimum_per_form <= 0 for item in integrated)
    ):
        _fail("curriculum_formula", "curriculum.integrated_task")

    return CapacityInputs(
        compiled.content_sha256,
        prototypes,
        concepts,
        families,
        integrated,
        tuple(real_sections),
        tuple(tier_frames),
    )


def _policy(
    policy: CapacityPolicyInput,
) -> tuple[dict[str, RoleBundlePolicy], int, int, int, int, int]:
    if type(policy) is not CapacityPolicyInput:
        raise TypeError("expected CapacityPolicyInput")
    if (
        type(policy.role_bundles) is not tuple
        or any(type(item) is not RoleBundlePolicy for item in policy.role_bundles)
        or tuple(item.role_id for item in policy.role_bundles) != _ROLE_IDS
    ):
        _fail("role_bundle_order", "policy.role_bundles")
    output = {}
    for index, bundle in enumerate(policy.role_bundles):
        path = f"policy.role_bundles[{index}]"
        values = bundle.record_kind_multiplicities
        if type(values) is not tuple or len(values) != _KIND_COUNT:
            _fail("role_bundle_shape", path)
        total = 0
        for kind, value in enumerate(values, 1):
            if type(value) is not int or not 0 <= value <= _MAX_SLOTS_PER_KIND:
                _fail("role_bundle_multiplicity", f"{path}.kind[{kind}]")
            total = _add(total, value, path)
        if total == 0:
            _fail("empty_required_role", path)
        output[bundle.role_id] = bundle
    maximum = policy.maximum_content_body_payload
    probe = policy.maximum_probe_payload
    if type(maximum) is not int or not 1 <= maximum <= _MAX_SECTION_BYTES:
        _fail("section_payload_maximum", "policy.maximum_content_body_payload")
    if type(probe) is not int or not 1 <= probe <= _MAX_SECTION_BYTES:
        _fail("section_payload_maximum", "policy.maximum_probe_payload")
    numerator = policy.generic_support_fraction_numerator
    denominator = policy.generic_support_fraction_denominator
    minimum_cycles = policy.generic_support_minimum_cycles
    if type(numerator) is not int or numerator <= 0:
        _fail("bad_value", "policy.generic_support_fraction_numerator")
    if type(denominator) is not int or denominator <= 0:
        _fail("bad_value", "policy.generic_support_fraction_denominator")
    if numerator > denominator:
        _fail("bad_value", "policy.generic_support_fraction")
    if type(minimum_cycles) is not int or not 1 <= minimum_cycles <= _MAX_TOTAL_SLOTS:
        _fail("bad_value", "policy.generic_support_minimum_cycles")
    return output, maximum, probe, numerator, denominator, minimum_cycles


def _bundle_slots(
    bucket_id: str,
    role_ordinal: int,
    role_id: str,
    bundles: dict[str, RoleBundlePolicy],
    prototypes: tuple[PrototypeMaximum, ...],
    start_ordinal: int,
) -> tuple[CapacitySlot, ...]:
    output = []
    bundle = bundles[role_id]
    bundle_count = sum(bundle.record_kind_multiplicities)
    if start_ordinal > _MAX_TOTAL_SLOTS - bundle_count:
        _fail("slot_limit", bucket_id)
    ordinal = start_ordinal
    for prototype, multiplicity in zip(
        prototypes, bundle.record_kind_multiplicities, strict=True
    ):
        for _ in range(multiplicity):
            output.append(
                CapacitySlot(
                    bucket_id,
                    ordinal,
                    role_ordinal,
                    role_id,
                    prototype.kind,
                    prototype.prototype_id,
                    prototype.frame_length,
                )
            )
            ordinal += 1
    return tuple(output)


def _preflight_role_occurrences(
    role_ids: tuple[str, ...],
    bundles: dict[str, RoleBundlePolicy],
    counts: Counter[int],
    path: str,
) -> None:
    """Bound slot growth before constructing any per-slot objects."""

    additions: Counter[int] = Counter()
    for role_id in role_ids:
        for kind, value in enumerate(
            bundles[role_id].record_kind_multiplicities, 1
        ):
            additions[kind] = _add(additions[kind], value, path)
    for kind in range(1, _KIND_COUNT + 1):
        combined = _add(counts[kind], additions[kind], path)
        if combined > _MAX_SLOTS_PER_KIND:
            _fail("per_kind_slot_limit", f"{path}.kind[{kind}]")
    if sum(counts.values()) > _MAX_TOTAL_SLOTS - sum(additions.values()):
        _fail("slot_limit", path)
    counts.update(additions)


def _pack_bucket(
    bucket_id: str,
    tier: str,
    protection_class: str,
    slots: tuple[CapacitySlot, ...],
    maximum: int,
) -> CapacityBucket:
    if not slots:
        _fail("empty_bucket", bucket_id)
    sections = []
    first = 0
    count = 0
    length = 0
    total = 0
    for slot in slots:
        if slot.frame_length > maximum:
            _fail("slot_too_large", f"{bucket_id}.slots[{slot.slot_ordinal}]")
        if count and slot.frame_length > maximum - length:
            sections.append(
                CapacitySection(
                    bucket_id,
                    len(sections),
                    tier,
                    protection_class,
                    first,
                    count,
                    length,
                )
            )
            first = slot.slot_ordinal
            count = 0
            length = 0
        count += 1
        length = _add(length, slot.frame_length, bucket_id)
        total = _add(total, slot.frame_length, bucket_id)
    sections.append(
        CapacitySection(
            bucket_id,
            len(sections),
            tier,
            protection_class,
            first,
            count,
            length,
        )
    )
    return CapacityBucket(
        bucket_id,
        tier,
        protection_class,
        slots,
        tuple(sections),
        total,
    )


def derive_capacity_envelope(
    inputs: CapacityInputs,
    policy: CapacityPolicyInput,
) -> CapacityEnvelope:
    """Expand frozen P4 role counts into exact ordered P3 capacity slots."""

    if type(inputs) is not CapacityInputs:
        raise TypeError("expected CapacityInputs")
    if (
        type(inputs.slice_semantic_sha256) is not str
        or len(inputs.slice_semantic_sha256) != 64
        or any(
            character not in "0123456789abcdef"
            for character in inputs.slice_semantic_sha256
        )
    ):
        _fail("digest", "inputs.slice_semantic_sha256")
    (
        bundles,
        maximum,
        probe,
        generic_numerator,
        generic_denominator,
        minimum_cycles,
    ) = _policy(policy)
    prototypes = inputs.prototypes
    if (
        type(prototypes) is not tuple
        or any(type(item) is not PrototypeMaximum for item in prototypes)
        or tuple(item.kind for item in prototypes)
        != tuple(range(1, _KIND_COUNT + 1))
        or len({item.prototype_id for item in prototypes}) != _KIND_COUNT
        or len({item.source_record_id for item in prototypes}) != _KIND_COUNT
    ):
        _fail("prototype_coverage", "inputs.prototypes")
    if any(
        type(item.frame_length) is not int or not 1 <= item.frame_length <= maximum
        for item in prototypes
    ):
        _fail("prototype_length", "inputs.prototypes")

    def identifiers(rows: tuple, row_type: type, field: str, path: str) -> None:
        if type(rows) is not tuple or any(type(item) is not row_type for item in rows):
            _fail("input_shape", path)
        values = tuple(getattr(item, field) for item in rows)
        if (
            len(values) != len(set(values))
            or any(
                type(value) is not str
                or not value
                or not value.isascii()
                or "/" in value
                for value in values
            )
        ):
            _fail("input_identifier", path)

    identifiers(inputs.concepts, CapacityConcept, "concept_id", "inputs.concepts")
    identifiers(inputs.families, CapacityFamily, "family_id", "inputs.families")
    identifiers(
        inputs.integrated_tasks,
        CapacityIntegratedTask,
        "task_id",
        "inputs.integrated_tasks",
    )
    if any(
        item.tier not in _TIERS or type(item.heuristic_required) is not bool
        for item in inputs.concepts
    ):
        _fail("input_shape", "inputs.concepts")
    if any(
        item.tier not in _TIERS or type(item.delayed_required) is not bool
        for item in inputs.families
    ):
        _fail("input_shape", "inputs.families")
    if any(
        type(item.minimum_per_form) is not int
        or not 1 <= item.minimum_per_form <= _MAX_SLOTS_PER_KIND
        for item in inputs.integrated_tasks
    ):
        _fail("input_shape", "inputs.integrated_tasks")

    buckets: list[CapacityBucket] = []
    concept_bytes = 0
    assessment_bytes = 0
    integrated_bytes = 0
    planned_counts: Counter[int] = Counter()

    for concept in inputs.concepts:
        bucket_id = f"concept_minima/{concept.concept_id}"
        role_ids = (*_CONCEPT_ROLE_IDS,)
        if concept.heuristic_required:
            role_ids = (*role_ids, _HEURISTIC_ROLE_ID)
        _preflight_role_occurrences(role_ids, bundles, planned_counts, bucket_id)
        slots: list[CapacitySlot] = []
        for role_ordinal, role_id in enumerate(role_ids):
            slots.extend(
                _bundle_slots(
                    bucket_id,
                    role_ordinal,
                    role_id,
                    bundles,
                    prototypes,
                    len(slots),
                )
            )
        bucket = _pack_bucket(
            bucket_id,
            concept.tier,
            _protection(concept.tier, bucket_id),
            tuple(slots),
            maximum,
        )
        concept_bytes = _add(concept_bytes, bucket.payload_length, "concept_minima")
        buckets.append(bucket)

    for family in inputs.families:
        bucket_id = f"assessment/{family.family_id}"
        occurrences = 3 * (2 + 2) + (3 if family.delayed_required else 0)
        _preflight_role_occurrences(
            (_ASSESSMENT_ROLE_ID,) * occurrences,
            bundles,
            planned_counts,
            bucket_id,
        )
        slots = []
        for role_ordinal in range(occurrences):
            slots.extend(
                _bundle_slots(
                    bucket_id,
                    role_ordinal,
                    _ASSESSMENT_ROLE_ID,
                    bundles,
                    prototypes,
                    len(slots),
                )
            )
        bucket = _pack_bucket(
            bucket_id,
            family.tier,
            _protection(family.tier, bucket_id),
            tuple(slots),
            maximum,
        )
        assessment_bytes = _add(assessment_bytes, bucket.payload_length, "assessment")
        buckets.append(bucket)

    for task in inputs.integrated_tasks:
        bucket_id = f"integrated/{task.task_id}"
        occurrences = _mul(3, task.minimum_per_form, bucket_id)
        _preflight_role_occurrences(
            (_INTEGRATED_ROLE_ID,) * occurrences,
            bundles,
            planned_counts,
            bucket_id,
        )
        slots = []
        for role_ordinal in range(occurrences):
            slots.extend(
                _bundle_slots(
                    bucket_id,
                    role_ordinal,
                    _INTEGRATED_ROLE_ID,
                    bundles,
                    prototypes,
                    len(slots),
                )
            )
        bucket = _pack_bucket(
            bucket_id,
            "core3",
            _NONREPLICATED,
            tuple(slots),
            maximum,
        )
        integrated_bytes = _add(integrated_bytes, bucket.payload_length, "integrated")
        buckets.append(bucket)

    base_total = _add(
        _add(concept_bytes, assessment_bytes, "generic_shared_support.target"),
        integrated_bytes,
        "generic_shared_support.target",
    )
    role_sizes = []
    for role_id in _ROLE_IDS:
        size = 0
        for prototype, multiplicity in zip(
            prototypes,
            bundles[role_id].record_kind_multiplicities,
            strict=True,
        ):
            size = _add(
                size,
                _mul(multiplicity, prototype.frame_length, role_id),
                role_id,
            )
        role_sizes.append((size, role_id))
    largest_size = max(value[0] for value in role_sizes)
    largest_role = min(
        role_id for size, role_id in role_sizes if size == largest_size
    )
    bucket_id = "generic_shared_support"
    one_cycle = [
        CapacitySlot(
            bucket_id,
            index,
            0,
            "all_content_kinds",
            prototype.kind,
            prototype.prototype_id,
            prototype.frame_length,
        )
        for index, prototype in enumerate(prototypes)
    ]
    one_cycle.extend(
        _bundle_slots(
            bucket_id,
            0,
            largest_role,
            bundles,
            prototypes,
            len(one_cycle),
        )
    )
    cycle_bytes = sum(item.frame_length for item in one_cycle)
    if cycle_bytes <= 0:
        _fail("empty_cycle", bucket_id)
    target = max(
        _mul(minimum_cycles, cycle_bytes, f"{bucket_id}.target"),
        _ceil_div(
            _mul(base_total, generic_numerator, f"{bucket_id}.target"),
            generic_denominator,
            f"{bucket_id}.target",
        ),
    )
    cycle_count = max(
        minimum_cycles,
        _ceil_div(target, cycle_bytes, f"{bucket_id}.cycles"),
    )
    generic_role_ids = []
    # Each cycle starts with one slot of every kind, modeled here as a
    # temporary exact multiplicity vector, and then adds the largest bundle.
    all_kinds_id = "__all_content_kinds__"
    bundles[all_kinds_id] = RoleBundlePolicy(all_kinds_id, (1,) * _KIND_COUNT)
    for _ in range(cycle_count):
        generic_role_ids.extend((all_kinds_id, largest_role))
    _preflight_role_occurrences(
        tuple(generic_role_ids), bundles, planned_counts, bucket_id
    )
    del bundles[all_kinds_id]
    generic_slots: list[CapacitySlot] = []
    for cycle in range(cycle_count):
        for slot in one_cycle:
            generic_slots.append(
                CapacitySlot(
                    bucket_id,
                    len(generic_slots),
                    cycle,
                    slot.role_id,
                    slot.kind,
                    slot.prototype_id,
                    slot.frame_length,
                )
            )
    generic = _pack_bucket(
        bucket_id,
        "core0",
        _REPLICATED,
        tuple(generic_slots),
        maximum,
    )
    buckets.append(generic)

    counts = Counter(
        slot.kind for bucket in buckets for slot in bucket.slots
    )
    if counts != planned_counts:
        _fail("slot_count_mismatch", "buckets")
    if any(counts[kind] > _MAX_SLOTS_PER_KIND for kind in range(1, 15)):
        _fail("per_kind_slot_limit", "buckets")
    total_slots = sum(counts.values())
    if total_slots > _MAX_TOTAL_SLOTS:
        _fail("slot_limit", "buckets")
    authoring_bytes = _add(base_total, generic.payload_length, "authoring_payload")
    if authoring_bytes > C.CONTENT_MAX_STREAM_BYTES:
        _fail("authoring_byte_limit", "authoring_payload")

    return CapacityEnvelope(
        inputs.slice_semantic_sha256,
        prototypes,
        policy.role_bundles,
        tuple(buckets),
        concept_bytes,
        assessment_bytes,
        integrated_bytes,
        generic.payload_length,
        authoring_bytes,
        tuple(counts[kind] for kind in range(1, 15)),
        maximum,
        probe,
    )


def reserve_requirement(real_payload_bytes: int, authoring_payload_bytes: int) -> int:
    """Return exact R=max((C+18)//19, 382) without floating point."""

    total = _add(real_payload_bytes, authoring_payload_bytes, "reserve.C")
    numerator = _add(total, 18, "reserve.ceil")
    return max(numerator // 19, 2 * _COMMON_BLOCK_BYTES)


def partition_probe_payload(payload_length: int, maximum_payload: int) -> tuple[int, ...]:
    """Partition a probe into the fewest nonempty fixed-size sections."""

    payload_length = _u64(payload_length, "probe.payload_length")
    if type(maximum_payload) is not int or not 1 <= maximum_payload <= _MAX_SECTION_BYTES:
        _fail("section_payload_maximum", "probe.maximum_payload")
    if payload_length == 0:
        return ()
    full, remainder = divmod(payload_length, maximum_payload)
    if full > _MAX_TOTAL_SLOTS:
        _fail("section_count_limit", "probe.payload_length")
    values = (maximum_payload,) * full
    return values if remainder == 0 else (*values, remainder)


def solve_reserve_fixed_point(
    real_payload_bytes_excluding_inventory: int,
    authoring_payload_bytes: int,
    inventory_payload_without_reserve_entries: int,
    reserve_inventory_entry_length: int,
    maximum_probe_payload: int,
) -> ReservePlan:
    """Solve the bounded inventory/reserve-section-count fixed point.

    The caller supplies the exact already-frozen inventory entry charge; this
    function owns only checked monotone arithmetic, not dependency policy.
    """

    real = _u64(
        real_payload_bytes_excluding_inventory,
        "reserve_fixed.real_payload_bytes_excluding_inventory",
    )
    authoring = _u64(authoring_payload_bytes, "reserve_fixed.authoring_payload_bytes")
    base_inventory = _u64(
        inventory_payload_without_reserve_entries,
        "reserve_fixed.inventory_payload_without_reserve_entries",
    )
    entry = _u64(
        reserve_inventory_entry_length,
        "reserve_fixed.reserve_inventory_entry_length",
    )
    if entry == 0:
        _fail("bad_value", "reserve_fixed.reserve_inventory_entry_length")
    section_count = 0
    for _ in range(4097):
        inventory = _add(
            base_inventory,
            _mul(section_count, entry, "reserve_fixed.inventory"),
            "reserve_fixed.inventory",
        )
        before_reserve = _add(_add(real, inventory, "reserve_fixed.C"), authoring, "reserve_fixed.C")
        reserve = reserve_requirement(before_reserve, 0)
        payloads = partition_probe_payload(reserve, maximum_probe_payload)
        next_count = len(payloads)
        if next_count == section_count:
            return ReservePlan(before_reserve, reserve, payloads, inventory)
        if next_count < section_count:
            _fail("nonmonotone", "reserve_fixed.section_count")
        section_count = next_count
    _fail("section_count_limit", "reserve_fixed.section_count")


def section_charge(
    logical_payload_length: int,
    dependency_count: int,
    check_id: int,
    semantic_copy_count: int,
) -> SectionCharge:
    """Charge common-envelope, fragmentation, and semantic-copy overhead."""

    payload = _u64(logical_payload_length, "section.payload_length")
    if payload > _MAX_SECTION_BYTES:
        _fail("section_payload_maximum", "section.payload_length")
    if type(dependency_count) is not int or not 0 <= dependency_count <= 4095:
        _fail("dependency_count", "section.dependencies")
    if check_id not in (1, 2):
        _fail("check_id", "section.check_id")
    if type(semantic_copy_count) is not int or semantic_copy_count not in (1, 2, 3):
        _fail("copy_count", "section.semantic_copy_count")
    envelope = _add(
        _add(18, _mul(4, dependency_count, "section.envelope"), "section.envelope"),
        payload,
        "section.envelope",
    )
    envelope = _add(envelope, 4 if check_id == 1 else 8, "section.envelope")
    if envelope > _MAX_SECTION_BYTES:
        _fail("section_envelope_limit", "section.envelope")
    fragments = _ceil_div(envelope, _FRAGMENT_PAYLOAD_BYTES, "section.fragments")
    blocks = _mul(fragments, semantic_copy_count, "section.common_blocks")
    common_bytes = _mul(blocks, _COMMON_BLOCK_BYTES, "section.common_block_bytes")
    return SectionCharge(
        payload,
        dependency_count,
        check_id,
        semantic_copy_count,
        envelope,
        fragments,
        blocks,
        common_bytes,
    )


def partition_residual_cells(
    residual_cells: int, protected_unit_cells: int
) -> LoadProbeFill:
    """Assign all residual cells to whole load-probe units or fixed pad."""

    residual = _u64(residual_cells, "load_probe.residual_cells")
    unit = _u64(protected_unit_cells, "load_probe.protected_unit_cells")
    if unit == 0:
        _fail("bad_value", "load_probe.protected_unit_cells")
    whole, pad = divmod(residual, unit)
    return LoadProbeFill(whole, _mul(whole, unit, "load_probe.cells"), pad)


def probe_fill_bytes(slice_semantic_sha256: str, length: int) -> bytes:
    """Generate the exact bounded M2 probe/fixed-pad byte stream prefix."""

    if (
        type(slice_semantic_sha256) is not str
        or len(slice_semantic_sha256) != 64
        or any(character not in "0123456789abcdef" for character in slice_semantic_sha256)
    ):
        _fail("digest", "fill.slice_semantic_sha256")
    if type(length) is not int or not 0 <= length <= _MAX_SECTION_BYTES:
        _fail("fill_length", "fill.length")
    digest = bytes.fromhex(slice_semantic_sha256)
    output = bytearray()
    counter = 0
    while len(output) < length:
        if counter > _U64_MAX:
            _fail("counter_overflow", "fill.counter")
        output.extend(
            hashlib.sha256(
                _FILL_DOMAIN + digest + counter.to_bytes(8, "big")
            ).digest()
        )
        counter += 1
    return bytes(output[:length])


def assign_authored_records(
    envelope: CapacityEnvelope,
    demands: tuple[AuthoredRecordDemand, ...],
) -> tuple[SlotAssignment, ...]:
    """Assign each declared future record to the first compatible unused slot."""

    if type(envelope) is not CapacityEnvelope:
        raise TypeError("expected CapacityEnvelope")
    if type(demands) is not tuple or len(demands) > _MAX_TOTAL_SLOTS:
        _fail("demand_shape", "demands")
    buckets = {item.bucket_id: item for item in envelope.buckets}
    used: set[tuple[str, int]] = set()
    records: set[int] = set()
    output = []
    for ordinal, demand in enumerate(demands):
        path = f"demands[{ordinal}]"
        if type(demand) is not AuthoredRecordDemand:
            _fail("demand_type", path)
        if type(demand.record_id) is not int or not 1 <= demand.record_id <= 0xFFFF:
            _fail("record_id", f"{path}.record_id")
        if demand.record_id in records:
            _fail("duplicate_record", f"{path}.record_id")
        if type(demand.kind) is not int or not 1 <= demand.kind <= _KIND_COUNT:
            _fail("record_kind", f"{path}.kind")
        if type(demand.frame_length) is not int or demand.frame_length <= 0:
            _fail("frame_length", f"{path}.frame_length")
        bucket = buckets.get(demand.bucket_id)
        if bucket is None:
            _fail("unknown_bucket", f"{path}.bucket_id")
        slot = next(
            (
                item
                for item in bucket.slots
                if (item.bucket_id, item.slot_ordinal) not in used
                and item.kind == demand.kind
                and demand.frame_length <= item.frame_length
            ),
            None,
        )
        if slot is None:
            _fail("slot_exhausted", path)
        used.add((slot.bucket_id, slot.slot_ordinal))
        records.add(demand.record_id)
        output.append(
            SlotAssignment(
                demand.record_id,
                demand.bucket_id,
                slot.slot_ordinal,
                demand.kind,
                demand.frame_length,
            )
        )
    return tuple(output)
