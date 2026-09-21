# M2 participant-revision bootstrap v2 — development owner

Profile 8, `eh72-hier-r5-r2-r1-lzss-crc32c-v1`, is a new development
candidate. This owner does not promote it or reinterpret profile 7. The
historical bootstrap-v0/v1 owners and their exposed bytes remain unchanged.
Reopening, complete carried teaching and fresh Gates 1–8 precede any new
Candidate-ready claim. The 2048-square / 512 KiB scope ceiling remains fixed.

## Storage and required closure

The revised logical content is slice-v1. Required body sections are exactly
16, 17 and 18; the all tier additionally includes 100..163 and 200..210.
Every required teaching page remains in the required closure. All 64 games
remain complete and byte-exact. Changing these sets requires revising this
owner, not accepting an arbitrary inventory declaration.

Common blocks keep the inherited 191-byte framing, local CRC32C, profile
field and fragment grammar. Their profile field is 8. Every semantic copy ID
is zero. EH72 still encodes the common block plus one mandatory zero byte
as 24 codewords / 216 bytes / 1728 bits. Local payload starts at 30;
reserved bytes 26..29 and decoded byte 191 are zero. Physical interior pad
is separately owned and may be nonzero.

The inventory section and payload use version 2. The prefix, 20-byte entry
and dependency encoding remain those of inventory v1. Entry byte 10 is one;
flags bit 0 denotes an ordinal, bits 1..3 are the literal factor 1, 2 or 5,
and bits 4..7 are zero. CRC32C check ID is one throughout. The inventory
payload itself is at most 16,384 bytes and declares its exact own length.
Every stored section payload has length 1..16,384, including probes; a
zero-length capacity need creates no probe section.

The exact factor-five / closure-128 set is `{1,2,3,16,17,18}`. Inventory 1
has type 1/version 2/no dependencies. Tiers 2/3 have type 2/version 0;
their dependencies are respectively exactly `(16,17,18)` and all 78 body
IDs in sorted order. Every body has type 3/version 0 or 1/no dependencies.
Sections 100..163 carry ordinals 0..63 respectively; no other section carries
an ordinal. All other bodies have factor one/closure 129. Unknown body IDs,
missing bodies or extra required IDs reject the inventory.

Capacity/reserve/load probes start at section 211 and have types 4/5/6,
version 0, closure 129, no dependencies and no game ordinal. Capacity factor
is 1 or 2 and must additionally match the independently derived owner class;
reserve factor is exactly 2; load factor is exactly 1. Inventory validation
alone cannot establish the complete capacity ledger or carrier eligibility.

Each entry's inherited `logical_payload_length` field counts stored section
payload bytes (encoded bytes for a compressed body). Existing envelope/local
checks bind those bytes. Body version 1 uses the exact codec in
`body-codec-v1.md`; version 0 is unchanged raw data. Tier stream lengths,
record counts and logical reserve calculations use recovered content bytes.
Assemble only after decoding every required body atomically, then apply the
full existing content-v0 acceptance rules. Invalid required content exposes
neither stream; invalid all-only content can expose valid required content
with a degraded artifact result. Diagnostic sections never establish a tier.

## Transport and mapping

Groups retain bootstrap-v1's exact all-lane plus raw-repetition enumeration,
deduplication, conflict and inventory-bootstrap rules. Physical IDs 1..5
are the first inventory fragment's five complete lanes. Every candidate,
including raw repetition after a locally valid lane, is considered.

Mapping keeps the exact table-17 smallest-multiplier rule and two-stage map.
For side S/shell W, I=S−2W, Q=floor(I²/1728), j=I/8 and B=table17[j].
For unit u/bit b, slot=B*(u−1) mod Q and logical=1728*slot+b. The inherited
affine cell multiplier is 2I−1 and the profile-dependent offset is now
`(8*40503 + W*257) mod I²`. Inverse domains and fixed-pad classification
remain exact. Geometry and all invalid indices/zero table entries reject;
no hardcoded observed mapping replaces these relations.

Recipe 109 remains the inherited modular affine primitive: it reduces its
logical argument modulo I² and has only its inherited coarse side guards.
It is not the complete physical map. The full mapping adapter owns the
multiple-of-eight geometry, shell and table domains, one-based unit ID,
encoded-bit bounds and inverse/pad checks above, before invoking that
primitive. The carried composition must show this distinction; a successful
out-of-domain primitive call does not admit a physical cell or unit.

## Recipes and remaining promotion work

The new package uses the sole grammar of `recipe-wire-v1.md`, unchanged
generic operations and full resource accounting. The inherited CRC32C/EH
recipes keep their meanings. Recipe 109 uses this new profile's affine
offset; old profile 7's package remains unchanged. The codec's complete
bounded decoder and small construction examples must be carried, not called
through a host decompression shortcut.

Carried definitions/examples must close C01–C11 in
`studies/m2/participant-learnings-v1.md`, including field widths, unit and
mapping composition, profile/status/availability distinctions, inventory and
typed-content acceptance. Their exact bytes, all four complete routes,
knowledge-use/ablation checks, total fit and independent generation are still
required before promotion. Neither this development owner nor its low-level
inventory/codec tests provide those missing results.
