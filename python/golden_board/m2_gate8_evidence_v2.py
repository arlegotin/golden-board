"""Exact raw generated-file closure; component admission remains separate."""
from hashlib import sha256

from . import canonical_manifest as manifest
from .m2_gate8_policy_v2 import _document,result_file_paths_v2,validate_result_file_rows_v2
from .m2_source_v2 import admit_source_projection_v2


def require(ok,reason):
    if not ok:raise ValueError('gate8-evidence-v2:'+reason)


def gate8_paths_v2(policy,*,include_generated=True):
    owner=_document(policy)
    require(type(include_generated) is bool,'include-generated')
    paths=set(owner['lifecycle']['fixed_gate8_files'])
    for kind in ('technical','learner'):
        contract=owner[kind+'_bundle']
        paths.update(f"{owner['authority']['gate8_root']}/bundles/{kind}/{path}"
                     for path in (*contract['participant_paths'],*contract['owner_paths']))
    if not include_generated:paths.remove(owner['generated_evidence']['path'])
    require(len(paths)<=owner['bounds']['gate8_files'],'gate8-count')
    return tuple(sorted(paths))


def _row(path,raw,maximum):
    require(type(raw) is bytes and 0<len(raw)<=maximum,'file-bound')
    return dict(path=path,mode='100644',bytes=len(raw),sha256=sha256(raw).hexdigest())


def render_generated_evidence_v2(policy,source_raw,damage_paths,candidate_read,gate8_read,
                                *,candidate_names,gate8_names):
    """Rehash actual bytes after caller validates complete recursive inventory."""
    owner=_document(policy);admit_source_projection_v2(source_raw,policy)
    expected=result_file_paths_v2(policy,damage_paths)
    require(type(candidate_names) is tuple and candidate_names==expected,'candidate-inventory')
    require(type(gate8_names) is tuple and gate8_names==gate8_paths_v2(policy,include_generated=False),
            'gate8-inventory')
    rows=tuple(_row(path,candidate_read(path),owner['bounds']['canonical_json_bytes']) for path in expected)
    validate_result_file_rows_v2(policy,rows,damage_paths)
    candidate_rows=[dict(row,path=owner['authority']['candidate_root']+'/'+row['path']) for row in rows]
    gate8_rows=[];total=0
    for path in gate8_names:
        raw=gate8_read(path)
        if path==owner['source_projection']['path']:require(raw==source_raw,'source-preimage')
        maximum=owner['bounds']['bundle_file_bytes'] if '/bundles/technical/' in path or '/bundles/learner/' in path \
            else owner['bounds']['canonical_json_bytes']
        gate8_rows.append(_row(path,raw,maximum));total+=len(raw)
        require(total<=owner['bounds']['gate8_aggregate_bytes'],'gate8-total')
    result=manifest.serialize_manifest(dict(schema=owner['generated_evidence']['schema'],
        source_projection_sha256=sha256(source_raw).hexdigest(),candidate_file_rows=candidate_rows,
        gate8_file_rows=gate8_rows))
    require(len(result)<=owner['bounds']['canonical_json_bytes'],'manifest-bound')
    return result


def validate_generated_evidence_v2(raw,*args,**kwargs):
    require(type(raw) is bytes and raw==render_generated_evidence_v2(*args,**kwargs),'recomputation')
    return manifest.validate_canonical_manifest(raw)
