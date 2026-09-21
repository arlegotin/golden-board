"""Bundle commitments bind exact role preimages and release order."""
from pathlib import Path
from hashlib import sha256
from types import SimpleNamespace
import unittest

from golden_board import canonical_manifest as manifest
from golden_board.m2_gate8_policy_v2 import load_gate8_policy_v2
from golden_board.m2_preflight_v2 import PreflightV2
from tools.m2 import package_participant_v2 as package

ROOT=Path(__file__).resolve().parents[2]


class ParticipantBundleV2(unittest.TestCase):
    def setUp(self):
        self.policy=load_gate8_policy_v2((ROOT/'spec/gate8-policy-v2.toml').read_bytes())
        document=self.policy.document
        sources={path:b'x' for kind in ('technical','learner')
                 for path in document[kind+'_bundle']['literal_sources'].values()}
        sources.update({path:(ROOT/path).read_bytes() for path in ('spec/gate8-policy-v2.toml',
            'spec/learner-assessment-v2.md','studies/m2/learner-assessment-v2.toml')})
        self.source=manifest.serialize_manifest(dict(schema='m2-evidence-source-v2',
            roadmap_normative_sha256='0'*64,entries=[dict(path=path,mode='100644',
                byte_length=len(raw),sha256=sha256(raw).hexdigest()) for path,raw in sorted(sources.items())]))
        # These are projection-only fixture bytes, never a source-built kit or
        # a recovery/gate claim. The real packagers invoke actual source APIs.
        recovered=SimpleNamespace(value=b'provenance',decoder_result=b'result',
                                  required_stream=b'required',all_stream=b'all')
        source=SimpleNamespace(image=SimpleNamespace(carrier=b'carrier'),
                               static=SimpleNamespace(candidate_manifest=b'candidate'))
        self.preflight=PreflightV2(source,recovered,(),tuple(sorted({
            'carrier.bin':b'carrier','recovery-provenance.json':b'provenance',
            'decoder-result.json':b'result','m2-required.content-v0.bin':b'required',
            'm2-all.content-v0.bin':b'all'}.items())))
        self.bundles=[]
        for kind in ('technical','learner'):
            contract=document[kind+'_bundle']
            files={name:b'x' for name in (*contract['participant_paths'],*contract['owner_paths'])}
            if kind=='learner':files['recipient/lesson.content-v0.bin']=recovered.required_stream
            else:
                files['recipient/01-clean/observation.bits']=source.image.carrier
                files['owner/expected/clean.json']=recovered.decoder_result
            raw=package.render_bundle_manifest_v2(self.policy,kind,files,self.source,self.preflight)
            self.bundles.append((kind,files,raw))

    def test_exact_releases_and_both_actual_preimage_sets_are_bound(self):
        result=manifest.validate_canonical_manifest(package.render_bundle_preimages_v2(
            self.policy,tuple(self.bundles),self.source,self.preflight))
        self.assertEqual([row['bundle_id'] for row in result['bundle_rows']],['technical-v2','learner-v2'])
        self.assertEqual([len(row['file_rows']) for row in result['bundle_rows']],[25,11])
        technical=manifest.validate_canonical_manifest(self.bundles[0][2])
        self.assertEqual([len(row['participant_role_ids']) for row in technical['release_rows']],[5,3,7,1])
        self.assertEqual([row['ordinal'] for row in technical['release_rows']],[0,1,2,3])
        self.assertEqual({row['path'] for row in technical['participant_files']}&
                         {row['path'] for row in technical['owner_files']},set())

    def test_changed_missing_or_extra_actual_file_rejects(self):
        for operation in ('change','missing','extra'):
            kind,files,raw=self.bundles[0];files=dict(files)
            if operation=='change':files[next(iter(files))]=b'y'
            elif operation=='missing':del files[next(iter(files))]
            else:files['extra']=b'x'
            with self.subTest(operation=operation),self.assertRaises(ValueError):
                package.render_bundle_preimages_v2(self.policy,((kind,files,raw),self.bundles[1]),self.source,self.preflight)

    def test_rebound_manifest_shape_role_mode_and_integer_types_reject(self):
        for index,mutate in enumerate((
            lambda v:v.update(extra=0),
            lambda v:v.update(schema='different'),
            lambda v:v['participant_files'][0].update(bytes=True),
            lambda v:v['participant_files'][0].update(mode='100755'),
            lambda v:v['participant_files'][0].update(role_id='different'),
            lambda v:v['release_rows'].reverse(),
        )):
            kind,files,raw=self.bundles[0];value=manifest.validate_canonical_manifest(raw)
            mutate(value)
            with self.subTest(index=index),self.assertRaises(ValueError):
                package.render_bundle_preimages_v2(self.policy,
                    ((kind,files,manifest.serialize_manifest(value)),self.bundles[1]),self.source,self.preflight)

    def test_source_projection_and_rebound_literal_are_checked(self):
        for raw in (b'source',self.source.replace(b'"byte_length":1',b'"byte_length":2',1)):
            with self.assertRaises(ValueError):
                package.render_bundle_preimages_v2(self.policy,tuple(self.bundles),raw,self.preflight)
        kind,files,_=self.bundles[0];files=dict(files)
        files['recipient/01-clean/READ-ME.txt']=b'changed'
        with self.assertRaisesRegex(ValueError,'literal-source-binding'):
            package.render_bundle_manifest_v2(self.policy,kind,files,self.source,self.preflight)

    def test_manifest_cannot_claim_a_different_actual_content_or_artifact(self):
        for index,path in ((0,'recipient/01-clean/observation.bits'),
            (0,'owner/expected/clean.json'),(1,'recipient/lesson.content-v0.bin')):
            kind,files,_=self.bundles[index];files=dict(files);files[path]=b'other'
            with self.assertRaises(ValueError):
                package.render_bundle_manifest_v2(self.policy,kind,files,self.source,self.preflight)

    def test_preimages_cannot_mix_self_declared_candidate_or_recovery_hashes(self):
        for key in ('candidate_manifest_sha256','recovery_provenance_sha256','content_stream_sha256'):
            kind,files,raw=self.bundles[1];value=manifest.validate_canonical_manifest(raw);value[key]='f'*64
            with self.assertRaises(ValueError):
                package.render_bundle_preimages_v2(self.policy,(self.bundles[0],
                    (kind,files,manifest.serialize_manifest(value))),self.source,self.preflight)


if __name__=='__main__':unittest.main()
