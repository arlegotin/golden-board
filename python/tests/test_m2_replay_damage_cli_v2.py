"""A replay failure must leave no apparently completed evidence directory."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import os
import signal
import subprocess
import tempfile
import unittest

from golden_board.m2_decoder import DecodeResult, SectionResult
from tools.m2 import replay_damage_v2 as tool


class ReplayDamageCliV2(unittest.TestCase):
    def test_python_only_mode_requires_no_foreign_executable(self):
        args=tool.parse_args(['--selection','preflight','--receiver','python',
                              '--output-dir','/private/tmp/unused-replay-target'])
        self.assertEqual(args.receiver,'python')
        self.assertIsNone(args.rust_decoder)
        for extra in (['--receiver','python','--rust-decoder','/bin/cat'],
                      ['--receiver','python-rust']):
            with self.subTest(extra=extra),self.assertRaises(SystemExit):
                tool.parse_args(['--selection','all','--output-dir','/private/tmp/unused-replay-target',*extra])

    def test_python_worker_runs_actual_receiver_without_a_foreign_process(self):
        from golden_board import canonical_manifest
        from golden_board.m2_damage_v2 import DamageObservationV2
        root=Path(__file__).resolve().parents[2]
        owners={name:(root/name).read_bytes() for name in tool.OWNERS}
        case=DamageObservationV2('D7',0,'OBS_UNITS','framing-regression',(),b'\0')
        section_ids=(1,2,3,16,17,18)
        literal=DecodeResult('failure',None,(),(),False,())
        expected=SimpleNamespace(artifact_state='failure',required_stream=None,all_stream=None,
            semantic_result=literal,wrong_accepts=0,section_states=tuple((i,'unknown') for i in section_ids))
        corpus=SimpleNamespace(case=lambda family,ordinal:case,sections=section_ids,clean_envelopes={})
        oracle=SimpleNamespace(evaluate=lambda observed:expected)
        previous=signal.getsignal(signal.SIGTERM)
        try:
            # The hand-owned malformed frame isolates orchestration from the
            # expensive source compiler; receiver and canonical renderer are real.
            with patch.object(tool,'build_corpus',return_value=corpus),\
                 patch.object(tool,'DamageOracleV2',return_value=oracle),\
                 patch.object(tool,'RevisionBatchDecoder',side_effect=AssertionError('foreign process')):
                tool.initialize_worker(owners,None)
                self.assertIsNone(tool._INIT_ERROR)
                index,raw=tool.evaluate_case((0,'D7',0))
            row=canonical_manifest.validate_canonical_manifest(raw)
            self.assertEqual(index,0)
            self.assertEqual(row['decoder_result']['artifact_state'],'failure')
            self.assertEqual(row['observation'],case.identity())
            self.assertEqual(row['promise_result'],'pass')
            self.assertEqual(row['decoder_result']['resource']['primitive_steps'],0)
        finally:
            signal.signal(signal.SIGTERM,previous)
            tool.close_worker()
            tool._INIT_ERROR=None

    def test_semantic_disagreement_and_wrong_accept_cannot_be_hidden(self):
        actual=DecodeResult('failure',None,(),(),False,())
        expected=SimpleNamespace(artifact_state='failure',required_stream=None,all_stream=None,
            semantic_result=actual,wrong_accepts=0)
        self.assertIsNone(tool.compare_semantics(expected,actual,{}))
        with self.assertRaises(ValueError):tool.compare_semantics(expected,replace(actual,artifact_state='exact'),{})
        with self.assertRaises(ValueError):tool.compare_semantics(expected,replace(actual,m2_required_stream=b'forged'),{})
        changed=replace(actual,section_results=(SectionResult(1,'verified',b'changed'),))
        expected.semantic_result=changed
        with self.assertRaises(ValueError):tool.compare_semantics(expected,changed,{1:b'clean'})
        expected.wrong_accepts=1
        self.assertIsNone(tool.compare_semantics(expected,changed,{1:b'clean'}))

    def test_case_order_and_selection_cannot_omit_a_full_family(self):
        counts=(16,4,256,128,1908,21,7632,415)
        keys=tool.case_keys(counts,21,'all')
        self.assertEqual(len(keys),10401)
        self.assertEqual(keys[0],('D0',0));self.assertEqual(keys[-1],('B0',20))
        self.assertEqual(tuple(sum(f==family for f,_ in keys) for family in tool.FAMILIES),counts+(21,))
        selected=tool.case_keys(counts,21,'preflight')
        self.assertEqual(len(selected),38)
        self.assertEqual(len(set(selected)),38)
        for args in ((counts[:-1],21,'all'),(counts,True,'all'),(counts,21,'partial'),
                     ((True,)+counts[1:],21,'all'),(counts,20,'all')):
            with self.subTest(args=args),self.assertRaises(ValueError):tool.case_keys(*args)

    def test_stage_is_removed_on_error_and_existing_destination_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory).resolve()/'new'
            def fail(stage):
                (stage/'partial').write_bytes(b'private')
                raise ValueError('deliberate producer failure')
            with self.assertRaises(ValueError):tool.publish_new_directory(output,fail)
            self.assertFalse(output.exists())
            self.assertEqual(list(Path(directory).iterdir()),[])
            output.mkdir();(output/'keep').write_bytes(b'original')
            with self.assertRaises(ValueError):tool.publish_new_directory(output,fail)
            self.assertEqual((output/'keep').read_bytes(),b'original')

    def test_success_is_installed_only_after_producer_returns(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory).resolve()/'new'
            def write(stage):
                self.assertFalse(output.exists())
                (stage/'complete').write_bytes(b'complete')
            tool.publish_new_directory(output,write)
            self.assertEqual((output/'complete').read_bytes(),b'complete')

    def test_directory_appearing_after_last_check_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory).resolve()/'new'
            real_is_symlink=Path.is_symlink
            checks=0
            appeared={}
            def race_after_check(path):
                nonlocal checks
                answer=real_is_symlink(path)
                if path==output:
                    checks+=1
                    if checks==2:
                        # The final no-destination check has observed absence;
                        # another publisher creates a real empty directory.
                        output.mkdir(mode=0o701)
                        appeared['inode']=output.stat().st_ino
                return answer
            def produce(stage):
                (stage/'complete').write_bytes(b'private-stage')
            with patch.object(Path,'is_symlink',race_after_check):
                with self.assertRaises(ValueError):
                    tool.publish_new_directory(output,produce)
            self.assertEqual(checks,2)
            self.assertEqual(output.stat().st_ino,appeared['inode'])
            self.assertEqual(list(output.iterdir()),[])
            self.assertEqual(list(output.parent.iterdir()),[output])

    def test_termination_during_client_construction_reaps_the_child(self):
        # The expensive source factory is irrelevant to the exact Popen→client
        # registration interruption boundary. The subprocess and signal are real.
        children=[];real_popen=subprocess.Popen
        previous=signal.getsignal(signal.SIGTERM)
        def spawn(*args,**kwargs):
            child=real_popen(*args,**kwargs);children.append(child);return child
        def interrupt(_descriptor,_blocking):
            os.kill(os.getpid(),signal.SIGTERM)
        try:
            with patch.object(tool,'build_corpus',return_value=object()),\
                 patch.object(tool,'DamageOracleV2',return_value=object()),\
                 patch.object(tool,'ObservationDecoderV2',return_value=object()),\
                 patch('golden_board.m2_damage.subprocess.Popen',side_effect=spawn),\
                 patch('golden_board.m2_decoder_bridge_v2.os.set_blocking',side_effect=interrupt):
                with self.assertRaises(SystemExit):
                    tool.initialize_worker(dict.fromkeys(tool.OWNERS,b''),'/bin/cat')
            self.assertEqual(len(children),1)
            self.assertIsNotNone(children[0].poll(),'interrupted constructor leaked its child')
        finally:
            signal.signal(signal.SIGTERM,previous)
            tool.close_worker()
            for child in children:
                if child.poll() is None:child.kill();child.wait()
                for stream in (child.stdin,child.stdout):
                    if stream is not None:stream.close()


if __name__=='__main__':unittest.main()
