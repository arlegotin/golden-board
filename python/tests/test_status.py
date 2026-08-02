from __future__ import annotations

import hashlib
import unittest
from unittest.mock import patch

from golden_board import status as status_module
from golden_board.status import (
    StatusError,
    derive_status,
    parse_status,
    render_m0_completion,
    validate_header_status,
)


MILESTONES = (
    "M0 — Foundation and source reconnaissance",
    "M1 — Chess truth, source grammar, and assessment blueprint",
    "M2 — Full-carrier bootstrap and transport feasibility",
    "M3 — Complete content and formative integration",
    "M4 — Final profile, candidate, and automated qualification",
    "M5 — Independent reconstruction and learner validation",
    "M6 — Guided explorer, public package, and final audit",
)


def roadmap(
    statuses: tuple[str, ...] | None = None,
    *,
    project_state: str = "Not started",
    current_milestone: str = MILESTONES[0],
) -> str:
    selected = statuses or ("Not started",) * 7
    rows = []
    for index, (milestone, status) in enumerate(zip(MILESTONES, selected, strict=True)):
        evidence = "—"
        if status.startswith("Complete —"):
            evidence = f"reports/g{index + 1}.json"
        rows.append(f"| {milestone} | {status} | {evidence} |")
    return (
        "# Roadmap\n\n"
        "| Field | Value |\n"
        "|---|---|\n"
        "| Roadmap revision | 1 |\n"
        f"| Project state | {project_state} |\n"
        f"| Current milestone | {current_milestone} |\n\n"
        "## 13. Project status — sole mutable authority\n\n"
        "| Milestone | Status | Completion evidence or blocker |\n"
        "|---|---|---|\n"
        + "\n".join(rows)
        + "\n\nAllowed states are:\n"
    )


class StatusTests(unittest.TestCase):
    def test_parse_exact_seven_rows(self) -> None:
        rows = parse_status(roadmap())
        self.assertEqual(7, len(rows))
        self.assertEqual(MILESTONES[0], rows[0][0])
        self.assertEqual(("Not started", "—"), rows[0][1:])

    def test_all_allowed_status_forms_parse(self) -> None:
        statuses = (
            "Complete — 2026-08-02 and report identity abc",
            "In progress",
            "Blocked — Docker daemon unavailable",
            "Needs revision — source report drift",
            "Candidate ready — independent validation pending",
            "Stopped — redesign required",
            "Not started",
        )
        self.assertEqual(list(statuses), [row[1] for row in parse_status(roadmap(statuses))])

    def test_rejects_unknown_missing_duplicate_or_reordered_rows(self) -> None:
        valid = roadmap()
        cases = (
            valid.replace(
                f"| {MILESTONES[0]} | Not started | — |",
                f"| {MILESTONES[0]} | Waiting | — |",
                1,
            ),
            valid.replace(f"| {MILESTONES[6]} | Not started | — |\n", ""),
            valid.replace(
                f"| {MILESTONES[1]} | Not started | — |\n",
                f"| {MILESTONES[0]} | Not started | — |\n",
            ),
            valid.replace(
                f"| {MILESTONES[0]} | Not started | — |",
                "| M9 — Unknown | Not started | — |",
                1,
            ),
            valid.replace(
                f"| {MILESTONES[6]} | Not started | — |",
                f"| {MILESTONES[6]} | Not started | — |\n"
                "| M9 — Unknown | Not started | — |",
                1,
            ),
            valid.replace(
                f"| {MILESTONES[0]} | Not started | — |\n"
                f"| {MILESTONES[1]} | Not started | — |",
                f"| {MILESTONES[1]} | Not started | — |\n"
                f"| {MILESTONES[0]} | Not started | — |",
            ),
        )
        for malformed in cases:
            with self.subTest(malformed=malformed):
                with self.assertRaises(StatusError):
                    parse_status(malformed)

    def test_rejects_empty_specific_suffixes_and_pipe_in_evidence(self) -> None:
        for status in (
            "Blocked — ",
            "Blocked — exact <specific missing prerequisite>",
            "Needs revision — ",
            "Complete — ",
        ):
            with self.subTest(status=status):
                with self.assertRaises(StatusError):
                    parse_status(roadmap((status,) + ("Not started",) * 6))
        with self.assertRaises(StatusError):
            parse_status(roadmap().replace("| Not started | — |", "| Not started | a | b |", 1))

    def test_rejects_impossible_completion_date_or_missing_identity(self) -> None:
        for status in (
            "Complete — 2026-99-99 and report identity abc",
            "Complete — 2026-08-02 finished",
            "Complete — 2026-08-02 and report identity ",
            "Complete — 2026-08-02 and report identity <identity>",
            "Complete — 2026-08-02 and report identity (<identity>)",
        ):
            with self.subTest(status=status):
                with self.assertRaises(StatusError):
                    parse_status(roadmap((status,) + ("Not started",) * 6))

    def test_rejects_multiline_header_and_over_limit_input(self) -> None:
        text = roadmap()
        malformed = text.replace(
            "| Project state | Not started |",
            "| Project state | Not started\n |",
        )
        with self.assertRaises(StatusError):
            validate_header_status(malformed)
        with patch.object(status_module, "MAX_ROADMAP_CHARACTERS", len(text)):
            self.assertEqual(7, len(parse_status(text)))
        with patch.object(status_module, "MAX_ROADMAP_CHARACTERS", len(text) - 1):
            with self.assertRaises(StatusError):
                parse_status(text)
        controls = (
            text.replace(
                "| Milestone | Status | Completion evidence or blocker |\n|---|---|---|",
                "| Milestone | Status | Completion evidence or blocker |\v|---|---|---|",
            ),
            text.replace(
                f"| {MILESTONES[0]} | Not started | — |\n",
                f"| {MILESTONES[0]} | Not started | — |\x1c",
            ),
            text.replace(
                "| Roadmap revision | 1 |\n| Project state |",
                "| Roadmap revision | 1 |\v| Project state |",
            ),
        )
        for malformed in controls:
            with self.subTest(malformed=malformed), self.assertRaises(StatusError):
                validate_header_status(malformed)

    def test_derives_all_four_project_state_rules(self) -> None:
        complete = tuple(
            f"Complete — 2026-08-0{i + 1} report identity {i}" for i in range(7)
        )
        self.assertEqual(("Complete", "Complete"), derive_status(parse_status(roadmap(complete))))
        self.assertEqual(
            ("Not started", MILESTONES[0]),
            derive_status(parse_status(roadmap())),
        )
        exceptional = (
            "Complete — 2026-08-02 report identity 0",
            "Blocked — exact missing prerequisite",
        ) + ("Not started",) * 5
        self.assertEqual(
            ("Blocked — exact missing prerequisite", MILESTONES[1]),
            derive_status(parse_status(roadmap(exceptional))),
        )
        progressing = (
            "Complete — 2026-08-02 report identity 0",
            "In progress",
        ) + ("Not started",) * 5
        self.assertEqual(
            ("In progress", MILESTONES[1]),
            derive_status(parse_status(roadmap(progressing))),
        )

    def test_derive_status_rejects_malformed_direct_rows(self) -> None:
        rows = parse_status(roadmap())
        invalid_status = list(rows)
        invalid_status[0] = (MILESTONES[0], "invented", "—")
        short_row = list(rows)
        short_row[0] = (MILESTONES[0], "Not started")  # type: ignore[assignment]
        for malformed in (invalid_status, short_row):
            with self.subTest(malformed=malformed), self.assertRaises(StatusError):
                derive_status(malformed)  # type: ignore[arg-type]

        def overlong_rows():
            yield from rows
            yield rows[0]
            raise AssertionError("derive_status consumed beyond its eight-row cap")

        with self.assertRaises(StatusError):
            derive_status(overlong_rows())  # type: ignore[arg-type]

        total_characters = sum(len(value) for row in rows for value in row)
        with patch.object(status_module, "MAX_ROADMAP_CHARACTERS", total_characters):
            self.assertEqual(("Not started", MILESTONES[0]), derive_status(rows))
        with patch.object(
            status_module, "MAX_ROADMAP_CHARACTERS", total_characters - 1
        ):
            with self.assertRaises(StatusError):
                derive_status(rows)
        control_after_limit = list(rows)
        control_after_limit[0] = (MILESTONES[0], "In progress", "\x00")
        with patch.object(status_module, "MAX_ROADMAP_CHARACTERS", 1):
            with self.assertRaisesRegex(StatusError, "character limit"):
                derive_status(control_after_limit)

    def test_requires_one_canonical_status_header_and_separator(self) -> None:
        text = roadmap()
        cases = (
            text.replace(
                "| Milestone | Status | Completion evidence or blocker |",
                "| Milestone | State | Completion evidence or blocker |",
            ),
            text.replace("|---|---|---|", "| --- | Waiting | injected |"),
            text.replace(
                "| Milestone | Status | Completion evidence or blocker |\n",
                "| Milestone | Status | Completion evidence or blocker |\n"
                "| Milestone | Status | Completion evidence or blocker |\n",
            ),
        )
        for malformed in cases:
            with self.subTest(malformed=malformed), self.assertRaises(StatusError):
                parse_status(malformed)

    def test_header_validation_is_read_only_and_reports_staleness(self) -> None:
        text = roadmap()
        before = text[:]
        self.assertEqual([], validate_header_status(text))
        self.assertEqual(before, text)
        stale = text.replace("| Project state | Not started |", "| Project state | In progress |")
        self.assertEqual(
            ["roadmap header Project state is stale: expected Not started, found In progress"],
            validate_header_status(stale),
        )

        spoofed = text.replace("| Project state | Not started |\n", "").replace(
            "# Roadmap\n",
            "# Roadmap\n\n```text\n| Project state | Not started |\n```\n",
            1,
        )
        with self.assertRaises(StatusError):
            validate_header_status(spoofed)

    def test_status_rows_are_contiguous_and_cells_are_single_line(self) -> None:
        text = roadmap()
        first = f"| {MILESTONES[0]} | Not started | — |"
        second = f"| {MILESTONES[1]} | Not started | — |"
        malformed_tables = (
            text.replace(
                "| Milestone | Status | Completion evidence or blocker |\n|---|---|---|",
                "| Milestone | Status | Completion evidence or blocker |\n\n|---|---|---|",
            ),
            text.replace(f"{first}\n{second}", f"{first}\nprose\n{second}"),
            text.replace(
                first,
                f"| {MILESTONES[0]} | Not started | \x00 |",
                1,
            ),
            text.replace(
                first,
                f"| {MILESTONES[0]} | Not started | \t |",
                1,
            ),
        )
        for malformed in malformed_tables:
            with self.subTest(malformed=malformed), self.assertRaises(StatusError):
                parse_status(malformed)

        rows = parse_status(text)
        malformed_rows = []
        for field in (
            "Blocked — line one\n| Project state | injected |",
            "Blocked — contains\x00control",
        ):
            candidate = list(rows)
            candidate[0] = (MILESTONES[0], field, "—")
            malformed_rows.append(candidate)
        candidate = list(rows)
        candidate[0] = (MILESTONES[0], "Not started", "raw|pipe")
        malformed_rows.append(candidate)
        for malformed in malformed_rows:
            with self.subTest(malformed=malformed), self.assertRaises(StatusError):
                derive_status(malformed)

    def test_completion_renderer_changes_only_m0_and_two_header_values(self) -> None:
        in_progress = roadmap(
            ("In progress",) + ("Not started",) * 6,
            project_state="In progress",
        )
        digest = hashlib.sha256(b"source report\n").hexdigest()
        rendered = render_m0_completion(
            in_progress,
            completed_on="2026-08-02",
            source_report_sha256=digest,
        )
        self.assertIn(
            f"| {MILESTONES[0]} | Complete — 2026-08-02 and G1 source-doctor raw SHA-256 {digest} | reports/source-doctor.json |",
            rendered,
        )
        self.assertIn("| Project state | In progress |", rendered)
        self.assertIn(f"| Current milestone | {MILESTONES[1]} |", rendered)
        self.assertEqual([], validate_header_status(rendered))
        self.assertEqual(in_progress.count("\n"), rendered.count("\n"))

    def test_completion_renderer_rejects_wrong_state_date_or_digest(self) -> None:
        digest = "a" * 64
        with self.assertRaises(StatusError):
            render_m0_completion(
                roadmap(), completed_on="2026-08-02", source_report_sha256=digest
            )
        in_progress = roadmap(
            ("In progress",) + ("Not started",) * 6,
            project_state="In progress",
        )
        for date, candidate_digest in (("02-08-2026", digest), ("2026-08-02", "A" * 64)):
            with self.subTest(date=date, digest=candidate_digest):
                with self.assertRaises(StatusError):
                    render_m0_completion(
                        in_progress,
                        completed_on=date,
                        source_report_sha256=candidate_digest,
                    )
        for completed_on, candidate_digest in ((None, digest), ("2026-08-02", None)):
            with self.subTest(completed_on=completed_on, digest=candidate_digest):
                with self.assertRaises(StatusError):
                    render_m0_completion(
                        in_progress,
                        completed_on=completed_on,  # type: ignore[arg-type]
                        source_report_sha256=candidate_digest,  # type: ignore[arg-type]
                    )


if __name__ == "__main__":
    unittest.main()
