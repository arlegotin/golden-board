"""Checked per-observation accounting for the explicit v2 receiver.

VM instructions retain their existing meaning. Adapter rows count declared
reference-kernel work, never host CPU instructions or allocator overhead.
"""
from contextlib import contextmanager
from hashlib import sha256

from . import bootstrap
from .m2_decoder import DecoderError, ResourceUsage
from . import canonical_manifest

RESOURCE_OWNER_SHA256 = 'e36aaee1b61b47bc71ebc7a6bdbbb91b721d14b6d49bf8aec969aebdb8dd807f'
_RESOURCE_KEYS = ('section_attempts','primitive_steps','peak_scratch_bytes')
_ADAPTER_KEYS = ('calls','reference_input_units','peak_workspace_bytes')
_OWNER_PATHS = ('spec/profile-policy-v2.toml','spec/profile-limits-v2.toml',
                'spec/damage-policy-v2.toml','spec/resource-accounting-v2.md')

_U64 = (1 << 64)-1
ADAPTER_KERNELS = (
    'observation','square-view','shell-read','route-frame','recipe-parse',
    'program-refinement','route-example','definition-validation','mapping-search',
    'unit-extraction','lane-adapter','repetition-adapter','common-frame',
    'section-assembly','section-check','inventory','group-layout',
    'dependency-closure','body-adapter','content-validation','result-selection',
    'result-render',
)


def checked(value):
    if type(value) is not int or not 0 <= value <= _U64:
        raise DecoderError('resource-limit')
    return value


def add(a,b):
    a,b = checked(a),checked(b)
    if b > _U64-a:
        raise DecoderError('resource-limit')
    return a+b


def multiply(a,b):
    a,b = checked(a),checked(b)
    if a and b > _U64//a:
        raise DecoderError('resource-limit')
    return a*b


class ResourceMeterV2:
    """No counters are rolled back, including on semantic or global failure."""
    def __init__(self):
        self._attempted = set()
        self._steps = self._peak = self._live = 0
        self._adapter = {}
        self._retained = {}
        self._attempt_bytes = 0

    @property
    def usage(self):
        return ResourceUsage(len(self._attempted),self._steps,self._peak)

    @property
    def adapter_rows(self):
        return tuple((key,*self._adapter[key]) for key in ADAPTER_KERNELS if key in self._adapter)

    def invoke(self, steps, scratch, count=1):
        total = add(self._steps,multiply(steps,count))
        peak = max(self._peak,add(self._live,scratch))
        self._steps,self._peak = total,peak

    def adapter(self, kernel, work, workspace):
        if kernel not in ADAPTER_KERNELS:
            raise DecoderError('resource-limit')
        work,workspace = checked(work),checked(workspace)
        calls,old_work,old_peak = self._adapter.get(kernel,(0,0,0))
        row = (add(calls,1),add(old_work,work),max(old_peak,workspace))
        peak = max(self._peak,add(self._live,workspace))
        self._adapter[kernel],self._peak = row,peak

    def adapter_workspace(self, kernel, workspace):
        if kernel not in self._adapter:
            raise DecoderError('resource-limit')
        workspace = checked(workspace)
        calls,work,peak = self._adapter[kernel]
        total_peak = max(self._peak,add(self._live,workspace))
        self._adapter[kernel] = (calls,work,max(peak,workspace))
        self._peak = total_peak

    def adapter_work(self, kernel, work):
        """Finish an already reserved event without another call/peak change."""
        if kernel not in self._adapter:
            raise DecoderError('resource-limit')
        calls,old_work,peak = self._adapter[kernel]
        self._adapter[kernel] = (calls,add(old_work,work),peak)

    @contextmanager
    def hold(self, size):
        live = add(self._live,size)
        self._live = live
        self._peak = max(self._peak,live)
        try:
            yield
        finally:
            self._live -= size

    def retain(self, key, size):
        size = checked(size)
        old = self._retained.get(key,0)
        live = add(self._live-old,size)
        self._retained[key] = size
        self._live = live
        self._peak = max(self._peak,live)

    def section(self, raw):
        if not bootstrap.section_envelope_attempt_eligible(raw) or raw in self._attempted:
            return
        if len(self._attempted) >= 4096:
            raise DecoderError('resource-limit')
        # Admission precedes check comparison, including deliberately bad CRC.
        retained = add(self._attempt_bytes,add(len(raw),8))
        self.retain('attempts',retained)
        self.adapter('section-check',len(raw),len(raw))
        self._attempted.add(raw)
        self._attempt_bytes = retained


def content_shape(raw):
    """Bounded resource metadata only; this NEVER admits a content stream.

    Regions duplicated into each lesson's runtime map require a multiplicity
    term even when many lessons share one compact REGION_SET record.
    """
    if type(raw) is not bytes:
        raise TypeError('content resource metadata requires bytes')
    if len(raw) > 1048576:
        raise DecoderError('resource-limit')
    if len(raw) < 4:
        return len(raw),0,0
    count = int.from_bytes(raw[2:4],'big')
    regions,lessons,cursor = {},[],4
    for _ in range(count):
        if cursor+8 > len(raw):
            break
        rid = int.from_bytes(raw[cursor:cursor+2],'big')
        kind = int.from_bytes(raw[cursor+2:cursor+4],'big')
        size = int.from_bytes(raw[cursor+4:cursor+8],'big')
        start,end = cursor+8,cursor+8+size
        if end > len(raw):
            break
        if kind == 7 and size >= 4:
            regions[rid] = min(4096,int.from_bytes(raw[start+2:start+4],'big'))
        elif kind == 13 and size >= 18:
            lessons.append(int.from_bytes(raw[start+6:start+8],'big'))
        cursor = end
    # A content-v0 stream has at most4096 lessons. Invalid declarations above
    # that bound reject before projection construction; no larger allocation
    # is attributed to the reference validator.
    h = sum(regions.get(ref,0) for ref in lessons[:4096])
    return len(raw),count,h


def content_workspace(byte_length, record_count, region_rows=0):
    """Owned reference arenas and mutually exclusive validator phase storage.

    This is the reservation in resource-accounting-v2, not a host allocator
    measurement. Public projection/authoring views are separate operations.
    """
    b,r,h = checked(byte_length),checked(record_count),checked(region_rows)
    a,s,e,l = min(65535,b//4),min(4096,b//4),min(16384,b//2),min(4096,r)
    base = add(add(multiply(32,b),multiply(128,r)),multiply(8,h))
    dependency = add(multiply(4,b),multiply(24,r))
    passive = add(add(multiply(64,a),multiply(32,s)),add(multiply(24,l),256))
    graph = add(multiply(48,e),multiply(192,l))
    return add(base,max(dependency,passive,graph))


def _recipe_shape(raw):
    if type(raw) is not bytes or len(raw) > 1048576:
        raise DecoderError('resource-limit')
    if len(raw) < 64:
        return len(raw),0,0,0,0,0
    n = lambda at,width,maximum: min(maximum,int.from_bytes(raw[at:at+width],'big'))
    p,t,nodes,edges,data = n(16,2,256),n(18,2,4096),n(20,4,65535),n(24,4,262140),n(28,4,1048576)
    expanded = min(1048576,len(raw)+26*nodes) if raw[8:10] == b'\0\1' else len(raw)
    return expanded,p,t,nodes,edges,data


def recipe_storage(raw):
    """Canonical immutable wire/parsed-program reservation, not admission."""
    if type(raw) is bytes and len(raw) < 64:
        return len(raw)
    x,p,t,n,e,d = _recipe_shape(raw)
    return sum((len(raw),3*x,64*n,64*t,128*p,8*d))


def recipe_workspace(raw):
    x,p,t,n,e,d = _recipe_shape(raw)
    return recipe_storage(raw)+48*n+8*e+16*t+32*p


def definition_workspace(definitions, package_raw):
    """Finite local DEFINE checks, including their public miniature views."""
    size = sum(map(len,definitions))
    # 575-byte base plus its largest two-byte presentation mutation. Four
    # concurrent content/view arenas cover base, public/authoring conversion,
    # changed authoring records, and the one currently tested candidate.
    miniature = 4*content_workspace(577,29,29*(577//14))
    return 8*size+max(recipe_workspace(package_raw),recipe_storage(package_raw)+miniature)


def _digest(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def render_resource_projection_v2(channel, observation_sha256, result_raw, usage, adapter_rows, policy):
    """Sidecar generation; intentionally excluded from receiver scratch."""
    if channel not in ('OBS_BITS','OBS_MATRIX','OBS_UNITS') or not _digest(observation_sha256):
        raise ValueError('resource-observation')
    result = canonical_manifest.validate_canonical_manifest(result_raw)
    resource = {key:checked(getattr(usage,key)) for key in _RESOURCE_KEYS}
    if (result.get('schema') != 'golden-board.m2-damage-decoder-result/v2'
            or result.get('channel') != channel or result.get('resource') != resource):
        raise ValueError('resource-result')
    rows = {row[0]:row[1:] for row in adapter_rows}
    if len(rows) != len(adapter_rows) or not rows.keys() <= set(ADAPTER_KERNELS):
        raise ValueError('resource-kernels')
    owners = dict(zip(_OWNER_PATHS,(policy.profile_policy_sha256,policy.profile_limits_sha256,
                                  policy.damage_policy_sha256,RESOURCE_OWNER_SHA256),strict=True))
    value = dict(schema='golden-board.m2-observation-resources/v2',channel=channel,
        observation_sha256=observation_sha256,result_sha256=sha256(result_raw).hexdigest(),
        source_owners=owners,resource=resource,adapter_rows=[dict(kernel=key,
            **dict(zip(_ADAPTER_KEYS,map(checked,rows.get(key,(0,0,0))),strict=True))) for key in ADAPTER_KERNELS])
    return canonical_manifest.serialize_manifest(value)


def _read_resource_projection(raw):
    from .m2_policy_v2 import PROFILE_POLICY_SHA256,PROFILE_LIMITS_SHA256,DAMAGE_POLICY_SHA256
    value = canonical_manifest.validate_canonical_manifest(raw)
    if (set(value) != {'schema','channel','observation_sha256','result_sha256','source_owners','resource','adapter_rows'}
            or value['schema'] != 'golden-board.m2-observation-resources/v2'
            or value['channel'] not in ('OBS_BITS','OBS_MATRIX','OBS_UNITS')
            or not all(_digest(value[key]) for key in ('observation_sha256','result_sha256'))
            or type(value['source_owners']) is not dict or set(value['source_owners']) != set(_OWNER_PATHS)
            or not all(_digest(d) for d in value['source_owners'].values())
            or tuple(value['source_owners'][p] for p in _OWNER_PATHS[:3]) !=
                (PROFILE_POLICY_SHA256,PROFILE_LIMITS_SHA256,DAMAGE_POLICY_SHA256)
            or value['source_owners'][_OWNER_PATHS[-1]] != RESOURCE_OWNER_SHA256
            or type(value['resource']) is not dict or set(value['resource']) != set(_RESOURCE_KEYS)
            or type(value['adapter_rows']) is not list or len(value['adapter_rows']) != len(ADAPTER_KERNELS)):
        raise ValueError('resource-projection')
    for counter in value['resource'].values():
        checked(counter)
    for key,row in zip(ADAPTER_KERNELS,value['adapter_rows'],strict=True):
        if type(row) is not dict or set(row) != {'kernel',*_ADAPTER_KEYS} or row['kernel'] != key:
            raise ValueError('resource-kernel')
        for field in _ADAPTER_KEYS:
            checked(row[field])
        if row['calls'] == 0 and any(row[field] for field in _ADAPTER_KEYS[1:]):
            raise ValueError('resource-unused-kernel')
    return value


class ResourceAggregateV2:
    """One-row-at-a-time maxima; the finished identity is supplied after hashing."""
    def __init__(self,expected_case_ids):
        if (type(expected_case_ids) is not tuple
            or not 1 <= len(expected_case_ids) <= 65535
            or any(type(case) is not str or not case.isascii() or not 1 <= len(case) <= 128 for case in expected_case_ids)
            or len(set(expected_case_ids)) != len(expected_case_ids)):
            raise ValueError('resource-corpus')
        self.ids=expected_case_ids
        self.index=0
        self.digest=sha256(b'GBRESV2\0'+len(expected_case_ids).to_bytes(4,'big'))
        self.resource=dict.fromkeys(_RESOURCE_KEYS,0)
        self.maxima=[dict(kernel=key,**dict.fromkeys(_ADAPTER_KEYS,0)) for key in ADAPTER_KERNELS]
        self.owners=None

    def push(self,case_id,raw):
        if self.index>=len(self.ids) or case_id!=self.ids[self.index]:
            raise ValueError('resource-case-order')
        value = _read_resource_projection(raw)
        if self.owners is not None and self.owners != value['source_owners']:
            raise ValueError('resource-source-owners')
        self.owners = value['source_owners']
        raw_id = case_id.encode('ascii')
        self.digest.update(len(raw_id).to_bytes(2,'big')+raw_id+sha256(raw).digest())
        for key in _RESOURCE_KEYS:
            self.resource[key] = max(self.resource[key],value['resource'][key])
        for target,source in zip(self.maxima,value['adapter_rows'],strict=True):
            for key in _ADAPTER_KEYS:
                target[key] = max(target[key],source[key])
        self.index+=1

    def finish(self,corpus_sha256):
        if self.index!=len(self.ids) or not _digest(corpus_sha256):
            raise ValueError('resource-corpus')
        return canonical_manifest.serialize_manifest(dict(schema='golden-board.m2-resource-limits/v2',
            corpus_sha256=corpus_sha256,case_count=len(self.ids),case_resources_sha256=self.digest.hexdigest(),
            source_owners=self.owners,maximum_resource=self.resource,adapter_maxima=self.maxima))


def build_resource_limits_v2(corpus_sha256, expected_case_ids, rows):
    """Aggregate only an exactly covered caller-owned corpus; no admission."""
    if not _digest(corpus_sha256):
        raise ValueError('resource-corpus')
    aggregate=ResourceAggregateV2(expected_case_ids)
    iterator,sentinel=iter(rows),object()
    for case_id in expected_case_ids:
        row=next(iterator,None)
        if type(row) is not tuple or len(row)!=2 or row[0]!=case_id:
            raise ValueError('resource-case-order')
        aggregate.push(case_id,row[1])
    if next(iterator,sentinel) is not sentinel:
        raise ValueError('resource-extra-case')
    return aggregate.finish(corpus_sha256)
