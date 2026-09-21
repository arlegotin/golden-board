"""Fresh complete replay after independently compared native preflight cores.

Callbacks address private staging. This module emits no Gate8 receipt, source
freeze or publication claim; the coordinator owns those boundaries.
"""
from dataclasses import dataclass
from hashlib import sha256

from . import canonical_manifest as manifest
from .m2_complete_damage_v2 import build_complete_damage_v2
from .m2_independence_v2 import build_independence_proof_v2
from .m2_preflight_v2 import BOUND_PATHS, PreflightV2
from .m2_receiver_bounds_v2 import derive_receiver_bounds_v2, validate_measured_bounds_v2


def require(ok,reason):
    if not ok:raise ValueError('complete-candidate-v2:'+reason)


@dataclass(frozen=True,slots=True)
class CandidateFileV2:
    path: str
    bytes: int
    sha256: str


@dataclass(frozen=True,slots=True)
class CompleteCandidateV2:
    files: tuple
    damage_manifest: bytes
    resource_limits: bytes
    measured_resources_within_bounds: bool
    gate6_passed: bool
    independence_proof: bytes | None

    @property
    def passed(self):
        return self.gate6_passed and self.independence_proof is not None and \
            manifest.validate_canonical_manifest(self.independence_proof)['result']=='pass'


def _enter(core,workers):
    require(type(core) is PreflightV2,'preflight-type')
    require(type(workers) is int and 1<=workers<=8,'workers')
    files=dict(core.files)
    for path in ('known-answer-manifest.json','grammar-state-manifest.json'):
        value=manifest.validate_canonical_manifest(files[path])
        require(value['summary']['result']=='pass','preflight')
    value=manifest.validate_canonical_manifest(files['static-limits.json'])
    require(value['realism']==dict(result='pass',failures=[]),'preflight')
    inputs=dict(core.source.inputs)
    owners=tuple(inputs[path] for path in BOUND_PATHS)
    require(files['receiver-bounds.json']==derive_receiver_bounds_v2(*owners),'source-bounds')
    validate_measured_bounds_v2(files['preflight-resource-limits.json'],*owners)


def _rows(core,workers):
    # Python-only source oracle and actual receiver; no foreign executable.
    from tools.m2.replay_damage_v2 import case_keys, parallel_rows
    corpus=core.source.corpus
    keys=case_keys(corpus.family_counts,corpus.boundary_count,'all')
    return parallel_rows(keys,dict(core.source.inputs),None,workers)


def _proof_binding(proof,core,damage):
    value=manifest.validate_canonical_manifest(proof)
    for name,raw in (('recovery_provenance',core.recovered.value),
                     ('knowledge_use',core.recovered.knowledge_use),
                     ('first_use',core.recovered.first_use),('damage_manifest',damage)):
        require(value[name]==dict(bytes=len(raw),sha256=sha256(raw).hexdigest()),'proof-binding')
    require(value['result'] in ('pass','fail'),'proof-result')


def build_complete_candidate_v2(core,workers,emit,read):
    """Build from a fresh own-language core, never from deserialized evidence."""
    _enter(core,workers)
    files={};total=0
    def save(path,raw):
        nonlocal total
        require(type(path) is str and path not in files and type(raw) is bytes
            and 0<len(raw)<=1048576 and len(files)<4119,'output-bound')
        require(total+len(raw)<=570425344,'output-total')
        emit(path,raw)
        total+=len(raw)
        files[path]=CandidateFileV2(path,len(raw),sha256(raw).hexdigest())
    for path,raw in core.files:save(path,raw)
    damage_names=[]
    def damage_emit(path,raw):
        save(path,raw);damage_names.append(path)
    source=core.source;static=source.static
    records=_rows(core,workers)
    try:
        root,limits=build_complete_damage_v2(static.candidate_manifest,static.capacity_ledger,
            static.ownership_ledger,static.semantic_envelope,source.corpus,records,
            core.kat_receipts,damage_emit)
    finally:
        # Closing a partially consumed generator terminates and joins its pool.
        close=getattr(records,'close',None)
        if close is not None:close()
    inputs=dict(source.inputs)
    owners=tuple(inputs[path] for path in BOUND_PATHS)
    within_bounds=True
    try:validate_measured_bounds_v2(limits,*owners)
    except ValueError as error:
        # Only a measured excess is a converged losing result. Malformed or
        # foreign owner data remains an error and cannot be retained as a pass.
        if str(error) not in ('receiver-bounds-resource','receiver-bounds-adapter'):raise
        within_bounds=False
    value=manifest.validate_canonical_manifest(root)
    require(value['result'] in ('pass','fail'),'damage-result')
    gate6=value['result']=='pass' and within_bounds
    proof=None
    if gate6:
        proof=build_independence_proof_v2(static.candidate_manifest,static.capacity_ledger,
            static.ownership_ledger,static.semantic_envelope,source.image.carrier,
            *owners[:3],source.corpus,read,tuple(sorted(damage_names)))
        _proof_binding(proof,core,root)
        save('independence-proof.json',proof)
    return CompleteCandidateV2(tuple(files[name] for name in sorted(files)),root,limits,
                               within_bounds,gate6,proof)
