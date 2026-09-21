# Revised M2 required-stream runner v1

This development owner adds explicit admission of the revised required stream.
It changes neither runner-v0 nor content-v0, the 65 learner pages, historical
entry points, or Gate-8 lifecycle. A development bundle and passing tests are
not a qualifying release or evidence of recipient success.

## Admission and participant behavior

`golden_board.m2_runner_v1.m2_runner_v1(raw, label_suppressed=bool)` accepts
immutable bytes with exactly this identity:

```text
length 42432
sha256 141168a051b44f978667f7c562070300d79368ace3fee47f5d19082de7642c17
root ID 588
```

Check type and length before hashing. Construct the existing GenericRunner,
which performs complete content-v0 validation, then verify ROOT. Suppression
must be an exact Boolean. Import no chess, compiler, transport, owner answers,
or evidence. Use the supplied bytes; never replace them from local sources.
The historical `m2_runner()` still accepts only its original13644-byte all
stream. Neither entry accepts the other's stream or the revised all stream.

Frames, actions, budgets and label suppression retain runner-v0 semantics.
Final external nodes contain no answer cases/predicate and return neutral
outcomes for either selection. Artifact-carried worked examples remain visible;
owner scoring and final answers remain outside the recipient runtime.

## Explicit standalone entry

`tools/m2/learner_runner_v1.py` supplies `StandaloneRunner`, `run_commands`,
and a CLI with `--content-stream`, `--commands`, `--label-suppressed`. It uses
only the standard library and unchanged sibling `learner_runner.py` generic
payload/runtime primitives. A separate constructor admits the revised exact
identity and terminal ROOT. Never modify the sibling's constants or admission.
Its parser is an allowlist for reviewed exact bytes, not a universal validator.

Commands keep schema `golden-board.learner-runner-commands/v0`, exact root keys
`schema,commands`, and one-key rows `action_hex` (eight lowercase hex digits)
or `advance:true`. Reject duplicate keys, malformed JSON/UTF-8, excessive
nesting, other types/keys, and unavailable operations. CLI inputs use the
historical regular-file reader with its bounded reads and file identity checks.

The new transcript schema is `golden-board.learner-runner-transcript/v1`, with
exact keys `content_stream_sha256,final_frame,results,schema`. Return the final
participant frame and one action-result integer or `advanced` per command.
The final frame contains the complete event sequence. Avoid repeating that
growing sequence in a snapshot for every command. Object API frames and CLI
command prefixes still permit inspection at any point. Serialize compact,
sorted-key UTF-8 JSON with a final LF; emit nothing on failure.

## Bounds derived from the source

Let G be ROOT's global event budget4160. Every action consumes one event;
advance consumes none but can occur at most once after a consumed commit.
Thus at most G actions, G advances and2G=8320 commands are possible, including
sustained rejection loops. Per-node budget16 remains unchanged. These bounds
come from the stream, not an increased generic content limit. Historical
command/output limits256 and1MiB remain unchanged.

For command input, calculate the byte length of the canonical command envelope
containing G action rows and G advance rows, plus LF. Action rows have fixed
eight-character payloads. This admits every canonical executable command list;
noncanonical whitespace also fits when the same total byte bound permits it.
Count both operation kinds before execution and reject either count above G.

Derive output allocation from actual source presentation graphs, not a chosen
power-of-two allowance. Enumerate each of the65 nodes' participant-frame
shapes with an empty event list: active with empty or each singleton selection;
committed for every case and default feedback/next pair; exhausted with empty
or singleton selection. Use the maximum-width admitted global/local budget
values, the longer Boolean spelling where necessary, and the longest legal
response shape. Take F as the largest compact serialized frame size in either
suppression mode. Let E be the longest serialized event row over actual node
IDs, eight-character action bytes, and one-digit result codes. Let H be the
serialized output wrapper with empty final-frame object and empty results,
including LF, minus the two bytes of that object.

An empty event array already counted in F grows by at most `G*(E+1)-1`.
The empty results array already counted in H grows by at most `13*G-1`:
G one-character action results, G ten-character quoted `advanced` values,
and2G-1 commas. The output bound is exactly
`H + F + G*(E+1)-1 + 13*G-1`. Bounds are conservative across mutually exclusive
dynamic states; they do not invent an executable state or count as a lesson
outcome. Use checked unsigned32 arithmetic and reject inconsistent source
counts/shapes before deriving limits. Check final output before writing.

For the admitted source, the measured derivation gives F=14878, E=50, H=174,
command input178946 bytes and output281290 bytes. An executable witness uses
empty commits through the worked prefix, then repeated default rejection at
the first practice node:4160 commit/advance pairs consume8320 commands and
exactly178946 canonical input bytes including LF, ending exhausted with4160
events. Its final transcript is270372 bytes. No command-count slack was added;
the output bound conservatively covers every node's larger display graph.

## Packaging and recovery boundary

`tools/m2/package_learner_v1.py` admits its caller's exact required bytes through
the new factory and packages those same bytes. It must not regenerate them
from authoring. Observation recovery/provenance belongs to the calling decoder;
byte identity alone establishes neither stream availability nor release status.

The recipient kit contains exactly `READ-ME.txt`, `index.html`, `layout.js`,
`ui.js`, `viewer.js`, `lesson-data.js`, `lesson.content-v0.bin`,
`learner_runner.py`, and `learner_runner_v1.py`. The README directs optional
CLI use to the revised entry. The browser and its explicit prototype session
schemas remain unchanged. No scoring, owner pages, final answers, chess
fixtures, carrier reference, or network dependency is included.

Keep sorted archive entries, stored compression, fixed1980 timestamp,0644
regular-file mode and the `golden-board-learner/` directory. Test every revised
page against GenericRunner in both modes, including opposite final selections,
retry/reset/exhaustion, and old admission rejection. Execute the copied runner
under Python isolation in a directory containing only recipient files. These
checks do not write a Gate-8 receipt or promote the prototype bundle.
