# M2 runner-v0

Status: normative owner for the candidate-neutral M2 generic runner and its
automated semantic-path evidence.

This owner is deliberately small. It does not define content-v0 bytes, chess
meaning, transport verification, participant scoring, or a general user
interface. `spec/content-v0.md` remains the owner of accepted streams and
runtime transitions; `spec/slice-v0.md` remains the owner of the exact M2
content streams.

## 1. Accepted input and boundary

The generic runner accepts a `bytes` value only through content-v0
`stream_validation`. It drives the returned projection only through
`new_run`, `step`, and `advance_committed`. It obtains all record and state
information used for presentation or evidence through `projection_view` and
`run_state_view`; it does not inspect private projection/state fields or decode
run-state bytes.

The M2-bound entry additionally requires the exact `m2_all` stream:

```text
length  = 13644
sha256  = de7e22f0aa4316d9f32d9435287dd19bd6c04519aae1dc9bd816613f26929671
root ID = 182
```

An otherwise valid content-v0 stream with another identity is valid generic
runner input but is not M2 evidence. Identity failure occurs before a runner
escapes.

## 2. Participant view

A frame is an immutable projection of the current public content/run views. It
contains the current node, budgets, phase/outcome, selection buffer, exact
committed response bytes, feedback and next-node values, available canonical
actions, whether advancing is possible, the presentation graph, region
geometry, optional passive demonstration, and optional feedback display.

Display graphs are bounded DAG projections. Each reachable display record is
emitted at most once in ascending record-ID order. They expose only:

- `TEXT`: its UTF-8 bytes in ordinary mode and no text value in suppressed
  mode;
- atom vectors: atom class/width/range-or-mask/entries and exact atoms;
- matrices: the same atom schema, dimensions, and row-major cells;
- tuples: exact field storage/type/count and values, plus field-name text only
  in ordinary mode; and
- opaque data: its numeric values without its semantic-binding identifier.

Region views expose the selectable handle, rectangle, flags, and optional
label text. A zero label stays absent. Passive views expose only the
artifact-carried presentation/regions/resulting presentation, optional
limitation text, and canonical demonstration actions. They do not expose the
passive record's expected outcome, expected feedback, or expected next node.

Internal semantic-binding and predicate identifiers are not participant
labels. Evaluator evidence is a separate immutable value.

For an active state, available actions are, in order: selectable region actions
in region order that are valid under the current selection count/duplicate
rule, reset, then commit. A committed or exhausted state has no content action;
`can_advance` is true only for a committed state with a nonzero next node.

## 3. Label suppression and bounds

Mode is fixed when a runner is created and cannot change during a run.
Suppressed mode returns no `TEXT` bytes anywhere in the presentation, tuple
field names, region labels, passive limitation, or feedback display. It never
replaces them with record IDs, binding IDs, transliteration, code points,
Unicode names, or glyph-dependent tokens. Numeric atoms, dimensions,
coordinates, structural references, action handles, and neutral interface
mechanics remain.

Changing mode affects presentation only. With the same accepted bytes and
actions, ordinary and suppressed modes must have identical available-action
sequences, content event sequence, outcomes, budgets, committed responses,
feedback/next-node values, and evaluator predicates. Replacing every TEXT
payload with other valid UTF-8 while preserving the content graph must also
leave a suppressed run's frame semantics and event evidence unchanged. Thus
no required suppressed distinction depends on a Unicode code point, font, or
glyph identity.

The runner performs no recursive display expansion. It uses the content-v0
record, tuple-slot, matrix-cell, region, selection, event, stream, and text
bounds and rejects an inconsistent public view rather than returning a partial
frame.

## 4. Evaluator evidence

After each commit, the evaluator-side commitment records:

```text
node_id
committed_response
outcome
feedback_ref
next_node_ref
node_predicate
feedback_predicate
```

A nonzero predicate is resolved through the public projection as the exact
`PREDICATE_RESULT`, its predicate `SEMANTIC_BINDING`, subject `OPAQUE_DATA`
binding reference, and result atom-vector reference. Zero means no predicate.
These values are never included in the participant frame.

The M2 semantic path is exactly these action groups, with
`advance_committed` between groups:

```text
181: 01000002 03000000
 26: 01000001 03000000
 27: 01000003 01000001 03000000
 28: 01000003 01000001 03000000
```

The final ordered event results are `1,3,1,3,1,1,3,1,1,3`. The four committed
responses are, in order:

```text
0100010002
0100010001
02000200010003
03000200030001
```

The respective `(outcome, feedback_ref, next_node_ref)` tuples are
`(3,180,26)`, `(1,21,27)`, `(3,20,28)`, and `(3,24,0)`.

`semantic_path_bytes` is canonical-manifest-v0 JSON with exact root keys
`checkpoints, commitments, content_stream_sha256, events, schema`. Schema is
`golden-board.runner-semantic-path/v0`. Checkpoints include the initial state,
every post-action state, and every post-advance state in chronological order;
each contains available actions, budgets, committed response, current node,
feedback, next node, outcome, phase, and evaluator predicate. Events and
commitments use the fields above. This is an evaluator event-log encoding, not
a content or run-state wire format.

SHA-256 of those exact canonical bytes is `semantic_path_sha256` and binds the
technical-to-learner bridge because `content_stream_sha256` is inside the
preimage. Ordinary and suppressed execution must produce byte-identical
`semantic_path_bytes` and therefore the same digest.

The reviewed v0 evidence is 9,883 bytes with SHA-256
`966e510af60a9a95afc60badee2d985da95add187f7d132bc2009369db33cbd3`.

## 5. Dependency firewall

The runner module may depend only on the generic content and canonical-manifest
owners plus standard-library hashing/value types. It does not import a chess
core, slice compiler, transport module, external rules, game constants, or
evaluator answers. Non-domain canaries with unequal rectangular matrices,
three-valued enums, masks, state transitions, reset/exhaustion, passive traces,
and arbitrary opaque bytes exercise this boundary.
