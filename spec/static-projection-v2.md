# Profile-8 static projection v2

This owns source-built static evidence for the participant revision. It supplies
Gate1–5 inputs; it does not report cross-language agreement before comparison,
full resource admission, damage, independence, promotion, or recipient success.
Historical schemas, hashes and admissions remain exact. No ceiling increases.
The complete physical artifact remains at most2048² bits/512KiB; its four-byte
file count is outside that cap. A failed density check remains measured losing
evidence, not a construction exception or permission to change thresholds.

## Inputs and deterministic output

Python API: `build_static_projection_v2(compiled, prototype_source, blueprint,
inherited_profile_policy_raw, image, routes, *, policy_v2) -> StaticProjectionV2`.
The first two inputs are admitted SliceCompilation objects; image is the complete
DevelopmentCarrier and routes is its complete RouteImageSet. Policy_v2 is the
strict v2 decoder policy projection. Independent Rust uses the corresponding
source-built typed values and exact owner source bytes. No saved projection,
old passing result, or other implementation's emitted bytes is an input.

Revalidate the actual content streams/projections, historical prototype source,
neutral capacity policy, complete section/tier assignments and body codecs.
Re-derive the CapacityPlan from those inputs and the four actual route prefix
lengths and require exact agreement with the supplied plan, including every
search row and probe byte. Reconstruct source-owned complete route images and
require equality to supplied images/prefixes. These are authoring checks, not
observation-only acquisition or knowledge-use proof. Reparse each carried
compact package and require its profile8; all four package bytes must agree.
Every emitted source digest is calculated from its supplied bytes, not a
previous receipt. Derive package/recipe counters from its checked logical parse.

Return seven immutable canonical JSON byte documents, using the existing
canonical_manifest grammar (u64 only, depth32, at most1MiB per document), with
these filenames and attributes:

| Filename | Attribute | Schema |
|---|---|---|
| semantic-envelope.json | semantic_envelope | golden-board.m2-semantic-envelope/v2 |
| capacity-ledger.json | capacity_ledger | golden-board.m2-capacity-ledger/v2 |
| ownership-ledger.json | ownership_ledger | golden-board.m2-ownership-ledger/v2 |
| density-ledger.json | density_ledger | golden-board.m2-density-ledger/v0 |
| geometry-search.json | geometry_search | golden-board.m2-geometry-search/v2 |
| static-limits.json | static_limits | golden-board.m2-static-limits/v2 |
| candidate-manifest.json | candidate_manifest | golden-board.m2-candidate-manifest/v2 |

All top-level key sets and row fields below are closed. Tables carry two keys
`<name>_fields` (listed column strings) and `<name>_rows` (arrays in that order).
Absent game/fixture ordinals are65535. Every sum/product/counter is checkedu64;
all parsed scalar types are exact integers, never booleans. Arrays are bounded
by the existing source capacities:4096 sections,4095 dependencies per section,2389 units,
65535 content records, and the neutral capacity slot bounds. Do not truncate.
All integer SHA-256 preimages use big-endian. Strings/hashes are lowercase
ASCII. Current profile_id is `eh72-hier-r5-r2-r1-lzss-crc32c-v1`, version8.

## Shared mappings and immutable provenance

`mapping` has exactly: `id="affine-slot-then-interior-v2"`, `interior_side`,
`population`, `unit_population`, `unit_multiplier`, `unit_inverse_multiplier`,
`cell_multiplier`, `offset`, `cell_inverse_multiplier`. Derive all values from
bootstrap-v2's admitted S/W/table17 rule, not copied historical placement.

`source_identities` has exactly `inherited_profile_policy_sha256`,
`profile_policy_sha256`, `profile_limits_source_sha256`, `damage_policy_sha256`,
`required_content_sha256`, `all_content_sha256`. The first is calculated from
the strict historical neutral policy bytes, the next three are the exact strict
v2 policy source identities (not promoted generated limits), and the last two
are calculated from the actual streams. This is static input provenance; the
later promotion owner additionally binds the complete tracked source DAG.

## Semantic envelope

Keys: schema, profile_id, source_identities, prototype_fields/prototype_rows,
real_section_fields/real_section_rows, tier_frame_fields/tier_frame_rows,
bucket_fields/bucket_rows, capacity_section_fields/capacity_section_rows,
slot_fields/slot_rows, totals.

* prototype: `(kind,prototype_id,source_record_id,frame_bytes)`; kind order1..14.
* real_section: `(section_id,closure_class,physical_replica_count,decoded_payload_bytes,stored_payload_bytes,section_version,record_ids,game_ordinal,fixture_ordinal)`; ascendingsection ID. Decoded bytes sum complete assigned non-root frames; stored/version are actual body-codec selection. Required factor5; all-only factor1.
* tier_frame: `(section_id,physical_replica_count,payload_bytes,dependency_ids,assembled_stream_bytes,assembled_record_count,root_record_bytes)`; IDs2,3, factor5. root_record_bytes is a byte count, not opaque hex.
* bucket: `(bucket_id,tier,protection_class,payload_bytes,slot_count,section_count)`; unchanged neutral capacity order.
* capacity_section: `(section_id,bucket_id,section_ordinal,tier,protection_class,first_slot_ordinal,slot_count,payload_bytes)`; IDs start211, omit zero payloads, neutral bucket/section order.
* slot: `(bucket_id,slot_ordinal,role_ordinal,role_id,kind,prototype_id,frame_bytes)`; neutral envelope order.

The bucket and capacity-section `protection_class` strings retain the neutral
capacity source names used by carrier-v2: `replicated-core0-2` (factor2) and
`nonreplicated-core3-4` (factor1). Do not relabel them with the historical
profile7 presentation names `replicated-m2` / `nonreplicated-m2`.

Totals exactly: prototype_count, real_section_count, tier_frame_count,
bucket_count, capacity_section_count, slot_count, authoring_payload_bytes,
real_decoded_body_payload_bytes, real_stored_body_payload_bytes,
tier_payload_bytes, content_capacity_before_reserve_bytes,
reserve_payload_bytes, protected_logical_capacity_bytes.
C = decoded-body sum+tier-payload sum+16384+authoring bytes; reserve=max(382,
ceil(C/19)); protected logical capacity=C+reserve. Compression never reduces C.

## Capacity and protected-unit ledger

Keys: schema, profile_id, carrier_sha256, semantic_envelope_sha256,
section_fields/section_rows, unit_fields/unit_rows, ledger.

Sections ascend numeric ID. Columns:
`section_id,section_type,section_version,closure_class,check_id,semantic_copy_count,physical_replica_count,owner_id,dependency_ids,stored_payload_bytes,decoded_payload_bytes,payload_sha256,envelope_sha256,envelope_bytes,fragment_count,first_physical_unit,last_physical_unit`.
check_id=1, semantic_copy_count=1. Decoded payload equals stored payload except
body sections, where it is the exact decoded complete-frame length.
Owner IDs are `inventory`, `tier:2`, `tier:3`, `body:<section_id>`,
`capacity:<bucket_id>:<section_ordinal>`, `reserve:<zero-based-partition>`,
`load:<zero-based-partition>`. No owner is selected merely by its factor.
Derive capacity identities from the complete neutral bucket sequence and
reserve/load identities from their actual ordered partitions.

Unit columns, in physical ID order:
`physical_unit_id,section_id,semantic_copy_id,fragment_index,replica_index,physical_replica_count,encoded_bytes,encoded_sha256,slot,logical_bit_first,logical_bit_count`.
Semantic copy ID=0; encoded bytes=216, logical bit count=1728. For each sorted
section, fragment its freshly encoded envelope, then emit all complete replicas
before the next fragment. Slot=B*(id−1) mod Q; logical first=1728*slot. Check
each actual encoded unit in the matrix against this freshly encoded unit.
First/last IDs in section rows cover exactly its fragments*factor units.

Ledger keys exactly:
`stored_payload_bytes,decoded_body_payload_bytes,replicated_payload_bytes,envelope_header_bytes,section_check_bytes,fragment_header_bytes,fragment_zero_pad_bytes,local_check_bytes,transport_pad_bytes,parity_bytes,encoded_transport_bytes,logical_group_count,factor_1_group_count,factor_2_group_count,factor_5_group_count,physical_unit_count,codeword_count,real_protected_cells,capacity_probe_cells,reserve_probe_cells,load_probe_cells,shell_instruction_cells,shell_example_cells,shell_recipe_cells,shell_headroom_cells,shell_fixed_pad_cells,interior_fixed_pad_cells,unused_cells,total_cells`.
Stored payload=sum payload lengths once; decoded_body=sum decoded lengths only
for type3. Replicated payload=sum factor*stored length. Envelope headers=sum
factor*(18+4*dependencycount); section checks=sum factor*4; fragment headers=30Q;
fragment zero pad=157Q−sum factor*envelope length; local checks=4Q; transport
pad=Q; parity=24Q. Their replicated-payload/header/check/pad/parity sum must
be216Q. Group counts=sum fragment counts for each factor; their weighted sum
mustQ. Codewords=24Q. Protected cell scopes charge1728 per complete unit,
classified by section type1..3/4/5/6. Shell classes are described below.
All five shell classes+four protected classes+interior pad sumS²; unused=0.

## Actual matrix ownership and density

Verify input file length exactly4+S²/8 and its u32 cell count exactlyS².
Every `carrier_sha256` hashes complete carrier.bin, including its four-byte
cell count. The physical-byte cap excludes those four bytes. Scan
canonical matrix row-major. Derive each shell sector/local index by inverting
the four half-open bootstrap sector formulas. For each interior cell, invert
the affine map; if logical<1728Q, derive slot/bit then unit through B inverse;
otherwise it is logical-tail fixed pad. Verify both round trips, every unit's
1728 unique mapped cells, all expected owners and every actual bit against the
source-built complete shell image/unit/pad byte. No decoder output is an oracle.

Ownership keys: schema, profile_id, carrier_sha256, capacity_ledger_sha256,
side, shell_width, mapping, shell_fields/shell_rows, unit_fields/unit_rows,
interior_fixed_pad, cell_table, cell_table_sha256.
Shell columns: `sector_id,route_prefix_cells,headroom_cells,fixed_pad_cells,image_sha256,spans`.
Spans are `(start_cell,cell_count,owner)` arrays covering the complete admitted
route image. Require consecutive nonoverlapping full coverage. Normalize each
source span to the five owner strings `instruction`, `example`, `recipe`,
`headroom`, `fixed-pad`, then coalesce adjacent spans of the same class. Prefix
owner classes: worked:, held-out:, vm-discriminator:, body-codec: are example;
recipe-package: is recipe; all remaining prefix spans are instruction.
headroom* spans are headroom; fixed-pad is shell fixed pad. Thus the additional
VM/codec examples receive example cost, not incidental instruction cost.
Unit columns: `physical_unit_id,mapped_cell_sha256`. Each digest is SHA256 of
the1728 interior physical indices in ascending encoded-bit order, eachu32.

`interior_fixed_pad` keys: logical_bit_first=1728Q, logical_bit_count=P−1728Q,
fill_order=`affine-images-of-ascending-logical-tail`. The pad bits are the
MSB-first continuation of the exact capacity/reserve/load stream.
`cell_table` keys: row_bytes=9, row_count=S²,
row_order=`canonical-matrix-row-major`,
owner_kind_ids=`["1-shell-route","2-shell-headroom","3-shell-fixed-pad","4-protected-unit","5-interior-fixed-pad"]`,
owner_id_rule=`sector-id-for-shell-kinds-physical-unit-id-for-protected-unit-zero-for-interior-fixed-pad`,
owner_bit_offset_rule=`zero-based-offset-within-named-owner`.
Hash streamed9-byte rows `(kind:u8,owner_id:u32,offset:u32)`. Shell route offset
is local index; headroom/fixed-pad offsets subtract their preceding spans.
Protected offset is encodedbit0..1727; interior pad offset is logical−1728Q,
NOT its physical row-major rank. Only the hash is serialized, never a giant
cell list. This new meaning must never be admitted under ownership-v1.

Density uses the unchanged complete density-v0 field set: schema, profile_id,
carrier_sha256, scope_rows, interior_regularity. Scopes in order: shell,
real-protected, capacity-probe, reserve-probe, load-probe, fixed-pad,
complete-interior. Each row has scope_id, cell_count, zero_count, one_count,
one_density_ppm=floor(10^6*ones/count), zero for an empty scope. Fixed-pad
includes shell fixed pad and interior pad; complete-interior includes protected
and interior pad only. Regularity has longest_horizontal_equal_run,
longest_vertical_equal_run, tile_one_count_min, tile_one_count_max,
repeated_row_count, repeated_column_count, measured on the complete rectangular
interior. Count aligned complete32×32 tiles from its top-left. Repeated counts
are total rows/columns minus distinct byte patterns.
Unchanged policy: interior ones fraction1/4..3/4 inclusive; tile counts128..896;
equal runs<=max(128,ceil(I/4)); repeated rows/columns<=max(2,floor(I/32)).
Use existing failure labels/order: global-one-fraction-below-minimum,
global-one-fraction-above-maximum, tile-one-count-below-minimum,
tile-one-count-above-maximum, horizontal-equal-run-above-maximum,
vertical-equal-run-above-maximum, repeated-row-count-above-maximum,
repeated-column-count-above-maximum. A nonempty interior is mandatory.

## Search and measured static limits

Geometry keys: schema, profile_id, prefix_bytes (four integers), headroom_cells
(four integers), selected_side, selected_shell_width, row_fields, rows.
row_fields=`["side","shell_width","result"]`. Rows are every actually tested
lexicographic geometry through the first fit inclusive; labels exactly
`route-headroom`, `mapping-table`, `inventory-load-fixed-point`, `fit`.
No geometry after that fit is emitted; no earlier failure may be omitted.

Static-limits keys: schema, profile_id, scope=`static-construction-only`,
source_identities, carrier_sha256, projection_sha256, semantic_capacity,
selected_manifestation, route_package, declared_transport, realism.
`projection_sha256` keys: semantic_envelope, capacity_ledger, ownership_ledger,
density_ledger, geometry_search; their values hash the complete canonical docs.
`semantic_capacity` is exactly semantic-envelope totals.
`selected_manifestation` keys: side, shell_width, cells, carrier_bytes,
carrier_file_bytes, interior_side, population, physical_units, protected_cells,
fixed_pad_cells, inventory_entries, inventory_payload_bytes,
inventory_dependency_count, maximum_dependency_count, maximum_section_payload_bytes,
maximum_decoded_body_bytes, maximum_section_envelope_bytes,
maximum_fragments_per_section, logical_groups, factor_group_counts,
load_payload_bytes, load_fragment_counts, mandatory_physical_units,
route_prefix_bytes, route_headroom_cells.
Physical carrier bytes=S²/8; file bytes include4; factor_group_counts order1,2,5.
Mandatory units exclude only type6 load units. All maxima are actual, not copied
safety ceilings. Inventory dependency count sums all entries; maximum is perentry.

`route_package` keys: sha256, encoded_bytes, expanded_bytes, recipe_count,
table_count, table_payload_bytes, node_count, edge_count,
maximum_declared_primitive_steps, maximum_declared_scratch_bytes,
recipe_fields, recipe_rows, records_per_sector, prefix_sha256.
Recipe columns `(recipe_id,node_count,edge_count,primitive_steps,scratch_bytes)`
are ascending ID. Expanded bytes is the checked logical package encoding length.
records_per_sector and prefix_sha256 are four-element arrays. These are declared
VM logical resources, not adapter measurements or full damaged-path maxima.

`declared_transport` keys: scope=`one-pass-complete-inventory-groups`,
eh_codewords_per_unit=24, eh_decoder_calls, repetition_groups,
repetition_symbol_calls, complete_group_calls, roster_calls, body_decoder_calls,
primitive_steps, peak_recipe_scratch_bytes. This is one complete catalog pass
after inventory admission. Let G=G1+G2+G5 and H=G2+G5: diagnostic EH calls=24Q,
repetition groups=H, nested symbol count=1728H, complete group120 calls=G,
roster123 calls=G, body202 calls=count of compressed version1/type3 sections.
Steps=sum these direct calls*observed recipes30/120/123/202 declared steps;
nested symbols are already included in120 and receive no additional113 charge.
Scratch is max of those called recipe scratch. This explicitly excludes first
bootstrap127 and subsequent discovery/retries, route/adapter/native host work,
multiple paths and failed discovery;
it must not be renamed a full receiver limit or Gate4 pass.

`realism` keys: result (`pass`/`fail`), failures (ordered strings). Derived from
actual density and unchanged policy, never source expectations.

## Identity DAG and candidate manifest

Candidate keys: schema, profile_id, profile_version=8,
status=`static-projection-only`, source_identities, files, manifest_identity.
Files are sorted by ASCII path, each `(path,bytes,sha256)` object, covering
carrier.bin, route-0.bin through route-3.bin (prefixes only), and the six JSON
projection files preceding candidate-manifest.json. Exclude the candidate from
its own files. First canonicalize the complete candidate without manifest_identity;
identity is existing `identity_hex(b"golden-board:manifest:v0\\0", (omitted,))`
with the domain's final byte NUL, then canonicalize with the lowercase identity.
All other JSON documents have no self-identity field. No file hashes its own
preimage; capacity points to semantic, ownership to capacity, static-limits to
all five preceding projections, and candidate to all six plus physical bytes.

Generated limits remain separate from the tracked policy-ceiling owner until
full independent resource/damage/lifecycle admission is available. Static
outputs are deterministic comparable production inputs, not a promotion receipt.
