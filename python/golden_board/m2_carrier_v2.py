"""Source-built development carrier and a separate clean-matrix recovery path.

Clean recovery is a roundtrip check, not damage/acquisition/Gate8 admission.
It consumes only the actual matrix and the explicitly supplied shell width.
"""

from dataclasses import dataclass
from math import isqrt

from . import bootstrap, bootstrap_v2, m2_codec, m2_route_data
from .m2_capacity_v2 import build_capacity_plan
from .m2_mapping_v2 import mapping_parameters
from .m2_route_v2 import build_route_prefixes_v2, build_route_images_v2
from .m2_transport_v2 import aggregate_replica_group


@dataclass(frozen=True, slots=True)
class DevelopmentCarrier:
    carrier: bytes
    capacity_plan: object
    route_prefixes: tuple[bytes, ...]
    owner_cell_counts: tuple[int, int, int]


def _bits(raw):
    return bytes((byte >> bit) & 1 for byte in raw for bit in range(7, -1, -1))


def _pack(bits):
    if len(bits) % 8:
        raise ValueError('matrix-bit-alignment')
    return bytes(sum(bits[i+j] << (7-j) for j in range(8)) for i in range(0, len(bits), 8))


def build_development_carrier(compiled, prototype_source, blueprint, policy):
    prefixes = build_route_prefixes_v2(compiled)
    plan = build_capacity_plan(compiled, prototype_source, blueprint, policy,
                               tuple(len(raw) for raw in prefixes))
    routes = build_route_images_v2(compiled, plan.side, plan.width)
    mapping = mapping_parameters(plan.side, plan.width)
    matrix, owners = bytearray(plan.side**2), bytearray(plan.side**2)

    def put(index, value, owner):
        if owners[index]:
            raise ValueError('cell-owner-overlap')
        owners[index], matrix[index] = owner, value

    for sector in routes.sectors:
        for offset, bit in enumerate(_bits(sector.data)):
            row, column = bootstrap.sector_cell(plan.side, plan.width, sector.sector_id, offset)
            put(row*plan.side+column, bit, 1)
    unit_count = 0
    for section in plan.sections:
        envelope = bootstrap.encode_section_envelope(bootstrap.SectionEnvelope(
            section.section_id, section.section_type, section.version, section.closure,
            1, section.dependencies, section.payload))
        fragments = bootstrap.fragment_section(envelope, 8, 0)
        if len(fragments) != section.fragments:
            raise ValueError('section-fragment-charge')
        for block in fragments:
            bits = _bits(m2_codec.eh72_encode_unit(block))
            if len(bits) != 1728:
                raise ValueError('encoded-unit-width')
            for _ in range(section.factor):
                slot = mapping.slot_multiplier*unit_count % mapping.units
                for bit_index, bit in enumerate(bits):
                    logical = 1728*slot+bit_index
                    physical = (mapping.cell_multiplier*logical+mapping.offset) % mapping.population
                    row, column = divmod(physical, mapping.interior)
                    put((row+plan.width)*plan.side+column+plan.width, bit, 2)
                unit_count += 1
    if unit_count != plan.units:
        raise ValueError('physical-unit-charge')
    for index, bit in enumerate(_bits(plan.pad_bytes)[:plan.pad_cells]):
        logical = 1728*unit_count+index
        physical = (mapping.cell_multiplier*logical+mapping.offset) % mapping.population
        row, column = divmod(physical, mapping.interior)
        put((row+plan.width)*plan.side+column+plan.width, bit, 3)
    if 0 in owners:
        raise ValueError('cell-owner-gap')
    counts = tuple(owners.count(kind) for kind in (1, 2, 3))
    if counts != (4*plan.width*(plan.side-plan.width), plan.units*1728, plan.pad_cells):
        raise ValueError('owner-cell-counts')
    raw = len(matrix).to_bytes(4, 'big') + _pack(matrix)
    return DevelopmentCarrier(raw, plan, prefixes, counts)


def recover_clean_matrix(carrier: bytes, shell_width: int):
    """Recover all content from physical cells, without builder section inputs."""
    if type(carrier) is not bytes or not 4 <= len(carrier) <= 524292:
        raise ValueError('carrier-framing')
    count = int.from_bytes(carrier[:4], 'big')
    side = isqrt(count)
    if side*side != count or len(carrier) != 4+(count+7)//8:
        raise ValueError('carrier-square-or-length')
    mapping = mapping_parameters(side, shell_width)
    matrix = _bits(carrier[4:])
    if len(matrix) != count:
        raise ValueError('carrier-padding')

    def observation(unit_id):
        if not 1 <= unit_id <= mapping.units:
            raise ValueError('physical-unit-domain')
        # Decoder iterates physical bits with its own arithmetic path; it
        # never reads or receives builder envelopes, units, plan or fill.
        slot = ((unit_id-1)*mapping.slot_multiplier) % mapping.units
        start = (1728*slot*mapping.cell_multiplier + mapping.offset) % mapping.population
        bits = bytearray()
        physical = start
        for _ in range(1728):
            row, column = divmod(physical, mapping.interior)
            bits.append(matrix[(row+shell_width)*side+column+shell_width])
            physical = (physical+mapping.cell_multiplier) % mapping.population
        return m2_codec.CopyObservation(_pack(bits), ())

    groups = {}

    def group(first, factor):
        if (first, factor) not in groups:
            rows = tuple(observation(first+i) for i in range(factor))
            result = aggregate_replica_group(rows)
            if result.group_state != 2 or result.distinct_candidate_count != 1:
                raise ValueError('clean-group-not-verified')
            groups[(first, factor)] = result.chosen_block
        return groups[(first, factor)]

    first = bootstrap.decode_common_block(group(1, 5), 8)
    if (first.section_id, first.semantic_copy_id, first.section_type,
            first.section_version, first.fragment_index) != (1, 0, 1, 2, 0):
        raise ValueError('inventory-bootstrap-identity')
    if not 1 <= first.fragment_count <= 105 or first.section_envelope_length > 16406:
        raise ValueError('inventory-bootstrap-bound')
    blocks = tuple(group(1+5*i, 5) for i in range(first.fragment_count))
    _, inventory_envelope = bootstrap.assemble_semantic_copy(blocks, 8)
    inventory = bootstrap_v2.decode_inventory(bootstrap.decode_section_envelope(inventory_envelope).payload)
    sections = {}
    next_id = 1
    for entry in inventory.entries:
        envelope_length = 22+4*len(entry.dependencies)+entry.logical_payload_length
        fragments = (envelope_length+156)//157
        accepted = []
        for ordinal in range(fragments):
            raw = group(next_id, entry.physical_replica_count)
            block = bootstrap.decode_common_block(raw, 8)
            if (block.section_id, block.semantic_copy_id, block.section_type, block.section_version,
                block.fragment_index, block.fragment_count, block.section_envelope_length) != (
                entry.section_id, 0, entry.section_type, entry.section_version, ordinal,
                fragments, envelope_length):
                raise ValueError('physical-group-identity')
            accepted.append(raw)
            next_id += entry.physical_replica_count
        _, envelope = bootstrap.assemble_semantic_copy(accepted, 8)
        sections[entry.section_id] = envelope
    if next_id != mapping.units+1 or sections[1] != inventory_envelope:
        raise ValueError('physical-inventory-completeness')
    result = bootstrap_v2.recover_content(sections)
    if result.required_bytes is None or result.all_bytes is None or result.rejected_section_ids:
        raise ValueError('clean-content-incomplete')
    return result
