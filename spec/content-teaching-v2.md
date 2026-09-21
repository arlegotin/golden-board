# Carried content/control miniature v2 — development owner

This supplies a finite mathematical miniature and discriminating consequences
for route fact 12. It does not change content-v0, admit profile 8, replace the
65-page chess slice, add an interpreter, or claim a new human result. Sustained
inference and composition of previously grounded primitives are permitted;
neither familiar names nor an uncarried host validator count as evidence.

## Semantic source and context

The miniature's logical source is the sole `generic-base` entry's
`projection.records` in tracked `conformance/content-v0.json`. Construct its
29 typed records through each implementation's content authoring API. Do not
decode or copy `stream_hex` as the construction input. After independent
encoding, compare to that source's `stream_hex`, length, projection and digest.
The result is exactly 575 bytes, content version 0, ROOT ID 29/entry 26/budget
8, SHA256 `99c783060adb543ef1621b4e17f57772bd88c9d37cb249981aed5f9a4962d7dc`.
Input source is canonical JSON, bounded at 1 MiB. Closed shapes, exact integer
types (no booleans), array counts and source identity are checked before use.

This is context 2, distinct from current required/all contexts 0/1. Record
IDs in the miniature never refer into the actual slice. Its English TEXT
labels are literal values, not definitions of grammar or chess meaning. It
already contains all 14 record kinds, unsigned/enum/mask schemas, a tuple with
inline atoms and typed record slots, all five feedback codes, packed/external/
heuristic nodes, SINGLE/SET/SEQUENCE, and a tight success budget 2+3+3=8.
The actual slice additionally demonstrates worked-unscored nodes and repeated
real content, local traces, rejection loops and forward accepted edges.

## Framing and exact charge

The fact-12 replacement value is `u32 miniature_bytes || miniature || u32
supplement_bytes || supplement`, all big-endian. The supplement contains the
four blocks below in order, each preceded by its u16 row count. It is exactly
1056 bytes: `4*2 + 48*14 + 6*12 + 4*12 + 8*32`.
The complete framed value is **1639 bytes**. Replacing the former 301-byte
excerpt and 12-byte ROOT costs 1326 bytes; adding `(2,29,29)` as a six-byte
context row makes the net route delta **1332 bytes per sector**. Existing
actual-stream context, framing, reference and namespace bridges remain.

These are finite numeric relationships, not a second bytecode or a production
parser dispatch table. Scalar replacement uses the already grounded indexed
write operation. The owner implementation checks every consequence with the
existing complete content validator/runtime before emitting any value.

## Scalar consequences: 48 rows, 14 bytes each

Each row is `(offset:u16, width:u16, old:u32, new:u32, accepted:u16)`.
Apply exactly one replacement to a fresh miniature; width is 1, 2 or 4 and
values are encoded in that many bytes, big-endian. `old` must match exactly.
The final value is Boolean 0/1 for whole-stream acceptance, not local-record
acceptance or a content rejection-code number. No partial stream is exposed.

| Offset | Width | Old | New | Accepted |
|---:|---:|---:|---:|---:|
| 0 | 2 | 0 | 1 | 0 |
| 2 | 2 | 29 | 28 | 0 |
| 4 | 2 | 1 | 0 | 0 |
| 19 | 2 | 2 | 1 | 0 |
| 563 | 2 | 29 | 65535 | 1 |
| 571 | 2 | 26 | 0 | 0 |
| 571 | 2 | 26 | 27 | 0 |
| 573 | 2 | 8 | 7 | 0 |
| 573 | 2 | 8 | 9 | 1 |
| 573 | 2 | 8 | 65535 | 1 |
| 555 | 2 | 3 | 2 | 0 |
| 555 | 2 | 3 | 4 | 0 |
| 6 | 2 | 1 | 0 | 0 |
| 167 | 2 | 6 | 0 | 0 |
| 167 | 2 | 6 | 12 | 0 |
| 167 | 2 | 6 | 1 | 0 |
| 169 | 2 | 2 | 0 | 0 |
| 178 | 1 | 5 | 6 | 0 |
| 129 | 2 | 2 | 1 | 0 |
| 145 | 1 | 1 | 0 | 0 |
| 158 | 1 | 1 | 0 | 1 |
| 158 | 1 | 1 | 2 | 0 |
| 193 | 2 | 6 | 3 | 0 |
| 223 | 1 | 2 | 3 | 1 |
| 223 | 1 | 2 | 6 | 0 |
| 191 | 1 | 1 | 0 | 0 |
| 224 | 2 | 9 | 1 | 0 |
| 302 | 2 | 1 | 0 | 0 |
| 314 | 1 | 3 | 6 | 0 |
| 329 | 2 | 16 | 6 | 0 |
| 343 | 2 | 17 | 1 | 0 |
| 345 | 2 | 10 | 9 | 0 |
| 359 | 2 | 0 | 19 | 0 |
| 373 | 2 | 19 | 0 | 0 |
| 493 | 2 | 2 | 1 | 0 |
| 456 | 1 | 0 | 1 | 0 |
| 514 | 1 | 0 | 1 | 0 |
| 544 | 1 | 1 | 0 | 1 |
| 439 | 1 | 1 | 2 | 0 |
| 443 | 2 | 27 | 26 | 0 |
| 435 | 4 | 50331648 | 16777217 | 0 |
| 561 | 2 | 0 | 27 | 0 |
| 413 | 2 | 5 | 1 | 0 |
| 192 | 1 | 0 | 1 | 0 |
| 250 | 2 | 1 | 3 | 0 |
| 258 | 2 | 2 | 1 | 0 |
| 545 | 2 | 14 | 12 | 1 |
| 12 | 1 | 83 | 255 | 0 |

The positive ID-gap example preserves the actual generic rule: IDs are
nonzero/increasing, not universally contiguous. The slice declaration may
separately require contiguous authored IDs. ROOT budget 65535 is valid even
though no record of that ID exists in the unchanged miniature; it is a
quantity, not a reference. Changing the entry to 27 or dropping the last use
of TEXT 5 leaves an orphan. The last edge 28→27 creates a success cycle;
ordinary rejected self-edges at 26 remain valid. Local budget 4 is itself
sufficient for node 28, but its new path total 9 exceeds ROOT budget 8.

## Closed role relationships: six rows, 12 bytes each

Fields are `role:u8, mode:u8, predicate_presence_min:u8,
predicate_presence_max:u8, accepted_case_min:u16, case_max:u16,
trace_presence_min:u8, trace_presence_max:u8, default_feedback:u8,
default_outcome:u8`. Presence is 0 for an absent reference and 1 for a present
reference. A present reference must still pass the complete typed checks.
These are the six allowed rows, not permission for combinations outside them.

```text
1 3 1 1 0    0 0 1 1 3
2 3 1 1 0    0 0 1 1 3
3 3 1 1 0    0 1 1 1 3
4 3 0 0 0    0 0 1 5 3
5 1 1 1 1 4096 1 1 3 2
5 2 0 0 0    0 0 0 1 3
```

The packed row's default outcome is rejected. Its accepted case separately
uses MATCH with the node's assertion; special rejection uses ALTERNATIVE and
its assertion. The complete miniature carries all three consequences.
Role checks must use fully typed constructed records with otherwise valid
dependencies, not merely compare these row bytes to themselves.

## Presentation occurrences: four rows, 12 bytes each

Each row is six u16: `(presentation_kind, presentation_id, surface_id,
direct_matrix_occurrences, transitive_matrix_occurrences, accepted)`.
For a direct MATRIX, its own occurrence counts as one. For a TUPLE, count
matrix reference slots/paths, not distinct target IDs.

```text
6 14 12 1 1 1
6 14 12 2 2 0
4 12 12 1 1 1
6 14 12 0 0 0
```

The first row is the miniature. For the second, change the final field of
schema 13 to count two and tuple 14's final field to `(12,12)`, recomputing
framing through the authoring API. For the third, use direct matrix 12 in
node 28. For the fourth, remove that final field from both schema and tuple.
The complete content validator, including presentation/region linkage,
determines the carried acceptance. No invalid variant is installed in the
active content stream.

## Action and budget consequences: eight rows, 32 bytes each

The fields are, in order: `node_id:u16, action_count:u8, actions:12 bytes,
phase:u8, last_result:u8, response_shape:u8, selection_count:u8,
selection_ids:2*u16, outcome:u8, feedback_ref:u16, next_node_ref:u16,
global_remaining:u16, local_remaining:u16`. Unused action bytes and selection
slots are zero. When committed, selections are the canonical committed
response; otherwise they are the current buffer.

Begin a fresh whole-miniature run. To reach node 27, commit empty at 26 and
advance. To reach node 28, also commit empty at 27 and advance. Then apply
only the row's actions. The implicit setup is fixed and bounded, and uses
the actual carried edges; it is not an alternate start-node admission rule.
The following table lists only active action/selection entries.

| Node | Actions (hex, in order) | Phase | Last result | Shape | IDs | Outcome | Feedback | Next | Global | Local |
|---:|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| 26 | 03000000 | 2 | 3 | 1 | empty | 1 | 21 | 27 | 7 | 1 |
| 26 | 01000002 03000000 | 2 | 3 | 1 | 2 | 2 | 23 | 26 | 6 | 0 |
| 26 | 01000003 03000000 | 2 | 3 | 1 | 3 | 2 | 22 | 26 | 6 | 0 |
| 27 | 01000002 01000001 03000000 | 2 | 3 | 2 | 1,2 | 3 | 20 | 28 | 4 | 0 |
| 28 | 01000001 01000001 03000000 | 2 | 3 | 3 | 1,1 | 3 | 24 | 0 | 3 | 0 |
| 28 | 01000002 01000001 03000000 | 2 | 3 | 3 | 2,1 | 3 | 24 | 0 | 3 | 0 |
| 26 | 01000001 01000001 | 3 | 6 | 1 | 1 | 0 | 0 | 0 | 6 | 0 |
| 26 | 02000000 03000000 | 2 | 3 | 1 | empty | 1 | 21 | 27 | 6 | 0 |

These distinguish case/default outcomes, set sorting, sequence ordering and
repetition, duplicate-before-over-limit, exhausted versus committed, reset
without budget replenishment, and successful commit on the final local event.

## Claim and remaining check

These bytes provide actual positive and negative mathematical/control
relationships; they do not require a proof of unique inference from finite
examples. A fresh motivated receiver may inspect, backtrack and compose the
previously grounded primitives. Before promotion, validate the full emitted
material in both languages and run the existing knowledge-use/ablation and
recipient gates on the actual new carrier. The actual required/all streams
still need independent full content-v0 validation and inventory/tier checks.
This miniature alone establishes neither universal receiver conformance nor
chess understanding. Its presence cannot substitute for required lesson
protection, complete source closure, damaged-input isolation or fresh fit.
