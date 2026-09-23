"""Finite source-only bounds; no selected result or measured input derives them."""
from hashlib import sha256

from . import canonical_manifest
from .m2_policy_v2 import load_decoder_policy_v2
from .m2_resources_v2 import (
    ADAPTER_KERNELS, RESOURCE_OWNER_SHA256, checked, add, multiply, content_workspace,
)

BOUNDS_OWNER_SHA256 = '6e96a646adfa4628ca4b786abe02cb60f50c2c6fc67ff93b077a967c7568b765'
_PATHS = ('spec/profile-policy-v2.toml', 'spec/profile-limits-v2.toml',
          'spec/damage-policy-v2.toml', 'spec/resource-accounting-v2.md',
          'spec/receiver-bounds-v2.md')
_COUNTERS = ('section_attempts', 'primitive_steps', 'peak_scratch_bytes')
_ADAPTER = ('calls', 'reference_input_units', 'peak_workspace_bytes')


def _sum(*values):
    total = 0
    for value in values:
        total = add(total, value)
    return total


def _product(*values):
    total = 1
    for value in values:
        total = multiply(total, value)
    return total


def derive_receiver_bounds_v2(profile_raw, limits_raw, damage_raw, resource_raw, bounds_raw):
    policy = load_decoder_policy_v2(profile_raw, limits_raw, damage_raw)
    for raw, digest in ((resource_raw, RESOURCE_OWNER_SHA256), (bounds_raw, BOUNDS_OWNER_SHA256)):
        if type(raw) is not bytes or not 1 <= len(raw) <= 65536 or sha256(raw).hexdigest() != digest:
            raise ValueError('receiver-bounds-owner')
    c = policy.policy_ceilings
    v, p, w = c['square_view_hypotheses'], c['route_path_hypotheses'], c['shell_width']
    i, d, b, r = c['inventory_entries'], c['dependency_count_per_section'], c['content_stream_bytes'], c['content_records']
    q = max(shape.protected_units for shape in policy.profiles_for_units(policy.maximum_units))
    g = len(policy.registry_profiles)
    a, f, j = _product(v, w//8, 4), _product(w, c['side'])//8, _sum(p, g, 1)
    l, k = _product(j, q), _product(3, j, q)
    e = _sum(18, _product(4, d), c['section_payload_bytes'], 8)
    advertised = 1048576
    layout_envelope = _sum(18,_product(4,d),(1 << 32)-1,8)
    n = _sum(layout_envelope, 156)//157
    u, h = _product(i, n, 5), _product(i, d)
    assemblies = _product(j, _sum(_product(3, q), _product(2, i)))
    y, m = _product(j, _sum(q, 1)), _product(j, i)
    nodes, edges, tables, recipes = (c[key] for key in ('recipe_nodes','recipe_edges','recipe_tables','recipes'))
    storage = _sum(c['recipe_package_bytes'], _product(3, c['recipe_expanded_package_bytes']),
                   _product(64, nodes), _product(64, tables), _product(128, recipes),
                   _product(8, c['recipe_table_payload_bytes']))
    parsing = _sum(storage, _product(48, nodes), _product(8, edges),
                   _product(16, tables), _product(32, recipes))
    definitions = _sum(_product(8, f), max(parsing, _sum(storage,
                       _product(4, content_workspace(577,29,29*(577//14))))))
    content = content_workspace(b, r, _product(4096,4096))
    result = _sum(_product(_sum(i, _product(g,q)), _sum(48,e)),
                  _product(_sum(u, _product(g,q)), 40+191), _product(48,p), _product(2,b))
    route_calls = _product(a, max(_sum(c['route_records'],3),62))
    raw_rows = (
        ('observation', 1, c['observation_frame_bytes'], 0),
        ('square-view', v, c['raw_bits'], 0),
        ('shell-read', _product(2,a), _product(8,f), f),
        ('route-frame', a, f, _product(8,c['route_records'])),
        ('recipe-parse', _product(a,c['route_records']), c['recipe_package_bytes'], parsing),
        ('program-refinement', _sum(a,m), nodes, _sum(_product(32,nodes),_product(8,edges),_product(8,tables))),
        ('route-example', route_calls, f, _sum(f,_product(64,c['recipe_package_bytes']),8*128)),
        ('definition-validation', a, f, definitions),
        ('mapping-search', a, _product(4,q), 64),
        ('unit-extraction', j, _product(q,255,8), _product(q,8+2*255)),
        ('lane-adapter', l, 255, 255+191),
        ('repetition-adapter', k, 5*1728, 216+2*1728),
        ('common-frame', _sum(l,k), 191, 191),
        ('section-assembly', assemblies, _product(191,q), _sum(advertised,_product(24,q))),
        ('section-check', c['section_attempts'], e, e),
        ('inventory', y, e-22, _product(16,e-22)),
        ('group-layout', y, u, _sum(_product(128,u),_product(64,i))),
        ('dependency-closure', y, h, _sum(_product(24,i),_product(8,h))),
        ('body-adapter', m, c['section_payload_bytes'], _sum(c['section_payload_bytes'],32768)),
        ('content-validation', _product(2,j), b, content),
        ('result-selection', j, _product(j,result), result),
        ('result-render', 2, _product(2,_sum(c['output_bytes'],1)), _sum(c['output_bytes'],256)),
    )
    if tuple(row[0] for row in raw_rows) != ADAPTER_KERNELS:
        raise ValueError('receiver-bounds-kernels')
    adapters = [dict(kernel=key,calls=checked(calls),reference_input_units=_product(calls,units),
                     peak_workspace_bytes=checked(workspace)) for key,calls,units,workspace in raw_rows]
    steps = _product(c['recipe_primitive_steps'], _sum(route_calls,_product(24,l),_product(1728+24,k),m))
    peak = _sum(c['raw_bits'], _product(q,_sum(8,2*255,_product(g,199))),
                _product(a,c['route_records'],storage), _product(a,_sum(f,_product(16,c['route_records']))),
                _product(c['section_attempts'],_sum(e,8)),
                _product(16,e-22),_product(128,u),_product(64,i),_product(8,h),
                _product(i,_sum(c['decoded_body_bytes'],8)),_product(2,b),_product(j,result),
                _product(128,a),_product(48,p),64,f,
                c['recipe_scratch_bytes'],max(row[3] for row in raw_rows))
    raws = (profile_raw,limits_raw,damage_raw,resource_raw,bounds_raw)
    return canonical_manifest.serialize_manifest(dict(
        schema='golden-board.m2-receiver-bounds/v2', profile_id=policy.active_shape.profile_id,
        source_owners={path:sha256(raw).hexdigest() for path,raw in zip(_PATHS,raws,strict=True)},
        derivation=dict(A=a,Q=q,G=g,J=j,L=l,K=k,E=e,Ea=advertised,El=layout_envelope,N=n,U=u,H=h,C=assemblies,Y=y,M=m,
                        S=storage,Sp=parsing,X=content,Zr=result),
        maximum_resource=dict(section_attempts=c['section_attempts'],primitive_steps=steps,peak_scratch_bytes=peak),
        adapter_bounds=adapters))


def _digest(value):
    return type(value) is str and len(value) == 64 and all(ch in '0123456789abcdef' for ch in value)


def validate_measured_bounds_v2(measured_raw, *owner_raws):
    """Componentwise limit admission only; caller must prove corpus coverage."""
    bound = canonical_manifest.validate_canonical_manifest(derive_receiver_bounds_v2(*owner_raws))
    value = canonical_manifest.validate_canonical_manifest(measured_raw)
    if (set(value) != {'schema','corpus_sha256','case_count','case_resources_sha256','source_owners',
                      'maximum_resource','adapter_maxima'}
            or value['schema'] != 'golden-board.m2-resource-limits/v2'
            or not _digest(value['corpus_sha256']) or not _digest(value['case_resources_sha256'])
            or type(value['case_count']) is not int or not 1 <= value['case_count'] <= 65535
            or value['source_owners'] != {p:bound['source_owners'][p] for p in _PATHS[:4]}
            or type(value['maximum_resource']) is not dict or set(value['maximum_resource']) != set(_COUNTERS)
            or type(value['adapter_maxima']) is not list or len(value['adapter_maxima']) != len(ADAPTER_KERNELS)):
        raise ValueError('receiver-bounds-measured-shape')
    for key in _COUNTERS:
        if checked(value['maximum_resource'][key]) > bound['maximum_resource'][key]:
            raise ValueError('receiver-bounds-resource')
    for actual,maximum in zip(value['adapter_maxima'],bound['adapter_bounds'],strict=True):
        if type(actual) is not dict or set(actual) != {'kernel',*_ADAPTER} or actual['kernel'] != maximum['kernel']:
            raise ValueError('receiver-bounds-kernel')
        for key in _ADAPTER:
            if checked(actual[key]) > maximum[key]:
                raise ValueError('receiver-bounds-adapter')
        if actual['calls'] == 0 and any(actual[key] for key in _ADAPTER[1:]):
            raise ValueError('receiver-bounds-unused-kernel')
