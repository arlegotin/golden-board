# Exact authoring and scoring predicates

Normative scope: the [practical adapter](chess.md), current carried content and [maintenance contract](../docs/roadmap.md). This is a finite
catalog of developer operations, not an embedded language. English names,
coordinates and formulas here do not enter the nonlinguistic message. Cases name
one operation, its explicit inputs/domain and result encoding, or enumerate a
complete finite accepted set. No arbitrary expressions/callbacks at runtime.

**Implementation boundary:** G1–G4 are evaluated by the generic record/Player
mechanism. C1–C7 use the qualified legal replay, source import and literal playback
checks. R1–R7 and F1–F2 define the exact authoring relations consumed by the current
foundation/practical/advanced course and predicate modules. Actual coverage is
bound by [coverage.toml](../content/coverage.toml), with146 obligations carried in
the final documents. This catalogue is not a promise of a public API for every
possible diagram or arbitrary proof. Recovery-only G5 is retired. The Player
receives explicit frames/updates/accepted responses; it evaluates no chess
predicate. Automated assertions, historical interpretation and release packaging
remain separate kinds of evidence.

## Domains and result discipline

Use artifact cell/role identities through an explicit binding; developer square
names are diagnostic. A board-local diagram has valid structure but no asserted
reachability/history. Stateful legal choices, claims, endings and sequence effects
require one standard-start legal Replay witness, including accepted declarations.
Reject malformed/out-of-domain inputs; do not manufacture a false/empty answer.
Outside-profile deadness is a separate result, not false deadness.

An expected set is complete, sorted/unique for serialization; order is not
semantics. A sequence retains order and repetitions. An empty committed response
can be correct; absence of submission is not an answer. An expected alternative
list enumerates every accepted response; it is not a partial sample. Case labels
and familiar terminology alone cannot establish message grounding.

## G1 — finite_response

Inputs: response shape, finite exposed region IDs, explicit accepted alternatives,
and a committed response. Single/set/sequence shape and domain must validate.
Accept iff the complete normalized response equals one listed alternative;
sets normalize by ascending ID, sequences never reorder. Selection alone is
uncommitted; empty commit is distinct. Missing/invalid submission gets no score.
The exact rule behind the accepted list must be recomputed during authoring;
listing an author-preferred move cannot prove that another legal move is bad.

## G2 — finite_data

For an explicit finite list/matrix, return length/count of a named value,
equality, indexed element, row/column or specified order relation. Matrix index
is row*column_count+column, both zero-based developer integers. Count/order/value/
address roles are distinct inputs. Result depends only on the stated finite data,
not the shape, color or answer-dependent highlighting of its rendering.

## G3 — cell_updates

Given a complete initial frame and finite steps of unique in-range cell/value
pairs, the next frame copies the previous frame then replaces exactly the named
cells. Unmentioned cells persist. Return any requested intermediate frame or
changed/unchanged set. Reject duplicate/out-of-range indices, unknown tokens,
missing referenced data or ambiguous encoding. An early wrong frame is a failure
even if later updates cancel it. Generic Player.packet provides actual frames.

## G4 — player_actions

Given a valid carried document, exposed entry and finite action sequence, compare
every Player state/packet: node, step, selection, committed response and feedback
relation. Follow the existing select/commit/reset/link/seek contract; invalid
actions preserve state. Selection changes a buffer; commit evaluates the carried
finite relation and traverses its feedback link; reset clears only uncommitted
selection. Retry starts another logged attempt. No hidden automatic chess reply.
This operation includes record boundary/ordinal navigation and finite buffer
bounds, not an invented unlimited selection sequence.

## G5 — retired recovery availability

Superseded by the [clean-input scope](../docs/history/experiments.md#clean-input-scope).
No copy vote, damaged reconstruction, competing copies or recovery-dependency
lesson is required. Historical definition/evidence remain in the pre-clean snapshot.
Current clean transport validates complete framing/checks/inventory atomically;
no unavailable bytes are restored or guessed. This is an engineering boundary,
not an additional teaching stratum.

## C1 — replay_state

Return the specified field of the coherent Replay: occupancy, side, rights,
immediate diagnostic EP, halfmove clock, current repetition key/count, accepted
events, active/closed state or immutable outcome. Initial count is one. The
standard arrangement and first side are fixed; roles retain their artifact
mapping across orientations. Never splice occupancy with unrelated history.

## C2 — legal_choice_and_effect

For an active Replay return all legal coordinate moves, or those with a specified
origin, with explicit promotion choice. A requested candidate is admissible iff
in that set. After acceptance compare its entire resulting occupancy/side/rights/
EP/clock/history/outcome against a fresh replay of the same legal prefix plus
move. Reject encoding/legality/closed-state errors atomically. Ordinary movement,
friendly occupancy, knight jumping, double pawn moves, castling, en passant and
promotion use this qualified interface. A destination alone does not identify a
promotion. Do not describe geometric control as this set.

## C3 — geometric_control_and_check

For a local piece return every geometrically controlled square, including a
friendly occupant at a ray endpoint; stop sliders at the first occupant. Pawns
control diagonals, kings adjacent cells, knights jump. Pins do not filter control.
A side is in check iff its king square is controlled by the other side in the
actual occupancy. For a proposed legal king move use C2's fully updated occupancy,
including captured-piece removal; a pre-move control overlay is insufficient.
Complete evasions are all C2 legal moves from a checked Replay, not only king moves.

## C4 — selected_board_ending

After a legal move, checkmate iff checked with no legal move; otherwise stalemate
iff not checked with no legal move; otherwise common-dead only for KK/KBK/KNK in
either color direction; otherwise active. Other material has no general deadness
verdict. Closure score/order and later-action rejection follow spec/chess.md.
Mate/stalemate require coherent witnesses; local common-material classification
establishes no reachable history. The two are distinct evidence types.

## C5 — current_history_claim

Key = occupancy + side + rights + EP target only when a legal EP capture exists.
Count every occurrence in the legal replay, initial one included. Threefold is
current count>=3; fifty-move is current halfmove clock>=100. Pawn moves and all
captures reset that clock. Eligible is not closed; only an explicit valid current
side claim closes. One move before the threshold is not a current claim. Automatic
fivefold/75-move and intended-move paperwork are excluded; no library shortcut.

## C6 — declaration_and_record_score

Resignation by either active side awards the other side the win. Agreement
requires explicit distinct consents after both sides have moved, while active.
Claims require C5. Compare accepted/rejected event and all observations before/
after. A concluded record's score is exactly first win/second win/draw; on an
active final board its cause is unspecified. Reject attempts to infer mate,
resignation/agreement or a claim solely from that score.

## C7 — complete_game_reading

Decode the actual game table into every origin/destination/explicit promotion and
minimal score. From standard start compare each resulting occupancy/turn and
applicable result with carried generic updates and Player frames. Every selected
ordinal/ply and score must be reachable through carried navigation. Canonical
content order follows selection, not source names or historical chronology.
Complete carried move/playback length and references must validate; a current replay prefix does not claim to be the complete record. Invalid input is rejected without guessing. Held-out records are newly authored canonical data, not remembered
anthology fragments; actual A-recovered bytes are the authoritative B input.

## R1 — occupied_attack_and_defense

For each geometric control pair (piece square,target square), keep target if
occupied. Enemy occupancy means attacked, friendly occupancy means defended.
Return pairs, not merely a highlight count. This includes pinned controllers;
it says neither that a capture is legal nor that an exchange is profitable.
Boundary example: a pinned knight can defend a friendly pawn yet have no legal
move; an empty controlled cell is controlled, not an attacked occupied piece.

## R2 — absolute_line_pin

Return triples (own king,own nonking blocker,enemy slider). All three lie on one
rank/file/diagonal, blocker lies strictly between king and slider and is the sole
intervening occupant. Slider is queen, rook on rank/file, or bishop on diagonal.
This defines an absolute line pin, not relative pin/skewer or total immobility:
a pinned rook/bishop/pawn can sometimes move along the pin line. Counterexamples:
another blocker between, wrong slider direction, or valuable queen behind instead
of king. Actual legal moves still use C2; pinned pieces still control by C3.

## R3 — geometric_fork

For a specified piece, R1's enemy occupied target set has at least two distinct
members; return the complete target set/pairs. King may be a target (check).
This is the exact geometric double-attack relation taught here. It does not
claim legal captures, material gain or a favorable exchange. Contrast a pinned
controller or defended targets; if legal capture choices are requested, score C2
separately. Two attackers on one enemy are not this one-piece fork predicate.

## R4 — discovered_slider_relation

Inputs: an active coherent Replay and a legal move. In the resulting position,
return (stationary friendly slider,unchanged enemy target) newly controlled along
a ray that, before the move, was blocked by the moving friendly piece's origin.
Slider and target must retain their square/type/side; origin lies strictly between
them before movement. All other intervening cells are empty after movement.
Target equal to enemy king is discovered check. A direct attack by the moved
piece, moving the slider itself, or a newly introduced target is not this relation.
Self-checking candidate is rejected by C2, not accepted as a tactical success.
This selected geometric definition makes no profitability/forced-win claim.

## R5 — pawn_and_file_relations

For side first, forward means increasing orthodox rank; for side second,
decreasing rank. A pawn is passed iff no opposing pawn lies on its own or either
adjacent file at a strictly forward rank. Edge files have one neighbor. A same-rank
enemy pawn is not strictly ahead. Own pawns/nonpawns do not affect this predicate;
it is not a guarantee of safe passage/promotion. Match positive/negative pairs by
changing one relevant opposing pawn, including edge/adjacent/same-rank cases.

A file is open iff it has no pawn of either side; semi-open for side S iff no
S pawn and at least one opposite pawn exists on it. Other pieces do not alter
these labels. Thus open is not also semi-open in this declared convention.
Use F1 for a limited scheduled promotion race and F2 only for a proved forced
game conclusion; kings, captures and timing cannot be silently ignored.

## R6 — material_inventory_and_convention

Count pieces by side/type in the actual position. The taught rough scale assigns
P=1,N=3,B=3,R=5,Q=9; king has no exchange value. Arithmetic totals/differences
are exact for this convention, not advantage, soundness or a win probability.
Promotion/capture updates inventory immediately. A higher total can coexist with
mate/loss; the latter is determined by C4/accepted events, never this sum.

## R7 — observed_guidance_and_limits

Strategy questions name exact observable facts or a complete finite accepted set:
original minor-piece departure from its initial square in the shown history;
occupancy/control of the four central cells; geometric control or legal-mobility
sets with mode/side explicit; open lines R5; pawn relations R5; checks/legal king
routes C2/C3; and before/after changes in those facts. A return home does not erase
the departure event. A mobility comparison uses coherent states with the same
side to move and states exactly what was counted. A changed count alone proves
neither causation nor positional merit. Original identity follows the legal move
history, not the location of a later promoted replacement.

Teach development/center/king safety/activity/lines/restriction/pawn ideas as
fallible guidance with contrasts. Score fact recognition, recognition that the
guidance does not determine the best move, or explicitly shown finite alternatives.
Do not score a different legal move wrong because an author likes another one.

## F1 — shown_path_and_first_promotion

An explicit finite move/event schedule starts from a coherent legal prefix;
validate every step/event and record every intermediate. A first-promotion query
returns the earliest promotion event (side,ply,choice) or none within the shown
schedule, with immediate resulting occupancy. A promotion leaf can be active.
A scheduled pawn-only race visibly excludes king moves and other alternatives;
it is a limited event prediction, never proof of a forced win or safe promotion.
Counterfactual schedule/timing/capture/king-interference examples expose the limit.

## F2 — finite_forced_game_witness

A finite acyclic authored tree starts from one coherent legal Replay prefix.
For a claimed winning side, each of its decision nodes supplies at least one
explicit legal chosen continuation; each opponent reply node supplies every
legal move plus every currently eligible draw claim. Validate child effects by
Replay and compare move/claim sets exactly at opponent nodes. Optional opponent
resignation awards the asserted winner; agreement cannot be compelled, so neither
adds a stronger defense than the enumerated continuations. A full witness can
explicitly record that omitted resignation is dominated by the same winning score.

Every leaf must be actually closed with the asserted winning score under C4–C6.
Every opponent child must have such a finite subtree; choose only supported
attacker continuations. Missing reply, active leaf, invented history, assumed
general deadness or unsupported leaf makes the proof incomplete. Interior KQK/
KRK positions outside common-dead classes are allowed; their mating witness
needs no universal deadness solver. A failed proof is not a fabricated losing
verdict. No minimax evaluation, free reply generation or executable tree logic
is supplied to the generic Player: every lesson reply/frame/feedback is carried.

Both queen and rook elementary mating routes require legal worked sequences.
At least one scored mating family has the full relevant reply witness; showing
only a cooperative path supports F1, not the forced F2 assertion. Historical assessment results are summarized in
[the development findings](../docs/history/experiments.md); the public source tree
is not a complete original evaluation dataset.

## Development boundary examples

These are definition witnesses, not final hidden assessment cases or claims of
serialized teaching by themselves. Actual consumed relations and their complete
carried bindings are checked by the current course builders and coverage inventory.

* Local diagram `7k/6b1/8/1r6/4q3/2N5/8/K7 w - - 0 1`: R2 has
  (a1,c3,g7). R3's knight target set is {b5,e4}; the knight's pin does not erase
  geometric control. Adding another friendly blocker on b2 removes that R2
  triple. Do not infer arbitrary-diagram reachability or stateful legal history.
* Local diagram `7k/8/8/2pP4/8/8/8/K7 w - - 0 1`: d5 satisfies the declared
  passed-pawn predicate; c5 is same-rank, not ahead. Moving that opposing pawn to
  c6 makes d5 not passed. Open files are {a,b,e,f,g,h}; semi-open for first is
  {c}, for second {d}. A nonpawn on a file does not change the pawn-file labels.
* Coherent prefix `b2b3 d7d5 c1b2 e7e6 b1c3 g8f6`, then `c3b5`: R4 returns
  (b2,f6). The bishop is stationary, the knight vacates its ray and the target
  knight stays f6. The moving knight's direct attacks are a different relation.
* The source49 b1 promotion followed by capture and eventual draw demonstrates
  why a first-promotion event is not a forced-win leaf. F2 accepts only an actual
  complete finite terminal witness; this observation alone proves no general
  draw, winning or mating rule.
