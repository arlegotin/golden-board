# Observation channels

Inputs are binary files. All multibyte integers below are unsigned and
big-endian. Preserve the observations byte-for-byte.

- `OBS_BITS`: a four-byte cell count followed by that many binary cells,
  packed most-significant-bit first. The payload occupies the count divided
  by eight, rounded up, bytes. Unused low bits in the last byte are zero.
- `OBS_MATRIX`: a **two-byte** positive side length followed by exactly
  side × side bytes in row-major order. Each cell byte is `0`, `1`, or `2`;
  `2` means an unknown/erased cell, not a known zero. These cells are not packed.
- `OBS_UNITS`: a four-byte entry count followed by that many entries. Each
  entry contains a four-byte positive unit ID, a two-byte payload length,
  and exactly that many payload bytes. Payload lengths are 1 through 255.
  Preserve the presented order. IDs must be unique. An absent unit is
  represented by an omitted entry, not an invented zero-filled payload.

None of these formats permits trailing bytes or a truncated field/payload.
Malformed framing does not authorize guessing missing bytes. Parsing storage
does not establish artifact geometry, integrity, completeness or content.

The tiny fixtures exercise storage only. In particular, the eight-cell
packing example is not a square carrier. Their values do not specify the
structure, parameters or expected result of any puzzle observation.
