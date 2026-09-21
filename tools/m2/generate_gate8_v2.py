#!/usr/bin/env python3
"""Independent Python producer; canonical authority is coordinator-owned."""
from hashlib import sha256
import os
from pathlib import Path
import platform
import selectors
import stat
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
if __name__=='__main__':
    # -B suppresses writes but still reads existing pyc files. Artifact factories
    # must be imported from the current frozen source, including direct CLI use.
    _import_cache=tempfile.TemporaryDirectory(prefix='golden-board-v2-imports-')
    sys.pycache_prefix=_import_cache.name;sys.dont_write_bytecode=True

from golden_board import canonical_manifest as manifest
from golden_board.m2_gate8_policy_v2 import load_gate8_policy_v2,_document,validate_result_file_rows_v2
from golden_board.m2_source_v2 import (build_source_projection_v2,read_source_file_v2,
                                      validate_source_projection_v2,_path)
from golden_board.m2_preflight_v2 import SOURCE_PATHS,build_preflight_v2
from golden_board.m2_complete_candidate_v2 import build_complete_candidate_v2,_enter
from golden_board.m2_gate8_receipts_v2 import environment_identity_v2,render_producer_receipt_v2
from tools.m2.package_participant_v2 import (build_technical_files_v2,build_learner_files_v2,
    render_bundle_manifest_v2,render_bundle_preimages_v2)
from tools.m2.generate_damage import _rename_noreplace


def require(ok,reason):
    if not ok:raise ValueError('gate8-execution-v2:'+reason)


def digest(raw):return sha256(raw).hexdigest()


def file_row(path,raw):
    require(type(raw) is bytes and 0<len(raw)<=1048576,'file-bytes')
    return dict(path=path,mode='100644',bytes=len(raw),sha256=digest(raw))


def core_paths(policy):
    return tuple(p for p in _document(policy)['candidate_files']['fixed']
                 if p not in ('independence-proof.json','bundle-preimages.json'))


def _hash(value):
    return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)


def render_ready_v2(policy,producer_id,source_hash,files):
    raw=manifest.serialize_manifest(dict(schema='golden-board.m2-preflight-ready/v2',
        producer_id=producer_id,source_projection_sha256=source_hash,
        core_rows=[file_row(path,data) for path,data in files]))
    admit_ready_v2(raw,policy,producer_id,source_hash)
    return raw


def admit_ready_v2(raw,policy,producer_id,source_hash):
    owner=_document(policy)
    require(type(raw) is bytes and 0<len(raw)<=16384,'ready-bound')
    value=manifest.validate_canonical_manifest(raw)
    require(set(value)=={'schema','producer_id','source_projection_sha256','core_rows'}
        and value['schema']=='golden-board.m2-preflight-ready/v2'
        and producer_id in owner['producer_receipt']['producer_order'] and value['producer_id']==producer_id
        and _hash(source_hash) and value['source_projection_sha256']==source_hash,'ready-context')
    rows=value['core_rows'];paths=core_paths(policy)
    require(type(rows) is list and len(rows)==len(paths)==22,'ready-count')
    for row,path in zip(rows,paths,strict=True):
        require(type(row) is dict and set(row)=={'path','mode','bytes','sha256'}
            and row['path']==path and row['mode']=='100644' and type(row['bytes']) is int
            and 0<row['bytes']<=1048576 and _hash(row['sha256']),'ready-row')
    return value


def core_rows_sha256(rows):
    return digest(manifest.serialize_manifest(dict(schema='golden-board.m2-preflight-files/v2',rows=rows)))


def render_release_v2(ready):
    return manifest.serialize_manifest(dict(schema='golden-board.m2-preflight-release/v2',
        source_projection_sha256=ready['source_projection_sha256'],
        core_rows_sha256=core_rows_sha256(ready['core_rows'])))


def admit_release_v2(raw,ready):
    require(type(raw) is bytes and 0<len(raw)<=4096,'release-bound')
    manifest.validate_canonical_manifest(raw)
    require(raw==render_release_v2(ready),'release-binding')


def read_release_v2(stream,timeout=3600):
    deadline=time.monotonic()+timeout;raw=bytearray()
    with selectors.DefaultSelector() as selector:
        selector.register(stream,selectors.EVENT_READ)
        while True:
            remaining=deadline-time.monotonic();require(remaining>0,'release-timeout')
            require(selector.select(remaining),'release-timeout')
            chunk=os.read(stream.fileno(),4097-len(raw))
            if not chunk:break
            raw.extend(chunk);require(len(raw)<=4096,'release-bound')
    return bytes(raw)


def _directory(path,*,private=False):
    metadata=path.lstat()
    require(stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode),'directory')
    if private:require(stat.S_IMODE(metadata.st_mode)==0o700,'directory-mode')


def absolute_path(path):
    require(isinstance(path,Path) and path.is_absolute() and str(path)==os.path.abspath(path)
        and all(part not in ('.','..') for part in path.parts),'absolute-path')
    for parent in reversed(path.parents):_directory(parent)
    return path


def admit_work_root(work,repository,executable):
    absolute_path(work);_directory(work,private=True)
    repository=repository.absolute();executable=executable.absolute()
    require(not work.is_relative_to(repository) and not repository.is_relative_to(work)
        and not executable.is_relative_to(work),'work-alias')
    def identity(path):
        info=path.stat();return info.st_dev,info.st_ino
    work_identity=identity(work);repository_identity=identity(repository)
    require(repository_identity not in {identity(path) for path in (work,*work.parents)}
        and work_identity not in {identity(path) for path in (repository,*repository.parents)}
        and work_identity not in {identity(path) for path in executable.parents},'work-inode-alias')
    with os.scandir(work) as entries:require(next(entries,None) is None,'work-not-empty')


def fsync_directory(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)


def write_file(root,relative,raw):
    _path(relative);require(type(raw) is bytes and len(raw)<=4194306,'write-bound')
    absolute_path(root);_directory(root,private=True);current=root
    try:
        for component in relative.split('/')[:-1]:
            parent=current;current=current/component
            try:current.mkdir(mode=0o700)
            except FileExistsError:pass
            _directory(current,private=True);fsync_directory(parent)
        path=root/relative
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
        with os.fdopen(fd,'wb') as stream:
            os.fchmod(stream.fileno(),0o644);stream.write(raw);stream.flush();os.fsync(stream.fileno())
        fsync_directory(current)
    except OSError as error:raise ValueError('gate8-execution-v2:write') from error


def tree_rows(root,max_files,max_file_bytes,max_total):
    absolute_path(root);_directory(root,private=True)
    pending=[root];rows=[];inodes=set();entries=0;total=0;directories=set()
    while pending:
        current=pending.pop()
        with os.scandir(current) as scan:
            for entry in scan:
                entries+=1;require(entries<=2*max_files+128,'tree-entries')
                path=Path(entry.path);relative=path.relative_to(root).as_posix();_path(relative)
                metadata=entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(metadata.st_mode):
                    _directory(path,private=True);directories.add(relative);pending.append(path);continue
                require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink==1
                    and stat.S_IMODE(metadata.st_mode)==0o644,'tree-file')
                inode=(metadata.st_dev,metadata.st_ino);require(inode not in inodes,'tree-alias');inodes.add(inode)
                raw,admitted=read_source_file_v2(root,relative,max_file_bytes)
                identity=lambda info:(info.st_dev,info.st_ino,info.st_size,info.st_mode,
                    info.st_nlink,info.st_mtime_ns,info.st_ctime_ns)
                require(admitted['mode']=='100644' and identity(path.lstat())==identity(metadata),'tree-file-changed')
                require(len(rows)<max_files and raw,'tree-file-count')
                total+=len(raw);require(total<=max_total,'tree-total')
                rows.append(dict(path=relative,mode='100644',bytes=len(raw),sha256=digest(raw)))
    expected={str(parent) for row in rows for parent in Path(row['path']).parents if str(parent)!='.'}
    require(directories==expected,'tree-extra-directory')
    return tuple(sorted(rows,key=lambda row:row['path']))


def executable_identity(path,implementation,maximum=536870912):
    absolute_path(path)
    before=path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and 0<before.st_size<=maximum,'executable-file')
    h=sha256();length=0
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        opened=os.fstat(stream.fileno())
        require((opened.st_dev,opened.st_ino)==(before.st_dev,before.st_ino),'executable-open')
        while chunk:=stream.read(65536):
            length+=len(chunk);require(length<=maximum,'executable-bound');h.update(chunk)
    after=path.lstat()
    identity=lambda info:(info.st_dev,info.st_ino,info.st_size,info.st_mode,info.st_nlink,info.st_mtime_ns,info.st_ctime_ns)
    require(identity(before)==identity(after) and length==before.st_size,'executable-race')
    return dict(implementation=implementation,bytes=length,sha256=h.hexdigest())


def atomic_last_file(root,name,raw,*,postcondition=lambda:None):
    _path(name);require('/' not in name,'last-file-path')
    absolute_path(root);_directory(root)
    fd,temporary=tempfile.mkstemp(prefix='.receipt-',dir=root);path=Path(temporary)
    identity=None;installed=False
    try:
        with os.fdopen(fd,'wb') as stream:
            os.fchmod(stream.fileno(),0o644);stream.write(raw);stream.flush();os.fsync(stream.fileno())
            info=os.fstat(stream.fileno());identity=(info.st_dev,info.st_ino)
        _rename_noreplace(path,root/name);installed=True;fsync_directory(root);postcondition()
    except BaseException:
        if installed:
            info=(root/name).lstat()
            if (info.st_dev,info.st_ino)==identity:(root/name).unlink()
        raise
    finally:
        if path.exists():path.unlink()


def parse_arguments(arguments):
    require(type(arguments) is list and len(arguments)==7 and arguments[0]=='producer'
        and arguments[1]=='--producer-id' and arguments[3]=='--workers' and arguments[5]=='--work-root',
        'arguments')
    require(arguments[2] in ('native-python','linux-python') and arguments[4] in tuple(map(str,range(1,9))),
            'producer-workers')
    work=Path(arguments[6]);absolute_path(work)
    return arguments[2],int(arguments[4]),work


def finish_candidate_v2(preflight,workers,work,policy,source_raw,*,freeze=lambda:None):
    """Fresh full candidate and kits, called only after independent core agreement."""
    candidate=work/'candidate';candidate.mkdir(mode=0o700)
    completed=build_complete_candidate_v2(preflight,workers,
        lambda path,raw:write_file(candidate,path,raw),lambda path:read_source_file_v2(candidate,path,1048576)[0])
    require(completed.passed,'candidate-failed')
    freeze()
    bundles=[]
    for kind,build in (('technical',build_technical_files_v2),('learner',build_learner_files_v2)):
        files=build(ROOT,preflight)
        raw=render_bundle_manifest_v2(policy,kind,files,source_raw,preflight)
        prefix='bundles/'+kind+'-v2/'
        for path,data in files.items():write_file(work,prefix+path,data)
        write_file(work,prefix+'bundle-manifest.json',raw)
        actual=tree_rows(work/'bundles'/(kind+'-v2'),256,4194306,67108864)
        expected=tuple(sorted((dict(path=path,mode='100644',bytes=len(data),sha256=digest(data))
            for path,data in {**files,'bundle-manifest.json':raw}.items()),key=lambda row:row['path']))
        require(actual==expected,'bundle-preimages')
        bundles.append((kind,files,raw))
        freeze()
    projection=render_bundle_preimages_v2(policy,tuple(bundles),source_raw,preflight)
    write_file(candidate,'bundle-preimages.json',projection)
    damage_paths=tuple(row.path for row in completed.files if row.path.startswith('damage/')
                       or row.path=='resource-limits.json')
    rows=tree_rows(candidate,4120,1048576,570425344)
    validate_result_file_rows_v2(policy,rows,damage_paths)
    expected={row.path:(row.bytes,row.sha256) for row in completed.files}
    expected['bundle-preimages.json']=(len(projection),digest(projection))
    require({row['path']:(row['bytes'],row['sha256']) for row in rows}==expected,'candidate-preimages')
    freeze()
    return rows,damage_paths


def observed_environment_v2(producer_id):
    kind=producer_id.split('-')[0];require(kind in ('native','linux'),'environment-kind')
    acquisition=None
    if kind=='linux':
        require(platform.system()=='Linux' and platform.machine() in ('aarch64','arm64'),'linux-platform')
        acquisition=read_source_file_v2(ROOT,'artifacts/linux/verifier-v0.env',379)[0]
    architecture={'aarch64':'arm64','AMD64':'x86_64'}.get(platform.machine(),platform.machine())
    return environment_identity_v2(kind,platform.system().lower()+'/'+architecture,acquisition)


def produce(producer_id,workers,work):
    require(Path.cwd()==ROOT,'repository-cwd')
    executable=Path(sys.executable).resolve()
    admit_work_root(work,ROOT,executable)
    policy=load_gate8_policy_v2(read_source_file_v2(ROOT,'spec/gate8-policy-v2.toml')[0])
    source_raw=build_source_projection_v2(ROOT,policy)
    identity=executable_identity(executable,'python',policy.document['bounds']['executable_bytes'])
    environment=observed_environment_v2(producer_id)
    def freeze():
        validate_source_projection_v2(source_raw,ROOT,policy)
        require(identity==executable_identity(executable,'python',policy.document['bounds']['executable_bytes']),
                'executable-changed')
        require(environment==observed_environment_v2(producer_id),'environment-changed')
    preflight=build_preflight_v2({path:read_source_file_v2(ROOT,path)[0] for path in SOURCE_PATHS})
    _enter(preflight,workers)
    write_file(work,'source.json',source_raw)
    for path,raw in preflight.files:write_file(work,'preflight/'+path,raw)
    ready_raw=render_ready_v2(policy,producer_id,digest(source_raw),preflight.files)
    ready=admit_ready_v2(ready_raw,policy,producer_id,digest(source_raw))
    require(tree_rows(work/'preflight',22,1048576,33554432)==tuple(ready['core_rows']),'preflight-preimages')
    freeze();sys.stdout.buffer.write(ready_raw);sys.stdout.buffer.flush()
    admit_release_v2(read_release_v2(sys.stdin.buffer),ready);freeze()
    rows,damage_paths=finish_candidate_v2(preflight,workers,work,policy,source_raw,freeze=freeze)
    receipt=render_producer_receipt_v2(policy,source_raw,producer_id,identity,environment,rows,damage_paths)
    freeze();atomic_last_file(work,'receipt.json',receipt,postcondition=freeze)


def main(arguments=None):
    try:
        produce(*parse_arguments(list(sys.argv[1:] if arguments is None else arguments)))
        return 0
    except (ValueError,OSError,KeyError,TypeError) as error:
        print(('M2 v2 producer rejected: '+str(error))[:512],file=sys.stderr)
        return 2


if __name__=='__main__':raise SystemExit(main())
