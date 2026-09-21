"""Pure revised Gate8 projections; no execution receipt or authority writes.

Callers own fresh component admission and provide its exact raw preimages.
These projections recheck closed shapes, identities and complete file bindings.
They cannot turn file presence, an unrun gate or a retained result into a pass.
"""
from hashlib import sha256
import tomllib

from . import canonical_manifest as manifest
from .m2_gate8 import roadmap_normative_sha256
from .m2_gate8_policy_v2 import _document, _path, result_file_paths_v2
from .m2_physical_v2 import admit_physical_inputs, numeric_tree
from .m2_policy_v2 import PROFILE_POLICY_SHA256
from .m2_source_v2 import admit_source_projection_v2

MAX_U64 = (1 << 64)-1
COUNTERS = ('primitive_steps', 'peak_scratch_bytes', 'section_attempts')


def require(ok, reason):
    if not ok:
        raise ValueError('gate8-reports-v2:' + reason)


def digest(raw):
    return sha256(raw).hexdigest()


def _hash(value):
    require(type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value), 'hash')
    return value


def uint(value):
    require(type(value) is int and 0 <= value <= MAX_U64, 'u64')
    return value


def shape(value, keys):
    require(type(value) is dict and set(value) == set(keys), 'shape')
    return value


def _raw(read, path, maximum=1048576, *, allow_empty=False):
    require(_path(path), 'path')
    try:
        raw = read(path)
    except (KeyError, OSError) as error:
        raise ValueError('gate8-reports-v2:missing:' + path) from error
    require(type(raw) is bytes and (0 if allow_empty else 1) <= len(raw) <= maximum, 'file-bound:' + path)
    return raw


def _json(raw, schema=None, keys=None):
    require(type(raw) is bytes and 0 < len(raw) <= 1048576, 'json-bound')
    value = manifest.validate_canonical_manifest(raw)
    if schema is not None:
        require(value.get('schema') == schema, 'schema')
    if keys is not None:
        shape(value, keys)
    return value


def _profile(raw, owner):
    require(type(raw) is bytes and digest(raw) == PROFILE_POLICY_SHA256, 'profile-owner')
    value = tomllib.loads(raw.decode('utf-8'))
    require(value['candidate']['id'] == owner['candidate_id'], 'profile-id')
    return value


def _row(path, raw):
    return dict(path=path, bytes=len(raw), sha256=digest(raw))


def _match_row(row, raw, *, mode=False):
    shape(row, ('path', 'bytes', 'sha256', 'mode') if mode else ('path', 'bytes', 'sha256'))
    require(_path(row['path']) and uint(row['bytes']) == len(raw)
        and row['sha256'] == digest(raw) and (not mode or row['mode'] == '100644'), 'file-binding')


def derive_candidate_metrics_v2(policy, candidate_read):
    """Derive the23 fields; caller separately admits the complete damage tree."""
    owner = _document(policy)
    read = lambda p: _raw(candidate_read, p)
    physical = admit_physical_inputs(*(read(p) for p in (
        'candidate-manifest.json', 'capacity-ledger.json', 'ownership-ledger.json', 'semantic-envelope.json')))
    static = _json(read('static-limits.json'), 'golden-board.m2-static-limits/v2', (
        'schema','profile_id','scope','source_identities','carrier_sha256','projection_sha256',
        'semantic_capacity','selected_manifestation','route_package','declared_transport','realism'))
    require(static['profile_id'] == owner['candidate_id'] and static['scope'] == 'static-construction-only'
        and static['source_identities'] == physical.semantic['source_identities']
        and static['semantic_capacity'] == physical.semantic['totals'], 'static-source')
    projection = shape(static['projection_sha256'], (
        'semantic_envelope','capacity_ledger','ownership_ledger','density_ledger','geometry_search'))
    for key, value in projection.items():
        require(value == digest(read(key.replace('_', '-')+'.json')), 'static-projection')
    candidate = _json(read('candidate-manifest.json'))
    entries = candidate['files']
    for entry in entries:
        _match_row(entry, _raw(candidate_read, entry['path']))
    selected = shape(static['selected_manifestation'], (
        'side','shell_width','cells','carrier_bytes','carrier_file_bytes','interior_side','population',
        'physical_units','protected_cells','fixed_pad_cells','inventory_entries','inventory_payload_bytes',
        'inventory_dependency_count','maximum_dependency_count','maximum_section_payload_bytes',
        'maximum_decoded_body_bytes','maximum_section_envelope_bytes','maximum_fragments_per_section',
        'logical_groups','factor_group_counts','load_payload_bytes','load_fragment_counts',
        'mandatory_physical_units','route_prefix_bytes','route_headroom_cells'))
    package = shape(static['route_package'], (
        'sha256','encoded_bytes','expanded_bytes','recipe_count','table_count','table_payload_bytes',
        'node_count','edge_count','maximum_declared_primitive_steps','maximum_declared_scratch_bytes',
        'recipe_fields','recipe_rows','records_per_sector','prefix_sha256'))
    numeric_tree(selected)
    numeric_tree(package)
    cells, carrier_bytes = uint(selected['cells']), uint(selected['carrier_bytes'])
    carrier = _raw(candidate_read, 'carrier.bin', owner['bounds']['carrier_file_bytes'])
    require(cells == physical.side*physical.side and cells == 8*carrier_bytes
        and 0 < carrier_bytes <= 524288 and len(carrier) == carrier_bytes+4
        and static['carrier_sha256'] == digest(carrier) == physical.capacity['carrier_sha256']
        and selected['physical_units'] == physical.count and selected['shell_width'] == physical.width,
        'selected-geometry')
    required, all_stream = read('m2-required.content-v0.bin'), read('m2-all.content-v0.bin')
    require(digest(required) == physical.semantic['source_identities']['required_content_sha256']
        and digest(all_stream) == physical.semantic['source_identities']['all_content_sha256'], 'stream-binding')
    measured_raw = read('resource-limits.json')
    measured = _json(measured_raw, 'golden-board.m2-resource-limits/v2', (
        'schema','corpus_sha256','case_count','case_resources_sha256','source_owners','maximum_resource','adapter_maxima'))
    _hash(measured['corpus_sha256']); _hash(measured['case_resources_sha256'])
    for value in shape(measured['source_owners'], (
        'spec/profile-policy-v2.toml','spec/profile-limits-v2.toml',
        'spec/damage-policy-v2.toml','spec/resource-accounting-v2.md')).values():
        _hash(value)
    from .m2_resources_v2 import ADAPTER_KERNELS
    require(type(measured['adapter_maxima']) is list and len(measured['adapter_maxima']) == 22, 'measured-kernels')
    for row,kernel in zip(measured['adapter_maxima'],ADAPTER_KERNELS,strict=True):
        shape(row, ('kernel','calls','reference_input_units','peak_workspace_bytes'))
        require(row['kernel'] == kernel, 'measured-kernel-order')
        for key in ('calls','reference_input_units','peak_workspace_bytes'):
            uint(row[key])
        require(row['calls'] != 0 or row['reference_input_units'] == row['peak_workspace_bytes'] == 0, 'unused-kernel')
    damage = _json(read('damage/manifest.json'), 'golden-board.m2-damage-manifest/v2')
    require(uint(measured['case_count']) == uint(damage['accidental_case_count'])+uint(damage['boundary_case_count'])
        == 861+5*physical.count and damage['resource_limits_sha256'] == digest(measured_raw)
        and measured['corpus_sha256'] == damage['corpus_sha256']
        and damage['candidate_manifest_sha256'] == digest(read('candidate-manifest.json')),
        'complete-measurement')
    maximum = shape(measured['maximum_resource'], COUNTERS)
    for value in maximum.values():
        uint(value)
    values = [cells,carrier_bytes,selected['shell_width'],selected['physical_units'],selected['logical_groups'],
        *[package[k] for k in ('encoded_bytes','expanded_bytes','recipe_count','node_count','edge_count','table_count','table_payload_bytes')],
        *[physical.capacity['ledger'][k] for k in ('shell_instruction_cells','shell_example_cells','shell_recipe_cells')],
        len(required),len(all_stream),physical.semantic['totals']['content_capacity_before_reserve_bytes'],
        physical.semantic['totals']['reserve_payload_bytes'],524288-carrier_bytes,*[maximum[k] for k in COUNTERS]]
    require(len(values) == 23, 'metric-count')
    return dict(zip(owner['metrics']['keys'], map(uint, values), strict=True))


def _gate_paths(owner, gate, damage_paths):
    paths = damage_paths if gate == 6 else owner['gates']['gate'+str(gate)]
    prefix = owner['authority']['candidate_root']+'/'
    return tuple(sorted(p if p.startswith(('spec/', 'artifacts/gate8/')) else prefix+p for p in paths))


def build_gate_rows_v2(policy, results, evidence_read, damage_paths):
    """Hash reached roles for caller-supplied actual gate outcomes, not decide them."""
    owner = _document(policy)
    require(type(results) is tuple and len(results) == 8 and type(damage_paths) is tuple, 'gate-inputs')
    if results[5] != 'not_evaluated':
        result_file_paths_v2(policy,damage_paths)
    rows = []; stopped = False
    for gate,result in enumerate(results,1):
        require(result in owner['gates']['states'] and (result == 'not_evaluated' if stopped
            else result != 'not_evaluated'), 'gate-order')
        witnesses = [] if stopped else [_row(path,_raw(evidence_read,path))
            for path in _gate_paths(owner,gate,damage_paths)]
        rows.append(dict(gate_id=gate,result=result,evidence_rows=witnesses))
        stopped = stopped or result == 'fail'
    return rows


def render_selection_v2(policy, profile_policy_raw, cross_raw, gate_rows, evidence_read, damage_paths):
    owner = _document(policy)
    _profile(profile_policy_raw, owner)
    require(type(gate_rows) is list and len(gate_rows) == 8 and type(damage_paths) is tuple, 'gates')
    if any(row.get('gate_id') == 6 and row.get('result') != 'not_evaluated' for row in gate_rows if type(row) is dict):
        result_file_paths_v2(policy, damage_paths)
    stopped = False
    for gate, row in enumerate(gate_rows, 1):
        shape(row, owner['selection']['gate_row_keys'])
        require(type(row['gate_id']) is int and row['gate_id'] == gate
            and row['result'] in owner['gates']['states'] and type(row['evidence_rows']) is list, 'gate-domain')
        if stopped:
            require(row['result'] == 'not_evaluated' and row['evidence_rows'] == [], 'gate-short-circuit')
            continue
        require(row['result'] != 'not_evaluated', 'unreached-first-gate')
        paths = _gate_paths(owner, gate, damage_paths)
        require(len(row['evidence_rows']) == len(paths) and all(type(r) is dict for r in row['evidence_rows'])
            and [r.get('path') for r in row['evidence_rows']] == list(paths), 'gate-evidence-paths')
        for witness in row['evidence_rows']:
            _match_row(witness, _raw(evidence_read, witness['path']))
        stopped = row['result'] == 'fail'
    cross_hash = 'none'
    if gate_rows[-1]['result'] == 'not_evaluated':
        require(cross_raw is None, 'unrun-comparison')
    else:
        cross = _json(cross_raw, owner['cross_language']['schema'], owner['cross_language']['keys'])
        require(cross['profile_id'] == owner['candidate_id'] and cross['result'] in ('pass','fail'), 'comparison-domain')
        _hash(cross['source_projection_sha256'])
        require(type(cross['producer_rows']) is list and len(cross['producer_rows']) == 4, 'comparison-rows')
        for row,producer in zip(cross['producer_rows'],owner['producer_receipt']['producer_order'],strict=True):
            shape(row,owner['cross_language']['row_keys'])
            require(row['producer_id'] == producer and row['result'] == cross['result']
                and uint(row['receipt_bytes']) > 0 and uint(row['file_count']) > 0, 'comparison-row')
            _hash(row['receipt_sha256']); _hash(row['file_rows_sha256'])
        path = owner['cross_language']['path']
        require(_raw(evidence_read,path) == cross_raw, 'comparison-binding')
        require(gate_rows[-1]['result'] != 'pass' or cross['result'] == 'pass', 'gate8-comparison')
        cross_hash = digest(cross_raw)
    survives = all(row['result'] == 'pass' for row in gate_rows)
    outcome = [owner['candidate_id']] if survives else 'no-passing-result'
    before = [owner['candidate_id']]
    steps = []
    for step in owner['selection']['step_order']:
        preimage = dict(schema='golden-board.m2-selection-step-evidence/v2',
            profile_policy_sha256=digest(profile_policy_raw), cross_language_sha256=cross_hash,
            gate_rows=gate_rows, step=step, surviving_before=before, outcome=outcome)
        steps.append(dict(step=step, surviving_before=before, outcome=outcome,
                          evidence_sha256=digest(manifest.serialize_manifest(preimage))))
        before = [owner['candidate_id']] if survives else []
    return manifest.serialize_manifest(dict(schema=owner['selection']['schema'], profile_id=owner['candidate_id'],
        profile_policy_sha256=digest(profile_policy_raw), cross_language_sha256=cross_hash, gate_rows=gate_rows,
        retained_finalist_ids=[owner['candidate_id']] if survives else [],
        provisional_preferred_id=owner['candidate_id'] if survives else 'none', selection_steps=steps))


def validate_selection_v2(raw, *args):
    _json(raw)
    require(raw == render_selection_v2(*args), 'selection-recomputation')
    return manifest.validate_canonical_manifest(raw)


def _report_shape(raw, owner):
    value = _json(raw, owner['report']['schema'], owner['report']['keys'])
    require(type(value['roadmap_revision']) is int and value['roadmap_revision'] == 11
        and value['m1_repository_baseline'] == owner['report']['m1_repository_baseline']
        and value['retained_finalist_ids'] == [owner['candidate_id']]
        and value['provisional_preferred_id'] == owner['candidate_id'], 'report-identity')
    require(value['technical_round_summaries'] == value['learner_round_summaries']
        == value['permitted_administrative_counts'] == [] and value['qualifying_technical_round_id']
        == value['qualifying_learner_round_id'] == 'none', 'pending-human-evidence')
    require(value['accepted_limitations'] == sorted(owner['report']['limitations']), 'limitations')
    for key, kind, paths in (
        ('semantic_input_identities','semantic_input',owner['report']['semantic_paths']),
        ('spec_policy_limit_source_lock_identities','normative_owner',owner['report']['normative_paths'])):
        rows = value[key]
        require(type(rows) is list and len(rows) == len(paths), 'source-identities')
        for row, path in zip(rows, sorted(paths), strict=True):
            shape(row, ('kind','name','sha256'))
            require(row['kind'] == kind and row['name'] == path, 'source-identity-role')
            _hash(row['sha256'])
    candidates = value['candidate_rows']
    require(type(candidates) is list and len(candidates) == 1, 'report-candidates')
    candidate = shape(candidates[0], ('candidate_id','tuple_identity','policy_identity','complexity_class',
        'metrics','hard_gates','disposition','reason_code','reason'))
    require(candidate['candidate_id'] == owner['candidate_id'] and candidate['complexity_class'] == 'C1'
        and candidate['disposition'] == 'preferred' and candidate['reason_code'] == owner['report']['reason_code']
        and candidate['reason'] == owner['report']['reason'], 'candidate-domain')
    _hash(candidate['tuple_identity']); _hash(candidate['policy_identity'])
    for number in shape(candidate['metrics'], owner['metrics']['keys']).values():
        uint(number)
    gates = shape(candidate['hard_gates'], owner['report']['hard_gate_keys'])
    require(list(gates.get(key) for key in owner['report']['hard_gate_keys']) == ['pass']*8+['not_evaluated'], 'report-gates')
    steps = value['selection_steps']
    require(type(steps) is list and len(steps) == 6, 'report-selection')
    for row, step in zip(steps, owner['selection']['step_order'], strict=True):
        shape(row,owner['selection']['step_keys'])
        require(row['step'] == step and row['surviving_before'] == row['outcome'] == [owner['candidate_id']], 'report-step')
        _hash(row['evidence_sha256'])
    capacity = shape(value['provisional_capacity_envelope'], (
        'profile_limits_sha256','semantic_envelope_sha256','side_search_policy_sha256','retained_ledger_identities'))
    for key in ('profile_limits_sha256','semantic_envelope_sha256','side_search_policy_sha256'):
        _hash(capacity[key])
    ledger_rows = capacity['retained_ledger_identities']
    require(type(ledger_rows) is list and len(ledger_rows) == 8, 'report-ledgers')
    for row, kind in zip(ledger_rows, sorted(owner['report']['ledger_kinds']), strict=True):
        shape(row, ('kind','name','sha256'))
        require(row['kind'] == kind and row['name'] == owner['candidate_id'], 'report-ledger-role')
        _hash(row['sha256'])
    carrier = shape(value['preferred_carrier_identity_and_density'], (
        'candidate_id','carrier_sha256','ownership_ledger_sha256','density_ledger_sha256','N','S','W'))
    require(carrier['candidate_id'] == owner['candidate_id'] and uint(carrier['N']) == uint(carrier['S'])**2
        and 64 <= carrier['S'] <= 2048 and carrier['S'] % 8 == 0 and 8 <= uint(carrier['W']) <= 128
        and carrier['W'] % 8 == 0, 'report-geometry')
    for key in ('carrier_sha256','ownership_ledger_sha256','density_ledger_sha256'):
        _hash(carrier[key])
    damage = value['damage_summary_D0_through_D7']
    require(type(damage) is list and len(damage) == 8, 'report-damage')
    for i, row in enumerate(damage):
        shape(row, ('candidate_id','family_id','manifest_sha256','guarantee_id','result','wrong_accept_count'))
        require(row['candidate_id'] == owner['candidate_id'] and row['family_id'] == 'D'+str(i)
            and row['guarantee_id'] == _guarantee(i) and row['result'] == 'pass'
            and uint(row['wrong_accept_count']) == 0, 'report-damage-row')
        _hash(row['manifest_sha256'])
    cross = shape(value['cross_language_and_linux_results'], (
        'evidence_source_projection_sha256','host_full','linux_full','execution_snapshots_equal',
        'canonical_bytes_equal','states_equal','ledgers_equal'))
    _hash(cross['evidence_source_projection_sha256'])
    require(cross['host_full'] == cross['linux_full'] == 'pass' and all(cross[k] is True for k in (
        'execution_snapshots_equal','canonical_bytes_equal','states_equal','ledgers_equal')), 'report-linux')
    pilot = shape(value['m2_pilot_envelope'], owner['report']['pilot_keys'])
    require(pilot['profile_id'] == owner['candidate_id'] and pilot['state'] == 'validation-pending', 'pilot-state')
    for key in set(pilot)-{'profile_id','state'}:
        _hash(pilot[key])
    rows = value['generated_evidence_hashes']
    require(type(rows) is list and 1 <= len(rows) <= 4393, 'generated-identities')
    previous = ('','')
    for row in rows:
        shape(row, ('kind','name','sha256'))
        require(row['kind'] in ('generated_file','generated_manifest') and _path(row['name'])
            and previous < (row['kind'],row['name']), 'generated-identity-order')
        previous = (row['kind'],row['name']); _hash(row['sha256'])
    return value


def _guarantee(index):
    return ('all_declared_m2_sections_exact' if index in (0,1,5) else
            'correct_or_explicit_failure' if index == 7 else 'm2_required_closure')


def _bundle_files(owner, kind, source_rows, source_hash, candidate_hash, recovery_hash, content_hash, read):
    contract = owner[kind+'_bundle']
    path = 'artifacts/gate8/bundles/'+kind+'-v2.json'
    raw = _raw(read,path)
    value = _json(raw,owner['bundle_common']['schema'],owner['bundle_common']['keys'])
    require(value['bundle_id'] == contract['bundle_id'] and value['profile_id'] == owner['candidate_id']
        and value['source_projection_sha256'] == source_hash and value['candidate_manifest_sha256'] == candidate_hash
        and value['recovery_provenance_sha256'] == recovery_hash and value['content_stream_sha256'] == content_hash, 'bundle-context')
    files = {}
    for group in ('participant','owner'):
        rows = value[group+'_files']
        roles, paths = contract[group+'_roles'], contract[group+'_paths']
        require(type(rows) is list and len(rows) == len(paths), 'bundle-file-count')
        for row,role,p in zip(rows,roles,paths,strict=True):
            shape(row,owner['bundle_common']['file_keys'])
            require(row['role_id'] == role and row['path'] == p, 'bundle-role-path')
            payload = _raw(read,'artifacts/gate8/bundles/'+kind+'/'+p,owner['bounds']['bundle_file_bytes'])
            _match_row({k:v for k,v in row.items() if k != 'role_id'},payload,mode=True)
            files[p] = payload
    expected = []; offset = 0
    for i,(release,count) in enumerate(zip(contract['release_ids'],contract['release_counts'],strict=True)):
        expected.append(dict(ordinal=i,release_id=release,participant_role_ids=list(contract['participant_roles'][offset:offset+count])))
        offset += count
    require(manifest.serialize_manifest(dict(rows=value['release_rows'])) == manifest.serialize_manifest(dict(rows=expected)), 'bundle-releases')
    roles = dict(zip((*contract['participant_roles'],*contract['owner_roles']),
                     (*contract['participant_paths'],*contract['owner_paths']),strict=True))
    for role,path in contract['literal_sources'].items():
        require(path in source_rows and source_rows[path]['byte_length'] == len(files[roles[role]])
            and source_rows[path]['sha256'] == digest(files[roles[role]]), 'bundle-literal-source')
    row = dict(bundle_id=contract['bundle_id'],manifest_bytes=len(raw),manifest_sha256=digest(raw),
               file_rows=value['participant_files']+value['owner_files'])
    return raw,files,row


def render_candidate_ready_report_v2(policy, roadmap_raw, source_raw, selection_raw, generated_raw,
        candidate_read, gate8_read, source_read, damage_paths, acquisition_raw, *,
        preflight, candidate_names, gate8_names):
    """Admit complete retained bindings and render; caller owns fresh execution.

    candidate_read accepts candidate-relative paths; gate8_read/source_read
    accept repository-relative paths. preflight is the fresh source construction
    and recovery context, never deserialized from retained files. Names are the
    actual recursive inventories, with generated manifest included in Gate8.
    """
    from .m2_complete_damage_v2 import admit_complete_damage_v2
    from .m2_gate8_receipts_v2 import (admit_producer_receipt_v2, validate_cross_language_v2,
                                     admit_linux_attestation_v2)
    from .m2_receiver_bounds_v2 import derive_receiver_bounds_v2, validate_measured_bounds_v2
    from .m2_gate8_evidence_v2 import gate8_paths_v2, validate_generated_evidence_v2
    from .m2_preflight_v2 import PreflightV2, SourceCandidateV2, SOURCE_PATHS
    from tools.m2.package_participant_v2 import render_bundle_preimages_v2
    owner = _document(policy)
    require(type(preflight) is PreflightV2 and type(preflight.source) is SourceCandidateV2, 'fresh-preflight-context')
    source_inputs = dict(preflight.source.inputs)
    require(len(preflight.source.inputs) == len(source_inputs) == len(SOURCE_PATHS)
        and set(source_inputs) == set(SOURCE_PATHS) and all(
            _raw(source_read,p,owner['bounds']['source_file_bytes']) == raw for p,raw in source_inputs.items()), 'preflight-source-binding')
    require(type(candidate_names) is tuple and candidate_names == result_file_paths_v2(policy,damage_paths)
        and type(gate8_names) is tuple and gate8_names == gate8_paths_v2(policy), 'recursive-inventory')
    core = dict(preflight.files)
    expected_core = set(owner['candidate_files']['fixed'])-{'bundle-preimages.json','independence-proof.json'}
    require(len(preflight.files) == len(core) == 22 and set(core) == expected_core
        and all(_raw(candidate_read,p) == raw for p,raw in core.items()), 'fresh-preflight-bytes')
    validate_generated_evidence_v2(generated_raw,policy,source_raw,damage_paths,candidate_read,gate8_read,
        candidate_names=candidate_names,
        gate8_names=tuple(p for p in gate8_names if p != owner['generated_evidence']['path']))
    require(_raw(gate8_read,owner['generated_evidence']['path']) == generated_raw, 'generated-manifest-preimage')
    source = admit_source_projection_v2(source_raw,policy)
    source_rows = {row['path']:row for row in source['entries']}
    for path,row in source_rows.items():
        raw = _raw(source_read,path,owner['bounds']['source_file_bytes'],allow_empty=True)
        require(row['byte_length'] == len(raw) and row['sha256'] == digest(raw), 'source-preimage')
    require(_raw(source_read,'spec/gate8-policy-v2.toml') == policy._raw
        and source['roadmap_normative_sha256'] == roadmap_normative_sha256(roadmap_raw), 'source-owner-roadmap')
    read = lambda p: _raw(candidate_read,p)
    raw4 = tuple(read(p) for p in ('candidate-manifest.json','capacity-ledger.json','ownership-ledger.json','semantic-envelope.json'))
    damage_raw, measured_raw = admit_complete_damage_v2(*raw4,preflight.source.corpus,candidate_read,damage_paths)
    require(damage_raw == read('damage/manifest.json') and measured_raw == read('resource-limits.json'), 'damage-recomputation')
    damage = _json(damage_raw)
    require(damage['result'] == 'pass' and uint(damage['wrong_accept_count']) == 0, 'damage-pass')
    metrics = derive_candidate_metrics_v2(policy,candidate_read)
    static = _json(read('static-limits.json'))
    require(static['realism'] == dict(result='pass',failures=[]), 'static-realism-pass')
    known = _json(read('known-answer-manifest.json'),owner['known_answer']['schema'],owner['known_answer']['keys'])
    grammar = _json(read('grammar-state-manifest.json'),owner['grammar_state']['schema'],owner['grammar_state']['keys'])
    require(known['profile_id'] == grammar['profile_id'] == owner['candidate_id']
        and manifest.serialize_manifest(known['summary']) == manifest.serialize_manifest(dict(
            route_count=4,example_count=128,result='pass'))
        and manifest.serialize_manifest(grammar['summary']) == manifest.serialize_manifest(dict(
            boundary_case_count=21,boundary_kat_count=4,result='pass')), 'preflight-gate-results')
    bound_paths = ('spec/profile-policy-v2.toml','spec/profile-limits-v2.toml','spec/damage-policy-v2.toml',
                   'spec/resource-accounting-v2.md','spec/receiver-bounds-v2.md')
    bound_owners = tuple(_raw(source_read,p) for p in bound_paths)
    require(read('receiver-bounds.json') == derive_receiver_bounds_v2(*bound_owners), 'analytic-bound-source')
    validate_measured_bounds_v2(measured_raw,*bound_owners)
    validate_measured_bounds_v2(read('preflight-resource-limits.json'),*bound_owners)
    receipts = {p:_raw(gate8_read,owner['producer_receipt']['path'].format(producer_id=p))
                for p in owner['producer_receipt']['producer_order']}
    for raw in receipts.values():
        receipt = admit_producer_receipt_v2(raw,policy,source_raw,damage_paths,source_read=source_read)
        for row in receipt['file_rows']:
            _match_row(row,read(row['path']),mode=True)
    cross_raw = _raw(gate8_read,owner['cross_language']['path'])
    cross = validate_cross_language_v2(cross_raw,policy,source_raw,receipts,damage_paths,source_read=source_read)
    require(cross['result'] == 'pass', 'cross-language-pass')
    linux = admit_linux_attestation_v2(_raw(gate8_read,owner['linux']['attestation_path']),
        policy,source_raw,receipts,damage_paths,acquisition_raw,source_read=source_read)
    def evidence_read(path):
        prefix = owner['authority']['candidate_root']+'/'
        return candidate_read(path[len(prefix):]) if path.startswith(prefix) else (
            gate8_read(path) if path.startswith('artifacts/gate8/') else source_read(path))
    selected = _json(selection_raw,owner['selection']['schema'],owner['selection']['keys'])
    selection = validate_selection_v2(selection_raw,policy,bound_owners[0],cross_raw,
        selected['gate_rows'],evidence_read,damage_paths)
    require(selection['retained_finalist_ids'] == [owner['candidate_id']]
        and _raw(gate8_read,owner['selection']['path']) == selection_raw, 'selection-pass')
    proof = _json(read('independence-proof.json'),'golden-board.m2-independence-proof/v2',(
        'schema','profile_id','input_sha256','physical_evidence','recovery_provenance','knowledge_use',
        'first_use','damage_manifest','predicate_rows','result'))
    from .m2_physical_v2 import build_physical_evidence_v2
    from .m2_independence_v2 import damage_binding_predicate
    physical_raw = build_physical_evidence_v2(*raw4)
    physical = _json(physical_raw)
    physical_inputs = admit_physical_inputs(*raw4)
    expected_predicates = physical['predicate_rows']+[damage_binding_predicate(damage,physical_inputs.count)]
    require(proof['profile_id'] == owner['candidate_id'] and proof['input_sha256'] == physical['input_sha256']
        and proof['result'] == 'pass' and manifest.serialize_manifest(dict(rows=proof['predicate_rows'])) ==
            manifest.serialize_manifest(dict(rows=expected_predicates))
        and all(row['result'] == 'pass' and uint(row['witness_count']) > 0 and uint(row['violation_count']) == 0
                for row in proof['predicate_rows']), 'independence-proof')
    for role,raw in [('physical_evidence',physical_raw),('damage_manifest',damage_raw),
        *[(r,read(p)) for r,p in (('recovery_provenance','recovery-provenance.json'),
                                 ('knowledge_use','knowledge-use.json'),('first_use','first-use.json'))]]:
        require(proof[role] == dict(bytes=len(raw),sha256=digest(raw)), 'proof-preimage')
    recovery_raw = read('recovery-provenance.json')
    recovery = _json(recovery_raw,'golden-board.m2-recovery-provenance/v2')
    require(recovery['result'] == 'pass' and recovery['profile_id'] == owner['candidate_id'], 'recovery-result')
    required,all_stream = read('m2-required.content-v0.bin'),read('m2-all.content-v0.bin')
    bundles = [_bundle_files(owner,kind,source_rows,digest(source_raw),digest(raw4[0]),digest(recovery_raw),
        digest(all_stream if kind == 'technical' else required),gate8_read) for kind in ('technical','learner')]
    regenerated_preimages = render_bundle_preimages_v2(policy,tuple(
        (kind,files,raw) for kind,(raw,files,_) in zip(('technical','learner'),bundles,strict=True)),
        source_raw,preflight,source_read=source_read)
    require(read('bundle-preimages.json') == regenerated_preimages, 'fresh-bundle-context')
    from .m2_learner_assessment_v2 import validate_learner_assessment_v2
    validate_learner_assessment_v2(bundles[1][1]['owner/semantic-evaluation.json'],required,
        _raw(source_read,'studies/m2/learner-assessment-v2.toml'),_raw(source_read,'conformance/chess-v0.json'),
        _raw(source_read,'reports/game-set-v0.bin'))
    expected_preimages = dict(schema=owner['bundle_preimages']['schema'],profile_id=owner['candidate_id'],
        source_projection_sha256=digest(source_raw),bundle_rows=[b[2] for b in bundles])
    require(read('bundle-preimages.json') == manifest.serialize_manifest(expected_preimages), 'bundle-preimages')
    generated = _json(generated_raw,owner['generated_evidence']['schema'],owner['generated_evidence']['keys'])
    require(generated['source_projection_sha256'] == digest(source_raw), 'generated-source')
    candidate_paths = result_file_paths_v2(policy,damage_paths)
    prefix = owner['authority']['candidate_root']+'/'
    gate8_paths = set(owner['lifecycle']['fixed_gate8_files'])-{owner['generated_evidence']['path']}
    for kind,(_,files,_) in zip(('technical','learner'),bundles,strict=True):
        gate8_paths.update('artifacts/gate8/bundles/'+kind+'/'+p for p in files)
    for key,paths,read_file in (
        ('candidate_file_rows',tuple(prefix+p for p in candidate_paths),lambda p:candidate_read(p[len(prefix):])),
        ('gate8_file_rows',tuple(sorted(gate8_paths)),gate8_read)):
        rows = generated[key]
        require(type(rows) is list and len(rows) == len(paths), 'generated-coverage')
        for row,path in zip(rows,paths,strict=True):
            require(type(row) is dict and row.get('path') == path, 'generated-path-order')
            _match_row(row,_raw(read_file,path,owner['bounds']['bundle_file_bytes']),mode=True)
    require(_raw(gate8_read,owner['source_projection']['path']) == source_raw, 'generated-source-preimage')
    generated_hashes = [dict(kind='generated_file',name=row['path'],sha256=row['sha256'])
        for key in ('candidate_file_rows','gate8_file_rows') for row in generated[key]]
    generated_hashes.append(dict(kind='generated_manifest',name=owner['generated_evidence']['path'],sha256=digest(generated_raw)))
    generated_hashes.sort(key=lambda r:(r['kind'],r['name']))
    def identities(kind,paths):
        require(all(path == 'roadmap-normative-v0' or path in source_rows for path in paths), 'report-source-coverage')
        return [dict(kind=kind,name=path,sha256=source['roadmap_normative_sha256'] if path == 'roadmap-normative-v0'
                     else source_rows[path]['sha256']) for path in sorted(paths)]
    ledger_rows = sorted((dict(kind=kind,name=owner['candidate_id'],sha256=digest(read(path)))
        for kind,path in zip(owner['report']['ledger_kinds'],owner['report']['ledger_paths'],strict=True)), key=lambda r:(r['kind'],r['name']))
    candidate_row = dict(candidate_id=owner['candidate_id'],tuple_identity=digest(manifest.serialize_manifest(dict(
        schema='golden-board.m2-profile-tuple/v2',candidate=_profile(bound_owners[0],owner)['candidate']))),
        policy_identity=digest(bound_owners[0]),complexity_class='C1',metrics=metrics,
        hard_gates=dict(zip(owner['report']['hard_gate_keys'],['pass']*8+['not_evaluated'],strict=True)),
        disposition='preferred',reason_code=owner['report']['reason_code'],reason=owner['report']['reason'])
    damage_rows = [dict(candidate_id=owner['candidate_id'],family_id='D'+str(i),
        manifest_sha256=digest(read(f'damage/D{i}/manifest.json')),guarantee_id=_guarantee(i),
        result=row['result'],wrong_accept_count=row['wrong_accept_count']) for i,row in enumerate(damage['family_rows'])]
    result = dict(schema=owner['report']['schema'],roadmap_revision=11,
        m1_repository_baseline=owner['report']['m1_repository_baseline'],
        semantic_input_identities=identities('semantic_input',owner['report']['semantic_paths']),
        spec_policy_limit_source_lock_identities=identities('normative_owner',owner['report']['normative_paths']),
        candidate_rows=[candidate_row],retained_finalist_ids=selection['retained_finalist_ids'],
        provisional_preferred_id=selection['provisional_preferred_id'],selection_steps=selection['selection_steps'],
        provisional_capacity_envelope=dict(profile_limits_sha256=digest(read('receiver-bounds.json')),
            semantic_envelope_sha256=digest(raw4[3]),side_search_policy_sha256=digest(read('geometry-search.json')),
            retained_ledger_identities=ledger_rows),
        preferred_carrier_identity_and_density=dict(candidate_id=owner['candidate_id'],
            carrier_sha256=digest(read('carrier.bin')),ownership_ledger_sha256=digest(raw4[2]),
            density_ledger_sha256=digest(read('density-ledger.json')),N=physical_inputs.side**2,
            S=physical_inputs.side,W=physical_inputs.width),damage_summary_D0_through_D7=damage_rows,
        cross_language_and_linux_results=dict(evidence_source_projection_sha256=digest(source_raw),
            host_full=linux['host_full'],linux_full=linux['linux_full'],
            execution_snapshots_equal=linux['execution_snapshots_equal'],canonical_bytes_equal=linux['canonical_bytes_equal'],
            states_equal=True,ledgers_equal=True),technical_round_summaries=[],qualifying_technical_round_id='none',
        learner_round_summaries=[],qualifying_learner_round_id='none',permitted_administrative_counts=[],
        accepted_limitations=sorted(owner['report']['limitations']),generated_evidence_hashes=generated_hashes,
        m2_pilot_envelope=dict(profile_id=owner['candidate_id'],source_projection_sha256=digest(source_raw),
            candidate_manifest_sha256=digest(raw4[0]),recovery_provenance_sha256=digest(recovery_raw),
            technical_bundle_sha256=digest(bundles[0][0]),learner_bundle_sha256=digest(bundles[1][0]),
            required_stream_sha256=digest(required),all_stream_sha256=digest(all_stream),
            generated_evidence_sha256=digest(generated_raw),state='validation-pending'))
    raw = manifest.serialize_manifest(result)
    _report_shape(raw,owner)
    render_candidate_ready_roadmap_v2(policy,roadmap_raw,raw)
    return raw


def validate_candidate_ready_report_v2(raw,*args,**kwargs):
    require(type(raw) is bytes and raw == render_candidate_ready_report_v2(*args,**kwargs), 'report-recomputation')
    return manifest.validate_canonical_manifest(raw)


def render_candidate_ready_roadmap_v2(policy, roadmap_raw, report_raw):
    """Render status-last bytes only; caller must admit the complete report."""
    owner = _document(policy)
    report = _report_shape(report_raw, owner)
    require(type(roadmap_raw) is bytes and 0 < len(roadmap_raw) <= 8388608
        and roadmap_raw.endswith(b'\n') and b'\r' not in roadmap_raw, 'roadmap-bytes')
    normative = roadmap_normative_sha256(roadmap_raw)
    virtual = [r for r in report['spec_policy_limit_source_lock_identities']
               if type(r) is dict and r.get('name') == 'roadmap-normative-v0']
    require(virtual == [dict(kind='normative_owner',name='roadmap-normative-v0',sha256=normative)], 'roadmap-source')
    lines = roadmap_raw.splitlines(keepends=True)
    require(lines.count(b'| Roadmap revision | 11 |\n') == 1
        and sum(line.startswith(b'| Roadmap revision | ') for line in lines) == 1, 'roadmap-revision')
    before = b'| Project state | In progress |\n'
    after = b'| Project state | Candidate ready |\n'
    milestone = '| Current milestone | M2 — Full-carrier bootstrap and transport feasibility |\n'.encode()
    row_before = '| M2 — Full-carrier bootstrap and transport feasibility | In progress | '.encode()
    row_after = ('| M2 — Full-carrier bootstrap and transport feasibility | '+owner['lifecycle']['m2_status']+' | ').encode()
    tail = owner['lifecycle']['pre_ready_tail'].encode()
    replacement = owner['lifecycle']['candidate_ready_tail'].format(
        candidate_id=owner['candidate_id'],report_sha256=digest(report_raw)).encode()
    matches = [i for i,line in enumerate(lines) if line.startswith(row_before)]
    require(lines.count(before) == 1 and lines.count(milestone) == 1 and len(matches) == 1
        and sum(line.startswith(b'| Project state | ') for line in lines) == 1
        and roadmap_raw.count(tail) == 1 and lines[matches[0]].endswith(tail+b' |\n'), 'roadmap-precondition')
    require(sum(line.startswith('| M2 — Full-carrier bootstrap and transport feasibility | '.encode())
                for line in lines) == 1, 'roadmap-duplicate-milestone')
    offset = sum(map(len,lines[:matches[0]]))
    require(roadmap_raw.index(b'## 13. Project status') < offset < roadmap_raw.index(b'## 14. Adversarial stress matrix'), 'roadmap-status-location')
    lines[matches[0]] = lines[matches[0]].replace(row_before,row_after,1).replace(tail,replacement,1)
    result = b''.join(lines).replace(before,after,1)
    require(roadmap_normative_sha256(result) == normative, 'roadmap-normative-preservation')
    return result


def validate_candidate_ready_roadmap_v2(policy, before_raw, after_raw, report_raw):
    require(type(after_raw) is bytes and after_raw == render_candidate_ready_roadmap_v2(
        policy,before_raw,report_raw), 'roadmap-transition-binding')
