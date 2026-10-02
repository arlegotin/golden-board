"""Receipt/table projections cannot hide disagreement or invent Linux checks."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import unittest
from unittest.mock import patch

from golden_board import canonical_manifest as manifest
from golden_board import m2_gate8_receipts_v2 as receipts
from golden_board.m2_gate8 import _linux_acquisition_receipt_bytes, load_gate8_policy
from golden_board.m2_gate8_policy_v2 import load_gate8_policy_v2,result_file_paths_v2

ROOT=Path(__file__).resolve().parents[2]


class ReceiptsV2(unittest.TestCase):
    def setUp(self):
        self.policy=load_gate8_policy_v2((ROOT/'spec/gate8-policy-v2.toml').read_bytes())
        names=('spec/gate8-policy-v2.toml','spec/gate8-policy-v0.toml',
               'spec/gate8-verifier-refresh-v0.toml','tools/linux/Dockerfile')
        self.source=manifest.serialize_manifest(dict(schema='m2-evidence-source-v2',
            roadmap_normative_sha256='0'*64,entries=[dict(path=p,mode='100644',
                byte_length=len((ROOT/p).read_bytes()),sha256=sha256((ROOT/p).read_bytes()).hexdigest())
                for p in sorted(names)]))
        self.damage=tuple(sorted(('resource-limits.json','damage/manifest.json','damage/boundary-kats.json',
            *(f'damage/{f}/{name}.json' for f in ('D0','D1','D2','D3','D4','D5','D6','D7','B0')
              for name in ('000000','manifest')))))
        # Structural fixture only. Semantic complete-damage admission and
        # fresh execution are owned by the production coordinator, not here.
        self.rows=tuple(dict(path=p,mode='100644',bytes=1,sha256=sha256(b'x').hexdigest())
                        for p in result_file_paths_v2(self.policy,self.damage))
        self.acquisition=_linux_acquisition_receipt_bytes(load_gate8_policy(
            (ROOT/'spec/gate8-policy-v0.toml').read_bytes()))
        self.receipts={}
        for producer in self.policy.document['producer_receipt']['producer_order']:
            kind,implementation=producer.split('-')
            environment=receipts.environment_identity_v2(kind,'darwin/arm64',self.acquisition)
            executable=dict(implementation=implementation,bytes=10,sha256=sha256(producer.encode()).hexdigest())
            self.receipts[producer]=receipts.render_producer_receipt_v2(self.policy,self.source,
                producer,executable,environment,self.rows,self.damage)

    def test_full_tables_equal_while_producer_executables_may_differ(self):
        raw=receipts.render_cross_language_v2(self.policy,self.source,self.receipts,self.damage)
        value=receipts.validate_cross_language_v2(raw,self.policy,self.source,self.receipts,self.damage)
        self.assertEqual(value['result'],'pass')
        self.assertEqual([r['producer_id'] for r in value['producer_rows']],
                         list(self.policy.document['producer_receipt']['producer_order']))

    def test_one_late_file_disagreement_makes_all_four_rows_fail(self):
        changed=dict(self.receipts)
        value=manifest.validate_canonical_manifest(changed['linux-rust'])
        value['file_rows'][-1]['sha256']='f'*64
        changed['linux-rust']=manifest.serialize_manifest(value)
        result=manifest.validate_canonical_manifest(receipts.render_cross_language_v2(
            self.policy,self.source,changed,self.damage))
        self.assertEqual(result['result'],'fail')
        self.assertEqual([row['result'] for row in result['producer_rows']],['fail']*4)
        self.assertEqual(result['producer_rows'][-1]['receipt_sha256'],sha256(changed['linux-rust']).hexdigest())

    def test_closed_receipt_types_environment_and_file_coverage(self):
        for mutate in (lambda v:v.update(extra=0),lambda v:v.update(source_projection_sha256='f'*64),
            lambda v:v['executable_identity'].update(bytes=True),
            lambda v:v['environment_identity'].update(image_id='none'),
            lambda v:v['file_rows'].pop(),lambda v:v['file_rows'].reverse(),
            lambda v:v['file_rows'][0].update(bytes=True)):
            value=manifest.validate_canonical_manifest(self.receipts['linux-python']);mutate(value)
            with self.assertRaises(ValueError):receipts.admit_producer_receipt_v2(
                manifest.serialize_manifest(value),self.policy,self.source,self.damage)

    def test_linux_requires_actual_matching_snapshots_and_both_full_checks(self):
        verification=receipts.LinuxVerificationV2('pass','pass','a'*64,'a'*64)
        args=(self.policy,self.source,self.receipts,self.damage,self.acquisition)
        raw=receipts.render_linux_attestation_v2(*args,verification)
        value=receipts.admit_linux_attestation_v2(raw,*args)
        self.assertTrue(value['execution_snapshots_equal'])
        self.assertNotIn('host_snapshot_sha256',value)
        for change in (dict(host_full='fail'),dict(linux_full='fail'),dict(linux_snapshot_sha256='b'*64),
                       dict(host_snapshot_sha256='')):
            with self.assertRaises(ValueError):receipts.render_linux_attestation_v2(*args,replace(verification,**change))
        value['canonical_bytes_equal']=1
        with self.assertRaises(ValueError):receipts.admit_linux_attestation_v2(
            manifest.serialize_manifest(value),*args)

    def test_supplied_frozen_source_reader_avoids_live_worktree_reads(self):
        source_read=lambda path:(ROOT/path).read_bytes()
        args=(self.policy,self.source,self.receipts,self.damage,self.acquisition)
        verification=receipts.LinuxVerificationV2('pass','pass','a'*64,'a'*64)
        with patch.object(receipts,'read_source_file_v2',side_effect=AssertionError('live source read')):
            raw=receipts.render_linux_attestation_v2(*args,verification,source_read=source_read)
            receipts.admit_linux_attestation_v2(raw,*args,source_read=source_read)


if __name__=='__main__':unittest.main()
