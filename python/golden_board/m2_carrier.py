"""Deterministic P6 semantic-envelope and full-carrier construction.

The tracked owners define every byte and ordering rule.  Large manifestations
remain caller-owned/ignored values; this module returns immutable evidence and
never writes an artifact directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from array import array
from math import gcd, isqrt
import tomllib
from typing import NoReturn, Sequence

from . import (
    bootstrap,
    canonical_manifest,
    capacity,
    identity,
    m2_codec,
    m2_policy,
    m2_recipe,
    m2_route_data,
    m2_slice,
)


SEMANTIC_SCHEMA = "golden-board.m2-semantic-envelope/v0"
CANDIDATE_SCHEMA = "golden-board.m2-candidate-manifest/v0"
OWNERSHIP_SCHEMA = "golden-board.m2-ownership-ledger/v0"
CAPACITY_SCHEMA = "golden-board.m2-capacity-ledger/v0"
DENSITY_SCHEMA = "golden-board.m2-density-ledger/v0"
ELIMINATION_SCHEMA = "golden-board.m2-elimination-bound/v0"
CAPACITY_SECTION_FIRST = 211
RESERVE_PAYLOAD_BYTES = 7_141
MAX_SECTION_PAYLOAD = 16_384
FILL_DOMAIN = b"GB-M2-FILL-v0\0"


class CarrierError(ValueError):
    """Stable fail-closed P6 construction error."""

    __slots__ = ("reason",)

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class Manifestation:
    profile_id: str
    semantic_envelope: bytes
    carrier: bytes
    candidate_manifest: bytes
    ownership_ledger: bytes
    capacity_ledger: bytes
    density_ledger: bytes


@dataclass(frozen=True, slots=True)
class R3CarrierOwnerProof:
    """Raw evidence required before any v7 manifestation may be built."""

    promotion_manifest_raw: bytes
    owner_fixture_raw: bytes
    inherited_profile_policy_raw: bytes
    python_route_receipt_raw: bytes
    rust_route_receipt_raw: bytes
    python_limits_receipt_raw: bytes
    rust_limits_receipt_raw: bytes


@dataclass(frozen=True, slots=True)
class R3CarrierPreflight:
    profile_id: str
    side: int
    shell_width: int
    physical_unit_count: int
    lower_bound_cells: int
    route_sha256: str


@dataclass(frozen=True, slots=True)
class _OwnerAdmission:
    inherited_policy: m2_policy.ProfilePolicy
    policy_document: dict[str, object]
    limits_document: dict[str, object]
    route_document: dict[str, object] | None
    semantic_envelope_sha256: str


@dataclass(frozen=True, slots=True)
class RealismEvaluation:
    result: str
    failure_reasons: tuple[str, ...]
    complete_interior_cell_count: int
    complete_interior_one_count: int
    complete_interior_one_density_ppm: int
    tile_one_count_min: int
    tile_one_count_max: int
    longest_horizontal_equal_run: int
    longest_vertical_equal_run: int
    repeated_row_count: int
    repeated_column_count: int


@dataclass(frozen=True, slots=True)
class P6Outcome:
    profile_id: str
    gate5_result: str
    failure_reason: str | None
    elimination_bound: bytes | None
    manifestation: Manifestation | None


@dataclass(frozen=True, slots=True)
class _Section:
    section_id: int
    section_type: int
    closure_class: int
    copy_count: int
    dependencies: tuple[int, ...]
    payload: bytes
    owner_id: str
    game_ordinal: int | None = None
    physical_replica_count: int = 1
    section_version: int = 0


@dataclass(frozen=True, slots=True)
class _Unit:
    unit_id: int
    section_id: int
    semantic_copy_id: int
    fragment_index: int
    encoded: bytes
    owner_kind: str
    replica_index: int = 0
    physical_replica_count: int = 1


def _is_r3(profile: m2_codec.CandidateProfile) -> bool:
    return (
        type(profile) is m2_codec.CandidateProfile
        and profile.profile_version == 7
        and profile.profile_id == "eh72-hier-r5-r2-r1-crc32c-v0"
        and profile.transport_id == m2_codec.HIER_TRANSPORT
        and profile.required_copy_count == 1
        and profile.inventory_version == 1
    )


def _r3_factor(section_id: int, owner_class: str) -> int:
    if section_id in (1, 2, 3, 16):
        return 5
    if owner_class in ("replicated-m2", "reserve-probe"):
        return 2
    if owner_class in ("nonreplicated-m2", "load-probe"):
        return 1
    _fail("physical-replica-owner")


def _unit_permutation_multiplier(interior: int, physical_units: int) -> int:
    """Return the smallest frozen B satisfying the v7 lane separation proof."""

    if (
        type(interior) is not int
        or type(physical_units) is not int
        or interior <= 0
        or physical_units <= 1
    ):
        _fail("unit-permutation")
    population = interior * interior
    cell_multiplier = 2 * interior - 1
    window = max(32, interior // 8)
    for candidate in range(1, physical_units):
        if gcd(candidate, physical_units) != 1:
            continue
        valid = True
        for distance in range(1, 5):
            residue = (candidate * distance) % physical_units
            for delta in (residue, residue - physical_units):
                physical = (cell_multiplier * 1728 * delta) % population
                row, column = divmod(physical, interior)
                column_separation = min(column, interior - column)
                row_deltas = (row,) if column == 0 else (row, (row + 1) % interior)
                for row_delta in row_deltas:
                    row_separation = min(row_delta, interior - row_delta)
                    if max(row_separation, column_separation) < window:
                        valid = False
                        break
                if not valid:
                    break
            if not valid:
                break
        if valid:
            return candidate
    _fail("unit-permutation")


@lru_cache(maxsize=1)
def unit_multiplier_table() -> bytes:
    """Regenerate the exact bootstrap-v1 table-17 payload."""

    result = bytearray(256)
    for index in range(1, 255):
        interior = 8 * index
        physical_units = (interior * interior) // 1728
        if physical_units < 2:
            continue
        try:
            result[index] = _unit_permutation_multiplier(
                interior, physical_units
            )
        except CarrierError as error:
            if error.reason != "unit-permutation":
                raise
    return bytes(result)


def mapping_parameters(
    profile: m2_codec.CandidateProfile,
    side: int,
    shell_width: int,
    physical_units: int,
) -> dict[str, int | str]:
    """Return the exact legacy or v7 interior mapping parameters."""

    if (
        type(profile) is not m2_codec.CandidateProfile
        or type(side) is not int
        or type(shell_width) is not int
        or type(physical_units) is not int
        or side <= 2 * shell_width
        or shell_width <= 0
        or physical_units <= 0
    ):
        _fail("mapping")
    if _is_r3(profile) and (
        side % 8 != 0
        or shell_width % 8 != 0
        or not 64 <= side <= 2_048
        or not 8 <= shell_width <= 128
        or shell_width > (side - 8) // 2
    ):
        _fail("mapping")
    interior = side - 2 * shell_width
    population = interior * interior
    multiplier = 2 * interior - 1
    offset = (profile.profile_version * 40_503 + shell_width * 257) % population
    try:
        inverse = pow(multiplier, -1, population)
    except ValueError as error:
        raise CarrierError("mapping") from error
    if _is_r3(profile):
        expected_units = population // (profile.protected_unit_bytes * 8)
        if physical_units != expected_units:
            _fail("mapping-unit-count")
        unit_multiplier = unit_multiplier_table()[interior // 8]
        if unit_multiplier == 0:
            _fail("unit-permutation")
        try:
            inverse_unit_multiplier = pow(unit_multiplier, -1, physical_units)
        except ValueError as error:
            raise CarrierError("unit-permutation") from error
        return {
            "id": "affine-slot-then-interior-v1",
            "interior_side": interior,
            "population": population,
            "unit_population": physical_units,
            "unit_multiplier": unit_multiplier,
            "unit_inverse_multiplier": inverse_unit_multiplier,
            "cell_multiplier": multiplier,
            "offset": offset,
            "cell_inverse_multiplier": inverse,
        }
    return {
        "id": "affine-interior-v1",
        "interior_side": interior,
        "population": population,
        "multiplier": multiplier,
        "offset": offset,
        "inverse_multiplier": inverse,
    }


def map_unit_bit(
    mapping: dict[str, int | str], unit_id: int, bit_offset: int
) -> int:
    """Map one protected-unit bit to a zero-based interior physical cell."""

    if (
        type(mapping) is not dict
        or type(unit_id) is not int
        or type(bit_offset) is not int
        or unit_id <= 0
        or not 0 <= bit_offset < 1728
    ):
        _fail("mapping")
    try:
        population = int(mapping["population"])
        multiplier = int(mapping["cell_multiplier"])
        offset = int(mapping["offset"])
    except (KeyError, TypeError, ValueError) as error:
        raise CarrierError("mapping") from error
    if mapping.get("id") == "affine-slot-then-interior-v1":
        count = mapping.get("unit_population")
        unit_multiplier = mapping.get("unit_multiplier")
        if (
            type(count) is not int
            or type(unit_multiplier) is not int
            or not 1 <= unit_id <= count
        ):
            _fail("mapping")
        slot = (unit_multiplier * (unit_id - 1)) % count
        logical = 1728 * slot + bit_offset
    else:
        _fail("mapping")
    return (multiplier * logical + offset) % population


def invert_interior_cell(
    mapping: dict[str, int | str], physical: int
) -> tuple[int, int] | None:
    """Invert a mapped cell, returning ``None`` for the fixed-pad tail."""

    if type(mapping) is not dict or type(physical) is not int:
        _fail("mapping")
    try:
        population = int(mapping["population"])
        offset = int(mapping["offset"])
        inverse = int(mapping["cell_inverse_multiplier"])
    except (KeyError, TypeError, ValueError) as error:
        raise CarrierError("mapping") from error
    if not 0 <= physical < population:
        _fail("mapping")
    logical = (inverse * (physical - offset)) % population
    slot, bit_offset = divmod(logical, 1728)
    if mapping.get("id") == "affine-slot-then-interior-v1":
        count = mapping.get("unit_population")
        inverse_unit = mapping.get("unit_inverse_multiplier")
        if type(count) is not int or type(inverse_unit) is not int:
            _fail("mapping")
        if slot >= count:
            return None
        ordinal = (inverse_unit * slot) % count
        return ordinal + 1, bit_offset
    _fail("mapping")


def _fail(reason: str) -> NoReturn:
    raise CarrierError(reason)


def _closure(value: str) -> int:
    if value == "m2_required":
        return 128
    if value == "m2_all_only":
        return 129
    _fail("closure")


def _copy_class(value: str) -> str:
    if value == "replicated-core0-2":
        return "replicated-m2"
    if value == "nonreplicated-core3-4":
        return "nonreplicated-m2"
    _fail("copy-class")


def _frames(stream: bytes) -> dict[int, bytes]:
    if type(stream) is not bytes or len(stream) < 4:
        _fail("content-stream")
    count = int.from_bytes(stream[2:4], "big")
    offset = 4
    result: dict[int, bytes] = {}
    for _ in range(count):
        if len(stream) - offset < 8:
            _fail("content-stream")
        record_id = int.from_bytes(stream[offset : offset + 2], "big")
        length = 8 + int.from_bytes(stream[offset + 4 : offset + 8], "big")
        end = offset + length
        if record_id in result or end > len(stream):
            _fail("content-stream")
        result[record_id] = stream[offset:end]
        offset = end
    if offset != len(stream):
        _fail("content-stream")
    return result


def semantic_envelope_value(
    compiled: m2_slice.SliceCompilation,
    inputs: capacity.CapacityInputs,
    envelope: capacity.CapacityEnvelope,
) -> dict[str, object]:
    """Return the exact compact candidate-neutral semantic projection."""

    if (
        type(compiled) is not m2_slice.SliceCompilation
        or type(inputs) is not capacity.CapacityInputs
        or type(envelope) is not capacity.CapacityEnvelope
        or compiled.content_sha256 != inputs.slice_semantic_sha256
        or envelope.slice_semantic_sha256 != inputs.slice_semantic_sha256
    ):
        _fail("semantic-input")
    assignments = {item.section_id: item for item in compiled.atomic_assignments}
    if set(assignments) != {item.section_id for item in inputs.real_content_sections}:
        _fail("semantic-sections")
    prototype_rows = [
        [item.kind, item.prototype_id, item.source_record_id, item.frame_length]
        for item in inputs.prototypes
    ]
    real_rows = []
    for item in sorted(inputs.real_content_sections, key=lambda row: row.section_id):
        assignment = assignments[item.section_id]
        game = assignment.game_ordinal
        real_rows.append(
            [
                item.section_id,
                _closure(item.closure),
                "replicated-m2" if item.closure == "m2_required" else "nonreplicated-m2",
                item.payload_length,
                list(item.record_ids),
                game is not None,
                65_535 if game is None else game,
            ]
        )
    tier_rows = [
        [
            item.section_id,
            128,
            "fixed-two-m2",
            item.logical_payload_length,
            list(item.body_section_ids),
        ]
        for item in sorted(inputs.tier_frames, key=lambda row: row.section_id)
    ]
    bucket_rows = []
    capacity_rows = []
    slot_rows = []
    next_section_id = CAPACITY_SECTION_FIRST
    for bucket in envelope.buckets:
        copy_class = _copy_class(bucket.protection_class)
        bucket_rows.append(
            [
                bucket.bucket_id,
                bucket.tier,
                copy_class,
                bucket.payload_length,
                len(bucket.slots),
                len(bucket.sections),
            ]
        )
        for section in bucket.sections:
            capacity_rows.append(
                [
                    next_section_id,
                    bucket.bucket_id,
                    section.section_ordinal,
                    section.tier,
                    copy_class,
                    section.first_slot_ordinal,
                    section.slot_count,
                    section.payload_length,
                ]
            )
            next_section_id += 1
        slot_rows.extend(
            [
                slot.bucket_id,
                slot.slot_ordinal,
                slot.role_ordinal,
                slot.role_id,
                slot.kind,
                slot.prototype_id,
                slot.frame_length,
            ]
            for slot in bucket.slots
        )
    if next_section_id != CAPACITY_SECTION_FIRST + 53 or len(slot_rows) != 4_174:
        _fail("semantic-count")
    return {
        "schema": SEMANTIC_SCHEMA,
        "slice_semantic_sha256": inputs.slice_semantic_sha256,
        "prototype_row_fields": ["kind", "prototype_id", "source_record_id", "frame_length"],
        "prototype_rows": prototype_rows,
        "real_section_row_fields": ["section_id", "closure_class", "copy_class", "logical_payload_bytes", "record_ids", "has_game_ordinal", "game_ordinal"],
        "real_section_rows": real_rows,
        "tier_frame_row_fields": ["section_id", "closure_class", "copy_class", "logical_payload_bytes", "dependency_ids"],
        "tier_frame_rows": tier_rows,
        "bucket_row_fields": ["bucket_id", "tier", "copy_class", "logical_payload_bytes", "slot_count", "section_count"],
        "bucket_rows": bucket_rows,
        "capacity_section_row_fields": ["section_id", "bucket_id", "section_ordinal", "tier", "copy_class", "first_slot_ordinal", "slot_count", "logical_payload_bytes"],
        "capacity_section_rows": capacity_rows,
        "slot_row_fields": ["bucket_id", "slot_ordinal", "role_ordinal", "role_id", "kind", "prototype_id", "frame_length"],
        "slot_rows": slot_rows,
        "totals": {
            "prototype_count": len(prototype_rows),
            "real_section_count": len(real_rows),
            "tier_frame_count": len(tier_rows),
            "bucket_count": len(bucket_rows),
            "capacity_section_count": len(capacity_rows),
            "slot_count": len(slot_rows),
            "authoring_payload_bytes": envelope.authoring_payload_bytes,
        },
    }


def render_semantic_envelope(
    compiled: m2_slice.SliceCompilation,
    inputs: capacity.CapacityInputs,
    envelope: capacity.CapacityEnvelope,
) -> bytes:
    return canonical_manifest.serialize_manifest(
        semantic_envelope_value(compiled, inputs, envelope)
    )


def _fill(length: int, digest_hex: str) -> bytes:
    if not 0 <= length <= 1_048_576:
        _fail("fill-length")
    digest = bytes.fromhex(digest_hex)
    output = bytearray()
    counter = 0
    while len(output) < length:
        output.extend(sha256(FILL_DOMAIN + digest + counter.to_bytes(8, "big")).digest())
        counter += 1
    return bytes(output[:length])


def _bits(raw: bytes) -> list[int]:
    return [(byte >> shift) & 1 for byte in raw for shift in range(7, -1, -1)]


def _packed(bits: Sequence[int]) -> bytes:
    if any(value not in (0, 1) for value in bits):
        _fail("bit-value")
    output = bytearray((len(bits) + 7) // 8)
    for index, value in enumerate(bits):
        output[index // 8] |= value << (7 - index % 8)
    return bytes(output)


def _section_charge(
    payload_length: int, dependency_count: int, check_id: int, copy_count: int
) -> capacity.SectionCharge:
    if type(payload_length) is not int or not 0 <= payload_length <= MAX_SECTION_PAYLOAD:
        _fail("section-payload")
    return capacity.section_charge(
        payload_length, dependency_count, check_id, copy_count
    )


def _tier_payloads(
    compiled: m2_slice.SliceCompilation, inputs: capacity.CapacityInputs
) -> dict[int, bytes]:
    all_frames = _frames(compiled.content_bytes)
    required_frames = _frames(compiled.required_content_bytes)
    result = {}
    for item in inputs.tier_frames:
        frames = required_frames if item.section_id == 2 else all_frames
        root_id = 29 if item.section_id == 2 else 182
        result[item.section_id] = bootstrap.encode_tier_frame(
            bootstrap.TierFrame(
                item.section_id - 2,
                item.body_section_ids,
                item.assembled_stream_length,
                item.assembled_record_count,
                frames[root_id],
            )
        )
    return result


def _real_payloads(
    compiled: m2_slice.SliceCompilation, inputs: capacity.CapacityInputs
) -> dict[int, bytes]:
    frames = _frames(compiled.content_bytes)
    return {
        item.section_id: b"".join(frames[record_id] for record_id in item.record_ids)
        for item in inputs.real_content_sections
    }


def _layout_for_geometry(
    profile: m2_codec.CandidateProfile,
    side: int,
    shell_width: int,
    inputs: capacity.CapacityInputs,
    semantic: dict[str, object],
) -> tuple[int, tuple[int, ...], tuple[int, ...], int]:
    """Return load count, load fragment counts/payloads, and interior pad cells."""

    interior = side - 2 * shell_width
    if interior <= 0:
        _fail("geometry")
    population = interior * interior
    check_id = 1 if profile.check_bytes == 4 else 2
    capacity_rows = semantic["capacity_section_rows"]
    if type(capacity_rows) is not list:
        _fail("semantic-capacity-row")
    reserve_payloads = capacity.partition_probe_payload(
        RESERVE_PAYLOAD_BYTES, MAX_SECTION_PAYLOAD
    )
    real_by_id = {item.section_id: item for item in inputs.real_content_sections}
    tier_by_id = {item.section_id: item for item in inputs.tier_frames}
    base_entry_count = 1 + len(tier_by_id) + len(real_by_id) + len(capacity_rows) + len(reserve_payloads)
    dependency_total = sum(len(item.body_section_ids) for item in tier_by_id.values())
    unit_bits = profile.protected_unit_bytes * 8
    maximum_load_fragments = (
        18 + MAX_SECTION_PAYLOAD + profile.check_bytes + 156
    ) // 157
    r3 = _is_r3(profile)

    def physical_units(
        payload_length: int,
        dependency_count: int,
        semantic_copies: int,
        factor: int,
    ) -> int:
        charge = _section_charge(
            payload_length, dependency_count, check_id, semantic_copies
        )
        return charge.common_blocks * factor

    def nonload_units(load_count: int) -> int:
        entry_count = base_entry_count + load_count
        if entry_count > 4_096:
            _fail("inventory-count")
        inventory_payload = 8 + 20 * entry_count + 4 * dependency_total
        total = physical_units(
            inventory_payload, 0, 1 if r3 else 2, 5 if r3 else 1
        )
        for item in tier_by_id.values():
            total += physical_units(
                item.logical_payload_length,
                len(item.body_section_ids),
                1 if r3 else 2,
                _r3_factor(item.section_id, "replicated-m2") if r3 else 1,
            )
        for item in real_by_id.values():
            copies = (
                1
                if r3
                else profile.required_copy_count
                if item.closure == "m2_required"
                else 1
            )
            owner_class = (
                "replicated-m2"
                if item.closure == "m2_required"
                else "nonreplicated-m2"
            )
            total += physical_units(
                item.payload_length,
                0,
                copies,
                _r3_factor(item.section_id, owner_class) if r3 else 1,
            )
        for row in capacity_rows:
            if not isinstance(row, list) or len(row) != 8:
                _fail("semantic-capacity-row")
            copies = (
                1
                if r3
                else profile.required_copy_count
                if row[4] == "replicated-m2"
                else 1
            )
            total += physical_units(
                row[7],
                0,
                copies,
                _r3_factor(row[0], row[4]) if r3 else 1,
            )
        for payload in reserve_payloads:
            total += physical_units(
                payload,
                0,
                1 if r3 else profile.required_copy_count,
                2 if r3 else 1,
            )
        return total

    selected: tuple[int, int] | None = None
    maximum_load_count = min(
        4_096 - base_entry_count,
        (MAX_SECTION_PAYLOAD - 8 - 20 * base_entry_count - 4 * dependency_total) // 20,
    )
    if maximum_load_count < 0:
        _fail("load-fixed-point")
    for load_count in range(maximum_load_count + 1):
        fixed_units = nonload_units(load_count)
        if r3:
            if (
                interior % 8 != 0
                or not 0 < interior // 8 < 255
                or unit_multiplier_table()[interior // 8] == 0
            ):
                continue
        fixed_cells = fixed_units * unit_bits
        if fixed_cells > population:
            continue
        available = (population - fixed_cells) // unit_bits
        required = 0 if available == 0 else (available + maximum_load_fragments - 1) // maximum_load_fragments
        if load_count == 0:
            if available == 0:
                selected = (0, 0)
                break
        elif available >= load_count and load_count >= required:
            selected = (load_count, available)
            break
    if selected is None:
        _fail("load-fixed-point")
    load_count, load_units = selected
    fragment_counts = []
    remaining = load_units
    for ordinal in range(load_count):
        minimum_tail = load_count - ordinal - 1
        value = min(maximum_load_fragments, remaining - minimum_tail)
        if value <= 0:
            _fail("load-fragments")
        fragment_counts.append(value)
        remaining -= value
    if remaining:
        _fail("load-fragments")
    payloads = tuple(
        min(
            MAX_SECTION_PAYLOAD,
            fragments * 157 - 18 - profile.check_bytes,
        )
        for fragments in fragment_counts
    )
    if any(
        _section_charge(payload, 0, check_id, 1).fragments_per_copy != fragments
        for payload, fragments in zip(payloads, fragment_counts, strict=True)
    ):
        _fail("load-payload")
    used_cells = (nonload_units(load_count) + load_units) * unit_bits
    return load_count, tuple(fragment_counts), payloads, population - used_cells


def derive_r3_capacity_projection(
    profile: m2_codec.CandidateProfile,
    side: int,
    shell_width: int,
    inputs: capacity.CapacityInputs,
    semantic: dict[str, object],
) -> dict[str, object]:
    """Derive the exact route-owner capacity projection without a carrier."""

    if not _is_r3(profile):
        _fail("r3-capacity-profile")
    load_count, load_fragments, load_payloads, fixed_pad = _layout_for_geometry(
        profile, side, shell_width, inputs, semantic
    )
    capacity_rows = semantic.get("capacity_section_rows")
    if type(capacity_rows) is not list:
        _fail("semantic-capacity-row")
    reserve_payloads = capacity.partition_probe_payload(
        RESERVE_PAYLOAD_BYTES, MAX_SECTION_PAYLOAD
    )
    dependency_count = sum(
        len(item.body_section_ids) for item in inputs.tier_frames
    )
    inventory_entry_count = (
        1
        + len(inputs.tier_frames)
        + len(inputs.real_content_sections)
        + len(capacity_rows)
        + len(reserve_payloads)
        + load_count
    )
    inventory_payload = (
        8 + 20 * inventory_entry_count + 4 * dependency_count
    )
    fixed_sections: list[tuple[int, int, int]] = [(inventory_payload, 0, 5)]
    fixed_sections.extend(
        (
            item.logical_payload_length,
            len(item.body_section_ids),
            _r3_factor(item.section_id, "replicated-m2"),
        )
        for item in inputs.tier_frames
    )
    fixed_sections.extend(
        (
            item.payload_length,
            0,
            _r3_factor(
                item.section_id,
                "replicated-m2"
                if item.closure == "m2_required"
                else "nonreplicated-m2",
            ),
        )
        for item in inputs.real_content_sections
    )
    for row in capacity_rows:
        if not isinstance(row, list) or len(row) != 8:
            _fail("semantic-capacity-row")
        fixed_sections.append(
            (row[7], 0, _r3_factor(row[0], row[4]))
        )
    fixed_sections.extend((payload, 0, 2) for payload in reserve_payloads)
    factor_counts = {1: 0, 2: 0, 5: 0}
    for payload, dependencies, factor in fixed_sections:
        fragments = _section_charge(payload, dependencies, 1, 1).common_blocks
        factor_counts[factor] += fragments
    fixed_logical_groups = sum(factor_counts.values())
    mandatory_physical_units = sum(
        factor * count for factor, count in factor_counts.items()
    )
    factor_counts[1] += sum(load_fragments)
    physical_units = mandatory_physical_units + sum(load_fragments)
    interior = side - 2 * shell_width
    population = interior * interior
    unit_population = population // 1_728
    if physical_units != unit_population or fixed_pad != population - 1_728 * physical_units:
        _fail("r3-capacity-reconciliation")
    mapping = mapping_parameters(
        profile, side, shell_width, physical_units
    )
    inventory_fragments = _section_charge(
        inventory_payload, 0, 1, 1
    ).common_blocks
    return {
        "cell_inverse_multiplier": mapping["cell_inverse_multiplier"],
        "cell_multiplier": mapping["cell_multiplier"],
        "cell_offset": mapping["offset"],
        "encoded_transport_bytes": physical_units * profile.protected_unit_bytes,
        "factor_1_group_count": factor_counts[1],
        "factor_2_group_count": factor_counts[2],
        "factor_5_group_count": factor_counts[5],
        "fixed_logical_group_count": fixed_logical_groups,
        "fixed_pad_cells": fixed_pad,
        "interior_side": interior,
        "inventory_dependency_count": dependency_count,
        "inventory_entry_count": inventory_entry_count,
        "inventory_fragment_count": inventory_fragments,
        "inventory_payload_bytes": inventory_payload,
        "load_fragment_counts": list(load_fragments),
        "load_payload_bytes": list(load_payloads),
        "logical_group_count": fixed_logical_groups + sum(load_fragments),
        "mandatory_physical_unit_count": mandatory_physical_units,
        "physical_unit_count": physical_units,
        "population": population,
        "protected_cells": 1_728 * physical_units,
        "separation_window": max(32, interior // 8),
        "slot_inverse_multiplier": mapping["unit_inverse_multiplier"],
        "slot_multiplier": mapping["unit_multiplier"],
    }


def _reconcile_r3_capacity_projection(
    admission: _OwnerAdmission,
    profile: m2_codec.CandidateProfile,
    projection: dict[str, object],
    side: int,
    shell_width: int,
) -> None:
    route = admission.route_document
    selected = admission.limits_document.get("selected_manifestation")
    generated = admission.policy_document.get("generated")
    limit_rows = admission.limits_document.get("profile")
    if (
        type(route) is not dict
        or type(selected) is not dict
        or type(generated) is not dict
        or type(limit_rows) is not list
        or len(limit_rows) != 1
        or type(limit_rows[0]) is not dict
    ):
        _fail("r3-capacity-owner")
    route_generated = route.get("generated")
    if type(route_generated) is not dict:
        _fail("r3-capacity-owner")
    selected_projection = {
        "carrier_bytes": side * side // 8,
        "cell_inverse_multiplier": projection["cell_inverse_multiplier"],
        "cell_multiplier": projection["cell_multiplier"],
        "cell_offset": projection["cell_offset"],
        "cells": side * side,
        "dependency_edges": projection["inventory_dependency_count"],
        "encoded_transport_bytes": projection["encoded_transport_bytes"],
        "factor_1_group_count": projection["factor_1_group_count"],
        "factor_2_group_count": projection["factor_2_group_count"],
        "factor_5_group_count": projection["factor_5_group_count"],
        "fixed_pad_cells": projection["fixed_pad_cells"],
        "interior_side": projection["interior_side"],
        "inventory_dependency_count": projection[
            "inventory_dependency_count"
        ],
        "inventory_entry_count": projection["inventory_entry_count"],
        "inventory_fragment_count": projection["inventory_fragment_count"],
        "inventory_payload_bytes": projection["inventory_payload_bytes"],
        "load_fragment_counts": projection["load_fragment_counts"],
        "load_payload_bytes": projection["load_payload_bytes"],
        "logical_group_count": projection["logical_group_count"],
        "mandatory_physical_unit_count": projection[
            "mandatory_physical_unit_count"
        ],
        "physical_unit_count": projection["physical_unit_count"],
        "population": projection["population"],
        "protected_cells": projection["protected_cells"],
        "sector_capacity_bytes": shell_width * (side - shell_width) // 8,
        "semantic_copy_count": 1,
        "separation_window": projection["separation_window"],
        "shell_width": shell_width,
        "side": side,
        "slot_inverse_multiplier": projection["slot_inverse_multiplier"],
        "slot_multiplier": projection["slot_multiplier"],
    }
    if (
        route_generated.get("capacity_projection") != projection
        or any(selected.get(key) != value for key, value in selected_projection.items())
        or route.get("side") != side
        or route.get("shell_width") != shell_width
        or route.get("sector_capacity_bytes")
        != selected_projection["sector_capacity_bytes"]
        or generated.get("side") != side
        or generated.get("shell_width") != shell_width
        or generated.get("physical_unit_count") != profile.protected_units
        or generated.get("encoded_transport_bytes")
        != profile.encoded_transport_bytes
        or limit_rows[0].get("protected_units") != profile.protected_units
        or limit_rows[0].get("encoded_transport_bytes")
        != profile.encoded_transport_bytes
    ):
        _fail("r3-capacity-owner")


def _reconcile_r3_realization(
    admission: _OwnerAdmission,
    profile: m2_codec.CandidateProfile,
    sections: tuple[_Section, ...],
    units: tuple[_Unit, ...],
    envelopes: dict[int, bytes],
    charges: dict[int, capacity.SectionCharge],
) -> None:
    selected = admission.limits_document.get("selected_manifestation")
    limit_rows = admission.limits_document.get("profile")
    if (
        type(selected) is not dict
        or type(limit_rows) is not list
        or len(limit_rows) != 1
        or type(limit_rows[0]) is not dict
    ):
        _fail("r3-realization-owner")
    factor_counts = {1: 0, 2: 0, 5: 0}
    for section in sections:
        if section.copy_count != 1 or section.physical_replica_count not in factor_counts:
            _fail("r3-realization-shape")
        factor_counts[section.physical_replica_count] += charges[
            section.section_id
        ].fragments_per_copy
    inventory = next(
        (section for section in sections if section.section_id == 1), None
    )
    maximum_envelope = max(len(raw) for raw in envelopes.values())
    maximum_fragments = max(
        charge.fragments_per_copy for charge in charges.values()
    )
    dependency_edges = sum(len(section.dependencies) for section in sections)
    expected = {
        "factor_1_group_count": factor_counts[1],
        "factor_2_group_count": factor_counts[2],
        "factor_5_group_count": factor_counts[5],
        "inventory_dependency_count": dependency_edges,
        "inventory_entry_count": len(sections),
        "inventory_fragment_count": charges[1].fragments_per_copy,
        "inventory_payload_bytes": 0 if inventory is None else len(inventory.payload),
        "maximum_fragments_per_section": maximum_fragments,
        "maximum_section_envelope_bytes": maximum_envelope,
        "physical_unit_count": len(units),
    }
    limit_row = limit_rows[0]
    if (
        inventory is None
        or any(selected.get(key) != value for key, value in expected.items())
        or len(units) != profile.protected_units
        or sum(len(unit.encoded) for unit in units)
        != profile.encoded_transport_bytes
        or limit_row.get("fragments_per_semantic_copy") != maximum_fragments
        or limit_row.get("section_envelope_bytes") != maximum_envelope
        or limit_row.get("protected_units") != len(units)
        or limit_row.get("semantic_copy_count") != 1
    ):
        _fail("r3-realization-owner")


def _shell_blueprint(
    route_manifest_raw: bytes,
    profile: m2_codec.CandidateProfile,
    recipient_package: bytes,
) -> tuple[
    m2_route_data.CandidateRouteData,
    tuple[bytes, bytes, bytes, bytes],
    tuple[tuple[tuple[str, int], ...], ...],
    tuple[int, int, int, int],
]:
    candidate = m2_route_data.CandidateRouteData(
        profile.profile_id,
        profile.profile_version,
        profile.transport_id,
        profile.section_check_id,
        (recipient_package,),
    )
    if _is_r3(profile):
        try:
            route = canonical_manifest.validate_canonical_manifest(
                route_manifest_raw
            )
            package = bootstrap.decode_recipe_package(recipient_package, 7)
        except (TypeError, ValueError) as error:
            raise CarrierError("recipient-package") from error
        generated = route.get("generated")
        if (
            route.get("schema") != "golden-board.route-data/v1"
            or type(generated) is not dict
            or len(recipient_package) != generated.get("recipient_package_bytes")
            or sha256(recipient_package).hexdigest()
            != generated.get("recipient_package_sha256")
            or package.total_node_count
            != generated.get("recipient_package_node_count")
            or package.total_edge_count
            != generated.get("recipient_package_edge_count")
            or package.table_payload_bytes
            != generated.get("recipient_package_table_payload_bytes")
            or package.maximum_primitive_steps
            != generated.get("recipient_package_primitive_steps")
            or package.peak_live_scratch_bytes
            != generated.get("recipient_package_peak_scratch_bytes")
        ):
            _fail("recipient-package")
        try:
            maximum = m2_route_data.build_r3_route_images(
                candidate, 2_048, 128
            )
        except (TypeError, ValueError) as error:
            raise CarrierError("route-owner") from error
    else:
        try:
            m2_recipe.admit_eh72_transport_recipe(
                profile.profile_version, recipient_package
            )
        except (TypeError, ValueError) as error:
            raise CarrierError("recipient-package") from error
        maximum = m2_route_data.build_route_images(
            route_manifest_raw, candidate, 2_048, 128
        )
    route_parts = []
    owners = []
    headrooms = []
    for sector in maximum.sectors:
        route_parts.append(sector.data[: sector.route_prefix_cells // 8])
        owner_rows = []
        for span in sector.spans[2:]:
            if span.owner.startswith("headroom") or span.owner == "fixed-pad":
                break
            owner_rows.append((span.owner, span.cell_count))
        owners.append(tuple(owner_rows))
        headrooms.append(sector.headroom_cells)
    if len(route_parts) != 4 or len(owners) != 4 or len(headrooms) != 4:
        _fail("route-count")
    if _is_r3(profile):
        prefix_sha256 = [sha256(raw).hexdigest() for raw in route_parts]
        if (
            [len(raw) * 8 for raw in route_parts]
            != generated.get("route_prefix_cells_by_sector")
            or prefix_sha256
            != generated.get("route_prefix_sha256_by_sector")
            or sha256(b"".join(route_parts)).hexdigest()
            != generated.get("route_sha256")
            or headrooms != generated.get("route_headroom_cells_by_sector")
        ):
            _fail("route-owner")
    return (
        candidate,
        (route_parts[0], route_parts[1], route_parts[2], route_parts[3]),
        (owners[0], owners[1], owners[2], owners[3]),
        (headrooms[0], headrooms[1], headrooms[2], headrooms[3]),
    )


def _admit_owners(
    profile: m2_codec.CandidateProfile,
    profile_policy_raw: bytes,
    profile_limits_raw: bytes,
    damage_policy_raw: bytes,
    bootstrap_spec_raw: bytes,
    inputs: capacity.CapacityInputs,
    route_manifest_raw: bytes | None = None,
    r3_owner_proof: R3CarrierOwnerProof | None = None,
) -> _OwnerAdmission:
    if _is_r3(profile):
        if (
            type(r3_owner_proof) is not R3CarrierOwnerProof
            or type(route_manifest_raw) is not bytes
            or any(
                type(raw) is not bytes
                for raw in (
                    r3_owner_proof.promotion_manifest_raw,
                    r3_owner_proof.owner_fixture_raw,
                    r3_owner_proof.inherited_profile_policy_raw,
                    r3_owner_proof.python_route_receipt_raw,
                    r3_owner_proof.rust_route_receipt_raw,
                    r3_owner_proof.python_limits_receipt_raw,
                    r3_owner_proof.rust_limits_receipt_raw,
                )
            )
        ):
            _fail("r3-owner-proof")
        try:
            bundle = m2_policy.R3PromotionWriteBundle(
                profile_policy_raw,
                damage_policy_raw,
                route_manifest_raw,
                profile_limits_raw,
                r3_owner_proof.promotion_manifest_raw,
            )
            m2_policy.load_r3_promoted_owner_set(
                bundle,
                bootstrap_spec_raw,
                r3_owner_proof.owner_fixture_raw,
                r3_owner_proof.python_route_receipt_raw,
                r3_owner_proof.rust_route_receipt_raw,
                r3_owner_proof.python_limits_receipt_raw,
                r3_owner_proof.rust_limits_receipt_raw,
            )
            policy_document = tomllib.loads(profile_policy_raw.decode("utf-8"))
            limits_document = tomllib.loads(profile_limits_raw.decode("utf-8"))
            route_document = canonical_manifest.validate_canonical_manifest(
                route_manifest_raw
            )
            inherited_policy = m2_policy.load_profile_policy(
                r3_owner_proof.inherited_profile_policy_raw
            )
            inherited_document = tomllib.loads(
                r3_owner_proof.inherited_profile_policy_raw.decode("utf-8")
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            UnicodeError,
            tomllib.TOMLDecodeError,
        ) as error:
            raise CarrierError("owner-admission") from error
        base = policy_document.get("base")
        bindings = policy_document.get("bindings")
        generated = policy_document.get("generated")
        profile_rows = policy_document.get("profile")
        limit_rows = limits_document.get("profile")
        selected = limits_document.get("selected_manifestation")
        route_generated = route_document.get("generated")
        if (
            type(base) is not dict
            or base.get("sha256") != inherited_policy.sha256
            or base.get("mutable_live_v0_fallback") is not False
            or inherited_document.get("schema")
            != "golden-board.profile-policy/v0"
            or type(bindings) is not dict
            or type(generated) is not dict
            or type(profile_rows) is not list
            or len(profile_rows) != 1
            or type(limit_rows) is not list
            or len(limit_rows) != 1
            or type(selected) is not dict
            or type(route_generated) is not dict
        ):
            _fail("r3-owner-shape")
        policy_row = profile_rows[0]
        limit_row = limit_rows[0]
        if type(policy_row) is not dict or type(limit_row) is not dict:
            _fail("r3-owner-shape")
        try:
            expected_profile = m2_codec.r3_candidate_profile(
                protected_units=limit_row["protected_units"],
                encoded_transport_bytes=limit_row["encoded_transport_bytes"],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise CarrierError("r3-owner-profile") from error
        semantic_sha256 = bindings.get("semantic_envelope_sha256")
        capacity_projection = route_generated.get("capacity_projection")
        if (
            profile != expected_profile
            or policy_row.get("id") != profile.profile_id
            or policy_row.get("profile_version") != 7
            or policy_row.get("transport_id") != profile.transport_id
            or policy_row.get("section_check_id") != profile.section_check_id
            or policy_row.get("semantic_copy_count") != 1
            or policy_row.get("complexity_class") != profile.complexity_class
            or policy_row.get("map_id") != profile.placement_id
            or limit_row.get("id") != profile.profile_id
            or limit_row.get("profile_version") != 7
            or limit_row.get("semantic_copy_count") != 1
            or limit_row.get("physical_replica_counts") != [1, 2, 5]
            or limit_row.get("protected_unit_bytes")
            != profile.protected_unit_bytes
            or limits_document.get("profile_ids") != [profile.profile_id]
            or type(semantic_sha256) is not str
            or len(semantic_sha256) != 64
            or bindings.get("slice_semantic_sha256")
            != inputs.slice_semantic_sha256
            or generated.get("physical_unit_count") != profile.protected_units
            or generated.get("encoded_transport_bytes")
            != profile.encoded_transport_bytes
            or generated.get("route_data_sha256")
            != sha256(route_manifest_raw).hexdigest()
            or selected.get("physical_unit_count") != profile.protected_units
            or selected.get("encoded_transport_bytes")
            != profile.encoded_transport_bytes
            or type(capacity_projection) is not dict
            or capacity_projection.get("physical_unit_count")
            != profile.protected_units
            or capacity_projection.get("encoded_transport_bytes")
            != profile.encoded_transport_bytes
        ):
            _fail("r3-owner-binding")
        return _OwnerAdmission(
            inherited_policy,
            policy_document,
            limits_document,
            route_document,
            semantic_sha256,
        )
    if r3_owner_proof is not None or route_manifest_raw is not None:
        _fail("owner-admission")
    try:
        policy = m2_policy.load_profile_policy(profile_policy_raw)
        damage = m2_policy.load_damage_policy(damage_policy_raw)
        limits = m2_policy.load_profile_limits(
            profile_limits_raw, policy, damage, inputs
        )
        profiles = m2_codec.load_candidate_profiles(
            profile_policy_raw, profile_limits_raw
        )
        policy_document = tomllib.loads(profile_policy_raw.decode("utf-8"))
    except (KeyError, TypeError, ValueError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise CarrierError("owner-admission") from error
    selected = tuple(item for item in profiles if item.profile_id == profile.profile_id)
    semantic_capacity = limits.get("semantic_capacity")
    if (
        type(profile) is not m2_codec.CandidateProfile
        or len(selected) != 1
        or selected[0] != profile
        or type(bootstrap_spec_raw) is not bytes
        or sha256(bootstrap_spec_raw).hexdigest()
        != limits.get("bootstrap_spec_sha256")
        or type(semantic_capacity) is not dict
        or semantic_capacity.get("reserve_payload_bytes") != RESERVE_PAYLOAD_BYTES
        or semantic_capacity.get("simulated_sections") != 53
    ):
        _fail("owner-binding")
    semantic_owner = policy_document.get("semantic_envelope_manifest")
    if type(semantic_owner) is not dict:
        _fail("owner-binding")
    semantic_sha256 = semantic_owner.get("expected_sha256")
    if type(semantic_sha256) is not str:
        _fail("owner-binding")
    return _OwnerAdmission(
        policy,
        policy_document,
        limits,
        None,
        semantic_sha256,
    )


def _lower_bound_value(
    profile: m2_codec.CandidateProfile,
    profile_policy_raw: bytes,
    profile_limits_raw: bytes,
    semantic_raw: bytes,
    semantic: dict[str, object],
    inputs: capacity.CapacityInputs,
    route_parts: tuple[bytes, bytes, bytes, bytes],
    side_max: int,
) -> dict[str, object]:
    check_id = 1 if profile.check_bytes == 4 else 2
    r3 = _is_r3(profile)
    capacity_rows = semantic.get("capacity_section_rows")
    if type(capacity_rows) is not list:
        _fail("semantic-capacity-row")
    reserve_payloads = capacity.partition_probe_payload(
        RESERVE_PAYLOAD_BYTES, MAX_SECTION_PAYLOAD
    )
    dependency_total = sum(len(item.body_section_ids) for item in inputs.tier_frames)
    inventory_section_count = (
        1
        + len(inputs.tier_frames)
        + len(inputs.real_content_sections)
        + len(capacity_rows)
        + len(reserve_payloads)
    )
    inventory_payload = 8 + 20 * inventory_section_count + 4 * dependency_total
    if inventory_payload != 3_000:
        _fail("lower-bound-inventory")

    category_sources = (
        (
            "inventory",
            1,
            inventory_payload,
            _section_charge(
                inventory_payload, 0, check_id, 1 if r3 else 2
            ).common_blocks
            * (5 if r3 else 1),
        ),
        (
            "tier-frame",
            len(inputs.tier_frames),
            sum(item.logical_payload_length for item in inputs.tier_frames),
            sum(
                _section_charge(
                    item.logical_payload_length,
                    len(item.body_section_ids),
                    check_id,
                    1 if r3 else 2,
                ).common_blocks
                * (5 if r3 else 1)
                for item in inputs.tier_frames
            ),
        ),
        (
            "real-content",
            len(inputs.real_content_sections),
            sum(item.payload_length for item in inputs.real_content_sections),
            sum(
                _section_charge(
                    item.payload_length,
                    0,
                    check_id,
                    (
                        1
                        if r3
                        else profile.required_copy_count
                        if item.closure == "m2_required"
                        else 1
                    ),
                ).common_blocks
                * (
                    _r3_factor(
                        item.section_id,
                        "replicated-m2"
                        if item.closure == "m2_required"
                        else "nonreplicated-m2",
                    )
                    if r3
                    else 1
                )
                for item in inputs.real_content_sections
            ),
        ),
        (
            "capacity-probe",
            len(capacity_rows),
            sum(row[7] for row in capacity_rows),
            sum(
                _section_charge(
                    row[7],
                    0,
                    check_id,
                    (
                        1
                        if r3
                        else profile.required_copy_count
                        if row[4] == "replicated-m2"
                        else 1
                    ),
                ).common_blocks
                * (_r3_factor(row[0], row[4]) if r3 else 1)
                for row in capacity_rows
            ),
        ),
        (
            "reserve-probe",
            len(reserve_payloads),
            sum(reserve_payloads),
            sum(
                _section_charge(
                    payload,
                    0,
                    check_id,
                    1 if r3 else profile.required_copy_count,
                ).common_blocks
                * (2 if r3 else 1)
                for payload in reserve_payloads
            ),
        ),
    )
    unit_bits = profile.protected_unit_bytes * 8
    category_rows = [
        [name, section_count, logical_bytes, units, units * unit_bits]
        for name, section_count, logical_bytes, units in category_sources
    ]
    unit_count = sum(row[3] for row in category_rows)
    protected_cells = unit_count * unit_bits
    route_prefix_cells = sum(len(item) * 8 for item in route_parts)
    lower_bound_cells = protected_cells + route_prefix_cells
    hard_ceiling = side_max * side_max
    return {
        "schema": ELIMINATION_SCHEMA,
        "profile_policy_sha256": sha256(profile_policy_raw).hexdigest(),
        "profile_limits_sha256": sha256(profile_limits_raw).hexdigest(),
        "semantic_envelope_sha256": sha256(semantic_raw).hexdigest(),
        "profile_id": profile.profile_id,
        "side_max": side_max,
        "protected_unit_bits": unit_bits,
        "route_prefix_cells": route_prefix_cells,
        "category_row_fields": [
            "category_id",
            "semantic_section_count",
            "logical_payload_bytes",
            "protected_unit_count",
            "protected_cells",
        ],
        "category_rows": category_rows,
        "protected_unit_count": unit_count,
        "protected_cells": protected_cells,
        "lower_bound_cells": lower_bound_cells,
        "hard_ceiling_cells": hard_ceiling,
        "candidate_favorable_omissions": [
            "shell-headroom",
            "alignment-pad",
            "load-probe",
        ],
        "result": (
            "lower-bound-exceeds-hard-ceiling"
            if lower_bound_cells > hard_ceiling
            else "lower-bound-does-not-eliminate"
        ),
    }


def render_elimination_bound(
    profile: m2_codec.CandidateProfile,
    profile_policy_raw: bytes,
    profile_limits_raw: bytes,
    damage_policy_raw: bytes,
    bootstrap_spec_raw: bytes,
    compiled: m2_slice.SliceCompilation,
    inputs: capacity.CapacityInputs,
    envelope: capacity.CapacityEnvelope,
    route_manifest_raw: bytes,
    recipient_package: bytes,
) -> bytes:
    """Render exact gate-5 lower-bound evidence for one gate-2 survivor."""

    if type(profile) is not m2_codec.CandidateProfile or profile.profile_version != 3:
        _fail("elimination-profile")
    admission = _admit_owners(
        profile,
        profile_policy_raw,
        profile_limits_raw,
        damage_policy_raw,
        bootstrap_spec_raw,
        inputs,
    )
    policy = admission.inherited_policy
    semantic_raw = render_semantic_envelope(compiled, inputs, envelope)
    semantic = canonical_manifest.validate_canonical_manifest(semantic_raw)
    if sha256(semantic_raw).hexdigest() != admission.semantic_envelope_sha256:
        _fail("semantic-identity")
    _, route_parts, _, _ = _shell_blueprint(
        route_manifest_raw, profile, recipient_package
    )
    value = _lower_bound_value(
        profile,
        profile_policy_raw,
        profile_limits_raw,
        semantic_raw,
        semantic,
        inputs,
        route_parts,
        policy.side_max,
    )
    if value["result"] != "lower-bound-exceeds-hard-ceiling":
        _fail("lower-bound-does-not-eliminate")
    return canonical_manifest.serialize_manifest(value)


def _choose_geometry(
    profile: m2_codec.CandidateProfile,
    inputs: capacity.CapacityInputs,
    semantic: dict[str, object],
    route_parts: tuple[bytes, bytes, bytes, bytes],
    headrooms: tuple[int, int, int, int],
) -> tuple[int, int, tuple[int, ...], tuple[int, ...], int]:
    prefix = tuple(len(item) * 8 for item in route_parts)
    for side in range(64, 2_049, 8):
        maximum_width = min(128, (side - 8) // 2)
        for width in range(8, maximum_width + 1, 8):
            sector_cells = width * (side - width)
            if any(
                prefix[index] + headrooms[index] > sector_cells
                for index in range(4)
            ):
                continue
            try:
                _, fragments, payloads, pad = _layout_for_geometry(
                    profile, side, width, inputs, semantic
                )
            except CarrierError as error:
                if error.reason in {"load-fixed-point", "geometry"}:
                    continue
                raise
            return side, width, fragments, payloads, pad
    _fail("no-fitting-geometry")


def _reconcile_r3_lower_bound(
    admission: _OwnerAdmission,
    lower_bound: dict[str, object],
) -> None:
    geometry_owner = admission.policy_document.get("geometry")
    capacity_owner = admission.policy_document.get("capacity")
    lower_bound_owner = admission.policy_document.get("lower_bound")
    policy_ceiling = admission.limits_document.get("policy_ceiling")
    selected = admission.limits_document.get("selected_manifestation")
    if (
        type(geometry_owner) is not dict
        or type(capacity_owner) is not dict
        or type(lower_bound_owner) is not dict
        or type(policy_ceiling) is not dict
        or type(selected) is not dict
    ):
        _fail("r3-lower-bound-owner")
    expected_omissions = lower_bound_owner.get(
        "candidate_favorable_omissions_allowed"
    )
    if (
        lower_bound.get("protected_unit_count") != 1_465
        or lower_bound.get("protected_unit_count")
        != capacity_owner.get(
            "pre_route_projection_mandatory_physical_units"
        )
        or lower_bound.get("protected_cells") != 2_531_520
        or lower_bound.get("route_prefix_cells") != 930_912
        or lower_bound.get("lower_bound_cells") != 3_462_432
        or lower_bound.get("hard_ceiling_cells") != 4_194_304
        or lower_bound.get("hard_ceiling_cells")
        != geometry_owner.get("raw_bits_max")
        or lower_bound.get("hard_ceiling_cells")
        != policy_ceiling.get("raw_bits")
        or lower_bound.get("candidate_favorable_omissions")
        != expected_omissions
        or expected_omissions
        != ["shell-headroom", "alignment-pad", "load-probe"]
        or lower_bound_owner.get("semantic_copy_count") != 1
        or lower_bound_owner.get(
            "semantic_or_required_overhead_omission_allowed"
        )
        is not False
        or lower_bound_owner.get(
            "elimination_only_when_lower_bound_exceeds_bits_max"
        )
        is not True
        or selected.get("mandatory_physical_unit_count") != 1_465
        or selected.get("physical_unit_count") != 1_841
        or lower_bound.get("result") != "lower-bound-does-not-eliminate"
    ):
        _fail("r3-lower-bound-owner")


def preflight_r3_carrier(
    profile: m2_codec.CandidateProfile,
    profile_policy_raw: bytes,
    profile_limits_raw: bytes,
    damage_policy_raw: bytes,
    bootstrap_spec_raw: bytes,
    compiled: m2_slice.SliceCompilation,
    inputs: capacity.CapacityInputs,
    envelope: capacity.CapacityEnvelope,
    route_manifest_raw: bytes,
    recipient_package: bytes,
    *,
    r3_owner_proof: R3CarrierOwnerProof,
) -> R3CarrierPreflight:
    """Admit all v7 owners and exact geometry without building a carrier."""

    if not _is_r3(profile):
        _fail("r3-preflight-profile")
    admission = _admit_owners(
        profile,
        profile_policy_raw,
        profile_limits_raw,
        damage_policy_raw,
        bootstrap_spec_raw,
        inputs,
        route_manifest_raw,
        r3_owner_proof,
    )
    semantic_raw = render_semantic_envelope(compiled, inputs, envelope)
    semantic = canonical_manifest.validate_canonical_manifest(semantic_raw)
    if sha256(semantic_raw).hexdigest() != admission.semantic_envelope_sha256:
        _fail("semantic-identity")
    _, route_parts, _, headrooms = _shell_blueprint(
        route_manifest_raw, profile, recipient_package
    )
    lower_bound = _lower_bound_value(
        profile,
        profile_policy_raw,
        profile_limits_raw,
        semantic_raw,
        semantic,
        inputs,
        route_parts,
        admission.inherited_policy.side_max,
    )
    _reconcile_r3_lower_bound(admission, lower_bound)
    side, width, _, _, _ = _choose_geometry(
        profile, inputs, semantic, route_parts, headrooms
    )
    projection = derive_r3_capacity_projection(
        profile, side, width, inputs, semantic
    )
    _reconcile_r3_capacity_projection(
        admission, profile, projection, side, width
    )
    route = admission.route_document
    if type(route) is not dict or type(route.get("generated")) is not dict:
        _fail("r3-route-owner")
    route_sha256 = route["generated"].get("route_sha256")
    if type(route_sha256) is not str:
        _fail("r3-route-owner")
    return R3CarrierPreflight(
        profile.profile_id,
        side,
        width,
        int(projection["physical_unit_count"]),
        int(lower_bound["lower_bound_cells"]),
        route_sha256,
    )


def _build_sections(
    profile: m2_codec.CandidateProfile,
    compiled: m2_slice.SliceCompilation,
    inputs: capacity.CapacityInputs,
    semantic: dict[str, object],
    load_payload_lengths: tuple[int, ...],
    fill_bytes: bytes,
) -> tuple[_Section, ...]:
    check_id = 1 if profile.check_bytes == 4 else 2
    r3 = _is_r3(profile)
    real_payloads = _real_payloads(compiled, inputs)
    tier_payloads = _tier_payloads(compiled, inputs)
    assignments = {item.section_id: item for item in compiled.atomic_assignments}
    capacity_rows = semantic["capacity_section_rows"]
    if type(capacity_rows) is not list:
        _fail("semantic-capacity-row")
    reserve_lengths = capacity.partition_probe_payload(
        RESERVE_PAYLOAD_BYTES, MAX_SECTION_PAYLOAD
    )
    payload_total = (
        sum(row[7] for row in capacity_rows)
        + sum(reserve_lengths)
        + sum(load_payload_lengths)
    )
    if len(fill_bytes) < payload_total:
        _fail("fill-short")
    cursor = 0
    sections: list[_Section] = []
    for item in inputs.tier_frames:
        factor = _r3_factor(item.section_id, "replicated-m2") if r3 else 1
        sections.append(
            _Section(
                item.section_id,
                2,
                128,
                1 if r3 else 2,
                item.body_section_ids,
                tier_payloads[item.section_id],
                f"section:{item.section_id:010d}",
                physical_replica_count=factor,
            )
        )
    for item in inputs.real_content_sections:
        assignment = assignments[item.section_id]
        owner_class = (
            "replicated-m2"
            if item.closure == "m2_required"
            else "nonreplicated-m2"
        )
        copies = (
            1
            if r3
            else profile.required_copy_count
            if item.closure == "m2_required"
            else 1
        )
        sections.append(
            _Section(
                item.section_id,
                3,
                _closure(item.closure),
                copies,
                (),
                real_payloads[item.section_id],
                f"section:{item.section_id:010d}",
                assignment.game_ordinal,
                _r3_factor(item.section_id, owner_class) if r3 else 1,
            )
        )
    for row in capacity_rows:
        length = row[7]
        payload = fill_bytes[cursor : cursor + length]
        cursor += length
        copies = (
            1
            if r3
            else profile.required_copy_count
            if row[4] == "replicated-m2"
            else 1
        )
        sections.append(
            _Section(
                row[0],
                4,
                129,
                copies,
                (),
                payload,
                f"section:{row[0]:010d}",
                physical_replica_count=(
                    _r3_factor(row[0], row[4]) if r3 else 1
                ),
            )
        )
    next_id = CAPACITY_SECTION_FIRST + len(capacity_rows)
    for length in reserve_lengths:
        payload = fill_bytes[cursor : cursor + length]
        cursor += length
        sections.append(
            _Section(
                next_id,
                5,
                129,
                1 if r3 else profile.required_copy_count,
                (),
                payload,
                f"section:{next_id:010d}",
                physical_replica_count=2 if r3 else 1,
            )
        )
        next_id += 1
    for length in load_payload_lengths:
        payload = fill_bytes[cursor : cursor + length]
        cursor += length
        sections.append(
            _Section(
                next_id,
                6,
                129,
                1,
                (),
                payload,
                f"section:{next_id:010d}",
                physical_replica_count=1,
            )
        )
        next_id += 1
    if cursor != payload_total:
        _fail("fill-cursor")

    entry_count = 1 + len(sections)
    inventory_length = 8 + 20 * entry_count + 4 * sum(
        len(section.dependencies) for section in sections
    )
    entries = [
        bootstrap.InventoryEntry(
            1,
            1,
            1 if r3 else 0,
            128,
            check_id,
            1 if r3 else 2,
            (),
            inventory_length,
            physical_replica_count=5 if r3 else 1,
        )
    ]
    entries.extend(
        bootstrap.InventoryEntry(
            section.section_id,
            section.section_type,
            section.section_version,
            section.closure_class,
            check_id,
            section.copy_count,
            section.dependencies,
            len(section.payload),
            section.game_ordinal,
            section.physical_replica_count,
        )
        for section in sorted(sections, key=lambda item: item.section_id)
    )
    inventory = bootstrap.Inventory(tuple(entries), 1 if r3 else 0)
    inventory_payload = bootstrap.encode_inventory(inventory)
    if len(inventory_payload) != inventory_length:
        _fail("inventory-fixed-point")
    sections.append(
        _Section(
            1,
            1,
            128,
            1 if r3 else 2,
            (),
            inventory_payload,
            "section:0000000001",
            physical_replica_count=5 if r3 else 1,
            section_version=1 if r3 else 0,
        )
    )
    ordered = tuple(sorted(sections, key=lambda item: item.section_id))
    if len({item.section_id for item in ordered}) != len(ordered):
        _fail("section-id")
    if r3:
        factor_five = {
            item.section_id for item in ordered if item.physical_replica_count == 5
        }
        required = {
            item.section_id for item in ordered if item.closure_class == 128
        }
        if factor_five != {1, 2, 3, 16} or required != {1, 2, 3, 16}:
            _fail("required-spine")
    return ordered


def _encode_units(
    profile: m2_codec.CandidateProfile,
    sections: tuple[_Section, ...],
) -> tuple[tuple[_Unit, ...], dict[int, bytes], dict[int, capacity.SectionCharge]]:
    check_id = 1 if profile.check_bytes == 4 else 2
    units = []
    envelopes = {}
    charges = {}
    for section in sections:
        envelope = bootstrap.encode_section_envelope(
            bootstrap.SectionEnvelope(
                section.section_id,
                section.section_type,
                section.section_version,
                section.closure_class,
                check_id,
                section.dependencies,
                section.payload,
            )
        )
        charge = _section_charge(
            len(section.payload),
            len(section.dependencies),
            check_id,
            section.copy_count,
        )
        if len(envelope) != charge.envelope_length:
            _fail("section-charge")
        envelopes[section.section_id] = envelope
        charges[section.section_id] = charge
    if _is_r3(profile):
        for section in sorted(sections, key=lambda item: item.section_id):
            owner_kind = {
                1: "real-protected",
                2: "real-protected",
                3: "real-protected",
                4: "capacity-probe",
                5: "reserve-probe",
                6: "load-probe",
            }[section.section_type]
            blocks = bootstrap.fragment_section(
                envelopes[section.section_id], profile.profile_version, 0
            )
            for fragment_index, block in enumerate(blocks):
                encoded = m2_codec.eh72_encode_unit(block)
                for replica_index in range(section.physical_replica_count):
                    units.append(
                        _Unit(
                            len(units) + 1,
                            section.section_id,
                            0,
                            fragment_index,
                            encoded,
                            owner_kind,
                            replica_index,
                            section.physical_replica_count,
                        )
                    )
        return tuple(units), envelopes, charges
    for semantic_copy_id in range(max(section.copy_count for section in sections)):
        for section in sections:
            if semantic_copy_id >= section.copy_count:
                continue
            owner_kind = {
                1: "real-protected",
                2: "real-protected",
                3: "real-protected",
                4: "capacity-probe",
                5: "reserve-probe",
                6: "load-probe",
            }[section.section_type]
            blocks = bootstrap.fragment_section(
                envelopes[section.section_id],
                profile.profile_version,
                semantic_copy_id,
            )
            for fragment_index, block in enumerate(blocks):
                encoded = (
                    m2_codec.eh72_encode_unit(block)
                    if profile.transport_id in (
                        m2_codec.EH_TRANSPORT,
                        m2_codec.HIER_TRANSPORT,
                    )
                    else m2_codec.rs255_191_encode(block)
                )
                units.append(
                    _Unit(
                        len(units) + 1,
                        section.section_id,
                        semantic_copy_id,
                        fragment_index,
                        encoded,
                        owner_kind,
                    )
                )
    return tuple(units), envelopes, charges


def _shell_counts(routes: m2_route_data.RouteImageSet) -> tuple[dict[str, int], list[dict[str, object]]]:
    counts = {
        "instruction": 0,
        "example": 0,
        "recipe": 0,
        "headroom": 0,
        "fixed-pad": 0,
    }
    rows = []
    for sector in routes.sectors:
        for span in sector.spans:
            if span.owner.startswith(("worked:", "held-out:")):
                counts["example"] += span.cell_count
            elif span.owner.startswith("recipe-package:"):
                counts["recipe"] += span.cell_count
            elif span.owner.startswith("headroom"):
                counts["headroom"] += span.cell_count
            elif span.owner == "fixed-pad":
                counts["fixed-pad"] += span.cell_count
            else:
                counts["instruction"] += span.cell_count
        rows.append(
            {
                "sector_id": sector.sector_id,
                "route_prefix_cells": sector.route_prefix_cells,
                "headroom_cells": sector.headroom_cells,
                "fixed_pad_cells": next(
                    (span.cell_count for span in sector.spans if span.owner == "fixed-pad"),
                    0,
                ),
                "image_sha256": sha256(sector.data).hexdigest(),
            }
        )
    return counts, rows


def _regularity(
    matrix: bytearray, side: int, width: int
) -> dict[str, int]:
    interior = side - 2 * width
    rows = [
        bytes(matrix[(width + row) * side + width : (width + row) * side + width + interior])
        for row in range(interior)
    ]
    horizontal = 0
    for row in rows:
        run = 0
        previous = -1
        for value in row:
            run = run + 1 if value == previous else 1
            previous = value
            horizontal = max(horizontal, run)
    vertical = 0
    running = [0] * interior
    previous = [-1] * interior
    for row in rows:
        for column, value in enumerate(row):
            running[column] = running[column] + 1 if value == previous[column] else 1
            previous[column] = value
            vertical = max(vertical, running[column])
    tile_counts = [
        sum(
            rows[row + subrow][column + subcolumn]
            for subrow in range(32)
            for subcolumn in range(32)
        )
        for row in range(0, interior - 31, 32)
        for column in range(0, interior - 31, 32)
    ]
    if not tile_counts:
        _fail("density-tiles")
    repeated_rows = len(rows) - len(set(rows))
    columns = [bytes(row[column] for row in rows) for column in range(interior)]
    repeated_columns = len(columns) - len(set(columns))
    return {
        "longest_horizontal_equal_run": horizontal,
        "longest_vertical_equal_run": vertical,
        "tile_one_count_min": min(tile_counts),
        "tile_one_count_max": max(tile_counts),
        "repeated_row_count": repeated_rows,
        "repeated_column_count": repeated_columns,
    }


def _realism_failures(
    scopes: dict[str, list[int]],
    regularity: dict[str, int],
    interior_side: int,
    policy_document: dict[str, object],
) -> tuple[str, ...]:
    realism = policy_document.get("realism")
    if type(realism) is not dict:
        _fail("realism-owner")
    required = (
        "global_one_fraction_min_numerator",
        "global_one_fraction_min_denominator",
        "global_one_fraction_max_numerator",
        "global_one_fraction_max_denominator",
        "tile_side",
        "tile_one_count_min",
        "tile_one_count_max",
    )
    if (
        realism.get("global_one_fraction_scope") != "complete-interior"
        or any(type(realism.get(key)) is not int for key in required)
    ):
        _fail("realism-owner")
    count, ones = scopes["complete-interior"]
    minimum_numerator = realism["global_one_fraction_min_numerator"]
    minimum_denominator = realism["global_one_fraction_min_denominator"]
    maximum_numerator = realism["global_one_fraction_max_numerator"]
    maximum_denominator = realism["global_one_fraction_max_denominator"]
    if minimum_denominator <= 0 or maximum_denominator <= 0 or realism["tile_side"] != 32:
        _fail("realism-owner")
    failures = []
    if count == 0:
        failures.append("complete-interior-empty")
    else:
        if ones * minimum_denominator < count * minimum_numerator:
            failures.append("global-one-fraction-below-minimum")
        if ones * maximum_denominator > count * maximum_numerator:
            failures.append("global-one-fraction-above-maximum")
    if regularity["tile_one_count_min"] < realism["tile_one_count_min"]:
        failures.append("tile-one-count-below-minimum")
    if regularity["tile_one_count_max"] > realism["tile_one_count_max"]:
        failures.append("tile-one-count-above-maximum")
    run_limit = max(128, (interior_side + 3) // 4)
    if regularity["longest_horizontal_equal_run"] > run_limit:
        failures.append("horizontal-equal-run-above-maximum")
    if regularity["longest_vertical_equal_run"] > run_limit:
        failures.append("vertical-equal-run-above-maximum")
    repeated_limit = max(2, interior_side // 32)
    if regularity["repeated_row_count"] > repeated_limit:
        failures.append("repeated-row-count-above-maximum")
    if regularity["repeated_column_count"] > repeated_limit:
        failures.append("repeated-column-count-above-maximum")
    return tuple(failures)


def evaluate_realism(
    density_ledger_raw: bytes, profile_policy_raw: bytes
) -> RealismEvaluation:
    """Evaluate the frozen realism gate without suppressing losing evidence."""

    try:
        m2_policy.load_profile_policy(profile_policy_raw)
        policy_document = tomllib.loads(profile_policy_raw.decode("utf-8"))
        value = canonical_manifest.validate_canonical_manifest(density_ledger_raw)
    except (TypeError, ValueError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise CarrierError("realism-input") from error
    if set(value) != {
        "schema", "profile_id", "carrier_sha256", "scope_rows", "interior_regularity"
    } or value.get("schema") != DENSITY_SCHEMA:
        _fail("realism-ledger")
    scope_rows = value.get("scope_rows")
    regularity = value.get("interior_regularity")
    if type(scope_rows) is not list or type(regularity) is not dict:
        _fail("realism-ledger")
    expected_scope_ids = (
        "shell", "real-protected", "capacity-probe", "reserve-probe",
        "load-probe", "fixed-pad", "complete-interior"
    )
    if tuple(row.get("scope_id") for row in scope_rows if type(row) is dict) != expected_scope_ids:
        _fail("realism-ledger")
    complete = scope_rows[-1]
    if type(complete) is not dict:
        _fail("realism-ledger")
    scalar_keys = (
        "cell_count", "zero_count", "one_count", "one_density_ppm"
    )
    regularity_keys = (
        "longest_horizontal_equal_run", "longest_vertical_equal_run",
        "tile_one_count_min", "tile_one_count_max", "repeated_row_count",
        "repeated_column_count"
    )
    if (
        any(type(complete.get(key)) is not int for key in scalar_keys)
        or set(regularity) != set(regularity_keys)
        or any(type(regularity.get(key)) is not int for key in regularity_keys)
    ):
        _fail("realism-ledger")
    count = complete["cell_count"]
    zeros = complete["zero_count"]
    ones = complete["one_count"]
    density_ppm = complete["one_density_ppm"]
    interior_side = isqrt(count)
    if (
        interior_side * interior_side != count
        or zeros + ones != count
        or density_ppm != (0 if count == 0 else ones * 1_000_000 // count)
    ):
        _fail("realism-ledger")
    metrics = {key: int(regularity[key]) for key in regularity_keys}
    failures = _realism_failures(
        {"complete-interior": [count, ones]},
        metrics,
        interior_side,
        policy_document,
    )
    return RealismEvaluation(
        "pass" if not failures else "fail",
        failures,
        count,
        ones,
        density_ppm,
        metrics["tile_one_count_min"],
        metrics["tile_one_count_max"],
        metrics["longest_horizontal_equal_run"],
        metrics["longest_vertical_equal_run"],
        metrics["repeated_row_count"],
        metrics["repeated_column_count"],
    )


def build_manifestation(
    profile: m2_codec.CandidateProfile,
    profile_policy_raw: bytes,
    profile_limits_raw: bytes,
    damage_policy_raw: bytes,
    bootstrap_spec_raw: bytes,
    compiled: m2_slice.SliceCompilation,
    inputs: capacity.CapacityInputs,
    envelope: capacity.CapacityEnvelope,
    route_manifest_raw: bytes,
    recipient_package: bytes,
    *,
    r3_owner_proof: R3CarrierOwnerProof | None = None,
) -> Manifestation:
    """Build one complete P6 survivor manifestation without damage/selection."""

    if (
        type(profile) is not m2_codec.CandidateProfile
        or (
            profile.profile_version not in (1, 3)
            and not (_is_r3(profile) and profile.protected_units > 0)
        )
    ):
        _fail("gate-two-survivor")
    admission = _admit_owners(
        profile,
        profile_policy_raw,
        profile_limits_raw,
        damage_policy_raw,
        bootstrap_spec_raw,
        inputs,
        route_manifest_raw if _is_r3(profile) else None,
        r3_owner_proof,
    )
    policy = admission.inherited_policy
    semantic_raw = render_semantic_envelope(compiled, inputs, envelope)
    semantic = canonical_manifest.validate_canonical_manifest(semantic_raw)
    if sha256(semantic_raw).hexdigest() != admission.semantic_envelope_sha256:
        _fail("semantic-identity")
    candidate, route_parts, route_owners, headrooms = _shell_blueprint(
        route_manifest_raw, profile, recipient_package
    )
    lower_bound = _lower_bound_value(
        profile,
        profile_policy_raw,
        profile_limits_raw,
        semantic_raw,
        semantic,
        inputs,
        route_parts,
        policy.side_max,
    )
    if _is_r3(profile):
        _reconcile_r3_lower_bound(admission, lower_bound)
    if lower_bound["result"] == "lower-bound-exceeds-hard-ceiling":
        _fail("eliminated-lower-bound")
    side, width, load_fragments, load_payloads, interior_pad = _choose_geometry(
        profile, inputs, semantic, route_parts, headrooms
    )
    if _is_r3(profile):
        projection = derive_r3_capacity_projection(
            profile, side, width, inputs, semantic
        )
        _reconcile_r3_capacity_projection(
            admission, profile, projection, side, width
        )
    routes = m2_route_data._assemble_route_images(
        candidate, route_parts, route_owners, side, width
    )
    capacity_rows = semantic["capacity_section_rows"]
    if type(capacity_rows) is not list:
        _fail("semantic-capacity-row")
    payload_fill_length = (
        sum(row[7] for row in capacity_rows)
        + RESERVE_PAYLOAD_BYTES
        + sum(load_payloads)
    )
    fill = _fill(
        payload_fill_length + (interior_pad + 7) // 8,
        inputs.slice_semantic_sha256,
    )
    sections = _build_sections(
        profile,
        compiled,
        inputs,
        semantic,
        load_payloads,
        fill,
    )
    units, encoded_envelopes, charges = _encode_units(profile, sections)
    if _is_r3(profile):
        _reconcile_r3_realization(
            admission,
            profile,
            sections,
            units,
            encoded_envelopes,
            charges,
        )
    if tuple(
        _section_charge(len(section.payload), len(section.dependencies), 1 if profile.check_bytes == 4 else 2, section.copy_count).fragments_per_copy
        for section in sections
        if section.section_type == 6
    ) != load_fragments:
        _fail("load-realization")

    interior = side - 2 * width
    population = interior * interior
    unit_bits = profile.protected_unit_bytes * 8
    protected_bits = len(units) * unit_bits
    if protected_bits + interior_pad != population:
        _fail("interior-reconciliation")
    mapping = mapping_parameters(profile, side, width, len(units))
    multiplier = 0 if _is_r3(profile) else int(mapping["multiplier"])
    offset = int(mapping["offset"])
    matrix = bytearray(side * side)
    owner_kind = bytearray(side * side)
    owner_id = array("I", [0]) * (side * side)
    owner_offset = array("I", [0]) * (side * side)

    for sector in routes.sectors:
        sector_bits = _bits(sector.data)
        for local, bit in enumerate(sector_bits):
            row, column = bootstrap.sector_cell(side, width, sector.sector_id, local)
            at = row * side + column
            if owner_kind[at]:
                _fail("shell-overlap")
            matrix[at] = bit
            if local < sector.route_prefix_cells:
                kind, owned_offset = 1, local
            elif local < sector.route_prefix_cells + sector.headroom_cells:
                kind, owned_offset = 2, local - sector.route_prefix_cells
            else:
                kind, owned_offset = 3, local - sector.route_prefix_cells - sector.headroom_cells
            owner_kind[at] = kind
            owner_id[at] = sector.sector_id
            owner_offset[at] = owned_offset

    unit_by_id = {unit.unit_id: unit for unit in units}
    for unit in units:
        encoded_bits = _bits(unit.encoded)
        if len(encoded_bits) != unit_bits:
            _fail("unit-width")
        for bit_offset, bit in enumerate(encoded_bits):
            if _is_r3(profile):
                physical = map_unit_bit(mapping, unit.unit_id, bit_offset)
            else:
                logical = (unit.unit_id - 1) * unit_bits + bit_offset
                physical = (multiplier * logical + offset) % population
            row, column = divmod(physical, interior)
            at = (row + width) * side + column + width
            if owner_kind[at]:
                _fail("interior-overlap")
            matrix[at] = bit
            owner_kind[at] = 4
            owner_id[at] = unit.unit_id
            owner_offset[at] = bit_offset
    pad_bits = _bits(fill[payload_fill_length:])[:interior_pad]
    pad_offset = 0
    for row in range(interior):
        for column in range(interior):
            at = (row + width) * side + column + width
            if owner_kind[at]:
                continue
            if pad_offset >= len(pad_bits):
                _fail("interior-pad-short")
            matrix[at] = pad_bits[pad_offset]
            owner_kind[at] = 5
            owner_offset[at] = pad_offset
            pad_offset += 1
    if pad_offset != interior_pad:
        _fail("interior-pad-count")
    if 0 in owner_kind:
        _fail("ownership-gap")

    carrier = len(matrix).to_bytes(4, "big") + _packed(matrix)
    carrier_sha = sha256(carrier).hexdigest()
    shell_counts, shell_rows = _shell_counts(routes)
    section_by_id = {section.section_id: section for section in sections}
    section_rows = []
    logical_rows = []
    for section in sections:
        charge = charges[section.section_id]
        if _is_r3(profile):
            section_row = {
                "section_id": section.section_id,
                "section_type": section.section_type,
                "closure_class": section.closure_class,
                "check_id": 1,
                "semantic_copy_count": section.copy_count,
                "physical_replica_count": section.physical_replica_count,
                "copy_class": (
                    "required-spine"
                    if section.section_id in (1, 2, 3, 16)
                    else "replicated-m2"
                    if section.physical_replica_count == 2
                    else "nonreplicated-m2"
                ),
                "dependency_ids": list(section.dependencies),
                "logical_payload_bytes": len(section.payload),
                "envelope_bytes": len(encoded_envelopes[section.section_id]),
                "fragment_count": charge.fragments_per_copy,
            }
            logical_row = {
                "owner_id": section.owner_id,
                "section_type": section.section_type,
                "closure_class": section.closure_class,
                "semantic_copy_count": section.copy_count,
                "physical_replica_count": section.physical_replica_count,
                "logical_bytes": len(section.payload),
            }
        else:
            section_row = {
                "section_id": section.section_id,
                "section_type": section.section_type,
                "closure_class": section.closure_class,
                "check_id": 1 if profile.check_bytes == 4 else 2,
                "copy_count": section.copy_count,
                "dependency_ids": list(section.dependencies),
                "logical_payload_bytes": len(section.payload),
                "envelope_bytes": len(encoded_envelopes[section.section_id]),
                "fragment_count": charge.fragments_per_copy,
            }
            logical_row = {
                "owner_id": section.owner_id,
                "section_type": section.section_type,
                "closure_class": section.closure_class,
                "copy_count": section.copy_count,
                "logical_bytes": len(section.payload),
            }
        section_rows.append(section_row)
        logical_rows.append(logical_row)
    unit_rows = []
    ownership_unit_rows = []
    for unit in units:
        unit_row = {
            "physical_unit_id": unit.unit_id,
            "section_id": unit.section_id,
            "semantic_copy_id": unit.semantic_copy_id,
            "fragment_index": unit.fragment_index,
            "transport_id": profile.transport_id,
            "encoded_bytes": len(unit.encoded),
            "encoded_sha256": sha256(unit.encoded).hexdigest(),
            "logical_bit_first": (
                1728
                * (
                    int(mapping["unit_multiplier"])
                    * (unit.unit_id - 1)
                    % len(units)
                )
                if _is_r3(profile)
                else (unit.unit_id - 1) * unit_bits
            ),
            "logical_bit_count": unit_bits,
        }
        if _is_r3(profile):
            unit_row.update(
                {
                    "replica_index": unit.replica_index,
                    "physical_replica_count": unit.physical_replica_count,
                    "slot": int(unit_row["logical_bit_first"]) // 1728,
                }
            )
            mapped_cells = tuple(
                map_unit_bit(mapping, unit.unit_id, bit_offset)
                for bit_offset in range(1_728)
            )
            if (
                len(set(mapped_cells)) != 1_728
                or any(not 0 <= value < population for value in mapped_cells)
            ):
                _fail("unit-cell-set")
            ownership_unit_rows.append(
                {
                    "physical_unit_id": unit.unit_id,
                    "section_id": unit.section_id,
                    "fragment_index": unit.fragment_index,
                    "replica_index": unit.replica_index,
                    "physical_replica_count": unit.physical_replica_count,
                    "slot": unit_row["slot"],
                    "logical_bit_first": unit_row["logical_bit_first"],
                    "logical_bit_count": unit_bits,
                    "mapped_cell_sha256": sha256(
                        b"".join(
                            value.to_bytes(4, "big") for value in mapped_cells
                        )
                    ).hexdigest(),
                }
            )
        unit_rows.append(unit_row)
    def physical_witnesses(section: _Section) -> int:
        return section.copy_count * section.physical_replica_count

    envelope_header_bytes = sum(
        physical_witnesses(section) * (18 + 4 * len(section.dependencies))
        for section in sections
    )
    section_check_bytes = sum(
        physical_witnesses(section) * profile.check_bytes for section in sections
    )
    fragment_zero_pad = 157 * len(units) - sum(
        physical_witnesses(section) * len(encoded_envelopes[section.section_id])
        for section in sections
    )
    real_cells = sum(
        unit_bits for unit in units if section_by_id[unit.section_id].section_type <= 3
    )
    capacity_cells = sum(
        unit_bits for unit in units if section_by_id[unit.section_id].section_type == 4
    )
    reserve_cells = sum(
        unit_bits for unit in units if section_by_id[unit.section_id].section_type == 5
    )
    load_cells = sum(
        unit_bits for unit in units if section_by_id[unit.section_id].section_type == 6
    )
    package = bootstrap.decode_recipe_package(recipient_package, profile.profile_version)
    decoder = next(item for item in package.recipes if item.recipe_id == 30)
    repetition = (
        next(item for item in package.recipes if item.recipe_id == 113)
        if _is_r3(profile)
        else None
    )
    repeated_groups = sum(
        charges[section.section_id].fragments_per_copy
        for section in sections
        if section.physical_replica_count > 1
    )
    ledger = {
        "logical_bytes_by_owner": sorted(logical_rows, key=lambda row: row["owner_id"]),
        "envelope_bytes": envelope_header_bytes,
        "fragment_header_bytes": 30 * len(units),
        "fragment_zero_pad_bytes": fragment_zero_pad,
        "local_check_bytes": 4 * len(units),
        "section_check_bytes": section_check_bytes,
        "transport_pad_bytes": len(units),
        "parity_bytes": 24 * len(units),
        "shell_instruction_cells": shell_counts["instruction"],
        "shell_example_cells": shell_counts["example"],
        "shell_recipe_cells": shell_counts["recipe"],
        "shell_headroom_cells": shell_counts["headroom"],
        "shell_fixed_pad_cells": shell_counts["fixed-pad"],
        "real_protected_cells": real_cells,
        "capacity_probe_cells": capacity_cells,
        "reserve_probe_cells": reserve_cells,
        "load_probe_cells": load_cells,
        "interior_fixed_pad_cells": interior_pad,
        "protected_unit_count": len(units),
        "codeword_count": 24 * len(units),
        "worst_case_section_attempts": max(section.copy_count for section in sections),
        "worst_case_work_units": (
            len(units) * 24 * decoder.primitive_steps
            + repeated_groups
            * (
                24 * decoder.primitive_steps
                + 1_728 * repetition.primitive_steps
            )
            if _is_r3(profile)
            else len(units) * 24 * decoder.primitive_steps
        ),
        "scratch_bytes": package.peak_live_scratch_bytes,
        "unused_cells": 0,
        "total_cells": side * side,
    }
    common_reconciled = (
        sum(
            physical_witnesses(section) * len(section.payload)
            for section in sections
        )
        + envelope_header_bytes
        + section_check_bytes
        + ledger["fragment_header_bytes"]
        + fragment_zero_pad
        + ledger["local_check_bytes"]
        + ledger["transport_pad_bytes"]
        + ledger["parity_bytes"]
    )
    if common_reconciled != sum(len(unit.encoded) for unit in units):
        _fail("byte-ledger")
    if (
        sum(
            ledger[key]
            for key in (
                "shell_instruction_cells",
                "shell_example_cells",
                "shell_recipe_cells",
                "shell_headroom_cells",
                "shell_fixed_pad_cells",
                "real_protected_cells",
                "capacity_probe_cells",
                "reserve_probe_cells",
                "load_probe_cells",
                "interior_fixed_pad_cells",
            )
        )
        != side * side
    ):
        _fail("cell-ledger")

    table_hash = sha256()
    chunk = bytearray()
    for index in range(side * side):
        chunk.extend(
            bytes((owner_kind[index],))
            + int(owner_id[index]).to_bytes(4, "big")
            + int(owner_offset[index]).to_bytes(4, "big")
        )
        if len(chunk) >= 9 * 4_096:
            table_hash.update(chunk)
            chunk.clear()
    table_hash.update(chunk)
    ownership_value = {
        "schema": (
            "golden-board.m2-ownership-ledger/v1"
            if _is_r3(profile)
            else OWNERSHIP_SCHEMA
        ),
        "profile_id": profile.profile_id,
        "side": side,
        "shell_width": width,
        "mapping": mapping,
        "shell_rows": shell_rows,
        "unit_rows": ownership_unit_rows if _is_r3(profile) else unit_rows,
        "interior_fixed_pad": {
            "logical_bit_first": protected_bits,
            "logical_bit_count": interior_pad,
            "fill_order": "unoccupied-interior-cells-in-physical-row-major-order",
        },
        "cell_table": {
            "row_bytes": 9,
            "row_count": side * side,
            "row_order": "canonical-matrix-row-major",
            "owner_kind_ids": [
                "1-shell-route",
                "2-shell-headroom",
                "3-shell-fixed-pad",
                "4-protected-unit",
                "5-interior-fixed-pad",
            ],
            "owner_id_rule": "sector-id-for-shell-kinds-physical-unit-id-for-protected-unit-zero-for-interior-fixed-pad",
            "owner_bit_offset_rule": "zero-based-offset-within-named-owner",
        },
        "cell_table_sha256": table_hash.hexdigest(),
    }
    ownership_raw = canonical_manifest.serialize_manifest(ownership_value)

    scopes = {name: [0, 0] for name in (
        "shell", "real-protected", "capacity-probe", "reserve-probe",
        "load-probe", "fixed-pad", "complete-interior"
    )}
    for index, bit in enumerate(matrix):
        kind = owner_kind[index]
        names = []
        if kind in (1, 2, 3):
            names.append("shell")
        if kind == 3 or kind == 5:
            names.append("fixed-pad")
        if kind in (4, 5):
            names.append("complete-interior")
        if kind == 4:
            names.append(unit_by_id[int(owner_id[index])].owner_kind)
        for name in names:
            scopes[name][0] += 1
            scopes[name][1] += bit
    scope_rows = []
    for name, (count, ones) in scopes.items():
        scope_rows.append(
            {
                "scope_id": name,
                "cell_count": count,
                "zero_count": count - ones,
                "one_count": ones,
                "one_density_ppm": 0 if count == 0 else ones * 1_000_000 // count,
            }
        )
    regularity = _regularity(matrix, side, width)
    density_value = {
        "schema": DENSITY_SCHEMA,
        "profile_id": profile.profile_id,
        "carrier_sha256": carrier_sha,
        "scope_rows": scope_rows,
        "interior_regularity": regularity,
    }
    density_raw = canonical_manifest.serialize_manifest(density_value)
    capacity_value = {
        "schema": (
            "golden-board.m2-capacity-ledger/v1"
            if _is_r3(profile)
            else CAPACITY_SCHEMA
        ),
        "profile_id": profile.profile_id,
        "carrier_sha256": carrier_sha,
        "section_rows": section_rows,
        "unit_rows": unit_rows,
        "ledger": ledger,
    }
    capacity_raw = canonical_manifest.serialize_manifest(capacity_value)
    candidate_value = {
        "schema": (
            "golden-board.m2-candidate-manifest/v1"
            if _is_r3(profile)
            else CANDIDATE_SCHEMA
        ),
        "profile_policy_sha256": sha256(profile_policy_raw).hexdigest(),
        "profile_limits_sha256": sha256(profile_limits_raw).hexdigest(),
        "bootstrap_spec_sha256": sha256(bootstrap_spec_raw).hexdigest(),
        **(
            {
                "route_data_sha256": sha256(route_manifest_raw).hexdigest(),
                "recipient_package_sha256": sha256(recipient_package).hexdigest(),
            }
            if _is_r3(profile)
            else {}
        ),
        "profile_id": profile.profile_id,
        "profile_version": profile.profile_version,
        "semantic_envelope_sha256": sha256(semantic_raw).hexdigest(),
        "side": side,
        "shell_width": width,
        "mapping": mapping,
        "shell_rows": shell_rows,
        "section_rows": section_rows,
        "unit_rows": unit_rows,
        "ownership_sha256": sha256(ownership_raw).hexdigest(),
        "capacity_ledger_sha256": sha256(capacity_raw).hexdigest(),
        "density_ledger_sha256": sha256(density_raw).hexdigest(),
        "carrier_sha256": carrier_sha,
        "ledger": ledger,
    }
    omitted = canonical_manifest.serialize_manifest(candidate_value)
    candidate_value["manifest_identity"] = identity.identity_hex(
        b"golden-board:manifest:v0\0", (omitted,)
    )
    candidate_raw = canonical_manifest.serialize_manifest(candidate_value)
    return Manifestation(
        profile.profile_id,
        semantic_raw,
        carrier,
        candidate_raw,
        ownership_raw,
        capacity_raw,
        density_raw,
    )


def build_p6_outcome(
    profile: m2_codec.CandidateProfile,
    profile_policy_raw: bytes,
    profile_limits_raw: bytes,
    damage_policy_raw: bytes,
    bootstrap_spec_raw: bytes,
    compiled: m2_slice.SliceCompilation,
    inputs: capacity.CapacityInputs,
    envelope: capacity.CapacityEnvelope,
    route_manifest_raw: bytes,
    recipient_package: bytes,
    *,
    r3_owner_proof: R3CarrierOwnerProof | None = None,
) -> P6Outcome:
    """Return exactly a manifestation or its checked gate-5 elimination."""

    if type(profile) is not m2_codec.CandidateProfile:
        _fail("gate-two-survivor")
    if profile.profile_version not in (1, 3) and not _is_r3(profile):
        _fail("gate-two-survivor")
    manifestation = build_manifestation(
        profile,
        profile_policy_raw,
        profile_limits_raw,
        damage_policy_raw,
        bootstrap_spec_raw,
        compiled,
        inputs,
        envelope,
        route_manifest_raw,
        recipient_package,
        r3_owner_proof=r3_owner_proof,
    )
    realism_policy_raw = (
        r3_owner_proof.inherited_profile_policy_raw
        if _is_r3(profile) and type(r3_owner_proof) is R3CarrierOwnerProof
        else profile_policy_raw
    )
    realism = evaluate_realism(
        manifestation.density_ledger, realism_policy_raw
    )
    return P6Outcome(
        profile.profile_id,
        realism.result,
        None if realism.result == "pass" else realism.failure_reasons[0],
        None,
        manifestation,
    )


def validate_elimination_bound(
    expected: bytes,
    profile: m2_codec.CandidateProfile,
    profile_policy_raw: bytes,
    profile_limits_raw: bytes,
    damage_policy_raw: bytes,
    bootstrap_spec_raw: bytes,
    compiled: m2_slice.SliceCompilation,
    inputs: capacity.CapacityInputs,
    envelope: capacity.CapacityEnvelope,
    route_manifest_raw: bytes,
    recipient_package: bytes,
) -> None:
    """Rebuild and byte-compare one bounded lower-bound artifact."""

    if type(expected) is not bytes:
        _fail("elimination-bound-mismatch")
    try:
        value = canonical_manifest.validate_canonical_manifest(expected)
    except (TypeError, ValueError) as error:
        raise CarrierError("elimination-bound-mismatch") from error
    if (
        value.get("schema") != ELIMINATION_SCHEMA
        or value.get("profile_id") != profile.profile_id
        or value.get("profile_policy_sha256") != sha256(profile_policy_raw).hexdigest()
        or value.get("profile_limits_sha256") != sha256(profile_limits_raw).hexdigest()
        or value.get("result") != "lower-bound-exceeds-hard-ceiling"
        or expected != render_elimination_bound(
        profile,
        profile_policy_raw,
        profile_limits_raw,
        damage_policy_raw,
        bootstrap_spec_raw,
        compiled,
        inputs,
        envelope,
        route_manifest_raw,
        recipient_package,
        )
    ):
        _fail("elimination-bound-mismatch")


def validate_manifestation(
    expected: Manifestation,
    profile: m2_codec.CandidateProfile,
    profile_policy_raw: bytes,
    profile_limits_raw: bytes,
    damage_policy_raw: bytes,
    bootstrap_spec_raw: bytes,
    compiled: m2_slice.SliceCompilation,
    inputs: capacity.CapacityInputs,
    envelope: capacity.CapacityEnvelope,
    route_manifest_raw: bytes,
    recipient_package: bytes,
    *,
    r3_owner_proof: R3CarrierOwnerProof | None = None,
) -> None:
    """Rebuild and byte-compare all six complete manifestation artifacts."""

    if type(expected) is not Manifestation or any(
        type(raw) is not bytes
        for raw in (
            expected.semantic_envelope,
            expected.carrier,
            expected.candidate_manifest,
            expected.ownership_ledger,
            expected.capacity_ledger,
            expected.density_ledger,
        )
    ):
        _fail("manifestation-mismatch")
    r3 = _is_r3(profile)
    admission = _admit_owners(
        profile,
        profile_policy_raw,
        profile_limits_raw,
        damage_policy_raw,
        bootstrap_spec_raw,
        inputs,
        route_manifest_raw if r3 else None,
        r3_owner_proof,
    )
    try:
        candidate = canonical_manifest.validate_canonical_manifest(
            expected.candidate_manifest
        )
        ownership = canonical_manifest.validate_canonical_manifest(
            expected.ownership_ledger
        )
        capacity_value = canonical_manifest.validate_canonical_manifest(
            expected.capacity_ledger
        )
        density = canonical_manifest.validate_canonical_manifest(
            expected.density_ledger
        )
    except (TypeError, ValueError) as error:
        raise CarrierError("manifestation-mismatch") from error
    common_mismatch = (
        expected.profile_id != profile.profile_id
        or len(expected.carrier) < 4
        or (int.from_bytes(expected.carrier[:4], "big") + 7) // 8
        != len(expected.carrier) - 4
        or candidate.get("profile_id") != profile.profile_id
        or candidate.get("profile_policy_sha256") != sha256(profile_policy_raw).hexdigest()
        or candidate.get("profile_limits_sha256") != sha256(profile_limits_raw).hexdigest()
        or candidate.get("bootstrap_spec_sha256") != sha256(bootstrap_spec_raw).hexdigest()
        or candidate.get("semantic_envelope_sha256") != sha256(expected.semantic_envelope).hexdigest()
        or candidate.get("carrier_sha256") != sha256(expected.carrier).hexdigest()
        or candidate.get("ownership_sha256") != sha256(expected.ownership_ledger).hexdigest()
        or candidate.get("capacity_ledger_sha256") != sha256(expected.capacity_ledger).hexdigest()
        or candidate.get("density_ledger_sha256") != sha256(expected.density_ledger).hexdigest()
        or ownership.get("mapping") != candidate.get("mapping")
        or ownership.get("shell_rows") != candidate.get("shell_rows")
        or ownership.get("profile_id") != profile.profile_id
        or ownership.get("side") != candidate.get("side")
        or ownership.get("shell_width") != candidate.get("shell_width")
        or capacity_value.get("profile_id") != profile.profile_id
        or capacity_value.get("carrier_sha256") != candidate.get("carrier_sha256")
        or capacity_value.get("section_rows") != candidate.get("section_rows")
        or capacity_value.get("unit_rows") != candidate.get("unit_rows")
        or density.get("schema") != DENSITY_SCHEMA
        or density.get("profile_id") != profile.profile_id
        or density.get("carrier_sha256") != candidate.get("carrier_sha256")
    )
    if r3:
        candidate_owner = admission.policy_document.get("candidate_manifest")
        ownership_owner = admission.policy_document.get("ownership_ledger")
        capacity_owner = admission.policy_document.get("capacity_ledger")
        if (
            type(candidate_owner) is not dict
            or type(ownership_owner) is not dict
            or type(capacity_owner) is not dict
        ):
            _fail("manifestation-mismatch")
        candidate_keys = candidate_owner.get("top_level_keys")
        mapping_keys = candidate_owner.get("mapping_keys")
        section_keys = candidate_owner.get("section_row_keys")
        unit_keys = candidate_owner.get("unit_row_keys")
        ownership_keys = ownership_owner.get("keys")
        ownership_unit_keys = ownership_owner.get("unit_row_keys")
        capacity_keys = capacity_owner.get("keys")
        if not all(
            type(keys) is list
            and all(type(key) is str for key in keys)
            for keys in (
                candidate_keys,
                mapping_keys,
                section_keys,
                unit_keys,
                ownership_keys,
                ownership_unit_keys,
                capacity_keys,
            )
        ):
            _fail("manifestation-mismatch")
        candidate_sections = candidate.get("section_rows")
        candidate_units = candidate.get("unit_rows")
        ownership_units = ownership.get("unit_rows")
        mapping = candidate.get("mapping")
        shell_rows = candidate.get("shell_rows")
        ledger = candidate.get("ledger")
        inherited = tomllib.loads(
            r3_owner_proof.inherited_profile_policy_raw.decode("utf-8")
        )
        inherited_candidate = inherited.get("candidate_manifest")
        inherited_ownership = inherited.get("ownership_ledger")
        inherited_density = inherited.get("density_ledger")
        if (
            type(inherited_candidate) is not dict
            or type(inherited_ownership) is not dict
            or type(inherited_density) is not dict
        ):
            _fail("manifestation-mismatch")
        shell_keys = inherited_candidate.get("shell_row_keys")
        ledger_owner = inherited_candidate.get("ledger")
        interior_pad_keys = inherited_ownership.get(
            "interior_fixed_pad_keys"
        )
        cell_table_keys = inherited_ownership.get("cell_table_keys")
        density_keys = inherited_density.get("keys")
        density_scope_keys = inherited_density.get("scope_row_keys")
        density_scope_ids = inherited_density.get("scope_ids")
        density_regularity_keys = inherited_density.get(
            "interior_regularity_keys"
        )
        if type(ledger_owner) is not dict:
            _fail("manifestation-mismatch")
        ledger_keys = ledger_owner.get("keys")
        logical_owner_keys = candidate_owner.get("ledger", {}).get(
            "logical_owner_row_keys"
        )
        if not all(
            type(keys) is list
            and all(type(key) is str for key in keys)
            for keys in (
                shell_keys,
                ledger_keys,
                logical_owner_keys,
                interior_pad_keys,
                cell_table_keys,
                density_keys,
                density_scope_keys,
                density_scope_ids,
                density_regularity_keys,
            )
        ):
            _fail("manifestation-mismatch")
        logical_rows = (
            ledger.get("logical_bytes_by_owner")
            if type(ledger) is dict
            else None
        )
        ownership_pad = ownership.get("interior_fixed_pad")
        ownership_table = ownership.get("cell_table")
        density_scopes = density.get("scope_rows")
        density_regularity = density.get("interior_regularity")
        if (
            candidate.get("schema") != candidate_owner.get("schema")
            or set(candidate) != set(candidate_keys)
            or type(mapping) is not dict
            or set(mapping) != set(mapping_keys)
            or type(candidate_sections) is not list
            or any(
                type(row) is not dict or set(row) != set(section_keys)
                for row in candidate_sections
            )
            or [row["section_id"] for row in candidate_sections]
            != sorted(row["section_id"] for row in candidate_sections)
            or type(shell_rows) is not list
            or len(shell_rows) != 4
            or any(
                type(row) is not dict or set(row) != set(shell_keys)
                for row in shell_rows
            )
            or [row["sector_id"] for row in shell_rows] != list(range(4))
            or type(candidate_units) is not list
            or any(
                type(row) is not dict or set(row) != set(unit_keys)
                for row in candidate_units
            )
            or [row["physical_unit_id"] for row in candidate_units]
            != list(range(1, len(candidate_units) + 1))
            or any(row["semantic_copy_id"] != 0 for row in candidate_units)
            or candidate.get("route_data_sha256")
            != sha256(route_manifest_raw).hexdigest()
            or candidate.get("recipient_package_sha256")
            != sha256(recipient_package).hexdigest()
            or type(ledger) is not dict
            or set(ledger) != set(ledger_keys)
            or type(logical_rows) is not list
            or any(
                type(row) is not dict
                or set(row) != set(logical_owner_keys)
                for row in logical_rows
            )
            or [row["owner_id"] for row in logical_rows]
            != sorted(row["owner_id"] for row in logical_rows)
            or ownership.get("schema") != ownership_owner.get("schema")
            or set(ownership) != set(ownership_keys)
            or type(ownership_units) is not list
            or len(ownership_units) != len(candidate_units)
            or any(
                type(row) is not dict
                or set(row) != set(ownership_unit_keys)
                for row in ownership_units
            )
            or type(ownership_pad) is not dict
            or set(ownership_pad) != set(interior_pad_keys)
            or type(ownership_table) is not dict
            or set(ownership_table) != set(cell_table_keys)
            or capacity_value.get("schema") != capacity_owner.get("schema")
            or set(capacity_value) != set(capacity_keys)
            or capacity_value.get("ledger") != candidate.get("ledger")
            or set(density) != set(density_keys)
            or type(density_scopes) is not list
            or any(
                type(row) is not dict or set(row) != set(density_scope_keys)
                for row in density_scopes
            )
            or [row["scope_id"] for row in density_scopes]
            != density_scope_ids
            or type(density_regularity) is not dict
            or set(density_regularity) != set(density_regularity_keys)
        ):
            _fail("manifestation-mismatch")
        ownership_common = (
            "physical_unit_id",
            "section_id",
            "fragment_index",
            "replica_index",
            "physical_replica_count",
            "slot",
            "logical_bit_first",
            "logical_bit_count",
        )
        if any(
            tuple(owner_row[key] for key in ownership_common)
            != tuple(candidate_row[key] for key in ownership_common)
            for candidate_row, owner_row in zip(
                candidate_units, ownership_units, strict=True
            )
        ):
            _fail("manifestation-mismatch")
        omitted_candidate = dict(candidate)
        manifest_identity = omitted_candidate.pop("manifest_identity", None)
        if manifest_identity != identity.identity_hex(
            b"golden-board:manifest:v0\0",
            (canonical_manifest.serialize_manifest(omitted_candidate),),
        ):
            _fail("manifestation-mismatch")
    elif (
        candidate.get("schema") != CANDIDATE_SCHEMA
        or ownership.get("schema") != OWNERSHIP_SCHEMA
        or ownership.get("unit_rows") != candidate.get("unit_rows")
        or capacity_value.get("schema") != CAPACITY_SCHEMA
    ):
        _fail("manifestation-mismatch")
    rebuilt = build_manifestation(
        profile,
        profile_policy_raw,
        profile_limits_raw,
        damage_policy_raw,
        bootstrap_spec_raw,
        compiled,
        inputs,
        envelope,
        route_manifest_raw,
        recipient_package,
        r3_owner_proof=r3_owner_proof,
    )
    if common_mismatch or expected != rebuilt:
        _fail("manifestation-mismatch")
