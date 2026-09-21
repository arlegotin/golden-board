"""Source-informed transport/content oracle, separate from route acquisition.

This projection is semantic evidence, not a full resource/hypothesis result
or a gate receipt. Its complete envelopes must come from observed lane data.
The clean source supplies ownership and an independent wrong-accept baseline.
"""
from dataclasses import dataclass

from . import bootstrap, bootstrap_v2, body_codec_v1, m2_codec
from . import m2_damage as inherited
from .m2_transport_v2 import aggregate_replica_group


@dataclass(frozen=True, slots=True)
class OracleProjectionV2:
    artifact_state: str
    section_states: tuple
    wrong_accepts: int
    required_stream: bytes | None
    all_stream: bytes | None
    reauthored_boundary: bool
    semantic_result: object


class _ContextV2(inherited._Context):
    """Reuse the historical source oracle's group/section arithmetic only."""

    def __init__(self, corpus):
        self.profile = m2_codec.CandidateProfile(
            profile_id='eh72-hier-r5-r2-r1-lzss-crc32c-v1',profile_version=8,
            transport_id=m2_codec.HIER_TRANSPORT,section_check_id=m2_codec.CRC32C,
            check_bytes=4,required_copy_count=1,complexity_class=1,
            protected_unit_bytes=216,protected_units=len(corpus.all_ids),
            encoded_transport_bytes=216*len(corpus.all_ids),inventory_version=2,
            placement_id='affine-slot-then-interior-v2',physical_replica_counts=(1,2,5))
        self.is_r3 = True
        self.clean_common,self.clean_encoded = corpus.clean_common,corpus.clean_encoded
        self.clean_envelopes,self.inventory = corpus.clean_envelopes,corpus.inventory
        self.unit_rows = tuple(dict(row,semantic_copy_id=0) for row in corpus.unit_rows)
        self.row_by_unit = {row['physical_unit_id']:row for row in self.unit_rows}
        self.rows_by_group = {}
        for row in self.unit_rows:
            self.rows_by_group.setdefault((row['section_id'],row['fragment_index']),[]).append(row)
        self.section_rows = tuple(dict(section_id=s.section_id,closure_class=s.closure,
            fragment_count=s.fragments) for s in corpus.sections.values())

    def _oracle_aggregate_group(self, observations):
        return aggregate_replica_group(observations)

    def _oracle_inventory_decode(self, raw):
        return bootstrap_v2.decode_inventory(raw)

    def _oracle_registry_profiles(self):
        return (self.profile,*m2_codec.candidate_profiles()[1:],
            m2_codec.r3_candidate_profile(protected_units=1841,encoded_transport_bytes=397656))

    def _oracle_body_payload(self, raw):
        envelope = bootstrap.decode_section_envelope(raw)
        try:
            return body_codec_v1.decode_body(envelope.section_version,envelope.payload)
        except ValueError as error:
            raise bootstrap.BootstrapReject(bootstrap.TIER_FRAME,'oracle.body-codec') from error


class DamageOracleV2:
    def __init__(self, corpus):
        self.corpus = corpus
        self.context = _ContextV2(corpus)

    def _observed_units(self, case):
        corpus = self.corpus
        if case.channel == 'OBS_UNITS':
            raw,offset,units = case.observation,4,{}
            if len(raw)<4:
                raise ValueError('oracle.units.header')
            count = int.from_bytes(raw[:4],'big')
            if count>2389:
                raise ValueError('oracle.units.count')
            for _ in range(count):
                if offset+6>len(raw):
                    raise ValueError('oracle.units.header')
                unit,length = int.from_bytes(raw[offset:offset+4],'big'),int.from_bytes(raw[offset+4:offset+6],'big')
                offset += 6
                if not unit or unit in units or offset+length>len(raw):
                    raise ValueError('oracle.units.frame')
                units[unit] = raw[offset:offset+length]
                offset += length
            if offset!=len(raw) or not set(units)<=set(corpus.all_ids):
                raise ValueError('oracle.units.trailing-or-foreign-id')
            return ({i:raw for i,raw in units.items() if raw!=corpus.clean_encoded[i]},
                {},set(corpus.all_ids)-set(units))
        if case.channel == 'OBS_BITS':
            raw = case.observation
            if int.from_bytes(raw[:4],'big')!=corpus.side**2 or len(raw)!=len(corpus.carrier):
                raise ValueError('oracle.bits.geometry')
            cells = inherited._bits(raw[4:])
        elif case.channel == 'OBS_MATRIX':
            raw = case.observation
            if int.from_bytes(raw[:2],'big')!=corpus.side or len(raw)!=2+corpus.side**2 or any(v>2 for v in raw[2:]):
                raise ValueError('oracle.matrix.geometry')
            cells = raw[2:]
        else:
            raise ValueError('oracle.channel')
        parameters = {key:value for key,_type,value in case.parameters}
        transform,polarity = (parameters['transform_id'],parameters['polarity_id']) if case.family=='D0' else (0,0)
        replacements,erasures = {},{}
        for unit in corpus.all_ids:
            bits,erased = bytearray(1728),[]
            for bit in range(1728):
                index = corpus.matrix_index(unit,bit)
                if transform:
                    row,column = divmod(index,corpus.side)
                    row,column = inherited._transform_coordinate(corpus.side,transform,row,column)
                    index = row*corpus.side+column
                value = cells[index]
                if value==2:
                    erased.append(bit)
                    value = 0
                else:
                    value ^= polarity
                bits[bit] = value
            encoded = inherited._packed(bits)
            if encoded!=corpus.clean_encoded[unit]:
                replacements[unit] = encoded
            if erased:
                erasures[unit] = tuple(erased)
        return replacements,erasures,set()

    def evaluate(self, case):
        from .m2_damage_v2 import DamageObservationV2
        if type(case) is not DamageObservationV2:
            raise ValueError('oracle.case.type')
        owned = (self.corpus.boundary_case(case.ordinal) if case.family=='B0'
                 else self.corpus.case(case.family,case.ordinal))
        if case != owned:
            raise ValueError('oracle.case.binding')
        return self._evaluate_observation(case)

    def _evaluate_observation(self, case):
        if case.family=='D7' and case.ordinal in (405,406,407,408,409,410,411,412,413):
            forced = 'resource-limit' if case.ordinal in (405,406) else 'failure'
            result = self.context._evaluate_r3({}, {},set(),route_conflict=False,forced_state=forced)
        else:
            replacements,erasures,omitted = self._observed_units(case)
            result = self.context._evaluate_r3(replacements,erasures,omitted,
                route_conflict=False,forced_state=None)
        semantic = result.decoder_base
        return OracleProjectionV2(result.artifact_state,result.section_states,result.wrong_accepts,
            semantic.m2_required_stream,semantic.m2_all_stream,case.family=='B0',semantic)
