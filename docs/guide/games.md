# The games

The anthology contains 64 complete games, played between 1909 and 2021. Together
they carry 6,890 plies: one ply is one player's move. Playback includes each game's
initial position and every position after a move, for 6,954 states in total.
There are 39 White wins, 16 Black wins and 9 draws.

The selection covers attacks and sacrifices, quiet restriction, defense and
counterattack, resourceful draws, pawn play, promotion and several kinds of ending.
Those are played examples. The collection makes no claim that a move was optimal
or that every defense was forced.

The [game index](game-index.md) gives names, dates and the matching artifact ordinal.
That information belongs to this human guide. The artifact carries
the moves, minimal scores and playback, without names, dates, events, openings,
annotations or critical-move markers.

## What each record contains

A game starts from the ordinary initial position. Every move records an origin
square, destination square and promotion choice. In the anthology, those fields
occupy 6, 6 and 3 bits inside a two-byte table value; the remaining high bit is
zero. The supplied schema establishes the field widths. The player sees an inert
number, rather than a chess instruction.

The game also carries a minimal first-side win, second-side win or draw score.
A score does not identify why play ended. A recorded win on an active board does
not establish checkmate, resignation or a player's intention.

Playback is separate data: an initial frame and the cell updates after each ply.
The generic player applies those updates. It neither calculates legal moves nor
recreates missing positions from the move list. Keeping both records lets the
recipient inspect the moves while seeing the carried sequence.

## Which order is used

The source PGN keeps the editorial selection order. All 64 games remain included.
For the artifact, complete game content is sorted into a deterministic order.
Artifact Game 1 therefore need not be the first record in the source file.

The index follows the artifact's order and includes the source number. For headless playback, open document 2 and its corresponding root. Entry IDs run from 324 to 387. Every entry
contains the whole game; the longest has 271 plies.

## Checking faithfulness

The original source notation was read independently through Python and chess.js.
All moves and every-ply states were compared, with the project's explicit treatment
of immediately recorded en-passant targets. Current packed move fields and carried
playback were then checked against the qualified source. A familiar game or a
plausible final board cannot substitute for those comparisons.

The source remains one maintained [PGN file](../../inputs/anthology.pgn). This guide's
index contains metadata, not a second copy of the movetext.

Next: [inspect the documents](build.md#inspect-and-operate-documents-offline).

References: [source qualification](../history/experiments.md#source-qualification),
[selection and breadth](../history/experiments.md#source-qualification),
[packed moves](../../src/golden_board/move_packing.py).


## Source comparison boundary

All64 supplied games passed original-SAN legal/state comparison. Every game stops
on an active board; its score does not establish resignation, agreement or mate.
The reference comparison explicitly projects392 immediately recorded en-passant
FEN targets where chess.js omits some unusable targets. This convention preserves
source-state accounting; repetition still considers en passant only when a legal
capture exists. [rules.py](../../src/golden_board/rules.py) owns that distinction.

`./gb check focused source` repeats original-SAN qualification and literal
playback without modifying PGN or the accepted qualified input. Canonical order
is a byte-content sort after membership validation; editorial ranking controls
retention but is not carried as descriptive metadata. All64 games remain.
