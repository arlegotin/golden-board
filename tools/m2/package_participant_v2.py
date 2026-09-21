"""Revised participant preimages from fresh own-language source/recovery.

No publication or human pass occurs here. The production coordinator calls
this only after the automated prerequisites and validates both complete kits.
"""
from hashlib import sha256
from pathlib import Path

from golden_board import canonical_manifest as manifest
from golden_board.m2_damage_oracle_v2 import DamageOracleV2
from golden_board.m2_decoder_v2 import ObservationDecoderV2
from golden_board.m2_preflight_v2 import POLICY_PATHS, PreflightV2, _semantic_convergence
from golden_board.m2_learner_assessment_v2 import build_learner_assessment_v2
from golden_board.m2_gate8_policy_v2 import _document
from golden_board.m2_source_v2 import admit_source_projection_v2
from tools.m2 import package_learner_v1
from tools.m2.package_technical_preview_v2 import CASES, content_query, read_file

ROOT=Path(__file__).resolve().parents[2]


def require(ok,reason):
    if not ok:raise ValueError('participant-v2:'+reason)


def _context(preflight):
    require(type(preflight) is PreflightV2,'fresh-preflight-type')
    source=preflight.source;recovered=preflight.recovered
    files=dict(preflight.files)
    require(files['carrier.bin']==source.image.carrier
        and files['recovery-provenance.json']==recovered.value
        and files['decoder-result.json']==recovered.decoder_result
        and files['m2-required.content-v0.bin']==recovered.required_stream
        and files['m2-all.content-v0.bin']==recovered.all_stream,'recovered-binding')
    return source,recovered


def build_technical_files_v2(root,preflight):
    source,recovered=_context(preflight)
    inputs=dict(source.inputs)
    corpus=source.corpus;oracle=DamageOracleV2(corpus)
    decoder=ObservationDecoderV2(*(inputs[p] for p in POLICY_PATHS))
    cases=tuple(corpus.case(family,ordinal) for family,ordinal in CASES)
    require(tuple(case.channel for case in cases)==('OBS_MATRIX','OBS_MATRIX','OBS_UNITS','OBS_UNITS'),
            'heldout-channels')
    template=root/'studies/m2/templates/technical'
    literal={
        'recipient/01-clean/READ-ME.txt':'clean-instructions-v2.txt',
        'recipient/01-clean/opening.md':'neutral-opening-prompt.md',
        'recipient/01-clean/allowed-tools.md':'allowed-tools.md',
        'recipient/01-clean/storage.txt':'storage-v2.txt',
        'recipient/02-adapter/READ-ME.txt':'adapter-instructions-v2.txt',
        'recipient/02-adapter/channel-formats.md':'channel-formats.md',
        'recipient/02-adapter/channel-mechanics-fixtures.json':'channel-mechanics-fixtures.json',
        'recipient/03-heldouts/READ-ME.txt':'heldout-instructions-v2.txt',
        'recipient/04-final-account/final-account-question.md':'final-account-question.md',
        'owner/READ-ME.txt':'owner-instructions-v2.txt',
        'owner/optional-help/export-format.md':'export-format.md',
    }
    files={name:read_file(template/path) for name,path in literal.items()}
    files['recipient/01-clean/observation.bits']=source.image.carrier
    files['recipient/03-heldouts/channels.json']=manifest.serialize_manifest(dict(observations=[
        dict(file=f'observation-{letter}.bin',channel=case.channel)
        for letter,case in zip('abcd',cases,strict=True)]))
    files['owner/expected/clean.json']=recovered.decoder_result
    for letter,case in zip('abcd',cases,strict=True):
        expected=oracle.evaluate(case)
        actual=decoder.decode(case.channel,case.observation)
        _semantic_convergence(expected,actual,corpus)
        require(expected.wrong_accepts==0,'heldout-wrong-accept')
        files[f'recipient/03-heldouts/observation-{letter}.bin']=case.observation
        files[f'owner/expected/{letter}.json']=decoder.render_result(case.channel,actual)
    request,answer,position=content_query(recovered.all_stream)
    files['recipient/03-heldouts/content-query.json']=request
    files['owner/expected/content-query.json']=answer
    files['owner/expected/query-position.bin']=position
    require(len(files)==25,'technical-file-count')
    return dict(sorted(files.items()))


def build_learner_files_v2(root,preflight):
    source,recovered=_context(preflight)
    inputs=dict(source.inputs)
    files={'recipient/'+path:raw for path,raw in package_learner_v1.build_files(
        recovered.required_stream,root).items()}
    files['owner/semantic-evaluation.json']=build_learner_assessment_v2(
        recovered.required_stream,read_file(root/'studies/m2/learner-assessment-v2.toml'),
        inputs['conformance/chess-v0.json'],inputs['reports/game-set-v0.bin'])
    files['owner/READ-ME.txt']=read_file(root/'studies/m2/templates/learner/owner-instructions-v2.txt')
    require(len(files)==11,'learner-file-count')
    return dict(sorted(files.items()))


def _bundle_value(policy,kind,files,source_hash,candidate_hash,recovery_hash,content_hash):
    require(kind in ('technical','learner') and type(files) is dict,'bundle-domain')
    contract=policy[kind+'_bundle']
    names=(*contract['participant_paths'],*contract['owner_paths'])
    require(set(files)==set(names) and len(files)==len(names),'bundle-paths')
    require(all(type(raw) is bytes and 0<len(raw)<=policy['bounds']['bundle_file_bytes']
                for raw in files.values())
        and sum(map(len,files.values()))<=policy['bounds']['bundle_aggregate_bytes'],'bundle-size')
    def rows(roles,paths):
        return [dict(role_id=role,path=path,mode='100644',bytes=len(files[path]),
                     sha256=sha256(files[path]).hexdigest())
                for role,path in zip(roles,paths,strict=True)]
    participants=rows(contract['participant_roles'],contract['participant_paths'])
    owners=rows(contract['owner_roles'],contract['owner_paths'])
    releases=[];offset=0
    for ordinal,(release_id,count) in enumerate(zip(contract['release_ids'],contract['release_counts'],strict=True)):
        releases.append(dict(ordinal=ordinal,release_id=release_id,
            participant_role_ids=list(contract['participant_roles'][offset:offset+count])))
        offset+=count
    require(offset==len(participants),'release-coverage')
    for digest in (source_hash,candidate_hash,recovery_hash,content_hash):
        require(type(digest) is str and len(digest)==64 and all(c in '0123456789abcdef' for c in digest),
                'bundle-identity')
    return dict(schema='golden-board.m2-participant-bundle/v2',
        bundle_id=contract['bundle_id'],profile_id=policy['candidate_id'],
        source_projection_sha256=source_hash,candidate_manifest_sha256=candidate_hash,
        recovery_provenance_sha256=recovery_hash,content_stream_sha256=content_hash,
        participant_files=participants,owner_files=owners,release_rows=releases)


def _source_rows(policy,source_projection_raw,source_read):
    rows={row['path']:row for row in admit_source_projection_v2(source_projection_raw,policy)['entries']}
    owners={'spec/gate8-policy-v2.toml':policy._raw,
            **{path:read_file(ROOT/path) if source_read is None else source_read(path) for path in ('spec/learner-assessment-v2.md',
                'studies/m2/learner-assessment-v2.toml')}}
    for path,raw in owners.items():
        require(path in rows and rows[path]['byte_length']==len(raw)
            and rows[path]['sha256']==sha256(raw).hexdigest(),'source-owner-binding')
    return rows


def _literal_bindings(policy,kind,files,source_rows):
    contract=policy[kind+'_bundle']
    roles=dict(zip((*contract['participant_roles'],*contract['owner_roles']),
                   (*contract['participant_paths'],*contract['owner_paths']),strict=True))
    for role,source_path in contract['literal_sources'].items():
        require(source_path in source_rows and roles[role] in files,'literal-source-path')
        row=source_rows[source_path];raw=files[roles[role]]
        require(row['byte_length']==len(raw) and row['sha256']==sha256(raw).hexdigest(),
                'literal-source-binding')


def render_bundle_manifest_v2(policy,kind,files,source_projection_raw,preflight,*,source_read=None):
    """Closed projection; caller generated and retains every named preimage."""
    source_rows=_source_rows(policy,source_projection_raw,source_read);policy=_document(policy)
    source,recovered=_context(preflight)
    require(kind in ('technical','learner'),'bundle-kind')
    _literal_bindings(policy,kind,files,source_rows)
    if kind=='learner':
        require(files.get('recipient/lesson.content-v0.bin')==recovered.required_stream,'content-binding')
    else:
        require(files.get('recipient/01-clean/observation.bits')==source.image.carrier
            and files.get('owner/expected/clean.json')==recovered.decoder_result,'artifact-binding')
    raw=preflight.recovered.all_stream if kind=='technical' else preflight.recovered.required_stream
    return manifest.serialize_manifest(_bundle_value(policy,kind,files,
        sha256(source_projection_raw).hexdigest(),sha256(preflight.source.static.candidate_manifest).hexdigest(),
        sha256(preflight.recovered.value).hexdigest(),sha256(raw).hexdigest()))


def render_bundle_preimages_v2(policy,bundles,source_projection_raw,preflight,*,source_read=None):
    source_rows=_source_rows(policy,source_projection_raw,source_read);owner=_document(policy)
    require(type(bundles) is tuple and len(bundles)==2,'bundle-pair')
    rows=[]
    for (kind,files,raw),expected in zip(bundles,('technical','learner'),strict=True):
        require(kind==expected,'bundle-order')
        _literal_bindings(owner,kind,files,source_rows)
        value=manifest.validate_canonical_manifest(raw)
        require(set(value)==set(owner['bundle_common']['keys']),'bundle-shape')
        regenerated=render_bundle_manifest_v2(policy,kind,files,source_projection_raw,preflight,source_read=source_read)
        require(regenerated==raw,'bundle-recomputation')
        file_rows=value['participant_files']+value['owner_files']
        require(set(files)=={row['path'] for row in file_rows} and len(files)==len(file_rows),
                'bundle-preimages')
        for row in file_rows:
            preimage=files[row['path']]
            require(row['bytes']==len(preimage) and row['sha256']==sha256(preimage).hexdigest(),
                    'bundle-file-binding')
        rows.append(dict(bundle_id=value['bundle_id'],manifest_bytes=len(raw),manifest_sha256=sha256(raw).hexdigest(),
                         file_rows=file_rows))
    return manifest.serialize_manifest(dict(schema='golden-board.m2-bundle-preimages/v2',
        profile_id=owner['candidate_id'],source_projection_sha256=sha256(source_projection_raw).hexdigest(),
        bundle_rows=rows))
