"""Compact owner-reviewed M2 human result and exact packet-file binding."""
from hashlib import sha256

from . import canonical_manifest as manifest
from .m2_gate8 import roadmap_normative_sha256
from .m2_gate8_reports_v2 import recover_pending_roadmap_v2
from .m2_source_v2 import read_source_file_v2, _path

PATH = 'studies/m2/qualification-v2.json'
SCHEMA = 'golden-board.m2-human-qualification/v2'
PACKET_SCHEMA = 'golden-board.m2-packet-files/v2'


def require(ok,reason):
    if not ok:raise ValueError('m2-qualification-v2:'+reason)


def digest(raw):return sha256(raw).hexdigest()


def _hash(value):
    return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)


def packet_files_digest_v2(files):
    require(type(files) is dict and 1<=len(files)<=64,'packet-count')
    rows=[];total=0
    for path,raw in sorted(files.items()):
        require(_path(path) == path and type(raw) is bytes and len(raw)<=4194306,'packet-file')
        total+=len(raw);require(total<=33554432,'packet-aggregate')
        rows.append(dict(path=path,bytes=len(raw),sha256=digest(raw)))
    return digest(manifest.serialize_manifest(dict(schema=PACKET_SCHEMA,files=rows)))


def qualification_shape_v2(raw):
    require(type(raw) is bytes and 0<len(raw)<=8192,'record-bound')
    value=manifest.validate_canonical_manifest(raw)
    require(type(value) is dict and set(value)=={'schema','trial_id','frozen_source_snapshot_sha256',
        'technical','learner','source_reconciliation'} and value['schema']==SCHEMA
        and value['trial_id']=='20-open-technical-group'
        and _hash(value['frozen_source_snapshot_sha256']),'record-shape')
    technical=value['technical']
    require(type(technical) is dict and set(technical)=={'unit','result','group_final_sha256',
        'review_sha256','packet_files_sha256','clean_abc','d_strict','content_query'}
        and technical['unit']=='fresh-three-person-group' and technical['result']=='pass'
        and technical['clean_abc']=='exact' and technical['d_strict']=='explicit-refusal'
        and technical['content_query']=='exact'
        and all(_hash(technical[key]) for key in ('group_final_sha256','review_sha256',
            'packet_files_sha256')),'technical')
    learner=value['learner']
    require(type(learner) is dict and set(learner)=={'unit','result','answer_sha256',
        'attempt_sha256','review_sha256','packet_files_sha256','finals_correct'}
        and learner['unit']=='fresh-individual' and learner['result']=='pass'
        and type(learner['finals_correct']) is int and learner['finals_correct']==12
        and all(_hash(learner[key]) for key in ('answer_sha256','attempt_sha256',
            'review_sha256','packet_files_sha256')),'learner')
    reconciliation=value['source_reconciliation']
    require(type(reconciliation) is dict and set(reconciliation)=={'meaning','changed_paths'}
        and reconciliation['meaning']=='nonsemantic-execution-and-qualification-only',
        'source-reconciliation')
    paths=reconciliation['changed_paths']
    require(type(paths) is list and 1<=len(paths)<=64
        and all(type(path) is str and _path(path)==path for path in paths)
        and paths==sorted(set(paths)),'source-paths')
    return value


def admit_qualification_v2(raw,policy,root):
    """Bind the owner judgment to every installed technical/learner packet file."""
    value=qualification_shape_v2(raw)
    for kind in ('technical','learner'):
        contract=policy.document[kind+'_bundle']
        paths=(*contract['participant_paths'],*contract['owner_paths'])
        files={path:read_source_file_v2(root,
            'artifacts/gate8/bundles/'+kind+'/'+path,4194306)[0] for path in paths}
        require(packet_files_digest_v2(files)==value[kind]['packet_files_sha256'],kind+'-packet')
    return value


_M2 = '| M2 — Full-carrier bootstrap and transport feasibility | '
_CURRENT_M2 = b'| Current milestone | M2 \xe2\x80\x94 Full-carrier bootstrap and transport feasibility |\n'
_CURRENT_M3 = b'| Current milestone | M3 \xe2\x80\x94 Complete content and formative integration |\n'
_PROJECT_READY = b'| Project state | Candidate ready |\n'
_PROJECT_COMPLETE = b'| Project state | In progress |\n'


def _status_terms(policy,report_raw,qualification_raw):
    owner=policy.document
    ready=(_M2+owner['lifecycle']['m2_status']+' | ').encode()
    complete=(_M2+'Complete — human feasibility qualified | ').encode()
    ready_tail=owner['lifecycle']['candidate_ready_tail'].format(
        candidate_id=owner['candidate_id'],report_sha256=digest(report_raw)).encode()
    complete_tail=(
        'The revised candidate passes gates 1–8 with provisional preferred candidate '
        f'`{owner["candidate_id"]}` and automated report `reports/m2-feasibility-v2.json` '
        f'SHA-256 `{digest(report_raw)}`; the technical group and individual learner '
        'qualify under `studies/m2/qualification-v2.json` SHA-256 '
        f'`{digest(qualification_raw)}` after fresh release. The M4 actual-content '
        'rerun remains required.').encode()
    return ready,complete,ready_tail,complete_tail


def _status_line(lines,prefix,tail,root):
    matches=[i for i,line in enumerate(lines) if line.startswith(prefix)]
    require(len(matches)==1 and sum(line.startswith(_M2.encode()) for line in lines)==1
        and root.count(tail)==1 and lines[matches[0]].endswith(tail+b' |\n'),
        'roadmap-status')
    offset=sum(map(len,lines[:matches[0]]))
    require(root.index(b'## 13. Project status')<offset<root.index(b'## 14. Adversarial stress matrix'),
        'roadmap-status-location')
    return matches[0]


def render_complete_roadmap_v2(policy,ready_raw,report_raw,qualification_raw):
    """Apply only the reviewed release-last M2 status and derived display rows."""
    recover_pending_roadmap_v2(policy,ready_raw,report_raw)
    qualification_shape_v2(qualification_raw)
    before=roadmap_normative_sha256(ready_raw)
    lines=ready_raw.splitlines(keepends=True)
    ready,complete,ready_tail,complete_tail=_status_terms(policy,report_raw,qualification_raw)
    require(lines.count(_PROJECT_READY)==1 and lines.count(_CURRENT_M2)==1
        and sum(line.startswith(b'| Current milestone | ') for line in lines)==1,
        'roadmap-ready-display')
    i=_status_line(lines,ready,ready_tail,ready_raw)
    lines[i]=lines[i].replace(ready,complete,1).replace(ready_tail,complete_tail,1)
    lines[lines.index(_PROJECT_READY)]=_PROJECT_COMPLETE
    lines[lines.index(_CURRENT_M2)]=_CURRENT_M3
    result=b''.join(lines)
    require(roadmap_normative_sha256(result)==before,'roadmap-normative-preservation')
    return result


def recover_ready_roadmap_v2(policy,complete_raw,report_raw,qualification_raw):
    """Reverse only the exact completed status and prove the forward round trip."""
    qualification_shape_v2(qualification_raw)
    require(type(complete_raw) is bytes and 0<len(complete_raw)<=8388608
        and complete_raw.endswith(b'\n') and b'\r' not in complete_raw,'roadmap-bytes')
    lines=complete_raw.splitlines(keepends=True)
    ready,complete,ready_tail,complete_tail=_status_terms(policy,report_raw,qualification_raw)
    require(lines.count(_PROJECT_COMPLETE)==1 and lines.count(_CURRENT_M3)==1
        and sum(line.startswith(b'| Project state | ') for line in lines)==1
        and sum(line.startswith(b'| Current milestone | ') for line in lines)==1,
        'roadmap-complete-display')
    i=_status_line(lines,complete,complete_tail,complete_raw)
    lines[i]=lines[i].replace(complete,ready,1).replace(complete_tail,ready_tail,1)
    lines[lines.index(_PROJECT_COMPLETE)]=_PROJECT_READY
    lines[lines.index(_CURRENT_M3)]=_CURRENT_M2
    candidate_ready=b''.join(lines)
    require(render_complete_roadmap_v2(policy,candidate_ready,report_raw,qualification_raw)
        == complete_raw,'roadmap-complete-binding')
    return candidate_ready
