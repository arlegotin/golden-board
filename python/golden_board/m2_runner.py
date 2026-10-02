"""Bounded generic runner and exact M2 semantic-path evidence."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

from . import canonical_manifest
from . import constants as C
from . import content


__all__ = (
    "EvaluatorPredicate",
    "GenericRunner",
    "M2_ALL_CONTENT_SHA256",
    "M2_SEMANTIC_ACTION_GROUPS",
    "M2_SEMANTIC_PATH_SHA256",
    "RunnerAtomEntry",
    "RunnerAtomSchema",
    "RunnerCommitment",
    "RunnerDisplayField",
    "RunnerDisplayGraph",
    "RunnerDisplayRecord",
    "RunnerError",
    "RunnerFrame",
    "RunnerPassiveView",
    "RunnerRegionView",
    "RunnerTrace",
    "SemanticCheckpoint",
    "m2_runner",
    "run_m2_semantic_path",
    "semantic_path_bytes",
    "semantic_path_sha256",
)


M2_ALL_CONTENT_SHA256 = (
    "de7e22f0aa4316d9f32d9435287dd19bd6c04519aae1dc9bd816613f26929671"
)
M2_SEMANTIC_PATH_SHA256 = (
    "966e510af60a9a95afc60badee2d985da95add187f7d132bc2009369db33cbd3"
)
_M2_ALL_CONTENT_LENGTH = 13_644
_M2_ALL_ROOT_ID = 182
_SEMANTIC_PATH_SCHEMA = "golden-board.runner-semantic-path/v0"

M2_SEMANTIC_ACTION_GROUPS = (
    (bytes.fromhex("01000002"), bytes.fromhex("03000000")),
    (bytes.fromhex("01000001"), bytes.fromhex("03000000")),
    (
        bytes.fromhex("01000003"),
        bytes.fromhex("01000001"),
        bytes.fromhex("03000000"),
    ),
    (
        bytes.fromhex("01000003"),
        bytes.fromhex("01000001"),
        bytes.fromhex("03000000"),
    ),
)


class RunnerError(ValueError):
    """One immutable runner-boundary failure."""

    __slots__ = ("_reason",)

    def __init__(self, reason: str):
        if type(reason) is not str:
            raise TypeError("runner reason must be a string")
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
class RunnerAtomEntry:
    value: int
    label: bytes | None


@dataclass(frozen=True, slots=True)
class RunnerAtomSchema:
    atom_class: int
    atom_width: int
    entries: tuple[RunnerAtomEntry, ...]
    min_value: int | None
    max_value: int | None
    allowed_mask: int | None


@dataclass(frozen=True, slots=True)
class RunnerDisplayField:
    name: bytes | None
    storage: int
    type_code: int
    count: int
    atoms: tuple[int, ...]
    record_refs: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class RunnerDisplayRecord:
    record_id: int
    kind: int
    text: bytes | None
    atom_schema: RunnerAtomSchema | None
    atoms: tuple[int, ...]
    rows: int
    columns: int
    fields: tuple[RunnerDisplayField, ...]
    opaque_data: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class RunnerDisplayGraph:
    root_record_id: int
    records: tuple[RunnerDisplayRecord, ...]


@dataclass(frozen=True, slots=True)
class RunnerRegionView:
    region_id: int
    label: bytes | None
    row_start: int
    row_end: int
    column_start: int
    column_end: int
    flags: int


@dataclass(frozen=True, slots=True)
class RunnerPassiveView:
    presentation: RunnerDisplayGraph
    regions: tuple[RunnerRegionView, ...]
    resulting_presentation: RunnerDisplayGraph | None
    limitation: bytes | None
    actions: tuple[bytes, ...]


@dataclass(frozen=True, slots=True)
class RunnerFrame:
    current_node_id: int
    global_remaining: int
    local_remaining: int
    phase: int
    outcome: int
    selection_buffer: tuple[int, ...]
    committed_response: bytes
    feedback_ref: int
    next_node_ref: int
    available_actions: tuple[bytes, ...]
    can_advance: bool
    presentation: RunnerDisplayGraph
    regions: tuple[RunnerRegionView, ...]
    passive: RunnerPassiveView | None
    feedback: RunnerDisplayGraph | None
    events: tuple[content.RunEventView, ...]


@dataclass(frozen=True, slots=True)
class EvaluatorPredicate:
    predicate_result_ref: int
    predicate_binding_ref: int
    binding_class: int
    namespace_id: int
    semantic_code: int
    argument: int
    auxiliary: int
    subject_opaque_data_ref: int
    subject_data_binding_ref: int
    result_atom_vector_ref: int


_NO_PREDICATE = EvaluatorPredicate(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)


@dataclass(frozen=True, slots=True)
class SemanticCheckpoint:
    current_node_id: int
    global_remaining: int
    local_remaining: int
    phase: int
    outcome: int
    selection_buffer: tuple[int, ...]
    committed_response: bytes
    feedback_ref: int
    next_node_ref: int
    available_actions: tuple[bytes, ...]
    can_advance: bool
    evaluator_predicate: EvaluatorPredicate


@dataclass(frozen=True, slots=True)
class RunnerCommitment:
    node_id: int
    committed_response: bytes
    outcome: int
    feedback_ref: int
    next_node_ref: int
    node_predicate: EvaluatorPredicate
    feedback_predicate: EvaluatorPredicate


@dataclass(frozen=True, slots=True)
class RunnerTrace:
    content_stream_sha256: str
    checkpoints: tuple[SemanticCheckpoint, ...]
    commitments: tuple[RunnerCommitment, ...]
    events: tuple[content.RunEventView, ...]


def _record_map(view: content.ContentProjectionView) -> dict[int, content.ContentRecordView]:
    output = {record.record_id: record for record in view.records}
    if len(output) != len(view.records):
        raise RunnerError("inconsistent_projection_view")
    return output


def _record(
    records: dict[int, content.ContentRecordView],
    record_id: int,
    expected: type,
) -> object:
    try:
        payload = records[record_id].payload
    except KeyError as error:
        raise RunnerError("inconsistent_projection_view") from error
    if type(payload) is not expected:
        raise RunnerError("inconsistent_projection_view")
    return payload


def _label(
    records: dict[int, content.ContentRecordView],
    record_id: int,
    suppressed: bool,
) -> bytes | None:
    if record_id == 0 or suppressed:
        return None
    value = _record(records, record_id, content.ContentText)
    assert isinstance(value, content.ContentText)
    return value.text.encode("utf-8")


def _atom_schema(
    records: dict[int, content.ContentRecordView],
    record_id: int,
    suppressed: bool,
) -> RunnerAtomSchema:
    value = _record(records, record_id, content.ContentAtomSchema)
    assert isinstance(value, content.ContentAtomSchema)
    return RunnerAtomSchema(
        value.atom_class,
        value.atom_width,
        tuple(
            RunnerAtomEntry(entry.code, _label(records, entry.label_text_ref, suppressed))
            for entry in value.entries
        ),
        value.min_value,
        value.max_value,
        value.allowed_mask,
    )


def _display_record(
    records: dict[int, content.ContentRecordView],
    record_id: int,
    suppressed: bool,
) -> tuple[RunnerDisplayRecord, tuple[int, ...]]:
    try:
        record = records[record_id]
    except KeyError as error:
        raise RunnerError("inconsistent_projection_view") from error
    value = record.payload
    empty_fields: tuple[RunnerDisplayField, ...] = ()
    if type(value) is content.ContentText:
        return (
            RunnerDisplayRecord(
                record_id,
                record.kind,
                None if suppressed else value.text.encode("utf-8"),
                None,
                (),
                0,
                0,
                empty_fields,
                (),
            ),
            (),
        )
    if type(value) is content.ContentAtomVector:
        return (
            RunnerDisplayRecord(
                record_id,
                record.kind,
                None,
                _atom_schema(records, value.atom_schema_ref, suppressed),
                value.atoms,
                0,
                0,
                empty_fields,
                (),
            ),
            (),
        )
    if type(value) is content.ContentMatrix:
        return (
            RunnerDisplayRecord(
                record_id,
                record.kind,
                None,
                _atom_schema(records, value.atom_schema_ref, suppressed),
                value.cells,
                value.rows,
                value.columns,
                empty_fields,
                (),
            ),
            (),
        )
    if type(value) is content.ContentTuple:
        schema = _record(records, value.field_schema_ref, content.ContentFieldSchema)
        assert isinstance(schema, content.ContentFieldSchema)
        if len(schema.fields) != len(value.field_values):
            raise RunnerError("inconsistent_projection_view")
        fields = []
        references = []
        for definition, field_value in zip(
            schema.fields, value.field_values, strict=True
        ):
            if type(field_value) is content.ContentAtomFieldValue:
                atoms = field_value.atoms
                refs: tuple[int, ...] = ()
            elif type(field_value) is content.ContentRecordRefFieldValue:
                atoms = ()
                refs = field_value.record_refs
                references.extend(refs)
            else:
                raise RunnerError("inconsistent_projection_view")
            fields.append(
                RunnerDisplayField(
                    _label(records, definition.name_text_ref, suppressed),
                    definition.storage,
                    definition.type_code,
                    definition.count,
                    atoms,
                    refs,
                )
            )
        return (
            RunnerDisplayRecord(
                record_id,
                record.kind,
                None,
                None,
                (),
                0,
                0,
                tuple(fields),
                (),
            ),
            tuple(references),
        )
    if type(value) is content.ContentOpaqueData:
        return (
            RunnerDisplayRecord(
                record_id,
                record.kind,
                None,
                None,
                (),
                0,
                0,
                empty_fields,
                value.data,
            ),
            (),
        )
    raise RunnerError("unsupported_display_kind")


def _display_graph(
    records: dict[int, content.ContentRecordView],
    root_record_id: int,
    suppressed: bool,
) -> RunnerDisplayGraph:
    pending = [root_record_id]
    emitted: dict[int, RunnerDisplayRecord] = {}
    while pending:
        record_id = pending.pop()
        if record_id in emitted:
            continue
        if len(emitted) >= len(records):
            raise RunnerError("inconsistent_projection_view")
        display, references = _display_record(records, record_id, suppressed)
        emitted[record_id] = display
        pending.extend(reversed(references))
    return RunnerDisplayGraph(
        root_record_id,
        tuple(emitted[record_id] for record_id in sorted(emitted)),
    )


def _regions(
    records: dict[int, content.ContentRecordView],
    region_set_ref: int,
    suppressed: bool,
) -> tuple[RunnerRegionView, ...]:
    region_set = _record(records, region_set_ref, content.ContentRegionSet)
    assert isinstance(region_set, content.ContentRegionSet)
    return tuple(
        RunnerRegionView(
            region.region_id,
            _label(records, region.label_ref, suppressed),
            region.row_start,
            region.row_end,
            region.column_start,
            region.column_end,
            region.flags,
        )
        for region in region_set.regions
    )


def _passive(
    records: dict[int, content.ContentRecordView],
    passive_trace_ref: int,
    suppressed: bool,
) -> RunnerPassiveView | None:
    if passive_trace_ref == 0:
        return None
    passive = _record(records, passive_trace_ref, content.ContentPassiveTrace)
    assert isinstance(passive, content.ContentPassiveTrace)
    return RunnerPassiveView(
        _display_graph(records, passive.presentation_ref, suppressed),
        _regions(records, passive.region_set_ref, suppressed),
        (
            None
            if passive.resulting_presentation_ref == 0
            else _display_graph(
                records, passive.resulting_presentation_ref, suppressed
            )
        ),
        _label(records, passive.limitation_text_ref, suppressed),
        passive.actions,
    )


def _available_actions(
    node: content.ContentLessonNode,
    regions: tuple[RunnerRegionView, ...],
    state: content.RunStateView,
) -> tuple[bytes, ...]:
    if state.phase != C.PHASE_ACTIVE:
        return ()
    output = []
    can_select = len(state.selection_buffer) < node.max_selections
    repeated = bool(
        node.response_shape == C.RESPONSE_SEQUENCE
        and node.flags & C.LESSON_ALLOW_REPEATED_SELECTIONS
    )
    if can_select:
        for region in regions:
            if not region.flags & C.REGION_SELECTABLE:
                continue
            if region.region_id in state.selection_buffer and not repeated:
                continue
            output.append(bytes((C.ACTION_SELECT, 0, *region.region_id.to_bytes(2, "big"))))
    output.extend(
        (
            bytes((C.ACTION_RESET, 0, 0, 0)),
            bytes((C.ACTION_COMMIT, 0, 0, 0)),
        )
    )
    return tuple(output)


class GenericRunner:
    """One bounded mutable session over an accepted generic content stream."""

    __slots__ = ("_projection", "_projection_view", "_records", "_state", "_suppressed")

    def __init__(self, raw_content_bytes: bytes, *, label_suppressed: bool):
        if type(raw_content_bytes) is not bytes:
            raise TypeError("runner input must be bytes")
        if type(label_suppressed) is not bool:
            raise TypeError("label_suppressed must be bool")
        projection = content.stream_validation(raw_content_bytes)
        projection_view = content.projection_view(projection)
        self._projection = projection
        self._projection_view = projection_view
        self._records = _record_map(projection_view)
        self._state = content.new_run(projection)
        self._suppressed = label_suppressed

    @property
    def projection_view(self) -> content.ContentProjectionView:
        return self._projection_view

    def frame(self) -> RunnerFrame:
        state = content.run_state_view(self._state)
        node = _record(
            self._records, state.current_node_id, content.ContentLessonNode
        )
        assert isinstance(node, content.ContentLessonNode)
        regions = _regions(self._records, node.region_set_ref, self._suppressed)
        feedback = None
        if state.feedback_ref:
            feedback_value = _record(
                self._records, state.feedback_ref, content.ContentFeedback
            )
            assert isinstance(feedback_value, content.ContentFeedback)
            feedback = _display_graph(
                self._records, feedback_value.display_ref, self._suppressed
            )
        return RunnerFrame(
            state.current_node_id,
            state.global_remaining,
            state.local_remaining,
            state.phase,
            state.outcome,
            state.selection_buffer,
            state.committed_response,
            state.feedback_ref,
            state.next_node_ref,
            _available_actions(node, regions, state),
            state.phase == C.PHASE_COMMITTED and state.next_node_ref != 0,
            _display_graph(self._records, node.presentation_ref, self._suppressed),
            regions,
            _passive(self._records, node.passive_trace_ref, self._suppressed),
            feedback,
            state.events,
        )

    def perform(self, action: bytes) -> int:
        if type(action) is not bytes:
            raise TypeError("runner action must be bytes")
        frame = self.frame()
        if action not in frame.available_actions:
            raise RunnerError("action_not_available")
        self._state, result = content.step(self._projection, self._state, action)
        return result

    def advance(self) -> None:
        if not self.frame().can_advance:
            raise RunnerError("advance_not_available")
        self._state = content.advance_committed(self._projection, self._state)

    def evaluator_predicate(self) -> EvaluatorPredicate:
        state = content.run_state_view(self._state)
        node = _record(
            self._records, state.current_node_id, content.ContentLessonNode
        )
        assert isinstance(node, content.ContentLessonNode)
        return _evaluator_predicate(self._records, node.predicate_result_ref)

    def commitment(self) -> RunnerCommitment:
        state = content.run_state_view(self._state)
        if state.phase != C.PHASE_COMMITTED:
            raise RunnerError("commitment_not_available")
        node = _record(
            self._records, state.current_node_id, content.ContentLessonNode
        )
        assert isinstance(node, content.ContentLessonNode)
        feedback = _record(
            self._records, state.feedback_ref, content.ContentFeedback
        )
        assert isinstance(feedback, content.ContentFeedback)
        return RunnerCommitment(
            state.current_node_id,
            state.committed_response,
            state.outcome,
            state.feedback_ref,
            state.next_node_ref,
            _evaluator_predicate(self._records, node.predicate_result_ref),
            _evaluator_predicate(self._records, feedback.predicate_result_ref),
        )


def _evaluator_predicate(
    records: dict[int, content.ContentRecordView], predicate_result_ref: int
) -> EvaluatorPredicate:
    if predicate_result_ref == 0:
        return _NO_PREDICATE
    predicate = _record(
        records, predicate_result_ref, content.ContentPredicateResult
    )
    assert isinstance(predicate, content.ContentPredicateResult)
    binding = _record(
        records, predicate.predicate_binding_ref, content.ContentSemanticBinding
    )
    subject = _record(
        records, predicate.subject_opaque_data_ref, content.ContentOpaqueData
    )
    _record(records, predicate.result_atom_vector_ref, content.ContentAtomVector)
    assert isinstance(binding, content.ContentSemanticBinding)
    assert isinstance(subject, content.ContentOpaqueData)
    return EvaluatorPredicate(
        predicate_result_ref,
        predicate.predicate_binding_ref,
        binding.binding_class,
        binding.namespace_id,
        binding.semantic_code,
        binding.argument,
        binding.auxiliary,
        predicate.subject_opaque_data_ref,
        subject.data_binding_ref,
        predicate.result_atom_vector_ref,
    )


def m2_runner(raw_content_bytes: bytes, *, label_suppressed: bool) -> GenericRunner:
    if type(raw_content_bytes) is not bytes:
        raise TypeError("runner input must be bytes")
    if (
        len(raw_content_bytes) != _M2_ALL_CONTENT_LENGTH
        or hashlib.sha256(raw_content_bytes).hexdigest() != M2_ALL_CONTENT_SHA256
    ):
        raise RunnerError("m2_content_stream_identity")
    runner = GenericRunner(raw_content_bytes, label_suppressed=label_suppressed)
    if runner.projection_view.root_record_id != _M2_ALL_ROOT_ID:
        raise RunnerError("m2_content_stream_identity")
    return runner


def _checkpoint(runner: GenericRunner) -> SemanticCheckpoint:
    frame = runner.frame()
    return SemanticCheckpoint(
        frame.current_node_id,
        frame.global_remaining,
        frame.local_remaining,
        frame.phase,
        frame.outcome,
        frame.selection_buffer,
        frame.committed_response,
        frame.feedback_ref,
        frame.next_node_ref,
        frame.available_actions,
        frame.can_advance,
        runner.evaluator_predicate(),
    )


def run_m2_semantic_path(
    raw_content_bytes: bytes, *, label_suppressed: bool
) -> RunnerTrace:
    runner = m2_runner(raw_content_bytes, label_suppressed=label_suppressed)
    checkpoints = [_checkpoint(runner)]
    commitments = []
    for group_index, actions in enumerate(M2_SEMANTIC_ACTION_GROUPS):
        if group_index:
            runner.advance()
            checkpoints.append(_checkpoint(runner))
        for action in actions:
            runner.perform(action)
            checkpoints.append(_checkpoint(runner))
        commitments.append(runner.commitment())
    final = runner.frame()
    return RunnerTrace(
        M2_ALL_CONTENT_SHA256,
        tuple(checkpoints),
        tuple(commitments),
        final.events,
    )


def _predicate_value(value: EvaluatorPredicate) -> dict[str, int]:
    return {
        "argument": value.argument,
        "auxiliary": value.auxiliary,
        "binding_class": value.binding_class,
        "namespace_id": value.namespace_id,
        "predicate_binding_ref": value.predicate_binding_ref,
        "predicate_result_ref": value.predicate_result_ref,
        "result_atom_vector_ref": value.result_atom_vector_ref,
        "semantic_code": value.semantic_code,
        "subject_data_binding_ref": value.subject_data_binding_ref,
        "subject_opaque_data_ref": value.subject_opaque_data_ref,
    }


def semantic_path_bytes(trace: RunnerTrace) -> bytes:
    if type(trace) is not RunnerTrace:
        raise TypeError("expected RunnerTrace")
    value = {
        "checkpoints": [
            {
                "available_actions_hex": [action.hex() for action in item.available_actions],
                "can_advance": item.can_advance,
                "committed_response_hex": item.committed_response.hex(),
                "current_node_id": item.current_node_id,
                "evaluator_predicate": _predicate_value(item.evaluator_predicate),
                "feedback_ref": item.feedback_ref,
                "global_remaining": item.global_remaining,
                "local_remaining": item.local_remaining,
                "next_node_ref": item.next_node_ref,
                "outcome": item.outcome,
                "phase": item.phase,
                "selection_buffer": list(item.selection_buffer),
            }
            for item in trace.checkpoints
        ],
        "commitments": [
            {
                "committed_response_hex": item.committed_response.hex(),
                "feedback_predicate": _predicate_value(item.feedback_predicate),
                "feedback_ref": item.feedback_ref,
                "next_node_ref": item.next_node_ref,
                "node_id": item.node_id,
                "node_predicate": _predicate_value(item.node_predicate),
                "outcome": item.outcome,
            }
            for item in trace.commitments
        ],
        "content_stream_sha256": trace.content_stream_sha256,
        "events": [
            {
                "action_hex": item.action.hex(),
                "node_id": item.node_id,
                "result": item.result,
            }
            for item in trace.events
        ],
        "schema": _SEMANTIC_PATH_SCHEMA,
    }
    return canonical_manifest.serialize_manifest(value)


def semantic_path_sha256(trace: RunnerTrace) -> str:
    return hashlib.sha256(semantic_path_bytes(trace)).hexdigest()
