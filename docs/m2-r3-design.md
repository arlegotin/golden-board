# M2 R3 pre-result redesign freeze

| Field | Value |
|---|---|
| Status | Gates 1–7 remain exact for the sole R3 v7 candidate; prior Gate-8 evidence is superseded only by the acquired Linux verifier provenance refresh and its Gate-8 rerun is pending |
| Roadmap | Revision 10, M2 Linux verifier provenance refresh |
| Date | 2026-08-21 |
| Trigger | No R2 candidate survived through gate 6 |
| Active candidate | `eh72-hier-r5-r2-r1-crc32c-v0` |
| Wire profile version | 7 |

## 1. Scope and non-result boundary

This document is the normative R3 restart overlay for M2. It changes only the
transport, inventory, placement, manifestation, and damage-accounting rules
named here. Unchanged M2 rules continue to come from
[`m2-spec.md`](m2-spec.md), [`m2-plan.md`](m2-plan.md), and the promoted files
under `spec/`.

The complete R1 and R2 evidence remains failed evidence. R2 candidate bytes
and their exact owner inputs are retained under
`artifacts/history/m2-r2-candidates/`; R3 MUST NOT rewrite, relabel, or admit
those bytes under the new rules. `owners/archive-files.sha256` binds the
candidate trees/direct owners and `owners/bound-inputs.sha256` binds every
profile-policy input plus the exact revision-8 roadmap. The R2 damage-manifest
SHA-256 values are:

- `eh72-r2-crc32c-v0`:
  `b561fab93531d97a83fb98342f0da09e3d698e7277249253b15a406ab9525086`;
- `eh72-r3-crc32c-v0`:
  `dd0c9d3359ac475f6e5e5b3ce11a96acf89bbe6b04cd19c819d16e237cb56138`.

The first pre-clarification v7 six-file tree is retained only as pre-D history
under `artifacts/history/m2-r3-pre-d7-mapping-clarification/`; its exact old
candidate and owner inputs are bound by that directory's
`archive-files.sha256`. After the accepted-hypothesis mapping identity was
clarified in the smallest damage owner, the dependent owner DAG was atomically
re-frozen and the canonical tree was independently regenerated. The retained
old tree is never a canonical gate or damage input.

The next clarified gates-1--5 tree exposed a result-artifact ownership gap
before any damage observation existed: v1 had not completely frozen the root,
family, shard, decoder-result, boundary-KAT, or independence-proof framing and
persistence rules. That six-file tree and its exact then-current damage,
limits, promotion, and reproduction inputs are retained under
`artifacts/history/m2-r3-pre-damage-artifact-schema-clarification/`, bound by
its eleven-row `archive-files.sha256`. The canonical candidate path was absent
while the pre-D schema clarification was atomically re-frozen and gates 1--5
were regenerated. The retained tree remains evidence that the unchanged
carrier bytes passed those gates under its bound owner set; it is not a current
gate-6 input.

After that schema owner was re-frozen, the independently regenerated gates-1--5
tree exposed one final proof-only ambiguity before any damage observation: the
nine independence predicates did not own exact witness counts and violation
units. That six-file tree and its exact then-current owner inputs are retained
under
`artifacts/history/m2-r3-pre-independence-witness-clarification/`, bound by its
eleven-row `archive-files.sha256`. The canonical candidate path was absent
during the exact witness refreeze. That refreeze is now complete and the final
canonical tree has been independently regenerated through gates 1--5.

No R3 D0--D7 observation may be generated, decoded, retained, or used to
choose a parameter until Section 12's freeze barrier closes. Bounded algebra,
capacity arithmetic, route-size measurement, placement proofs, synthetic
code-boundary KATs, and parser/serializer tests are pre-result design work. The
barrier first closed without a v7 carrier or R3 D0--D7 observation. The
clarified carrier was then independently reproduced and gates 1–5 passed. The
final independence-witness owner DAG was frozen and its canonical carrier was
again reproduced byte-identically through gates 1--5. Two subsequent complete
gate-6 create attempts executed R3 D0--D7, but each ended in
independent/tooling disagreement and took the owned write-nothing path. The
pre-attempt tree and owner tuple are archived. After the bounded convergence
repairs, the complete rerun converged across the oracle, fresh Python decoder,
and persistent Rust decoder and atomically published the canonical gate-6
bundle. Its raw SHA-256 is
`77697d720bf0df357217d739935931b470cdfda24f7ed3be4b92fc2e6f10e497`
and manifest identity is
`b7024bed03ef0ee4b7c0f89bd5ac626a285dc35c39d8642a3d820570670e7177`.
All 10,038 cases and four boundary KATs pass with zero wrong accepts. Gate 7
then published the independently byte-identical proof, raw SHA-256
`e73a4a186af1a79d1bea3ec73911aa9c4da7cde09e74f36d08e8019d26082964`,
identity
`303b3f710c17517072221156bc5376841970720da3081ae82193243ce009eb04`;
all nine predicates pass with zero violations. The Gate-8 rerun under the
revision-10 verifier provenance owner remains pending.

## 2. Decision and identifiers

R3 admits exactly one new candidate:

| Field | Frozen value |
|---|---|
| profile ID | `eh72-hier-r5-r2-r1-crc32c-v0` |
| profile version | 7 |
| transport ID | `eh72-hier-repetition-v0` |
| section check | `crc32c-v0` |
| placement ID | `affine-slot-then-interior-v1` |
| common-block bytes | 191 |
| inner code | existing shortened extended-Hamming `[72,64,4]`, 24 codewords |
| semantic copy count | exactly 1 |
| physical replica factors | exactly 1, 2, or 5 as Section 4 assigns |

Versions 1--6 and their profile IDs are evidence-bound and are never reused.
For D7 interoperability fixtures, the active route registry order is exactly
v7, v2, v3, v4, v5, v6. Those five legacy rows are negative fixtures, not R3
candidates and cannot advance a gate. The exact route-conflict alternate is
`eh72-r3-crc32c-v0`, profile version 3. The five cross-profile splice sources
are versions 2--6 in ascending version order. The archived version-1 profile
is not an active R3 fixture. Ordinary `OBS_UNITS` discovery tries the six
registry recipient-unit procedures in that exact order for every serialized
input, without short-circuiting, but only v7 may establish an R3 artifact;
legacy results remain bounded foreign-profile diagnostics. `OBS_BITS` and
`OBS_MATRIX` follow only complete locally accepted observed routes, including
the v3 route in its named D7 conflict case, rather than injecting fixture
profiles as hidden hypotheses.

R3 uses direct physical repetition because the roadmap's fallback order puts
more direct replication before a more complex product or symbol code. CRC32C
is retained because the CRC64 EH manifestations already failed the exact shell
fit gate. Neither fact predicts or claims an R3 damage result.

## 3. Semantic bytes versus physical lanes

The 191-byte common-block grammar is unchanged. Every v7 block has
`profile_version=7` and `semantic_copy_id=0`. A physical replica lane is a
byte-identical EH72 encoding of that same common block. `replica_index` is
derived physical metadata; it is never transmitted in, or trusted from, the
common block.

Every inventory entry has semantic `copy_count=1`. Physical repetition is a
separate, fully charged construction. Every repeated envelope byte, common
header, payload byte, local check, transport pad, and parity bit counts once
per physical lane.

This separation is incompatible with `eh72-replicated-v0`; it therefore uses
the new transport and profile identifiers above. No implementation may treat a
physical lane as a second semantic value or vote among distinct valid common
blocks.

## 4. Inventory v1 and protection factors

The inventory section has section version 1 and its payload has
`inventory_version=1`. Its entry remains exactly 20 bytes. Existing fields
retain their offsets, with these v1 constraints:

- byte 10, `copy_count`, is exactly 1;
- flag bit 0 remains `has_game_ordinal`;
- flag bits 1--3 encode the literal `physical_replica_count` and admit only
  the integer values 1, 2, and 5;
- flag bits 4--7 are zero.

Thus the flags byte is exactly
`(physical_replica_count << 1) | has_game_ordinal`. Any other factor, reserved
bit, or semantic copy count rejects the inventory.

The assignment is exact:

| Owner class | Section domain | Factor |
|---|---|---:|
| `required-spine` | section IDs 1, 2, 3, and 16, exactly | 5 |
| `replicated-m2` | every non-spine section whose frozen owner/capacity class is `replicated-m2`, including replicated real/capacity, generic-support, and reserve | 2 |
| `nonreplicated-m2` | every section whose frozen owner/capacity class is `nonreplicated-m2`, including nonreplicated real/capacity and load | 1 |

The set `{1,2,3,16}` is exactly the provisional `m2_required` closure and is
exactly the factor-5 set. Factor 5 outside that set, factor 2 on a
nonreplicated owner, factor 1 on a replicated owner, or a mismatch between the
closure and spine set rejects the complete manifestation. An M3 replacement
consumes the same frozen capacity-class envelope and physical factor as the
capacity it replaces; changing that class or factor reopens M2 before any new
outcome.

The route fixes only section 1's ID, inventory version, factor 5, and initial
grouping. A decoder groups and recovers the section-1 fragments in fives,
assembles one checked inventory, and only then trusts its factor declarations
to derive every later physical group. Without a unique valid inventory, the
decoder may retain bounded observed diagnostics but makes no catalog,
completeness, dependency, or tier claim.

## 5. Physical IDs and two-stage placement

Logical fragment groups are ordered by `(section_id, fragment_index)`.
For group `g`, let `rho(g)` be its inventory-declared factor and define:

```text
K(g) = sum rho(h) for every group h before g
physical_unit_id(g,r) = K(g) + r + 1,  0 <= r < rho(g)
```

Physical IDs are therefore contiguous and group-contiguous. This ordering is
used by `OBS_UNITS` regardless of arrival order. The first five IDs are the
five physical lanes of inventory fragment zero. An ID/header/factor mismatch
is corrupt input and never remaps an observation.

For candidate geometry `(S,W)`, define:

```text
I = S - 2W
P = I^2
Q = floor(P / 1728)
w = max(32, floor(I / 8))
a = 2I - 1
offset = (40503 * 7 + 257W) mod P
```

Load probes fill the residual whole-unit capacity so the physical IDs are
exactly `1..Q`; the remaining `P - 1728Q` interior cells are fixed pad.
Set the unit-permutation offset to zero. Select the smallest integer
`B` in `1..Q-1` for which `gcd(B,Q)=1` and the following predicate holds for
each `d` in `1..4`:

```text
m = (B*d) mod Q
for delta in {m, m-Q}:
    x = (a * 1728 * delta) mod P
    (q,t) = divmod(x,I)
    column_separation = min(t,I-t)
    row_deltas = {q} if t=0 else {q,(q+1) mod I}
    for row_delta in row_deltas:
        row_separation = min(row_delta,I-row_delta)
        max(row_separation,column_separation) >= w
```

If no such `B` exists, that geometry does not fit. No damage seed participates
in this search.

The two possible row deltas are the exact row-major carry cases; this is not a
flat-distance approximation. A nonwrapping square/window of side `w` spans at
most `w-1` coordinates on either axis. For zero-based physical ordinal
`k=physical_unit_id-1` and encoded bit
`t` in `0..1727`:

```text
slot = (B*k) mod Q
logical_flat = 1728*slot + t
physical_flat = (a*logical_flat + offset) mod P
```

The inverse is exact: invert the cell affine modulo `P`, divide by 1728 to
obtain `(slot,t)`, then apply `B^-1 mod Q` to recover `k`. An inverse landing in
the fixed-pad tail is pad, not a protected unit. Candidate and ownership unit
rows record `replica_index`, `physical_replica_count`, `slot`, and
`logical_bit_first=1728*slot`; none is trusted from a common block.

As a non-gating projection only, `(S,W)=(1952,128)` gives
`I=1696`, `P=2876416`, `Q=1664`, `B=15`, `B^-1=111`,
`a=3391`, `a^-1=2873023`, and `offset=316417`. The actual first-fit geometry
is derived only after the exact v7 route package exists.

## 6. Replica aggregation

For one inventory-derived physical group of factor `R`:

1. independently run the existing EH72 decoder, transport-pad check, common
   grammar, and local CRC32C on every observed lane;
2. for `R>1` and at least one observed lane, independently construct one raw
   repetition observation bit by bit;
3. for candidate bit `b`, let `e` be the number of known opposite lane bits
   and `s` the erased/absent lane count; `b` is admissible exactly when
   `2e+s<R`;
4. emit the sole admissible bit, or an erasure when neither bit is uniquely
   admissible, into the ordinary EH72 decoder; then apply the same pad,
   grammar, and local-CRC checks;
5. union all locally valid lane results and the valid repetition result,
   byte-deduplicate, and accept exactly one distinct common block.

Two or more distinct valid common blocks in one physical group are a fragment
conflict. Physical grouping happens before semantic-header grouping, so a
divergent valid header cannot escape into another identity bucket. Zero valid
blocks is `missing` only when every lane is absent; otherwise it is `corrupt`.
REP1 has no repetition candidate. There is no Cartesian search, check-directed
choice, or majority over different valid semantic bytes.

The chosen fragment is `verified` when an unchanged independently verified
lane witnesses it; otherwise it is `recovered`. Existing checked section,
inventory, dependency, tier, and artifact-state rules then apply. A fragment
conflict makes its section corrupt unless two nonidentical complete section
envelopes independently pass every check; only the latter is section/artifact
`ambiguous` under the existing taxonomy.

The work is bounded by `R+1` EH unit decodes for `R>1`, at most six candidates
and 1,728 repetition-symbol decisions for REP5. For one complete clean v7
profile traversal, canonical logical resource charging is cache-independent:

```text
24 * (physical_lane_count + count_of_factor_2_or_5_logical_groups)
```

recipient codeword-decoder invocations per complete accepted v7 route path,
plus the exact frozen repetition and assembly recipe charges. Four accepted
clean sectors therefore charge four paths even when their semantic result
deduplicates. For `OBS_UNITS`, each serialized input charges one invocation of
each of the six registry procedures; an absent ID charges no lane invocation.
The v7 path additionally charges one repetition candidate for each factor-2/5
group having at least one serialized lane. The promoted owner binds each
invocation to its exact declared package steps and freezes rejected-route and
resource-precedence charges; no value may depend on caching or implementation
short-circuiting. Exact primitive steps, scratch, and package hashes are frozen
from the final route package before manifestation.

## 7. Capacity honesty and hard fit

The R2 logical ledger projects, before the new route and load fixed point:

```text
30 required-spine fragments       * 5 = 150 units
442 replicated fragments outside  * 2 = 884 units
431 nonreplicated fixed fragments  * 1 = 431 units
                                      ---------
                                      1465 units before load
```

The 442 groups are 396 capacity and 46 reserve fragments. The 431 groups are
128 optional-real and 303 nonreplicated-capacity fragments. Thus the exact R2
capacity and reserve physical charges are preserved: 1,095 capacity units and
92 reserve units. The 105,277-byte authoring allowance, 7,141-byte reserve,
damage-threshold formulas, and 512 KiB carrier ceiling do not change; geometry
still determines each formula's realized D2/D3 value.

At the old `(1952,128)` geometry this would leave 199 load units in two load
sections with fragment counts 105 and 94 and payloads 16,384 and 14,736 bytes;
the inventory would remain 20 fragments. These numbers are a static
reconciliation check, not a selected R3 geometry or damage result.

The exact v7 route prefix is a hard pre-damage gate. For each candidate side,
the ordinary four-sector prefix, five-percent headroom, alignment, fixed pad,
and per-sector limits are recomputed. A package that requires `S>2048`, exceeds
512 KiB, exceeds any recipe/resource limit, or fails any sector fit is
eliminated before carrier or damage generation. No cap, headroom, content
allowance, or recipe semantics may be weakened to retain the candidate.

## 8. Route and recipe contract

R3 promotes new exact route-data bytes while retaining R2 route-data in the
history archive. The v7 route teaches the complete recipient behavior through
the existing bounded product-adapter model; no candidate bytes, host codec,
unbounded search, or implementation-selected map may replace its recipe
invocations and checked arithmetic. The package retains recipe IDs 30 and
101--112 byte-for-byte, adds only recipe 113 for one repetition-symbol
decision, and adds the independently reproduced 256-byte smallest-`B` table
17. Facts 8--10 are revised as one closed dependency chain:

- fact 8 uses recipe 113 and retained recipes 30/108 to teach EH72 lane
  decoding plus the factor-1/2/5 repetition relation;
- fact 9 uses retained recipe 109 plus table 17 and bounded adapter arithmetic
  to teach physical ID to unit slot to affine cell mapping and its exact
  inverse, including smallest-`B` validation; and
- fact 10 uses retained recipe 110 plus bounded inventory/group parsing to
  teach inventory-v1 factor validation, physical grouping, conflict-safe
  candidate union, fragment assembly, and section validation.

Recipe 113 accepts only factor 2 or 5 plus unsigned known-zero and known-one
counts whose checked sum does not exceed the factor. It returns the strictly
greater known bit, or a canonical erasure on equal counts. Full five-lane
aggregation and map/inverse KATs are direct adapter commitments, not giant
route recipe interfaces.

The exact interfaces, helper/export IDs, worked and held-out bytes, malformed
cases, package bytes/hash, node/edge/table counts, maximum steps, and scratch
are produced and independently reproduced before policy freeze. The route
must include synthetic KATs for:

- factors 1, 2, and 5 and all missing-lane counts 0 through 5;
- repetition boundaries `2e+s=R-1` and `2e+s=R`;
- a divergent locally valid lane, which must conflict rather than be voted
  away;
- group and arrival-order permutation;
- wrong factor, duplicate/missing physical ID, and header/group mismatch;
- forward/inverse placement at zero, last, wrap, slot-tail, and first-pad
  boundaries; and
- exact attempt, work, scratch, and boundary-plus-one behavior.

## 9. Frozen damage semantics

D0--D7 family order, transforms, polarities, coordinate-generation formulas,
samplers, D3 seeds, weight formula, strata, threshold constants, carrier
ceiling, and wrong-accept maximum remain unchanged. Candidate-derived D2/D3
coordinates are regenerated from the frozen formulas against the v7 geometry,
map, and ownership only after the freeze barrier closes. The two operator
realizations explicitly revised below, candidate-derived physical targets, and
v7 resource/package rows change normatively; no retained R2 observation is
reclassified.

The exact R3 target rules are:

- D4 enumerates every physical unit ID; D6 remains four shell sectors times
  every physical unit ID. Loss of one factor-2/5 lane is recoverable; a
  factor-1 optional section may become incomplete explicitly.
- D5 permutations operate on numeric physical IDs and grouping is restored
  from those IDs plus the checked inventory.
- the three mapping mutants retain the clean unit-slot permutation exactly and
  rewrite all `Q` lanes under, in order: identity instead of the cell affine,
  clean cell-affine offset plus one modulo `P`, and cell multiplier `2I+1`
  with its exact inverse. No R3 D7 case mutates `B` or the slot permutation.
- local-check, inner-code, cross-profile-splice, and algebraic-one-beyond
  mutants rewrite every lane of the selected logical group so an untouched
  lane cannot make the case vacuous. The inherited mutation is applied
  independently to each replica with the same ordered common-byte,
  codeword-position, and encoded-bit offsets; replica order never selects a
  different mutation.
- section-check mutants rewrite every lane of every fragment in the selected
  section.
- the `valid-copy-conflicts` family keeps its ID/order/count but its sole v7
  operator becomes a valid-replica-lane conflict. In section 1, fragment 0,
  replica index 0, XOR common payload byte 0 with `01`, retain every common
  header identity field, recompute the local CRC32C, and EH72 re-encode that
  lane; replica indices 1--4 remain clean. The five per-input diagnostics show
  their respective locally valid bytes, the group has two distinct candidates,
  section 1 is corrupt, and the artifact explicitly fails. No majority hides
  the conflict.
- `missing-unit-one-beyond` keeps its family ID/order/count but omits exactly
  physical IDs 1--5: all five lanes of section 1, fragment 0. This is one
  beyond REP5's four-erasure boundary.
- D2-plus-one and D3-plus-one regenerate their parent coordinates from the
  exact v7 D2/D3 formulas and streams, then apply the unchanged plus-one rule.

The D7 family count remains 408. D4/D6 counts remain candidate-derived. Add
direct, non-family KATs for REP2 and REP5 correction/unclaimed boundaries;
they do not replace or enlarge a damage family. A separate direct KAT supplies
two nonidentical, complete, structurally valid, check-valid section candidates
and requires section/artifact `ambiguous`, preserving the complete-candidate
taxonomy that the revised valid-replica family no longer exercises. This KAT
is required by the D7 gate.

R3 also freezes the already diagnosed result-projection repairs before a new
outcome: a unique eligible v7 hypothesis derived from a route or `OBS_UNITS`
retains every observed fragment diagnostic and independently discovered
checked section even when inventory is unavailable. The route-fixed section-1
identity remains reportable: a divergent or present-invalid initial group
makes section 1 `corrupt`, while all five initial lanes absent makes it
`incomplete`. Only independently checked later sections are named; every other
catalog identity absent without inventory is evaluator-expanded to `unknown`.
Section attempts are charged after complete header/dependency/payload/check-
width structure and deduplication but immediately before stored-check
comparison. Consequently a wrong check ID with inconsistent width is not an
attempt, while wrong stored byte order is one attempt. Python, Rust, and the
independent oracle must emit byte-identical complete decoder results.

Fragment diagnostics use unsigned-16 `65535` as the absent
`replica_index`/`physical_replica_count` sentinel. Before a unique inventory,
only the route-fixed initial physical IDs 1--5 may expose count 5 and indices
0--4; every other row uses both sentinels. In the valid-replica conflict row,
the five input rows expose indices 0--4/count 5 and each row's own valid common
block digest; physical-lane and repetition candidates consume no section
attempt. Only a deduplicated, structurally complete section envelope consumes
an attempt, including an independently discovered envelope when inventory is
unavailable.

## 10. Generated schemas and independence proof

R3 bumps the candidate-manifest, ownership-ledger, capacity-ledger,
decoder-result, damage-manifest, and independence-proof schema IDs to v1.
Archived v0 bytes retain their old meanings. At minimum:

- section rows expose semantic copy count and physical factor separately;
- unit/fragment diagnostic rows add `replica_index` and
  `physical_replica_count`, using the frozen absent sentinel when neither a
  unique inventory nor the route-fixed initial-group rule derives them;
- unit rows bind physical ID, group identity, slot, bit range, encoded digest,
  and factor;
- capacity rows multiply every physical byte/cell charge by factor; and
- resource rows bind the exact v7 recipient package and both per-lane and
  repetition-path work.

Gate 7 is separately recomputed and may run only after gate 6 passes. Its
physical proof replaces semantic-copy-floor predicates with exact checks that:

1. every logical group has exactly its inventory-declared 1, 2, or 5 IDs;
2. those IDs, slots, and mapped cell sets are distinct and totally partitioned;
3. every factor agrees with the spine/replicated/nonreplicated owner rule;
4. the final-cell separation predicate holds for every factor-2/5 lane pair;
5. D2 cannot cover corresponding bits in two lanes, and D4/D6 remove at most
   one lane from a required group;
6. section, dependency, inventory, shell-route, and total-ledger closure still
   reconcile; and
7. every bound D0--D7 promise and wrong-accept row agrees with the retained
   damage evidence.

The nine proof rows have exact witness counts, in the order above and in the
promoted damage owner: `3182656`, `4161600`, `978944`, `3181248`, `4161600`,
`1282176`, `37844`, `1362`, and `10038`. A violation is not inferred from that
count: each row uses its separately frozen unit, including one
logical-group/condition pair for group topology, the eight class totals plus
the total and three factor aggregates for ledger reconciliation, and the
`1279 + 78 + 4 + 1` group/dependency/sector-removal/total-closure units for the
inventory predicate. The four boundary KATs are prerequisites, not damage
cases: they add no row-9 witnesses, while a failed KAT makes the D7 family
non-pass and therefore makes all 408 bound D7 case witnesses violate. Both
implementations fully enumerate and recompute every row before rendering the
same canonical proof bytes.

No candidate manifest, clean carrier, expected route bytes, evaluator section
table, or damage answer enters the observation-only decoder.

The v1 damage evidence is one closed, bounded bundle under the exact candidate
`damage/` directory. It contains one root manifest, exactly eight family
manifests, and the canonical nonempty case shards. The root binds common case
rows, boundary-KAT results, owner bytes, and raw candidate bytes without
binding family-file hashes; shards bind the root identity; family manifests
bind the root identity and raw shard hashes. That ordering is acyclic and lets
both implementations reproduce the same bytes. Every canonical file is at
most 1 MiB, every shard has at most 256 rows, the complete directory has a
fixed file/aggregate-byte ceiling, and unknown files, subdirectories, links,
partial states, or mismatched existing bytes reject without overwrite.

The complete gate-6 directory is staged, cross-checked against the independent
oracle/Python/Rust projections, fsynced, and atomically published only in an
explicit create mode. Check mode cannot start the first corpus. A converged
candidate failure is still published as losing evidence; an implementation
disagreement is a tooling blocker and writes nothing. If gate 6 passes, gate 7
separately and atomically adds the byte-identical v1 independence proof,
whether that proof passes or fails, without rewriting gate-6 evidence.

## 11. Selection and stop rules

The v7 profile is the sole active R3 candidate. It has passed gates 1--7 and is
eligible for the existing P8/Linux/recipient/human sequence. The prior Gate-8
run is historical after the local verifier identity changed; the exact
revision-10 reopen preserves Gates 1--7 but admits no current finalist or
preference until Gate 8 reruns. Its
outcome-independent Gate-8 paths, schemas, preimages, selection, bundle, Linux,
and report-overlay contract is frozen in `spec/gate8-policy-v0.toml`; that owner
contains no observed Gate-8 hash or result. Its sole-candidate
Candidate-ready IDs are conditional serialization rules, not an observed
preference. Any first failure is retained normally and later gates remain
`not_evaluated`. If v7 fails at a later gate, M2 returns to `Needs revision` or
`Stopped` without a preferred/finalist row and without changing the frozen
damage corpus.

## 12. R3 implementation freeze barrier

The implementation order is mandatory:

1. retain the complete R2 candidates and exact old owners in a fail-if-exists
   history tree;
2. land this design, the dated decision, roadmap revision 9, and phase-aware
   repository admission;
3. implement inventory-v1, factor-aware codecs, the two-stage inverse map, and
   synthetic KATs independently in Python and Rust;
4. generate and independently reproduce the exact v7 route/package bytes,
   metrics, examples, and malformed corpus; reject if the hard shell gate
   fails;
5. promote the complete bootstrap, route, profile, damage, schema, and
   resource owners together, bind their hashes, and regenerate full-set limits
   independently;
6. independently generate byte-identical semantic, carrier, candidate,
   ownership, capacity, density, and placement-proof artifacts and close gates
   1--5;
7. only then run the Section-9-adjusted, otherwise unchanged complete D0--D7
   family/order/count corpus through the independent oracle, fresh Python
   decoder, and persistent Rust decoder; and
8. run gate 7 only after a real gate-6 pass, then continue in the existing gate
   order.

No partial owner hash, provisional route byte string, static projection, or
synthetic KAT is an R3 candidate outcome.

The final owner paths are `spec/bootstrap-v1.md`,
`spec/profile-policy-v1.toml`, `spec/damage-policy-v1.toml`,
`spec/route-data-v1.json`, and `spec/profile-limits-v1.toml`; their atomic
admission record is `spec/m2-r3-owner-promotion-v1.toml`. A `blocked` record is
deliberate and does not weaken this section: it permits only implementation,
bounded algebra, and synthetic owner KATs. The exact route and limits paths may
be absent while blocked. The current admitted record is complete and
`pre-result-frozen`; partial tracked bytes reject. Its final damage, limits,
and promotion SHA-256 values are respectively
`b3b28f00d3ba04addbed4517eb1abb4ecd02796176eaaecdbc1d47f1f39509df`,
`32c2bd0cb978eb800bed7f8ac1c7db223b593b4cf3bad951a9ce4cdc3a568902`,
and `8c30ae216f5a3fd8ee13f2821d38412afa6c50303c9140cbe54da8610df9cd8d`.
Steps 6–8 are complete for the current final-owner tree. It passed gates 1–5 with
candidate-manifest identity
`d783917d34bc6fb472ea7e20c989562092707c516195019434e01f2bc6f68681`
and raw manifest SHA-256
`38839aa28561ff2bec0997a80d8dc938e876526c25f40e23b6a78844f8fc1d86`;
Python and Rust reproduced all six canonical files byte for byte. The preceding
raw manifest
`4439abb20aeb4943d9f3dddd4b2b914c08f3a411b791d2ced797533351168019`
with identity
`69b4052299e43a675683361e6a7fa83798b7b3646c873233cfbdd18432ac4cf4`
and its owner tuple are retained under
`artifacts/history/m2-r3-pre-gate6-convergence-clarification/` as history only.
Two complete gate-6 attempts executed R3 D0--D7 but ended in
independent/tooling disagreement and wrote no damage bundle. After the bounded
repairs, the complete rerun converged and atomically published the 10,038-case
gate-6 bundle with zero wrong accepts. Gate 7 then published the independently
byte-identical nine-predicate proof with zero violations. The candidate
preserves exact gates 1–7 while the revision-10 Linux verifier provenance
refresh reopens gate 8; no current finalist or preference is declared.
