# Practical chess adapter

The [lessons guide](../docs/guide/lessons.md#the-chess-boundary) states the preserved
practical profile. This contract records
the production interface and its qualification boundary; library conveniences
do not define adjudication policy. The reference is the selected
[FIDE 2023 Laws](https://handbook.fide.com/chapter/E012023), especially Articles
1–3, 5, 9.2.2–9.2.3 and 9.3.2. Excluded tournament procedures, automatic fivefold/
75-move endings and arbitrary deadness remain excluded.

## Coherent replay and observations

`golden_board.rules.Replay()` owns the pinned chess 1.11.2 Board and starts at
the orthodox initial position. No constructor combines arbitrary occupancy,
clock or repetition history. `fen` is diagnostic notation retaining immediate
en-passant targets, even when unusable; it is not artifact grammar. `moves` is
an immutable coordinate tuple; `legal_moves` is a sorted tuple of currently
admissible moves, empty after closure. `play(move)` validates strict lowercase
`a1b2` syntax with optional explicit `q`, `r`, `b` or `n`, then membership before
mutation. No null moves, whitespace repair or implicit queen promotion.

`side_to_move` is integer 0/1 for first/second side, never a chess color boolean.
`halfmove_clock` resets on every pawn move or capture, otherwise increments.
`repetition_key` is `(board occupancy, side, castling rights, legal EP square or
None)`. Only an actually legal EP capture includes the target; a pinned capture
does not. Diagnostic FEN, halfmove and fullmove counters are not repetition keys.
`repetition_count` counts the current key; the initial position occurs once.
`available_claims` is an immutable ordered tuple of eligible names `threefold`
(current count >=3), `fifty-move` (clock >=100), or both, while active.
Opportunities never automatically end the record. Intended-next-move claims are
not supported.

`events` is an immutable tuple of accepted actions: `('move', coordinate)`,
`('claim', actor, reason)`, `('resign', actor)` and `('agree', 0, 1)`.
`outcome` is None while active, otherwise an immutable `Outcome(score, reason)`.
Scores are 0 first side wins, 1 second side wins, 2 draw. `closed` reflects an
outcome. Rejected actions raise ValueError without changing any observation.

## Endings and declarations

After each legal move, evaluate checkmate, then stalemate, then only KK, KBK,
KNK in either color direction. Other material gives no general deadness verdict.
`board_ending(board)` shares this exact policy with strict source import; its
input is a valid coherent board. Mate awards the other side from the new turn;
stalemate/common-dead draw. No library `outcome`, broad insufficient-material
policy, automatic draw or prospective claim API is used.

`claim_draw(actor, reason)` requires the exact integer side to move, active state
and an eligible current reason; acceptance immediately closes as a draw.
`resign(actor)` accepts either exact integer side while active, including the
side not to move, awarding the other side the win. Ordinary resignation follows
the declared profile; general mating-possibility exceptions are not adjudicated.
`agree_draw(consenting_sides)` accepts a list or tuple of exactly two distinct
integer roles 0/1, in either order, only after at least two legal plies and while
active. Bool/float/string roles and implicit/missing consent are invalid. No
pending offers or clock/arbiter state are needed. Every closed replay rejects
all later moves, claims, resignations and agreements atomically.

A concluded source score is separate from replay events. A nonterminal source
win or draw never identifies why players stopped and never fabricates a
resignation, agreement or claim. Source games may continue through unclaimed
draw opportunities but cannot continue after a board ending.

## Occupancy, control and local diagrams

Geometric control is not filtered through legal moves: pinned pieces still
control, pawns attack diagonals, kings adjacent squares, and sliders stop at the
first occupant, including a defended friendly piece. Captures and en passant
remove all relevant occupants before king safety; promotion requires a choice.

For orthodox castling, evaluate origin under current occupancy, transit with
king moved from origin and rook unmoved, and destination after both king and
rook move. All squares between king and rook must be empty, including b1/b8 for
long castling. Only the king's origin/transit/destination need be safe; attacks
on the rook or b-file square alone do not prohibit castling. Rook capture,
king/rook movement and promoted replacement rooks do not restore lost rights.
Pinned dependency occupancy inspection and hand-derived legal witnesses qualify
this delegation; the tested square's own occupant does not affect attacks to it.

`local_controls(fen, origin)` returns geometric destination-square names for a
structurally valid diagnostic diagram. `local_deadness(fen)` returns
`common-dead` for exactly the three classes, otherwise `outside-profile`, never
a fabricated `not dead`. Neither establishes legal reachability, moves or
history for arbitrary FEN. Stateful teaching witnesses must include standard-start
replay and needed history; local diagrams are explicitly local.

## Source and qualification

Source qualification separates byte-bound source span identity, strict all-record import and
original-SAN independent qualification. Every selected source ply is compared
through pinned chess.js 1.4.0, production parsing and Replay. Native reference
FEN is retained beside an explicit immediate-EP projection from the resolved
double pawn move; this diagnostic projection is not the repetition key.
Strict SAN roundtrip, complete token consumption, score/board-ending consistency,
duplicates/conflicts, ranked prefix membership and canonical metadata independence
are checked separately. Complete generic game documents supply every playback
frame; the Player has no chess inference. Canonical move/score bytes are semantic
identities, not recipient grammar.

Hand-derived fixtures cover current claims versus prospective opportunities,
legal/pinned/absent EP identity, side/rights/history, clock resets, excluded
automatic endings, both castlings/colors, both-color promotions, geometric
control, declaration consent, exact closure and rejection. Coherent mate,
stalemate and source-prefix-plus-test-tail common-dead witnesses test the public
adapter. Material diagrams cover all three common classes and unsupported cases.
The [public source analysis](../docs/history/experiments.md#source-qualification)
and [retained exact source truth](../evidence/S04-rules/actual-source.json.gz)
record qualification and its limits. `./gb check focused source` repeats complete
original-SAN/state and literal playback checks. The current rules regression
includes the hand-derived boundaries above. Rule/source qualification alone does
not establish recipient understanding; [trials](../docs/guide/trials.md) separates
that historical evidence from native conformance and [status](../docs/status.md)
records actual current checks.
