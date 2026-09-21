# Revised complete damage replay

This is a development evidence projection of the already owned v2 damage
corpus, source oracle, observation receiver and resource accounting. It adds
no damage case, acceptance promise, gate or participant requirement. Promotion
and Gate8 must bind a fresh execution before these bytes can support release.

Generate the carrier and every observation from source. The source oracle may
receive their ownership; production receivers receive only the serialized
channel and observation with the neutral owners. A Python producer compares
its independently derived source semantic projection to its observation-only
Python receiver, without a foreign executable or result as a generation input.
An explicit development comparison mode may additionally compare complete
result/resource bytes with a persistent independent Rust receiver. It must not
be labeled a standalone Python producer. A separate Rust source-oracle producer independently generates
the complete canonical result, resource sidecar and source section states.
Their replay rows must agree byte for byte, including the observation identity.
Never supply a saved row, clean catalog, case ID or expected result to a receiver.

Each canonical row is a closed object with:

- schema: `golden-board.m2-damage-replay-case/v2`;
- observation: the exact `DamageObservationV2.identity()` object owned by
  damage-corpus-v2, including its raw observation hash and byte count;
- decoder_result: the complete canonical result-v2 object;
- resource_projection: the complete canonical observation-resources/v2 object;
- expected_section_states: ascending objects with exactly section_id and state,
  covering every clean candidate section, inserting unknown only for absent
  diagnostic rows as owned by damage-oracle-v2;
- wrong_accept_count: the source oracle's checked u64 raw difference count;
- reauthored_boundary: true exactly for B0, false for D0–D7;
- promise_result: pass or fail, derived below, never a caller-supplied override.

The result channel and sidecar channel must equal the observation channel.
The sidecar binds that observation hash and the raw canonical result bytes,
including their trailing LF. Its counters equal the result counters, its
owners are current, and all closed kernel rows are present. Each result section
has the same state in the complete source section-state projection. Unknown
states supplied by the source catalog cannot establish a visible section.
Use the existing strict canonical result/sidecar admission, not permissive JSON.

Preserve the existing accidental promises. D0/D1/D5 pass only when every
declared section is verified or recovered. D2/D3/D4/D6 pass only when every
required closure section is verified or recovered; the revised closure is
1,2,3,16,17,18. Every accidental case additionally requires zero wrong accepts
and exact source/receiver convergence. D7 retains correct recovery or explicit
failure under that same convergence and zero-wrong-accept requirement. A
converged promise failure is retained as fail, not discarded or rewritten.
The21 deliberately reauthenticated B0 probes remain separate: exact source
semantic and full-result convergence is required, but their changed checked
section count remains diagnostic and is not an accidental wrong-accept total.

Rows are ordered D0 through D7, then B0, each by ascending zero-based ordinal.
Counts are freshly derived from the source corpus. A partial selected replay
names its exact ordered case IDs and is never described as a complete corpus.
No duplicate, missing, reordered or extra row is admissible. Repeated warm
execution must produce the same bytes; worker count cannot affect row order.

Development exporters may stream these canonical LF-terminated rows as JSONL.
Each row is at most1048576 bytes; readers bound each line before parsing.
Keep at most twice the declared worker count pending, with at most8 workers.
Only source factories and immutable neutral owners initialize workers; actual
observations are generated in the evaluator and passed by channel/bytes to
the production receiver. A mismatch is a failed replay, with private bounded
diagnostics permitted; it cannot publish a success summary. Completion also
requires unchanged source preimages and all child processes reaped.
Bind the actual Python executable before/after Python replay and, in the
explicit comparison mode, the immutable Rust executable too. Python-only mode
accepts no Rust executable argument and launches no Rust child. Full production
admission separately requires the complete independent Rust reproduction.

The complete resource-limits projection is computed from the exact ordered
sidecars using resource-accounting-v2's existing aggregator. Its corpus hash
is SHA-256 of the concatenated canonical observation identity rows, each with
one trailing LF. B0 is included in resource maxima but not accidental damage
counts. A replay's row-stream hash is SHA-256 of its exact concatenated rows;
neither file includes its own hash in its preimage.
