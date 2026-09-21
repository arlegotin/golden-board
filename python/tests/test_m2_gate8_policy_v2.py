"""Revised Gate8 contracts are closed without executing or claiming gates."""
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from pathlib import Path
import unittest

from golden_board.m2_gate8_policy_v2 import (
    GATE8_POLICY_V2_SHA256, Gate8PolicyV2Error, load_gate8_policy_v2,
    result_file_paths_v2, validate_result_file_rows_v2,
)

ROOT = Path(__file__).resolve().parents[2]


class Gate8PolicyV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (ROOT / 'spec/gate8-policy-v2.toml').read_bytes()
        cls.policy = load_gate8_policy_v2(cls.raw)

    def damage_paths(self):
        return tuple(sorted(('resource-limits.json', 'damage/manifest.json',
            'damage/boundary-kats.json', *(path for family in
            ('D0', 'D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7', 'B0')
            for path in (f'damage/{family}/manifest.json', f'damage/{family}/000000.json')))))

    def test_exact_owner_is_deeply_immutable_and_does_not_admit_production(self):
        self.assertEqual(sha256(self.raw).hexdigest(), GATE8_POLICY_V2_SHA256)
        self.assertFalse(self.policy.document['outcome_values_present'])
        self.assertEqual(self.policy.document['status'], 'source-contract; no-production-result')
        with self.assertRaises(TypeError):
            self.policy.document['bounds']['carrier_bits'] = 1
        with self.assertRaises(FrozenInstanceError):
            self.policy.sha256 = '0' * 64
        forged = replace(self.policy, document={})
        self.assertEqual(result_file_paths_v2(forged, self.damage_paths()),
                         result_file_paths_v2(self.policy, self.damage_paths()))
        with self.assertRaises(Gate8PolicyV2Error):
            result_file_paths_v2(replace(self.policy, _raw=b'forged'), self.damage_paths())

    def test_changed_foreign_oversized_or_mutable_owner_rejects(self):
        for raw in (b'', bytearray(self.raw), memoryview(self.raw), self.raw + b'\n',
                    self.raw.replace(b'policy_version = 2', b'policy_version = true'),
                    self.raw + b'unknown = 1\n', b'x' * 65537,
                    (ROOT / 'spec/gate8-policy-v0.toml').read_bytes()):
            with self.subTest(kind=type(raw)), self.assertRaises(Gate8PolicyV2Error):
                load_gate8_policy_v2(raw)

    def test_result_inventory_uses_the_complete_dynamic_damage_closure(self):
        paths = result_file_paths_v2(self.policy, self.damage_paths())
        self.assertEqual(paths, tuple(sorted((*self.policy.document['candidate_files']['fixed'],
                                             *self.damage_paths()))))
        self.assertIn('preflight-resource-limits.json', paths)
        self.assertIn('bundle-preimages.json', paths)
        self.assertIn('resource-limits.json', paths)
        self.assertIn('damage/B0/000000.json', paths)
        more = tuple(sorted((*self.damage_paths(), 'damage/D7/000001.json')))
        self.assertIn('damage/D7/000001.json', result_file_paths_v2(self.policy, more))

    def test_partial_extra_unsafe_reordered_and_noncontiguous_paths_reject(self):
        good = self.damage_paths()
        wrong = [good[:-1], good[::-1], (*good, good[0]),
                 tuple(sorted((*good, 'damage/D8/000000.json'))),
                 tuple(sorted((*good, 'damage/D7/000002.json'))),
                 tuple(sorted((*good, 'damage/D7/../answer.json'))),
                 tuple(p for p in good if p != 'damage/B0/000000.json'),
                 tuple(sorted((*good, 'carrier.bin')))]
        for paths in wrong:
            with self.subTest(paths=paths[-2:]), self.assertRaises(Gate8PolicyV2Error):
                result_file_paths_v2(self.policy, paths)

    def test_receipt_file_rows_require_exact_paths_modes_types_hashes_and_bounds(self):
        paths = result_file_paths_v2(self.policy, self.damage_paths())
        good = tuple(dict(path=p, mode='100644', bytes=1, sha256='1' * 64) for p in paths)
        admitted = validate_result_file_rows_v2(self.policy, good, self.damage_paths())
        self.assertEqual(tuple(row.path for row in admitted), paths)
        self.assertEqual(len(admitted), len(good))
        for change in ({'bytes': True}, {'bytes': 0}, {'bytes': 1048577},
                       {'sha256': 'A' * 64}, {'mode': '100755'}, {'extra': 0}):
            mutated = (dict(good[0], **change), *good[1:])
            with self.subTest(change=change), self.assertRaises(Gate8PolicyV2Error):
                validate_result_file_rows_v2(self.policy, mutated, self.damage_paths())
        for rows in (good[:-1], good[::-1], (*good, good[-1])):
            with self.assertRaises(Gate8PolicyV2Error):
                validate_result_file_rows_v2(self.policy, rows, self.damage_paths())

    def test_physical_and_aggregate_inventory_bounds_cannot_be_hidden_by_hashes(self):
        paths = result_file_paths_v2(self.policy, self.damage_paths())
        for path, maximum in (('carrier.bin', 524292), ('route-0.bin', 32768),
                              ('damage/D7/000000.json', 524288)):
            rows = tuple(dict(path=p, mode='100644', bytes=maximum + 1 if p == path else 1,
                              sha256='1' * 64) for p in paths)
            with self.subTest(path=path), self.assertRaises(Gate8PolicyV2Error):
                validate_result_file_rows_v2(self.policy, rows, self.damage_paths())
        damage = tuple(sorted((*self.damage_paths(),
            *(f'damage/D7/{i:06d}.json' for i in range(1, 1200)))))
        paths = result_file_paths_v2(self.policy, damage)
        rows = tuple(dict(path=p, mode='100644', bytes=524288 if p.startswith('damage/D7/0') else 1,
                          sha256='1' * 64) for p in paths)
        with self.assertRaisesRegex(Gate8PolicyV2Error, 'file-total'):
            validate_result_file_rows_v2(self.policy, rows, damage)

    def test_preflight_and_complete_measurements_are_distinct_and_gates_stay_ordered(self):
        p = self.policy.document
        self.assertEqual(p['gates']['order'], tuple(range(1, 9)))
        self.assertIn('preflight-resource-limits.json', p['gates']['gate4'])
        self.assertNotIn('resource-limits.json', p['gates']['gate4'])
        self.assertIn('resource-limits.json', p['gates']['gate6'])
        self.assertEqual(p['bounds']['carrier_bits'], 2048 ** 2)
        self.assertEqual(p['producer_receipt']['producer_order'],
                         ('native-python', 'native-rust', 'linux-python', 'linux-rust'))
        self.assertEqual(len(p['metrics']['keys']), 23)
        self.assertNotIn('robustness_ppm', p['metrics']['keys'])

    def test_bundle_roles_release_exactly_once_without_initial_answers(self):
        p = self.policy.document
        for name in ('technical_bundle', 'learner_bundle'):
            bundle = p[name]
            self.assertEqual(len(bundle['participant_roles']), len(bundle['participant_paths']))
            self.assertEqual(sum(bundle['release_counts']), len(bundle['participant_roles']))
            self.assertEqual(len(bundle['owner_roles']), len(bundle['owner_paths']))
            self.assertEqual(len(set(bundle['participant_roles'] + bundle['owner_roles'])),
                             len(bundle['participant_roles']) + len(bundle['owner_roles']))
        technical = p['technical_bundle']
        self.assertEqual(technical['participant_roles'][:technical['release_counts'][0]],
                         ('clean-instructions', 'opening', 'allowed-tools', 'storage', 'artifact'))
        self.assertIn('optional-export-help', technical['owner_roles'])
        self.assertNotIn('optional-export-help', technical['participant_roles'])
        self.assertEqual(p['report']['schema'], 'm2-feasibility-v2')
        self.assertEqual(p['authority']['report_path'], 'reports/m2-feasibility-v2.json')
        self.assertEqual(p['bundle_preimages']['bundle_order'], ('technical-v2', 'learner-v2'))


if __name__ == '__main__':
    unittest.main()
