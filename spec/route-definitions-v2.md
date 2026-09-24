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

Every integer is unsigned big-endian, except the explicitly illustrated
canonical base-128 wire2 scalar bytes. `u8/u16/u32` state byte width. `L(rows)`
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
   The picture is counted cells, not a presupposed numeric parser. Append count11
   as u8, then rows `(value:u64,encoded_length:u8,encoded_bytes:10 bytes)` for
   `0,1,127,128,255,256,16383,16384,65535,4294967295,18446744073709551615`.
   Encode by recipe-wire-v2's canonical unsigned base-128 groups and pad the
   ten-byte storage with zeroes beyond the exact length. Total306 bytes.

4. Carry `(32,8,24,6)` as u16, then 24 rows of six u16 `(q,u,v,r,c,k)`.
   Visit q=0..3 and local points `(0,0),(0,23),(7,0),(7,23),(0,1),(1,0)`
   in that order. `k=24u+v`; mapped coordinates respectively are `(u,v)`,
   `(v,31-u)`, `(31-u,31-v)`, `(31-v,u)`. Verify with the production sector
   mapping primitive. This is a small geometry example, not a fitting carrier.
   Total 296.

5. Carry these seven layout tables in order, followed by the nine u16 values
   `(109,32,3,2,2,10,42,N,42+N)` with N derived from its actual
   canonical wire2 nodes. They identify recipe 109, header length,
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
   | Route value descriptor | 0/2,2/1,3/1,4/4,8/4 |
   | Compact recipe interface | 0/1,1/0 |

   TABLE framing is explicit even when the new route carries tables only
   inside its complete package. Width0 in the compact interface layout marks
   the canonical variable-width scalar established by fact3. These particular
   recipe109 descriptors are two bytes each. Total236 bytes.

6. Carry 25 rows of six u8 `(opcode,arity,maximum_argument_bytes,maximum_aux_bytes,
   maximum_immediate_bytes,maximum_node_bytes)`, opcode order 1..25. Arity is zero for
   1/2/24/25, one for 5/14/22, three for 3/20/23, two otherwise. Argument
   bytes=3*arity; auxiliary bytes=3 only for2/5/22; immediate bytes=10 only
   for1/5/14/22/25; node bytes=6+the three lengths (one tag and up to five
   width bytes). These are grammar maxima, not fixed record sizes. Then six rows
   `(type:u8,width_unit:u8,minimum:u32,maximum:u32)`:
   `(0,0,1,64),(1,0,1,1),(2,0,1,1048576),(3,1,0,1048576),
   (4,2,0,1048576),(5,0,16,16)`. Unit 0 is bits, 1 bytes, 2 the table's
   element descriptor. The TABLE row is only an outer bound, not scalar
   validation; its actual element descriptor governs. Append six u8 triples
   `(opcode,type,tag)` for `(1,0,1),(1,1,33),(3,2,67),(3,3,99),(2,4,130),
   (24,5,184)`, demonstrating `(type<<5)|opcode`. Total228 bytes.

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

10. Carry ten u16 references `(123,124,120,125,126,127,24,25,26,27)`, then
    `(case_count:u8=8,row_bytes:u8=57)`. Programs and tables are owned by
    recovery-program-v2. Table24's two216-byte sources must exactly equal fact8.
    Table25 contains the structurally illustrated68-byte inventory with three
    entries1/400/401. Its first envelope has one fragment and factor5, so400
    starts at physical6 with factor5 and401 starts at11 with factor2. It is a
    roster example, not a complete semantically admitted production inventory.

    Each row is `(query_unit:u32,case:u8,STATUS16,first:u32,factor:u8,key:20bytes,
    state:u8,accepted:BOOL byte,local_envelope:23bytes)`. Cases0..6 query unit6;
    case7 queries11. Case IDs are zero-based table26 indexes. Execute126 on the
    query and case only. It derives the roster/key through122, constructs all
    raw lanes through125 and calls119; the row's output is never an input.
    Table26's five template IDs per case are:

    ```text
    (0,0,0,0,0), (4,0,0,0,0), (1,0,0,0,0), (3,0,0,0,0),
    (1,4,5,6,7), (4,5,6,7,8), (9,10,11,12,13), (1,1,0,0,0)
    ```

    Table27's template0 is absent. Templates1..13 are `(source,unknown,first,count)`:
    `(0,0,0,0),(0,0,59,5),(0,0,0,1)`, five `(1,0,2i,2)` for i0..4,
    then five `(0,1,59+i,5)` for i0..4. Source selects A/B; unknown0 flips the
    raw bits, unknown1 clears storage and sets the mask. Remaining raw bytes
    stay intact. Presence is distinct from an all-zero present observation.
    Out-of-factor nonabsent templates reject. No validity masks or supplied
    identity/conflict flags cross the constructor's input interface.

    Outcomes respectively are missing, corrupt, verified A, recovered A,
    conflict between A and raw-REP B, REP-only B, unknown-aware REP-only A,
    and unique verified A rejected for physical identity401. The final case
    retains the local A envelope as a diagnostic; acceptance remains false.
    Missing/corrupt/conflict envelopes are zero. All191 candidate bytes govern
    equality even though this finite result displays only the23-byte envelope.
    Public120 accepts arbitrary pairs and returns the complete191-byte block.

    Framed WORKED1002 and HELD_OUT1003 invoke126 for cases4 and6; additional
    WORKED1004 invokes case7. The eight embedded calls all invoke126 again in
    case order. Primitive/recursive resources are charged exactly as owned by
    resource-accounting-v2. Ordinary values and independent numeric relationship
    validation must agree. There is no host-supplied candidate classification.
    Total478 bytes. Full inventory and typed-content admission remain fact11's
    subsequent boundary, not an implication of this miniature.

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
    miniature, supplement length:u32, complete1120-byte supplement; total1703.
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
    Current total is 2485 bytes; changing actual source frames changes measured
    cost and requires review rather than truncation.

## Admission and remaining limits

The current expected value sizes are
`16,64,306,296,236,228,636,544,464,478,314,2485`, total6067 bytes. This is
an audited construction target, not a cap or a passing fit. Compared with the
3779-byte design estimate, 26 bytes explicitly frame package TABLEs, 16 bytes
ground selected-profile rejection, 8 bytes carry ordinal admission outcomes,
and 12 bytes disambiguate the two content-stream ID spaces. The miniature
replacement and its third context add1396 bytes to that3841-byte intermediate.
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
