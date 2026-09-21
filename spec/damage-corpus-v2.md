# Revised M2 damage observations v2

This owner defines observations, not outcomes or promotion. The generator
receives the source-built profile8 carrier and exact source-owned diagnostic
profile3 route inputs. It must not call either production decoder, consume an
expected result, or read retained damage manifests. The production decoder
receives only the serialized channel observation and neutral admitted owners.

The D0–D6 meanings, transforms, polarities, seed domains, rejection sampling,
Fisher–Yates procedure and D2/D3 formulas are inherited exactly from
`damage-policy-v1.toml`. Derive every coordinate from the revised geometry,
required closure, slot multiplier and affine placement. D4 covers all Q unit
IDs, and D6 covers the sector×unit Cartesian product. Counts are therefore
16, 4, 256, 128, Q, 21 and 4Q; no historical count or coordinate is an input.
Cases use `Dk-` followed by a six-digit zero-based family ordinal. Sampling
and case order do not depend on a decoder result.

The diagnostic profile3 route is freshly generated from the neutral legacy
EH recipient package builder and `spec/route-data-v0.json` with exact SHA256
`965a3e35ceb4b5a92a7715b3fcde20cc3019f8c9d9efa533abd93b051bb86641`.
The caller supplies that bounded raw source owner; arbitrary supplied route
prefixes and regenerated/retained damage outputs are not substitutes. Its
complete sector0 prefix replaces only that prefix's physical cells, using
donor shell width128 and the revised carrier's side. Build its full source
route at that donor geometry before extracting the complete declared prefix.

D7 first preserves the 408 v1 operator positions and their exact order.
Replace v7 by v8 for the active carrier, inventory, grouping and physical
placement. The foreign route remains the source-built profile3 route. Its
27714-byte prefix cannot fit a W112 sector (26992 bytes); ordinal10 therefore
uses the explicit donor width128 above, with its own observed sector scan.
Only those prefix cells change. Some are revised interior cells, so this case
does not promise an unchanged interior. The complete valid foreign route
and unchanged correct-recovery-or-explicit-failure/zero-wrong-accept guarantee
are retained. Do not truncate the prefix, drop the case or enlarge a ceiling.
This is the sole replacement of the inherited D7 physical mutation geometry.
The
five original splices remain profiles2..6. Resource mutants change the same
package header fields in the first sector's compact package, preserving all
lengths. The geometry case remains side2056. Existing transform, check,
coding, replica-conflict and one-beyond meanings are unchanged.

Append these explicit versioned cases, in the order below:

| Ordinals | Operator | Exact order and target |
|---|---|---|
| 408..413 | compact-wire-mutants | package wire version0, package reserved byte48=1, declared byte length minus1, first node opcode0, first node type0, first recipe declared steps plus1. Apply the same mutation independently in all four route packages; all other prefix and physical bytes remain unchanged. |
| 414 | foreign-profile7-bootstrap | replace IDs1..5 with the first clean common block reauthored under profile7 and re-encoded with EH. The inventory remains version2 and cannot establish profile7 or8. |

These additional boundary KATs deliberately reauthor checked envelopes. They
are separate from accidental damage: successful transport verification of
their changed envelope is not a wrong acceptance. No D0–D7 wrong-accept
definition or threshold changes. The boundary admission compares exact
diagnostics and requires invalid semantic content to remain unavailable.
Use IDs `B0-000000` through `B0-000020`, in this order:

| Ordinals | Operator | Exact order and target |
|---|---|---|
| 0..13 | compressed-body-mutants | required then all-only; lowest numeric compressed body of that closure. For each target: unknown codec2; declared decoded length16385; zero decoded length with trailing source; first token backward-reference before output; one-literal output with nonzero unused flag bits; one-literal output with trailing data; first copy length18 against decoded limit1. Preserve the original stored payload length, filling the explicitly synthetic suffix with zero bytes, and recompute the section and every local check/EH lane. Inventory shape and physical grouping remain unchanged. |
| 14..19 | checked-tier-control-mutants | tier2 then tier3; each: terminal ROOT entry0; terminal ROOT budget0; assembled stream byte length plus1. Change only the named field and recompute the section and local checks/EH lanes. All stored lengths remain unchanged. |
| 20 | square-inventory-undercoverage | subtract157 from the lowest numeric load section payload length declared in inventory2, keeping the inventory byte length and all other entries unchanged; recompute all inventory section/local checks and fivefold lanes; replace those lanes at their actual matrix cells. Observed Q is unchanged. |

For the synthetic compressed cases, require the target stored length at least6;
the last five forms begin respectively `03 00 00`,
`03 00 03 80 00 00`, `03 00 01 01 00`, `03 00 01 00 00`,
`03 00 01 80 00 0f`, followed by zeros to the unchanged stored length.
The unknown-codec and too-large decoded-length forms retain the rest of the
original payload. Framing and successful transport integrity do not establish
valid decoded content. Required failure must expose neither stream; an
all-only failure may retain independently valid required content. Exact
section diagnostics and resource outcomes must be independently derived.

D7 count is415. Total damage count is840+5Q; the current Q1908 gives10380.
The21 boundary KATs are counted separately and all are required.
This arithmetic is an operator inventory, not a successful corpus run.
All observations are generated lazily, one bounded byte string at a time.
Unknown family/ordinal, bool-as-integer, malformed carrier or inconsistent
source-built physical units reject. No case may silently disappear when its
required target is missing: that is a corpus-construction failure.

Parameter projections retain v1 rows for positions0..407. Added cases use
`case_ordinal:u64`; compressed and tier cases also use `section_id:u64`;
foreign7 uses `source_profile_version:u64` and `target_unit_ids:u64-list`;
undercoverage uses `section_id:u64` and `removed_payload_bytes:u64`.
The added parameter `case_ordinal` is the mutation index within each named
section target: 0..6 for compressed bodies and 0..2 for tiers. Their section_id
distinguishes repeated indices. The top-level `case_ordinal` remains the full
family ordinal (D7 0..414, B0 0..20). Undercoverage uses `OBS_BITS`; all other
B0 cases use `OBS_UNITS`.
The canonical observation identity has exactly `schema`, `case_id`,
`family_id`, `case_ordinal`, `channel`, `operator`, `parameter_projection`,
`observation_bytes`, `observation_sha256`. Schema is
`golden-board.damage-observation/v2`; `parameter_projection` is an array of
objects with exactly `id`, `value_type`, `value`, sorted by ASCII id. Values
retain the inherited integer/string/array forms. No result or source digest
is invented in this row; enclosing evidence binds source owners separately.
No manifest includes itself.
Semantic-definition ablations and VM/native equivalence are separate named
proofs; their outcomes must not be counted as accidental-damage cases here.
The fixed donor width128 is part of ordinal10's operator, not an extra
parameter field; its inherited `alternate_profile_version=3` row is retained.
