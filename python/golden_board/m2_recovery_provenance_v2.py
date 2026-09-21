"""Bound actual OBS_BITS recovery to finite carried-knowledge evidence."""
from dataclasses import dataclass
from hashlib import sha256

from . import bootstrap, bootstrap_v2, canonical_manifest as manifest
from .body_codec_v1 import decode_body
from .m2_decoder_v2 import ObservationDecoderV2
from .m2_first_use_v2 import build_first_use_v2
from .m2_knowledge_v2 import build_knowledge_use_v2
from .m2_physical_v2 import admit_physical_inputs

PROFILE = 'eh72-hier-r5-r2-r1-lzss-crc32c-v1'
BODY_IDS = (16, 17, 18, *range(100, 164), *range(200, 211))
POLICIES = ('spec/profile-policy-v2.toml', 'spec/profile-limits-v2.toml',
            'spec/damage-policy-v2.toml')


class RecoveryProvenanceError(ValueError):
    pass


def _require(ok, reason):
    if not ok:
        raise RecoveryProvenanceError(reason)


def _hash(raw):
    return sha256(raw).hexdigest()


def _identity(raw):
    return dict(bytes=len(raw), sha256=_hash(raw))


def _bounded(raw, maximum=1048576):
    _require(type(raw) is bytes and 0 < len(raw) <= maximum, 'input-bound')


@dataclass(frozen=True, slots=True)
class RecoveredBody:
    section_id: int
    section_version: int
    envelope: bytes
    stored_payload: bytes
    decoded_payload: bytes


@dataclass(frozen=True, slots=True)
class RecoveryProvenance:
    value: bytes
    decoder_result: bytes
    knowledge_use: bytes
    first_use: bytes
    prefixes: tuple[bytes, bytes, bytes, bytes]
    required_stream: bytes
    all_stream: bytes
    bodies: tuple[RecoveredBody, ...]


def _extract(raw, side, width, sector, count):
    out = bytearray(count)
    for offset in range(count * 8):
        row, col = bootstrap.sector_cell(side, width, sector, offset)
        flat = row * side + col
        out[offset // 8] |= ((raw[4 + flat // 8] >> (7 - flat % 8)) & 1) << (7 - offset % 8)
    return bytes(out)


def _build(carrier_raw, candidate_raw, capacity_raw, ownership_raw, semantic_raw,
           profile_policy_raw, profile_limits_raw, damage_policy_raw):
    _bounded(carrier_raw, 524292)
    for raw in (candidate_raw, capacity_raw, ownership_raw, semantic_raw,
                profile_policy_raw, profile_limits_raw, damage_policy_raw):
        _bounded(raw)
    context = admit_physical_inputs(candidate_raw, capacity_raw, ownership_raw, semantic_raw)
    candidate = manifest.validate_canonical_manifest(candidate_raw)
    files = {r['path']: r for r in candidate['files']}
    _require(_identity(carrier_raw) == {k: files['carrier.bin'][k] for k in ('bytes', 'sha256')}, 'carrier-binding')
    side, width = context.side, context.width
    _require(int.from_bytes(carrier_raw[:4], 'big') == side * side and
             len(carrier_raw) == 4 + side * side // 8, 'carrier-geometry')
    policy_raw = (profile_policy_raw, profile_limits_raw, damage_policy_raw)
    for raw, key in zip(policy_raw, ('profile_policy_sha256', 'profile_limits_source_sha256', 'damage_policy_sha256')):
        _require(_hash(raw) == candidate['source_identities'][key], 'policy-binding')
    decoder = ObservationDecoderV2(*policy_raw)
    result = decoder.decode('OBS_BITS', carrier_raw)
    _require(result.profile_id == PROFILE and result.inventory_available and result.artifact_state == 'exact', 'recovery')
    expected = {r['section_id']: r for r in context.sections}
    _require(len(result.section_results) == len(expected) and
             {r.section_id for r in result.section_results} == set(expected), 'section-set')
    hypotheses = result.accepted_hypotheses
    _require(len(hypotheses) == 4 and
             {(h.transform_id, h.polarity_id, h.sector_id, h.profile_id) for h in hypotheses} ==
             {(0, 0, s, PROFILE) for s in range(4)}, 'hypotheses')
    mapping_hash = _hash(manifest.serialize_manifest(context.ownership['mapping']))
    _require(all(h.mapping_sha256 == mapping_hash for h in hypotheses), 'mapping-binding')
    prefixes = []
    for sector in range(4):
        header = _extract(carrier_raw, side, width, sector, 64)
        cells = int.from_bytes(header[56:60], 'big')
        _require(512 <= cells <= 32768 * 8 and cells % 8 == 0 and cells <= width * (side - width), 'prefix-bound')
        prefix = _extract(carrier_raw, side, width, sector, cells // 8)
        row = files[f'route-{sector}.bin']
        _require(_identity(prefix) == {k: row[k] for k in ('bytes', 'sha256')} and
                 cells == context.shells[sector]['route_prefix_cells'], 'prefix-binding')
        prefixes.append(prefix)
    bodies = []
    inventory = None
    for recovered in sorted(result.section_results, key=lambda r: r.section_id):
        _require(recovered.state == 'verified' and type(recovered.envelope) is bytes, 'section-state')
        raw = recovered.envelope
        section = bootstrap.decode_section_envelope(raw)
        row = expected[recovered.section_id]
        for key in ('section_id', 'section_type', 'section_version', 'closure_class', 'check_id'):
            _require(getattr(section, key) == row[key], 'section-fields')
        _require(list(section.dependencies) == row['dependency_ids'] and
                 len(raw) == row['envelope_bytes'] and _hash(raw) == row['envelope_sha256'] and
                 len(section.payload) == row['stored_payload_bytes'] and _hash(section.payload) == row['payload_sha256'], 'section-binding')
        if section.section_id == 1:
            inventory = bootstrap_v2.decode_inventory(section.payload)
        if section.section_type == 3:
            decoded = decode_body(section.section_version, section.payload)
            _require(len(decoded) == row['decoded_payload_bytes'] and len(decoded) <= 16384, 'body-binding')
            bodies.append(RecoveredBody(section.section_id, section.section_version, raw, section.payload, decoded))
    _require(inventory is not None and {r.section_id for r in inventory.entries} == set(expected), 'inventory-binding')
    _require(tuple(b.section_id for b in bodies) == BODY_IDS and
             sum(len(b.decoded_payload) for b in bodies) <= 1048576, 'body-set')
    required, all_stream = result.m2_required_stream, result.m2_all_stream
    for raw, key in ((required, 'required_content_sha256'), (all_stream, 'all_content_sha256')):
        _bounded(raw)
        _require(len(raw) >= 4 and _hash(raw) == candidate['source_identities'][key], 'stream-binding')
    prefixes = tuple(prefixes)
    knowledge = build_knowledge_use_v2(prefixes, side=side, width=width,
        required_stream=required, all_stream=all_stream,
        body_payloads={b.section_id: b.decoded_payload for b in bodies})
    _require(all(r['mapping_sha256'] == mapping_hash for r in manifest.validate_canonical_manifest(knowledge)['route_rows']), 'knowledge-mapping')
    first_use = build_first_use_v2(prefixes, side=side, width=width)
    rendered = decoder.render_result('OBS_BITS', result)
    for raw in (rendered, knowledge, first_use):
        _bounded(raw)
    value = manifest.serialize_manifest(dict(
        schema='golden-board.m2-recovery-provenance/v2', profile_id=PROFILE,
        scope='actual-observation-to-carried-knowledge', result='pass',
        inputs={k: _identity(v) for k, v in zip(('carrier', 'candidate_manifest', 'capacity_ledger', 'ownership_ledger', 'semantic_envelope'),
            (carrier_raw, candidate_raw, capacity_raw, ownership_raw, semantic_raw))},
        policy_sha256={k: _hash(v) for k, v in zip(POLICIES, policy_raw)},
        geometry=dict(side=side, shell_width=width), decoder_result=_identity(rendered),
        prefix_rows=[dict(sector_id=s, **_identity(v)) for s, v in enumerate(prefixes)],
        stream_rows=[dict(section_id=s, **_identity(v)) for s, v in ((2, required), (3, all_stream))],
        body_rows=[dict(section_id=b.section_id, section_version=b.section_version,
            envelope=_identity(b.envelope), stored=_identity(b.stored_payload), decoded=_identity(b.decoded_payload)) for b in bodies],
        knowledge_use=_identity(knowledge), first_use=_identity(first_use)))
    _bounded(value)
    return RecoveryProvenance(value, rendered, knowledge, first_use, prefixes, required, all_stream, tuple(bodies))


def build_recovery_provenance_v2(carrier_raw, candidate_raw, capacity_raw, ownership_raw, semantic_raw,
                               profile_policy_raw, profile_limits_raw, damage_policy_raw):
    try:
        return _build(carrier_raw, candidate_raw, capacity_raw, ownership_raw, semantic_raw,
                      profile_policy_raw, profile_limits_raw, damage_policy_raw)
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise RecoveryProvenanceError(str(exc)) from exc


def validate_recovery_provenance_v2(raw, *inputs):
    _bounded(raw)
    _require(raw == build_recovery_provenance_v2(*inputs).value, 'provenance-binding')
