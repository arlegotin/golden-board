"""Closed source contract for revised Gate8; loading is not gate admission.

The inventory helpers check only the declared filename/row contract. A caller
must first run complete-damage admission and independently validate each role.
No execution, promotion, participant result or filesystem write occurs here.
"""
from dataclasses import dataclass, field
from hashlib import sha256
import re
from types import MappingProxyType
from typing import Mapping
import tomllib

GATE8_POLICY_V2_SHA256 = '366271004d3700b908c6ba8d86a16b81d740e0e186e45fb871026bfef83258d6'
_PROFILE = 'eh72-hier-r5-r2-r1-lzss-crc32c-v1'
_SECTIONS = ('authority', 'bounds', 'candidate_files', 'gates', 'known_answer',
    'grammar_state', 'preflight_resources', 'source_projection', 'producer_receipt',
    'cross_language', 'bundle_preimages', 'linux', 'selection', 'metrics', 'bundle_common',
    'technical_bundle', 'learner_bundle', 'report', 'generated_evidence', 'lifecycle')
_FAMILIES = ('D0', 'D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7', 'B0')
_SHARD = re.compile(r'damage/(D[0-7]|B0)/([0-9]{6})\.json\Z', re.ASCII)


class Gate8PolicyV2Error(ValueError):
    pass


def _require(ok, reason):
    if not ok:
        raise Gate8PolicyV2Error(reason)


def _freeze(value):
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class Gate8PolicyV2:
    sha256: str
    document: Mapping[str, object]
    _raw: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class ResultFileV2:
    path: str
    mode: str
    bytes: int
    sha256: str


def _path(value):
    return (type(value) is str and 1 <= len(value) <= 255
        and all(32 <= ord(c) <= 126 for c in value) and '\\' not in value
        and all(part not in ('', '.', '..') for part in value.split('/')))


def _paths(values):
    return (type(values) in (list, tuple) and all(_path(p) for p in values)
            and list(values) == sorted(set(values)))


def _shape(value):
    _require(set(value) == {'schema', 'policy_version', 'status', 'candidate_id',
                           'outcome_values_present', 'scope', *_SECTIONS}, 'owner-keys')
    _require(value['schema'] == 'golden-board.m2-gate8-policy/v2'
        and type(value['policy_version']) is int and value['policy_version'] == 2
        and value['candidate_id'] == _PROFILE
        and value['status'] == 'source-contract; no-production-result'
        and value['outcome_values_present'] is False, 'owner-domain')
    _require(all(type(value[name]) is dict for name in _SECTIONS), 'owner-tables')
    bounds = value['bounds']
    for key, item in bounds.items():
        if key not in ('integer', 'file_type', 'modes', 'path', 'hash', 'limits_scope'):
            _require(type(item) is int and 0 < item <= (1 << 64) - 1, 'owner-bound')
    _require(bounds['carrier_bits'] == 4194304 and bounds['carrier_file_bytes'] == 524292
        and bounds['canonical_json_bytes'] == 1048576, 'neutral-ceiling')
    _require(value['gates']['order'] == list(range(1, 9)), 'gate-order')
    _require(value['candidate_files']['damage_families'] == list(_FAMILIES), 'damage-order')
    fixed = value['candidate_files']['fixed']
    _require(_paths(fixed) and len(fixed) == 24, 'candidate-paths')
    _require(_paths(value['report']['normative_paths'])
        and _paths(value['lifecycle']['fixed_gate8_files']), 'projection-paths')
    _require(len(value['metrics']['keys']) == len(set(value['metrics']['keys'])) == 23,
             'metric-keys')
    _require(value['producer_receipt']['producer_order'] ==
        ['native-python', 'native-rust', 'linux-python', 'linux-rust'], 'producer-order')
    for name in ('technical_bundle', 'learner_bundle'):
        bundle = value[name]
        roles = bundle['participant_roles'] + bundle['owner_roles']
        paths = bundle['participant_paths'] + bundle['owner_paths']
        _require(len(roles) == len(set(roles)) == len(paths) == len(set(paths))
            and all(_path(path) for path in paths)
            and len(bundle['release_ids']) == len(bundle['release_counts'])
            and all(type(n) is int and n > 0 for n in bundle['release_counts'])
            and sum(bundle['release_counts']) == len(bundle['participant_roles']), 'bundle-roles')


def load_gate8_policy_v2(raw: bytes) -> Gate8PolicyV2:
    """Admit only this exact bounded source owner, returning immutable values."""
    _require(type(raw) is bytes and 0 < len(raw) <= 65536, 'owner-bound')
    _require(sha256(raw).hexdigest() == GATE8_POLICY_V2_SHA256, 'owner-identity')
    try:
        value = tomllib.loads(raw.decode('utf-8'))
    except (UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise Gate8PolicyV2Error('owner-toml') from exc
    _shape(value)
    return Gate8PolicyV2(GATE8_POLICY_V2_SHA256, _freeze(value), raw)


def _document(policy):
    # Parsed wrappers are publicly constructible; never trust a forged document.
    _require(type(policy) is Gate8PolicyV2, 'policy-type')
    return load_gate8_policy_v2(policy._raw).document


def result_file_paths_v2(policy: Gate8PolicyV2, damage_paths: tuple[str, ...]) -> tuple[str, ...]:
    """Join exact fixed roles to an ALREADY ADMITTED complete-damage inventory.

    This helper rejects unknown/gapped path sets, but cannot prove greedy shard
    boundaries or semantic coverage without the complete-damage documents.
    """
    document = _document(policy)
    _require(type(damage_paths) is tuple and len(damage_paths) <= 4096
             and _paths(damage_paths), 'damage-path-order')
    mandatory = {'resource-limits.json', 'damage/manifest.json', 'damage/boundary-kats.json',
                 *(f'damage/{family}/manifest.json' for family in _FAMILIES)}
    _require(mandatory <= set(damage_paths), 'damage-path-coverage')
    ordinals = {family: [] for family in _FAMILIES}
    for path in damage_paths:
        if path in mandatory:
            continue
        match = _SHARD.fullmatch(path)
        _require(match is not None, 'damage-path-domain')
        ordinals[match[1]].append(int(match[2]))
    _require(all(rows and rows == list(range(len(rows))) for rows in ordinals.values()),
             'damage-shard-order')
    fixed = document['candidate_files']['fixed']
    _require(not set(fixed).intersection(damage_paths), 'candidate-path-overlap')
    paths = tuple(sorted((*fixed, *damage_paths)))
    _require(len(paths) <= document['bounds']['candidate_files'], 'candidate-path-count')
    return paths


def validate_result_file_rows_v2(policy: Gate8PolicyV2, rows: tuple[dict, ...],
                                 damage_paths: tuple[str, ...]) -> tuple[ResultFileV2, ...]:
    """Validate receipt inventory structure, never file bytes or gate outcomes."""
    document = _document(policy)
    paths = result_file_paths_v2(policy, damage_paths)
    _require(type(rows) is tuple and len(rows) == len(paths), 'file-row-count')
    output, total = [], 0
    for path, row in zip(paths, rows, strict=True):
        _require(type(row) is dict and set(row) == {'path', 'mode', 'bytes', 'sha256'}, 'file-row')
        _require(type(row['path']) is str and row['path'] == path
                 and row['mode'] == '100644', 'file-path-mode')
        maximum = 1048576
        if path == 'carrier.bin':
            maximum = document['bounds']['carrier_file_bytes']
        elif path in ('route-0.bin', 'route-1.bin', 'route-2.bin', 'route-3.bin'):
            maximum = document['bounds']['route_prefix_bytes']
        elif _SHARD.fullmatch(path):
            maximum = 524288
        _require(type(row['bytes']) is int and 0 < row['bytes'] <= maximum, 'file-bytes')
        digest = row['sha256']
        _require(type(digest) is str and len(digest) == 64
                 and all(c in '0123456789abcdef' for c in digest), 'file-hash')
        total += row['bytes']
        _require(total <= document['bounds']['candidate_aggregate_bytes'], 'file-total')
        output.append(ResultFileV2(path, row['mode'], row['bytes'], digest))
    return tuple(output)
