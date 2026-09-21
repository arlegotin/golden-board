# Golden Board decisions

## 2026-08-21 — M2 R3 uses hierarchical physical repetition

No R2 candidate survived through gate 6, so the roadmap's predeclared revision path
was reached. R3 selects one new, not-yet-run profile:
`eh72-hier-r5-r2-r1-crc32c-v0` (wire profile version 7).

The design keeps one semantic fragment value and separates physical
redundancy from semantic identity. The fixed M2 entry spine uses five physical
lanes, all other replicated Core 0--2 capacity uses two, and nonreplicated
material uses one. This is the smallest direct-replication design found that
both addresses R2's dense required-spine substitutions and honestly charges
the complete future capacity envelope within the unchanged 512 KiB ceiling.
Distinct locally valid lane values conflict; no majority chooses semantic
bytes. A result-free two-stage affine placement separates corresponding lanes.

Pure cross-copy fragment union was rejected because it left every R2 D3
required-population seed failing. Uniform REP5 was rejected because the exact
future replicated-capacity charge cannot fit. RS was not reopened because its
complete recipient recipe had already failed an earlier gate and direct
repetition is earlier in the frozen fallback order.

The exact pre-result contract and restart barrier are in
[`m2-r3-design.md`](m2-r3-design.md). The R1/R2 failures remain evidence. No R3
carrier or D0--D7 result was observed before this decision.

## 2026-09-16 — M2 reopens for the participant-driven revision

The revised teaching, semantic slice and transport change the source of
Gates 1–7 as well as Gate 8. The verifier-only reopen cannot cover this work.
Revision 11 therefore sets M2 In progress and reopens Gates 1–8 without
changing M0/M1 or the 512 KiB carrier ceiling. The exact previous source,
owners, candidate, receipts, report, timeline, acquisition provenance and
original quiz material are archived before authority changes, under
`spec/m2-participant-revision-transition-v1.md`. The historical v7 candidate
is excluded from the revised active set. No new gate result or fresh human
success is asserted; fresh production and affected human evidence remain
pending. The archive is internal provenance, not participant material.
