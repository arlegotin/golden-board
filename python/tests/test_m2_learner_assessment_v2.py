from pathlib import Path
import unittest

from golden_board import canonical_manifest as manifest
from golden_board.m2_learner_assessment_v2 import (
    build_learner_assessment_v2, validate_learner_assessment_v2,
)
from tools.m2.learner_compile import compile_pages
from tools.m2.learner_content import build_cases

ROOT = Path(__file__).resolve().parents[2]


class LearnerAssessmentV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw, cls.old = compile_pages(build_cases(ROOT))
        cls.sources = tuple((ROOT / path).read_bytes() for path in (
            'studies/m2/learner-assessment-v2.toml', 'conformance/chess-v0.json',
            'reports/game-set-v0.bin'))

    def test_all_existing_finals_are_rederived_and_owner_only(self):
        raw = build_learner_assessment_v2(self.raw, *self.sources)
        value = manifest.validate_canonical_manifest(raw)
        self.assertEqual(value['schema'], 'golden-board.m2-lesson-owner/v2')
        finals = [p for p in self.old['pages'] if p['phase'] == 'heldout']
        self.assertEqual(len(value['pages']), 12)
        for actual, old in zip(value['pages'], finals, strict=True):
            self.assertEqual({k: v for k, v in actual.items() if k != 'evidence'},
                             {k: v for k, v in old.items() if k != 'evidence'})
        self.assertEqual(value['pages'][10]['evidence']['occurrences'], 2)
        self.assertFalse(value['pages'][10]['evidence']['threefold_available'])
        self.assertTrue(all(o['legal'] for o in value['pages'][11]['evidence']['options']))
        validate_learner_assessment_v2(raw, self.raw, *self.sources)

    def test_recovered_bytes_source_intent_and_result_cannot_be_substituted(self):
        with self.assertRaises(ValueError):
            build_learner_assessment_v2(self.raw[:-1] + bytes([self.raw[-1] ^ 1]), *self.sources)
        for before, after in ((b'"b1c3", "b8c6"', b'"b1a3", "b8c6"'),
                              (b'page_ordinal = 53', b'page_ordinal = true'),
                              (b'reverse = true', b'reverse = 1')):
            altered = self.sources[0].replace(before, after, 1)
            self.assertNotEqual(altered, self.sources[0])
            with self.assertRaises(ValueError):
                build_learner_assessment_v2(self.raw, altered, *self.sources[1:])
        value = manifest.validate_canonical_manifest(build_learner_assessment_v2(self.raw, *self.sources))
        value['pages'][0]['correct'] = [2]
        with self.assertRaises(ValueError):
            validate_learner_assessment_v2(manifest.serialize_manifest(value), self.raw, *self.sources)

    def test_source_bounds_and_fixture_identity(self):
        with self.assertRaises(ValueError):
            build_learner_assessment_v2(self.raw, b' ' * 16385, *self.sources[1:])
        with self.assertRaises(ValueError):
            build_learner_assessment_v2(self.raw, self.sources[0], self.sources[1] + b' ', self.sources[2])
        with self.assertRaises(ValueError):
            build_learner_assessment_v2(self.raw, *self.sources[:2], self.sources[2][:-1])

    def test_existing_session_replay_scores_the_same_twelve_finals(self):
        from python.tests.test_m2_learner_session import LearnerSession
        from tools.m2.learner_session import review_session
        LearnerSession.setUpClass()
        owner = manifest.validate_canonical_manifest(build_learner_assessment_v2(self.raw, *self.sources))
        result = review_session(LearnerSession.session, self.raw, owner)
        self.assertTrue(result['complete'])
        self.assertEqual((result['matching_answers'], result['question_count']), (12, 12))


if __name__ == '__main__':
    unittest.main()
