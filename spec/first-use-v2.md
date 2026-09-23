# Finite carried first-use coverage v2

This additive development owner covers the actual profile8 route/recipe
surface in m2-spec §6.5. It does not replace knowledge-use-v2, its recovered
content checks or 96 ablations, nor establish provenance, human acquisition,
full Gate5, damage admission or promotion. No historical bytes change.

`build_first_use_v2(prefixes, *, side, width)` consumes exactly four observed
immutable prefixes under the same prefix/geometry bounds as knowledge-use-v2.
It returns canonical-manifest-v0 bytes, at most1MiB. The matching validator
requires canonical bytes equal to a fresh complete derivation. Missing,
additional, reordered or changed coverage fails. No file, builder, fixture,
retained proof, interpreter extension or expected package bytes is an input.
Each prefix must pass observation-only route2 admission, including all numeric
definitions and actual examples. All four packages/DEFINE values must agree.

## Definition versus execution

Physical record order is retained and all spans name actual observed bytes.
The logical prerequisite order is not a claim that an untrained reader runs
the host parser. Literal pictures, ordered values and input/output relations
may be inspected and revisited before interpreting their recipe references.
Facts1–5 ground bit relations, counting, order, traversal and framing. Fact6
adds numeric opcode lengths/types. Those together frame symbolic dataflow and
literal inputs/outputs; they do not require executing that dataflow first.

The teaching cluster has these non-circular literal anchors:

* CONST and TABLE leaves are their carried immediate and table payload bytes.
* EMIT has exact input-copy anchors in211: both inputs1/2 into output33 at
  bit offsets0/8, and input4 into output34 at byte offsets0/3. Widths and
  positions come from carried descriptors and fixed-position node fields.
* Every non-EMIT node of211 has either a literal leaf, or its entire value
  directly present in an output slot (offset0, same type/width). The only
  exception is FAIL5, which is a literal status leaf compared with CONST5;
  separate212 exposes FAIL4 as the complete two-byte failed output after
  earlier data emission. SUCCESS is directly present in status output1.
* Every ordinary relation's arguments are input bytes, CONST/TABLE leaves,
  directly visible output values or that FAIL literal. No missing intermediate
  value may be manufactured by evaluating an unknown operation.
* ITER is grounded last relative to every opcode used by its lower-ID helper
  closure210/213. The helper graphs use already-grounded relations;214 carries
  zero→three and overflow observations. This is composition of existing
  primitives, not a second execution grammar.

This is finite relational evidence, not uniqueness of inference from examples.
The existing VM subsequently checks the complete carried computations. That
check cannot fill an absent literal anchor or a prerequisite cycle.

Independently compare both211 primary examples' four input-copy segments
against their actual output bytes (without VM evaluation), and require the
visible status to be0. The212 literal grounding is its exact four-node graph
CONST UINT8(7), EMIT value1 to output2/offset0, FAIL4, EMIT value3 to
output1/offset0; its carried observation has empty input and only STATUS4.
This is an explicit suppression relationship, not a host-generated missing
intermediate. A changed graph or copy byte fails the literal anchor check.

For each opcode derive dependencies from all its211 witnesses: every
nonliteral result needs EMIT5; an argument anchored by CONST1, TABLE2 or
FAIL25 needs that opcode. Remove a self dependency only for a literal leaf.
EMIT5 has no opcode prerequisite (its input-copy anchors use only facts1–6).
FAIL25 additionally requires CONST1 and EMIT5 and the212 failure observation.
ITER22 additionally consumes every opcode of its transitive lower-ID helper
closure, excluding none; a recursive/opcode cycle rejects. Generate the
smallest-ready-opcode topological order; all25 must occur. Complete executable
package use follows this order; facts7–12 then use already-grounded recipes.
The order is generated from observed uses, not a chosen list that hides cycles.

## Closed enumeration

Offsets in package rows are package-relative. Route rows provide each sector's
actual package offset, so byte offset maps to eight MSB-first sector-scan cells.
Definition-relative offsets similarly use the per-sector definition spans.

Parse the six observed fact5 L tables in order. Each layout row is
`[layout_id, definition_offset, [[field_offset,field_width],...]]`, IDs0..5
for route envelope, frame, package, table, recipe, descriptor. Definition
offset names its count field. A field use names the exact four-byte pair at
`definition_offset+2+4*field_index`. Every field is covered, including reserved
zeros and counts. Each layout partitions its fixed header without gaps.
For every route layout0 applies at prefix offset32 and layout1 at each
frame_span's start. Every DEFINE's12-byte descriptor uses layout5 at
value_start-12; its preceding u16 fact ID equals that descriptor's ID. These
are derived field uses, not omitted defaults. Example metadata is explicitly
partitioned into fact:u16, recipe:u16, input_bytes:u32, output_bytes:u32 and
the two ranges in example_spans; lengths match the observed descriptor widths.
Recipient admission checks these exact framing and interface relationships.

The package is partitioned exactly into its64-byte header, table headers and
payloads, recipe32-byte headers,12-byte descriptors and opcode-sized nodes.
No trailing/gap/overlapping bytes, unknown field/opcode/type or unresolved
reference is covered by a default. Existing full semantic admission supplies
typed arithmetic/resource checks; this enumeration independently binds spans.

`field_rows` are `[layout_id, owner_id, item_id, field_index, offset, width,
definition_pair_offset]` for package header(owner/item0), tables(owner=tableID,
item0), recipe headers(owner=recipeID,item0), and descriptors(owner=recipeID,
item=input index or65536+output index). All rows follow wire order.
Node fields are fully specified by `node_rows` and actual fact6 row: fixed
opcode/type/width at0/1/2 of widths1/1/4, then exactly the carried arity's u16
arguments, optional u16 auxiliary and optional u64 immediate. Implicit IDs
are input_count+node_index and are not fictional wire bytes.

`table_rows`: `[id,start,length,payload_offset,payload_bytes,type,width,count]`.
`recipe_rows`: `[id,start,length,input_count,output_count,node_count]`.
`descriptor_rows`: `[recipe,io,index,id,start,type,width,count]`, io0=input,
1=output, index one-based. `node_rows`:
`[recipe,node_index,value_id,start,length,opcode,type,width,arguments,aux,imm]`.
Each argument is `[value_id,field_offset,producer_offset,producer_length]`;
the producer is its input descriptor or a preceding node of this recipe.
Aux is empty or `[value,field_offset,target_offset,target_length]`, targeting
the actual table2, output descriptor5 or lower-ID recipe22. Imm is empty or
`[field_offset,value]`; its eight bytes are the explicit constant/offset/count,
whose type and role come from that node and fact6. No host constant substitutes.

`literal_rows` enumerate every non-EMIT211 node:
`[node_index,opcode,argument_anchors,result_anchor]`.
An anchor is `[kind,id]`:0=input index,1=CONST node index,2=table ID,
3=output index,4=FAIL node index. Inputs/output spans resolve through observed
211 descriptors and each example's actual input/output boundaries. Choose the
lowest-index complete matching output for visible values. Literal nodes use
their immediate/table anchors even if also emitted. A nonliteral lacking a
complete output anchor rejects. `copy_rows` enumerate211 EMITs whose source is
an input: `[node_index,input_index,output_index,offset]`; require exactly
`[70,1,33,0],[71,2,33,8],[72,4,34,0],[73,4,34,3]` under the observed211 numbering.
FAIL literal only for opcode25; its immediate must be exposed by the separate
212 status relationship already checked at admission. `opcode_rows` are
`[opcode,definition_offset,dependencies,teaching_node_indices]`, with
definition_offset=6*(opcode-1), length6 in fact6. EMIT's teaching nodes are all
211 EMITs. Each of25 rows must have a witness. Type rows are
`[type,definition_offset,10]`, offset150+10*type, all six used by the package.

`call_rows` are `[caller,node_index,callee]`. Each example root's transitive
recipe closure is derived from these actual calls. Add operational roots
30/109/113/202, and table17's explicit fact9 mapping lookup. Every package
recipe and table must be reached; unused tables/recipes fail. `use_rows` are
`[fact,recipe,closure_recipe_ids,closure_table_ids]`, ordered by ascending
fact then first appearance of distinct recipe in that fact's actual examples.
After fact10's framed roots, add its observed embedded decision root at
DEFINE offset158 (recipe110); observed admission executes all eight traces.
This is an explicit carried use, not a claim of an ordinary framed example.
Fact8 also consumes108 to encode the actual carried whole-unit examples:
48 rows, A then B, lane0..23. `adapter_rows` are
`[8,108,block_index,lane,input_segments,output_segment]`; each segment is
`[fact,value_relative_offset,bytes]`. Fact7 A/B begin134/325. Lanes0..22
read eight bytes there; lane23 reads the final seven common bytes plus the
one zero byte at fact8 offset15. Output is nine bytes at fact8 offset
112+216*block_index+9*lane. Execute observed108 on those exact input bytes;
require status0 and its output equal the observed output segment. This proves
encoding direction for the whole-unit teaching relation; receiver use30 is
separate. This adds fact8/108 to use_rows after that fact's example roots.

Operational rows use fact0, ordered30/109/113/202, after example rows. Fact0
denotes post-teaching receiver use, never an extra defining fact.

`mapping_use` is `[9,17,index,package_element_offset,value,0,464]`, where
index=(side-2*width)/8, offset points at that exact observed table17 byte,
and the last two values bind the complete fact9 relationship. Require its
UINT8/256-element descriptor and in-range index; route admission separately
derives and validates the smallest multiplier from that observed value.
This explicit non-VM table use accompanies the ordinary TABLE node uses.

`convention_rows` are `[fact,dependencies,value_bytes,example_record_ids]` with
the exact twelve-fact dependency graph of knowledge-use-v2. Each whole numeric
value is a bounded relationship cluster, not an English name supplied as
evidence. The corresponding checked relationships are precisely route-
definitions-v2: primitive/order/field conventions1–6, common/check domains7,
whole-unit grouping8, mapping/table17 traversal9, all-lane conflict/fragment
order10, inventory/tier availability11 and typed/content/namespace/control/
Position composition12. Existing knowledge evidence independently replays the
recovered context; this projection does not re-enumerate actual content fields.

## Canonical output and bounds

Closed top-level keys: `schema`=`golden-board.m2-first-use/v2`, `scope`=
`finite-carried-convention-coverage-development`, `inputs`, `route_rows`,
`layout_rows`, `field_rows`, `table_rows`, `recipe_rows`, `descriptor_rows`,
`node_rows`, `literal_rows`, `copy_rows`, `opcode_rows`, `type_rows`,
`opcode_order`, `call_rows`, `use_rows`, `adapter_rows`, `mapping_use`, `convention_rows`, `summary`.
Inputs has `side`, `shell_width`, `package`={bytes,sha256}.
Route rows have `sector_id`, `bytes`, `sha256`, `package_offset`,
`definition_spans` (fact,start,length triples), `frame_spans`
(stage,kind,recordID,start,length), and `example_spans`
(fact,recipe,recordID,input_start,input_bytes,output_start,output_bytes).
Record IDs in convention rows use sector0's actual IDs; other sectors resolve
by their recorded spans, not an assumed absolute location.
Summary keys: `result`=`pass`, `route_count`, `package_bytes`, `field_count`,
`node_count`, `constant_count` (nodes with immediate), `table_count`,
`recipe_count`, `opcode_count`, `literal_count`, `copy_count`.

Require at most4096 nodes,16384 edges,256 recipes,256 tables,32768 package
bytes (the stricter actual route prefix cap already applies),65536 field rows,
and1MiB output. All integer arrays use canonical unsigned integers.
The producer verifies complete source-byte partition and exact finite grammar
before publishing; failure returns no successful partial projection.
