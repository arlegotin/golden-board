"""Run a source-built development replay; no Gate8 publication."""
import argparse
from collections import deque
from hashlib import sha256
import multiprocessing
from multiprocessing.util import Finalize
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
# Keep direct script invocation equivalent to the importable tools.m2 entry.
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from golden_board import canonical_manifest as manifest, curriculum, m2_policy
from golden_board.m2_carrier_v2 import build_development_carrier
from golden_board.m2_damage_v2 import DamageCorpusV2
from golden_board.m2_damage_oracle_v2 import DamageOracleV2
from golden_board.m2_damage_replay_v2 import FAMILIES, render_replay_row, validate_replay_row
from golden_board.m2_decoder_v2 import ObservationDecoderV2
from golden_board.m2_decoder_bridge_v2 import RevisionBatchDecoder
from golden_board.m2_resources_v2 import build_resource_limits_v2
from golden_board.m2_slice import compile_slice_v0
from golden_board.m2_slice_v1 import compile_slice_v1
from tools.m2.generate_damage import _rename_noreplace

SOURCE_PATHS=('studies/m2/slice-v0.json','conformance/content-v0.json','conformance/chess-v0.json',
    'reports/game-set-v0.bin','spec/content-v0.md','spec/constants-v0.toml','spec/curriculum-v0.toml')
OWNERS=('spec/profile-policy-v2.toml','spec/profile-limits-v2.toml','spec/damage-policy-v2.toml')
FACTORY_PATHS=(*SOURCE_PATHS,*OWNERS,'studies/m2/slice-v1.json',
    'spec/profile-policy-v0.toml','spec/route-data-v0.json')
PREFLIGHT=(('D0',0),('D0',7),('D1',0),('D2',0),('D3',0),('D3',96),('D4',0),('D6',0),
    *(('D7',i) for i in (0,10,16,401,402,405,408,413,414)),*(('B0',i) for i in range(21)))
_CONTEXT=None
_INIT_ERROR=None


def require(ok,reason):
    if not ok:raise ValueError('damage-replay:'+reason)


def compare_semantics(expected,actual,clean_envelopes):
    require((actual.artifact_state,actual.m2_required_stream,actual.m2_all_stream,
             actual.section_results,actual.fragment_diagnostics)==
            (expected.artifact_state,expected.required_stream,expected.all_stream,
             expected.semantic_result.section_results,expected.semantic_result.fragment_diagnostics),
            'source-semantic-disagreement')
    wrong=sum(row.envelope is not None and row.envelope!=clean_envelopes.get(row.section_id)
              for row in actual.section_results)
    require(wrong==expected.wrong_accepts,'source-wrong-accept-disagreement')


def case_keys(counts,boundary_count,selection):
    require(type(counts) is tuple and len(counts)==8
        and all(type(v) is int and 1<=v<=65535 for v in counts)
        and type(boundary_count) is int and boundary_count==21
        and sum(counts)+boundary_count<=65535,'case-counts')
    require(selection in ('all','preflight'),'selection')
    all_keys=tuple((family,i) for family,count in zip(FAMILIES,counts+(boundary_count,),strict=True)
                   for i in range(count))
    if selection=='all':return all_keys
    require(set(PREFLIGHT)<=set(all_keys),'preflight-domain')
    return PREFLIGHT


def publish_new_directory(output,produce):
    require(type(output) is type(Path()) and output.is_absolute()
        and output.name not in ('','.','..'),'output-path')
    for parent in output.parents:
        require(stat.S_ISDIR(parent.lstat().st_mode),'output-parent')
    require(not output.exists() and not output.is_symlink(),'output-exists')
    stage=Path(tempfile.mkdtemp(prefix='.damage-replay-v2-',dir=output.parent))
    try:
        produce(stage)
        require(not output.exists() and not output.is_symlink(),'output-appeared')
        _rename_noreplace(stage,output)
    finally:
        if stage.exists():shutil.rmtree(stage)


def read_regular(path,maximum=8388608):
    before=path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink==1
        and before.st_size<=maximum,'source-file')
    descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(descriptor,'rb') as stream:
        opened=os.fstat(stream.fileno())
        require((opened.st_dev,opened.st_ino)==(before.st_dev,before.st_ino),'source-replaced')
        raw=stream.read(maximum+1)
    after=path.lstat()
    require(len(raw)<=maximum and (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns)==
        (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns),'source-changed')
    return raw


def digest_row(path,raw):
    return dict(path=path,bytes=len(raw),sha256=sha256(raw).hexdigest())


def source_snapshot(root):
    result=subprocess.run(('git','ls-files','--cached','--others','--exclude-standard','-z'),
        cwd=root,check=True,stdout=subprocess.PIPE,timeout=30)
    require(len(result.stdout)<=1048576,'source-path-bound')
    paths=set(result.stdout.decode('utf-8').split('\0'))-{''}
    paths.update(FACTORY_PATHS)
    require(len(paths)<=4096,'source-count')
    rows=[];total=0
    for name in sorted(paths):
        path=Path(name)
        require(not path.is_absolute() and '..' not in path.parts,'source-path')
        for parent in (root/path).parents:
            if parent==root:break
            require(stat.S_ISDIR(parent.lstat().st_mode),'source-parent')
        raw=read_regular(root/path)
        # The visible checkout includes about74 MiB of historical evidence.
        # Bind it too; it is never supplied to either observation receiver.
        total+=len(raw);require(total<=134217728,'source-total')
        rows.append(digest_row(name,raw))
    return manifest.serialize_manifest(dict(schema='golden-board.m2-development-source/v2',files=rows))


def build_corpus(inputs):
    raws=tuple(inputs[path] for path in SOURCE_PATHS)
    compiled=compile_slice_v1(inputs['studies/m2/slice-v1.json'],*raws)
    image=build_development_carrier(compiled,compile_slice_v0(*raws),curriculum.load_blueprint(raws[-1]),
        m2_policy.load_profile_policy(inputs['spec/profile-policy-v0.toml']).capacity_policy)
    return DamageCorpusV2(image,alternate_route_owner_raw=inputs['spec/route-data-v0.json'])


def close_worker():
    global _CONTEXT
    if _CONTEXT is not None:
        if _CONTEXT[-1] is not None:
            _CONTEXT[-1]._abort()
        _CONTEXT=None


def terminate_worker(_signum,_frame):
    close_worker()
    raise SystemExit(143)


def initialize_worker(inputs,rust_binary):
    global _CONTEXT,_INIT_ERROR
    _INIT_ERROR=None
    signal.signal(signal.SIGTERM,terminate_worker)
    # Keep initializer failures as task errors; Pool must not endlessly respawn
    # workers when a source owner is invalid.
    try:
        corpus=build_corpus(inputs)
        oracle=DamageOracleV2(corpus)
        decoder=ObservationDecoderV2(*(inputs[p] for p in OWNERS))
        # A pending termination may run only after the newly spawned child has
        # an owner that can kill and reap it, including constructor interruption.
        previous_mask=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM})
        try:
            client=None if rust_binary is None else RevisionBatchDecoder((rust_binary,),timeout_seconds=120)
            _CONTEXT=(corpus,oracle,decoder,client)
            Finalize(None,close_worker,exitpriority=10)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK,previous_mask)
    except Exception as error:
        _INIT_ERROR=f'{type(error).__name__}: {error}'


def evaluate_case(task):
    require(_INIT_ERROR is None,'worker-initialization:'+str(_INIT_ERROR))
    require(_CONTEXT is not None,'worker-context')
    index,family,ordinal=task
    corpus,oracle,decoder,client=_CONTEXT
    case=corpus.boundary_case(ordinal) if family=='B0' else corpus.case(family,ordinal)
    expected=oracle.evaluate(case)
    # No source object, family ID or expected result enters either receiver.
    actual=decoder.decode(case.channel,case.observation)
    compare_semantics(expected,actual,corpus.clean_envelopes)
    result_raw=decoder.render_result(case.channel,actual)
    resources_raw=decoder.render_resources()
    if client is not None:
        rust=client.decode(case.channel,case.observation)
        require((rust.result_raw,rust.resources_raw)==(result_raw,resources_raw),
            'receiver-disagreement:'+case.case_id+':'+sha256(result_raw).hexdigest()+':'+
            sha256(rust.result_raw).hexdigest())
    row=render_replay_row(case=case,result_raw=result_raw,resources_raw=resources_raw,
        section_states=expected.section_states,wrong_accept_count=expected.wrong_accepts,
        section_ids=tuple(corpus.sections),required_section_ids=(1,2,3,16,17,18))
    return index,row


def parallel_rows(keys,inputs,rust_binary,workers):
    require(type(workers) is int and 1<=workers<=min(8,os.cpu_count() or 1),'workers')
    pool=multiprocessing.get_context('spawn').Pool(workers,initializer=initialize_worker,
        initargs=(inputs,None if rust_binary is None else str(rust_binary)))
    pending=deque();submitted=0;received=0
    try:
        while received<len(keys):
            while submitted<len(keys) and len(pending)<2*workers:
                family,ordinal=keys[submitted]
                pending.append(pool.apply_async(evaluate_case,((submitted,family,ordinal),)))
                submitted+=1
            index,raw=pending.popleft().get(timeout=900)
            require(index==received,'worker-order')
            yield raw
            received+=1
        pool.close();pool.join()
    except BaseException:
        pool.terminate();pool.join()
        raise


def write_file(path,raw):
    with path.open('xb') as stream:
        os.chmod(path,0o600);stream.write(raw);stream.flush();os.fsync(stream.fileno())


def generate(root,output,rust_binary,workers,selection):
    before=source_snapshot(root)
    binary=None if rust_binary is None else read_regular(rust_binary,67108864)
    python_binary=Path(sys.executable).resolve(strict=True)
    python_image=read_regular(python_binary,67108864)
    inputs={path:read_regular(root/path) for path in FACTORY_PATHS}
    require(source_snapshot(root)==before,'source-changed-before-start')
    corpus=build_corpus(inputs)
    keys=case_keys(corpus.family_counts,corpus.boundary_count,selection)
    ids=tuple(f'{family}-{ordinal:06d}' for family,ordinal in keys)

    def produce(stage):
        row_hash=sha256();identity_hash=sha256();rows_bytes=identities_bytes=0
        families={family:dict(family_id=family,case_count=0,wrong_accept_count=0,
                              failed_promise_count=0) for family in FAMILIES}
        with (stage/'cases.jsonl').open('xb') as rows,(stage/'identities.jsonl').open('xb') as identities:
            os.chmod(stage/'cases.jsonl',0o600);os.chmod(stage/'identities.jsonl',0o600)
            for index,raw in enumerate(parallel_rows(keys,inputs,rust_binary,workers)):
                family,ordinal=keys[index]
                case=corpus.boundary_case(ordinal) if family=='B0' else corpus.case(family,ordinal)
                value=validate_replay_row(raw,case,tuple(corpus.sections),(1,2,3,16,17,18))
                identity=manifest.serialize_manifest(value['observation'])
                rows.write(raw);identities.write(identity)
                row_hash.update(raw);identity_hash.update(identity)
                rows_bytes+=len(raw);identities_bytes+=len(identity)
                require(rows_bytes<=536870912 and identities_bytes<=16777216,'output-total')
                summary=families[family];summary['case_count']+=1
                summary['wrong_accept_count']+=value['wrong_accept_count']
                summary['failed_promise_count']+=value['promise_result']=='fail'
                if selection=='preflight' or (index+1)%100==0 or index+1==len(keys):
                    print(f'{index+1}/{len(keys)} {case.case_id} {value["decoder_result"]["artifact_state"]} {value["promise_result"]}',flush=True)
            for stream in (rows,identities):stream.flush();os.fsync(stream.fileno())

        def sidecars():
            with (stage/'cases.jsonl').open('rb') as stream:
                for case_id in ids:
                    raw=stream.readline(1048577)
                    require(len(raw)<=1048576 and raw.endswith(b'\n'),'stored-row-bound')
                    value=manifest.validate_canonical_manifest(raw)
                    require(value['observation']['case_id']==case_id,'stored-row-order')
                    yield case_id,manifest.serialize_manifest(value['resource_projection'])
                require(not stream.read(1),'stored-extra-row')
        limits=build_resource_limits_v2(identity_hash.hexdigest(),ids,sidecars())
        require(source_snapshot(root)==before,'source-changed-during-replay')
        if binary is not None:
            require(read_regular(rust_binary,67108864)==binary,'binary-changed-during-replay')
        require(read_regular(python_binary,67108864)==python_image,'python-changed-during-replay')
        write_file(stage/'resource-limits.json',limits)
        write_file(stage/'source.json',before)
        summary=dict(schema='golden-board.m2-development-replay/v2',
            scope=('python-semantic-oracle-and-python-receiver; independent-rust-reproduction-pending'
                   if binary is None else
                   'python-semantic-oracle-and-python-rust-receivers; independent-full-source-oracle-comparison-pending'),
            receiver_implementation='python' if binary is None else 'python-rust',
            python_executable_sha256=sha256(python_image).hexdigest(),
            selection=selection,complete_corpus=selection=='all',case_count=len(keys),
            family_rows=list(families.values()),
            files=[dict(path='cases.jsonl',bytes=rows_bytes,sha256=row_hash.hexdigest()),
                   dict(path='identities.jsonl',bytes=identities_bytes,sha256=identity_hash.hexdigest()),
                   digest_row('resource-limits.json',limits),digest_row('source.json',before)])
        if binary is not None:
            summary['rust_decoder_sha256']=sha256(binary).hexdigest()
        write_file(stage/'summary.json',manifest.serialize_manifest(summary))
    publish_new_directory(output,produce)


def parse_args(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection',choices=('preflight','all'),required=True)
    parser.add_argument('--workers',type=int,default=1)
    parser.add_argument('--receiver',choices=('python','python-rust'),default='python-rust')
    parser.add_argument('--rust-decoder',type=Path)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args(argv)
    if (args.receiver=='python') != (args.rust_decoder is None):
        parser.error('--receiver python requires no --rust-decoder; python-rust requires one')
    return args


def main():
    args=parse_args()
    generate(ROOT,args.output_dir.absolute(),None if args.rust_decoder is None else args.rust_decoder.absolute(),
             args.workers,args.selection)


if __name__=='__main__':main()
