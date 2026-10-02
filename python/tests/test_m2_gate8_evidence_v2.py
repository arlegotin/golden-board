"""Complete generated-evidence closure hashes actual files without a self-cycle."""
from hashlib import sha256
from pathlib import Path
import unittest

from golden_board import canonical_manifest as manifest
from golden_board import m2_gate8_evidence_v2 as evidence
from golden_board.m2_gate8_policy_v2 import load_gate8_policy_v2,result_file_paths_v2

ROOT=Path(__file__).resolve().parents[2]


class GeneratedEvidenceV2(unittest.TestCase):
    def setUp(self):
        owner=(ROOT/'spec/gate8-policy-v2.toml').read_bytes();self.policy=load_gate8_policy_v2(owner)
        self.source=manifest.serialize_manifest(dict(schema='m2-evidence-source-v2',
            roadmap_normative_sha256='0'*64,entries=[dict(path='spec/gate8-policy-v2.toml',mode='100644',
                byte_length=len(owner),sha256=sha256(owner).hexdigest())]))
        self.damage=tuple(sorted(('resource-limits.json','damage/manifest.json','damage/boundary-kats.json',
            *(f'damage/{f}/{n}.json' for f in ('D0','D1','D2','D3','D4','D5','D6','D7','B0')
              for n in ('000000','manifest')))))
        # Structural closure fixtures, not semantically admitted production evidence.
        self.candidate={path:b'x' for path in result_file_paths_v2(self.policy,self.damage)}
        self.gate8={path:b'x' for path in evidence.gate8_paths_v2(self.policy,include_generated=False)}
        self.gate8['artifacts/gate8/evidence-source-v2.json']=self.source

    def render(self,**options):
        return evidence.render_generated_evidence_v2(self.policy,self.source,self.damage,
            self.candidate.__getitem__,self.gate8.__getitem__,
            candidate_names=options.get('candidate_names',tuple(sorted(self.candidate))),
            gate8_names=options.get('gate8_names',tuple(sorted(self.gate8))))

    def test_every_preimage_is_bound_and_manifest_excludes_itself(self):
        raw=self.render();value=manifest.validate_canonical_manifest(raw)
        self.assertEqual(len(value['candidate_file_rows']),len(self.candidate))
        self.assertEqual(len(value['gate8_file_rows']),len(self.gate8))
        self.assertNotIn('artifacts/gate8/generated-evidence-v2.json',self.gate8)
        self.candidate['carrier.bin']=b'changed'
        self.assertNotEqual(raw,self.render())
        self.gate8['artifacts/gate8/bundles/learner/recipient/viewer.js']=b'changed viewer'
        self.assertNotEqual(raw,self.render())

    def test_missing_extra_duplicate_or_self_referential_inventory_rejects(self):
        for argument,values in (('candidate_names',tuple(sorted(self.candidate))[1:]),
            ('gate8_names',tuple(sorted(self.gate8))+('extra',)),
            ('gate8_names',tuple(sorted(self.gate8))*2),
            ('gate8_names',evidence.gate8_paths_v2(self.policy))):
            with self.assertRaises(ValueError):self.render(**{argument:values})
        self.gate8['artifacts/gate8/evidence-source-v2.json']=b'other'
        with self.assertRaises(ValueError):self.render()


if __name__=='__main__':unittest.main()
