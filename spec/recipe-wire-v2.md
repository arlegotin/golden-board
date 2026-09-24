# Canonical bounded recipe wire v2 — development owner

Encoding 2 is an explicit profile-8 development encoding of the unchanged
logical recipe VM. It adds no operation, value type, failure interpretation,
logical resource allowance or correction capability. Historical encodings 0/1
and their emitters/admission remain byte-exact. Encoding 2 does not promote a
carrier or establish participant acquisition.

The 64-byte package header, table records and32-byte recipe headers retain
encoding1's layout. Set the encoding u16 at
offset 8 to 2. Profile must be exactly 8. Package and recipe byte lengths count
the actual encoding-2 bytes. Reserved fields remain zero. All counts, logical
steps, edges and scratch are unchanged by compression.

Immediately after each recipe header, encode its input descriptors followed by
its output descriptors. Each descriptor is `value_type:u8, width:U32`, using
the same canonical integer grammar as nodes. Types0,1,2,3,5 are admitted;
TABLE4 and every unknown type reject. IDs are implicit ordinals starting1
separately for inputs and outputs. Flags0 and count1 are implicit: these are
already the only legal values in the logical interface grammar. A descriptor
occupies2..6 wire bytes and expands to the original12 bytes. Type/width and
first-output STATUS16 constraints are still checked by the full logical
validator. No logical interface value or capability is omitted.

Every node carries, in order:

1. tag:u8 = `(output_type << 5) | opcode`;
2. output_width:U32;
3. each argument reference:U16, in order, exactly arity(opcode) times;
4. auxiliary:U16 only for opcodes 2, 5 and 22;
5. immediate:U64 only for opcodes 1, 5, 14, 22 and 25.

U16/U32/U64 denote canonical unsigned base-128 little-endian groups, not the
big-endian integers used in the unchanged envelopes. Each byte's low seven
bits is a digit; high bit 1 means another byte follows. The final high bit is
zero. Zero is one zero byte. A multibyte value with final digit zero rejects.
U16 has at most 3 bytes and value <=65535; U32 at most 5 and <=4294967295;
U64 at most 10 and <=18446744073709551615. Truncation, continuation at the
maximum byte, excess high bits, overlong forms and crossing the recipe boundary
all reject. No resynchronization, alternate width, signed value or fallback.

The tag's low five bits are opcode 1..25; high three bits are output type
0..5. Opcode 0/26..31 and types 6/7 reject. There is exactly one tag grammar;
the earlier two-byte development measurement is not an admitted alternative.

Examples: 0→00, 1→01, 127→7f, 128→8001, 255→ff01, 256→8002,
16383→ff7f, 16384→808001, 65535→ffff03. Node IDs are implicit ordinals.
The opcode arity and omitted zero fields are exactly those of encoding 1.
No dictionary or additional executable interpreter is introduced.

Before output allocation, validate bounded headers/counts, all descriptor and
node framing; derive full logical expanded size using12 bytes per descriptor
and32 bytes per node and reject excess.
Then reconstruct encoding-0 logical bytes, with exact implicit IDs/zeros and
derived lengths, and apply every existing logical validation rule. Encoders
validate logical input before compression. Execution reparses retained bytes;
an editable cached logical view is not authority. All resource/status failures
retain their existing meanings.

Python and Rust independently implement canonical encoding and bounded decoding.
Their emitted bytes, expanded logical bytes and evaluations must agree. Old
encoding-specific entrypoints continue to reject encoding 2; active profile-8
admission selects an explicit version-aware entrypoint when this development
encoding is integrated. No historical result is reinterpreted.
