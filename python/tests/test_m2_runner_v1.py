"""Explicit revised admission and recipient-only standalone equivalence."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from golden_board import m2_runner
from golden_board.m2_runner_v1 import m2_runner_v1
from golden_board.m2_slice_v1 import compile_slice_v1
from tools.m2 import learner_runner as old, learner_runner_v1 as standalone
from tools.m2.learner_content import build_cases
from tools.m2.learner_compile import compile_pages
from tools.m2.package_learner_v1 import build_files
from python.tests.test_m2_learner_runner import _generic_frame

ROOT = Path(__file__).resolve().parents[2]


class RevisedRunner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw,cls.owner = compile_pages(build_cases(ROOT))
        cls.sources = tuple((ROOT/p).read_bytes() for p in (
            'studies/m2/slice-v1.json','studies/m2/slice-v0.json','conformance/content-v0.json',
            'conformance/chess-v0.json','reports/game-set-v0.bin','spec/content-v0.md',
            'spec/constants-v0.toml','spec/curriculum-v0.toml'))
        cls.compiled = compile_slice_v1(*cls.sources)

    def test_explicit_identity_preserves_old_entry_and_strict_types(self):
        from golden_board.m2_slice import compile_slice_v0
        historical = compile_slice_v0(*self.sources[1:]).content_bytes
        changed = self.raw[:-1]+bytes((self.raw[-1]^1,))
        for wrong in (historical,self.compiled.content_bytes,self.raw[:-1],changed):
            for factory in (m2_runner_v1,standalone.StandaloneRunner):
                with self.subTest(factory=factory,length=len(wrong)),self.assertRaises(ValueError):
                    factory(wrong,label_suppressed=True)
        for factory in (m2_runner.m2_runner,old.StandaloneRunner):
            factory(historical,label_suppressed=True)
            with self.assertRaises(ValueError):factory(self.raw,label_suppressed=True)
        for factory in (m2_runner_v1,standalone.StandaloneRunner):
            with self.assertRaises(TypeError):factory(bytearray(self.raw),label_suppressed=True)
            with self.assertRaises(TypeError):factory(self.raw,label_suppressed=1)

    def test_all_pages_and_opposite_final_choices_match_generic_runtime(self):
        for suppressed in (False,True):
            generic = m2_runner_v1(self.raw,label_suppressed=suppressed)
            runner = standalone.StandaloneRunner(self.raw,label_suppressed=suppressed)
            commands = []
            for index,page in enumerate(self.owner['pages']):
                if index:
                    generic.advance(); runner.advance(); commands.append({'advance':True})
                self.assertEqual(runner.frame(),_generic_frame(generic.frame()))
                self.assertEqual(runner.frame()['current_node_id'],page['node_id'])
                choice = 3-page['correct'][0] if page['phase']=='heldout' else page['correct'][0]
                actions = (b'\x01\0'+choice.to_bytes(2,'big'),bytes.fromhex('02000000'),
                           b'\x01\0'+choice.to_bytes(2,'big'),bytes.fromhex('03000000'))
                for action in actions:
                    self.assertEqual(runner.perform(action),generic.perform(action))
                    self.assertEqual(runner.frame(),_generic_frame(generic.frame()))
                    commands.append({'action_hex':action.hex()})
                if page['phase']=='heldout':
                    self.assertEqual((runner.frame()['outcome'],runner.frame()['passive']),(3,None))
            self.assertFalse(runner.frame()['can_advance'])
            encoded = json.dumps({'schema':standalone.COMMAND_SCHEMA,'commands':commands}).encode()
            transcript = json.loads(standalone.run_commands(self.raw,encoded,label_suppressed=suppressed))
            self.assertEqual(transcript['final_frame'],runner.frame())
            self.assertEqual(len(transcript['results']),324)

    def test_retry_and_budget_exhaustion_are_authored_behavior(self):
        runner = standalone.StandaloneRunner(self.raw,label_suppressed=True)
        generic = m2_runner_v1(self.raw,label_suppressed=True)
        for _ in range(16):
            self.assertEqual(runner.perform(bytes.fromhex('02000000')),
                             generic.perform(bytes.fromhex('02000000')))
        self.assertEqual(runner.frame(),_generic_frame(generic.frame()))
        self.assertEqual(runner.frame()['phase'],3)
        with self.assertRaises(ValueError):runner.perform(bytes.fromhex('03000000'))

    def test_recipient_cli_needs_no_repository_and_exposes_no_owner_answers(self):
        files = build_files(self.raw)
        self.assertEqual(set(files),{'READ-ME.txt','index.html','layout.js','ui.js','viewer.js',
            'lesson-data.js','lesson.content-v0.bin','learner_runner.py','learner_runner_v1.py'})
        self.assertEqual(files['lesson.content-v0.bin'],self.raw)
        self.assertEqual(files['learner_runner.py'],(ROOT/'tools/m2/learner_runner.py').read_bytes())
        command = {'schema':standalone.COMMAND_SCHEMA,'commands':[{'action_hex':'02000000'}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            for name,raw in files.items():(path/name).write_bytes(raw)
            (path/'commands.json').write_text(json.dumps(command))
            result = subprocess.run([sys.executable,'-I','learner_runner_v1.py',
                '--content-stream','lesson.content-v0.bin','--commands','commands.json','--label-suppressed'],
                cwd=path,capture_output=True,check=False)
            self.assertEqual(result.returncode,0,result.stderr)
            transcript = json.loads(result.stdout)
            self.assertEqual(transcript['schema'],'golden-board.learner-runner-transcript/v1')
            self.assertEqual(transcript['content_stream_sha256'],self.compiled.required_content_sha256)
            for secret in ('evaluator_predicate','matching_answers','correct','record_move_hex','after_hex'):
                self.assertNotIn(secret,result.stdout.decode())

    def test_command_shapes_and_derived_resource_limits_fail_closed(self):
        runner = standalone.StandaloneRunner(self.raw,label_suppressed=True)
        limits = runner.limits
        self.assertEqual((limits.events,limits.commands),(4160,8320))
        self.assertLess(limits.output_bytes,524288)
        valid = lambda commands: json.dumps({'schema':standalone.COMMAND_SCHEMA,'commands':commands}).encode()
        for raw in (b'[]',b'{"schema":0,"schema":1,"commands":[]}',valid([{'advance':1}]),
                    valid([{'action_hex':'0100000A'}]),valid([{'advance':True,'extra':0}]),
                    b'['*2000+b']'*2000,b' '*(limits.command_bytes+1),valid([{'advance':True}]*4161)):
            with self.subTest(length=len(raw)),self.assertRaises(ValueError):
                standalone.run_commands(self.raw,raw,label_suppressed=True)
        self.assertEqual(old.COMMAND_COUNT_MAX,256)
        self.assertEqual(old.OUTPUT_BYTES_MAX,1048576)

    def test_exact_maximum_command_path_fits_the_derived_bounds(self):
        runner = standalone.StandaloneRunner(self.raw,label_suppressed=True)
        commands = []
        # Empty commits traverse the worked nodes and repeat the first
        # practice rejection. Each commit permits one advance, even the last
        # exhausted advance; this witnesses the actual2G command ceiling.
        for _ in range(runner.limits.events):
            commands.extend(({'action_hex':'03000000'},{'advance':True}))
        encoded = json.dumps({'schema':standalone.COMMAND_SCHEMA,'commands':commands},
                             sort_keys=True,separators=(',',':')).encode()+b'\n'
        self.assertEqual(len(encoded),runner.limits.command_bytes)
        actual = standalone.run_commands(self.raw,encoded,label_suppressed=True)
        self.assertLessEqual(len(actual),runner.limits.output_bytes)
        result = json.loads(actual)
        final = result['final_frame']
        self.assertEqual((len(result['results']),len(final['events']),final['phase'],
                          final['global_remaining'],final['local_remaining']),
                         (8320,4160,3,0,0))
        self.assertEqual((runner.limits.command_bytes,runner.limits.output_bytes,
                          runner.limits.frame_bytes,runner.limits.event_bytes),
                         (178946,281290,14878,50))
        commands.append({'action_hex':'02000000'})
        excessive = json.dumps({'schema':standalone.COMMAND_SCHEMA,'commands':commands},
                               separators=(',',':')).encode()
        with self.assertRaises(ValueError):
            standalone.run_commands(self.raw,excessive,label_suppressed=True)


if __name__ == '__main__':
    unittest.main()
