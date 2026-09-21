# Carried Position and Move16 examples v2

This development owner adds an exact 408-byte numeric suffix to route fact 12.
It leaves the 65 learner pages, final questions, chess rules, and all historical
formats unchanged. The suffix connects actual recovered matrices and opaque
subjects to canonical bytes. It is finite teaching, not an independent chess
validator, a new artifact admission rule, or evidence of recipient success.

Every integer is unsigned big-endian. Context 0 is the current required
ContentStream; context 1 is the current all ContentStream. Record references
are within their stated context. Offsets into a MATRIX refer to its decoded
cell array, excluding its schema/row/column header. Offsets into an OPAQUE
subject refer to its data bytes, excluding its two-byte binding reference.
`L(rows)` means count:u16 followed by pairs of u16, as in route definitions.

## Exact suffix construction

Concatenate these components in order; offsets below are within the suffix.

| Span | Bytes | Construction |
|---|---:|---|
| 0..2 | 2 | version:u16 = 2 |
| 2..20 | 18 | Position layout `L((0,64),(64,1),(65,1),(66,1))` |
| 20..26 | 6 | `(context=0,matrix_record=43,output_length=67)` as u16 |
| 26..82 | 56 | count9:u16, then the nine extraction triples below, all u16 |
| 82..149 | 67 | pure Position extracted from MATRIX43 and checked by replay |
| 149..161 | 12 | `(context=1,opaque_record=717,tagged_start=22,tagged_length=68,position_start=23,position_length=67)` as u16 |
| 161..229 | 68 | exact OPAQUE717 data bytes `[22,90)` |
| 229..296 | 67 | exact OPAQUE717 data bytes `[23,90)`, checked by replay |
| 296..314 | 18 | Move16 bit fields `L((10,6),(4,6),(1,3),(0,1))`; pairs mean least-significant-bit index and width |
| 314..388 | 74 | count12:u16, then the twelve six-byte Move16 rows below |
| 388..394 | 6 | `(context=1,opaque_record=589,subject_length=69)` as u16 |
| 394..408 | 14 | game layout `L((0,2),(2,66),(68,1))` |

The Position layout's four fields are canonical square bytes, side, rights,
and nominal target code. The Move16 fields are origin, destination, promotion,
and reserved zero. The game layout fields are ply count, complete Move16
sequence, and score. These relationships are grounded by actual source bytes
and the finite consequences, not by carrying their English names.

The nine `(source_cell,position_offset,count)` triples are:

```text
(204,0,8) (177,8,8) (150,16,8) (123,24,8) (96,32,8)
(69,40,8) (42,48,8) (15,56,8) (258,64,3)
```

MATRIX43 is the required 20x27 matrix on the worked target21/square20 page.
Its post-move board starts at column15. Copy the eight rank slices in canonical
square order and then its three footer bytes. The result must equal public
chess re-encoding after the first move of canonical game0, `31c0` (origin12,
destination28, no promotion). Its last three bytes are `01 0f 15`, including
nominal target21 even though no opposing pawn can capture. Its complete bytes:

```text
0402030506030204010101010001010100000000000000000000000001000000
0000000000000000000000000000000007070707070707070a08090b0c09080a
010f15
```

The literal is a check vector, never a substitute for source extraction and
independent replay. Existing required matrices33/43/53/63/73 provide absent0,
21→20,43→42,45→44, and expiry to0. This suffix ties their displayed field to
canonical byte offset66; it does not redefine nominal versus effective target.

OPAQUE717 is section200's actual namespace3/code1 fixture. Its full90-byte
subject is version0, kind1; prior byte length12 and six Move16 values; subject
length2 and move `1060`; expected length68; variant1 and Position67. Parse the
lengths and require exact EOF before extracting either carried result. Replay
the six prior moves from the standard start, apply the subject with the public
chess API, and require exact `encode_position` equality. Also require
`encode_position(decode_position(raw)) == raw` for both 67-byte examples.
The fixture variant1 byte is **not** generic VM STATUS16 or part of Position.
Other fixture variants have different payloads; this example does not license
stripping one byte from arbitrary fixture results.

Each Move16 row is `(wire:u16,origin:u8,destination:u8,promotion:u8,
wire_admitted:u8)`. Rows are, in order:

```text
c790 49 57 0 1    c792 49 57 1 1    c794 49 57 2 1
c796 49 57 3 1    c798 49 57 4 1    c79a 49 57 5 0
c79c 49 57 6 0    c79e 49 57 7 0    1950  6 21 0 1
e6a0 57 42 0 1    31c1 12 28 0 0    30c0 12 12 0 0
```

Generate the first eight from the actual promotion-queen fixture's subject
`c792`: clear bits3..1, then substitute promotion0..7. Check promotion1..4
against actual fixture subjects3..6. Generate `1950`/`e6a0` from game0's
zero-based plies2/3. Generate `31c1` by setting the reserved low bit on game0's
first move. Generate `30c0` by replacing its destination with its origin.
Derive projected fields from shifts/masks and verify the admission bit using
public `decode_move`; admitted values must re-encode identically.

Wire admission is **not legal move admission**. In the promotion fixture's
replayed prestate, `c790` decodes but applying it rejects for missing promotion;
`c792` decodes and applies legally. Validate that distinction while constructing
the examples. Reserved promotion codes, reserved low bit, and equal squares
reject at wire decoding before any board lookup. Current final questions still
display decoded triples; their result measures consequence interpretation,
not independent discovery of these fields.

The game subject is actual section100 namespace2/code1, binding588/OPAQUE589.
Require its data to equal compiled canonical game0. Parse count33, exactly66
move bytes and score0, with no trailing bytes; verify the complete record with
the public chess source-record validator. The layout is generated from those
lengths, not copied as a generic fixed-size rule for every game.

## Source checks and interface

`build_position_teaching_v2(compiled)` returns a fresh frozen
`PositionTeachingV2(value:bytes)`. Revalidate both complete content streams and
supplied digests/projections before source lookup. As with route definitions,
implementations with private admitted streams and no separate hash fields use
typed re-encoding and compiler source identity instead. Verify actual section
assignments, DATA namespaces/codes, OPAQUE binding references, and equality to
the compiled game/fixture payloads. Bound source lists and packet lengths before
scanning. All examples must come from the current source; changed record IDs,
shapes, bytes, or consequences that violate the explicit examples fail closed
until this owner is revised. Full anthology identity remains the canonical
source compiler's responsibility; this helper checks the selected examples.

An implementation may not load another implementation's serialized suffix as
its production input. Host validation is construction evidence only; the
carried relationships still require independent interpretation. No handout
wording or project-specific Position identity is counted as artifact teaching.
