from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from math import isqrt
from pathlib import Path
import unittest

from golden_board import canonical_manifest, chess, m2_damage, m2_decoder


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "studies/m2/templates/technical/channel-mechanics-fixtures.json"


class ParticipantObservationMechanics(unittest.TestCase):
    def test_published_fixtures_parse_and_serialize_with_production_code(self) -> None:
        document = canonical_manifest.validate_canonical_manifest(FIXTURES.read_bytes())
        self.assertEqual(document["schema"], "golden-board.m2-technical-channel-fixtures/v0")
        channels = set()
        for fixture in document["fixtures"]:
            channel = fixture["channel"]
            channels.add(channel)
            raw = bytes.fromhex(fixture["hex"])
            with self.subTest(channel=channel, raw=raw.hex()):
                if channel == m2_decoder.OBS_BITS:
                    count = fixture["expected_cell_count"]
                    self.assertEqual(int.from_bytes(raw[:4], "big"), count)
                    self.assertEqual(len(raw), 4 + (count + 7) // 8)
                    cells = m2_damage._bits(raw[4:], count)
                    self.assertEqual(m2_damage._obs_bits(cells), raw)
                    side = isqrt(count)
                    if side * side == count:
                        self.assertEqual(m2_decoder._parse_bits(raw), (side, bytes(cells)))
                    else:
                        # Packing examples need not be square artifacts. Their
                        # storage validity must not bypass carrier geometry.
                        with self.assertRaisesRegex(m2_decoder.DecoderError, "geometry"):
                            m2_decoder._parse_bits(raw)
                elif channel == m2_decoder.OBS_MATRIX:
                    side, cells = m2_decoder._parse_matrix(raw)
                    self.assertEqual(side, fixture["expected_side"])
                    self.assertEqual(m2_damage._obs_matrix(side, cells), raw)
                elif channel == m2_decoder.OBS_UNITS:
                    units = m2_decoder._parse_units(raw, 16)
                    self.assertEqual(len(units), fixture["expected_entry_count"])
                    order = [unit.unit_id for unit in units]
                    self.assertEqual(order, fixture["expected_ids"])
                    self.assertEqual(
                        m2_damage._obs_units(
                            order, {unit.unit_id: unit.encoded for unit in units}
                        ),
                        raw,
                    )
                else:
                    self.fail(f"unknown fixture channel {channel!r}")
        self.assertEqual(
            channels,
            {m2_decoder.OBS_BITS, m2_decoder.OBS_MATRIX, m2_decoder.OBS_UNITS},
        )

    def test_bits_are_msb_first_and_low_unused_bits_are_zero(self) -> None:
        cells = bytes((1, 0, 1, 0, 0, 1, 0, 1, 1))
        raw = bytes.fromhex("00000009a580")
        self.assertEqual(m2_damage._obs_bits(cells), raw)
        self.assertEqual(m2_decoder._parse_bits(raw), (3, cells))
        for malformed in (
            b"", bytes.fromhex("00000000"), raw[:-1], raw + b"\0",
            bytes.fromhex("00000009a581"), bytes.fromhex("0040000180"),
        ):
            with self.subTest(raw=malformed.hex()), self.assertRaises(m2_decoder.DecoderError):
                m2_decoder._parse_bits(malformed)

    def test_matrix_uses_u16_side_and_preserves_erasure_cells(self) -> None:
        cells = bytes((0, 2, 1, 0))
        raw = bytes.fromhex("000200020100")
        self.assertEqual(m2_damage._obs_matrix(2, cells), raw)
        self.assertEqual(m2_decoder._parse_matrix(raw), (2, cells))
        for malformed in (
            # The former participant fixture used a four-byte side.
            bytes.fromhex("0000000200010100"),
            bytes.fromhex("000200030100"), bytes.fromhex("000000"),
            raw[:-1], raw + b"\0",
        ):
            with self.subTest(raw=malformed.hex()), self.assertRaises(m2_decoder.DecoderError):
                m2_decoder._parse_matrix(malformed)

    def test_units_preserve_order_and_do_not_invent_missing_ids(self) -> None:
        raw = bytes.fromhex("0000000200000009000200ff000000020001a5")
        payloads = {2: b"\xa5", 9: b"\0\xff"}
        self.assertEqual(m2_damage._obs_units((9, 2), payloads), raw)
        parsed = m2_decoder._parse_units(raw, 2)
        self.assertEqual(
            [(unit.unit_id, unit.encoded) for unit in parsed],
            [(9, b"\0\xff"), (2, b"\xa5")],
        )
        empty = bytes.fromhex("00000000")
        self.assertEqual(m2_damage._obs_units((), {}), empty)
        self.assertEqual(m2_decoder._parse_units(empty, 2), ())
        with self.assertRaisesRegex(m2_decoder.DecoderError, "length"):
            m2_decoder._parse_units(raw, 1)

    def test_units_reject_invalid_ids_lengths_and_duplicate_entries(self) -> None:
        malformed = (
            bytes.fromhex("00000001000000000001a5"),  # zero ID
            bytes.fromhex("00000001000000020000"),  # empty payload
            bytes.fromhex("00000002000000020001a500000002000100"),
            bytes.fromhex("00000001000000020002a5"),  # truncated payload
            bytes.fromhex("00000001000000"),  # truncated header
            bytes.fromhex("00000001000000020001a500"),  # trailing byte
            bytes.fromhex("00000001000000020100") + bytes(256),
        )
        for raw in malformed:
            with self.subTest(raw=raw[:20].hex()), self.assertRaises(m2_decoder.DecoderError):
                m2_decoder._parse_units(raw, 2)


class ParticipantOutputMechanics(unittest.TestCase):
    def test_degraded_output_can_contain_both_streams(self) -> None:
        # This tests the output contract, not validity of synthetic content.
        result = m2_decoder.DecodeResult(
            "degraded", "eh72-hier-r5-r2-r1-crc32c-v0",
            (m2_decoder.SectionResult(9, "incomplete", None),), (), True,
            m2_required_stream=b"required", m2_all_stream=b"complete",
        )
        raw = m2_decoder.render_decoder_result(m2_decoder.OBS_UNITS, result, schema_version=1)
        rendered = canonical_manifest.validate_canonical_manifest(raw)
        self.assertEqual(rendered["artifact_state"], "degraded")
        self.assertTrue(rendered["m2_required_available"])
        self.assertTrue(rendered["m2_all_available"])
        self.assertEqual(rendered["m2_all_stream_sha256"], sha256(b"complete").hexdigest())
        with self.assertRaisesRegex(m2_decoder.DecoderError, "result-shape"):
            m2_decoder.render_decoder_result(
                m2_decoder.OBS_UNITS,
                replace(result, artifact_state="exact"),
                schema_version=1,
            )

    def test_required_only_output_and_invalid_complete_without_required(self) -> None:
        result = m2_decoder.DecodeResult(
            "degraded", "eh72-hier-r5-r2-r1-crc32c-v0",
            (m2_decoder.SectionResult(9, "incomplete", None),), (), True,
            m2_required_stream=b"required",
        )
        rendered = canonical_manifest.validate_canonical_manifest(
            m2_decoder.render_decoder_result(m2_decoder.OBS_UNITS, result, schema_version=1)
        )
        self.assertTrue(rendered["m2_required_available"])
        self.assertFalse(rendered["m2_all_available"])
        self.assertEqual(rendered["m2_all_stream_sha256"], "0" * 64)
        with self.assertRaisesRegex(m2_decoder.DecoderError, "result-shape"):
            m2_decoder.render_decoder_result(
                m2_decoder.OBS_UNITS,
                replace(result, m2_required_stream=None, m2_all_stream=b"complete"),
                schema_version=1,
            )

    def test_position_export_has_no_status_prefix_and_uses_nominal_target_plus_one(self) -> None:
        replay = chess.replay_from_start((chess.decode_move(bytes.fromhex("31c0")),))
        raw = chess.encode_position(replay.position)
        self.assertEqual(len(raw), 67)
        self.assertEqual(raw[:8], bytes((4, 2, 3, 5, 6, 3, 2, 4)))
        self.assertEqual((raw[12], raw[28]), (0, 1))
        self.assertEqual(raw[64:], bytes((1, 15, 21)))
        self.assertEqual(chess.encode_position(chess.decode_position(raw)), raw)
        self.assertEqual(chess.encode_position(chess.replay_from_start(()).position)[66], 0)


if __name__ == "__main__":
    unittest.main()
