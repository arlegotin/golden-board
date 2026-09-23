"""Own-language source construction and finite pre-damage evidence.

This stage generates no D0–D7 observation and awards no cross-language pass.
The coordinator compares independently produced cores before starting damage.
"""
from dataclasses import dataclass, fields
from hashlib import sha256

from . import canonical_manifest as manifest, curriculum, m2_policy
from .m2_boundary_kat_v2 import boundary_kat_results_v2
from .m2_carrier_v2 import build_development_carrier
from .m2_complete_damage_v2 import _kats
from .m2_damage_oracle_v2 import DamageOracleV2
from .m2_damage_replay_v2 import render_replay_row, validate_replay_row
from .m2_damage_v2 import DamageCorpusV2
from .m2_decoder_v2 import ObservationDecoderV2
from .m2_physical_v2 import PROFILE, SPINE
from .m2_policy_v2 import load_decoder_policy_v2
from .m2_receiver_bounds_v2 import derive_receiver_bounds_v2, validate_measured_bounds_v2
from .m2_recovery_provenance_v2 import build_recovery_provenance_v2
from .m2_resources_v2 import ResourceAggregateV2
from .m2_route_v2 import build_route_images_v2
from .m2_slice import compile_slice_v0
from .m2_slice_v1 import compile_slice_v1
from .m2_static_v2 import build_static_projection_v2

SLICE_PATHS=('studies/m2/slice-v0.json','conformance/content-v0.json','conformance/chess-v0.json',
    'reports/game-set-v0.bin','spec/content-v0.md','spec/constants-v0.toml','spec/curriculum-v0.toml')
POLICY_PATHS=('spec/profile-policy-v2.toml','spec/profile-limits-v2.toml','spec/damage-policy-v2.toml')
BOUND_PATHS=(*POLICY_PATHS,'spec/resource-accounting-v2.md','spec/receiver-bounds-v2.md')
SOURCE_PATHS=tuple(sorted((*SLICE_PATHS,*BOUND_PATHS,'studies/m2/slice-v1.json',
                          'spec/profile-policy-v0.toml','spec/route-data-v0.json')))


def require(ok,reason):
    if not ok:raise ValueError('preflight-v2:'+reason)


def digest(raw):return sha256(raw).hexdigest()


@dataclass(frozen=True,slots=True)
class SourceCandidateV2:
    inputs: tuple
    image: object
    static: object
    corpus: DamageCorpusV2


@dataclass(frozen=True,slots=True)
class PreflightV2:
    source: SourceCandidateV2
    recovered: object
    kat_receipts: tuple
    files: tuple


def build_source_candidate_v2(inputs):
    require(type(inputs) is dict and set(inputs)==set(SOURCE_PATHS)
        and all(type(raw) is bytes and 0<len(raw)<=8388608 for raw in inputs.values())
        and sum(map(len,inputs.values()))<=134217728,'source-domain')
    policy=load_decoder_policy_v2(*(inputs[p] for p in POLICY_PATHS))
    # Admit these two exact owners before any construction as well.
    derive_receiver_bounds_v2(*(inputs[p] for p in BOUND_PATHS))
    source=tuple(inputs[path] for path in SLICE_PATHS)
    prototype=compile_slice_v0(*source)
    compiled=compile_slice_v1(inputs['studies/m2/slice-v1.json'],*source)
    blueprint=curriculum.load_blueprint(source[-1])
    neutral=inputs['spec/profile-policy-v0.toml']
    image=build_development_carrier(compiled,prototype,blueprint,
                                  m2_policy.load_profile_policy(neutral).capacity_policy)
    routes=build_route_images_v2(compiled,image.capacity_plan.side,image.capacity_plan.width)
    static=build_static_projection_v2(compiled,prototype,blueprint,neutral,image,routes,policy_v2=policy)
    corpus=DamageCorpusV2(image,alternate_route_owner_raw=inputs['spec/route-data-v0.json'])
    return SourceCandidateV2(tuple(sorted(inputs.items())),image,static,corpus)


def _known_answer(recovered,profile_raw):
    knowledge=manifest.validate_canonical_manifest(recovered.knowledge_use)
    require(knowledge['summary']['result']=='pass' and knowledge['summary']['example_count']==132,
            'knowledge-premise')
    rows=[];packages=set()
    require(len(knowledge['route_rows'])==4,'route-count')
    for sector,route in enumerate(knowledge['route_rows']):
        require(type(route['sector_id']) is int and route['sector_id']==sector,'route-order')
        packages.add(route['package_sha256'])
        records={row['record_id']:row for row in route['record_rows']}
        require(len(route['example_rows'])==33,'example-count')
        for example in route['example_rows']:
            require(type(example['success']) is bool and example['success'],'example-outcome')
            rows.append(dict(sector_id=sector,**example,record_sha256=records[example['record_id']]['sha256']))
    require(len(packages)==1,'package-agreement')
    return manifest.serialize_manifest(dict(schema='golden-board.m2-known-answer/v2',profile_id=PROFILE,
        input_sha256=dict(profile_policy=digest(profile_raw),knowledge_use=digest(recovered.knowledge_use),
            first_use=digest(recovered.first_use),recovery_provenance=digest(recovered.value)),
        package_sha256=next(iter(packages)),example_rows=rows,
        summary=dict(route_count=4,example_count=len(rows),result='pass')))


def _semantic_convergence(expected,actual,corpus):
    require((actual.artifact_state,actual.m2_required_stream,actual.m2_all_stream,
             actual.section_results,actual.fragment_diagnostics)==
            (expected.artifact_state,expected.required_stream,expected.all_stream,
             expected.semantic_result.section_results,expected.semantic_result.fragment_diagnostics),
            'source-semantic-disagreement')
    wrong=sum(row.envelope is not None and row.envelope!=corpus.clean_envelopes.get(row.section_id)
              for row in actual.section_results)
    require(wrong==expected.wrong_accepts,'source-wrong-accept-disagreement')


def _grammar(source,recovered,kat_receipts,owners):
    corpus=source.corpus
    decoder=ObservationDecoderV2(*owners[:3])
    oracle=DamageOracleV2(corpus)
    clean=decoder.decode('OBS_BITS',source.image.carrier)
    clean_raw=decoder.render_result('OBS_BITS',clean)
    require(clean_raw==recovered.decoder_result,'fresh-clean-result')
    clean_sidecar=decoder.render_resources()
    clean_identity=manifest.serialize_manifest(dict(case_id='clean-observation',channel='OBS_BITS',
        observation_bytes=len(source.image.carrier),observation_sha256=digest(source.image.carrier)))
    corpus_hash=sha256(clean_identity)
    ids=('clean-observation',*(f'B0-{i:06d}' for i in range(21)))
    aggregate=ResourceAggregateV2(ids);aggregate.push(ids[0],clean_sidecar)
    rows=[]
    for ordinal in range(21):
        case=corpus.boundary_case(ordinal)
        expected=oracle.evaluate(case)
        actual=decoder.decode(case.channel,case.observation)
        _semantic_convergence(expected,actual,corpus)
        result_raw=decoder.render_result(case.channel,actual)
        sidecar=decoder.render_resources()
        raw=render_replay_row(case=case,result_raw=result_raw,resources_raw=sidecar,
            section_states=expected.section_states,wrong_accept_count=expected.wrong_accepts,
            section_ids=tuple(corpus.sections),required_section_ids=SPINE)
        validate_replay_row(raw,case,tuple(corpus.sections),SPINE)
        aggregate.push(case.case_id,sidecar)
        corpus_hash.update(manifest.serialize_manifest(case.identity()))
        result=manifest.validate_canonical_manifest(result_raw)
        rows.append(dict(case_id=case.case_id,observation_sha256=digest(case.observation),
            replay_bytes=len(raw),replay_sha256=digest(raw),decoder_result_sha256=digest(result_raw),
            resource_projection_sha256=digest(sidecar),artifact_state=actual.artifact_state,
            resource=result['resource'],convergence='pass'))
    preliminary=aggregate.finish(corpus_hash.hexdigest())
    validate_measured_bounds_v2(preliminary,*owners)
    kats,kats_pass=_kats(kat_receipts)
    require(kats_pass,'boundary-kat-failure')
    result=manifest.validate_canonical_manifest(clean_raw)
    grammar=manifest.serialize_manifest(dict(schema='golden-board.m2-grammar-state/v2',profile_id=PROFILE,
        input_sha256=dict(candidate_manifest=digest(source.static.candidate_manifest),
            recovery_provenance=digest(recovered.value),decoder_result=digest(clean_raw)),
        clean_result=dict(artifact_state=result['artifact_state'],established_profile_id=result['established_profile_id'],
            section_count=len(result['section_rows']),required_stream_sha256=result['m2_required_stream_sha256'],
            all_stream_sha256=result['m2_all_stream_sha256']),
        boundary_kats=manifest.validate_canonical_manifest(kats)['rows'],boundary_rows=rows,
        summary=dict(boundary_case_count=21,boundary_kat_count=4,result='pass')))
    return grammar,preliminary


def build_preflight_v2(inputs):
    source=build_source_candidate_v2(inputs);static=source.static
    owners=tuple(inputs[p] for p in BOUND_PATHS)
    recovered=build_recovery_provenance_v2(source.image.carrier,static.candidate_manifest,
        static.capacity_ledger,static.ownership_ledger,static.semantic_envelope,*owners[:3])
    known=_known_answer(recovered,owners[0])
    kats=boundary_kat_results_v2(*owners[:3])
    grammar,preliminary=_grammar(source,recovered,kats,owners)
    output={field.name.replace('_','-')+'.json':getattr(static,field.name) for field in fields(static)}
    output.update({'carrier.bin':source.image.carrier,
        **{f'route-{i}.bin':raw for i,raw in enumerate(source.image.route_prefixes)},
        'recovery-provenance.json':recovered.value,'knowledge-use.json':recovered.knowledge_use,
        'first-use.json':recovered.first_use,'decoder-result.json':recovered.decoder_result,
        'm2-required.content-v0.bin':recovered.required_stream,'m2-all.content-v0.bin':recovered.all_stream,
        'receiver-bounds.json':derive_receiver_bounds_v2(*owners),
        'known-answer-manifest.json':known,'grammar-state-manifest.json':grammar,
        'preflight-resource-limits.json':preliminary})
    require(len(output)==22 and all(0<len(raw)<=1048576 for raw in output.values()),'core-files')
    return PreflightV2(source,recovered,kats,tuple(sorted(output.items())))
