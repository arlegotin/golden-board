#!/usr/bin/env python3
"""Run isolated independent producers, then check their actual staged bytes."""
from hashlib import sha256
import os
from pathlib import Path
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
if __name__=='__main__':
    _import_cache=tempfile.TemporaryDirectory(prefix='golden-board-v2-imports-')
    sys.pycache_prefix=_import_cache.name;sys.dont_write_bytecode=True

from golden_board import canonical_manifest as manifest
from golden_board.m2_gate8_policy_v2 import load_gate8_policy_v2
from golden_board.m2_source_v2 import build_source_projection_v2,read_source_file_v2,validate_source_projection_v2
from golden_board.m2_gate8_receipts_v2 import admit_producer_receipt_v2
from tools.m2 import generate_gate8_v2 as producer
from tools.m2 import reopen_participant_revision as transition

ARCHIVE_SHA256='6c9c4e7a70bd8d281425885416aef77c237fdf827a547300b6dc5c7eb5928d25'


def require(ok,reason):
    if not ok:raise ValueError('gate8-coordinator-v2:'+reason)


def digest(raw):return sha256(raw).hexdigest()


def _stop(children):
    pending=dict(children);signalled=set();last_permission=None
    for child in children.values():
        if child.stdin and not child.stdin.closed:
            try:child.stdin.close()
            except OSError:pass
        child.poll()
    # Darwin returns EPERM for a process group containing only unreaped zombies.
    # Reap direct children first; allow init to reap terminated descendants too.
    # Never reinterpret a persistent permission denial as successful cleanup.
    for number,seconds in ((signal.SIGTERM,2),(signal.SIGKILL,1)):
        signalled.clear();deadline=time.monotonic()+seconds
        while pending:
            for name,child in tuple(pending.items()):
                child.poll()
                try:
                    os.killpg(child.pid,0 if name in signalled else number)
                    signalled.add(name)
                except ProcessLookupError:pending.pop(name)
                except PermissionError as error:last_permission=error
            if not pending or time.monotonic()>=deadline:break
            time.sleep(.02)
        if not pending:break
    if pending:
        if last_permission is not None:raise last_permission
        raise ValueError('gate8-coordinator-v2:process-group-cleanup')
    for child in children.values():child.wait()


def execute_pair_v2(commands,cwd,policy,source_hash,environment,check_ready,logs,
                    *,preflight_timeout=3600):
    """A zero exit, finite protocol and successful preimage callback are required.

    This only proves process completion; callers separately admit all receipts
    and actual candidate/bundle files. No supplied success flag is accepted.
    """
    require(set(commands) in ({'native-python','native-rust'},{'linux-python','linux-rust'}),'pair-roles')
    logs.mkdir(mode=0o700)
    children={};buffers={name:bytearray() for name in commands};ready={};stderr={}
    released=False;started=time.monotonic();last_notice=started
    cancelled=[]
    previous={number:signal.getsignal(number) for number in (signal.SIGTERM,signal.SIGINT)}
    # Defer cancellation until child ownership is recorded. A handler that raises
    # between Popen and dictionary insertion can leak the new process group.
    for number in previous:signal.signal(number,lambda number,_frame:cancelled.append(number))
    try:
        with selectors.DefaultSelector() as selector:
            for name,command in commands.items():
                child=subprocess.Popen(command,cwd=cwd,env=environment,stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True,bufsize=0)
                children[name]=child;stderr[name]=bytearray()
                for channel in ('stdout','stderr'):
                    stream=getattr(child,channel);os.set_blocking(stream.fileno(),False)
                    selector.register(stream,selectors.EVENT_READ,(name,channel))
            while selector.get_map() or any(child.poll() is None for child in children.values()):
                require(not cancelled,'pair-cancelled')
                for name,child in children.items():
                    code=child.poll()
                    require(code is None or code==0,'producer-exit:'+name+':'+str(code))
                require(released or time.monotonic()-started<preflight_timeout,'preflight-timeout')
                for key,_ in selector.select(.2):
                    name,channel=key.data;stream=key.fileobj
                    chunk=os.read(stream.fileno(),4096)
                    if not chunk:
                        selector.unregister(stream);stream.close()
                        if channel=='stdout':require(name in ready,'missing-readiness:'+name)
                        continue
                    if channel=='stderr':
                        stderr[name].extend(chunk);require(len(stderr[name])<=65536,'diagnostic-bound:'+name)
                        continue
                    require(name not in ready,'extra-stdout:'+name)
                    buffers[name].extend(chunk);require(len(buffers[name])<=16384,'readiness-bound:'+name)
                    if b'\n' in buffers[name]:
                        raw=bytes(buffers[name]);require(raw.count(b'\n')==1 and raw.endswith(b'\n'),'readiness-line')
                        ready[name]=producer.admit_ready_v2(raw,policy,name,source_hash)
                if len(ready)==2 and not released:
                    require(all(child.poll() is None for child in children.values()),'early-producer-exit')
                    check_ready(ready)
                    require(not cancelled,'pair-cancelled')
                    for name,child in children.items():
                        child.stdin.write(producer.render_release_v2(ready[name]));child.stdin.close()
                    released=True
                    print('M2 v2: independent preflights agree; full damage replay started.',file=sys.stderr,flush=True)
                if time.monotonic()-last_notice>=60:
                    active=','.join(name for name,child in children.items() if child.poll() is None)
                    print('M2 v2: active '+active+'; elapsed '+str(int(time.monotonic()-started))+'s.',
                          file=sys.stderr,flush=True);last_notice=time.monotonic()
            require(released and all(child.wait()==0 for child in children.values()),'pair-incomplete')
        return ready
    finally:
        try:
            _stop(children)
            for child in children.values():
                for stream in (child.stdin,child.stdout,child.stderr):
                    if stream and not stream.closed:stream.close()
            for name,raw in stderr.items():
                # Logs are diagnostic only and may be empty. They never enter evidence.
                fd=os.open(logs/(name+'.stderr'),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,'wb') as stream:stream.write(raw[:65536])
        finally:
            for number,handler in previous.items():signal.signal(number,handler)


def damage_paths_v2(raw):
    value=manifest.validate_canonical_manifest(raw)
    require(type(value) is dict and type(value.get('file_rows')) is list,'receipt-file-rows')
    rows=value['file_rows'];require(len(rows)<=4120,'receipt-file-count')
    require(all(type(row) is dict and type(row.get('path')) is str for row in rows),'receipt-file-path')
    return tuple(row['path'] for row in rows
                 if row['path']=='resource-limits.json' or row['path'].startswith('damage/'))


def read_receipts_v2(directory,kind,policy,source_raw):
    producer.absolute_path(directory);producer._directory(directory,private=True)
    names=tuple(kind+'-'+implementation for implementation in ('python','rust'))
    actual=producer.tree_rows(directory,2,1048576,2097152)
    require(tuple(row['path'] for row in actual)==tuple(name+'.json' for name in names),'receipt-directory')
    raw={name:read_source_file_v2(directory,name+'.json',1048576)[0] for name in names}
    values={}
    for name in names:
        values[name]=admit_producer_receipt_v2(raw[name],policy,source_raw,damage_paths_v2(raw[name]))
        require(values[name]['producer_id']==name,'receipt-role')
    require(values[names[0]]['file_rows']==values[names[1]]['file_rows'],'pair-file-disagreement')
    return raw,values


def admit_transition_v2(root,policy):
    """Read the exact preserved tuple and sole roadmap authority; no writes."""
    archive=root/transition.ARCHIVE
    transition._load_package(archive,ARCHIVE_SHA256)
    before=transition._read(archive/'pending/docs/roadmap.md')
    current=read_source_file_v2(root,'docs/roadmap.md')[0]
    require(not os.path.lexists(root/transition.TOMBSTONE)
        and not os.path.lexists(root/transition.REPORT),'historical-authority-present')
    report_path=root/policy.document['authority']['report_path']
    gate8=root/policy.document['authority']['gate8_root']
    if current==before:
        require(not os.path.lexists(report_path) and not os.path.lexists(gate8),'partial-pending-authority')
        return 'pending',before
    from golden_board.m2_gate8_reports_v2 import validate_candidate_ready_roadmap_v2
    report=read_source_file_v2(root,policy.document['authority']['report_path'],1048576)[0]
    validate_candidate_ready_roadmap_v2(policy,before,current,report)
    producer._directory(gate8,private=True)
    require(tuple(policy.document['authority']['gate8_root']+'/'+row['path'] for row in
        producer.tree_rows(gate8,272,4194306,83886080))==_gate8_paths(policy),'installed-gate8-inventory')
    return 'ready',before


def _gate8_paths(policy):
    from golden_board.m2_gate8_evidence_v2 import gate8_paths_v2
    return gate8_paths_v2(policy)


def linux_input_v2(native):
    policy=load_gate8_policy_v2(read_source_file_v2(ROOT,'spec/gate8-policy-v2.toml')[0])
    admit_transition_v2(ROOT,policy)
    source=build_source_projection_v2(ROOT,policy)
    read_receipts_v2(native,'native',policy,source)
    validate_source_projection_v2(source,ROOT,policy)
    print(digest(source))


def _private_executable(source,work):
    before=producer.executable_identity(source,'rust')
    producer.require(stat.S_IMODE(source.lstat().st_mode)==0o500,'rust-private-mode')
    destination=work/'gb-m2-gate8-v2'
    fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o500)
    with os.fdopen(fd,'wb') as output,source.open('rb') as incoming:
        length=0
        while chunk:=incoming.read(65536):
            length+=len(chunk);require(length<=536870912,'rust-copy-bound');output.write(chunk)
        output.flush();os.fchmod(output.fileno(),0o500);os.fsync(output.fileno())
    require(producer.executable_identity(source,'rust')==before
        and producer.executable_identity(destination,'rust')==before,'rust-copy-identity')
    producer.fsync_directory(work)
    return destination,before


def _bundle_preimages(work,policy,source_raw):
    projection=manifest.validate_canonical_manifest(read_source_file_v2(work/'candidate','bundle-preimages.json')[0])
    require(type(projection) is dict and projection.get('schema')==policy.document['bundle_preimages']['schema']
        and projection.get('source_projection_sha256')==digest(source_raw)
        and projection.get('profile_id')==policy.document['candidate_id'],'bundle-projection')
    require(set(projection)==set(policy.document['bundle_preimages']['keys'])
        and type(projection['bundle_rows']) is list and len(projection['bundle_rows'])==2,'bundle-projection-shape')
    for kind,row in zip(('technical','learner'),projection['bundle_rows'],strict=True):
        require(type(row) is dict and set(row)==set(policy.document['bundle_preimages']['row_keys'])
            and row['bundle_id']==kind+'-v2','bundle-row')
        root=work/'bundles'/(kind+'-v2')
        raw=read_source_file_v2(root,'bundle-manifest.json')[0]
        value=manifest.validate_canonical_manifest(raw)
        require(len(raw)==row['manifest_bytes'] and digest(raw)==row['manifest_sha256'],'bundle-manifest-preimage')
        require(value['participant_files']+value['owner_files']==row['file_rows'],'bundle-row-preimages')
        contract=policy.document[kind+'_bundle']
        expected_roles=tuple(zip((*contract['participant_roles'],*contract['owner_roles']),
                                (*contract['participant_paths'],*contract['owner_paths']),strict=True))
        require(tuple((item['role_id'],item['path']) for item in row['file_rows'])==expected_roles,'bundle-roles')
        expected=tuple(sorted([dict(path=item['path'],mode=item['mode'],bytes=item['bytes'],sha256=item['sha256'])
            for item in row['file_rows']]+[producer.file_row('bundle-manifest.json',raw)],key=lambda item:item['path']))
        require(producer.tree_rows(root,256,4194306,67108864)==expected,'bundle-actual-preimages')


def pair_v2(kind,workers,rust_binary,work,native=None):
    require(Path.cwd()==ROOT and kind in ('native','linux') and type(workers) is int and 1<=workers<=8,'pair-context')
    require((kind=='linux')==(native is not None),'native-input-role')
    producer.admit_work_root(work,ROOT,rust_binary)
    policy=load_gate8_policy_v2(read_source_file_v2(ROOT,'spec/gate8-policy-v2.toml')[0])
    source=build_source_projection_v2(ROOT,policy)
    native_values=read_receipts_v2(native,'native',policy,source)[1] if native is not None else None
    rust,identity=_private_executable(rust_binary,work)
    python=Path(sys.executable).resolve();python_identity=producer.executable_identity(python,'python')
    roots={kind+'-'+language:work/(kind+'-'+language) for language in ('python','rust')}
    for root in roots.values():root.mkdir(mode=0o700)
    cache=work/'pycache';cache.mkdir(mode=0o700)
    environment=dict(os.environ,PYTHONPATH=str(ROOT/'python')+os.pathsep+str(ROOT),
        PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',PYTHONPYCACHEPREFIX=str(cache))
    commands={name:([str(python),'-B',str(ROOT/'tools/m2/generate_gate8_v2.py')] if name.endswith('python')
              else [str(rust)])+['producer','--producer-id',name,'--workers',str(workers),'--work-root',str(root)]
              for name,root in roots.items()}
    def freeze():
        validate_source_projection_v2(source,ROOT,policy)
        require(producer.executable_identity(rust,'rust')==identity
            and producer.executable_identity(python,'python')==python_identity,'pair-executable-changed')
    def ready_check(values):
        freeze();tables=[]
        for name,value in values.items():
            require(read_source_file_v2(roots[name],'source.json')[0]==source,'child-source')
            require(producer.tree_rows(roots[name]/'preflight',22,1048576,33554432)
                ==tuple(value['core_rows']),'child-core-preimages')
            tables.append(value['core_rows'])
        if native_values:
            paths=set(producer.core_paths(policy))
            tables.extend([row for row in value['file_rows'] if row['path'] in paths]
                          for value in native_values.values())
        require(all(table==tables[0] for table in tables),'independent-core-disagreement')
    ready=execute_pair_v2(commands,ROOT,policy,digest(source),environment,ready_check,work/'logs')
    freeze();receipts={};tables=[]
    for name,root in roots.items():
        raw=read_source_file_v2(root,'receipt.json',1048576)[0]
        value=admit_producer_receipt_v2(raw,policy,source,damage_paths_v2(raw))
        require(value['producer_id']==name and value['executable_identity']==
            (python_identity if name.endswith('python') else identity),'child-receipt-identity')
        require(value['environment_identity']==producer.observed_environment_v2(name),'child-environment')
        actual=producer.tree_rows(root/'candidate',4120,1048576,570425344)
        require(actual==tuple(value['file_rows']),'child-candidate-preimages')
        require([row for row in value['file_rows'] if row['path'] in producer.core_paths(policy)]
            ==ready[name]['core_rows'],'released-core-changed')
        require(producer.tree_rows(root/'preflight',22,1048576,33554432)
            ==tuple(ready[name]['core_rows']),'preflight-changed')
        _bundle_preimages(root,policy,source);receipts[name]=raw;tables.append(value['file_rows'])
    if native_values:tables.extend(value['file_rows'] for value in native_values.values())
    require(all(table==tables[0] for table in tables),'complete-file-disagreement')
    freeze();producer.write_file(work,'source.json',source)
    for name,raw in receipts.items():producer.write_file(work,'receipts/'+name+'.json',raw)
    return receipts


def publish_stage_v2(repository,policy,stage,before,after,mode,freeze):
    """Publish an already semantically admitted stage; no gate is decided here."""
    cancelled=[]
    previous={number:signal.getsignal(number) for number in (signal.SIGTERM,signal.SIGINT)}
    for number in previous:signal.signal(number,lambda number,_frame:cancelled.append(number))
    def checkpoint():
        require(not cancelled,'publication-cancelled')
        freeze();require(not cancelled,'publication-cancelled')
    try:
        return _publish_stage_v2(repository,policy,stage,before,after,mode,checkpoint)
    finally:
        for number,handler in previous.items():signal.signal(number,handler)


def _publish_stage_v2(repository,policy,stage,before,after,mode,freeze):
    require(mode in ('generate','check'),'publication-mode')
    authority=policy.document['authority']
    destinations={kind:repository/authority[key] for kind,key in
        (('candidate','candidate_root'),('gate8','gate8_root'),('report','report_path'))}
    roadmap=repository/'docs/roadmap.md'
    for path in (*destinations.values(),roadmap):producer.absolute_path(path)
    expected={kind:producer.tree_rows(stage/kind,*bounds) for kind,bounds in
        (('candidate',(4120,1048576,570425344)),('gate8',(272,4194306,83886080)))}
    report=read_source_file_v2(stage,'report.json',1048576)[0]
    require(read_source_file_v2(stage,'roadmap.md')[0]==after,'staged-roadmap')
    def check_tree(kind,path):
        bounds=(4120,1048576,570425344) if kind=='candidate' else (272,4194306,83886080)
        require(producer.tree_rows(path,*bounds)==expected[kind],'publication-tree:'+kind)
    def read_roadmap():return read_source_file_v2(repository,'docs/roadmap.md')[0]
    freeze()
    if mode=='check':
        for kind in ('candidate','gate8'):check_tree(kind,destinations[kind])
        require(read_source_file_v2(repository,authority['report_path'],1048576)[0]==report
            and read_roadmap()==after,'publication-check')
        freeze();return
    require(read_roadmap()==before and not os.path.lexists(destinations['gate8'])
        and not os.path.lexists(destinations['report']),'publication-precondition')
    reused=os.path.lexists(destinations['candidate'])
    if reused:check_tree('candidate',destinations['candidate'])
    # Same-filesystem stages permit atomic renames even when computation used /tmp.
    private=Path(tempfile.mkdtemp(prefix='.gate8-v2-install-',dir=repository/'artifacts'))
    os.chmod(private,0o700);owned={};roadmap_installed=False
    def inode(path):
        info=path.lstat();return info.st_dev,info.st_ino
    try:
        for kind in ('candidate','gate8'):
            if kind=='candidate' and reused:continue
            (private/kind).mkdir(mode=0o700)
            for row in expected[kind]:
                raw=read_source_file_v2(stage/kind,row['path'],4194306)[0]
                require(len(raw)==row['bytes'] and digest(raw)==row['sha256'],'stage-changed')
                producer.write_file(private/kind,row['path'],raw)
            check_tree(kind,private/kind)
        for name,raw in (('report.json',report),('roadmap.md',after),('roadmap-before.md',before)):
            producer.write_file(private,name,raw)
        freeze()
        require(read_roadmap()==before and not os.path.lexists(destinations['gate8'])
            and not os.path.lexists(destinations['report']),'publication-stale-precondition')
        if reused:check_tree('candidate',destinations['candidate'])
        for kind in ('candidate','gate8','report'):
            if kind=='candidate' and reused:continue
            source=private/('report.json' if kind=='report' else kind);destination=destinations[kind]
            identity=inode(source)
            producer._rename_noreplace(source,destination);owned[kind]=identity
            producer.fsync_directory(destination.parent)
            freeze()
        for kind in ('candidate','gate8'):check_tree(kind,destinations[kind])
        require(read_source_file_v2(repository,authority['report_path'],1048576)[0]==report
            and read_roadmap()==before,'publication-before-status')
        freeze()
        os.replace(private/'roadmap.md',roadmap);roadmap_installed=True
        producer.fsync_directory(roadmap.parent)
        require(read_roadmap()==after,'publication-status')
        freeze()
    except BaseException:
        if roadmap_installed:
            require(read_roadmap()==after,'rollback-roadmap-changed')
            os.replace(private/'roadmap-before.md',roadmap);producer.fsync_directory(roadmap.parent)
        for kind in ('report','gate8','candidate'):
            if kind not in owned:continue
            destination=destinations[kind];require(inode(destination)==owned[kind],'rollback-ownership')
            if kind=='report':
                require(read_source_file_v2(repository,authority['report_path'],1048576)[0]==report,'rollback-report')
                destination.unlink()
            else:
                check_tree(kind,destination);shutil.rmtree(destination)
            producer.fsync_directory(destination.parent)
        raise
    finally:
        shutil.rmtree(private)


def assemble_v2(work,policy,source,receipts,linux_attestation,before,mode,workers=8):
    """Regenerate independently; retained/foreign evidence supplies comparisons only."""
    from golden_board.m2_gate8_receipts_v2 import render_cross_language_v2,admit_linux_attestation_v2
    from golden_board.m2_gate8_reports_v2 import (build_gate_rows_v2,render_selection_v2,
        render_candidate_ready_report_v2,render_candidate_ready_roadmap_v2)
    from golden_board.m2_gate8_evidence_v2 import render_generated_evidence_v2
    owner=policy.document;require(set(receipts)==set(owner['producer_receipt']['producer_order']),'assembly-receipts')
    producer.admit_work_root(work,ROOT,Path(sys.executable).resolve())
    interpreter=producer.executable_identity(Path(sys.executable).resolve(),'python')
    def freeze():
        validate_source_projection_v2(source,ROOT,policy)
        require(interpreter==producer.executable_identity(Path(sys.executable).resolve(),'python'),'assembly-executable')
    freeze();values={}
    for name,raw in receipts.items():
        values[name]=admit_producer_receipt_v2(raw,policy,source,damage_paths_v2(raw))
        require(values[name]['producer_id']==name,'assembly-receipt-role')
    tables=[value['file_rows'] for value in values.values()]
    require(all(table==tables[0] for table in tables),'assembly-producer-disagreement')
    source_read=lambda path:read_source_file_v2(ROOT,path)[0]
    preflight=producer.build_preflight_v2({path:source_read(path) for path in producer.SOURCE_PATHS})
    producer._enter(preflight,workers)
    ready=producer.admit_ready_v2(producer.render_ready_v2(policy,'native-python',digest(source),preflight.files),
        policy,'native-python',digest(source))
    core=set(producer.core_paths(policy))
    require(all([row for row in table if row['path'] in core]==ready['core_rows'] for table in tables),
        'assembly-core-disagreement')
    freeze();print('M2 v2: assembly preflight agrees; fresh full replay started.',file=sys.stderr,flush=True)
    rows,damage_paths=producer.finish_candidate_v2(preflight,workers,work,policy,source,freeze=freeze)
    require(all(tuple(table)==rows for table in tables),'assembly-file-disagreement')
    _bundle_preimages(work,policy,source);freeze()
    acquisition=source_read('artifacts/linux/verifier-v0.env')
    admit_linux_attestation_v2(linux_attestation,policy,source,receipts,damage_paths,acquisition)
    gate8=work/'gate8';gate8.mkdir(mode=0o700)
    def gate_write(path,raw):
        prefix=owner['authority']['gate8_root']+'/'
        require(path.startswith(prefix),'assembly-gate8-path');producer.write_file(gate8,path[len(prefix):],raw)
    for kind in ('technical','learner'):
        root=work/'bundles'/(kind+'-v2');contract=owner[kind+'_bundle']
        gate_write('artifacts/gate8/bundles/'+kind+'-v2.json',read_source_file_v2(root,'bundle-manifest.json')[0])
        for path in (*contract['participant_paths'],*contract['owner_paths']):
            gate_write('artifacts/gate8/bundles/'+kind+'/'+path,read_source_file_v2(root,path,4194306)[0])
    gate_write(owner['source_projection']['path'],source)
    for name,raw in receipts.items():gate_write(owner['producer_receipt']['path'].format(producer_id=name),raw)
    cross=render_cross_language_v2(policy,source,receipts,damage_paths)
    require(manifest.validate_canonical_manifest(cross)['result']=='pass','assembly-cross-language')
    gate_write(owner['cross_language']['path'],cross)
    gate_write(owner['linux']['attestation_path'],linux_attestation)
    candidate_read=lambda path:read_source_file_v2(work/'candidate',path,1048576)[0]
    gate_read=lambda path:read_source_file_v2(gate8,path[len('artifacts/gate8/'):],4194306)[0]
    def evidence_read(path):
        prefix=owner['authority']['candidate_root']+'/'
        if path.startswith(prefix):return candidate_read(path[len(prefix):])
        return gate_read(path) if path.startswith('artifacts/gate8/') else source_read(path)
    gate_rows=build_gate_rows_v2(policy,('pass',)*8,evidence_read,damage_paths)
    selection=render_selection_v2(policy,source_read('spec/profile-policy-v2.toml'),cross,gate_rows,evidence_read,damage_paths)
    gate_write(owner['selection']['path'],selection)
    candidate_names=tuple(row['path'] for row in producer.tree_rows(work/'candidate',4120,1048576,570425344))
    gate_names=lambda:tuple('artifacts/gate8/'+row['path'] for row in producer.tree_rows(gate8,272,4194306,83886080))
    generated=render_generated_evidence_v2(policy,source,damage_paths,candidate_read,gate_read,
        candidate_names=candidate_names,gate8_names=gate_names())
    gate_write(owner['generated_evidence']['path'],generated)
    report=render_candidate_ready_report_v2(policy,before,source,selection,generated,candidate_read,gate_read,
        source_read,damage_paths,acquisition,preflight=preflight,candidate_names=candidate_names,gate8_names=gate_names())
    after=render_candidate_ready_roadmap_v2(policy,before,report)
    producer.write_file(work,'report.json',report);producer.write_file(work,'roadmap.md',after)
    freeze();publish_stage_v2(ROOT,policy,work,before,after,mode,freeze)
    return report


def run_checked_v2(command,work,label,environment=None):
    """Bound diagnostic storage and own process cancellation; success is exit0."""
    cancelled=[];child=None
    previous={number:signal.getsignal(number) for number in (signal.SIGTERM,signal.SIGINT)}
    for number in previous:signal.signal(number,lambda number,_frame:cancelled.append(number))
    try:
        with (work/(label+'.log')).open('xb') as output:
            child=subprocess.Popen(command,cwd=ROOT,env=environment,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                start_new_session=True)
            last=time.monotonic();length=0
            with selectors.DefaultSelector() as selector:
                os.set_blocking(child.stdout.fileno(),False)
                selector.register(child.stdout,selectors.EVENT_READ)
                while selector.get_map() or child.poll() is None:
                    require(not cancelled,'command-cancelled:'+label)
                    code=child.poll()
                    for key,_ in selector.select(.2):
                        chunk=os.read(key.fd,65536)
                        if not chunk:selector.unregister(key.fileobj);continue
                        accepted=chunk[:max(0,16777216-length)];output.write(accepted);length+=len(accepted)
                        require(len(accepted)==len(chunk),'command-log-bound:'+label)
                    require(code is None or code==0,'command-exit:'+label+':'+str(code))
                    if time.monotonic()-last>=60:
                        print('M2 v2: '+label+' is active.',file=sys.stderr,flush=True);last=time.monotonic()
            require(not cancelled,'command-cancelled:'+label)
            output.flush()
            if child.returncode:
                with (work/(label+'.log')).open('rb') as stream:
                    stream.seek(max(0,os.fstat(stream.fileno()).st_size-8192))
                    print(stream.read(8192).decode('utf-8','replace'),file=sys.stderr)
            require(child.returncode==0,'command-exit:'+label+':'+str(child.returncode))
    finally:
        try:
            if child:
                _stop({label:child})
                if child.stdout:child.stdout.close()
        finally:
            for number,handler in previous.items():signal.signal(number,handler)


def _build_native_binary(work):
    run_checked_v2(['rustup','run','1.97.1','cargo','build','-p','gb-bootstrap','--bin','gb-m2-gate8-v2',
        '--release','--locked','--offline'],work,'rust-build')
    binary=ROOT/'target/release/gb-m2-gate8-v2'
    identity=producer.executable_identity(binary,'rust')
    destination=work/'native-rust-executable'
    fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o500)
    with os.fdopen(fd,'wb') as output,binary.open('rb') as incoming:
        length=0
        while chunk:=incoming.read(65536):
            length+=len(chunk);require(length<=536870912,'build-copy-bound');output.write(chunk)
        output.flush();os.fchmod(output.fileno(),0o500);os.fsync(output.fileno())
    require(producer.executable_identity(binary,'rust')==identity
        and producer.executable_identity(destination,'rust')==identity,'build-copy')
    producer.fsync_directory(work);return destination


def _linux_execution(work,policy,source,native):
    from golden_board.m2_gate8_receipts_v2 import LinuxVerificationV2,render_linux_attestation_v2
    from tools.linux.snapshot import build_manifest
    snapshot=digest(build_manifest(ROOT)[1])
    output=work/'linux';output.mkdir(mode=0o700)
    environment=dict(os.environ,GB_M2_GATE8_V2_OUTPUT=str(output),
        GB_M2_GATE8_V2_NATIVE_RECEIPTS=str(work/'native/receipts'))
    run_checked_v2(['tools/linux/verify.sh'],work,'linux',environment)
    require(digest(build_manifest(ROOT)[1])==snapshot,'linux-snapshot-changed')
    actual=producer.tree_rows(output,3,1048576,2101248)
    require(tuple(row['path'] for row in actual)==('linux-python.json','linux-rust.json','verification.json'),
            'linux-output-set')
    receipts={name:read_source_file_v2(output,name+'.json')[0] for name in ('linux-python','linux-rust')}
    record=manifest.validate_canonical_manifest(read_source_file_v2(output,'verification.json',4096)[0])
    acquisition=read_source_file_v2(ROOT,'artifacts/linux/verifier-v0.env',4096)[0]
    require(record==dict(schema='golden-board.m2-linux-verification/v2',source_projection_sha256=digest(source),
        acquisition_sha256=digest(acquisition),host_snapshot_sha256=snapshot,container_snapshot_sha256=snapshot,
        components='pass',pair='pass',linux_receipt_sha256={k:digest(v) for k,v in receipts.items()}),'linux-verification')
    all_receipts={**native,**receipts};paths=damage_paths_v2(native['native-python'])
    verification=LinuxVerificationV2('pass','pass',snapshot,snapshot)
    return all_receipts,render_linux_attestation_v2(policy,source,all_receipts,paths,acquisition,verification)


def workflow_v2(mode):
    require(mode in ('bootstrap','full','release') and Path.cwd()==ROOT,'workflow')
    policy=load_gate8_policy_v2(read_source_file_v2(ROOT,'spec/gate8-policy-v2.toml')[0])
    state,before=admit_transition_v2(ROOT,policy)
    require(state==('pending' if mode=='bootstrap' else 'ready'),'workflow-state')
    # Keep all failed stages/logs for bounded local diagnosis. No stage is authority.
    work=Path(tempfile.mkdtemp(prefix='golden-board-gate8-v2-'+mode+'-')).resolve();os.chmod(work,0o700)
    print('M2 v2 '+mode+' work: '+str(work),file=sys.stderr,flush=True)
    initial=build_source_projection_v2(ROOT,policy)
    retained_report=read_source_file_v2(ROOT,policy.document['authority']['report_path'])[0] if state=='ready' else None
    run_checked_v2(['scripts/check','components'],work,'components')
    validate_source_projection_v2(initial,ROOT,policy)
    binary=_build_native_binary(work)
    validate_source_projection_v2(initial,ROOT,policy)
    native_work=work/'native';native_work.mkdir(mode=0o700)
    native=pair_v2('native',8,binary,native_work)
    source=read_source_file_v2(native_work,'source.json')[0]
    require(source==initial,'workflow-source')
    if mode in ('bootstrap','release'):
        receipts,attestation=_linux_execution(work,policy,source,native)
    else:
        receipts={**native,**{name:read_source_file_v2(ROOT,
            policy.document['producer_receipt']['path'].format(producer_id=name))[0]
            for name in ('linux-python','linux-rust')}}
        attestation=read_source_file_v2(ROOT,policy.document['linux']['attestation_path'])[0]
    assembly=work/'assembly';assembly.mkdir(mode=0o700)
    report=assemble_v2(assembly,policy,source,receipts,attestation,before,
                       'generate' if mode=='bootstrap' else 'check')
    require(retained_report is None or retained_report==report,'release-report-changed')
    validate_source_projection_v2(initial,ROOT,policy)
    require(admit_transition_v2(ROOT,policy)[0]=='ready','workflow-final-state')
    print('M2 v2 '+mode+' passed; report SHA-256 '+digest(report)+'.',file=sys.stderr,flush=True)


def parse_arguments(args):
    if len(args)==1 and args[0] in ('bootstrap','full','release'):return (args[0],)
    if len(args)==3 and args[:2]==['linux-input','--native-receipts']:
        return 'linux-input',producer.absolute_path(Path(args[2]))
    require(len(args) in (9,11) and args[0]=='pair' and args[1]=='--kind'
        and args[3]=='--workers' and args[5]=='--rust-binary' and args[7]=='--work-root','arguments')
    kind=args[2];require(kind in ('native','linux') and args[4] in tuple(map(str,range(1,9))),'pair-arguments')
    require((kind=='native' and len(args)==9) or
        (kind=='linux' and len(args)==11 and args[9]=='--native-receipts'),'pair-input-arguments')
    return ('pair',kind,int(args[4]),producer.absolute_path(Path(args[6])),
            producer.absolute_path(Path(args[8])),producer.absolute_path(Path(args[10])) if len(args)==11 else None)


def main(args=None):
    previous=signal.getsignal(signal.SIGTERM)
    def cancel(number,_frame):raise SystemExit(128+number)
    signal.signal(signal.SIGTERM,cancel)
    try:
        parsed=parse_arguments(list(sys.argv[1:] if args is None else args))
        if parsed[0]=='pair':pair_v2(*parsed[1:])
        elif parsed[0]=='linux-input':linux_input_v2(parsed[1])
        else:workflow_v2(parsed[0])
        return 0
    except (ValueError,OSError,KeyError,TypeError) as error:
        print(('M2 v2 coordinator rejected: '+str(error))[:512],file=sys.stderr);return 2
    finally:signal.signal(signal.SIGTERM,previous)


if __name__=='__main__':raise SystemExit(main())
