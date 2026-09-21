# Compact recipe wire v1 — development contract

This new encoding preserves the existing 25 recipe operations, value types,
arithmetic, iteration, status/output rules and all resource ceilings. It is
not permission to change any existing profile's wire format or passing result.
The participant-revision candidate reserves profile 8; it is not promoted.
The hard carrier ceiling remains 2048 squared bits (512 KiB).

Before promotion, the initial fixed-24 development experiment was replaced
by the opcode-specific grammar below. Its old measured bytes remain a labeled
local experiment, not an admitted encoding. Encoding 1 now has exactly this
one grammar: no fixed-24 fallback, sniffing or resynchronization is allowed.

The package remains a 64-byte header with `GBRECP0\0` magic. The u16 encoding
version at offset 8 is 1 instead of 0; ABI version at 10 remains 0. Tables and
the 32-byte recipe headers and 12-byte value descriptors retain their v0
fields. Package byte length at 32 and each recipe byte length at 28 describe
the actual compact bytes. A recipe's exact size is
`32 + 12*(inputs+outputs) + sum(encoded_node_size)`.

Each node starts with a six-byte prefix, followed only by opcode-assigned
fields, in this exact order:

| Offset | Value |
|---:|---|
| 0 | opcode u8 |
| 1 | output type u8 |
| 2 | output width u32 |
| 6 | argument u16, repeated exactly arity(opcode) times |
| following arguments | auxiliary u16, only for opcodes 2, 5, 22 |
| following auxiliary, if any | immediate u64, only for opcodes 1, 5, 14, 22, 25 |

All multibyte integers remain big-endian. The node ID is its one-based ordinal
within its recipe. Arity is uniquely determined by its opcode: 0 for
1/2/24/25; 1 for 5/14/22; 3 for 3/20/23; 2 for the remaining admitted opcodes.
There are no varints, flags, alignment bytes or explicit node lengths.
Assigned fields are mandatory even when zero; unassigned fields are absent.
The full 32-bit width, 16-bit arguments/auxiliary and 64-bit immediate remain.
Expansion inserts zero unused argument slots, zero unassigned fields and
the zero v0 auxiliary-u32 field. No EMIT offset is lost: it is the existing
immediate-u64. Encoding validates the original complete logical package before
discarding any zero field; it must not sanitize an invalid source package.

Both independent decoders first bound every count, length and multiplication.
Recipe headers delimit node bytes. Each opcode determines its exact node
width (6..18 bytes) before reading its operands. Reject unknown opcodes,
crossing the recipe boundary, extra bytes after its declared node count or
inconsistent final package end. Derive total expanded size from unchanged
table/descriptor/header lengths plus 32 bytes for every declared logical node;
bound it before allocating. Then reconstruct implicit fields/lengths and apply
all existing recipe validation stages. Expanded size remains under the
existing package maximum. All declared nodes, edges, steps and peak scratch
are checked from the expanded logical program, not discounted because its
wire encoding is smaller. Unrecognized opcodes, trailing bytes, truncated
records, invalid references and inconsistent resources reject atomically.

For diagnostics the codec may round-trip existing logical profiles 1..7 in
this new wire format; their historical carrier owners continue to reject it.
Profile 8 uses the same semantic parser under this new explicit admission.
The original public v0 parser/evaluator keep their original profile range
1..7 and version-zero admission. New entrypoints cannot make version-one
bytes acceptable to the old profile owner.

The codec must independently reproduce compact bytes from each language's
logical recipe package. Expansion must recover the same logical package
exactly, and evaluation reparses wire bytes before execution. Current package
savings and future decoder costs are measurements, not carrier eligibility.
The present 699-node logical package compacts from 25,930 to 11,664 bytes,
with unchanged logical resources; this is a diagnostic target.
Complete route grounding, content decompression, geometry, damage, resource,
and acquisition evidence remain required before promotion.
