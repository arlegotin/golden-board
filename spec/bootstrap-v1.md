# Golden Board R3 bootstrap delta v1

| Field | Value |
|---|---|
| Status authority | `spec/m2-r3-owner-promotion-v1.toml`; this delta is usable for implementation while blocked and becomes pre-result frozen only through that record |
| Base owner | archived `bootstrap-v0.md`, SHA-256 `82c25776871ac48184d5a7f15663bcc1d192618d66df72ff5fbf3a252aa564c2` |
| Active profile | `eh72-hier-r5-r2-r1-crc32c-v0`, wire profile version 7 |
| Route-data target | `spec/route-data-v1.json`; admissible only when the promotion record binds independently reproduced bytes |

## 1. Scope, inheritance, and promotion barrier

This file is the exact R3 delta over the hash-bound base owner copied at
`artifacts/history/m2-r2-candidates/owners/bootstrap-v0.md`. The base's raw
observation, transform/polarity, shell-sector, recipe-machine, 191-byte common
block, semantic-envelope, tier-frame, content-stream, CRC32C, and EH72 rules
are inherited byte-for-byte except where Sections 2--8 below replace them.
There is no textual fallback to the mutable live `spec/bootstrap-v0.md`.

The delta is implementation authority for pre-result R3 work and becomes a
promoted carrier owner only through the promotion record. Promotion requires
one complete canonical
`spec/route-data-v1.json`, byte-identical independently generated route and
recipient-package bytes, and all exact hashes/counts/step/scratch values named
in Section 8. Before that transition no R3 carrier or D0--D7 observation is admissible.
Missing generated values are absent, never zero, an empty string, a wildcard,
or an implementation-selected default.

## 2. Inventory v1

The common block remains exactly 191 bytes and keeps fragment grammar version
0. Every v7 common block has `profile_version=7` and
`semantic_copy_id=0`. Section envelopes retain envelope version 0. The
inventory section has section version 1 and its logical payload begins with
`inventory_version=1`.

The inventory prefix and 20-byte entry layout are unchanged from the base,
with these replacements:

- every entry byte 10 (`copy_count`) is exactly 1;
- flags bit 0 remains `has_game_ordinal`;
- flags bits 1--3 contain the literal unsigned
  `physical_replica_count`, which is exactly 1, 2, or 5;
- flags bits 4--7 are zero; and
- the flags byte is exactly
  `(physical_replica_count << 1) | has_game_ordinal`.

The factor-5 section IDs are exactly `1,2,3,16`. Section 1 is inventory v1;
sections 2 and 3 are the unchanged tier frames; section 16 is the frozen
required content-body spine member. A factor-5 entry outside that set, or a
non-factor-5 entry inside it, rejects. Every other `replicated-m2` owner has
factor 2 and every `nonreplicated-m2` owner has factor 1. That final class
agreement is checked against the frozen semantic/capacity owner ledger and is
not inferred from an untrusted entry. Any copy count, factor, reserved bit,
game-ordinal encoding, spine membership, owner-class, or closure mismatch
rejects the complete inventory/manifestation.

The route fixes section 1, section/inventory version 1, copy 0, factor 5, and
physical IDs 1--5 as the first fragment group. It does not fix the remaining
catalog. A unique checked inventory must be recovered from consecutive
factor-5 groups before later factors or identities are trusted. Without it,
only IDs 1--5 have route-established replica indices 0--4 and count 5.

## 3. Physical groups and canonical observation values

Logical groups are in `(section_id,fragment_index)` order. If `rho(g)` is the
checked inventory factor, then:

```text
K(g) = sum rho(h) for groups h before g
physical_unit_id(g,r) = K(g) + r + 1,  0 <= r < rho(g)
```

IDs are contiguous and one-based; lanes of one group are contiguous in
replica-index order. `replica_index` is derived metadata and is never present
in a common block. Header grouping occurs only after the physical group has
been aggregated, so a valid divergent header cannot migrate to another
identity bucket.

The bounded product adapter holds at most five 1,728-bit lane observations in
index order `1728*replica_index + encoded_bit`. A value bit whose known bit is
zero is canonically zero. Lanes at an index greater than or equal to the factor
must be absent. For each encoded-bit column the adapter derives exact
`known_zero_count` and `known_one_count` values in replica-index order; it does
not accept caller-supplied counts.

## 4. Repetition and group aggregation

For factor `R` equal to 2 or 5 and one corresponding encoded-bit column, let
`s` be the number of absent or erased lanes. Bit `b` is admissible exactly when
the number `e` of known opposite bits satisfies `2e+s<R`. The sole admissible
bit is emitted; if neither bit is admissible, the output is an erasure. The two
bits cannot both be admissible. REP1 creates no repetition candidate.

For a complete group:

1. each present lane is independently decoded as 24 existing EH72 codewords,
   followed by transport-pad, common-grammar, and local-CRC32C validation;
2. for factor 2 or 5 with at least one present lane, one raw repetition
   observation is constructed over all 1,728 columns and decoded through that
   same 24-codeword and local-validation path;
3. every locally valid lane block and the locally valid repetition block are
   byte-deduplicated; and
4. zero distinct blocks is missing only if no lane was present, otherwise
   corrupt; one is accepted; two or more is conflict.

An accepted block is verified exactly when a present lane with all 1,728 bits
known, no EH correction, a zero transport pad, and valid grammar/local CRC
witnesses the chosen bytes. Otherwise it is recovered. A conflict is a
fragment conflict. It is not voted away and does not by itself create a
complete-section or artifact ambiguity.

The group-state values are `0=missing`, `1=corrupt`, `2=verified`,
`3=recovered`, and `4=conflict`. Per-lane states are `0=absent`, `1=corrupt`,
`2=verified`, and `3=recovered`. Repetition states are `0=not-constructed`,
`1=corrupt`, and `3=recovered`. A valid-shaped product-adapter aggregation,
including a missing, corrupt, or conflicting group, retains its bounded
diagnostics. Shape, factor, ID, or noncanonical erased-value failure rejects
the adapter input. An inner EH status other than 11 makes only that
lane/candidate corrupt; status 11 propagates atomically with no partial
canonical section.

## 5. Two-stage placement

For `(S,W)`, use the exact definitions and smallest-`B` predicate in
`docs/m2-r3-design.md` Section 5. That predicate is incorporated here by
reference as a byte-for-byte normative inclusion of that section from
`I=S-2W` through the fixed-pad inverse rule; changing it requires changing
this owner. In particular, the map is
`affine-slot-then-interior-v1`, the unit-permutation offset is zero, and `B`
is the smallest admissible integer, not a transmitted or implementation-chosen
parameter.

Because admitted `S` and `W` are multiples of eight, `I` is a multiple of
eight and the predicate depends only on `I`. Recipient package table ID 17 is
exactly `UINT[8]` with 256 elements and no flags. At index `j`, set
`I=8*j`, derive `P,Q,w,a`, and store the smallest predicate-satisfying `B`, or
zero if `j` is 0 or 255, `Q<2`, or no `B` exists. The table payload preimage is
the 256 raw element bytes in index order with no header. Both implementations
independently regenerated those bytes before this digest was bound. The map
adapter validates the geometry, requires `I%8=0`, looks up index `I/8`, rejects
a zero result, and then uses the returned `B`. Independently reproduced
canonical payload facts are: SHA-256
`835717bf400c597a3a9e1b59747f23d93047b6cfab462756fa07d96c5f3eba3f`,
236 nonzero entries, 24 distinct nonzero values, maximum 217, and zero indices
`0,1..13,15..18,21,255`. Across all 3,815 admitted `(S,W)` pairs, 3,536
lookups fit and 279 reject. The table is a finite rendering of the exact
smallest search, not a new choice or an observed metric.

The mapping adapter uses interior-local `physical_flat` in `0..I^2-1`.
Forward mapping accepts only `physical_unit_id` in `1..Q` and
`encoded_bit` in `0..1727`. Inverse kind 0 means protected and returns the
unique ID/bit; kind 1 means fixed-pad tail and returns zero ID and zero bit.
Invalid geometry, no admissible `B`, or an out-of-domain argument is status 3.
Checked arithmetic/resource exhaustion is status 11. The non-gating
`S=1952,W=128` KAT fixes `Q=1664`, `B=15`, `B^-1=111`, `a=3391`,
`a^-1=2873023`, and `offset=316417`; it does not select R3 geometry.

## 6. Route/package ABI

Route v1 retains the base recipe-package binary, value types, opcodes,
statuses, static rejection order, record framing, stage order, and sector
record-ID formulas. Its route envelope has `route_version=1`. Recipe IDs are
global within the package. IDs 30 and 101--112 retain their base meanings and
interfaces byte-for-byte. In particular, 30/108 remain the EH72 lane decoder
and encoder, 109 remains the cell-affine mapping primitive, and 110 remains the
fragment-identity primitive. No retained recipe may be reinterpreted. The
exact v7 export order is:

```text
30,101,102,103,104,105,106,107,108,109,110,111,112,113
```

The new interfaces, excluding the automatically encoded leading
`STATUS[16]` result slot, are:

| ID | Name | Inputs | Successful outputs |
|---:|---|---|---|
| 113 | `repetition-symbol-v1` | `UINT[8] factor, UINT[8] known_zero_count, UINT[8] known_one_count` | `BOOL[1] output_known, BOOL[1] output_bit` |

Recipe 113 admits factor 2 or 5 only and requires the checked sum of the two
counts to be at most the factor. If one known count is strictly greater than
the other, it emits `output_known=true` and that count's bit; equal counts emit
`output_known=false, output_bit=false`. An unknown output with bit true is
noncanonical. Invalid parameters return status 3 and checked
arithmetic/resource exhaustion returns status 11. No other new recipe or
table is exported besides recipe 113 and table 17.

The group adapter is an exact bounded composition, not an additional recipe or
a host codec shortcut. In replica-index order it validates lane presence,
mask/value shape, tail absence, IDs, and factor, invokes recipe 30 exactly 24
times for every present lane, and retains each lane's locally valid common
block and state. For factor 2 or 5 it derives the two known counts for each of
the 1,728 columns, invokes recipe 113 exactly once per column to build one raw
value/erasure vector, then invokes recipe 30 exactly 24 times for that vector.
It performs the inherited pad/common/local checks, byte-deduplication, state
classification, and diagnostics in Section 4. It exposes each input lane's
state and locally valid 191-byte block, plus the repetition state/block and the
deduplicated group state/block, to the result adapter. Invalid blocks have no
digest-bearing bytes. Implementations may batch this composition only if the
canonical output and logical recipe invocation/step charge are identical.

The map adapter is likewise exact bounded arithmetic rather than a new recipe.
It validates `(S,W)`, obtains `B` only from table 17, computes or validates
`Q`, performs the Section-5 slot permutation or inverse with checked `u64`
arithmetic, and invokes retained recipe 109 for the cell-affine primitive.
Forward and inverse then enforce every domain, protected-tail, and fixed-pad
rule in Section 5. The assembly adapter uses retained recipe 110 and bounded
inventory/group parsing to derive replica indices and complete fragment
identities. Neither adapter may replace recipe 109 or 110 with candidate bytes,
a coordinate table, an unbounded search, or an implementation-selected map.

Fact 8's exact name and definition value are ASCII
`eh72-hier-repetition-v1`; it consumes facts 6 and 7, uses recipe 113, and
requires support recipes 30 and 108. Fact 9's exact name and definition value
are ASCII `slot-affine-adapter-v1`; it consumes facts 6 and 8, uses retained
recipe 109, and requires table 17. Fact 10's exact name and definition value
are ASCII `group-fragment-adapter-v1`; it consumes facts 7, 8, and 9 and uses
retained recipe 110. Fact IDs, stages, and facts 1--7 and 11--12 otherwise
remain unchanged. Full five-lane/group, mapping/inverse, and inventory
aggregation KATs are direct generated conformance commitments over these exact
adapters; they are not serialized as giant recipe interfaces in route WORKED
or HELD_OUT records.

Fact 8 replaces the base's special damaged-codeword WORKED/HELD derivation.
It has empty `mask_input_slots` and uses these exact already-sectorized recipe
113 interface bytes; no sector XOR is applied:

| Sector | WORKED input | WORKED output | HELD input | HELD output |
|---:|---|---|---|---|
| 0 | `050302` | `00000100` | `050203` | `00000101` |
| 1 | `020100` | `00000100` | `020001` | `00000101` |
| 2 | `050100` | `00000100` | `050001` | `00000101` |
| 3 | `020101` | `00000000` | `050202` | `00000000` |

In every output the first two bytes are success status 0, followed by the
one-byte canonical BOOL values `output_known` and `output_bit`. The eight
inputs are pairwise distinct. Fact 9 retains the recipe-109 interface,
mask-input slot 1, and base inputs `0000000008000080` and
`0001e24008000080`; before sector masking their v7 outputs are respectively
`00000004d401` and `0000002971c1`. Fact 10 retains the recipe-110 interface,
mask-input slots 1 and 2, WORKED input/output
`000000010000`/`0000000000010000`, and HELD input/output
`010203040506`/`0000010203040506`. Facts other than 8 use the inherited sector
mask and output-recomputation rule.

The fixed WORKED-plus-HELD record charge for facts 8--10 is exactly 190 bytes
per sector: 54 for recipe 113, 68 for recipe 109, and 68 for recipe 110,
including both 8-byte record headers, both 12-byte example payload headers,
all inputs, and the status-prefixed outputs. The corresponding v0 charge was
222 bytes. Their three DEFINE values shrink by another 15 bytes. Table 17 adds
272 bytes to the package and one separately framed route TABLE record of 280
bytes. At `S=2048,W=128`, the exact headroom equation admits at most 29,257
route-prefix bytes per sector; the archived EH-CRC32 route used 27,714.
Consequently recipe 113 may encode to at most 1,038 bytes if this geometry is
to remain possible: `29,257 - 27,714 - 272 - 280 + 32 + 15 = 1,038`.
This is a pre-generation upper bound, not a claim that the recipe or complete
package fits; exact v7 bytes and the recomputed complete four-sector prefixes
remain a hard barrier.

## 7. Required route KAT semantics

The route-data owner must carry disjoint worked and held-out examples for each
fact and exact direct KAT rows for the new exports. Literal bytes are generated
only after both implementations agree, but these case IDs and outcomes are
already fixed:

- `rep2-one-known`, `rep2-disagree-erases`, `rep5-two-opposite`,
  `rep5-three-opposite`, `rep5-four-erased-one-known`, and
  `rep5-all-erased` exercise `2e+s=R-1` and `2e+s=R` boundaries;
- `factor-1-no-repetition`, `factor-2`, and `factor-5` exercise complete group
  construction;
- every missing-lane count 0 through 5 appears where its factor admits it;
- `valid-lane-versus-valid-repetition-conflict` returns group state 4 and both
  distinct diagnostic blocks;
- every permutation of serialized group arrival produces the same
  replica-index-ordered output;
- wrong factor, factor-tail presence, duplicate physical ID, missing
  in-range ID, nonzero erased value, common-header/group mismatch, and
  inventory reserved/copy/spine/class mutants reject at their owning layer;
- forward/inverse cases cover unit zero boundary (ID 1), ID `Q`, encoded bits
  0 and 1727, cell-affine wrap, the last protected cell, and the first fixed
  pad cell; and
- exact invocation count, primitive steps, scratch, and each boundary-plus-one
  case are bound after package generation.

The group-conflict KAT is not a damage result. The separate complete-section
KAT supplies two nonidentical structurally complete check-valid envelopes and
requires section/artifact ambiguity under the inherited taxonomy.

## 8. Route-data v1 schema and missing generated fields

The future canonical JSON has schema `golden-board.route-data/v1`, route
version 1, and rejects unknown keys. Its top-level keys, in canonical-manifest
order, are exactly:

```text
calibration_hex, discriminator_cells, examples, facts, generated,
profiles, recipe_export_ids, route_version, schema,
sector_capacity_bytes, sector_masks_hex, shell_width, side
```

`profiles` is ordered v7, v2, v3, v4, v5, v6. Only v7 has
`candidate=true`; the others have `candidate=false` and `fixture=true`.
Every profile row has exactly the v0 four identity fields plus those two
booleans. The v1 fact graph, examples, routes, and package are generated only
for v7. The five fixture rows select their exact archived v0 route-data and
recipient-package bindings from the base/damage owners; they do not request a
second v1 route or reinterpret a v1 fact.

`facts` retains the v0 row/definition shapes and order. Rows 1--7 and 11--12
are byte-identical to v0. Rows 8--10 use the names, consumes, recipes, stages,
and ASCII definitions in Section 6. `examples` has exactly the keys `common`,
`mapping`, `owner_fixture`, `section_check`, and `transport`. `common` retains
the v0 rows for facts 1--7, 10, and 12; `mapping` contains only the v7 fact-9
row; `section_check` contains only the inherited CRC32C fact-11 row; and
`owner_fixture` is exactly an object with `path`, `schema`, and `sha256` for
`conformance/m2-r3-owner-v1.json`. `transport` contains only one v7 fact-8 row
with keys, in canonical JSON ordering:

```text
fact_id, held_sector_inputs_hex, held_sector_outputs_hex, inputs,
mask_input_slots, outputs, profile_version, recipe_id, support_recipe_ids,
transport_id, worked_sector_inputs_hex, worked_sector_outputs_hex
```

Its profile version is 7, recipe ID is 113, support IDs are `[30,108]`, and
transport ID is `eh72-hier-repetition-v0`. Its three inputs are count-one
UINT width 8; its two non-status outputs are count-one BOOL width 1; its mask
list is empty; and its four-element sector arrays are exactly the Section-6
table in sector order. No `worked_input_hex`, `held_input_hex`, source-message,
damage-offset, or sector-mask-derived field is admitted in that row.

`generated` is a closed object. Its keys are exactly, in canonical-manifest
ordering:

```text
capacity_projection, first_fit, held_out_record_bytes_by_sector,
malformed_corpus_case_count, malformed_corpus_sha256,
python_reproduction_sha256, recipe_resource_rows,
recipient_package_bytes, recipient_package_edge_count,
recipient_package_node_count, recipient_package_peak_scratch_bytes,
recipient_package_primitive_steps, recipient_package_sha256,
recipient_package_table_payload_bytes, reproduction_projection_sha256,
route_data_template_sha256, route_example_peak_scratch_bytes_by_sector,
route_example_primitive_steps_by_sector, route_headroom_cells_by_sector,
route_prefix_cells_by_sector, route_prefix_sha256_by_sector, route_sha256,
rust_reproduction_sha256, slot_multiplier_table_sha256,
worked_record_bytes_by_sector
```

Every digest is exactly 64 lowercase hexadecimal characters. Every number is
a canonical-manifest unsigned integer derived with checked `u64` arithmetic.
Every `*_by_sector` value is an array of exactly four items in sector order
0,1,2,3. `recipient_package_primitive_steps` is the package header's exact
derived maximum recipe-step value; it is not a sum. The four route-example
step values each sum every WORKED and HELD_OUT recipe invocation charged in
that sector, without caching or short-circuiting, and the corresponding peak
scratch value is the maximum scratch of any invoked recipe. Worked and
held-out record-byte counts include their eight-byte route record headers and
complete payloads. `recipe_resource_rows` is ordered by recipe ID
`30,109,110,113`; each row has exactly the keys
`encoded_bytes,node_count,peak_scratch_bytes,primitive_steps,recipe_id`.

`capacity_projection` has exactly these keys:

```text
cell_inverse_multiplier, cell_multiplier, cell_offset,
encoded_transport_bytes, factor_1_group_count, factor_2_group_count,
factor_5_group_count, fixed_logical_group_count, fixed_pad_cells,
interior_side, inventory_dependency_count, inventory_entry_count,
inventory_fragment_count, inventory_payload_bytes, load_fragment_counts,
load_payload_bytes, logical_group_count, mandatory_physical_unit_count,
physical_unit_count, population, protected_cells, separation_window,
slot_inverse_multiplier, slot_multiplier
```

The two load arrays have the same length, are in ascending generated load
section-ID order, and each pair is the exact fragment count and payload bytes
for that section. Load section IDs remain derivable by the inherited
contiguous-after-reserve rule and are not repeated here. The following
equalities are mandatory, not merely receipt assertions:

```text
fixed_logical_group_count + sum(load_fragment_counts) = logical_group_count
factor_1_group_count + factor_2_group_count + factor_5_group_count
    = logical_group_count
factor_1_group_count + 2*factor_2_group_count + 5*factor_5_group_count
    = physical_unit_count
mandatory_physical_unit_count + sum(load_fragment_counts)
    = physical_unit_count
encoded_transport_bytes = 216*physical_unit_count
protected_cells = 1728*physical_unit_count
fixed_pad_cells = population - protected_cells
```

Every inventory count and load payload is independently recomputed through
the Section-2 inventory grammar and the inherited exact load fixed point.
Neither implementation may obtain these fields from the other implementation,
the final route-data file, or a carrier result.

`first_fit` has exactly the keys
`examined_pair_count,predecessor_reason,predecessor_shell_width,predecessor_side,selected_pair_ordinal,total_pair_count`.
The two ordinal/count fields are one-based and equal. `total_pair_count` is the
complete admitted Section-5 `(S,W)` enumeration count. The predecessor is the
pair immediately before the selected pair in that order and its reason is one
of `no-admissible-map`, `mandatory-units-do-not-fit`,
`route-shell-capacity`, or `load-fixed-point`. Every earlier pair is actually
evaluated with failure precedence in that listed order; recording only the
last rejection does not permit an implementation to skip the earlier pairs.
The selected pair must be the first pair having none of those failures and
must equal the top-level `side,shell_width`.

`route_prefix_sha256_by_sector` hashes each complete raw route prefix beginning
with its 32 calibration bytes and ending with its END record. `route_sha256`
hashes the raw concatenation of those four complete prefix byte strings in
sector order, with no count, length, separator, or JSON framing. Route-prefix
cell counts equal eight times the corresponding raw prefix byte length.
`recipient_package_sha256` hashes the complete raw recipe-package bytes.
`slot_multiplier_table_sha256` hashes only the 256 raw table-17 payload bytes,
without its 16-byte package/route table header, and must equal the Section-5
owner digest.

The noncircular route template is the complete canonical route-data object
with the selected top-level geometry and with `generated` replaced by the
empty object `{}`. `route_data_template_sha256` hashes exactly the canonical
manifest serialization of that object, including the serializer's one final
LF byte. It never hashes the final route-data object. The reproduction
projection is the complete final `generated` object with exactly
`python_reproduction_sha256`, `rust_reproduction_sha256`, and
`reproduction_projection_sha256` omitted. Canonically serialize that
projection as a top-level object, including its one final LF, and bind its
SHA-256 as `reproduction_projection_sha256`.

Each implementation then emits one canonical reproduction receipt having
exactly these keys:

```text
implementation_id, recipient_package_sha256,
reproduction_projection_sha256, route_data_template_sha256, route_sha256,
schema
```

`schema` is exactly `golden-board.m2-r3-route-reproduction/v1` and
`implementation_id` is exactly `python` or `rust`. The other five values are
copied from independently derived values in the common projection. The
corresponding `*_reproduction_sha256` hashes the receipt's complete canonical
manifest serialization including its one final LF. A receipt contains neither
its own digest nor a digest of the final route-data JSON. The two receipts must
differ. Admission independently recomputes the projection and the
template/package/route digests, compares them with every receipt field, and
only then accepts the receipt digest.

The malformed corpus is also noncircular. Start every row from the complete
clean sector-0 prefix and apply only the named size-preserving mutation; no
length, count, checksum, or other byte is repaired. Route offsets below are
zero-based from the start of the 32-byte route envelope after calibration.
Records are located by their canonical sector-0 record IDs and package
structures are located by the inherited binary grammar. The eight cases, in
this exact order, are:

1. `route-version-zero`: replace route-envelope bytes 8--9 with `0000`.
2. `profile-version-three`: replace route-envelope bytes 12--13 with `0003`.
3. `fact8-definition-v0`: in DEFINE record ID 801, replace the final value
   byte `31` with `30`.
4. `fact8-worked-recipe30`: in WORKED record ID 802, replace its payload
   recipe-ID bytes 2--3 with `001e`.
5. `route-table17-index223-xor01`: in route TABLE record ID 5010, XOR raw
   table-payload byte 223 with `01`.
6. `both-table17-index255-one`: set raw table-payload byte 255 to `01` in both
   route TABLE record ID 5010 and the table-17 record inside RECIPE record ID
   6001.
7. `package-recipe113-id114`: in the recipe-package payload of RECIPE record
   ID 6001, replace recipe 113's header ID with `0072`.
8. `package-recipe113-input0-width7`: in that package's recipe 113, replace
   the first input descriptor's width field with `00000007`.

Every case must be rejected atomically by v1 route admission. The corpus value
has exactly the top-level keys `clean_sector_sha256,rows,schema`, where schema
is `golden-board.m2-r3-route-malformed-corpus/v1` and
`clean_sector_sha256` is the sector-0 member of
`route_prefix_sha256_by_sector`. Each row has exactly
`case_id,expected_result,mutant_bytes,mutant_sha256,sector_id`; sector ID is
zero, `expected_result` is `reject`, `mutant_bytes` is the unchanged clean
prefix byte length, and `mutant_sha256` hashes the complete raw mutant.
`malformed_corpus_sha256` hashes the canonical serialization of that complete
corpus value including its one final LF, and
`malformed_corpus_case_count` is exactly eight.

No `spec/route-data-v1.json` is valid while any generated key is absent,
unknown, empty, inconsistent, zero merely as a sentinel, or supported by only
one implementation. Named admission mutants remove one generated key, add one
unknown generated key, shorten one sector array to three elements, replace a
nonzero numeric value with zero, flip each projection/receipt digest in turn,
make the two receipt digests equal, and inject each malformed-corpus member;
every one rejects. The owner-promotion manifest, profile policy, generated
limits, and damage policy must bind the same final route and package digests
before their status can become `pre-result-frozen`.
