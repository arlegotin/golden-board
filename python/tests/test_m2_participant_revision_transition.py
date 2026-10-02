"""Lifecycle fault tests use temporary repositories, never a live transition."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools.m2 import reopen_participant_revision as transition


def prior_documents():
    """Bounded historical-anchor fixture, independent of current source docs.

    Full historical tuple admission is tested separately; the temporary
    copier/state-machine tests intentionally mock that admission.
    """
    common = (
        "| Roadmap | Revision 10, M2 Linux verifier provenance refresh |\n"
        "| Status | Gates 1–7 remain exact for the sole R3 v7 candidate; gate 8 "
        "is reopened only for the acquired Linux verifier provenance refresh |\n"
    )
    return {
        "docs/roadmap.md": (
            "# Historical fixture\n\n| Roadmap revision | 10 |\n"
            "| Last updated | 2026-08-30 |\n"
            "| Project state | Candidate ready |\n"
            "| Current milestone | M2 |\n\n"
            "## 13. Project status\n\n"
            "| M2 — Full-carrier bootstrap and transport feasibility | "
            "Candidate ready — independent validation pending | "
            "The candidate passes gates 1–8 with provisional preferred candidate "
            "`historical-fixture`; automated native and clean-Linux evidence "
            "passes, while technical and learner validation remains pending. |\n\n"
            "## 14. Adversarial stress matrix\n\nUnchanged fixture suffix.\n"
        ).encode(),
        "docs/m2-spec.md": ("# Historical specification fixture\n\n" + common
                            + "\n## 1. Purpose\n\nPreserve this original text.\n").encode(),
        "docs/m2-plan.md": ("# Historical plan fixture\n\n" + common
                            + "\n**Goal:** Preserve this original plan.\n").encode(),
        "docs/decisions.md": b"# Historical decision fixture\n\nKeep this history.\n",
    }


class TransitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.repo = self.base / "repository"
        self.repo.mkdir()
        (self.repo / ".git").mkdir()
        for name in transition.ROOTS:
            (self.repo / name).mkdir(parents=True, exist_ok=True)
        self.original_documents = prior_documents()
        for name in transition.DOCUMENTS:
            self.write(name, self.original_documents[name])
        self.write(transition.REPORT, b"{\"old\":true}\n")
        self.write(transition.GATE8 + "/receipt.json", b"old receipt\n")
        self.write(transition.CANDIDATE + "/carrier.bin", b"old carrier\0")
        self.write("artifacts/quiz/answer.bin", b"original submission\0")
        self.write("artifacts/linux/verifier-v0.env", b"environment only\n")
        self.write("artifacts/history/old/owner.toml", b"old owner\n")
        self.write("tools/original.py", b"old source\n", 0o755)
        self.source_paths = (*transition.DOCUMENTS, "tools/original.py")
        self.prepared = self.base / "prepared"
        self.real_package_admission = transition._verify_historical_package
        self.package_admission = mock.patch.object(transition, "_verify_historical_package")
        self.package_admission.start()
        self.addCleanup(self.package_admission.stop)

    def write(self, name, data, mode=0o644):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(mode)

    def prepare(self):
        # The fixture exercises the shared bounded copier/state machine, not
        # the unrelated full historical Gate8 validator and 483 MB corpus.
        with mock.patch.object(transition, "_admit_historical", return_value=self.source_paths):
            return transition.prepare(self.repo, self.prepared)

    def snapshot(self):
        return {str(p.relative_to(self.repo)): p.read_bytes()
                for p in self.repo.rglob("*") if p.is_file()}

    def test_pending_documents_reopen_exact_anchors_without_live_source(self):
        before = dict(self.original_documents)
        pending = transition._pending_documents(before)
        self.assertEqual(before, self.original_documents)
        self.assertEqual(set(pending), set(transition.DOCUMENTS))
        self.assertIn(b"| Roadmap revision | 11 |", pending["docs/roadmap.md"])
        self.assertIn(b"| Project state | In progress |", pending["docs/roadmap.md"])
        self.assertIn(b"No current Candidate-ready claim is admitted.", pending["docs/roadmap.md"])
        for name in ("docs/m2-spec.md", "docs/m2-plan.md"):
            self.assertIn("Gates 1–8 reopened".encode(), pending[name])
            self.assertIn(b"**Revision 11 current scope:**", pending[name])
        self.assertTrue(pending["docs/decisions.md"].startswith(before["docs/decisions.md"]))

    def test_prepare_is_read_only_and_apply_preserves_history(self):
        before = self.snapshot()
        digest = self.prepare()
        self.assertEqual(self.snapshot(), before)
        manifest = json.loads((self.prepared / "archive-manifest.json").read_bytes())
        self.assertEqual(digest, hashlib.sha256((self.prepared / "archive-manifest.json").read_bytes()).hexdigest())
        transition.apply(self.repo, self.prepared, digest)
        self.assertFalse((self.repo / transition.REPORT).exists())
        self.assertFalse((self.repo / transition.GATE8).exists())
        self.assertIn(b"| Project state | In progress |", (self.repo / "docs/roadmap.md").read_bytes())
        self.assertIn(b"Gates 1", (self.repo / "docs/m2-spec.md").read_bytes())
        for row in manifest["files"]:
            self.assertEqual((self.repo / transition.ARCHIVE / row["archive_path"]).read_bytes(), before[row["path"]])
        self.assertEqual((self.repo / transition.CANDIDATE / "carrier.bin").read_bytes(), b"old carrier\0")
        final = self.snapshot()
        with mock.patch.object(transition, "_replace_document", side_effect=AssertionError("idempotent write")):
            transition.apply(self.repo, self.prepared, digest)
        self.assertEqual(self.snapshot(), final)

    def test_stale_source_and_extra_gate8_reject_before_authority(self):
        for name, raw in (("tools/original.py", b"changed"), (transition.GATE8 + "/extra", b"extra")):
            with self.subTest(name=name):
                if not self.prepared.exists():
                    digest = self.prepare()
                self.write(name, raw)
                before = self.snapshot()
                with self.assertRaises(transition.TransitionError):
                    transition.apply(self.repo, self.prepared, digest)
                self.assertEqual(self.snapshot(), before)
                if name.endswith("extra"):
                    (self.repo / name).unlink()
                else:
                    self.write(name, b"old source\n", 0o755)

    def test_archive_tamper_and_wrong_digest_reject(self):
        digest = self.prepare()
        before = self.snapshot()
        with self.assertRaises(transition.TransitionError):
            transition.apply(self.repo, self.prepared, "0" * 64)
        (self.prepared / "prior/tools/original.py").write_bytes(b"bad")
        with self.assertRaises(transition.TransitionError):
            transition.apply(self.repo, self.prepared, digest)
        self.assertEqual(self.snapshot(), before)

    def test_link_and_hardlink_preparation_reject(self):
        target = self.repo / "artifacts/quiz/answer.bin"
        alias = self.repo / "artifacts/quiz/alias"
        alias.symlink_to(target)
        with self.assertRaises(transition.TransitionError):
            self.prepare()
        alias.unlink()
        os.link(target, alias)
        with self.assertRaises(transition.TransitionError):
            self.prepare()

    def test_failure_before_authority_preserves_prior(self):
        digest = self.prepare()
        before = self.snapshot()
        with mock.patch.object(transition, "_replace_document", side_effect=OSError("injected")):
            with self.assertRaises(OSError):
                transition.apply(self.repo, self.prepared, digest)
        for name, data in before.items():
            self.assertEqual((self.repo / name).read_bytes(), data)
        self.assertTrue((self.repo / transition.ARCHIVE / "archive-manifest.json").is_file())
        transition.apply(self.repo, self.prepared, digest)

    def test_failure_after_authority_can_resume_and_never_restores_ready(self):
        digest = self.prepare()
        original = transition._replace_document
        def interrupt(root, path, prior, pending):
            if path != "docs/roadmap.md":
                raise OSError("injected after authority")
            original(root, path, prior, pending)
        with mock.patch.object(transition, "_replace_document", side_effect=interrupt):
            with self.assertRaises(OSError):
                transition.apply(self.repo, self.prepared, digest)
        self.assertIn(b"| Project state | In progress |", (self.repo / "docs/roadmap.md").read_bytes())
        self.assertTrue((self.repo / transition.REPORT).exists())
        transition.apply(self.repo, self.prepared, digest)
        self.assertFalse((self.repo / transition.GATE8).exists())

    def test_partial_tombstone_resume_rejects_foreign_file(self):
        digest = self.prepare()
        with mock.patch.object(transition, "_remove_stale", side_effect=OSError("injected")):
            with self.assertRaises(OSError):
                transition.apply(self.repo, self.prepared, digest)
        (self.repo / transition.GATE8).rename(self.repo / transition.TOMBSTONE)
        foreign = self.repo / transition.TOMBSTONE / "foreign"
        foreign.write_bytes(b"keep me")
        with self.assertRaises(transition.TransitionError):
            transition.apply(self.repo, self.prepared, digest)
        self.assertEqual(foreign.read_bytes(), b"keep me")
        foreign.unlink()
        (self.repo / transition.TOMBSTONE / "receipt.json").unlink()
        transition.apply(self.repo, self.prepared, digest)
        self.assertFalse((self.repo / transition.TOMBSTONE).exists())

    def test_manifest_types_paths_extras_and_empty_directories(self):
        (self.repo / "artifacts/quiz/empty").mkdir()
        digest = self.prepare()
        self.assertTrue((self.prepared / "prior/artifacts/quiz/empty").is_dir())
        raw = (self.prepared / "archive-manifest.json").read_bytes()
        for mutation in (lambda m: m["files"][0].update(byte_length=True),
                         lambda m: m["files"][0].update(path="../escape"),
                         lambda m: m.update(unexpected=0)):
            value = json.loads(raw)
            mutation(value)
            changed = json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
            (self.prepared / "archive-manifest.json").write_bytes(changed)
            with self.assertRaises(transition.TransitionError):
                transition.apply(self.repo, self.prepared, hashlib.sha256(changed).hexdigest())
        (self.prepared / "archive-manifest.json").write_bytes(raw)
        (self.prepared / "extra").write_bytes(b"extra")
        with self.assertRaises(transition.TransitionError):
            transition.apply(self.repo, self.prepared, digest)

    def test_archived_source_rows_require_every_exact_preimage(self):
        source_rows = [{"path": f"tools/source-{i:03}.py", "byte_length": 1,
                        "sha256": hashlib.sha256(b"x").hexdigest(), "mode": "100644"}
                       for i in range(323)]
        projection = transition._canonical({"schema": "m2-evidence-source-v0",
                     "entries": source_rows, "roadmap_normative_sha256": "0" * 64})
        rows = [{"path": r["path"], "archive_path": "prior/" + r["path"],
                 "byte_length": r["byte_length"], "sha256": r["sha256"], "mode": "0644"}
                for r in source_rows]
        rows += [transition._row(p, b"document", 0o644, "prior/") for p in transition.DOCUMENTS]
        source_path = self.base / "package-source" / "prior" / transition.SOURCE
        source_path.parent.mkdir(parents=True)
        source_path.write_bytes(projection)
        rows.append(transition._row(transition.SOURCE, projection, 0o644, "prior/"))
        pins = {transition.SOURCE: hashlib.sha256(projection).hexdigest()}
        with mock.patch.dict(transition.PINS, pins, clear=True), mock.patch.object(transition, "_admit_gate8"):
            self.real_package_admission(self.base / "package-source", {"files": rows})
            for changed in (rows[1:], [dict(r, mode="0755") if i == 0 else r for i, r in enumerate(rows)]):
                with self.assertRaisesRegex(transition.TransitionError, "archived-source-preimage"):
                    self.real_package_admission(self.base / "package-source", {"files": changed})

    def test_interrupted_document_stage_rejects_before_any_archive_write(self):
        digest = self.prepare()
        self.write("docs/.m2-spec.md.participant-revision-v1", b"interrupted output")
        before = self.snapshot()
        with self.assertRaisesRegex(transition.TransitionError, "document-stage-present"):
            transition.apply(self.repo, self.prepared, digest)
        self.assertEqual(before, self.snapshot())

    def test_file_count_and_byte_bounds_reject_before_output(self):
        for attr, value in (("MAX_FILES", 2), ("MAX_TOTAL", 1)):
            with self.subTest(bound=attr), mock.patch.object(transition, attr, value):
                with self.assertRaises(transition.TransitionError):
                    self.prepare()
                self.assertFalse(self.prepared.exists())
        self.write("artifacts/quiz/oversized", bytes(transition.MAX_FILE + 1))
        with self.assertRaises(transition.TransitionError):
            self.prepare()
        self.assertFalse(self.prepared.exists())


if __name__ == "__main__":
    unittest.main()
