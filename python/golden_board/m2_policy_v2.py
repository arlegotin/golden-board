"""Exact source-owned development policy for observation-only profile8 work.

The pinned hashes identify the three reviewed source documents, not generated
measurements or passing evidence. There are deliberately no selected-geometry,
full damage, promotion, or Gate8 values. Historical loaders remain untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType
from typing import Mapping
import tomllib

from . import m2_codec, m2_policy


PROFILE_POLICY_SHA256 = '9eaec2db363649ec2f8799867cecd4fed64d15ead5a64ab63564d670a2662804'
DAMAGE_POLICY_SHA256 = '8284c96f0b8b5f53b28d0575341d9deb5f96a98d886e134579e14d67dc7430e0'
PROFILE_LIMITS_SHA256 = 'c7a7a6fa0a5094796135603174e56809e30e03484b9384b6a0877e83f33833a7'
_MAX_OWNER_BYTES = 65536
_ORDER = (8, 2, 3, 4, 5, 6, 7)


class PolicyV2Error(ValueError):
    """Stable rejection from the explicitly development-only v2 boundary."""


@dataclass(frozen=True, slots=True)
class SourceOwnerV2:
    sha256: str
    document: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ProgramResourceV2:
    profile_version: int
    profile_id: str
    recipe_id: int
    package_sha256: str
    primitive_steps: int
    peak_scratch_bytes: int
    provenance: str


@dataclass(frozen=True, slots=True)
class DecoderPolicyV2:
    profile_policy_sha256: str
    damage_policy_sha256: str
    profile_limits_sha256: str
    registry_profiles: tuple[m2_policy.ProfileTuple, ...]
    obs_units_resource_profiles: tuple[tuple[int, str, str, int, int], ...]
    repetition_primitive_steps: int
    repetition_peak_scratch_bytes: int
    decompression_primitive_steps: int
    decompression_peak_scratch_bytes: int
    maximum_units: int
    policy_ceilings: Mapping[str, int]
    program_resources: tuple[ProgramResourceV2, ...]
    active_shape: m2_codec.CandidateProfile
    result_schema_version: int = 2
    establishing_profile_versions: frozenset[int] = frozenset((8,))
    production_ready: bool = False

    def candidate_profile(self, units: int) -> m2_codec.CandidateProfile:
        """Form a bounded structural tuple; units is not a promoted first fit."""
        if type(units) is not int or not 1 <= units <= self.maximum_units:
            raise PolicyV2Error('physical-unit-domain')
        from dataclasses import replace
        return replace(self.active_shape, protected_units=units,
                       encoded_transport_bytes=216 * units)

    def profiles_for_units(self, units: int) -> tuple[m2_codec.CandidateProfile, ...]:
        """Active8 plus exact historical diagnostic shapes, in owned order."""
        return (self.candidate_profile(units), *m2_codec.candidate_profiles()[1:],
                m2_codec.r3_candidate_profile(protected_units=1841,
                                             encoded_transport_bytes=397656))

    def resource_for(self, profile_version: int, recipe_id: int) -> ProgramResourceV2:
        if type(profile_version) is not int or type(recipe_id) is not int:
            raise PolicyV2Error('program-resource-domain')
        for row in self.program_resources:
            if (row.profile_version, row.recipe_id) == (profile_version, recipe_id):
                return row
        raise PolicyV2Error('program-resource-domain')


def _freeze(value):
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


def _document(raw, digest, schema, keys):
    if type(raw) is not bytes or not 1 <= len(raw) <= _MAX_OWNER_BYTES:
        raise PolicyV2Error('owner-size-or-type')
    # Admission is exact source identity; a merely well-shaped replacement is
    # not an owner. This precedes TOML allocation for arbitrary input.
    if sha256(raw).hexdigest() != digest:
        raise PolicyV2Error('owner-identity-binding')
    try:
        document = tomllib.loads(raw.decode('utf-8'))
    except (UnicodeError, tomllib.TOMLDecodeError) as error:
        raise PolicyV2Error('owner-toml') from error
    if (set(document) != set(keys) or document.get('schema') != schema
            or type(document.get('policy_version')) is not int
            or document['policy_version'] != 2 or document.get('status') != 'development'):
        raise PolicyV2Error('owner-shape')
    return SourceOwnerV2(digest, _freeze(document))


def load_profile_policy_v2(raw: bytes) -> SourceOwnerV2:
    return _document(raw, PROFILE_POLICY_SHA256, 'golden-board.profile-policy/v2', (
        'schema', 'policy_version', 'status', 'scope', 'production_authority',
        'owners', 'candidate', 'registry', 'geometry', 'storage', 'mapping', 'admission'))


def load_damage_policy_v2(raw: bytes) -> SourceOwnerV2:
    return _document(raw, DAMAGE_POLICY_SHA256, 'golden-board.damage-policy/v2', (
        'schema', 'policy_version', 'status', 'scope', 'profile_policy_path',
        'production_authority', 'inheritance', 'corpus', 'decoder', 'resource',
        'decoder_result', 'program_resource'))


def load_profile_limits_v2(raw: bytes) -> SourceOwnerV2:
    return _document(raw, PROFILE_LIMITS_SHA256, 'golden-board.profile-limits/v2', (
        'schema', 'policy_version', 'status', 'scope', 'profile_policy_path',
        'damage_policy_path', 'production_authority', 'policy_ceiling', 'pending'))


def _integer(table, name, low, high):
    value = table[name]
    if type(value) is not int or not low <= value <= high:
        raise PolicyV2Error('owner-integer:' + name)
    return value


def load_decoder_policy_v2(profile_raw: bytes, limits_raw: bytes, damage_raw: bytes,
                           *, require_promoted: bool = False) -> DecoderPolicyV2:
    """Admit only bounded development decoding; never a production result.

    The production flag intentionally cannot succeed in this scaffolding. A
    future promotion implementation must admit a complete independently
    derived owner tuple, not toggle this flag or reuse these ceiling rows as
    measured limits. No filesystem, builder or saved artifact is consulted.
    """
    if type(require_promoted) is not bool:
        raise PolicyV2Error('promotion-flag-type')
    profile = load_profile_policy_v2(profile_raw)
    limits = load_profile_limits_v2(limits_raw)
    damage = load_damage_policy_v2(damage_raw)
    if require_promoted:
        raise PolicyV2Error('production-promotion-required')
    p, l, d = profile.document, limits.document, damage.document
    geometry, ceiling, candidate = p['geometry'], l['policy_ceiling'], p['candidate']
    maximum_units = ((_integer(geometry, 'side_max', 64, 2048)
                      - 2 * _integer(geometry, 'shell_width_min', 8, 128)) ** 2) // 1728
    if (maximum_units != ceiling['physical_units']
            or p['registry']['order'] != _ORDER
            or d['decoder']['registry_profile_order'] != _ORDER
            or d['decoder']['establishing_profile_versions'] != (8,)
            or d['decoder_result']['profile_allowlist'] != _ORDER
            or d['corpus']['gate6_admission'] is not False
            or d['corpus']['outcome_values_present'] is not False
            or l['pending']['production_admission'] is not False):
        raise PolicyV2Error('decoder-owner-binding')
    active = m2_codec.CandidateProfile(
        candidate['id'], _integer(candidate, 'profile_version', 8, 8),
        candidate['transport_id'], candidate['section_check_id'],
        _integer(candidate, 'check_bytes', 4, 4),
        _integer(candidate, 'semantic_copy_count', 1, 1),
        _integer(candidate, 'complexity_class', 1, 1),
        _integer(candidate, 'protected_unit_bytes', 216, 216),
        maximum_units, maximum_units * 216,
        _integer(candidate, 'inventory_version', 2, 2), candidate['placement_id'],
        candidate['physical_replica_counts'])
    # This tuple's count is explicitly the admissible geometry ceiling, never
    # a generated selected-manifestation claim. Call candidate_profile(Q) when
    # observed geometry supplies an actual Q.
    shapes = (active, *m2_codec.candidate_profiles()[1:],
              m2_codec.r3_candidate_profile(protected_units=1841,
                                           encoded_transport_bytes=397656))
    registry = tuple(m2_policy.ProfileTuple(
        row.profile_id, row.profile_version, row.transport_id, row.check_bytes,
        row.required_copy_count, row.protected_unit_bytes, row.complexity_class)
        for row in shapes)
    rows = []
    row_keys = {'profile_version','profile_id','recipe_id','package_sha256',
                'primitive_steps','peak_scratch_bytes','provenance'}
    for item in d['program_resource']:
        if set(item) != row_keys:
            raise PolicyV2Error('program-resource-shape')
        version = _integer(item, 'profile_version', 2, 8)
        digest = item['package_sha256']
        if (version not in _ORDER or type(digest) is not str or len(digest) != 64
                or any(ch not in '0123456789abcdef' for ch in digest)
                or item['profile_id'] != next(r.profile_id for r in registry
                                              if r.profile_version == version)):
            raise PolicyV2Error('program-resource-binding')
        rows.append(ProgramResourceV2(
            version, item['profile_id'], _integer(item, 'recipe_id', 1, 65535), digest,
            _integer(item, 'primitive_steps', 1, ceiling['recipe_primitive_steps']),
            _integer(item, 'peak_scratch_bytes', 1, ceiling['recipe_scratch_bytes']),
            item['provenance']))
    if tuple((row.profile_version,row.recipe_id) for row in rows) != (
            *((version,30) for version in _ORDER), (8,113), (7,113), (8,202)):
        raise PolicyV2Error('program-resource-order')
    if len({row.package_sha256 for row in rows if row.profile_version == 8}) != 1:
        raise PolicyV2Error('program-resource-package')
    repetition, decompression = rows[7], rows[9]
    return DecoderPolicyV2(
        profile.sha256, damage.sha256, limits.sha256, registry,
        tuple((row.profile_version,row.profile_id,row.package_sha256,
               row.primitive_steps,row.peak_scratch_bytes) for row in rows[:7]),
        repetition.primitive_steps, repetition.peak_scratch_bytes,
        decompression.primitive_steps, decompression.peak_scratch_bytes,
        maximum_units, ceiling, tuple(rows), active)
