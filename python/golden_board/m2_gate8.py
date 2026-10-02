"""Bounded, fail-closed M2 Gate-8 projections and evidence serializers.

Every emitted byte shape is reproduced from the frozen Gate-8 owner and its
named preimages.  Human participation is deliberately outside this module:
the Candidate-ready bundle and report contain neutral materials and an
explicitly unevaluated human gate, never participant actions or outcomes.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
import stat
import subprocess
import tomllib
from typing import BinaryIO, Mapping, Sequence

from . import (
    bootstrap,
    canonical_manifest,
    chess,
    content,
    identity,
    m2_carrier,
    m2_codec,
    m2_damage,
    m2_decoder,
    m2_independence,
    m2_policy,
    m2_recipe,
    m2_runner,
)


__all__ = (
    "CROSS_LANGUAGE_SCHEMA",
    "DAMAGE_INVENTORY_SCHEMA",
    "EVIDENCE_SOURCE_SCHEMA",
    "GATE8_POLICY_SHA256",
    "GATE8_VERIFIER_REFRESH_SHA256",
    "Gate8Error",
    "SemanticContentProjection",
    "OWNER_PROJECTION_SCHEMA",
    "PRODUCER_RECEIPT_SCHEMA",
    "SEMANTIC_CONTENT_SCHEMA",
    "SELECTION_SCHEMA",
    "build_damage_inventory",
    "build_candidate_row",
    "build_bundle_files",
    "build_damage_rows",
    "derive_candidate_metrics",
    "build_evidence_source_projection",
    "build_owner_projection",
    "profile_tuple_manifest",
    "build_semantic_content_projection",
    "build_semantic_content_projection_from_carrier",
    "profile_tuple_identity",
    "load_gate8_policy",
    "load_gate8_verifier_refresh",
    "owner_projection_paths",
    "render_cross_language_manifest",
    "render_bundle_manifest",
    "render_candidate_ready_report",
    "render_candidate_ready_roadmap",
    "render_damage_inventory",
    "render_producer_receipt",
    "parse_producer_receipt",
    "parse_linux_acquisition_receipt",
    "render_generated_evidence",
    "render_geometry_equivalence",
    "render_learner_expected",
    "render_learner_heldout_request",
    "render_learner_slice_binding",
    "render_linux_verification_input",
    "render_linux_attestation",
    "render_owner_projection",
    "render_pilot_envelope",
    "render_technical_content_query",
    "render_technical_heldout_classes",
    "render_technical_heldout_expected",
    "render_selection",
    "roadmap_normative_sha256",
    "validate_cross_language_manifest",
    "validate_bundle_manifest",
    "validate_candidate_ready_report",
    "validate_candidate_ready_roadmap",
    "validate_damage_inventory",
    "validate_evidence_source_projection",
    "validate_gate8_source_surface",
    "validate_installed_gate8",
    "validate_owner_projection",
    "validate_producer_receipt",
    "validate_generated_evidence",
    "validate_linux_attestation",
    "validate_linux_verification_input",
    "validate_selection",
    "validate_semantic_content_projection",
)


EVIDENCE_SOURCE_SCHEMA = "m2-evidence-source-v0"
OWNER_PROJECTION_SCHEMA = "golden-board.m2-owner-projection/v0"
SEMANTIC_CONTENT_SCHEMA = "golden-board.m2-gate8-semantic-content/v0"
DAMAGE_INVENTORY_SCHEMA = "golden-board.m2-gate8-damage-inventory/v0"
CROSS_LANGUAGE_SCHEMA = "golden-board.m2-cross-language/v0"
PRODUCER_RECEIPT_SCHEMA = "golden-board.m2-gate8-producer-receipt/v0"
SELECTION_SCHEMA = "golden-board.m2-selection/v0"
LINUX_VERIFICATION_INPUT_SCHEMA = (
    "golden-board.m2-gate8-linux-verification-input/v0"
)
GATE8_POLICY_SHA256 = (
    "fd53145eeb5d0d5578b8cb1aff980039c999839516528b309a626dd62e52794e"
)
GATE8_VERIFIER_REFRESH_SHA256 = (
    "8b01c255d948f46ea4fb30b16160af00c416cb087dddc9c62ac768a989772116"
)
_CANDIDATE_ID = "eh72-hier-r5-r2-r1-crc32c-v0"
_CANDIDATE_SCHEMA = "golden-board.m2-candidate-manifest/v1"
_CANDIDATE_MANIFEST_SHA256 = (
    "38839aa28561ff2bec0997a80d8dc938e876526c25f40e23b6a78844f8fc1d86"
)
_CANDIDATE_METRICS = {
    "operation_kind_count": 23,
    "table_count": 13,
    "table_bytes": 1_470,
    "graph_nodes": 699,
    "graph_edges": 1_087,
    "dependency_depth": 36,
    "recipe_cells": 830_016,
    "worked_example_cells": 11_712,
    "held_out_example_cells": 11_712,
    "shell_cells": 978_944,
    "convention_count": 12,
    "plain_bits": 1_954_312,
    "protected_bits": 3_181_248,
    "reserve_bits": 57_128,
    "total_bits": 4_161_600,
    "robustness_ppm": 0,
    "worst_case_work_units": 4_484_682_504,
    "scratch_bytes": 6_163,
    "remaining_reserve_bytes": 4_088,
}
_PROFILE_POLICY_SHA256 = (
    "44215d993e3fdfdd1630c404f1ee969e8abc6e4928fda83365fc6940e5cfd412"
)
_PROFILE_VERSION = 7
_COMMON_BLOCK_BYTES = 191
_SECTION_COUNT = 138
_LOGICAL_GROUP_COUNT = 1_279
_SECTION_DOMAIN = b"golden-board:m2:gate8:section-envelopes:v0\0"
_COMMON_DOMAIN = b"golden-board:m2:gate8:common-plain-blocks:v0\0"
_DAMAGE_FAMILIES = tuple(f"D{ordinal}" for ordinal in range(8))
_DAMAGE_SHARD_COUNTS = (1, 1, 2, 3, 11, 1, 41, 3)
_DAMAGE_GUARANTEES = (
    "all_declared_m2_sections_exact",
    "all_declared_m2_sections_exact",
    "m2_required_closure",
    "m2_required_closure",
    "m2_required_closure",
    "all_declared_m2_sections_exact",
    "m2_required_closure",
    "correct_or_explicit_failure",
)
_DAMAGE_ROOT_FILES = ("damage-manifest.json",)
_DAMAGE_FAMILY_FILES = tuple(f"damage-{family}.json" for family in _DAMAGE_FAMILIES)
_DAMAGE_PROOF_FILE = "independence-proof.json"
_DAMAGE_FILE_BYTES_MAX = 1_048_576
_DAMAGE_AGGREGATE_BYTES_MAX = 67_108_864
_OWNER_ROLES: dict[str, tuple[str, tuple[str, ...]]] = {
    "parameter_manifest": (
        "parameter-manifest-v7",
        (
            "spec/profile-policy-v1.toml",
            "spec/profile-limits-v1.toml",
            f"artifacts/candidates/{_CANDIDATE_ID}/candidate-manifest.json",
        ),
    ),
    "known_answer_manifest": (
        "known-answer-manifest-v7",
        ("conformance/m2-r3-owner-v1.json", "spec/route-data-v1.json"),
    ),
    "shell_manifest": (
        "shell-manifest-v7",
        (
            "spec/bootstrap-v1.md",
            "spec/route-data-v1.json",
            f"artifacts/candidates/{_CANDIDATE_ID}/candidate-manifest.json",
        ),
    ),
    "recipe_manifest": (
        "recipe-manifest-v7",
        ("spec/bootstrap-v1.md", "spec/route-data-v1.json"),
    ),
    "grammar_state_manifest": (
        "grammar-state-manifest-v7",
        (
            "spec/profile-policy-v1.toml",
            "spec/damage-policy-v1.toml",
            f"artifacts/candidates/{_CANDIDATE_ID}/semantic-envelope.json",
            f"artifacts/candidates/{_CANDIDATE_ID}/candidate-manifest.json",
        ),
    ),
    "work_scratch_ledger": (
        "work-scratch-ledger-v7",
        (
            "spec/profile-limits-v1.toml",
            "spec/route-data-v1.json",
            f"artifacts/candidates/{_CANDIDATE_ID}/capacity-ledger.json",
        ),
    ),
    "profile_limits_derivation": (
        "profile-limits-v7",
        (
            "spec/profile-policy-v1.toml",
            "spec/damage-policy-v1.toml",
            "spec/bootstrap-v1.md",
            "spec/route-data-v1.json",
            "spec/profile-limits-v1.toml",
            "spec/m2-r3-owner-promotion-v1.toml",
        ),
    ),
    "side_search_policy": (
        "side-search-v7",
        (
            "spec/profile-policy-v1.toml",
            "spec/profile-limits-v1.toml",
            "spec/route-data-v1.json",
            f"artifacts/candidates/{_CANDIDATE_ID}/candidate-manifest.json",
            f"artifacts/candidates/{_CANDIDATE_ID}/capacity-ledger.json",
        ),
    ),
}
_EXCLUDED_PATHS = frozenset(
    (
        "docs/roadmap.md",
        "docs/decisions.md",
        "reports/m2-feasibility-v0.json",
    )
)
_ROADMAP_DOMAIN = b"golden-board:roadmap-normative:v0\0"
_PRE_GATE8_ROADMAP_SHA256 = (
    "153f66d0713c04d357c3bf980b3fde1feae328d7751099e5c9bb019c6f98b1f1"
)
_STATUS_HEADING = b"## 13. Project status"
_STRESS_HEADING = b"## 14. Adversarial stress matrix"
_MAX_ENTRIES = 8_192
_MAX_FILE_BYTES = 16 * 1_048_576
_MAX_GIT_OUTPUT_BYTES = 4 * 1_048_576
_MAX_PATH_BYTES = 255
_ARTIFACT_IDS = (
    "semantic-content-projection",
    "candidate-manifest",
    "carrier",
    "ownership-ledger",
    "capacity-ledger",
    "density-ledger",
    "damage-bundle-inventory",
    "independence-proof",
)
_PRODUCER_IDS = (
    "native-python",
    "native-rust",
    "linux-python",
    "linux-rust",
)
_SELECTION_STEPS = (
    "gate-filter",
    "lowest-complexity-class",
    "near-minimum-band",
    "rank",
    "top-two",
    "preference",
)
_METRIC_KEYS = (
    "operation_kind_count",
    "table_count",
    "table_bytes",
    "graph_nodes",
    "graph_edges",
    "dependency_depth",
    "recipe_cells",
    "worked_example_cells",
    "held_out_example_cells",
    "shell_cells",
    "convention_count",
    "plain_bits",
    "protected_bits",
    "reserve_bits",
    "total_bits",
    "robustness_ppm",
    "worst_case_work_units",
    "scratch_bytes",
    "remaining_reserve_bytes",
)
_HARD_GATE_KEYS = (
    "profile-and-cross-language-kat",
    "bootstrap-recipe-shell",
    "common-grammar-atomic-state",
    "generated-resource-limits",
    "provisional-capacity",
    "damage-zero-wrong-accept",
    "physical-independence",
    "native-linux-reproducibility",
    "preferred-human-feasibility",
)
_SHARED_ROLE_NAMES = (
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
)
_CANDIDATE_ROLE_ORDER = (
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
)


class Gate8Error(ValueError):
    """One stable gate-8 evidence-boundary failure."""

    __slots__ = ("_reason",)

    def __init__(self, reason: str):
        if type(reason) is not str:
            raise TypeError("gate-8 reason must be a string")
        self._reason = reason
        super().__init__(reason)

    @property
    def reason(self) -> str:
        return self._reason

    def __setattr__(self, name: str, value: object) -> None:
        if name == "_reason" and hasattr(self, name):
            raise AttributeError("_reason is read-only")
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if name == "_reason":
            raise AttributeError("_reason is read-only")
        super().__delattr__(name)


@dataclass(frozen=True, slots=True)
class SemanticContentProjection:
    """One exact semantic projection and its independently assembled stream."""

    canonical_bytes: bytes
    content_stream: bytes


def _fail(reason: str) -> None:
    raise Gate8Error(reason)


def _u64_be(value: int) -> bytes:
    if type(value) is not int or not 0 <= value <= canonical_manifest.MAX_U64:
        _fail("roadmap-normative-length")
    return value.to_bytes(8, "big")


def roadmap_normative_sha256(raw: bytes) -> str:
    """Hash the immutable roadmap prefix/suffix around its mutable status."""

    if type(raw) is not bytes:
        raise TypeError("roadmap bytes must be bytes")
    if len(raw) > _MAX_FILE_BYTES:
        _fail("roadmap-byte-limit")
    if b"\r" in raw or not raw.endswith(b"\n"):
        _fail("roadmap-framing")
    if raw.count(_STATUS_HEADING) != 1 or raw.count(_STRESS_HEADING) != 1:
        _fail("roadmap-heading")
    status = raw.index(_STATUS_HEADING)
    stress = raw.index(_STRESS_HEADING)
    if status >= stress:
        _fail("roadmap-heading-order")
    prefix_lines = raw[:status].splitlines(keepends=True)
    mutable_prefixes = (b"| Project state | ", b"| Current milestone | ")
    mutable_indices: set[int] = set()
    for row_prefix in mutable_prefixes:
        matches = [
            index
            for index, line in enumerate(prefix_lines)
            if line.startswith(row_prefix)
        ]
        if len(matches) != 1:
            _fail("roadmap-derived-header")
        line = prefix_lines[matches[0]]
        value = line[len(row_prefix) :]
        if not value.endswith(b" |\n") or b"|" in value[:-3]:
            _fail("roadmap-derived-header")
        mutable_indices.add(matches[0])
    prefix = b"".join(
        line for index, line in enumerate(prefix_lines) if index not in mutable_indices
    )
    suffix = raw[stress:]
    preimage = b"".join(
        (
            _ROADMAP_DOMAIN,
            _u64_be(len(prefix)),
            prefix,
            _u64_be(len(suffix)),
            suffix,
        )
    )
    return hashlib.sha256(preimage).hexdigest()


def render_candidate_ready_roadmap(roadmap_raw: bytes, report_raw: bytes) -> bytes:
    """Render the exact status-last Candidate-ready roadmap transition."""

    if type(roadmap_raw) is not bytes or type(report_raw) is not bytes:
        raise TypeError("roadmap transition inputs must be bytes")
    if len(roadmap_raw) > _MAX_FILE_BYTES or not roadmap_raw.endswith(b"\n"):
        _fail("roadmap-transition")
    if (
        len(roadmap_raw) != 189_838
        or hashlib.sha256(roadmap_raw).hexdigest() != _PRE_GATE8_ROADMAP_SHA256
    ):
        _fail("roadmap-transition-precondition")
    _canonical_value(report_raw, "roadmap-transition-report")
    if roadmap_raw.count(b"| Roadmap revision | 10 |\n") != 1:
        _fail("roadmap-transition")
    project_before = b"| Project state | In progress |\n"
    project_after = b"| Project state | Candidate ready |\n"
    milestone = (
        b"| Current milestone | M2 \xe2\x80\x94 Full-carrier bootstrap and "
        b"transport feasibility |\n"
    )
    row_before = (
        b"| M2 \xe2\x80\x94 Full-carrier bootstrap and transport feasibility | "
        b"In progress | "
    )
    row_after = (
        b"| M2 \xe2\x80\x94 Full-carrier bootstrap and transport feasibility | "
        b"Candidate ready \xe2\x80\x94 independent validation pending | "
    )
    sentence_before = (
        b"Revision 10 preserves the R3 candidate and Gates 1\xe2\x80\x937 while "
        b"reopening only Gate 8 for the acquired Linux verifier provenance "
        b"refresh; no current Candidate-ready claim is admitted."
    )
    report_digest = hashlib.sha256(report_raw).hexdigest().encode("ascii")
    sentence_after = (
        b"The candidate passes gates 1\xe2\x80\x938 with provisional preferred "
        b"candidate `"
        + _CANDIDATE_ID.encode("ascii")
        + b"` and tracked report SHA-256 `"
        + report_digest
        + b"`; automated native and clean-Linux evidence passes, while technical "
        b"and learner validation remains pending."
    )
    lines = roadmap_raw.splitlines(keepends=True)
    row_matches = [index for index, line in enumerate(lines) if line.startswith(row_before)]
    if (
        roadmap_raw.count(project_before) != 1
        or roadmap_raw.count(project_after) != 0
        or roadmap_raw.count(milestone) != 1
        or roadmap_raw.count(sentence_before) != 1
        or roadmap_raw.count(sentence_after) != 0
        or len(row_matches) != 1
        or not lines[row_matches[0]].endswith(sentence_before + b" |\n")
    ):
        _fail("roadmap-transition-precondition")
    final_row = lines[row_matches[0]].replace(row_before, row_after, 1).replace(
        sentence_before, sentence_after, 1
    )
    lines[row_matches[0]] = final_row
    final = b"".join(lines).replace(project_before, project_after, 1)
    if roadmap_normative_sha256(final) != roadmap_normative_sha256(roadmap_raw):
        _fail("roadmap-transition-preservation")
    validate_candidate_ready_roadmap(final, report_raw)
    return final


def validate_candidate_ready_roadmap(
    roadmap_raw: bytes, report_raw: bytes
) -> None:
    """Admit the exact final Candidate-ready authority rows and report binding."""

    if type(roadmap_raw) is not bytes or type(report_raw) is not bytes:
        raise TypeError("roadmap transition inputs must be bytes")
    if len(roadmap_raw) > _MAX_FILE_BYTES or not roadmap_raw.endswith(b"\n"):
        _fail("roadmap-final")
    _canonical_value(report_raw, "roadmap-final-report")
    project = b"| Project state | Candidate ready |\n"
    milestone = (
        b"| Current milestone | M2 \xe2\x80\x94 Full-carrier bootstrap and "
        b"transport feasibility |\n"
    )
    row_prefix = (
        b"| M2 \xe2\x80\x94 Full-carrier bootstrap and transport feasibility | "
        b"Candidate ready \xe2\x80\x94 independent validation pending | "
    )
    sentence = (
        b"The candidate passes gates 1\xe2\x80\x938 with provisional preferred "
        b"candidate `"
        + _CANDIDATE_ID.encode("ascii")
        + b"` and tracked report SHA-256 `"
        + hashlib.sha256(report_raw).hexdigest().encode("ascii")
        + b"`; automated native and clean-Linux evidence passes, while technical "
        b"and learner validation remains pending."
    )
    rows = [
        line
        for line in roadmap_raw.splitlines(keepends=True)
        if line.startswith(row_prefix)
    ]
    if (
        roadmap_raw.count(b"| Roadmap revision | 10 |\n") != 1
        or roadmap_raw.count(project) != 1
        or roadmap_raw.count(milestone) != 1
        or roadmap_raw.count(sentence) != 1
        or len(rows) != 1
        or not rows[0].endswith(sentence + b" |\n")
    ):
        _fail("roadmap-final")
    pending = roadmap_raw
    replacements = (
        (project, b"| Project state | In progress |\n"),
        (
            row_prefix,
            b"| M2 \xe2\x80\x94 Full-carrier bootstrap and transport feasibility | "
            b"In progress | ",
        ),
        (
            sentence,
            b"Revision 10 preserves the R3 candidate and Gates 1\xe2\x80\x937 while "
            b"reopening only Gate 8 for the acquired Linux verifier provenance "
            b"refresh; no current Candidate-ready claim is admitted.",
        ),
    )
    for old, new in replacements:
        if pending.count(old) != 1:
            _fail("roadmap-final")
        pending = pending.replace(old, new, 1)
    if (
        len(pending) != 189_838
        or hashlib.sha256(pending).hexdigest() != _PRE_GATE8_ROADMAP_SHA256
    ):
        _fail("roadmap-final")


def _read_bounded(stream: BinaryIO, maximum: int, reason: str) -> bytes:
    output = bytearray()
    while True:
        chunk = stream.read(min(65_536, maximum + 1 - len(output)))
        if not chunk:
            return bytes(output)
        output.extend(chunk)
        if len(output) > maximum:
            _fail(reason)


def _git_visible_paths(root: Path) -> tuple[bytes, ...]:
    environment = os.environ.copy()
    environment["GIT_CONFIG_GLOBAL"] = "/dev/null"
    environment["GIT_CONFIG_NOSYSTEM"] = "1"
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        process = subprocess.Popen(
            (
                "git",
                "-c",
                "core.excludesFile=/dev/null",
                "-C",
                os.fspath(root),
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
        )
    except OSError as error:
        raise Gate8Error("source-projection-git") from error
    assert process.stdout is not None
    assert process.stderr is not None
    try:
        output = _read_bounded(
            process.stdout, _MAX_GIT_OUTPUT_BYTES, "source-projection-git-output"
        )
        stderr = _read_bounded(
            process.stderr, 65_536, "source-projection-git-stderr"
        )
    except BaseException:
        process.kill()
        process.wait()
        raise
    finally:
        process.stdout.close()
        process.stderr.close()
    if process.wait() != 0:
        del stderr
        _fail("source-projection-git")
    paths = tuple(item for item in output.split(b"\0") if item)
    if len(paths) > _MAX_ENTRIES or len(set(paths)) != len(paths):
        _fail("source-projection-entry-count")
    return paths


def _checked_path(raw: bytes) -> tuple[str, tuple[bytes, ...]]:
    if (
        not raw
        or len(raw) > _MAX_PATH_BYTES
        or raw.startswith(b"/")
        or b"\\" in raw
        or b"\0" in raw
        or any(byte < 0x20 or byte > 0x7E for byte in raw)
    ):
        _fail("source-projection-path")
    components = tuple(raw.split(b"/"))
    if any(component in {b"", b".", b".."} for component in components):
        _fail("source-projection-path")
    return raw.decode("ascii"), components


def _regular_row(root: Path, raw_path: bytes) -> dict[str, object] | None:
    path_text, components = _checked_path(raw_path)
    current = os.fsencode(root)
    metadata: os.stat_result | None = None
    for index, component in enumerate(components):
        current = os.path.join(current, component)
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            return None
        if index + 1 != len(components):
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                _fail("source-projection-parent")
    assert metadata is not None
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
    ):
        _fail("source-projection-file")
    digest = hashlib.sha256()
    length = 0
    try:
        with open(current, "rb", buffering=0) as stream:
            while True:
                chunk = stream.read(65_536)
                if not chunk:
                    break
                length += len(chunk)
                if length > _MAX_FILE_BYTES:
                    _fail("source-projection-file-limit")
                digest.update(chunk)
        after = os.lstat(current)
    except OSError as error:
        raise Gate8Error("source-projection-file") from error
    if (
        after.st_dev != metadata.st_dev
        or after.st_ino != metadata.st_ino
        or after.st_size != metadata.st_size
        or after.st_mtime_ns != metadata.st_mtime_ns
        or after.st_mode != metadata.st_mode
        or after.st_nlink != 1
        or length != metadata.st_size
    ):
        _fail("source-projection-race")
    return {
        "path": path_text,
        "mode": "100755" if metadata.st_mode & 0o111 else "100644",
        "byte_length": length,
        "sha256": digest.hexdigest(),
    }


def _real_repository(root: Path) -> Path:
    if not isinstance(root, Path):
        raise TypeError("repository root must be a Path")
    absolute = Path(os.path.abspath(root))
    try:
        metadata = os.lstat(absolute)
        git_metadata = os.lstat(absolute / ".git")
    except OSError as error:
        raise Gate8Error("source-projection-root") from error
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(git_metadata.st_mode)
        or not stat.S_ISDIR(git_metadata.st_mode)
    ):
        _fail("source-projection-root")
    return absolute


def _regular_root(root: Path) -> Path:
    if not isinstance(root, Path):
        raise TypeError("root must be a Path")
    absolute = Path(os.path.abspath(root))
    try:
        metadata = os.lstat(absolute)
    except OSError as error:
        raise Gate8Error("gate8-root") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        _fail("gate8-root")
    return absolute


def _repo_path_text(value: str) -> str:
    if type(value) is not str:
        raise TypeError("repository path must be a string")
    try:
        raw = value.encode("ascii")
    except UnicodeEncodeError as error:
        raise Gate8Error("gate8-path") from error
    try:
        path, _ = _checked_path(raw)
    except Gate8Error as error:
        raise Gate8Error("gate8-path") from error
    return path


def _read_repo_file(
    root: Path,
    relative: str,
    *,
    maximum: int = _MAX_FILE_BYTES,
    allow_empty: bool = False,
) -> bytes:
    root = _regular_root(root)
    relative = _repo_path_text(relative)
    components = relative.split("/")
    current = root
    try:
        for component in components[:-1]:
            current = current / component
            metadata = os.lstat(current)
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                _fail("gate8-file-parent")
        path = current / components[-1]
        before = os.lstat(path)
        if (
            stat.S_ISLNK(before.st_mode)
            or not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size > maximum
            or (not allow_empty and before.st_size == 0)
        ):
            _fail("gate8-file")
        with path.open("rb", buffering=0) as stream:
            raw = _read_bounded(stream, maximum, "gate8-file-limit")
        after = os.lstat(path)
    except Gate8Error:
        raise
    except OSError as error:
        raise Gate8Error("gate8-file") from error
    if (
        len(raw) != before.st_size
        or after.st_dev != before.st_dev
        or after.st_ino != before.st_ino
        or after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
        or after.st_mode != before.st_mode
        or after.st_nlink != 1
    ):
        _fail("gate8-file-race")
    return raw


def _canonical(value: object, reason: str) -> bytes:
    try:
        return canonical_manifest.serialize_manifest(value)
    except canonical_manifest.ManifestError as error:
        raise Gate8Error(reason) from error


def _canonical_value(raw: bytes, reason: str) -> dict[str, object]:
    if type(raw) is not bytes:
        raise TypeError(f"{reason} bytes must be bytes")
    try:
        return canonical_manifest.validate_canonical_manifest(raw)
    except canonical_manifest.ManifestError as error:
        raise Gate8Error(reason) from error


def _hex64(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _u32(value: int, reason: str) -> bytes:
    if type(value) is not int or not 0 <= value <= 0xFFFF_FFFF:
        _fail(reason)
    return value.to_bytes(4, "big")


def build_evidence_source_projection(root: Path) -> bytes:
    """Render the exact non-self-referential current-worktree projection."""

    root = _real_repository(root)
    rows: list[dict[str, object]] = []
    previous: bytes | None = None
    visible_paths = tuple(sorted(_git_visible_paths(root)))
    if b"docs/roadmap.md" not in visible_paths:
        _fail("roadmap-not-visible")
    for raw_path in visible_paths:
        if previous is not None and raw_path <= previous:
            _fail("source-projection-order")
        previous = raw_path
        path_text, _ = _checked_path(raw_path)
        if path_text in _EXCLUDED_PATHS:
            continue
        row = _regular_row(root, raw_path)
        if row is not None:
            rows.append(row)
    if not rows:
        _fail("source-projection-empty")
    roadmap_path = root / "docs" / "roadmap.md"
    roadmap_row = _regular_row(root, b"docs/roadmap.md")
    if roadmap_row is None:
        _fail("roadmap-missing")
    try:
        with roadmap_path.open("rb", buffering=0) as stream:
            roadmap_raw = _read_bounded(stream, _MAX_FILE_BYTES, "roadmap-byte-limit")
    except OSError as error:
        raise Gate8Error("roadmap-missing") from error
    if (
        len(roadmap_raw) != roadmap_row["byte_length"]
        or hashlib.sha256(roadmap_raw).hexdigest() != roadmap_row["sha256"]
    ):
        _fail("source-projection-race")
    value = {
        "schema": EVIDENCE_SOURCE_SCHEMA,
        "roadmap_normative_sha256": roadmap_normative_sha256(roadmap_raw),
        "entries": rows,
    }
    try:
        return canonical_manifest.serialize_manifest(value)
    except canonical_manifest.ManifestError as error:
        raise Gate8Error("source-projection-manifest") from error


def _source_projection_value(raw: bytes) -> dict[str, object]:
    value = _canonical_value(raw, "source-projection-manifest")
    rows = value.get("entries")
    if (
        set(value) != {"schema", "roadmap_normative_sha256", "entries"}
        or value.get("schema") != EVIDENCE_SOURCE_SCHEMA
        or not _hex64(value.get("roadmap_normative_sha256"))
        or type(rows) is not list
        or not 1 <= len(rows) <= _MAX_ENTRIES
    ):
        _fail("source-projection-shape")
    previous: bytes | None = None
    for row in rows:
        if (
            type(row) is not dict
            or set(row) != {"path", "mode", "byte_length", "sha256"}
            or row.get("mode") not in ("100644", "100755")
            or type(row.get("byte_length")) is not int
            or not 0 <= int(row["byte_length"]) <= canonical_manifest.MAX_U64
            or not _hex64(row.get("sha256"))
        ):
            _fail("source-projection-row")
        try:
            path = _repo_path_text(row["path"])  # type: ignore[arg-type]
        except (TypeError, Gate8Error) as error:
            raise Gate8Error("source-projection-row") from error
        encoded = path.encode("ascii")
        if previous is not None and encoded <= previous:
            _fail("source-projection-order")
        previous = encoded
    return value


def validate_evidence_source_projection(raw: bytes, root: Path) -> dict[str, object]:
    """Strictly parse and reproduce one source projection from its repository."""

    value = _source_projection_value(raw)
    expected = build_evidence_source_projection(root)
    if raw != expected:
        _fail("source-projection-stale")
    return value


def validate_gate8_source_surface(
    raw: bytes,
    root: Path,
    gate8_policy_raw: bytes,
) -> dict[str, object]:
    """Admit the complete candidate-ready source and immutable R3 history."""

    policy = load_gate8_policy(gate8_policy_raw)
    value = validate_evidence_source_projection(raw, root)
    rows = value.get("entries")
    if type(rows) is not list or any(type(row) is not dict for row in rows):
        _fail("gate8-source-entries")
    by_path = {row.get("path"): row for row in rows}
    if len(by_path) != len(rows) or any(type(path) is not str for path in by_path):
        _fail("gate8-source-entries")
    templates = policy.get("tracked_templates")
    tools = policy.get("tracked_gate8_tools")
    surface = policy.get("implementation_surface")
    linux = policy.get("linux_source_surface")
    if any(type(item) is not dict for item in (templates, tools, surface, linux)):
        _fail("gate8-source-policy")
    assert isinstance(templates, dict)
    assert isinstance(tools, dict)
    assert isinstance(surface, dict)
    assert isinstance(linux, dict)
    required_groups = (
        templates.get("paths"),
        tools.get("paths"),
        surface.get("current_required_paths"),
        surface.get("candidate_ready_additional_required_paths"),
    )
    if any(
        type(group) is not list or any(type(path) is not str for path in group)
        for group in required_groups
    ):
        _fail("gate8-source-policy")
    required = {
        path
        for group in required_groups
        for path in group  # type: ignore[union-attr]
    }
    if not required <= set(by_path) or any(
        by_path[path].get("byte_length", 0) <= 0 for path in required
    ):
        _fail("gate8-source-surface")
    expected_modes = {
        "tools/m2/generate_gate8.py": "100755",
        "tools/m2/learner_runner.py": "100755",
        "crates/gb-bootstrap/src/bin/gb-m2-gate8.rs": "100644",
    }
    if any(by_path[path].get("mode") != mode for path, mode in expected_modes.items()):
        _fail("gate8-source-mode")
    history_roots = linux.get("required_unignored_history_roots")
    history_paths_max = linux.get("history_paths_per_root_max")
    if (
        type(history_roots) is not list
        or len(history_roots) != 5
        or history_paths_max != 128
    ):
        _fail("gate8-source-policy")
    root = _regular_root(root)
    for relative in history_roots:
        if type(relative) is not str:
            _fail("gate8-source-history")
        history = root / _repo_path_text(relative)
        try:
            metadata = os.lstat(history)
            paths = tuple(history.rglob("*"))
        except OSError as error:
            raise Gate8Error("gate8-source-history") from error
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or len(paths) > history_paths_max
        ):
            _fail("gate8-source-history")
        for path in paths:
            path_metadata = os.lstat(path)
            if stat.S_ISLNK(path_metadata.st_mode):
                _fail("gate8-source-history")
            if stat.S_ISREG(path_metadata.st_mode):
                repository_relative = path.relative_to(root).as_posix()
                if repository_relative not in by_path:
                    _fail("gate8-source-history")
            elif not stat.S_ISDIR(path_metadata.st_mode):
                _fail("gate8-source-history")
    damage_raw = _read_repo_file(root, "spec/damage-policy-v1.toml")
    try:
        m2_policy.validate_r3_pre_clarification_archive(root, damage_raw)
        m2_policy.validate_r3_pre_damage_schema_archive(root, damage_raw)
        m2_policy.validate_r3_pre_independence_witness_archive(root, damage_raw)
        m2_policy.validate_r3_pre_gate6_convergence_archive(root, damage_raw)
    except m2_policy.PolicyError as error:
        raise Gate8Error("gate8-source-history") from error
    return value


def render_owner_projection(
    role_id: str, source_preimages: Mapping[str, bytes]
) -> bytes:
    """Render one owner projection from its complete named byte preimages."""

    if type(role_id) is not str or role_id not in _OWNER_ROLES:
        _fail("owner-projection-role")
    projection_id, source_paths = _OWNER_ROLES[role_id]
    if (
        not isinstance(source_preimages, Mapping)
        or set(source_preimages) != set(source_paths)
        or len(source_preimages) != len(source_paths)
        or any(type(raw) is not bytes or not raw for raw in source_preimages.values())
    ):
        _fail("owner-projection-sources")
    rows = []
    for path in sorted(source_paths, key=str.encode):
        raw = source_preimages[path]
        rows.append(
            {
                "byte_length": len(raw),
                "path": path,
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    return _canonical(
        {
            "projection_id": projection_id,
            "schema": OWNER_PROJECTION_SCHEMA,
            "source_rows": rows,
        },
        "owner-projection-manifest",
    )


def owner_projection_paths(role_id: str) -> tuple[str, ...]:
    """Return the exact ordered source paths for one frozen owner projection."""

    if type(role_id) is not str or role_id not in _OWNER_ROLES:
        _fail("owner-projection-role")
    return _OWNER_ROLES[role_id][1]


def build_owner_projection(root: Path, role_id: str) -> bytes:
    """Read and render one exact gate-1-through-4 owner projection."""

    if type(role_id) is not str or role_id not in _OWNER_ROLES:
        _fail("owner-projection-role")
    return render_owner_projection(
        role_id,
        {
            path: _read_repo_file(root, path)
            for path in _OWNER_ROLES[role_id][1]
        },
    )


def validate_owner_projection(
    raw: bytes, root: Path, role_id: str
) -> dict[str, object]:
    """Strictly parse and independently reproduce one owner projection."""

    value = _canonical_value(raw, "owner-projection-manifest")
    if set(value) != {"projection_id", "schema", "source_rows"}:
        _fail("owner-projection-shape")
    if value.get("schema") != OWNER_PROJECTION_SCHEMA:
        _fail("owner-projection-schema")
    if raw != build_owner_projection(root, role_id):
        _fail("owner-projection-stale")
    return value


def _damage_names() -> tuple[str, ...]:
    shards = tuple(
        f"damage-{family}-cases-{ordinal:04d}.json"
        for family, count in zip(
            _DAMAGE_FAMILIES, _DAMAGE_SHARD_COUNTS, strict=True
        )
        for ordinal in range(count)
    )
    gate6 = tuple(
        sorted(_DAMAGE_ROOT_FILES + _DAMAGE_FAMILY_FILES + shards, key=str.encode)
    )
    if len(gate6) != 72:
        raise AssertionError("gate-8 damage inventory cardinality")
    return gate6 + (_DAMAGE_PROOF_FILE,)


def render_damage_inventory(files: Mapping[str, bytes]) -> bytes:
    """Render the exact 72-file gate-6 inventory from regenerated bytes.

    The independence proof must also be supplied and admitted as the sole
    explicitly excluded directory file.  It is independently hashed by the
    cross-language manifest rather than folded into this inventory.
    """

    if not isinstance(files, Mapping):
        raise TypeError("damage files must be a mapping")
    expected = _damage_names()
    if (
        any(type(name) is not str or type(raw) is not bytes for name, raw in files.items())
        or set(files) != set(expected)
        or len(files) != len(expected)
    ):
        _fail("damage-inventory-files")
    total = 0
    rows = []
    for name in expected[:-1]:
        _repo_path_text(name)
        raw = files[name]
        if not 1 <= len(raw) <= _DAMAGE_FILE_BYTES_MAX:
            _fail("damage-inventory-file-limit")
        total += len(raw)
        if total > _DAMAGE_AGGREGATE_BYTES_MAX:
            _fail("damage-inventory-aggregate-limit")
        rows.append(
            {
                "byte_length": len(raw),
                "path": name,
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    proof = files[_DAMAGE_PROOF_FILE]
    if not 1 <= len(proof) <= _DAMAGE_FILE_BYTES_MAX:
        _fail("damage-inventory-proof")
    return _canonical(
        {
            "candidate_id": _CANDIDATE_ID,
            "file_rows": rows,
            "schema": DAMAGE_INVENTORY_SCHEMA,
        },
        "damage-inventory-manifest",
    )


def build_damage_inventory(root: Path) -> bytes:
    """Read and strictly inventory the exact retained gate-6/7 directory."""

    root = _regular_root(root)
    relative_root = f"artifacts/candidates/{_CANDIDATE_ID}/damage"
    damage_root = root / relative_root
    try:
        metadata = os.lstat(damage_root)
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            _fail("damage-inventory-root")
        entries = tuple(damage_root.iterdir())
    except Gate8Error:
        raise
    except OSError as error:
        raise Gate8Error("damage-inventory-root") from error
    expected = _damage_names()
    if (
        len(entries) != len(expected)
        or {entry.name for entry in entries} != set(expected)
    ):
        _fail("damage-inventory-allowlist")
    files = {
        name: _read_repo_file(
            root,
            f"{relative_root}/{name}",
            maximum=_DAMAGE_FILE_BYTES_MAX,
        )
        for name in expected
    }
    return render_damage_inventory(files)


def validate_damage_inventory(raw: bytes, files: Mapping[str, bytes]) -> dict[str, object]:
    """Strictly parse and independently reproduce one damage inventory."""

    value = _canonical_value(raw, "damage-inventory-manifest")
    if set(value) != {"candidate_id", "file_rows", "schema"}:
        _fail("damage-inventory-shape")
    if value.get("schema") != DAMAGE_INVENTORY_SCHEMA:
        _fail("damage-inventory-schema")
    if raw != render_damage_inventory(files):
        _fail("damage-inventory-stale")
    return value


def _candidate_sections(
    candidate_manifest_raw: bytes,
) -> tuple[dict[str, object], tuple[dict[str, object], ...]]:
    candidate = _canonical_value(candidate_manifest_raw, "semantic-candidate")
    if (
        candidate.get("schema") != _CANDIDATE_SCHEMA
        or candidate.get("profile_id") != _CANDIDATE_ID
        or candidate.get("profile_version") != _PROFILE_VERSION
    ):
        _fail("semantic-candidate")
    raw_rows = candidate.get("section_rows")
    if type(raw_rows) is not list or len(raw_rows) != _SECTION_COUNT:
        _fail("semantic-section-rows")
    rows: list[dict[str, object]] = []
    previous = 0
    for row in raw_rows:
        if type(row) is not dict:
            _fail("semantic-section-rows")
        section_id = row.get("section_id")
        if type(section_id) is not int or not previous < section_id <= 0xFFFF_FFFF:
            _fail("semantic-section-order")
        if (
            row.get("semantic_copy_count") != 1
            or type(row.get("fragment_count")) is not int
            or not 1 <= int(row["fragment_count"]) <= 0xFFFF
            or type(row.get("envelope_bytes")) is not int
            or not 22 <= int(row["envelope_bytes"]) <= _MAX_FILE_BYTES
        ):
            _fail("semantic-section-row")
        previous = section_id
        rows.append(row)
    if sum(int(row["fragment_count"]) for row in rows) != _LOGICAL_GROUP_COUNT:
        _fail("semantic-group-count")
    return candidate, tuple(rows)


def build_semantic_content_projection(
    candidate_manifest_raw: bytes,
    content_stream_raw: bytes,
    semantic_envelope_raw: bytes,
    section_envelopes: Sequence[tuple[int, bytes]],
    common_plain_blocks: Sequence[tuple[int, int, bytes]],
) -> bytes:
    """Render the exact semantic-content projection from regenerated bytes."""

    if (
        type(content_stream_raw) is not bytes
        or not 1 <= len(content_stream_raw) <= _MAX_FILE_BYTES
        or type(semantic_envelope_raw) is not bytes
        or not 1 <= len(semantic_envelope_raw) <= _MAX_FILE_BYTES
    ):
        _fail("semantic-input")
    candidate, section_rows = _candidate_sections(candidate_manifest_raw)
    if (
        candidate.get("semantic_envelope_sha256")
        != hashlib.sha256(semantic_envelope_raw).hexdigest()
    ):
        _fail("semantic-envelope-binding")
    semantic = _canonical_value(semantic_envelope_raw, "semantic-envelope")
    if semantic.get("schema") != "golden-board.m2-semantic-envelope/v0":
        _fail("semantic-envelope")
    if not isinstance(section_envelopes, Sequence) or isinstance(
        section_envelopes, (bytes, bytearray, str)
    ):
        raise TypeError("section envelopes must be a sequence")
    if not isinstance(common_plain_blocks, Sequence) or isinstance(
        common_plain_blocks, (bytes, bytearray, str)
    ):
        raise TypeError("common blocks must be a sequence")
    sections = tuple(section_envelopes)
    blocks = tuple(common_plain_blocks)
    if len(sections) != _SECTION_COUNT or len(blocks) != _LOGICAL_GROUP_COUNT:
        _fail("semantic-projection-count")
    expected_sections = {
        int(row["section_id"]): row for row in section_rows
    }
    section_by_id: dict[int, bytes] = {}
    decoded_by_id: dict[int, bootstrap.SectionEnvelope] = {}
    previous_section = 0
    section_preimage = bytearray(_SECTION_DOMAIN)
    section_preimage.extend(len(sections).to_bytes(8, "big"))
    for item in sections:
        if (
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not int
            or type(item[1]) is not bytes
        ):
            _fail("semantic-section-envelope")
        section_id, envelope = item
        row = expected_sections.get(section_id)
        if row is None or section_id <= previous_section:
            _fail("semantic-section-order")
        if len(envelope) != row["envelope_bytes"]:
            _fail("semantic-section-length")
        try:
            decoded = bootstrap.decode_section_envelope(envelope)
        except bootstrap.BootstrapReject as error:
            raise Gate8Error("semantic-section-envelope") from error
        if decoded.section_id != section_id:
            _fail("semantic-section-envelope")
        previous_section = section_id
        section_by_id[section_id] = envelope
        decoded_by_id[section_id] = decoded
        section_preimage.extend(_u32(section_id, "semantic-section-id"))
        section_preimage.extend(len(envelope).to_bytes(8, "big"))
        section_preimage.extend(envelope)
    if set(section_by_id) != set(expected_sections):
        _fail("semantic-section-set")

    by_section: dict[int, list[bytes]] = {section_id: [] for section_id in section_by_id}
    common_preimage = bytearray(_COMMON_DOMAIN)
    common_preimage.extend(len(blocks).to_bytes(8, "big"))
    previous_identity = (0, -1)
    for item in blocks:
        if (
            type(item) is not tuple
            or len(item) != 3
            or type(item[0]) is not int
            or type(item[1]) is not int
            or type(item[2]) is not bytes
        ):
            _fail("semantic-common-block")
        section_id, fragment_index, block = item
        identity = (section_id, fragment_index)
        row = expected_sections.get(section_id)
        if (
            row is None
            or identity <= previous_identity
            or not 0 <= fragment_index < int(row["fragment_count"])
            or len(block) != _COMMON_BLOCK_BYTES
        ):
            _fail("semantic-common-order")
        try:
            decoded = bootstrap.decode_common_block(block, _PROFILE_VERSION)
        except bootstrap.BootstrapReject as error:
            raise Gate8Error("semantic-common-block") from error
        if (
            decoded.section_id != section_id
            or decoded.semantic_copy_id != 0
            or decoded.fragment_index != fragment_index
            or decoded.fragment_count != row["fragment_count"]
            or decoded.section_envelope_length != row["envelope_bytes"]
        ):
            _fail("semantic-common-block")
        previous_identity = identity
        by_section[section_id].append(block)
        common_preimage.extend(_u32(section_id, "semantic-section-id"))
        common_preimage.extend(_u32(fragment_index, "semantic-fragment-index"))
        common_preimage.extend(_COMMON_BLOCK_BYTES.to_bytes(8, "big"))
        common_preimage.extend(block)
    for section_id, section_blocks in by_section.items():
        try:
            copy_id, envelope = bootstrap.assemble_semantic_copy(
                section_blocks, _PROFILE_VERSION
            )
        except bootstrap.BootstrapReject as error:
            raise Gate8Error("semantic-section-assembly") from error
        if copy_id != 0 or envelope != section_by_id[section_id]:
            _fail("semantic-section-assembly")

    try:
        inventory = bootstrap.decode_inventory(decoded_by_id[1].payload)
        frame_envelope = decoded_by_id[3]
        frame = bootstrap.decode_tier_frame(frame_envelope.payload, 3)
        bootstrap.validate_tier_against_inventory(
            frame, frame_envelope, inventory
        )
        assembled_content = bootstrap.assemble_content_stream(
            frame,
            {
                section_id: decoded_by_id[section_id].payload
                for section_id in frame.body_section_ids
            },
        )
    except (KeyError, bootstrap.BootstrapReject) as error:
        raise Gate8Error("semantic-content-stream") from error
    if assembled_content != content_stream_raw:
        _fail("semantic-content-stream")

    return _canonical(
        {
            "candidate_id": _CANDIDATE_ID,
            "common_plain_blocks_sha256": hashlib.sha256(common_preimage).hexdigest(),
            "content_stream_sha256": hashlib.sha256(content_stream_raw).hexdigest(),
            "schema": SEMANTIC_CONTENT_SCHEMA,
            "section_envelopes_sha256": hashlib.sha256(section_preimage).hexdigest(),
            "semantic_envelope_sha256": hashlib.sha256(semantic_envelope_raw).hexdigest(),
        },
        "semantic-content-manifest",
    )


def _carrier_bit(carrier_payload: bytes, index: int) -> int:
    return (carrier_payload[index // 8] >> (7 - index % 8)) & 1


def _clean_common_block(encoded: bytes) -> bytes:
    if type(encoded) is not bytes or len(encoded) != 216:
        _fail("semantic-encoded-unit")
    decoded = bytearray()
    for offset in range(0, len(encoded), 9):
        try:
            recovery = m2_codec.eh72_decode(encoded[offset : offset + 9])
        except m2_codec.CodecError as error:
            raise Gate8Error("semantic-encoded-unit") from error
        if recovery.state != "verified" or recovery.decoded is None:
            _fail("semantic-encoded-unit")
        decoded.extend(recovery.decoded)
    if len(decoded) != 192 or decoded[-1] != 0:
        _fail("semantic-encoded-unit")
    common = bytes(decoded[:-1])
    try:
        bootstrap.decode_common_block(common, _PROFILE_VERSION)
    except bootstrap.BootstrapReject as error:
        raise Gate8Error("semantic-common-block") from error
    return common


def build_semantic_content_projection_from_carrier(
    candidate_manifest_raw: bytes,
    carrier_raw: bytes,
    semantic_envelope_raw: bytes,
 ) -> SemanticContentProjection:
    """Extract the logical groups once from a freshly generated v7 carrier."""

    candidate, section_rows = _candidate_sections(candidate_manifest_raw)
    if type(carrier_raw) is not bytes or not 5 <= len(carrier_raw) <= _MAX_FILE_BYTES:
        _fail("semantic-carrier")
    if candidate.get("carrier_sha256") != hashlib.sha256(carrier_raw).hexdigest():
        _fail("semantic-carrier-binding")
    side = candidate.get("side")
    width = candidate.get("shell_width")
    mapping = candidate.get("mapping")
    raw_units = candidate.get("unit_rows")
    if (
        type(side) is not int
        or type(width) is not int
        or type(mapping) is not dict
        or type(raw_units) is not list
        or len(raw_units) != 1_841
    ):
        _fail("semantic-carrier-shape")
    cell_count = int.from_bytes(carrier_raw[:4], "big")
    if cell_count != side * side or len(carrier_raw) != 4 + (cell_count + 7) // 8:
        _fail("semantic-carrier-framing")
    payload = carrier_raw[4:]
    if cell_count % 8 and payload[-1] & ((1 << (8 - cell_count % 8)) - 1):
        _fail("semantic-carrier-padding")
    interior = side - 2 * width
    if interior <= 0:
        _fail("semantic-carrier-geometry")

    grouped: dict[tuple[int, int], dict[int, bytes]] = {}
    previous_id = 0
    for row in raw_units:
        if type(row) is not dict:
            _fail("semantic-unit-row")
        unit_id = row.get("physical_unit_id")
        section_id = row.get("section_id")
        fragment_index = row.get("fragment_index")
        replica_index = row.get("replica_index")
        factor = row.get("physical_replica_count")
        if (
            type(unit_id) is not int
            or unit_id != previous_id + 1
            or type(section_id) is not int
            or type(fragment_index) is not int
            or type(replica_index) is not int
            or type(factor) is not int
            or factor not in (1, 2, 5)
            or not 0 <= replica_index < factor
            or row.get("semantic_copy_id") != 0
            or row.get("transport_id") != "eh72-hier-repetition-v0"
            or row.get("encoded_bytes") != 216
            or row.get("logical_bit_count") != 1_728
        ):
            _fail("semantic-unit-row")
        previous_id = unit_id
        encoded_bits = bytearray(216)
        try:
            for bit_offset in range(1_728):
                physical = m2_carrier.map_unit_bit(mapping, unit_id, bit_offset)
                local_row, local_column = divmod(physical, interior)
                matrix_index = (local_row + width) * side + local_column + width
                encoded_bits[bit_offset // 8] |= _carrier_bit(
                    payload, matrix_index
                ) << (7 - bit_offset % 8)
        except (m2_carrier.CarrierError, IndexError, ValueError) as error:
            raise Gate8Error("semantic-unit-mapping") from error
        encoded = bytes(encoded_bits)
        if row.get("encoded_sha256") != hashlib.sha256(encoded).hexdigest():
            _fail("semantic-unit-hash")
        common = _clean_common_block(encoded)
        decoded = bootstrap.decode_common_block(common, _PROFILE_VERSION)
        if (
            decoded.section_id != section_id
            or decoded.semantic_copy_id != 0
            or decoded.fragment_index != fragment_index
        ):
            _fail("semantic-unit-identity")
        lanes = grouped.setdefault((section_id, fragment_index), {})
        if replica_index in lanes:
            _fail("semantic-unit-replica")
        lanes[replica_index] = common

    if len(grouped) != _LOGICAL_GROUP_COUNT:
        _fail("semantic-group-count")
    common_rows = []
    section_blocks: dict[int, list[bytes]] = {}
    factors = {
        (int(row["section_id"]), int(row["fragment_index"])):
        int(row["physical_replica_count"])
        for row in raw_units
    }
    for (section_id, fragment_index), lanes in sorted(grouped.items()):
        factor = factors[(section_id, fragment_index)]
        if set(lanes) != set(range(factor)) or len(set(lanes.values())) != 1:
            _fail("semantic-unit-replication")
        common = lanes[0]
        common_rows.append((section_id, fragment_index, common))
        section_blocks.setdefault(section_id, []).append(common)
    envelopes = []
    for row in section_rows:
        section_id = int(row["section_id"])
        blocks = section_blocks.get(section_id)
        if blocks is None:
            _fail("semantic-section-set")
        try:
            copy_id, envelope = bootstrap.assemble_semantic_copy(
                blocks, _PROFILE_VERSION
            )
        except bootstrap.BootstrapReject as error:
            raise Gate8Error("semantic-section-assembly") from error
        if copy_id != 0:
            _fail("semantic-section-assembly")
        envelopes.append((section_id, envelope))
    decoded_envelopes = {
        section_id: bootstrap.decode_section_envelope(envelope)
        for section_id, envelope in envelopes
    }
    try:
        inventory = bootstrap.decode_inventory(decoded_envelopes[1].payload)
        frame_envelope = decoded_envelopes[3]
        frame = bootstrap.decode_tier_frame(frame_envelope.payload, 3)
        bootstrap.validate_tier_against_inventory(
            frame, frame_envelope, inventory
        )
        content_stream_raw = bootstrap.assemble_content_stream(
            frame,
            {
                section_id: decoded_envelopes[section_id].payload
                for section_id in frame.body_section_ids
            },
        )
    except (KeyError, bootstrap.BootstrapReject) as error:
        raise Gate8Error("semantic-content-stream") from error
    canonical_bytes = build_semantic_content_projection(
        candidate_manifest_raw,
        content_stream_raw,
        semantic_envelope_raw,
        tuple(envelopes),
        tuple(common_rows),
    )
    return SemanticContentProjection(canonical_bytes, content_stream_raw)


def validate_semantic_content_projection(
    raw: bytes,
    candidate_manifest_raw: bytes,
    content_stream_raw: bytes,
    semantic_envelope_raw: bytes,
    section_envelopes: Sequence[tuple[int, bytes]],
    common_plain_blocks: Sequence[tuple[int, int, bytes]],
) -> dict[str, object]:
    """Strictly parse and independently reproduce a semantic projection."""

    value = _canonical_value(raw, "semantic-content-manifest")
    if set(value) != {
        "candidate_id",
        "common_plain_blocks_sha256",
        "content_stream_sha256",
        "schema",
        "section_envelopes_sha256",
        "semantic_envelope_sha256",
    }:
        _fail("semantic-content-shape")
    if value.get("schema") != SEMANTIC_CONTENT_SCHEMA:
        _fail("semantic-content-schema")
    expected = build_semantic_content_projection(
        candidate_manifest_raw,
        content_stream_raw,
        semantic_envelope_raw,
        section_envelopes,
        common_plain_blocks,
    )
    if raw != expected:
        _fail("semantic-content-stale")
    return value


def profile_tuple_manifest() -> bytes:
    """Return the exact canonical active-v7 profile tuple object."""

    return _canonical(
        {
            "local_check_id": "crc32c-v0",
            "mapping_id": "affine-slot-then-interior-v1",
            "physical_replica_counts": [1, 2, 5],
            "profile_id": _CANDIDATE_ID,
            "profile_version": _PROFILE_VERSION,
            "schema": "golden-board.m2-profile-tuple/v1",
            "section_check_id": "crc32c-v0",
            "semantic_copy_count": 1,
            "transport_id": "eh72-hier-repetition-v0",
        },
        "profile-tuple-manifest",
    )


def profile_tuple_identity() -> str:
    """Hash the exact canonical active-v7 profile tuple object."""

    return hashlib.sha256(profile_tuple_manifest()).hexdigest()


def _recipe_dependency_depth(package: bootstrap.RecipePackage) -> int:
    recipe_depths: dict[int, int] = {}
    maximum = 0
    for recipe in package.recipes:
        input_count = len(recipe.inputs)
        node_depths: dict[int, int] = {}
        for node in recipe.nodes:
            predecessors = [
                node_depths[value_id - input_count]
                for value_id in node.arguments
                if value_id > input_count
            ]
            if node.opcode == 22:
                body_depth = recipe_depths.get(node.auxiliary_u16)
                if body_depth is None:
                    _fail("metric-iterate-body")
                predecessors.append(body_depth)
            depth = 1 + (max(predecessors) if predecessors else 0)
            node_depths[node.node_id] = depth
        if not node_depths:
            _fail("metric-recipe-depth")
        recipe_depths[recipe.recipe_id] = max(node_depths.values())
        maximum = max(maximum, recipe_depths[recipe.recipe_id])
    return maximum


def _toml(raw: bytes, schema: str, reason: str) -> dict[str, object]:
    if type(raw) is not bytes or len(raw) > _MAX_FILE_BYTES:
        _fail(reason)
    try:
        document = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as error:
        raise Gate8Error(reason) from error
    if document.get("schema") != schema:
        _fail(reason)
    return document


def derive_candidate_metrics(
    recipient_package_raw: bytes,
    profile_limits_raw: bytes,
    route_data_raw: bytes,
    capacity_ledger_raw: bytes,
) -> dict[str, int]:
    """Independently derive the exact 19-field active-v7 metric map."""

    try:
        package = bootstrap.decode_recipe_package(
            recipient_package_raw, _PROFILE_VERSION
        )
    except bootstrap.BootstrapReject as error:
        raise Gate8Error("metric-recipient-package") from error
    limits = _toml(
        profile_limits_raw, "golden-board.profile-limits/v1", "metric-limits"
    )
    route = _canonical_value(route_data_raw, "metric-route")
    capacity = _canonical_value(capacity_ledger_raw, "metric-capacity")
    if (
        route.get("schema") != "golden-board.route-data/v1"
        or capacity.get("schema") != "golden-board.m2-capacity-ledger/v1"
        or capacity.get("profile_id") != _CANDIDATE_ID
    ):
        _fail("metric-owner")
    policy_ceiling = limits.get("policy_ceiling")
    semantic_capacity = limits.get("semantic_capacity")
    selected = limits.get("selected_manifestation")
    route_package = limits.get("route_package")
    ledger = capacity.get("ledger")
    facts = route.get("facts")
    if any(
        type(value) is not dict
        for value in (
            policy_ceiling,
            semantic_capacity,
            selected,
            route_package,
            ledger,
        )
    ) or type(facts) is not list:
        _fail("metric-owner")
    assert isinstance(policy_ceiling, dict)
    assert isinstance(semantic_capacity, dict)
    assert isinstance(selected, dict)
    assert isinstance(route_package, dict)
    assert isinstance(ledger, dict)
    package_sha256 = hashlib.sha256(recipient_package_raw).hexdigest()
    if (
        route_package.get("recipient_package_sha256") != package_sha256
        or route_package.get("recipient_package_bytes") != len(recipient_package_raw)
        or route_package.get("recipient_package_table_count") != len(package.tables)
        or route_package.get("recipient_package_table_payload_bytes")
        != package.table_payload_bytes
        or route_package.get("recipient_package_node_count")
        != package.total_node_count
        or route_package.get("recipient_package_edge_count")
        != package.total_edge_count
        or route_package.get("recipient_package_primitive_steps")
        != package.maximum_primitive_steps
        or route_package.get("recipient_package_peak_scratch_bytes")
        != package.peak_live_scratch_bytes
    ):
        _fail("metric-package-binding")
    side = selected.get("side")
    width = selected.get("shell_width")
    groups = selected.get("logical_group_count")
    protected = selected.get("protected_cells")
    total = selected.get("cells")
    carrier_bytes = selected.get("carrier_bytes")
    reserve_payload = semantic_capacity.get("reserve_payload_bytes")
    carrier_ceiling = policy_ceiling.get("carrier_bytes")
    worked = route_package.get("worked_record_bytes_by_sector")
    held = route_package.get("held_out_record_bytes_by_sector")
    if (
        any(
            type(value) is not int
            for value in (
                side,
                width,
                groups,
                protected,
                total,
                carrier_bytes,
                reserve_payload,
                carrier_ceiling,
            )
        )
        or type(worked) is not list
        or type(held) is not list
        or len(worked) != 4
        or len(held) != 4
        or any(type(value) is not int for value in worked + held)
    ):
        _fail("metric-owner")
    assert isinstance(side, int)
    assert isinstance(width, int)
    assert isinstance(groups, int)
    assert isinstance(protected, int)
    assert isinstance(total, int)
    assert isinstance(carrier_bytes, int)
    assert isinstance(reserve_payload, int)
    assert isinstance(carrier_ceiling, int)
    operation_kinds = {
        node.opcode for recipe in package.recipes for node in recipe.nodes
    }
    metrics = {
        "operation_kind_count": len(operation_kinds),
        "table_count": len(package.tables),
        "table_bytes": package.table_payload_bytes,
        "graph_nodes": package.total_node_count,
        "graph_edges": package.total_edge_count,
        "dependency_depth": _recipe_dependency_depth(package),
        "recipe_cells": ledger.get("shell_recipe_cells"),
        "worked_example_cells": 8 * sum(worked),
        "held_out_example_cells": 8 * sum(held),
        "shell_cells": 4 * width * (side - width),
        "convention_count": len(facts),
        "plain_bits": groups * _COMMON_BLOCK_BYTES * 8,
        "protected_bits": protected,
        "reserve_bits": reserve_payload * 8,
        "total_bits": total,
        "robustness_ppm": 0,
        "worst_case_work_units": ledger.get("worst_case_work_units"),
        "scratch_bytes": ledger.get("scratch_bytes"),
        "remaining_reserve_bytes": carrier_ceiling - carrier_bytes,
    }
    if (
        any(type(value) is not int or not 0 <= value <= canonical_manifest.MAX_U64 for value in metrics.values())
        or total != side * side
        or carrier_bytes != (total + 7) // 8
        or ledger.get("total_cells") != total
        or ledger.get("scratch_bytes") != package.peak_live_scratch_bytes
        or selected.get("protected_cells") != ledger.get("real_protected_cells", 0)
        + ledger.get("capacity_probe_cells", 0)
        + ledger.get("reserve_probe_cells", 0)
        + ledger.get("load_probe_cells", 0)
    ):
        _fail("metric-reconciliation")
    return metrics


def load_gate8_policy(raw: bytes) -> dict[str, object]:
    """Admit only the exact frozen pre-result Gate-8 owner bytes."""

    if type(raw) is not bytes:
        raise TypeError("gate-8 policy must be bytes")
    if hashlib.sha256(raw).hexdigest() != GATE8_POLICY_SHA256:
        _fail("gate8-policy-hash")
    policy = _toml(raw, "golden-board.m2-gate8-policy/v0", "gate8-policy")
    if (
        policy.get("policy_version") != 0
        or policy.get("status") != "pre-gate8-frozen"
        or policy.get("candidate_id") != _CANDIDATE_ID
        or policy.get("outcome_values_present") is not False
    ):
        _fail("gate8-policy")
    return policy


def load_gate8_verifier_refresh(raw: bytes) -> dict[str, object]:
    """Admit only the exact frozen one-way verifier refresh owner."""

    if type(raw) is not bytes:
        raise TypeError("gate-8 verifier refresh owner must be bytes")
    if hashlib.sha256(raw).hexdigest() != GATE8_VERIFIER_REFRESH_SHA256:
        _fail("gate8-verifier-refresh-hash")
    owner = _toml(
        raw,
        "golden-board.m2-gate8-verifier-refresh/v0",
        "gate8-verifier-refresh",
    )
    if (
        set(owner)
        != {
            "schema",
            "transition_version",
            "status",
            "candidate_id",
            "candidate_outcome_values_present",
            "historical_output_identity_values_present",
            "new_gate8_output_identity_values_present",
            "unknown_or_duplicate_keys",
            "authority",
            "transition",
            "prior_state",
            "new_acquisition",
            "archive",
            "roadmap_reopen",
            "reopen_cli",
            "regeneration",
            "release_repair",
            "candidate_ready_test_repair",
            "candidate_ready_runtime_test_repair",
            "candidate_ready_clean_snapshot_test_repair",
            "candidate_ready_provenance_input_repair",
            "candidate_ready_provenance_fixture_repair",
        }
        or owner.get("transition_version") != 0
        or owner.get("status") != "pre-apply-frozen"
        or owner.get("candidate_id") != _CANDIDATE_ID
        or owner.get("candidate_outcome_values_present") is not False
        or owner.get("historical_output_identity_values_present") is not True
        or owner.get("new_gate8_output_identity_values_present") is not False
        or owner.get("unknown_or_duplicate_keys") != "reject"
    ):
        _fail("gate8-verifier-refresh")
    authority = owner.get("authority")
    acquisition = owner.get("new_acquisition")
    reopen = owner.get("reopen_cli")
    repair = owner.get("release_repair")
    test_repair = owner.get("candidate_ready_test_repair")
    runtime_test_repair = owner.get("candidate_ready_runtime_test_repair")
    clean_snapshot_test_repair = owner.get(
        "candidate_ready_clean_snapshot_test_repair"
    )
    provenance_input_repair = owner.get(
        "candidate_ready_provenance_input_repair"
    )
    provenance_fixture_repair = owner.get(
        "candidate_ready_provenance_fixture_repair"
    )
    if (
        type(authority) is not dict
        or authority.get("gate8_policy_sha256")
        != f"sha256:{GATE8_POLICY_SHA256}"
        or authority.get("gate8_policy_path") != "spec/gate8-policy-v0.toml"
        or authority.get("roadmap_path") != "docs/roadmap.md"
        or authority.get("gate8_root") != "artifacts/gate8"
        or authority.get("report_path") != "reports/m2-feasibility-v0.json"
        or authority.get("acquisition_receipt_path")
        != "artifacts/linux/verifier-v0.env"
        or type(acquisition) is not dict
        or acquisition.get("receipt_sha256")
        != "sha256:315f9021f83ee8c6640af6ea6bcd58387287bcef42e7b27eaaf5f76b2187f6a2"
        or acquisition.get("receipt_byte_length") != 378
        or acquisition.get("image_digest")
        != "sha256:1b76a6d672c2d4b875302271f3cd5242200b6dc3d9a8491af611951e498ecd96"
        or type(reopen) is not dict
        or reopen.get("entrypoint") != "tools/m2/generate_gate8.py"
        or reopen.get("subcommand") != "reopen-verifier"
        or reopen.get("argv_order") != ["reopen-verifier"]
        or type(repair) is not dict
        or repair.get("status") != "pre-apply-frozen"
        or repair.get("prior_gate8_policy_sha256")
        != "sha256:9cce42cc5af70c2ef0111632138e381aff7978370c014ccf958568a5cd389768"
        or repair.get("prior_refresh_owner_sha256")
        != "sha256:8d807b6876f280545960c2efa8933dbda7769d169fcfe1404fecf79f3de9e82e"
        or repair.get("prior_report_sha256")
        != "sha256:f6da8e64635fcbca8f65baac2b14dedcaed45bef2479eff2e1acb56f4e760809"
        or repair.get("prior_roadmap_sha256")
        != "sha256:16116145b7db913cec1b322a6dccc1adefacdd52c9153aa4bd7913f14de8b418"
        or repair.get("archive_root")
        != "artifacts/linux/gate8-clean-linux-test-refresh-v0"
        or repair.get("archive_schema")
        != "golden-board.m2-gate8-clean-linux-test-refresh-archive/v0"
        or repair.get("archive_file_count") != 71
        or repair.get("archive_payload_bytes") != 11_436_098
        or repair.get("archive_manifest_bytes") != 11_824
        or repair.get("archive_manifest_sha256")
        != "sha256:5a1188fd65d9734bc3cb10f912af98dedd2282cd9d57a0d4edb41d8b0ed5d482"
        or repair.get("archive_payload_sequence_sha256")
        != "sha256:d76245a7b0d8cfc8071b6a4a68c3da1bb60000e1dfdbccaae62dfcdd35560d9a"
        or repair.get("pending_roadmap_sha256")
        != "sha256:153f66d0713c04d357c3bf980b3fde1feae328d7751099e5c9bb019c6f98b1f1"
        or repair.get("subcommand") != "reopen-clean-linux-tests"
        or repair.get("argv_order") != ["reopen-clean-linux-tests"]
        or type(test_repair) is not dict
        or set(test_repair)
        != {
            "status",
            "reason",
            "scope",
            "candidate_and_gates1_through_8",
            "test_rule",
            "prior_gate8_policy_sha256",
            "prior_refresh_owner_sha256",
            "prior_report_sha256",
            "prior_roadmap_sha256",
            "prior_evidence_source_sha256",
            "prior_generated_evidence_sha256",
            "prior_linux_attestation_sha256",
            "prior_selection_sha256",
            "archive_root",
            "archive_manifest_path",
            "archive_schema",
            "archive_file_count",
            "archive_payload_bytes",
            "archive_manifest_bytes",
            "archive_manifest_sha256",
            "archive_payload_sequence_domain",
            "archive_payload_sequence_sha256",
            "archive_rule",
            "pending_roadmap_sha256",
            "roadmap_rule",
            "subcommand",
            "argv_order",
            "write_order",
            "failure_rule",
            "idempotence",
            "regeneration",
        }
        or test_repair.get("status") != "pre-apply-frozen"
        or test_repair.get("prior_gate8_policy_sha256")
        != "sha256:9cce42cc5af70c2ef0111632138e381aff7978370c014ccf958568a5cd389768"
        or test_repair.get("prior_refresh_owner_sha256")
        != "sha256:a84082c13cae8080892c6a1723164d6c1354d828244f1964879ff98e927dab01"
        or test_repair.get("prior_report_sha256")
        != "sha256:1589678984f75c7d7c27fab3e06c39d23b99d7d80a0a1a8a3b9d2461e632ddcb"
        or test_repair.get("prior_roadmap_sha256")
        != "sha256:be9f9634cb9ec475240df1df592568cbe9ab74c7c052ec9a701e59f259c22281"
        or test_repair.get("prior_evidence_source_sha256")
        != "sha256:189734ba320682feccb88b34ae8d1a35fb36a295d253d599db385009b84186a6"
        or test_repair.get("prior_generated_evidence_sha256")
        != "sha256:16049609ac3465f138ad7c91e7eb69f2c3c190b67b83b3dcd233168c3b8225a1"
        or test_repair.get("prior_linux_attestation_sha256")
        != "sha256:1f3275d2bec434a38f94f4929e995c83e98780c5298f3a56198eae25f875191f"
        or test_repair.get("prior_selection_sha256")
        != "sha256:af3cdaaa194e5a07aa81e1918fb7a394dfe6dfaff46a07defb0ffead61ef7baf"
        or test_repair.get("archive_root")
        != "artifacts/linux/gate8-candidate-ready-test-refresh-v0"
        or test_repair.get("archive_manifest_path")
        != "artifacts/linux/gate8-candidate-ready-test-refresh-v0/archive-manifest-v0.json"
        or test_repair.get("archive_schema")
        != "golden-board.m2-gate8-candidate-ready-test-refresh-archive/v0"
        or test_repair.get("archive_file_count") != 71
        or test_repair.get("archive_payload_bytes") != 11_436_098
        or test_repair.get("archive_manifest_bytes") != 11_828
        or test_repair.get("archive_manifest_sha256")
        != "sha256:13bf603c0bac6ff5f44a5d115b8954a214f777d505a49ddc12c445f7fd5a760f"
        or test_repair.get("archive_payload_sequence_sha256")
        != "sha256:f378a44cdea3c65acf2275346b9b939c4467e9f7b330a873c1cda2339906b3b0"
        or test_repair.get("pending_roadmap_sha256")
        != "sha256:153f66d0713c04d357c3bf980b3fde1feae328d7751099e5c9bb019c6f98b1f1"
        or test_repair.get("subcommand") != "reopen-candidate-ready-tests"
        or test_repair.get("argv_order") != ["reopen-candidate-ready-tests"]
        or test_repair.get("write_order")
        != ["archive", "roadmap-In-progress", "remove-report", "remove-gate8-tree"]
        or type(runtime_test_repair) is not dict
        or set(runtime_test_repair) != set(test_repair)
        or runtime_test_repair.get("status") != "pre-apply-frozen"
        or runtime_test_repair.get("prior_gate8_policy_sha256")
        != "sha256:9cce42cc5af70c2ef0111632138e381aff7978370c014ccf958568a5cd389768"
        or runtime_test_repair.get("prior_refresh_owner_sha256")
        != "sha256:4b2ab5a9dacd4f10c76a42673b2855be68b8a30abdc4ecc1f8b5ca52f3debce3"
        or runtime_test_repair.get("prior_report_sha256")
        != "sha256:0bf75dac0bb3b1d71376885be946cb591d4e8970fd3686b1784c2165b3a3ede1"
        or runtime_test_repair.get("prior_roadmap_sha256")
        != "sha256:cf121dfa99390ba0b73b88c8eb1aff20667d6e47569ecfc138763600929f27e0"
        or runtime_test_repair.get("prior_evidence_source_sha256")
        != "sha256:0d743b09c0a180e92b0f12fe9cfeb213b59ce30d4748256ef40b2420aaf8dc3b"
        or runtime_test_repair.get("prior_generated_evidence_sha256")
        != "sha256:ac5a52d302665c603298c8821c28d35b0fca9d461d0e1ed80e081d3d785795c5"
        or runtime_test_repair.get("prior_linux_attestation_sha256")
        != "sha256:d3ca34196d8235aade12e7fe0d140b966cb4fa773e2d0d0a1ff1fa730b93baca"
        or runtime_test_repair.get("prior_selection_sha256")
        != "sha256:af3cdaaa194e5a07aa81e1918fb7a394dfe6dfaff46a07defb0ffead61ef7baf"
        or runtime_test_repair.get("archive_root")
        != "artifacts/linux/gate8-candidate-ready-runtime-test-refresh-v0"
        or runtime_test_repair.get("archive_manifest_path")
        != "artifacts/linux/gate8-candidate-ready-runtime-test-refresh-v0/archive-manifest-v0.json"
        or runtime_test_repair.get("archive_schema")
        != "golden-board.m2-gate8-candidate-ready-runtime-test-refresh-archive/v0"
        or runtime_test_repair.get("archive_file_count") != 71
        or runtime_test_repair.get("archive_payload_bytes") != 11_436_099
        or runtime_test_repair.get("archive_manifest_bytes") != 11_836
        or runtime_test_repair.get("archive_manifest_sha256")
        != "sha256:5f6932d350d2f418ad23290b92b983489e8fab077524209e9f1375e1738607f5"
        or runtime_test_repair.get("archive_payload_sequence_sha256")
        != "sha256:e00576ade3267b94cb0b25b5f313eb1d8a25cc50f639bf264cfef1c07ae3d290"
        or runtime_test_repair.get("pending_roadmap_sha256")
        != "sha256:153f66d0713c04d357c3bf980b3fde1feae328d7751099e5c9bb019c6f98b1f1"
        or runtime_test_repair.get("subcommand")
        != "reopen-candidate-ready-runtime-tests"
        or runtime_test_repair.get("argv_order")
        != ["reopen-candidate-ready-runtime-tests"]
        or runtime_test_repair.get("write_order")
        != ["archive", "roadmap-In-progress", "remove-report", "remove-gate8-tree"]
        or type(clean_snapshot_test_repair) is not dict
        or set(clean_snapshot_test_repair) != set(test_repair)
        or clean_snapshot_test_repair.get("status") != "pre-apply-frozen"
        or clean_snapshot_test_repair.get("prior_gate8_policy_sha256")
        != "sha256:9cce42cc5af70c2ef0111632138e381aff7978370c014ccf958568a5cd389768"
        or clean_snapshot_test_repair.get("prior_refresh_owner_sha256")
        != "sha256:f6b7c2ba3abf299e8a0822417e35ffc181d2b12070bfa937c3266a8a21eb662f"
        or clean_snapshot_test_repair.get("prior_report_sha256")
        != "sha256:4e039eb356a2153d86cf1a5d4db5af2aa7d15f64bce97902cd11d0e6bcb135a8"
        or clean_snapshot_test_repair.get("prior_roadmap_sha256")
        != "sha256:b1f884836b76b08b505a33fc66549a4b0ea3462820401ed1661834717599044e"
        or clean_snapshot_test_repair.get("prior_evidence_source_sha256")
        != "sha256:1a54cd22226e56587f200741b74e344e71ba0baceec778da86f8da7e503195b0"
        or clean_snapshot_test_repair.get("prior_generated_evidence_sha256")
        != "sha256:c2ffcb91e465be35461fdcb9f20b3ee86528ed2bb4fc0218895435131142152b"
        or clean_snapshot_test_repair.get("prior_linux_attestation_sha256")
        != "sha256:d4893a6830a7e16566189e44f54575fc302cf30b400659af9ce313c9c1aa1074"
        or clean_snapshot_test_repair.get("prior_selection_sha256")
        != "sha256:af3cdaaa194e5a07aa81e1918fb7a394dfe6dfaff46a07defb0ffead61ef7baf"
        or clean_snapshot_test_repair.get("archive_root")
        != "artifacts/linux/gate8-candidate-ready-clean-snapshot-refresh-v0"
        or clean_snapshot_test_repair.get("archive_manifest_path")
        != "artifacts/linux/gate8-candidate-ready-clean-snapshot-refresh-v0/archive-manifest-v0.json"
        or clean_snapshot_test_repair.get("archive_schema")
        != "golden-board.m2-gate8-candidate-ready-clean-snapshot-refresh-archive/v0"
        or clean_snapshot_test_repair.get("archive_file_count") != 71
        or clean_snapshot_test_repair.get("archive_payload_bytes") != 11_436_099
        or clean_snapshot_test_repair.get("archive_manifest_bytes") != 11_838
        or clean_snapshot_test_repair.get("archive_manifest_sha256")
        != "sha256:fadd7a64769bc944c7416280d3bfb7c5cbd61a1f7c4211bc173abe6a752f0762"
        or clean_snapshot_test_repair.get("archive_payload_sequence_sha256")
        != "sha256:a0fea678870075dca724c66f776d0c0eea0a180edcea1b8035fba413392efa38"
        or clean_snapshot_test_repair.get("pending_roadmap_sha256")
        != "sha256:153f66d0713c04d357c3bf980b3fde1feae328d7751099e5c9bb019c6f98b1f1"
        or clean_snapshot_test_repair.get("subcommand")
        != "reopen-candidate-ready-clean-snapshot-tests"
        or clean_snapshot_test_repair.get("argv_order")
        != ["reopen-candidate-ready-clean-snapshot-tests"]
        or clean_snapshot_test_repair.get("write_order")
        != ["archive", "roadmap-In-progress", "remove-report", "remove-gate8-tree"]
        or type(provenance_input_repair) is not dict
        or set(provenance_input_repair)
        != (set(test_repair) - {"test_rule"}) | {"repair_rule"}
        or provenance_input_repair.get("status") != "pre-apply-frozen"
        or provenance_input_repair.get("prior_gate8_policy_sha256")
        != "sha256:9cce42cc5af70c2ef0111632138e381aff7978370c014ccf958568a5cd389768"
        or provenance_input_repair.get("prior_refresh_owner_sha256")
        != "sha256:7dbd1d591aebd50ea2381681787c175a872bee906e28e9412b9187d1fa48e0e5"
        or provenance_input_repair.get("prior_report_sha256")
        != "sha256:9d23768ab807954a627aa5a83ddefd2522eddedc05dd103c173442c2f6b945db"
        or provenance_input_repair.get("prior_roadmap_sha256")
        != "sha256:818c8f653edcdb4269db391980c6609b8d7424bcbed8bf4ff4b01e66c7c82be9"
        or provenance_input_repair.get("prior_evidence_source_sha256")
        != "sha256:19a81497c591b107eafd4db86445803c908a517d4a925880d44a8686b5f044a4"
        or provenance_input_repair.get("prior_generated_evidence_sha256")
        != "sha256:ac4a24da19e0bedf462c2481865e30ffb4af47b7d5226b44e6973d518ccd9f94"
        or provenance_input_repair.get("prior_linux_attestation_sha256")
        != "sha256:ea046fbca0ab10718c65f6e0d3614375589965e5523f4ec180d4eb48c2a4717f"
        or provenance_input_repair.get("prior_selection_sha256")
        != "sha256:af3cdaaa194e5a07aa81e1918fb7a394dfe6dfaff46a07defb0ffead61ef7baf"
        or provenance_input_repair.get("archive_root")
        != "artifacts/linux/gate8-candidate-ready-provenance-input-refresh-v0"
        or provenance_input_repair.get("archive_manifest_path")
        != "artifacts/linux/gate8-candidate-ready-provenance-input-refresh-v0/archive-manifest-v0.json"
        or provenance_input_repair.get("archive_schema")
        != "golden-board.m2-gate8-candidate-ready-provenance-input-refresh-archive/v0"
        or provenance_input_repair.get("archive_file_count") != 71
        or provenance_input_repair.get("archive_payload_bytes") != 11_436_099
        or provenance_input_repair.get("archive_manifest_bytes") != 11_840
        or provenance_input_repair.get("archive_manifest_sha256")
        != "sha256:07aed69df68caae925ec29c75433db214fb47f8a1d8b8b1ea524806fde656803"
        or provenance_input_repair.get("archive_payload_sequence_sha256")
        != "sha256:62e0b1b8bd1cfcfc2733ae207a5be882f991de0080c0c63c9988b71e0eacd2d5"
        or provenance_input_repair.get("pending_roadmap_sha256")
        != "sha256:153f66d0713c04d357c3bf980b3fde1feae328d7751099e5c9bb019c6f98b1f1"
        or provenance_input_repair.get("subcommand")
        != "reopen-candidate-ready-provenance-input"
        or provenance_input_repair.get("argv_order")
        != ["reopen-candidate-ready-provenance-input"]
        or provenance_input_repair.get("write_order")
        != ["archive", "roadmap-In-progress", "remove-report", "remove-gate8-tree"]
        or type(provenance_fixture_repair) is not dict
        or set(provenance_fixture_repair)
        != set(test_repair)
        or provenance_fixture_repair.get("status") != "pre-apply-frozen"
        or provenance_fixture_repair.get("prior_gate8_policy_sha256")
        != "sha256:fd53145eeb5d0d5578b8cb1aff980039c999839516528b309a626dd62e52794e"
        or provenance_fixture_repair.get("prior_refresh_owner_sha256")
        != "sha256:58d229da7b72451a03293fdb9db921dda59f77f4be8a17dce2a5de3b5daacd29"
        or provenance_fixture_repair.get("prior_report_sha256")
        != "sha256:d4f3170059a605541029a8ae69288e2a1f718fea9881e67ca12456f0b9d76f0f"
        or provenance_fixture_repair.get("prior_roadmap_sha256")
        != "sha256:9d375aff96dbc7ae029468dfc687f2c0d33c9b9c3c446daf4cbf7641bdbd6f66"
        or provenance_fixture_repair.get("prior_evidence_source_sha256")
        != "sha256:32d5464337eee49a3944a9e846d72268f5006f034a8de408b7f2247974551746"
        or provenance_fixture_repair.get("prior_generated_evidence_sha256")
        != "sha256:0f314946d8ccb104513bea6cfc7356bd240f2c3f530f7db7c6e6e8121f1d3659"
        or provenance_fixture_repair.get("prior_linux_attestation_sha256")
        != "sha256:dea3ad41b42ca8c5562eba73b0755cce67824edd7b5b54a6ef08048f5212e431"
        or provenance_fixture_repair.get("prior_selection_sha256")
        != "sha256:af3cdaaa194e5a07aa81e1918fb7a394dfe6dfaff46a07defb0ffead61ef7baf"
        or provenance_fixture_repair.get("archive_root")
        != "artifacts/linux/gate8-provenance-fixture-refresh-v0"
        or provenance_fixture_repair.get("archive_manifest_path")
        != "artifacts/linux/gate8-provenance-fixture-refresh-v0/archive-manifest-v0.json"
        or provenance_fixture_repair.get("archive_schema")
        != "golden-board.m2-gate8-provenance-fixture-refresh-archive/v0"
        or provenance_fixture_repair.get("archive_file_count") != 71
        or provenance_fixture_repair.get("archive_payload_bytes") != 11_436_100
        or provenance_fixture_repair.get("archive_manifest_bytes") != 11_826
        or provenance_fixture_repair.get("archive_manifest_sha256")
        != "sha256:16c9692dcb32802e77f4c3e56ce34807e05227d4f4a0164ccb2f5726a563c418"
        or provenance_fixture_repair.get("archive_payload_sequence_sha256")
        != "sha256:af4d10df67057564200a3c1efaac7ca9f619f246cffefe11f8e8296add0c3ee0"
        or provenance_fixture_repair.get("pending_roadmap_sha256")
        != "sha256:153f66d0713c04d357c3bf980b3fde1feae328d7751099e5c9bb019c6f98b1f1"
        or provenance_fixture_repair.get("subcommand")
        != "reopen-provenance-fixtures"
        or provenance_fixture_repair.get("argv_order")
        != ["reopen-provenance-fixtures"]
        or provenance_fixture_repair.get("write_order")
        != ["archive", "roadmap-In-progress", "remove-report", "remove-gate8-tree"]
    ):
        _fail("gate8-verifier-refresh-binding")
    return owner


def _linux_acquisition_receipt_bytes(policy: Mapping[str, object]) -> bytes:
    receipt = policy.get("linux_acquisition_receipt")
    if type(receipt) is not dict:
        _fail("linux-image-evidence")
    keys = receipt.get("key_order")
    if keys != [
        "schema",
        "image",
        "image_id",
        "platform",
        "contract",
        "base",
        "dockerfile_sha256",
    ]:
        _fail("linux-image-evidence")
    rows: list[bytes] = []
    for key in keys:
        value = receipt.get(key)
        if type(value) is not str or not value or "\n" in value or "\r" in value:
            _fail("linux-image-evidence")
        if key == "dockerfile_sha256":
            if not value.startswith("sha256:"):
                _fail("linux-image-evidence")
            value = value[7:]
        try:
            rows.append(f"{key}={value}\n".encode("ascii"))
        except UnicodeError as error:
            raise Gate8Error("linux-image-evidence") from error
    return b"".join(rows)


def parse_linux_acquisition_receipt(
    raw: bytes, gate8_policy_raw: bytes
) -> dict[str, str]:
    """Strictly admit the exact current seven-line Linux acquisition receipt."""

    if type(raw) is not bytes or type(gate8_policy_raw) is not bytes:
        raise TypeError("Linux acquisition receipt inputs must be bytes")
    policy = load_gate8_policy(gate8_policy_raw)
    receipt = policy.get("linux_acquisition_receipt")
    if type(receipt) is not dict:
        _fail("linux-image-evidence")
    expected = _linux_acquisition_receipt_bytes(policy)
    expected_hash = receipt.get("sha256")
    if (
        raw != expected
        or len(raw) != receipt.get("byte_length")
        or type(expected_hash) is not str
        or not expected_hash.startswith("sha256:")
        or hashlib.sha256(raw).hexdigest() != expected_hash[7:]
        or b"\r" in raw
    ):
        _fail("linux-image-evidence")
    values: dict[str, str] = {}
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeError as error:
        raise Gate8Error("linux-image-evidence") from error
    for line in lines:
        key, separator, value = line.partition("=")
        if not separator or not key or key in values or not value:
            _fail("linux-image-evidence")
        values[key] = value
    return values


def _artifact_manifest(
    raw: bytes,
    *,
    schema: str,
    reason: str,
) -> dict[str, object]:
    value = _canonical_value(raw, reason)
    if value.get("schema") != schema:
        _fail(reason)
    return value


def _validate_artifact_preimages(artifacts: Mapping[str, bytes]) -> None:
    if not isinstance(artifacts, Mapping):
        raise TypeError("Gate-8 artifacts must be a mapping")
    if (
        tuple(artifacts) != _ARTIFACT_IDS
        or any(type(raw) is not bytes for raw in artifacts.values())
        or any(not 1 <= len(raw) <= 1_048_576 for raw in artifacts.values())
    ):
        _fail("producer-artifacts")
    semantic = _artifact_manifest(
        artifacts["semantic-content-projection"],
        schema=SEMANTIC_CONTENT_SCHEMA,
        reason="producer-semantic",
    )
    candidate_raw = artifacts["candidate-manifest"]
    candidate = _artifact_manifest(
        candidate_raw,
        schema=_CANDIDATE_SCHEMA,
        reason="producer-candidate",
    )
    if (
        candidate.get("profile_id") != _CANDIDATE_ID
        or candidate.get("profile_version") != _PROFILE_VERSION
        or hashlib.sha256(candidate_raw).hexdigest() != _CANDIDATE_MANIFEST_SHA256
        or semantic.get("candidate_id") != _CANDIDATE_ID
        or semantic.get("semantic_envelope_sha256")
        != candidate.get("semantic_envelope_sha256")
    ):
        _fail("producer-candidate")
    side = candidate.get("side")
    if type(side) is not int:
        _fail("producer-candidate")
    carrier = artifacts["carrier"]
    count = int.from_bytes(carrier[:4], "big") if len(carrier) >= 4 else -1
    if (
        candidate.get("carrier_sha256") != hashlib.sha256(carrier).hexdigest()
        or count != side**2
        or len(carrier) != 4 + (count + 7) // 8
    ):
        _fail("producer-carrier")
    for artifact_id, schema, candidate_field in (
        (
            "ownership-ledger",
            "golden-board.m2-ownership-ledger/v1",
            "ownership_sha256",
        ),
        (
            "capacity-ledger",
            "golden-board.m2-capacity-ledger/v1",
            "capacity_ledger_sha256",
        ),
        (
            "density-ledger",
            "golden-board.m2-density-ledger/v0",
            "density_ledger_sha256",
        ),
    ):
        ledger_raw = artifacts[artifact_id]
        ledger = _artifact_manifest(
            ledger_raw, schema=schema, reason="producer-ledger"
        )
        if (
            ledger.get("profile_id") != _CANDIDATE_ID
            or (
                artifact_id != "ownership-ledger"
                and ledger.get("carrier_sha256")
                != hashlib.sha256(carrier).hexdigest()
            )
            or candidate.get(candidate_field) != hashlib.sha256(ledger_raw).hexdigest()
        ):
            _fail("producer-ledger")
    inventory = _artifact_manifest(
        artifacts["damage-bundle-inventory"],
        schema=DAMAGE_INVENTORY_SCHEMA,
        reason="producer-damage-inventory",
    )
    proof_raw = artifacts["independence-proof"]
    proof = _artifact_manifest(
        proof_raw,
        schema="golden-board.m2-independence-proof/v1",
        reason="producer-proof",
    )
    if (
        inventory.get("candidate_id") != _CANDIDATE_ID
        or proof.get("profile_id") != _CANDIDATE_ID
        or proof.get("candidate_manifest_sha256") != _CANDIDATE_MANIFEST_SHA256
        or not isinstance(proof.get("summary"), dict)
        or proof["summary"].get("result") != "pass"  # type: ignore[index]
    ):
        _fail("producer-gate7")


def render_producer_receipt(
    producer_id: str,
    artifacts: Mapping[str, bytes],
) -> bytes:
    """Render one independently generated eight-artifact receipt."""

    if type(producer_id) is not str or producer_id not in _PRODUCER_IDS:
        _fail("producer-id")
    _validate_artifact_preimages(artifacts)
    return _canonical(
        {
            "artifact_rows": [
                {
                    "artifact_id": artifact_id,
                    "sha256": hashlib.sha256(artifacts[artifact_id]).hexdigest(),
                }
                for artifact_id in _ARTIFACT_IDS
            ],
            "candidate_id": _CANDIDATE_ID,
            "producer_id": producer_id,
            "schema": PRODUCER_RECEIPT_SCHEMA,
        },
        "producer-receipt",
    )


def _producer_receipt_value(
    raw: bytes,
    expected_producer_id: str | None = None,
) -> dict[str, object]:
    value = _canonical_value(raw, "producer-receipt")
    if set(value) != {"artifact_rows", "candidate_id", "producer_id", "schema"}:
        _fail("producer-receipt-shape")
    producer_id = value.get("producer_id")
    if (
        value.get("schema") != PRODUCER_RECEIPT_SCHEMA
        or value.get("candidate_id") != _CANDIDATE_ID
        or type(producer_id) is not str
        or producer_id not in _PRODUCER_IDS
        or (expected_producer_id is not None and producer_id != expected_producer_id)
    ):
        _fail("producer-receipt-binding")
    rows = value.get("artifact_rows")
    if type(rows) is not list or len(rows) != len(_ARTIFACT_IDS):
        _fail("producer-receipt-rows")
    for artifact_id, row in zip(_ARTIFACT_IDS, rows, strict=True):
        if (
            type(row) is not dict
            or set(row) != {"artifact_id", "sha256"}
            or row.get("artifact_id") != artifact_id
            or not _hex64(row.get("sha256"))
        ):
            _fail("producer-receipt-rows")
    return value


def parse_producer_receipt(
    raw: bytes,
    producer_id: str | None = None,
) -> dict[str, object]:
    """Strictly parse one canonical receipt without another producer preimage."""

    return _producer_receipt_value(raw, producer_id)


def validate_producer_receipt(
    raw: bytes,
    producer_id: str,
    artifacts: Mapping[str, bytes],
) -> dict[str, object]:
    """Strictly reproduce one producer receipt from its private preimages."""

    value = _producer_receipt_value(raw, producer_id)
    if raw != render_producer_receipt(producer_id, artifacts):
        _fail("producer-receipt-stale")
    return value


def render_linux_verification_input(
    evidence_source_raw: bytes,
    native_receipts: Mapping[str, bytes],
) -> bytes:
    """Bind two fresh native receipts to one exact clean-source projection."""

    try:
        _source_projection_value(evidence_source_raw)
    except Gate8Error as error:
        raise Gate8Error("linux-input-source") from error
    native_ids = ("native-python", "native-rust")
    if (
        not isinstance(native_receipts, Mapping)
        or tuple(native_receipts) != native_ids
        or any(type(raw) is not bytes for raw in native_receipts.values())
        or any(not 1 <= len(raw) <= 1_048_576 for raw in native_receipts.values())
    ):
        _fail("linux-input-receipts")
    rows = []
    for producer_id in native_ids:
        raw = native_receipts[producer_id]
        _producer_receipt_value(raw, producer_id)
        rows.append(
            {
                "byte_length": len(raw),
                "path": f"{producer_id}.json",
                "producer_id": producer_id,
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    return _canonical(
        {
            "candidate_id": _CANDIDATE_ID,
            "evidence_source_projection_sha256": hashlib.sha256(
                evidence_source_raw
            ).hexdigest(),
            "native_receipt_rows": rows,
            "schema": LINUX_VERIFICATION_INPUT_SCHEMA,
        },
        "linux-verification-input",
    )


def validate_linux_verification_input(
    raw: bytes,
    evidence_source_raw: bytes,
    native_receipts: Mapping[str, bytes],
) -> dict[str, object]:
    """Strictly reproduce the transient read-only Linux input manifest."""

    value = _canonical_value(raw, "linux-verification-input")
    if set(value) != {
        "candidate_id",
        "evidence_source_projection_sha256",
        "native_receipt_rows",
        "schema",
    } or value.get("schema") != LINUX_VERIFICATION_INPUT_SCHEMA:
        _fail("linux-verification-input-shape")
    if raw != render_linux_verification_input(
        evidence_source_raw, native_receipts
    ):
        _fail("linux-verification-input-stale")
    return value


def render_cross_language_manifest(
    receipts: Mapping[str, bytes],
    retained_candidate_manifest_raw: bytes,
) -> bytes:
    """Project four independently produced receipts into one closed manifest."""

    if not isinstance(receipts, Mapping):
        raise TypeError("producer receipts must be a mapping")
    if tuple(receipts) != _PRODUCER_IDS or any(
        type(raw) is not bytes for raw in receipts.values()
    ):
        _fail("cross-language-receipts")
    candidate = _artifact_manifest(
        retained_candidate_manifest_raw,
        schema=_CANDIDATE_SCHEMA,
        reason="cross-language-candidate",
    )
    if (
        candidate.get("profile_id") != _CANDIDATE_ID
        or hashlib.sha256(retained_candidate_manifest_raw).hexdigest()
        != _CANDIDATE_MANIFEST_SHA256
    ):
        _fail("cross-language-candidate")
    values = {
        producer_id: _producer_receipt_value(receipts[producer_id], producer_id)
        for producer_id in _PRODUCER_IDS
    }
    receipt_rows = {
        producer_id: {
            str(row["artifact_id"]): str(row["sha256"])
            for row in value["artifact_rows"]  # type: ignore[index]
        }
        for producer_id, value in values.items()
    }
    artifact_rows = []
    for artifact_id in _ARTIFACT_IDS:
        digests = [receipt_rows[producer][artifact_id] for producer in _PRODUCER_IDS]
        artifact_rows.append(
            {
                "artifact_id": artifact_id,
                "native_python_sha256": digests[0],
                "native_rust_sha256": digests[1],
                "linux_python_sha256": digests[2],
                "linux_rust_sha256": digests[3],
                "result": "pass" if len(set(digests)) == 1 else "fail",
            }
        )
    return _canonical(
        {
            "artifact_rows": artifact_rows,
            "candidate_id": _CANDIDATE_ID,
            "candidate_manifest_sha256": _CANDIDATE_MANIFEST_SHA256,
            "schema": CROSS_LANGUAGE_SCHEMA,
            "summary": {
                "artifact_count": len(_ARTIFACT_IDS),
                "result": (
                    "pass"
                    if all(row["result"] == "pass" for row in artifact_rows)
                    else "fail"
                ),
            },
        },
        "cross-language-manifest",
    )


def validate_cross_language_manifest(
    raw: bytes,
    receipts: Mapping[str, bytes],
    retained_candidate_manifest_raw: bytes,
) -> dict[str, object]:
    """Strictly reproduce the four-producer cross-language manifest."""

    value = _canonical_value(raw, "cross-language-manifest")
    if set(value) != {
        "artifact_rows",
        "candidate_id",
        "candidate_manifest_sha256",
        "schema",
        "summary",
    } or value.get("schema") != CROSS_LANGUAGE_SCHEMA:
        _fail("cross-language-shape")
    if raw != render_cross_language_manifest(
        receipts, retained_candidate_manifest_raw
    ):
        _fail("cross-language-stale")
    return value


def build_candidate_row(
    metrics: Mapping[str, int],
    profile_policy_raw: bytes,
    cross_language_raw: bytes,
) -> dict[str, object]:
    """Build the sole candidate-ready row after all eight automated gates."""

    if not isinstance(metrics, Mapping) or tuple(metrics) != _METRIC_KEYS:
        _fail("candidate-metrics")
    if any(
        type(value) is not int or not 0 <= value <= canonical_manifest.MAX_U64
        for value in metrics.values()
    ):
        _fail("candidate-metrics")
    profile = _toml(
        profile_policy_raw, "golden-board.profile-policy/v1", "candidate-policy"
    )
    if (
        profile.get("policy_version") != 1
        or hashlib.sha256(profile_policy_raw).hexdigest()
        != _PROFILE_POLICY_SHA256
    ):
        _fail("candidate-policy")
    cross = _canonical_value(cross_language_raw, "candidate-cross-language")
    if (
        cross.get("schema") != CROSS_LANGUAGE_SCHEMA
        or cross.get("candidate_id") != _CANDIDATE_ID
        or not isinstance(cross.get("summary"), dict)
        or cross["summary"].get("result") != "pass"  # type: ignore[index]
    ):
        _fail("candidate-cross-language")
    hard_gates = {key: "pass" for key in _HARD_GATE_KEYS[:-1]}
    hard_gates[_HARD_GATE_KEYS[-1]] = "not_evaluated"
    return {
        "candidate_id": _CANDIDATE_ID,
        "tuple_identity": profile_tuple_identity(),
        "policy_identity": hashlib.sha256(profile_policy_raw).hexdigest(),
        "complexity_class": "C1",
        "metrics": dict(metrics),
        "hard_gates": hard_gates,
        "disposition": "preferred",
        "reason_code": "sole-candidate-pass",
        "reason": "Sole active R3 candidate passed automated gates 1 through 8.",
    }


def render_selection(
    candidate_row: Mapping[str, object],
    cross_language_raw: bytes,
    profile_policy_raw: bytes,
) -> bytes:
    """Render the exact six-step singleton R3 selection recomputation."""

    if not isinstance(candidate_row, Mapping):
        raise TypeError("candidate row must be a mapping")
    if tuple(candidate_row) != (
        "candidate_id",
        "tuple_identity",
        "policy_identity",
        "complexity_class",
        "metrics",
        "hard_gates",
        "disposition",
        "reason_code",
        "reason",
    ):
        _fail("selection-candidate-row")
    if (
        candidate_row.get("candidate_id") != _CANDIDATE_ID
        or candidate_row.get("disposition") != "preferred"
        or candidate_row.get("reason_code") != "sole-candidate-pass"
        or candidate_row.get("policy_identity")
        != hashlib.sha256(profile_policy_raw).hexdigest()
    ):
        _fail("selection-candidate-row")
    cross = _canonical_value(cross_language_raw, "selection-cross-language")
    if (
        cross.get("schema") != CROSS_LANGUAGE_SCHEMA
        or not isinstance(cross.get("summary"), dict)
        or cross["summary"].get("result") != "pass"  # type: ignore[index]
    ):
        _fail("selection-cross-language")
    profile_sha = hashlib.sha256(profile_policy_raw).hexdigest()
    cross_sha = hashlib.sha256(cross_language_raw).hexdigest()
    candidate_rows_raw = _canonical(
        {
            "candidate_rows": [dict(candidate_row)],
            "schema": "golden-board.m2-candidate-rows/v0",
        },
        "selection-candidate-rows",
    )
    candidate_rows_sha = hashlib.sha256(candidate_rows_raw).hexdigest()
    ids = [_CANDIDATE_ID]
    selection_rows = []
    for step in _SELECTION_STEPS:
        evidence = _canonical(
            {
                "candidate_rows_sha256": candidate_rows_sha,
                "cross_language_manifest_sha256": cross_sha,
                "outcome": ids,
                "profile_policy_sha256": profile_sha,
                "schema": "golden-board.m2-selection-step-evidence/v0",
                "step": step,
                "surviving_before": ids,
            },
            "selection-step-evidence",
        )
        selection_rows.append(
            {
                "step": step,
                "surviving_before": ids,
                "outcome": ids,
                "evidence_sha256": hashlib.sha256(evidence).hexdigest(),
            }
        )
    return _canonical(
        {
            "candidate_rows": [dict(candidate_row)],
            "cross_language_manifest_sha256": cross_sha,
            "profile_policy_sha256": profile_sha,
            "provisional_preferred_id": _CANDIDATE_ID,
            "retained_finalist_ids": ids,
            "schema": SELECTION_SCHEMA,
            "selection_steps": selection_rows,
        },
        "selection-manifest",
    )


def validate_selection(
    raw: bytes,
    candidate_row: Mapping[str, object],
    cross_language_raw: bytes,
    profile_policy_raw: bytes,
) -> dict[str, object]:
    """Strictly reproduce the active singleton selection manifest."""

    value = _canonical_value(raw, "selection-manifest")
    if set(value) != {
        "candidate_rows",
        "cross_language_manifest_sha256",
        "profile_policy_sha256",
        "provisional_preferred_id",
        "retained_finalist_ids",
        "schema",
        "selection_steps",
    } or value.get("schema") != SELECTION_SCHEMA:
        _fail("selection-shape")
    if raw != render_selection(
        candidate_row, cross_language_raw, profile_policy_raw
    ):
        _fail("selection-stale")
    return value


def _bundle_policy(
    gate8_policy_raw: bytes,
    bundle_kind: str,
) -> tuple[dict[str, object], dict[str, object]]:
    policy = load_gate8_policy(gate8_policy_raw)
    if bundle_kind not in ("technical", "learner"):
        _fail("bundle-kind")
    value = policy.get(f"{bundle_kind}_bundle")
    common = policy.get("bundle_common")
    if type(value) is not dict or type(common) is not dict:
        _fail("bundle-policy")
    return value, common


def build_bundle_files(
    gate8_policy_raw: bytes,
    source_root: Path,
    bundle_kind: str,
    generated_preimages: Mapping[str, bytes],
) -> dict[str, bytes]:
    """Resolve one bundle only from tracked templates and named generators."""

    bundle, _common = _bundle_policy(gate8_policy_raw, bundle_kind)
    participants = bundle.get("participant_roles")
    evaluators = bundle.get("evaluator_roles")
    preimages = bundle.get("role_preimages")
    if (
        type(participants) is not list
        or type(evaluators) is not list
        or type(preimages) is not dict
    ):
        _fail("bundle-policy")
    roles = tuple(participants + evaluators)
    if set(preimages) != set(roles):
        _fail("bundle-policy")
    generated_roles = tuple(
        role
        for role in roles
        if not str(preimages[role]).startswith("tracked-template:")
    )
    if (
        not isinstance(generated_preimages, Mapping)
        or tuple(generated_preimages) != generated_roles
        or any(
            type(raw) is not bytes or not raw
            for raw in generated_preimages.values()
        )
    ):
        _fail("bundle-generated-preimages")
    output: dict[str, bytes] = {}
    for role in roles:
        rule = preimages[role]
        if type(rule) is not str:
            _fail("bundle-policy")
        if rule.startswith("tracked-template:"):
            relative = rule.removeprefix("tracked-template:")
            output[role] = _read_repo_file(source_root, relative, maximum=1_048_576)
        else:
            output[role] = generated_preimages[role]
    exact_source_roles = {
        "learner": {
            "runner": "tools/m2/learner_runner.py",
            "heldout-cases": "studies/m2/templates/learner/heldout-cases.json",
        },
        "technical": {
            "resource-limits": "spec/profile-limits-v1.toml",
        },
    }[bundle_kind]
    for role, relative in exact_source_roles.items():
        if output.get(role) != _read_repo_file(
            source_root, relative, maximum=1_048_576
        ):
            _fail("bundle-source-preimage")
    return output


def render_bundle_manifest(
    gate8_policy_raw: bytes,
    bundle_kind: str,
    file_bytes: Mapping[str, bytes],
) -> bytes:
    """Render one exact participant/evaluator bundle from role preimages."""

    bundle, common = _bundle_policy(gate8_policy_raw, bundle_kind)
    if not isinstance(file_bytes, Mapping):
        raise TypeError("bundle files must be a mapping")
    participant_roles = bundle.get("participant_roles")
    evaluator_roles = bundle.get("evaluator_roles")
    paths = bundle.get("role_paths")
    override_roles = bundle.get("mode_override_roles")
    role_modes = bundle.get("role_modes", {})
    if (
        type(participant_roles) is not list
        or type(evaluator_roles) is not list
        or type(paths) is not dict
        or type(override_roles) is not list
        or type(role_modes) is not dict
        or any(type(role) is not str for role in participant_roles + evaluator_roles)
    ):
        _fail("bundle-policy")
    roles = tuple(participant_roles + evaluator_roles)
    if (
        tuple(file_bytes) != roles
        or set(paths) != set(roles)
        or set(override_roles) != set(role_modes)
        or any(type(raw) is not bytes for raw in file_bytes.values())
    ):
        _fail("bundle-files")
    maximum_file = common.get("file_bytes_max")
    maximum_total = common.get("aggregate_file_bytes_max")
    if type(maximum_file) is not int or type(maximum_total) is not int:
        _fail("bundle-policy")
    total = 0
    rows: dict[str, dict[str, object]] = {}
    seen_paths: set[str] = set()
    for role in roles:
        raw = file_bytes[role]
        if not 1 <= len(raw) <= maximum_file:
            _fail("bundle-file-limit")
        total += len(raw)
        if total > maximum_total:
            _fail("bundle-aggregate-limit")
        path = paths.get(role)
        if type(path) is not str:
            _fail("bundle-path")
        path = _repo_path_text(path)
        prefix = "participant/" if role in participant_roles else "evaluator/"
        if not path.startswith(prefix) or path in seen_paths:
            _fail("bundle-path")
        seen_paths.add(path)
        mode = role_modes.get(role, common.get("mode_default"))
        if mode not in ("100644", "100755"):
            _fail("bundle-mode")
        rows[role] = {
            "role_id": role,
            "path": path,
            "mode": mode,
            "byte_length": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    release_ids = bundle.get("release_ids")
    if type(release_ids) is not list or any(
        type(release_id) is not str for release_id in release_ids
    ):
        _fail("bundle-releases")
    release_rows = []
    released: list[str] = []
    for ordinal, release_id in enumerate(release_ids):
        release_roles = bundle.get(f"release_{ordinal}_roles")
        if type(release_roles) is not list or any(
            type(role) is not str for role in release_roles
        ):
            _fail("bundle-releases")
        released.extend(release_roles)
        release_rows.append(
            {
                "ordinal": ordinal,
                "release_id": release_id,
                "participant_role_ids": release_roles,
            }
        )
    if released != participant_roles:
        _fail("bundle-releases")
    value: dict[str, object] = {
        "bundle_id": bundle.get("bundle_id"),
        "candidate_id": _CANDIDATE_ID,
        "evaluator_files": [rows[role] for role in evaluator_roles],
        "participant_files": [rows[role] for role in participant_roles],
        "release_rows": release_rows,
        "schema": bundle.get("schema"),
    }
    if bundle_kind == "technical":
        value["recipient_condition"] = {
            "headcount": bundle.get("recipient_headcount"),
            "mode": bundle.get("recipient_mode"),
        }
    else:
        content = file_bytes.get("content-stream")
        if type(content) is not bytes:
            _fail("bundle-content-stream")
        value["content_stream_sha256"] = hashlib.sha256(content).hexdigest()
    return _canonical(value, "bundle-manifest")


def validate_bundle_manifest(
    raw: bytes,
    gate8_policy_raw: bytes,
    bundle_kind: str,
    file_bytes: Mapping[str, bytes],
) -> dict[str, object]:
    """Strictly reproduce one bundle manifest from all released bytes."""

    value = _canonical_value(raw, "bundle-manifest")
    expected = render_bundle_manifest(gate8_policy_raw, bundle_kind, file_bytes)
    if raw != expected:
        _fail("bundle-stale")
    return value


def build_damage_rows(
    damage_manifest_raw: bytes,
    family_manifest_raws: Mapping[str, bytes],
) -> list[dict[str, object]]:
    """Project the exact eight family manifests into report damage rows."""

    root = _artifact_manifest(
        damage_manifest_raw,
        schema="golden-board.m2-damage-manifest/v1",
        reason="damage-row-root",
    )
    summary = root.get("summary")
    if (
        root.get("profile_id") != _CANDIDATE_ID
        or type(summary) is not dict
        or not _hex64(summary.get("manifest_identity"))
        or summary.get("wrong_accept_count") != 0
        or type(summary.get("family_case_counts")) is not list
        or not isinstance(family_manifest_raws, Mapping)
        or tuple(family_manifest_raws) != _DAMAGE_FAMILIES
        or type(root.get("family_rows")) is not list
        or len(root["family_rows"]) != len(_DAMAGE_FAMILIES)
    ):
        _fail("damage-row-root")
    root_identity = summary["manifest_identity"]
    root_rows = root["family_rows"]
    output = []
    for family_id, guarantee_id, root_row in zip(
        _DAMAGE_FAMILIES, _DAMAGE_GUARANTEES, root_rows, strict=True
    ):
        raw = family_manifest_raws[family_id]
        family = _artifact_manifest(
            raw,
            schema="golden-board.m2-damage-family/v1",
            reason="damage-row-family",
        )
        family_summary = family.get("summary")
        if (
            family.get("profile_id") != _CANDIDATE_ID
            or family.get("family_id") != family_id
            or family.get("damage_manifest_identity") != root_identity
            or type(family_summary) is not dict
            or family_summary.get("result") not in ("pass", "fail")
            or type(family_summary.get("wrong_accept_count")) is not int
            or not 0
            <= int(family_summary["wrong_accept_count"])
            <= canonical_manifest.MAX_U64
            or family.get("guarantee_id") != guarantee_id
            or type(root_row) is not dict
            or set(root_row)
            != {
                "family_id",
                "case_count",
                "case_rows_sha256",
                "result",
                "wrong_accept_count",
            }
            or root_row.get("family_id") != family_id
            or root_row.get("case_count") != family_summary.get("case_count")
            or not _hex64(root_row.get("case_rows_sha256"))
            or root_row.get("result") != family_summary.get("result")
            or root_row.get("wrong_accept_count")
            != family_summary.get("wrong_accept_count")
        ):
            _fail("damage-row-family")
        output.append(
            {
                "candidate_id": _CANDIDATE_ID,
                "family_id": family_id,
                "manifest_sha256": hashlib.sha256(raw).hexdigest(),
                "guarantee_id": family["guarantee_id"],
                "result": family_summary["result"],
                "wrong_accept_count": family_summary["wrong_accept_count"],
            }
        )
    if summary["family_case_counts"] != [
        {"family_id": row["family_id"], "case_count": row["case_count"]}
        for row in root_rows
    ]:
        _fail("damage-row-root")
    return output


def render_linux_attestation(
    evidence_source_raw: bytes,
    cross_language_raw: bytes,
    verifier_environment_raw: bytes,
) -> bytes:
    """Render the source-bound Linux equality attestation after four passes."""

    try:
        source = _source_projection_value(evidence_source_raw)
    except Gate8Error as error:
        raise Gate8Error("linux-source-projection") from error
    cross = _canonical_value(cross_language_raw, "linux-cross-language")
    if (
        source.get("schema") != EVIDENCE_SOURCE_SCHEMA
        or cross.get("schema") != CROSS_LANGUAGE_SCHEMA
        or not isinstance(cross.get("summary"), dict)
        or cross["summary"].get("result") != "pass"  # type: ignore[index]
    ):
        _fail("linux-evidence")
    rows = cross.get("artifact_rows")
    if (
        type(rows) is not list
        or any(type(row) is not dict for row in rows)
        or [row.get("artifact_id") for row in rows] != list(_ARTIFACT_IDS)
        or any(row.get("result") != "pass" for row in rows)
    ):
        _fail("linux-evidence")
    policy_path_rows = [
        row
        for row in source.get("entries", [])
        if type(row) is dict and row.get("path") == "spec/gate8-policy-v0.toml"
    ]
    refresh_path_rows = [
        row
        for row in source.get("entries", [])
        if type(row) is dict
        and row.get("path") == "spec/gate8-verifier-refresh-v0.toml"
    ]
    if (
        len(policy_path_rows) != 1
        or policy_path_rows[0].get("sha256") != GATE8_POLICY_SHA256
        or len(refresh_path_rows) != 1
        or refresh_path_rows[0].get("sha256")
        != GATE8_VERIFIER_REFRESH_SHA256
    ):
        _fail("linux-image-evidence")
    policy_raw = _read_repo_file(
        Path(__file__).resolve().parents[2], "spec/gate8-policy-v0.toml"
    )
    values = parse_linux_acquisition_receipt(
        verifier_environment_raw, policy_raw
    )
    source_rows = source.get("entries")
    if type(source_rows) is not list:
        _fail("linux-image-evidence")
    dockerfile_rows = [
        row
        for row in source_rows
        if type(row) is dict
        and row.get("path") == "tools/linux/Dockerfile"
    ]
    image_id = values.get("image_id")
    if (
        len(dockerfile_rows) != 1
        or dockerfile_rows[0].get("sha256") != values.get("dockerfile_sha256")
        or values.get("schema") != "m2-linux-image-v0"
        or values.get("image") != "golden-board-verifier:m2-debian13-arm64"
        or image_id
        != "sha256:1b76a6d672c2d4b875302271f3cd5242200b6dc3d9a8491af611951e498ecd96"
        or values.get("platform") != "linux/arm64"
        or values.get("contract") != "m2-linux-verifier-v0"
        or not str(values.get("base", "")).startswith(
            "debian:13-slim@sha256:"
        )
        or len(str(values.get("base", "")))
        != len("debian:13-slim@sha256:") + 64
        or not _hex64(str(values.get("base", ""))[-64:])
        or not _hex64(values.get("dockerfile_sha256"))
    ):
        _fail("linux-image-evidence")
    return _canonical(
        {
            "canonical_bytes_equal": True,
            "evidence_source_projection_sha256": hashlib.sha256(
                evidence_source_raw
            ).hexdigest(),
            "execution_snapshots_equal": True,
            "host_full": "pass",
            "image_digest": image_id,
            "ledgers_equal": True,
            "linux_full": "pass",
            "platform": "linux/arm64",
            "schema": "m2-linux-attestation-v0",
            "states_equal": True,
        },
        "linux-attestation",
    )


def validate_linux_attestation(
    raw: bytes,
    evidence_source_raw: bytes,
    cross_language_raw: bytes,
    verifier_environment_raw: bytes,
) -> dict[str, object]:
    """Strictly reproduce one Linux attestation from its bound evidence."""

    value = _canonical_value(raw, "linux-attestation")
    if raw != render_linux_attestation(
        evidence_source_raw, cross_language_raw, verifier_environment_raw
    ):
        _fail("linux-attestation-stale")
    return value


def render_generated_evidence(
    shared_preimages: Mapping[str, tuple[str, bytes]],
    candidate_preimages: Mapping[str, bytes],
) -> bytes:
    """Render the exact pre-human Gate-1-through-8 identity closure."""

    if not isinstance(shared_preimages, Mapping) or tuple(shared_preimages) != tuple(
        role for role, _ in _SHARED_ROLE_NAMES
    ):
        _fail("generated-shared-roles")
    shared_rows = []
    for role, expected_name in _SHARED_ROLE_NAMES:
        item = shared_preimages[role]
        if (
            type(item) is not tuple
            or len(item) != 2
            or item[0] != expected_name
            or type(item[1]) is not bytes
            or not item[1]
        ):
            _fail("generated-shared-roles")
        shared_rows.append(
            {
                "kind": role,
                "name": expected_name,
                "sha256": hashlib.sha256(item[1]).hexdigest(),
            }
        )
    if not isinstance(candidate_preimages, Mapping) or tuple(
        candidate_preimages
    ) != _CANDIDATE_ROLE_ORDER or any(
        type(raw) is not bytes or not raw for raw in candidate_preimages.values()
    ):
        _fail("generated-candidate-roles")
    candidate_rows = [
        {
            "kind": role,
            "name": _CANDIDATE_ID,
            "sha256": hashlib.sha256(candidate_preimages[role]).hexdigest(),
        }
        for role in _CANDIDATE_ROLE_ORDER
    ]
    return _canonical(
        {
            "candidate_evidence": [
                {"candidate_id": _CANDIDATE_ID, "identities": candidate_rows}
            ],
            "round_summary_identities": [],
            "schema": "m2-generated-evidence-v0",
            "shared_identities": shared_rows,
        },
        "generated-evidence",
    )


def validate_generated_evidence(
    raw: bytes,
    shared_preimages: Mapping[str, tuple[str, bytes]],
    candidate_preimages: Mapping[str, bytes],
) -> dict[str, object]:
    """Strictly reproduce the Gate-1-through-8 evidence identity closure."""

    value = _canonical_value(raw, "generated-evidence")
    if raw != render_generated_evidence(shared_preimages, candidate_preimages):
        _fail("generated-evidence-stale")
    return value


def render_geometry_equivalence(candidate_manifest_raw: bytes) -> bytes:
    """Render the exact singleton admitted raw-geometry equivalence class."""

    candidate = _artifact_manifest(
        candidate_manifest_raw,
        schema=_CANDIDATE_SCHEMA,
        reason="geometry-candidate",
    )
    side = candidate.get("side")
    if (
        candidate.get("profile_id") != _CANDIDATE_ID
        or type(side) is not int
        or not 1 <= side <= 0xFFFF_FFFF
    ):
        _fail("geometry-candidate")
    return _canonical(
        {
            "admitted_N_S_pairs": [{"N": side * side, "S": side}],
            "schema": "golden-board.m2-geometry-equivalence/v0",
        },
        "geometry-equivalence",
    )


def render_technical_content_query(
    gate8_policy_raw: bytes,
    content_stream_raw: bytes,
) -> tuple[bytes, bytes]:
    """Render the exact technical query and its independently derived answer."""

    policy = load_gate8_policy(gate8_policy_raw)
    query = policy.get("technical_content_query")
    if type(query) is not dict:
        _fail("technical-content-policy")
    if (
        type(content_stream_raw) is not bytes
        or len(content_stream_raw) != 13_644
        or hashlib.sha256(content_stream_raw).hexdigest()
        != "de7e22f0aa4316d9f32d9435287dd19bd6c04519aae1dc9bd816613f26929671"
    ):
        _fail("technical-content-stream")
    request = _canonical(
        {
            "chess_transition": {
                "game_ordinal": query.get("chess_game_ordinal"),
                "ply_ordinal": query.get("chess_ply_ordinal"),
            },
            "generic_record": {"record_id": query.get("generic_record_id")},
            "schema": query.get("request_schema"),
        },
        "technical-content-request",
    )
    try:
        projection = content.projection_view(
            content.stream_validation(content_stream_raw)
        )
    except content.ContentReject as error:
        raise Gate8Error("technical-content-stream") from error
    frames: dict[int, bytes] = {}
    if len(content_stream_raw) < 4:
        _fail("technical-content-stream")
    count = int.from_bytes(content_stream_raw[2:4], "big")
    offset = 4
    for _ in range(count):
        if len(content_stream_raw) - offset < 8:
            _fail("technical-content-stream")
        start = offset
        record_id = int.from_bytes(content_stream_raw[offset : offset + 2], "big")
        payload_length = int.from_bytes(
            content_stream_raw[offset + 4 : offset + 8], "big"
        )
        offset += 8 + payload_length
        if offset > len(content_stream_raw) or record_id in frames:
            _fail("technical-content-stream")
        frames[record_id] = content_stream_raw[start:offset]
    if offset != len(content_stream_raw) or set(frames) != {
        record.record_id for record in projection.records
    }:
        _fail("technical-content-stream")
    generic_id = query.get("generic_record_id")
    if type(generic_id) is not int or generic_id not in frames:
        _fail("technical-content-record")
    bindings = [
        record
        for record in projection.records
        if type(record.payload) is content.ContentSemanticBinding
        and record.payload.namespace_id == 2
        and record.payload.semantic_code == 1
    ]
    if len(bindings) != 1:
        _fail("technical-content-game")
    binding_id = bindings[0].record_id
    payloads = [
        record.payload
        for record in projection.records
        if type(record.payload) is content.ContentOpaqueData
        and record.payload.data_binding_ref == binding_id
    ]
    if len(payloads) != 1:
        _fail("technical-content-game")
    game = bytes(payloads[0].data)
    if len(game) < 5:
        _fail("technical-content-game")
    ply_count = int.from_bytes(game[:2], "big")
    if len(game) != 2 + 2 * ply_count + 1 or ply_count < 1:
        _fail("technical-content-game")
    move_raw = game[2:4]
    try:
        replay = chess.apply_move(
            chess.replay_from_start(()), chess.decode_move(move_raw)
        )
        position_identity = identity.identity_hex(
            b"golden-board:position:v0\0",
            (chess.encode_position(replay.position),),
        )
    except (ValueError, identity.IdentityError) as error:
        raise Gate8Error("technical-content-game") from error
    result = _canonical(
        {
            "chess_transition": {
                "game_ordinal": 0,
                "move_hex": move_raw.hex(),
                "ply_ordinal": 0,
                "resulting_position_identity": position_identity,
            },
            "generic_record": {
                "canonical_record_sha256": hashlib.sha256(
                    frames[generic_id]
                ).hexdigest(),
                "record_id": generic_id,
            },
            "schema": query.get("result_schema"),
        },
        "technical-content-result",
    )
    return request, result


def _heldout_case_rows(
    case_rows: Mapping[str, Mapping[str, object]],
) -> tuple[tuple[str, str, str], ...]:
    roles = (
        "unknown-error-observation",
        "known-erasure-observation",
        "missing-unit-observation",
        "negative-observation",
    )
    case_ids = ("D3-000000", "D2-000000", "D4-000000", "D7-000011")
    if (
        not isinstance(case_rows, Mapping)
        or len(case_rows) != len(case_ids)
        or set(case_rows) != set(case_ids)
    ):
        _fail("technical-heldout-cases")
    output = []
    for role, case_id in zip(roles, case_ids, strict=True):
        row = case_rows[case_id]
        if (
            not isinstance(row, Mapping)
            or row.get("case_id") != case_id
            or row.get("channel") not in ("OBS_BITS", "OBS_MATRIX", "OBS_UNITS")
            or row.get("expected_artifact_state")
            not in ("exact", "degraded", "ambiguous", "failure", "resource-limit")
            or not _hex64(row.get("observation_sha256"))
            or not _hex64(row.get("decoder_result_sha256"))
        ):
            _fail("technical-heldout-cases")
        output.append((role, case_id, str(row["channel"])))
    return tuple(output)


def render_technical_heldout_classes(
    case_rows: Mapping[str, Mapping[str, object]],
) -> bytes:
    """Render the four answer-free technical held-out class bindings."""

    rows = _heldout_case_rows(case_rows)
    return _canonical(
        {
            "candidate_id": _CANDIDATE_ID,
            "rows": [
                {"case_id": case_id, "channel": channel, "role_id": role}
                for role, case_id, channel in rows
            ],
            "schema": "golden-board.m2-technical-heldout-classes/v0",
        },
        "technical-heldout-classes",
    )


def render_technical_heldout_expected(
    case_rows: Mapping[str, Mapping[str, object]],
) -> bytes:
    """Render the evaluator-only hashes and states for four held-out cases."""

    rows = _heldout_case_rows(case_rows)
    return _canonical(
        {
            "candidate_id": _CANDIDATE_ID,
            "heldout_rows": [
                {
                    "case_id": case_id,
                    "channel": channel,
                    "decoder_result_sha256": case_rows[case_id][
                        "decoder_result_sha256"
                    ],
                    "expected_artifact_state": case_rows[case_id][
                        "expected_artifact_state"
                    ],
                    "observation_sha256": case_rows[case_id]["observation_sha256"],
                    "role_id": role,
                }
                for role, case_id, channel in rows
            ],
            "schema": "golden-board.m2-technical-heldout-expected/v0",
        },
        "technical-heldout-expected",
    )


def render_learner_heldout_request(gate8_policy_raw: bytes) -> bytes:
    """Render the exact answer-free learner held-out request."""

    policy = load_gate8_policy(gate8_policy_raw)
    owner = policy.get("learner_heldout_request")
    if type(owner) is not dict:
        _fail("learner-heldout-policy")
    return _canonical(
        {
            "case_id": owner.get("case_id"),
            "label_suppressed": owner.get("label_suppressed"),
            "schema": owner.get("schema"),
            "start_node_id": owner.get("start_node_id"),
            "start_phase": owner.get("start_phase"),
        },
        "learner-heldout-request",
    )


def render_learner_slice_binding(
    gate8_policy_raw: bytes,
    content_stream_raw: bytes,
) -> bytes:
    """Render the participant-visible opaque stream binding."""

    policy = load_gate8_policy(gate8_policy_raw)
    owner = policy.get("learner_slice_binding")
    if (
        type(owner) is not dict
        or type(content_stream_raw) is not bytes
        or len(content_stream_raw) != owner.get("stream_bytes")
        or hashlib.sha256(content_stream_raw).hexdigest()
        != "de7e22f0aa4316d9f32d9435287dd19bd6c04519aae1dc9bd816613f26929671"
    ):
        _fail("learner-slice-binding")
    return _canonical(
        {
            "content_stream_sha256": hashlib.sha256(content_stream_raw).hexdigest(),
            "root_record_id": owner.get("root_record_id"),
            "schema": owner.get("schema"),
            "stream_bytes": len(content_stream_raw),
        },
        "learner-slice-binding",
    )


def render_learner_expected(
    gate8_policy_raw: bytes,
    content_stream_raw: bytes,
    semantic_path_raw: bytes,
) -> bytes:
    """Render the evaluator-only semantic-path and node-28 commitments."""

    policy = load_gate8_policy(gate8_policy_raw)
    owner = policy.get("learner_expected")
    if (
        type(owner) is not dict
        or type(content_stream_raw) is not bytes
        or hashlib.sha256(content_stream_raw).hexdigest()
        != "de7e22f0aa4316d9f32d9435287dd19bd6c04519aae1dc9bd816613f26929671"
        or type(semantic_path_raw) is not bytes
        or len(semantic_path_raw) != 9_883
        or hashlib.sha256(semantic_path_raw).hexdigest()
        != "966e510af60a9a95afc60badee2d985da95add187f7d132bc2009369db33cbd3"
    ):
        _fail("learner-expected-input")
    semantic = _artifact_manifest(
        semantic_path_raw,
        schema="golden-board.runner-semantic-path/v0",
        reason="learner-semantic-path",
    )
    commitments = semantic.get("commitments")
    if type(commitments) is not list or len(commitments) != 4:
        _fail("learner-semantic-path")
    final = commitments[3]
    if type(final) is not dict:
        _fail("learner-semantic-path")
    commitment = {
        "committed_response_hex": final.get("committed_response_hex"),
        "feedback_predicate": final.get("feedback_predicate"),
        "feedback_ref": final.get("feedback_ref"),
        "next_node_ref": final.get("next_node_ref"),
        "node_id": final.get("node_id"),
        "node_predicate": final.get("node_predicate"),
        "outcome": final.get("outcome"),
    }
    predicate_keys = {
        "argument",
        "auxiliary",
        "binding_class",
        "namespace_id",
        "predicate_binding_ref",
        "predicate_result_ref",
        "result_atom_vector_ref",
        "semantic_code",
        "subject_data_binding_ref",
        "subject_opaque_data_ref",
    }
    if (
        commitment["node_id"] != 28
        or commitment["committed_response_hex"] != "03000200030001"
        or commitment["outcome"] != 3
        or commitment["feedback_ref"] != 24
        or commitment["next_node_ref"] != 0
        or any(
            type(commitment[name]) is not dict
            or set(commitment[name]) != predicate_keys
            or any(value != 0 for value in commitment[name].values())
            for name in ("node_predicate", "feedback_predicate")
        )
        or semantic.get("content_stream_sha256")
        != hashlib.sha256(content_stream_raw).hexdigest()
    ):
        _fail("learner-semantic-path")
    commitment_raw = _canonical(commitment, "learner-heldout-commitment")
    return _canonical(
        {
            "candidate_id": _CANDIDATE_ID,
            "content_stream_sha256": hashlib.sha256(content_stream_raw).hexdigest(),
            "heldout_commitment_sha256": hashlib.sha256(commitment_raw).hexdigest(),
            "required_predicate_ids": owner.get("required_predicate_ids"),
            "schema": owner.get("schema"),
            "semantic_path_sha256": hashlib.sha256(semantic_path_raw).hexdigest(),
        },
        "learner-expected",
    )


def _packed_bits(bits: Sequence[int], reason: str) -> bytes:
    if not isinstance(bits, Sequence) or isinstance(bits, (bytes, bytearray, str)):
        _fail(reason)
    output = bytearray((len(bits) + 7) // 8)
    for index, bit in enumerate(bits):
        if bit not in (0, 1):
            _fail(reason)
        output[index // 8] |= bit << (7 - index % 8)
    return bytes(output)


def render_pilot_envelope(
    *,
    source_root: Path,
    gate8_policy_raw: bytes,
    candidate_manifest_raw: bytes,
    carrier_raw: bytes,
    ownership_ledger_raw: bytes,
    capacity_ledger_raw: bytes,
    density_ledger_raw: bytes,
    independence_proof_raw: bytes,
    semantic_envelope_raw: bytes,
    bootstrap_spec_raw: bytes,
    route_data_raw: bytes,
    profile_policy_raw: bytes,
    damage_policy_raw: bytes,
    parameter_projection_raw: bytes,
    geometry_equivalence_raw: bytes,
    technical_bundle_raw: bytes,
    technical_files: Mapping[str, bytes],
    technical_heldout_classes_raw: bytes,
    learner_bundle_raw: bytes,
    learner_files: Mapping[str, bytes],
    content_stream_raw: bytes,
    vertical_slice_raw: bytes,
    runner_raw: bytes,
    semantic_path_raw: bytes,
    generated_evidence_raw: bytes,
    generated_shared_preimages: Mapping[str, tuple[str, bytes]],
    generated_candidate_preimages: Mapping[str, bytes],
) -> dict[str, object]:
    """Derive the complete Candidate-ready M2 pilot envelope."""

    byte_inputs = (
        gate8_policy_raw,
        candidate_manifest_raw,
        carrier_raw,
        ownership_ledger_raw,
        capacity_ledger_raw,
        density_ledger_raw,
        independence_proof_raw,
        semantic_envelope_raw,
        bootstrap_spec_raw,
        route_data_raw,
        profile_policy_raw,
        damage_policy_raw,
        parameter_projection_raw,
        geometry_equivalence_raw,
        technical_bundle_raw,
        technical_heldout_classes_raw,
        learner_bundle_raw,
        content_stream_raw,
        vertical_slice_raw,
        runner_raw,
        semantic_path_raw,
        generated_evidence_raw,
    )
    if any(
        type(raw) is not bytes or not 1 <= len(raw) <= _MAX_FILE_BYTES
        for raw in byte_inputs
    ):
        _fail("pilot-preimages")
    load_gate8_policy(gate8_policy_raw)
    if (
        gate8_policy_raw
        != _read_repo_file(source_root, "spec/gate8-policy-v0.toml")
        or bootstrap_spec_raw
        != _read_repo_file(source_root, "spec/bootstrap-v1.md")
        or route_data_raw != _read_repo_file(source_root, "spec/route-data-v1.json")
        or profile_policy_raw
        != _read_repo_file(source_root, "spec/profile-policy-v1.toml")
        or damage_policy_raw
        != _read_repo_file(source_root, "spec/damage-policy-v1.toml")
        or vertical_slice_raw
        != _read_repo_file(source_root, "studies/m2/slice-v0.json")
        or runner_raw != _read_repo_file(source_root, "tools/m2/learner_runner.py")
        or parameter_projection_raw
        != render_owner_projection(
            "parameter_manifest",
            {
                "spec/profile-policy-v1.toml": profile_policy_raw,
                "spec/profile-limits-v1.toml": _read_repo_file(
                    source_root, "spec/profile-limits-v1.toml"
                ),
                f"artifacts/candidates/{_CANDIDATE_ID}/candidate-manifest.json": candidate_manifest_raw,
            },
        )
    ):
        _fail("pilot-source-preimage")
    candidate = _artifact_manifest(
        candidate_manifest_raw,
        schema=_CANDIDATE_SCHEMA,
        reason="pilot-candidate",
    )
    if (
        hashlib.sha256(candidate_manifest_raw).hexdigest()
        != _CANDIDATE_MANIFEST_SHA256
        or candidate.get("profile_id") != _CANDIDATE_ID
        or candidate.get("carrier_sha256") != hashlib.sha256(carrier_raw).hexdigest()
        or candidate.get("ownership_sha256")
        != hashlib.sha256(ownership_ledger_raw).hexdigest()
        or candidate.get("capacity_ledger_sha256")
        != hashlib.sha256(capacity_ledger_raw).hexdigest()
        or candidate.get("density_ledger_sha256")
        != hashlib.sha256(density_ledger_raw).hexdigest()
        or candidate.get("semantic_envelope_sha256")
        != hashlib.sha256(semantic_envelope_raw).hexdigest()
    ):
        _fail("pilot-candidate")
    ownership = _artifact_manifest(
        ownership_ledger_raw,
        schema="golden-board.m2-ownership-ledger/v1",
        reason="pilot-ownership",
    )
    density = _artifact_manifest(
        density_ledger_raw,
        schema="golden-board.m2-density-ledger/v0",
        reason="pilot-density",
    )
    proof = _artifact_manifest(
        independence_proof_raw,
        schema="golden-board.m2-independence-proof/v1",
        reason="pilot-proof",
    )
    geometry = _artifact_manifest(
        geometry_equivalence_raw,
        schema="golden-board.m2-geometry-equivalence/v0",
        reason="pilot-geometry",
    )
    parameter_projection = _artifact_manifest(
        parameter_projection_raw,
        schema=OWNER_PROJECTION_SCHEMA,
        reason="pilot-parameter-projection",
    )
    heldout_classes = _artifact_manifest(
        technical_heldout_classes_raw,
        schema="golden-board.m2-technical-heldout-classes/v0",
        reason="pilot-heldout-classes",
    )
    expected_heldout_class_rows = [
        {
            "case_id": case_id,
            "channel": channel,
            "role_id": role_id,
        }
        for role_id, case_id, channel in (
            ("unknown-error-observation", "D3-000000", "OBS_MATRIX"),
            ("known-erasure-observation", "D2-000000", "OBS_MATRIX"),
            ("missing-unit-observation", "D4-000000", "OBS_UNITS"),
            ("negative-observation", "D7-000011", "OBS_UNITS"),
        )
    ]
    side = candidate.get("side")
    width = candidate.get("shell_width")
    shell_rows = candidate.get("shell_rows")
    mapping = candidate.get("mapping")
    if (
        type(side) is not int
        or type(width) is not int
        or type(shell_rows) is not list
        or len(shell_rows) != 4
        or type(mapping) is not dict
        or geometry_equivalence_raw != render_geometry_equivalence(candidate_manifest_raw)
        or ownership.get("shell_rows") != shell_rows
        or proof.get("profile_id") != _CANDIDATE_ID
        or proof.get("candidate_manifest_sha256")
        != _CANDIDATE_MANIFEST_SHA256
        or not isinstance(proof.get("summary"), dict)
        or proof["summary"].get("result") != "pass"  # type: ignore[index]
        or parameter_projection.get("projection_id") != "parameter-manifest-v7"
        or heldout_classes.get("candidate_id") != _CANDIDATE_ID
        or set(heldout_classes) != {"candidate_id", "rows", "schema"}
        or heldout_classes.get("rows") != expected_heldout_class_rows
    ):
        _fail("pilot-shape")
    count = int.from_bytes(carrier_raw[:4], "big") if len(carrier_raw) >= 4 else -1
    if count != side * side or len(carrier_raw) != 4 + (count + 7) // 8:
        _fail("pilot-carrier")
    payload = carrier_raw[4:]
    route_preimage = bytearray(b"golden-board:m2:pilot:shell-route-bytes:v0\0")
    route_preimage.extend((4).to_bytes(8, "big"))
    for sector_id, row in enumerate(shell_rows):
        if type(row) is not dict or row.get("sector_id") != sector_id:
            _fail("pilot-shell-row")
        prefix_cells = row.get("route_prefix_cells")
        if type(prefix_cells) is not int or prefix_cells % 8:
            _fail("pilot-shell-row")
        bits = []
        try:
            for offset in range(prefix_cells):
                shell_row, shell_column = bootstrap.sector_cell(
                    side, width, sector_id, offset
                )
                index = shell_row * side + shell_column
                bits.append(_carrier_bit(payload, index))
        except (bootstrap.BootstrapReject, IndexError) as error:
            raise Gate8Error("pilot-shell-row") from error
        route_bytes = _packed_bits(bits, "pilot-shell-row")
        route_preimage.extend(len(route_bytes).to_bytes(8, "big"))
        route_preimage.extend(route_bytes)
    shell_bits = [
        _carrier_bit(payload, row * side + column)
        for row in range(side)
        for column in range(side)
        if row < width
        or row >= side - width
        or column < width
        or column >= side - width
    ]
    shell_cell_preimage = bytearray(b"golden-board:m2:pilot:shell-cells:v0\0")
    shell_cell_preimage.extend(len(shell_bits).to_bytes(8, "big"))
    shell_cell_preimage.extend(_packed_bits(shell_bits, "pilot-shell-cells"))
    shell_ownership_raw = _canonical(
        {
            "schema": "golden-board.m2-shell-ownership-projection/v0",
            "shell_rows": shell_rows,
        },
        "pilot-shell-ownership",
    )
    mapping_raw = _canonical(
        {
            "mapping": mapping,
            "schema": "golden-board.m2-mapping-parameters/v1",
        },
        "pilot-mapping",
    )
    regularity = density.get("interior_regularity")
    scope_rows = density.get("scope_rows")
    if (
        type(regularity) is not dict
        or type(scope_rows) is not list
        or not scope_rows
        or type(scope_rows[-1]) is not dict
        or scope_rows[-1].get("scope_id") != "complete-interior"
    ):
        _fail("pilot-density")
    interior = side - 2 * width
    maximum_run = max(128, (interior + 3) // 4)
    maximum_repeated = max(2, interior // 32)
    if (
        not 250_000 <= int(scope_rows[-1].get("one_density_ppm", -1)) <= 750_000
        or not 125_000 <= int(regularity.get("tile_one_count_min", -1)) * 1_000_000 // 1024
        or int(regularity.get("tile_one_count_max", 1025)) * 1_000_000 // 1024
        > 875_000
        or int(regularity.get("longest_horizontal_equal_run", maximum_run + 1))
        > maximum_run
        or int(regularity.get("longest_vertical_equal_run", maximum_run + 1))
        > maximum_run
        or int(regularity.get("repeated_row_count", maximum_repeated + 1))
        > maximum_repeated
        or int(regularity.get("repeated_column_count", maximum_repeated + 1))
        > maximum_repeated
    ):
        _fail("pilot-density")
    technical = _canonical_value(technical_bundle_raw, "pilot-technical-bundle")
    learner = _canonical_value(learner_bundle_raw, "pilot-learner-bundle")
    if (
        technical.get("schema") != "golden-board.m2-technical-bundle/v0"
        or learner.get("schema") != "golden-board.m2-learner-bundle/v0"
    ):
        _fail("pilot-bundle")
    validate_bundle_manifest(
        technical_bundle_raw, gate8_policy_raw, "technical", technical_files
    )
    validate_bundle_manifest(
        learner_bundle_raw, gate8_policy_raw, "learner", learner_files
    )
    for bundle_kind, files in (
        ("technical", technical_files),
        ("learner", learner_files),
    ):
        bundle, _common = _bundle_policy(gate8_policy_raw, bundle_kind)
        preimages = bundle.get("role_preimages")
        if type(preimages) is not dict:
            _fail("pilot-bundle-preimage")
        generated_roles = tuple(
            role
            for role in tuple(preimages)
            if not str(preimages[role]).startswith("tracked-template:")
        )
        generated_files = {
            role: files[role]
            for role in generated_roles
            if role in files
        }
        if len(generated_files) != len(generated_roles) or dict(files) != build_bundle_files(
            gate8_policy_raw,
            source_root,
            bundle_kind,
            generated_files,
        ):
            _fail("pilot-bundle-preimage")
    validate_generated_evidence(
        generated_evidence_raw,
        generated_shared_preimages,
        generated_candidate_preimages,
    )
    technical_roles = (
        "export-format",
        "neutral-opening-prompt",
        "allowed-tools",
        "session-policy",
        "facilitation-policy",
    )
    learner_roles = (
        "label-suppressed-config",
        "teaching-practice-order",
        "facilitation-policy",
        "learner-condition",
        "session-policy",
    )
    if any(role not in technical_files for role in technical_roles) or any(
        role not in learner_files for role in learner_roles
    ):
        _fail("pilot-bundle-files")
    if (
        type(content_stream_raw) is not bytes
        or hashlib.sha256(content_stream_raw).hexdigest()
        != "de7e22f0aa4316d9f32d9435287dd19bd6c04519aae1dc9bd816613f26929671"
        or type(semantic_path_raw) is not bytes
        or hashlib.sha256(semantic_path_raw).hexdigest()
        != "966e510af60a9a95afc60badee2d985da95add187f7d132bc2009369db33cbd3"
        or learner_files.get("content-stream") != content_stream_raw
        or learner_files.get("runner") != runner_raw
        or learner_files.get("semantic-path-expected") != semantic_path_raw
        or generated_shared_preimages.get("content_stream")
        != ("m2_all", content_stream_raw)
        or generated_shared_preimages.get("vertical_slice")
        != ("slice-v0", vertical_slice_raw)
        or generated_shared_preimages.get("semantic_envelope")
        != ("capacity-envelope-v1", semantic_envelope_raw)
        or generated_shared_preimages.get("technical_bundle")
        != ("technical-v0", technical_bundle_raw)
        or generated_shared_preimages.get("learner_bundle")
        != ("learner-v0", learner_bundle_raw)
        or generated_candidate_preimages.get("parameter_manifest")
        != parameter_projection_raw
        or generated_candidate_preimages.get("carrier") != carrier_raw
        or generated_candidate_preimages.get("ownership_ledger")
        != ownership_ledger_raw
        or generated_candidate_preimages.get("capacity_ledger")
        != capacity_ledger_raw
        or generated_candidate_preimages.get("density_ledger")
        != density_ledger_raw
        or generated_candidate_preimages.get("independence_proof")
        != independence_proof_raw
    ):
        _fail("pilot-learner")
    technical_invariance = {
        "raw_geometry": {
            "observed_N": side * side,
            "observed_S": side,
            "admitted_N_S_pairs": geometry["admitted_N_S_pairs"],
            "equivalence_proof_sha256": hashlib.sha256(
                geometry_equivalence_raw
            ).hexdigest(),
        },
        "shell": {
            "W": width,
            "complete_bytes_sha256": hashlib.sha256(route_preimage).hexdigest(),
            "complete_cells_sha256": hashlib.sha256(shell_cell_preimage).hexdigest(),
            "sector_ownership_sha256": hashlib.sha256(
                shell_ownership_raw
            ).hexdigest(),
        },
        "bootstrap": {
            "framing_sha256": hashlib.sha256(bootstrap_spec_raw).hexdigest(),
            "dependency_graph_sha256": hashlib.sha256(route_data_raw).hexdigest(),
            "recipe_sha256": hashlib.sha256(route_data_raw).hexdigest(),
            "operation_set_sha256": hashlib.sha256(route_data_raw).hexdigest(),
            "tables_sha256": hashlib.sha256(route_data_raw).hexdigest(),
            "discriminator_sha256": hashlib.sha256(route_data_raw).hexdigest(),
            "grouping_id": "physical-unit-group-contiguous-v1",
            "bit_order_id": "msb-first",
            "traversal_id": "row-major-square-dihedral-polarity-v0",
        },
        "transport": {
            "candidate_id": _CANDIDATE_ID,
            "parameter_manifest_sha256": hashlib.sha256(
                parameter_projection_raw
            ).hexdigest(),
            "common_grammar_sha256": hashlib.sha256(bootstrap_spec_raw).hexdigest(),
            "protected_semantics_sha256": hashlib.sha256(
                profile_policy_raw
            ).hexdigest(),
            "state_semantics_sha256": hashlib.sha256(damage_policy_raw).hexdigest(),
        },
        "mapping": {
            "formula_id": "affine-slot-then-interior-v1",
            "parameters_sha256": hashlib.sha256(mapping_raw).hexdigest(),
            "inverse_proof_sha256": hashlib.sha256(
                independence_proof_raw
            ).hexdigest(),
        },
        "interior_bounds": {
            "density_min_ppm": 250_000,
            "density_max_ppm": 750_000,
            "tile_density_min_ppm": 125_000,
            "tile_density_max_ppm": 875_000,
            "max_horizontal_run": maximum_run,
            "max_vertical_run": maximum_run,
            "max_repeated_rows": maximum_repeated,
            "max_repeated_columns": maximum_repeated,
        },
        "challenge": {
            "export_format_sha256": hashlib.sha256(
                technical_files["export-format"]
            ).hexdigest(),
            "neutral_prompt_sha256": hashlib.sha256(
                technical_files["neutral-opening-prompt"]
            ).hexdigest(),
            "heldout_class_manifest_sha256": hashlib.sha256(
                technical_heldout_classes_raw
            ).hexdigest(),
        },
        "recipient_condition": {
            "mode": "individual",
            "headcount": 1,
            "allowed_tools_sha256": hashlib.sha256(
                technical_files["allowed-tools"]
            ).hexdigest(),
            "session_policy_sha256": hashlib.sha256(
                technical_files["session-policy"]
            ).hexdigest(),
            "facilitation_sha256": hashlib.sha256(
                technical_files["facilitation-policy"]
            ).hexdigest(),
            "think_aloud_sha256": hashlib.sha256(
                technical_files["facilitation-policy"]
            ).hexdigest(),
            "active_time_ceiling_seconds": 57_600,
            "elapsed_time_ceiling_seconds": 604_800,
        },
    }
    learner_invariance = {
        "content_stream_sha256": hashlib.sha256(content_stream_raw).hexdigest(),
        "slice_sha256": hashlib.sha256(vertical_slice_raw).hexdigest(),
        "runner_sha256": hashlib.sha256(runner_raw).hexdigest(),
        "label_suppressed_config_sha256": hashlib.sha256(
            learner_files["label-suppressed-config"]
        ).hexdigest(),
        "teaching_practice_order_sha256": hashlib.sha256(
            learner_files["teaching-practice-order"]
        ).hexdigest(),
        "semantic_path_sha256": hashlib.sha256(semantic_path_raw).hexdigest(),
        "facilitation_sha256": hashlib.sha256(
            learner_files["facilitation-policy"]
        ).hexdigest(),
        "learner_condition_sha256": hashlib.sha256(
            learner_files["learner-condition"]
        ).hexdigest(),
        "time_policy_sha256": hashlib.sha256(
            learner_files["session-policy"]
        ).hexdigest(),
    }
    evidence_identities = {
        "m2_all_content_stream_sha256": hashlib.sha256(content_stream_raw).hexdigest(),
        "vertical_slice_sha256": hashlib.sha256(vertical_slice_raw).hexdigest(),
        "carrier_sha256": hashlib.sha256(carrier_raw).hexdigest(),
        "exact_cell_count_ledger_sha256": hashlib.sha256(
            capacity_ledger_raw
        ).hexdigest(),
        "ownership_ledger_sha256": hashlib.sha256(
            ownership_ledger_raw
        ).hexdigest(),
        "density_ledger_sha256": hashlib.sha256(density_ledger_raw).hexdigest(),
        "technical_bundle_sha256": hashlib.sha256(technical_bundle_raw).hexdigest(),
        "learner_bundle_sha256": hashlib.sha256(learner_bundle_raw).hexdigest(),
        "generated_evidence_manifest_sha256": hashlib.sha256(
            generated_evidence_raw
        ).hexdigest(),
    }
    return {
        "technical_invariance": technical_invariance,
        "learner_invariance": learner_invariance,
        "evidence_identities": evidence_identities,
    }


def _source_identity_rows(
    evidence_source: dict[str, object],
    gate8_policy: dict[str, object],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    rows = evidence_source.get("entries")
    if type(rows) is not list or any(type(row) is not dict for row in rows):
        _fail("report-source-projection")
    by_path = {row.get("path"): row for row in rows}
    if len(by_path) != len(rows):
        _fail("report-source-projection")
    semantic_paths = (
        "docs/64_games.md",
        "reports/source-doctor.json",
        "reports/source-compilation-v0.json",
        "reports/game-set-v0.bin",
        "studies/m2/slice-v0.json",
    )
    overlay = gate8_policy.get("report_r3_overlay")
    if type(overlay) is not dict or type(overlay.get("normative_owner_paths")) is not list:
        _fail("report-source-policy")
    normative_paths = tuple(overlay["normative_owner_paths"])

    def source_row(kind: str, path: str) -> dict[str, object]:
        if path == "roadmap-normative-v0":
            digest = evidence_source.get("roadmap_normative_sha256")
        else:
            row = by_path.get(path)
            digest = row.get("sha256") if type(row) is dict else None
        if not _hex64(digest):
            _fail("report-source-row")
        return {"kind": kind, "name": path, "sha256": digest}

    semantic = sorted(
        (source_row("semantic_input", path) for path in semantic_paths),
        key=lambda row: (str(row["kind"]).encode(), str(row["name"]).encode()),
    )
    normative = sorted(
        (source_row("normative_owner", str(path)) for path in normative_paths),
        key=lambda row: (str(row["kind"]).encode(), str(row["name"]).encode()),
    )
    return semantic, normative


def render_candidate_ready_report(
    *,
    source_root: Path,
    gate8_policy_raw: bytes,
    roadmap_raw: bytes,
    evidence_source_raw: bytes,
    candidate_metrics: Mapping[str, int],
    selection_raw: bytes,
    profile_policy_raw: bytes,
    profile_limits_raw: bytes,
    semantic_envelope_raw: bytes,
    side_search_projection_raw: bytes,
    candidate_manifest_raw: bytes,
    carrier_raw: bytes,
    ownership_ledger_raw: bytes,
    capacity_ledger_raw: bytes,
    density_ledger_raw: bytes,
    work_scratch_projection_raw: bytes,
    damage_manifest_raw: bytes,
    family_manifest_raws: Mapping[str, bytes],
    damage_bundle_files: Mapping[str, bytes],
    producer_receipts: Mapping[str, bytes],
    producer_artifacts: Mapping[str, bytes],
    cross_language_raw: bytes,
    linux_attestation_raw: bytes,
    verifier_environment_raw: bytes,
    technical_bundle_raw: bytes,
    technical_files: Mapping[str, bytes],
    learner_bundle_raw: bytes,
    learner_files: Mapping[str, bytes],
    generated_evidence_raw: bytes,
    generated_shared_preimages: Mapping[str, tuple[str, bytes]],
    generated_candidate_preimages: Mapping[str, bytes],
    owner_source_preimages: Mapping[str, bytes],
    pilot_preimages: Mapping[str, bytes],
) -> bytes:
    """Render the compact tracked Candidate-ready report, with no human claim."""

    policy = load_gate8_policy(gate8_policy_raw)
    pilot_keys = (
        "bootstrap_spec_raw",
        "route_data_raw",
        "damage_policy_raw",
        "geometry_equivalence_raw",
        "technical_heldout_classes_raw",
        "content_stream_raw",
        "vertical_slice_raw",
        "runner_raw",
        "semantic_path_raw",
    )
    if (
        not isinstance(pilot_preimages, Mapping)
        or tuple(pilot_preimages) != pilot_keys
        or any(
            type(raw) is not bytes or not 1 <= len(raw) <= _MAX_FILE_BYTES
            for raw in pilot_preimages.values()
        )
    ):
        _fail("report-pilot-preimages")
    try:
        source = validate_gate8_source_surface(
            evidence_source_raw, source_root, gate8_policy_raw
        )
    except Gate8Error as error:
        raise Gate8Error("report-source-projection") from error
    if type(roadmap_raw) is not bytes or not roadmap_raw.endswith(b"\n"):
        _fail("report-roadmap")
    if (
        roadmap_raw != _read_repo_file(source_root, "docs/roadmap.md")
        or gate8_policy_raw
        != _read_repo_file(source_root, "spec/gate8-policy-v0.toml")
    ):
        _fail("report-source-preimage")
    try:
        roadmap_text = roadmap_raw.decode("utf-8")
    except UnicodeError as error:
        raise Gate8Error("report-roadmap") from error
    revision_rows = [
        line
        for line in roadmap_text.splitlines()
        if line.startswith("| Roadmap revision | ") and line.endswith(" |")
    ]
    if len(revision_rows) != 1:
        _fail("report-roadmap")
    try:
        roadmap_revision = int(revision_rows[0].split("|")[2].strip())
    except (ValueError, IndexError) as error:
        raise Gate8Error("report-roadmap") from error
    if roadmap_revision < 0:
        _fail("report-roadmap")
    if source.get("roadmap_normative_sha256") != roadmap_normative_sha256(
        roadmap_raw
    ):
        _fail("report-roadmap")
    semantic_rows, normative_rows = _source_identity_rows(source, policy)
    _validate_artifact_preimages(producer_artifacts)
    if (
        not isinstance(damage_bundle_files, Mapping)
        or damage_bundle_files.get("damage-manifest.json")
        != damage_manifest_raw
        or damage_bundle_files.get("independence-proof.json")
        != producer_artifacts.get("independence-proof")
        or any(
            damage_bundle_files.get(f"damage-{family}.json")
            != family_manifest_raws.get(family)
            for family in _DAMAGE_FAMILIES
        )
        or render_damage_inventory(damage_bundle_files)
        != producer_artifacts.get("damage-bundle-inventory")
    ):
        _fail("report-damage-bundle")
    family_raw_sequence = tuple(
        family_manifest_raws[family] for family in _DAMAGE_FAMILIES
    )
    shard_names = tuple(
        name
        for family in _DAMAGE_FAMILIES
        for name in sorted(
            (
                name
                for name in damage_bundle_files
                if name.startswith(f"damage-{family}-cases-")
                and name.endswith(".json")
            ),
            key=str.encode,
        )
    )
    if set(damage_bundle_files) != {
        "damage-manifest.json",
        "independence-proof.json",
        *(f"damage-{family}.json" for family in _DAMAGE_FAMILIES),
        *shard_names,
    }:
        _fail("report-damage-bundle")
    try:
        admitted_damage = m2_damage.validate_damage_bundle_v1(
            damage_manifest_raw,
            family_raw_sequence,
            tuple((name, damage_bundle_files[name]) for name in shard_names),
            pilot_preimages["damage_policy_raw"],
            profile_policy_raw,
            profile_limits_raw,
            pilot_preimages["bootstrap_spec_raw"],
            pilot_preimages["route_data_raw"],
            m2_recipe.build_r3_recipe_package(),
            candidate_manifest_raw,
            carrier_raw,
        )
        admitted_proof = m2_independence.validate_independence_proof_v1(
            producer_artifacts["independence-proof"],
            candidate_manifest_raw,
            ownership_ledger_raw,
            damage_manifest_raw,
            family_raw_sequence,
            tuple(damage_bundle_files[name] for name in shard_names),
        )
    except (m2_damage.DamageError, m2_independence.IndependenceError) as error:
        raise Gate8Error("report-damage-bundle") from error
    if admitted_damage.result != "pass" or admitted_proof.result != "pass":
        _fail("report-damage-bundle")
    semantic_projection = build_semantic_content_projection_from_carrier(
        candidate_manifest_raw, carrier_raw, semantic_envelope_raw
    )
    if (
        semantic_projection.canonical_bytes
        != producer_artifacts.get("semantic-content-projection")
    ):
        _fail("report-semantic-projection")
    if (
        producer_artifacts.get("candidate-manifest") != candidate_manifest_raw
        or producer_artifacts.get("carrier") != carrier_raw
        or producer_artifacts.get("ownership-ledger") != ownership_ledger_raw
        or producer_artifacts.get("capacity-ledger") != capacity_ledger_raw
        or producer_artifacts.get("density-ledger") != density_ledger_raw
        or tuple(producer_receipts) != _PRODUCER_IDS
    ):
        _fail("report-producer-artifacts")
    for producer_id in _PRODUCER_IDS:
        validate_producer_receipt(
            producer_receipts[producer_id], producer_id, producer_artifacts
        )
    cross = validate_cross_language_manifest(
        cross_language_raw, producer_receipts, candidate_manifest_raw
    )
    candidate_row = build_candidate_row(
        candidate_metrics, profile_policy_raw, cross_language_raw
    )
    expected_metrics = derive_candidate_metrics(
        m2_recipe.build_r3_recipe_package(),
        profile_limits_raw,
        pilot_preimages["route_data_raw"],
        capacity_ledger_raw,
    )
    if dict(candidate_metrics) != expected_metrics:
        _fail("report-candidate-metrics")
    selection = validate_selection(
        selection_raw, candidate_row, cross_language_raw, profile_policy_raw
    )
    linux = validate_linux_attestation(
        linux_attestation_raw,
        evidence_source_raw,
        cross_language_raw,
        verifier_environment_raw,
    )
    case_rows = {
        str(row["case_id"]): row
        for family_rows in admitted_damage.case_rows_by_family
        for row in family_rows
        if row.get("case_id")
        in {"D2-000000", "D3-000000", "D4-000000", "D7-000011"}
    }
    if set(case_rows) != {
        "D2-000000",
        "D3-000000",
        "D4-000000",
        "D7-000011",
    }:
        _fail("report-bundle-preimages")
    content_query_raw, content_query_result_raw = render_technical_content_query(
        gate8_policy_raw, semantic_projection.content_stream
    )
    heldout_classes_raw = render_technical_heldout_classes(case_rows)
    if pilot_preimages["technical_heldout_classes_raw"] != heldout_classes_raw:
        _fail("report-bundle-preimages")
    heldout_expected_raw = render_technical_heldout_expected(case_rows)
    decoder = m2_decoder.ObservationDecoder(
        profile_policy_raw,
        profile_limits_raw,
        pilot_preimages["damage_policy_raw"],
    )
    clean_result_raw = decoder.render_result(
        m2_decoder.OBS_BITS,
        decoder.decode(m2_decoder.OBS_BITS, carrier_raw),
    )
    observation_roles = {
        "unknown-error-observation": "D3-000000",
        "known-erasure-observation": "D2-000000",
        "missing-unit-observation": "D4-000000",
        "negative-observation": "D7-000011",
    }
    if any(
        type(technical_files.get(role)) is not bytes
        or hashlib.sha256(technical_files[role]).hexdigest()
        != case_rows[case_id]["observation_sha256"]
        for role, case_id in observation_roles.items()
    ):
        _fail("report-bundle-preimages")
    technical_values = {
        "clean-observation": carrier_raw,
        "content-query": content_query_raw,
        **{role: technical_files[role] for role in observation_roles},
        "candidate-bindings": candidate_manifest_raw,
        "clean-expected": clean_result_raw,
        "content-query-expected": content_query_result_raw,
        "heldout-expected": heldout_expected_raw,
        "resource-limits": profile_limits_raw,
    }
    semantic_path_raw = m2_runner.semantic_path_bytes(
        m2_runner.run_m2_semantic_path(
            semantic_projection.content_stream,
            label_suppressed=True,
        )
    )
    learner_values = {
        "content-stream": semantic_projection.content_stream,
        "runner": _read_repo_file(source_root, "tools/m2/learner_runner.py"),
        "slice-binding": render_learner_slice_binding(
            gate8_policy_raw, semantic_projection.content_stream
        ),
        "heldout-cases": render_learner_heldout_request(gate8_policy_raw),
        "candidate-bindings": candidate_manifest_raw,
        "semantic-path-expected": semantic_path_raw,
        "heldout-expected": render_learner_expected(
            gate8_policy_raw,
            semantic_projection.content_stream,
            semantic_path_raw,
        ),
    }
    for bundle_kind, supplied, generated_values in (
        ("technical", technical_files, technical_values),
        ("learner", learner_files, learner_values),
    ):
        bundle, _common = _bundle_policy(gate8_policy_raw, bundle_kind)
        preimages = bundle.get("role_preimages")
        if type(preimages) is not dict:
            _fail("report-bundle-preimages")
        generated_roles = tuple(
            role
            for role in tuple(preimages)
            if not str(preimages[role]).startswith("tracked-template:")
        )
        exact_generated = {
            role: generated_values[role]
            for role in generated_roles
            if role in generated_values
        }
        if (
            len(exact_generated) != len(generated_roles)
            or dict(supplied)
            != build_bundle_files(
                gate8_policy_raw,
                source_root,
                bundle_kind,
                exact_generated,
            )
        ):
            _fail("report-bundle-preimages")
        validate_bundle_manifest(
            technical_bundle_raw if bundle_kind == "technical" else learner_bundle_raw,
            gate8_policy_raw,
            bundle_kind,
            supplied,
        )
    generated = validate_generated_evidence(
        generated_evidence_raw,
        generated_shared_preimages,
        generated_candidate_preimages,
    )
    projection_raws = {
        **{
            role: generated_candidate_preimages[role]
            for role in (
                "parameter_manifest",
                "known_answer_manifest",
                "shell_manifest",
                "recipe_manifest",
                "grammar_state_manifest",
                "work_scratch_ledger",
            )
        },
        "profile_limits_derivation": generated_shared_preimages[
            "profile_limits_derivation"
        ][1],
        "side_search_policy": generated_shared_preimages[
            "side_search_policy"
        ][1],
    }
    if not isinstance(owner_source_preimages, Mapping):
        _fail("report-owner-sources")
    required_source_paths = {
        path for _projection, paths in _OWNER_ROLES.values() for path in paths
    }
    if (
        set(owner_source_preimages) != required_source_paths
        or any(
            type(raw) is not bytes or not raw
            for raw in owner_source_preimages.values()
        )
    ):
        _fail("report-owner-sources")
    for path, raw in owner_source_preimages.items():
        if not path.startswith("artifacts/candidates/") and raw != _read_repo_file(
            source_root, path
        ):
            _fail("report-owner-sources")
    if (
        owner_source_preimages.get("spec/profile-policy-v1.toml")
        != profile_policy_raw
        or owner_source_preimages.get("spec/profile-limits-v1.toml")
        != profile_limits_raw
        or owner_source_preimages.get(
            f"artifacts/candidates/{_CANDIDATE_ID}/candidate-manifest.json"
        )
        != candidate_manifest_raw
        or owner_source_preimages.get(
            f"artifacts/candidates/{_CANDIDATE_ID}/semantic-envelope.json"
        )
        != semantic_envelope_raw
        or owner_source_preimages.get(
            f"artifacts/candidates/{_CANDIDATE_ID}/capacity-ledger.json"
        )
        != capacity_ledger_raw
        or projection_raws.get("side_search_policy")
        != side_search_projection_raw
        or projection_raws.get("work_scratch_ledger")
        != work_scratch_projection_raw
    ):
        _fail("report-owner-sources")
    for role, raw in projection_raws.items():
        source_preimages = {
            path: owner_source_preimages[path]
            for path in _OWNER_ROLES[role][1]
        }
        if raw != render_owner_projection(role, source_preimages):
            _fail("report-owner-projection")
    candidate = _artifact_manifest(
        candidate_manifest_raw,
        schema=_CANDIDATE_SCHEMA,
        reason="report-candidate",
    )
    side_projection = _artifact_manifest(
        side_search_projection_raw,
        schema=OWNER_PROJECTION_SCHEMA,
        reason="report-side-search",
    )
    work_projection = _artifact_manifest(
        work_scratch_projection_raw,
        schema=OWNER_PROJECTION_SCHEMA,
        reason="report-work-scratch",
    )
    if (
        side_projection.get("projection_id") != "side-search-v7"
        or work_projection.get("projection_id") != "work-scratch-ledger-v7"
        or candidate.get("profile_id") != _CANDIDATE_ID
        or hashlib.sha256(candidate_manifest_raw).hexdigest()
        != _CANDIDATE_MANIFEST_SHA256
        or candidate.get("carrier_sha256") != hashlib.sha256(carrier_raw).hexdigest()
        or candidate.get("ownership_sha256")
        != hashlib.sha256(ownership_ledger_raw).hexdigest()
        or candidate.get("capacity_ledger_sha256")
        != hashlib.sha256(capacity_ledger_raw).hexdigest()
        or candidate.get("density_ledger_sha256")
        != hashlib.sha256(density_ledger_raw).hexdigest()
        or candidate.get("semantic_envelope_sha256")
        != hashlib.sha256(semantic_envelope_raw).hexdigest()
    ):
        _fail("report-candidate")
    if (
        selection.get("candidate_rows") != [dict(candidate_row)]
        or selection.get("retained_finalist_ids") != [_CANDIDATE_ID]
        or selection.get("provisional_preferred_id") != _CANDIDATE_ID
        or selection.get("cross_language_manifest_sha256")
        != hashlib.sha256(cross_language_raw).hexdigest()
        or not isinstance(cross.get("summary"), dict)
        or cross["summary"].get("result") != "pass"  # type: ignore[index]
        or linux.get("evidence_source_projection_sha256")
        != hashlib.sha256(evidence_source_raw).hexdigest()
        or any(
            linux.get(key) is not expected
            for key, expected in (
                ("execution_snapshots_equal", True),
                ("canonical_bytes_equal", True),
                ("states_equal", True),
                ("ledgers_equal", True),
            )
        )
        or linux.get("host_full") != "pass"
        or linux.get("linux_full") != "pass"
    ):
        _fail("report-gate8")
    damage_rows = build_damage_rows(damage_manifest_raw, family_manifest_raws)
    if any(
        row["result"] != "pass" or row["wrong_accept_count"] != 0
        for row in damage_rows
    ):
        _fail("report-damage")
    generated_shared = generated.get("shared_identities")
    generated_candidates = generated.get("candidate_evidence")
    generated_rounds = generated.get("round_summary_identities")
    if (
        type(generated_shared) is not list
        or type(generated_candidates) is not list
        or len(generated_candidates) != 1
        or type(generated_candidates[0]) is not dict
        or generated_candidates[0].get("candidate_id") != _CANDIDATE_ID
        or type(generated_candidates[0].get("identities")) is not list
        or generated_rounds != []
    ):
        _fail("report-generated-evidence")
    generated_rows = [
        *generated_shared,
        *generated_candidates[0]["identities"],
        *generated_rounds,
    ]
    if any(
        type(row) is not dict
        or set(row) != {"kind", "name", "sha256"}
        or not _hex64(row.get("sha256"))
        for row in generated_rows
    ):
        _fail("report-generated-evidence")
    generated_hashes = sorted(
        generated_rows,
        key=lambda row: (str(row["kind"]).encode(), str(row["name"]).encode()),
    )
    if len({(row["kind"], row["name"]) for row in generated_hashes}) != len(
        generated_hashes
    ):
        _fail("report-generated-evidence")

    def generated_hash(kind: str) -> str:
        matches = [
            row["sha256"]
            for row in generated_hashes
            if row["kind"] == kind
            and (
                row["name"] != _CANDIDATE_ID
                or kind in _CANDIDATE_ROLE_ORDER
            )
        ]
        if len(matches) != 1 or not _hex64(matches[0]):
            _fail("report-generated-binding")
        return str(matches[0])

    expected_generated = {
        "content_stream": hashlib.sha256(
            pilot_preimages["content_stream_raw"]
        ).hexdigest(),
        "vertical_slice": hashlib.sha256(
            pilot_preimages["vertical_slice_raw"]
        ).hexdigest(),
        "selection_recomputation": hashlib.sha256(selection_raw).hexdigest(),
        "linux_attestation": hashlib.sha256(linux_attestation_raw).hexdigest(),
        "technical_bundle": hashlib.sha256(technical_bundle_raw).hexdigest(),
        "learner_bundle": hashlib.sha256(learner_bundle_raw).hexdigest(),
        "semantic_envelope": hashlib.sha256(semantic_envelope_raw).hexdigest(),
        "profile_limits_derivation": hashlib.sha256(
            projection_raws["profile_limits_derivation"]
        ).hexdigest(),
        "side_search_policy": hashlib.sha256(side_search_projection_raw).hexdigest(),
        "evidence_source_projection": hashlib.sha256(
            evidence_source_raw
        ).hexdigest(),
        **{
            role: hashlib.sha256(projection_raws[role]).hexdigest()
            for role in (
                "parameter_manifest",
                "known_answer_manifest",
                "shell_manifest",
                "recipe_manifest",
                "grammar_state_manifest",
            )
        },
        "carrier": hashlib.sha256(carrier_raw).hexdigest(),
        "ownership_ledger": hashlib.sha256(ownership_ledger_raw).hexdigest(),
        "capacity_ledger": hashlib.sha256(capacity_ledger_raw).hexdigest(),
        "density_ledger": hashlib.sha256(density_ledger_raw).hexdigest(),
        "work_scratch_ledger": hashlib.sha256(
            work_scratch_projection_raw
        ).hexdigest(),
        "damage_manifest": hashlib.sha256(damage_manifest_raw).hexdigest(),
        "independence_proof": hashlib.sha256(
            producer_artifacts["independence-proof"]
        ).hexdigest(),
        "cross_language_manifest": hashlib.sha256(cross_language_raw).hexdigest(),
    }
    if any(generated_hash(kind) != digest for kind, digest in expected_generated.items()):
        _fail("report-generated-binding")
    for family in _DAMAGE_FAMILIES:
        if generated_hash(f"damage_{family}") != hashlib.sha256(
            family_manifest_raws[family]
        ).hexdigest():
            _fail("report-generated-binding")
    ledger_rows = sorted(
        (
            {
                "kind": kind,
                "name": _CANDIDATE_ID,
                "sha256": generated_hash(kind),
            }
            for kind in (
                "ownership_ledger",
                "capacity_ledger",
                "density_ledger",
                "work_scratch_ledger",
                "damage_manifest",
            )
        ),
        key=lambda row: (str(row["kind"]).encode(), str(row["name"]).encode()),
    )
    if (
        owner_source_preimages.get("spec/bootstrap-v1.md")
        != pilot_preimages["bootstrap_spec_raw"]
        or owner_source_preimages.get("spec/route-data-v1.json")
        != pilot_preimages["route_data_raw"]
        or owner_source_preimages.get("spec/damage-policy-v1.toml")
        != pilot_preimages["damage_policy_raw"]
        or pilot_preimages["vertical_slice_raw"]
        != _read_repo_file(source_root, "studies/m2/slice-v0.json")
        or pilot_preimages["runner_raw"]
        != _read_repo_file(source_root, "tools/m2/learner_runner.py")
        or verifier_environment_raw
        != _read_repo_file(source_root, "artifacts/linux/verifier-v0.env")
    ):
        _fail("report-pilot-preimages")
    pilot = render_pilot_envelope(
        source_root=source_root,
        gate8_policy_raw=gate8_policy_raw,
        candidate_manifest_raw=candidate_manifest_raw,
        carrier_raw=carrier_raw,
        ownership_ledger_raw=ownership_ledger_raw,
        capacity_ledger_raw=capacity_ledger_raw,
        density_ledger_raw=density_ledger_raw,
        independence_proof_raw=producer_artifacts["independence-proof"],
        semantic_envelope_raw=semantic_envelope_raw,
        bootstrap_spec_raw=pilot_preimages["bootstrap_spec_raw"],
        route_data_raw=pilot_preimages["route_data_raw"],
        profile_policy_raw=profile_policy_raw,
        damage_policy_raw=pilot_preimages["damage_policy_raw"],
        parameter_projection_raw=generated_candidate_preimages[
            "parameter_manifest"
        ],
        geometry_equivalence_raw=pilot_preimages["geometry_equivalence_raw"],
        technical_bundle_raw=technical_bundle_raw,
        technical_files=technical_files,
        technical_heldout_classes_raw=pilot_preimages[
            "technical_heldout_classes_raw"
        ],
        learner_bundle_raw=learner_bundle_raw,
        learner_files=learner_files,
        content_stream_raw=pilot_preimages["content_stream_raw"],
        vertical_slice_raw=pilot_preimages["vertical_slice_raw"],
        runner_raw=pilot_preimages["runner_raw"],
        semantic_path_raw=pilot_preimages["semantic_path_raw"],
        generated_evidence_raw=generated_evidence_raw,
        generated_shared_preimages=generated_shared_preimages,
        generated_candidate_preimages=generated_candidate_preimages,
    )
    pilot_evidence = pilot.get("evidence_identities")
    if type(pilot_evidence) is not dict or (
        pilot_evidence.get("generated_evidence_manifest_sha256")
        != hashlib.sha256(generated_evidence_raw).hexdigest()
        or pilot_evidence.get("carrier_sha256") != generated_hash("carrier")
        or pilot_evidence.get("ownership_ledger_sha256")
        != generated_hash("ownership_ledger")
        or pilot_evidence.get("exact_cell_count_ledger_sha256")
        != generated_hash("capacity_ledger")
        or pilot_evidence.get("density_ledger_sha256")
        != generated_hash("density_ledger")
        or pilot_evidence.get("technical_bundle_sha256")
        != generated_hash("technical_bundle")
        or pilot_evidence.get("learner_bundle_sha256")
        != generated_hash("learner_bundle")
        or pilot_evidence.get("m2_all_content_stream_sha256")
        != generated_hash("content_stream")
        or pilot_evidence.get("vertical_slice_sha256")
        != generated_hash("vertical_slice")
    ):
        _fail("report-pilot")
    side = candidate.get("side")
    width = candidate.get("shell_width")
    if type(side) is not int or type(width) is not int:
        _fail("report-candidate")
    report = {
        "schema": "m2-feasibility-v0",
        "roadmap_revision": roadmap_revision,
        "m1_repository_baseline": "0feaf4b559f48507f2457e6d203f25c969a98589",
        "semantic_input_identities": semantic_rows,
        "spec_policy_limit_source_lock_identities": normative_rows,
        "candidate_rows": [dict(candidate_row)],
        "retained_finalist_ids": [_CANDIDATE_ID],
        "provisional_preferred_id": _CANDIDATE_ID,
        "selection_steps": selection["selection_steps"],
        "provisional_capacity_envelope": {
            "profile_limits_sha256": hashlib.sha256(profile_limits_raw).hexdigest(),
            "semantic_envelope_sha256": generated_hash("semantic_envelope"),
            "side_search_policy_sha256": generated_hash("side_search_policy"),
            "retained_ledger_identities": ledger_rows,
        },
        "preferred_carrier_identity_and_density": {
            "candidate_id": _CANDIDATE_ID,
            "carrier_sha256": generated_hash("carrier"),
            "ownership_ledger_sha256": generated_hash("ownership_ledger"),
            "density_ledger_sha256": generated_hash("density_ledger"),
            "N": side * side,
            "S": side,
            "W": width,
        },
        "damage_summary_D0_through_D7": damage_rows,
        "cross_language_and_linux_results": {
            "evidence_source_projection_sha256": hashlib.sha256(
                evidence_source_raw
            ).hexdigest(),
            "host_full": "pass",
            "linux_full": "pass",
            "execution_snapshots_equal": True,
            "canonical_bytes_equal": True,
            "states_equal": True,
            "ledgers_equal": True,
        },
        "technical_round_summaries": [],
        "qualifying_technical_round_id": "none",
        "learner_round_summaries": [],
        "qualifying_learner_round_id": "none",
        "m2_pilot_envelope": pilot,
        "permitted_administrative_counts": [],
        "accepted_limitations": [
            "Final transport dimensions remain provisional until the M4 actual-content rerun.",
            "Technical and learner validation is pending.",
        ],
        "generated_evidence_hashes": generated_hashes,
    }
    return _canonical(report, "candidate-ready-report")


def validate_candidate_ready_report(
    raw: bytes,
    **inputs: object,
) -> dict[str, object]:
    """Strictly reproduce a Candidate-ready report from all named evidence."""

    value = _canonical_value(raw, "candidate-ready-report")
    try:
        expected = render_candidate_ready_report(**inputs)  # type: ignore[arg-type]
    except TypeError as error:
        raise Gate8Error("candidate-ready-report-input") from error
    if raw != expected:
        _fail("candidate-ready-report-stale")
    return value


def _installed_pilot_envelope(
    root: Path,
    candidate: Mapping[str, object],
    carrier_raw: bytes,
    files: Mapping[str, tuple[bytes, str]],
    bundle_files: Mapping[str, Mapping[str, bytes]],
    generated_by_kind: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    """Reproduce the pilot projection from retained Gate-8 closure bytes."""

    side = candidate.get("side")
    width = candidate.get("shell_width")
    shell_rows = candidate.get("shell_rows")
    mapping = candidate.get("mapping")
    if (
        type(side) is not int
        or type(width) is not int
        or type(shell_rows) is not list
        or len(shell_rows) != 4
        or type(mapping) is not dict
    ):
        _fail("installed-gate8-pilot")
    count = int.from_bytes(carrier_raw[:4], "big") if len(carrier_raw) >= 4 else -1
    if count != side * side or len(carrier_raw) != 4 + (count + 7) // 8:
        _fail("installed-gate8-pilot")
    payload = carrier_raw[4:]
    route_preimage = bytearray(b"golden-board:m2:pilot:shell-route-bytes:v0\0")
    route_preimage.extend((4).to_bytes(8, "big"))
    for sector_id, row in enumerate(shell_rows):
        if type(row) is not dict or row.get("sector_id") != sector_id:
            _fail("installed-gate8-pilot")
        prefix_cells = row.get("route_prefix_cells")
        if type(prefix_cells) is not int or prefix_cells % 8:
            _fail("installed-gate8-pilot")
        bits = []
        try:
            for offset in range(prefix_cells):
                shell_row, shell_column = bootstrap.sector_cell(
                    side, width, sector_id, offset
                )
                bits.append(_carrier_bit(payload, shell_row * side + shell_column))
        except (bootstrap.BootstrapReject, IndexError) as error:
            raise Gate8Error("installed-gate8-pilot") from error
        route_bytes = _packed_bits(bits, "installed-gate8-pilot")
        route_preimage.extend(len(route_bytes).to_bytes(8, "big"))
        route_preimage.extend(route_bytes)
    shell_bits = [
        _carrier_bit(payload, row * side + column)
        for row in range(side)
        for column in range(side)
        if row < width
        or row >= side - width
        or column < width
        or column >= side - width
    ]
    shell_cell_preimage = bytearray(b"golden-board:m2:pilot:shell-cells:v0\0")
    shell_cell_preimage.extend(len(shell_bits).to_bytes(8, "big"))
    shell_cell_preimage.extend(
        _packed_bits(shell_bits, "installed-gate8-pilot")
    )
    shell_ownership_raw = _canonical(
        {
            "schema": "golden-board.m2-shell-ownership-projection/v0",
            "shell_rows": shell_rows,
        },
        "installed-gate8-pilot",
    )
    mapping_raw = _canonical(
        {
            "mapping": mapping,
            "schema": "golden-board.m2-mapping-parameters/v1",
        },
        "installed-gate8-pilot",
    )

    def digest(kind: str) -> str:
        row = generated_by_kind.get(kind)
        value = row.get("sha256") if isinstance(row, Mapping) else None
        if not _hex64(value):
            _fail("installed-gate8-pilot")
        return str(value)

    technical = bundle_files["technical"]
    learner = bundle_files["learner"]
    bootstrap_raw = _read_repo_file(root, "spec/bootstrap-v1.md")
    route_raw = _read_repo_file(root, "spec/route-data-v1.json")
    profile_raw = _read_repo_file(root, "spec/profile-policy-v1.toml")
    damage_raw = _read_repo_file(root, "spec/damage-policy-v1.toml")
    content_raw = files["projections/m2-all.content-v0.bin"][0]
    slice_raw = _read_repo_file(root, "studies/m2/slice-v0.json")
    runner_raw = _read_repo_file(root, "tools/m2/learner_runner.py")
    semantic_path_raw = files["projections/runner-semantic-path-v0.json"][0]
    technical_bundle_raw = files["bundles/technical-v0.json"][0]
    learner_bundle_raw = files["bundles/learner-v0.json"][0]
    heldout_raw = files["projections/technical-heldout-classes-v0.json"][0]
    generated_raw = files["generated-evidence-v0.json"][0]
    geometry_raw = files["projections/geometry-equivalence-v7.json"][0]
    geometry = _canonical_value(geometry_raw, "installed-gate8-pilot")
    interior = side - 2 * width
    maximum_run = max(128, (interior + 3) // 4)
    maximum_repeated = max(2, interior // 32)
    return {
        "technical_invariance": {
            "raw_geometry": {
                "observed_N": side * side,
                "observed_S": side,
                "admitted_N_S_pairs": geometry.get("admitted_N_S_pairs"),
                "equivalence_proof_sha256": hashlib.sha256(
                    geometry_raw
                ).hexdigest(),
            },
            "shell": {
                "W": width,
                "complete_bytes_sha256": hashlib.sha256(route_preimage).hexdigest(),
                "complete_cells_sha256": hashlib.sha256(
                    shell_cell_preimage
                ).hexdigest(),
                "sector_ownership_sha256": hashlib.sha256(
                    shell_ownership_raw
                ).hexdigest(),
            },
            "bootstrap": {
                "framing_sha256": hashlib.sha256(bootstrap_raw).hexdigest(),
                "dependency_graph_sha256": hashlib.sha256(route_raw).hexdigest(),
                "recipe_sha256": hashlib.sha256(route_raw).hexdigest(),
                "operation_set_sha256": hashlib.sha256(route_raw).hexdigest(),
                "tables_sha256": hashlib.sha256(route_raw).hexdigest(),
                "discriminator_sha256": hashlib.sha256(route_raw).hexdigest(),
                "grouping_id": "physical-unit-group-contiguous-v1",
                "bit_order_id": "msb-first",
                "traversal_id": "row-major-square-dihedral-polarity-v0",
            },
            "transport": {
                "candidate_id": _CANDIDATE_ID,
                "parameter_manifest_sha256": hashlib.sha256(
                    files["projections/parameter-manifest-v7.json"][0]
                ).hexdigest(),
                "common_grammar_sha256": hashlib.sha256(bootstrap_raw).hexdigest(),
                "protected_semantics_sha256": hashlib.sha256(profile_raw).hexdigest(),
                "state_semantics_sha256": hashlib.sha256(damage_raw).hexdigest(),
            },
            "mapping": {
                "formula_id": "affine-slot-then-interior-v1",
                "parameters_sha256": hashlib.sha256(mapping_raw).hexdigest(),
                "inverse_proof_sha256": digest("independence_proof"),
            },
            "interior_bounds": {
                "density_min_ppm": 250_000,
                "density_max_ppm": 750_000,
                "tile_density_min_ppm": 125_000,
                "tile_density_max_ppm": 875_000,
                "max_horizontal_run": maximum_run,
                "max_vertical_run": maximum_run,
                "max_repeated_rows": maximum_repeated,
                "max_repeated_columns": maximum_repeated,
            },
            "challenge": {
                "export_format_sha256": hashlib.sha256(
                    technical["export-format"]
                ).hexdigest(),
                "neutral_prompt_sha256": hashlib.sha256(
                    technical["neutral-opening-prompt"]
                ).hexdigest(),
                "heldout_class_manifest_sha256": hashlib.sha256(
                    heldout_raw
                ).hexdigest(),
            },
            "recipient_condition": {
                "mode": "individual",
                "headcount": 1,
                "allowed_tools_sha256": hashlib.sha256(
                    technical["allowed-tools"]
                ).hexdigest(),
                "session_policy_sha256": hashlib.sha256(
                    technical["session-policy"]
                ).hexdigest(),
                "facilitation_sha256": hashlib.sha256(
                    technical["facilitation-policy"]
                ).hexdigest(),
                "think_aloud_sha256": hashlib.sha256(
                    technical["facilitation-policy"]
                ).hexdigest(),
                "active_time_ceiling_seconds": 57_600,
                "elapsed_time_ceiling_seconds": 604_800,
            },
        },
        "learner_invariance": {
            "content_stream_sha256": hashlib.sha256(content_raw).hexdigest(),
            "slice_sha256": hashlib.sha256(slice_raw).hexdigest(),
            "runner_sha256": hashlib.sha256(runner_raw).hexdigest(),
            "label_suppressed_config_sha256": hashlib.sha256(
                learner["label-suppressed-config"]
            ).hexdigest(),
            "teaching_practice_order_sha256": hashlib.sha256(
                learner["teaching-practice-order"]
            ).hexdigest(),
            "semantic_path_sha256": hashlib.sha256(semantic_path_raw).hexdigest(),
            "facilitation_sha256": hashlib.sha256(
                learner["facilitation-policy"]
            ).hexdigest(),
            "learner_condition_sha256": hashlib.sha256(
                learner["learner-condition"]
            ).hexdigest(),
            "time_policy_sha256": hashlib.sha256(
                learner["session-policy"]
            ).hexdigest(),
        },
        "evidence_identities": {
            "m2_all_content_stream_sha256": hashlib.sha256(content_raw).hexdigest(),
            "vertical_slice_sha256": hashlib.sha256(slice_raw).hexdigest(),
            "carrier_sha256": hashlib.sha256(carrier_raw).hexdigest(),
            "exact_cell_count_ledger_sha256": digest("capacity_ledger"),
            "ownership_ledger_sha256": digest("ownership_ledger"),
            "density_ledger_sha256": digest("density_ledger"),
            "technical_bundle_sha256": hashlib.sha256(
                technical_bundle_raw
            ).hexdigest(),
            "learner_bundle_sha256": hashlib.sha256(learner_bundle_raw).hexdigest(),
            "generated_evidence_manifest_sha256": hashlib.sha256(
                generated_raw
            ).hexdigest(),
        },
    }


def validate_installed_gate8(root: Path) -> dict[str, object]:
    """Cheap recursive admission of one already-installed Gate-8 freeze.

    This path intentionally performs no candidate or damage regeneration.  It
    is the post-full/post-Linux release check over the sealed 69-file tree and
    tracked report; generation/check mode remains the stronger reproduction
    boundary.
    """

    root = _regular_root(root)
    policy_raw = _read_repo_file(root, "spec/gate8-policy-v0.toml")
    policy = load_gate8_policy(policy_raw)
    try:
        roadmap_raw = _read_repo_file(root, "docs/roadmap.md")
        roadmap_text = roadmap_raw.decode("utf-8")
    except UnicodeError as error:
        raise Gate8Error("installed-gate8-roadmap") from error
    gate8 = root / "artifacts" / "gate8"
    report_raw = _read_repo_file(root, "reports/m2-feasibility-v0.json")
    try:
        validate_candidate_ready_roadmap(roadmap_raw, report_raw)
    except Gate8Error as error:
        raise Gate8Error("installed-gate8-roadmap") from error
    try:
        gate8_metadata = os.lstat(gate8)
        paths = tuple(gate8.rglob("*"))
    except OSError as error:
        raise Gate8Error("installed-gate8-tree") from error
    if (
        stat.S_ISLNK(gate8_metadata.st_mode)
        or not stat.S_ISDIR(gate8_metadata.st_mode)
        or stat.S_IMODE(gate8_metadata.st_mode) != 0o700
        or len(paths) > 128
    ):
        _fail("installed-gate8-tree")
    files: dict[str, tuple[bytes, str]] = {}
    directories: set[str] = set()
    inodes: set[tuple[int, int]] = set()
    aggregate = 0
    for path in paths:
        metadata = os.lstat(path)
        if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
            if stat.S_IMODE(metadata.st_mode) != 0o700:
                _fail("installed-gate8-directory-mode")
            directories.add(path.relative_to(gate8).as_posix())
            continue
        mode = stat.S_IMODE(metadata.st_mode)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_nlink != 1
            or mode not in (0o644, 0o755)
            or not 1 <= metadata.st_size <= 16 * _MAX_FILE_BYTES
        ):
            _fail("installed-gate8-file")
        inode = (metadata.st_dev, metadata.st_ino)
        if inode in inodes:
            _fail("installed-gate8-hardlink")
        inodes.add(inode)
        try:
            raw = path.read_bytes()
            after = os.lstat(path)
        except OSError as error:
            raise Gate8Error("installed-gate8-file") from error
        if (
            len(raw) != metadata.st_size
            or after.st_dev != metadata.st_dev
            or after.st_ino != metadata.st_ino
            or after.st_mtime_ns != metadata.st_mtime_ns
            or after.st_nlink != 1
        ):
            _fail("installed-gate8-race")
        aggregate += len(raw)
        if aggregate > 83_886_080:
            _fail("installed-gate8-aggregate")
        relative = path.relative_to(gate8).as_posix()
        files[relative] = (
            raw,
            "100755" if mode == 0o755 else "100644",
        )
    phase = policy.get("phase_paths")
    if type(phase) is not dict or type(phase.get("gate8_exact_files")) is not list:
        _fail("installed-gate8-policy")
    fixed = {
        str(path).removeprefix("artifacts/gate8/")
        for path in phase["gate8_exact_files"]
        if type(path) is str and str(path).startswith("artifacts/gate8/")
    }
    if len(fixed) != 25:
        _fail("installed-gate8-policy")

    bundle_files: dict[str, dict[str, bytes]] = {}
    dynamic: set[str] = set()
    for kind in ("technical", "learner"):
        bundle_policy = policy.get(f"{kind}_bundle")
        if type(bundle_policy) is not dict:
            _fail("installed-gate8-policy")
        manifest_path = str(bundle_policy.get("path", "")).removeprefix(
            "artifacts/gate8/"
        )
        file_root = str(bundle_policy.get("file_root", "")).removeprefix(
            "artifacts/gate8/"
        )
        manifest_item = files.get(manifest_path)
        if manifest_item is None:
            _fail("installed-gate8-bundle")
        manifest = _canonical_value(
            manifest_item[0], "installed-gate8-bundle"
        )
        participant = manifest.get("participant_files")
        evaluator = manifest.get("evaluator_files")
        roles = bundle_policy.get("participant_roles", []) + bundle_policy.get(
            "evaluator_roles", []
        )
        if (
            type(participant) is not list
            or type(evaluator) is not list
            or type(roles) is not list
            or len(participant) + len(evaluator) != len(roles)
        ):
            _fail("installed-gate8-bundle")
        values: dict[str, bytes] = {}
        for role, row in zip(roles, participant + evaluator, strict=True):
            if (
                type(role) is not str
                or type(row) is not dict
                or set(row)
                != {"role_id", "path", "mode", "byte_length", "sha256"}
                or row.get("role_id") != role
                or type(row.get("path")) is not str
            ):
                _fail("installed-gate8-bundle")
            relative = f"{file_root}/{row['path']}"
            item = files.get(relative)
            if (
                item is None
                or item[1] != row.get("mode")
                or len(item[0]) != row.get("byte_length")
                or hashlib.sha256(item[0]).hexdigest() != row.get("sha256")
            ):
                _fail("installed-gate8-bundle")
            dynamic.add(relative)
            values[role] = item[0]
        validate_bundle_manifest(manifest_item[0], policy_raw, kind, values)
        bundle_files[kind] = values
    expected_files = fixed | dynamic
    expected_directories = {
        parent.as_posix()
        for name in expected_files
        for parent in Path(name).parents
        if parent.as_posix() != "."
    }
    if (
        len(dynamic) != 44
        or set(files) != expected_files
        or len(files) != 69
        or directories != expected_directories
    ):
        _fail("installed-gate8-allowlist")
    if any(files[name][1] != "100644" for name in fixed):
        _fail("installed-gate8-fixed-mode")

    source_raw = files["evidence-source-v0.json"][0]
    validate_gate8_source_surface(source_raw, root, policy_raw)
    candidate_raw = bundle_files["technical"].get("candidate-bindings")
    if (
        candidate_raw is None
        or candidate_raw != bundle_files["learner"].get("candidate-bindings")
        or hashlib.sha256(candidate_raw).hexdigest() != _CANDIDATE_MANIFEST_SHA256
    ):
        _fail("installed-gate8-candidate")
    candidate = _artifact_manifest(
        candidate_raw, schema=_CANDIDATE_SCHEMA, reason="installed-gate8-candidate"
    )
    receipts = {
        producer_id: files[f"receipts/{producer_id}.json"][0]
        for producer_id in _PRODUCER_IDS
    }
    cross_raw = files[f"{_CANDIDATE_ID}/cross-language-manifest.json"][0]
    cross = validate_cross_language_manifest(cross_raw, receipts, candidate_raw)
    if not isinstance(cross.get("summary"), dict) or cross["summary"].get(  # type: ignore[index]
        "result"
    ) != "pass":
        _fail("installed-gate8-cross")
    candidate_row = build_candidate_row(
        _CANDIDATE_METRICS,
        _read_repo_file(root, "spec/profile-policy-v1.toml"),
        cross_raw,
    )
    selection_raw = files["selection-v0.json"][0]
    selection = validate_selection(
        selection_raw,
        candidate_row,
        cross_raw,
        _read_repo_file(root, "spec/profile-policy-v1.toml"),
    )
    linux_raw = files["linux-attestation-v0.json"][0]
    validate_linux_attestation(
        linux_raw,
        source_raw,
        cross_raw,
        _read_repo_file(root, "artifacts/linux/verifier-v0.env"),
    )
    generated_raw = files["generated-evidence-v0.json"][0]
    generated = _canonical_value(generated_raw, "installed-gate8-generated")
    shared = generated.get("shared_identities")
    candidate_evidence = generated.get("candidate_evidence")
    if (
        set(generated)
        != {
            "candidate_evidence",
            "round_summary_identities",
            "schema",
            "shared_identities",
        }
        or generated.get("schema") != "m2-generated-evidence-v0"
        or generated.get("round_summary_identities") != []
        or type(shared) is not list
        or len(shared) != len(_SHARED_ROLE_NAMES)
        or type(candidate_evidence) is not list
        or len(candidate_evidence) != 1
        or type(candidate_evidence[0]) is not dict
        or set(candidate_evidence[0]) != {"candidate_id", "identities"}
        or candidate_evidence[0].get("candidate_id") != _CANDIDATE_ID
        or type(candidate_evidence[0].get("identities")) is not list
        or len(candidate_evidence[0]["identities"]) != len(_CANDIDATE_ROLE_ORDER)
    ):
        _fail("installed-gate8-generated")
    generated_rows = [*shared, *candidate_evidence[0]["identities"]]
    if (
        len(generated_rows) != 31
        or any(
            type(row) is not dict
            or set(row) != {"kind", "name", "sha256"}
            or not _hex64(row.get("sha256"))
            for row in generated_rows
        )
    ):
        _fail("installed-gate8-generated")
    if (
        [(row["kind"], row["name"]) for row in shared]
        != list(_SHARED_ROLE_NAMES)
        or [
            (row["kind"], row["name"])
            for row in candidate_evidence[0]["identities"]
        ]
        != [(role, _CANDIDATE_ID) for role in _CANDIDATE_ROLE_ORDER]
    ):
        _fail("installed-gate8-generated")
    generated_by_kind = {str(row["kind"]): row for row in generated_rows}
    direct_bindings = {
        "content_stream": files["projections/m2-all.content-v0.bin"][0],
        "vertical_slice": _read_repo_file(root, "studies/m2/slice-v0.json"),
        "selection_recomputation": selection_raw,
        "linux_attestation": linux_raw,
        "technical_bundle": files["bundles/technical-v0.json"][0],
        "learner_bundle": files["bundles/learner-v0.json"][0],
        "profile_limits_derivation": files[
            "projections/profile-limits-v7.json"
        ][0],
        "side_search_policy": files["projections/side-search-v7.json"][0],
        "evidence_source_projection": source_raw,
        "parameter_manifest": files["projections/parameter-manifest-v7.json"][0],
        "known_answer_manifest": files[
            "projections/known-answer-manifest-v7.json"
        ][0],
        "shell_manifest": files["projections/shell-manifest-v7.json"][0],
        "recipe_manifest": files["projections/recipe-manifest-v7.json"][0],
        "grammar_state_manifest": files[
            "projections/grammar-state-manifest-v7.json"
        ][0],
        "work_scratch_ledger": files[
            "projections/work-scratch-ledger-v7.json"
        ][0],
        "carrier": bundle_files["technical"]["clean-observation"],
        "cross_language_manifest": cross_raw,
    }
    cross_rows = cross.get("artifact_rows")
    if type(cross_rows) is not list or len(cross_rows) != len(_ARTIFACT_IDS):
        _fail("installed-gate8-cross")
    cross_digests = {
        str(row["artifact_id"]): str(row["native_python_sha256"])
        for row in cross_rows
        if type(row) is dict
    }
    if set(cross_digests) != set(_ARTIFACT_IDS):
        _fail("installed-gate8-cross")
    inventory_raw = files["projections/damage-inventory-v7.json"][0]
    inventory = _artifact_manifest(
        inventory_raw,
        schema=DAMAGE_INVENTORY_SCHEMA,
        reason="installed-gate8-inventory",
    )
    inventory_rows = inventory.get("file_rows")
    expected_damage_names = _damage_names()[:-1]
    if (
        set(inventory) != {"candidate_id", "file_rows", "schema"}
        or inventory.get("candidate_id") != _CANDIDATE_ID
        or type(inventory_rows) is not list
        or len(inventory_rows) != len(expected_damage_names)
        or any(
            type(row) is not dict
            or set(row) != {"byte_length", "path", "sha256"}
            or row.get("path") != name
            or type(row.get("byte_length")) is not int
            or not 1 <= int(row["byte_length"]) <= _DAMAGE_FILE_BYTES_MAX
            or not _hex64(row.get("sha256"))
            for row, name in zip(
                inventory_rows, expected_damage_names, strict=True
            )
        )
        or sum(int(row["byte_length"]) for row in inventory_rows)
        > _DAMAGE_AGGREGATE_BYTES_MAX
    ):
        _fail("installed-gate8-inventory")
    inventory_hashes = {
        str(row["path"]): str(row["sha256"]) for row in inventory_rows
    }
    unavailable_bindings = {
        "semantic_envelope": candidate.get("semantic_envelope_sha256"),
        "ownership_ledger": candidate.get("ownership_sha256"),
        "capacity_ledger": candidate.get("capacity_ledger_sha256"),
        "density_ledger": candidate.get("density_ledger_sha256"),
        "damage_manifest": inventory_hashes.get("damage-manifest.json"),
        **{
            f"damage_{family}": inventory_hashes.get(f"damage-{family}.json")
            for family in _DAMAGE_FAMILIES
        },
        "independence_proof": cross_digests.get("independence-proof"),
    }
    semantic_raw = files["projections/semantic-content-v7.json"][0]
    semantic = _artifact_manifest(
        semantic_raw,
        schema=SEMANTIC_CONTENT_SCHEMA,
        reason="installed-gate8-semantic",
    )
    if (
        set(semantic)
        != {
            "candidate_id",
            "common_plain_blocks_sha256",
            "content_stream_sha256",
            "schema",
            "section_envelopes_sha256",
            "semantic_envelope_sha256",
        }
        or semantic.get("candidate_id") != _CANDIDATE_ID
        or semantic.get("content_stream_sha256")
        != hashlib.sha256(direct_bindings["content_stream"]).hexdigest()
        or semantic.get("semantic_envelope_sha256")
        != candidate.get("semantic_envelope_sha256")
        or not _hex64(semantic.get("common_plain_blocks_sha256"))
        or not _hex64(semantic.get("section_envelopes_sha256"))
        or cross_digests.get("semantic-content-projection")
        != hashlib.sha256(semantic_raw).hexdigest()
        or cross_digests.get("candidate-manifest")
        != hashlib.sha256(candidate_raw).hexdigest()
        or cross_digests.get("carrier")
        != hashlib.sha256(direct_bindings["carrier"]).hexdigest()
        or cross_digests.get("ownership-ledger")
        != candidate.get("ownership_sha256")
        or cross_digests.get("capacity-ledger")
        != candidate.get("capacity_ledger_sha256")
        or cross_digests.get("density-ledger")
        != candidate.get("density_ledger_sha256")
        or cross_digests.get("damage-bundle-inventory")
        != hashlib.sha256(inventory_raw).hexdigest()
    ):
        _fail("installed-gate8-artifact-binding")
    if any(
        generated_by_kind.get(kind, {}).get("sha256")
        != hashlib.sha256(raw).hexdigest()
        for kind, raw in direct_bindings.items()
    ) or any(
        not _hex64(digest)
        or generated_by_kind.get(kind, {}).get("sha256") != digest
        for kind, digest in unavailable_bindings.items()
    ):
        _fail("installed-gate8-generated-binding")
    projection_files = {
        "parameter_manifest": "projections/parameter-manifest-v7.json",
        "known_answer_manifest": "projections/known-answer-manifest-v7.json",
        "shell_manifest": "projections/shell-manifest-v7.json",
        "recipe_manifest": "projections/recipe-manifest-v7.json",
        "grammar_state_manifest": "projections/grammar-state-manifest-v7.json",
        "work_scratch_ledger": "projections/work-scratch-ledger-v7.json",
        "profile_limits_derivation": "projections/profile-limits-v7.json",
        "side_search_policy": "projections/side-search-v7.json",
    }
    candidate_source_rows = {
        f"artifacts/candidates/{_CANDIDATE_ID}/candidate-manifest.json": (
            len(candidate_raw),
            hashlib.sha256(candidate_raw).hexdigest(),
        ),
        f"artifacts/candidates/{_CANDIDATE_ID}/semantic-envelope.json": (
            376_036,
            str(candidate["semantic_envelope_sha256"]),
        ),
        f"artifacts/candidates/{_CANDIDATE_ID}/capacity-ledger.json": (
            673_935,
            str(candidate["capacity_ledger_sha256"]),
        ),
    }
    for role, relative in projection_files.items():
        projection_raw = files[relative][0]
        projection = _canonical_value(
            projection_raw, "installed-gate8-owner-projection"
        )
        expected_rows = []
        for path in sorted(_OWNER_ROLES[role][1], key=str.encode):
            if path in candidate_source_rows:
                length, digest = candidate_source_rows[path]
            else:
                source_bytes = _read_repo_file(root, path)
                length = len(source_bytes)
                digest = hashlib.sha256(source_bytes).hexdigest()
            expected_rows.append(
                {"byte_length": length, "path": path, "sha256": digest}
            )
        if projection != {
            "projection_id": _OWNER_ROLES[role][0],
            "schema": OWNER_PROJECTION_SCHEMA,
            "source_rows": expected_rows,
        }:
            _fail("installed-gate8-owner-projection")
    content_raw = direct_bindings["content_stream"]
    semantic_path_raw = files["projections/runner-semantic-path-v0.json"][0]
    expected_semantic_path = m2_runner.semantic_path_bytes(
        m2_runner.run_m2_semantic_path(content_raw, label_suppressed=True)
    )
    if semantic_path_raw != expected_semantic_path:
        _fail("installed-gate8-semantic-path")
    learner_expected = {
        "content-stream": content_raw,
        "runner": _read_repo_file(root, "tools/m2/learner_runner.py"),
        "slice-binding": render_learner_slice_binding(policy_raw, content_raw),
        "heldout-cases": render_learner_heldout_request(policy_raw),
        "candidate-bindings": candidate_raw,
        "semantic-path-expected": semantic_path_raw,
        "heldout-expected": render_learner_expected(
            policy_raw, content_raw, semantic_path_raw
        ),
    }
    if dict(bundle_files["learner"]) != build_bundle_files(
        policy_raw, root, "learner", learner_expected
    ):
        _fail("installed-gate8-learner")
    content_query_raw, content_result_raw = render_technical_content_query(
        policy_raw, content_raw
    )
    decoder = m2_decoder.ObservationDecoder(
        _read_repo_file(root, "spec/profile-policy-v1.toml"),
        _read_repo_file(root, "spec/profile-limits-v1.toml"),
        _read_repo_file(root, "spec/damage-policy-v1.toml"),
    )
    clean_result_raw = decoder.render_result(
        m2_decoder.OBS_BITS,
        decoder.decode(m2_decoder.OBS_BITS, direct_bindings["carrier"]),
    )
    technical = bundle_files["technical"]
    technical_exact = {
        "clean-observation": direct_bindings["carrier"],
        "content-query": content_query_raw,
        "candidate-bindings": candidate_raw,
        "clean-expected": clean_result_raw,
        "content-query-expected": content_result_raw,
        "resource-limits": _read_repo_file(root, "spec/profile-limits-v1.toml"),
    }
    heldout_hashes = {
        "unknown-error-observation": "9cba9e3a83064ba6799ba8949304289d0c033b41457cc65b0f256a9f91f91249",
        "known-erasure-observation": "f131b068ab22ba6178d6db660cb89025132b1535cede2fbfe0699de95b6c26d6",
        "missing-unit-observation": "40bf1c82170bfee99f31857663abb335681fade56af164f5df423ed2221d1a3f",
        "negative-observation": "337d325906bce6aee21d27478ae7145c76b0913aeb46ed8716f7cfc73cdb1e57",
        "heldout-expected": "718435aed7a6e6bb57a9fbb67383ce1bc0cc385fd90955829a228599e9dc27c1",
    }
    if (
        any(technical.get(role) != raw for role, raw in technical_exact.items())
        or any(
            type(technical.get(role)) is not bytes
            or hashlib.sha256(technical[role]).hexdigest() != digest
            for role, digest in heldout_hashes.items()
        )
        or hashlib.sha256(
            files["projections/technical-heldout-classes-v0.json"][0]
        ).hexdigest()
        != "e279a39bba5492124283b277b5ef9c246ab567aa69e7a1daa60bbb66442e1e7e"
    ):
        _fail("installed-gate8-technical")
    try:
        revision_rows = [
            line
            for line in roadmap_text.splitlines()
            if line.startswith("| Roadmap revision | ") and line.endswith(" |")
        ]
        if len(revision_rows) != 1:
            _fail("installed-gate8-roadmap")
        roadmap_revision = int(revision_rows[0].split("|")[2].strip())
    except (ValueError, IndexError) as error:
        raise Gate8Error("installed-gate8-roadmap") from error
    semantic_rows, normative_rows = _source_identity_rows(
        _source_projection_value(source_raw), policy
    )
    damage_rows = [
        {
            "candidate_id": _CANDIDATE_ID,
            "family_id": family,
            "manifest_sha256": inventory_hashes[f"damage-{family}.json"],
            "guarantee_id": guarantee,
            "result": "pass",
            "wrong_accept_count": 0,
        }
        for family, guarantee in zip(
            _DAMAGE_FAMILIES, _DAMAGE_GUARANTEES, strict=True
        )
    ]
    generated_hashes = sorted(
        generated_rows,
        key=lambda row: (str(row["kind"]).encode(), str(row["name"]).encode()),
    )
    ledger_rows = sorted(
        (
            {
                "kind": kind,
                "name": _CANDIDATE_ID,
                "sha256": generated_by_kind[kind]["sha256"],
            }
            for kind in (
                "ownership_ledger",
                "capacity_ledger",
                "density_ledger",
                "work_scratch_ledger",
                "damage_manifest",
            )
        ),
        key=lambda row: (str(row["kind"]).encode(), str(row["name"]).encode()),
    )
    side = candidate.get("side")
    width = candidate.get("shell_width")
    if type(side) is not int or type(width) is not int:
        _fail("installed-gate8-candidate")
    expected_report = {
        "schema": "m2-feasibility-v0",
        "roadmap_revision": roadmap_revision,
        "m1_repository_baseline": "0feaf4b559f48507f2457e6d203f25c969a98589",
        "semantic_input_identities": semantic_rows,
        "spec_policy_limit_source_lock_identities": normative_rows,
        "candidate_rows": [candidate_row],
        "retained_finalist_ids": [_CANDIDATE_ID],
        "provisional_preferred_id": _CANDIDATE_ID,
        "selection_steps": selection["selection_steps"],
        "provisional_capacity_envelope": {
            "profile_limits_sha256": hashlib.sha256(
                _read_repo_file(root, "spec/profile-limits-v1.toml")
            ).hexdigest(),
            "semantic_envelope_sha256": generated_by_kind[
                "semantic_envelope"
            ]["sha256"],
            "side_search_policy_sha256": generated_by_kind[
                "side_search_policy"
            ]["sha256"],
            "retained_ledger_identities": ledger_rows,
        },
        "preferred_carrier_identity_and_density": {
            "candidate_id": _CANDIDATE_ID,
            "carrier_sha256": generated_by_kind["carrier"]["sha256"],
            "ownership_ledger_sha256": generated_by_kind[
                "ownership_ledger"
            ]["sha256"],
            "density_ledger_sha256": generated_by_kind[
                "density_ledger"
            ]["sha256"],
            "N": side * side,
            "S": side,
            "W": width,
        },
        "damage_summary_D0_through_D7": damage_rows,
        "cross_language_and_linux_results": {
            "evidence_source_projection_sha256": hashlib.sha256(
                source_raw
            ).hexdigest(),
            "host_full": "pass",
            "linux_full": "pass",
            "execution_snapshots_equal": True,
            "canonical_bytes_equal": True,
            "states_equal": True,
            "ledgers_equal": True,
        },
        "technical_round_summaries": [],
        "qualifying_technical_round_id": "none",
        "learner_round_summaries": [],
        "qualifying_learner_round_id": "none",
        "m2_pilot_envelope": _installed_pilot_envelope(
            root,
            candidate,
            direct_bindings["carrier"],
            files,
            bundle_files,
            generated_by_kind,
        ),
        "permitted_administrative_counts": [],
        "accepted_limitations": [
            "Final transport dimensions remain provisional until the M4 actual-content rerun.",
            "Technical and learner validation is pending.",
        ],
        "generated_evidence_hashes": generated_hashes,
    }
    expected_raw = _canonical(expected_report, "installed-gate8-report")
    if report_raw != expected_raw:
        _fail("installed-gate8-report")
    return expected_report
