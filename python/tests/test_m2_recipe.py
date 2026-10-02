from __future__ import annotations

from hashlib import sha256
import unittest

from golden_board import bootstrap, m2_codec, m2_recipe


class CandidateRecipeLane(unittest.TestCase):
    @staticmethod
    def _evaluate_eh(
        package: bootstrap.RecipePackage,
        observed: bytes,
        erasures: tuple[int, ...] = (),
    ) -> bootstrap.RecipeResult:
        return bootstrap.evaluate_recipe(
            package,
            30,
            (
                observed,
                bytes((len(erasures),)),
                bytes(erasures) + bytes(3 - len(erasures)),
            ),
        )

    def test_independent_eh_decoder30_is_bounded_and_exact(self) -> None:
        raw = m2_recipe.build_eh72_decoder_recipe(1)
        self.assertEqual(raw, m2_recipe.build_eh72_decoder_recipe(1))
        package = bootstrap.decode_recipe_package(raw, 1)
        self.assertEqual(
            (
                len(raw),
                package.total_node_count,
                package.total_edge_count,
                package.table_payload_bytes,
                package.maximum_primitive_steps,
                package.peak_live_scratch_bytes,
            ),
            (19_862, 442, 682, 4_970, 19_012, 184),
        )

        source = bytes.fromhex("0123456789abcdef")
        encoded = m2_codec.eh72_encode(source)
        cases: list[tuple[bytes, tuple[int, ...]]] = [(encoded, ())]
        for position in range(72):
            changed = bytearray(encoded)
            changed[position // 8] ^= 1 << (7 - position % 8)
            cases.append((bytes(changed), ()))

            erased = bytearray(encoded)
            erased[position // 8] ^= 1 << (7 - position % 8)
            cases.append((bytes(erased), (position + 1,)))
        mixed = bytearray(encoded)
        mixed[5 // 8] ^= 1 << (7 - 5 % 8)
        mixed[71 // 8] ^= 1 << (7 - 71 % 8)
        cases.append((bytes(mixed), (6,)))
        cases.extend((encoded, positions) for positions in ((1, 2), (1, 2, 3)))

        for observed, erasures in cases:
            with self.subTest(erasures=erasures, observed=observed.hex()):
                result = self._evaluate_eh(package, observed, erasures)
                self.assertEqual(result.status, 0)
                self.assertEqual(result.outputs, (source,))
                self.assertEqual(
                    result.outputs[0],
                    m2_codec.eh72_decode(observed, erasures).decoded,
                )

    def test_independent_eh_decoder30_fails_closed(self) -> None:
        package = bootstrap.decode_recipe_package(
            m2_recipe.build_eh72_decoder_recipe(1), 1
        )
        encoded = m2_codec.eh72_encode(bytes(8))
        beyond = bytearray(encoded)
        beyond[0] ^= 0x80
        beyond[1] ^= 0x40
        self.assertEqual(self._evaluate_eh(package, bytes(beyond)).status, 5)

        malformed = (
            (encoded, b"\x04", bytes(3), 4),
            (encoded, b"\x02", b"\x01\x01\x00", 3),
            (encoded, b"\x01", b"\x01\x01\x00", 3),
        )
        for observed, count, positions, status in malformed:
            with self.subTest(count=count, positions=positions):
                result = bootstrap.evaluate_recipe(
                    package, 30, (observed, count, positions)
                )
                self.assertEqual(result.status, status)
                self.assertEqual(result.outputs, ())

    def test_python_rs_diagnostic_package_metrics_are_exact(self) -> None:
        for version in (5, 6):
            raw = m2_recipe.build_rs_decoder_recipe(version)
            package = bootstrap.decode_recipe_package(raw, version)
            self.assertEqual(
                (
                    len(raw),
                    package.total_node_count,
                    package.total_edge_count,
                    package.table_payload_bytes,
                    package.maximum_primitive_steps,
                    package.peak_live_scratch_bytes,
                ),
                (38_165, 972, 1_378, 4_389, 1_832_609, 4_762),
            )
            self.assertGreater(package.maximum_primitive_steps, 1_000_000)
            self.assertGreater(len(raw), 29_257)

    def test_compact_r3_recipient_package_is_independently_exact(self) -> None:
        raw = m2_recipe.build_r3_recipe_package()
        metrics = m2_recipe.r3_recipe_package_metrics()
        self.assertEqual(
            metrics,
            m2_recipe.R3RecipePackageMetrics(
                25_930,
                "4bd8e0d485ae6e6a65f4edc4ef2aaac9585a2bcd8c4623e44d69f1dad3b0ec8e",
                699,
                1_087,
                1_470,
                80_435,
                6_163,
                872,
                24,
            ),
        )
        package = bootstrap.decode_recipe_package(raw, 7)
        self.assertEqual(
            tuple(recipe.recipe_id for recipe in package.recipes),
            (1, 2, 3, 4, 30, 90, 92, 99, 100) + tuple(range(101, 114)),
        )
        self.assertEqual(
            tuple(table.table_id for table in package.tables),
            (3, 4, 5, 10, 11, 12, 13, 14, 15, 17, 18, 19, 20),
        )
        table17 = next(table for table in package.tables if table.table_id == 17)
        self.assertEqual(table17.payload, m2_recipe.r3_slot_multiplier_table())
        self.assertEqual(
            sha256(table17.payload).hexdigest(),
            "835717bf400c597a3a9e1b59747f23d93047b6cfab462756fa07d96c5f3eba3f",
        )

    def test_legacy_eh_recipient_packages_are_independently_exact(self) -> None:
        expected = {
            1: (
                24_786,
                "f030732cd966fd9570149f6fd2d1befb5eed66319eb248b609693e868f977941",
            ),
            2: (
                26_738,
                "cce1758613d7f10278533409e07103ae15162972fcf30030e17c233e39664011",
            ),
            3: (
                24_786,
                "8c91ba74f9bbed97aed89191e8d8d30a9a0c4d32bd5ac98b63a4c19ed71fb0e7",
            ),
            4: (
                26_738,
                "de237fcd9d53581710404bd8b00152cb68f50adef48e715fdd4572e786bae4b8",
            ),
        }
        recipe_ids = (1, 2, 3, 4, 30, 90, 92, 99, 100) + tuple(range(101, 113))
        table_ids = (3, 4, 5, 10, 11, 12, 13, 14, 15, 18, 19, 20)
        for profile_version, (expected_bytes, expected_hash) in expected.items():
            with self.subTest(profile_version=profile_version):
                raw = m2_recipe.build_eh_recipient_package(profile_version)
                self.assertEqual(
                    raw,
                    m2_recipe.build_eh_recipient_package(profile_version),
                )
                self.assertEqual(len(raw), expected_bytes)
                self.assertEqual(sha256(raw).hexdigest(), expected_hash)
                package = bootstrap.decode_recipe_package(raw, profile_version)
                self.assertEqual(
                    tuple(recipe.recipe_id for recipe in package.recipes),
                    recipe_ids,
                )
                self.assertEqual(
                    tuple(table.table_id for table in package.tables),
                    table_ids,
                )
                self.assertEqual(package.maximum_primitive_steps, 80_435)
                self.assertEqual(package.table_payload_bytes, 1_214)

                common_crc = bootstrap.evaluate_recipe(package, 107, (b"123456789",))
                section_crc = bootstrap.evaluate_recipe(package, 111, (b"123456789",))
                self.assertEqual(
                    (common_crc.status, common_crc.outputs),
                    (0, (bytes.fromhex("e3069283"),)),
                )
                expected_section_crc = (
                    "e3069283" if profile_version % 2 else "6c40df5f0b497347"
                )
                self.assertEqual(
                    (section_crc.status, section_crc.outputs),
                    (0, (bytes.fromhex(expected_section_crc),)),
                )

        for profile_version in (0, 5, 6, 7):
            with self.subTest(rejected_profile_version=profile_version):
                with self.assertRaisesRegex(ValueError, "profile_version"):
                    m2_recipe.build_eh_recipient_package(profile_version)

    def test_compact_r3_repetition_count_abi_fails_closed(self) -> None:
        package = bootstrap.decode_recipe_package(
            m2_recipe.build_r3_recipe_package(), 7
        )
        for factor, zeros, ones, known, bit in (
            (2, 0, 0, 0, 0),
            (2, 1, 0, 1, 0),
            (2, 0, 1, 1, 1),
            (2, 1, 1, 0, 0),
            (5, 3, 2, 1, 0),
            (5, 2, 3, 1, 1),
            (5, 2, 2, 0, 0),
            (5, 0, 0, 0, 0),
        ):
            with self.subTest(factor=factor, zeros=zeros, ones=ones):
                result = bootstrap.evaluate_recipe(
                    package,
                    113,
                    (bytes((factor,)), bytes((zeros,)), bytes((ones,))),
                )
                self.assertEqual(
                    (result.status, result.outputs),
                    (0, (bytes((known,)), bytes((bit,)))),
                )
        for factor, zeros, ones in ((1, 1, 0), (2, 2, 1), (5, 255, 255)):
            with self.subTest(factor=factor, zeros=zeros, ones=ones):
                result = bootstrap.evaluate_recipe(
                    package,
                    113,
                    (bytes((factor,)), bytes((zeros,)), bytes((ones,))),
                )
                self.assertEqual((result.status, result.outputs), (3, ()))

    def test_rs_decoder30_corrects_before_local_check(self) -> None:
        contract = m2_recipe.rs_decoder_recipe_contract(5)
        package = bootstrap.decode_recipe_package(contract.package, 5)
        result = bootstrap.evaluate_recipe(package, 30, contract.held_input)
        self.assertEqual(result.status, 0)
        self.assertEqual(result.outputs, (contract.held_output[2:],))


if __name__ == "__main__":
    unittest.main()
