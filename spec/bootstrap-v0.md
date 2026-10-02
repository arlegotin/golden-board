# Golden Board bootstrap v0

| Field | Value |
|---|---|
| Status | M2 common framing and P4 recipe/route construction owner; candidate recipe payloads land in P5 |
| Parent contract | [`docs/m2-spec.md`](../docs/m2-spec.md) Sections 6--8 |
| Integer order | big-endian unless a bit traversal is explicitly named |
| Common plain block | exactly 191 bytes |
| Maximum raw observation | 4,194,304 indexed bits |
| Route-data manifest | `spec/route-data-v0.json`, SHA-256 `965a3e35ceb4b5a92a7715b3fcde20cc3019f8c9d9efa533abd93b051bb86641` |

## 1. Scope and promotion boundary

This file owns the candidate-neutral bootstrap facts needed to build the real
M2 semantic input before transport results exist:

- raw square/transform/polarity enumeration;
- four disjoint rotated shell-sector cell sets and traversal formulas;
- the closed recipe value types and candidate-neutral operation vocabulary;
- the exact common 191-byte plain block;
- semantic section, inventory, and tier-frame bytes;
- singular content-v0 stream assembly; and
- candidate-neutral validation and atomicity rules.

Sections 12--16 are P4's pre-result promotion of the exact recipe opcode and
framing table, bootstrap dependency nodes, route record framing, stable recipe
status assignments, and formula-derived instructional-cell placements. P5
installs the candidate recipes and their literal small KAT payloads using only
that closed language. Those later data records cannot add an opcode, widen a
bound, change a route, or alter a profile choice.

`spec/profile-policy-v0.toml` will own exact candidate IDs, ECC/check tuples,
copy alternatives, mapping family, metrics, and selection. This file owns only
the common bytes and shell/recipe language in which those choices are taught.
`spec/damage-policy-v0.toml` will own channels, damage operators, seeds, and
damage promises. `spec/content-v0.md` owns the bytes assembled after transport.

No implementation, fixture, generated carrier, or explanatory external
standard may override this file. All parsers are bounded, reject trailing data,
and return no accepted prefix or partial canonical value.

## 2. Common conventions and bounds

Unsigned integers use the widths shown and big-endian byte order. Additions,
multiplications, offsets, counts, and ceiling divisions use checked arithmetic.
There is no implicit integer wrap, padding, alignment, native-endian field, or
host-sized value.

The candidate-neutral parser safety bounds are:

| Quantity | Inclusive maximum |
|---|---:|
| indexed raw bits | 4,194,304 |
| square side | 2,048 |
| common blocks per semantic-copy section | 65,535 |
| complete semantic envelope bytes | 1,048,576 |
| dependency IDs in one section | 4,095 |
| inventory entries | 4,096 |
| content-body IDs in one tier frame | 4,094 |
| complete-section candidates reaching section-check comparison | 4,096 |

Generated `spec/profile-limits-v0.toml` may impose a smaller bound. It may not
increase one of these safety ceilings. A declared count is checked against its
bound before multiplication, allocation, iteration, or slicing.

Candidate-neutral bootstrap operations use this closed rejection-code space.
The numeric value is durable evidence; explanatory host text is not:

| Code | Symbol | Meaning |
|---:|---|---|
| 1 | `raw_length` | missing, excess, or count-mismatched observation |
| 2 | `raw_value` | observation value is not exactly zero or one |
| 3 | `raw_geometry` | count is not an admitted bounded square |
| 4 | `shell_geometry` | side/width/sector coordinate violates Section 4 |
| 5 | `resource_limit` | declared or derived count/work/allocation exceeds a bound |
| 6 | `block_framing` | common-block length, version, type, or reserved field fails |
| 7 | `fragment_shape` | fragment count/index/length/pad relationship fails |
| 8 | `local_check` | the selected local check does not match |
| 9 | `fragment_conflict` | one full fragment identity has distinct valid bytes |
| 10 | `section_incomplete` | at least one required fragment is absent |
| 11 | `section_framing` | envelope header, length, type, or dependency shape fails |
| 12 | `section_check` | the selected section check does not match |
| 13 | `inventory` | authoritative inventory bytes or entry agreement fail |
| 14 | `tier_frame` | tier-frame bytes, membership, or header/root facts fail |
| 15 | `dependency` | inventory dependency closure is missing, cyclic, or inconsistent |
| 16 | `content_stream` | singular assembly or atomic content-v0 validation fails |
| 17 | `ambiguous` | distinct complete valid canonical alternatives survive |
| 18 | `recipe` | promoted recipe framing/static validation/evaluation fails |
| 19 | `trailing_data` | an otherwise complete bounded object has extra bytes |

An implementation may attach a bounded field/index path, but may not mint a
new public code or use prose matching as control flow. Build-only invalid host
values fail before bytes escape and are not reclassified as observed damage.

Canonical byte arrays compare by length and then unsigned byte value. IDs are
unsigned numeric values. “Strictly increasing” means each next numeric value is
greater than the preceding value; duplicates therefore reject.

## 3. Raw observation and the sixteen entry hypotheses

The raw input is exactly `N` indexed values, each integer 0 or 1. Validation
precedes geometry:

1. reject `N=0` or `N>4_194_304`;
2. reject a supplied sequence whose number of values is not exactly `N`;
3. reject the first value not exactly 0 or 1;
4. compute the checked integer square root `S`;
5. reject unless `S*S=N` and `S<=2048`; and
6. map observed index `i` to provisional `(r=i//S,c=i%S)`.

For each transform `t` below and polarity `p` in order `0,1`, normalized cell
`C_t,p(r,c)` is observed cell at the listed coordinate XOR `p`:

| `t` | observed coordinate for normalized `(r,c)` |
|---:|---|
| 0 | `(r, c)` |
| 1 | `(S-1-c, r)` |
| 2 | `(S-1-r, S-1-c)` |
| 3 | `(c, S-1-r)` |
| 4 | `(r, S-1-c)` |
| 5 | `(S-1-c, S-1-r)` |
| 6 | `(S-1-r, c)` |
| 7 | `(c, r)` |

Hypothesis order is `(t=0,p=0)`, `(0,1)`, `(1,0)`, `(1,1)`, through
`(7,0)`, `(7,1)`. All subtractions are checked after `0<=r,c<S`. There is no
byte-order, content, CRC, ECC, or semantic score at this stage.

Two hypotheses that eventually yield byte-identical complete canonical results
are equivalent and deduplicate. Two nonidentical results that both pass the
entire shell, protected transport, inventory, section, and content chain make
the artifact `ambiguous`; content plausibility never chooses one.

## 4. Four shell sectors

For an admitted pair `(S,W)`, `W` is a multiple of eight and
`8<=W<=min(128,(S-8)//2)`. Define local sector coordinates
`0<=u<W` and `0<=v<S-W`. The four cell mappings are:

| Sector | Global `(r,c)` for local `(u,v)` |
|---:|---|
| 0 | `(u, v)` |
| 1 | `(v, S-1-u)` |
| 2 | `(S-1-u, S-1-v)` |
| 3 | `(S-1-v, u)` |

Each sector contains exactly `W*(S-W)` cells. The mappings are pairwise
disjoint and their union is the complete shell:

~~~text
r < W or r >= S-W or c < W or c >= S-W
~~~

They give the four corners to sectors 0, 1, 2, and 3 respectively in clockwise
order. The interior is exactly `W<=r<S-W` and `W<=c<S-W`. Sector traversal is
local row-major order `k=u*(S-W)+v`; the inverse is `u=k//(S-W)`,
`v=k%(S-W)`, followed by the table above. This is also the D1 sector-erasure
cell set. There are no shared or unowned shell cells.

Every sector's route occupies a generated prefix of its traversal. P4 freezes
the exact prefix length and every bit for each candidate route. The remaining
sector cells are only the formula-assigned headroom and explicit fixed pad that
P4 freezes; they are never implicit slack. All four sectors must carry a
complete route from stage-0 calibration to the fixed inventory entry ID in
Section 9.

The generated `route_sector_capacity_bytes` limit is the inclusive capacity of
one complete sector, not an occupied-prefix length. At `S=2048,W=128` it is
exactly `128*(2048-128)/8 = 30,720` bytes. The envelope's
`route_prefix_cells` field remains the actual calibration, envelope, and route
record prefix. That prefix plus formula headroom must fit within the sector;
the remaining cells are the explicit fixed pad owned below.

For a frozen route candidate, let `I` be the exact occupied instruction/
example/table/recipe cell count over all sectors before headroom, and let `d`
be the P4-frozen size of one candidate-neutral additional-discriminator block.
Headroom is exactly:

~~~text
H = max((I + 19) // 20, 4*d)
~~~

P4 assigns one complete `d`-cell block in each sector, then assigns the
remaining `H-4*d` cells one at a time in sector order 0,1,2,3 to each sector's
next unused canonical headroom position. All `H` cells have fixed values,
remain outside parsed route records, and appear in the shell ledger.

## 5. Bootstrap route knowledge boundary

The dependency root is exactly:

~~~text
intentional finite binary sequence + exact total count
~~~

The final endpoint is the first fully verified canonical content-v0 stream.
P4's promoted DAG uses stable node IDs and grounds, without a backward edge:

1. repetition, complement, equality, and asymmetry;
2. transform/polarity discrimination;
3. small unsigned integers and unsigned order;
4. row/column traversal, fixed-width grouping, and MSB-first significance;
5. bootstrap record framing and lengths;
6. recipe values, operations, framing, and limits;
7. this file's common block and the selected local-check procedure;
8. the selected transport procedure and disjoint known answers;
9. the selected physical-map inverse;
10. fragment identity, conflict, and semantic section assembly;
11. selected section-check and inventory validation; and
12. the tier frame and complete content-v0 validation.

Stage 0 uses only nodes 1--2 and their worked primitive consequences. It does
not use a CRC, ECC syndrome, profile registry, content parser, central catalog,
or preferred transform default.

Each P4 node declares its facts, consumed facts/operations, exact record/cell
owners, worked and held-out example IDs, bounds, and downstream nodes. A
generated topological order is authoritative. The linter rejects first use
before definition, duplicate fact definition, unreachable required endpoint,
unused required definition, cycle, or a node exceeding its bound. The ablation
suite removes/corrupts each defining node and requires failure there or in a
declared dependent.

## 6. Recipe value types and candidate-neutral operations

Recipe data is a declarative finite DAG for teaching/reconstruction evidence;
production decoders implement the selected profile directly. Recipe
interpreters have no filesystem, network, process, environment, clock,
randomness, dynamic import, host callback, or chess operation.

The exact value-type tags are:

| Tag | Type | Width meaning |
|---:|---|---|
| 0 | `UINT` | `1..64` significant bits |
| 1 | `BOOL` | width must be 1 and value is 0 or 1 |
| 2 | `BITS` | fixed `1..1_048_576` bits, final unused low bits zero |
| 3 | `BYTES` | fixed `0..1_048_576` bytes |
| 4 | `TABLE` | immutable fixed-width elements plus exact count |
| 5 | `STATUS` | one P4-frozen explicit success/failure code |

P4 assigns the exact opcodes, operand record widths, package framing, stable
fail codes, and static-validation precedence for this closed vocabulary:

- constant, immutable table, slice, concatenate, and fixed-position emit;
- checked add, subtract, multiply, quotient, and remainder;
- AND, OR, XOR, mask, left/right shift, equality, and unsigned order;
- checked fixed-array read/write and immutable table lookup;
- fixed-count iteration over a statically declared bound;
- finite conditional DAG edges; and
- explicit success or failure.

No P4 opcode may hide CRC, Hamming, RS, map inversion, fragment assembly,
content parsing, or chess semantics. Those procedures must be expressed from
the generic operations above. There is no recursion, arbitrary jump,
data-dependent unbounded loop, dynamic-length allocation, implicit coercion,
uninitialized read, overlapping/duplicate output write, or unchecked
arithmetic/index/shift.

Each completed recipe declares input/output types and widths, immutable table
bytes, nodes/edges, maximum primitive steps, peak live scratch bytes, encoded
length, and every possible explicit fail status. Complete static validation
precedes evaluation. A cycle, bad type/width, forward/uninitialized use,
unknown table/opcode, invalid shift/divisor/index, overflow/underflow,
unreachable node, overlapping output, count excess, trailing byte, or
boundary-plus-one resource rejects without partial output.

## 7. Common 191-byte plain block

Both initial transport families encode the exact following 191 bytes before
their candidate-specific protection:

| Offset | Size | Field | Canonical constraint |
|---:|---:|---|---|
| 0 | 2 | `profile_version` | exact selected tuple value; no parser dispatch |
| 2 | 2 | `fragment_grammar_version` | exactly 0 |
| 4 | 4 | `section_id` | nonzero |
| 8 | 2 | `semantic_copy_id` | less than inventory `copy_count` |
| 10 | 2 | `section_type` | Section 8 closed value |
| 12 | 2 | `section_version` | exact inventory value |
| 14 | 2 | `flags` | exactly zero in v0 |
| 16 | 2 | `fragment_index` | less than `fragment_count` |
| 18 | 2 | `fragment_count` | `1..65_535` |
| 20 | 2 | `valid_payload_length` | `1..157` and exact final/nonfinal rule |
| 22 | 4 | `section_envelope_length` | `1..1_048_576` |
| 26 | 4 | `reserved_zero` | exactly zero |
| 30 | 157 | `payload` | valid prefix then zero padding |
| 187 | 4 | `local_crc32c` | selected CRC-32C semantic integer, big-endian |

The fixed common payload capacity `P` is 157 bytes. For envelope length `L`,
fragment count is exactly `F=(L+156)//157`. Every nonfinal fragment has
`valid_payload_length=157`. The final length is exactly
`L-157*(F-1)` and lies in `1..157`. All payload bytes after the valid prefix are
zero and covered by the local check.

The local-check preimage is the exact eight-byte vector
`d3 91 6a c4 72 08 be 5f` followed by bytes 0--186 of the common block. P4's
profile policy owns the exact CRC-32C tuple and known answers. Stored check
bytes are the big-endian semantic integer even if an implementation uses a
reflected internal update. The check localizes a recovered fragment candidate;
it does not prove section completeness or identity.

Common-block post-transport validation order is:

1. exact 191-byte length;
2. grammar/profile/version and closed section type;
3. flags and reserved zeros;
4. count/index/length ranges and checked `F`/final-length equality;
5. zero payload padding; and
6. local-check equality.

A failing block contributes no fragment bytes. Two byte-identical locally valid
blocks for the same full fragment identity deduplicate. Nonidentical locally
valid bytes for one identity are `ambiguous`; copy count or arrival order does
not vote.

The complete fragment identity is
`(profile_version,section_id,semantic_copy_id,section_type,section_version,
fragment_index,fragment_count,section_envelope_length)`. Assembly first groups
by that identity. A group with distinct valid 191-byte blocks is
`fragment_conflict`; identical blocks collapse to one. One semantic copy is
complete only when the surviving indices are exactly `0..fragment_count-1`;
their valid payload prefixes concatenate in index order to exactly
`section_envelope_length` bytes. Header disagreement across its fragments is a
conflict, never another partial copy.

After envelope and inventory agreement, byte-identical complete physical
witnesses collapse to one logical section. The logical state is `verified` if
at least one witness was recovered with every protected unit reported
`verified`; otherwise it is `recovered`. Distinct complete valid envelope bytes
for the same logical section identity yield `ambiguous`, even if one witness is
`verified` and another is merely `recovered`. Physical-copy diagnostics remain
separate from this deterministic aggregate and arrival order never changes it.

## 8. Semantic section envelope

The closed v0 section-type values are:

| Value | Type |
|---:|---|
| 1 | `inventory` |
| 2 | `tier-frame` |
| 3 | `content-body` |
| 4 | `capacity-probe` |
| 5 | `reserve-probe` |
| 6 | `load-probe` |

The closed v0 recovery/closure-class values are:

| Value | Meaning |
|---:|---|
| 128 | `m2_required` member |
| 129 | `m2_all_only` member |

Values 0--4 are reserved for final RT0--RT4 use and reject in M2. Other values
reject. A complete `m2_all` stream includes required plus all-only content; the
class names do not claim actual product RT closure.

The check-ID field accepts 1 (`crc32c`) or 2 (`crc64-ecma`) after P4 freezes the
exact selected comparison tuples. It dispatches only to those promoted
procedures. No unknown algorithm is accepted.

Every semantic envelope is exactly:

| Offset | Size | Field |
|---:|---:|---|
| 0 | 2 | `envelope_version`, exactly 0 |
| 2 | 4 | nonzero `section_id` |
| 6 | 2 | closed `section_type` |
| 8 | 2 | `section_version` |
| 10 | 1 | closed `closure_class` |
| 11 | 1 | closed `check_id` |
| 12 | 2 | `dependency_count` |
| 14 | 4 | `logical_payload_length` |
| 18 | `4*dependency_count` | strictly increasing nonzero dependency IDs |
| next | `logical_payload_length` | logical payload bytes |
| final | 4 or 8 | stored selected section check, big-endian semantic integer |

The section-check preimage is the exact eight-byte vector
`4b e2 19 77 a0 3c 65 d8` followed by all envelope bytes except the stored
check. The complete envelope length is derived with checked arithmetic and must
equal the concatenated fragment length exactly. It never includes semantic copy
ID, physical placement, fragment index, candidate transform, or observed order.

Dependencies may not include the section itself. Envelope fields/type/version/
class/check/dependencies/payload length must equal the authoritative inventory
entry. Fragment header section ID/type/version/envelope length must equal the
decoded envelope. Any mismatch rejects that complete section candidate before
its bytes can enter a tier.

Section validation order is:

1. complete outer bytes and safety cap;
2. fixed header version/ID/type/class/check code;
3. dependency count before offset arithmetic;
4. strictly increasing nonzero dependencies and no self-dependency;
5. exact payload/check/total length;
6. section-check equality;
7. exact fragment-header/envelope agreement; and
8. exact inventory agreement.

## 9. Inventory payload

The shell's fixed Core-0 entry section ID is 1. It has section type `inventory`,
section version 0, closure class `m2_required`, and exactly two semantic copies
with copy IDs 0 and 1 in independent P4-proved failure domains. Its semantic
envelope bytes are identical across copies.

Inventory logical payload begins:

| Offset | Size | Field | Constraint |
|---:|---:|---|---|
| 0 | 2 | `inventory_version` | exactly 0 |
| 2 | 2 | `entry_count` | `3..4096` |
| 4 | 2 | `game_ordinal_first` | exactly 0 |
| 6 | 2 | `game_ordinal_count` | exactly 64 |

It is followed by `entry_count` entries in strictly increasing `section_id`
order. Each entry has a 20-byte fixed header followed immediately by its
dependency IDs:

| Relative offset | Size | Field | Constraint |
|---:|---:|---|---|
| 0 | 4 | `section_id` | nonzero, strictly increasing across entries |
| 4 | 2 | `section_type` | Section 8 closed value |
| 6 | 2 | `section_version` | exact expected version |
| 8 | 1 | `closure_class` | Section 8 closed M2 value |
| 9 | 1 | `check_id` | 1 or 2 |
| 10 | 1 | `copy_count` | 1, 2, or 3 |
| 11 | 1 | `flags` | bit 0 `has_game_ordinal`; all others zero |
| 12 | 2 | `dependency_count` | `0..4095` |
| 14 | 4 | `logical_payload_length` | exact payload length |
| 18 | 2 | `game_ordinal` | `0..63` iff flag set; otherwise `0xffff` |
| 20 | `4*dependency_count` | dependency IDs | strictly increasing, nonzero, not self |

Every dependency names another inventory entry. Semantic copy IDs expected for
one entry are exactly `0..copy_count-1`. Entry 1 describes the inventory itself
with copy count 2 and no dependency. Entry 2 is the `m2_required` tier frame;
entry 3 is the `m2_all` tier frame. Both have type `tier-frame`, version 0, and
at least two copies. Other IDs are assigned by the reviewed slice/capacity
manifest and become immutable before candidate manifestations.

Exactly 64 entries across the complete inventory have
`has_game_ordinal=1`, with each ordinal 0 through 63 present exactly once; each
is a `content-body` section. A game-bearing section payload contains complete
content record frames for that one game only and is never split across semantic
sections. The inventory must list itself, both tier frames, and every real,
capacity-probe, reserve-probe, and load-probe section carried by the candidate.

Valid inventory semantic bytes must be unique. Conflicting valid inventories
make the artifact `ambiguous`. If no complete valid inventory copy survives,
individual fragments may be diagnosed but no completeness/tier claim exists.

Once the inventory is accepted, its dependency graph is checked in increasing
section-ID neighbor order with three-color depth-first traversal. A dependency
on an absent entry is `inventory`; a cycle is `dependency`; an incomplete
requested transitive closure is `dependency`. This graph check occurs before a
tier frame can authorize content-stream assembly.

## 10. Tier-frame payload and singular content stream

The fixed tier-frame section IDs are 2 (`m2_required`) and 3 (`m2_all`). The
closed tier IDs inside their payloads are 0 and 1 respectively. Their closure
classes are `m2_required`; each has at least two semantic copies as frozen by
the inventory and placement proof.

Tier-frame logical payload is:

| Offset | Size | Field | Constraint |
|---:|---:|---|---|
| 0 | 2 | `tier_frame_version` | exactly 0 |
| 2 | 1 | `tier_id` | 0 required, 1 all; matches section ID |
| 3 | 1 | `reserved_zero` | exactly 0 |
| 4 | 2 | `body_section_count` | `1..4094` |
| 6 | 2 | `reserved_zero` | exactly 0 |
| 8 | 4 | `assembled_stream_byte_length` | exact nonzero final length |
| 12 | 2 | `assembled_record_count` | exact content-v0 record count |
| 14 | 4 | `root_record_byte_length` | exact nonzero complete frame length |
| 18 | 4 | `content_stream_header` | exact `u16_be version || u16_be record_count` |
| 22 | `4*body_section_count` | body section IDs | strictly increasing, duplicate-free |
| next | `root_record_byte_length` | final complete content-v0 root record bytes |

Every listed ID exists in the inventory with type `content-body`; its unique
selected logical payload is a concatenation of one or more complete non-root
content-v0 record frames. A semantic section boundary occurs only between
complete records. Tier-frame dependencies equal the body ID list exactly.

Assembly is exactly:

~~~text
content_stream_header
|| each listed content-body logical payload in ID order
|| root_record_bytes
~~~

Before the content parser is called, checked arithmetic verifies the exact
assembled byte length, exact encoded record count, content header count, root
length, and complete consumption of every body payload. `stream_validation`
must then accept the entire assembled byte array with exactly one final root and
no trailing byte. No header/root is synthesized or patched, no record is
reordered, no accepted prefix is returned, and no lower tier silently replaces
the requested tier.

The required frame lists every content-body section in `m2_required`. The all
frame lists the strictly increasing union of required and `m2_all_only`
content-body sections. Its list therefore contains the required list as an
ordered subsequence. Capacity/reserve/load probes are inventoried transport
sections but never content-body IDs and never enter the assembled stream.

The two independent content encoders first emit each exact complete feasibility
stream. A splitter derives body/root boundaries independently; reassembly in
both languages must equal each original encoder byte-for-byte. One encoder's
bytes/split are never used as the other's input.

## 11. Atomic validation order

The complete decoder order is fixed:

1. observation channel, exact total length, and generated resource preflight;
2. at most sixteen transform/polarity shell hypotheses;
3. selected map inverse and protected-unit extraction;
4. bounded selected transport recovery;
5. common-block header/range/reserved/pad/local-check validation;
6. identity deduplication and conflict handling;
7. exact semantic envelope assembly/framing;
8. selected section check;
9. authoritative inventory, tier-frame, and dependency closure;
10. exact singular tier stream assembly;
11. atomic content-v0 validation; and only then
12. evaluator-side chess/lesson/game assertions.

No valid prefix, partial block, incomplete locally checked section, or
unverified content record contributes canonical bytes. Missing values are not
filled from zero, chess legality, evaluator answers, another candidate, or
another semantic copy. Byte-identical valid witnesses deduplicate; nonidentical
fully valid alternatives are `ambiguous`.

## 12. Recipe package binary

Recipe data is a bounded, side-effect-free collection of topologically ordered
recipes and immutable tables. All integers in this section are unsigned and
big-endian. A package is at most 1,048,576 bytes. Its fixed 64-byte header is:

The shared exact package/input/status/output KAT is canonical manifest
`conformance/recipe-v0.json`, SHA-256
`50862edb1d0c9654e5c903735f86b41c7ca2958a1e36cffb70a7622ee9a20845`.
It exercises every opcode 1--25, a lower-ID iterator body, partial fixed-offset
emits, package tables, explicit failure, and runtime resource failure. Python
and Rust consume these same literal bytes; independently similar fixtures do
not satisfy the cross-language KAT.

| Offset | Size | Field | Constraint |
|---:|---:|---|---|
| 0 | 8 | magic | exactly `47 42 52 45 43 50 30 00` (`GBRECP0` plus zero) |
| 8 | 2 | package version | exactly 0 |
| 10 | 2 | operation version | exactly 0 |
| 12 | 2 | profile version | one exact profile-policy value |
| 14 | 2 | flags | exactly zero |
| 16 | 2 | recipe count | `1..256` |
| 18 | 2 | table count | `0..4096` |
| 20 | 4 | total node count | `1..65,535` |
| 24 | 4 | total edge count | `0..262,140` |
| 28 | 4 | table payload bytes | `0..1,048,576` and exact |
| 32 | 4 | package bytes | exact complete byte length, `64..1,048,576` |
| 36 | 8 | maximum primitive steps | exact derived value, at most 268,435,456 |
| 44 | 4 | peak live scratch bytes | exact derived value, at most 16,777,216 |
| 48 | 16 | reserved | all zero |

The header is followed by all table records in strictly increasing table ID,
then all recipe records in strictly increasing recipe ID, with no alignment or
trailer. A table record is a 16-byte header followed immediately by its exact
payload:

| Offset | Size | Field | Constraint |
|---:|---:|---|---|
| 0 | 2 | table ID | nonzero and strictly increasing |
| 2 | 1 | element type | `UINT`, `BOOL`, `BITS`, `BYTES`, or `STATUS`; never `TABLE` |
| 3 | 1 | flags | exactly zero |
| 4 | 4 | element width | valid for the element type |
| 8 | 4 | element count | `1..1,048,576` and within package limits |
| 12 | 4 | payload bytes | exact checked product/packing length |

`UINT`, `BOOL`, and `STATUS` elements occupy `ceil(width/8)` bytes each,
big-endian, with unused high bits zero. `BITS` elements occupy
`ceil(width/8)` bytes each in MSB-first order, with unused final low bits zero.
For `BYTES`, width is bytes per element. `STATUS` width is exactly 16;
`BOOL` width is exactly 1. Elements are concatenated without padding.

Each recipe begins with this fixed 32-byte header:

| Offset | Size | Field | Constraint |
|---:|---:|---|---|
| 0 | 2 | recipe ID | nonzero and strictly increasing |
| 2 | 2 | flags | exactly zero |
| 4 | 2 | input count | `0..64` |
| 6 | 2 | output count | `1..64` |
| 8 | 4 | node count | `1..65,535`, within package total |
| 12 | 4 | edge count | exact local dependency-edge count |
| 16 | 8 | primitive steps | exact derived worst case |
| 24 | 4 | peak live scratch bytes | exact derived value |
| 28 | 4 | recipe bytes | exact header, descriptors, and nodes |

It is followed by `input_count` input descriptors, `output_count` output
descriptors, then `node_count` fixed 32-byte nodes. A descriptor is:

~~~text
u16 value_id || u8 type || u8 flags_zero || u32 width || u32 count
~~~

Input IDs are exactly `1..input_count`. Input descriptor count is one except
that `TABLE` is forbidden on recipe input and output interfaces: immutable
table values originate only at opcode 2, whose named package table supplies the
element type, width, count, and bytes needed for exact static typing. A node's
output value ID is exactly `input_count + node_id`; the checked sum
`input_count + node_count` must not exceed 65,535. An output descriptor's
`value_id` is instead
its output-slot ID, exactly `1..output_count`; nodes populate those separately
allocated slots through `EMIT`. Output slot 1 is exactly a width-16 `STATUS`;
other output slots cannot have type `STATUS` or `TABLE`. All interface
descriptors have count one. All descriptor and computed storage sizes use
checked `u64` arithmetic.

## 13. Closed node records and opcodes

A node record is exactly:

~~~text
u16 node_id
u8  opcode
u8  output_type
u32 output_width
u16 argument_count
u16 argument_0
u16 argument_1
u16 argument_2
u16 argument_3
u16 auxiliary_u16
u32 auxiliary_u32
u64 immediate_u64
~~~

Node IDs are exactly `1..node_count`. Arguments are value IDs and must name an
input or an earlier node output. `argument_count` is `0..4`; every unused
argument field is zero. Fields not assigned below are zero. No opcode has a
host-dependent result or hidden code-specific behavior.

| Opcode | Name | Exact arguments and result |
|---:|---|---|
| 1 | `CONST` | zero arguments; `UINT`, `BOOL`, or `STATUS` result from `immediate_u64`; value fits exact width |
| 2 | `TABLE` | zero arguments; `auxiliary_u16` names the immutable table; descriptor must match |
| 3 | `SLICE` | sequence, start `UINT`, length `UINT`; fixed result is same sequence type, or `UINT` from at most 64 MSB-first `BITS`; runtime length equals result width |
| 4 | `CONCAT` | two equal sequence types, or two `UINT`s; widths add exactly; `UINT` concatenation is high argument then low argument |
| 5 | `EMIT` | one value; `auxiliary_u16` names an output slot and `immediate_u64` is its bit/byte offset; result is success `STATUS` |
| 6 | `ADD` | two same-width `UINT`s; checked exact-width sum |
| 7 | `SUB` | two same-width `UINT`s; checked nonnegative difference |
| 8 | `MUL` | two same-width `UINT`s; checked exact-width product |
| 9 | `QUOT` | two same-width `UINT`s; divisor nonzero; unsigned quotient |
| 10 | `REM` | two same-width `UINT`s; divisor nonzero; unsigned remainder |
| 11 | `AND` | two equal-width `UINT` or `BITS` values |
| 12 | `OR` | two equal-width `UINT` or `BITS` values |
| 13 | `XOR` | two equal-width `UINT` or `BITS` values |
| 14 | `MASK` | one `UINT`; `immediate_u64` fits the width; result is value AND mask |
| 15 | `SHL` | `UINT` value and `UINT` shift; checked left shift, shift less than width |
| 16 | `SHR` | `UINT` value and `UINT` shift; logical right shift, shift less than width |
| 17 | `EQ` | two exactly equal typed widths; `BOOL` result |
| 18 | `LT` | two same-width `UINT`s; unsigned `BOOL` result |
| 19 | `ARRAY_READ` | `BITS`/`BYTES`/`TABLE` and `UINT` index; result is `BOOL`, width-8 `UINT`, or the table element respectively |
| 20 | `ARRAY_WRITE` | sequence, `UINT` index, exactly typed element; result is a new same-width sequence |
| 21 | `TABLE_LOOKUP` | `TABLE` and `UINT` index; result exactly matches its element descriptor |
| 22 | `ITERATE` | initial accumulator; `auxiliary_u16` names a lower-ID body recipe and `immediate_u64` is fixed count; result matches accumulator |
| 23 | `SELECT` | `BOOL`, true value, false value; both branches exactly same type/width; selected result |
| 24 | `SUCCESS` | zero arguments; success `STATUS` 0 |
| 25 | `FAILURE` | zero arguments; `STATUS` from nonzero `immediate_u64` in the closed table below |

`SLICE` indexes bits or bytes from zero. `ARRAY_READ`/`ARRAY_WRITE` use the
same zero origin. A `BITS` bit at index zero is the first serialized MSB.
`EMIT` converts a `UINT` to exactly its significant-width MSB-first bits and
otherwise copies the exact declared bit/byte representation; that conversion
is part of the opcode, not an implicit cast. Every declared output-slot
position is written exactly once by statically visible `EMIT` nodes. Slot 1
receives exactly one complete status value. Any gap, overlap, duplicate writer,
or out-of-range write rejects the complete recipe. Other output slots are
released only when slot 1 is success.

An `ITERATE` body has exactly two inputs: the accumulator type/width and a
width-64 `UINT` index. It has exactly two outputs: slot 1 is the required
`STATUS`, and slot 2 matches the accumulator. Each successful iteration feeds
slot 2 to the next iteration; a nonzero slot 1 aborts the iterator with that
status and no accumulator output. Its recipe ID is lower than the caller's.
Iteration indexes are exactly `0..count-1`; count zero returns the initial
accumulator. The count is at most 1,048,576. Calls exist only through this
operator, so lower-ID references make the package call graph acyclic without
recursion or arbitrary jumps.

All nodes are evaluated once in node order. `SELECT` selects between already
computed finite DAG values; it does not skip validation or conceal a loop.
Each opcode execution counts one primitive step. An `ITERATE` contributes one
step plus `count * body_steps`, checked recursively. A recipe's local edge
count is the sum of all node `argument_count` values plus one control edge for
each `ITERATE` body-recipe reference; package total edges are the sum of local
edge counts. Package maximum steps are the maximum recipe steps, not their
sum. Package/recipe declared steps and edges must equal these derived values.

Every node must reach at least one `EMIT` node by zero or more same-recipe
backward argument edges; an `EMIT` is itself reachable. An unused calculation,
including an unused `SUCCESS` or `FAILURE`, rejects. Every recipe is an
independently invokable entry, while each `ITERATE` body is also a control
dependency of its caller.

Scratch is the exact peak bytes of live node results under last-use release in
node order, excluding immutable inputs/tables and separately allocated final
output buffers. Storage is `ceil(width/8)` bytes for `UINT`, `BOOL`, `BITS`,
and `STATUS`, `width` bytes for `BYTES`, and zero charged bytes for immutable
`TABLE`. Immediately before a node executes, all argument results are still
live. A regular node's peak candidate is current live bytes plus its result
storage; only after the result exists are arguments at their last use released.
For `ITERATE`, the peak candidate is the maximum of current live bytes plus the
lower-ID body recipe's exact peak, and current live bytes plus the iterator
result storage. This recurrence is finite because body IDs are lower. A
functional array write therefore charges its complete new array while the old
array and other live arguments remain live. Recipe peak is the maximum of its
node candidates; package peak is the maximum recipe peak.

## 14. Recipe statuses and static rejection order

The closed `STATUS` assignments are:

| Value | Name |
|---:|---|
| 0 | `success` |
| 1 | `explicit-failure` |
| 2 | `observation-shape` |
| 3 | `parameter` |
| 4 | `algebra-boundary` |
| 5 | `no-unique-codeword` |
| 6 | `local-check` |
| 7 | `section-check` |
| 8 | `fragment-incomplete` |
| 9 | `section-incomplete` |
| 10 | `ambiguous` |
| 11 | `resource-limit` |
| 12 | `inventory` |
| 13 | `dependency` |
| 14 | `content-stream` |
| 15 | `reserved-failure` |

`FAILURE` may emit 1--14. Value 15 is reserved and rejects if used. A recipe
that completes with any nonzero status exposes no other output bytes.

Complete static validation precedes evaluation in this order:

1. outer byte cap and exact 64-byte header availability;
2. magic, versions, profile, flags, and reserved zeros;
3. package count/range arithmetic and exact declared outer length;
4. table IDs, descriptors, exact payload sizes, and unused bits;
5. recipe IDs, headers, count arithmetic, and exact recipe boundaries;
6. input/output descriptors and value-ID rules;
7. node IDs, known opcodes, argument counts, and unused zero fields;
8. backward value references and exact edge counts;
9. opcode-specific type, width, immediate, index, shift, and divisor rules;
10. lower-ID iteration bodies, global acyclicity, and fixed iteration bounds;
11. exact output coverage without gap, overlap, or duplicate writer;
12. exact derived steps/scratch and all resource ceilings; and
13. complete package consumption with no trailing byte.

The first failure returns bootstrap rejection 18 (`recipe`). Nothing is
evaluated and no partial output/status is returned. Runtime checked arithmetic,
index, divisor, or declared resource failure returns recipe status 11 and no
other output. Runtime `FAILURE` returns its named status. Two independent
interpreters must agree on the full status/output pair, not only successful
bytes.

## 15. Four complete route records

Each shell sector begins with its exact 32-byte calibration block, followed by
one route envelope and its records. Calibration bytes are read as bits MSB
first:

| Sector | Calibration bytes |
|---:|---|
| 0 | `f0 0f cc 33 aa 55 96 69 81 7e 24 db 18 e7 42 bd 01 fe 02 fd 04 fb 08 f7 10 ef 20 df 40 bf 80 7f` |
| 1 | `cc 33 aa 55 96 69 f0 0f 02 fd 18 e7 42 bd 81 7e 04 fb 08 f7 10 ef 20 df 40 bf 80 7f 01 fe 24 db` |
| 2 | `aa 55 96 69 f0 0f cc 33 04 fb 42 bd 81 7e 24 db 08 f7 10 ef 20 df 40 bf 80 7f 01 fe 02 fd 18 e7` |
| 3 | `96 69 f0 0f cc 33 aa 55 08 f7 81 7e 24 db 18 e7 10 ef 20 df 40 bf 80 7f 01 fe 02 fd 04 fb 42 bd` |

Every adjacent byte pair in each block supplies complementary and asymmetric
worked relationships; the complete 256-bit blocks differ. The stage-0 linter
uses equality, complement, repetition, and asymmetry only. A one-example match
does not validate a route.

The following fixed 32-byte route envelope is immediately after calibration:

| Offset | Size | Field | Constraint |
|---:|---:|---|---|
| 0 | 8 | magic | exactly `47 42 52 4f 55 54 45 00` (`GBROUTE` plus zero) |
| 8 | 2 | route version | exactly 0 |
| 10 | 1 | sector ID | matches physical sector |
| 11 | 1 | route ID | exactly sector ID |
| 12 | 2 | profile version | exact candidate profile |
| 14 | 2 | record count | exact, `37..256` |
| 16 | 4 | record bytes | exact bytes following this envelope |
| 20 | 4 | recipe package bytes | exact sum of kind-5 payload bytes |
| 24 | 4 | route prefix cells | exactly `(32 + 32 + record_bytes) * 8` |
| 28 | 2 | discriminator cells | exactly 256 |
| 30 | 2 | flags | exactly zero |

A route record is `u8 stage || u8 kind || u16 record_id || u32 payload_bytes`
followed by exactly that payload. Records have strictly increasing IDs and
stages never decrease. Kinds are:

| Kind | Name | Payload |
|---:|---|---|
| 1 | `DEFINE` | `u16 fact_id` plus exact typed fact descriptor/value |
| 2 | `WORKED` | `u16 fact_id || u16 recipe_id || u32 input_bytes || u32 output_bytes` then literal input and output |
| 3 | `HELD_OUT` | same frame as `WORKED`, with disjoint literal input/output |
| 4 | `TABLE` | one exact Section-12 table record |
| 5 | `RECIPE` | one complete exact Section-12 recipe package |
| 6 | `ENDPOINT` | exact `u32 1`, the inventory section ID |
| 7 | `END` | empty; must be final |

For kind 1, the fact descriptor immediately follows `fact_id`; its `value_id`
equals `fact_id`, and its canonical value bytes follow with the exact table-
element packing rules from Section 12. Kind-2 and kind-3 input/output bytes are
the concatenation of values in recipe interface slot order using those same
packing rules; their lengths are therefore independently derivable. They are
complete recipe interface encodings, not prose.
Their recipe IDs exist in the route's kind-5 package. Worked and held-out
preimages are disjoint and exact. A kind-4 table that names a package table ID
must be byte-identical to it; a nonidentical duplicate is a conflict. A route
has exactly one endpoint and one final end.

All four routes use the same canonical fact graph and candidate procedure but
carry independent complete literal copies. Sector ID, calibration, record IDs,
and fixed example data differ by the formulas below, so sectors are not
byte-identical decoration. For canonical fact node `n`, sector `q`, and
`base=10,000*q`, record IDs are:

~~~text
DEFINE:   base + 100*n + 1
WORKED:   base + 100*n + 2
HELD_OUT: base + 100*n + 3
TABLE:    base + 5000 + local_table_ordinal
RECIPE:   base + 6000 + local_package_ordinal
ENDPOINT: base + 7001
END:      base + 7002
~~~

`spec/route-data-v0.json` is the canonical owner of the twelve exact DEFINE
descriptors/values, the route-required recipe IDs 30 and 101--112, interfaces,
canonical worked/held-out bytes, and each fact's nonempty
`mask_input_slots`. Fact 8 binds its WORKED and HELD_OUT records to recovery
entry 30; recipe 108 is its required support encoder. Records
remain numerically increasing by placing each fact's definition,
worked example, and held-out in fact/stage order, then tables, recipes,
endpoint, and end. Table/package ordinals increase. Literal example bytes for
sector `q`, except fact 8, are formed by XORing only those declared datum input
slots with the repeated one-byte mask
`00`, `3c`, `a5`, or `c9` respectively before the locally taught expected
operation. Structural parameters, coordinates, IDs, and count bounds in
undeclared slots remain literal. For `UINT`, `BOOL`, and `BITS` the mask is truncated to the declared
significant width; for `BYTES` it repeats across the value; `STATUS` is not
masked. Unused bits remain zero. Worked and held-out inputs must remain
disjoint after every sector mask, every masked evaluation must succeed, and
the complete interface output is recomputed from the masked input. This is a
data transformation, not a semantic shortcut or a second candidate result.

Fact 8 instead derives one exact source message per sector before executing
encoder 108, injecting the manifest's one fixed in-radius damage, and executing
recovery entry 30 with zero erasures. For EH, the sector mask is XORed across
the whole canonical eight-byte source-message slot. For RS, the source is a
profile-version-bound valid common block: bytes 0--29 remain literal, the mask
is XORed only across all 157 payload bytes at offsets 30--186, and bytes
187--190 are recomputed as the exact common-block local CRC-32C. The canonical
manifest freezes the four resulting worked sources and four resulting held-out
sources for every profile; implementations must validate their framing,
profile version, zero padding, and local CRC before use. The EH encoder interface is
`BYTES[8] -> STATUS[16], BYTES[9]`; its decoder interface is
`BYTES[9], BYTES[1], BYTES[3] -> STATUS[16], BYTES[8]`. The RS encoder
interface is `BYTES[191] -> STATUS[16], BYTES[255]`; its decoder interface is
`BYTES[255], BYTES[1], BYTES[64] -> STATUS[16], BYTES[191]`. In both decoder
interfaces the one-byte erasure count is followed by a fixed-capacity position
array whose first `count` bytes are strictly increasing positions and whose
remainder is zero. Active EH position bytes use the one-based encoded-bit
positions `1..72`; active RS position bytes use the zero-based wire-symbol
positions `0..254`. The frozen fact-8 examples set the count and every position
byte to zero. EH WORKED flips observation bit 0 (`byte[0] XOR 80` hex) and EH
HELD_OUT flips bit 71 (`byte[8] XOR 01` hex). RS WORKED flips `byte[0] XOR 53`
hex and RS HELD_OUT flips `byte[254] XOR 53` hex. Encoder 108, decoder 30, and
the complete recovery output are evaluated through the generic recipe
machine. Each example requires status zero and the exact masked source message;
no host codec shortcut is permitted. The EH product adapter applies decoder 30
exactly 24 times for each fact-4 grouping, with no hidden transport logic.
Table, recipe, endpoint, and end records use stage 5.

## 16. Exact route graph, cell charge, and map handoff

The route graph is the following closed table. Consumed fact IDs are sorted;
each is smaller than its consumer. Every route contains one `DEFINE`, one
disjoint `WORKED`, and one disjoint `HELD_OUT` for each row.

| Fact ID | Stage | Fact | Consumes |
|---:|---:|---|---|
| 1 | 0 | binary equality, complement, repetition, asymmetry | none |
| 2 | 0 | eight square transforms and two polarities | 1 |
| 3 | 1 | unsigned integers, equality, and order | 1 |
| 4 | 1 | row-major traversal, fixed grouping, MSB significance | 2,3 |
| 5 | 2 | route and recipe record lengths | 3,4 |
| 6 | 2 | recipe types, opcodes, statuses, and bounds | 5 |
| 7 | 3 | common block and local CRC-32C | 6 |
| 8 | 3 | selected EH72 or RS transport and KATs | 6,7 |
| 9 | 4 | affine-interior-v1 inverse and candidate parameters | 6,8 |
| 10 | 4 | fragment identity, conflict, and section assembly | 7,8,9 |
| 11 | 5 | section check, inventory, and dependency closure | 10 |
| 12 | 5 | tier frame and complete content-v0 validation | 11 |

The profile policy owns the exact `affine-interior-v1` mapping formula and
parameters. Fact 9
has exactly the interface `logical_flat UINT[32], side UINT[16], shell_width
UINT[16] -> physical_flat UINT[32]`; profile version is a package constant.
Only `logical_flat` is a maskable datum. `side` and `shell_width` remain literal
structural inputs, and 2048/128 are canonical examples rather than hidden
constants. Its interior side is exactly `side-2*shell_width`, never
`side-shell_width`. Fact 9 must express its closed-form multiplier inverse
using only promoted opcodes and teach the one-line coprimality identity; no
coordinate table is permitted.
Facts 7, 8, and 11 use the exact
selected profile/check tuple. Every candidate-specific recipe package therefore
uses only opcodes 1--25 and every required operation kind appears in at least
one route record before its first candidate procedure use.

For one candidate, let `route_prefix_cells[q]` be the exact envelope value for
sector `q`, and `I=sum(route_prefix_cells)`. The additional-discriminator block
size is exactly `d=256` cells. Shell headroom remains
`H=max((I+19)//20,4*d)`. The first 256 headroom cells in each sector are that
sector's calibration block repeated once; remaining headroom cells are assigned
by Section 4. Every other shell cell is explicit fixed pad.

Remaining headroom and shell-pad bits come in this exact order from:

~~~text
SHA256("GB-M2-SHELL-PAD-v0\0"
       || profile_version_u16_be
       || sector_id_u8
       || counter_u64_be)
~~~

The domain bytes are exactly
`47 42 2d 4d 32 2d 53 48 45 4c 4c 2d 50 41 44 2d 76 30 00`.
Counter starts at zero and increments without wrapping. Digests contribute raw
bits MSB first; a final digest contributes its shortest prefix. Headroom bits
consume the stream first, then that sector's remaining pad in traversal order.
These cells remain outside the route record parser and appear as their exact
owners in the shell ledger.

For each `(profile,S,W)`, the route generator must finish all four route byte
packages before geometry fit is evaluated. A route prefix exceeding its sector,
headroom not fitting, a route record/schema disagreement, or any absent fact,
worked example, held-out, table, recipe, endpoint, or end rejects that geometry.
Only a uniquely complete route after the full downstream inventory, transport,
section, tier, and content validation may accept an entry hypothesis.

## 17. Exact RS(255,191) encoder and decoder

This section is the complete algorithmic owner for profile
`rs255-191-v0`. Implementations must not substitute a library's defaults or
infer conventions from a successful checksum. All arrays named as polynomials
below store coefficients in ascending degree; the 255-byte transport word is
the separate descending-power wire representation
`r[0]*x^254 + ... + r[254]`.

### 17.1 Field and systematic encoder

Field elements are bytes. Addition and subtraction are XOR. Multiplication is
the following fixed eight-round operation: initialize `a` and `b` from the two
operands and `product=0`; for exactly eight rounds, XOR `a` into `product` when
the low bit of `b` is one, replace `a` by `(a<<1)&255` and additionally XOR
`0x1d` when its old high bit was one, then replace `b` by `b>>1`. The primitive
element is `alpha=2`; `alpha_pow(k)` uses exponent `k mod 255`. Division by zero
and `inverse(0)` reject. For nonzero `a`, inversion is the fixed square-and-
multiply computation `a^254` in this field.

The generator is

~~~text
g(x) = product over j=0..63, in increasing j, of (x + alpha_pow(j))
~~~

and its 65 coefficients, written from degree 64 down to degree zero, are the
exact 65 bytes:

~~~text
01c10aff3a80b7738c99935bc5dbdddc8e1c7815a49306cc28e6b60e79308f4d
e451552ba210c3a323959a2384646433b00ba186d084f4b0c0dde8ab7d9be4f2f5
~~~

Their SHA-256 is
`cac6037e9f22730421948ada2652249582abf7b4919347c2408622de22b81a34`.
Encoding exactly 191 data bytes is ordinary monic polynomial division of the
data followed by 64 zero coefficients by this generator. The emitted word is
the unchanged 191 data bytes followed by the resulting 64 parity bytes. No
shortening, reversal, reflection, implicit leading coefficient, or alternate
root range is permitted.

### 17.2 Input normalization and syndromes

The decoder accepts exactly 255 observed bytes and an explicit erasure-position
array. Positions are zero-based wire indices and must be strictly increasing,
unique, and in `0..254`; malformed shape or positions reject with status 3.
More than 64 erasures reject with status 4 before field work. Let their count be
`s`. Copy the observed word and set every named erasure byte to zero. Any
surviving value in an erased byte is discarded, not used as a soft hint.

Compute exactly 64 syndromes, in this order:

~~~text
S[j] = r(alpha_pow(j)), j=0..63
~~~

Each evaluation is Horner evaluation over wire positions `p=0..254`, hence in
descending coefficient order. If `s=0` and all 64 syndromes are zero, the word
is clean. Otherwise continue. For any position `p`, define its position number
`X[p]=alpha_pow(254-p)`.

### 17.3 Erasure transform and Berlekamp--Massey

Build the erasure locator, processing the already sorted erasure positions in
ascending order:

~~~text
Gamma(z) = product over erased p of (1 + X[p]*z)
~~~

Coefficient arrays are ascending degree and multiplication is ordinary bounded
GF(256) convolution. `Gamma[0]=1` and it has at most 65 coefficients. Form the
64 modified syndrome coefficients

~~~text
T[k] = XOR over i=0..min(k,s) of Gamma[i] * S[k-i], k=0..63
U[n] = T[s+n], n=0..63-s
~~~

Dropping exactly the first `s` coefficients is part of the algorithm.

Run the following Berlekamp--Massey loop on `U`, without normalization or an
alternate update rule. Initially `C=B=[1]`, `L=0`, `m=1`, and `b=1`. For each
`n=0..len(U)-1`, compute

~~~text
d = U[n] XOR (XOR over i=1..L of C[i]*U[n-i])
~~~

with absent coefficients treated as zero. If `d=0`, increment `m`. Otherwise
copy the old `C` to `old_C`, compute `q=mul(d,inverse(b))` (that is, `d/b`), and perform
`C = C XOR q*z^m*B`. If `2*L <= n`, then additionally set
`L=n+1-L`, `B=old_C`, `b=d`, and `m=1`; otherwise increment `m`. After the loop,
remove trailing zero coefficients only. Require `degree(C)=L`, at most 33
coefficients, and `2*L+s <= 64`; otherwise reject with status 4.

The full locator is `Lambda=Gamma*C`. Require at most 65 coefficients and
`degree(Lambda)=s+L<=64`, else status 4.

### 17.4 Chien search, evaluator, and magnitudes

Scan every position exactly once in ascending order `p=0..254`. Its Chien
argument is

~~~text
z[p] = alpha_pow(p+1) = inverse(X[p])
~~~

and `p` is a root precisely when `Lambda(z[p])=0`. Require the root count to
equal `degree(Lambda)`, require every named erasure to be a root, and require
exactly `L` roots outside the erasure set. Any mismatch rejects with status 5.

Compute the evaluator and formal derivative in ascending degree:

~~~text
Omega(z) = (S(z)*Lambda(z)) mod z^64
Lambda_prime[i-1] = Lambda[i] for odd i; all even-i terms vanish
~~~

For every root position, in ascending position order, derive and retain the
correction magnitude before changing any received byte:

~~~text
E[p] = X[p] * Omega(z[p]) / Lambda_prime(z[p])
~~~

A zero derivative rejects with status 5. A zero magnitude is allowed for a
named erasure and is rejected for an unknown-error root. Let `e` be the number
of non-erasure roots with nonzero magnitude; require `e=L` and `2*e+s<=64`, or
reject with status 5. The leading `X[p]` factor is mandatory for the root-zero
syndrome convention: with `S(z)=sum E/(1-X*z)`, evaluation at `X^-1` gives
`E = X*Omega/Lambda_prime`.

Only after all magnitudes pass, XOR them into the zero-filled working word in
ascending position order. Recompute all 64 syndromes and require all zero;
otherwise status 5. Then and only then validate the 191-byte common-block
framing and local CRC-32C; RS has no transport pad. A local-check failure is
status 6. A successful non-clean decode is recovered. No failure exposes
partial bytes.

There are zero retries, alternate erasure fills, erasure subsets, list paths,
check-directed searches, or post-check candidate choices. The result and
status are therefore stable even outside the algebraic radius. A resource-cap
failure is status 11. Decoder failure precedence is input/status 3, erasure or
degree boundary/status 4, unique-codeword algebra/status 5, local check/status
6, and resource/status 11 at the point its exact cap would be exceeded.

### 17.5 Exact resource bounds and conformance

One protected unit uses at most 64 syndrome coefficients, 65 erasure-locator
coefficients, 64 Berlekamp--Massey input coefficients, 33 unknown-error-locator
coefficients, 65 full-locator coefficients, 64 evaluator coefficients, 64
derivative coefficients, and 64 retained correction positions. Chien search
evaluates exactly 255 positions. Across the entire unit the implementation must
not exceed 80,000 field multiplications, 128 field inversions, or 1,000,000
promoted primitive steps. Direct-reference accounting charges exactly eight
steps for each field multiplication and one step for each inverse call. The
immutable alpha-power table is derived once outside decoding and contributes
no per-decode steps. Generic recipe-VM primitive-step accounting remains the
separate Section-12 opcode/iteration accounting. Fixed-size arrays at these bounds are sufficient;
allocation or work proportional to untrusted values beyond them rejects with
status 11.

`conformance/rs255-191-v0.json` is the shared canonical corpus. Its exact
SHA-256 is
`d4dcc0cc441f42c66dc19d6db636733fc577751baf073dc7f951cd3c3dd23f72`.
It binds field operations; the derived generator; systematic words for zero,
endpoint, ascending, and non-palindromic data; single errors at both data and
parity endpoints; mixed equality-bound cases; one-beyond cases; and an exact
intermediate trace through syndromes, `Gamma`, `T`, `U`, locators, `Omega`,
roots, and magnitudes. Its named mutant list is mandatory negative coverage:
wrong modulus or roots, reversed wire coefficients, parity-first or LSB-first
symbols, wrong position power, missing erasure transform or prefix drop, wrong
Chien exponent, missing Forney `X`, ordinary rather than formal derivative,
nonzero erased fill, sequential correction before magnitudes are frozen,
skipped root-count check, and skipped post-syndrome check. Both implementations
must consume the identical corpus bytes and independently rederive its field,
generator, encoder, intermediate, success, and rejection expectations.
