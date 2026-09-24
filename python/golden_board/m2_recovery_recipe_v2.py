"""Source-owned generic recovery programs and separately charged refinements.

No generated route, carrier or participant input is read here. Native evaluation
requires an already parsed profile-8 package with the exact transitive source
program/table closure. The caller must charge the full generic recipe resources
before dispatch; native execution does not provide or discount that charge.

Roster kernels 122/123 require a previously admitted complete inventory. Their
bounded structural traversal derives membership, not inventory admission. The
first inventory group (physical IDs 1..5) must be bootstrapped separately.
Recipe126 demonstrates the same traversal on a finite illustrative miniature;
its table25 does not constitute a fully admitted production inventory and its
local result never constitutes artifact admission.
"""
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from itertools import islice
from pathlib import Path
import tomllib

from . import bootstrap, m2_recipe, m2_codec, m2_transport_v2, recipe_wire_v1, recipe_wire_v2
from .m2_body_recipe_v1 import BodyRecipeProgramV1
from .m2_revision_recipe import build_revision_recipe_package, _encode_profile8_package
from .m2_recovery_reference_v2 import PROGRAMS as _REFERENCE_PROGRAMS, TABLES as _REFERENCE_TABLES


_SOURCE_LIMIT = 262144
_RECIPE_IDS = tuple(range(114, 128))
_NATIVE_IDS = (119, 120, 122, 123, 124, 126, 127)
_TABLE_SHAPES = ((23, bootstrap.BYTES, 8, 1), (24, bootstrap.BYTES, 216, 2),
                 (25, bootstrap.BYTES, 68, 1), (26, bootstrap.BYTES, 5, 8),
                 (27, bootstrap.BYTES, 4, 14))
# The finite fixture tables have closed contents as well as closed shapes.
# These source guards are not a substitute for comparing the actual carried
# transitive program/table records before native execution.
_TABLE_DIGESTS = (
    sha256(bytes.fromhex('d3916ac47208be5f')).hexdigest(),
    '852a7ac722c3d320e634ed8617e04f3105e18f683746c4e03578074945a19b9e',
    '64285c0bea30c06f2e16507c0a5f2c3a751082abc840429fa3a4bfda53d5c6c6',
    '3445e37879b2a7aa5e885fba817e974fa3234f352ffc82a301fbfdfd509f5b72',
    'fb6d348c685a7537d1ea70572feece31bdfcf1d743c62597c0e333f7aa4deaaa',
)


def _uint(value, maximum=2**64 - 1):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError('recovery-source-integer')
    return value


def _pairs(value):
    if type(value) is not list or not 1 <= len(value) <= 64:
        raise ValueError('recovery-source-descriptors')
    rows = []
    for pair in value:
        if type(pair) is not list or len(pair) != 2:
            raise ValueError('recovery-source-descriptor')
        rows.append((_uint(pair[0], 5), _uint(pair[1], 2**32 - 1)))
    return tuple(rows)


def _source():
    path = Path(__file__).resolve().parents[2] / 'spec/recovery-program-v2.toml'
    with path.open('rb') as stream:
        raw = stream.read(_SOURCE_LIMIT + 1)
    if len(raw) > _SOURCE_LIMIT:
        raise ValueError('recovery-source-size')
    source = tomllib.loads(raw.decode('utf-8'))
    if (set(source) != {'version', 'tables', 'recipes'}
            or type(source['version']) is not int or source['version'] != 1
            or type(source['tables']) is not list or len(source['tables']) != len(_TABLE_SHAPES)
            or type(source['recipes']) is not list
            or len(source['recipes']) != len(_RECIPE_IDS)):
        raise ValueError('recovery-source-shape')
    for table, shape, digest in zip(source['tables'], _TABLE_SHAPES, _TABLE_DIGESTS, strict=True):
        if (type(table) is not dict
                or set(table) != {'id', 'type', 'width', 'count', 'payload'}
                or tuple(_uint(table[k]) for k in ('id', 'type', 'width', 'count')) != shape
                or type(table['payload']) is not str
                or len(table['payload']) != 2*shape[2]*shape[3]):
            raise ValueError('recovery-source-table')
        payload = bytes.fromhex(table['payload'])
        if payload.hex() != table['payload'] or sha256(payload).hexdigest() != digest:
            raise ValueError('recovery-source-table-payload')
    return source


def recovery_programs() -> tuple[BodyRecipeProgramV1, ...]:
    """Read the bounded closed source; package validation owns VM semantics."""
    result = []
    for expected_id, row in zip(_RECIPE_IDS, _source()['recipes'], strict=True):
        if (type(row) is not dict or set(row) != {'id', 'inputs', 'outputs', 'nodes'}
                or _uint(row['id'], 65535) != expected_id
                or type(row['nodes']) is not list or not 1 <= len(row['nodes']) <= 4096):
            raise ValueError('recovery-source-program')
        nodes = []
        for node in row['nodes']:
            if type(node) is not list or len(node) != 9:
                raise ValueError('recovery-source-node')
            op, kind, width, arity, a, b, c, aux, imm = tuple(_uint(x) for x in node)
            args = (a, b, c)
            if (not 1 <= op <= 25 or kind > 5 or width > 2**32-1
                    or arity > 3 or any(args[arity:])
                    or max(a, b, c, aux) > 65535):
                raise ValueError('recovery-source-node-fields')
            nodes.append((op, kind, width, args[:arity], aux, imm))
        result.append(BodyRecipeProgramV1(expected_id, _pairs(row['inputs']),
                                         _pairs(row['outputs']), tuple(nodes)))
    result = tuple(result)
    if result != _reference_programs():
        raise ValueError('recovery-source-reference-drift')
    return result


def recovery_tables() -> tuple[bytes, ...]:
    """Return owned table records, suitable for package composition."""
    source = _source()
    result = tuple(m2_recipe._table_record(*shape, bytes.fromhex(table['payload']))
                   for shape, table in zip(_TABLE_SHAPES, source['tables'], strict=True))
    if result != _reference_tables():
        raise ValueError('recovery-source-reference-drift')
    return result


def _reference_programs():
    return tuple(BodyRecipeProgramV1(*row) for row in _REFERENCE_PROGRAMS)


def _reference_tables():
    return tuple(m2_recipe._table_record(*row) for row in _REFERENCE_TABLES)


@lru_cache(maxsize=1)
def _neutral_baseline():
    # This predecessor constructor uses only fixed generic source programs and
    # tables. In particular, it never generates the current teaching route.
    old = recipe_wire_v1.decode_recipe_package_v1(build_revision_recipe_package(), 8).logical
    inherited = tuple(BodyRecipeProgramV1(r.recipe_id,
        tuple((d.value_type, d.width) for d in r.inputs),
        tuple((d.value_type, d.width) for d in r.outputs),
        tuple((n.opcode, n.output_type, n.output_width, n.arguments,
               n.auxiliary_u16, n.immediate_u64) for n in r.nodes)) for r in old.recipes)
    tables = tuple(m2_recipe._table_record(t.table_id, t.element_type,
        t.element_width, t.element_count, t.payload) for t in old.tables)
    raw = _encode_profile8_package(tuple(sorted(inherited + _reference_programs(),
        key=lambda p: p.recipe_id)), tables + _reference_tables())
    return recipe_wire_v1.decode_recipe_package_v1(raw, 8).logical


def _closure(logical, root):
    if type(logical) is not bootstrap.RecipePackage or logical.profile_version != 8:
        return None
    if len(logical.recipes) > 256 or len(logical.tables) > 4096:
        return None
    programs = {r.recipe_id: r for r in logical.recipes}
    tables = {t.table_id: t for t in logical.tables}
    if len(programs) != len(logical.recipes) or len(tables) != len(logical.tables):
        return None
    seen, used_tables, pending = set(), set(), [root]
    while pending:
        rid = pending.pop()
        if rid in seen:
            continue
        if rid not in programs:
            return None
        seen.add(rid)
        for node in programs[rid].nodes:
            if node.opcode == 2:
                used_tables.add(node.auxiliary_u16)
            elif node.opcode == 22:
                pending.append(node.auxiliary_u16)
    if not used_tables <= tables.keys():
        return None
    # Complete immutable records include descriptor IDs/counts, every node
    # field, edge counts, exact resource declarations and expanded byte sizes.
    return (tuple(programs[rid] for rid in sorted(seen)),
            tuple(tables[tid] for tid in sorted(used_tables)))


def recovery_program_refined(package, recipe_id):
    """Admit an exact source closure in an already parsed package."""
    if (type(package) is not recipe_wire_v1.RecipePackageV1
            or package.profile_version != 8 or type(recipe_id) is not int
            or recipe_id not in _NATIVE_IDS):
        return False
    expected = _closure(_neutral_baseline(), recipe_id)
    return expected is not None and _closure(package.logical, recipe_id) == expected


@dataclass(frozen=True, slots=True, init=False)
class RecoveryExecution:
    """An immutable, scoped admission of retained wire2 recovery programs.

    Construction reparses the retained bytes and checks each requested closure
    once. Evaluation preserves the native typed-input and domain behavior;
    the caller still charges admission and complete generic execution costs.
    """

    _package: recipe_wire_v1.RecipePackageV1
    _roots: tuple[int, ...]

    def __init__(self, package, roots):
        if (type(package) is not recipe_wire_v1.RecipePackageV1
                or package.profile_version != 8 or type(package.encoded) is not bytes):
            raise ValueError('recovery-native-package')
        if isinstance(roots, (bytes, bytearray, str)):
            raise ValueError('recovery-native-roots')
        try:
            requested = tuple(islice(roots, len(_NATIVE_IDS)+1))
        except TypeError as error:
            raise ValueError('recovery-native-roots') from error
        if (not 1 <= len(requested) <= len(_NATIVE_IDS)
                or any(type(root) is not int or root not in _NATIVE_IDS for root in requested)
                or len(set(requested)) != len(requested)):
            raise ValueError('recovery-native-roots')
        retained = recipe_wire_v2.decode_recipe_package_v2(package.encoded, 8)
        if any(not recovery_program_refined(retained, root) for root in requested):
            raise ValueError('recovery-native-unrefined-closure')
        object.__setattr__(self, '_package', retained)
        object.__setattr__(self, '_roots', requested)

    def evaluate(self, recipe_id, inputs):
        if type(recipe_id) is not int or recipe_id not in self._roots:
            raise ValueError('recovery-native-unadmitted-root')
        return _evaluate_recovery_admitted(self._package, recipe_id, inputs)


def admit_recovery_programs(package, roots):
    """Reparse retained wire2 bytes and admit a bounded set of native roots."""
    return RecoveryExecution(package, roots)


def _group(inputs):
    factor, presence = inputs[0][0], inputs[1][0]
    if factor not in (1, 2, 5) or presence >> factor:
        return bootstrap.RecipeResult(3, ())
    lanes = []
    for index, pair in enumerate(inputs[3:]):
        if not (presence >> index) & 1:
            if any(pair):
                return bootstrap.RecipeResult(3, ())
            if index < factor:
                lanes.append(None)
            continue
        encoded, mask = pair[:216], pair[216:]
        if any(a & b for a, b in zip(encoded, mask, strict=True)):
            return bootstrap.RecipeResult(3, ())
        erased = tuple(bit for bit in range(1728) if mask[bit // 8] & (128 >> (bit % 8)))
        lanes.append(m2_codec.CopyObservation(encoded, erased))
    result = m2_transport_v2.aggregate_replica_group(tuple(lanes))
    block = result.chosen_block
    identity = block[:2] + block[4:14] + block[16:20] + block[22:26]
    accepted = result.group_state in (2, 3) and identity == inputs[2]
    return bootstrap.RecipeResult(0, (bytes((result.group_state,)), bytes((int(accepted),)), block))


def _roster(raw, length, target):
    count = int.from_bytes(raw[2:4], 'big')
    if (not 8 <= length <= 16384 or raw[:2] != b'\0\2'
            or raw[4:8] != b'\0\0\0\x40' or not 3 <= count <= 818 or target == 0):
        return bootstrap.RecipeResult(3, ())
    cursor, next_unit, previous, selected = 8, 1, 0, None
    for ordinal in range(count):
        if cursor + 20 > length:
            return bootstrap.RecipeResult(3, ())
        header = raw[cursor:cursor+20]
        sid = int.from_bytes(header[:4], 'big')
        kind = int.from_bytes(header[4:6], 'big')
        version = int.from_bytes(header[6:8], 'big')
        check, copies, flags = header[9:12]
        dependencies = int.from_bytes(header[12:14], 'big')
        payload = int.from_bytes(header[14:18], 'big')
        factor = (flags >> 1) & 7
        next_cursor = cursor + 20 + 4*dependencies
        if (sid <= previous or not 1 <= kind <= 6 or check != 1 or copies != 1
                or flags & 240 or factor not in (1, 2, 5) or dependencies > 4095
                or not 1 <= payload <= 16384 or next_cursor > length
                or (ordinal == 0 and (sid, kind, version, factor, dependencies, payload)
                    != (1, 1, 2, 5, 0, length))):
            return bootstrap.RecipeResult(3, ())
        envelope = 22 + 4*dependencies + payload
        fragments = (envelope + 156) // 157
        end = next_unit + fragments*factor
        if next_unit <= target < end:
            fragment = (target-next_unit) // factor
            first = next_unit + fragment*factor
            key = (b'\0\10' + header[:4] + bytes(2) + header[4:8]
                   + fragment.to_bytes(2, 'big') + fragments.to_bytes(2, 'big')
                   + envelope.to_bytes(4, 'big'))
            selected = bytes((factor,)) + first.to_bytes(4, 'big') + (first+factor-1).to_bytes(4, 'big') + key
        cursor, next_unit, previous = next_cursor, end, sid
    if cursor != length or selected is None:
        return bootstrap.RecipeResult(3, ())
    state = (raw + length.to_bytes(2, 'big') + cursor.to_bytes(2, 'big')
             + next_unit.to_bytes(4, 'big') + previous.to_bytes(4, 'big')
             + target.to_bytes(4, 'big') + b'\1' + selected + b'\1')
    return bootstrap.RecipeResult(0, (state,))


def _mapping(package, inputs):
    side, width, unit, bit = (int.from_bytes(raw, 'big') for raw in inputs)
    if (not 64 <= side <= 2048 or not 8 <= width <= 128 or side % 8 or width % 8
            or 2*width+8 > side):
        return bootstrap.RecipeResult(3, ())
    interior = side-2*width
    population, units = interior**2, interior**2 // 1728
    table = next(t for t in package.logical.tables if t.table_id == 17)
    multiplier = table.payload[interior // 8]
    if units < 2 or multiplier == 0 or not 1 <= unit <= units or bit >= 1728:
        return bootstrap.RecipeResult(3, ())
    slot = multiplier*(unit-1) % units
    logical = 1728*slot + bit
    physical = ((2*interior-1)*logical + 8*40503 + width*257) % population
    row, column = width + physical//interior, width + physical % interior
    return bootstrap.RecipeResult(0, tuple(v.to_bytes(4, 'big') for v in
        (slot, logical, physical, row, column, row*side+column)))


def _construction(package, inputs):
    tables = {t.table_id: t.payload for t in package.logical.tables}
    target, case = int.from_bytes(inputs[0], 'big'), inputs[1][0]
    roster = _roster(tables[25].ljust(16384, b'\0'), 68, target)
    if roster.status:
        return roster
    if case >= 8:
        return bootstrap.RecipeResult(3, ())
    state = roster.outputs[0]
    factor, first, key = state[16401], state[16402:16406], state[16410:16430]
    tokens = tables[26][5*case:5*(case+1)]
    lanes, presence = [], 0
    for lane, token in enumerate(tokens):
        if token == 0:
            lanes.append(bytes(432))
            continue
        if lane >= factor:
            return bootstrap.RecipeResult(3, ())
        source, unknown, start, count = tables[27][4*token:4*(token+1)]
        encoded = bytearray(tables[24][216*source:216*(source+1)])
        mask = bytearray(216)
        # Frozen templates contain bounded ranges of at most five bits.
        # No decoded header, supplied ownership flag or expected result is
        # used to construct these raw observed/unknown lane pairs.
        for bit in range(start, start+count):
            flag = 128 >> (bit % 8)
            if unknown == 1:
                mask[bit//8] |= flag
                encoded[bit//8] &= 255 ^ flag
            else:
                encoded[bit//8] ^= flag
        lanes.append(bytes(encoded+mask))
        presence |= 1 << lane
    result = _group((bytes((factor,)), bytes((presence,)), key, *lanes))
    if result.status:
        return result
    local, accepted, block = result.outputs
    return bootstrap.RecipeResult(0, (first, bytes((factor,)), key, local, accepted, block[30:53]))


def _bootstrap_first(inputs):
    limit = int.from_bytes(inputs[0], 'big')
    result = _group((b'\5', inputs[1], bytes(20), *inputs[2:]))
    if result.status:
        return result
    if not 5 <= limit <= 2389:
        return bootstrap.RecipeResult(3, ())
    local, _, block = result.outputs
    route_prefix = bytes.fromhex('000800000000000100000001000200000000')
    length, count = int.from_bytes(block[22:26], 'big'), int.from_bytes(block[18:20], 'big')
    accepted = (local in (b'\2', b'\3') and block[:18] == route_prefix
                and 22 <= length <= 16406 and 5*count <= limit)
    # This admits provisional first-fragment metadata only. Full envelope and
    # inventory semantics remain mandatory after consecutive fragment recovery.
    return bootstrap.RecipeResult(0, (local, bytes((int(accepted),)),
                                     block if accepted else bytes(191)))


def evaluate_recovery_native(package, recipe_id, inputs):
    """Return exact generic outputs after structural admission, without charging.

    The owner must validate retained wire bytes before providing ``package``
    and charge the generic recipe's complete declared work/scratch separately.
    Malformed input containers/elements raise TypeError; incorrect typed widths
    raise BootstrapReject, as in the generic VM. Materialization stops after
    one excess argument. Failed domain checks return status with no outputs.
    """
    if not recovery_program_refined(package, recipe_id):
        raise ValueError('recovery-native-unrefined-closure')
    return _evaluate_recovery_admitted(package, recipe_id, inputs)


def _evaluate_recovery_admitted(package, recipe_id, inputs):
    recipe = next(r for r in package.logical.recipes if r.recipe_id == recipe_id)
    if isinstance(inputs, (bytes, bytearray, str)):
        raise TypeError('inputs must be a sequence of byte strings')
    try:
        inputs = tuple(islice(inputs, len(recipe.inputs)+1))
    except TypeError as error:
        raise TypeError('inputs must be a sequence of byte strings') from error
    if any(type(raw) is not bytes for raw in inputs):
        raise TypeError('inputs must contain only bytes')
    if len(inputs) != len(recipe.inputs):
        bootstrap._recipe_reject('evaluation.inputs')
    for descriptor, raw in zip(recipe.inputs, inputs, strict=True):
        bootstrap._decode_value(raw, bootstrap._RecipeShape(descriptor.value_type,
            descriptor.width), 'evaluation.inputs')
    if recipe_id == 120:
        return _group(inputs)
    if recipe_id == 119:
        state = inputs[0]
        result = _group((state[:1], state[1:2], state[2:22],
                         *(state[22+i*432:22+(i+1)*432] for i in range(5))))
        if result.status:
            return result
        local, accepted, block = result.outputs
        returned = bytearray(4096)
        returned[2806:2997] = block
        returned[3010:3012] = local + accepted
        return bootstrap.RecipeResult(0, (bytes(returned),))
    if recipe_id == 122:
        state = inputs[0]
        return _roster(state[:16384], int.from_bytes(state[16384:16386], 'big'),
                       int.from_bytes(state[16396:16400], 'big'))
    if recipe_id == 123:
        result = _roster(inputs[0], int.from_bytes(inputs[1], 'big'), int.from_bytes(inputs[2], 'big'))
        if result.status:
            return result
        state = result.outputs[0]
        total = int.from_bytes(state[16388:16392], 'big')-1
        return bootstrap.RecipeResult(0, (state[16401:16402], state[16402:16406],
            state[16406:16410], state[16410:16430], total.to_bytes(4, 'big')))
    if recipe_id == 126:
        return _construction(package, inputs)
    if recipe_id == 127:
        return _bootstrap_first(inputs)
    return _mapping(package, inputs)
