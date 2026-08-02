from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date
from itertools import islice


class StatusError(ValueError):
    """The roadmap status table or derived display is malformed."""


MILESTONES = (
    "M0 — Foundation and source reconnaissance",
    "M1 — Chess truth, source grammar, and assessment blueprint",
    "M2 — Full-carrier bootstrap and transport feasibility",
    "M3 — Complete content and formative integration",
    "M4 — Final profile, candidate, and automated qualification",
    "M5 — Independent reconstruction and learner validation",
    "M6 — Guided explorer, public package, and final audit",
)
SECTION_HEADING = "## 13. Project status — sole mutable authority"
SECTION_END = "Allowed states are:"
METADATA_HEADER = "| Field | Value |"
METADATA_SEPARATOR = "|---|---|"
STATUS_HEADER = "| Milestone | Status | Completion evidence or blocker |"
STATUS_SEPARATOR = "|---|---|---|"
EXACT_STATUSES = {
    "Not started",
    "In progress",
    "Candidate ready — independent validation pending",
    "Stopped — redesign required",
}
SPECIFIC_PREFIXES = ("Blocked — ", "Needs revision — ")
LOWER_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
COMPLETE = re.compile(r"Complete — (\d{4}-\d{2}-\d{2}) (.+)\Z")
MAX_ROADMAP_CHARACTERS = 4 * 1024 * 1024


def _status_is_allowed(status: str) -> bool:
    if status in EXACT_STATUSES:
        return True
    for prefix in SPECIFIC_PREFIXES:
        if status.startswith(prefix):
            detail = status[len(prefix) :].strip()
            return bool(detail) and "<" not in detail and ">" not in detail
    complete = COMPLETE.fullmatch(status)
    if complete is not None:
        try:
            date.fromisoformat(complete.group(1))
        except ValueError:
            return False
        detail = complete.group(2)
        if "<" in detail or ">" in detail:
            return False
        named_identity = re.search(r"\b(?:report|candidate) identity (\S+)", detail)
        sha_identity = re.search(r"\bSHA-256 [0-9a-f]{64}\b", detail)
        return named_identity is not None or sha_identity is not None
    return False


def _roadmap_structure(roadmap: str) -> tuple[list[str], int, int]:
    if type(roadmap) is not str:
        raise StatusError("roadmap must be text")
    if len(roadmap) > MAX_ROADMAP_CHARACTERS:
        raise StatusError("roadmap exceeds the 4 MiB character limit")
    if any(
        character != "\n" and not character.isprintable()
        for character in roadmap
    ):
        raise StatusError("roadmap must contain printable text and LF line endings")
    lines = roadmap.split("\n")
    headings = [index for index, line in enumerate(lines) if line == SECTION_HEADING]
    if len(headings) != 1:
        raise StatusError(f"missing heading: {SECTION_HEADING}")
    start = headings[0]
    endings = [
        index
        for index, line in enumerate(lines[start + 1 :], start + 1)
        if line == SECTION_END
    ]
    if len(endings) != 1:
        raise StatusError(f"missing Section 13 terminator: {SECTION_END}")
    return lines, start, endings[0]


def _section(roadmap: str) -> str:
    lines, start, end = _roadmap_structure(roadmap)
    return "\n".join(lines[start:end])


def _validated_rows(rows: Sequence[object]) -> tuple[tuple[str, str, str], ...]:
    try:
        candidates = tuple(islice(rows, len(MILESTONES) + 1))
    except TypeError as error:
        raise StatusError("status rows must be a sequence") from error
    if len(candidates) != len(MILESTONES):
        raise StatusError("status rows must contain exactly M0 through M6 in roadmap order")

    validated: list[tuple[str, str, str]] = []
    character_count = 0
    for row in candidates:
        if type(row) is not tuple or len(row) != 3 or not all(
            type(value) is str for value in row
        ):
            raise StatusError("each status row must be a three-string tuple")
        milestone, status, evidence = row
        character_count += len(milestone) + len(status) + len(evidence)
        if character_count > MAX_ROADMAP_CHARACTERS:
            raise StatusError("status rows exceed the 4 MiB character limit")
        if any(
            "|" in value or any(not character.isprintable() for character in value)
            for value in row
        ):
            raise StatusError("status row fields must be printable single-line cells")
        validated.append((milestone, status, evidence))

    if tuple(row[0] for row in validated) != MILESTONES:
        raise StatusError("status rows must contain exactly M0 through M6 in roadmap order")
    for milestone, status, evidence in validated:
        if not _status_is_allowed(status):
            raise StatusError(f"invalid status for {milestone}: {status}")
        if status.startswith("Complete —") and evidence in {"", "—"}:
            raise StatusError(f"completed milestone lacks evidence: {milestone}")
    return tuple(validated)


def parse_status(roadmap: str) -> list[tuple[str, str, str]]:
    lines = _section(roadmap).splitlines()
    header_indexes = [
        index for index, line in enumerate(lines) if line == STATUS_HEADER
    ]
    if len(header_indexes) != 1:
        raise StatusError("status table must contain one canonical header")
    header_index = header_indexes[0]
    if lines[0] != SECTION_HEADING:
        raise StatusError("status section heading is malformed")
    row_start = header_index + 2
    row_end = row_start + len(MILESTONES)
    if header_index + 1 >= len(lines) or lines[header_index + 1] != STATUS_SEPARATOR:
        raise StatusError("status table must contain one contiguous canonical separator")
    if row_end > len(lines) or any(line for line in lines[row_end:]):
        raise StatusError("status table must contain exactly seven contiguous rows")

    parsed: list[tuple[str, str, str]] = []
    for line in lines[row_start:row_end]:
        if not line.startswith("|") or not line.endswith("|"):
            raise StatusError("status table rows must be physically contiguous")
        if any(not character.isprintable() for character in line):
            raise StatusError("status table rows must contain only printable text")
        parts = line.split("|")
        if len(parts) != 5 or parts[0] or parts[-1]:
            raise StatusError(f"malformed status row: {line}")
        milestone, status, evidence = (part.strip() for part in parts[1:4])
        parsed.append((milestone, status, evidence))
    return list(_validated_rows(parsed))


def derive_status(
    rows: Sequence[tuple[str, str, str]],
) -> tuple[str, str]:
    statuses = tuple(row[1] for row in _validated_rows(rows))
    if all(status.startswith("Complete —") for status in statuses):
        return ("Complete", "Complete")
    if all(status == "Not started" for status in statuses):
        return ("Not started", MILESTONES[0])

    unfinished_index = next(
        index
        for index, status in enumerate(statuses)
        if not status.startswith("Complete —")
    )
    unfinished = statuses[unfinished_index]
    exceptional = (
        "Blocked — ",
        "Needs revision — ",
        "Candidate ready — ",
        "Stopped — ",
    )
    project_state = unfinished if unfinished.startswith(exceptional) else "In progress"
    return (project_state, MILESTONES[unfinished_index])


def _metadata_values(roadmap: str) -> dict[str, str]:
    all_lines, section_start, _ = _roadmap_structure(roadmap)
    lines = all_lines[:section_start]
    header_indexes = [
        index for index, line in enumerate(lines) if line == METADATA_HEADER
    ]
    if len(header_indexes) != 1:
        raise StatusError("roadmap must contain one canonical metadata table")
    header_index = header_indexes[0]
    first_content = next(
        (index for index, line in enumerate(lines[1:], 1) if line), None
    )
    if not lines or not lines[0].startswith("# ") or header_index != first_content:
        raise StatusError("roadmap metadata table must follow the document title")
    if header_index + 1 >= len(lines) or lines[header_index + 1] != METADATA_SEPARATOR:
        raise StatusError("roadmap metadata table lacks its canonical separator")

    values: dict[str, str] = {}
    for line in lines[header_index + 2 :]:
        if not line.startswith("|"):
            break
        if any(not character.isprintable() for character in line):
            raise StatusError("roadmap metadata rows must contain only printable text")
        parts = line.split("|")
        if len(parts) != 4 or parts[0] or parts[-1]:
            raise StatusError(f"malformed roadmap metadata row: {line}")
        field, value = (part.strip() for part in parts[1:3])
        if (
            not field
            or field in values
            or any(
                "|" in cell
                or any(not character.isprintable() for character in cell)
                for cell in (field, value)
            )
        ):
            raise StatusError(f"invalid roadmap metadata row: {line}")
        values[field] = value
    for field in ("Project state", "Current milestone"):
        if field not in values:
            raise StatusError(f"roadmap metadata table lacks {field}")
    return values


def validate_header_status(roadmap: str) -> list[str]:
    expected_state, expected_milestone = derive_status(parse_status(roadmap))
    metadata = _metadata_values(roadmap)
    found_state = metadata["Project state"]
    found_milestone = metadata["Current milestone"]
    errors: list[str] = []
    if found_state != expected_state:
        errors.append(
            "roadmap header Project state is stale: "
            f"expected {expected_state}, found {found_state}"
        )
    if found_milestone != expected_milestone:
        errors.append(
            "roadmap header Current milestone is stale: "
            f"expected {expected_milestone}, found {found_milestone}"
        )
    return errors


def _replace_exact_line(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise StatusError(f"expected exactly one line to replace: {old}")
    return text.replace(old, new, 1)


def render_m0_completion(
    roadmap: str,
    *,
    completed_on: str,
    source_report_sha256: str,
) -> str:
    if type(completed_on) is not str or ISO_DATE.fullmatch(completed_on) is None:
        raise StatusError("completion date must be YYYY-MM-DD")
    try:
        date.fromisoformat(completed_on)
    except ValueError as error:
        raise StatusError("completion date is not a real calendar date") from error
    if (
        type(source_report_sha256) is not str
        or LOWER_SHA256.fullmatch(source_report_sha256) is None
    ):
        raise StatusError("source report identity must be lowercase SHA-256")
    rows = parse_status(roadmap)
    if rows[0][1:] != ("In progress", "—"):
        raise StatusError("M0 must be exactly In progress with no evidence before completion")
    if validate_header_status(roadmap):
        raise StatusError("roadmap header must be current before completion")

    old_row = f"| {MILESTONES[0]} | In progress | — |"
    status = (
        f"Complete — {completed_on} and G1 source-doctor raw SHA-256 "
        f"{source_report_sha256}"
    )
    new_row = f"| {MILESTONES[0]} | {status} | reports/source-doctor.json |"
    rendered = _replace_exact_line(roadmap, old_row, new_row)
    rendered = _replace_exact_line(
        rendered,
        "| Project state | In progress |",
        "| Project state | In progress |",
    )
    rendered = _replace_exact_line(
        rendered,
        f"| Current milestone | {MILESTONES[0]} |",
        f"| Current milestone | {MILESTONES[1]} |",
    )
    if validate_header_status(rendered):
        raise StatusError("rendered completion produced stale header values")
    return rendered
