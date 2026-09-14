from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from golden_board import (
    bootstrap,
    m2_carrier,
    m2_codec,
    m2_damage,
    m2_decoder,
    m2_route_data,
)


ROOT = Path(__file__).resolve().parents[2]
P1 = "eh72-r2-crc32c-v0"
P3 = "eh72-r3-crc32c-v0"
RETAINED_LEGACY_CANDIDATES = all(
    (ROOT / "artifacts/candidates" / profile_id / "carrier.obs-bits").is_file()
    for profile_id in (P1, P3)
)


def _read(relative: str) -> bytes:
    return (ROOT / relative).read_bytes()


def _emit(profile_version: int) -> bytes:
    environment = dict(os.environ)
    if "RUSTC" not in environment:
        environment["RUSTC"] = subprocess.run(
            ["rustup", "which", "--toolchain", "1.97.1", "rustc"],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        ).stdout.strip()
    with tempfile.TemporaryDirectory(prefix="golden-board-decoder-") as directory:
        output = Path(directory) / "package.bin"
        subprocess.run(
            [
                "rustup",
                "run",
                "1.97.1",
                "cargo",
                "run",
                "-q",
                "--locked",
                "--offline",
                "-p",
                "gb-bootstrap",
                "--example",
                "dump_eh_package",
                "--",
                str(profile_version),
                str(output),
            ],
            cwd=ROOT,
            env=environment,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return output.read_bytes()


def _rust_decoder_command() -> tuple[str, ...]:
    environment = dict(os.environ)
    if "RUSTC" not in environment:
        environment["RUSTC"] = subprocess.run(
            ["rustup", "which", "--toolchain", "1.97.1", "rustc"],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        ).stdout.strip()
    subprocess.run(
        [
            "rustup",
            "run",
            "1.97.1",
            "cargo",
            "build",
            "-q",
            "--release",
            "--locked",
            "--offline",
            "-p",
            "gb-bootstrap",
            "--bin",
            "gb-damage-decoder",
        ],
        cwd=ROOT,
        env=environment,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return (str(ROOT / "target/release/gb-damage-decoder"),)


def _bits(raw: bytes) -> bytearray:
    count = int.from_bytes(raw[:4], "big")
    return bytearray(
        (raw[4 + index // 8] >> (7 - index % 8)) & 1
        for index in range(count)
    )


def _obs_bits(values: bytearray) -> bytes:
    packed = bytearray((len(values) + 7) // 8)
    for index, value in enumerate(values):
        packed[index // 8] |= value << (7 - index % 8)
    return len(values).to_bytes(4, "big") + bytes(packed)


def _flip_bit(raw: bytes, position: int) -> bytes:
    changed = bytearray(raw)
    changed[position // 8] ^= 1 << (7 - position % 8)
    return bytes(changed)


def _v7_decoder() -> m2_decoder.ObservationDecoder:
    decoder = object.__new__(m2_decoder.ObservationDecoder)
    decoder._unit_cache = {}
    decoder._transport_cache = {}
    return decoder


def _v7_observation(unit_id: int, common: bytes) -> m2_decoder._ObservedUnit:
    return m2_decoder._ObservedUnit(
        unit_id, m2_codec.eh72_encode_unit(common), ()
    )


def _v7_inventory() -> bootstrap.Inventory:
    entries = [
        bootstrap.InventoryEntry(1, 1, 1, 128, 1, 1, (), 1_376, None, 5),
        bootstrap.InventoryEntry(2, 2, 0, 128, 1, 1, (16,), 38, None, 5),
        bootstrap.InventoryEntry(3, 2, 0, 128, 1, 1, (16,), 38, None, 5),
        bootstrap.InventoryEntry(16, 3, 0, 128, 1, 1, (), 2, None, 5),
    ]
    entries.extend(
        bootstrap.InventoryEntry(
            100 + ordinal,
            3,
            0,
            129,
            1,
            1,
            (),
            2,
            ordinal,
            1,
        )
        for ordinal in range(64)
    )
    return bootstrap.Inventory(tuple(entries), 1)


class M2R3DecoderPrimitives(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = m2_codec.r3_candidate_profile(
            protected_units=100,
            encoded_transport_bytes=100 * 216,
        )
        self.decoder = _v7_decoder()

    @staticmethod
    def _common_for_envelope(envelope: bytes) -> bytes:
        return bootstrap.encode_common_block(
            bootstrap.CommonBlock(
                7,
                9,
                0,
                3,
                0,
                0,
                1,
                len(envelope),
                envelope,
            )
        )

    def test_v7_no_inventory_initial_group_conflict_keeps_lane_diagnostics(self) -> None:
        first = bootstrap.fragment_section(
            bootstrap.encode_section_envelope(
                bootstrap.SectionEnvelope(1, 1, 1, 128, 1, (), b"first")
            ),
            7,
            0,
        )[0]
        alternate = bootstrap.fragment_section(
            bootstrap.encode_section_envelope(
                bootstrap.SectionEnvelope(1, 1, 1, 128, 1, (), b"other")
            ),
            7,
            0,
        )[0]
        observations = tuple(
            _v7_observation(unit_id, alternate if unit_id == 1 else first)
            for unit_id in range(1, 6)
        )
        result = self.decoder._without_inventory((self.profile,), observations)
        self.assertEqual(result.section_results, (m2_decoder.SectionResult(1, "corrupt", None),))
        self.assertEqual(result.resource.section_attempts, 0)
        self.assertEqual(
            [
                (row.input_id, row.replica_index, row.physical_replica_count, row.state)
                for row in result.fragment_diagnostics
            ],
            [(unit_id, unit_id - 1, 5, "verified") for unit_id in range(1, 6)],
        )
        self.assertEqual(result.fragment_diagnostics[0].common_block, alternate)
        self.assertTrue(
            all(row.common_block == first for row in result.fragment_diagnostics[1:])
        )
        rendered = json.loads(
            m2_decoder.render_decoder_result(
                m2_decoder.OBS_UNITS, result, schema_version=1
            )
        )
        self.assertEqual(
            rendered["schema"], "golden-board.m2-damage-decoder-result/v1"
        )

    def test_v7_complete_checked_section_conflict_is_artifact_ambiguous(self) -> None:
        profiles = (
            self.profile,
            m2_codec.r3_registry_profiles()[1],
        )

        def observation(
            input_id: int, profile_version: int, payload: bytes
        ) -> m2_decoder._ObservedUnit:
            envelope = bootstrap.encode_section_envelope(
                bootstrap.SectionEnvelope(9, 3, 0, 129, 1, (), payload)
            )
            common = bootstrap.fragment_section(
                envelope, profile_version, 0
            )[0]
            return _v7_observation(input_id, common)

        result = self.decoder._without_inventory(
            profiles,
            (
                observation(100, 7, b"first"),
                observation(101, 2, b"second"),
            ),
        )
        self.assertEqual(result.artifact_state, "ambiguous")
        self.assertEqual(
            result.section_results,
            (
                m2_decoder.SectionResult(1, "incomplete", None),
                m2_decoder.SectionResult(9, "ambiguous", None),
            ),
        )
        self.assertEqual(result.resource.section_attempts, 2)

    def test_mapping_hash_projection_is_exact_tagged_union(self) -> None:
        hierarchical = {
            "id": "affine-slot-then-interior-v1",
            "interior_side": 1_784,
            "population": 3_182_656,
            "unit_population": 1_841,
            "unit_multiplier": 2,
            "unit_inverse_multiplier": 921,
            "cell_multiplier": 3_567,
            "offset": 316_417,
            "cell_inverse_multiplier": 3_179_087,
        }
        legacy = {
            "id": "affine-interior-v1",
            "interior_side": 1_784,
            "population": 3_182_656,
            "multiplier": 3_567,
            "offset": 154_405,
            "inverse_multiplier": 3_179_087,
        }
        self.assertEqual(
            m2_decoder._mapping_sha256(1, hierarchical),
            "90d6fa3a3a6b28489c8c63e62df17caab7a46180614e387952a77071731da439",
        )
        self.assertEqual(
            m2_decoder._mapping_sha256(0, legacy),
            "7f2f3f2a9bd9238668b3fefc78f31ae2ac4a0fa58acaab2793b24ca4d3c2369c",
        )
        for route_version, changed in (
            (0, hierarchical),
            (1, legacy),
            (2, hierarchical),
            (1, {**hierarchical, "unknown": 0}),
            (1, {key: value for key, value in hierarchical.items() if key != "offset"}),
            (1, {**hierarchical, "id": "affine-interior-v1"}),
            (1, {**hierarchical, "unit_inverse_multiplier": 920}),
            (0, {**legacy, "inverse_multiplier": 3_179_086}),
        ):
            with self.subTest(route_version=route_version, changed=changed):
                with self.assertRaisesRegex(m2_decoder.DecoderError, "route-mapping"):
                    m2_decoder._mapping_sha256(route_version, changed)

    def test_v7_inventory_recovery_derives_group_contiguous_expected_ids(self) -> None:
        profile = m2_codec.r3_candidate_profile(
            protected_units=200,
            encoded_transport_bytes=200 * 216,
        )
        inventory = _v7_inventory()
        payload = bootstrap.encode_inventory(inventory)
        envelope = bootstrap.encode_section_envelope(
            bootstrap.SectionEnvelope(1, 1, 1, 128, 1, (), payload)
        )
        fragments = bootstrap.fragment_section(envelope, 7, 0)
        observations = []
        for fragment_index, common in enumerate(fragments):
            group_first = 5 * fragment_index + 1
            observations.extend(
                _v7_observation(group_first + replica_index, common)
                for replica_index in range(5)
            )
        self.assertEqual(
            self.decoder._recover_inventory(profile, tuple(observations)),
            (inventory, envelope),
        )
        expected = self.decoder._expected_units(profile, inventory)
        self.assertEqual(len(expected), 124)
        self.assertEqual(
            [
                (
                    row.unit_id,
                    row.section_id,
                    row.fragment_index,
                    row.replica_index,
                    row.physical_replica_count,
                    row.group_first_physical_unit_id,
                )
                for row in expected[:10]
            ],
            [
                (unit_id, 1, (unit_id - 1) // 5, (unit_id - 1) % 5, 5, group_first)
                for group_first in (1, 6)
                for unit_id in range(group_first, group_first + 5)
            ],
        )
        section_16 = [row for row in expected if row.section_id == 16]
        self.assertEqual(
            [
                (row.unit_id, row.replica_index, row.physical_replica_count)
                for row in section_16
            ],
            [(unit_id, replica, 5) for replica, unit_id in enumerate(range(56, 61))],
        )

    def test_v7_no_inventory_missing_initial_group_and_checked_later_section(self) -> None:
        missing = self.decoder._without_inventory((self.profile,), ())
        self.assertEqual(
            missing.section_results,
            (m2_decoder.SectionResult(1, "incomplete", None),),
        )
        self.assertEqual(
            [
                (row.input_id, row.replica_index, row.physical_replica_count, row.state)
                for row in missing.fragment_diagnostics
            ],
            [(unit_id, unit_id - 1, 5, "missing") for unit_id in range(1, 6)],
        )

        envelope = bootstrap.encode_section_envelope(
            bootstrap.SectionEnvelope(9, 3, 0, 129, 1, (), b"checked")
        )
        common = bootstrap.fragment_section(envelope, 7, 0)[0]
        discovered = self.decoder._without_inventory(
            (self.profile,), (_v7_observation(100, common),)
        )
        self.assertEqual(
            discovered.section_results,
            (
                m2_decoder.SectionResult(1, "incomplete", None),
                m2_decoder.SectionResult(9, "verified", envelope),
            ),
        )
        self.assertEqual(discovered.resource.section_attempts, 1)
        later = next(
            row for row in discovered.fragment_diagnostics if row.input_id == 100
        )
        self.assertEqual(
            (later.replica_index, later.physical_replica_count),
            (0xFFFF, 0xFFFF),
        )

    def test_v7_section_attempt_charge_excludes_wrong_width_but_counts_bad_check(self) -> None:
        clean = bootstrap.encode_section_envelope(
            bootstrap.SectionEnvelope(9, 3, 0, 129, 1, (), b"checked")
        )
        wrong_width = bytearray(clean)
        wrong_width[11] = 2
        wrong_stored = clean[:-4] + clean[-4:][::-1]
        cases = ((bytes(wrong_width), 0), (wrong_stored, 1))
        for ordinal, (envelope, attempts) in enumerate(cases, 100):
            with self.subTest(ordinal=ordinal):
                result = self.decoder._without_inventory(
                    (self.profile,),
                    (_v7_observation(ordinal, self._common_for_envelope(envelope)),),
                )
                self.assertEqual(result.resource.section_attempts, attempts)
                self.assertEqual(result.section_results[0].section_id, 1)
                self.assertFalse(
                    any(row.section_id == 9 for row in result.section_results)
                )

    def test_v1_result_projection_rejects_sentinel_and_order_drift(self) -> None:
        base = m2_decoder.DecodeResult("failure", None, (), (), False)
        invalid_rows = (
            (
                m2_decoder.FragmentDiagnostic(
                    2, self.profile.profile_id, 1, 0, 0, "missing", None, 1, 5
                ),
                m2_decoder.FragmentDiagnostic(
                    1, self.profile.profile_id, 1, 0, 0, "missing", None, 0, 5
                ),
            ),
            (
                m2_decoder.FragmentDiagnostic(
                    1,
                    self.profile.profile_id,
                    1,
                    0,
                    0,
                    "missing",
                    None,
                    0,
                    0xFFFF,
                ),
            ),
            (
                m2_decoder.FragmentDiagnostic(
                    6, self.profile.profile_id, 1, 0, 0, "missing", None, 0, 5
                ),
            ),
        )
        for rows in invalid_rows:
            with self.subTest(rows=rows), self.assertRaisesRegex(
                m2_decoder.DecoderError, "result-shape"
            ):
                m2_decoder.render_decoder_result(
                    m2_decoder.OBS_UNITS,
                    m2_decoder.DecodeResult(
                        base.artifact_state,
                        base.profile_id,
                        base.section_results,
                        base.route_profile_ids,
                        base.inventory_available,
                        rows,
                    ),
                    schema_version=1,
                )

        absent = m2_decoder.FragmentDiagnostic(
            1, "", 0, 0xFFFF, 0xFFFF, "corrupt", None
        )
        v7 = m2_decoder.FragmentDiagnostic(
            1,
            self.profile.profile_id,
            9,
            0,
            0,
            "missing",
            None,
        )
        for row in (
            replace(absent, section_id=9),
            replace(absent, semantic_copy_id=0),
            replace(absent, fragment_index=0),
            replace(v7, section_id=0),
            replace(v7, semantic_copy_id=0xFFFF),
            replace(v7, fragment_index=0xFFFF),
            replace(v7, semantic_copy_id=1),
        ):
            with self.subTest(row=row), self.assertRaisesRegex(
                m2_decoder.DecoderError, "result-shape"
            ):
                m2_decoder.render_decoder_result(
                    m2_decoder.OBS_UNITS,
                    replace(base, fragment_diagnostics=(row,)),
                    schema_version=1,
                )

    def test_v1_result_projection_closes_stream_route_and_resource_shapes(self) -> None:
        base = m2_decoder.DecodeResult("failure", None, (), (), False)
        profile_id = self.profile.profile_id
        accepted = m2_decoder.AcceptedHypothesis(
            0, 0, 0, profile_id, "0" * 64
        )
        valid_route = replace(
            base,
            route_profile_ids=(profile_id,),
            accepted_hypotheses=(accepted,),
        )
        m2_decoder.render_decoder_result(
            m2_decoder.OBS_BITS, valid_route, schema_version=1
        )
        degraded_with_complete_tier_streams = replace(
            base,
            artifact_state="degraded",
            profile_id=profile_id,
            inventory_available=True,
            section_results=(
                m2_decoder.SectionResult(1, "corrupt", None),
            ),
            m2_required_stream=b"required",
            m2_all_stream=b"all",
        )
        m2_decoder.render_decoder_result(
            m2_decoder.OBS_BITS,
            degraded_with_complete_tier_streams,
            schema_version=1,
        )
        invalid = (
            (m2_decoder.OBS_BITS, replace(base, artifact_state="exact")),
            (m2_decoder.OBS_BITS, replace(base, artifact_state="degraded")),
            (
                m2_decoder.OBS_BITS,
                replace(
                    base,
                    artifact_state="exact",
                    profile_id=profile_id,
                    inventory_available=True,
                ),
            ),
            (m2_decoder.OBS_UNITS, valid_route),
            (
                m2_decoder.OBS_BITS,
                replace(valid_route, route_profile_ids=()),
            ),
            (
                m2_decoder.OBS_BITS,
                replace(base, m2_all_stream=b"all"),
            ),
            (
                m2_decoder.OBS_BITS,
                replace(
                    base,
                    artifact_state="resource-limit",
                    section_results=(
                        m2_decoder.SectionResult(1, "unknown", None),
                    ),
                ),
            ),
        )
        for channel, result in invalid:
            with self.subTest(channel=channel, result=result), self.assertRaisesRegex(
                m2_decoder.DecoderError, "result-shape"
            ):
                m2_decoder.render_decoder_result(
                    channel, result, schema_version=1
                )

        resource = replace(base, artifact_state="resource-limit")
        rendered = json.loads(
            m2_decoder.render_decoder_result(
                m2_decoder.OBS_BITS, resource, schema_version=1
            )
        )
        self.assertEqual(
            rendered["fragment_diagnostics_sha256"],
            "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        )
        self.assertEqual(rendered["section_rows"], [])
        self.assertEqual(rendered["accepted_hypothesis_rows"], [])

    def test_v1_result_projection_enforces_one_mib_canonical_cap(self) -> None:
        rows = tuple(
            m2_decoder.SectionResult(section_id, "unknown", None)
            for section_id in range(1, 20_001)
        )
        with self.assertRaisesRegex(m2_decoder.DecoderError, "result-shape"):
            m2_decoder.render_decoder_result(
                m2_decoder.OBS_BITS,
                m2_decoder.DecodeResult("failure", None, rows, (), False),
                schema_version=1,
            )


class M2R3ProductionDecoder(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy_raw = _read("spec/profile-policy-v1.toml")
        cls.limits_raw = _read("spec/profile-limits-v1.toml")
        cls.damage_raw = _read("spec/damage-policy-v1.toml")

    def test_promoted_owner_admission_is_exact_and_registry_is_closed(self) -> None:
        decoder = m2_decoder.ObservationDecoder(
            self.policy_raw, self.limits_raw, self.damage_raw
        )
        self.assertEqual(decoder.result_schema_version, 1)
        self.assertEqual(
            [profile.profile_version for profile in decoder.profiles],
            [7, 2, 3, 4, 5, 6],
        )
        self.assertEqual(decoder.establishing_profile_versions, frozenset((7,)))
        self.assertEqual(decoder.maximum_units, 1_841)
        self.assertEqual(decoder.transport_resources[7], (80_435, 4_613))
        self.assertEqual(decoder.repetition_resource, (24, 10))
        for ordinal, raws in enumerate(
            (
                (self.policy_raw + b" ", self.limits_raw, self.damage_raw),
                (self.policy_raw, self.limits_raw + b" ", self.damage_raw),
                (self.policy_raw, self.limits_raw, self.damage_raw + b" "),
            )
        ):
            with self.subTest(ordinal=ordinal), self.assertRaisesRegex(
                m2_decoder.DecoderError, "owner"
            ):
                m2_decoder.ObservationDecoder(*raws)

    def test_bare_failure_schema_is_bound_to_admitted_owner(self) -> None:
        decoder = m2_decoder.ObservationDecoder(
            self.policy_raw, self.limits_raw, self.damage_raw
        )
        result = m2_decoder.DecodeResult("failure", None, (), (), False)
        self.assertEqual(
            json.loads(decoder.render_result(m2_decoder.OBS_BITS, result))[
                "schema"
            ],
            "golden-board.m2-damage-decoder-result/v1",
        )
        self.assertEqual(
            json.loads(
                m2_decoder.render_decoder_result(m2_decoder.OBS_BITS, result)
            )["schema"],
            "golden-board.m2-damage-decoder-result/v0",
        )
        for version in (-1, 2, True):
            with self.subTest(version=version), self.assertRaisesRegex(
                m2_decoder.DecoderError, "result-shape"
            ):
                m2_decoder.render_decoder_result(
                    m2_decoder.OBS_BITS, result, schema_version=version
                )

    def test_hopeless_present_rep5_group_is_fully_charged(self) -> None:
        decoder = m2_decoder.ObservationDecoder(
            self.policy_raw, self.limits_raw, self.damage_raw
        )
        profile = decoder.profiles[0]
        observations = tuple(
            m2_decoder._ObservedUnit(unit_id, bytes(216), ())
            for unit_id in range(1, 6)
        )
        result = decoder._recover_sections(
            profile,
            observations,
            retain_extra_inputs=True,
            transport_primitive_steps=80_435,
            transport_peak_scratch=4_613,
            repetition_primitive_steps=24,
            repetition_peak_scratch=10,
        )
        self.assertFalse(result.inventory_available)
        self.assertEqual(
            result.resource,
            m2_decoder.ResourceUsage(
                0,
                5 * 24 * 80_435 + 1_728 * 24 + 24 * 80_435,
                4_613,
            ),
        )

    def test_foreign_initial_group_cannot_replace_route_fixed_section_one(self) -> None:
        decoder = m2_decoder.ObservationDecoder(
            self.policy_raw, self.limits_raw, self.damage_raw
        )
        envelope = bootstrap.encode_section_envelope(
            bootstrap.SectionEnvelope(1, 1, 1, 128, 1, (), b"inventory-like")
        )
        clean = bootstrap.fragment_section(envelope, 7, 0)[0]
        block = bootstrap.decode_common_block(clean, 7)
        foreign = bootstrap.encode_common_block(
            bootstrap.CommonBlock(
                2,
                block.section_id,
                block.semantic_copy_id,
                block.section_type,
                block.section_version,
                block.fragment_index,
                block.fragment_count,
                block.section_envelope_length,
                block.payload,
            )
        )
        observations = tuple(
            _v7_observation(unit_id, foreign) for unit_id in range(1, 6)
        )
        result = decoder._without_inventory(decoder.profiles, observations)
        self.assertEqual(
            result.section_results,
            (m2_decoder.SectionResult(1, "corrupt", None),),
        )
        self.assertEqual(result.resource.section_attempts, 0)
        self.assertEqual(
            [row.profile_id for row in result.fragment_diagnostics],
            ["eh72-r2-crc64-ecma-v0"] * 5,
        )
        self.assertEqual(
            [(row.replica_index, row.physical_replica_count) for row in result.fragment_diagnostics],
            [(index, 5) for index in range(5)],
        )

    def test_worker_catch_path_keeps_v1_result_schema(self) -> None:
        class FakeRust:
            @staticmethod
            def decode(_channel: str, _raw: bytes) -> bytes:
                return b"{}\n"

        names = (
            "_WORKER_POLICY_RAW",
            "_WORKER_LIMITS_RAW",
            "_WORKER_DAMAGE_RAW",
            "_WORKER_CLEAN_ENVELOPES",
            "_WORKER_RUST_DECODER",
            "_WORKER_RESULT_SCHEMA_VERSION",
        )
        previous = {name: getattr(m2_damage, name) for name in names}
        try:
            m2_damage._WORKER_POLICY_RAW = self.policy_raw
            m2_damage._WORKER_LIMITS_RAW = self.limits_raw
            m2_damage._WORKER_DAMAGE_RAW = self.damage_raw
            m2_damage._WORKER_CLEAN_ENVELOPES = {}
            m2_damage._WORKER_RUST_DECODER = FakeRust()
            m2_damage._WORKER_RESULT_SCHEMA_VERSION = 1
            _, actual_raw, rust_raw, state, rows, wrong = (
                m2_damage._decoder_worker_evaluate(
                    ("synthetic", m2_decoder.OBS_BITS, b"")
                )
            )
        finally:
            for name, value in previous.items():
                setattr(m2_damage, name, value)
        self.assertEqual(
            json.loads(actual_raw)["schema"],
            "golden-board.m2-damage-decoder-result/v1",
        )
        self.assertEqual((rust_raw, state, rows, wrong), (b"{}\n", "failure", (), 0))

    def test_obs_units_transport_enumeration_is_id_then_registry(self) -> None:
        decoder = m2_decoder.ObservationDecoder(
            self.policy_raw, self.limits_raw, self.damage_raw
        )
        calls: list[tuple[int, int]] = []

        def fake_decode(
            profile: m2_codec.CandidateProfile,
            encoded: bytes,
            _erasures: tuple[int, ...],
        ) -> m2_codec.Recovery:
            calls.append((encoded[0], profile.profile_version))
            return m2_codec.Recovery("corrupt", None, 0)

        decoder._decode_unit = fake_decode
        raw = b"".join(
            (
                (2).to_bytes(4, "big"),
                (2).to_bytes(4, "big"),
                (216).to_bytes(2, "big"),
                bytes((2,)) + bytes(215),
                (1).to_bytes(4, "big"),
                (216).to_bytes(2, "big"),
                bytes((1,)) + bytes(215),
            )
        )
        decoder.decode(m2_decoder.OBS_UNITS, raw)
        self.assertEqual(
            calls[:8],
            [
                (input_id, profile_version)
                for input_id in (1, 2)
                for profile_version in (7, 2, 3, 4)
            ],
        )

    def test_clean_persisted_carrier_matches_independent_rust_kat(self) -> None:
        decoder = m2_decoder.ObservationDecoder(
            self.policy_raw, self.limits_raw, self.damage_raw
        )
        carrier_path = ROOT / (
            "artifacts/candidates/eh72-hier-r5-r2-r1-crc32c-v0/"
            "carrier.obs-bits"
        )
        if not carrier_path.is_file():
            carrier_path = ROOT / (
                "artifacts/history/"
                "m2-r3-pre-damage-artifact-schema-clarification/"
                "eh72-hier-r5-r2-r1-crc32c-v0/carrier.obs-bits"
            )
        carrier = carrier_path.read_bytes()
        result = decoder.decode(m2_decoder.OBS_BITS, carrier)
        raw = decoder.render_result(m2_decoder.OBS_BITS, result)
        self.assertEqual(
            (
                result.artifact_state,
                result.profile_id,
                len(result.section_results),
                len(result.accepted_hypotheses),
                result.resource,
                len(raw),
                sha256(raw).hexdigest(),
            ),
            (
                "exact",
                "eh72-hier-r5-r2-r1-crc32c-v0",
                138,
                4,
                m2_decoder.ResourceUsage(138, 17_938_790_552, 6_163),
                18_303,
                "19b0672e7e05e3740439eab0f2055a618fb909f59ab65421d8213aa1ae16252c",
            ),
        )


class M2ProductionDecoder(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy_raw = _read("spec/profile-policy-v0.toml")
        cls.limits_raw = _read("spec/profile-limits-v0.toml")
        cls.damage_raw = _read("spec/damage-policy-v0.toml")
        cls.profiles = m2_codec.load_candidate_profiles(
            cls.policy_raw, cls.limits_raw
        )

    def _decode_clean(self, profile_id: str) -> tuple[m2_decoder.DecodeResult, bytes]:
        carrier = _read(f"artifacts/candidates/{profile_id}/carrier.obs-bits")
        result = m2_decoder.ObservationDecoder(
            self.policy_raw, self.limits_raw, self.damage_raw
        ).decode(m2_decoder.OBS_BITS, carrier)
        return result, m2_decoder.render_decoder_result(
            m2_decoder.OBS_BITS, result
        )

    @unittest.skipUnless(
        RETAINED_LEGACY_CANDIDATES,
        "retained ignored legacy candidates are absent in a clean execution snapshot",
    )
    def test_clean_cross_language_results_and_resources_are_exact(self) -> None:
        expected = {
            P1: (
                137,
                12_849_712_464,
                6_163,
                18_125,
                "bc2a853b5dd4be7bf6686807efbe65dc00e9af7f98f4a9dd2300ee1299640779",
            ),
            P3: (
                135,
                14_092_915_824,
                6_163,
                17_879,
                "d6aa54580c2bf7f12073147a6b910b8c7dbea9c67c22639916befbdf7d363a97",
            ),
        }
        for profile_id, wanted in expected.items():
            with self.subTest(profile_id=profile_id):
                result, raw = self._decode_clean(profile_id)
                self.assertEqual(result.artifact_state, "exact")
                self.assertEqual(result.profile_id, profile_id)
                self.assertTrue(result.inventory_available)
                self.assertEqual(len(result.accepted_hypotheses), 4)
                self.assertEqual(
                    (
                        result.resource.section_attempts,
                        result.resource.primitive_steps,
                        result.resource.peak_scratch_bytes,
                        len(raw),
                        sha256(raw).hexdigest(),
                    ),
                    wanted,
                )

    def test_eh72_syndrome_path_matches_exhaustive_correction_domain(self) -> None:
        encoded = m2_codec.eh72_encode(bytes.fromhex("0123456789abcdef"))
        cases: list[tuple[bytes, tuple[int, ...]]] = [(encoded, ())]
        for position in range(72):
            cases.extend(
                (
                    (_flip_bit(encoded, position), ()),
                    (encoded, (position + 1,)),
                    (_flip_bit(encoded, position), (position + 1,)),
                )
            )
        for erased_position in (0, 35, 71):
            cases.extend(
                (_flip_bit(encoded, changed_position), (erased_position + 1,))
                for changed_position in range(72)
                if changed_position != erased_position
            )
        for erasures in ((1, 2), (1, 72), (36, 37), (71, 72), (1, 36, 72)):
            for mask in range(1 << len(erasures)):
                observed = encoded
                for ordinal, position in enumerate(erasures):
                    if mask >> ordinal & 1:
                        observed = _flip_bit(observed, position - 1)
                cases.append((observed, erasures))
        for observed, erasures in cases:
            with self.subTest(erasures=erasures):
                self.assertEqual(
                    m2_decoder._eh72_decode_syndrome(observed, erasures),
                    m2_codec.eh72_decode(observed, erasures),
                )

    @unittest.skipUnless(
        RETAINED_LEGACY_CANDIDATES,
        "retained ignored legacy candidates are absent in a clean execution snapshot",
    )
    def test_bounded_worker_requires_oracle_python_and_rust_equality(self) -> None:
        base = ROOT / "artifacts" / "candidates" / P3
        manifestation = m2_carrier.Manifestation(
            P3,
            *(
                (base / name).read_bytes()
                for name in (
                    "semantic-envelope.json",
                    "carrier.obs-bits",
                    "candidate-manifest.json",
                    "ownership-ledger.json",
                    "capacity-ledger.json",
                    "density-ledger.json",
                )
            ),
        )
        profile = next(item for item in self.profiles if item.profile_id == P3)
        context = m2_damage._Context(manifestation, profile)
        alternate_package = _emit(1)
        case_id = "D0-000000"
        parameters = {
            "polarity_id": ("u64", 0),
            "transform_id": ("u64", 0),
        }

        evaluator = m2_damage._DamageEvaluator(
            context,
            self.policy_raw,
            self.limits_raw,
            self.damage_raw,
            alternate_package,
            _rust_decoder_command(),
            1,
        )
        digest, wrong = evaluator.evaluate(
            case_id,
            "clean-transform-polarity",
            parameters,
            m2_decoder.OBS_BITS,
            manifestation.carrier,
            context.evaluate(),
        )
        rows: list[dict[str, object]] = [
            {"case_id": case_id, "wrong_accept_count": wrong}
        ]
        evaluator.finish(rows)
        self.assertTrue(evaluator.match_by_case[case_id])
        self.assertEqual(rows[0]["wrong_accept_count"], 0)
        self.assertEqual(
            digest,
            "d6aa54580c2bf7f12073147a6b910b8c7dbea9c67c22639916befbdf7d363a97",
        )
        self.assertEqual(
            sha256(evaluator.boundary_kat()).hexdigest(),
            "4ad1468cd6cac6774b95e997d37c6fb420ff94cc0aa82595aeaa7b356440a68b",
        )
        evaluator.close()

        mismatch_program = """
import sys
while True:
    header = sys.stdin.buffer.read(5)
    if not header:
        break
    if len(header) != 5:
        raise SystemExit(2)
    size = int.from_bytes(header[1:], 'big')
    if len(sys.stdin.buffer.read(size)) != size:
        raise SystemExit(2)
    raw = b'{}\\n'
    sys.stdout.buffer.write(len(raw).to_bytes(4, 'big') + raw)
    sys.stdout.buffer.flush()
"""
        evaluator = m2_damage._DamageEvaluator(
            context,
            self.policy_raw,
            self.limits_raw,
            self.damage_raw,
            alternate_package,
            (sys.executable, "-c", mismatch_program),
            1,
        )
        _digest, wrong = evaluator.evaluate(
            case_id,
            "clean-transform-polarity",
            parameters,
            m2_decoder.OBS_BITS,
            manifestation.carrier,
            context.evaluate(),
        )
        rows = [{"case_id": case_id, "wrong_accept_count": wrong}]
        evaluator.finish(rows)
        self.assertFalse(evaluator.match_by_case[case_id])
        evaluator.close()

        evaluator = m2_damage._DamageEvaluator(
            context,
            self.policy_raw,
            self.limits_raw,
            self.damage_raw,
            alternate_package,
            (sys.executable, "-c", "raise SystemExit(7)"),
            1,
        )
        _digest, wrong = evaluator.evaluate(
            case_id,
            "clean-transform-polarity",
            parameters,
            m2_decoder.OBS_BITS,
            manifestation.carrier,
            context.evaluate(),
        )
        rows = [{"case_id": case_id, "wrong_accept_count": wrong}]
        with self.assertRaises(m2_damage.DamageError):
            evaluator.finish(rows)

        if (os.cpu_count() or 1) >= 2:
            evaluator = m2_damage._DamageEvaluator(
                context,
                self.policy_raw,
                self.limits_raw,
                self.damage_raw,
                alternate_package,
                _rust_decoder_command(),
                2,
            )
            rows = []
            for ordinal in range(2):
                parallel_case_id = f"D0-{ordinal:06d}"
                _digest, wrong = evaluator.evaluate(
                    parallel_case_id,
                    "clean-transform-polarity",
                    parameters,
                    m2_decoder.OBS_BITS,
                    manifestation.carrier,
                    context.evaluate(),
                )
                rows.append(
                    {
                        "case_id": parallel_case_id,
                        "wrong_accept_count": wrong,
                    }
                )
            evaluator.finish(rows)
            self.assertEqual(
                [evaluator.match_by_case[str(row["case_id"])] for row in rows],
                [True, True],
            )
            evaluator.close()

    @unittest.skipUnless(
        RETAINED_LEGACY_CANDIDATES,
        "retained ignored legacy candidates are absent in a clean execution snapshot",
    )
    def test_d0_transform_ids_one_and_three_are_not_inverted(self) -> None:
        base = ROOT / "artifacts" / "candidates" / P3
        manifestation = m2_carrier.Manifestation(
            P3,
            *(
                (base / name).read_bytes()
                for name in (
                    "semantic-envelope.json",
                    "carrier.obs-bits",
                    "candidate-manifest.json",
                    "ownership-ledger.json",
                    "capacity-ledger.json",
                    "density-ledger.json",
                )
            ),
        )
        profile = next(item for item in self.profiles if item.profile_id == P3)
        context = m2_damage._Context(manifestation, profile)
        evaluator = m2_damage._DamageEvaluator(
            context,
            self.policy_raw,
            self.limits_raw,
            self.damage_raw,
            _emit(1),
            _rust_decoder_command(),
            1,
        )
        rows: list[dict[str, object]] = []
        for transform_id in (1, 3):
            case_id = f"D0-{transform_id:06d}"
            observed = m2_damage._transform_matrix(
                context.clean, context.side, transform_id, 0
            )
            _digest, wrong = evaluator.evaluate(
                case_id,
                "clean-transform-polarity",
                {
                    "polarity_id": ("u64", 0),
                    "transform_id": ("u64", transform_id),
                },
                m2_decoder.OBS_BITS,
                m2_damage._obs_bits(observed),
                context.evaluate(),
            )
            rows.append({"case_id": case_id, "wrong_accept_count": wrong})
        evaluator.finish(rows)
        self.assertEqual(
            [evaluator.match_by_case[str(row["case_id"])] for row in rows],
            [True, True],
        )
        self.assertEqual([row["wrong_accept_count"] for row in rows], [0, 0])
        evaluator.close()

    @unittest.skipUnless(
        RETAINED_LEGACY_CANDIDATES,
        "retained ignored legacy candidates are absent in a clean execution snapshot",
    )
    def test_observed_alternate_route_is_followed_without_expected_route_bytes(self) -> None:
        carrier = _read(f"artifacts/candidates/{P1}/carrier.obs-bits")
        cells = _bits(carrier)
        side, width = 1_952, 128
        alternate_profile = next(
            profile for profile in self.profiles if profile.profile_id == P3
        )
        routes = m2_route_data.build_route_images(
            _read("spec/route-data-v0.json"),
            m2_route_data.CandidateRouteData(
                alternate_profile.profile_id,
                alternate_profile.profile_version,
                alternate_profile.transport_id,
                alternate_profile.section_check_id,
                (_emit(alternate_profile.profile_version),),
            ),
            side,
            width,
        )
        alternate = routes.sectors[0].data
        for offset in range(width * (side - width)):
            row, column = bootstrap.sector_cell(side, width, 0, offset)
            cells[row * side + column] = (
                alternate[offset // 8] >> (7 - offset % 8)
            ) & 1
        result = m2_decoder.ObservationDecoder(
            self.policy_raw, self.limits_raw, self.damage_raw
        ).decode(m2_decoder.OBS_BITS, _obs_bits(cells))
        self.assertEqual((result.artifact_state, result.profile_id), ("exact", P1))
        self.assertEqual(
            [(item.sector_id, item.profile_id) for item in result.accepted_hypotheses],
            [(0, P3), (1, P1), (2, P1), (3, P1)],
        )

    def test_boundary_kat_uses_real_section_assembler(self) -> None:
        raw = m2_decoder.section_attempt_boundary_kat()
        self.assertEqual(len(raw), 307)
        self.assertEqual(
            sha256(raw).hexdigest(),
            "4ad1468cd6cac6774b95e997d37c6fb420ff94cc0aa82595aeaa7b356440a68b",
        )

    def test_parser_is_fail_closed_and_public_boundary_is_observation_only(self) -> None:
        decoder = m2_decoder.ObservationDecoder(
            self.policy_raw, self.limits_raw, self.damage_raw
        )
        for channel, raw in (
            (m2_decoder.OBS_BITS, b"\0\0\0\x09\x80\x01"),
            (m2_decoder.OBS_MATRIX, b"\0\x01\x03"),
            (m2_decoder.OBS_UNITS, b"\0\0\0\x01\0\0\0\x01\0\0"),
        ):
            with self.subTest(channel=channel), self.assertRaises(
                m2_decoder.DecoderError
            ):
                decoder.decode(channel, raw)
        parameters = tuple(inspect.signature(m2_decoder.decode_observation).parameters)
        self.assertEqual(
            parameters,
            (
                "channel",
                "raw",
                "profile_policy_raw",
                "profile_limits_raw",
                "damage_policy_raw",
            ),
        )
        source = inspect.getsource(m2_decoder)
        self.assertNotIn("m2_route_data", source)
        self.assertNotIn("route_manifest_raw", source)


if __name__ == "__main__":
    unittest.main()
