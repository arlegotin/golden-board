"""Closed producer/comparison/environment bindings, distinct from execution.

These projections never substitute for source generation, complete candidate
admission, actual process exits, or observed Docker image validation.
"""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from . import canonical_manifest as manifest
from .m2_gate8 import (_linux_acquisition_receipt_bytes,load_gate8_policy,
                       parse_linux_acquisition_receipt)
from .m2_gate8_policy_v2 import _document,validate_result_file_rows_v2
from .m2_source_v2 import admit_source_projection_v2,read_source_file_v2

ROOT=Path(__file__).resolve().parents[2]


def require(ok,reason):
    if not ok:raise ValueError('gate8-receipts-v2:'+reason)


def _hash(value):
    return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)


def _text(value):
    return type(value) is str and 1<=len(value)<=64 and all(32<=ord(c)<=126 for c in value)


def _source(raw,policy):
    rows={row['path']:row for row in admit_source_projection_v2(raw,policy)['entries']}
    row=rows.get('spec/gate8-policy-v2.toml',{})
    require(row.get('byte_length')==len(policy._raw) and row.get('sha256')==sha256(policy._raw).hexdigest(),
            'source-owner')
    return rows


def _read(path,source_read):
    return read_source_file_v2(ROOT,path)[0] if source_read is None else source_read(path)


def _acquisition(raw=None,*,source_read=None):
    owner=_read('spec/gate8-policy-v0.toml',source_read)
    if raw is None:raw=_linux_acquisition_receipt_bytes(load_gate8_policy(owner))
    return raw,parse_linux_acquisition_receipt(raw,owner)


def environment_identity_v2(kind,platform,acquisition_raw=None,*,source_read=None):
    require(kind in ('native','linux'),'environment-kind')
    if kind=='native':
        require(_text(platform),'environment-platform')
        return dict(kind=kind,platform=platform,image_id='none',acquisition_sha256='none')
    require(type(acquisition_raw) is bytes,'acquisition-required')
    raw,values=_acquisition(acquisition_raw,source_read=source_read)
    return dict(kind=kind,platform=values['platform'],image_id=values['image_id'],
                acquisition_sha256=sha256(raw).hexdigest())


def admit_producer_receipt_v2(raw,policy,source_raw,damage_paths,*,source_read=None):
    """Shape and provenance bindings; damage_paths must already be admitted."""
    owner=_document(policy);contract=owner['producer_receipt'];_source(source_raw,policy)
    require(type(raw) is bytes and 0<len(raw)<=owner['bounds']['canonical_json_bytes'],'receipt-bytes')
    value=manifest.validate_canonical_manifest(raw)
    require(set(value)==set(contract['keys']) and value['schema']==contract['schema']
        and value['profile_id']==owner['candidate_id']
        and value['producer_id'] in contract['producer_order']
        and value['source_projection_sha256']==sha256(source_raw).hexdigest(),'receipt-root')
    kind,implementation=value['producer_id'].split('-')
    executable=value['executable_identity'];environment=value['environment_identity']
    require(type(executable) is dict and set(executable)==set(contract['executable_keys'])
        and executable['implementation']==implementation and type(executable['bytes']) is int
        and 0<executable['bytes']<=owner['bounds']['executable_bytes'] and _hash(executable['sha256']),'executable')
    require(type(environment) is dict and set(environment)==set(contract['environment_keys'])
        and environment['kind']==kind and _text(environment['platform']),'environment')
    acquisition,_=_acquisition(source_read=source_read) if kind=='linux' else (None,None)
    require(environment==environment_identity_v2(kind,environment['platform'],acquisition,
        source_read=source_read),'environment-binding')
    require(type(value['file_rows']) is list,'file-rows')
    validate_result_file_rows_v2(policy,tuple(value['file_rows']),damage_paths)
    return value


def render_producer_receipt_v2(policy,source_raw,producer_id,executable_identity,
                               environment_identity,file_rows,damage_paths,*,source_read=None):
    """Called only after fresh complete candidate/bundle admission by caller."""
    owner=_document(policy)
    require(type(file_rows) is tuple,'file-rows-type')
    raw=manifest.serialize_manifest(dict(schema=owner['producer_receipt']['schema'],
        profile_id=owner['candidate_id'],producer_id=producer_id,
        source_projection_sha256=sha256(source_raw).hexdigest(),executable_identity=executable_identity,
        environment_identity=environment_identity,file_rows=list(file_rows)))
    admit_producer_receipt_v2(raw,policy,source_raw,damage_paths,source_read=source_read)
    return raw


def _receipts(policy,source_raw,receipts,damage_paths,*,source_read=None):
    producers=_document(policy)['producer_receipt']['producer_order']
    require(type(receipts) is dict and set(receipts)==set(producers),'four-receipts')
    values={}
    for producer in producers:
        value=admit_producer_receipt_v2(receipts[producer],policy,source_raw,damage_paths,source_read=source_read)
        require(value['producer_id']==producer,'receipt-role')
        values[producer]=value
    return values


def render_cross_language_v2(policy,source_raw,receipts,damage_paths,*,source_read=None):
    owner=_document(policy);values=_receipts(policy,source_raw,receipts,damage_paths,source_read=source_read)
    tables=[manifest.serialize_manifest(dict(schema='golden-board.m2-producer-files/v2',
                                             rows=value['file_rows'])) for value in values.values()]
    result='pass' if len(set(tables))==1 else 'fail'
    rows=[dict(producer_id=producer,receipt_bytes=len(receipts[producer]),
        receipt_sha256=sha256(receipts[producer]).hexdigest(),file_count=len(values[producer]['file_rows']),
        file_rows_sha256=sha256(table).hexdigest(),result=result)
        for producer,table in zip(values,tables,strict=True)]
    return manifest.serialize_manifest(dict(schema=owner['cross_language']['schema'],
        profile_id=owner['candidate_id'],source_projection_sha256=sha256(source_raw).hexdigest(),
        producer_rows=rows,result=result))


def validate_cross_language_v2(raw,policy,source_raw,receipts,damage_paths,*,source_read=None):
    require(type(raw) is bytes and raw==render_cross_language_v2(policy,source_raw,receipts,damage_paths,
        source_read=source_read),
            'cross-language-recomputation')
    return manifest.validate_canonical_manifest(raw)


@dataclass(frozen=True,slots=True)
class LinuxVerificationV2:
    """Actual coordinator observations, not a deserializable success receipt."""
    host_full: str
    linux_full: str
    host_snapshot_sha256: str
    linux_snapshot_sha256: str


def _linux_value(policy,source_raw,receipts,damage_paths,acquisition_raw,*,source_read=None):
    owner=_document(policy);rows=_source(source_raw,policy)
    acquisition,environment=_acquisition(acquisition_raw,source_read=source_read)
    for path in ('spec/gate8-policy-v0.toml','spec/gate8-verifier-refresh-v0.toml','tools/linux/Dockerfile'):
        raw=_read(path,source_read)
        require(path in rows and rows[path]['byte_length']==len(raw)
            and rows[path]['sha256']==sha256(raw).hexdigest(),'linux-source-binding')
    require(rows['tools/linux/Dockerfile']['sha256']==environment['dockerfile_sha256'],'linux-dockerfile')
    cross=manifest.validate_canonical_manifest(render_cross_language_v2(policy,source_raw,receipts,damage_paths,
        source_read=source_read))
    require(cross['result']=='pass','linux-canonical-disagreement')
    maps={kind:{p:sha256(receipts[p]).hexdigest() for p in owner['producer_receipt']['producer_order']
                if p.startswith(kind+'-')} for kind in ('native','linux')}
    return dict(schema=owner['linux']['attestation_schema'],source_projection_sha256=sha256(source_raw).hexdigest(),
        image_id=environment['image_id'],platform=environment['platform'],acquisition_sha256=sha256(acquisition).hexdigest(),
        native_receipt_sha256=maps['native'],linux_receipt_sha256=maps['linux'],
        host_full='pass',linux_full='pass',execution_snapshots_equal=True,canonical_bytes_equal=True)


def render_linux_attestation_v2(policy,source_raw,receipts,damage_paths,acquisition_raw,verification,*,source_read=None):
    require(type(verification) is LinuxVerificationV2 and verification.host_full=='pass'
        and verification.linux_full=='pass' and _hash(verification.host_snapshot_sha256)
        and verification.host_snapshot_sha256==verification.linux_snapshot_sha256,'linux-execution')
    return manifest.serialize_manifest(_linux_value(policy,source_raw,receipts,damage_paths,acquisition_raw,
        source_read=source_read))


def admit_linux_attestation_v2(raw,policy,source_raw,receipts,damage_paths,acquisition_raw,*,source_read=None):
    """Check retained exact claims and bindings; caller separately proves runs."""
    require(type(raw) is bytes and raw==manifest.serialize_manifest(
        _linux_value(policy,source_raw,receipts,damage_paths,acquisition_raw,source_read=source_read)),'linux-attestation')
    return manifest.validate_canonical_manifest(raw)
