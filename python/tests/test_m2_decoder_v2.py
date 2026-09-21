"""Recovery from observations; source-built values appear only in the oracle."""
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
import json
import os
import unittest

from golden_board import bootstrap, bootstrap_v2, curriculum, m2_policy, m2_codec
from golden_board import m2_decoder as old
from golden_board.m2_decoder_v2 import ObservationDecoderV2
from golden_board.m2_slice import compile_slice_v0
from golden_board.m2_slice_v1 import compile_slice_v1
from golden_board.m2_carrier_v2 import build_development_carrier

ROOT = Path(__file__).resolve().parents[2]


def serialized(units, order=None):
    order = sorted(units) if order is None else order
    return len(order).to_bytes(4,'big')+b''.join(
        i.to_bytes(4,'big')+len(units[i]).to_bytes(2,'big')+units[i] for i in order)


class RevisedFallbackAccounting(unittest.TestCase):
    def test_legacy_inventory_incomplete_copy_is_repeated_in_final_fallback(self):
        owners=tuple((ROOT/path).read_bytes() for path in ('spec/profile-policy-v2.toml',
            'spec/profile-limits-v2.toml','spec/damage-policy-v2.toml'))
        decoder=ObservationDecoderV2(*owners)
        envelope=bootstrap.encode_section_envelope(bootstrap.SectionEnvelope(1,1,0,128,1,(),b'x'*200))
        block=bootstrap.fragment_section(envelope,2,0)[0]
        self.assertEqual(bootstrap.decode_common_block(block,2).fragment_count,2)
        observation=serialized({i:m2_codec.eh72_encode_unit(block) for i in range(1,6)})
        result=decoder.decode(old.OBS_UNITS,observation)
        self.assertEqual(result.artifact_state,'failure')
        self.assertEqual(result.resource.section_attempts,0)
        side=json.loads(decoder.render_resources())
        assembly=next(row for row in side['adapter_rows'] if row['kernel']=='section-assembly')
        # Discovery, per-profile failed-inventory diagnostics, registry-wide
        # diagnostics all assemble these five incomplete witnesses separately.
        self.assertEqual(assembly,dict(kernel='section-assembly',calls=3,
            reference_input_units=3*5*191,peak_workspace_bytes=5*24))
        self.assertTrue(all(row.envelope is None for row in result.section_results))


class RevisedObservationDecoder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owner = tuple(ROOT.joinpath(p).read_bytes() for p in (
            'spec/profile-policy-v2.toml','spec/profile-limits-v2.toml','spec/damage-policy-v2.toml'))
        raws = tuple(ROOT.joinpath(p).read_bytes() for p in (
            'studies/m2/slice-v0.json','conformance/content-v0.json','conformance/chess-v0.json',
            'reports/game-set-v0.bin','spec/content-v0.md','spec/constants-v0.toml','spec/curriculum-v0.toml'))
        legacy = compile_slice_v0(*raws)
        cls.compiled = compile_slice_v1(ROOT.joinpath('studies/m2/slice-v1.json').read_bytes(),*raws)
        cls.image = build_development_carrier(cls.compiled,legacy,curriculum.load_blueprint(raws[-1]),
            m2_policy.load_profile_policy(ROOT.joinpath('spec/profile-policy-v0.toml').read_bytes()).capacity_policy)
        cls.decoder = ObservationDecoderV2(*cls.owner)
        side, bits = old._parse_bits(cls.image.carrier)
        cls.cells = old._Cells(bits,side,0,0)
        route = cls.decoder._parse_route(cls.cells,cls.image.capacity_plan.width,0)
        if route is None:
            raise AssertionError('new actual route was rejected')
        observations = cls.decoder._extract_units(cls.cells,route.profile,route.shell_width,route.mapping)
        cls.units = {row.unit_id:row.encoded for row in observations}
        cls.inventory = cls.decoder._recover_inventory(route.profile,observations)[0]
        cls.expected = cls.decoder._expected_units(route.profile,cls.inventory)

    def test_units_clean_reordered_and_resource_charge_are_exact(self):
        decoder = self.decoder
        clean = decoder.decode(old.OBS_UNITS,serialized(self.units))
        self.assertEqual(clean.artifact_state,'exact')
        self.assertEqual(clean.m2_required_stream,self.compiled.required_content_bytes)
        self.assertEqual(clean.m2_all_stream,self.compiled.content_bytes)
        reordered = decoder.decode(old.OBS_UNITS,serialized(self.units,sorted(self.units,reverse=True)))
        self.assertEqual(reordered,clean)
        projected = json.loads(decoder.render_result(old.OBS_UNITS,clean))
        self.assertEqual(projected['schema'],'golden-board.m2-damage-decoder-result/v2')
        with self.assertRaises(old.DecoderError):
            old.render_decoder_result(old.OBS_UNITS,clean,schema_version=1)

    def test_foreign_inventory_fallback_converges_after_full_source_generation(self):
        from golden_board.m2_damage_v2 import DamageCorpusV2
        from golden_board.m2_damage_oracle_v2 import DamageOracleV2
        from golden_board.m2_preflight_v2 import _semantic_convergence
        corpus=DamageCorpusV2(self.image,alternate_route_owner_raw=(ROOT/'spec/route-data-v0.json').read_bytes())
        oracle=DamageOracleV2(corpus)
        export=os.environ.get('GB_FOREIGN_INVENTORY_TEST_EXPORT')
        if export:Path(export).mkdir(mode=0o700)
        decoder=ObservationDecoderV2(*self.owner)
        for ordinal in (11,12,13,14,15,414):
            case=corpus.case('D7',ordinal)
            expected=oracle.evaluate(case)
            actual=decoder.decode(case.channel,case.observation)
            _semantic_convergence(expected,actual,corpus)
            self.assertEqual(expected.wrong_accepts,0)
            self.assertIsNone(actual.m2_required_stream)
            self.assertIsNone(actual.m2_all_stream)
            result=decoder.render_result(case.channel,actual);resources=decoder.render_resources()
            if export:
                (Path(export)/(case.case_id+'.result.json')).write_bytes(result)
                (Path(export)/(case.case_id+'.resources.json')).write_bytes(resources)

    def test_missing_probe_preserves_both_streams_but_degrades_artifact(self):
        removed = {row.unit_id for row in self.expected if row.section_type == 6}
        result = self.decoder.decode(old.OBS_UNITS,serialized({i:b for i,b in self.units.items() if i not in removed}))
        self.assertEqual(result.artifact_state,'degraded')
        self.assertEqual(result.m2_required_stream,self.compiled.required_content_bytes)
        self.assertEqual(result.m2_all_stream,self.compiled.content_bytes)
        self.decoder.render_result(old.OBS_UNITS,result)

    def test_missing_body_or_bootstrap_has_no_clean_fallback(self):
        for sid in (100,16,1):
            removed = {row.unit_id for row in self.expected if row.section_id == sid}
            result = self.decoder.decode(old.OBS_UNITS,serialized({i:b for i,b in self.units.items() if i not in removed}))
            with self.subTest(section=sid):
                self.assertIsNone(result.m2_all_stream)
                self.assertEqual(result.m2_required_stream,self.compiled.required_content_bytes if sid == 100 else None)
                self.assertEqual(result.artifact_state,'degraded' if sid == 100 else 'failure')
                self.decoder.render_result(old.OBS_UNITS,result)

    def test_failed_route_vm_charge_survives_cache_and_other_routes_recover(self):
        prefix = self.image.route_prefixes[0]
        offset = 64
        while prefix[offset+1] != 2:
            offset += 8+int.from_bytes(prefix[offset+4:offset+8],'big')
        last = offset+8+int.from_bytes(prefix[offset+4:offset+8],'big')-1
        side,width = self.image.capacity_plan.side,self.image.capacity_plan.width
        row,column = bootstrap.sector_cell(side,width,0,last*8+7)
        bit = row*side+column
        changed = bytearray(self.image.carrier)
        changed[4+bit//8] ^= 1 << (7-bit%8)
        decoder = ObservationDecoderV2(*self.owner)
        first = decoder.decode(old.OBS_BITS,bytes(changed))
        charged = decoder._rejected_route_steps
        self.assertGreater(charged,0)
        self.assertEqual(len(first.accepted_hypotheses),3)
        self.assertEqual(first.artifact_state,'exact')
        self.assertEqual(first.m2_required_stream,self.compiled.required_content_bytes)
        self.assertEqual(first.m2_all_stream,self.compiled.content_bytes)
        second = decoder.decode(old.OBS_BITS,bytes(changed))
        self.assertEqual(second,first)
        self.assertEqual(decoder._rejected_route_steps,charged)

    def replace_section_units(self, section_id, envelope):
        blocks = bootstrap.fragment_section(envelope,8,0)
        replaced = dict(self.units)
        for row in self.expected:
            if row.section_id == section_id:
                replaced[row.unit_id] = m2_codec.eh72_encode_unit(blocks[row.fragment_index])
        return replaced

    def test_fresh_transport_checks_do_not_hide_invalid_compressed_content(self):
        all_only = next(s.section_id for s in self.image.capacity_plan.sections
                        if s.section_type == 3 and s.version == 1 and s.section_id >= 100)
        for sid in (16,all_only):
            original = bootstrap.decode_section_envelope(self.envelopes()[sid])
            malformed = replace(original,payload=b'\x02'+original.payload[1:])
            units = self.replace_section_units(sid,bootstrap.encode_section_envelope(malformed))
            result = self.decoder.decode(old.OBS_UNITS,serialized(units))
            with self.subTest(section=sid):
                self.assertEqual(next(s for s in result.section_results if s.section_id == sid).state,'verified')
                self.assertIsNone(result.m2_all_stream)
                self.assertEqual(result.m2_required_stream,self.compiled.required_content_bytes if sid != 16 else None)
                self.assertEqual(result.artifact_state,'degraded' if sid != 16 else 'failure')

    def test_square_inventory_must_cover_its_observed_physical_population(self):
        decoder = ObservationDecoderV2(*self.owner)
        route = decoder._parse_route(self.cells,self.image.capacity_plan.width,0)
        # Remove one declared load fragment, keeping an otherwise valid exact
        # inventory payload and recomputing all outer/local checks.
        entries = tuple(replace(e,logical_payload_length=e.logical_payload_length-157)
                        if e.section_type == 6 else e for e in self.inventory.entries)
        inventory = bootstrap_v2.encode_inventory(replace(self.inventory,entries=entries))
        envelope = bootstrap.decode_section_envelope(self.envelopes()[1])
        units = self.replace_section_units(1,bootstrap.encode_section_envelope(replace(envelope,payload=inventory)))
        observations = old._parse_units(serialized(units),decoder.maximum_units)
        self.assertIsNotNone(decoder._recover_inventory_v7(decoder.profile_by_version[8],observations))
        decoder._current_package = decoder._observed_packages[route.packages[0]]
        self.assertIsNone(decoder._recover_inventory_v7(route.profile,observations))

    def envelopes(self):
        return {s.section_id:bootstrap.encode_section_envelope(bootstrap.SectionEnvelope(
            s.section_id,s.section_type,s.version,s.closure,1,s.dependencies,s.payload))
            for s in self.image.capacity_plan.sections}

    def test_shared_bodies_charge_once_and_full_cache_does_not_exhaust(self):
        decoder = ObservationDecoderV2(*self.owner)
        with patch.object(decoder,'_decode_body',wraps=decoder._decode_body) as decode:
            required,all_stream,steps,scratch = decoder._recover_content_tiers(
                decoder.profile_by_version[8],self.inventory,self.envelopes())
        self.assertEqual(required,self.compiled.required_content_bytes)
        self.assertEqual(all_stream,self.compiled.content_bytes)
        self.assertEqual(decode.call_count,78)
        self.assertEqual(sum(call.args[0] == 1 for call in decode.call_args_list),10)
        self.assertEqual(steps,10*decoder.policy.decompression_primitive_steps)
        self.assertEqual(scratch,decoder.policy.decompression_peak_scratch_bytes)
        route = decoder._parse_route(self.cells,self.image.capacity_plan.width,0)
        decoder._current_package = decoder._observed_packages[route.packages[0]]
        decoder._body_cache = {(b'',i):None for i in range(4096)}
        # Saturating an optional cache changes no availability. Force the
        # generic VM branch and an explicit program rejection, not cache failure.
        with patch('golden_board.m2_decoder_v2.body_program_refined',return_value=False), \
             patch('golden_board.m2_decoder_v2.recipe_wire_v1.evaluate_recipe_v1',
                   return_value=bootstrap.RecipeResult(3,())):
            required,all_stream,_,_ = decoder._recover_content_tiers(
                decoder.profile_by_version[8],self.inventory,self.envelopes())
        self.assertIsNone(required)
        self.assertIsNone(all_stream)

    def test_distinct_observed_programs_are_both_recovered_before_ambiguity(self):
        decoder = ObservationDecoderV2(*self.owner)
        route = decoder._parse_route(self.cells,self.image.capacity_plan.width,0)
        other = replace(route,sector_id=1,packages=(b'another-admitted-program',))
        # This isolates aggregation after route admission: distinct programs
        # sharing the geometry must not overwrite each other's recovery path.
        first = old.DecodeResult('exact',route.profile.profile_id,
            (old.SectionResult(1,'verified',b'A'),),(),True,
            m2_required_stream=b'A',m2_all_stream=b'A')
        second = replace(first,section_results=(old.SectionResult(1,'verified',b'B'),),
                         m2_required_stream=b'B',m2_all_stream=b'B')
        with patch.object(decoder,'_discover_routes',side_effect=[(route,other)]+[()]*15), \
             patch.object(decoder,'_extract_units',return_value=()), \
             patch.object(decoder,'_recover_route_sections',side_effect=(first,second)) as recover:
            result = decoder._decode_square(self.cells.side,b'')
        self.assertEqual(recover.call_count,2)
        self.assertEqual(result.artifact_state,'ambiguous')
        self.assertIsNone(result.m2_required_stream)

    @unittest.skipUnless(os.environ.get('GB_M2_DECODER_V2_MATRIX') == '1','explicit full carried202 matrix execution')
    def test_actual_square_uses_observed_program_then_matches_matrix_channel(self):
        decoder = self.decoder
        result = decoder.decode(old.OBS_BITS,self.image.carrier)
        self.assertEqual(result.artifact_state,'exact')
        self.assertEqual(result.m2_required_stream,self.compiled.required_content_bytes)
        self.assertEqual(result.m2_all_stream,self.compiled.content_bytes)
        self.assertEqual(len(result.accepted_hypotheses),4)
        side,bits = old._parse_bits(self.image.carrier)
        other = decoder.decode(old.OBS_MATRIX,side.to_bytes(2,'big')+bits)
        self.assertEqual(other,result)
        decoder.render_result(old.OBS_BITS,result)


if __name__ == '__main__':
    unittest.main()
