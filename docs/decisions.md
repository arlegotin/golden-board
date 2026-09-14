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
