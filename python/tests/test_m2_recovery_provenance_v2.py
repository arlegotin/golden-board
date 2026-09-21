from dataclasses import FrozenInstanceError
from hashlib import sha256
from pathlib import Path
import os
import unittest

from golden_board import bootstrap, canonical_manifest as manifest, curriculum, identity, m2_policy
from golden_board.m2_carrier_v2 import build_development_carrier
from golden_board.m2_policy_v2 import load_decoder_policy_v2
from golden_board.m2_route_v2 import build_route_images_v2
from golden_board.m2_slice import compile_slice_v0
from golden_board.m2_slice_v1 import compile_slice_v1
from golden_board.m2_static_v2 import build_static_projection_v2
from golden_board.m2_recovery_provenance_v2 import (
    RecoveryProvenanceError, build_recovery_provenance_v2,
    validate_recovery_provenance_v2,
)

ROOT = Path(__file__).resolve().parents[2]


class RecoveryProvenance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sources = tuple((ROOT/p).read_bytes() for p in (
            'studies/m2/slice-v0.json','conformance/content-v0.json',
            'conformance/chess-v0.json','reports/game-set-v0.bin',
            'spec/content-v0.md','spec/constants-v0.toml','spec/curriculum-v0.toml'))
        prototype=compile_slice_v0(*sources)
        cls.compiled=compile_slice_v1((ROOT/'studies/m2/slice-v1.json').read_bytes(),*sources)
        blueprint=curriculum.load_blueprint(sources[-1])
        neutral=(ROOT/'spec/profile-policy-v0.toml').read_bytes()
        cls.policies=tuple((ROOT/'spec'/p).read_bytes() for p in (
            'profile-policy-v2.toml','profile-limits-v2.toml','damage-policy-v2.toml'))
        cls.image=build_development_carrier(cls.compiled,prototype,blueprint,
            m2_policy.load_profile_policy(neutral).capacity_policy)
        routes=build_route_images_v2(cls.compiled,cls.image.capacity_plan.side,cls.image.capacity_plan.width)
        cls.static=build_static_projection_v2(cls.compiled,prototype,blueprint,neutral,cls.image,routes,
            policy_v2=load_decoder_policy_v2(*cls.policies))
        cls.inputs=(cls.image.carrier,cls.static.candidate_manifest,cls.static.capacity_ledger,
            cls.static.ownership_ledger,cls.static.semantic_envelope)
        cls.result=build_recovery_provenance_v2(*cls.inputs,*cls.policies)

    def test_actual_decoder_bytes_feed_both_fresh_evidence_producers(self):
        r=self.result; value=manifest.validate_canonical_manifest(r.value)
        self.assertEqual(len(value),13)
        self.assertEqual(value['schema'],'golden-board.m2-recovery-provenance/v2')
        self.assertEqual(value['scope'],'actual-observation-to-carried-knowledge')
        self.assertEqual(r.prefixes,self.image.route_prefixes)
        self.assertEqual(r.required_stream,self.compiled.required_content_bytes)
        self.assertEqual(r.all_stream,self.compiled.content_bytes)
        self.assertEqual(tuple(b.section_id for b in r.bodies),
            (16,17,18,*range(100,164),*range(200,211)))
        self.assertEqual(len(value['prefix_rows']),4)
        self.assertEqual(len(value['body_rows']),78)
        for name,raw in (('decoder_result',r.decoder_result),('knowledge_use',r.knowledge_use),('first_use',r.first_use)):
            self.assertEqual(value[name],{'bytes':len(raw),'sha256':sha256(raw).hexdigest()})
        knowledge=manifest.validate_canonical_manifest(r.knowledge_use)
        self.assertEqual(knowledge['inputs']['required_stream']['sha256'],sha256(r.required_stream).hexdigest())
        self.assertEqual(len(knowledge['inputs']['decoded_bodies']),78)
        self.assertEqual(manifest.validate_canonical_manifest(r.decoder_result)['artifact_state'],'exact')
        with self.assertRaises(FrozenInstanceError):
            r.required_stream=b''
        if path := os.environ.get('GB_RECOVERY_V2_EXPORT'):
            output = Path(path)
            output.mkdir()
            for name, raw in (('recovery-provenance.json',r.value),('decoder-result.json',r.decoder_result),
                              ('knowledge-use.json',r.knowledge_use),('first-use.json',r.first_use)):
                (output/name).write_bytes(raw)

    def test_forged_carrier_and_rebound_stale_prefix_reject(self):
        bad=bytearray(self.inputs[0]); bad[-1]^=1
        with self.assertRaises(RecoveryProvenanceError):
            build_recovery_provenance_v2(bytes(bad),*self.inputs[1:],*self.policies)
        candidate=manifest.validate_canonical_manifest(self.inputs[1])
        next(r for r in candidate['files'] if r['path']=='route-0.bin')['sha256']='0'*64
        candidate.pop('manifest_identity')
        candidate['manifest_identity']=identity.identity_hex(b'golden-board:manifest:v0\0',(manifest.serialize_manifest(candidate),))
        with self.assertRaises(RecoveryProvenanceError):
            build_recovery_provenance_v2(self.inputs[0],manifest.serialize_manifest(candidate),*self.inputs[2:],*self.policies)

    def test_stale_context_binding_rejects_after_actual_recovery(self):
        candidate,capacity,ownership,semantic=[manifest.validate_canonical_manifest(raw) for raw in self.inputs[1:]]
        for value in (candidate,semantic):
            value['source_identities']['required_content_sha256']='0'*64
        semantic_raw=manifest.serialize_manifest(semantic)
        capacity['semantic_envelope_sha256']=sha256(semantic_raw).hexdigest()
        capacity_raw=manifest.serialize_manifest(capacity)
        ownership['capacity_ledger_sha256']=sha256(capacity_raw).hexdigest()
        ownership_raw=manifest.serialize_manifest(ownership)
        changed={'semantic-envelope.json':semantic_raw,'capacity-ledger.json':capacity_raw,'ownership-ledger.json':ownership_raw}
        for row in candidate['files']:
            if row['path'] in changed:
                raw=changed[row['path']]; row.update(bytes=len(raw),sha256=sha256(raw).hexdigest())
        candidate.pop('manifest_identity')
        candidate['manifest_identity']=identity.identity_hex(b'golden-board:manifest:v0\0',(manifest.serialize_manifest(candidate),))
        with self.assertRaises(RecoveryProvenanceError):
            build_recovery_provenance_v2(self.inputs[0],manifest.serialize_manifest(candidate),capacity_raw,
                ownership_raw,semantic_raw,*self.policies)

    def test_changed_proof_and_non_byte_inputs_reject(self):
        value=manifest.validate_canonical_manifest(self.result.value)
        value['body_rows'][0]['decoded']['sha256']='0'*64
        with self.assertRaises(RecoveryProvenanceError):
            validate_recovery_provenance_v2(manifest.serialize_manifest(value),*self.inputs,*self.policies)
        with self.assertRaises(RecoveryProvenanceError):
            build_recovery_provenance_v2(bytearray(self.inputs[0]),*self.inputs[1:],*self.policies)

    def test_rebound_corrupt_route_calibrations_have_no_source_fallback(self):
        carrier=bytearray(self.inputs[0])
        side,width=self.image.capacity_plan.side,self.image.capacity_plan.width
        for sector in range(4):
            row,col=bootstrap.sector_cell(side,width,sector,0)
            flat=row*side+col
            carrier[4+flat//8]^=1<<(7-flat%8)
        carrier=bytes(carrier)
        candidate,capacity,ownership=[manifest.validate_canonical_manifest(raw) for raw in self.inputs[1:4]]
        capacity['carrier_sha256']=ownership['carrier_sha256']=sha256(carrier).hexdigest()
        capacity_raw=manifest.serialize_manifest(capacity)
        ownership['capacity_ledger_sha256']=sha256(capacity_raw).hexdigest()
        ownership_raw=manifest.serialize_manifest(ownership)
        changed={'carrier.bin':carrier,'capacity-ledger.json':capacity_raw,'ownership-ledger.json':ownership_raw}
        for row in candidate['files']:
            if row['path'] in changed:
                raw=changed[row['path']]; row.update(bytes=len(raw),sha256=sha256(raw).hexdigest())
        candidate.pop('manifest_identity')
        candidate['manifest_identity']=identity.identity_hex(b'golden-board:manifest:v0\0',(manifest.serialize_manifest(candidate),))
        with self.assertRaisesRegex(RecoveryProvenanceError,'recovery'):
            build_recovery_provenance_v2(carrier,manifest.serialize_manifest(candidate),capacity_raw,
                ownership_raw,self.inputs[4],*self.policies)


if __name__=='__main__': unittest.main()
