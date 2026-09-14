"""Independent, fail-closed M2 gate-7 ownership proof.

This module consumes only the retained P6 ownership evidence and the retained
P7 damage manifests.  It does not generate damage, decode observations, or use
clean carrier bytes.  Every proof is a deterministic projection of its exact
bound inputs.
"""

from __future__ import annotations

from array import array
from dataclasses import dataclass
from hashlib import sha256
from math import gcd
from typing import Any, NoReturn, Sequence

from . import canonical_manifest, identity, m2_codec


SCHEMA = "golden-board.m2-independence-proof/v0"
R3_SCHEMA = "golden-board.m2-independence-proof/v1"
_IDENTITY_DOMAIN = b"golden-board:manifest:v0\0"
_SAMPLE_DOMAIN = bytes.fromhex("47422d44414d4147452d763000")
_WINDOW_DOMAIN = bytes.fromhex("47422d44414d4147452d57494e444f572d763000")
_BOUNDARY_SHA256 = "4ad1468cd6cac6774b95e997d37c6fb420ff94cc0aa82595aeaa7b356440a68b"
_PROFILE_POLICY_SHA256 = "c180c2ad312c21e7559a33d9d6aee7ae5ecdc287e94197061242985c57b02265"
_PROFILE_LIMITS_SHA256 = "2047141ec25acc71ba45d39e803203b627d4b1c1823c147b4da361da1b189693"
_DAMAGE_POLICY_SHA256 = "9cbb185dd5d7d3fec1d4ce4aa978fa77d92e7a4ef272c2f038f0ada769c376e4"
_BOOTSTRAP_SPEC_SHA256 = "82c25776871ac48184d5a7f15663bcc1d192618d66df72ff5fbf3a252aa564c2"

# The v1 proof is deliberately a closed proof for the one promoted v7
# manifestation.  These are raw-byte owner bindings, not configurable
# defaults.  A different candidate or owner set needs a new owning contract.
_R3_PROFILE_ID = "eh72-hier-r5-r2-r1-crc32c-v0"
_R3_CANDIDATE_SHA256 = "38839aa28561ff2bec0997a80d8dc938e876526c25f40e23b6a78844f8fc1d86"
_R3_PROFILE_POLICY_SHA256 = "44215d993e3fdfdd1630c404f1ee969e8abc6e4928fda83365fc6940e5cfd412"
_R3_PROFILE_LIMITS_SHA256 = "32c2bd0cb978eb800bed7f8ac1c7db223b593b4cf3bad951a9ce4cdc3a568902"
_R3_DAMAGE_POLICY_SHA256 = "b3b28f00d3ba04addbed4517eb1abb4ecd02796176eaaecdbc1d47f1f39509df"
_R3_BOOTSTRAP_SPEC_SHA256 = "e4d0a5667758a753d35603632dee550db7ecb66cf64ee675ce7485531da27dde"
_R3_ROUTE_DATA_SHA256 = "94df79d9a3fb01b69014417683a0f48f2222fea9fe991361bc99aa0c30dc663e"
_R3_RECIPIENT_PACKAGE_SHA256 = "4bd8e0d485ae6e6a65f4edc4ef2aaac9585a2bcd8c4623e44d69f1dad3b0ec8e"
_R3_BOUNDARY_KAT_IDS = (
    "rep2-correction-boundary",
    "rep5-correction-boundary",
    "complete-section-conflict",
    "section-attempt-ceiling-plus-one",
)
_R3_BOUNDARY_KAT_SHA256 = (
    "452d38bd592174b0fb022cee41e4f261768957811893ae471934bf3e4e8e6622",
    "5158867ec6d4c740afec018f5695a51779ca54758113303d3b656c4b6ee1f01e",
    "9508a43cc54c7f6dc06fcee677a18db1ed57bfdb87e1c5f692d332642a3c5b56",
    "966307a69ded9f055704443e6c6c46b4d0226a4a4bced398e0573fe5afe03187",
)

_PREDICATES = (
    "affine-map-bijection",
    "matrix-owner-total-partition",
    "shell-sector-total-partition",
    "protected-unit-total-partition",
    "owner-class-ledger-reconciliation",
    "semantic-copy-required-dependency-separation",
    "single-sector-route-survival",
    "d2-d4-d6-required-closure-survival",
    "damage-promise-binding",
)
_FLOORS = (1, 1, 1, 1, 1, 2, 3, 1, 1)
_R3_PREDICATES = (
    "two-stage-map-bijection",
    "matrix-owner-total-partition",
    "shell-sector-total-partition",
    "physical-group-total-partition",
    "owner-factor-ledger-reconciliation",
    "final-cell-lane-separation",
    "d2-d4-d6-required-closure-survival",
    "section-dependency-inventory-closure",
    "damage-promise-binding",
)
_R3_WITNESS_COUNTS = (
    3_182_656,
    4_161_600,
    978_944,
    3_181_248,
    4_161_600,
    1_282_176,
    37_844,
    1_362,
    10_038,
)
_R3_FLOORS = (1,) * 9
_FAMILIES = tuple(f"D{index}" for index in range(8))
_GUARANTEES = (
    "all_declared_m2_sections_exact",
    "all_declared_m2_sections_exact",
    "m2_required_closure",
    "m2_required_closure",
    "m2_required_closure",
    "all_declared_m2_sections_exact",
    "m2_required_closure",
    "correct_or_explicit_failure",
)
_SECTION_STATES = frozenset(
    ("verified", "recovered", "incomplete", "corrupt", "ambiguous", "unknown")
)
_ARTIFACT_STATES = frozenset(
    ("exact", "degraded", "failure", "ambiguous", "resource-limit")
)
_HEX = frozenset("0123456789abcdef")
_MAX_U64 = (1 << 64) - 1

_CANDIDATE_KEYS = frozenset(
    (
        "schema",
        "profile_policy_sha256",
        "profile_limits_sha256",
        "bootstrap_spec_sha256",
        "profile_id",
        "profile_version",
        "semantic_envelope_sha256",
        "side",
        "shell_width",
        "mapping",
        "shell_rows",
        "section_rows",
        "unit_rows",
        "ownership_sha256",
        "capacity_ledger_sha256",
        "density_ledger_sha256",
        "carrier_sha256",
        "ledger",
        "manifest_identity",
    )
)
_MAPPING_KEYS = frozenset(
    ("id", "interior_side", "population", "multiplier", "offset", "inverse_multiplier")
)
_SHELL_ROW_KEYS = frozenset(
    ("sector_id", "route_prefix_cells", "headroom_cells", "fixed_pad_cells", "image_sha256")
)
_SECTION_ROW_KEYS = frozenset(
    (
        "section_id",
        "section_type",
        "closure_class",
        "check_id",
        "copy_count",
        "dependency_ids",
        "logical_payload_bytes",
        "envelope_bytes",
        "fragment_count",
    )
)
_UNIT_ROW_KEYS = frozenset(
    (
        "physical_unit_id",
        "section_id",
        "semantic_copy_id",
        "fragment_index",
        "transport_id",
        "encoded_bytes",
        "encoded_sha256",
        "logical_bit_first",
        "logical_bit_count",
    )
)
_LEDGER_KEYS = frozenset(
    (
        "logical_bytes_by_owner",
        "envelope_bytes",
        "fragment_header_bytes",
        "fragment_zero_pad_bytes",
        "local_check_bytes",
        "section_check_bytes",
        "transport_pad_bytes",
        "parity_bytes",
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
        "protected_unit_count",
        "codeword_count",
        "worst_case_section_attempts",
        "worst_case_work_units",
        "scratch_bytes",
        "unused_cells",
        "total_cells",
    )
)
_LOGICAL_OWNER_KEYS = frozenset(
    ("owner_id", "section_type", "closure_class", "copy_count", "logical_bytes")
)
_OWNERSHIP_KEYS = frozenset(
    (
        "schema",
        "profile_id",
        "side",
        "shell_width",
        "mapping",
        "shell_rows",
        "unit_rows",
        "interior_fixed_pad",
        "cell_table",
        "cell_table_sha256",
    )
)
_INTERIOR_PAD_KEYS = frozenset(("logical_bit_first", "logical_bit_count", "fill_order"))
_CELL_TABLE_KEYS = frozenset(
    ("row_bytes", "row_count", "row_order", "owner_kind_ids", "owner_id_rule", "owner_bit_offset_rule")
)
_DAMAGE_KEYS = frozenset(
    (
        "schema",
        "damage_policy_sha256",
        "profile_policy_sha256",
        "profile_id",
        "candidate_manifest_sha256",
        "clean_observation_sha256",
        "family_rows",
        "boundary_kat_rows",
        "summary",
    )
)
_FAMILY_ROW_KEYS = frozenset(
    ("family_id", "case_count", "wrong_accept_count", "result", "case_rows_sha256")
)
_BOUNDARY_ROW_KEYS = frozenset(("kat_id", "result_sha256", "result"))
_DAMAGE_SUMMARY_KEYS = frozenset(
    ("family_case_counts", "wrong_accept_count", "manifest_identity")
)
_FAMILY_COUNT_KEYS = frozenset(("family_id", "case_count"))
_FAMILY_KEYS = frozenset(
    (
        "schema",
        "damage_manifest_identity",
        "profile_id",
        "family_id",
        "guarantee_id",
        "shard_rows",
        "summary",
    )
)
_SHARD_REF_KEYS = frozenset(("shard_ordinal", "case_first", "case_count", "manifest_sha256"))
_FAMILY_SUMMARY_KEYS = frozenset(("case_count", "wrong_accept_count", "result", "manifest_identity"))
_SHARD_KEYS = frozenset(
    (
        "schema",
        "damage_manifest_identity",
        "profile_id",
        "family_id",
        "shard_ordinal",
        "case_first",
        "case_rows",
        "summary",
    )
)
_SHARD_SUMMARY_KEYS = frozenset(("case_count", "wrong_accept_count", "manifest_identity"))
_CASE_KEYS = frozenset(
    (
        "case_id",
        "family_id",
        "channel",
        "operator",
        "parameter_projection",
        "observation_sha256",
        "decoder_result_sha256",
        "expected_artifact_state",
        "expected_section_states",
        "wrong_accept_count",
    )
)
_PARAMETER_KEYS = frozenset(("id", "value_type", "value"))
_SECTION_STATE_KEYS = frozenset(("section_id", "state"))
_PROOF_KEYS = frozenset(
    (
        "schema",
        "profile_id",
        "candidate_manifest_sha256",
        "ownership_ledger_sha256",
        "damage_manifest_sha256",
        "predicate_rows",
        "summary",
    )
)
_PREDICATE_ROW_KEYS = frozenset(
    ("predicate_id", "witness_count", "minimum_surviving_count", "violation_count", "result")
)
_PROOF_SUMMARY_KEYS = frozenset(("predicate_count", "result", "manifest_identity"))

_R3_CANDIDATE_KEYS = frozenset(
    (
        "schema",
        "profile_policy_sha256",
        "profile_limits_sha256",
        "bootstrap_spec_sha256",
        "route_data_sha256",
        "recipient_package_sha256",
        "profile_id",
        "profile_version",
        "semantic_envelope_sha256",
        "side",
        "shell_width",
        "mapping",
        "shell_rows",
        "section_rows",
        "unit_rows",
        "ownership_sha256",
        "capacity_ledger_sha256",
        "density_ledger_sha256",
        "carrier_sha256",
        "ledger",
        "manifest_identity",
    )
)
_R3_MAPPING_KEYS = frozenset(
    (
        "id",
        "interior_side",
        "population",
        "unit_population",
        "unit_multiplier",
        "unit_inverse_multiplier",
        "cell_multiplier",
        "offset",
        "cell_inverse_multiplier",
    )
)
_R3_SECTION_ROW_KEYS = frozenset(
    (
        "section_id",
        "section_type",
        "closure_class",
        "check_id",
        "semantic_copy_count",
        "physical_replica_count",
        "copy_class",
        "dependency_ids",
        "logical_payload_bytes",
        "envelope_bytes",
        "fragment_count",
    )
)
_R3_UNIT_ROW_KEYS = frozenset(
    (
        "physical_unit_id",
        "section_id",
        "semantic_copy_id",
        "fragment_index",
        "replica_index",
        "physical_replica_count",
        "slot",
        "transport_id",
        "encoded_bytes",
        "encoded_sha256",
        "logical_bit_first",
        "logical_bit_count",
    )
)
_R3_OWNERSHIP_UNIT_KEYS = frozenset(
    (
        "physical_unit_id",
        "section_id",
        "fragment_index",
        "replica_index",
        "physical_replica_count",
        "slot",
        "logical_bit_first",
        "logical_bit_count",
        "mapped_cell_sha256",
    )
)
_R3_LOGICAL_OWNER_KEYS = frozenset(
    (
        "owner_id",
        "section_type",
        "closure_class",
        "semantic_copy_count",
        "physical_replica_count",
        "logical_bytes",
    )
)
_R3_DAMAGE_KEYS = frozenset(
    (
        "schema",
        "damage_policy_sha256",
        "profile_policy_sha256",
        "profile_limits_sha256",
        "bootstrap_spec_sha256",
        "route_data_sha256",
        "recipient_package_sha256",
        "profile_id",
        "candidate_manifest_sha256",
        "clean_observation_sha256",
        "family_rows",
        "boundary_kat_rows",
        "summary",
    )
)


class IndependenceError(ValueError):
    """The gate-7 evidence or proof is outside its frozen contract."""

    __slots__ = ("reason",)

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class IndependenceProof:
    raw: bytes
    manifest_identity: str
    result: str
    predicate_rows: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class _Candidate:
    raw: bytes
    value: dict[str, Any]
    profile: m2_codec.CandidateProfile
    side: int
    width: int
    interior: int
    population: int
    unit_bits: int
    protected_bits: int
    sections: tuple[dict[str, Any], ...]
    units: tuple[dict[str, Any], ...]
    section_by_id: dict[int, dict[str, Any]]
    units_by_section_copy: dict[tuple[int, int], tuple[dict[str, Any], ...]]


@dataclass(frozen=True, slots=True)
class _Damage:
    raw: bytes
    value: dict[str, Any]
    cases: dict[str, tuple[dict[str, Any], ...]]
    family_results: dict[str, str]
    boundary_pass: bool


@dataclass(frozen=True, slots=True)
class _CandidateV1:
    raw: bytes
    value: dict[str, Any]
    side: int
    width: int
    interior: int
    population: int
    unit_bits: int
    protected_bits: int
    sections: tuple[dict[str, Any], ...]
    units: tuple[dict[str, Any], ...]
    section_by_id: dict[int, dict[str, Any]]
    unit_by_id: dict[int, dict[str, Any]]
    groups: tuple[tuple[dict[str, Any], ...], ...]
    groups_by_section: dict[int, tuple[tuple[dict[str, Any], ...], ...]]


@dataclass(frozen=True, slots=True)
class _DamageV1:
    raw: bytes
    value: dict[str, Any]
    cases: dict[str, tuple[dict[str, Any], ...]]
    family_results: dict[str, str]
    boundary_pass: bool


def _fail(reason: str) -> NoReturn:
    raise IndependenceError(reason)


def _keys(value: object, expected: frozenset[str], reason: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != expected:
        _fail(reason)
    return value


def _array(value: object, maximum: int, reason: str) -> list[Any]:
    if type(value) is not list or len(value) > maximum:
        _fail(reason)
    return value


def _u64(value: object, reason: str, low: int = 0, high: int = _MAX_U64) -> int:
    if type(value) is not int or not low <= value <= high:
        _fail(reason)
    return value


def _ascii(value: object, reason: str, maximum: int = 128) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value.encode("ascii", "ignore")) <= maximum
        or any(not 0x20 <= ord(character) <= 0x7E for character in value)
    ):
        _fail(reason)
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        _fail(reason)
    return value


def _hex64(value: object, reason: str) -> str:
    if type(value) is not str or len(value) != 64 or any(character not in _HEX for character in value):
        _fail(reason)
    return value


def _canonical(raw: bytes, reason: str) -> dict[str, Any]:
    try:
        value = canonical_manifest.validate_canonical_manifest(raw)
    except (TypeError, ValueError) as error:
        raise IndependenceError(reason) from error
    pending: list[object] = [value]
    while pending:
        item = pending.pop()
        if type(item) is bool:
            _fail(reason)
        if type(item) is dict:
            pending.extend(item.values())
        elif type(item) is list:
            pending.extend(item)
    return value


def _canonical_array_sha256(rows: Sequence[dict[str, Any]]) -> str:
    """Hash an exact canonical bare array one bounded row at a time."""

    digest = sha256()
    digest.update(b"[")
    for index, row in enumerate(rows):
        raw = canonical_manifest.serialize_manifest(row)
        if not raw.endswith(b"\n"):
            _fail("case-row-canonical")
        if index:
            digest.update(b",")
        digest.update(raw[:-1])
    digest.update(b"]")
    return digest.hexdigest()


def _checked_sum(values: Sequence[int], reason: str) -> int:
    total = 0
    for value in values:
        total += value
        if total > _MAX_U64:
            _fail(reason)
    return total


def _profile(profile_id: object, version: object) -> m2_codec.CandidateProfile:
    profiles = {item.profile_id: item for item in m2_codec.candidate_profiles()}
    if type(profile_id) is not str or profile_id not in profiles:
        _fail("candidate-profile")
    profile = profiles[profile_id]
    if version != profile.profile_version:
        _fail("candidate-profile")
    return profile


def _validate_candidate(raw: bytes, ownership_raw: bytes) -> _Candidate:
    value = _keys(_canonical(raw, "candidate-manifest"), _CANDIDATE_KEYS, "candidate-keys")
    if value["schema"] != "golden-board.m2-candidate-manifest/v0":
        _fail("candidate-schema")
    profile = _profile(value["profile_id"], value["profile_version"])
    for name in (
        "profile_policy_sha256",
        "profile_limits_sha256",
        "bootstrap_spec_sha256",
        "semantic_envelope_sha256",
        "ownership_sha256",
        "capacity_ledger_sha256",
        "density_ledger_sha256",
        "carrier_sha256",
    ):
        _hex64(value[name], "candidate-sha256")
    if (
        value["profile_policy_sha256"] != _PROFILE_POLICY_SHA256
        or value["profile_limits_sha256"] != _PROFILE_LIMITS_SHA256
        or value["bootstrap_spec_sha256"] != _BOOTSTRAP_SPEC_SHA256
    ):
        _fail("candidate-owner-binding")
    omitted = dict(value)
    claimed_identity = _hex64(omitted.pop("manifest_identity"), "candidate-identity")
    if claimed_identity != identity.identity_hex(
        _IDENTITY_DOMAIN, (canonical_manifest.serialize_manifest(omitted),)
    ):
        _fail("candidate-identity")
    if value["ownership_sha256"] != sha256(ownership_raw).hexdigest():
        _fail("candidate-ownership-binding")

    side = _u64(value["side"], "candidate-side", 64, 2048)
    if side % 8:
        _fail("candidate-side")
    width = _u64(value["shell_width"], "candidate-width", 8, min(128, (side - 8) // 2))
    if width % 8:
        _fail("candidate-width")
    interior = side - 2 * width
    population = interior * interior
    mapping = _keys(value["mapping"], _MAPPING_KEYS, "candidate-mapping")
    expected_mapping = {
        "id": "affine-interior-v1",
        "interior_side": interior,
        "population": population,
        "multiplier": 2 * interior - 1,
        "offset": (profile.profile_version * 40_503 + width * 257) % population,
        "inverse_multiplier": population - 2 * interior - 1,
    }
    if mapping != expected_mapping:
        _fail("candidate-mapping")

    shell_rows = _array(value["shell_rows"], 4, "candidate-shell")
    capacity = width * (side - width)
    if len(shell_rows) != 4:
        _fail("candidate-shell")
    for sector, raw_row in enumerate(shell_rows):
        row = _keys(raw_row, _SHELL_ROW_KEYS, "candidate-shell")
        if _u64(row["sector_id"], "candidate-shell", 0, 3) != sector:
            _fail("candidate-shell")
        prefix = _u64(row["route_prefix_cells"], "candidate-shell", 1, capacity)
        headroom = _u64(row["headroom_cells"], "candidate-shell", 0, capacity)
        fixed = _u64(row["fixed_pad_cells"], "candidate-shell", 0, capacity)
        _hex64(row["image_sha256"], "candidate-shell")
        if prefix + headroom + fixed != capacity:
            _fail("candidate-shell")

    sections_raw = _array(value["section_rows"], 65_535, "candidate-sections")
    if not sections_raw:
        _fail("candidate-sections")
    sections: list[dict[str, Any]] = []
    previous = 0
    check_id = 1 if profile.check_bytes == 4 else 2
    for raw_row in sections_raw:
        row = _keys(raw_row, _SECTION_ROW_KEYS, "candidate-section")
        section_id = _u64(row["section_id"], "candidate-section", 1, 0xFFFF_FFFF)
        if section_id <= previous:
            _fail("candidate-section-order")
        previous = section_id
        section_type = _u64(row["section_type"], "candidate-section", 1, 6)
        closure = _u64(row["closure_class"], "candidate-section")
        copies = _u64(row["copy_count"], "candidate-section", 1, 3)
        dependencies = _array(row["dependency_ids"], 4095, "candidate-dependencies")
        if (
            closure not in (128, 129)
            or row["check_id"] != check_id
            or dependencies != sorted(set(dependencies))
            or any(type(item) is not int or not 1 <= item <= 0xFFFF_FFFF for item in dependencies)
        ):
            _fail("candidate-section")
        payload = _u64(row["logical_payload_bytes"], "candidate-section", 0, 16_384)
        envelope = 18 + 4 * len(dependencies) + payload + profile.check_bytes
        if row["envelope_bytes"] != envelope or row["fragment_count"] != (envelope + 156) // 157:
            _fail("candidate-section-size")
        if section_id == 1 and (section_type, closure, copies, dependencies) != (1, 128, 2, []):
            _fail("candidate-inventory")
        if section_type == 2 and copies != 2:
            _fail("candidate-tier-copy")
        if section_type == 3 and copies != (profile.required_copy_count if closure == 128 else 1):
            _fail("candidate-content-copy")
        if section_type == 5 and copies != profile.required_copy_count:
            _fail("candidate-reserve-copy")
        if section_type == 6 and copies != 1:
            _fail("candidate-load-copy")
        sections.append(row)
    section_by_id = {int(row["section_id"]): row for row in sections}
    if any(
        dependency not in section_by_id or dependency == row["section_id"]
        for row in sections
        for dependency in row["dependency_ids"]
    ):
        _fail("candidate-dependency-target")

    unit_bits = profile.protected_unit_bytes * 8
    expected_tuples = [
        (int(section["section_id"]), copy_id, fragment)
        for copy_id in range(max(int(section["copy_count"]) for section in sections))
        for section in sections
        if copy_id < int(section["copy_count"])
        for fragment in range(int(section["fragment_count"]))
    ]
    units_raw = _array(value["unit_rows"], 65_535, "candidate-units")
    if len(units_raw) != len(expected_tuples) or len(units_raw) > profile.protected_units:
        _fail("candidate-unit-count")
    units: list[dict[str, Any]] = []
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for ordinal, (raw_row, expected_tuple) in enumerate(zip(units_raw, expected_tuples, strict=True)):
        row = _keys(raw_row, _UNIT_ROW_KEYS, "candidate-unit")
        if (
            row["physical_unit_id"] != ordinal + 1
            or (row["section_id"], row["semantic_copy_id"], row["fragment_index"]) != expected_tuple
            or row["transport_id"] != profile.transport_id
            or row["encoded_bytes"] != profile.protected_unit_bytes
            or row["logical_bit_first"] != ordinal * unit_bits
            or row["logical_bit_count"] != unit_bits
        ):
            _fail("candidate-unit")
        _hex64(row["encoded_sha256"], "candidate-unit-sha256")
        units.append(row)
        grouped.setdefault((expected_tuple[0], expected_tuple[1]), []).append(row)
    protected_bits = len(units) * unit_bits
    if protected_bits > population:
        _fail("candidate-protected-bits")

    ledger = _keys(value["ledger"], _LEDGER_KEYS, "candidate-ledger")
    for name in _LEDGER_KEYS - {"logical_bytes_by_owner"}:
        _u64(ledger[name], "candidate-ledger")
    logical_rows = _array(ledger["logical_bytes_by_owner"], 65_535, "candidate-logical-ledger")
    expected_logical = [
        {
            "owner_id": f"section:{int(section['section_id']):010d}",
            "section_type": section["section_type"],
            "closure_class": section["closure_class"],
            "copy_count": section["copy_count"],
            "logical_bytes": section["logical_payload_bytes"],
        }
        for section in sections
    ]
    for row in logical_rows:
        _keys(row, _LOGICAL_OWNER_KEYS, "candidate-logical-ledger")
    if logical_rows != expected_logical:
        _fail("candidate-logical-ledger")
    copied_envelopes = sum(
        int(section["copy_count"]) * int(section["envelope_bytes"]) for section in sections
    )
    header_bytes = sum(
        int(section["copy_count"]) * (18 + 4 * len(section["dependency_ids"]))
        for section in sections
    )
    protected_by_type = {
        section_type: sum(
            unit_bits for unit in units if section_by_id[int(unit["section_id"])]["section_type"] == section_type
        )
        for section_type in range(1, 7)
    }
    expected_scalars = {
        "envelope_bytes": header_bytes,
        "fragment_header_bytes": 30 * len(units),
        "fragment_zero_pad_bytes": 157 * len(units) - copied_envelopes,
        "local_check_bytes": 4 * len(units),
        "section_check_bytes": profile.check_bytes * sum(int(row["copy_count"]) for row in sections),
        "transport_pad_bytes": len(units) if profile.transport_id == m2_codec.EH_TRANSPORT else 0,
        "parity_bytes": (24 if profile.transport_id == m2_codec.EH_TRANSPORT else 64) * len(units),
        "real_protected_cells": sum(protected_by_type[index] for index in (1, 2, 3)),
        "capacity_probe_cells": protected_by_type[4],
        "reserve_probe_cells": protected_by_type[5],
        "load_probe_cells": protected_by_type[6],
        "interior_fixed_pad_cells": population - protected_bits,
        "protected_unit_count": len(units),
        "codeword_count": (24 if profile.transport_id == m2_codec.EH_TRANSPORT else 1) * len(units),
        "worst_case_section_attempts": max(int(row["copy_count"]) for row in sections),
        "unused_cells": 0,
        "total_cells": side * side,
    }
    if any(ledger[name] != expected for name, expected in expected_scalars.items()):
        _fail("candidate-ledger-scalar")
    route_total = sum(int(row["route_prefix_cells"]) for row in shell_rows)
    if (
        ledger["shell_instruction_cells"]
        + ledger["shell_example_cells"]
        + ledger["shell_recipe_cells"]
        != route_total
        or ledger["shell_headroom_cells"] != sum(int(row["headroom_cells"]) for row in shell_rows)
        or ledger["shell_fixed_pad_cells"] != sum(int(row["fixed_pad_cells"]) for row in shell_rows)
    ):
        _fail("candidate-shell-ledger")
    return _Candidate(
        raw,
        value,
        profile,
        side,
        width,
        interior,
        population,
        unit_bits,
        protected_bits,
        tuple(sections),
        tuple(units),
        section_by_id,
        {key: tuple(rows) for key, rows in grouped.items()},
    )


def _validate_ownership(raw: bytes, candidate: _Candidate) -> dict[str, Any]:
    value = _keys(_canonical(raw, "ownership-ledger"), _OWNERSHIP_KEYS, "ownership-keys")
    if (
        value["schema"] != "golden-board.m2-ownership-ledger/v0"
        or value["profile_id"] != candidate.profile.profile_id
        or value["side"] != candidate.side
        or value["shell_width"] != candidate.width
        or value["mapping"] != candidate.value["mapping"]
        or value["shell_rows"] != candidate.value["shell_rows"]
        or value["unit_rows"] != candidate.value["unit_rows"]
    ):
        _fail("ownership-binding")
    pad = _keys(value["interior_fixed_pad"], _INTERIOR_PAD_KEYS, "ownership-pad")
    if pad != {
        "logical_bit_first": candidate.protected_bits,
        "logical_bit_count": candidate.population - candidate.protected_bits,
        "fill_order": "unoccupied-interior-cells-in-physical-row-major-order",
    }:
        _fail("ownership-pad")
    table = _keys(value["cell_table"], _CELL_TABLE_KEYS, "ownership-cell-table")
    if table != {
        "row_bytes": 9,
        "row_count": candidate.side * candidate.side,
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
    }:
        _fail("ownership-cell-table")
    _hex64(value["cell_table_sha256"], "ownership-cell-table-sha256")
    return value


def _r3_map_unit_bit(mapping: dict[str, Any], unit_id: int, bit_offset: int) -> int:
    """Independent v1 two-stage forward map."""

    if (
        type(unit_id) is not int
        or type(bit_offset) is not int
        or not 1 <= unit_id <= 1_841
        or not 0 <= bit_offset < 1_728
    ):
        _fail("r3-map")
    slot = (int(mapping["unit_multiplier"]) * (unit_id - 1)) % int(
        mapping["unit_population"]
    )
    logical = 1_728 * slot + bit_offset
    return (
        int(mapping["cell_multiplier"]) * logical + int(mapping["offset"])
    ) % int(mapping["population"])


def _r3_invert_cell(
    mapping: dict[str, Any], physical: int
) -> tuple[int, int] | None:
    """Independent v1 inverse; ``None`` is the fixed-pad tail."""

    population = int(mapping["population"])
    if type(physical) is not int or not 0 <= physical < population:
        _fail("r3-map")
    logical = (
        int(mapping["cell_inverse_multiplier"])
        * ((physical - int(mapping["offset"])) % population)
    ) % population
    slot, bit_offset = divmod(logical, 1_728)
    count = int(mapping["unit_population"])
    if slot >= count:
        return None
    ordinal = (int(mapping["unit_inverse_multiplier"]) * slot) % count
    return ordinal + 1, bit_offset


def _r3_copy_class(section_id: int, section_type: int, value: object) -> tuple[str, int]:
    expected: tuple[str, int]
    if section_id in (1, 2, 3, 16):
        expected = ("required-spine", 5)
    elif section_type == 5:
        expected = ("replicated-m2", 2)
    elif section_type == 6:
        expected = ("nonreplicated-m2", 1)
    elif value == "replicated-m2":
        expected = ("replicated-m2", 2)
    else:
        expected = ("nonreplicated-m2", 1)
    if value != expected[0]:
        _fail("r3-candidate-owner-class")
    return expected


def _validate_candidate_v1(raw: bytes, ownership_raw: bytes) -> _CandidateV1:
    """Strictly admit the one promoted v7 candidate and its raw ownership binding."""

    if (
        type(raw) is not bytes
        or type(ownership_raw) is not bytes
        or sha256(raw).hexdigest() != _R3_CANDIDATE_SHA256
    ):
        _fail("r3-candidate-sha256")
    value = _keys(
        _canonical(raw, "r3-candidate-manifest"),
        _R3_CANDIDATE_KEYS,
        "r3-candidate-keys",
    )
    for name in (
        "profile_policy_sha256",
        "profile_limits_sha256",
        "bootstrap_spec_sha256",
        "route_data_sha256",
        "recipient_package_sha256",
        "semantic_envelope_sha256",
        "ownership_sha256",
        "capacity_ledger_sha256",
        "density_ledger_sha256",
        "carrier_sha256",
    ):
        _hex64(value[name], "r3-candidate-sha256")
    if (
        value["schema"] != "golden-board.m2-candidate-manifest/v1"
        or value["profile_id"] != _R3_PROFILE_ID
        or value["profile_version"] != 7
        or value["profile_policy_sha256"] != _R3_PROFILE_POLICY_SHA256
        or value["profile_limits_sha256"] != _R3_PROFILE_LIMITS_SHA256
        or value["bootstrap_spec_sha256"] != _R3_BOOTSTRAP_SPEC_SHA256
        or value["route_data_sha256"] != _R3_ROUTE_DATA_SHA256
        or value["recipient_package_sha256"] != _R3_RECIPIENT_PACKAGE_SHA256
        or value["ownership_sha256"] != sha256(ownership_raw).hexdigest()
    ):
        _fail("r3-candidate-owner-binding")
    omitted = dict(value)
    claimed_identity = _hex64(omitted.pop("manifest_identity"), "r3-candidate-identity")
    if claimed_identity != identity.identity_hex(
        _IDENTITY_DOMAIN, (canonical_manifest.serialize_manifest(omitted),)
    ):
        _fail("r3-candidate-identity")

    side = _u64(value["side"], "r3-candidate-geometry")
    width = _u64(value["shell_width"], "r3-candidate-geometry")
    if (side, width) != (2_040, 128):
        _fail("r3-candidate-geometry")
    interior = side - 2 * width
    population = interior * interior
    mapping = _keys(value["mapping"], _R3_MAPPING_KEYS, "r3-candidate-mapping")
    expected_mapping = {
        "id": "affine-slot-then-interior-v1",
        "interior_side": interior,
        "population": population,
        "unit_population": 1_841,
        "unit_multiplier": 2,
        "unit_inverse_multiplier": pow(2, -1, 1_841),
        "cell_multiplier": 2 * interior - 1,
        "offset": (40_503 * 7 + 257 * width) % population,
        "cell_inverse_multiplier": pow(2 * interior - 1, -1, population),
    }
    if mapping != expected_mapping:
        _fail("r3-candidate-mapping")

    shell_rows = _array(value["shell_rows"], 4, "r3-candidate-shell")
    sector_capacity = width * (side - width)
    if len(shell_rows) != 4:
        _fail("r3-candidate-shell")
    for sector_id, raw_row in enumerate(shell_rows):
        row = _keys(raw_row, _SHELL_ROW_KEYS, "r3-candidate-shell")
        if row["sector_id"] != sector_id:
            _fail("r3-candidate-shell")
        prefix = _u64(row["route_prefix_cells"], "r3-candidate-shell", 1)
        headroom = _u64(row["headroom_cells"], "r3-candidate-shell")
        fixed = _u64(row["fixed_pad_cells"], "r3-candidate-shell")
        _hex64(row["image_sha256"], "r3-candidate-shell")
        if prefix + headroom + fixed != sector_capacity:
            _fail("r3-candidate-shell")

    sections_raw = _array(value["section_rows"], 4_096, "r3-candidate-sections")
    if len(sections_raw) != 138:
        _fail("r3-candidate-sections")
    sections: list[dict[str, Any]] = []
    previous_section_id = 0
    dependency_count = 0
    for raw_row in sections_raw:
        row = _keys(raw_row, _R3_SECTION_ROW_KEYS, "r3-candidate-section")
        section_id = _u64(row["section_id"], "r3-candidate-section", 1, 0xFFFF_FFFF)
        if section_id <= previous_section_id:
            _fail("r3-candidate-section-order")
        previous_section_id = section_id
        section_type = _u64(row["section_type"], "r3-candidate-section", 1, 6)
        closure = _u64(row["closure_class"], "r3-candidate-section")
        if closure not in (128, 129) or row["check_id"] != 1:
            _fail("r3-candidate-section")
        if row["semantic_copy_count"] != 1:
            _fail("r3-candidate-section-copy")
        _, factor = _r3_copy_class(section_id, section_type, row["copy_class"])
        if row["physical_replica_count"] != factor:
            _fail("r3-candidate-section-factor")
        dependencies = _array(row["dependency_ids"], 4_095, "r3-candidate-dependencies")
        if dependencies != sorted(set(dependencies)) or any(
            type(item) is not int or not 1 <= item <= 0xFFFF_FFFF
            for item in dependencies
        ):
            _fail("r3-candidate-dependencies")
        dependency_count += len(dependencies)
        payload = _u64(row["logical_payload_bytes"], "r3-candidate-section", 0, 16_384)
        envelope = 18 + 4 * len(dependencies) + payload + 4
        fragments = (envelope + 156) // 157
        if row["envelope_bytes"] != envelope or row["fragment_count"] != fragments:
            _fail("r3-candidate-section-size")
        sections.append(row)
    section_by_id = {int(row["section_id"]): row for row in sections}
    if dependency_count != 78 or any(
        int(dependency) not in section_by_id or int(dependency) == int(row["section_id"])
        for row in sections
        for dependency in row["dependency_ids"]
    ):
        _fail("r3-candidate-dependency-target")

    expected_groups = [
        (section, fragment, int(section["physical_replica_count"]))
        for section in sections
        for fragment in range(int(section["fragment_count"]))
    ]
    if len(expected_groups) != 1_279:
        _fail("r3-candidate-group-count")
    units_raw = _array(value["unit_rows"], 1_841, "r3-candidate-units")
    if len(units_raw) != 1_841:
        _fail("r3-candidate-unit-count")
    units: list[dict[str, Any]] = []
    groups: list[tuple[dict[str, Any], ...]] = []
    cursor = 0
    for section, fragment, factor in expected_groups:
        group: list[dict[str, Any]] = []
        encoded_sha256: str | None = None
        for replica_index in range(factor):
            if cursor >= len(units_raw):
                _fail("r3-candidate-unit-count")
            row = _keys(units_raw[cursor], _R3_UNIT_ROW_KEYS, "r3-candidate-unit")
            unit_id = cursor + 1
            slot = (2 * cursor) % 1_841
            if (
                row["physical_unit_id"] != unit_id
                or row["section_id"] != section["section_id"]
                or row["semantic_copy_id"] != 0
                or row["fragment_index"] != fragment
                or row["replica_index"] != replica_index
                or row["physical_replica_count"] != factor
                or row["slot"] != slot
                or row["transport_id"] != "eh72-hier-repetition-v0"
                or row["encoded_bytes"] != 216
                or row["logical_bit_first"] != 1_728 * slot
                or row["logical_bit_count"] != 1_728
            ):
                _fail("r3-candidate-unit")
            digest = _hex64(row["encoded_sha256"], "r3-candidate-unit-sha256")
            if encoded_sha256 is None:
                encoded_sha256 = digest
            elif digest != encoded_sha256:
                _fail("r3-candidate-replica-bytes")
            units.append(row)
            group.append(row)
            cursor += 1
        groups.append(tuple(group))
    if cursor != len(units_raw):
        _fail("r3-candidate-unit-count")

    ledger = _keys(value["ledger"], _LEDGER_KEYS, "r3-candidate-ledger")
    for name in _LEDGER_KEYS - {"logical_bytes_by_owner"}:
        _u64(ledger[name], "r3-candidate-ledger")
    logical_rows = _array(
        ledger["logical_bytes_by_owner"], 4_096, "r3-candidate-logical-ledger"
    )
    expected_logical = [
        {
            "owner_id": f"section:{int(section['section_id']):010d}",
            "section_type": section["section_type"],
            "closure_class": section["closure_class"],
            "semantic_copy_count": 1,
            "physical_replica_count": section["physical_replica_count"],
            "logical_bytes": section["logical_payload_bytes"],
        }
        for section in sections
    ]
    for row in logical_rows:
        _keys(row, _R3_LOGICAL_OWNER_KEYS, "r3-candidate-logical-ledger")
    if logical_rows != expected_logical:
        _fail("r3-candidate-logical-ledger")
    physical_envelope_bytes = sum(
        int(row["physical_replica_count"])
        * (18 + 4 * len(row["dependency_ids"]))
        for row in sections
    )
    physical_section_checks = sum(
        4 * int(row["physical_replica_count"]) for row in sections
    )
    physical_envelopes = sum(
        int(row["physical_replica_count"]) * int(row["envelope_bytes"])
        for row in sections
    )
    unit_count = len(units)
    cells_by_type = {
        section_type: 1_728
        * sum(
            int(row["section_id"]) in section_by_id
            and int(section_by_id[int(row["section_id"])]["section_type"]) == section_type
            for row in units
        )
        for section_type in range(1, 7)
    }
    expected_scalars = {
        "envelope_bytes": physical_envelope_bytes,
        "fragment_header_bytes": 30 * unit_count,
        "fragment_zero_pad_bytes": 157 * unit_count - physical_envelopes,
        "local_check_bytes": 4 * unit_count,
        "section_check_bytes": physical_section_checks,
        "transport_pad_bytes": unit_count,
        "parity_bytes": 24 * unit_count,
        "real_protected_cells": sum(cells_by_type[index] for index in (1, 2, 3)),
        "capacity_probe_cells": cells_by_type[4],
        "reserve_probe_cells": cells_by_type[5],
        "load_probe_cells": cells_by_type[6],
        "interior_fixed_pad_cells": population - 1_728 * unit_count,
        "protected_unit_count": unit_count,
        "codeword_count": 24 * unit_count,
        "worst_case_section_attempts": 1,
        "unused_cells": 0,
        "total_cells": side * side,
    }
    if any(ledger[name] != expected for name, expected in expected_scalars.items()):
        _fail("r3-candidate-ledger-scalar")
    if (
        ledger["shell_instruction_cells"]
        + ledger["shell_example_cells"]
        + ledger["shell_recipe_cells"]
        != sum(int(row["route_prefix_cells"]) for row in shell_rows)
        or ledger["shell_headroom_cells"]
        != sum(int(row["headroom_cells"]) for row in shell_rows)
        or ledger["shell_fixed_pad_cells"]
        != sum(int(row["fixed_pad_cells"]) for row in shell_rows)
    ):
        _fail("r3-candidate-shell-ledger")
    factor_counts = {
        factor: sum(int(group[0]["physical_replica_count"]) == factor for group in groups)
        for factor in (1, 2, 5)
    }
    if factor_counts != {1: 807, 2: 442, 5: 30}:
        _fail("r3-candidate-factor-count")
    groups_by_section: dict[int, list[tuple[dict[str, Any], ...]]] = {}
    for group in groups:
        groups_by_section.setdefault(int(group[0]["section_id"]), []).append(group)
    return _CandidateV1(
        raw,
        value,
        side,
        width,
        interior,
        population,
        1_728,
        1_728 * unit_count,
        tuple(sections),
        tuple(units),
        section_by_id,
        {int(row["physical_unit_id"]): row for row in units},
        tuple(groups),
        {key: tuple(items) for key, items in groups_by_section.items()},
    )


def _validate_ownership_v1(raw: bytes, candidate: _CandidateV1) -> dict[str, Any]:
    value = _keys(
        _canonical(raw, "r3-ownership-ledger"),
        _OWNERSHIP_KEYS,
        "r3-ownership-keys",
    )
    if (
        sha256(raw).hexdigest() != candidate.value["ownership_sha256"]
        or value["schema"] != "golden-board.m2-ownership-ledger/v1"
        or value["profile_id"] != _R3_PROFILE_ID
        or value["side"] != candidate.side
        or value["shell_width"] != candidate.width
        or value["mapping"] != candidate.value["mapping"]
        or value["shell_rows"] != candidate.value["shell_rows"]
    ):
        _fail("r3-ownership-binding")
    raw_units = _array(value["unit_rows"], 1_841, "r3-ownership-units")
    if len(raw_units) != len(candidate.units):
        _fail("r3-ownership-units")
    for source, raw_row in zip(candidate.units, raw_units, strict=True):
        row = _keys(raw_row, _R3_OWNERSHIP_UNIT_KEYS, "r3-ownership-unit")
        if row != {
            "physical_unit_id": source["physical_unit_id"],
            "section_id": source["section_id"],
            "fragment_index": source["fragment_index"],
            "replica_index": source["replica_index"],
            "physical_replica_count": source["physical_replica_count"],
            "slot": source["slot"],
            "logical_bit_first": source["logical_bit_first"],
            "logical_bit_count": source["logical_bit_count"],
            "mapped_cell_sha256": row["mapped_cell_sha256"],
        }:
            _fail("r3-ownership-unit-binding")
        _hex64(row["mapped_cell_sha256"], "r3-ownership-unit-sha256")
    pad = _keys(value["interior_fixed_pad"], _INTERIOR_PAD_KEYS, "r3-ownership-pad")
    if pad != {
        "logical_bit_first": candidate.protected_bits,
        "logical_bit_count": candidate.population - candidate.protected_bits,
        "fill_order": "unoccupied-interior-cells-in-physical-row-major-order",
    }:
        _fail("r3-ownership-pad")
    table = _keys(value["cell_table"], _CELL_TABLE_KEYS, "r3-ownership-cell-table")
    if table != {
        "row_bytes": 9,
        "row_count": candidate.side * candidate.side,
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
    }:
        _fail("r3-ownership-cell-table")
    _hex64(value["cell_table_sha256"], "r3-ownership-cell-table-sha256")
    return value


def _parameter_map(value: object) -> dict[str, tuple[str, Any]]:
    rows = _array(value, 32, "damage-parameters")
    result: dict[str, tuple[str, Any]] = {}
    previous = ""
    for raw_row in rows:
        row = _keys(raw_row, _PARAMETER_KEYS, "damage-parameter")
        name = _ascii(row["id"], "damage-parameter")
        kind = row["value_type"]
        if name <= previous or kind not in ("u64", "ascii", "u64-list", "coordinate-list"):
            _fail("damage-parameter")
        previous = name
        item = row["value"]
        if kind == "u64":
            _u64(item, "damage-parameter")
        elif kind == "ascii":
            _ascii(item, "damage-parameter")
        elif kind == "u64-list":
            items = _array(item, 4_194_304, "damage-parameter")
            for scalar in items:
                _u64(scalar, "damage-parameter")
        else:
            items = _array(item, 4_194_304, "damage-parameter")
            for coordinate in items:
                if type(coordinate) is not list or len(coordinate) != 2:
                    _fail("damage-coordinate")
                _u64(coordinate[0], "damage-coordinate", 0, 0xFFFF_FFFF)
                _u64(coordinate[1], "damage-coordinate", 0, 0xFFFF_FFFF)
        result[name] = (kind, item)
    return result


def _sample_indices(population: int, count: int, seed: int) -> tuple[int, ...]:
    if not 0 <= count <= population or population <= 0:
        _fail("damage-sample")
    limit = ((1 << 64) // population) * population
    selected: set[int] = set()
    result: list[int] = []
    counter = 0
    retry_max = population * 64 + 1024
    while len(result) < count:
        if counter >= retry_max or counter > _MAX_U64:
            _fail("damage-sample")
        digest = sha256(
            _SAMPLE_DOMAIN + seed.to_bytes(8, "big") + counter.to_bytes(8, "big")
        ).digest()
        counter += 1
        for offset in range(0, 32, 8):
            word = int.from_bytes(digest[offset : offset + 8], "big")
            if word < limit:
                index = word % population
                if index not in selected:
                    selected.add(index)
                    result.append(index)
                    if len(result) == count:
                        break
    return tuple(result)


def _two_indices(population: int, seed: int) -> tuple[int, int]:
    if population <= 0:
        _fail("damage-window")
    limit = ((1 << 64) // population) * population
    result: list[int] = []
    counter = 0
    while len(result) < 2:
        if counter >= population * 64 + 1024:
            _fail("damage-window")
        digest = sha256(
            _WINDOW_DOMAIN + seed.to_bytes(8, "big") + counter.to_bytes(8, "big")
        ).digest()
        counter += 1
        for offset in range(0, 32, 8):
            word = int.from_bytes(digest[offset : offset + 8], "big")
            if word < limit:
                result.append(word % population)
                if len(result) == 2:
                    break
    return result[0], result[1]


def _d2_placements(candidate: _Candidate, square: int) -> tuple[tuple[int, int], ...]:
    domain = candidate.interior - square + 1
    choices = (0, domain // 2, domain - 1)
    anchors = tuple((row, column) for row in choices for column in choices)
    excluded = sorted(row * domain + column for row, column in anchors)
    sampled = _sample_indices(domain * domain - len(excluded), 256 - len(anchors), 5_134_751_402_299_490_304)

    def unfilter(index: int) -> int:
        value = index
        for item in excluded:
            if item <= value:
                value += 1
        return value

    extra = tuple(divmod(unfilter(index), domain) for index in sampled)
    return tuple((row + candidate.width, column + candidate.width) for row, column in anchors + extra)


def _d3_population(candidate: _Candidate, stratum: int) -> tuple[int, ...]:
    required = {
        int(row["section_id"]) for row in candidate.sections if int(row["closure_class"]) == 128
    }
    coordinates: set[int] = set()
    multiplier = int(candidate.value["mapping"]["multiplier"])
    offset = int(candidate.value["mapping"]["offset"])
    for unit in candidate.units:
        if stratum == 2 and int(unit["section_id"]) not in required:
            continue
        logical_first = int(unit["logical_bit_first"])
        for bit in range(candidate.unit_bits):
            physical = (multiplier * (logical_first + bit) + offset) % candidate.population
            row, column = divmod(physical, candidate.interior)
            if stratum == 2 or (
                bit < 16
                or bit >= candidate.unit_bits - 16
                or bit % 8 in (0, 7)
                or row % 16 in (0, 15)
                or column % 16 in (0, 15)
            ):
                coordinates.add(physical)
    return tuple(sorted(coordinates))


def _d3_coordinates(
    candidate: _Candidate,
    ordinal: int,
    population_cache: dict[int, tuple[int, ...]] | None = None,
) -> list[list[int]]:
    seed = 5_134_751_402_299_490_304 + ordinal
    stratum = ordinal // 32
    weight = max(64, (candidate.population + 1999) // 2000)
    if stratum == 0:
        selected = _sample_indices(candidate.population, weight, seed)
        points = (divmod(index, candidate.interior) for index in selected)
    elif stratum == 1:
        window = max(32, candidate.interior // 8)
        domain = candidate.interior - window + 1
        top, left = _two_indices(domain, seed)
        selected = _sample_indices(window * window, weight, seed)
        points = ((top + row, left + column) for row, column in (divmod(index, window) for index in selected))
    else:
        if population_cache is None:
            population = _d3_population(candidate, stratum)
        elif stratum in population_cache:
            population = population_cache[stratum]
        else:
            population = _d3_population(candidate, stratum)
            population_cache[stratum] = population
        selected = _sample_indices(len(population), weight, seed)
        points = (divmod(population[index], candidate.interior) for index in selected)
    return [[row + candidate.width, column + candidate.width] for row, column in points]


def _expected_d7(candidate: _Candidate) -> list[tuple[str, str, dict[str, tuple[str, Any]]]]:
    profile = candidate.profile
    first_unit = int(candidate.units[0]["physical_unit_id"])
    target_section = min(
        int(row["section_id"])
        for row in candidate.sections
        if int(row["closure_class"]) == 128 and int(row["section_id"]) != 1
    )
    result: list[tuple[str, str, dict[str, tuple[str, Any]]]] = []
    for ordinal in range(3):
        result.append(("OBS_BITS", "mapping-mutants", {"mutant_ordinal": ("u64", ordinal)}))
    for ordinal in range(4):
        parameter = (
            {"case_ordinal": ("u64", ordinal), "target_unit_id": ("u64", first_unit)}
            if ordinal < 2
            else {"case_ordinal": ("u64", ordinal), "section_id": ("u64", target_section)}
        )
        result.append(("OBS_UNITS", "check-mutants", parameter))
    code_count = 3 if profile.transport_id == m2_codec.EH_TRANSPORT else 5
    for ordinal in range(code_count):
        result.append(
            (
                "OBS_UNITS",
                "code-mutants",
                {"case_ordinal": ("u64", ordinal), "target_unit_id": ("u64", first_unit)},
            )
        )
    alternate_versions = {
        1: 3,
        2: 4,
        3: 1,
        4: 2,
        5: 1,
        6: 2,
    }
    result.append(
        (
            "OBS_BITS",
            "route-conflicts",
            {"alternate_profile_version": ("u64", alternate_versions[profile.profile_version])},
        )
    )
    for other in m2_codec.candidate_profiles():
        if other.profile_version != profile.profile_version:
            result.append(
                (
                    "OBS_UNITS",
                    "cross-profile-splices",
                    {
                        "source_profile_version": ("u64", other.profile_version),
                        "target_unit_id": ("u64", first_unit),
                    },
                )
            )
    result.append(("OBS_UNITS", "valid-copy-conflicts", {"section_id": ("u64", target_section)}))
    square = max(32, candidate.interior // 32)
    for ordinal in range(256):
        result.append(
            (
                "OBS_MATRIX",
                "d2-one-beyond",
                {"d2_ordinal": ("u64", ordinal), "side": ("u64", square + 1)},
            )
        )
    for ordinal in range(128):
        result.append(
            (
                "OBS_MATRIX",
                "d3-one-beyond",
                {"seed": ("u64", 5_134_751_402_299_490_304 + ordinal)},
            )
        )
    copy_zero = candidate.units_by_section_copy[(target_section, 0)][0]
    copy_one = candidate.units_by_section_copy[(target_section, 1)][0]
    result.append(
        (
            "OBS_UNITS",
            "missing-unit-one-beyond",
            {
                "omitted_unit_ids": (
                    "u64-list",
                    sorted((int(copy_zero["physical_unit_id"]), int(copy_one["physical_unit_id"]))),
                )
            },
        )
    )
    pairs = ((2, 0), (1, 2), (0, 4)) if profile.transport_id == m2_codec.EH_TRANSPORT else tuple(
        (errors, 65 - 2 * errors) for errors in range(33)
    )
    for errors, erasures in pairs:
        result.append(
            (
                "OBS_MATRIX",
                "algebraic-one-beyond",
                {"erasures": ("u64", erasures), "errors": ("u64", errors)},
            )
        )
    for declared in (268_435_457, 16_777_217):
        result.append(
            ("OBS_BITS", "resource-route-one-beyond", {"declared_value": ("u64", declared)})
        )
    result.append(("OBS_BITS", "geometry-one-beyond", {"side": ("u64", 2056)}))
    expected_count = 408 if profile.transport_id == m2_codec.EH_TRANSPORT else 440
    if len(result) != expected_count:
        _fail("damage-d7-count")
    return result


def _validate_case(
    row: object,
    family: str,
    ordinal: int,
    candidate: _Candidate,
    d2: tuple[tuple[int, int], ...],
    d3_cache: dict[int, list[list[int]]],
    d3_population_cache: dict[int, tuple[int, ...]],
    d7: Sequence[tuple[str, str, dict[str, tuple[str, Any]]]],
) -> dict[str, Any]:
    value = _keys(row, _CASE_KEYS, "damage-case")
    if value["case_id"] != f"{family}-{ordinal:06d}" or value["family_id"] != family:
        _fail("damage-case-id")
    _hex64(value["observation_sha256"], "damage-case-sha256")
    _hex64(value["decoder_result_sha256"], "damage-case-sha256")
    if value["expected_artifact_state"] not in _ARTIFACT_STATES:
        _fail("damage-case-state")
    _u64(value["wrong_accept_count"], "damage-case-wrong")
    state_rows = _array(value["expected_section_states"], 65_535, "damage-case-sections")
    expected_ids = [int(item["section_id"]) for item in candidate.sections]
    observed_ids: list[int] = []
    for raw_state in state_rows:
        state = _keys(raw_state, _SECTION_STATE_KEYS, "damage-case-section")
        observed_ids.append(_u64(state["section_id"], "damage-case-section", 1, 0xFFFF_FFFF))
        if state["state"] not in _SECTION_STATES:
            _fail("damage-case-section")
    if observed_ids != expected_ids:
        _fail("damage-case-section-order")
    parameters = _parameter_map(value["parameter_projection"])
    unit_ids = [int(item["physical_unit_id"]) for item in candidate.units]
    square = max(32, candidate.interior // 32)
    expected_channel: str
    expected_operator: str
    expected_parameters: dict[str, tuple[str, Any]]
    if family == "D0":
        expected_channel, expected_operator = "OBS_BITS", "clean-transform-polarity"
        expected_parameters = {
            "polarity_id": ("u64", ordinal % 2),
            "transform_id": ("u64", ordinal // 2),
        }
    elif family == "D1":
        expected_channel, expected_operator = "OBS_MATRIX", "erase-one-complete-shell-sector"
        expected_parameters = {"sector_id": ("u64", ordinal)}
    elif family == "D2":
        expected_channel, expected_operator = "OBS_MATRIX", "erase-square-in-protected-interior"
        expected_parameters = {
            "side": ("u64", square),
            "top_left": ("coordinate-list", [list(d2[ordinal])]),
        }
    elif family == "D3":
        expected_channel, expected_operator = "OBS_MATRIX", "fixed-weight-unknown-bit-substitution"
        if ordinal not in d3_cache:
            d3_cache[ordinal] = _d3_coordinates(
                candidate, ordinal, d3_population_cache
            )
        coordinates = d3_cache[ordinal]
        expected_parameters = {
            "coordinates": ("coordinate-list", coordinates),
            "seed": ("u64", 5_134_751_402_299_490_304 + ordinal),
            "stratum_id": ("u64", ordinal // 32),
        }
    elif family == "D4":
        expected_channel, expected_operator = "OBS_UNITS", "omit-one-protected-unit-observation"
        expected_parameters = {"omitted_unit_id": ("u64", unit_ids[ordinal])}
    elif family == "D5":
        expected_channel, expected_operator = "OBS_UNITS", "permute-intact-protected-unit-observations"
        expected_parameters = {"permutation_ordinal": ("u64", ordinal)}
    elif family == "D6":
        expected_channel, expected_operator = (
            "OBS_MATRIX",
            "erase-shell-sector-union-one-protected-unit-cell-set",
        )
        expected_parameters = {
            "sector_id": ("u64", ordinal // len(unit_ids)),
            "unit_id": ("u64", unit_ids[ordinal % len(unit_ids)]),
        }
    else:
        expected_channel, expected_operator, expected_parameters = d7[ordinal]
    if (
        value["channel"] != expected_channel
        or value["operator"] != expected_operator
        or parameters != expected_parameters
    ):
        _fail("damage-case-owner")
    return value


def _nested_identity(document: dict[str, Any], summary_keys: frozenset[str]) -> str:
    summary = dict(_keys(document["summary"], summary_keys, "damage-summary"))
    claimed = _hex64(summary.pop("manifest_identity"), "damage-identity")
    omitted = dict(document)
    omitted["summary"] = summary
    if claimed != identity.identity_hex(
        _IDENTITY_DOMAIN, (canonical_manifest.serialize_manifest(omitted),)
    ):
        _fail("damage-identity")
    return claimed


def _expected_family_counts(candidate: _Candidate) -> tuple[int, ...]:
    units = len(candidate.units)
    d7 = 408 if candidate.profile.transport_id == m2_codec.EH_TRANSPORT else 440
    return (16, 4, 256, 128, units, 21, 4 * units, d7)


def _validate_damage(
    raw: bytes,
    family_raws: Sequence[bytes],
    shard_raws: Sequence[bytes],
    candidate: _Candidate,
) -> _Damage:
    value = _keys(_canonical(raw, "damage-manifest"), _DAMAGE_KEYS, "damage-keys")
    if (
        value["schema"] != "golden-board.m2-damage-manifest/v0"
        or value["profile_id"] != candidate.profile.profile_id
        or value["damage_policy_sha256"] != _DAMAGE_POLICY_SHA256
        or value["profile_policy_sha256"] != candidate.value["profile_policy_sha256"]
        or value["candidate_manifest_sha256"] != sha256(candidate.raw).hexdigest()
    ):
        _fail("damage-binding")
    for name in (
        "damage_policy_sha256",
        "profile_policy_sha256",
        "candidate_manifest_sha256",
        "clean_observation_sha256",
    ):
        _hex64(value[name], "damage-sha256")
    damage_identity = _nested_identity(value, _DAMAGE_SUMMARY_KEYS)
    expected_counts = _expected_family_counts(candidate)
    root_rows = _array(value["family_rows"], 8, "damage-family-rows")
    count_rows = _array(value["summary"]["family_case_counts"], 8, "damage-family-counts")
    if len(root_rows) != 8 or len(count_rows) != 8:
        _fail("damage-family-counts")
    for index, family in enumerate(_FAMILIES):
        count_row = _keys(count_rows[index], _FAMILY_COUNT_KEYS, "damage-family-count")
        if count_row != {"family_id": family, "case_count": expected_counts[index]}:
            _fail("damage-family-count")
    boundary_rows = _array(value["boundary_kat_rows"], 1, "damage-boundary")
    if len(boundary_rows) != 1:
        _fail("damage-boundary")
    boundary = _keys(boundary_rows[0], _BOUNDARY_ROW_KEYS, "damage-boundary")
    if (
        boundary["kat_id"] != "section-attempt-ceiling-plus-one"
        or _hex64(boundary["result_sha256"], "damage-boundary") != _BOUNDARY_SHA256
        or boundary["result"] not in ("pass", "fail")
    ):
        _fail("damage-boundary")

    if isinstance(family_raws, (bytes, bytearray, str)) or len(family_raws) != 8:
        _fail("damage-family-files")
    if isinstance(shard_raws, (bytes, bytearray, str)) or len(shard_raws) > 65_535:
        _fail("damage-shard-files")
    families: dict[str, tuple[bytes, dict[str, Any]]] = {}
    for family_raw in family_raws:
        document = _keys(_canonical(family_raw, "damage-family"), _FAMILY_KEYS, "damage-family-keys")
        family_id = document.get("family_id")
        if type(family_id) is not str or family_id not in _FAMILIES or family_id in families:
            _fail("damage-family-id")
        families[family_id] = (family_raw, document)
    shards: dict[tuple[str, int], tuple[bytes, dict[str, Any]]] = {}
    for shard_raw in shard_raws:
        document = _keys(_canonical(shard_raw, "damage-shard"), _SHARD_KEYS, "damage-shard-keys")
        family_id = document.get("family_id")
        ordinal = document.get("shard_ordinal")
        if type(family_id) is not str or family_id not in _FAMILIES:
            _fail("damage-shard-id")
        ordinal = _u64(ordinal, "damage-shard-id", 0, 65_534)
        key = (family_id, ordinal)
        if key in shards:
            _fail("damage-shard-duplicate")
        shards[key] = (shard_raw, document)

    d2 = _d2_placements(candidate, max(32, candidate.interior // 32))
    d3_cache: dict[int, list[list[int]]] = {}
    d3_population_cache: dict[int, tuple[int, ...]] = {}
    d7 = _expected_d7(candidate)
    cases: dict[str, tuple[dict[str, Any], ...]] = {}
    family_results: dict[str, str] = {}
    used_shards: set[tuple[str, int]] = set()
    root_wrong: list[int] = []
    for index, family_id in enumerate(_FAMILIES):
        family_raw, family = families[family_id]
        if (
            family["schema"] != "golden-board.m2-damage-family/v0"
            or family["damage_manifest_identity"] != damage_identity
            or family["profile_id"] != candidate.profile.profile_id
            or family["guarantee_id"] != _GUARANTEES[index]
        ):
            _fail("damage-family-binding")
        family_identity = _nested_identity(family, _FAMILY_SUMMARY_KEYS)
        del family_identity
        refs = _array(family["shard_rows"], 65_535, "damage-shard-refs")
        joined: list[dict[str, Any]] = []
        first = 0
        for ordinal, raw_ref in enumerate(refs):
            ref = _keys(raw_ref, _SHARD_REF_KEYS, "damage-shard-ref")
            if ref["shard_ordinal"] != ordinal or ref["case_first"] != first:
                _fail("damage-shard-ref")
            count = _u64(ref["case_count"], "damage-shard-ref", 1, 256)
            digest = _hex64(ref["manifest_sha256"], "damage-shard-ref")
            key = (family_id, ordinal)
            if key not in shards:
                _fail("damage-shard-missing")
            shard_raw, shard = shards[key]
            used_shards.add(key)
            if (
                sha256(shard_raw).hexdigest() != digest
                or shard["schema"] != "golden-board.m2-damage-cases/v0"
                or shard["damage_manifest_identity"] != damage_identity
                or shard["profile_id"] != candidate.profile.profile_id
                or shard["family_id"] != family_id
                or shard["shard_ordinal"] != ordinal
                or shard["case_first"] != first
            ):
                _fail("damage-shard-binding")
            _nested_identity(shard, _SHARD_SUMMARY_KEYS)
            raw_cases = _array(shard["case_rows"], 256, "damage-shard-cases")
            wrong = _checked_sum(
                [
                    _u64(
                        item.get("wrong_accept_count")
                        if type(item) is dict
                        else None,
                        "damage-case-wrong",
                    )
                    for item in raw_cases
                ],
                "damage-wrong-overflow",
            )
            if (
                len(raw_cases) != count
                or shard["summary"]["case_count"] != count
                or shard["summary"]["wrong_accept_count"] != wrong
            ):
                _fail("damage-shard-summary")
            joined.extend(raw_cases)
            first += count
        if first != expected_counts[index]:
            _fail("damage-family-case-count")
        validated = tuple(
            _validate_case(
                row,
                family_id,
                ordinal,
                candidate,
                d2,
                d3_cache,
                d3_population_cache,
                d7,
            )
            for ordinal, row in enumerate(joined)
        )
        wrong = _checked_sum([int(row["wrong_accept_count"]) for row in validated], "damage-wrong-overflow")
        family_summary = family["summary"]
        root = _keys(root_rows[index], _FAMILY_ROW_KEYS, "damage-family-root")
        if (
            family_summary["case_count"] != len(validated)
            or family_summary["wrong_accept_count"] != wrong
            or family_summary["result"] not in ("pass", "fail")
            or root
            != {
                "family_id": family_id,
                "case_count": len(validated),
                "wrong_accept_count": wrong,
                "result": family_summary["result"],
                "case_rows_sha256": _canonical_array_sha256(list(validated)),
            }
        ):
            _fail("damage-family-summary")
        cases[family_id] = validated
        family_results[family_id] = family_summary["result"]
        root_wrong.append(wrong)
    if used_shards != set(shards):
        _fail("damage-shard-extra")
    total_wrong = _checked_sum(root_wrong, "damage-wrong-overflow")
    if value["summary"]["wrong_accept_count"] != total_wrong:
        _fail("damage-root-summary")
    return _Damage(raw, value, cases, family_results, boundary["result"] == "pass")


def _r3_d3_population(
    candidate: _CandidateV1,
    stratum: int,
    cache: dict[int, tuple[int, ...]],
) -> tuple[int, ...]:
    if stratum in cache:
        return cache[stratum]
    required = {
        int(row["section_id"])
        for row in candidate.sections
        if int(row["closure_class"]) == 128
    }
    coordinates: set[int] = set()
    for unit in candidate.units:
        if stratum == 2 and int(unit["section_id"]) not in required:
            continue
        unit_id = int(unit["physical_unit_id"])
        for bit_offset in range(1_728):
            physical = _r3_map_unit_bit(candidate.value["mapping"], unit_id, bit_offset)
            row, column = divmod(physical, candidate.interior)
            if stratum == 2 or (
                bit_offset < 16
                or bit_offset >= 1_712
                or bit_offset % 8 in (0, 7)
                or row % 16 in (0, 15)
                or column % 16 in (0, 15)
            ):
                coordinates.add(physical)
    result = tuple(sorted(coordinates))
    cache[stratum] = result
    return result


def _r3_d3_coordinates(
    candidate: _CandidateV1,
    ordinal: int,
    population_cache: dict[int, tuple[int, ...]],
) -> list[list[int]]:
    seed = 5_134_751_402_299_490_304 + ordinal
    stratum = ordinal // 32
    weight = max(64, (candidate.population + 1_999) // 2_000)
    if stratum == 0:
        selected = _sample_indices(candidate.population, weight, seed)
        points = (divmod(index, candidate.interior) for index in selected)
    elif stratum == 1:
        window = max(32, candidate.interior // 8)
        domain = candidate.interior - window + 1
        top, left = _two_indices(domain, seed)
        selected = _sample_indices(window * window, weight, seed)
        points = (
            (top + row, left + column)
            for row, column in (divmod(index, window) for index in selected)
        )
    else:
        population = _r3_d3_population(candidate, stratum, population_cache)
        selected = _sample_indices(len(population), weight, seed)
        points = (
            divmod(population[index], candidate.interior) for index in selected
        )
    return [
        [row + candidate.width, column + candidate.width]
        for row, column in points
    ]


def _r3_expected_d7() -> tuple[tuple[str, str, dict[str, tuple[str, Any]]], ...]:
    """Return all 408 owned v7 D7 case descriptors in exact family order."""

    result: list[tuple[str, str, dict[str, tuple[str, Any]]]] = []
    target_ids = [1, 2, 3, 4, 5]
    for ordinal in range(3):
        result.append(
            ("OBS_BITS", "mapping-mutants", {"mutant_ordinal": ("u64", ordinal)})
        )
    for ordinal in range(2):
        result.append(
            (
                "OBS_UNITS",
                "check-mutants",
                {
                    "case_ordinal": ("u64", ordinal),
                    "target_unit_ids": ("u64-list", target_ids),
                },
            )
        )
    for ordinal in range(2, 4):
        result.append(
            (
                "OBS_UNITS",
                "check-mutants",
                {
                    "case_ordinal": ("u64", ordinal),
                    "section_id": ("u64", 2),
                },
            )
        )
    for ordinal in range(3):
        result.append(
            (
                "OBS_UNITS",
                "code-mutants",
                {
                    "case_ordinal": ("u64", ordinal),
                    "target_unit_ids": ("u64-list", target_ids),
                },
            )
        )
    result.append(
        (
            "OBS_BITS",
            "route-conflicts",
            {"alternate_profile_version": ("u64", 3)},
        )
    )
    for version in (2, 3, 4, 5, 6):
        result.append(
            (
                "OBS_UNITS",
                "cross-profile-splices",
                {
                    "source_profile_version": ("u64", version),
                    "target_unit_ids": ("u64-list", target_ids),
                },
            )
        )
    result.append(
        (
            "OBS_UNITS",
            "valid-copy-conflicts",
            {"section_id": ("u64", 1), "target_unit_id": ("u64", 1)},
        )
    )
    for ordinal in range(256):
        result.append(
            (
                "OBS_MATRIX",
                "d2-one-beyond",
                {"d2_ordinal": ("u64", ordinal), "side": ("u64", 56)},
            )
        )
    for ordinal in range(128):
        result.append(
            (
                "OBS_MATRIX",
                "d3-one-beyond",
                {"seed": ("u64", 5_134_751_402_299_490_304 + ordinal)},
            )
        )
    result.append(
        (
            "OBS_UNITS",
            "missing-unit-one-beyond",
            {"omitted_unit_ids": ("u64-list", target_ids)},
        )
    )
    for errors, erasures in ((2, 0), (1, 2), (0, 4)):
        result.append(
            (
                "OBS_MATRIX",
                "algebraic-one-beyond",
                {
                    "erasures": ("u64", erasures),
                    "errors": ("u64", errors),
                    "target_unit_ids": ("u64-list", target_ids),
                },
            )
        )
    for declared in (268_435_457, 16_777_217):
        result.append(
            (
                "OBS_BITS",
                "resource-route-one-beyond",
                {"declared_value": ("u64", declared)},
            )
        )
    result.append(
        ("OBS_BITS", "geometry-one-beyond", {"side": ("u64", 2_056)})
    )
    if len(result) != 408:
        _fail("r3-d7-count")
    return tuple(result)


def _validate_case_v1(
    row: object,
    family: str,
    ordinal: int,
    candidate: _CandidateV1,
    d2: tuple[tuple[int, int], ...],
    d3_cache: dict[int, list[list[int]]],
    d3_population_cache: dict[int, tuple[int, ...]],
    d7: Sequence[tuple[str, str, dict[str, tuple[str, Any]]]],
) -> dict[str, Any]:
    value = _keys(row, _CASE_KEYS, "r3-damage-case")
    if value["case_id"] != f"{family}-{ordinal:06d}" or value["family_id"] != family:
        _fail("r3-damage-case-id")
    _hex64(value["observation_sha256"], "r3-damage-case-sha256")
    _hex64(value["decoder_result_sha256"], "r3-damage-case-sha256")
    if value["expected_artifact_state"] not in _ARTIFACT_STATES:
        _fail("r3-damage-case-state")
    _u64(value["wrong_accept_count"], "r3-damage-case-wrong")
    state_rows = _array(
        value["expected_section_states"], len(candidate.sections), "r3-damage-case-sections"
    )
    expected_ids = [int(item["section_id"]) for item in candidate.sections]
    observed_ids: list[int] = []
    for raw_state in state_rows:
        state = _keys(raw_state, _SECTION_STATE_KEYS, "r3-damage-case-section")
        observed_ids.append(
            _u64(state["section_id"], "r3-damage-case-section", 1, 0xFFFF_FFFF)
        )
        if state["state"] not in _SECTION_STATES:
            _fail("r3-damage-case-section")
    if observed_ids != expected_ids:
        _fail("r3-damage-case-section-order")
    parameters = _parameter_map(value["parameter_projection"])
    if family == "D0":
        expected = (
            "OBS_BITS",
            "clean-transform-polarity",
            {
                "polarity_id": ("u64", ordinal % 2),
                "transform_id": ("u64", ordinal // 2),
            },
        )
    elif family == "D1":
        expected = (
            "OBS_MATRIX",
            "erase-one-complete-shell-sector",
            {"sector_id": ("u64", ordinal)},
        )
    elif family == "D2":
        expected = (
            "OBS_MATRIX",
            "erase-square-in-protected-interior",
            {
                "side": ("u64", 55),
                "top_left": ("coordinate-list", [list(d2[ordinal])]),
            },
        )
    elif family == "D3":
        if ordinal not in d3_cache:
            d3_cache[ordinal] = _r3_d3_coordinates(
                candidate, ordinal, d3_population_cache
            )
        expected = (
            "OBS_MATRIX",
            "fixed-weight-unknown-bit-substitution",
            {
                "coordinates": ("coordinate-list", d3_cache[ordinal]),
                "seed": ("u64", 5_134_751_402_299_490_304 + ordinal),
                "stratum_id": ("u64", ordinal // 32),
            },
        )
    elif family == "D4":
        expected = (
            "OBS_UNITS",
            "omit-one-physical-unit-observation",
            {"omitted_unit_id": ("u64", ordinal + 1)},
        )
    elif family == "D5":
        expected = (
            "OBS_UNITS",
            "permute-intact-physical-unit-observations",
            {"permutation_ordinal": ("u64", ordinal)},
        )
    elif family == "D6":
        expected = (
            "OBS_MATRIX",
            "erase-shell-sector-union-one-physical-unit-cell-set",
            {
                "sector_id": ("u64", ordinal // 1_841),
                "unit_id": ("u64", ordinal % 1_841 + 1),
            },
        )
    else:
        expected = d7[ordinal]
    if (value["channel"], value["operator"], parameters) != expected:
        _fail("r3-damage-case-owner")
    return value


def _render_r3_shard(
    damage_identity: str,
    family_id: str,
    shard_ordinal: int,
    case_first: int,
    rows: Sequence[dict[str, Any]],
) -> bytes:
    summary: dict[str, object] = {
        "case_count": len(rows),
        "wrong_accept_count": _checked_sum(
            [int(row["wrong_accept_count"]) for row in rows],
            "r3-damage-wrong-overflow",
        ),
    }
    value: dict[str, object] = {
        "schema": "golden-board.m2-damage-cases/v1",
        "damage_manifest_identity": damage_identity,
        "profile_id": _R3_PROFILE_ID,
        "family_id": family_id,
        "shard_ordinal": shard_ordinal,
        "case_first": case_first,
        "case_rows": list(rows),
        "summary": summary,
    }
    manifest_identity = identity.identity_hex(
        _IDENTITY_DOMAIN, (canonical_manifest.serialize_manifest(value),)
    )
    value["summary"] = {**summary, "manifest_identity": manifest_identity}
    return canonical_manifest.serialize_manifest(value)


def _validate_damage_v1(
    raw: bytes,
    family_raws: Sequence[bytes],
    shard_raws: Sequence[bytes],
    candidate: _CandidateV1,
) -> _DamageV1:
    if type(raw) is not bytes or not 1 <= len(raw) <= 1_048_576:
        _fail("r3-damage-file-size")
    value = _keys(
        _canonical(raw, "r3-damage-manifest"),
        _R3_DAMAGE_KEYS,
        "r3-damage-keys",
    )
    owner_fields = {
        "damage_policy_sha256": _R3_DAMAGE_POLICY_SHA256,
        "profile_policy_sha256": _R3_PROFILE_POLICY_SHA256,
        "profile_limits_sha256": _R3_PROFILE_LIMITS_SHA256,
        "bootstrap_spec_sha256": _R3_BOOTSTRAP_SPEC_SHA256,
        "route_data_sha256": _R3_ROUTE_DATA_SHA256,
        "recipient_package_sha256": _R3_RECIPIENT_PACKAGE_SHA256,
    }
    if (
        value["schema"] != "golden-board.m2-damage-manifest/v1"
        or value["profile_id"] != _R3_PROFILE_ID
        or value["candidate_manifest_sha256"] != _R3_CANDIDATE_SHA256
        or any(value[name] != expected for name, expected in owner_fields.items())
    ):
        _fail("r3-damage-binding")
    for name in (
        *owner_fields,
        "candidate_manifest_sha256",
        "clean_observation_sha256",
    ):
        _hex64(value[name], "r3-damage-sha256")
    damage_identity = _nested_identity(value, _DAMAGE_SUMMARY_KEYS)
    expected_counts = (16, 4, 256, 128, 1_841, 21, 7_364, 408)
    root_rows = _array(value["family_rows"], 8, "r3-damage-family-rows")
    count_rows = _array(
        value["summary"]["family_case_counts"], 8, "r3-damage-family-counts"
    )
    if len(root_rows) != 8 or len(count_rows) != 8:
        _fail("r3-damage-family-counts")
    for index, family_id in enumerate(_FAMILIES):
        if _keys(
            count_rows[index], _FAMILY_COUNT_KEYS, "r3-damage-family-count"
        ) != {"family_id": family_id, "case_count": expected_counts[index]}:
            _fail("r3-damage-family-count")
    boundary_rows = _array(value["boundary_kat_rows"], 4, "r3-damage-boundary")
    if len(boundary_rows) != 4:
        _fail("r3-damage-boundary")
    boundary_pass = True
    for index, raw_row in enumerate(boundary_rows):
        row = _keys(raw_row, _BOUNDARY_ROW_KEYS, "r3-damage-boundary")
        if (
            row["kat_id"] != _R3_BOUNDARY_KAT_IDS[index]
            or _hex64(row["result_sha256"], "r3-damage-boundary")
            != _R3_BOUNDARY_KAT_SHA256[index]
            or row["result"] not in ("pass", "fail")
        ):
            _fail("r3-damage-boundary")
        boundary_pass = boundary_pass and row["result"] == "pass"

    if isinstance(family_raws, (bytes, bytearray, str)) or len(family_raws) != 8:
        _fail("r3-damage-family-files")
    if (
        isinstance(shard_raws, (bytes, bytearray, str))
        or not 8 <= len(shard_raws) <= 10_038
    ):
        _fail("r3-damage-shard-files")
    all_raws = (raw, *family_raws, *shard_raws)
    if any(type(item) is not bytes or len(item) > 1_048_576 for item in all_raws):
        _fail("r3-damage-file-size")
    if _checked_sum([len(item) for item in all_raws], "r3-damage-aggregate") > 536_870_912:
        _fail("r3-damage-aggregate")

    families: dict[str, tuple[bytes, dict[str, Any]]] = {}
    family_order: list[str] = []
    for family_raw in family_raws:
        document = _keys(
            _canonical(family_raw, "r3-damage-family"),
            _FAMILY_KEYS,
            "r3-damage-family-keys",
        )
        family_id = document.get("family_id")
        if type(family_id) is not str or family_id not in _FAMILIES or family_id in families:
            _fail("r3-damage-family-id")
        family_order.append(family_id)
        families[family_id] = (family_raw, document)
    if tuple(family_order) != _FAMILIES:
        _fail("r3-damage-family-order")

    shards: dict[tuple[str, int], tuple[bytes, dict[str, Any]]] = {}
    shard_order: list[tuple[str, int]] = []
    for shard_raw in shard_raws:
        document = _keys(
            _canonical(shard_raw, "r3-damage-shard"),
            _SHARD_KEYS,
            "r3-damage-shard-keys",
        )
        family_id = document.get("family_id")
        if type(family_id) is not str or family_id not in _FAMILIES:
            _fail("r3-damage-shard-id")
        ordinal = _u64(document.get("shard_ordinal"), "r3-damage-shard-id", 0, 10_037)
        key = (family_id, ordinal)
        if key in shards:
            _fail("r3-damage-shard-duplicate")
        shard_order.append(key)
        shards[key] = (shard_raw, document)
    if shard_order != sorted(shard_order, key=lambda item: (_FAMILIES.index(item[0]), item[1])):
        _fail("r3-damage-shard-order")

    d2 = _d2_placements(candidate, 55)
    d3_cache: dict[int, list[list[int]]] = {}
    d3_population_cache: dict[int, tuple[int, ...]] = {}
    d7 = _r3_expected_d7()
    cases: dict[str, tuple[dict[str, Any], ...]] = {}
    family_results: dict[str, str] = {}
    used_shards: set[tuple[str, int]] = set()
    root_wrong: list[int] = []
    for index, family_id in enumerate(_FAMILIES):
        _, family = families[family_id]
        if (
            family["schema"] != "golden-board.m2-damage-family/v1"
            or family["damage_manifest_identity"] != damage_identity
            or family["profile_id"] != _R3_PROFILE_ID
            or family["guarantee_id"] != _GUARANTEES[index]
        ):
            _fail("r3-damage-family-binding")
        _nested_identity(family, _FAMILY_SUMMARY_KEYS)
        refs = _array(family["shard_rows"], expected_counts[index], "r3-damage-shard-refs")
        joined: list[dict[str, Any]] = []
        shard_slices: list[tuple[int, int, bytes]] = []
        first = 0
        for ordinal, raw_ref in enumerate(refs):
            ref = _keys(raw_ref, _SHARD_REF_KEYS, "r3-damage-shard-ref")
            if ref["shard_ordinal"] != ordinal or ref["case_first"] != first:
                _fail("r3-damage-shard-ref")
            count = _u64(ref["case_count"], "r3-damage-shard-ref", 1, 256)
            digest = _hex64(ref["manifest_sha256"], "r3-damage-shard-ref")
            key = (family_id, ordinal)
            if key not in shards:
                _fail("r3-damage-shard-missing")
            shard_raw, shard = shards[key]
            used_shards.add(key)
            if (
                sha256(shard_raw).hexdigest() != digest
                or shard["schema"] != "golden-board.m2-damage-cases/v1"
                or shard["damage_manifest_identity"] != damage_identity
                or shard["profile_id"] != _R3_PROFILE_ID
                or shard["family_id"] != family_id
                or shard["shard_ordinal"] != ordinal
                or shard["case_first"] != first
            ):
                _fail("r3-damage-shard-binding")
            _nested_identity(shard, _SHARD_SUMMARY_KEYS)
            raw_cases = _array(shard["case_rows"], 256, "r3-damage-shard-cases")
            wrong = _checked_sum(
                [
                    _u64(
                        item.get("wrong_accept_count") if type(item) is dict else None,
                        "r3-damage-case-wrong",
                    )
                    for item in raw_cases
                ],
                "r3-damage-wrong-overflow",
            )
            if (
                len(raw_cases) != count
                or shard["summary"]["case_count"] != count
                or shard["summary"]["wrong_accept_count"] != wrong
                or _render_r3_shard(
                    damage_identity, family_id, ordinal, first, raw_cases
                )
                != shard_raw
            ):
                _fail("r3-damage-shard-summary")
            joined.extend(raw_cases)
            shard_slices.append((first, count, shard_raw))
            first += count
        if first != expected_counts[index]:
            _fail("r3-damage-family-case-count")
        for ordinal, (case_first, count, _) in enumerate(shard_slices):
            if count < 256 and case_first + count < len(joined):
                expanded = joined[case_first : case_first + count + 1]
                try:
                    expanded_raw = _render_r3_shard(
                        damage_identity, family_id, ordinal, case_first, expanded
                    )
                except canonical_manifest.ManifestError:
                    expanded_raw = None
                if expanded_raw is not None and len(expanded_raw) <= 1_048_576:
                    _fail("r3-damage-shard-not-maximal")
        validated = tuple(
            _validate_case_v1(
                row,
                family_id,
                ordinal,
                candidate,
                d2,
                d3_cache,
                d3_population_cache,
                d7,
            )
            for ordinal, row in enumerate(joined)
        )
        wrong = _checked_sum(
            [int(row["wrong_accept_count"]) for row in validated],
            "r3-damage-wrong-overflow",
        )
        family_summary = family["summary"]
        root = _keys(root_rows[index], _FAMILY_ROW_KEYS, "r3-damage-family-root")
        if (
            family_summary["case_count"] != len(validated)
            or family_summary["wrong_accept_count"] != wrong
            or family_summary["result"] not in ("pass", "fail")
            or root
            != {
                "family_id": family_id,
                "case_count": len(validated),
                "wrong_accept_count": wrong,
                "result": family_summary["result"],
                "case_rows_sha256": _canonical_array_sha256(list(validated)),
            }
        ):
            _fail("r3-damage-family-summary")
        required_ids = {
            int(row["section_id"])
            for row in candidate.sections
            if int(row["closure_class"]) == 128
        }
        family_pass = all(
            int(case["wrong_accept_count"]) == 0
            and _r3_gate6_case_guarantee(case, family_id, required_ids)
            for case in validated
        ) and (family_id != "D7" or boundary_pass)
        if family_summary["result"] != ("pass" if family_pass else "fail"):
            _fail("r3-damage-family-pass")
        cases[family_id] = validated
        family_results[family_id] = str(family_summary["result"])
        root_wrong.append(wrong)
    if used_shards != set(shards):
        _fail("r3-damage-shard-extra")
    total_wrong = _checked_sum(root_wrong, "r3-damage-wrong-overflow")
    if value["summary"]["wrong_accept_count"] != total_wrong:
        _fail("r3-damage-root-summary")
    if (
        total_wrong != 0
        or not boundary_pass
        or any(family_results[family_id] != "pass" for family_id in _FAMILIES)
    ):
        _fail("r3-damage-gate6-not-pass")
    return _DamageV1(raw, value, cases, family_results, boundary_pass)


def _shell_owner(candidate: _Candidate, row: int, column: int) -> tuple[int, int]:
    side, width = candidate.side, candidate.width
    last = side - 1
    if row < width and column < side - width:
        sector, u, v = 0, row, column
    elif column >= side - width and row < side - width:
        sector, u, v = 1, last - column, row
    elif row >= side - width and column >= width:
        sector, u, v = 2, last - row, last - column
    elif column < width and row >= width:
        sector, u, v = 3, column, last - row
    else:
        _fail("shell-coordinate")
    return sector, u * (side - width) + v


def _r3_mapping_evidence(candidate: _CandidateV1) -> int:
    """Enumerate every protected and fixed-pad logical cell once."""

    mapping = candidate.value["mapping"]
    population = candidate.population
    multiplier = int(mapping["cell_multiplier"])
    inverse = int(mapping["cell_inverse_multiplier"])
    offset = int(mapping["offset"])
    missing_target = 0xFFFF_FFFF
    targets = array("I", (missing_target,)) * population
    counts = bytearray(population)
    round_trip_bad = bytearray(population)
    for ordinal, unit in enumerate(candidate.units):
        unit_id = int(unit["physical_unit_id"])
        for bit_offset in range(1_728):
            identity_index = ordinal * 1_728 + bit_offset
            physical = _r3_map_unit_bit(mapping, unit_id, bit_offset)
            targets[identity_index] = physical
            if counts[physical] < 2:
                counts[physical] += 1
            logical = (inverse * ((physical - offset) % population)) % population
            if (
                logical % 1_728 != bit_offset
                or _r3_invert_cell(mapping, physical) != (unit_id, bit_offset)
                or (multiplier * logical + offset) % population != physical
            ):
                round_trip_bad[identity_index] = 1
    for logical in range(candidate.protected_bits, population):
        physical = (multiplier * logical + offset) % population
        targets[logical] = physical
        if counts[physical] < 2:
            counts[physical] += 1
        if (inverse * ((physical - offset) % population)) % population != logical:
            round_trip_bad[logical] = 1
    violations = 0
    for identity_index, physical in enumerate(targets):
        if (
            physical == missing_target
            or round_trip_bad[identity_index]
            or counts[physical] != 1
        ):
            violations += 1
    return violations


def _r3_group_evidence(
    candidate: _CandidateV1, ownership: dict[str, Any]
) -> tuple[int, tuple[bool, ...], bytearray]:
    """Enumerate the five owned topology conditions for every logical group."""

    ownership_by_id = {
        int(row["physical_unit_id"]): row for row in ownership["unit_rows"]
    }
    protected_counts = bytearray(candidate.population)
    violations = 0
    malformed: list[bool] = []
    expected_first_id = 1
    for group in candidate.groups:
        first = group[0]
        section = candidate.section_by_id[int(first["section_id"])]
        _, expected_factor = _r3_copy_class(
            int(section["section_id"]),
            int(section["section_type"]),
            section["copy_class"],
        )
        factor_condition = (
            len(group) == expected_factor
            and all(
                int(row["physical_replica_count"]) == expected_factor
                and int(row["replica_index"]) == replica_index
                and int(row["section_id"]) == int(section["section_id"])
                and int(row["fragment_index"]) == int(first["fragment_index"])
                and ownership_by_id.get(int(row["physical_unit_id"]), {}).get(
                    "physical_replica_count"
                )
                == expected_factor
                and ownership_by_id.get(int(row["physical_unit_id"]), {}).get(
                    "replica_index"
                )
                == replica_index
                for replica_index, row in enumerate(group)
            )
        )
        ids = tuple(int(row["physical_unit_id"]) for row in group)
        id_condition = ids == tuple(
            range(expected_first_id, expected_first_id + expected_factor)
        )
        expected_first_id += expected_factor
        slots = tuple(int(row["slot"]) for row in group)
        slot_condition = len(set(slots)) == expected_factor and all(
            slot == (2 * (unit_id - 1)) % 1_841
            and ownership_by_id.get(unit_id, {}).get("slot") == slot
            for slot, unit_id in zip(slots, ids, strict=True)
        )
        span_condition = all(
            int(row["logical_bit_count"]) == 1_728
            and int(row["logical_bit_first"]) == 1_728 * int(row["slot"])
            and ownership_by_id.get(int(row["physical_unit_id"]), {}).get(
                "logical_bit_count"
            )
            == 1_728
            and ownership_by_id.get(int(row["physical_unit_id"]), {}).get(
                "logical_bit_first"
            )
            == int(row["logical_bit_first"])
            for row in group
        )
        cell_condition = True
        group_cells: set[int] = set()
        for row in group:
            unit_id = int(row["physical_unit_id"])
            lane_cells: set[int] = set()
            lane_digest = sha256()
            for bit_offset in range(1_728):
                physical = _r3_map_unit_bit(
                    candidate.value["mapping"], unit_id, bit_offset
                )
                lane_digest.update(physical.to_bytes(4, "big"))
                if physical in lane_cells or physical in group_cells:
                    cell_condition = False
                lane_cells.add(physical)
                if protected_counts[physical] < 2:
                    protected_counts[physical] += 1
            group_cells.update(lane_cells)
            owner_row = ownership_by_id.get(unit_id)
            if (
                len(lane_cells) != 1_728
                or owner_row is None
                or owner_row.get("mapped_cell_sha256") != lane_digest.hexdigest()
            ):
                cell_condition = False
        conditions = (
            factor_condition,
            id_condition,
            slot_condition,
            span_condition,
            cell_condition,
        )
        violations += sum(not condition for condition in conditions)
        malformed.append(not all(conditions))
    if expected_first_id != 1_842:
        # The failure belongs to the final group's contiguous-ID condition.
        if malformed:
            violations += not malformed[-1]
            malformed[-1] = True
    return violations, tuple(malformed), protected_counts


def _r3_cell_evidence(
    candidate: _CandidateV1,
    ownership: dict[str, Any],
    protected_counts: bytearray,
) -> tuple[int, int, dict[str, int]]:
    """Enumerate the exact row-major 9-byte ownership table and four sectors."""

    table_hash = sha256()
    class_counts = {
        "shell-route": 0,
        "shell-headroom": 0,
        "shell-fixed-pad": 0,
        "real-protected": 0,
        "capacity-probe": 0,
        "reserve-probe": 0,
        "load-probe": 0,
        "interior-fixed-pad": 0,
    }
    sector_counts = [0, 0, 0, 0]
    cell_violations = 0
    pad_offset = 0
    for row in range(candidate.side):
        chunk = bytearray()
        for column in range(candidate.side):
            if (
                row < candidate.width
                or row >= candidate.side - candidate.width
                or column < candidate.width
                or column >= candidate.side - candidate.width
            ):
                sector, local = _shell_owner(candidate, row, column)
                sector_counts[sector] += 1
                shell = candidate.value["shell_rows"][sector]
                prefix = int(shell["route_prefix_cells"])
                headroom = int(shell["headroom_cells"])
                if local < prefix:
                    kind, owner_offset, class_id = 1, local, "shell-route"
                elif local < prefix + headroom:
                    kind, owner_offset, class_id = (
                        2,
                        local - prefix,
                        "shell-headroom",
                    )
                else:
                    kind, owner_offset, class_id = (
                        3,
                        local - prefix - headroom,
                        "shell-fixed-pad",
                    )
                owner_id = sector
            else:
                physical = (
                    (row - candidate.width) * candidate.interior
                    + column
                    - candidate.width
                )
                inverse = _r3_invert_cell(candidate.value["mapping"], physical)
                cell_bad = False
                if inverse is None:
                    cell_bad = protected_counts[physical] != 0
                    kind, owner_id, owner_offset, class_id = (
                        5,
                        0,
                        pad_offset,
                        "interior-fixed-pad",
                    )
                    pad_offset += 1
                else:
                    unit_id, bit_offset = inverse
                    cell_bad = protected_counts[physical] != 1
                    unit = candidate.unit_by_id.get(unit_id)
                    if unit is None:
                        cell_bad = True
                        kind, owner_id, owner_offset, class_id = (
                            5,
                            0,
                            pad_offset,
                            "interior-fixed-pad",
                        )
                        pad_offset += 1
                    else:
                        section_type = int(
                            candidate.section_by_id[int(unit["section_id"])][
                                "section_type"
                            ]
                        )
                        class_id = (
                            "real-protected"
                            if section_type <= 3
                            else {
                                4: "capacity-probe",
                                5: "reserve-probe",
                                6: "load-probe",
                            }[section_type]
                        )
                        kind, owner_id, owner_offset = 4, unit_id, bit_offset
                if cell_bad:
                    cell_violations += 1
            class_counts[class_id] += 1
            chunk.extend(
                bytes((kind,))
                + owner_id.to_bytes(4, "big")
                + owner_offset.to_bytes(4, "big")
            )
        table_hash.update(chunk)
    if pad_offset != candidate.population - candidate.protected_bits:
        cell_violations += 1
    if (
        ownership["cell_table"]["row_count"] != candidate.side * candidate.side
        or table_hash.hexdigest() != ownership["cell_table_sha256"]
    ):
        cell_violations += 1

    sector_cells = candidate.width * (candidate.side - candidate.width)
    shell_violations = sum(
        count != sector_cells
        or int(candidate.value["shell_rows"][sector]["route_prefix_cells"])
        + int(candidate.value["shell_rows"][sector]["headroom_cells"])
        + int(candidate.value["shell_rows"][sector]["fixed_pad_cells"])
        != sector_cells
        for sector, count in enumerate(sector_counts)
    )
    if 4 * sector_cells != candidate.side * candidate.side - candidate.population:
        shell_violations += 1
    return cell_violations, shell_violations, class_counts


def _r3_owner_factor_evidence(
    candidate: _CandidateV1, class_counts: dict[str, int]
) -> int:
    ledger = candidate.value["ledger"]
    expected_classes = {
        "shell-route": int(ledger["shell_instruction_cells"])
        + int(ledger["shell_example_cells"])
        + int(ledger["shell_recipe_cells"]),
        "shell-headroom": int(ledger["shell_headroom_cells"]),
        "shell-fixed-pad": int(ledger["shell_fixed_pad_cells"]),
        "real-protected": int(ledger["real_protected_cells"]),
        "capacity-probe": int(ledger["capacity_probe_cells"]),
        "reserve-probe": int(ledger["reserve_probe_cells"]),
        "load-probe": int(ledger["load_probe_cells"]),
        "interior-fixed-pad": int(ledger["interior_fixed_pad_cells"]),
    }
    violations = sum(
        class_counts[name] != expected for name, expected in expected_classes.items()
    )
    if sum(class_counts.values()) != candidate.side * candidate.side:
        violations += 1
    for factor, expected in (
        (1, (807, 807, 1_394_496)),
        (2, (442, 884, 1_527_552)),
        (5, (30, 150, 259_200)),
    ):
        groups = sum(int(group[0]["physical_replica_count"]) == factor for group in candidate.groups)
        units = sum(
            len(group)
            for group in candidate.groups
            if int(group[0]["physical_replica_count"]) == factor
        )
        if (groups, units, 1_728 * units) != expected:
            violations += 1
    return violations


def _r3_lane_pair_separated(
    candidate: _CandidateV1, first_id: int, second_id: int, bit_offset: int
) -> bool:
    first = _r3_map_unit_bit(candidate.value["mapping"], first_id, bit_offset)
    second = _r3_map_unit_bit(candidate.value["mapping"], second_id, bit_offset)
    first_row, first_column = divmod(first, candidate.interior)
    second_row, second_column = divmod(second, candidate.interior)
    return max(
        abs(first_row - second_row), abs(first_column - second_column)
    ) >= max(32, candidate.interior // 8)


def _r3_lane_separation_evidence(candidate: _CandidateV1) -> tuple[int, int]:
    witnesses = 0
    violations = 0
    for group in candidate.groups:
        if len(group) not in (2, 5):
            continue
        ids = tuple(int(row["physical_unit_id"]) for row in group)
        for first_index in range(len(ids)):
            for second_index in range(first_index + 1, len(ids)):
                for bit_offset in range(1_728):
                    witnesses += 1
                    if not _r3_lane_pair_separated(
                        candidate,
                        ids[first_index],
                        ids[second_index],
                        bit_offset,
                    ):
                        violations += 1
    return witnesses, violations


def _r3_closure_evidence(
    candidate: _CandidateV1, damage: _DamageV1
) -> tuple[int, int]:
    required_ids = tuple(
        int(row["section_id"])
        for row in candidate.sections
        if int(row["closure_class"]) == 128
    )
    if required_ids != (1, 2, 3, 16):
        _fail("r3-required-closure")
    witnesses = 0
    violations = 0
    group_by_unit = {
        int(row["physical_unit_id"]): group
        for group in candidate.groups
        for row in group
    }
    for case in damage.cases["D2"]:
        parameters = _parameter_map(case["parameter_projection"])
        side = int(parameters["side"][1])
        top, left = parameters["top_left"][1][0]
        erased: dict[tuple[int, int, int], set[int]] = {}
        for row in range(top, top + side):
            for column in range(left, left + side):
                physical = (
                    (row - candidate.width) * candidate.interior
                    + column
                    - candidate.width
                )
                inverse = _r3_invert_cell(candidate.value["mapping"], physical)
                if inverse is None:
                    continue
                unit_id, bit_offset = inverse
                unit = candidate.unit_by_id[unit_id]
                section_id = int(unit["section_id"])
                if section_id in required_ids:
                    erased.setdefault(
                        (section_id, int(unit["fragment_index"]), bit_offset), set()
                    ).add(int(unit["replica_index"]))
        group_damage: dict[
            tuple[int, int], tuple[list[list[int]], list[int]]
        ] = {}
        for (section_id, fragment_index, bit_offset), lanes in erased.items():
            group = next(
                group
                for group in candidate.groups_by_section[section_id]
                if int(group[0]["fragment_index"]) == fragment_index
            )
            lane_counts, repetition_counts = group_damage.setdefault(
                (section_id, fragment_index),
                ([[0] * 24 for _ in group], [0] * 24),
            )
            codeword = bit_offset // 72
            for lane in lanes:
                lane_counts[lane][codeword] += 1
            if len(lanes) == len(group):
                repetition_counts[codeword] += 1
        for section_id in required_ids:
            witnesses += 1
            section_survives = True
            for group in candidate.groups_by_section[section_id]:
                counts = group_damage.get(
                    (section_id, int(group[0]["fragment_index"]))
                )
                if counts is None:
                    continue
                lane_counts, repetition_counts = counts
                if not (
                    any(all(count <= 3 for count in lane) for lane in lane_counts)
                    or all(count <= 3 for count in repetition_counts)
                ):
                    section_survives = False
                    break
            if not section_survives:
                violations += 1
    for family_id, parameter_id in (("D4", "omitted_unit_id"), ("D6", "unit_id")):
        for case in damage.cases[family_id]:
            omitted_id = int(_parameter_map(case["parameter_projection"])[parameter_id][1])
            omitted_group = group_by_unit.get(omitted_id)
            for section_id in required_ids:
                witnesses += 1
                survives = all(
                    sum(
                        int(row["physical_unit_id"]) != omitted_id for row in group
                    )
                    >= 1
                    for group in candidate.groups_by_section[section_id]
                )
                if omitted_group is None or not survives:
                    violations += 1
    return witnesses, violations


def _r3_inventory_closure_evidence(
    candidate: _CandidateV1,
    malformed_groups: Sequence[bool],
    class_counts: dict[str, int],
) -> tuple[int, int]:
    witnesses = 0
    violations = 0
    for malformed in malformed_groups:
        witnesses += 1
        violations += bool(malformed)
    for section in candidate.sections:
        for dependency in section["dependency_ids"]:
            witnesses += 1
            target = candidate.section_by_id.get(int(dependency))
            if target is None or int(target["section_id"]) == int(section["section_id"]):
                violations += 1
    for removed in range(4):
        witnesses += 1
        survivors = sum(
            sector != removed
            and int(row["route_prefix_cells"]) > 0
            and type(row["image_sha256"]) is str
            and len(row["image_sha256"]) == 64
            for sector, row in enumerate(candidate.value["shell_rows"])
        )
        if survivors != 3:
            violations += 1
    witnesses += 1
    ledger = candidate.value["ledger"]
    closure = (
        len(candidate.groups) == 1_279
        and sum(len(row["dependency_ids"]) for row in candidate.sections) == 78
        and sum(len(group) for group in candidate.groups) == 1_841
        and candidate.protected_bits + int(ledger["interior_fixed_pad_cells"])
        == candidate.population
        and sum(class_counts.values()) == candidate.side * candidate.side
        and int(ledger["total_cells"]) == candidate.side * candidate.side
        and len(ledger["logical_bytes_by_owner"]) == len(candidate.sections)
    )
    if not closure:
        violations += 1
    return witnesses, violations


def _r3_gate6_case_guarantee(
    case: dict[str, Any], family_id: str, required_ids: set[int]
) -> bool:
    states = {
        int(row["section_id"]): str(row["state"])
        for row in case["expected_section_states"]
    }
    exact = {"verified", "recovered"}
    if family_id in ("D0", "D1", "D5"):
        return all(state in exact for state in states.values())
    if family_id in ("D2", "D3", "D4", "D6"):
        return all(states.get(section_id) in exact for section_id in required_ids)
    return family_id == "D7"


def _r3_case_guarantee(
    case: dict[str, Any], family_id: str, required_ids: set[int]
) -> bool:
    states = {
        int(row["section_id"]): str(row["state"])
        for row in case["expected_section_states"]
    }
    exact = {"verified", "recovered"}
    if family_id in ("D0", "D1", "D5"):
        return case["expected_artifact_state"] == "exact" and all(
            state in exact for state in states.values()
        )
    if family_id in ("D2", "D3", "D4", "D6"):
        return all(states.get(section_id) in exact for section_id in required_ids)
    return family_id == "D7"


def _r3_damage_promise_evidence(
    candidate: _CandidateV1, damage: _DamageV1
) -> tuple[int, int]:
    required_ids = {
        int(row["section_id"])
        for row in candidate.sections
        if int(row["closure_class"]) == 128
    }
    witnesses = 0
    violations = 0
    for family_id in _FAMILIES:
        family_pass = damage.family_results[family_id] == "pass" and (
            family_id != "D7" or damage.boundary_pass
        )
        for case in damage.cases[family_id]:
            witnesses += 1
            if (
                not family_pass
                or int(case["wrong_accept_count"]) != 0
                or not _r3_case_guarantee(case, family_id, required_ids)
            ):
                violations += 1
    return witnesses, violations


def _cell_evidence(candidate: _Candidate, ownership: dict[str, Any]) -> tuple[int, int, int, int, dict[str, int]]:
    mapping = candidate.value["mapping"]
    multiplier = int(mapping["multiplier"])
    offset = int(mapping["offset"])
    inverse = int(mapping["inverse_multiplier"])
    seen = bytearray((candidate.population + 7) // 8)
    affine_violations = 0
    for logical in range(candidate.population):
        physical = (multiplier * logical + offset) % candidate.population
        if (inverse * (physical - offset)) % candidate.population != logical:
            affine_violations += 1
        byte, bit = divmod(physical, 8)
        mask = 1 << bit
        if seen[byte] & mask:
            affine_violations += 1
        seen[byte] |= mask
    if gcd(multiplier, candidate.population) != 1:
        affine_violations += 1

    table_hash = sha256()
    shell_sector_counts = [0, 0, 0, 0]
    class_counts = {
        "shell-route": 0,
        "shell-headroom": 0,
        "shell-fixed-pad": 0,
        "real-protected": 0,
        "capacity-probe": 0,
        "reserve-probe": 0,
        "load-probe": 0,
        "interior-fixed-pad": 0,
    }
    partition_violations = 0
    protected_violations = 0
    pad_offset = 0
    shell_rows = candidate.value["shell_rows"]
    for row in range(candidate.side):
        chunk = bytearray()
        for column in range(candidate.side):
            if (
                row < candidate.width
                or row >= candidate.side - candidate.width
                or column < candidate.width
                or column >= candidate.side - candidate.width
            ):
                sector, local = _shell_owner(candidate, row, column)
                shell_sector_counts[sector] += 1
                shell = shell_rows[sector]
                prefix = int(shell["route_prefix_cells"])
                headroom = int(shell["headroom_cells"])
                if local < prefix:
                    kind, owner_offset, class_id = 1, local, "shell-route"
                elif local < prefix + headroom:
                    kind, owner_offset, class_id = 2, local - prefix, "shell-headroom"
                else:
                    kind, owner_offset, class_id = 3, local - prefix - headroom, "shell-fixed-pad"
                owner_id = sector
            else:
                physical = (row - candidate.width) * candidate.interior + column - candidate.width
                logical = (inverse * (physical - offset)) % candidate.population
                if (multiplier * logical + offset) % candidate.population != physical:
                    partition_violations += 1
                if logical < candidate.protected_bits:
                    unit_ordinal, owner_offset = divmod(logical, candidate.unit_bits)
                    if unit_ordinal >= len(candidate.units):
                        protected_violations += 1
                        owner_id = 0
                        class_id = "interior-fixed-pad"
                        kind, owner_offset = 5, pad_offset
                        pad_offset += 1
                    else:
                        unit = candidate.units[unit_ordinal]
                        owner_id = int(unit["physical_unit_id"])
                        section_type = int(candidate.section_by_id[int(unit["section_id"])]["section_type"])
                        class_id = (
                            "real-protected"
                            if section_type <= 3
                            else {4: "capacity-probe", 5: "reserve-probe", 6: "load-probe"}[section_type]
                        )
                        kind = 4
                else:
                    kind, owner_id, owner_offset, class_id = 5, 0, pad_offset, "interior-fixed-pad"
                    pad_offset += 1
            class_counts[class_id] += 1
            chunk.extend(bytes((kind,)) + owner_id.to_bytes(4, "big") + owner_offset.to_bytes(4, "big"))
        table_hash.update(chunk)
    if pad_offset != candidate.population - candidate.protected_bits:
        partition_violations += 1
    table_violations = partition_violations + (table_hash.hexdigest() != ownership["cell_table_sha256"])
    shell_violations = sum(
        count != candidate.width * (candidate.side - candidate.width)
        for count in shell_sector_counts
    )
    return affine_violations, int(table_violations), int(shell_violations), protected_violations, class_counts


def _predicate_six(candidate: _Candidate) -> tuple[int, int]:
    required = {
        int(row["section_id"]) for row in candidate.sections if int(row["closure_class"]) == 128
    }
    unit_index: dict[tuple[int, int, int], list[dict[str, Any]]] = {}
    unit_ids: set[int] = set()
    violations = 0
    for unit in candidate.units:
        key = (int(unit["section_id"]), int(unit["semantic_copy_id"]), int(unit["fragment_index"]))
        unit_index.setdefault(key, []).append(unit)
        unit_id = int(unit["physical_unit_id"])
        if unit_id in unit_ids:
            violations += 1
        unit_ids.add(unit_id)
    witnesses: set[tuple[object, ...]] = set()
    for section_id in sorted(required):
        section = candidate.section_by_id[section_id]
        for copy_id in range(int(section["copy_count"])):
            for fragment in range(int(section["fragment_count"])):
                key = (section_id, copy_id, fragment)
                witnesses.add(("section-fragment", *key))
                if len(unit_index.get(key, ())) != 1:
                    violations += 1
        for dependency in section["dependency_ids"]:
            target = candidate.section_by_id.get(int(dependency))
            if target is None:
                violations += 1
                continue
            for copy_id in range(int(target["copy_count"])):
                witnesses.add(("dependency-edge", section_id, int(dependency), copy_id))
                if not candidate.units_by_section_copy.get((int(dependency), copy_id)):
                    violations += 1
    inventory = candidate.section_by_id.get(1)
    if inventory is None:
        violations += 1
    else:
        for copy_id in range(int(inventory["copy_count"])):
            witnesses.add(("inventory-copy", 1, copy_id))
            if not candidate.units_by_section_copy.get((1, copy_id)):
                violations += 1
    return len(witnesses), violations


def _recoverable_units_for_square(
    candidate: _Candidate, top: int, left: int, side: int
) -> set[int]:
    inverse = int(candidate.value["mapping"]["inverse_multiplier"])
    offset = int(candidate.value["mapping"]["offset"])
    erased_bits: dict[int, set[int]] = {}
    for row in range(top, top + side):
        for column in range(left, left + side):
            physical = (row - candidate.width) * candidate.interior + column - candidate.width
            logical = (inverse * (physical - offset)) % candidate.population
            if logical >= candidate.protected_bits:
                continue
            unit_ordinal, bit = divmod(logical, candidate.unit_bits)
            unit_id = int(candidate.units[unit_ordinal]["physical_unit_id"])
            erased_bits.setdefault(unit_id, set()).add(bit)
    recoverable = {int(row["physical_unit_id"]) for row in candidate.units}
    for unit_id, bits in erased_bits.items():
        if candidate.profile.transport_id == m2_codec.EH_TRANSPORT:
            counts: dict[int, int] = {}
            for bit in bits:
                counts[bit // 72] = counts.get(bit // 72, 0) + 1
            good = all(count <= 3 for count in counts.values())
        else:
            good = len({bit // 8 for bit in bits}) <= 64
        if not good:
            recoverable.discard(unit_id)
    return recoverable


def _section_survives(
    candidate: _Candidate, section_id: int, recoverable: set[int]
) -> bool:
    section = candidate.section_by_id[section_id]
    return any(
        all(
            int(unit["physical_unit_id"]) in recoverable
            for unit in candidate.units_by_section_copy[(section_id, copy_id)]
        )
        for copy_id in range(int(section["copy_count"]))
    )


def _predicate_eight(candidate: _Candidate, damage: _Damage) -> tuple[int, int]:
    required = tuple(
        int(row["section_id"]) for row in candidate.sections if int(row["closure_class"]) == 128
    )
    all_units = {int(row["physical_unit_id"]) for row in candidate.units}
    witnesses = 0
    violations = 0
    for family in ("D2", "D4", "D6"):
        for case in damage.cases[family]:
            parameters = _parameter_map(case["parameter_projection"])
            if family == "D2":
                side = int(parameters["side"][1])
                top, left = parameters["top_left"][1][0]
                recoverable = _recoverable_units_for_square(candidate, top, left, side)
            else:
                omitted_id = int(
                    parameters["omitted_unit_id"][1] if family == "D4" else parameters["unit_id"][1]
                )
                recoverable = all_units - {omitted_id}
            for section_id in required:
                witnesses += 1
                if not _section_survives(candidate, section_id, recoverable):
                    violations += 1
    return witnesses, violations


def _case_guarantee(case: dict[str, Any], family: str, required: set[int]) -> bool:
    states = {int(row["section_id"]): row["state"] for row in case["expected_section_states"]}
    exact = {"verified", "recovered"}
    if family in ("D0", "D1", "D5"):
        return case["expected_artifact_state"] == "exact" and all(state in exact for state in states.values())
    if family in ("D2", "D3", "D4", "D6"):
        return all(states.get(section_id) in exact for section_id in required)
    return True


def _predicate_nine(candidate: _Candidate, damage: _Damage) -> tuple[int, int]:
    required = {
        int(row["section_id"]) for row in candidate.sections if int(row["closure_class"]) == 128
    }
    witnesses = 0
    violations = 0
    for family in _FAMILIES:
        family_pass = damage.family_results[family] == "pass" and (
            family != "D7" or damage.boundary_pass
        )
        for case in damage.cases[family]:
            witnesses += 1
            if (
                not family_pass
                or int(case["wrong_accept_count"]) != 0
                or not _case_guarantee(case, family, required)
            ):
                violations += 1
    return witnesses, violations


def _row(predicate_id: str, witness_count: int, floor: int, violations: int) -> dict[str, object]:
    _u64(witness_count, "proof-witness", 1)
    _u64(violations, "proof-violation")
    return {
        "predicate_id": predicate_id,
        "witness_count": witness_count,
        "minimum_surviving_count": floor,
        "violation_count": violations,
        "result": "pass" if violations == 0 and witness_count >= floor else "fail",
    }


def _build_independence_proof_v0(
    candidate_manifest_raw: bytes,
    ownership_ledger_raw: bytes,
    damage_manifest_raw: bytes,
    family_manifest_raws: Sequence[bytes],
    case_shard_raws: Sequence[bytes],
) -> IndependenceProof:
    """Build the exact gate-7 proof from bound retained evidence."""

    candidate = _validate_candidate(candidate_manifest_raw, ownership_ledger_raw)
    ownership = _validate_ownership(ownership_ledger_raw, candidate)
    damage = _validate_damage(
        damage_manifest_raw, family_manifest_raws, case_shard_raws, candidate
    )
    affine, table, shell, protected, class_counts = _cell_evidence(candidate, ownership)
    ledger = candidate.value["ledger"]
    expected_classes = {
        "shell-route": int(ledger["shell_instruction_cells"])
        + int(ledger["shell_example_cells"])
        + int(ledger["shell_recipe_cells"]),
        "shell-headroom": int(ledger["shell_headroom_cells"]),
        "shell-fixed-pad": int(ledger["shell_fixed_pad_cells"]),
        "real-protected": int(ledger["real_protected_cells"]),
        "capacity-probe": int(ledger["capacity_probe_cells"]),
        "reserve-probe": int(ledger["reserve_probe_cells"]),
        "load-probe": int(ledger["load_probe_cells"]),
        "interior-fixed-pad": int(ledger["interior_fixed_pad_cells"]),
    }
    class_violations = sum(class_counts[name] != expected for name, expected in expected_classes.items())
    if sum(class_counts.values()) != candidate.side * candidate.side:
        class_violations += 1
    separation_witnesses, separation_violations = _predicate_six(candidate)
    route_violations = 0
    for removed in range(4):
        survivors = sum(
            index != removed and int(row["route_prefix_cells"]) > 0
            for index, row in enumerate(candidate.value["shell_rows"])
        )
        if survivors != 3:
            route_violations += 1
    closure_witnesses, closure_violations = _predicate_eight(candidate, damage)
    promise_witnesses, promise_violations = _predicate_nine(candidate, damage)
    shell_cells = candidate.side * candidate.side - candidate.population
    rows = (
        _row(_PREDICATES[0], candidate.population, _FLOORS[0], affine),
        _row(_PREDICATES[1], candidate.side * candidate.side, _FLOORS[1], table),
        _row(_PREDICATES[2], shell_cells, _FLOORS[2], shell),
        _row(_PREDICATES[3], candidate.protected_bits, _FLOORS[3], protected),
        _row(_PREDICATES[4], candidate.side * candidate.side, _FLOORS[4], class_violations),
        _row(_PREDICATES[5], separation_witnesses, _FLOORS[5], separation_violations),
        _row(_PREDICATES[6], 4, _FLOORS[6], route_violations),
        _row(_PREDICATES[7], closure_witnesses, _FLOORS[7], closure_violations),
        _row(_PREDICATES[8], promise_witnesses, _FLOORS[8], promise_violations),
    )
    result = "pass" if all(row["result"] == "pass" for row in rows) else "fail"
    value: dict[str, object] = {
        "schema": SCHEMA,
        "profile_id": candidate.profile.profile_id,
        "candidate_manifest_sha256": sha256(candidate_manifest_raw).hexdigest(),
        "ownership_ledger_sha256": sha256(ownership_ledger_raw).hexdigest(),
        "damage_manifest_sha256": sha256(damage_manifest_raw).hexdigest(),
        "predicate_rows": list(rows),
        "summary": {"predicate_count": 9, "result": result},
    }
    manifest_identity = identity.identity_hex(
        _IDENTITY_DOMAIN, (canonical_manifest.serialize_manifest(value),)
    )
    value["summary"] = {
        "predicate_count": 9,
        "result": result,
        "manifest_identity": manifest_identity,
    }
    raw = canonical_manifest.serialize_manifest(value)
    return IndependenceProof(raw, manifest_identity, result, rows)


def _parse_independence_proof_v0(raw: bytes) -> IndependenceProof:
    """Validate the exact standalone proof schema and identity."""

    value = _keys(_canonical(raw, "independence-proof"), _PROOF_KEYS, "proof-keys")
    if value["schema"] != SCHEMA:
        _fail("proof-schema")
    profile_id = _ascii(value["profile_id"], "proof-profile")
    if profile_id not in {item.profile_id for item in m2_codec.candidate_profiles()}:
        _fail("proof-profile")
    for name in (
        "candidate_manifest_sha256",
        "ownership_ledger_sha256",
        "damage_manifest_sha256",
    ):
        _hex64(value[name], "proof-sha256")
    rows = _array(value["predicate_rows"], 9, "proof-predicates")
    if len(rows) != 9:
        _fail("proof-predicates")
    normalized: list[dict[str, object]] = []
    for index, raw_row in enumerate(rows):
        row = _keys(raw_row, _PREDICATE_ROW_KEYS, "proof-predicate")
        witness = _u64(row["witness_count"], "proof-predicate", 1)
        floor = _u64(row["minimum_surviving_count"], "proof-predicate", 1)
        violations = _u64(row["violation_count"], "proof-predicate")
        if (
            row["predicate_id"] != _PREDICATES[index]
            or floor != _FLOORS[index]
            or row["result"]
            != ("pass" if violations == 0 and witness >= _FLOORS[index] else "fail")
        ):
            _fail("proof-predicate")
        normalized.append(row)
    summary = _keys(value["summary"], _PROOF_SUMMARY_KEYS, "proof-summary")
    result = "pass" if all(row["result"] == "pass" for row in normalized) else "fail"
    if summary["predicate_count"] != 9 or summary["result"] != result:
        _fail("proof-summary")
    manifest_identity = _nested_identity(value, _PROOF_SUMMARY_KEYS)
    return IndependenceProof(raw, manifest_identity, result, tuple(normalized))


def _validate_independence_proof_v0(
    proof_raw: bytes,
    candidate_manifest_raw: bytes,
    ownership_ledger_raw: bytes,
    damage_manifest_raw: bytes,
    family_manifest_raws: Sequence[bytes],
    case_shard_raws: Sequence[bytes],
) -> IndependenceProof:
    """Recompute and byte-compare a retained gate-7 proof."""

    observed = _parse_independence_proof_v0(proof_raw)
    expected = _build_independence_proof_v0(
        candidate_manifest_raw,
        ownership_ledger_raw,
        damage_manifest_raw,
        family_manifest_raws,
        case_shard_raws,
    )
    if observed != expected:
        _fail("proof-mismatch")
    return observed


def _render_independence_proof_v1(
    candidate_manifest_sha256: str,
    ownership_ledger_sha256: str,
    damage_manifest_sha256: str,
    violation_counts: Sequence[int],
) -> IndependenceProof:
    """Render exact v1 bytes from nine complete enumeration totals."""

    if candidate_manifest_sha256 != _R3_CANDIDATE_SHA256:
        _fail("r3-proof-candidate-binding")
    for value in (
        candidate_manifest_sha256,
        ownership_ledger_sha256,
        damage_manifest_sha256,
    ):
        _hex64(value, "r3-proof-sha256")
    if isinstance(violation_counts, (bytes, bytearray, str)) or len(violation_counts) != 9:
        _fail("r3-proof-violations")
    rows: list[dict[str, object]] = []
    for index, violations_raw in enumerate(violation_counts):
        violations = _u64(violations_raw, "r3-proof-violations")
        rows.append(
            {
                "predicate_id": _R3_PREDICATES[index],
                "witness_count": _R3_WITNESS_COUNTS[index],
                "minimum_surviving_count": 1,
                "violation_count": violations,
                "result": "pass" if violations == 0 else "fail",
            }
        )
    result = "pass" if all(row["result"] == "pass" for row in rows) else "fail"
    value: dict[str, object] = {
        "schema": R3_SCHEMA,
        "profile_id": _R3_PROFILE_ID,
        "candidate_manifest_sha256": candidate_manifest_sha256,
        "ownership_ledger_sha256": ownership_ledger_sha256,
        "damage_manifest_sha256": damage_manifest_sha256,
        "predicate_rows": rows,
        "summary": {"predicate_count": 9, "result": result},
    }
    manifest_identity = identity.identity_hex(
        _IDENTITY_DOMAIN, (canonical_manifest.serialize_manifest(value),)
    )
    value["summary"] = {
        "predicate_count": 9,
        "result": result,
        "manifest_identity": manifest_identity,
    }
    raw = canonical_manifest.serialize_manifest(value)
    return IndependenceProof(raw, manifest_identity, result, tuple(rows))


def build_independence_proof_v1(
    candidate_manifest_raw: bytes,
    ownership_ledger_raw: bytes,
    damage_manifest_raw: bytes,
    family_manifest_raws: Sequence[bytes],
    case_shard_raws: Sequence[bytes],
) -> IndependenceProof:
    """Fully enumerate and render the promoted v7 gate-7 proof."""

    candidate = _validate_candidate_v1(candidate_manifest_raw, ownership_ledger_raw)
    ownership = _validate_ownership_v1(ownership_ledger_raw, candidate)
    damage = _validate_damage_v1(
        damage_manifest_raw, family_manifest_raws, case_shard_raws, candidate
    )

    mapping_violations = _r3_mapping_evidence(candidate)
    group_violations, malformed_groups, protected_counts = _r3_group_evidence(
        candidate, ownership
    )
    table_violations, shell_violations, class_counts = _r3_cell_evidence(
        candidate, ownership, protected_counts
    )
    factor_violations = _r3_owner_factor_evidence(candidate, class_counts)
    separation_witnesses, separation_violations = _r3_lane_separation_evidence(
        candidate
    )
    closure_witnesses, closure_violations = _r3_closure_evidence(candidate, damage)
    inventory_witnesses, inventory_violations = _r3_inventory_closure_evidence(
        candidate, malformed_groups, class_counts
    )
    promise_witnesses, promise_violations = _r3_damage_promise_evidence(
        candidate, damage
    )
    observed_witnesses = (
        candidate.population,
        candidate.side * candidate.side,
        candidate.side * candidate.side - candidate.population,
        candidate.protected_bits,
        candidate.side * candidate.side,
        separation_witnesses,
        closure_witnesses,
        inventory_witnesses,
        promise_witnesses,
    )
    if observed_witnesses != _R3_WITNESS_COUNTS:
        _fail("r3-proof-witness-count")
    return _render_independence_proof_v1(
        sha256(candidate_manifest_raw).hexdigest(),
        sha256(ownership_ledger_raw).hexdigest(),
        sha256(damage_manifest_raw).hexdigest(),
        (
            mapping_violations,
            table_violations,
            shell_violations,
            group_violations,
            factor_violations,
            separation_violations,
            closure_violations,
            inventory_violations,
            promise_violations,
        ),
    )


def parse_independence_proof_v1(raw: bytes) -> IndependenceProof:
    """Validate the exact standalone v1 proof, counts, floors, and identity."""

    value = _keys(
        _canonical(raw, "r3-independence-proof"), _PROOF_KEYS, "r3-proof-keys"
    )
    if value["schema"] != R3_SCHEMA or value["profile_id"] != _R3_PROFILE_ID:
        _fail("r3-proof-binding")
    for name in (
        "candidate_manifest_sha256",
        "ownership_ledger_sha256",
        "damage_manifest_sha256",
    ):
        _hex64(value[name], "r3-proof-sha256")
    if value["candidate_manifest_sha256"] != _R3_CANDIDATE_SHA256:
        _fail("r3-proof-candidate-binding")
    raw_rows = _array(value["predicate_rows"], 9, "r3-proof-predicates")
    if len(raw_rows) != 9:
        _fail("r3-proof-predicates")
    rows: list[dict[str, object]] = []
    for index, raw_row in enumerate(raw_rows):
        row = _keys(raw_row, _PREDICATE_ROW_KEYS, "r3-proof-predicate")
        witness = _u64(row["witness_count"], "r3-proof-predicate", 1)
        floor = _u64(row["minimum_surviving_count"], "r3-proof-predicate", 1)
        violations = _u64(row["violation_count"], "r3-proof-predicate")
        if (
            row["predicate_id"] != _R3_PREDICATES[index]
            or witness != _R3_WITNESS_COUNTS[index]
            or floor != 1
            or row["result"] != ("pass" if violations == 0 else "fail")
        ):
            _fail("r3-proof-predicate")
        rows.append(row)
    result = "pass" if all(row["result"] == "pass" for row in rows) else "fail"
    summary = _keys(value["summary"], _PROOF_SUMMARY_KEYS, "r3-proof-summary")
    if summary["predicate_count"] != 9 or summary["result"] != result:
        _fail("r3-proof-summary")
    manifest_identity = _nested_identity(value, _PROOF_SUMMARY_KEYS)
    return IndependenceProof(raw, manifest_identity, result, tuple(rows))


def validate_independence_proof_v1(
    proof_raw: bytes,
    candidate_manifest_raw: bytes,
    ownership_ledger_raw: bytes,
    damage_manifest_raw: bytes,
    family_manifest_raws: Sequence[bytes],
    case_shard_raws: Sequence[bytes],
) -> IndependenceProof:
    """Recompute all v1 rows and require retained bytes to be identical."""

    observed = parse_independence_proof_v1(proof_raw)
    expected = build_independence_proof_v1(
        candidate_manifest_raw,
        ownership_ledger_raw,
        damage_manifest_raw,
        family_manifest_raws,
        case_shard_raws,
    )
    if observed != expected:
        _fail("r3-proof-mismatch")
    return observed


def _document_schema(raw: bytes, reason: str) -> str:
    value = _canonical(raw, reason)
    schema = value.get("schema")
    if type(schema) is not str:
        _fail(reason)
    return schema


def build_independence_proof(
    candidate_manifest_raw: bytes,
    ownership_ledger_raw: bytes,
    damage_manifest_raw: bytes,
    family_manifest_raws: Sequence[bytes],
    case_shard_raws: Sequence[bytes],
) -> IndependenceProof:
    """Build v0 or v1 proof selected only by the exact candidate schema."""

    schema = _document_schema(candidate_manifest_raw, "candidate-manifest")
    if schema == "golden-board.m2-candidate-manifest/v0":
        return _build_independence_proof_v0(
            candidate_manifest_raw,
            ownership_ledger_raw,
            damage_manifest_raw,
            family_manifest_raws,
            case_shard_raws,
        )
    if schema == "golden-board.m2-candidate-manifest/v1":
        return build_independence_proof_v1(
            candidate_manifest_raw,
            ownership_ledger_raw,
            damage_manifest_raw,
            family_manifest_raws,
            case_shard_raws,
        )
    _fail("candidate-schema")


def parse_independence_proof(raw: bytes) -> IndependenceProof:
    """Parse a v0 or v1 proof without cross-version fallback."""

    schema = _document_schema(raw, "independence-proof")
    if schema == SCHEMA:
        return _parse_independence_proof_v0(raw)
    if schema == R3_SCHEMA:
        return parse_independence_proof_v1(raw)
    _fail("proof-schema")


def validate_independence_proof(
    proof_raw: bytes,
    candidate_manifest_raw: bytes,
    ownership_ledger_raw: bytes,
    damage_manifest_raw: bytes,
    family_manifest_raws: Sequence[bytes],
    case_shard_raws: Sequence[bytes],
) -> IndependenceProof:
    """Validate v0 or v1 proof selected by its exact schema."""

    schema = _document_schema(proof_raw, "independence-proof")
    if schema == SCHEMA:
        return _validate_independence_proof_v0(
            proof_raw,
            candidate_manifest_raw,
            ownership_ledger_raw,
            damage_manifest_raw,
            family_manifest_raws,
            case_shard_raws,
        )
    if schema == R3_SCHEMA:
        return validate_independence_proof_v1(
            proof_raw,
            candidate_manifest_raw,
            ownership_ledger_raw,
            damage_manifest_raw,
            family_manifest_raws,
            case_shard_raws,
        )
    _fail("proof-schema")


__all__ = (
    "SCHEMA",
    "R3_SCHEMA",
    "IndependenceError",
    "IndependenceProof",
    "build_independence_proof",
    "build_independence_proof_v1",
    "parse_independence_proof",
    "parse_independence_proof_v1",
    "validate_independence_proof",
    "validate_independence_proof_v1",
)
