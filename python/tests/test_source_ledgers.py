from pathlib import Path, PurePosixPath
import re
import unittest

from golden_board.source_lock import load_source_lock, read_regular_below


ROOT = Path(__file__).resolve().parents[2]
SOURCES = PurePosixPath("docs/sources.md")
DECISIONS = PurePosixPath("docs/decisions.md")
MAX_LEDGER_BYTES = 64 * 1024


class SourceLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock = load_source_lock(ROOT)

    def read_required(self, path: PurePosixPath) -> str:
        try:
            raw = read_regular_below(ROOT, path, MAX_LEDGER_BYTES)
        except ValueError as error:
            self.fail(f"{path} must be a bounded regular file: {error}")
        return raw.decode("utf-8", "strict")

    def lock_owned_facts(self) -> tuple[str, ...]:
        anthology = self.lock.anthology
        clean = self.lock.clean_linux
        return (
            anthology.file_type,
            str(anthology.byte_length),
            anthology.sha256,
            anthology.encoding,
            anthology.bom,
            anthology.newlines,
            anthology.final_lf,
            *vars(self.lock.toolchains).values(),
            *(item.acquired_sha256 for item in self.lock.references),
            clean.mechanism,
            clean.image,
            clean.digest,
            clean.platform_digest,
            clean.config_digest,
            clean.platform,
            clean.uv_archive,
            clean.uv_archive_sha256,
            clean.docker_client,
            clean.observed_daemon_state,
            clean.acquisition_protocol,
            clean.offline_protocol,
            *clean.mounts,
            clean.state,
            clean.blocker,
            clean.deadline,
        )

    def test_source_ledger_covers_lock_without_copying_lock_owned_facts(self):
        text = self.read_required(SOURCES)
        rows = []
        for line in text.splitlines():
            match = re.match(r"^\| `([^`]+)` — ", line)
            if match is None:
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            self.assertEqual(9, len(cells), match.group(1))
            self.assertTrue(all(cells), match.group(1))
            self.assertEqual("2026-08-02", cells[4], match.group(1))
            self.assertIn(
                cells[6],
                {
                    "Normative authority",
                    "Implementation profile",
                    "Design precedent",
                    "Pedagogical hypothesis",
                },
                match.group(1),
            )
            rows.append((match.group(1), cells, line))

        expected_ids = ["anthology", *(item.id for item in self.lock.references)]
        self.assertEqual(expected_ids, [item[0] for item in rows])
        by_id = {identifier: line for identifier, _, line in rows}
        for reference in self.lock.references:
            row = by_id[reference.id]
            for required_text in (
                reference.title,
                reference.authority,
                reference.edition,
                reference.locator,
            ):
                self.assertIn(required_text, row, reference.id)

        for fact in self.lock_owned_facts():
            self.assertNotIn(fact, text)

    def test_decision_ledger_defines_format_and_has_no_m0_entry(self):
        text = self.read_required(DECISIONS)
        for fact in self.lock_owned_facts():
            self.assertNotIn(fact, text)
        for trigger in (
            "selecting or incompatibly changing the transport/bootstrap profile",
            "changing the hard artifact ceiling or mandatory product scope",
            "changing the source path/profile or chess scope",
            "changing a result-bearing damage or human threshold after exposure",
            "replacing `docs/64_games.md`",
        ):
            self.assertIn(trigger, text)
        for field in (
            "**Trigger:**",
            "**Decision:**",
            "**Reason and rejected alternatives:**",
            "**Affected owners and evidence:**",
            "**Revisit condition:**",
        ):
            self.assertIn(field, text)
        self.assertIn("## Current entries\n\nNone.", text)
        self.assertEqual([], re.findall(r"^## \d{4}-\d{2}-\d{2} — ", text, re.MULTILINE))
        self.assertNotRegex(text, r"\b(?:TBD|TODO)\b")
        self.assertNotIn("<date>", text)
        self.assertNotIn("<title>", text)


if __name__ == "__main__":
    unittest.main()
