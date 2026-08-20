from __future__ import annotations

import itertools
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

try:
    from golden_board import constants_codegen
except ImportError:
    constants_codegen = None

try:
    from golden_board import constants
except ImportError:
    constants = None


ROOT = Path(__file__).resolve().parents[2]
OWNER = ROOT / "spec" / "constants-v0.toml"
PYTHON_TARGET = ROOT / "python" / "golden_board" / "constants.py"
RUST_TARGET = ROOT / "crates" / "gb-foundation" / "src" / "constants.rs"

MINIMAL = b'''schema = "golden-board.constants/v0"

[[codes]]
name = "sample"
type = "u8"
minimum = 0
maximum = 255
reserved = [{ first = 1, last = 254 }]
values = [
  { name = "SAMPLE_ZERO", value = 0 },
  { name = "SAMPLE_LAST", value = 255 },
]

[[bits]]
name = "flag"
type = "u8"
reserved_mask = 254
values = [{ name = "FLAG_ONE", value = 1 }]

[[constant]]
name = "SAMPLE_LIMIT"
type = "u32"
value = 7
'''

EXPECTED_PYTHON = b'''"""Generated from spec/constants-v0.toml; do not edit."""

SAMPLE_ZERO: int = 0
SAMPLE_LAST: int = 255

FLAG_ONE: int = 1

SAMPLE_LIMIT: int = 7
'''

EXPECTED_RUST = b'''//! Generated from spec/constants-v0.toml; do not edit.

pub const SAMPLE_ZERO: u8 = 0;
pub const SAMPLE_LAST: u8 = 255;

pub const FLAG_ONE: u8 = 1;

pub const SAMPLE_LIMIT: u32 = 7;
'''

EXPECTED_GROUPS = {
    "side": (
        "SIDE_FIRST",
        "SIDE_SECOND",
    ),
    "square_code": (
        "SQUARE_EMPTY",
        "SQUARE_FIRST_PAWN",
        "SQUARE_FIRST_KNIGHT",
        "SQUARE_FIRST_BISHOP",
        "SQUARE_FIRST_ROOK",
        "SQUARE_FIRST_QUEEN",
        "SQUARE_FIRST_KING",
        "SQUARE_SECOND_PAWN",
        "SQUARE_SECOND_KNIGHT",
        "SQUARE_SECOND_BISHOP",
        "SQUARE_SECOND_ROOK",
        "SQUARE_SECOND_QUEEN",
        "SQUARE_SECOND_KING",
    ),
    "promotion": (
        "PROMOTION_NONE",
        "PROMOTION_QUEEN",
        "PROMOTION_ROOK",
        "PROMOTION_BISHOP",
        "PROMOTION_KNIGHT",
    ),
    "event": (
        "EVENT_MOVE",
        "EVENT_RESIGNATION",
        "EVENT_DRAW_AGREEMENT",
        "EVENT_CLAIM_THREEFOLD",
        "EVENT_CLAIM_50_MOVE",
    ),
    "score": (
        "SCORE_FIRST_WIN",
        "SCORE_SECOND_WIN",
        "SCORE_DRAW",
    ),
    "board_terminal": (
        "BOARD_TERMINAL_NONE",
        "BOARD_TERMINAL_CHECKMATE",
        "BOARD_TERMINAL_STALEMATE",
        "BOARD_TERMINAL_COMMON_DEAD",
    ),
    "game_status": (
        "GAME_STATUS_ACTIVE",
        "GAME_STATUS_CHECKMATE",
        "GAME_STATUS_STALEMATE",
        "GAME_STATUS_COMMON_DEAD",
        "GAME_STATUS_RESIGNED",
        "GAME_STATUS_AGREED",
        "GAME_STATUS_CLAIMED_THREEFOLD",
        "GAME_STATUS_CLAIMED_50_MOVE",
    ),
    "source_suffix": (
        "SUFFIX_NONE",
        "SUFFIX_CHECK",
        "SUFFIX_MATE",
    ),
    "predicate": (
        "PREDICATE_SETUP_TURN",
        "PREDICATE_OCCUPANCY",
        "PREDICATE_MOVE_LEGALITY",
        "PREDICATE_CONTROL",
        "PREDICATE_DEFENDED",
        "PREDICATE_KING_CHECK",
        "PREDICATE_ABSOLUTE_PIN",
        "PREDICATE_FORK_DOUBLE_ATTACK",
        "PREDICATE_DISCOVERED_ATTACK_CHECK",
        "PREDICATE_ESCAPE_SQUARE_CONTROL",
        "PREDICATE_PASSED_PAWN",
        "PREDICATE_OPEN_FILE",
        "PREDICATE_SEMI_OPEN_FILE",
        "PREDICATE_FINITE_PROMOTION_RACE",
        "PREDICATE_FINITE_MATING_GEOMETRY",
        "PREDICATE_TERMINAL_TRANSITION",
        "PREDICATE_HISTORY_CLAIM",
        "PREDICATE_DECLARATION_EVENT",
        "PREDICATE_SOURCE_SCORE_RELATION",
        "PREDICATE_MOVE_RECORD_REPLAY",
    ),
    "chess_reject": (
        "CHESS_OK",
        "CHESS_POSITION_LENGTH",
        "CHESS_POSITION_SQUARE_CODE",
        "CHESS_POSITION_SIDE_CODE",
        "CHESS_POSITION_CASTLING_RESERVED",
        "CHESS_POSITION_EN_PASSANT_CODE",
        "CHESS_MOVE_LENGTH",
        "CHESS_MOVE_RESERVED",
        "CHESS_MOVE_PROMOTION_CODE",
        "CHESS_MOVE_SAME_SQUARE",
        "CHESS_EVENT_LENGTH",
        "CHESS_EVENT_CODE",
        "CHESS_EVENT_SIDE_CODE",
        "CHESS_EVENT_TRAILING",
        "CHESS_PREDICATE_UNKNOWN",
        "CHESS_PREDICATE_SIGNATURE",
        "CHESS_LOCAL_FIRST_KING_COUNT",
        "CHESS_LOCAL_SECOND_KING_COUNT",
        "CHESS_LOCAL_FIRST_PAWN_COUNT",
        "CHESS_LOCAL_SECOND_PAWN_COUNT",
        "CHESS_LOCAL_FIRST_PIECE_COUNT",
        "CHESS_LOCAL_SECOND_PIECE_COUNT",
        "CHESS_LOCAL_PAWN_ON_LAST_RANK",
        "CHESS_LOCAL_KINGS_ADJACENT",
        "CHESS_LOCAL_BOTH_KINGS_CHECKED",
        "CHESS_LOCAL_INACTIVE_KING_CHECKED",
        "CHESS_LOCAL_CASTLING_FIRST_KINGSIDE",
        "CHESS_LOCAL_CASTLING_FIRST_QUEENSIDE",
        "CHESS_LOCAL_CASTLING_SECOND_KINGSIDE",
        "CHESS_LOCAL_CASTLING_SECOND_QUEENSIDE",
        "CHESS_LOCAL_EN_PASSANT_RANK",
        "CHESS_LOCAL_EN_PASSANT_TARGET_OCCUPIED",
        "CHESS_LOCAL_EN_PASSANT_PAWN",
        "CHESS_LOCAL_EN_PASSANT_ORIGIN_OCCUPIED",
        "CHESS_GAME_CLOSED",
        "CHESS_RESOURCE_HISTORY_PLIES",
        "CHESS_RESOURCE_PREDICATE_INPUT",
        "CHESS_MOVE_EMPTY_ORIGIN",
        "CHESS_MOVE_WRONG_SIDE",
        "CHESS_MOVE_FRIENDLY_DESTINATION",
        "CHESS_MOVE_KING_CAPTURE",
        "CHESS_MOVE_PROMOTION_MISSING",
        "CHESS_MOVE_PROMOTION_UNNEEDED",
        "CHESS_MOVE_CASTLING_RIGHT",
        "CHESS_MOVE_CASTLING_PATH",
        "CHESS_MOVE_CASTLING_FROM_CHECK",
        "CHESS_MOVE_CASTLING_THROUGH_CHECK",
        "CHESS_MOVE_CASTLING_INTO_CHECK",
        "CHESS_MOVE_EN_PASSANT_TARGET",
        "CHESS_MOVE_EN_PASSANT_GEOMETRY",
        "CHESS_MOVE_GEOMETRY",
        "CHESS_MOVE_BLOCKED",
        "CHESS_MOVE_PAWN_ADVANCE",
        "CHESS_MOVE_PAWN_CAPTURE",
        "CHESS_MOVE_PAWN_DOUBLE",
        "CHESS_MOVE_SELF_CHECK",
        "CHESS_EVENT_AGREEMENT_TOO_EARLY",
        "CHESS_EVENT_THREEFOLD_UNAVAILABLE",
        "CHESS_EVENT_50_MOVE_UNAVAILABLE",
        "CHESS_PREDICATE_TREE",
        "CHESS_RECORD_EMPTY",
        "CHESS_RECORD_CHECKMATE_SCORE",
        "CHESS_RECORD_DRAW_SCORE",
    ),
    "source_reject": (
        "SOURCE_INPUT_TOO_LARGE",
        "SOURCE_UTF8_BOM",
        "SOURCE_UTF8_INVALID",
        "SOURCE_CONTROL",
        "SOURCE_NEWLINE_BARE_CR",
        "SOURCE_NEWLINE_MIXED",
        "SOURCE_NEWLINE_FINAL_MISSING",
        "SOURCE_FENCE_SHAPE",
        "SOURCE_FENCE_ORPHAN_CLOSE",
        "SOURCE_FENCE_NESTED_OPEN",
        "SOURCE_FENCE_UNCLOSED",
        "SOURCE_FENCE_BLOCK_BYTES",
        "SOURCE_FENCE_COUNT",
        "SOURCE_TAG_COUNT",
        "SOURCE_TAG_NAME_LENGTH",
        "SOURCE_TAG_VALUE_LENGTH",
        "SOURCE_TAG_SYNTAX",
        "SOURCE_TAG_ESCAPE",
        "SOURCE_TAG_DUPLICATE",
        "SOURCE_TAG_FORBIDDEN",
        "SOURCE_TAG_RESULT_MISSING",
        "SOURCE_TAG_RESULT_VALUE",
        "SOURCE_SEPARATOR_MISSING",
        "SOURCE_SEPARATOR_EXTRA",
        "SOURCE_MOVETEXT_MISSING",
        "SOURCE_MOVETEXT_EMPTY_LINE",
        "SOURCE_MOVETEXT_TAG_LINE",
        "SOURCE_MOVETEXT_LEADING_HWS",
        "SOURCE_MOVETEXT_TRAILING_HWS",
        "SOURCE_RESOURCE_TOKEN_COUNT",
        "SOURCE_RESOURCE_RECORD_PLIES",
        "SOURCE_RESOURCE_TOTAL_PLIES",
        "SOURCE_MOVE_NUMBER_SHAPE",
        "SOURCE_MOVE_NUMBER_VALUE",
        "SOURCE_MOVE_NUMBER_POSITION",
        "SOURCE_RESULT_TOO_EARLY",
        "SOURCE_RESULT_TOKEN",
        "SOURCE_RESULT_MISSING",
        "SOURCE_RESULT_MISMATCH",
        "SOURCE_TOKEN_AFTER_RESULT",
        "SOURCE_GAME_AFTER_TERMINAL",
        "SOURCE_SAN_SHAPE",
        "SOURCE_SAN_NO_MATCH",
        "SOURCE_SAN_AMBIGUOUS",
        "SOURCE_SAN_NONCANONICAL",
        "SOURCE_SAN_SUFFIX",
        "SOURCE_TERMINAL_SCORE",
        "SOURCE_DUPLICATE_MOVE_STREAM",
        "SOURCE_GAME_COUNT",
        "SOURCE_GAME_TRUNCATED",
        "SOURCE_GAME_MOVE",
        "SOURCE_GAME_SCORE",
        "SOURCE_GAME_TRAILING",
        "SOURCE_GAME_SEMANTIC",
        "SOURCE_GAME_SET_SIZE",
        "SOURCE_GAME_SET_COUNT",
        "SOURCE_GAME_SET_TRUNCATED",
        "SOURCE_GAME_SET_TOTAL_PLIES",
        "SOURCE_GAME_SET_ORDER",
        "SOURCE_GAME_SET_DUPLICATE",
        "SOURCE_GAME_SET_TRAILING",
        "SOURCE_ANTHOLOGY_COUNT",
        "SOURCE_ANTHOLOGY_DUPLICATE_STREAM",
        "SOURCE_EVIDENCE_SIZE",
        "SOURCE_EVIDENCE_SHAPE",
        "SOURCE_EVIDENCE_NONCANONICAL",
        "SOURCE_EVIDENCE_HASH",
        "SOURCE_EVIDENCE_CROSS_FIELD",
        "SOURCE_CANDIDATE_MISMATCH",
        "SOURCE_EVIDENCE_INSTALL",
    ),
    "content_record_kind": (
        "CONTENT_KIND_TEXT",
        "CONTENT_KIND_ATOM_SCHEMA",
        "CONTENT_KIND_ATOM_VECTOR",
        "CONTENT_KIND_MATRIX",
        "CONTENT_KIND_FIELD_SCHEMA",
        "CONTENT_KIND_TUPLE",
        "CONTENT_KIND_REGION_SET",
        "CONTENT_KIND_SEMANTIC_BINDING",
        "CONTENT_KIND_OPAQUE_DATA",
        "CONTENT_KIND_PREDICATE_RESULT",
        "CONTENT_KIND_FEEDBACK",
        "CONTENT_KIND_PASSIVE_TRACE",
        "CONTENT_KIND_LESSON_NODE",
        "CONTENT_KIND_ROOT",
    ),
    "content_atom_class": (
        "ATOM_UNSIGNED",
        "ATOM_ENUM",
        "ATOM_MASK",
    ),
    "content_field_storage": (
        "FIELD_INLINE_ATOM",
        "FIELD_RECORD_REF",
    ),
    "content_binding_class": (
        "BINDING_DATA",
        "BINDING_PREDICATE",
    ),
    "content_feedback": (
        "FEEDBACK_NEUTRAL",
        "FEEDBACK_MATCH",
        "FEEDBACK_NO_MATCH",
        "FEEDBACK_ALTERNATIVE",
        "FEEDBACK_LIMITATION",
    ),
    "content_action": (
        "ACTION_SELECT",
        "ACTION_RESET",
        "ACTION_COMMIT",
    ),
    "content_response_shape": (
        "RESPONSE_SINGLE",
        "RESPONSE_SET",
        "RESPONSE_SEQUENCE",
    ),
    "content_outcome": (
        "OUTCOME_NONE",
        "OUTCOME_ACCEPTED",
        "OUTCOME_REJECTED",
        "OUTCOME_NEUTRAL",
    ),
    "content_lesson_role": (
        "ROLE_EXACT_RULE",
        "ROLE_OBSERVABLE_RELATION",
        "ROLE_WORKED_EXAMPLE",
        "ROLE_HEURISTIC",
        "ROLE_PRACTICE",
    ),
    "content_answer_mode": (
        "ANSWER_PACKED_PRACTICE",
        "ANSWER_EXTERNAL",
        "ANSWER_UNSCORED",
    ),
    "content_case_class": (
        "CASE_ACCEPTED",
        "CASE_REJECTED_SPECIAL",
    ),
    "content_interaction_result": (
        "INTERACTION_SELECTED",
        "INTERACTION_RESET",
        "INTERACTION_COMMITTED",
        "INTERACTION_INVALID_ACTION",
        "INTERACTION_INVALID_REGION",
        "INTERACTION_DUPLICATE",
        "INTERACTION_OVER_LIMIT",
        "INTERACTION_ALREADY_COMMITTED",
        "INTERACTION_BUDGET_EXHAUSTED",
    ),
    "content_phase": (
        "PHASE_ACTIVE",
        "PHASE_COMMITTED",
        "PHASE_EXHAUSTED",
    ),
    "content_reject": (
        "CONTENT_OK",
        "CONTENT_LIMIT_EXCEEDED",
        "CONTENT_TRUNCATED",
        "CONTENT_BAD_VERSION",
        "CONTENT_BAD_RECORD_COUNT",
        "CONTENT_BAD_RECORD_ID",
        "CONTENT_RECORD_ORDER",
        "CONTENT_BAD_RECORD_KIND",
        "CONTENT_BAD_PAYLOAD_LENGTH",
        "CONTENT_TRAILING_DATA",
        "CONTENT_BAD_TAG",
        "CONTENT_RESERVED_NONZERO",
        "CONTENT_BAD_UTF8",
        "CONTENT_BAD_COUNT",
        "CONTENT_BAD_VALUE",
        "CONTENT_NONCANONICAL_ORDER",
        "CONTENT_DUPLICATE",
        "CONTENT_ZERO_REFERENCE",
        "CONTENT_FORWARD_REFERENCE",
        "CONTENT_MISSING_REFERENCE",
        "CONTENT_WRONG_REFERENCE_KIND",
        "CONTENT_SCHEMA_MISMATCH",
        "CONTENT_ROOT_COUNT",
        "CONTENT_ROOT_NOT_FINAL",
        "CONTENT_BAD_CONTROL_EDGE",
        "CONTENT_ORPHAN_RECORD",
        "CONTENT_BAD_RESPONSE_SCHEMA",
        "CONTENT_FORBIDDEN_ANSWER_DATA",
        "CONTENT_BAD_FEEDBACK",
        "CONTENT_BAD_PASSIVE_TRACE",
        "CONTENT_BUDGET_PROOF",
        "CONTENT_BAD_RUN_STATE",
    ),
    "castling_rights": (
        "CASTLING_FIRST_KINGSIDE",
        "CASTLING_FIRST_QUEENSIDE",
        "CASTLING_SECOND_KINGSIDE",
        "CASTLING_SECOND_QUEENSIDE",
    ),
    "content_region_flags": (
        "REGION_SELECTABLE",
        "REGION_HIGHLIGHTED",
    ),
    "content_lesson_flags": (
        "LESSON_ALLOW_REPEATED_SELECTIONS",
    ),
}


def replace(data: bytes, old: bytes, new: bytes) -> bytes:
    if old not in data:
        raise AssertionError(old)
    return data.replace(old, new, 1)


class ConstantsCodegen(unittest.TestCase):
    def test_exact_miniature_render(self) -> None:
        self.assertIsNotNone(constants_codegen)
        self.assertEqual(
            constants_codegen._render(MINIMAL),
            (EXPECTED_PYTHON, EXPECTED_RUST),
        )

    @unittest.skipIf(constants_codegen is None, "implementation not present")
    def test_closed_model_mutations_reject(self) -> None:
        second_code = b'''
[[codes]]
name = "other"
type = "u8"
minimum = 0
maximum = 255
reserved = [{ first = 1, last = 255 }]
values = [{ name = "OTHER_ZERO", value = 0 }]
'''
        cases = {
            "bom": b"\xef\xbb\xbf" + MINIMAL,
            "cr": MINIMAL.replace(b"\n", b"\r\n"),
            "no terminal lf": MINIMAL[:-1],
            "bad utf8": MINIMAL[:-1] + b"\xff\n",
            "unknown top key": replace(
                MINIMAL,
                b'schema = "golden-board.constants/v0"\n',
                b'schema = "golden-board.constants/v0"\nextra = 1\n',
            ),
            "missing top key": MINIMAL.replace(b"schema = \"golden-board.constants/v0\"\n", b""),
            "bad schema": replace(MINIMAL, b"constants/v0", b"constants/v1"),
            "empty category": replace(
                replace(
                    MINIMAL,
                    b'''[[bits]]
name = "flag"
type = "u8"
reserved_mask = 254
values = [{ name = "FLAG_ONE", value = 1 }]
''',
                    b"",
                ),
                b'schema = "golden-board.constants/v0"\n',
                b'schema = "golden-board.constants/v0"\nbits = []\n',
            ),
            "unknown entry key": replace(MINIMAL, b'name = "sample"', b'name = "sample"\nextra = 1'),
            "missing entry key": replace(MINIMAL, b"maximum = 255\n", b""),
            "unknown value key": replace(MINIMAL, b'name = "SAMPLE_ZERO", value = 0', b'name = "SAMPLE_ZERO", value = 0, extra = 1'),
            "missing value key": replace(MINIMAL, b'name = "SAMPLE_ZERO", value = 0', b'name = "SAMPLE_ZERO"'),
            "unknown reserved key": replace(MINIMAL, b'first = 1, last = 254', b'first = 1, last = 254, extra = 1'),
            "missing reserved key": replace(MINIMAL, b'first = 1, last = 254', b'first = 1'),
            "unknown bit key": replace(MINIMAL, b'reserved_mask = 254', b'reserved_mask = 254\nextra = 1'),
            "missing bit key": replace(MINIMAL, b'reserved_mask = 254\n', b''),
            "unknown scalar key": replace(MINIMAL, b'value = 7', b'value = 7\nextra = 1'),
            "missing scalar key": replace(MINIMAL, b'value = 7\n', b''),
            "bad code type": replace(MINIMAL, b'type = "u8"', b'type = "u32"'),
            "non-string code type": replace(MINIMAL, b'type = "u8"', b'type = []'),
            "bad scalar type": replace(MINIMAL, b'type = "u32"', b'type = "u16"'),
            "bad group name": replace(MINIMAL, b'name = "sample"', b'name = "Sample"'),
            "bad symbol name": replace(MINIMAL, b'SAMPLE_ZERO', b'sample_zero'),
            "bool integer": replace(MINIMAL, b'value = 0', b'value = true'),
            "negative": replace(MINIMAL, b'value = 0', b'value = -1'),
            "type overflow": replace(MINIMAL, b'value = 255', b'value = 256'),
            "minimum above maximum": replace(
                replace(MINIMAL, b'minimum = 0', b'minimum = 255'),
                b'maximum = 255',
                b'maximum = 254',
            ),
            "value outside domain": replace(MINIMAL, b'maximum = 255', b'maximum = 254'),
            "member in reserved": replace(MINIMAL, b'value = 255', b'value = 254'),
            "duplicate member value": replace(MINIMAL, b'value = 255', b'value = 0'),
            "member order": replace(
                MINIMAL,
                b'''  { name = "SAMPLE_ZERO", value = 0 },
  { name = "SAMPLE_LAST", value = 255 },''',
                b'''  { name = "SAMPLE_LAST", value = 255 },
  { name = "SAMPLE_ZERO", value = 0 },''',
            ),
            "undeclared hole": replace(MINIMAL, b'last = 254', b'last = 253'),
            "reversed reserved": replace(MINIMAL, b'first = 1, last = 254', b'first = 254, last = 1'),
            "reserved outside domain": replace(MINIMAL, b'first = 1, last = 254', b'first = 1, last = 256'),
            "reserved overlap": replace(MINIMAL, b'{ first = 1, last = 254 }', b'{ first = 1, last = 200 }, { first = 200, last = 254 }'),
            "reserved adjacent": replace(MINIMAL, b'{ first = 1, last = 254 }', b'{ first = 1, last = 200 }, { first = 201, last = 254 }'),
            "reserved order": replace(MINIMAL, b'{ first = 1, last = 254 }', b'{ first = 201, last = 254 }, { first = 1, last = 200 }'),
            "duplicate group": MINIMAL + second_code.replace(b'name = "other"', b'name = "sample"'),
            "duplicate symbol": MINIMAL + second_code.replace(b'OTHER_ZERO', b'SAMPLE_ZERO'),
            "zero bit": replace(MINIMAL, b'value = 1 }]', b'value = 0 }]'),
            "non one hot bit": replace(MINIMAL, b'value = 1 }]', b'value = 3 }]'),
            "bit overflow": replace(MINIMAL, b'value = 1 }]', b'value = 256 }]'),
            "bit reserved overlap": replace(MINIMAL, b'reserved_mask = 254', b'reserved_mask = 255'),
            "bit incomplete": replace(MINIMAL, b'reserved_mask = 254', b'reserved_mask = 252'),
            "duplicate bit value": replace(
                MINIMAL,
                b'values = [{ name = "FLAG_ONE", value = 1 }]',
                b'values = [{ name = "FLAG_A", value = 1 }, { name = "FLAG_B", value = 1 }]',
            ),
            "bit order": replace(
                MINIMAL,
                b'reserved_mask = 254\nvalues = [{ name = "FLAG_ONE", value = 1 }]',
                b'reserved_mask = 252\nvalues = [{ name = "FLAG_TWO", value = 2 }, { name = "FLAG_ONE", value = 1 }]',
            ),
        }
        for name, data in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(constants_codegen.ConstantsError):
                    constants_codegen._render(data)

        alias = MINIMAL + second_code.replace(b"OTHER_ZERO", b"SAMPLE_LIMIT")
        with self.assertRaises(constants_codegen.ConstantsError):
            constants_codegen._render(alias)

    @unittest.skipIf(constants_codegen is None, "implementation not present")
    def test_output_cap_rejects_before_return(self) -> None:
        with mock.patch.object(constants_codegen, "MAX_OUTPUT_BYTES", 100):
            with self.assertRaises(constants_codegen.ConstantsError):
                constants_codegen._render(MINIMAL)

    @unittest.skipIf(constants_codegen is None, "implementation not present")
    def test_safe_bounded_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exact = root / "exact"
            exact.write_bytes(b"x" * 10)
            with mock.patch.object(constants_codegen, "MAX_INPUT_BYTES", 10):
                self.assertEqual(constants_codegen._read(exact, 10), b"x" * 10)
                exact.write_bytes(b"x" * 11)
                with self.assertRaises(constants_codegen.ConstantsError):
                    constants_codegen._read(exact, 10)
            target = root / "target"
            target.write_bytes(b"x")
            link = root / "link"
            link.symlink_to(target)
            for path in (link, root):
                with self.subTest(path=path.name):
                    with self.assertRaises(constants_codegen.ConstantsError):
                        constants_codegen._read(path, 10)

    @unittest.skipIf(constants_codegen is None, "implementation not present")
    def test_read_rejects_preopen_fifo_swap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input"
            path.write_bytes(b"x")
            real_open = os.open

            def swap_then_open(target: Path, flags: int) -> int:
                self.assertTrue(flags & os.O_NONBLOCK)
                path.unlink()
                os.mkfifo(path)
                return real_open(target, flags)

            with mock.patch.object(constants_codegen.os, "open", swap_then_open):
                with self.assertRaises(constants_codegen.ConstantsError):
                    constants_codegen._read(path, 10)

    @unittest.skipIf(constants_codegen is None, "implementation not present")
    def test_read_rejects_same_inode_preopen_size_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input"
            path.write_bytes(b"x")
            real_open = os.open

            def mutate_then_open(target: Path, flags: int) -> int:
                path.write_bytes(b"xx")
                return real_open(target, flags)

            with mock.patch.object(constants_codegen.os, "open", mutate_then_open):
                with self.assertRaises(constants_codegen.ConstantsError):
                    constants_codegen._read(path, 10)

    @unittest.skipIf(constants_codegen is None, "implementation not present")
    def test_read_rejects_postread_same_size_path_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "input"
            replacement = root / "replacement"
            path.write_bytes(b"abcd")
            replacement.write_bytes(b"wxyz")
            real_read = os.read
            replaced = False

            def read_then_replace(descriptor: int, length: int) -> bytes:
                nonlocal replaced
                data = real_read(descriptor, length)
                if data and not replaced:
                    os.replace(replacement, path)
                    replaced = True
                return data

            with mock.patch.object(constants_codegen.os, "read", read_then_replace):
                with self.assertRaises(constants_codegen.ConstantsError):
                    constants_codegen._read(path, 10)

    @unittest.skipIf(constants_codegen is None, "implementation not present")
    def test_read_rejects_same_inode_during_read_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input"
            path.write_bytes(b"abcd")
            before = path.stat()
            real_read = os.read
            mutated = False

            def read_then_mutate(descriptor: int, length: int) -> bytes:
                nonlocal mutated
                data = real_read(descriptor, length)
                if data and not mutated:
                    path.write_bytes(b"wxyz")
                    os.utime(
                        path,
                        ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000),
                    )
                    mutated = True
                return data

            with mock.patch.object(constants_codegen.os, "read", read_then_mutate):
                with self.assertRaises(constants_codegen.ConstantsError):
                    constants_codegen._read(path, 10)

    @unittest.skipIf(constants_codegen is None, "implementation not present")
    def test_read_rejects_post_fstat_path_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "input"
            replacement = root / "replacement"
            path.write_bytes(b"abcd")
            replacement.write_bytes(b"wxyz")
            real_fstat = os.fstat
            calls = 0

            def fstat_then_replace(descriptor: int) -> os.stat_result:
                nonlocal calls
                snapshot = real_fstat(descriptor)
                calls += 1
                if calls == 2:
                    os.replace(replacement, path)
                return snapshot

            with mock.patch.object(constants_codegen.os, "fstat", fstat_then_replace):
                with self.assertRaises(constants_codegen.ConstantsError):
                    constants_codegen._read(path, 10)

    @unittest.skipIf(constants_codegen is None, "implementation not present")
    def test_actual_owner_and_semantic_agreement(self) -> None:
        model = constants_codegen._parse(constants_codegen._read(OWNER))
        names = [
            value["name"]
            for category in ("codes", "bits")
            for group in model[category]
            for value in group["values"]
        ] + [value["name"] for value in model["constant"]]
        self.assertEqual(
            (len(model["codes"]), len(model["bits"]), len(model["constant"])),
            (25, 3, 65),
        )
        self.assertEqual(len(names), 358)
        self.assertEqual(len(names), len(set(names)))
        groups_by_name = {
            group["name"]: tuple(value["name"] for value in group["values"])
            for category in ("codes", "bits")
            for group in model[category]
        }
        self.assertEqual(tuple(groups_by_name), tuple(EXPECTED_GROUPS))
        self.assertEqual(groups_by_name, EXPECTED_GROUPS)

        specs = {
            owner: (ROOT / f"spec/{owner}-v0.md").read_text()
            for owner in ("chess", "source", "content")
        }
        chess_groups = {
            "side", "square_code", "castling_rights", "promotion", "event",
            "score", "board_terminal", "game_status", "predicate", "chess_reject",
        }
        source_groups = {"source_suffix", "source_reject"}
        for group_name, group_names in groups_by_name.items():
            owner = (
                "chess"
                if group_name in chess_groups
                else "source"
                if group_name in source_groups
                else "content"
            )
            for name in group_names:
                with self.subTest(owner=owner, owner_occurrence=name):
                    self.assertRegex(specs[owner], rf"\b{re.escape(name)}\b")
        for scalar in model["constant"]:
            name = scalar["name"]
            owner = (
                "source"
                if name.startswith("SOURCE_")
                else "content"
                if name.startswith("CONTENT_")
                else "chess"
            )
            with self.subTest(owner=owner, owner_occurrence=name):
                self.assertRegex(specs[owner], rf"\b{re.escape(name)}\b")

        scalar_names = tuple(value["name"] for value in model["constant"])
        self.assertIn("SOURCE_ANTHOLOGY_GAME_COUNT", scalar_names)
        self.assertNotIn("SOURCE_REQUIRED_BLOCKS", scalar_names)
        scalar_values = {value["name"]: value["value"] for value in model["constant"]}
        self.assertEqual(scalar_values["SOURCE_ANTHOLOGY_GAME_COUNT"], 64)
        source_flat = " ".join(specs["source"].split())
        for fragment in (
            "SourceCandidate { SOURCE_ANTHOLOGY_GAME_COUNT CompiledGames",
            "requires exactly `SOURCE_ANTHOLOGY_GAME_COUNT` already valid records",
            "| Recognized blocks | exactly 64 | `SOURCE_ANTHOLOGY_GAME_COUNT` |",
            "requires exactly `SOURCE_ANTHOLOGY_GAME_COUNT` valid blocks",
            "emit `u16_be(SOURCE_ANTHOLOGY_GAME_COUNT)`",
            "ordinals `0..SOURCE_ANTHOLOGY_GAME_COUNT - 1`",
            "`game_count` is `SOURCE_ANTHOLOGY_GAME_COUNT`",
            "sums to `SOURCE_ANTHOLOGY_GAME_COUNT`",
            "Exactly `SOURCE_ANTHOLOGY_GAME_COUNT` structurally valid opener/closer pairs are required.",
            "For more than `SOURCE_ANTHOLOGY_GAME_COUNT` pairs, count points at opener number `SOURCE_ANTHOLOGY_GAME_COUNT + 1`.",
            "locked source acceptance requires `SOURCE_ANTHOLOGY_GAME_COUNT` records",
        ):
            with self.subTest(source_binding=fragment):
                self.assertIn(fragment, source_flat)

        groups = {
            group["name"]: [value["value"] for value in group["values"]]
            for group in model["codes"]
        }
        self.assertEqual(groups["predicate"], list(range(1, 21)))
        self.assertEqual(groups["chess_reject"], list(range(63)))
        self.assertEqual(groups["source_reject"], list(range(1, 71)))
        self.assertEqual(groups["content_record_kind"], list(range(1, 15)))
        self.assertEqual(groups["content_reject"], list(range(32)))
        source_reject = next(group for group in model["codes"] if group["name"] == "source_reject")
        self.assertEqual(source_reject["reserved"][0], {"first": 0, "last": 0})
        self.assertNotIn("SOURCE_OK", names)
        for deleted in (
            "CHESS_MAX_SQUARE_LIST",
            "CONTENT_MAX_BUFFER_IDS",
            "CONTENT_MAX_TRACE_ACTIONS",
        ):
            self.assertNotIn(deleted, names)
        self.assertTrue(all(value["type"] == "u32" for value in model["constant"]))

    @unittest.skipIf(constants is None, "generated constants not present")
    def test_fixed_chess_and_content_formulas(self) -> None:
        first = [
            constants.SQUARE_FIRST_ROOK,
            constants.SQUARE_FIRST_KNIGHT,
            constants.SQUARE_FIRST_BISHOP,
            constants.SQUARE_FIRST_QUEEN,
            constants.SQUARE_FIRST_KING,
            constants.SQUARE_FIRST_BISHOP,
            constants.SQUARE_FIRST_KNIGHT,
            constants.SQUARE_FIRST_ROOK,
        ]
        second = [
            constants.SQUARE_SECOND_ROOK,
            constants.SQUARE_SECOND_KNIGHT,
            constants.SQUARE_SECOND_BISHOP,
            constants.SQUARE_SECOND_QUEEN,
            constants.SQUARE_SECOND_KING,
            constants.SQUARE_SECOND_BISHOP,
            constants.SQUARE_SECOND_KNIGHT,
            constants.SQUARE_SECOND_ROOK,
        ]
        position = bytes(
            first
            + [constants.SQUARE_FIRST_PAWN] * 8
            + [constants.SQUARE_EMPTY] * (constants.CHESS_SQUARE_COUNT - 32)
            + [constants.SQUARE_SECOND_PAWN] * 8
            + second
            + [
                constants.SIDE_FIRST,
                constants.CASTLING_FIRST_KINGSIDE
                | constants.CASTLING_FIRST_QUEENSIDE
                | constants.CASTLING_SECOND_KINGSIDE
                | constants.CASTLING_SECOND_QUEENSIDE,
                constants.EN_PASSANT_NONE,
            ]
        )
        self.assertEqual(len(position) - 3, constants.CHESS_SQUARE_COUNT)
        self.assertEqual(constants.CHESS_SQUARE_COUNT, 1 << 6)
        self.assertEqual(len(position), constants.CHESS_POSITION_BYTES)
        self.assertEqual(
            position.hex(),
            "0402030506030204010101010101010100000000000000000000000000000000"
            "0000000000000000000000000000000007070707070707070a08090b0c09080a"
            "000f00",
        )
        masks = {
            "origin": constants.CHESS_MOVE_ORIGIN_MASK,
            "destination": constants.CHESS_MOVE_DESTINATION_MASK,
            "promotion": constants.CHESS_MOVE_PROMOTION_MASK,
            "reserved": constants.CHESS_MOVE_RESERVED_MASK,
        }
        square_bits = (constants.CHESS_SQUARE_COUNT - 1).bit_length()
        reserved_bits = 1
        promotion_bits = 3
        promotion_shift = reserved_bits
        destination_shift = promotion_shift + promotion_bits
        origin_shift = destination_shift + square_bits
        self.assertEqual(
            (
                constants.CHESS_MOVE_ORIGIN_SHIFT,
                constants.CHESS_MOVE_DESTINATION_SHIFT,
                constants.CHESS_MOVE_PROMOTION_SHIFT,
            ),
            (origin_shift, destination_shift, promotion_shift),
        )
        self.assertEqual(masks["origin"], ((1 << square_bits) - 1) << origin_shift)
        self.assertEqual(
            masks["destination"],
            ((1 << square_bits) - 1) << destination_shift,
        )
        self.assertEqual(
            masks["promotion"],
            ((1 << promotion_bits) - 1) << promotion_shift,
        )
        self.assertEqual(masks["reserved"], (1 << reserved_bits) - 1)
        for left, right in itertools.combinations(masks.values(), 2):
            self.assertEqual(left & right, 0)
        self.assertEqual(
            masks["origin"] | masks["destination"] | masks["promotion"] | masks["reserved"],
            (1 << (8 * constants.CHESS_MOVE_BYTES)) - 1,
        )

        self.assertEqual(
            2 + 2 * constants.SOURCE_MAX_GAME_SET_PLIES + 3 * constants.SOURCE_MAX_GAME_SET_GAMES,
            constants.SOURCE_MAX_GAME_SET_BYTES,
        )
        self.assertEqual(constants.SOURCE_MAX_GAME_PLIES, 4_096)
        self.assertEqual(constants.REGION_SELECTABLE | constants.REGION_HIGHLIGHTED | 252, 255)
        self.assertEqual(constants.LESSON_ALLOW_REPEATED_SELECTIONS | 254, 255)
        model = constants_codegen._parse(constants_codegen._read(OWNER))
        action = next(group for group in model["codes"] if group["name"] == "content_action")
        self.assertEqual(action["reserved"][0], {"first": 0, "last": 0})
        action_values = {value["value"] for value in action["values"]}
        sentinel = bytes((action["reserved"][0]["first"], 0, 0, 0))
        self.assertNotIn(sentinel[0], action_values)
        self.assertEqual(sentinel, b"\0\0\0\0")
        event_bytes = constants.CONTENT_EVENT_BYTES * constants.CONTENT_MAX_EVENT_BUDGET
        self.assertEqual(
            constants.CONTENT_RUN_STATE_FIXED_BYTES
            + constants.CONTENT_MAX_COMMITTED_RESPONSE_BYTES
            + event_bytes,
            constants.CONTENT_MAX_RUN_STATE_BYTES,
        )
        self.assertEqual(
            constants.CONTENT_RUN_STATE_FIXED_BYTES
            + 2 * constants.CONTENT_MAX_SELECTIONS
            + event_bytes,
            constants.CONTENT_MAX_EXHAUSTED_RUN_STATE_BYTES,
        )

    @unittest.skipIf(constants_codegen is None, "implementation not present")
    def test_tracked_projections_and_drift_are_read_only(self) -> None:
        expected = constants_codegen._render(constants_codegen._read(OWNER))
        self.assertEqual(constants_codegen._read(PYTHON_TARGET), expected[0])
        self.assertEqual(constants_codegen._read(RUST_TARGET), expected[1])
        for data, pattern in (
            (expected[0], rb"^([A-Z][A-Z0-9_]*): int ="),
            (expected[1], rb"^pub const ([A-Z][A-Z0-9_]*):"),
        ):
            names = re.findall(pattern, data, re.MULTILINE)
            self.assertEqual(len(names), len(set(names)))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            python_target = root / "constants.py"
            rust_target = root / "constants.rs"
            python_target.write_bytes(expected[0] + b"# drift\n")
            rust_target.write_bytes(expected[1])
            before = (python_target.read_bytes(), rust_target.read_bytes())
            self.assertEqual(
                constants_codegen._drift(OWNER, python_target, rust_target),
                [python_target],
            )
            self.assertEqual(before, (python_target.read_bytes(), rust_target.read_bytes()))
            with self.assertRaises(constants_codegen.ConstantsError):
                constants_codegen._read(python_target, len(expected[0]) - 1)

    @unittest.skipIf(constants_codegen is None, "implementation not present")
    def test_check_from_root_and_nested_cwd_leaves_status_unchanged(self) -> None:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "python")
        before = subprocess.run(
            ["git", "status", "--porcelain=v1"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
        for cwd in (ROOT, ROOT / "python" / "tests"):
            with self.subTest(cwd=cwd):
                result = subprocess.run(
                    [sys.executable, "-m", "golden_board.constants_codegen", "check"],
                    cwd=cwd,
                    env=environment,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
        after = subprocess.run(
            ["git", "status", "--porcelain=v1"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
