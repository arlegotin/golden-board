"""Bounded compact recipe framing with unchanged logical VM validation.

Diagnostic profiles 1..8 are explicit to this codec. Historical public v0
decoding/evaluation retain version zero and profiles 1..7; profile 8 is not
promoted by encoding or evaluating its recipe package.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from . import bootstrap


__all__ = (
    "RecipePackageV1",
    "encode_recipe_package_v1",
    "expand_recipe_package_v1",
    "decode_recipe_package_v1",
    "evaluate_recipe_v1",
)


@dataclass(frozen=True, slots=True)
class RecipePackageV1:
    profile_version: int
    encoded: bytes
    logical: bootstrap.RecipePackage


def _uint(raw: bytes, offset: int, width: int) -> int:
    return int.from_bytes(raw[offset:offset + width], "big")


def _reject(path: str) -> None:
    raise bootstrap.BootstrapReject(bootstrap.RECIPE, path)


def _arity(opcode: int) -> int:
    if not 1 <= opcode <= 25:
        _reject("compact.node.opcode")
    if opcode in (1, 2, 24, 25):
        return 0
    if opcode in (5, 14, 22):
        return 1
    if opcode in (3, 20, 23):
        return 3
    return 2


def _fields(opcode: int) -> tuple[int, bool, bool]:
    return _arity(opcode), opcode in (2, 5, 22), opcode in (1, 5, 14, 22, 25)


def encode_recipe_package_v1(expanded_raw: bytes, expected_profile: int) -> bytes:
    """Validate a logical package before omitting its uniquely implied fields."""

    logical = bootstrap._decode_recipe_package(
        expanded_raw, expected_profile, maximum_profile_version=8
    )
    table_end = 64 + sum(16 + len(table.payload) for table in logical.tables)
    encoded = bytearray(expanded_raw[:table_end])
    encoded[8:10] = b"\0\1"
    offset = table_end
    for recipe in logical.recipes:
        node_start = offset + 32 + 12 * (len(recipe.inputs) + len(recipe.outputs))
        header = bytearray(expanded_raw[offset:node_start])
        body = bytearray()
        for index in range(len(recipe.nodes)):
            node = expanded_raw[node_start + 32 * index:node_start + 32 * (index + 1)]
            arity, auxiliary, immediate = _fields(node[2])
            body.extend(node[2:8])
            body.extend(node[10:10 + 2 * arity])
            if auxiliary:
                body.extend(node[18:20])
            if immediate:
                body.extend(node[24:32])
        header[28:32] = (len(header) + len(body)).to_bytes(4, "big")
        encoded.extend(header)
        encoded.extend(body)
        offset += recipe.recipe_bytes
    encoded[32:36] = len(encoded).to_bytes(4, "big")
    return bytes(encoded)


def decode_recipe_package_v1(compact_raw: bytes, expected_profile: int) -> RecipePackageV1:
    """Bound wire framing before expansion, then apply every logical v0 check."""

    maximum = bootstrap.RECIPE_PACKAGE_MAX
    if type(compact_raw) is not bytes or not 64 <= len(compact_raw) <= maximum:
        _reject("compact.length")
    if (
        compact_raw[:8] != b"GBRECP0\0"
        or _uint(compact_raw, 8, 2) != 1
        or _uint(compact_raw, 10, 2) != 0
        or type(expected_profile) is not int
        or not 1 <= expected_profile <= 8
        or _uint(compact_raw, 12, 2) != expected_profile
        or _uint(compact_raw, 14, 2) != 0
        or any(compact_raw[48:64])
    ):
        _reject("compact.header")
    recipe_count = _uint(compact_raw, 16, 2)
    table_count = _uint(compact_raw, 18, 2)
    total_nodes = _uint(compact_raw, 20, 4)
    if (
        not 1 <= recipe_count <= 256
        or table_count > 4096
        or not 1 <= total_nodes <= bootstrap.RECIPE_NODE_MAX
        or _uint(compact_raw, 24, 4) > bootstrap.RECIPE_EDGE_MAX
        or _uint(compact_raw, 28, 4) > maximum
        or _uint(compact_raw, 32, 4) != len(compact_raw)
        or _uint(compact_raw, 36, 8) > bootstrap.RECIPE_STEP_MAX
        or _uint(compact_raw, 44, 4) > bootstrap.RECIPE_SCRATCH_MAX
    ):
        _reject("compact.ranges")
    # First validate framing and derive the complete expanded bound, without
    # allocating output. Table typing/scalars remain the logical parser's job.
    offset = 64
    for _ in range(table_count):
        if offset + 16 > len(compact_raw):
            _reject("compact.table.header")
        count = _uint(compact_raw, offset + 8, 4)
        payload = _uint(compact_raw, offset + 12, 4)
        if not 1 <= count <= maximum or payload > maximum:
            _reject("compact.table.ranges")
        end = offset + 16 + payload
        if end > len(compact_raw):
            _reject("compact.table.boundary")
        offset = end

    table_end = offset
    expanded_size = table_end
    node_sum = 0
    recipes = []
    for _ in range(recipe_count):
        if offset + 32 > len(compact_raw):
            _reject("compact.recipe.header")
        inputs = _uint(compact_raw, offset + 4, 2)
        outputs = _uint(compact_raw, offset + 6, 2)
        nodes = _uint(compact_raw, offset + 8, 4)
        if (
            inputs > 64
            or not 1 <= outputs <= 64
            or not 1 <= nodes <= bootstrap.RECIPE_NODE_MAX
            or inputs + nodes > 0xffff
            or _uint(compact_raw, offset + 12, 4) > bootstrap.RECIPE_EDGE_MAX
            or _uint(compact_raw, offset + 16, 8) > bootstrap.RECIPE_STEP_MAX
            or _uint(compact_raw, offset + 24, 4) > bootstrap.RECIPE_SCRATCH_MAX
        ):
            _reject("compact.recipe.ranges")
        node_sum += nodes
        if node_sum > total_nodes:
            _reject("compact.total_node_count")
        descriptor_bytes = 12 * (inputs + outputs)
        recipe_bytes = _uint(compact_raw, offset + 28, 4)
        if not 32 + descriptor_bytes + 6 * nodes <= recipe_bytes <= 32 + descriptor_bytes + 18 * nodes:
            _reject("compact.recipe.length")
        end = offset + recipe_bytes
        if end > len(compact_raw):
            _reject("compact.recipe.boundary")
        node_start = offset + 32 + descriptor_bytes
        expanded_size += 32 + descriptor_bytes + 32 * nodes
        if expanded_size > maximum:
            _reject("compact.expanded_length")
        node_offset = node_start
        for _ in range(nodes):
            if node_offset + 6 > end:
                _reject("compact.node.prefix")
            arity, auxiliary, immediate = _fields(compact_raw[node_offset])
            node_bytes = 6 + 2 * arity + 2 * auxiliary + 8 * immediate
            if node_offset + node_bytes > end:
                _reject("compact.node.boundary")
            node_offset += node_bytes
        if node_offset != end:
            _reject("compact.recipe.trailing_fields")
        recipes.append((offset, node_start, nodes))
        offset = end
    if node_sum != total_nodes or offset != len(compact_raw):
        _reject("compact.trailing_or_counts")

    # Every copy extent and implicit zero field is now bounded. Original bytes
    # are immutable, so this pass uses exactly the framing validated above.
    expanded = bytearray(expanded_size)
    expanded[:table_end] = compact_raw[:table_end]
    expanded[8:10] = b"\0\0"
    expanded[32:36] = expanded_size.to_bytes(4, "big")
    output = table_end
    for start, node_start, nodes in recipes:
        header_bytes = node_start - start
        expanded[output:output + header_bytes] = compact_raw[start:node_start]
        expanded[output + 28:output + 32] = (header_bytes + 32 * nodes).to_bytes(4, "big")
        output += header_bytes
        node_offset = node_start
        for index in range(nodes):
            arity, auxiliary, immediate = _fields(compact_raw[node_offset])
            expanded[output:output + 2] = (index + 1).to_bytes(2, "big")
            expanded[output + 2:output + 8] = compact_raw[node_offset:node_offset + 6]
            expanded[output + 8:output + 10] = arity.to_bytes(2, "big")
            node_offset += 6
            expanded[output + 10:output + 10 + 2 * arity] = compact_raw[node_offset:node_offset + 2 * arity]
            node_offset += 2 * arity
            if auxiliary:
                expanded[output + 18:output + 20] = compact_raw[node_offset:node_offset + 2]
                node_offset += 2
            if immediate:
                expanded[output + 24:output + 32] = compact_raw[node_offset:node_offset + 8]
                node_offset += 8
            output += 32
    logical = bootstrap._decode_recipe_package(
        bytes(expanded), expected_profile, maximum_profile_version=8
    )
    return RecipePackageV1(expected_profile, compact_raw, logical)


def expand_recipe_package_v1(compact_raw: bytes, expected_profile: int) -> bytes:
    """Return exact expanded bytes only after complete logical validation."""

    return decode_recipe_package_v1(compact_raw, expected_profile).logical.encoded


def evaluate_recipe_v1(
    package: RecipePackageV1, recipe_id: int, inputs: Sequence[bytes]
) -> bootstrap.RecipeResult:
    """Reparse retained compact bytes; cached logical fields are not authority."""

    if not isinstance(package, RecipePackageV1):
        raise TypeError("evaluate_recipe_v1 requires RecipePackageV1")
    trusted = decode_recipe_package_v1(package.encoded, package.profile_version)
    return bootstrap._evaluate_validated_recipe(trusted.logical, recipe_id, inputs)
