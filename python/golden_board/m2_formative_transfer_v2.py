"""Two source-owned formative observations; no receiver output is an oracle."""
from dataclasses import dataclass
from hashlib import sha256

from . import bootstrap, m2_codec
from .m2_capacity_v2 import CapacityPlan
from .m2_carrier_v2 import DevelopmentCarrier
from .m2_mapping_v2 import map_unit_bit, mapping_parameters


@dataclass(frozen=True, slots=True)
class FormativeTransferCaseV2:
    name: str
    observation: bytes
    source_carrier_sha256: str
    section_id: int
    fragment_index: int
    physical_first: int
    factor: int
    expected_common: bytes
    foreign_common: bytes | None
    expected_repetition_common: bytes
    expected_group_state: str
    edited_cells: tuple[tuple[int, int], ...]

    def owner_manifest(self):
        """Owner-only construction identity; never a recipient-side hint."""
        return dict(schema='golden-board.m2-formative-transfer-case/v2', name=self.name,
            channel='OBS_MATRIX', source_carrier_sha256=self.source_carrier_sha256,
            observation_sha256=sha256(self.observation).hexdigest(),
            section_id=self.section_id, fragment_index=self.fragment_index,
            physical_first=self.physical_first, factor=self.factor,
            expected_common_sha256=sha256(self.expected_common).hexdigest(),
            foreign_common_sha256=sha256(self.foreign_common).hexdigest() if self.foreign_common else '0'*64,
            expected_repetition_common_sha256=sha256(self.expected_repetition_common).hexdigest(),
            expected_group_state=self.expected_group_state,
            edited_cells=[list(row) for row in self.edited_cells])


def _require(condition, reason):
    if not condition:
        raise ValueError('formative-transfer.'+reason)


def _local(encoded, erased):
    """Independently compose the bounded EH primitive and common grammar."""
    plain = bytearray()
    for word in range(24):
        positions = tuple(bit%72+1 for bit in erased if bit//72 == word)
        if len(positions) > 3:
            return None
        result = m2_codec.eh72_decode(encoded[9*word:9*(word+1)], positions)
        if result.decoded is None:
            return None
        plain.extend(result.decoded)
    if plain[191] != 0:
        return None
    raw = bytes(plain[:191])
    try:
        bootstrap.decode_common_block(raw, 8)
    except bootstrap.BootstrapReject:
        return None
    return raw


def _repetition(lanes):
    combined, erased = bytearray(216), []
    masks = tuple(frozenset(unknown) for _, unknown in lanes)
    factor = len(lanes)
    for bit in range(1728):
        known = tuple((encoded[bit//8] >> (7-bit%8)) & 1
            for (encoded, _), mask in zip(lanes, masks, strict=True) if bit not in mask)
        ones, unknown = sum(known), factor-len(known)
        zeros = len(known)-ones
        zero, one = 2*ones+unknown < factor, 2*zeros+unknown < factor
        if zero == one:
            erased.append(bit)
        elif one:
            combined[bit//8] |= 128 >> (bit%8)
    return _local(bytes(combined), tuple(erased))


def build_formative_transfer_v2(image: DevelopmentCarrier) -> tuple[FormativeTransferCaseV2, ...]:
    """Build full matrix a/b from a fresh source carrier and its capacity plan.

    The returned observation is recipient data. Every other field and the
    owner_manifest are private construction/verification metadata.
    """
    _require(type(image) is DevelopmentCarrier and type(image.capacity_plan) is CapacityPlan,
             'source-type')
    plan, raw = image.capacity_plan, image.carrier
    mapping = mapping_parameters(plan.side, plan.width)
    _require(type(raw) is bytes and len(raw) == 4+(plan.side**2+7)//8
             and int.from_bytes(raw[:4], 'big') == plan.side**2
             and plan.units == mapping.units and 1 <= len(plan.sections) <= 818, 'source-shape')
    sections = plan.sections
    _require(tuple(row.section_id for row in sections)
             == tuple(sorted(set(row.section_id for row in sections)))
             and all(row.factor in (1, 2, 5) and 1 <= len(row.payload) <= 16384 for row in sections),
             'source-sections')
    candidates_a = tuple(row for row in sections if row.section_id != 1 and row.factor == 2 and row.fragments >= 3)
    candidates_b = tuple(row for row in sections if row.section_id != 1 and row.factor == 5
                         and row.closure == 128 and row.fragments >= 3)
    _require(candidates_a and candidates_b, 'selection')
    a = candidates_a[0]
    b = min(candidates_b, key=lambda row: (row.section_id not in (16, 17), row.section_id))
    selected, cursor = {}, 1
    for section in sections:
        if section.section_id in (a.section_id, b.section_id):
            envelope = bootstrap.encode_section_envelope(bootstrap.SectionEnvelope(
                section.section_id, section.section_type, section.version, section.closure,
                1, section.dependencies, section.payload))
            blocks = bootstrap.fragment_section(envelope, 8, 0)
            _require(len(blocks) == section.fragments, 'fragment-shape')
            selected[section.section_id] = (cursor+2*section.factor, blocks[2])
        cursor += section.fragments*section.factor
    _require(cursor == plan.units+1, 'source-population')
    clean = bytes((byte >> bit) & 1 for byte in raw[4:] for bit in range(7, -1, -1))

    def cell(unit, bit):
        physical = map_unit_bit(plan.side, plan.width, unit, bit)
        row, column = divmod(physical, mapping.interior)
        return (row+plan.width)*plan.side+column+plan.width

    source_sha = sha256(raw).hexdigest()
    cases = []
    for name, section in (('a', a), ('b', b)):
        first, expected = selected[section.section_id]
        original = m2_codec.eh72_encode_unit(expected)
        coordinates = tuple(tuple(cell(first+lane, bit) for bit in range(1728))
                            for lane in range(section.factor))
        for row in coordinates:
            _require(all(clean[flat] == (original[bit//8] >> (7-bit%8)) & 1
                         for bit, flat in enumerate(row)), 'source-lane-binding')
        foreign = selected[a.section_id][1] if name == 'b' else None
        lanes = []
        for lane in range(section.factor):
            encoded = bytearray(m2_codec.eh72_encode_unit(foreign) if name == 'b' and lane == 0 else original)
            erased = tuple(range(10*lane, 10*lane+5)) if name == 'a' else ()
            for bit in erased:
                encoded[bit//8] &= 255 ^ (128 >> (bit%8))
            if name == 'b' and lane:
                for bit in (32+2*(lane-1), 33+2*(lane-1)):
                    encoded[bit//8] ^= 128 >> (bit%8)
            lanes.append((bytes(encoded), erased))
        local = tuple(_local(encoded, erased) for encoded, erased in lanes)
        repeated = _repetition(lanes)
        _require(repeated == expected and local == ((None, None) if name == 'a'
                    else (foreign, None, None, None, None)), 'candidate-properties')
        candidates = {candidate for candidate in (*local, repeated) if candidate is not None}
        _require(candidates == ({expected} if name == 'a' else {foreign, expected})
                 and len(candidates) == (1 if name == 'a' else 2), 'candidate-union')
        matrix, edits = bytearray(clean), []
        for row, (encoded, erased) in zip(coordinates, lanes, strict=True):
            unknown = frozenset(erased)
            for bit, flat in enumerate(row):
                value = 2 if bit in unknown else (encoded[bit//8] >> (7-bit%8)) & 1
                if value != clean[flat]:
                    matrix[flat] = value
                    edits.append((flat, value))
        cases.append(FormativeTransferCaseV2(name, plan.side.to_bytes(2, 'big')+bytes(matrix),
            source_sha, section.section_id, 2, first, section.factor, expected, foreign,
            repeated, 'recovered' if name == 'a' else 'conflict', tuple(sorted(edits))))
    return tuple(cases)
