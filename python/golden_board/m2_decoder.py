"""Bounded production recovery for the three frozen M2 observation channels.

This module deliberately does not accept a candidate manifestation, clean
carrier, damage operator, mutation coordinates, or expected result.  Square
observations discover their profile and mapping through complete surviving
shell routes.  Unit observations discover them through locally checked common
headers and a checked inventory.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import gcd, isqrt
from hashlib import sha256
import tomllib
from typing import NoReturn, Sequence

from . import bootstrap, canonical_manifest, m2_codec, m2_policy, m2_recipe


OBS_BITS = "OBS_BITS"
OBS_MATRIX = "OBS_MATRIX"
OBS_UNITS = "OBS_UNITS"
_MAX_BITS = 4_194_304
_MAX_SIDE = 2_048
_MAX_OBSERVATION_BYTES = 4_194_306
_CALIBRATIONS = tuple(
    bytes.fromhex(value)
    for value in (
        "f00fcc33aa559669817e24db18e742bd01fe02fd04fb08f710ef20df40bf807f",
        "cc33aa559669f00f02fd18e742bd817e04fb08f710ef20df40bf807f01fe24db",
        "aa559669f00fcc3304fb42bd817e24db08f710ef20df40bf807f01fe02fd18e7",
        "9669f00fcc33aa5508f7817e24db18e710ef20df40bf807f01fe02fd04fb42bd",
    )
)
_R3_FACT_STAGES = (0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5)
_R3_FACT_NAMES = (
    b"binary-relations-v0",
    b"entry-hypotheses-v0",
    b"unsigned-order-v0",
    b"row-major-msb-v0",
    b"route-recipe-framing-v0",
    b"recipe-language-status-bounds-v0",
    b"common-block-local-crc32c-v0",
    b"eh72-hier-repetition-v1",
    b"slot-affine-adapter-v1",
    b"group-fragment-adapter-v1",
    b"selected-section-check-inventory-v0",
    b"tier-frame-content-validation-v0",
)
_R3_TABLE_IDS = (3, 4, 5, 10, 11, 12, 13, 14, 15, 17, 18, 19, 20)


class DecoderError(ValueError):
    """Stable fail-closed production-decoder rejection."""

    __slots__ = ("reason",)

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class SectionResult:
    section_id: int
    state: str
    envelope: bytes | None


@dataclass(frozen=True, slots=True)
class FragmentDiagnostic:
    input_id: int
    profile_id: str
    section_id: int
    semantic_copy_id: int
    fragment_index: int
    state: str
    common_block: bytes | None
    replica_index: int = 0xFFFF
    physical_replica_count: int = 0xFFFF


@dataclass(frozen=True, slots=True)
class AcceptedHypothesis:
    transform_id: int
    polarity_id: int
    sector_id: int
    profile_id: str
    mapping_sha256: str


@dataclass(frozen=True, slots=True)
class ResourceUsage:
    section_attempts: int = 0
    primitive_steps: int = 0
    peak_scratch_bytes: int = 0


@dataclass(frozen=True, slots=True)
class DecodeResult:
    artifact_state: str
    profile_id: str | None
    section_results: tuple[SectionResult, ...]
    route_profile_ids: tuple[str, ...]
    inventory_available: bool
    fragment_diagnostics: tuple[FragmentDiagnostic, ...] = ()
    m2_required_stream: bytes | None = None
    m2_all_stream: bytes | None = None
    resource: ResourceUsage = ResourceUsage()
    accepted_hypotheses: tuple[AcceptedHypothesis, ...] = ()


@dataclass(frozen=True, slots=True)
class _ObservedUnit:
    unit_id: int
    encoded: bytes
    erasures: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _ExpectedUnit:
    unit_id: int
    section_id: int
    semantic_copy_id: int
    fragment_index: int
    fragment_count: int
    section_type: int
    section_version: int
    envelope_length: int
    replica_index: int = 0
    physical_replica_count: int = 1
    group_first_physical_unit_id: int = 0


@dataclass(frozen=True, slots=True)
class _Route:
    profile: m2_codec.CandidateProfile
    shell_width: int
    packages: tuple[bytes, ...]
    magic: bytes
    route_version: int
    mapping: tuple[int, int, int]
    inventory_section_id: int
    sector_id: int
    route_primitive_steps: int
    route_peak_scratch: int
    transport_primitive_steps: int
    transport_peak_scratch: int
    repetition_primitive_steps: int
    repetition_peak_scratch: int


def _fail(reason: str) -> NoReturn:
    raise DecoderError(reason)


def _packed(values: Sequence[int]) -> bytes:
    result = bytearray((len(values) + 7) // 8)
    for index, value in enumerate(values):
        if value not in (0, 1):
            _fail("bit-value")
        result[index // 8] |= value << (7 - index % 8)
    return bytes(result)


_LEGACY_MAPPING_KEYS = frozenset(
    {
        "id",
        "interior_side",
        "population",
        "multiplier",
        "offset",
        "inverse_multiplier",
    }
)
_HIERARCHICAL_MAPPING_KEYS = frozenset(
    {
        "id",
        "interior_side",
        "population",
        "unit_population",
        "unit_multiplier",
        "unit_inverse_multiplier",
        "cell_multiplier",
        "offset",
        "cell_inverse_multiplier",
    }
)


def _mapping_sha256(
    route_version: int,
    mapping: dict[str, int | str],
) -> str:
    """Hash the exact route-version/map-id selected mapping projection."""

    if type(route_version) is not int or type(mapping) is not dict:
        _fail("route-mapping")
    mapping_id = mapping.get("id")
    if route_version == 0 and mapping_id == "affine-interior-v1":
        keys = _LEGACY_MAPPING_KEYS
        multiplier_key = "multiplier"
        inverse_key = "inverse_multiplier"
    elif (
        route_version == 1
        and mapping_id == "affine-slot-then-interior-v1"
    ):
        keys = _HIERARCHICAL_MAPPING_KEYS
        multiplier_key = "cell_multiplier"
        inverse_key = "cell_inverse_multiplier"
    else:
        _fail("route-mapping")
    integer_keys = keys - {"id"}
    if (
        set(mapping) != keys
        or any(
            type(mapping.get(key)) is not int or int(mapping[key]) < 0
            for key in integer_keys
        )
    ):
        _fail("route-mapping")
    interior = int(mapping["interior_side"])
    population = int(mapping["population"])
    multiplier = int(mapping[multiplier_key])
    inverse = int(mapping[inverse_key])
    offset = int(mapping["offset"])
    if (
        interior <= 0
        or population != interior * interior
        or not 0 < multiplier < population
        or not 0 <= offset < population
        or multiplier * inverse % population != 1
    ):
        _fail("route-mapping")
    if route_version == 1:
        unit_population = int(mapping["unit_population"])
        unit_multiplier = int(mapping["unit_multiplier"])
        unit_inverse = int(mapping["unit_inverse_multiplier"])
        table = m2_recipe.r3_slot_multiplier_table()
        if (
            interior % 8 != 0
            or not 0 < interior // 8 < len(table)
            or unit_population != population // 1_728
            or unit_population <= 1
            or unit_multiplier != table[interior // 8]
            or unit_multiplier == 0
            or unit_multiplier * unit_inverse % unit_population != 1
        ):
            _fail("route-mapping")
    raw = canonical_manifest.serialize_manifest(mapping)
    if not raw.endswith(b"\n") or raw.endswith(b"\n\n"):
        _fail("route-mapping")
    return sha256(raw).hexdigest()


def _route_mapping_projection(
    route_version: int,
    profile: m2_codec.CandidateProfile,
    mapping: tuple[int, int, int],
) -> dict[str, int | str]:
    if (
        type(route_version) is not int
        or type(profile) is not m2_codec.CandidateProfile
        or type(mapping) is not tuple
        or len(mapping) != 3
        or any(type(value) is not int for value in mapping)
    ):
        _fail("route-mapping")
    interior, cell_multiplier, offset = mapping
    population = interior * interior
    try:
        cell_inverse = pow(cell_multiplier, -1, population)
    except ValueError:
        _fail("route-mapping")
    if route_version == 0 and profile.profile_version != 7:
        return {
            "id": "affine-interior-v1",
            "interior_side": interior,
            "population": population,
            "multiplier": cell_multiplier,
            "offset": offset,
            "inverse_multiplier": cell_inverse,
        }
    if (
        route_version == 1
        and profile.profile_version == 7
        and profile.transport_id == m2_codec.HIER_TRANSPORT
        and interior % 8 == 0
    ):
        unit_population = population // 1_728
        table = m2_recipe.r3_slot_multiplier_table()
        if not 0 < interior // 8 < len(table):
            _fail("route-mapping")
        unit_multiplier = table[interior // 8]
        try:
            unit_inverse = pow(unit_multiplier, -1, unit_population)
        except ValueError:
            _fail("route-mapping")
        if profile.protected_units != unit_population:
            _fail("route-mapping")
        return {
            "id": "affine-slot-then-interior-v1",
            "interior_side": interior,
            "population": population,
            "unit_population": unit_population,
            "unit_multiplier": unit_multiplier,
            "unit_inverse_multiplier": unit_inverse,
            "cell_multiplier": cell_multiplier,
            "offset": offset,
            "cell_inverse_multiplier": cell_inverse,
        }
    _fail("route-mapping")


def _unpack(raw: bytes, count: int) -> bytes:
    return bytes(
        (raw[index // 8] >> (7 - index % 8)) & 1 for index in range(count)
    )


_EH_PARITY_POSITIONS = frozenset((1, 2, 4, 8, 16, 32, 64))
_EH_DATA_INDICES = tuple(
    position - 1
    for position in range(1, 72)
    if position not in _EH_PARITY_POSITIONS
)


def _eh72_tables() -> tuple[
    tuple[tuple[tuple[int, int], ...], ...],
    tuple[tuple[int, ...], ...],
]:
    syndrome_rows: list[tuple[tuple[int, int], ...]] = []
    data_rows: list[tuple[int, ...]] = []
    data_ordinal = {index: ordinal for ordinal, index in enumerate(_EH_DATA_INDICES)}
    for byte_ordinal in range(9):
        syndrome_values: list[tuple[int, int]] = []
        data_values: list[int] = []
        for value in range(256):
            hamming = 0
            overall = 0
            data = 0
            for bit_ordinal in range(8):
                if not value & (1 << (7 - bit_ordinal)):
                    continue
                index = byte_ordinal * 8 + bit_ordinal
                overall ^= 1
                if index < 71:
                    hamming ^= index + 1
                ordinal = data_ordinal.get(index)
                if ordinal is not None:
                    data |= 1 << (63 - ordinal)
            syndrome_values.append((hamming, overall))
            data_values.append(data)
        syndrome_rows.append(tuple(syndrome_values))
        data_rows.append(tuple(data_values))
    return tuple(syndrome_rows), tuple(data_rows)


_EH_SYNDROME_TABLE, _EH_DATA_TABLE = _eh72_tables()


def _eh72_decode_syndrome(
    observed: bytes, erasures: Sequence[int] = ()
) -> m2_codec.Recovery:
    """Decode one EH72 word without the exhaustive clean-word search.

    The accepted error/erasure region and the reported construction charge are
    exactly those of :func:`m2_codec.eh72_decode`.  The syndrome only replaces
    enumeration as the implementation strategy; it does not enlarge the
    decoder's correction radius.
    """

    if type(observed) is not bytes or len(observed) != 9:
        raise m2_codec.CodecError("eh72-codeword-length")
    if isinstance(erasures, (bytes, bytearray, str)):
        raise m2_codec.CodecError("erasures-type")
    try:
        erased_one_based = tuple(erasures)
    except TypeError as error:
        raise m2_codec.CodecError("erasures-type") from error
    if (
        len(erased_one_based) > 3
        or any(
            type(value) is not int or not 1 <= value <= 72
            for value in erased_one_based
        )
        or len(set(erased_one_based)) != len(erased_one_based)
    ):
        raise m2_codec.CodecError("erasures-range")
    erased = tuple(sorted(value - 1 for value in erased_one_based))
    erased_set = frozenset(erased)
    source = int.from_bytes(observed, "big")
    for index in erased:
        source &= ~(1 << (71 - index))

    maximum_changes = (3 - len(erased)) // 2
    constructions = (1 << len(erased)) * (
        1 + (72 - len(erased) if maximum_changes else 0)
    )
    candidates: set[bytes] = set()
    for fill_mask in range(1 << len(erased)):
        candidate = source
        for ordinal, index in enumerate(erased):
            if fill_mask >> ordinal & 1:
                candidate |= 1 << (71 - index)
        hamming = 0
        overall = 0
        encoded = candidate.to_bytes(9, "big")
        for byte_ordinal, value in enumerate(encoded):
            contribution, parity = _EH_SYNDROME_TABLE[byte_ordinal][value]
            hamming ^= contribution
            overall ^= parity
        if not hamming and not overall:
            candidates.add(encoded)
            continue
        if maximum_changes and overall:
            changed = 71 if hamming == 0 else hamming - 1
            if changed not in erased_set:
                candidate ^= 1 << (71 - changed)
                candidates.add(candidate.to_bytes(9, "big"))
    if len(candidates) > 1:
        raise m2_codec.CodecError("eh72-distance-invariant")
    if not candidates:
        return m2_codec.Recovery("corrupt", None, constructions)
    encoded = next(iter(candidates))
    data = 0
    for byte_ordinal, value in enumerate(encoded):
        data |= _EH_DATA_TABLE[byte_ordinal][value]
    decoded = data.to_bytes(8, "big")
    state = "verified" if not erased and encoded == observed else "recovered"
    return m2_codec.Recovery(state, decoded, constructions)


class _Cells:
    __slots__ = ("raw", "side", "transform", "polarity")

    def __init__(
        self, raw: bytes, side: int, transform: int = 0, polarity: int = 0
    ) -> None:
        self.raw = raw
        self.side = side
        self.transform = transform
        self.polarity = polarity

    def at(self, row: int, column: int) -> int:
        last = self.side - 1
        source_row, source_column = (
            (row, column),
            (last - column, row),
            (last - row, last - column),
            (column, last - row),
            (row, last - column),
            (last - column, last - row),
            (last - row, column),
            (column, row),
        )[self.transform]
        value = self.raw[source_row * self.side + source_column]
        return value if value == 2 else value ^ self.polarity

    def interior(self, width: int) -> bytes:
        interior = self.side - 2 * width
        if self.transform == 0:
            value = b"".join(
                self.raw[
                    (row + width) * self.side + width :
                    (row + width) * self.side + width + interior
                ]
                for row in range(interior)
            )
            if self.polarity:
                value = value.translate(bytes((1, 0, 2)) + bytes(range(3, 256)))
            return value
        return bytes(
            self.at(row + width, column + width)
            for row in range(interior)
            for column in range(interior)
        )


def _parse_bits(raw: bytes) -> tuple[int, bytes]:
    if type(raw) is not bytes or not 5 <= len(raw) <= 4 + (_MAX_BITS + 7) // 8:
        _fail("length")
    count = int.from_bytes(raw[:4], "big")
    if not 1 <= count <= _MAX_BITS or len(raw) != 4 + (count + 7) // 8:
        _fail("length")
    unused = (-count) % 8
    if unused and raw[-1] & ((1 << unused) - 1):
        _fail("value")
    side = isqrt(count)
    if side * side != count or not 1 <= side <= _MAX_SIDE:
        _fail("geometry")
    return side, _unpack(raw[4:], count)


def _parse_matrix(raw: bytes) -> tuple[int, bytes]:
    if type(raw) is not bytes or not 3 <= len(raw) <= _MAX_OBSERVATION_BYTES:
        _fail("length")
    side = int.from_bytes(raw[:2], "big")
    if not 1 <= side <= _MAX_SIDE or len(raw) != 2 + side * side:
        _fail("length")
    values = raw[2:]
    if values.count(0) + values.count(1) + values.count(2) != len(values):
        _fail("value")
    return side, values


def _parse_units(raw: bytes, maximum: int) -> tuple[_ObservedUnit, ...]:
    if type(raw) is not bytes or not 4 <= len(raw) <= _MAX_OBSERVATION_BYTES:
        _fail("length")
    count = int.from_bytes(raw[:4], "big")
    if count > maximum:
        _fail("length")
    offset = 4
    seen: set[int] = set()
    values: list[_ObservedUnit] = []
    for _ in range(count):
        if offset + 6 > len(raw):
            _fail("length")
        unit_id = int.from_bytes(raw[offset : offset + 4], "big")
        length = int.from_bytes(raw[offset + 4 : offset + 6], "big")
        offset += 6
        if (
            unit_id == 0
            or unit_id in seen
            or not 1 <= length <= 255
            or offset + length > len(raw)
        ):
            _fail("duplicate" if unit_id in seen else "value")
        seen.add(unit_id)
        values.append(_ObservedUnit(unit_id, raw[offset : offset + length], ()))
        offset += length
    if offset != len(raw):
        _fail("length")
    return tuple(values)


def _sector_bytes(
    cells: _Cells, width: int, sector: int, byte_count: int
) -> bytes | None:
    if byte_count < 0 or byte_count * 8 > width * (cells.side - width):
        return None
    result = bytearray(byte_count)
    for bit_offset in range(byte_count * 8):
        row, column = bootstrap.sector_cell(
            cells.side, width, sector, bit_offset
        )
        value = cells.at(row, column)
        if value == 2:
            return None
        result[bit_offset // 8] |= value << (7 - bit_offset % 8)
    return bytes(result)


def _route_records(
    raw: bytes, record_count: int, recipe_bytes: int
) -> tuple[tuple[tuple[int, int, int, bytes], ...], tuple[bytes, ...]]:
    offset = 0
    packages: list[bytes] = []
    records: list[tuple[int, int, int, bytes]] = []
    previous_record_id = -1
    previous_stage = 0
    for _ in range(record_count):
        if offset + 8 > len(raw):
            _fail("route-record")
        stage, kind = raw[offset], raw[offset + 1]
        record_id = int.from_bytes(raw[offset + 2 : offset + 4], "big")
        length = int.from_bytes(raw[offset + 4 : offset + 8], "big")
        offset += 8
        if (
            stage > 5
            or not 1 <= kind <= 7
            or record_id <= previous_record_id
            or stage < previous_stage
            or offset + length > len(raw)
        ):
            _fail("route-record")
        previous_record_id = record_id
        previous_stage = stage
        payload = raw[offset : offset + length]
        records.append((stage, kind, record_id, payload))
        if kind == 5:
            packages.append(payload)
        offset += length
    if (
        offset != len(raw)
        or not packages
        or sum(map(len, packages)) != recipe_bytes
    ):
        _fail("route-record")
    return tuple(records), tuple(packages)


def _r3_route_package_resource_declaration(
    records: tuple[tuple[int, int, int, bytes], ...],
    packages: tuple[bytes, ...],
    sector: int,
) -> tuple[int, int] | None:
    """Recognize the exact v7 outer route before reading package ceilings."""

    if (
        type(sector) is not int
        or not 0 <= sector < 4
        or len(records) != 36 + len(_R3_TABLE_IDS) + 3
        or len(packages) != 1
    ):
        return None
    base = sector * 10_000
    for fact_index, (stage, name) in enumerate(
        zip(_R3_FACT_STAGES, _R3_FACT_NAMES, strict=True), 1
    ):
        start = (fact_index - 1) * 3
        for local, kind in enumerate((1, 2, 3)):
            actual_stage, actual_kind, record_id, payload = records[
                start + local
            ]
            if (
                actual_stage != stage
                or actual_kind != kind
                or record_id != base + fact_index * 100 + 1 + local
                or len(payload) < (14 if kind == 1 else 12)
                or int.from_bytes(payload[:2], "big") != fact_index
            ):
                return None
            if kind == 1:
                if (
                    int.from_bytes(payload[2:4], "big") != fact_index
                    or payload[4] != bootstrap.BYTES
                    or payload[5] != 0
                    or int.from_bytes(payload[6:10], "big") != len(name)
                    or int.from_bytes(payload[10:14], "big") != 1
                    or payload[14:] != name
                ):
                    return None
            else:
                input_bytes = int.from_bytes(payload[4:8], "big")
                output_bytes = int.from_bytes(payload[8:12], "big")
                if 12 + input_bytes + output_bytes != len(payload):
                    return None
    for index, table_id in enumerate(_R3_TABLE_IDS):
        stage, kind, record_id, payload = records[36 + index]
        if (
            stage != 5
            or kind != 4
            or record_id != base + 5_001 + index
            or len(payload) < 2
            or int.from_bytes(payload[:2], "big") != table_id
        ):
            return None
    stage, kind, record_id, package = records[36 + len(_R3_TABLE_IDS)]
    if (
        stage != 5
        or kind != 5
        or record_id != base + 6_001
        or package != packages[0]
        or len(package) < 64
        or package[:8] != b"GBRECP0\0"
    ):
        return None
    return (
        int.from_bytes(package[36:44], "big"),
        int.from_bytes(package[44:48], "big"),
    )


def _table_wire(table: bootstrap.RecipeTable) -> bytes:
    return b"".join(
        (
            table.table_id.to_bytes(2, "big"),
            bytes((table.element_type, 0)),
            table.element_width.to_bytes(4, "big"),
            table.element_count.to_bytes(4, "big"),
            len(table.payload).to_bytes(4, "big"),
            table.payload,
        )
    )


class ObservationDecoder:
    """Reusable bounded decoder; caches only results derived from observations."""

    def __init__(
        self,
        profile_policy_raw: bytes,
        profile_limits_raw: bytes,
        damage_policy_raw: bytes,
    ) -> None:
        try:
            owner_schema = tomllib.loads(
                profile_policy_raw.decode("utf-8")
            ).get("schema")
            if owner_schema == "golden-board.profile-policy/v1":
                decoder_policy = m2_policy.load_r3_decoder_policy(
                    profile_policy_raw,
                    profile_limits_raw,
                    damage_policy_raw,
                )
                active = m2_codec.r3_candidate_profile(
                    protected_units=decoder_policy.protected_units,
                    encoded_transport_bytes=(
                        decoder_policy.encoded_transport_bytes
                    ),
                )
                self.profiles = m2_codec.r3_registry_profiles(active)
                observed_shapes = tuple(
                    (
                        item.profile_id,
                        item.profile_version,
                        item.transport_id,
                        item.check_bytes,
                        item.required_copy_count,
                        item.protected_unit_bytes,
                        item.complexity_class,
                    )
                    for item in self.profiles
                )
                expected_shapes = tuple(
                    (
                        item.profile_id,
                        item.profile_version,
                        item.transport_id,
                        item.check_bytes,
                        item.required_copy_count,
                        item.protected_unit_bytes,
                        item.complexity_class,
                    )
                    for item in decoder_policy.registry_profiles
                )
                if observed_shapes != expected_shapes:
                    _fail("owner")
                resource_rows = decoder_policy.obs_units_resource_profiles
                self.repetition_resource = (
                    decoder_policy.repetition_primitive_steps,
                    decoder_policy.repetition_peak_scratch_bytes,
                )
                self.result_schema_version = 1
                self.establishing_profile_versions = frozenset((7,))
            elif owner_schema == "golden-board.profile-policy/v0":
                self.profiles = m2_codec.load_candidate_profiles(
                    profile_policy_raw, profile_limits_raw
                )
                damage = m2_policy.load_damage_policy(damage_policy_raw)
                limits = tomllib.loads(profile_limits_raw.decode("utf-8"))
                if limits.get("damage_policy_sha256") != damage.sha256:
                    _fail("owner")
                resource_rows = damage.obs_units_resource_profiles
                self.repetition_resource = (0, 0)
                self.result_schema_version = 0
                self.establishing_profile_versions = frozenset(
                    profile.profile_version for profile in self.profiles
                )
            else:
                _fail("owner")
        except (
            m2_codec.CodecError,
            m2_policy.PolicyError,
            UnicodeError,
            tomllib.TOMLDecodeError,
        ) as error:
            raise DecoderError("owner") from error
        self.transport_resources = {
            version: (steps, scratch)
            for version, profile_id, _package_sha, steps, scratch
            in resource_rows
            if any(
                profile.profile_version == version
                and profile.profile_id == profile_id
                for profile in self.profiles
            )
        }
        if len(self.transport_resources) != len(self.profiles):
            _fail("owner")
        self.profile_by_version = {
            profile.profile_version: profile for profile in self.profiles
        }
        self.profile_order = {
            profile.profile_id: ordinal
            for ordinal, profile in enumerate(self.profiles)
        }
        self.maximum_units = (
            self.profiles[0].protected_units
            if self.result_schema_version == 1
            else max(profile.protected_units for profile in self.profiles)
        )
        self._unit_cache: dict[
            tuple[int, bytes, tuple[int, ...]], m2_codec.Recovery
        ] = {}
        self._transport_cache: dict[
            tuple[str, bytes, tuple[int, ...]], m2_codec.Recovery
        ] = {}
        self._route_cache: dict[
            tuple[int, int, int, bytes], _Route | None
        ] = {}
        self._validated_route_cache: dict[
            tuple[
                int,
                int,
                int,
                tuple[tuple[int, int, int, bytes], ...],
                tuple[bytes, ...],
            ],
            tuple[
                tuple[bytes, ...],
                tuple[int, int, int],
                int,
                int,
                int,
                int,
                int,
                int,
                int,
            ],
        ] = {}
        self._route_package_cache: dict[
            tuple[int, bytes], bootstrap.RecipePackage
        ] = {}
        self._route_evaluation_cache: dict[
            tuple[bytes, int, tuple[bytes, ...]], bootstrap.RecipeResult
        ] = {}

    def _decode_route_package(
        self, raw: bytes, profile_version: int
    ) -> bootstrap.RecipePackage:
        key = (profile_version, raw)
        package = self._route_package_cache.get(key)
        if package is None:
            package = bootstrap.decode_recipe_package(raw, profile_version)
            if len(self._route_package_cache) >= 256:
                _fail("resource-limit")
            self._route_package_cache[key] = package
        return package

    def _evaluate_route_recipe(
        self,
        package: bootstrap.RecipePackage,
        recipe_id: int,
        values: tuple[bytes, ...],
    ) -> bootstrap.RecipeResult:
        key = (package.encoded, recipe_id, values)
        evaluated = self._route_evaluation_cache.get(key)
        if evaluated is None:
            evaluated = bootstrap.evaluate_recipe(package, recipe_id, values)
            if len(self._route_evaluation_cache) >= 4_096:
                _fail("resource-limit")
            self._route_evaluation_cache[key] = evaluated
        return evaluated

    def _validate_route_records(
        self,
        profile: m2_codec.CandidateProfile,
        sector: int,
        records: tuple[tuple[int, int, int, bytes], ...],
        package_bytes: tuple[bytes, ...],
        side: int,
        width: int,
    ) -> tuple[
        tuple[bytes, ...],
        tuple[int, int, int],
        int,
        int,
        int,
        int,
        int,
        int,
        int,
    ]:
        if profile.profile_version == 7:
            declaration = _r3_route_package_resource_declaration(
                records, package_bytes, sector
            )
            if declaration is not None and (
                declaration[0] > bootstrap.RECIPE_STEP_MAX
                or declaration[1] > bootstrap.RECIPE_SCRATCH_MAX
            ):
                _fail("resource-limit")
        packages: list[bootstrap.RecipePackage] = []
        recipe_ids: set[int] = set()
        table_ids: set[int] = set()
        for raw in package_bytes:
            package = self._decode_route_package(raw, profile.profile_version)
            if any(recipe.recipe_id in recipe_ids for recipe in package.recipes):
                _fail("route-recipe")
            if any(table.table_id in table_ids for table in package.tables):
                _fail("route-table")
            recipe_ids.update(recipe.recipe_id for recipe in package.recipes)
            table_ids.update(table.table_id for table in package.tables)
            packages.append(package)
        recipes = {
            recipe.recipe_id: (package, recipe)
            for package in packages
            for recipe in package.recipes
        }
        observed_fact_records = [record for record in records if record[1] <= 3]
        definitions: dict[int, tuple[int, int, int, bytes]] = {}
        examples: dict[int, dict[int, tuple[int, bytes, bytes]]] = {}
        route_primitive_steps = 0
        route_peak_scratch = 0
        base = sector * 10_000
        for stage, kind, record_id, payload in observed_fact_records:
            if kind == 1:
                if len(payload) < 14:
                    _fail("route-define")
                fact_id = int.from_bytes(payload[:2], "big")
                value_id = int.from_bytes(payload[2:4], "big")
                value_type = payload[4]
                reserved = payload[5]
                value_width = int.from_bytes(payload[6:10], "big")
                value_count = int.from_bytes(payload[10:14], "big")
                value_bytes = (
                    value_width
                    if value_type == bootstrap.BYTES
                    else (value_width + 7) // 8
                )
                if (
                    fact_id == 0
                    or fact_id in definitions
                    or value_id != fact_id
                    or value_type
                    not in (
                        bootstrap.UINT,
                        bootstrap.BOOL,
                        bootstrap.BITS,
                        bootstrap.BYTES,
                        bootstrap.STATUS,
                    )
                    or reserved != 0
                    or value_count != 1
                    or value_width == 0
                    or len(payload) != 14 + value_bytes
                    or record_id != base + 100 * fact_id + 1
                ):
                    _fail("route-define")
                definitions[fact_id] = (
                    stage,
                    value_type,
                    value_width,
                    payload[14:],
                )
                continue
            if len(payload) < 12:
                _fail("route-example")
            fact_id = int.from_bytes(payload[:2], "big")
            recipe_id = int.from_bytes(payload[2:4], "big")
            input_length = int.from_bytes(payload[4:8], "big")
            output_length = int.from_bytes(payload[8:12], "big")
            if (
                fact_id == 0
                or recipe_id not in recipes
                or kind in examples.setdefault(fact_id, {})
                or record_id != base + 100 * fact_id + kind
                or len(payload) != 12 + input_length + output_length
            ):
                _fail("route-example")
            recipe_input = payload[12 : 12 + input_length]
            observed_output = payload[12 + input_length :]
            package, recipe = recipes[recipe_id]
            input_widths = tuple(
                item.width
                if item.value_type == bootstrap.BYTES
                else (item.width + 7) // 8
                for item in recipe.inputs
            )
            if sum(input_widths) != input_length:
                _fail("route-example")
            values = []
            cursor = 0
            for width_bytes in input_widths:
                values.append(recipe_input[cursor : cursor + width_bytes])
                cursor += width_bytes
            evaluated = self._evaluate_route_recipe(
                package, recipe_id, tuple(values)
            )
            route_primitive_steps += recipe.primitive_steps
            route_peak_scratch = max(
                route_peak_scratch, recipe.peak_live_scratch_bytes
            )
            actual_output = evaluated.status.to_bytes(2, "big") + b"".join(
                evaluated.outputs
            )
            if evaluated.status != 0 or actual_output != observed_output:
                _fail("route-example")
            examples[fact_id][kind] = (
                recipe_id,
                recipe_input,
                observed_output,
            )
        if (
            not 1 <= len(definitions) <= 256
            or set(definitions) != set(examples)
            or any(set(values) != {2, 3} for values in examples.values())
            or any(
                examples[fact_id][2][0] != examples[fact_id][3][0]
                for fact_id in definitions
            )
            or any(
                examples[fact_id][2][1] == examples[fact_id][3][1]
                for fact_id in definitions
            )
        ):
            _fail("route-facts")
        observed_tables = [record for record in records if record[1] == 4]
        tables = sorted(
            (table for package in packages for table in package.tables),
            key=lambda item: item.table_id,
        )
        if len(observed_tables) != len(tables):
            _fail("route-table")
        for ordinal, (record, table) in enumerate(
            zip(observed_tables, tables, strict=True), 1
        ):
            if record != (5, 4, base + 5_000 + ordinal, _table_wire(table)):
                _fail("route-table")
        observed_packages = [record for record in records if record[1] == 5]
        if [record[3] for record in observed_packages] != list(package_bytes):
            _fail("route-recipe")
        for ordinal, record in enumerate(observed_packages, 1):
            if record[:3] != (5, 5, base + 6_000 + ordinal):
                _fail("route-recipe")
        if records[-2:] != (
            (5, 6, base + 7_001, (1).to_bytes(4, "big")),
            (5, 7, base + 7_002, b""),
        ):
            _fail("route-endpoint")
        expected_kind_order = (
            tuple(kind for _ in definitions for kind in (1, 2, 3))
            + (4,) * len(tables)
            + (5,) * len(packages)
            + (6, 7)
        )
        if tuple(record[1] for record in records) != expected_kind_order:
            _fail("route-order")
        mapping_recipes = []
        for fact_id in sorted(definitions):
            recipe_id = examples[fact_id][2][0]
            _, recipe = recipes[recipe_id]
            input_shape = tuple(
                (item.value_type, item.width) for item in recipe.inputs
            )
            output_shape = tuple(
                (item.value_type, item.width) for item in recipe.outputs[1:]
            )
            if input_shape == (
                (bootstrap.UINT, 32),
                (bootstrap.UINT, 16),
                (bootstrap.UINT, 16),
            ) and output_shape == ((bootstrap.UINT, 32),):
                mapping_recipes.append(recipe_id)
        if len(set(mapping_recipes)) != 1:
            _fail("route-mapping")
        mapping_recipe_id = mapping_recipes[0]
        mapping_package, _ = recipes[mapping_recipe_id]
        interior = side - 2 * width
        population = interior * interior
        outputs = []
        for logical in (0, 1, population - 1):
            evaluated = self._evaluate_route_recipe(
                mapping_package,
                mapping_recipe_id,
                (
                    logical.to_bytes(4, "big"),
                    side.to_bytes(2, "big"),
                    width.to_bytes(2, "big"),
                ),
            )
            if evaluated.status != 0 or len(evaluated.outputs) != 1:
                _fail("route-mapping")
            outputs.append(int.from_bytes(evaluated.outputs[0], "big"))
        offset = outputs[0]
        multiplier = (outputs[1] - offset) % population
        if (
            not 0 <= offset < population
            or not 0 < multiplier < population
            or gcd(multiplier, population) != 1
            or (multiplier * (population - 1) + offset) % population
            != outputs[2]
        ):
            _fail("route-mapping")
        transport = recipes.get(30)
        if transport is None:
            _fail("route-transport")
        _, transport_recipe = transport
        repetition_steps = 0
        repetition_scratch = 0
        if profile.profile_version == 7:
            repetition = recipes.get(113)
            if repetition is None:
                _fail("route-repetition")
            _, repetition_recipe = repetition
            repetition_steps = repetition_recipe.primitive_steps
            repetition_scratch = repetition_recipe.peak_live_scratch_bytes
        return (
            tuple(package.encoded for package in packages),
            (interior, multiplier, offset),
            int.from_bytes(records[-2][3], "big"),
            route_primitive_steps,
            route_peak_scratch,
            transport_recipe.primitive_steps,
            transport_recipe.peak_live_scratch_bytes,
            repetition_steps,
            repetition_scratch,
        )

    def _decode_unit(
        self,
        profile: m2_codec.CandidateProfile,
        encoded: bytes,
        erasures: tuple[int, ...],
    ) -> m2_codec.Recovery:
        key = (profile.profile_version, encoded, erasures)
        cached = self._unit_cache.get(key)
        if cached is not None:
            return cached
        transport_erasures = (
            erasures
            if profile.transport_id in (
                m2_codec.EH_TRANSPORT,
                m2_codec.HIER_TRANSPORT,
            )
            else tuple(sorted({bit // 8 for bit in erasures}))
        )
        transport_key = (
            profile.transport_id,
            encoded,
            transport_erasures,
        )
        value = self._transport_cache.get(transport_key)
        if value is None:
            try:
                if profile.transport_id in (
                    m2_codec.EH_TRANSPORT,
                    m2_codec.HIER_TRANSPORT,
                ):
                    by_codeword: list[list[int]] = [[] for _ in range(24)]
                    for bit in transport_erasures:
                        by_codeword[bit // 72].append(bit % 72 + 1)
                    if any(len(items) > 3 for items in by_codeword):
                        value = m2_codec.Recovery("corrupt", None, 0)
                    else:
                        recovered = bytearray()
                        state = "verified"
                        constructions = 0
                        for ordinal, word_erasures in enumerate(by_codeword):
                            word = _eh72_decode_syndrome(
                                encoded[ordinal * 9 : (ordinal + 1) * 9],
                                word_erasures,
                            )
                            constructions += word.constructions
                            if word.decoded is None:
                                value = m2_codec.Recovery(
                                    "corrupt", None, constructions
                                )
                                break
                            recovered.extend(word.decoded)
                            if word.state != "verified":
                                state = "recovered"
                        else:
                            value = (
                                m2_codec.Recovery(
                                    state, bytes(recovered[:-1]), constructions
                                )
                                if recovered[-1] == 0
                                else m2_codec.Recovery(
                                    "corrupt", None, constructions
                                )
                            )
                else:
                    result = m2_codec.rs255_191_decode(
                        encoded, transport_erasures, None
                    )
                    value = m2_codec.Recovery(
                        result.state,
                        result.decoded,
                        result.primitive_steps,
                    )
            except (m2_codec.CodecError, ValueError, IndexError):
                value = m2_codec.Recovery("corrupt", None, 0)
            if len(self._transport_cache) >= 1_000_000:
                _fail("resource-limit")
            self._transport_cache[transport_key] = value
        if value.decoded is not None:
            try:
                bootstrap.decode_common_block(
                    value.decoded, profile.profile_version
                )
            except bootstrap.BootstrapReject:
                value = m2_codec.Recovery("corrupt", None, value.constructions)
        if len(self._unit_cache) >= 1_000_000:
            _fail("resource-limit")
        self._unit_cache[key] = value
        return value

    def _aggregate_v7_group(
        self,
        profile: m2_codec.CandidateProfile,
        observations: Sequence[_ObservedUnit | None],
    ) -> m2_codec.ReplicaGroupResult:
        """Aggregate one checked v7 group using the fast lane decoder."""

        lanes = tuple(observations)
        factor = len(lanes)
        zero = bytes(m2_codec.COMMON_BYTES)
        if (
            profile.profile_version != 7
            or profile.transport_id != m2_codec.HIER_TRANSPORT
            or factor not in (1, 2, 5)
        ):
            _fail("physical-group")
        lane_states: list[int] = []
        lane_blocks: list[bytes] = []
        normalized: list[tuple[bytes, frozenset[int]] | None] = []
        candidates: list[tuple[bytes, bool]] = []
        constructions = 0
        present = False
        for observation in lanes:
            if observation is None:
                lane_states.append(0)
                lane_blocks.append(zero)
                normalized.append(None)
                continue
            present = True
            if len(observation.encoded) != m2_codec.EH_UNIT_BYTES:
                lane_states.append(1)
                lane_blocks.append(zero)
                normalized.append(None)
                continue
            erased = frozenset(observation.erasures)
            if (
                len(erased) != len(observation.erasures)
                or any(
                    type(value) is not int
                    or not 0 <= value < m2_codec.EH_UNIT_BYTES * 8
                    for value in erased
                )
            ):
                _fail("physical-group")
            bits = _unpack(observation.encoded, m2_codec.EH_UNIT_BYTES * 8)
            if any(bits[index] for index in erased):
                _fail("physical-group")
            normalized.append((bits, erased))
            recovery = self._decode_unit(
                profile, observation.encoded, observation.erasures
            )
            constructions += recovery.constructions
            if recovery.decoded is None:
                lane_states.append(1)
                lane_blocks.append(zero)
            else:
                lane_states.append(2 if recovery.state == "verified" else 3)
                lane_blocks.append(recovery.decoded)
                candidates.append(
                    (recovery.decoded, recovery.state == "verified")
                )

        repetition_state = 0
        repetition_block = zero
        if factor > 1 and present:
            value_bits = bytearray(m2_codec.EH_UNIT_BYTES)
            repetition_erasures: list[int] = []
            for bit_index in range(m2_codec.EH_UNIT_BYTES * 8):
                known_mask = [0] * 5
                one_mask = [0] * 5
                for replica_index, normalized_lane in enumerate(normalized):
                    known = (
                        normalized_lane is not None
                        and bit_index not in normalized_lane[1]
                    )
                    known_mask[replica_index] = int(known)
                    one_mask[replica_index] = int(
                        known and normalized_lane[0][bit_index] == 1
                    )
                known, bit = m2_codec.repetition_symbol(
                    factor, known_mask, one_mask
                )
                if known:
                    value_bits[bit_index // 8] |= bit << (7 - bit_index % 8)
                else:
                    repetition_erasures.append(bit_index)
            recovery = self._decode_unit(
                profile, bytes(value_bits), tuple(repetition_erasures)
            )
            constructions += recovery.constructions
            if recovery.decoded is None:
                repetition_state = 1
            else:
                repetition_state = 3
                repetition_block = recovery.decoded
                candidates.append((recovery.decoded, False))

        distinct = {common for common, _ in candidates}
        if len(distinct) > 1:
            group_state, chosen = 4, zero
        elif not distinct:
            group_state, chosen = ((1, zero) if present else (0, zero))
        else:
            chosen = next(iter(distinct))
            verified = any(
                common == chosen and is_verified
                for common, is_verified in candidates
            )
            group_state = 2 if verified else 3
        return m2_codec.ReplicaGroupResult(
            0,
            group_state,
            len(distinct),
            chosen,
            tuple(lane_states),
            tuple(lane_blocks),
            repetition_state,
            repetition_block,
            constructions,
        )

    def _parse_route(
        self, cells: _Cells, width: int, sector: int
    ) -> _Route | None:
        header = _sector_bytes(cells, width, sector, 64)
        if header is None:
            return None
        cache_key: tuple[int, int, int, bytes] | None = None
        result: _Route | None = None
        try:
            calibration = header[:32]
            if calibration != _CALIBRATIONS[sector]:
                raise DecoderError("route-calibration")
            envelope = header[32:64]
            if (
                envelope[:8] != b"GBROUTE\0"
                or int.from_bytes(envelope[8:10], "big") not in (0, 1)
                or envelope[10] != sector
                or envelope[11] != sector
                or envelope[28:30] != b"\x01\0"
                or envelope[30:] != b"\0\0"
            ):
                raise DecoderError("route-envelope")
            profile_version = int.from_bytes(envelope[12:14], "big")
            route_version = int.from_bytes(envelope[8:10], "big")
            record_count = int.from_bytes(envelope[14:16], "big")
            record_bytes = int.from_bytes(envelope[16:20], "big")
            recipe_bytes = int.from_bytes(envelope[20:24], "big")
            prefix_cells = int.from_bytes(envelope[24:28], "big")
            discriminator = int.from_bytes(envelope[28:30], "big")
            profile = self.profile_by_version.get(profile_version)
            if (
                profile is None
                or route_version != (1 if profile.profile_version == 7 else 0)
                or not 37 <= record_count <= 256
                or prefix_cells != (64 + record_bytes) * 8
                or discriminator > width * (cells.side - width)
                or prefix_cells > width * (cells.side - width)
            ):
                raise DecoderError("route-envelope")
            prefix = _sector_bytes(cells, width, sector, 64 + record_bytes)
            if prefix is None:
                raise DecoderError("route-erased")
            cache_key = (cells.side, width, sector, prefix)
            if cache_key in self._route_cache:
                return self._route_cache[cache_key]
            records, package_bytes = _route_records(
                prefix[64:], record_count, recipe_bytes
            )
            base = sector * 10_000
            validation_key = (
                profile.profile_version,
                cells.side,
                width,
                tuple(
                    (stage, kind, record_id - base, payload)
                    for stage, kind, record_id, payload in records
                ),
                package_bytes,
            )
            validated = self._validated_route_cache.get(validation_key)
            if validated is None:
                validated = self._validate_route_records(
                    profile,
                    sector,
                    records,
                    package_bytes,
                    cells.side,
                    width,
                )
                if len(self._validated_route_cache) >= 4_096:
                    _fail("resource-limit")
                self._validated_route_cache[validation_key] = validated
            (
                packages,
                mapping,
                inventory_section_id,
                route_primitive_steps,
                route_peak_scratch,
                transport_primitive_steps,
                transport_peak_scratch,
                repetition_primitive_steps,
                repetition_peak_scratch,
            ) = validated
            result = _Route(
                profile,
                width,
                packages,
                envelope[:8],
                route_version,
                mapping,
                inventory_section_id,
                sector,
                route_primitive_steps,
                route_peak_scratch,
                transport_primitive_steps,
                transport_peak_scratch,
                repetition_primitive_steps,
                repetition_peak_scratch,
            )
        except DecoderError as error:
            if error.reason == "resource-limit":
                raise
            result = None
        except bootstrap.BootstrapReject:
            result = None
        if cache_key is not None:
            if len(self._route_cache) >= 4_096:
                _fail("resource-limit")
            self._route_cache[cache_key] = result
        return result

    def _discover_routes(self, cells: _Cells) -> tuple[_Route, ...]:
        discovered: dict[
            tuple[
                str,
                int,
                tuple[bytes, ...],
                bytes,
                int,
                tuple[int, int, int],
                int,
                int,
            ],
            _Route,
        ] = {}
        for width in range(8, min(128, (cells.side - 8) // 2) + 1, 8):
            for sector in range(4):
                route = self._parse_route(cells, width, sector)
                if route is not None:
                    discovered[
                        (
                            route.profile.profile_id,
                            route.shell_width,
                            route.packages,
                            route.magic,
                            route.route_version,
                            route.mapping,
                            route.inventory_section_id,
                            route.sector_id,
                        )
                    ] = route
        return tuple(
            discovered[key]
            for key in sorted(
                discovered,
                key=lambda item: (
                    self.profiles.index(discovered[item].profile),
                    item[1],
                    item[-1],
                ),
            )
        )

    def _extract_units(
        self,
        cells: _Cells,
        profile: m2_codec.CandidateProfile,
        width: int,
        mapping: tuple[int, int, int],
    ) -> tuple[_ObservedUnit, ...]:
        interior, multiplier, offset = mapping
        population = interior * interior
        if interior != cells.side - 2 * width:
            _fail("route-mapping")
        interior_cells = cells.interior(width)
        unit_bits = profile.protected_unit_bytes * 8
        count = min(profile.protected_units, population // unit_bits)
        projection = _route_mapping_projection(
            1 if profile.profile_version == 7 else 0,
            profile,
            mapping,
        )
        unit_multiplier = (
            int(projection["unit_multiplier"])
            if profile.profile_version == 7
            else 1
        )
        values: list[_ObservedUnit] = []
        for unit_id in range(1, count + 1):
            encoded = bytearray(profile.protected_unit_bytes)
            erasures: list[int] = []
            logical_first = (
                (unit_multiplier * (unit_id - 1)) % count
                if profile.profile_version == 7
                else unit_id - 1
            ) * unit_bits
            for bit_offset in range(unit_bits):
                physical = (
                    multiplier * (logical_first + bit_offset) + offset
                ) % population
                value = interior_cells[physical]
                if value == 2:
                    erasures.append(bit_offset)
                else:
                    encoded[bit_offset // 8] |= value << (7 - bit_offset % 8)
            values.append(
                _ObservedUnit(unit_id, bytes(encoded), tuple(erasures))
            )
        return tuple(values)

    def _recover_inventory(
        self,
        profile: m2_codec.CandidateProfile,
        observations: Sequence[_ObservedUnit],
    ) -> tuple[bootstrap.Inventory, bytes] | None:
        if profile.transport_id == m2_codec.HIER_TRANSPORT:
            return self._recover_inventory_v7(profile, observations)
        groups: dict[int, list[bytes]] = {}
        qualities: dict[int, bool] = {}
        for observation in observations:
            if len(observation.encoded) != profile.protected_unit_bytes:
                continue
            recovery = self._decode_unit(
                profile, observation.encoded, observation.erasures
            )
            if recovery.decoded is None:
                continue
            try:
                block = bootstrap.decode_common_block(
                    recovery.decoded, profile.profile_version
                )
            except bootstrap.BootstrapReject:
                continue
            if block.section_id == 1 and block.section_type == 1:
                groups.setdefault(block.semantic_copy_id, []).append(
                    recovery.decoded
                )
                qualities[block.semantic_copy_id] = (
                    qualities.get(block.semantic_copy_id, True)
                    and recovery.state == "verified"
                )
        witnesses: list[bootstrap.SectionWitness] = []
        for copy_id in sorted(groups):
            try:
                observed_copy, envelope = bootstrap.assemble_semantic_copy(
                    groups[copy_id], profile.profile_version
                )
                section = bootstrap.decode_section_envelope(envelope)
            except bootstrap.BootstrapReject:
                continue
            if (
                observed_copy == copy_id
                and section.section_id == 1
                and section.section_type == 1
            ):
                witnesses.append(
                    bootstrap.SectionWitness(envelope, qualities[copy_id])
                )
        try:
            _, envelope = bootstrap.recover_logical_section(witnesses)
            section = bootstrap.decode_section_envelope(envelope)
            inventory = bootstrap.decode_inventory(section.payload)
        except bootstrap.BootstrapReject:
            return None
        if inventory.version != profile.inventory_version:
            return None
        return inventory, envelope

    def _recover_inventory_v7(
        self,
        profile: m2_codec.CandidateProfile,
        observations: Sequence[_ObservedUnit],
    ) -> tuple[bootstrap.Inventory, bytes] | None:
        observed_by_id = {item.unit_id: item for item in observations}
        first = self._aggregate_v7_group(
            profile, tuple(observed_by_id.get(unit_id) for unit_id in range(1, 6))
        )
        if first.group_state not in (2, 3):
            return None
        try:
            first_block = bootstrap.decode_common_block(
                first.chosen_block, profile.profile_version
            )
        except bootstrap.BootstrapReject:
            return None
        if (
            first_block.section_id != 1
            or first_block.semantic_copy_id != 0
            or first_block.section_type != 1
            or first_block.section_version != 1
            or first_block.fragment_index != 0
            or first_block.fragment_count == 0
            or 5 * first_block.fragment_count > profile.protected_units
        ):
            return None
        blocks: list[bytes] = []
        for fragment_index in range(first_block.fragment_count):
            group_first = 5 * fragment_index + 1
            group = (
                first
                if fragment_index == 0
                else self._aggregate_v7_group(
                    profile,
                    tuple(
                        observed_by_id.get(group_first + replica_index)
                        for replica_index in range(5)
                    ),
                )
            )
            if group.group_state not in (2, 3):
                return None
            try:
                block = bootstrap.decode_common_block(
                    group.chosen_block, profile.profile_version
                )
            except bootstrap.BootstrapReject:
                return None
            if (
                block.section_id != 1
                or block.semantic_copy_id != 0
                or block.section_type != 1
                or block.section_version != 1
                or block.fragment_index != fragment_index
                or block.fragment_count != first_block.fragment_count
                or block.section_envelope_length
                != first_block.section_envelope_length
            ):
                return None
            blocks.append(group.chosen_block)
        try:
            observed_copy, envelope = bootstrap.assemble_semantic_copy(
                blocks, profile.profile_version
            )
            section = bootstrap.decode_section_envelope(envelope)
            inventory = bootstrap.decode_inventory(section.payload)
        except bootstrap.BootstrapReject:
            return None
        if (
            observed_copy != 0
            or section.section_id != 1
            or section.section_type != 1
            or section.section_version != 1
            or section.closure_class != 128
            or section.check_id != 1
            or section.dependencies
            or inventory.version != 1
        ):
            return None
        return inventory, envelope

    def _without_inventory(
        self,
        profiles: Sequence[m2_codec.CandidateProfile],
        observations: Sequence[_ObservedUnit],
    ) -> DecodeResult:
        if any(
            profile.transport_id == m2_codec.HIER_TRANSPORT
            for profile in profiles
        ):
            return self._without_inventory_v7(profiles, observations)
        diagnostics: list[FragmentDiagnostic] = []
        valid_blocks: list[tuple[str, str, bytes, bootstrap.CommonBlock]] = []
        for observation in sorted(observations, key=lambda item: item.unit_id):
            candidates: dict[
                tuple[str, bytes], tuple[str, bytes, bootstrap.CommonBlock]
            ] = {}
            for profile in profiles:
                if len(observation.encoded) != profile.protected_unit_bytes:
                    continue
                recovery = self._decode_unit(
                    profile, observation.encoded, observation.erasures
                )
                if recovery.decoded is None:
                    continue
                try:
                    block = bootstrap.decode_common_block(
                        recovery.decoded, profile.profile_version
                    )
                except bootstrap.BootstrapReject:
                    continue
                candidates[(profile.profile_id, recovery.decoded)] = (
                    recovery.state,
                    recovery.decoded,
                    block,
                )
            if len(candidates) == 1:
                (profile_id, _), (state, common, block) = next(
                    iter(candidates.items())
                )
                diagnostics.append(
                    FragmentDiagnostic(
                        observation.unit_id,
                        profile_id,
                        block.section_id,
                        block.semantic_copy_id,
                        block.fragment_index,
                        state,
                        common,
                    )
                )
                valid_blocks.append((profile_id, state, common, block))
            else:
                diagnostics.append(
                    FragmentDiagnostic(
                        observation.unit_id,
                        "",
                        0,
                        0xFFFF,
                        0xFFFF,
                        "ambiguous" if candidates else "corrupt",
                        None,
                    )
                )
        section_results: list[SectionResult] = []
        by_profile_section_copy: dict[
            tuple[str, int, int], list[tuple[str, bytes]]
        ] = {}
        profile_version_by_id = {
            profile.profile_id: profile.profile_version for profile in profiles
        }
        for profile_id, state, common, block in valid_blocks:
            by_profile_section_copy.setdefault(
                (profile_id, block.section_id, block.semantic_copy_id), []
            ).append((state, common))
        by_section: dict[int, list[bootstrap.SectionWitness]] = {}
        for (profile_id, section_id, _copy), blocks in sorted(
            by_profile_section_copy.items()
        ):
            try:
                _, envelope = bootstrap.assemble_semantic_copy(
                    (common for _, common in blocks),
                    profile_version_by_id[profile_id],
                )
            except bootstrap.BootstrapReject:
                continue
            by_section.setdefault(section_id, []).append(
                bootstrap.SectionWitness(
                    envelope, all(state == "verified" for state, _ in blocks)
                )
            )
        for section_id in sorted(by_section):
            try:
                state, envelope = bootstrap.recover_logical_section(
                    by_section[section_id]
                )
            except bootstrap.BootstrapReject as error:
                state = (
                    "ambiguous"
                    if error.code == bootstrap.AMBIGUOUS
                    else "corrupt"
                )
                envelope = None
            section_results.append(SectionResult(section_id, state, envelope))
        return DecodeResult(
            (
                "ambiguous"
                if any(item.state == "ambiguous" for item in section_results)
                else "failure"
            ),
            None,
            tuple(section_results),
            (),
            False,
            tuple(diagnostics),
        )

    def _without_inventory_v7(
        self,
        profiles: Sequence[m2_codec.CandidateProfile],
        observations: Sequence[_ObservedUnit],
    ) -> DecodeResult:
        v7_profiles = tuple(
            profile
            for profile in profiles
            if profile.transport_id == m2_codec.HIER_TRANSPORT
        )
        if len(v7_profiles) != 1:
            _fail("profile-registry")
        v7 = v7_profiles[0]
        observed_by_id = {item.unit_id: item for item in observations}
        initial = self._aggregate_v7_group(
            v7, tuple(observed_by_id.get(unit_id) for unit_id in range(1, 6))
        )
        inventory_group_results: dict[int, m2_codec.ReplicaGroupResult] = {0: initial}
        inventory_group_identity: dict[int, bool] = {0: False}
        inventory_identity_valid = False
        inventory_fragment_count = 1
        if initial.group_state in (2, 3):
            try:
                first_block = bootstrap.decode_common_block(
                    initial.chosen_block, v7.profile_version
                )
            except bootstrap.BootstrapReject:
                first_block = None
            inventory_identity_valid = first_block is not None and (
                first_block.section_id == 1
                and first_block.semantic_copy_id == 0
                and first_block.section_type == 1
                and first_block.section_version == 1
                and first_block.fragment_index == 0
            )
            inventory_group_identity[0] = inventory_identity_valid
            if inventory_identity_valid:
                inventory_fragment_count = first_block.fragment_count
                if (
                    inventory_fragment_count == 0
                    or 5 * inventory_fragment_count > v7.protected_units
                ):
                    inventory_identity_valid = False
                    inventory_fragment_count = 1
                else:
                    for fragment_index in range(1, inventory_fragment_count):
                        group_first = 5 * fragment_index + 1
                        inventory_group_results[fragment_index] = (
                            self._aggregate_v7_group(
                                v7,
                                tuple(
                                    observed_by_id.get(
                                        group_first + replica_index
                                    )
                                    for replica_index in range(5)
                                ),
                            )
                        )

        valid_blocks: list[tuple[str, str, bytes, bootstrap.CommonBlock]] = []
        diagnostics: list[FragmentDiagnostic] = []
        initial_lane_by_id = {
            unit_id: (
                initial.lane_states[unit_id - 1],
                initial.lane_blocks[unit_id - 1],
            )
            for unit_id in range(1, 6)
        }
        for observation in sorted(observations, key=lambda item: item.unit_id):
            candidates: dict[
                tuple[str, bytes], tuple[str, bytes, bootstrap.CommonBlock]
            ] = {}
            for profile in profiles:
                if len(observation.encoded) != profile.protected_unit_bytes:
                    continue
                recovery = self._decode_unit(
                    profile, observation.encoded, observation.erasures
                )
                if recovery.decoded is None:
                    continue
                try:
                    block = bootstrap.decode_common_block(
                        recovery.decoded, profile.profile_version
                    )
                except bootstrap.BootstrapReject:
                    continue
                candidates[(profile.profile_id, recovery.decoded)] = (
                    recovery.state,
                    recovery.decoded,
                    block,
                )
            replica_index = (
                observation.unit_id - 1
                if 1 <= observation.unit_id <= 5
                else 0xFFFF
            )
            factor = 5 if 1 <= observation.unit_id <= 5 else 0xFFFF
            if len(candidates) == 1:
                (profile_id, _), (state, common, block) = next(
                    iter(candidates.items())
                )
                if profile_id == v7.profile_id and observation.unit_id <= 5:
                    lane_state, lane_block = initial_lane_by_id[observation.unit_id]
                    state = {
                        1: "corrupt",
                        2: "verified",
                        3: "recovered",
                    }.get(lane_state, "corrupt")
                    common = lane_block if lane_state in (2, 3) else None
                diagnostics.append(
                    FragmentDiagnostic(
                        observation.unit_id,
                        profile_id,
                        block.section_id,
                        block.semantic_copy_id,
                        block.fragment_index,
                        state,
                        common,
                        replica_index,
                        factor,
                    )
                )
                # Section 1 is route-fixed to the v7 REP5 group before any
                # inventory exists.  A locally valid legacy splice is still a
                # useful per-input diagnostic, but it must not replace that
                # corrupt route-fixed identity with a foreign checked section.
                if block.section_id != 1:
                    valid_blocks.append((profile_id, state, common, block))
            else:
                diagnostics.append(
                    FragmentDiagnostic(
                        observation.unit_id,
                        "",
                        0,
                        0xFFFF,
                        0xFFFF,
                        "ambiguous" if candidates else "corrupt",
                        None,
                        replica_index,
                        factor,
                    )
                )
        observed_ids = set(observed_by_id)
        for unit_id in range(1, 6):
            if unit_id not in observed_ids:
                diagnostics.append(
                    FragmentDiagnostic(
                        unit_id,
                        v7.profile_id,
                        1,
                        0,
                        0,
                        "missing",
                        None,
                        unit_id - 1,
                        5,
                    )
                )
        diagnostics.sort(key=lambda item: item.input_id)

        if inventory_identity_valid:
            for fragment_index in range(inventory_fragment_count):
                group = inventory_group_results[fragment_index]
                if group.group_state not in (2, 3):
                    continue
                try:
                    block = bootstrap.decode_common_block(
                        group.chosen_block, v7.profile_version
                    )
                except bootstrap.BootstrapReject:
                    continue
                if (
                    block.section_id == 1
                    and block.semantic_copy_id == 0
                    and block.section_type == 1
                    and block.section_version == 1
                    and block.fragment_index == fragment_index
                    and block.fragment_count == inventory_fragment_count
                ):
                    inventory_group_identity[fragment_index] = True
                    valid_blocks.append(
                        (
                            v7.profile_id,
                            "verified" if group.group_state == 2 else "recovered",
                            group.chosen_block,
                            block,
                        )
                    )
                else:
                    inventory_group_identity[fragment_index] = False

        grouped: dict[
            tuple[str, int, int], list[tuple[str, bytes]]
        ] = {}
        profile_version_by_id = {
            profile.profile_id: profile.profile_version for profile in profiles
        }
        for profile_id, state, common, block in valid_blocks:
            grouped.setdefault(
                (profile_id, block.section_id, block.semantic_copy_id), []
            ).append((state, common))
        by_section: dict[int, list[bootstrap.SectionWitness]] = {}
        attempted_envelopes: set[bytes] = set()
        for (profile_id, section_id, _copy), blocks in sorted(grouped.items()):
            decoded_by_index: dict[int, bootstrap.CommonBlock] = {}
            identity: tuple[int, ...] | None = None
            conflict = False
            for _, common in blocks:
                try:
                    block = bootstrap.decode_common_block(
                        common, profile_version_by_id[profile_id]
                    )
                except bootstrap.BootstrapReject:
                    conflict = True
                    break
                current_identity = (
                    block.section_id,
                    block.semantic_copy_id,
                    block.section_type,
                    block.section_version,
                    block.fragment_count,
                    block.section_envelope_length,
                )
                if identity is None:
                    identity = current_identity
                elif identity != current_identity:
                    conflict = True
                    break
                previous = decoded_by_index.get(block.fragment_index)
                if previous is not None and previous != block:
                    conflict = True
                    break
                decoded_by_index[block.fragment_index] = block
            candidate_envelope = b""
            if (
                not conflict
                and identity is not None
                and set(decoded_by_index) == set(range(identity[4]))
            ):
                candidate_envelope = b"".join(
                    decoded_by_index[index].payload
                    for index in range(identity[4])
                )
                if len(candidate_envelope) != identity[5]:
                    candidate_envelope = b""
            if bootstrap.section_envelope_attempt_eligible(candidate_envelope):
                attempted_envelopes.add(candidate_envelope)
                if len(attempted_envelopes) > 4_096:
                    return DecodeResult(
                        "resource-limit",
                        None,
                        (),
                        (),
                        False,
                        resource=ResourceUsage(4_096),
                    )
            try:
                _, envelope = bootstrap.assemble_semantic_copy(
                    (common for _, common in blocks),
                    profile_version_by_id[profile_id],
                )
            except bootstrap.BootstrapReject:
                continue
            by_section.setdefault(section_id, []).append(
                bootstrap.SectionWitness(
                    envelope, all(state == "verified" for state, _ in blocks)
                )
            )

        section_results: list[SectionResult] = []
        section_ids = set(by_section)
        section_ids.add(1)
        for section_id in sorted(section_ids):
            witnesses = by_section.get(section_id, [])
            if witnesses:
                try:
                    state, envelope = bootstrap.recover_logical_section(witnesses)
                except bootstrap.BootstrapReject as error:
                    state = (
                        "ambiguous"
                        if error.code == bootstrap.AMBIGUOUS
                        else "corrupt"
                    )
                    envelope = None
            elif section_id == 1:
                states = tuple(
                    (
                        result.group_state
                        if result.group_state not in (2, 3)
                        or inventory_group_identity.get(fragment_index, False)
                        else 1
                    )
                    for fragment_index, result in sorted(
                        inventory_group_results.items()
                    )
                )
                state = (
                    "corrupt"
                    if not inventory_identity_valid
                    and initial.group_state != 0
                    or any(value in (1, 4) for value in states)
                    else "incomplete"
                )
                envelope = None
            else:
                continue
            section_results.append(SectionResult(section_id, state, envelope))
        return DecodeResult(
            (
                "ambiguous"
                if any(item.state == "ambiguous" for item in section_results)
                else "failure"
            ),
            None,
            tuple(section_results),
            (),
            False,
            tuple(diagnostics),
            resource=ResourceUsage(len(attempted_envelopes)),
        )

    @staticmethod
    def _expected_units(
        profile: m2_codec.CandidateProfile,
        inventory: bootstrap.Inventory,
    ) -> tuple[_ExpectedUnit, ...]:
        result: list[_ExpectedUnit] = []
        if inventory.version == 1:
            if (
                profile.profile_version != 7
                or profile.transport_id != m2_codec.HIER_TRANSPORT
            ):
                _fail("inventory-profile")
            for entry in inventory.entries:
                check_bytes = 4 if entry.check_id == 1 else 8
                envelope_length = (
                    18
                    + 4 * len(entry.dependencies)
                    + entry.logical_payload_length
                    + check_bytes
                )
                fragments = (envelope_length + 156) // 157
                for fragment_index in range(fragments):
                    group_first = len(result) + 1
                    for replica_index in range(entry.physical_replica_count):
                        result.append(
                            _ExpectedUnit(
                                len(result) + 1,
                                entry.section_id,
                                0,
                                fragment_index,
                                fragments,
                                entry.section_type,
                                entry.section_version,
                                envelope_length,
                                replica_index,
                                entry.physical_replica_count,
                                group_first,
                            )
                        )
            if len(result) > profile.protected_units:
                _fail("resource-limit")
            return tuple(result)
        for copy_id in range(max(entry.copy_count for entry in inventory.entries)):
            for entry in inventory.entries:
                if copy_id >= entry.copy_count:
                    continue
                check_bytes = 4 if entry.check_id == 1 else 8
                envelope_length = (
                    18
                    + 4 * len(entry.dependencies)
                    + entry.logical_payload_length
                    + check_bytes
                )
                fragments = (envelope_length + 156) // 157
                for fragment_index in range(fragments):
                    result.append(
                        _ExpectedUnit(
                            len(result) + 1,
                            entry.section_id,
                            copy_id,
                            fragment_index,
                            fragments,
                            entry.section_type,
                            entry.section_version,
                            envelope_length,
                        )
                    )
        if len(result) > profile.protected_units:
            _fail("resource-limit")
        return tuple(result)

    def _recover_sections_v7(
        self,
        profile: m2_codec.CandidateProfile,
        observations: Sequence[_ObservedUnit],
        inventory: bootstrap.Inventory,
        *,
        retain_extra_inputs: bool,
        transport_primitive_steps: int,
        transport_peak_scratch: int,
        repetition_primitive_steps: int,
        repetition_peak_scratch: int,
    ) -> DecodeResult:
        expected = self._expected_units(profile, inventory)
        expected_by_id = {item.unit_id: item for item in expected}
        observed_by_id = {
            item.unit_id: item
            for item in observations
            if retain_extra_inputs or item.unit_id in expected_by_id
        }
        by_group: dict[int, list[_ExpectedUnit]] = {}
        for item in expected:
            by_group.setdefault(item.group_first_physical_unit_id, []).append(item)

        diagnostics: list[FragmentDiagnostic] = []
        accepted_groups: dict[
            tuple[int, int], tuple[int, bytes]
        ] = {}
        group_states: dict[tuple[int, int], int] = {}
        repetition_group_count = 0
        for group_first in sorted(by_group):
            wanted_lanes = sorted(
                by_group[group_first], key=lambda item: item.replica_index
            )
            factor = wanted_lanes[0].physical_replica_count
            if (
                len(wanted_lanes) != factor
                or [item.replica_index for item in wanted_lanes]
                != list(range(factor))
                or [item.unit_id for item in wanted_lanes]
                != list(range(group_first, group_first + factor))
            ):
                _fail("physical-group")
            observed_lanes = tuple(
                observed_by_id.get(item.unit_id) for item in wanted_lanes
            )
            if factor > 1 and any(item is not None for item in observed_lanes):
                repetition_group_count += 1
            group = self._aggregate_v7_group(profile, observed_lanes)
            first = wanted_lanes[0]
            identity_valid = False
            if group.group_state in (2, 3):
                try:
                    block = bootstrap.decode_common_block(
                        group.chosen_block, profile.profile_version
                    )
                except bootstrap.BootstrapReject:
                    block = None
                identity_valid = block is not None and (
                    block.section_id,
                    block.semantic_copy_id,
                    block.fragment_index,
                    block.fragment_count,
                    block.section_type,
                    block.section_version,
                    block.section_envelope_length,
                ) == (
                    first.section_id,
                    first.semantic_copy_id,
                    first.fragment_index,
                    first.fragment_count,
                    first.section_type,
                    first.section_version,
                    first.envelope_length,
                )
                if identity_valid:
                    accepted_groups[(first.section_id, first.fragment_index)] = (
                        group.group_state,
                        group.chosen_block,
                    )
            group_states[(first.section_id, first.fragment_index)] = (
                group.group_state
                if group.group_state not in (2, 3) or identity_valid
                else 1
            )
            for wanted, observation, lane_state, lane_block in zip(
                wanted_lanes,
                observed_lanes,
                group.lane_states,
                group.lane_blocks,
                strict=True,
            ):
                state = {
                    0: "missing",
                    1: "corrupt",
                    2: "verified",
                    3: "recovered",
                }[lane_state]
                common = lane_block if lane_state in (2, 3) else None
                diagnostics.append(
                    FragmentDiagnostic(
                        wanted.unit_id,
                        profile.profile_id,
                        wanted.section_id,
                        wanted.semantic_copy_id,
                        wanted.fragment_index,
                        state,
                        common,
                        wanted.replica_index,
                        wanted.physical_replica_count,
                    )
                )

        for unit_id in sorted(set(observed_by_id) - set(expected_by_id)):
            observation = observed_by_id[unit_id]
            if len(observation.encoded) != profile.protected_unit_bytes:
                recovery = m2_codec.Recovery("corrupt", None, 0)
                block = None
            else:
                recovery = self._decode_unit(
                    profile, observation.encoded, observation.erasures
                )
                try:
                    block = (
                        bootstrap.decode_common_block(
                            recovery.decoded, profile.profile_version
                        )
                        if recovery.decoded is not None
                        else None
                    )
                except bootstrap.BootstrapReject:
                    block = None
            diagnostics.append(
                FragmentDiagnostic(
                    unit_id,
                    profile.profile_id,
                    block.section_id if block is not None else 0,
                    block.semantic_copy_id if block is not None else 0xFFFF,
                    block.fragment_index if block is not None else 0xFFFF,
                    recovery.state if block is not None else "corrupt",
                    recovery.decoded if block is not None else None,
                )
            )
        diagnostics.sort(key=lambda item: item.input_id)

        section_results: list[SectionResult] = []
        attempted_envelopes: set[bytes] = set()
        for entry in inventory.entries:
            check_bytes = 4 if entry.check_id == 1 else 8
            envelope_length = (
                18
                + 4 * len(entry.dependencies)
                + entry.logical_payload_length
                + check_bytes
            )
            fragment_count = (envelope_length + 156) // 157
            groups = [
                accepted_groups.get((entry.section_id, fragment_index))
                for fragment_index in range(fragment_count)
            ]
            envelope_value: bytes | None = None
            if all(group is not None for group in groups):
                concrete = [group for group in groups if group is not None]
                blocks = [group[1] for group in concrete]
                try:
                    candidate_envelope = b"".join(
                        bootstrap.decode_common_block(
                            block, profile.profile_version
                        ).payload
                        for block in blocks
                    )
                except bootstrap.BootstrapReject:
                    candidate_envelope = b""
                if bootstrap.section_envelope_attempt_eligible(candidate_envelope):
                    attempted_envelopes.add(candidate_envelope)
                    if len(attempted_envelopes) > 4_096:
                        return DecodeResult(
                            "resource-limit",
                            None,
                            (),
                            (),
                            False,
                            resource=ResourceUsage(
                                4_096,
                                0,
                                max(
                                    transport_peak_scratch,
                                    repetition_peak_scratch,
                                ),
                            ),
                        )
                try:
                    observed_copy, envelope = bootstrap.assemble_semantic_copy(
                        blocks, profile.profile_version
                    )
                    section = bootstrap.decode_section_envelope(envelope)
                    bootstrap.validate_envelope_against_inventory(
                        section, inventory
                    )
                except bootstrap.BootstrapReject:
                    state = "corrupt"
                else:
                    if observed_copy != 0:
                        state = "corrupt"
                    else:
                        envelope_value = envelope
                        state = (
                            "verified"
                            if all(group[0] == 2 for group in concrete)
                            else "recovered"
                        )
            else:
                states = [
                    group_states[(entry.section_id, fragment_index)]
                    for fragment_index in range(fragment_count)
                ]
                state = (
                    "corrupt"
                    if any(group_state in (1, 4) for group_state in states)
                    else "incomplete"
                )
            section_results.append(
                SectionResult(entry.section_id, state, envelope_value)
            )

        unique_envelopes = {
            item.section_id: item.envelope
            for item in section_results
            if item.envelope is not None
        }
        streams: list[bytes | None] = []
        for frame_section_id in (2, 3):
            try:
                frame_envelope = bootstrap.decode_section_envelope(
                    unique_envelopes[frame_section_id]
                )
                frame = bootstrap.decode_tier_frame(
                    frame_envelope.payload, frame_section_id
                )
                bootstrap.validate_tier_against_inventory(
                    frame, frame_envelope, inventory
                )
                body_payloads = {
                    section_id: bootstrap.decode_section_envelope(
                        unique_envelopes[section_id]
                    ).payload
                    for section_id in frame.body_section_ids
                }
                stream = bootstrap.assemble_content_stream(frame, body_payloads)
            except (KeyError, bootstrap.BootstrapReject):
                stream = None
            streams.append(stream)
        required_stream, all_stream = streams
        if required_stream is None:
            all_stream = None
        artifact = (
            "ambiguous"
            if any(item.state == "ambiguous" for item in section_results)
            else "exact"
            if all(
                item.state in ("verified", "recovered")
                for item in section_results
            )
            and required_stream is not None
            and all_stream is not None
            else "degraded"
            if required_stream is not None
            else "failure"
        )
        present_lanes = sum(
            1 for item in observations
        )
        primitive_steps = (
            present_lanes * 24 * transport_primitive_steps
            + repetition_group_count
            * (
                1_728 * repetition_primitive_steps
                + 24 * transport_primitive_steps
            )
        )
        return DecodeResult(
            artifact,
            profile.profile_id,
            tuple(section_results),
            (),
            True,
            tuple(diagnostics),
            required_stream,
            all_stream,
            ResourceUsage(
                len(attempted_envelopes),
                primitive_steps,
                max(transport_peak_scratch, repetition_peak_scratch),
            ),
        )

    def _recover_sections(
        self,
        profile: m2_codec.CandidateProfile,
        observations: Sequence[_ObservedUnit],
        *,
        retain_extra_inputs: bool,
        transport_primitive_steps: int,
        transport_peak_scratch: int,
        repetition_primitive_steps: int = 0,
        repetition_peak_scratch: int = 0,
    ) -> DecodeResult:
        inventory_result = self._recover_inventory(profile, observations)
        if inventory_result is None:
            value = self._without_inventory((profile,), observations)
            repetition_groups = (
                1
                if profile.transport_id == m2_codec.HIER_TRANSPORT
                and any(1 <= item.unit_id <= 5 for item in observations)
                else 0
            )
            return DecodeResult(
                value.artifact_state,
                value.profile_id,
                value.section_results,
                value.route_profile_ids,
                value.inventory_available,
                value.fragment_diagnostics,
                resource=ResourceUsage(
                    value.resource.section_attempts,
                    len(observations)
                    * (
                        24
                        if profile.transport_id
                        in (
                            m2_codec.EH_TRANSPORT,
                            m2_codec.HIER_TRANSPORT,
                        )
                        else 1
                    )
                    * transport_primitive_steps
                    + repetition_groups
                    * (
                        1_728 * repetition_primitive_steps
                        + 24 * transport_primitive_steps
                    ),
                    max(
                        transport_peak_scratch,
                        repetition_peak_scratch
                        if repetition_groups
                        else 0,
                    ),
                ),
            )
        inventory, _ = inventory_result
        if profile.transport_id == m2_codec.HIER_TRANSPORT:
            return self._recover_sections_v7(
                profile,
                observations,
                inventory,
                retain_extra_inputs=retain_extra_inputs,
                transport_primitive_steps=transport_primitive_steps,
                transport_peak_scratch=transport_peak_scratch,
                repetition_primitive_steps=repetition_primitive_steps,
                repetition_peak_scratch=repetition_peak_scratch,
            )
        expected = self._expected_units(profile, inventory)
        expected_by_id = {item.unit_id: item for item in expected}
        observed_by_id = {
            item.unit_id: item
            for item in observations
            if retain_extra_inputs or item.unit_id in expected_by_id
        }
        decoded: dict[int, m2_codec.Recovery] = {}
        decoded_blocks: dict[int, bootstrap.CommonBlock] = {}
        identity_matches: set[int] = set()
        for unit_id, item in observed_by_id.items():
            if len(item.encoded) != profile.protected_unit_bytes:
                decoded[unit_id] = m2_codec.Recovery("corrupt", None, 0)
                continue
            recovery = self._decode_unit(profile, item.encoded, item.erasures)
            if recovery.decoded is not None:
                try:
                    block = bootstrap.decode_common_block(
                        recovery.decoded, profile.profile_version
                    )
                except bootstrap.BootstrapReject:
                    recovery = m2_codec.Recovery("corrupt", None, 0)
                else:
                    decoded_blocks[unit_id] = block
                    wanted = expected_by_id.get(unit_id)
                    if wanted is not None and (
                        block.section_id,
                        block.semantic_copy_id,
                        block.fragment_index,
                        block.fragment_count,
                        block.section_type,
                        block.section_version,
                        block.section_envelope_length,
                    ) != (
                        wanted.section_id,
                        wanted.semantic_copy_id,
                        wanted.fragment_index,
                        wanted.fragment_count,
                        wanted.section_type,
                        wanted.section_version,
                        wanted.envelope_length,
                    ):
                        recovery = m2_codec.Recovery("corrupt", None, 0)
                    elif wanted is not None:
                        identity_matches.add(unit_id)
            decoded[unit_id] = recovery
        diagnostics: list[FragmentDiagnostic] = []
        for unit_id in sorted(set(expected_by_id) | set(observed_by_id)):
            wanted = expected_by_id.get(unit_id)
            observed = observed_by_id.get(unit_id)
            recovery = decoded.get(unit_id)
            if wanted is not None:
                if observed is None:
                    state, common = "missing", None
                elif unit_id not in identity_matches or recovery is None:
                    state, common = "corrupt", None
                else:
                    state, common = recovery.state, recovery.decoded
                diagnostics.append(
                    FragmentDiagnostic(
                        unit_id,
                        profile.profile_id,
                        wanted.section_id,
                        wanted.semantic_copy_id,
                        wanted.fragment_index,
                        state,
                        common,
                    )
                )
                continue
            block = decoded_blocks.get(unit_id)
            if block is None or recovery is None or recovery.decoded is None:
                diagnostics.append(
                    FragmentDiagnostic(
                        unit_id,
                        profile.profile_id,
                        0,
                        0xFFFF,
                        0xFFFF,
                        "corrupt",
                        None,
                    )
                )
            else:
                diagnostics.append(
                    FragmentDiagnostic(
                        unit_id,
                        profile.profile_id,
                        block.section_id,
                        block.semantic_copy_id,
                        block.fragment_index,
                        recovery.state,
                        recovery.decoded,
                    )
                )
        by_section: dict[int, list[_ExpectedUnit]] = {}
        for item in expected:
            by_section.setdefault(item.section_id, []).append(item)
        section_results: list[SectionResult] = []
        section_attempts = 0
        entry_by_id = {entry.section_id: entry for entry in inventory.entries}
        for section_id in sorted(by_section):
            by_copy: dict[int, list[_ExpectedUnit]] = {}
            for item in by_section[section_id]:
                by_copy.setdefault(item.semantic_copy_id, []).append(item)
            witnesses: list[bootstrap.SectionWitness] = []
            attempted_envelopes: set[bytes] = set()
            corrupt_seen = False
            missing_seen = False
            for copy_id in sorted(by_copy):
                blocks: list[bytes] = []
                all_verified = True
                complete = True
                for item in sorted(
                    by_copy[copy_id], key=lambda value: value.fragment_index
                ):
                    if item.unit_id not in observed_by_id:
                        missing_seen = True
                        complete = False
                        break
                    recovery = decoded[item.unit_id]
                    if item.unit_id not in identity_matches:
                        corrupt_seen = True
                        complete = False
                        break
                    if recovery.decoded is None:
                        corrupt_seen = True
                        complete = False
                        break
                    blocks.append(recovery.decoded)
                    all_verified = all_verified and recovery.state == "verified"
                if complete:
                    try:
                        candidate_envelope = b"".join(
                            bootstrap.decode_common_block(
                                block, profile.profile_version
                            ).payload
                            for block in blocks
                        )
                    except bootstrap.BootstrapReject:
                        candidate_envelope = b""
                    if len(candidate_envelope) == by_copy[copy_id][0].envelope_length:
                        attempted_envelopes.add(candidate_envelope)
                    try:
                        observed_copy, envelope = bootstrap.assemble_semantic_copy(
                            blocks, profile.profile_version
                        )
                        section = bootstrap.decode_section_envelope(envelope)
                    except bootstrap.BootstrapReject:
                        corrupt_seen = True
                        continue
                    entry = entry_by_id[section_id]
                    if (
                        observed_copy != copy_id
                        or section.section_id != entry.section_id
                        or section.section_type != entry.section_type
                        or section.section_version != entry.section_version
                        or section.closure_class != entry.closure_class
                        or section.check_id != entry.check_id
                        or section.dependencies != entry.dependencies
                        or len(section.payload) != entry.logical_payload_length
                    ):
                        corrupt_seen = True
                        continue
                    witnesses.append(
                        bootstrap.SectionWitness(envelope, all_verified)
                    )
            section_attempts += len(attempted_envelopes)
            envelope_value: bytes | None = None
            if witnesses:
                try:
                    state, envelope_value = bootstrap.recover_logical_section(
                        witnesses
                    )
                except bootstrap.BootstrapReject as error:
                    state = (
                        "ambiguous"
                        if error.code == bootstrap.AMBIGUOUS
                        else "corrupt"
                    )
            else:
                state = (
                    "corrupt"
                    if corrupt_seen
                    else "incomplete"
                    if missing_seen
                    else "unknown"
                )
            section_results.append(
                SectionResult(section_id, state, envelope_value)
            )
        unique_envelopes = {
            item.section_id: item.envelope
            for item in section_results
            if item.envelope is not None
        }
        streams: list[bytes | None] = []
        for frame_section_id in (2, 3):
            try:
                frame_envelope = bootstrap.decode_section_envelope(
                    unique_envelopes[frame_section_id]
                )
                frame = bootstrap.decode_tier_frame(
                    frame_envelope.payload, frame_section_id
                )
                bootstrap.validate_tier_against_inventory(
                    frame, frame_envelope, inventory
                )
                body_payloads = {
                    section_id: bootstrap.decode_section_envelope(
                        unique_envelopes[section_id]
                    ).payload
                    for section_id in frame.body_section_ids
                }
                stream = bootstrap.assemble_content_stream(frame, body_payloads)
            except (KeyError, bootstrap.BootstrapReject):
                stream = None
            streams.append(stream)
        required_stream, all_stream = streams
        artifact = (
            "ambiguous"
            if any(item.state == "ambiguous" for item in section_results)
            else "exact"
            if all(
                item.state in ("verified", "recovered")
                for item in section_results
            )
            and required_stream is not None
            and all_stream is not None
            else "degraded"
            if required_stream is not None
            else "failure"
        )
        return DecodeResult(
            artifact,
            profile.profile_id,
            tuple(section_results),
            (),
            True,
            tuple(diagnostics),
            required_stream,
            all_stream,
            ResourceUsage(
                section_attempts,
                len(observations)
                * (24 if profile.transport_id == m2_codec.EH_TRANSPORT else 1)
                * transport_primitive_steps,
                transport_peak_scratch,
            ),
        )

    @staticmethod
    def _semantic_key(result: DecodeResult) -> tuple[tuple[int, bytes], ...]:
        return tuple(
            (item.section_id, item.envelope)
            for item in result.section_results
            if item.envelope is not None
        )

    def _decode_square(self, side: int, raw_cells: bytes) -> DecodeResult:
        results: list[DecodeResult] = []
        eligible_results: list[DecodeResult] = []
        route_profiles: set[str] = set()
        accepted: dict[
            tuple[int, int, int, str, str], AcceptedHypothesis
        ] = {}
        route_primitive_steps = 0
        peak_scratch = 0
        transport_primitive_steps = 0
        for transform in range(8):
            for polarity in range(2):
                cells = _Cells(raw_cells, side, transform, polarity)
                routes = self._discover_routes(cells)
                if not routes:
                    continue
                route_profiles.update(route.profile.profile_id for route in routes)
                route_groups: dict[
                    tuple[str, int, tuple[int, int, int], int], _Route
                ] = {}
                route_group_counts: dict[
                    tuple[str, int, tuple[int, int, int], int], int
                ] = {}
                for route in routes:
                    route_primitive_steps += route.route_primitive_steps
                    peak_scratch = max(
                        peak_scratch, route.route_peak_scratch
                    )
                    hypothesis = AcceptedHypothesis(
                        transform,
                        polarity,
                        route.sector_id,
                        route.profile.profile_id,
                        _mapping_sha256(
                            route.route_version,
                            _route_mapping_projection(
                                route.route_version,
                                route.profile,
                                route.mapping,
                            ),
                        ),
                    )
                    accepted[
                        (
                            hypothesis.transform_id,
                            hypothesis.polarity_id,
                            hypothesis.sector_id,
                            hypothesis.profile_id,
                            hypothesis.mapping_sha256,
                        )
                    ] = hypothesis
                    group_key = (
                        route.profile.profile_id,
                        route.shell_width,
                        route.mapping,
                        route.inventory_section_id,
                    )
                    route_groups[group_key] = route
                    route_group_counts[group_key] = (
                        route_group_counts.get(group_key, 0) + 1
                    )
                for group_key, route in route_groups.items():
                    observations = self._extract_units(
                        cells,
                        route.profile,
                        route.shell_width,
                        route.mapping,
                    )
                    result = self._recover_sections(
                        route.profile,
                        observations,
                        retain_extra_inputs=False,
                        transport_primitive_steps=route.transport_primitive_steps,
                        transport_peak_scratch=route.transport_peak_scratch,
                        repetition_primitive_steps=(
                            route.repetition_primitive_steps
                        ),
                        repetition_peak_scratch=(
                            route.repetition_peak_scratch
                        ),
                    )
                    transport_primitive_steps += (
                        route_group_counts[group_key]
                        * result.resource.primitive_steps
                    )
                    peak_scratch = max(
                        peak_scratch, result.resource.peak_scratch_bytes
                    )
                    if (
                        route.profile.profile_version
                        in self.establishing_profile_versions
                    ):
                        if result not in eligible_results:
                            eligible_results.append(result)
                        if result.inventory_available:
                            results.append(result)
        accepted_rows = tuple(
            accepted[key]
            for key in sorted(
                accepted,
                key=lambda item: (
                    item[0],
                    item[1],
                    item[2],
                    self.profile_order[item[3]],
                    item[4],
                ),
            )
        )
        ordered_route_profiles = tuple(
            sorted(route_profiles, key=self.profile_order.__getitem__)
        )
        if not results:
            if len(eligible_results) == 1:
                selected = eligible_results[0]
                return DecodeResult(
                    selected.artifact_state,
                    None,
                    selected.section_results,
                    ordered_route_profiles,
                    False,
                    selected.fragment_diagnostics,
                    selected.m2_required_stream,
                    selected.m2_all_stream,
                    ResourceUsage(
                        selected.resource.section_attempts,
                        route_primitive_steps + transport_primitive_steps,
                        peak_scratch,
                    ),
                    accepted_rows,
                )
            return DecodeResult(
                "failure",
                None,
                (),
                ordered_route_profiles,
                False,
                resource=ResourceUsage(
                    0,
                    route_primitive_steps + transport_primitive_steps,
                    peak_scratch,
                ),
                accepted_hypotheses=accepted_rows,
            )
        unique: list[DecodeResult] = []
        for result in results:
            normalized = replace(
                result,
                resource=ResourceUsage(),
                accepted_hypotheses=(),
            )
            if normalized not in unique:
                unique.append(normalized)
        if len(unique) > 1:
            return DecodeResult(
                "ambiguous",
                None,
                (),
                ordered_route_profiles,
                False,
                resource=ResourceUsage(
                    0,
                    route_primitive_steps + transport_primitive_steps,
                    peak_scratch,
                ),
                accepted_hypotheses=accepted_rows,
            )
        selected = next(
            result
            for result in results
            if replace(
                result,
                resource=ResourceUsage(),
                accepted_hypotheses=(),
            )
            == unique[0]
        )
        return DecodeResult(
            selected.artifact_state,
            selected.profile_id,
            selected.section_results,
            ordered_route_profiles,
            True,
            selected.fragment_diagnostics,
            selected.m2_required_stream,
            selected.m2_all_stream,
            ResourceUsage(
                selected.resource.section_attempts,
                route_primitive_steps + transport_primitive_steps,
                peak_scratch,
            ),
            accepted_rows,
        )

    def decode(self, channel: str, raw: bytes) -> DecodeResult:
        """Decode one exact channel serialization without evaluator knowledge."""

        if channel == OBS_BITS:
            side, cells = _parse_bits(raw)
            return self._decode_square(side, cells)
        if channel == OBS_MATRIX:
            side, cells = _parse_matrix(raw)
            return self._decode_square(side, cells)
        if channel == OBS_UNITS:
            observations = _parse_units(raw, self.maximum_units)
            # Freeze the observable/cache-filling procedure order independently
            # of serialized arrival order: input ID first, then registry order.
            # Shape-incompatible profiles still consume their logical resource
            # row below, but have no transport invocation to cache.
            for observation in sorted(
                observations, key=lambda item: item.unit_id
            ):
                for profile in self.profiles:
                    if len(observation.encoded) == profile.protected_unit_bytes:
                        self._decode_unit(
                            profile, observation.encoded, observation.erasures
                        )
            results: list[DecodeResult] = []
            primitive_steps = 0
            peak_scratch = 0
            for profile in self.profiles:
                steps, scratch = self.transport_resources[profile.profile_version]
                repetition_steps, repetition_scratch = (
                    self.repetition_resource
                    if profile.transport_id == m2_codec.HIER_TRANSPORT
                    else (0, 0)
                )
                result = self._recover_sections(
                    profile,
                    observations,
                    retain_extra_inputs=True,
                    transport_primitive_steps=steps,
                    transport_peak_scratch=scratch,
                    repetition_primitive_steps=repetition_steps,
                    repetition_peak_scratch=repetition_scratch,
                )
                primitive_steps += result.resource.primitive_steps
                peak_scratch = max(
                    peak_scratch, result.resource.peak_scratch_bytes
                )
                if (
                    result.inventory_available
                    and profile.profile_version
                    in self.establishing_profile_versions
                ):
                    results.append(result)
            if not results:
                unresolved = self._without_inventory(
                    self.profiles, observations
                )
                return DecodeResult(
                    "failure",
                    None,
                    unresolved.section_results,
                    (),
                    False,
                    unresolved.fragment_diagnostics,
                    resource=ResourceUsage(
                        unresolved.resource.section_attempts,
                        primitive_steps,
                        peak_scratch,
                    ),
                )
            unique = {
                (result.profile_id, self._semantic_key(result)): result
                for result in results
            }
            selected = next(iter(unique.values()))
            if len(unique) > 1:
                return DecodeResult(
                    "ambiguous",
                    None,
                    (),
                    (),
                    False,
                    resource=ResourceUsage(0, primitive_steps, peak_scratch),
                )
            return DecodeResult(
                selected.artifact_state,
                selected.profile_id,
                selected.section_results,
                (),
                True,
                selected.fragment_diagnostics,
                selected.m2_required_stream,
                selected.m2_all_stream,
                ResourceUsage(
                    selected.resource.section_attempts,
                    primitive_steps,
                    peak_scratch,
                ),
            )
        _fail("channel")

    def render_result(self, channel: str, result: DecodeResult) -> bytes:
        """Render under the schema admitted by this decoder's owner set."""

        return render_decoder_result(
            channel, result, schema_version=self.result_schema_version
        )


def decode_observation(
    channel: str,
    raw: bytes,
    profile_policy_raw: bytes,
    profile_limits_raw: bytes,
    damage_policy_raw: bytes,
) -> DecodeResult:
    """One-shot convenience wrapper around :class:`ObservationDecoder`."""

    return ObservationDecoder(
        profile_policy_raw, profile_limits_raw, damage_policy_raw
    ).decode(channel, raw)


def _canonical_array(value: list[dict[str, object]]) -> bytes:
    try:
        wrapped = canonical_manifest.serialize_manifest({"rows": value})
    except canonical_manifest.ManifestError:
        _fail("result-shape")
    prefix, suffix = b'{"rows":', b"}\n"
    if not wrapped.startswith(prefix) or not wrapped.endswith(suffix):
        _fail("result-shape")
    return wrapped[len(prefix) : -len(suffix)]


def render_decoder_result(
    channel: str,
    result: DecodeResult,
    *,
    schema_version: int = 0,
) -> bytes:
    """Render the frozen closed decoder-result projection."""

    if (
        channel not in (OBS_BITS, OBS_MATRIX, OBS_UNITS)
        or type(result) is not DecodeResult
        or type(schema_version) is not int
        or schema_version not in (0, 1)
    ):
        _fail("result-shape")
    v1 = schema_version == 1
    zero = "0" * 64
    profile_ids = (
        (
            "eh72-hier-r5-r2-r1-crc32c-v0",
            "eh72-r2-crc64-ecma-v0",
            "eh72-r3-crc32c-v0",
            "eh72-r3-crc64-ecma-v0",
            "rs255-191-crc32c-v0",
            "rs255-191-crc64-ecma-v0",
        )
        if v1
        else tuple(profile.profile_id for profile in m2_codec.candidate_profiles())
    )
    profile_order = {profile_id: index for index, profile_id in enumerate(profile_ids)}
    if (
        result.artifact_state
        not in ("exact", "degraded", "failure", "ambiguous", "resource-limit")
        or result.profile_id not in ((profile_ids[0], None) if v1 else (*profile_ids, None))
        or type(result.inventory_available) is not bool
        or (result.profile_id is None) == result.inventory_available
        or type(result.resource) is not ResourceUsage
        or any(
            type(value) is not int or not 0 <= value <= 0xFFFF_FFFF_FFFF_FFFF
            for value in (
                result.resource.section_attempts,
                result.resource.primitive_steps,
                result.resource.peak_scratch_bytes,
            )
        )
        or any(
            type(stream) is not bytes
            for stream in (result.m2_required_stream, result.m2_all_stream)
            if stream is not None
        )
        or (
            result.m2_all_stream is not None
            and result.m2_required_stream is None
        )
        or (channel == OBS_UNITS and result.accepted_hypotheses)
        or len(set(result.route_profile_ids)) != len(result.route_profile_ids)
        or any(profile_id not in profile_order for profile_id in result.route_profile_ids)
        or tuple(result.route_profile_ids)
        != tuple(sorted(result.route_profile_ids, key=profile_order.__getitem__))
    ):
        _fail("result-shape")
    section_rows = [
        {
            "section_id": item.section_id,
            "state": item.state,
            "semantic_sha256": (
                sha256(item.envelope).hexdigest()
                if item.envelope is not None
                else zero
            ),
        }
        for item in result.section_results
    ]
    section_ids = [row["section_id"] for row in section_rows]
    if (
        section_ids != sorted(set(section_ids))
        or any(
            type(item.section_id) is not int
            or not 1 <= item.section_id <= 0xFFFF_FFFF
            or item.state
            not in (
                "verified",
                "recovered",
                "incomplete",
                "corrupt",
                "ambiguous",
                "unknown",
            )
            or (
                item.envelope is not None
                and type(item.envelope) is not bytes
            )
            or (
                item.state in ("verified", "recovered")
                and item.envelope is None
            )
            or (
                item.state
                in ("incomplete", "corrupt", "ambiguous", "unknown")
                and item.envelope is not None
            )
            for item in result.section_results
        )
    ):
        _fail("result-shape")
    fragment_rows = []
    previous_input_id = 0
    for item in result.fragment_diagnostics:
        if (
            type(item.input_id) is not int
            or not previous_input_id < item.input_id <= 0xFFFF_FFFF
            or type(item.section_id) is not int
            or not 0 <= item.section_id <= 0xFFFF_FFFF
            or type(item.semantic_copy_id) is not int
            or not 0 <= item.semantic_copy_id <= 0xFFFF
            or type(item.fragment_index) is not int
            or not 0 <= item.fragment_index <= 0xFFFF
            or item.profile_id not in ("", *profile_ids)
            or item.state
            not in (
                "verified",
                "recovered",
                "missing",
                "corrupt",
                "ambiguous",
                "unknown",
            )
            or (
                item.common_block is not None
                and (
                    type(item.common_block) is not bytes
                    or len(item.common_block) != m2_codec.COMMON_BYTES
                )
            )
            or (
                item.state in ("verified", "recovered")
                and (item.common_block is None or not item.profile_id)
            )
            or (
                item.state in ("missing", "corrupt", "ambiguous", "unknown")
                and item.common_block is not None
            )
        ):
            _fail("result-shape")
        previous_input_id = item.input_id
        if v1:
            identity_absent = item.profile_id == ""
            identity_sentinels = (
                item.section_id == 0,
                item.semantic_copy_id == 0xFFFF,
                item.fragment_index == 0xFFFF,
            )
            replica_known = item.replica_index != 0xFFFF
            factor_known = item.physical_replica_count != 0xFFFF
            if (
                (
                    identity_absent
                    and not all(identity_sentinels)
                )
                or (
                    not identity_absent
                    and any(identity_sentinels)
                )
                or (
                    item.profile_id == profile_ids[0]
                    and item.semantic_copy_id != 0
                )
                or type(item.replica_index) is not int
                or type(item.physical_replica_count) is not int
                or replica_known != factor_known
                or (
                    replica_known
                    and (
                        item.physical_replica_count not in (1, 2, 5)
                        or not 0
                        <= item.replica_index
                        < item.physical_replica_count
                    )
                )
                or (
                    not result.inventory_available
                    and replica_known
                    and (
                        not 1 <= item.input_id <= 5
                        or item.physical_replica_count != 5
                        or item.replica_index != item.input_id - 1
                    )
                )
            ):
                _fail("result-shape")
        row = {
            "input_id": item.input_id,
            "profile_id": item.profile_id,
            "section_id": item.section_id,
            "semantic_copy_id": item.semantic_copy_id,
            "fragment_index": item.fragment_index,
            "state": item.state,
            "common_block_sha256": (
                sha256(item.common_block).hexdigest()
                if item.common_block is not None
                else zero
            ),
        }
        if v1:
            row["replica_index"] = item.replica_index
            row["physical_replica_count"] = item.physical_replica_count
        fragment_rows.append(row)
    accepted_rows = [
        {
            "transform_id": item.transform_id,
            "polarity_id": item.polarity_id,
            "sector_id": item.sector_id,
            "profile_id": item.profile_id,
            "mapping_sha256": item.mapping_sha256,
        }
        for item in result.accepted_hypotheses
    ]
    accepted_keys = []
    for item in result.accepted_hypotheses:
        if (
            type(item.transform_id) is not int
            or not 0 <= item.transform_id < 8
            or type(item.polarity_id) is not int
            or not 0 <= item.polarity_id < 2
            or type(item.sector_id) is not int
            or not 0 <= item.sector_id < 4
            or item.profile_id not in profile_order
            or type(item.mapping_sha256) is not str
            or len(item.mapping_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in item.mapping_sha256
            )
        ):
            _fail("result-shape")
        accepted_keys.append(
            (
                item.transform_id,
                item.polarity_id,
                item.sector_id,
                profile_order[item.profile_id],
                item.mapping_sha256,
            )
        )
    if accepted_keys != sorted(set(accepted_keys)):
        _fail("result-shape")
    if v1:
        accepted_profile_ids = {item.profile_id for item in result.accepted_hypotheses}
        if result.route_profile_ids != tuple(
            profile_id
            for profile_id in profile_ids
            if profile_id in accepted_profile_ids
        ):
            _fail("result-shape")
        if (
            result.artifact_state in ("exact", "degraded")
            and result.profile_id != profile_ids[0]
        ):
            _fail("result-shape")
        if result.artifact_state == "exact" and (
            not result.section_results
            or any(
                item.state not in ("verified", "recovered")
                for item in result.section_results
            )
            or result.m2_required_stream is None
            or result.m2_all_stream is None
        ):
            _fail("result-shape")
        if result.artifact_state == "degraded" and (
            not result.section_results
            or result.m2_required_stream is None
        ):
            _fail("result-shape")
        if result.artifact_state == "resource-limit" and (
            result.profile_id is not None
            or result.section_results
            or result.fragment_diagnostics
            or result.m2_required_stream is not None
            or result.m2_all_stream is not None
            or result.accepted_hypotheses
            or result.route_profile_ids
        ):
            _fail("result-shape")
    value = {
        "schema": (
            "golden-board.m2-damage-decoder-result/v1"
            if v1
            else "golden-board.m2-damage-decoder-result/v0"
        ),
        "channel": channel,
        "artifact_state": result.artifact_state,
        "established_profile_id": result.profile_id or "",
        "section_rows": section_rows,
        "fragment_diagnostics_sha256": sha256(
            _canonical_array(fragment_rows)
        ).hexdigest(),
        "m2_required_available": result.m2_required_stream is not None,
        "m2_all_available": result.m2_all_stream is not None,
        "m2_required_stream_sha256": (
            sha256(result.m2_required_stream).hexdigest()
            if result.m2_required_stream is not None
            else zero
        ),
        "m2_all_stream_sha256": (
            sha256(result.m2_all_stream).hexdigest()
            if result.m2_all_stream is not None
            else zero
        ),
        "resource": {
            "section_attempts": result.resource.section_attempts,
            "primitive_steps": result.resource.primitive_steps,
            "peak_scratch_bytes": result.resource.peak_scratch_bytes,
        },
        "accepted_hypothesis_rows": accepted_rows,
    }
    try:
        raw = canonical_manifest.serialize_manifest(value)
    except canonical_manifest.ManifestError:
        _fail("result-shape")
    if v1 and len(raw) > 1_048_576:
        _fail("result-shape")
    return raw


def section_attempt_boundary_kat() -> bytes:
    """Execute the frozen 4096-allowed/4097th-rejected assembly boundary."""

    ceiling = 4_096
    candidates = tuple(
        bootstrap.SectionWitness(
            bootstrap.encode_section_envelope(
                bootstrap.SectionEnvelope(
                    4_000,
                    6,
                    0,
                    129,
                    1,
                    (),
                    index.to_bytes(2, "big"),
                )
            ),
            True,
        )
        for index in range(4_097)
    )
    ordered = tuple(sorted(candidates, key=lambda item: item.envelope))
    try:
        bootstrap.recover_logical_section(ordered)
    except bootstrap.BootstrapReject as error:
        if error.code != bootstrap.RESOURCE_LIMIT:
            _fail("boundary-kat")
    else:
        _fail("boundary-kat")
    return canonical_manifest.serialize_manifest(
        {
            "schema": "golden-board.m2-boundary-kat-result/v0",
            "kat_id": "section-attempt-ceiling-plus-one",
            "artifact_state": "resource-limit",
            "candidates_present": len(candidates),
            "candidates_checked": ceiling,
            "rejected_candidate_ordinal": ceiling,
            "section_output_sha256": "0" * 64,
        }
    )


_R3_BOUNDARY_KAT_IDS = (
    "rep2-correction-boundary",
    "rep5-correction-boundary",
    "complete-section-conflict",
    "section-attempt-ceiling-plus-one",
)


def _r3_boundary_result(kat_id: str, passed: bool) -> bytes:
    if kat_id not in _R3_BOUNDARY_KAT_IDS or type(passed) is not bool:
        _fail("boundary-kat")
    return canonical_manifest.serialize_manifest(
        {
            "schema": "golden-board.m2-boundary-kat-result/v1",
            "kat_id": kat_id,
            "result": "pass" if passed else "fail",
        }
    )


def _r3_repetition_boundary(factor: int) -> bool:
    """Assert the exact strict 2e+s boundary through both v1 adapters."""

    profile = m2_codec.r3_candidate_profile()
    envelope = bootstrap.encode_section_envelope(
        bootstrap.SectionEnvelope(4_001 + factor, 6, 0, 129, 1, (), b"kat")
    )
    common = bootstrap.fragment_section(envelope, 7, 0)[0]
    encoded = m2_codec.eh72_encode_unit(common)
    clean = m2_codec.CopyObservation(encoded, ())
    if factor == 2:
        direct_correction = m2_codec.repetition_symbol_counts(2, 1, 0)
        direct_rejection = m2_codec.repetition_symbol_counts(2, 1, 1)
        corrected = m2_codec.aggregate_replica_group(
            profile, (clean, None)
        )
        mask = bytes(
            0xAA if index % 2 == 0 else 0x55
            for index in range(len(encoded))
        )
        opposite = bytes(left ^ right for left, right in zip(mask, b"\xff" * len(mask), strict=True))
        rejected = m2_codec.aggregate_replica_group(
            profile,
            (
                m2_codec.CopyObservation(
                    bytes(left ^ right for left, right in zip(encoded, mask, strict=True)),
                    (),
                ),
                m2_codec.CopyObservation(
                    bytes(left ^ right for left, right in zip(encoded, opposite, strict=True)),
                    (),
                ),
            ),
        )
    elif factor == 5:
        direct_correction = m2_codec.repetition_symbol_counts(5, 2, 1)
        direct_rejection = m2_codec.repetition_symbol_counts(5, 2, 2)
        corrected = m2_codec.aggregate_replica_group(
            # One known lane plus four erased lanes is the exact product-
            # adapter 2e+s=4 boundary, not merely an easier majority case.
            profile, (clean, None, None, None, None)
        )
        mask = bytes(
            0xAA if index % 2 == 0 else 0x55
            for index in range(len(encoded))
        )
        opposite = bytes(left ^ 0xFF for left in mask)
        rejected = m2_codec.aggregate_replica_group(
            profile,
            (
                m2_codec.CopyObservation(
                    bytes(left ^ right for left, right in zip(encoded, mask, strict=True)),
                    (),
                ),
                m2_codec.CopyObservation(
                    bytes(left ^ right for left, right in zip(encoded, opposite, strict=True)),
                    (),
                ),
                None,
                None,
                None,
            ),
        )
    else:
        _fail("boundary-kat")
    return (
        direct_correction == (True, 0)
        and direct_rejection == (False, 0)
        and corrected.group_state in (2, 3)
        and corrected.chosen_block == common
        and rejected.group_state == 1
        and rejected.chosen_block == bytes(191)
    )


def r3_boundary_kat(ordinal: int) -> bytes:
    """Execute one frozen v1 KAT selected by its owner-order ordinal."""

    if type(ordinal) is not int or not 0 <= ordinal < len(_R3_BOUNDARY_KAT_IDS):
        _fail("boundary-kat")
    kat_id = _R3_BOUNDARY_KAT_IDS[ordinal]
    passed = False
    if ordinal in (0, 1):
        passed = _r3_repetition_boundary((2, 5)[ordinal])
    elif ordinal == 2:
        left = bootstrap.encode_section_envelope(
            bootstrap.SectionEnvelope(4_003, 6, 0, 129, 1, (), b"left")
        )
        right = bootstrap.encode_section_envelope(
            bootstrap.SectionEnvelope(4_003, 6, 0, 129, 1, (), b"right")
        )
        try:
            bootstrap.recover_logical_section(
                (
                    bootstrap.SectionWitness(left, True),
                    bootstrap.SectionWitness(right, True),
                )
            )
        except bootstrap.BootstrapReject as error:
            passed = error.code == bootstrap.AMBIGUOUS
    else:
        candidates = tuple(
            bootstrap.SectionWitness(
                bootstrap.encode_section_envelope(
                    bootstrap.SectionEnvelope(
                        4_004,
                        6,
                        0,
                        129,
                        1,
                        (),
                        index.to_bytes(2, "big"),
                    )
                ),
                True,
            )
            for index in range(4_097)
        )
        try:
            bootstrap.recover_logical_section(
                tuple(sorted(candidates, key=lambda item: item.envelope))
            )
        except bootstrap.BootstrapReject as error:
            passed = error.code == bootstrap.RESOURCE_LIMIT
    return _r3_boundary_result(kat_id, passed)


__all__ = [
    "DecodeResult",
    "DecoderError",
    "AcceptedHypothesis",
    "FragmentDiagnostic",
    "OBS_BITS",
    "OBS_MATRIX",
    "OBS_UNITS",
    "ObservationDecoder",
    "ResourceUsage",
    "SectionResult",
    "decode_observation",
    "render_decoder_result",
    "r3_boundary_kat",
    "section_attempt_boundary_kat",
]
