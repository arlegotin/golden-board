"""A compact reviewed human result binds the unchanged recipient files."""
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from golden_board import canonical_manifest as manifest
from golden_board.m2_gate8_policy_v2 import load_gate8_policy_v2

ROOT = Path(__file__).resolve().parents[2]
H = 'a'*64


def record(technical_hash, learner_hash):
    return manifest.serialize_manifest(dict(
        schema='golden-board.m2-human-qualification/v2',
        trial_id='20-open-technical-group',frozen_source_snapshot_sha256=H,
        technical=dict(unit='fresh-three-person-group',result='pass',group_final_sha256=H,
            review_sha256=H,packet_files_sha256=technical_hash,clean_abc='exact',
            d_strict='explicit-refusal',content_query='exact'),
        learner=dict(unit='fresh-individual',result='pass',answer_sha256=H,
            attempt_sha256=H,review_sha256=H,packet_files_sha256=learner_hash,finals_correct=12),
        source_reconciliation=dict(meaning='nonsemantic-execution-and-qualification-only',
            changed_paths=['python/golden_board/m2_gate8_reports_v2.py'])))


class QualificationV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy=load_gate8_policy_v2((ROOT/'spec/gate8-policy-v2.toml').read_bytes())

    def test_tracked_record_passes_release_shape_preflight(self):
        from golden_board.m2_qualification_v2 import qualification_shape_v2
        raw=(ROOT/'studies/m2/qualification-v2.json').read_bytes()
        try:value=qualification_shape_v2(raw)
        except ValueError as error:self.fail(f'tracked qualification rejected: {error}')
        self.assertEqual(value['trial_id'],'20-open-technical-group')

    def test_record_binds_exact_current_bundle_files_and_rejects_mutation(self):
        from golden_board.m2_qualification_v2 import admit_qualification_v2, packet_files_digest_v2
        with tempfile.TemporaryDirectory(prefix='gb-m2-qualification-') as name:
            root=Path(name)
            digests={}
            for kind in ('technical','learner'):
                paths=(*self.policy.document[kind+'_bundle']['participant_paths'],
                       *self.policy.document[kind+'_bundle']['owner_paths'])
                files={path:('fixture '+kind+' '+path+'\n').encode() for path in paths}
                for path,raw in files.items():
                    target=root/'artifacts/gate8/bundles'/kind/path
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(raw)
                digests[kind]=packet_files_digest_v2(files)
            raw=record(digests['technical'],digests['learner'])
            self.assertEqual(admit_qualification_v2(raw,self.policy,root)['trial_id'],'20-open-technical-group')
            target=root/'artifacts/gate8/bundles/learner/recipient/lesson.content-v0.bin'
            target.write_bytes(target.read_bytes()+b'x')
            with self.assertRaises(ValueError):admit_qualification_v2(raw,self.policy,root)
            target.write_bytes(target.read_bytes()[:-1])
            changed=manifest.validate_canonical_manifest(raw)
            changed['learner']['finals_correct']=11
            with self.assertRaises(ValueError):admit_qualification_v2(
                manifest.serialize_manifest(changed),self.policy,root)

    def test_completion_installs_last_and_restores_ready_status_on_late_failure(self):
        from tools.m2 import verify_gate8_v2 as coordinator
        ready=b'fixture candidate-ready roadmap\n'
        complete=b'fixture complete roadmap\n'
        with tempfile.TemporaryDirectory(prefix='gb-m2-completion-') as name:
            root=Path(name).resolve()
            (root/'docs').mkdir();(root/'artifacts').mkdir();(root/'reports').mkdir()
            (root/'studies/m2').mkdir(parents=True)
            (root/'docs/roadmap.md').write_bytes(ready)
            (root/'studies/m2/qualification-v2.json').write_bytes(record(H,H))
            with patch('golden_board.m2_gate8_reports_v2.render_candidate_ready_roadmap_v2',
                    return_value=ready),patch(
                    'golden_board.m2_qualification_v2.render_complete_roadmap_v2',
                    return_value=complete),patch(
                    'golden_board.m2_qualification_v2.admit_qualification_v2'),patch.object(
                    coordinator,'validate_source_projection_v2'),patch.object(
                    coordinator,'admit_transition_v2',side_effect=ValueError('late failure')):
                with self.assertRaisesRegex(ValueError,'late failure'):
                    coordinator.publish_completion_v2(root,self.policy,b'pending',b'report',b'source')
            self.assertEqual((root/'docs/roadmap.md').read_bytes(),ready)
            self.assertEqual(list((root/'artifacts').iterdir()),[])
            with patch('golden_board.m2_gate8_reports_v2.render_candidate_ready_roadmap_v2',
                    return_value=ready),patch(
                    'golden_board.m2_qualification_v2.render_complete_roadmap_v2',
                    return_value=complete),patch(
                    'golden_board.m2_qualification_v2.admit_qualification_v2'),patch.object(
                    coordinator,'validate_source_projection_v2'),patch.object(
                    coordinator,'admit_transition_v2',return_value=('complete',b'pending')):
                coordinator.publish_completion_v2(root,self.policy,b'pending',b'report',b'source')
            self.assertEqual((root/'docs/roadmap.md').read_bytes(),complete)
            self.assertEqual(list((root/'artifacts').iterdir()),[])


if __name__=='__main__':unittest.main()
