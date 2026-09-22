"""Complete development profile-8 routes, with exact carried-byte accounting.

Owner comparison here is a production/source integrity check. It does not
claim independent acquisition or replace the recipient's use of the artifact.
"""

from dataclasses import dataclass

from . import bootstrap, m2_route_data as old, recipe_wire_v1
from .m2_route_definitions_v2 import build_route_definitions_v2
from .m2_teaching_recipe_v2 import build_teaching_recipe_package, teaching_examples

PROFILE_ID = 'eh72-hier-r5-r2-r1-lzss-crc32c-v1'
RECORD_COUNT = 47


@dataclass(frozen=True, slots=True)
class RouteRecord:
    stage: int
    kind: int
    record_id: int
    start: int
    payload: bytes


def _case(package, recipe_id, inputs, expected):
    result = recipe_wire_v1.evaluate_recipe_v1(package, recipe_id, inputs)
    actual = result.status.to_bytes(2, 'big') + b''.join(result.outputs)
    if actual != expected or result.status and result.outputs:
        raise old.RouteDataError('v2-example-result')
    incoming = b''.join(inputs)
    return (recipe_id.to_bytes(2, 'big') + len(incoming).to_bytes(4, 'big')
            + len(actual).to_bytes(4, 'big') + incoming + actual)


def _primary(package, fact, sector, held, definition):
    if fact.fact_id == 6:
        row = teaching_examples()[int(held)]
        return _case(package, row.recipe_id, row.inputs, row.output)
    if fact.fact_id == 10:
        start = 294+12*(4+int(held))
        trace = definition.value[start:start+12]
        return _case(package,110,tuple(bytes((v,)) for v in trace[:9]),b'\0\0'+trace[9:])
    source = fact.held_source if held else fact.worked_source
    per_sector = fact.held_sector_sources if held else fact.worked_sector_sources
    incoming = per_sector[sector] if per_sector else old._mask_input(
        source, fact.source_inputs, fact.mask_input_slots, old.SECTOR_MASKS[sector])
    if fact.encoder_recipe_id is not None:
        raise old.RouteDataError('v2-unowned-encoder-example')
    recipe = next(r for r in package.logical.recipes if r.recipe_id == fact.recipe_id)
    if (tuple((d.value_type, d.width) for d in recipe.inputs)
            != tuple((d.value_type, d.width) for d in fact.inputs)
            or tuple((d.value_type, d.width) for d in recipe.outputs[1:])
            != tuple((d.value_type, d.width) for d in fact.outputs)):
        raise old.RouteDataError('v2-example-interface')
    expected = old._expected_nontransport_output(8, fact, incoming)
    if sector == 0 and fact.fact_id != 9:
        canonical = fact.held_output if held else fact.worked_output
        if expected != canonical:
            raise old.RouteDataError('v2-inherited-example-drift')
    return _case(package, fact.recipe_id,
                 old._split_values(incoming, fact.inputs, 'v2-example-input'), expected)


def _build(compiled):
    definitions = build_route_definitions_v2(compiled)
    if tuple(d.fact_id for d in definitions) != tuple(range(1, 13)):
        raise old.RouteDataError('v2-definition-order')
    raw_package = build_teaching_recipe_package()
    package = recipe_wire_v1.decode_recipe_package_v1(raw_package, 8)
    facts = old.r3_route_facts()
    additions = tuple(row for row in teaching_examples() if row.label == 'additional')
    prefixes, all_owners = [], []
    for sector in range(4):
        records, owners = [], []
        base = sector * 10000

        def append(stage, kind, record_id, payload, name):
            encoded = old._record(stage, kind, base + record_id, payload)
            records.append(encoded)
            owners.append((name, len(encoded)*8))

        for definition, fact in zip(definitions, facts, strict=True):
            fid = definition.fact_id
            if definition.stage != fact.stage or definition.consumes != fact.consumes:
                raise old.RouteDataError('v2-definition-dependency')
            payload = (fid.to_bytes(2, 'big')
                       + old._descriptor_wire(fid, old.ValueDescriptor(bootstrap.BYTES, len(definition.value)))
                       + definition.value)
            append(fact.stage, 1, 100*fid+1, payload, f'define:{fid}')
            for held in (False, True):
                payload = fid.to_bytes(2, 'big') + _primary(package, fact, sector, held, definition)
                append(fact.stage, 3 if held else 2, 100*fid+2+int(held), payload,
                       f'{"held-out" if held else "worked"}:{fid}')
            if fid == 6:
                for index, row in enumerate(additions):
                    payload = fid.to_bytes(2, 'big') + _case(package, row.recipe_id, row.inputs, row.output)
                    append(fact.stage, 2+index%2, 100*fid+10+index, payload, f'vm-discriminator:{index}')
            if fid == 12:
                for index, (tokens, length, output) in enumerate((
                    (b'\0' + b'12345678', 9, b'12345678'),
                    (b'\x40A\0\x04' + bytes(5), 4, b'AAAAAAAA'),
                )):
                    payload = fid.to_bytes(2, 'big') + _case(package, 203,
                        (tokens, length.to_bytes(2, 'big')), bytes(2) + output)
                    append(fact.stage, 2+index, 100*fid+10+index, payload, f'body-codec:{index}')
        append(5, 5, 6001, raw_package, 'recipe-package:1')
        append(5, 6, 7001, (1).to_bytes(4, 'big'), 'endpoint')
        append(5, 7, 7002, b'', 'end')
        if len(records) != RECORD_COUNT:
            raise old.RouteDataError('v2-record-count')
        body = b''.join(records)
        envelope = (old.ROUTE_MAGIC + b'\0\2' + bytes((sector, sector)) + b'\0\x08'
                    + len(records).to_bytes(2, 'big') + len(body).to_bytes(4, 'big')
                    + len(raw_package).to_bytes(4, 'big') + ((64+len(body))*8).to_bytes(4, 'big')
                    + old.DISCRIMINATOR_CELLS.to_bytes(2, 'big') + bytes(2))
        prefixes.append(old.CALIBRATIONS[sector] + envelope + body)
        all_owners.append(tuple(owners))
    return tuple(prefixes), tuple(all_owners)


def build_route_prefixes_v2(compiled) -> tuple[bytes, ...]:
    return _build(compiled)[0]


def build_route_images_v2(compiled, side: int, shell_width: int):
    prefixes, owners = _build(compiled)
    candidate = old.CandidateRouteData(PROFILE_ID, 8, 'eh72-hier-repetition-v0',
                                      'crc32c-v0', (build_teaching_recipe_package(),))
    return old._assemble_route_images(candidate, prefixes, owners, side, shell_width)


def validate_route_prefix_v2(data: bytes, compiled, sector: int) -> tuple[RouteRecord, ...]:
    """Exact source-owner admission, reading only the declared route prefix."""
    if (type(data) is not bytes or not 64 <= len(data) <= 32768
            or type(sector) is not int or not 0 <= sector <= 3):
        raise old.RouteDataError('v2-route-input')
    end = 64 + int.from_bytes(data[48:52], 'big')
    if end > len(data) or end > 32768 or end < 64:
        raise old.RouteDataError('v2-route-length')
    if (data[:32] != old.CALIBRATIONS[sector] or data[32:40] != old.ROUTE_MAGIC
            or data[40:46] != b'\0\2' + bytes((sector, sector)) + b'\0\x08'
            or int.from_bytes(data[46:48], 'big') != RECORD_COUNT
            or int.from_bytes(data[52:56], 'big') != len(build_teaching_recipe_package())
            or int.from_bytes(data[56:60], 'big') != end*8
            or data[60:64] != b'\x01\0\0\0'):
        raise old.RouteDataError('v2-route-header')
    records = []
    offset = 64
    prior_stage, prior_id = 0, sector*10000
    for _ in range(RECORD_COUNT):
        if offset+8 > end:
            raise old.RouteDataError('v2-record-header')
        stage, kind = data[offset:offset+2]
        record_id = int.from_bytes(data[offset+2:offset+4], 'big')
        length = int.from_bytes(data[offset+4:offset+8], 'big')
        if (not prior_stage <= stage <= 5 or kind not in (1, 2, 3, 5, 6, 7)
                or not prior_id < record_id < (sector+1)*10000
                or length > end-offset-8):
            raise old.RouteDataError('v2-record-shape')
        records.append(RouteRecord(stage, kind, record_id, offset, data[offset+8:offset+8+length]))
        prior_stage, prior_id = stage, record_id
        offset += 8+length
    if offset != end:
        raise old.RouteDataError('v2-route-end')
    expected = build_route_prefixes_v2(compiled)[sector]
    if data[:end] != expected:
        raise old.RouteDataError('v2-route-drift')
    return tuple(records)
