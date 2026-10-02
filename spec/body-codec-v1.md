# Bounded body codec v1 — development contract

This codec changes storage of content-body sections, not content-v0 or any
historical profile. It is development work until a new carrier owner admits
its section version, carried decoder/composition and complete measured costs.
Existing section version 0 remains raw. New content-body section version 1
contains the format below; other section kinds do not acquire this version.
Dispatch uses the checked section kind/version, never payload sniffing.

Both encoded and decoded payloads are bounded by 16,384 bytes. A version-1
payload starts with codec byte 3 and a big-endian u16 decoded length. Empty
decoded bytes are admissible to the codec, though not thereby to body/content
validation. After this three-byte header, groups consist of one flag byte
followed by up to eight tokens, in flag-bit order 7 through 0:

- A zero bit denotes one literal byte.
- A one bit denotes a big-endian u16. Its upper 12 bits plus one give backward
  distance 1..4096; its lower four bits plus three give length 3..18. Distance
  cannot exceed bytes already decoded. Copy one byte at a time from that
  distance behind the growing output, so overlap is allowed.

Before consuming a token, check its complete encoded length and resulting
decoded bound. Stop exactly at the declared output length. All unused low
flag bits in the final group must be zero, and no trailing bytes are allowed.
For zero decoded length the header is the complete encoding. Unknown codec,
truncation, invalid reference, output overrun, nonzero unused flag bits,
trailing input or either size bound rejects atomically, exposing no prefix.

The production encoder examines at most the prior 4096 positions, chooses
the longest match up to 18 bytes, and resolves equal lengths to the smallest
distance. A match of at least three bytes emits a copy; otherwise emit a
literal. Matching may overlap by comparing against the complete source.
Each complete group has eight tokens; unused final flag bits are zero.
For each source body, choose version 1 only when its complete encoded payload
is strictly shorter than the raw bytes. Otherwise return unchanged version 0.
There is no compression estimate or assumed ratio for future material.
An encoder's intermediate candidate is bounded by
`3 + 16384 + ceil(16384/8) = 18435` bytes; an oversized candidate is never
selected or admitted as a version-1 section. Direct diagnostic encoding may
return that candidate so incompressible input can be tested explicitly.

Decoder admission accepts every well-formed tokenization, without implicit
recompression. Deterministic generation uses the encoder rule above. Python
and Rust independently implement that rule; neither consumes the other's
generated payload. Public encoding/decoding functions reject invalid versions
and non-byte inputs rather than coercing them.

Validate the existing section envelope/check before decoding. Then decode
atomically and apply whole content-frame boundaries, tier ordering/lengths,
ROOT and all content-v0 typing/reference/control checks to the exact recovered
bytes. A codec success is not a section, tier, artifact or learner success.
Inventory and section checks bind encoded bytes; content-tier totals and
logical reserve calculations bind decoded bytes. Repeated/group conflicts
remain defined over complete checked blocks, not normalized codec output.

The 105,277-byte future allowance remains raw, and reserve derives from the
unchanged logical slice requirement. Required teaching keeps fivefold
protection. Every decoder node, table, construction example and route byte
must count in all four sector copies and their headroom. The unchanged
2048-square / 512 KiB ceiling is not enlarged by this owner.

The generic recipe implementation must have the same finite grammar and
failure behavior, with explicitly carried initialization, iteration and
finalization. A host codec alone or an undocumented token-step loop cannot
establish artifact self-description. Large fixed interfaces do not excuse
omitting their example-construction costs. Candidate admission still requires
this carried bridge, independent regeneration, actual fit and fresh gates.
