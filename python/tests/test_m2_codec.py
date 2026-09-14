"""Independent pre-result tests for the Python M2 candidate codec lane."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from hashlib import sha256
import json
from pathlib import Path
import unittest

from golden_board import bootstrap, m2_codec


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> bytes:
    return (ROOT / path).read_bytes()


def _flip_bit(data: bytes, index: int) -> bytes:
    changed = bytearray(data)
    changed[index // 8] ^= 1 << (7 - index % 8)
    return bytes(changed)


def _common(version: int, payload: bytes = bytes(range(157))) -> bytes:
    return bootstrap.encode_common_block(
        bootstrap.CommonBlock(version, 9, 0, 3, 0, 0, 1, len(payload), payload)
    )


class M2CandidateCodec(unittest.TestCase):
    def test_exact_six_profile_projection_and_owner_admission(self) -> None:
        profiles = m2_codec.load_candidate_profiles(
            _read("spec/profile-policy-v0.toml"),
            _read("spec/profile-limits-v0.toml"),
        )
        self.assertEqual(profiles, m2_codec.candidate_profiles())
        self.assertEqual(
            tuple(
                (
                    item.profile_version,
                    item.transport_id,
                    item.section_check_id,
                    item.required_copy_count,
                    item.protected_unit_bytes,
                    item.protected_units,
                )
                for item in profiles
            ),
            (
                (1, m2_codec.EH_TRANSPORT, m2_codec.CRC32C, 2, 216, 2427),
                (2, m2_codec.EH_TRANSPORT, m2_codec.CRC64_ECMA, 2, 216, 2427),
                (3, m2_codec.EH_TRANSPORT, m2_codec.CRC32C, 3, 216, 2427),
                (4, m2_codec.EH_TRANSPORT, m2_codec.CRC64_ECMA, 3, 216, 2427),
                (5, m2_codec.RS_TRANSPORT, m2_codec.CRC32C, 2, 255, 2056),
                (6, m2_codec.RS_TRANSPORT, m2_codec.CRC64_ECMA, 2, 255, 2056),
            ),
        )
        with self.assertRaises(FrozenInstanceError):
            profiles[0].profile_id = "changed"  # type: ignore[misc]
        changed = _read("spec/profile-limits-v0.toml").replace(
            b"protected_units = 2427", b"protected_units = 2426"
        )
        with self.assertRaises(m2_codec.CodecError) as caught:
            m2_codec.load_candidate_profiles(
                _read("spec/profile-policy-v0.toml"), changed
            )
        self.assertEqual(caught.exception.reason, "profile[0]")

    def test_section_check_kats_and_closed_ids(self) -> None:
        self.assertEqual(
            m2_codec.check_bytes(m2_codec.CRC32C, b"123456789").hex(),
            "e3069283",
        )
        self.assertEqual(
            m2_codec.check_bytes(m2_codec.CRC64_ECMA, b"123456789").hex(),
            "6c40df5f0b497347",
        )
        with self.assertRaises(m2_codec.CodecError):
            m2_codec.check_bytes("crc32-v0", b"")

    def test_eh72_literal_encoding_kats(self) -> None:
        vectors = (
            ("0000000000000000", "000000000000000000"),
            ("8000000000000000", "e00000000000000001"),
            ("0123456789abcdef", "11121a2a9e26af36de"),
            ("ffffffffffffffff", "ffffffffffffffffff"),
        )
        for plain, encoded in vectors:
            with self.subTest(plain=plain):
                self.assertEqual(m2_codec.eh72_encode(bytes.fromhex(plain)).hex(), encoded)
                result = m2_codec.eh72_decode(bytes.fromhex(encoded))
                self.assertEqual(result.state, "verified")
                self.assertEqual(result.decoded, bytes.fromhex(plain))
                self.assertEqual(result.constructions, 73)

    def test_eh72_bounded_mixed_recovery_and_atomic_failure(self) -> None:
        plain = bytes.fromhex("0123456789abcdef")
        encoded = m2_codec.eh72_encode(plain)
        cases = (
            (_flip_bit(encoded, 7), (), 73),
            (_flip_bit(_flip_bit(encoded, 7), 19), (20,), 144),
            (_flip_bit(_flip_bit(encoded, 3), 70), (4, 71), 4),
            (_flip_bit(_flip_bit(_flip_bit(encoded, 3), 33), 70), (4, 34, 71), 8),
        )
        for observed, erasures, constructions in cases:
            with self.subTest(erasures=erasures):
                result = m2_codec.eh72_decode(observed, erasures)
                self.assertEqual(result.state, "recovered")
                self.assertEqual(result.decoded, plain)
                self.assertEqual(result.constructions, constructions)
        failed = m2_codec.eh72_decode(
            _flip_bit(_flip_bit(encoded, 7), 19)
        )
        self.assertEqual(failed, m2_codec.Recovery("corrupt", None, 73))
        for erasures in ((1, 1), (0,), (73,), (1, 2, 3, 4)):
            with self.assertRaises(m2_codec.CodecError):
                m2_codec.eh72_decode(encoded, erasures)

    def test_eh72_every_changed_and_erased_position(self) -> None:
        plain = bytes.fromhex("0123456789abcdef")
        encoded = m2_codec.eh72_encode(plain)
        for position in range(72):
            observed = _flip_bit(encoded, position)
            with self.subTest(kind="changed", position=position):
                result = m2_codec.eh72_decode(observed)
                self.assertEqual((result.state, result.decoded), ("recovered", plain))
            with self.subTest(kind="erased", position=position):
                result = m2_codec.eh72_decode(observed, (position + 1,))
                self.assertEqual((result.state, result.decoded), ("recovered", plain))

    def test_eh72_recipe_package_executes_only_generic_frozen_operations(self) -> None:
        vectors = (
            bytes(8),
            bytes.fromhex("8000000000000000"),
            bytes.fromhex("0123456789abcdef"),
            bytes([0xFF]) * 8,
        )
        for version in range(1, 5):
            raw = m2_codec.build_eh72_encoder_recipe(version)
            package = bootstrap.decode_recipe_package(raw, version)
            self.assertEqual(len(package.recipes), 1)
            self.assertEqual(package.recipes[0].recipe_id, 108)
            self.assertEqual(package.total_node_count, 184)
            self.assertEqual(package.total_edge_count, 265)
            self.assertEqual(package.table_payload_bytes, 2_569)
            self.assertLessEqual(len(raw), 8_700)
            self.assertLess(package.peak_live_scratch_bytes, 1024)
            self.assertEqual(
                {node.opcode for node in package.recipes[0].nodes},
                {1, 2, 5, 6, 13, 14, 16, 19, 20, 21, 24},
            )
            for data in vectors:
                self.assertEqual(
                    m2_codec.execute_eh72_encoder_recipe(version, data),
                    m2_codec.eh72_encode(data),
                )
        with self.assertRaises(m2_codec.CodecError):
            m2_codec.build_eh72_encoder_recipe(5)
        raw = bytearray(m2_codec.build_eh72_encoder_recipe(1))
        raw[-1] ^= 1
        with self.assertRaises(bootstrap.BootstrapReject):
            bootstrap.decode_recipe_package(bytes(raw), 1)

    def test_eh72_unit_pad_common_check_and_no_vote_copy_aggregation(self) -> None:
        profiles = m2_codec.candidate_profiles()
        profile = profiles[0]
        common = _common(profile.profile_version)
        encoded = m2_codec.eh72_encode_unit(common)
        self.assertEqual(len(encoded), 216)
        damaged = _flip_bit(encoded, 5)
        result = m2_codec.recover_profile_copies(
            profile,
            (
                m2_codec.CopyObservation(damaged),
                None,
            ),
        )
        self.assertEqual(result.state, "recovered")
        self.assertEqual(result.decoded, common)

        corrupt = encoded
        for position in (0, 9, 18, 27):
            corrupt = _flip_bit(corrupt, position)
        expected_verified = m2_codec.Recovery("verified", common, 1_825)
        for observations in (
            (
                m2_codec.CopyObservation(corrupt),
                m2_codec.CopyObservation(encoded),
            ),
            (
                m2_codec.CopyObservation(encoded),
                m2_codec.CopyObservation(corrupt),
            ),
        ):
            with self.subTest(order=tuple(item.encoded == encoded for item in observations)):
                self.assertEqual(
                    m2_codec.recover_profile_copies(profile, observations),
                    expected_verified,
                )

        different = _common(profile.profile_version, b"different")
        ambiguous = m2_codec.recover_profile_copies(
            profile,
            (
                m2_codec.CopyObservation(encoded),
                m2_codec.CopyObservation(m2_codec.eh72_encode_unit(different)),
            ),
        )
        self.assertEqual(ambiguous.state, "ambiguous")
        self.assertIsNone(ambiguous.decoded)
        missing = m2_codec.recover_profile_copies(profile, (None, None))
        self.assertEqual(missing, m2_codec.Recovery("missing", None, 0))
        noncanonical_pad = b"".join(
            m2_codec.eh72_encode((common + b"\x01")[offset : offset + 8])
            for offset in range(0, 192, 8)
        )
        rejected_pad = m2_codec.recover_profile_copies(
            profile, (m2_codec.CopyObservation(noncanonical_pad), None)
        )
        self.assertEqual(rejected_pad.state, "corrupt")
        unchecked = bytearray(common)
        unchecked[40] ^= 1
        rejected_local = m2_codec.recover_profile_copies(
            profile,
            (m2_codec.CopyObservation(m2_codec.eh72_encode_unit(bytes(unchecked))), None),
        )
        self.assertEqual(rejected_local.state, "corrupt")
        with self.assertRaises(m2_codec.CodecError):
            m2_codec.recover_profile_copies(profile, (None,))

    def test_rs_generator_systematic_encoder_and_syndrome_kats(self) -> None:
        generator = (
            "01c10aff3a80b7738c99935bc5dbdddc8e1c7815a49306cc28e6b60e79308f"
            "4de451552ba210c3a323959a2384646433b00ba186d084f4b0c0dde8ab7d9be4f2f5"
        )
        parity_one = generator[2:]
        parity_range = (
            "8c1be694d057757c84ad114737f11751d3d433c6e33e536ff7bbc6d136ae4bd0"
            "15626fbc94c52cc5abebe53fdcf0a24e22fa2387d87449c7bed4ceeb9c94c6f9"
        )
        self.assertEqual(m2_codec.rs_generator_coefficients().hex(), generator)
        zero = m2_codec.rs255_191_encode(bytes(191))
        self.assertEqual(zero, bytes(255))
        one = m2_codec.rs255_191_encode(bytes(190) + b"\x01")
        self.assertEqual(one[:191], bytes(190) + b"\x01")
        self.assertEqual(one[191:].hex(), parity_one)
        sequence = m2_codec.rs255_191_encode(bytes(range(191)))
        self.assertEqual(sequence[:191], bytes(range(191)))
        self.assertEqual(sequence[191:].hex(), parity_range)
        for codeword in (zero, one, sequence):
            self.assertEqual(m2_codec.rs255_191_syndromes(codeword), (0,) * 64)
            self.assertTrue(m2_codec.rs255_191_is_codeword(codeword))
        self.assertFalse(m2_codec.rs255_191_is_codeword(_flip_bit(sequence, 5)))

    def test_rs_encoder_recipe_is_bounded_generic_and_matches_direct_lane(self) -> None:
        vectors = (bytes(191), bytes(190) + b"\x01", bytes(range(191)))
        for version in (5, 6):
            raw = m2_codec.build_rs255_191_encoder_recipe(version)
            package = bootstrap.decode_recipe_package(raw, version)
            self.assertLessEqual(len(raw), 3_400)
            self.assertEqual(package.total_node_count, 62)
            self.assertEqual(package.total_edge_count, 81)
            self.assertEqual(package.maximum_primitive_steps, 369_292)
            self.assertLess(package.peak_live_scratch_bytes, 1_024)
            self.assertEqual(package.recipes[-1].recipe_id, 108)
            self.assertEqual(
                tuple(
                    (item.value_type, item.width)
                    for item in package.recipes[-1].inputs
                ),
                ((bootstrap.BYTES, 191),),
            )
            self.assertEqual(
                {node.opcode for recipe in package.recipes for node in recipe.nodes},
                {1, 2, 3, 4, 5, 6, 13, 17, 19, 20, 21, 22, 23, 24, 25},
            )
            for data in vectors:
                self.assertEqual(
                    m2_codec.execute_rs255_191_encoder_recipe(version, data),
                    m2_codec.rs255_191_encode(data),
                )
        with self.assertRaises(m2_codec.CodecError):
            m2_codec.build_rs255_191_encoder_recipe(4)

    def test_rs_copy_recovery_uses_checked_complete_witnesses(self) -> None:
        profile = m2_codec.candidate_profiles()[4]
        common = _common(profile.profile_version)
        encoded = m2_codec.rs255_191_encode(common)
        clean = m2_codec.recover_profile_copies(
            profile,
            (m2_codec.CopyObservation(encoded), None),
        )
        self.assertEqual(clean.state, "verified")
        self.assertEqual(clean.decoded, common)
        damaged = m2_codec.recover_profile_copies(
            profile,
            (m2_codec.CopyObservation(_flip_bit(encoded, 5)), None),
        )
        self.assertEqual(damaged.state, "recovered")
        self.assertEqual(damaged.decoded, common)
        erased = m2_codec.recover_profile_copies(
            profile,
            (m2_codec.CopyObservation(encoded, (0,)), None),
        )
        self.assertEqual(erased.state, "recovered")
        self.assertEqual(erased.decoded, common)

    def test_rs_frozen_field_encode_decode_and_boundary_corpus(self) -> None:
        raw = _read("conformance/rs255-191-v0.json")
        self.assertEqual(
            sha256(raw).hexdigest(),
            "d4dcc0cc441f42c66dc19d6db636733fc577751baf073dc7f951cd3c3dd23f72",
        )
        fixture = json.loads(raw)
        self.assertEqual(fixture["schema"], "golden-board.rs255-191-v0-fixtures/v0")
        self.assertEqual(
            set(fixture["mutant_ids"]),
            {
                "field-modulus-0x11b",
                "generator-roots-1-through-64",
                "coefficient-order-ascending-on-wire",
                "parity-before-data",
                "symbol-bits-lsb-first",
                "position-power-alpha-to-p",
                "erasure-transform-not-multiplied",
                "transformed-syndrome-prefix-not-dropped",
                "chien-alpha-to-p",
                "forney-location-factor-omitted",
                "ordinary-derivative",
                "erased-observation-byte-not-zero-filled",
                "correction-applied-before-all-magnitudes",
                "root-count-degree-not-checked",
                "post-syndrome-not-checked",
            },
        )
        for row in fixture["field_multiplication_kats"]:
            self.assertEqual(
                m2_codec.gf256_multiply(row["a"], row["b"]), row["product"]
            )
        for row in fixture["field_inverse_kats"]:
            self.assertEqual(m2_codec.gf256_inverse(row["a"]), row["inverse"])
        for row in fixture["encode_kats"]:
            data = bytes.fromhex(row["data_hex"])
            expected = bytes.fromhex(row["codeword_hex"])
            self.assertEqual(m2_codec.rs255_191_encode(data), expected, row["id"])
            self.assertEqual(sha256(expected).hexdigest(), row["codeword_sha256"])
        expected_data = bytes(range(191))
        clean = m2_codec.rs255_191_decode(
            m2_codec.rs255_191_encode(expected_data)
        )
        self.assertEqual(
            (
                clean.field_multiplications,
                clean.field_inversions,
                clean.primitive_steps,
            ),
            (16_320, 0, 130_560),
        )
        exact_work = {
            "single-data-first": (33_522, 3, 268_179),
            "single-data-last": (33_522, 3, 268_179),
            "single-parity-first": (33_522, 3, 268_179),
            "single-parity-last": (33_522, 3, 268_179),
            "e0-s64": (66_880, 64, 535_104),
            "e1-s62": (66_258, 65, 530_129),
            "e16-s32": (57_513, 80, 460_184),
            "e31-s2": (49_870, 94, 399_054),
            "e32-s0": (49_425, 96, 395_496),
            "e1-s63": (22_449, 1, 179_593),
            "e16-s33": (20_034, 31, 160_303),
            "e32-s1": (19_442, 63, 155_599),
            "e33-s0": (27_905, 64, 223_304),
            "e0-s65": (0, 0, 0),
        }
        for row in fixture["decode_kats"]:
            observed = bytes.fromhex(row["observation_hex"])
            self.assertEqual(sha256(observed).hexdigest(), row["observation_sha256"])
            result = m2_codec.rs255_191_decode(
                observed, row["erasure_positions"]
            )
            self.assertEqual(result.status, row["expected_status"], row["id"])
            self.assertLessEqual(result.field_multiplications, 80_000)
            self.assertLessEqual(result.field_inversions, 128)
            self.assertLessEqual(result.primitive_steps, 1_000_000)
            self.assertEqual(
                (
                    result.field_multiplications,
                    result.field_inversions,
                    result.primitive_steps,
                ),
                exact_work[row["id"]],
                row["id"],
            )
            self.assertEqual(
                result.primitive_steps,
                8 * result.field_multiplications + result.field_inversions,
                row["id"],
            )
            if row["expected_status"] == 0:
                self.assertEqual(result.decoded, expected_data, row["id"])
            else:
                self.assertIsNone(result.decoded, row["id"])
            if row["expected_correction_positions"]:
                self.assertEqual(
                    result.correction_positions,
                    tuple(row["expected_correction_positions"]),
                )
                self.assertEqual(
                    result.correction_magnitudes,
                    tuple(row["expected_correction_magnitudes"]),
                )
        intermediate = fixture["intermediate_kat"]
        result = m2_codec.rs255_191_decode(
            bytes.fromhex(intermediate["observation_hex"]),
            intermediate["erasure_positions"],
        )
        self.assertEqual(result.status, intermediate["expected_status"])
        self.assertEqual(
            result.correction_positions,
            tuple(intermediate["correction_positions"]),
        )
        self.assertEqual(
            result.correction_magnitudes,
            tuple(intermediate["correction_magnitudes"]),
        )

    def test_rs_every_symbol_position_and_stable_predecode_rejections(self) -> None:
        expected = m2_codec.rs255_191_encode(bytes(range(191)))
        for position in range(255):
            observed = bytearray(expected)
            observed[position] ^= 0x53
            result = m2_codec.rs255_191_decode(bytes(observed))
            self.assertEqual(result.status, 0, position)
            self.assertEqual(result.decoded, bytes(range(191)), position)
            self.assertEqual(result.correction_positions, (position,), position)
            self.assertEqual(result.correction_magnitudes, (0x53,), position)
        malformed = (
            m2_codec.rs255_191_decode(bytes(254)),
            m2_codec.rs255_191_decode(expected, [1, 1]),
            m2_codec.rs255_191_decode(expected, [2, 1]),
            m2_codec.rs255_191_decode(expected, [-1]),
            m2_codec.rs255_191_decode(expected, [255]),
            m2_codec.rs255_191_decode(expected, iter((1,))),
        )
        self.assertTrue(all(item.status == 3 and item.decoded is None for item in malformed))
        over = m2_codec.rs255_191_decode(expected, tuple(range(65)))
        self.assertEqual((over.status, over.decoded, over.field_multiplications), (4, None, 0))

    def test_rs_local_check_is_after_algebra_and_atomic(self) -> None:
        common = bytearray(_common(5))
        common[40] ^= 1
        invalid = m2_codec.rs255_191_encode(bytes(common))
        clean = m2_codec.rs255_191_decode(invalid, expected_profile_version=5)
        self.assertEqual(clean.status, 6)
        self.assertIsNone(clean.decoded)
        damaged = bytearray(invalid)
        damaged[200] ^= 0x53
        recovered = m2_codec.rs255_191_decode(
            bytes(damaged), expected_profile_version=5
        )
        self.assertEqual(recovered.status, 6)
        self.assertIsNone(recovered.decoded)

    def test_v7_registry_repetition_boundaries_and_group_aggregation(self) -> None:
        profile = m2_codec.r3_candidate_profile()
        self.assertEqual(
            tuple(item.profile_version for item in m2_codec.r3_registry_profiles()),
            (7, 2, 3, 4, 5, 6),
        )
        self.assertEqual(profile.inventory_version, 1)
        self.assertEqual(profile.physical_replica_counts, (1, 2, 5))
        self.assertEqual(profile.required_copy_count, 1)

        self.assertEqual(
            m2_codec.repetition_symbol(2, (1, 0, 0, 0, 0), (1, 0, 0, 0, 0)),
            (True, 1),
        )
        self.assertEqual(
            m2_codec.repetition_symbol(2, (1, 1, 0, 0, 0), (0, 1, 0, 0, 0)),
            (False, 0),
        )
        self.assertEqual(
            m2_codec.repetition_symbol(5, (1, 1, 1, 1, 1), (1, 1, 0, 0, 0)),
            (True, 0),
        )
        self.assertEqual(
            m2_codec.repetition_symbol(5, (1, 1, 1, 1, 1), (1, 1, 1, 0, 0)),
            (True, 1),
        )
        self.assertEqual(
            m2_codec.repetition_symbol(5, (1, 0, 0, 0, 0), (1, 0, 0, 0, 0)),
            (True, 1),
        )
        self.assertEqual(
            m2_codec.repetition_symbol(5, (0, 0, 0, 0, 0), (0, 0, 0, 0, 0)),
            (False, 0),
        )
        self.assertEqual(m2_codec.repetition_symbol_counts(2, 0, 1), (True, 1))
        self.assertEqual(m2_codec.repetition_symbol_counts(2, 1, 1), (False, 0))
        self.assertEqual(m2_codec.repetition_symbol_counts(5, 3, 2), (True, 0))
        self.assertEqual(m2_codec.repetition_symbol_counts(5, 2, 3), (True, 1))
        self.assertEqual(m2_codec.repetition_symbol_counts(5, 0, 0), (False, 0))
        for arguments in ((1, 0, 0), (2, 2, 1), (5, -1, 0), (5, 0, 6)):
            with self.assertRaisesRegex(m2_codec.CodecError, "repetition-counts"):
                m2_codec.repetition_symbol_counts(*arguments)
        for arguments in (
            (1, (1, 0, 0, 0, 0), (0, 0, 0, 0, 0)),
            (2, (1, 0), (0, 0)),
            (2, (1, 0, 1, 0, 0), (0, 0, 0, 0, 0)),
            (2, (1, 0, 0, 0, 0), (0, 1, 0, 0, 0)),
        ):
            with self.subTest(arguments=arguments):
                with self.assertRaisesRegex(m2_codec.CodecError, "repetition-shape"):
                    m2_codec.repetition_symbol(*arguments)

        for factor in (1, 2, 5):
            for replica_index in range(factor):
                self.assertEqual(
                    m2_codec.physical_group_index(
                        100 + replica_index, 100, factor
                    ),
                    replica_index,
                )
        for arguments in ((99, 100, 5), (105, 100, 5), (100, 100, 3)):
            with self.assertRaisesRegex(m2_codec.CodecError, "physical-group-index"):
                m2_codec.physical_group_index(*arguments)

        common = _common(7)
        encoded = m2_codec.eh72_encode_unit(common)
        clean = m2_codec.CopyObservation(encoded)
        factor_one = m2_codec.aggregate_replica_group(profile, (clean,))
        self.assertEqual(
            (factor_one.group_state, factor_one.lane_states, factor_one.repetition_state),
            (2, (2,), 0),
        )
        factor_two = m2_codec.aggregate_replica_group(profile, (None, clean))
        self.assertEqual(
            (factor_two.group_state, factor_two.lane_states, factor_two.repetition_state),
            (2, (0, 2), 3),
        )
        missing = m2_codec.aggregate_replica_group(profile, (None,) * 5)
        self.assertEqual(
            (missing.group_state, missing.distinct_candidate_count, missing.repetition_state),
            (0, 0, 0),
        )

        damaged_lanes = []
        for first in range(0, 10, 2):
            observed = _flip_bit(_flip_bit(encoded, first), first + 1)
            damaged_lanes.append(m2_codec.CopyObservation(observed))
        recovered = m2_codec.aggregate_replica_group(profile, tuple(damaged_lanes))
        self.assertEqual(recovered.lane_states, (1, 1, 1, 1, 1))
        self.assertEqual(
            (
                recovered.group_state,
                recovered.distinct_candidate_count,
                recovered.chosen_block,
                recovered.repetition_state,
                recovered.repetition_block,
            ),
            (3, 1, common, 3, common),
        )

        alternate = _common(7, b"different")
        conflict = m2_codec.aggregate_replica_group(
            profile,
            (
                m2_codec.CopyObservation(m2_codec.eh72_encode_unit(alternate)),
                clean,
                clean,
                clean,
                clean,
            ),
        )
        self.assertEqual(
            (conflict.group_state, conflict.distinct_candidate_count), (4, 2)
        )
        self.assertEqual(conflict.chosen_block, bytes(191))
        self.assertEqual(conflict.lane_blocks[0], alternate)
        self.assertEqual(conflict.lane_blocks[1:], (common,) * 4)
        self.assertEqual(conflict.repetition_block, common)

        first_one = next(
            index
            for index, bit in enumerate(
                tuple(
                    (byte >> (7 - sub)) & 1
                    for byte in encoded
                    for sub in range(8)
                )
            )
            if bit
        )
        with self.assertRaisesRegex(m2_codec.CodecError, "replica-erased-value"):
            m2_codec.aggregate_replica_group(
                profile, (m2_codec.CopyObservation(encoded, (first_one,)),)
            )

    def test_length_and_type_boundaries_fail_closed(self) -> None:
        calls = (
            lambda: m2_codec.eh72_encode(bytes(7)),
            lambda: m2_codec.eh72_decode(bytes(8)),
            lambda: m2_codec.eh72_encode_unit(bytes(190)),
            lambda: m2_codec.rs255_191_encode(bytes(190)),
            lambda: m2_codec.rs255_191_syndromes(bytes(254)),
        )
        for call in calls:
            with self.assertRaises(m2_codec.CodecError):
                call()


if __name__ == "__main__":
    unittest.main()
