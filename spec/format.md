# Current format reference

The normative current envelope, inventory, document header, CRC conventions,
miniature and pruning rules are [self-contained-format.md](self-contained-format.md).
The complete five-record field reference and action behavior are in
[the payload guide](../docs/guide/format.md), with executable strict readers in
[document.py](../src/golden_board/document.py) and
[player.mjs](../mechanism/player.mjs).

The S02 vector retains an old document header only as an explicit rejection and
pinned-input conversion fixture. It is not a supported alternate recipient
format. Obsolete replicated transports and recovery profiles are explained in [the development history](../docs/guide/origins.md).
