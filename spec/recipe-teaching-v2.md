# Additional carried VM teaching — development owner

`recipe-teaching-v2.toml` owns the logical programs and exact carried examples
for profile 8. It is source, not a generated package or a recipient result.
This adds no VM operation and does not change any historical package.

The active teaching package replaces recipe110's former integer-concatenation
example with the finite group-candidate decision below. Historical/base
packages retain their original110. This repair follows the saved-method gap
in the fresh technical trials; it does not broaden the correction profile.

Recipe110 has six UINT2 inputs, then three BOOL inputs, and outputs STATUS16,
UINT2, UINT8, BOOL. The six inputs are sets of fully checked common-block
values: five physical lanes in order, then raw repetition. In the carried
examples, bit0 denotes fact7's complete A and bit1 its complete B; encode each
two-bit integer in its ordinary one-byte UINT representation. Unused/failed/absent candidate slots are zero.
These are equality-class names for the complete191 bytes, never CRCs, decoded
headers alone, or a production whitelist of A/B. The three flags are any lane
present, any locally verified lane, and agreement of every checked candidate
with the expected physical-group identity. Inputs come from fact10's complete
constructions, not supplied judgments about a participant's output.

OR all six candidate sets, including repetition after a verified lane. The
union is empty, a singleton, or conflicting. Group state is4 for a conflict,
2 for a singleton with a verified lane,3 for another singleton,1 for an empty
set with a present lane, otherwise0. Acceptance is true exactly for a singleton
and identity agreement. The same value from multiple sources stays one value;
identity disagreement prevents acceptance without pretending the local check
failed. VM status remains0 for these ordinary rejection/conflict outcomes.
This finite executable decision composes with the carried unit/EH/common and
raw-repetition constructions; it is not itself a complete carrier decoder.

Active recipe111 replaces the duplicated CRC program; fact11 uses identical
CRC recipe107. Historical packages retain111. Its inputs are BITS72 A, BITS72 B,
BOOL source, BOOL unknown, UINT8 first, UINT8 count; outputs STATUS16, BITS72
observed word, BITS72 erasure mask. Source0 selects A and1 selects B. Bit indices
are zero-based/MSB-first. For [first,first+count), unknown0 flips known bits;
unknown1 clears storage bits and marks those positions in the erasure mask.
Count0 is a no-op. Checked addition and subtraction reject overflow or a range
outside0..72 before any output. BOOL admission rejects selectors outside0/1.

Table22 contains one BITS144 value, nine zero bytes followed by nine FF bytes.
Slice72 bits at72-first and72-(first+count); XOR gives the range mask. SELECT,
XOR and AND construct the two outcomes using the existing generic VM. No
host-only operation or BITS shift is introduced. The ordinary fact10 pair
uses the same first59/count5 with unknown1 and unknown0, respectively, and
carries both source words and the four separately typed descriptor fields.
All thirteen observed templates are additionally executed and checked against
independent word/mask construction before the group traces.

Table21 is three UINT8 values7,8,9. Recipes
210–212 preserve the logical conformance/recipe-v0.json programs 1–3 with
their recipe/table references renamed. The source lists the complete logical
programs so independent builders need not read another builder's package.
Recipe 213 takes a UINT8 accumulator and UINT64 iteration index, looks the
index up in existing identity table 5, and adds it using checked arithmetic.
Recipe 214 runs it three times. The additions share the existing table 5;
they do not carry another copy of it.

Every descriptor pair is `(type, width)`, with implicit increasing IDs and
count one. Every nine-integer node row is `(opcode, type, width, arity,
argument0, argument1, argument2, auxiliary, immediate)`. Unused arguments
must be zero. Node IDs are implicit increasing ordinals. The opcode's existing
arity and every existing reference, type, output, status and resource rule
remain mandatory. The auxiliary-u32 field remains zero. This is a source
notation only; actual bytes use recipe-wire-v1.md, never this table notation
as a new executable interpreter.

Construct recipes in increasing ID order after the inherited and body-codec
recipes; derive complete logical edges, steps and scratch before compact
encoding. The active teaching package omits inherited recipe106: its old
byte-is-zero example was replaced by211, and no retained example, helper call
or receiver operation consumes106. This removes134 compact bytes and its five
nodes; it does not assign the dead predicate an invented use. The historical
profile7 and standalone profile8 revision packages retain106 byte-for-byte.
Except for the active110/111 replacements above, every other inherited recipe,
table and output remains exact. The active
recipe ID set is exactly
`1,2,3,4,30,90,92,99,100,101,102,103,104,105,107,108,109,110,111,112,113,201,202,203,210,211,212,213,214`.
The receiver's route2 allowlist must enforce this complete set; neither
missing live recipes nor the former unused106 is an admitted substitute.
No implementation may copy the other implementation's encoded package as its
generation input. Parse this bounded source with exact keys/types/counts,
or construct the exact same logical rows independently.

Examples concatenate the declared input values and an output containing
STATUS16 followed by data only on success. The worked/held rows distinguish
all operations, byte CONCAT, immutable WRITE, nonzero EMIT offsets and
iteration. Additional rows distinguish quotient failure, checked shift
overflow, checked addition overflow, explicit failure suppressing an earlier
data EMIT, iteration index progression and failure propagation. A failed
example is valid teaching; it does not make its underlying malformed operation
successful. These finite examples supplement the full carried procedure and
do not by themselves prove recipient VM conformance.

All rows must evaluate to their frozen output before any route is returned.
Extra WORKED/HELD_OUT example records are permitted only by the new route
owner. Old route owners retain their exact record counts and success rules.
