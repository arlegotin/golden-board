from __future__ import annotations

import hashlib
import os
import re
import selectors
import subprocess
import time
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import cast

from golden_board.manifest import decode_canonical_manifest, encode_canonical_value
from golden_board.registry import RegistryError, _run_bounded_process
from golden_board.source_doctor import build_source_report
from golden_board.source_lock import (
    SafeFileError,
    load_source_lock,
    read_regular_below,
    validate_same_mount_tree,
)


class ReportError(ValueError):
    pass


LOWER_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
ACCEPTANCE_HEADING = "## 12. Final acceptance matrix"
EXPECTED_GATE_IDS = tuple(f"G{index}" for index in range(1, 19))
EXPECTED_NATIVE_COMMANDS: list[dict[str, object]] = [
    {
        "phase": "acquisition",
        "argv": ["uv", "--no-config", "sync", "--project", ".", "--locked"],
        "exit_code": 0,
    },
    {
        "phase": "acquisition",
        "argv": ["cargo", "fetch", "--manifest-path", "Cargo.toml", "--locked"],
        "exit_code": 0,
    },
    {
        "phase": "acquisition",
        "argv": [
            "cargo",
            "build",
            "--manifest-path",
            "Cargo.toml",
            "--workspace",
            "--locked",
        ],
        "exit_code": 0,
    },
    {
        "phase": "offline",
        "argv": [
            "uv",
            "--no-config",
            "sync",
            "--project",
            ".",
            "--offline",
            "--locked",
        ],
        "exit_code": 0,
    },
    {
        "phase": "offline",
        "argv": [
            "cargo",
            "build",
            "--manifest-path",
            "Cargo.toml",
            "--workspace",
            "--offline",
            "--locked",
        ],
        "exit_code": 0,
    },
    {
        "phase": "offline",
        "argv": ["scripts/check", "full"],
        "exit_code": 0,
    },
]
EXPECTED_NATIVE_ISOLATION: dict[str, object] = {
    "project_environment": ".venv",
    "cache_roots": {
        "cargo_home": "artifacts/cargo-home",
        "cargo_target": "artifacts/cargo-target",
        "uv_cache": "artifacts/uv-cache",
        "uv_python": "artifacts/uv-python",
    },
    "environment": {
        "acquisition": {
            "CARGO_HOME": "artifacts/cargo-home",
            "CARGO_TARGET_DIR": "artifacts/cargo-target",
            "UV_CACHE_DIR": "artifacts/uv-cache",
            "UV_MANAGED_PYTHON": "true",
            "UV_NO_CONFIG": "1",
            "UV_PYTHON_INSTALL_DIR": "artifacts/uv-python",
            "UV_PROJECT_ENVIRONMENT": ".venv",
        },
        "offline": {
            "CARGO_HOME": "artifacts/cargo-home",
            "CARGO_NET_OFFLINE": "true",
            "CARGO_TARGET_DIR": "artifacts/cargo-target",
            "UV_CACHE_DIR": "artifacts/uv-cache",
            "UV_MANAGED_PYTHON": "true",
            "UV_NO_CONFIG": "1",
            "UV_OFFLINE": "1",
            "UV_PYTHON_DOWNLOADS": "never",
            "UV_PYTHON_INSTALL_DIR": "artifacts/uv-python",
            "UV_PROJECT_ENVIRONMENT": ".venv",
        },
    },
    "network": {
        "acquisition": "enabled",
        "offline": "package_manager_offline",
        "os_enforcement": "not_claimed_at_m0",
    },
}
NATIVE_TOOL_KEYS = ("cargo", "cc", "git", "ld", "python", "rust", "sdk", "uv")
NATIVE_EXCLUDED_PATHS = {
    "docs/roadmap.md",
    "reports/release-summary.json",
}
G1_PROTOCOL = "fresh-checkout-source-doctor+native-isolated-v0"
EXPECTED_GENERATION_INPUT_PATHS = (
    "docs/64_games.md",
    "inputs/source-lock.toml",
    "python/golden_board/source_doctor.py",
)
EXPECTED_G1_EVIDENCE = (
    ("anthology_raw_sha256", "docs/64_games.md"),
    ("source_doctor_report_raw_sha256", "reports/source-doctor.json"),
)
FIXED_GIT_ENVIRONMENT = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_TERMINAL_PROMPT": "0",
    "LANG": "C",
    "LC_ALL": "C",
    "TZ": "UTC",
}
GIT_ENVIRONMENT_KEYS = frozenset({*FIXED_GIT_ENVIRONMENT, "HOME", "PATH", "TMPDIR"})
MAX_TRACKED_PATH_BYTES = 4 * 1024 * 1024
MAX_GIT_CONFIG_BYTES = 64 * 1024
MAX_GIT_CONFIG_KEYS = 4_096
MAX_GIT_TREE_ENTRIES = 200_000
MAX_TRACKED_PATHS = 10_000
MAX_IDENTITY_FILE_BYTES = 32 * 1024 * 1024
MAX_REPORT_BYTES = 16 * 1024 * 1024
MAX_ROADMAP_BYTES = 4 * 1024 * 1024
MAX_ROADMAP_CHARACTERS = 4 * 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024
GIT_TIMEOUT_SECONDS = 30


def _exact_dict(value: object, keys: set[str], label: str) -> dict[str, object]:
    if type(value) is not dict:
        raise ReportError(f"{label} must be an object")
    result = cast(dict[str, object], value)
    actual = set(result)
    if actual != keys:
        raise ReportError(
            f"{label} keys must be {sorted(keys)}, found {sorted(actual)}"
        )
    return result


def _exact_int(value: object, expected: int, label: str) -> None:
    if type(value) is not int or value != expected:
        raise ReportError(f"{label} must be integer {expected}")


def _read_below(root: Path, relative: PurePosixPath, max_bytes: int) -> bytes:
    try:
        return read_regular_below(root, relative, max_bytes)
    except SafeFileError as error:
        raise ReportError(
            f"unsafe or unreadable repository input: {relative}"
        ) from error


def _sha256_below(root: Path, relative: PurePosixPath) -> str:
    return hashlib.sha256(
        _read_below(root, relative, MAX_IDENTITY_FILE_BYTES)
    ).hexdigest()


def _read_utf8_below(root: Path, relative: PurePosixPath, max_bytes: int) -> str:
    try:
        return _read_below(root, relative, max_bytes).decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        raise ReportError(f"file is not strict UTF-8: {relative}") from error


def _safe_relative_path(value: object, label: str) -> str:
    if (
        type(value) is not str
        or not value
        or any(character in value for character in ("\0", "\\"))
    ):
        raise ReportError(f"{label} must be a canonical repository-relative path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in ("", ".", "..") for part in path.parts)
        or path.as_posix() != value
    ):
        raise ReportError(f"{label} is not a canonical repository-relative path")
    return value


def _identity_records(value: object, label: str) -> list[dict[str, str]]:
    if type(value) is not list:
        raise ReportError(f"{label} must be an array")
    if len(cast(list[object], value)) > MAX_TRACKED_PATHS:
        raise ReportError(f"{label} exceeds its M0 record-count cap")
    records: list[dict[str, str]] = []
    for index, item in enumerate(cast(list[object], value)):
        record = _exact_dict(item, {"path", "sha256"}, f"{label}[{index}]")
        path = _safe_relative_path(record["path"], f"{label}[{index}].path")
        digest = record["sha256"]
        if type(digest) is not str or LOWER_SHA256.fullmatch(digest) is None:
            raise ReportError(f"{label}[{index}].sha256 must be lowercase SHA-256")
        records.append({"path": path, "sha256": digest})
    paths = [record["path"] for record in records]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise ReportError(f"{label} paths must be unique and sorted")
    return records


def _validated_git_context(
    git_executable: Path,
    git_environment: dict[str, str],
) -> tuple[str, dict[str, str]]:
    if not isinstance(git_executable, Path):
        raise ReportError("Git executable must be an absolute Path")
    executable = os.fspath(git_executable)
    if (
        not git_executable.is_absolute()
        or "\0" in executable
        or "\\" in executable
        or ".." in git_executable.parts
    ):
        raise ReportError("Git executable must be an absolute canonical path")
    if (
        type(git_environment) is not dict
        or set(git_environment) != GIT_ENVIRONMENT_KEYS
        or any(
            type(key) is not str
            or type(value) is not str
            or "\0" in key
            or "\0" in value
            for key, value in git_environment.items()
        )
    ):
        raise ReportError("Git environment must contain exactly the reviewed keys")
    environment = dict(git_environment)
    if any(
        environment[key] != expected for key, expected in FIXED_GIT_ENVIRONMENT.items()
    ):
        raise ReportError("Git environment fixed values drifted")
    for key in ("HOME", "TMPDIR"):
        path = Path(environment[key])
        if not path.is_absolute() or ".." in path.parts:
            raise ReportError(f"Git environment {key} must be absolute")
    search_path = environment["PATH"].split(os.pathsep)
    if not search_path or any(
        not item or not Path(item).is_absolute() or ".." in Path(item).parts
        for item in search_path
    ):
        raise ReportError("Git environment PATH must contain only absolute entries")
    return executable, environment


def _git_command_prefix(root: Path, executable: str) -> tuple[str, ...]:
    return (
        executable,
        "--no-pager",
        "--no-replace-objects",
        f"--git-dir={root / '.git'}",
        f"--work-tree={root}",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.untrackedCache=false",
        "-c",
        "core.excludesFile=/dev/null",
        "-c",
        "core.attributesFile=/dev/null",
        "-c",
        "core.hooksPath=/dev/null",
    )


def _validated_git_tree(root: Path) -> bytes:
    if (
        not isinstance(root, Path)
        or not root.is_absolute()
        or "\0" in os.fspath(root)
        or "\\" in os.fspath(root)
        or ".." in root.parts
    ):
        raise ReportError("Git repository root is unsafe")
    try:
        validate_same_mount_tree(
            root,
            PurePosixPath(".git"),
            max_entries=MAX_GIT_TREE_ENTRIES,
            max_depth=64,
        )
        config = read_regular_below(
            root,
            PurePosixPath(".git/config"),
            MAX_GIT_CONFIG_BYTES,
        )
        for relative in (
            PurePosixPath(".git/commondir"),
            PurePosixPath(".git/config.worktree"),
            PurePosixPath(".git/info/attributes"),
            PurePosixPath(".git/objects/info/alternates"),
            PurePosixPath(".git/objects/info/http-alternates"),
        ):
            try:
                read_regular_below(root, relative, MAX_GIT_CONFIG_BYTES)
            except SafeFileError as error:
                if str(error) != "safe_file.path":
                    raise
            else:
                raise ReportError("Git metadata redirection is forbidden")
        try:
            exclude = read_regular_below(
                root,
                PurePosixPath(".git/info/exclude"),
                MAX_GIT_CONFIG_BYTES,
            )
        except SafeFileError as error:
            if str(error) != "safe_file.path":
                raise
        else:
            try:
                exclude_text = exclude.decode("utf-8", "strict")
            except UnicodeDecodeError as error:
                raise ReportError("Git metadata exclude file is unsafe") from error
            if (
                b"\0" in exclude
                or b"\r" in exclude
                or (exclude and not exclude.endswith(b"\n"))
                or any(
                    line and not line.startswith("#")
                    for line in exclude_text.split("\n")
                )
            ):
                raise ReportError("Git metadata exclude file is unsafe")
    except ReportError:
        raise
    except SafeFileError as error:
        raise ReportError("Git metadata tree is unsafe") from error
    return config


def _validate_git_config_names(raw: bytes, stderr: bytes) -> None:
    if (
        type(raw) is not bytes
        or type(stderr) is not bytes
        or stderr
        or not raw
        or len(raw) > MAX_GIT_CONFIG_BYTES
        or not raw.endswith(b"\0")
    ):
        raise ReportError("Git configuration audit is invalid")
    names = raw[:-1].split(b"\0")
    if (
        not names
        or len(names) > MAX_GIT_CONFIG_KEYS
        or any(not name or len(name) > 1024 for name in names)
    ):
        raise ReportError("Git configuration audit is invalid")
    for raw_name in names:
        try:
            name = raw_name.decode("ascii", "strict").lower()
        except UnicodeDecodeError as error:
            raise ReportError("Git configuration audit is invalid") from error
        if (
            any(ord(character) < 0x20 or ord(character) == 0x7F for character in name)
            or name
            in {
                "core.worktree",
                "core.attributesfile",
                "core.excludesfile",
                "extensions.worktreeconfig",
                "extensions.partialclone",
                "include.path",
            }
            or (name.startswith("includeif.") and name.endswith(".path"))
            or name.startswith("filter.")
            or re.fullmatch(r"remote\..+\.(?:promisor|partialclonefilter)", name)
            is not None
        ):
            raise ReportError("Git configuration contains an escape key")


def git_control_preflight(
    root: Path,
    *,
    git_executable: Path,
    git_environment: dict[str, str],
    runner: Callable[..., object] = _run_bounded_process,
) -> tuple[str, ...]:
    executable, environment = _validated_git_context(git_executable, git_environment)
    config = _validated_git_tree(root)
    try:
        result = runner(
            [
                executable,
                "--no-pager",
                "config",
                "--file",
                str(root / ".git/config"),
                "--no-includes",
                "--null",
                "--name-only",
                "--list",
            ],
            b"",
            dict(environment),
            timeout=GIT_TIMEOUT_SECONDS,
            output_limit=MAX_GIT_CONFIG_BYTES,
            cwd=root,
        )
    except (OSError, RegistryError, ValueError) as error:
        raise ReportError("Git configuration audit failed") from error
    if (
        type(result) is not tuple
        or len(result) != 2
        or type(result[0]) is not bytes
        or type(result[1]) is not bytes
    ):
        raise ReportError("Git configuration audit is invalid")
    _validate_git_config_names(result[0], result[1])
    if _validated_git_tree(root) != config:
        raise ReportError("Git configuration changed during its audit")
    return _git_command_prefix(root, executable)


def _bounded_git_output(
    root: Path,
    *,
    git_executable: Path,
    git_environment: dict[str, str],
) -> bytes:
    executable, environment = _validated_git_context(git_executable, git_environment)
    prefix = git_control_preflight(
        root,
        git_executable=git_executable,
        git_environment=git_environment,
    )
    process = subprocess.Popen(
        [
            *prefix,
            "ls-files",
            "--cached",
            "--full-name",
            "-z",
            "--",
        ],
        cwd=root,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=environment,
        shell=False,
        close_fds=True,
    )
    if process.stdout is None:
        process.kill()
        process.wait()
        raise ReportError("git ls-files stdout pipe was not created")
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + GIT_TIMEOUT_SECONDS
    output = bytearray()
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ReportError("git ls-files timed out")
            events = selector.select(remaining)
            if not events:
                if process.poll() is not None:
                    break
                raise ReportError("git ls-files timed out")
            chunk = os.read(process.stdout.fileno(), READ_CHUNK_BYTES)
            if not chunk:
                break
            output.extend(chunk)
            if len(output) > MAX_TRACKED_PATH_BYTES:
                raise ReportError("git ls-files output exceeds its byte cap")
        try:
            return_code = process.wait(timeout=max(1, int(deadline - time.monotonic())))
        except subprocess.TimeoutExpired as error:
            raise ReportError("git ls-files timed out") from error
    except BaseException:
        if process.poll() is None:
            process.kill()
        process.wait()
        raise
    finally:
        selector.close()
        process.stdout.close()
    if return_code != 0:
        detail = bytes(output[:4096]).decode("utf-8", "replace").strip()
        raise ReportError(f"git ls-files failed: {detail}")
    return bytes(output)


def _tracked_paths(
    root: Path,
    *,
    git_executable: Path,
    git_environment: dict[str, str],
) -> tuple[PurePosixPath, ...]:
    raw = _bounded_git_output(
        root,
        git_executable=git_executable,
        git_environment=git_environment,
    )
    if not raw or not raw.endswith(b"\0"):
        raise ReportError("git ls-files output lacks its terminal NUL")
    try:
        names = raw.decode("utf-8", "strict").split("\0")
    except UnicodeDecodeError as error:
        raise ReportError("tracked paths are not strict UTF-8") from error
    paths: list[PurePosixPath] = []
    if names[-1] or any(not name for name in names[:-1]):
        raise ReportError("git ls-files output contains an empty path frame")
    for name in names[:-1]:
        normalized = _safe_relative_path(name, "tracked path")
        paths.append(PurePosixPath(normalized))
        if len(paths) > MAX_TRACKED_PATHS:
            raise ReportError("tracked path count exceeds its M0 cap")
    ordered = tuple(sorted(paths, key=str))
    if len(ordered) != len(set(ordered)):
        raise ReportError("git ls-files returned duplicate paths")
    return ordered


def _native_inventory(
    root: Path,
    *,
    git_executable: Path,
    git_environment: dict[str, str],
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for relative in _tracked_paths(
        root,
        git_executable=git_executable,
        git_environment=git_environment,
    ):
        name = relative.as_posix()
        if name in NATIVE_EXCLUDED_PATHS or name.startswith("docs/superpowers/"):
            continue
        records.append({"path": name, "sha256": _sha256_below(root, relative)})
    return records


def _bounded_roadmap(roadmap: object) -> str:
    if type(roadmap) is not str:
        raise ReportError("roadmap must be text")
    if len(roadmap) > MAX_ROADMAP_CHARACTERS:
        raise ReportError("roadmap exceeds the 4 MiB character limit")
    return roadmap


def _roadmap_revision(roadmap: str) -> int:
    roadmap = _bounded_roadmap(roadmap)
    matches = re.findall(r"^\| Roadmap revision \| ([0-9]+) \|$", roadmap, re.MULTILINE)
    if matches != ["1"]:
        raise ReportError("roadmap must contain exactly revision 1")
    return 1


def parse_acceptance_matrix(roadmap: str) -> list[tuple[str, str, str]]:
    roadmap = _bounded_roadmap(roadmap)
    headings = tuple(
        re.finditer(
            rf"^{re.escape(ACCEPTANCE_HEADING)}$",
            roadmap,
            re.MULTILINE,
        )
    )
    if len(headings) != 1:
        raise ReportError(
            f"roadmap must contain exactly one heading: {ACCEPTANCE_HEADING}"
        )
    start = headings[0].start()
    terminator = re.search(r"^---$", roadmap[start:], re.MULTILINE)
    if terminator is None:
        raise ReportError("acceptance matrix lacks its section terminator")
    end = start + terminator.start()
    rows: list[tuple[str, str, str]] = []
    for line in roadmap[start:end].splitlines():
        if re.match(r"^\| G[0-9]+ \|", line) is None:
            continue
        parts = line.split("|")
        if len(parts) != 6 or parts[0] or parts[-1]:
            raise ReportError(f"malformed acceptance row: {line}")
        gate_id, acceptance, owner, required_evidence = (
            part.strip() for part in parts[1:5]
        )
        if not acceptance or not owner or not required_evidence:
            raise ReportError(f"incomplete acceptance row: {line}")
        rows.append((gate_id, acceptance, owner))
    if tuple(row[0] for row in rows) != EXPECTED_GATE_IDS:
        raise ReportError(
            "acceptance matrix must contain exactly G1 through G18 in order"
        )
    return rows


def _native_shape(evidence: object) -> dict[str, object]:
    value = _exact_dict(
        evidence,
        {
            "schema_version",
            "protocol",
            "result",
            "roadmap_revision",
            "tool_versions",
            "isolation",
            "commands",
            "source_report_sha256",
            "inputs",
        },
        "native evidence",
    )
    _exact_int(value["schema_version"], 0, "native evidence schema_version")
    _exact_int(value["roadmap_revision"], 1, "native evidence roadmap_revision")
    if value["protocol"] != "native-isolated-v0":
        raise ReportError("native evidence protocol must be native-isolated-v0")
    if value["result"] != "pass":
        raise ReportError("native evidence result must be pass")

    tools = _exact_dict(
        value["tool_versions"], set(NATIVE_TOOL_KEYS), "native evidence tool_versions"
    )
    if any(type(tools[key]) is not str or not tools[key] for key in NATIVE_TOOL_KEYS):
        raise ReportError("native evidence tool versions must be nonempty strings")
    if value["isolation"] != EXPECTED_NATIVE_ISOLATION:
        raise ReportError(
            "native evidence isolation projection differs from native-isolated-v0"
        )
    if value["commands"] != EXPECTED_NATIVE_COMMANDS:
        raise ReportError("native evidence commands differ from native-isolated-v0")
    for index, command in enumerate(cast(list[dict[str, object]], value["commands"])):
        _exact_int(command["exit_code"], 0, f"native command[{index}] exit_code")
    digest = value["source_report_sha256"]
    if type(digest) is not str or LOWER_SHA256.fullmatch(digest) is None:
        raise ReportError("native source report identity must be lowercase SHA-256")
    inputs = _identity_records(value["inputs"], "native evidence inputs")
    if any(
        item["path"] in NATIVE_EXCLUDED_PATHS
        or item["path"].startswith("docs/superpowers/")
        for item in inputs
    ):
        raise ReportError("native evidence contains an excluded cyclic path")
    return value


def validate_native_evidence(
    root: Path,
    evidence: object,
    *,
    git_executable: Path,
    git_environment: dict[str, str],
) -> dict[str, object]:
    value = _native_shape(evidence)
    roadmap_text = _read_utf8_below(
        root, PurePosixPath("docs/roadmap.md"), MAX_ROADMAP_BYTES
    )
    if value["roadmap_revision"] != _roadmap_revision(roadmap_text):
        raise ReportError("native evidence roadmap revision is stale")

    lock = load_source_lock(root)
    expected_tools = {
        "cargo": lock.toolchains.cargo,
        "cc": lock.toolchains.cc,
        "git": lock.toolchains.git,
        "ld": lock.toolchains.ld,
        "python": lock.toolchains.python,
        "rust": lock.toolchains.rust,
        "sdk": lock.toolchains.sdk,
        "uv": lock.toolchains.uv,
    }
    if value["tool_versions"] != expected_tools:
        raise ReportError("native evidence tool versions do not match the source lock")
    tracked_source_raw = _read_below(
        root, PurePosixPath("reports/source-doctor.json"), MAX_REPORT_BYTES
    )
    expected_source_digest = hashlib.sha256(tracked_source_raw).hexdigest()
    if value["source_report_sha256"] != expected_source_digest:
        raise ReportError("native evidence source report identity is stale")
    try:
        tracked_source = decode_canonical_manifest(tracked_source_raw)
    except ValueError as error:
        raise ReportError("tracked source report is not canonical") from error
    if type(tracked_source) is not dict:
        raise ReportError("tracked source report must be an object")
    preflight, _, _ = _source_report_facts(
        root, cast(dict[str, object], tracked_source)
    )
    if not preflight:
        raise ReportError("native evidence requires passing source preflight")

    expected_inventory = _native_inventory(
        root,
        git_executable=git_executable,
        git_environment=git_environment,
    )
    if value["inputs"] != expected_inventory:
        raise ReportError("native evidence tracked-product inventory is stale")
    anthology_path = lock.anthology.path.as_posix()
    anthology_record = next(
        (record for record in expected_inventory if record["path"] == anthology_path),
        None,
    )
    if anthology_record != {
        "path": anthology_path,
        "sha256": lock.anthology.sha256,
    }:
        raise ReportError(
            "native evidence anthology identity differs from source evidence"
        )

    cloned = decode_canonical_manifest(encode_canonical_value(value))
    return cast(dict[str, object], cloned)


def _source_report_facts(
    root: Path, source_report: dict[str, object]
) -> tuple[bool, str, str]:
    tracked_raw = _read_below(
        root, PurePosixPath("reports/source-doctor.json"), MAX_REPORT_BYTES
    )
    if encode_canonical_value(source_report) != tracked_raw:
        raise ReportError("source report value differs from tracked canonical bytes")
    _exact_int(
        source_report.get("schema_version"),
        0,
        "source report schema_version",
    )
    preflight = source_report.get("g1_preflight")
    if type(preflight) is not bool:
        raise ReportError("source report g1_preflight must be Boolean")
    fence_count = source_report.get("fence_count")
    if type(fence_count) is not int or fence_count < 0:
        raise ReportError("source report fence_count must be a nonnegative integer")
    if preflight and fence_count != 64:
        raise ReportError("passing source preflight must report exactly 64 fences")

    module_digest = source_report.get("raw_module_sha256")
    if type(module_digest) is not str or LOWER_SHA256.fullmatch(module_digest) is None:
        raise ReportError("source report raw_module_sha256 is malformed")
    if module_digest != _sha256_below(
        root, PurePosixPath("python/golden_board/source_doctor.py")
    ):
        raise ReportError("source report module identity is stale")

    source = source_report.get("source")
    if type(source) is not dict:
        raise ReportError("source report source must be an object")
    lock = load_source_lock(root)
    expected_source = {
        "path": lock.anthology.path.as_posix(),
        "byte_length": lock.anthology.byte_length,
        "sha256": lock.anthology.sha256,
    }
    for key, expected in expected_source.items():
        if source.get(key) != expected:
            raise ReportError(f"source report source.{key} differs from source lock")
    return preflight, module_digest, hashlib.sha256(tracked_raw).hexdigest()


def build_release_summary(
    root: Path,
    source_report: dict[str, object],
    native_evidence: dict[str, object] | None = None,
    *,
    git_executable: Path | None = None,
    git_environment: dict[str, str] | None = None,
) -> dict[str, object]:
    roadmap_text = _read_utf8_below(
        root, PurePosixPath("docs/roadmap.md"), MAX_ROADMAP_BYTES
    )
    revision = _roadmap_revision(roadmap_text)
    matrix = parse_acceptance_matrix(roadmap_text)
    preflight, module_digest, source_report_digest = _source_report_facts(
        root, source_report
    )
    lock = load_source_lock(root)

    validated_native: dict[str, object] | None = None
    if native_evidence is not None:
        if not preflight:
            raise ReportError("native evidence cannot override failed source preflight")
        if git_executable is None or git_environment is None:
            raise ReportError("native evidence validation requires sealed Git context")
        validated_native = validate_native_evidence(
            root,
            native_evidence,
            git_executable=git_executable,
            git_environment=git_environment,
        )

    generation_inputs = [
        {"path": lock.anthology.path.as_posix(), "sha256": lock.anthology.sha256},
        {
            "path": "inputs/source-lock.toml",
            "sha256": _sha256_below(root, PurePosixPath("inputs/source-lock.toml")),
        },
        {
            "path": "python/golden_board/source_doctor.py",
            "sha256": module_digest,
        },
    ]
    generation_inputs.sort(key=lambda item: item["path"])

    g1_evidence = [
        {
            "kind": "anthology_raw_sha256",
            "path": lock.anthology.path.as_posix(),
            "sha256": lock.anthology.sha256,
        },
        {
            "kind": "source_doctor_report_raw_sha256",
            "path": "reports/source-doctor.json",
            "sha256": source_report_digest,
        },
    ]
    gate_id, acceptance, owner = matrix[0]
    g1: dict[str, object] = {
        "id": gate_id,
        "acceptance": acceptance,
        "owner_milestone": owner,
        "result": (
            "pass"
            if preflight and validated_native is not None
            else "pending_m0_verification"
        ),
        "protocol": G1_PROTOCOL,
        "evidence": g1_evidence,
        "limitations": [
            (
                "M0 verifies repository/source identity with package-manager offline modes; OS-level network denial and chess semantics remain later-owned."
                if preflight and validated_native is not None
                else "G1 remains open until source preflight and native-isolated-v0 both pass."
            )
        ],
    }
    if validated_native is not None:
        g1["native_verification"] = validated_native

    gates: list[dict[str, object]] = [g1]
    for gate_id, acceptance, owner in matrix[1:]:
        gates.append(
            {
                "id": gate_id,
                "acceptance": acceptance,
                "owner_milestone": owner,
                "result": "pending_owner_milestone",
                "limitations": [
                    f"Owned by {owner}; M0 supplies no candidate evidence."
                ],
            }
        )
    return {
        "schema_version": 0,
        "roadmap_revision": revision,
        "generation_inputs": generation_inputs,
        "gates": gates,
    }


def _release_shape(value: object, roadmap: str) -> dict[str, object]:
    report = _exact_dict(
        value,
        {"schema_version", "roadmap_revision", "generation_inputs", "gates"},
        "release summary top-level",
    )
    _exact_int(report["schema_version"], 0, "release summary schema_version")
    _exact_int(
        report["roadmap_revision"],
        _roadmap_revision(roadmap),
        "release summary roadmap_revision",
    )
    inputs = _identity_records(report["generation_inputs"], "generation_inputs")
    if tuple(item["path"] for item in inputs) != EXPECTED_GENERATION_INPUT_PATHS:
        raise ReportError(
            "generation_inputs must contain the exact ordered M0 identity graph"
        )

    gates_value = report["gates"]
    if type(gates_value) is not list:
        raise ReportError("release summary gates must be an array")
    gates = cast(list[object], gates_value)
    matrix = parse_acceptance_matrix(roadmap)
    if len(gates) != len(matrix):
        raise ReportError("release summary must contain exactly 18 gates")

    for index, ((expected_id, acceptance, owner), gate_value) in enumerate(
        zip(matrix, gates, strict=True)
    ):
        label = expected_id
        if index == 0:
            if type(gate_value) is not dict:
                raise ReportError("G1 must be an object")
            gate_keys = set(cast(dict[str, object], gate_value))
            pending_keys = {
                "id",
                "acceptance",
                "owner_milestone",
                "result",
                "protocol",
                "evidence",
                "limitations",
            }
            pass_keys = pending_keys | {"native_verification"}
            if gate_keys not in (pending_keys, pass_keys):
                raise ReportError(f"G1 keys are invalid: {sorted(gate_keys)}")
            gate = cast(dict[str, object], gate_value)
        else:
            gate = _exact_dict(
                gate_value,
                {
                    "id",
                    "acceptance",
                    "owner_milestone",
                    "result",
                    "limitations",
                },
                label,
            )
        if gate["id"] != expected_id:
            raise ReportError(f"{label} id or order drifted")
        if gate["acceptance"] != acceptance:
            raise ReportError(f"{label} acceptance wording drifted")
        if gate["owner_milestone"] != owner:
            raise ReportError(f"{label} owner milestone drifted")

        if index == 0:
            if gate["protocol"] != G1_PROTOCOL:
                raise ReportError("G1 protocol drifted")
            evidence = gate["evidence"]
            if type(evidence) is not list or len(evidence) != 2:
                raise ReportError(
                    "G1 must contain exactly two source evidence identities"
                )
            for evidence_index, item in enumerate(cast(list[object], evidence)):
                record = _exact_dict(
                    item,
                    {"kind", "path", "sha256"},
                    f"G1 evidence[{evidence_index}]",
                )
                path = _safe_relative_path(record["path"], "G1 evidence path")
                expected_kind, expected_path = EXPECTED_G1_EVIDENCE[evidence_index]
                if record["kind"] != expected_kind or path != expected_path:
                    raise ReportError(
                        f"G1 evidence[{evidence_index}] kind/path differs from the M0 identity graph"
                    )
                digest = record["sha256"]
                if type(digest) is not str or LOWER_SHA256.fullmatch(digest) is None:
                    raise ReportError("G1 evidence digest must be lowercase SHA-256")
            if gate["result"] == "pending_m0_verification":
                if "native_verification" in gate:
                    raise ReportError("pending G1 cannot carry native verification")
                expected_limitations = [
                    "G1 remains open until source preflight and native-isolated-v0 both pass."
                ]
            elif gate["result"] == "pass":
                if "native_verification" not in gate:
                    raise ReportError("passing G1 lacks native verification")
                _native_shape(gate["native_verification"])
                expected_limitations = [
                    "M0 verifies repository/source identity with package-manager offline modes; OS-level network denial and chess semantics remain later-owned."
                ]
            else:
                raise ReportError("G1 result is invalid")
            if gate["limitations"] != expected_limitations:
                raise ReportError("G1 limitations drifted")
        else:
            if gate["result"] != "pending_owner_milestone":
                raise ReportError(f"{label} must remain pending_owner_milestone at M0")
            expected_limitations = [
                f"Owned by {owner}; M0 supplies no candidate evidence."
            ]
            if gate["limitations"] != expected_limitations:
                raise ReportError(f"{label} limitations drifted")
    return report


def validate_release_summary(value: object, roadmap: str) -> list[str]:
    try:
        _release_shape(value, roadmap)
    except ReportError as error:
        return [str(error)]
    return []


def native_evidence_from_summary(value: object) -> dict[str, object] | None:
    if type(value) is not dict:
        raise ReportError("release summary must be an object")
    gates = cast(dict[str, object], value).get("gates")
    if type(gates) is not list or not gates or type(gates[0]) is not dict:
        raise ReportError("release summary lacks G1")
    g1 = cast(dict[str, object], gates[0])
    if g1.get("result") == "pending_m0_verification":
        return None
    if g1.get("result") != "pass" or "native_verification" not in g1:
        raise ReportError("release summary G1 result/native evidence disagree")
    native = _native_shape(g1["native_verification"])
    return cast(
        dict[str, object],
        decode_canonical_manifest(encode_canonical_value(native)),
    )


def check_report_schemas(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        source = decode_canonical_manifest(
            _read_below(
                root,
                PurePosixPath("reports/source-doctor.json"),
                MAX_REPORT_BYTES,
            )
        )
        if type(source) is not dict:
            raise ReportError("source report must be an object")
        _source_report_facts(root, source)
        release = decode_canonical_manifest(
            _read_below(
                root,
                PurePosixPath("reports/release-summary.json"),
                MAX_REPORT_BYTES,
            )
        )
        roadmap = _read_utf8_below(
            root,
            PurePosixPath("docs/roadmap.md"),
            MAX_ROADMAP_BYTES,
        )
        errors.extend(validate_release_summary(release, roadmap))
    except (OSError, UnicodeError, ValueError) as error:
        errors.append(f"tracked report schema check failed: {error}")
    return errors


def check_tracked_reports(
    root: Path,
    *,
    git_executable: Path | None = None,
    git_environment: dict[str, str] | None = None,
) -> list[str]:
    errors: list[str] = []
    try:
        lock = load_source_lock(root)
        expected_source = build_source_report(root, lock)
        tracked_source_raw = _read_below(
            root, PurePosixPath("reports/source-doctor.json"), MAX_REPORT_BYTES
        )
        if encode_canonical_value(expected_source) != tracked_source_raw:
            errors.append("reports/source-doctor.json is stale")

        tracked_release_raw = _read_below(
            root, PurePosixPath("reports/release-summary.json"), MAX_REPORT_BYTES
        )
        tracked_release = decode_canonical_manifest(tracked_release_raw)
        roadmap = _read_utf8_below(
            root, PurePosixPath("docs/roadmap.md"), MAX_ROADMAP_BYTES
        )
        errors.extend(validate_release_summary(tracked_release, roadmap))
        if errors:
            return errors

        native = native_evidence_from_summary(tracked_release)
        def pending_projection() -> tuple[dict[str, object], bytes]:
            expected_release = build_release_summary(root, expected_source)
            expected_gates = cast(list[object], expected_release["gates"])
            expected_first_gate = cast(dict[str, object], expected_gates[0])
            tracked_without_native = [
                dict(gate) for gate in cast(list[object], tracked_release["gates"])
            ]
            if len(tracked_without_native) > 0:
                tracked_gate_zero = dict(cast(dict[str, object], tracked_without_native[0]))
                tracked_gate_zero.pop("native_verification", None)
                tracked_gate_zero["result"] = expected_first_gate["result"]
                tracked_gate_zero["limitations"] = expected_first_gate["limitations"]
                tracked_without_native[0] = tracked_gate_zero
            projected = dict(tracked_release)
            projected["gates"] = tracked_without_native
            return expected_release, encode_canonical_value(projected)

        projected_raw = tracked_release_raw
        if native is not None and (
            git_executable is None or git_environment is None
        ):
            expected_release, projected_raw = pending_projection()
        else:
            try:
                expected_release = build_release_summary(
                    root,
                    expected_source,
                    native,
                    git_executable=git_executable,
                    git_environment=git_environment,
                )
            except ReportError as error:
                if str(error) != "native evidence tracked-product inventory is stale":
                    raise
                expected_release, projected_raw = pending_projection()
        if encode_canonical_value(expected_release) != projected_raw:
            errors.append("reports/release-summary.json is stale")
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError) as error:
        errors.append(f"tracked report check failed: {error}")
    return errors
