from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest import mock

try:
    from golden_board import canonical_manifest, identity
except ImportError:
    canonical_manifest = None
    identity = None

try:
    from golden_board import source_doctor
except ImportError:
    source_doctor = None


ROOT = Path(__file__).resolve().parents[2]
IDENTITY_FIXTURE = ROOT / "conformance" / "identity-v0.json"
MANIFEST_FIXTURE = ROOT / "conformance" / "manifest-v0.json"
CHESS_FIXTURE = ROOT / "conformance" / "chess-v0.json"
SOURCE_FIXTURE = ROOT / "conformance" / "source-v0.json"
CONTENT_FIXTURE = ROOT / "conformance" / "content-v0.json"
MAX_REPO_TEXT_BYTES = 1_048_576
M0_IDENTITY_VECTORS_SHA256 = (
    "19b90c4ab863ca3853a1b8229b8ae84a886e4a8cf0c3bee496157e592bf000ae"
)
M1_IDENTITY_VECTORS = [
    {
        "domain_hex": "676f6c64656e2d626f6172643a706f736974696f6e3a763000",
        "fields_hex": [
            "0402030506030204010101010101010100000000000000000000000000000000"
            "0000000000000000000000000000000007070707070707070a08090b0c09080a"
            "000f00"
        ],
        "identity": "7d578698cdb2095a1b818234f12b3e6d4f19bbadb414887f26e6a8d52417a186",
        "name": "initial-position",
        "preimage_hex": (
            "676f6c64656e2d626f6172643a706f736974696f6e3a763000000100000043"
            "0402030506030204010101010101010100000000000000000000000000000000"
            "0000000000000000000000000000000007070707070707070a08090b0c09080a"
            "000f00"
        ),
    },
    {
        "domain_hex": (
            "676f6c64656e2d626f6172643a72657065746974696f6e2d6b65793a763000"
        ),
        "fields_hex": [
            "0402030506030204010101010101010100000000000000000000000000000000"
            "0000000000000000000000000000000007070707070707070a08090b0c09080a"
            "000f00"
        ],
        "identity": "b12da42c15cc340394688be5d771ad8936241e9dcb03592b2791e06b9dbe33e3",
        "name": "initial-repetition-key",
        "preimage_hex": (
            "676f6c64656e2d626f6172643a72657065746974696f6e2d6b65793a763000"
            "000100000043"
            "0402030506030204010101010101010100000000000000000000000000000000"
            "0000000000000000000000000000000007070707070707070a08090b0c09080a"
            "000f00"
        ),
    },
    {
        "domain_hex": "676f6c64656e2d626f6172643a67616d653a763000",
        "fields_hex": ["00043550d24039e0edf001"],
        "identity": "c49a921d652aa82b69a320073ca7ca0f5f3adf3d4ccc80d5aea162a52925b3bb",
        "name": "fools-mate-game",
        "preimage_hex": (
            "676f6c64656e2d626f6172643a67616d653a76300000010000000b"
            "00043550d24039e0edf001"
        ),
    },
    {
        "domain_hex": "676f6c64656e2d626f6172643a67616d652d7365743a763000",
        "fields_hex": ["000100043550d24039e0edf001"],
        "identity": "4070001b03556dcf41043adcf7a261c4b20aa7874a8033546520a48107fbc2f8",
        "name": "fools-mate-game-set",
        "preimage_hex": (
            "676f6c64656e2d626f6172643a67616d652d7365743a76300000010000000d"
            "000100043550d24039e0edf001"
        ),
    },
]


def repo_text_bytes(root: Path, relative: bytes) -> bytes:
    components = relative.split(b"/")
    if (
        not relative
        or b"\0" in relative
        or relative.startswith(b"/")
        or any(component in {b"", b".", b".."} for component in components)
        or not hasattr(os, "O_NOFOLLOW")
    ):
        raise AssertionError(f"unsafe repository text path: {relative!r}")

    directory_fd = None
    file_fd = None
    try:
        directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        for component in components[:-1]:
            metadata = os.stat(component, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise AssertionError(f"unsafe repository text path: {relative!r}")
            next_fd = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
            os.close(directory_fd)
            directory_fd = next_fd

        metadata = os.stat(components[-1], dir_fd=directory_fd, follow_symlinks=False)
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > MAX_REPO_TEXT_BYTES
        ):
            raise AssertionError(f"unsafe repository text path: {relative!r}")
        file_fd = os.open(
            components[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd
        )
        metadata = os.fstat(file_fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_REPO_TEXT_BYTES:
            raise AssertionError(f"unsafe repository text path: {relative!r}")

        data = bytearray()
        while len(data) <= MAX_REPO_TEXT_BYTES:
            chunk = os.read(file_fd, min(65_536, MAX_REPO_TEXT_BYTES + 1 - len(data)))
            if not chunk:
                return bytes(data)
            data.extend(chunk)
        raise AssertionError(f"unsafe repository text path: {relative!r}")
    except OSError as error:
        raise AssertionError(f"unsafe repository text path: {relative!r}") from error
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if directory_fd is not None:
            os.close(directory_fd)


def validate_conformance_registry(root: Path) -> None:
    try:
        registry = tomllib.loads(
            repo_text_bytes(root, b"conformance/registry.toml").decode("utf-8")
        )
    except (AssertionError, OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise AssertionError("invalid conformance registry") from error
    if set(registry) != {"schema", "suite"} or registry["schema"] != (
        "golden-board.conformance-registry/v0"
    ):
        raise AssertionError("invalid conformance registry")
    suites = registry["suite"]
    if not isinstance(suites, list):
        raise AssertionError("invalid conformance registry")

    row_keys = {
        "id",
        "path",
        "specification",
        "version",
        "sha256",
        "consumers",
        "provenance",
    }
    identifiers = set()
    paths = set()
    for suite in suites:
        if not isinstance(suite, dict) or set(suite) != row_keys:
            raise AssertionError("invalid conformance registry")
        identifier = suite["id"]
        specification = suite["specification"]
        if any(
            not isinstance(value, str)
            or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value) is None
            for value in (identifier, specification)
        ):
            raise AssertionError("invalid conformance registry")
        path = suite["path"]
        if (
            not isinstance(path, str)
            or path != f"conformance/{identifier}.json"
            or identifier in identifiers
            or path in paths
            or suite["version"] != "v0"
            or not isinstance(suite["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", suite["sha256"]) is None
            or suite["consumers"] != ["python", "rust"]
            or suite["provenance"] != "hand-authored"
        ):
            raise AssertionError("invalid conformance registry")
        identifiers.add(identifier)
        paths.add(path)
        payload = repo_text_bytes(root, path.encode("ascii"))
        if hashlib.sha256(payload).hexdigest() != suite["sha256"]:
            raise AssertionError("invalid conformance registry")

    try:
        inventory = set()
        with os.scandir(root / "conformance") as entries:
            for entry in entries:
                if entry.name == "registry.toml":
                    continue
                metadata = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                    raise AssertionError("invalid conformance registry")
                inventory.add(f"conformance/{entry.name}")
                if len(inventory) > len(paths):
                    raise AssertionError("invalid conformance registry")
    except OSError as error:
        raise AssertionError("invalid conformance registry") from error
    if inventory != paths:
        raise AssertionError("invalid conformance registry")


def _content_u16(value: int) -> bytes:
    return value.to_bytes(2, "big")


def _content_u32(value: int) -> bytes:
    return value.to_bytes(4, "big")


_CONTENT_KINDS = {
    "TEXT": 1,
    "ATOM_SCHEMA": 2,
    "ATOM_VECTOR": 3,
    "MATRIX": 4,
    "FIELD_SCHEMA": 5,
    "TUPLE": 6,
    "REGION_SET": 7,
    "SEMANTIC_BINDING": 8,
    "OPAQUE_DATA": 9,
    "PREDICATE_RESULT": 10,
    "FEEDBACK": 11,
    "PASSIVE_TRACE": 12,
    "LESSON_NODE": 13,
    "ROOT": 14,
}


def _content_record(record_id: int, kind: str, payload: bytes) -> bytes:
    return (
        _content_u16(record_id)
        + _content_u16(_CONTENT_KINDS[kind])
        + _content_u32(len(payload))
        + payload
    )


def _content_stream(records: list[bytes]) -> bytes:
    return b"\0\0" + _content_u16(len(records)) + b"".join(records)


def _content_schema(record_id: int) -> bytes:
    return _content_record(record_id, "ATOM_SCHEMA", b"\x01\x01\0\0\0\0")


def _content_vector(record_id: int, schema: int, values: list[int]) -> bytes:
    return _content_record(
        record_id,
        "ATOM_VECTOR",
        _content_u16(schema) + _content_u16(len(values)) + bytes(values),
    )


def _content_matrix(
    record_id: int, schema: int, rows: int, columns: int, values: list[int]
) -> bytes:
    return _content_record(
        record_id,
        "MATRIX",
        _content_u16(schema)
        + _content_u16(rows)
        + _content_u16(columns)
        + bytes(values),
    )


def _content_feedback(record_id: int, code: int, display: int, predicate: int) -> bytes:
    return _content_record(
        record_id,
        "FEEDBACK",
        _content_u16(code) + _content_u16(display) + _content_u16(predicate),
    )


def _content_wrong_root(records: list[bytes], root_id: int, entry: int) -> bytes:
    return _content_stream(
        [*records, _content_record(root_id, "ROOT", _content_u16(entry) + b"\0\x01")]
    )


def _content_support_stream() -> bytes:
    records = [
        _content_record(1, "TEXT", b"cell"),
        _content_schema(2),
        _content_matrix(3, 2, 64, 64, [0] * 4096),
    ]
    regions = _content_u16(3) + _content_u16(4096)
    for index in range(4096):
        row, column = divmod(index, 64)
        regions += (
            _content_u16(index + 1)
            + _content_u16(1)
            + _content_u16(row)
            + _content_u16(row + 1)
            + _content_u16(column)
            + _content_u16(column + 1)
            + b"\x01\0"
        )
    records.extend(
        [
            _content_record(4, "REGION_SET", regions),
            _content_record(
                5,
                "SEMANTIC_BINDING",
                b"\x01\0" + _content_u16(1) + _content_u16(1)
                + _content_u16(2) + _content_u16(1),
            ),
            _content_record(6, "OPAQUE_DATA", _content_u16(5) + b"\0"),
            _content_vector(7, 2, [0]),
            _content_record(
                8,
                "SEMANTIC_BINDING",
                b"\x02\0" + _content_u16(1) + _content_u16(2)
                + _content_u16(5) + _content_u16(2),
            ),
            _content_record(
                9,
                "PREDICATE_RESULT",
                _content_u16(8) + _content_u16(6) + _content_u16(7),
            ),
            _content_feedback(10, 2, 1, 9),
            _content_feedback(11, 3, 1, 9),
        ]
    )
    actions = b"".join(
        b"\x01\0" + _content_u16(index) for index in range(1, 4097)
    ) + b"\x03\0\0\0"
    records.append(
        _content_record(
            12,
            "PASSIVE_TRACE",
            _content_u16(3) + _content_u16(4) + b"\0\0\0\0"
            + _content_u16(4097) + actions + b"\x01\0"
            + _content_u16(10) + b"\0\0",
        )
    )
    selected = b"".join(_content_u16(index) for index in range(1, 4097))
    case = b"\x01\0" + _content_u16(4096) + selected + _content_u16(10) + b"\0\0"
    node = (
        bytes((5, 2, 1, 0)) + _content_u16(3) + _content_u16(4)
        + _content_u16(9) + _content_u16(12) + _content_u16(4096)
        + _content_u16(65535) + _content_u16(1) + case
        + _content_u16(11) + _content_u16(13)
    )
    records.extend(
        [
            _content_record(13, "LESSON_NODE", node),
            _content_record(14, "ROOT", _content_u16(13) + _content_u16(65535)),
        ]
    )
    return _content_stream(records)


def _content_max_states() -> tuple[bytes, bytes]:
    def event(action: bytes, result: int) -> bytes:
        return _content_u16(13) + action + bytes((result,))

    sentinel = event(b"\0" * 4, 4)
    selections = b"".join(
        event(b"\x01\0" + _content_u16(index), 1) for index in range(1, 4097)
    )
    response = b"\x02" + _content_u16(4096) + b"".join(
        _content_u16(index) for index in range(1, 4097)
    )
    committed = (
        _content_u16(0) + _content_u16(14) + _content_u16(13) + b"\0\0\0\0"
        + b"\x02\x01\0\0" + _content_u16(len(response)) + response
        + _content_u16(65535) + sentinel * 61438 + selections
        + event(b"\x03\0\0\0", 3)
    )
    exhausted = (
        _content_u16(0) + _content_u16(14) + _content_u16(13) + b"\0\0\0\0"
        + b"\x03\0" + _content_u16(4096)
        + b"".join(_content_u16(index) for index in range(1, 4097))
        + b"\0\0" + _content_u16(65535) + selections + sentinel * 61439
    )
    return committed, exhausted


def _content_control_stream(extra: bool) -> bytes:
    records = [
        _content_record(1, "TEXT", b"cell"),
        _content_schema(2),
        _content_matrix(3, 2, 1, 3, [0, 0, 0]),
    ]
    regions = _content_u16(3) + _content_u16(3)
    for index in range(3):
        regions += (
            _content_u16(index + 1) + _content_u16(1) + b"\0\0\0\x01"
            + _content_u16(index) + _content_u16(index + 1) + b"\x01\0"
        )
    records.extend(
        [
            _content_record(4, "REGION_SET", regions),
            _content_record(
                5,
                "SEMANTIC_BINDING",
                b"\x01\0" + _content_u16(1) + _content_u16(1)
                + _content_u16(2) + _content_u16(1),
            ),
            _content_record(6, "OPAQUE_DATA", _content_u16(5) + b"\0"),
            _content_vector(7, 2, [0]),
            _content_record(
                8,
                "SEMANTIC_BINDING",
                b"\x02\0" + _content_u16(1) + _content_u16(2)
                + _content_u16(5) + _content_u16(2),
            ),
            _content_record(
                9,
                "PREDICATE_RESULT",
                _content_u16(8) + _content_u16(6) + _content_u16(7),
            ),
            _content_feedback(10, 2, 1, 9),
            _content_feedback(11, 3, 1, 9),
            _content_feedback(12, 4, 1, 9),
        ]
    )
    first_node = 4109
    for index in range(4096):
        next_node = first_node + index + 1 if index < 4095 else 0
        payload = (
            _content_u16(3) + _content_u16(4) + b"\0\0\0\0"
            + _content_u16(1) + b"\x03\0\0\0\x01\0"
            + _content_u16(10) + _content_u16(next_node)
        )
        records.append(_content_record(13 + index, "PASSIVE_TRACE", payload))
    for index in range(4096):
        node_id = first_node + index
        success = node_id + 1 if index < 4095 else 0
        alternatives = [[1], [2]]
        if index == 4095:
            alternatives.extend([[3], [1, 1]] if extra else [[3]])
        cases = [(1, [], 10, success), *(
            (2, region_ids, 12, node_id) for region_ids in alternatives
        )]
        payload = (
            bytes((5, 3, 1, 1)) + _content_u16(3) + _content_u16(4)
            + _content_u16(9) + _content_u16(13 + index)
            + _content_u16(2) + _content_u16(3) + _content_u16(len(cases))
        )
        for case_class, region_ids, feedback, target in cases:
            payload += (
                bytes((case_class, 0)) + _content_u16(len(region_ids))
                + b"".join(_content_u16(value) for value in region_ids)
                + _content_u16(feedback) + _content_u16(target)
            )
        records.append(
            _content_record(
                node_id,
                "LESSON_NODE",
                payload + _content_u16(11) + _content_u16(node_id),
            )
        )
    records.append(
        _content_record(
            first_node + 4096,
            "ROOT",
            _content_u16(first_node) + _content_u16(12287),
        )
    )
    return _content_stream(records)


_CONTENT_RECIPE_INPUT_KEYS = {
    "patch-base": ({"base", "patches"},),
    "stream-byte-cap": ({"byte_count"},),
    "maximum-support-stream": ({
        "accepted_selection_count", "event_budget", "matrix_columns",
        "matrix_rows", "record_count", "region_count", "selection_cap",
    },),
    "maximum-selection-cap-over": ({"base_stream_sha256", "selection_cap"},),
    "maximum-committed-state": ({
        "event_count", "invalid_action_count", "selection_count",
        "support_stream_sha256",
    },),
    "maximum-exhausted-state": ({
        "event_count", "invalid_action_count", "selection_count",
        "support_stream_sha256",
    },),
    "maximum-state-byte-over": ({"append_hex", "base_state"},),
    "typed-step-sequence": ({
        "first_4096", "last", "next_61439", "operation_count",
        "support_stream_sha256",
    },),
    "stream-bytes-boundary": ({"boundary", "byte_count"},),
    "record-count-boundary": ({"boundary", "record_count"},),
    "record-id-boundary": ({"boundary", "record_id"},),
    "text-bytes-boundary": (
        {"boundary", "text_bytes"},
        {"boundary", "declared_text_bytes"},
    ),
    "per-kind-records-boundary": ({"boundary", "text_record_count"},),
    "enum-entries-boundary": ({"boundary", "entry_count"},),
    "vector-atoms-boundary": ({"atom_count", "boundary"},),
    "matrix-cells-boundary": ({"boundary", "cell_count", "columns", "rows"},),
    "field-schema-fields-boundary": ({"boundary", "field_count"},),
    "tuple-slots-boundary": ({"boundary", "slot_count"},),
    "opaque-atoms-boundary": ({"atom_count", "boundary"},),
    "regions-boundary": ({"boundary", "region_count"},),
    "lesson-nodes-boundary": ({"boundary", "lesson_node_count"},),
    "cases-per-node-boundary": ({"boundary", "case_count"},),
    "record-payload-bytes-boundary": ({"boundary", "declared_payload_bytes"},),
    "control-edge-boundary": ({"control_edges", "lesson_nodes"},),
}

_CONTENT_DIRECT_NAMES = {
    "stream_validation": frozenset("""
        passive-region-set-owner-mismatch stream-bad-record-count-zero
        stream-bad-version stream-empty-truncated stream-partial-header-truncated
        stream-trailing-data stream-truncated-final-payload
        stream-truncated-record-header stream-valid-generic-base
    """.split()),
    "new_run": frozenset("new-run-exact".split()),
    "step": frozenset("""
        step-caller-zero-action-is-sentinel step-committed-is-immutable
        step-default-rejected-commit step-duplicate-before-over-limit
        step-empty-accepted-commit-passive-trace step-exhausted-is-immutable
        step-external-neutral-commit step-heuristic-neutral-terminal-commit
        step-malformed-action-normalizes-sentinel step-over-limit
        step-reset-final-local-event step-select step-select-zero-invalid-region
        step-selected-accepted-commit step-special-rejected-commit
    """.split()),
    "advance_committed": frozenset("""
        advance-active-invalid-host-state advance-committed-ordinary
        advance-terminal-invalid-host-state advance-to-heuristic
        advance-with-zero-global-reaches-exhausted
    """.split()),
    "validate_run_state": frozenset("""
        validate-state-active validate-state-active-with-outcome
        validate-state-active-zero-budget validate-state-bad-phase
        validate-state-bad-version validate-state-buffer-count-over-cap
        validate-state-buffer-region-zero validate-state-committed-response-bad-shape
        validate-state-committed-response-length-over-cap
        validate-state-event-bad-action-tag validate-state-event-count-over-budget
        validate-state-event-result-mismatch validate-state-event-wrong-node
        validate-state-exhausted validate-state-global-over-root
        validate-state-local-over-global validate-state-local-over-node
        validate-state-missing-current-node validate-state-post-advance
        validate-state-pre-advance validate-state-pre-post-advance-hybrid
        validate-state-replay-final-global-mismatch validate-state-short-prefix
        validate-state-trailing-byte validate-state-wrong-root
    """.split()),
}

_CONTENT_RECIPE_NAMES = {
    "cases-per-node-boundary": frozenset("cases-per-node-exact cases-per-node-plus-one".split()),
    "control-edge-boundary": frozenset("control-edges-exact control-edges-plus-one".split()),
    "enum-entries-boundary": frozenset("enum-entries-exact enum-entries-plus-one".split()),
    "field-schema-fields-boundary": frozenset("field-schema-fields-exact field-schema-fields-plus-one".split()),
    "lesson-nodes-boundary": frozenset("lesson-nodes-exact lesson-nodes-plus-one".split()),
    "matrix-cells-boundary": frozenset("matrix-cells-exact matrix-cells-plus-one".split()),
    "maximum-committed-state": frozenset("maximum-committed-run-state".split()),
    "maximum-exhausted-state": frozenset("maximum-exhausted-run-state".split()),
    "maximum-selection-cap-over": frozenset("maximum-selection-cap-plus-one".split()),
    "maximum-state-byte-over": frozenset(
        "committed-run-state-first-byte-over exhausted-run-state-first-byte-over".split()
    ),
    "maximum-support-stream": frozenset("maximum-support-content-stream".split()),
    "opaque-atoms-boundary": frozenset("opaque-atoms-exact opaque-atoms-plus-one".split()),
    "patch-base": frozenset("""
        alternative-feedback-missing-predicate atom-class-unknown atom-width-unknown
        bad-control-edge binding-class-unknown binding-key-duplicate
        data-binding-atom-count-zero data-binding-namespace-zero
        data-binding-semantic-code-zero duplicate-field-name-bytes
        enum-code-decreasing enum-code-duplicate external-default-feedback-mismatch
        feedback-code-unknown field-count-zero field-name-multiline
        field-reserved-nonzero field-storage-unknown
        heuristic-default-feedback-mismatch inline-field-count-zero
        lesson-case-reserved-nonzero lesson-case-response-decreasing
        lesson-case-response-duplicate lesson-case-tag-unknown lesson-flags-reserved
        lesson-mode-tag-unknown lesson-role-tag-unknown lesson-shape-tag-unknown
        limitation-feedback-with-predicate mask-bit-decreasing mask-bit-duplicate
        mask-listed-bit-not-one-hot mask-popcount-mismatch
        match-feedback-missing-predicate matrix-cell-outside-schema
        matrix-row-count-zero matrix-schema-forward matrix-schema-missing
        matrix-schema-self-reference matrix-schema-wrong-kind matrix-schema-zero
        multiple-passive-trace-owners multiple-roots
        neutral-feedback-with-predicate no-match-feedback-missing-predicate
        node-local-budget-below-selection-plus-commit node-local-budget-zero
        opaque-atom-outside-schema orphan-text-five packed-case-absent-region
        packed-case-feedback-mismatch packed-case-nonselectable-region
        packed-case-over-selection-cap packed-case-region-zero
        packed-default-feedback-mismatch packed-no-accepted-case
        packed-special-feedback-mismatch passive-action-count-exceeds-budget
        passive-action-count-zero passive-action-tag-unknown
        passive-commit-nonzero-region passive-expected-feedback-mismatch
        passive-expected-next-node-mismatch passive-expected-outcome-mismatch
        passive-final-action-not-commit passive-limitation-for-practice
        passive-outcome-tag-unknown passive-prefinal-action-result-mismatch
        passive-presentation-owner-mismatch practice-external-with-predicate
        precedence-stage3-id-before-kind precedence-stage4-before-stage5a
        precedence-stage5a-before-stage5b precedence-stage5b-before-stage5c
        precedence-stage7a-before-stage7b precedence-stage7b-before-stage7c
        precedence-success-cycle-before-budget predicate-binding-wrong-class
        predicate-result-binding-schema-mismatch predicate-result-schema-mismatch
        presentation-wrong-kind record-id-decreasing record-id-zero record-kind-zero
        region-count-zero region-flags-reserved region-id-decreasing
        region-id-duplicate region-id-zero region-label-wrong-kind
        region-out-of-surface-bounds region-selectable-overlap
        repeat-flag-set-forbidden repeat-flag-single-forbidden
        role-1-mode-1-forbidden role-1-mode-2-forbidden role-2-mode-1-forbidden
        role-2-mode-2-forbidden role-3-mode-1-forbidden role-3-mode-2-forbidden
        role-4-mode-1-forbidden role-4-mode-2-forbidden role-5-mode-3-forbidden
        root-budget-too-small root-budget-zero root-kind-changed-missing-root
        root-not-final sequence-case-repeat-forbidden single-case-cardinality-two
        single-max-selections-bad stream-stage-order-version-before-later-kind
        success-cycle text-initial-bom text-invalid-utf8
        text-invalid-utf8-continuation text-invalid-utf8-out-of-range
        text-invalid-utf8-overlong text-invalid-utf8-surrogate
        text-payload-length-zero text-prohibited-c0 text-prohibited-cr
        text-prohibited-del text-prohibited-nul text-truncated-utf8-sequence
        text-valid-multibyte-prefix-prohibited-c1 tuple-inline-atom-outside-schema
        tuple-presentation-contains-surface-twice
        tuple-reference-derived-length-mismatch tuple-slot-forward
        tuple-slot-missing tuple-slot-self-reference tuple-slot-wrong-kind
        tuple-slot-zero unsigned-entry-count-nonzero unsigned-min-greater-than-max
        vector-reference-derived-length-mismatch
    """.split()),
    "per-kind-records-boundary": frozenset("per-kind-records-exact per-kind-records-plus-one".split()),
    "record-count-boundary": frozenset("record-count-exact".split()),
    "record-id-boundary": frozenset("record-id-65535-exact".split()),
    "record-payload-bytes-boundary": frozenset(
        "record-payload-bytes-exact record-payload-bytes-plus-one".split()
    ),
    "regions-boundary": frozenset("regions-exact regions-plus-one".split()),
    "stream-byte-cap": frozenset("stream-byte-cap-plus-one".split()),
    "stream-bytes-boundary": frozenset("stream-bytes-exact stream-bytes-plus-one".split()),
    "text-bytes-boundary": frozenset("text-bytes-exact text-bytes-plus-one".split()),
    "tuple-slots-boundary": frozenset("tuple-slots-exact tuple-slots-plus-one".split()),
    "typed-step-sequence": frozenset("typed-step-65536-does-not-wrap".split()),
    "vector-atoms-boundary": frozenset("vector-atoms-exact".split()),
}

_CONTENT_BOUNDARY_TAGS = frozenset({
    "cases-per-node-boundary", "enum-entries-boundary",
    "field-schema-fields-boundary", "lesson-nodes-boundary",
    "matrix-cells-boundary", "opaque-atoms-boundary",
    "per-kind-records-boundary", "record-count-boundary",
    "record-id-boundary", "record-payload-bytes-boundary",
    "regions-boundary", "stream-bytes-boundary", "text-bytes-boundary",
    "tuple-slots-boundary", "vector-atoms-boundary",
})

_CONTENT_RECIPE_CAPS = dict.fromkeys(
    _CONTENT_RECIPE_NAMES["patch-base"], MAX_REPO_TEXT_BYTES
)
_CONTENT_RECIPE_CAPS.update({
    "cases-per-node-exact": 41_006,
    "cases-per-node-plus-one": 41_016,
    "committed-run-state-first-byte-over": 466_959,
    "control-edges-exact": 16_384,
    "control-edges-plus-one": 16_385,
    "enum-entries-exact": 53_276,
    "enum-entries-plus-one": 53_280,
    "exhausted-run-state-first-byte-over": 466_956,
    "field-schema-fields-exact": 5_052,
    "field-schema-fields-plus-one": 5_072,
    "lesson-nodes-exact": 122_896,
    "lesson-nodes-plus-one": 122_926,
    "matrix-cells-exact": 65_579,
    "matrix-cells-plus-one": 65_580,
    "maximum-committed-run-state": 466_958,
    "maximum-exhausted-run-state": 466_955,
    "maximum-selection-cap-plus-one": 86_252,
    "maximum-support-content-stream": 86_252,
    "opaque-atoms-exact": 4_154,
    "opaque-atoms-plus-one": 4_097,
    "per-kind-records-exact": 36_880,
    "per-kind-records-plus-one": 36_889,
    "record-count-exact": 65_535,
    "record-id-65535-exact": 65_535,
    "record-payload-bytes-exact": 1_048_576,
    "record-payload-bytes-plus-one": 1_048_577,
    "regions-exact": 61_508,
    "regions-plus-one": 61_522,
    "stream-byte-cap-plus-one": 1_048_577,
    "stream-bytes-exact": 1_048_576,
    "stream-bytes-plus-one": 1_048_577,
    "text-bytes-exact": 4_120,
    "text-bytes-plus-one": 4_097,
    "tuple-slots-exact": 8_248,
    "tuple-slots-plus-one": 4_097,
    "typed-step-65536-does-not-wrap": 65_536,
    "vector-atoms-exact": 65_577,
})


def _content_hex(value: object) -> bytes:
    if type(value) is not str or re.fullmatch(r"(?:[0-9a-f]{2})*", value) is None:
        raise AssertionError("invalid content fixture hex")
    return bytes.fromhex(value)


def _content_recipe_bytes(payload: dict[str, object], recipe: dict[str, object]) -> bytes:
    tag = recipe["recipe"]
    data = recipe["input"]
    name = recipe["name"]
    if tag not in _CONTENT_RECIPE_INPUT_KEYS or set(data) not in _CONTENT_RECIPE_INPUT_KEYS[tag]:
        raise AssertionError("invalid content recipe input")
    for value in data.values():
        if type(value) not in {int, str, list}:
            raise AssertionError("invalid content recipe value")
    if recipe["count_cap"] != _CONTENT_RECIPE_CAPS.get(name):
        raise AssertionError("invalid content recipe cap")
    integer_values = [value for value in data.values() if type(value) is int]
    if integer_values and max(integer_values) > recipe["count_cap"]:
        raise AssertionError("content recipe exceeds declared cap")
    if tag in _CONTENT_BOUNDARY_TAGS and data["boundary"] != (
        "plus-one" if name.endswith("-plus-one") else "exact"
    ):
        raise AssertionError("invalid content recipe boundary")

    base_row = payload["bases"][0]
    base = _content_hex(base_row["stream_hex"])
    support_sha = None
    if tag in {
        "maximum-support-stream", "maximum-selection-cap-over",
        "maximum-committed-state", "maximum-exhausted-state",
        "typed-step-sequence",
    }:
        support_sha = hashlib.sha256(_content_support_stream()).hexdigest()
    if tag == "maximum-support-stream" and data != {
        "accepted_selection_count": 4096,
        "event_budget": 65535,
        "matrix_columns": 64,
        "matrix_rows": 64,
        "record_count": 14,
        "region_count": 4096,
        "selection_cap": 4096,
    }:
        raise AssertionError("invalid maximum content support descriptor")
    if tag == "maximum-selection-cap-over" and data != {
        "base_stream_sha256": support_sha,
        "selection_cap": 4097,
    }:
        raise AssertionError("invalid selection-cap descriptor")
    if tag == "maximum-committed-state" and data != {
        "event_count": 65535,
        "invalid_action_count": 61438,
        "selection_count": 4096,
        "support_stream_sha256": support_sha,
    }:
        raise AssertionError("invalid committed-state descriptor")
    if tag == "maximum-exhausted-state" and data != {
        "event_count": 65535,
        "invalid_action_count": 61439,
        "selection_count": 4096,
        "support_stream_sha256": support_sha,
    }:
        raise AssertionError("invalid exhausted-state descriptor")
    if tag == "maximum-state-byte-over" and (
        data["base_state"] not in {"committed", "exhausted"}
        or data["append_hex"] != "00"
    ):
        raise AssertionError("invalid maximum-state excess descriptor")
    if tag == "typed-step-sequence" and data != {
        "first_4096": "select-region-ids-1-through-4096",
        "last": "commit",
        "next_61439": "invalid-action-sentinel",
        "operation_count": 65536,
        "support_stream_sha256": support_sha,
    }:
        raise AssertionError("invalid typed-step descriptor")
    if tag == "control-edge-boundary" and data not in (
        {"control_edges": 16384, "lesson_nodes": 4096},
        {"control_edges": 16385, "lesson_nodes": 4096},
    ):
        raise AssertionError("invalid control-edge descriptor")
    if tag == "patch-base":
        if data["base"] != "generic-base" or type(data["patches"]) is not list:
            raise AssertionError("invalid content patch recipe")
        output = bytearray(base)
        previous = len(base) + 1
        for patch in data["patches"]:
            if type(patch) is not dict or set(patch) != {"new_hex", "old_hex", "start"}:
                raise AssertionError("invalid content patch")
            if type(patch["start"]) is not int or patch["start"] < 0:
                raise AssertionError("invalid content patch start")
            old = _content_hex(patch["old_hex"])
            new = _content_hex(patch["new_hex"])
            start = patch["start"]
            if start >= previous or start + len(old) > previous:
                raise AssertionError("content patches are not descending and disjoint")
            if bytes(output[start:start + len(old)]) != old:
                raise AssertionError("content patch old bytes mismatch")
            output[start:start + len(old)] = new
            previous = start
        return bytes(output)
    if tag == "stream-byte-cap":
        return b"\0" * data["byte_count"]
    if tag == "maximum-support-stream":
        return _content_support_stream()
    if tag == "maximum-selection-cap-over":
        support = _content_support_stream()
        start = 78030
        return support[:start] + _content_u16(data["selection_cap"]) + support[start + 2:]
    if tag in {"maximum-committed-state", "maximum-exhausted-state"}:
        committed, exhausted = _content_max_states()
        return committed if tag == "maximum-committed-state" else exhausted
    if tag == "maximum-state-byte-over":
        committed, exhausted = _content_max_states()
        state = committed if data["base_state"] == "committed" else exhausted
        return state + _content_hex(data["append_hex"])
    if tag == "typed-step-sequence":
        return (
            b"".join(b"\x01\0" + _content_u16(index) for index in range(1, 4097))
            + b"\0" * 4 * 61439 + b"\x03\0\0\0"
        )
    if tag == "stream-bytes-boundary":
        return b"\0" * 4 + b"a" * (data["byte_count"] - 4)
    if tag == "record-count-boundary":
        return b"\0\0" + _content_u16(data["record_count"])
    if tag == "record-id-boundary":
        return _content_stream(
            [
                _content_record(1, "TEXT", b"a"),
                _content_record(data["record_id"], "ROOT", b"\0\x01\0\x01"),
            ]
        )
    if tag == "text-bytes-boundary":
        if data["boundary"] == "exact":
            return _content_wrong_root(
                [_content_record(1, "TEXT", b"a" * data["text_bytes"])], 2, 1
            )
        return (
            b"\0\0\0\x02\0\x01\0\x01"
            + _content_u32(data["declared_text_bytes"])
            + _content_record(2, "ROOT", b"\0\x01\0\x01")
        )
    if tag == "per-kind-records-boundary":
        count = data["text_record_count"]
        records = [_content_record(index, "TEXT", b"a") for index in range(1, count + 1)]
        return _content_wrong_root(records, count + 1, 1) if count == 4096 else _content_stream(
            [*records, _content_record(count + 1, "ROOT", b"\0\x01\0\x01")]
        )
    if tag == "enum-entries-boundary":
        count = data["entry_count"]
        labels = [_content_record(index, "TEXT", b"a") for index in range(1, 4097)]
        entries = b"".join(
            _content_u16(index) + _content_u16(index + 1 if count == 4096 else 1)
            for index in range(count)
        )
        enum = _content_record(4097, "ATOM_SCHEMA", b"\x02\x02" + _content_u16(count) + entries)
        return _content_wrong_root([*labels, enum], 4098, 4097) if count == 4096 else _content_stream(
            [*labels, enum, _content_record(4098, "ROOT", _content_u16(4097) + b"\0\x01")]
        )
    if tag == "vector-atoms-boundary":
        return _content_wrong_root(
            [_content_schema(1), _content_vector(2, 1, [0] * data["atom_count"])], 3, 2
        )
    if tag == "matrix-cells-boundary":
        records = [
            _content_schema(1),
            _content_matrix(2, 1, data["rows"], data["columns"], [0] * data["cell_count"]),
        ]
        return _content_wrong_root(records, 3, 2) if data["boundary"] == "exact" else _content_stream(
            [*records, _content_record(3, "ROOT", b"\0\x02\0\x01")]
        )
    if tag == "field-schema-fields-boundary":
        count = data["field_count"]
        names = [_content_record(index, "TEXT", f"f{index}".encode()) for index in range(1, count + 1)]
        atom_id = 258
        fields = _content_record(
            259,
            "FIELD_SCHEMA",
            _content_u16(count) + b"".join(
                _content_u16(index + 1) + b"\x01\0" + _content_u16(atom_id) + b"\0\x01"
                for index in range(count)
            ),
        )
        records = [*names, _content_schema(atom_id), fields]
        return _content_wrong_root(records, 260, 259) if count == 256 else _content_stream(
            [*records, _content_record(260, "ROOT", _content_u16(259) + b"\0\x01")]
        )
    if tag == "tuple-slots-boundary":
        count = data["slot_count"]
        field_schema = _content_record(
            2,
            "FIELD_SCHEMA",
            b"\0\x01\0\x01\x02\0\0\x01" + _content_u16(count),
        )
        if count == 4096:
            return _content_wrong_root(
                [_content_record(1, "TEXT", b"refs"), field_schema,
                 _content_record(3, "TUPLE", b"\0\x02" + b"\0\x01" * count)],
                4,
                3,
            )
        return _content_stream(
            [_content_record(1, "TEXT", b"refs"), field_schema,
             _content_record(3, "ROOT", b"\0\x02\0\x01")]
        )
    if tag == "opaque-atoms-boundary":
        count = data["atom_count"]
        binding = _content_record(
            2,
            "SEMANTIC_BINDING",
            b"\x01\0\0\x01\0\x01\0\x01" + _content_u16(count),
        )
        if count == 4096:
            return _content_wrong_root(
                [_content_schema(1), binding,
                 _content_record(3, "OPAQUE_DATA", b"\0\x02" + b"\0" * count)],
                4,
                3,
            )
        return _content_stream(
            [_content_schema(1), binding, _content_record(3, "ROOT", b"\0\x02\0\x01")]
        )
    if tag == "regions-boundary":
        count = data["region_count"]
        regions = _content_u16(3) + _content_u16(count)
        for index in range(count):
            row, column = divmod(index, 64)
            regions += (
                _content_u16(index + 1) + _content_u16(1) + _content_u16(row)
                + _content_u16(row + 1) + _content_u16(column)
                + _content_u16(column + 1) + b"\x01\0"
            )
        records = [
            _content_record(1, "TEXT", b"cell"),
            _content_schema(2),
            _content_matrix(3, 2, 64, 64, [0] * 4096),
            _content_record(4, "REGION_SET", regions),
        ]
        return _content_wrong_root(records, 5, 4) if count == 4096 else _content_stream(
            [*records, _content_record(5, "ROOT", b"\0\x04\0\x01")]
        )
    if tag == "lesson-nodes-boundary":
        count = data["lesson_node_count"]
        nodes = [_content_record(index, "LESSON_NODE", b"\0" * 22) for index in range(1, count + 1)]
        return _content_stream(
            [*nodes, _content_record(count + 1, "ROOT", b"\0\x01\0\x01")]
        )
    if tag == "cases-per-node-boundary":
        count = data["case_count"]
        payload_bytes = bytes((5, 3, 1, 1)) + b"\0\0" * 4 + _content_u16(4096) + _content_u16(65535) + _content_u16(count)
        payload_bytes += b"".join(
            b"\x01\0\0\x01" + _content_u16(index) + b"\0\0\0\0"
            for index in range(1, count + 1)
        )
        return _content_stream(
            [_content_record(1, "LESSON_NODE", payload_bytes + b"\0\0\0\0"),
             _content_record(2, "ROOT", b"\0\x01\xff\xff")]
        )
    if tag == "record-payload-bytes-boundary":
        return b"\0\0\0\x02\0\x01\0\x03" + _content_u32(data["declared_payload_bytes"])
    if tag == "control-edge-boundary":
        return _content_control_stream(data["control_edges"] == 16385)
    raise AssertionError(f"unknown content recipe: {name}")


def _content_projection_is_closed(projection: object) -> None:
    if type(projection) is not dict or set(projection) != {
        "records", "root_record_id", "version"
    }:
        raise AssertionError("invalid content projection")
    if type(projection["version"]) is not int or type(projection["root_record_id"]) is not int:
        raise AssertionError("invalid content projection scalar")
    records = projection["records"]
    if type(records) is not list:
        raise AssertionError("invalid content projection records")
    record_keys = {
        "ATOM_VECTOR": {"atom_count", "atom_schema_ref", "atoms"},
        "FEEDBACK": {"display_ref", "feedback_code", "predicate_result_ref"},
        "FIELD_SCHEMA": {"field_count", "fields"},
        "LESSON_NODE": {
            "answer_mode", "case_count", "cases", "default_feedback_ref",
            "default_next_node_ref", "flags", "item_event_budget",
            "max_selections", "passive_trace_ref", "predicate_result_ref",
            "presentation_ref", "region_set_ref", "response_shape", "role",
        },
        "MATRIX": {"atom_schema_ref", "cells", "columns", "rows"},
        "OPAQUE_DATA": {"data", "data_binding_ref"},
        "PASSIVE_TRACE": {
            "action_count", "actions", "expected_feedback_ref",
            "expected_next_node_ref", "expected_outcome", "limitation_text_ref",
            "presentation_ref", "region_set_ref", "resulting_presentation_ref",
        },
        "PREDICATE_RESULT": {
            "predicate_binding_ref", "result_atom_vector_ref",
            "subject_opaque_data_ref",
        },
        "REGION_SET": {"region_count", "regions", "surface_matrix_ref"},
        "ROOT": {"entry_node_ref", "global_event_budget"},
        "SEMANTIC_BINDING": {
            "argument", "auxiliary", "binding_class", "namespace_id",
            "semantic_code",
        },
        "TEXT": {"text"},
        "TUPLE": {"field_schema_ref", "field_values"},
    }
    for record in records:
        if type(record) is not dict or type(record.get("kind")) is not str:
            raise AssertionError("invalid content projection record")
        kind = record["kind"]
        expected = record_keys.get(kind)
        if kind == "ATOM_SCHEMA":
            atom_class = record.get("atom_class")
            if type(atom_class) is not int:
                raise AssertionError("invalid atom class")
            expected = {
                1: {"atom_class", "atom_width", "entry_count", "max_value", "min_value"},
                2: {"atom_class", "atom_width", "entries", "entry_count"},
                3: {"allowed_mask", "atom_class", "atom_width", "entries", "entry_count"},
            }.get(atom_class)
        if expected is None or set(record) != {"kind", "record_id", *expected}:
            raise AssertionError("invalid content projection record keys")
        if type(record["record_id"]) is not int:
            raise AssertionError("invalid content record id")
        for key, value in record.items():
            if key in {"kind", "text"}:
                if type(value) is not str:
                    raise AssertionError("invalid content projection text")
            elif key in {"atoms", "cells", "data"}:
                if type(value) is not list or any(type(item) is not int for item in value):
                    raise AssertionError("invalid content scalar list")
            elif key == "actions":
                if type(value) is not list:
                    raise AssertionError("invalid content action list")
                for action in value:
                    if len(_content_hex(action)) != 4:
                        raise AssertionError("invalid content action")
            elif key == "entries":
                if type(value) is not list:
                    raise AssertionError("invalid content entries")
                entry_keys = (
                    {"code", "label_text_ref"}
                    if record["atom_class"] == 2
                    else {"label_text_ref", "one_hot_bit"}
                )
                for entry in value:
                    if type(entry) is not dict or set(entry) != entry_keys or any(
                        type(item) is not int for item in entry.values()
                    ):
                        raise AssertionError("invalid content entry")
            elif key == "fields":
                if type(value) is not list:
                    raise AssertionError("invalid content fields")
                for field in value:
                    if type(field) is not dict or set(field) != {
                        "count", "name_text_ref", "storage", "type"
                    } or any(type(item) is not int for item in field.values()):
                        raise AssertionError("invalid content field")
            elif key == "field_values":
                if type(value) is not list:
                    raise AssertionError("invalid tuple fields")
                for field in value:
                    if type(field) is not dict or set(field) not in (
                        {"atoms"}, {"record_refs"}
                    ):
                        raise AssertionError("invalid tuple field")
                    values = next(iter(field.values()))
                    if type(values) is not list or any(type(item) is not int for item in values):
                        raise AssertionError("invalid tuple field values")
            elif key == "regions":
                if type(value) is not list:
                    raise AssertionError("invalid content regions")
                for region in value:
                    if type(region) is not dict or set(region) != {
                        "column_end", "column_start", "flags", "label_ref",
                        "region_id", "row_end", "row_start",
                    } or any(type(item) is not int for item in region.values()):
                        raise AssertionError("invalid content region")
            elif key == "cases":
                if type(value) is not list:
                    raise AssertionError("invalid content cases")
                for case in value:
                    if type(case) is not dict or set(case) != {
                        "case_class", "feedback_ref", "next_node_ref",
                        "region_ids", "selection_count",
                    }:
                        raise AssertionError("invalid content case")
                    if any(
                        type(item) is not int
                        for name, item in case.items() if name != "region_ids"
                    ) or type(case["region_ids"]) is not list or any(
                        type(item) is not int for item in case["region_ids"]
                    ):
                        raise AssertionError("invalid content case values")
            elif type(value) is not int:
                raise AssertionError("invalid content projection scalar")


def validate_content_fixture_contract(payload: object) -> None:
    if type(payload) is not dict or set(payload) != {"bases", "cases", "recipes", "schema"}:
        raise AssertionError("invalid content fixture")
    if payload["schema"] != "golden-board.content-v0-fixtures/v0":
        raise AssertionError("invalid content fixture schema")
    if type(payload["bases"]) is not list or len(payload["bases"]) != 1:
        raise AssertionError("invalid content fixture base")
    base = payload["bases"][0]
    if type(base) is not dict or set(base) != {
        "name", "projection", "stream_hex", "stream_length", "stream_sha256"
    } or base["name"] != "generic-base":
        raise AssertionError("invalid content fixture base")
    stream = _content_hex(base["stream_hex"])
    if (
        type(base["stream_length"]) is not int
        or base["stream_length"] != len(stream)
        or type(base["stream_sha256"]) is not str
        or base["stream_sha256"] != hashlib.sha256(stream).hexdigest()
    ):
        raise AssertionError("invalid content fixture base bytes")
    _content_projection_is_closed(base["projection"])

    if type(payload["cases"]) is not list or type(payload["recipes"]) is not list:
        raise AssertionError("invalid content fixture rows")
    rows = [*payload["cases"], *payload["recipes"]]
    names = [row.get("name") for row in rows if type(row) is dict]
    if len(names) != len(rows) or len(names) != len(set(names)) or any(
        type(name) is not str or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) is None
        for name in names
    ):
        raise AssertionError("invalid content fixture names")
    by_name = {row["name"]: row for row in rows}
    direct_names = {
        operation: frozenset(
            row["name"] for row in payload["cases"]
            if row.get("operation") == operation
        )
        for operation in _CONTENT_DIRECT_NAMES
    }
    recipe_names = {
        tag: frozenset(
            row["name"] for row in payload["recipes"]
            if row.get("recipe") == tag
        )
        for tag in _CONTENT_RECIPE_NAMES
    }
    if direct_names != _CONTENT_DIRECT_NAMES or recipe_names != _CONTENT_RECIPE_NAMES:
        raise AssertionError("invalid content name-to-operation inventory")
    if sum(map(len, direct_names.values())) != len(payload["cases"]) or sum(
        map(len, recipe_names.values())
    ) != len(payload["recipes"]):
        raise AssertionError("unknown content row")
    if by_name["stream-valid-generic-base"]["operation"] != "stream_validation":
        raise AssertionError("invalid content operation")
    if by_name["new-run-exact"]["operation"] != "new_run":
        raise AssertionError("invalid content operation")
    projection = by_name["stream-valid-generic-base"]["expected"]["success"]["projection"]
    if projection != base["projection"]:
        raise AssertionError("content base projection mismatch")

    input_keys = {
        "stream_validation": {"stream_hex"},
        "new_run": {"stream_hex"},
        "step": {"action_hex", "state_hex", "stream_hex"},
        "advance_committed": {"state_hex", "stream_hex"},
        "validate_run_state": {"state_hex", "stream_hex"},
    }
    success_shapes = {
        frozenset({"projection"}),
        frozenset({"state_hex"}),
        frozenset({"state_hex", "interaction_result"}),
        frozenset({
            "feedback_ref", "interaction_result", "next_node_ref", "outcome", "state_hex"
        }),
        frozenset({"stream_length", "stream_sha256"}),
        frozenset({"state_length", "state_sha256"}),
        frozenset({
            "final_state_bytes", "final_state_sha256", "last_interaction_result",
            "state_unchanged",
        }),
    }
    integer_success = {
        "feedback_ref", "final_state_bytes", "interaction_result",
        "last_interaction_result", "next_node_ref", "outcome",
        "state_length", "stream_length",
    }
    boolean_success = {"state_unchanged"}

    for case in payload["cases"]:
        if type(case) is not dict or set(case) != {"covers", "expected", "input", "name", "operation"}:
            raise AssertionError("invalid direct content row")
        operation = case["operation"]
        if operation not in input_keys or type(case["input"]) is not dict or set(case["input"]) != input_keys[operation]:
            raise AssertionError("invalid direct content input")
        for key, value in case["input"].items():
            if key.endswith("_hex"):
                _content_hex(value)
        if type(case["covers"]) is not list or len(case["covers"]) != len(set(case["covers"])) or any(
            type(label) is not str for label in case["covers"]
        ):
            raise AssertionError("invalid content coverage")

    for row in rows:
        expected = row["expected"]
        if type(expected) is not dict or len(expected) != 1:
            raise AssertionError("invalid content expected branch")
        branch, value = next(iter(expected.items()))
        if branch == "rejection":
            if type(value) is not dict or set(value) != {"code", "raw_end", "raw_start"} or any(
                type(item) is not int for item in value.values()
            ):
                raise AssertionError("invalid content rejection")
        elif branch == "invalid_host_state":
            if value != {}:
                raise AssertionError("invalid host-state result")
        elif branch == "success":
            if type(value) is not dict or frozenset(value) not in success_shapes:
                raise AssertionError("invalid content success shape")
            for key, item in value.items():
                if key == "projection":
                    _content_projection_is_closed(item)
                elif key.endswith("_hex"):
                    _content_hex(item)
                elif key.endswith("_sha256"):
                    if type(item) is not str or re.fullmatch(r"[0-9a-f]{64}", item) is None:
                        raise AssertionError("invalid content success digest")
                elif key in integer_success and type(item) is not int:
                    raise AssertionError("invalid content success integer")
                elif key in boolean_success and type(item) is not bool:
                    raise AssertionError("invalid content success boolean")
                elif key not in integer_success | boolean_success:
                    raise AssertionError("invalid content success field")
        else:
            raise AssertionError("invalid content expected branch")

    tag_operations = {
        tag: "stream_validation" for tag in _CONTENT_RECIPE_INPUT_KEYS
    }
    tag_operations.update(
        {
            "maximum-committed-state": "validate_run_state",
            "maximum-exhausted-state": "validate_run_state",
            "maximum-state-byte-over": "validate_run_state",
            "typed-step-sequence": "step",
        }
    )
    for recipe in payload["recipes"]:
        if type(recipe) is not dict or set(recipe) != {
            "count_cap", "covers", "expected", "input", "input_bytes",
            "input_sha256", "name", "operation", "recipe",
        }:
            raise AssertionError("invalid content recipe row")
        tag = recipe["recipe"]
        if type(tag) is not str or tag_operations.get(tag) != recipe["operation"]:
            raise AssertionError("invalid content recipe dispatch")
        if type(recipe["covers"]) is not list or len(recipe["covers"]) != len(
            set(recipe["covers"])
        ) or any(type(label) is not str for label in recipe["covers"]):
            raise AssertionError("invalid content coverage")
        if (
            type(recipe["count_cap"]) is not int
            or not 0 < recipe["count_cap"] <= MAX_REPO_TEXT_BYTES + 1
            or type(recipe["input_bytes"]) is not int
            or not 0 <= recipe["input_bytes"] <= MAX_REPO_TEXT_BYTES + 1
            or type(recipe["input_sha256"]) is not str
            or re.fullmatch(r"[0-9a-f]{64}", recipe["input_sha256"]) is None
        ):
            raise AssertionError("invalid content recipe metadata")
        built = _content_recipe_bytes(payload, recipe)
        digest = hashlib.sha256(built).hexdigest()
        if len(built) != recipe["input_bytes"] or digest != recipe["input_sha256"]:
            raise AssertionError(
                f"content recipe construction mismatch: {recipe['name']} "
                f"{len(built)}/{digest}"
            )


class FoundationModulesPresent(unittest.TestCase):
    def test_identity_and_manifest_modules_exist(self) -> None:
        self.assertIsNotNone(identity)
        self.assertIsNotNone(canonical_manifest)

    def test_source_doctor_module_exists(self) -> None:
        self.assertIsNotNone(source_doctor)


@unittest.skipIf(identity is None, "implementation not present")
class IdentityConformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.before = IDENTITY_FIXTURE.read_bytes()
        cls.fixture = json.loads(cls.before)

    @classmethod
    def tearDownClass(cls) -> None:
        if IDENTITY_FIXTURE.read_bytes() != cls.before:
            raise AssertionError("identity fixture was modified")

    def test_hand_authored_vectors(self) -> None:
        for case in self.fixture["vectors"]:
            with self.subTest(case=case["name"]):
                domain = bytes.fromhex(case["domain_hex"])
                fields = [bytes.fromhex(value) for value in case["fields_hex"]]
                self.assertEqual(
                    identity.frame_preimage(domain, fields).hex(),
                    case["preimage_hex"],
                )
                self.assertEqual(
                    identity.identity_hex(domain, fields), case["identity"]
                )

    def test_registered_m1_vectors_are_exact(self) -> None:
        vectors = self.fixture["vectors"]
        self.assertEqual(len(vectors), 12)
        m0_bytes = json.dumps(
            vectors[:8], ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
        self.assertEqual(hashlib.sha256(m0_bytes).hexdigest(), M0_IDENTITY_VECTORS_SHA256)
        self.assertEqual(vectors[8:], M1_IDENTITY_VECTORS)

    def test_nist_sha256_known_answers(self) -> None:
        for case in self.fixture["sha256"]:
            with self.subTest(case=case["name"]):
                self.assertEqual(
                    hashlib.sha256(bytes.fromhex(case["message_hex"])).hexdigest(),
                    case["digest"],
                )

    def test_integer_boundaries(self) -> None:
        self.assertEqual(identity.u16_be(0), b"\x00\x00")
        self.assertEqual(identity.u16_be(65_535), b"\xff\xff")
        self.assertEqual(identity.u32_be(0), b"\x00\x00\x00\x00")
        self.assertEqual(identity.u32_be(4_294_967_295), b"\xff\xff\xff\xff")
        for value in (-1, 65_536):
            with self.subTest(kind="u16", value=value):
                with self.assertRaises(identity.IdentityError):
                    identity.u16_be(value)
        for value in (-1, 4_294_967_296):
            with self.subTest(kind="u32", value=value):
                with self.assertRaises(identity.IdentityError):
                    identity.u32_be(value)

    def test_field_count_and_domain_rejections(self) -> None:
        with self.assertRaises(identity.IdentityError):
            identity.frame_preimage(b"test:a\0", [b""] * 65_536)
        for domain in (b"test:a", b"test\0a\0", b"t\xff\0", "test:a\0"):
            with self.subTest(domain=domain):
                with self.assertRaises(identity.IdentityError):
                    identity.frame_preimage(domain, [])
        with self.assertRaises(identity.IdentityError):
            identity.frame_preimage(b"test:a\0", ["not-bytes"])


@unittest.skipIf(canonical_manifest is None, "implementation not present")
class ManifestConformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.before = MANIFEST_FIXTURE.read_bytes()
        cls.fixture = json.loads(cls.before)

    @classmethod
    def tearDownClass(cls) -> None:
        if MANIFEST_FIXTURE.read_bytes() != cls.before:
            raise AssertionError("manifest fixture was modified")

    def test_payload_cases(self) -> None:
        for case in self.fixture["cases"]:
            source = bytes.fromhex(case["source_hex"])
            expected = bytes.fromhex(case["canonical_hex"])
            with self.subTest(case=case["name"]):
                if case["outcome"] == "reject":
                    with self.assertRaises(canonical_manifest.ManifestError):
                        canonical_manifest.canonicalize_manifest(source)
                    continue
                self.assertEqual(
                    canonical_manifest.canonicalize_manifest(source), expected
                )
                if case["outcome"] == "canonical":
                    canonical_manifest.validate_canonical_manifest(source)
                else:
                    with self.assertRaises(canonical_manifest.ManifestError):
                        canonical_manifest.validate_canonical_manifest(source)

    def test_fixture_files_are_canonical(self) -> None:
        canonical_manifest.validate_canonical_manifest(IDENTITY_FIXTURE.read_bytes())
        canonical_manifest.validate_canonical_manifest(MANIFEST_FIXTURE.read_bytes())
        canonical_manifest.validate_canonical_manifest(CHESS_FIXTURE.read_bytes())
        canonical_manifest.validate_canonical_manifest(SOURCE_FIXTURE.read_bytes())

    def test_depth_boundaries(self) -> None:
        depth_32 = b'{"a":' * 31 + b"{}" + b"}" * 31 + b"\n"
        depth_33 = b'{"a":' * 32 + b"{}" + b"}" * 32 + b"\n"
        canonical_manifest.validate_canonical_manifest(depth_32)
        with self.assertRaises(canonical_manifest.ManifestError):
            canonical_manifest.canonicalize_manifest(depth_33)
        nested = {}
        for _ in range(32):
            nested = {"a": nested}
        with self.assertRaises(canonical_manifest.ManifestError):
            canonical_manifest.serialize_manifest(nested)

    def test_input_and_output_boundaries(self) -> None:
        content = "a" * (canonical_manifest.MAX_BYTES - 9)
        exact = ('{"s":"' + content + '"}\n').encode()
        self.assertEqual(len(exact), canonical_manifest.MAX_BYTES)
        canonical_manifest.validate_canonical_manifest(exact)
        with self.assertRaises(canonical_manifest.ManifestError):
            canonical_manifest.canonicalize_manifest(exact + b"\n")
        self.assertEqual(
            len(canonical_manifest.serialize_manifest({"s": content})),
            canonical_manifest.MAX_BYTES,
        )
        with self.assertRaises(canonical_manifest.ManifestError):
            canonical_manifest.serialize_manifest({"s": content + "a"})

    def test_round_trip_and_insertion_order(self) -> None:
        source = b'{"a":[true,0,"x"],"b":{}}\n'
        value = canonical_manifest.validate_canonical_manifest(source)
        self.assertEqual(canonical_manifest.serialize_manifest(value), source)
        self.assertEqual(
            canonical_manifest.serialize_manifest({"b": 1, "a": 2}),
            canonical_manifest.serialize_manifest({"a": 2, "b": 1}),
        )

    def test_serializer_rejects_values_outside_subset(self) -> None:
        values = [None, -1, 1.0, {"": 1}, {"é": 1}, {"a": "\ud800"}, [1]]
        for value in values:
            with self.subTest(value=repr(value)):
                with self.assertRaises(canonical_manifest.ManifestError):
                    canonical_manifest.serialize_manifest(value)


@unittest.skipIf(source_doctor is None, "source doctor not present")
class SourceDoctorTrustBoundary(unittest.TestCase):
    def test_lock_accepts_only_the_closed_m0_document(self) -> None:
        lock = (ROOT / "inputs/source-lock.toml").read_bytes()
        parsed = source_doctor.parse_source_lock(lock, ROOT)
        self.assertEqual(parsed.path, "docs/64_games.md")
        self.assertEqual(parsed.expected_bytes, 165_145)

        mutations = [
            lock.replace(b'id = "pgn-guide-1994"', b'id = "fide-laws-2023"'),
            lock.replace(b"33d44f7167ab190c", b"X3d44f7167ab190c", 1),
            lock.replace(b'newline = "lf"\n', b"", 1),
            lock.replace(b'newline = "lf"\n', b'newline = "lf"\nextra = 1\n', 1),
            lock.replace(b'path = "docs/64_games.md"', b'path = "/tmp/x"', 1),
            lock.replace(b'path = "docs/64_games.md"', b'path = "../x"', 1),
            lock.replace(b'role = "historical_background"', b'role = "future_profile"', 1),
            lock.replace(b'newline = "lf"\n', b'newline = "lf"\nprofile = "v0"\n', 1),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                with self.assertRaises(source_doctor.LockError):
                    source_doctor.parse_source_lock(mutation, ROOT)

    def test_regular_source_bounds_and_lock_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            path = root / "docs/source.md"
            for size in (source_doctor.MAX_SOURCE_BYTES - 1, source_doctor.MAX_SOURCE_BYTES):
                data = b"a" * size
                path.write_bytes(data)
                locked = source_doctor.LockedSource(
                    "docs/source.md", len(data), hashlib.sha256(data).hexdigest()
                )
                opened = source_doctor.read_locked_source(root, locked)
                self.assertTrue(opened.lock_match)
                self.assertEqual(opened.data, data)

            path.write_bytes(b"a" * (source_doctor.MAX_SOURCE_BYTES + 1))
            with self.assertRaises(source_doctor.InputError):
                source_doctor.read_locked_source(
                    root,
                    source_doctor.LockedSource("docs/source.md", 0, "0" * 64),
                )

            path.write_bytes(b"same")
            expected = source_doctor.LockedSource(
                "docs/source.md", 4, hashlib.sha256(b"same").hexdigest()
            )
            for replacement in (b"diff", b"same-more", b"sam"):
                path.write_bytes(replacement)
                opened = source_doctor.read_locked_source(root, expected)
                self.assertFalse(opened.lock_match)
            path.write_bytes(b"same")
            wrong_size = source_doctor.LockedSource(
                "docs/source.md", 5, hashlib.sha256(b"same").hexdigest()
            )
            wrong_hash = source_doctor.LockedSource("docs/source.md", 4, "0" * 64)
            self.assertFalse(source_doctor.read_locked_source(root, wrong_size).lock_match)
            self.assertFalse(source_doctor.read_locked_source(root, wrong_hash).lock_match)

            path.chmod(0)
            try:
                if not os.access(path, os.R_OK):
                    with self.assertRaises(source_doctor.InputError):
                        source_doctor.read_locked_source(root, expected)
            finally:
                path.chmod(0o600)

    def test_unsafe_source_objects_reject_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            target = root / "docs/target"
            target.write_bytes(b"x")
            locked = source_doctor.LockedSource("docs/input", 1, hashlib.sha256(b"x").hexdigest())
            input_path = root / locked.path

            cases = []
            input_path.symlink_to(target)
            cases.append("symlink")
            for kind in cases:
                with self.subTest(kind=kind):
                    with self.assertRaises(source_doctor.InputError):
                        source_doctor.read_locked_source(root, locked)
            input_path.unlink()

            input_path.mkdir()
            with self.assertRaises(source_doctor.InputError):
                source_doctor.read_locked_source(root, locked)
            input_path.rmdir()

            if hasattr(os, "mkfifo"):
                os.mkfifo(input_path)
                try:
                    with self.assertRaises(source_doctor.InputError):
                        source_doctor.read_locked_source(root, locked)
                finally:
                    input_path.unlink()

            if hasattr(socket, "AF_UNIX"):
                listener = socket.socket(socket.AF_UNIX)
                try:
                    listener.bind(str(input_path))
                    with self.assertRaises(source_doctor.InputError):
                        source_doctor.read_locked_source(root, locked)
                finally:
                    listener.close()
                    input_path.unlink(missing_ok=True)

            with self.assertRaises(source_doctor.InputError):
                source_doctor.read_locked_source(root, locked)
            with self.assertRaises(source_doctor.InputError):
                source_doctor.read_locked_source(
                    root,
                    source_doctor.LockedSource("../outside", 0, "0" * 64),
                )


@unittest.skipIf(source_doctor is None, "source doctor not present")
class SourceDoctorScanner(unittest.TestCase):
    def scan(self, data: bytes) -> dict:
        locked = source_doctor.LockedSource(
            "docs/source.md", len(data), hashlib.sha256(data).hexdigest()
        )
        return source_doctor.scan_source(data, locked)

    def test_source_fences_tags_spans_and_regions(self) -> None:
        data = (
            b"outer  \n"
            b"```pgn\n"
            b'[Event "x...?!"]\n'
            b'[Result "1-0"]\n'
            b'[Event "escaped\\\"quote"]\n'
            b"malformed\n"
            b"\n"
            b"1. e4 e5 1-0\n"
            b"```\n"
        )
        report = self.scan(data)
        self.assertEqual(report["fences"]["candidate_count"], 1)
        block = report["blocks"][0]
        for key in ("fence_span", "content_span", "tag_span", "separator_span", "movetext_span"):
            start, end = block[key]
            self.assertEqual(len(data[start:end]), end - start)
        self.assertEqual(data[slice(*block["movetext_span"])], b"1. e4 e5 1-0\n")
        self.assertEqual(report["tags"]["recognized_lines"], 3)
        self.assertEqual(report["tags"]["duplicate_blocks"]["count"], 1)
        self.assertEqual(report["tags"]["malformed_lines"]["count"], 1)
        self.assertEqual(report["tags"]["escape_counts"]["quote"], 1)
        event = next(item for item in report["tags"]["punctuation"] if item["name"] == "Event")
        self.assertEqual(event["ellipsis_value_count"], 1)
        self.assertEqual(event["question_value_count"], 1)
        trailing = report["source"]["trailing_horizontal_whitespace"]
        self.assertEqual([item["region"] for item in trailing], [
            "outer_markdown", "fence", "tags", "separator", "movetext"
        ])
        self.assertEqual(trailing[0]["count"], 1)
        self.assertEqual(report["movetext"]["constructs"][0]["count"], 0)
        canonical_manifest.validate_canonical_manifest(
            canonical_manifest.serialize_manifest(report)
        )

    def test_encoding_newlines_controls_and_fence_anomalies(self) -> None:
        data = (
            b"\xef\xbb\xbftext\n"
            b"```PGN\r\n"
            b"```\n"
            b"```pgn\n"
            b"```pgn\n"
            b"\x7f\n"
            b"```\n"
            b"```pgn\n"
        )
        report = self.scan(data)
        self.assertTrue(report["source"]["bom"])
        self.assertEqual(report["source"]["line_endings"]["crlf"], 1)
        self.assertEqual(report["source"]["unexpected_controls"]["count"], 1)
        self.assertEqual(report["fences"]["near_misses"]["count"], 1)
        self.assertEqual(report["fences"]["orphan_closers"]["count"], 1)
        self.assertEqual(report["fences"]["nested_openers"]["count"], 1)
        self.assertEqual(report["fences"]["unclosed_openers"]["count"], 1)
        self.assertEqual(report["fences"]["candidate_count"], 1)

        invalid = self.scan(b"\xff\n")
        self.assertFalse(invalid["source"]["utf8_valid"])
        self.assertEqual(invalid["source"]["nfc_state"], "unavailable")
        non_nfc = self.scan("e\u0301\n".encode())
        self.assertEqual(non_nfc["source"]["nfc_state"], "valid_non_nfc")

        candidate = b"```pgn\n\n```\n"
        for count in (0, 1, 63, 64, 65):
            source = candidate * count
            locked = source_doctor.LockedSource(
                "docs/source.md", len(source), hashlib.sha256(source).hexdigest()
            )
            counted = source_doctor.scan_source(source, locked)
            self.assertEqual(counted["fences"]["candidate_count"], count)
            self.assertEqual(source_doctor._gate_passes(counted), count == 64)

    def test_movetext_classes_constructs_results_and_duplicates(self) -> None:
        first = (
            b"```pgn\n[Result \"1-0\"]\n\n"
            b"1. e4 Nf3 N1f3 Nb1d2 O-O exd5 e8=Q+ Raxd1# 2. O-O-O 1-0\n```\n"
        )
        second = b"```pgn\n[Result \"0-1\"]\n\n1. e4  e5 1-0\n```\n"
        third = b"```pgn\n[Result \"1-0\"]\n\n1. e4 e5 1-0\n```\n"
        fourth = b"```pgn\n[Result \"1-0\"]\n\n1. e4 e5 1-0\n```\n"
        constructs = (
            b"```pgn\n\n%escape\n"
            b"1... { } ( ) ; 0-0 e.p. ++ e2-e4 e2e4 $12 foo!? *\n```\n"
        )
        empty = b"```pgn\n\n\n```\n"
        report = self.scan(first + second + third + fourth + constructs + empty)
        primary = report["movetext"]["primary_counts"]
        self.assertGreater(primary["move_number"], 0)
        self.assertGreater(primary["castle"], 0)
        self.assertGreater(primary["piece"], 0)
        self.assertGreater(primary["pawn_capture"], 0)
        self.assertGreater(primary["pawn_quiet"], 0)
        self.assertGreater(primary["unknown"], 0)
        features = report["movetext"]["feature_counts"]
        for key in features:
            self.assertGreater(features[key], 0, key)
        construct_counts = {item["key"]: item["count"] for item in report["movetext"]["constructs"]}
        for key in construct_counts:
            self.assertGreater(construct_counts[key], 0, key)
        self.assertEqual(report["movetext"]["result_agreement_counts"], {
            "indeterminate": 2, "match": 3, "mismatch": 1
        })
        token_groups = report["duplicate_candidates"]["token_sequence"]
        self.assertEqual(token_groups[0]["ordinals"], [2, 3, 4])
        self.assertEqual(report["duplicate_candidates"]["raw_movetext"][0]["ordinals"], [3, 4])
        self.assertGreater(report["movetext"]["line_wrap"]["empty_lines"], 0)
        self.assertGreater(report["movetext"]["line_wrap"]["repeated_space_lines"], 0)

    def test_samples_and_report_limit_are_bounded(self) -> None:
        unknowns = b" ".join([b"x" * 300] + [f"?{index}".encode() for index in range(40)])
        data = b"```pgn\n\n" + unknowns + b"\n```\n"
        sampled = self.scan(data)["movetext"]["unknown_tokens"]
        self.assertEqual(sampled["count"], 41)
        self.assertEqual(len(sampled["examples"]), 32)
        self.assertEqual(sampled["omitted_count"], 9)
        self.assertTrue(sampled["examples"][0]["truncated"])
        self.assertEqual(len(sampled["examples"][0]["bytes_hex"]), 512)

        dense = b"```pgn\n\n```\n" * 60_000
        self.assertLessEqual(len(dense), source_doctor.MAX_SOURCE_BYTES)
        locked = source_doctor.LockedSource(
            "docs/source.md", len(dense), hashlib.sha256(dense).hexdigest()
        )
        self.assertEqual(source_doctor.generate_report_bytes(dense, locked), source_doctor.REPORT_LIMIT_BYTES)

        unique_tags = b"".join(
            f'[A{index} "x"]\n'.encode() for index in range(2_000)
        )
        tag_dense = b"```pgn\n" + unique_tags + b"\n```\n"
        first = self.scan(tag_dense)
        self.assertEqual(first["tags"]["recognized_lines"], 2_000)
        self.assertEqual(first, self.scan(tag_dense))


@unittest.skipIf(source_doctor is None, "source doctor not present")
class SourceDoctorEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (ROOT / "docs/64_games.md").read_bytes()
        cls.locked = source_doctor.load_source_lock(ROOT)
        cls.report_bytes = (ROOT / "reports/source-doctor.json").read_bytes()
        cls.report = json.loads(cls.report_bytes)

    def test_checked_report_is_exact_deterministic_and_lexical_only(self) -> None:
        self.assertEqual(source_doctor.generate_report_bytes(self.source, self.locked), self.report_bytes)
        canonical_manifest.validate_canonical_manifest(self.report_bytes)
        self.assertEqual(set(self.report), {
            "blocks", "duplicate_candidates", "fences", "movetext", "schema",
            "scope", "source", "tags"
        })
        self.assertEqual(set(self.report["source"]), {
            "bom", "expected_bytes", "expected_sha256", "file_kind", "final_lf",
            "line_endings", "lock_match", "nfc_state", "observed_bytes",
            "observed_sha256", "path", "symlink", "tab_count",
            "trailing_horizontal_whitespace", "unexpected_controls", "utf8_valid"
        })
        self.assertEqual(set(self.report["fences"]), {
            "candidate_count", "near_misses", "nested_openers", "orphan_closers",
            "recognized_closers", "recognized_openers", "unclosed_openers"
        })
        self.assertEqual(set(self.report["tags"]), {
            "duplicate_blocks", "escape_counts", "malformed_lines", "name_stats",
            "orders", "punctuation", "recognized_lines", "separator_states",
            "special_name_counts"
        })
        self.assertEqual(set(self.report["movetext"]), {
            "constructs", "feature_counts", "final_slot_counts", "line_wrap",
            "move_numbers", "primary_counts", "ranges", "result_agreement_counts",
            "result_counts", "token_bytes", "total_tokens", "unknown_tokens"
        })
        block_keys = {
            "closer_line", "content_span", "fence_span", "lexical_final_slot",
            "lexical_ply_count", "movetext_lines", "movetext_span", "opener_line",
            "ordinal", "raw_movetext_sha256", "result_agreement", "separator_span",
            "separator_state", "tag_count", "tag_span", "token_count",
            "token_projection_sha256"
        }
        for ordinal, block in enumerate(self.report["blocks"], 1):
            self.assertEqual(set(block), block_keys)
            self.assertEqual(block["ordinal"], ordinal)
            fence_start, fence_end = block["fence_span"]
            content_start, content_end = block["content_span"]
            self.assertLessEqual(fence_start, content_start)
            self.assertLessEqual(content_end, fence_end)
            self.assertEqual(len(self.source[fence_start:fence_end]), fence_end - fence_start)
            for name in ("tag_span", "separator_span", "movetext_span"):
                span = block[name]
                self.assertIn(len(span), (0, 2))
                if span:
                    self.assertLessEqual(content_start, span[0])
                    self.assertLessEqual(span[1], content_end)
        report_text = self.report_bytes.decode("utf-8")
        for forbidden in ("canonical_game", "chess_legal", "resolved_move", "position_fen", "semantic_identity"):
            self.assertNotIn(forbidden, report_text)

    def test_current_facts_match_the_reviewed_reconnaissance(self) -> None:
        self.assertEqual(self.report["source"]["observed_bytes"], 165_145)
        self.assertEqual(self.report["source"]["line_endings"], {"bare_cr": 0, "crlf": 0, "lf": 4_376})
        self.assertTrue(self.report["source"]["lock_match"])
        self.assertEqual(self.report["fences"]["candidate_count"], 64)
        self.assertEqual(self.report["tags"]["recognized_lines"], 895)
        self.assertEqual(len(self.report["tags"]["orders"]), 7)
        self.assertEqual(self.report["movetext"]["total_tokens"], 7_456)
        primary = self.report["movetext"]["primary_counts"]
        self.assertEqual(sum(primary[name] for name in ("castle", "piece", "pawn_capture", "pawn_quiet")), 4_915)
        self.assertEqual(self.report["duplicate_candidates"], {"raw_movetext": [], "token_sequence": []})
        self.assertEqual(
            [(item["region"], item["count"]) for item in self.report["source"]["trailing_horizontal_whitespace"]],
            [("outer_markdown", 192), ("fence", 0), ("tags", 0), ("separator", 0), ("movetext", 0)],
        )

    def run_doctor(self, cwd: Path) -> subprocess.CompletedProcess[bytes]:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "python")
        return subprocess.run(
            [sys.executable, "-m", "golden_board.source_doctor"],
            cwd=cwd,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def make_checkout(self, root: Path, data: bytes, lock_matches: bool) -> None:
        (root / "docs").mkdir()
        (root / "inputs").mkdir()
        (root / "docs/64_games.md").write_bytes(data)
        lock = (ROOT / "inputs/source-lock.toml").read_bytes()
        if lock_matches:
            lock = lock.replace(b"bytes = 165145", f"bytes = {len(data)}".encode(), 1)
            lock = lock.replace(
                b"33d44f7167ab190cc793e3fdfd8190d89ed13c1dc507c20854cf64751c7be7da",
                hashlib.sha256(data).hexdigest().encode(),
                1,
            )
        (root / "inputs/source-lock.toml").write_bytes(lock)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)

    def test_command_from_root_nested_and_failure_modes(self) -> None:
        before = hashlib.sha256(self.source).digest()
        for cwd in (ROOT, ROOT / "docs"):
            result = self.run_doctor(cwd)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, self.report_bytes)
        self.assertEqual(hashlib.sha256((ROOT / "docs/64_games.md").read_bytes()).digest(), before)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            changed = b"X" + self.source[1:]
            self.make_checkout(root, changed, lock_matches=False)
            mismatch = self.run_doctor(root)
            self.assertEqual(mismatch.returncode, 1)
            self.assertFalse(json.loads(mismatch.stdout)["source"]["lock_match"])
            (root / "docs/64_games.md").unlink()
            unsafe = self.run_doctor(root)
            self.assertEqual(unsafe.returncode, 1)
            self.assertEqual(unsafe.stdout, b"")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            near_miss = b"```PGN\n" + self.source
            self.make_checkout(root, near_miss, lock_matches=True)
            result = self.run_doctor(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["fences"]["near_misses"]["count"], 1)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dense = b"```pgn\n\n```\n" * 60_000
            self.make_checkout(root, dense, lock_matches=True)
            result = self.run_doctor(root)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, source_doctor.REPORT_LIMIT_BYTES)


@unittest.skipIf(source_doctor is None, "source doctor not present")
class SourceDoctorFast(unittest.TestCase):
    def test_locked_current_source_is_gate_clean(self) -> None:
        locked = source_doctor.load_source_lock(ROOT)
        opened = source_doctor.read_locked_source(ROOT, locked)
        self.assertTrue(opened.lock_match)
        self.assertTrue(source_doctor._gate_passes(source_doctor.scan_source(opened.data, locked)))


class RepoContract(unittest.TestCase):
    REQUIRED = [
        ".gitignore", ".python-version", "AGENTS.md", "Cargo.lock", "Cargo.toml",
        "README.md", "conformance/chess-v0.json", "conformance/content-v0.json", "conformance/identity-v0.json",
        "conformance/manifest-v0.json", "conformance/source-v0.json",
        "conformance/registry.toml", "crates/gb-foundation/Cargo.toml",
        "crates/gb-foundation/src/constants.rs", "crates/gb-foundation/src/lib.rs",
        "crates/gb-foundation/tests/conformance.rs",
        "crates/gb-chess/Cargo.toml", "crates/gb-chess/src/lib.rs",
        "crates/gb-chess/src/source.rs", "crates/gb-chess/tests/chess.rs",
        "crates/gb-chess/tests/source.rs", "crates/gb-content/Cargo.toml",
        "crates/gb-content/src/lib.rs", "crates/gb-content/tests/content.rs",
        "docs/64_games.md", "docs/m0-plan.md", "docs/m0-spec.md", "docs/roadmap.md",
        "docs/m1-plan.md", "docs/m1-spec.md", "docs/sources.md", "inputs/source-lock.toml", "pyproject.toml",
        "python/golden_board/__init__.py", "python/golden_board/canonical_manifest.py",
        "python/golden_board/constants.py", "python/golden_board/constants_codegen.py",
        "python/golden_board/chess.py", "python/golden_board/content.py",
        "python/golden_board/curriculum.py", "python/golden_board/identity.py",
        "python/golden_board/source_compiler.py", "python/golden_board/source_doctor.py",
        "python/tests/test_chess.py", "python/tests/test_chess_oracle.py",
        "python/tests/test_constants.py", "python/tests/test_content.py",
        "python/tests/test_curriculum.py", "python/tests/test_curriculum_contract.py",
        "python/tests/test_foundation.py", "python/tests/test_source_compiler.py",
        "reports/game-set-v0.bin", "reports/source-compilation-v0.json",
        "reports/source-doctor.json",
        "rust-toolchain.toml", "scripts/check", "spec/chess-v0.md",
        "spec/constants-v0.toml", "spec/content-v0.md", "spec/curriculum-v0.toml", "spec/identity-v0.md",
        "spec/source-v0.md", "uv.lock",
    ]

    def tracked(self) -> dict[str, str]:
        output = subprocess.run(
            ["git", "ls-files", "--stage", "--", *self.REQUIRED],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        ).stdout
        return {line.split("\t", 1)[1]: line.split()[0] for line in output.splitlines()}

    def test_required_surface_is_nonempty_tracked_and_not_premature(self) -> None:
        tracked = self.tracked()
        self.assertEqual(set(tracked), set(self.REQUIRED))
        for relative in self.REQUIRED:
            self.assertGreater((ROOT / relative).stat().st_size, 0, relative)
        self.assertEqual(tracked["scripts/check"], "100755")
        self.assertTrue(os.access(ROOT / "scripts/check", os.X_OK))

        all_tracked = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, check=True, stdout=subprocess.PIPE, text=True
        ).stdout.splitlines()
        forbidden_exact = {".dockerignore", "Dockerfile", "docs/decisions.md", "flake.nix"}
        forbidden_prefixes = (".github/workflows/", "release/", "schemas/", "tools/linux/")
        self.assertFalse(forbidden_exact.intersection(all_tracked))
        self.assertFalse([path for path in all_tracked if path.startswith(forbidden_prefixes)])

    def test_text_registry_links_and_status_are_consistent(self) -> None:
        output = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
        for relative in [
            *(os.fsencode(path) for path in self.REQUIRED),
            *(path for path in output.split(b"\0") if path),
        ]:
            if relative in {b"docs/64_games.md", b"reports/game-set-v0.bin"}:
                continue
            data = repo_text_bytes(ROOT, relative)
            self.assertNotIn(b"\r", data, relative)
            self.assertTrue(data.endswith(b"\n"), relative)
            for line in data.splitlines():
                self.assertFalse(line.endswith((b" ", b"\t")), relative)
                self.assertFalse(line.startswith((b"<<<<<<<", b"=======", b">>>>>>>")), relative)

        validate_conformance_registry(ROOT)

        readme = (ROOT / "README.md").read_text()
        agents = (ROOT / "AGENTS.md").read_text()
        for command in (
            "scripts/check fast", "scripts/check focused source",
            "scripts/check focused identity", "scripts/check focused chess",
            "scripts/check focused curriculum", "scripts/check focused content",
            "scripts/check focused repo",
            "scripts/check full",
        ):
            self.assertIn(command, readme)
            self.assertIn(command, agents)
        self.assertLessEqual(len(agents.splitlines()), 80)

        roadmap = (ROOT / "docs/roadmap.md").read_text()
        header_state = re.search(r"^\| Project state \| (.+) \|$", roadmap, re.MULTILINE).group(1)
        header_milestone = re.search(r"^\| Current milestone \| (.+) \|$", roadmap, re.MULTILINE).group(1)
        rows = re.findall(r"^\| (M[0-6] — [^|]+) \| ([^|]+) \|", roadmap, re.MULTILINE)
        current = next(((name, status.strip()) for name, status in rows if not status.strip().startswith("Complete")), None)
        if current is None:
            expected_state, expected_milestone = "Complete", "Completed project"
        else:
            expected_milestone = current[0]
            leading = current[1].split(" — ", 1)[0]
            if all(status.strip() == "Not started" for _, status in rows):
                expected_state = "Not started"
            elif leading == "Not started":
                expected_state = "In progress"
            else:
                expected_state = leading
        self.assertEqual(header_state, expected_state)
        self.assertEqual(header_milestone, expected_milestone)

    def test_chess_fixture_is_registered(self) -> None:
        registry = tomllib.loads((ROOT / "conformance/registry.toml").read_text())
        rows = [row for row in registry["suite"] if row["id"] == "chess-v0"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0],
            {
                "consumers": ["python", "rust"],
                "id": "chess-v0",
                "path": "conformance/chess-v0.json",
                "provenance": "hand-authored",
                "sha256": "9a63aa74a32761bf1f8919278e895f532e4d4f305a30f74ddd1d0c4acec6a639",
                "specification": "chess-v0",
                "version": "v0",
            },
        )

    def test_source_fixture_is_registered(self) -> None:
        registry = tomllib.loads((ROOT / "conformance/registry.toml").read_text())
        rows = [row for row in registry["suite"] if row["id"] == "source-v0"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0],
            {
                "consumers": ["python", "rust"],
                "id": "source-v0",
                "path": "conformance/source-v0.json",
                "provenance": "hand-authored",
                "sha256": "07c36421b2b27aa3b9ab4609f34b6f0d24d63bac9752e0c083747cb90e0f8b30",
                "specification": "source-v0",
                "version": "v0",
            },
        )

    def test_content_fixture_is_registered_and_closed(self) -> None:
        registry = tomllib.loads((ROOT / "conformance/registry.toml").read_text())
        rows = [row for row in registry["suite"] if row["id"] == "content-v0"]
        payload_bytes = repo_text_bytes(ROOT, b"conformance/content-v0.json")
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0],
            {
                "consumers": ["python", "rust"],
                "id": "content-v0",
                "path": "conformance/content-v0.json",
                "provenance": "hand-authored",
                "sha256": "b3f4279e95854e77bd3ce25c05e8580b1298ffccc164ac40a6010e86091a038b",
                "specification": "content-v0",
                "version": "v0",
            },
        )
        self.assertEqual(
            hashlib.sha256(payload_bytes).hexdigest(),
            "b3f4279e95854e77bd3ce25c05e8580b1298ffccc164ac40a6010e86091a038b",
        )

        payload = canonical_manifest.validate_canonical_manifest(payload_bytes)
        validate_content_fixture_contract(payload)
        self.assertEqual(set(payload), {"bases", "cases", "recipes", "schema"})
        self.assertEqual(payload["schema"], "golden-board.content-v0-fixtures/v0")
        self.assertEqual(len(payload["bases"]), 1)
        base = payload["bases"][0]
        self.assertEqual(
            set(base),
            {"name", "projection", "stream_hex", "stream_length", "stream_sha256"},
        )
        stream = bytes.fromhex(base["stream_hex"])
        self.assertEqual(base["name"], "generic-base")
        self.assertEqual(base["stream_length"], len(stream))
        self.assertEqual(base["stream_sha256"], hashlib.sha256(stream).hexdigest())
        self.assertEqual(
            {record["kind"] for record in base["projection"]["records"]},
            {
                "ATOM_SCHEMA", "ATOM_VECTOR", "FEEDBACK", "FIELD_SCHEMA",
                "LESSON_NODE", "MATRIX", "OPAQUE_DATA", "PASSIVE_TRACE",
                "PREDICATE_RESULT", "REGION_SET", "ROOT", "SEMANTIC_BINDING",
                "TEXT", "TUPLE",
            },
        )
        projection = base["projection"]
        self.assertEqual(set(projection), {"records", "root_record_id", "version"})
        self.assertEqual(projection["version"], 0)
        self.assertEqual(projection["root_record_id"], 29)
        self.assertEqual(
            [record["record_id"] for record in projection["records"]],
            list(range(1, 30)),
        )
        record_keys = {
            "ATOM_VECTOR": {"atom_count", "atom_schema_ref", "atoms"},
            "FEEDBACK": {"display_ref", "feedback_code", "predicate_result_ref"},
            "FIELD_SCHEMA": {"field_count", "fields"},
            "LESSON_NODE": {
                "answer_mode", "case_count", "cases", "default_feedback_ref",
                "default_next_node_ref", "flags", "item_event_budget",
                "max_selections", "passive_trace_ref", "predicate_result_ref",
                "presentation_ref", "region_set_ref", "response_shape", "role",
            },
            "MATRIX": {"atom_schema_ref", "cells", "columns", "rows"},
            "OPAQUE_DATA": {"data", "data_binding_ref"},
            "PASSIVE_TRACE": {
                "action_count", "actions", "expected_feedback_ref",
                "expected_next_node_ref", "expected_outcome", "limitation_text_ref",
                "presentation_ref", "region_set_ref", "resulting_presentation_ref",
            },
            "PREDICATE_RESULT": {
                "predicate_binding_ref", "result_atom_vector_ref",
                "subject_opaque_data_ref",
            },
            "REGION_SET": {"region_count", "regions", "surface_matrix_ref"},
            "ROOT": {"entry_node_ref", "global_event_budget"},
            "SEMANTIC_BINDING": {
                "argument", "auxiliary", "binding_class", "namespace_id",
                "semantic_code",
            },
            "TEXT": {"text"},
            "TUPLE": {"field_schema_ref", "field_values"},
        }
        for record in projection["records"]:
            expected = record_keys.get(record["kind"])
            if record["kind"] == "ATOM_SCHEMA":
                expected = {
                    1: {"atom_class", "atom_width", "entry_count", "max_value", "min_value"},
                    2: {"atom_class", "atom_width", "entries", "entry_count"},
                    3: {
                        "allowed_mask", "atom_class", "atom_width", "entries",
                        "entry_count",
                    },
                }[record["atom_class"]]
            self.assertEqual(set(record), {"kind", "record_id", *expected})

        for field in projection["records"][12]["fields"]:
            self.assertEqual(set(field), {"count", "name_text_ref", "storage", "type"})
        for region in projection["records"][14]["regions"]:
            self.assertEqual(
                set(region),
                {
                    "column_end", "column_start", "flags", "label_ref", "region_id",
                    "row_end", "row_start",
                },
            )
        for node in projection["records"][25:28]:
            for case in node["cases"]:
                self.assertEqual(
                    set(case),
                    {
                        "case_class", "feedback_ref", "next_node_ref", "region_ids",
                        "selection_count",
                    },
                )

        rows = [*payload["cases"], *payload["recipes"]]
        self.assertEqual((len(payload["cases"]), len(payload["recipes"])), (55, 173))
        names = [row["name"] for row in rows]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) for name in names))
        for case in payload["cases"]:
            self.assertEqual(set(case), {"covers", "expected", "input", "name", "operation"})
        for recipe in payload["recipes"]:
            self.assertEqual(
                set(recipe),
                {
                    "count_cap", "covers", "expected", "input", "input_bytes",
                    "input_sha256", "name", "operation", "recipe",
                },
            )
            self.assertIs(type(recipe["count_cap"]), int)
            self.assertGreater(recipe["count_cap"], 0)
            self.assertIs(type(recipe["input_bytes"]), int)
            self.assertGreaterEqual(recipe["input_bytes"], 0)
            self.assertLessEqual(recipe["input_bytes"], MAX_REPO_TEXT_BYTES + 1)
            self.assertRegex(recipe["input_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            {recipe["recipe"] for recipe in payload["recipes"]},
            {
                "cases-per-node-boundary", "control-edge-boundary",
                "enum-entries-boundary", "field-schema-fields-boundary",
                "lesson-nodes-boundary", "matrix-cells-boundary",
                "maximum-committed-state", "maximum-exhausted-state",
                "maximum-selection-cap-over", "maximum-state-byte-over",
                "maximum-support-stream",
                "opaque-atoms-boundary", "patch-base", "per-kind-records-boundary",
                "record-count-boundary", "record-id-boundary",
                "record-payload-bytes-boundary",
                "regions-boundary", "stream-byte-cap", "stream-bytes-boundary",
                "text-bytes-boundary", "tuple-slots-boundary",
                "typed-step-sequence", "vector-atoms-boundary",
            },
        )
        for row in rows:
            self.assertIs(type(row["covers"]), list)
            self.assertEqual(len(row["covers"]), len(set(row["covers"])))
            self.assertTrue(all(type(label) is str for label in row["covers"]))
            self.assertEqual(len(row["expected"]), 1)
            if "rejection" in row["expected"]:
                self.assertEqual(
                    set(row["expected"]["rejection"]),
                    {"code", "raw_end", "raw_start"},
                )
            if "invalid_host_state" in row["expected"]:
                self.assertEqual(row["expected"]["invalid_host_state"], {})
        self.assertEqual(
            {row["operation"] for row in payload["cases"]},
            {
                "advance_committed", "new_run", "step", "stream_validation",
                "validate_run_state",
            },
        )
        self.assertEqual(
            {
                row["expected"]["rejection"]["code"]
                for row in rows
                if "rejection" in row["expected"]
            },
            set(range(1, 32)),
        )
        self.assertEqual(
            {
                row["expected"]["success"]["interaction_result"]
                for row in payload["cases"]
                if "success" in row["expected"]
                and "interaction_result" in row["expected"]["success"]
            },
            set(range(1, 10)),
        )
        coverage = {label for row in rows for label in row["covers"]}
        self.assertTrue(
            {
                "all-record-kinds", "all-reject-codes", "all-response-shapes",
                "all-answer-modes", "all-feedback", "all-outcomes",
                "all-runtime-results", "full-width-u16", "maximum-committed-state",
                "maximum-exhausted-state", "nested-shape-closure", "precedence",
            }.issubset(coverage)
        )

    def test_content_fixture_shape_mutations_fail_closed(self) -> None:
        payload = canonical_manifest.validate_canonical_manifest(
            CONTENT_FIXTURE.read_bytes()
        )

        def nested_type(value: dict[str, object]) -> None:
            value["bases"][0]["projection"]["records"][5]["entry_count"] = "0"

        def extra_patch_key(value: dict[str, object]) -> None:
            recipe = next(row for row in value["recipes"] if row["recipe"] == "patch-base")
            recipe["input"]["patches"][0]["extra"] = 1

        def swapped_operation(value: dict[str, object]) -> None:
            first, second = value["cases"][:2]
            first["operation"], second["operation"] = second["operation"], first["operation"]

        def bad_old_bytes(value: dict[str, object]) -> None:
            recipe = next(row for row in value["recipes"] if row["recipe"] == "patch-base")
            recipe["input"]["patches"][0]["old_hex"] = "ffff"

        def bad_digest(value: dict[str, object]) -> None:
            value["recipes"][0]["input_sha256"] = "0" * 64

        def bad_cap(value: dict[str, object]) -> None:
            recipe = next(
                row for row in value["recipes"]
                if row["name"] == "control-edges-plus-one"
            )
            recipe["count_cap"] = 1

        def bad_hex(value: dict[str, object]) -> None:
            recipe = next(row for row in value["recipes"] if row["recipe"] == "patch-base")
            recipe["input"]["patches"][0]["new_hex"] = "0"

        def bad_patch_order(value: dict[str, object]) -> None:
            recipe = next(
                row for row in value["recipes"]
                if row["recipe"] == "patch-base" and len(row["input"]["patches"]) > 1
            )
            recipe["input"]["patches"].reverse()

        def extra_success_key(value: dict[str, object]) -> None:
            value["cases"][0]["expected"]["success"]["extra"] = 1

        def unknown_name(value: dict[str, object]) -> None:
            value["recipes"][0]["name"] = "unknown-content-recipe"

        def unknown_recipe(value: dict[str, object]) -> None:
            value["recipes"][0]["recipe"] = "unknown-content-builder"

        def bad_support_receipt(value: dict[str, object]) -> None:
            recipe = next(
                row for row in value["recipes"]
                if row["name"] == "maximum-committed-run-state"
            )
            recipe["input"]["support_stream_sha256"] = "0" * 64

        def wrapped_operation_count(value: dict[str, object]) -> None:
            recipe = next(
                row for row in value["recipes"]
                if row["name"] == "typed-step-65536-does-not-wrap"
            )
            recipe["input"]["operation_count"] = 0

        def unknown_boundary(value: dict[str, object]) -> None:
            recipe = next(
                row for row in value["recipes"]
                if row["name"] == "vector-atoms-exact"
            )
            recipe["input"]["boundary"] = "unknown"

        def non_string_coverage(value: dict[str, object]) -> None:
            recipe = next(row for row in value["recipes"] if not row["covers"])
            recipe["covers"] = [1]

        def inflated_cap(value: dict[str, object]) -> None:
            recipe = next(
                row for row in value["recipes"]
                if row["name"] == "enum-entries-exact"
            )
            recipe["count_cap"] = MAX_REPO_TEXT_BYTES + 1

        for name, mutate in {
            "nested type": nested_type,
            "extra patch key": extra_patch_key,
            "swapped operation": swapped_operation,
            "bad patch old bytes": bad_old_bytes,
            "bad constructed digest": bad_digest,
            "bad recipe cap": bad_cap,
            "bad patch hex": bad_hex,
            "bad patch order": bad_patch_order,
            "extra success key": extra_success_key,
            "unknown name": unknown_name,
            "unknown recipe": unknown_recipe,
            "bad support receipt": bad_support_receipt,
            "wrapped operation count": wrapped_operation_count,
            "unknown symbolic boundary": unknown_boundary,
            "non-string recipe coverage": non_string_coverage,
            "inflated exact cap": inflated_cap,
        }.items():
            with self.subTest(name=name):
                mutated = copy.deepcopy(payload)
                mutate(mutated)
                with self.assertRaises(AssertionError):
                    validate_content_fixture_contract(mutated)

    def test_content_fixture_semantic_review_regressions_are_frozen(self) -> None:
        payload = canonical_manifest.validate_canonical_manifest(
            CONTENT_FIXTURE.read_bytes()
        )
        rows = {row["name"]: row for row in [*payload["cases"], *payload["recipes"]]}
        rejections = {
            "matrix-schema-missing": (19, 154, 156),
            "matrix-schema-self-reference": (18, 167, 169),
            "tuple-slot-missing": (19, 211, 213),
            "tuple-slot-self-reference": (18, 224, 226),
            "repeat-flag-single-forbidden": (26, 456, 457),
            "repeat-flag-set-forbidden": (26, 514, 515),
            "single-case-cardinality-two": (26, 491, 493),
            "packed-case-over-selection-cap": (26, 491, 493),
            "packed-case-absent-region": (26, 493, 495),
            "packed-case-nonselectable-region": (26, 493, 495),
            "sequence-case-repeat-forbidden": (26, 495, 497),
            "packed-no-accepted-case": (26, 469, 471),
            "match-feedback-missing-predicate": (28, 373, 375),
            "no-match-feedback-missing-predicate": (28, 387, 389),
            "alternative-feedback-missing-predicate": (28, 401, 403),
            "limitation-feedback-with-predicate": (28, 415, 417),
            "packed-default-feedback-mismatch": (28, 499, 501),
            "packed-special-feedback-mismatch": (28, 495, 497),
            "heuristic-default-feedback-mismatch": (28, 559, 561),
            "external-default-feedback-mismatch": (28, 529, 531),
            "passive-region-set-owner-mismatch": (29, 154, 156),
            "passive-action-count-exceeds-budget": (29, 433, 435),
            "passive-prefinal-action-result-mismatch": (29, 435, 439),
            "passive-expected-feedback-mismatch": (29, 441, 443),
            "passive-expected-next-node-mismatch": (29, 443, 445),
            "record-id-65535-exact": (20, 21, 23),
            "record-payload-bytes-exact": (2, 12, 12),
            "region-label-wrong-kind": (20, 246, 248),
        }
        for name, (code, raw_start, raw_end) in rejections.items():
            with self.subTest(name=name):
                self.assertEqual(
                    rows[name]["expected"],
                    {"rejection": {
                        "code": code,
                        "raw_end": raw_end,
                        "raw_start": raw_start,
                    }},
                )

        region_wrong_kind = rows["region-label-wrong-kind"]
        self.assertEqual(
            region_wrong_kind["input"]["patches"],
            [{"new_hex": "000d", "old_hex": "0001", "start": 246}],
        )
        self.assertEqual(
            _content_recipe_bytes(payload, region_wrong_kind)[246:248], b"\0\r"
        )
        payload_boundary = rows["record-payload-bytes-exact"]
        self.assertEqual(
            _content_recipe_bytes(payload, payload_boundary)[6:8], b"\0\x03"
        )
        payload_excess = rows["record-payload-bytes-plus-one"]
        self.assertEqual(
            _content_recipe_bytes(payload, payload_excess)[6:8], b"\0\x03"
        )

        self.assertEqual(len(payload["recipes"]), 173)
        self.assertFalse({
            "typed-record-65536-rejects-without-wrap",
            "typed-vector-atom-65536-rejects-without-wrap",
        }.intersection(rows))

    def test_source_fixture_semantic_review_regressions_are_frozen(self) -> None:
        payload = canonical_manifest.validate_canonical_manifest(
            repo_text_bytes(ROOT, b"conformance/source-v0.json")
        )
        rows = {
            row["name"]: row
            for key in ("cases", "recipes")
            for row in payload[key]
        }

        with self.subTest(finding="raw game count, not forged typed encoder input"):
            self.assertFalse("binary-game-typed-4097" in rows)
            name = "binary-game-count-4097"
            self.assertIn(name, rows)
            if name in rows:
                self.assertEqual(
                    rows[name],
                    {
                        "count_cap": 1,
                        "expected": {
                            "rejection": {"code": 49, "raw_end": 2, "raw_start": 0}
                        },
                        "input": {
                            "prefix_hex": "",
                            "repeat_count": 1,
                            "repeat_hex": "1001",
                            "suffix_hex": "",
                        },
                        "input_bytes": 2,
                        "input_sha256": (
                            "27c24fcb8474773e2af799d0848495ff053272d33c432dc26277993df45c9276"
                        ),
                        "name": name,
                        "operation": "decode_game",
                        "recipe": "literal-repeat",
                    },
                )

        cycle = "1950fad05460b7e0"
        for name, expected_hash in (
            (
                "binary-game-set-total-plies-65535",
                "b9ed9c501fba4549cb8f5f2803ca3583999eb1bbd6631b51e5321bf909ec7798",
            ),
            (
                "binary-game-set-total-plies-65536",
                "4534aa261bf8f36534ec0faf68f3984716e5881f40dd3ccb80f84f9142e6f3ce",
            ),
        ):
            with self.subTest(finding="legal typed game-set cycle", name=name):
                self.assertEqual(rows[name]["input"].get("cycle_moves_hex"), cycle)
                self.assertNotIn("move_hex", rows[name]["input"])
                self.assertEqual(rows[name]["input_sha256"], expected_hash)

        source_lock = tomllib.loads((ROOT / "inputs/source-lock.toml").read_text())
        receipt = next(row for row in source_lock["source"] if row["id"] == "anthology")
        base = repo_text_bytes(ROOT, receipt["path"].encode("ascii"))

        def expanded(name: str) -> bytes:
            recipe = rows[name]
            patches = recipe["input"]["patches"]
            self.assertLessEqual(len(patches), recipe["patch_cap"])
            value = bytearray(base)
            for patch in patches:
                start = patch["start"]
                old = bytes.fromhex(patch["old_hex"])
                replacement = bytes.fromhex(patch["replacement_hex"])
                self.assertEqual(value[start:start + len(old)], old)
                value[start:start + len(old)] = replacement
            self.assertLessEqual(len(value), MAX_REPO_TEXT_BYTES + 1)
            return bytes(value)

        with self.subTest(finding="missing capture token span"):
            raw = expanded("san-noncanonical-missing-capture")
            rejection = rows["san-noncanonical-missing-capture"]["expected"]["rejection"]
            self.assertEqual(rejection, {"code": 45, "raw_end": 12413, "raw_start": 12411})
            self.assertEqual(raw[12405:12407], b"d5")
            self.assertEqual(raw[12408:12413], b"2. d5")

        terminal_rows = {
            "terminal-score-checkmate": (
                164274,
                "b2fe08f4dc7d76e66ebcda1497db8d1777c533d435efd26e49d9fad45723f732",
                {"code": 47, "raw_end": 12422, "raw_start": 12419},
                None,
            ),
            "terminal-after-stalemate": (
                164375,
                "dfde2615e14afde446b24436dd575d6406a1d2210458438b0fd6684bdf126f7c",
                {"code": 41, "raw_end": 12515, "raw_start": 12513},
                (12459, b"Qxd7+"),
            ),
            "terminal-score-stalemate": (
                164364,
                "f97fe97cdf517783cd2383d4d84494aa4a0bb0338a0ed0933f685ed953d3f34d",
                {"code": 47, "raw_end": 12512, "raw_start": 12509},
                (12455, b"Qxd7+"),
            ),
            "terminal-after-common-dead": (
                164488,
                "f6afec6817e55db9f411cc806ae031bf18909f7f1b406afa0e661dfd72b3d3d3",
                {"code": 41, "raw_end": 12628, "raw_start": 12625},
                (12597, b"Rxf2"),
            ),
            "terminal-score-common-dead": (
                164476,
                "75a07e38155b5e6e9bb0957e3cca3a1abb2556dc4e4eae92d7fa7859cc5ef1cd",
                {"code": 47, "raw_end": 12624, "raw_start": 12621},
                (12593, b"Rxf2"),
            ),
        }
        for name, (length, digest, rejection, capture) in terminal_rows.items():
            with self.subTest(finding="terminal capture and marker", name=name):
                raw = expanded(name)
                self.assertEqual(len(raw), length)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)
                self.assertEqual(rows[name]["input_bytes"], length)
                self.assertEqual(rows[name]["input_sha256"], digest)
                self.assertEqual(rows[name]["expected"]["rejection"], rejection)
                if capture is not None:
                    start, token = capture
                    self.assertEqual(raw[start:start + len(token)], token)
                if rejection["code"] == 47:
                    self.assertEqual(raw[12392:12395], b"1-0")
                    self.assertNotEqual(rejection["raw_start"], 12392)
                    self.assertEqual(
                        raw[rejection["raw_start"]:rejection["raw_end"]], b"1-0"
                    )

    def test_source_fixture_shape_and_coverage_are_closed(self) -> None:
        payload = canonical_manifest.validate_canonical_manifest(
            repo_text_bytes(ROOT, b"conformance/source-v0.json")
        )
        self.assertEqual(set(payload), {"bases", "cases", "recipes", "schema"})
        self.assertEqual(payload["schema"], "golden-board.source-v0-fixtures/v0")
        self.assertEqual(
            payload["bases"],
            [{"id": "locked-anthology", "source_lock_id": "anthology"}],
        )
        self.assertEqual(len(payload["cases"]), 71)
        self.assertEqual(len(payload["recipes"]), 115)
        names = [row["name"] for key in ("cases", "recipes") for row in payload[key]]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(
            all(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) for name in names)
        )
        expected_names = set(
            """
            raw-utf8-bom raw-utf8-invalid-lead raw-utf8-unexpected-continuation
            raw-utf8-overlong raw-utf8-surrogate raw-utf8-out-of-range raw-utf8-truncated
            raw-valid-multibyte-prefix raw-control-00 raw-control-01 raw-control-02
            raw-control-03 raw-control-04 raw-control-05 raw-control-06 raw-control-07
            raw-control-08 raw-control-0b raw-control-0c raw-control-0e raw-control-0f
            raw-control-10 raw-control-11 raw-control-12 raw-control-13 raw-control-14
            raw-control-15 raw-control-16 raw-control-17 raw-control-18 raw-control-19
            raw-control-1a raw-control-1b raw-control-1c raw-control-1d raw-control-1e
            raw-control-1f raw-control-7f raw-newline-bare-cr raw-newline-mixed-lf-then-crlf
            raw-newline-mixed-crlf-then-lf raw-newline-final-missing fence-shape-uppercase
            fence-shape-four-backticks fence-shape-suffix fence-shape-indented
            fence-orphan-close fence-nested-open fence-unclosed binary-game-count-zero
            binary-game-count-one binary-game-truncated-header binary-game-truncated-body
            binary-game-move binary-game-score binary-game-trailing binary-game-semantic-move
            binary-game-semantic-score binary-game-fools-mate binary-game-set-count-zero
            binary-game-set-count-one binary-game-set-truncated-header
            binary-game-set-truncated-game binary-game-set-order binary-game-set-duplicate
            binary-game-set-trailing evidence-shape-malformed evidence-shape-extra-key
            evidence-noncanonical evidence-hash evidence-cross-field raw-input-too-large
            fence-block-bytes-excess fence-unclosed-precedes-size-and-count fence-count-63
            fence-count-65 raw-input-max-reaches-fence-count tag-count-64-boundary tag-count-65
            tag-name-32-boundary tag-name-33 tag-value-1024-boundary tag-value-1025
            tag-syntax-missing-space tag-syntax-bad-name tag-syntax-trailing-space
            tag-escape-invalid tag-escape-terminal-backslash tag-duplicate-decoded-name
            tag-forbidden-setup tag-forbidden-fen tag-forbidden-variant tag-result-missing
            tag-result-value-2a tag-result-value-312f32 tag-result-value-30
            tag-result-value-312d31 framing-separator-missing framing-separator-extra
            framing-movetext-missing framing-movetext-empty-line framing-movetext-tag-line
            framing-movetext-leading-hws framing-movetext-trailing-hws framing-movetext-hws-only
            resource-token-count-8192 resource-token-count-8193 resource-record-plies-4096
            resource-record-plies-4097 structure-move-number-shape
            structure-move-number-value-30312e structure-move-number-value-302e
            structure-move-number-value-343239343936373239362e structure-move-number-value-322e
            structure-move-number-position structure-position-precedes-value-at-same-token
            structure-result-too-early-first structure-result-too-early-after-number
            structure-result-star structure-result-missing structure-result-mismatch
            structure-token-after-result terminal-after-checkmate
            terminal-continuation-precedes-earlier-suffix san-shape-piece-case
            san-shape-zero-castle san-shape-ep-suffix san-shape-double-check san-shape-lan
            san-shape-annotation san-no-match-pawn san-no-match-capture san-ambiguous-knight
            san-noncanonical-redundant-file san-noncanonical-redundant-rank
            san-noncanonical-redundant-square san-noncanonical-missing-capture
            san-noncanonical-extra-capture san-noncanonical-precedes-suffix
            san-suffix-extra-check san-suffix-missing-check san-suffix-wrong-mate
            san-suffix-missing-mate terminal-score-checkmate terminal-after-stalemate
            terminal-score-stalemate terminal-after-common-dead terminal-score-common-dead
            accept-san-no-check accept-san-zero-disambiguation accept-san-check accept-san-mate
            accept-san-castles accept-san-queenside-castles accept-san-en-passant
            accept-san-file-disambiguation accept-san-promotion-q accept-san-promotion-r
            accept-san-promotion-b accept-san-promotion-n san-shape-promotion-missing
            san-shape-promotion-unneeded accept-san-rank-disambiguation
            accept-san-full-square-disambiguation accept-san-pinned-pseudo-mover-excluded
            accept-opaque-tag duplicate-move-stream-same-score
            duplicate-move-stream-different-score binary-game-count-4096 binary-game-set-size
            binary-game-set-size-boundary binary-game-count-4097 binary-game-set-count-65535
            binary-game-set-count-65536 binary-game-set-total-plies-65535
            binary-game-set-total-plies-65536 binary-anthology-count-63
            binary-anthology-count-64 binary-anthology-count-65
            binary-anthology-duplicate-stream resource-total-plies-65535
            resource-total-plies-65536 accept-newline-lf accept-newline-crlf evidence-size
            accept-locked-anthology
            """.split()
        )
        self.assertEqual(set(names), expected_names)
        expected_operations = dict.fromkeys(expected_names, "compile_source")
        for operation, operation_names in {
            "decode_game": """
                binary-game-count-zero binary-game-count-one binary-game-truncated-header
                binary-game-truncated-body binary-game-move binary-game-score
                binary-game-trailing binary-game-semantic-move binary-game-semantic-score
                binary-game-fools-mate binary-game-count-4096 binary-game-count-4097
            """,
            "decode_game_set": """
                binary-game-set-count-zero binary-game-set-count-one
                binary-game-set-truncated-header binary-game-set-truncated-game
                binary-game-set-order binary-game-set-duplicate binary-game-set-trailing
                binary-game-set-size binary-game-set-size-boundary
            """,
            "validate_candidate_trace": """
                evidence-shape-malformed evidence-shape-extra-key evidence-noncanonical
                evidence-hash evidence-cross-field evidence-size
            """,
            "encode_game_set": """
                binary-game-set-count-65535 binary-game-set-count-65536
                binary-game-set-total-plies-65535 binary-game-set-total-plies-65536
            """,
            "validate_anthology": """
                binary-anthology-count-63 binary-anthology-count-64
                binary-anthology-count-65 binary-anthology-duplicate-stream
            """,
        }.items():
            expected_operations.update(dict.fromkeys(operation_names.split(), operation))
        self.assertEqual(
            {
                row["name"]: row["operation"]
                for key in ("cases", "recipes")
                for row in payload[key]
            },
            expected_operations,
        )
        self.assertEqual(
            {
                prefix: sum(name.startswith(prefix + "-") for name in names)
                for prefix in (
                    "raw", "fence", "tag", "framing", "resource", "structure",
                    "terminal", "san", "duplicate", "binary", "evidence", "accept",
                )
            },
            {
                "raw": 44, "fence": 11, "tag": 20, "framing": 8,
                "resource": 6, "structure": 13, "terminal": 7, "san": 21,
                "duplicate": 2, "binary": 29, "evidence": 6, "accept": 19,
            },
        )
        self.assertEqual(
            {row["operation"] for key in ("cases", "recipes") for row in payload[key]},
            {
                "compile_source", "decode_game", "decode_game_set",
                "encode_game_set", "validate_anthology", "validate_candidate_trace",
            },
        )

        source_lock = tomllib.loads((ROOT / "inputs/source-lock.toml").read_text())
        receipts = [row for row in source_lock["source"] if row["id"] == "anthology"]
        self.assertEqual(len(receipts), 1)
        receipt = receipts[0]
        base = repo_text_bytes(ROOT, receipt["path"].encode("ascii"))
        self.assertEqual(len(base), receipt["bytes"])
        self.assertEqual(hashlib.sha256(base).hexdigest(), receipt["sha256"])

        lowercase_hex = re.compile(r"(?:[0-9a-f]{2})*")
        expected_codes = set()

        def checked_hex(value: object) -> bytes:
            self.assertIs(type(value), str)
            self.assertIsNotNone(lowercase_hex.fullmatch(value))
            self.assertLessEqual(len(value), 2 * (MAX_REPO_TEXT_BYTES + 1))
            return bytes.fromhex(value)

        def check_expected(expected: object, input_length: int) -> None:
            self.assertIs(type(expected), dict)
            self.assertIn(set(expected), ({"accept"}, {"rejection"}))
            if "accept" in expected:
                self.assertEqual(expected["accept"], {})
                return
            rejection = expected["rejection"]
            self.assertIs(type(rejection), dict)
            self.assertEqual(set(rejection), {"code", "raw_end", "raw_start"})
            self.assertIs(type(rejection["code"]), int)
            self.assertIn(rejection["code"], range(1, 69))
            expected_codes.add(rejection["code"])
            for key in ("raw_start", "raw_end"):
                self.assertIs(type(rejection[key]), int)
            self.assertLessEqual(0, rejection["raw_start"])
            self.assertLessEqual(rejection["raw_start"], rejection["raw_end"])
            self.assertLessEqual(rejection["raw_end"], input_length)

        for case in payload["cases"]:
            self.assertIs(type(case), dict)
            self.assertEqual(
                set(case), {"expected", "input_hex", "name", "operation"}
            )
            self.assertIs(type(case["name"]), str)
            self.assertIs(type(case["operation"]), str)
            raw = checked_hex(case["input_hex"])
            check_expected(case["expected"], len(raw))

        recipe_keys = {
            "literal-repeat": {
                "count_cap", "expected", "input", "input_bytes", "input_sha256",
                "name", "operation", "recipe",
            },
            "locked-base-patch": {
                "expected", "input", "input_bytes", "input_sha256", "name",
                "operation", "patch_cap", "recipe",
            },
            "knight-cycle-corpus": {
                "count_cap", "expected", "input", "input_bytes", "input_sha256",
                "name", "operation", "recipe",
            },
            "typed-game-set-games": {
                "count_cap", "expected", "input", "input_bytes", "input_sha256",
                "name", "operation", "recipe",
            },
            "typed-game-set-total-plies": {
                "count_cap", "expected", "input", "input_bytes", "input_sha256",
                "name", "operation", "recipe",
            },
            "typed-anthology": {
                "count_cap", "expected", "input", "input_bytes", "input_sha256",
                "name", "operation", "recipe",
            },
        }
        count_caps = {
            "raw-input-too-large": 1_048_576,
            "fence-block-bytes-excess": 65_529,
            "fence-unclosed-precedes-size-and-count": 65_528,
            "fence-count-63": 63,
            "fence-count-65": 65,
            "raw-input-max-reaches-fence-count": 1_048_575,
            "resource-token-count-8192": 8_192,
            "resource-token-count-8193": 8_193,
            "resource-record-plies-4096": 4_096,
            "resource-record-plies-4097": 4_097,
            "binary-game-count-4096": 1_024,
            "binary-game-set-size": 327_678,
            "binary-game-set-size-boundary": 327_677,
            "binary-game-count-4097": 1,
            "binary-game-set-count-65535": 65_536,
            "binary-game-set-count-65536": 65_536,
            "binary-game-set-total-plies-65535": 16,
            "binary-game-set-total-plies-65536": 16,
            "binary-anthology-count-63": 65,
            "binary-anthology-count-64": 65,
            "binary-anthology-count-65": 65,
            "binary-anthology-duplicate-stream": 65,
            "resource-total-plies-65535": 64,
            "resource-total-plies-65536": 64,
            "accept-newline-lf": 64,
            "accept-newline-crlf": 64,
            "evidence-size": 1_048_577,
        }
        recipe_counts = {key: 0 for key in recipe_keys}
        for recipe in payload["recipes"]:
            self.assertIs(type(recipe), dict)
            kind = recipe["recipe"]
            self.assertIn(kind, recipe_keys)
            self.assertEqual(set(recipe), recipe_keys[kind])
            self.assertIs(type(recipe["name"]), str)
            self.assertIs(type(recipe["operation"]), str)
            if kind == "locked-base-patch":
                self.assertEqual(recipe["patch_cap"], 4)
            else:
                self.assertIn(recipe["name"], count_caps)
                self.assertEqual(recipe["count_cap"], count_caps[recipe["name"]])
            recipe_counts[kind] += 1
            inputs = recipe["input"]
            self.assertIs(type(inputs), dict)
            if kind == "literal-repeat":
                self.assertEqual(
                    set(inputs), {"prefix_hex", "repeat_count", "repeat_hex", "suffix_hex"}
                )
                self.assertIs(type(recipe["count_cap"]), int)
                self.assertIs(type(inputs["repeat_count"]), int)
                self.assertLessEqual(0, inputs["repeat_count"])
                self.assertLessEqual(inputs["repeat_count"], recipe["count_cap"])
                prefix = checked_hex(inputs["prefix_hex"])
                repeated = checked_hex(inputs["repeat_hex"])
                suffix = checked_hex(inputs["suffix_hex"])
                expanded_length = (
                    len(prefix) + len(repeated) * inputs["repeat_count"] + len(suffix)
                )
                self.assertLessEqual(expanded_length, MAX_REPO_TEXT_BYTES + 1)
                raw = (
                    prefix + repeated * inputs["repeat_count"] + suffix
                )
            elif kind == "locked-base-patch":
                self.assertEqual(set(inputs), {"base", "patches"})
                self.assertEqual(inputs["base"], "locked-anthology")
                self.assertIs(type(inputs["patches"]), list)
                self.assertIs(type(recipe["patch_cap"]), int)
                self.assertLessEqual(len(inputs["patches"]), recipe["patch_cap"])
                raw_buffer = bytearray(base)
                prior_start = len(base) + 1
                expanded_length = len(base)
                for patch in inputs["patches"]:
                    self.assertIs(type(patch), dict)
                    self.assertEqual(
                        set(patch), {"old_hex", "replacement_hex", "start"}
                    )
                    self.assertIs(type(patch["start"]), int)
                    old = checked_hex(patch["old_hex"])
                    replacement = checked_hex(patch["replacement_hex"])
                    start = patch["start"]
                    self.assertLessEqual(0, start)
                    self.assertLessEqual(start + len(old), len(base))
                    self.assertLess(start, prior_start)
                    self.assertLessEqual(start + len(old), prior_start)
                    self.assertEqual(base[start:start + len(old)], old)
                    self.assertEqual(raw_buffer[start:start + len(old)], old)
                    expanded_length += len(replacement) - len(old)
                    self.assertLessEqual(expanded_length, MAX_REPO_TEXT_BYTES + 1)
                    raw_buffer[start:start + len(old)] = replacement
                    prior_start = start
                raw = bytes(raw_buffer)
            elif kind == "knight-cycle-corpus":
                self.assertIn(
                    set(inputs),
                    (
                        {"cycle", "ply_counts", "result"},
                        {"cycle", "newline_hex", "ply_counts", "result"},
                    ),
                )
                self.assertEqual(inputs["cycle"], ["Nf3", "Nf6", "Ng1", "Ng8"])
                self.assertEqual(inputs["result"], "1/2-1/2")
                self.assertIs(type(inputs["ply_counts"]), list)
                self.assertLessEqual(len(inputs["ply_counts"]), recipe["count_cap"])
                self.assertTrue(all(type(count) is int for count in inputs["ply_counts"]))
                self.assertLessEqual(sum(inputs["ply_counts"]), 65_536)
                newline = checked_hex(inputs.get("newline_hex", "0a"))
                self.assertIn(newline, (b"\n", b"\r\n"))
                blocks = []
                cycle = [token.encode("ascii") for token in inputs["cycle"]]
                for count in inputs["ply_counts"]:
                    self.assertIn(count, range(1, 4097))
                    tokens = []
                    for ply in range(count):
                        if ply % 2 == 0:
                            tokens.append(f"{ply // 2 + 1}.".encode("ascii"))
                        tokens.append(cycle[ply % 4])
                    tokens.append(b"1/2-1/2")
                    blocks.append(
                        newline.join(
                            (b"```pgn", b'[Result "1/2-1/2"]', b"",
                             b" ".join(tokens), b"```", b"")
                        )
                    )
                raw = b"".join(blocks)
            elif kind == "typed-game-set-games":
                self.assertEqual(set(inputs), {"count", "unit_hex"})
                self.assertIs(type(inputs["count"]), int)
                self.assertLessEqual(0, inputs["count"])
                self.assertLessEqual(inputs["count"], recipe["count_cap"])
                unit = checked_hex(inputs["unit_hex"])
                self.assertLessEqual(
                    len(unit) * inputs["count"], MAX_REPO_TEXT_BYTES + 1
                )
                raw = unit * inputs["count"]
            elif kind == "typed-game-set-total-plies":
                self.assertEqual(set(inputs), {"cycle_moves_hex", "ply_counts", "score"})
                cycle = checked_hex(inputs["cycle_moves_hex"])
                self.assertEqual(cycle, bytes.fromhex("1950fad05460b7e0"))
                self.assertIs(type(inputs["ply_counts"]), list)
                self.assertLessEqual(len(inputs["ply_counts"]), recipe["count_cap"])
                self.assertTrue(all(type(count) is int for count in inputs["ply_counts"]))
                self.assertLessEqual(sum(inputs["ply_counts"]), 65_536)
                self.assertIs(type(inputs["score"]), int)
                self.assertIn(inputs["score"], (0, 1, 2))
                pieces = []
                for count in inputs["ply_counts"]:
                    self.assertIn(count, range(1, 4097))
                    moves = (cycle * ((count + 3) // 4))[:count * 2]
                    pieces.append(count.to_bytes(2, "big") + moves + bytes([inputs["score"]]))
                raw = b"".join(pieces)
            else:
                self.assertEqual(
                    set(inputs), {"cycle_moves_hex", "ply_counts", "score"}
                )
                cycle = checked_hex(inputs["cycle_moves_hex"])
                self.assertEqual(len(cycle), 8)
                self.assertIs(type(inputs["ply_counts"]), list)
                self.assertLessEqual(len(inputs["ply_counts"]), recipe["count_cap"])
                self.assertTrue(all(type(count) is int for count in inputs["ply_counts"]))
                self.assertLessEqual(sum(inputs["ply_counts"]), 65_536)
                self.assertIs(type(inputs["score"]), int)
                self.assertIn(inputs["score"], (0, 1, 2))
                pieces = []
                for count in inputs["ply_counts"]:
                    self.assertIn(count, range(1, 4097))
                    moves = (cycle * ((count + 3) // 4))[:count * 2]
                    pieces.append(count.to_bytes(2, "big") + moves + bytes([inputs["score"]]))
                raw = b"".join(pieces)

            self.assertLessEqual(len(raw), MAX_REPO_TEXT_BYTES + 1)
            self.assertIs(type(recipe["input_bytes"]), int)
            self.assertEqual(len(raw), recipe["input_bytes"])
            self.assertIs(type(recipe["input_sha256"]), str)
            self.assertIsNotNone(re.fullmatch(r"[0-9a-f]{64}", recipe["input_sha256"]))
            self.assertEqual(hashlib.sha256(raw).hexdigest(), recipe["input_sha256"])
            check_expected(recipe["expected"], len(raw))

        self.assertEqual(
            recipe_counts,
            {
                "literal-repeat": 15, "locked-base-patch": 88,
                "knight-cycle-corpus": 4,
                "typed-game-set-games": 2, "typed-game-set-total-plies": 2,
                "typed-anthology": 4,
            },
        )
        self.assertEqual(expected_codes, set(range(1, 69)))
        self.assertNotIn(69, expected_codes)
        self.assertNotIn(70, expected_codes)

    def test_source_unclosed_fence_recipes_end_in_lf(self) -> None:
        payload = canonical_manifest.validate_canonical_manifest(SOURCE_FIXTURE.read_bytes())
        recipes = {row["name"]: row for row in payload["recipes"]}
        expected = {
            "fence-block-bytes-excess": (
                65_528,
                65_536,
                "e57c734b09f596ddc9767cfe68e11b4c2f023269c901b95d73b604a541be3225",
                {"code": 12, "raw_start": 65_535, "raw_end": 65_536},
            ),
            "fence-unclosed-precedes-size-and-count": (
                65_527,
                65_535,
                "9d3d745c438ccaeaef02dd46b9ee1278af917b23c78c1028d921e5d7efb4bbd3",
                {"code": 11, "raw_start": 65_535, "raw_end": 65_535},
            ),
        }
        for name, (repeat_count, length, digest, rejection) in expected.items():
            row = recipes[name]
            self.assertEqual(row["input"]["suffix_hex"], "0a")
            self.assertEqual(row["input"]["repeat_count"], repeat_count)
            self.assertEqual(row["input_bytes"], length)
            self.assertEqual(row["input_sha256"], digest)
            self.assertEqual(row["expected"]["rejection"], rejection)

    def test_source_resource_and_span_repairs_are_stage_isolated(self) -> None:
        payload = canonical_manifest.validate_canonical_manifest(SOURCE_FIXTURE.read_bytes())
        recipes = {row["name"]: row for row in payload["recipes"]}
        source_lock = tomllib.loads((ROOT / "inputs/source-lock.toml").read_text())
        receipt = next(row for row in source_lock["source"] if row["id"] == "anthology")
        base = repo_text_bytes(ROOT, receipt["path"].encode("ascii"))

        def expanded(name: str) -> bytes:
            row = recipes[name]
            inputs = row["input"]
            if row["recipe"] == "literal-repeat":
                return (
                    bytes.fromhex(inputs["prefix_hex"])
                    + bytes.fromhex(inputs["repeat_hex"]) * inputs["repeat_count"]
                    + bytes.fromhex(inputs["suffix_hex"])
                )
            raw = bytearray(base)
            for patch in inputs["patches"]:
                start = patch["start"]
                old = bytes.fromhex(patch["old_hex"])
                self.assertEqual(raw[start:start + len(old)], old)
                raw[start:start + len(old)] = bytes.fromhex(patch["replacement_hex"])
            return bytes(raw)

        resource_rows = {
            "resource-token-count-8192": (
                26_934,
                "eaeb0072d9e66acc8bf80e868eb0647fa4da1c48b4cf852760ee0cf3b92f1a50",
                {"code": 35, "raw_start": 26, "raw_end": 28},
            ),
            "resource-token-count-8193": (
                26_937,
                "30865292f39dfd74589ed784ef5674e2443d61d7981c8ea2dbd7d0fc9775d7de",
                {"code": 30, "raw_start": 24_599, "raw_end": 24_601},
            ),
            "resource-record-plies-4096": (
                10_554,
                "bf31cb776a2060674983644250c11058a3f0dc803f969ad3e23fb416c16e56df",
                {"code": 33, "raw_start": 23, "raw_end": 24},
            ),
            "resource-record-plies-4097": (
                10_556,
                "9b6f4ce902d86e5d4b8a9188be69eaf8472f494be14c79640be51be0ada1dff7",
                {"code": 31, "raw_start": 8_215, "raw_end": 8_216},
            ),
        }
        for name, (length, digest, rejection) in resource_rows.items():
            with self.subTest(name=name):
                row = recipes[name]
                raw = expanded(name)
                self.assertEqual(raw.splitlines().count(b"```pgn"), 64)
                self.assertEqual(raw.splitlines().count(b"```"), 64)
                self.assertEqual(len(raw), length)
                self.assertEqual(row["input_bytes"], length)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)
                self.assertEqual(row["input_sha256"], digest)
                self.assertEqual(row["expected"]["rejection"], rejection)
                if name.startswith("resource-token"):
                    self.assertFalse(raw.split(b"\n```\n", 1)[0].endswith((b" ", b"\t")))

        span_rows = {
            "framing-movetext-hws-only": (28, 12_399, 12_400, b" "),
            "structure-result-too-early-first": (36, 12_399, 12_402, b"1-0"),
            "structure-result-too-early-after-number": (36, 12_402, 12_405, b"1-0"),
        }
        for name, (code, start, end, token) in span_rows.items():
            with self.subTest(name=name):
                raw = expanded(name)
                self.assertEqual(
                    recipes[name]["expected"]["rejection"],
                    {"code": code, "raw_start": start, "raw_end": end},
                )
                self.assertEqual(raw[start:end], token)

    def test_source_fixture_shape_mutations_fail_closed(self) -> None:
        payload = canonical_manifest.validate_canonical_manifest(SOURCE_FIXTURE.read_bytes())
        original_reader = repo_text_bytes

        def row(value: dict[str, object], name: str) -> dict[str, object]:
            return next(
                item
                for key in ("cases", "recipes")
                for item in value[key]
                if item["name"] == name
            )

        def change_cap(value: dict[str, object], name: str, field: str) -> None:
            item = row(value, name)
            item[field] += 1

        def swap_operations(value: dict[str, object], first: str, second: str) -> None:
            left, right = row(value, first), row(value, second)
            left["operation"], right["operation"] = right["operation"], left["operation"]

        def extra_key(value: dict[str, object]) -> None:
            value["cases"][0]["extra"] = 1

        def missing_key(value: dict[str, object]) -> None:
            del value["cases"][0]["input_hex"]

        def unknown_recipe(value: dict[str, object]) -> None:
            value["recipes"][0]["recipe"] = "unknown"

        def unknown_name(value: dict[str, object]) -> None:
            value["cases"][0]["name"] += "-unknown"

        def malformed_hex(value: dict[str, object]) -> None:
            value["cases"][0]["input_hex"] = "0"

        def base_mismatch(value: dict[str, object]) -> None:
            row(value, "accept-locked-anthology")["input"]["base"] = "unknown"

        def patch_recipe(value: dict[str, object]) -> dict[str, object]:
            return next(item for item in value["recipes"] if item["input"].get("patches"))

        def non_descending_patch(value: dict[str, object]) -> None:
            item = patch_recipe(value)
            item["input"]["patches"].append(copy.deepcopy(item["input"]["patches"][0]))

        def overlapping_patch(value: dict[str, object]) -> None:
            item = patch_recipe(value)
            start = item["input"]["patches"][0]["start"]
            base = original_reader(ROOT, b"docs/64_games.md")
            item["input"]["patches"].append(
                {
                    "old_hex": base[start - 1:start + 1].hex(),
                    "replacement_hex": "",
                    "start": start - 1,
                }
            )

        def wrong_old_patch(value: dict[str, object]) -> None:
            patch = patch_recipe(value)["input"]["patches"][0]
            old = bytes.fromhex(patch["old_hex"])
            patch["old_hex"] = bytes((old[0] ^ 1,)).hex() + old[1:].hex()

        def final_length_mismatch(value: dict[str, object]) -> None:
            row(value, "accept-locked-anthology")["input_bytes"] += 1

        def final_hash_mismatch(value: dict[str, object]) -> None:
            row(value, "accept-locked-anthology")["input_sha256"] = "0" * 64

        mutations = {
            "raw count cap": lambda value: change_cap(value, "raw-input-too-large", "count_cap"),
            "patch cap": lambda value: change_cap(value, "accept-locked-anthology", "patch_cap"),
            "newline count cap": lambda value: change_cap(value, "accept-newline-lf", "count_cap"),
            "forged typed Game encoder": lambda value: row(
                value, "binary-game-count-4097"
            ).update(operation="encode_game"),
            "decode Game/GameSet swap": lambda value: swap_operations(
                value, "binary-game-count-zero", "binary-game-set-count-zero"
            ),
            "extra key": extra_key,
            "missing key": missing_key,
            "unknown recipe": unknown_recipe,
            "unknown name": unknown_name,
            "malformed hex": malformed_hex,
            "base mismatch": base_mismatch,
            "non-descending patch": non_descending_patch,
            "overlapping patch": overlapping_patch,
            "wrong old patch": wrong_old_patch,
            "final length mismatch": final_length_mismatch,
            "final hash mismatch": final_hash_mismatch,
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                mutated = copy.deepcopy(payload)
                mutate(mutated)
                data = canonical_manifest.serialize_manifest(mutated)

                def selective_reader(root: Path, relative: bytes) -> bytes:
                    if relative == b"conformance/source-v0.json":
                        return data
                    return original_reader(root, relative)

                with mock.patch.object(
                    sys.modules[__name__], "repo_text_bytes", side_effect=selective_reader
                ):
                    with self.assertRaises(AssertionError):
                        self.test_source_fixture_shape_and_coverage_are_closed()

    def test_chess_fixture_shape_and_coverage_are_closed(self) -> None:
        payload = canonical_manifest.validate_canonical_manifest(
            repo_text_bytes(ROOT, b"conformance/chess-v0.json")
        )
        self.assertEqual(set(payload), {"cases", "recipes", "schema"})
        self.assertEqual(payload["schema"], "golden-board.chess-v0-fixtures/v0")

        cases = payload["cases"]
        self.assertEqual(len(cases), 224)
        names = [case["name"] for case in cases]
        self.assertEqual(len(set(names)), len(names))
        self.assertTrue(all(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) for name in names))
        self.assertEqual(
            {case["operation"] for case in cases},
            {
                "apply_event", "apply_move", "controls_square", "decode_event",
                "decode_move", "decode_position", "evaluate_predicate", "legal_moves",
                "pseudo_legal_moves", "repetition_key", "replay_from_start",
                "validate_local", "validate_source_record",
            },
        )
        self.assertEqual(
            {
                prefix: sum(name.startswith(prefix + "-") for name in names)
                for prefix in (
                    "wire", "structural", "local", "geometry", "castling",
                    "en-passant", "promotion", "terminal", "history", "event",
                    "record", "predicate", "precedence",
                )
            },
            {
                "wire": 14, "structural": 17, "local": 20, "geometry": 19,
                "castling": 15, "en-passant": 11, "promotion": 11, "terminal": 7,
                "history": 8, "event": 21, "record": 13, "predicate": 60,
                "precedence": 8,
            },
        )
        required = {
            "wire-position-initial", "wire-initial-legal-moves",
            "local-lowest-square-tie", "geometry-king-capture-removes-blocker-self-check",
            "castling-failure-origin-safe-transit-attack",
            "en-passant-pinned-effective-key-omitted", "promotion-immediate-checkmate",
            "en-passant-geometry-after-nominal-target",
            "terminal-stalemate-precedes-common-dead",
            "terminal-king-two-knights-versus-king-not-common-dead",
            "history-pawn-move-resets-halfmove", "event-after-claimed-fifty-move-closure",
            "record-common-dead-second-win-contradiction",
            "predicate-correct-discovered-attack-check",
            "predicate-correct-finite-mating-geometry", "predicate-tree-defect-depth",
            "predicate-closed-fork-seventeen-before-resource",
            "predicate-resource-node-count-4097", "predicate-resource-edges-per-node-257",
            "predicate-resource-total-edges-4096",
            *(f"precedence-layer-{letter}-{suffix}" for letter, suffix in (
                ("a", "structure"), ("b", "local"), ("c", "closure"),
                ("d", "resource"), ("e", "illegal-move"), ("f", "invalid-event"),
                ("g", "finite-proof"), ("h", "source-record"),
            )),
        }
        self.assertTrue(required.issubset(names))
        input_shapes = {
            "apply_event": {"event_hex": str, "events_hex": list},
            "apply_move": {"move_hex": str, "moves_hex": str},
            "controls_square": {"position_hex": str, "side": int, "target": int},
            "decode_event": {"event_hex": str},
            "decode_move": {"move_hex": str},
            "decode_position": {"position_hex": str},
            "evaluate_predicate": {"input": dict, "predicate_id": str},
            "legal_moves": {"moves_hex": str},
            "pseudo_legal_moves": {"position_hex": str},
            "repetition_key": {"moves_hex": str},
            "replay_from_start": {"moves_hex": str},
            "validate_local": {"position_hex": str},
            "validate_source_record": {"moves_hex": str, "score": int},
        }
        success_shapes = {
            "apply_event": ({"cause": dict, "score": int, "status": int},),
            "apply_move": (
                {"position_hex": str},
                {"halfmove_clock": int, "position_hex": str},
                {"king_in_check": bool, "position_hex": str, "terminal": int},
            ),
            "controls_square": ({"squares": list},),
            "decode_event": ({"event_hex": str},),
            "decode_move": ({"move_hex": str},),
            "decode_position": ({"position_hex": str},),
            "evaluate_predicate": ({"result": dict},),
            "legal_moves": ({"moves_hex": str},),
            "pseudo_legal_moves": ({"moves_hex": str},),
            "repetition_key": ({"repetition_key_hex": str},),
            "replay_from_start": (
                {"common_dead": bool, "terminal": int},
                {"common_dead": bool, "terminal": int, "winning_side": int},
            ),
            "validate_source_record": (
                {"score": int, "terminal": int},
                {
                    "fifty_move_available": bool,
                    "score": int,
                    "terminal": int,
                    "threefold_available": bool,
                },
            ),
        }
        predicate_input_shapes = {
            "chess.absolute_pin": {"origin": int, "position_hex": str, "variant": str},
            "chess.control": {"position_hex": str, "side": int, "target": int, "variant": str},
            "chess.declaration_event": {"event_hex": str, "events_hex": list, "variant": str},
            "chess.defended": {"defender": dict, "position_hex": str, "target": int, "variant": str},
            "chess.discovered_attack_check": {"move_hex": str, "moves_hex": str, "slider_origin": int, "target": int, "variant": str},
            "chess.escape_square_control": {"candidate": int, "position_hex": str, "side": int, "variant": str},
            "chess.finite_mating_geometry": {"mating_side": int, "moves_hex": str, "nodes": list, "variant": str},
            "chess.finite_promotion_race": {"moves_hex": str, "nodes": list, "variant": str},
            "chess.fork_double_attack": {"move_hex": str, "moves_hex": str, "targets": list, "variant": str},
            "chess.history_claim": {"moves_hex": str, "variant": str},
            "chess.king_check": {"position_hex": str, "side": int, "variant": str},
            "chess.move_legality": {"move_hex": str, "moves_hex": str, "variant": str},
            "chess.move_record_replay": {"move_hex": str, "variant": str},
            "chess.occupancy": {"match": dict, "position_hex": str, "square": int, "variant": str},
            "chess.open_file": {"file": int, "position_hex": str, "variant": str},
            "chess.passed_pawn": {"pawn_square": int, "position_hex": str, "variant": str},
            "chess.semi_open_file": {"file": int, "position_hex": str, "side": int, "variant": str},
            "chess.setup_turn": {"position_hex": str, "variant": str},
            "chess.source_score_relation": {"moves_hex": str, "score": int, "variant": str},
            "chess.terminal_transition": {"move_hex": str, "moves_hex": str, "variant": str},
            "chess.unknown": {"position_hex": str, "variant": str},
        }
        predicate_result_shapes = {
            **{
                predicate_id: {"value": bool}
                for predicate_id in (
                    "chess.absolute_pin", "chess.defended", "chess.discovered_attack_check",
                    "chess.escape_square_control", "chess.fork_double_attack",
                    "chess.king_check", "chess.occupancy", "chess.open_file",
                    "chess.passed_pawn", "chess.semi_open_file", "chess.setup_turn",
                )
            },
            "chess.control": {"squares": list},
            "chess.declaration_event": {"cause": dict, "kind": str, "score": int, "status": int},
            "chess.finite_mating_geometry": {"all_branches_mate": bool, "mating_side": int, "max_plies": int},
            "chess.finite_promotion_race": {"outcomes": list},
            "chess.history_claim": {
                "current_key_occurrences": int,
                "effective_ep": dict,
                "fifty_move_available": bool,
                "halfmove_clock": int,
                "nominal_ep": dict,
                "played_plies": int,
                "threefold_available": bool,
            },
            "chess.move_legality": {"kind": str},
            "chess.move_record_replay": {"kind": str, "move_hex": str},
            "chess.source_score_relation": {"kind": str, "terminal": int},
            "chess.terminal_transition": {"terminal": int, "winning_side": int},
        }
        cause_shapes = (
            {"kind": str},
            {"kind": str, "side": int},
            {"kind": str, "terminal": int},
            {"kind": str, "terminal": int, "winning_side": int},
        )
        for case in cases:
            self.assertEqual(set(case), {"expected", "input", "name", "operation"})
            self.assertIsInstance(case["input"], dict)
            input_shape = input_shapes[case["operation"]]
            self.assertEqual(set(case["input"]), set(input_shape))
            for key, expected_type in input_shape.items():
                self.assertIs(type(case["input"][key]), expected_type)
            self.assertEqual(len(case["expected"]), 1)
            self.assertIn(next(iter(case["expected"])), {"rejection", "success"})
            if "rejection" in case["expected"]:
                self.assertIs(type(case["expected"]["rejection"]), int)
                self.assertIn(case["expected"]["rejection"], range(1, 63))
            else:
                success = case["expected"]["success"]
                self.assertIsInstance(success, dict)
                matching = [
                    shape
                    for shape in success_shapes[case["operation"]]
                    if set(success) == set(shape)
                ]
                self.assertEqual(len(matching), 1)
                for key, expected_type in matching[0].items():
                    self.assertIs(type(success[key]), expected_type)

            if case["operation"] == "apply_event":
                self.assertTrue(all(type(item) is str for item in case["input"]["events_hex"]))
                if "success" in case["expected"]:
                    cause = case["expected"]["success"]["cause"]
                    matching_causes = [shape for shape in cause_shapes if set(cause) == set(shape)]
                    self.assertEqual(len(matching_causes), 1)
                    for key, expected_type in matching_causes[0].items():
                        self.assertIs(type(cause[key]), expected_type)
            if case["operation"] == "controls_square" and "success" in case["expected"]:
                self.assertTrue(
                    all(type(square) is int for square in case["expected"]["success"]["squares"])
                )
            if case["operation"] == "evaluate_predicate":
                predicate_id = case["input"]["predicate_id"]
                predicate_input = case["input"]["input"]
                predicate_shape = predicate_input_shapes[predicate_id]
                if set(predicate_input) == {"variant"}:
                    self.assertEqual(case["expected"], {"rejection": 15})
                    self.assertIs(type(predicate_input["variant"]), str)
                else:
                    self.assertEqual(set(predicate_input), set(predicate_shape))
                    for key, expected_type in predicate_shape.items():
                        self.assertIs(type(predicate_input[key]), expected_type)
                    if "match" in predicate_input:
                        self.assertEqual(set(predicate_input["match"]), {"kind", "piece", "side"})
                        self.assertIs(type(predicate_input["match"]["kind"]), str)
                        self.assertIs(type(predicate_input["match"]["piece"]), int)
                        self.assertIs(type(predicate_input["match"]["side"]), int)
                    if "defender" in predicate_input:
                        self.assertEqual(set(predicate_input["defender"]), {"kind", "square"})
                        self.assertIs(type(predicate_input["defender"]["kind"]), str)
                        self.assertIs(type(predicate_input["defender"]["square"]), int)
                    if "targets" in predicate_input:
                        self.assertTrue(all(type(target) is int for target in predicate_input["targets"]))
                    if "events_hex" in predicate_input:
                        self.assertTrue(all(type(event) is str for event in predicate_input["events_hex"]))
                    if "nodes" in predicate_input:
                        for node in predicate_input["nodes"]:
                            self.assertIs(type(node), dict)
                            self.assertEqual(set(node), {"edges"})
                            self.assertIs(type(node["edges"]), list)
                            for edge in node["edges"]:
                                self.assertIs(type(edge), dict)
                                self.assertEqual(set(edge), {"child", "move_hex"})
                                self.assertIs(type(edge["child"]), int)
                                self.assertIs(type(edge["move_hex"]), str)
                if "success" in case["expected"]:
                    result = case["expected"]["success"]["result"]
                    result_shape = predicate_result_shapes[predicate_id]
                    self.assertEqual(set(result), set(result_shape))
                    for key, expected_type in result_shape.items():
                        self.assertIs(type(result[key]), expected_type)
                    if "squares" in result:
                        self.assertTrue(all(type(square) is int for square in result["squares"]))
                    if "outcomes" in result:
                        self.assertTrue(all(type(outcome) is str for outcome in result["outcomes"]))
                    if "cause" in result:
                        self.assertEqual(set(result["cause"]), {"kind", "side"})
                        self.assertIs(type(result["cause"]["kind"]), str)
                        self.assertIs(type(result["cause"]["side"]), int)
                    for key in ("effective_ep", "nominal_ep"):
                        if key in result:
                            ep = result[key]
                            self.assertIn(set(ep), ({"kind"}, {"kind", "square"}))
                            self.assertIs(type(ep["kind"]), str)
                            if "square" in ep:
                                self.assertIs(type(ep["square"]), int)

        def check_hex(value: object) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    if key.endswith("_hex"):
                        values = item if isinstance(item, list) else [item]
                        self.assertTrue(all(isinstance(part, str) for part in values))
                        self.assertTrue(all(re.fullmatch(r"(?:[0-9a-f]{2})*", part) for part in values))
                        if key == "moves_hex":
                            self.assertTrue(all(len(part) % 4 == 0 for part in values))
                    check_hex(item)
            elif isinstance(value, list):
                for item in value:
                    check_hex(item)

        check_hex(payload)
        recipes = payload["recipes"]
        self.assertEqual([recipe["name"] for recipe in recipes], [
            "history-boundary-4095", "history-boundary-4096", "history-excess-4097",
        ])
        expected_recipe_facts = (
            (4095, "", 8190, "fe083157aff7dddf8ef1d7c55d14d74836351de95367107f2382c465ba670735", {"success": {"played_plies": 4095}}),
            (4096, "", 8192, "39b9ad3d90be853994abbf8fba476816fcc15865f9fdf99f26a33673e0972616", {"success": {"played_plies": 4096}}),
            (4097, "4180", 8194, "b2b5803f901288658064cbd1c05ff36db5b6fe73f99d68941e85178b968c5abc", {"rejection": 35}),
        )
        for recipe, (plies, final_move, byte_count, digest, expected) in zip(recipes, expected_recipe_facts):
            self.assertEqual(set(recipe), {
                "count_cap", "expected", "input", "input_bytes", "input_sha256", "name", "recipe",
            })
            self.assertEqual(recipe["recipe"], "knight-cycle-history")
            self.assertIs(type(recipe["count_cap"]), int)
            self.assertEqual(recipe["count_cap"], 4097)
            self.assertIs(type(recipe["input"]), dict)
            self.assertEqual(set(recipe["input"]), {"cycle_moves_hex", "final_move_hex", "ply_count"})
            self.assertEqual(recipe["expected"], expected)
            if "success" in expected:
                self.assertIs(type(recipe["expected"]["success"]["played_plies"]), int)
            else:
                self.assertIs(type(recipe["expected"]["rejection"]), int)
            self.assertIs(type(recipe["input"]["ply_count"]), int)
            self.assertEqual(recipe["input"]["ply_count"], plies)
            self.assertIs(type(recipe["input"]["final_move_hex"]), str)
            self.assertEqual(recipe["input"]["final_move_hex"], final_move)
            prefix_plies = plies - bool(final_move)
            cycle = recipe["input"]["cycle_moves_hex"]
            self.assertIs(type(cycle), str)
            self.assertEqual(cycle, "1950fad05460b7e0")
            constructed = (cycle * ((prefix_plies + 3) // 4))[: prefix_plies * 4] + final_move
            raw = bytes.fromhex(constructed)
            self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), (byte_count, digest))
            self.assertIs(type(recipe["input_bytes"]), int)
            self.assertIs(type(recipe["input_sha256"]), str)
            self.assertEqual((recipe["input_bytes"], recipe["input_sha256"]), (byte_count, digest))

    def test_chess_fixture_shape_mutations_fail_closed(self) -> None:
        payload = canonical_manifest.validate_canonical_manifest(CHESS_FIXTURE.read_bytes())

        def extra_input(value: dict[str, object]) -> None:
            value["cases"][0]["input"]["extra"] = 1

        def extra_success(value: dict[str, object]) -> None:
            value["cases"][0]["expected"]["success"]["extra"] = 1

        def wrong_recipe_branch(value: dict[str, object]) -> None:
            value["recipes"][0]["expected"] = {"rejection": 1}

        def wrong_recipe_type(value: dict[str, object]) -> None:
            value["recipes"][0]["expected"]["success"]["played_plies"] = "4095"

        def predicate_input_extra(value: dict[str, object]) -> None:
            case = next(
                case for case in value["cases"]
                if case["name"] == "predicate-correct-setup-turn"
            )
            case["input"]["input"]["extra"] = 1

        def predicate_result_type(value: dict[str, object]) -> None:
            case = next(
                case for case in value["cases"]
                if case["name"] == "predicate-correct-fork-double-attack"
            )
            case["expected"]["success"]["result"]["value"] = 1

        for name, mutate in {
            "extra operation input": extra_input,
            "extra operation success": extra_success,
            "wrong recipe branch": wrong_recipe_branch,
            "wrong recipe result type": wrong_recipe_type,
            "extra predicate input": predicate_input_extra,
            "wrong predicate result type": predicate_result_type,
        }.items():
            with self.subTest(name=name):
                mutated = copy.deepcopy(payload)
                mutate(mutated)
                data = canonical_manifest.serialize_manifest(mutated)
                with mock.patch.object(
                    sys.modules[__name__], "repo_text_bytes", return_value=data
                ):
                    with self.assertRaises(AssertionError):
                        self.test_chess_fixture_shape_and_coverage_are_closed()

        oversized = copy.deepcopy(payload)
        oversized["recipes"][0]["input"]["cycle_moves_hex"] += "00"
        data = canonical_manifest.serialize_manifest(oversized)
        with mock.patch.object(sys.modules[__name__], "repo_text_bytes", return_value=data):
            with mock.patch.object(hashlib, "sha256", side_effect=RuntimeError("expanded")):
                with self.assertRaises(AssertionError):
                    self.test_chess_fixture_shape_and_coverage_are_closed()

    def test_conformance_registry_mutations_fail_closed(self) -> None:
        payload = b"fixture\n"
        digest = hashlib.sha256(payload).hexdigest().encode()
        registry = (
            b'schema = "golden-board.conformance-registry/v0"\n\n'
            b"[[suite]]\n"
            b'id = "identity-v0"\n'
            b'path = "conformance/identity-v0.json"\n'
            b'specification = "identity-v0"\n'
            b'version = "v0"\n'
            + b'sha256 = "' + digest + b'"\n'
            b'consumers = ["python", "rust"]\n'
            b'provenance = "hand-authored"\n'
        )
        mutations = {
            "missing_top_key": registry.replace(
                b'schema = "golden-board.conformance-registry/v0"\n\n', b""
            ),
            "missing_suite": b'schema = "golden-board.conformance-registry/v0"\n',
            "extra_top_key": registry.replace(
                b"\n\n[[suite]]", b"\nextra = true\n\n[[suite]]"
            ),
            "bad_schema": registry.replace(b"registry/v0", b"registry/v1"),
            "missing_row_key": registry.replace(b'version = "v0"\n', b""),
            "extra_row_key": registry + b'extra = "x"\n',
            "bad_id_empty": registry.replace(b'id = "identity-v0"', b'id = ""'),
            "bad_id_uppercase": registry.replace(b"identity-v0", b"Identity-v0", 1),
            "bad_id_hyphens": registry.replace(b"identity-v0", b"identity--v0", 1),
            "bad_specification": registry.replace(
                b'specification = "identity-v0"', b'specification = "identity_v0"'
            ),
            "empty_path": registry.replace(
                b'path = "conformance/identity-v0.json"', b'path = ""'
            ),
            "parent_path": registry.replace(
                b'path = "conformance/identity-v0.json"', b'path = "../identity-v0.json"'
            ),
            "absolute_path": registry.replace(
                b'path = "conformance/identity-v0.json"', b'path = "/identity-v0.json"'
            ),
            "nested_path": registry.replace(
                b'path = "conformance/identity-v0.json"',
                b'path = "conformance/nested/identity-v0.json"',
            ),
            "backslash_alias": registry.replace(
                b'path = "conformance/identity-v0.json"',
                br"path = 'conformance\identity-v0.json'",
            ),
            "nul_path": registry.replace(
                b'path = "conformance/identity-v0.json"',
                br'path = "conformance/identity-v0\u0000.json"',
            ),
            "dot_path": registry.replace(
                b'path = "conformance/identity-v0.json"', b'path = "."'
            ),
            "dot_dot_path": registry.replace(
                b'path = "conformance/identity-v0.json"', b'path = ".."'
            ),
            "alternate_path": registry.replace(
                b'path = "conformance/identity-v0.json"',
                b'path = "conformance/./identity-v0.json"',
            ),
            "registry_self_path": registry.replace(
                b'path = "conformance/identity-v0.json"',
                b'path = "conformance/registry.toml"',
            ),
            "bad_version": registry.replace(b'version = "v0"', b'version = "v1"'),
            "bad_hash": registry.replace(digest, b"A" * 64),
            "bad_consumers": registry.replace(
                b'["python", "rust"]', b'["rust", "python"]'
            ),
            "bad_provenance": registry.replace(b"hand-authored", b"generated"),
            "duplicate_id": registry + b"[[suite]]\n" + registry.split(b"[[suite]]\n", 1)[1],
            "duplicate_path": registry
            + b"[[suite]]\n"
            + registry.split(b"[[suite]]\n", 1)[1].replace(
                b'id = "identity-v0"', b'id = "manifest-v0"'
            ),
            "oversized_registry": registry
            + b" " * (MAX_REPO_TEXT_BYTES + 1 - len(registry)),
        }
        for name, mutation in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory(
                prefix="registry-contract-"
            ) as directory:
                root = Path(directory)
                (root / "conformance").mkdir()
                (root / "conformance/registry.toml").write_bytes(mutation)
                (root / "conformance/identity-v0.json").write_bytes(payload)
                with self.assertRaises(AssertionError):
                    validate_conformance_registry(root)

    def test_conformance_registry_tree_and_payload_bounds(self) -> None:
        def write_valid(root: Path, payload: bytes = b"fixture\n") -> Path:
            conformance = root / "conformance"
            conformance.mkdir()
            digest = hashlib.sha256(payload).hexdigest()
            (conformance / "registry.toml").write_text(
                'schema = "golden-board.conformance-registry/v0"\n\n'
                "[[suite]]\n"
                'id = "identity-v0"\n'
                'path = "conformance/identity-v0.json"\n'
                'specification = "identity-v0"\n'
                'version = "v0"\n'
                f'sha256 = "{digest}"\n'
                'consumers = ["python", "rust"]\n'
                'provenance = "hand-authored"\n'
            )
            path = conformance / "identity-v0.json"
            path.write_bytes(payload)
            return path

        for name in (
            "missing_target",
            "unregistered_payload",
            "direct_symlink",
            "non_regular_target",
            "hash_mismatch",
            "inventory_mismatch",
            "unexpected_symlink",
            "registry_symlink",
            "registry_non_regular",
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory(
                prefix="registry-contract-"
            ) as directory:
                root = Path(directory)
                path = write_valid(root)
                if name == "missing_target":
                    path.unlink()
                elif name == "unregistered_payload":
                    (root / "conformance/manifest-v0.json").write_bytes(b"extra\n")
                elif name == "direct_symlink":
                    path.unlink()
                    target = root / "target.json"
                    target.write_bytes(b"fixture\n")
                    path.symlink_to(target)
                elif name == "non_regular_target":
                    path.unlink()
                    path.mkdir()
                elif name == "hash_mismatch":
                    path.write_bytes(b"changed\n")
                elif name == "inventory_mismatch":
                    path.unlink()
                    (root / "conformance/manifest-v0.json").write_bytes(b"fixture\n")
                elif name == "unexpected_symlink":
                    target = root / "target.json"
                    target.write_bytes(b"extra\n")
                    (root / "conformance/extra.json").symlink_to(target)
                else:
                    registry_path = root / "conformance/registry.toml"
                    registry = registry_path.read_bytes()
                    registry_path.unlink()
                    if name == "registry_symlink":
                        target = root / "registry.toml"
                        target.write_bytes(registry)
                        registry_path.symlink_to(target)
                    else:
                        registry_path.mkdir()
                with self.assertRaises(AssertionError):
                    validate_conformance_registry(root)

        for size, accepted in (
            (MAX_REPO_TEXT_BYTES, True),
            (MAX_REPO_TEXT_BYTES + 1, False),
        ):
            with self.subTest(size=size), tempfile.TemporaryDirectory(
                prefix="registry-contract-"
            ) as directory:
                root = Path(directory)
                write_valid(root, b"x" * size)
                if accepted:
                    validate_conformance_registry(root)
                else:
                    with self.assertRaises(AssertionError):
                        validate_conformance_registry(root)

    def test_untracked_text_scan_rejects_unsafe_files(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT, prefix="repo-contract-") as directory:
            root = Path(directory)
            (root / "regular.txt").write_bytes(b"regular\n")
            (root / "newline\nname.txt").write_bytes(b"newline\n")
            self.test_text_registry_links_and_status_are_consistent()
            self.assertEqual(repo_text_bytes(root, b"regular.txt"), b"regular\n")
            for relative in (b"/absolute", b"../outside", b"regular.txt/../outside"):
                with self.subTest(relative=relative), self.assertRaises(AssertionError):
                    repo_text_bytes(root, relative)

            safe_directory = root / "safe-directory"
            safe_directory.mkdir()
            (safe_directory / "inside.txt").write_bytes(b"inside\n")
            (root / "directory-link").symlink_to(safe_directory, target_is_directory=True)
            with self.assertRaises(AssertionError):
                repo_text_bytes(root, b"directory-link/inside.txt")
            (root / "directory-link").unlink()

            target = root / "target.txt"
            target.write_bytes(b"target\n")
            (root / "link.txt").symlink_to(target)
            with self.assertRaises(AssertionError):
                self.test_text_registry_links_and_status_are_consistent()
            (root / "link.txt").unlink()

            (root / "oversize.txt").write_bytes(b"x" * (1_048_576 + 1))
            with self.assertRaises(AssertionError):
                self.test_text_registry_links_and_status_are_consistent()
            (root / "oversize.txt").unlink()

            if hasattr(os, "mkfifo"):
                fifo = root / "pipe"
                os.mkfifo(fifo)
                try:
                    with self.assertRaises(AssertionError):
                        repo_text_bytes(root, b"pipe")
                finally:
                    fifo.unlink()

    def test_m1_admission_policy(self) -> None:
        check = (ROOT / "scripts/check").read_text()
        self.assertIn("cargo test -p gb-foundation", check)
        self.assertIn("git diff --check || return 1", check)
        self.assertIn("git diff --cached --check || return 1", check)
        identity_block = check.split("identity() {", 1)[1].split("\n}\n", 1)[0]
        repo_block = check.split("repo() {", 1)[1].split("\n}\n", 1)[0]
        self.assertNotIn("--workspace", identity_block)
        self.assertNotIn("git diff --check -- ", repo_block)
        self.assertNotIn("git diff --cached --check -- ", repo_block)
        self.assertIn("chess() {", check)
        self.assertIn("python.tests.test_chess", check)
        self.assertIn("cargo test -p gb-chess", check)
        self.assertIn("content() {", check)
        self.assertIn("python.tests.test_content", check)
        self.assertIn("cargo test -p gb-content", check)
        self.assertIn("curriculum() {", check)
        self.assertIn("python.tests.test_curriculum", check)
        self.assertIn("source-python", check)
        self.assertIn("python.tests.test_source_compiler", check)
        self.assertIn("source-rust", check)
        self.assertIn("--test source", check)

        roadmap = (ROOT / "docs/roadmap.md").read_text()
        self.assertIn(
            "| M1 — Chess truth, source grammar, and assessment blueprint | Complete — 2026-08-17; scripts/check full; game-set identity ffe37ea482b590eb2b454041c0918d05a85161c8f0c604bbf58cc7b71de87db9; report SHA-256 93d0f7ee9e3777386e817bac159b11065fc3378f13644b014b5c399bd420be54 |",
            roadmap,
        )

    def test_m1_chess_convergence_is_live_and_oracle_is_isolated(self) -> None:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())
        self.assertEqual(project["dependency-groups"]["oracle"], ["chess==1.11.2"])

        python_test = (ROOT / "python/tests/test_chess.py").read_text()
        rust_test = (ROOT / "crates/gb-chess/tests/chess.rs").read_text()
        oracle_test = (ROOT / "python/tests/test_chess_oracle.py").read_text()
        self.assertIn("_neutral_cycle_observations", python_test)
        self.assertIn("neutral_cycle_observations", rust_test)
        for count in (59, 91, 74):
            self.assertIn(f"self.assertEqual(seen, {count})", python_test)
        self.assertIn("assert_eq!(cases.len(), 224)", rust_test)
        self.assertIn("assert_eq!(recipes.len(), 3)", rust_test)
        self.assertIn("import chess", oracle_test)
        for forbidden in ("parse_san", ".fen(", ".outcome(", "push_san"):
            self.assertNotIn(forbidden, oracle_test)
        for production in (
            ROOT / "python/golden_board/chess.py",
            ROOT / "crates/gb-chess/src/lib.rs",
        ):
            self.assertNotIn("python-chess", production.read_text())
            self.assertNotIn("import chess", production.read_text())

    def test_m1_portable_evidence_and_run_state_owners_are_explicit(self) -> None:
        source = " ".join((ROOT / "spec/source-v0.md").read_text().split())
        content = " ".join((ROOT / "spec/content-v0.md").read_text().split())
        m1_spec = " ".join((ROOT / "docs/m1-spec.md").read_text().split())
        m1_plan = " ".join((ROOT / "docs/m1-plan.md").read_text().split())

        self.assertIn(
            "`conformance/source-v0.json` is the portable shared fixture. It owns "
            "exact raw-byte and typed-operation cases through "
            "`SOURCE_EVIDENCE_CROSS_FIELD`.",
            source,
        )
        self.assertIn(
            "`SOURCE_CANDIDATE_MISMATCH` is P5 coordinator evidence constructed "
            "only after two individually valid candidates.",
            source,
        )
        self.assertIn(
            "`SOURCE_EVIDENCE_INSTALL` is language-local host-adapter failure and "
            "interruption evidence.",
            source,
        )
        self.assertIn(
            "Neither latter case is a portable shared-fixture input; both retain "
            "the owner-defined canonical span `[0,0)`.",
            source,
        )
        self.assertIn(
            "`global_remaining <= root.global_event_budget`; failure spans "
            "`global_remaining` `[6,8)`; "
            "`local_remaining <= current_node.item_event_budget`; failure spans "
            "`local_remaining` `[8,10)`; "
            "`local_remaining <= global_remaining`; failure spans "
            "`local_remaining` `[8,10)`. "
            "Active requires both remaining values nonzero; exhausted requires at "
            "least one zero; committed permits either. A phase/budget mismatch "
            "spans `phase` `[10,11)`.",
            content,
        )
        self.assertIn(
            "Hand-authored portable fixtures cover exact raw-byte or "
            "typed-operation inputs and expected code/span for every rejection "
            "through `SOURCE_EVIDENCE_CROSS_FIELD`, including:",
            source,
        )
        self.assertNotIn(
            "fixtures cover exact raw bytes and expected code/span for every "
            "rejection above",
            source,
        )
        self.assertIn(
            "Literal boundary-plus-one evidence is required whenever representable.",
            content,
        )
        full_width = (
            "When a wire maximum fills its field (for example `u16` 65,535), "
            "commit the literal maximum encoding and test one additional "
            "host/runtime element or operation without encoding wrap; rejection "
            "or exhaustion is atomic with no output/state mutation."
        )
        self.assertIn(full_width, content)
        for overview in (m1_spec, m1_plan):
            self.assertIn(
                "Shared source fixtures are portable raw/typed inputs; P5 owns "
                "candidate mismatch, and adapter-local tests own install/interruption.",
                overview,
            )
            self.assertIn(full_width, overview)

    def test_m1_chess_and_source_owners_are_closed(self) -> None:
        chess = (ROOT / "spec/chess-v0.md").read_text()
        source = (ROOT / "spec/source-v0.md").read_text()
        design = (ROOT / "docs/m1-spec.md").read_text()
        design_words = " ".join(design.split())

        self.assertIn("sole owner of Golden Board v0 chess types", chess)
        self.assertIn("sole owner of Golden Board v0 raw Markdown", source)
        self.assertIn("sole normative owner of chess bytes", design_words)
        self.assertIn("sole normative owner of raw grammar", design_words)
        self.assertIsNone(re.search(r"\b(?:TODO|TBD|FIXME|XXX)\b", chess + source))

        operations = {
            "decode_position", "encode_position", "decode_move", "encode_move",
            "decode_event", "encode_event", "validate_local",
            "controls_square", "king_in_check", "pseudo_legal_moves",
            "replay_from_start", "legal_moves", "apply_move",
            "repetition_key", "board_terminal", "common_dead", "new_game",
            "apply_event", "validate_source_record", "evaluate_predicate",
        }
        api = chess.split("## 5. Public logical API", 1)[1].split(
            "## 6. Board semantics", 1
        )[0]
        api_block = api.split("```text", 1)[1].split("```", 1)[0]
        self.assertEqual(
            set(re.findall(r"^([a-z_]+)\(", api_block, re.MULTILINE)),
            operations,
        )

        source_operations = {
            "compile_source", "encode_game", "decode_game",
            "validate_anthology", "encode_game_set", "decode_game_set",
            "encode_candidate_trace", "validate_candidate_trace",
            "coordinate_candidates", "validate_retained_evidence",
        }
        source_api = source.split("### 1.2 Logical API", 1)[1].split(
            "## 2. Input profile and spans", 1
        )[0]
        source_api_block = source_api.split("```text", 1)[1].split("```", 1)[0]
        self.assertEqual(
            set(re.findall(r"^([a-z_]+)\(", source_api_block, re.MULTILINE)),
            source_operations,
        )

        predicates = set(
            re.findall(r"^\| `(chess\.[a-z0-9_]+)` \|", chess, re.MULTILINE)
        )
        self.assertEqual(
            predicates,
            {
                "chess.setup_turn", "chess.occupancy", "chess.move_legality",
                "chess.control", "chess.defended", "chess.king_check",
                "chess.absolute_pin", "chess.fork_double_attack",
                "chess.discovered_attack_check", "chess.escape_square_control",
                "chess.passed_pawn", "chess.open_file", "chess.semi_open_file",
                "chess.finite_promotion_race", "chess.finite_mating_geometry",
                "chess.terminal_transition", "chess.history_claim",
                "chess.declaration_event", "chess.source_score_relation",
                "chess.move_record_replay",
            },
        )
        self.assertEqual(
            re.findall(r"^\*\*Stage ([0-9]+) ", source, re.MULTILINE),
            [str(stage) for stage in range(1, 12)],
        )

    def test_m1_content_owner_is_closed(self) -> None:
        content = (ROOT / "spec/content-v0.md").read_text()
        design = " ".join((ROOT / "docs/m1-spec.md").read_text().split())

        self.assertIn("sole owner of Golden Board content-v0", content)
        self.assertIn("sole normative owner of generic content bytes", design)
        self.assertIsNone(re.search(r"\b(?:TODO|TBD|FIXME|XXX)\b", content))
        self.assertIn("content.stream_validation", content)
        self.assertIn("466,958", content)
        self.assertIn("466,955", content)

        self.assertEqual(
            set(re.findall(r"\bCONTENT_KIND_[A-Z_]+\b", content)),
            {
                "CONTENT_KIND_TEXT", "CONTENT_KIND_ATOM_SCHEMA",
                "CONTENT_KIND_ATOM_VECTOR", "CONTENT_KIND_MATRIX",
                "CONTENT_KIND_FIELD_SCHEMA", "CONTENT_KIND_TUPLE",
                "CONTENT_KIND_REGION_SET", "CONTENT_KIND_SEMANTIC_BINDING",
                "CONTENT_KIND_OPAQUE_DATA", "CONTENT_KIND_PREDICATE_RESULT",
                "CONTENT_KIND_FEEDBACK", "CONTENT_KIND_PASSIVE_TRACE",
                "CONTENT_KIND_LESSON_NODE", "CONTENT_KIND_ROOT",
            },
        )
        code_section = content.split("### 13.2 Primary code order", 1)[1].split(
            "### 13.3 Validation stages", 1
        )[0]
        self.assertEqual(
            re.findall(r"^\d+\. `(CONTENT_[A-Z0-9_]+)`$", code_section, re.MULTILINE),
            [
                "CONTENT_LIMIT_EXCEEDED", "CONTENT_TRUNCATED",
                "CONTENT_BAD_VERSION", "CONTENT_BAD_RECORD_COUNT",
                "CONTENT_BAD_RECORD_ID", "CONTENT_RECORD_ORDER",
                "CONTENT_BAD_RECORD_KIND", "CONTENT_BAD_PAYLOAD_LENGTH",
                "CONTENT_TRAILING_DATA", "CONTENT_BAD_TAG",
                "CONTENT_RESERVED_NONZERO", "CONTENT_BAD_UTF8",
                "CONTENT_BAD_COUNT", "CONTENT_BAD_VALUE",
                "CONTENT_NONCANONICAL_ORDER", "CONTENT_DUPLICATE",
                "CONTENT_ZERO_REFERENCE", "CONTENT_FORWARD_REFERENCE",
                "CONTENT_MISSING_REFERENCE", "CONTENT_WRONG_REFERENCE_KIND",
                "CONTENT_SCHEMA_MISMATCH", "CONTENT_ROOT_COUNT",
                "CONTENT_ROOT_NOT_FINAL", "CONTENT_BAD_CONTROL_EDGE",
                "CONTENT_ORPHAN_RECORD", "CONTENT_BAD_RESPONSE_SCHEMA",
                "CONTENT_FORBIDDEN_ANSWER_DATA", "CONTENT_BAD_FEEDBACK",
                "CONTENT_BAD_PASSIVE_TRACE", "CONTENT_BUDGET_PROOF",
                "CONTENT_BAD_RUN_STATE",
            ],
        )

    def test_m1_owner_and_plan_alignment(self) -> None:
        chess = " ".join((ROOT / "spec/chess-v0.md").read_text().split())
        content = " ".join((ROOT / "spec/content-v0.md").read_text().split())
        plan = " ".join((ROOT / "docs/m1-plan.md").read_text().split())
        design = " ".join((ROOT / "docs/m1-spec.md").read_text().split())
        roadmap = " ".join((ROOT / "docs/roadmap.md").read_text().split())

        self.assertIn("`EN_PASSANT_NONE` is numeric zero", chess)
        self.assertIn("exactly `square_index + 1`", chess)
        self.assertIn("`ContentRejectCode` is a constants-owned `u16`", content)
        self.assertIn("P4-Python source -> P6 curriculum", plan)
        self.assertIn("P6-Python content -> P6 curriculum", plan)
        self.assertIn("Python source owner API from P4", plan)
        self.assertIn("Python generic-content validation from P6.1", plan)
        self.assertNotIn("P2 -> P6 curriculum", plan)
        self.assertIn(
            "each referenced stratum's typed owner call independently recomputes and passes",
            design,
        )
        self.assertIn(
            "each referenced stratum's typed owner call independently recomputes and passes",
            roadmap,
        )
        same_as_prior = (
            "an absent prior item selects first; a present empty prior response commits "
            "empty; a mechanically valid mapped response replays; and an incompatible "
            "mapping selects first"
        )
        self.assertIn(same_as_prior, design)
        self.assertIn(same_as_prior, roadmap)
        self.assertIn(
            "Before the first screened candidate or reserve starts result-bearing pretest, "
            "publish a tracked salted commitment",
            design,
        )
        self.assertIn(
            "Before the first screened candidate or reserve starts result-bearing pretest, "
            "publish a tracked salted commitment",
            roadmap,
        )
        self.assertNotIn("owns the numeric value of every symbolic code named here", chess)
        for owner in (chess, design):
            self.assertIn("records and mirrors them for generation", owner)
            self.assertIn("second normative assignment", owner)
        self.assertIn("canonical `a1..h8` order", chess)
        self.assertIn("`square_index` is `0..63`", chess)
        self.assertIn(
            "square order is `a1,b1,...,h1,a2,...,h8` and square index is `0..63`",
            design,
        )
        self.assertIn(
            "Nominal en-passant is `0` for none, otherwise `square_index + 1`",
            design,
        )
        self.assertIn(
            "The Python and Rust generic-content lanes remain independent and no-chess",
            plan,
        )
        self.assertIn("one presentation-identical neutral acknowledgement", design)
        self.assertIn("one presentation-identical neutral acknowledgement", roadmap)
        self.assertIn(
            "Result-bearing feedback for every screened slot, including unused reserves, "
            "is withheld until every selected learner's normal or fallback feedback "
            "window resolves",
            design,
        )
        self.assertIn(
            "result-bearing feedback for every screened slot, including unused reserves, "
            "remain withheld until every selected participant's normal or fallback "
            "feedback window has resolved",
            roadmap,
        )
        for protocol in (design, roadmap):
            self.assertIn("later private assessment manifest", protocol)
            self.assertIn("commitment byte framing", protocol)
            self.assertIn("first delayed attempt is the only attempt", protocol)
            self.assertIn(
                "closed interval from 36 through 60 hours after that learner's complete "
                "valid posttest",
                protocol,
            )
            self.assertIn(
                "posttest itself finishes by the slot's frozen posttest deadline",
                protocol,
            )
            self.assertIn("early, late, invalid, or missed first attempt", protocol)
            self.assertIn("without retry", protocol)
            self.assertIn(
                "valid in-window completion or at the +60-hour fallback deadline",
                protocol,
            )
        self.assertIn("reveal and verify both only after all selected windows resolve", design)
        self.assertIn(
            "reveal follows resolution of all selected normal or fallback windows",
            roadmap,
        )
        self.assertIn(
            "feedback embargo for that slot resolves 60 hours after that deadline",
            design,
        )
        self.assertIn(
            "that slot's feedback embargo resolves 60 hours after the deadline",
            roadmap,
        )


class RootCheckCLI(unittest.TestCase):
    SCRIPT = ROOT / "scripts/check"

    def run_check(self, *arguments: str, **kwargs) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.SCRIPT), *arguments],
            cwd=kwargs.get("cwd", ROOT),
            env=kwargs.get("env"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

    def test_usage_errors(self) -> None:
        for arguments in ((), ("unknown",), ("focused",), ("focused", "unknown"), ("full", "extra"), ("focused", "repo", "extra")):
            with self.subTest(arguments=arguments):
                result = self.run_check(*arguments)
                self.assertEqual(result.returncode, 2)
                self.assertIn("usage:", result.stderr)

    def fake_environment(self, root: Path, fail_child: bool) -> dict[str, str]:
        binary = root / "bin"
        binary.mkdir(parents=True)
        fake_rustc = binary / "rustc"
        fake_rustc.write_text("#!/bin/sh\necho 'rustc 1.97.1 (test)'\n")
        fake_rustc.chmod(0o755)
        git = binary / "git"
        git.write_text("#!/bin/sh\necho 'git version test'\n")
        git.chmod(0o755)
        uv = binary / "uv"
        uv.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = --version ]; then echo 'uv 0.11.29 (test)'; exit 0; fi\n"
            + (
                "case \" $* \" in *\" -c \"*) exit 0;; *) exit 1;; esac\n"
                if fail_child
                else "exit 0\n"
            )
        )
        uv.chmod(0o755)
        rustup = binary / "rustup"
        rustup.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = which ]; then echo \"${0%/*}/rustc\"; exit 0; fi\n"
            "if [ \"$4\" = --version ]; then echo 'cargo 1.97.1 (test)'; exit 0; fi\n"
            "exit 0\n"
        )
        rustup.chmod(0o755)
        environment = os.environ.copy()
        environment["PATH"] = str(binary)
        return environment

    def test_success_and_failed_child_are_classified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copied = root / "scripts/check"
            copied.parent.mkdir()
            copied.write_bytes(self.SCRIPT.read_bytes())
            copied.chmod(0o755)
            environment = self.fake_environment(root, fail_child=False)
            success = subprocess.run(
                [str(copied), "focused", "identity"], cwd=root, env=environment,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False
            )
            self.assertEqual(success.returncode, 0, success.stderr)
            failed_environment = self.fake_environment(root / "failed", fail_child=True)
            failure = subprocess.run(
                [str(copied), "focused", "identity"], cwd=root, env=failed_environment,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False
            )
            self.assertEqual(failure.returncode, 1)
            self.assertIn("identity", failure.stderr)

    def test_live_m1_areas_are_admitted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copied = root / "scripts/check"
            copied.parent.mkdir()
            copied.write_bytes(self.SCRIPT.read_bytes())
            copied.chmod(0o755)
            environment = self.fake_environment(root, fail_child=False)
            for area in ("chess", "content", "curriculum"):
                with self.subTest(area=area):
                    result = subprocess.run(
                        [str(copied), "focused", area],
                        cwd=root,
                        env=environment,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_dependency_cache_fails_actionably(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            environment = os.environ.copy()
            environment["CARGO_HOME"] = directory
            result = self.run_check("focused", "identity", env=environment)
            self.assertEqual(result.returncode, 1)
            self.assertIn("identity-rust failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
