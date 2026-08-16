"""Independent source-v0 compiler checks."""

from __future__ import annotations

import functools
import hashlib
import io
import json
from pathlib import Path
import unittest
from unittest import mock

from golden_board.canonical_manifest import validate_canonical_manifest
from golden_board import canonical_manifest
from golden_board import constants as C


ROOT = Path(__file__).resolve().parents[2]
_FILE_CAP = canonical_manifest.MAX_BYTES


def _read_bounded(path: Path, cap: int = _FILE_CAP) -> bytes:
    with path.open("rb") as source:
        raw = source.read(cap + 1)
    if len(raw) > cap:
        raise ValueError(f"bounded test input exceeds {cap} bytes")
    return raw


FIXTURE_BYTES = _read_bounded(ROOT / "conformance/source-v0.json")
FIXTURE = validate_canonical_manifest(FIXTURE_BYTES)
LOCKED = _read_bounded(ROOT / "docs/64_games.md")


def _outcome(source: object, operation: str, value: object) -> dict[str, object]:
    try:
        getattr(source, operation)(value)
    except source.SourceReject as reject:
        return {
            "rejection": {
                "code": reject.code,
                "raw_start": reject.raw_start,
                "raw_end": reject.raw_end,
            }
        }
    return {"accept": {}}


@functools.lru_cache(maxsize=128)
def _decode_typed_game(source: object, raw: bytes) -> object:
    return source.decode_game(raw)


def _typed_recipe_input(source: object, row: dict[str, object]) -> tuple[object, ...]:
    if (
        type(row) is not dict
        or set(row) != {
            "count_cap", "expected", "input", "input_bytes", "input_sha256",
            "name", "operation", "recipe",
        }
        or type(row["count_cap"]) is not int
        or not 0 <= row["count_cap"] <= 65_536
        or type(row["input_bytes"]) is not int
        or not 0 <= row["input_bytes"] <= _FILE_CAP
        or type(row["input_sha256"]) is not str
        or len(row["input_sha256"]) != 64
        or type(row["input"]) is not dict
        or type(row["recipe"]) is not str
    ):
        raise AssertionError("closed typed recipe record")
    inputs = row["input"]
    kind = row["recipe"]
    if kind == "typed-game-set-games":
        if (
            set(inputs) != {"count", "unit_hex"}
            or type(inputs["count"]) is not int
            or not 0 <= inputs["count"] <= row["count_cap"]
            or type(inputs["unit_hex"]) is not str
        ):
            raise AssertionError("closed typed game-count recipe")
        unit = _checked_hex(inputs["unit_hex"])
        if (
            len(unit) * inputs["count"] != row["input_bytes"]
            or hashlib.sha256(unit * inputs["count"]).hexdigest() != row["input_sha256"]
        ):
            raise AssertionError("typed game-count recipe bytes")
        return (_decode_typed_game(source, unit),) * inputs["count"]

    if kind not in ("typed-game-set-total-plies", "typed-anthology") or set(inputs) != {
        "cycle_moves_hex", "ply_counts", "score",
    }:
        raise AssertionError("closed typed recipe kind")
    counts = inputs["ply_counts"]
    if (
        type(counts) is not list
        or len(counts) > row["count_cap"]
        or not counts
        or any(type(count) is not int or not 1 <= count <= 4096 for count in counts)
        or type(inputs["cycle_moves_hex"]) is not str
        or type(inputs["score"]) is not int
        or inputs["score"] not in (0, 1, 2)
    ):
        raise AssertionError("bounded typed recipe fields")
    cycle = _checked_hex(inputs["cycle_moves_hex"])
    if len(cycle) != 8:
        raise AssertionError("four-move typed recipe cycle")
    games = []
    digest = hashlib.sha256()
    length = 0
    for count in counts:
        moves = (cycle * ((count + 3) // 4))[: count * 2]
        raw = count.to_bytes(2, "big") + moves + bytes((inputs["score"],))
        digest.update(raw)
        length += len(raw)
        games.append(_decode_typed_game(source, raw))
    if length != row["input_bytes"] or digest.hexdigest() != row["input_sha256"]:
        raise AssertionError("typed recipe byte identity")
    return tuple(games)


def _checked_hex(value: object) -> bytes:
    if (
        type(value) is not str
        or len(value) > 2 * (_FILE_CAP + 1)
        or len(value) % 2
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise AssertionError("bounded lowercase hex")
    return bytes.fromhex(value)


def _recipe_bytes(row: dict[str, object]) -> bytes:
    if (
        type(row) is not dict
        or type(row.get("input")) is not dict
        or type(row.get("input_bytes")) is not int
        or not 0 <= row["input_bytes"] <= _FILE_CAP + 1
        or type(row.get("input_sha256")) is not str
        or len(row["input_sha256"]) != 64
        or type(row.get("recipe")) is not str
    ):
        raise AssertionError("closed byte recipe record")
    inputs = row["input"]
    kind = row["recipe"]
    if kind == "literal-repeat":
        if (
            set(row) != {
                "count_cap", "expected", "input", "input_bytes", "input_sha256",
                "name", "operation", "recipe",
            }
            or set(inputs) != {"prefix_hex", "repeat_count", "repeat_hex", "suffix_hex"}
            or type(row["count_cap"]) is not int
            or not 0 <= row["count_cap"] <= _FILE_CAP + 1
            or type(inputs["repeat_count"]) is not int
            or not 0 <= inputs["repeat_count"] <= row["count_cap"]
        ):
            raise AssertionError("closed literal-repeat recipe")
        prefix = _checked_hex(inputs["prefix_hex"])
        repeated = _checked_hex(inputs["repeat_hex"])
        suffix = _checked_hex(inputs["suffix_hex"])
        if len(prefix) + len(repeated) * inputs["repeat_count"] + len(suffix) != row["input_bytes"]:
            raise AssertionError("literal-repeat derived length")
        raw = (
            prefix
            + repeated * inputs["repeat_count"]
            + suffix
        )
    elif kind == "locked-base-patch":
        if (
            set(row) != {
                "expected", "input", "input_bytes", "input_sha256", "name",
                "operation", "patch_cap", "recipe",
            }
            or set(inputs) != {"base", "patches"}
            or inputs["base"] != "locked-anthology"
            or type(row["patch_cap"]) is not int
            or not 0 <= row["patch_cap"] <= 4
            or type(inputs["patches"]) is not list
            or len(inputs["patches"]) > row["patch_cap"]
        ):
            raise AssertionError("closed locked-base recipe")
        raw_buffer = bytearray(LOCKED)
        prior = len(LOCKED) + 1
        for patch in inputs["patches"]:
            if (
                type(patch) is not dict
                or set(patch) != {"old_hex", "replacement_hex", "start"}
                or type(patch["start"]) is not int
            ):
                raise AssertionError("closed source patch")
            old = _checked_hex(patch["old_hex"])
            replacement = _checked_hex(patch["replacement_hex"])
            start = patch["start"]
            if (
                len(raw_buffer) - len(old) + len(replacement) > _FILE_CAP + 1
                or not 0 <= start <= start + len(old) <= prior <= len(LOCKED) + 1
            ):
                raise AssertionError("unbounded or overlapping fixture patch")
            if raw_buffer[start : start + len(old)] != old:
                raise AssertionError("fixture patch old bytes differ")
            raw_buffer[start : start + len(old)] = replacement
            prior = start
        raw = bytes(raw_buffer)
    elif kind == "knight-cycle-corpus":
        if (
            set(row) != {
                "count_cap", "expected", "input", "input_bytes", "input_sha256",
                "name", "operation", "recipe",
            }
            or set(inputs) not in (
                {"cycle", "ply_counts", "result"},
                {"cycle", "newline_hex", "ply_counts", "result"},
            )
            or type(row["count_cap"]) is not int
            or not 0 <= row["count_cap"] <= 64
            or type(inputs["cycle"]) is not list
            or inputs["cycle"] != ["Nf3", "Nf6", "Ng1", "Ng8"]
            or type(inputs["ply_counts"]) is not list
            or len(inputs["ply_counts"]) > row["count_cap"]
            or any(
                type(count) is not int or not 1 <= count <= 4096
                for count in inputs["ply_counts"]
            )
            or sum(inputs["ply_counts"]) > 65_536
            or inputs["result"] != "1/2-1/2"
        ):
            raise AssertionError("closed knight-cycle recipe")
        newline = _checked_hex(inputs.get("newline_hex", "0a"))
        if newline not in (b"\n", b"\r\n"):
            raise AssertionError("closed recipe newline")
        cycle = tuple(token.encode("ascii") for token in inputs["cycle"])
        blocks = []
        for count in inputs["ply_counts"]:
            tokens = []
            for ply in range(count):
                if ply % 2 == 0:
                    tokens.append(f"{ply // 2 + 1}.".encode("ascii"))
                tokens.append(cycle[ply % len(cycle)])
            tokens.append(inputs["result"].encode("ascii"))
            blocks.append(
                newline.join(
                    (b"```pgn", b'[Result "1/2-1/2"]', b"", b" ".join(tokens), b"```", b"")
                )
            )
        raw = b"".join(blocks)
    else:
        raise AssertionError(f"not a byte recipe: {kind}")
    if len(raw) != row["input_bytes"] or hashlib.sha256(raw).hexdigest() != row["input_sha256"]:
        raise AssertionError("fixture recipe length/digest mismatch")
    return raw


def _locked_blocks() -> tuple[bytes, ...]:
    blocks = []
    start: int | None = None
    offset = 0
    for line in LOCKED.splitlines(keepends=True):
        logical = line.removesuffix(b"\n")
        if start is None and logical.startswith(b"```pgn"):
            start = offset
        elif start is not None and logical.rstrip(b" \t") == b"```":
            blocks.append(LOCKED[start : offset + len(line)])
            start = None
        offset += len(line)
    if start is not None or len(blocks) != 64:
        raise AssertionError("locked source block extraction")
    return tuple(blocks)


class SourceCompilerApi(unittest.TestCase):
    def test_candidate_evidence_is_canonical_validated_and_fail_closed(self) -> None:
        from golden_board import source_compiler as source, source_doctor

        opened = source_doctor.read_locked_source(
            ROOT, source_doctor.load_source_lock(ROOT)
        )
        self.assertTrue(opened.lock_match)
        evidence = source.EvidenceInputs(
            source=opened.data,
            chess_v0=_read_bounded(ROOT / "spec/chess-v0.md"),
            source_v0=_read_bounded(ROOT / "spec/source-v0.md"),
            identity_v0=_read_bounded(ROOT / "spec/identity-v0.md"),
            constants_v0=_read_bounded(ROOT / "spec/constants-v0.toml"),
        )
        candidate = source.compile_source(opened.data)
        candidate_bytes = source.encode_candidate_trace(candidate, evidence)
        self.assertEqual(validate_canonical_manifest(candidate_bytes)["ply_count"], 4_915)
        validated = source.validate_candidate_trace(
            candidate_bytes, candidate.game_set_bytes, evidence
        )
        retained = source.coordinate_candidates(validated, validated)
        report = validate_canonical_manifest(retained.report_bytes)
        self.assertEqual(report["schema"], "golden-board-source-compilation-v0")
        self.assertEqual(report["producer_labels"], ["python", "rust"])
        source.validate_retained_evidence(
            retained.report_bytes, retained.game_set_bytes, evidence
        )
        tracked_report = _read_bounded(ROOT / "reports/source-compilation-v0.json")
        tracked_set = _read_bounded(ROOT / "reports/game-set-v0.bin")
        self.assertEqual(tracked_report, retained.report_bytes)
        self.assertEqual(tracked_set, retained.game_set_bytes)
        source.validate_retained_evidence(tracked_report, tracked_set, evidence)

        for report_bytes, game_set_bytes, code in (
            (tracked_report + b" ", tracked_set, C.SOURCE_EVIDENCE_NONCANONICAL),
            (
                tracked_report,
                tracked_set[:-1] + bytes([tracked_set[-1] ^ 1]),
                C.SOURCE_EVIDENCE_CROSS_FIELD,
            ),
        ):
            with self.assertRaises(source.SourceReject) as caught:
                source.validate_retained_evidence(
                    report_bytes, game_set_bytes, evidence
                )
            self.assertEqual(
                (caught.exception.code, caught.exception.raw_start, caught.exception.raw_end),
                (code, 0, 0),
            )

        rows = [
            row for key in ("cases", "recipes") for row in FIXTURE[key]
            if row["operation"] == "validate_candidate_trace"
        ]
        self.assertEqual(len(rows), 6)
        for row in rows:
            raw = bytes.fromhex(row["input_hex"]) if "input_hex" in row else _recipe_bytes(row)
            with self.subTest(row["name"]), self.assertRaises(source.SourceReject) as caught:
                source.validate_candidate_trace(raw, b"", evidence)
            self.assertEqual(
                (caught.exception.code, caught.exception.raw_start, caught.exception.raw_end),
                (
                    row["expected"]["rejection"]["code"],
                    row["expected"]["rejection"]["raw_start"],
                    row["expected"]["rejection"]["raw_end"],
                ),
            )

        mismatched = source._make(
            source.ValidatedCandidate,
            candidate_bytes=candidate_bytes + b" ",
            game_set_bytes=candidate.game_set_bytes,
        )
        with self.assertRaises(source.SourceReject) as caught:
            source.coordinate_candidates(validated, mismatched)
        self.assertEqual(
            (caught.exception.code, caught.exception.raw_start, caught.exception.raw_end),
            (C.SOURCE_CANDIDATE_MISMATCH, 0, 0),
        )

    def test_fixture_operation_inventory_is_closed(self) -> None:
        rows = [*FIXTURE["cases"], *FIXTURE["recipes"]]
        portable_operations = {
            "compile_source",
            "decode_game",
            "decode_game_set",
            "encode_game_set",
            "validate_anthology",
        }
        portable = [row for row in rows if row["operation"] in portable_operations]
        deferred = [row for row in rows if row["operation"] == "validate_candidate_trace"]
        self.assertEqual(len(portable), 180)
        self.assertEqual(len(deferred), 6)
        self.assertEqual(
            {row["operation"] for row in rows},
            portable_operations | {"validate_candidate_trace"},
        )
        self.assertEqual(len({row["name"] for row in rows}), len(rows))

    def test_fixture_adapter_bounds_before_recipe_construction(self) -> None:
        with mock.patch.object(
            Path,
            "open",
            return_value=io.BytesIO(b"x" * (_FILE_CAP + 1)),
        ):
            with self.assertRaisesRegex(ValueError, "bounded test input"):
                _read_bounded(Path("ignored"))

        recipes = {row["name"]: row for row in FIXTURE["recipes"]}
        byte_mutations = (
            ("raw-input-too-large", "repeat_count", 10**100),
            ("tag-count-64-boundary", "patch-start", True),
            ("resource-total-plies-65535", "ply_counts", [10**100]),
        )
        for name, field, replacement in byte_mutations:
            row = json.loads(json.dumps(recipes[name]))
            if field == "patch-start":
                row["input"]["patches"][0]["start"] = replacement
            else:
                row["input"][field] = replacement
            with self.subTest(recipe=name, field=field):
                with self.assertRaisesRegex(AssertionError, "recipe|patch"):
                    _recipe_bytes(row)

        class DecodeMustNotRun:
            @staticmethod
            def decode_game(raw: bytes) -> object:
                raise AssertionError(f"decoded {len(raw)} attacker bytes")

        typed_mutations = (
            ("binary-game-set-count-65535", "count", 10**100),
            ("binary-game-set-total-plies-65535", "cycle_moves_hex", "00" * (_FILE_CAP + 1)),
            ("binary-anthology-count-64", "ply_counts", [1] * 66),
        )
        for name, field, replacement in typed_mutations:
            row = json.loads(json.dumps(recipes[name]))
            row["input"][field] = replacement
            with self.subTest(recipe=name, field=field):
                with self.assertRaisesRegex(AssertionError, "recipe|hex"):
                    _typed_recipe_input(DecodeMustNotRun(), row)

    def test_public_api_is_present(self) -> None:
        from golden_board import source_compiler as source

        self.assertEqual(
            source.__all__,
            (
                "CompiledGame",
                "GameRecord",
                "SourceCandidate",
                "SourceReject",
                "compile_source",
                "decode_game",
                "decode_game_set",
                "encode_game",
                "encode_game_set",
                "validate_anthology",
            ),
        )
        public_callables = {
            name
            for name, value in vars(source).items()
            if not name.startswith("_")
            and callable(value)
            and getattr(value, "__module__", None) == source.__name__
        }
        self.assertEqual(set(source.__all__), public_callables)
        self.assertEqual(len(source.__all__), len(set(source.__all__)))

    def test_direct_and_recipe_binary_cases(self) -> None:
        from golden_board import source_compiler as source

        rows = [
            row
            for row in FIXTURE["cases"]
            if row["operation"] in ("decode_game", "decode_game_set")
        ]
        rows += [
            row
            for row in FIXTURE["recipes"]
            if row["operation"] in ("decode_game", "decode_game_set")
        ]
        self.assertEqual(len(rows), 21)
        for row in rows:
            with self.subTest(row["name"]):
                raw = (
                    bytes.fromhex(row["input_hex"])
                    if "input_hex" in row
                    else _recipe_bytes(row)
                )
                self.assertEqual(
                    _outcome(source, row["operation"], raw),
                    row["expected"],
                )

    def test_typed_encoder_and_anthology_recipes(self) -> None:
        from golden_board import source_compiler as source

        rows = [
            row
            for row in FIXTURE["recipes"]
            if row["operation"] in ("encode_game_set", "validate_anthology")
        ]
        self.assertEqual(len(rows), 8)
        for row in rows:
            with self.subTest(row["name"]):
                self.assertEqual(
                    _outcome(source, row["operation"], _typed_recipe_input(source, row)),
                    row["expected"],
                )

    def test_aggregate_bounds_precede_codec_work(self) -> None:
        from golden_board import source_compiler as source

        rows = {row["name"]: row for row in FIXTURE["recipes"]}
        over_total = _typed_recipe_input(
            source, rows["binary-game-set-total-plies-65536"]
        )
        with mock.patch.object(source, "encode_game", side_effect=AssertionError("encoded")):
            self.assertEqual(
                _outcome(source, "encode_game_set", over_total),
                rows["binary-game-set-total-plies-65536"]["expected"],
            )

        with mock.patch.object(source.chess, "decode_move", side_effect=AssertionError("decoded")):
            self.assertEqual(
                _outcome(source, "decode_game", bytes.fromhex("1001")),
                {"rejection": {"code": 49, "raw_start": 0, "raw_end": 2}},
            )
        game_4096 = _recipe_bytes(rows["binary-game-count-4096"])
        encoded_set = b"\0\x10" + game_4096 * 16
        with mock.patch.object(source, "_decode_game_at", side_effect=AssertionError("decoded")):
            self.assertEqual(
                _outcome(source, "decode_game_set", encoded_set),
                {"rejection": {"code": 58, "raw_start": 122_927, "raw_end": 122_929}},
            )
        with mock.patch.object(source, "_profile", side_effect=AssertionError("profiled")):
            self.assertEqual(
                _outcome(source, "compile_source", b"x" * 1_048_577),
                {"rejection": {"code": 1, "raw_start": 1_048_576, "raw_end": 1_048_577}},
            )
        resource = rows["resource-total-plies-65536"]
        with mock.patch.object(source, "_structure", side_effect=AssertionError("structured")):
            self.assertEqual(
                _outcome(source, "compile_source", _recipe_bytes(resource)),
                resource["expected"],
            )

    def test_game_set_decodes_every_game_before_canonical_order(self) -> None:
        from golden_board import source_compiler as source

        short = bytes.fromhex("000131c000")
        long = bytes.fromhex("00043550d24039e0edf001")
        invalid = bytes.fromhex("0001000100")
        for name, prefix in (
            ("order", long + short),
            ("duplicate", short + short),
        ):
            raw = b"\0\3" + prefix + invalid
            invalid_start = 2 + len(prefix) + 2
            with self.subTest(name=name):
                self.assertEqual(
                    _outcome(source, "decode_game_set", raw),
                    {
                        "rejection": {
                            "code": C.SOURCE_GAME_MOVE,
                            "raw_start": invalid_start,
                            "raw_end": invalid_start + 2,
                        }
                    },
                )

    def test_result_escape_must_decode_before_result_value(self) -> None:
        from golden_board import source_compiler as source

        raw = LOCKED.replace(b'[Result "0-1"]', b'[Result "0\\q1"]', 1)
        escape = raw.index(b"\\q")
        self.assertEqual(
            _outcome(source, "compile_source", raw),
            {
                "rejection": {
                    "code": C.SOURCE_TAG_ESCAPE,
                    "raw_start": escape,
                    "raw_end": escape + 2,
                }
            },
        )

    def test_exhausted_block_missing_spans_use_content_end(self) -> None:
        from golden_board import source_compiler as source

        for newline in (b"\n", b"\r\n"):
            valid = newline.join(
                (
                    b"```pgn",
                    b'[Result "0-1"]',
                    b"",
                    b"1. f3 e5 2. g4 Qh4# 0-1",
                    b"```",
                    b"",
                )
            )
            for name, tag, code in (
                ("result", b'[Opaque "x"]', C.SOURCE_TAG_RESULT_MISSING),
                ("separator", b'[Result "0-1"]', C.SOURCE_SEPARATOR_MISSING),
            ):
                bad = newline.join((b"```pgn", tag, b"```", b""))
                content_end = bad.index(b"```", 3)
                with self.subTest(newline=newline, name=name):
                    self.assertEqual(
                        _outcome(source, "compile_source", bad + valid * 63),
                        {
                            "rejection": {
                                "code": code,
                                "raw_start": content_end,
                                "raw_end": content_end,
                            }
                        },
                    )

    def test_tag_value_cap_precedes_decoded_growth(self) -> None:
        from golden_board import source_compiler as source

        row = next(
            row
            for row in FIXTURE["recipes"]
            if row["name"] == "tag-value-1025"
        )

        class CapGuard(bytearray):
            def append(self, value: int) -> None:
                if len(self) >= C.SOURCE_MAX_TAG_VALUE_BYTES:
                    raise AssertionError("decoded beyond tag cap")
                super().append(value)

        with mock.patch.object(source, "bytearray", CapGuard, create=True):
            self.assertEqual(
                _outcome(source, "compile_source", _recipe_bytes(row)),
                row["expected"],
            )

    def test_compile_source_replays_semantics_on_every_call(self) -> None:
        from golden_board import source_compiler as source

        source.compile_source(LOCKED)
        with mock.patch.object(
            source.chess,
            "new_game",
            side_effect=AssertionError("fresh semantic replay required"),
        ):
            with self.assertRaisesRegex(AssertionError, "fresh semantic replay required"):
                source.compile_source(LOCKED)

    def test_stage_two_uses_lowest_raw_start_across_defect_families(self) -> None:
        from golden_board import source_compiler as source

        self.assertEqual(
            _outcome(source, "compile_source", b"\0\xff\n"),
            {"rejection": {"code": 4, "raw_start": 0, "raw_end": 1}},
        )
        self.assertEqual(
            _outcome(source, "compile_source", b"\xff\0\n"),
            {"rejection": {"code": 3, "raw_start": 0, "raw_end": 1}},
        )

    def test_semantic_lookup_tables_are_read_only(self) -> None:
        from golden_board import source_compiler as source

        for name in ("_PIECE_KIND", "_PIECE_LETTER", "_PROMOTION", "_PROMOTION_LETTER"):
            table = getattr(source, name)
            key = next(iter(table))
            with self.subTest(name=name), self.assertRaises(TypeError):
                table[key] = table[key]

    def test_game_values_are_opaque_and_round_trip(self) -> None:
        from golden_board import source_compiler as source

        for authority in (source.GameRecord, source.CompiledGame, source.SourceCandidate):
            with self.subTest(authority=authority.__name__):
                with self.assertRaises(TypeError):
                    authority()
        raw = bytes.fromhex("000131c000")
        record = source.decode_game(raw)
        self.assertEqual(source.encode_game(record), raw)
        self.assertEqual(source.encode_game_set((record,)), b"\0\1" + raw)
        self.assertEqual(source.decode_game_set(b"\0\1" + raw), (record,))

    def test_locked_anthology_is_complete_and_atomic(self) -> None:
        from golden_board import source_compiler as source

        candidate = source.compile_source(LOCKED)
        self.assertEqual(len(candidate.games), 64)
        self.assertEqual(tuple(game.source_ordinal for game in candidate.games), tuple(range(64)))
        self.assertEqual(sum(len(game.record.moves) for game in candidate.games), 4_915)
        self.assertTrue(
            all(len(game.rows) == len(game.record.moves) for game in candidate.games)
        )
        for compiled in candidate.games:
            opener_start, opener_end = compiled.opener_span
            self.assertTrue(LOCKED[opener_start:opener_end].startswith(b"```pgn"))
            game = source.chess.new_game()
            for row, move in zip(compiled.rows, compiled.record.moves, strict=True):
                start, end, move_hex, position_hex, suffix = row
                self.assertTrue(0 <= start < end <= len(LOCKED))
                self.assertEqual(move_hex, source.chess.encode_move(move).hex())
                event = source.chess.decode_event(
                    bytes((C.EVENT_MOVE,)) + source.chess.encode_move(move)
                )
                game = source.chess.apply_event(game, event)
                self.assertEqual(
                    position_hex,
                    source.chess.encode_position(game.replay.position).hex(),
                )
                checked = source.chess.king_in_check(
                    source.chess.validate_local(game.replay.position),
                    game.replay.position.side_to_move,
                )
                truth = (
                    C.SUFFIX_MATE
                    if game.status == C.GAME_STATUS_CHECKMATE
                    else C.SUFFIX_CHECK if checked else C.SUFFIX_NONE
                )
                self.assertEqual(suffix, truth)
        records = tuple(game.record for game in candidate.games)
        self.assertEqual(candidate.game_set_bytes, source.encode_game_set(records))
        decoded = source.decode_game_set(candidate.game_set_bytes)
        self.assertEqual(
            tuple(map(source.encode_game, decoded)),
            tuple(sorted(map(source.encode_game, records))),
        )

        before = (
            candidate.game_set_bytes,
            candidate.games[0].rows,
            candidate.games[-1].record,
        )
        damaged = LOCKED[:-1] + b"\0\n"
        self.assertEqual(
            _outcome(source, "compile_source", damaged),
            {"rejection": {"code": 4, "raw_start": len(LOCKED) - 1, "raw_end": len(LOCKED)}},
        )
        self.assertEqual(
            before,
            (
                candidate.game_set_bytes,
                candidate.games[0].rows,
                candidate.games[-1].record,
            ),
        )

    def test_metadata_wrapping_newlines_and_block_order_do_not_enter_game_set(self) -> None:
        from golden_board import source_compiler as source

        blocks = _locked_blocks()
        expected = source.compile_source(LOCKED).game_set_bytes
        transformed = {
            "opaque-tags": LOCKED.replace(
                b'[Result "', b'[Opaque "ignored"]\n[Result "'
            ),
            "outer-prose": b"opaque outer prose \xe2\x98\x83\n" + b"".join(blocks) + b"tail\t\n",
            "uniform-crlf": LOCKED.replace(b"\n", b"\r\n"),
            "rewrapped-hws": LOCKED.replace(
                b"1. e4 c5 2. Nf3", b"1.\te4\nc5  2. Nf3", 1
            ),
        }
        for rotation in (1, 7, 31, 63):
            transformed[f"block-rotation-{rotation}"] = b"".join(
                blocks[rotation:] + blocks[:rotation]
            )
        for name, raw in transformed.items():
            with self.subTest(transformation=name):
                self.assertEqual(source.compile_source(raw).game_set_bytes, expected)

    def test_named_source_mutants_are_killed(self) -> None:
        from golden_board import source_compiler as source

        rows = {row["name"]: row for row in FIXTURE["recipes"]}
        suffix = _outcome(
            source, "compile_source", _recipe_bytes(rows["san-suffix-extra-check"])
        )
        self.assertEqual(suffix, rows["san-suffix-extra-check"]["expected"])
        self.assertNotEqual(suffix, {"accept": {}})

        geometric = _outcome(
            source,
            "compile_source",
            _recipe_bytes(rows["accept-san-pinned-pseudo-mover-excluded"]),
        )
        self.assertEqual(
            geometric, rows["accept-san-pinned-pseudo-mover-excluded"]["expected"]
        )
        for mutant_code in (44, 45):
            self.assertNotEqual(
                geometric,
                {
                    "rejection": {
                        "code": mutant_code,
                        "raw_start": 12_474,
                        "raw_end": 12_477,
                    }
                },
            )

        terminal = _outcome(
            source, "compile_source", _recipe_bytes(rows["terminal-after-checkmate"])
        )
        self.assertEqual(terminal, rows["terminal-after-checkmate"]["expected"])
        self.assertNotEqual(
            terminal,
            {"rejection": {"code": 43, "raw_start": 12_422, "raw_end": 12_424}},
        )
        precedence = _outcome(
            source,
            "compile_source",
            _recipe_bytes(rows["terminal-continuation-precedes-earlier-suffix"]),
        )
        self.assertEqual(
            precedence, rows["terminal-continuation-precedes-earlier-suffix"]["expected"]
        )
        self.assertNotEqual(
            precedence,
            {"rejection": {"code": 46, "raw_start": 12_417, "raw_end": 12_418}},
        )

    def test_raw_compile_fixture(self) -> None:
        from golden_board import source_compiler as source

        rows = [row for row in FIXTURE["cases"] if row["operation"] == "compile_source"]
        rows += [row for row in FIXTURE["recipes"] if row["operation"] == "compile_source"]
        self.assertEqual(len(rows), 151)
        for row in rows:
            raw = bytes.fromhex(row["input_hex"]) if "input_hex" in row else _recipe_bytes(row)
            with self.subTest(row["name"]):
                self.assertEqual(_outcome(source, "compile_source", raw), row["expected"])


if __name__ == "__main__":
    unittest.main()
