"""A failed prerequisite or replay cannot advance to the physical proof."""
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from golden_board import canonical_manifest as manifest
from golden_board import m2_complete_candidate_v2 as complete
from golden_board.m2_preflight_v2 import BOUND_PATHS, PreflightV2


class CompleteCandidateV2(unittest.TestCase):
    def setUp(self):
        static=SimpleNamespace(candidate_manifest=b'candidate',capacity_ledger=b'capacity',
            ownership_ledger=b'ownership',semantic_envelope=b'semantic')
        source=SimpleNamespace(static=static,inputs=tuple((p,b'owner') for p in BOUND_PATHS),image=SimpleNamespace(carrier=b'carrier'),
                               corpus=SimpleNamespace(counts=(1,)*8,boundary_count=21))
        self.core=PreflightV2(source,SimpleNamespace(value=b'recovery',knowledge_use=b'knowledge',
            first_use=b'first-use'),(),(('carrier.bin',b'carrier'),))
        self.saved={};self.emit=lambda path,raw:self.saved.__setitem__(path,raw)

    def pipeline(self,passed=True,rows=(b'first',b'second')):
        root=manifest.serialize_manifest(dict(result='pass' if passed else 'fail'))
        limits=b'limits'
        def damage(*args):
            records=args[-3];emit=args[-1]
            for i,raw in enumerate(records):emit(f'damage/D0/{i:06}.json',raw)
            emit('resource-limits.json',limits);emit('damage/manifest.json',root)
            return root,limits
        identities={name:dict(bytes=len(raw),sha256=sha256(raw).hexdigest()) for name,raw in (
            ('recovery_provenance',b'recovery'),('knowledge_use',b'knowledge'),
            ('first_use',b'first-use'),('damage_manifest',root))}
        proof=manifest.serialize_manifest(dict(result='pass',**identities))
        return (patch.object(complete,'_enter'),patch.object(complete,'_rows',return_value=iter(rows)),
            patch.object(complete,'build_complete_damage_v2',side_effect=damage),
            patch.object(complete,'validate_measured_bounds_v2'),
            patch.object(complete,'build_independence_proof_v2',return_value=proof))

    def test_complete_pass_binds_proof_to_this_run_and_emits_it_last(self):
        a,b,c,d,e=self.pipeline()
        with a,b,c,d,e:
            result=complete.build_complete_candidate_v2(self.core,1,self.emit,self.saved.__getitem__)
        self.assertTrue(result.passed)
        self.assertEqual(list(self.saved)[-1],'independence-proof.json')
        self.assertEqual(tuple(row.path for row in result.files),tuple(sorted(self.saved)))

    def test_converged_damage_failure_is_retained_without_proof(self):
        a,b,c,d,e=self.pipeline(False)
        with a,b,c,d,e as proof:
            result=complete.build_complete_candidate_v2(self.core,1,self.emit,self.saved.__getitem__)
        self.assertFalse(result.gate6_passed)
        self.assertIsNone(result.independence_proof)
        self.assertIn('damage/manifest.json',self.saved)
        proof.assert_not_called()

    def test_exceeded_bounds_retains_failure_but_malformed_bounds_aborts(self):
        for reason in ('receiver-bounds-resource','receiver-bounds-adapter','receiver-bounds-measured-shape'):
            self.saved={}
            a,b,c,d,e=self.pipeline()
            with a,b,c,d as bounds,e as proof:
                bounds.side_effect=ValueError(reason)
                if reason.endswith('shape'):
                    with self.assertRaisesRegex(ValueError,'measured-shape'):
                        complete.build_complete_candidate_v2(self.core,1,self.emit,self.saved.__getitem__)
                else:
                    result=complete.build_complete_candidate_v2(self.core,1,self.emit,self.saved.__getitem__)
                    self.assertFalse(result.measured_resources_within_bounds)
                    self.assertFalse(result.passed)
                proof.assert_not_called()

    def test_worker_error_or_changed_recovery_never_emits_proof(self):
        def broken_rows():
            yield b'first'
            raise ValueError('receiver-disagreement')
        a,b,c,d,e=self.pipeline(rows=broken_rows())
        with a,b,c,d,e as proof,self.assertRaisesRegex(ValueError,'receiver-disagreement'):
            complete.build_complete_candidate_v2(self.core,1,self.emit,self.saved.__getitem__)
        proof.assert_not_called()
        self.assertNotIn('damage/manifest.json',self.saved)
        a,b,c,d,e=self.pipeline()
        changed=replace(self.core,recovered=SimpleNamespace(value=b'other',knowledge_use=b'knowledge',
                                                             first_use=b'first-use'))
        self.saved={}
        with a,b,c,d,e,self.assertRaisesRegex(ValueError,'proof-binding'):
            complete.build_complete_candidate_v2(changed,1,self.emit,self.saved.__getitem__)
        self.assertNotIn('independence-proof.json',self.saved)

    def test_failed_preflight_cannot_issue_any_damage_or_output(self):
        for path in ('known-answer-manifest.json','grammar-state-manifest.json','static-limits.json'):
            files={name:manifest.serialize_manifest(dict(summary=dict(result='pass'))) for name in
                   ('known-answer-manifest.json','grammar-state-manifest.json')}
            files['static-limits.json']=manifest.serialize_manifest(dict(realism=dict(result='pass',failures=[])))
            files[path]=manifest.serialize_manifest(dict(realism=dict(result='fail',failures=['capacity']))) \
                if path=='static-limits.json' else manifest.serialize_manifest(dict(summary=dict(result='fail')))
            core=replace(self.core,files=tuple(sorted(files.items())))
            emit=Mock()
            with patch.object(complete,'_rows') as replay,self.assertRaises(ValueError):
                complete.build_complete_candidate_v2(core,1,emit,self.saved.__getitem__)
            replay.assert_not_called();emit.assert_not_called()


if __name__=='__main__':unittest.main()
