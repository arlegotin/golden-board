from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stderr
from dataclasses import replace
from hashlib import sha256
from io import StringIO
import os
from pathlib import Path
import shutil
import tempfile
from time import monotonic
import unittest
from unittest import mock

from golden_board import (
    bootstrap,
    canonical_manifest,
    identity,
    m2_codec,
    m2_damage,
    m2_decoder,
    m2_independence,
    m2_recipe,
    m2_route_data,
)
from tools.m2 import generate_damage, probe_r3_damage


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "artifacts" / "candidates" / generate_damage.PROFILE_ID
DAMAGE = BASE / "damage"
LEGACY_BASE = ROOT / "artifacts" / "candidates" / "eh72-r3-crc32c-v0"
RETAINED_R3_CANDIDATE = (BASE / "candidate-manifest.json").is_file()


def _retained_run(base: Path) -> m2_damage.DamageRun:
    damage = base / "damage"
    manifest = (damage / "damage-manifest.json").read_bytes()
    document = canonical_manifest.validate_canonical_manifest(manifest)
    families = tuple(
        (damage / f"damage-D{index}.json").read_bytes() for index in range(8)
    )
    shards = tuple(
        (path.name, path.read_bytes())
        for path in sorted(damage.glob("damage-D*-cases-*.json"))
    )
    family_counts = tuple(
        (row["family_id"], row["case_count"])
        for row in document["summary"]["family_case_counts"]
    )
    wrong = document["summary"]["wrong_accept_count"]
    gate6 = (
        "pass"
        if wrong == 0
        and all(row["result"] == "pass" for row in document["family_rows"])
        else "fail"
    )
    return m2_damage.DamageRun(
        base.name,
        manifest,
        document["summary"]["manifest_identity"],
        families,
        shards,
        sum(count for _, count in family_counts),
        family_counts,
        wrong,
        gate6,
        "not_evaluated",
    )


class M2DamageCLI(unittest.TestCase):
    def test_d7_range_probe_bounds_are_exact(self) -> None:
        arguments = probe_r3_damage._arguments(
            ["--first", "5", "--stop", "7", "--workers", "1"]
        )
        self.assertEqual(
            (arguments.first, arguments.stop, arguments.workers),
            (5, 7, 1),
        )
        invalid_ranges = ((0, 0), (-1, 1), (407, 409), (0, 33))
        for first, stop in invalid_ranges:
            with self.subTest(first=first, stop=stop):
                with redirect_stderr(StringIO()):
                    with self.assertRaises(SystemExit):
                        probe_r3_damage._arguments(
                            [
                                "--first",
                                str(first),
                                "--stop",
                                str(stop),
                                "--workers",
                                "1",
                            ]
                        )

    def test_r3_decoder_disagreement_fails_early_with_bounded_diagnostics(
        self,
    ) -> None:
        expected_raw = canonical_manifest.serialize_manifest(
            {"artifact_state": "failure", "resource": {"steps": 1}}
        )
        python_raw = canonical_manifest.serialize_manifest(
            {"artifact_state": "failure", "resource": {"steps": 2}}
        )
        rust_raw = canonical_manifest.serialize_manifest(
            {"artifact_state": "exact", "resource": {"steps": 2}}
        )
        pending = mock.Mock()
        pending.get.return_value = (
            "D6-000123",
            python_raw,
            rust_raw,
            "failure",
            ((1, "verified"),),
            0,
        )
        evaluator = object.__new__(m2_damage._DamageEvaluator)
        evaluator._pending = [
            (
                "D6-000123",
                pending,
                expected_raw,
                "failure",
                ((1, "verified"),),
                0,
            )
        ]
        evaluator._actual_wrong = {}
        evaluator.match_by_case = {}
        evaluator.capture_mismatches = False
        evaluator.mismatch_raw_by_case = {}
        evaluator.context = mock.Mock(is_r3=True)

        with mock.patch.object(evaluator, "_abort") as abort:
            with self.assertRaises(m2_damage.DamageError) as caught:
                evaluator._finish_next()
        reason = caught.exception.reason
        self.assertIn("decoder-independent-disagreement", reason)
        self.assertIn("case=D6-000123", reason)
        self.assertIn(
            f"expected_sha256={sha256(expected_raw).hexdigest()}", reason
        )
        self.assertIn(
            f"python_sha256={sha256(python_raw).hexdigest()}", reason
        )
        self.assertIn(f"rust_sha256={sha256(rust_raw).hexdigest()}", reason)
        self.assertIn("expected_python_keys=resource", reason)
        self.assertIn("python_rust_keys=artifact_state", reason)
        self.assertIn("projection_deltas=none", reason)
        abort.assert_called_once_with()

    def test_worker_default_and_bounds_are_exact(self) -> None:
        maximum = min(8, os.cpu_count() or 1)
        self.assertEqual(generate_damage._parse_arguments([]).workers, maximum)
        self.assertEqual(
            generate_damage._parse_arguments(["--workers", "1"]).workers,
            1,
        )
        self.assertEqual(
            generate_damage._parse_arguments(
                ["--workers", str(maximum)]
            ).workers,
            maximum,
        )
        for value in ("0", str(maximum + 1), "not-an-integer"):
            with self.subTest(value=value), redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    generate_damage._parse_arguments(["--workers", value])
                self.assertEqual(caught.exception.code, 2)

    def test_default_is_check_only_and_modes_are_closed(self) -> None:
        default = generate_damage._parse_arguments([])
        self.assertFalse(default.check)
        self.assertFalse(default.create)
        self.assertFalse(default.gate7)
        self.assertTrue(generate_damage._parse_arguments(["--check"]).check)
        self.assertTrue(generate_damage._parse_arguments(["--create"]).create)
        self.assertTrue(generate_damage._parse_arguments(["--gate7"]).gate7)
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            generate_damage._parse_arguments(["--create", "--gate7"])
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            generate_damage._parse_arguments(["--check", "--create"])
        with mock.patch.object(
            generate_damage, "_parse_arguments", return_value=default
        ), mock.patch.object(
            generate_damage, "check_existing", return_value="checked"
        ) as checked, mock.patch.object(
            generate_damage, "_build_rust_binary"
        ) as built, mock.patch("builtins.print"):
            self.assertEqual(generate_damage.main(), 0)
        checked.assert_called_once_with()
        built.assert_not_called()

    def test_only_v1_rust_bridge_binary_is_admitted(self) -> None:
        self.assertEqual(
            generate_damage.RUST_DECODER.name, "gb-r3-damage-decoder"
        )
        with self.assertRaisesRegex(
            generate_damage.DamageWriterError, "rust-binary-name"
        ):
            generate_damage._build_rust_binary("gb-damage-decoder")

    def test_v1_bridge_channels_and_boundary_ordinals_are_exact(self) -> None:
        decoder = object.__new__(m2_damage.RustBatchDecoder)
        with mock.patch.object(
            m2_damage.RustBatchDecoder, "_exchange", return_value=b"result"
        ) as exchange:
            for channel, channel_id in (
                ("OBS_BITS", 0),
                ("OBS_MATRIX", 1),
                ("OBS_UNITS", 2),
            ):
                self.assertEqual(decoder.decode(channel, b"observation"), b"result")
                exchange.assert_called_with(channel_id, b"observation")
            for ordinal in range(4):
                self.assertEqual(decoder.boundary_kat(ordinal), b"result")
                exchange.assert_called_with(255, bytes((ordinal,)))

    def test_hierarchical_and_eh_lanes_charge_all_24_codewords(self) -> None:
        active = m2_codec.r3_candidate_profile(
            protected_units=1_841,
            encoded_transport_bytes=397_656,
        )
        profiles = m2_codec.r3_registry_profiles(active)
        self.assertEqual(
            tuple(
                m2_damage._transport_lane_invocations(profile)
                for profile in profiles
            ),
            (24, 24, 24, 24, 1, 1),
        )

    def test_case_row_commitment_streams_beyond_artifact_limit(self) -> None:
        rows = [
            {"case_id": f"D6-{index:06d}", "payload": "x" * 256}
            for index in range(5_000)
        ]
        small = canonical_manifest.serialize_manifest({"rows": rows[:3]})
        self.assertEqual(
            m2_damage._canonical_array_sha256(rows[:3]),
            sha256(small[8:-2]).hexdigest(),
        )
        with self.assertRaises(canonical_manifest.ManifestError):
            canonical_manifest.serialize_manifest({"rows": rows})
        digest = sha256()
        digest.update(b"[")
        for index, row in enumerate(rows):
            if index:
                digest.update(b",")
            digest.update(canonical_manifest.serialize_manifest(row)[:-1])
        digest.update(b"]")
        self.assertEqual(
            m2_damage._canonical_array_sha256(rows), digest.hexdigest()
        )
        self.assertEqual(
            m2_independence._canonical_array_sha256(rows), digest.hexdigest()
        )


@unittest.skipUnless(
    RETAINED_R3_CANDIDATE,
    "retained ignored Gate 1-5 candidate is absent in a clean execution snapshot",
)
class M2R3DamageWriterBounded(unittest.TestCase):
    @staticmethod
    def _copy_context(directory: str) -> tuple[Path, Path]:
        workspace = Path(directory)
        spec = workspace / "spec"
        spec.mkdir()
        for name in (
            "profile-policy-v1.toml",
            "profile-limits-v1.toml",
            "damage-policy-v1.toml",
            "bootstrap-v1.md",
            "route-data-v1.json",
            "route-data-v0.json",
        ):
            shutil.copyfile(ROOT / "spec" / name, spec / name)
        candidate = (
            workspace
            / "artifacts"
            / "candidates"
            / generate_damage.PROFILE_ID
        )
        candidate.mkdir(parents=True)
        for name in generate_damage.generate_candidates.R3_ALLOWLIST:
            shutil.copyfile(
                ROOT
                / "artifacts"
                / "candidates"
                / generate_damage.PROFILE_ID
                / name,
                candidate / name,
            )
        return workspace, candidate

    @staticmethod
    def _fake_gate6_values() -> dict[str, bytes]:
        values = {"damage-manifest.json": b"root\n"}
        for family_index in range(8):
            values[f"damage-D{family_index}.json"] = (
                canonical_manifest.serialize_manifest(
                    {
                        "schema": m2_damage.R3_FAMILY_SCHEMA,
                        "family_id": f"D{family_index}",
                        "shard_rows": [{"shard_ordinal": 0}],
                    }
                )
            )
            values[f"damage-D{family_index}-cases-0000.json"] = b"case\n"
        return values

    @staticmethod
    def _write_gate6(candidate: Path, values: dict[str, bytes]) -> None:
        damage = candidate / "damage"
        damage.mkdir()
        for name, raw in values.items():
            (damage / name).write_bytes(raw)

    def test_owner_reads_are_workspace_local_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="golden-board-r3-damage-owner-"
        ) as directory:
            workspace, candidate = self._copy_context(directory)
            admitted = generate_damage._owner_inputs(workspace, candidate)
            self.assertEqual(admitted.profile.profile_id, generate_damage.PROFILE_ID)
            path = workspace / "spec" / "damage-policy-v1.toml"
            path.write_bytes(path.read_bytes() + b" ")
            with self.assertRaisesRegex(
                generate_damage.DamageWriterError, "owner-admission"
            ):
                generate_damage._owner_inputs(workspace, candidate)

    def test_gate6_publish_is_noreplace_idempotent_and_cleans_failure(self) -> None:
        values = {
            "damage-manifest.json": b"root\n",
            **{f"damage-D{index}.json": b"family\n" for index in range(8)},
        }
        with tempfile.TemporaryDirectory(
            prefix="golden-board-r3-damage-publish-"
        ) as directory:
            workspace, candidate = self._copy_context(directory)
            inputs = generate_damage._owner_inputs(workspace, candidate)
            fake_admission = object()
            with mock.patch.object(
                generate_damage,
                "_validate_gate6_values",
                return_value=fake_admission,
            ):
                self.assertEqual(
                    generate_damage.persist_gate6(inputs, values), "created"
                )
                self.assertEqual(
                    generate_damage.persist_gate6(inputs, values), "unchanged"
                )
            shutil.rmtree(candidate / "damage")
            with mock.patch.object(
                generate_damage,
                "_validate_gate6_values",
                return_value=fake_admission,
            ), mock.patch.object(
                generate_damage,
                "_rename_noreplace",
                side_effect=generate_damage.DamageWriterError("injected"),
            ):
                with self.assertRaisesRegex(
                    generate_damage.DamageWriterError, "injected"
                ):
                    generate_damage.persist_gate6(inputs, values)
            self.assertFalse((candidate / "damage").exists())
            self.assertFalse(
                any(path.name.startswith(".m2-damage-stage-") for path in candidate.iterdir())
            )

    def test_regular_file_reader_rejects_links(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="golden-board-r3-damage-links-"
        ) as directory:
            root = Path(directory)
            source = root / "source"
            source.write_bytes(b"x")
            symlink = root / "symlink"
            os.symlink(source, symlink)
            hardlink = root / "hardlink"
            os.link(source, hardlink)
            for path in (source, symlink, hardlink):
                with self.subTest(path=path.name), self.assertRaisesRegex(
                    generate_damage.DamageWriterError, "test-link"
                ):
                    generate_damage._real_regular(path, "test-link")

    def test_gate7_publishes_only_converged_proof_and_is_idempotent(self) -> None:
        proof = m2_independence.IndependenceProof(
            b"proof\n", "a" * 64, "pass", ()
        )
        values = self._fake_gate6_values()
        with tempfile.TemporaryDirectory(
            prefix="golden-board-r3-gate7-publish-"
        ) as directory:
            workspace, candidate = self._copy_context(directory)
            self._write_gate6(candidate, values)
            admitted = mock.Mock(result="pass")
            with mock.patch.object(
                generate_damage, "ROOT", workspace
            ), mock.patch.object(
                generate_damage, "CANDIDATE_ROOT", candidate
            ), mock.patch.object(
                generate_damage,
                "_validate_gate6_values",
                return_value=admitted,
            ), mock.patch.object(
                generate_damage, "_build_python_proof", return_value=proof
            ), mock.patch.object(
                generate_damage, "_run_rust_proof", return_value=proof.raw
            ), mock.patch.object(
                generate_damage, "_validate_proof_bytes", return_value=proof
            ):
                self.assertEqual(
                    generate_damage._create_gate7_with_binary(
                        Path("/unused-rust-proof"), workspace, candidate
                    ),
                    "created-pass",
                )
                before = {
                    name: (candidate / "damage" / name).read_bytes()
                    for name in values
                }
                self.assertEqual(
                    generate_damage._create_gate7_with_binary(
                        Path("/unused-rust-proof"), workspace, candidate
                    ),
                    "unchanged",
                )
                self.assertEqual(
                    generate_damage.check_existing(
                        workspace,
                        candidate,
                        Path("/unused-rust-proof"),
                    ),
                    "gate7-pass",
                )
            self.assertEqual(
                (candidate / "damage" / generate_damage.INDEPENDENCE_FILE).read_bytes(),
                proof.raw,
            )
            self.assertEqual(
                {
                    name: (candidate / "damage" / name).read_bytes()
                    for name in values
                },
                before,
            )
            self.assertFalse(
                any(
                    path.name.startswith(".m2-proof-stage-")
                    for path in candidate.iterdir()
                )
            )

    def test_gate7_retains_converged_failure(self) -> None:
        proof = m2_independence.IndependenceProof(
            b"failing-proof\n", "b" * 64, "fail", ()
        )
        with tempfile.TemporaryDirectory(
            prefix="golden-board-r3-gate7-fail-"
        ) as directory:
            workspace, candidate = self._copy_context(directory)
            self._write_gate6(candidate, self._fake_gate6_values())
            admitted = mock.Mock(result="pass")

            with mock.patch.object(
                generate_damage, "ROOT", workspace
            ), mock.patch.object(
                generate_damage, "CANDIDATE_ROOT", candidate
            ), mock.patch.object(
                generate_damage,
                "_validate_gate6_values",
                return_value=admitted,
            ), mock.patch.object(
                generate_damage, "_build_python_proof", return_value=proof
            ), mock.patch.object(
                generate_damage, "_run_rust_proof", return_value=proof.raw
            ), mock.patch.object(
                generate_damage, "_validate_proof_bytes", return_value=proof
            ):
                self.assertEqual(
                    generate_damage._create_gate7_with_binary(
                        Path("/unused-rust-proof"), workspace, candidate
                    ),
                    "created-fail",
                )
            self.assertEqual(
                (candidate / "damage" / generate_damage.INDEPENDENCE_FILE).read_bytes(),
                proof.raw,
            )

    def test_gate7_disagreement_or_failed_gate6_writes_nothing(self) -> None:
        values = self._fake_gate6_values()
        proof = m2_independence.IndependenceProof(
            b"python-proof\n", "c" * 64, "pass", ()
        )
        for gate6_result, rust_raw, reason in (
            ("pass", b"rust-proof\n", "proof-independent-disagreement"),
            ("fail", proof.raw, "gate7-after-failed-gate6"),
        ):
            with self.subTest(gate6_result=gate6_result), tempfile.TemporaryDirectory(
                prefix="golden-board-r3-gate7-reject-"
            ) as directory:
                workspace, candidate = self._copy_context(directory)
                self._write_gate6(candidate, values)
                admitted = mock.Mock(result=gate6_result)
                with mock.patch.object(
                    generate_damage, "ROOT", workspace
                ), mock.patch.object(
                    generate_damage, "CANDIDATE_ROOT", candidate
                ), mock.patch.object(
                    generate_damage,
                    "_validate_gate6_values",
                    return_value=admitted,
                ), mock.patch.object(
                    generate_damage, "_build_python_proof", return_value=proof
                ), mock.patch.object(
                    generate_damage, "_run_rust_proof", return_value=rust_raw
                ):
                    with self.assertRaisesRegex(
                        generate_damage.DamageWriterError, reason
                    ):
                        generate_damage._create_gate7_with_binary(
                            Path("/unused-rust-proof"), workspace, candidate
                        )
                self.assertFalse(
                    (candidate / "damage" / generate_damage.INDEPENDENCE_FILE).exists()
                )
                self.assertFalse(
                    any(
                        path.name.startswith(".m2-proof-stage-")
                        or path.name.startswith(".m2-proof-check-")
                        for path in candidate.iterdir()
                    )
                )

    def test_gate7_pre_publish_failure_leaves_gate6_byte_exact(self) -> None:
        values = self._fake_gate6_values()
        proof = m2_independence.IndependenceProof(
            b"proof\n", "d" * 64, "pass", ()
        )
        with tempfile.TemporaryDirectory(
            prefix="golden-board-r3-gate7-injected-"
        ) as directory:
            workspace, candidate = self._copy_context(directory)
            self._write_gate6(candidate, values)
            admitted = mock.Mock(result="pass")
            with mock.patch.object(
                generate_damage,
                "_validate_gate6_values",
                return_value=admitted,
            ), mock.patch.object(
                generate_damage, "_build_python_proof", return_value=proof
            ), mock.patch.object(
                generate_damage, "_run_rust_proof", return_value=proof.raw
            ), mock.patch.object(
                generate_damage, "_validate_proof_bytes", return_value=proof
            ), mock.patch.object(
                generate_damage,
                "_rename_noreplace",
                side_effect=generate_damage.DamageWriterError("injected"),
            ):
                with self.assertRaisesRegex(
                    generate_damage.DamageWriterError, "injected"
                ):
                    generate_damage._create_gate7_with_binary(
                        Path("/unused-rust-proof"), workspace, candidate
                    )
            self.assertEqual(
                {
                    name: (candidate / "damage" / name).read_bytes()
                    for name in values
                },
                values,
            )
            self.assertFalse(
                (candidate / "damage" / generate_damage.INDEPENDENCE_FILE).exists()
            )
            self.assertFalse(
                any(
                    path.name.startswith(".m2-proof-stage-")
                    for path in candidate.iterdir()
                )
            )

    def test_check_without_proof_never_builds_or_runs_gate7(self) -> None:
        values = self._fake_gate6_values()
        for result, expected in (
            ("pass", "gate6-pass-awaiting-gate7"),
            ("fail", "gate6-fail"),
        ):
            with self.subTest(result=result), tempfile.TemporaryDirectory(
                prefix="golden-board-r3-gate6-check-"
            ) as directory:
                workspace, candidate = self._copy_context(directory)
                self._write_gate6(candidate, values)
                with mock.patch.object(
                    generate_damage,
                    "_validate_gate6_values",
                    return_value=mock.Mock(result=result),
                ), mock.patch.object(
                    generate_damage, "_build_rust_binary"
                ) as build, mock.patch.object(
                    generate_damage, "_run_rust_proof"
                ) as run:
                    self.assertEqual(
                        generate_damage.check_existing(workspace, candidate),
                        expected,
                    )
                build.assert_not_called()
                run.assert_not_called()

    def test_rust_proof_stdout_is_bounded_protocol_and_stderr_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="golden-board-r3-proof-cli-"
        ) as directory:
            root = Path(directory)
            binary = root / "proof-cli"
            binary.write_text(
                "#!/bin/sh\nprintf 'benign warning\\n' >&2\nprintf 'proof\\n'\n",
                encoding="utf-8",
            )
            binary.chmod(0o700)
            candidate = root / "candidate"
            ownership = root / "ownership"
            damage = root / "damage"
            candidate.write_bytes(b"candidate")
            ownership.write_bytes(b"ownership")
            damage.mkdir()
            self.assertEqual(
                generate_damage._run_rust_proof(
                    binary, candidate, ownership, damage
                ),
                b"proof\n",
            )


class M2R3DamageAdmissionBounded(unittest.TestCase):
    @unittest.skipUnless(
        RETAINED_R3_CANDIDATE,
        "retained ignored Gate 1-5 candidate is absent in a clean execution snapshot",
    )
    def test_d7_mapping_identity_retains_no_inventory_projection(self) -> None:
        inputs = generate_damage._owner_inputs()
        context = m2_damage._Context(inputs.manifestation, inputs.profile)
        spec = m2_damage._r3_d7_case_spec(
            context, inputs.profile, b"unused", b"unused", 0
        )
        decoder = m2_decoder.ObservationDecoder(
            inputs.profile_policy_raw,
            inputs.profile_limits_raw,
            inputs.damage_policy_raw,
        )
        actual = decoder.decode(spec.channel, spec.observation)
        actual_raw = decoder.render_result(spec.channel, actual)
        value = canonical_manifest.validate_canonical_manifest(actual_raw)

        self.assertEqual(
            actual.section_results,
            spec.expected.decoder_base.section_results,
        )
        self.assertEqual(
            actual.fragment_diagnostics,
            spec.expected.decoder_base.fragment_diagnostics,
        )
        self.assertEqual(actual.artifact_state, spec.expected.artifact_state)
        self.assertEqual(len(actual_raw), 1_431)
        self.assertEqual(
            sha256(actual_raw).hexdigest(),
            "18e4f5da2c37157d11549756a134b456e8ea328ce8dac9d6bbdfdaa8d7fdbc69",
        )
        self.assertEqual(
            value["fragment_diagnostics_sha256"],
            "3e79c23e29ef4f2f904348de5b46447ede164d91c91d41cacaeaa1340852d617",
        )
        self.assertEqual(
            value["section_rows"],
            [
                {
                    "section_id": 1,
                    "semantic_sha256": "0" * 64,
                    "state": "corrupt",
                }
            ],
        )
        self.assertEqual(
            (
                actual.resource.section_attempts,
                actual.resource.primitive_steps,
                actual.resource.peak_scratch_bytes,
            ),
            (0, 14_223_708_344, 6_163),
        )
        self.assertEqual(len(actual.accepted_hypotheses), 4)
        self.assertEqual(len(spec.expected.section_states), 138)
        self.assertEqual(spec.expected.section_states[0], (1, "corrupt"))
        self.assertTrue(
            all(
                state == "unknown"
                for _section_id, state in spec.expected.section_states[1:]
            )
        )

    @unittest.skipUnless(
        RETAINED_R3_CANDIDATE,
        "retained ignored Gate 1-5 candidate is absent in a clean execution snapshot",
    )
    def test_d7_required_check_mutants_have_closed_tier_projection(self) -> None:
        inputs = generate_damage._owner_inputs()
        context = m2_damage._Context(inputs.manifestation, inputs.profile)
        decoder = m2_decoder.ObservationDecoder(
            inputs.profile_policy_raw,
            inputs.profile_limits_raw,
            inputs.damage_policy_raw,
        )
        target_section = 2
        expected = (
            (
                137,
                "abd38e7e9039647929eb95c353a0f33c79f5cdaf8ff790f839e186b662d4a020",
            ),
            (
                138,
                "73949e666f31f87326601f60ed6befe8768f8c7bbb48018c729f9a3b5017aa66",
            ),
        )
        for ordinal, (attempts, digest) in enumerate(expected, start=5):
            spec = m2_damage._r3_d7_case_spec(
                context, inputs.profile, b"unused", b"unused", ordinal
            )
            oracle = spec.expected
            actual = decoder.decode(spec.channel, spec.observation)
            actual_raw = decoder.render_result(spec.channel, actual)
            expected_raw = m2_decoder.render_decoder_result(
                spec.channel,
                replace(oracle.decoder_base, resource=actual.resource),
                schema_version=1,
            )
            value = canonical_manifest.validate_canonical_manifest(actual_raw)

            with self.subTest(case_id=f"D7-{ordinal:06d}"):
                self.assertEqual(oracle.artifact_state, "failure")
                self.assertEqual(oracle.wrong_accepts, 0)
                self.assertIsNone(oracle.decoder_base.m2_required_stream)
                self.assertIsNone(oracle.decoder_base.m2_all_stream)
                self.assertEqual(actual_raw, expected_raw)
                self.assertEqual(len(actual_raw), 17_600)
                self.assertEqual(sha256(actual_raw).hexdigest(), digest)
                self.assertEqual(
                    (
                        actual.resource.section_attempts,
                        actual.resource.primitive_steps,
                        actual.resource.peak_scratch_bytes,
                    ),
                    (attempts, 21_398_719_042, 7_688),
                )
                self.assertEqual(value["artifact_state"], "failure")
                self.assertEqual(
                    value["established_profile_id"], generate_damage.PROFILE_ID
                )
                self.assertEqual(
                    next(
                        row["state"]
                        for row in value["section_rows"]
                        if row["section_id"] == target_section
                    ),
                    "corrupt",
                )
                self.assertFalse(value["m2_required_available"])
                self.assertFalse(value["m2_all_available"])
                self.assertEqual(value["m2_required_stream_sha256"], "0" * 64)
                self.assertEqual(value["m2_all_stream_sha256"], "0" * 64)
                self.assertEqual(value["accepted_hypothesis_rows"], [])

    def test_route_conflict_replaces_prefix_cells_only(self) -> None:
        side = 64
        width = 8
        matrix = bytearray(side * side)
        sector = m2_route_data.SectorImage(0, b"\xff\x00", 5, 7, ())
        m2_damage._replace_sector_route_prefix(matrix, side, width, sector)
        changed = {
            divmod(index, side)
            for index, value in enumerate(matrix)
            if value
        }
        expected = {
            bootstrap.sector_cell(side, width, 0, offset)
            for offset in range(5)
        }
        self.assertEqual(changed, expected)
        self.assertEqual(sum(matrix), 5)

    @unittest.skipUnless(
        RETAINED_R3_CANDIDATE,
        "retained ignored Gate 1-5 candidate is absent in a clean execution snapshot",
    )
    def test_exact_owner_and_candidate_reach_strict_root_validation(self) -> None:
        candidate = ROOT / "artifacts" / "candidates" / generate_damage.PROFILE_ID
        with self.assertRaisesRegex(m2_damage.DamageError, "r3-damage-root"):
            m2_damage.validate_damage_bundle_v1(
                b"{}\n",
                (b"{}\n",) * 8,
                tuple(
                    (f"damage-D{index}-cases-0000.json", b"{}\n")
                    for index in range(8)
                ),
                (ROOT / "spec/damage-policy-v1.toml").read_bytes(),
                (ROOT / "spec/profile-policy-v1.toml").read_bytes(),
                (ROOT / "spec/profile-limits-v1.toml").read_bytes(),
                (ROOT / "spec/bootstrap-v1.md").read_bytes(),
                (ROOT / "spec/route-data-v1.json").read_bytes(),
                m2_recipe.build_r3_recipe_package(),
                (candidate / "candidate-manifest.json").read_bytes(),
                (candidate / "carrier.obs-bits").read_bytes(),
            )


@unittest.skipUnless(
    os.environ.get("GB_M2_R3_PREFLIGHT") == "1",
    "explicit bounded cross-language preflight",
)
class M2R3DamageCrossLanguagePreflight(unittest.TestCase):
    def test_d7_route_resource_ceiling_plus_one_is_global(self) -> None:
        inputs = generate_damage._owner_inputs()
        rust_decoder = generate_damage._build_rust_binary(
            "gb-r3-damage-decoder"
        )
        context = m2_damage._Context(inputs.manifestation, inputs.profile)
        expected_sha256 = (
            "78253f50589a2cb22fe53f38d4959c58ec3483db3e0f74574a1b06634322e71d"
        )
        for ordinal in (405, 406):
            spec = m2_damage._r3_d7_case_spec(
                context, inputs.profile, b"unused", b"unused", ordinal
            )
            expected = spec.expected.decoder_base
            rendered = m2_decoder.render_decoder_result(
                spec.channel, expected, schema_version=1
            )
            with self.subTest(case_id=f"D7-{ordinal:06d}"):
                self.assertEqual(expected.artifact_state, "resource-limit")
                self.assertIsNone(expected.profile_id)
                self.assertEqual(expected.section_results, ())
                self.assertEqual(expected.fragment_diagnostics, ())
                self.assertEqual(expected.accepted_hypotheses, ())
                self.assertEqual(
                    expected.resource, m2_decoder.ResourceUsage()
                )
                self.assertEqual(sha256(rendered).hexdigest(), expected_sha256)

        with tempfile.TemporaryDirectory(
            prefix="golden-board-r3-route-resource-"
        ) as directory:
            alternate_package = generate_damage.generate_candidates._emit_package(
                3, Path(directory)
            )
            before = set(m2_damage._ACTIVE_EVALUATORS)
            self.assertEqual(
                m2_damage.run_r3_d7_range_probe(
                    inputs.manifestation,
                    inputs.profile,
                    inputs.profile_policy_raw,
                    inputs.profile_limits_raw,
                    inputs.damage_policy_raw,
                    alternate_package,
                    inputs.alternate_route_data_raw,
                    (str(rust_decoder),),
                    1,
                    405,
                    407,
                ),
                tuple(
                    (f"D7-{ordinal:06d}", expected_sha256, 0)
                    for ordinal in (405, 406)
                ),
            )
            self.assertEqual(set(m2_damage._ACTIVE_EVALUATORS), before)

    def test_d7_missing_rep5_group_retains_route_fixed_identity(self) -> None:
        inputs = generate_damage._owner_inputs()
        rust_decoder = generate_damage._build_rust_binary(
            "gb-r3-damage-decoder"
        )
        context = m2_damage._Context(inputs.manifestation, inputs.profile)
        spec = m2_damage._r3_d7_case_spec(
            context, inputs.profile, b"unused", b"unused", 401
        )
        expected = spec.expected.decoder_base
        self.assertEqual(expected.artifact_state, "failure")
        self.assertFalse(expected.inventory_available)
        self.assertEqual(len(expected.section_results), 138)
        self.assertEqual(expected.section_results[0].state, "incomplete")
        self.assertTrue(
            all(row.state == "verified" for row in expected.section_results[1:])
        )
        self.assertEqual(len(expected.fragment_diagnostics), 1_841)
        for index, row in enumerate(expected.fragment_diagnostics[:5]):
            with self.subTest(input_id=index + 1):
                self.assertEqual(row.input_id, index + 1)
                self.assertEqual(row.profile_id, generate_damage.PROFILE_ID)
                self.assertEqual(row.section_id, 1)
                self.assertEqual(row.semantic_copy_id, 0)
                self.assertEqual(row.fragment_index, 0)
                self.assertEqual(row.replica_index, index)
                self.assertEqual(row.physical_replica_count, 5)
                self.assertEqual(row.state, "missing")
                self.assertIsNone(row.common_block)
        projected = canonical_manifest.validate_canonical_manifest(
            m2_decoder.render_decoder_result(
                spec.channel, expected, schema_version=1
            )
        )
        self.assertEqual(
            projected["fragment_diagnostics_sha256"],
            "379652c89611f3ef0d503f157e9bc0d0175cc859be083a4bc600b736f4c2a2df",
        )

        with tempfile.TemporaryDirectory(
            prefix="golden-board-r3-missing-rep5-"
        ) as directory:
            alternate_package = generate_damage.generate_candidates._emit_package(
                3, Path(directory)
            )
            before = set(m2_damage._ACTIVE_EVALUATORS)
            self.assertEqual(
                m2_damage.run_r3_d7_range_probe(
                    inputs.manifestation,
                    inputs.profile,
                    inputs.profile_policy_raw,
                    inputs.profile_limits_raw,
                    inputs.damage_policy_raw,
                    alternate_package,
                    inputs.alternate_route_data_raw,
                    (str(rust_decoder),),
                    1,
                    401,
                    402,
                ),
                (
                    (
                        "D7-000401",
                        "1e897f63ed3d222a1e587f1ab1fb599d2da4e6c226396794b7091a5261b421fc",
                        0,
                    ),
                ),
            )
            self.assertEqual(set(m2_damage._ACTIVE_EVALUATORS), before)

    def test_d7_route_conflict_charges_exact_alternate_route(self) -> None:
        inputs = generate_damage._owner_inputs()
        rust_decoder = generate_damage._build_rust_binary(
            "gb-r3-damage-decoder"
        )
        with tempfile.TemporaryDirectory(
            prefix="golden-board-r3-route-conflict-"
        ) as directory:
            alternate_package = generate_damage.generate_candidates._emit_package(
                3, Path(directory)
            )
            context = m2_damage._Context(inputs.manifestation, inputs.profile)
            spec = m2_damage._r3_d7_case_spec(
                context,
                inputs.profile,
                alternate_package,
                inputs.alternate_route_data_raw,
                10,
            )
            alternate_profile = next(
                profile
                for profile in m2_codec.r3_registry_profiles(inputs.profile)
                if profile.profile_version == 3
            )
            alternate_routes = m2_route_data.build_route_images(
                inputs.alternate_route_data_raw,
                m2_route_data.CandidateRouteData(
                    alternate_profile.profile_id,
                    alternate_profile.profile_version,
                    alternate_profile.transport_id,
                    alternate_profile.section_check_id,
                    (alternate_package,),
                ),
                context.side,
                context.width,
            )
            sector = alternate_routes.sectors[0]
            recipe_ids = m2_damage._route_example_recipe_ids(
                sector.data[: sector.route_prefix_cells // 8]
            )
            self.assertEqual(len(recipe_ids), 24)
            self.assertEqual(recipe_ids.count(30), 2)

            decoder = m2_decoder.ObservationDecoder(
                inputs.profile_policy_raw,
                inputs.profile_limits_raw,
                inputs.damage_policy_raw,
            )
            actual = decoder.decode(spec.channel, spec.observation)
            actual_raw = decoder.render_result(spec.channel, actual)
            self.assertEqual(
                (
                    actual.resource.section_attempts,
                    actual.resource.primitive_steps,
                    actual.resource.peak_scratch_bytes,
                ),
                (138, 17_008_208_910, 6_163),
            )
            self.assertEqual(
                sha256(actual_raw).hexdigest(),
                "14f82792480529a158d2d567d64465b6f026d9b19a26e4dbe843e3783cfea87b",
            )

            before = set(m2_damage._ACTIVE_EVALUATORS)
            self.assertEqual(
                m2_damage.run_r3_d7_range_probe(
                    inputs.manifestation,
                    inputs.profile,
                    inputs.profile_policy_raw,
                    inputs.profile_limits_raw,
                    inputs.damage_policy_raw,
                    alternate_package,
                    inputs.alternate_route_data_raw,
                    (str(rust_decoder),),
                    1,
                    10,
                    11,
                ),
                (
                    (
                        "D7-000010",
                        "14f82792480529a158d2d567d64465b6f026d9b19a26e4dbe843e3783cfea87b",
                        0,
                    ),
                ),
            )
            self.assertEqual(set(m2_damage._ACTIVE_EVALUATORS), before)

    def test_representative_cases_are_worker_order_independent(self) -> None:
        inputs = generate_damage._owner_inputs()
        rust_decoder = generate_damage._build_rust_binary(
            "gb-r3-damage-decoder"
        )
        workers_to_run = tuple(
            int(value)
            for value in os.environ.get(
                "GB_M2_R3_PREFLIGHT_WORKERS", "1,2"
            ).split(",")
        )
        self.assertTrue(workers_to_run)
        self.assertTrue(all(value in (1, 2) for value in workers_to_run))
        observed: list[bytes] = []
        elapsed: list[float] = []
        with tempfile.TemporaryDirectory(
            prefix="golden-board-r3-damage-preflight-"
        ) as directory:
            alternate_package = generate_damage.generate_candidates._emit_package(
                3, Path(directory)
            )
            for workers in workers_to_run:
                before = set(m2_damage._ACTIVE_EVALUATORS)
                started = monotonic()
                observed.append(
                    m2_damage.run_r3_damage_preflight(
                        inputs.manifestation,
                        inputs.profile,
                        inputs.profile_policy_raw,
                        inputs.profile_limits_raw,
                        inputs.damage_policy_raw,
                        alternate_package,
                        (str(rust_decoder),),
                        workers,
                    )
                )
                elapsed.append(monotonic() - started)
                self.assertEqual(set(m2_damage._ACTIVE_EVALUATORS), before)
        self.assertTrue(all(raw == observed[0] for raw in observed))
        value = canonical_manifest.validate_canonical_manifest(observed[0])
        self.assertEqual(
            tuple(row["case_id"] for row in value["case_rows"]),
            (
                "D2-000000",
                "D3-000000",
                "D4-000000",
                "D6-000000",
                "D7-000016",
            ),
        )
        self.assertTrue(
            all(row["wrong_accept_count"] == 0 for row in value["case_rows"])
        )
        print(
            "r3 damage preflight seconds: "
            + " ".join(
                f"worker{workers}={seconds:.3f}"
                for workers, seconds in zip(
                    workers_to_run, elapsed, strict=True
                )
            )
        )


@unittest.skip("superseded unbounded v0 fixture walk; bounded compatibility is below")
class M2DamageEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not (DAMAGE / "damage-manifest.json").is_file():
            raise unittest.SkipTest("ignored P7 damage fixtures are not present")
        cls.damage_run = _retained_run(BASE)
        cls.common_raw = cls.damage_run.manifest
        cls.common = canonical_manifest.validate_canonical_manifest(cls.common_raw)
        cls.family_raw = cls.damage_run.family_manifests
        cls.families = tuple(
            canonical_manifest.validate_canonical_manifest(raw)
            for raw in cls.family_raw
        )
        cls.shard_items = cls.damage_run.case_shards
        cls.shards = {
            name: canonical_manifest.validate_canonical_manifest(raw)
            for name, raw in cls.shard_items
        }
        cls.case_rows = tuple(
            row
            for index, family in enumerate(cls.families)
            for shard_row in family["shard_rows"]
            for row in cls.shards[
                f"damage-D{index}-cases-{shard_row['shard_ordinal']:04d}.json"
            ]["case_rows"]
        )

    def test_common_manifest_is_closed_and_bound_to_final_p3_candidate(self) -> None:
        candidate_raw = (BASE / "candidate-manifest.json").read_bytes()
        self.assertEqual(
            sha256(candidate_raw).hexdigest(),
            "1e1bd5551ee357f3f4b809afba480b379c41b7365b971493db8f3bc2e415168b",
        )
        self.assertEqual(self.common["schema"], m2_damage.DAMAGE_SCHEMA)
        self.assertEqual(
            self.common["candidate_manifest_sha256"],
            sha256(candidate_raw).hexdigest(),
        )
        self.assertEqual(
            self.common["damage_policy_sha256"],
            sha256((ROOT / "spec/damage-policy-v0.toml").read_bytes()).hexdigest(),
        )
        self.assertEqual(
            self.common["profile_policy_sha256"],
            sha256((ROOT / "spec/profile-policy-v0.toml").read_bytes()).hexdigest(),
        )
        self.assertEqual(
            self.damage_run.family_case_counts,
            (
                ("D0", 16),
                ("D1", 4),
                ("D2", 256),
                ("D3", 128),
                ("D4", 1825),
                ("D5", 21),
                ("D6", 7300),
                ("D7", 408),
            ),
        )
        self.assertEqual(len(self.case_rows), 9958)
        omitted = deepcopy(self.common)
        manifest_identity = omitted["summary"].pop("manifest_identity")
        self.assertEqual(
            manifest_identity,
            identity.identity_hex(
                b"golden-board:manifest:v0\0",
                (canonical_manifest.serialize_manifest(omitted),),
            ),
        )

    def test_eight_family_manifests_are_exact_identity_bound_projections(self) -> None:
        damage_identity = self.common["summary"]["manifest_identity"]
        guarantees = (
            "all_declared_m2_sections_exact",
            "all_declared_m2_sections_exact",
            "m2_required_closure",
            "m2_required_closure",
            "m2_required_closure",
            "all_declared_m2_sections_exact",
            "m2_required_closure",
            "correct_or_explicit_failure",
        )
        for index, family in enumerate(self.families):
            self.assertEqual(family["schema"], "golden-board.m2-damage-family/v0")
            self.assertEqual(family["damage_manifest_identity"], damage_identity)
            self.assertEqual(family["family_id"], f"D{index}")
            self.assertEqual(family["guarantee_id"], guarantees[index])
            family_rows = [
                row for row in self.case_rows if row["family_id"] == f"D{index}"
            ]
            projected_rows = []
            for shard_row in family["shard_rows"]:
                name = (
                    f"damage-D{index}-cases-"
                    f"{shard_row['shard_ordinal']:04d}.json"
                )
                raw = dict(self.shard_items)[name]
                self.assertEqual(
                    shard_row["manifest_sha256"], sha256(raw).hexdigest()
                )
                shard = self.shards[name]
                self.assertEqual(shard["damage_manifest_identity"], damage_identity)
                self.assertEqual(shard["case_first"], len(projected_rows))
                projected_rows.extend(shard["case_rows"])
            self.assertEqual(projected_rows, family_rows)
            root_row = self.common["family_rows"][index]
            digest = sha256()
            digest.update(b"[")
            for row_index, row in enumerate(family_rows):
                if row_index:
                    digest.update(b",")
                digest.update(canonical_manifest.serialize_manifest(row)[:-1])
            digest.update(b"]")
            self.assertEqual(
                root_row["case_rows_sha256"], digest.hexdigest()
            )
            omitted = deepcopy(family)
            manifest_identity = omitted["summary"].pop("manifest_identity")
            self.assertEqual(
                manifest_identity,
                identity.identity_hex(
                    b"golden-board:manifest:v0\0",
                    (canonical_manifest.serialize_manifest(omitted),),
                ),
            )

    def test_seed_boundary_and_current_d7_operator_rows_are_exact(self) -> None:
        d3 = [row for row in self.case_rows if row["family_id"] == "D3"]
        seeds = [
            next(
                item["value"]
                for item in row["parameter_projection"]
                if item["id"] == "seed"
            )
            for row in d3
        ]
        self.assertEqual(
            seeds, list(range(5134751402299490304, 5134751402299490432))
        )
        d7 = [row for row in self.case_rows if row["family_id"] == "D7"]
        self.assertEqual(len(d7), 408)
        self.assertEqual(sum(row["operator"] == "d2-one-beyond" for row in d7), 256)
        self.assertEqual(sum(row["operator"] == "d3-one-beyond" for row in d7), 128)
        self.assertEqual(sum(row["operator"] == "route-conflicts" for row in d7), 1)
        self.assertEqual(
            self.common["boundary_kat_rows"],
            [
                {
                    "kat_id": "section-attempt-ceiling-plus-one",
                    "result_sha256": "4ad1468cd6cac6774b95e997d37c6fb420ff94cc0aa82595aeaa7b356440a68b",
                    "result": "pass",
                }
            ],
        )

    def test_writer_deep_validates_and_derives_exact_conditional_allowlist(self) -> None:
        values = generate_damage._artifact_map(self.damage_run)
        expected = {
            *generate_damage.ROOT_FILES,
            *(name for name, _ in self.damage_run.case_shards),
        }
        if self.damage_run.gate6_result == "pass":
            expected.add(generate_damage.INDEPENDENCE_FILE)
            proof = m2_independence.validate_independence_proof(
                values[generate_damage.INDEPENDENCE_FILE],
                (BASE / "candidate-manifest.json").read_bytes(),
                (BASE / "ownership-ledger.json").read_bytes(),
                self.damage_run.manifest,
                self.damage_run.family_manifests,
                tuple(raw for _, raw in self.damage_run.case_shards),
            )
            self.assertEqual(proof.result, "pass")
        else:
            self.assertNotIn(generate_damage.INDEPENDENCE_FILE, values)
        self.assertEqual(set(values), expected)

    def test_atomic_writer_reruns_unchanged_and_rejects_extra_types(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="golden-board-damage-writer-"
        ) as directory:
            output = Path(directory) / "damage"
            self.assertEqual(
                generate_damage.persist(output, self.damage_run), "created"
            )
            self.assertEqual(
                generate_damage.persist(output, self.damage_run), "unchanged"
            )
            extra = output / "extra"
            extra.mkdir()
            os.symlink(output / "damage-manifest.json", extra / "link")
            with self.assertRaisesRegex(
                generate_damage.DamageWriterError, "existing-type"
            ):
                generate_damage.persist(output, self.damage_run)

    def test_writer_rejects_run_scalar_or_filename_claims_not_bound_by_evidence(self) -> None:
        with self.assertRaisesRegex(
            generate_damage.DamageWriterError, "damage-result-binding"
        ):
            generate_damage._artifact_map(
                replace(
                    self.damage_run,
                    wrong_accept_count=self.damage_run.wrong_accept_count + 1,
                )
            )
        _, first_raw = self.damage_run.case_shards[0]
        renamed = (("renamed.json", first_raw), *self.damage_run.case_shards[1:])
        with self.assertRaisesRegex(
            generate_damage.DamageWriterError, "artifact-name"
        ):
            generate_damage._artifact_map(
                replace(self.damage_run, case_shards=renamed)
            )
        with self.assertRaisesRegex(
            generate_damage.DamageWriterError, "damage-result"
        ):
            generate_damage._artifact_map(
                replace(self.damage_run, gate7_result="pass")
            )

    def test_retained_gate6_failure_has_no_gate7_proof_when_available(self) -> None:
        losing = []
        for profile_id in generate_damage.PROFILE_IDS:
            base = ROOT / "artifacts" / "candidates" / profile_id
            if (base / "damage" / "damage-manifest.json").is_file():
                run = _retained_run(base)
                if run.gate6_result == "fail":
                    losing.append((base, run))
        if not losing:
            self.skipTest("no retained gate-6 losing fixture is present")
        for base, run in losing:
            with self.subTest(profile=base.name):
                values = generate_damage._artifact_map(run)
                self.assertNotIn(generate_damage.INDEPENDENCE_FILE, values)
                self.assertEqual(run.gate7_result, "not_evaluated")


class M2DamageV0FixtureCompatibility(unittest.TestCase):
    def test_archived_root_and_one_shard_remain_v0(self) -> None:
        damage = LEGACY_BASE / "damage"
        root_path = damage / "damage-manifest.json"
        if not root_path.is_file():
            self.skipTest("archived v0 damage fixture is absent")
        root = canonical_manifest.validate_canonical_manifest(
            root_path.read_bytes()
        )
        self.assertEqual(root["schema"], m2_damage.DAMAGE_SCHEMA)
        self.assertEqual(root["profile_id"], LEGACY_BASE.name)
        self.assertEqual(
            [row["case_count"] for row in root["family_rows"]],
            [16, 4, 256, 128, 1825, 21, 7300, 408],
        )
        family = canonical_manifest.validate_canonical_manifest(
            (damage / "damage-D7.json").read_bytes()
        )
        first = family["shard_rows"][0]
        shard_path = damage / (
            f"damage-D7-cases-{first['shard_ordinal']:04d}.json"
        )
        shard_raw = shard_path.read_bytes()
        shard = canonical_manifest.validate_canonical_manifest(shard_raw)
        self.assertEqual(family["schema"], "golden-board.m2-damage-family/v0")
        self.assertEqual(shard["schema"], "golden-board.m2-damage-cases/v0")
        self.assertEqual(first["manifest_sha256"], sha256(shard_raw).hexdigest())


if __name__ == "__main__":
    unittest.main()
