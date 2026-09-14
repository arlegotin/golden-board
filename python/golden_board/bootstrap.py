"""Candidate-neutral M2 bootstrap framing for the frozen v0/v1 grammars."""

from __future__ import annotations

from dataclasses import dataclass
from math import isqrt
from collections.abc import Iterator
from typing import Iterable, Sequence


__all__ = (
    "BootstrapReject",
    "CommonBlock",
    "EntryHypothesis",
    "Inventory",
    "InventoryEntry",
    "RawObservation",
    "Recipe",
    "RecipeNode",
    "RecipePackage",
    "RecipeResult",
    "RecipeTable",
    "RecipeValueDescriptor",
    "SectionEnvelope",
    "SectionWitness",
    "TierFrame",
    "assemble_content_stream",
    "assemble_semantic_copy",
    "assemble_tier_bytes",
    "crc32c_v0",
    "crc64_ecma_v0",
    "decode_common_block",
    "decode_inventory",
    "decode_inventory_entry_v1_header",
    "decode_recipe_package",
    "decode_section_envelope",
    "decode_tier_frame",
    "dependency_closure",
    "encode_common_block",
    "encode_inventory",
    "encode_section_envelope",
    "encode_tier_frame",
    "entry_hypotheses",
    "evaluate_recipe",
    "fragment_section",
    "recover_logical_section",
    "sector_cell",
    "section_envelope_attempt_eligible",
    "validate_envelope_against_inventory",
    "validate_common_against_inventory",
    "validate_inventory_closure",
    "validate_tier_against_inventory",
)


RAW_MAX_BITS = 4_194_304
SIDE_MAX = 2_048
COMMON_BLOCK_BYTES = 191
COMMON_PAYLOAD_BYTES = 157
SECTION_MAX_BYTES = 1_048_576
DEPENDENCY_MAX = 4_095
INVENTORY_ENTRY_MAX = 4_096
TIER_BODY_MAX = 4_094

RECIPE_PACKAGE_MAX = 1_048_576
RECIPE_STEP_MAX = 268_435_456
RECIPE_SCRATCH_MAX = 16_777_216
RECIPE_NODE_MAX = 65_535
RECIPE_EDGE_MAX = 262_140
RECIPE_ITERATION_MAX = 1_048_576

UINT = 0
BOOL = 1
BITS = 2
BYTES = 3
TABLE = 4
STATUS = 5

LOCAL_DOMAIN = bytes.fromhex("d3916ac47208be5f")
SECTION_DOMAIN = bytes.fromhex("4be21977a03c65d8")

RAW_LENGTH = 1
RAW_VALUE = 2
RAW_GEOMETRY = 3
SHELL_GEOMETRY = 4
RESOURCE_LIMIT = 5
BLOCK_FRAMING = 6
FRAGMENT_SHAPE = 7
LOCAL_CHECK = 8
FRAGMENT_CONFLICT = 9
SECTION_INCOMPLETE = 10
SECTION_FRAMING = 11
SECTION_CHECK = 12
INVENTORY = 13
TIER_FRAME = 14
DEPENDENCY = 15
CONTENT_STREAM = 16
AMBIGUOUS = 17
RECIPE = 18
TRAILING_DATA = 19


class BootstrapReject(ValueError):
    """A stable candidate-neutral bootstrap rejection."""

    __slots__ = ("_code", "_path")

    def __init__(self, code: int, path: str = "") -> None:
        if type(code) is not int or not 1 <= code <= 19:
            raise ValueError("invalid bootstrap rejection code")
        if type(path) is not str or not path.isascii() or len(path) > 255:
            raise ValueError("invalid bootstrap rejection path")
        self._code = code
        self._path = path
        super().__init__(code, path)

    @property
    def code(self) -> int:
        return self._code

    @property
    def path(self) -> str:
        return self._path

    def __setattr__(self, name: str, value: object) -> None:
        if name in self.__slots__ and hasattr(self, name):
            raise AttributeError(f"{name} is read-only")
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if name in self.__slots__:
            raise AttributeError(f"{name} is read-only")
        super().__delattr__(name)


def _reject(code: int, path: str) -> None:
    raise BootstrapReject(code, path)


@dataclass(frozen=True, slots=True)
class EntryHypothesis:
    """One transform/polarity pair in the exact candidate-neutral order."""

    transform: int
    polarity: int

    def __post_init__(self) -> None:
        if type(self.transform) is not int or not 0 <= self.transform <= 7:
            _reject(RAW_GEOMETRY, "hypothesis.transform")
        if type(self.polarity) is not int or self.polarity not in (0, 1):
            _reject(RAW_VALUE, "hypothesis.polarity")


class RawObservation:
    """A bounded raw observation with lazy normalized-cell access."""

    __slots__ = ("_bits", "_side")

    def __init__(self, bits: Sequence[int], declared_count: int) -> None:
        if type(declared_count) is not int or not 1 <= declared_count <= RAW_MAX_BITS:
            _reject(RAW_LENGTH, "declared_count")
        try:
            count = len(bits)
        except TypeError:
            _reject(RAW_LENGTH, "bits")
        if count != declared_count:
            _reject(RAW_LENGTH, "bits")
        normalized = bytearray(declared_count)
        for index, value in enumerate(bits):
            if type(value) is not int or value not in (0, 1):
                _reject(RAW_VALUE, f"bits[{index}]")
            normalized[index] = value
        side = isqrt(declared_count)
        if side * side != declared_count or side > SIDE_MAX:
            _reject(RAW_GEOMETRY, "bits")
        self._bits = bytes(normalized)
        self._side = side

    @classmethod
    def parse(cls, bits: Sequence[int], declared_count: int) -> RawObservation:
        return cls(bits, declared_count)

    def __setattr__(self, name: str, value: object) -> None:
        if name in self.__slots__ and hasattr(self, name):
            raise AttributeError(f"{name} is read-only")
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if name in self.__slots__:
            raise AttributeError(f"{name} is read-only")
        object.__delattr__(self, name)

    @property
    def side(self) -> int:
        return self._side

    def normalized_bit(self, hypothesis: EntryHypothesis, row: int, column: int) -> int:
        if not isinstance(hypothesis, EntryHypothesis):
            raise TypeError("hypothesis must be EntryHypothesis")
        if (
            type(row) is not int
            or type(column) is not int
            or not 0 <= row < self._side
            or not 0 <= column < self._side
        ):
            _reject(RAW_GEOMETRY, "normalized_coordinate")
        last = self._side - 1
        coordinates = (
            (row, column),
            (last - column, row),
            (last - row, last - column),
            (column, last - row),
            (row, last - column),
            (last - column, last - row),
            (last - row, column),
            (column, row),
        )
        source_row, source_column = coordinates[hypothesis.transform]
        return self._bits[source_row * self._side + source_column] ^ hypothesis.polarity


class _NormalizedBits(Sequence[int]):
    """A constant-size view; it never expands an N-cell hypothesis."""

    __slots__ = ("_hypothesis", "_observation")

    def __init__(
        self, observation: RawObservation, hypothesis: EntryHypothesis
    ) -> None:
        self._observation = observation
        self._hypothesis = hypothesis

    def __len__(self) -> int:
        return self._observation.side * self._observation.side

    def __getitem__(self, index: int | slice) -> int | tuple[int, ...]:
        if isinstance(index, slice):
            return tuple(
                self[subindex] for subindex in range(*index.indices(len(self)))
            )
        if type(index) is not int:
            raise TypeError("normalized index must be an integer or slice")
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError("normalized index out of range")
        return self._observation.normalized_bit(
            self._hypothesis,
            index // self._observation.side,
            index % self._observation.side,
        )

    def __iter__(self) -> Iterator[int]:
        for index in range(len(self)):
            value = self[index]
            assert type(value) is int
            yield value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Sequence):
            return False
        return len(self) == len(other) and all(
            left == right for left, right in zip(self, other, strict=True)
        )


def _u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 2], "big")


def _u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], "big")


def _be16(value: int, path: str) -> bytes:
    if type(value) is not int or not 0 <= value <= 0xFFFF:
        _reject(RESOURCE_LIMIT, path)
    return value.to_bytes(2, "big")


def _be32(value: int, path: str) -> bytes:
    if type(value) is not int or not 0 <= value <= 0xFFFF_FFFF:
        _reject(RESOURCE_LIMIT, path)
    return value.to_bytes(4, "big")


def _strict_ids(values: Sequence[int], maximum: int, code: int, path: str) -> None:
    if len(values) > maximum:
        _reject(RESOURCE_LIMIT, path)
    previous = 0
    for index, value in enumerate(values):
        if type(value) is not int or not 1 <= value <= 0xFFFF_FFFF:
            _reject(code, f"{path}[{index}]")
        if value <= previous:
            _reject(code, f"{path}[{index}]")
        previous = value


def crc32c_v0(data: bytes) -> int:
    if type(data) is not bytes:
        raise TypeError("crc32c_v0 requires bytes")
    register = 0xFFFF_FFFF
    for byte in data:
        register ^= byte
        for _ in range(8):
            register = (register >> 1) ^ 0x82F63B78 if register & 1 else register >> 1
    return register ^ 0xFFFF_FFFF


def crc64_ecma_v0(data: bytes) -> int:
    if type(data) is not bytes:
        raise TypeError("crc64_ecma_v0 requires bytes")
    register = 0
    for byte in data:
        register ^= byte << 56
        for _ in range(8):
            register = (
                ((register << 1) ^ 0x42F0E1EBA9EA3693) & 0xFFFF_FFFF_FFFF_FFFF
                if register & (1 << 63)
                else (register << 1) & 0xFFFF_FFFF_FFFF_FFFF
            )
    return register


def _check(check_id: int, preimage: bytes, path: str) -> bytes:
    if check_id == 1:
        return crc32c_v0(preimage).to_bytes(4, "big")
    if check_id == 2:
        return crc64_ecma_v0(preimage).to_bytes(8, "big")
    _reject(SECTION_FRAMING, path)


def entry_hypotheses(
    bits: Sequence[int], declared_count: int
) -> tuple[Sequence[int], ...]:
    """Return sixteen lazy normalized views in exact transform/polarity order."""

    observation = RawObservation(bits, declared_count)
    return tuple(
        _NormalizedBits(observation, EntryHypothesis(transform, polarity))
        for transform in range(8)
        for polarity in range(2)
    )


def sector_cell(side: int, width: int, sector: int, offset: int) -> tuple[int, int]:
    if (
        type(side) is not int
        or type(width) is not int
        or type(sector) is not int
        or type(offset) is not int
        or side > SIDE_MAX
        or width % 8 != 0
        or not 8 <= width <= min(128, (side - 8) // 2)
        or not 0 <= sector < 4
        or not 0 <= offset < width * (side - width)
    ):
        _reject(SHELL_GEOMETRY, "sector")
    u, v = divmod(offset, side - width)
    last = side - 1
    return (
        (u, v),
        (v, last - u),
        (last - u, last - v),
        (last - v, u),
    )[sector]


@dataclass(frozen=True, slots=True)
class CommonBlock:
    profile_version: int
    section_id: int
    semantic_copy_id: int
    section_type: int
    section_version: int
    fragment_index: int
    fragment_count: int
    section_envelope_length: int
    payload: bytes


def fragment_section(
    envelope: bytes, profile_version: int, semantic_copy_id: int
) -> tuple[bytes, ...]:
    """Frame one already checked semantic envelope into common plain blocks."""

    section = decode_section_envelope(envelope)
    if type(semantic_copy_id) is not int or not 0 <= semantic_copy_id <= 0xFFFF:
        _reject(FRAGMENT_SHAPE, "semantic_copy_id")
    count = (len(envelope) + 156) // 157
    return tuple(
        encode_common_block(
            CommonBlock(
                profile_version,
                section.section_id,
                semantic_copy_id,
                section.section_type,
                section.section_version,
                index,
                count,
                len(envelope),
                envelope[index * 157 : min((index + 1) * 157, len(envelope))],
            )
        )
        for index in range(count)
    )


def assemble_semantic_copy(
    encoded_blocks: Iterable[bytes], expected_profile_version: int
) -> tuple[int, bytes]:
    """Deduplicate and assemble exactly one semantic-copy witness."""

    groups: dict[tuple[int, ...], bytes] = {}
    common_identity: tuple[int, ...] | None = None
    for ordinal, encoded in enumerate(encoded_blocks):
        if ordinal >= 65_535:
            _reject(RESOURCE_LIMIT, "blocks")
        block = decode_common_block(encoded, expected_profile_version)
        identity = (
            block.profile_version,
            block.section_id,
            block.semantic_copy_id,
            block.section_type,
            block.section_version,
            block.fragment_count,
            block.section_envelope_length,
        )
        if common_identity is None:
            common_identity = identity
        elif identity != common_identity:
            _reject(FRAGMENT_CONFLICT, f"blocks[{ordinal}].identity")
        old = groups.get((block.fragment_index,))
        if old is not None and old != encoded:
            _reject(FRAGMENT_CONFLICT, f"blocks[{ordinal}]")
        groups[(block.fragment_index,)] = encoded
    if common_identity is None:
        _reject(SECTION_INCOMPLETE, "blocks")
    fragment_count = common_identity[5]
    if set(index[0] for index in groups) != set(range(fragment_count)):
        _reject(SECTION_INCOMPLETE, "blocks")
    decoded = [
        decode_common_block(groups[(index,)], expected_profile_version)
        for index in range(fragment_count)
    ]
    envelope = b"".join(block.payload for block in decoded)
    if len(envelope) != common_identity[6]:
        _reject(SECTION_FRAMING, "section_envelope_length")
    section = decode_section_envelope(envelope)
    if (
        section.section_id != common_identity[1]
        or section.section_type != common_identity[3]
        or section.section_version != common_identity[4]
    ):
        _reject(SECTION_FRAMING, "fragment_envelope_agreement")
    return common_identity[2], envelope


@dataclass(frozen=True, slots=True)
class SectionWitness:
    envelope: bytes
    all_units_verified: bool


def recover_logical_section(witnesses: Iterable[SectionWitness]) -> tuple[str, bytes]:
    """Aggregate complete valid physical witnesses without voting."""

    unique: dict[bytes, bool] = {}
    section_identity: tuple[int, int, int] | None = None
    for ordinal, witness in enumerate(witnesses):
        if ordinal >= 4_096:
            _reject(RESOURCE_LIMIT, "witnesses")
        if (
            not isinstance(witness, SectionWitness)
            or type(witness.all_units_verified) is not bool
        ):
            _reject(SECTION_FRAMING, f"witnesses[{ordinal}]")
        section = decode_section_envelope(witness.envelope)
        identity = (section.section_id, section.section_type, section.section_version)
        if section_identity is None:
            section_identity = identity
        elif identity != section_identity:
            _reject(AMBIGUOUS, "witnesses.identity")
        unique[witness.envelope] = (
            unique.get(witness.envelope, False) or witness.all_units_verified
        )
    if not unique:
        _reject(SECTION_INCOMPLETE, "witnesses")
    if len(unique) != 1:
        _reject(AMBIGUOUS, "witnesses")
    envelope, has_verified = next(iter(unique.items()))
    return ("verified" if has_verified else "recovered"), envelope


def encode_common_block(block: CommonBlock) -> bytes:
    if not isinstance(block, CommonBlock):
        raise TypeError("encode_common_block requires CommonBlock")
    payload = block.payload
    if type(payload) is not bytes or not 1 <= len(payload) <= COMMON_PAYLOAD_BYTES:
        _reject(FRAGMENT_SHAPE, "payload")
    expected_count = (block.section_envelope_length + 156) // 157
    expected_final = block.section_envelope_length - 157 * (expected_count - 1)
    if (
        not 1 <= block.profile_version <= 0xFFFF
        or not 1 <= block.section_id <= 0xFFFF_FFFF
        or not 0 <= block.semantic_copy_id <= 0xFFFF
        or block.section_type not in range(1, 7)
        or not 0 <= block.section_version <= 0xFFFF
        or not 1 <= block.fragment_count <= 0xFFFF
        or not 0 <= block.fragment_index < block.fragment_count
        or not 1 <= block.section_envelope_length <= SECTION_MAX_BYTES
        or block.fragment_count != expected_count
        or len(payload)
        != (expected_final if block.fragment_index + 1 == expected_count else 157)
    ):
        _reject(FRAGMENT_SHAPE, "block")
    prefix = b"".join(
        (
            _be16(block.profile_version, "profile_version"),
            b"\0\0",
            _be32(block.section_id, "section_id"),
            _be16(block.semantic_copy_id, "semantic_copy_id"),
            _be16(block.section_type, "section_type"),
            _be16(block.section_version, "section_version"),
            b"\0\0",
            _be16(block.fragment_index, "fragment_index"),
            _be16(block.fragment_count, "fragment_count"),
            _be16(len(payload), "valid_payload_length"),
            _be32(block.section_envelope_length, "section_envelope_length"),
            b"\0\0\0\0",
            payload,
            bytes(COMMON_PAYLOAD_BYTES - len(payload)),
        )
    )
    assert len(prefix) == 187
    return prefix + crc32c_v0(LOCAL_DOMAIN + prefix).to_bytes(4, "big")


def decode_common_block(data: bytes, expected_profile_version: int) -> CommonBlock:
    if type(data) is not bytes or len(data) != COMMON_BLOCK_BYTES:
        _reject(BLOCK_FRAMING, "block")
    profile_version = _u16(data, 0)
    section_id = _u32(data, 4)
    section_type = _u16(data, 10)
    if (
        type(expected_profile_version) is not int
        or not 1 <= expected_profile_version <= 0xFFFF
        or profile_version != expected_profile_version
        or data[2:4] != b"\0\0"
        or section_id == 0
        or section_type not in range(1, 7)
        or data[14:16] != b"\0\0"
        or data[26:30] != b"\0\0\0\0"
    ):
        _reject(BLOCK_FRAMING, "block.header")
    index = _u16(data, 16)
    count = _u16(data, 18)
    valid = _u16(data, 20)
    envelope_length = _u32(data, 22)
    expected_count = (envelope_length + 156) // 157 if envelope_length else 0
    expected_final = (
        envelope_length - 157 * (expected_count - 1) if expected_count else 0
    )
    if (
        count == 0
        or index >= count
        or not 1 <= valid <= 157
        or not 1 <= envelope_length <= SECTION_MAX_BYTES
        or count != expected_count
        or valid != (expected_final if index + 1 == count else 157)
        or any(data[30 + valid : 187])
    ):
        _reject(FRAGMENT_SHAPE, "block.fragment")
    if data[187:] != crc32c_v0(LOCAL_DOMAIN + data[:187]).to_bytes(4, "big"):
        _reject(LOCAL_CHECK, "block.local_crc32c")
    return CommonBlock(
        profile_version,
        section_id,
        _u16(data, 8),
        section_type,
        _u16(data, 12),
        index,
        count,
        envelope_length,
        data[30 : 30 + valid],
    )


@dataclass(frozen=True, slots=True)
class SectionEnvelope:
    section_id: int
    section_type: int
    section_version: int
    closure_class: int
    check_id: int
    dependencies: tuple[int, ...]
    payload: bytes


def encode_section_envelope(section: SectionEnvelope) -> bytes:
    if not isinstance(section, SectionEnvelope):
        raise TypeError("encode_section_envelope requires SectionEnvelope")
    if (
        not 1 <= section.section_id <= 0xFFFF_FFFF
        or section.section_type not in range(1, 7)
        or not 0 <= section.section_version <= 0xFFFF
        or section.closure_class not in (128, 129)
        or section.check_id not in (1, 2)
        or type(section.payload) is not bytes
        or len(section.payload) > SECTION_MAX_BYTES
    ):
        _reject(SECTION_FRAMING, "section")
    _strict_ids(section.dependencies, DEPENDENCY_MAX, SECTION_FRAMING, "dependencies")
    if section.section_id in section.dependencies:
        _reject(SECTION_FRAMING, "dependencies")
    prefix = b"".join(
        (
            b"\0\0",
            _be32(section.section_id, "section_id"),
            _be16(section.section_type, "section_type"),
            _be16(section.section_version, "section_version"),
            bytes((section.closure_class, section.check_id)),
            _be16(len(section.dependencies), "dependency_count"),
            _be32(len(section.payload), "payload_length"),
            b"".join(_be32(value, "dependency") for value in section.dependencies),
            section.payload,
        )
    )
    result = prefix + _check(section.check_id, SECTION_DOMAIN + prefix, "check_id")
    if len(result) > SECTION_MAX_BYTES:
        _reject(RESOURCE_LIMIT, "section")
    return result


def decode_section_envelope(data: bytes) -> SectionEnvelope:
    if type(data) is not bytes or not 22 <= len(data) <= SECTION_MAX_BYTES:
        _reject(SECTION_FRAMING, "section")
    section_id = _u32(data, 2)
    section_type = _u16(data, 6)
    closure = data[10]
    check_id = data[11]
    if (
        data[:2] != b"\0\0"
        or section_id == 0
        or section_type not in range(1, 7)
        or closure not in (128, 129)
        or check_id not in (1, 2)
    ):
        _reject(SECTION_FRAMING, "section.header")
    count = _u16(data, 12)
    if count > DEPENDENCY_MAX:
        _reject(RESOURCE_LIMIT, "section.dependencies")
    payload_length = _u32(data, 14)
    dependencies_end = 18 + 4 * count
    if dependencies_end > len(data):
        _reject(SECTION_FRAMING, "section.dependencies")
    dependencies = tuple(_u32(data, 18 + 4 * index) for index in range(count))
    _strict_ids(dependencies, DEPENDENCY_MAX, SECTION_FRAMING, "dependencies")
    if section_id in dependencies:
        _reject(SECTION_FRAMING, "dependencies")
    check_length = 4 if check_id == 1 else 8
    expected = dependencies_end + payload_length + check_length
    if expected != len(data):
        _reject(
            TRAILING_DATA if expected < len(data) else SECTION_FRAMING, "section.length"
        )
    if data[-check_length:] != _check(
        check_id, SECTION_DOMAIN + data[:-check_length], "check_id"
    ):
        _reject(SECTION_CHECK, "section.check")
    return SectionEnvelope(
        section_id,
        section_type,
        _u16(data, 8),
        closure,
        check_id,
        dependencies,
        data[dependencies_end:-check_length],
    )


def section_envelope_attempt_eligible(data: bytes) -> bool:
    """Return whether ``data`` reaches the stored section-check comparison."""

    if type(data) is not bytes or not 22 <= len(data) <= SECTION_MAX_BYTES:
        return False
    section_id = _u32(data, 2)
    section_type = _u16(data, 6)
    closure = data[10]
    check_id = data[11]
    if (
        data[:2] != b"\0\0"
        or section_id == 0
        or section_type not in range(1, 7)
        or closure not in (128, 129)
        or check_id not in (1, 2)
    ):
        return False
    count = _u16(data, 12)
    if count > DEPENDENCY_MAX:
        return False
    dependencies_end = 18 + 4 * count
    if dependencies_end > len(data):
        return False
    dependencies = tuple(_u32(data, 18 + 4 * index) for index in range(count))
    if (
        any(not 1 <= value <= 0xFFFF_FFFF for value in dependencies)
        or any(
            left >= right
            for left, right in zip(dependencies, dependencies[1:])
        )
        or section_id in dependencies
    ):
        return False
    check_length = 4 if check_id == 1 else 8
    return dependencies_end + _u32(data, 14) + check_length == len(data)


@dataclass(frozen=True, slots=True)
class InventoryEntry:
    section_id: int
    section_type: int
    section_version: int
    closure_class: int
    check_id: int
    copy_count: int
    dependencies: tuple[int, ...]
    logical_payload_length: int
    game_ordinal: int | None = None
    physical_replica_count: int = 1


@dataclass(frozen=True, slots=True)
class Inventory:
    entries: tuple[InventoryEntry, ...]
    version: int = 0


def encode_inventory(inventory: Inventory) -> bytes:
    if (
        not isinstance(inventory, Inventory)
        or inventory.version not in (0, 1)
        or not 3 <= len(inventory.entries) <= INVENTORY_ENTRY_MAX
    ):
        _reject(INVENTORY, "inventory")
    output = bytearray(
        _be16(inventory.version, "inventory_version")
        + _be16(len(inventory.entries), "entry_count")
        + b"\0\0\0@"
    )
    previous = 0
    ordinals: list[int] = []
    ids = {entry.section_id for entry in inventory.entries}
    for index, entry in enumerate(inventory.entries):
        if not isinstance(entry, InventoryEntry) or entry.section_id <= previous:
            _reject(INVENTORY, f"entries[{index}]")
        previous = entry.section_id
        _strict_ids(
            entry.dependencies,
            DEPENDENCY_MAX,
            INVENTORY,
            f"entries[{index}].dependencies",
        )
        if (
            entry.section_type not in range(1, 7)
            or not 0 <= entry.section_version <= 0xFFFF
            or entry.closure_class not in (128, 129)
            or entry.check_id not in (1, 2)
            or (
                entry.copy_count != 1
                if inventory.version == 1
                else entry.copy_count not in (1, 2, 3)
            )
            or (
                entry.physical_replica_count not in (1, 2, 5)
                if inventory.version == 1
                else entry.physical_replica_count != 1
            )
            or not 0 <= entry.logical_payload_length <= 0xFFFF_FFFF
            or (entry.section_type in (1, 2, 3) and entry.logical_payload_length == 0)
            or entry.section_id in entry.dependencies
            or any(value not in ids for value in entry.dependencies)
        ):
            _reject(INVENTORY, f"entries[{index}]")
        if entry.game_ordinal is None:
            flags, ordinal = 0, 0xFFFF
        elif (
            type(entry.game_ordinal) is int
            and 0 <= entry.game_ordinal < 64
            and entry.section_type == 3
        ):
            flags, ordinal = 1, entry.game_ordinal
            ordinals.append(ordinal)
        else:
            _reject(INVENTORY, f"entries[{index}].game_ordinal")
        if inventory.version == 1:
            flags |= entry.physical_replica_count << 1
        fixed_header = b"".join(
            (
                _be32(entry.section_id, "section_id"),
                _be16(entry.section_type, "section_type"),
                _be16(entry.section_version, "section_version"),
                bytes(
                    (entry.closure_class, entry.check_id, entry.copy_count, flags)
                ),
                _be16(len(entry.dependencies), "dependency_count"),
                _be32(entry.logical_payload_length, "logical_payload_length"),
                _be16(ordinal, "game_ordinal"),
            )
        )
        if inventory.version == 1:
            decode_inventory_entry_v1_header(fixed_header)
        output.extend(fixed_header)
        output.extend(
            b"".join(_be32(value, "dependency") for value in entry.dependencies)
        )
    if sorted(ordinals) != list(range(64)):
        _reject(INVENTORY, "game_ordinals")
    _validate_inventory_fixed_entries(inventory.entries, inventory.version)
    validate_inventory_closure(inventory)
    encoded = bytes(output)
    if inventory.entries[0].logical_payload_length != len(encoded):
        _reject(INVENTORY, "fixed_entries[0].logical_payload_length")
    return encoded


def _validate_inventory_fixed_entries(
    entries: Sequence[InventoryEntry], inventory_version: int = 0
) -> None:
    by_id = {entry.section_id: entry for entry in entries}
    if set((1, 2, 3)) - by_id.keys():
        _reject(INVENTORY, "fixed_entries")
    first, required, all_frame = by_id[1], by_id[2], by_id[3]
    common = (
        first.section_type == 1
        and first.closure_class == 128
        and not first.dependencies
        and required.section_type == all_frame.section_type == 2
        and required.section_version == all_frame.section_version == 0
        and required.closure_class == all_frame.closure_class == 128
    )
    if inventory_version == 0:
        valid = (
            common
            and first.section_version == 0
            and first.copy_count == 2
            and required.copy_count >= 2
            and all_frame.copy_count >= 2
            and all(entry.physical_replica_count == 1 for entry in entries)
        )
    elif inventory_version == 1:
        valid = (
            common
            and first.section_version == 1
            and all(entry.copy_count == 1 for entry in entries)
            and all(entry.physical_replica_count in (1, 2, 5) for entry in entries)
            and all(
                by_id[section_id].physical_replica_count == 5
                for section_id in (1, 2, 3, 16)
                if section_id in by_id
            )
            and 16 in by_id
            and {
                entry.section_id
                for entry in entries
                if entry.physical_replica_count == 5
            }
            == {1, 2, 3, 16}
            and {
                entry.section_id
                for entry in entries
                if entry.closure_class == 128
            }
            == {1, 2, 3, 16}
            and by_id[16].section_type == 3
        )
    else:
        valid = False
    if not valid:
        _reject(INVENTORY, "fixed_entries")


def decode_inventory_entry_v1_header(data: bytes) -> tuple[int, bool]:
    """Execute the exact bootstrap-v1 recipe-116 fixed-header projection."""

    if type(data) is not bytes or len(data) != 20:
        _reject(INVENTORY, "inventory_entry_v1.header")
    section_id = _u32(data, 0)
    section_type = _u16(data, 4)
    section_version = _u16(data, 6)
    closure_class, check_id, copy_count, flags = data[8:12]
    dependency_count = _u16(data, 12)
    logical_payload_length = _u32(data, 14)
    ordinal_raw = _u16(data, 18)
    factor = flags >> 1
    has_ordinal = bool(flags & 1)
    spine = section_id in (1, 2, 3, 16)
    if (
        not 1 <= section_id <= 0xFFFF_FFFF
        or section_type not in range(1, 7)
        or closure_class not in (128, 129)
        or check_id != 1
        or copy_count != 1
        or flags & 0xF0
        or factor not in (1, 2, 5)
        or dependency_count > DEPENDENCY_MAX
        or not 0 <= logical_payload_length <= 0xFFFF_FFFF
        or (section_type in (1, 2, 3) and logical_payload_length == 0)
        or (factor == 5) != spine
        or (closure_class == 128) != spine
        or (has_ordinal and (ordinal_raw >= 64 or section_type != 3))
        or (not has_ordinal and ordinal_raw != 0xFFFF)
        or (
            section_id == 1
            and (
                section_type != 1
                or section_version != 1
                or dependency_count != 0
                or has_ordinal
            )
        )
        or (
            section_id in (2, 3)
            and (section_type != 2 or section_version != 0 or has_ordinal)
        )
        or (
            section_id == 16
            and (section_type != 3 or section_version != 0 or has_ordinal)
        )
    ):
        _reject(INVENTORY, "inventory_entry_v1")
    return factor, has_ordinal


def decode_inventory(data: bytes) -> Inventory:
    if (
        type(data) is not bytes
        or len(data) < 8
        or data[4:8] != b"\0\0\0@"
    ):
        _reject(INVENTORY, "inventory.header")
    inventory_version = _u16(data, 0)
    if inventory_version not in (0, 1):
        _reject(INVENTORY, "inventory.version")
    count = _u16(data, 2)
    if not 3 <= count <= INVENTORY_ENTRY_MAX:
        _reject(INVENTORY, "inventory.entry_count")
    offset = 8
    entries: list[InventoryEntry] = []
    previous = 0
    ordinals: list[int] = []
    for index in range(count):
        if offset + 20 > len(data):
            _reject(INVENTORY, f"entries[{index}]")
        section_id = _u32(data, offset)
        section_type = _u16(data, offset + 4)
        version = _u16(data, offset + 6)
        closure, check_id, copies, flags = data[offset + 8 : offset + 12]
        dependency_count = _u16(data, offset + 12)
        payload_length = _u32(data, offset + 14)
        ordinal_raw = _u16(data, offset + 18)
        projected_v1 = (
            decode_inventory_entry_v1_header(data[offset : offset + 20])
            if inventory_version == 1
            else None
        )
        if dependency_count > DEPENDENCY_MAX:
            _reject(RESOURCE_LIMIT, f"entries[{index}].dependencies")
        end = offset + 20 + 4 * dependency_count
        if end > len(data):
            _reject(INVENTORY, f"entries[{index}].dependencies")
        dependencies = tuple(
            _u32(data, offset + 20 + 4 * sub) for sub in range(dependency_count)
        )
        _strict_ids(
            dependencies, DEPENDENCY_MAX, INVENTORY, f"entries[{index}].dependencies"
        )
        if (
            section_id <= previous
            or section_type not in range(1, 7)
            or closure not in (128, 129)
            or check_id not in (1, 2)
            or (
                copies != 1
                if inventory_version == 1
                else copies not in (1, 2, 3)
            )
            or (
                flags & ~0x0F
                if inventory_version == 1
                else flags & ~1
            )
            or section_id in dependencies
        ):
            _reject(INVENTORY, f"entries[{index}]")
        physical_replica_count = flags >> 1 if inventory_version == 1 else 1
        if inventory_version == 1 and physical_replica_count not in (1, 2, 5):
            _reject(INVENTORY, f"entries[{index}].physical_replica_count")
        if projected_v1 is not None and projected_v1 != (
            physical_replica_count,
            bool(flags & 1),
        ):
            _reject(INVENTORY, f"entries[{index}]")
        previous = section_id
        if flags & 1:
            if ordinal_raw >= 64 or section_type != 3:
                _reject(INVENTORY, f"entries[{index}].game_ordinal")
            game_ordinal: int | None = ordinal_raw
            ordinals.append(ordinal_raw)
        else:
            if ordinal_raw != 0xFFFF:
                _reject(INVENTORY, f"entries[{index}].game_ordinal")
            game_ordinal = None
        entries.append(
            InventoryEntry(
                section_id,
                section_type,
                version,
                closure,
                check_id,
                copies,
                dependencies,
                payload_length,
                game_ordinal,
                physical_replica_count,
            )
        )
        offset = end
    if offset != len(data):
        _reject(TRAILING_DATA, "inventory")
    ids = {entry.section_id for entry in entries}
    if any(
        dependency not in ids for entry in entries for dependency in entry.dependencies
    ):
        _reject(INVENTORY, "dependencies")
    if sorted(ordinals) != list(range(64)):
        _reject(INVENTORY, "game_ordinals")
    _validate_inventory_fixed_entries(entries, inventory_version)
    if any(
        entry.section_type in (1, 2, 3) and entry.logical_payload_length == 0
        for entry in entries
    ):
        _reject(INVENTORY, "logical_payload_length")
    if entries[0].logical_payload_length != len(data):
        _reject(INVENTORY, "fixed_entries[0].logical_payload_length")
    inventory = Inventory(tuple(entries), inventory_version)
    validate_inventory_closure(inventory)
    return inventory


def validate_inventory_closure(inventory: Inventory) -> None:
    """Reject absent dependency IDs and cycles in canonical traversal order."""

    if not isinstance(inventory, Inventory):
        raise TypeError("validate_inventory_closure requires Inventory")
    by_id = {entry.section_id: entry for entry in inventory.entries}
    if len(by_id) != len(inventory.entries):
        _reject(INVENTORY, "entries")
    if any(
        dependency not in by_id
        for entry in inventory.entries
        for dependency in entry.dependencies
    ):
        _reject(INVENTORY, "dependencies")
    colors: dict[int, int] = {section_id: 0 for section_id in by_id}
    for root in sorted(by_id):
        if colors[root] != 0:
            continue
        colors[root] = 1
        stack: list[tuple[int, int]] = [(root, 0)]
        while stack:
            section_id, dependency_index = stack[-1]
            dependencies = by_id[section_id].dependencies
            if dependency_index == len(dependencies):
                colors[section_id] = 2
                stack.pop()
                continue
            dependency = dependencies[dependency_index]
            stack[-1] = (section_id, dependency_index + 1)
            if colors[dependency] == 1:
                _reject(DEPENDENCY, f"dependencies[{dependency}]")
            if colors[dependency] == 0:
                colors[dependency] = 1
                stack.append((dependency, 0))


def dependency_closure(
    inventory: Inventory, roots: Sequence[int], available: set[int]
) -> tuple[int, ...]:
    """Return the exact requested transitive closure or reject incompleteness."""

    validate_inventory_closure(inventory)
    if type(available) is not set or any(type(value) is not int for value in available):
        raise TypeError("available must be a set of integer section IDs")
    _strict_ids(roots, DEPENDENCY_MAX, DEPENDENCY, "roots")
    by_id = {entry.section_id: entry for entry in inventory.entries}
    closure: set[int] = set()
    stack = list(reversed(roots))
    while stack:
        section_id = stack.pop()
        entry = by_id.get(section_id)
        if entry is None or section_id not in available:
            _reject(DEPENDENCY, f"sections[{section_id}]")
        if section_id not in closure:
            closure.add(section_id)
            stack.extend(reversed(entry.dependencies))
    return tuple(sorted(closure))


def validate_envelope_against_inventory(
    section: SectionEnvelope, inventory: Inventory
) -> None:
    if not isinstance(section, SectionEnvelope) or not isinstance(inventory, Inventory):
        raise TypeError("invalid section/inventory")
    by_id = {entry.section_id: entry for entry in inventory.entries}
    entry = by_id.get(section.section_id)
    if entry is None or (
        entry.section_type != section.section_type
        or entry.section_version != section.section_version
        or entry.closure_class != section.closure_class
        or entry.check_id != section.check_id
        or entry.dependencies != section.dependencies
        or entry.logical_payload_length != len(section.payload)
    ):
        _reject(INVENTORY, f"sections[{section.section_id}]")


def validate_common_against_inventory(block: CommonBlock, inventory: Inventory) -> None:
    """Reject a physical block that exceeds its inventoried semantic-copy set."""

    if not isinstance(block, CommonBlock) or not isinstance(inventory, Inventory):
        raise TypeError("invalid common block/inventory")
    encode_common_block(block)
    # Re-encoding performs the same closed inventory validation used by the wire
    # path without trusting a host-constructed Inventory value.
    encode_inventory(inventory)
    by_id = {entry.section_id: entry for entry in inventory.entries}
    entry = by_id.get(block.section_id)
    if entry is None or (
        block.section_type != entry.section_type
        or block.section_version != entry.section_version
        or block.semantic_copy_id >= entry.copy_count
    ):
        _reject(INVENTORY, f"blocks[{block.section_id}]")


@dataclass(frozen=True, slots=True)
class TierFrame:
    tier_id: int
    body_section_ids: tuple[int, ...]
    assembled_stream_byte_length: int
    assembled_record_count: int
    root_record_bytes: bytes


def _root_record_id(raw: bytes) -> int:
    if (
        type(raw) is not bytes
        or len(raw) != 12
        or _u16(raw, 0) == 0
        or _u16(raw, 2) != 14
        or _u32(raw, 4) != 4
    ):
        _reject(TIER_FRAME, "root_record_bytes")
    return _u16(raw, 0)


def _body_record_ids(raw: bytes, path: str) -> tuple[int, ...]:
    if type(raw) is not bytes or not raw:
        _reject(TIER_FRAME, path)
    if len(raw) > SECTION_MAX_BYTES:
        _reject(RESOURCE_LIMIT, path)
    offset = 0
    ids: list[int] = []
    while offset < len(raw):
        if len(raw) - offset < 8:
            _reject(TIER_FRAME, path)
        record_id = _u16(raw, offset)
        kind = _u16(raw, offset + 2)
        payload_length = _u32(raw, offset + 4)
        if record_id == 0 or not 1 <= kind <= 13:
            _reject(TIER_FRAME, path)
        end = offset + 8 + payload_length
        if end > len(raw):
            _reject(TIER_FRAME, path)
        if ids and record_id <= ids[-1]:
            _reject(TIER_FRAME, path)
        ids.append(record_id)
        offset = end
    return tuple(ids)


def encode_tier_frame(frame: TierFrame) -> bytes:
    if not isinstance(frame, TierFrame):
        raise TypeError("encode_tier_frame requires TierFrame")
    if (
        frame.tier_id not in (0, 1)
        or not 1 <= len(frame.body_section_ids) <= TIER_BODY_MAX
    ):
        _reject(TIER_FRAME, "tier")
    _strict_ids(frame.body_section_ids, TIER_BODY_MAX, TIER_FRAME, "body_section_ids")
    if (
        not 1 <= frame.assembled_stream_byte_length <= SECTION_MAX_BYTES
        or not 1 <= frame.assembled_record_count <= 0xFFFF
        or type(frame.root_record_bytes) is not bytes
        or not frame.root_record_bytes
    ):
        _reject(TIER_FRAME, "tier")
    _root_record_id(frame.root_record_bytes)
    header = b"\0\0" + _be16(frame.assembled_record_count, "record_count")
    encoded = b"".join(
        (
            b"\0\0",
            bytes((frame.tier_id, 0)),
            _be16(len(frame.body_section_ids), "body_count"),
            b"\0\0",
            _be32(frame.assembled_stream_byte_length, "stream_length"),
            _be16(frame.assembled_record_count, "record_count"),
            _be32(len(frame.root_record_bytes), "root_length"),
            header,
            b"".join(
                _be32(value, "body_section_id") for value in frame.body_section_ids
            ),
            frame.root_record_bytes,
        )
    )
    if len(encoded) > SECTION_MAX_BYTES:
        _reject(RESOURCE_LIMIT, "tier")
    return encoded


def decode_tier_frame(data: bytes, expected_section_id: int) -> TierFrame:
    if type(data) is not bytes or len(data) < 27 or expected_section_id not in (2, 3):
        _reject(TIER_FRAME, "tier")
    tier_id = data[2]
    body_count = _u16(data, 4)
    stream_length = _u32(data, 8)
    record_count = _u16(data, 12)
    root_length = _u32(data, 14)
    if (
        data[:2] != b"\0\0"
        or tier_id != expected_section_id - 2
        or data[3] != 0
        or data[6:8] != b"\0\0"
        or not 1 <= body_count <= TIER_BODY_MAX
        or stream_length == 0
        or record_count == 0
        or root_length == 0
        or data[18:22] != b"\0\0" + _be16(record_count, "record_count")
    ):
        _reject(TIER_FRAME, "tier.header")
    if stream_length > SECTION_MAX_BYTES:
        _reject(RESOURCE_LIMIT, "tier.assembled_stream_byte_length")
    root_offset = 22 + 4 * body_count
    if root_offset + root_length != len(data):
        _reject(
            TRAILING_DATA if root_offset + root_length < len(data) else TIER_FRAME,
            "tier.length",
        )
    ids = tuple(_u32(data, 22 + 4 * index) for index in range(body_count))
    _strict_ids(ids, TIER_BODY_MAX, TIER_FRAME, "body_section_ids")
    frame = TierFrame(tier_id, ids, stream_length, record_count, data[root_offset:])
    _root_record_id(frame.root_record_bytes)
    return frame


def validate_tier_against_inventory(
    frame: TierFrame, envelope: SectionEnvelope, inventory: Inventory
) -> None:
    if not isinstance(frame, TierFrame):
        raise TypeError("frame must be TierFrame")
    expected_section_id = frame.tier_id + 2
    if (
        envelope.section_id != expected_section_id
        or envelope.section_type != 2
        or envelope.section_version != 0
        or envelope.closure_class != 128
        or envelope.dependencies != frame.body_section_ids
    ):
        _reject(TIER_FRAME, "tier.inventory_agreement")
    validate_envelope_against_inventory(envelope, inventory)
    expected = tuple(
        entry.section_id
        for entry in inventory.entries
        if entry.section_type == 3
        and (frame.tier_id == 1 or entry.closure_class == 128)
    )
    if frame.body_section_ids != expected:
        _reject(TIER_FRAME, "tier.body_section_ids")


def assemble_tier_bytes(frame: TierFrame, body_payloads: dict[int, bytes]) -> bytes:
    if not isinstance(frame, TierFrame) or type(body_payloads) is not dict:
        raise TypeError("invalid content assembly input")
    if set(body_payloads) != set(frame.body_section_ids):
        _reject(DEPENDENCY, "body_payloads")
    root_id = _root_record_id(frame.root_record_bytes)
    chunks: list[bytes] = [
        b"\0\0" + _be16(frame.assembled_record_count, "record_count")
    ]
    record_ids: list[int] = []
    derived_length = 4 + len(frame.root_record_bytes)
    for section_id in frame.body_section_ids:
        payload = body_payloads[section_id]
        if type(payload) is not bytes:
            _reject(TIER_FRAME, f"body_payloads[{section_id}]")
        derived_length += len(payload)
        if derived_length > frame.assembled_stream_byte_length:
            _reject(TIER_FRAME, "assembled_stream_byte_length")
        ids = _body_record_ids(payload, f"body_payloads[{section_id}]")
        if record_ids and ids[0] <= record_ids[-1]:
            _reject(TIER_FRAME, f"body_payloads[{section_id}]")
        record_ids.extend(ids)
        if len(record_ids) >= frame.assembled_record_count:
            _reject(TIER_FRAME, "assembled_record_count")
        chunks.append(payload)
    if not record_ids or root_id <= record_ids[-1]:
        _reject(TIER_FRAME, "root_record_bytes")
    if len(record_ids) + 1 != frame.assembled_record_count:
        _reject(TIER_FRAME, "assembled_record_count")
    if derived_length != frame.assembled_stream_byte_length:
        _reject(TIER_FRAME, "assembled_stream_byte_length")
    chunks.append(frame.root_record_bytes)
    stream = b"".join(chunks)
    if len(stream) != frame.assembled_stream_byte_length:
        _reject(CONTENT_STREAM, "assembled_stream_byte_length")
    return stream


def assemble_content_stream(frame: TierFrame, body_payloads: dict[int, bytes]) -> bytes:
    """Assemble and atomically validate the singular content-v0 stream."""

    stream = assemble_tier_bytes(frame, body_payloads)
    from . import content

    try:
        content.stream_validation(stream)
    except content.ContentReject as error:
        raise BootstrapReject(CONTENT_STREAM, "content_stream") from error
    return stream


# Recipe packages deliberately use immutable parsed objects.  Evaluation
# reparses the retained wire bytes, so a caller cannot bypass validation by
# constructing one of these public value objects directly.
@dataclass(frozen=True, slots=True)
class RecipeValueDescriptor:
    value_id: int
    value_type: int
    width: int
    count: int


@dataclass(frozen=True, slots=True)
class RecipeTable:
    table_id: int
    element_type: int
    element_width: int
    element_count: int
    payload: bytes


@dataclass(frozen=True, slots=True)
class RecipeNode:
    node_id: int
    opcode: int
    output_type: int
    output_width: int
    arguments: tuple[int, ...]
    auxiliary_u16: int
    auxiliary_u32: int
    immediate_u64: int


@dataclass(frozen=True, slots=True)
class Recipe:
    recipe_id: int
    inputs: tuple[RecipeValueDescriptor, ...]
    outputs: tuple[RecipeValueDescriptor, ...]
    nodes: tuple[RecipeNode, ...]
    edge_count: int
    primitive_steps: int
    peak_live_scratch_bytes: int
    recipe_bytes: int


@dataclass(frozen=True, slots=True)
class RecipePackage:
    profile_version: int
    tables: tuple[RecipeTable, ...]
    recipes: tuple[Recipe, ...]
    total_node_count: int
    total_edge_count: int
    table_payload_bytes: int
    maximum_primitive_steps: int
    peak_live_scratch_bytes: int
    encoded: bytes


@dataclass(frozen=True, slots=True)
class RecipeResult:
    status: int
    outputs: tuple[bytes, ...]


@dataclass(frozen=True, slots=True)
class _RecipeShape:
    value_type: int
    width: int
    count: int = 1
    element_type: int | None = None


@dataclass(frozen=True, slots=True)
class _RecipeValue:
    shape: _RecipeShape
    value: int | bytes


@dataclass(frozen=True, slots=True)
class _RawRecipe:
    recipe_id: int
    input_count: int
    output_count: int
    node_count: int
    edge_count: int
    primitive_steps: int
    peak_scratch: int
    recipe_bytes: int
    descriptors: bytes
    node_bytes: bytes


class _RecipeRuntimeLimit(Exception):
    pass


def _recipe_reject(path: str) -> None:
    _reject(RECIPE, path)


def _u64(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 8], "big")


def _shape_for_plain_type(value_type: int, width: int, path: str) -> _RecipeShape:
    if value_type == UINT and 1 <= width <= 64:
        return _RecipeShape(value_type, width)
    if value_type == BOOL and width == 1:
        return _RecipeShape(value_type, width)
    if value_type == BITS and 1 <= width <= RECIPE_PACKAGE_MAX:
        return _RecipeShape(value_type, width)
    if value_type == BYTES and 0 <= width <= RECIPE_PACKAGE_MAX:
        return _RecipeShape(value_type, width)
    if value_type == STATUS and width == 16:
        return _RecipeShape(value_type, width)
    _recipe_reject(path)


def _shape_storage(shape: _RecipeShape) -> int:
    if shape.value_type == TABLE:
        return 0
    if shape.value_type == BYTES:
        return shape.width
    return (shape.width + 7) // 8


def _table_element_size(element_type: int, width: int, path: str) -> int:
    shape = _shape_for_plain_type(element_type, width, path)
    return _shape_storage(shape)


def _validate_scalar_encoding(
    raw: bytes, value_type: int, width: int, path: str
) -> None:
    if value_type == BYTES:
        return
    if not raw:
        _recipe_reject(path)
    number = int.from_bytes(raw, "big")
    if value_type == BITS:
        unused = len(raw) * 8 - width
        if unused and number & ((1 << unused) - 1):
            _recipe_reject(path)
        return
    if number >= 1 << width:
        _recipe_reject(path)
    if value_type == BOOL and number > 1:
        _recipe_reject(path)
    if value_type == STATUS and number > 14:
        _recipe_reject(path)


def _parse_descriptor(raw: bytes, expected_id: int, path: str) -> RecipeValueDescriptor:
    value_id = _u16(raw, 0)
    value_type = raw[2]
    flags = raw[3]
    width = _u32(raw, 4)
    count = _u32(raw, 8)
    if value_id != expected_id or flags != 0:
        _recipe_reject(path)
    # TABLE is intentionally not an interface type: its wire descriptor has no
    # element-type field, so it cannot be typed without hidden inference.
    if value_type == TABLE:
        _recipe_reject(path)
    _shape_for_plain_type(value_type, width, path)
    if count != 1:
        _recipe_reject(path)
    return RecipeValueDescriptor(value_id, value_type, width, count)


def _node_shape(
    node: RecipeNode,
    tables: dict[int, RecipeTable],
    arguments: tuple[_RecipeShape, ...] = (),
) -> _RecipeShape:
    if node.output_type == TABLE:
        if node.opcode == 2:
            table = tables.get(node.auxiliary_u16)
            if table is None or node.output_width != table.element_width:
                _recipe_reject(f"recipes[{node.node_id}].output")
            return _RecipeShape(
                TABLE,
                table.element_width,
                table.element_count,
                table.element_type,
            )
        if (
            node.opcode == 23
            and len(arguments) == 3
            and arguments[1].value_type == TABLE
            and arguments[1] == arguments[2]
            and node.output_width == arguments[1].width
        ):
            return arguments[1]
        _recipe_reject(f"recipes[{node.node_id}].output")
    return _shape_for_plain_type(
        node.output_type, node.output_width, f"nodes[{node.node_id}].output"
    )


def _same_shape(left: _RecipeShape, right: _RecipeShape) -> bool:
    return left == right


def _emit_units(shape: _RecipeShape) -> tuple[str, int]:
    if shape.value_type == BYTES:
        return "byte", shape.width
    if shape.value_type == TABLE:
        _recipe_reject("emit.table")
    return "bit", shape.width


def _emit_compatible(source: _RecipeShape, destination: _RecipeShape) -> bool:
    if source.value_type == STATUS or destination.value_type == STATUS:
        return source.value_type == destination.value_type == STATUS
    if source.value_type == BYTES or destination.value_type == BYTES:
        return source.value_type == destination.value_type == BYTES
    if source.value_type == TABLE or destination.value_type == TABLE:
        return False
    if source.value_type == BOOL:
        return destination.value_type == BOOL
    if source.value_type == UINT:
        return destination.value_type in (UINT, BITS)
    return source.value_type == BITS and destination.value_type == BITS


def decode_recipe_package(data: bytes, expected_profile_version: int) -> RecipePackage:
    """Parse and completely validate one Section-12 recipe package.

    Static rejection is atomic: every malformed package maps to rejection 18,
    and no evaluator-visible object is returned before all thirteen stages pass.
    """

    # Stage 1: cap and complete fixed header.
    if type(data) is not bytes or not 64 <= len(data) <= RECIPE_PACKAGE_MAX:
        _recipe_reject("package.length")
    # Stage 2: identity/version/profile and reserved fields.
    if (
        data[:8] != b"GBRECP0\0"
        or _u16(data, 8) != 0
        or _u16(data, 10) != 0
        or type(expected_profile_version) is not int
        or not 1 <= expected_profile_version <= 7
        or _u16(data, 12) != expected_profile_version
        or _u16(data, 14) != 0
        or any(data[48:64])
    ):
        _recipe_reject("package.header")
    recipe_count = _u16(data, 16)
    table_count = _u16(data, 18)
    total_nodes = _u32(data, 20)
    total_edges = _u32(data, 24)
    declared_table_payload = _u32(data, 28)
    package_bytes = _u32(data, 32)
    maximum_steps = _u64(data, 36)
    package_peak = _u32(data, 44)
    # Stage 3: closed ranges and exact outer length. Derived equality is later.
    if (
        not 1 <= recipe_count <= 256
        or table_count > 4_096
        or not 1 <= total_nodes <= RECIPE_NODE_MAX
        or total_edges > RECIPE_EDGE_MAX
        or declared_table_payload > RECIPE_PACKAGE_MAX
        or package_bytes != len(data)
        or not 64 <= package_bytes <= RECIPE_PACKAGE_MAX
        or maximum_steps > RECIPE_STEP_MAX
        or package_peak > RECIPE_SCRATCH_MAX
    ):
        _recipe_reject("package.ranges")

    # Stage 4: tables, including exact payload representation.
    offset = 64
    tables: list[RecipeTable] = []
    table_payload_sum = 0
    previous_id = 0
    for ordinal in range(table_count):
        if offset + 16 > len(data):
            _recipe_reject(f"tables[{ordinal}].header")
        table_id = _u16(data, offset)
        element_type = data[offset + 2]
        flags = data[offset + 3]
        width = _u32(data, offset + 4)
        count = _u32(data, offset + 8)
        payload_bytes = _u32(data, offset + 12)
        if table_id <= previous_id or table_id == 0 or flags != 0:
            _recipe_reject(f"tables[{ordinal}].header")
        previous_id = table_id
        element_size = _table_element_size(
            element_type, width, f"tables[{ordinal}].descriptor"
        )
        if not 1 <= count <= RECIPE_PACKAGE_MAX:
            _recipe_reject(f"tables[{ordinal}].count")
        expected_payload = element_size * count
        if expected_payload > RECIPE_PACKAGE_MAX or payload_bytes != expected_payload:
            _recipe_reject(f"tables[{ordinal}].payload_bytes")
        end = offset + 16 + payload_bytes
        if end > len(data):
            _recipe_reject(f"tables[{ordinal}].payload")
        payload = data[offset + 16 : end]
        for index in range(count):
            start = index * element_size
            _validate_scalar_encoding(
                payload[start : start + element_size],
                element_type,
                width,
                f"tables[{ordinal}].elements[{index}]",
            )
        table_payload_sum += payload_bytes
        if table_payload_sum > RECIPE_PACKAGE_MAX:
            _recipe_reject("package.table_payload_bytes")
        tables.append(RecipeTable(table_id, element_type, width, count, payload))
        offset = end
    if table_payload_sum != declared_table_payload:
        _recipe_reject("package.table_payload_bytes")

    # Stage 5: recipe headers and exact record boundaries. Descriptor and node
    # semantics remain untouched until their prescribed stages below.
    raw_recipes: list[_RawRecipe] = []
    previous_id = 0
    declared_node_sum = 0
    for ordinal in range(recipe_count):
        if offset + 32 > len(data):
            _recipe_reject(f"recipes[{ordinal}].header")
        recipe_id = _u16(data, offset)
        flags = _u16(data, offset + 2)
        input_count = _u16(data, offset + 4)
        output_count = _u16(data, offset + 6)
        node_count = _u32(data, offset + 8)
        edge_count = _u32(data, offset + 12)
        primitive_steps = _u64(data, offset + 16)
        peak_scratch = _u32(data, offset + 24)
        recipe_bytes = _u32(data, offset + 28)
        expected_bytes = 32 + 12 * (input_count + output_count) + 32 * node_count
        if (
            recipe_id <= previous_id
            or recipe_id == 0
            or flags != 0
            or input_count > 64
            or not 1 <= output_count <= 64
            or not 1 <= node_count <= RECIPE_NODE_MAX
            or input_count + node_count > 0xFFFF
            or edge_count > RECIPE_EDGE_MAX
            or primitive_steps > RECIPE_STEP_MAX
            or peak_scratch > RECIPE_SCRATCH_MAX
            or recipe_bytes != expected_bytes
        ):
            _recipe_reject(f"recipes[{ordinal}].header")
        previous_id = recipe_id
        end = offset + recipe_bytes
        if end > len(data):
            _recipe_reject(f"recipes[{ordinal}].boundary")
        descriptors_end = offset + 32 + 12 * (input_count + output_count)
        raw_recipes.append(
            _RawRecipe(
                recipe_id,
                input_count,
                output_count,
                node_count,
                edge_count,
                primitive_steps,
                peak_scratch,
                recipe_bytes,
                data[offset + 32 : descriptors_end],
                data[descriptors_end:end],
            )
        )
        declared_node_sum += node_count
        if declared_node_sum > RECIPE_NODE_MAX:
            _recipe_reject("package.total_node_count")
        offset = end
    if declared_node_sum != total_nodes:
        _recipe_reject("package.total_node_count")

    # Stage 6: closed interface descriptors.
    descriptor_sets: list[
        tuple[tuple[RecipeValueDescriptor, ...], tuple[RecipeValueDescriptor, ...]]
    ] = []
    for raw in raw_recipes:
        inputs = tuple(
            _parse_descriptor(
                raw.descriptors[index * 12 : (index + 1) * 12],
                index + 1,
                f"recipes[{raw.recipe_id}].inputs[{index}]",
            )
            for index in range(raw.input_count)
        )
        output_base = raw.input_count * 12
        outputs = tuple(
            _parse_descriptor(
                raw.descriptors[
                    output_base + index * 12 : output_base + (index + 1) * 12
                ],
                index + 1,
                f"recipes[{raw.recipe_id}].outputs[{index}]",
            )
            for index in range(raw.output_count)
        )
        if outputs[0].value_type != STATUS or outputs[0].width != 16:
            _recipe_reject(f"recipes[{raw.recipe_id}].outputs[0]")
        if any(output.value_type == STATUS for output in outputs[1:]):
            _recipe_reject(f"recipes[{raw.recipe_id}].outputs")
        descriptor_sets.append((inputs, outputs))

    # Stage 7: node records, known opcodes, counts, and unused fields.
    node_sets: list[tuple[RecipeNode, ...]] = []
    assigned_fields = {
        1: (False, True),
        2: (True, False),
        5: (True, True),
        14: (False, True),
        22: (True, True),
        25: (False, True),
    }
    argument_counts = {
        1: 0,
        2: 0,
        3: 3,
        4: 2,
        5: 1,
        6: 2,
        7: 2,
        8: 2,
        9: 2,
        10: 2,
        11: 2,
        12: 2,
        13: 2,
        14: 1,
        15: 2,
        16: 2,
        17: 2,
        18: 2,
        19: 2,
        20: 3,
        21: 2,
        22: 1,
        23: 3,
        24: 0,
        25: 0,
    }
    for raw in raw_recipes:
        nodes: list[RecipeNode] = []
        for index in range(raw.node_count):
            record = raw.node_bytes[index * 32 : (index + 1) * 32]
            node_id = _u16(record, 0)
            opcode = record[2]
            output_type = record[3]
            output_width = _u32(record, 4)
            argument_count = _u16(record, 8)
            all_arguments = tuple(_u16(record, 10 + 2 * sub) for sub in range(4))
            auxiliary_u16 = _u16(record, 18)
            auxiliary_u32 = _u32(record, 20)
            immediate = _u64(record, 24)
            expected_arguments = argument_counts.get(opcode)
            aux_assigned, immediate_assigned = assigned_fields.get(
                opcode, (False, False)
            )
            if (
                node_id != index + 1
                or expected_arguments is None
                or argument_count != expected_arguments
                or any(all_arguments[argument_count:])
                or auxiliary_u32 != 0
                or (not aux_assigned and auxiliary_u16 != 0)
                or (not immediate_assigned and immediate != 0)
            ):
                _recipe_reject(f"recipes[{raw.recipe_id}].nodes[{index}]")
            nodes.append(
                RecipeNode(
                    node_id,
                    opcode,
                    output_type,
                    output_width,
                    all_arguments[:argument_count],
                    auxiliary_u16,
                    auxiliary_u32,
                    immediate,
                )
            )
        node_sets.append(tuple(nodes))

    # Stage 8: all data references are backward and edge declarations are exact.
    derived_edge_sum = 0
    for raw, nodes in zip(raw_recipes, node_sets, strict=True):
        local_edges = 0
        for node in nodes:
            maximum_value_id = raw.input_count + node.node_id - 1
            if any(
                not 1 <= value_id <= maximum_value_id for value_id in node.arguments
            ):
                _recipe_reject(
                    f"recipes[{raw.recipe_id}].nodes[{node.node_id}].arguments"
                )
            local_edges += len(node.arguments) + (1 if node.opcode == 22 else 0)
        if local_edges != raw.edge_count:
            _recipe_reject(f"recipes[{raw.recipe_id}].edge_count")
        derived_edge_sum += local_edges
    if derived_edge_sum != total_edges or derived_edge_sum > RECIPE_EDGE_MAX:
        _recipe_reject("package.total_edge_count")

    # Stage 9: exact opcode typing and fixed immediate rules, except cross-recipe
    # ITERATE body constraints which are deliberately stage 10.
    table_by_id = {table.table_id: table for table in tables}
    shape_sets: list[dict[int, _RecipeShape]] = []
    for raw, descriptors, nodes in zip(
        raw_recipes, descriptor_sets, node_sets, strict=True
    ):
        inputs, outputs = descriptors
        shapes: dict[int, _RecipeShape] = {
            descriptor.value_id: _RecipeShape(
                descriptor.value_type, descriptor.width, descriptor.count
            )
            for descriptor in inputs
        }
        output_shapes = tuple(
            _RecipeShape(item.value_type, item.width, item.count) for item in outputs
        )
        for node in nodes:
            args = tuple(shapes[value_id] for value_id in node.arguments)
            result = _node_shape(node, table_by_id, args)
            opcode = node.opcode
            valid = True
            if opcode == 1:
                valid = result.value_type in (UINT, BOOL, STATUS)
                if valid:
                    valid = node.immediate_u64 < (1 << result.width)
                if result.value_type == BOOL:
                    valid = valid and node.immediate_u64 <= 1
                if result.value_type == STATUS:
                    valid = valid and node.immediate_u64 <= 14
            elif opcode == 2:
                valid = node.auxiliary_u16 in table_by_id and result.value_type == TABLE
            elif opcode == 3:
                sequence, start, length = args
                valid = start.value_type == length.value_type == UINT
                valid = valid and (
                    (
                        sequence.value_type == BITS
                        and result.value_type in (BITS, UINT)
                        and (result.value_type != UINT or result.width <= 64)
                    )
                    or sequence.value_type == result.value_type == BYTES
                )
                valid = valid and result.width <= sequence.width
            elif opcode == 4:
                left, right = args
                valid = left.value_type == right.value_type == result.value_type
                valid = valid and result.value_type in (UINT, BITS, BYTES)
                valid = valid and result.width == left.width + right.width
                valid = valid and (result.value_type != UINT or result.width <= 64)
            elif opcode == 5:
                slot = node.auxiliary_u16
                valid = result == _RecipeShape(STATUS, 16) and 1 <= slot <= len(outputs)
                if valid:
                    destination = output_shapes[slot - 1]
                    source_kind, source_width = _emit_units(args[0])
                    destination_kind, destination_width = _emit_units(destination)
                    valid = (
                        source_kind == destination_kind
                        and _emit_compatible(args[0], destination)
                        and node.immediate_u64 + source_width <= destination_width
                    )
            elif opcode in (6, 7, 8, 9, 10):
                valid = (
                    args[0].value_type
                    == args[1].value_type
                    == result.value_type
                    == UINT
                    and args[0].width == args[1].width == result.width
                )
            elif opcode in (11, 12, 13):
                valid = args[0] == args[1] == result and result.value_type in (
                    UINT,
                    BITS,
                )
            elif opcode == 14:
                valid = args[0] == result and result.value_type == UINT
                valid = valid and node.immediate_u64 < (1 << result.width)
            elif opcode in (15, 16):
                valid = args[0] == result and result.value_type == UINT
                valid = valid and args[1].value_type == UINT
            elif opcode == 17:
                valid = args[0] == args[1] and result == _RecipeShape(BOOL, 1)
            elif opcode == 18:
                valid = (
                    args[0] == args[1]
                    and args[0].value_type == UINT
                    and result == _RecipeShape(BOOL, 1)
                )
            elif opcode == 19:
                sequence, index = args
                valid = index.value_type == UINT
                expected = None
                if sequence.value_type == BITS:
                    expected = _RecipeShape(BOOL, 1)
                elif sequence.value_type == BYTES:
                    expected = _RecipeShape(UINT, 8)
                elif sequence.value_type == TABLE:
                    assert sequence.element_type is not None
                    expected = _RecipeShape(sequence.element_type, sequence.width)
                valid = valid and expected == result
            elif opcode == 20:
                sequence, index, element = args
                valid = index.value_type == UINT and result == sequence
                valid = valid and (
                    (sequence.value_type == BITS and element == _RecipeShape(BOOL, 1))
                    or (
                        sequence.value_type == BYTES
                        and element == _RecipeShape(UINT, 8)
                    )
                )
            elif opcode == 21:
                table_shape, index = args
                valid = table_shape.value_type == TABLE and index.value_type == UINT
                if valid:
                    assert table_shape.element_type is not None
                    valid = result == _RecipeShape(
                        table_shape.element_type, table_shape.width
                    )
            elif opcode == 22:
                valid = result == args[0]
                valid = valid and node.immediate_u64 <= RECIPE_ITERATION_MAX
                valid = valid and node.auxiliary_u16 != 0
            elif opcode == 23:
                valid = (
                    args[0] == _RecipeShape(BOOL, 1) and args[1] == args[2] == result
                )
            elif opcode == 24:
                valid = result == _RecipeShape(STATUS, 16)
            elif opcode == 25:
                valid = (
                    result == _RecipeShape(STATUS, 16) and 1 <= node.immediate_u64 <= 14
                )
            if not valid:
                _recipe_reject(f"recipes[{raw.recipe_id}].nodes[{node.node_id}].opcode")
            shapes[raw.input_count + node.node_id] = result
        shape_sets.append(shapes)

    # Stage 10: the only calls are fixed, lower-ID ITERATE bodies.
    recipe_index_by_id = {raw.recipe_id: index for index, raw in enumerate(raw_recipes)}
    for recipe_index, (raw, nodes, shapes) in enumerate(
        zip(raw_recipes, node_sets, shape_sets, strict=True)
    ):
        for node in nodes:
            if node.opcode != 22:
                continue
            body_index = recipe_index_by_id.get(node.auxiliary_u16)
            if body_index is None or body_index >= recipe_index:
                _recipe_reject(f"recipes[{raw.recipe_id}].nodes[{node.node_id}].body")
            body_inputs, body_outputs = descriptor_sets[body_index]
            accumulator = shapes[node.arguments[0]]
            if (
                len(body_inputs) != 2
                or len(body_outputs) != 2
                or _RecipeShape(body_inputs[0].value_type, body_inputs[0].width)
                != accumulator
                or _RecipeShape(body_inputs[1].value_type, body_inputs[1].width)
                != _RecipeShape(UINT, 64)
                or _RecipeShape(body_outputs[1].value_type, body_outputs[1].width)
                != accumulator
            ):
                _recipe_reject(f"recipes[{raw.recipe_id}].nodes[{node.node_id}].body")

    # Stage 11: every node reaches an EMIT, and EMIT ranges cover every output
    # position once without a gap or overlap.
    for recipe_index, (raw, descriptors, nodes) in enumerate(
        zip(raw_recipes, descriptor_sets, node_sets, strict=True)
    ):
        _, outputs = descriptors
        reachable: set[int] = {node.node_id for node in nodes if node.opcode == 5}
        stack = list(reachable)
        while stack:
            node_id = stack.pop()
            node = nodes[node_id - 1]
            for value_id in node.arguments:
                if value_id > raw.input_count:
                    dependency = value_id - raw.input_count
                    if dependency not in reachable:
                        reachable.add(dependency)
                        stack.append(dependency)
        if reachable != set(range(1, raw.node_count + 1)):
            _recipe_reject(f"recipes[{raw.recipe_id}].unreachable")
        coverage = [
            bytearray(_emit_units(_RecipeShape(o.value_type, o.width))[1])
            for o in outputs
        ]
        for node in nodes:
            if node.opcode != 5:
                continue
            source_id = node.arguments[0]
            source_shape = shape_sets[recipe_index][source_id]
            _, width = _emit_units(source_shape)
            slot = node.auxiliary_u16 - 1
            start = node.immediate_u64
            end = start + width
            if any(coverage[slot][start:end]):
                _recipe_reject(f"recipes[{raw.recipe_id}].outputs[{slot}]")
            coverage[slot][start:end] = b"\1" * width
        if any(not all(slot) for slot in coverage):
            _recipe_reject(f"recipes[{raw.recipe_id}].outputs")

    # Stage 12: recursively derived worst-case steps and exact last-use scratch.
    derived_steps: list[int] = []
    derived_peaks: list[int] = []
    for recipe_index, (raw, nodes, shapes) in enumerate(
        zip(raw_recipes, node_sets, shape_sets, strict=True)
    ):
        steps = len(nodes)
        for node in nodes:
            if node.opcode == 22:
                body_index = recipe_index_by_id[node.auxiliary_u16]
                steps += node.immediate_u64 * derived_steps[body_index]
                if steps > RECIPE_STEP_MAX:
                    _recipe_reject(f"recipes[{raw.recipe_id}].primitive_steps")
        last_use = {node.node_id: node.node_id for node in nodes}
        for consumer in nodes:
            for value_id in consumer.arguments:
                if value_id > raw.input_count:
                    last_use[value_id - raw.input_count] = consumer.node_id
        live: dict[int, int] = {}
        live_bytes = 0
        peak = 0
        for node in nodes:
            result_shape = shapes[raw.input_count + node.node_id]
            result_bytes = _shape_storage(result_shape)
            if node.opcode == 22:
                body_index = recipe_index_by_id[node.auxiliary_u16]
                peak = max(peak, live_bytes + derived_peaks[body_index])
            peak = max(peak, live_bytes + result_bytes)
            live[node.node_id] = result_bytes
            live_bytes += result_bytes
            for value_node_id in tuple(live):
                if last_use[value_node_id] == node.node_id:
                    live_bytes -= live.pop(value_node_id)
        if (
            steps != raw.primitive_steps
            or peak != raw.peak_scratch
            or steps > RECIPE_STEP_MAX
            or peak > RECIPE_SCRATCH_MAX
        ):
            _recipe_reject(f"recipes[{raw.recipe_id}].resources")
        derived_steps.append(steps)
        derived_peaks.append(peak)
    if maximum_steps != max(derived_steps) or package_peak != max(derived_peaks):
        _recipe_reject("package.resources")

    # Stage 13: the final recipe ends at the exact package end.
    if offset != len(data):
        _recipe_reject("package.trailing_data")

    recipes = tuple(
        Recipe(
            raw.recipe_id,
            descriptor_sets[index][0],
            descriptor_sets[index][1],
            node_sets[index],
            raw.edge_count,
            raw.primitive_steps,
            raw.peak_scratch,
            raw.recipe_bytes,
        )
        for index, raw in enumerate(raw_recipes)
    )
    return RecipePackage(
        expected_profile_version,
        tuple(tables),
        recipes,
        total_nodes,
        total_edges,
        declared_table_payload,
        maximum_steps,
        package_peak,
        data,
    )


def _decode_value(raw: bytes, shape: _RecipeShape, path: str) -> _RecipeValue:
    if type(raw) is not bytes or len(raw) != _shape_storage(shape):
        _recipe_reject(path)
    _validate_scalar_encoding(raw, shape.value_type, shape.width, path)
    if shape.value_type == BYTES:
        return _RecipeValue(shape, raw)
    number = int.from_bytes(raw, "big")
    if shape.value_type == BITS:
        number >>= len(raw) * 8 - shape.width
    return _RecipeValue(shape, number)


def _encode_value(value: _RecipeValue) -> bytes:
    shape = value.shape
    if shape.value_type == BYTES:
        assert type(value.value) is bytes
        return value.value
    assert type(value.value) is int
    size = _shape_storage(shape)
    number = value.value
    if shape.value_type == BITS:
        number <<= size * 8 - shape.width
    return number.to_bytes(size, "big")


def _table_element(table: RecipeTable, index: int) -> _RecipeValue:
    if not 0 <= index < table.element_count:
        raise _RecipeRuntimeLimit
    shape = _RecipeShape(table.element_type, table.element_width)
    size = _shape_storage(shape)
    return _decode_value(
        table.payload[index * size : (index + 1) * size], shape, "table.element"
    )


def _value_bits(value: _RecipeValue) -> tuple[int, ...]:
    shape = value.shape
    assert shape.value_type not in (BYTES, TABLE)
    assert type(value.value) is int
    return tuple(
        (value.value >> (shape.width - index - 1)) & 1 for index in range(shape.width)
    )


def _execute_recipe(
    package: RecipePackage,
    recipe: Recipe,
    input_raw: tuple[bytes, ...],
    recipe_by_id: dict[int, Recipe],
    table_by_id: dict[int, RecipeTable],
) -> RecipeResult:
    if len(input_raw) != len(recipe.inputs):
        _recipe_reject("evaluation.inputs")
    values: dict[int, _RecipeValue] = {}
    for descriptor, raw in zip(recipe.inputs, input_raw, strict=True):
        shape = _RecipeShape(descriptor.value_type, descriptor.width)
        values[descriptor.value_id] = _decode_value(raw, shape, "evaluation.inputs")
    output_shapes = tuple(
        _RecipeShape(output.value_type, output.width) for output in recipe.outputs
    )
    staged: list[list[int | None]] = [
        [None] * _emit_units(shape)[1] for shape in output_shapes
    ]
    try:
        for node in recipe.nodes:
            args = tuple(values[value_id] for value_id in node.arguments)
            shape = _node_shape(node, table_by_id, tuple(arg.shape for arg in args))
            opcode = node.opcode
            result: _RecipeValue
            if opcode == 1:
                result = _RecipeValue(shape, node.immediate_u64)
            elif opcode == 2:
                table = table_by_id[node.auxiliary_u16]
                result = _RecipeValue(shape, table.payload)
            elif opcode == 3:
                sequence, start_value, length_value = args
                assert (
                    type(start_value.value) is int and type(length_value.value) is int
                )
                start, length = start_value.value, length_value.value
                if length != shape.width or start + length > sequence.shape.width:
                    raise _RecipeRuntimeLimit
                if sequence.shape.value_type == BYTES:
                    assert type(sequence.value) is bytes
                    result = _RecipeValue(shape, sequence.value[start : start + length])
                else:
                    assert type(sequence.value) is int
                    shift = sequence.shape.width - start - length
                    result = _RecipeValue(
                        shape, (sequence.value >> shift) & ((1 << length) - 1)
                    )
            elif opcode == 4:
                left, right = args
                if shape.value_type == BYTES:
                    assert type(left.value) is bytes and type(right.value) is bytes
                    combined: int | bytes = left.value + right.value
                else:
                    assert type(left.value) is int and type(right.value) is int
                    combined = (left.value << right.shape.width) | right.value
                result = _RecipeValue(shape, combined)
            elif opcode == 5:
                source = args[0]
                slot = node.auxiliary_u16 - 1
                start = node.immediate_u64
                if source.shape.value_type == BYTES:
                    assert type(source.value) is bytes
                    units = tuple(source.value)
                else:
                    units = _value_bits(source)
                staged[slot][start : start + len(units)] = units
                result = _RecipeValue(shape, 0)
            elif opcode in (6, 7, 8, 9, 10):
                assert type(args[0].value) is int and type(args[1].value) is int
                left, right = args[0].value, args[1].value
                limit = 1 << shape.width
                if opcode == 6:
                    number = left + right
                    if number >= limit:
                        raise _RecipeRuntimeLimit
                elif opcode == 7:
                    if left < right:
                        raise _RecipeRuntimeLimit
                    number = left - right
                elif opcode == 8:
                    number = left * right
                    if number >= limit:
                        raise _RecipeRuntimeLimit
                else:
                    if right == 0:
                        raise _RecipeRuntimeLimit
                    number = left // right if opcode == 9 else left % right
                result = _RecipeValue(shape, number)
            elif opcode in (11, 12, 13):
                assert type(args[0].value) is int and type(args[1].value) is int
                if opcode == 11:
                    number = args[0].value & args[1].value
                elif opcode == 12:
                    number = args[0].value | args[1].value
                else:
                    number = args[0].value ^ args[1].value
                result = _RecipeValue(shape, number)
            elif opcode == 14:
                assert type(args[0].value) is int
                result = _RecipeValue(shape, args[0].value & node.immediate_u64)
            elif opcode in (15, 16):
                assert type(args[0].value) is int and type(args[1].value) is int
                shift = args[1].value
                if shift >= shape.width:
                    raise _RecipeRuntimeLimit
                number = (
                    args[0].value << shift if opcode == 15 else args[0].value >> shift
                )
                if number >= 1 << shape.width:
                    raise _RecipeRuntimeLimit
                result = _RecipeValue(shape, number)
            elif opcode in (17, 18):
                if opcode == 17:
                    number = int(args[0].value == args[1].value)
                else:
                    assert type(args[0].value) is int and type(args[1].value) is int
                    number = int(args[0].value < args[1].value)
                result = _RecipeValue(shape, number)
            elif opcode in (19, 21):
                sequence, index_value = args
                assert type(index_value.value) is int
                index = index_value.value
                if sequence.shape.value_type == BITS:
                    if index >= sequence.shape.width:
                        raise _RecipeRuntimeLimit
                    assert type(sequence.value) is int
                    number = (sequence.value >> (sequence.shape.width - index - 1)) & 1
                    result = _RecipeValue(shape, number)
                elif sequence.shape.value_type == BYTES:
                    if index >= sequence.shape.width:
                        raise _RecipeRuntimeLimit
                    assert type(sequence.value) is bytes
                    result = _RecipeValue(shape, sequence.value[index])
                else:
                    table = next(
                        item
                        for item in package.tables
                        if item.payload == sequence.value
                        and item.element_type == sequence.shape.element_type
                        and item.element_width == sequence.shape.width
                        and item.element_count == sequence.shape.count
                    )
                    result = _table_element(table, index)
            elif opcode == 20:
                sequence, index_value, element = args
                assert type(index_value.value) is int
                index = index_value.value
                if index >= sequence.shape.width:
                    raise _RecipeRuntimeLimit
                if sequence.shape.value_type == BITS:
                    assert type(sequence.value) is int and type(element.value) is int
                    shift = sequence.shape.width - index - 1
                    number = (sequence.value & ~(1 << shift)) | (element.value << shift)
                    result = _RecipeValue(shape, number)
                else:
                    assert type(sequence.value) is bytes and type(element.value) is int
                    updated = bytearray(sequence.value)
                    updated[index] = element.value
                    result = _RecipeValue(shape, bytes(updated))
            elif opcode == 22:
                accumulator = args[0]
                body = recipe_by_id[node.auxiliary_u16]
                for index in range(node.immediate_u64):
                    body_result = _execute_recipe(
                        package,
                        body,
                        (_encode_value(accumulator), index.to_bytes(8, "big")),
                        recipe_by_id,
                        table_by_id,
                    )
                    if body_result.status != 0:
                        return RecipeResult(body_result.status, ())
                    accumulator = _decode_value(
                        body_result.outputs[0], shape, "iterate.accumulator"
                    )
                result = accumulator
            elif opcode == 23:
                assert type(args[0].value) is int
                result = args[1] if args[0].value else args[2]
            elif opcode == 24:
                result = _RecipeValue(shape, 0)
            else:
                assert opcode == 25
                result = _RecipeValue(shape, node.immediate_u64)
            values[len(recipe.inputs) + node.node_id] = result
    except _RecipeRuntimeLimit:
        return RecipeResult(11, ())

    if any(any(unit is None for unit in slot) for slot in staged):
        # Impossible after complete static coverage, retained as a fail-closed
        # evaluator invariant rather than exposing a partial result.
        return RecipeResult(11, ())
    output_raw: list[bytes] = []
    for shape, slot in zip(output_shapes, staged, strict=True):
        if shape.value_type == BYTES:
            output_raw.append(bytes(int(unit) for unit in slot))
        else:
            number = 0
            for unit in slot:
                number = (number << 1) | int(unit)
            output_raw.append(_encode_value(_RecipeValue(shape, number)))
    status = int.from_bytes(output_raw[0], "big")
    if not 0 <= status <= 14:
        return RecipeResult(11, ())
    return RecipeResult(status, tuple(output_raw[1:]) if status == 0 else ())


def evaluate_recipe(
    package: RecipePackage, recipe_id: int, inputs: Sequence[bytes]
) -> RecipeResult:
    """Evaluate one fully validated recipe with atomic status/output release."""

    if not isinstance(package, RecipePackage):
        raise TypeError("evaluate_recipe requires RecipePackage")
    # Reparse retained wire bytes to defend the evaluator from forged dataclass
    # instances and from any future accidental validation/evaluation drift.
    trusted = decode_recipe_package(package.encoded, package.profile_version)
    if type(recipe_id) is not int:
        raise TypeError("recipe_id must be an integer")
    if isinstance(inputs, (bytes, bytearray, str)):
        raise TypeError("inputs must be a sequence of byte strings")
    try:
        input_tuple = tuple(inputs)
    except TypeError as error:
        raise TypeError("inputs must be a sequence of byte strings") from error
    if any(type(item) is not bytes for item in input_tuple):
        raise TypeError("inputs must contain only bytes")
    recipe_by_id = {recipe.recipe_id: recipe for recipe in trusted.recipes}
    recipe = recipe_by_id.get(recipe_id)
    if recipe is None:
        _recipe_reject("evaluation.recipe_id")
    return _execute_recipe(
        trusted,
        recipe,
        input_tuple,
        recipe_by_id,
        {table.table_id: table for table in trusted.tables},
    )
