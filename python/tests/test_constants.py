from __future__ import annotations

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
        owners = "\n".join(
            (ROOT / path).read_text()
            for path in ("spec/chess-v0.md", "spec/source-v0.md", "spec/content-v0.md")
        )
        for name in names:
            with self.subTest(owner_occurrence=name):
                self.assertRegex(owners, rf"\b{re.escape(name)}\b")

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
            + [constants.SQUARE_EMPTY] * 32
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
        self.assertEqual(len(position), constants.CHESS_POSITION_BYTES)
        self.assertEqual(
            position.hex(),
            "0402030506030204010101010101010100000000000000000000000000000000"
            "0000000000000000000000000000000007070707070707070a08090b0c09080a"
            "000f00",
        )
        masks = (
            constants.CHESS_MOVE_ORIGIN_MASK,
            constants.CHESS_MOVE_DESTINATION_MASK,
            constants.CHESS_MOVE_PROMOTION_MASK,
            constants.CHESS_MOVE_RESERVED_MASK,
        )
        self.assertEqual(sum(masks), 65_535)
        self.assertEqual(masks[0] & masks[1] | masks[0] & masks[2] | masks[1] & masks[2], 0)
        self.assertEqual(63 << constants.CHESS_MOVE_ORIGIN_SHIFT & ~masks[0], 0)
        self.assertEqual(63 << constants.CHESS_MOVE_DESTINATION_SHIFT & ~masks[1], 0)
        self.assertEqual(constants.PROMOTION_KNIGHT << constants.CHESS_MOVE_PROMOTION_SHIFT & ~masks[2], 0)

        self.assertEqual(
            2 + 2 * constants.SOURCE_MAX_GAME_SET_PLIES + 3 * constants.SOURCE_MAX_GAME_SET_GAMES,
            constants.SOURCE_MAX_GAME_SET_BYTES,
        )
        self.assertEqual(constants.SOURCE_MAX_GAME_PLIES, 4_096)
        self.assertEqual(constants.REGION_SELECTABLE | constants.REGION_HIGHLIGHTED | 252, 255)
        self.assertEqual(constants.LESSON_ALLOW_REPEATED_SELECTIONS | 254, 255)
        self.assertEqual(bytes((0, 0, 0, 0)), b"\0\0\0\0")
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
