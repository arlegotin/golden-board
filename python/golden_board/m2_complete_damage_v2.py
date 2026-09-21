"""Bounded retained projection of complete fresh revised damage executions.

An emit callback writes only private staging. Admission reconstructs retained
facts; it never substitutes for oracle/receiver convergence during production.
"""
from hashlib import sha256
import re

from . import canonical_manifest as manifest
from .m2_boundary_kat_v2 import KAT_IDS
from .m2_damage_replay_v2 import FAMILIES, STATES, validate_replay_row, _ids
from .m2_damage_v2 import DamageCorpusV2
from .m2_physical_v2 import PROFILE, SPINE, admit_physical_inputs
from .m2_resources_v2 import ResourceAggregateV2, _read_resource_projection, _digest, add, checked

CASE_FIELDS=set(('observation','decoder_result_sha256','artifact_state','stream_rows',
    'section_states','wrong_accept_count','promise_result','resource_projection_sha256',
    'resource','adapter_rows'))
MAX_CASE=262144
MAX_SHARD=524288


def require(ok,reason):
    if not ok:raise ValueError('complete-damage:'+reason)


def canonical(raw,maximum=1048576):
    require(type(raw) is bytes and 0<len(raw)<=maximum,'document-bound')
    return manifest.validate_canonical_manifest(raw)


def file_row(path,raw):
    return dict(path=path,bytes=len(raw),sha256=sha256(raw).hexdigest())


def compact_replay_row(raw,case,section_ids):
    value=validate_replay_row(raw,case,section_ids,SPINE)
    result=value['decoder_result'];resources=value['resource_projection']
    output=manifest.serialize_manifest(dict(observation=value['observation'],
        decoder_result_sha256=sha256(manifest.serialize_manifest(result)).hexdigest(),
        artifact_state=result['artifact_state'],stream_rows=[
            [sid,result[f'm2_{tier}_available'],result[f'm2_{tier}_stream_sha256']]
            for sid,tier in ((2,'required'),(3,'all'))],
        section_states=[[row['section_id'],row['state']] for row in value['expected_section_states']],
        wrong_accept_count=value['wrong_accept_count'],promise_result=value['promise_result'],
        resource_projection_sha256=sha256(manifest.serialize_manifest(resources)).hexdigest(),
        resource=resources['resource'],adapter_rows=resources['adapter_rows']))
    require(len(output)<=MAX_CASE,'case-bound')
    return output


def validate_compact_case(raw,case,section_ids,source_owners):
    """Return reconstructed sidecar, without claiming a complete result replay."""
    value=canonical(raw,MAX_CASE);_ids(section_ids)
    require(set(value)==CASE_FIELDS and manifest.serialize_manifest(value['observation'])==
        manifest.serialize_manifest(case.identity()),'case-shape-binding')
    require(all(_digest(value[k]) for k in ('decoder_result_sha256','resource_projection_sha256')),
            'case-hash')
    rows=value['section_states']
    require(type(rows) is list and len(rows)==len(section_ids) and all(
        type(row) is list and len(row)==2 and type(row[0]) is int and row[0]==sid
        and row[1] in STATES for row,sid in zip(rows,section_ids,strict=True)), 'section-coverage')
    require(set(SPINE)<=set(section_ids),'required-coverage')
    streams=value['stream_rows']
    require(type(streams) is list and len(streams)==2 and all(
        type(row) is list and len(row)==3 and type(row[0]) is int and row[0]==sid
        and type(row[1]) is bool and _digest(row[2]) and row[1]==(row[2]!='0'*64)
        for row,sid in zip(streams,(2,3),strict=True)),'streams')
    require(not streams[1][1] or streams[0][1],'stream-closure')
    state=value['artifact_state']
    require(state in ('exact','degraded','failure','ambiguous','resource-limit'),'artifact-state')
    require(state not in ('exact','degraded') or streams[0][1],'required-stream')
    require(state not in ('failure','ambiguous','resource-limit') or
            (not streams[0][1] and not streams[1][1]),'failed-stream')
    require(state!='exact' or (streams[1][1] and all(s in ('verified','recovered') for _,s in rows)),
            'exact-state')
    require(state!='resource-limit' or (not streams[0][1] and not streams[1][1]
        and all(s=='unknown' for _,s in rows)),'closed-resource-limit')
    wrong=checked(value['wrong_accept_count'])
    passed=case.family=='B0' or wrong==0
    states=dict(rows)
    if case.family in ('D0','D1','D5'):
        passed=passed and all(s in ('verified','recovered') for s in states.values())
    elif case.family in ('D2','D3','D4','D6'):
        passed=passed and all(states[sid] in ('verified','recovered') for sid in SPINE)
    require(value['promise_result']==('pass' if passed else 'fail'),'promise')
    sidecar=manifest.serialize_manifest(dict(schema='golden-board.m2-observation-resources/v2',
        channel=case.channel,observation_sha256=value['observation']['observation_sha256'],
        result_sha256=value['decoder_result_sha256'],source_owners=source_owners,
        resource=value['resource'],adapter_rows=value['adapter_rows']))
    _read_resource_projection(sidecar)
    require(value['resource']['section_attempts']<=4096,'attempt-ceiling')
    require(sha256(sidecar).hexdigest()==value['resource_projection_sha256'],'sidecar-binding')
    return sidecar


class FamilyWriter:
    """At most32 compact cases in memory; callers validate each one first."""
    def __init__(self,family,carrier_hash,emit):
        require(family in FAMILIES and _digest(carrier_hash),'family')
        self.family,self.carrier_hash,self.emit=family,carrier_hash,emit
        self.pending=[];self.shards=[];self.count=0;self.wrong=0;self.failed=0
        self.digest=sha256();self.closed=False

    def _raw(self,cases):
        return manifest.serialize_manifest(dict(schema='golden-board.m2-damage-shard/v2',
            profile_id=PROFILE,family_id=self.family,first_ordinal=self.count-len(self.pending),
            case_count=len(cases),cases=cases))

    def _flush(self):
        if not self.pending:return
        raw=self._raw(self.pending)
        require(len(raw)<=MAX_SHARD,'shard-bound')
        path=f'damage/{self.family}/{len(self.shards):06d}.json'
        row=dict(**file_row(path,raw),first_ordinal=self.count-len(self.pending),case_count=len(self.pending))
        self.emit(path,raw);self.shards.append(row);self.pending=[]

    def push(self,raw):
        require(not self.closed,'family-closed')
        value=canonical(raw,MAX_CASE)
        require(value['observation']['family_id']==self.family
            and type(value['observation']['case_ordinal']) is int
            and value['observation']['case_ordinal']==self.count,'family-order')
        if self.pending and (len(self.pending)==32 or len(self._raw(self.pending+[value]))>MAX_SHARD):
            self._flush()
        self.pending.append(value);self.count+=1;self.digest.update(raw)
        self.wrong=add(self.wrong,value['wrong_accept_count'])
        self.failed=add(self.failed,int(value['promise_result']=='fail'))

    def finish(self,kats_pass):
        require(not self.closed and self.count>0 and type(kats_pass) is bool,'family-finish')
        self._flush();self.closed=True
        passed=self.failed==0 and (self.family=='B0' or self.wrong==0)
        if self.family=='D7':passed=passed and kats_pass
        return manifest.serialize_manifest(dict(schema='golden-board.m2-damage-family/v2',
            profile_id=PROFILE,carrier_sha256=self.carrier_hash,family_id=self.family,
            case_count=self.count,wrong_accept_count=self.wrong,failed_promise_count=self.failed,
            result='pass' if passed else 'fail',cases_sha256=self.digest.hexdigest(),shards=self.shards))


class _Sink:
    def __init__(self,emit):self.emit=emit;self.names=set();self.total=0
    def __call__(self,path,raw):
        require(path not in self.names and len(self.names)<4096,'output-paths')
        require(type(raw) is bytes and 0<len(raw)<=1048576,'output-file-bound')
        self.total+=len(raw);require(self.total<=536870912,'output-total')
        self.emit(path,raw);self.names.add(path)


def _context(candidate_raw,capacity_raw,ownership_raw,semantic_raw,corpus):
    inputs=admit_physical_inputs(candidate_raw,capacity_raw,ownership_raw,semantic_raw)
    require(type(corpus) is DamageCorpusV2 and corpus.mapping.units==inputs.count
        and (corpus.side,corpus.width)==(inputs.side,inputs.width)
        and sha256(corpus.carrier).hexdigest()==inputs.capacity['carrier_sha256'],'corpus-static')
    sections=tuple(row['section_id'] for row in inputs.sections)
    require(tuple(corpus.sections)==sections and tuple(corpus.clean_envelopes)==sections,'corpus-catalog')
    for row in inputs.sections:
        raw=corpus.clean_envelopes[row['section_id']]
        require(len(raw)==row['envelope_bytes'] and sha256(raw).hexdigest()==row['envelope_sha256'],
                'corpus-envelope')
    counts=(16,4,256,128,inputs.count,21,4*inputs.count,415,21)
    require(corpus.family_counts==counts[:-1] and corpus.boundary_count==counts[-1],'corpus-counts')
    ids=tuple(f'{family}-{i:06d}' for family,count in zip(FAMILIES,counts,strict=True) for i in range(count))
    return inputs,sections,counts,ids


def _case(corpus,family,ordinal):
    return corpus.boundary_case(ordinal) if family=='B0' else corpus.case(family,ordinal)


def _kats(receipts):
    require(type(receipts) is tuple and len(receipts)==4,'kat-count')
    rows=[]
    for kat_id,raw in zip(KAT_IDS,receipts,strict=True):
        value=canonical(raw,4096)
        require(set(value)=={'schema','kat_id','result'} and value['schema']=='golden-board.m2-boundary-kat-result/v2'
            and value['kat_id']==kat_id and value['result'] in ('pass','fail'),'kat-shape')
        rows.append(dict(kat_id=kat_id,result=value['result'],bytes=len(raw),sha256=sha256(raw).hexdigest()))
    raw=manifest.serialize_manifest(dict(schema='golden-board.m2-boundary-kats/v2',profile_id=PROFILE,rows=rows))
    return raw,all(row['result']=='pass' for row in rows)


def _root(candidate_raw,inputs,sections,counts,families,kats,aggregate,corpus_hash,replay_hash,sink):
    limits=aggregate.finish(corpus_hash)
    sink('resource-limits.json',limits)
    raw=manifest.serialize_manifest(dict(schema='golden-board.m2-damage-manifest/v2',profile_id=PROFILE,
        candidate_manifest_sha256=sha256(candidate_raw).hexdigest(),carrier_sha256=inputs.capacity['carrier_sha256'],
        source_owners=aggregate.owners,required_section_ids=list(SPINE),section_ids=list(sections),
        physical_units=inputs.count,accidental_case_count=sum(counts[:-1]),boundary_case_count=counts[-1],
        wrong_accept_count=sum(row['wrong_accept_count'] for row in families[:-1]),
        result='pass' if all(row['result']=='pass' for row in families) else 'fail',
        corpus_sha256=corpus_hash,complete_replay_sha256=replay_hash,
        resource_limits_sha256=sha256(limits).hexdigest(),family_rows=families[:-1],
        reauthored_boundary=families[-1],boundary_kats=file_row('damage/boundary-kats.json',kats)))
    sink('damage/manifest.json',raw)
    return raw,limits


def _family_row(family,raw,sink):
    path=f'damage/{family}/manifest.json'
    value=canonical(raw);sink(path,raw)
    return dict(**{key:value[key] for key in ('family_id','case_count','wrong_accept_count','result')},
                **file_row(path,raw))


def build_complete_damage_v2(candidate_raw,capacity_raw,ownership_raw,semantic_raw,corpus,records,kat_receipts,emit):
    """Consume all converged rows in order; emit exclusively to private staging."""
    inputs,sections,counts,ids=_context(candidate_raw,capacity_raw,ownership_raw,semantic_raw,corpus)
    sink=_Sink(emit);kats,kats_pass=_kats(kat_receipts)
    aggregate=ResourceAggregateV2(ids);corpus_hash=sha256();replay_hash=sha256()
    iterator=iter(records);families=[];sentinel=object()
    for family,count in zip(FAMILIES,counts,strict=True):
        writer=FamilyWriter(family,inputs.capacity['carrier_sha256'],sink)
        for ordinal in range(count):
            raw=next(iterator,sentinel);require(raw is not sentinel,'missing-case')
            case=_case(corpus,family,ordinal)
            compact=compact_replay_row(raw,case,sections)
            value=canonical(raw)
            side=validate_compact_case(compact,case,sections,value['resource_projection']['source_owners'])
            aggregate.push(case.case_id,side);writer.push(compact)
            corpus_hash.update(manifest.serialize_manifest(case.identity()));replay_hash.update(raw)
        families.append(_family_row(family,writer.finish(kats_pass),sink))
    require(next(iterator,sentinel) is sentinel,'extra-case')
    sink('damage/boundary-kats.json',kats)
    return _root(candidate_raw,inputs,sections,counts,families,kats,aggregate,
                 corpus_hash.hexdigest(),replay_hash.hexdigest(),sink)


def admit_complete_damage_v2(candidate_raw,capacity_raw,ownership_raw,semantic_raw,corpus,read,names):
    """Recompute the closed retained tree, without asserting fresh execution."""
    require(type(names) is tuple and len(names)<=4096 and all(type(n) is str and len(n)<=128
        and n.isascii() and (n in ('resource-limits.json','damage/manifest.json','damage/boundary-kats.json')
            or re.fullmatch(r'damage/(?:D[0-7]|B0)/(?:manifest|[0-9]{6})\.json',n)) for n in names)
        and names==tuple(sorted(set(names))),'retained-paths')
    inputs,sections,counts,ids=_context(candidate_raw,capacity_raw,ownership_raw,semantic_raw,corpus)
    admitted=set(names)
    def load(path,maximum=1048576):
        require(path in admitted,'missing-path')
        raw=read(path);canonical(raw,maximum);return raw
    root=canonical(load('damage/manifest.json'))
    require(_digest(root.get('complete_replay_sha256')),'complete-replay-hash')
    owners=root.get('source_owners')
    def compare(path,raw):require(load(path)==raw,'retained-recomputation:'+path)
    sink=_Sink(compare)
    kat_raw=load('damage/boundary-kats.json',16384);kat_value=canonical(kat_raw)
    require(type(kat_value.get('rows')) is list and len(kat_value['rows'])==4,'kat-rows')
    receipts=tuple(manifest.serialize_manifest(dict(schema='golden-board.m2-boundary-kat-result/v2',
        kat_id=row.get('kat_id'),result=row.get('result'))) for row in kat_value['rows'] if type(row) is dict)
    kats,kats_pass=_kats(receipts);require(kats==kat_raw,'kat-recomputation')
    aggregate=ResourceAggregateV2(ids);corpus_hash=sha256();families=[]
    for family,count in zip(FAMILIES,counts,strict=True):
        document=canonical(load(f'damage/{family}/manifest.json'))
        shards=document.get('shards')
        require(type(shards) is list and 1<=len(shards)<=count,'shard-count')
        writer=FamilyWriter(family,inputs.capacity['carrier_sha256'],sink);ordinal=0
        for index,row in enumerate(shards):
            path=f'damage/{family}/{index:06d}.json'
            require(type(row) is dict and row.get('path')==path,'shard-path')
            shard=canonical(load(path,MAX_SHARD),MAX_SHARD)
            cases=shard.get('cases')
            require(type(cases) is list and 1<=len(cases)<=32 and ordinal+len(cases)<=count,'shard-cases')
            for value in cases:
                case=_case(corpus,family,ordinal);raw=manifest.serialize_manifest(value)
                side=validate_compact_case(raw,case,sections,owners)
                aggregate.push(case.case_id,side);writer.push(raw)
                corpus_hash.update(manifest.serialize_manifest(case.identity()));ordinal+=1
        require(ordinal==count,'family-coverage')
        families.append(_family_row(family,writer.finish(kats_pass),sink))
    sink('damage/boundary-kats.json',kats)
    result=_root(candidate_raw,inputs,sections,counts,families,kats,aggregate,
        corpus_hash.hexdigest(),root['complete_replay_sha256'],sink)
    require(sink.names==admitted,'extra-paths')
    return result
