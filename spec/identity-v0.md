# Golden Board Identity v0

Status: frozen for M0

## 1. Scope and ownership

This specification owns developer identity framing and the canonical developer-manifest subset. It does not define chess, source-game, transport, profile, section, lesson, candidate, or artifact identities. SHA-256 identities are evaluator and developer evidence; blind recipients are not required to know these prefixes or this manifest syntax.

`spec/constants-v0.json` owns the registered M0 prefix and diagnostic byte values. Generated Python and Rust files are consumers.

## 2. Digest and rendering

The digest is SHA-256 over the exact preimage bytes. Text rendering is exactly 64 lowercase ASCII hexadecimal characters. Uppercase, shortened, prefixed, or whitespace-padded forms are noncanonical.

## 3. Domain prefixes

A registered prefix is nonempty printable ASCII bytes `0x20` through `0x7e`, followed by exactly one terminal zero byte. It contains no earlier zero byte and is at most 63 bytes including the terminator.

M0 registers only:

```text
GB-IDENTITY-TEST-A-v0\0
GB-IDENTITY-TEST-B-v0\0
GB-MANIFEST-v0\0
```

Prefixes are compared byte-for-byte. A later owner must register a new literal before first use; M0 does not reserve speculative semantic domains.

## 4. Scalar framing

For prefix `P` and payload bytes `X`:

```text
P || u32_be(len(X)) || X
```

`len(X)` is the exact byte length and must fit unsigned 32 bits.

## 5. Ordered-list framing

For prefix `P` and ordered byte items `X[0]` through `X[n-1]`:

```text
P
|| u16_be(n)
|| for i in 0..n: u32_be(len(X[i])) || X[i]
```

The item count must fit unsigned 16 bits and each item length must fit unsigned 32 bits. Item order is semantic. An empty payload, empty list, and one-item list containing an empty item are distinct.

## 6. Identity known answers

| Case | Lowercase SHA-256 |
|---|---|
| Test A scalar empty | `d884e5911a8a923feb85ae9c2b8066eb982234dfe6c6e7f34900988e6dc27a14` |
| Test A scalar `00` | `788f75a4aec50bc39d44796a9c335e36343c690363de84db24972be2bad5eda1` |
| Test B scalar `00` | `bd9a12341ac48f633c769140093675496d828dfa9ed21874b725acf3b8870c0e` |
| Test A empty list | `ce8a5a8230d526db58192616683de0a728d0f6f9198b3ee5ebe55f2fa767a2da` |
| Test A one empty item | `c475f1fbfda9eae9b0ad3e71603bdd6d45ebf545c866bb50f79170bc8895d72c` |
| Test A items `00`, `0102` | `ba34053b678a144a645eb524bca6f464ee1923fe5d12f5d32dc29ab80d8a218f` |
| Test A items `0102`, `00` | `67b715044915a1337625e8002b7745c620fbf187c68882cef25c163b949125e9` |

## 7. Canonical developer-manifest values

Allowed values are Unicode-scalar strings, booleans, integers from 0 through 18446744073709551615, arrays, and objects with ASCII keys. Objects may be empty; keys may contain decoded ASCII control, quote, or backslash values.

Host-language value encoders admit only their exact closed-model value types. User-defined value subclasses reject as `manifest.unsupported_type` before any overridable behavior is invoked; a subclass used as an object key rejects as `manifest.invalid_key`.

Forbidden values and forms are `null`, floats, fractions, exponent notation, negative zero, negative integers, integers above the unsigned-64 maximum, duplicate keys, invalid UTF-8, a UTF-8 byte-order mark, isolated UTF-16 surrogate escapes, comments, and trailing data.

M0 limits are:

| Limit | Inclusive maximum |
|---|---:|
| Input bytes including final LF | 16,777,216 |
| Nested array/object levels | 64 |
| Members in one object | 65,535 |
| Items in one array | 65,535 |
| Decoded scalar/container value nodes | 1,000,000 |
| UTF-8 bytes in one decoded string | 16,777,216 |

Each limit is checked before the corresponding recursion, collection growth, or output growth.

## 8. Canonical ordering and string bytes

Object keys are sorted recursively by decoded ASCII bytes.

Strings are enclosed in ASCII quotes. Quote emits `\"`; reverse solidus emits `\\`; backspace, tab, LF, form feed, and carriage return emit `\b`, `\t`, `\n`, `\f`, and `\r`. Other controls U+0000 through U+001F emit lowercase `\u00xx`. Slash is never escaped. Every other Unicode scalar emits directly as UTF-8. No Unicode normalization occurs. Surrogate code points reject.

Canonical structural output has no insignificant whitespace, no leading or trailing spaces, no structural newline, and exactly one final LF. That LF participates in a manifest identity payload.

## 9. Strict acceptance and diagnostics

A strict reader caps input, validates UTF-8 and BOM absence, parses while preserving object pairs and number spelling, rejects syntax or trailing bytes, applies semantic validation in the fixed precedence below, emits canonical bytes, and accepts only when those bytes equal the original input.

```text
manifest.limit
manifest.utf8
manifest.syntax
manifest.trailing_data
manifest.duplicate_key
manifest.unsupported_type
manifest.integer_range
manifest.invalid_key
manifest.invalid_unicode
manifest.noncanonical
```

Exception wording is not normative. Python and Rust return the same primary diagnostic ID for every registered rejection.

## 10. Manifest identity known answer

For the canonical empty-object document:

```text
canonical bytes = 7b7d0a
domain prefix = 47422d4d414e49464553542d763000
scalar preimage = 47422d4d414e49464553542d763000000000037b7d0a
SHA-256 = 836b1e2073681781d86862b6135f26e66db2c15cc73080d01815930aefbc4a4a
```

The manifest hash operation first validates the exact input as canonical and then hashes the original validated bytes under `GB-MANIFEST-v0\0`. It never hashes an unvalidated or re-emitted substitute.
