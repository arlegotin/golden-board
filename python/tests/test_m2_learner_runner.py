"""Focused equivalence, firewall, and CLI checks for the standalone learner runner."""

from __future__ import annotations

import ast
from dataclasses import is_dataclass
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from golden_board import m2_runner
from golden_board import m2_slice


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "tools/m2/learner_runner.py"
COMMAND_SCHEMA = "golden-board.learner-runner-commands/v0"


def _read(relative: str) -> bytes:
    return (ROOT / relative).read_bytes()


SLICE_INPUTS = (
    _read("studies/m2/slice-v0.json"),
    _read("conformance/content-v0.json"),
    _read("conformance/chess-v0.json"),
    _read("reports/game-set-v0.bin"),
    _read("spec/content-v0.md"),
    _read("spec/constants-v0.toml"),
    _read("spec/curriculum-v0.toml"),
)


def _all_stream() -> bytes:
    return m2_slice.compile_slice_v0(*SLICE_INPUTS).content_bytes


def _load_standalone():
    spec = importlib.util.spec_from_file_location("m2_standalone_learner_runner", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("standalone learner runner cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _text(value: bytes | None) -> str | None:
    return None if value is None else value.decode("utf-8")


def _atom_schema(value) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "allowed_mask": value.allowed_mask,
        "atom_class": value.atom_class,
        "atom_width": value.atom_width,
        "entries": [
            {"label": _text(entry.label), "value": entry.value}
            for entry in value.entries
        ],
        "max_value": value.max_value,
        "min_value": value.min_value,
    }


def _display_record(value) -> dict[str, object]:
    return {
        "atom_schema": _atom_schema(value.atom_schema),
        "atoms": list(value.atoms),
        "columns": value.columns,
        "fields": [
            {
                "atoms": list(field.atoms),
                "count": field.count,
                "name": _text(field.name),
                "record_refs": list(field.record_refs),
                "storage": field.storage,
                "type_code": field.type_code,
            }
            for field in value.fields
        ],
        "kind": value.kind,
        "opaque_data": list(value.opaque_data),
        "record_id": value.record_id,
        "rows": value.rows,
        "text": _text(value.text),
    }


def _graph(value) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "records": [_display_record(record) for record in value.records],
        "root_record_id": value.root_record_id,
    }


def _region(value) -> dict[str, object]:
    return {
        "column_end": value.column_end,
        "column_start": value.column_start,
        "flags": value.flags,
        "label": _text(value.label),
        "region_id": value.region_id,
        "row_end": value.row_end,
        "row_start": value.row_start,
    }


def _passive(value) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "actions_hex": [action.hex() for action in value.actions],
        "limitation": _text(value.limitation),
        "presentation": _graph(value.presentation),
        "regions": [_region(region) for region in value.regions],
        "resulting_presentation": _graph(value.resulting_presentation),
    }


def _generic_frame(value) -> dict[str, object]:
    return {
        "available_actions_hex": [action.hex() for action in value.available_actions],
        "can_advance": value.can_advance,
        "committed_response_hex": value.committed_response.hex(),
        "current_node_id": value.current_node_id,
        "events": [
            {"action_hex": event.action.hex(), "node_id": event.node_id, "result": event.result}
            for event in value.events
        ],
        "feedback": _graph(value.feedback),
        "feedback_ref": value.feedback_ref,
        "global_remaining": value.global_remaining,
        "local_remaining": value.local_remaining,
        "next_node_ref": value.next_node_ref,
        "outcome": value.outcome,
        "passive": _passive(value.passive),
        "phase": value.phase,
        "presentation": _graph(value.presentation),
        "regions": [_region(region) for region in value.regions],
        "selection_buffer": list(value.selection_buffer),
    }


def _commands_bytes() -> bytes:
    commands = []
    for group_index, group in enumerate(m2_runner.M2_SEMANTIC_ACTION_GROUPS):
        if group_index:
            commands.append({"advance": True})
        commands.extend({"action_hex": action.hex()} for action in group)
    return (
        json.dumps(
            {"commands": commands, "schema": COMMAND_SCHEMA},
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


class StandaloneLearnerRunner(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.stream = _all_stream()
        cls.standalone = _load_standalone()

    def test_participant_frames_match_generic_runner_on_semantic_path(self) -> None:
        for suppressed in (False, True):
            with self.subTest(label_suppressed=suppressed):
                generic = m2_runner.m2_runner(self.stream, label_suppressed=suppressed)
                standalone = self.standalone.StandaloneRunner(
                    self.stream,
                    label_suppressed=suppressed,
                )
                self.assertEqual(standalone.frame(), _generic_frame(generic.frame()))
                for group_index, group in enumerate(m2_runner.M2_SEMANTIC_ACTION_GROUPS):
                    if group_index:
                        standalone.advance()
                        generic.advance()
                        self.assertEqual(standalone.frame(), _generic_frame(generic.frame()))
                    for action in group:
                        self.assertEqual(standalone.perform(action), generic.perform(action))
                        self.assertEqual(standalone.frame(), _generic_frame(generic.frame()))

    def test_source_and_transcript_keep_the_dependency_and_evaluator_firewalls(self) -> None:
        raw = RUNNER_PATH.read_bytes()
        source = raw.decode("utf-8")
        tree = ast.parse(source)
        allowed = {
            "__future__",
            "argparse",
            "bisect",
            "dataclasses",
            "hashlib",
            "json",
            "os",
            "stat",
            "sys",
            "typing",
        }
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0)
                self.assertIsNotNone(node.module)
                imported.add(node.module.split(".", 1)[0])
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, {"eval", "exec", "__import__"})
        self.assertTrue(imported.issubset(allowed), imported - allowed)
        self.assertNotIn("golden_board", source)
        self.assertNotIn(str(ROOT), source)
        self.assertFalse(is_dataclass(self.standalone.StandaloneRunner))
        self.assertTrue(os.access(RUNNER_PATH, os.X_OK))
        self.assertEqual(RUNNER_PATH.stat().st_mode & 0o777, 0o755)

        transcript = self.standalone.run_commands(
            self.stream,
            _commands_bytes(),
            label_suppressed=True,
        )
        self.assertNotIn(b"predicate", transcript)
        self.assertNotIn(b"expected", transcript)
        value = json.loads(transcript)
        generic = m2_runner.m2_runner(self.stream, label_suppressed=True)
        for group_index, group in enumerate(m2_runner.M2_SEMANTIC_ACTION_GROUPS):
            if group_index:
                generic.advance()
            for action in group:
                generic.perform(action)
        self.assertEqual(value["frames"][-1], _generic_frame(generic.frame()))
        self.assertEqual(value["frames"][-1]["committed_response_hex"], "03000200030001")

    def test_cli_runs_in_isolated_stdlib_only_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = root / "learner_runner.py"
            stream = root / "m2-all.content-v0.bin"
            commands = root / "commands.json"
            shutil.copyfile(RUNNER_PATH, runner)
            runner.chmod(0o755)
            stream.write_bytes(self.stream)
            commands.write_bytes(_commands_bytes())
            completed = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(runner),
                    "--content-stream",
                    str(stream),
                    "--commands",
                    str(commands),
                    "--label-suppressed",
                ],
                cwd=root,
                env={"PATH": os.environ.get("PATH", "")},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stderr, b"")
            value = json.loads(completed.stdout)
            self.assertEqual(value["schema"], "golden-board.learner-runner-transcript/v0")
            self.assertEqual(value["content_stream_sha256"], m2_runner.M2_ALL_CONTENT_SHA256)
            self.assertEqual(value["frames"][-1]["committed_response_hex"], "03000200030001")
            self.assertEqual(len(value["frames"]), 14)

    def test_cli_and_library_reject_wrong_identity_links_and_bad_commands(self) -> None:
        with self.assertRaisesRegex(self.standalone.RunnerError, "content_stream_identity"):
            self.standalone.StandaloneRunner(self.stream[:-1] + b"X", label_suppressed=True)
        with self.assertRaisesRegex(self.standalone.RunnerError, "commands"):
            self.standalone.run_commands(
                self.stream,
                b'{"commands":[{"action_hex":"0100000A"}],"schema":"golden-board.learner-runner-commands/v0"}\n',
                label_suppressed=True,
            )
        with self.assertRaisesRegex(self.standalone.RunnerError, "commands"):
            self.standalone.run_commands(
                self.stream,
                b'{"commands":[],"commands":[],"schema":"golden-board.learner-runner-commands/v0"}\n',
                label_suppressed=True,
            )
        oversized_commands = (
            json.dumps(
                {
                    "commands": [{"advance": True}] * 257,
                    "schema": COMMAND_SCHEMA,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode()
        with self.assertRaisesRegex(self.standalone.RunnerError, "commands"):
            self.standalone.run_commands(
                self.stream,
                oversized_commands,
                label_suppressed=True,
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stream = root / "stream.bin"
            commands = root / "commands.json"
            stream.write_bytes(self.stream)
            commands.write_bytes(_commands_bytes())
            link = root / "commands-link.json"
            link.symlink_to(commands.name)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER_PATH),
                    "--content-stream",
                    str(stream),
                    "--commands",
                    str(link),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(completed.returncode, 3)
            self.assertEqual(completed.stdout, b"")
            self.assertLessEqual(len(completed.stderr), 16_384)


if __name__ == "__main__":
    unittest.main()
