#!/usr/bin/env python3
"""Build and reproduce the bounded M2 Git execution-snapshot manifest."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile


SCHEMA = "m2-execution-snapshot-v0"
MAX_ENTRIES = 8_192
MAX_FILE_BYTES = 16 * 1_048_576
MAX_INDEX_BYTES = 16 * 1_048_576
MAX_MANIFEST_BYTES = 1_048_576
MAX_PATH_BYTES = 4_096
MODES = {0o100644: "100644", 0o100755: "100755"}


class SnapshotError(RuntimeError):
    """The repository cannot be represented by the closed snapshot grammar."""


def _git(
    root: Path,
    *arguments: str,
    input_bytes: bytes | None = None,
    index_path: Path | None = None,
) -> bytes:
    environment = os.environ.copy()
    environment["GIT_CONFIG_GLOBAL"] = "/dev/null"
    environment["GIT_CONFIG_NOSYSTEM"] = "1"
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    if index_path is not None:
        environment["GIT_INDEX_FILE"] = os.fspath(index_path)
    result = subprocess.run(
        [
            "git", "-c", "core.excludesFile=/dev/null",
            "-c", f"safe.directory={root}", "-C", os.fspath(root), *arguments,
        ],
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise SnapshotError(f"git {' '.join(arguments)} failed: {detail}")
    return result.stdout


def _digest_stream(stream) -> tuple[int, str]:
    digest = hashlib.sha256()
    length = 0
    while True:
        chunk = stream.read(65_536)
        if not chunk:
            break
        length += len(chunk)
        if length > MAX_FILE_BYTES:
            raise SnapshotError("execution-snapshot file exceeds byte limit")
        digest.update(chunk)
    return length, digest.hexdigest()


def _regular_file(root: Path, path: bytes) -> tuple[str, int, str] | None:
    if not path or len(path) > MAX_PATH_BYTES or b"\0" in path or path.startswith(b"/"):
        raise SnapshotError(f"unsafe execution-snapshot path: {path!r}")
    components = path.split(b"/")
    if any(component in {b"", b".", b".."} for component in components):
        raise SnapshotError(f"unsafe execution-snapshot path: {path!r}")
    current = os.fspath(root).encode()
    for component in components:
        current = os.path.join(current, component)
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            return None
        if component != components[-1]:
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise SnapshotError(f"unsafe execution-snapshot parent: {path!r}")
            continue
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise SnapshotError(f"unsupported execution-snapshot file: {path!r}")
        mode = "100755" if metadata.st_mode & 0o111 else "100644"
        with open(current, "rb", buffering=0) as stream:
            length, digest = _digest_stream(stream)
        after = os.lstat(current)
        if (
            after.st_dev != metadata.st_dev
            or after.st_ino != metadata.st_ino
            or after.st_size != metadata.st_size
            or after.st_mtime_ns != metadata.st_mtime_ns
            or after.st_mode != metadata.st_mode
        ):
            raise SnapshotError(f"execution-snapshot file changed while hashing: {path!r}")
        return mode, length, digest
    raise AssertionError("unreachable")


def _blob_sha256(root: Path, oid: str) -> str:
    process = subprocess.Popen(
        [
            "git", "-c", f"safe.directory={root}", "-C", os.fspath(root),
            "cat-file", "blob", oid,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
    )
    assert process.stdout is not None
    try:
        length, digest = _digest_stream(process.stdout)
    except BaseException:
        process.kill()
        process.wait()
        raise
    stderr = process.stderr.read() if process.stderr is not None else b""
    if process.wait() != 0:
        raise SnapshotError(
            f"cannot read Git blob {oid}: {stderr.decode('utf-8', 'replace').strip()}"
        )
    if length > MAX_FILE_BYTES:
        raise SnapshotError("Git blob exceeds execution-snapshot byte limit")
    return digest


def _tree_layer(root: Path, head_oid: str) -> dict[bytes, tuple[str, str]]:
    output = _git(root, "ls-tree", "-rz", "--full-tree", head_oid)
    layer: dict[bytes, tuple[str, str]] = {}
    for record in output.split(b"\0"):
        if not record:
            continue
        metadata, path = record.split(b"\t", 1)
        mode_bytes, kind, oid_bytes = metadata.split(b" ")
        if kind != b"blob" or mode_bytes not in {b"100644", b"100755"}:
            raise SnapshotError(f"unsupported HEAD entry: {path!r}")
        layer[path] = (mode_bytes.decode("ascii"), _blob_sha256(root, oid_bytes.decode("ascii")))
    return layer


def _repository_index(root: Path) -> Path:
    git_dir_text = _git(root, "rev-parse", "--absolute-git-dir").rstrip(b"\n")
    try:
        git_dir = Path(os.fsdecode(git_dir_text))
    except UnicodeError as error:
        raise SnapshotError("Git directory is not a filesystem path") from error
    if git_dir != root / ".git" or not git_dir.is_dir() or git_dir.is_symlink():
        raise SnapshotError("execution snapshot requires a repository-local .git directory")
    index_path = git_dir / "index"
    metadata = index_path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_INDEX_BYTES:
        raise SnapshotError("Git index is missing, unsafe, or oversized")
    return index_path


def _index_layer(
    root: Path, command_index: Path
) -> dict[bytes, tuple[str, str, str]]:
    output = _git(root, "ls-files", "--stage", "-z", index_path=command_index)
    layer: dict[bytes, tuple[str, str, str]] = {}
    for record in output.split(b"\0"):
        if not record:
            continue
        metadata_bytes, path = record.split(b"\t", 1)
        mode_bytes, oid_bytes, stage = metadata_bytes.split(b" ")
        if stage != b"0":
            raise SnapshotError(f"unmerged index entry: {path!r}")
        if mode_bytes not in {b"100644", b"100755"}:
            raise SnapshotError(f"unsupported index entry: {path!r}")
        oid = oid_bytes.decode("ascii")
        layer[path] = (
            mode_bytes.decode("ascii"),
            _blob_sha256(root, oid),
            oid,
        )
    return layer


def _worktree_paths(root: Path, command_index: Path) -> set[bytes]:
    output = _git(
        root,
        "ls-files",
        "-z",
        "--cached",
        "--others",
        "--exclude-standard",
        index_path=command_index,
    )
    paths = {path for path in output.split(b"\0") if path}
    if len(paths) > MAX_ENTRIES:
        raise SnapshotError("execution snapshot exceeds entry limit")
    return paths


def _reject_renames_and_verify_status(
    root: Path, changed: set[bytes], command_index: Path
) -> None:
    output = _git(
        root,
        "-c",
        "status.renames=copies",
        "status",
        "--porcelain=v2",
        "-z",
        "--untracked-files=all",
        index_path=command_index,
    )
    status_paths: set[bytes] = set()
    for record in output.split(b"\0"):
        if not record:
            continue
        kind = record[:1]
        if kind in {b"2", b"u"}:
            raise SnapshotError("rename, copy, or unmerged Git state is unsupported")
        if kind == b"1":
            pieces = record.split(b" ", 8)
            if len(pieces) != 9:
                raise SnapshotError("malformed Git status record")
            status_paths.add(pieces[8])
        elif kind in {b"?", b"!"}:
            status_paths.add(record[2:])
        else:
            raise SnapshotError("unknown Git status record")
    if status_paths != changed:
        raise SnapshotError("Git status and execution-snapshot classification disagree")


def _classify(
    head: tuple[str, str] | None,
    index: tuple[str, str, str] | None,
    worktree: tuple[str, int, str] | None,
) -> str:
    head_pair = head
    index_pair = None if index is None else index[:2]
    worktree_pair = None if worktree is None else (worktree[0], worktree[2])
    if head_pair is not None and index_pair == head_pair and worktree_pair == head_pair:
        return "tracked_clean"
    if head_pair is not None and index_pair is not None and worktree_pair is not None:
        if index_pair != head_pair and worktree_pair == index_pair:
            return "index_modified"
        if index_pair == head_pair and worktree_pair != head_pair:
            return "worktree_modified"
        if index_pair != head_pair and worktree_pair != index_pair:
            return "index_and_worktree_modified"
    if head_pair is None and index_pair is not None and worktree_pair is not None:
        if worktree_pair == index_pair:
            return "index_added"
        return "index_added_worktree_modified"
    if head_pair is not None and index_pair is None:
        if worktree_pair is None:
            return "index_deleted"
        return "index_deleted_worktree_present"
    if head_pair is not None and index_pair is not None and worktree_pair is None:
        if index_pair == head_pair:
            return "worktree_deleted"
        return "index_modified_worktree_deleted"
    if head_pair is None and index_pair is None and worktree_pair is not None:
        return "untracked"
    raise SnapshotError("Git layers have an unsupported state")


def build_manifest(root: Path) -> tuple[dict[str, object], bytes, dict[bytes, tuple[str, str, str]]]:
    root = root.resolve(strict=True)
    head_oid = _git(root, "rev-parse", "--verify", "HEAD").decode("ascii").strip()
    if len(head_oid) != 40 or any(character not in "0123456789abcdef" for character in head_oid):
        raise SnapshotError("HEAD is not a lowercase SHA-1 object identity")
    index_path = _repository_index(root)
    with index_path.open("rb", buffering=0) as stream:
        index_length, raw_index_sha256 = _digest_stream(stream)
    if index_length > MAX_INDEX_BYTES:
        raise SnapshotError("Git index exceeds byte limit")

    with tempfile.TemporaryDirectory(prefix="gb-snapshot-index-") as directory:
        command_index = Path(directory) / "index"
        shutil.copyfile(index_path, command_index, follow_symlinks=False)
        head = _tree_layer(root, head_oid)
        index = _index_layer(root, command_index)
        paths = set(head) | set(index) | _worktree_paths(root, command_index)
        if len(paths) > MAX_ENTRIES:
            raise SnapshotError("execution snapshot exceeds entry limit")

        entries: list[dict[str, object]] = []
        changed: set[bytes] = set()
        for path in sorted(paths):
            try:
                text_path = path.decode("utf-8")
            except UnicodeDecodeError as error:
                raise SnapshotError(f"non-UTF-8 execution-snapshot path: {path!r}") from error
            worktree = _regular_file(root, path)
            git_class = _classify(head.get(path), index.get(path), worktree)
            if git_class != "tracked_clean":
                changed.add(path)
            entries.append(
                {
                    "path": text_path,
                    "head_mode": head[path][0] if path in head else "absent",
                    "head_sha256": head[path][1] if path in head else "absent",
                    "index_mode": index[path][0] if path in index else "absent",
                    "index_sha256": index[path][1] if path in index else "absent",
                    "worktree_mode": worktree[0] if worktree is not None else "absent",
                    "worktree_byte_length": worktree[1] if worktree is not None else 0,
                    "worktree_sha256": worktree[2] if worktree is not None else "absent",
                    "git_class": git_class,
                }
            )

        _reject_renames_and_verify_status(root, changed, command_index)
        _git(root, "diff", "--check", index_path=command_index)
        _git(root, "diff", "--cached", "--check", index_path=command_index)

    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "head_oid": head_oid,
        "raw_index_sha256": raw_index_sha256,
        "entries": entries,
    }
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
        + b"\n"
    )
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise SnapshotError("execution-snapshot manifest exceeds byte limit")
    return manifest, manifest_bytes, index


def _copy_regular(source: Path, target: Path, relative: str, mode: str) -> None:
    source_path = source / relative
    target_path = target / relative
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with source_path.open("rb", buffering=0) as reader, target_path.open("xb", buffering=0) as writer:
        copied = 0
        while True:
            chunk = reader.read(65_536)
            if not chunk:
                break
            copied += len(chunk)
            if copied > MAX_FILE_BYTES:
                raise SnapshotError("execution-snapshot file exceeds byte limit")
            writer.write(chunk)
    target_path.chmod(0o755 if mode == "100755" else 0o644)


def materialize(source: Path, target: Path) -> str:
    source = source.resolve(strict=True)
    if target.exists():
        raise SnapshotError("execution-snapshot target already exists")
    manifest, manifest_bytes, index = build_manifest(source)
    target.mkdir(parents=True)
    initialized = subprocess.run(
        ["git", "init", "--quiet", os.fspath(target)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if initialized.returncode != 0:
        raise SnapshotError(
            "Git init for execution snapshot failed: "
            + initialized.stderr.decode("utf-8", "replace").strip()
        )
    head_oid = str(manifest["head_oid"])
    bundle = target / ".git" / "m2-base.bundle"
    _git(source, "bundle", "create", os.fspath(bundle), "HEAD")
    _git(target, "fetch", os.fspath(bundle), "HEAD")
    _git(target, "update-ref", "HEAD", head_oid)
    bundle.unlink()

    for mode, _digest, oid in index.values():
        blob = _git(source, "cat-file", "blob", oid)
        written = _git(target, "hash-object", "-w", "--stdin", input_bytes=blob).decode("ascii").strip()
        if written != oid:
            raise SnapshotError("index blob identity changed while materializing")

    source_index = source / ".git" / "index"
    target_index = target / ".git" / "index"
    shutil.copyfile(source_index, target_index, follow_symlinks=False)
    target_index.chmod(0o644)

    for entry in manifest["entries"]:
        assert isinstance(entry, dict)
        mode = entry["worktree_mode"]
        if mode != "absent":
            _copy_regular(source, target, str(entry["path"]), str(mode))

    _manifest_again, target_bytes, _target_index = build_manifest(target)
    if target_bytes != manifest_bytes:
        raise SnapshotError("materialized execution snapshot differs from source")
    return hashlib.sha256(manifest_bytes).hexdigest()


def file_sha256(path: Path) -> str:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise SnapshotError("hash target is not a regular file")
    with path.open("rb", buffering=0) as stream:
        _length, digest = _digest_stream(stream)
    return digest


def main(arguments: list[str]) -> int:
    try:
        if len(arguments) == 2 and arguments[0] == "manifest":
            _manifest, data, _index = build_manifest(Path(arguments[1]))
            sys.stdout.buffer.write(data)
            return 0
        if len(arguments) == 2 and arguments[0] == "digest":
            _manifest, data, _index = build_manifest(Path(arguments[1]))
            print(hashlib.sha256(data).hexdigest())
            return 0
        if len(arguments) == 2 and arguments[0] == "file-sha256":
            print(file_sha256(Path(arguments[1])))
            return 0
        if len(arguments) == 3 and arguments[0] == "materialize":
            print(materialize(Path(arguments[1]), Path(arguments[2])))
            return 0
        print(
            "usage: snapshot.py manifest ROOT | digest ROOT | "
            "file-sha256 FILE | materialize SOURCE TARGET",
            file=sys.stderr,
        )
        return 2
    except (OSError, SnapshotError, subprocess.SubprocessError, UnicodeError) as error:
        print(f"snapshot: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
