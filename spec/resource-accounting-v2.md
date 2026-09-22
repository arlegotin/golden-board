# Observation receiver resource accounting v2

This source owner applies only to the explicit profile8 development receiver.
Historical result schemas0/1, public decoder entry points, source owners and
reported resource bytes remain exact. This is an accounting contract, not
measured full-damage limits, a promoted candidate, or a new aggregate VM cap.

## Exact logical VM schedule

Create a fresh meter for each serialized observation. Every counter and every
intermediate sum/product is an exact nonnegative u64; reject bools. Before an
addition/multiplication would overflow, stop with resource-limit and preserve
all previously completed charge events. The overflowing event is not charged.
An event charges its complete declared instruction cost and peak typed scratch
before execution, including nonzero status or a later semantic rejection.
Caches replay the same logical charge; they never discount it.

* OBS_UNITS requires the four-byte count header first. A declared count above2389
  is resource-limit immediately, even if the repeated rows are truncated.
  An in-range count then requires exact valid repeated-row framing. It visits ascending input ID and registry
  order8,2,3,4,5,6,7. Each present input charges its profile's declared30 row:
  24 calls for EH profiles2/3/4/7/8; one for RS5/6. A wrong input byte width
  still invokes the registered shape-check procedure and receives this owned
  logical charge, but does not enter the native transport kernel.
  Finish those lane procedures before recovery in registry order8,2,3,4,5,6,7.
  A reached foreign7 checked inventory traverses its groups. Final registry-wide
  no-inventory diagnostics reuse the same group keys and global attempt set.
* Square observations visit transform0..7, polarity0..1, width8..128 by8 within
  the geometry domain, then sector0..3. All route examples executed before the
  first stable reject charge their observed declared recipe cost. After the
  examples, mapping109 executes exactly0,1,P−1 in that order, including foreign
  route0/1 under this v2 receiver; charge all three. Samples do not prove a
  changed mapping program's universal refinement.
  Route2's exact admission order is package parse, mapping/transport closure
  refinement, carried record examples, table17/smallest-multiplier search,
  the three mapping109 calls, the ten fact10 embedded110 traces in their
  carried order, then local DEFINE validation. Each embedded call charges
  its full observed program and route-example adapter cost before execution;
  a failure retains that charge and stops the remaining schedule. The32
  framed WORKED/HELD_OUT records remain32; embedded traces are additional
  observed calls, not invented framed records. Legacy routes0/1
  have no program-refinement kernel event.
* At most64 complete valid route paths proceed to transport. The attempted65th
  path is global resource-limit, after retaining prior discovery costs. Every
  complete path runs its transport recovery logically, including byte-identical
  routes. Computation sharing is allowed, but may not postpone the cost until
  after a possibly failing shared recovery. Foreign paths execute their
  diagnostic procedure and never establish the profile8 artifact.
  Discover and validate every width/sector in the current transform/polarity
  view before transporting any of that view's complete routes; then transport
  them in registry-profile order, width, sector. Finish this view before the
  next view. Costs of discovering a view remain charged if its65th cumulative
  complete path later exhausts the path bound.
* For each square path, visit every extracted unit in increasing physical ID.
  Charge its observed30 declaration as above. Legacy2..4's historical2427 and
  RS5..6's2056 unit ceilings never bind legal S≤2048,W≥8 interior geometry:
  extraction is floor(P/(8*unit_bytes)). Profile7 retains its exact old mapping
  admission; profile8 uses geometry Q and checked inventory must cover Q.
* Within one logical path/profile, a present factor2/5 group charges1728 calls
  to113 and24 calls to30. Its key is profile version plus the ordered tuple of
  physical input IDs/absences, so bootstrap re-use and subsequent checked
  inventory traversal do not charge the same group twice. Distinct groups do.
  Charge a group actually reached before a failed bootstrap, not an invented
  complete inventory. OBS_UNITS has one shared path, with separate profile keys.
* Compressed bodies invoke202 once per body section ID per path, shared by
  required/all assembly. Charge before decoding, even on rejection and even
  when a native refinement or cached output is used. Raw bodies have no202
  invocation. A later route has a new logical path and new charges.
  OBS_UNITS has no observed program202, so its known channel transform incurs
  no observed-program-refinement event; square paths compare the reached
  observed202 closure at the owned body admission boundary.

VM `primitive_steps` is the sum of those recipe declarations. It excludes host
adapter operations; do not call byte scans or SHA operations VM instructions.
No per-recipe ceiling is reused as an aggregate observation ceiling.

## Section checks and failure projection

One observation owns one global set of complete candidate envelope bytes.
Validate common-block framing, consistent section/copy/fragment identity,
complete ordered fragment coverage and declared envelope length first. A
candidate consumes one attempt only if the complete section header, dependency
array, payload and declared check width are structurally eligible. Deduplicate
identical bytes before charging. Charge immediately before the first stored
section-check comparison, including inventory discovery and foreign diagnostics.
Wrong check width consumes no attempt; a wrong stored check value/order does.
The eligible structural grammar is exactly: total bytes22..32790, envelope
u16version0, nonzero u32section ID, type1..6, closure128/129, checkID1/2,
dependency count≤4095, a complete strictly increasing array of nonzero IDs
excluding the section itself, and total length18+4×dependency_count+
declared_payload_length+(4 for check1 or8 for check2). Section_version is an
unrestricted u16 at this stage. The structural attempt boundary does not
separately constrain payload length to16KiB; full inventory/section/content
admission supplies that rule. The stored check value is never an eligibility
input.
Attempt4096 is admitted. Candidate4097 causes resource-limit before comparison;
reported attempts remain4096. The set is global across paths and profiles,
including paths that subsequently conflict or fail, rather than the selected
successful path's count.

A global failure retains every completed meter event. Resource-limit clears
established profile, sections, fragment diagnostics, route profiles, accepted
hypotheses and both canonical streams. Other failures expose only the bounded
result allowed by the decoder owner. The CLI must serialize the receiver's
returned counters; it must not synthesize a zero-resource result after a
DecoderError. Owned count cap2389 is resource-limit; truncated, inconsistent or
invalid frame structure is failure. This distinction does not change old APIs.

Square-path foreign sections and fragment rows are diagnostics internal to that
path and do not enter the selected profile8 result. A wholly foreign square
retains accepted route hypotheses, route-profile identities and charges, with
empty sections/fragments and no canonical streams. The separate OBS_UNITS
no-inventory result may retain its registry-wide unambiguous checked diagnostics.

## Caches

Semantic state, route admission state, result commitments and counters start
empty per observation. Optional computation caches may remain warm, or may be
cleared. Their saturation skips insertion or evicts deterministically; it never
causes semantic failure. Identical logical work receives the same charge in
cold, warm and saturated-cache executions.
Current maximum entries remain unit/transport1000000 each, route4096,
validated-route4096, package256, evaluation4096, body4096. These are implementation
storage bounds, not a new artifact gate or permission to retain state between
unrelated observations. Cache keys include every observed program/input/erasure
value required for semantic equivalence. Cached body output is bounded16384.

## Reference adapter ledger

Adapter accounting is separate from VM instruction counting. It is a closed
set of bounded reference-kernel invocation rows, not an estimate of Python/Rust
CPU instructions, allocator object overhead, RSS, or elapsed time. Each row is
`(kernel,calls,reference_input_units,peak_workspace_bytes)`, summed across the
same logical schedule even when native computation is cached. Different kernel
unit dimensions are never added together. This table makes all adapter work
accountable without assigning a fictitious VM cost to a host validator.
Each row's peak_workspace_bytes is only that kernel's local reservation.
The resource.peak_scratch_bytes counter adds concurrently retained observation,
program, path and result buffers to that local reservation (or VM scratch).

The complete implementation must cover these kernels. Parenthetical units are
what `reference_input_units` counts; all child parsers retain their existing
source-owned bounds and fail-closed checks:

| Kernel | Logical boundary and unit |
|---|---|
| observation | one exact serialized frame; supplied bytes |
| square-view | each D4/polarity view; S² logical cells |
| shell-read | each header/prefix extraction; requested cells |
| route-frame | bounded observed prefix parser; prefix bytes |
| recipe-parse | complete compact/logical semantic validation; wire bytes |
| program-refinement | observed transitive closure comparisons; logical nodes |
| route-example | each worked/held/additional/mapping/embedded-group call adapter; input bytes |
| definition-validation | complete local numeric relationship validator; DEFINE bytes |
| mapping-search | bounded smallest-multiplier search; candidate/distance tests |
| unit-extraction | affine gathering and erasure conversion; encoded cells |
| lane-adapter | each registered physical lane procedure; supplied bytes |
| repetition-adapter | each present group; factor×1728 symbols |
| common-frame | local profile/header/pad/check interpretation;191-byte blocks |
| section-assembly | complete fragment candidate construction; common-block bytes |
| section-check | eligible deduplicated stored-check comparison; envelope bytes |
| inventory | admitted payload parse and identity binding; payload bytes |
| group-layout | expected physical identities; emitted lane rows |
| dependency-closure | checked inventory reachability; declared dependency edges |
| body-adapter | body framing and atomic output adaptation; stored body bytes |
| content-validation | full content-v0 assembly/validator; assembled stream bytes |
| result-selection | deterministic downstream comparison; compared result bytes |
| result-render | canonical diagnostic-array preimage and closed result serialization; emitted bytes including wrapper, or first attempted out-of-bound byte |

### Other canonical reservations and lifetimes

Caller-owned input wire and optional computation caches are outside reference
scratch. The reference machine keeps no optional cache: cached implementations
must reproduce its work and workspace reservations. The observation adapter
itself reserves zero bytes. Allocate the normalized square or OBS_UNITS pool
only after the complete serialized frame passes framing; malformed frames
retain no partial normalized pool. Normalize a square into S²
one-byte cells, held through every view. Transform/polarity views are coordinate
adapters and allocate no second square. A shell header reserves64 bytes; a
prefix reserves its declared bounded length through complete route validation.
Each route-frame parser reserves8 bytes per record for offset/length indexes.
The64-byte header remains live alongside the full prefix. Always charge one
512-cell/64-byte header request for each attempted width/sector, even if erasure
or geometry prevents extracting it. An absent header ends that attempt.
For legacy route0/1, validate calibration/envelope/profile/count/extent before
the full-prefix request; a bad calibration therefore has no prefix/frame event.
For observed version2, bound its declared extent first and request that prefix,
then validate its calibration/envelope/count/length. A successful prefix read
stays live through parsing. An erased read receives the requested shell-read
charge but no route-frame event. Route-frame fires immediately before the
record-frame scanner, after those route-header checks, including a scanner
rejection. Recipe-parse fires before each reached observed package parser,
including parser rejection; a route whose earlier framing/skeleton check fails
does not reach that event. The existing explicit excessive VM declaration check
is resource-limit before recipe-parse for a recognizable version2 package header.
The route-frame index area is local to its scanner and is released before
recipe parsing; parsed record indexes have no additional retained reservation.

For legacy routes0/1, distinguish generic record framing from later semantic
skeleton checks. First scan all record extents, legal kinds, monotone IDs/stages,
and total bytes of the collected kind5 packages. A failed generic scan has no
recipe-parse event. Apply the inherited recognizable profile7 declaration guard,
then parse collected packages in their wire order and reject duplicate recipe
or table identities. Next visit DEFINE/WORKED/HELD records in observed order:
check each record's fields and invoke each example as it is reached. Only after
that scan check complete fact/example pairing, standalone TABLE equality,
package-record semantic ID/stage, endpoint and kind order. Then derive the
mapping interface and execute its three owned samples. Thus a generic-invalid
package kind can stop before parsing, while a generically framed package with
a wrong semantic record ID retains parsing and prior example charges. This
explicit v2 schedule does not change historical public decoder charges.

For a complete recipe header define V=wire bytes, P=min(declared recipes,256),
T=min(tables,4096), N=min(nodes,65535), E=min(edges,262140),
D=min(table payload,1048576). These clamps only bound accounting on malformed
headers; they do not validate or repair the declaration. For compact encoding1,
X=min(1048576,V+26N); for every other tag X=V. The strict wire parser still
rejects an unknown tag; this reservation rule does not admit a fallback format.
X reserves the maximum
expanded wire, because a compact node has at least6 bytes and expands to32.
A short header reserves only V. Full semantic parsing still rejects every
out-of-domain header before its dependent parser allocation.

An immutable program reserves `V+3X+64N+64T+128P+8D`: input and expanded wire,
two additional X-byte descriptor/sequence arenas (a12-byte descriptor has four
u64 fields), eight-word node metadata, eight-word table headers, sixteen-word
recipe headers, and one u64 scalar per table payload byte. References into
node arguments use the retained expanded wire. Parsing adds48N+8E+16T+32P for
type/liveness/node work, dependency edges and table/recipe validation indexes.
Program refinement reserves32N+8E+8T for closure traversal and comparison; its
work is the total observed package node count, excluding immutable baseline
programs, regardless of the smaller selected closure. Mapping/transport comparison is one
event per complete package admission. Body comparison is one event per reached
compressed body, even if its native output is cached.

The active route retains its parsed program through examples and DEFINE checks.
Admitted programs are retained once per complete immutable wire byte string
until observation end. Historical route parsers retain their parsed packages
as soon as parsing succeeds. Admitted DEFINE tuples retain their byte sum plus
16 bytes per fact, once per exact ordered twelve-value tuple through observation
end. Repeated equal definitions share this retained reservation; their validation
events still occur for each admitted route. Each worked/held/additional/mapping adapter reserves its
input bytes, declared output byte widths (including status), and eight bytes
per input/output descriptor. Recipe VM scratch is added to the simultaneously
retained buffers, not added to all other nonoverlapping VM calls.
Parsing a byte-identical retained package still reserves a second full transient
immutable-program arena plus parse workspace. Successful admission deduplicates
its persistent storage afterward. This is the no-cache reference schedule.
The DEFINE checker's internal revalidation is included in its one local
definition-validation reservation and creates no additional recipe-parse event.
Mapping-search counts one test for each distance1..4 entered for a gcd-admitted
candidate, including the first failing distance. Skip non-coprime candidates
without a test; stop that candidate on its first failed distance. Its event is
completed on either successful selection or bounded search failure, with a
64-byte local workspace. Observation and square-view events have zero local
workspace; the normalized observation pool has its separately retained lifetime.

The finite DEFINE checker reserves eight bytes per DEFINE byte for decoded
numeric tuples/indexes and the small fixed transport/mapping relations. It
revalidates the observed program, so add the larger of recipe-parse workspace
or immutable-program storage plus four content arenas. Each miniature arena
uses the content formula below with B=577, R=29 and H=29×floor(577/14). The
complete carried base is575 bytes; its largest presentation mutation adds two
bytes. Four arenas cover the base private projection, public/authoring copies,
changed authoring records and the currently tested candidate. Scalar mutations,
role examples and action trials run sequentially. This explicitly includes
public-record views here; main recovered-content validation does not make them.

Each supplied/extracted unit reserves an eight-byte identity/index row, encoded
bytes and an equally sized packed erasure bitmap. OBS_UNITS additionally keeps
seven candidate rows per input, each191-byte common block plus eight-byte
status/reference; a square path keeps one such candidate row per extracted
unit. Unit extraction has one event per square path: work is Q times encoded
cells, and local workspace is Q times (8+2 times encoded bytes). After that
event, hold the full Q times (8+2 times encoded bytes+199) path pool before
lane processing. A lane adapter reserves supplied bytes plus191 output bytes;
the common-frame adapter reserves191 bytes. REP reserves216 packed output
bytes and two1728-byte symbol arrays. Each section assembly reserves its
candidate envelope and24 bytes per common-block input for fragment indexes.
The common-frame kernel is a fixed191-byte status/framing phase per compatible
lane or newly charged present REP group; a failed transport status may stop
before reading the slot, but still reserves/counts that logical phase. Wrong
input widths do not enter it. Section-assembly counts every selected input
common block passed to that call, including duplicate fragment indexes and
incomplete candidates, rather than all unselected lane witnesses. Only an
eligible complete candidate later consumes a section attempt.
Every retained common block has the canonical191-byte reservation, including
implementations that physically retain a digest or another compact witness.

Eligible attempted envelopes persist globally as raw bytes plus an eight-byte
index each; a stored-check event also reserves one envelope-sized check buffer.
Inventory parsing first charges a local16-times-payload reservation, then
promotes that arena to path retention until path completion. It fires only when an inventory payload parser is
actually reached, including a rejected payload; repeating section1 assembly
does not alone create an inventory event. Expected group construction reserves128Q+64I for Q
emitted physical rows and I inventory entries:48 bytes per expected row,40 per
diagnostic row and40 for lookup/group/state indexes;48 bytes per section row
and16 for its inventory index. The group-layout event first reserves its local
128Q+64I bytes, then retains128Q+64I+8edges through path completion.
Dependency traversal subsequently reserves24I+8edges concurrently with that
retained layout. These path reservations
end after the path result has been considered, before the next profile/path.
There is one group-layout and one dependency-closure event per admitted
inventory, and neither event without one. For foreign profiles2..6, first
assemble section1 copies for inventory discovery; parse and lay out any admitted
inventory, then assemble expected sections including section1 again. A failed
inventory instead leads to per-profile diagnostic assembly of all copies,
including section1. The later registry-wide no-inventory fallback may assemble
the same candidates again. These repeated section-assembly events remain;
only identical eligible envelope check attempts are globally deduplicated.

For hierarchical profiles, bootstrap section1 assembly precedes inventory
parsing and admission, including the exact square-geometry coverage check.
Only an admitted inventory reaches the later catalog traversal that assembles
section1 again. An unestablished inventory instead reaches diagnostic fallback.
That fallback groups every individually valid non-section1 lane by observed
profile/section/copy, preserving physical duplicates. Section1 uses only the
reached, uniquely accepted bootstrap group representatives with the required
inventory identity; raw section1 lanes cannot substitute for a rejected group.
Invoke section assembly once per resulting nonempty copy. Identical duplicate
fragment indexes remain in its input-work count; conflicting values or identities
reject that whole copy before an envelope check, without Cartesian alternatives.

Decoded bodies retain bytes plus an eight-byte ID each, shared between the two
tier assemblies. The body adapter reserves stored bytes plus two16384-byte
input/output buffers. Assembled required/all streams remain held through
transfer to an immutable result. Content-validation starts only after all
selected bodies decode, before checking the tier's declared assembled length.
Its initial reservation uses declared B/R and H=0; complete assembly updates
H from actual referenced region rows. Missing or malformed bodies therefore
have no content-validation event, while an assembled-length mismatch does.
The stream currently being assembled and validated is already part of that
content arena. Add it to retained assembled streams only after successful
validation; do not count a second concurrent B-byte copy of the current stream.
A result reserves48 bytes per section row,
40 per fragment row,48 per hypothesis, every retained envelope/common block,
and both streams. The40-byte fragment row uses bounded packed scalar fields and
byte-span references; it is not nine Python object slots. Result selection
reserves one candidate-sized comparison area and counts candidate bytes times
max(1,prior candidates). Here candidate bytes means the reference footprint
defined in the preceding sentences, not JSON bytes. Prior candidates are the
already deduplicated normalized results; charge before deduplicating the current
candidate. Normalization removes resource counters and accepted hypotheses.
For OBS_UNITS, selection events cover profile8 establishing candidates, or the
single final registry-wide no-inventory result when none establishes a profile.
Square paths use the explicit active-profile selection in damage-oracle-v2.
Distinct normalized result objects persist once by
complete value. A view holds128 bytes per complete route descriptor; accepted
hypotheses hold48 bytes each until observation end.
Discover the complete view's routes before processing paths in registry,
width, sector order. Admit and retain each path's hypothesis immediately before
its unit extraction, not while scanning later paths. Thus a later route does
not increase the accepted-row pool during an earlier path's validation.

Observation pools, current path pools and view descriptors are released before
final rendering. Admitted programs/definitions, attempted envelopes, retained
normalized results and accepted rows keep their observation-wide lifetimes.
For each valid channel, decode reserves a fixed1048576-byte writer slot plus256
bytes for scalar, hash and nesting state before finalizing the result counters.
Serialize the canonical `{"rows":fragment_rows}` wrapper, hash its array, then
reuse the slot for the final result. Count both serialized lengths. The first
attempted byte beyond either slot counts as1048577 bytes for that failed write;
discard it and serialize a closed resource-limit result in the same slot,
preserving completed VM/adapter charges. This second logical render increments
calls. A repeated external result renderer does not recharge or alter state.
Invalid host channel values have no canonical result-render event. All valid
serialized observations, including failures, do. This changes only v2; old
schemas preserve their prior output-bound rejection and resource bytes.

### Content validator reference storage

The reference content adapter reserves the following explicit arenas. This is a
specified packed reference implementation of content-v0 validation, with u64
scalar/reference slots and u32 source offsets; it is not an inferred bound on
Python objects, Rust allocations, or process memory. It invokes the private
validated projection operation (`stream_validation` / `_parse`), without making
public-record or authoring views. Those views in the finite DEFINE miniature are
accounted separately by the definition adapter.

Let B be declared assembled stream bytes and R its declared records. A bounded
frame scan computes H, the sum of the referenced REGION_SET region count for
each LESSON_NODE, counting a shared set again for every referring lesson. The
scan cannot admit content; invalid input still goes through the full validator.
For malformed content shorter than four bytes, metadata is B=actual length,
R=0,H=0, preserving ordinary typed rejection rather than resource exhaustion.
At most4096 lesson rows and4096 regions per referenced set contribute to H.
The initial reservation uses H=0 before assembly; once exact frame bytes exist,
the reservation increases to include H before validator projection construction.

The persistent reservation is32B+128R+8H:

| Pool | Bytes reserved | Canonical representation |
|---|---:|---|
| byte arenas | 4B | B each for assembled source, payload/text scratch, encoded case-response keys, and temporary byte construction |
| decoded scalar arena | 8B | at most one u64 slot per encoded byte; this includes fixed payload fields, atom arrays, text scalar values, region/case fields and references |
| construction arena | 8B | mutable item slots and the corresponding immutable sequence can coexist; one additional u64 slot per source byte |
| nested-item indexes | 8B | sequence spans, field/tuple boundaries and case-map key/value indexes; one u64 slot per source byte |
| offset/type scratch | 4B | one u32 slot per source byte for source positions and staged type checks |
| record descriptors | 48R | six u64 fields: ID, kind, frame start, length-field start, payload start, payload end |
| record headers | 64R | eight u64 fields: ID/kind, payload base, scalar-span start/end, presentation count/matrix, region-map span and case-map span; actual payload fields use the scalar arena |
| record indexes | 16R | one ordered-record reference and one ID-index reference per record |
| lesson region maps | 8H | two u32 fields (region ID, flags) per lesson-specific map entry |

These are reserved capacities, including unused slots, rather than exact live
item counts. Every decoded scalar consumes at least one source byte. A case-map
entry has its own encoded case; only the per-lesson region maps expand aliases
and therefore use H. Item-index spans refer into the scalar arenas; they do not
copy referenced matrices or tuples. Text uses Unicode scalars within its scalar
arena. Rectangles are compared directly, without expanding a grid of cells.

Add the largest of these mutually exclusive phase reservations:

* Dependency traversal:4B+24R. The pending reference stack reserves one u64 per
  two source bytes (references may repeat); three u64 arrays per record cover
  reached/index state and trace-owner work.
* Passive validation:64A+32S+24L+256, where A=min(65535,floor(B/4)),
  S=min(4096,A), L=min(4096,R). Each event reserves eight u64 slots for link,
  node, action, result/count and construction references. Four u64 arrays of S
  selections cover old/new buffers plus sorted/response temporaries. Three
  u64 error fields per lesson and two16-word run-state headers remain live.
  Validate one passive trace at a time; a retained event chain has at most A
  four-byte actions. No selection array exceeds4096.
* Control graph:48E+192L, where E=min(16384,floor(B/2)). Edge triples use24E,
  adjacency construction and immutable adjacency each8E. The final8E is shared
  by reverse adjacency during component discovery and cycle spans afterward;
  reverse adjacency has ended before cycle-span construction. Twenty-four u64
  slots per lesson reserve node/index tables, visited/order/DFS state,
  component/group spans and traversal stacks, then cycle/candidate/cost maps.
  Reuse those phase-local slots only after their prior owners have ended.

Thus the exact reserved workspace is
`32B+128R+8H+max(4B+24R,64A+32S+24L+256,48E+192L)`.
All arithmetic uses the checked-u64 operations above. A retained assembled
stream or decoded body in the caller is outside this adapter reservation and
is counted concurrently by the caller's live-buffer ledger.

### Closed evidence projections

`ObservationDecoderV2.render_resources()` serializes the completed observation
ledger as canonical-manifest-v0 with exactly: schema
`golden-board.m2-observation-resources/v2`, channel, observation_sha256,
result_sha256, source_owners, resource, adapter_rows. source_owners has exactly
the four paths `spec/profile-policy-v2.toml`, `spec/profile-limits-v2.toml`,
`spec/damage-policy-v2.toml`, `spec/resource-accounting-v2.md`, each mapped to its
actual source SHA256. resource has section_attempts, primitive_steps,
peak_scratch_bytes. adapter_rows contains every kernel in the table's order,
each with exactly kernel, calls, reference_input_units, peak_workspace_bytes.
Unused kernels have actual zero counters. All counts are u64; digests are64
lowercase hex characters. The sidecar is generated after the result; the result
contains no sidecar hash, size or counters. It is evidence generation outside
the receiver's runtime scratch, and its own hash is excluded from its preimage.

`build_resource_limits_v2(corpus_sha256, expected_case_ids, rows)` is a bounded
aggregation helper, not a promotion gate. The caller supplies the case IDs
derived from the owning corpus and must bind that derivation in promotion.
Require1..65535 unique ASCII case IDs of1..128 bytes, and consume exactly one
`(case_id,resource-sidecar-bytes)` row in that order. Reject omissions, extras,
reordering, noncanonical/foreign sidecars and differing source-owner sets.
Its case digest preimage is `GBRESV2\0 || u32_be(case_count)` followed by
`u16_be(id_bytes) || ASCII(id) || SHA256(sidecar)` for every ordered row.

The aggregate canonical object has exactly schema
`golden-board.m2-resource-limits/v2`, corpus_sha256, case_count,
case_resources_sha256, source_owners, maximum_resource, adapter_maxima.
maximum_resource takes the separate maximum of each of the three result
resource counters. adapter_maxima keeps the kernel order and takes separate
maxima of calls, reference_input_units and peak_workspace_bytes for each kernel.
These maxima need not occur in one observation. The aggregate is measured only
from provided complete rows; no fabricated zero case or old passing evidence
can substitute for a missing revised observation. Independent reproduction,
full corpus execution, result comparison and promotion bindings remain required
before these generated values can be admitted as production limits.
