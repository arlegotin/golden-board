#!/usr/bin/env python3
"""Prepare or apply the archive-first revision; no gate outcomes are generated."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT))
from tools.m2.generate_gate8 import (  # noqa: E402
    _fsync_directory, _rename_noreplace, _prior_tree_expected_paths,
)
from golden_board import canonical_manifest  # noqa: E402

GATE8 = "artifacts/gate8"
REPORT = "reports/m2-feasibility-v0.json"
CANDIDATE = "artifacts/candidates/eh72-hier-r5-r2-r1-crc32c-v0"
ARCHIVE = "artifacts/history/m2-pre-participant-revision-v1"
TOMBSTONE = "artifacts/.gate8-participant-revision-remove-v1"
ROOTS = (CANDIDATE, GATE8, "artifacts/quiz", "artifacts/linux", "artifacts/history")
DOCUMENTS = tuple(sorted(("docs/roadmap.md", "docs/m2-spec.md", "docs/m2-plan.md", "docs/decisions.md")))
SOURCE = GATE8 + "/evidence-source-v0.json"
INCIDENTAL = GATE8 + "/bundles/learner/participant/__pycache__/m2-learner-runner.cpython-314.pyc"
PINS = {
    SOURCE: "1943409374c64366f2619d76e807f7f2e1a415aecb3b3afbba73ced006c077b1",
    "docs/roadmap.md": "695e28fa0432da10a6dc6dbdb61ca2bd8764ea6006bbbeb558c3b8f20933b4c9",
    REPORT: "2315d001d3cceadeeacd1dfeedefeb681b6be3a32b787541fc6260502881d1b3",
    GATE8 + "/generated-evidence-v0.json": "d06134324aa0e0d89c46f4c5366f105dd949f5cf7b94700446f605bdf73413f9",
    "artifacts/linux/verifier-v0.env": "315f9021f83ee8c6640af6ea6bcd58387287bcef42e7b27eaaf5f76b2187f6a2",
}
MAX_FILES = 4096
MAX_FILE = 8 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
MAX_MANIFEST = 2 * 1024 * 1024
SCHEMA = "golden-board.m2-participant-revision-transition/v1"


class TransitionError(ValueError):
    pass


def _require(ok, reason):
    if not ok:
        raise TransitionError(reason)


def _canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii") + b"\n"


def _path(value, maximum=255):
    _require(type(value) is str and 0 < len(value) <= maximum
             and all(32 <= ord(c) < 127 for c in value)
             and "\\" not in value and all(c not in ("", ".", "..") for c in value.split("/")), "path")
    return value


def _directory(path):
    path = Path(path)
    _require(path.is_absolute() and path == Path(os.path.abspath(path)), "absolute-directory")
    for component in (path, *path.parents):
        _require(stat.S_ISDIR(component.lstat().st_mode), "directory-link-or-type")
    return path


def _regular(path, maximum=MAX_FILE):
    _directory(path.parent)
    before = path.lstat()
    _require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
             and stat.S_IMODE(before.st_mode) in (0o600, 0o644, 0o755)
             and before.st_size <= maximum, "regular-file")
    return before


def _stream(path, destination=None, maximum=MAX_FILE):
    before = _regular(path, maximum)
    digest = hashlib.sha256()
    total = 0
    chunks = [] if destination is None else None
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        opened = os.fstat(source.fileno())
        _require((opened.st_dev, opened.st_ino, opened.st_nlink) == (before.st_dev, before.st_ino, 1), "read-race")
        while chunk := source.read(min(1024 * 1024, maximum + 1 - total)):
            total += len(chunk)
            _require(total <= maximum, "file-bound")
            digest.update(chunk)
            if destination is None:
                chunks.append(chunk)
            else:
                destination.write(chunk)
        after = os.fstat(source.fileno())
    final = path.lstat()
    fields = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_nlink)
    _require(fields(before) == fields(after) == fields(final) and total == before.st_size, "read-race")
    return total, digest.hexdigest(), stat.S_IMODE(before.st_mode), b"".join(chunks) if chunks is not None else None


def _read(path, maximum=MAX_FILE):
    return _stream(path, maximum=maximum)[3]


def _write(path, raw):
    _directory(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as out:
        os.fchmod(out.fileno(), 0o600)
        out.write(raw)
        out.flush()
        os.fsync(out.fileno())


def _mkdirs(path):
    missing = []
    current = path
    while not os.path.lexists(current):
        missing.append(current)
        current = current.parent
    _directory(current)
    for item in reversed(missing):
        item.mkdir(mode=0o700)


def _walk(root, relative, *, exclude=()):
    files, directories = set(), set()
    pending = [relative]
    while pending:
        name = pending.pop()
        if name in exclude:
            continue
        _path(name, 280)
        path = root / name
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            directories.add(name)
            _require(len(directories) <= MAX_FILES, "directory-bound")
            with os.scandir(path) as entries:
                for entry in entries:
                    pending.append(name + "/" + entry.name)
                    _require(len(pending) + len(files) + len(directories) <= 2 * MAX_FILES, "entry-bound")
        else:
            _regular(path)
            files.add(name)
            _require(len(files) <= MAX_FILES, "file-count")
    return files, directories


def _source_paths(raw):
    value = json.loads(raw)
    _require(type(value) is dict and set(value) == {"schema", "entries", "roadmap_normative_sha256"}
             and value["schema"] == "m2-evidence-source-v0"
             and type(value["entries"]) is list and len(value["entries"]) == 323, "source-projection")
    _require(_canonical(value) == raw, "source-canonical")
    return value["entries"]


def _admit_gate8(read, rows):
    observed = {}
    for name, row in rows.items():
        if name.startswith(GATE8 + "/") and name != INCIDENTAL:
            raw = read(name)
            if name.endswith(".json"):
                canonical_manifest.validate_canonical_manifest(raw)
            observed[name[len(GATE8) + 1:]] = (raw, int(row["mode"], 8))
    expected = _prior_tree_expected_paths(read("spec/gate8-policy-v0.toml"), observed)
    _require(set(expected) == set(observed) and all(observed[p][1] == mode for p, mode in expected.items()), "canonical-gate8-view")
    row = rows.get(INCIDENTAL)
    _require(row is not None and (row["byte_length"], row["sha256"], row["mode"]) == (
        45017, "54820a16d61653dab4f043a0abcb41c8ef2f23edf4eec6de21414403f9a830cb", "0644"), "incidental-identity")


def _admit_historical(root):
    _directory(root / ".git")
    for name, digest in PINS.items():
        _require(hashlib.sha256(_read(root / name)).hexdigest() == digest, "historical-identity:" + name)
    entries = _source_paths(_read(root / SOURCE))
    names = []
    for row in entries:
        _require(type(row) is dict and set(row) == {"path", "mode", "byte_length", "sha256"}, "source-row")
        name = _path(row["path"])
        length, digest, mode, _ = _stream(root / name)
        _require(type(row["byte_length"]) is int and row["byte_length"] == length
                 and row["sha256"] == digest and row["mode"] == f"100{mode:o}", "source-preimage:" + name)
        names.append(name)
    _require(names == sorted(set(names)), "source-order")
    files, _ = _walk(root, GATE8)
    rows = {}
    for name in files:
        length, digest, mode, _ = _stream(root / name)
        rows[name] = {"byte_length": length, "sha256": digest, "mode": f"{mode:04o}"}
    _admit_gate8(lambda name: _read(root / name), rows)
    return tuple(names)


def _replace_once(raw, old, new):
    old, new = old.encode(), new.encode()
    _require(raw.count(old) == 1 and new not in raw, "document-anchor")
    return raw.replace(old, new, 1)


def _pending_documents(original):
    roadmap = original["docs/roadmap.md"]
    for old, new in (
        ("| Roadmap revision | 10 |", "| Roadmap revision | 11 |"),
        ("| Last updated | 2026-08-30 |", "| Last updated | 2026-09-16 |"),
        ("| Project state | Candidate ready |", "| Project state | In progress |"),
        ("| M2 — Full-carrier bootstrap and transport feasibility | Candidate ready — independent validation pending |",
         "| M2 — Full-carrier bootstrap and transport feasibility | In progress |"),
        ("The candidate passes gates 1–8 with provisional preferred candidate", "The historical candidate passed gates 1–8 with provisional preferred candidate"),
        ("automated native and clean-Linux evidence passes, while technical and learner validation remains pending.",
         "its automated native and clean-Linux evidence passed, while technical and learner validation remained pending. Revision 11 reopens Gates 1–8 for the participant-driven semantic and transport revision under `spec/m2-participant-revision-transition-v1.md`. The complete prior tuple is preserved under `artifacts/history/m2-pre-participant-revision-v1/`; the historical v7 candidate is not an active revised candidate. No current Candidate-ready claim is admitted. The 512 KiB ceiling is unchanged, and fresh technical and learner validation remains pending."),
    ):
        roadmap = _replace_once(roadmap, old, new)
    result = {"docs/roadmap.md": roadmap}
    notice = ("\n**Revision 11 current scope:** M2 is In progress; Gates 1–8 reopen for the\n"
              "participant-driven semantic and transport revision. Prior R3 descriptions\n"
              "below are historical evidence, not current gate outcomes. M0/M1 and the\n"
              "512 KiB ceiling are unchanged. The archive-first transition is owned by\n"
              "[`spec/m2-participant-revision-transition-v1.md`](../spec/m2-participant-revision-transition-v1.md).\n"
              "Fresh production evidence and affected human validation remain pending.\n")
    for name in ("docs/m2-spec.md", "docs/m2-plan.md"):
        raw = original[name]
        raw = _replace_once(raw, "Revision 10, M2 Linux verifier provenance refresh", "Revision 11, M2 participant-driven semantic and transport revision")
        raw = _replace_once(raw, "Gates 1–7 remain exact for the sole R3 v7 candidate; gate 8 is reopened only for the acquired Linux verifier provenance refresh", "In progress; Gates 1–8 reopened; prior R3 results are historical")
        anchor = "\n## 1. " if name.endswith("spec.md") else "\n**Goal:**"
        _require(raw.count(anchor.encode()) == 1, "document-anchor")
        raw = raw.replace(anchor.encode(), notice.encode() + anchor.encode(), 1)
        result[name] = raw
    result["docs/decisions.md"] = original["docs/decisions.md"] + (
        "\n## 2026-09-16 — M2 reopens for the participant-driven revision\n\n"
        "The revised teaching, semantic slice and transport change the source of\n"
        "Gates 1–7 as well as Gate 8. The verifier-only reopen cannot cover this work.\n"
        "Revision 11 therefore sets M2 In progress and reopens Gates 1–8 without\n"
        "changing M0/M1 or the 512 KiB carrier ceiling. The exact previous source,\n"
        "owners, candidate, receipts, report, timeline, acquisition provenance and\n"
        "original quiz material are archived before authority changes, under\n"
        "`spec/m2-participant-revision-transition-v1.md`. The historical v7 candidate\n"
        "is excluded from the revised active set. No new gate result or fresh human\n"
        "success is asserted; fresh production and affected human evidence remain\n"
        "pending. The archive is internal provenance, not participant material.\n"
    ).encode()
    return result


def _row(name, raw, mode, prefix):
    return {"archive_path": prefix + name, "byte_length": len(raw), "mode": f"{mode:04o}",
            "path": name, "sha256": hashlib.sha256(raw).hexdigest()}


def prepare(historical_root, output_dir):
    root = _directory(Path(historical_root))
    output = Path(output_dir)
    _directory(output.parent)
    _require(not os.path.lexists(output) and not output.is_relative_to(root), "private-output")
    _require(not os.path.lexists(root / ARCHIVE) and not os.path.lexists(root / TOMBSTONE), "prior-transition-present")
    source_paths = _admit_historical(root)
    files = set(source_paths) | set(DOCUMENTS) | {REPORT}
    directories = set()
    for name in ROOTS:
        observed, dirs = _walk(root, name)
        files.update(observed)
        directories.update(dirs)
    _require(len(files) <= MAX_FILES and len(directories) <= MAX_FILES, "tuple-count")
    rows, total = [], 0
    for name in sorted(files):
        _path(name)
        length, digest, mode, _ = _stream(root / name)
        total += length
        _require(total <= MAX_TOTAL, "tuple-bytes")
        rows.append({"archive_path": ("incidental/" if name == INCIDENTAL else "prior/") + name,
                     "byte_length": length, "mode": f"{mode:04o}", "path": name, "sha256": digest})
    pending = _pending_documents({name: _read(root / name) for name in DOCUMENTS})
    manifest = {"schema": SCHEMA, "files": rows, "directories": sorted(directories),
                "pending": [_row(name, pending[name], 0o644, "pending/") for name in DOCUMENTS]}
    raw = _canonical(manifest)
    _require(len(raw) <= MAX_MANIFEST, "manifest-bound")
    output.mkdir(mode=0o700)
    for name in directories:
        _mkdirs(output / "prior" / name)
    for row in rows:
        target = output / row["archive_path"]
        _mkdirs(target.parent)
        with target.open("xb") as out:
            os.fchmod(out.fileno(), 0o600)
            length, digest, mode, _ = _stream(root / row["path"], out)
            out.flush()
            os.fsync(out.fileno())
        _require((length, digest, f"{mode:04o}") == (row["byte_length"], row["sha256"], row["mode"]), "copy-preimage")
    for name in DOCUMENTS:
        target = output / "pending" / name
        _mkdirs(target.parent)
        _write(target, pending[name])
    _write(output / "archive-manifest.json", raw)
    digest = hashlib.sha256(raw).hexdigest()
    _load_package(output, digest)
    _verify_live(root, manifest, output, pending=False)
    _sync_tree(output)
    return digest


def _load_package(root, digest):
    _directory(root)
    _require(type(digest) is str and re.fullmatch("[0-9a-f]{64}", digest) is not None, "manifest-digest")
    raw = _read(root / "archive-manifest.json", MAX_MANIFEST)
    _require(hashlib.sha256(raw).hexdigest() == digest, "manifest-digest")
    value = json.loads(raw)
    _require(type(value) is dict and set(value) == {"schema", "files", "directories", "pending"}
             and value["schema"] == SCHEMA and _canonical(value) == raw, "manifest-shape")
    expected_files = {"archive-manifest.json"}
    expected_dirs = set()
    total = 0
    for field in ("files", "pending"):
        rows = value[field]
        _require(type(rows) is list and 1 <= len(rows) <= MAX_FILES, "manifest-count")
        names = []
        for row in rows:
            _require(type(row) is dict and set(row) == {"archive_path", "path", "byte_length", "sha256", "mode"}, "manifest-row")
            name = _path(row["path"])
            names.append(name)
            prefix = "pending/" if field == "pending" else "incidental/" if name == INCIDENTAL else "prior/"
            _require(row["archive_path"] == prefix + name and type(row["byte_length"]) is int
                     and 0 <= row["byte_length"] <= MAX_FILE and row["mode"] in ("0600", "0644", "0755")
                     and type(row["sha256"]) is str and re.fullmatch("[0-9a-f]{64}", row["sha256"]) is not None, "manifest-row-value")
            if field == "files":
                total += row["byte_length"]
                _require(total <= MAX_TOTAL, "tuple-bytes")
            length, sha, mode, _ = _stream(root / row["archive_path"])
            _require((length, sha, mode) == (row["byte_length"], row["sha256"], 0o600), "archive-preimage")
            expected_files.add(row["archive_path"])
        _require(names == sorted(set(names)), "manifest-order")
        if field == "pending":
            _require(tuple(names) == DOCUMENTS and all(row["mode"] == "0644" for row in rows), "pending-set")
    dirs = value["directories"]
    _require(type(dirs) is list and len(dirs) <= MAX_FILES and all(type(d) is str for d in dirs)
             and dirs == sorted(set(dirs)) and set(ROOTS).issubset(dirs), "directory-set")
    for name in dirs:
        _path(name)
        _require(any(name == p or name.startswith(p + "/") for p in ROOTS)
                 and name != ARCHIVE and not name.startswith(ARCHIVE + "/"), "directory-scope")
        expected_dirs.add("prior/" + name)
    for name in expected_files | expected_dirs.copy():
        expected_dirs.update(str(p) for p in Path(name).parents if str(p) != ".")
    actual_files, actual_dirs = set(), set()
    with os.scandir(root) as entries:
        for entry in entries:
            files, dirs = _walk(root, entry.name)
            actual_files.update(files)
            actual_dirs.update(dirs)
    _require(actual_files == expected_files and actual_dirs == expected_dirs, "archive-extras")
    _require(all(stat.S_IMODE((root / d).lstat().st_mode) == 0o700 for d in actual_dirs | {"."})
             and stat.S_IMODE((root / "archive-manifest.json").stat().st_mode) == 0o600, "archive-mode")
    original = {name: _read(root / "prior" / name) for name in DOCUMENTS}
    pending = _pending_documents(original)
    _require(all(_read(root / "pending" / name) == raw for name, raw in pending.items()), "pending-projection")
    _verify_historical_package(root, value)
    return value


def _verify_historical_package(root, manifest):
    rows = {row["path"]: row for row in manifest["files"]}
    _require(set(PINS).issubset(rows) and set(DOCUMENTS).issubset(rows), "historical-required-files")
    for name, digest in PINS.items():
        _require(rows[name]["sha256"] == digest, "historical-package-identity:" + name)
    read = lambda name: _read(root / rows[name]["archive_path"])
    entries = _source_paths(read(SOURCE))
    source_names = []
    for entry in entries:
        _require(type(entry) is dict and set(entry) == {"path", "mode", "byte_length", "sha256"}, "source-row")
        name = _path(entry["path"])
        source_names.append(name)
        row = rows.get(name)
        _require(row is not None and type(entry["byte_length"]) is int
                 and (row["byte_length"], row["sha256"], "100" + row["mode"][1:]) == (
                     entry["byte_length"], entry["sha256"], entry["mode"]), "archived-source-preimage")
    _require(source_names == sorted(set(source_names)), "source-order")
    allowed = set(source_names) | set(DOCUMENTS) | {REPORT}
    _require(all(p in allowed or any(p.startswith(r + "/") for r in ROOTS) for p in rows), "archive-file-scope")
    _admit_gate8(read, rows)


def _verify_live(root, manifest, package, *, pending):
    _directory(root / ".git")
    rows = {row["path"]: row for row in manifest["files"]}
    gate_rows = {p: r for p, r in rows.items() if p.startswith(GATE8 + "/")}
    live_gate, tomb = os.path.lexists(root / GATE8), os.path.lexists(root / TOMBSTONE)
    _require(not (live_gate and tomb) and (pending or (live_gate and not tomb)), "gate8-state")
    seen_files, seen_dirs = set(), set()
    for name in ROOTS:
        if name == GATE8 and not live_gate:
            continue
        files, dirs = _walk(root, name, exclude=(ARCHIVE,))
        seen_files.update(files)
        seen_dirs.update(dirs)
    expected_root_files = {p for p in rows if any(p.startswith(r + "/") for r in ROOTS)}
    expected_dirs = set(manifest["directories"])
    if pending:
        _require(seen_files <= expected_root_files and seen_dirs <= expected_dirs, "live-extras")
        _require(seen_files - set(gate_rows) == expected_root_files - set(gate_rows), "live-missing")
        _require(seen_dirs - {d for d in expected_dirs if d == GATE8 or d.startswith(GATE8 + "/")}
                 == expected_dirs - {d for d in expected_dirs if d == GATE8 or d.startswith(GATE8 + "/")}, "live-directories")
    else:
        _require(seen_files == expected_root_files and seen_dirs == expected_dirs, "live-file-set")
    for name, row in rows.items():
        if pending and name.startswith(GATE8 + "/"):
            continue
        if pending and name == REPORT and not os.path.lexists(root / name):
            continue
        length, sha, mode, _ = _stream(root / name)
        if pending and name in DOCUMENTS:
            old = _read(package / "prior" / name)
            new = _read(package / "pending" / name)
            _require(_read(root / name) in ((new,) if name == "docs/roadmap.md" else (old, new)), "document-state")
            _require(mode == int(row["mode"], 8), "document-mode")
        else:
            _require((length, sha, f"{mode:04o}") == (row["byte_length"], row["sha256"], row["mode"]), "live-preimage:" + name)
    if live_gate or tomb:
        prefix = GATE8 if live_gate else TOMBSTONE
        files, dirs = _walk(root, prefix)
        translated = {GATE8 + p[len(prefix):] for p in files}
        _require(translated <= set(gate_rows), "gate8-extras")
        allowed_dirs = {d for d in expected_dirs if d == GATE8 or d.startswith(GATE8 + "/")}
        _require({GATE8 + p[len(prefix):] for p in dirs} <= allowed_dirs, "gate8-extra-directory")
        for name in files:
            row = gate_rows[GATE8 + name[len(prefix):]]
            length, sha, mode, _ = _stream(root / name)
            _require((length, sha, f"{mode:04o}") == (row["byte_length"], row["sha256"], row["mode"]), "gate8-preimage")


def _sync_tree(root):
    directories = [root]
    for current, dirs, _ in os.walk(root):
        directories.extend(Path(current) / name for name in dirs)
    for name in sorted(directories, key=lambda p: len(p.parts), reverse=True):
        _fsync_directory(name)


def _install_archive(repository, prepared, digest, manifest):
    destination = repository / ARCHIVE
    if os.path.lexists(destination):
        _load_package(destination, digest)
        return
    _directory(destination.parent)
    stage = Path(tempfile.mkdtemp(prefix=".participant-revision-stage-", dir=repository / "artifacts"))
    for name in manifest["directories"]:
        _mkdirs(stage / "prior" / name)
    for row in manifest["files"] + manifest["pending"]:
        target = stage / row["archive_path"]
        _mkdirs(target.parent)
        with target.open("xb") as out:
            os.fchmod(out.fileno(), 0o600)
            _stream(prepared / row["archive_path"], out)
            out.flush()
            os.fsync(out.fileno())
    _write(stage / "archive-manifest.json", _read(prepared / "archive-manifest.json", MAX_MANIFEST))
    _load_package(stage, digest)
    _sync_tree(stage)
    _rename_noreplace(stage, destination)
    _fsync_directory(destination.parent)
    _load_package(destination, digest)


def _replace_document(root, name, prior, pending):
    path = root / name
    observed = _read(path)
    if observed == pending:
        return
    _require(observed == prior, "document-preimage")
    stage = path.with_name("." + path.name + ".participant-revision-v1")
    _require(not os.path.lexists(stage), "document-stage-present")
    _write(stage, pending)
    stage.chmod(0o644)
    with stage.open("rb") as source:
        os.fsync(source.fileno())
    _require(_read(path) == prior, "document-prewrite")
    os.replace(stage, path)
    _fsync_directory(path.parent)


def _remove_stale(root, manifest, archive):
    _verify_live(root, manifest, archive, pending=True)
    report = root / REPORT
    if os.path.lexists(report):
        _require(_read(report) == _read(archive / "prior" / REPORT), "report-predelete")
        report.unlink()
        _fsync_directory(report.parent)
    live, tomb = root / GATE8, root / TOMBSTONE
    if os.path.lexists(live):
        _rename_noreplace(live, tomb)
        _fsync_directory(live.parent)
    if os.path.lexists(tomb):
        _verify_live(root, manifest, archive, pending=True)
        files, directories = _walk(root, TOMBSTONE)
        rows = {row["path"]: row for row in manifest["files"]}
        for name in sorted(files):
            original = GATE8 + name[len(TOMBSTONE):]
            row = rows[original]
            length, sha, mode, _ = _stream(root / name)
            _require((length, sha, f"{mode:04o}") == (row["byte_length"], row["sha256"], row["mode"]), "gate8-predelete")
            (root / name).unlink()
        for name in sorted(directories, key=lambda p: (len(p.split("/")), p), reverse=True):
            (root / name).rmdir()
        _fsync_directory(tomb.parent)


def apply(repository_root, prepared, manifest_sha256):
    root, package = _directory(Path(repository_root)), _directory(Path(prepared))
    _require(not package.is_relative_to(root), "external-preparation")
    manifest = _load_package(package, manifest_sha256)
    roadmap = _read(root / "docs/roadmap.md")
    prior = _read(package / "prior/docs/roadmap.md")
    pending = _read(package / "pending/docs/roadmap.md")
    _require(roadmap in (prior, pending), "roadmap-state")
    is_pending = roadmap == pending
    for name in DOCUMENTS:
        document = root / name
        stage = document.with_name("." + document.name + ".participant-revision-v1")
        _require(not os.path.lexists(stage), "document-stage-present")
    if is_pending:
        _load_package(root / ARCHIVE, manifest_sha256)
    _verify_live(root, manifest, package, pending=is_pending)
    if not is_pending:
        _install_archive(root, package, manifest_sha256, manifest)
        _verify_live(root, manifest, package, pending=False)
        _replace_document(root, "docs/roadmap.md", prior, pending)
    for name in DOCUMENTS:
        if name != "docs/roadmap.md" and _read(root / name) != _read(package / "pending" / name):
            _replace_document(root, name, _read(package / "prior" / name), _read(package / "pending" / name))
    _remove_stale(root, manifest, root / ARCHIVE)
    _verify_live(root, manifest, root / ARCHIVE, pending=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--historical-root", required=True, type=Path)
    prepare_parser.add_argument("--output-dir", required=True, type=Path)
    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument("--repository-root", required=True, type=Path)
    apply_parser.add_argument("--prepared", required=True, type=Path)
    apply_parser.add_argument("--manifest-sha256", required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            print(prepare(args.historical_root, args.output_dir))
        else:
            apply(args.repository_root, args.prepared, args.manifest_sha256)
            print("M2 In progress; prior tuple archived; stale Gate8/report absent.")
    except (OSError, ValueError) as error:
        parser.exit(2, "transition rejected: " + str(error)[:512] + "\n")


if __name__ == "__main__":
    main()
