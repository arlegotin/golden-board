# Revised observation decoder bridge

This internal bounded process protocol carries observations to the independent
profile8 Rust receiver. It does not admit a candidate or award a gate. The
historical bridge and its channel numbering remain unchanged.

Each request is one channel byte (1=OBS_BITS,2=OBS_MATRIX,3=OBS_UNITS), a
big-endian u32 byte count, then exactly that many observation bytes. Maximum
observation bytes are4194306. Zero bytes are a valid host frame containing an
invalid observation. An unknown channel, excessive declared length, truncated
header or truncated body is a fatal host framing error; do not drain oversized
input, invent a decoder result or continue a desynchronized stream. EOF is
successful only between requests. No case ID, clean source or expected result
is part of the protocol.

Each response has two fields, each framed by its own big-endian u32 byte count:
the canonical decoder-result/v2 and then the canonical observation-resources/v2
sidecar. Each field must contain1..1048576 bytes. Flush after the whole response.
One process may serve successive observations; semantic state and counters
restart each time, while optional bounded computation caches may persist.

The client rejects malformed or noncanonical response fields, stale source
owners, mismatched channel/observation/result digests, or differing result and
sidecar resource counters. After a response or transfer error, terminate that
client’s process and never reuse its stream. Validate request types and bounds
before writing. Pipes are nonblocking and every read/write loop observes its
finite deadline; selecting a writable pipe does not authorize an unbounded
blocking whole-frame write. Process-close deadlines are also finite.
Result admission checks the closed decoder-result/v2 field set, integer and
Boolean types, digest shapes, sorted unique section/hypothesis rows, current
profile domains and state/availability consistency before returning the pair.
This structural validation does not infer the truth of retained digests.

These checks bind transport and resource identity. Full semantic result
admission still requires exact independent result comparison and the damage
owner's complete case coverage; a valid response frame is no passing evidence.
