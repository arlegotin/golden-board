# The message

Golden Board is 4,194,304 binary cells arranged as a 2048 × 2048 square. Packed
eight cells to a byte, it occupies 524,288 bytes: 512 KiB.

The top 64 rows form a strip of 32 bootstrap panels. Each panel is 64 × 64 cells.
The remaining 1,984 rows hold the lessons, games and the checks needed to read them.

The recipient is assumed to recognize a deliberate message, count, reason about
sequences and shapes, and write simple programs. The input is already a clean
sampled square or an ordered stream of symbols. Receiving a signal or scanning a
physical object is a separate problem.

```text
                2048 cells
┌────────────────────────────────────────┐
│ 32 bootstrap panels                    │ 64 rows
├────────────────────────────────────────┤
│ Inventory                              │
│ Five documents                         │ 1984 rows
│ Unused reserve                         │
└────────────────────────────────────────┘
```

The square and the serial file carry the same bits in the same order. Start at
the top left, read each row left to right, then continue with the next row. The
serial file writes these as `0` and `1`, with an optional final line feed. In the
displayed image, black is `1` and white is `0`. Discovering the intended direction
and polarity is part of reading the bootstrap.
The text presentation uses one character per cell: 4,194,305 bytes with the final
line feed. The binary message itself remains 512 KiB.

## What fills the square

These are the measured sizes of the complete current release.

| Part | Bytes | Cells |
|---|---:|---:|
| Bootstrap | 16,384 | 131,072 |
| Inventory | 268 | 2,144 |
| Five document bodies | 506,181 | 4,049,448 |
| Six section headers and checks | 60 | 480 |
| Unused reserve | 1,395 | 11,160 |
| **Total** | **524,288** | **4,194,304** |

There is no space outside this count that the recipient needs to read the message.
The document bodies include the actual pictures, practice responses, feedback,
passive routes and game playback.

| Document | Contents | Body bytes |
|---|---|---:|
| 1 | Representation and interaction before chess | 13,245 |
| 2 | All 64 complete games and their playback | 93,017 |
| 3 | Board, pieces, movement and king safety | 35,296 |
| 4 | Special moves, history, endings and game reading | 195,452 |
| 5 | Tactical and pawn relations, mating, guidance and exploration | 169,171 |

Document numbers identify storage. The learning sequence starts with 1, then
3, 4 and 5; document 2 is the anthology. The [lesson map](lessons.md) explains
the connections.

## Finding a byte

The payload starts at row 64, packed-file byte offset 16,384. Each row contains
256 bytes. For payload byte `k` and bit `b`, counting both from zero:

```text
row    = 64 + floor(k / 256)
column = 8 × (k mod 256) + b
```

Bits within a byte run from most significant to least significant. Byte 0 starts
at row 64, column 0. Byte 255 ends at column 2047 of that row. Byte 256 starts
the next row. Sections continue across row boundaries; rows are not packets.

## Reading clean input

Each payload section is stored once. Identical pictures and other inert records
can share references inside a document; calibration and teaching examples may
repeat a pattern. Those repetitions explain the message rather than reconstruct
a lost copy.

The reader checks lengths, identifiers, references, inventory and CRC-32C checksums
before accepting the content. A checksum detects a mismatch. It cannot restore a
missing bit, authenticate a sender or choose a plausible chess move. Invalid
content is unavailable.

The clean square may be rotated, reflected or have its two cell states exchanged:
eight geometric arrangements × two polarities give 16 presentations. These are
tested. Damaged cells, missing regions, perspective correction and reception from
a radio signal are outside the input contract.

Next: [read the bootstrap](bootstrap.md).

Exact references: [current transport implementation](../../src/golden_board/clean_carrier.py),
[complete cell ledger](../release/baseline.json),
[release identity checks](../release/verification.json).
