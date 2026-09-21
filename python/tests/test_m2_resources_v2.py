"""Exact per-observation logical charges, independent of execution caches."""
import unittest

from golden_board import bootstrap
from golden_board.m2_decoder import DecoderError, ResourceUsage
from golden_board.m2_resources_v2 import ResourceMeterV2


class ResourceMeterTests(unittest.TestCase):
    def test_reference_owner_identity_is_exact(self):
        from pathlib import Path
        from hashlib import sha256
        from golden_board.m2_resources_v2 import RESOURCE_OWNER_SHA256
        owner = Path(__file__).resolve().parents[2]/'spec/resource-accounting-v2.md'
        self.assertEqual(sha256(owner.read_bytes()).hexdigest(),RESOURCE_OWNER_SHA256)

    def test_checked_charge_preserves_last_complete_event(self):
        meter = ResourceMeterV2()
        meter.invoke((1 << 64)-2, 17)
        with self.assertRaisesRegex(DecoderError,'resource-limit'):
            meter.invoke(2,99)
        self.assertEqual(meter.usage,ResourceUsage(0,(1 << 64)-2,17))
        for value in (True,-1,1 << 64):
            with self.subTest(value=value), self.assertRaisesRegex(DecoderError,'resource-limit'):
                meter.invoke(value,0)

    def test_attempts_are_global_byte_deduplicated_and_eligible(self):
        meter = ResourceMeterV2()
        raw = bootstrap.encode_section_envelope(bootstrap.SectionEnvelope(1,1,2,128,1,(),b'x'))
        meter.section(raw)
        meter.section(raw)
        meter.section(raw[:-1])
        self.assertEqual(meter.usage.section_attempts,1)
        malformed_check = raw[:-4]+bytes((raw[-4]^1,))+raw[-3:]
        meter.section(malformed_check)
        self.assertEqual(meter.usage.section_attempts,2)

    def test_exact_limit_rejects_before_next_check(self):
        meter = ResourceMeterV2()
        for ordinal in range(4096):
            raw = bootstrap.encode_section_envelope(bootstrap.SectionEnvelope(ordinal+1,1,2,128,1,(),b'x'))
            meter.section(raw)
        meter.invoke(53,7)
        with self.assertRaisesRegex(DecoderError,'resource-limit'):
            meter.section(bootstrap.encode_section_envelope(bootstrap.SectionEnvelope(4097,1,2,128,1,(),b'x')))
        self.assertEqual(meter.usage,ResourceUsage(4096,53,4096*(len(raw)+8)+len(raw)))

    def test_adapter_rows_are_closed_checked_and_not_vm_steps(self):
        meter = ResourceMeterV2()
        meter.adapter('observation',3,8)
        meter.adapter('observation',5,13)
        self.assertEqual(meter.adapter_rows,(("observation",2,8,13),))
        self.assertEqual(meter.usage.primitive_steps,0)
        with self.assertRaisesRegex(DecoderError,'resource-limit'):
            meter.adapter('unowned-kernel',1,0)
        self.assertEqual(meter.adapter_rows,(("observation",2,8,13),))


class DecoderResourceBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pathlib import Path
        root = Path(__file__).resolve().parents[2]
        cls.owners = tuple(root.joinpath('spec',name).read_bytes() for name in (
            'profile-policy-v2.toml','profile-limits-v2.toml','damage-policy-v2.toml'))

    def decoder(self):
        from golden_board.m2_decoder_v2 import ObservationDecoderV2
        return ObservationDecoderV2(*self.owners)

    def test_global_failure_keeps_completed_lane_cost_and_clears_every_output(self):
        from unittest.mock import patch
        from golden_board import m2_decoder as old
        decoder = self.decoder()
        raw = b'\0\0\0\1\0\0\0\1\0\xd8'+bytes(216)
        with patch.object(decoder,'_decode_unit',side_effect=DecoderError('resource-limit')):
            result = decoder.decode(old.OBS_UNITS,raw)
        self.assertEqual(result.artifact_state,'resource-limit')
        self.assertEqual(result.resource.primitive_steps,24*80435)
        self.assertFalse(result.inventory_available)
        self.assertEqual(result.section_results,())
        self.assertEqual(result.fragment_diagnostics,())
        self.assertEqual(result.accepted_hypotheses,())
        self.assertIsNone(result.profile_id)
        self.assertIsNone(result.m2_required_stream)
        self.assertIsNone(result.m2_all_stream)
        decoder.render_result(old.OBS_UNITS,result)

    def test_count_cap_and_malformed_frame_are_distinct(self):
        from golden_board import m2_decoder as old
        decoder = self.decoder()
        self.assertEqual(decoder.decode(old.OBS_UNITS,(2390).to_bytes(4,'big')).artifact_state,'resource-limit')
        self.assertEqual(decoder.decode(old.OBS_UNITS,b'\0\0\0\1').artifact_state,'failure')

    def test_legacy_bad_calibration_never_reaches_prefix_or_frame_parser(self):
        from golden_board import m2_decoder as old
        decoder = self.decoder()
        self.assertIsNone(decoder._parse_route(old._Cells(bytes(128*128),128,0,0),8,0))
        self.assertEqual(decoder._meter.adapter_rows,(('shell-read',1,512,64),))

    def test_inventory_charge_occurs_at_payload_parse_not_section_assembly(self):
        decoder = self.decoder()
        envelope = bootstrap.encode_section_envelope(bootstrap.SectionEnvelope(1,1,1,128,1,(),b'x'))
        decoder._assemble_semantic_copy(bootstrap.fragment_section(envelope,7,0),7)
        self.assertNotIn('inventory',dict((r[0],r[1:]) for r in decoder._meter.adapter_rows))
        with self.assertRaises(bootstrap.BootstrapReject):
            decoder._decode_inventory_payload(decoder.profile_by_version[7],b'x')
        self.assertIn(('inventory',1,1,16),decoder._meter.adapter_rows)

    def test_cache_history_and_saturation_do_not_change_result(self):
        from golden_board import m2_decoder as old
        decoder = self.decoder()
        raw = b'\0\0\0\1\0\0\0\x09\0\x01\0'
        first = decoder.decode(old.OBS_UNITS,raw)
        decoder._unit_cache['unrelated previous request'] = None
        self.assertEqual(decoder.decode(old.OBS_UNITS,raw),first)
        cache = {1:'first'}
        decoder._cache_store(cache,2,'second',1)
        self.assertEqual(cache,{1:'first'})

    def test_logical_render_is_once_and_external_projection_is_pure(self):
        from golden_board import m2_decoder as old
        decoder = self.decoder()
        result = decoder.decode(old.OBS_UNITS,b'\0\0\0\1')
        rows = decoder._meter.adapter_rows
        wire = decoder.render_result(old.OBS_UNITS,result)
        self.assertEqual(decoder.render_result(old.OBS_UNITS,result),wire)
        self.assertEqual(decoder._meter.adapter_rows,rows)
        rendered = next(row for row in rows if row[0] == 'result-render')
        self.assertEqual(rendered,('result-render',1,len(wire)+len(b'{"rows":[]}\n'),1048576+256))
        self.assertGreaterEqual(result.resource.peak_scratch_bytes,1048576+256)

    def test_output_exhaustion_keeps_prior_charge_and_returns_closed_result(self):
        from golden_board import m2_decoder as old
        decoder = self.decoder()
        decoder._meter.invoke(19,9)
        fragments = tuple(old.FragmentDiagnostic(i+1,'',
            0,65535,65535,'corrupt',None) for i in range(10000))
        result = old.DecodeResult('failure',None,(),(),False,fragments)
        final = decoder._finish_result(old.OBS_UNITS,result)
        self.assertEqual(final.artifact_state,'resource-limit')
        self.assertEqual(final.resource.primitive_steps,19)
        self.assertEqual(final.fragment_diagnostics,())
        self.assertLess(len(decoder.render_result(old.OBS_UNITS,final)),1048576)

    def test_resource_sidecar_is_bound_to_result_and_complete_kernel_inventory(self):
        from hashlib import sha256
        from golden_board import m2_decoder as old,canonical_manifest
        from golden_board.m2_resources_v2 import ADAPTER_KERNELS
        decoder = self.decoder()
        raw = b'\0\0\0\1'
        result = decoder.decode(old.OBS_UNITS,raw)
        ledger = canonical_manifest.validate_canonical_manifest(decoder.render_resources())
        self.assertEqual(ledger['observation_sha256'],sha256(raw).hexdigest())
        self.assertEqual(ledger['result_sha256'],sha256(decoder.render_result(old.OBS_UNITS,result)).hexdigest())
        self.assertEqual(tuple(row['kernel'] for row in ledger['adapter_rows']),ADAPTER_KERNELS)
        self.assertEqual(ledger['resource']['primitive_steps'],0)
        self.assertEqual(decoder.render_resources(),decoder.render_resources())

    def test_limits_require_exact_owned_case_order_and_all_rows(self):
        from golden_board import m2_decoder as old,canonical_manifest
        from golden_board.m2_resources_v2 import build_resource_limits_v2
        decoder = self.decoder()
        decoder.decode(old.OBS_UNITS,b'\0\0\0\1')
        row = decoder.render_resources()
        result = build_resource_limits_v2('1'*64,('D0-000000','D0-000001'),
            (('D0-000000',row),('D0-000001',row)))
        value = canonical_manifest.validate_canonical_manifest(result)
        self.assertEqual(value['case_count'],2)
        self.assertEqual(value['maximum_resource']['primitive_steps'],0)
        for rows in ((('D0-000001',row),('D0-000000',row)),(('D0-000000',row),),
                     (('D0-000000',row),('D0-000001',row),None)):
            with self.assertRaises(ValueError):
                build_resource_limits_v2('1'*64,('D0-000000','D0-000001'),rows)

class ContentWorkspaceTests(unittest.TestCase):
    def test_short_content_metadata_does_not_claim_resource_exhaustion(self):
        from golden_board.m2_resources_v2 import content_shape
        from golden_board import content
        for size in range(4):
            raw = bytes(size)
            self.assertEqual(content_shape(raw),(size,0,0))
            with self.assertRaises(content.ContentReject):
                content.stream_validation(raw)

    def test_content_phase_reservations_include_graph_and_duplicate_references(self):
        from golden_board.m2_resources_v2 import content_workspace
        # Descriptor/scalar pools coexist with the largest phase, not their sum.
        self.assertEqual(content_workspace(1000,30,12),
            32000+3840+96+max(4000+720,64*250+32*250+24*30+256,48*500+192*30))
        with self.assertRaisesRegex(DecoderError,'resource-limit'):
            content_workspace(1 << 64,1,0)

    def test_valid_lessons_retain_each_shared_region_map(self):
        from golden_board import content as c
        from golden_board.m2_resources_v2 import content_shape
        count,lessons = 7,5
        records = [c.ContentRecordView(1,c.ContentAtomSchema(1,1,(),0,255)),
            c.ContentRecordView(2,c.ContentMatrix(1,1,count,(0,)*count)),
            c.ContentRecordView(3,c.ContentRegionSet(2,tuple(
                c.ContentRegion(i+1,0,0,1,i,i+1,1) for i in range(count)))),
            c.ContentRecordView(4,c.ContentFeedback(1,2,0))]
        records.extend(c.ContentRecordView(5+i,c.ContentLessonNode(
            5,1,2,0,2,3,0,0,1,2,(),4,6+i if i+1 < lessons else 0)) for i in range(lessons))
        records.append(c.ContentRecordView(5+lessons,c.ContentRoot(5,2*lessons)))
        raw = c.encode_content_v0(c.ContentAuthoringProjection(0,tuple(records)))
        parsed = c.stream_validation(raw)
        self.assertEqual(content_shape(raw),(len(raw),len(records),count*lessons))
        self.assertEqual(sum(map(len,parsed._region_flags.values())),count*lessons)

    def test_shared_region_map_multiplicity_is_not_assumed_byte_linear(self):
        from golden_board.m2_resources_v2 import content_shape
        def frame(rid,kind,payload):
            return rid.to_bytes(2,'big')+kind.to_bytes(2,'big')+len(payload).to_bytes(4,'big')+payload
        region = b'\0\1'+(4096).to_bytes(2,'big')+bytes(14*4096)
        lesson = bytes(6)+b'\0\1'+bytes(10)
        raw = b'\0\0'+(4097).to_bytes(2,'big')+frame(1,7,region)+b''.join(
            frame(i+2,13,lesson) for i in range(4096))
        self.assertEqual(content_shape(raw),(len(raw),4097,4096*4096))
        # This helper only accounts shape; it does not admit this deliberately
        # incomplete teaching stream as valid content.
        with self.assertRaises(ValueError):
            from golden_board import content
            content.stream_validation(raw)


class ProgramWorkspaceTests(unittest.TestCase):
    def test_recipe_header_reservations_are_bounded_before_semantic_admission(self):
        from golden_board.m2_resources_v2 import recipe_storage,recipe_workspace
        raw = bytearray(64)
        raw[8:10] = b'\0\1'
        for at,width,value in ((16,2,2),(18,2,3),(20,4,5),(24,4,7)):
            raw[at:at+width] = value.to_bytes(width,'big')
        # X reserves maximum logical expansion; this helper does not validate
        # the deliberately absent recipe bodies or admit the package.
        x = 64+26*5
        stored = 64+3*x+64*5+64*3+128*2
        self.assertEqual(recipe_storage(bytes(raw)),stored)
        self.assertEqual(recipe_workspace(bytes(raw)),stored+48*5+8*7+16*3+32*2)
        # Even impossible declarations reserve only source-owned ceilings.
        raw[20:24] = b'\xff'*4
        self.assertLess(recipe_workspace(bytes(raw)),16*1048576)

    def test_invalid_or_short_program_only_reserves_its_supplied_wire(self):
        from golden_board.m2_resources_v2 import recipe_storage,recipe_workspace
        self.assertEqual(recipe_storage(b'x'*63),63)
        self.assertEqual(recipe_workspace(b'x'*63),63)


if __name__ == '__main__':
    unittest.main()
