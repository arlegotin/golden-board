"""Independent bounded geometry witnesses over hash-bound static evidence."""
from array import array
from dataclasses import dataclass
from hashlib import sha256
from math import gcd

from . import canonical_manifest as manifest, identity
from .m2_independence import _d2_placements, _shell_owner

PROFILE = 'eh72-hier-r5-r2-r1-lzss-crc32c-v1'
SPINE = (1,2,3,16,17,18)
PREDICATES = ('two-stage-map-bijection','matrix-owner-total-partition',
    'shell-sector-total-partition','physical-group-total-partition',
    'owner-factor-ledger-reconciliation','final-cell-lane-separation',
    'd2-d4-d6-required-closure-survival','section-dependency-inventory-closure')
SECTION = 'section_id,section_type,section_version,closure_class,check_id,semantic_copy_count,physical_replica_count,owner_id,dependency_ids,stored_payload_bytes,decoded_payload_bytes,payload_sha256,envelope_sha256,envelope_bytes,fragment_count,first_physical_unit,last_physical_unit'
UNIT = 'physical_unit_id,section_id,semantic_copy_id,fragment_index,replica_index,physical_replica_count,encoded_bytes,encoded_sha256,slot,logical_bit_first,logical_bit_count'
SHELL = 'sector_id,route_prefix_cells,headroom_cells,fixed_pad_cells,image_sha256,spans'
LEDGER = 'stored_payload_bytes,decoded_body_payload_bytes,replicated_payload_bytes,envelope_header_bytes,section_check_bytes,fragment_header_bytes,fragment_zero_pad_bytes,local_check_bytes,transport_pad_bytes,parity_bytes,encoded_transport_bytes,logical_group_count,factor_1_group_count,factor_2_group_count,factor_5_group_count,physical_unit_count,codeword_count,real_protected_cells,capacity_probe_cells,reserve_probe_cells,load_probe_cells,shell_instruction_cells,shell_example_cells,shell_recipe_cells,shell_headroom_cells,shell_fixed_pad_cells,interior_fixed_pad_cells,unused_cells,total_cells'
SOURCE = 'inherited_profile_policy_sha256,profile_policy_sha256,profile_limits_source_sha256,damage_policy_sha256,required_content_sha256,all_content_sha256'
SEMANTIC_TABLES = {
    'prototype':'kind,prototype_id,source_record_id,frame_bytes',
    'real_section':'section_id,closure_class,physical_replica_count,decoded_payload_bytes,stored_payload_bytes,section_version,record_ids,game_ordinal,fixture_ordinal',
    'tier_frame':'section_id,physical_replica_count,payload_bytes,dependency_ids,assembled_stream_bytes,assembled_record_count,root_record_bytes',
    'bucket':'bucket_id,tier,protection_class,payload_bytes,slot_count,section_count',
    'capacity_section':'section_id,bucket_id,section_ordinal,tier,protection_class,first_slot_ordinal,slot_count,payload_bytes',
    'slot':'bucket_id,slot_ordinal,role_ordinal,role_id,kind,prototype_id,frame_bytes',
}
TOTALS = 'prototype_count,real_section_count,tier_frame_count,bucket_count,capacity_section_count,slot_count,authoring_payload_bytes,real_decoded_body_payload_bytes,real_stored_body_payload_bytes,tier_payload_bytes,content_capacity_before_reserve_bytes,reserve_payload_bytes,protected_logical_capacity_bytes'


class PhysicalEvidenceError(ValueError):
    pass


def require(value, reason):
    if not value:
        raise PhysicalEvidenceError(reason)


def keys(value, names):
    require(type(value) is dict and set(value)==set(names.split(',')), 'shape')
    return value


def uint(value, high=(1<<64)-1, low=0):
    require(type(value) is int and low<=value<=high, 'integer')
    return value


def digest(value):
    require(type(value) is str and len(value)==64 and
            all(c in '0123456789abcdef' for c in value), 'digest')


def numeric_tree(value):
    if type(value) is dict:
        for item in value.values(): numeric_tree(item)
    elif type(value) is list:
        for item in value: numeric_tree(item)
    elif type(value) is not str:
        uint(value)


def document(raw, schema, names):
    try:
        value = manifest.validate_canonical_manifest(raw)
    except ValueError as error:
        raise PhysicalEvidenceError('canonical') from error
    keys(value,names)
    require(value['schema']=='golden-board.m2-'+schema+'/v2' and
            value['profile_id']==PROFILE,'schema-profile')
    numeric_tree(value)
    return value


def table(value, name, fields, maximum):
    require(value[name+'_fields']==fields.split(','),'columns')
    rows = value[name+'_rows']
    require(type(rows) is list and len(rows)<=maximum,'row-bound')
    require(all(type(row) is list and len(row)==len(fields.split(',')) for row in rows),'row-shape')
    return tuple(dict(zip(fields.split(','),row,strict=True)) for row in rows)


def source(value):
    keys(value,SOURCE)
    for item in value.values(): digest(item)


def smallest_multiplier(interior, units):
    population = interior*interior
    for multiplier in range(1,units):
        if gcd(multiplier,units)!=1: continue
        good = True
        for distance in range(1,5):
            residue = multiplier*distance%units
            for delta in (residue,residue-units):
                row,column = divmod((2*interior-1)*1728*delta%population,interior)
                for carry in ((0,) if column==0 else (0,1)):
                    r = (row+carry)%interior
                    if max(min(r,interior-r),min(column,interior-column))<max(32,interior//8):
                        good = False
        if good: return multiplier
    raise PhysicalEvidenceError('no-mapping')


@dataclass(frozen=True, slots=True)
class PhysicalInputs:
    input_sha256: dict
    capacity: dict
    ownership: dict
    semantic: dict
    side: int
    width: int
    interior: int
    population: int
    count: int
    sections: tuple
    units: tuple
    shells: tuple
    groups: tuple
    factors: dict

    def forward(self, unit, bit):
        m = self.ownership['mapping']
        slot = m['unit_multiplier']*(unit-1)%self.count
        return (m['cell_multiplier']*(1728*slot+bit)+m['offset'])%self.population

    def inverse(self, physical):
        m = self.ownership['mapping']
        logical = m['cell_inverse_multiplier']*(physical-m['offset'])%self.population
        slot,bit = divmod(logical,1728)
        return logical, (m['unit_inverse_multiplier']*slot%self.count+1,bit)

    def group_specs(self):
        actual={}
        for row in self.units:
            actual.setdefault((row['section_id'],row['fragment_index']),[]).append(row)
        return tuple((s['section_id'],fragment,self.factors[s['section_id']],
                      tuple(actual.get((s['section_id'],fragment),())))
            for s in self.sections for fragment in range(s['fragment_count']))


def admit_physical_inputs(candidate_raw, capacity_raw, ownership_raw, semantic_raw):
    candidate = document(candidate_raw,'candidate-manifest',
        'schema,profile_id,profile_version,status,source_identities,files,manifest_identity')
    require(candidate['profile_version']==8 and candidate['status']=='static-projection-only','candidate')
    source(candidate['source_identities'])
    digest(candidate['manifest_identity'])
    omitted = {k:v for k,v in candidate.items() if k!='manifest_identity'}
    require(candidate['manifest_identity']==identity.identity_hex(b'golden-board:manifest:v0\0',
        (manifest.serialize_manifest(omitted),)),'manifest-identity')
    expected_paths = sorted(['carrier.bin',*(f'route-{i}.bin' for i in range(4)),
        *(s+'.json' for s in ('capacity-ledger','ownership-ledger','semantic-envelope',
                             'density-ledger','geometry-search','static-limits'))])
    files = candidate['files']
    require(type(files) is list and len(files)==len(expected_paths),'files')
    for row,path in zip(files,expected_paths,strict=True):
        keys(row,'path,bytes,sha256'); uint(row['bytes'],1<<20,1); digest(row['sha256'])
        require(row['path']==path,'file-order')
    by_path = {row['path']:row for row in files}
    for name,raw in (('capacity-ledger',capacity_raw),('ownership-ledger',ownership_raw),
                     ('semantic-envelope',semantic_raw)):
        row = by_path[name+'.json']
        require(row['bytes']==len(raw) and row['sha256']==sha256(raw).hexdigest(),'input-binding')
    capacity = document(capacity_raw,'capacity-ledger',
        'schema,profile_id,carrier_sha256,semantic_envelope_sha256,section_fields,section_rows,unit_fields,unit_rows,ledger')
    ownership = document(ownership_raw,'ownership-ledger',
        'schema,profile_id,carrier_sha256,capacity_ledger_sha256,side,shell_width,mapping,shell_fields,shell_rows,unit_fields,unit_rows,interior_fixed_pad,cell_table,cell_table_sha256')
    semantic = document(semantic_raw,'semantic-envelope',
        'schema,profile_id,source_identities,totals,'+','.join(k+s for k in SEMANTIC_TABLES for s in ('_fields','_rows')))
    source(semantic['source_identities'])
    require(semantic['source_identities']==candidate['source_identities'],'source-binding')
    keys(semantic['totals'],TOTALS)
    require(capacity['semantic_envelope_sha256']==sha256(semantic_raw).hexdigest() and
        ownership['capacity_ledger_sha256']==sha256(capacity_raw).hexdigest(),'cross-binding')
    require(capacity['carrier_sha256']==ownership['carrier_sha256']==by_path['carrier.bin']['sha256'],'carrier-binding')
    side,width = ownership['side'],ownership['shell_width']
    uint(side,2048,64); uint(width,128,8)
    require(side%8==width%8==0 and 2*width+8<=side,'geometry')
    interior = side-2*width; population=interior*interior; count=population//1728
    require(2<=count<=2389 and by_path['carrier.bin']['bytes']==4+side*side//8,'carrier-size')
    m = keys(ownership['mapping'],'id,interior_side,population,unit_population,unit_multiplier,unit_inverse_multiplier,cell_multiplier,offset,cell_inverse_multiplier')
    require(m['id']=='affine-slot-then-interior-v2' and (m['interior_side'],m['population'],m['unit_population'])==(interior,population,count),'mapping-domain')
    for name in ('unit_multiplier','unit_inverse_multiplier'): uint(m[name],count-1,1)
    for name in ('cell_multiplier','cell_inverse_multiplier'): uint(m[name],population-1,1)
    uint(m['offset'],population-1)
    require(gcd(m['cell_multiplier'],population)==gcd(m['unit_multiplier'],count)==1,'mapping-permutation')
    sections = table(capacity,'section',SECTION,4096)
    units = table(capacity,'unit',UNIT,2389)
    shells = table(ownership,'shell',SHELL,4)
    owners = table(ownership,'unit','physical_unit_id,mapped_cell_sha256',2389)
    require(len(shells)==4 and len(units)==len(owners)==count and len(sections)>=6,'row-domain')
    for expected,row in enumerate(shells):
        require(row['sector_id']==expected,'sector-order')
        for k in ('route_prefix_cells','headroom_cells','fixed_pad_cells'):uint(row[k],side*side)
        digest(row['image_sha256'])
        require(row['route_prefix_cells']==8*by_path[f'route-{expected}.bin']['bytes']
                and row['route_prefix_cells']>=512,'route-prefix-binding')
        spans=row['spans']; require(type(spans) is list and len(spans)<=512,'spans')
        cursor=0
        for span in spans:
            require(type(span) is list and len(span)==3 and span[0]==cursor and
                span[2] in ('instruction','example','recipe','headroom','fixed-pad'),'span')
            cursor+=uint(span[1],side*side,1)
        require(cursor==width*(side-width),'span-total')
    previous=0; section_ids=set()
    for row in sections:
        sid=uint(row['section_id'],(1<<32)-1,previous+1); previous=sid; section_ids.add(sid)
        uint(row['section_type'],6,1); uint(row['section_version'],65535)
        require(row['closure_class'] in (128,129) and row['check_id']==1 and row['semantic_copy_count']==1 and row['physical_replica_count'] in (1,2,5),'section-domain')
        require(type(row['owner_id']) is str and row['owner_id'].isascii() and len(row['owner_id'])<=256,'owner')
        deps=row['dependency_ids']; require(type(deps) is list and len(deps)<=4095,'dependencies')
        require(all(type(d) is int and 0<d<(1<<32) for d in deps) and deps==sorted(set(deps)),'dependency-order')
        for k in ('stored_payload_bytes','decoded_payload_bytes'):uint(row[k],16384)
        uint(row['envelope_bytes'],32790,22);uint(row['fragment_count'],count,1)
        uint(row['first_physical_unit'],count,1);uint(row['last_physical_unit'],count,1)
        digest(row['payload_sha256']);digest(row['envelope_sha256'])
    require(tuple(r['section_id'] for r in sections if r['closure_class']==128)==SPINE,'required-spine')
    groups={}
    for number,(row,owner) in enumerate(zip(units,owners,strict=True),1):
        require(row['physical_unit_id']==owner['physical_unit_id']==number and row['section_id'] in section_ids,'unit-order')
        require(row['semantic_copy_id']==0 and row['physical_replica_count'] in (1,2,5) and row['encoded_bytes']==216,'unit-domain')
        uint(row['fragment_index'],count-1);uint(row['replica_index'],4)
        uint(row['slot'],count-1);uint(row['logical_bit_first'],population-1);uint(row['logical_bit_count'],population,1)
        digest(row['encoded_sha256']);digest(owner['mapped_cell_sha256'])
        groups.setdefault((row['section_id'],row['fragment_index']),[]).append(row)
    keys(capacity['ledger'],LEDGER)
    pad=keys(ownership['interior_fixed_pad'],'logical_bit_first,logical_bit_count,fill_order')
    require(pad['fill_order']=='affine-images-of-ascending-logical-tail','pad-order')
    cell=keys(ownership['cell_table'],'owner_bit_offset_rule,owner_id_rule,owner_kind_ids,row_bytes,row_count,row_order')
    require(cell['row_bytes']==9 and cell['row_order']=='canonical-matrix-row-major' and
        cell['owner_kind_ids']==['1-shell-route','2-shell-headroom','3-shell-fixed-pad','4-protected-unit','5-interior-fixed-pad'] and
        cell['owner_id_rule']=='sector-id-for-shell-kinds-physical-unit-id-for-protected-unit-zero-for-interior-fixed-pad' and
        cell['owner_bit_offset_rule']=='zero-based-offset-within-named-owner','cell-table')
    digest(ownership['cell_table_sha256'])
    semantic_tables={name:table(semantic,name,columns,65535) for name,columns in SEMANTIC_TABLES.items()}
    string_fields={'bucket_id','protection_class','role_id','prototype_id','tier'}
    array_fields={'record_ids','dependency_ids'}
    for name,rows in semantic_tables.items():
        for row in rows:
            for field,value in row.items():
                if field in string_fields:
                    require(type(value) is str and value.isascii() and len(value)<=256,'semantic-string')
                elif field in array_fields:
                    require(type(value) is list and len(value)<=65535,'semantic-array')
                    for entry in value:uint(entry,65535,1)
                else:uint(value)
    factors={1:5,2:5,3:5}
    for row in semantic_tables['real_section']:
        sid=row['section_id'];require(sid not in factors and sid in section_ids,'real-section')
        factors[sid]=5 if row['closure_class']==128 else 1
    for row in semantic_tables['capacity_section']:
        sid=row['section_id'];require(sid not in factors and sid in section_ids,'capacity-section')
        require(row['protection_class'] in ('replicated-core0-2','nonreplicated-core3-4'),'capacity-class')
        factors[sid]=2 if row['protection_class']=='replicated-core0-2' else 1
    for row in sections:
        if row['section_type'] in (5,6): factors[row['section_id']]=2 if row['section_type']==5 else 1
    require(set(factors)==section_ids,'section-class-coverage')
    require(sum(r['fragment_count']*factors[r['section_id']] for r in sections)<=2389,
            'aggregate-group-bound')
    return PhysicalInputs(dict(candidate_manifest=sha256(candidate_raw).hexdigest(),
        capacity_ledger=sha256(capacity_raw).hexdigest(),ownership_ledger=sha256(ownership_raw).hexdigest(),
        semantic_envelope=sha256(semantic_raw).hexdigest()),capacity,ownership,semantic,
        side,width,interior,population,count,sections,units,shells,
        tuple(tuple(v) for _,v in sorted(groups.items())),factors)


def mapping_evidence(c):
    m=c.ownership['mapping']; p=c.population; q=c.count
    expected=smallest_multiplier(c.interior,q)
    owned=(m['unit_multiplier']==expected and m['unit_inverse_multiplier']==pow(expected,-1,q)
        and m['cell_multiplier']==2*c.interior-1 and m['cell_inverse_multiplier']==pow(2*c.interior-1,-1,p)
        and m['offset']==(8*40503+c.width*257)%p)
    counts=bytearray(p); targets=array('I',[0])*p; bad=bytearray(p)
    for logical in range(p):
        physical=(m['cell_multiplier']*logical+m['offset'])%p
        targets[logical]=physical;counts[physical]=min(2,counts[physical]+1)
        inverse,(unit,bit)=c.inverse(physical)
        bad[logical]=not owned or inverse!=logical or (logical<1728*q and c.forward(unit,bit)!=physical)
    return sum(bool(bad[i] or counts[target]!=1) for i,target in enumerate(targets))


def group_evidence(c):
    m=c.ownership['mapping']; by_section={r['section_id']:r for r in c.sections}
    owners=dict(c.ownership['unit_rows']); covered=bytearray(c.population)
    violations=0;malformed=[];first_id=1
    for sid,fragment,factor,group in c.group_specs():
        factor_ok=len(group)==factor and all(r['physical_replica_count']==factor and
            r['replica_index']==i and r['section_id']==sid and
            r['fragment_index']==fragment for i,r in enumerate(group))
        factor_ok=factor_ok and by_section[sid]['physical_replica_count']==factor
        ids=tuple(r['physical_unit_id'] for r in group)
        id_ok=ids==tuple(range(first_id,first_id+factor));first_id+=factor
        slot_ok=len({r['slot'] for r in group})==factor and all(
            r['slot']==m['unit_multiplier']*(r['physical_unit_id']-1)%c.count for r in group)
        span_ok=all(r['logical_bit_count']==1728 and r['logical_bit_first']==1728*r['slot'] for r in group)
        cell_ok=True;group_cells=set()
        for row in group:
            h=sha256();unit=row['physical_unit_id']
            for bit in range(1728):
                physical=c.forward(unit,bit);h.update(physical.to_bytes(4,'big'))
                if physical in group_cells:cell_ok=False
                group_cells.add(physical);covered[physical]=min(2,covered[physical]+1)
            cell_ok=cell_ok and owners[unit]==h.hexdigest()
        conditions=(factor_ok,id_ok,slot_ok,span_ok,cell_ok)
        violations+=sum(not value for value in conditions);malformed.append(not all(conditions))
    return violations,tuple(malformed),covered


def cell_evidence(c,covered):
    h=sha256();counts=dict.fromkeys(('shell-route','shell-headroom','shell-fixed-pad',
        'real-protected','capacity-probe','reserve-probe','load-probe','interior-fixed-pad'),0)
    sectors=[0]*4;bad=0
    types={r['section_id']:r['section_type'] for r in c.sections}
    for row in range(c.side):
        chunk=bytearray()
        for column in range(c.side):
            if not (c.width<=row<c.side-c.width and c.width<=column<c.side-c.width):
                sector,local=_shell_owner(c,row,column);sectors[sector]+=1;shell=c.shells[sector]
                prefix,headroom=shell['route_prefix_cells'],shell['headroom_cells']
                owner=sector
                if local<prefix:kind,offset,name=1,local,'shell-route'
                elif local<prefix+headroom:kind,offset,name=2,local-prefix,'shell-headroom'
                else:kind,offset,name=3,local-prefix-headroom,'shell-fixed-pad'
            else:
                physical=(row-c.width)*c.interior+column-c.width
                logical,(unit,bit)=c.inverse(physical)
                if logical>=1728*c.count:
                    kind,owner,offset,name=5,0,logical-1728*c.count,'interior-fixed-pad'
                    bad+=covered[physical]!=0
                else:
                    kind,owner,offset=4,unit,bit;bad+=covered[physical]!=1
                    section_type=types[c.units[unit-1]['section_id']]
                    name='real-protected' if section_type<=3 else {4:'capacity-probe',5:'reserve-probe',6:'load-probe'}[section_type]
            counts[name]+=1
            chunk.extend(bytes((kind,))+owner.to_bytes(4,'big')+offset.to_bytes(4,'big'))
        h.update(chunk)
    bad+=c.ownership['cell_table']['row_count']!=c.side*c.side or h.hexdigest()!=c.ownership['cell_table_sha256']
    sector_size=c.width*(c.side-c.width)
    shell_bad=sum(sectors[i]!=sector_size or sum(c.shells[i][k] for k in
        ('route_prefix_cells','headroom_cells','fixed_pad_cells'))!=sector_size for i in range(4))
    shell_bad+=sum(not shell_spans_valid(shell,sector_size) for shell in c.shells)
    return bad,shell_bad,counts


def shell_spans_valid(shell,sector_size):
    prefix=shell['route_prefix_cells'];headroom=prefix+shell['headroom_cells']
    prior=None
    for start,length,kind in shell['spans']:
        if kind==prior:return False
        prior=kind
        low,high=((0,prefix) if kind in ('instruction','example','recipe') else
                  (prefix,headroom) if kind=='headroom' else (headroom,sector_size))
        if not low<=start<start+length<=high:return False
    return True


def ledger_evidence(c,counts):
    ledger=c.capacity['ledger']
    expected={name:ledger[name.replace('-','_')+'_cells'] for name in counts if name!='shell-route'}
    expected['shell-route']=sum(ledger['shell_'+s+'_cells'] for s in ('instruction','example','recipe'))
    bad=sum(counts[name]!=value for name,value in expected.items())
    bad+=sum(counts.values())!=c.side*c.side
    shell_classes=dict.fromkeys(('instruction','example','recipe','headroom','fixed-pad'),0)
    for shell in c.shells:
        for _,length,kind in shell['spans']:
            shell_classes[kind]+=length
    bad+=sum(value!=ledger['shell_'+kind.replace('-','_')+'_cells']
             for kind,value in shell_classes.items())
    for factor in (1,2,5):
        groups=[g for _,_,f,g in c.group_specs() if f==factor]
        actual=(len(groups),sum(len(g) for g in groups),1728*sum(len(g) for g in groups))
        declared=ledger[f'factor_{factor}_group_count']
        bad+=actual!=(declared,declared*factor,declared*factor*1728)
    return bad


def separation_evidence(c):
    witnesses=violations=0;window=max(32,c.interior//8);first_id=1
    for _,_,factor,group in c.group_specs():
        start=first_id;first_id+=factor
        if factor not in (2,5):continue
        lanes={i:tuple(r for r in group if r['replica_index']==i) for i in range(factor)}
        for first in range(factor):
            for second in range(first+1,factor):
                if (len(lanes[first])!=1 or len(lanes[second])!=1 or
                    lanes[first][0]['physical_unit_id']!=start+first or
                    lanes[second][0]['physical_unit_id']!=start+second):
                    witnesses+=1728;violations+=1728
                    continue
                a,b=lanes[first][0]['physical_unit_id'],lanes[second][0]['physical_unit_id']
                for bit in range(1728):
                    x,y=divmod(c.forward(a,bit),c.interior);u,v=divmod(c.forward(b,bit),c.interior)
                    witnesses+=1;violations+=max(abs(x-u),abs(y-v))<window
    return witnesses,violations


def closure_evidence(c):
    grouped={};start=1
    for sid,fragment,factor,group in c.group_specs():
        available={}
        for replica in range(factor):
            matches=[r for r in group if r['replica_index']==replica]
            if len(matches)==1 and matches[0]['physical_unit_id']==start+replica:
                available[replica]=start+replica
        if sid in SPINE:grouped[(sid,fragment)]=(factor,available)
        start+=factor
    by_section={sid:[key for key in grouped if key[0]==sid] for sid in SPINE}
    violations=0;witnesses=0;square=max(32,c.interior//32)
    for top,left in _d2_placements(c,square):
        erased={}
        for row in range(top,top+square):
            for column in range(left,left+square):
                logical,(unit,bit)=c.inverse((row-c.width)*c.interior+column-c.width)
                if logical>=1728*c.count:continue
                entry=c.units[unit-1];sid=entry['section_id']
                if sid in by_section:
                    erased.setdefault((sid,entry['fragment_index'],bit),set()).add(entry['replica_index'])
        counts={}
        for key,(factor,available) in grouped.items():
            counts[key]=([[0 if lane in available else 72]*24 for lane in range(factor)],
                         [0 if available else 72]*24)
        for (sid,fragment,bit),lanes in erased.items():
            key=(sid,fragment)
            if key not in grouped:continue
            _,available=grouped[key];lane_counts,rep=counts[key]
            for lane in lanes & available.keys():lane_counts[lane][bit//72]+=1
            if available and available.keys()<=lanes:rep[bit//72]+=1
        for sid in SPINE:
            witnesses+=1;survives=True
            for key in by_section[sid]:
                lanes,rep=counts[key]
                survives=survives and (any(all(v<=3 for v in lane) for lane in lanes) or all(v<=3 for v in rep))
            violations+=not survives
    for repetition in range(5):  # D4 once; D6 once per removed shell sector.
        for omitted in range(1,c.count+1):
            for sid in SPINE:
                witnesses+=1
                violations+=not all(any(unit!=omitted for unit in grouped[key][1].values())
                                    for key in by_section[sid])
    return witnesses,violations


def inventory_evidence(c,malformed,counts):
    by_id={r['section_id']:r for r in c.sections}
    witnesses=len(malformed);violations=sum(malformed)
    bodies=table(c.semantic,'real_section',SEMANTIC_TABLES['real_section'],4096)
    for sid in (2,3):
        actual=by_id.get(sid)
        expected=[row['section_id'] for row in bodies if sid==3 or row['section_id'] in SPINE]
        for dep in expected:
            witnesses+=1
            violations+=actual is None or dep not in actual['dependency_ids'] or dep not in by_id
    for removed in range(4):
        witnesses+=1;violations+=sum(i!=removed and s['route_prefix_cells']>0 for i,s in enumerate(c.shells))!=3
    witnesses+=1
    ledger=c.capacity['ledger'];pad=c.ownership['interior_fixed_pad']
    good=(ledger['logical_group_count']==len(c.group_specs()) and ledger['physical_unit_count']==c.count
        and pad['logical_bit_first']==1728*c.count and pad['logical_bit_count']==c.population-1728*c.count
        and sum(counts.values())==ledger['total_cells']==c.side*c.side and ledger['unused_cells']==0
        and ledger['encoded_transport_bytes']==216*c.count and ledger['codeword_count']==24*c.count)
    sums=dict(stored_payload_bytes=sum(r['stored_payload_bytes'] for r in c.sections),
        decoded_body_payload_bytes=sum(r['decoded_payload_bytes'] for r in c.sections if r['section_type']==3),
        replicated_payload_bytes=sum(r['physical_replica_count']*r['stored_payload_bytes'] for r in c.sections),
        envelope_header_bytes=sum(r['physical_replica_count']*(18+4*len(r['dependency_ids'])) for r in c.sections),
        section_check_bytes=sum(4*r['physical_replica_count'] for r in c.sections),
        fragment_header_bytes=30*c.count,fragment_zero_pad_bytes=157*c.count-sum(r['physical_replica_count']*r['envelope_bytes'] for r in c.sections),
        local_check_bytes=4*c.count,transport_pad_bytes=c.count,parity_bytes=24*c.count)
    good=good and all(ledger[k]==v for k,v in sums.items())
    first=1
    for section in c.sections:
        actual=[(fragment,g) for sid,fragment,_,g in c.group_specs() if sid==section['section_id']]
        length=section['envelope_bytes'];fragments=(length+156)//157;factor=c.factors[section['section_id']]
        good=good and length==22+4*len(section['dependency_ids'])+section['stored_payload_bytes']
        good=good and section['fragment_count']==fragments and len(actual)==fragments and all(
            fragment==i and len(g)==factor for i,(fragment,g) in enumerate(actual))
        good=good and section['first_physical_unit']==first and section['last_physical_unit']==first+factor*fragments-1
        first+=factor*fragments
    good=good and first==c.count+1
    good=good and semantic_agreement(c)
    return witnesses,violations+int(not good)


def semantic_agreement(c):
    """Tie every section's role to the separately bound semantic projection."""
    by_id={r['section_id']:r for r in c.sections}
    semantic={name:table(c.semantic,name,columns,65535) for name,columns in SEMANTIC_TABLES.items()}
    buckets={r['bucket_id']:r for r in semantic['bucket']}
    if len(buckets)!=len(semantic['bucket']):return False
    good=True;expected={1:('inventory',1,2,128,5,[],None,None)}
    for row in semantic['real_section']:
        sid=row['section_id'];factor=5 if sid in SPINE else 1
        expected[sid]=(f'body:{sid}',3,row['section_version'],128 if sid in SPINE else 129,
            factor,[],row['stored_payload_bytes'],row['decoded_payload_bytes'])
        good=good and row['physical_replica_count']==factor
    if tuple(r['section_id'] for r in semantic['tier_frame'])!=(2,3):return False
    for row in semantic['tier_frame']:
        sid=row['section_id'];deps=row['dependency_ids']
        expected[sid]=(f'tier:{sid}',2,0,128,5,deps,row['payload_bytes'],row['payload_bytes'])
        intended=[r['section_id'] for r in semantic['real_section'] if sid==3 or r['section_id'] in SPINE]
        good=good and deps==intended and row['physical_replica_count']==5
    for row in semantic['capacity_section']:
        bucket=buckets.get(row['bucket_id']);sid=row['section_id']
        good=good and bucket is not None and bucket['protection_class']==row['protection_class'] and bucket['tier']==row['tier']
        expected[sid]=(f"capacity:{row['bucket_id']}:{row['section_ordinal']}",4,0,129,c.factors[sid],[],row['payload_bytes'],row['payload_bytes'])
    for kind,name,factor in ((5,'reserve',2),(6,'load',1)):
        for ordinal,section in enumerate(r for r in c.sections if r['section_type']==kind):
            expected[section['section_id']]=(f'{name}:{ordinal}',kind,0,129,factor,[],
                section['stored_payload_bytes'],section['stored_payload_bytes'])
    good=good and set(expected)==set(by_id)
    for sid,(owner,kind,version,closure,factor,deps,stored,decoded) in expected.items():
        row=by_id[sid]
        good=good and (row['owner_id'],row['section_type'],row['section_version'],row['closure_class'],row['physical_replica_count'],row['dependency_ids'])==(owner,kind,version,closure,factor,deps)
        good=good and (stored is None or row['stored_payload_bytes']==stored) and (decoded is None or row['decoded_payload_bytes']==decoded)
    good=good and sum(r['stored_payload_bytes'] for r in c.sections if r['section_type']==5)==c.semantic['totals']['reserve_payload_bytes']
    return good


def build_physical_evidence_v2(candidate_raw,capacity_raw,ownership_raw,semantic_raw):
    c=admit_physical_inputs(candidate_raw,capacity_raw,ownership_raw,semantic_raw)
    mapping=mapping_evidence(c)
    group_bad,malformed,covered=group_evidence(c)
    cell_bad,shell_bad,counts=cell_evidence(c,covered)
    separation=separation_evidence(c);closure=closure_evidence(c)
    inventory=inventory_evidence(c,malformed,counts)
    rows=[]
    for name,(witnesses,bad) in zip(PREDICATES,((c.population,mapping),
        (c.side*c.side,cell_bad),(c.side*c.side-c.population,shell_bad),
        (1728*c.count,group_bad),(c.side*c.side,ledger_evidence(c,counts)),
        separation,closure,inventory),strict=True):
        uint(witnesses,low=1);uint(bad)
        rows.append(dict(predicate_id=name,witness_count=witnesses,minimum_surviving_count=1,
                         violation_count=bad,result='pass' if bad==0 else 'fail'))
    return manifest.serialize_manifest(dict(schema='golden-board.m2-physical-evidence/v2',
        profile_id=PROFILE,scope='physical-predicates-only',input_sha256=c.input_sha256,predicate_rows=rows))
