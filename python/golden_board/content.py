"""Independent, bounded generic content-v0 parser and runtime."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import NoReturn

from . import constants as C


__all__ = (
    "ContentReject",
    "InvalidHostState",
    "stream_validation",
    "new_run",
    "step",
    "advance_committed",
    "encode_run_state",
    "validate_run_state",
)

_AUTHORITY = object()


class _AuthorityMeta(type):
    def __call__(cls, *args, _token=None, **kwargs):
        if _token is not _AUTHORITY:
            raise TypeError(f"{cls.__name__} is created by content-v0 operations")
        return super().__call__(*args, **kwargs)


class ContentReject(ValueError):
    """The stable content-v0 rejection datum."""

    __slots__ = ("_code", "_raw_start", "_raw_end")

    def __init__(self, code: int, raw_start: int, raw_end: int):
        if any(type(value) is not int for value in (code, raw_start, raw_end)):
            raise TypeError("code and span endpoints must be exact integers")
        if not 1 <= code <= C.CONTENT_BAD_RUN_STATE:
            raise ValueError("code is not a content-v0 rejection")
        if not 0 <= raw_start <= raw_end <= 0xFFFFFFFF:
            raise ValueError("span is not a canonical u32 range")
        self._code = code
        self._raw_start = raw_start
        self._raw_end = raw_end
        super().__init__(code, raw_start, raw_end)

    @property
    def code(self) -> int:
        return self._code

    @property
    def raw_start(self) -> int:
        return self._raw_start

    @property
    def raw_end(self) -> int:
        return self._raw_end


class InvalidHostState(ValueError):
    """A noncanonical host-programming failure."""


def _reject(code: int, start: int, end: int) -> NoReturn:
    raise ContentReject(code, start, end)


_KINDS = frozenset(
    (
        C.CONTENT_KIND_TEXT,
        C.CONTENT_KIND_ATOM_SCHEMA,
        C.CONTENT_KIND_ATOM_VECTOR,
        C.CONTENT_KIND_MATRIX,
        C.CONTENT_KIND_FIELD_SCHEMA,
        C.CONTENT_KIND_TUPLE,
        C.CONTENT_KIND_REGION_SET,
        C.CONTENT_KIND_SEMANTIC_BINDING,
        C.CONTENT_KIND_OPAQUE_DATA,
        C.CONTENT_KIND_PREDICATE_RESULT,
        C.CONTENT_KIND_FEEDBACK,
        C.CONTENT_KIND_PASSIVE_TRACE,
        C.CONTENT_KIND_LESSON_NODE,
        C.CONTENT_KIND_ROOT,
    )
)
_MIN_PAYLOAD = {
    C.CONTENT_KIND_TEXT: 1,
    C.CONTENT_KIND_ATOM_SCHEMA: 5,
    C.CONTENT_KIND_ATOM_VECTOR: 4,
    C.CONTENT_KIND_MATRIX: 7,
    C.CONTENT_KIND_FIELD_SCHEMA: 10,
    C.CONTENT_KIND_TUPLE: 3,
    C.CONTENT_KIND_REGION_SET: 18,
    C.CONTENT_KIND_SEMANTIC_BINDING: 10,
    C.CONTENT_KIND_OPAQUE_DATA: 3,
    C.CONTENT_KIND_PREDICATE_RESULT: 6,
    C.CONTENT_KIND_FEEDBACK: 6,
    C.CONTENT_KIND_PASSIVE_TRACE: 20,
    C.CONTENT_KIND_LESSON_NODE: 22,
    C.CONTENT_KIND_ROOT: 4,
}
_EXACT_PAYLOAD = {
    C.CONTENT_KIND_SEMANTIC_BINDING: 10,
    C.CONTENT_KIND_PREDICATE_RESULT: 6,
    C.CONTENT_KIND_FEEDBACK: 6,
    C.CONTENT_KIND_ROOT: 4,
}


def _u16(raw: memoryview, start: int) -> int:
    return (raw[start] << 8) | raw[start + 1]


def _u32(raw: memoryview, start: int) -> int:
    return (_u16(raw, start) << 16) | _u16(raw, start + 2)


@dataclass(frozen=True, slots=True)
class _Descriptor:
    record_id: int
    kind: int
    start: int
    length_start: int
    payload_start: int
    payload_end: int


@dataclass(frozen=True, slots=True)
class _Record:
    record_id: int
    kind: int


@dataclass(frozen=True, slots=True)
class _Text(_Record):
    text: str


@dataclass(frozen=True, slots=True)
class _AtomEntry:
    value: int
    label_text_ref: int


@dataclass(frozen=True, slots=True)
class _AtomSchema(_Record):
    atom_class: int
    atom_width: int
    entry_count: int
    min_value: int = 0
    max_value: int = 0
    allowed_mask: int = 0
    entries: tuple[_AtomEntry, ...] = ()


@dataclass(frozen=True, slots=True)
class _AtomVector(_Record):
    atom_schema_ref: int
    atom_count: int
    atoms: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class _Matrix(_Record):
    atom_schema_ref: int
    rows: int
    columns: int
    cells: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class _Field:
    name_text_ref: int
    storage: int
    type: int
    count: int


@dataclass(frozen=True, slots=True)
class _FieldSchema(_Record):
    field_count: int
    fields: tuple[_Field, ...]
    tuple_width: int = 0


@dataclass(frozen=True, slots=True)
class _Tuple(_Record):
    field_schema_ref: int
    field_values: tuple[tuple[int, ...], ...] = ()
    presentation_count: int = 0
    presentation_matrix: int = 0


@dataclass(frozen=True, slots=True)
class _Region:
    region_id: int
    label_ref: int
    row_start: int
    row_end: int
    column_start: int
    column_end: int
    flags: int


@dataclass(frozen=True, slots=True)
class _RegionSet(_Record):
    surface_matrix_ref: int
    region_count: int
    regions: tuple[_Region, ...]


@dataclass(frozen=True, slots=True)
class _Binding(_Record):
    binding_class: int
    namespace_id: int
    semantic_code: int
    argument: int
    auxiliary: int


@dataclass(frozen=True, slots=True)
class _Opaque(_Record):
    data_binding_ref: int
    data: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class _Predicate(_Record):
    predicate_binding_ref: int
    subject_opaque_data_ref: int
    result_atom_vector_ref: int


@dataclass(frozen=True, slots=True)
class _Feedback(_Record):
    feedback_code: int
    display_ref: int
    predicate_result_ref: int


@dataclass(frozen=True, slots=True)
class _Passive(_Record):
    presentation_ref: int
    region_set_ref: int
    resulting_presentation_ref: int
    limitation_text_ref: int
    action_count: int
    actions: tuple[bytes, ...]
    expected_outcome: int
    expected_feedback_ref: int
    expected_next_node_ref: int


@dataclass(frozen=True, slots=True)
class _Case:
    case_class: int
    region_ids: tuple[int, ...]
    feedback_ref: int
    next_node_ref: int


@dataclass(frozen=True, slots=True)
class _Lesson(_Record):
    role: int
    response_shape: int
    answer_mode: int
    flags: int
    presentation_ref: int
    region_set_ref: int
    predicate_result_ref: int
    passive_trace_ref: int
    max_selections: int
    item_event_budget: int
    cases: tuple[_Case, ...]
    default_feedback_ref: int
    default_next_node_ref: int


@dataclass(frozen=True, slots=True)
class _Root(_Record):
    entry_node_ref: int
    global_event_budget: int


_DISPLAY_KINDS = frozenset(
    (
        C.CONTENT_KIND_TEXT,
        C.CONTENT_KIND_ATOM_VECTOR,
        C.CONTENT_KIND_MATRIX,
        C.CONTENT_KIND_TUPLE,
        C.CONTENT_KIND_OPAQUE_DATA,
    )
)
_VALUE_KINDS = _DISPLAY_KINDS
_ROLES = frozenset(
    (
        C.ROLE_EXACT_RULE,
        C.ROLE_OBSERVABLE_RELATION,
        C.ROLE_WORKED_EXAMPLE,
        C.ROLE_HEURISTIC,
        C.ROLE_PRACTICE,
    )
)
_SHAPES = frozenset((C.RESPONSE_SINGLE, C.RESPONSE_SET, C.RESPONSE_SEQUENCE))
_MODES = frozenset((C.ANSWER_PACKED_PRACTICE, C.ANSWER_EXTERNAL, C.ANSWER_UNSCORED))
_CASE_CLASSES = frozenset((C.CASE_ACCEPTED, C.CASE_REJECTED_SPECIAL))
_FEEDBACK_CODES = frozenset(
    (
        C.FEEDBACK_NEUTRAL,
        C.FEEDBACK_MATCH,
        C.FEEDBACK_NO_MATCH,
        C.FEEDBACK_ALTERNATIVE,
        C.FEEDBACK_LIMITATION,
    )
)
_OUTCOMES = frozenset((C.OUTCOME_ACCEPTED, C.OUTCOME_REJECTED, C.OUTCOME_NEUTRAL))
_CALLABLE_ACTIONS = frozenset((C.ACTION_SELECT, C.ACTION_RESET, C.ACTION_COMMIT))


def _need(length: int, offset: int, count: int, code: int = C.CONTENT_TRUNCATED) -> None:
    if count > length - offset:
        _reject(code, length, length)


def _frame(data: bytes) -> tuple[memoryview, tuple[_Descriptor, ...]]:
    length = len(data)
    if length > C.CONTENT_MAX_STREAM_BYTES:
        _reject(
            C.CONTENT_LIMIT_EXCEEDED,
            C.CONTENT_MAX_STREAM_BYTES,
            C.CONTENT_MAX_STREAM_BYTES + 1,
        )
    raw = memoryview(data)
    _need(length, 0, 2)
    version = _u16(raw, 0)
    _need(length, 2, 2)
    count = _u16(raw, 2)
    if version != C.CONTENT_VERSION:
        _reject(C.CONTENT_BAD_VERSION, 0, 2)
    if not C.CONTENT_MIN_RECORDS <= count <= C.CONTENT_MAX_RECORDS:
        _reject(C.CONTENT_BAD_RECORD_COUNT, 2, 4)

    descriptors: list[_Descriptor] = []
    kind_counts: dict[int, int] = {}
    offset = 4
    previous_id = 0
    for _ in range(count):
        _need(length, offset, 8)
        record_id = _u16(raw, offset)
        kind = _u16(raw, offset + 2)
        payload_length = _u32(raw, offset + 4)
        candidates: list[tuple[int, int, int]] = []
        if record_id == 0:
            candidates.append((offset, C.CONTENT_BAD_RECORD_ID, offset + 2))
        elif record_id <= previous_id:
            candidates.append((offset, C.CONTENT_RECORD_ORDER, offset + 2))
        seen = 0
        if kind not in _KINDS:
            candidates.append((offset + 2, C.CONTENT_BAD_RECORD_KIND, offset + 4))
        else:
            seen = kind_counts.get(kind, 0) + 1
            if (
                kind != C.CONTENT_KIND_ROOT
                and seen > C.CONTENT_MAX_RECORDS_PER_NON_ROOT_KIND
            ):
                candidates.append((offset + 2, C.CONTENT_LIMIT_EXCEEDED, offset + 4))
            if payload_length > C.CONTENT_MAX_PAYLOAD_BYTES or (
                kind == C.CONTENT_KIND_TEXT
                and payload_length > C.CONTENT_MAX_TEXT_BYTES
            ):
                candidates.append((offset + 4, C.CONTENT_LIMIT_EXCEEDED, offset + 8))
        if candidates:
            start, code, end = min(candidates, key=lambda item: (item[0], item[1]))
            _reject(code, start, end)
        kind_counts[kind] = seen
        payload_start = offset + 8
        _need(length, payload_start, payload_length)
        payload_end = payload_start + payload_length
        if payload_length < _MIN_PAYLOAD[kind] or (
            kind in _EXACT_PAYLOAD and payload_length != _EXACT_PAYLOAD[kind]
        ):
            _reject(C.CONTENT_BAD_PAYLOAD_LENGTH, offset + 4, offset + 8)
        descriptors.append(
            _Descriptor(
                record_id,
                kind,
                offset,
                offset + 4,
                payload_start,
                payload_end,
            )
        )
        previous_id = record_id
        offset = payload_end
    if offset != length:
        _reject(C.CONTENT_TRAILING_DATA, offset, offset + 1)
    return raw, tuple(descriptors)


def _atom(raw: memoryview, start: int, width: int) -> int:
    if width == 1:
        return raw[start]
    if width == 2:
        return _u16(raw, start)
    return _u32(raw, start)


def _length(desc: _Descriptor, expected: int) -> None:
    if desc.payload_end - desc.payload_start != expected:
        _reject(C.CONTENT_BAD_PAYLOAD_LENGTH, desc.length_start, desc.length_start + 4)


def _decode_text(raw: memoryview, desc: _Descriptor) -> _Text:
    payload = bytes(raw[desc.payload_start : desc.payload_end])
    try:
        value = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        start = desc.payload_start + error.start
        end = desc.payload_start + (
            error.end if error.reason == "unexpected end of data" else error.start + 1
        )
        _reject(C.CONTENT_BAD_UTF8, start, end)
    offset = desc.payload_start
    for index, character in enumerate(value):
        encoded = character.encode("utf-8")
        codepoint = ord(character)
        if (
            (codepoint < 0x20 and codepoint != 0x0A)
            or 0x7F <= codepoint <= 0x9F
            or (index == 0 and codepoint == 0xFEFF)
        ):
            _reject(C.CONTENT_BAD_VALUE, offset, offset + len(encoded))
        offset += len(encoded)
    return _Text(desc.record_id, desc.kind, value)


def _decode_schema(raw: memoryview, desc: _Descriptor) -> _AtomSchema:
    start = desc.payload_start
    atom_class = raw[start]
    width = raw[start + 1]
    count = _u16(raw, start + 2)
    if atom_class not in (C.ATOM_UNSIGNED, C.ATOM_ENUM, C.ATOM_MASK):
        _reject(C.CONTENT_BAD_TAG, start, start + 1)
    if width not in (1, 2, 4):
        _reject(C.CONTENT_BAD_TAG, start + 1, start + 2)
    if count > C.CONTENT_MAX_ENUM_ENTRIES:
        _reject(C.CONTENT_LIMIT_EXCEEDED, start + 2, start + 4)
    if atom_class == C.ATOM_UNSIGNED:
        if count != 0:
            _reject(C.CONTENT_BAD_COUNT, start + 2, start + 4)
        _length(desc, 4 + 2 * width)
        minimum = _atom(raw, start + 4, width)
        maximum = _atom(raw, start + 4 + width, width)
        if minimum > maximum:
            _reject(C.CONTENT_BAD_VALUE, start + 4 + width, start + 4 + 2 * width)
        return _AtomSchema(
            desc.record_id, desc.kind, atom_class, width, count, minimum, maximum
        )
    if atom_class == C.ATOM_ENUM:
        if count == 0:
            _reject(C.CONTENT_BAD_COUNT, start + 2, start + 4)
        _length(desc, 4 + count * (width + 2))
        entries: list[_AtomEntry] = []
        offset = start + 4
        previous = -1
        for _ in range(count):
            code = _atom(raw, offset, width)
            if code <= previous:
                _reject(
                    C.CONTENT_DUPLICATE if code == previous else C.CONTENT_NONCANONICAL_ORDER,
                    offset,
                    offset + width,
                )
            entries.append(_AtomEntry(code, _u16(raw, offset + width)))
            previous = code
            offset += width + 2
        return _AtomSchema(
            desc.record_id,
            desc.kind,
            atom_class,
            width,
            count,
            entries=tuple(entries),
        )

    _length(desc, 4 + width + count * (width + 2))
    allowed = _atom(raw, start + 4, width)
    if count != allowed.bit_count():
        _reject(C.CONTENT_BAD_COUNT, start + 2, start + 4)
    entries = []
    offset = start + 4 + width
    previous = -1
    for _ in range(count):
        bit = _atom(raw, offset, width)
        if bit == 0 or bit & (bit - 1) or bit & ~allowed:
            _reject(C.CONTENT_BAD_VALUE, offset, offset + width)
        if bit <= previous:
            _reject(
                C.CONTENT_DUPLICATE if bit == previous else C.CONTENT_NONCANONICAL_ORDER,
                offset,
                offset + width,
            )
        entries.append(_AtomEntry(bit, _u16(raw, offset + width)))
        previous = bit
        offset += width + 2
    return _AtomSchema(
        desc.record_id,
        desc.kind,
        atom_class,
        width,
        count,
        allowed_mask=allowed,
        entries=tuple(entries),
    )


def _decode_field_schema(raw: memoryview, desc: _Descriptor) -> _FieldSchema:
    start = desc.payload_start
    count = _u16(raw, start)
    if count == 0:
        _reject(C.CONTENT_BAD_COUNT, start, start + 2)
    if count > C.CONTENT_MAX_FIELD_SCHEMA_FIELDS:
        _reject(C.CONTENT_LIMIT_EXCEEDED, start, start + 2)
    _length(desc, 2 + 8 * count)
    fields: list[_Field] = []
    slots = 0
    for index in range(count):
        offset = start + 2 + index * 8
        storage = raw[offset + 2]
        if storage not in (C.FIELD_INLINE_ATOM, C.FIELD_RECORD_REF):
            _reject(C.CONTENT_BAD_TAG, offset + 2, offset + 3)
        if raw[offset + 3] != 0:
            _reject(C.CONTENT_RESERVED_NONZERO, offset + 3, offset + 4)
        field_type = _u16(raw, offset + 4)
        if storage == C.FIELD_RECORD_REF and field_type not in _VALUE_KINDS:
            _reject(C.CONTENT_BAD_TAG, offset + 4, offset + 6)
        item_count = _u16(raw, offset + 6)
        if item_count == 0:
            _reject(C.CONTENT_BAD_COUNT, offset + 6, offset + 8)
        if item_count > C.CONTENT_MAX_TUPLE_SLOTS:
            _reject(C.CONTENT_LIMIT_EXCEEDED, offset + 6, offset + 8)
        slots += item_count
        if slots > C.CONTENT_MAX_TUPLE_SLOTS:
            _reject(C.CONTENT_LIMIT_EXCEEDED, offset + 6, offset + 8)
        fields.append(_Field(_u16(raw, offset), storage, field_type, item_count))
    return _FieldSchema(desc.record_id, desc.kind, count, tuple(fields))


def _decode_regions(raw: memoryview, desc: _Descriptor) -> _RegionSet:
    start = desc.payload_start
    count = _u16(raw, start + 2)
    if count == 0:
        _reject(C.CONTENT_BAD_COUNT, start + 2, start + 4)
    if count > C.CONTENT_MAX_REGIONS:
        _reject(C.CONTENT_LIMIT_EXCEEDED, start + 2, start + 4)
    _length(desc, 4 + 14 * count)
    regions: list[_Region] = []
    previous = 0
    for index in range(count):
        offset = start + 4 + index * 14
        region_id = _u16(raw, offset)
        if region_id == 0:
            _reject(C.CONTENT_BAD_VALUE, offset, offset + 2)
        if region_id <= previous:
            _reject(
                C.CONTENT_DUPLICATE
                if region_id == previous
                else C.CONTENT_NONCANONICAL_ORDER,
                offset,
                offset + 2,
            )
        row_start = _u16(raw, offset + 4)
        row_end = _u16(raw, offset + 6)
        column_start = _u16(raw, offset + 8)
        column_end = _u16(raw, offset + 10)
        if row_start >= row_end:
            _reject(C.CONTENT_BAD_VALUE, offset + 6, offset + 8)
        if column_start >= column_end:
            _reject(C.CONTENT_BAD_VALUE, offset + 10, offset + 12)
        flags = raw[offset + 12]
        if flags & ~(C.REGION_SELECTABLE | C.REGION_HIGHLIGHTED):
            _reject(C.CONTENT_RESERVED_NONZERO, offset + 12, offset + 13)
        if raw[offset + 13] != 0:
            _reject(C.CONTENT_RESERVED_NONZERO, offset + 13, offset + 14)
        regions.append(
            _Region(
                region_id,
                _u16(raw, offset + 2),
                row_start,
                row_end,
                column_start,
                column_end,
                flags,
            )
        )
        previous = region_id
    return _RegionSet(desc.record_id, desc.kind, _u16(raw, start), count, tuple(regions))


def _decode_binding(
    raw: memoryview, desc: _Descriptor, keys: set[tuple[int, int, int]]
) -> _Binding:
    start = desc.payload_start
    binding_class = raw[start]
    if binding_class not in (C.BINDING_DATA, C.BINDING_PREDICATE):
        _reject(C.CONTENT_BAD_TAG, start, start + 1)
    if raw[start + 1] != 0:
        _reject(C.CONTENT_RESERVED_NONZERO, start + 1, start + 2)
    namespace = _u16(raw, start + 2)
    semantic = _u16(raw, start + 4)
    auxiliary = _u16(raw, start + 8)
    if namespace == 0:
        _reject(C.CONTENT_BAD_VALUE, start + 2, start + 4)
    if semantic == 0:
        _reject(C.CONTENT_BAD_VALUE, start + 4, start + 6)
    key = (binding_class, namespace, semantic)
    if key in keys:
        _reject(C.CONTENT_DUPLICATE, start, start + 1)
    keys.add(key)
    if binding_class == C.BINDING_DATA:
        if auxiliary == 0:
            _reject(C.CONTENT_BAD_COUNT, start + 8, start + 10)
        if auxiliary > C.CONTENT_MAX_OPAQUE_ATOMS:
            _reject(C.CONTENT_LIMIT_EXCEEDED, start + 8, start + 10)
    return _Binding(
        desc.record_id,
        desc.kind,
        binding_class,
        namespace,
        semantic,
        _u16(raw, start + 6),
        auxiliary,
    )


def _decode_passive(raw: memoryview, desc: _Descriptor) -> _Passive:
    start = desc.payload_start
    count = _u16(raw, start + 8)
    if count == 0:
        _reject(C.CONTENT_BAD_COUNT, start + 8, start + 10)
    _length(desc, 16 + 4 * count)
    actions: list[bytes] = []
    for index in range(count):
        offset = start + 10 + index * 4
        tag = raw[offset]
        if tag not in _CALLABLE_ACTIONS:
            _reject(C.CONTENT_BAD_TAG, offset, offset + 1)
        if raw[offset + 1] != 0:
            _reject(C.CONTENT_RESERVED_NONZERO, offset + 1, offset + 2)
        if tag in (C.ACTION_RESET, C.ACTION_COMMIT) and _u16(raw, offset + 2) != 0:
            _reject(C.CONTENT_BAD_VALUE, offset + 2, offset + 4)
        actions.append(bytes(raw[offset : offset + 4]))
    tail = start + 10 + 4 * count
    outcome = raw[tail]
    if outcome not in _OUTCOMES:
        _reject(C.CONTENT_BAD_TAG, tail, tail + 1)
    if raw[tail + 1] != 0:
        _reject(C.CONTENT_RESERVED_NONZERO, tail + 1, tail + 2)
    return _Passive(
        desc.record_id,
        desc.kind,
        _u16(raw, start),
        _u16(raw, start + 2),
        _u16(raw, start + 4),
        _u16(raw, start + 6),
        count,
        tuple(actions),
        outcome,
        _u16(raw, tail + 2),
        _u16(raw, tail + 4),
    )


def _decode_lesson(raw: memoryview, desc: _Descriptor) -> _Lesson:
    start = desc.payload_start
    role = raw[start]
    shape = raw[start + 1]
    mode = raw[start + 2]
    flags = raw[start + 3]
    if role not in _ROLES:
        _reject(C.CONTENT_BAD_TAG, start, start + 1)
    if shape not in _SHAPES:
        _reject(C.CONTENT_BAD_TAG, start + 1, start + 2)
    if mode not in _MODES:
        _reject(C.CONTENT_BAD_TAG, start + 2, start + 3)
    if flags & ~C.LESSON_ALLOW_REPEATED_SELECTIONS:
        _reject(C.CONTENT_RESERVED_NONZERO, start + 3, start + 4)
    maximum = _u16(raw, start + 12)
    count = _u16(raw, start + 16)
    if count > C.CONTENT_MAX_CASES_PER_NODE:
        _reject(C.CONTENT_LIMIT_EXCEEDED, start + 16, start + 18)
    offset = start + 18
    cases: list[_Case] = []
    previous = b""
    for index in range(count):
        if offset + 4 > desc.payload_end - 4:
            _reject(C.CONTENT_BAD_PAYLOAD_LENGTH, desc.length_start, desc.length_start + 4)
        case_class = raw[offset]
        if case_class not in _CASE_CLASSES:
            _reject(C.CONTENT_BAD_TAG, offset, offset + 1)
        if raw[offset + 1] != 0:
            _reject(C.CONTENT_RESERVED_NONZERO, offset + 1, offset + 2)
        selection_count = _u16(raw, offset + 2)
        end = offset + 4 + 2 * selection_count + 4
        if end > desc.payload_end - 4:
            _reject(C.CONTENT_BAD_PAYLOAD_LENGTH, desc.length_start, desc.length_start + 4)
        ids = tuple(
            _u16(raw, offset + 4 + item * 2) for item in range(selection_count)
        )
        if shape == C.RESPONSE_SET:
            prior = -1
            for item, region_id in enumerate(ids):
                if region_id <= prior:
                    at = offset + 4 + item * 2
                    _reject(
                        C.CONTENT_DUPLICATE
                        if region_id == prior
                        else C.CONTENT_NONCANONICAL_ORDER,
                        at,
                        at + 2,
                    )
                prior = region_id
        response_key = bytes(raw[offset + 2 : offset + 4 + 2 * selection_count])
        if index and response_key <= previous:
            _reject(
                C.CONTENT_DUPLICATE
                if response_key == previous
                else C.CONTENT_NONCANONICAL_ORDER,
                offset + 2,
                offset + 4,
            )
        previous = response_key
        cases.append(
            _Case(
                case_class,
                ids,
                _u16(raw, end - 4),
                _u16(raw, end - 2),
            )
        )
        offset = end
    if offset + 4 != desc.payload_end:
        _reject(C.CONTENT_BAD_PAYLOAD_LENGTH, desc.length_start, desc.length_start + 4)
    return _Lesson(
        desc.record_id,
        desc.kind,
        role,
        shape,
        mode,
        flags,
        _u16(raw, start + 4),
        _u16(raw, start + 6),
        _u16(raw, start + 8),
        _u16(raw, start + 10),
        maximum,
        _u16(raw, start + 14),
        tuple(cases),
        _u16(raw, offset),
        _u16(raw, offset + 2),
    )


def _decode_local(
    raw: memoryview, descriptors: tuple[_Descriptor, ...]
) -> tuple[list[_Record], dict[int, _Descriptor]]:
    records: list[_Record] = []
    binding_keys: set[tuple[int, int, int]] = set()
    desc_by_id = {desc.record_id: desc for desc in descriptors}
    for desc in descriptors:
        start = desc.payload_start
        kind = desc.kind
        if kind == C.CONTENT_KIND_TEXT:
            record: _Record = _decode_text(raw, desc)
        elif kind == C.CONTENT_KIND_ATOM_SCHEMA:
            record = _decode_schema(raw, desc)
        elif kind == C.CONTENT_KIND_ATOM_VECTOR:
            record = _AtomVector(
                desc.record_id, kind, _u16(raw, start), _u16(raw, start + 2)
            )
        elif kind == C.CONTENT_KIND_MATRIX:
            rows = _u16(raw, start + 2)
            columns = _u16(raw, start + 4)
            if rows == 0:
                _reject(C.CONTENT_BAD_COUNT, start + 2, start + 4)
            if columns == 0:
                _reject(C.CONTENT_BAD_COUNT, start + 4, start + 6)
            if rows * columns > C.CONTENT_MAX_MATRIX_CELLS:
                _reject(C.CONTENT_LIMIT_EXCEEDED, start + 4, start + 6)
            record = _Matrix(desc.record_id, kind, _u16(raw, start), rows, columns)
        elif kind == C.CONTENT_KIND_FIELD_SCHEMA:
            record = _decode_field_schema(raw, desc)
        elif kind == C.CONTENT_KIND_TUPLE:
            record = _Tuple(desc.record_id, kind, _u16(raw, start))
        elif kind == C.CONTENT_KIND_REGION_SET:
            record = _decode_regions(raw, desc)
        elif kind == C.CONTENT_KIND_SEMANTIC_BINDING:
            record = _decode_binding(raw, desc, binding_keys)
        elif kind == C.CONTENT_KIND_OPAQUE_DATA:
            record = _Opaque(desc.record_id, kind, _u16(raw, start))
        elif kind == C.CONTENT_KIND_PREDICATE_RESULT:
            record = _Predicate(
                desc.record_id,
                kind,
                _u16(raw, start),
                _u16(raw, start + 2),
                _u16(raw, start + 4),
            )
        elif kind == C.CONTENT_KIND_FEEDBACK:
            feedback_code = _u16(raw, start)
            if feedback_code not in _FEEDBACK_CODES:
                _reject(C.CONTENT_BAD_TAG, start, start + 2)
            record = _Feedback(
                desc.record_id,
                kind,
                feedback_code,
                _u16(raw, start + 2),
                _u16(raw, start + 4),
            )
        elif kind == C.CONTENT_KIND_PASSIVE_TRACE:
            record = _decode_passive(raw, desc)
        elif kind == C.CONTENT_KIND_LESSON_NODE:
            record = _decode_lesson(raw, desc)
        elif kind == C.CONTENT_KIND_ROOT:
            record = _Root(
                desc.record_id, kind, _u16(raw, start), _u16(raw, start + 2)
            )
        else:  # pragma: no cover - framing closes the kind set
            raise AssertionError("unreachable content kind")
        records.append(record)
    return records, desc_by_id


def _reference(
    by_id: dict[int, _Record],
    owner: _Record,
    value: int,
    start: int,
    kinds: frozenset[int] | tuple[int, ...] | int,
    *,
    optional: bool = False,
    binding_class: int | None = None,
) -> _Record | None:
    if value == 0:
        if optional:
            return None
        _reject(C.CONTENT_ZERO_REFERENCE, start, start + 2)
    if value >= owner.record_id:
        _reject(C.CONTENT_FORWARD_REFERENCE, start, start + 2)
    target = by_id.get(value)
    if target is None:
        _reject(C.CONTENT_MISSING_REFERENCE, start, start + 2)
    allowed = frozenset((kinds,)) if type(kinds) is int else frozenset(kinds)
    if target.kind not in allowed or (
        binding_class is not None
        and (not isinstance(target, _Binding) or target.binding_class != binding_class)
    ):
        _reject(C.CONTENT_WRONG_REFERENCE_KIND, start, start + 2)
    return target


def _lesson_case_offsets(desc: _Descriptor, node: _Lesson) -> tuple[tuple[int, ...], int]:
    offset = desc.payload_start + 18
    offsets: list[int] = []
    for case in node.cases:
        offsets.append(offset)
        offset += 8 + 2 * len(case.region_ids)
    return tuple(offsets), offset


def _validate_stage5a(
    records: list[_Record], by_id: dict[int, _Record], descs: dict[int, _Descriptor]
) -> None:
    for record in records:
        start = descs[record.record_id].payload_start
        if isinstance(record, _AtomSchema):
            if record.atom_class == C.ATOM_ENUM:
                offset = start + 4
            elif record.atom_class == C.ATOM_MASK:
                offset = start + 4 + record.atom_width
            else:
                continue
            for entry in record.entries:
                _reference(
                    by_id,
                    record,
                    entry.label_text_ref,
                    offset + record.atom_width,
                    C.CONTENT_KIND_TEXT,
                )
                offset += record.atom_width + 2
        elif isinstance(record, (_AtomVector, _Matrix)):
            _reference(by_id, record, record.atom_schema_ref, start, C.CONTENT_KIND_ATOM_SCHEMA)
        elif isinstance(record, _FieldSchema):
            for index, item in enumerate(record.fields):
                offset = start + 2 + index * 8
                _reference(by_id, record, item.name_text_ref, offset, C.CONTENT_KIND_TEXT)
                if item.storage == C.FIELD_INLINE_ATOM:
                    _reference(by_id, record, item.type, offset + 4, C.CONTENT_KIND_ATOM_SCHEMA)
        elif isinstance(record, _Tuple):
            _reference(by_id, record, record.field_schema_ref, start, C.CONTENT_KIND_FIELD_SCHEMA)
        elif isinstance(record, _RegionSet):
            _reference(by_id, record, record.surface_matrix_ref, start, C.CONTENT_KIND_MATRIX)
            for index, region in enumerate(record.regions):
                _reference(
                    by_id,
                    record,
                    region.label_ref,
                    start + 4 + index * 14 + 2,
                    _DISPLAY_KINDS,
                    optional=True,
                )
        elif isinstance(record, _Binding):
            if record.binding_class == C.BINDING_DATA:
                _reference(by_id, record, record.argument, start + 6, C.CONTENT_KIND_ATOM_SCHEMA)
            else:
                _reference(
                    by_id,
                    record,
                    record.argument,
                    start + 6,
                    C.CONTENT_KIND_SEMANTIC_BINDING,
                    binding_class=C.BINDING_DATA,
                )
                _reference(by_id, record, record.auxiliary, start + 8, C.CONTENT_KIND_ATOM_SCHEMA)
        elif isinstance(record, _Opaque):
            _reference(
                by_id,
                record,
                record.data_binding_ref,
                start,
                C.CONTENT_KIND_SEMANTIC_BINDING,
                binding_class=C.BINDING_DATA,
            )
        elif isinstance(record, _Predicate):
            _reference(
                by_id,
                record,
                record.predicate_binding_ref,
                start,
                C.CONTENT_KIND_SEMANTIC_BINDING,
                binding_class=C.BINDING_PREDICATE,
            )
            _reference(
                by_id,
                record,
                record.subject_opaque_data_ref,
                start + 2,
                C.CONTENT_KIND_OPAQUE_DATA,
            )
            _reference(
                by_id,
                record,
                record.result_atom_vector_ref,
                start + 4,
                C.CONTENT_KIND_ATOM_VECTOR,
            )
        elif isinstance(record, _Feedback):
            _reference(by_id, record, record.display_ref, start + 2, _DISPLAY_KINDS)
            _reference(
                by_id,
                record,
                record.predicate_result_ref,
                start + 4,
                C.CONTENT_KIND_PREDICATE_RESULT,
                optional=True,
            )
        elif isinstance(record, _Passive):
            _reference(
                by_id,
                record,
                record.presentation_ref,
                start,
                (C.CONTENT_KIND_MATRIX, C.CONTENT_KIND_TUPLE),
            )
            _reference(by_id, record, record.region_set_ref, start + 2, C.CONTENT_KIND_REGION_SET)
            _reference(
                by_id,
                record,
                record.resulting_presentation_ref,
                start + 4,
                (C.CONTENT_KIND_MATRIX, C.CONTENT_KIND_TUPLE),
                optional=True,
            )
            _reference(
                by_id,
                record,
                record.limitation_text_ref,
                start + 6,
                C.CONTENT_KIND_TEXT,
                optional=True,
            )
            tail = start + 10 + 4 * record.action_count
            _reference(
                by_id,
                record,
                record.expected_feedback_ref,
                tail + 2,
                C.CONTENT_KIND_FEEDBACK,
            )
        elif isinstance(record, _Lesson):
            _reference(
                by_id,
                record,
                record.presentation_ref,
                start + 4,
                (C.CONTENT_KIND_MATRIX, C.CONTENT_KIND_TUPLE),
            )
            _reference(by_id, record, record.region_set_ref, start + 6, C.CONTENT_KIND_REGION_SET)
            _reference(
                by_id,
                record,
                record.predicate_result_ref,
                start + 8,
                C.CONTENT_KIND_PREDICATE_RESULT,
                optional=True,
            )
            _reference(
                by_id,
                record,
                record.passive_trace_ref,
                start + 10,
                C.CONTENT_KIND_PASSIVE_TRACE,
                optional=True,
            )
            offsets, final = _lesson_case_offsets(descs[record.record_id], record)
            for case, offset in zip(record.cases, offsets, strict=True):
                feedback_at = offset + 4 + 2 * len(case.region_ids)
                _reference(
                    by_id,
                    record,
                    case.feedback_ref,
                    feedback_at,
                    C.CONTENT_KIND_FEEDBACK,
                )
            _reference(
                by_id,
                record,
                record.default_feedback_ref,
                final,
                C.CONTENT_KIND_FEEDBACK,
            )
        elif isinstance(record, _Root):
            _reference(by_id, record, record.entry_node_ref, start, C.CONTENT_KIND_LESSON_NODE)


def _replace_record(
    records: list[_Record], by_id: dict[int, _Record], index: int, value: _Record
) -> None:
    records[index] = value
    by_id[value.record_id] = value


def _validate_stage5b5c(
    raw: memoryview,
    records: list[_Record],
    by_id: dict[int, _Record],
    descs: dict[int, _Descriptor],
) -> None:
    for index, record in enumerate(records):
        desc = descs[record.record_id]
        start = desc.payload_start
        if isinstance(record, _AtomVector):
            schema = by_id[record.atom_schema_ref]
            assert isinstance(schema, _AtomSchema)
            _length(desc, 4 + record.atom_count * schema.atom_width)
            atoms = tuple(
                _atom(raw, start + 4 + item * schema.atom_width, schema.atom_width)
                for item in range(record.atom_count)
            )
            _replace_record(records, by_id, index, replace(record, atoms=atoms))
        elif isinstance(record, _Matrix):
            schema = by_id[record.atom_schema_ref]
            assert isinstance(schema, _AtomSchema)
            count = record.rows * record.columns
            _length(desc, 6 + count * schema.atom_width)
            cells = tuple(
                _atom(raw, start + 6 + item * schema.atom_width, schema.atom_width)
                for item in range(count)
            )
            _replace_record(records, by_id, index, replace(record, cells=cells))
        elif isinstance(record, _FieldSchema):
            width = 0
            for item in record.fields:
                if item.storage == C.FIELD_INLINE_ATOM:
                    schema = by_id[item.type]
                    assert isinstance(schema, _AtomSchema)
                    width += schema.atom_width * item.count
                else:
                    width += 2 * item.count
            _replace_record(records, by_id, index, replace(record, tuple_width=width))
        elif isinstance(record, _Tuple):
            schema = by_id[record.field_schema_ref]
            assert isinstance(schema, _FieldSchema)
            _length(desc, 2 + schema.tuple_width)
            offset = start + 2
            values: list[tuple[int, ...]] = []
            for item in schema.fields:
                if item.storage == C.FIELD_INLINE_ATOM:
                    atom_schema = by_id[item.type]
                    assert isinstance(atom_schema, _AtomSchema)
                    field_values = tuple(
                        _atom(raw, offset + part * atom_schema.atom_width, atom_schema.atom_width)
                        for part in range(item.count)
                    )
                    offset += item.count * atom_schema.atom_width
                else:
                    field_values = tuple(
                        _u16(raw, offset + part * 2) for part in range(item.count)
                    )
                    offset += item.count * 2
                values.append(field_values)
            _replace_record(records, by_id, index, replace(record, field_values=tuple(values)))
        elif isinstance(record, _Opaque):
            binding = by_id[record.data_binding_ref]
            assert isinstance(binding, _Binding)
            schema = by_id[binding.argument]
            assert isinstance(schema, _AtomSchema)
            _length(desc, 2 + binding.auxiliary * schema.atom_width)
            values = tuple(
                _atom(raw, start + 2 + item * schema.atom_width, schema.atom_width)
                for item in range(binding.auxiliary)
            )
            _replace_record(records, by_id, index, replace(record, data=values))

    for record in records:
        if not isinstance(record, _Tuple):
            continue
        schema = by_id[record.field_schema_ref]
        assert isinstance(schema, _FieldSchema)
        offset = descs[record.record_id].payload_start + 2
        for definition, values in zip(schema.fields, record.field_values, strict=True):
            if definition.storage == C.FIELD_INLINE_ATOM:
                atom_schema = by_id[definition.type]
                assert isinstance(atom_schema, _AtomSchema)
                offset += definition.count * atom_schema.atom_width
                continue
            for part, reference in enumerate(values):
                _reference(
                    by_id,
                    record,
                    reference,
                    offset + part * 2,
                    definition.type,
                )
            offset += definition.count * 2


def _atom_valid(schema: _AtomSchema, value: int) -> bool:
    if schema.atom_class == C.ATOM_UNSIGNED:
        return schema.min_value <= value <= schema.max_value
    if schema.atom_class == C.ATOM_ENUM:
        low = 0
        high = len(schema.entries)
        while low < high:
            middle = (low + high) // 2
            candidate = schema.entries[middle].value
            if candidate < value:
                low = middle + 1
            else:
                high = middle
        return low < len(schema.entries) and schema.entries[low].value == value
    return value & ~schema.allowed_mask == 0


def _presentation(record: _Record) -> tuple[int, int]:
    if isinstance(record, _Matrix):
        return 1, record.record_id
    if isinstance(record, _Tuple):
        return record.presentation_count, record.presentation_matrix
    return 0, 0


def _check_presentation(
    by_id: dict[int, _Record], presentation: int, regions: int, start: int
) -> None:
    region_set = by_id[regions]
    value = by_id[presentation]
    assert isinstance(region_set, _RegionSet)
    count, matrix = _presentation(value)
    if count != 1 or matrix != region_set.surface_matrix_ref:
        _reject(C.CONTENT_SCHEMA_MISMATCH, start, start + 2)


def _validate_stage5d(
    raw: memoryview,
    records: list[_Record],
    by_id: dict[int, _Record],
    descs: dict[int, _Descriptor],
) -> None:
    for index, record in enumerate(records):
        desc = descs[record.record_id]
        start = desc.payload_start
        if isinstance(record, _AtomVector):
            schema = by_id[record.atom_schema_ref]
            assert isinstance(schema, _AtomSchema)
            for item, value in enumerate(record.atoms):
                if not _atom_valid(schema, value):
                    at = start + 4 + item * schema.atom_width
                    _reject(C.CONTENT_BAD_VALUE, at, at + schema.atom_width)
        elif isinstance(record, _Matrix):
            schema = by_id[record.atom_schema_ref]
            assert isinstance(schema, _AtomSchema)
            for item, value in enumerate(record.cells):
                if not _atom_valid(schema, value):
                    at = start + 6 + item * schema.atom_width
                    _reject(C.CONTENT_BAD_VALUE, at, at + schema.atom_width)
        elif isinstance(record, _FieldSchema):
            names: set[str] = set()
            for item, field_value in enumerate(record.fields):
                at = start + 2 + item * 8
                name = by_id[field_value.name_text_ref]
                assert isinstance(name, _Text)
                if "\n" in name.text:
                    _reject(C.CONTENT_SCHEMA_MISMATCH, at, at + 2)
                if name.text in names:
                    _reject(C.CONTENT_DUPLICATE, at, at + 2)
                names.add(name.text)
        elif isinstance(record, _Tuple):
            schema = by_id[record.field_schema_ref]
            assert isinstance(schema, _FieldSchema)
            offset = start + 2
            total = 0
            sole = 0
            for definition, values in zip(schema.fields, record.field_values, strict=True):
                if definition.storage == C.FIELD_INLINE_ATOM:
                    atom_schema = by_id[definition.type]
                    assert isinstance(atom_schema, _AtomSchema)
                    for value in values:
                        if not _atom_valid(atom_schema, value):
                            _reject(
                                C.CONTENT_BAD_VALUE,
                                offset,
                                offset + atom_schema.atom_width,
                            )
                        offset += atom_schema.atom_width
                else:
                    for reference in values:
                        count, matrix = _presentation(by_id[reference])
                        if count:
                            total = min(2, total + count)
                            sole = matrix if total == 1 else 0
                        offset += 2
            updated = replace(
                record, presentation_count=total, presentation_matrix=sole
            )
            _replace_record(records, by_id, index, updated)
        elif isinstance(record, _RegionSet):
            surface = by_id[record.surface_matrix_ref]
            assert isinstance(surface, _Matrix)
            for item, region in enumerate(record.regions):
                at = start + 4 + item * 14
                if region.row_end > surface.rows:
                    _reject(C.CONTENT_BAD_VALUE, at + 6, at + 8)
                if region.column_end > surface.columns:
                    _reject(C.CONTENT_BAD_VALUE, at + 10, at + 12)
                if not region.flags & C.REGION_SELECTABLE:
                    continue
                for earlier_index in range(item):
                    earlier = record.regions[earlier_index]
                    if not earlier.flags & C.REGION_SELECTABLE:
                        continue
                    separated = (
                        region.row_end <= earlier.row_start
                        or earlier.row_end <= region.row_start
                        or region.column_end <= earlier.column_start
                        or earlier.column_end <= region.column_start
                    )
                    if not separated:
                        _reject(C.CONTENT_BAD_VALUE, at, at + 2)
        elif isinstance(record, _Binding):
            if record.binding_class == C.BINDING_PREDICATE:
                data_binding = by_id[record.argument]
                assert isinstance(data_binding, _Binding)
                if data_binding.binding_class != C.BINDING_DATA:
                    _reject(C.CONTENT_SCHEMA_MISMATCH, start + 6, start + 8)
        elif isinstance(record, _Opaque):
            binding = by_id[record.data_binding_ref]
            assert isinstance(binding, _Binding)
            schema = by_id[binding.argument]
            assert isinstance(schema, _AtomSchema)
            for item, value in enumerate(record.data):
                if not _atom_valid(schema, value):
                    at = start + 2 + item * schema.atom_width
                    _reject(C.CONTENT_BAD_VALUE, at, at + schema.atom_width)
        elif isinstance(record, _Predicate):
            binding = by_id[record.predicate_binding_ref]
            subject = by_id[record.subject_opaque_data_ref]
            result = by_id[record.result_atom_vector_ref]
            assert isinstance(binding, _Binding)
            assert isinstance(subject, _Opaque)
            assert isinstance(result, _AtomVector)
            if subject.data_binding_ref != binding.argument:
                _reject(C.CONTENT_SCHEMA_MISMATCH, start + 2, start + 4)
            if result.atom_schema_ref != binding.auxiliary or result.atom_count != 1:
                _reject(C.CONTENT_SCHEMA_MISMATCH, start + 4, start + 6)
        elif isinstance(record, _Passive):
            _check_presentation(by_id, record.presentation_ref, record.region_set_ref, start)
            if record.resulting_presentation_ref:
                _check_presentation(
                    by_id,
                    record.resulting_presentation_ref,
                    record.region_set_ref,
                    start + 4,
                )
        elif isinstance(record, _Lesson):
            _check_presentation(
                by_id, record.presentation_ref, record.region_set_ref, start + 4
            )


def _dependency_ids(record: _Record, by_id: dict[int, _Record]) -> tuple[int, ...]:
    values: list[int] = []
    if isinstance(record, _AtomSchema):
        values.extend(entry.label_text_ref for entry in record.entries)
    elif isinstance(record, (_AtomVector, _Matrix)):
        values.append(record.atom_schema_ref)
    elif isinstance(record, _FieldSchema):
        for item in record.fields:
            values.append(item.name_text_ref)
            if item.storage == C.FIELD_INLINE_ATOM:
                values.append(item.type)
    elif isinstance(record, _Tuple):
        values.append(record.field_schema_ref)
        schema = by_id[record.field_schema_ref]
        assert isinstance(schema, _FieldSchema)
        for definition, field_values in zip(schema.fields, record.field_values, strict=True):
            if definition.storage == C.FIELD_RECORD_REF:
                values.extend(field_values)
    elif isinstance(record, _RegionSet):
        values.append(record.surface_matrix_ref)
        values.extend(region.label_ref for region in record.regions if region.label_ref)
    elif isinstance(record, _Binding):
        values.append(record.argument)
        if record.binding_class == C.BINDING_PREDICATE:
            values.append(record.auxiliary)
    elif isinstance(record, _Opaque):
        values.append(record.data_binding_ref)
    elif isinstance(record, _Predicate):
        values.extend(
            (
                record.predicate_binding_ref,
                record.subject_opaque_data_ref,
                record.result_atom_vector_ref,
            )
        )
    elif isinstance(record, _Feedback):
        values.append(record.display_ref)
        if record.predicate_result_ref:
            values.append(record.predicate_result_ref)
    elif isinstance(record, _Passive):
        values.extend((record.presentation_ref, record.region_set_ref))
        values.extend(
            value
            for value in (
                record.resulting_presentation_ref,
                record.limitation_text_ref,
                record.expected_feedback_ref,
            )
            if value
        )
    elif isinstance(record, _Lesson):
        values.extend((record.presentation_ref, record.region_set_ref))
        values.extend(
            value
            for value in (record.predicate_result_ref, record.passive_trace_ref)
            if value
        )
        values.extend(case.feedback_ref for case in record.cases)
        values.append(record.default_feedback_ref)
        values.extend(case.next_node_ref for case in record.cases if case.next_node_ref)
        if record.default_next_node_ref:
            values.append(record.default_next_node_ref)
    elif isinstance(record, _Root):
        values.append(record.entry_node_ref)
    return tuple(values)


@dataclass(frozen=True, slots=True)
class _EventLink:
    previous: _EventLink | None
    node_id: int
    action: bytes
    result: int
    count: int


@dataclass(frozen=True, slots=True)
class _ContentProjection(metaclass=_AuthorityMeta):
    version: int
    root_record_id: int
    records: tuple[_Record, ...]
    _by_id: MappingProxyType = field(repr=False, compare=False)
    _region_flags: MappingProxyType = field(repr=False, compare=False)
    _case_maps: MappingProxyType = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True, eq=False)
class _RunState(metaclass=_AuthorityMeta):
    _projection: _ContentProjection = field(repr=False, compare=False)
    current_node_id: int
    global_remaining: int
    local_remaining: int
    phase: int
    outcome: int
    buffer: tuple[int, ...]
    committed_response: bytes
    feedback_ref: int
    next_node_ref: int
    _events: _EventLink | None = field(repr=False, compare=False)
    event_count: int


def _response(shape: int, values: tuple[int, ...]) -> bytes:
    output = bytearray(3 + 2 * len(values))
    output[0] = shape
    output[1:3] = len(values).to_bytes(2, "big")
    offset = 3
    for value in values:
        output[offset : offset + 2] = value.to_bytes(2, "big")
        offset += 2
    return bytes(output)


def _make_projection(records: list[_Record]) -> _ContentProjection:
    by_id = {record.record_id: record for record in records}
    root = records[-1]
    assert isinstance(root, _Root)
    region_flags: dict[int, MappingProxyType] = {}
    case_maps: dict[int, MappingProxyType] = {}
    for record in records:
        if not isinstance(record, _Lesson):
            continue
        region_set = by_id[record.region_set_ref]
        assert isinstance(region_set, _RegionSet)
        region_flags[record.record_id] = MappingProxyType(
            {region.region_id: region.flags for region in region_set.regions}
        )
        case_maps[record.record_id] = MappingProxyType(
            {
                _response(record.response_shape, case.region_ids): case
                for case in record.cases
            }
        )
    return _ContentProjection(
        C.CONTENT_VERSION,
        root.record_id,
        tuple(records),
        MappingProxyType(by_id),
        MappingProxyType(region_flags),
        MappingProxyType(case_maps),
        _token=_AUTHORITY,
    )


def _new_state(
    projection: _ContentProjection,
    node_id: int | None = None,
    *,
    passive: bool = False,
) -> _RunState:
    root = projection._by_id[projection.root_record_id]
    assert isinstance(root, _Root)
    current = root.entry_node_ref if node_id is None else node_id
    node = projection._by_id[current]
    assert isinstance(node, _Lesson)
    global_remaining = node.item_event_budget if passive else root.global_event_budget
    return _RunState(
        projection,
        current,
        global_remaining,
        node.item_event_budget,
        C.PHASE_ACTIVE,
        C.OUTCOME_NONE,
        (),
        b"",
        0,
        0,
        None,
        0,
        _token=_AUTHORITY,
    )


def _normalize_action(raw_action: bytes) -> tuple[bytes, int, int]:
    if len(raw_action) != C.CONTENT_ACTION_BYTES:
        return b"\0" * 4, 0, 0
    tag = raw_action[0]
    region = int.from_bytes(raw_action[2:4], "big")
    if (
        tag not in _CALLABLE_ACTIONS
        or raw_action[1] != 0
        or (tag in (C.ACTION_RESET, C.ACTION_COMMIT) and region != 0)
    ):
        return b"\0" * 4, 0, 0
    return raw_action, tag, region


def _transition(
    projection: _ContentProjection, state: _RunState, raw_action: bytes
) -> tuple[_RunState, int]:
    if state.phase == C.PHASE_COMMITTED:
        return state, C.INTERACTION_ALREADY_COMMITTED
    if state.phase == C.PHASE_EXHAUSTED:
        return state, C.INTERACTION_BUDGET_EXHAUSTED
    node = projection._by_id[state.current_node_id]
    assert isinstance(node, _Lesson)
    action, tag, region = _normalize_action(raw_action)
    global_remaining = state.global_remaining - 1
    local_remaining = state.local_remaining - 1
    buffer = state.buffer
    response = b""
    outcome = C.OUTCOME_NONE
    feedback = 0
    next_node = 0
    if tag == 0:
        result = C.INTERACTION_INVALID_ACTION
    elif tag == C.ACTION_SELECT:
        flags = projection._region_flags[node.record_id].get(region, 0)
        if not flags & C.REGION_SELECTABLE:
            result = C.INTERACTION_INVALID_REGION
        elif region in buffer and not (
            node.response_shape == C.RESPONSE_SEQUENCE
            and node.flags & C.LESSON_ALLOW_REPEATED_SELECTIONS
        ):
            result = C.INTERACTION_DUPLICATE
        elif len(buffer) >= node.max_selections:
            result = C.INTERACTION_OVER_LIMIT
        else:
            if node.response_shape == C.RESPONSE_SEQUENCE:
                buffer = (*buffer, region)
            else:
                at = bisect_left(buffer, region)
                buffer = (*buffer[:at], region, *buffer[at:])
            result = C.INTERACTION_SELECTED
    elif tag == C.ACTION_RESET:
        buffer = ()
        result = C.INTERACTION_RESET
    else:
        response = _response(node.response_shape, buffer)
        selected = projection._case_maps[node.record_id].get(response)
        if selected is None:
            feedback = node.default_feedback_ref
            next_node = node.default_next_node_ref
            outcome = (
                C.OUTCOME_REJECTED
                if node.answer_mode == C.ANSWER_PACKED_PRACTICE
                else C.OUTCOME_NEUTRAL
            )
        else:
            feedback = selected.feedback_ref
            next_node = selected.next_node_ref
            outcome = (
                C.OUTCOME_ACCEPTED
                if selected.case_class == C.CASE_ACCEPTED
                else C.OUTCOME_REJECTED
            )
        buffer = ()
        result = C.INTERACTION_COMMITTED
    events = _EventLink(
        state._events,
        state.current_node_id,
        action,
        result,
        state.event_count + 1,
    )
    phase = C.PHASE_COMMITTED if tag == C.ACTION_COMMIT else C.PHASE_ACTIVE
    if tag != C.ACTION_COMMIT and (global_remaining == 0 or local_remaining == 0):
        phase = C.PHASE_EXHAUSTED
    return (
        _RunState(
            projection,
            state.current_node_id,
            global_remaining,
            local_remaining,
            phase,
            outcome,
            buffer,
            response,
            feedback,
            next_node,
            events,
            state.event_count + 1,
            _token=_AUTHORITY,
        ),
        result,
    )


def _advance(projection: _ContentProjection, state: _RunState) -> _RunState:
    if state.phase != C.PHASE_COMMITTED or state.next_node_ref == 0:
        raise InvalidHostState()
    target = projection._by_id[state.next_node_ref]
    assert isinstance(target, _Lesson)
    exhausted = state.global_remaining == 0
    return _RunState(
        projection,
        target.record_id,
        state.global_remaining,
        0 if exhausted else min(target.item_event_budget, state.global_remaining),
        C.PHASE_EXHAUSTED if exhausted else C.PHASE_ACTIVE,
        C.OUTCOME_NONE,
        (),
        b"",
        0,
        0,
        state._events,
        state.event_count,
        _token=_AUTHORITY,
    )


def _validate_stage6(
    records: list[_Record],
    by_id: dict[int, _Record],
    descs: dict[int, _Descriptor],
) -> _Root:
    root = None
    for record in records:
        if not isinstance(record, _Root):
            continue
        if root is not None:
            at = descs[record.record_id].start + 2
            _reject(C.CONTENT_ROOT_COUNT, at, at + 2)
        root = record
    if root is None:
        end = descs[records[-1].record_id].payload_end if records else 4
        _reject(C.CONTENT_ROOT_COUNT, end, end)
    if root is not records[-1]:
        at = descs[root.record_id].start + 2
        _reject(C.CONTENT_ROOT_NOT_FINAL, at, at + 2)

    runtime_edges = 0

    def check_control(at: int, target_id: int, runtime: bool) -> None:
        nonlocal runtime_edges
        if target_id:
            if runtime:
                runtime_edges += 1
                if runtime_edges > C.CONTENT_MAX_CONTROL_EDGES:
                    _reject(C.CONTENT_LIMIT_EXCEEDED, at, at + 2)
            target = by_id.get(target_id)
            if not isinstance(target, _Lesson):
                _reject(C.CONTENT_BAD_CONTROL_EDGE, at, at + 2)

    for record in records:
        start = descs[record.record_id].payload_start
        if isinstance(record, _Passive):
            check_control(
                start + 14 + 4 * record.action_count,
                record.expected_next_node_ref,
                False,
            )
        elif isinstance(record, _Lesson):
            offsets, final = _lesson_case_offsets(descs[record.record_id], record)
            for case, offset in zip(record.cases, offsets, strict=True):
                check_control(
                    offset + 6 + 2 * len(case.region_ids),
                    case.next_node_ref,
                    True,
                )
            check_control(final + 2, record.default_next_node_ref, True)

    reached: set[int] = set()
    stack = [root.record_id]
    while stack:
        record_id = stack.pop()
        if record_id in reached:
            continue
        reached.add(record_id)
        stack.extend(
            value
            for value in _dependency_ids(by_id[record_id], by_id)
            if value not in reached
        )
    candidates: list[tuple[int, int, int]] = []
    for record in records:
        if record.record_id not in reached:
            at = descs[record.record_id].start
            candidates.append((at, C.CONTENT_ORPHAN_RECORD, at + 2))
            break
    trace_owner: dict[int, tuple[int, int]] = {}
    for record in records:
        if not isinstance(record, _Lesson) or not record.passive_trace_ref:
            continue
        at = descs[record.record_id].payload_start + 10
        if record.passive_trace_ref in trace_owner:
            candidates.append((at, C.CONTENT_BAD_PASSIVE_TRACE, at + 2))
        else:
            trace_owner[record.passive_trace_ref] = (record.record_id, at)
    if candidates:
        at, code, end = min(candidates, key=lambda item: (item[0], item[1]))
        _reject(code, at, end)
    return root


def _case_span(desc: _Descriptor, node: _Lesson, index: int) -> tuple[int, int]:
    offsets, _ = _lesson_case_offsets(desc, node)
    start = offsets[index]
    return start, start + 8 + 2 * len(node.cases[index].region_ids)


def _validate_stage7a(
    records: list[_Record], projection: _ContentProjection, descs: dict[int, _Descriptor]
) -> None:
    for node in (record for record in records if isinstance(record, _Lesson)):
        start = descs[node.record_id].payload_start
        candidates: list[tuple[int, int, int]] = []
        if (
            node.flags & C.LESSON_ALLOW_REPEATED_SELECTIONS
            and node.response_shape != C.RESPONSE_SEQUENCE
        ):
            candidates.append((start + 3, C.CONTENT_BAD_RESPONSE_SCHEMA, start + 4))
        if node.response_shape == C.RESPONSE_SINGLE and node.max_selections != 1:
            candidates.append((start + 12, C.CONTENT_BAD_RESPONSE_SCHEMA, start + 14))
        if node.max_selections > C.CONTENT_MAX_SELECTIONS:
            candidates.append((start + 12, C.CONTENT_BAD_RESPONSE_SCHEMA, start + 14))
        region_flags = projection._region_flags[node.record_id]
        for index, case in enumerate(node.cases):
            case_start, _ = _case_span(descs[node.record_id], node, index)
            count_at = case_start + 2
            if node.response_shape == C.RESPONSE_SINGLE and len(case.region_ids) > 1:
                candidates.append(
                    (count_at, C.CONTENT_BAD_RESPONSE_SCHEMA, count_at + 2)
                )
            if len(case.region_ids) > node.max_selections:
                candidates.append(
                    (count_at, C.CONTENT_BAD_RESPONSE_SCHEMA, count_at + 2)
                )
            seen: set[int] = set()
            for item, region_id in enumerate(case.region_ids):
                at = case_start + 4 + item * 2
                if not region_flags.get(region_id, 0) & C.REGION_SELECTABLE:
                    candidates.append((at, C.CONTENT_BAD_RESPONSE_SCHEMA, at + 2))
                if (
                    node.response_shape == C.RESPONSE_SEQUENCE
                    and not node.flags & C.LESSON_ALLOW_REPEATED_SELECTIONS
                    and region_id in seen
                ):
                    candidates.append((at, C.CONTENT_BAD_RESPONSE_SCHEMA, at + 2))
                seen.add(region_id)

        allowed = (
            node.answer_mode == C.ANSWER_UNSCORED
            and node.role
            in {
                C.ROLE_EXACT_RULE,
                C.ROLE_OBSERVABLE_RELATION,
                C.ROLE_WORKED_EXAMPLE,
                C.ROLE_HEURISTIC,
            }
        ) or (
            node.role == C.ROLE_PRACTICE
            and node.answer_mode in {C.ANSWER_PACKED_PRACTICE, C.ANSWER_EXTERNAL}
        )
        if not allowed:
            candidates.append((start + 2, C.CONTENT_FORBIDDEN_ANSWER_DATA, start + 3))

        required_predicate = node.role in {
            C.ROLE_EXACT_RULE,
            C.ROLE_OBSERVABLE_RELATION,
            C.ROLE_WORKED_EXAMPLE,
        } or (
            node.role == C.ROLE_PRACTICE
            and node.answer_mode == C.ANSWER_PACKED_PRACTICE
        )
        required_trace = node.role == C.ROLE_WORKED_EXAMPLE or (
            node.role == C.ROLE_PRACTICE
            and node.answer_mode == C.ANSWER_PACKED_PRACTICE
        )
        forbidden_cases = node.answer_mode != C.ANSWER_PACKED_PRACTICE
        if bool(node.predicate_result_ref) != required_predicate:
            candidates.append((start + 8, C.CONTENT_FORBIDDEN_ANSWER_DATA, start + 10))
        if required_trace and not node.passive_trace_ref:
            candidates.append(
                (start + 10, C.CONTENT_FORBIDDEN_ANSWER_DATA, start + 12)
            )
        if (
            node.answer_mode == C.ANSWER_EXTERNAL and node.passive_trace_ref
        ):
            candidates.append(
                (start + 10, C.CONTENT_FORBIDDEN_ANSWER_DATA, start + 12)
            )
        if forbidden_cases and node.cases:
            candidates.append(
                (start + 16, C.CONTENT_FORBIDDEN_ANSWER_DATA, start + 18)
            )
        if node.answer_mode == C.ANSWER_PACKED_PRACTICE and not any(
            case.case_class == C.CASE_ACCEPTED for case in node.cases
        ):
            candidates.append((start + 16, C.CONTENT_BAD_RESPONSE_SCHEMA, start + 18))
        if candidates:
            at, code, end = min(candidates, key=lambda item: (item[0], item[1]))
            _reject(code, at, end)


def _validate_stage7b(
    records: list[_Record], by_id: dict[int, _Record], descs: dict[int, _Descriptor]
) -> None:
    for feedback in (record for record in records if isinstance(record, _Feedback)):
        present = feedback.predicate_result_ref != 0
        required = feedback.feedback_code in {
            C.FEEDBACK_MATCH,
            C.FEEDBACK_NO_MATCH,
            C.FEEDBACK_ALTERNATIVE,
        }
        if present != required:
            at = descs[feedback.record_id].payload_start + 4
            _reject(C.CONTENT_BAD_FEEDBACK, at, at + 2)
    for node in (record for record in records if isinstance(record, _Lesson)):
        desc = descs[node.record_id]
        offsets, final = _lesson_case_offsets(desc, node)
        for case, at in zip(node.cases, offsets, strict=True):
            feedback_at = at + 4 + 2 * len(case.region_ids)
            feedback = by_id[case.feedback_ref]
            assert isinstance(feedback, _Feedback)
            if node.answer_mode == C.ANSWER_PACKED_PRACTICE:
                if case.case_class == C.CASE_ACCEPTED:
                    valid = (
                        feedback.feedback_code == C.FEEDBACK_MATCH
                        and feedback.predicate_result_ref == node.predicate_result_ref
                    )
                else:
                    valid = feedback.feedback_code == C.FEEDBACK_ALTERNATIVE
                if not valid:
                    _reject(C.CONTENT_BAD_FEEDBACK, feedback_at, feedback_at + 2)
        default = by_id[node.default_feedback_ref]
        assert isinstance(default, _Feedback)
        if node.answer_mode == C.ANSWER_PACKED_PRACTICE:
            valid_default = (
                default.feedback_code == C.FEEDBACK_NO_MATCH
                and default.predicate_result_ref == node.predicate_result_ref
            )
        elif node.role == C.ROLE_HEURISTIC:
            valid_default = default.feedback_code == C.FEEDBACK_LIMITATION
        else:
            valid_default = default.feedback_code == C.FEEDBACK_NEUTRAL
        if not valid_default:
            _reject(C.CONTENT_BAD_FEEDBACK, final, final + 2)


def _validate_stage7c(
    records: list[_Record], projection: _ContentProjection, descs: dict[int, _Descriptor]
) -> None:
    candidates: list[tuple[int, int, int]] = []
    for node in (record for record in records if isinstance(record, _Lesson)):
        if not node.passive_trace_ref:
            continue
        trace = projection._by_id[node.passive_trace_ref]
        assert isinstance(trace, _Passive)
        node_start = descs[node.record_id].payload_start
        trace_start = descs[trace.record_id].payload_start
        owned = None
        if bool(trace.limitation_text_ref) != (node.role == C.ROLE_HEURISTIC):
            owned = (
                trace_start + 6,
                C.CONTENT_BAD_PASSIVE_TRACE,
                trace_start + 8,
            )
        elif trace.action_count > node.item_event_budget:
            owned = (
                trace_start + 8,
                C.CONTENT_BAD_PASSIVE_TRACE,
                trace_start + 10,
            )
        else:
            state = _new_state(projection, node.record_id, passive=True)
            for index, action in enumerate(trace.actions):
                at = trace_start + 10 + index * 4
                state, result = _transition(projection, state, action)
                if index + 1 < trace.action_count:
                    expected = (
                        C.INTERACTION_SELECTED
                        if action[0] == C.ACTION_SELECT
                        else C.INTERACTION_RESET
                    )
                    if (
                        action[0] not in (C.ACTION_SELECT, C.ACTION_RESET)
                        or result != expected
                    ):
                        owned = (at, C.CONTENT_BAD_PASSIVE_TRACE, at + 4)
                        break
                elif action[0] != C.ACTION_COMMIT or result != C.INTERACTION_COMMITTED:
                    owned = (at, C.CONTENT_BAD_PASSIVE_TRACE, at + 4)
                    break
            if owned is None:
                tail = trace_start + 10 + 4 * trace.action_count
                if state.outcome != trace.expected_outcome:
                    owned = (tail, C.CONTENT_BAD_PASSIVE_TRACE, tail + 1)
                elif state.feedback_ref != trace.expected_feedback_ref:
                    owned = (tail + 2, C.CONTENT_BAD_PASSIVE_TRACE, tail + 4)
                elif state.next_node_ref != trace.expected_next_node_ref:
                    owned = (tail + 4, C.CONTENT_BAD_PASSIVE_TRACE, tail + 6)
        if owned is None and (
            trace.presentation_ref != node.presentation_ref
            or trace.region_set_ref != node.region_set_ref
        ):
            owned = (node_start + 10, C.CONTENT_BAD_PASSIVE_TRACE, node_start + 12)
        if owned is not None:
            candidates.append(owned)
    if candidates:
        at, code, end = min(candidates, key=lambda item: (item[0], item[1]))
        _reject(code, at, end)


def _success_edges(
    records: list[_Record], descs: dict[int, _Descriptor]
) -> list[tuple[int, int, int]]:
    edges: list[tuple[int, int, int]] = []
    for node in (record for record in records if isinstance(record, _Lesson)):
        offsets, final = _lesson_case_offsets(descs[node.record_id], node)
        if node.answer_mode == C.ANSWER_PACKED_PRACTICE:
            for case, offset in zip(node.cases, offsets, strict=True):
                if case.case_class == C.CASE_ACCEPTED and case.next_node_ref:
                    edges.append(
                        (
                            node.record_id,
                            case.next_node_ref,
                            offset + 6 + 2 * len(case.region_ids),
                        )
                    )
        elif node.default_next_node_ref:
            edges.append((node.record_id, node.default_next_node_ref, final + 2))
    return edges


def _components(nodes: tuple[int, ...], adjacency: dict[int, tuple[int, ...]]):
    seen: set[int] = set()
    order: list[int] = []
    for origin in nodes:
        if origin in seen:
            continue
        seen.add(origin)
        stack: list[tuple[int, int]] = [(origin, 0)]
        while stack:
            node, index = stack[-1]
            neighbours = adjacency[node]
            if index < len(neighbours):
                target = neighbours[index]
                stack[-1] = (node, index + 1)
                if target not in seen:
                    seen.add(target)
                    stack.append((target, 0))
            else:
                order.append(node)
                stack.pop()
    reverse = {node: [] for node in nodes}
    for node, targets in adjacency.items():
        for target in targets:
            reverse[target].append(node)
    component: dict[int, int] = {}
    groups: list[tuple[int, ...]] = []
    for origin in reversed(order):
        if origin in component:
            continue
        identifier = len(groups)
        group: list[int] = []
        stack = [origin]
        component[origin] = identifier
        while stack:
            node = stack.pop()
            group.append(node)
            for target in reverse[node]:
                if target not in component:
                    component[target] = identifier
                    stack.append(target)
        groups.append(tuple(group))
    return component, tuple(groups), tuple(order)


def _validate_stage8(
    records: list[_Record], root: _Root, descs: dict[int, _Descriptor]
) -> None:
    lessons = tuple(record for record in records if isinstance(record, _Lesson))
    nodes = tuple(node.record_id for node in lessons)
    edges = _success_edges(records, descs)
    adjacency_lists = {node: [] for node in nodes}
    for source, target, _ in edges:
        adjacency_lists[source].append(target)
    adjacency = {node: tuple(targets) for node, targets in adjacency_lists.items()}
    component, groups, order = _components(nodes, adjacency)
    cyclic = {
        index
        for index, group in enumerate(groups)
        if len(group) > 1 or any(target == group[0] for target in adjacency[group[0]])
    }
    cycle_spans = [
        at
        for source, target, at in edges
        if component[source] == component[target] and component[source] in cyclic
    ]
    if cycle_spans:
        at = min(cycle_spans)
        _reject(C.CONTENT_BAD_CONTROL_EDGE, at, at + 2)

    candidates: list[tuple[int, int]] = []
    for node in lessons:
        at = descs[node.record_id].payload_start + 14
        if node.item_event_budget == 0 or node.item_event_budget < node.max_selections + 1:
            candidates.append((at, at + 2))
    root_at = descs[root.record_id].payload_start + 2
    if root.global_event_budget == 0:
        candidates.append((root_at, root_at + 2))
    if candidates:
        at, end = min(candidates)
        _reject(C.CONTENT_BUDGET_PROOF, at, end)

    costs: dict[int, int] = {}
    lesson_by_id = {node.record_id: node for node in lessons}
    budget = root.global_event_budget
    for node_id in order:
        node = lesson_by_id[node_id]
        following = max((costs[target] for target in adjacency[node_id]), default=0)
        costs[node_id] = min(budget + 1, node.item_event_budget + following)
    if costs[root.entry_node_ref] > budget:
        _reject(C.CONTENT_BUDGET_PROOF, root_at, root_at + 2)


def _parse(data: bytes) -> _ContentProjection:
    raw, descriptors = _frame(data)
    records, descs = _decode_local(raw, descriptors)
    by_id = {record.record_id: record for record in records}
    _validate_stage5a(records, by_id, descs)
    _validate_stage5b5c(raw, records, by_id, descs)
    _validate_stage5d(raw, records, by_id, descs)
    root = _validate_stage6(records, by_id, descs)
    projection = _make_projection(records)
    _validate_stage7a(records, projection, descs)
    _validate_stage7b(records, by_id, descs)
    _validate_stage7c(records, projection, descs)
    _validate_stage8(records, root, descs)
    return projection


def stream_validation(raw_content_bytes: bytes):
    if type(raw_content_bytes) is not bytes:
        raise TypeError("expected bytes")
    return _parse(raw_content_bytes)


def new_run(projection):
    if type(projection) is not _ContentProjection:
        raise TypeError("expected accepted content projection")
    return _new_state(projection)


def step(projection, state, raw_action: bytes):
    if (
        type(projection) is not _ContentProjection
        or type(state) is not _RunState
        or state._projection is not projection
    ):
        raise TypeError("expected matching accepted content projection and run state")
    if type(raw_action) is not bytes:
        raise TypeError("expected bytes")
    return _transition(projection, state, raw_action)


def advance_committed(projection, state):
    if (
        type(projection) is not _ContentProjection
        or type(state) is not _RunState
        or state._projection is not projection
    ):
        raise TypeError("expected matching accepted content projection and run state")
    return _advance(projection, state)


def encode_run_state(state) -> bytes:
    if type(state) is not _RunState:
        raise TypeError("expected accepted run state")
    size = (
        C.CONTENT_RUN_STATE_FIXED_BYTES
        + 2 * len(state.buffer)
        + len(state.committed_response)
        + C.CONTENT_EVENT_BYTES * state.event_count
    )
    if size > C.CONTENT_MAX_RUN_STATE_BYTES:
        raise ValueError("accepted state exceeds content-v0 bound")
    output = bytearray(size)
    output[0:2] = C.CONTENT_VERSION.to_bytes(2, "big")
    output[2:4] = state._projection.root_record_id.to_bytes(2, "big")
    output[4:6] = state.current_node_id.to_bytes(2, "big")
    output[6:8] = state.global_remaining.to_bytes(2, "big")
    output[8:10] = state.local_remaining.to_bytes(2, "big")
    output[10] = state.phase
    output[11] = state.outcome
    output[12:14] = len(state.buffer).to_bytes(2, "big")
    offset = 14
    for region_id in state.buffer:
        output[offset : offset + 2] = region_id.to_bytes(2, "big")
        offset += 2
    output[offset : offset + 2] = len(state.committed_response).to_bytes(2, "big")
    offset += 2
    output[offset : offset + len(state.committed_response)] = state.committed_response
    offset += len(state.committed_response)
    output[offset : offset + 2] = state.event_count.to_bytes(2, "big")
    offset += 2
    event = state._events
    event_offset = size
    seen = 0
    while event is not None:
        event_offset -= C.CONTENT_EVENT_BYTES
        output[event_offset : event_offset + 2] = event.node_id.to_bytes(2, "big")
        output[event_offset + 2 : event_offset + 6] = event.action
        output[event_offset + 6] = event.result
        event = event.previous
        seen += 1
    if seen != state.event_count or event_offset != offset:
        raise ValueError("invalid private event chain")
    return bytes(output)


def _state_reject(start: int, end: int) -> NoReturn:
    _reject(C.CONTENT_BAD_RUN_STATE, start, end)


def _state_need(length: int, offset: int, count: int) -> None:
    if count > length - offset:
        _state_reject(length, length)


def _state_buffer(
    projection: _ContentProjection,
    node: _Lesson,
    values: tuple[int, ...],
    count_start: int,
    values_start: int,
) -> None:
    if node.response_shape == C.RESPONSE_SINGLE and len(values) > 1:
        _state_reject(count_start, count_start + 2)
    if len(values) > node.max_selections:
        _state_reject(count_start, count_start + 2)
    flags = projection._region_flags[node.record_id]
    previous = -1
    seen: set[int] = set()
    for index, value in enumerate(values):
        at = values_start + index * 2
        if not flags.get(value, 0) & C.REGION_SELECTABLE:
            _state_reject(at, at + 2)
        if node.response_shape == C.RESPONSE_SET:
            if value <= previous:
                _state_reject(at, at + 2)
            previous = value
        elif (
            node.response_shape == C.RESPONSE_SEQUENCE
            and not node.flags & C.LESSON_ALLOW_REPEATED_SELECTIONS
        ):
            if value in seen:
                _state_reject(at, at + 2)
            seen.add(value)


def _committed_details(
    projection: _ContentProjection,
    node: _Lesson,
    response: bytes,
    start: int,
    length_start: int,
) -> tuple[int, int, int]:
    if len(response) < 3:
        _state_reject(length_start, length_start + 2)
    if response[0] != node.response_shape:
        _state_reject(start, start + 1)
    count = int.from_bytes(response[1:3], "big")
    if len(response) != 3 + 2 * count:
        _state_reject(start + 1, start + 3)
    values = tuple(
        int.from_bytes(response[3 + index * 2 : 5 + index * 2], "big")
        for index in range(count)
    )
    _state_buffer(projection, node, values, start + 1, start + 3)
    selected = projection._case_maps[node.record_id].get(response)
    if selected is None:
        return (
            C.OUTCOME_REJECTED
            if node.answer_mode == C.ANSWER_PACKED_PRACTICE
            else C.OUTCOME_NEUTRAL,
            node.default_feedback_ref,
            node.default_next_node_ref,
        )
    return (
        C.OUTCOME_ACCEPTED
        if selected.case_class == C.CASE_ACCEPTED
        else C.OUTCOME_REJECTED,
        selected.feedback_ref,
        selected.next_node_ref,
    )


def _canonical_event_action(action: bytes, start: int) -> None:
    if action == b"\0" * 4:
        return
    if action[0] not in _CALLABLE_ACTIONS:
        _state_reject(start, start + 1)
    if action[1] != 0:
        _state_reject(start + 1, start + 2)
    if action[0] in (C.ACTION_RESET, C.ACTION_COMMIT) and action[2:4] != b"\0\0":
        _state_reject(start + 2, start + 4)


def _retain_candidates(
    candidates: list[_RunState], value: object, getter, start: int, end: int
) -> list[_RunState]:
    kept = [candidate for candidate in candidates if getter(candidate) == value]
    if not kept:
        _state_reject(start, end)
    return kept


def _final_candidate(
    candidates: list[_RunState],
    current_node: int,
    global_remaining: int,
    local_remaining: int,
    phase: int,
    outcome: int,
    buffer: tuple[int, ...],
    buffer_start: int,
    response: bytes,
    response_length_start: int,
    response_start: int,
) -> _RunState:
    candidates = _retain_candidates(
        candidates, current_node, lambda state: state.current_node_id, 4, 6
    )
    candidates = _retain_candidates(
        candidates, global_remaining, lambda state: state.global_remaining, 6, 8
    )
    candidates = _retain_candidates(
        candidates, local_remaining, lambda state: state.local_remaining, 8, 10
    )
    candidates = _retain_candidates(candidates, phase, lambda state: state.phase, 10, 11)
    candidates = _retain_candidates(candidates, outcome, lambda state: state.outcome, 11, 12)
    candidates = _retain_candidates(
        candidates, len(buffer), lambda state: len(state.buffer), 12, 14
    )
    for index, value in enumerate(buffer):
        at = buffer_start + index * 2
        candidates = _retain_candidates(
            candidates, value, lambda state, item=index: state.buffer[item], at, at + 2
        )
    candidates = _retain_candidates(
        candidates,
        len(response),
        lambda state: len(state.committed_response),
        response_length_start,
        response_length_start + 2,
    )
    for index, value in enumerate(response):
        at = response_start + index
        candidates = _retain_candidates(
            candidates,
            value,
            lambda state, item=index: state.committed_response[item],
            at,
            at + 1,
        )
    return candidates[0]


def validate_run_state(projection, run_state_bytes: bytes):
    if type(projection) is not _ContentProjection:
        raise TypeError("expected accepted content projection")
    if type(run_state_bytes) is not bytes:
        raise TypeError("expected bytes")
    length = len(run_state_bytes)
    if length > C.CONTENT_MAX_RUN_STATE_BYTES:
        _reject(
            C.CONTENT_LIMIT_EXCEEDED,
            C.CONTENT_MAX_RUN_STATE_BYTES,
            C.CONTENT_MAX_RUN_STATE_BYTES + 1,
        )
    raw = memoryview(run_state_bytes)
    if length < 11:
        _state_reject(length, length)
    phase = raw[10]
    if phase not in (C.PHASE_ACTIVE, C.PHASE_COMMITTED, C.PHASE_EXHAUSTED):
        _state_reject(10, 11)
    if phase == C.PHASE_EXHAUSTED and length > C.CONTENT_MAX_EXHAUSTED_RUN_STATE_BYTES:
        _reject(
            C.CONTENT_LIMIT_EXCEEDED,
            C.CONTENT_MAX_EXHAUSTED_RUN_STATE_BYTES,
            C.CONTENT_MAX_EXHAUSTED_RUN_STATE_BYTES + 1,
        )

    _state_need(length, 0, 14)
    version = _u16(raw, 0)
    root_id = _u16(raw, 2)
    current_node = _u16(raw, 4)
    global_remaining = _u16(raw, 6)
    local_remaining = _u16(raw, 8)
    outcome = raw[11]
    buffer_count = _u16(raw, 12)
    if buffer_count > C.CONTENT_MAX_SELECTIONS:
        _state_reject(12, 14)
    buffer_start = 14
    response_length_start = buffer_start + 2 * buffer_count
    _state_need(length, buffer_start, 2 * buffer_count + 2)
    buffer = tuple(
        _u16(raw, buffer_start + index * 2) for index in range(buffer_count)
    )
    response_length = _u16(raw, response_length_start)
    if response_length > C.CONTENT_MAX_COMMITTED_RESPONSE_BYTES:
        _state_reject(response_length_start, response_length_start + 2)
    response_start = response_length_start + 2
    event_count_start = response_start + response_length
    _state_need(length, response_start, response_length + 2)
    response = bytes(raw[response_start:event_count_start])
    event_count = _u16(raw, event_count_start)
    events_start = event_count_start + 2
    expected_end = events_start + C.CONTENT_EVENT_BYTES * event_count
    if expected_end > length:
        _state_reject(length, length)
    if expected_end < length:
        _state_reject(expected_end, expected_end + 1)

    root = projection._by_id[projection.root_record_id]
    assert isinstance(root, _Root)
    if version != C.CONTENT_VERSION:
        _state_reject(0, 2)
    if root_id != projection.root_record_id:
        _state_reject(2, 4)
    node = projection._by_id.get(current_node)
    if not isinstance(node, _Lesson):
        _state_reject(4, 6)
    if global_remaining > root.global_event_budget:
        _state_reject(6, 8)
    if local_remaining > node.item_event_budget:
        _state_reject(8, 10)
    if local_remaining > global_remaining:
        _state_reject(8, 10)
    if (
        phase == C.PHASE_ACTIVE
        and (global_remaining == 0 or local_remaining == 0)
    ) or (
        phase == C.PHASE_EXHAUSTED
        and global_remaining != 0
        and local_remaining != 0
    ):
        _state_reject(10, 11)
    if phase in (C.PHASE_ACTIVE, C.PHASE_EXHAUSTED):
        if outcome != C.OUTCOME_NONE:
            _state_reject(11, 12)
        _state_buffer(projection, node, buffer, 12, buffer_start)
        if response_length != 0:
            _state_reject(response_length_start, response_length_start + 2)
        feedback = 0
        next_node = 0
    else:
        if outcome not in _OUTCOMES:
            _state_reject(11, 12)
        if buffer_count != 0:
            _state_reject(12, 14)
        derived_outcome, feedback, next_node = _committed_details(
            projection, node, response, response_start, response_length_start
        )
        if outcome != derived_outcome:
            _state_reject(11, 12)
    if event_count > root.global_event_budget:
        _state_reject(event_count_start, event_count_start + 2)

    replay = _new_state(projection)
    for index in range(event_count):
        at = events_start + index * C.CONTENT_EVENT_BYTES
        event_node = _u16(raw, at)
        action = bytes(raw[at + 2 : at + 6])
        encoded_result = raw[at + 6]
        if replay.phase == C.PHASE_COMMITTED:
            if replay.next_node_ref == 0:
                _state_reject(at, at + 2)
            replay = _advance(projection, replay)
        if replay.phase == C.PHASE_EXHAUSTED or event_node != replay.current_node_id:
            _state_reject(at, at + 2)
        _canonical_event_action(action, at + 2)
        replay, result = _transition(projection, replay, action)
        if result != encoded_result:
            _state_reject(at + 6, at + 7)
    candidates = [replay]
    if replay.phase == C.PHASE_COMMITTED and replay.next_node_ref:
        candidates.append(_advance(projection, replay))
    return _final_candidate(
        candidates,
        current_node,
        global_remaining,
        local_remaining,
        phase,
        outcome,
        buffer,
        buffer_start,
        response,
        response_length_start,
        response_start,
    )
