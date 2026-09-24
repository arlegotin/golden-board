from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import unittest

from golden_board import canonical_manifest as manifest
from golden_board.m2_gate8_policy_v2 import load_gate8_policy_v2
from golden_board.m2_gate8_reports_v2 import (
    derive_candidate_metrics_v2, render_selection_v2, validate_selection_v2,
    render_candidate_ready_roadmap_v2, validate_candidate_ready_roadmap_v2,
    render_candidate_ready_report_v2,
)

ROOT = Path(__file__).resolve().parents[2]


class Gate8ReportProjectionsV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = load_gate8_policy_v2((ROOT/'spec/gate8-policy-v2.toml').read_bytes())
        cls.profile = (ROOT/'spec/profile-policy-v2.toml').read_bytes()

    def test_unrun_cross_and_gate_short_circuit_never_fabricate_a_finalist(self):
        owner = self.policy.document
        files = {}
        rows = []
        for i in range(1, 9):
            paths = owner['gates']['gate1'] if i == 1 else ()
            evidence = []
            for path in paths:
                path = path if path.startswith('spec/') else owner['authority']['candidate_root']+'/'+path
                raw = self.profile if path.startswith('spec/') else b'fixture-only failed evidence\n'
                files[path] = raw
                evidence.append(dict(path=path, bytes=len(raw), sha256=sha256(raw).hexdigest()))
            rows.append(dict(gate_id=i, result='fail' if i == 1 else 'not_evaluated',
                             evidence_rows=sorted(evidence, key=lambda r:r['path'])))
        raw = render_selection_v2(self.policy, self.profile, None, rows, files.__getitem__, ())
        value = manifest.validate_canonical_manifest(raw)
        self.assertEqual(value['cross_language_sha256'], 'none')
        self.assertEqual(value['retained_finalist_ids'], [])
        self.assertEqual(value['provisional_preferred_id'], 'none')
        self.assertEqual([s['surviving_before'] for s in value['selection_steps']],
                         [[owner['candidate_id']], [], [], [], [], []])
        validate_selection_v2(raw, self.policy, self.profile, None, rows, files.__getitem__, ())
        for field, changed in [('result', 'pass'), ('gate_id', True)]:
            bad = deepcopy(rows)
            bad[1][field] = changed
            with self.assertRaises(ValueError):
                render_selection_v2(self.policy, self.profile, None, bad, files.__getitem__, ())
        files[next(p for p in files if p.endswith('known-answer-manifest.json'))] += b'changed'
        with self.assertRaises(ValueError):
            render_selection_v2(self.policy, self.profile, None, rows, files.__getitem__, ())

    def test_metrics_require_measured_complete_evidence_and_no_bool_coercion(self):
        # Missing evidence rejects before a synthetic zero can become a metric.
        with self.assertRaises(ValueError):
            derive_candidate_metrics_v2(self.policy, lambda path: b'{}\n')

    def test_empty_source_preimage_is_allowed_without_admitting_empty_evidence(self):
        from golden_board.m2_gate8_reports_v2 import _raw
        from golden_board.m2_source_v2 import admit_source_projection_v2
        # Source grammar permits an actual empty regular file; report evidence
        # still requires a nonempty preimage. Do not conflate these boundaries.
        source_raw = manifest.serialize_manifest(dict(schema='m2-evidence-source-v2',
            roadmap_normative_sha256='a'*64, entries=[dict(path='empty',mode='100644',
                byte_length=0,sha256=sha256(b'').hexdigest())]))
        row = admit_source_projection_v2(source_raw,self.policy)['entries'][0]
        try:
            actual = _raw({'empty':b''}.__getitem__,row['path'],
                self.policy.document['bounds']['source_file_bytes'],allow_empty=True)
        except (TypeError,ValueError) as error:
            self.fail('admitted empty source preimage rejected: '+str(error))
        self.assertEqual(actual,b'')
        for invalid in (b'',bytearray(),None):
            with self.assertRaises(ValueError):_raw({'evidence':invalid}.__getitem__,'evidence')
        for invalid in (bytearray(),None,b'ab'):
            with self.assertRaises(ValueError):
                _raw({'source':invalid}.__getitem__,'source',1,allow_empty=True)
        with self.assertRaises(ValueError):_raw({}.__getitem__,'empty',allow_empty=True)

    def test_metrics_use_current_static_fields_and_full_measurement_identity(self):
        from python.tests.test_m2_static_v2 import StaticProjection
        StaticProjection.setUpClass()
        fixture = StaticProjection
        files = {p:getattr(fixture.result,p[:-5].replace('-','_')) for p in (
            'candidate-manifest.json','static-limits.json','semantic-envelope.json','capacity-ledger.json',
            'ownership-ledger.json','density-ledger.json','geometry-search.json')}
        files.update({'carrier.bin':fixture.image.carrier,
            'm2-required.content-v0.bin':fixture.compiled.required_content_bytes,
            'm2-all.content-v0.bin':fixture.compiled.content_bytes,
            **{f'route-{i}.bin':raw for i,raw in enumerate(fixture.image.route_prefixes)}})
        # Formula fixture only: component scope verifies source/static inputs
        # and commitment linkage; full report separately admits all real cases.
        from golden_board.m2_resources_v2 import ADAPTER_KERNELS
        measured = dict(schema='golden-board.m2-resource-limits/v2',corpus_sha256='a'*64,
            case_count=861+5*fixture.image.capacity_plan.units,case_resources_sha256='b'*64,
            source_owners={p:sha256((ROOT/p).read_bytes()).hexdigest() for p in (
                'spec/profile-policy-v2.toml','spec/profile-limits-v2.toml',
                'spec/damage-policy-v2.toml','spec/resource-accounting-v2.md')},
            maximum_resource=dict(primitive_steps=123,peak_scratch_bytes=456,section_attempts=7),
            adapter_maxima=[dict(kernel=k,calls=0,reference_input_units=0,peak_workspace_bytes=0) for k in ADAPTER_KERNELS])
        files['resource-limits.json'] = manifest.serialize_manifest(measured)
        damage = dict(schema='golden-board.m2-damage-manifest/v2',
            accidental_case_count=840+5*fixture.image.capacity_plan.units,boundary_case_count=21,
            corpus_sha256=measured['corpus_sha256'],resource_limits_sha256=sha256(files['resource-limits.json']).hexdigest(),
            candidate_manifest_sha256=sha256(files['candidate-manifest.json']).hexdigest())
        files['damage/manifest.json'] = manifest.serialize_manifest(damage)
        metrics = derive_candidate_metrics_v2(self.policy,files.__getitem__)
        self.assertEqual(set(metrics),set(self.policy.document['metrics']['keys']))
        self.assertEqual((metrics['carrier_cells'],metrics['carrier_bytes'],metrics['shell_width']),
                         (2040**2,2040**2//8,112))
        self.assertEqual((metrics['required_stream_bytes'],metrics['all_stream_bytes']),(42432,55664))
        self.assertEqual((metrics['measured_primitive_steps'],metrics['measured_peak_scratch_bytes'],
                          metrics['measured_section_attempts']),(123,456,7))
        measured['maximum_resource']['primitive_steps'] = True
        files['resource-limits.json'] = manifest.serialize_manifest(measured)
        damage['resource_limits_sha256'] = sha256(files['resource-limits.json']).hexdigest()
        files['damage/manifest.json'] = manifest.serialize_manifest(damage)
        with self.assertRaises(ValueError):derive_candidate_metrics_v2(self.policy,files.__getitem__)
        measured['maximum_resource']['primitive_steps'] = 123
        measured['case_count'] = 22
        files['resource-limits.json'] = manifest.serialize_manifest(measured)
        damage['resource_limits_sha256'] = sha256(files['resource-limits.json']).hexdigest()
        files['damage/manifest.json'] = manifest.serialize_manifest(damage)
        with self.assertRaises(ValueError):derive_candidate_metrics_v2(self.policy,files.__getitem__)

    def test_roadmap_rejects_partial_stale_and_non_v2_report(self):
        roadmap = (ROOT/'docs/roadmap.md').read_bytes()
        for report in (b'{}\n', manifest.serialize_manifest({'schema':'m2-feasibility-v0'})):
            with self.assertRaises(ValueError):
                render_candidate_ready_roadmap_v2(self.policy, roadmap, report)
        with self.assertRaises(ValueError):
            validate_candidate_ready_roadmap_v2(self.policy, roadmap, roadmap, b'{}\n')

    def test_report_requires_a_fresh_preflight_context_before_retained_files(self):
        def unreachable(_path):
            self.fail('partial context must reject before trusting any retained file')
        with self.assertRaises(ValueError):
            render_candidate_ready_report_v2(self.policy,b'roadmap\n',b'{}\n',b'{}\n',b'{}\n',
                unreachable,unreachable,unreachable,(),b'acquisition',
                preflight=None,candidate_names=(),gate8_names=())

    def test_status_renderer_preserves_normative_bytes_and_binds_exact_report(self):
        # Structural renderer fixture only. It does not establish component,
        # execution or human evidence and is never written to authority paths.
        from golden_board.m2_gate8 import roadmap_normative_sha256
        owner = self.policy.document
        roadmap = ('| Roadmap revision | 11 |\n| Project state | In progress |\n'
            '| Current milestone | M2 — Full-carrier bootstrap and transport feasibility |\n'
            'Normative prefix.\n## 13. Project status\n'
            '| M2 — Full-carrier bootstrap and transport feasibility | In progress | Historic evidence. '+
            owner['lifecycle']['pre_ready_tail']+' |\n## 14. Adversarial stress matrix\nNormative suffix.\n').encode()
        h = 'a'*64
        identities = lambda kind,paths: [dict(kind=kind,name=p,sha256=
            roadmap_normative_sha256(roadmap) if p == 'roadmap-normative-v0' else h) for p in sorted(paths)]
        from golden_board.m2_gate8_reports_v2 import _guarantee
        value = dict(schema='m2-feasibility-v2',roadmap_revision=11,
            m1_repository_baseline=owner['report']['m1_repository_baseline'],
            semantic_input_identities=identities('semantic_input',owner['report']['semantic_paths']),
            spec_policy_limit_source_lock_identities=identities('normative_owner',owner['report']['normative_paths']),
            candidate_rows=[dict(candidate_id=owner['candidate_id'],tuple_identity=h,policy_identity=h,
                complexity_class='C1',metrics={key:0 for key in owner['metrics']['keys']},
                hard_gates=dict(zip(owner['report']['hard_gate_keys'],['pass']*8+['not_evaluated'],strict=True)),
                disposition='preferred',reason_code=owner['report']['reason_code'],reason=owner['report']['reason'])],
            retained_finalist_ids=[owner['candidate_id']],provisional_preferred_id=owner['candidate_id'],
            selection_steps=[dict(step=step,surviving_before=[owner['candidate_id']],outcome=[owner['candidate_id']],
                                 evidence_sha256=h) for step in owner['selection']['step_order']],
            provisional_capacity_envelope=dict(profile_limits_sha256=h,semantic_envelope_sha256=h,
                side_search_policy_sha256=h,retained_ledger_identities=identities('placeholder',[])),
            preferred_carrier_identity_and_density=dict(candidate_id=owner['candidate_id'],carrier_sha256=h,
                ownership_ledger_sha256=h,density_ledger_sha256=h,N=2040**2,S=2040,W=112),
            damage_summary_D0_through_D7=[dict(candidate_id=owner['candidate_id'],family_id='D'+str(i),
                manifest_sha256=h,guarantee_id=_guarantee(i),result='pass',wrong_accept_count=0) for i in range(8)],
            cross_language_and_linux_results=dict(evidence_source_projection_sha256=h,host_full='pass',linux_full='pass',
                execution_snapshots_equal=True,canonical_bytes_equal=True,states_equal=True,ledgers_equal=True),
            technical_round_summaries=[],qualifying_technical_round_id='none',learner_round_summaries=[],
            qualifying_learner_round_id='none',permitted_administrative_counts=[],
            accepted_limitations=sorted(owner['report']['limitations']),
            generated_evidence_hashes=[dict(kind='generated_manifest',name=owner['generated_evidence']['path'],sha256=h)],
            m2_pilot_envelope={key:owner['candidate_id'] if key == 'profile_id' else
                'validation-pending' if key == 'state' else h for key in owner['report']['pilot_keys']})
        value['provisional_capacity_envelope']['retained_ledger_identities'] = [
            dict(kind=kind,name=owner['candidate_id'],sha256=h) for kind in sorted(owner['report']['ledger_kinds'])]
        raw = manifest.serialize_manifest(value)
        after = render_candidate_ready_roadmap_v2(self.policy,roadmap,raw)
        self.assertEqual(roadmap_normative_sha256(after),roadmap_normative_sha256(roadmap))
        self.assertIn(sha256(raw).hexdigest().encode(),after)
        self.assertIn(b'Historic evidence.',after)
        validate_candidate_ready_roadmap_v2(self.policy,roadmap,after,raw)
        for before in (roadmap.replace(b'| 11 |',b'| 10 |',1),after,
                       roadmap.replace(b'Historic evidence.',b'Historic evidence. '+owner['lifecycle']['pre_ready_tail'].encode())):
            with self.assertRaises(ValueError):render_candidate_ready_roadmap_v2(self.policy,before,raw)
        with self.assertRaises(ValueError):validate_candidate_ready_roadmap_v2(self.policy,roadmap,after+b'x',raw)
        changed = deepcopy(value);changed['candidate_rows'][0]['metrics']['carrier_bytes']=True
        with self.assertRaises(ValueError):render_candidate_ready_roadmap_v2(self.policy,roadmap,manifest.serialize_manifest(changed))


if __name__ == '__main__':
    unittest.main()
