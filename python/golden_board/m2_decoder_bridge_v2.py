"""Bounded observation-only IPC; semantic agreement remains the caller's job."""
from dataclasses import dataclass
from hashlib import sha256
import os
import select
from time import monotonic

from . import canonical_manifest, m2_codec
from .m2_damage import RustBatchDecoder, DamageError
from .m2_resources_v2 import _read_resource_projection, checked


class BridgeV2Error(ValueError):
    pass


_PROFILES=('eh72-hier-r5-r2-r1-lzss-crc32c-v1',
           *(p.profile_id for p in m2_codec.candidate_profiles()[1:]),
           'eh72-hier-r5-r2-r1-crc32c-v0')
_RESULT_FIELDS=frozenset(('schema','channel','artifact_state','established_profile_id',
    'section_rows','fragment_diagnostics_sha256','m2_required_available','m2_all_available',
    'm2_required_stream_sha256','m2_all_stream_sha256','resource','accepted_hypothesis_rows'))


def _require(condition):
    if not condition:raise BridgeV2Error('result-frame-shape')


def _digest(value):
    return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)


def _result_frame_value(raw):
    """Closed wire structure only; hashes are not assumed semantic truth."""
    value=canonical_manifest.validate_canonical_manifest(raw)
    _require(type(value) is dict and set(value)==_RESULT_FIELDS)
    _require(value['schema']=='golden-board.m2-damage-decoder-result/v2'
        and value['channel'] in ('OBS_BITS','OBS_MATRIX','OBS_UNITS')
        and value['artifact_state'] in ('exact','degraded','failure','ambiguous','resource-limit')
        and value['established_profile_id'] in ('',_PROFILES[0])
        and type(value['section_rows']) is list and type(value['accepted_hypothesis_rows']) is list
        and type(value['resource']) is dict
        and set(value['resource'])=={'section_attempts','primitive_steps','peak_scratch_bytes'})
    for counter in value['resource'].values():checked(counter)
    _require(value['resource']['section_attempts']<=4096)
    _require(_digest(value['fragment_diagnostics_sha256']))
    for tier in ('required','all'):
        available,digest=value['m2_'+tier+'_available'],value['m2_'+tier+'_stream_sha256']
        _require(type(available) is bool and _digest(digest) and available==(digest!='0'*64))
    _require(not value['m2_all_available'] or value['m2_required_available'])
    previous=0
    for row in value['section_rows']:
        _require(type(row) is dict and set(row)=={'section_id','state','semantic_sha256'})
        _require(type(row['section_id']) is int and previous<row['section_id']<1<<32
            and row['state'] in ('verified','recovered','incomplete','corrupt','ambiguous','unknown')
            and _digest(row['semantic_sha256'])
            and (row['state'] in ('verified','recovered') or row['semantic_sha256']=='0'*64))
        previous=row['section_id']
    previous=None
    _require(len(value['accepted_hypothesis_rows'])<=64)
    for row in value['accepted_hypothesis_rows']:
        _require(type(row) is dict and set(row)=={'transform_id','polarity_id','sector_id','profile_id','mapping_sha256'})
        _require(all(type(row[name]) is int and 0<=row[name]<bound for name,bound in
                     (('transform_id',8),('polarity_id',2),('sector_id',4)))
                 and row['profile_id'] in _PROFILES and _digest(row['mapping_sha256']))
        key=(*[row[name] for name in ('transform_id','polarity_id','sector_id')],
             _PROFILES.index(row['profile_id']),row['mapping_sha256'])
        _require(previous is None or previous<key)
        previous=key
    _require(value['channel']!='OBS_UNITS' or not value['accepted_hypothesis_rows'])
    state=value['artifact_state']
    if state in ('failure','ambiguous','resource-limit'):
        _require(not value['m2_required_available'] and not value['m2_all_available'])
    if state in ('exact','degraded'):
        _require(value['established_profile_id']==_PROFILES[0]
                 and bool(value['section_rows']) and value['m2_required_available'])
    if state=='exact':
        _require(value['m2_all_available'] and all(row['state'] in ('verified','recovered')
                                                  for row in value['section_rows']))
    if state=='resource-limit':
        _require(not value['established_profile_id'] and not value['section_rows']
                 and not value['accepted_hypothesis_rows'] and not value['m2_required_available']
                 and not value['m2_all_available']
                 and value['fragment_diagnostics_sha256']==sha256(b'[]').hexdigest())
    return value


@dataclass(frozen=True,slots=True)
class ObservationEvidenceV2:
    result_raw: bytes
    resources_raw: bytes


class RevisionBatchDecoder(RustBatchDecoder):
    """Reuse bounded pipe transfers, with a distinct channel and response ABI."""

    def __init__(self,command,*,timeout_seconds=60.0):
        super().__init__(command,timeout_seconds=timeout_seconds)
        try:
            for stream in (self._process.stdin,self._process.stdout):
                assert stream is not None
                os.set_blocking(stream.fileno(),False)
        except OSError as error:
            self._abort()
            raise BridgeV2Error('nonblocking-pipes') from error

    def _transfer(self,descriptor,data,write):
        deadline=monotonic()+self._timeout
        cursor=0;output=bytearray();view=memoryview(data)
        while cursor<len(view):
            remaining=deadline-monotonic()
            if remaining<=0:raise BridgeV2Error('transfer-timeout')
            try:
                readable,writable,_=select.select(() if write else (descriptor,),
                    (descriptor,) if write else (),(),remaining)
                if not (writable if write else readable):raise BridgeV2Error('transfer-timeout')
                if write:
                    consumed=os.write(descriptor,view[cursor:cursor+65536])
                    if consumed<=0:raise BridgeV2Error('transfer-short-write')
                    cursor+=consumed
                else:
                    chunk=os.read(descriptor,min(65536,len(view)-cursor))
                    if not chunk:raise BridgeV2Error('transfer-short-read')
                    output.extend(chunk);cursor+=len(chunk)
            except (BlockingIOError,InterruptedError):
                continue
        return bytes(output)

    def _abort(self):
        if self._closed:return
        self._closed=True
        if self._process.poll() is None:self._process.kill()
        self._process.wait()
        for stream in (self._process.stdin,self._process.stdout):
            if stream is not None:stream.close()

    def boundary_kat(self,ordinal=None):
        raise BridgeV2Error('v2 bridge accepts observations only')

    def decode(self,channel,raw):
        if (type(channel) is not str or channel not in ('OBS_BITS','OBS_MATRIX','OBS_UNITS')
                or type(raw) is not bytes or len(raw)>4194306):
            raise BridgeV2Error('request-frame')
        channel_id={'OBS_BITS':1,'OBS_MATRIX':2,'OBS_UNITS':3}[channel]
        try:
            result_raw=self._exchange(channel_id,raw)
            stdout=self._process.stdout
            assert stdout is not None
            length=int.from_bytes(self._transfer(stdout.fileno(),bytes(4),False),'big')
            if not 1<=length<=1048576:raise BridgeV2Error('resource-frame-length')
            resources_raw=self._transfer(stdout.fileno(),bytes(length),False)
            result=_result_frame_value(result_raw)
            resources=_read_resource_projection(resources_raw)
            if (type(result) is not dict
                    or result.get('schema')!='golden-board.m2-damage-decoder-result/v2'
                    or result.get('channel')!=channel or resources['channel']!=channel
                    or resources['observation_sha256']!=sha256(raw).hexdigest()
                    or resources['result_sha256']!=sha256(result_raw).hexdigest()
                    or type(result.get('resource')) is not dict
                    or result['resource']!=resources['resource']):
                raise BridgeV2Error('response-binding')
            for value in result['resource'].values():checked(value)
            return ObservationEvidenceV2(result_raw,resources_raw)
        except (ValueError,OSError) as error:
            self._abort()
            if isinstance(error,BridgeV2Error):raise
            raise BridgeV2Error('response-or-transfer') from error

    def close(self):
        try:
            super().close()
        except DamageError as error:
            raise BridgeV2Error('process-close') from error

    def __exit__(self,exc_type,exc,traceback):
        if exc is not None:
            self._abort()
        else:
            self.close()
