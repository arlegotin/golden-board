"""Finite observed carried-use evidence; no authoring or recovery provenance input.

The development projection is distinct from full Gate5 and human acquisition.
Observation admission remains in the recipient modules; test mutations live
only in this evidence producer and never enter the recipient's normal path.
"""
from hashlib import sha256

from . import canonical_manifest
from .m2_decoder import DecoderError
from .m2_route_receiver_v2 import decode_observed_route_v2
from .m2_route_semantics_v2 import validate_recovered_context

_PROFILE = 'eh72-hier-r5-r2-r1-lzss-crc32c-v1'
_LIMIT = 1_048_576
_FACTS = ((1,0,()),(2,0,(1,)),(3,1,(1,)),(4,1,(2,3)),(5,2,(3,4)),
          (6,2,(5,)),(7,3,(6,)),(8,3,(6,7)),(9,4,(6,8)),
          (10,4,(7,8,9)),(11,5,(10,)),(12,5,(11,)))
_REPAIRS = (
    ('C01',(1,2,3,4,5,6),()),('C02',(5,6),()),('C03',(7,8,9),()),
    ('C04',(9,),()),('C05',(8,10,11),()),('C06',(7,10,11),()),
    ('C07',(11,12),('required','all')),
    ('C08',(7,8,10,11,12),('required','all')),
    ('C09',(12,),('required','all','section-membership')),
    ('C10',(12,),('required','all')),('C11',(7,9),()),
)


class KnowledgeUseError(ValueError):
    """Missing, malformed or failed development evidence."""


def _require(condition, reason):
    if not condition:
        raise KnowledgeUseError(reason)


def _identity(raw):
    return dict(bytes=len(raw),sha256=sha256(raw).hexdigest())


def _inputs(prefixes,side,width,required_stream,all_stream,body_payloads):
    _require(type(prefixes) is tuple and len(prefixes)==4
             and all(type(p) is bytes and 64<=len(p)<=32768 for p in prefixes),'prefixes')
    _require(type(side) is int and type(width) is int and 64<=side<=2048
             and 8<=width<=128 and side%8==width%8==0 and 2*width+8<=side,'geometry')
    for prefix in prefixes:
        _require(64+int.from_bytes(prefix[48:52],'big')==len(prefix)
                 and 8*len(prefix)<=width*(side-width),'prefix-boundary')
    _require(all(type(p) is bytes and 4<=len(p)<=_LIMIT
                 for p in (required_stream,all_stream)),'streams')
    _require(type(body_payloads) is dict and 1<=len(body_payloads)<=4096
             and all(type(sid) is int and 1<=sid<=0xffffffff
                     and type(raw) is bytes and 1<=len(raw)<=16384
                     for sid,raw in body_payloads.items())
             and {100,200}<=body_payloads.keys()
             and sum(map(len,body_payloads.values()))<=_LIMIT,'bodies')


def _topology():
    dependencies={fact:parents for fact,_,parents in _FACTS}
    pending=set(dependencies)
    ordered=[]
    while pending:
        ready=sorted(fact for fact in pending if all(p in ordered for p in dependencies[fact]))
        _require(bool(ready),'fact-cycle')
        chosen=ready[0]
        ordered.append(chosen)
        pending.remove(chosen)
    reached={12}
    for fact in reversed(ordered):
        if fact in reached:
            reached.update(dependencies[fact])
    _require(reached==set(dependencies),'unused-fact')
    return ordered


def _records(prefix):
    offset,records=64,[]
    while offset<len(prefix):
        _require(len(records)<47 and offset+8<=len(prefix),'record-count')
        stage,kind=prefix[offset:offset+2]
        rid=int.from_bytes(prefix[offset+2:offset+4],'big')
        length=int.from_bytes(prefix[offset+4:offset+8],'big')
        end=offset+8+length
        _require(end<=len(prefix),'record-boundary')
        records.append(dict(record_id=rid,stage=stage,kind=kind,byte_offset=offset,
                            payload_bytes=length,**_identity(prefix[offset:end])))
        offset=end
    _require(len(records)==47,'record-count')
    return records


def _facts_and_examples(prefix,records):
    facts,examples,seen=[],[],set()
    for record in records:
        at=record['byte_offset']+8
        payload=prefix[at:at+record['payload_bytes']]
        kind=record['kind']
        if kind==1:
            fact=int.from_bytes(payload[:2],'big')
            _require(1<=fact<=12 and fact not in seen,'fact-identity')
            _,stage,consumes=_FACTS[fact-1]
            _require(record['stage']==stage and all(p in seen for p in consumes),'fact-first-use')
            seen.add(fact)
            facts.append(dict(fact_id=fact,stage=stage,consumes=list(consumes),
                definition_record_id=record['record_id'],value_byte_offset=at+14,
                value_bytes=len(payload)-14,value_sha256=sha256(payload[14:]).hexdigest(),
                worked_record_ids=[],held_out_record_ids=[]))
        elif kind in (2,3):
            fact=int.from_bytes(payload[:2],'big')
            _require(fact in seen,'example-first-use')
            ilen=int.from_bytes(payload[4:8],'big')
            olen=int.from_bytes(payload[8:12],'big')
            status=int.from_bytes(payload[12+ilen:14+ilen],'big')
            examples.append(dict(record_id=record['record_id'],fact_id=fact,
                recipe_id=int.from_bytes(payload[2:4],'big'),
                kind='worked' if kind==2 else 'held-out',input_bytes=ilen,
                output_bytes=olen,status=status,success=True))
            target=next(row for row in facts if row['fact_id']==fact)
            target['worked_record_ids' if kind==2 else 'held_out_record_ids'].append(record['record_id'])
    _require(seen==set(range(1,13)) and len(examples)==32
             and all(row['worked_record_ids'] and row['held_out_record_ids'] for row in facts),'fact-coverage')
    return facts,examples


def _ablate(prefix,record,operator):
    start=record['byte_offset']
    end=start+record['bytes']
    if operator=='remove':
        changed=bytearray(prefix[:start]+prefix[end:])
        changed[46:48]=(46).to_bytes(2,'big')
        changed[48:52]=(len(changed)-64).to_bytes(4,'big')
        changed[56:60]=(8*len(changed)).to_bytes(4,'big')
    else:
        changed=bytearray(prefix)
        changed[end-1]^=1
    return bytes(changed)


def build_knowledge_use_v2(prefixes, *, side, width, required_stream, all_stream, body_payloads):
    """Replay all four observed routes, contexts and96 bounded rejection probes.

    Inputs must be bound to actual recovery separately by the integrating gate.
    This function deliberately has no source or carrier reconstruction fallback.
    """
    _inputs(prefixes,side,width,required_stream,all_stream,body_payloads)
    order=_topology()
    routes,ablations=[],[]
    admitted=[]
    try:
        for sector,prefix in enumerate(prefixes):
            route=decode_observed_route_v2(prefix,side,width,sector)
            _require(route.prefix_bytes==len(prefix) and route.example_count==32
                     and route.inventory_section_id==1,'observed-route')
            if admitted:
                _require(route.package.encoded==admitted[0].package.encoded
                         and route.definitions==admitted[0].definitions,'route-agreement')
            admitted.append(route)
            context=validate_recovered_context(route.commitments,required_bytes=required_stream,
                all_bytes=all_stream,body_payloads=body_payloads)
            _require(context.required_context_checked and context.all_context_checked
                     and context.section_membership_checked,'context-coverage')
            records=_records(prefix)
            facts,examples=_facts_and_examples(prefix,records)
            routes.append(dict(sector_id=sector,package_sha256=sha256(route.package.encoded).hexdigest(),
                mapping_sha256=sha256(canonical_manifest.serialize_manifest(route.mapping)).hexdigest(),
                record_rows=records,fact_rows=facts,example_rows=examples,
                context={'required':'checked','all':'checked','section-membership':'checked'}))
    except DecoderError as error:
        raise KnowledgeUseError('observed-use:'+error.reason) from error

    # Baseline use and all recovered contexts must succeed before any rejection
    # can be credited. Every probe is evaluated afresh, without a known hash KAT.
    for sector,(prefix,row) in enumerate(zip(prefixes,routes,strict=True)):
        records={record['record_id']:record for record in row['record_rows']}
        for fact in row['fact_rows']:
            record=records[fact['definition_record_id']]
            for operator in ('remove','contradict'):
                changed=_ablate(prefix,record,operator)
                classification=('record-structure' if operator=='remove' else 'definition-relationship')
                try:
                    decode_observed_route_v2(changed,side,width,sector)
                except DecoderError as error:
                    expected=(error.reason=='route-v2.length' if operator=='remove'
                              else error.reason.startswith('route-v2.semantic.'))
                    _require(expected,'ablation-unrelated-rejection')
                else:
                    raise KnowledgeUseError('ablation-accepted')
                ablations.append(dict(sector_id=sector,fact_id=fact['fact_id'],operator=operator,
                                      classification=classification,success=False,**_identity(changed)))
    value=dict(schema='golden-board.m2-knowledge-use/v2',profile_id=_PROFILE,
        scope='carried-finite-use-and-ablation-development',
        inputs=dict(side=side,shell_width=width,
            prefixes=[dict(sector_id=i,**_identity(raw)) for i,raw in enumerate(prefixes)],
            required_stream=_identity(required_stream),all_stream=_identity(all_stream),
            decoded_bodies=[dict(section_id=sid,**_identity(raw)) for sid,raw in sorted(body_payloads.items())]),
        topological_order=order,route_rows=routes,
        repair_coverage=[dict(repair_id=repair,fact_ids=list(facts),context_claims=list(claims))
                         for repair,facts,claims in _REPAIRS],
        ablation_rows=ablations,summary=dict(route_count=len(routes),
            definition_count=sum(len(r['fact_rows']) for r in routes),
            example_count=sum(len(r['example_rows']) for r in routes),
            structural_presence_rejections=sum(r['operator']=='remove' for r in ablations),
            relationship_contradiction_rejections=sum(r['operator']=='contradict' for r in ablations),
            recovered_context_count=len(routes),result='pass'))
    raw=canonical_manifest.serialize_manifest(value)
    _require(len(raw)<=_LIMIT,'evidence-bound')
    return raw


def validate_knowledge_use_v2(raw, prefixes, *, side, width, required_stream, all_stream, body_payloads):
    """Reject any evidence differing from a fresh complete replay."""
    _require(type(raw) is bytes and 1<=len(raw)<=_LIMIT,'evidence-input')
    try:
        canonical_manifest.validate_canonical_manifest(raw)
    except ValueError as error:
        raise KnowledgeUseError('evidence-canonical') from error
    expected=build_knowledge_use_v2(prefixes,side=side,width=width,required_stream=required_stream,
        all_stream=all_stream,body_payloads=body_payloads)
    _require(raw==expected,'evidence-replay')
