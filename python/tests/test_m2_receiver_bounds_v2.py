"""Source-derived limits cannot be substituted by small measured samples."""
from copy import deepcopy
from pathlib import Path
import unittest

from golden_board import canonical_manifest

ROOT = Path(__file__).resolve().parents[2]


class ReceiverBounds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owners = tuple((ROOT/'spec'/name).read_bytes() for name in (
            'profile-policy-v2.toml', 'profile-limits-v2.toml',
            'damage-policy-v2.toml', 'resource-accounting-v2.md',
            'receiver-bounds-v2.md'))

    def api(self):
        from golden_board import m2_receiver_bounds_v2 as bounds
        return bounds

    def test_source_only_derivation_covers_each_dimension(self):
        from golden_board.m2_resources_v2 import ADAPTER_KERNELS
        raw = self.api().derive_receiver_bounds_v2(*self.owners)
        doc = canonical_manifest.validate_canonical_manifest(raw)
        self.assertEqual(doc['derivation']['A'], 16*16*4)
        self.assertEqual(doc['derivation']['J'], 64+7+1)
        self.assertEqual(doc['derivation']['E'], 18+4*4095+16384+8)
        self.assertEqual(doc['maximum_resource']['section_attempts'], 4096)
        self.assertGreater(doc['maximum_resource']['primitive_steps'], 268435456)
        self.assertGreater(doc['maximum_resource']['peak_scratch_bytes'], 16777216)
        self.assertEqual(tuple(r['kernel'] for r in doc['adapter_bounds']), ADAPTER_KERNELS)
        self.assertEqual(self.api().derive_receiver_bounds_v2(*self.owners), raw)
        for row in doc['adapter_bounds']:
            self.assertGreater(row['calls'], 0)
            self.assertGreater(row['reference_input_units'], 0)

    def measured(self):
        doc = canonical_manifest.validate_canonical_manifest(
            self.api().derive_receiver_bounds_v2(*self.owners))
        return dict(schema='golden-board.m2-resource-limits/v2',
            corpus_sha256='1'*64, case_count=1, case_resources_sha256='2'*64,
            source_owners={p:h for p,h in doc['source_owners'].items()
                           if p != 'spec/receiver-bounds-v2.md'},
            maximum_resource=doc['maximum_resource'], adapter_maxima=doc['adapter_bounds'])

    def test_rejected_inventory_payload_charge_is_covered(self):
        from golden_board.m2_decoder_v2 import ObservationDecoderV2
        decoder = ObservationDecoderV2(*self.owners[:3])
        # A valid generic section can carry this before inventory rejection.
        payload = bytes(32790-22)
        with self.assertRaises(ValueError):
            decoder._decode_inventory_payload(decoder.profiles[0], payload)
        actual = dict((row[0],row[1:]) for row in decoder._meter.adapter_rows)['inventory']
        bounds = self.measured()['adapter_maxima']
        maximum = next(row for row in bounds if row['kernel'] == 'inventory')
        self.assertLessEqual(actual[2], maximum['peak_workspace_bytes'])

    def test_admission_checks_every_counter_and_preserves_subset_scope(self):
        value = self.measured()
        encode = canonical_manifest.serialize_manifest
        # This API checks resource bounds only, never complete-corpus coverage.
        self.api().validate_measured_bounds_v2(encode(value), *self.owners)
        for key in value['maximum_resource']:
            bad = deepcopy(value)
            bad['maximum_resource'][key] += 1
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'bound'):
                self.api().validate_measured_bounds_v2(encode(bad), *self.owners)
        for ordinal,row in enumerate(value['adapter_maxima']):
            for key in ('calls','reference_input_units','peak_workspace_bytes'):
                bad = deepcopy(value)
                bad['adapter_maxima'][ordinal][key] += 1
                with self.subTest(kernel=row['kernel'],key=key), self.assertRaisesRegex(ValueError, 'bound'):
                    self.api().validate_measured_bounds_v2(encode(bad), *self.owners)

    def test_wrong_owners_incomplete_rows_and_boolean_counters_reject(self):
        for index in range(len(self.owners)):
            bad = list(self.owners)
            bad[index] += b'\n'
            with self.subTest(owner=index), self.assertRaises(ValueError):
                self.api().derive_receiver_bounds_v2(*bad)
        original = self.measured()
        mutations = []
        bad = deepcopy(original); bad['maximum_resource']['section_attempts'] = True; mutations.append(bad)
        bad = deepcopy(original); bad['adapter_maxima'].pop(); mutations.append(bad)
        bad = deepcopy(original); bad['adapter_maxima'].reverse(); mutations.append(bad)
        bad = deepcopy(original); bad['adapter_maxima'][0]['extra'] = 0; mutations.append(bad)
        bad = deepcopy(original); bad['source_owners']['spec/resource-accounting-v2.md'] = '0'*64; mutations.append(bad)
        bad = deepcopy(original); bad['case_count'] = 0; mutations.append(bad)
        for bad in mutations:
            with self.subTest(bad=bad.keys()), self.assertRaises(ValueError):
                self.api().validate_measured_bounds_v2(canonical_manifest.serialize_manifest(bad), *self.owners)
