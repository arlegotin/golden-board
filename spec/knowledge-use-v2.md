# Revised carried knowledge/use development evidence

This additive owner binds finite automated use of the actual four observed
route2 prefixes to supplied recovered content. It changes no historical
Gate5 owner, evidence, result or recipient record. The output is development
evidence, **not a complete Gate5 pass**, a fresh human acquisition result,
a universal reconstruction proof, a resource/damage proof or promotion.

The dependency root and twelve-fact meanings retain bootstrap-v0 §5 and
route-definitions-v2. Trial, inference and composing the carried primitives
remain permitted. A source hash, English relation name or successful host
content parse alone establishes none of the relationships checked here.

## Input boundary and API

`build_knowledge_use_v2(prefixes, *, side, width, required_stream, all_stream,
body_payloads)` returns canonical-manifest-v0 bytes.
`validate_knowledge_use_v2(raw, <same inputs>)` first checks canonical input,
then regenerates the complete evidence and requires exact bytes. Missing,
failed, reordered, altered, additional or stale evidence rejects. There is
no success-by-default field, retained result input or evidence cache.

Inputs are exactly:

- `prefixes`: a tuple of four immutable byte strings, indexed by sector0..3;
  each64..32768 bytes and ending exactly at its declared prefix boundary.
- Integer S64..2048 and W8..128, both divisible by8, with2W+8<=S. Booleans
  are not integers. Each complete prefix must fit W(S-W) cells.
- Both required and all immutable content streams, each4..1048576 bytes.
  Missing streams cannot yield this complete-context evidence.
- A plain dictionary of1..4096 decoded body byte strings keyed by nonzero
  u32 section ID; each body1..16384 bytes, total<=1048576. IDs100 and200
  are mandatory. Additional bodies are identity-bound only; their presence
  does not establish complete checked-inventory coverage.

The producer reads no files and imports no authoring, source-fixture, carrier,
route or slice builder. It consumes the same observation-only route and numeric
relationship validators as recipient admission, plus the separate recovered-
context validator. A caller can supply source-equivalent bytes: this API
cannot infer their provenance. Eventual integration must separately bind these
exact input hashes to fresh source→carrier→actual decoder evidence. In
particular it does not claim raw-square route acquisition from prefix inputs.

## Replayed observations and fact graph

For each sector independently, run `decode_observed_route_v2` on its supplied
prefix and geometry. Require all48 records,12 numeric DEFINE values,33 carried
WORKED/HELD_OUT examples, admitted profile8 compact program and endpoint1.
The receiver executes the carried examples, checks mapping/transport program
refinement, derives the active mapping from table17 and109, and checks the
actual finite numeric definitions. Full numeric meaning remains owned by
route-definitions-v2, content-teaching-v2 and position-teaching-v2, not by
an expected route byte string. All four observed package byte strings and
corresponding DEFINE value byte strings must agree.

Reparse the admitted record frames only to enumerate exact record byte ranges,
value ranges and example references. Offset0 is the first calibration byte;
local shell bit span is byte_offset*8, byte_length*8 under the owned sector
scan. Each frame includes its eight-byte header. All spans end exactly at
prefix length. DEFINE value begins14 bytes after the record payload start.
Every WORKED/HELD_OUT fact and recipe reference comes from its observed payload.

Use this exact graph (fact,stage,consumed facts):

```
1  0  []
2  0  [1]
3  1  [1]
4  1  [2,3]
5  2  [3,4]
6  2  [5]
7  3  [6]
8  3  [6,7]
9  4  [6,8]
10 4  [7,8,9]
11 5  [10]
12 5  [11]
```

Derive a topological order from these edges (smallest available fact ID first),
require every consumed definition earlier in the observed DEFINE order and
require the transitive ancestor closure of endpoint fact12 to contain all
facts. Reject duplicate, missing, late or unreachable definitions. The graph
is the explicit owner interpretation of the observed stage/fact identities;
it is not an extra carried dependency record. This finite fact-use check
makes no claim to a new universal first-operation interpreter/linter.

For each route's immutable checked fact12 commitment, run
`validate_recovered_context` against the supplied streams and decoded bodies.
Require required_context_checked, all_context_checked and
section_membership_checked all true. This rechecks actual typed references,
required Position extraction, all-stream DATA/OPAQUE namespaces, game/fixture
and Move16/Position relationships, and section100/200 membership. Failure
rejects this evidence; it does not alter transport availability or choose a
replacement stream by chess plausibility.

## Ninety-six bounded rejection probes

Order is sector0..3, then fact1..12, then `remove`, `contradict`.

`remove` deletes only that entire DEFINE frame, changes route record count
48→47, and recomputes body byte length and total prefix cells; package byte
length and all remaining bytes stay unchanged. The recipient must reject
with classification `record-structure`. This is **structural presence
ablation**, not proof of semantic use: the closed skeleton already rejects47.

`contradict` XORs1 into the final byte of that DEFINE's numeric value, keeping
every frame/count/length unchanged. The recipient must reject during local
numeric relationship validation, classification `definition-relationship`.
These are48 finite relationship contradictions, distinct from the48 presence
ablations. They accompany the positive arithmetic, layout, codec, miniature
control and recovered-context checks; they do not prove every possible
incorrect interpretation impossible. Resource exhaustion, an unrelated
rejection, an exception or successful admission fails evidence generation.

Classifications are language-neutral. Implementation exception strings may
be local diagnostics but are not equality fields. Each row binds mutated
prefix length/hash, fact, sector, operator and `success:false`.

## Repair coverage and exact canonical output

The complete ordered repair mapping is:

| Repair | Fact IDs | Recovered context required |
|---|---|---|
| C01 |1,2,3,4,5,6| none |
| C02 |5,6| none |
| C03 |7,8,9| none |
| C04 |9| none |
| C05 |8,10,11| none |
| C06 |7,10,11| none |
| C07 |11,12| required, all |
| C08 |7,8,10,11,12| required, all |
| C09 |12| required, all, section-membership |
| C10 |12| required, all |
| C11 |7,9| none |

These rows locate the carried repair relationships. They do not replace
physical ownership, complete damaged-state validation, participant handoff
provenance or fresh acquisition with an automatic “finding closed” claim.

The closed top-level object has exactly:

- `schema`: `golden-board.m2-knowledge-use/v2`.
- `profile_id`: `eh72-hier-r5-r2-r1-lzss-crc32c-v1`.
- `scope`: `carried-finite-use-and-ablation-development`.
- `inputs`: exactly `side`, `shell_width`, `prefixes`, `required_stream`,
  `all_stream`, `decoded_bodies`. Prefix rows have sector_id,bytes,sha256;
  stream objects have bytes,sha256; body rows have section_id,bytes,sha256
  in ascending section ID. Hashes identify raw inputs; they are not semantic
  validation substitutes.
- `topological_order`: derived12 integer IDs.
- `route_rows`: four rows in sector order, each exactly `sector_id`,
  `package_sha256`, `mapping_sha256`, `record_rows`, `fact_rows`,
  `example_rows`, `context`.
- `repair_coverage`: eleven rows in C01..C11 order, each exactly repair_id,
  fact_ids,context_claims, with context claim strings from the table above.
- `ablation_rows`: the96 rows, each exactly sector_id,fact_id,operator,
  bytes,sha256,classification,success.
- `summary`: exactly route_count=4, definition_count=48,
  example_count=132, structural_presence_rejections=48,
  relationship_contradiction_rejections=48, recovered_context_count=4,
  result=`pass`. This result is limited to the named development scope.

A route `record_rows` row is exactly record_id,stage,kind,byte_offset,bytes,
payload_bytes,sha256; its digest includes the complete frame. A `fact_rows`
row is exactly fact_id,stage,consumes,definition_record_id,value_byte_offset,
value_bytes,value_sha256,worked_record_ids,held_out_record_ids. IDs for each
kind retain observed order. An `example_rows` row is exactly record_id,fact_id,
recipe_id,kind,input_bytes,output_bytes,status,success; kind is `worked` or
`held-out`, status is the carried u16 outcome, success=true means its carried
output agrees with generic execution (including nonzero-status suppression).
`context` has exactly required,all,section-membership with value `checked`.
`mapping_sha256` hashes the canonical mapping object already owned by route-v2.
No document hashes itself. Evidence output is bounded to1048576 bytes before
return; validation accepts only immutable bytes within that same bound.
