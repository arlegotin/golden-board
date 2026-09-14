from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from golden_board import (
    canonical_manifest,
    capacity,
    curriculum,
    identity,
    m2_carrier,
    m2_codec,
    m2_policy,
    m2_recipe,
    m2_slice,
)
from tools.m2 import generate_candidates


ROOT = Path(__file__).resolve().parents[2]
RETAINED_CANDIDATE_ROOT = ROOT / "artifacts/candidates"


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
    with tempfile.TemporaryDirectory(prefix="golden-board-carrier-") as directory:
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


class M2R3CarrierPrimitives(unittest.TestCase):
    def test_v7_unit_multiplier_table_is_independently_regenerated(self) -> None:
        table = m2_carrier.unit_multiplier_table()
        self.assertEqual(len(table), 256)
        self.assertEqual((table[0], table[255]), (0, 0))
        self.assertEqual(sum(value != 0 for value in table), 236)
        self.assertEqual(len(set(table) - {0}), 24)
        self.assertEqual(max(table), 217)
        self.assertEqual(table[1_696 // 8], 15)
        self.assertEqual(
            sha256(table).hexdigest(),
            "835717bf400c597a3a9e1b59747f23d93047b6cfab462756fa07d96c5f3eba3f",
        )

    def test_v7_two_stage_mapping_known_answer_and_exact_inverse(self) -> None:
        profile = m2_codec.r3_candidate_profile(
            protected_units=1_664,
            encoded_transport_bytes=1_664 * 216,
        )
        mapping = m2_carrier.mapping_parameters(profile, 1_952, 128, 1_664)
        self.assertEqual(
            mapping,
            {
                "id": "affine-slot-then-interior-v1",
                "interior_side": 1_696,
                "population": 2_876_416,
                "unit_population": 1_664,
                "unit_multiplier": 15,
                "unit_inverse_multiplier": 111,
                "cell_multiplier": 3_391,
                "offset": 316_417,
                "cell_inverse_multiplier": 2_873_023,
            },
        )
        for unit_id, bit_offset in (
            (1, 0),
            (1, 1_727),
            (1_664, 0),
            (1_664, 1_727),
        ):
            with self.subTest(unit_id=unit_id, bit_offset=bit_offset):
                physical = m2_carrier.map_unit_bit(mapping, unit_id, bit_offset)
                self.assertEqual(
                    m2_carrier.invert_interior_cell(mapping, physical),
                    (unit_id, bit_offset),
                )
        first_tail = (
            mapping["cell_multiplier"] * (1_664 * 1_728) + mapping["offset"]
        ) % mapping["population"]
        self.assertIsNone(m2_carrier.invert_interior_cell(mapping, first_tail))
        for bad_unit, bad_bit in ((0, 0), (1_665, 0), (1, -1), (1, 1_728)):
            with self.subTest(bad_unit=bad_unit, bad_bit=bad_bit):
                with self.assertRaises(m2_carrier.CarrierError):
                    m2_carrier.map_unit_bit(mapping, bad_unit, bad_bit)

    def test_v7_unit_ids_are_group_contiguous_and_lanes_are_identical(self) -> None:
        profile = m2_codec.r3_candidate_profile()
        sections = (
            m2_carrier._Section(
                1,
                1,
                128,
                1,
                (),
                b"inventory",
                "section:0000000001",
                physical_replica_count=5,
                section_version=1,
            ),
            m2_carrier._Section(
                4,
                3,
                129,
                1,
                (),
                b"content",
                "section:0000000004",
                physical_replica_count=2,
            ),
        )
        units, envelopes, charges = m2_carrier._encode_units(profile, sections)
        self.assertEqual([unit.unit_id for unit in units], list(range(1, 8)))
        self.assertEqual(
            [
                (
                    unit.section_id,
                    unit.semantic_copy_id,
                    unit.fragment_index,
                    unit.replica_index,
                    unit.physical_replica_count,
                )
                for unit in units
            ],
            [(1, 0, 0, lane, 5) for lane in range(5)]
            + [(4, 0, 0, lane, 2) for lane in range(2)],
        )
        self.assertEqual(len({unit.encoded for unit in units[:5]}), 1)
        self.assertEqual(len({unit.encoded for unit in units[5:]}), 1)
        self.assertEqual(set(envelopes), {1, 4})
        self.assertEqual(set(charges), {1, 4})


class M2R3CarrierPreflight(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile_raw = _read("spec/profile-policy-v1.toml")
        cls.limits_raw = _read("spec/profile-limits-v1.toml")
        cls.damage_raw = _read("spec/damage-policy-v1.toml")
        cls.bootstrap_raw = _read("spec/bootstrap-v1.md")
        cls.route_raw = _read("spec/route-data-v1.json")
        cls.base_profile_raw = _read("spec/profile-policy-v0.toml")
        cls.compiled = m2_slice.compile_slice_v0(
            _read("studies/m2/slice-v0.json"),
            _read("conformance/content-v0.json"),
            _read("conformance/chess-v0.json"),
            _read("reports/game-set-v0.bin"),
            _read("spec/content-v0.md"),
            _read("spec/constants-v0.toml"),
            _read("spec/curriculum-v0.toml"),
        )
        blueprint = curriculum.load_blueprint(_read("spec/curriculum-v0.toml"))
        cls.inputs = capacity.derive_capacity_inputs(cls.compiled, blueprint)
        base_policy = m2_policy.load_profile_policy(cls.base_profile_raw)
        cls.envelope = capacity.derive_capacity_envelope(
            cls.inputs, base_policy.capacity_policy
        )
        cls.profile = m2_codec.r3_candidate_profile(
            protected_units=1_841,
            encoded_transport_bytes=397_656,
        )
        cls.package = m2_recipe.build_r3_recipe_package()
        route = canonical_manifest.validate_canonical_manifest(cls.route_raw)
        generated = route["generated"]

        def route_receipt(implementation_id: str) -> bytes:
            return canonical_manifest.serialize_manifest(
                {
                    "implementation_id": implementation_id,
                    "recipient_package_sha256": generated[
                        "recipient_package_sha256"
                    ],
                    "reproduction_projection_sha256": generated[
                        "reproduction_projection_sha256"
                    ],
                    "route_data_template_sha256": generated[
                        "route_data_template_sha256"
                    ],
                    "route_sha256": generated["route_sha256"],
                    "schema": "golden-board.m2-r3-route-reproduction/v1",
                }
            )

        cls.proof = m2_carrier.R3CarrierOwnerProof(
            _read("spec/m2-r3-owner-promotion-v1.toml"),
            _read("conformance/m2-r3-owner-v1.json"),
            cls.base_profile_raw,
            route_receipt("python"),
            route_receipt("rust"),
            m2_policy.render_r3_limits_reproduction_receipt(
                "python", cls.limits_raw, cls.route_raw
            ),
            m2_policy.render_r3_limits_reproduction_receipt(
                "rust", cls.limits_raw, cls.route_raw
            ),
        )
        cls.outcome = m2_carrier.build_p6_outcome(
            cls.profile,
            cls.profile_raw,
            cls.limits_raw,
            cls.damage_raw,
            cls.bootstrap_raw,
            cls.compiled,
            cls.inputs,
            cls.envelope,
            cls.route_raw,
            cls.package,
            r3_owner_proof=cls.proof,
        )
        if cls.outcome.manifestation is None:
            raise RuntimeError("unexpected v7 P6 setup outcome")
        cls.manifestation = cls.outcome.manifestation

    def _preflight(
        self,
        *,
        proof: m2_carrier.R3CarrierOwnerProof | None = None,
        route_raw: bytes | None = None,
        package: bytes | None = None,
    ) -> m2_carrier.R3CarrierPreflight:
        return m2_carrier.preflight_r3_carrier(
            self.profile,
            self.profile_raw,
            self.limits_raw,
            self.damage_raw,
            self.bootstrap_raw,
            self.compiled,
            self.inputs,
            self.envelope,
            self.route_raw if route_raw is None else route_raw,
            self.package if package is None else package,
            r3_owner_proof=self.proof if proof is None else proof,
        )

    def test_strict_raw_owner_proof_and_exact_preflight(self) -> None:
        self.assertEqual(
            self._preflight(),
            m2_carrier.R3CarrierPreflight(
                "eh72-hier-r5-r2-r1-crc32c-v0",
                2_040,
                128,
                1_841,
                3_462_432,
                "a3a6c9fc8a67d5cc36d0d75f74464fbeac2819d7b6bd8048206aa19d6cbd7922",
            ),
        )
        for field in self.proof.__dataclass_fields__:
            with self.subTest(field=field):
                damaged = replace(
                    self.proof,
                    **{field: getattr(self.proof, field) + b" "},
                )
                with self.assertRaises(m2_carrier.CarrierError) as caught:
                    self._preflight(proof=damaged)
                self.assertEqual(caught.exception.reason, "owner-admission")
        with self.assertRaises(m2_carrier.CarrierError) as caught:
            self._preflight(proof=replace(self.proof, owner_fixture_raw="bad"))
        self.assertEqual(caught.exception.reason, "r3-owner-proof")

    def test_exact_package_route_and_lower_bound_bindings(self) -> None:
        _, route_parts, _, headrooms = m2_carrier._shell_blueprint(
            self.route_raw, self.profile, self.package
        )
        self.assertEqual(tuple(len(raw) * 8 for raw in route_parts), (232_728,) * 4)
        self.assertEqual(headrooms, (11_637, 11_637, 11_636, 11_636))
        self.assertEqual(
            sha256(b"".join(route_parts)).hexdigest(),
            "a3a6c9fc8a67d5cc36d0d75f74464fbeac2819d7b6bd8048206aa19d6cbd7922",
        )
        semantic_raw = m2_carrier.render_semantic_envelope(
            self.compiled, self.inputs, self.envelope
        )
        semantic = canonical_manifest.validate_canonical_manifest(semantic_raw)
        lower = m2_carrier._lower_bound_value(
            self.profile,
            self.profile_raw,
            self.limits_raw,
            semantic_raw,
            semantic,
            self.inputs,
            route_parts,
            2_048,
        )
        self.assertEqual(
            (
                lower["protected_unit_count"],
                lower["protected_cells"],
                lower["route_prefix_cells"],
                lower["lower_bound_cells"],
                lower["hard_ceiling_cells"],
                lower["candidate_favorable_omissions"],
                lower["result"],
            ),
            (
                1_465,
                2_531_520,
                930_912,
                3_462_432,
                4_194_304,
                ["shell-headroom", "alignment-pad", "load-probe"],
                "lower-bound-does-not-eliminate",
            ),
        )
        with self.assertRaises(m2_carrier.CarrierError):
            self._preflight(package=self.package[:-1])
        route = canonical_manifest.validate_canonical_manifest(self.route_raw)
        route["generated"]["route_prefix_sha256_by_sector"][0] = "0" * 64
        with self.assertRaises(m2_carrier.CarrierError) as caught:
            m2_carrier._shell_blueprint(
                canonical_manifest.serialize_manifest(route),
                self.profile,
                self.package,
            )
        self.assertEqual(caught.exception.reason, "route-owner")

    def test_realism_uses_exact_inherited_v0_boundary(self) -> None:
        count = 1_784 * 1_784
        ones = count // 4
        scopes = []
        for scope_id in (
            "shell",
            "real-protected",
            "capacity-probe",
            "reserve-probe",
            "load-probe",
            "fixed-pad",
            "complete-interior",
        ):
            scope_count = count if scope_id == "complete-interior" else 0
            scope_ones = ones if scope_id == "complete-interior" else 0
            scopes.append(
                {
                    "scope_id": scope_id,
                    "cell_count": scope_count,
                    "zero_count": scope_count - scope_ones,
                    "one_count": scope_ones,
                    "one_density_ppm": (
                        0
                        if scope_count == 0
                        else scope_ones * 1_000_000 // scope_count
                    ),
                }
            )
        density = canonical_manifest.serialize_manifest(
            {
                "schema": m2_carrier.DENSITY_SCHEMA,
                "profile_id": self.profile.profile_id,
                "carrier_sha256": "0" * 64,
                "scope_rows": scopes,
                "interior_regularity": {
                    "longest_horizontal_equal_run": 446,
                    "longest_vertical_equal_run": 446,
                    "tile_one_count_min": 128,
                    "tile_one_count_max": 896,
                    "repeated_row_count": 55,
                    "repeated_column_count": 55,
                },
            }
        )
        self.assertEqual(
            m2_carrier.evaluate_realism(
                density, self.base_profile_raw
            ).result,
            "pass",
        )
        with self.assertRaises(m2_carrier.CarrierError) as caught:
            m2_carrier.evaluate_realism(density, self.profile_raw)
        self.assertEqual(caught.exception.reason, "realism-input")

    def test_complete_v7_gate_one_through_five_matches_rust(self) -> None:
        outcome = self.outcome
        self.assertEqual(
            (outcome.gate5_result, outcome.failure_reason), ("pass", None)
        )
        self.assertIsNotNone(outcome.manifestation)
        manifestation = self.manifestation
        artifacts = (
            manifestation.semantic_envelope,
            manifestation.carrier,
            manifestation.candidate_manifest,
            manifestation.ownership_ledger,
            manifestation.capacity_ledger,
            manifestation.density_ledger,
        )
        self.assertEqual(
            tuple(map(len, artifacts)),
            (376_036, 520_204, 675_827, 478_010, 673_935, 1_157),
        )
        self.assertEqual(
            tuple(sha256(raw).hexdigest() for raw in artifacts),
            (
                "f81e29b04b307b147aec1c2602933c778e1c9198084e5d5c8e4e29cad1bdb0fd",
                "c6309da5f199a237b8fc79292a5135581ad0f9b517fbe9516770ebaf084d49b0",
                "38839aa28561ff2bec0997a80d8dc938e876526c25f40e23b6a78844f8fc1d86",
                "fe82dc8119d77a855e7227dea95a673e3fb2ffb5a9c513cf31a169ea53ee5d12",
                "a6e4a9b5e6a78a3ecf7d42ebbe75b0fa84258b6931183e37109dc927d0f9d2c6",
                "6e931df836f063e1de96ee73514ca91b4ddd59071bc8338bdd5a79244fcbee61",
            ),
        )
        candidate = canonical_manifest.validate_canonical_manifest(
            manifestation.candidate_manifest
        )
        self.assertEqual(
            candidate["manifest_identity"],
            "d783917d34bc6fb472ea7e20c989562092707c516195019434e01f2bc6f68681",
        )
        self.assertEqual(
            [
                row["section_id"]
                for row in candidate["section_rows"]
                if row["copy_class"] == "required-spine"
            ],
            [1, 2, 3, 16],
        )
        self.assertEqual(
            (
                candidate["side"],
                candidate["shell_width"],
                candidate["ledger"]["protected_unit_count"],
                candidate["ledger"]["worst_case_work_units"],
                candidate["ledger"]["scratch_bytes"],
            ),
            (2_040, 128, 1_841, 4_484_682_504, 6_163),
        )
        realism = m2_carrier.evaluate_realism(
            manifestation.density_ledger, self.base_profile_raw
        )
        self.assertEqual(
            (
                realism.result,
                realism.complete_interior_one_count,
                realism.longest_horizontal_equal_run,
                realism.longest_vertical_equal_run,
                realism.tile_one_count_min,
                realism.tile_one_count_max,
                realism.repeated_row_count,
                realism.repeated_column_count,
            ),
            ("pass", 1_260_060, 31, 29, 249, 499, 0, 0),
        )
        m2_carrier.validate_manifestation(
            manifestation,
            self.profile,
            self.profile_raw,
            self.limits_raw,
            self.damage_raw,
            self.bootstrap_raw,
            self.compiled,
            self.inputs,
            self.envelope,
            self.route_raw,
            self.package,
            r3_owner_proof=self.proof,
        )

    def test_v7_cross_language_atomic_writer_is_closed(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="golden-board-r3-writer-", dir="/tmp"
        ) as directory:
            root = Path(directory)
            rust_directory = root / "rust-emission"
            rust_values = generate_candidates._emit_r3_rust(rust_directory)
            generate_candidates.compare_r3_rust_emission(
                rust_values, self.manifestation
            )
            changed = dict(rust_values)
            changed["candidate-manifest.json"] = changed[
                "candidate-manifest.json"
            ][:-1]
            with self.assertRaisesRegex(
                generate_candidates.CandidateWriterError,
                "r3-cross-language-mismatch",
            ):
                generate_candidates.compare_r3_rust_emission(
                    changed, self.manifestation
                )
            extra_rust = rust_directory / "extra"
            extra_rust.write_bytes(b"not allowlisted")
            with self.assertRaisesRegex(
                generate_candidates.CandidateWriterError,
                "r3-rust-allowlist",
            ):
                generate_candidates._validate_r3_rust_emission(
                    rust_directory
                )
            extra_rust.unlink()

            output = root / "candidates"
            r2_damage_target = root / "r2-damage-target"
            r2_damage_target.mkdir()
            marker = r2_damage_target / "historical"
            marker.write_bytes(b"unchanged R2 damage")
            r2_profile = output / generate_candidates.P1
            r2_profile.mkdir(parents=True)
            (r2_profile / "damage").symlink_to(
                r2_damage_target, target_is_directory=True
            )
            self.assertEqual(
                generate_candidates.persist_r3_candidate(
                    output, self.manifestation
                ),
                "created",
            )
            self.assertEqual(marker.read_bytes(), b"unchanged R2 damage")
            target = output / generate_candidates.P7
            self.assertEqual(
                {path.name for path in target.iterdir()},
                set(generate_candidates.R3_ALLOWLIST),
            )
            self.assertEqual(
                generate_candidates.persist_r3_candidate(
                    output, self.manifestation
                ),
                "unchanged",
            )
            self.assertEqual(
                generate_candidates.verify_r3_candidate(
                    output, self.manifestation
                ),
                "verified",
            )
            damage = target / "damage"
            damage.mkdir()
            (damage / "downstream-evidence").write_bytes(b"not claimed by p6")
            self.assertEqual(
                generate_candidates.verify_r3_candidate(
                    output, self.manifestation
                ),
                "verified",
            )

            carrier_path = target / "carrier.obs-bits"
            carrier_raw = carrier_path.read_bytes()
            carrier_path.write_bytes(carrier_raw[:-1])
            with self.assertRaisesRegex(
                generate_candidates.CandidateWriterError,
                "r3-existing-mismatch",
            ):
                generate_candidates.persist_r3_candidate(
                    output, self.manifestation
                )
            carrier_path.write_bytes(carrier_raw)
            extra = target / "extra"
            extra.mkdir()
            with self.assertRaisesRegex(
                generate_candidates.CandidateWriterError,
                "r3-existing-allowlist",
            ):
                generate_candidates.persist_r3_candidate(
                    output, self.manifestation
                )
            extra.rmdir()
            density_path = target / "density-ledger.json"
            density_raw = density_path.read_bytes()
            density_path.unlink()
            density_path.symlink_to(marker)
            with self.assertRaisesRegex(
                generate_candidates.CandidateWriterError,
                "r3-existing-mismatch",
            ):
                generate_candidates.persist_r3_candidate(
                    output, self.manifestation
                )
            density_path.unlink()
            density_path.write_bytes(density_raw)

            symlink_root = root / "symlink-root"
            symlink_root.symlink_to(output, target_is_directory=True)
            with self.assertRaisesRegex(
                generate_candidates.CandidateWriterError, "output-type"
            ):
                generate_candidates.persist_r3_candidate(
                    symlink_root, self.manifestation
                )
            linked_output = root / "linked-output"
            linked_output.mkdir()
            outside = root / "outside"
            outside.mkdir()
            (linked_output / generate_candidates.P7).symlink_to(
                outside, target_is_directory=True
            )
            with self.assertRaisesRegex(
                generate_candidates.CandidateWriterError,
                "r3-existing-target",
            ):
                generate_candidates.persist_r3_candidate(
                    linked_output, self.manifestation
                )

            atomic_output = root / "atomic-output"
            atomic_output.mkdir()
            with mock.patch.object(
                generate_candidates.os,
                "replace",
                side_effect=OSError("injected write failure"),
            ):
                with self.assertRaisesRegex(
                    generate_candidates.CandidateWriterError,
                    "r3-atomic-write",
                ):
                    generate_candidates.persist_r3_candidate(
                        atomic_output, self.manifestation
                    )
            self.assertEqual(list(atomic_output.iterdir()), [])


class M2R3CandidateAdmission(unittest.TestCase):
    @unittest.skipUnless(
        RETAINED_CANDIDATE_ROOT.is_dir(),
        "retained ignored candidates are absent in a clean execution snapshot",
    )
    def test_canonical_regeneration_requires_archive_and_absent_target(self) -> None:
        output = RETAINED_CANDIDATE_ROOT
        target = output / generate_candidates.P7
        if target.exists() or target.is_symlink():
            generate_candidates._admit_r3_canonical_context(
                output, regeneration=False
            )
            with self.assertRaisesRegex(
                generate_candidates.CandidateWriterError,
                "r3-regeneration-precondition",
            ):
                generate_candidates._admit_r3_canonical_context(
                    output, regeneration=True
                )
        else:
            generate_candidates._admit_r3_canonical_context(
                output, regeneration=True
            )
            with self.assertRaisesRegex(
                generate_candidates.CandidateWriterError,
                "r3-existing-target",
            ):
                generate_candidates._admit_r3_canonical_context(
                    output, regeneration=False
                )
        with tempfile.TemporaryDirectory(
            prefix="golden-board-r3-noncanonical-", dir="/tmp"
        ) as directory:
            with self.assertRaisesRegex(
                generate_candidates.CandidateWriterError,
                "r3-canonical-output",
            ):
                generate_candidates._admit_r3_canonical_context(
                    Path(directory), regeneration=True
                )
        validators = (
            "validate_r3_pre_clarification_archive",
            "validate_r3_pre_damage_schema_archive",
            "validate_r3_pre_independence_witness_archive",
            "validate_r3_pre_gate6_convergence_archive",
        )
        for validator in validators:
            with self.subTest(validator=validator), mock.patch.object(
                generate_candidates.m2_policy,
                validator,
                side_effect=m2_policy.PolicyError("mutant"),
            ):
                with self.assertRaisesRegex(
                    generate_candidates.CandidateWriterError,
                    "r3-archive:mutant",
                ):
                    generate_candidates._admit_r3_canonical_context(
                        output, regeneration=not target.exists()
                    )

    def test_rust_emitter_ignores_benign_stderr_only_after_success(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="golden-board-r3-stderr-", dir="/tmp"
        ) as directory:
            output = Path(directory) / "emission"
            calls = iter(
                (
                    subprocess.CompletedProcess(
                        (), 0, stdout="/tmp/rustc\n", stderr=""
                    ),
                    subprocess.CompletedProcess(
                        (), 0, stdout="rustc 1.97.1 (test)\n", stderr=""
                    ),
                    subprocess.CompletedProcess(
                        (),
                        0,
                        stdout=f"{output}\n",
                        stderr="warning: bounded benign warning\n",
                    ),
                )
            )
            expected = {name: b"x" for name in generate_candidates.R3_ALLOWLIST}
            with (
                mock.patch.object(
                    generate_candidates.subprocess,
                    "run",
                    side_effect=lambda *args, **kwargs: next(calls),
                ),
                mock.patch.object(
                    generate_candidates,
                    "_validate_r3_rust_emission",
                    return_value=expected,
                ),
            ):
                self.assertEqual(
                    generate_candidates._emit_r3_rust(output), expected
                )


class M2Carrier(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile_raw = _read("spec/profile-policy-v0.toml")
        cls.limits_raw = _read("spec/profile-limits-v0.toml")
        cls.damage_raw = _read("spec/damage-policy-v0.toml")
        cls.bootstrap_raw = _read("spec/bootstrap-v0.md")
        cls.route_raw = _read("spec/route-data-v0.json")
        cls.compiled = m2_slice.compile_slice_v0(
            _read("studies/m2/slice-v0.json"),
            _read("conformance/content-v0.json"),
            _read("conformance/chess-v0.json"),
            _read("reports/game-set-v0.bin"),
            _read("spec/content-v0.md"),
            _read("spec/constants-v0.toml"),
            _read("spec/curriculum-v0.toml"),
        )
        blueprint = curriculum.load_blueprint(_read("spec/curriculum-v0.toml"))
        cls.inputs = capacity.derive_capacity_inputs(cls.compiled, blueprint)
        policy = m2_policy.load_profile_policy(cls.profile_raw)
        cls.envelope = capacity.derive_capacity_envelope(
            cls.inputs, policy.capacity_policy
        )
        profiles = m2_codec.load_candidate_profiles(
            cls.profile_raw, cls.limits_raw
        )
        cls.profile_one = profiles[0]
        cls.profile_three = profiles[2]
        cls.package_one = _emit(1)
        cls.package_three = _emit(3)
        common = (
            cls.profile_raw,
            cls.limits_raw,
            cls.damage_raw,
            cls.bootstrap_raw,
            cls.compiled,
            cls.inputs,
            cls.envelope,
            cls.route_raw,
        )
        cls.outcome_one = m2_carrier.build_p6_outcome(
            cls.profile_one, *common, cls.package_one
        )
        cls.outcome_three = m2_carrier.build_p6_outcome(
            cls.profile_three, *common, cls.package_three
        )
        if (
            cls.outcome_one.manifestation is None
            or cls.outcome_three.manifestation is None
            or cls.outcome_one.elimination_bound is not None
            or cls.outcome_three.elimination_bound is not None
        ):
            raise RuntimeError("unexpected P6 setup outcome")
        cls.manifestation_one = cls.outcome_one.manifestation
        cls.manifestation_three = cls.outcome_three.manifestation

    def test_semantic_envelope_and_cross_language_artifact_identities(self) -> None:
        manifestation_one = self.manifestation_one
        manifestation_three = self.manifestation_three
        self.assertEqual(len(manifestation_one.semantic_envelope), 376_036)
        self.assertEqual(
            manifestation_one.semantic_envelope,
            manifestation_three.semantic_envelope,
        )
        self.assertEqual(
            sha256(manifestation_one.semantic_envelope).hexdigest(),
            "f81e29b04b307b147aec1c2602933c778e1c9198084e5d5c8e4e29cad1bdb0fd",
        )
        self.assertEqual(
            (
                sha256(manifestation_one.carrier).hexdigest(),
                sha256(manifestation_one.candidate_manifest).hexdigest(),
                sha256(manifestation_one.ownership_ledger).hexdigest(),
                sha256(manifestation_one.capacity_ledger).hexdigest(),
                sha256(manifestation_one.density_ledger).hexdigest(),
            ),
            (
                "6e13d469877971ca30818d11084723f7b36a3560bf404de3904cb6a1f47f0513",
                "75d8b6a518315a707d6c1964001b4482c3913be8c3ba79bb43781e33816e6bbb",
                "bb1b1def3afa01adc47b612fae3b31d9620aa0f70484ae3e69ce75e7fed7f3bc",
                "6cc17f016052bfc56265e64262f0800236e4a2bdf76ea249724eced38eb18480",
                "c1c4c3ce92aac7f16e477158b4b826c7be13e4a9368c515bb3a94c0e99c078ab",
            ),
        )
        self.assertEqual(
            (
                sha256(manifestation_three.carrier).hexdigest(),
                sha256(manifestation_three.candidate_manifest).hexdigest(),
                sha256(manifestation_three.ownership_ledger).hexdigest(),
                sha256(manifestation_three.capacity_ledger).hexdigest(),
                sha256(manifestation_three.density_ledger).hexdigest(),
            ),
            (
                "40405cd5cafe41653d1bc75e082ccf3f4458403426e154d3e2aeba2f1c58c1f8",
                "1e1bd5551ee357f3f4b809afba480b379c41b7365b971493db8f3bc2e415168b",
                "d72137c290c35d2fa0da6d09848fdb511ab7f3fe2db1a325a85d16292084b872",
                "a92436acab9a9b80ff3a0a09c68103e18f04ccaf7467743449d1b45644ee99c7",
                "c7d9558d241acc735f01602bec938c7c05eb6ecb963ede840ca021e3a4313016",
            ),
        )

    def test_profile_one_complete_manifestation_reconciles(self) -> None:
        manifestation = self.manifestation_one
        candidate = canonical_manifest.validate_canonical_manifest(
            manifestation.candidate_manifest
        )
        ownership = canonical_manifest.validate_canonical_manifest(
            manifestation.ownership_ledger
        )
        capacity_ledger = canonical_manifest.validate_canonical_manifest(
            manifestation.capacity_ledger
        )
        semantic = canonical_manifest.validate_canonical_manifest(
            manifestation.semantic_envelope
        )
        self.assertEqual((candidate["side"], candidate["shell_width"]), (1952, 128))
        self.assertEqual(
            (len(manifestation.carrier), int.from_bytes(manifestation.carrier[:4], "big")),
            (476_292, 1952 * 1952),
        )
        self.assertEqual(
            (len(semantic["slot_rows"]), len(semantic["capacity_section_rows"])),
            (4_174, 53),
        )
        self.assertEqual(
            [row[0] for row in semantic["capacity_section_rows"]],
            list(range(211, 264)),
        )
        section_rows = candidate["section_rows"]
        self.assertEqual(
            (len(section_rows), [row["section_id"] for row in section_rows[-4:]]),
            (137, [264, 265, 266, 267]),
        )
        self.assertEqual(
            (
                section_rows[0]["logical_payload_bytes"],
                section_rows[-4]["logical_payload_bytes"],
                tuple(row["logical_payload_bytes"] for row in section_rows[-3:]),
                section_rows[-1]["logical_payload_bytes"],
                section_rows[-1]["fragment_count"],
            ),
            (3_060, 7_141, (16_384, 16_384, 12_381), 12_381, 79),
        )
        self.assertEqual(len(candidate["unit_rows"]), 1_664)
        self.assertEqual(
            [
                (row["semantic_copy_id"], row["section_id"], row["fragment_index"])
                for row in candidate["unit_rows"]
            ],
            sorted(
                (
                    row["semantic_copy_id"],
                    row["section_id"],
                    row["fragment_index"],
                )
                for row in candidate["unit_rows"]
            ),
        )
        self.assertEqual(
            [row["physical_unit_id"] for row in candidate["unit_rows"]],
            list(range(1, 1_665)),
        )
        mapping = candidate["mapping"]
        for logical in (0, 1, 1_727, mapping["population"] - 1):
            physical = (
                mapping["multiplier"] * logical + mapping["offset"]
            ) % mapping["population"]
            recovered = (
                mapping["inverse_multiplier"]
                * (physical - mapping["offset"])
            ) % mapping["population"]
            self.assertEqual(recovered, logical)
        self.assertEqual(
            (
                candidate["ledger"]["load_probe_cells"],
                candidate["ledger"]["interior_fixed_pad_cells"],
                candidate["ledger"]["unused_cells"],
            ),
            (499_392, 1_024, 0),
        )
        self.assertEqual(ownership["mapping"], candidate["mapping"])
        self.assertEqual(ownership["shell_rows"], candidate["shell_rows"])
        self.assertEqual(ownership["unit_rows"], candidate["unit_rows"])
        self.assertEqual(
            ownership["interior_fixed_pad"]["fill_order"],
            "unoccupied-interior-cells-in-physical-row-major-order",
        )
        self.assertEqual(capacity_ledger["section_rows"], section_rows)
        self.assertEqual(capacity_ledger["unit_rows"], candidate["unit_rows"])
        self.assertEqual(
            candidate["ownership_sha256"],
            sha256(manifestation.ownership_ledger).hexdigest(),
        )
        omitted = dict(candidate)
        manifest_identity = omitted.pop("manifest_identity")
        self.assertEqual(
            manifest_identity,
            identity.identity_hex(
                b"golden-board:manifest:v0\0",
                (canonical_manifest.serialize_manifest(omitted),),
            ),
        )
        self.assertEqual(
            manifest_identity,
            "0627029a418877e9331651d881da5b587e657f69f03fe08e01a641b9248c7cba",
        )
        self.assertFalse(any(key.startswith("damage") for key in candidate))

    def test_profile_one_passes_the_unchanged_realism_gate(self) -> None:
        evaluation = m2_carrier.evaluate_realism(
            self.manifestation_one.density_ledger, self.profile_raw
        )
        self.assertEqual(evaluation.result, "pass")
        self.assertEqual(evaluation.failure_reasons, ())
        self.assertEqual(
            (
                evaluation.complete_interior_cell_count,
                evaluation.complete_interior_one_count,
                evaluation.complete_interior_one_density_ppm,
                evaluation.tile_one_count_min,
                evaluation.tile_one_count_max,
                evaluation.longest_horizontal_equal_run,
                evaluation.longest_vertical_equal_run,
                evaluation.repeated_row_count,
                evaluation.repeated_column_count,
            ),
            (2_876_416, 1_165_423, 405_164, 165, 504, 45, 63, 0, 0),
        )
        outcome = self.outcome_one
        self.assertEqual(
            (outcome.gate5_result, outcome.failure_reason, outcome.elimination_bound),
            ("pass", None, None),
        )
        self.assertIsNotNone(outcome.manifestation)

    def test_profile_three_complete_manifestation_passes(self) -> None:
        manifestation = self.manifestation_three
        candidate = canonical_manifest.validate_canonical_manifest(
            manifestation.candidate_manifest
        )
        self.assertEqual((candidate["side"], candidate["shell_width"]), (2032, 128))
        self.assertEqual(
            (len(manifestation.carrier), int.from_bytes(manifestation.carrier[:4], "big")),
            (516_132, 2032 * 2032),
        )
        self.assertEqual(len(candidate["section_rows"]), 135)
        self.assertEqual(
            [row["section_id"] for row in candidate["section_rows"][-2:]],
            [264, 265],
        )
        self.assertEqual(
            (
                candidate["section_rows"][0]["logical_payload_bytes"],
                candidate["section_rows"][-2]["logical_payload_bytes"],
                candidate["section_rows"][-1]["logical_payload_bytes"],
                candidate["section_rows"][-1]["fragment_count"],
            ),
            (3_020, 7_141, 606, 4),
        )
        self.assertEqual(len(candidate["unit_rows"]), 1_825)
        self.assertEqual(
            [
                (row["semantic_copy_id"], row["section_id"], row["fragment_index"])
                for row in candidate["unit_rows"]
            ],
            sorted(
                (
                    row["semantic_copy_id"],
                    row["section_id"],
                    row["fragment_index"],
                )
                for row in candidate["unit_rows"]
            ),
        )
        self.assertEqual(
            [row["physical_unit_id"] for row in candidate["unit_rows"]],
            list(range(1, 1_826)),
        )
        self.assertEqual(
            (
                candidate["ledger"]["load_probe_cells"],
                candidate["ledger"]["interior_fixed_pad_cells"],
                candidate["ledger"]["unused_cells"],
            ),
            (6_912, 576, 0),
        )
        self.assertEqual(
            candidate["manifest_identity"],
            "758ca1a16fdec033ee30a4ed9fef2853d41a433d9e2e2a56cd466834f7582ff9",
        )
        evaluation = m2_carrier.evaluate_realism(
            manifestation.density_ledger, self.profile_raw
        )
        self.assertEqual(evaluation.result, "pass")
        self.assertEqual(evaluation.failure_reasons, ())
        self.assertEqual(
            (
                evaluation.complete_interior_cell_count,
                evaluation.complete_interior_one_count,
                evaluation.complete_interior_one_density_ppm,
                evaluation.tile_one_count_min,
                evaluation.tile_one_count_max,
                evaluation.longest_horizontal_equal_run,
                evaluation.longest_vertical_equal_run,
                evaluation.repeated_row_count,
                evaluation.repeated_column_count,
            ),
            (3_154_176, 1_281_920, 406_419, 158, 497, 48, 66, 0, 0),
        )
        outcome = self.outcome_three
        self.assertEqual(
            (outcome.gate5_result, outcome.failure_reason, outcome.elimination_bound),
            ("pass", None, None),
        )
        self.assertIsNotNone(outcome.manifestation)

    def test_non_survivors_never_reach_p6_and_owners_fail_closed(self) -> None:
        profiles = m2_codec.load_candidate_profiles(self.profile_raw, self.limits_raw)
        for profile in (profiles[1], profiles[3], profiles[4], profiles[5]):
            with self.subTest(profile=profile.profile_id):
                with self.assertRaisesRegex(m2_carrier.CarrierError, "gate-two-survivor"):
                    m2_carrier.build_p6_outcome(
                        profile,
                        self.profile_raw,
                        self.limits_raw,
                        self.damage_raw,
                        self.bootstrap_raw,
                        self.compiled,
                        self.inputs,
                        self.envelope,
                        self.route_raw,
                        b"",
                    )
        with self.assertRaisesRegex(m2_carrier.CarrierError, "owner-admission"):
            m2_carrier.build_manifestation(
                self.profile_one,
                self.profile_raw[:-1] + b" ",
                self.limits_raw,
                self.damage_raw,
                self.bootstrap_raw,
                self.compiled,
                self.inputs,
                self.envelope,
                self.route_raw,
                self.package_one,
            )

    def test_payload_boundary_and_bounded_exact_validators(self) -> None:
        self.assertGreater(
            m2_carrier._section_charge(16_384, 0, 1, 1).common_blocks, 0
        )
        with self.assertRaisesRegex(m2_carrier.CarrierError, "section-payload"):
            m2_carrier._section_charge(16_385, 0, 1, 1)
        semantic = canonical_manifest.validate_canonical_manifest(
            self.manifestation_one.semantic_envelope
        )
        load_count, fragments, payloads, pad = m2_carrier._layout_for_geometry(
            self.profile_one, 1952, 128, self.inputs, semantic
        )
        self.assertEqual(
            (load_count, fragments, payloads, pad),
            (3, (105, 105, 79), (16_384, 16_384, 12_381), 1_024),
        )
        with self.assertRaisesRegex(m2_carrier.CarrierError, "load-fixed-point"):
            m2_carrier._layout_for_geometry(
                self.profile_one, 1_024, 128, self.inputs, semantic
            )
        overlong = dict(semantic)
        overlong_rows = [list(row) for row in semantic["capacity_section_rows"]]
        overlong_rows[0][7] = 16_385
        overlong["capacity_section_rows"] = overlong_rows
        with self.assertRaisesRegex(m2_carrier.CarrierError, "section-payload"):
            m2_carrier._layout_for_geometry(
                self.profile_one, 1952, 128, self.inputs, overlong
            )
        with self.assertRaisesRegex(m2_carrier.CarrierError, "manifestation-mismatch"):
            m2_carrier.validate_manifestation(
                replace(
                    self.manifestation_one,
                    carrier=self.manifestation_one.carrier[:-1],
                ),
                self.profile_one,
                self.profile_raw,
                self.limits_raw,
                self.damage_raw,
                self.bootstrap_raw,
                self.compiled,
                self.inputs,
                self.envelope,
                self.route_raw,
                self.package_one,
            )
        with self.assertRaisesRegex(m2_carrier.CarrierError, "manifestation-mismatch"):
            m2_carrier.validate_manifestation(
                replace(
                    self.manifestation_three,
                    density_ledger=self.manifestation_three.density_ledger[:-1],
                ),
                self.profile_three,
                self.profile_raw,
                self.limits_raw,
                self.damage_raw,
                self.bootstrap_raw,
                self.compiled,
                self.inputs,
                self.envelope,
                self.route_raw,
                self.package_three,
            )

    def test_atomic_allowlisted_persistence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="golden-board-writer-") as directory:
            output = Path(directory) / "candidates"
            self.assertEqual(
                generate_candidates.persist_candidates(
                    output, self.manifestation_one, self.manifestation_three
                ),
                "created",
            )
            observed = {
                path.relative_to(output).as_posix()
                for path in output.rglob("*")
                if path.is_file()
            }
            self.assertEqual(observed, set(generate_candidates.ALLOWLIST))
            self.assertEqual(
                generate_candidates.persist_candidates(
                    output, self.manifestation_one, self.manifestation_three
                ),
                "unchanged",
            )
            damage = output / self.profile_three.profile_id / "damage" / "proof.json"
            damage.parent.mkdir()
            damage.write_bytes(b"downstream evidence")
            self.assertEqual(
                generate_candidates.persist_candidates(
                    output, self.manifestation_one, self.manifestation_three
                ),
                "unchanged",
            )
            self.assertEqual(damage.read_bytes(), b"downstream evidence")
            extra = output / self.profile_one.profile_id / "extra"
            extra.write_bytes(b"not allowed")
            with self.assertRaisesRegex(
                generate_candidates.CandidateWriterError, "existing-allowlist"
            ):
                generate_candidates.persist_candidates(
                    output, self.manifestation_one, self.manifestation_three
                )


if __name__ == "__main__":
    unittest.main()
