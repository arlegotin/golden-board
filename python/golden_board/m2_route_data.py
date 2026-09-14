"""Result-free M2 route-data owner and exact shell-sector ledger.

The module owns the candidate-neutral twelve-fact route template.  Candidate
procedure packages are inputs: they must expose the frozen recipe ABI and pass
the frozen worked/held-out examples before any route bytes are returned.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import Sequence

from . import bootstrap, canonical_manifest


SECTOR_SIDE = 2_048
SHELL_WIDTH = 128
SECTOR_CAPACITY_CELLS = SHELL_WIDTH * (SECTOR_SIDE - SHELL_WIDTH)
SECTOR_CAPACITY_BYTES = SECTOR_CAPACITY_CELLS // 8
R3_SECTOR_SIDE = 2_040
R3_SHELL_WIDTH = 128
R3_SECTOR_CAPACITY_BYTES = (
    R3_SHELL_WIDTH * (R3_SECTOR_SIDE - R3_SHELL_WIDTH) // 8
)
DISCRIMINATOR_CELLS = 256
PAD_DOMAIN = b"GB-M2-SHELL-PAD-v0\0"
ROUTE_MAGIC = b"GBROUTE\0"
ROUTE_VERSION = 0
EXPORTED_RECIPE_FIRST = 101
EXPORTED_RECIPE_LAST = 112

CALIBRATIONS = (
    bytes.fromhex("f00fcc33aa559669817e24db18e742bd01fe02fd04fb08f710ef20df40bf807f"),
    bytes.fromhex("cc33aa559669f00f02fd18e742bd817e04fb08f710ef20df40bf807f01fe24db"),
    bytes.fromhex("aa559669f00fcc3304fb42bd817e24db08f710ef20df40bf807f01fe02fd18e7"),
    bytes.fromhex("9669f00fcc33aa5508f7817e24db18e710ef20df40bf807f01fe02fd04fb42bd"),
)
SECTOR_MASKS = (0x00, 0x3C, 0xA5, 0xC9)


class RouteDataError(ValueError):
    """Stable fail-closed route-data rejection."""

    __slots__ = ("reason",)

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class ValueDescriptor:
    value_type: int
    width: int

    @property
    def encoded_bytes(self) -> int:
        return self.width if self.value_type == bootstrap.BYTES else (self.width + 7) // 8


@dataclass(frozen=True, slots=True)
class FactTemplate:
    fact_id: int
    stage: int
    name: str
    consumes: tuple[int, ...]
    definition: ValueDescriptor
    definition_value: bytes
    recipe_id: int
    inputs: tuple[ValueDescriptor, ...]
    outputs: tuple[ValueDescriptor, ...]
    mask_input_slots: tuple[int, ...]
    source_inputs: tuple[ValueDescriptor, ...]
    worked_source: bytes
    held_source: bytes
    source_mask_mode: str | None
    worked_sector_sources: tuple[bytes, ...]
    held_sector_sources: tuple[bytes, ...]
    encoder_recipe_id: int | None
    worked_damage_offset: int | None
    worked_damage_xor: int | None
    held_damage_offset: int | None
    held_damage_xor: int | None
    erasure_capacity: int | None
    worked_input: bytes
    worked_output: bytes
    held_input: bytes
    held_output: bytes


@dataclass(frozen=True, slots=True)
class CandidateRouteData:
    profile_id: str
    profile_version: int
    transport_id: str
    section_check_id: str
    recipe_packages: tuple[bytes, ...]


@dataclass(frozen=True, slots=True)
class LedgerSpan:
    start_cell: int
    cell_count: int
    owner: str


@dataclass(frozen=True, slots=True)
class SectorImage:
    sector_id: int
    data: bytes
    route_prefix_cells: int
    headroom_cells: int
    spans: tuple[LedgerSpan, ...]


@dataclass(frozen=True, slots=True)
class RouteImageSet:
    profile_id: str
    profile_version: int
    instruction_cells: int
    headroom_cells: int
    sectors: tuple[SectorImage, ...]


@dataclass(frozen=True, slots=True)
class R3RouteResourceMetrics:
    worked_held_primitive_steps_per_sector: int
    peak_scratch_bytes: int


@dataclass(frozen=True, slots=True)
class R3RouteOwnerProjection:
    route_data_template: bytes
    route_prefixes: tuple[bytes, bytes, bytes, bytes]
    malformed_corpus: bytes
    reproduction_projection: bytes
    python_reproduction_receipt: bytes


_PROFILE_ROWS = (
    ("eh72-r2-crc32c-v0", 1, "eh72-replicated-v0", "crc32c-v0"),
    ("eh72-r2-crc64-ecma-v0", 2, "eh72-replicated-v0", "crc64-ecma-v0"),
    ("eh72-r3-crc32c-v0", 3, "eh72-replicated-v0", "crc32c-v0"),
    ("eh72-r3-crc64-ecma-v0", 4, "eh72-replicated-v0", "crc64-ecma-v0"),
    ("rs255-191-crc32c-v0", 5, "rs255-191-v0", "crc32c-v0"),
    ("rs255-191-crc64-ecma-v0", 6, "rs255-191-v0", "crc64-ecma-v0"),
)
_R3_PROFILE_ROW = (
    "eh72-hier-r5-r2-r1-crc32c-v0",
    7,
    "eh72-hier-repetition-v0",
    "crc32c-v0",
)

_FACT_ROWS = (
    (1, 0, "binary-relations-v0", ()),
    (2, 0, "entry-hypotheses-v0", (1,)),
    (3, 1, "unsigned-order-v0", (1,)),
    (4, 1, "row-major-msb-v0", (2, 3)),
    (5, 2, "route-recipe-framing-v0", (3, 4)),
    (6, 2, "recipe-language-status-bounds-v0", (5,)),
    (7, 3, "common-block-local-crc32c-v0", (6,)),
    (8, 3, "selected-transport-procedure-v0", (6, 7)),
    (9, 4, "affine-interior-inverse-v0", (6, 8)),
    (10, 4, "fragment-section-assembly-v0", (7, 8, 9)),
    (11, 5, "selected-section-check-inventory-v0", (10,)),
    (12, 5, "tier-frame-content-validation-v0", (11,)),
)


def _descriptor(value_type: int, width: int) -> ValueDescriptor:
    return ValueDescriptor(value_type, width)


def _hex_uint(value: int, width: int) -> str:
    return value.to_bytes((width + 7) // 8, "big").hex()


_RS_GENERATOR = bytes.fromhex(
    "01c10aff3a80b7738c99935bc5dbdddc8e1c7815a49306cc28e6b60e79308f4d"
    "e451552ba210c3a323959a2384646433b00ba186d084f4b0c0dde8ab7d9be4f2f5"
)


def _gf256_multiply(left: int, right: int) -> int:
    product = 0
    for _ in range(8):
        if right & 1:
            product ^= left
        carry = left & 0x80
        left = (left << 1) & 0xFF
        if carry:
            left ^= 0x1D
        right >>= 1
    return product


def _rs255_191_encode(source: bytes) -> bytes:
    """Exact bounded owner-side encoding used only to freeze fact-8 bytes."""

    if type(source) is not bytes or len(source) != 191:
        raise RouteDataError("rs-encoder-source")
    remainder = bytearray(source + bytes(64))
    for offset in range(191):
        factor = remainder[offset]
        if factor:
            for coefficient in range(1, 65):
                remainder[offset + coefficient] ^= _gf256_multiply(
                    factor, _RS_GENERATOR[coefficient]
                )
    return source + bytes(remainder[191:])


def _rs_common_source(profile_version: int, payload: bytes) -> bytes:
    return bootstrap.encode_common_block(
        bootstrap.CommonBlock(
            profile_version=profile_version,
            section_id=8,
            semantic_copy_id=0,
            section_type=3,
            section_version=0,
            fragment_index=0,
            fragment_count=1,
            section_envelope_length=157,
            payload=payload,
        )
    )


def _profile_examples(profile_version: int) -> dict[int, dict[str, object]]:
    profile = _PROFILE_ROWS[profile_version - 1]
    transport_id = profile[2]
    check_id = profile[3]
    if transport_id == "eh72-replicated-v0":
        transport_input_width = 8
        transport_output_width = 9
        transport_worked_input = bytes(8)
        transport_worked_output = bytes(9)
        transport_held_input = bytes.fromhex("0123456789abcdef")
        transport_held_output = bytes.fromhex("11121a2a9e26af36de")
        source_mask_mode = "whole-value-xor-v0"
        worked_sector_sources = tuple(
            bytes(value ^ mask for value in transport_worked_input)
            for mask in SECTOR_MASKS
        )
        held_sector_sources = tuple(
            bytes(value ^ mask for value in transport_held_input)
            for mask in SECTOR_MASKS
        )
        decoder_input_widths = (9, 1, 3)
        worked_damage_offset, worked_damage_xor = 0, 0x80
        held_damage_offset, held_damage_xor = 8, 0x01
    else:
        transport_input_width = 191
        transport_output_width = 255
        source_mask_mode = "common-block-payload-xor-recrc32c-v0"
        worked_payload = bytes(157)
        held_payload = bytes((73 * index + 41) & 0xFF for index in range(157))
        worked_sector_sources = tuple(
            _rs_common_source(
                profile_version,
                bytes(value ^ mask for value in worked_payload),
            )
            for mask in SECTOR_MASKS
        )
        held_sector_sources = tuple(
            _rs_common_source(
                profile_version,
                bytes(value ^ mask for value in held_payload),
            )
            for mask in SECTOR_MASKS
        )
        transport_worked_input = worked_sector_sources[0]
        transport_held_input = held_sector_sources[0]
        transport_worked_output = _rs255_191_encode(transport_worked_input)
        transport_held_output = _rs255_191_encode(transport_held_input)
        decoder_input_widths = (255, 1, 64)
        worked_damage_offset = 0
        held_damage_offset = 254
        worked_damage_xor = held_damage_xor = 0x53
    worked_observation = bytearray(transport_worked_output)
    worked_observation[worked_damage_offset] ^= worked_damage_xor
    held_observation = bytearray(transport_held_output)
    held_observation[held_damage_offset] ^= held_damage_xor
    erasure_capacity = decoder_input_widths[2]
    interior = 2_048 - 2 * 128
    population = interior * interior
    offset = (40_503 * profile_version + 128 * 257) % population
    held_physical = ((2 * interior - 1) * 123_456 + offset) % population
    check_width = 32 if check_id == "crc32c-v0" else 64
    check_worked = "e3069283" if check_width == 32 else "6c40df5f0b497347"
    check_held = "7144c5a8" if check_width == 32 else "07e3c1c7b567078b"
    return {
        1: {
            "inputs": ((bootstrap.BITS, 8),),
            "outputs": ((bootstrap.BITS, 8),),
            "mask": (1,),
            "worked": ("0f", "0000f0"),
            "held": ("96", "000069"),
        },
        2: {
            "inputs": (
                (bootstrap.UINT, 3), (bootstrap.BOOL, 1),
                (bootstrap.UINT, 16), (bootstrap.UINT, 16),
                (bootstrap.UINT, 16), (bootstrap.BOOL, 1),
            ),
            "outputs": ((bootstrap.UINT, 32), (bootstrap.BOOL, 1)),
            "mask": (6,),
            "worked": ("030100020005000800", "00000000002d01"),
            "held": ("050000010006000801", "00000000000e01"),
        },
        3: {
            "inputs": ((bootstrap.UINT, 16), (bootstrap.UINT, 16)),
            "outputs": ((bootstrap.BOOL, 1),),
            "mask": (1, 2),
            "worked": ("00010002", "000001"),
            "held": ("ffff0000", "000000"),
        },
        4: {
            "inputs": ((bootstrap.UINT, 16), (bootstrap.UINT, 16), (bootstrap.UINT, 16)),
            "outputs": ((bootstrap.UINT, 32),),
            "mask": (1, 2),
            "worked": ("000200030008", "000000000013"),
            "held": ("000700000008", "000000000038"),
        },
        5: {
            "inputs": ((bootstrap.UINT, 32),),
            "outputs": ((bootstrap.UINT, 32),),
            "mask": (1,),
            "worked": ("00000008", "000000000009"),
            "held": ("0000013f", "000000000140"),
        },
        6: {
            "inputs": ((bootstrap.UINT, 8),),
            "outputs": ((bootstrap.BOOL, 1),),
            "mask": (1,),
            "worked": ("00", "000001"),
            "held": ("0b", "000000"),
        },
        7: {
            "inputs": ((bootstrap.BYTES, 9),),
            "outputs": ((bootstrap.UINT, 32),),
            "mask": (1,),
            "worked": ("313233343536373839", "0000e3069283"),
            "held": ("000102030405060708", "00007144c5a8"),
        },
        8: {
            "inputs": tuple((bootstrap.BYTES, width) for width in decoder_input_widths),
            "outputs": ((bootstrap.BYTES, transport_input_width),),
            "mask": (1,),
            "source_inputs": ((bootstrap.BYTES, transport_input_width),),
            "worked_source": transport_worked_input.hex(),
            "held_source": transport_held_input.hex(),
            "source_mask_mode": source_mask_mode,
            "worked_sector_sources": tuple(item.hex() for item in worked_sector_sources),
            "held_sector_sources": tuple(item.hex() for item in held_sector_sources),
            "encoder_recipe_id": 108,
            "worked_damage_offset": worked_damage_offset,
            "worked_damage_xor": worked_damage_xor,
            "held_damage_offset": held_damage_offset,
            "held_damage_xor": held_damage_xor,
            "erasure_capacity": erasure_capacity,
            "worked": (
                bytes(worked_observation).hex() + "00" + bytes(erasure_capacity).hex(),
                "0000" + transport_worked_input.hex(),
            ),
            "held": (
                bytes(held_observation).hex() + "00" + bytes(erasure_capacity).hex(),
                "0000" + transport_held_input.hex(),
            ),
        },
        9: {
            "inputs": (
                (bootstrap.UINT, 32), (bootstrap.UINT, 16),
                (bootstrap.UINT, 16),
            ),
            "outputs": ((bootstrap.UINT, 32),),
            "mask": (1,),
            "worked": (
                "0000000008000080",
                "0000" + _hex_uint(offset, 32),
            ),
            "held": (
                "0001e24008000080",
                "0000" + _hex_uint(held_physical, 32),
            ),
        },
        10: {
            "inputs": ((bootstrap.UINT, 32), (bootstrap.UINT, 16)),
            "outputs": ((bootstrap.UINT, 48),),
            "mask": (1, 2),
            "worked": ("000000010000", "0000000000010000"),
            "held": ("010203040506", "0000010203040506"),
        },
        11: {
            "inputs": ((bootstrap.BYTES, 9),),
            "outputs": ((bootstrap.UINT, check_width),),
            "mask": (1,),
            "worked": ("313233343536373839", "0000" + check_worked),
            "held": ("000102030405060708", "0000" + check_held),
        },
        12: {
            "inputs": (
                (bootstrap.UINT, 16), (bootstrap.UINT, 16), (bootstrap.BOOL, 1),
            ),
            "outputs": ((bootstrap.BOOL, 1),),
            "mask": (3,),
            "worked": ("0040003f01", "000001"),
            "held": ("0001000201", "000000"),
        },
    }


def expected_route_data_manifest() -> dict[str, object]:
    """Return the closed canonical route-data owner as plain manifest values."""

    facts = []
    for fact_id, stage, name, consumes in _FACT_ROWS:
        value = name.encode("ascii")
        facts.append(
            {
                "consumes": list(consumes),
                "definition": {
                    "count": 1,
                    "type": bootstrap.BYTES,
                    "value_hex": value.hex(),
                    "value_id": fact_id,
                    "width": len(value),
                },
                "fact_id": fact_id,
                "name": name,
                "recipe_id": 30 if fact_id == 8 else 100 + fact_id,
                "stage": stage,
            }
        )
    def example_row(fact_id: int, item: dict[str, object]) -> dict[str, object]:
        return {
            "fact_id": fact_id,
            "held_input_hex": item["held"][0],
            "held_output_hex": item["held"][1],
            "inputs": [
                {"type": value_type, "width": width}
                for value_type, width in item["inputs"]
            ],
            "mask_input_slots": list(item["mask"]),
            "outputs": [
                {"type": value_type, "width": width}
                for value_type, width in item["outputs"]
            ],
            "recipe_id": 30 if fact_id == 8 else 100 + fact_id,
            "worked_input_hex": item["worked"][0],
            "worked_output_hex": item["worked"][1],
        } | (
            {
                "encoder_recipe_id": item["encoder_recipe_id"],
                "erasure_capacity": item["erasure_capacity"],
                "held_damage_offset": item["held_damage_offset"],
                "held_damage_xor": item["held_damage_xor"],
                "held_source_hex": item["held_source"],
                "held_sector_sources_hex": list(item["held_sector_sources"]),
                "source_mask_mode": item["source_mask_mode"],
                "source_inputs": [
                    {"type": value_type, "width": width}
                    for value_type, width in item["source_inputs"]
                ],
                "worked_damage_offset": item["worked_damage_offset"],
                "worked_damage_xor": item["worked_damage_xor"],
                "worked_source_hex": item["worked_source"],
                "worked_sector_sources_hex": list(item["worked_sector_sources"]),
            }
            if "encoder_recipe_id" in item
            else {}
        )

    profile_examples = tuple(_profile_examples(version) for version in range(1, 7))
    common_fact_ids = (1, 2, 3, 4, 5, 6, 7, 10, 12)
    examples = {
        "common": [example_row(fact_id, profile_examples[0][fact_id]) for fact_id in common_fact_ids],
        "mapping": [
            {"profile_version": version, "value": example_row(9, profile_examples[version - 1][9])}
            for version in range(1, 7)
        ],
        "section_check": [
            {"section_check_id": check_id, "value": example_row(11, profile_examples[index][11])}
            for check_id, index in (("crc32c-v0", 0), ("crc64-ecma-v0", 1))
        ],
        "transport": [
            {
                "profile_version": version,
                "transport_id": _PROFILE_ROWS[version - 1][2],
                "value": example_row(8, profile_examples[version - 1][8]),
            }
            for version in range(1, 7)
        ],
    }
    profiles = []
    for profile_id, version, transport_id, check_id in _PROFILE_ROWS:
        profiles.append(
            {
                "profile_id": profile_id,
                "profile_version": version,
                "section_check_id": check_id,
                "transport_id": transport_id,
            }
        )
    return {
        "calibration_hex": [item.hex() for item in CALIBRATIONS],
        "discriminator_cells": DISCRIMINATOR_CELLS,
        "examples": examples,
        "facts": facts,
        "profiles": profiles,
        "recipe_export_ids": [30] + list(range(EXPORTED_RECIPE_FIRST, EXPORTED_RECIPE_LAST + 1)),
        "route_version": ROUTE_VERSION,
        "schema": "golden-board.route-data/v0",
        "sector_capacity_bytes": SECTOR_CAPACITY_BYTES,
        "sector_masks_hex": [f"{item:02x}" for item in SECTOR_MASKS],
        "side": SECTOR_SIDE,
        "shell_width": SHELL_WIDTH,
    }


def render_route_data_manifest() -> bytes:
    return canonical_manifest.serialize_manifest(expected_route_data_manifest())


def expected_r3_route_data_template(
    owner_fixture_raw: bytes,
) -> dict[str, object]:
    """Return the exact incomplete v1 owner template before generated facts."""

    try:
        owner_fixture = canonical_manifest.validate_canonical_manifest(
            owner_fixture_raw
        )
    except (TypeError, canonical_manifest.ManifestError) as error:
        raise RouteDataError("owner-fixture") from error
    if owner_fixture.get("schema") != "golden-board.m2-r3-owner-fixtures/v1":
        raise RouteDataError("owner-fixture")
    root = deepcopy(expected_route_data_manifest())
    root["schema"] = "golden-board.route-data/v1"
    root["route_version"] = 1
    root["side"] = R3_SECTOR_SIDE
    root["shell_width"] = R3_SHELL_WIDTH
    root["sector_capacity_bytes"] = R3_SECTOR_CAPACITY_BYTES
    root["recipe_export_ids"] = [30] + list(range(101, 114))
    root["profiles"] = [
        {
            "candidate": True,
            "fixture": False,
            "profile_id": _R3_PROFILE_ROW[0],
            "profile_version": 7,
            "section_check_id": "crc32c-v0",
            "transport_id": "eh72-hier-repetition-v0",
        },
        *(
            {
                "candidate": False,
                "fixture": True,
                "profile_id": profile_id,
                "profile_version": version,
                "section_check_id": check_id,
                "transport_id": transport_id,
            }
            for profile_id, version, transport_id, check_id in _PROFILE_ROWS[1:]
        ),
    ]
    deltas = {
        8: ("eh72-hier-repetition-v1", [6, 7], 113),
        9: ("slot-affine-adapter-v1", [6, 8], 109),
        10: ("group-fragment-adapter-v1", [7, 8, 9], 110),
    }
    for fact in root["facts"]:
        if fact["fact_id"] not in deltas:
            continue
        name, consumes, recipe_id = deltas[fact["fact_id"]]
        fact["name"] = name
        fact["consumes"] = consumes
        fact["recipe_id"] = recipe_id
        fact["definition"]["width"] = len(name)
        fact["definition"]["value_hex"] = name.encode("ascii").hex()
    old_examples = root["examples"]
    mapping = deepcopy(
        next(
            row
            for row in old_examples["mapping"]
            if row["profile_version"] == 1
        )
    )
    mapping["profile_version"] = 7
    mapping["value"]["worked_output_hex"] = "00000004d401"
    mapping["value"]["held_output_hex"] = "0000002971c1"
    section_check = deepcopy(
        next(
            row
            for row in old_examples["section_check"]
            if row["section_check_id"] == "crc32c-v0"
        )
    )
    root["examples"] = {
        "common": old_examples["common"],
        "mapping": [mapping],
        "owner_fixture": {
            "path": "conformance/m2-r3-owner-v1.json",
            "schema": "golden-board.m2-r3-owner-fixtures/v1",
            "sha256": sha256(owner_fixture_raw).hexdigest(),
        },
        "section_check": [section_check],
        "transport": [
            {
                "fact_id": 8,
                "held_sector_inputs_hex": [
                    "050203",
                    "020001",
                    "050001",
                    "050202",
                ],
                "held_sector_outputs_hex": [
                    "00000101",
                    "00000101",
                    "00000101",
                    "00000000",
                ],
                "inputs": [
                    {"type": bootstrap.UINT, "width": 8},
                    {"type": bootstrap.UINT, "width": 8},
                    {"type": bootstrap.UINT, "width": 8},
                ],
                "mask_input_slots": [],
                "outputs": [
                    {"type": bootstrap.BOOL, "width": 1},
                    {"type": bootstrap.BOOL, "width": 1},
                ],
                "profile_version": 7,
                "recipe_id": 113,
                "support_recipe_ids": [30, 108],
                "transport_id": "eh72-hier-repetition-v0",
                "worked_sector_inputs_hex": [
                    "050302",
                    "020100",
                    "050100",
                    "020101",
                ],
                "worked_sector_outputs_hex": [
                    "00000100",
                    "00000100",
                    "00000100",
                    "00000000",
                ],
            }
        ],
    }
    root["generated"] = {}
    return root


def render_r3_route_data_template(owner_fixture_raw: bytes) -> bytes:
    return canonical_manifest.serialize_manifest(
        expected_r3_route_data_template(owner_fixture_raw)
    )


def load_route_data_manifest(raw: bytes) -> tuple[tuple[FactTemplate, ...], ...]:
    """Admit only the exact tracked route-data owner and project its profiles."""

    try:
        value = canonical_manifest.validate_canonical_manifest(raw)
    except canonical_manifest.ManifestError as error:
        raise RouteDataError("manifest-canonical") from error
    if raw != render_route_data_manifest() or value.get("schema") != "golden-board.route-data/v0":
        raise RouteDataError("manifest-drift")
    return _project_manifest(value)


def lint_route_data_manifest(raw: bytes) -> tuple[tuple[FactTemplate, ...], ...]:
    """Lint a canonical template, including ablations, without exact-owner admission."""

    try:
        value = canonical_manifest.validate_canonical_manifest(raw)
    except canonical_manifest.ManifestError as error:
        raise RouteDataError("manifest-canonical") from error
    if value.get("schema") != "golden-board.route-data/v0":
        raise RouteDataError("manifest-schema")
    try:
        return _project_manifest(value)
    except (KeyError, TypeError, ValueError, IndexError) as error:
        if isinstance(error, RouteDataError):
            raise
        raise RouteDataError("manifest-shape") from error


def _project_manifest(value: dict[str, object]) -> tuple[tuple[FactTemplate, ...], ...]:
    result = []
    facts = value["facts"]
    catalog = value["examples"]
    common = {item["fact_id"]: item for item in catalog["common"]}
    transports = {item["profile_version"]: item["value"] for item in catalog["transport"]}
    checks = {item["section_check_id"]: item["value"] for item in catalog["section_check"]}
    mappings = {item["profile_version"]: item["value"] for item in catalog["mapping"]}
    for profile in value["profiles"]:
        examples = dict(common)
        examples[8] = transports[profile["profile_version"]]
        examples[9] = mappings[profile["profile_version"]]
        examples[11] = checks[profile["section_check_id"]]
        projected = []
        for fact in facts:
            example = examples[fact["fact_id"]]
            definition = fact["definition"]
            projected.append(
                FactTemplate(
                    fact["fact_id"],
                    fact["stage"],
                    fact["name"],
                    tuple(fact["consumes"]),
                    _descriptor(definition["type"], definition["width"]),
                    bytes.fromhex(definition["value_hex"]),
                    example["recipe_id"],
                    tuple(_descriptor(item["type"], item["width"]) for item in example["inputs"]),
                    tuple(_descriptor(item["type"], item["width"]) for item in example["outputs"]),
                    tuple(example["mask_input_slots"]),
                    tuple(
                        _descriptor(item["type"], item["width"])
                        for item in example.get("source_inputs", example["inputs"])
                    ),
                    bytes.fromhex(example.get("worked_source_hex", example["worked_input_hex"])),
                    bytes.fromhex(example.get("held_source_hex", example["held_input_hex"])),
                    example.get("source_mask_mode"),
                    tuple(
                        bytes.fromhex(item)
                        for item in example.get("worked_sector_sources_hex", ())
                    ),
                    tuple(
                        bytes.fromhex(item)
                        for item in example.get("held_sector_sources_hex", ())
                    ),
                    example.get("encoder_recipe_id"),
                    example.get("worked_damage_offset"),
                    example.get("worked_damage_xor"),
                    example.get("held_damage_offset"),
                    example.get("held_damage_xor"),
                    example.get("erasure_capacity"),
                    bytes.fromhex(example["worked_input_hex"]),
                    bytes.fromhex(example["worked_output_hex"]),
                    bytes.fromhex(example["held_input_hex"]),
                    bytes.fromhex(example["held_output_hex"]),
                )
            )
        result.append(tuple(projected))
    projected_profiles = tuple(result)
    _validate_template(projected_profiles)
    return projected_profiles


def _validate_template(profiles: tuple[tuple[FactTemplate, ...], ...]) -> None:
    if len(profiles) != 6:
        raise RouteDataError("template-profiles")
    reference_definitions = tuple(
        (item.fact_id, item.stage, item.name, item.consumes, item.definition, item.definition_value)
        for item in profiles[0]
    )
    for profile_version, facts in enumerate(profiles, start=1):
        if len(facts) != 12 or tuple(item.fact_id for item in facts) != tuple(range(1, 13)):
            raise RouteDataError("template-facts")
        if tuple(item.recipe_id for item in facts) != (101, 102, 103, 104, 105, 106, 107, 30, 109, 110, 111, 112):
            raise RouteDataError("template-recipes")
        if tuple(
            (item.fact_id, item.stage, item.name, item.consumes, item.definition, item.definition_value)
            for item in facts
        ) != reference_definitions:
            raise RouteDataError("template-definition-drift")
        defined: set[int] = set()
        for item in facts:
            if any(dependency not in defined for dependency in item.consumes):
                raise RouteDataError(f"knowledge-use:{item.fact_id}")
            defined.add(item.fact_id)
            if not item.mask_input_slots or len(set(item.mask_input_slots)) != len(item.mask_input_slots):
                raise RouteDataError(f"mask-slots:{item.fact_id}")
            if any(not 1 <= slot <= len(item.inputs) for slot in item.mask_input_slots):
                raise RouteDataError(f"mask-slots:{item.fact_id}")
            if any(not 1 <= slot <= len(item.source_inputs) for slot in item.mask_input_slots):
                raise RouteDataError(f"source-mask-slots:{item.fact_id}")
            _validate_value(item.definition_value, item.definition, f"definition:{item.fact_id}")
            for label, raw, descriptors in (
                ("worked-input", item.worked_input, item.inputs),
                ("held-input", item.held_input, item.inputs),
                ("worked-output", item.worked_output, (_descriptor(bootstrap.STATUS, 16),) + item.outputs),
                ("held-output", item.held_output, (_descriptor(bootstrap.STATUS, 16),) + item.outputs),
            ):
                _split_values(raw, descriptors, f"{label}:{item.fact_id}")
            if item.worked_input == item.held_input or item.worked_output[:2] != b"\0\0" or item.held_output[:2] != b"\0\0":
                raise RouteDataError(f"examples:{item.fact_id}")
            _split_values(item.worked_source, item.source_inputs, f"worked-source:{item.fact_id}")
            _split_values(item.held_source, item.source_inputs, f"held-source:{item.fact_id}")
            for sector, mask in enumerate(SECTOR_MASKS):
                if item.encoder_recipe_id is None:
                    worked = _mask_input(
                        item.worked_source, item.source_inputs, item.mask_input_slots, mask
                    )
                    held = _mask_input(
                        item.held_source, item.source_inputs, item.mask_input_slots, mask
                    )
                else:
                    if (
                        len(item.worked_sector_sources) != 4
                        or len(item.held_sector_sources) != 4
                        or item.worked_sector_sources[0] != item.worked_source
                        or item.held_sector_sources[0] != item.held_source
                    ):
                        raise RouteDataError("transport-sector-sources")
                    worked = item.worked_sector_sources[sector]
                    held = item.held_sector_sources[sector]
                if worked == held:
                    raise RouteDataError(f"masked-example-collision:{item.fact_id}")
            if item.encoder_recipe_id is not None:
                if (
                    item.fact_id != 8
                    or item.encoder_recipe_id != 108
                    or item.erasure_capacity not in (3, 64)
                    or any(
                        type(value) is not int or value < 0
                        for value in (
                            item.worked_damage_offset,
                            item.worked_damage_xor,
                            item.held_damage_offset,
                            item.held_damage_xor,
                        )
                    )
                ):
                    raise RouteDataError("transport-preprocessing")
                if profile_version <= 4:
                    if item.source_mask_mode != "whole-value-xor-v0":
                        raise RouteDataError("transport-source-mask-mode")
                    for sector, mask in enumerate(SECTOR_MASKS):
                        for canonical, observed in (
                            (item.worked_source, item.worked_sector_sources[sector]),
                            (item.held_source, item.held_sector_sources[sector]),
                        ):
                            if observed != _mask_input(
                                canonical, item.source_inputs, item.mask_input_slots, mask
                            ):
                                raise RouteDataError("transport-sector-source-mask")
                else:
                    if item.source_mask_mode != "common-block-payload-xor-recrc32c-v0":
                        raise RouteDataError("transport-source-mask-mode")
                    for canonical, sources in (
                        (item.worked_source, item.worked_sector_sources),
                        (item.held_source, item.held_sector_sources),
                    ):
                        try:
                            canonical_block = bootstrap.decode_common_block(
                                canonical, profile_version
                            )
                        except bootstrap.BootstrapError as error:
                            raise RouteDataError("transport-common-source") from error
                        if len(canonical_block.payload) != 157:
                            raise RouteDataError("transport-common-payload")
                        for sector, mask in enumerate(SECTOR_MASKS):
                            observed = sources[sector]
                            try:
                                observed_block = bootstrap.decode_common_block(
                                    observed, profile_version
                                )
                            except bootstrap.BootstrapError as error:
                                raise RouteDataError("transport-common-source") from error
                            if (
                                observed[:30] != canonical[:30]
                                or observed_block != bootstrap.CommonBlock(
                                    canonical_block.profile_version,
                                    canonical_block.section_id,
                                    canonical_block.semantic_copy_id,
                                    canonical_block.section_type,
                                    canonical_block.section_version,
                                    canonical_block.fragment_index,
                                    canonical_block.fragment_count,
                                    canonical_block.section_envelope_length,
                                    bytes(value ^ mask for value in canonical_block.payload),
                                )
                            ):
                                raise RouteDataError("transport-common-source-mask")
                    for source, encoded_input, damage_offset, damage_xor in (
                        (
                            item.worked_source,
                            item.worked_input,
                            item.worked_damage_offset,
                            item.worked_damage_xor,
                        ),
                        (
                            item.held_source,
                            item.held_input,
                            item.held_damage_offset,
                            item.held_damage_xor,
                        ),
                    ):
                        observation = bytearray(_rs255_191_encode(source))
                        observation[damage_offset] ^= damage_xor
                        expected_input = bytes(observation) + bytes(65)
                        if encoded_input != expected_input:
                            raise RouteDataError("transport-canonical-preprocessing")
            elif (
                item.source_mask_mode is not None
                or item.worked_sector_sources
                or item.held_sector_sources
            ):
                raise RouteDataError("unexpected-sector-sources")
    used = {dependency for row in reference_definitions for dependency in row[3]}
    if used | {12} != set(range(1, 13)):
        raise RouteDataError("unused-definition")
    reachable = {12}
    changed = True
    while changed:
        changed = False
        for fact_id, _, _, consumes, _, _ in reference_definitions:
            if fact_id in reachable:
                for dependency in consumes:
                    if dependency not in reachable:
                        reachable.add(dependency)
                        changed = True
    if reachable != set(range(1, 13)):
        raise RouteDataError("endpoint-unreachable")


def _validate_value(raw: bytes, descriptor: ValueDescriptor, path: str) -> None:
    if len(raw) != descriptor.encoded_bytes:
        raise RouteDataError(path)
    value = int.from_bytes(raw, "big")
    if descriptor.value_type == bootstrap.BYTES:
        return
    if descriptor.value_type == bootstrap.BITS:
        unused = len(raw) * 8 - descriptor.width
        if unused and value & ((1 << unused) - 1):
            raise RouteDataError(path)
        return
    if descriptor.value_type == bootstrap.BOOL:
        if descriptor.width != 1 or value > 1:
            raise RouteDataError(path)
        return
    if descriptor.value_type == bootstrap.STATUS:
        if descriptor.width != 16 or value > 14:
            raise RouteDataError(path)
        return
    if descriptor.value_type != bootstrap.UINT or not 1 <= descriptor.width <= 64 or value >= 1 << descriptor.width:
        raise RouteDataError(path)


def _split_values(raw: bytes, descriptors: Sequence[ValueDescriptor], path: str) -> tuple[bytes, ...]:
    values = []
    offset = 0
    for index, descriptor in enumerate(descriptors):
        end = offset + descriptor.encoded_bytes
        if end > len(raw):
            raise RouteDataError(path)
        item = raw[offset:end]
        _validate_value(item, descriptor, f"{path}:{index + 1}")
        values.append(item)
        offset = end
    if offset != len(raw):
        raise RouteDataError(path)
    return tuple(values)


def _mask_input(
    raw: bytes,
    descriptors: Sequence[ValueDescriptor],
    mask_slots: Sequence[int],
    mask: int,
) -> bytes:
    values = list(_split_values(raw, descriptors, "mask-input"))
    for slot in mask_slots:
        descriptor = descriptors[slot - 1]
        original = values[slot - 1]
        repeated = bytes((mask,)) * len(original)
        if descriptor.value_type == bootstrap.BITS:
            unused = len(original) * 8 - descriptor.width
            if unused:
                repeated = repeated[:-1] + bytes((repeated[-1] & (0xFF << unused),))
            values[slot - 1] = bytes(left ^ right for left, right in zip(original, repeated, strict=True))
        elif descriptor.value_type in (bootstrap.UINT, bootstrap.BOOL, bootstrap.STATUS):
            number = int.from_bytes(original, "big")
            mask_number = int.from_bytes(repeated, "big") & ((1 << descriptor.width) - 1)
            values[slot - 1] = (number ^ mask_number).to_bytes(len(original), "big")
        else:
            values[slot - 1] = bytes(left ^ right for left, right in zip(original, repeated, strict=True))
    return b"".join(values)


def _expected_nontransport_output(
    profile_version: int, fact: FactTemplate, recipe_input: bytes
) -> bytes:
    """Derive one common-fact result without consulting its recipe package."""

    values = _split_values(recipe_input, fact.inputs, "expected-input")
    numbers = tuple(int.from_bytes(value, "big") for value in values)
    if fact.fact_id == 1:
        outputs = ((numbers[0] ^ 0xFF).to_bytes(1, "big"),)
    elif fact.fact_id == 2:
        transform, polarity, row, column, side, observed = numbers
        if side == 0 or row >= side or column >= side:
            raise RouteDataError("expected-transform-domain")
        last = side - 1
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
        mapped_row, mapped_column = coordinates[transform]
        outputs = (
            (mapped_row * side + mapped_column).to_bytes(4, "big"),
            bytes((observed ^ polarity,)),
        )
    elif fact.fact_id == 3:
        outputs = (bytes((numbers[0] < numbers[1],)),)
    elif fact.fact_id == 4:
        outputs = ((numbers[0] * numbers[2] + numbers[1]).to_bytes(4, "big"),)
    elif fact.fact_id == 5:
        outputs = ((numbers[0] + 1).to_bytes(4, "big"),)
    elif fact.fact_id == 6:
        outputs = (bytes((numbers[0] == 0,)),)
    elif fact.fact_id == 7:
        outputs = (bootstrap.crc32c_v0(values[0]).to_bytes(4, "big"),)
    elif fact.fact_id == 8 and fact.recipe_id == 113:
        factor, zero_count, one_count = numbers
        if factor not in (2, 5) or zero_count + one_count > factor:
            raise RouteDataError("expected-repetition-domain")
        outputs = (
            bytes((zero_count != one_count,)),
            bytes((zero_count < one_count,)),
        )
    elif fact.fact_id == 9:
        logical, side, shell_width = numbers
        if not 0 < side <= 2_048 or 2 * shell_width >= side:
            raise RouteDataError("expected-mapping-domain")
        interior = side - 2 * shell_width
        population = interior * interior
        offset = (40_503 * profile_version + shell_width * 257) % population
        physical = ((2 * interior - 1) * (logical % population) + offset) % population
        outputs = (physical.to_bytes(4, "big"),)
    elif fact.fact_id == 10:
        outputs = (values[0] + values[1],)
    elif fact.fact_id == 11:
        width = fact.outputs[0].width
        check = (
            bootstrap.crc32c_v0(values[0])
            if width == 32
            else bootstrap.crc64_ecma_v0(values[0])
        )
        outputs = (check.to_bytes(width // 8, "big"),)
    elif fact.fact_id == 12:
        expected_count, available_count, valid = numbers
        outputs = (
            bytes(
                (
                    available_count < 0xFFFF
                    and expected_count == available_count + 1
                    and valid == 1,
                )
            ),
        )
    else:
        raise RouteDataError(f"expected-fact:{fact.fact_id}")
    expected_shapes = tuple(
        descriptor.encoded_bytes for descriptor in fact.outputs
    )
    if tuple(map(len, outputs)) != expected_shapes:
        raise RouteDataError(f"expected-shape:{fact.fact_id}")
    return b"\0\0" + b"".join(outputs)


def _be(value: int, width: int) -> bytes:
    if type(value) is not int or not 0 <= value < 1 << (8 * width):
        raise RouteDataError("integer-range")
    return value.to_bytes(width, "big")


def _descriptor_wire(value_id: int, descriptor: ValueDescriptor) -> bytes:
    return b"".join((_be(value_id, 2), bytes((descriptor.value_type, 0)), _be(descriptor.width, 4), _be(1, 4)))


def _table_wire(table: bootstrap.RecipeTable) -> bytes:
    return b"".join(
        (
            _be(table.table_id, 2), bytes((table.element_type, 0)),
            _be(table.element_width, 4), _be(table.element_count, 4),
            _be(len(table.payload), 4), table.payload,
        )
    )


def _record(stage: int, kind: int, record_id: int, payload: bytes) -> bytes:
    return bytes((stage, kind)) + _be(record_id, 2) + _be(len(payload), 4) + payload


def _validated_packages(candidate: CandidateRouteData) -> tuple[bootstrap.RecipePackage, ...]:
    if (
        type(candidate.profile_id) is not str
        or type(candidate.profile_version) is not int
        or type(candidate.transport_id) is not str
        or type(candidate.section_check_id) is not str
    ):
        raise RouteDataError("candidate-shape")
    expected = (
        _R3_PROFILE_ROW
        if candidate.profile_version == 7
        else _PROFILE_ROWS[candidate.profile_version - 1]
        if 1 <= candidate.profile_version <= 6
        else None
    )
    if expected != (candidate.profile_id, candidate.profile_version, candidate.transport_id, candidate.section_check_id):
        raise RouteDataError("candidate-identity")
    if type(candidate.recipe_packages) is not tuple or not candidate.recipe_packages:
        raise RouteDataError("candidate-packages")
    packages = []
    recipe_ids: set[int] = set()
    table_ids: set[int] = set()
    for raw in candidate.recipe_packages:
        if type(raw) is not bytes:
            raise RouteDataError("candidate-package-type")
        try:
            package = bootstrap.decode_recipe_package(raw, candidate.profile_version)
        except bootstrap.BootstrapError as error:
            raise RouteDataError("candidate-package") from error
        for recipe in package.recipes:
            if recipe.recipe_id in recipe_ids:
                raise RouteDataError("duplicate-recipe-id")
            recipe_ids.add(recipe.recipe_id)
        for table in package.tables:
            if table.table_id in table_ids:
                raise RouteDataError("duplicate-table-id")
            table_ids.add(table.table_id)
        packages.append(package)
    required = {30} | set(range(101, 114 if candidate.profile_version == 7 else 113))
    if not required.issubset(recipe_ids):
        raise RouteDataError("missing-exported-recipe")
    return tuple(sorted(packages, key=lambda item: (item.recipes[0].recipe_id, sha256(item.encoded).digest())))


def _recipe_index(packages: Sequence[bootstrap.RecipePackage]) -> dict[int, tuple[bootstrap.RecipePackage, bootstrap.Recipe]]:
    return {recipe.recipe_id: (package, recipe) for package in packages for recipe in package.recipes}


def _check_examples(
    facts: Sequence[FactTemplate],
    recipes: dict[int, tuple[bootstrap.RecipePackage, bootstrap.Recipe]],
    mask: int,
) -> tuple[tuple[bytes, bytes], ...]:
    try:
        sector = SECTOR_MASKS.index(mask)
    except ValueError as error:
        raise RouteDataError("sector-mask") from error
    result = []
    for fact in facts:
        package, recipe = recipes[fact.recipe_id]
        observed_inputs = tuple((item.value_type, item.width) for item in recipe.inputs)
        observed_outputs = tuple((item.value_type, item.width) for item in recipe.outputs[1:])
        expected_inputs = tuple((item.value_type, item.width) for item in fact.inputs)
        expected_outputs = tuple((item.value_type, item.width) for item in fact.outputs)
        if observed_inputs != expected_inputs or observed_outputs != expected_outputs:
            raise RouteDataError(f"recipe-interface:{fact.fact_id}")
        rows = []
        for label, canonical_source, canonical_input, canonical_output, damage_offset, damage_xor in (
            (
                "worked", fact.worked_source, fact.worked_input,
                fact.worked_output, fact.worked_damage_offset, fact.worked_damage_xor,
            ),
            (
                "held", fact.held_source, fact.held_input,
                fact.held_output, fact.held_damage_offset, fact.held_damage_xor,
            ),
        ):
            if fact.encoder_recipe_id is None and not fact.worked_sector_sources:
                masked_source = _mask_input(
                    canonical_source, fact.source_inputs, fact.mask_input_slots, mask
                )
            else:
                sector_sources = (
                    fact.worked_sector_sources
                    if label == "worked"
                    else fact.held_sector_sources
                )
                if len(sector_sources) != 4:
                    raise RouteDataError("transport-sector-sources")
                masked_source = sector_sources[sector]
            if fact.encoder_recipe_id is None:
                recipe_input = masked_source
            else:
                encoder_package, encoder = recipes[fact.encoder_recipe_id]
                source_shapes = tuple(
                    (item.value_type, item.width) for item in fact.source_inputs
                )
                encoder_inputs = tuple(
                    (item.value_type, item.width) for item in encoder.inputs
                )
                encoder_outputs = tuple(
                    (item.value_type, item.width) for item in encoder.outputs[1:]
                )
                observation_width = fact.inputs[0].width
                if (
                    encoder_inputs != source_shapes
                    or encoder_outputs != ((bootstrap.BYTES, observation_width),)
                    or damage_offset is None
                    or damage_xor is None
                    or fact.erasure_capacity is None
                    or not 0 <= damage_offset < observation_width
                    or not 1 <= damage_xor <= 0xFF
                ):
                    raise RouteDataError("transport-preprocessing")
                encoded = bootstrap.evaluate_recipe(
                    encoder_package,
                    fact.encoder_recipe_id,
                    _split_values(masked_source, fact.source_inputs, "encoder-input"),
                )
                if encoded.status != 0 or len(encoded.outputs) != 1:
                    raise RouteDataError("encoder-example-status")
                observation = bytearray(encoded.outputs[0])
                observation[damage_offset] ^= damage_xor
                recipe_input = (
                    bytes(observation) + b"\0" + bytes(fact.erasure_capacity)
                )
            input_values = _split_values(recipe_input, fact.inputs, f"{label}-input:{fact.fact_id}")
            evaluated = bootstrap.evaluate_recipe(package, fact.recipe_id, input_values)
            actual_output = _be(evaluated.status, 2) + b"".join(evaluated.outputs)
            if evaluated.status != 0:
                raise RouteDataError(f"masked-example-status:{fact.fact_id}:{mask:02x}")
            if fact.encoder_recipe_id is None:
                expected_output = _expected_nontransport_output(
                    package.profile_version, fact, recipe_input
                )
                if actual_output != expected_output:
                    raise RouteDataError(
                        f"independent-example:{fact.fact_id}:{label}:{mask:02x}"
                    )
                actual_output = expected_output
            if mask == 0 and actual_output != canonical_output:
                raise RouteDataError(f"canonical-example:{fact.fact_id}:{label}")
            if mask == 0 and recipe_input != canonical_input:
                raise RouteDataError(f"canonical-preprocessing:{fact.fact_id}:{label}")
            if actual_output != b"\0\0" + masked_source:
                if fact.encoder_recipe_id is not None:
                    raise RouteDataError(f"recovery-example:{fact.fact_id}:{label}")
            rows.append((recipe_input, actual_output))
        result.append((rows[0], rows[1]))
    return tuple(result)


def _build_records(
    sector_id: int,
    facts: Sequence[FactTemplate],
    packages: Sequence[bootstrap.RecipePackage],
    examples: Sequence[tuple[tuple[bytes, bytes], tuple[bytes, bytes]]],
) -> tuple[bytes, tuple[tuple[str, int], ...]]:
    base = sector_id * 10_000
    records: list[bytes] = []
    owners: list[tuple[str, int]] = []
    for fact, (worked, held) in zip(facts, examples, strict=True):
        define_payload = _be(fact.fact_id, 2) + _descriptor_wire(fact.fact_id, fact.definition) + fact.definition_value
        define = _record(fact.stage, 1, base + 100 * fact.fact_id + 1, define_payload)
        worked_payload = _be(fact.fact_id, 2) + _be(fact.recipe_id, 2) + _be(len(worked[0]), 4) + _be(len(worked[1]), 4) + worked[0] + worked[1]
        worked_record = _record(fact.stage, 2, base + 100 * fact.fact_id + 2, worked_payload)
        held_payload = _be(fact.fact_id, 2) + _be(fact.recipe_id, 2) + _be(len(held[0]), 4) + _be(len(held[1]), 4) + held[0] + held[1]
        held_record = _record(fact.stage, 3, base + 100 * fact.fact_id + 3, held_payload)
        for name, encoded in ((f"define:{fact.fact_id}", define), (f"worked:{fact.fact_id}", worked_record), (f"held-out:{fact.fact_id}", held_record)):
            records.append(encoded)
            owners.append((name, len(encoded) * 8))
    tables = sorted((table for package in packages for table in package.tables), key=lambda item: item.table_id)
    for ordinal, table in enumerate(tables, 1):
        encoded = _record(5, 4, base + 5_000 + ordinal, _table_wire(table))
        records.append(encoded)
        owners.append((f"table:{table.table_id}", len(encoded) * 8))
    for ordinal, package in enumerate(packages, 1):
        encoded = _record(5, 5, base + 6_000 + ordinal, package.encoded)
        records.append(encoded)
        owners.append((f"recipe-package:{ordinal}", len(encoded) * 8))
    endpoint = _record(5, 6, base + 7_001, _be(1, 4))
    end = _record(5, 7, base + 7_002, b"")
    records.extend((endpoint, end))
    owners.extend((("endpoint", len(endpoint) * 8), ("end", len(end) * 8)))
    if not 37 <= len(records) <= 256:
        raise RouteDataError("record-count")
    if len(tables) > 1_000 or len(packages) > 1_000:
        raise RouteDataError("record-id-range")
    return b"".join(records), tuple(owners)


def _pad_bits(profile_version: int, sector_id: int, count: int) -> tuple[int, ...]:
    result: list[int] = []
    counter = 0
    while len(result) < count:
        digest = sha256(PAD_DOMAIN + _be(profile_version, 2) + bytes((sector_id,)) + _be(counter, 8)).digest()
        for byte in digest:
            result.extend((byte >> shift) & 1 for shift in range(7, -1, -1))
        counter += 1
    return tuple(result[:count])


def _bytes_to_bits(raw: bytes) -> list[int]:
    return [(byte >> shift) & 1 for byte in raw for shift in range(7, -1, -1)]


def _bits_to_bytes(bits: Sequence[int]) -> bytes:
    if len(bits) % 8:
        raise RouteDataError("bit-alignment")
    result = bytearray()
    for offset in range(0, len(bits), 8):
        value = 0
        for bit in bits[offset : offset + 8]:
            value = (value << 1) | bit
        result.append(value)
    return bytes(result)


def r3_route_facts() -> tuple[FactTemplate, ...]:
    """Project the v7 fact graph from the inherited v0 owner and exact delta."""

    inherited = list(_project_manifest(expected_route_data_manifest())[0])
    repetition_inputs = ((bootstrap.UINT, 8),) * 3
    repetition_outputs = ((bootstrap.BOOL, 1),) * 2
    worked_inputs = tuple(
        bytes.fromhex(value)
        for value in ("050302", "020100", "050100", "020101")
    )
    worked_outputs = tuple(
        bytes.fromhex(value)
        for value in ("00000100", "00000100", "00000100", "00000000")
    )
    held_inputs = tuple(
        bytes.fromhex(value)
        for value in ("050203", "020001", "050001", "050202")
    )
    held_outputs = tuple(
        bytes.fromhex(value)
        for value in ("00000101", "00000101", "00000101", "00000000")
    )
    name = "eh72-hier-repetition-v1"
    inherited[7] = replace(
        inherited[7],
        name=name,
        consumes=(6, 7),
        definition=_descriptor(bootstrap.BYTES, len(name)),
        definition_value=name.encode("ascii"),
        recipe_id=113,
        inputs=tuple(_descriptor(*item) for item in repetition_inputs),
        outputs=tuple(_descriptor(*item) for item in repetition_outputs),
        mask_input_slots=(),
        source_inputs=tuple(_descriptor(*item) for item in repetition_inputs),
        worked_source=worked_inputs[0],
        held_source=held_inputs[0],
        source_mask_mode=None,
        worked_sector_sources=worked_inputs,
        held_sector_sources=held_inputs,
        encoder_recipe_id=None,
        worked_damage_offset=None,
        worked_damage_xor=None,
        held_damage_offset=None,
        held_damage_xor=None,
        erasure_capacity=None,
        worked_input=worked_inputs[0],
        worked_output=worked_outputs[0],
        held_input=held_inputs[0],
        held_output=held_outputs[0],
    )
    name = "slot-affine-adapter-v1"
    inherited[8] = replace(
        inherited[8],
        name=name,
        consumes=(6, 8),
        definition=_descriptor(bootstrap.BYTES, len(name)),
        definition_value=name.encode("ascii"),
        worked_output=bytes.fromhex("00000004d401"),
        held_output=bytes.fromhex("0000002971c1"),
    )
    name = "group-fragment-adapter-v1"
    inherited[9] = replace(
        inherited[9],
        name=name,
        consumes=(7, 8, 9),
        definition=_descriptor(bootstrap.BYTES, len(name)),
        definition_value=name.encode("ascii"),
    )
    return tuple(inherited)


def build_r3_route_images(
    candidate: CandidateRouteData,
    side: int,
    shell_width: int,
) -> RouteImageSet:
    """Build the exact pre-promotion v7 route from the frozen delta."""

    if (
        candidate.profile_id,
        candidate.profile_version,
        candidate.transport_id,
        candidate.section_check_id,
    ) != _R3_PROFILE_ROW:
        raise RouteDataError("candidate-identity")
    packages = _validated_packages(candidate)
    recipes = _recipe_index(packages)
    facts = r3_route_facts()
    route_parts = []
    record_owners = []
    for sector_id, mask in enumerate(SECTOR_MASKS):
        examples = _check_examples(facts, recipes, mask)
        records, owners = _build_records(sector_id, facts, packages, examples)
        record_count = (
            3 * len(facts)
            + sum(len(package.tables) for package in packages)
            + len(packages)
            + 2
        )
        recipe_bytes = sum(len(package.encoded) for package in packages)
        prefix_cells = (64 + len(records)) * 8
        envelope = b"".join(
            (
                ROUTE_MAGIC,
                _be(1, 2),
                bytes((sector_id, sector_id)),
                _be(candidate.profile_version, 2),
                _be(record_count, 2),
                _be(len(records), 4),
                _be(recipe_bytes, 4),
                _be(prefix_cells, 4),
                _be(DISCRIMINATOR_CELLS, 2),
                b"\0\0",
            )
        )
        route_parts.append(CALIBRATIONS[sector_id] + envelope + records)
        record_owners.append(owners)
    return _assemble_route_images(
        candidate,
        tuple(route_parts),
        tuple(record_owners),
        side,
        shell_width,
    )


def r3_route_resource_metrics(
    candidate: CandidateRouteData,
) -> R3RouteResourceMetrics:
    """Derive the logical worked/held charge from the exact v7 fact graph."""

    if (
        candidate.profile_id,
        candidate.profile_version,
        candidate.transport_id,
        candidate.section_check_id,
    ) != _R3_PROFILE_ROW:
        raise RouteDataError("candidate-identity")
    recipes = _recipe_index(_validated_packages(candidate))
    primitive_steps = 0
    scratch = 0
    for fact in r3_route_facts():
        package, recipe = recipes[fact.recipe_id]
        del package
        primitive_steps += 2 * recipe.primitive_steps
        scratch = max(scratch, recipe.peak_live_scratch_bytes)
        if fact.encoder_recipe_id is not None:
            encoder_package, encoder = recipes[fact.encoder_recipe_id]
            del encoder_package
            primitive_steps += 2 * encoder.primitive_steps
            scratch = max(scratch, encoder.peak_live_scratch_bytes)
    return R3RouteResourceMetrics(primitive_steps, scratch)


_R3_CAPACITY_PROJECTION_KEYS = frozenset(
    {
        "cell_inverse_multiplier",
        "cell_multiplier",
        "cell_offset",
        "encoded_transport_bytes",
        "factor_1_group_count",
        "factor_2_group_count",
        "factor_5_group_count",
        "fixed_logical_group_count",
        "fixed_pad_cells",
        "interior_side",
        "inventory_dependency_count",
        "inventory_entry_count",
        "inventory_fragment_count",
        "inventory_payload_bytes",
        "load_fragment_counts",
        "load_payload_bytes",
        "logical_group_count",
        "mandatory_physical_unit_count",
        "physical_unit_count",
        "population",
        "protected_cells",
        "separation_window",
        "slot_inverse_multiplier",
        "slot_multiplier",
    }
)


def _r3_route_prefixes(
    images: RouteImageSet,
) -> tuple[bytes, bytes, bytes, bytes]:
    if (
        type(images) is not RouteImageSet
        or images.profile_id != _R3_PROFILE_ROW[0]
        or images.profile_version != 7
        or len(images.sectors) != 4
    ):
        raise RouteDataError("r3-route-images")
    prefixes = []
    for sector_id, sector in enumerate(images.sectors):
        if (
            sector.sector_id != sector_id
            or sector.route_prefix_cells % 8
            or sector.route_prefix_cells > len(sector.data) * 8
        ):
            raise RouteDataError("r3-route-images")
        prefix = sector.data[: sector.route_prefix_cells // 8]
        if (
            len(prefix) < 64
            or prefix[:32] != CALIBRATIONS[sector_id]
            or prefix[32:40] != ROUTE_MAGIC
            or prefix[40:42] != b"\0\x01"
            or prefix[42:44] != bytes((sector_id, sector_id))
            or prefix[44:46] != b"\0\x07"
        ):
            raise RouteDataError("r3-route-images")
        prefixes.append(prefix)
    return tuple(prefixes)  # type: ignore[return-value]


def _r3_route_record_index(
    prefix: bytes,
) -> dict[int, tuple[int, int, int]]:
    if len(prefix) < 64:
        raise RouteDataError("r3-route-record")
    record_count = int.from_bytes(prefix[46:48], "big")
    record_bytes = int.from_bytes(prefix[48:52], "big")
    if len(prefix) != 64 + record_bytes:
        raise RouteDataError("r3-route-record")
    result: dict[int, tuple[int, int, int]] = {}
    offset = 64
    previous_id = 0
    for _ in range(record_count):
        if offset + 8 > len(prefix):
            raise RouteDataError("r3-route-record")
        kind = prefix[offset + 1]
        record_id = int.from_bytes(prefix[offset + 2 : offset + 4], "big")
        length = int.from_bytes(prefix[offset + 4 : offset + 8], "big")
        payload_offset = offset + 8
        end = payload_offset + length
        if (
            record_id <= previous_id
            or record_id in result
            or not 1 <= kind <= 7
            or end > len(prefix)
        ):
            raise RouteDataError("r3-route-record")
        result[record_id] = (kind, payload_offset, length)
        previous_id = record_id
        offset = end
    if offset != len(prefix):
        raise RouteDataError("r3-route-record")
    return result


def _r3_package_offsets(
    package: bytes,
) -> tuple[dict[int, tuple[int, int]], dict[int, tuple[int, int]]]:
    """Return raw TABLE payload and RECIPE record offsets after full decode."""

    if len(package) < 64:
        raise RouteDataError("r3-package-layout")
    table_count = int.from_bytes(package[18:20], "big")
    recipe_count = int.from_bytes(package[16:18], "big")
    tables: dict[int, tuple[int, int]] = {}
    offset = 64
    for _ in range(table_count):
        if offset + 16 > len(package):
            raise RouteDataError("r3-package-layout")
        table_id = int.from_bytes(package[offset : offset + 2], "big")
        length = int.from_bytes(package[offset + 12 : offset + 16], "big")
        payload_offset = offset + 16
        end = payload_offset + length
        if table_id in tables or end > len(package):
            raise RouteDataError("r3-package-layout")
        tables[table_id] = (payload_offset, length)
        offset = end
    recipes: dict[int, tuple[int, int]] = {}
    for _ in range(recipe_count):
        if offset + 32 > len(package):
            raise RouteDataError("r3-package-layout")
        recipe_id = int.from_bytes(package[offset : offset + 2], "big")
        length = int.from_bytes(package[offset + 28 : offset + 32], "big")
        end = offset + length
        if recipe_id in recipes or length < 32 or end > len(package):
            raise RouteDataError("r3-package-layout")
        recipes[recipe_id] = (offset, length)
        offset = end
    if offset != len(package):
        raise RouteDataError("r3-package-layout")
    return tables, recipes


def build_r3_malformed_route_corpus(clean_prefix: bytes) -> bytes:
    """Build the exact eight-row noncircular v1 malformed route corpus."""

    if type(clean_prefix) is not bytes:
        raise RouteDataError("r3-malformed-prefix")
    records = _r3_route_record_index(clean_prefix)
    try:
        define_kind, define_offset, define_length = records[801]
        worked_kind, worked_offset, _ = records[802]
        table_kind, table_offset, table_length = records[5010]
        package_kind, package_offset, package_length = records[6001]
    except KeyError as error:
        raise RouteDataError("r3-malformed-record") from error
    if (
        define_kind != 1
        or worked_kind != 2
        or table_kind != 4
        or package_kind != 5
        or define_length < 1
        or table_length < 16 + 256
    ):
        raise RouteDataError("r3-malformed-record")
    package = clean_prefix[package_offset : package_offset + package_length]
    try:
        bootstrap.decode_recipe_package(package, 7)
    except bootstrap.BootstrapError as error:
        raise RouteDataError("r3-malformed-package") from error
    package_tables, package_recipes = _r3_package_offsets(package)
    if (
        clean_prefix[table_offset : table_offset + 2] != b"\0\x11"
        or clean_prefix[table_offset + 16 + 255] != 0
        or 17 not in package_tables
        or 113 not in package_recipes
    ):
        raise RouteDataError("r3-malformed-owner")
    package_table_offset, package_table_length = package_tables[17]
    recipe_offset, recipe_length = package_recipes[113]
    if package_table_length != 256 or recipe_length < 48:
        raise RouteDataError("r3-malformed-owner")

    mutations: list[tuple[str, tuple[tuple[int, bytes], ...]]] = [
        ("route-version-zero", ((40, b"\0\0"),)),
        ("profile-version-three", ((44, b"\0\x03"),)),
        (
            "fact8-definition-v0",
            ((define_offset + define_length - 1, b"\x30"),),
        ),
        ("fact8-worked-recipe30", ((worked_offset + 2, b"\0\x1e"),)),
        (
            "route-table17-index223-xor01",
            ((table_offset + 16 + 223, bytes((clean_prefix[table_offset + 16 + 223] ^ 1,))),),
        ),
        (
            "both-table17-index255-one",
            (
                (table_offset + 16 + 255, b"\x01"),
                (package_offset + package_table_offset + 255, b"\x01"),
            ),
        ),
        (
            "package-recipe113-id114",
            ((package_offset + recipe_offset, b"\0\x72"),),
        ),
        (
            "package-recipe113-input0-width7",
            ((package_offset + recipe_offset + 32 + 4, b"\0\0\0\x07"),),
        ),
    ]
    expected_clean = (
        (40, b"\0\x01"),
        (44, b"\0\x07"),
        (define_offset + define_length - 1, b"\x31"),
        (worked_offset + 2, b"\0\x71"),
        (package_offset + recipe_offset, b"\0\x71"),
        (package_offset + recipe_offset + 32 + 4, b"\0\0\0\x08"),
    )
    if any(
        clean_prefix[offset : offset + len(value)] != value
        for offset, value in expected_clean
    ):
        raise RouteDataError("r3-malformed-owner")
    rows = []
    for case_id, changes in mutations:
        mutant = bytearray(clean_prefix)
        for offset, replacement in changes:
            end = offset + len(replacement)
            if end > len(mutant):
                raise RouteDataError("r3-malformed-offset")
            mutant[offset:end] = replacement
        raw = bytes(mutant)
        if len(raw) != len(clean_prefix) or raw == clean_prefix:
            raise RouteDataError("r3-malformed-mutation")
        rows.append(
            {
                "case_id": case_id,
                "expected_result": "reject",
                "mutant_bytes": len(raw),
                "mutant_sha256": sha256(raw).hexdigest(),
                "sector_id": 0,
            }
        )
    return canonical_manifest.serialize_manifest(
        {
            "clean_sector_sha256": sha256(clean_prefix).hexdigest(),
            "rows": rows,
            "schema": "golden-board.m2-r3-route-malformed-corpus/v1",
        }
    )


def _validate_r3_capacity_projection(
    value: dict[str, object], table17: bytes
) -> None:
    if type(value) is not dict or set(value) != _R3_CAPACITY_PROJECTION_KEYS:
        raise RouteDataError("r3-capacity-projection")
    arrays = (value["load_fragment_counts"], value["load_payload_bytes"])
    if (
        any(type(item) is not list for item in arrays)
        or len(arrays[0]) != len(arrays[1])
        or not arrays[0]
        or any(
            type(item) is not int or item <= 0
            for array in arrays
            for item in array
        )
        or any(
            type(item) is not int or item < 0
            for key, item in value.items()
            if key not in {"load_fragment_counts", "load_payload_bytes"}
        )
    ):
        raise RouteDataError("r3-capacity-projection")
    interior = value["interior_side"]
    population = value["population"]
    physical = value["physical_unit_count"]
    slot = value["slot_multiplier"]
    cell = value["cell_multiplier"]
    if (
        len(table17) != 256
        or interior != R3_SECTOR_SIDE - 2 * R3_SHELL_WIDTH
        or population != interior * interior
        or physical != population // 1_728
        or slot != table17[interior // 8]
        or value["slot_inverse_multiplier"] != pow(slot, -1, physical)
        or cell != 2 * interior - 1
        or value["cell_inverse_multiplier"] != pow(cell, -1, population)
        or value["cell_offset"]
        != (40_503 * 7 + 257 * R3_SHELL_WIDTH) % population
        or value["separation_window"] != max(32, interior // 8)
        or value["fixed_logical_group_count"] + sum(arrays[0])
        != value["logical_group_count"]
        or value["factor_1_group_count"]
        + value["factor_2_group_count"]
        + value["factor_5_group_count"]
        != value["logical_group_count"]
        or value["factor_1_group_count"]
        + 2 * value["factor_2_group_count"]
        + 5 * value["factor_5_group_count"]
        != physical
        or value["mandatory_physical_unit_count"] + sum(arrays[0])
        != physical
        or value["encoded_transport_bytes"] != 216 * physical
        or value["protected_cells"] != 1_728 * physical
        or value["fixed_pad_cells"]
        != population - value["protected_cells"]
    ):
        raise RouteDataError("r3-capacity-projection")


def _r3_first_fit(
    prefixes: tuple[bytes, bytes, bytes, bytes],
    table17: bytes,
    mandatory_units: int,
) -> dict[str, object]:
    pairs = tuple(
        (side, width)
        for side in range(64, 2_049, 8)
        for width in range(8, min(128, (side - 8) // 2) + 1, 8)
    )
    prefix_cells = tuple(len(prefix) * 8 for prefix in prefixes)
    instruction_cells = sum(prefix_cells)
    headroom = max((instruction_cells + 19) // 20, 4 * DISCRIMINATOR_CELLS)
    remaining = headroom - 4 * DISCRIMINATOR_CELLS
    quotient, remainder = divmod(remaining, 4)
    headrooms = tuple(
        DISCRIMINATOR_CELLS + quotient + int(sector < remainder)
        for sector in range(4)
    )
    selected_ordinal = 0
    predecessor_reason = ""
    for ordinal, (side, width) in enumerate(pairs, 1):
        interior = side - 2 * width
        population = interior * interior
        units = population // 1_728
        table_index = interior // 8
        if (
            interior % 8
            or not 0 < table_index < 255
            or table17[table_index] == 0
        ):
            reason = "no-admissible-map"
        elif units < mandatory_units:
            reason = "mandatory-units-do-not-fit"
        elif any(
            prefix_cells[sector] + headrooms[sector] > width * (side - width)
            for sector in range(4)
        ):
            reason = "route-shell-capacity"
        else:
            selected_ordinal = ordinal
            break
        predecessor_reason = reason
    if (
        selected_ordinal == 0
        or pairs[selected_ordinal - 1] != (R3_SECTOR_SIDE, R3_SHELL_WIDTH)
        or selected_ordinal == 1
    ):
        raise RouteDataError("r3-first-fit")
    predecessor_side, predecessor_width = pairs[selected_ordinal - 2]
    return {
        "examined_pair_count": selected_ordinal,
        "predecessor_reason": predecessor_reason,
        "predecessor_shell_width": predecessor_width,
        "predecessor_side": predecessor_side,
        "selected_pair_ordinal": selected_ordinal,
        "total_pair_count": len(pairs),
    }


def _r3_example_record_bytes(prefix: bytes) -> tuple[int, int]:
    worked = 0
    held = 0
    for kind, _offset, length in _r3_route_record_index(prefix).values():
        if kind == 2:
            worked += 8 + length
        elif kind == 3:
            held += 8 + length
    return worked, held


def _r3_reproduction_receipt(
    implementation_id: str, projection: dict[str, object]
) -> bytes:
    if implementation_id not in {"python", "rust"}:
        raise RouteDataError("r3-reproduction-implementation")
    projection_raw = canonical_manifest.serialize_manifest(projection)
    return canonical_manifest.serialize_manifest(
        {
            "implementation_id": implementation_id,
            "recipient_package_sha256": projection["recipient_package_sha256"],
            "reproduction_projection_sha256": sha256(projection_raw).hexdigest(),
            "route_data_template_sha256": projection["route_data_template_sha256"],
            "route_sha256": projection["route_sha256"],
            "schema": "golden-board.m2-r3-route-reproduction/v1",
        }
    )


def build_r3_route_owner_projection(
    owner_fixture_raw: bytes,
    candidate: CandidateRouteData,
    capacity_projection: dict[str, object],
) -> R3RouteOwnerProjection:
    """Build all noncircular Python inputs to the final v1 route owner."""

    packages = _validated_packages(candidate)
    if len(packages) != 1:
        raise RouteDataError("r3-package-count")
    package = packages[0]
    images = build_r3_route_images(
        candidate, R3_SECTOR_SIDE, R3_SHELL_WIDTH
    )
    prefixes = _r3_route_prefixes(images)
    template = render_r3_route_data_template(owner_fixture_raw)
    table17 = next(
        (table.payload for table in package.tables if table.table_id == 17),
        None,
    )
    if table17 is None:
        raise RouteDataError("r3-table17")
    _validate_r3_capacity_projection(capacity_projection, table17)
    first_fit = _r3_first_fit(
        prefixes,
        table17,
        int(capacity_projection["mandatory_physical_unit_count"]),
    )
    malformed = build_r3_malformed_route_corpus(prefixes[0])
    malformed_value = canonical_manifest.validate_canonical_manifest(malformed)
    recipes = {recipe.recipe_id: recipe for recipe in package.recipes}
    resource_rows = []
    for recipe_id in (30, 109, 110, 113):
        try:
            recipe = recipes[recipe_id]
        except KeyError as error:
            raise RouteDataError("r3-resource-recipe") from error
        resource_rows.append(
            {
                "encoded_bytes": recipe.recipe_bytes,
                "node_count": len(recipe.nodes),
                "peak_scratch_bytes": recipe.peak_live_scratch_bytes,
                "primitive_steps": recipe.primitive_steps,
                "recipe_id": recipe_id,
            }
        )
    record_bytes = tuple(_r3_example_record_bytes(prefix) for prefix in prefixes)
    route_resources = r3_route_resource_metrics(candidate)
    projection: dict[str, object] = {
        "capacity_projection": deepcopy(capacity_projection),
        "first_fit": first_fit,
        "held_out_record_bytes_by_sector": [item[1] for item in record_bytes],
        "malformed_corpus_case_count": len(malformed_value["rows"]),
        "malformed_corpus_sha256": sha256(malformed).hexdigest(),
        "recipe_resource_rows": resource_rows,
        "recipient_package_bytes": len(package.encoded),
        "recipient_package_edge_count": package.total_edge_count,
        "recipient_package_node_count": package.total_node_count,
        "recipient_package_peak_scratch_bytes": package.peak_live_scratch_bytes,
        "recipient_package_primitive_steps": package.maximum_primitive_steps,
        "recipient_package_sha256": sha256(package.encoded).hexdigest(),
        "recipient_package_table_payload_bytes": package.table_payload_bytes,
        "route_data_template_sha256": sha256(template).hexdigest(),
        "route_example_peak_scratch_bytes_by_sector": [
            route_resources.peak_scratch_bytes
        ]
        * 4,
        "route_example_primitive_steps_by_sector": [
            route_resources.worked_held_primitive_steps_per_sector
        ]
        * 4,
        "route_headroom_cells_by_sector": [
            sector.headroom_cells for sector in images.sectors
        ],
        "route_prefix_cells_by_sector": [
            sector.route_prefix_cells for sector in images.sectors
        ],
        "route_prefix_sha256_by_sector": [
            sha256(prefix).hexdigest() for prefix in prefixes
        ],
        "route_sha256": sha256(b"".join(prefixes)).hexdigest(),
        "slot_multiplier_table_sha256": sha256(table17).hexdigest(),
        "worked_record_bytes_by_sector": [item[0] for item in record_bytes],
    }
    projection_raw = canonical_manifest.serialize_manifest(projection)
    python_receipt = _r3_reproduction_receipt("python", projection)
    return R3RouteOwnerProjection(
        template,
        prefixes,
        malformed,
        projection_raw,
        python_receipt,
    )


def render_r3_route_data_owner(
    projection: R3RouteOwnerProjection,
    python_receipt_raw: bytes,
    rust_receipt_raw: bytes,
) -> bytes:
    """Close the v1 route owner only from two exact reproduction receipts."""

    if type(projection) is not R3RouteOwnerProjection:
        raise RouteDataError("r3-owner-projection")
    try:
        template = canonical_manifest.validate_canonical_manifest(
            projection.route_data_template
        )
        generated = canonical_manifest.validate_canonical_manifest(
            projection.reproduction_projection
        )
    except canonical_manifest.ManifestError as error:
        raise RouteDataError("r3-owner-projection") from error
    if template.get("generated") != {}:
        raise RouteDataError("r3-owner-template")
    expected_python = _r3_reproduction_receipt("python", generated)
    expected_rust = _r3_reproduction_receipt("rust", generated)
    if (
        type(python_receipt_raw) is not bytes
        or type(rust_receipt_raw) is not bytes
        or python_receipt_raw != projection.python_reproduction_receipt
        or python_receipt_raw != expected_python
        or rust_receipt_raw != expected_rust
        or python_receipt_raw == rust_receipt_raw
    ):
        raise RouteDataError("r3-reproduction-receipt")
    projection_sha256 = sha256(projection.reproduction_projection).hexdigest()
    generated["python_reproduction_sha256"] = sha256(
        python_receipt_raw
    ).hexdigest()
    generated["reproduction_projection_sha256"] = projection_sha256
    generated["rust_reproduction_sha256"] = sha256(rust_receipt_raw).hexdigest()
    template["generated"] = generated
    return canonical_manifest.serialize_manifest(template)


def load_r3_route_data_owner(
    raw: bytes,
    expected: R3RouteOwnerProjection,
    python_receipt_raw: bytes,
    rust_receipt_raw: bytes,
) -> dict[str, object]:
    """Admit only the independently regenerated complete v1 route owner."""

    if type(raw) is not bytes:
        raise RouteDataError("r3-owner-type")
    rendered = render_r3_route_data_owner(
        expected, python_receipt_raw, rust_receipt_raw
    )
    if raw != rendered:
        raise RouteDataError("r3-owner-drift")
    try:
        value = canonical_manifest.validate_canonical_manifest(raw)
    except canonical_manifest.ManifestError as error:
        raise RouteDataError("r3-owner-canonical") from error
    if value.get("schema") != "golden-board.route-data/v1":
        raise RouteDataError("r3-owner-schema")
    return value


def build_route_images(
    manifest_raw: bytes,
    candidate: CandidateRouteData,
    side: int,
    shell_width: int,
) -> RouteImageSet:
    """Build all four exact full-capacity sector images and ownership ledgers."""

    profiles = load_route_data_manifest(manifest_raw)
    packages = _validated_packages(candidate)
    recipes = _recipe_index(packages)
    facts = profiles[candidate.profile_version - 1]
    route_parts = []
    record_owners = []
    for sector_id, mask in enumerate(SECTOR_MASKS):
        examples = _check_examples(facts, recipes, mask)
        records, owners = _build_records(sector_id, facts, packages, examples)
        record_count = 36 + sum(len(package.tables) for package in packages) + len(packages) + 2
        recipe_bytes = sum(len(package.encoded) for package in packages)
        prefix_cells = (64 + len(records)) * 8
        envelope = b"".join(
            (
                ROUTE_MAGIC, _be(ROUTE_VERSION, 2), bytes((sector_id, sector_id)),
                _be(candidate.profile_version, 2), _be(record_count, 2),
                _be(len(records), 4), _be(recipe_bytes, 4), _be(prefix_cells, 4),
                _be(DISCRIMINATOR_CELLS, 2), b"\0\0",
            )
        )
        route_parts.append(CALIBRATIONS[sector_id] + envelope + records)
        record_owners.append(owners)
    return _assemble_route_images(
        candidate,
        tuple(route_parts),
        tuple(record_owners),
        side,
        shell_width,
    )


def _assemble_route_images(
    candidate: CandidateRouteData,
    route_parts: tuple[bytes, bytes, bytes, bytes],
    record_owners: tuple[
        tuple[tuple[str, int], ...],
        tuple[tuple[str, int], ...],
        tuple[tuple[str, int], ...],
        tuple[tuple[str, int], ...],
    ],
    side: int,
    shell_width: int,
) -> RouteImageSet:
    if (
        type(side) is not int
        or type(shell_width) is not int
        or not 64 <= side <= SECTOR_SIDE
        or side % 8 != 0
        or shell_width % 8 != 0
        or not 8 <= shell_width <= min(SHELL_WIDTH, (side - 8) // 2)
    ):
        raise RouteDataError("sector-geometry")
    sector_capacity_cells = shell_width * (side - shell_width)
    route_cells = tuple(len(item) * 8 for item in route_parts)
    instruction_cells = sum(route_cells)
    headroom_cells = max((instruction_cells + 19) // 20, 4 * DISCRIMINATOR_CELLS)
    remaining = headroom_cells - 4 * DISCRIMINATOR_CELLS
    quotient, remainder = divmod(remaining, 4)
    per_sector_headroom = tuple(DISCRIMINATOR_CELLS + quotient + (sector < remainder) for sector in range(4))
    sectors = []
    for sector_id in range(4):
        prefix = route_parts[sector_id]
        prefix_cells = route_cells[sector_id]
        assigned_headroom = per_sector_headroom[sector_id]
        if prefix_cells + assigned_headroom > sector_capacity_cells:
            raise RouteDataError("sector-fit")
        bits = _bytes_to_bits(prefix)
        bits.extend(_bytes_to_bits(CALIBRATIONS[sector_id]))
        generated_count = sector_capacity_cells - prefix_cells - DISCRIMINATOR_CELLS
        bits.extend(_pad_bits(candidate.profile_version, sector_id, generated_count))
        if len(bits) != sector_capacity_cells:
            raise RouteDataError("ledger-size")
        spans = [LedgerSpan(0, 256, "calibration"), LedgerSpan(256, 256, "route-envelope")]
        cursor = 512
        for owner, cell_count in record_owners[sector_id]:
            spans.append(LedgerSpan(cursor, cell_count, owner))
            cursor += cell_count
        if cursor != prefix_cells:
            raise RouteDataError("ledger-prefix")
        spans.append(LedgerSpan(cursor, DISCRIMINATOR_CELLS, "headroom-discriminator"))
        cursor += DISCRIMINATOR_CELLS
        extra = assigned_headroom - DISCRIMINATOR_CELLS
        if extra:
            spans.append(LedgerSpan(cursor, extra, "headroom-formula"))
            cursor += extra
        pad_count = sector_capacity_cells - cursor
        if pad_count:
            spans.append(LedgerSpan(cursor, pad_count, "fixed-pad"))
            cursor += pad_count
        if cursor != sector_capacity_cells or any(
            left.start_cell + left.cell_count != right.start_cell
            for left, right in zip(spans, spans[1:])
        ):
            raise RouteDataError("ledger-contiguity")
        sectors.append(SectorImage(sector_id, _bits_to_bytes(bits), prefix_cells, assigned_headroom, tuple(spans)))
    return RouteImageSet(candidate.profile_id, candidate.profile_version, instruction_cells, headroom_cells, tuple(sectors))


def validate_route_images(
    manifest_raw: bytes,
    candidate: CandidateRouteData,
    observed: Sequence[SectorImage],
    side: int,
    shell_width: int,
) -> RouteImageSet:
    """Rebuild and compare the complete route/ledger atomically."""

    if isinstance(observed, (bytes, bytearray, str)):
        raise RouteDataError("observed-shape")
    try:
        supplied = tuple(observed)
    except TypeError as error:
        raise RouteDataError("observed-shape") from error
    expected = build_route_images(manifest_raw, candidate, side, shell_width)
    if supplied != expected.sectors:
        raise RouteDataError("route-drift")
    return expected


def ablated_manifest(manifest_raw: bytes, fact_id: int) -> bytes:
    """Return a test-only canonical manifest with one defining node removed."""

    if type(fact_id) is not int or not 1 <= fact_id <= 12:
        raise RouteDataError("ablation-fact")
    try:
        value = canonical_manifest.validate_canonical_manifest(manifest_raw)
    except canonical_manifest.ManifestError as error:
        raise RouteDataError("manifest-canonical") from error
    value["facts"] = [item for item in value["facts"] if item["fact_id"] != fact_id]
    catalog = value["examples"]
    catalog["common"] = [item for item in catalog["common"] if item["fact_id"] != fact_id]
    for key in ("transport", "mapping", "section_check"):
        catalog[key] = [item for item in catalog[key] if item["value"]["fact_id"] != fact_id]
    return canonical_manifest.serialize_manifest(value)
