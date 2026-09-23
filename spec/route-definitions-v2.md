# Numeric carried route definitions v2

This development owner fixes the twelve numeric DEFINE values for the new
profile-8 route. It does not change historical route bytes. Recipe probes,
WORKED/HELD record framing, complete route validation and promotion are owned
separately. Values below are concrete finite relationships and observations,
not an executable layout language or relation-name strings counted as proof.
No value alone proves complete recipient knowledge or content validation.

The Python construction interface is `build_route_definitions_v2(compiled,
content_fixture_raw=None)`, returning twelve fresh immutable records with
`fact_id`, `stage`, `consumes` and `value`. Explicit fixture bytes support
independent source reproduction; omission reads at most1MiB+1 from the tracked
`conformance/content-v0.json` and rejects overflow. Neither path reads a
generated definition or route blob. Independent implementations may include
the same tracked source at build time.

Every integer is unsigned big-endian. `u8/u16/u32` state byte width. `L(rows)`
is `row_count:u16` followed by `(offset:u16,width:u16)` pairs in the listed
order. Other fixed-count rows have no extra count unless stated. Concatenate
each fact's components in their listed order. The fact's enclosing BYTES
descriptor supplies its actual complete length. No encoder truncates a
component to meet a projected byte budget.

Inputs are the current canonical slice-v1 compiler result, its exact required
and all streams, complete record frames and section assignments. Validate both
streams with content-v0 before projection; verify supplied SHA-256 fields against
their bytes. Representations with private admitted streams and no separate hash
fields instead verify typed projection re-encoding against those streams; their
source compiler retains source identity checks. Stream-derived IDs and lengths are generated, not copied from
historical slice-v0 IDs. The first twelve required frames must have kinds
`2,3,4,7,8,9,8,10,4,11,12,13`; failure requires revising the owning example,
not silently substituting a different subject. The source compiler separately
establishes the 64 canonical games; DEFINE generation is not that identity gate.

The fact stages/dependencies are:

| Fact | Stage | Dependencies |
|---:|---:|---|
| 1 | 0 | none |
| 2 | 0 | 1 |
| 3 | 1 | 1 |
| 4 | 1 | 2,3 |
| 5 | 2 | 3,4 |
| 6 | 2 | 5 |
| 7 | 3 | 6 |
| 8 | 3 | 6,7 |
| 9 | 4 | 6,8 |
| 10 | 4 | 7,8,9 |
| 11 | 5 | 10 |
| 12 | 5 | 11 |

## Facts 1–6

1. Carry exactly eight byte/complement pairs:
   `00ff 807f aa55 f00f cc33 01fe 817e 18e7` (16 bytes).

2. Starting with the asymmetric 8x8 row-major MSB bitmap `80402010080403c1`,
   carry its eight D4 images in bootstrap's exact transform order:
   `80402010080403c1`, `81820408102040c0`, `83c0201008040201`,
   `0302040810204181`, `010204081020c083`, `c040201008048281`,
   `c103040810204080`, `8141201008040203`. Generate from the coordinates and
   verify these literal images, including that all images and complements
   are distinct. Total 64 bytes. Integer parsing is not a prerequisite for
   observing these literal bit relationships.

3. For n in `0,1,2,3,4,5,7,8,15,16,24,31`, carry the four-byte 32-cell picture
   whose low n bits are set, then `n:u8`, `255 XOR n:u8`, and `n:u16`.
   The picture is counted cells, not a presupposed numeric parser. Total 96.

4. Carry `(32,8,24,6)` as u16, then 24 rows of six u16 `(q,u,v,r,c,k)`.
   Visit q=0..3 and local points `(0,0),(0,23),(7,0),(7,23),(0,1),(1,0)`
   in that order. `k=24u+v`; mapped coordinates respectively are `(u,v)`,
   `(v,31-u)`, `(31-u,31-v)`, `(31-v,u)`. Verify with the production sector
   mapping primitive. This is a small geometry example, not a fitting carrier.
   Total 296.

5. Carry these six layout tables in order, followed by the nine u16 values
   `(109,32,3,2,12,60,42,484,576)`. They identify recipe 109, header length,
   input/output counts, descriptor width/total, node count, compact node bytes
   and complete compact recipe bytes. Verify them against the generated
   profile-8 recipe; they are not a fixed-32 node-size formula.

   | Layout | Ordered offset/width pairs |
   |---|---|
   | Route envelope | 0/8,8/2,10/1,11/1,12/2,14/2,16/4,20/4,24/4,28/2,30/2 |
   | Route record | 0/1,1/1,2/2,4/4 |
   | Recipe package | 0/8,8/2,10/2,12/2,14/2,16/2,18/2,20/4,24/4,28/4,32/4,36/8,44/4,48/16 |
   | Package TABLE | 0/2,2/1,3/1,4/4,8/4,12/4 |
   | Recipe | 0/2,2/2,4/2,6/2,8/4,12/4,16/8,24/4,28/4 |
   | Value descriptor | 0/2,2/1,3/1,4/4,8/4 |

   TABLE framing is explicit even when the new route carries tables only
   inside its complete package. Total 226 bytes.

6. Carry 25 rows of six u8 `(opcode,arity,total_argument_bytes,aux_bytes,
   immediate_bytes,node_bytes)`, opcode order 1..25. Arity is zero for
   1/2/24/25, one for 5/14/22, three for 3/20/23, two otherwise. Argument
   bytes=2*arity; auxiliary bytes=2 only for 2/5/22; immediate bytes=8 only
   for 1/5/14/22/25; node bytes=6+the three lengths. Then six rows
   `(type:u8,width_unit:u8,minimum:u32,maximum:u32)`:
   `(0,0,1,64),(1,0,1,1),(2,0,1,1048576),(3,1,0,1048576),
   (4,2,0,1048576),(5,0,16,16)`. Unit 0 is bits, 1 bytes, 2 the table's
   element descriptor. The TABLE row is only an outer bound, not scalar
   validation; its actual element descriptor governs. Total 210 bytes.

## Facts 7–10

7. Carry common and envelope prefix layouts:
   `L(0/2,2/2,4/4,8/2,10/2,12/2,14/2,16/2,18/2,20/2,22/4,26/4,30/157,187/4)`
   and `L(0/2,2/4,6/2,8/2,10/1,11/1,12/2,14/4)`.
   Append local domain `d3916ac47208be5f`, section domain `4be21977a03c65d8`,
   then two `(nine input bytes,four CRC32C bytes)` examples for ASCII bytes
   `313233343536373839` and bytes `000102030405060708`; results respectively
   `e3069283` and `7144c5a8`.

   Append full 191-byte common blocks A then B. Their profile is 8, section
   400, copy 0, type 4/version 0, fragment index 0/count 1. The fragment
   contains a freshly checksummed 23-byte envelope: section 400/type 4/version
   0/closure 129/check 1/no dependencies/one payload byte, respectively 0 and
   1. The remaining common payload is zero and its local CRC is freshly
   calculated. These are valid local examples, not actual inventory members.

   Append ten mutation rows `(offset,width,replacement,recheck,local_ok,
   envelope_agreement_ok)`, all u16, applied separately to A:

   ```text
   (2,2,1,1,0,0)    (14,2,1,1,0,0)  (26,2,1,1,0,0)
   (18,2,0,1,0,0)   (16,2,1,1,0,0)  (4,2,1,1,1,0)
   (22,2,1,1,0,0)   (48,1,1,0,0,0)
   (187,1,A[187] XOR 1,0,0,0)       (53,1,1,1,0,0)
   ```

   Replacement is big-endian in the stated width; recheck=1 recomputes only
   the local CRC after replacement. Local acceptance always uses expected
   profile 8. Envelope agreement requires local success, a checked envelope,
   and exact section ID/type/version/length agreement with the common header.
   A changed section-ID high half can pass locally without agreement. These
   finite examples are not a new executable patch language. Total 636 bytes.

8. Carry eight u16 `(24,9,8,216,192,191,1,0)`, then 24 u16 pairs `(9i,8i)`
   for i=0..23, then full 216-byte EH encodings of `A||00` and `B||00`.
   Generate with the EH primitive; verify decoded 192 bytes, mandatory final
   zero, and common acceptance under profile 8. Bit zero has no extra anchor.
   Total 544. The actual final carrier's first inventory unit needs its own
   complete check; these illustrative blocks cannot substitute for it.

9. For geometries `(S,W)=(2040,128),(1952,128)`, first carry both ten-u32
   parameter rows `(S,W,I,P,Q,B,B_inverse,a,a_inverse,offset)`, then eight
   six-u32 mapping rows per geometry `(unit,bit,slot,logical,physical,kind)`.
   Derive `I=S-2W`, `P=I*I`, `Q=floor(P/1728)`, B from actual table17[I/8],
   inverses modulo Q/P, `a=2I-1`, `offset=(8*40503+257W)%P`.
   Visit `(unit,bit)=(1,0),(1,1727),(Q,0),(Q,1727),(floor(Q/B)+2,0)`,
   then logical cells `1728Q-1,1728Q,P-1`. Protected rows have kind 0;
   pad rows kind 1 with unit/bit/slot zero. Derive the last protected unit
   through the inverse, not by assuming Q. Verify forward/inverse production
   mapping and the independent equations. Total 464. Invalid geometry, table
   and index rejection remains the complete adapter's responsibility; modular
   primitive 109 is not that adapter.

10. Carry the complete physical-observation-to-decision example below. The
    body is443 bytes, including executable construction bindings; production packet/inventory widths do not change.
    The illustrative roster is incomplete and never substitutes for an accepted
    inventory. Every byte position below is relative to this DEFINE value.

    At0, carry `(rows:u16=4,columns:u16=6)` and four rows of six u16
    `(section,fragment,F,R,first,last)`:
    `(1,0,2,5,1,5),(1,1,2,5,6,10),(400,0,1,5,11,15),
    (401,0,1,2,16,17)`. Ranges are inclusive physical unit IDs. At52,
    carry the eight identity-field offsets `0,4,8,10,12,16,18,22` as u8;
    their widths remain those in fact7: `2,4,2,2,2,2,2,4`.
    At60, carry expected-key count2 as u8, followed by the two complete keys
    `(8,400,0,4,0,0,1,23)` and `(8,401,0,4,0,0,1,23)`, each20 bytes in
    those field widths. Bind a key to its roster row by section, fragment and
    fragment count. Thus identical checked A bytes belong to400 at units11..15
    and fail expected identity at units16..17; a decoded header cannot move a
    physical observation to another group. Compare every one of the eight
    fields for every distinct checked candidate. No candidates means false.

    At101, carry `(constructor_recipe:u16=111,word_index:u8=0)`. At104,
    carry `(template_count:u8=13,template_width:u8=4)`, then rows
    `(source:u8,unknown:u8,first_bit:u8,count:u8)`. Source0 is encoded A and
    source1 encoded B from fact8. Unknown0 toggles the indicated contiguous bits;
    unknown1 makes them unknown and clears only their storage bits. Packet bits
    are zero-based, MSB first. Count0 leaves the source unchanged and requires
    first0. Templates are numbered1..13 in this order:

    ```text
    (0,0,0,0), (0,0,59,5), (0,0,0,1),
    (1,0,0,2), (1,0,2,2), (1,0,4,2), (1,0,6,2), (1,0,8,2),
    (0,1,59,5), (0,1,60,5), (0,1,61,5), (0,1,62,5), (0,1,63,5)
    ```

    Execute recipe111 for every template on fact8's two first words and the four
    fields, compare its observed word/mask with independent range construction,
    and retain the source's remaining207 bytes unchanged. Template2 is the
    ordinary HELD_OUT flip counterpart of WORKED template9's erasure. Their
    outputs distinguish the observed erroneous packed `BHB` interpretation.
    At158 carry `decision_recipe:u16=110`. At160 carry
    `(case_count:u8=8,case_width:u8=24)`. Each row contains
    `first_physical_unit:u8`, five `template_id:u8`, five `lane_state:u8`,
    `REP_state:u8`, the nine input bytes of recipe110, and its three output
    bytes without STATUS16. Template0 means an absent observation, not a zero
    codeword. The physical first ID selects the roster group and its factor;
    slots at or beyond that factor must be absent. The eight case constructions
    are `(first,templates)`:

    ```text
    (11,0,0,0,0,0), (11,4,0,0,0,0), (11,1,0,0,0,0),
    (11,3,0,0,0,0), (11,1,4,5,6,7), (11,4,5,6,7,8),
    (11,9,10,11,12,13), (16,1,1,0,0,0)
    ```

    Derive each lane state and candidate with the existing bounded EH/common
    checks. States are0 absent,1 corrupt,2 verified,3 recovered,4 conflict;
    trailing out-of-factor lane states are0. Derive raw repetition from all
    original observations, including failed lanes, by counting known zeroes and
    ones at each bit. Unknown storage bits never contribute known zeroes.
    REP state is0 when no lane is present and no REP observation is constructed,
    1 when the constructed REP does not yield a checked candidate, and3 on
    success. Complete checked
    191-byte block equality determines masks: A=1, B=2. Unknown example values
    reject this finite construction. Keep all lane and REP candidates, deduplicate
    equal blocks, and reject conflicting distinct candidates.

    Derive recipe110's six masks, presence flag, **any locally verified lane**
    flag, and the expected-key identity flag. A corrected standalone A is a
    candidate but does not set the verified flag: case3 is verified and case4
    recovered. Case5 retains clean A and raw-REP B and rejects their conflict;
    case6 recovers B only by REP. Case7 recovers A only by retaining failed
    lanes and unknown symbols; interpreting storage zeroes as observations must
    fail. Case8 contains checked A at physical ownership401 and rejects identity.
    Execute recipe110 and compare all outputs with the independently derived
    group decision. The case traces start at174+24*i, i=0..7. The ordinary framed pair
    constructs the two contrasting observations above; embedded110 retains all
    eight decisions, including conflict and REP-only recovery.

    At354, carry `(coordinate_rows:u8=3,row_width:u8=4)` and three rows
    `(packet_bit:u16,word_index:u8,EH_position:u8)`:
    `(0,0,1),(63,0,64),(72,1,1)`. These explicitly connect zero-based packet and
    word indices to the one-based EH position, including a word boundary.
    At368, carry `(case_number:u8=7,source:u8=0,word_index:u8=0,recipe:u16=30)`,
    followed by the13-byte recipe30 input derived from that case's raw REP:
    `00014000000000062001400000`. The input's first nine bytes retain canonical
    zero storage for its remaining unknown; the rest are count1 and positions
    `64,0,0`. Execute the observed recipe and compare its successful eight-byte
    result with A's first eight decoded bytes from fact7. Derive this input
    from the observations; do not fill an unknown from the intact specimen.
    Changing only the erased storage placeholder does not change the result.
    The additional ordinary WORKED record1004 repeats this derived input and
    its result, connecting case7 to the framed executable-example path.

    At386, carry `(recipe:u16=113,column_count:u8=4,row_width:u8=8)`, then rows
    `(R:u8,five_symbols:u8[5],known:u8,value:u8)`:
    `(2,0,1,2,2,2,0,0)`, `(5,0,1,1,1,1,1,1)`,
    `(5,1,2,2,2,2,1,1)`, `(5,2,2,2,2,2,0,0)`. Symbols0/1 are observed bits and2 is unknown;
    out-of-factor slots must be2 and do not enter counts. These demonstrate a
    tie, a known disagreement resolved by repetition, one known1 surviving
    four unknowns, and the all-unknown column at case7 bit63. Derive `(R,known_zero_count,known_one_count)` as
    `(2,1,1),(5,1,4),(5,0,1),(5,0,0)`, execute recipe113 and compare its known/value
    outputs. Use the same count-derived operation on the actual case columns;
    do not replace it with “all known bits must agree” or with voting on candidate
    identities. Failed lane decoding does not remove its original symbols.

    At422, carry row count5 as u8, then five rows
    `(L:u16,F:u8,last:u8)` for L=`22,157,158,314,315`, with
    `F=ceil(L/157)` and `last=L-157(F-1)`. Independently construct all fragment
    lengths and verify reassembly sums to the already carried L; its duplicate
    column is removed. These are fragment-length examples, not claims of valid
    section/inventory acceptance. Fact11 remains required for those outcomes.
    The last byte belongs to this non-VM metadata; contradictory-definition
    rejection therefore retains the complete route's charged VM schedule.

## Facts 11–12

11. Carry inventory prefix `L(0/2,2/2,4/2,6/2)` and entry
    `L(0/4,4/2,6/2,8/1,9/1,10/1,11/1,12/2,14/4,18/2)`.
    Append six u8 triples `(R,has_ordinal,2R+has_ordinal)`, R=1,2,5 and
    absent then present. This is flag construction, not permission for every
    combination under the section-role rules. Append nine u16
    `(1,2,0,5,1,2,3,4,5)` for inventory ID/version/copy/factor and physical IDs.

    Append twelve nine-u8 availability rows. The six inputs are inventory
    admitted I, required section set complete R, all section set complete A,
    required typed stream valid T, all typed stream valid U, every inventoried
    section available E. Inputs, in order, are
    `011111,100000,110000,111011,110100,111101,111100,111110,111111,
    000000,010101,101111`. Outputs are `required=I&R&T`,
    `all=required&A&U`, `exact=all&E`. These conditional Boolean relationships
    apply only after higher ambiguity/unsupported/resource dispositions are
    resolved; they do not replace those dispositions or prove a full carrier
    pass. Required and all section sets include their respective tier frames.

    Append two four-u16 profile-check rows `(wire_profile,selected_profile,
    recompute_local_crc,accepted)=(8,8,1,1),(7,8,1,0)`. Apply the wire-profile
    replacement to A and recompute CRC to demonstrate selected-profile
    rejection independently of stale checks.

    Append `3:u16` then u8 correspondence triples `(4,2,4),(10,6,2),(12,8,2)`
    common→envelope; append `7:u16` then `(2,0,4),(6,4,2),(8,6,2),(10,8,1),
    (11,9,1),(12,12,2),(14,14,4)` envelope→inventory. Common envelope length
    is not inventory payload length; common and inventory flags differ.

    Append IDs `(2,16,17,18)` as u16, then four five-byte dependency cases:
    `(adjacency:u16,selected_mask:u8,closure_mask:u8,valid:u8)` equal
    `(7000hex,8,15,1),(4200hex,8,14,1),(0000hex,4,4,1),(4800hex,8,0,0)`.
    Adjacency bits are the 4x4 row-major matrix, MSB first, edge source→target;
    mask bit 3 denotes the first ID. Verify with the dependency graph primitive.
    These subgraphs are not complete admitted inventories.

    Append four u16 rows `(section,ordinal,has_ordinal,entry_admitted)`:
    `(100,0,1,1),(163,63,1,1),(211,65535,0,1),(101,0,1,0)`. Use body
    version 0, closure129, CRC1, copy1, factor1, no dependencies, payload
    length1; section211 is type4, others type3. Validate the actual v2 entry
    header. The last row conflicts with the required ordinal and duplicates
    ordinal zero if combined with the first. Total 314 bytes.

12. First carry three u16 triples `(context,record_count,root_id)` for required
    context 0 and all context 1, derived from their complete streams, and
    miniature context 2 with count29/root29. The reference examples below are
    in required context; the subject bridges at the end are in all context.
    The complete miniature and supplement belong only to context2. This distinction is essential:
    required ROOT 588 is currently reused as all DATA binding 588.

    Carry layouts for stream `L(0/2,2/2)`, record `L(0/2,2/2,4/4)`, binding
    `L(0/1,1/1,2/2,4/2,6/2,8/2)`, ROOT `L(0/2,2/2)`, OPAQUE prefix
    `L(0/2)`, and tier `L(0/2,2/1,3/1,4/2,6/2,8/4,12/2,14/4,18/4)`.
    Then fourteen u16 triples `(kind,length,fixed_not_minimum)`:
    `(1,1,0),(2,5,0),(3,4,0),(4,7,0),(5,10,0),(6,3,0),(7,18,0),
    (8,10,1),(9,3,0),(10,6,1),(11,6,1),(12,20,0),(13,22,0),(14,4,1)`.
    These are content-v0's stage-3 shapes, not complete dynamic validation.

    Append the complete `ContentTeachingV2.value` owned by
    `spec/content-teaching-v2.md`: miniature length:u32, complete575-byte
    miniature, supplement length:u32, complete1056-byte supplement; total1639.
    Generate from the canonical content-v0 conformance fixture's semantic
    source and validate every carried consequence. Never substitute a generated
    opaque blob as production input. This is generic content/control teaching,
    not current learner/chess content or evidence of fresh recipient success.
    Append ten u16 rows `(owner_id,payload_offset,target_or_count,target_kind)`:
    DATA5 argument/count at offsets6/8; PREDICATE7 argument/schema at6/8;
    OPAQUE6 binding at0; MATRIX3 schema at0; FEEDBACK10 display at2;
    LESSON12 default-next at its final two payload bytes; required ROOT entry
    and budget at0/2. Derive values from actual payloads. Target kind is 0 for
    scalar/count rows; otherwise verify the real referenced kind. The default
    next must demonstrate a forward LESSON_NODE reference, while ordinary
    nonzero display/schema/data references are earlier. Append four u16 budget
    triples `(3,5,8),(3,5,7),(8,1,9),(8,1,8)`. Arithmetic comparisons alone
    do not establish path reachability, acyclicity or worst-case budgets.

    Append the complete DATA binding frames in all sections100 and
    200, then their two-byte OPAQUE binding-reference prefixes, then two rows
    `(section:u32,binding_id:u16,opaque_id:u16,namespace:u16,code:u16)`.
    Require namespaces2/3 respectively and code1; verify their full OPAQUE
    payloads equal source game0/fixture0. Current pairs are588/589 and716/717;
    regenerate from assignments rather than freezing historical record IDs.
    Finally append the complete 408-byte Position/Move16 numeric suffix owned
    by `spec/position-teaching-v2.md`. Its two Position examples are extracted
    from actual current source records and checked with public chess replay;
    fixture variant1 is distinct from Position and generic STATUS16. Move wire
    admission is distinct from legal move admission. The 65 learner pages and
    final consequence questions are unchanged.
    Current total is 2421 bytes; changing actual source frames changes measured
    cost and requires review rather than truncation.

## Admission and remaining limits

The current expected value sizes are
`16,64,96,296,226,210,636,544,464,443,314,2421`, total 5730 bytes. This is
an audited construction target, not a cap or a passing fit. Compared with the
3779-byte design estimate, 26 bytes explicitly frame package TABLEs, 16 bytes
ground selected-profile rejection, 8 bytes carry ordinal admission outcomes,
and 12 bytes disambiguate the two content-stream ID spaces. The miniature
replacement and its third context add1332 bytes to that3841-byte intermediate.
The explicit Position/Move16 suffix adds another408 bytes.

Implementations must verify positive/negative observations with production
primitives and compare generic EH/repetition recipe consequences separately.
They must use expected profile8 for local checks. Recomputing CRC cannot
establish inventory, physical or typed agreement. Preserve all candidate
lanes and raw repetition before conflict classification. Source-derived values
remain local bounded computations, never generated answer strings interpreted
as instructions.

Fact12's complete miniature and finite consequences now ground examples of
dynamic atom lengths, references, presentation linkage, role/mode rules, trace
replay, reachability, acyclicity and event budgets. Finite observations still
do not constitute a universal independent validator or fresh recipient result.
Generic opaque acceptance also establishes no chess meaning.
No successful host validator run may be relabeled as carried knowledge.


## Observation admission and recovered-context proof

Local contradictions in numeric DEFINE relationships invalidate the observed
route2. This means checking their actual finite arithmetic, byte layouts,
common/EH/group relationships, mapping rows, typed miniature and local
Position/Move16 examples; matching a source hash or descriptor width alone
is not this check. The observation parser retains immutable context commitments.

Downstream namespace, game/fixture, Position extraction and section-membership
claims are checked separately against already recovered streams and decoded
body frames as carried-knowledge evidence. This check never changes transport's
content-v0 availability, chooses recovered bytes by chess plausibility, or
substitutes clean/source content. Missing streams leave the corresponding
knowledge claims unresolved. Local host validation still does not establish
human discovery; the owned use/ablation and fresh participant evidence retain
their distinct roles.
