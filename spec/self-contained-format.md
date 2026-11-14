# Current message grammar

Engineering revision7 (final bootstrap layout), 2026-11-14. Revision numbers are external development
metadata; none is carried in the square. Supersedes current-use wire5/document1
headers only. Historical specifications, vectors, candidates and claims remain.

The square is2048×2048binary cells, MSB-first packed row-major into524288bytes.
The32panels64×64 occupy rows0–63. Payload starts at packed offset16384; exactly
507904bytes are available. Serial presentation is4194304ASCII0/1characters with
one optional finalLF, carrying identical cells. All16rotation/reflection/polarity
presentations normalize uniquely. Clean complete observations only; no recovery.

All integers below are unsigned, big-endian. Sections occur in increasing ID
order: inventory0, then declared documents1–5. Each primary section occurs once:

`ID:u16 | length:u32 | body:length | CRC32C:u32`

CRC covers the six header bytes and body. Startffffffff, XOR each byte into the
low end, perform eight reflected shifts with polynomial82f63b78, finalXORffffffff,
store high byte first. Check detects faults; never restores content. A literal
section vector is `000100000002aabbbec1ff10` (ID1, two bodybytesaabb).

Inventory: `document_count:u16`, then each `ID:u16, length:u32, sectionCRC:u32,
entry_count:u16, entryIDs:u16[]`. Counts/lengths/checks/ordered roots must match
actual sections; no missing/duplicate/extra sections or nonzero final reserve.

Document: `d639 | entry_count:u16 | record_count:u16 | entryIDs:u16[]`, then
increasing unique records `kind:u8 | ID:u16 | length:u32 | payload:length`.
Five record payload kinds and optionalNONE65535 retain their existing meanings;
see [current field reference](../docs/guide/format.md). Internal model APIs may
retain a virtual schema tag; it is not a field in the message. Framing, record
types, dimensions, padding, references and bounds remain strict. No format
autodetection, hidden chess logic or guessed missing data.

[Current326Bminiature](vectors/current-mini.hex) uses three2×3glyphs: blank000/000,
pattern110/101 and contrast001/010. All non-glyph miniature records are unchanged.
The [pre-clarity miniature](vectors/pre-clarity-mini.hex) remains a named
historical fixture; it is not the miniature drawn in the final bootstrap.
The section is336B; its
inventory section28B; concatenation364B. All three miniature glyphs are used.
Section/inventory/header/CRC-scope drawings use these actual bytes. Panel7 carries
only four quantities: side2048, start64, eight bits/byte and actual usedbytes,
atx14 with16/16/16/32bit widths. The oldx8reader does not transfer. Glyph0/1are
defined together in22, assembled in23, updated in24; pages/outcomes/actions and
passive routes occupy25–28. No payload-body or document/section grammar change
accompanies this engineering revision.

Complete product pruning removes only glyph definitions unused by any frame or
trace update in their local document. Numeric table values are not glyph refs.
Visible glyph masks and all surviving IDs remain exact. Document5 table841 was
an extra SHA fingerprint; its sole trace846 reference is removed too. CRC and
inventory integrity stay. Games directory columns, move/playback/schema tables,
source proofs, response fields and semantic zero values remain.

Historical input conversion is allowed only at two SHA-pinned authoring imports;
it is not recipient reconstruction. Exact historical codec source is retained in
`inputs/qualified/` for old qualification guards; current readers get
new native parity and raw-recipient evidence. Developer revisions remain in
reports/manifests so old candidates can be reproduced without carried labels.
