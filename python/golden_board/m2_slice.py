"""Deterministic compiler for the reviewed M2 slice-v0 declaration."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import tomllib
from typing import NoReturn

from . import canonical_manifest
from . import constants as C
from . import content


__all__ = (
    "SliceAtomicAssignment",
    "SliceCapacityPrototype",
    "SliceCompilation",
    "SliceError",
    "SliceTierRoot",
    "compile_slice_v0",
)


_SLICE_SCHEMA = "golden-board.m2-slice/v0"
_GAME_SET_DOMAIN = b"golden-board:game-set:v0\0"
_GAME_SET_CAP = 327_677
_GAME_COUNT = 64
_REQUIRED_CONTENT_BYTES = 575
_REQUIRED_RECORD_COUNT = 29
_ALL_RECORD_COUNT = 182

_ROOT_KEYS = frozenset(
    (
        "asymmetry_probe",
        "capacity_prototypes",
        "chess_fixture_cases",
        "content_base",
        "game_record_plan",
        "inputs",
        "records",
        "schema",
        "section_plan",
        "selected_curriculum_families",
    )
)
_INPUT_KEYS = frozenset(
    (
        "chess_fixture",
        "constants",
        "content_fixture",
        "content_spec",
        "curriculum",
        "game_set",
    )
)
_FILE_BINDING_KEYS = frozenset(("path", "sha256"))
_GAME_BINDING_KEYS = frozenset(("count", "identity", "path", "sha256"))
_BASE_KEYS = frozenset(
    (
        "fixture_name",
        "removed_root_record_id",
        "retain_record_ids",
        "stream_length",
        "stream_sha256",
    )
)
_GAME_PLAN_KEYS = frozenset(("assignments", "binding_record", "opaque_record"))
_GAME_ASSIGNMENT_KEYS = frozenset(
    (
        "binding_record_id",
        "closure",
        "game_ordinal",
        "opaque_record_id",
        "section_id",
        "semantic_copy_id",
    )
)
_BINDING_TEMPLATE = {
    "argument": 29,
    "auxiliary": "len(canonical_game_bytes[game_ordinal])",
    "binding_class": C.BINDING_DATA,
    "kind": "SEMANTIC_BINDING",
    "namespace_id": 2,
    "record_id": "binding_record_id",
    "semantic_code": "game_ordinal+1",
}
_OPAQUE_TEMPLATE = {
    "data": "canonical_game_bytes[game_ordinal]",
    "data_binding_ref": "binding_record_id",
    "kind": "OPAQUE_DATA",
    "record_id": "opaque_record_id",
}
_PROTOTYPE_KEYS = frozenset(("kind", "prototype_id", "role", "source_record_id"))
_PROTOTYPE_SOURCE_IDS = (1, 6, 9, 12, 13, 14, 15, 16, 17, 19, 20, 25, 26, 29)
_FIXTURE_PLAN_KEYS = frozenset(
    ("assignments", "binding_record", "opaque_record", "payload_encoding")
)
_FIXTURE_ASSIGNMENT_KEYS = frozenset(
    (
        "binding_record_id",
        "case_name",
        "closure",
        "fixture_ordinal",
        "opaque_record_id",
        "role",
        "section_id",
        "semantic_copy_id",
    )
)
_FIXTURE_BINDING_TEMPLATE = {
    "argument": 29,
    "auxiliary": "len(chess_fixture_binary[fixture_ordinal])",
    "binding_class": C.BINDING_DATA,
    "kind": "SEMANTIC_BINDING",
    "namespace_id": 3,
    "record_id": "binding_record_id",
    "semantic_code": "fixture_ordinal+1",
}
_FIXTURE_OPAQUE_TEMPLATE = {
    "data": "chess_fixture_binary[fixture_ordinal]",
    "data_binding_ref": "binding_record_id",
    "kind": "OPAQUE_DATA",
    "record_id": "opaque_record_id",
}
_CHESS_CASES = (
    ("castling-positive-first-kingside", "castling-kingside"),
    ("castling-positive-first-queenside", "castling-queenside"),
    ("en-passant-legal-capture", "en-passant"),
    ("promotion-quiet-queen", "promotion-queen"),
    ("promotion-quiet-rook", "promotion-rook"),
    ("promotion-quiet-bishop", "promotion-bishop"),
    ("promotion-quiet-knight", "promotion-knight"),
    ("geometry-illegal-self-check", "self-check-rejection"),
    ("en-passant-nominal-without-capturer", "board-local-history-contrast"),
    ("en-passant-effective-key-retained", "board-local-history-contrast"),
)
_FAMILIES = (
    "setup_turn",
    "ordinary_move_capture",
    "control_vs_legal",
    "king_safety",
    "castling",
    "en_passant",
    "promotion",
    "position_history_draw",
    "record_replay",
)


class SliceError(ValueError):
    """One immutable build-time slice-v0 failure."""

    __slots__ = ("_reason", "_path")

    def __init__(self, reason: str, path: str):
        if type(reason) is not str or type(path) is not str:
            raise TypeError("slice error fields must be strings")
        self._reason = reason
        self._path = path
        super().__init__(reason, path)

    @property
    def reason(self) -> str:
        return self._reason

    @property
    def path(self) -> str:
        return self._path

    def __setattr__(self, name: str, value: object) -> None:
        if name in SliceError.__slots__ and hasattr(self, name):
            raise AttributeError(f"{name} is read-only")
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if name in SliceError.__slots__:
            raise AttributeError(f"{name} is read-only")
        super().__delattr__(name)


@dataclass(frozen=True, slots=True)
class SliceAtomicAssignment:
    section_id: int
    closure: str
    semantic_copy_id: int
    record_ids: tuple[int, ...]
    game_ordinal: int | None
    fixture_ordinal: int | None


@dataclass(frozen=True, slots=True)
class SliceCapacityPrototype:
    kind: int
    prototype_id: str
    source_record_id: int
    frame_length: int


@dataclass(frozen=True, slots=True)
class SliceTierRoot:
    section_id: int
    closure: str
    semantic_copy_id: int
    record_id: int


@dataclass(frozen=True, slots=True)
class SliceCompilation:
    required_content_bytes: bytes
    required_content_sha256: str
    required_projection: content.ContentProjectionView
    content_bytes: bytes
    content_sha256: str
    projection: content.ContentProjectionView
    game_payloads: tuple[bytes, ...]
    fixture_payloads: tuple[bytes, ...]
    atomic_assignments: tuple[SliceAtomicAssignment, ...]
    capacity_prototypes: tuple[SliceCapacityPrototype, ...]
    tier_roots: tuple[SliceTierRoot, ...]
    chess_fixture_cases: tuple[str, ...]
    selected_curriculum_families: tuple[str, ...]


def _fail(reason: str, path: str) -> NoReturn:
    raise SliceError(reason, path)


def _closed(value: object, keys: frozenset[str], path: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        _fail("closed_shape", path)
    return value


def _list(value: object, path: str) -> list[object]:
    if type(value) is not list:
        _fail("bad_type", path)
    return value


def _int(value: object, low: int, high: int, path: str) -> int:
    if type(value) is not int or not low <= value <= high:
        _fail("bad_value", path)
    return value


def _string(value: object, path: str) -> str:
    if type(value) is not str or not value or not value.isascii():
        _fail("bad_value", path)
    return value


def _hex_digest(value: object, path: str) -> str:
    text = _string(value, path)
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        _fail("bad_value", path)
    return text


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _bound_file(declaration: object, raw: bytes, expected_path: str, path: str) -> None:
    binding = _closed(declaration, _FILE_BINDING_KEYS, path)
    if binding["path"] != expected_path:
        _fail("bad_value", f"{path}.path")
    if _hex_digest(binding["sha256"], f"{path}.sha256") != _sha256(raw):
        _fail("hash_mismatch", path)


def _identity_hex(domain: bytes, field: bytes) -> str:
    preimage = domain + b"\0\1" + len(field).to_bytes(4, "big") + field
    return _sha256(preimage)


def _game_payloads(game_set: bytes, path: str) -> tuple[bytes, ...]:
    if len(game_set) > _GAME_SET_CAP:
        _fail("limit_exceeded", path)
    if len(game_set) < 2:
        _fail("truncated", path)
    count = int.from_bytes(game_set[:2], "big")
    if count != _GAME_COUNT:
        _fail("bad_value", f"{path}.count")
    offset = 2
    total_plies = 0
    previous: bytes | None = None
    output: list[bytes] = []
    for ordinal in range(count):
        start = offset
        if len(game_set) - offset < 2:
            _fail("truncated", f"{path}[{ordinal}]")
        ply_count = int.from_bytes(game_set[offset : offset + 2], "big")
        if not 1 <= ply_count <= 4096:
            _fail("bad_value", f"{path}[{ordinal}].ply_count")
        total_plies += ply_count
        if total_plies > 65_535:
            _fail("limit_exceeded", f"{path}[{ordinal}].ply_count")
        size = 2 + 2 * ply_count + 1
        if size > len(game_set) - offset:
            _fail("truncated", f"{path}[{ordinal}]")
        offset += size
        value = game_set[start:offset]
        if previous is not None and value <= previous:
            _fail("bad_order", f"{path}[{ordinal}]")
        output.append(value)
        previous = value
    if offset != len(game_set):
        _fail("trailing_data", path)
    return tuple(output)


def _content_frames(stream: bytes, path: str) -> dict[int, bytes]:
    if len(stream) < 4:
        _fail("truncated", path)
    count = int.from_bytes(stream[2:4], "big")
    offset = 4
    frames: dict[int, bytes] = {}
    for index in range(count):
        start = offset
        if len(stream) - offset < 8:
            _fail("truncated", f"{path}.records[{index}]")
        record_id = int.from_bytes(stream[offset : offset + 2], "big")
        payload_length = int.from_bytes(stream[offset + 4 : offset + 8], "big")
        size = 8 + payload_length
        if size > len(stream) - offset:
            _fail("truncated", f"{path}.records[{index}]")
        offset += size
        if record_id in frames:
            _fail("duplicate", f"{path}.records[{index}]")
        frames[record_id] = stream[start:offset]
    if offset != len(stream):
        _fail("trailing_data", path)
    return frames


def _base_projection(
    declaration: object, fixture: dict[str, object]
) -> tuple[content.ContentAuthoringProjection, content.ContentProjectionView, bytes]:
    base = _closed(declaration, _BASE_KEYS, "content_base")
    name = _string(base["fixture_name"], "content_base.fixture_name")
    bases = _list(fixture.get("bases"), "inputs.content_fixture.bases")
    matches = [
        item for item in bases if type(item) is dict and item.get("name") == name
    ]
    if len(matches) != 1:
        _fail("bad_reference", "content_base.fixture_name")
    selected = _closed(
        matches[0],
        frozenset(
            ("name", "projection", "stream_hex", "stream_length", "stream_sha256")
        ),
        "inputs.content_fixture.base",
    )
    stream_hex = _string(
        selected["stream_hex"], "inputs.content_fixture.base.stream_hex"
    )
    try:
        stream = bytes.fromhex(stream_hex)
    except ValueError:
        _fail("bad_value", "inputs.content_fixture.base.stream_hex")
    length = _int(
        base["stream_length"],
        0,
        C.CONTENT_MAX_STREAM_BYTES,
        "content_base.stream_length",
    )
    digest = _hex_digest(base["stream_sha256"], "content_base.stream_sha256")
    if (
        selected["stream_length"] != length
        or selected["stream_sha256"] != digest
        or len(stream) != length
        or _sha256(stream) != digest
    ):
        _fail("hash_mismatch", "content_base")
    try:
        accepted = content.stream_validation(stream)
    except content.ContentReject:
        _fail("invalid_content", "content_base")
    view = content.projection_view(accepted)
    removed = _int(
        base["removed_root_record_id"], 1, 0xFFFF, "content_base.removed_root_record_id"
    )
    retained = tuple(
        _int(value, 1, 0xFFFF, f"content_base.retain_record_ids[{index}]")
        for index, value in enumerate(
            _list(base["retain_record_ids"], "content_base.retain_record_ids")
        )
    )
    actual_ids = tuple(item.record_id for item in view.records)
    if view.root_record_id != removed or actual_ids != (*retained, removed):
        _fail("bad_reference", "content_base.retain_record_ids")
    if tuple(sorted(set(retained))) != retained:
        _fail("bad_order", "content_base.retain_record_ids")
    authored = content.authoring_from_validated(view)
    try:
        reencoded = content.encode_content_v0(authored)
    except content.ContentAuthoringError:
        _fail("invalid_content", "content_base")
    if reencoded != stream:
        _fail("unexpected_compilation", "content_base")
    return (
        content.ContentAuthoringProjection(
            authored.version,
            tuple(item for item in authored.records if item.record_id in set(retained)),
        ),
        view,
        stream,
    )


def _record(value: object, index: int) -> content.ContentRecordView:
    path = f"records[{index}]"
    if type(value) is not dict:
        _fail("bad_type", path)
    kind = value.get("kind")
    if kind == "ATOM_SCHEMA":
        row = _closed(
            value,
            frozenset(
                (
                    "atom_class",
                    "atom_width",
                    "entries",
                    "kind",
                    "max_value",
                    "min_value",
                    "record_id",
                )
            ),
            path,
        )
        entries = _list(row["entries"], f"{path}.entries")
        payload = content.ContentAtomSchema(
            _int(row["atom_class"], 0, 0xFF, f"{path}.atom_class"),
            _int(row["atom_width"], 0, 0xFF, f"{path}.atom_width"),
            tuple(entries),
            _int(row["min_value"], 0, 0xFFFFFFFF, f"{path}.min_value"),
            _int(row["max_value"], 0, 0xFFFFFFFF, f"{path}.max_value"),
            None,
        )
    elif kind == "FIELD_SCHEMA":
        row = _closed(value, frozenset(("fields", "kind", "record_id")), path)
        fields = []
        for part, field in enumerate(_list(row["fields"], f"{path}.fields")):
            field_path = f"{path}.fields[{part}]"
            item = _closed(
                field,
                frozenset(("count", "name_text_ref", "storage", "type")),
                field_path,
            )
            fields.append(
                content.ContentFieldSpec(
                    _int(
                        item["name_text_ref"], 1, 0xFFFF, f"{field_path}.name_text_ref"
                    ),
                    _int(item["storage"], 0, 0xFF, f"{field_path}.storage"),
                    _int(item["type"], 1, 0xFFFF, f"{field_path}.type"),
                    _int(item["count"], 0, 0xFFFF, f"{field_path}.count"),
                )
            )
        payload = content.ContentFieldSchema(tuple(fields))
    elif kind == "TUPLE":
        row = _closed(
            value,
            frozenset(("field_schema_ref", "field_values", "kind", "record_id")),
            path,
        )
        fields = []
        for part, field in enumerate(
            _list(row["field_values"], f"{path}.field_values")
        ):
            field_path = f"{path}.field_values[{part}]"
            item = _closed(field, frozenset(("record_refs",)), field_path)
            fields.append(
                content.ContentRecordRefFieldValue(
                    tuple(
                        _int(reference, 1, 0xFFFF, f"{field_path}.record_refs[{at}]")
                        for at, reference in enumerate(
                            _list(item["record_refs"], f"{field_path}.record_refs")
                        )
                    )
                )
            )
        payload = content.ContentTuple(
            _int(row["field_schema_ref"], 1, 0xFFFF, f"{path}.field_schema_ref"),
            tuple(fields),
        )
    elif kind == "FEEDBACK":
        row = _closed(
            value,
            frozenset(
                (
                    "display_ref",
                    "feedback_code",
                    "kind",
                    "predicate_result_ref",
                    "record_id",
                )
            ),
            path,
        )
        payload = content.ContentFeedback(
            _int(row["feedback_code"], 0, 0xFFFF, f"{path}.feedback_code"),
            _int(row["display_ref"], 0, 0xFFFF, f"{path}.display_ref"),
            _int(
                row["predicate_result_ref"], 0, 0xFFFF, f"{path}.predicate_result_ref"
            ),
        )
    elif kind == "LESSON_NODE":
        row = _closed(
            value,
            frozenset(
                (
                    "answer_mode",
                    "case_count",
                    "cases",
                    "default_feedback_ref",
                    "default_next_node_ref",
                    "flags",
                    "item_event_budget",
                    "kind",
                    "max_selections",
                    "passive_trace_ref",
                    "predicate_result_ref",
                    "presentation_ref",
                    "record_id",
                    "region_set_ref",
                    "response_shape",
                    "role",
                )
            ),
            path,
        )
        cases = _list(row["cases"], f"{path}.cases")
        if row["case_count"] != len(cases) or cases:
            _fail("bad_value", f"{path}.cases")
        payload = content.ContentLessonNode(
            _int(row["role"], 0, 0xFF, f"{path}.role"),
            _int(row["response_shape"], 0, 0xFF, f"{path}.response_shape"),
            _int(row["answer_mode"], 0, 0xFF, f"{path}.answer_mode"),
            _int(row["flags"], 0, 0xFF, f"{path}.flags"),
            _int(row["presentation_ref"], 0, 0xFFFF, f"{path}.presentation_ref"),
            _int(row["region_set_ref"], 0, 0xFFFF, f"{path}.region_set_ref"),
            _int(
                row["predicate_result_ref"], 0, 0xFFFF, f"{path}.predicate_result_ref"
            ),
            _int(row["passive_trace_ref"], 0, 0xFFFF, f"{path}.passive_trace_ref"),
            _int(row["max_selections"], 0, 0xFFFF, f"{path}.max_selections"),
            _int(row["item_event_budget"], 0, 0xFFFF, f"{path}.item_event_budget"),
            (),
            _int(
                row["default_feedback_ref"], 0, 0xFFFF, f"{path}.default_feedback_ref"
            ),
            _int(
                row["default_next_node_ref"], 0, 0xFFFF, f"{path}.default_next_node_ref"
            ),
        )
    elif kind == "ROOT":
        row = _closed(
            value,
            frozenset(("entry_node_ref", "global_event_budget", "kind", "record_id")),
            path,
        )
        payload = content.ContentRoot(
            _int(row["entry_node_ref"], 1, 0xFFFF, f"{path}.entry_node_ref"),
            _int(row["global_event_budget"], 1, 0xFFFF, f"{path}.global_event_budget"),
        )
    else:
        _fail("bad_value", f"{path}.kind")
    return content.ContentRecordView(
        _int(row["record_id"], 1, 0xFFFF, f"{path}.record_id"), payload
    )


def _game_records(
    declaration: object, game_payloads: tuple[bytes, ...]
) -> tuple[tuple[content.ContentRecordView, ...], tuple[SliceAtomicAssignment, ...]]:
    plan = _closed(declaration, _GAME_PLAN_KEYS, "game_record_plan")
    if plan["binding_record"] != _BINDING_TEMPLATE:
        _fail("bad_value", "game_record_plan.binding_record")
    if plan["opaque_record"] != _OPAQUE_TEMPLATE:
        _fail("bad_value", "game_record_plan.opaque_record")
    rows = _list(plan["assignments"], "game_record_plan.assignments")
    if len(rows) != _GAME_COUNT:
        _fail("bad_value", "game_record_plan.assignments")
    records: list[content.ContentRecordView] = []
    assignments: list[SliceAtomicAssignment] = []
    sections: set[int] = set()
    for ordinal, value in enumerate(rows):
        path = f"game_record_plan.assignments[{ordinal}]"
        row = _closed(value, _GAME_ASSIGNMENT_KEYS, path)
        expected_binding = 30 + 2 * ordinal
        binding_id = _int(
            row["binding_record_id"], 1, 0xFFFF, f"{path}.binding_record_id"
        )
        opaque_id = _int(row["opaque_record_id"], 1, 0xFFFF, f"{path}.opaque_record_id")
        section_id = _int(row["section_id"], 1, 0xFFFFFFFF, f"{path}.section_id")
        if (
            row["game_ordinal"] != ordinal
            or binding_id != expected_binding
            or opaque_id != expected_binding + 1
            or row["closure"] != "m2_all_only"
            or row["semantic_copy_id"] != 0
            or section_id != 100 + ordinal
            or section_id in sections
        ):
            _fail("bad_value", path)
        sections.add(section_id)
        records.extend(
            (
                content.ContentRecordView(
                    binding_id,
                    content.ContentSemanticBinding(
                        C.BINDING_DATA,
                        2,
                        ordinal + 1,
                        29,
                        len(game_payloads[ordinal]),
                    ),
                ),
                content.ContentRecordView(
                    opaque_id,
                    content.ContentOpaqueData(
                        binding_id, tuple(game_payloads[ordinal])
                    ),
                ),
            )
        )
        assignments.append(
            SliceAtomicAssignment(
                section_id,
                "m2_all_only",
                0,
                (binding_id, opaque_id),
                ordinal,
                None,
            )
        )
    return tuple(records), tuple(assignments)


def _support_assignments(
    declaration: object,
) -> tuple[tuple[SliceAtomicAssignment, ...], tuple[SliceTierRoot, ...]]:
    plan = _closed(
        declaration, frozenset(("support_assignments", "tier_roots")), "section_plan"
    )
    rows = _list(plan["support_assignments"], "section_plan.support_assignments")
    expected = (
        (16, "m2_required", 0, tuple(range(1, 29))),
        (17, "m2_all_only", 0, (29,)),
        (210, "m2_all_only", 0, tuple(range(178, 182))),
    )
    if len(rows) != len(expected):
        _fail("bad_value", "section_plan.support_assignments")
    output = []
    keys = frozenset(("closure", "record_ids", "section_id", "semantic_copy_id"))
    for index, (value, wanted) in enumerate(zip(rows, expected, strict=True)):
        path = f"section_plan.support_assignments[{index}]"
        row = _closed(value, keys, path)
        record_ids = tuple(_list(row["record_ids"], f"{path}.record_ids"))
        actual = (
            row["section_id"],
            row["closure"],
            row["semantic_copy_id"],
            record_ids,
        )
        if actual != wanted:
            _fail("bad_value", path)
        output.append(
            SliceAtomicAssignment(
                wanted[0], wanted[1], wanted[2], wanted[3], None, None
            )
        )
    root_rows = _list(plan["tier_roots"], "section_plan.tier_roots")
    root_keys = frozenset(
        ("closure", "record_id", "section_id", "semantic_copy_id", "source")
    )
    root_expected = (
        (2, "m2_required", 0, 29, "content_base.removed_root_record"),
        (3, "m2_all", 0, 182, "records"),
    )
    if len(root_rows) != len(root_expected):
        _fail("bad_value", "section_plan.tier_roots")
    roots = []
    for index, (value, wanted) in enumerate(zip(root_rows, root_expected, strict=True)):
        path = f"section_plan.tier_roots[{index}]"
        row = _closed(value, root_keys, path)
        actual = (
            row["section_id"],
            row["closure"],
            row["semantic_copy_id"],
            row["record_id"],
            row["source"],
        )
        if actual != wanted:
            _fail("bad_value", path)
        roots.append(SliceTierRoot(wanted[0], wanted[1], wanted[2], wanted[3]))
    return tuple(output), tuple(roots)


def _capacity_prototypes(
    declaration: object,
    base_view: content.ContentProjectionView,
    base_stream: bytes,
) -> tuple[SliceCapacityPrototype, ...]:
    rows = _list(declaration, "capacity_prototypes")
    if len(rows) != 14:
        _fail("bad_value", "capacity_prototypes")
    by_id = {record.record_id: record for record in base_view.records}
    frames = _content_frames(base_stream, "capacity_prototypes")
    output = []
    for index, (value, source_id) in enumerate(
        zip(rows, _PROTOTYPE_SOURCE_IDS, strict=True)
    ):
        path = f"capacity_prototypes[{index}]"
        row = _closed(value, _PROTOTYPE_KEYS, path)
        kind = index + 1
        if (
            row["kind"] != kind
            or row["prototype_id"] != f"generic-base-kind-{kind:02d}"
            or row["role"] != "nonsemantic-capacity-only"
            or row["source_record_id"] != source_id
            or source_id not in by_id
            or by_id[source_id].kind != kind
        ):
            _fail("bad_value", path)
        try:
            frame_length = len(frames[source_id])
        except KeyError:
            _fail("bad_reference", path)
        output.append(
            SliceCapacityPrototype(
                kind,
                row["prototype_id"],
                source_id,
                frame_length,
            )
        )
    return tuple(output)


def _wire_hex(value: object, path: str, length: int | None = None) -> bytes:
    text = _string(value, path)
    if len(text) % 2:
        _fail("bad_value", path)
    try:
        data = bytes.fromhex(text)
    except ValueError:
        _fail("bad_value", path)
    if length is not None and len(data) != length:
        _fail("bad_value", path)
    return data


def _history_location(value: object, path: str) -> tuple[int, int]:
    if type(value) is not dict:
        _fail("bad_type", path)
    if value.get("kind") == "none":
        _closed(value, frozenset(("kind",)), path)
        return 0, 0xFF
    row = _closed(value, frozenset(("kind", "square")), path)
    if row["kind"] != "square":
        _fail("bad_value", f"{path}.kind")
    return 1, _int(row["square"], 0, 63, f"{path}.square")


def _fixture_binary(case: object, ordinal: int, path: str) -> bytes:
    row = _closed(case, frozenset(("expected", "input", "name", "operation")), path)
    if ordinal < 8:
        if row["operation"] != "apply_move":
            _fail("bad_value", f"{path}.operation")
        input_row = _closed(
            row["input"], frozenset(("move_hex", "moves_hex")), f"{path}.input"
        )
        prior = _wire_hex(input_row["moves_hex"], f"{path}.input.moves_hex")
        if len(prior) % 2:
            _fail("bad_value", f"{path}.input.moves_hex")
        subject = _wire_hex(input_row["move_hex"], f"{path}.input.move_hex", 2)
        expected = (
            _closed(row["expected"], frozenset(("success",)), f"{path}.expected")
            if ordinal < 7
            else None
        )
        if ordinal in (0, 1):
            success = _closed(
                expected["success"],
                frozenset(("position_hex",)),
                f"{path}.expected.success",
            )
            projected = b"\x01" + _wire_hex(
                success["position_hex"], f"{path}.expected.success.position_hex", 67
            )
        elif ordinal == 2:
            success = _closed(
                expected["success"],
                frozenset(("halfmove_clock", "position_hex")),
                f"{path}.expected.success",
            )
            projected = (
                b"\x02"
                + _int(
                    success["halfmove_clock"],
                    0,
                    0xFFFF,
                    f"{path}.expected.success.halfmove_clock",
                ).to_bytes(2, "big")
                + _wire_hex(
                    success["position_hex"], f"{path}.expected.success.position_hex", 67
                )
            )
        elif ordinal < 7:
            success = _closed(
                expected["success"],
                frozenset(("king_in_check", "position_hex", "terminal")),
                f"{path}.expected.success",
            )
            checked = success["king_in_check"]
            if type(checked) is not bool:
                _fail("bad_value", f"{path}.expected.success.king_in_check")
            projected = (
                b"\x03"
                + _wire_hex(
                    success["position_hex"], f"{path}.expected.success.position_hex", 67
                )
                + bytes(
                    (
                        int(checked),
                        _int(
                            success["terminal"],
                            0,
                            0xFF,
                            f"{path}.expected.success.terminal",
                        ),
                    )
                )
            )
        else:
            rejected = _closed(
                row["expected"], frozenset(("rejection",)), f"{path}.expected"
            )
            projected = b"\x04" + _int(
                rejected["rejection"], 0, 0xFFFF, f"{path}.expected.rejection"
            ).to_bytes(2, "big")
    else:
        if row["operation"] != "evaluate_predicate":
            _fail("bad_value", f"{path}.operation")
        input_row = _closed(
            row["input"], frozenset(("input", "predicate_id")), f"{path}.input"
        )
        if input_row["predicate_id"] != "chess.history_claim":
            _fail("bad_value", f"{path}.input.predicate_id")
        history_input = _closed(
            input_row["input"],
            frozenset(("moves_hex", "variant")),
            f"{path}.input.input",
        )
        if history_input["variant"] != "history-claim":
            _fail("bad_value", f"{path}.input.input.variant")
        prior = _wire_hex(history_input["moves_hex"], f"{path}.input.input.moves_hex")
        if len(prior) % 2:
            _fail("bad_value", f"{path}.input.input.moves_hex")
        subject = b""
        outer = _closed(row["expected"], frozenset(("success",)), f"{path}.expected")
        success = _closed(
            outer["success"], frozenset(("result",)), f"{path}.expected.success"
        )
        result = _closed(
            success["result"],
            frozenset(
                (
                    "current_key_occurrences",
                    "effective_ep",
                    "fifty_move_available",
                    "halfmove_clock",
                    "nominal_ep",
                    "played_plies",
                    "threefold_available",
                )
            ),
            f"{path}.expected.success.result",
        )
        nominal_kind, nominal_square = _history_location(
            result["nominal_ep"], f"{path}.expected.success.result.nominal_ep"
        )
        effective_kind, effective_square = _history_location(
            result["effective_ep"], f"{path}.expected.success.result.effective_ep"
        )
        fifty = result["fifty_move_available"]
        threefold = result["threefold_available"]
        if type(fifty) is not bool or type(threefold) is not bool:
            _fail("bad_value", f"{path}.expected.success.result")
        projected = b"\x05" + b"".join(
            (
                _int(
                    result["played_plies"],
                    0,
                    0xFFFF,
                    f"{path}.expected.success.result.played_plies",
                ).to_bytes(2, "big"),
                _int(
                    result["halfmove_clock"],
                    0,
                    0xFFFF,
                    f"{path}.expected.success.result.halfmove_clock",
                ).to_bytes(2, "big"),
                _int(
                    result["current_key_occurrences"],
                    0,
                    0xFFFF,
                    f"{path}.expected.success.result.current_key_occurrences",
                ).to_bytes(2, "big"),
                bytes(
                    (
                        nominal_kind,
                        nominal_square,
                        effective_kind,
                        effective_square,
                        int(fifty),
                        int(threefold),
                    )
                ),
            )
        )
    if len(prior) > 0xFFFF or len(subject) > 0xFFFF or len(projected) > 0xFFFF:
        _fail("limit_exceeded", path)
    return b"".join(
        (
            bytes((0, ordinal + 1)),
            len(prior).to_bytes(2, "big"),
            prior,
            len(subject).to_bytes(2, "big"),
            subject,
            len(projected).to_bytes(2, "big"),
            projected,
        )
    )


def _chess_fixture_records(
    declaration: object, fixture: dict[str, object]
) -> tuple[
    tuple[content.ContentRecordView, ...],
    tuple[SliceAtomicAssignment, ...],
    tuple[str, ...],
    tuple[bytes, ...],
]:
    plan = _closed(declaration, _FIXTURE_PLAN_KEYS, "chess_fixture_cases")
    if plan["payload_encoding"] != "slice-v0-chess-fixture-binary":
        _fail("bad_value", "chess_fixture_cases.payload_encoding")
    if plan["binding_record"] != _FIXTURE_BINDING_TEMPLATE:
        _fail("bad_value", "chess_fixture_cases.binding_record")
    if plan["opaque_record"] != _FIXTURE_OPAQUE_TEMPLATE:
        _fail("bad_value", "chess_fixture_cases.opaque_record")
    rows = _list(plan["assignments"], "chess_fixture_cases.assignments")
    if len(rows) != len(_CHESS_CASES):
        _fail("bad_value", "chess_fixture_cases.assignments")
    cases = _list(fixture.get("cases"), "inputs.chess_fixture.cases")
    by_name = {item.get("name"): item for item in cases if type(item) is dict}
    if len(by_name) != len(cases):
        _fail("duplicate", "inputs.chess_fixture.cases")
    records = []
    assignments = []
    names = []
    payloads = []
    for index, (value, wanted) in enumerate(zip(rows, _CHESS_CASES, strict=True)):
        path = f"chess_fixture_cases.assignments[{index}]"
        row = _closed(value, _FIXTURE_ASSIGNMENT_KEYS, path)
        binding_id = 158 + 2 * index
        opaque_id = binding_id + 1
        section_id = 200 + index
        if (
            (row["case_name"], row["role"]) != wanted
            or row["fixture_ordinal"] != index
            or row["binding_record_id"] != binding_id
            or row["opaque_record_id"] != opaque_id
            or row["section_id"] != section_id
            or row["closure"] != "m2_all_only"
            or row["semantic_copy_id"] != 0
            or wanted[0] not in by_name
        ):
            _fail("bad_reference", path)
        payload = _fixture_binary(
            by_name[wanted[0]], index, f"inputs.chess_fixture.{wanted[0]}"
        )
        records.extend(
            (
                content.ContentRecordView(
                    binding_id,
                    content.ContentSemanticBinding(
                        C.BINDING_DATA, 3, index + 1, 29, len(payload)
                    ),
                ),
                content.ContentRecordView(
                    opaque_id, content.ContentOpaqueData(binding_id, tuple(payload))
                ),
            )
        )
        assignments.append(
            SliceAtomicAssignment(
                section_id,
                "m2_all_only",
                0,
                (binding_id, opaque_id),
                None,
                index,
            )
        )
        names.append(wanted[0])
        payloads.append(payload)
    return tuple(records), tuple(assignments), tuple(names), tuple(payloads)


def _families(declaration: object, curriculum_bytes: bytes) -> tuple[str, ...]:
    rows = _list(declaration, "selected_curriculum_families")
    if tuple(rows) != _FAMILIES:
        _fail("bad_value", "selected_curriculum_families")
    try:
        parsed = tomllib.loads(curriculum_bytes.decode("utf-8"))
        available = {item["id"] for item in parsed["family"]}
    except (UnicodeError, tomllib.TOMLDecodeError, KeyError, TypeError):
        _fail("bad_value", "inputs.curriculum")
    if any(value not in available for value in _FAMILIES):
        _fail("bad_reference", "selected_curriculum_families")
    return _FAMILIES


def _asymmetry_probe(
    declaration: object, base_view: content.ContentProjectionView
) -> None:
    path = "asymmetry_probe"
    row = _closed(
        declaration,
        frozenset(
            (
                "cells",
                "columns",
                "committed_response_hex",
                "detects",
                "matrix_record_id",
                "path_actions_hex",
                "region_ids",
                "region_set_record_id",
                "rows",
            )
        ),
        path,
    )
    expected = {
        "cells": [0, 1, 2, 3, 4, 5],
        "columns": 3,
        "committed_response_hex": "0100010002",
        "detects": ["transpose", "reflection", "polarity", "row-column", "bit-order"],
        "matrix_record_id": 12,
        "path_actions_hex": ["01000002", "03000000"],
        "region_ids": [1, 2, 3],
        "region_set_record_id": 15,
        "rows": 2,
    }
    if row != expected:
        _fail("bad_value", path)
    by_id = {record.record_id: record.payload for record in base_view.records}
    matrix = by_id.get(12)
    regions = by_id.get(15)
    if (
        type(matrix) is not content.ContentMatrix
        or (matrix.rows, matrix.columns, list(matrix.cells))
        != (2, 3, expected["cells"])
        or type(regions) is not content.ContentRegionSet
        or regions.surface_matrix_ref != 12
        or [item.region_id for item in regions.regions] != expected["region_ids"]
    ):
        _fail("bad_reference", path)
    cells = matrix.cells
    transpose = tuple(
        cells[row_index * 3 + column_index]
        for column_index in range(3)
        for row_index in range(2)
    )
    reflection = tuple(
        cells[row_index * 3 + (2 - column_index)]
        for row_index in range(2)
        for column_index in range(3)
    )
    bit_reversed = tuple(int(f"{value:08b}"[::-1], 2) for value in cells)
    if (
        transpose == cells
        or reflection == cells
        or bit_reversed == cells
        or tuple(value ^ 0xFF for value in cells) == cells
    ):
        _fail("bad_value", path)


def compile_slice_v0(
    manifest_bytes: bytes,
    content_fixture_bytes: bytes,
    chess_fixture_bytes: bytes,
    game_set_bytes: bytes,
    content_spec_bytes: bytes,
    constants_bytes: bytes,
    curriculum_bytes: bytes,
) -> SliceCompilation:
    """Compile one closed slice declaration into independently checked content."""

    values = (
        manifest_bytes,
        content_fixture_bytes,
        chess_fixture_bytes,
        game_set_bytes,
        content_spec_bytes,
        constants_bytes,
        curriculum_bytes,
    )
    if any(type(value) is not bytes for value in values):
        raise TypeError("slice-v0 inputs must be bytes")
    try:
        declaration = canonical_manifest.validate_canonical_manifest(manifest_bytes)
        content_fixture = canonical_manifest.validate_canonical_manifest(
            content_fixture_bytes
        )
        chess_fixture = canonical_manifest.validate_canonical_manifest(
            chess_fixture_bytes
        )
    except canonical_manifest.ManifestError:
        _fail("invalid_manifest", "inputs")
    _closed(declaration, _ROOT_KEYS, "manifest")
    if declaration["schema"] != _SLICE_SCHEMA:
        _fail("bad_value", "schema")

    inputs = _closed(declaration["inputs"], _INPUT_KEYS, "inputs")
    _bound_file(
        inputs["content_fixture"],
        content_fixture_bytes,
        "conformance/content-v0.json",
        "inputs.content_fixture",
    )
    _bound_file(
        inputs["chess_fixture"],
        chess_fixture_bytes,
        "conformance/chess-v0.json",
        "inputs.chess_fixture",
    )
    _bound_file(
        inputs["content_spec"],
        content_spec_bytes,
        "spec/content-v0.md",
        "inputs.content_spec",
    )
    _bound_file(
        inputs["constants"],
        constants_bytes,
        "spec/constants-v0.toml",
        "inputs.constants",
    )
    _bound_file(
        inputs["curriculum"],
        curriculum_bytes,
        "spec/curriculum-v0.toml",
        "inputs.curriculum",
    )
    game_binding = _closed(inputs["game_set"], _GAME_BINDING_KEYS, "inputs.game_set")
    if (
        game_binding["path"] != "reports/game-set-v0.bin"
        or game_binding["count"] != _GAME_COUNT
    ):
        _fail("bad_value", "inputs.game_set")
    if _hex_digest(game_binding["sha256"], "inputs.game_set.sha256") != _sha256(
        game_set_bytes
    ):
        _fail("hash_mismatch", "inputs.game_set")
    if _hex_digest(
        game_binding["identity"], "inputs.game_set.identity"
    ) != _identity_hex(_GAME_SET_DOMAIN, game_set_bytes):
        _fail("identity_mismatch", "inputs.game_set")

    game_payloads = _game_payloads(game_set_bytes, "inputs.game_set")
    base, base_view, required_stream = _base_projection(
        declaration["content_base"], content_fixture
    )
    if (
        len(required_stream) != _REQUIRED_CONTENT_BYTES
        or len(base_view.records) != _REQUIRED_RECORD_COUNT
    ):
        _fail("unexpected_compilation", "content_base")
    capacity_prototypes = _capacity_prototypes(
        declaration["capacity_prototypes"], base_view, required_stream
    )
    fixture_records, fixture_assignments, chess_cases, fixture_payloads = (
        _chess_fixture_records(declaration["chess_fixture_cases"], chess_fixture)
    )
    families = _families(declaration["selected_curriculum_families"], curriculum_bytes)
    _asymmetry_probe(declaration["asymmetry_probe"], base_view)

    declared_records = tuple(
        _record(value, index)
        for index, value in enumerate(_list(declaration["records"], "records"))
    )
    if tuple(item.record_id for item in declared_records) != (
        29,
        178,
        179,
        180,
        181,
        182,
    ):
        _fail("bad_order", "records")
    game_records, game_assignments = _game_records(
        declaration["game_record_plan"], game_payloads
    )
    authored = content.ContentAuthoringProjection(
        C.CONTENT_VERSION,
        (
            *base.records,
            declared_records[0],
            *game_records,
            *fixture_records,
            *declared_records[1:],
        ),
    )
    try:
        stream = content.encode_content_v0(authored)
        accepted = content.stream_validation(stream)
    except (content.ContentAuthoringError, content.ContentReject):
        _fail("invalid_content", "records")
    projection = content.projection_view(accepted)
    if len(projection.records) != _ALL_RECORD_COUNT:
        _fail("unexpected_compilation", "records")

    support, tier_roots = _support_assignments(declaration["section_plan"])
    assignments = tuple(
        sorted(
            (*support, *fixture_assignments, *game_assignments),
            key=lambda item: item.section_id,
        )
    )
    assigned = [
        record_id for assignment in assignments for record_id in assignment.record_ids
    ]
    actual = [record.record_id for record in projection.records]
    if tuple(assigned) != tuple(actual[:-1]) or len(assigned) != len(set(assigned)):
        _fail("assignment_coverage", "section_plan")
    required_assigned = (*support[0].record_ids, tier_roots[0].record_id)
    if required_assigned != tuple(record.record_id for record in base_view.records):
        _fail("assignment_coverage", "section_plan.tier_roots[0]")
    if tier_roots[1].record_id != actual[-1]:
        _fail("assignment_coverage", "section_plan.tier_roots[1]")
    sections = [assignment.section_id for assignment in assignments]
    if len(sections) != len(set(sections)):
        _fail("duplicate", "section_plan")
    required_frames = _content_frames(required_stream, "content_base")
    all_frames = _content_frames(stream, "records")
    try:
        required_assembled = b"".join(
            (
                required_stream[:4],
                *(required_frames[record_id] for record_id in support[0].record_ids),
                required_frames[tier_roots[0].record_id],
            )
        )
        all_assembled = b"".join(
            (
                stream[:4],
                *(
                    all_frames[record_id]
                    for assignment in assignments
                    for record_id in assignment.record_ids
                ),
                all_frames[tier_roots[1].record_id],
            )
        )
    except KeyError:
        _fail("assignment_coverage", "section_plan")
    if required_assembled != required_stream or all_assembled != stream:
        _fail("assignment_order", "section_plan")
    try:
        content.stream_validation(required_assembled)
        content.stream_validation(all_assembled)
    except content.ContentReject:
        _fail("invalid_content", "section_plan")

    return SliceCompilation(
        required_stream,
        _sha256(required_stream),
        base_view,
        stream,
        _sha256(stream),
        projection,
        game_payloads,
        fixture_payloads,
        assignments,
        capacity_prototypes,
        tier_roots,
        chess_cases,
        families,
    )
