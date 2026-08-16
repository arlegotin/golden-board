# Golden Board identity and canonical manifest v0

This specification is the sole owner of Golden Board's developer identity
framing and canonical-manifest v0 bytes. Implementations and fixtures prove this
contract but do not redefine it.

## Primitive encodings

- `u16_be(n)` is exactly two unsigned big-endian bytes for
  `0 <= n <= 65,535`.
- `u32_be(n)` is exactly four unsigned big-endian bytes for
  `0 <= n <= 4,294,967,295`.
- A byte field is `u32_be(length) || bytes`.
- A field list is `u16_be(count) || field_0 || ... || field_(count-1)`.
- Bounds are checked before output construction. Overflow or an out-of-range
  declared length rejects.

## Domain-separated identity

An identity domain is a literal registered ASCII byte string ending in one NUL
byte and containing no earlier NUL. The registered product domains are exactly:

```text
golden-board:manifest:v0\0
golden-board:position:v0\0
golden-board:repetition-key:v0\0
golden-board:game:v0\0
golden-board:game-set:v0\0
```

Fixture-local domains such as `test:a\0` and `test:b\0` test framing but are not
registered product domains.

For domain `D` and ordered byte fields `F`, the exact preimage is:

```text
D || u16_be(len(F)) || concat(u32_be(len(field)) || field for field in F)
```

The identity is SHA-256 of that preimage, rendered as exactly 64 lowercase
hexadecimal characters. There is no implicit UTF-8 conversion, Unicode, path or
newline normalization, field sorting, extra delimiter, or terminal LF.

A manifest identity has exactly one field: the complete canonical-manifest
bytes, including their final LF, under `golden-board:manifest:v0\0`.

The other four registered identities also have exactly one field. Their exact
hand vectors are below. The position and repetition-key fields are the standard
initial 67-byte chess-v0 values. The game is Fool's mate (`f2-f3`, `e7-e5`,
`g2-g4`, `d8-h4`) with `SCORE_SECOND_WIN`; the set contains exactly that game.

```text
name = initial-position
domain_hex = 676f6c64656e2d626f6172643a706f736974696f6e3a763000
field_hex = 04020305060302040101010101010101000000000000000000000000000000000000000000000000000000000000000007070707070707070a08090b0c09080a000f00
preimage_hex = 676f6c64656e2d626f6172643a706f736974696f6e3a76300000010000004304020305060302040101010101010101000000000000000000000000000000000000000000000000000000000000000007070707070707070a08090b0c09080a000f00
sha256 = 7d578698cdb2095a1b818234f12b3e6d4f19bbadb414887f26e6a8d52417a186

name = initial-repetition-key
domain_hex = 676f6c64656e2d626f6172643a72657065746974696f6e2d6b65793a763000
field_hex = 04020305060302040101010101010101000000000000000000000000000000000000000000000000000000000000000007070707070707070a08090b0c09080a000f00
preimage_hex = 676f6c64656e2d626f6172643a72657065746974696f6e2d6b65793a76300000010000004304020305060302040101010101010101000000000000000000000000000000000000000000000000000000000000000007070707070707070a08090b0c09080a000f00
sha256 = b12da42c15cc340394688be5d771ad8936241e9dcb03592b2791e06b9dbe33e3

name = fools-mate-game
domain_hex = 676f6c64656e2d626f6172643a67616d653a763000
field_hex = 00043550d24039e0edf001
preimage_hex = 676f6c64656e2d626f6172643a67616d653a76300000010000000b00043550d24039e0edf001
sha256 = c49a921d652aa82b69a320073ca7ca0f5f3adf3d4ccc80d5aea162a52925b3bb

name = fools-mate-game-set
domain_hex = 676f6c64656e2d626f6172643a67616d652d7365743a763000
field_hex = 000100043550d24039e0edf001
preimage_hex = 676f6c64656e2d626f6172643a67616d652d7365743a76300000010000000d000100043550d24039e0edf001
sha256 = 4070001b03556dcf41043adcf7a261c4b20aa7874a8033546520a48107fbc2f8
```

## Canonical manifest data model

A manifest is one top-level object. Nested values may be objects, arrays,
strings containing valid Unicode scalar values, booleans, or integers in
`0..=18,446,744,073,709,551,615` (`u64`).

The following reject: `null`, negative numbers, negative zero, floats, exponent
notation, arbitrary-precision integers, byte strings, dates, comments,
duplicate decoded keys, or trailing data.

Object keys are nonempty Unicode strings restricted after decoding to ASCII
bytes `0x20..0x7e`. Controls, DEL, and non-ASCII keys reject. Keys sort
lexicographically by decoded ASCII bytes; source or insertion order has no
authority.

Strings preserve their exact Unicode scalar sequence. No normalization occurs.
Invalid UTF-8 and unpaired UTF-16 surrogate escapes reject; a valid surrogate
pair decodes to its scalar value.

## Canonical serialization

- emit UTF-8 with no BOM;
- emit object keys in raw decoded ASCII-byte order and arrays in input order;
- emit `true` and `false` in lowercase;
- emit integers as shortest unsigned decimal, with no sign or leading zero
  except that zero is `0`;
- emit no insignificant whitespace;
- escape quote, backslash, backspace, tab, LF, form feed, and CR as `\"`, `\\`,
  `\b`, `\t`, `\n`, `\f`, and `\r`;
- escape every other scalar `U+0000..U+001F` as lowercase `\u00xx`;
- emit `U+007F` raw as its single UTF-8 byte `7f`;
- do not escape slash, printable ASCII, or non-ASCII scalar values; and
- emit exactly one LF after the top-level object and no other trailing byte.

Canonical validation parses under this data model, serializes again, and
requires byte equality. Thus otherwise valid JSON with whitespace, reordered
keys, unnecessary escapes, a BOM, escaped `U+007F`, or a missing final LF is
noncanonical and rejects.

## Resource limits

| Resource | Limit |
|---|---:|
| Input or serialized output bytes, including final LF | 1,048,576 |
| Nesting depth, counting the top object as 1 | 32 |
| Integer | `u64::MAX` |

Only objects and arrays increase depth; scalar children occupy their container's
depth. Parsing rejects before descending to depth 33. Input size is checked
before parsing. Serialization counts bytes while emitting and rejects rather
than returning output over the limit. No unchecked input length controls
allocation or recursion.

## Conformance fixtures

`conformance/identity-v0.json` contains hand-authored framing and SHA-256
vectors, including the two attributed NIST byte-oriented known answers.
`conformance/manifest-v0.json` contains lowercase-hex payloads for valid,
noncanonical, invalid, and generated boundary cases. Boundary recipes construct
large payloads in each implementation rather than committing them.

Expected bytes and digests are authored from this specification and checked
independently. Tests never rewrite them. Any authoring aid writes only to
ignored `artifacts/` for human comparison.

## Registry

`conformance/registry.toml` is the closed v0 index of shared conformance
payloads. The registry and every payload are at most 1,048,576 bytes. Each is
opened without following links and must be a direct regular non-symlink file.

The TOML has exactly the top-level keys `schema` and `suite`. `schema` is
exactly `golden-board.conformance-registry/v0`. Every `suite` row has exactly
the keys `id`, `path`, `specification`, `version`, `sha256`, `consumers`, and
`provenance`, with these rules:

- `id` and `path` are unique across rows;
- `id` and `specification` are nonempty lowercase ASCII identifiers containing
  only `a-z`, `0-9`, and interior `-` characters;
- `path` is byte-for-byte `conformance/<id>.json`, rejecting absolute, empty,
  dot, dot-dot, nested, backslash or platform-alias, NUL, registry-self, and
  alternate-spelling paths;
- `version` is exactly `v0`;
- `sha256` is exactly 64 lowercase hexadecimal characters;
- `consumers` is exactly `["python", "rust"]`; and
- `provenance` is exactly `hand-authored`.

Every row target exists and its SHA-256 matches. Row paths are exact-set equal
to all direct entries under `conformance/` other than `registry.toml`; every
such entry must itself be a regular non-symlink file. Missing, unregistered, or
unexpected entries, including symlinks and non-regular files, fail closed.

M0 registers only the identity and manifest suites. Empty future source, chess,
transport, curriculum, damage, or browser slots are forbidden.
