#!/usr/bin/env python3
"""Prepare a local, unreleased technical preview; never a Gate8 bundle/pass."""
import argparse
from hashlib import sha256
import os
from pathlib import Path
import stat

from golden_board import bootstrap, canonical_manifest as manifest, chess, content, curriculum, identity, m2_policy
from golden_board.body_codec_v1 import decode_body
from golden_board.m2_carrier_v2 import build_development_carrier
from golden_board.m2_damage_v2 import DamageCorpusV2
from golden_board.m2_damage_oracle_v2 import DamageOracleV2
from golden_board.m2_decoder_v2 import ObservationDecoderV2
from golden_board.m2_knowledge_v2 import validate_knowledge_use_v2
from golden_board.m2_slice import compile_slice_v0
from golden_board.m2_slice_v1 import compile_slice_v1

ROOT=Path(__file__).resolve().parents[2]
SOURCES=('studies/m2/slice-v0.json','conformance/content-v0.json','conformance/chess-v0.json',
         'reports/game-set-v0.bin','spec/content-v0.md','spec/constants-v0.toml','spec/curriculum-v0.toml')
OWNERS=('spec/profile-policy-v2.toml','spec/profile-limits-v2.toml','spec/damage-policy-v2.toml')
RECOVERY=('all.content-v0.bin','body-100.bin','body-200.bin','decoder-resources.json',
          'decoder-result.json','knowledge-use.json','required.content-v0.bin',
          'route-0.bin','route-1.bin','route-2.bin','route-3.bin')
CASES=(('D3',0),('D2',0),('D4',0),('D7',11))
STORAGE=b'''The observation is a binary file. Its first four bytes give the exact
number N of following binary symbols, as an unsigned big-endian integer.
The symbols are packed eight per byte, most-significant bit first. Read
exactly N symbols; unused low bits of the final byte, if any, are zero.
This describes file storage only. Preserve the file unchanged.
'''
START=b'''Read opening.md and allowed-tools.md, then examine observation.bits.
Storage.txt describes only how its binary symbols are stored in the file.

Work out what the data conveys and explain how its own evidence supports
your reading. Trying ideas, wrong starts and backtracking are welcome.
Save working code, the command needed to run it, notes and actual outputs
in answers/clean/ outside this input folder. Keep uncertainties and rival
interpretations in your own words. An unfinished reproducible result is useful.
Tell the owner when you are ready for the next inputs. No extra form is needed.
'''.replace(b'Storage.txt',b'storage.txt')
ADAPTER=b'''These files describe storage for the later observations only.
Keep your clean-method files unchanged. If needed, add a thin input adapter
and save it with its command in answers/adapter/. Tell the owner when ready.
Do not change the interpretation to match a later input without saying so.
'''
HELDOUT=b'''Use your saved method on each observation separately. channels.json names
only the storage channel for each file. Save code, commands, actual outputs
and a short account for each input in answers/heldout/a/ through d/.
Do not fill unavailable data from the clean observation or another result.

Answer content-query.json from the clean output you actually recovered and
identify the references you followed. Save the answer and any resulting bytes
in answers/heldout/content-query/. If the requested data is unavailable, say so.
For generic_record, return its complete record bytes, their SHA-256 and your
explanation of its fields and references. For chess_transition, return the
recorded move bytes and resulting position, identifying the representation
you used. Detailed output conventions are available only as explicit help.
Keep unsupported conclusions and any later method changes explicit.
'''
OWNER='''LOCAL DEVELOPMENT PREVIEW — NOT RELEASED

Do not show this kit to anyone yet. It is not a qualifying participant round,
Candidate-ready bundle or fresh-release receipt. Historical assisted successes
and historical packets remain separate. A fresh release and its exact revised
production bindings are still required before exposure.

When a later owner-authorized release is ready, the intended simple sequence is:

1. Copy only recipient/01-clean/ into the person's offline workspace. Ask them
   to read READ-ME.txt and reconstruct what the data conveys. Give ordinary
   local tools and room for sustained effort, false starts and backtracking.
   They save working code, the run command, notes and actual output files in
   answers/clean/. Do not supply this kit's manifest, owner directory, repository,
   decoder, learner runner, inferred geometry, hashes or expected answers.
2. When they declare their clean method ready, keep an unchanged copy of those
   submitted files. Give only recipient/02-adapter/. They may add a thin storage
   adapter and save it in answers/adapter/. Keep the earlier method unchanged;
   do not confirm whether it is correct. Save that method plus adapter before
   showing actual held-outs. These copies are useful checkpoints, not forms.
3. Give recipient/03-heldouts/ together. Ask them to run the saved method
   separately on a..d and answer the existing content query from their actual
   clean recovered output. Outputs go in answers/heldout/a/ through d/ and
   answers/heldout/content-query/. Later interpretation changes are useful
   diagnostic work, not a retroactive success by the earlier saved method.
4. Give recipient/04-final-account/. Ask for the concise account it requests;
   save answers/final-account.txt. Collect the working source, commands and
   real output files. No names, dates, consent, eligibility quiz, biography,
   timing form or reconstructed terminal history is requested by this preview.

owner/optional-help/export-format.md supplies detailed output conventions,
including Position export. Keep it private initially. If supplied later, note
that ordinary fact in the person's existing notes and interpret the result as
assisted on those conventions; never count the supplied convention as discovery.
Procedural file/tool help is fine; substantive hints or expected-answer feedback
make subsequent work diagnostic. Do not impose the old generic lesson as a new
technical task or substitute familiar/example bytes for recovered bytes.

owner/expected/ is for local checking only. It contains freshly derived Python
receiver results and resource sidecars, checked for semantic agreement with the
separate source oracle. This is not full corpus/resource-oracle or independent
Rust agreement. The exact old record12/game0/ply0 selectors are reused, but their
answers come from current observed recovered content. No new quiz is added.

The initial-hint conflicts in the historical bundle are deliberately avoided:
clean-question/export conventions are not put in the first share, and later
observations have neutral a..d names. This preview does not mutate or admit the
historical Gate8 policy. Full revised Gate8 source/bundle/release bindings and
fresh human acquisition remain pending. Its manifest is an owner inventory,
not a participant handout or success receipt.
'''


def require(ok,reason):
    if not ok:raise ValueError('technical-preview:'+reason)


def read_file(path,maximum=1048576):
    metadata=path.lstat()
    require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink==1,'regular-source')
    with path.open('rb') as stream:raw=stream.read(maximum+1)
    require(len(raw)<=maximum,'source-bound')
    return raw


def digest_row(path,raw):
    return dict(path=path,bytes=len(raw),sha256=sha256(raw).hexdigest())


def bind_recovery(carrier,files):
    require(type(carrier) is bytes and type(files) is dict
            and set(files)=={*RECOVERY,'recovery-provenance.json'}
            and all(type(raw) is bytes and len(raw)<=1048576 for raw in files.values()),'recovery-files')
    value=manifest.validate_canonical_manifest(files['recovery-provenance.json'])
    require(set(value)=={'schema','scope','carrier_bytes','carrier_sha256','files'}
        and value['schema']=='golden-board.m2-knowledge-recovery-development/v2'
        and value['scope']=='local-observation-recovery-and-finite-knowledge-evidence-only'
        and type(value['carrier_bytes']) is int and value['carrier_bytes']==len(carrier)
        and value['carrier_sha256']==sha256(carrier).hexdigest()
        and value['files']==[digest_row(name,files[name]) for name in sorted(RECOVERY)],'recovery-binding')


def participant_files(root,carrier,cases):
    """Render staged recipient materials; no expected result is an argument."""
    require(len(cases)==4 and tuple(c.channel for c in cases)==
            ('OBS_MATRIX','OBS_MATRIX','OBS_UNITS','OBS_UNITS'),'heldout-channels')
    template=root/'studies/m2/templates/technical'
    files={'recipient/01-clean/READ-ME.txt':START,
        'recipient/01-clean/opening.md':read_file(template/'neutral-opening-prompt.md'),
        'recipient/01-clean/allowed-tools.md':read_file(template/'allowed-tools.md'),
        'recipient/01-clean/storage.txt':STORAGE,
        'recipient/01-clean/observation.bits':carrier,
        'recipient/02-adapter/READ-ME.txt':ADAPTER,
        'recipient/02-adapter/channel-formats.md':read_file(template/'channel-formats.md'),
        'recipient/02-adapter/channel-mechanics-fixtures.json':read_file(template/'channel-mechanics-fixtures.json'),
        'recipient/03-heldouts/READ-ME.txt':HELDOUT,
        'recipient/03-heldouts/channels.json':manifest.serialize_manifest(dict(observations=[
            dict(file=f'observation-{letter}.bin',channel=case.channel)
            for letter,case in zip('abcd',cases,strict=True)])),
        'recipient/04-final-account/final-account-question.md':read_file(template/'final-account-question.md')}
    files.update((f'recipient/03-heldouts/observation-{letter}.bin',case.observation)
                 for letter,case in zip('abcd',cases,strict=True))
    return files


def content_query(raw):
    projection=content.projection_view(content.stream_validation(raw))
    records={r.record_id:r for r in projection.records}
    require(12 in records,'generic-query-record')
    cursor,frames=4,{}
    for _ in projection.records:
        end=cursor+8+int.from_bytes(raw[cursor+4:cursor+8],'big')
        frames[int.from_bytes(raw[cursor:cursor+2],'big')]=raw[cursor:end]
        cursor=end
    bindings=[r.record_id for r in projection.records if type(r.payload) is content.ContentSemanticBinding
              and (r.payload.binding_class,r.payload.namespace_id,r.payload.semantic_code)==(1,2,1)]
    require(len(bindings)==1,'query-game-binding')
    games=[bytes(r.payload.data) for r in projection.records if type(r.payload) is content.ContentOpaqueData
           and r.payload.data_binding_ref==bindings[0]]
    require(len(games)==1,'query-game-payload')
    game=games[0];count=int.from_bytes(game[:2],'big')
    require(count>=1 and len(game)==2+2*count+1,'query-game-framing')
    moves=tuple(chess.decode_move(game[i:i+2]) for i in range(2,len(game)-1,2))
    chess.validate_source_record(moves,game[-1])
    position=chess.encode_position(chess.replay_from_start(moves[:1]).position)
    request=dict(schema='golden-board.m2-technical-content-query/v0',
                 generic_record=dict(record_id=12),chess_transition=dict(game_ordinal=0,ply_ordinal=0))
    answer=dict(schema='golden-board.m2-technical-content-query-result/v0',
        generic_record=dict(record_id=12,canonical_record_sha256=sha256(frames[12]).hexdigest()),
        chess_transition=dict(game_ordinal=0,ply_ordinal=0,move_hex=game[2:4].hex(),
            resulting_position_identity=identity.identity_hex(b'golden-board:position:v0\0',(position,))))
    return manifest.serialize_manifest(request),manifest.serialize_manifest(answer),position


def build_files(root,carrier,recovery_files):
    bind_recovery(carrier,recovery_files)
    source_paths=(*SOURCES,*OWNERS,'studies/m2/slice-v1.json','spec/profile-policy-v0.toml',
        'spec/damage-corpus-v2.md','spec/damage-oracle-v2.md','spec/resource-accounting-v2.md',
        'spec/knowledge-use-v2.md','tools/m2/package_technical_preview_v2.py',
        *(f'studies/m2/templates/technical/{name}' for name in ('neutral-opening-prompt.md','allowed-tools.md',
          'channel-formats.md','channel-mechanics-fixtures.json','export-format.md','final-account-question.md')))
    sources={p:read_file(root/p) for p in source_paths}
    raws=tuple(sources[p] for p in SOURCES)
    declaration=sources['studies/m2/slice-v1.json']
    policy_raw=sources['spec/profile-policy-v0.toml']
    compiled=compile_slice_v1(declaration,*raws)
    image=build_development_carrier(compiled,compile_slice_v0(*raws),curriculum.load_blueprint(raws[-1]),
        m2_policy.load_profile_policy(policy_raw).capacity_policy)
    require(image.carrier==carrier,'current-source-carrier-mismatch')
    prefixes=tuple(recovery_files[f'route-{i}.bin'] for i in range(4))
    require(prefixes==image.route_prefixes,'observed-prefix-binding')
    decoder=ObservationDecoderV2(*(sources[p] for p in OWNERS))
    clean=decoder.decode('OBS_BITS',carrier)
    require(clean.artifact_state=='exact' and clean.m2_required_stream==recovery_files['required.content-v0.bin']
            and clean.m2_all_stream==recovery_files['all.content-v0.bin'],'fresh-clean-recovery')
    bodies={}
    for sid in (100,200):
        rows=[row for row in clean.section_results if row.section_id==sid]
        require(len(rows)==1 and rows[0].envelope is not None,'fresh-body-section')
        envelope=bootstrap.decode_section_envelope(rows[0].envelope)
        bodies[sid]=decode_body(envelope.section_version,envelope.payload)
        require(bodies[sid]==recovery_files[f'body-{sid}.bin'],'fresh-body-recovery')
    validate_knowledge_use_v2(recovery_files['knowledge-use.json'],prefixes,
        side=image.capacity_plan.side,width=image.capacity_plan.width,
        required_stream=clean.m2_required_stream,all_stream=clean.m2_all_stream,body_payloads=bodies)
    files={'OWNER-READ-ME.txt':OWNER.encode(),
        'owner/expected/clean-result.json':decoder.render_result('OBS_BITS',clean),
        'owner/expected/clean-resources.json':decoder.render_resources(),
        'owner/optional-help/export-format.md':read_file(root/'studies/m2/templates/technical/export-format.md')}
    corpus=DamageCorpusV2(image)
    oracle=DamageOracleV2(corpus)
    cases=tuple(corpus.case(family,ordinal) for family,ordinal in CASES)
    files.update(participant_files(root,carrier,cases))
    request,answer,position=content_query(clean.m2_all_stream)
    files['recipient/03-heldouts/content-query.json']=request
    files['owner/expected/content-query-result.json']=answer
    files['owner/expected/content-query-position.bin']=position
    expected_rows=[]
    for letter,case in zip('abcd',cases,strict=True):
        expected=oracle.evaluate(case)
        actual=decoder.decode(case.channel,case.observation)
        require((actual.artifact_state,actual.m2_required_stream,actual.m2_all_stream,
                 actual.section_results,actual.fragment_diagnostics)==
                (expected.artifact_state,expected.required_stream,expected.all_stream,
                 expected.semantic_result.section_results,expected.semantic_result.fragment_diagnostics)
                and expected.wrong_accepts==0,'fresh-heldout-agreement:'+case.case_id)
        result=decoder.render_result(case.channel,actual)
        resources=decoder.render_resources()
        files[f'owner/expected/{letter}-result.json']=result
        files[f'owner/expected/{letter}-resources.json']=resources
        expected_rows.append(dict(label=letter,case_id=case.case_id,channel=case.channel,
            observation_sha256=sha256(case.observation).hexdigest(),
            result_sha256=sha256(result).hexdigest(),resources_sha256=sha256(resources).hexdigest(),
            artifact_state=actual.artifact_state,wrong_accepts=expected.wrong_accepts))
    files['owner/expected/heldouts.json']=manifest.serialize_manifest(dict(
        schema='golden-board.m2-technical-preview-expected/v2',rows=expected_rows))
    require(all(read_file(root/p)==raw for p,raw in sources.items()),'source-drift')
    require(len(files)<=128 and all(type(raw) is bytes and len(raw)<=4194306 for raw in files.values())
            and sum(map(len,files.values()))<=67108864,'output-bound')
    releases=[dict(ordinal=i,phase=phase,files=sorted(p for p in files if p.startswith(f'recipient/{i+1:02}-{phase}/')))
              for i,phase in enumerate(('clean','adapter','heldouts','final-account'))]
    preview=dict(schema='golden-board.m2-technical-preview/v2',status='local-development-preview-not-released',
        carrier=digest_row('recipient/01-clean/observation.bits',carrier),
        recovery_provenance_sha256=sha256(recovery_files['recovery-provenance.json']).hexdigest(),
        knowledge_use_sha256=sha256(recovery_files['knowledge-use.json']).hexdigest(),
        source_files=[digest_row(p,raw) for p,raw in sorted(sources.items())],
        release_rows=releases,optional_help_files=['owner/optional-help/export-format.md'],
        files=[digest_row(p,raw) for p,raw in sorted(files.items())],
        pending=['revised-production-gates-and-bindings','fresh-release','owner-authorized-exposure',
                 'fresh-human-acquisition'])
    files['preview-manifest.json']=manifest.serialize_manifest(preview)
    return dict(sorted(files.items()))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--carrier',type=Path,required=True)
    parser.add_argument('--recovery-dir',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    require(not args.output_dir.exists() and not args.output_dir.is_symlink(),'output-must-be-new')
    require({p.name for p in args.recovery_dir.iterdir()}=={*RECOVERY,'recovery-provenance.json'},'recovery-tree')
    recovery={name:read_file(args.recovery_dir/name) for name in (*RECOVERY,'recovery-provenance.json')}
    files=build_files(ROOT,read_file(args.carrier,524292),recovery)
    # Validation finishes before reserving a fresh private output directory.
    # A partial IO failure leaves no manifest and is never a complete preview.
    args.output_dir.mkdir(mode=0o700)
    for name in (*sorted(p for p in files if p!='preview-manifest.json'),'preview-manifest.json'):
        path=args.output_dir/name
        path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(files[name])
        os.chmod(path,0o600)
        require(read_file(path,4194306)==files[name],'written-file-binding')
    print(manifest.serialize_manifest(dict(status='local-development-preview-not-released',
        files=len(files),manifest_sha256=sha256(files['preview-manifest.json']).hexdigest())).decode(),end='')


if __name__=='__main__':main()
