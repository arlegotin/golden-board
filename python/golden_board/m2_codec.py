"""Independent Python implementations of the frozen M2 candidate codecs.

This module is deliberately smaller than the later route runner.  It owns the
candidate transforms, bounded EH72 recovery, semantic-copy aggregation, and
the RS field/encoder/syndrome primitives that can be implemented from the
pre-result contract.  RS correction stays unavailable until that contract
pins one exact decoder procedure.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations, product
from typing import Iterable, Sequence
import tomllib

from . import bootstrap, m2_policy


__all__ = (
    "CandidateProfile",
    "CodecError",
    "CopyObservation",
    "Recovery",
    "ReplicaGroupResult",
    "RsDecodeResult",
    "alpha_pow",
    "candidate_profiles",
    "check_bytes",
    "build_eh72_encoder_recipe",
    "build_rs255_191_encoder_recipe",
    "eh72_decode",
    "eh72_encode",
    "eh72_encode_unit",
    "execute_eh72_encoder_recipe",
    "execute_rs255_191_encoder_recipe",
    "gf256_inverse",
    "gf256_multiply",
    "load_candidate_profiles",
    "r3_candidate_profile",
    "r3_registry_profiles",
    "recover_replica_group",
    "aggregate_replica_group",
    "physical_group_index",
    "repetition_symbol",
    "repetition_symbol_counts",
    "recover_profile_copies",
    "rs255_191_encode",
    "rs255_191_decode",
    "rs255_191_is_codeword",
    "rs255_191_syndromes",
    "rs_generator_coefficients",
)


EH_TRANSPORT = "eh72-replicated-v0"
HIER_TRANSPORT = "eh72-hier-repetition-v0"
RS_TRANSPORT = "rs255-191-v0"
CRC32C = "crc32c-v0"
CRC64_ECMA = "crc64-ecma-v0"
COMMON_BYTES = 191
EH_UNIT_BYTES = 216
RS_UNIT_BYTES = 255
_EH_PARITY_POSITIONS = frozenset((1, 2, 4, 8, 16, 32, 64))
_RS_GENERATOR_HEX = (
    "01c10aff3a80b7738c99935bc5dbdddc8e1c7815a49306cc28e6b60e79308f"
    "4de451552ba210c3a323959a2384646433b00ba186d084f4b0c0dde8ab7d9be4f2f5"
)
_RS_DECODER = {
    "id": "syndrome-bm-forney-v0",
    "owner": "spec/bootstrap-v0.md-section-17",
    "erased_symbol_fill": 0,
    "syndrome_first_root": 0,
    "syndrome_count": 64,
    "polynomial_coefficient_order": "ascending-degree-in-decoder",
    "erasure_locator_factor": "one-plus-alpha-to-254-minus-position-times-z",
    "modified_syndrome": "first-64-coefficients-of-syndrome-times-erasure-locator-then-drop-first-s",
    "unknown_locator": "canonical-berlekamp-massey",
    "bm_update_condition": "two-L-less-than-or-equal-to-n",
    "chien_position_order": "0-through-254",
    "chien_argument": "alpha-to-position-plus-1-mod-255",
    "evaluator": "first-64-coefficients-of-syndrome-times-full-locator",
    "formal_derivative": "odd-degree-locator-coefficients-only",
    "magnitude": "alpha-to-254-minus-position-times-evaluator-at-chien-argument-divided-by-formal-derivative",
    "correction_order": "position-ascending-after-all-magnitudes-derived",
    "postcheck": "all-64-syndromes-zero-then-transport-pad-and-local-check",
    "retry_count": 0,
    "alternate_erasure_fill_count": 0,
    "list_decoding": False,
    "check_directed_search": False,
    "syndrome_coefficients_max": 64,
    "erasure_locator_coefficients_max": 65,
    "bm_input_coefficients_max": 64,
    "unknown_error_locator_coefficients_max": 33,
    "full_locator_coefficients_max": 65,
    "evaluator_coefficients_max": 64,
    "derivative_coefficients_max": 64,
    "correction_positions_max": 64,
    "chien_position_evaluations": 255,
    "field_multiplication_calls_max": 80_000,
    "field_inverse_calls_max": 128,
    "promoted_primitive_steps_max": 1_000_000,
    "status_parameter": 3,
    "status_algebra_boundary": 4,
    "status_no_unique_codeword": 5,
    "status_local_check": 6,
    "status_resource_limit": 11,
}
_PROFILE_ROWS = (
    ("eh72-r2-crc32c-v0", 1, EH_TRANSPORT, CRC32C, 2, 1, 216, 2427, 524232),
    ("eh72-r2-crc64-ecma-v0", 2, EH_TRANSPORT, CRC64_ECMA, 2, 1, 216, 2427, 524232),
    ("eh72-r3-crc32c-v0", 3, EH_TRANSPORT, CRC32C, 3, 1, 216, 2427, 524232),
    ("eh72-r3-crc64-ecma-v0", 4, EH_TRANSPORT, CRC64_ECMA, 3, 1, 216, 2427, 524232),
    ("rs255-191-crc32c-v0", 5, RS_TRANSPORT, CRC32C, 2, 2, 255, 2056, 524280),
    ("rs255-191-crc64-ecma-v0", 6, RS_TRANSPORT, CRC64_ECMA, 2, 2, 255, 2056, 524280),
)
_R3_PROFILE_ROW = (
    "eh72-hier-r5-r2-r1-crc32c-v0",
    7,
    HIER_TRANSPORT,
    CRC32C,
    1,
    1,
    216,
)


class CodecError(ValueError):
    """A stable, fail-closed candidate-codec rejection."""

    __slots__ = ("_reason",)

    def __init__(self, reason: str) -> None:
        self._reason = reason
        super().__init__(reason)

    @property
    def reason(self) -> str:
        return self._reason


@dataclass(frozen=True, slots=True)
class CandidateProfile:
    profile_id: str
    profile_version: int
    transport_id: str
    section_check_id: str
    check_bytes: int
    required_copy_count: int
    complexity_class: int
    protected_unit_bytes: int
    protected_units: int
    encoded_transport_bytes: int
    inventory_version: int = 0
    placement_id: str = "affine-interior-v0"
    physical_replica_counts: tuple[int, ...] = (1,)


@dataclass(frozen=True, slots=True)
class Recovery:
    """Atomic recovery result; unsuccessful states never expose bytes."""

    state: str
    decoded: bytes | None
    constructions: int = 0


@dataclass(frozen=True, slots=True)
class ReplicaGroupResult:
    """Fixed-output projection of the exact bounded v1 group adapter."""

    status: int
    group_state: int
    distinct_candidate_count: int
    chosen_block: bytes
    lane_states: tuple[int, ...]
    lane_blocks: tuple[bytes, ...]
    repetition_state: int
    repetition_block: bytes
    constructions: int = 0


@dataclass(frozen=True, slots=True)
class RsDecodeResult:
    state: str
    decoded: bytes | None
    status: int
    correction_positions: tuple[int, ...] = ()
    correction_magnitudes: tuple[int, ...] = ()
    field_multiplications: int = 0
    field_inversions: int = 0
    primitive_steps: int = 0


@dataclass(frozen=True, slots=True)
class CopyObservation:
    encoded: bytes
    erasures: tuple[int, ...] = ()


def _fixed_profiles() -> tuple[CandidateProfile, ...]:
    check_widths = {CRC32C: 4, CRC64_ECMA: 8}
    return tuple(
        CandidateProfile(
            profile_id,
            version,
            transport,
            check,
            check_widths[check],
            copies,
            complexity,
            unit_bytes,
            units,
            encoded_bytes,
        )
        for (
            profile_id,
            version,
            transport,
            check,
            copies,
            complexity,
            unit_bytes,
            units,
            encoded_bytes,
        ) in _PROFILE_ROWS
    )


def candidate_profiles() -> tuple[CandidateProfile, ...]:
    """Return the exact closed six-tuple candidate set."""

    return _fixed_profiles()


def r3_candidate_profile(
    *, protected_units: int = 0, encoded_transport_bytes: int = 0
) -> CandidateProfile:
    """Return the frozen R3 shape, optionally with generated admitted limits.

    Zero limits are an explicitly pending structural value and are rejected by
    carrier/decoder admission.  They let the codec KATs exist before the route
    package generates the authoritative v1 limits.
    """

    (
        profile_id,
        version,
        transport,
        check,
        copies,
        complexity,
        unit_bytes,
    ) = _R3_PROFILE_ROW
    if (
        type(protected_units) is not int
        or type(encoded_transport_bytes) is not int
        or protected_units < 0
        or encoded_transport_bytes < 0
        or (protected_units == 0) != (encoded_transport_bytes == 0)
        or (
            protected_units > 0
            and encoded_transport_bytes != protected_units * unit_bytes
        )
    ):
        raise CodecError("r3-generated-limits")
    return CandidateProfile(
        profile_id,
        version,
        transport,
        check,
        4,
        copies,
        complexity,
        unit_bytes,
        protected_units,
        encoded_transport_bytes,
        1,
        "affine-slot-then-interior-v1",
        (1, 2, 5),
    )


def r3_registry_profiles(
    active: CandidateProfile | None = None,
) -> tuple[CandidateProfile, ...]:
    """Return v7 followed by the exact five legacy negative fixtures v2--v6."""

    v7 = r3_candidate_profile() if active is None else active
    if not _is_r3_profile(v7):
        raise CodecError("r3-profile")
    legacy = _fixed_profiles()
    return (v7,) + legacy[1:]


def _is_r3_profile(profile: CandidateProfile) -> bool:
    structural = r3_candidate_profile()
    return (
        type(profile) is CandidateProfile
        and profile.profile_id == structural.profile_id
        and profile.profile_version == structural.profile_version
        and profile.transport_id == structural.transport_id
        and profile.section_check_id == structural.section_check_id
        and profile.check_bytes == structural.check_bytes
        and profile.required_copy_count == structural.required_copy_count
        and profile.complexity_class == structural.complexity_class
        and profile.protected_unit_bytes == structural.protected_unit_bytes
        and profile.inventory_version == structural.inventory_version
        and profile.placement_id == structural.placement_id
        and profile.physical_replica_counts == structural.physical_replica_counts
        and profile.protected_units >= 0
        and profile.encoded_transport_bytes
        == profile.protected_units * profile.protected_unit_bytes
    )


def load_candidate_profiles(
    profile_policy_raw: bytes, profile_limits_raw: bytes
) -> tuple[CandidateProfile, ...]:
    """Admit the frozen policy and its exact codec-relevant limit projection."""

    try:
        policy = m2_policy.load_profile_policy(profile_policy_raw)
    except (m2_policy.PolicyError, KeyError, TypeError, ValueError) as error:
        raise CodecError("profile-policy") from error
    if type(profile_limits_raw) is not bytes or not 1 <= len(profile_limits_raw) <= 65_536:
        raise CodecError("profile-limits")
    try:
        policy_doc = tomllib.loads(profile_policy_raw.decode("utf-8"))
        limits_doc = tomllib.loads(profile_limits_raw.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as error:
        raise CodecError("owner-toml") from error
    expected = _fixed_profiles()
    rows = policy_doc.get("profile")
    limit_rows = limits_doc.get("profile")
    if (
        limits_doc.get("schema") != "golden-board.profile-limits/v0"
        or limits_doc.get("profile_policy_sha256") != policy.sha256
        or type(rows) is not list
        or type(limit_rows) is not list
        or len(rows) != 6
        or len(limit_rows) != 6
    ):
        raise CodecError("owner-shape")
    for index, item in enumerate(expected):
        row = rows[index]
        limit = limit_rows[index]
        observed_policy = (
            row.get("id"),
            row.get("profile_version"),
            row.get("transport_id"),
            row.get("section_check_id"),
            row.get("required_copy_count"),
            row.get("complexity_class"),
        )
        observed_limit = (
            limit.get("id"),
            limit.get("profile_version"),
            limit.get("check_bytes"),
            limit.get("required_copy_count"),
            limit.get("protected_unit_bytes"),
            limit.get("protected_units"),
            limit.get("encoded_transport_bytes"),
        )
        if observed_policy != (
            item.profile_id,
            item.profile_version,
            item.transport_id,
            item.section_check_id,
            item.required_copy_count,
            item.complexity_class,
        ) or observed_limit != (
            item.profile_id,
            item.profile_version,
            item.check_bytes,
            item.required_copy_count,
            item.protected_unit_bytes,
            item.protected_units,
            item.encoded_transport_bytes,
        ):
            raise CodecError(f"profile[{index}]")
    transport = policy_doc.get("transport", {})
    eh = transport.get("eh72", {})
    rs = transport.get("rs255_191", {})
    if (
        tuple(eh.get("hamming_parity_positions", ())) != (1, 2, 4, 8, 16, 32, 64)
        or tuple(eh.get("copy_counts", ())) != (2, 3)
        or (
            eh.get("code_length_bits"),
            eh.get("data_length_bits"),
            eh.get("minimum_distance"),
            eh.get("overall_parity_position"),
            eh.get("mixed_bound"),
        ) != (72, 64, 4, 72, 3)
        or (
            rs.get("field_modulus"),
            rs.get("primitive_element"),
            rs.get("first_root_exponent"),
            rs.get("root_count"),
            rs.get("code_symbols"),
            rs.get("data_symbols"),
            rs.get("parity_symbols"),
        ) != (0x11D, 2, 0, 64, 255, 191, 64)
        or rs.get("generator_coefficients_hex") != _RS_GENERATOR_HEX
        or rs.get("decoder") != _RS_DECODER
    ):
        raise CodecError("transport-parameters")
    return expected


def check_bytes(check_id: str, preimage: bytes) -> bytes:
    if type(preimage) is not bytes:
        raise TypeError("preimage must be bytes")
    if check_id == CRC32C:
        return bootstrap.crc32c_v0(preimage).to_bytes(4, "big")
    if check_id == CRC64_ECMA:
        return bootstrap.crc64_ecma_v0(preimage).to_bytes(8, "big")
    raise CodecError("check-id")


def _bytes_to_bits(data: bytes) -> list[int]:
    return [((byte >> shift) & 1) for byte in data for shift in range(7, -1, -1)]


def _bits_to_bytes(bits: Sequence[int]) -> bytes:
    result = bytearray(len(bits) // 8)
    for index, bit in enumerate(bits):
        result[index // 8] |= bit << (7 - index % 8)
    return bytes(result)


def _eh_valid(bits: Sequence[int]) -> bool:
    if len(bits) != 72:
        return False
    for parity in _EH_PARITY_POSITIONS:
        if sum(bits[position - 1] for position in range(1, 72) if position & parity) & 1:
            return False
    return sum(bits) & 1 == 0


def eh72_encode(data: bytes) -> bytes:
    if type(data) is not bytes or len(data) != 8:
        raise CodecError("eh72-data-length")
    bits = [0] * 72
    source = iter(_bytes_to_bits(data))
    for position in range(1, 72):
        if position not in _EH_PARITY_POSITIONS:
            bits[position - 1] = next(source)
    for parity in _EH_PARITY_POSITIONS:
        bits[parity - 1] = sum(
            bits[position - 1]
            for position in range(1, 72)
            if position != parity and position & parity
        ) & 1
    bits[71] = sum(bits[:71]) & 1
    assert _eh_valid(bits)
    return _bits_to_bytes(bits)


def _erasures(values: Iterable[int], maximum: int, limit: int) -> tuple[int, ...]:
    if isinstance(values, (bytes, bytearray, str)):
        raise CodecError("erasures-type")
    try:
        result = tuple(values)
    except TypeError as error:
        raise CodecError("erasures-type") from error
    if (
        len(result) > limit
        or any(type(value) is not int or not 0 <= value < maximum for value in result)
        or len(set(result)) != len(result)
    ):
        raise CodecError("erasures-range")
    return tuple(sorted(result))


def _eh_erasures(values: Iterable[int]) -> tuple[int, ...]:
    if isinstance(values, (bytes, bytearray, str)):
        raise CodecError("erasures-type")
    try:
        result = tuple(values)
    except TypeError as error:
        raise CodecError("erasures-type") from error
    if (
        len(result) > 3
        or any(type(value) is not int or not 1 <= value <= 72 for value in result)
        or len(set(result)) != len(result)
    ):
        raise CodecError("erasures-range")
    return tuple(sorted(value - 1 for value in result))


def eh72_decode(observed: bytes, erasures: Iterable[int] = ()) -> Recovery:
    if type(observed) is not bytes or len(observed) != 9:
        raise CodecError("eh72-codeword-length")
    # The public EH coordinate is the frozen code position in 1..72.  Only the
    # bounded enumeration below uses zero-based Python bit indices.
    erased = _eh_erasures(erasures)
    known = tuple(index for index in range(72) if index not in set(erased))
    maximum_changes = (3 - len(erased)) // 2
    source = _bytes_to_bits(observed)
    candidates: set[bytes] = set()
    constructions = 0
    for fills in product((0, 1), repeat=len(erased)):
        filled = source.copy()
        for index, value in zip(erased, fills, strict=True):
            filled[index] = value
        for changed_count in range(maximum_changes + 1):
            for changed in combinations(known, changed_count):
                candidate = filled.copy()
                for index in changed:
                    candidate[index] ^= 1
                constructions += 1
                if _eh_valid(candidate):
                    candidates.add(_bits_to_bytes(candidate))
    if len(candidates) > 1:
        raise CodecError("eh72-distance-invariant")
    if not candidates:
        return Recovery("corrupt", None, constructions)
    encoded = next(iter(candidates))
    bits = _bytes_to_bits(encoded)
    data_bits = [
        bits[position - 1]
        for position in range(1, 72)
        if position not in _EH_PARITY_POSITIONS
    ]
    state = "verified" if not erased and encoded == observed else "recovered"
    return Recovery(state, _bits_to_bytes(data_bits), constructions)


def eh72_encode_unit(common_block: bytes) -> bytes:
    if type(common_block) is not bytes or len(common_block) != COMMON_BYTES:
        raise CodecError("common-block-length")
    padded = common_block + b"\0"
    return b"".join(eh72_encode(padded[offset : offset + 8]) for offset in range(0, 192, 8))


def _be(value: int, width: int) -> bytes:
    return value.to_bytes(width, "big")


def _recipe_descriptor(value_id: int, value_type: int, width: int) -> bytes:
    return b"".join(
        (_be(value_id, 2), bytes((value_type, 0)), _be(width, 4), _be(1, 4))
    )


def _recipe_node(
    node_id: int,
    opcode: int,
    value_type: int,
    width: int,
    arguments: tuple[int, ...] = (),
    auxiliary: int = 0,
    immediate: int = 0,
) -> bytes:
    return b"".join(
        (
            _be(node_id, 2),
            bytes((opcode, value_type)),
            _be(width, 4),
            _be(len(arguments), 2),
            b"".join(_be(value, 2) for value in arguments + (0,) * (4 - len(arguments))),
            _be(auxiliary, 2),
            bytes(4),
            _be(immediate, 8),
        )
    )


def _recipe_record(
    recipe_id: int,
    inputs: tuple[tuple[int, int], ...],
    outputs: tuple[tuple[int, int], ...],
    nodes: list[tuple[int, int, int, tuple[int, ...], int, int]],
    prior_resources: dict[int, tuple[int, int]] | None = None,
) -> tuple[bytes, int, int, int]:
    """Serialize one acyclic recipe and independently derive its resources."""

    input_count = len(inputs)
    edge_count = sum(len(node[3]) + (node[0] == 22) for node in nodes)
    resources = {} if prior_resources is None else prior_resources
    steps = len(nodes) + sum(
        node[5] * resources[node[4]][0] for node in nodes if node[0] == 22
    )
    last_use = {index: index for index in range(1, len(nodes) + 1)}
    for consumer, node in enumerate(nodes, 1):
        for value_id in node[3]:
            if value_id > input_count:
                last_use[value_id - input_count] = consumer
    live: dict[int, int] = {}
    peak = 0
    for node_id, node in enumerate(nodes, 1):
        opcode, value_type, width, _, auxiliary, _ = node
        storage = (
            0
            if value_type == bootstrap.TABLE
            else width
            if value_type == bootstrap.BYTES
            else (width + 7) // 8
        )
        live_bytes = sum(live.values())
        if opcode == 22:
            peak = max(peak, live_bytes + resources[auxiliary][1])
        peak = max(peak, live_bytes + storage)
        live[node_id] = storage
        for prior in tuple(live):
            if last_use[prior] == node_id:
                del live[prior]
    descriptors = b"".join(
        _recipe_descriptor(index, value_type, width)
        for index, (value_type, width) in enumerate(inputs, 1)
    ) + b"".join(
        _recipe_descriptor(index, value_type, width)
        for index, (value_type, width) in enumerate(outputs, 1)
    )
    node_bytes = b"".join(
        _recipe_node(index, opcode, value_type, width, arguments, auxiliary, immediate)
        for index, (opcode, value_type, width, arguments, auxiliary, immediate) in enumerate(nodes, 1)
    )
    recipe_bytes = 32 + len(descriptors) + len(node_bytes)
    header = b"".join(
        (
            _be(recipe_id, 2),
            bytes(2),
            _be(len(inputs), 2),
            _be(len(outputs), 2),
            _be(len(nodes), 4),
            _be(edge_count, 4),
            _be(steps, 8),
            _be(peak, 4),
            _be(recipe_bytes, 4),
        )
    )
    return header + descriptors + node_bytes, edge_count, steps, peak


@lru_cache(maxsize=4)
def build_eh72_encoder_recipe(profile_version: int) -> bytes:
    """Build the byte-ABI generic-opcode EH72 fact-108 encoder."""

    profile = next(
        (
            item
            for item in _fixed_profiles()
            if item.profile_version == profile_version and item.transport_id == EH_TRANSPORT
        ),
        None,
    )
    if profile is None:
        raise CodecError("eh72-profile-version")
    # EH72 is linear.  One closed table maps each of the sixteen input
    # nibbles and its value to a nine-byte codeword contribution.  The recipe
    # XORs all sixteen rows, keeping the public ABI byte-oriented as frozen by
    # route fact 8.  Rows are derived here from the parity equations rather
    # than from the production encoder.
    rows = []
    for nibble_ordinal in range(16):
        for nibble_value in range(16):
            data = [0] * 64
            base = nibble_ordinal * 4
            for offset in range(4):
                data[base + offset] = (nibble_value >> (3 - offset)) & 1
            positions: dict[int, int] = {}
            source = iter(data)
            for position in range(1, 72):
                if position not in _EH_PARITY_POSITIONS:
                    positions[position] = next(source)
            for parity in sorted(_EH_PARITY_POSITIONS):
                value = 0
                for position in range(1, 72):
                    if position != parity and position & parity:
                        value ^= positions.get(position, 0)
                positions[parity] = value
            overall = 0
            for position in range(1, 72):
                overall ^= positions[position]
            positions[72] = overall
            rows.append(
                _bits_to_bytes(
                    tuple(positions[position] for position in range(1, 73))
                )
            )
    table_specs = (
        (bootstrap.UINT, 64, 256, b"".join(row[:8] for row in rows)),
        (bootstrap.UINT, 8, 256, bytes(row[8] for row in rows)),
        (bootstrap.UINT, 8, 256, bytes(range(256))),
        (bootstrap.BYTES, 9, 1, bytes(9)),
    )
    table_records = tuple(
        b"".join(
            (
                _be(index + 1, 2),
                bytes((value_type, 0)),
                _be(width, 4),
                _be(count, 4),
                _be(len(payload), 4),
                payload,
            )
        )
        for index, (value_type, width, count, payload) in enumerate(table_specs)
    )
    inputs = ((bootstrap.BYTES, 8),)
    outputs = ((bootstrap.STATUS, 16), (bootstrap.BYTES, 9))
    nodes: list[tuple[int, int, int, tuple[int, ...], int, int]] = []

    def add(
        opcode: int,
        value_type: int,
        width: int,
        arguments: tuple[int, ...] = (),
        auxiliary: int = 0,
        immediate: int = 0,
    ) -> int:
        nodes.append((opcode, value_type, width, arguments, auxiliary, immediate))
        return len(inputs) + len(nodes)

    high_table = add(2, bootstrap.TABLE, 64, auxiliary=1)
    tail_table = add(2, bootstrap.TABLE, 8, auxiliary=2)
    identity_table = add(2, bootstrap.TABLE, 8, auxiliary=3)
    zero_table = add(2, bootstrap.TABLE, 9, auxiliary=4)
    shift = add(1, bootstrap.UINT, 8, immediate=4)
    input_indexes = tuple(
        add(1, bootstrap.UINT, 64, immediate=index) for index in range(8)
    )
    input_bytes = tuple(
        add(19, bootstrap.UINT, 8, (1, index)) for index in input_indexes
    )
    high_rows = []
    tail_rows = []
    for ordinal in range(16):
        value = input_bytes[ordinal // 2]
        nibble = (
            add(16, bootstrap.UINT, 8, (value, shift))
            if ordinal % 2 == 0
            else add(14, bootstrap.UINT, 8, (value,), immediate=0x0F)
        )
        base = add(1, bootstrap.UINT, 8, immediate=ordinal * 16)
        row_index = add(6, bootstrap.UINT, 8, (base, nibble))
        high_rows.append(
            add(21, bootstrap.UINT, 64, (high_table, row_index))
        )
        tail_rows.append(
            add(21, bootstrap.UINT, 8, (tail_table, row_index))
        )
    zero_index = add(1, bootstrap.UINT, 8, immediate=0)
    result = add(21, bootstrap.BYTES, 9, (zero_table, zero_index))
    high = high_rows[0]
    tail = tail_rows[0]
    for contribution in high_rows[1:]:
        high = add(13, bootstrap.UINT, 64, (high, contribution))
    for contribution in tail_rows[1:]:
        tail = add(13, bootstrap.UINT, 8, (tail, contribution))
    output_indexes = tuple(
        add(1, bootstrap.UINT, 64, immediate=index) for index in range(9)
    )
    for index, output_index in enumerate(output_indexes[:8]):
        shift_count = (7 - index) * 8
        shifted = (
            high
            if shift_count == 0
            else add(
                16,
                bootstrap.UINT,
                64,
                (high, add(1, bootstrap.UINT, 64, immediate=shift_count)),
            )
        )
        masked = add(14, bootstrap.UINT, 64, (shifted,), immediate=0xFF)
        value = add(
            21, bootstrap.UINT, 8, (identity_table, masked)
        )
        result = add(
            20, bootstrap.BYTES, 9, (result, output_index, value)
        )
    result = add(
        20, bootstrap.BYTES, 9, (result, output_indexes[8], tail)
    )
    success = add(24, bootstrap.STATUS, 16)
    add(5, bootstrap.STATUS, 16, (success,), auxiliary=1)
    add(5, bootstrap.STATUS, 16, (result,), auxiliary=2)
    record, edges, steps, peak = _recipe_record(108, inputs, outputs, nodes)
    tables = b"".join(table_records)
    package_bytes = 64 + len(tables) + len(record)
    header = b"".join(
        (
            b"GBRECP0\0",
            bytes(4),
            _be(profile.profile_version, 2),
            bytes(2),
            _be(1, 2),
            _be(len(table_records), 2),
            _be(len(nodes), 4),
            _be(edges, 4),
            _be(sum(len(item[3]) for item in table_specs), 4),
            _be(package_bytes, 4),
            _be(steps, 8),
            _be(peak, 4),
            bytes(16),
        )
    )
    package = header + tables + record
    # Builder output is not usable until the candidate-neutral interpreter has
    # independently accepted the complete binary package.
    bootstrap.decode_recipe_package(package, profile.profile_version)
    return package


def execute_eh72_encoder_recipe(profile_version: int, data: bytes) -> bytes:
    if type(data) is not bytes or len(data) != 8:
        raise CodecError("eh72-data-length")
    package = bootstrap.decode_recipe_package(
        build_eh72_encoder_recipe(profile_version), profile_version
    )
    result = bootstrap.evaluate_recipe(package, 108, (data,))
    if result.status != 0 or len(result.outputs) != 1 or len(result.outputs[0]) != 9:
        raise CodecError("eh72-recipe-result")
    return result.outputs[0]


@lru_cache(maxsize=2)
def build_rs255_191_encoder_recipe(profile_version: int) -> bytes:
    """Build a compact fixed-iteration generic-opcode RS encoder."""

    profile = next(
        (
            item
            for item in _fixed_profiles()
            if item.profile_version == profile_version and item.transport_id == RS_TRANSPORT
        ),
        None,
    )
    if profile is None:
        raise CodecError("rs-profile-version")
    generator = rs_generator_coefficients()
    exponents = [1]
    for _ in range(1, 510):
        exponents.append(_gf_mul(exponents[-1], 2))
    logarithms = [0] * 256
    for exponent, value in enumerate(exponents[:255]):
        logarithms[value] = exponent
    table_specs = (
        (bootstrap.UINT, 8, 256, bytes(logarithms)),
        (bootstrap.UINT, 8, 510, bytes(exponents)),
        (bootstrap.UINT, 8, 64, generator[1:]),
        (bootstrap.BYTES, 65, 1, bytes(65)),
    )
    table_records = tuple(
        b"".join(
            (
                _be(index + 1, 2),
                bytes((value_type, 0)),
                _be(width, 4),
                _be(count, 4),
                _be(len(payload), 4),
                payload,
            )
        )
        for index, (value_type, width, count, payload) in enumerate(table_specs)
    )
    resources: dict[int, tuple[int, int]] = {}
    records: list[bytes] = []
    totals: list[tuple[int, int, int]] = []

    def record(
        recipe_id: int,
        inputs: tuple[tuple[int, int], ...],
        outputs: tuple[tuple[int, int], ...],
        build: object,
    ) -> None:
        nodes: list[tuple[int, int, int, tuple[int, ...], int, int]] = []

        def add(
            opcode: int,
            value_type: int,
            width: int,
            arguments: tuple[int, ...] = (),
            auxiliary: int = 0,
            immediate: int = 0,
        ) -> int:
            nodes.append((opcode, value_type, width, arguments, auxiliary, immediate))
            return len(inputs) + len(nodes)

        build(add)
        raw, edges, steps, peak = _recipe_record(
            recipe_id, inputs, outputs, nodes, resources
        )
        records.append(raw)
        resources[recipe_id] = (steps, peak)
        totals.append((len(nodes), edges, peak))

    state_inputs = ((bootstrap.BYTES, 256), (bootstrap.UINT, 64))
    state_outputs = ((bootstrap.STATUS, 16), (bootstrap.BYTES, 256))

    def zero_body(add: object) -> None:
        base = add(1, bootstrap.UINT, 64, immediate=191)
        position = add(6, bootstrap.UINT, 64, (base, 2))
        value = add(19, bootstrap.UINT, 8, (1, position))
        zero = add(1, bootstrap.UINT, 8, immediate=0)
        valid = add(17, bootstrap.BOOL, 1, (value, zero))
        success = add(24, bootstrap.STATUS, 16)
        parameter = add(25, bootstrap.STATUS, 16, immediate=3)
        status = add(23, bootstrap.STATUS, 16, (valid, success, parameter))
        add(5, bootstrap.STATUS, 16, (status,), auxiliary=1)
        add(5, bootstrap.STATUS, 16, (1,), auxiliary=2)

    record(1, state_inputs, state_outputs, zero_body)

    def parity_body(add: object) -> None:
        log_table = add(2, bootstrap.TABLE, 8, auxiliary=1)
        exp_table = add(2, bootstrap.TABLE, 8, auxiliary=2)
        generator_table = add(2, bootstrap.TABLE, 8, auxiliary=3)
        feedback_index = add(1, bootstrap.UINT, 64, immediate=255)
        feedback = add(19, bootstrap.UINT, 8, (1, feedback_index))
        factor = add(21, bootstrap.UINT, 8, (generator_table, 2))
        zero8 = add(1, bootstrap.UINT, 8, immediate=0)
        feedback_zero = add(17, bootstrap.BOOL, 1, (feedback, zero8))
        factor_zero = add(17, bootstrap.BOOL, 1, (factor, zero8))
        feedback_log = add(21, bootstrap.UINT, 8, (log_table, feedback))
        factor_log = add(21, bootstrap.UINT, 8, (log_table, factor))
        feedback_wide = add(4, bootstrap.UINT, 16, (zero8, feedback_log))
        factor_wide = add(4, bootstrap.UINT, 16, (zero8, factor_log))
        exponent = add(6, bootstrap.UINT, 16, (feedback_wide, factor_wide))
        product_nonzero = add(21, bootstrap.UINT, 8, (exp_table, exponent))
        product_left = add(
            23, bootstrap.UINT, 8, (feedback_zero, zero8, product_nonzero)
        )
        product_value = add(
            23, bootstrap.UINT, 8, (factor_zero, zero8, product_left)
        )
        next_base = add(1, bootstrap.UINT, 64, immediate=192)
        next_index = add(6, bootstrap.UINT, 64, (next_base, 2))
        following = add(19, bootstrap.UINT, 8, (1, next_index))
        combined = add(13, bootstrap.UINT, 8, (product_value, following))
        last = add(1, bootstrap.UINT, 64, immediate=63)
        is_last = add(17, bootstrap.BOOL, 1, (2, last))
        selected = add(
            23, bootstrap.UINT, 8, (is_last, product_value, combined)
        )
        parity_base = add(1, bootstrap.UINT, 64, immediate=191)
        parity_index = add(6, bootstrap.UINT, 64, (parity_base, 2))
        updated = add(20, bootstrap.BYTES, 256, (1, parity_index, selected))
        success = add(24, bootstrap.STATUS, 16)
        add(5, bootstrap.STATUS, 16, (success,), auxiliary=1)
        add(5, bootstrap.STATUS, 16, (updated,), auxiliary=2)

    record(2, state_inputs, state_outputs, parity_body)

    def data_body(add: object) -> None:
        data_value = add(19, bootstrap.UINT, 8, (1, 2))
        parity_index = add(1, bootstrap.UINT, 64, immediate=191)
        parity_first = add(19, bootstrap.UINT, 8, (1, parity_index))
        feedback = add(13, bootstrap.UINT, 8, (data_value, parity_first))
        feedback_index = add(1, bootstrap.UINT, 64, immediate=255)
        staged = add(20, bootstrap.BYTES, 256, (1, feedback_index, feedback))
        encoded = add(
            22,
            bootstrap.BYTES,
            256,
            (staged,),
            auxiliary=2,
            immediate=64,
        )
        success = add(24, bootstrap.STATUS, 16)
        add(5, bootstrap.STATUS, 16, (success,), auxiliary=1)
        add(5, bootstrap.STATUS, 16, (encoded,), auxiliary=2)

    record(3, state_inputs, state_outputs, data_body)

    main_inputs = ((bootstrap.BYTES, 191),)
    main_outputs = ((bootstrap.STATUS, 16), (bootstrap.BYTES, 255))

    def main(add: object) -> None:
        zero_table = add(2, bootstrap.TABLE, 65, auxiliary=4)
        zero_index = add(1, bootstrap.UINT, 64, immediate=0)
        zero_pad = add(
            21, bootstrap.BYTES, 65, (zero_table, zero_index)
        )
        staged = add(4, bootstrap.BYTES, 256, (1, zero_pad))
        checked = add(
            22,
            bootstrap.BYTES,
            256,
            (staged,),
            auxiliary=1,
            immediate=65,
        )
        encoded = add(
            22,
            bootstrap.BYTES,
            256,
            (checked,),
            auxiliary=3,
            immediate=191,
        )
        zero = add(1, bootstrap.UINT, 64, immediate=0)
        length = add(1, bootstrap.UINT, 64, immediate=255)
        result = add(3, bootstrap.BYTES, 255, (encoded, zero, length))
        success = add(24, bootstrap.STATUS, 16)
        add(5, bootstrap.STATUS, 16, (success,), auxiliary=1)
        add(5, bootstrap.STATUS, 16, (result,), auxiliary=2)

    record(108, main_inputs, main_outputs, main)
    tables = b"".join(table_records)
    package_bytes = 64 + len(tables) + sum(map(len, records))
    if package_bytes > bootstrap.RECIPE_PACKAGE_MAX:
        raise CodecError("rs-recipe-package-limit")
    total_nodes = sum(item[0] for item in totals)
    total_edges = sum(int.from_bytes(raw[12:16], "big") for raw in records)
    header = b"".join(
        (
            b"GBRECP0\0",
            bytes(4),
            _be(profile.profile_version, 2),
            bytes(2),
            _be(len(records), 2),
            _be(len(table_records), 2),
            _be(total_nodes, 4),
            _be(total_edges, 4),
            _be(sum(len(item[3]) for item in table_specs), 4),
            _be(package_bytes, 4),
            _be(max(item[0] for item in resources.values()), 8),
            _be(max(item[1] for item in resources.values()), 4),
            bytes(16),
        )
    )
    package = header + tables + b"".join(records)
    bootstrap.decode_recipe_package(package, profile.profile_version)
    return package


def execute_rs255_191_encoder_recipe(profile_version: int, data: bytes) -> bytes:
    if type(data) is not bytes or len(data) != COMMON_BYTES:
        raise CodecError("rs-data-length")
    package = bootstrap.decode_recipe_package(
        build_rs255_191_encoder_recipe(profile_version), profile_version
    )
    result = bootstrap.evaluate_recipe(package, 108, (data,))
    if result.status != 0 or len(result.outputs) != 1 or len(result.outputs[0]) != 255:
        raise CodecError("rs-recipe-result")
    return result.outputs[0]


def _eh72_decode_unit(
    encoded: bytes, erasures: Iterable[int], expected_profile_version: int
) -> Recovery:
    if type(encoded) is not bytes or len(encoded) != EH_UNIT_BYTES:
        raise CodecError("eh72-unit-length")
    erased = _erasures(erasures, EH_UNIT_BYTES * 8, 72)
    by_codeword: list[list[int]] = [[] for _ in range(24)]
    for index in erased:
        # CopyObservation uses flattened zero-based observation coordinates;
        # the codeword decoder ABI uses one-based EH code positions.
        by_codeword[index // 72].append(index % 72 + 1)
    if any(len(items) > 3 for items in by_codeword):
        return Recovery("corrupt", None, 0)
    recovered = bytearray()
    state = "verified"
    constructions = 0
    for ordinal in range(24):
        result = eh72_decode(
            encoded[ordinal * 9 : (ordinal + 1) * 9], by_codeword[ordinal]
        )
        constructions += result.constructions
        if result.decoded is None:
            return Recovery("corrupt", None, constructions)
        if result.state != "verified":
            state = "recovered"
        recovered.extend(result.decoded)
    if recovered[-1] != 0:
        return Recovery("corrupt", None, constructions)
    common = bytes(recovered[:-1])
    try:
        bootstrap.decode_common_block(common, expected_profile_version)
    except bootstrap.BootstrapReject:
        return Recovery("corrupt", None, constructions)
    return Recovery(state, common, constructions)


def _gf_mul(left: int, right: int) -> int:
    result = 0
    for _ in range(8):
        if right & 1:
            result ^= left
        carry = left & 0x80
        left = (left << 1) & 0xFF
        if carry:
            left ^= 0x1D
        right >>= 1
    return result


def gf256_multiply(left: int, right: int) -> int:
    if (
        type(left) is not int
        or type(right) is not int
        or not 0 <= left <= 255
        or not 0 <= right <= 255
    ):
        raise CodecError("field-element")
    return _gf_mul(left, right)


def _gf_pow(exponent: int) -> int:
    result = 1
    base = 2
    while exponent:
        if exponent & 1:
            result = _gf_mul(result, base)
        base = _gf_mul(base, base)
        exponent >>= 1
    return result


def alpha_pow(exponent: int) -> int:
    if type(exponent) is not int:
        raise CodecError("field-exponent")
    return _gf_pow(exponent % 255)


def gf256_inverse(value: int) -> int:
    if type(value) is not int or not 1 <= value <= 255:
        raise CodecError("field-inverse")
    result = 1
    base = value
    exponent = 254
    while exponent:
        if exponent & 1:
            result = _gf_mul(result, base)
        base = _gf_mul(base, base)
        exponent >>= 1
    return result


def _derive_rs_generator() -> bytes:
    coefficients = [1]
    for root in range(64):
        factor = _gf_pow(root)
        following = [0] * (len(coefficients) + 1)
        for index, coefficient in enumerate(coefficients):
            following[index] ^= coefficient
            following[index + 1] ^= _gf_mul(coefficient, factor)
        coefficients = following
    return bytes(coefficients)


def rs_generator_coefficients() -> bytes:
    generator = _derive_rs_generator()
    if generator.hex() != _RS_GENERATOR_HEX:
        raise CodecError("rs-generator-invariant")
    return generator


def rs255_191_encode(data: bytes) -> bytes:
    if type(data) is not bytes or len(data) != COMMON_BYTES:
        raise CodecError("rs-data-length")
    dividend = bytearray(data + bytes(64))
    generator = rs_generator_coefficients()
    for offset in range(COMMON_BYTES):
        coefficient = dividend[offset]
        if coefficient:
            for subscript, factor in enumerate(generator):
                dividend[offset + subscript] ^= _gf_mul(coefficient, factor)
    return data + bytes(dividend[COMMON_BYTES:])


def rs255_191_syndromes(codeword: bytes) -> tuple[int, ...]:
    if type(codeword) is not bytes or len(codeword) != RS_UNIT_BYTES:
        raise CodecError("rs-codeword-length")
    result = []
    for root in range(64):
        point = _gf_pow(root)
        value = 0
        for coefficient in codeword:
            value = _gf_mul(value, point) ^ coefficient
        result.append(value)
    return tuple(result)


def rs255_191_is_codeword(codeword: bytes) -> bool:
    return not any(rs255_191_syndromes(codeword))


class _RsResourceLimit(Exception):
    pass


@dataclass(slots=True)
class _RsWork:
    multiplications: int = 0
    inversions: int = 0
    steps: int = 0

    def step(self, count: int = 1) -> None:
        self.steps += count
        if self.steps > 1_000_000:
            raise _RsResourceLimit

    def multiply(self, left: int, right: int) -> int:
        self.multiplications += 1
        self.step(8)
        if self.multiplications > 80_000:
            raise _RsResourceLimit
        return _gf_mul(left, right)

    def inverse(self, value: int) -> int:
        if value == 0:
            raise ZeroDivisionError
        self.inversions += 1
        self.step()
        if self.inversions > 128:
            raise _RsResourceLimit
        result = 1
        base = value
        exponent = 254
        while exponent:
            if exponent & 1:
                result = self.multiply(result, base)
            base = self.multiply(base, base)
            exponent >>= 1
        return result


def _rs_failure(status: int, work: _RsWork) -> RsDecodeResult:
    return RsDecodeResult(
        "corrupt",
        None,
        status,
        field_multiplications=work.multiplications,
        field_inversions=work.inversions,
        primitive_steps=work.steps,
    )


def _rs_syndromes(codeword: Sequence[int], work: _RsWork) -> list[int]:
    result: list[int] = []
    for root in range(64):
        point = alpha_pow(root)
        value = 0
        for coefficient in codeword:
            value = work.multiply(value, point) ^ coefficient
        result.append(value)
    return result


def _poly_multiply(
    left: Sequence[int], right: Sequence[int], work: _RsWork, limit: int
) -> list[int]:
    if len(left) + len(right) - 1 > limit:
        raise _RsResourceLimit
    result = [0] * (len(left) + len(right) - 1)
    for left_index, left_value in enumerate(left):
        for right_index, right_value in enumerate(right):
            result[left_index + right_index] ^= work.multiply(
                left_value, right_value
            )
    return result


def _poly_evaluate(coefficients: Sequence[int], point: int, work: _RsWork) -> int:
    value = 0
    for coefficient in reversed(coefficients):
        value = work.multiply(value, point) ^ coefficient
    return value


def _trim_polynomial(coefficients: list[int]) -> list[int]:
    while len(coefficients) > 1 and coefficients[-1] == 0:
        coefficients.pop()
    return coefficients


def rs255_191_decode(
    observed: bytes,
    erasure_positions: Sequence[int] = (),
    expected_profile_version: int | None = None,
) -> RsDecodeResult:
    """Run the exact bounded syndrome/BM/Forney decoder from bootstrap §17."""

    work = _RsWork()
    if type(observed) is not bytes or len(observed) != RS_UNIT_BYTES:
        return _rs_failure(3, work)
    if expected_profile_version is not None and (
        type(expected_profile_version) is not int
        or expected_profile_version not in (5, 6)
    ):
        return _rs_failure(3, work)
    if isinstance(erasure_positions, (bytes, bytearray, str)) or not isinstance(
        erasure_positions, Sequence
    ):
        return _rs_failure(3, work)
    if len(erasure_positions) > 64:
        return _rs_failure(4, work)
    erasures = tuple(erasure_positions)
    if any(
        type(position) is not int or not 0 <= position <= 254
        for position in erasures
    ) or any(left >= right for left, right in zip(erasures, erasures[1:])):
        return _rs_failure(3, work)
    working = bytearray(observed)
    for position in erasures:
        working[position] = 0
    try:
        syndromes = _rs_syndromes(working, work)
        if not erasures and not any(syndromes):
            decoded = bytes(working[:COMMON_BYTES])
            if expected_profile_version is not None:
                try:
                    bootstrap.decode_common_block(decoded, expected_profile_version)
                except bootstrap.BootstrapReject:
                    return _rs_failure(6, work)
            return RsDecodeResult(
                "verified",
                decoded,
                0,
                field_multiplications=work.multiplications,
                field_inversions=work.inversions,
                primitive_steps=work.steps,
            )

        gamma = [1]
        for position in erasures:
            gamma = _poly_multiply(
                gamma, (1, alpha_pow(254 - position)), work, 65
            )
        erased_count = len(erasures)
        transformed: list[int] = []
        for degree in range(64):
            value = 0
            for index in range(min(degree, erased_count) + 1):
                value ^= work.multiply(gamma[index], syndromes[degree - index])
            transformed.append(value)
        bm_input = transformed[erased_count:]
        if len(bm_input) > 64:
            return _rs_failure(11, work)

        c = [1]
        b_poly = [1]
        locator_degree = 0
        shift = 1
        prior_discrepancy = 1
        for ordinal, syndrome in enumerate(bm_input):
            discrepancy = syndrome
            for index in range(1, locator_degree + 1):
                coefficient = c[index] if index < len(c) else 0
                discrepancy ^= work.multiply(coefficient, bm_input[ordinal - index])
            if discrepancy == 0:
                shift += 1
                continue
            old_c = c.copy()
            quotient = work.multiply(discrepancy, work.inverse(prior_discrepancy))
            required = shift + len(b_poly)
            if len(c) < required:
                c.extend([0] * (required - len(c)))
            for index, coefficient in enumerate(b_poly):
                c[index + shift] ^= work.multiply(quotient, coefficient)
            if 2 * locator_degree <= ordinal:
                locator_degree = ordinal + 1 - locator_degree
                b_poly = old_c
                prior_discrepancy = discrepancy
                shift = 1
            else:
                shift += 1
        c = _trim_polynomial(c)
        if (
            len(c) - 1 != locator_degree
            or len(c) > 33
            or 2 * locator_degree + erased_count > 64
        ):
            return _rs_failure(4, work)
        locator = _trim_polynomial(_poly_multiply(gamma, c, work, 65))
        full_degree = erased_count + locator_degree
        if len(locator) > 65 or len(locator) - 1 != full_degree or full_degree > 64:
            return _rs_failure(4, work)

        roots = tuple(
            position
            for position in range(255)
            if _poly_evaluate(locator, alpha_pow(position + 1), work) == 0
        )
        erasure_set = set(erasures)
        unknown_roots = tuple(position for position in roots if position not in erasure_set)
        if (
            len(roots) != full_degree
            or not erasure_set.issubset(roots)
            or len(unknown_roots) != locator_degree
        ):
            return _rs_failure(5, work)

        evaluator = [0] * 64
        for left_index, left_value in enumerate(syndromes):
            for right_index, right_value in enumerate(locator):
                degree = left_index + right_index
                if degree >= 64:
                    break
                evaluator[degree] ^= work.multiply(left_value, right_value)
        derivative = [0] * max(1, len(locator) - 1)
        for degree in range(1, len(locator), 2):
            derivative[degree - 1] = locator[degree]
        if len(evaluator) > 64 or len(derivative) > 64:
            return _rs_failure(11, work)

        magnitudes: list[int] = []
        for position in roots:
            point = alpha_pow(position + 1)
            denominator = _poly_evaluate(derivative, point, work)
            if denominator == 0:
                return _rs_failure(5, work)
            numerator = work.multiply(
                alpha_pow(254 - position),
                _poly_evaluate(evaluator, point, work),
            )
            magnitude = work.multiply(numerator, work.inverse(denominator))
            if position not in erasure_set and magnitude == 0:
                return _rs_failure(5, work)
            magnitudes.append(magnitude)
        error_count = sum(
            position not in erasure_set and magnitude != 0
            for position, magnitude in zip(roots, magnitudes, strict=True)
        )
        if error_count != locator_degree or 2 * error_count + erased_count > 64:
            return _rs_failure(5, work)
        for position, magnitude in zip(roots, magnitudes, strict=True):
            working[position] ^= magnitude
        if any(_rs_syndromes(working, work)):
            return _rs_failure(5, work)
    except _RsResourceLimit:
        return _rs_failure(11, work)
    except ZeroDivisionError:
        return _rs_failure(5, work)
    decoded = bytes(working[:COMMON_BYTES])
    if expected_profile_version is not None:
        try:
            bootstrap.decode_common_block(decoded, expected_profile_version)
        except bootstrap.BootstrapReject:
            return _rs_failure(6, work)
    return RsDecodeResult(
        "recovered",
        decoded,
        0,
        roots,
        tuple(magnitudes),
        work.multiplications,
        work.inversions,
        work.steps,
    )


def _rs_decode_unit(
    encoded: bytes, erasures: Iterable[int], expected_profile_version: int
) -> Recovery:
    result = rs255_191_decode(  # type: ignore[arg-type]
        encoded, erasures, expected_profile_version
    )
    if result.decoded is None:
        return Recovery("corrupt", None, result.primitive_steps)
    return Recovery(result.state, result.decoded, result.primitive_steps)


def repetition_symbol(
    factor: int, known_mask: Sequence[int], one_mask: Sequence[int]
) -> tuple[bool, int]:
    """Project five lane masks through the compact repetition primitive."""

    if (
        type(factor) is not int
        or factor not in (2, 5)
        or isinstance(known_mask, (bytes, bytearray, str))
        or isinstance(one_mask, (bytes, bytearray, str))
    ):
        raise CodecError("repetition-shape")
    known = tuple(known_mask)
    ones = tuple(one_mask)
    if (
        len(known) != 5
        or len(ones) != 5
        or any(value not in (0, 1) for value in known + ones)
        or any(one and not present for present, one in zip(known, ones, strict=True))
        or any(known[factor:])
        or any(ones[factor:])
    ):
        raise CodecError("repetition-shape")
    known_one_count = sum(
        one
        for present, one in zip(known[:factor], ones[:factor], strict=True)
        if present
    )
    known_count = sum(known[:factor])
    return repetition_symbol_counts(
        factor, known_count - known_one_count, known_one_count
    )


def repetition_symbol_counts(
    factor: int, known_zero_count: int, known_one_count: int
) -> tuple[bool, int]:
    """Execute the compact bootstrap-v1 recipe-113 count relation."""

    if (
        type(factor) is not int
        or type(known_zero_count) is not int
        or type(known_one_count) is not int
        or factor not in (2, 5)
        or known_zero_count < 0
        or known_one_count < 0
        or known_zero_count + known_one_count > factor
    ):
        raise CodecError("repetition-counts")
    erased_count = factor - known_zero_count - known_one_count
    admissible = tuple(
        bit
        for bit in (0, 1)
        if 2 * (known_one_count if bit == 0 else known_zero_count)
        + erased_count
        < factor
    )
    return (True, admissible[0]) if len(admissible) == 1 else (False, 0)


def physical_group_index(
    physical_unit_id: int,
    group_first_physical_unit_id: int,
    factor: int,
) -> int:
    """Execute the exact bounded bootstrap-v1 group-index host adapter."""

    if (
        type(physical_unit_id) is not int
        or type(group_first_physical_unit_id) is not int
        or type(factor) is not int
        or factor not in (1, 2, 5)
        or not 1 <= physical_unit_id <= 0xFFFF_FFFF
        or not 1 <= group_first_physical_unit_id <= 0xFFFF_FFFF
    ):
        raise CodecError("physical-group-index")
    replica_index = physical_unit_id - group_first_physical_unit_id
    if not 0 <= replica_index < factor:
        raise CodecError("physical-group-index")
    return replica_index


def aggregate_replica_group(
    profile: CandidateProfile,
    observations: Sequence[CopyObservation | None],
) -> ReplicaGroupResult:
    """Return the fixed diagnostic projection of one v7 physical group."""

    if not _is_r3_profile(profile):
        raise CodecError("replica-profile")
    return _aggregate_replica_group(profile.profile_version, profile.physical_replica_counts,
                                    observations)


def _aggregate_replica_group(expected_profile_version, physical_replica_counts,
                             observations):
    """Shared composition; public profile admission remains caller-owned."""
    zero = bytes(COMMON_BYTES)
    if isinstance(observations, (bytes, bytearray, str)):
        raise CodecError("replicas-type")
    try:
        lanes = tuple(observations)
    except TypeError as error:
        raise CodecError("replicas-type") from error
    factor = len(lanes)
    if factor not in physical_replica_counts:
        raise CodecError("replica-count")

    valid: list[tuple[Recovery, bool]] = []
    lane_states: list[int] = []
    lane_blocks: list[bytes] = []
    normalized: list[tuple[list[int], set[int]] | None] = []
    constructions = 0
    present = False
    for lane in lanes:
        if lane is None:
            lane_states.append(0)
            lane_blocks.append(zero)
            normalized.append(None)
            continue
        present = True
        if type(lane) is not CopyObservation or len(lane.encoded) != EH_UNIT_BYTES:
            raise CodecError("replica-observation")
        erased = set(
            _erasures(lane.erasures, EH_UNIT_BYTES * 8, EH_UNIT_BYTES * 8)
        )
        bits = _bytes_to_bits(lane.encoded)
        if any(bits[index] for index in erased):
            raise CodecError("replica-erased-value")
        normalized.append((bits, erased))
        try:
            result = _eh72_decode_unit(
                lane.encoded, lane.erasures, expected_profile_version
            )
        except CodecError:
            result = Recovery("corrupt", None, 0)
        constructions += result.constructions
        if result.decoded is None:
            lane_states.append(1)
            lane_blocks.append(zero)
        else:
            lane_states.append(2 if result.state == "verified" else 3)
            lane_blocks.append(result.decoded)
            valid.append((result, True))

    repetition_state = 0
    repetition_block = zero
    if factor > 1 and present:
        repetition_bits: list[int] = []
        repetition_erasures: list[int] = []
        for bit_index in range(EH_UNIT_BYTES * 8):
            known_mask = [0] * 5
            one_mask = [0] * 5
            for replica_index, lane in enumerate(normalized):
                known = lane is not None and bit_index not in lane[1]
                known_mask[replica_index] = int(known)
                one_mask[replica_index] = int(
                    known and lane[0][bit_index] == 1
                )
            known, value = repetition_symbol(factor, known_mask, one_mask)
            repetition_bits.append(value)
            if not known:
                repetition_erasures.append(bit_index)
        try:
            # Construction is unconditional for every present REP2/REP5
            # group.  The product adapter charges the same 24 recipe-30
            # invocations even when this host batch can already prove that
            # the raw vector has too many erasures.
            result = _eh72_decode_unit(
                _bits_to_bytes(repetition_bits),
                repetition_erasures,
                expected_profile_version,
            )
        except CodecError:
            result = Recovery("corrupt", None, 0)
        constructions += result.constructions
        if result.decoded is not None:
            repetition_state = 3
            repetition_block = result.decoded
            valid.append((result, False))
        else:
            repetition_state = 1

    distinct = {item.decoded for item, _ in valid}
    if len(distinct) > 1:
        group_state, chosen = 4, zero
    elif not distinct:
        group_state, chosen = (1, zero) if present else (0, zero)
    else:
        chosen_value = next(iter(distinct))
        assert chosen_value is not None
        verified_lane = any(
            is_lane and item.state == "verified" and item.decoded == chosen_value
            for item, is_lane in valid
        )
        group_state, chosen = (2 if verified_lane else 3), chosen_value
    return ReplicaGroupResult(
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


def recover_replica_group(
    profile: CandidateProfile,
    observations: Sequence[CopyObservation | None],
) -> Recovery:
    """Compatibility projection of :func:`aggregate_replica_group`."""

    result = aggregate_replica_group(profile, observations)
    state = {
        0: "missing",
        1: "corrupt",
        2: "verified",
        3: "recovered",
        4: "ambiguous",
    }[result.group_state]
    return Recovery(
        state,
        result.chosen_block if result.group_state in (2, 3) else None,
        result.constructions,
    )


def recover_profile_copies(
    profile: CandidateProfile,
    observations: Sequence[CopyObservation | None],
) -> Recovery:
    """Recover checked complete copies without voting or partial release."""

    if profile not in _fixed_profiles() and not _is_r3_profile(profile):
        raise CodecError("profile")
    if isinstance(observations, (bytes, bytearray, str)):
        raise CodecError("copies-type")
    try:
        copies = tuple(observations)
    except TypeError as error:
        raise CodecError("copies-type") from error
    if len(copies) != profile.required_copy_count:
        raise CodecError("copy-count")
    valid: list[Recovery] = []
    corrupt_seen = False
    constructions = 0
    for copy in copies:
        if copy is None:
            continue
        if type(copy) is not CopyObservation:
            raise CodecError("copy-observation")
        if profile.transport_id in (EH_TRANSPORT, HIER_TRANSPORT):
            result = _eh72_decode_unit(
                copy.encoded, copy.erasures, profile.profile_version
            )
        else:
            result = _rs_decode_unit(
                copy.encoded, copy.erasures, profile.profile_version
            )
        constructions += result.constructions
        if result.decoded is None:
            corrupt_seen = True
        else:
            valid.append(result)
    if not valid:
        return Recovery("corrupt" if corrupt_seen else "missing", None, constructions)
    distinct = {item.decoded for item in valid}
    if len(distinct) != 1:
        return Recovery("ambiguous", None, constructions)
    state = "verified" if any(item.state == "verified" for item in valid) else "recovered"
    return Recovery(state, next(iter(distinct)), constructions)
