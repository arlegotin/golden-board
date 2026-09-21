from hashlib import sha256
from pathlib import Path
import unittest

from golden_board import bootstrap, m2_codec, m2_policy
from golden_board import m2_policy_v2 as v2
from golden_board.m2_teaching_recipe_v2 import build_teaching_recipe_package
from golden_board.recipe_wire_v1 import decode_recipe_package_v1

ROOT = Path(__file__).resolve().parents[2]


class DevelopmentOwners(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raws = tuple((ROOT / 'spec' / name).read_bytes() for name in (
            'profile-policy-v2.toml', 'profile-limits-v2.toml', 'damage-policy-v2.toml'))

    def test_development_projection_has_bounded_explicit_profile8_admission(self):
        policy = v2.load_decoder_policy_v2(*self.raws)
        self.assertEqual(policy.result_schema_version, 2)
        self.assertEqual(policy.establishing_profile_versions, frozenset((8,)))
        self.assertEqual(tuple(p.profile_version for p in policy.registry_profiles), (8,2,3,4,5,6,7))
        self.assertEqual(policy.maximum_units, 2389)
        self.assertEqual(policy.policy_ceilings['dependency_count_per_section'], bootstrap.DEPENDENCY_MAX)
        self.assertEqual(v2.load_profile_policy_v2(self.raws[0]).document['storage']['dependency_count_max'], bootstrap.DEPENDENCY_MAX)
        active = policy.candidate_profile(1925)
        self.assertEqual((active.protected_units, active.encoded_transport_bytes), (1925,415800))
        self.assertEqual((active.profile_version, active.inventory_version), (8,2))
        self.assertEqual(active.physical_replica_counts, (1,2,5))
        profiles = policy.profiles_for_units(1925)
        self.assertEqual(profiles[0], active)
        self.assertEqual(profiles[1:6], m2_codec.candidate_profiles()[1:])
        self.assertEqual(profiles[-1], m2_codec.r3_candidate_profile(
            protected_units=1841, encoded_transport_bytes=397656))
        for bad in (0,2390,True,1.0,None):
            with self.subTest(bad=bad), self.assertRaises(v2.PolicyV2Error):
                policy.candidate_profile(bad)

    def test_declared_resources_are_actual_program_resources_not_damage_results(self):
        policy = v2.load_decoder_policy_v2(*self.raws)
        raw = build_teaching_recipe_package()
        package = decode_recipe_package_v1(raw, 8).logical
        self.assertEqual(policy.obs_units_resource_profiles[0][2], sha256(raw).hexdigest())
        by_id = {r.recipe_id:r for r in package.recipes}
        self.assertEqual(policy.obs_units_resource_profiles[0][3:],
                         (by_id[30].primitive_steps, by_id[30].peak_live_scratch_bytes))
        self.assertEqual((policy.repetition_primitive_steps, policy.repetition_peak_scratch_bytes),
                         (by_id[113].primitive_steps, by_id[113].peak_live_scratch_bytes))
        self.assertEqual((policy.decompression_primitive_steps, policy.decompression_peak_scratch_bytes),
                         (by_id[202].primitive_steps, by_id[202].peak_live_scratch_bytes))
        legacy = m2_policy.load_r3_decoder_policy(
            (ROOT/'spec/profile-policy-v1.toml').read_bytes(),
            (ROOT/'spec/profile-limits-v1.toml').read_bytes(),
            (ROOT/'spec/damage-policy-v1.toml').read_bytes())
        self.assertEqual(policy.obs_units_resource_profiles[1:6], legacy.obs_units_resource_profiles[1:])
        self.assertEqual(policy.obs_units_resource_profiles[-1], legacy.obs_units_resource_profiles[0])

    def test_no_draft_or_forged_measurement_can_establish_production(self):
        with self.assertRaisesRegex(v2.PolicyV2Error, 'promotion'):
            v2.load_decoder_policy_v2(*self.raws, require_promoted=True)
        with self.assertRaises(v2.PolicyV2Error):
            v2.load_decoder_policy_v2(*self.raws, require_promoted=1)
        limits = self.raws[1]
        for suffix in (b'\n[selected_manifestation]\nside=2048\n',
                       b'\n[generated]\nphysical_units=0\n',
                       b'\n[results]\ngate6="pass"\n'):
            with self.subTest(suffix=suffix), self.assertRaises(v2.PolicyV2Error):
                v2.load_profile_limits_v2(limits+suffix)

    def test_closed_shapes_types_bounds_and_hash_bindings_reject(self):
        loaders = (v2.load_profile_policy_v2,v2.load_profile_limits_v2,v2.load_damage_policy_v2)
        for loader,raw in zip(loaders,self.raws):
            for bad in (raw+b'\n[unknown]\nx=1\n', raw+b'\nschema="duplicate"\n',
                        b'', b'x' * 65537, bytearray(raw), raw.replace(b'"development"',b'"promoted"',1)):
                with self.subTest(loader=loader.__name__, bad=type(bad)), self.assertRaises(v2.PolicyV2Error):
                    loader(bad)
        for old,new in ((b'profile_version = 8',b'profile_version = true'),
                        (b'side_max = 2048',b'side_max = 2560'),
                        (b'active_versions = [8]',b'active_versions = [7, 8]')):
            self.assertIn(old,self.raws[0])
            with self.assertRaises(v2.PolicyV2Error):
                v2.load_profile_policy_v2(self.raws[0].replace(old,new,1))
        for slot in (0,2):
            changed=list(self.raws);changed[slot]+=b'\n# changed source identity\n'
            with self.assertRaisesRegex(v2.PolicyV2Error,'binding'):
                v2.load_decoder_policy_v2(*changed)
        # Exact integer checking must not treat a recipe's true as step count1.
        with self.assertRaises(v2.PolicyV2Error):
            v2.load_damage_policy_v2(self.raws[2].replace(b'primitive_steps = 24',b'primitive_steps = true',1))

    def test_old_public_admission_remains_closed_and_unchanged(self):
        with self.assertRaises(m2_policy.PolicyError):
            m2_policy.load_profile_policy(self.raws[0])
        with self.assertRaises(m2_policy.PolicyError):
            m2_policy.load_r3_decoder_policy(*self.raws)
        with self.assertRaises(bootstrap.BootstrapReject):
            bootstrap.decode_recipe_package(build_teaching_recipe_package(),8)
        policy = v2.load_decoder_policy_v2(*self.raws)
        with self.assertRaises(m2_codec.CodecError):
            m2_codec.aggregate_replica_group(policy.candidate_profile(1925),(None,))
        with self.assertRaises(TypeError):
            v2.load_profile_limits_v2(self.raws[1]).document['policy_ceiling']['side'] = 4096


if __name__ == '__main__':
    unittest.main()
