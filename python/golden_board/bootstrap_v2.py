"""Closed development inventory for profile8; historical entrypoints reject it."""
from dataclasses import dataclass
from . import bootstrap as base
from .body_codec_v1 import decode_body

REQUIRED_BODIES = (16, 17, 18)
ALL_BODIES = (*REQUIRED_BODIES, *range(100, 164), *range(200, 211))
SPINE = frozenset((1, 2, 3, *REQUIRED_BODIES))
PAYLOAD_MAX = 16_384


def _reject(path):
    raise base.BootstrapReject(base.INVENTORY, path)


def decode_inventory_entry_header(data):
    if type(data) is not bytes or len(data) != 20:
        _reject('inventory_v2.header')
    number = lambda start, end: int.from_bytes(data[start:end], 'big')
    sid, kind, version = number(0, 4), number(4, 6), number(6, 8)
    closure, check, copies, flags = data[8:12]
    deps, size, ordinal = number(12, 14), number(14, 18), number(18, 20)
    factor, has_ordinal = flags >> 1, bool(flags & 1)
    if (not 1 <= sid <= 0xffffffff or kind not in range(1, 7)
            or closure not in (128, 129) or check != 1 or copies != 1
            or flags & 0xf0 or factor not in (1, 2, 5)
            or (closure == 128) != (sid in SPINE)
            or (factor == 5) != (sid in SPINE)
            or not 1 <= size <= PAYLOAD_MAX or deps > base.DEPENDENCY_MAX
            or (has_ordinal and (kind != 3 or not 100 <= sid < 164 or ordinal != sid - 100))
            or (not has_ordinal and ordinal != 0xffff)
            or has_ordinal != (100 <= sid < 164)):
        _reject('inventory_v2.entry')
    if sid == 1:
        valid = kind == 1 and version == 2 and deps == 0
    elif sid in (2, 3):
        valid = kind == 2 and version == 0 and deps == (3 if sid == 2 else 78)
    elif sid in ALL_BODIES:
        valid = kind == 3 and version in (0, 1) and deps == 0
        if sid not in SPINE:
            valid = valid and factor == 1
    else:
        valid = (sid >= 211 and kind in (4, 5, 6) and version == 0 and deps == 0
                 and ((kind == 4 and factor in (1, 2))
                      or (kind == 5 and factor == 2) or (kind == 6 and factor == 1)))
    if not valid:
        _reject('inventory_v2.role')
    return factor, has_ordinal


def _validate_entries(entries):
    if not isinstance(entries, (tuple, list)) or not 3 <= len(entries) <= base.INVENTORY_ENTRY_MAX:
        _reject('inventory_v2.entry_count')
    for entry in entries:
        if type(entry) is not base.InventoryEntry:
            _reject('inventory_v2.entry_type')
        integer_fields = (entry.section_id, entry.section_type, entry.section_version,
                          entry.closure_class, entry.check_id, entry.copy_count,
                          entry.logical_payload_length, entry.physical_replica_count)
        if (any(type(value) is not int for value in integer_fields)
                or type(entry.dependencies) is not tuple
                or len(entry.dependencies) > base.DEPENDENCY_MAX
                or any(type(value) is not int for value in entry.dependencies)
                or (entry.game_ordinal is not None and type(entry.game_ordinal) is not int)):
            _reject('inventory_v2.field_type')
        if not 1 <= entry.section_id <= 0xffffffff:
            _reject('inventory_v2.section_id')
    by_id = {item.section_id: item for item in entries}
    if (len(by_id) != len(entries)
            or set(by_id) & set(range(1, 211)) != {1, 2, 3, *ALL_BODIES}
            or by_id[2].dependencies != REQUIRED_BODIES
            or by_id[3].dependencies != ALL_BODIES):
        _reject('inventory_v2.coverage')


def encode_inventory(inventory):
    if (type(inventory) is not base.Inventory or type(inventory.version) is not int
            or inventory.version != 2 or type(inventory.entries) is not tuple):
        _reject('inventory_v2.version')
    _validate_entries(inventory.entries)
    encoded = base._encode_inventory(inventory, maximum_inventory_version=2)
    if len(encoded) > PAYLOAD_MAX:
        _reject('inventory_v2.length')
    return encoded


def decode_inventory(raw):
    if (type(raw) is not bytes or not 8 <= len(raw) <= PAYLOAD_MAX or raw[:2] != b'\0\2'):
        _reject('inventory_v2.length_or_version')
    return base._decode_inventory(raw, maximum_inventory_version=2)


@dataclass(frozen=True, slots=True)
class ContentRecovery:
    required_bytes: bytes | None
    all_bytes: bytes | None
    checked_section_ids: tuple[int, ...]
    rejected_section_ids: tuple[int, ...]


def recover_content(section_bytes):
    """Check inventory/envelopes, decompress and validate both content tiers.

    Inputs are independently assembled section envelopes, never clean fallback
    bytes. This layer reports content availability; artifact state additionally
    depends on every inventory owner and the observed physical recovery.
    """
    if (type(section_bytes) is not dict or not 1 <= len(section_bytes) <= base.INVENTORY_ENTRY_MAX
            or any(type(sid) is not int or not 1 <= sid <= 0xffffffff
                   or type(raw) is not bytes for sid, raw in section_bytes.items())
            or 1 not in section_bytes):
        _reject('inventory_v2.sections')
    if len(section_bytes[1]) > PAYLOAD_MAX + 22:
        _reject('inventory_v2.section_length')
    first = base.decode_section_envelope(section_bytes[1])
    inventory = decode_inventory(first.payload)
    if first.section_id != 1:
        _reject('inventory_v2.section_id')
    base.validate_envelope_against_inventory(first, inventory)
    by_id = {entry.section_id: entry for entry in inventory.entries}
    if set(section_bytes) - set(by_id):
        _reject('inventory_v2.unowned_section')
    checked = {1: first}
    rejected = []
    for sid, raw in sorted(section_bytes.items()):
        if sid == 1:
            continue
        try:
            if len(raw) > PAYLOAD_MAX + 22 + 4 * len(ALL_BODIES):
                _reject('inventory_v2.section_length')
            envelope = base.decode_section_envelope(raw)
            if envelope.section_id != sid:
                _reject('inventory_v2.section_id')
            base.validate_envelope_against_inventory(envelope, inventory)
            checked[sid] = envelope
        except base.BootstrapReject:
            rejected.append(sid)

    def assemble(sid):
        try:
            envelope = checked[sid]
            frame = base.decode_tier_frame(envelope.payload, sid)
            base.validate_tier_against_inventory(frame, envelope, inventory)
            bodies = {body_id: decode_body(checked[body_id].section_version,
                                           checked[body_id].payload)
                      for body_id in frame.body_section_ids}
            return base.assemble_content_stream(frame, bodies)
        except (base.BootstrapReject, ValueError, KeyError):
            return None

    required = assemble(2)
    all_stream = assemble(3) if required is not None else None
    return ContentRecovery(required, all_stream, tuple(sorted(checked)), tuple(rejected))
