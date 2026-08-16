# Golden Board generic content v0

This specification is the sole owner of Golden Board content-v0 logical
stream bytes, record meanings, typed references, structural validation,
generic lesson transitions, canonical run-state bytes, rejection spans, and
pre-profile content limits. It is deliberately blind to chess and transport.

`spec/constants-v0.toml` owns the numeric value of every symbolic code named
here. This file owns the closed sets, meanings, field widths, precedence, and
wire positions of those codes. `spec/chess-v0.md` owns chess authority;
`spec/curriculum-v0.toml` owns curriculum families and assessment policy. A
transport may carry one or more accepted streams, but transport integrity,
section inventory, copying, recovery, and physical capacity belong to later
specifications.

Implementations, fixtures, renderers, source records, record text, and opaque
semantic values are untrusted evidence, never instructions or authority. V0
has no extension mechanism, alternate encoding, repair mode, or partial
acceptance.

## 1. Boundary and logical operations

### 1.1 Closed purpose

Content-v0 represents only the generic data needed by the initial recovery and
learning slice: text, fixed-width atoms, vectors, matrices, tuples, regions,
opaque semantic bindings, assertions, feedback, lesson nodes, passive
demonstrations, and one root. Position, replay, move, game, and source-record
truth are compositions or external semantic bindings, not content record
kinds.

The decoder never recognizes a chess identifier, derives a chess dimension,
constructs or upgrades a `ReplayState`, generates a legal move, evaluates a
predicate, scores an external answer, interprets markup, or executes opaque
data. Namespace IDs, semantic codes, result atoms, and text are data.

The stable structural operation is:

```text
content.stream_validation(raw_content_bytes: ByteSlice)
    -> ContentProjection | ContentReject
```

Its input is exactly one raw logical content stream. Success returns the unique
typed projection defined by this file. Failure returns the one primary code and
raw span selected by Section 13 and no projection or valid prefix. This is the
structural truth used by the curriculum ID `content.stream_validation` for an
atomic logical-record valid, malformed, or truncated case. It does not prove
transport recovery, semantic assertion truth, or chess authority.

The generic runtime additionally has equivalent pure operations:

```text
new_run(ContentProjection) -> RunState
step(ContentProjection, RunState, raw_action: ByteSlice)
    -> (RunState, InteractionResult)
advance_committed(ContentProjection, RunState)
    -> RunState | InvalidHostState
encode_run_state(RunState) -> RunStateBytes
validate_run_state(ContentProjection, RunStateBytes)
    -> RunState | ContentReject
```

`InvalidHostState` is a host programming error with no canonical wire code. It
never mutates the supplied state. There is no general serializer, dynamic
object model, recursive loader, expression language, extension registry,
markup engine, URL action, script support, callback, or generic VM.

### 1.2 Primitive conventions

- Every integer in stream, action, response, and run-state bytes is unsigned
  big-endian.
- `ByteSlice` is immutable and carries an explicit bounded length. A runtime
  inspects at most four bytes of an action and never copies an overlong action.
- Record IDs, declared `REGION_SET.region_id` values, and references are `u16`;
  record and declared region IDs are nonzero. A region value in an encoded
  case, action, or run-state buffer is syntactically any `u16`, and zero fails
  that field's later membership or transition rule. A zero reference is invalid
  except where its field explicitly defines absence or terminal meaning.
- Format-reserved bytes and flag bits must be zero. Unknown tags, codes, or
  kinds reject; none are ignored or masked. Schema-declared enum/mask values
  outside their valid set are invalid atom values, not format-reserved fields.
- “Earlier” means a numerically smaller record ID, which is also earlier in
  source order after framing validation.
- “Sorted” means strictly increasing unsigned canonical bytes unless a rule
  separately permits equality. A sorted collection is duplicate-free.
- Record-ID equality or decrease uses the framing-specific
  `CONTENT_RECORD_ORDER`. In every payload sorted-unique collection, equality
  with an earlier value is only `CONTENT_DUPLICATE`; a strictly lower later
  value is only `CONTENT_NONCANONICAL_ORDER`. Complete canonical case-response
  bytes follow the payload rule.
- Every length, product, sum, graph count, offset, and derived width is checked
  before allocation, iteration, indexing, or output growth. Parsing and graph
  checks are iterative and bounded; correctness must not depend on recursion
  depth, locale, time, randomness, host enum layout, or map iteration order.

### 1.3 Canonical projection

`ContentProjection` is an immutable value containing `version = 0`, the root
record ID, and the ordered record sequence. Each projected record contains its
`record_id`, symbolic `record_kind`, and the named typed payload fields printed
in Sections 3–6. Raw length fields, reserved zeros, and source offsets are not
semantic payload fields; offsets may be retained as noncanonical diagnostics.
Atom bytes project to their unsigned value, references remain record IDs, and
actions/responses retain their canonical byte order. No implementation may add
an inferred default, normalize text, reorder a sequence, resolve an opaque
namespace, or omit an encoded zero-valued optional field from equality.

This logical projection is the cross-language comparison surface. This file
does not define a JSON projection or give JSON key order canonical status.

## 2. Stream framing and closed kinds

### 2.1 Frame

```text
ContentStream :=
    u16 content_version       # exactly 0
    u16 record_count          # 2..65535
    Record[record_count]

Record :=
    u16 record_id             # nonzero, strictly increasing
    u16 record_kind
    u32 payload_length
    u8  payload[payload_length]
```

The complete input is at most 1,048,576 bytes. The validator bounds and indexes
the complete frame before exposing or locally decoding any record. It then
validates records in ascending ID order, references, graph invariants, and
budgets. A declared record payload is contiguous; padding and trailing bytes
do not exist.

For a record beginning at raw offset `s`, the ID span is `[s,s+2)`, kind span
`[s+2,s+4)`, length span `[s+4,s+8)`, and payload span
`[s+8,s+8+payload_length)`.

### 2.2 Record kinds

The constants owner assigns the following fourteen nonzero kind codes. This
set is closed; kind zero and every other code reject.

```text
CONTENT_KIND_TEXT
CONTENT_KIND_ATOM_SCHEMA
CONTENT_KIND_ATOM_VECTOR
CONTENT_KIND_MATRIX
CONTENT_KIND_FIELD_SCHEMA
CONTENT_KIND_TUPLE
CONTENT_KIND_REGION_SET
CONTENT_KIND_SEMANTIC_BINDING
CONTENT_KIND_OPAQUE_DATA
CONTENT_KIND_PREDICATE_RESULT
CONTENT_KIND_FEEDBACK
CONTENT_KIND_PASSIVE_TRACE
CONTENT_KIND_LESSON_NODE
CONTENT_KIND_ROOT
```

At most 4,096 records of any one non-root kind may occur. Exactly one root
occurs. A genuinely needed new kind requires a new content version; v0 has no
reserved extension range.

## 3. Primitive records

### 3.1 `CONTENT_KIND_TEXT`

The payload is exactly `1..4096` text bytes; record framing supplies its
length. It is strict UTF-8 with no normalization. LF is permitted. Every other
C0 control, CR, DEL, C1 control U+0080..U+009F, NUL, and an initial U+FEFF are
forbidden. Other Unicode scalar values U+0020 and above are permitted.

Strict UTF-8 means the Unicode scalar byte grammar: overlong encodings,
surrogates, invalid continuations, and values above U+10FFFF are ill-formed.
Within the payload, let `p` be the first byte after the maximal valid prefix.
An ill-formed subsequence spans `[p,p+1)` in raw stream coordinates. A valid
lead whose required continuation bytes are missing at payload end spans from
`p` through that payload end.

A `TEXT` used as a field name must additionally contain no LF. Renderers treat
all text as escaped literal text, never markup, a URL, a template, a command,
or an instruction. This is v0's only textual primitive.

### 3.2 `CONTENT_KIND_ATOM_SCHEMA`

```text
u8  atom_class
u8  atom_width        # exactly 1, 2, or 4
u16 entry_count
class-specific bytes
```

The closed classes are `ATOM_UNSIGNED`, `ATOM_ENUM`, and `ATOM_MASK`. `Atom`
below means exactly `atom_width` bytes decoded as unsigned big-endian.

For `ATOM_UNSIGNED`:

```text
entry_count = 0
Atom min_value
Atom max_value
```

`min_value <= max_value`. An atom is valid exactly when it lies in that closed
range.

For `ATOM_ENUM`:

```text
entry_count = 1..4096
entry_count * {
    Atom code
    u16  label_text_ref
}
```

Codes are strictly increasing. Every label is an earlier `TEXT`. The listed
codes are exactly the valid values; every other width-fitting value is an
invalid atom value.

For `ATOM_MASK`:

```text
Atom allowed_mask
entry_count * {
    Atom one_hot_bit
    u16  label_text_ref
}
```

`entry_count` is `popcount(allowed_mask)` and may be zero. Each listed bit is
nonzero, one-hot, contained in `allowed_mask`, strictly increasing, and has an
earlier `TEXT` label. These rules make their bitwise OR exactly
`allowed_mask`; no second search for a missing bit is needed. An atom is valid
exactly when it has no bit outside `allowed_mask`; a complement bit is an
invalid atom value.

Each class has exactly the payload length derived above. There is no signed,
floating, variable-width, implicit, native, or textual atom encoding.

### 3.3 `CONTENT_KIND_ATOM_VECTOR`

```text
u16 atom_schema_ref
u16 atom_count        # 0..65535
Atom atoms[atom_count]
```

The schema is an earlier `ATOM_SCHEMA`; every atom satisfies it. Payload length
is exactly `4 + atom_count * schema.atom_width`. A scalar value is exactly a
vector with count one. Count zero is the sole empty vector representation.

### 3.4 `CONTENT_KIND_MATRIX`

```text
u16 atom_schema_ref
u16 rows              # 1..65535
u16 columns           # 1..65535
Atom cells[rows * columns]
```

The schema is earlier. The checked cell product is `1..65535`, every cell
satisfies the schema, and payload length is exactly
`6 + rows * columns * schema.atom_width`. Cells are row-major: row zero in
column order, then each later row.

### 3.5 `CONTENT_KIND_FIELD_SCHEMA`

```text
u16 field_count       # 1..256

field_count * {
    u16 name_text_ref
    u8  storage
    u8  reserved_zero
    u16 type
    u16 count
}
```

Storage is exactly `FIELD_INLINE_ATOM` or `FIELD_RECORD_REF`.

For `FIELD_INLINE_ATOM`, `type` is an earlier `ATOM_SCHEMA` record ID and
`count` is `1..4096`. Its tuple-width contribution is
`atom_schema.atom_width * count`.

For `FIELD_RECORD_REF`, `type` is the constants-owned numeric record-kind code,
not a record ID, and `count` is `1..4096`. Only these value kinds are permitted:

```text
CONTENT_KIND_TEXT
CONTENT_KIND_ATOM_VECTOR
CONTENT_KIND_MATRIX
CONTENT_KIND_TUPLE
CONTENT_KIND_OPAQUE_DATA
```

Its tuple-width contribution is `2 * count` bytes. Each name is an earlier
single-line `TEXT`; field-name byte strings are distinct. Across all fields,
the checked sum of inline atoms plus record-reference slots is at most 4,096.
The exact derived tuple width is the checked sum of all contributions.

### 3.6 `CONTENT_KIND_TUPLE`

```text
u16 field_schema_ref
u8  field_bytes[exact derived schema width]
```

The field schema is earlier. Fields appear in schema order with no tags,
padding, lengths, or optional values. Inline atoms satisfy their declared atom
schema. Each record-reference slot is a nonzero earlier ID of exactly the
declared value kind. The payload length is exactly two plus the derived width.

## 4. Regions and presentation linkage

### 4.1 `CONTENT_KIND_REGION_SET`

```text
u16 surface_matrix_ref
u16 region_count       # 1..4096

region_count * {
    u16 region_id      # nonzero, strictly increasing
    u16 label_ref      # 0 or earlier DisplayRef
    u16 row_start
    u16 row_end
    u16 column_start
    u16 column_end
    u8  flags
    u8  reserved_zero
}
```

`surface_matrix_ref` is an earlier `MATRIX`. Coordinates are half-open and
nonempty:

```text
row_start < row_end <= surface.rows
column_start < column_end <= surface.columns
```

Every region is visible. The only live flag bits are
`REGION_SELECTABLE` and `REGION_HIGHLIGHTED`; every other bit is reserved.
All rectangles carrying `REGION_SELECTABLE` are pairwise disjoint. The bounded
check examines at most 8,386,560 unordered pairs for 4,096 regions. Nonselectable
regions may overlap because they cannot create ambiguous input mapping.

### 4.2 Display and presentation categories

`DisplayRef` means exactly an earlier record of kind `TEXT`, `ATOM_VECTOR`,
`MATRIX`, `TUPLE`, or `OPAQUE_DATA`. Zero means “no label” only in
`REGION_SET.label_ref`; it is not a DisplayRef elsewhere.

A `PresentationRef` is either:

1. the exact `MATRIX` named by the associated region set's
   `surface_matrix_ref`; or
2. an earlier `TUPLE` whose transitive record-reference slots contain that
   exact surface matrix exactly once and contain no other `MATRIX`.

The transitive walk follows only `FIELD_RECORD_REF` slots. Earlier-only tuple
dependencies make it acyclic. Validation derives each tuple once in ascending
record ID. One record-reference slot contributes `(0, none)` for a non-matrix,
non-tuple value, `(1, matrix_id)` for a matrix, or the already-derived tuple
summary for a tuple. Slot summaries are added with the occurrence count
saturated at two; a sole matrix ID is retained only while the total is exactly
one. Thus every tuple has one linear-work summary `(0, none)`,
`(1, sole_matrix_id)`, or `(2, none)`, where two means two-or-more.

Occurrences are counted by reference slot and path, not merely by unique target
ID, so reaching the same matrix through two slots produces the saturated count
two and rejects. A presentation accepts exactly when its direct/derived summary
is `(1, region_surface_matrix_id)`. Text prompts and other non-matrix value
records may coexist. An unrelated surface or omitted surface rejects without
enumerating paths.

Every lesson/passive `presentation_ref`, and every nonzero passive
`resulting_presentation_ref`, satisfies this rule against that record's
`region_set_ref`. Zero resulting presentation means no distinct resulting
presentation is supplied; the committed view retains the original
presentation.

## 5. Opaque semantics and feedback

### 5.1 `CONTENT_KIND_SEMANTIC_BINDING`

The payload is exactly ten bytes:

```text
u8  binding_class
u8  reserved_zero
u16 namespace_id
u16 semantic_code
u16 argument
u16 auxiliary
```

`namespace_id` and `semantic_code` are nonzero opaque integers. The tuple
`(binding_class, namespace_id, semantic_code)` is unique in one stream.

For `BINDING_DATA`, `argument` is an earlier `ATOM_SCHEMA` and `auxiliary` is
an atom count in `1..4096`.

For `BINDING_PREDICATE`, `argument` is an earlier `SEMANTIC_BINDING` of class
`BINDING_DATA`, and `auxiliary` is an earlier result `ATOM_SCHEMA`.

No other binding class exists. Recognition of a namespace or semantic code by
another subsystem never changes what the generic decoder accepted.

### 5.2 `CONTENT_KIND_OPAQUE_DATA`

```text
u16 data_binding_ref
Atom data[binding.atom_count]
```

The reference is an earlier `BINDING_DATA`. Its argument schema supplies atom
width and validity; its auxiliary supplies the exact count. The generic
validator checks only those structural constraints. It does not interpret the
atoms or assert that they are a legal position, replay, move, or record.

### 5.3 `CONTENT_KIND_PREDICATE_RESULT`

The payload is exactly six bytes:

```text
u16 predicate_binding_ref
u16 subject_opaque_data_ref
u16 result_atom_vector_ref
```

All references are earlier. The binding has class `BINDING_PREDICATE`; the
subject's data binding is exactly the predicate binding's argument; and the
result vector uses exactly the predicate binding's auxiliary atom schema and
has count one. This is a packed assertion, not executable predicate code. Its
structural acceptance does not prove the assertion true.

### 5.4 `CONTENT_KIND_FEEDBACK`

The payload is exactly six bytes:

```text
u16 feedback_code
u16 display_ref
u16 predicate_result_ref
```

`display_ref` is a nonzero earlier `DisplayRef`. The closed feedback meanings
are:

| Feedback | Predicate-result field |
|---|---|
| `FEEDBACK_NEUTRAL` | exactly zero |
| `FEEDBACK_MATCH` | nonzero earlier `PREDICATE_RESULT` |
| `FEEDBACK_NO_MATCH` | nonzero earlier `PREDICATE_RESULT` |
| `FEEDBACK_ALTERNATIVE` | nonzero earlier `PREDICATE_RESULT` |
| `FEEDBACK_LIMITATION` | exactly zero |

There is no implicit feedback and no generic correctness inference. An exact
legal-but-outside-objective case uses `FEEDBACK_ALTERNATIVE` with its own
assertion rather than a chess-specific feedback code.

## 6. Passive traces, lesson nodes, and root

### 6.1 Canonical actions and responses

Canonical action bytes are exactly four bytes:

```text
u8  action_code
u8  reserved_zero
u16 region_id
```

The only valid callable action codes are `ACTION_SELECT`, `ACTION_RESET`, and
`ACTION_COMMIT`. Action tag zero is reserved and non-callable. The exact four-
zero byte value is named `INVALID_ACTION_SENTINEL`; it is not an action code and
appears only in a run-state event log after malformed raw input. A well-framed
`SELECT` carries any `u16` region ID, including zero;
region validity is a transition result. Well-framed `RESET` and `COMMIT`
require a zero region ID.

Canonical response bytes are:

```text
u8  response_shape
u16 selection_count
u16 region_ids[selection_count]
```

The closed shapes are `RESPONSE_SINGLE`, `RESPONSE_SET`, and
`RESPONSE_SEQUENCE`. `SINGLE` has count zero or one. `SET` IDs are unique and
strictly increasing. `SEQUENCE` preserves order and permits repeats only when
its lesson node enables them. Empty commit is always a syntactically valid
response; packed acceptance derives only from an explicit accepted case.
External validity is evaluator-side and is never encoded here.

### 6.2 `CONTENT_KIND_PASSIVE_TRACE`

```text
u16 presentation_ref
u16 region_set_ref
u16 resulting_presentation_ref   # 0 allowed
u16 limitation_text_ref          # 0 allowed
u16 action_count                 # 1..65535
Action actions[action_count]
u8  expected_outcome
u8  reserved_zero
u16 expected_feedback_ref
u16 expected_next_node_ref       # 0 means terminal
```

Payload length is exactly `16 + 4 * action_count`.
All nonzero reference fields except `expected_next_node_ref` are earlier
dependencies.
The next-node field is a control reference. Outcome is exactly
`OUTCOME_ACCEPTED`, `OUTCOME_REJECTED`, or `OUTCOME_NEUTRAL`. Expected feedback
is a nonzero earlier `FEEDBACK`.

Every passive trace is referenced by exactly one `LESSON_NODE`; it is a
standalone per-node demonstration, not a cross-node trace protocol. Its
presentation and region-set IDs equal that node's IDs. It is replayed from a
fresh empty active state at that node with both remaining budgets initialized
to the node's `item_event_budget`. Every pre-final action is a well-framed
`SELECT` or `RESET` whose result is respectively `INTERACTION_SELECTED` or
`INTERACTION_RESET`; the final action is `COMMIT`. Replay must finish committed
and exactly reproduce the encoded outcome, feedback, and next-node edge. The
action count is at most the node budget. It neither advances nor demonstrates
another node.

`limitation_text_ref` is nonzero exactly for a trace referenced by a
`ROLE_HEURISTIC` node and is then an earlier `TEXT`; it is zero for every other
role. A nonzero resulting presentation satisfies Section 4.2. The trace may
select only the node's declared selectable regions; the region set is the
complete exposed action scope.

### 6.3 `CONTENT_KIND_LESSON_NODE`

```text
u8  role
u8  response_shape
u8  answer_mode
u8  flags
u16 presentation_ref
u16 region_set_ref
u16 predicate_result_ref
u16 passive_trace_ref
u16 max_selections
u16 item_event_budget
u16 case_count

case_count * {
    u8  case_class
    u8  reserved_zero
    u16 selection_count
    u16 region_ids[selection_count]
    u16 feedback_ref
    u16 next_node_ref
}

u16 default_feedback_ref
u16 default_next_node_ref
```

Payload length is exactly `22 + sum(8 + 2 * selection_count)` over the encoded
cases.
The closed lesson roles are `ROLE_EXACT_RULE`,
`ROLE_OBSERVABLE_RELATION`, `ROLE_WORKED_EXAMPLE`, `ROLE_HEURISTIC`, and
`ROLE_PRACTICE`. Curriculum roles `feedback` and `passive_trace` are embodied
by their record kinds and are not lesson-node role codes.

Answer mode is exactly `ANSWER_PACKED_PRACTICE`, `ANSWER_EXTERNAL`, or
`ANSWER_UNSCORED`. The only live flag is
`LESSON_ALLOW_REPEATED_SELECTIONS`; it is permitted only with
`RESPONSE_SEQUENCE`. Single and set forbid it. `max_selections` is `1` for
single and `0..4096` for set/sequence. It is a mechanical buffer ceiling, not
an answer-cardinality signal. `item_event_budget` is nonzero and at least
`max_selections + 1` using checked arithmetic.

Each case class is `CASE_ACCEPTED` or `CASE_REJECTED_SPECIAL`. Its selected
IDs form a canonical response under the node's shape, cap, repeat flag, and
selectable region set. Cases are strictly increasing by complete canonical
response bytes and therefore unique. `case_count` is `0..4096`. Feedback is a
nonzero earlier `FEEDBACK`; next node is a control reference and zero means
terminal. The default fields handle every well-formed response not listed as a
case. A node has at most 4,096 cases.

### 6.4 Closed role by answer-mode table

No combination outside this table is valid:

| Role | Answer mode | Predicate result | Cases and feedback | Passive trace |
|---|---|---|---|---|
| `ROLE_EXACT_RULE` | `ANSWER_UNSCORED` | required exact assertion | no cases; neutral default | optional |
| `ROLE_OBSERVABLE_RELATION` | `ANSWER_UNSCORED` | required exact assertion | no cases; neutral default | optional |
| `ROLE_WORKED_EXAMPLE` | `ANSWER_UNSCORED` | required exact assertion | no cases; neutral default | required |
| `ROLE_HEURISTIC` | `ANSWER_UNSCORED` | zero | no cases; limitation default | optional |
| `ROLE_PRACTICE` | `ANSWER_PACKED_PRACTICE` | required exact assertion | packed exact cases/default | required |
| `ROLE_PRACTICE` | `ANSWER_EXTERNAL` | zero | no cases; neutral default | zero |

A known role/mode pair outside the table is
`CONTENT_FORBIDDEN_ANSWER_DATA` at `answer_mode`. Within an allowed row, a
predicate, case, or trace reference/count whose required zero/nonzero presence
violates the table uses that code at the first such field in lesson payload
order. A packed node with no `CASE_ACCEPTED` instead uses
`CONTENT_BAD_RESPONSE_SCHEMA` at `case_count`. A present but incompatible
feedback relationship uses `CONTENT_BAD_FEEDBACK`, and a present trace that
does not replay exactly uses `CONTENT_BAD_PASSIVE_TRACE`.

Every unscored node has no cases and one answer-independent default edge. Its
default feedback is `FEEDBACK_NEUTRAL`, except a heuristic requires
`FEEDBACK_LIMITATION`. Exact-rule, observable-relation, and worked-example
assertions describe the lesson content but are not scored. Their optional or
required trace commits through the same neutral default edge.

Packed practice has at least one accepted case. Every accepted case uses
`FEEDBACK_MATCH` referencing exactly the node assertion. Its default uses
`FEEDBACK_NO_MATCH` referencing exactly that assertion. Every special rejected
case uses `FEEDBACK_ALTERNATIVE` and its own exact assertion. A packed case
cannot carry neutral or limitation feedback. The passive trace commits an
accepted case.

External practice contains no predicate result, case, accepted response,
correctness feedback, passive trace, answer cardinality, or correctness-
dependent edge. Its default is `FEEDBACK_NEUTRAL`, and the same edge is taken
for every committed response. Response shape and `max_selections` describe
only mechanics. External scoring and all accepted alternatives remain outside
the learner/public content stream.

No unencoded property such as “public teaching node” affects validation.

### 6.5 Exact commit outcome

Commit first canonicalizes the current buffer under the declared response
shape, then chooses a case by exact response-byte equality or the default:

- a packed-practice accepted case produces `OUTCOME_ACCEPTED`;
- a packed-practice special case or default produces `OUTCOME_REJECTED`; and
- an external or unscored default produces `OUTCOME_NEUTRAL`.

The selected feedback and next node are exactly the chosen case/default fields.
There is no partial match, inferred early completion, implicit correct answer,
administrator override, or content-side score.

### 6.6 `CONTENT_KIND_ROOT`

The payload is exactly four bytes:

```text
u16 entry_node_ref
u16 global_event_budget       # 1..65535
```

`entry_node_ref` is a nonzero earlier `LESSON_NODE`. Exactly one root exists;
it is the final and highest-ID record. The root's global budget is distinct
from every node's local `item_event_budget`; neither is inferred from the
other.

## 7. Typed references and graph validation

### 7.1 Field-by-field reference table

Unless marked control, every nonzero record reference is an earlier dependency.
For a required dependency, zero is `CONTENT_ZERO_REFERENCE`; for an explicitly
optional dependency, zero has the meaning printed here.

| Owner and field | Zero | Required target or interpretation | Order |
|---|---|---|---|
| enum/mask `label_text_ref` | forbidden | `TEXT` | earlier |
| `ATOM_VECTOR.atom_schema_ref` | forbidden | `ATOM_SCHEMA` | earlier |
| `MATRIX.atom_schema_ref` | forbidden | `ATOM_SCHEMA` | earlier |
| `FIELD_SCHEMA.name_text_ref` | forbidden | single-line `TEXT` | earlier |
| inline field `type` | forbidden | `ATOM_SCHEMA` record ID | earlier |
| record-ref field `type` | forbidden | permitted record-kind code, not an ID | not a reference |
| `TUPLE.field_schema_ref` | forbidden | `FIELD_SCHEMA` | earlier |
| tuple record-ref slot | forbidden | exactly its declared value kind | earlier |
| `REGION_SET.surface_matrix_ref` | forbidden | `MATRIX` | earlier |
| `REGION_SET.label_ref` | no label | `DisplayRef` | earlier |
| data binding `argument` | forbidden | `ATOM_SCHEMA` | earlier |
| data binding `auxiliary` | forbidden | atom count, not a reference | not a reference |
| predicate binding `argument` | forbidden | data `SEMANTIC_BINDING` | earlier |
| predicate binding `auxiliary` | forbidden | result `ATOM_SCHEMA` | earlier |
| `OPAQUE_DATA.data_binding_ref` | forbidden | data `SEMANTIC_BINDING` | earlier |
| predicate result `predicate_binding_ref` | forbidden | predicate `SEMANTIC_BINDING` | earlier |
| predicate result `subject_opaque_data_ref` | forbidden | `OPAQUE_DATA` | earlier |
| predicate result `result_atom_vector_ref` | forbidden | scalar `ATOM_VECTOR` | earlier |
| `FEEDBACK.display_ref` | forbidden | `DisplayRef` | earlier |
| `FEEDBACK.predicate_result_ref` | absent assertion where allowed | `PREDICATE_RESULT` | earlier |
| trace `presentation_ref` | forbidden | linked `PresentationRef` | earlier |
| trace `region_set_ref` | forbidden | `REGION_SET` | earlier |
| trace `resulting_presentation_ref` | no distinct result view | linked `PresentationRef` | earlier |
| trace `limitation_text_ref` | no limitation text | `TEXT` when heuristic | earlier |
| trace `expected_feedback_ref` | forbidden | `FEEDBACK` | earlier |
| trace `expected_next_node_ref` | terminal | `LESSON_NODE` | control |
| node `presentation_ref` | forbidden | linked `PresentationRef` | earlier |
| node `region_set_ref` | forbidden | `REGION_SET` | earlier |
| node `predicate_result_ref` | absent assertion where allowed | `PREDICATE_RESULT` | earlier |
| node `passive_trace_ref` | no trace where allowed | `PASSIVE_TRACE` | earlier |
| case/default `feedback_ref` | forbidden | `FEEDBACK` | earlier |
| case/default `next_node_ref` | terminal | `LESSON_NODE` | control |
| root `entry_node_ref` | forbidden | `LESSON_NODE` | earlier |

A dependency `ref >= owner_record_id` is forward/self even if no record has
that ID. A lower absent ID is missing. A present target of the wrong kind is a
wrong-kind reference; a required `SEMANTIC_BINDING` class is part of that typed
target and a wrong class uses the same code. After kind/class validation, an
incompatible field, binding, tuple, predicate, or presentation relation is a
schema mismatch.

Stage 5a/5c emits `CONTENT_ZERO_REFERENCE` only for a dependency-reference
field whose Zero column says “forbidden” unconditionally. Rows marked “not a
reference” remain Stage 4 local values and use their owning tag/count rule. A
reference field whose Zero column permits absence or terminal meaning is
skipped as a reference when zero. If its later role/feedback/trace row requires
nonzero, Stage 7 emits the owning semantic code:

- feedback `predicate_result_ref`: `CONTENT_BAD_FEEDBACK` in Stage 7b;
- node `predicate_result_ref` or `passive_trace_ref`:
  `CONTENT_FORBIDDEN_ANSWER_DATA` in Stage 7a; and
- trace `limitation_text_ref`: `CONTENT_BAD_PASSIVE_TRACE` in Stage 7c.

Zero region label, resulting presentation, and next-node fields retain their
unconditional absent/terminal meanings. Any nonzero conditional reference
still receives full Stage 5a validation before its semantic rule, so an invalid
nonzero reference wins over the later feedback/role/trace mismatch.

### 7.2 Reachability and edges

The only references exempt from earlier-only ordering are case next node,
default next node, and passive expected next node. They may target any existing
lesson node, including the owner node. Every nonzero target must exist and have
kind `LESSON_NODE`.

Runtime control edges are only case/default next-node fields. Starting from the
root, following every dependency and every runtime control edge must reach
every non-root record. The passive expected-next field is a mirror checked
against its owning node's committed edge; it does not establish reachability,
count as a runtime edge, or create a trace chain. Reachability is graph
reachability, not source proximity.

A passive trace has exactly one incoming `passive_trace_ref` from a lesson
node. Zero owners makes it unreachable and therefore
`CONTENT_ORPHAN_RECORD`; more than one owner is
`CONTENT_BAD_PASSIVE_TRACE`. The total count of nonzero case/default next-node
fields is at most 16,384 and is checked before graph traversal.

### 7.3 Success termination and budget proof

The success edges are all accepted-case edges of packed-practice nodes and the
single default edge of external/unscored nodes. Zero is a terminal success
edge. The directed graph of nonzero success edges over every reachable lesson
node must be acyclic. Consequently every success path terminates; a reachable
node may not end in a nonterminal success cycle.

A root success path begins at the root entry node, follows only success edges,
and ends at zero. Its cost is the checked sum of the complete
`item_event_budget` of every visited node, including entry and the node whose
success edge is terminal. The maximum such sum over the finite success DAG
must be at most `ROOT.global_event_budget`. This deliberately budgets complete
local items, not merely trace length or `max_selections + 1`.

Special-case and packed-default rejection edges may form cycles. Each traversal
of any edge follows a commit, every commit consumes one global event, and
`advance_committed` never replenishes the global budget. Thus every such cycle
is bounded without enumerating the combinatorial response state space. Passive
traces are validated independently per node and are not concatenated into this
proof.

## 8. Interaction state machine

### 8.1 Result and phase sets

The closed interaction results are:

```text
INTERACTION_SELECTED
INTERACTION_RESET
INTERACTION_COMMITTED
INTERACTION_INVALID_ACTION
INTERACTION_INVALID_REGION
INTERACTION_DUPLICATE
INTERACTION_OVER_LIMIT
INTERACTION_ALREADY_COMMITTED
INTERACTION_BUDGET_EXHAUSTED
```

Run phases are `PHASE_ACTIVE`, `PHASE_COMMITTED`, and `PHASE_EXHAUSTED`.
`OUTCOME_NONE` has value zero and is the live no-outcome state value. The
nonzero outcomes are exactly `OUTCOME_ACCEPTED`, `OUTCOME_REJECTED`, and
`OUTCOME_NEUTRAL`.

### 8.2 New run

`new_run` selects the root entry node, sets global remaining to the root global
budget, local remaining to the entry node's `item_event_budget`, phase active,
outcome `OUTCOME_NONE`, empty response buffer, no committed response, and empty
event log. The budget proof guarantees the local value does not exceed the
initial global value.

### 8.3 Raw action normalization

These raw inputs normalize to `INVALID_ACTION_SENTINEL`:

- any length other than four;
- unknown/reserved action code, including caller-supplied tag zero;
- nonzero reserved byte; or
- nonzero region argument on `RESET` or `COMMIT`.

They return `INTERACTION_INVALID_ACTION`, consume one event, and log only the
sentinel. Attacker-controlled wrong-length bytes never enter canonical state.

A four-byte `SELECT` with zero, an absent region ID, or a visible but
nonselectable region remains its original canonical action. It returns
`INTERACTION_INVALID_REGION`, consumes one event, and logs that action. This
distinction and precedence are normative.

### 8.4 `step` order

`step` is total over a validated state and any raw action:

1. A committed state returns `INTERACTION_ALREADY_COMMITTED`, unchanged and
   unlogged.
2. An exhausted state returns `INTERACTION_BUDGET_EXHAUSTED`, unchanged and
   unlogged.
3. An active state necessarily has positive global and local remaining.
4. Normalize the raw action, then decrement both budgets exactly once.
5. A sentinel produces `INTERACTION_INVALID_ACTION` with no buffer change.
6. For `SELECT`, test region membership/selectability, then prohibited
   duplicate, then current buffer count against `max_selections`. Return
   respectively `INTERACTION_INVALID_REGION`, `INTERACTION_DUPLICATE`, or
   `INTERACTION_OVER_LIMIT` without mutation; otherwise insert into a sorted
   set/single buffer or append to a sequence and return
   `INTERACTION_SELECTED`.
7. `RESET` clears only the uncommitted buffer and returns
   `INTERACTION_RESET`.
8. `COMMIT` freezes the canonical response, chooses the exact case/default,
   outcome, feedback, and edge from Section 6, clears the mutable buffer,
   enters committed phase, and returns `INTERACTION_COMMITTED`.
9. Append exactly one event containing the current node ID, canonical action,
   and returned result for the consumed call.
10. If a noncommit consumed the last global or local event, enter exhausted
    phase after logging its specific result. The buffer remains as produced by
    that action.

A commit on the final local or global event succeeds and remains committed,
even when both remaining values become zero. Terminal calls never change the
response, outcome, feedback, edge, state bytes, log, or budgets.

### 8.5 Committed advance

`advance_committed` is permitted only once on a committed state whose selected
next-node ref is nonzero. It preserves the global remaining value and event
log, moves to that exact target, clears committed response/outcome/feedback/
edge, and starts with an empty buffer.

If global remaining is zero, the target phase is exhausted and local remaining
is zero. Otherwise the target phase is active and local remaining is:

```text
min(target.item_event_budget, global_remaining)
```

Advancing a terminal edge, an active state, or an exhausted state is
`InvalidHostState` and leaves the state unchanged. No learner action performs
or implies an advance.

## 9. Canonical run-state bytes

### 9.1 Layout

```text
u16 state_version                 # exactly 0
u16 root_record_id
u16 current_node_id
u16 global_remaining
u16 local_remaining
u8  phase
u8  outcome
u16 buffer_count
u16 buffer_ids[buffer_count]
u16 committed_response_length
u8  committed_response[committed_response_length]
u16 event_count
Event events[event_count]

Event :=
    u16 node_id
    Action action                 # exactly four bytes
    u8  result
```

The root ID is exactly the projection's final root and the current node is an
existing lesson node. Event count is at most 65,535 and at most the root's
initial global budget. Each consumed call contributes one seven-byte event;
immutable terminal calls and `advance_committed` contribute none.

Active and exhausted states have outcome `OUTCOME_NONE` and no committed
response. Their buffer obeys the current node's shape, cap, selectable IDs, and
repetition rule. A committed state has an empty buffer, one canonical response
(including the three-byte empty response), and the exact nonzero outcome
derived from it.
Set buffers are sorted; sequence buffers preserve order. An event action is
either the four-zero sentinel or a canonical well-framed select/reset/commit;
its result is exactly the replayed result.

### 9.2 Replay validation

State validation begins from `new_run` and replays events in order. Before an
event, if replay is committed, the validator requires its nonzero selected
edge and applies the single deterministic advance; the event's node ID must
then equal the reached node. No event may follow an exhausted or terminal-
committed state. Each action/result pair must reproduce exactly.

After all events, the encoded fields must equal either the replay state or, if
that state is nonterminal committed, its one permitted deterministic advance.
This allows a persisted checkpoint immediately before or after host advance
without logging an invented learner event. Phase, current node, both budgets,
buffer, committed response, outcome, and all redundant counts must agree; any
trailing byte rejects. In particular:

```text
event_count + global_remaining = root.global_event_budget
```

Invalid raw action bytes cannot be recovered from a state: replay of the zero
sentinel deterministically yields `INTERACTION_INVALID_ACTION`.

### 9.3 Exact size maxima

The fixed fields outside buffer, response, and events occupy 18 bytes. The
largest buffer has 4,096 IDs (`8,192` bytes). The largest committed response
has one shape byte, a two-byte count, and 4,096 IDs (`8,195` bytes). The largest
event log has 65,535 seven-byte events (`458,745` bytes).

A committed state cannot also carry a buffer, so the exact maximum valid
run-state size is:

```text
18 + 8,195 + 458,745 = 466,958 bytes
```

An exhausted state carries no committed response. Its exact buffer maximum is:

```text
18 + 8,192 + 458,745 = 466,955 bytes
```

These maxima are attainable at the format bounds through budget-consuming
rejected cycles followed by a final full response or final noncommit. They are
not computed by adding both mutually exclusive response representations. The
validator checks the overall and exhausted-phase maxima before allocating
variable fields. Evidence includes each boundary and its one-byte-over case.

## 10. Resource limits

These are inclusive pre-profile parser/runtime safety limits, not promises
about final artifact capacity:

| Resource | Limit |
|---|---:|
| Raw content stream | 1,048,576 bytes |
| Records / highest possible ID | 65,535 |
| One declared payload | 1,048,576 bytes and within remaining stream |
| Records of any one non-root kind | 4,096 |
| Text payload | 4,096 bytes |
| Enum entries | 4,096 |
| Vector atoms | 65,535 |
| Matrix cells | 65,535 |
| Field-schema fields | 256 |
| Tuple inline atoms plus reference slots | 4,096 |
| Opaque-data atoms | 4,096 |
| Regions in one set | 4,096 |
| Lesson nodes | 4,096 |
| Cases in one node | 4,096 |
| Nonzero lesson case/default control edges | 16,384 |
| Global/local event budget and logged events | 65,535 |
| Canonical run state | 466,958 bytes |
| Exhausted canonical run state | 466,955 bytes |
| Root records | exactly one |

Structural minima and smaller per-field limits win. A payload still must fit
inside the already bounded stream. Counts/products are rejected before loops;
the validator does not allocate the declared count to discover that it is too
large.

## 11. Closed local validation rules

Payloads are decoded in ascending record ID and encoded field order. Framing
first establishes fixed or self-delimiting prefixes. Validation then performs:

1. local tags, reserved fields, UTF-8, self-contained counts/caps/products,
   self-derived lengths, numeric order/uniqueness, and values;
2. every statically located earlier typed reference;
3. lengths/layouts derived from those valid schemas or bindings;
4. tuple record-reference slots located by the valid derived layout;
5. referenced-schema atom values, field-name bytes, region bounds, binding/
   predicate relations, and presentation compatibility;
6. root/control/reachability;
7. role, response, feedback, and passive-trace rules; and
8. success termination and budgets.

Thus an invalid prerequisite reference wins over a length/value check that
cannot be interpreted without that reference. A tuple's valid field schema and
exact derived payload length win before any purported tuple-slot bytes are
treated as references.

| Kind | Self-contained work | Later prerequisite work |
|---|---|---|
| `TEXT` | minimum/cap in Stage 3; UTF-8 and scalar rules in Stage 4 | none |
| `ATOM_SCHEMA` | class/width/count, exact length, definitions/order/value in Stage 4 | labels in 5a |
| `ATOM_VECTOR` | four-byte prefix and count cap in Stage 4 | schema ref 5a, length 5b, atoms 5d |
| `MATRIX` | six-byte prefix, nonzero dimensions, cell-product cap in Stage 4 | schema ref 5a, length 5b, atoms 5d |
| `FIELD_SCHEMA` | `2 + 8 * field_count`, storage/reserved/count/slot totals in Stage 4 | refs 5a, name/schema relations 5d |
| `TUPLE` | two-byte prefix in Stage 4 | schema ref 5a, layout/length 5b, slots 5c, atoms 5d |
| `REGION_SET` | `4 + 14 * region_count`, IDs, flags, nonempty coordinates in Stage 4 | refs 5a, surface bounds/overlap 5d |
| `SEMANTIC_BINDING` | fixed length in Stage 3; class/reserved/count/value/key uniqueness in Stage 4 | refs 5a, binding relations 5d |
| `OPAQUE_DATA` | two-byte prefix in Stage 4 | binding ref 5a, length 5b, atoms 5d |
| `PREDICATE_RESULT` | fixed length in Stage 3 | refs 5a, binding/schema relations 5d |
| `FEEDBACK` | fixed length in Stage 3; code in Stage 4 | refs 5a, feedback relation Stage 7 |
| `PASSIVE_TRACE` | `16 + 4 * action_count`, action/outcome tags in Stage 4 | deps 5a, control Stage 6, replay Stage 7 |
| `LESSON_NODE` | self-derived case framing/tags/counts/order in Stage 4 | deps 5a, controls Stage 6, lesson rules Stage 7, budgets Stage 8 |
| `ROOT` | fixed four-byte payload in Stage 3 | entry ref 5a, graph Stage 6, budget Stage 8 |

The first rejection selection remains Section 13's global stage order, not the
implementation's convenient traversal order.

## 12. Authority and package boundary

An accepted `OPAQUE_DATA` or `PREDICATE_RESULT` remains structurally typed
content. Only a separately verified semantic owner may recognize its binding
and validate its truth. Content acceptance cannot create a chess value,
`ReplayState`, legal-game history, declaration, source score, or evaluator
answer. Binding mismatch is content-owned; semantic falsity is owned by the
recognized subsystem.

External/result-bearing nodes contain no packed answer, accepted cardinality,
correctness branch, correctness feedback, passive trace, seed, schedule, or
score. The later private assessment owner may bind responses evaluator-side;
that private material is not added to this stream before authorized reveal.

The later blind transducer may parse and traverse this grammar but must remain
generic. Conformance includes non-chess matrices, enums, and regions. No
chess-derived 8x8 dimension, chess identifier, or chess behavior may be linked
or special-cased; the existence of record kind 8 is unrelated and valid.

## 13. Rejection contract

### 13.1 Canonical shape and selection

```text
ContentReject {
    code: ContentRejectCode,
    raw_start: u32,
    raw_end: u32
}
```

The span is zero-based, half-open, and indexes exactly the supplied content or
run-state bytes. `ContentRejectCode` is a constants-owned `u16` before
downstream constants generation. The constants owner reserves code zero for
`CONTENT_OK` and assigns the nonzero codes in Section 13.2's order. Code and
span are the entire canonical rejection. Messages, paths, record IDs, and
richer context are optional, noncanonical, and excluded from fixture/cross-
language equality.

The earliest validation stage, including an explicitly lettered substage,
wins even if a later-stage defect starts at a lower byte. Within one leaf stage
or substage, lowest `raw_start` wins; equal starts use the code order below.
Stage 3's record-local gates are the sole further ordering rule: the earlier
source record wins, then the earlier gate named in Stage 3. Implementations may
discover candidates in another order but must return this result. Every
rejection returns no partial projection or state.

### 13.2 Primary code order

1. `CONTENT_LIMIT_EXCEEDED`
2. `CONTENT_TRUNCATED`
3. `CONTENT_BAD_VERSION`
4. `CONTENT_BAD_RECORD_COUNT`
5. `CONTENT_BAD_RECORD_ID`
6. `CONTENT_RECORD_ORDER`
7. `CONTENT_BAD_RECORD_KIND`
8. `CONTENT_BAD_PAYLOAD_LENGTH`
9. `CONTENT_TRAILING_DATA`
10. `CONTENT_BAD_TAG`
11. `CONTENT_RESERVED_NONZERO`
12. `CONTENT_BAD_UTF8`
13. `CONTENT_BAD_COUNT`
14. `CONTENT_BAD_VALUE`
15. `CONTENT_NONCANONICAL_ORDER`
16. `CONTENT_DUPLICATE`
17. `CONTENT_ZERO_REFERENCE`
18. `CONTENT_FORWARD_REFERENCE`
19. `CONTENT_MISSING_REFERENCE`
20. `CONTENT_WRONG_REFERENCE_KIND`
21. `CONTENT_SCHEMA_MISMATCH`
22. `CONTENT_ROOT_COUNT`
23. `CONTENT_ROOT_NOT_FINAL`
24. `CONTENT_BAD_CONTROL_EDGE`
25. `CONTENT_ORPHAN_RECORD`
26. `CONTENT_BAD_RESPONSE_SCHEMA`
27. `CONTENT_FORBIDDEN_ANSWER_DATA`
28. `CONTENT_BAD_FEEDBACK`
29. `CONTENT_BAD_PASSIVE_TRACE`
30. `CONTENT_BUDGET_PROOF`
31. `CONTENT_BAD_RUN_STATE`

### 13.3 Validation stages

**Stage 1 — whole-input bounds.** A content stream over 1,048,576 bytes or a
run state over the overall 466,958-byte maximum is
`CONTENT_LIMIT_EXCEEDED` at its first excess byte. No phase or declared field
has been decoded at this stage.

**Stage 2 — stream header.** Require the complete four-byte header before
interpreting either field. If it is incomplete, return `CONTENT_TRUNCATED` at
the zero-width span `[EOF,EOF)`; no version or count candidate exists.
Otherwise require version zero and record count `2..65535`; the lower-offset
field wins if both fail.

**Stage 3 — complete record index.** Process declared records in source order
through these record-local gates, completing one record before the next:

1. require its complete eight-byte header; otherwise return
   `CONTENT_TRUNCATED` at `[EOF,EOF)` and generate no ID, kind, or length
   candidate from the partial header;
2. check nonzero/increasing ID, known kind, the general 1,048,576-byte declared
   payload cap, the `TEXT` 4,096-byte declared payload cap, and the non-root
   per-kind record cap; ordinary lowest-offset/code-order selection applies
   within this complete header;
3. require the declared payload to remain in the stream, otherwise return
   `CONTENT_TRUNCATED` at `[EOF,EOF)`; and
4. check any known fixed/minimum payload shape, returning
   `CONTENT_BAD_PAYLOAD_LENGTH` at the payload-length field.

Stage 3 gate 4 uses this closed table:

| Kind | Stage 3 payload shape |
|---|---:|
| `TEXT` | at least 1 byte |
| `ATOM_SCHEMA` | at least 5 bytes |
| `ATOM_VECTOR` | at least 4 bytes |
| `MATRIX` | at least 7 bytes |
| `FIELD_SCHEMA` | at least 10 bytes |
| `TUPLE` | at least 3 bytes |
| `REGION_SET` | at least 18 bytes |
| `SEMANTIC_BINDING` | exactly 10 bytes |
| `OPAQUE_DATA` | at least 3 bytes |
| `PREDICATE_RESULT` | exactly 6 bytes |
| `FEEDBACK` | exactly 6 bytes |
| `PASSIVE_TRACE` | at least 20 bytes |
| `LESSON_NODE` | at least 22 bytes |
| `ROOT` | exactly 4 bytes |

After exactly the declared record count, reject any trailing byte. An exact
dynamic mismatch discovered from an in-range local count uses
`CONTENT_BAD_PAYLOAD_LENGTH` in Stage 4 or 5b. The first record beyond a
per-kind count cap is a limit failure at its kind field.

**Stage 4 — self-contained local payloads.** In ascending record ID and field
order, check tags, reserved bits/bytes, UTF-8, self-contained counts/products,
self-derived payload lengths, atom-schema definitions, nonempty region
coordinates, canonical order, and numeric uniqueness. This includes region IDs
inside each set-shaped case response and complete case-response ordering. Do
not validate an atom, length, tuple layout, or matrix bound that needs a
referenced target. A declared count or checked product above its stated maximum is
`CONTENT_LIMIT_EXCEEDED` at the owning count field; an in-range count that
violates a minimum or exact self-contained relation is `CONTENT_BAD_COUNT`.
No self-derived length or value candidate exists until every earlier local tag,
count, and width needed to interpret it is valid. In particular, an over-cap
count stops iteration and derived-length work, so its limit failure wins.
For `LESSON_NODE`, Stage 4 caps `case_count` and uses each
`selection_count` only for framing and order. `max_selections` and response
cardinality/cap/membership/repetition are Stage 7a; `item_event_budget` is
Stage 8b.
Equality in a sorted-unique collection is duplicate; only a strictly lower
later value is noncanonical order. Root/node budget minima and relationships
are deliberately deferred to Stage 8b.

**Stage 5a — statically located dependency references.** Check every
dependency field whose offset is known from framing and Stage 4, in ascending
owner ID and field order. This includes schema/binding refs that later derive a
layout, but excludes tuple record-reference slots whose offsets are not yet
known. Any zero/forward/missing/wrong-kind failure here wins before Stage 5b
regardless of raw offset.

**Stage 5b — reference-derived lengths and layouts.** From valid Stage 5a
targets, derive and check `ATOM_VECTOR`, `MATRIX`, `TUPLE`, and `OPAQUE_DATA`
payload lengths and tuple field offsets. A mismatch is
`CONTENT_BAD_PAYLOAD_LENGTH` at the record's payload-length field. No tuple
slot is read as a reference until its complete derived layout fits exactly.

**Stage 5c — tuple-slot dependency references.** Check every now-located tuple
record-reference slot in ascending tuple ID, field order, and element order.
Zero/forward/missing/wrong-kind rules are identical to Stage 5a.

**Stage 5d — reference-derived values and relations.** Validate vector/matrix/
tuple/opaque atoms against their referenced schemas; region ends against the
surface matrix followed by overlap among valid selectable rectangles;
single-line/distinct field-name bytes; binding and predicate schema relations;
and the linear presentation summary. Invalid references from
5a/5c and derived length failures from 5b always win first.

**Stage 6a — root shape.** Check root count and finality. These failures win
before any graph traversal.

**Stage 6b — controls and edge bound.** Check every order-exempt next-node
target in raw field order and the case/default runtime-edge cap. An invalid
control graph is not used to establish reachability.

**Stage 6c — reachability and trace ownership.** Follow the valid dependency
and runtime-control graph, reject the lowest-ID orphan, and check that no
passive trace has multiple lesson owners.

**Stage 7a — lesson response and answer mode.** In ascending lesson-node ID,
check response shape/cap/repetition/cases, the allowed role/mode row, and
required/forbidden predicate, case, and trace presence. Feedback code/assertion
relationships are exclusively Stage 7b.

**Stage 7b — feedback.** Check intrinsic feedback assertion rules and every
node's exact case/default feedback relationship.

**Stage 7c — passive replay.** Check node/trace linkage and replay every
required or present standalone trace.

**Stage 8a — success termination.** Reject a cycle in the success-edge graph
before using that graph for a path proof.

**Stage 8b — budgets.** Check node-local bounds, root global budget, and the
worst success-path proof. Root global budget zero, node local budget zero, and
`item_event_budget < max_selections + 1` are budget failures.

**Stage 9 — run state.** For `validate_run_state`, after the supplied content
projection is already valid, check state framing, codes, counts, the decoded
466,955-byte exhausted-phase maximum, canonical buffers/responses/events, and
exact replay. Stream Stages 2–8 are not rerun.

### 13.4 Invariant, code, and span table

| Invariant failure | Primary code | Normative span and stage |
|---|---|---|
| Whole stream or overall run-state byte cap | `CONTENT_LIMIT_EXCEEDED` | first excess byte; Stage 1 |
| Missing header/record/payload required byte | `CONTENT_TRUNCATED` | `[EOF,EOF)`; Stage 2 or 3 |
| Version not zero | `CONTENT_BAD_VERSION` | version field; Stage 2 |
| Record count outside `2..65535` | `CONTENT_BAD_RECORD_COUNT` | record-count field; Stage 2 |
| Record ID zero | `CONTENT_BAD_RECORD_ID` | record-ID field; Stage 3 |
| Record ID duplicate/decreasing | `CONTENT_RECORD_ORDER` | later record-ID field; Stage 3 |
| Unknown/zero record kind | `CONTENT_BAD_RECORD_KIND` | kind field; Stage 3 |
| Declared payload exceeds 1,048,576 bytes | `CONTENT_LIMIT_EXCEEDED` | payload-length field; Stage 3 |
| `TEXT` declared payload exceeds 4,096 bytes | `CONTENT_LIMIT_EXCEEDED` | record payload-length field; Stage 3 gate 2 |
| First non-root record beyond its per-kind cap | `CONTENT_LIMIT_EXCEEDED` | excess record's kind field; Stage 3 |
| Declared/self-derived/reference-derived payload length impossible | `CONTENT_BAD_PAYLOAD_LENGTH` | record payload-length field; Stage 3, 4, or 5b |
| Bytes remain after indexed records | `CONTENT_TRAILING_DATA` | first trailing byte; Stage 3 |
| Unknown content-payload class/storage/record-ref kind/role/shape/mode/case/feedback/action/outcome code | `CONTENT_BAD_TAG` | exact tag/code field; Stage 4 |
| Content-payload reserved byte or reserved flag bit nonzero | `CONTENT_RESERVED_NONZERO` | exact reserved/flag field; Stage 4 |
| Passive-trace `RESET`/`COMMIT` carries a nonzero argument | `CONTENT_BAD_VALUE` | that action's two-byte `region_id`; Stage 4 |
| Ill-formed UTF-8 | `CONTENT_BAD_UTF8` | first invalid byte after maximal valid prefix; incomplete final sequence spans its remaining bytes; Stage 4 |
| Declared count/product/cumulative total exceeds its field-specific cap | `CONTENT_LIMIT_EXCEEDED` | owning count field, or first field count crossing a cumulative cap; Stage 4 |
| In-range encoded count violates a structural equality/minimum | `CONTENT_BAD_COUNT` | owning count field; Stage 4 |
| Self-contained atom-schema/range/coordinate/min-max/namespace/code value invalid | `CONTENT_BAD_VALUE` | exact atom/value field; Stage 4 |
| Decreasing enum/bit/region/case/set value | `CONTENT_NONCANONICAL_ORDER` | later key/ID; a case uses its selection-count field; Stage 4 |
| Duplicate enum/bit/binding key/region/case/set value | `CONTENT_DUPLICATE` | later key/ID; a binding uses its class byte and a case uses its selection-count field; Stage 4 |
| Required reference is zero | `CONTENT_ZERO_REFERENCE` | exact reference field; Stage 5a or 5c |
| Dependency ref is self/forward | `CONTENT_FORWARD_REFERENCE` | exact reference field; Stage 5a or 5c |
| Lower dependency ref is absent | `CONTENT_MISSING_REFERENCE` | exact reference field; Stage 5a or 5c |
| Present dependency has wrong kind/class | `CONTENT_WRONG_REFERENCE_KIND` | exact reference field; Stage 5a or 5c |
| Referenced-schema atom invalid | `CONTENT_BAD_VALUE` | exact atom bytes; Stage 5d |
| Region exceeds surface bounds or selectable rectangles overlap | `CONTENT_BAD_VALUE` | offending end field; overlap uses later region-ID field; Stage 5d |
| Duplicate field-name bytes | `CONTENT_DUPLICATE` | later name-reference field; Stage 5d |
| Field-name/binding/tuple/predicate/presentation linkage mismatch | `CONTENT_SCHEMA_MISMATCH` | exact referencing field/slot; Stage 5d |
| Missing root or later additional root | `CONTENT_ROOT_COUNT` | `[EOF,EOF)` for missing; later root kind field for multiple; Stage 6a |
| Sole root not final/highest | `CONTENT_ROOT_NOT_FINAL` | root kind field; Stage 6a |
| First nonzero lesson case/default edge beyond 16,384 | `CONTENT_LIMIT_EXCEEDED` | exact excess control ref; Stage 6b |
| Control target absent/wrong kind or success cycle | `CONTENT_BAD_CONTROL_EDGE` | exact control ref; Stage 6b; cycle uses lowest-offset participating success ref in Stage 8a |
| Record unreachable from root | `CONTENT_ORPHAN_RECORD` | lowest-ID orphan's record-ID field; Stage 6c |
| Response cardinality/cap/selectable membership/repetition policy or accepted-case requirement invalid | `CONTENT_BAD_RESPONSE_SCHEMA` | incompatible repeat enablement uses node `flags`; a declared cap uses `max_selections`; case cardinality/cap uses that `selection_count`; zero/missing/nonselectable membership or forbidden sequence repetition uses the offending region ID; no accepted packed case uses `case_count`; Stage 7a; set order/duplicates and case ordering already use Stage 4 codes |
| Role/mode invalid or forbidden predicate/case/trace presence | `CONTENT_FORBIDDEN_ANSWER_DATA` | answer-mode field for an invalid row, otherwise first forbidden field in payload order; Stage 7a |
| Feedback code/assertion/node relationship invalid | `CONTENT_BAD_FEEDBACK` | intrinsic predicate-presence failure uses `FEEDBACK.predicate_result_ref`; a node relationship uses that case/default `feedback_ref`; Stage 7b |
| Multiple trace owners or trace link/action/replay/outcome mismatch | `CONTENT_BAD_PASSIVE_TRACE` | later node `passive_trace_ref` for multiple owners in Stage 6c; node/trace presentation or region linkage uses the node `passive_trace_ref`; limitation presence uses trace `limitation_text_ref`; count/budget uses trace `action_count`; replay failure uses the offending four-byte action; expected outcome/feedback/next mismatch uses that trace field; Stage 7c |
| Root budget zero, node local bound failure, or worst success path exceeds root budget | `CONTENT_BUDGET_PROOF` | node item-budget field for local failure; root global-budget field for root/path failure; Stage 8b |
| Exhausted state exceeds 466,955 bytes | `CONTENT_LIMIT_EXCEEDED` | first excess byte; Stage 9 |
| Run-state framing/code/canonical/replay/trailing mismatch | `CONTENT_BAD_RUN_STATE` | exact span in Section 13.5; Stage 9 |

For a prohibited text scalar or initial U+FEFF, `CONTENT_BAD_VALUE` spans that
scalar's UTF-8 bytes. An in-range mask popcount mismatch uses
`CONTENT_BAD_COUNT`; a multi-bit or wrong listed bit uses `CONTENT_BAD_VALUE`.
An unsigned-schema `min_value > max_value` failure spans the later encoded
`max_value`. A nonempty-coordinate failure spans its later `row_end` or
`column_end`; ordinary lowest-start selection makes the row failure win when
both relations fail.

For a product cap, the owning span is the later encoded multiplicand that makes
the checked product exceed the cap (`MATRIX.columns` for cells). A cumulative
cap uses the first encoded count whose addition crosses it.
When an expected dynamic payload is short or long but still wholly present,
`CONTENT_BAD_PAYLOAD_LENGTH` points to its record length field. For a
reference-derived layout, Stage 5a validates its statically located prerequisite
references first; a tuple validates exact layout length before Stage 5c treats
any payload bytes as record-reference slots.

### 13.5 Run-state spans

Stage 1 first rejects a run state longer than 466,958 bytes. Stage 9 then uses
these exact rules, in order:

1. Fewer than 11 bytes cannot contain the fixed prefix through `phase` and is
   `CONTENT_BAD_RUN_STATE` at `[EOF,EOF)`; no field candidate is produced from
   a partial field.
2. An unknown phase spans byte `[10,11)`. If the valid phase is
   `PHASE_EXHAUSTED`, a length above 466,955 bytes is
   `CONTENT_LIMIT_EXCEEDED` at `[466955,466956)` before any variable field is
   read. Active and committed states have only the overall Stage 1 cap.
3. Parse the complete layout using its encoded counts without allocating from
   those counts. A missing fixed or variable byte, including a partial event,
   is `CONTENT_BAD_RUN_STATE` at `[EOF,EOF)`. The only variable-framing caps in
   this rule are `buffer_count <= 4096` and
   `committed_response_length <= 8195`; an excess spans that count/length field
   and stops the variable read. Encoded `event_count` is already a `u16` and has
   no additional framing cap. Data after the exact final event spans its first
   trailing byte.
4. After a complete frame with no trailing byte, perform only checks that do
   not require event replay: `state_version`; exact root ID; current-node
   existence/kind; remaining-budget numeric bounds; phase/outcome/buffer/
   committed-response structural compatibility; buffer shape,
   `max_selections`, membership, order, and repetition against the encoded
   current node; committed-response syntax and case/default-derived outcome
   against that node; and `event_count <= root.global_event_budget`. A failure
   spans its exact encoded field; set-buffer order or duplication spans the
   later ID.
5. Replay events in encoded order. An event after exhaustion or terminal
   commit, or an event naming the wrong reached node, spans its two-byte
   `node_id`. An event action that is neither `INVALID_ACTION_SENTINEL` nor a
   canonical callable action spans its exact bad tag, reserved byte, or
   two-byte argument; another action/replay inconsistency spans the complete
   four-byte action. A result mismatch spans the event's one-byte `result`.
6. Only after successful replay, compare the encoded final-state fields with
   the replay state and, when Section 9.2 permits it, the one deterministic
   post-advance state. Scan fields in Section 9.1 layout order while retaining
   every allowed candidate whose prefix still equals the encoding; discard a
   candidate at its first unequal field and reject at the field that discards
   the last candidate. This makes a hybrid pre/post-advance encoding
   unambiguous. Compare current node, both remaining budgets, phase, outcome,
   buffer, committed response, and every redundant count. A differing count or
   length spans its field; equal-length byte data spans its first differing
   byte.

Within a numbered rule, Section 13.1's lowest-start and code-order rules apply.
An event defect in rule 5 therefore wins before any replay-derived final-state
mismatch in rule 6.

## 14. Required conformance evidence

Hand-reviewed conformance evidence must include:

- one genuinely non-chess stream whose surface is not chess-derived, including
  text, all atom classes, scalar/vector, matrix, field schema/tuple, regions,
  both binding classes, opaque data, predicate assertion, feedback, passive
  trace, all three response shapes, all live answer modes, and one four-byte
  root;
- exact projection and action/response/run-state bytes for select, reset,
  invalid action normalization, invalid region, duplicate, over-limit, empty
  and nonempty commit, all three outcomes, immutable committed/exhausted calls,
  advance with and without remaining global budget, and passive replay;
- missing/multiple/nonfinal root, orphan, unknown kind/tag/flag, each typed-
  reference class, tuple/presentation mismatch, region overlap, every invalid
  role/mode row, forbidden external answer data, feedback mismatch, passive
  mismatch, success cycle, node/root budget failure, and multiply-invalid
  precedence;
- strict UTF-8 and multibyte raw spans, truncation at each frame boundary,
  boundary and one-over evidence for every structural cap, the 466,958-byte
  valid run-state maximum, and the 466,955-byte exhausted maximum; and
- dependency/import canaries proving both generic implementations contain no
  chess dependency or chess-derived 8x8 behavior.

Large boundary cases may be deterministic bounded recipes, but expected codes,
spans, bytes, and digests are committed literals. An implementation, external
library, generated string, or opaque semantic payload may not generate its own
expected truth.
