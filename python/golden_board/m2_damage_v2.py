"""Lazy revised damage observations. No decoder or expected result is invoked."""
from dataclasses import dataclass, replace
from hashlib import sha256

from . import bootstrap, bootstrap_v2, m2_codec, recipe_wire_v2
from . import m2_damage as inherited
from .m2_mapping_v2 import mapping_parameters


def _freeze(value):
    return tuple(_freeze(item) for item in value) if isinstance(value,(list,tuple)) else value


def _json_value(value):
    return [_json_value(item) for item in value] if isinstance(value,tuple) else value


@dataclass(frozen=True, slots=True)
class DamageObservationV2:
    family: str
    ordinal: int
    channel: str
    operator: str
    parameters: tuple
    observation: bytes

    def __post_init__(self):
        object.__setattr__(self,'parameters',_freeze(self.parameters))

    @property
    def case_id(self):
        return f'{self.family}-{self.ordinal:06d}'

    def identity(self):
        return dict(schema='golden-board.damage-observation/v2',case_id=self.case_id,
            family_id=self.family,case_ordinal=self.ordinal,channel=self.channel,
            operator=self.operator,parameter_projection=[dict(id=k,value_type=t,value=_json_value(v))
                for k,t,v in self.parameters],observation_bytes=len(self.observation),
            observation_sha256=sha256(self.observation).hexdigest())


class DamageCorpusV2:
    """Source-side operator context; never passed to an observation decoder."""

    def __init__(self, image, *, alternate_route_owner_raw=None):
        plan = image.capacity_plan
        self.side,self.width = plan.side,plan.width
        self.mapping = mapping_parameters(self.side,self.width)
        self.interior,self.population = self.mapping.interior,self.mapping.population
        self.unit_bits = 1728
        self.carrier = image.carrier
        if (type(self.carrier) is not bytes or len(self.carrier) != 4+self.side**2//8
                or int.from_bytes(self.carrier[:4],'big') != self.side**2
                or plan.units != self.mapping.units):
            raise ValueError('damage-carrier-shape')
        self.clean = inherited._bits(self.carrier[4:])
        self.prefixes = image.route_prefixes
        if alternate_route_owner_raw is not None and (type(alternate_route_owner_raw) is not bytes
                or len(alternate_route_owner_raw)>1048576 or sha256(alternate_route_owner_raw).hexdigest()
                != '965a3e35ceb4b5a92a7715b3fcde20cc3019f8c9d9efa533abd93b051bb86641'):
            raise ValueError('damage-diagnostic-route-owner')
        self.alternate_route_owner_raw = alternate_route_owner_raw
        self._alternate_profile3_prefix = None
        self.sections = {s.section_id:s for s in plan.sections}
        if len(self.sections) != len(plan.sections) or tuple(self.sections) != tuple(sorted(self.sections)):
            raise ValueError('damage-section-order')
        self.clean_envelopes,self.clean_common,self.clean_encoded = {},{},{}
        self.rows_by_section,self.unit_rows,self.section_rows = {},[],[]
        for section in plan.sections:
            raw = bootstrap.encode_section_envelope(bootstrap.SectionEnvelope(section.section_id,
                section.section_type,section.version,section.closure,1,section.dependencies,section.payload))
            self.clean_envelopes[section.section_id] = raw
            blocks = bootstrap.fragment_section(raw,8,0)
            rows = []
            for fragment,block in enumerate(blocks):
                encoded = m2_codec.eh72_encode_unit(block)
                for replica in range(section.factor):
                    unit_id = len(self.unit_rows)+1
                    row = dict(physical_unit_id=unit_id,section_id=section.section_id,
                        fragment_index=fragment,replica_index=replica,physical_replica_count=section.factor,
                        logical_bit_first=1728*(self.mapping.slot_multiplier*(unit_id-1)%plan.units))
                    actual = bytearray(1728)
                    for bit in range(1728):
                        actual[bit] = self.clean[self.matrix_index(unit_id,bit)]
                    if inherited._packed(actual) != encoded:
                        raise ValueError('damage-source-matrix-mismatch')
                    self.unit_rows.append(row)
                    rows.append(row)
                    self.clean_encoded[unit_id],self.clean_common[unit_id] = encoded,block
            self.rows_by_section[section.section_id] = tuple(rows)
            self.section_rows.append(dict(section_id=section.section_id,closure_class=section.closure))
        if len(self.unit_rows) != plan.units:
            raise ValueError('damage-unit-count')
        self.row_by_unit = {row['physical_unit_id']:row for row in self.unit_rows}
        self.unit_rows,self.section_rows = tuple(self.unit_rows),tuple(self.section_rows)
        self.all_ids = tuple(self.clean_encoded)
        self.d3_population_cache = {}
        self._erased_sector = None
        self.family_counts = (16,4,256,128,plan.units,21,4*plan.units,415)
        self.boundary_count = 21
        self.inventory = bootstrap_v2.decode_inventory(self.sections[1].payload)
        if bootstrap_v2.encode_inventory(self.inventory) != self.sections[1].payload:
            raise ValueError('damage-inventory')
        if len(self.prefixes) != 4:
            raise ValueError('damage-route-count')
        for sector,prefix in enumerate(self.prefixes):
            actual = bytes(self.clean[r*self.side+c] for bit in range(len(prefix)*8)
                for r,c in (bootstrap.sector_cell(self.side,self.width,sector,bit),))
            if inherited._packed(actual) != prefix:
                raise ValueError('damage-route-source-mismatch')

    def physical_cell(self, unit_id, bit):
        slot = self.mapping.slot_multiplier*(unit_id-1)%self.mapping.units
        return (self.mapping.cell_multiplier*(1728*slot+bit)+self.mapping.offset)%self.population

    def matrix_index(self, unit_id, bit):
        row,column = divmod(self.physical_cell(unit_id,bit),self.interior)
        return (row+self.width)*self.side+column+self.width

    def damage_coordinates(self, ordinal, extra=0):
        if type(ordinal) is not int or not 0 <= ordinal < 128 or type(extra) is not int or extra not in (0,1):
            raise ValueError('damage-coordinate-domain')
        return inherited._d3_coordinates(self,ordinal,extra)

    def _matrix(self, coordinates, *, erased, base=None):
        matrix = bytearray(self.clean if base is None else base)
        for row,column in coordinates:
            at = row*self.side+column
            matrix[at] = 2 if erased else matrix[at]^1
        return inherited._obs_matrix(self.side,matrix)

    def _sector(self, sector):
        return (bootstrap.sector_cell(self.side,self.width,sector,i)
                for i in range(self.width*(self.side-self.width)))

    def _sector_erasure_base(self, sector):
        # One immutable 4MiB-at-most generation cache. Each case copies it
        # before adding its own unit erasure; prior cases never accumulate.
        if self._erased_sector is None or self._erased_sector[0]!=sector:
            matrix = bytearray(self.clean)
            for row,column in self._sector(sector):
                matrix[row*self.side+column] = 2
            self._erased_sector = (sector,bytes(matrix))
        return self._erased_sector[1]

    def _units(self, replacements=None, *, omit=(), order=None):
        units = self.clean_encoded if replacements is None else self.clean_encoded|replacements
        ids = self.all_ids if order is None else order
        excluded = frozenset(omit)
        return inherited._obs_units(tuple(i for i in ids if i not in excluded),units)

    def _section_replacements(self, section_id, raw):
        original = bootstrap.decode_section_envelope(self.clean_envelopes[section_id])
        blocks = inherited._fragment_unchecked_envelope(raw,original,8,0)
        rows = self.rows_by_section[section_id]
        if len(raw) != len(self.clean_envelopes[section_id]) or len(blocks) != 1+max(r['fragment_index'] for r in rows):
            raise ValueError('damage-section-length-change')
        encoded = tuple(m2_codec.eh72_encode_unit(b) for b in blocks)
        return {row['physical_unit_id']:encoded[row['fragment_index']] for row in rows}

    def _changed_payload(self, section_id, payload):
        original = bootstrap.decode_section_envelope(self.clean_envelopes[section_id])
        return self._section_replacements(section_id,
            bootstrap.encode_section_envelope(replace(original,payload=payload)))

    def _replace_prefix(self, matrix, sector, prefix, *, width=None):
        width = self.width if width is None else width
        if type(width) is not int or not 8 <= width <= 128 or width%8 or 2*width+8 > self.side:
            raise ValueError('damage-prefix-geometry')
        if type(prefix) is not bytes or not 64 <= len(prefix) <= 32768 or len(prefix)*8 > width*(self.side-width):
            raise ValueError('damage-prefix-bound')
        for offset,bit in enumerate(inherited._bits(prefix)):
            row,column = bootstrap.sector_cell(self.side,width,sector,offset)
            matrix[row*self.side+column] = bit

    @staticmethod
    def _package_offset(prefix):
        offset,found = 64,[]
        while offset < len(prefix):
            if offset+8 > len(prefix):
                raise ValueError('damage-route-frame')
            size = int.from_bytes(prefix[offset+4:offset+8],'big')
            if prefix[offset+1] == 5:
                found.append(offset+8)
            offset += 8+size
        if offset != len(prefix) or len(found) != 1:
            raise ValueError('damage-route-package')
        return found[0]

    def _route_mutation(self, mutate, *, sectors=range(4)):
        matrix = bytearray(self.clean)
        for sector in sectors:
            prefix = bytearray(self.prefixes[sector])
            package = self._package_offset(prefix)
            mutate(prefix,package)
            self._replace_prefix(matrix,sector,bytes(prefix))
        return inherited._obs_bits(matrix)

    def _square(self, ordinal, extra=0):
        side = max(32,self.interior//32)
        top,left = inherited._d2_placements(self,side)[ordinal]
        side += extra
        top,left = min(top,self.side-self.width-side),min(left,self.side-self.width-side)
        return side,top,left,((top+r,left+c) for r in range(side) for c in range(side))

    def case(self, family, ordinal):
        if (type(family) is not str or family not in tuple(f'D{i}' for i in range(8))
                or type(ordinal) is not int or not 0 <= ordinal < self.family_counts[int(family[1])]):
            raise ValueError('damage-case-domain')
        if family == 'D7':
            channel,operator,parameters,raw = self._special(434 if ordinal==414 else ordinal)
        elif family == 'D0':
            transform,polarity = divmod(ordinal,2)
            channel,operator = 'OBS_BITS','clean-transform-polarity'
            parameters = dict(transform_id=('u64',transform),polarity_id=('u64',polarity))
            raw = inherited._obs_bits(inherited._transform_matrix(self.clean,self.side,transform,polarity))
        elif family == 'D1':
            channel,operator = 'OBS_MATRIX','erase-one-complete-shell-sector'
            parameters = dict(sector_id=('u64',ordinal))
            raw = self._matrix(self._sector(ordinal),erased=True)
        elif family == 'D2':
            side,top,left,coordinates = self._square(ordinal)
            channel,operator = 'OBS_MATRIX','erase-square-in-protected-interior'
            parameters = dict(side=('u64',side),top_left=('coordinate-list',[[top,left]]))
            raw = self._matrix(coordinates,erased=True)
        elif family == 'D3':
            coordinates = self.damage_coordinates(ordinal)
            channel,operator = 'OBS_MATRIX','fixed-weight-unknown-bit-substitution'
            parameters = dict(coordinates=('coordinate-list',[list(c) for c in coordinates]),
                seed=('u64',5134751402299490304+ordinal),stratum_id=('u64',ordinal//32))
            raw = self._matrix(coordinates,erased=False)
        elif family == 'D4':
            channel,operator = 'OBS_UNITS','omit-one-physical-unit-observation'
            parameters = dict(omitted_unit_id=('u64',ordinal+1))
            raw = self._units(omit=(ordinal+1,))
        elif family == 'D5':
            ids = self.all_ids
            orders = (ids,tuple(reversed(ids)),ids[1:]+ids[:1],ids[::2]+ids[1::2],ids[1::2]+ids[::2])
            order = orders[ordinal] if ordinal < 5 else inherited._fisher_yates(ids,5134751402299490560+ordinal-5)
            channel,operator = 'OBS_UNITS','permute-intact-physical-unit-observations'
            parameters = dict(permutation_ordinal=('u64',ordinal))
            raw = self._units(order=order)
        else:
            sector,unit = divmod(ordinal,len(self.all_ids))
            unit += 1
            channel,operator = 'OBS_MATRIX','erase-shell-sector-union-one-physical-unit-cell-set'
            parameters = dict(sector_id=('u64',sector),unit_id=('u64',unit))
            matrix = bytearray(self._sector_erasure_base(sector))
            for bit in range(1728):
                matrix[self.matrix_index(unit,bit)] = 2
            raw = inherited._obs_matrix(self.side,matrix)
        return DamageObservationV2(family,ordinal,channel,operator,
            tuple((key,*parameters[key]) for key in sorted(parameters)),raw)

    def boundary_case(self, ordinal):
        if type(ordinal) is not int or not 0 <= ordinal < self.boundary_count:
            raise ValueError('damage-boundary-domain')
        channel,operator,parameters,raw = self._special(414+ordinal if ordinal<20 else 435)
        return DamageObservationV2('B0',ordinal,channel,operator,
            tuple((key,*parameters[key]) for key in sorted(parameters)),raw)

    def _special(self, ordinal):
        # Internal operator indices are separate from serialized D7/B0 IDs.
        params = {}
        channel = 'OBS_UNITS'
        if ordinal < 3:
            operator,channel = 'mapping-mutants','OBS_BITS'
            multiplier,offset = ((1,0),(self.mapping.cell_multiplier,(self.mapping.offset+1)%self.population),
                (2*self.interior+1,self.mapping.offset))[ordinal]
            matrix = bytearray(self.clean)
            for unit in self.all_ids:
                first = self.row_by_unit[unit]['logical_bit_first']
                for bit,value in enumerate(inherited._bits(self.clean_encoded[unit])):
                    row,column = divmod((multiplier*(first+bit)+offset)%self.population,self.interior)
                    matrix[(row+self.width)*self.side+column+self.width] = value
            params['mutant_ordinal'] = ('u64',ordinal)
            raw = inherited._obs_bits(matrix)
        elif ordinal < 7:
            operator = 'check-mutants'
            number = ordinal-3
            params['case_ordinal'] = ('u64',number)
            if number < 2:
                common = self.clean_common[1]
                check = common[187:][::-1]
                if number == 1:
                    register = 0xffffffff
                    for byte in bootstrap.LOCAL_DOMAIN+common[:187]:
                        register ^= byte<<24
                        for _ in range(8):
                            register = ((register<<1)^ (0x1edc6f41 if register&0x80000000 else 0))&0xffffffff
                    check = (register^0xffffffff).to_bytes(4,'big')
                encoded = m2_codec.eh72_encode_unit(common[:187]+check)
                raw = self._units(dict.fromkeys(range(1,6),encoded))
                params['target_unit_ids'] = ('u64-list',list(range(1,6)))
            else:
                envelope = bytearray(self.clean_envelopes[2])
                if number == 2:
                    envelope[11] = 2
                else:
                    envelope[-4:] = envelope[-4:][::-1]
                raw = self._units(self._section_replacements(2,bytes(envelope)))
                params['section_id'] = ('u64',2)
        elif ordinal < 10:
            operator = 'code-mutants'
            number = ordinal-7
            name = ('eh-parity-position-off-by-one','eh-position-72-in-hamming-equations','eh-lsb-first')[number]
            encoded = inherited._eh_mutant_unit(self.clean_common[1],name)
            raw = self._units(dict.fromkeys(range(1,6),encoded))
            params = dict(case_ordinal=('u64',number),target_unit_ids=('u64-list',list(range(1,6))))
        elif ordinal == 10:
            operator,channel = 'route-conflicts','OBS_BITS'
            if self.alternate_route_owner_raw is None:
                raise ValueError('source-owned-profile3-route-required')
            if self._alternate_profile3_prefix is None:
                from . import m2_recipe, m2_route_data
                profile = next(p for p in m2_codec.candidate_profiles() if p.profile_version==3)
                candidate = m2_route_data.CandidateRouteData(profile.profile_id,3,profile.transport_id,
                    profile.section_check_id,(m2_recipe.build_eh_recipient_package(3),))
                routes = m2_route_data.build_route_images(self.alternate_route_owner_raw,candidate,self.side,128)
                self._alternate_profile3_prefix = routes.sectors[0].data[:routes.sectors[0].route_prefix_cells//8]
            prefix = self._alternate_profile3_prefix
            matrix = bytearray(self.clean)
            self._replace_prefix(matrix,0,prefix,width=128)
            raw = inherited._obs_bits(matrix)
            params = dict(alternate_profile_version=('u64',3))
        elif ordinal < 16 or ordinal == 434:
            version = ordinal-9 if ordinal < 16 else 7
            operator = 'cross-profile-splices' if ordinal < 16 else 'foreign-profile7-bootstrap'
            block = bootstrap.decode_common_block(self.clean_common[1],8)
            common = bootstrap.encode_common_block(replace(block,profile_version=version))
            encoded = m2_codec.rs255_191_encode(common) if version in (5,6) else m2_codec.eh72_encode_unit(common)
            raw = self._units(dict.fromkeys(range(1,6),encoded))
            params = dict(source_profile_version=('u64',version),target_unit_ids=('u64-list',list(range(1,6))))
        elif ordinal == 16:
            operator = 'valid-copy-conflicts'
            block = bootstrap.decode_common_block(self.clean_common[1],8)
            common = bootstrap.encode_common_block(replace(block,payload=bytes((block.payload[0]^1,))+block.payload[1:]))
            raw = self._units({1:m2_codec.eh72_encode_unit(common)})
            params = dict(section_id=('u64',1),target_unit_id=('u64',1))
        elif ordinal < 273:
            operator,channel = 'd2-one-beyond','OBS_MATRIX'
            side,_,_,coordinates = self._square(ordinal-17,1)
            raw = self._matrix(coordinates,erased=True)
            params = dict(d2_ordinal=('u64',ordinal-17),side=('u64',side))
        elif ordinal < 401:
            operator,channel = 'd3-one-beyond','OBS_MATRIX'
            raw = self._matrix(self.damage_coordinates(ordinal-273,1),erased=False)
            params = dict(seed=('u64',5134751402299490304+ordinal-273))
        elif ordinal == 401:
            operator = 'missing-unit-one-beyond'
            raw = self._units(omit=range(1,6))
            params = dict(omitted_unit_ids=('u64-list',list(range(1,6))))
        elif ordinal < 405:
            operator,channel = 'algebraic-one-beyond','OBS_MATRIX'
            errors,erasures = ((2,0),(1,2),(0,4))[ordinal-402]
            matrix = bytearray(self.clean)
            for unit in range(1,6):
                for bit in range(erasures):
                    matrix[self.matrix_index(unit,bit)] = 2
                for bit in range(erasures,erasures+errors):
                    matrix[self.matrix_index(unit,bit)] ^= 1
            raw = inherited._obs_matrix(self.side,matrix)
            params = dict(errors=('u64',errors),erasures=('u64',erasures),target_unit_ids=('u64-list',list(range(1,6))))
        elif ordinal < 407:
            operator,channel = 'resource-route-one-beyond','OBS_BITS'
            offset,length,value = ((36,8,268435457),(44,4,16777217))[ordinal-405]
            def change(prefix,package):
                prefix[package+offset:package+offset+length] = value.to_bytes(length,'big')
            raw = self._route_mutation(change,sectors=(0,))
            params = dict(declared_value=('u64',value))
        elif ordinal == 407:
            operator,channel = 'geometry-one-beyond','OBS_BITS'
            cells = 2056**2
            raw = cells.to_bytes(4,'big')+bytes(cells//8)
            params = dict(side=('u64',2056))
        elif ordinal < 414:
            operator,channel = 'compact-wire-mutants','OBS_BITS'
            number = ordinal-408
            def change(prefix,package):
                if number == 0:
                    prefix[package+8:package+10] = bytes(2)
                elif number == 1:
                    prefix[package+48] = 1
                elif number == 2:
                    count = int.from_bytes(prefix[package+32:package+36],'big')
                    prefix[package+32:package+36] = (count-1).to_bytes(4,'big')
                else:
                    recipe = package+64
                    for _ in range(int.from_bytes(prefix[package+18:package+20],'big')):
                        recipe += 16+int.from_bytes(prefix[recipe+12:recipe+16],'big')
                    if number == 5:
                        steps = int.from_bytes(prefix[recipe+16:recipe+24],'big')
                        prefix[recipe+16:recipe+24] = (steps+1).to_bytes(8,'big')
                    else:
                        descriptors = int.from_bytes(prefix[recipe+4:recipe+6],'big')+int.from_bytes(prefix[recipe+6:recipe+8],'big')
                        node = recipe+32
                        end = recipe+int.from_bytes(prefix[recipe+28:recipe+32],'big')
                        if not 0 <= descriptors <= 128:
                            raise ValueError('damage-compact-descriptors')
                        for _ in range(descriptors):
                            node = recipe_wire_v2._descriptor(prefix,node,end)[0]
                        if not node < end or not prefix[node]&31 or not prefix[node]>>5:
                            raise ValueError('damage-compact-target')
                        prefix[node] &= 0xe0 if number==3 else 0x1f
            raw = self._route_mutation(change)
            params = dict(case_ordinal=('u64',number))
        elif ordinal < 428:
            operator = 'compressed-body-mutants'
            role,number = divmod(ordinal-414,7)
            section = next((s for s in self.sections.values() if s.section_type==3 and s.version==1
                            and s.closure==(128 if role==0 else 129)),None)
            if section is None or len(section.payload) < 6:
                raise ValueError('damage-compressed-target')
            payload = section.payload
            if number == 0:
                payload = b'\x02'+payload[1:]
            elif number == 1:
                payload = b'\x03\x40\x01'+payload[3:]
            else:
                prefix = (b'\x03\0\0',b'\x03\0\x03\x80\0\0',b'\x03\0\x01\x01\0',
                          b'\x03\0\x01\0\0',b'\x03\0\x01\x80\0\x0f')[number-2]
                payload = prefix+bytes(len(payload)-len(prefix))
            raw = self._units(self._changed_payload(section.section_id,payload))
            params = dict(case_ordinal=('u64',number),section_id=('u64',section.section_id))
        elif ordinal < 434:
            operator = 'checked-tier-control-mutants'
            role,number = divmod(ordinal-428,3)
            sid = role+2
            payload = bytearray(self.sections[sid].payload)
            if number == 0:
                payload[-4:-2] = bytes(2)
            elif number == 1:
                payload[-2:] = bytes(2)
            else:
                size = int.from_bytes(payload[8:12],'big')
                payload[8:12] = (size+1).to_bytes(4,'big')
            raw = self._units(self._changed_payload(sid,bytes(payload)))
            params = dict(case_ordinal=('u64',number),section_id=('u64',sid))
        else:
            operator,channel = 'square-inventory-undercoverage','OBS_BITS'
            target = next((s.section_id for s in self.sections.values() if s.section_type==6 and len(s.payload)>157),None)
            if target is None:
                raise ValueError('damage-load-target')
            entries = tuple(replace(e,logical_payload_length=e.logical_payload_length-157)
                if e.section_id==target else e for e in self.inventory.entries)
            payload = bootstrap_v2.encode_inventory(replace(self.inventory,entries=entries))
            replacements = self._changed_payload(1,payload)
            matrix = bytearray(self.clean)
            for unit,encoded in replacements.items():
                for bit,value in enumerate(inherited._bits(encoded)):
                    matrix[self.matrix_index(unit,bit)] = value
            raw = inherited._obs_bits(matrix)
            params = dict(section_id=('u64',target),removed_payload_bytes=('u64',157))
        return channel,operator,params,raw
