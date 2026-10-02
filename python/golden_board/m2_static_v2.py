"""Source-built static facts for profile8, without full-gate admission claims."""
from dataclasses import dataclass
from hashlib import sha256

from . import bootstrap as b, canonical_manifest, capacity, identity, m2_codec, m2_policy
from . import m2_policy_v2
from .m2_capacity_v1 import derive_capacity_inputs_v1
from .m2_capacity_v2 import build_capacity_plan
from .m2_carrier import _regularity, evaluate_realism
from .m2_carrier_v2 import DevelopmentCarrier
from .m2_mapping_v2 import mapping_parameters
from .m2_route_receiver_v2 import decode_observed_route_v2
from .m2_route_v2 import build_route_images_v2

PROFILE_ID = 'eh72-hier-r5-r2-r1-lzss-crc32c-v1'
_MAX_U64 = (1 << 64)-1
_SCOPE_NAMES = ('shell','real-protected','capacity-probe','reserve-probe',
                'load-probe','fixed-pad','complete-interior')
_OUTPUTS = ('semantic-envelope','capacity-ledger','ownership-ledger','density-ledger',
            'geometry-search','static-limits','candidate-manifest')


class StaticProjectionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class StaticProjectionV2:
    semantic_envelope: bytes
    capacity_ledger: bytes
    ownership_ledger: bytes
    density_ledger: bytes
    geometry_search: bytes
    static_limits: bytes
    candidate_manifest: bytes


def _require(ok, reason):
    if not ok:
        raise StaticProjectionError(reason)


def _sum(values):
    result = 0
    for value in values:
        _require(type(value) is int and 0 <= value <= _MAX_U64-result,'integer-bound')
        result += value
    return result


def _digest(raw):
    return sha256(raw).hexdigest()


def _table(name, fields, rows):
    return {name+'_fields':fields.split(','),name+'_rows':rows}


def _serialize(value):
    # A canonical serializer bounds bytes/depth and rejects any non-u64 scalar.
    return canonical_manifest.serialize_manifest(value)


def _mapping(plan):
    row = mapping_parameters(plan.side,plan.width)
    return row,dict(id='affine-slot-then-interior-v2',interior_side=row.interior,
        population=row.population,unit_population=row.units,
        unit_multiplier=row.slot_multiplier,unit_inverse_multiplier=row.slot_inverse,
        cell_multiplier=row.cell_multiplier,offset=row.offset,cell_inverse_multiplier=row.cell_inverse)


def _semantic(compiled, inputs, envelope, plan, sources):
    sections = {row.section_id:row for row in plan.sections}
    assignments = {row.section_id:row for row in compiled.atomic_assignments}
    real = []
    for row in inputs.real_content_sections:
        actual,assignment = sections[row.section_id],assignments[row.section_id]
        real.append([row.section_id,actual.closure,actual.factor,row.payload_length,
                     len(actual.payload),actual.version,list(row.record_ids),
                     65535 if assignment.game_ordinal is None else assignment.game_ordinal,
                     65535 if assignment.fixture_ordinal is None else assignment.fixture_ordinal])
    tiers = [[row.section_id,5,row.logical_payload_length,list(row.body_section_ids),
              row.assembled_stream_length,row.assembled_record_count,row.root_record_frame_length]
             for row in inputs.tier_frames]
    buckets,capacity_sections,slots,owner_ids = [],[],[],{}
    next_id = 211
    for bucket in envelope.buckets:
        buckets.append([bucket.bucket_id,bucket.tier,bucket.protection_class,bucket.payload_length,
                        len(bucket.slots),len(bucket.sections)])
        for row in bucket.sections:
            if row.payload_length:
                capacity_sections.append([next_id,bucket.bucket_id,row.section_ordinal,row.tier,
                    row.protection_class,row.first_slot_ordinal,row.slot_count,row.payload_length])
                owner_ids[next_id] = f'capacity:{bucket.bucket_id}:{row.section_ordinal}'
                next_id += 1
        slots.extend([s.bucket_id,s.slot_ordinal,s.role_ordinal,s.role_id,s.kind,s.prototype_id,s.frame_length]
                     for s in bucket.slots)
    decoded = _sum(row[3] for row in real)
    stored = _sum(row[4] for row in real)
    tier_bytes = _sum(row[2] for row in tiers)
    before = _sum((decoded,tier_bytes,16384,envelope.authoring_payload_bytes))
    reserve = max(382,(before+18)//19)
    _require(reserve == plan.reserve_bytes,'logical-reserve')
    totals = dict(prototype_count=len(inputs.prototypes),real_section_count=len(real),
        tier_frame_count=len(tiers),bucket_count=len(buckets),capacity_section_count=len(capacity_sections),
        slot_count=len(slots),authoring_payload_bytes=envelope.authoring_payload_bytes,
        real_decoded_body_payload_bytes=decoded,real_stored_body_payload_bytes=stored,
        tier_payload_bytes=tier_bytes,content_capacity_before_reserve_bytes=before,
        reserve_payload_bytes=reserve,protected_logical_capacity_bytes=_sum((before,reserve)))
    value = dict(schema='golden-board.m2-semantic-envelope/v2',profile_id=PROFILE_ID,
        source_identities=sources,
        **_table('prototype','kind,prototype_id,source_record_id,frame_bytes',
                 [[p.kind,p.prototype_id,p.source_record_id,p.frame_length] for p in inputs.prototypes]),
        **_table('real_section','section_id,closure_class,physical_replica_count,decoded_payload_bytes,stored_payload_bytes,section_version,record_ids,game_ordinal,fixture_ordinal',real),
        **_table('tier_frame','section_id,physical_replica_count,payload_bytes,dependency_ids,assembled_stream_bytes,assembled_record_count,root_record_bytes',tiers),
        **_table('bucket','bucket_id,tier,protection_class,payload_bytes,slot_count,section_count',buckets),
        **_table('capacity_section','section_id,bucket_id,section_ordinal,tier,protection_class,first_slot_ordinal,slot_count,payload_bytes',capacity_sections),
        **_table('slot','bucket_id,slot_ordinal,role_ordinal,role_id,kind,prototype_id,frame_bytes',slots),
        totals=totals)
    return value,owner_ids


def _span_class(owner):
    if owner.startswith(('worked:','held-out:','vm-discriminator:','body-codec:')):
        return 'example'
    if owner.startswith('recipe-package:'):
        return 'recipe'
    if owner.startswith('headroom'):
        return 'headroom'
    return 'fixed-pad' if owner == 'fixed-pad' else 'instruction'


def _shell(routes, plan):
    classes = dict.fromkeys(('instruction','example','recipe','headroom','fixed-pad'),0)
    rows = []
    for sector in routes.sectors:
        spans,cursor = [],0
        for span in sector.spans:
            _require(span.start_cell == cursor and span.cell_count > 0,'shell-span-coverage')
            kind = _span_class(span.owner)
            classes[kind] = _sum((classes[kind],span.cell_count))
            if spans and spans[-1][2] == kind:
                spans[-1][1] += span.cell_count
            else:
                spans.append([cursor,span.cell_count,kind])
            cursor += span.cell_count
        _require(cursor == plan.width*(plan.side-plan.width),'shell-span-total')
        pad = cursor-sector.route_prefix_cells-sector.headroom_cells
        rows.append([sector.sector_id,sector.route_prefix_cells,sector.headroom_cells,pad,
                     _digest(sector.data),spans])
    return rows,classes


def _protected(plan, inputs, mapping, capacity_owners):
    decoded_lengths = {row.section_id:row.payload_length for row in inputs.real_content_sections}
    section_rows,unit_rows,unit_bytes,unit_kinds,positions = [],[],[],[],[]
    group_counts = {1:0,2:0,5:0}
    reserve_index = load_index = 0
    for section in plan.sections:
        if section.section_id == 1:
            owner = 'inventory'
        elif section.section_type == 2:
            owner = f'tier:{section.section_id}'
        elif section.section_type == 3:
            owner = f'body:{section.section_id}'
        elif section.section_type == 4:
            owner = capacity_owners[section.section_id]
        elif section.section_type == 5:
            owner = f'reserve:{reserve_index}'
            reserve_index += 1
        else:
            owner = f'load:{load_index}'
            load_index += 1
        encoded = b.encode_section_envelope(b.SectionEnvelope(section.section_id,section.section_type,
            section.version,section.closure,1,section.dependencies,section.payload))
        blocks = b.fragment_section(encoded,8,0)
        _require(len(blocks) == section.fragments,'fragment-count')
        group_counts[section.factor] += len(blocks)
        first = len(unit_rows)+1
        for fragment,block in enumerate(blocks):
            wire = m2_codec.eh72_encode_unit(block)
            for replica in range(section.factor):
                uid = len(unit_rows)+1
                slot = mapping.slot_multiplier*(uid-1)%mapping.units
                logical = 1728*slot
                unit_rows.append([uid,section.section_id,0,fragment,replica,section.factor,
                                  len(wire),_digest(wire),slot,logical,1728])
                unit_bytes.append(wire)
                unit_kinds.append(section.section_type)
                mapped = tuple((mapping.cell_multiplier*(logical+bit)+mapping.offset)%mapping.population for bit in range(1728))
                _require(len(set(mapped)) == 1728,'unit-mapping-unique')
                positions.append([uid,_digest(b''.join(index.to_bytes(4,'big') for index in mapped))])
        section_rows.append([section.section_id,section.section_type,section.version,section.closure,
            1,1,section.factor,owner,list(section.dependencies),len(section.payload),
            decoded_lengths.get(section.section_id,len(section.payload)),_digest(section.payload),
            _digest(encoded),len(encoded),len(blocks),first,len(unit_rows)])
    _require(len(unit_rows) == plan.units,'unit-total')
    return section_rows,unit_rows,unit_bytes,unit_kinds,positions,group_counts


def _ledger(plan, section_rows, group_counts, shell_classes):
    q = plan.units
    ledger = dict(stored_payload_bytes=_sum(row[9] for row in section_rows),
        decoded_body_payload_bytes=_sum(row[10] for row in section_rows if row[1] == 3),
        replicated_payload_bytes=_sum(row[6]*row[9] for row in section_rows),
        envelope_header_bytes=_sum(row[6]*(18+4*len(row[8])) for row in section_rows),
        section_check_bytes=_sum(4*row[6] for row in section_rows),fragment_header_bytes=30*q,
        fragment_zero_pad_bytes=157*q-_sum(row[6]*row[13] for row in section_rows),
        local_check_bytes=4*q,transport_pad_bytes=q,parity_bytes=24*q,encoded_transport_bytes=216*q,
        logical_group_count=_sum(group_counts.values()),factor_1_group_count=group_counts[1],
        factor_2_group_count=group_counts[2],factor_5_group_count=group_counts[5],
        physical_unit_count=q,codeword_count=24*q,
        real_protected_cells=_sum(1728*row[6]*row[14] for row in section_rows if row[1] <= 3),
        capacity_probe_cells=_sum(1728*row[6]*row[14] for row in section_rows if row[1] == 4),
        reserve_probe_cells=_sum(1728*row[6]*row[14] for row in section_rows if row[1] == 5),
        load_probe_cells=_sum(1728*row[6]*row[14] for row in section_rows if row[1] == 6),
        shell_instruction_cells=shell_classes['instruction'],shell_example_cells=shell_classes['example'],
        shell_recipe_cells=shell_classes['recipe'],shell_headroom_cells=shell_classes['headroom'],
        shell_fixed_pad_cells=shell_classes['fixed-pad'],interior_fixed_pad_cells=plan.pad_cells,
        unused_cells=0,total_cells=plan.side**2)
    _require(_sum(ledger[k] for k in ('replicated_payload_bytes','envelope_header_bytes','section_check_bytes',
        'fragment_header_bytes','fragment_zero_pad_bytes','local_check_bytes','transport_pad_bytes','parity_bytes')) == 216*q,'byte-ledger')
    _require(_sum(ledger[k] for k in ('real_protected_cells','capacity_probe_cells','reserve_probe_cells',
        'load_probe_cells','shell_instruction_cells','shell_example_cells','shell_recipe_cells','shell_headroom_cells',
        'shell_fixed_pad_cells','interior_fixed_pad_cells')) == plan.side**2,'cell-ledger')
    _require(_sum(factor*count for factor,count in group_counts.items()) == q,'factor-ledger')
    return ledger


def _actual_matrix(image, routes, plan, mapping, unit_bytes, unit_kinds):
    raw = image.carrier
    _require(type(raw) is bytes and len(raw) == 4+plan.side**2//8
             and int.from_bytes(raw[:4],'big') == plan.side**2,'carrier-frame')
    matrix = bytearray((byte >> bit)&1 for byte in raw[4:] for bit in range(7,-1,-1))
    scopes = {name:[0,0] for name in _SCOPE_NAMES}
    table_hash,chunk = sha256(),bytearray()
    side,width,interior = plan.side,plan.width,mapping.interior
    protected_end = 1728*plan.units
    owner_counts = [0,0,0]
    for index,observed in enumerate(matrix):
        row,column = divmod(index,side)
        if width <= row < side-width and width <= column < side-width:
            physical = (row-width)*interior+column-width
            logical = mapping.cell_inverse*(physical-mapping.offset)%mapping.population
            _require((mapping.cell_multiplier*logical+mapping.offset)%mapping.population == physical,'cell-inverse')
            names = ['complete-interior']
            if logical < protected_end:
                slot,offset = divmod(logical,1728)
                uid = mapping.slot_inverse*slot%plan.units+1
                _require(mapping.slot_multiplier*(uid-1)%plan.units == slot,'slot-inverse')
                wire = unit_bytes[uid-1]
                expected = (wire[offset//8] >> (7-offset%8))&1
                kind,owner = 4,uid
                names.append('real-protected' if unit_kinds[uid-1] <= 3 else _SCOPE_NAMES[unit_kinds[uid-1]-2])
                owner_counts[1] += 1
            else:
                kind,owner,offset = 5,0,logical-protected_end
                _require(offset < plan.pad_cells,'pad-domain')
                expected = (plan.pad_bytes[offset//8] >> (7-offset%8))&1
                names.append('fixed-pad')
                owner_counts[2] += 1
        else:
            if row < width and column < side-width:
                sector,u,v = 0,row,column
            elif column >= side-width and row < side-width:
                sector,u,v = 1,side-1-column,row
            elif row >= side-width and column >= width:
                sector,u,v = 2,side-1-row,side-1-column
            else:
                _require(column < width and row >= width,'shell-inverse')
                sector,u,v = 3,column,side-1-row
            local = u*(side-width)+v
            _require(b.sector_cell(side,width,sector,local) == (row,column),'shell-roundtrip')
            image_sector = routes.sectors[sector]
            expected = (image_sector.data[local//8] >> (7-local%8))&1
            names,owner = ['shell'],sector
            if local < image_sector.route_prefix_cells:
                kind,offset = 1,local
            elif local < image_sector.route_prefix_cells+image_sector.headroom_cells:
                kind,offset = 2,local-image_sector.route_prefix_cells
            else:
                kind,offset = 3,local-image_sector.route_prefix_cells-image_sector.headroom_cells
                names.append('fixed-pad')
            owner_counts[0] += 1
        _require(observed == expected,'actual-cell-value')
        for name in names:
            scopes[name][0] += 1
            scopes[name][1] += observed
        chunk.extend(bytes((kind,))+owner.to_bytes(4,'big')+offset.to_bytes(4,'big'))
        if len(chunk) >= 9*4096:
            table_hash.update(chunk)
            chunk.clear()
    table_hash.update(chunk)
    _require(tuple(owner_counts) == image.owner_cell_counts
             == (4*width*(side-width),protected_end,plan.pad_cells),'owner-counts')
    scope_rows = [dict(scope_id=name,cell_count=count,zero_count=count-ones,one_count=ones,
                       one_density_ppm=0 if not count else 1000000*ones//count)
                  for name,(count,ones) in scopes.items()]
    return table_hash.hexdigest(),scope_rows,_regularity(matrix,side,width)


def _static_limits(sources, carrier_sha, hashes, semantic, plan, mapping, packages,
                   ledger, section_rows, prefixes, policy_raw, density_raw):
    package = packages[0].logical
    recipes = {r.recipe_id:r for r in package.recipes}
    loads = [row for row in section_rows if row[1] == 6]
    selected = dict(side=plan.side,shell_width=plan.width,cells=plan.side**2,
        carrier_bytes=plan.side**2//8,carrier_file_bytes=4+plan.side**2//8,
        interior_side=mapping.interior,population=mapping.population,physical_units=plan.units,
        protected_cells=1728*plan.units,fixed_pad_cells=plan.pad_cells,
        inventory_entries=len(plan.inventory.entries),inventory_payload_bytes=len(plan.sections[0].payload),
        inventory_dependency_count=_sum(len(s.dependencies) for s in plan.sections),
        maximum_dependency_count=max(len(s.dependencies) for s in plan.sections),
        maximum_section_payload_bytes=max(len(s.payload) for s in plan.sections),
        maximum_decoded_body_bytes=max(row[10] for row in section_rows if row[1] == 3),
        maximum_section_envelope_bytes=max(row[13] for row in section_rows),
        maximum_fragments_per_section=max(row[14] for row in section_rows),
        logical_groups=ledger['logical_group_count'],
        factor_group_counts=[ledger[f'factor_{factor}_group_count'] for factor in (1,2,5)],
        load_payload_bytes=[row[9] for row in loads],load_fragment_counts=[row[14] for row in loads],
        mandatory_physical_units=plan.units-_sum(row[6]*row[14] for row in loads),
        route_prefix_bytes=[len(raw) for raw in prefixes],route_headroom_cells=list(plan.headroom_cells))
    _require(selected['maximum_dependency_count'] <= b.DEPENDENCY_MAX
             and selected['maximum_decoded_body_bytes'] <= 16384
             and selected['carrier_bytes'] <= 524288,'selected-ceiling')
    route = dict(sha256=_digest(packages[0].encoded),encoded_bytes=len(packages[0].encoded),
        expanded_bytes=len(package.encoded),recipe_count=len(package.recipes),table_count=len(package.tables),
        table_payload_bytes=package.table_payload_bytes,node_count=package.total_node_count,
        edge_count=package.total_edge_count,maximum_declared_primitive_steps=package.maximum_primitive_steps,
        maximum_declared_scratch_bytes=package.peak_live_scratch_bytes,
        **_table('recipe','recipe_id,node_count,edge_count,primitive_steps,scratch_bytes',
                 [[r.recipe_id,len(r.nodes),r.edge_count,r.primitive_steps,r.peak_live_scratch_bytes] for r in package.recipes]),
        records_per_sector=[int.from_bytes(raw[46:48],'big') for raw in prefixes],
        prefix_sha256=[_digest(raw) for raw in prefixes])
    repeated = ledger['factor_2_group_count']+ledger['factor_5_group_count']
    groups = ledger['logical_group_count']
    calls = ((30,24*plan.units),(120,groups),(123,groups),
             (202,sum(s.section_type == 3 and s.version == 1 for s in plan.sections)))
    declared = dict(scope='one-pass-complete-inventory-groups',eh_codewords_per_unit=24,
        eh_decoder_calls=calls[0][1],repetition_groups=repeated,repetition_symbol_calls=1728*repeated,
        complete_group_calls=groups,roster_calls=groups,
        body_decoder_calls=calls[3][1],primitive_steps=_sum(count*recipes[rid].primitive_steps for rid,count in calls),
        peak_recipe_scratch_bytes=max(recipes[rid].peak_live_scratch_bytes for rid,count in calls if count))
    realism = evaluate_realism(density_raw,policy_raw)
    return dict(schema='golden-board.m2-static-limits/v2',profile_id=PROFILE_ID,
        scope='static-construction-only',source_identities=sources,carrier_sha256=carrier_sha,
        projection_sha256=hashes,semantic_capacity=semantic['totals'],selected_manifestation=selected,
        route_package=route,declared_transport=declared,
        realism=dict(result=realism.result,failures=list(realism.failure_reasons)))


def build_static_projection_v2(compiled, prototype_source, blueprint, inherited_profile_policy_raw,
                               image, routes, *, policy_v2):
    """Return deterministic source-built ledgers without file writes or promotion."""
    try:
        return _build(compiled,prototype_source,blueprint,inherited_profile_policy_raw,image,routes,policy_v2)
    except StaticProjectionError:
        raise
    except (ValueError,TypeError,KeyError,IndexError,AttributeError,StopIteration,OverflowError) as error:
        raise StaticProjectionError('static-input-or-projection') from error


def _build(compiled, prototype_source, blueprint, policy_raw, image, routes, policy_v2):
    _require(type(image) is DevelopmentCarrier,'carrier-type')
    _require(type(policy_v2) is m2_policy_v2.DecoderPolicyV2 and
             (policy_v2.profile_policy_sha256,policy_v2.profile_limits_sha256,policy_v2.damage_policy_sha256) ==
             (m2_policy_v2.PROFILE_POLICY_SHA256,m2_policy_v2.PROFILE_LIMITS_SHA256,m2_policy_v2.DAMAGE_POLICY_SHA256),
             'policy-source-bindings')
    neutral = m2_policy.load_profile_policy(policy_raw)
    inputs = derive_capacity_inputs_v1(compiled,prototype_source,blueprint)
    envelope = capacity.derive_capacity_envelope(inputs,neutral.capacity_policy)
    supplied_plan = image.capacity_plan
    expected_routes = build_route_images_v2(compiled,supplied_plan.side,supplied_plan.width)
    _require(routes == expected_routes,'source-route-images')
    routes = expected_routes
    prefixes = tuple(sector.data[:sector.route_prefix_cells//8] for sector in routes.sectors)
    _require(image.route_prefixes == prefixes,'source-route-prefixes')
    plan = build_capacity_plan(compiled,prototype_source,blueprint,neutral.capacity_policy,
                               tuple(len(raw) for raw in prefixes))
    _require(supplied_plan == plan,'source-capacity-plan')
    _require(type(image.carrier) is bytes and len(image.carrier) == 4+plan.side**2//8
             and int.from_bytes(image.carrier[:4],'big') == plan.side**2,'carrier-frame')
    mapping,mapping_value = _mapping(plan)
    observed = tuple(decode_observed_route_v2(raw,plan.side,plan.width,sector)
                     for sector,raw in enumerate(prefixes))
    packages = tuple(row.package for row in observed)
    _require(all(package.encoded == packages[0].encoded for package in packages),'route-package-agreement')
    sources = dict(inherited_profile_policy_sha256=_digest(policy_raw),
        profile_policy_sha256=policy_v2.profile_policy_sha256,
        profile_limits_source_sha256=policy_v2.profile_limits_sha256,
        damage_policy_sha256=policy_v2.damage_policy_sha256,
        required_content_sha256=_digest(compiled.required_content_bytes),all_content_sha256=_digest(compiled.content_bytes))
    carrier_sha = _digest(image.carrier)
    semantic,capacity_owners = _semantic(compiled,inputs,envelope,plan,sources)
    semantic_raw = _serialize(semantic)
    shell_rows,shell_classes = _shell(routes,plan)
    section_rows,unit_rows,unit_bytes,unit_kinds,position_rows,group_counts = _protected(plan,inputs,mapping,capacity_owners)
    ledger = _ledger(plan,section_rows,group_counts,shell_classes)
    capacity_raw = _serialize(dict(schema='golden-board.m2-capacity-ledger/v2',profile_id=PROFILE_ID,
        carrier_sha256=carrier_sha,semantic_envelope_sha256=_digest(semantic_raw),
        **_table('section','section_id,section_type,section_version,closure_class,check_id,semantic_copy_count,physical_replica_count,owner_id,dependency_ids,stored_payload_bytes,decoded_payload_bytes,payload_sha256,envelope_sha256,envelope_bytes,fragment_count,first_physical_unit,last_physical_unit',section_rows),
        **_table('unit','physical_unit_id,section_id,semantic_copy_id,fragment_index,replica_index,physical_replica_count,encoded_bytes,encoded_sha256,slot,logical_bit_first,logical_bit_count',unit_rows),ledger=ledger))
    table_sha,scope_rows,regularity = _actual_matrix(image,routes,plan,mapping,unit_bytes,unit_kinds)
    ownership_raw = _serialize(dict(schema='golden-board.m2-ownership-ledger/v2',profile_id=PROFILE_ID,
        carrier_sha256=carrier_sha,capacity_ledger_sha256=_digest(capacity_raw),side=plan.side,shell_width=plan.width,
        mapping=mapping_value,
        **_table('shell','sector_id,route_prefix_cells,headroom_cells,fixed_pad_cells,image_sha256,spans',shell_rows),
        **_table('unit','physical_unit_id,mapped_cell_sha256',position_rows),
        interior_fixed_pad=dict(logical_bit_first=1728*plan.units,logical_bit_count=plan.pad_cells,
                               fill_order='affine-images-of-ascending-logical-tail'),
        cell_table=dict(row_bytes=9,row_count=plan.side**2,row_order='canonical-matrix-row-major',
            owner_kind_ids=['1-shell-route','2-shell-headroom','3-shell-fixed-pad','4-protected-unit','5-interior-fixed-pad'],
            owner_id_rule='sector-id-for-shell-kinds-physical-unit-id-for-protected-unit-zero-for-interior-fixed-pad',
            owner_bit_offset_rule='zero-based-offset-within-named-owner'),cell_table_sha256=table_sha))
    density_raw = _serialize(dict(schema='golden-board.m2-density-ledger/v0',profile_id=PROFILE_ID,
        carrier_sha256=carrier_sha,scope_rows=scope_rows,interior_regularity=regularity))
    geometry_raw = _serialize(dict(schema='golden-board.m2-geometry-search/v2',profile_id=PROFILE_ID,
        prefix_bytes=[len(raw) for raw in prefixes],headroom_cells=list(plan.headroom_cells),
        selected_side=plan.side,selected_shell_width=plan.width,row_fields=['side','shell_width','result'],
        rows=[list(row) for row in plan.search_rows]))
    outputs = [semantic_raw,capacity_raw,ownership_raw,density_raw,geometry_raw]
    hashes = {name.replace('-','_'):_digest(raw) for name,raw in zip(_OUTPUTS,outputs)}
    limits_raw = _serialize(_static_limits(sources,carrier_sha,hashes,semantic,plan,mapping,packages,
                                          ledger,section_rows,prefixes,policy_raw,density_raw))
    outputs.append(limits_raw)
    files = [(name+'.json',raw) for name,raw in zip(_OUTPUTS,outputs)]
    files += [('carrier.bin',image.carrier)]+[(f'route-{i}.bin',raw) for i,raw in enumerate(prefixes)]
    candidate = dict(schema='golden-board.m2-candidate-manifest/v2',profile_id=PROFILE_ID,
        profile_version=8,status='static-projection-only',source_identities=sources,
        files=[dict(path=path,bytes=len(raw),sha256=_digest(raw)) for path,raw in sorted(files)])
    candidate['manifest_identity'] = identity.identity_hex(b'golden-board:manifest:v0\0',(_serialize(candidate),))
    outputs.append(_serialize(candidate))
    return StaticProjectionV2(*outputs)
