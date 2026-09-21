"""Independent logical compiler for the participant-revised M2 slice."""
from __future__ import annotations

from dataclasses import fields
import hashlib

from . import canonical_manifest as manifest, content as c
from .m2_slice import (SliceAtomicAssignment, SliceCompilation, SliceError,
                       SliceTierRoot, compile_slice_v0, _content_frames)


def _fail(path):
    raise SliceError('invalid_slice_v1', path)


def _object(value, keys, path):
    if type(value) is not dict or set(value) != set(keys):
        _fail(path)
    return value


def _integer(value, maximum, path):
    if type(value) is not int or not 0 <= value <= maximum:
        _fail(path)
    return value


def _array(value, path):
    if type(value) is not list or len(value) > 65535:
        _fail(path)
    return value


_TYPES = {
    2:c.ContentAtomSchema, 3:c.ContentAtomVector, 4:c.ContentMatrix,
    7:c.ContentRegionSet, 8:c.ContentSemanticBinding, 9:c.ContentOpaqueData,
    10:c.ContentPredicateResult, 11:c.ContentFeedback, 12:c.ContentPassiveTrace,
    13:c.ContentLessonNode, 14:c.ContentRoot,
}
_SEQUENCES = {'atoms', 'cells', 'data', 'region_ids'}


def _value(cls, value, path):
    names = [field.name for field in fields(cls)]
    if cls is c.ContentAtomSchema:
        names = ['atom_class', 'atom_width', 'min_value', 'max_value']
    row = _object(value, names, path)
    result = {}
    for name, item in row.items():
        here = f'{path}.{name}'
        if name in _SEQUENCES:
            result[name] = tuple(_integer(number, 0xffffffff, here)
                                 for number in _array(item, here))
        elif name in ('regions', 'cases'):
            nested = c.ContentRegion if name == 'regions' else c.ContentLessonCase
            result[name] = tuple(_value(nested, part, here) for part in _array(item, here))
        elif name == 'actions':
            actions = []
            for action in _array(item, here):
                if type(action) is not str or len(action) != 8 or any(
                    char not in '0123456789abcdef' for char in action
                ):
                    _fail(here)
                actions.append(bytes.fromhex(action))
            result[name] = tuple(actions)
        else:
            result[name] = _integer(item, 0xffffffff, here)
    if cls is c.ContentAtomSchema and result != dict(
        atom_class=1, atom_width=1, min_value=0, max_value=255
    ):
        _fail(path)
    return cls(**result)


def compile_slice_v1(declaration, legacy_declaration, content_fixture,
                     chess_fixture, game_set, content_spec, constants, curriculum):
    """Compile v1 without trusting generated content or a retained carrier."""
    row = manifest.validate_canonical_manifest(declaration)
    _object(row, ('schema', 'legacy_declaration_sha256', 'lesson_records'), 'declaration')
    if row['schema'] != 'golden-board.m2-slice/v1' or row['legacy_declaration_sha256'] != hashlib.sha256(legacy_declaration).hexdigest():
        _fail('source_binding')
    legacy = compile_slice_v0(legacy_declaration, content_fixture, chess_fixture,
                              game_set, content_spec, constants, curriculum)
    logical = _array(row['lesson_records'], 'lesson_records')
    if not 1 <= len(logical) <= 4096:
        _fail('lesson_records')
    records = []
    for index, record in enumerate(logical, 1):
        item = _object(record, ('record_id', 'kind', 'payload'), 'record')
        if _integer(item['record_id'], 65535, 'record_id') != index:
            _fail('record_id')
        kind = _integer(item['kind'], 14, 'kind')
        if kind not in _TYPES:
            _fail('kind')
        records.append(c.ContentRecordView(index, _value(_TYPES[kind], item['payload'], f'record[{index}]')))
    required = c.encode_content_v0(c.ContentAuthoringProjection(0, tuple(records)))
    required_view = c.projection_view(c.stream_validation(required))
    root = records[-1].payload
    if not isinstance(root, c.ContentRoot) or not isinstance(records[0].payload, c.ContentAtomSchema):
        _fail('required_root')
    entry = records[root.entry_node_ref - 1].payload
    if not isinstance(entry, c.ContentLessonNode) or not entry.predicate_result_ref:
        _fail('entry')
    regions = records[entry.region_set_ref - 1].payload
    if not isinstance(regions, c.ContentRegionSet) or not {1, 2}.issubset(
        {region.region_id for region in regions.regions if region.flags & 1}
    ):
        _fail('entry_regions')

    # A shared body frame never changes between required and all tiers.
    records.pop()
    frames = _content_frames(required, 'required')
    assignments = []
    group, size, section = [], 0, 16
    for record in records:
        length = len(frames[record.record_id])
        if length > 16384:
            _fail('record_too_large')
        if size + length > 16384:
            assignments.append(SliceAtomicAssignment(section, 'm2_required', 0, tuple(group), None, None))
            group, size, section = [], 0, section + 1
        group.append(record.record_id)
        size += length
    if group:
        assignments.append(SliceAtomicAssignment(section, 'm2_required', 0, tuple(group), None, None))
    if section > 31:
        _fail('required_section_limit')

    def add(payload):
        record_id = len(records) + 1
        records.append(c.ContentRecordView(record_id, payload))
        return record_id

    payload_ids = []
    for namespace, start, payloads in ((2, 100, legacy.game_payloads), (3, 200, legacy.fixture_payloads)):
        for ordinal, payload in enumerate(payloads):
            binding_id = add(c.ContentSemanticBinding(1, namespace, ordinal + 1, 1, len(payload)))
            payload_id = add(c.ContentOpaqueData(binding_id, tuple(payload)))
            payload_ids.append(payload_id)
            assignments.append(SliceAtomicAssignment(start + ordinal, 'm2_all_only', 0,
                (binding_id, payload_id), ordinal if namespace == 2 else None,
                ordinal if namespace == 3 else None))
    support_start = len(records) + 1
    label = add(c.ContentText('0'))
    payload_label = add(c.ContentText('1'))
    limitation = add(c.ContentText('Inspecting raw records alone does not establish their chess meaning.'))
    matrix = add(c.ContentMatrix(1, 1, 1, (74,)))
    regions = add(c.ContentRegionSet(matrix, (c.ContentRegion(1, 0, 0, 1, 0, 1, 1),)))
    schema = add(c.ContentFieldSchema((c.ContentFieldSpec(label, 2, 4, 1),
                                     c.ContentFieldSpec(payload_label, 2, 9, 74))))
    library = add(c.ContentTuple(schema, (c.ContentRecordRefFieldValue((matrix,)),
                                        c.ContentRecordRefFieldValue(tuple(payload_ids)))))
    feedback = add(c.ContentFeedback(5, library, 0))
    trace = add(c.ContentPassiveTrace(matrix, regions, library, limitation,
        (bytes.fromhex('01000001'), bytes.fromhex('03000000')), 3, feedback, root.entry_node_ref))
    node = add(c.ContentLessonNode(4, 1, 3, 0, matrix, regions, 0, trace, 1, 16,
                                  (), feedback, root.entry_node_ref))
    assignments.append(SliceAtomicAssignment(210, 'm2_all_only', 0,
                       tuple(range(support_start, node + 1)), None, None))
    all_root = add(c.ContentRoot(node, root.global_event_budget + 64))
    stream = c.encode_content_v0(c.ContentAuthoringProjection(0, tuple(records)))
    view = c.projection_view(c.stream_validation(stream))
    all_frames = _content_frames(stream, 'all')
    if any(sum(len(all_frames[index]) for index in assignment.record_ids) > 16384
           for assignment in assignments):
        _fail('section_too_large')
    if b''.join((stream[:4], *(all_frames[index] for assignment in assignments
                for index in assignment.record_ids), all_frames[all_root])) != stream:
        _fail('section_coverage')
    return SliceCompilation(required, hashlib.sha256(required).hexdigest(), required_view,
        stream, hashlib.sha256(stream).hexdigest(), view, legacy.game_payloads,
        legacy.fixture_payloads, tuple(assignments), legacy.capacity_prototypes,
        (SliceTierRoot(2, 'm2_required', 0, required_view.root_record_id),
         SliceTierRoot(3, 'm2_all', 0, all_root)), legacy.chess_fixture_cases,
        legacy.selected_curriculum_families)
