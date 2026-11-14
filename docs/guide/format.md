# From bytes to lessons

The payload uses a small document format. It can describe a picture, change a
few cells, offer a response and follow a link. The player needs no chess rules to
do any of those things.

The message teaches one grammar. Development revision numbers live in project
records; they are not fields the recipient has to decode. The current release uses this
grammar; its raw reconstruction was checked with the submitted recipient decoder.

## Sections and inventory

After the bootstrap, six sections follow one another: inventory 0, then documents
1–5. Each section has this layout. Widths below are bytes.

```text
ID:2 | body length:4 | body:N | CRC-32C:4
```

The check covers the six header bytes and the body. ID 0 identifies the
inventory; positive IDs identify documents. Integers use the high byte first.

CRC-32C starts at `ffffffff`. XOR each byte into the low end, then perform eight
right shifts, XORing `82f63b78` after a shift when the previous low bit was 1.
Finally XOR with `ffffffff` and store the result high byte first. These choices
are demonstrated in the bootstrap.

The inventory begins with a two-byte document count.
For each document, it lists:

```text
ID:2 | body length:4 | section check:4 | entry count:2 | entry IDs:2 each
```

Entries are the pages or traces a reader can open directly. The inventory must
agree with the actual sections and their entry lists. No section can be missing,
duplicated or inserted out of order. The decoder accepts the complete checked
set; it does not expose a successful partial reconstruction.

## Five kinds of record

A document starts with bytes `d6 39`, two-byte entry and
record counts, then the two-byte entry IDs. Records follow in increasing ID order:

```text
kind:1 | ID:2 | payload length:4 | payload:N
```

| Kind | Record | What it carries |
|---|---|---|
| 1 | Glyph | A small binary bitmap with its dimensions |
| 2 | Frame | A rectangular grid of glyph IDs, plus optional selectable regions |
| 3 | Trace | An initial frame, references to numeric tables and ordered cell updates |
| 4 | Page | A frame or trace, response type, choices, accepted responses, feedback and links |
| 5 | Table | A rectangular array of unsigned numbers |

IDs name records within their document; they do not carry a hidden chess meaning.
The reserved ID `65535` means an absent optional reference. Every actual reference
must name an existing record of the right kind.

<details>
<summary>Exact payload fields for implementation</summary>

| Record | Fields, in order |
|---|---|
| Glyph | Rows and columns, one byte each; packed bitmap with zero low-bit padding |
| Frame | Rows/columns, one byte each; one glyph byte per cell; two-byte region count; pairs of two-byte region ID and cell index |
| Trace | Two-byte initial-frame ID; one-byte table count and two-byte table IDs; four-byte step count; each step has a two-byte change count and pairs of two-byte cell index and one-byte glyph |
| Page | One-byte display kind and two-byte display ID; one-byte response shape; two-byte choice count and IDs; two-byte accepted-response count, each with a two-byte length and IDs; two-byte success/failure/passive IDs; two-byte link count and IDs |
| Table | Four-byte row count, one-byte column count; two bytes per value |

</details>

## A trace changes only the named cells

In the bootstrap miniature, the initial glyph grid is:

```text
0 1 1
1 0 1
```

Step 1 changes cell 0 to glyph 1. Step 2 changes cell 5 to glyph 0. Seeking to
frame 0 shows the initial grid; seeking to frame 2 applies both updates:

```text
1 1 1
1 0 0
```

Unmentioned cells stay as they were. The same operation plays a chess game. The
player applies carried changes; it never derives the next board from a move.
Numeric moves and visible playback both remain in the artifact.

## A page defines the interaction

Responses have four shapes: passive, one choice, a set or an ordered sequence.
The player provides five actions:

| Action | Result |
|---|---|
| Select | Replace a single choice, toggle a set member or append to a sequence |
| Reset | Clear the uncommitted selection |
| Commit | Compare the selection with the page's carried accepted responses and open its feedback page |
| Link | Open a carried page reference |
| Seek | Show a numbered frame of the current trace |

Selecting does not submit an answer. An empty commit does. Sequence order matters;
set order does not. Invalid actions report an error and leave the current state
unchanged. A complete passive route supplies the instruction and feedback without
requiring the learner to answer correctly.

Lengths, dimensions, references, glyphs, regions and update positions are checked
before use. The format contains no script, URL, filesystem instruction or chess
operation to execute.

Next: [the lessons](lessons.md).

Exact references: [document codec](../../src/golden_board/document.py),
[generic player](../../mechanism/player.mjs), [literal miniature](../../spec/vectors/current-mini.hex).
