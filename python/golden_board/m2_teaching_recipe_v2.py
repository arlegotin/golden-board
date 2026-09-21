"""Additional source-owned generic VM teaching; no carrier promotion implied."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import tomllib

from . import bootstrap, m2_recipe, recipe_wire_v1
from .m2_body_recipe_v1 import BodyRecipeProgramV1
from .m2_revision_recipe import build_revision_recipe_package, _encode_profile8_package


@dataclass(frozen=True, slots=True)
class TeachingExample:
    label: str
    recipe_id: int
    inputs: tuple[bytes, ...]
    output: bytes


def _uint(value, maximum=2**64 - 1):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError('teaching-source-integer')
    return value


def _pairs(value):
    if type(value) is not list or len(value) > 64:
        raise ValueError('teaching-source-descriptors')
    rows = []
    for pair in value:
        if type(pair) is not list or len(pair) != 2:
            raise ValueError('teaching-source-descriptor')
        rows.append((_uint(pair[0], 5), _uint(pair[1], 2**32 - 1)))
    return tuple(rows)


def _source():
    path = Path(__file__).resolve().parents[2] / 'spec/recipe-teaching-v2.toml'
    with path.open('rb') as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError('teaching-source-size')
    source = tomllib.loads(raw.decode('utf-8'))
    if (set(source) != {'version', 'tables', 'recipes', 'examples'}
            or type(source['version']) is not int or source['version'] != 1
            or type(source['tables']) is not list or len(source['tables']) != 1
            or type(source['recipes']) is not list or len(source['recipes']) != 5
            or type(source['examples']) is not list or len(source['examples']) != 8):
        raise ValueError('teaching-source-shape')
    return source


def _programs(source):
    result = []
    for expected_id, row in zip(range(210, 215), source['recipes'], strict=True):
        if (set(row) != {'id', 'inputs', 'outputs', 'nodes'}
                or _uint(row['id'], 65535) != expected_id
                or type(row['nodes']) is not list or not 1 <= len(row['nodes']) <= 100):
            raise ValueError('teaching-source-program')
        nodes = []
        for node in row['nodes']:
            if type(node) is not list or len(node) != 9:
                raise ValueError('teaching-source-node')
            op, kind, width, arity, a, b, c, aux, imm = tuple(_uint(x) for x in node)
            args = (a, b, c)
            if arity > 3 or any(args[arity:]):
                raise ValueError('teaching-source-unused-arguments')
            # The full package validator owns exact opcode arity, types,
            # widths, references, flags, effects and resource acceptance.
            nodes.append((op, kind, width, args[:arity], aux, imm))
        result.append(BodyRecipeProgramV1(expected_id, _pairs(row['inputs']),
                                        _pairs(row['outputs']), tuple(nodes)))
    return tuple(result)


def _examples(source):
    rows = []
    for row in source['examples']:
        if (set(row) != {'label', 'recipe', 'inputs', 'output'}
                or row['label'] not in ('worked', 'held', 'additional')
                or type(row['inputs']) is not list or len(row['inputs']) > 64
                or type(row['output']) is not str or len(row['output']) > 1024
                or any(type(x) is not str or len(x) > 1024 for x in row['inputs'])):
            raise ValueError('teaching-source-example')
        rows.append(TeachingExample(row['label'], _uint(row['recipe'], 65535),
                                    tuple(bytes.fromhex(x) for x in row['inputs']),
                                    bytes.fromhex(row['output'])))
    return tuple(rows)


def teaching_examples() -> tuple[TeachingExample, ...]:
    return _examples(_source())


@lru_cache(maxsize=1)
def build_teaching_recipe_package() -> bytes:
    source = _source()
    table = source['tables'][0]
    if (set(table) != {'id', 'type', 'width', 'count', 'payload'}
            or tuple(_uint(table[k]) for k in ('id', 'type', 'width', 'count')) != (21, 0, 8, 3)
            or table['payload'] != '070809'):
        raise ValueError('teaching-source-table')
    old = recipe_wire_v1.decode_recipe_package_v1(build_revision_recipe_package(), 8).logical
    inherited = tuple(BodyRecipeProgramV1(
        r.recipe_id, tuple((d.value_type, d.width) for d in r.inputs),
        tuple((d.value_type, d.width) for d in r.outputs),
        tuple((n.opcode, n.output_type, n.output_width, n.arguments,
               n.auxiliary_u16, n.immediate_u64) for n in r.nodes)) for r in old.recipes if r.recipe_id != 106)
    tables = tuple(m2_recipe._table_record(t.table_id, t.element_type, t.element_width,
                                         t.element_count, t.payload) for t in old.tables)
    tables += (m2_recipe._table_record(21, bootstrap.UINT, 8, 3, b'\x07\x08\x09'),)
    raw = _encode_profile8_package(inherited + _programs(source), tables)
    package = recipe_wire_v1.decode_recipe_package_v1(raw, 8)
    for row in _examples(source):
        actual = recipe_wire_v1.evaluate_recipe_v1(package, row.recipe_id, row.inputs)
        if actual.status.to_bytes(2, 'big') + b''.join(actual.outputs) != row.output:
            raise ValueError('teaching-source-example-result')
    return raw
