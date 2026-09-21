"""Preflight derives its evidence before any accidental damage case runs."""
from pathlib import Path
import os
import unittest
from unittest.mock import patch

from golden_board import canonical_manifest as manifest
from golden_board import m2_preflight_v2 as preflight
from golden_board.m2_damage_v2 import DamageCorpusV2

ROOT=Path(__file__).resolve().parents[2]


class PreflightV2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs={path:(ROOT/path).read_bytes() for path in preflight.SOURCE_PATHS}
        with patch.object(DamageCorpusV2,'case',side_effect=AssertionError('accidental damage before preflight')):
            cls.result=preflight.build_preflight_v2(cls.inputs)
        cls.files=dict(cls.result.files)

    def test_actual_preflight_is_closed_and_checks_the_complete_boundary(self):
        self.assertEqual(len(self.files),22)
        known=manifest.validate_canonical_manifest(self.files['known-answer-manifest.json'])
        self.assertEqual(known['summary'],dict(route_count=4,example_count=128,result='pass'))
        self.assertTrue(all(row['success'] for row in known['example_rows']))
        self.assertTrue(any(row['status']!=0 for row in known['example_rows']))
        grammar=manifest.validate_canonical_manifest(self.files['grammar-state-manifest.json'])
        self.assertEqual(grammar['summary'],dict(boundary_case_count=21,boundary_kat_count=4,result='pass'))
        self.assertEqual([row['case_id'] for row in grammar['boundary_rows']],
                         [f'B0-{i:06d}' for i in range(21)])
        limits=manifest.validate_canonical_manifest(self.files['preflight-resource-limits.json'])
        self.assertEqual(limits['case_count'],22)
        self.assertEqual(self.files['m2-required.content-v0.bin'],self.result.recovered.required_stream)
        self.assertEqual(self.files['m2-all.content-v0.bin'],self.result.recovered.all_stream)
        self.assertFalse(any(path.startswith('damage/') for path in self.files))
        if export:=os.environ.get('GB_PREFLIGHT_V2_EXPORT'):
            output=Path(export);output.mkdir(mode=0o700)
            for name,raw in self.files.items():(output/name).write_bytes(raw)

    def test_foreign_or_missing_source_cannot_enter_a_builder(self):
        for changes in ({'saved-result.json':b'{}\n'}, {'spec/receiver-bounds-v2.md':bytearray(b'x')}):
            inputs=dict(self.inputs);inputs.update(changes)
            with (patch.object(preflight,'compile_slice_v1',side_effect=AssertionError('builder reached')),
                  self.assertRaises(ValueError)):
                preflight.build_preflight_v2(inputs)
        inputs=dict(self.inputs);del inputs['spec/profile-policy-v2.toml']
        with self.assertRaises(ValueError):preflight.build_preflight_v2(inputs)


if __name__=='__main__':unittest.main()
