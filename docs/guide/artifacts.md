# The canonical artifacts

The [artifacts directory](../../artifacts/) contains the one final Golden Board
in three formats. The accepted packed message is the reference. Text and image
are mechanical views; none is an independently authored replacement.

| File | Bytes | Meaning |
|---|---:|---|
| [GOLDEN-BOARD.bin](../../artifacts/GOLDEN-BOARD.bin) | 524,288 | Raw row-major packed bits, no file header |
| [GOLDEN-BOARD.txt](../../artifacts/GOLDEN-BOARD.txt) | 4,194,305 | ASCII 0/1 for each cell, then LF |
| [GOLDEN-BOARD.png](../../artifacts/GOLDEN-BOARD.png) | 126,525 | 2048², grayscale, one bit per pixel, black=1 |

SHA-256 values are retained in [SHA256SUMS](../../artifacts/SHA256SUMS) and the
[machine-readable manifest](../../artifacts/manifest.json). The binary hash is:

```text
0116be5b721d72b8aed5f67265b290a506c818354f9f297b0618768db996b479
```

## Reference identity

The packed bitplane is the canonical reference. The TXT and PNG views reproduce
its cells exactly. Lengths, dimensions and hashes are recorded in the
[baseline](../release/baseline.json); [native verification](../release/verification.json)
checks the three representations and five document bodies. File modification
times do not determine authority.

## Exact relationship

For packed byte index `i`, bit `b` in 0…7 corresponds to serial index `8i+b`,
with mask `128 >> b`. Serial index `2048r+c` corresponds to pixel `(c,r)`.
ASCII `1` and a set packed bit mean black; PNG grayscale bit 0 also means black.
Thus PNG stored samples are the complement of the message bits. The LF is outside
the 4,194,304-cell message. There are no TXT row separators or BIN container bytes.

[verify_artifacts](../../src/golden_board/artifacts.py) checks all three frozen
file identities, independently groups the text, validates PNG chunk CRCs and
scanline boundaries, compares every pixel, then decodes and checks every document.
Its PNG reader intentionally supports this project's exact renderer rather than
arbitrary colour, filtered or interlaced PNG input. Carrier decoding has its own
strict checks. A valid PNG wrapper alone does not establish a valid message.

```sh
./gb verify
./gb verify --transforms
```

The second command verifies native extraction from every rotation/reflection and
polarity combination of the complete square. It is an established conformance
check, not a new recipient trial or a damaged-input recovery test.

## Reproduction and change control

`./gb reproduce --output build/reproduced` regenerates the packed square, TXT,
five bodies and PNG using the retained authoring sources, pinned dependencies and
qualified inputs, then compares them with the frozen canonical set. Output uses a
new directory; the canonical files are never overwritten. The current renderer
uses a deterministic one-bit PNG stream; byte identity is checked separately from
pixel identity so compression differences cannot silently become content changes.

A proposed future content change must be a separately identified artifact with
new applicable evidence. Keep this final set unchanged. A working build report
is a native engineering result; it does not rerun or extend the historical model
qualification. See [architecture](architecture.md), [build](build.md) and [trials](trials.md).
