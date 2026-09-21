"""Bounded interpretation of observed numeric DEFINE relationships.

No source fixture, authoring builder, file lookup or generated clean byte string
is an admission input. These finite checks are not a fresh recipient result or
a universal refinement proof for an arbitrary carried VM program. In particular,
affine extraction requires a separate observed-109 program refinement check.
"""
from dataclasses import dataclass, replace
from math import gcd

from . import bootstrap as b, bootstrap_v2, chess, content as c, m2_codec, recipe_wire_v1
from .m2_transport_v2 import aggregate_replica_group
from .m2_decoder import DecoderError

_WIDTHS = (16,64,96,296,226,210,636,544,464,294,314,2421)
_AUTHORITY = object()


def _check(ok, label):
    if not ok:
        raise DecoderError('route-v2.semantic.'+label)


class _Read:
    def __init__(self, raw, label):
        self.raw, self.at, self.label = raw, 0, label

    def take(self, length):
        _check(type(length) is int and 0 <= length <= len(self.raw)-self.at, self.label+'.length')
        start = self.at
        self.at += length
        return self.raw[start:self.at]

    def n(self, width=2):
        return int.from_bytes(self.take(width), 'big')

    def row(self, widths):
        return tuple(self.n(width) for width in widths)

    def expect(self, values, widths=None):
        widths = (2,)*len(values) if widths is None else widths
        _check(self.row(widths) == tuple(values), self.label+'.relationship')

    def layout(self, pairs):
        self.expect((len(pairs),))
        for pair in pairs:
            self.expect(pair)

    def end(self):
        _check(self.at == len(self.raw), self.label+'.trailing')


@dataclass(frozen=True, slots=True)
class DefinitionCommitmentsV2:
    """Locally checked observed fact12; context checks still require recovery."""
    fact12: bytes
    _authority: object


@dataclass(frozen=True, slots=True)
class ContextValidationV2:
    """Evidence coverage; absent contexts never become successful claims."""
    required_context_checked: bool
    all_context_checked: bool
    section_membership_checked: bool


def _accepts(raw):
    try:
        c.stream_validation(raw)
        return 1
    except c.ContentReject:
        return 0


def _common_ok(raw):
    try:
        block = b.decode_common_block(raw, 8)
    except b.BootstrapReject:
        return 0, 0
    try:
        section = b.decode_section_envelope(block.payload)
        agreement = (block.section_id == section.section_id
            and block.section_type == section.section_type
            and block.section_version == section.section_version
            and block.section_envelope_length == len(block.payload))
    except b.BootstrapReject:
        agreement = False
    return 1, int(agreement)


def _patched(raw, offset, width, value, recheck=False):
    _check(0 <= offset <= len(raw)-width and width in (1,2,4)
           and 0 <= value < 1 << (8*width), 'patch')
    result = bytearray(raw)
    result[offset:offset+width] = value.to_bytes(width,'big')
    if recheck:
        result[187:] = b.crc32c_v0(b.LOCAL_DOMAIN+result[:187]).to_bytes(4,'big')
    return bytes(result)


def _facts_1_6(definitions, package):
    r = _Read(definitions[0], 'fact1')
    for value in (0,128,170,240,204,1,129,24):
        r.expect((value,value^255),(1,1))
    r.end()
    r = _Read(definitions[1], 'fact2')
    base = r.raw[:8]
    _check(base == bytes.fromhex('80402010080403c1'), 'fact2.subject')
    bits = tuple((byte >> shift)&1 for byte in base for shift in range(7,-1,-1))
    images = []
    for view in b.entry_hypotheses(bits,64)[::2]:
        image = bytes(sum(view[i*8+j] << (7-j) for j in range(8)) for i in range(8))
        images.append(image)
        _check(r.take(8) == image, 'fact2.transform')
    _check(len(set(images+[bytes(x^255 for x in value) for value in images])) == 16,'fact2.distinct')
    r.end()
    r = _Read(definitions[2], 'fact3')
    for n in (0,1,2,3,4,5,7,8,15,16,24,31):
        picture = r.n(4)
        r.expect((n,255^n,n),(1,1,2))
        _check(picture == (1 << n)-1 and picture.bit_count() == n,'fact3.count')
    r.end()
    r = _Read(definitions[3], 'fact4')
    r.expect((32,8,24,6))
    for sector in range(4):
        for u,v in ((0,0),(0,23),(7,0),(7,23),(0,1),(1,0)):
            row,col = b.sector_cell(32,8,sector,24*u+v)
            r.expect((sector,u,v,row,col,24*u+v))
    r.end()
    r = _Read(definitions[4], 'fact5')
    for layout in (
        ((0,8),(8,2),(10,1),(11,1),(12,2),(14,2),(16,4),(20,4),(24,4),(28,2),(30,2)),
        ((0,1),(1,1),(2,2),(4,4)),
        ((0,8),(8,2),(10,2),(12,2),(14,2),(16,2),(18,2),(20,4),(24,4),(28,4),(32,4),(36,8),(44,4),(48,16)),
        ((0,2),(2,1),(3,1),(4,4),(8,4),(12,4)),
        ((0,2),(2,2),(4,2),(6,2),(8,4),(12,4),(16,8),(24,4),(28,4)),
        ((0,2),(2,1),(3,1),(4,4),(8,4))):
        r.layout(layout)
    recipe = next(item for item in package.logical.recipes if item.recipe_id == 109)
    nodes_size = sum(6+2*len(n.arguments)+2*(n.opcode in (2,5,22))
                     +8*(n.opcode in (1,5,14,22,25)) for n in recipe.nodes)
    descriptors = 12*(len(recipe.inputs)+len(recipe.outputs))
    r.expect((109,32,len(recipe.inputs),len(recipe.outputs),12,descriptors,
              len(recipe.nodes),nodes_size,32+descriptors+nodes_size))
    r.end()
    r = _Read(definitions[5], 'fact6')
    for opcode in range(1,26):
        arity = 0 if opcode in (1,2,24,25) else 1 if opcode in (5,14,22) else 3 if opcode in (3,20,23) else 2
        aux,immediate = 2*(opcode in (2,5,22)),8*(opcode in (1,5,14,22,25))
        r.expect((opcode,arity,2*arity,aux,immediate,6+2*arity+aux+immediate),(1,)*6)
    for row in ((0,0,1,64),(1,0,1,1),(2,0,1,1048576),(3,1,0,1048576),(4,2,0,1048576),(5,0,16,16)):
        r.expect(row,(1,1,4,4))
    r.end()


def _facts_7_8(definitions):
    r = _Read(definitions[6], 'fact7')
    r.layout(((0,2),(2,2),(4,4),(8,2),(10,2),(12,2),(14,2),(16,2),(18,2),(20,2),(22,4),(26,4),(30,157),(187,4)))
    r.layout(((0,2),(2,4),(6,2),(8,2),(10,1),(11,1),(12,2),(14,4)))
    _check(r.take(8) == b.LOCAL_DOMAIN and r.take(8) == b.SECTION_DOMAIN,'fact7.domains')
    for subject in (bytes.fromhex('313233343536373839'),bytes(range(9))):
        _check(r.take(9) == subject and r.n(4) == b.crc32c_v0(subject),'fact7.crc')
    common = (r.take(191),r.take(191))
    for i,raw in enumerate(common):
        block = b.decode_common_block(raw,8)
        section = b.decode_section_envelope(block.payload)
        _check((block.section_id,block.semantic_copy_id,block.section_type,block.section_version,
                block.fragment_index,block.fragment_count,block.section_envelope_length) == (400,0,4,0,0,1,23)
               and (section.section_id,section.section_type,section.section_version,section.closure_class,
                    section.check_id,section.dependencies,section.payload) == (400,4,0,129,1,(),bytes((i,))), 'fact7.common')
        _check(_common_ok(raw) == (1,1),'fact7.agreement')
    mutations = ((2,2,1,1),(14,2,1,1),(26,2,1,1),(18,2,0,1),(16,2,1,1),
                 (4,2,1,1),(22,2,1,1),(48,1,1,0),(187,1,common[0][187]^1,0),(53,1,1,1))
    for mutation in mutations:
        r.expect(mutation)
        r.expect(_common_ok(_patched(common[0],*mutation[:3],bool(mutation[3]))))
    r.end()
    r = _Read(definitions[7], 'fact8')
    r.expect((24,9,8,216,192,191,1,0))
    for i in range(24):
        r.expect((9*i,8*i))
    encoded = []
    for raw in common:
        wire = r.take(216)
        _check(wire == m2_codec.eh72_encode_unit(raw),'fact8.encoding')
        recovered = b''.join(m2_codec.eh72_decode(wire[i:i+9]).decoded for i in range(0,216,9))
        _check(recovered == raw+b'\0','fact8.decoding')
        encoded.append(wire)
    r.end()
    return common,tuple(encoded)


def _smallest_slot(interior, units):
    population,affine,window = interior**2,2*interior-1,max(32,interior//8)
    for candidate in range(1,units):
        if gcd(candidate,units) != 1:
            continue
        admitted = True
        for distance in range(1,5):
            residue = candidate*distance%units
            for delta in (residue,residue-units):
                row,column = divmod(affine*1728*delta%population,interior)
                rows = (row,) if column == 0 else (row,(row+1)%interior)
                if any(max(min(item,interior-item),min(column,interior-column)) < window for item in rows):
                    admitted = False
        if admitted:
            return candidate
    raise DecoderError('route-v2.semantic.fact9.slot-absent')


def _fact9(raw, package):
    r = _Read(raw,'fact9')
    table = next(t for t in package.logical.tables if t.table_id == 17)
    _check((table.element_type,table.element_width,table.element_count,len(table.payload)) == (b.UINT,8,256,256),'fact9.table')
    geometries = []
    for side,width in ((2040,128),(1952,128)):
        interior = side-2*width
        population = interior**2
        units = population//1728
        slot = table.payload[interior//8]
        _check(slot == _smallest_slot(interior,units),'fact9.slot')
        affine,offset = 2*interior-1,(8*40503+257*width)%population
        r.expect((side,width,interior,population,units,slot,pow(slot,-1,units),affine,pow(affine,-1,population),offset),(4,)*10)
        geometries.append((population,units,slot,affine,offset))
    for population,units,slot,affine,offset in geometries:
        for unit,bit in ((1,0),(1,1727),(units,0),(units,1727),(units//slot+2,0)):
            at = slot*(unit-1)%units
            logical = 1728*at+bit
            physical = (affine*logical+offset)%population
            r.expect((unit,bit,at,logical,physical,0),(4,)*6)
            _check(pow(affine,-1,population)*(physical-offset)%population == logical
                   and pow(slot,-1,units)*at%units+1 == unit,'fact9.inverse')
        for logical in (1728*units-1,1728*units,population-1):
            physical = (affine*logical+offset)%population
            if logical < units*1728:
                at,bit = divmod(logical,1728)
                unit,kind = pow(slot,-1,units)*at%units+1,0
            else:
                unit,bit,at,kind = 0,0,0,1
            r.expect((unit,bit,at,logical,physical,kind),(4,)*6)
    r.end()


def _flip(raw, positions):
    result = bytearray(raw)
    for bit in positions:
        result[bit//8] ^= 1 << (7-bit%8)
    return bytes(result)


def _group(lanes, expected_section):
    obs = tuple(None if lane is None else m2_codec.CopyObservation(lane,()) for lane in lanes)
    group = aggregate_replica_group(obs)
    lane_blocks = {block for state,block in zip(group.lane_states,group.lane_blocks,strict=True) if state in (2,3)}
    rep = group.repetition_state == 3
    distinct = lane_blocks | ({group.repetition_block} if rep else set())
    identities = tuple((v.section_id,v.semantic_copy_id,v.section_type,v.section_version,
                        v.fragment_index,v.fragment_count,v.section_envelope_length)
                       for v in (b.decode_common_block(raw,8) for raw in distinct))
    identity = bool(identities) and all(value == (expected_section,0,4,0,0,1,23) for value in identities)
    row = (len(lanes),sum(x is not None for x in lanes),len(lane_blocks),int(rep),
           int(rep and group.repetition_block in lane_blocks),int(identity),
           int(identity and len(distinct) == 1),int(identity and len(distinct)>1))
    return group,row,distinct


def _fact10(raw, common, encoded):
    r = _Read(raw,'fact10')
    last = 0
    for sid,fragment,count,factor in ((1,0,2,5),(1,1,2,5),(211,0,2,2),(211,1,2,2)):
        r.expect((sid,fragment,count,factor,last+1,last+factor),(4,)*6)
        last += factor
    r.expect((0,4,8,10,12,16,18,22),(1,)*8)
    a,z = encoded
    first = (a,)+tuple(_flip(z,(2*i,2*i+1)) for i in range(4))
    second = tuple(_flip(z,(2*i,2*i+1)) for i in range(5))
    lane_sets = ((None,)*5,(_flip(z,(0,1)),),(a,),(a,)*5,first,second,(a,None),(a,z),(a,))
    for index,lanes in enumerate(lane_sets):
        _,row,_ = _group(lanes,401 if index == 8 else 400)
        r.expect(row,(1,)*8)
    for construction,lanes in enumerate((first,second)):
        for index,lane in enumerate(lanes):
            clean = construction == 0 and index == 0
            pair = (0,0) if clean else (2*(index-1 if construction == 0 else index),2*(index-1 if construction == 0 else index)+1)
            r.expect((1 if clean else 2,0 if clean else 2,*pair),(1,1,2,2))
            _check(lane == _flip(encoded[0 if clean else 1],() if clean else pair),'fact10.lane')
        group,_,distinct = _group(lanes,400)
        mask = sum(1 << i for i,block in enumerate(common) if block in distinct)
        r.expect((*group.lane_states,group.repetition_state,group.distinct_candidate_count,group.group_state,mask),(1,)*9)
    for length in (22,157,158,314,315):
        count = (length+156)//157
        r.expect((length,count,length-157*(count-1),length))
    r.end()


def _closure(adjacency, selected):
    edges = {i:tuple(j for j in range(4) if adjacency & (1 << (15-4*i-j))) for i in range(4)}
    colors = [0]*4
    def visit(i):
        if colors[i] == 1:
            raise ValueError('cycle')
        if colors[i] == 2:
            return
        colors[i] = 1
        for child in edges[i]:
            visit(child)
        colors[i] = 2
    try:
        for i in range(4):
            visit(i)
    except ValueError:
        return 0,0
    chosen = {i for i in range(4) if selected & (1 << (3-i))}
    for _ in range(4):
        chosen.update(child for i in tuple(chosen) for child in edges[i])
    return sum(1 << (3-i) for i in chosen),1


def _fact11(raw, common):
    r = _Read(raw,'fact11')
    r.layout(((0,2),(2,2),(4,2),(6,2)))
    r.layout(((0,4),(4,2),(6,2),(8,1),(9,1),(10,1),(11,1),(12,2),(14,4),(18,2)))
    for factor in (1,2,5):
        for ordinal in (0,1):
            r.expect((factor,ordinal,2*factor+ordinal),(1,)*3)
    r.expect((1,2,0,5,1,2,3,4,5))
    for bits in ('011111','100000','110000','111011','110100','111101','111100','111110','111111','000000','010101','101111'):
        i,req,all_,typed_req,typed_all,every = map(int,bits)
        required,all_ok = i&req&typed_req,i&req&typed_req&all_&typed_all
        r.expect((i,req,all_,typed_req,typed_all,every,required,all_ok,all_ok&every),(1,)*9)
    for wire in (8,7):
        changed = _patched(common[0],0,2,wire,True)
        r.expect((wire,8,1,_common_ok(changed)[0]))
    for rows in (((4,2,4),(10,6,2),(12,8,2)),((2,0,4),(6,4,2),(8,6,2),(10,8,1),(11,9,1),(12,12,2),(14,14,4))):
        r.expect((len(rows),))
        for row in rows:
            r.expect(row,(1,)*3)
    r.expect((2,16,17,18))
    for adjacency,selected in ((0x7000,8),(0x4200,8),(0,4),(0x4800,8)):
        closure,valid = _closure(adjacency,selected)
        r.expect((adjacency,selected,closure,valid),(2,1,1,1))
    for sid,ordinal,has in ((100,0,1),(163,63,1),(211,65535,0),(101,0,1)):
        header = (sid.to_bytes(4,'big')+(4 if sid == 211 else 3).to_bytes(2,'big')+b'\0\0'
                  +bytes((129,1,1,2+has))+b'\0\0'+(1).to_bytes(4,'big')+ordinal.to_bytes(2,'big'))
        try:
            bootstrap_v2.decode_inventory_entry_header(header)
            admitted = 1
        except b.BootstrapReject:
            admitted = 0
        r.expect((sid,ordinal,has,admitted))
    r.end()


def _record_dependencies(payload):
    """Public typed references for pruning finite synthetic role examples."""
    if isinstance(payload,c.ContentAtomSchema):
        return tuple(e.label_text_ref for e in payload.entries)
    if isinstance(payload,(c.ContentAtomVector,c.ContentMatrix)):
        return (payload.atom_schema_ref,)
    if isinstance(payload,c.ContentRegionSet):
        return (payload.surface_matrix_ref,)+tuple(x.label_ref for x in payload.regions if x.label_ref)
    if isinstance(payload,c.ContentSemanticBinding):
        return (payload.argument,)+( (payload.auxiliary,) if payload.binding_class == 2 else ())
    if isinstance(payload,c.ContentOpaqueData):
        return (payload.data_binding_ref,)
    if isinstance(payload,c.ContentPredicateResult):
        return (payload.predicate_binding_ref,payload.subject_opaque_data_ref,payload.result_atom_vector_ref)
    if isinstance(payload,c.ContentFeedback):
        return tuple(x for x in (payload.display_ref,payload.predicate_result_ref) if x)
    if isinstance(payload,c.ContentPassiveTrace):
        return tuple(x for x in (payload.presentation_ref,payload.region_set_ref,payload.resulting_presentation_ref,
                               payload.limitation_text_ref,payload.expected_feedback_ref) if x)
    if isinstance(payload,c.ContentLessonNode):
        return tuple(x for x in (payload.presentation_ref,payload.region_set_ref,payload.predicate_result_ref,
                               payload.passive_trace_ref,payload.default_feedback_ref,payload.default_next_node_ref,
                               *(v for case in payload.cases for v in (case.feedback_ref,case.next_node_ref))) if x)
    if isinstance(payload,c.ContentRoot):
        return (payload.entry_node_ref,)
    return ()


def _role_example(role, mode, predicate, trace, feedback):
    packed = mode == 1
    records = (
        c.ContentRecordView(1,c.ContentText('x')),
        c.ContentRecordView(2,c.ContentAtomSchema(1,1,(),0,255)),
        c.ContentRecordView(3,c.ContentMatrix(2,1,1,(0,))),
        c.ContentRecordView(4,c.ContentRegionSet(3,(c.ContentRegion(1,0,0,1,0,1,1),))),
        c.ContentRecordView(5,c.ContentSemanticBinding(1,1,1,2,1)),
        c.ContentRecordView(6,c.ContentOpaqueData(5,(0,))),
        c.ContentRecordView(7,c.ContentSemanticBinding(2,1,1,5,2)),
        c.ContentRecordView(8,c.ContentAtomVector(2,(1,))),
        c.ContentRecordView(9,c.ContentPredicateResult(7,6,8)),
        c.ContentRecordView(10,c.ContentFeedback(feedback,3,9 if packed else 0)),
        c.ContentRecordView(11,c.ContentFeedback(2,3,9)),
        c.ContentRecordView(12,c.ContentPassiveTrace(3,4,3,1 if role == 4 else 0,
                              (b'\3\0\0\0',),1 if packed else 3,11 if packed else 10,0)),
        c.ContentRecordView(13,c.ContentLessonNode(role,1,mode,0,3,4,9 if predicate else 0,
                              12 if trace else 0,1,2,
                              (c.ContentLessonCase(1,(),11,0),) if packed else (),10,13 if packed else 0)),
        c.ContentRecordView(14,c.ContentRoot(13,2)))
    by_id = {record.record_id:record for record in records}
    chosen,queue = set(),[14]
    while queue:
        rid = queue.pop()
        if rid not in chosen:
            chosen.add(rid)
            queue.extend(_record_dependencies(by_id[rid].payload))
    return c.encode_content_v0(c.ContentAuthoringProjection(0,tuple(r for r in records if r.record_id in chosen)))


def _miniature(raw):
    r = _Read(raw,'fact12.miniature')
    _check(r.n(4) == 575,'fact12.miniature.length')
    base = r.take(575)
    projection = c.stream_validation(base)
    view = c.projection_view(projection)
    _check(len(view.records) == 29 and view.root_record_id == 29
           and tuple(sorted({record.kind for record in view.records})) == tuple(range(1,15)), 'fact12.miniature.coverage')
    _check(r.n(4) == 1056,'fact12.supplement.length')
    supplement = _Read(r.take(1056),'fact12.supplement')
    r.end()
    scalar = ((0,2,1),(2,2,28),(4,2,0),(19,2,1),(563,2,65535),(571,2,0),
        (571,2,27),(573,2,7),(573,2,9),(573,2,65535),(555,2,2),(555,2,4),
        (6,2,0),(167,2,0),(167,2,12),(167,2,1),(169,2,0),(178,1,6),
        (129,2,1),(145,1,0),(158,1,0),(158,1,2),(193,2,3),(223,1,3),
        (223,1,6),(191,1,0),(224,2,1),(302,2,0),(314,1,6),(329,2,6),
        (343,2,1),(345,2,9),(359,2,19),(373,2,0),(493,2,1),(456,1,1),
        (514,1,1),(544,1,0),(439,1,2),(443,2,26),(435,4,16777217),(561,2,27),
        (413,2,1),(192,1,1),(250,2,3),(258,2,1),(545,2,12),(12,1,255))
    supplement.expect((48,))
    for offset,width,new in scalar:
        old = int.from_bytes(base[offset:offset+width],'big')
        result = _accepts(_patched(base,offset,width,new))
        supplement.expect((offset,width,old,new,result),(2,2,4,4,2))
    supplement.expect((6,))
    roles = ((1,3,1,1,0,0,0,1,1,3),(2,3,1,1,0,0,0,1,1,3),
             (3,3,1,1,0,0,1,1,1,3),(4,3,0,0,0,0,0,1,5,3),
             (5,1,1,1,1,4096,1,1,3,2),(5,2,0,0,0,0,0,0,1,3))
    for row in roles:
        supplement.expect(row,(1,1,1,1,2,2,1,1,1,1))
        role,mode,pmin,pmax,_,_,tmin,tmax,feedback,outcome = row
        for predicate in range(pmin,pmax+1):
            for trace in range(tmin,tmax+1):
                example = _role_example(role,mode,predicate,trace,feedback)
                parsed = c.stream_validation(example)
                state = c.new_run(parsed)
                # Packed default needs a nonaccepted region; other modes commit empty.
                if mode == 1:
                    state,_ = c.step(parsed,state,b'\1\0\0\1')
                state,result = c.step(parsed,state,b'\3\0\0\0')
                _check(result == 3 and c.run_state_view(state).outcome == outcome,'fact12.role-outcome')
    supplement.expect((4,))
    authoring = c.authoring_from_validated(view)
    for kind,direct,transitive in ((6,1,1),(6,2,2),(4,1,1),(6,0,0)):
        changed = []
        for record in authoring.records:
            value = record.payload
            if kind == 6 and direct != 1 and record.record_id == 13:
                fields = value.fields[:-1]+((replace(value.fields[-1],count=2),) if direct == 2 else ())
                value = replace(value,fields=fields)
            if kind == 6 and direct != 1 and record.record_id == 14:
                fields = value.field_values[:-1]+((c.ContentRecordRefFieldValue((12,12)),) if direct == 2 else ())
                value = replace(value,field_values=fields)
            if kind == 4 and record.record_id == 28:
                value = replace(value,presentation_ref=12)
            changed.append(c.ContentRecordView(record.record_id,value))
        try:
            c.encode_content_v0(c.ContentAuthoringProjection(0,tuple(changed)))
            accepted = 1
        except c.ContentAuthoringError:
            accepted = 0
        supplement.expect((kind,12 if kind == 4 else 14,12,direct,transitive,accepted))
    supplement.expect((8,))
    actions = ((26,('03000000',)),(26,('01000002','03000000')),
               (26,('01000003','03000000')),(27,('01000002','01000001','03000000')),
               (28,('01000001','01000001','03000000')),(28,('01000002','01000001','03000000')),
               (26,('01000001','01000001')),(26,('02000000','03000000')))
    by_id = {record.record_id:record.payload for record in view.records}
    for node,sequence in actions:
        state = c.new_run(projection)
        for _ in range(node-26):
            state,_ = c.step(projection,state,b'\3\0\0\0')
            state = c.advance_committed(projection,state)
        _check(c.run_state_view(state).current_node_id == node,'fact12.action-start')
        wire_actions = tuple(bytes.fromhex(value) for value in sequence)
        for action in wire_actions:
            state,result = c.step(projection,state,action)
        actual = c.run_state_view(state)
        selections = actual.selection_buffer
        if actual.phase == 2:
            response = actual.committed_response
            selections = tuple(int.from_bytes(response[i:i+2],'big') for i in range(3,len(response),2))
        _check(len(selections) <= 2,'fact12.selection-count')
        supplement.expect((node,len(wire_actions)),(2,1))
        _check(supplement.take(12) == b''.join(wire_actions).ljust(12,b'\0'),'fact12.actions')
        supplement.expect((actual.phase,result,by_id[node].response_shape,len(selections)),(1,1,1,1))
        supplement.expect((*selections,*(0 for _ in range(2-len(selections)))))
        supplement.expect((actual.outcome,actual.feedback_ref,actual.next_node_ref,
                           actual.global_remaining,actual.local_remaining),(1,2,2,2,2))
    supplement.end()


def _position_local(raw):
    r = _Read(raw,'fact12.position')
    r.expect((2,))
    r.layout(((0,64),(64,1),(65,1),(66,1)))
    r.expect((0,43,67))
    triples = tuple((204-27*i,8*i,8) for i in range(8))+((258,64,3),)
    r.expect((9,))
    for row in triples:
        r.expect(row)
    first = r.take(67)
    _check(chess.encode_position(chess.decode_position(first)) == first,'fact12.position-wire')
    r.expect((1,717,22,68,23,67))
    tagged,second = r.take(68),r.take(67)
    _check(tagged == b'\1'+second and chess.encode_position(chess.decode_position(second)) == second,'fact12.variant')
    r.layout(((10,6),(4,6),(1,3),(0,1)))
    r.expect((12,))
    wires = tuple(0xc790+2*i for i in range(8))+(0x1950,0xe6a0,0x31c1,0x30c0)
    for wire in wires:
        try:
            move = chess.decode_move(wire.to_bytes(2,'big'))
            _check(chess.encode_move(move) == wire.to_bytes(2,'big'),'fact12.move-roundtrip')
            valid = 1
        except chess.ChessReject:
            valid = 0
        r.expect((wire,(wire>>10)&63,(wire>>4)&63,(wire>>1)&7,valid),(2,1,1,1,1))
    r.expect((1,589,69))
    r.layout(((0,2),(2,66),(68,1)))
    r.end()


def _fact12(raw, *, validate_mini=True):
    r = _Read(raw,'fact12')
    contexts = tuple(r.row((2,2,2)) for _ in range(3))
    _check(tuple(row[0] for row in contexts) == (0,1,2)
           and all(1 <= count <= root <= 65535 for _,count,root in contexts)
           and contexts[2] == (2,29,29),'fact12.context')
    for layout in (((0,2),(2,2)),((0,2),(2,2),(4,4)),((0,1),(1,1),(2,2),(4,2),(6,2),(8,2)),
                   ((0,2),(2,2)),((0,2),),((0,2),(2,1),(3,1),(4,2),(6,2),(8,4),(12,2),(14,4),(18,4))):
        r.layout(layout)
    for row in ((1,1,0),(2,5,0),(3,4,0),(4,7,0),(5,10,0),(6,3,0),(7,18,0),
                (8,10,1),(9,3,0),(10,6,1),(11,6,1),(12,20,0),(13,22,0),(14,4,1)):
        r.expect(row)
    miniature = r.take(1639)
    if validate_mini:
        _miniature(miniature)
    references = tuple(r.row((2,)*4) for _ in range(10))
    for owner,offset,target,kind in references:
        _check(1 <= owner <= contexts[0][2] and kind <= 14 and offset <= 16384,'fact12.reference-shape')
        _check(kind == 0 or 1 <= target <= contexts[0][2],'fact12.reference-target')
    for a,z,budget in ((3,5,8),(3,5,7),(8,1,9),(8,1,8)):
        r.expect((a,z,budget))
    bindings = (r.take(18),r.take(18))
    opaque_prefixes = (r.n(),r.n())
    bridges = tuple(r.row((4,2,2,2,2)) for _ in range(2))
    for index,(section,binding,opaque,namespace,code) in enumerate(bridges):
        frame = bindings[index]
        _check(section == (100,200)[index] and namespace == index+2 and code == 1
               and 1 <= binding < opaque < contexts[1][2] and opaque_prefixes[index] == binding
               and int.from_bytes(frame[:2],'big') == binding
               and frame[2:8] == b'\0\10\0\0\0\12'
               and frame[8:10] == b'\1\0' and int.from_bytes(frame[10:12],'big') == namespace
               and int.from_bytes(frame[12:14],'big') == code,
               'fact12.namespace-shape')
    suffix = r.take(408)
    _position_local(suffix)
    r.end()
    return contexts,references,bindings,bridges,suffix


def validate_local_definitions(definitions, package, *, side, width, sector):
    """Validate local carried facts; return commitments requiring stream binding.

    The caller separately admits the complete route skeleton and VM examples.
    Parsed package objects are revalidated from observed wire bytes here.
    """
    _check(type(definitions) is tuple and len(definitions) == 12
           and all(type(raw) is bytes and len(raw) == size for raw,size in zip(definitions,_WIDTHS,strict=True)), 'definitions')
    _check(type(side) is int and type(width) is int and type(sector) is int
           and 64 <= side <= 2048 and side%8 == 0 and 8 <= width <= 128 and width%8 == 0
           and 2*width+8 <= side and 0 <= sector < 4,'geometry')
    _check(type(package) is recipe_wire_v1.RecipePackageV1,'package-type')
    try:
        checked = recipe_wire_v1.decode_recipe_package_v1(package.encoded,8)
        _facts_1_6(definitions,checked)
        common,encoded = _facts_7_8(definitions)
        _fact9(definitions[8],checked)
        _fact10(definitions[9],common,encoded)
        _fact11(definitions[10],common)
        _fact12(definitions[11])
    except DecoderError:
        raise
    except (ValueError,TypeError,KeyError,IndexError,StopIteration,OverflowError) as error:
        raise DecoderError('route-v2.semantic.invalid') from error
    return DefinitionCommitmentsV2(definitions[11],_AUTHORITY)


def _stream(raw, count, root):
    _check(type(raw) is bytes and 4 <= len(raw) <= 1048576,'context.stream-bound')
    projection = c.projection_view(c.stream_validation(raw))
    _check(len(projection.records) == count and projection.root_record_id == root,'context.count-root')
    records = {record.record_id:record for record in projection.records}
    frames,payloads,cursor = {},{},4
    for record in projection.records:
        end = cursor+8+int.from_bytes(raw[cursor+4:cursor+8],'big')
        frames[record.record_id],payloads[record.record_id] = raw[cursor:end],raw[cursor+8:end]
        cursor = end
    _check(cursor == len(raw),'context.framing')
    return records,frames,payloads


def _moves(raw):
    _check(len(raw)%2 == 0 and len(raw) <= 16384,'context.moves')
    return tuple(chess.decode_move(raw[i:i+2]) for i in range(0,len(raw),2))


def _fixture(raw, kind=1):
    r = _Read(raw,'context.fixture')
    r.expect((0,kind),(1,1))
    prior = r.take(r.n())
    subject = r.take(r.n())
    expected = r.take(r.n())
    r.end()
    variant = 1 if kind == 1 else 3
    _check(len(prior) <= 4096 and len(subject) == 2
           and len(expected) == (68 if variant == 1 else 70)
           and expected[0] == variant,'context.fixture-shape')
    replay = chess.replay_from_start(_moves(prior))
    result = chess.apply_move(replay,chess.decode_move(subject))
    _check(chess.encode_position(result.position) == expected[1:68],'context.fixture-replay')
    if variant == 3:
        checked = chess.king_in_check(chess.validate_local(result.position),result.position.side_to_move)
        _check(expected[68:] == bytes((int(checked),chess.board_terminal(result).code)), 'context.fixture-consequence')
    return prior,subject,expected


def validate_recovered_context(commitments, *, required_bytes, all_bytes, body_payloads=None):
    """Produce knowledge-use evidence over already recovered content.

    Missing streams have no claims checked here; availability is decoder-owned.
    Chess/namespace interpretation failures never change transport availability,
    select another transport candidate, or authorize clean-content fallback.
    Providing decoded body_payloads additionally proves section100/200 framing
    membership. Without that mapping this function claims only stream bindings.
    No unavailable stream is replaced with a source or retained clean stream.
    """
    _check(type(commitments) is DefinitionCommitmentsV2 and commitments._authority is _AUTHORITY
           and type(commitments.fact12) is bytes and len(commitments.fact12) == 2421,'commitments')
    if body_payloads is not None:
        _check(type(body_payloads) is dict and len(body_payloads) <= 4096
               and all(type(sid) is int and 1 <= sid <= 0xffffffff and type(raw) is bytes
                       and 1 <= len(raw) <= 16384 for sid,raw in body_payloads.items()),'context.bodies')
    try:
        # Recheck retained observed bytes: dataclass replacement must not turn a
        # caller-constructed wrapper into authority over unvalidated statements.
        contexts,references,bindings,bridges,suffix = _fact12(commitments.fact12)
        required = None if required_bytes is None else _stream(required_bytes,*contexts[0][1:])
        all_ = None if all_bytes is None else _stream(all_bytes,*contexts[1][1:])
        if required is not None:
            records,frames,payloads = required
            root = contexts[0][2]
            subjects = ((5,6),(5,8),(7,6),(7,8),(6,0),(3,0),(10,2),
                        (12,len(payloads[12])-2),(root,0),(root,2))
            for row,(owner,offset) in zip(references,subjects,strict=True):
                target = int.from_bytes(payloads[owner][offset:offset+2],'big')
                scalar = (owner,offset) in ((5,8),(root,2))
                kind = 0 if scalar else records[target].kind
                _check(row == (owner,offset,target,kind),'context.reference')
                if not scalar:
                    _check((target > owner and kind == 13) if owner == 12 else target < owner,'context.reference-order')
            matrix = records[43].payload
            _check(type(matrix) is c.ContentMatrix and (matrix.rows,matrix.columns) == (20,27),'context.position-matrix')
            extracted = bytearray(67)
            for source,target,count in (tuple((204-27*i,8*i,8) for i in range(8))+((258,64,3),)):
                extracted[target:target+count] = bytes(matrix.cells[source:source+count])
            _check(bytes(extracted) == suffix[82:149],'context.position-extraction')
        if all_ is not None:
            records,frames,payloads = all_
            opaque_subjects = []
            for index,(section,binding,opaque,namespace,code) in enumerate(bridges):
                data = records[binding].payload
                subject = records[opaque].payload
                _check(frames[binding] == bindings[index]
                       and type(data) is c.ContentSemanticBinding
                       and (data.binding_class,data.namespace_id,data.semantic_code) == (1,namespace,code)
                       and type(subject) is c.ContentOpaqueData and subject.data_binding_ref == binding,
                       'context.namespace')
                opaque_subjects.append(bytes(subject.data))
                if body_payloads is not None:
                    _check(section in body_payloads
                           and body_payloads[section].startswith(frames[binding]+frames[opaque]),'context.section-membership')
            game,fixture = opaque_subjects
            _check(len(game) == 69 and int.from_bytes(game[:2],'big') == 33
                   and game[-1] == 0,'context.game-shape')
            moves = _moves(game[2:-1])
            chess.validate_source_record(moves,game[-1])
            first = chess.replay_from_start(moves[:1])
            _check(chess.encode_position(first.position) == suffix[82:149],'context.first-move')
            prior,subject,expected = _fixture(fixture)
            _check(len(fixture) == 90 and len(prior) == 12 and subject == b'\x10\x60'
                   and fixture[22:90] == suffix[161:229]
                   and fixture[23:90] == suffix[229:296] and expected == suffix[161:229], 'context.fixture-extraction')
            _check(chess.encode_move(moves[2]) == b'\x19\x50'
                   and chess.encode_move(moves[3]) == b'\xe6\xa0'
                   and chess.encode_move(moves[0]) == b'\x31\xc0','context.move-subjects')
            fixtures = {}
            for record in records.values():
                value = record.payload
                if type(value) is c.ContentOpaqueData:
                    binding = records[value.data_binding_ref].payload
                    if binding.namespace_id == 3:
                        _check(binding.semantic_code not in fixtures,'context.fixture-code')
                        fixtures[binding.semantic_code] = bytes(value.data)
            _check(all(code in fixtures for code in (1,4,5,6,7)),'context.fixture-count')
            for promotion in range(1,5):
                _,subject,_ = _fixture(fixtures[promotion+3],promotion+3)
                _check(subject == (0xc790+2*promotion).to_bytes(2,'big'),'context.promotion-subject')
            prior,_,_ = _fixture(fixtures[4],4)
            prestate = chess.replay_from_start(_moves(prior))
            try:
                chess.apply_move(prestate,chess.decode_move(b'\xc7\x90'))
                missing_promotion_rejected = False
            except chess.ChessReject:
                missing_promotion_rejected = True
            _check(missing_promotion_rejected,'context.promotion-legality')
            chess.apply_move(prestate,chess.decode_move(b'\xc7\x92'))
    except DecoderError:
        raise
    except (ValueError,TypeError,KeyError,IndexError,StopIteration,OverflowError) as error:
        raise DecoderError('route-v2.semantic.context-invalid') from error
    return ContextValidationV2(required_bytes is not None, all_bytes is not None,
                               all_bytes is not None and body_payloads is not None)
