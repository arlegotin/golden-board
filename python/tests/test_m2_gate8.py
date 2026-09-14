"""Bounded tests for the M2 gate-8 evidence primitives."""

from __future__ import annotations

import contextlib
import hashlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from golden_board import (
    bootstrap,
    canonical_manifest,
    m2_gate8,
    m2_recipe,
    m2_runner,
    m2_slice,
)
from tools.m2 import generate_gate8


ROOT = Path(__file__).resolve().parents[2]
RETAINED_GATE7 = all(
    path.is_file()
    for path in (
        ROOT
        / "artifacts/candidates/eh72-hier-r5-r2-r1-crc32c-v0/"
        "candidate-manifest.json",
        ROOT
        / "artifacts/candidates/eh72-hier-r5-r2-r1-crc32c-v0/damage/"
        "damage-manifest.json",
        ROOT
        / "artifacts/candidates/eh72-hier-r5-r2-r1-crc32c-v0/damage/"
        "independence-proof.json",
    )
)


class M2Gate8SourceProjection(unittest.TestCase):
    def git(self, root: Path, *arguments: str) -> None:
        subprocess.run(
            ("git", "-C", str(root), *arguments),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def repository(self, root: Path) -> None:
        self.git(root, "init", "-q")
        self.git(root, "config", "user.email", "gate8@example.invalid")
        self.git(root, "config", "user.name", "Gate 8 Test")
        (root / ".gitignore").write_bytes(b"ignored/\n")
        (root / "docs").mkdir()
        (root / "docs/roadmap.md").write_bytes(
            b"# Roadmap\n\n"
            b"| Project state | In progress |\n"
            b"| Current milestone | M2 |\n\n"
            b"## 12. Frozen\nA\n\n"
            b"## 13. Project status\nmutable\n\n"
            b"## 14. Adversarial stress matrix\nB\n"
        )
        (root / "docs/decisions.md").write_bytes(b"mutable decision\n")
        (root / "reports").mkdir()
        (root / "reports/m2-feasibility-v0.json").write_bytes(b"excluded\n")
        (root / "plain.txt").write_bytes(b"plain\n")
        executable = root / "run.sh"
        executable.write_bytes(b"#!/bin/sh\nexit 0\n")
        executable.chmod(0o755)
        (root / "ignored").mkdir()
        (root / "ignored/cache").write_bytes(b"ignored\n")
        self.git(root, "add", ".")
        self.git(root, "commit", "-qm", "base")

    def test_projection_is_exact_sorted_and_non_self_referential(self) -> None:
        with tempfile.TemporaryDirectory(prefix="m2-gate8-source-") as directory:
            root = Path(directory)
            self.repository(root)
            (root / "untracked.txt").write_bytes(b"current\n")
            raw = m2_gate8.build_evidence_source_projection(root)
            value = canonical_manifest.validate_canonical_manifest(raw)
            self.assertEqual(value["schema"], "m2-evidence-source-v0")
            rows = value["entries"]
            paths = [row["path"] for row in rows]
            self.assertEqual(paths, sorted(paths, key=str.encode))
            self.assertNotIn("docs/roadmap.md", paths)
            self.assertNotIn("docs/decisions.md", paths)
            self.assertNotIn("reports/m2-feasibility-v0.json", paths)
            self.assertNotIn("ignored/cache", paths)
            self.assertIn("untracked.txt", paths)
            by_path = {row["path"]: row for row in rows}
            self.assertEqual(by_path["plain.txt"]["mode"], "100644")
            self.assertEqual(by_path["run.sh"]["mode"], "100755")
            self.assertEqual(by_path["plain.txt"]["byte_length"], 6)
            self.assertEqual(
                by_path["plain.txt"]["sha256"], hashlib.sha256(b"plain\n").hexdigest()
            )
            self.assertEqual(
                m2_gate8.validate_evidence_source_projection(raw, root), value
            )

            (root / "docs/decisions.md").write_bytes(b"another decision\n")
            self.assertEqual(m2_gate8.build_evidence_source_projection(root), raw)
            roadmap = root / "docs/roadmap.md"
            roadmap.write_bytes(roadmap.read_bytes().replace(b"mutable", b"changed"))
            self.assertEqual(m2_gate8.build_evidence_source_projection(root), raw)
            (root / "plain.txt").write_bytes(b"changed\n")
            with self.assertRaises(m2_gate8.Gate8Error) as stale:
                m2_gate8.validate_evidence_source_projection(raw, root)
            self.assertEqual(stale.exception.reason, "source-projection-stale")

    def test_roadmap_hash_binds_only_normative_prefix_and_suffix(self) -> None:
        first = (
            b"prefix\n| Project state | In progress |\n"
            b"| Current milestone | M2 |\n"
            b"## 13. Project status\none\n"
            b"## 14. Adversarial stress matrix\nsuffix\n"
        )
        second = first.replace(b"In progress", b"Candidate ready").replace(
            b"\none\n", b"\ntwo\n"
        )
        third = second.replace(b"suffix", b"changed")
        self.assertEqual(
            m2_gate8.roadmap_normative_sha256(first),
            m2_gate8.roadmap_normative_sha256(second),
        )
        self.assertNotEqual(
            m2_gate8.roadmap_normative_sha256(first),
            m2_gate8.roadmap_normative_sha256(third),
        )
        for invalid in (
            b"missing\n",
            first + b"## 13. Project status\n",
            b"## 14. Adversarial stress matrix\nx\n## 13. Project status\ny\n",
            first.replace(b"| Project state | In progress |\n", b""),
            first.replace(
                b"| Current milestone | M2 |\n",
                b"| Current milestone | M2 | extra |\n",
            ),
            first.replace(b"\n", b"\r\n"),
            first[:-1],
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(m2_gate8.Gate8Error):
                    m2_gate8.roadmap_normative_sha256(invalid)

    def test_nonregular_visible_paths_reject(self) -> None:
        with tempfile.TemporaryDirectory(prefix="m2-gate8-invalid-") as directory:
            root = Path(directory)
            self.repository(root)
            (root / "visible-link").symlink_to("plain.txt")
            with self.assertRaises(m2_gate8.Gate8Error) as linked:
                m2_gate8.build_evidence_source_projection(root)
            self.assertEqual(linked.exception.reason, "source-projection-file")
            (root / "visible-link").unlink()
            long_parent = root / ("x" * 130)
            long_parent.mkdir()
            (long_parent / (("y" * 121) + ".txt")).write_bytes(b"x")
            with self.assertRaises(m2_gate8.Gate8Error) as path:
                m2_gate8.build_evidence_source_projection(root)
            self.assertEqual(path.exception.reason, "source-projection-path")

    def test_root_and_types_fail_closed(self) -> None:
        with self.assertRaises(TypeError):
            m2_gate8.build_evidence_source_projection(".")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            m2_gate8.roadmap_normative_sha256(bytearray())  # type: ignore[arg-type]
        with tempfile.TemporaryDirectory(prefix="m2-gate8-root-") as directory:
            root = Path(directory)
            with self.assertRaises(m2_gate8.Gate8Error):
                m2_gate8.build_evidence_source_projection(root)
            link = root / "link"
            target = root / "target"
            target.mkdir()
            link.symlink_to(target, target_is_directory=True)
            with self.assertRaises(m2_gate8.Gate8Error):
                m2_gate8.build_evidence_source_projection(link)

    def test_ignored_untracked_roadmap_rejects(self) -> None:
        with tempfile.TemporaryDirectory(prefix="m2-gate8-roadmap-") as directory:
            root = Path(directory)
            self.repository(root)
            self.git(root, "rm", "-q", "--cached", "docs/roadmap.md")
            with (root / ".gitignore").open("ab") as stream:
                stream.write(b"docs/roadmap.md\n")
            with self.assertRaises(m2_gate8.Gate8Error) as hidden:
                m2_gate8.build_evidence_source_projection(root)
            self.assertEqual(hidden.exception.reason, "roadmap-not-visible")


class M2Gate8FrozenProjections(unittest.TestCase):
    @staticmethod
    def write(root: Path, relative: str, raw: bytes) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    def test_owner_projection_binds_exact_sorted_raw_sources(self) -> None:
        with tempfile.TemporaryDirectory(prefix="m2-gate8-owner-") as directory:
            root = Path(directory)
            self.write(root, "conformance/m2-r3-owner-v1.json", b"fixture\n")
            self.write(root, "spec/route-data-v1.json", b"route\n")
            raw = m2_gate8.build_owner_projection(root, "known_answer_manifest")
            value = canonical_manifest.validate_canonical_manifest(raw)
            self.assertEqual(
                value,
                {
                    "projection_id": "known-answer-manifest-v7",
                    "schema": "golden-board.m2-owner-projection/v0",
                    "source_rows": [
                        {
                            "byte_length": 8,
                            "path": "conformance/m2-r3-owner-v1.json",
                            "sha256": hashlib.sha256(b"fixture\n").hexdigest(),
                        },
                        {
                            "byte_length": 6,
                            "path": "spec/route-data-v1.json",
                            "sha256": hashlib.sha256(b"route\n").hexdigest(),
                        },
                    ],
                },
            )
            self.assertEqual(
                m2_gate8.validate_owner_projection(
                    raw, root, "known_answer_manifest"
                ),
                value,
            )
            self.write(root, "spec/route-data-v1.json", b"changed\n")
            with self.assertRaises(m2_gate8.Gate8Error) as stale:
                m2_gate8.validate_owner_projection(
                    raw, root, "known_answer_manifest"
                )
            self.assertEqual(stale.exception.reason, "owner-projection-stale")
            with self.assertRaises(m2_gate8.Gate8Error) as role:
                m2_gate8.build_owner_projection(root, "unknown")
            self.assertEqual(role.exception.reason, "owner-projection-role")

    @staticmethod
    def damage_files() -> dict[str, bytes]:
        values: dict[str, bytes] = {
            "damage-manifest.json": b"root\n",
            "independence-proof.json": b"proof\n",
        }
        counts = (1, 1, 2, 3, 11, 1, 41, 3)
        for family, count in zip(range(8), counts, strict=True):
            values[f"damage-D{family}.json"] = f"D{family}\n".encode()
            for ordinal in range(count):
                values[
                    f"damage-D{family}-cases-{ordinal:04d}.json"
                ] = f"D{family}:{ordinal}\n".encode()
        return values

    def test_damage_inventory_excludes_only_the_bound_proof(self) -> None:
        files = self.damage_files()
        raw = m2_gate8.render_damage_inventory(files)
        value = canonical_manifest.validate_canonical_manifest(raw)
        self.assertEqual(value["schema"], "golden-board.m2-gate8-damage-inventory/v0")
        self.assertEqual(value["candidate_id"], "eh72-hier-r5-r2-r1-crc32c-v0")
        rows = value["file_rows"]
        self.assertEqual(len(rows), 72)
        self.assertEqual(
            [row["path"] for row in rows],
            sorted((set(files) - {"independence-proof.json"}), key=str.encode),
        )
        self.assertEqual(m2_gate8.validate_damage_inventory(raw, files), value)
        without_proof = dict(files)
        del without_proof["independence-proof.json"]
        with self.assertRaises(m2_gate8.Gate8Error) as missing:
            m2_gate8.render_damage_inventory(without_proof)
        self.assertEqual(missing.exception.reason, "damage-inventory-files")

        with tempfile.TemporaryDirectory(prefix="m2-gate8-damage-") as directory:
            root = Path(directory)
            for name, contents in files.items():
                self.write(
                    root,
                    "artifacts/candidates/eh72-hier-r5-r2-r1-crc32c-v0/"
                    f"damage/{name}",
                    contents,
                )
            self.assertEqual(m2_gate8.build_damage_inventory(root), raw)
            extra = (
                root
                / "artifacts/candidates/eh72-hier-r5-r2-r1-crc32c-v0/"
                "damage/extra.json"
            )
            extra.write_bytes(b"extra\n")
            with self.assertRaises(m2_gate8.Gate8Error) as unknown:
                m2_gate8.build_damage_inventory(root)
            self.assertEqual(unknown.exception.reason, "damage-inventory-allowlist")

    @staticmethod
    def semantic_fixture() -> tuple[
        bytes,
        bytes,
        bytes,
        tuple[tuple[int, bytes], ...],
        tuple[tuple[int, int, bytes], ...],
    ]:
        semantic_raw = canonical_manifest.serialize_manifest(
            {"schema": "golden-board.m2-semantic-envelope/v0"}
        )
        envelopes = []
        blocks = []
        section_rows = []
        for section_id in range(1, 139):
            fragment_count = 10 if section_id <= 37 else 9
            payload_length = fragment_count * 157 - 22
            envelope = bootstrap.encode_section_envelope(
                bootstrap.SectionEnvelope(
                    section_id,
                    1,
                    1,
                    128,
                    1,
                    (),
                    bytes((section_id & 0xFF,)) * payload_length,
                )
            )
            common = bootstrap.fragment_section(envelope, 7, 0)
            if len(common) != fragment_count:
                raise AssertionError("semantic fixture fragment count")
            envelopes.append((section_id, envelope))
            blocks.extend(
                (section_id, fragment_index, block)
                for fragment_index, block in enumerate(common)
            )
            section_rows.append(
                {
                    "section_id": section_id,
                    "semantic_copy_count": 1,
                    "fragment_count": fragment_count,
                    "envelope_bytes": len(envelope),
                }
            )
        candidate_raw = canonical_manifest.serialize_manifest(
            {
                "schema": "golden-board.m2-candidate-manifest/v1",
                "profile_id": "eh72-hier-r5-r2-r1-crc32c-v0",
                "profile_version": 7,
                "semantic_envelope_sha256": hashlib.sha256(
                    semantic_raw
                ).hexdigest(),
                "section_rows": section_rows,
            }
        )
        return (
            candidate_raw,
            b"content-stream\n",
            semantic_raw,
            tuple(envelopes),
            tuple(blocks),
        )

    def test_semantic_projection_binds_owned_binary_preimages(self) -> None:
        fixture = self.semantic_fixture()
        candidate, content, semantic, envelopes, blocks = fixture
        with self.assertRaises(m2_gate8.Gate8Error) as content_error:
            m2_gate8.build_semantic_content_projection(*fixture)
        self.assertEqual(content_error.exception.reason, "semantic-content-stream")
        changed = list(blocks)
        changed[0], changed[1] = changed[1], changed[0]
        with self.assertRaises(m2_gate8.Gate8Error) as order:
            m2_gate8.build_semantic_content_projection(
                candidate, content, semantic, envelopes, tuple(changed)
            )
        self.assertEqual(order.exception.reason, "semantic-common-order")

    def test_profile_tuple_identity_is_exact_and_stable(self) -> None:
        raw = m2_gate8.profile_tuple_manifest()
        value = canonical_manifest.validate_canonical_manifest(raw)
        self.assertEqual(
            value,
            {
                "local_check_id": "crc32c-v0",
                "mapping_id": "affine-slot-then-interior-v1",
                "physical_replica_counts": [1, 2, 5],
                "profile_id": "eh72-hier-r5-r2-r1-crc32c-v0",
                "profile_version": 7,
                "schema": "golden-board.m2-profile-tuple/v1",
                "section_check_id": "crc32c-v0",
                "semantic_copy_count": 1,
                "transport_id": "eh72-hier-repetition-v0",
            },
        )
        self.assertEqual(
            m2_gate8.profile_tuple_identity(), hashlib.sha256(raw).hexdigest()
        )

    @unittest.skipUnless(
        RETAINED_GATE7,
        "retained ignored Gate 1-7 evidence is absent in a clean execution snapshot",
    )
    def test_frozen_policy_receipts_cross_manifest_and_selection_are_closed(self) -> None:
        root = Path(__file__).resolve().parents[2]
        policy_raw = (root / "spec/gate8-policy-v0.toml").read_bytes()
        self.assertEqual(
            hashlib.sha256(policy_raw).hexdigest(), m2_gate8.GATE8_POLICY_SHA256
        )
        self.assertEqual(
            m2_gate8.load_gate8_policy(policy_raw)["candidate_id"],
            "eh72-hier-r5-r2-r1-crc32c-v0",
        )
        with self.assertRaises(m2_gate8.Gate8Error) as stale:
            m2_gate8.load_gate8_policy(policy_raw + b"\n")
        self.assertEqual(stale.exception.reason, "gate8-policy-hash")

        artifact_ids = [
            "semantic-content-projection",
            "candidate-manifest",
            "carrier",
            "ownership-ledger",
            "capacity-ledger",
            "density-ledger",
            "damage-bundle-inventory",
            "independence-proof",
        ]
        producer_ids = [
            "native-python",
            "native-rust",
            "linux-python",
            "linux-rust",
        ]
        receipts = {}
        for producer in producer_ids:
            receipts[producer] = canonical_manifest.serialize_manifest(
                {
                    "artifact_rows": [
                        {
                            "artifact_id": artifact_id,
                            "sha256": hashlib.sha256(artifact_id.encode()).hexdigest(),
                        }
                        for artifact_id in artifact_ids
                    ],
                    "candidate_id": "eh72-hier-r5-r2-r1-crc32c-v0",
                    "producer_id": producer,
                    "schema": "golden-board.m2-gate8-producer-receipt/v0",
                }
            )
        candidate_raw = (
            root
            / "artifacts/candidates/eh72-hier-r5-r2-r1-crc32c-v0/"
            "candidate-manifest.json"
        ).read_bytes()
        cross_raw = m2_gate8.render_cross_language_manifest(receipts, candidate_raw)
        cross = canonical_manifest.validate_canonical_manifest(cross_raw)
        self.assertEqual(cross["summary"], {"artifact_count": 8, "result": "pass"})
        self.assertEqual(
            m2_gate8.validate_cross_language_manifest(
                cross_raw, receipts, candidate_raw
            ),
            cross,
        )
        rust = canonical_manifest.validate_canonical_manifest(
            receipts["native-rust"]
        )
        rust["artifact_rows"][0]["sha256"] = "0" * 64
        disagreeing = dict(receipts)
        disagreeing["native-rust"] = canonical_manifest.serialize_manifest(rust)
        fail_raw = m2_gate8.render_cross_language_manifest(
            disagreeing, candidate_raw
        )
        self.assertEqual(
            canonical_manifest.validate_canonical_manifest(fail_raw)["summary"][
                "result"
            ],
            "fail",
        )

        metrics = {
            "operation_kind_count": 23,
            "table_count": 13,
            "table_bytes": 1470,
            "graph_nodes": 699,
            "graph_edges": 1087,
            "dependency_depth": 36,
            "recipe_cells": 830016,
            "worked_example_cells": 11712,
            "held_out_example_cells": 11712,
            "shell_cells": 978944,
            "convention_count": 12,
            "plain_bits": 1954312,
            "protected_bits": 3181248,
            "reserve_bits": 57128,
            "total_bits": 4161600,
            "robustness_ppm": 0,
            "worst_case_work_units": 4484682504,
            "scratch_bytes": 6163,
            "remaining_reserve_bytes": 4088,
        }
        profile_raw = (root / "spec/profile-policy-v1.toml").read_bytes()
        row = m2_gate8.build_candidate_row(metrics, profile_raw, cross_raw)
        selection_raw = m2_gate8.render_selection(row, cross_raw, profile_raw)
        selection = canonical_manifest.validate_canonical_manifest(selection_raw)
        self.assertEqual(len(selection["selection_steps"]), 6)
        self.assertEqual(
            [value["step"] for value in selection["selection_steps"]],
            [
                "gate-filter",
                "lowest-complexity-class",
                "near-minimum-band",
                "rank",
                "top-two",
                "preference",
            ],
        )
        self.assertEqual(
            m2_gate8.validate_selection(
                selection_raw, row, cross_raw, profile_raw
            ),
            selection,
        )
        with self.assertRaises(m2_gate8.Gate8Error) as no_vote:
            m2_gate8.build_candidate_row(metrics, profile_raw, fail_raw)
        self.assertEqual(no_vote.exception.reason, "candidate-cross-language")

    def test_producer_ownership_ledger_does_not_invent_carrier_binding(self) -> None:
        def artifact_set(*, capacity_carrier: bool) -> tuple[dict[str, bytes], str]:
            carrier = (64).to_bytes(4, "big") + b"\0" * 8
            carrier_sha256 = hashlib.sha256(carrier).hexdigest()
            semantic_envelope_sha256 = "1" * 64
            semantic = canonical_manifest.serialize_manifest(
                {
                    "candidate_id": "eh72-hier-r5-r2-r1-crc32c-v0",
                    "schema": "golden-board.m2-gate8-semantic-content/v0",
                    "semantic_envelope_sha256": semantic_envelope_sha256,
                }
            )
            ownership = canonical_manifest.serialize_manifest(
                {
                    "profile_id": "eh72-hier-r5-r2-r1-crc32c-v0",
                    "schema": "golden-board.m2-ownership-ledger/v1",
                }
            )
            capacity_value = {
                "profile_id": "eh72-hier-r5-r2-r1-crc32c-v0",
                "schema": "golden-board.m2-capacity-ledger/v1",
            }
            if capacity_carrier:
                capacity_value["carrier_sha256"] = carrier_sha256
            capacity = canonical_manifest.serialize_manifest(capacity_value)
            density = canonical_manifest.serialize_manifest(
                {
                    "carrier_sha256": carrier_sha256,
                    "profile_id": "eh72-hier-r5-r2-r1-crc32c-v0",
                    "schema": "golden-board.m2-density-ledger/v0",
                }
            )
            candidate = canonical_manifest.serialize_manifest(
                {
                    "capacity_ledger_sha256": hashlib.sha256(capacity).hexdigest(),
                    "carrier_sha256": carrier_sha256,
                    "density_ledger_sha256": hashlib.sha256(density).hexdigest(),
                    "ownership_sha256": hashlib.sha256(ownership).hexdigest(),
                    "profile_id": "eh72-hier-r5-r2-r1-crc32c-v0",
                    "profile_version": 7,
                    "schema": "golden-board.m2-candidate-manifest/v1",
                    "semantic_envelope_sha256": semantic_envelope_sha256,
                    "side": 8,
                }
            )
            candidate_sha256 = hashlib.sha256(candidate).hexdigest()
            return (
                {
                    "semantic-content-projection": semantic,
                    "candidate-manifest": candidate,
                    "carrier": carrier,
                    "ownership-ledger": ownership,
                    "capacity-ledger": capacity,
                    "density-ledger": density,
                    "damage-bundle-inventory": canonical_manifest.serialize_manifest(
                        {
                            "candidate_id": "eh72-hier-r5-r2-r1-crc32c-v0",
                            "schema": "golden-board.m2-gate8-damage-inventory/v0",
                        }
                    ),
                    "independence-proof": canonical_manifest.serialize_manifest(
                        {
                            "candidate_manifest_sha256": candidate_sha256,
                            "profile_id": "eh72-hier-r5-r2-r1-crc32c-v0",
                            "schema": "golden-board.m2-independence-proof/v1",
                            "summary": {"result": "pass"},
                        }
                    ),
                },
                candidate_sha256,
            )

        artifacts, candidate_sha256 = artifact_set(capacity_carrier=True)
        with mock.patch.object(
            m2_gate8, "_CANDIDATE_MANIFEST_SHA256", candidate_sha256
        ):
            receipt = m2_gate8.render_producer_receipt(
                "native-python", artifacts
            )
        self.assertEqual(
            canonical_manifest.validate_canonical_manifest(receipt)["producer_id"],
            "native-python",
        )

        invalid, invalid_candidate_sha256 = artifact_set(capacity_carrier=False)
        with (
            mock.patch.object(
                m2_gate8,
                "_CANDIDATE_MANIFEST_SHA256",
                invalid_candidate_sha256,
            ),
            self.assertRaises(m2_gate8.Gate8Error) as rejected,
        ):
            m2_gate8.render_producer_receipt("native-python", invalid)
        self.assertEqual(rejected.exception.reason, "producer-ledger")

    def test_bundle_manifests_bind_every_role_release_path_and_mode(self) -> None:
        root = Path(__file__).resolve().parents[2]
        policy_raw = (root / "spec/gate8-policy-v0.toml").read_bytes()
        policy = m2_gate8.load_gate8_policy(policy_raw)
        for kind in ("technical", "learner"):
            bundle = policy[f"{kind}_bundle"]
            roles = bundle["participant_roles"] + bundle["evaluator_roles"]
            files = {
                role: f"{kind}:{role}\n".encode("ascii") for role in roles
            }
            raw = m2_gate8.render_bundle_manifest(policy_raw, kind, files)
            value = canonical_manifest.validate_canonical_manifest(raw)
            self.assertEqual(
                m2_gate8.validate_bundle_manifest(
                    raw, policy_raw, kind, files
                ),
                value,
            )
            self.assertEqual(
                [row["role_id"] for row in value["participant_files"]],
                bundle["participant_roles"],
            )
            released = [
                role
                for row in value["release_rows"]
                for role in row["participant_role_ids"]
            ]
            self.assertEqual(released, bundle["participant_roles"])
            modes = {
                row["role_id"]: row["mode"]
                for row in value["participant_files"] + value["evaluator_files"]
            }
            if kind == "learner":
                self.assertEqual(modes["runner"], "100755")
            changed = dict(files)
            changed[roles[0]] += b"changed\n"
            with self.assertRaises(m2_gate8.Gate8Error) as stale:
                m2_gate8.validate_bundle_manifest(
                    raw, policy_raw, kind, changed
                )
            self.assertEqual(stale.exception.reason, "bundle-stale")

    @unittest.skipUnless(
        RETAINED_GATE7,
        "retained ignored Gate 1-7 evidence is absent in a clean execution snapshot",
    )
    def test_damage_linux_and_generated_evidence_projections_are_closed(self) -> None:
        root = Path(__file__).resolve().parents[2]
        candidate_root = (
            root / "artifacts/candidates/eh72-hier-r5-r2-r1-crc32c-v0"
        )
        damage_root = candidate_root / "damage"
        families = {
            f"D{ordinal}": (damage_root / f"damage-D{ordinal}.json").read_bytes()
            for ordinal in range(8)
        }
        damage_rows = m2_gate8.build_damage_rows(
            (damage_root / "damage-manifest.json").read_bytes(), families
        )
        self.assertEqual([row["family_id"] for row in damage_rows], [f"D{i}" for i in range(8)])
        self.assertTrue(all(row["result"] == "pass" for row in damage_rows))
        self.assertTrue(all(row["wrong_accept_count"] == 0 for row in damage_rows))

        artifact_ids = [
            "semantic-content-projection",
            "candidate-manifest",
            "carrier",
            "ownership-ledger",
            "capacity-ledger",
            "density-ledger",
            "damage-bundle-inventory",
            "independence-proof",
        ]
        producer_ids = [
            "native-python",
            "native-rust",
            "linux-python",
            "linux-rust",
        ]
        receipts = {
            producer: canonical_manifest.serialize_manifest(
                {
                    "artifact_rows": [
                        {
                            "artifact_id": artifact,
                            "sha256": hashlib.sha256(artifact.encode()).hexdigest(),
                        }
                        for artifact in artifact_ids
                    ],
                    "candidate_id": "eh72-hier-r5-r2-r1-crc32c-v0",
                    "producer_id": producer,
                    "schema": "golden-board.m2-gate8-producer-receipt/v0",
                }
            )
            for producer in producer_ids
        }
        candidate_raw = (candidate_root / "candidate-manifest.json").read_bytes()
        cross_raw = m2_gate8.render_cross_language_manifest(receipts, candidate_raw)
        verifier_raw = (root / "artifacts/linux/verifier-v0.env").read_bytes()
        source_raw = m2_gate8.build_evidence_source_projection(root)
        linux_raw = m2_gate8.render_linux_attestation(
            source_raw,
            cross_raw,
            verifier_raw,
        )
        self.assertEqual(
            m2_gate8.validate_linux_attestation(
                linux_raw,
                source_raw,
                cross_raw,
                verifier_raw,
            )["linux_full"],
            "pass",
        )
        mismatched_source = canonical_manifest.serialize_manifest(
            {
                "entries": [
                    {
                        "byte_length": (root / "tools/linux/Dockerfile").stat().st_size,
                        "mode": "100644",
                        "path": "tools/linux/Dockerfile",
                        "sha256": "0" * 64,
                    }
                ],
                "roadmap_normative_sha256": "1" * 64,
                "schema": "m2-evidence-source-v0",
            }
        )
        with self.assertRaisesRegex(m2_gate8.Gate8Error, "linux-image-evidence"):
            m2_gate8.render_linux_attestation(
                mismatched_source,
                cross_raw,
                verifier_raw,
            )

        shared_names = [
            ("content_stream", "m2_all"),
            ("vertical_slice", "slice-v0"),
            ("semantic_envelope", "capacity-envelope-v1"),
            ("profile_limits_derivation", "profile-limits-v7"),
            ("side_search_policy", "side-search-v7"),
            ("evidence_source_projection", "m2-evidence-source-v0"),
            ("selection_recomputation", "selection-v0"),
            ("linux_attestation", "linux-v0"),
            ("technical_bundle", "technical-v0"),
            ("learner_bundle", "learner-v0"),
        ]
        shared = {
            role: (name, f"shared:{role}\n".encode())
            for role, name in shared_names
        }
        candidate_roles = [
            "parameter_manifest",
            "known_answer_manifest",
            "shell_manifest",
            "recipe_manifest",
            "grammar_state_manifest",
            "work_scratch_ledger",
            "carrier",
            "ownership_ledger",
            "capacity_ledger",
            "density_ledger",
            "damage_manifest",
            "damage_D0",
            "damage_D1",
            "damage_D2",
            "damage_D3",
            "damage_D4",
            "damage_D5",
            "damage_D6",
            "damage_D7",
            "independence_proof",
            "cross_language_manifest",
        ]
        candidate = {
            role: f"candidate:{role}\n".encode() for role in candidate_roles
        }
        evidence_raw = m2_gate8.render_generated_evidence(shared, candidate)
        evidence = canonical_manifest.validate_canonical_manifest(evidence_raw)
        self.assertEqual(len(evidence["shared_identities"]), 10)
        self.assertEqual(
            len(evidence["candidate_evidence"][0]["identities"]), 21
        )
        self.assertEqual(
            m2_gate8.validate_generated_evidence(
                evidence_raw, shared, candidate
            ),
            evidence,
        )

    @unittest.skipUnless(
        RETAINED_GATE7,
        "retained ignored Gate 1-7 evidence is absent in a clean execution snapshot",
    )
    def test_policy_derived_geometry_content_and_heldout_objects_are_exact(self) -> None:
        root = Path(__file__).resolve().parents[2]
        policy_raw = (root / "spec/gate8-policy-v0.toml").read_bytes()
        candidate_root = (
            root / "artifacts/candidates/eh72-hier-r5-r2-r1-crc32c-v0"
        )
        geometry_raw = m2_gate8.render_geometry_equivalence(
            (candidate_root / "candidate-manifest.json").read_bytes()
        )
        self.assertEqual(
            canonical_manifest.validate_canonical_manifest(geometry_raw),
            {
                "admitted_N_S_pairs": [{"N": 4_161_600, "S": 2_040}],
                "schema": "golden-board.m2-geometry-equivalence/v0",
            },
        )

        def read(relative: str) -> bytes:
            return (root / relative).read_bytes()
        compiled = m2_slice.compile_slice_v0(
            read("studies/m2/slice-v0.json"),
            read("conformance/content-v0.json"),
            read("conformance/chess-v0.json"),
            read("reports/game-set-v0.bin"),
            read("spec/content-v0.md"),
            read("spec/constants-v0.toml"),
            read("spec/curriculum-v0.toml"),
        )
        request_raw, result_raw = m2_gate8.render_technical_content_query(
            policy_raw, compiled.content_bytes
        )
        request = canonical_manifest.validate_canonical_manifest(request_raw)
        result = canonical_manifest.validate_canonical_manifest(result_raw)
        self.assertEqual(request["generic_record"], {"record_id": 12})
        self.assertEqual(result["chess_transition"]["move_hex"], "31c0")
        self.assertEqual(
            result["chess_transition"]["resulting_position_identity"],
            "517c201fd26a976d9181d3a6fd7bf4afaf17d680635e6504a88b4755f827c523",
        )

        heldout_request = m2_gate8.render_learner_heldout_request(policy_raw)
        self.assertEqual(
            heldout_request,
            read("studies/m2/templates/learner/heldout-cases.json"),
        )
        binding = canonical_manifest.validate_canonical_manifest(
            m2_gate8.render_learner_slice_binding(
                policy_raw, compiled.content_bytes
            )
        )
        self.assertEqual(binding["root_record_id"], 182)
        semantic = m2_runner.semantic_path_bytes(
            m2_runner.run_m2_semantic_path(
                compiled.content_bytes, label_suppressed=True
            )
        )
        learner = canonical_manifest.validate_canonical_manifest(
            m2_gate8.render_learner_expected(
                policy_raw, compiled.content_bytes, semantic
            )
        )
        self.assertEqual(
            learner["semantic_path_sha256"],
            "966e510af60a9a95afc60badee2d985da95add187f7d132bc2009369db33cbd3",
        )

        damage = candidate_root / "damage"
        wanted = ("D3-000000", "D2-000000", "D4-000000", "D7-000011")
        case_rows = {}
        for case_id in wanted:
            family = case_id[:2]
            for shard in sorted(damage.glob(f"damage-{family}-cases-*.json")):
                rows = canonical_manifest.validate_canonical_manifest(
                    shard.read_bytes()
                )["case_rows"]
                match = next(
                    (row for row in rows if row["case_id"] == case_id), None
                )
                if match is not None:
                    case_rows[case_id] = match
                    break
        classes = canonical_manifest.validate_canonical_manifest(
            m2_gate8.render_technical_heldout_classes(case_rows)
        )
        expected = canonical_manifest.validate_canonical_manifest(
            m2_gate8.render_technical_heldout_expected(case_rows)
        )
        reordered_case_rows = {
            case_id: case_rows[case_id]
            for case_id in ("D2-000000", "D3-000000", "D4-000000", "D7-000011")
        }
        self.assertEqual(
            m2_gate8.render_technical_heldout_classes(reordered_case_rows),
            m2_gate8.render_technical_heldout_classes(case_rows),
        )
        self.assertEqual(
            m2_gate8.render_technical_heldout_expected(reordered_case_rows),
            m2_gate8.render_technical_heldout_expected(case_rows),
        )
        self.assertEqual(len(classes["rows"]), 4)
        self.assertEqual(
            [row["expected_artifact_state"] for row in expected["heldout_rows"]],
            ["degraded", "degraded", "exact", "failure"],
        )

        policy = m2_gate8.load_gate8_policy(policy_raw)
        technical_roles = (
            policy["technical_bundle"]["participant_roles"]
            + policy["technical_bundle"]["evaluator_roles"]
        )
        learner_roles = (
            policy["learner_bundle"]["participant_roles"]
            + policy["learner_bundle"]["evaluator_roles"]
        )
        technical_generated = {
            role: f"technical:{role}\n".encode()
            for role in technical_roles
            if not policy["technical_bundle"]["role_preimages"][role].startswith(
                "tracked-template:"
            )
        }
        technical_generated["resource-limits"] = read(
            "spec/profile-limits-v1.toml"
        )
        learner_generated = {
            role: f"learner:{role}\n".encode()
            for role in learner_roles
            if not policy["learner_bundle"]["role_preimages"][role].startswith(
                "tracked-template:"
            )
        }
        learner_generated["content-stream"] = compiled.content_bytes
        learner_generated["runner"] = read("tools/m2/learner_runner.py")
        learner_generated["semantic-path-expected"] = semantic
        learner_generated["heldout-cases"] = read(
            "studies/m2/templates/learner/heldout-cases.json"
        )
        technical_files = m2_gate8.build_bundle_files(
            policy_raw, root, "technical", technical_generated
        )
        learner_files = m2_gate8.build_bundle_files(
            policy_raw, root, "learner", learner_generated
        )
        technical_bundle = m2_gate8.render_bundle_manifest(
            policy_raw, "technical", technical_files
        )
        learner_bundle = m2_gate8.render_bundle_manifest(
            policy_raw, "learner", learner_files
        )
        owner_roles = {
            role: m2_gate8.build_owner_projection(root, role)
            for role in (
                "parameter_manifest",
                "known_answer_manifest",
                "shell_manifest",
                "recipe_manifest",
                "grammar_state_manifest",
                "work_scratch_ledger",
                "profile_limits_derivation",
                "side_search_policy",
            )
        }
        damage_root = candidate_root / "damage"
        generated_shared = {
            "content_stream": ("m2_all", compiled.content_bytes),
            "vertical_slice": ("slice-v0", read("studies/m2/slice-v0.json")),
            "semantic_envelope": (
                "capacity-envelope-v1",
                (candidate_root / "semantic-envelope.json").read_bytes(),
            ),
            "profile_limits_derivation": (
                "profile-limits-v7",
                owner_roles["profile_limits_derivation"],
            ),
            "side_search_policy": (
                "side-search-v7",
                owner_roles["side_search_policy"],
            ),
            "evidence_source_projection": ("m2-evidence-source-v0", b"source\n"),
            "selection_recomputation": ("selection-v0", b"selection\n"),
            "linux_attestation": ("linux-v0", b"linux\n"),
            "technical_bundle": ("technical-v0", technical_bundle),
            "learner_bundle": ("learner-v0", learner_bundle),
        }
        generated_candidate = {
            **{
                role: owner_roles[role]
                for role in (
                    "parameter_manifest",
                    "known_answer_manifest",
                    "shell_manifest",
                    "recipe_manifest",
                    "grammar_state_manifest",
                    "work_scratch_ledger",
                )
            },
            "carrier": (candidate_root / "carrier.obs-bits").read_bytes(),
            "ownership_ledger": (
                candidate_root / "ownership-ledger.json"
            ).read_bytes(),
            "capacity_ledger": (
                candidate_root / "capacity-ledger.json"
            ).read_bytes(),
            "density_ledger": (candidate_root / "density-ledger.json").read_bytes(),
            "damage_manifest": (damage_root / "damage-manifest.json").read_bytes(),
            **{
                f"damage_D{ordinal}": (
                    damage_root / f"damage-D{ordinal}.json"
                ).read_bytes()
                for ordinal in range(8)
            },
            "independence_proof": (
                damage_root / "independence-proof.json"
            ).read_bytes(),
            "cross_language_manifest": b"cross\n",
        }
        generated_raw = m2_gate8.render_generated_evidence(
            generated_shared, generated_candidate
        )
        pilot = m2_gate8.render_pilot_envelope(
            source_root=root,
            gate8_policy_raw=policy_raw,
            candidate_manifest_raw=(
                candidate_root / "candidate-manifest.json"
            ).read_bytes(),
            carrier_raw=(candidate_root / "carrier.obs-bits").read_bytes(),
            ownership_ledger_raw=(
                candidate_root / "ownership-ledger.json"
            ).read_bytes(),
            capacity_ledger_raw=(
                candidate_root / "capacity-ledger.json"
            ).read_bytes(),
            density_ledger_raw=(
                candidate_root / "density-ledger.json"
            ).read_bytes(),
            independence_proof_raw=(
                candidate_root / "damage/independence-proof.json"
            ).read_bytes(),
            semantic_envelope_raw=(
                candidate_root / "semantic-envelope.json"
            ).read_bytes(),
            bootstrap_spec_raw=read("spec/bootstrap-v1.md"),
            route_data_raw=read("spec/route-data-v1.json"),
            profile_policy_raw=read("spec/profile-policy-v1.toml"),
            damage_policy_raw=read("spec/damage-policy-v1.toml"),
            parameter_projection_raw=owner_roles["parameter_manifest"],
            geometry_equivalence_raw=geometry_raw,
            technical_bundle_raw=technical_bundle,
            technical_files=technical_files,
            technical_heldout_classes_raw=m2_gate8.render_technical_heldout_classes(
                case_rows
            ),
            learner_bundle_raw=learner_bundle,
            learner_files=learner_files,
            content_stream_raw=compiled.content_bytes,
            vertical_slice_raw=read("studies/m2/slice-v0.json"),
            runner_raw=read("tools/m2/learner_runner.py"),
            semantic_path_raw=semantic,
            generated_evidence_raw=generated_raw,
            generated_shared_preimages=generated_shared,
            generated_candidate_preimages=generated_candidate,
        )
        self.assertEqual(
            pilot["technical_invariance"]["raw_geometry"]["observed_N"],
            4_161_600,
        )
        self.assertEqual(
            pilot["technical_invariance"]["interior_bounds"],
            {
                "density_min_ppm": 250000,
                "density_max_ppm": 750000,
                "tile_density_min_ppm": 125000,
                "tile_density_max_ppm": 875000,
                "max_horizontal_run": 446,
                "max_vertical_run": 446,
                "max_repeated_rows": 55,
                "max_repeated_columns": 55,
            },
        )

    @unittest.skipUnless(
        os.environ.get("GB_M2_GATE8_CARRIER") == "1",
        "set GB_M2_GATE8_CARRIER=1 for retained-carrier extraction KAT",
    )
    def test_retained_carrier_semantic_extraction(self) -> None:
        root = Path(__file__).resolve().parents[2]
        candidate_root = (
            root / "artifacts/candidates/eh72-hier-r5-r2-r1-crc32c-v0"
        )
        projection = m2_gate8.build_semantic_content_projection_from_carrier(
            (candidate_root / "candidate-manifest.json").read_bytes(),
            (candidate_root / "carrier.obs-bits").read_bytes(),
            (candidate_root / "semantic-envelope.json").read_bytes(),
        )
        value = canonical_manifest.validate_canonical_manifest(
            projection.canonical_bytes
        )
        self.assertEqual(value["schema"], "golden-board.m2-gate8-semantic-content/v0")
        self.assertEqual(
            value["content_stream_sha256"],
            hashlib.sha256(projection.content_stream).hexdigest(),
        )
        metrics = m2_gate8.derive_candidate_metrics(
            m2_recipe.build_r3_recipe_package(),
            (root / "spec/profile-limits-v1.toml").read_bytes(),
            (root / "spec/route-data-v1.json").read_bytes(),
            (candidate_root / "capacity-ledger.json").read_bytes(),
        )
        self.assertEqual(
            list(metrics.items()),
            [
                ("operation_kind_count", 23),
                ("table_count", 13),
                ("table_bytes", 1470),
                ("graph_nodes", 699),
                ("graph_edges", 1087),
                ("dependency_depth", 36),
                ("recipe_cells", 830016),
                ("worked_example_cells", 11712),
                ("held_out_example_cells", 11712),
                ("shell_cells", 978944),
                ("convention_count", 12),
                ("plain_bits", 1954312),
                ("protected_bits", 3181248),
                ("reserve_bits", 57128),
                ("total_bits", 4161600),
                ("robustness_ppm", 0),
                ("worst_case_work_units", 4484682504),
                ("scratch_bytes", 6163),
                ("remaining_reserve_bytes", 4088),
            ],
        )
        artifacts = {
            "semantic-content-projection": projection.canonical_bytes,
            "candidate-manifest": (
                candidate_root / "candidate-manifest.json"
            ).read_bytes(),
            "carrier": (candidate_root / "carrier.obs-bits").read_bytes(),
            "ownership-ledger": (
                candidate_root / "ownership-ledger.json"
            ).read_bytes(),
            "capacity-ledger": (
                candidate_root / "capacity-ledger.json"
            ).read_bytes(),
            "density-ledger": (
                candidate_root / "density-ledger.json"
            ).read_bytes(),
            "damage-bundle-inventory": m2_gate8.build_damage_inventory(root),
            "independence-proof": (
                candidate_root / "damage/independence-proof.json"
            ).read_bytes(),
        }
        receipt = m2_gate8.render_producer_receipt("native-python", artifacts)
        self.assertEqual(
            m2_gate8.validate_producer_receipt(
                receipt, "native-python", artifacts
            )["producer_id"],
            "native-python",
        )

class M2Gate8CliLifecycle(unittest.TestCase):
    @staticmethod
    def private_directory(root: Path, name: str) -> Path:
        path = root / name
        path.mkdir(mode=0o700)
        path.chmod(0o700)
        return path

    @staticmethod
    def receipt(producer_id: str) -> bytes:
        artifact_ids = (
            "semantic-content-projection",
            "candidate-manifest",
            "carrier",
            "ownership-ledger",
            "capacity-ledger",
            "density-ledger",
            "damage-bundle-inventory",
            "independence-proof",
        )
        return canonical_manifest.serialize_manifest(
            {
                "artifact_rows": [
                    {
                        "artifact_id": artifact_id,
                        "sha256": hashlib.sha256(artifact_id.encode()).hexdigest(),
                    }
                    for artifact_id in artifact_ids
                ],
                "candidate_id": "eh72-hier-r5-r2-r1-crc32c-v0",
                "producer_id": producer_id,
                "schema": "golden-board.m2-gate8-producer-receipt/v0",
            }
        )

    def test_refresh_fixture_admits_only_exact_standalone_provenance(self) -> None:
        policy = (ROOT / "spec/gate8-policy-v0.toml").read_bytes()
        receipt_raw = m2_gate8._linux_acquisition_receipt_bytes(
            m2_gate8.load_gate8_policy(policy)
        )
        with tempfile.TemporaryDirectory(prefix="m2-refresh-fixture-") as name:
            root = Path(name).resolve()
            (root / "spec").mkdir()
            (root / "spec/gate8-policy-v0.toml").write_bytes(policy)
            linux = root / "artifacts/linux"
            linux.mkdir(parents=True)
            receipt = linux / "verifier-v0.env"
            with (
                mock.patch(__name__ + ".ROOT", root),
                mock.patch.object(generate_gate8, "_GATE8_ROOT", root / "artifacts/gate8"),
            ):
                with self.assertRaises(unittest.SkipTest):
                    self.refresh_prior_values()
                receipt.write_bytes(receipt_raw)
                with self.assertRaises(unittest.SkipTest):
                    self.refresh_prior_values()
                for bad in (receipt_raw + b"\n", b"", b"x" * 380):
                    receipt.write_bytes(bad)
                    with self.assertRaises(generate_gate8.Gate8CliError):
                        self.refresh_prior_values()
                receipt.write_bytes(receipt_raw)
                alias = linux / "alias"
                os.link(receipt, alias)
                with self.assertRaises(generate_gate8.Gate8CliError):
                    self.refresh_prior_values()
                receipt.unlink()
                receipt.symlink_to(alias)
                with self.assertRaises(generate_gate8.Gate8CliError):
                    self.refresh_prior_values()
                receipt.unlink()
                alias.unlink()
                os.mkfifo(receipt)
                with self.assertRaises(generate_gate8.Gate8CliError):
                    self.refresh_prior_values()
                receipt.unlink()
                receipt.write_bytes(receipt_raw)
                for path in (
                    root / "artifacts/gate8",
                    linux / "verifier-refresh-c1ef7213-v0",
                    linux / "gate8-clean-linux-test-refresh-v0",
                ):
                    path.mkdir()
                    with self.assertRaises(generate_gate8.Gate8CliError):
                        self.refresh_prior_values()
                    path.rmdir()
                    path.symlink_to(root / "missing")
                    with self.assertRaises(generate_gate8.Gate8CliError):
                        self.refresh_prior_values()
                    if path == root / "artifacts/gate8":
                        try:
                            with self.assertRaises(generate_gate8.Gate8CliError):
                                self.test_candidate_ready_provenance_fixture_repair_is_one_way_and_idempotent()
                        except unittest.SkipTest:
                            self.fail("present linked history must reject, never skip")
                    path.unlink()

    def test_assembly_lifecycle_needs_no_retained_refresh_fixture(self) -> None:
        with mock.patch.object(
            self, "refresh_prior_values", side_effect=AssertionError("archive read")
        ):
            self.test_assembly_tree_is_report_last_idempotent_and_rolls_back()

    def refresh_prior_values(self) -> dict[str, tuple[bytes, int]]:
        archive = (
            ROOT / "artifacts/linux/verifier-refresh-c1ef7213-v0"
        )
        if archive.exists() or archive.is_symlink():
            return generate_gate8._archive_values(archive)
        gate8 = ROOT / "artifacts/gate8"
        receipt = ROOT / "artifacts/linux/verifier-v0.env"
        historical_paths = (
            gate8,
            *(ROOT / path for path in (
                "artifacts/linux/gate8-clean-linux-test-refresh-v0",
                "artifacts/linux/gate8-candidate-ready-test-refresh-v0",
                "artifacts/linux/gate8-candidate-ready-runtime-test-refresh-v0",
                "artifacts/linux/gate8-candidate-ready-clean-snapshot-refresh-v0",
                "artifacts/linux/gate8-candidate-ready-provenance-input-refresh-v0",
                "artifacts/linux/gate8-provenance-fixture-refresh-v0",
            )),
        )
        if not any(path.exists() or path.is_symlink() for path in historical_paths):
            if receipt.exists() or receipt.is_symlink():
                raw = generate_gate8._regular_file(receipt, "fixture-provenance", 379)
                policy_raw = (ROOT / "spec/gate8-policy-v0.toml").read_bytes()
                try:
                    m2_gate8.parse_linux_acquisition_receipt(raw, policy_raw)
                except m2_gate8.Gate8Error as error:
                    raise generate_gate8.Gate8CliError("fixture-provenance", 2) from error
            self.skipTest(
                "retained ignored verifier-refresh evidence is absent in a "
                "clean execution snapshot"
            )
        policy_raw = (ROOT / "spec/gate8-policy-v0.toml").read_bytes()
        return generate_gate8._admit_prior_live(policy_raw)

    def release_repair_prior_values(self) -> dict[str, tuple[bytes, int]]:
        archive = ROOT / "artifacts/linux/gate8-clean-linux-test-refresh-v0"
        if archive.exists() or archive.is_symlink():
            return generate_gate8._release_repair_archive_values(archive)
        gate8 = ROOT / "artifacts/gate8"
        verifier_archive = ROOT / "artifacts/linux/verifier-refresh-c1ef7213-v0"
        if (
            not gate8.exists()
            and not gate8.is_symlink()
            and not verifier_archive.exists()
            and not verifier_archive.is_symlink()
        ):
            self.skipTest(
                "retained ignored release-repair evidence is absent in a "
                "clean execution snapshot"
            )
        return generate_gate8._release_repair_live_values()

    def clean_snapshot_test_repair_prior_values(
        self,
    ) -> dict[str, tuple[bytes, int]]:
        archive = (
            ROOT
            / "artifacts/linux/gate8-candidate-ready-clean-snapshot-refresh-v0"
        )
        if archive.exists() or archive.is_symlink():
            return generate_gate8._clean_snapshot_test_repair_archive_values(
                archive
            )
        gate8 = ROOT / "artifacts/gate8"
        if not gate8.exists() and not gate8.is_symlink():
            self.skipTest(
                "retained ignored clean-snapshot repair evidence is absent "
                "in a clean execution snapshot"
            )
        return generate_gate8._clean_snapshot_test_repair_live_values()

    def provenance_input_repair_prior_values(
        self,
    ) -> dict[str, tuple[bytes, int]]:
        archive = (
            ROOT
            / "artifacts/linux/gate8-candidate-ready-provenance-input-refresh-v0"
        )
        if archive.exists() or archive.is_symlink():
            return generate_gate8._provenance_input_repair_archive_values(
                archive
            )
        gate8 = ROOT / "artifacts/gate8"
        if not gate8.exists() and not gate8.is_symlink():
            self.skipTest(
                "retained ignored provenance-input repair evidence is absent "
                "in a clean execution snapshot"
            )
        return generate_gate8._provenance_input_repair_live_values()

    def post_assembly_test_prior_values(
        self,
    ) -> dict[str, tuple[bytes, int]]:
        archive = ROOT / "artifacts/linux/gate8-candidate-ready-test-refresh-v0"
        gate8 = ROOT / "artifacts/gate8"
        if (
            not archive.exists()
            and not archive.is_symlink()
            and not gate8.exists()
            and not gate8.is_symlink()
        ):
            self.skipTest(
                "retained ignored Candidate-ready test-repair evidence is "
                "absent in a clean execution snapshot"
            )
        return generate_gate8._post_assembly_test_archive_values(archive)

    def runtime_test_repair_prior_values(
        self,
    ) -> dict[str, tuple[bytes, int]]:
        archive = (
            ROOT
            / "artifacts/linux/gate8-candidate-ready-runtime-test-refresh-v0"
        )
        gate8 = ROOT / "artifacts/gate8"
        if (
            not archive.exists()
            and not archive.is_symlink()
            and not gate8.exists()
            and not gate8.is_symlink()
        ):
            self.skipTest(
                "retained ignored Candidate-ready runtime-test-repair "
                "evidence is absent in a clean execution snapshot"
            )
        return generate_gate8._runtime_test_repair_archive_values(archive)

    def refresh_receipt(self) -> bytes:
        path = ROOT / "artifacts/linux/verifier-v0.env"
        try:
            return path.read_bytes()
        except FileNotFoundError:
            archive = ROOT / "artifacts/linux/verifier-refresh-c1ef7213-v0"
            gate8 = ROOT / "artifacts/gate8"
            if (
                not archive.exists()
                and not archive.is_symlink()
                and not gate8.exists()
                and not gate8.is_symlink()
            ):
                self.skipTest(
                    "retained ignored verifier-refresh evidence is absent in a "
                    "clean execution snapshot"
                )
            raise

    def test_producer_generate_and_check_clean_candidate_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="m2-gate8-cli-") as directory:
            temporary = Path(directory).resolve()
            candidate = self.private_directory(temporary, "candidate")
            output = self.private_directory(temporary, "receipts")
            receipt = self.receipt("native-python")

            def fake_generation(root: Path) -> generate_gate8.GeneratedGateSeven:
                (root / "generated").write_bytes(b"private\n")
                return generate_gate8.GeneratedGateSeven(
                    object(), {}, b"proof\n", {}
                )

            with (
                mock.patch.object(
                    generate_gate8,
                    "_generate_python_gate_seven",
                    side_effect=fake_generation,
                ),
                mock.patch.object(
                    m2_gate8,
                    "render_producer_receipt",
                    return_value=receipt,
                ),
            ):
                generate_gate8.producer(
                    "generate", "native-python", candidate, output
                )
                self.assertEqual(tuple(candidate.iterdir()), ())
                self.assertEqual(
                    (output / "native-python.json").read_bytes(), receipt
                )
                generate_gate8.producer(
                    "check", "native-python", candidate, output
                )
                self.assertEqual(tuple(candidate.iterdir()), ())

    def test_verifier_refresh_owner_receipt_and_archive_projection_are_exact(self) -> None:
        policy_raw = (ROOT / "spec/gate8-policy-v0.toml").read_bytes()
        refresh_raw = (
            ROOT / "spec/gate8-verifier-refresh-v0.toml"
        ).read_bytes()
        receipt_raw = self.refresh_receipt()
        self.assertEqual(
            hashlib.sha256(policy_raw).hexdigest(),
            "fd53145eeb5d0d5578b8cb1aff980039c999839516528b309a626dd62e52794e",
        )
        self.assertEqual(
            hashlib.sha256(refresh_raw).hexdigest(),
            "8b01c255d948f46ea4fb30b16160af00c416cb087dddc9c62ac768a989772116",
        )
        self.assertEqual(
            m2_gate8.load_gate8_verifier_refresh(refresh_raw)["status"],
            "pre-apply-frozen",
        )
        with self.assertRaises(m2_gate8.Gate8Error):
            m2_gate8.load_gate8_verifier_refresh(refresh_raw + b"\n")
        values = m2_gate8.parse_linux_acquisition_receipt(
            receipt_raw, policy_raw
        )
        self.assertEqual(
            values["image_id"],
            "sha256:1b76a6d672c2d4b875302271f3cd5242200b6dc3d9a8491af611951e498ecd96",
        )
        with self.assertRaises(m2_gate8.Gate8Error):
            m2_gate8.parse_linux_acquisition_receipt(
                receipt_raw + b"\n", policy_raw
            )
        prior = self.refresh_prior_values()
        self.assertEqual(len(prior), 71)
        self.assertEqual(
            sum(len(raw) for raw, _mode in prior.values()), 11_435_789
        )
        self.assertEqual(
            generate_gate8._refresh_payload_sequence(prior),
            "a741dff22f080aa01f790570cf02626e489c669c5ea26c102571a51a0ab1487b",
        )
        manifest = generate_gate8._refresh_manifest(prior)
        self.assertEqual(len(manifest), 11_816)
        self.assertEqual(
            hashlib.sha256(manifest).hexdigest(),
            "b462ef1a05384bb4803b9fe6e1bd4a8b3ce479cc70f0fd8f0083cbe2f59c5d21",
        )
        pending = generate_gate8._render_reopened_roadmap(
            prior["docs/roadmap.md"][0]
        )
        self.assertEqual(len(pending), 189_838)
        self.assertEqual(
            hashlib.sha256(pending).hexdigest(),
            "153f66d0713c04d357c3bf980b3fde1feae328d7751099e5c9bb019c6f98b1f1",
        )

        repair = m2_gate8.load_gate8_verifier_refresh(refresh_raw)[
            "release_repair"
        ]
        self.assertEqual(repair["archive_file_count"], 71)
        self.assertEqual(repair["archive_payload_bytes"], 11_436_098)
        release_prior = self.release_repair_prior_values()
        self.assertEqual(len(release_prior), 71)
        self.assertEqual(
            generate_gate8._release_repair_payload_sequence(release_prior),
            "d76245a7b0d8cfc8071b6a4a68c3da1bb60000e1dfdbccaae62dfcdd35560d9a",
        )
        self.assertEqual(
            hashlib.sha256(
                generate_gate8._release_repair_manifest(release_prior)
            ).hexdigest(),
            "5a1188fd65d9734bc3cb10f912af98dedd2282cd9d57a0d4edb41d8b0ed5d482",
        )

        provenance_prior = self.provenance_input_repair_prior_values()
        self.assertEqual(len(provenance_prior), 71)
        self.assertEqual(
            sum(len(raw) for raw, _mode in provenance_prior.values()),
            11_436_099,
        )
        self.assertEqual(
            generate_gate8._provenance_input_repair_payload_sequence(
                provenance_prior
            ),
            "62e0b1b8bd1cfcfc2733ae207a5be882f991de0080c0c63c9988b71e0eacd2d5",
        )
        provenance_manifest = generate_gate8._provenance_input_repair_manifest(
            provenance_prior
        )
        self.assertEqual(len(provenance_manifest), 11_840)
        self.assertEqual(
            hashlib.sha256(provenance_manifest).hexdigest(),
            "07aed69df68caae925ec29c75433db214fb47f8a1d8b8b1ea524806fde656803",
        )

    def test_clean_linux_release_repair_is_one_way_and_idempotent(self) -> None:
        prior = self.release_repair_prior_values()
        with tempfile.TemporaryDirectory(
            prefix="m2-gate8-release-repair-"
        ) as directory:
            temporary = Path(directory).resolve()
            artifacts = temporary / "artifacts"
            linux = artifacts / "linux"
            reports = temporary / "reports"
            docs = temporary / "docs"
            linux.mkdir(parents=True)
            reports.mkdir()
            docs.mkdir()
            gate8 = artifacts / "gate8"
            gate8.mkdir(mode=0o700)
            for original, (raw, mode) in prior.items():
                if not original.startswith("artifacts/gate8/"):
                    continue
                destination = gate8 / original.removeprefix(
                    "artifacts/gate8/"
                )
                destination.parent.mkdir(
                    mode=0o700, parents=True, exist_ok=True
                )
                destination.write_bytes(raw)
                destination.chmod(mode)
            for path in (
                gate8,
                *(item for item in gate8.rglob("*") if item.is_dir()),
            ):
                path.chmod(0o700)
            report = reports / "m2-feasibility-v0.json"
            roadmap = docs / "roadmap.md"
            acquisition = linux / "verifier-v0.env"
            report.write_bytes(prior["reports/m2-feasibility-v0.json"][0])
            roadmap.write_bytes(prior["docs/roadmap.md"][0])
            acquisition.write_bytes(self.refresh_receipt())
            acquisition.chmod(0o600)
            archive = linux / "gate8-clean-linux-test-refresh-v0"
            patches = {
                "_RELEASE_REPAIR_ARCHIVE": archive,
                "_GATE8_ROOT": gate8,
                "_REPORT_PATH": report,
                "_ROADMAP_PATH": roadmap,
                "_ACQUISITION_PATH": acquisition,
            }
            with (
                mock.patch.multiple(generate_gate8, **patches),
                mock.patch.object(generate_gate8, "_admit_observed_verifier"),
                mock.patch.object(generate_gate8, "_admit_refresh_candidate"),
            ):
                generate_gate8.reopen_clean_linux_tests()
                self.assertFalse(gate8.exists())
                self.assertFalse(report.exists())
                self.assertEqual(
                    hashlib.sha256(roadmap.read_bytes()).hexdigest(),
                    generate_gate8._PENDING_ROADMAP_SHA256,
                )
                self.assertEqual(
                    generate_gate8._release_repair_archive_values(), prior
                )
                before = {
                    path.relative_to(archive).as_posix(): path.stat().st_mtime_ns
                    for path in archive.rglob("*")
                }
                roadmap_time = roadmap.stat().st_mtime_ns
                generate_gate8.reopen_clean_linux_tests()
                after = {
                    path.relative_to(archive).as_posix(): path.stat().st_mtime_ns
                    for path in archive.rglob("*")
                }
                self.assertEqual(after, before)
                self.assertEqual(roadmap.stat().st_mtime_ns, roadmap_time)

    def test_candidate_ready_test_repair_is_one_way_and_idempotent(self) -> None:
        prior = self.post_assembly_test_prior_values()
        with tempfile.TemporaryDirectory(
            prefix="m2-gate8-post-assembly-test-repair-"
        ) as directory:
            temporary = Path(directory).resolve()
            artifacts = temporary / "artifacts"
            linux = artifacts / "linux"
            reports = temporary / "reports"
            docs = temporary / "docs"
            linux.mkdir(parents=True)
            reports.mkdir()
            docs.mkdir()
            gate8 = artifacts / "gate8"
            gate8.mkdir(mode=0o700)
            for original, (raw, mode) in prior.items():
                if not original.startswith("artifacts/gate8/"):
                    continue
                destination = gate8 / original.removeprefix(
                    "artifacts/gate8/"
                )
                destination.parent.mkdir(
                    mode=0o700, parents=True, exist_ok=True
                )
                destination.write_bytes(raw)
                destination.chmod(mode)
            for path in (
                gate8,
                *(item for item in gate8.rglob("*") if item.is_dir()),
            ):
                path.chmod(0o700)
            report = reports / "m2-feasibility-v0.json"
            roadmap = docs / "roadmap.md"
            acquisition = linux / "verifier-v0.env"
            report.write_bytes(prior["reports/m2-feasibility-v0.json"][0])
            roadmap.write_bytes(prior["docs/roadmap.md"][0])
            acquisition.write_bytes(self.refresh_receipt())
            acquisition.chmod(0o600)
            archive = linux / "gate8-candidate-ready-test-refresh-v0"
            patches = {
                "_POST_ASSEMBLY_TEST_ARCHIVE": archive,
                "_GATE8_ROOT": gate8,
                "_REPORT_PATH": report,
                "_ROADMAP_PATH": roadmap,
                "_ACQUISITION_PATH": acquisition,
            }
            with (
                mock.patch.multiple(generate_gate8, **patches),
                mock.patch.object(generate_gate8, "_admit_observed_verifier"),
                mock.patch.object(generate_gate8, "_admit_refresh_candidate"),
            ):
                generate_gate8.reopen_candidate_ready_tests()
                self.assertFalse(gate8.exists())
                self.assertFalse(report.exists())
                self.assertEqual(
                    hashlib.sha256(roadmap.read_bytes()).hexdigest(),
                    generate_gate8._PENDING_ROADMAP_SHA256,
                )
                self.assertEqual(
                    generate_gate8._post_assembly_test_archive_values(), prior
                )
                before = {
                    path.relative_to(archive).as_posix(): path.stat().st_mtime_ns
                    for path in archive.rglob("*")
                }
                roadmap_time = roadmap.stat().st_mtime_ns
                generate_gate8.reopen_candidate_ready_tests()
                after = {
                    path.relative_to(archive).as_posix(): path.stat().st_mtime_ns
                    for path in archive.rglob("*")
                }
                self.assertEqual(after, before)
                self.assertEqual(roadmap.stat().st_mtime_ns, roadmap_time)

    def test_candidate_ready_runtime_test_repair_is_one_way_and_idempotent(
        self,
    ) -> None:
        prior = self.runtime_test_repair_prior_values()
        with tempfile.TemporaryDirectory(
            prefix="m2-gate8-runtime-test-repair-"
        ) as directory:
            temporary = Path(directory).resolve()
            artifacts = temporary / "artifacts"
            linux = artifacts / "linux"
            reports = temporary / "reports"
            docs = temporary / "docs"
            linux.mkdir(parents=True)
            reports.mkdir()
            docs.mkdir()
            gate8 = artifacts / "gate8"
            gate8.mkdir(mode=0o700)
            for original, (raw, mode) in prior.items():
                if not original.startswith("artifacts/gate8/"):
                    continue
                destination = gate8 / original.removeprefix(
                    "artifacts/gate8/"
                )
                destination.parent.mkdir(
                    mode=0o700, parents=True, exist_ok=True
                )
                destination.write_bytes(raw)
                destination.chmod(mode)
            for path in (
                gate8,
                *(item for item in gate8.rglob("*") if item.is_dir()),
            ):
                path.chmod(0o700)
            report = reports / "m2-feasibility-v0.json"
            roadmap = docs / "roadmap.md"
            acquisition = linux / "verifier-v0.env"
            report.write_bytes(prior["reports/m2-feasibility-v0.json"][0])
            roadmap.write_bytes(prior["docs/roadmap.md"][0])
            acquisition.write_bytes(self.refresh_receipt())
            acquisition.chmod(0o600)
            archive = linux / "gate8-candidate-ready-runtime-test-refresh-v0"
            patches = {
                "_RUNTIME_TEST_REPAIR_ARCHIVE": archive,
                "_GATE8_ROOT": gate8,
                "_REPORT_PATH": report,
                "_ROADMAP_PATH": roadmap,
                "_ACQUISITION_PATH": acquisition,
            }
            with (
                mock.patch.multiple(generate_gate8, **patches),
                mock.patch.object(generate_gate8, "_admit_observed_verifier"),
                mock.patch.object(generate_gate8, "_admit_refresh_candidate"),
            ):
                generate_gate8.reopen_candidate_ready_runtime_tests()
                self.assertFalse(gate8.exists())
                self.assertFalse(report.exists())
                self.assertEqual(
                    hashlib.sha256(roadmap.read_bytes()).hexdigest(),
                    generate_gate8._PENDING_ROADMAP_SHA256,
                )
                self.assertEqual(
                    generate_gate8._runtime_test_repair_archive_values(), prior
                )
                before = {
                    path.relative_to(archive).as_posix(): path.stat().st_mtime_ns
                    for path in archive.rglob("*")
                }
                roadmap_time = roadmap.stat().st_mtime_ns
                generate_gate8.reopen_candidate_ready_runtime_tests()
                after = {
                    path.relative_to(archive).as_posix(): path.stat().st_mtime_ns
                    for path in archive.rglob("*")
                }
                self.assertEqual(after, before)
                self.assertEqual(roadmap.stat().st_mtime_ns, roadmap_time)

    def test_candidate_ready_clean_snapshot_test_repair_is_one_way_and_idempotent(
        self,
    ) -> None:
        prior = self.clean_snapshot_test_repair_prior_values()
        with tempfile.TemporaryDirectory(
            prefix="m2-gate8-clean-snapshot-test-repair-"
        ) as directory:
            temporary = Path(directory).resolve()
            artifacts = temporary / "artifacts"
            linux = artifacts / "linux"
            reports = temporary / "reports"
            docs = temporary / "docs"
            linux.mkdir(parents=True)
            reports.mkdir()
            docs.mkdir()
            gate8 = artifacts / "gate8"
            gate8.mkdir(mode=0o700)
            for original, (raw, mode) in prior.items():
                if not original.startswith("artifacts/gate8/"):
                    continue
                destination = gate8 / original.removeprefix(
                    "artifacts/gate8/"
                )
                destination.parent.mkdir(
                    mode=0o700, parents=True, exist_ok=True
                )
                destination.write_bytes(raw)
                destination.chmod(mode)
            for path in (
                gate8,
                *(item for item in gate8.rglob("*") if item.is_dir()),
            ):
                path.chmod(0o700)
            report = reports / "m2-feasibility-v0.json"
            roadmap = docs / "roadmap.md"
            acquisition = linux / "verifier-v0.env"
            report.write_bytes(prior["reports/m2-feasibility-v0.json"][0])
            roadmap.write_bytes(prior["docs/roadmap.md"][0])
            acquisition.write_bytes(self.refresh_receipt())
            acquisition.chmod(0o600)
            archive = (
                linux / "gate8-candidate-ready-clean-snapshot-refresh-v0"
            )
            patches = {
                "_CLEAN_SNAPSHOT_TEST_REPAIR_ARCHIVE": archive,
                "_GATE8_ROOT": gate8,
                "_REPORT_PATH": report,
                "_ROADMAP_PATH": roadmap,
                "_ACQUISITION_PATH": acquisition,
            }
            with (
                mock.patch.multiple(generate_gate8, **patches),
                mock.patch.object(generate_gate8, "_admit_observed_verifier"),
                mock.patch.object(generate_gate8, "_admit_refresh_candidate"),
            ):
                generate_gate8.reopen_candidate_ready_clean_snapshot_tests()
                self.assertFalse(gate8.exists())
                self.assertFalse(report.exists())
                self.assertEqual(
                    hashlib.sha256(roadmap.read_bytes()).hexdigest(),
                    generate_gate8._PENDING_ROADMAP_SHA256,
                )
                self.assertEqual(
                    generate_gate8._clean_snapshot_test_repair_archive_values(),
                    prior,
                )
                before = {
                    path.relative_to(archive).as_posix(): path.stat().st_mtime_ns
                    for path in archive.rglob("*")
                }
                roadmap_time = roadmap.stat().st_mtime_ns
                generate_gate8.reopen_candidate_ready_clean_snapshot_tests()
                after = {
                    path.relative_to(archive).as_posix(): path.stat().st_mtime_ns
                    for path in archive.rglob("*")
                }
                self.assertEqual(after, before)
                self.assertEqual(roadmap.stat().st_mtime_ns, roadmap_time)

    def test_candidate_ready_provenance_input_repair_is_one_way_and_idempotent(
        self,
    ) -> None:
        prior = self.provenance_input_repair_prior_values()
        with tempfile.TemporaryDirectory(
            prefix="m2-gate8-provenance-input-repair-"
        ) as directory:
            temporary = Path(directory).resolve()
            artifacts = temporary / "artifacts"
            linux = artifacts / "linux"
            reports = temporary / "reports"
            docs = temporary / "docs"
            linux.mkdir(parents=True)
            reports.mkdir()
            docs.mkdir()
            gate8 = artifacts / "gate8"
            gate8.mkdir(mode=0o700)
            for original, (raw, mode) in prior.items():
                if not original.startswith("artifacts/gate8/"):
                    continue
                destination = gate8 / original.removeprefix(
                    "artifacts/gate8/"
                )
                destination.parent.mkdir(
                    mode=0o700, parents=True, exist_ok=True
                )
                destination.write_bytes(raw)
                destination.chmod(mode)
            for path in (
                gate8,
                *(item for item in gate8.rglob("*") if item.is_dir()),
            ):
                path.chmod(0o700)
            report = reports / "m2-feasibility-v0.json"
            roadmap = docs / "roadmap.md"
            acquisition = linux / "verifier-v0.env"
            report.write_bytes(prior["reports/m2-feasibility-v0.json"][0])
            roadmap.write_bytes(prior["docs/roadmap.md"][0])
            acquisition.write_bytes(self.refresh_receipt())
            acquisition.chmod(0o600)
            archive = (
                linux
                / "gate8-candidate-ready-provenance-input-refresh-v0"
            )
            patches = {
                "_PROVENANCE_INPUT_REPAIR_ARCHIVE": archive,
                "_GATE8_ROOT": gate8,
                "_REPORT_PATH": report,
                "_ROADMAP_PATH": roadmap,
                "_ACQUISITION_PATH": acquisition,
            }
            with (
                mock.patch.multiple(generate_gate8, **patches),
                mock.patch.object(generate_gate8, "_admit_observed_verifier"),
                mock.patch.object(generate_gate8, "_admit_refresh_candidate"),
            ):
                generate_gate8.reopen_candidate_ready_provenance_input()
                self.assertFalse(gate8.exists())
                self.assertFalse(report.exists())
                self.assertEqual(
                    hashlib.sha256(roadmap.read_bytes()).hexdigest(),
                    generate_gate8._PENDING_ROADMAP_SHA256,
                )
                self.assertEqual(
                    generate_gate8._provenance_input_repair_archive_values(),
                    prior,
                )
                before = {
                    path.relative_to(archive).as_posix(): path.stat().st_mtime_ns
                    for path in archive.rglob("*")
                }
                roadmap_time = roadmap.stat().st_mtime_ns
                generate_gate8.reopen_candidate_ready_provenance_input()
                after = {
                    path.relative_to(archive).as_posix(): path.stat().st_mtime_ns
                    for path in archive.rglob("*")
                }
                self.assertEqual(after, before)
                self.assertEqual(roadmap.stat().st_mtime_ns, roadmap_time)

    def test_candidate_ready_provenance_fixture_repair_is_one_way_and_idempotent(
        self,
    ) -> None:
        archive_source = ROOT / "artifacts/linux/gate8-provenance-fixture-refresh-v0"
        if archive_source.exists() or archive_source.is_symlink():
            prior = generate_gate8._provenance_fixture_repair_archive_values(archive_source)
        elif (
            (ROOT / "artifacts/gate8").exists()
            or (ROOT / "artifacts/gate8").is_symlink()
        ):
            prior = generate_gate8._provenance_fixture_repair_live_values()
        else:
            self.skipTest("retained ignored provenance-fixture repair history is absent")
        with tempfile.TemporaryDirectory(
            prefix="m2-gate8-provenance-fixture-repair-"
        ) as directory:
            temporary = Path(directory).resolve()
            artifacts = temporary / "artifacts"
            linux = artifacts / "linux"
            reports = temporary / "reports"
            docs = temporary / "docs"
            linux.mkdir(parents=True)
            reports.mkdir()
            docs.mkdir()
            gate8 = artifacts / "gate8"
            gate8.mkdir(mode=0o700)
            for original, (raw, mode) in prior.items():
                if not original.startswith("artifacts/gate8/"):
                    continue
                destination = gate8 / original.removeprefix(
                    "artifacts/gate8/"
                )
                destination.parent.mkdir(
                    mode=0o700, parents=True, exist_ok=True
                )
                destination.write_bytes(raw)
                destination.chmod(mode)
            for path in (
                gate8,
                *(item for item in gate8.rglob("*") if item.is_dir()),
            ):
                path.chmod(0o700)
            report = reports / "m2-feasibility-v0.json"
            roadmap = docs / "roadmap.md"
            acquisition = linux / "verifier-v0.env"
            report.write_bytes(prior["reports/m2-feasibility-v0.json"][0])
            roadmap.write_bytes(prior["docs/roadmap.md"][0])
            acquisition.write_bytes(self.refresh_receipt())
            acquisition.chmod(0o600)
            archive = (
                linux
                / "gate8-provenance-fixture-refresh-v0"
            )
            patches = {
                "_PROVENANCE_FIXTURE_REPAIR_ARCHIVE": archive,
                "_GATE8_ROOT": gate8,
                "_REPORT_PATH": report,
                "_ROADMAP_PATH": roadmap,
                "_ACQUISITION_PATH": acquisition,
            }
            with (
                mock.patch.multiple(generate_gate8, **patches),
                mock.patch.object(generate_gate8, "_admit_observed_verifier"),
                mock.patch.object(generate_gate8, "_admit_refresh_candidate"),
            ):
                with (
                    mock.patch.object(generate_gate8, "_install_pending_roadmap",
                                      side_effect=generate_gate8.Gate8CliError("injected")),
                    self.assertRaises(generate_gate8.Gate8CliError),
                ):
                    generate_gate8.reopen_provenance_fixtures()
                self.assertEqual(report.read_bytes(), prior["reports/m2-feasibility-v0.json"][0])
                self.assertEqual(roadmap.read_bytes(), prior["docs/roadmap.md"][0])
                self.assertEqual(generate_gate8._provenance_fixture_repair_archive_values(), prior)
                generate_gate8.reopen_provenance_fixtures()
                self.assertFalse(gate8.exists())
                self.assertFalse(report.exists())
                self.assertEqual(
                    hashlib.sha256(roadmap.read_bytes()).hexdigest(),
                    generate_gate8._PENDING_ROADMAP_SHA256,
                )
                self.assertEqual(
                    generate_gate8._provenance_fixture_repair_archive_values(),
                    prior,
                )
                before = {
                    path.relative_to(archive).as_posix(): path.stat().st_mtime_ns
                    for path in archive.rglob("*")
                }
                roadmap_time = roadmap.stat().st_mtime_ns
                generate_gate8.reopen_provenance_fixtures()
                after = {
                    path.relative_to(archive).as_posix(): path.stat().st_mtime_ns
                    for path in archive.rglob("*")
                }
                self.assertEqual(after, before)
                self.assertEqual(roadmap.stat().st_mtime_ns, roadmap_time)

    def test_verifier_refresh_observed_image_admission_is_exact(self) -> None:
        policy_raw = (ROOT / "spec/gate8-policy-v0.toml").read_bytes()
        receipt_raw = self.refresh_receipt()
        values = m2_gate8.parse_linux_acquisition_receipt(
            receipt_raw, policy_raw
        )
        observed = "\n".join(
            (
                values["image_id"],
                values["platform"],
                values["contract"],
                values["base"],
                "",
            )
        ).encode("ascii")
        real_popen = subprocess.Popen

        def process_for(raw: bytes):
            def start(_arguments: object, **options: object):
                return real_popen(
                    ("printf", "%s", raw.decode("ascii")), **options
                )

            return start

        with mock.patch.object(
            generate_gate8.subprocess,
            "Popen",
            side_effect=process_for(observed),
        ):
            self.assertEqual(
                generate_gate8._admit_observed_verifier(
                    policy_raw, receipt_raw
                ),
                values,
            )
        changed = observed.replace(b"linux/arm64", b"linux/amd64")
        with (
            mock.patch.object(
                generate_gate8.subprocess,
                "Popen",
                side_effect=process_for(changed),
            ),
            self.assertRaises(generate_gate8.Gate8CliError) as rejected,
        ):
            generate_gate8._admit_observed_verifier(policy_raw, receipt_raw)
        self.assertEqual(rejected.exception.reason, "refresh-observed-image")

    def test_verifier_refresh_lifecycle_is_one_way_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="m2-gate8-refresh-") as directory:
            temporary = Path(directory).resolve()
            artifacts = temporary / "artifacts"
            linux = artifacts / "linux"
            reports = temporary / "reports"
            docs = temporary / "docs"
            linux.mkdir(parents=True)
            reports.mkdir()
            docs.mkdir()
            prior = self.refresh_prior_values()
            gate8 = artifacts / "gate8"
            gate8.mkdir(mode=0o700)
            for original, (raw, mode) in prior.items():
                if not original.startswith("artifacts/gate8/"):
                    continue
                destination = gate8 / original.removeprefix("artifacts/gate8/")
                destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                destination.write_bytes(raw)
                destination.chmod(mode)
            for path in (gate8, *(item for item in gate8.rglob("*") if item.is_dir())):
                path.chmod(0o700)
            report = reports / "m2-feasibility-v0.json"
            roadmap = docs / "roadmap.md"
            acquisition = linux / "verifier-v0.env"
            report.write_bytes(prior["reports/m2-feasibility-v0.json"][0])
            roadmap.write_bytes(prior["docs/roadmap.md"][0])
            acquisition.write_bytes(self.refresh_receipt())
            acquisition.chmod(0o600)
            archive = linux / "verifier-refresh-c1ef7213-v0"
            patches = {
                "_REFRESH_ARCHIVE": archive,
                "_GATE8_ROOT": gate8,
                "_REPORT_PATH": report,
                "_ROADMAP_PATH": roadmap,
                "_ACQUISITION_PATH": acquisition,
            }
            with (
                mock.patch.multiple(generate_gate8, **patches),
                mock.patch.object(generate_gate8, "_admit_observed_verifier"),
                mock.patch.object(generate_gate8, "_admit_refresh_candidate"),
            ):
                real_install = generate_gate8._install_pending_roadmap
                with (
                    mock.patch.object(
                        generate_gate8,
                        "_install_pending_roadmap",
                        side_effect=generate_gate8.Gate8CliError("injected"),
                    ),
                    self.assertRaises(generate_gate8.Gate8CliError),
                ):
                    generate_gate8.reopen_verifier()
                self.assertEqual(
                    hashlib.sha256(roadmap.read_bytes()).hexdigest(),
                    generate_gate8._PRIOR_ROADMAP_SHA256,
                )
                self.assertTrue(archive.is_dir())
                self.assertTrue(gate8.is_dir())
                self.assertTrue(report.is_file())

                with (
                    mock.patch.object(
                        generate_gate8,
                        "_install_pending_roadmap",
                        side_effect=real_install,
                    ),
                    mock.patch.object(
                        generate_gate8,
                        "_remove_prior_outputs",
                        side_effect=generate_gate8.Gate8CliError("injected"),
                    ),
                    self.assertRaises(generate_gate8.Gate8CliError),
                ):
                    generate_gate8.reopen_verifier()
                self.assertEqual(
                    hashlib.sha256(roadmap.read_bytes()).hexdigest(),
                    generate_gate8._PENDING_ROADMAP_SHA256,
                )
                self.assertTrue(gate8.is_dir())
                self.assertTrue(report.is_file())

                generate_gate8.reopen_verifier()
                self.assertFalse(gate8.exists())
                self.assertFalse(report.exists())
                self.assertTrue(archive.is_dir())
                before = {
                    path.relative_to(archive).as_posix(): path.stat().st_mtime_ns
                    for path in archive.rglob("*")
                }
                roadmap_time = roadmap.stat().st_mtime_ns
                generate_gate8.reopen_verifier()
                after = {
                    path.relative_to(archive).as_posix(): path.stat().st_mtime_ns
                    for path in archive.rglob("*")
                }
                self.assertEqual(after, before)
                self.assertEqual(roadmap.stat().st_mtime_ns, roadmap_time)

                archived_file = next(
                    path for path in archive.rglob("*") if path.is_file()
                )
                alias = temporary / "archive-alias"
                os.link(archived_file, alias)
                with self.assertRaises(generate_gate8.Gate8CliError) as alias_error:
                    generate_gate8.reopen_verifier()
                self.assertEqual(alias_error.exception.exit_code, 2)
                alias.unlink()

                extra = archive / "unexpected"
                extra.write_bytes(b"extra\n")
                extra.chmod(0o600)
                with self.assertRaises(generate_gate8.Gate8CliError) as archive_error:
                    generate_gate8.reopen_verifier()
                self.assertEqual(archive_error.exception.exit_code, 3)
                extra.unlink()

                tomb = gate8.parent / ".gate8-verifier-refresh-remove-v0"
                tomb.mkdir(mode=0o700)
                tree_path, (tree_raw, tree_mode) = next(
                    (path.removeprefix("artifacts/gate8/"), item)
                    for path, item in generate_gate8._archive_values(archive).items()
                    if path.startswith("artifacts/gate8/")
                )
                tomb_file = tomb / tree_path
                tomb_file.parent.mkdir(mode=0o700, parents=True)
                for parent in tomb_file.parents:
                    if parent == tomb.parent:
                        break
                    parent.chmod(0o700)
                tomb_file.write_bytes(tree_raw)
                tomb_file.chmod(tree_mode)
                generate_gate8.reopen_verifier()
                self.assertFalse(tomb.exists())

    def test_reopen_cli_grammar_and_acquire_guard_are_fail_closed(self) -> None:
        for arguments in (
            ["reopen-verifier", "--help"],
            ["reopen-verifier", "unexpected"],
            ["reopen-clean-linux-tests", "--help"],
            ["reopen-clean-linux-tests", "unexpected"],
            ["reopen-candidate-ready-tests", "--help"],
            ["reopen-candidate-ready-tests", "unexpected"],
            ["reopen-candidate-ready-runtime-tests", "--help"],
            ["reopen-candidate-ready-runtime-tests", "unexpected"],
            ["reopen-candidate-ready-clean-snapshot-tests", "--help"],
            ["reopen-candidate-ready-clean-snapshot-tests", "unexpected"],
            ["reopen-candidate-ready-provenance-input", "--help"],
            ["reopen-candidate-ready-provenance-input", "unexpected"],
            ["reopen-provenance-fixtures", "--help"],
            ["reopen-provenance-fixtures", "unexpected"],
        ):
            with (
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as rejected,
            ):
                generate_gate8._arguments(arguments)
            self.assertEqual(rejected.exception.code, 2)
        with tempfile.TemporaryDirectory(prefix="m2-acquire-guard-") as directory:
            temporary = Path(directory)
            marker = temporary / "docker-called"
            docker = temporary / "docker"
            docker.write_bytes(
                b"#!/bin/sh\nprintf called > '"
                + os.fsencode(marker)
                + b"'\nexit 99\n"
            )
            docker.chmod(0o755)
            environment = dict(os.environ)
            environment["PATH"] = os.fspath(temporary)
            completed = subprocess.run(
                ("/bin/sh", "tools/linux/acquire.sh"),
                cwd=ROOT,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=10,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertFalse(marker.exists())
            self.assertIn(b"explicit refresh owner required", completed.stderr)

    def test_phase_check_is_write_free_and_cleans_generated_entries(self) -> None:
        with tempfile.TemporaryDirectory(prefix="m2-gate8-phase-") as directory:
            candidate = self.private_directory(Path(directory).resolve(), "candidate")

            def fake_generation(root: Path) -> generate_gate8.GeneratedGateSeven:
                (root / "candidate-manifest.json").write_bytes(b"private\n")
                return generate_gate8.GeneratedGateSeven(
                    object(), {}, b"proof\n", {}
                )

            with (
                mock.patch.object(generate_gate8, "_phase_outputs_absent"),
                mock.patch.object(
                    generate_gate8,
                    "_generate_python_gate_seven",
                    side_effect=fake_generation,
                ),
            ):
                generate_gate8.phase_check("pre-gate8-clean", candidate)
            self.assertEqual(tuple(candidate.iterdir()), ())

    def test_linux_input_is_exact_and_hardlinks_reject(self) -> None:
        source_raw = canonical_manifest.serialize_manifest(
            {
                "entries": [
                    {
                        "byte_length": 1,
                        "mode": "100644",
                        "path": "fixture",
                        "sha256": hashlib.sha256(b"x").hexdigest(),
                    }
                ],
                "roadmap_normative_sha256": "1" * 64,
                "schema": "m2-evidence-source-v0",
            }
        )
        with tempfile.TemporaryDirectory(prefix="m2-gate8-linux-") as directory:
            temporary = Path(directory).resolve()
            receipt_root = self.private_directory(temporary, "receipts")
            output = self.private_directory(temporary, "output")
            native_python = receipt_root / "native-python.json"
            native_rust = receipt_root / "native-rust.json"
            native_python.write_bytes(self.receipt("native-python"))
            native_rust.write_bytes(self.receipt("native-rust"))
            with (
                mock.patch.object(
                    m2_gate8,
                    "build_evidence_source_projection",
                    return_value=source_raw,
                ),
                mock.patch.object(m2_gate8, "validate_gate8_source_surface"),
            ):
                generate_gate8.prepare_linux_input(
                    "release-fresh", native_python, native_rust, output
                )
            self.assertEqual(
                {path.name for path in output.iterdir()},
                {"input-manifest.json", "native-python.json", "native-rust.json"},
            )
            m2_gate8.validate_linux_verification_input(
                (output / "input-manifest.json").read_bytes(),
                source_raw,
                {
                    "native-python": native_python.read_bytes(),
                    "native-rust": native_rust.read_bytes(),
                },
            )

            linked_root = self.private_directory(temporary, "linked-output")
            alias = receipt_root / "native-rust-alias.json"
            os.link(native_rust, alias)
            with self.assertRaises(generate_gate8.Gate8CliError) as hardlink:
                generate_gate8.prepare_linux_input(
                    "release-fresh", native_python, alias, linked_root
                )
            self.assertEqual(hardlink.exception.reason, "linux-input-receipt")
            alias.unlink()

            rollback_root = self.private_directory(temporary, "rollback-output")
            real_rename_noreplace = generate_gate8._rename_noreplace
            replacements = 0

            def fail_second_replace(source: Path, destination: Path) -> None:
                nonlocal replacements
                replacements += 1
                if replacements == 2:
                    raise OSError("injected")
                real_rename_noreplace(source, destination)

            with (
                mock.patch.object(
                    generate_gate8,
                    "_rename_noreplace",
                    side_effect=fail_second_replace,
                ),
                mock.patch.object(
                    m2_gate8,
                    "build_evidence_source_projection",
                    return_value=source_raw,
                ),
                mock.patch.object(m2_gate8, "validate_gate8_source_surface"),
                self.assertRaises(generate_gate8.Gate8CliError) as rollback,
            ):
                generate_gate8.prepare_linux_input(
                    "release-fresh", native_python, native_rust, rollback_root
                )
            self.assertEqual(rollback.exception.reason, "linux-input-write")
            self.assertEqual(tuple(rollback_root.iterdir()), ())

    def test_assembly_tree_is_report_last_idempotent_and_rolls_back(self) -> None:
        tree = {
            f"group-{index // 10}/file-{index:02d}.bin": (
                f"value-{index}\n".encode(),
                0o755 if index == 0 else 0o644,
            )
            for index in range(69)
        }
        report = canonical_manifest.serialize_manifest(
            {"schema": "m2-feasibility-v0"}
        )
        pre_roadmap = (ROOT / "docs/roadmap.md").read_bytes()
        policy = m2_gate8.load_gate8_policy(
            (ROOT / "spec/gate8-policy-v0.toml").read_bytes()
        )
        transition = policy["roadmap_transition"]
        pending_sentence = transition["pre_gate8_terminal_sentence"].encode()
        if b"| Project state | Candidate ready |\n" in pre_roadmap:
            lines = pre_roadmap.splitlines(keepends=True)
            prefix = "| M2 — Full-carrier bootstrap and transport feasibility | ".encode()
            rows = [i for i, line in enumerate(lines) if line.startswith(prefix)]
            self.assertEqual(len(rows), 1)
            row = lines[rows[0]]
            start = row.index(b"The candidate passes gates 1")
            self.assertTrue(row.endswith(b" |\n"))
            lines[rows[0]] = (
                row[:start].replace(
                    "Candidate ready — independent validation pending".encode(),
                    b"In progress", 1,
                ) + pending_sentence + b" |\n"
            )
            pre_roadmap = b"".join(lines).replace(
                b"| Project state | Candidate ready |\n",
                b"| Project state | In progress |\n", 1,
            )
        self.assertEqual(
            hashlib.sha256(pre_roadmap).hexdigest(),
            "153f66d0713c04d357c3bf980b3fde1feae328d7751099e5c9bb019c6f98b1f1",
        )
        assembly = generate_gate8.Gate8Assembly(tree, report)
        with tempfile.TemporaryDirectory(prefix="m2-gate8-assembly-") as directory:
            temporary = Path(directory).resolve()
            output = temporary / "gate8"
            report_path = temporary / "report.json"
            roadmap_path = temporary / "roadmap.md"
            roadmap_path.write_bytes(pre_roadmap)
            generate_gate8._install_assembly(
                "generate", output, report_path, roadmap_path, assembly
            )
            generate_gate8._install_assembly(
                "check", output, report_path, roadmap_path, assembly
            )
            self.assertEqual(report_path.read_bytes(), report)
            m2_gate8.validate_candidate_ready_roadmap(
                roadmap_path.read_bytes(), report
            )
            (output / "extra").write_bytes(b"extra\n")
            with self.assertRaises(generate_gate8.Gate8CliError) as extra:
                generate_gate8._install_assembly(
                    "check", output, report_path, roadmap_path, assembly
                )
            self.assertEqual(extra.exception.reason, "gate8-tree-mismatch")
            (output / "extra").unlink()
            (output / "empty-extra").mkdir(mode=0o700)
            with self.assertRaises(generate_gate8.Gate8CliError) as directory:
                generate_gate8._install_assembly(
                    "check", output, report_path, roadmap_path, assembly
                )
            self.assertEqual(directory.exception.reason, "gate8-tree-mismatch")

        with tempfile.TemporaryDirectory(prefix="m2-gate8-rollback-") as directory:
            temporary = Path(directory).resolve()
            output = temporary / "gate8"
            report_path = temporary / "report.json"
            roadmap_path = temporary / "roadmap.md"
            roadmap_path.write_bytes(pre_roadmap)
            real_rename_noreplace = generate_gate8._rename_noreplace

            def fail_report(source: Path, destination: Path) -> None:
                if Path(destination) == report_path:
                    raise OSError("injected")
                real_rename_noreplace(source, destination)

            with (
                mock.patch.object(
                    generate_gate8,
                    "_rename_noreplace",
                    side_effect=fail_report,
                ),
                self.assertRaises(generate_gate8.Gate8CliError),
            ):
                generate_gate8._install_assembly(
                    "generate", output, report_path, roadmap_path, assembly
                )
            self.assertFalse(report_path.exists())
            self.assertFalse(output.exists())
            self.assertEqual(roadmap_path.read_bytes(), pre_roadmap)

        with tempfile.TemporaryDirectory(prefix="m2-gate8-race-") as directory:
            temporary = Path(directory).resolve()
            output = temporary / "gate8"
            report_path = temporary / "report.json"
            roadmap_path = temporary / "roadmap.md"
            roadmap_path.write_bytes(pre_roadmap)
            real_rename_noreplace = generate_gate8._rename_noreplace

            def race_report(source: Path, destination: Path) -> None:
                if destination == report_path:
                    destination.write_bytes(b"raced\n")
                real_rename_noreplace(source, destination)

            with (
                mock.patch.object(
                    generate_gate8,
                    "_rename_noreplace",
                    side_effect=race_report,
                ),
                self.assertRaises(generate_gate8.Gate8CliError) as raced,
            ):
                generate_gate8._install_assembly(
                    "generate", output, report_path, roadmap_path, assembly
                )
            self.assertEqual(raced.exception.reason, "assembly-publish-race")
            self.assertFalse(output.exists())
            self.assertEqual(report_path.read_bytes(), b"raced\n")
            self.assertEqual(roadmap_path.read_bytes(), pre_roadmap)

        with tempfile.TemporaryDirectory(prefix="m2-gate8-fsync-") as directory:
            temporary = Path(directory).resolve()
            output = temporary / "gate8"
            report_path = temporary / "report.json"
            roadmap_path = temporary / "roadmap.md"
            roadmap_path.write_bytes(pre_roadmap)
            real_fsync_directory = generate_gate8._fsync_directory
            parent_fsyncs = 0

            def fail_backup_removal_fsync(path: Path) -> None:
                nonlocal parent_fsyncs
                if path == temporary:
                    parent_fsyncs += 1
                    if parent_fsyncs == 6:
                        raise generate_gate8.Gate8CliError("injected-fsync")
                real_fsync_directory(path)

            with (
                mock.patch.object(
                    generate_gate8,
                    "_fsync_directory",
                    side_effect=fail_backup_removal_fsync,
                ),
                self.assertRaises(generate_gate8.Gate8CliError) as fsync,
            ):
                generate_gate8._install_assembly(
                    "generate", output, report_path, roadmap_path, assembly
                )
            self.assertEqual(fsync.exception.reason, "injected-fsync")
            self.assertFalse(output.exists())
            self.assertFalse(report_path.exists())
            self.assertEqual(roadmap_path.read_bytes(), pre_roadmap)

    def test_gate8_tree_writer_keeps_every_nested_directory_private(self) -> None:
        with tempfile.TemporaryDirectory(prefix="m2-gate8-nested-") as directory:
            root = Path(directory).resolve()
            root.chmod(0o700)
            expected = {
                f"nested/deeper/artifact-{ordinal:02d}.json": (
                    canonical_manifest.serialize_manifest(
                        {"ordinal": ordinal, "schema": "test-v0"}
                    ),
                    0o644,
                )
                for ordinal in range(69)
            }
            generate_gate8._write_tree(root, expected)
            generate_gate8._validate_tree(root, expected)
            directories = [path for path in root.rglob("*") if path.is_dir()]
            self.assertTrue(directories)
            self.assertTrue(
                all(path.stat().st_mode & 0o777 == 0o700 for path in directories)
            )

    def test_work_and_output_role_aliases_reject_before_generation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="m2-gate8-alias-") as directory:
            temporary = Path(directory).resolve()
            shared = self.private_directory(temporary, "shared")
            with (
                mock.patch.object(
                    generate_gate8,
                    "_generate_python_gate_seven",
                    side_effect=AssertionError("generation started"),
                ),
                self.assertRaises(generate_gate8.Gate8CliError) as producer,
            ):
                generate_gate8.producer(
                    "generate", "native-python", shared, shared
                )
            self.assertEqual(producer.exception.reason, "producer-root-alias")

            report = temporary / "report.json"
            with self.assertRaises(generate_gate8.Gate8CliError) as assembly:
                generate_gate8.assemble(
                    "generate", shared, shared, shared, report
                )
            self.assertEqual(assembly.exception.reason, "assembly-target")

            with self.assertRaises(generate_gate8.Gate8CliError) as linux:
                generate_gate8.verify_linux(shared, shared, shared, shared)
            self.assertEqual(linux.exception.reason, "linux-work-root")


if __name__ == "__main__":
    unittest.main()
