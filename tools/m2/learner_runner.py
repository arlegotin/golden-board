#!/usr/bin/env python3
"""Standalone, participant-safe runner for the frozen M2 learner stream.

This file intentionally uses only the Python standard library.  It validates
the exact learner ContentStream identity, interprets its generic content-v0
records, and emits participant-visible frames.  Evaluator predicates and
expected commitments are never exposed by this interface.
"""

from __future__ import annotations

import argparse
from bisect import bisect_left
from dataclasses import dataclass
import hashlib
import json
import os
import stat
import sys
from typing import NoReturn


CONTENT_BYTES = 13_644
CONTENT_SHA256 = "de7e22f0aa4316d9f32d9435287dd19bd6c04519aae1dc9bd816613f26929671"
CONTENT_ROOT_ID = 182
COMMAND_BYTES_MAX = 1_048_576
OUTPUT_BYTES_MAX = 1_048_576
COMMAND_COUNT_MAX = 256

KIND_TEXT = 1
KIND_ATOM_SCHEMA = 2
KIND_ATOM_VECTOR = 3
KIND_MATRIX = 4
KIND_FIELD_SCHEMA = 5
KIND_TUPLE = 6
KIND_REGION_SET = 7
KIND_SEMANTIC_BINDING = 8
KIND_OPAQUE_DATA = 9
KIND_PREDICATE_RESULT = 10
KIND_FEEDBACK = 11
KIND_PASSIVE_TRACE = 12
KIND_LESSON_NODE = 13
KIND_ROOT = 14

ATOM_UNSIGNED = 1
ATOM_ENUM = 2
ATOM_MASK = 3
FIELD_INLINE_ATOM = 1
FIELD_RECORD_REF = 2

ACTION_SELECT = 1
ACTION_RESET = 2
ACTION_COMMIT = 3
RESPONSE_SEQUENCE = 3
ANSWER_PACKED_PRACTICE = 1
CASE_ACCEPTED = 1
REGION_SELECTABLE = 1
LESSON_ALLOW_REPEATED_SELECTIONS = 1

OUTCOME_NONE = 0
OUTCOME_ACCEPTED = 1
OUTCOME_REJECTED = 2
OUTCOME_NEUTRAL = 3
PHASE_ACTIVE = 1
PHASE_COMMITTED = 2
PHASE_EXHAUSTED = 3

INTERACTION_SELECTED = 1
INTERACTION_RESET = 2
INTERACTION_COMMITTED = 3

COMMAND_SCHEMA = "golden-board.learner-runner-commands/v0"
TRANSCRIPT_SCHEMA = "golden-board.learner-runner-transcript/v0"


class RunnerError(ValueError):
    """One stable standalone-runner failure."""


@dataclass(frozen=True, slots=True)
class _Record:
    record_id: int
    kind: int
    value: object


@dataclass(slots=True)
class _State:
    current_node_id: int
    global_remaining: int
    local_remaining: int
    phase: int
    outcome: int
    selections: tuple[int, ...]
    committed_response: bytes
    feedback_ref: int
    next_node_ref: int
    events: list[tuple[int, bytes, int]]


def _fail(reason: str) -> NoReturn:
    raise RunnerError(reason)


def _u16(raw: bytes | memoryview, offset: int) -> int:
    if offset < 0 or offset + 2 > len(raw):
        _fail("truncated_content")
    return int.from_bytes(raw[offset : offset + 2], "big")


def _u32(raw: bytes | memoryview, offset: int) -> int:
    if offset < 0 or offset + 4 > len(raw):
        _fail("truncated_content")
    return int.from_bytes(raw[offset : offset + 4], "big")


def _atom(raw: memoryview, offset: int, width: int) -> int:
    if width not in (1, 2, 4) or offset < 0 or offset + width > len(raw):
        _fail("invalid_content")
    return int.from_bytes(raw[offset : offset + width], "big")


def _finish(cursor: int, raw: memoryview) -> None:
    if cursor != len(raw):
        _fail("invalid_content")


def _record(records: dict[int, _Record], record_id: int, kind: int) -> _Record:
    value = records.get(record_id)
    if value is None or value.kind != kind:
        _fail("invalid_content")
    return value


def _schema_width(records: dict[int, _Record], record_id: int) -> int:
    schema = _record(records, record_id, KIND_ATOM_SCHEMA).value
    assert isinstance(schema, dict)
    width = schema["atom_width"]
    assert isinstance(width, int)
    return width


def _parse_payload(
    record_id: int,
    kind: int,
    raw: memoryview,
    records: dict[int, _Record],
) -> object:
    if kind == KIND_TEXT:
        try:
            return bytes(raw).decode("utf-8")
        except UnicodeDecodeError as error:
            raise RunnerError("invalid_content") from error

    if kind == KIND_ATOM_SCHEMA:
        if len(raw) < 4:
            _fail("invalid_content")
        atom_class = raw[0]
        width = raw[1]
        count = _u16(raw, 2)
        if atom_class not in (ATOM_UNSIGNED, ATOM_ENUM, ATOM_MASK) or width not in (1, 2, 4):
            _fail("invalid_content")
        cursor = 4
        entries: list[tuple[int, int]] = []
        minimum = maximum = allowed_mask = None
        if atom_class == ATOM_UNSIGNED:
            minimum = _atom(raw, cursor, width)
            maximum = _atom(raw, cursor + width, width)
            cursor += 2 * width
        elif atom_class == ATOM_ENUM:
            for _ in range(count):
                entries.append((_atom(raw, cursor, width), _u16(raw, cursor + width)))
                cursor += width + 2
        else:
            allowed_mask = _atom(raw, cursor, width)
            cursor += width
            for _ in range(count):
                entries.append((_atom(raw, cursor, width), _u16(raw, cursor + width)))
                cursor += width + 2
        _finish(cursor, raw)
        return {
            "allowed_mask": allowed_mask,
            "atom_class": atom_class,
            "atom_width": width,
            "entries": tuple(entries),
            "max_value": maximum,
            "min_value": minimum,
        }

    if kind == KIND_ATOM_VECTOR:
        schema_ref = _u16(raw, 0)
        count = _u16(raw, 2)
        width = _schema_width(records, schema_ref)
        cursor = 4
        atoms = tuple(_atom(raw, cursor + index * width, width) for index in range(count))
        cursor += count * width
        _finish(cursor, raw)
        return {"atom_schema_ref": schema_ref, "atoms": atoms}

    if kind == KIND_MATRIX:
        schema_ref = _u16(raw, 0)
        rows = _u16(raw, 2)
        columns = _u16(raw, 4)
        count = rows * columns
        width = _schema_width(records, schema_ref)
        cursor = 6
        cells = tuple(_atom(raw, cursor + index * width, width) for index in range(count))
        cursor += count * width
        _finish(cursor, raw)
        return {
            "atom_schema_ref": schema_ref,
            "cells": cells,
            "columns": columns,
            "rows": rows,
        }

    if kind == KIND_FIELD_SCHEMA:
        count = _u16(raw, 0)
        cursor = 2
        fields = []
        for _ in range(count):
            fields.append(
                {
                    "count": _u16(raw, cursor + 6),
                    "name_text_ref": _u16(raw, cursor),
                    "storage": raw[cursor + 2],
                    "type_code": _u16(raw, cursor + 4),
                }
            )
            cursor += 8
        _finish(cursor, raw)
        return {"fields": tuple(fields)}

    if kind == KIND_TUPLE:
        schema_ref = _u16(raw, 0)
        schema = _record(records, schema_ref, KIND_FIELD_SCHEMA).value
        assert isinstance(schema, dict)
        cursor = 2
        values = []
        for field in schema["fields"]:
            assert isinstance(field, dict)
            count = field["count"]
            if field["storage"] == FIELD_INLINE_ATOM:
                width = _schema_width(records, field["type_code"])
                atoms = tuple(
                    _atom(raw, cursor + index * width, width) for index in range(count)
                )
                cursor += count * width
                values.append({"atoms": atoms, "record_refs": ()})
            elif field["storage"] == FIELD_RECORD_REF:
                refs = tuple(_u16(raw, cursor + index * 2) for index in range(count))
                cursor += count * 2
                values.append({"atoms": (), "record_refs": refs})
            else:
                _fail("invalid_content")
        _finish(cursor, raw)
        return {"field_schema_ref": schema_ref, "field_values": tuple(values)}

    if kind == KIND_REGION_SET:
        surface_ref = _u16(raw, 0)
        count = _u16(raw, 2)
        cursor = 4
        regions = []
        for _ in range(count):
            regions.append(
                {
                    "column_end": _u16(raw, cursor + 10),
                    "column_start": _u16(raw, cursor + 8),
                    "flags": raw[cursor + 12],
                    "label_ref": _u16(raw, cursor + 2),
                    "region_id": _u16(raw, cursor),
                    "row_end": _u16(raw, cursor + 6),
                    "row_start": _u16(raw, cursor + 4),
                }
            )
            cursor += 14
        _finish(cursor, raw)
        return {"regions": tuple(regions), "surface_matrix_ref": surface_ref}

    if kind == KIND_SEMANTIC_BINDING:
        if len(raw) != 10:
            _fail("invalid_content")
        return {
            "argument": _u16(raw, 6),
            "auxiliary": _u16(raw, 8),
            "binding_class": raw[0],
            "namespace_id": _u16(raw, 2),
            "semantic_code": _u16(raw, 4),
        }

    if kind == KIND_OPAQUE_DATA:
        binding_ref = _u16(raw, 0)
        binding = _record(records, binding_ref, KIND_SEMANTIC_BINDING).value
        assert isinstance(binding, dict)
        width = _schema_width(records, binding["argument"])
        count = binding["auxiliary"]
        cursor = 2
        data = tuple(_atom(raw, cursor + index * width, width) for index in range(count))
        cursor += count * width
        _finish(cursor, raw)
        return {"data": data, "data_binding_ref": binding_ref}

    if kind == KIND_PREDICATE_RESULT:
        if len(raw) != 6:
            _fail("invalid_content")
        return {
            "predicate_binding_ref": _u16(raw, 0),
            "result_atom_vector_ref": _u16(raw, 4),
            "subject_opaque_data_ref": _u16(raw, 2),
        }

    if kind == KIND_FEEDBACK:
        if len(raw) != 6:
            _fail("invalid_content")
        return {
            "display_ref": _u16(raw, 2),
            "feedback_code": _u16(raw, 0),
            "predicate_result_ref": _u16(raw, 4),
        }

    if kind == KIND_PASSIVE_TRACE:
        count = _u16(raw, 8)
        cursor = 10
        actions = tuple(bytes(raw[cursor + index * 4 : cursor + index * 4 + 4]) for index in range(count))
        cursor += count * 4
        if cursor + 6 != len(raw):
            _fail("invalid_content")
        return {
            "actions": actions,
            "expected_feedback_ref": _u16(raw, cursor + 2),
            "expected_next_node_ref": _u16(raw, cursor + 4),
            "expected_outcome": raw[cursor],
            "limitation_text_ref": _u16(raw, 6),
            "presentation_ref": _u16(raw, 0),
            "region_set_ref": _u16(raw, 2),
            "resulting_presentation_ref": _u16(raw, 4),
        }

    if kind == KIND_LESSON_NODE:
        if len(raw) < 22:
            _fail("invalid_content")
        count = _u16(raw, 16)
        cursor = 18
        cases = []
        for _ in range(count):
            selection_count = _u16(raw, cursor + 2)
            ids = tuple(_u16(raw, cursor + 4 + index * 2) for index in range(selection_count))
            tail = cursor + 4 + 2 * selection_count
            cases.append(
                {
                    "case_class": raw[cursor],
                    "feedback_ref": _u16(raw, tail),
                    "next_node_ref": _u16(raw, tail + 2),
                    "region_ids": ids,
                }
            )
            cursor = tail + 4
        if cursor + 4 != len(raw):
            _fail("invalid_content")
        return {
            "answer_mode": raw[2],
            "cases": tuple(cases),
            "default_feedback_ref": _u16(raw, cursor),
            "default_next_node_ref": _u16(raw, cursor + 2),
            "flags": raw[3],
            "item_event_budget": _u16(raw, 14),
            "max_selections": _u16(raw, 12),
            "passive_trace_ref": _u16(raw, 10),
            "predicate_result_ref": _u16(raw, 8),
            "presentation_ref": _u16(raw, 4),
            "region_set_ref": _u16(raw, 6),
            "response_shape": raw[1],
            "role": raw[0],
        }

    if kind == KIND_ROOT:
        if len(raw) != 4:
            _fail("invalid_content")
        return {"entry_node_ref": _u16(raw, 0), "global_event_budget": _u16(raw, 2)}

    _fail("invalid_content")


def _parse_content(raw: bytes) -> dict[int, _Record]:
    if len(raw) != CONTENT_BYTES or hashlib.sha256(raw).hexdigest() != CONTENT_SHA256:
        _fail("content_stream_identity")
    if _u16(raw, 0) != 0:
        _fail("invalid_content")
    count = _u16(raw, 2)
    cursor = 4
    records: dict[int, _Record] = {}
    previous = 0
    for _ in range(count):
        record_id = _u16(raw, cursor)
        kind = _u16(raw, cursor + 2)
        length = _u32(raw, cursor + 4)
        start = cursor + 8
        end = start + length
        if record_id <= previous or end > len(raw) or kind not in range(1, 15):
            _fail("invalid_content")
        value = _parse_payload(record_id, kind, memoryview(raw)[start:end], records)
        records[record_id] = _Record(record_id, kind, value)
        previous = record_id
        cursor = end
    if cursor != len(raw) or previous != CONTENT_ROOT_ID:
        _fail("invalid_content")
    root = _record(records, CONTENT_ROOT_ID, KIND_ROOT).value
    assert isinstance(root, dict)
    _record(records, root["entry_node_ref"], KIND_LESSON_NODE)
    return records


class StandaloneRunner:
    """Bounded participant-visible interpreter for one exact learner stream."""

    __slots__ = ("_records", "_state", "_suppressed")

    def __init__(self, raw_content: bytes, *, label_suppressed: bool):
        if type(raw_content) is not bytes or type(label_suppressed) is not bool:
            raise TypeError("invalid runner input")
        self._records = _parse_content(raw_content)
        root = _record(self._records, CONTENT_ROOT_ID, KIND_ROOT).value
        assert isinstance(root, dict)
        node_id = root["entry_node_ref"]
        node = self._node(node_id)
        self._state = _State(
            node_id,
            root["global_event_budget"],
            node["item_event_budget"],
            PHASE_ACTIVE,
            OUTCOME_NONE,
            (),
            b"",
            0,
            0,
            [],
        )
        self._suppressed = label_suppressed

    def _node(self, record_id: int) -> dict[str, object]:
        value = _record(self._records, record_id, KIND_LESSON_NODE).value
        assert isinstance(value, dict)
        return value

    def _label(self, record_id: int) -> str | None:
        if record_id == 0 or self._suppressed:
            return None
        value = _record(self._records, record_id, KIND_TEXT).value
        assert isinstance(value, str)
        return value

    def _atom_schema_value(self, record_id: int) -> dict[str, object]:
        value = _record(self._records, record_id, KIND_ATOM_SCHEMA).value
        assert isinstance(value, dict)
        return {
            "allowed_mask": value["allowed_mask"],
            "atom_class": value["atom_class"],
            "atom_width": value["atom_width"],
            "entries": [
                {"label": self._label(label_ref), "value": code}
                for code, label_ref in value["entries"]
            ],
            "max_value": value["max_value"],
            "min_value": value["min_value"],
        }

    def _display_record(self, record_id: int) -> tuple[dict[str, object], tuple[int, ...]]:
        record = self._records.get(record_id)
        if record is None:
            _fail("invalid_content")
        value = record.value
        output: dict[str, object] = {
            "atom_schema": None,
            "atoms": [],
            "columns": 0,
            "fields": [],
            "kind": record.kind,
            "opaque_data": [],
            "record_id": record_id,
            "rows": 0,
            "text": None,
        }
        references: list[int] = []
        if record.kind == KIND_TEXT:
            assert isinstance(value, str)
            output["text"] = None if self._suppressed else value
        elif record.kind == KIND_ATOM_VECTOR:
            assert isinstance(value, dict)
            output["atom_schema"] = self._atom_schema_value(value["atom_schema_ref"])
            output["atoms"] = list(value["atoms"])
        elif record.kind == KIND_MATRIX:
            assert isinstance(value, dict)
            output["atom_schema"] = self._atom_schema_value(value["atom_schema_ref"])
            output["atoms"] = list(value["cells"])
            output["columns"] = value["columns"]
            output["rows"] = value["rows"]
        elif record.kind == KIND_TUPLE:
            assert isinstance(value, dict)
            schema = _record(self._records, value["field_schema_ref"], KIND_FIELD_SCHEMA).value
            assert isinstance(schema, dict)
            fields = []
            for definition, field_value in zip(schema["fields"], value["field_values"], strict=True):
                refs = field_value["record_refs"]
                references.extend(refs)
                fields.append(
                    {
                        "atoms": list(field_value["atoms"]),
                        "count": definition["count"],
                        "name": self._label(definition["name_text_ref"]),
                        "record_refs": list(refs),
                        "storage": definition["storage"],
                        "type_code": definition["type_code"],
                    }
                )
            output["fields"] = fields
        elif record.kind == KIND_OPAQUE_DATA:
            assert isinstance(value, dict)
            output["opaque_data"] = list(value["data"])
        else:
            _fail("unsupported_display_kind")
        return output, tuple(references)

    def _display_graph(self, root_id: int) -> dict[str, object]:
        pending = [root_id]
        emitted: dict[int, dict[str, object]] = {}
        while pending:
            record_id = pending.pop()
            if record_id in emitted:
                continue
            if len(emitted) >= len(self._records):
                _fail("invalid_content")
            display, references = self._display_record(record_id)
            emitted[record_id] = display
            pending.extend(reversed(references))
        return {
            "records": [emitted[record_id] for record_id in sorted(emitted)],
            "root_record_id": root_id,
        }

    def _regions(self, region_set_ref: int) -> list[dict[str, object]]:
        value = _record(self._records, region_set_ref, KIND_REGION_SET).value
        assert isinstance(value, dict)
        return [
            {
                "column_end": region["column_end"],
                "column_start": region["column_start"],
                "flags": region["flags"],
                "label": self._label(region["label_ref"]),
                "region_id": region["region_id"],
                "row_end": region["row_end"],
                "row_start": region["row_start"],
            }
            for region in value["regions"]
        ]

    def _available_actions(self) -> tuple[bytes, ...]:
        if self._state.phase != PHASE_ACTIVE:
            return ()
        node = self._node(self._state.current_node_id)
        regions = self._regions(node["region_set_ref"])
        repeated = bool(
            node["response_shape"] == RESPONSE_SEQUENCE
            and node["flags"] & LESSON_ALLOW_REPEATED_SELECTIONS
        )
        output = []
        if len(self._state.selections) < node["max_selections"]:
            for region in regions:
                region_id = region["region_id"]
                if not region["flags"] & REGION_SELECTABLE:
                    continue
                if region_id in self._state.selections and not repeated:
                    continue
                output.append(bytes((ACTION_SELECT, 0, *region_id.to_bytes(2, "big"))))
        output.extend((bytes((ACTION_RESET, 0, 0, 0)), bytes((ACTION_COMMIT, 0, 0, 0))))
        return tuple(output)

    def frame(self) -> dict[str, object]:
        state = self._state
        node = self._node(state.current_node_id)
        feedback = None
        if state.feedback_ref:
            value = _record(self._records, state.feedback_ref, KIND_FEEDBACK).value
            assert isinstance(value, dict)
            feedback = self._display_graph(value["display_ref"])
        passive = None
        if node["passive_trace_ref"]:
            value = _record(self._records, node["passive_trace_ref"], KIND_PASSIVE_TRACE).value
            assert isinstance(value, dict)
            passive = {
                "actions_hex": [action.hex() for action in value["actions"]],
                "limitation": self._label(value["limitation_text_ref"]),
                "presentation": self._display_graph(value["presentation_ref"]),
                "regions": self._regions(value["region_set_ref"]),
                "resulting_presentation": (
                    None
                    if value["resulting_presentation_ref"] == 0
                    else self._display_graph(value["resulting_presentation_ref"])
                ),
            }
        actions = self._available_actions()
        return {
            "available_actions_hex": [action.hex() for action in actions],
            "can_advance": state.phase == PHASE_COMMITTED and state.next_node_ref != 0,
            "committed_response_hex": state.committed_response.hex(),
            "current_node_id": state.current_node_id,
            "events": [
                {"action_hex": action.hex(), "node_id": node_id, "result": result}
                for node_id, action, result in state.events
            ],
            "feedback": feedback,
            "feedback_ref": state.feedback_ref,
            "global_remaining": state.global_remaining,
            "local_remaining": state.local_remaining,
            "next_node_ref": state.next_node_ref,
            "outcome": state.outcome,
            "passive": passive,
            "phase": state.phase,
            "presentation": self._display_graph(node["presentation_ref"]),
            "regions": self._regions(node["region_set_ref"]),
            "selection_buffer": list(state.selections),
        }

    def perform(self, action: bytes) -> int:
        if type(action) is not bytes:
            raise TypeError("action must be bytes")
        if action not in self._available_actions():
            _fail("action_not_available")
        state = self._state
        node = self._node(state.current_node_id)
        global_remaining = state.global_remaining - 1
        local_remaining = state.local_remaining - 1
        selections = state.selections
        response = b""
        outcome = OUTCOME_NONE
        feedback_ref = 0
        next_node_ref = 0
        tag = action[0]
        if tag == ACTION_SELECT:
            region_id = int.from_bytes(action[2:4], "big")
            if node["response_shape"] == RESPONSE_SEQUENCE:
                selections = (*selections, region_id)
            else:
                at = bisect_left(selections, region_id)
                selections = (*selections[:at], region_id, *selections[at:])
            result = INTERACTION_SELECTED
        elif tag == ACTION_RESET:
            selections = ()
            result = INTERACTION_RESET
        else:
            response = bytes((node["response_shape"], *len(selections).to_bytes(2, "big"))) + b"".join(
                value.to_bytes(2, "big") for value in selections
            )
            selected = next(
                (case for case in node["cases"] if case["region_ids"] == selections),
                None,
            )
            if selected is None:
                feedback_ref = node["default_feedback_ref"]
                next_node_ref = node["default_next_node_ref"]
                outcome = (
                    OUTCOME_REJECTED
                    if node["answer_mode"] == ANSWER_PACKED_PRACTICE
                    else OUTCOME_NEUTRAL
                )
            else:
                feedback_ref = selected["feedback_ref"]
                next_node_ref = selected["next_node_ref"]
                outcome = OUTCOME_ACCEPTED if selected["case_class"] == CASE_ACCEPTED else OUTCOME_REJECTED
            selections = ()
            result = INTERACTION_COMMITTED
        state.events.append((state.current_node_id, action, result))
        phase = PHASE_COMMITTED if tag == ACTION_COMMIT else PHASE_ACTIVE
        if tag != ACTION_COMMIT and (global_remaining == 0 or local_remaining == 0):
            phase = PHASE_EXHAUSTED
        state.global_remaining = global_remaining
        state.local_remaining = local_remaining
        state.phase = phase
        state.outcome = outcome
        state.selections = selections
        state.committed_response = response
        state.feedback_ref = feedback_ref
        state.next_node_ref = next_node_ref
        return result

    def advance(self) -> None:
        state = self._state
        if state.phase != PHASE_COMMITTED or state.next_node_ref == 0:
            _fail("advance_not_available")
        target = self._node(state.next_node_ref)
        exhausted = state.global_remaining == 0
        state.current_node_id = state.next_node_ref
        state.local_remaining = 0 if exhausted else min(target["item_event_budget"], state.global_remaining)
        state.phase = PHASE_EXHAUSTED if exhausted else PHASE_ACTIVE
        state.outcome = OUTCOME_NONE
        state.selections = ()
        state.committed_response = b""
        state.feedback_ref = 0
        state.next_node_ref = 0


def _read_regular(path: str, maximum: int) -> bytes:
    try:
        info = os.lstat(path)
    except OSError as error:
        raise RunnerError("input_file") from error
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > maximum:
        _fail("input_file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if (
                opened.st_dev != info.st_dev
                or opened.st_ino != info.st_ino
                or opened.st_size != info.st_size
                or not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
            ):
                _fail("input_file")
            chunks = []
            remaining = maximum + 1
            while remaining:
                chunk = os.read(descriptor, min(65_536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            if len(raw) > maximum or os.read(descriptor, 1):
                _fail("input_file")
        finally:
            os.close(descriptor)
    except OSError as error:
        raise RunnerError("input_file") from error
    if len(raw) != info.st_size:
        _fail("input_file")
    return raw


def _commands(raw: bytes) -> tuple[dict[str, object], ...]:
    if type(raw) is not bytes:
        raise TypeError("commands must be bytes")

    def object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        output = {}
        for key, value in pairs:
            if key in output:
                _fail("commands")
            output[key] = value
        return output

    try:
        value = json.loads(raw, object_pairs_hook=object_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RunnerError("commands") from error
    if type(value) is not dict or set(value) != {"commands", "schema"} or value["schema"] != COMMAND_SCHEMA:
        _fail("commands")
    rows = value["commands"]
    if type(rows) is not list or len(rows) > COMMAND_COUNT_MAX:
        _fail("commands")
    output = []
    for row in rows:
        if type(row) is not dict:
            _fail("commands")
        if set(row) == {"action_hex"}:
            encoded = row["action_hex"]
            if type(encoded) is not str or len(encoded) != 8 or any(character not in "0123456789abcdef" for character in encoded):
                _fail("commands")
        elif set(row) == {"advance"}:
            if row["advance"] is not True:
                _fail("commands")
        else:
            _fail("commands")
        output.append(row)
    return tuple(output)


def run_commands(raw_content: bytes, commands_raw: bytes, *, label_suppressed: bool) -> bytes:
    runner = StandaloneRunner(raw_content, label_suppressed=label_suppressed)
    frames = [runner.frame()]
    results: list[int | str] = []
    for command in _commands(commands_raw):
        if "action_hex" in command:
            result = runner.perform(bytes.fromhex(command["action_hex"]))
            results.append(result)
        else:
            runner.advance()
            results.append("advanced")
        frames.append(runner.frame())
    value = {
        "content_stream_sha256": CONTENT_SHA256,
        "frames": frames,
        "results": results,
        "schema": TRANSCRIPT_SCHEMA,
    }
    raw = (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
    if len(raw) > OUTPUT_BYTES_MAX:
        _fail("output_limit")
    return raw


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="m2-learner-runner", allow_abbrev=False)
    parser.add_argument("--content-stream", required=True)
    parser.add_argument("--commands", required=True)
    parser.add_argument("--label-suppressed", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = _parser().parse_args(argv)
        content = _read_regular(arguments.content_stream, CONTENT_BYTES)
        commands = _read_regular(arguments.commands, COMMAND_BYTES_MAX)
        output = run_commands(content, commands, label_suppressed=arguments.label_suppressed)
    except RunnerError as error:
        print(f"m2-learner-runner: {error}", file=sys.stderr)
        return 3
    sys.stdout.buffer.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
