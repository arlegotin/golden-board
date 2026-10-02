# Revised receiver boundary checks

The participant revision retains the four extra D7 boundary checks in
damage-policy-v1's boundary_kat table. They are fresh executions through the
v2 repetition and section-check boundaries, outside D0–D7 and B0; they add no
damage cases and do not change any recovery promise. Historical KAT receipts
cannot establish these results.

The exact order is rep2-correction-boundary, rep5-correction-boundary,
complete-section-conflict, section-attempt-ceiling-plus-one. Each independent
Python/Rust implementation builds its own fixtures, asserts the semantics below,
and emits canonical-manifest-v0 bytes with exactly schema
`golden-board.m2-boundary-kat-result/v2`, kat_id and result (`pass` or `fail`).
Converged failures remain losing evidence. Invalid caller ordinals/types reject;
they do not select a default check. No saved result is a fixture input.

For repetition factors2 and5, exercise both the direct repetition symbol and
the actual profile8 product adapter at respectively2e+s=1/2 and4/5. At the
strictly correctable boundary the exact common block must be recovered; at
equality to the factor the candidate must not be accepted. Use fresh profile8
fragments and transport encoding. The product fixtures include one intact lane
and the remaining erased lanes at the correctable boundary; conflicting masked
lanes plus erasures exercise the rejection boundary. A direct symbol assertion
alone is insufficient.

The section conflict fixture contains two distinct complete, structurally
valid, check-valid envelopes for the same section identity. Both must reach
the actual section-check/recovery boundary. Their section state and resulting
artifact state must be ambiguous, with no selected canonical section or tier
stream. Neither semantic plausibility nor insertion order breaks the tie.

The attempt fixture has4097 distinct, deduplicated, structurally complete
envelopes for one section identity, sorted by their complete raw byte strings.
Candidates1 through4096 reach stored-check comparison. Candidate4097 is
rejected resource-limit before comparison, retaining the4096 completed
attempts and all earlier logical charges. Repeated identical envelopes do not
consume another attempt. Global failure clears canonical section, stream,
profile and hypothesis output under resource-accounting-v2. The fixture must
observe the reached comparison count, not infer it solely from an exception.
Fixtures spread across different section IDs do not satisfy this check.

These are bounded pure fixture producers. They may use the receiver's internal
section boundary with a fresh meter; they must not add evaluator/fixture inputs
to the observation-only decoder IPC. Keep any export command separate from
that IPC. The complete revised damage manifest binds all four ordered receipts
from both implementations, independently of its corpus counts and row hash.
