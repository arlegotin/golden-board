from copy import deepcopy
from hashlib import sha256
import io
import json
from pathlib import Path
import unittest
import zipfile

from golden_board.m2_runner import GenericRunner
from tools.m2.learner_compile import compile_pages, reference_transcript, _wire
from tools.m2.learner_content import build_cases
from tools.m2.learner_session import review_session
from tools.m2.package_learner_v1 import build_files, archive_bytes

ROOT = Path(__file__).resolve().parents[2]


class LearnerSession(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw, cls.owner = compile_pages(build_cases(ROOT))
        commands = reference_transcript(cls.raw, cls.owner)['commands']
        runner = GenericRunner(cls.raw, label_suppressed=True)
        commitments = []
        for command in commands:
            if 'advance' in command:
                runner.advance()
            else:
                runner.perform(bytes.fromhex(command['action_hex']))
                if command['action_hex'] == '03000000':
                    frame = _wire(runner.frame())
                    commitments.append({key:frame['current_node_id' if key == 'node_id' else key]
                        for key in ('node_id','committed_response_hex','outcome','feedback_ref','next_node_ref')})
        frame = _wire(runner.frame())
        cls.session = dict(schema='golden-board.learner-prototype-session/v0',
            content_stream_sha256=cls.owner['content_sha256'], attempt=1,
            commands=commands, events=frame['events'], commitments=commitments,
            final_state={key:frame[key] for key in ('current_node_id','global_remaining',
                'local_remaining','phase','outcome','selection_buffer','committed_response_hex',
                'feedback_ref','next_node_ref','events')}, examples_seen=[])

    def test_replay_scores_only_external_answers_and_rejects_forged_summary(self):
        result = review_session(self.session, self.raw, self.owner)
        self.assertTrue(result['complete'])
        self.assertEqual((result['matching_answers'], result['question_count']), (12, 12))
        for field in ('commitments', 'events'):
            changed = deepcopy(self.session)
            changed[field] = []
            with self.assertRaises(ValueError):
                review_session(changed, self.raw, self.owner)
        changed = deepcopy(self.session)
        changed['final_state']['global_remaining'] = float(changed['final_state']['global_remaining'])
        with self.assertRaises(ValueError):
            review_session(changed, self.raw, self.owner)

    def test_wrong_final_is_recorded_without_revealing_or_rejecting_answer(self):
        changed = deepcopy(self.session)
        first = next(p for p in self.owner['pages'] if p['phase'] == 'heldout')
        run = GenericRunner(self.raw, label_suppressed=True)
        for command in changed['commands']:
            if 'advance' in command:
                run.advance()
            else:
                if run.frame().current_node_id == first['node_id'] and command['action_hex'].startswith('01'):
                    command['action_hex'] = f"0100{3-first['correct'][0]:04x}"
                run.perform(bytes.fromhex(command['action_hex']))
                if run.frame().current_node_id == first['node_id'] and command['action_hex'] == '03000000':
                    self.assertEqual(run.frame().outcome, 3)
                    self.assertEqual(run.frame().passive, None)
                    break

    def test_valid_exhausted_revised_session_replays_all_8320_commands(self):
        runner = GenericRunner(self.raw, label_suppressed=True)
        commands, commitments = [], []
        # Empty commits reach a practice node, whose rejection loops. Each
        # event permits one advance, including the final exhausted advance.
        for _ in range(4160):
            runner.perform(bytes.fromhex('03000000'))
            frame = runner.frame()
            commitments.append(dict(node_id=frame.current_node_id,
                committed_response_hex=frame.committed_response.hex(),outcome=frame.outcome,
                feedback_ref=frame.feedback_ref,next_node_ref=frame.next_node_ref))
            runner.advance()
            commands.extend(({'action_hex':'03000000'},{'advance':True}))
        frame = _wire(runner.frame())
        session = dict(schema='golden-board.learner-prototype-session/v0',
            content_stream_sha256=sha256(self.raw).hexdigest(),attempt=1,
            commands=commands,events=frame['events'],commitments=commitments,
            final_state={key:frame[key] for key in ('current_node_id','global_remaining',
                'local_remaining','phase','outcome','selection_buffer','committed_response_hex',
                'feedback_ref','next_node_ref','events')},examples_seen=[])
        result = review_session(session,self.raw,self.owner)
        self.assertEqual((result['command_count'],result['commitment_count']), (8320,4160))
        self.assertTrue(result['exhausted'])
        self.assertFalse(result['complete'])
        session['commands'].append({'action_hex':'02000000'})
        with self.assertRaisesRegex(ValueError,'command count'):
            review_session(session,self.raw,self.owner)

    def test_command_bound_comes_from_validated_root_not_owner_claim(self):
        base = json.loads((ROOT/'conformance/content-v0.json').read_bytes())['bases'][0]
        raw = bytes.fromhex(base['stream_hex'])
        self.assertEqual(GenericRunner(raw,label_suppressed=True).frame().global_remaining,8)
        session = deepcopy(self.session)
        session['content_stream_sha256'] = sha256(raw).hexdigest()
        session['commands'] = [{'action_hex':'02000000'}]*17
        owner = dict(content_sha256=sha256(raw).hexdigest(),global_budget=4160,pages=[])
        with self.assertRaisesRegex(ValueError,'command count'):
            review_session(session,raw,owner)

    def test_package_binds_exact_bytes_and_contains_only_participant_files(self):
        files = build_files(self.raw)
        self.assertEqual(set(files), {'READ-ME.txt','index.html','layout.js','ui.js',
                                     'viewer.js','lesson-data.js','lesson.content-v0.bin',
                                     'learner_runner.py','learner_runner_v1.py'})
        self.assertEqual(files['lesson.content-v0.bin'], self.raw)
        archive = archive_bytes(files)
        self.assertEqual(archive, archive_bytes(dict(reversed(list(files.items())))))
        with zipfile.ZipFile(io.BytesIO(archive)) as opened:
            self.assertEqual(opened.namelist(), ['golden-board-learner/'+name for name in sorted(files)])
            for name, data in files.items():
                self.assertEqual(opened.read('golden-board-learner/'+name), data)
        damaged = self.raw[:-1] + bytes((self.raw[-1] ^ 1,))
        with self.assertRaises(ValueError):
            build_files(damaged)
