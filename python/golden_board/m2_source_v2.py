"""Bounded revised source identities; parsing alone is not source reproduction."""
from hashlib import sha256
import os
import selectors
import stat
import subprocess
import time

from . import canonical_manifest as manifest
from .m2_gate8 import _checked_path, _real_repository, roadmap_normative_sha256
from .m2_gate8_policy_v2 import _document


def require(ok,reason):
    if not ok:raise ValueError('source-v2:'+reason)


def _hash(value):
    return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)


def _path(value):
    require(type(value) is str,'path-type')
    try:raw=value.encode('ascii')
    except UnicodeError as error:raise ValueError('source-v2:path') from error
    return _checked_path(raw)[0]


def admit_source_projection_v2(raw,policy):
    """Admit exact bounded shape, without claiming filesystem or full coverage."""
    owner=_document(policy);bounds=owner['bounds'];contract=owner['source_projection']
    require(type(raw) is bytes and 0<len(raw)<=bounds['canonical_json_bytes'],'bytes')
    value=manifest.validate_canonical_manifest(raw)
    require(set(value)==set(contract['keys']) and value['schema']==contract['schema']
        and _hash(value['roadmap_normative_sha256']),'root')
    rows=value['entries']
    require(type(rows) is list and 1<=len(rows)<=bounds['source_files'],'entries')
    previous='';total=0
    for row in rows:
        require(type(row) is dict and set(row)==set(contract['row_keys']),'row')
        path=_path(row['path'])
        require(previous<path and path not in contract['excluded_paths'],'path-order')
        previous=path
        require(row['mode'] in ('100644','100755') and type(row['byte_length']) is int
            and 0<=row['byte_length']<=bounds['source_file_bytes'] and _hash(row['sha256']),'row-domain')
        total+=row['byte_length'];require(total<=bounds['source_aggregate_bytes'],'aggregate')
    return value


def _identity(st):
    return (st.st_dev,st.st_ino,st.st_mode,st.st_nlink,st.st_size,st.st_mtime_ns,st.st_ctime_ns)


def _git_visible_paths(root):
    # Neither inherited index/repository overrides nor a configured fsmonitor
    # hook may alter the source selected by this explicit repository root.
    environment={key:value for key,value in os.environ.items() if not key.startswith('GIT_')}
    environment.update(GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_NOSYSTEM='1',GIT_OPTIONAL_LOCKS='0')
    process=subprocess.Popen(('git','-c','core.excludesFile=/dev/null','-c','core.fsmonitor=false',
        '-C',os.fspath(root),'ls-files','--cached','--others','--exclude-standard','-z'),
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=environment)
    output=bytearray();errors=bytearray();deadline=time.monotonic()+30
    try:
        with selectors.DefaultSelector() as selector:
            for pipe,buffer,maximum in ((process.stdout,output,1048576),(process.stderr,errors,65536)):
                os.set_blocking(pipe.fileno(),False)
                selector.register(pipe,selectors.EVENT_READ,(buffer,maximum))
            while selector.get_map():
                remaining=deadline-time.monotonic();require(remaining>0,'git-timeout')
                for key,_ in selector.select(remaining):
                    chunk=os.read(key.fd,65536)
                    if not chunk:selector.unregister(key.fileobj);continue
                    buffer,maximum=key.data;buffer.extend(chunk)
                    require(len(buffer)<=maximum,'git-output')
        require(process.wait(timeout=max(0.001,deadline-time.monotonic()))==0,'git-exit')
        require(not output or output.endswith(b'\0'),'git-framing')
        paths=tuple(bytes(output).split(b'\0')[:-1])
        require(len(paths)<=4096 and len(set(paths))==len(paths),'git-count')
        return paths
    except BaseException:
        process.kill();process.wait();raise
    finally:
        process.stdout.close();process.stderr.close()


def read_source_file_v2(root,path,maximum=8388608):
    """Read through no-follow descriptors and check the same path afterward."""
    _path(path)
    descriptors=[];parents=[]
    try:
        fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);descriptors.append(fd)
        current=root
        for component in path.split('/')[:-1]:
            current=current/component
            fd=os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            descriptors.append(fd);parents.append((current,os.fstat(fd)))
        name=path.split('/')[-1]
        before=os.stat(name,dir_fd=fd,follow_symlinks=False)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size<=maximum,'file')
        file_fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd)
        with os.fdopen(file_fd,'rb') as stream:
            require(_identity(os.fstat(stream.fileno()))==_identity(before),'opened-race')
            raw=stream.read(maximum+1)
            require(_identity(os.fstat(stream.fileno()))==_identity(before),'read-race')
        after=os.stat(name,dir_fd=fd,follow_symlinks=False)
        require(_identity(after)==_identity(before) and len(raw)==before.st_size,'file-race')
        for directory,info in parents:
            now=directory.lstat()
            require(stat.S_ISDIR(now.st_mode) and (now.st_dev,now.st_ino)==(info.st_dev,info.st_ino),'parent-race')
        require(_identity((root/path).lstat())==_identity(before),'path-race')
        return raw,dict(path=path,mode='100755' if before.st_mode&0o111 else '100644',
                       byte_length=len(raw),sha256=sha256(raw).hexdigest())
    except OSError as error:
        raise ValueError('source-v2:file-access') from error
    finally:
        for fd in reversed(descriptors):os.close(fd)


def build_source_projection_v2(root,policy):
    owner=_document(policy);bounds=owner['bounds'];contract=owner['source_projection']
    root=_real_repository(root)
    paths=tuple(sorted(_git_visible_paths(root)))
    require(len(paths)<=bounds['source_files'] and b'docs/roadmap.md' in paths,'visible-source')
    rows=[];total=0
    for encoded in paths:
        path=_checked_path(encoded)[0]
        if path in contract['excluded_paths']:continue
        # Preserve the existing current-worktree enumeration for tracked paths
        # intentionally absent in the checkout. Existing links still reject.
        try:(root/path).lstat()
        except FileNotFoundError:continue
        _,row=read_source_file_v2(root,path,bounds['source_file_bytes'])
        total+=row['byte_length'];require(total<=bounds['source_aggregate_bytes'],'aggregate')
        rows.append(row)
    roadmap,_=read_source_file_v2(root,'docs/roadmap.md',bounds['source_file_bytes'])
    require(tuple(sorted(_git_visible_paths(root)))==paths,'enumeration-race')
    raw=manifest.serialize_manifest(dict(schema=contract['schema'],
        roadmap_normative_sha256=roadmap_normative_sha256(roadmap),entries=rows))
    admit_source_projection_v2(raw,policy)
    return raw


def validate_source_projection_v2(raw,root,policy):
    value=admit_source_projection_v2(raw,policy)
    require(raw==build_source_projection_v2(root,policy),'stale')
    return value
