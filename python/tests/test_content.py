"""Independent Python evidence for the generic content-v0 runtime."""

from __future__ import annotations

import importlib
import hashlib
import ast
from dataclasses import FrozenInstanceError
import sys
import types
from pathlib import Path
import unittest

from golden_board import canonical_manifest
from golden_board import constants as C
from python.tests.test_foundation import (
    _content_recipe_bytes,
    repo_text_bytes,
    validate_content_fixture_contract,
)


ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_RAW = repo_text_bytes(ROOT, b"conformance/content-v0.json")
FIXTURE = canonical_manifest.validate_canonical_manifest(_FIXTURE_RAW)
validate_content_fixture_contract(FIXTURE)


_KIND_NAMES = {
    value: name.removeprefix("CONTENT_KIND_")
    for name, value in vars(C).items()
    if name.startswith("CONTENT_KIND_")
}


def _projection_value(content: object, projection: object) -> dict[str, object]:
    by_id = {record.record_id: record for record in projection.records}
    records = []
    for record in projection.records:
        value = {
            "kind": _KIND_NAMES[record.kind],
            "record_id": record.record_id,
        }
        if isinstance(record, content._Text):
            value["text"] = record.text
        elif isinstance(record, content._AtomSchema):
            value.update(
                atom_class=record.atom_class,
                atom_width=record.atom_width,
                entry_count=record.entry_count,
            )
            if record.atom_class == C.ATOM_UNSIGNED:
                value.update(min_value=record.min_value, max_value=record.max_value)
            else:
                value["entries"] = [
                    (
                        {"code": entry.value, "label_text_ref": entry.label_text_ref}
                        if record.atom_class == C.ATOM_ENUM
                        else {
                            "one_hot_bit": entry.value,
                            "label_text_ref": entry.label_text_ref,
                        }
                    )
                    for entry in record.entries
                ]
                if record.atom_class == C.ATOM_MASK:
                    value["allowed_mask"] = record.allowed_mask
        elif isinstance(record, content._AtomVector):
            value.update(
                atom_schema_ref=record.atom_schema_ref,
                atom_count=record.atom_count,
                atoms=list(record.atoms),
            )
        elif isinstance(record, content._Matrix):
            value.update(
                atom_schema_ref=record.atom_schema_ref,
                rows=record.rows,
                columns=record.columns,
                cells=list(record.cells),
            )
        elif isinstance(record, content._FieldSchema):
            value.update(
                field_count=record.field_count,
                fields=[
                    {
                        "name_text_ref": item.name_text_ref,
                        "storage": item.storage,
                        "type": item.type,
                        "count": item.count,
                    }
                    for item in record.fields
                ],
            )
        elif isinstance(record, content._Tuple):
            schema = by_id[record.field_schema_ref]
            value.update(
                field_schema_ref=record.field_schema_ref,
                field_values=[
                    {
                        "atoms" if definition.storage == C.FIELD_INLINE_ATOM else "record_refs":
                        list(values)
                    }
                    for definition, values in zip(
                        schema.fields, record.field_values, strict=True
                    )
                ],
            )
        elif isinstance(record, content._RegionSet):
            value.update(
                surface_matrix_ref=record.surface_matrix_ref,
                region_count=record.region_count,
                regions=[
                    {
                        "region_id": item.region_id,
                        "label_ref": item.label_ref,
                        "row_start": item.row_start,
                        "row_end": item.row_end,
                        "column_start": item.column_start,
                        "column_end": item.column_end,
                        "flags": item.flags,
                    }
                    for item in record.regions
                ],
            )
        elif isinstance(record, content._Binding):
            value.update(
                binding_class=record.binding_class,
                namespace_id=record.namespace_id,
                semantic_code=record.semantic_code,
                argument=record.argument,
                auxiliary=record.auxiliary,
            )
        elif isinstance(record, content._Opaque):
            value.update(data_binding_ref=record.data_binding_ref, data=list(record.data))
        elif isinstance(record, content._Predicate):
            value.update(
                predicate_binding_ref=record.predicate_binding_ref,
                subject_opaque_data_ref=record.subject_opaque_data_ref,
                result_atom_vector_ref=record.result_atom_vector_ref,
            )
        elif isinstance(record, content._Feedback):
            value.update(
                feedback_code=record.feedback_code,
                display_ref=record.display_ref,
                predicate_result_ref=record.predicate_result_ref,
            )
        elif isinstance(record, content._Passive):
            value.update(
                presentation_ref=record.presentation_ref,
                region_set_ref=record.region_set_ref,
                resulting_presentation_ref=record.resulting_presentation_ref,
                limitation_text_ref=record.limitation_text_ref,
                action_count=record.action_count,
                actions=[action.hex() for action in record.actions],
                expected_outcome=record.expected_outcome,
                expected_feedback_ref=record.expected_feedback_ref,
                expected_next_node_ref=record.expected_next_node_ref,
            )
        elif isinstance(record, content._Lesson):
            value.update(
                role=record.role,
                response_shape=record.response_shape,
                answer_mode=record.answer_mode,
                flags=record.flags,
                presentation_ref=record.presentation_ref,
                region_set_ref=record.region_set_ref,
                predicate_result_ref=record.predicate_result_ref,
                passive_trace_ref=record.passive_trace_ref,
                max_selections=record.max_selections,
                item_event_budget=record.item_event_budget,
                case_count=len(record.cases),
                cases=[
                    {
                        "case_class": item.case_class,
                        "selection_count": len(item.region_ids),
                        "region_ids": list(item.region_ids),
                        "feedback_ref": item.feedback_ref,
                        "next_node_ref": item.next_node_ref,
                    }
                    for item in record.cases
                ],
                default_feedback_ref=record.default_feedback_ref,
                default_next_node_ref=record.default_next_node_ref,
            )
        elif isinstance(record, content._Root):
            value.update(
                entry_node_ref=record.entry_node_ref,
                global_event_budget=record.global_event_budget,
            )
        else:
            raise AssertionError("unknown private projected record")
        records.append(value)
    return {
        "version": projection.version,
        "root_record_id": projection.root_record_id,
        "records": records,
    }


class ContentApi(unittest.TestCase):
    def test_exact_public_surface_is_present(self) -> None:
        content = importlib.import_module("golden_board.content")
        expected = {
            "ContentReject",
            "InvalidHostState",
            "stream_validation",
            "new_run",
            "step",
            "advance_committed",
            "encode_run_state",
            "validate_run_state",
        }
        self.assertEqual(set(content.__all__), expected)
        self.assertEqual(len(content.__all__), len(expected))
        self.assertTrue(all(callable(getattr(content, name)) for name in expected))

    def test_projection_is_exact_and_authority_values_are_immutable(self) -> None:
        content = importlib.import_module("golden_board.content")
        base = FIXTURE["bases"][0]
        projection = content.stream_validation(bytes.fromhex(base["stream_hex"]))
        self.assertEqual(_projection_value(content, projection), base["projection"])
        state = content.new_run(projection)
        with self.assertRaises(FrozenInstanceError):
            projection.version = 1
        with self.assertRaises(FrozenInstanceError):
            state.phase = C.PHASE_EXHAUSTED
        with self.assertRaises(TypeError):
            content._ContentProjection()
        with self.assertRaises(TypeError):
            content._RunState()
        with self.assertRaises(TypeError):
            content.stream_validation(bytearray())
        with self.assertRaises(TypeError):
            content.step(projection, state, bytearray(b"\0" * 4))

    def test_stream_framing_rejections_are_exact(self) -> None:
        content = importlib.import_module("golden_board.content")
        names = {
            "stream-empty-truncated",
            "stream-partial-header-truncated",
            "stream-bad-version",
            "stream-bad-record-count-zero",
            "stream-truncated-record-header",
            "stream-truncated-final-payload",
            "stream-trailing-data",
        }
        cases = {case["name"]: case for case in FIXTURE["cases"]}
        for name in names:
            case = cases[name]
            expected = case["expected"]["rejection"]
            with self.subTest(name=name):
                with self.assertRaises(content.ContentReject) as caught:
                    content.stream_validation(bytes.fromhex(case["input"]["stream_hex"]))
                self.assertEqual(
                    (caught.exception.code, caught.exception.raw_start, caught.exception.raw_end),
                    (expected["code"], expected["raw_start"], expected["raw_end"]),
                )

    def test_every_stream_validation_row(self) -> None:
        content = importlib.import_module("golden_board.content")
        rows = [
            row
            for group in (FIXTURE["cases"], FIXTURE["recipes"])
            for row in group
            if row["operation"] == "stream_validation"
        ]
        self.assertEqual(len(rows), 177)
        for row in rows:
            raw = (
                bytes.fromhex(row["input"]["stream_hex"])
                if "recipe" not in row
                else _content_recipe_bytes(FIXTURE, row)
            )
            with self.subTest(name=row["name"]):
                try:
                    projection = content.stream_validation(raw)
                except content.ContentReject as error:
                    self.assertEqual(
                        row["expected"],
                        {
                            "rejection": {
                                "code": error.code,
                                "raw_end": error.raw_end,
                                "raw_start": error.raw_start,
                            }
                        },
                    )
                else:
                    self.assertIn("success", row["expected"])
                    self.assertEqual(projection.version, 0)
                    self.assertGreaterEqual(len(projection.records), 2)

    def test_every_direct_runtime_row(self) -> None:
        content = importlib.import_module("golden_board.content")
        rows = [row for row in FIXTURE["cases"] if row["operation"] != "stream_validation"]
        self.assertEqual(len(rows), 46)
        for row in rows:
            data = row["input"]
            projection = content.stream_validation(bytes.fromhex(data["stream_hex"]))
            with self.subTest(name=row["name"]):
                if row["operation"] == "new_run":
                    state = content.new_run(projection)
                    self.assertEqual(
                        row["expected"],
                        {"success": {"state_hex": content.encode_run_state(state).hex()}},
                    )
                    continue
                state_bytes = bytes.fromhex(data["state_hex"])
                if row["operation"] == "validate_run_state":
                    try:
                        state = content.validate_run_state(projection, state_bytes)
                    except content.ContentReject as error:
                        actual = {
                            "rejection": {
                                "code": error.code,
                                "raw_end": error.raw_end,
                                "raw_start": error.raw_start,
                            }
                        }
                    else:
                        actual = {"success": {"state_hex": content.encode_run_state(state).hex()}}
                    self.assertEqual(row["expected"], actual)
                    continue
                state = content.validate_run_state(projection, state_bytes)
                before = content.encode_run_state(state)
                self.assertEqual(before, state_bytes)
                if row["operation"] == "advance_committed":
                    try:
                        after = content.advance_committed(projection, state)
                    except content.InvalidHostState:
                        actual = {"invalid_host_state": {}}
                        self.assertEqual(content.encode_run_state(state), before)
                    else:
                        actual = {"success": {"state_hex": content.encode_run_state(after).hex()}}
                else:
                    after, result = content.step(
                        projection, state, bytes.fromhex(data["action_hex"])
                    )
                    success = {
                        "interaction_result": result,
                        "state_hex": content.encode_run_state(after).hex(),
                    }
                    expected_success = row["expected"]["success"]
                    for key in ("outcome", "feedback_ref", "next_node_ref"):
                        if key in expected_success:
                            success[key] = getattr(after, key)
                    actual = {"success": success}
                    self.assertEqual(content.encode_run_state(state), before)
                self.assertEqual(row["expected"], actual)

    def test_every_runtime_recipe(self) -> None:
        content = importlib.import_module("golden_board.content")
        recipes = [row for row in FIXTURE["recipes"] if row["operation"] != "stream_validation"]
        self.assertEqual(len(recipes), 5)
        support_row = next(
            row for row in FIXTURE["recipes"] if row["name"] == "maximum-support-content-stream"
        )
        support = _content_recipe_bytes(FIXTURE, support_row)
        projection = content.stream_validation(support)
        for row in recipes:
            built = _content_recipe_bytes(FIXTURE, row)
            with self.subTest(name=row["name"]):
                if row["operation"] == "validate_run_state":
                    try:
                        state = content.validate_run_state(projection, built)
                    except content.ContentReject as error:
                        actual = {
                            "rejection": {
                                "code": error.code,
                                "raw_end": error.raw_end,
                                "raw_start": error.raw_start,
                            }
                        }
                    else:
                        encoded = content.encode_run_state(state)
                        actual = {
                            "success": {
                                "state_length": len(encoded),
                                "state_sha256": hashlib.sha256(encoded).hexdigest(),
                            }
                        }
                    self.assertEqual(row["expected"], actual)
                    continue
                self.assertEqual(row["operation"], "step")
                state = content.new_run(projection)
                before_last = b""
                result = 0
                operation_count = row["input"]["operation_count"]
                self.assertEqual(len(built), operation_count * 4)
                for index in range(operation_count):
                    if index + 1 == operation_count:
                        before_last = content.encode_run_state(state)
                    state, result = content.step(
                        projection, state, built[index * 4 : index * 4 + 4]
                    )
                encoded = content.encode_run_state(state)
                self.assertEqual(
                    row["expected"],
                    {
                        "success": {
                            "final_state_bytes": len(encoded),
                            "final_state_sha256": hashlib.sha256(encoded).hexdigest(),
                            "last_interaction_result": result,
                            "state_unchanged": encoded == before_last,
                        }
                    },
                )

    def test_runtime_properties_and_dependency_boundary(self) -> None:
        content = importlib.import_module("golden_board.content")
        base = bytes.fromhex(FIXTURE["bases"][0]["stream_hex"])
        projection = content.stream_validation(base)
        self.assertEqual(
            _projection_value(content, content.stream_validation(base)),
            _projection_value(content, projection),
        )

        for length in range(9):
            state = content.new_run(projection)
            after, result = content.step(projection, state, b"\xff" * length)
            self.assertEqual(result, C.INTERACTION_INVALID_ACTION)
            self.assertEqual(content.encode_run_state(after)[-5:-1], b"\0" * 4)
            self.assertEqual(content.encode_run_state(state), bytes.fromhex(
                next(row for row in FIXTURE["cases"] if row["name"] == "new-run-exact")
                ["expected"]["success"]["state_hex"]
            ))

        state = content.new_run(projection)
        state, _ = content.step(projection, state, bytes.fromhex("03000000"))
        state = content.advance_committed(projection, state)
        state, _ = content.step(projection, state, bytes.fromhex("01000003"))
        state, _ = content.step(projection, state, bytes.fromhex("01000001"))
        self.assertEqual(state.buffer, (1, 3))
        state, _ = content.step(projection, state, bytes.fromhex("03000000"))
        state = content.advance_committed(projection, state)
        state, first = content.step(projection, state, bytes.fromhex("01000002"))
        state, second = content.step(projection, state, bytes.fromhex("01000002"))
        self.assertEqual((first, second, state.buffer), (1, 1, (2, 2)))

        other = content.stream_validation(base)
        with self.assertRaises(TypeError):
            content.step(other, content.new_run(projection), b"\0" * 4)

        source = repo_text_bytes(
            ROOT, b"python/golden_board/content.py"
        ).decode("utf-8")
        tree = ast.parse(source)
        imports = {
            (node.module, node.level)
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        self.assertEqual(
            imports,
            {
                ("__future__", 0),
                ("bisect", 0),
                ("dataclasses", 0),
                ("types", 0),
                ("typing", 0),
                (None, 1),
            },
        )
        direct_calls = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and any(
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == node.name
                for call in ast.walk(node)
            )
        }
        self.assertEqual(direct_calls, set())
        for forbidden in ("golden_board.chess", "golden_board.source", "curriculum"):
            self.assertNotIn(forbidden, source)

    def test_named_fault_specific_source_mutants_are_killed(self) -> None:
        content = importlib.import_module("golden_board.content")
        source = repo_text_bytes(
            ROOT, b"python/golden_board/content.py"
        ).decode("utf-8")
        rows = {
            row["name"]: row
            for group in (FIXTURE["cases"], FIXTURE["recipes"])
            for row in group
        }

        def load_mutant(name: str, replacements: tuple[tuple[str, str], ...]):
            changed = source
            for old, new in replacements:
                self.assertEqual(changed.count(old), 1, (name, old))
                changed = changed.replace(old, new)
            module_name = f"golden_board._content_mutant_{name.replace('-', '_')}"
            module = types.ModuleType(module_name)
            module.__file__ = str(ROOT / "python" / "golden_board" / "content.py")
            module.__package__ = "golden_board"
            sys.modules[module_name] = module
            try:
                exec(compile(changed, module.__file__, "exec"), module.__dict__)
            except BaseException:
                sys.modules.pop(module_name, None)
                raise
            self.addCleanup(sys.modules.pop, module_name, None)
            return module

        def rejection(module: object, name: str):
            row = rows[name]
            raw = _content_recipe_bytes(FIXTURE, row)
            try:
                module.stream_validation(raw)
            except module.ContentReject as error:
                return error.code, error.raw_start, error.raw_end
            return "accepted"

        def step_result(module: object, name: str):
            row = rows[name]
            data = row["input"]
            projection = module.stream_validation(bytes.fromhex(data["stream_hex"]))
            state = module.validate_run_state(projection, bytes.fromhex(data["state_hex"]))
            after, result = module.step(
                projection, state, bytes.fromhex(data["action_hex"])
            )
            return result, after.event_count

        def state_result(module: object, name: str):
            row = rows[name]
            data = row["input"]
            projection = module.stream_validation(bytes.fromhex(data["stream_hex"]))
            try:
                module.validate_run_state(projection, bytes.fromhex(data["state_hex"]))
            except module.ContentReject as error:
                return error.code, error.raw_start, error.raw_end
            return "accepted"

        mutants = (
            (
                "stage4-tag-skipped",
                ((
                    "    if role not in _ROLES:\n        _reject(C.CONTENT_BAD_TAG, start, start + 1)\n",
                    "    if False and role not in _ROLES:\n        _reject(C.CONTENT_BAD_TAG, start, start + 1)\n",
                ),),
                lambda module: rejection(module, "precedence-stage4-before-stage5a"),
            ),
            (
                "duplicate-after-limit",
                (("elif region in buffer and not (", "elif False and region in buffer and not ("),),
                lambda module: step_result(module, "step-duplicate-before-over-limit"),
            ),
            (
                "success-cycle-omitted",
                (
                    ("    if cycle_spans:\n", "    if False and cycle_spans:\n"),
                    (
                        "for target in adjacency[node_id]), default=0)",
                        "for target in adjacency[node_id] if component[target] != component[node_id]), default=0)",
                    ),
                ),
                lambda module: rejection(module, "success-cycle"),
            ),
            (
                "hybrid-prefix-only",
                ((
                    "    return _final_candidate(\n",
                    "    return candidates[0] if current_node == candidates[0].current_node_id else _final_candidate(\n",
                ),),
                lambda module: state_result(module, "validate-state-pre-post-advance-hybrid"),
            ),
            (
                "terminal-calls-consume",
                (
                    (
                        "    if state.phase == C.PHASE_COMMITTED:\n        return state, C.INTERACTION_ALREADY_COMMITTED\n",
                        "    if False and state.phase == C.PHASE_COMMITTED:\n        return state, C.INTERACTION_ALREADY_COMMITTED\n",
                    ),
                    (
                        "    if state.phase == C.PHASE_EXHAUSTED:\n        return state, C.INTERACTION_BUDGET_EXHAUSTED\n",
                        "    if False and state.phase == C.PHASE_EXHAUSTED:\n        return state, C.INTERACTION_BUDGET_EXHAUSTED\n",
                    ),
                ),
                lambda module: (
                    step_result(module, "step-committed-is-immutable"),
                    step_result(module, "step-exhausted-is-immutable"),
                ),
            ),
        )
        for name, replacements, observe in mutants:
            with self.subTest(name=name):
                baseline = observe(content)
                mutant = load_mutant(name, replacements)
                self.assertNotEqual(observe(mutant), baseline)


if __name__ == "__main__":
    unittest.main()
