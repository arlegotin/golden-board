"""Production dispatch uses carried complete programs, including rejection."""
from pathlib import Path
import unittest

from golden_board import bootstrap, m2_codec, recipe_wire_v2
from golden_board import m2_decoder as old
from golden_board.m2_decoder_v2 import ObservationDecoderV2
from golden_board.m2_teaching_recipe_v2 import build_teaching_recipe_package

ROOT = Path(__file__).resolve().parents[2]


class OperationalRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owners = tuple((ROOT/path).read_bytes() for path in (
            'spec/profile-policy-v2.toml', 'spec/profile-limits-v2.toml',
            'spec/damage-policy-v2.toml'))
        cls.package = recipe_wire_v2.decode_recipe_package_v2(build_teaching_recipe_package(), 8)
        cls.programs = {r.recipe_id: r for r in cls.package.logical.recipes}

    def setUp(self):
        self.decoder = ObservationDecoderV2(*self.owners)
        self.decoder._current_package = self.package
        self.profile = self.decoder.policy.candidate_profile(100)

    @staticmethod
    def block(sid=400, payload=b'x'):
        envelope = bootstrap.encode_section_envelope(
            bootstrap.SectionEnvelope(sid, 4, 0, 128, 1, (), payload))
        return bootstrap.fragment_section(envelope, 8, 0)[0]

    @staticmethod
    def key(block):
        return block[:2] + block[4:14] + block[16:20] + block[22:26]

    @staticmethod
    def lane(unit, block, erased=()):
        encoded = bytearray(m2_codec.eh72_encode_unit(block))
        for bit in erased:
            encoded[bit//8] &= ~(128 >> (bit % 8))
        return old._ObservedUnit(unit, bytes(encoded), tuple(erased))

    def call(self, first, lanes, key=None, bootstrap_first=False):
        return self.decoder._aggregate_v7_group(self.profile, lanes,
            physical_first=first, expected_key=key, bootstrap_first=bootstrap_first)

    def test_complete_program_recovers_raw_union_and_charges_once(self):
        block = self.block()
        # All five individual headers fail bounded EH; disjoint raw erasures
        # leave every REP bit recoverable. Membership comes from physical IDs.
        lanes = tuple(self.lane(6+i, block, range(i*5, i*5+5)) for i in range(5))
        result = self.call(6, lanes, self.key(block))
        self.assertEqual(result.lane_states, (1,)*5)
        self.assertEqual((result.group_state, result.chosen_block), (3, block))
        self.assertEqual(self.decoder._meter.usage.primitive_steps, self.programs[120].primitive_steps)
        self.assertEqual(self.call(6, lanes, self.key(block)), result)
        self.assertEqual(self.decoder._meter.usage.primitive_steps, self.programs[120].primitive_steps)

    def test_foreign_unique_rejects_but_keeps_local_diagnostics(self):
        block = self.block(401)
        lanes = (self.lane(6, block), None)
        result = self.call(6, lanes, self.key(self.block(400)))
        self.assertEqual(result.group_state, 1)
        self.assertEqual(result.lane_states, (2, 0))
        self.assertEqual(result.lane_blocks[0], block)
        self.assertEqual(self.decoder._meter.usage.primitive_steps, self.programs[120].primitive_steps)

    def test_missing_physical_groups_do_not_alias(self):
        key = self.key(self.block())
        for first in (6, 8):
            self.assertEqual(self.call(first, (None, None), key).group_state, 0)
        self.assertEqual(self.decoder._meter.usage.primitive_steps, 2*self.programs[120].primitive_steps)

    def test_bootstrap_uses_actual_geometry_and_preserves_rejected_lane(self):
        envelope = bootstrap.encode_section_envelope(
            bootstrap.SectionEnvelope(1, 1, 2, 128, 1, (), b'x'*400))
        block = bootstrap.fragment_section(envelope, 8, 0)[0]
        lanes = tuple(self.lane(1+i, block) for i in range(5))
        self.profile = self.decoder.policy.candidate_profile(10)
        result = self.call(1, lanes, bootstrap_first=True)
        self.assertEqual(result.group_state, 1)  # Three fragments require15 units.
        self.assertEqual(result.lane_blocks[0], block)
        self.assertEqual(self.decoder._meter.usage.primitive_steps, self.programs[127].primitive_steps)


if __name__ == '__main__':
    unittest.main()
