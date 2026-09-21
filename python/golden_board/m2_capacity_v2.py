"""Exact development-profile capacity, with logical reserve kept uncompressed."""

from dataclasses import dataclass, replace

from . import bootstrap, bootstrap_v2, body_codec_v1, capacity
from .m2_capacity_v1 import derive_capacity_inputs_v1
from .m2_mapping_v2 import mapping_parameters


@dataclass(frozen=True, slots=True)
class Section:
    section_id: int
    section_type: int
    version: int
    closure: int
    dependencies: tuple[int, ...]
    payload: bytes
    factor: int
    ordinal: int | None = None

    @property
    def fragments(self):
        return (22 + 4*len(self.dependencies) + len(self.payload) + 156)//157


@dataclass(frozen=True, slots=True)
class CapacityPlan:
    side: int
    width: int
    units: int
    pad_cells: int
    pad_bytes: bytes
    authoring_bytes: int
    reserve_bytes: int
    sections: tuple[Section, ...]
    inventory: bootstrap.Inventory
    headroom_cells: tuple[int, ...]
    search_rows: tuple[tuple[int, int, str], ...]


def _inventory_size(entries, dependencies):
    return 8 + 20*entries + 4*dependencies


def _layout(noninventory, units, dependencies):
    base_entries = 1 + len(noninventory)
    base_units = sum(s.fragments*s.factor for s in noninventory)
    maximum_count = min(4096-base_entries,
                        (16384 - 8 - 20*base_entries - 4*dependencies)//20)
    for count in range(maximum_count+1):
        size = _inventory_size(base_entries+count, dependencies)
        available = units - base_units - 5*((22+size+156)//157)
        if available < 0:
            break
        if count == 0 and available == 0:
            return ()
        if count and count <= available <= 105*count:
            payloads = []
            remaining = available
            for index in range(count):
                fragments = min(105, remaining-(count-index-1))
                length = min(16384, 157*fragments-22)
                if (22+length+156)//157 != fragments:
                    raise ValueError('load-fragment-reconciliation')
                payloads.append(length)
                remaining -= fragments
            if remaining:
                raise ValueError('load-remainder')
            return tuple(payloads)
    return None


def build_capacity_plan(compiled, prototype_source, blueprint, policy,
                        prefix_lengths: tuple[int, ...]) -> CapacityPlan:
    """Derive from source bytes and actual route lengths; no gate result implied."""
    if (type(prefix_lengths) is not tuple or len(prefix_lengths) != 4
            or any(type(n) is not int or not 64 <= n <= 32768 for n in prefix_lengths)):
        raise ValueError('route-prefix-lengths')
    inputs = derive_capacity_inputs_v1(compiled, prototype_source, blueprint)
    envelope = capacity.derive_capacity_envelope(inputs, policy)
    total_headroom = max((sum(prefix_lengths)*8+19)//20, 1024)
    extra, remainder = divmod(total_headroom-1024, 4)
    headrooms = tuple(256+extra+int(i<remainder) for i in range(4))
    frames = capacity._frames(compiled.content_bytes, 'v2-all')
    assignments = {a.section_id: a for a in compiled.atomic_assignments}
    sections = []
    for row in inputs.real_content_sections:
        source = b''.join(frames[rid] for rid in row.record_ids)
        version, encoded = body_codec_v1.encode_body(source)
        required = row.closure == 'm2_required'
        sections.append(Section(row.section_id, 3, version, 128 if required else 129,
                                (), encoded, 5 if required else 1,
                                assignments[row.section_id].game_ordinal))
    for tier in inputs.tier_frames:
        source = compiled.required_content_bytes if tier.section_id == 2 else compiled.content_bytes
        terminal = capacity._frames(source, 'v2-tier')[int.from_bytes(source[2:4], 'big')]
        payload = bootstrap.encode_tier_frame(bootstrap.TierFrame(
            tier.section_id-2, tier.body_section_ids, len(source),
            int.from_bytes(source[2:4], 'big'), terminal))
        if len(payload) != tier.logical_payload_length:
            raise ValueError('tier-capacity-reconciliation')
        sections.append(Section(tier.section_id, 2, 0, 128, tier.body_section_ids, payload, 5))
    logical_real = sum(s.payload_length for s in inputs.real_content_sections)
    logical_real += sum(t.logical_payload_length for t in inputs.tier_frames)
    reserve = capacity.reserve_requirement(logical_real+16384, envelope.authoring_payload_bytes)
    next_id = 211
    for bucket in envelope.buckets:
        for row in bucket.sections:
            if not row.payload_length:
                continue
            factors = {'replicated-core0-2': 2, 'nonreplicated-core3-4': 1}
            if row.protection_class not in factors or not 1 <= row.payload_length <= 16384:
                raise ValueError('capacity-probe-shape')
            sections.append(Section(next_id, 4, 0, 129, (), bytes(row.payload_length),
                                    factors[row.protection_class]))
            next_id += 1
    for length in capacity.partition_probe_payload(reserve, 16384):
        sections.append(Section(next_id, 5, 0, 129, (), bytes(length), 2))
        next_id += 1
    dependencies = sum(len(s.dependencies) for s in sections)
    selected = None
    search_rows = []
    for side in range(64, 2049, 8):
        for width in range(8, min(128, (side-8)//2)+1, 8):
            if any(n*8+h > width*(side-width) for n, h in zip(prefix_lengths, headrooms, strict=True)):
                search_rows.append((side, width, 'route-headroom'))
                continue
            try:
                mapping = mapping_parameters(side, width)
            except ValueError:
                search_rows.append((side, width, 'mapping-table'))
                continue
            load = _layout(sections, mapping.units, dependencies)
            if load is None:
                search_rows.append((side, width, 'inventory-load-fixed-point'))
                continue
            search_rows.append((side, width, 'fit'))
            selected = side, width, mapping, load
            break
        if selected is not None:
            break
    if selected is None:
        raise ValueError('no-carrier-fit-within-512KiB')
    side, width, mapping, load = selected
    for length in load:
        sections.append(Section(next_id, 6, 0, 129, (), bytes(length), 1))
        next_id += 1
    sections.sort(key=lambda s: s.section_id)
    pad_cells = mapping.population - mapping.units*1728
    probe_length = sum(len(s.payload) for s in sections if s.section_type in (4, 5, 6))
    fill = capacity.probe_fill_bytes(compiled.content_sha256, probe_length+(pad_cells+7)//8)
    cursor = 0
    for index, section in enumerate(sections):
        if section.section_type in (4, 5, 6):
            length = len(section.payload)
            sections[index] = replace(section, payload=fill[cursor:cursor+length])
            cursor += length
    if cursor != probe_length:
        raise ValueError('probe-fill-reconciliation')
    length = _inventory_size(1+len(sections), dependencies)
    entries = [bootstrap.InventoryEntry(1, 1, 2, 128, 1, 1, (), length,
                                       physical_replica_count=5)]
    entries.extend(bootstrap.InventoryEntry(s.section_id, s.section_type, s.version,
        s.closure, 1, 1, s.dependencies, len(s.payload), s.ordinal, s.factor) for s in sections)
    inventory = bootstrap.Inventory(tuple(entries), 2)
    payload = bootstrap_v2.encode_inventory(inventory)
    if len(payload) != length:
        raise ValueError('inventory-size-reconciliation')
    sections.insert(0, Section(1, 1, 2, 128, (), payload, 5))
    if (sum(s.fragments*s.factor for s in sections) != mapping.units
            or {s.section_id for s in sections if s.factor == 5} != bootstrap_v2.SPINE):
        raise ValueError('physical-cost-reconciliation')
    return CapacityPlan(side, width, mapping.units, pad_cells, fill[cursor:],
                        envelope.authoring_payload_bytes, reserve, tuple(sections), inventory,
                        headrooms, tuple(search_rows))
