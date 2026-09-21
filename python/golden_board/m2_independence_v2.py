"""Nine-predicate proof with fresh physical and actual-recovery premises."""
from hashlib import sha256

from . import canonical_manifest as manifest
from .m2_complete_damage_v2 import admit_complete_damage_v2
from .m2_physical_v2 import PROFILE, admit_physical_inputs, build_physical_evidence_v2
from .m2_recovery_provenance_v2 import build_recovery_provenance_v2
from .m2_resources_v2 import checked


def require(ok,reason):
    if not ok:raise ValueError('independence-v2:'+reason)


def damage_binding_predicate(damage,units):
    """The complete damage tree has already been admitted by the constructor."""
    require(type(units) is int and 2<=units<=2389,'unit-domain')
    counts=(16,4,256,128,units,21,4*units,415)
    require(type(damage) is dict and damage.get('physical_units')==units
        and type(damage.get('accidental_case_count')) is int
        and damage['accidental_case_count']==sum(counts),'damage-count')
    rows=damage.get('family_rows')
    require(type(rows) is list and len(rows)==8,'family-coverage')
    violations=0
    for i,(row,count) in enumerate(zip(rows,counts,strict=True)):
        require(type(row) is dict and row.get('family_id')==f'D{i}'
            and type(row.get('case_count')) is int and row['case_count']==count
            and row.get('result') in ('pass','fail'),'family-binding')
        wrong=checked(row.get('wrong_accept_count'))
        require(wrong==0 or row['result']=='fail','wrong-accept-pass')
        if row['result']!='pass':violations+=count
    return dict(predicate_id='damage-promise-binding',witness_count=sum(counts),
        minimum_surviving_count=1,violation_count=violations,result='pass' if violations==0 else 'fail')


def build_independence_proof_v2(candidate_raw,capacity_raw,ownership_raw,semantic_raw,
        carrier_raw,profile_policy_raw,profile_limits_raw,damage_policy_raw,corpus,read,names):
    """Fresh proof construction; caller separately owns damage execution/gate order."""
    inputs=admit_physical_inputs(candidate_raw,capacity_raw,ownership_raw,semantic_raw)
    damage_raw,_=admit_complete_damage_v2(candidate_raw,capacity_raw,ownership_raw,
                                         semantic_raw,corpus,read,names)
    physical_raw=build_physical_evidence_v2(candidate_raw,capacity_raw,ownership_raw,semantic_raw)
    recovered=build_recovery_provenance_v2(carrier_raw,candidate_raw,capacity_raw,ownership_raw,
        semantic_raw,profile_policy_raw,profile_limits_raw,damage_policy_raw)
    physical=manifest.validate_canonical_manifest(physical_raw)
    rows=physical['predicate_rows']+[damage_binding_predicate(
        manifest.validate_canonical_manifest(damage_raw),inputs.count)]
    identities={name:dict(bytes=len(raw),sha256=sha256(raw).hexdigest()) for name,raw in (
        ('physical_evidence',physical_raw),('recovery_provenance',recovered.value),
        ('knowledge_use',recovered.knowledge_use),('first_use',recovered.first_use),
        ('damage_manifest',damage_raw))}
    return manifest.serialize_manifest(dict(schema='golden-board.m2-independence-proof/v2',
        profile_id=PROFILE,input_sha256=physical['input_sha256'],**identities,predicate_rows=rows,
        result='pass' if all(row['result']=='pass' for row in rows) else 'fail'))


def validate_independence_proof_v2(raw,*inputs):
    require(type(raw) is bytes and 0<len(raw)<=1048576,'proof-bound')
    manifest.validate_canonical_manifest(raw)
    expected=build_independence_proof_v2(*inputs)
    require(raw==expected,'proof-recomputation')
    return expected
