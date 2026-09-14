# Observation channels

Inputs are binary files. Preserve them byte-for-byte.

- `OBS_BITS`: four-byte big-endian cell count followed by MSB-first packed
  binary cells; unused tail bits are zero.
- `OBS_MATRIX`: four-byte big-endian side followed by one byte per row-major
  cell; values are zero, one, or the owned erasure marker.
- `OBS_UNITS`: a canonical unit-observation stream whose record IDs and payload
  lengths are part of the checked framing.

Malformed framing is evidence of failure, not permission to guess missing
bytes.
