"""Finite numeric route examples owned by spec/route-definitions-v2.md.

These checks establish the stated local observations, never carrier admission.
"""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from . import bootstrap as b, bootstrap_v2, content, m2_codec as codec
from . import m2_mapping_v2 as mapping, recipe_wire_v1
from .m2_revision_recipe import build_revision_recipe_package
from .m2_slice import SliceCompilation
from .position_teaching_v2 import build_position_teaching_v2


@dataclass(frozen=True, slots=True)
class RouteDefinitionV2:
    fact_id: int
    stage: int
    consumes: tuple[int, ...]
    value: bytes


def _check(condition, path):
    if not condition:
        raise ValueError('route_definitions_v2.' + path)


def _ints(values, width=2):
    return b''.join(value.to_bytes(width, 'big') for value in values)


def _layout(rows):
    return _ints((len(rows),)) + _ints(x for row in rows for x in row)


def _bits(raw):
    return tuple((value >> (7-i)) & 1 for value in raw for i in range(8))


def _pack(bits):
    return bytes(sum(bits[8*i+j] << (7-j) for j in range(8))
                 for i in range(len(bits)//8))


def _common_examples():
    result = []
    for value in (0, 1):
        envelope = b.encode_section_envelope(b.SectionEnvelope(400,4,0,129,1,(),bytes([value])))
        raw = b.encode_common_block(b.CommonBlock(8,400,0,4,0,0,1,len(envelope),envelope))
        _check(_local(raw) == (True, True), 'common.example')
        result.append(raw)
    return tuple(result)


def _local(raw):
    try:
        block = b.decode_common_block(raw, 8)
    except b.BootstrapReject:
        return False, False
    try:
        section = b.decode_section_envelope(block.payload)
    except b.BootstrapReject:
        return True, False
    return True, (block.section_id == section.section_id and
                  block.section_type == section.section_type and
                  block.section_version == section.section_version and
                  block.section_envelope_length == len(block.payload))


def _recheck(raw):
    return raw[:187] + b.crc32c_v0(b.LOCAL_DOMAIN + raw[:187]).to_bytes(4, 'big')


def _first_six():
    one = bytes.fromhex('00ff807faa55f00fcc3301fe817e18e7')
    observation = b.RawObservation(_bits(bytes.fromhex('80402010080403c1')), 64)
    images = tuple(_pack(tuple(observation.normalized_bit(b.EntryHypothesis(t,0),r,c)
        for r in range(8) for c in range(8))) for t in range(8))
    expected = ('80402010080403c1','81820408102040c0','83c0201008040201',
        '0302040810204181','010204081020c083','c040201008048281',
        'c103040810204080','8141201008040203')
    _check(tuple(x.hex() for x in images) == expected, 'transforms')
    _check(len(set(images + tuple(bytes(v^255 for v in x) for x in images))) == 16, 'polarities')
    three = b''.join(_ints(((1<<n)-1,),4)+bytes((n,n^255))+_ints((n,))
        for n in (0,1,2,3,4,5,7,8,15,16,24,31))
    four = bytearray(_ints((32,8,24,6)))
    for q in range(4):
        for u,v in ((0,0),(0,23),(7,0),(7,23),(0,1),(1,0)):
            r,c = ((u,v),(v,31-u),(31-u,31-v),(31-v,u))[q]
            _check(b.sector_cell(32,8,q,24*u+v) == (r,c), 'sector')
            four.extend(_ints((q,u,v,r,c,24*u+v)))
    layouts = (
        ((0,8),(8,2),(10,1),(11,1),(12,2),(14,2),(16,4),(20,4),(24,4),(28,2),(30,2)),
        ((0,1),(1,1),(2,2),(4,4)),
        ((0,8),(8,2),(10,2),(12,2),(14,2),(16,2),(18,2),(20,4),(24,4),(28,4),(32,4),(36,8),(44,4),(48,16)),
        ((0,2),(2,1),(3,1),(4,4),(8,4),(12,4)),
        ((0,2),(2,2),(4,2),(6,2),(8,4),(12,4),(16,8),(24,4),(28,4)),
        ((0,2),(2,1),(3,1),(4,4),(8,4)))
    package = recipe_wire_v1.decode_recipe_package_v1(build_revision_recipe_package(),8)
    recipe = next(r for r in package.logical.recipes if r.recipe_id == 109)
    compact_nodes = sum(6+2*len(n.arguments)+(2 if n.opcode in (2,5,22) else 0)
        +(8 if n.opcode in (1,5,14,22,25) else 0) for n in recipe.nodes)
    observed = (109,32,len(recipe.inputs),len(recipe.outputs),12,
                12*(len(recipe.inputs)+len(recipe.outputs)),len(recipe.nodes),compact_nodes,
                32+12*(len(recipe.inputs)+len(recipe.outputs))+compact_nodes)
    _check(observed == (109,32,3,2,12,60,42,484,576), 'recipe109')
    five = b''.join(_layout(rows) for rows in layouts) + _ints(observed)
    six = bytearray()
    for op in range(1,26):
        arity = 0 if op in (1,2,24,25) else 1 if op in (5,14,22) else 3 if op in (3,20,23) else 2
        aux, imm = (2 if op in (2,5,22) else 0), (8 if op in (1,5,14,22,25) else 0)
        six.extend(bytes((op,arity,2*arity,aux,imm,6+2*arity+aux+imm)))
    for kind,unit,low,high in ((0,0,1,64),(1,0,1,1),(2,0,1,1048576),
                             (3,1,0,1048576),(4,2,0,1048576),(5,0,16,16)):
        six.extend(bytes((kind,unit))+_ints((low,high),4))
    return one,b''.join(images),three,bytes(four),five,bytes(six)


def _seven_eight(common):
    a,c = common
    seven = bytearray(_layout(((0,2),(2,2),(4,4),(8,2),(10,2),(12,2),(14,2),
        (16,2),(18,2),(20,2),(22,4),(26,4),(30,157),(187,4))))
    seven.extend(_layout(((0,2),(2,4),(6,2),(8,2),(10,1),(11,1),(12,2),(14,4))))
    seven.extend(b.LOCAL_DOMAIN+b.SECTION_DOMAIN)
    for raw,expected in ((b'123456789',0xe3069283),(bytes(range(9)),0x7144c5a8)):
        _check(b.crc32c_v0(raw) == expected, 'crc.example')
        seven.extend(raw+_ints((expected,),4))
    seven.extend(a+c)
    mutations = ((2,2,1,1,0,0),(14,2,1,1,0,0),(26,2,1,1,0,0),
        (18,2,0,1,0,0),(16,2,1,1,0,0),(4,2,1,1,1,0),
        (22,2,1,1,0,0),(48,1,1,0,0,0),(187,1,a[187]^1,0,0,0),(53,1,1,1,0,0))
    for offset,width,value,recheck,local,agreement in mutations:
        raw = a[:offset]+_ints((value,),width)+a[offset+width:]
        if recheck:
            raw = _recheck(raw)
        _check(_local(raw) == (bool(local),bool(agreement)), 'common.mutation')
        seven.extend(_ints((offset,width,value,recheck,local,agreement)))
    encoded = tuple(codec.eh72_encode_unit(raw) for raw in common)
    for raw,unit in zip(common,encoded):
        result = codec._eh72_decode_unit(unit,(),8)
        _check(result.state == 'verified' and result.decoded == raw, 'eh.example')
    eight = _ints((24,9,8,216,192,191,1,0))+_ints(x for i in range(24) for x in (9*i,8*i))+b''.join(encoded)
    return bytes(seven),eight,encoded


def _nine():
    parameters,examples = bytearray(),bytearray()
    for side,width in ((2040,128),(1952,128)):
        p = mapping.mapping_parameters(side,width)
        parameters.extend(_ints((side,width,p.interior,p.population,p.units,p.slot_multiplier,
            p.slot_inverse,p.cell_multiplier,p.cell_inverse,p.offset),4))
        rows = []
        for unit,bit in ((1,0),(1,1727),(p.units,0),(p.units,1727),(p.units//p.slot_multiplier+2,0)):
            slot = p.slot_multiplier*(unit-1)%p.units
            rows.append((unit,bit,slot,1728*slot+bit,0))
        for logical in (1728*p.units-1,1728*p.units,p.population-1):
            if logical < 1728*p.units:
                slot,bit = divmod(logical,1728)
                rows.append((p.slot_inverse*slot%p.units+1,bit,slot,logical,0))
            else:
                rows.append((0,0,0,logical,1))
        for unit,bit,slot,logical,kind in rows:
            physical = (p.cell_multiplier*logical+p.offset)%p.population
            _check(mapping.invert_interior_cell(side,width,physical) == (kind,unit,bit), 'inverse')
            if not kind:
                _check(mapping.map_unit_bit(side,width,unit,bit) == physical, 'forward')
            examples.extend(_ints((unit,bit,slot,logical,physical,kind),4))
    return bytes(parameters+examples)


def _group(lanes, common, expected_key, erasures=None):
    """Finite composition of primitives with the carried physical expectation."""
    lane_erasures = ((),)*len(lanes) if erasures is None else erasures
    states,valid,lane_values = [],[],[]
    for lane,unknown in zip(lanes,lane_erasures,strict=True):
        if lane is None:
            states.append(0)
            lane_values.append(None)
            continue
        result = codec._eh72_decode_unit(lane,unknown,8)
        states.append({'corrupt':1,'verified':2,'recovered':3}[result.state])
        lane_values.append(result.decoded)
        if result.decoded is not None:
            valid.append(result.decoded)
    rep,rep_wire,rep_erasures = None,None,()
    if any(lane is not None for lane in lanes):
        bits,unknown_bits = [],[]
        lane_bits = tuple(_bits(lane) if lane is not None else None for lane in lanes)
        for index in range(1728):
            known_values = tuple(row[index] for row,unknown in zip(lane_bits,lane_erasures,strict=True)
                                 if row is not None and index not in unknown)
            ones = sum(known_values)
            known,value = codec.repetition_symbol_counts(len(lanes),len(known_values)-ones,ones)
            bits.append(value)
            if not known:
                unknown_bits.append(index)
        rep_wire,rep_erasures = _pack(tuple(bits)),tuple(unknown_bits)
        if len(rep_erasures) <= 72:
            rep = codec._eh72_decode_unit(rep_wire,rep_erasures,8).decoded
    distinct = set(valid)
    if rep is not None:
        distinct.add(rep)
    def identity_fields(raw):
        block = b.decode_common_block(raw,8)
        return (block.profile_version,block.section_id,block.semantic_copy_id,
                block.section_type,block.section_version,block.fragment_index,
                block.fragment_count,block.section_envelope_length)
    identity = bool(distinct) and all(identity_fields(raw) == expected_key for raw in distinct)
    accepted = identity and len(distinct) == 1
    mask = sum(1<<i for i,raw in enumerate(common) if raw in distinct)
    def candidate_mask(raw):
        _check(raw is None or raw in common,'group.unknown-example-block')
        return 0 if raw is None else 1 << common.index(raw)
    inputs = bytes(tuple(candidate_mask(raw) for raw in lane_values)
        +(0,)*(5-len(lanes))+(candidate_mask(rep),int(any(states)),int(2 in states),int(identity)))
    local_state = 4 if len(distinct)>1 else (2 if 2 in states else 3) if len(distinct)==1 else 1 if any(states) else 0
    output = bytes((mask,local_state,int(accepted)))
    rep_state = 3 if rep is not None else 1 if rep_wire is not None else 0
    return bytes(states)+bytes(5-len(states)),rep_state,inputs+output,rep_wire,rep_erasures


def _ten(common, encoded):
    from .m2_teaching_recipe_v2 import build_teaching_recipe_package
    package = recipe_wire_v1.decode_recipe_package_v1(build_teaching_recipe_package(),8)
    roster = ((1,0,2,5,1,5),(1,1,2,5,6,10),(400,0,1,5,11,15),(401,0,1,2,16,17))
    result = bytearray(_ints((4,6))+_ints(x for row in roster for x in row))
    result.extend(bytes((0,4,8,10,12,16,18,22)))
    keys = ((8,400,0,4,0,0,1,23),(8,401,0,4,0,0,1,23))
    result.append(len(keys))
    for key in keys:
        result.extend(b''.join(value.to_bytes(width,'big') for value,width in
                              zip(key,(2,4,2,2,2,2,2,4),strict=True)))
    templates = ((0,0,0,0),(0,0,59,5),(0,0,0,1)) + tuple((1,0,2*i,2) for i in range(5)) + tuple((0,1,59+i,5) for i in range(5))
    result.extend(_ints((111,))+bytes((0,)))
    result.extend(bytes((len(templates),4)))
    for row in templates:
        result.extend(bytes(row))
    observations = [(None,())]
    for source,unknown,first,count in templates:
        raw = bytearray(encoded[source])
        for bit in range(first,first+count):
            if unknown:
                raw[bit//8] &= ~(1 << (7-bit%8))
            else:
                raw[bit//8] ^= 1 << (7-bit%8)
        mask = sum(1 << (71-bit) for bit in range(first,first+count)) if unknown else 0
        constructed = recipe_wire_v1.evaluate_recipe_v1(package,111,
            (encoded[0][:9],encoded[1][:9],*tuple(bytes((v,)) for v in (source,unknown,first,count))))
        _check(constructed.status == 0 and constructed.outputs ==
               (bytes(raw[:9]),mask.to_bytes(9,'big')),'group.construction')
        observations.append((constructed.outputs[0]+encoded[source][9:],
                             tuple(range(first,first+count)) if unknown else ()))
    cases = ((11,0,0,0,0,0),(11,4,0,0,0,0),(11,1,0,0,0,0),(11,3,0,0,0,0),
             (11,1,4,5,6,7),(11,4,5,6,7,8),(11,9,10,11,12,13),(16,1,1,0,0,0))
    result.extend(_ints((110,))+bytes((len(cases),24)))
    erasure_word = None
    for number,(first,*tokens) in enumerate(cases,1):
        row = next(row for row in roster if row[4] == first)
        expected = next(key for key in keys if (key[1],key[5],key[6]) == row[:3])
        factor = row[3]
        _check(not any(tokens[factor:]),'group.outside-factor')
        lanes,unknowns = zip(*(observations[token] for token in tokens[:factor]),strict=True)
        states,rep_state,trace,rep_wire,rep_unknown = _group(lanes,common,expected,unknowns)
        checked = recipe_wire_v1.evaluate_recipe_v1(package,110,tuple(bytes((v,)) for v in trace[:9]))
        _check(checked.status == 0 and b''.join(checked.outputs) == trace[9:],'group.decision')
        result.extend(bytes((first,*tokens))+states+bytes((rep_state,))+trace)
        if number == 7:
            _check(states == bytes((1,)*5) and rep_state == 3 and rep_unknown == (63,), 'group.raw-unknown-repetition')
            erasure_word = rep_wire[:9]+bytes((1,rep_unknown[0]+1,0,0))
    result.extend(bytes((3,4)))
    for bit in (0,63,72):
        result.extend(_ints((bit,))+bytes((bit//72,bit%72+1)))
    result.extend(bytes((7,0,0))+_ints((30,))+erasure_word)
    decoded = recipe_wire_v1.evaluate_recipe_v1(package,30,(erasure_word[:9],erasure_word[9:10],erasure_word[10:]))
    _check(decoded.status == 0 and decoded.outputs == (common[0][:8],),'group.erasure-word')
    result.extend(_ints((113,))+bytes((4,8)))
    for factor,symbols in ((2,(0,1,2,2,2)),(5,(0,1,1,1,1)),(5,(1,2,2,2,2)),(5,(2,2,2,2,2))):
        args = (factor,symbols[:factor].count(0),symbols[:factor].count(1))
        known,value = codec.repetition_symbol_counts(*args)
        checked = recipe_wire_v1.evaluate_recipe_v1(package,113,tuple(bytes((v,)) for v in args))
        _check(checked.status == 0 and checked.outputs == (bytes((known,)),bytes((value,))),'group.raw-counts')
        result.extend(bytes((factor,*symbols,known,value)))
    result.append(5)
    for length in (22,157,158,314,315):
        count = (length+156)//157
        chunks = tuple(bytes(min(157,length-i*157)) for i in range(count))
        for i,chunk in enumerate(chunks):
            framed = b.encode_common_block(b.CommonBlock(8,400,0,4,0,i,count,length,chunk))
            _check(b.decode_common_block(framed,8).payload == chunk,'fragment.length')
        _check(sum(map(len,chunks)) == length,'fragment.reassembled')
        result.extend(_ints((length,))+bytes((count,len(chunks[-1]))))
    _check(len(result) == 443,'group.definition-size')
    return bytes(result)


def _eleven(common):
    result = bytearray(_layout(((0,2),(2,2),(4,2),(6,2)))+_layout(
        ((0,4),(4,2),(6,2),(8,1),(9,1),(10,1),(11,1),(12,2),(14,4),(18,2))))
    result.extend(bytes(x for factor in (1,2,5) for ordinal in (0,1) for x in (factor,ordinal,2*factor+ordinal)))
    result.extend(_ints((1,2,0,5,1,2,3,4,5)))
    for case in ('011111','100000','110000','111011','110100','111101',
                 '111100','111110','111111','000000','010101','101111'):
        i,r,a,t,u,e = tuple(map(int,case))
        required = i&r&t
        all_content = required&a&u
        result.extend(bytes((i,r,a,t,u,e,required,all_content,all_content&e)))
    for profile in (8,7):
        raw = _recheck(_ints((profile,))+common[0][2:])
        accepted = _local(raw)[0]
        _check(accepted == (profile == 8), 'selected.profile')
        result.extend(_ints((profile,8,1,int(accepted))))
    for rows in (((4,2,4),(10,6,2),(12,8,2)),
                 ((2,0,4),(6,4,2),(8,6,2),(10,8,1),(11,9,1),(12,12,2),(14,14,4))):
        result.extend(_ints((len(rows),))+bytes(x for row in rows for x in row))
    ids = (2,16,17,18)
    result.extend(_ints(ids))
    for adjacency,selected,closure,valid in ((0x7000,8,15,1),(0x4200,8,14,1),(0,4,4,1),(0x4800,8,0,0)):
        entries = tuple(b.InventoryEntry(sid,3,0,128,1,1,
            tuple(target for j,target in enumerate(ids) if adjacency & (1<<(15-4*i-j))),1)
            for i,sid in enumerate(ids))
        try:
            actual = b.dependency_closure(b.Inventory(entries),tuple(sid for i,sid in enumerate(ids)
                if selected & (1<<(3-i))),set(ids))
            observed = sum(1<<(3-i) for i,sid in enumerate(ids) if sid in actual)
            _check(valid == 1 and observed == closure, 'dependency.closure')
        except b.BootstrapReject:
            _check(valid == 0 and closure == 0, 'dependency.reject')
        result.extend(_ints((adjacency,))+bytes((selected,closure,valid)))
    for sid,ordinal,has,admitted in ((100,0,1,1),(163,63,1,1),(211,65535,0,1),(101,0,1,0)):
        header = _ints((sid,),4)+_ints((4 if sid == 211 else 3,0))+bytes((129,1,1,2+has))+bytes(2)+_ints((1,),4)+_ints((ordinal,))
        try:
            bootstrap_v2.decode_inventory_entry_header(header)
            actual = 1
        except b.BootstrapReject:
            actual = 0
        _check(actual == admitted, 'ordinal.admission')
        result.extend(_ints((sid,ordinal,has,admitted)))
    return bytes(result)


def _frames(raw):
    projection = content.projection_view(content.stream_validation(raw))
    offset,frames = 4,{}
    for _ in projection.records:
        size = int.from_bytes(raw[offset+4:offset+8],'big')
        frame = raw[offset:offset+8+size]
        frames[int.from_bytes(frame[:2],'big')] = frame
        offset += 8+size
    _check(offset == len(raw), 'frames.eof')
    return projection,frames


def _twelve(compiled, required, all_frames, miniature):
    rp,rf = required
    ap,af = all_frames
    mp,mf = _frames(miniature.base_stream)
    result = bytearray(_ints(x for i,p in enumerate((rp,ap,mp)) for x in (i,len(p.records),p.root_record_id)))
    for rows in (((0,2),(2,2)),((0,2),(2,2),(4,4)),((0,1),(1,1),(2,2),(4,2),(6,2),(8,2)),
                 ((0,2),(2,2)),((0,2),),((0,2),(2,1),(3,1),(4,2),(6,2),(8,4),(12,2),(14,4),(18,4))):
        result.extend(_layout(rows))
    result.extend(_ints(x for row in ((1,1,0),(2,5,0),(3,4,0),(4,7,0),(5,10,0),(6,3,0),(7,18,0),
        (8,10,1),(9,3,0),(10,6,1),(11,6,1),(12,20,0),(13,22,0),(14,4,1)) for x in row))
    result.extend(miniature.value)
    kinds = {rid:int.from_bytes(frame[2:4],'big') for rid,frame in rf.items()}
    _check(tuple(kinds[i] for i in range(1,13)) == (2,3,4,7,8,9,8,10,4,11,12,13), 'required.subject')
    refs = ((5,6,2),(5,8,0),(7,6,8),(7,8,2),(6,0,8),(3,0,2),
            (10,2,4),(12,len(rf[12])-10,13),(rp.root_record_id,0,13),(rp.root_record_id,2,0))
    for owner,offset,kind in refs:
        value = int.from_bytes(rf[owner][8+offset:10+offset],'big')
        _check(kind == 0 or kinds.get(value) == kind, 'reference.kind')
        if kind:
            _check(value > owner if owner == 12 else value < owner, 'reference.order')
        result.extend(_ints((owner,offset,value,kind)))
    result.extend(_ints(x for row in ((3,5,8),(3,5,7),(8,1,9),(8,1,8)) for x in row))
    bridges = []
    _check(len(compiled.atomic_assignments) <= 4095 and len(compiled.game_payloads) == 64
           and len(compiled.fixture_payloads) == 10, 'source.subjects')
    for sid,namespace,payload in ((100,2,compiled.game_payloads[0]),(200,3,compiled.fixture_payloads[0])):
        matches = tuple(a for a in compiled.atomic_assignments if a.section_id == sid)
        _check(len(matches) == 1 and len(matches[0].record_ids) == 2, 'namespace.assignment')
        binding,opaque = matches[0].record_ids
        data,raw = af[binding],af[opaque]
        _check(int.from_bytes(data[2:4],'big') == 8 and len(data) == 18
               and data[8:14] == b'\x01\0'+_ints((namespace,1)), 'namespace.binding')
        _check(int.from_bytes(raw[2:4],'big') == 9 and raw[8:10] == _ints((binding,)) and raw[10:] == payload, 'namespace.opaque')
        bridges.append((sid,binding,opaque,namespace,data,raw))
    result.extend(b''.join(row[4] for row in bridges))
    result.extend(b''.join(row[5][8:10] for row in bridges))
    for sid,binding,opaque,namespace,_,_ in bridges:
        result.extend(_ints((sid,),4)+_ints((binding,opaque,namespace,1)))
    result.extend(build_position_teaching_v2(compiled).value)
    return bytes(result)


def build_route_definitions_v2(
    compiled: SliceCompilation, content_fixture_raw: bytes | None = None
) -> tuple[RouteDefinitionV2, ...]:
    """Build fresh immutable values, rechecking source bytes before projection."""
    _check(type(compiled) is SliceCompilation, 'compiled.type')
    for raw,digest in ((compiled.required_content_bytes,compiled.required_content_sha256),
                       (compiled.content_bytes,compiled.content_sha256)):
        _check(type(raw) is bytes and 4 <= len(raw) <= 524288, 'stream.bound')
        _check(type(digest) is str and sha256(raw).hexdigest() == digest, 'stream.digest')
    required,all_frames = _frames(compiled.required_content_bytes),_frames(compiled.content_bytes)
    _check(required[0] == compiled.required_projection and all_frames[0] == compiled.projection, 'stream.projection')
    if content_fixture_raw is None:
        source = Path(__file__).resolve().parents[2] / 'conformance/content-v0.json'
        with source.open('rb') as handle:
            content_fixture_raw = handle.read(1048577)
    _check(type(content_fixture_raw) is bytes and 1 <= len(content_fixture_raw) <= 1048576, 'fixture.bound')
    from .content_teaching_v2 import build_content_teaching_v2
    miniature = build_content_teaching_v2(content_fixture_raw)
    common = _common_examples()
    seven,eight,encoded = _seven_eight(common)
    values = (*_first_six(),seven,eight,_nine(),_ten(common,encoded),_eleven(common),
              _twelve(compiled,required,all_frames,miniature))
    _check(tuple(map(len,values)) == (16,64,96,296,226,210,636,544,464,443,314,2421), 'value.sizes')
    metadata = ((0,()),(0,(1,)),(1,(1,)),(1,(2,3)),(2,(3,4)),(2,(5,)),
                (3,(6,)),(3,(6,7)),(4,(6,8)),(4,(7,8,9)),(5,(10,)),(5,(11,)))
    return tuple(RouteDefinitionV2(i,stage,dependencies,value)
                 for i,((stage,dependencies),value) in enumerate(zip(metadata,values),1))
