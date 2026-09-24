"""Canonical bounded integer fields; unchanged logical recipe semantics.

Encoding 2 is admitted only explicitly for development profile 8. The older
wire codec and historical production entrypoints keep their own admission.
"""
from __future__ import annotations

from typing import Sequence

from . import bootstrap
from .recipe_wire_v1 import RecipePackageV1, _fields, _uint


def _reject(path):
    raise bootstrap.BootstrapReject(bootstrap.RECIPE, 'compact2.' + path)


def _uleb(value: int) -> bytes:
    if type(value) is not int or not 0 <= value < 2**64:
        _reject('integer')
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def _read_uleb(raw: bytes, cursor: int, end: int, bits: int) -> tuple[int, int]:
    value = 0
    for ordinal in range((bits + 6) // 7):
        if cursor >= end:
            _reject('integer.boundary')
        byte = raw[cursor]
        cursor += 1
        value |= (byte & 127) << (7 * ordinal)
        if value >= 1 << bits:
            _reject('integer.overflow')
        if byte < 128:
            if ordinal and byte == 0:
                _reject('integer.noncanonical')
            return value, cursor
    _reject('integer.length')


def encode_recipe_package_v2(expanded_raw: bytes, expected_profile: int) -> bytes:
    if type(expected_profile) is not int or expected_profile != 8:
        _reject('profile')
    logical = bootstrap._decode_recipe_package(expanded_raw, expected_profile,
                                               maximum_profile_version=8)
    tables_end = 64 + sum(16 + len(table.payload) for table in logical.tables)
    encoded = bytearray(expanded_raw[:tables_end])
    encoded[8:10] = b'\0\2'
    offset = tables_end
    for recipe in logical.recipes:
        header = bytearray(expanded_raw[offset:offset + 32])
        descriptors = b''.join(bytes((d.value_type,)) + _uleb(d.width)
                               for d in recipe.inputs + recipe.outputs)
        nodes = bytearray()
        for node in recipe.nodes:
            _, auxiliary, immediate = _fields(node.opcode)
            nodes.append((node.output_type << 5) | node.opcode)
            nodes.extend(_uleb(node.output_width))
            for argument in node.arguments:
                nodes.extend(_uleb(argument))
            if auxiliary:
                nodes.extend(_uleb(node.auxiliary_u16))
            if immediate:
                nodes.extend(_uleb(node.immediate_u64))
        header[28:32] = (32 + len(descriptors) + len(nodes)).to_bytes(4, 'big')
        encoded.extend(header)
        encoded.extend(descriptors)
        encoded.extend(nodes)
        offset += recipe.recipe_bytes
    if len(encoded) > bootstrap.RECIPE_PACKAGE_MAX:
        _reject('length')
    encoded[32:36] = len(encoded).to_bytes(4, 'big')
    return bytes(encoded)


def _node(raw, cursor, end):
    if cursor + 2 > end:
        _reject('node.prefix')
    opcode, kind = raw[cursor] & 31, raw[cursor] >> 5
    if kind > 5:
        _reject('node.type')
    arity, auxiliary, immediate = _fields(opcode)
    width, cursor = _read_uleb(raw, cursor + 1, end, 32)
    args = []
    for _ in range(arity):
        value, cursor = _read_uleb(raw, cursor, end, 16)
        args.append(value)
    aux = imm = 0
    if auxiliary:
        aux, cursor = _read_uleb(raw, cursor, end, 16)
    if immediate:
        imm, cursor = _read_uleb(raw, cursor, end, 64)
    return cursor, opcode, kind, width, args, aux, imm


def _descriptor(raw, cursor, end):
    if cursor >= end or raw[cursor] not in (0,1,2,3,5):
        _reject('descriptor.type')
    kind = raw[cursor]
    width, cursor = _read_uleb(raw,cursor+1,end,32)
    return cursor,kind,width


def decode_recipe_package_v2(raw: bytes, expected_profile: int) -> RecipePackageV1:
    maximum = bootstrap.RECIPE_PACKAGE_MAX
    if type(raw) is not bytes or not 64 <= len(raw) <= maximum:
        _reject('length')
    if (type(expected_profile) is not int or expected_profile != 8
            or raw[:8] != b'GBRECP0\0' or raw[8:16] != b'\0\2\0\0\0\10\0\0'
            or any(raw[48:64])):
        _reject('header')
    recipe_count, table_count = _uint(raw,16,2), _uint(raw,18,2)
    total_nodes = _uint(raw,20,4)
    if (not 1 <= recipe_count <= 256 or table_count > 4096
            or not 1 <= total_nodes <= bootstrap.RECIPE_NODE_MAX
            or _uint(raw,24,4) > bootstrap.RECIPE_EDGE_MAX
            or _uint(raw,28,4) > maximum or _uint(raw,32,4) != len(raw)
            or _uint(raw,36,8) > bootstrap.RECIPE_STEP_MAX
            or _uint(raw,44,4) > bootstrap.RECIPE_SCRATCH_MAX):
        _reject('ranges')
    cursor = 64
    for _ in range(table_count):
        if cursor + 16 > len(raw):
            _reject('table.header')
        count, payload = _uint(raw,cursor+8,4), _uint(raw,cursor+12,4)
        if not 1 <= count <= maximum or payload > maximum:
            _reject('table.ranges')
        cursor += 16 + payload
        if cursor > len(raw):
            _reject('table.boundary')
    table_end = cursor
    expanded_size, node_sum, recipes = table_end, 0, []
    # First pass proves every node boundary and full expansion bound. Retain at
    # most 256 recipe spans; node values are reread from the immutable bytes.
    for _ in range(recipe_count):
        start = cursor
        if start + 32 > len(raw):
            _reject('recipe.header')
        inputs, outputs, nodes = _uint(raw,start+4,2), _uint(raw,start+6,2), _uint(raw,start+8,4)
        if (inputs > 64 or not 1 <= outputs <= 64
                or not 1 <= nodes <= bootstrap.RECIPE_NODE_MAX or inputs + nodes > 65535
                or _uint(raw,start+12,4) > bootstrap.RECIPE_EDGE_MAX
                or _uint(raw,start+16,8) > bootstrap.RECIPE_STEP_MAX
                or _uint(raw,start+24,4) > bootstrap.RECIPE_SCRATCH_MAX):
            _reject('recipe.ranges')
        node_sum += nodes
        if node_sum > total_nodes:
            _reject('node.count')
        descriptors = inputs + outputs
        front = 32 + 12 * descriptors
        size = _uint(raw,start+28,4)
        if not 32 + 2*descriptors + 2*nodes <= size <= 32 + 6*descriptors + 22*nodes:
            _reject('recipe.length')
        end = start + size
        if end > len(raw):
            _reject('recipe.boundary')
        expanded_size += front + 32 * nodes
        if expanded_size > maximum:
            _reject('expanded.length')
        cursor = start + 32
        for _ in range(descriptors):
            cursor = _descriptor(raw,cursor,end)[0]
        node_start = cursor
        for _ in range(nodes):
            cursor = _node(raw,cursor,end)[0]
        if cursor != end:
            _reject('recipe.trailing')
        recipes.append((start,inputs,outputs,nodes,node_start,end))
    if node_sum != total_nodes or cursor != len(raw):
        _reject('trailing_or_counts')
    expanded = bytearray(expanded_size)
    expanded[:table_end] = raw[:table_end]
    expanded[8:10] = b'\0\0'
    expanded[32:36] = expanded_size.to_bytes(4,'big')
    output = table_end
    for start,inputs,outputs,nodes,node_start,end in recipes:
        front = 32+12*(inputs+outputs)
        expanded[output:output+32] = raw[start:start+32]
        expanded[output+28:output+32] = (front+32*nodes).to_bytes(4,'big')
        output += 32
        cursor = start+32
        for count in (inputs,outputs):
            for ordinal in range(1,count+1):
                cursor,kind,width = _descriptor(raw,cursor,end)
                expanded[output:output+2] = ordinal.to_bytes(2,'big')
                expanded[output+2] = kind
                expanded[output+4:output+8] = width.to_bytes(4,'big')
                expanded[output+8:output+12] = (1).to_bytes(4,'big')
                output += 12
        if cursor != node_start:
            _reject('descriptor.boundary')
        for ordinal in range(1,nodes+1):
            cursor,op,kind,width,args,aux,imm = _node(raw,cursor,end)
            expanded[output:output+2] = ordinal.to_bytes(2,'big')
            expanded[output+2:output+4] = bytes((op,kind))
            expanded[output+4:output+8] = width.to_bytes(4,'big')
            expanded[output+8:output+10] = len(args).to_bytes(2,'big')
            for index,arg in enumerate(args):
                expanded[output+10+2*index:output+12+2*index] = arg.to_bytes(2,'big')
            expanded[output+18:output+20] = aux.to_bytes(2,'big')
            expanded[output+24:output+32] = imm.to_bytes(8,'big')
            output += 32
    logical = bootstrap._decode_recipe_package(bytes(expanded),8,maximum_profile_version=8)
    return RecipePackageV1(8,raw,logical)


def expand_recipe_package_v2(raw: bytes, expected_profile: int) -> bytes:
    return decode_recipe_package_v2(raw,expected_profile).logical.encoded


def evaluate_recipe_v2(package: RecipePackageV1, recipe_id: int,
                       inputs: Sequence[bytes]) -> bootstrap.RecipeResult:
    if not isinstance(package,RecipePackageV1):
        raise TypeError('evaluate_recipe_v2 requires RecipePackageV1')
    trusted = decode_recipe_package_v2(package.encoded,package.profile_version)
    return bootstrap._evaluate_validated_recipe(trusted.logical,recipe_id,inputs)
