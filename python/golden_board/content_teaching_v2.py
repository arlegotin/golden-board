"""Finite carried content relationships; no new receiver interpreter."""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import struct

from . import canonical_manifest, constants as K, content as C


class ContentTeachingError(ValueError):
    """Invalid source or a carried consequence disagrees with content-v0."""


@dataclass(frozen=True, slots=True)
class ContentTeachingV2:
    base_stream: bytes
    value: bytes


_BASE_SHA256 = "99c783060adb543ef1621b4e17f57772bd88c9d37cb249981aed5f9a4962d7dc"
_MUTATIONS = (
    (0, 2, 0, 1, 0), (2, 2, 29, 28, 0), (4, 2, 1, 0, 0),
    (19, 2, 2, 1, 0), (563, 2, 29, 65535, 1), (571, 2, 26, 0, 0),
    (571, 2, 26, 27, 0), (573, 2, 8, 7, 0), (573, 2, 8, 9, 1),
    (573, 2, 8, 65535, 1), (555, 2, 3, 2, 0), (555, 2, 3, 4, 0),
    (6, 2, 1, 0, 0), (167, 2, 6, 0, 0), (167, 2, 6, 12, 0),
    (167, 2, 6, 1, 0), (169, 2, 2, 0, 0), (178, 1, 5, 6, 0),
    (129, 2, 2, 1, 0), (145, 1, 1, 0, 0), (158, 1, 1, 0, 1),
    (158, 1, 1, 2, 0), (193, 2, 6, 3, 0), (223, 1, 2, 3, 1),
    (223, 1, 2, 6, 0), (191, 1, 1, 0, 0), (224, 2, 9, 1, 0),
    (302, 2, 1, 0, 0), (314, 1, 3, 6, 0), (329, 2, 16, 6, 0),
    (343, 2, 17, 1, 0), (345, 2, 10, 9, 0), (359, 2, 0, 19, 0),
    (373, 2, 19, 0, 0), (493, 2, 2, 1, 0), (456, 1, 0, 1, 0),
    (514, 1, 0, 1, 0), (544, 1, 1, 0, 1), (439, 1, 1, 2, 0),
    (443, 2, 27, 26, 0), (435, 4, 50331648, 16777217, 0),
    (561, 2, 0, 27, 0), (413, 2, 5, 1, 0), (192, 1, 0, 1, 0),
    (250, 2, 1, 3, 0), (258, 2, 2, 1, 0), (545, 2, 14, 12, 1),
    (12, 1, 83, 255, 0),
)
_ROLES = (
    (1, 3, 1, 1, 0, 0, 0, 1, 1, 3),
    (2, 3, 1, 1, 0, 0, 0, 1, 1, 3),
    (3, 3, 1, 1, 0, 0, 1, 1, 1, 3),
    (4, 3, 0, 0, 0, 0, 0, 1, 5, 3),
    (5, 1, 1, 1, 1, 4096, 1, 1, 3, 2),
    (5, 2, 0, 0, 0, 0, 0, 0, 1, 3),
)
_PRESENTATIONS = (
    (6, 14, 12, 1, 1, 1), (6, 14, 12, 2, 2, 0),
    (4, 12, 12, 1, 1, 1), (6, 14, 12, 0, 0, 0),
)
# Node, canonical actions, phase/result/shape, selected IDs, outcome/feedback/
# next, then global/local remaining. All outputs are frozen owner consequences.
_ACTIONS = (
    (26, ("03000000",), 2, 3, 1, (), 1, 21, 27, 7, 1),
    (26, ("01000002", "03000000"), 2, 3, 1, (2,), 2, 23, 26, 6, 0),
    (26, ("01000003", "03000000"), 2, 3, 1, (3,), 2, 22, 26, 6, 0),
    (27, ("01000002", "01000001", "03000000"), 2, 3, 2, (1, 2), 3, 20, 28, 4, 0),
    (28, ("01000001", "01000001", "03000000"), 2, 3, 3, (1, 1), 3, 24, 0, 3, 0),
    (28, ("01000002", "01000001", "03000000"), 2, 3, 3, (2, 1), 3, 24, 0, 3, 0),
    (26, ("01000001", "01000001"), 3, 6, 1, (1,), 0, 0, 0, 6, 0),
    (26, ("02000000", "03000000"), 2, 3, 1, (), 1, 21, 27, 6, 0),
    (26, ("01000001", "01000002"), 3, 7, 1, (1,), 0, 0, 0, 6, 0),
    (26, ("01000001", "02000000"), 3, 2, 1, (), 0, 0, 0, 6, 0),
)


def _require(condition: bool) -> None:
    if not condition:
        raise ContentTeachingError("content-teaching-source-or-consequence")


def _object(value: object, keys: set[str]) -> dict:
    _require(type(value) is dict and set(value) == keys)
    return value


def _uint(value: object, maximum: int = 0xFFFFFFFF) -> int:
    _require(type(value) is int and 0 <= value <= maximum)
    return value


def _array(value: object, maximum: int = 4096) -> list:
    _require(type(value) is list and len(value) <= maximum)
    return value


def _numbers(value: object) -> tuple[int, ...]:
    return tuple(_uint(item) for item in _array(value))


def _count(value: dict, name: str, items: tuple) -> None:
    _require(_uint(value[name]) == len(items))


def _atom_entries(raw: object) -> tuple[C.ContentAtomEntry, ...]:
    result = []
    for row in _array(raw):
        key = "code" if "code" in row else "one_hot_bit"
        row = _object(row, {key, "label_text_ref"})
        result.append(C.ContentAtomEntry(_uint(row[key]), _uint(row["label_text_ref"])))
    return tuple(result)


def _record(raw: object) -> C.ContentRecordView:
    _require(type(raw) is dict and "record_id" in raw and "kind" in raw)
    record_id, kind = _uint(raw["record_id"], 65535), raw["kind"]
    _require(type(kind) is str)
    value = {key: item for key, item in raw.items() if key not in ("kind", "record_id")}
    if kind == "TEXT":
        _object(value, {"text"})
        _require(type(value["text"]) is str)
        payload = C.ContentText(value["text"])
    elif kind == "ATOM_SCHEMA":
        atom_class = _uint(value.get("atom_class"), 3)
        common = {"atom_class", "atom_width", "entry_count"}
        if atom_class == 1:
            _object(value, common | {"min_value", "max_value"})
            _require(_uint(value["entry_count"]) == 0)
            payload = C.ContentAtomSchema(atom_class, _uint(value["atom_width"]),
                                          min_value=_uint(value["min_value"]), max_value=_uint(value["max_value"]))
        else:
            _object(value, common | {"entries"} | ({"allowed_mask"} if atom_class == 3 else set()))
            entries = _atom_entries(value["entries"])
            _count(value, "entry_count", entries)
            payload = C.ContentAtomSchema(atom_class, _uint(value["atom_width"]), entries,
                                          allowed_mask=_uint(value["allowed_mask"]) if atom_class == 3 else None)
    elif kind == "ATOM_VECTOR":
        _object(value, {"atom_schema_ref", "atom_count", "atoms"})
        atoms = _numbers(value["atoms"])
        _count(value, "atom_count", atoms)
        payload = C.ContentAtomVector(_uint(value["atom_schema_ref"]), atoms)
    elif kind == "MATRIX":
        _object(value, {"atom_schema_ref", "rows", "columns", "cells"})
        payload = C.ContentMatrix(_uint(value["atom_schema_ref"]), _uint(value["rows"]),
                                  _uint(value["columns"]), _numbers(value["cells"]))
    elif kind == "FIELD_SCHEMA":
        _object(value, {"field_count", "fields"})
        fields = []
        for field in _array(value["fields"], 256):
            _object(field, {"name_text_ref", "storage", "type", "count"})
            fields.append(C.ContentFieldSpec(*(_uint(field[k]) for k in ("name_text_ref", "storage", "type", "count"))))
        _count(value, "field_count", tuple(fields))
        payload = C.ContentFieldSchema(tuple(fields))
    elif kind == "TUPLE":
        _object(value, {"field_schema_ref", "field_values"})
        fields = []
        for field in _array(value["field_values"], 256):
            _require(type(field) is dict)
            if set(field) == {"atoms"}:
                fields.append(C.ContentAtomFieldValue(_numbers(field["atoms"])))
            else:
                _object(field, {"record_refs"})
                fields.append(C.ContentRecordRefFieldValue(_numbers(field["record_refs"])))
        payload = C.ContentTuple(_uint(value["field_schema_ref"]), tuple(fields))
    elif kind == "REGION_SET":
        _object(value, {"surface_matrix_ref", "region_count", "regions"})
        keys = ("region_id", "label_ref", "row_start", "row_end", "column_start", "column_end", "flags")
        regions = []
        for region in _array(value["regions"]):
            _object(region, set(keys))
            regions.append(C.ContentRegion(*(_uint(region[k]) for k in keys)))
        _count(value, "region_count", tuple(regions))
        payload = C.ContentRegionSet(_uint(value["surface_matrix_ref"]), tuple(regions))
    elif kind in ("SEMANTIC_BINDING", "PREDICATE_RESULT", "FEEDBACK", "ROOT"):
        cls, keys = {
            "SEMANTIC_BINDING": (C.ContentSemanticBinding, ("binding_class", "namespace_id", "semantic_code", "argument", "auxiliary")),
            "PREDICATE_RESULT": (C.ContentPredicateResult, ("predicate_binding_ref", "subject_opaque_data_ref", "result_atom_vector_ref")),
            "FEEDBACK": (C.ContentFeedback, ("feedback_code", "display_ref", "predicate_result_ref")),
            "ROOT": (C.ContentRoot, ("entry_node_ref", "global_event_budget")),
        }[kind]
        _object(value, set(keys))
        payload = cls(*(_uint(value[k]) for k in keys))
    elif kind == "OPAQUE_DATA":
        _object(value, {"data_binding_ref", "data"})
        payload = C.ContentOpaqueData(_uint(value["data_binding_ref"]), _numbers(value["data"]))
    elif kind == "PASSIVE_TRACE":
        keys = ("presentation_ref", "region_set_ref", "resulting_presentation_ref", "limitation_text_ref")
        tail = ("expected_outcome", "expected_feedback_ref", "expected_next_node_ref")
        _object(value, set(keys + tail) | {"action_count", "actions"})
        actions = []
        for action in _array(value["actions"]):
            _require(type(action) is str and len(action) == 8)
            encoded = bytes.fromhex(action)
            _require(encoded.hex() == action)
            actions.append(encoded)
        _count(value, "action_count", tuple(actions))
        payload = C.ContentPassiveTrace(*(_uint(value[k]) for k in keys), tuple(actions), *(_uint(value[k]) for k in tail))
    elif kind == "LESSON_NODE":
        prefix = ("role", "response_shape", "answer_mode", "flags", "presentation_ref", "region_set_ref", "predicate_result_ref", "passive_trace_ref", "max_selections", "item_event_budget")
        tail = ("default_feedback_ref", "default_next_node_ref")
        _object(value, set(prefix + tail) | {"case_count", "cases"})
        cases = []
        for case in _array(value["cases"]):
            _object(case, {"case_class", "selection_count", "region_ids", "feedback_ref", "next_node_ref"})
            ids = _numbers(case["region_ids"])
            _count(case, "selection_count", ids)
            cases.append(C.ContentLessonCase(_uint(case["case_class"]), ids, _uint(case["feedback_ref"]), _uint(case["next_node_ref"])))
        _count(value, "case_count", tuple(cases))
        payload = C.ContentLessonNode(*(_uint(value[k]) for k in prefix), tuple(cases), *(_uint(value[k]) for k in tail))
    else:
        raise ContentTeachingError("content-teaching-kind")
    return C.ContentRecordView(record_id, payload)


def _source(raw: bytes) -> tuple[bytes, C.ContentAuthoringProjection]:
    _require(type(raw) is bytes and 1 <= len(raw) <= 1048576)
    source = canonical_manifest.validate_canonical_manifest(raw)
    _object(source, {"bases", "cases", "recipes", "schema"})
    _require(source["schema"] == "golden-board.content-v0-fixtures/v0")
    bases = _array(source["bases"], 1)
    _require(len(bases) == 1)
    base = _object(bases[0], {"name", "projection", "stream_hex", "stream_length", "stream_sha256"})
    _require(base["name"] == "generic-base")
    logical = _object(base["projection"], {"version", "root_record_id", "records"})
    _require(_uint(logical["version"]) == 0 and _uint(logical["root_record_id"]) == 29)
    rows = _array(logical["records"], 29)
    _require(len(rows) == 29)
    authoring = C.ContentAuthoringProjection(0, tuple(_record(row) for row in rows))
    encoded = C.encode_content_v0(authoring)
    _require(len(encoded) == 575 and _uint(base["stream_length"]) == 575)
    _require(base["stream_sha256"] == _BASE_SHA256 and sha256(encoded).hexdigest() == _BASE_SHA256)
    # Comparison follows semantic construction; golden bytes never drive it.
    _require(type(base["stream_hex"]) is str and encoded.hex() == base["stream_hex"])
    return encoded, authoring


def _authoring_accepted(authoring: C.ContentAuthoringProjection) -> bool:
    try:
        C.encode_content_v0(authoring)
        return True
    except C.ContentAuthoringError:
        return False


def _role_example(role: int, mode: int, predicate: bool, trace: bool) -> C.ContentAuthoringProjection:
    """Otherwise well-typed bounded witnesses for the closed role relation."""
    packed = mode == 1
    assertion = predicate or packed
    records = [
        C.ContentRecordView(1, C.ContentText("0")),
        C.ContentRecordView(2, C.ContentAtomSchema(1, 1, min_value=0, max_value=255)),
        C.ContentRecordView(4, C.ContentMatrix(2, 1, 1, (1,))),
        C.ContentRecordView(5, C.ContentRegionSet(4, (C.ContentRegion(1, 1, 0, 1, 0, 1, 1),))),
    ]
    if assertion:
        records.extend((
            C.ContentRecordView(3, C.ContentAtomVector(2, (1,))),
            C.ContentRecordView(6, C.ContentSemanticBinding(1, 1, 1, 2, 1)),
            C.ContentRecordView(7, C.ContentOpaqueData(6, (1,))),
            C.ContentRecordView(8, C.ContentSemanticBinding(2, 1, 1, 6, 2)),
            C.ContentRecordView(9, C.ContentPredicateResult(8, 7, 3)),
        ))
    records.append(C.ContentRecordView(10, C.ContentFeedback(2 if packed else (5 if role == 4 else 1), 4, 9 if packed else 0)))
    if packed:
        records.append(C.ContentRecordView(11, C.ContentFeedback(3, 4, 9)))
    if trace:
        records.append(C.ContentRecordView(12, C.ContentPassiveTrace(4, 5, 0, 1 if role == 4 else 0,
                        (bytes.fromhex("01000001"), bytes.fromhex("03000000")), 1 if packed else 3, 10, 0)))
    cases = (C.ContentLessonCase(1, (1,), 10, 0),) if packed else ()
    records.append(C.ContentRecordView(13, C.ContentLessonNode(role, 1, mode, 0, 4, 5, 9 if predicate else 0,
                    12 if trace else 0, 1, 2, cases, 11 if packed else 10, 0)))
    records.append(C.ContentRecordView(14, C.ContentRoot(13, 2)))
    return C.ContentAuthoringProjection(0, tuple(sorted(records, key=lambda record: record.record_id)))


def _validate_roles() -> None:
    allowed = {(row[0], row[1]): row for row in _ROLES}
    for role in range(1, 6):
        for mode in range(1, 4):
            row = allowed.get((role, mode))
            if row is None:
                _require(not _authoring_accepted(_role_example(role, mode, role in (1, 2, 3) or mode == 1, mode == 1 or role == 3)))
                continue
            for predicate in (False, True):
                for trace in (False, True):
                    expected = row[2] <= predicate <= row[3] and row[6] <= trace <= row[7]
                    _require(_authoring_accepted(_role_example(role, mode, predicate, trace)) == expected)
            example = _role_example(role, mode, bool(row[2]), bool(row[6]))
            projection = C.stream_validation(C.encode_content_v0(example))
            state, _ = C.step(projection, C.new_run(projection), bytes.fromhex("03000000"))
            view = C.run_state_view(state)
            records = {record.record_id: record.payload for record in example.records}
            _require(records[view.feedback_ref].feedback_code == row[8] and view.outcome == row[9])
            _require(sum(case.case_class == K.CASE_ACCEPTED for case in records[13].cases) == row[4])
            _require(row[5] == (K.CONTENT_MAX_CASES_PER_NODE if mode == K.ANSWER_PACKED_PRACTICE else 0))


def _validate_presentations(authoring: C.ContentAuthoringProjection) -> None:
    for index, row in enumerate(_PRESENTATIONS):
        records = list(authoring.records)
        if index in (1, 3):
            schema, value = records[12].payload, records[13].payload
            if index == 1:
                schema = replace(schema, fields=schema.fields[:-1] + (replace(schema.fields[-1], count=2),))
                value = replace(value, field_values=value.field_values[:-1] + (C.ContentRecordRefFieldValue((12, 12)),))
            else:
                schema = replace(schema, fields=schema.fields[:-1])
                value = replace(value, field_values=value.field_values[:-1])
            records[12] = replace(records[12], payload=schema)
            records[13] = replace(records[13], payload=value)
        elif index == 2:
            records[27] = replace(records[27], payload=replace(records[27].payload, presentation_ref=12))
        _require(_authoring_accepted(C.ContentAuthoringProjection(0, tuple(records))) == bool(row[-1]))


def _action_rows(base: bytes) -> bytes:
    projection = C.stream_validation(base)
    encoded = bytearray()
    for node, action_hex, phase, last, shape, ids, outcome, feedback, nxt, global_left, local_left in _ACTIONS:
        state = C.new_run(projection)
        for _ in range(2):
            if C.run_state_view(state).current_node_id == node:
                break
            state, _ = C.step(projection, state, bytes.fromhex("03000000"))
            state = C.advance_committed(projection, state)
        _require(C.run_state_view(state).current_node_id == node)
        actions = tuple(bytes.fromhex(action) for action in action_hex)
        for action in actions:
            state, actual_last = C.step(projection, state, action)
        view = C.run_state_view(state)
        _require((view.phase, actual_last, view.outcome, view.feedback_ref, view.next_node_ref, view.global_remaining, view.local_remaining)
                 == (phase, last, outcome, feedback, nxt, global_left, local_left))
        if view.committed_response:
            _require(view.committed_response == bytes((shape,)) + len(ids).to_bytes(2, "big") + b"".join(i.to_bytes(2, "big") for i in ids))
        else:
            _require(view.selection_buffer == ids)
        padded_ids = ids + (0,) * (2 - len(ids))
        encoded.extend(struct.pack(">HB12sBBBBHHBHHHH", node, len(actions), b"".join(actions).ljust(12, b"\0"),
                                   phase, last, shape, len(ids), *padded_ids, outcome, feedback, nxt, global_left, local_left))
    return bytes(encoded)


def build_content_teaching_v2(fixture_source: bytes) -> ContentTeachingV2:
    """Construct from semantic source and check every frozen consequence."""
    try:
        base, authoring = _source(fixture_source)
        mutations = bytearray()
        for offset, width, old, new, expected in _MUTATIONS:
            _require(width in (1, 2, 4) and offset + width <= len(base))
            _require(int.from_bytes(base[offset:offset + width], "big") == old)
            changed = bytearray(base)
            changed[offset:offset + width] = new.to_bytes(width, "big")
            try:
                C.stream_validation(bytes(changed))
                actual = 1
            except C.ContentReject:
                actual = 0
            _require(actual == expected)
            mutations.extend(struct.pack(">HHIIH", offset, width, old, new, expected))
        _validate_roles()
        _validate_presentations(authoring)
        blocks = (
            (48, bytes(mutations)),
            (6, b"".join(struct.pack(">BBBBHHBBBB", *row) for row in _ROLES)),
            (4, b"".join(struct.pack(">6H", *row) for row in _PRESENTATIONS)),
            (10, _action_rows(base)),
        )
        supplement = b"".join(count.to_bytes(2, "big") + raw for count, raw in blocks)
        _require(len(supplement) == 1120)
        value = len(base).to_bytes(4, "big") + base + len(supplement).to_bytes(4, "big") + supplement
        _require(len(value) == 1703)
        return ContentTeachingV2(base, value)
    except ContentTeachingError:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, C.ContentAuthoringError, C.ContentReject) as error:
        raise ContentTeachingError("content-teaching-source-or-consequence") from error
