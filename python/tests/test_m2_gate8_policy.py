from __future__ import annotations

import hashlib
from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "spec" / "gate8-policy-v0.toml"
REFRESH_PATH = ROOT / "spec" / "gate8-verifier-refresh-v0.toml"
CANDIDATE_ID = "eh72-hier-r5-r2-r1-crc32c-v0"


class M2Gate8PolicyContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = POLICY_PATH.read_bytes()
        cls.policy = tomllib.loads(cls.raw.decode("utf-8"))
        cls.refresh_raw = REFRESH_PATH.read_bytes()
        cls.refresh = tomllib.loads(cls.refresh_raw.decode("utf-8"))

    def test_pre_gate8_owner_has_no_gate8_outcome(self) -> None:
        policy = self.policy
        self.assertEqual(policy["schema"], "golden-board.m2-gate8-policy/v0")
        self.assertEqual(policy["status"], "pre-gate8-frozen")
        self.assertEqual(policy["candidate_id"], CANDIDATE_ID)
        self.assertIs(policy["outcome_values_present"], False)
        self.assertIn("reopened-gate8-run", policy["status_scope"])
        self.assertIn("environment-bindings-not-outcomes", policy["outcome_values_scope"])
        self.assertTrue(self.raw.endswith(b"\n"))
        self.assertNotRegex(
            self.raw.decode("utf-8"),
            r"(?<!sha256:)(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])",
        )
        self.assertEqual(
            self.refresh["schema"], "golden-board.m2-gate8-verifier-refresh/v0"
        )
        self.assertIs(self.refresh["candidate_outcome_values_present"], False)
        self.assertIs(self.refresh["historical_output_identity_values_present"], True)
        self.assertIs(self.refresh["new_gate8_output_identity_values_present"], False)
        self.assertTrue(self.refresh_raw.endswith(b"\n"))
        self.assertEqual(
            self.refresh["authority"]["gate8_policy_sha256"],
            f"sha256:{hashlib.sha256(self.raw).hexdigest()}",
        )

    def test_gate_roles_and_cross_language_preimages_are_closed(self) -> None:
        policy = self.policy
        projections = policy["owner_projection"]["role"]
        self.assertEqual(
            [row["role_id"] for row in projections],
            [
                "parameter_manifest",
                "known_answer_manifest",
                "shell_manifest",
                "recipe_manifest",
                "grammar_state_manifest",
                "work_scratch_ledger",
                "profile_limits_derivation",
                "side_search_policy",
            ],
        )
        for row in projections:
            self.assertTrue(row["source_paths"])
            self.assertEqual(len(row["source_paths"]), len(set(row["source_paths"])))

        cross = policy["cross_language_manifest"]
        receipt = policy["producer_receipt"]
        self.assertEqual(cross["artifact_ids"], receipt["artifact_ids"])
        self.assertEqual(
            receipt["producer_ids"],
            ["native-python", "native-rust", "linux-python", "linux-rust"],
        )
        self.assertIn("candidate-under-test", cross["candidate_manifest_sha256_field"])
        self.assertEqual(policy["damage_inventory"]["file_count"], 72)
        self.assertEqual(sum(policy["damage_inventory"]["shard_counts_by_family"]), 63)
        self.assertIn("retained-gate6-files", policy["damage_inventory"]["shortcuts"])

    def test_selection_and_damage_rows_resolve_the_v0_conflicts(self) -> None:
        selection = self.policy["selection"]
        self.assertEqual(
            selection["selection_row_keys"],
            ["step", "surviving_before", "outcome", "evidence_sha256"],
        )
        self.assertNotIn("ordinal", selection["selection_row_keys"])
        self.assertNotIn("rule_id", selection["selection_row_keys"])
        base = tomllib.loads((ROOT / "spec/profile-policy-v0.toml").read_text())
        self.assertEqual(selection["selection_row_keys"], base["selection_row"]["keys"])
        self.assertEqual(selection["step_order"], base["selection_row"]["step_order"])
        damage = self.policy["damage_row"]
        self.assertIn("damage-{family_id}.json", damage["manifest_preimage"])
        self.assertIn("never-the-root-manifest-or-a-shard", damage["manifest_preimage"])

    def test_bundle_paths_preimages_releases_and_bounds_are_closed(self) -> None:
        policy = self.policy
        total_dynamic = 0
        for bundle_name in ("technical_bundle", "learner_bundle"):
            bundle = policy[bundle_name]
            roles = [*bundle["participant_roles"], *bundle["evaluator_roles"]]
            self.assertEqual(set(bundle["role_paths"]), set(roles))
            self.assertEqual(set(bundle["role_preimages"]), set(roles))
            self.assertEqual(len(roles), len(set(roles)))
            total_dynamic += len(roles)
            for role, path in bundle["role_paths"].items():
                self.assertFalse(path.startswith("/"), role)
                self.assertNotIn("..", path.split("/"), role)
                prefix = "participant/" if role in bundle["participant_roles"] else "evaluator/"
                self.assertTrue(path.startswith(prefix), (role, path))
            released = []
            for ordinal in range(len(bundle["release_ids"])):
                released.extend(bundle[f"release_{ordinal}_roles"])
            self.assertEqual(released, bundle["participant_roles"])
        self.assertEqual(total_dynamic, policy["phase_paths"]["gate8_dynamic_file_count"])
        fixed = policy["phase_paths"]["gate8_exact_files"]
        self.assertEqual(
            len(fixed) + total_dynamic,
            policy["phase_paths"]["gate8_total_regular_file_count"],
        )
        self.assertEqual(
            policy["learner_bundle"]["role_preimages"]["runner"],
            "generated:complete-raw-tools/m2/learner_runner.py-bytes",
        )
        self.assertEqual(policy["technical_bundle"]["mode_override_roles"], [])
        self.assertEqual(policy["learner_bundle"]["mode_override_roles"], ["runner"])
        self.assertEqual(policy["learner_bundle"]["role_modes"], {"runner": "100755"})
        common = policy["bundle_common"]
        self.assertEqual(common["file_bytes_max"], 4_161_602)
        self.assertEqual(
            common["largest_required_file_roles"],
            [
                "technical:unknown-error-observation",
                "technical:known-erasure-observation",
            ],
        )
        self.assertIn("2-plus2040-times2040", common["largest_required_file_formula"])
        self.assertEqual(common["aggregate_file_bytes_max"], 67_108_864)
        self.assertIn("8323204", common["aggregate_bound_rule"])

        templates = policy["tracked_templates"]["paths"]
        surface = policy["implementation_surface"]
        self.assertEqual(len(templates), surface["tracked_template_count"])
        self.assertEqual(
            surface["tracked_gate8_support_count"],
            len(templates) + len(policy["tracked_gate8_tools"]["paths"]),
        )
        self.assertEqual(
            surface["candidate_ready_additional_required_paths"],
            [
                "crates/gb-bootstrap/src/bin/gb-m2-gate8.rs",
                "tools/m2/generate_gate8.py",
                "tools/m2/learner_runner.py",
            ],
        )

        heldout = policy["learner_heldout_request"]
        self.assertEqual(heldout["start_node_id"], 28)
        self.assertIs(heldout["label_suppressed"], True)
        expected = policy["learner_expected"]
        self.assertEqual(expected["semantic_path_owner"], "spec/runner-v0.md-section-4")
        self.assertEqual(expected["heldout_commitment_node_id"], 28)
        self.assertEqual(expected["heldout_commitment_response_hex"], "03000200030001")
        self.assertIn("no-wrapper", expected["heldout_commitment_preimage"])

    def test_producer_and_assembly_cli_grammars_are_closed(self) -> None:
        producer = self.policy["producer_cli"]
        self.assertEqual(producer["python_entrypoint"], "tools/m2/generate_gate8.py")
        self.assertEqual(producer["rust_entrypoint"], "gb-m2-gate8")
        self.assertEqual(producer["python_producer_ids"], ["native-python", "linux-python"])
        self.assertEqual(producer["rust_producer_ids"], ["native-rust", "linux-rust"])
        self.assertEqual(
            producer["native_allowed_names"],
            [
                f"{producer_id}.json"
                for producer_id in self.policy["producer_receipt"]["producer_ids"]
            ],
        )
        self.assertEqual(
            producer["linux_allowed_names"],
            self.policy["producer_receipt"]["linux_receipt_allowed_names"],
        )
        self.assertEqual(producer["exit_codes"], [0, 2, 3])
        self.assertIn("{absolute-candidate-root}", producer["argv_order"])
        self.assertIn("existing-empty-private-mode-0700", producer["candidate_root"])
        self.assertIn("internally-generates", producer["candidate_root"])
        self.assertIn("exact-empty-state", producer["candidate_root_cleanup"])
        self.assertIn("other-language-runtime", self.policy["producer_receipt"]["implementation_independence"])
        self.assertIn("run_damage", self.policy["producer_receipt"]["python_generation"])
        self.assertIn("profile-version-2-3-4-5-and6", self.policy["producer_receipt"]["legacy_package_generation"])
        self.assertIn("only-the-profile-version-3-route-prefix", self.policy["producer_receipt"]["legacy_route_prefix_generation"])
        self.assertIn("not-applicable", self.policy["producer_receipt"]["legacy_route_prefix_generation"])
        self.assertIn("dump_eh_package", self.policy["producer_receipt"]["python_legacy_fixture_builder"])
        self.assertIn("profile-version-3", self.policy["producer_receipt"]["d7_route_conflict_fixture"])
        self.assertIn("comparison-only", self.policy["producer_receipt"]["retained_legacy_fixture_use"])

        assembly = self.policy["assembly_cli"]
        self.assertEqual(assembly["entrypoint"], producer["python_entrypoint"])
        self.assertEqual(assembly["subcommand"], "assemble")
        self.assertIn("existing-empty-private-mode-0700", assembly["candidate_root"])
        self.assertIn("internally-regenerates", assembly["candidate_root"])
        self.assertIn("exact-empty-state", assembly["candidate_root_cleanup"])
        self.assertIn("report-last", assembly["generate_rule"])
        self.assertIn("roadmap-status-last", assembly["generate_rule"])
        self.assertIn("exact-source-root/artifacts/gate8", assembly["canonical_target_rule"])

        reopen = self.refresh["reopen_cli"]
        self.assertEqual(reopen["entrypoint"], producer["python_entrypoint"])
        self.assertEqual(reopen["subcommand"], "reopen-verifier")
        self.assertEqual(reopen["argv_order"], ["reopen-verifier"])
        self.assertIn("no-network-docker-build", reopen["forbidden"])
        self.assertIn("unknown_option_or_positional_argument", reopen)

        phase = self.policy["phase_check_cli"]
        self.assertEqual(phase["subcommand"], "phase-check")
        self.assertEqual(phase["phase_values"], ["pre-gate8-clean"])
        self.assertIn("regenerate-and-strictly-validate", phase["operation"])
        self.assertIn("no-receipt", phase["forbidden_outputs"])

        linux_input = self.policy["linux_verification_input"]
        self.assertEqual(linux_input["container_mount"], "/gate8-native-input")
        self.assertEqual(
            linux_input["file_names"],
            ["input-manifest.json", "native-python.json", "native-rust.json"],
        )
        self.assertEqual(
            linux_input["native_producer_order"],
            ["native-python", "native-rust"],
        )
        self.assertIn("source-projection-binding", linux_input["container_admission"])
        self.assertIn("never-derives", linux_input["native_receipt_substitution"])
        provenance_input = self.policy[
            "candidate_ready_linux_provenance_input"
        ]
        self.assertEqual(
            provenance_input["host_path"],
            "artifacts/linux/verifier-v0.env",
        )
        self.assertEqual(
            provenance_input["container_mount"],
            "/gate8-verifier-input",
        )
        self.assertEqual(provenance_input["container_mount_mode"], "read-only-file")
        self.assertEqual(provenance_input["byte_length"], 378)
        self.assertIn(
            "after-execution-snapshot-verification",
            provenance_input["installation_order"],
        )
        self.assertIn(
            "execution-snapshot-identity-remains-exactly-equal",
            provenance_input["post_installation_check"],
        )
        input_cli = self.policy["linux_input_cli"]
        self.assertEqual(input_cli["subcommand"], "prepare-linux-input")
        self.assertEqual(input_cli["mode_values"], ["release-fresh", "standalone-retained"])
        self.assertIn("{absolute-native-python-receipt}", input_cli["argv_order"])
        self.assertIn("{absolute-native-rust-receipt}", input_cli["argv_order"])
        self.assertIn("exact-three-file-set", input_cli["operation"])

        linux = self.policy["candidate_ready_linux_cli"]
        self.assertEqual(linux["subcommand"], "verify-linux")
        self.assertIn("/gate8-native-input", linux["argv_order"])
        self.assertIn("/gate8-output", linux["argv_order"])
        self.assertIn("do-not-open", linux["tracked_report_read_barrier"])
        self.assertIn("complete-tracked-report-bytes", linux["comparison"])
        self.assertIn("forbidden", linux["retained_gate8_use"])
        modes = self.policy["linux_entry_modes"]
        self.assertIn("git-plus-declared-container-runtime-only", modes["candidate_ready_standalone"])
        self.assertIn("fresh-native-python", modes["candidate_ready_release"])
        self.assertIn("tracked-report-read-barrier", modes["common_linux_work"])
        self.assertIn("only-candidate-ready-command", modes["release_scope"])
        self.assertIn(
            "standalone-retained-input-evidence",
            self.policy["linux_source_surface"]["transient_verification_input"],
        )
        self.assertIn(
            "exact-byte-equality-with-the-retained-linux-receipts",
            self.policy["producer_receipt"]["linux_receipt_return_rule"],
        )
        self.assertIn(
            "standalone-linux-uses-only-the-two-canonical-retained-native-receipts",
            self.policy["admission"]["linux_native_receipt_source"],
        )

    def test_report_linux_and_lifecycle_bindings_are_exact(self) -> None:
        policy = self.policy
        owners = policy["report_r3_overlay"]["normative_owner_paths"]
        for required in (
            "spec/bootstrap-v1.md",
            "spec/profile-policy-v1.toml",
            "spec/damage-policy-v1.toml",
            "spec/route-data-v1.json",
            "spec/profile-limits-v1.toml",
            "spec/m2-r3-owner-promotion-v1.toml",
            "conformance/m2-r3-owner-v1.json",
            "spec/runner-v0.md",
            "spec/slice-v0.md",
            "spec/gate8-policy-v0.toml",
            "spec/gate8-verifier-refresh-v0.toml",
        ):
            self.assertIn(required, owners)
        self.assertEqual(
            policy["report_r3_overlay"]["permitted_administrative_counts_before_human_validation"],
            [],
        )
        self.assertEqual(policy["technical_bundle"]["recipient_mode"], "individual")
        self.assertEqual(policy["technical_bundle"]["recipient_headcount"], 1)
        self.assertIs(policy["admission"]["participant_contact_authorized"], False)
        self.assertEqual(
            policy["linux_attestation"]["image_digest"],
            "sha256:1b76a6d672c2d4b875302271f3cd5242200b6dc3d9a8491af611951e498ecd96",
        )
        acquisition = policy["linux_acquisition_receipt"]
        self.assertEqual(acquisition["byte_length"], 378)
        self.assertEqual(
            acquisition["sha256"],
            "sha256:315f9021f83ee8c6640af6ea6bcd58387287bcef42e7b27eaaf5f76b2187f6a2",
        )
        self.assertEqual(
            acquisition["key_order"],
            [
                "schema",
                "image",
                "image_id",
                "platform",
                "contract",
                "base",
                "dockerfile_sha256",
            ],
        )
        self.assertEqual(acquisition["image_id"], policy["linux_attestation"]["image_digest"])
        receipt_values = {
            key: acquisition[key] for key in acquisition["key_order"]
        }
        receipt_values["dockerfile_sha256"] = receipt_values[
            "dockerfile_sha256"
        ].removeprefix("sha256:")
        receipt_bytes = "".join(
            f"{key}={receipt_values[key]}\n" for key in acquisition["key_order"]
        ).encode("ascii")
        self.assertEqual(len(receipt_bytes), acquisition["byte_length"])
        self.assertEqual(
            f"sha256:{hashlib.sha256(receipt_bytes).hexdigest()}",
            acquisition["sha256"],
        )
        self.assertIn("docker-image-inspect", acquisition["observed_image_admission"])
        self.assertIn("not-claimed-to-be-reproducible", acquisition["identity_semantics"])
        refresh = self.refresh
        self.assertEqual(refresh["new_acquisition"]["image_digest"], acquisition["image_id"])
        self.assertEqual(refresh["new_acquisition"]["receipt_sha256"], acquisition["sha256"])
        clean_snapshot_repair = refresh[
            "candidate_ready_clean_snapshot_test_repair"
        ]
        self.assertEqual(clean_snapshot_repair["status"], "pre-apply-frozen")
        self.assertEqual(
            clean_snapshot_repair["prior_report_sha256"],
            "sha256:4e039eb356a2153d86cf1a5d4db5af2aa7d15f64bce97902cd11d0e6bcb135a8",
        )
        self.assertEqual(
            clean_snapshot_repair["prior_roadmap_sha256"],
            "sha256:b1f884836b76b08b505a33fc66549a4b0ea3462820401ed1661834717599044e",
        )
        self.assertEqual(clean_snapshot_repair["archive_file_count"], 71)
        self.assertEqual(clean_snapshot_repair["archive_payload_bytes"], 11_436_099)
        self.assertEqual(clean_snapshot_repair["archive_manifest_bytes"], 11_838)
        self.assertEqual(
            clean_snapshot_repair["subcommand"],
            "reopen-candidate-ready-clean-snapshot-tests",
        )
        self.assertIn(
            "both-wholly-absent",
            clean_snapshot_repair["test_rule"],
        )
        provenance_repair = refresh[
            "candidate_ready_provenance_input_repair"
        ]
        self.assertEqual(provenance_repair["status"], "pre-apply-frozen")
        self.assertEqual(
            provenance_repair["prior_report_sha256"],
            "sha256:9d23768ab807954a627aa5a83ddefd2522eddedc05dd103c173442c2f6b945db",
        )
        self.assertEqual(
            provenance_repair["prior_roadmap_sha256"],
            "sha256:818c8f653edcdb4269db391980c6609b8d7424bcbed8bf4ff4b01e66c7c82be9",
        )
        self.assertEqual(provenance_repair["archive_file_count"], 71)
        self.assertEqual(provenance_repair["archive_payload_bytes"], 11_436_099)
        self.assertEqual(provenance_repair["archive_manifest_bytes"], 11_840)
        self.assertEqual(
            provenance_repair["subcommand"],
            "reopen-candidate-ready-provenance-input",
        )
        self.assertIn(
            "separate-read-only-provenance-mount",
            provenance_repair["repair_rule"],
        )
        self.assertEqual(
            refresh["transition"]["phase_order"],
            [
                "admit-prior-and-new-acquisition",
                "archive-prior-output",
                "reopen-roadmap",
                "remove-canonical-prior-output",
                "freeze-source",
                "regenerate",
                "ordinary-generate",
                "candidate-ready-release",
            ],
        )
        self.assertIn(
            "remain-exactly-unchanged",
            refresh["transition"]["gate1_through_7_preservation"],
        )
        self.assertIn(
            "revision-increments-from9-to10",
            refresh["transition"]["roadmap_revision_rule"],
        )
        self.assertEqual(refresh["archive"]["file_count"], 71)
        self.assertEqual(refresh["archive"]["manifest_byte_length"], 11_816)
        self.assertEqual(refresh["prior_state"]["gate8_file_count"], 69)
        self.assertEqual(
            refresh["prior_state"]["gate8_plus_report_and_roadmap_file_count"],
            refresh["archive"]["file_count"],
        )
        self.assertIn("no-replace", refresh["archive"]["creation"])
        self.assertEqual(refresh["roadmap_reopen"]["new_revision"], 10)
        self.assertEqual(refresh["roadmap_reopen"]["new_m2_status"], "In progress")
        self.assertIn(
            "fail-before-docker-build",
            refresh["new_acquisition"]["future_acquisition_guard"],
        )
        self.assertEqual(
            policy["linux_source_surface"]["required_unignored_history_roots"],
            [
                "artifacts/history/m2-r3-pre-d7-mapping-clarification",
                "artifacts/history/m2-r3-pre-damage-artifact-schema-clarification",
                "artifacts/history/m2-r3-pre-independence-witness-clarification",
                "artifacts/history/m2-r3-pre-gate6-convergence-clarification",
                "artifacts/history/m2-r3-pre-local-check-reflection-clarification",
            ],
        )
        self.assertEqual(
            policy["linux_source_surface"]["history_paths_per_root_max"], 128
        )
        lifecycle = policy["gate8_lifecycle"]
        self.assertEqual(lifecycle["phase_order"], ["pre-gate8-clean", "candidate-ready"])
        self.assertIn("phase_check_cli", lifecycle["pre_gate8_clean_full"])
        self.assertIn("linux_verification_input", lifecycle["candidate_ready_full"])
        self.assertIn("candidate_ready_linux_cli", lifecycle["candidate_ready_full"])
        self.assertIn(
            "ordinary-assembly_cli-generate",
            lifecycle["candidate_ready_verifier_refresh"],
        )
        self.assertEqual(lifecycle["release_mode"], "candidate-ready-only")
        projection = policy["roadmap_projection"]
        self.assertEqual(
            projection["mutable_derived_header_row_prefixes"],
            ["| Project state | ", "| Current milestone | "],
        )
        self.assertIn("omit-those-two-complete-lines", projection["derived_header_row_rule"])
        transition = policy["roadmap_transition"]
        self.assertIn("revision10", transition["precondition"])
        self.assertEqual(
            transition["pre_gate8_terminal_sentence"],
            refresh["roadmap_reopen"]["pending_terminal_sentence"],
        )
        self.assertEqual(
            transition["install_order"],
            ["complete-gate8-tree", "tracked-report", "roadmap-status"],
        )
        self.assertIn("raw-sha256-of-the-installed-report", transition["final_admission"])
        self.assertIn("preserves-the-exact-precondition-roadmap", transition["rollback"])
        self.assertIn(
            "not-a-report-field",
            policy["candidate_ready_report"]["roadmap_state_meaning"],
        )
        self.assertIn(
            "pre-gate8-during-initial-generate-and-final-candidate-ready-during-check",
            policy["candidate_ready_report"]["roadmap_render_input"],
        )

    def test_docs_bind_the_smallest_gate8_owner(self) -> None:
        for relative in ("docs/m2-spec.md", "docs/m2-plan.md", "docs/m2-r3-design.md"):
            text = (ROOT / relative).read_text()
            self.assertIn("spec/gate8-policy-v0.toml", text, relative)
        for relative in ("docs/m2-spec.md", "docs/m2-plan.md"):
            self.assertIn(
                "spec/gate8-verifier-refresh-v0.toml",
                (ROOT / relative).read_text(),
                relative,
            )


if __name__ == "__main__":
    unittest.main()
