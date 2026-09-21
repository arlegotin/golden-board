# Additional carried VM teaching — development owner

`recipe-teaching-v2.toml` owns the logical programs and exact carried examples
for profile 8. It is source, not a generated package or a recipient result.
This adds no VM operation and does not change any historical recipe.

There is one three-byte UINT8 table, ID 21, containing 7, 8, 9. Recipes
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
Every other inherited recipe, table and output remains exact. The active
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
