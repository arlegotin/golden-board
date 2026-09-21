"""Bounded complete replay rows; production promotion remains separate."""
from hashlib import sha256

from . import canonical_manifest as manifest
from .m2_damage_v2 import DamageObservationV2
from .m2_decoder_bridge_v2 import _result_frame_value
from .m2_resources_v2 import _read_resource_projection, checked

SCHEMA='golden-board.m2-damage-replay-case/v2'
FAMILIES=tuple(f'D{i}' for i in range(8))+('B0',)
STATES=('verified','recovered','incomplete','corrupt','ambiguous','unknown')
FIELDS=frozenset(('schema','observation','decoder_result','resource_projection',
    'expected_section_states','wrong_accept_count','reauthored_boundary','promise_result'))


def _require(ok,reason):
    if not ok:raise ValueError('damage-replay:'+reason)


def _ids(values):
    _require(type(values) is tuple and 1<=len(values)<=4096
        and all(type(v) is int and 0<v<1<<32 for v in values)
        and all(a<b for a,b in zip(values,values[1:])),'section-domain')


def render_replay_row(*,case,result_raw,resources_raw,section_states,
                      wrong_accept_count,section_ids,required_section_ids):
    """Serialize converged evaluator facts, never infer their source truth.

    The caller must freshly compute and compare semantic truth before calling.
    This boundary closes byte binding, catalog coverage and promise derivation.
    """
    _require(type(case) is DamageObservationV2 and type(case.family) is str
        and case.family in FAMILIES and type(case.ordinal) is int
        and 0<=case.ordinal<1000000 and type(case.observation) is bytes
        and len(case.observation)<=4194306,'case-domain')
    _ids(section_ids);_ids(required_section_ids)
    _require(required_section_ids==(1,2,3,16,17,18)
        and set(required_section_ids)<=set(section_ids),'required-domain')
    _require(type(section_states) is tuple and len(section_states)==len(section_ids)
        and all(type(row) is tuple and len(row)==2 and type(row[0]) is int
                and row[0]==sid and row[1] in STATES
                for row,sid in zip(section_states,section_ids,strict=True)),'section-coverage')
    checked(wrong_accept_count)
    result=_result_frame_value(result_raw)
    resources=_read_resource_projection(resources_raw)
    observation=case.identity()
    _require(result['channel']==case.channel==resources['channel']
        and resources['observation_sha256']==observation['observation_sha256']
        and resources['result_sha256']==sha256(result_raw).hexdigest()
        and resources['resource']==result['resource'],'result-binding')
    states=dict(section_states)
    _require(all(row['state']!='unknown' and states.get(row['section_id'])==row['state']
                 for row in result['section_rows']),'visible-section-state')
    visible={row['section_id'] for row in result['section_rows']}
    _require(all(state=='unknown' or sid in visible for sid,state in section_states),
             'invented-source-state')
    boundary=case.family=='B0'
    passed=boundary or wrong_accept_count==0
    if case.family in ('D0','D1','D5'):
        passed=passed and all(state in ('verified','recovered') for state in states.values())
    elif case.family in ('D2','D3','D4','D6'):
        passed=passed and all(states[sid] in ('verified','recovered') for sid in required_section_ids)
    return manifest.serialize_manifest(dict(schema=SCHEMA,observation=observation,
        decoder_result=result,resource_projection=resources,
        expected_section_states=[dict(section_id=sid,state=state) for sid,state in section_states],
        wrong_accept_count=wrong_accept_count,reauthored_boundary=boundary,
        promise_result='pass' if passed else 'fail'))


def validate_replay_row(raw,case,section_ids,required_section_ids):
    """Rebind an external row to the fresh exact case and complete catalog."""
    value=manifest.validate_canonical_manifest(raw)
    _require(set(value)==FIELDS and value['schema']==SCHEMA,'row-shape')
    rows=value['expected_section_states']
    _require(type(rows) is list and all(type(row) is dict
        and set(row)=={'section_id','state'} for row in rows),'state-shape')
    expected=render_replay_row(case=case,
        result_raw=manifest.serialize_manifest(value['decoder_result']),
        resources_raw=manifest.serialize_manifest(value['resource_projection']),
        section_states=tuple((row['section_id'],row['state']) for row in rows),
        wrong_accept_count=value['wrong_accept_count'],section_ids=section_ids,
        required_section_ids=required_section_ids)
    _require(raw==expected,'row-recomputation')
    return value
