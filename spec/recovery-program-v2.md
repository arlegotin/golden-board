# Profile-8 executable physical recovery

This development owner replaces the host-composed group teaching in route2.
It does not promote a carrier or change a historical trial result. The carried
programs use the existing 25 VM operations and types; recipe-wire-v2 changes
their storage only. The bounded logical source is recovery-program-v2.toml.
Source and observed-program admission retain all existing VM resource limits.

## Physical ownership before recovery

The receiver first admits orientation, route, geometry and mapping. The route
establishes inventory section1, type1, version2, semantic copy0, factor5, first
fragment0 in physical units1 through5. This is the only pre-inventory ownership
anchor. It is not derived from whichever damaged lane happens to decode.

The first inventory group's unique locally valid common block supplies its
bounded envelope length and fragment count. Subsequent inventory fragments
occupy consecutive groups of five. Their complete expected keys use those
first-fragment values and their physical fragment ordinal. Complete section
checks, inventory self-description, typed entries, dependency closure and
physical coverage are still required before the inventory becomes authority.
An inventory lookup cannot establish its own admission precondition.

Program127 is the first-group entry: UINT32 physical unit limit, UINT8 presence,
and five BYTES432 pairs. It invokes119 with factor5 and a zero comparison key,
then requires a unique local candidate with profile8/section1/copy0/type1/
version2/fragment0, envelope length22..16406 and5×fragment_count no greater than
the supplied checked geometry limit. The limit must be5..2389 or the call
returns status3 without outputs. Outputs are STATUS16, local state:u8,
bootstrap-accepted:BOOL and the191-byte block (zero unless bootstrap-accepted).
Length/count are read from that accepted block for subsequent120 calls. The
limit is caller-supplied geometry, not information learned from decoded headers.
Even a127-accepted fragment may contain a bad envelope check or malformed
inventory; complete admission below remains mandatory.

For an admitted inventory, programs121–123 traverse its actual entry bytes in
section-ID order. An entry consumes20+4×dependency_count inventory bytes. Its
section envelope consumes22+4×dependency_count+payload_length bytes, and its
fragment count is ceiling(envelope_length/157). Starting at physical unit1,
each entry owns fragment_count×physical_factor consecutive units. A queried
unit selects a fragment by division by that entry's factor. This determines
the complete physical group, factor and expected identity before lane decoding.
Erased member headers cannot remove, move or relabel a physical input.

Program123 accepts BYTES16384 padded admitted inventory, exact UINT16 length,
and UINT32 queried physical unit. Its outputs are STATUS16, UINT8 factor,
UINT32 first unit, UINT32 inclusive last unit, BYTES20 expected key, and UINT32
total physical units. Program122 is its reusable state kernel;121 is the
entry step. The818-iteration bound is floor((16384−8)/20), including every
inventory that fits the existing payload bound. Whole traversal must end at
the exact declared length, with strictly increasing IDs and a selected group.
All speculative reads are bounded before eager evaluation. Invalid active
entries fail rather than being skipped after a successful lookup.

Program124 maps (UINT16 side, UINT16 shell width, UINT32 unit, UINT16 bit) to
six UINT32 outputs: slot, logical interior index, physical interior index,
matrix row, matrix column, row-major matrix index. It validates the geometry,
unit and bit domains, applies table17's slot permutation and then the complete
affine cell mapping. It returns no output on invalid input. This forward map
does not infer orientation or replace mapping-table admission.

## All observations enter one group procedure

Program120's inputs are UINT8 factor, UINT8 presence mask, BYTES20 expected
key, then five BYTES432 lane pairs. Factor is1,2 or5. Each pair contains216
observed bytes followed by216 unknown-mask bytes; both are MSB first, and a
mask1 means unknown. Unknown observed bits are zero. Every absent or
out-of-factor pair is entirely zero, and out-of-factor presence bits are zero.
Malformed input shape returns status3 with no outputs.

The key concatenates big-endian profile:u16, section_id:u32,
semantic_copy:u16, section_type:u16, section_version:u16, fragment_index:u16,
fragment_count:u16, envelope_length:u32. These bytes are a comparison target;
the group procedure does not make a caller-supplied key inventory authority.

Program119 is the reusable group kernel. Programs114–118 derive raw repetition,
perform bounded per-word EH correction, validate local common framing/padding/
CRC, and accumulate the complete candidate union. Program120 and ordinary
construction examples invoke the identical119 program through ITERATE.

For each bit, repetition uses all physically present raw lanes, including
lanes whose individual EH decoding fails. A value is determined only when
2×known_opposite+unknown_or_absent < factor. Factor1 has no additional REP
candidate. All five original lanes and the raw REP candidate are examined;
inactive candidates are ineligible, not shortcuts around input canonicality.

An uncorrectable EH word is ordinary candidate-invalid data. It cannot stop
the other candidates from being examined. Machine/resource failures remain
atomic failures. Correction has the same bounded72-bit search as the existing
transport; it does not use CRC constraints to extend the correction radius.
Each candidate then requires all24 words, the zero transport pad, the complete
profile8 common grammar, exact fragment/payload lengths, zero unused payload,
reserved fields and CRC32C. Semantic copy and section version remain unrestricted
u16 values locally; physical acceptance compares them against the expected key.

Deduplication compares every one of the191 common-block bytes. Any two distinct
locally valid candidates cause conflict, including an original lane versus
REP. Voting cannot erase that conflict. Only after local validation is the
complete key compared. A unique result is verified when an original valid lane
was fully known and uncorrected; otherwise it is recovered.

Outputs are STATUS16, UINT8 local state, BOOL accepted, BYTES191 unique local
block. Local states are0 missing,1 corrupt,2 verified,3 recovered,4 conflict.
The block is zero for missing/corrupt/conflict. A unique foreign block remains
available as a local diagnostic with accepted=false. This distinction permits
the explicit first-inventory bootstrap; it never permits relocation or artifact
acceptance based on an observed header.

## Reusable state interfaces

Kernel119 takes (BYTES4096,UINT64 iteration) and returns STATUS16,BYTES4096.
The iteration argument is ignored. Input byte0 is factor,1 presence,2..21 key,
and22..2181 the five lane pairs. All subsequent input bytes are reset. Its
output is zero except unique local block2806..2996, state3010 and accepted3011.
Every returned byte, including zeros, belongs to the generic/native contract.

Kernel122 takes (BYTES16431,UINT64 iteration) and returns STATUS16,BYTES16431.
Only raw inventory0..16383, exact length16384..16385, and target16396..16399 are
inputs. All supplied derived metadata is ignored. Its checked final state has:
length at16384:u16, cursor16386:u16, next unit16388:u32, previous section16392:u32,
target16396:u32, found16400:u8, factor16401:u8, first16402:u32, last16406:u32,
key16410:20 bytes, header-admitted16430:u8. The raw inventory remains unchanged.
It initializes cursor8, next unit1, and recomputes header admission; successful
completion requires found1 and cursor equal to length. The output is the whole
checked state, not merely the selected result fields.

## Worked construction and transfer

An ordinary carried construction starts with a raw miniature inventory and a
physical query, derives its expected group through122, constructs all raw lane
observations from explicit carried bytes/ranges, and calls119. It takes no
candidate-valid mask, supplied conflict flag, expected-identity Boolean or
precomputed REP result. The constructor is an example source, not a whitelist
for120: arbitrary correctly shaped lane data remain valid inputs.

Examples cover absence, corrupt lanes, clean and corrected recovery, a valid
lane conflicting with raw REP, all-individually-corrupt REP recovery, raw unknown
bits, and valid data in the wrong physical group. The finite miniature illustrates
roster traversal; it is not a production inventory passing full content admission.
Transfer checks use fresh source inventories and groups outside those examples,
including distinct valid payloads and erased member headers. Worked results,
generic execution and owner transfer checks do not establish human acquisition.

## Exact native execution and charging

Native execution is permitted only for the exact observed transitive logical
program/table closure, following program-refinement-v2. Compare every interface,
node, argument, auxiliary field, immediate, resource declaration and referenced
table. Construct the reference closure from neutral source programs, never a
regenerated route, current carrier, saved participant answer or expected result.
Unsupported closures cannot use the native result. A digest or finite examples
alone cannot authorize a different program.

The native state relation preserves raw presence/unknown bits; every word's
bounded local correction result; raw REP; complete local candidates; the first
candidate, conflict, original verified witness and all expected-key comparisons.
The roster relation preserves byte cursor, next physical unit, preceding ID,
whole traversal admission and selected range/key. Typed input rejection, status,
all output bytes and absence on failure must agree with generic execution.

Charge the complete observed generic declaration before each logical call,
including failure and cache reuse. Native acceleration changes elapsed time,
never the gate, logical step count or scratch accounting. Ordinary wrappers are
charged once by their recursively derived declaration; their internal kernel
calls must not be charged a second time. Generic and native differential checks
support this implementation relation and are labelled accurately in evidence.
