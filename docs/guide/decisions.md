# Design decisions and lessons learned

The final structure follows observed constraints and explicit choices. This chapter
separates why a choice was made from what its tests actually establish.

## A generic document mechanism, rather than hidden chess

The carrier must teach its interpretation. Putting chess rules or generated
answers inside the reader would make the software explain missing content on the
artifact's behalf. The chosen record vocabulary therefore carries glyphs, frames,
partial updates, numeric tables, pages, accepted responses and links. A Player
knows only how to operate those records. Python computes chess while authoring;
the resulting observations and feedback are serialized.

This costs space: every-ply playback is explicit, in addition to move tuples.
It makes the display independently inspectable. Comparing only the final board
would miss an incorrect intermediate patch later canceled by another update.
The build audits each frame/action; [architecture](architecture.md) shows the
boundary and [format](format.md) describes the records.

## Manual micro-relay versus complete passive export

The first per-frame interpretation relay was stopped after eight actual returns. Most work
went into delivery and repeated source inspection, without a committed assessment.
The [record](../history/experiments.md#relay-and-passive-teaching) explicitly leaves the teaching
question open. Complete passive batches subsequently reduced delivery overhead
and supported three finite applications. The lesson is that an assessment interface
can obstruct investigation independently of the message's actual examples.

Passive routes remain in the message itself. They expose prompt, alternatives,
worked application, feedback and limitation without requiring a correct response
to unlock the explanation. They are not host-generated explanations.

## Replicas and correction were an abandoned scope, not an impossibility

Early separated copies and recovery instruction addressed a different contract.
Actual recipient integration eventually succeeded, but copies, reconciliation,
additional teaching and physical layout consumed substantial space and complexity.
The final contract uses clean observations and single-copy payload storage.
The [scope change](../history/experiments.md#clean-input-scope) preserved complete
teaching and every game while retiring damage guarantees.

The final CRC detects inconsistency; it never votes, fills missing bytes or uses
plausible chess to repair content. Zero reserve is checked rather than treated as
an extension point inside the final accepted candidate. Single-copy storage does
not prohibit repeated worked examples or sharing identical inert records.

## Capacity was measured at the complete-content boundary

Sharing anthology records saved 31,283 bytes, but the replicated carrier still
failed. Later fragmented clean sections exceeded1984 rows. Direct checked sections
eliminated unnecessary fragment/row costs while preserving identity, ordering,
lengths, checks and inventory. [Complete-fit evidence](../history/experiments.md#complete-fit)
records this transition. No game cut or larger artifact was needed.

Move tuples fit six origin bits, six destination bits and three promotion bits,
with one unused high bit in a u16. The [packing implementation](../../src/golden_board/move_packing.py)
and [independent masks audit](../../tools/audit-move-packing.mjs) compare all moves
and literal playback. This simple representation was teachable using the existing
numeric-record grammar. It did not introduce a compressed-code execution language.

Literal history segments share common prefixes and retain explicit boundaries.
The mechanism applies carried frames; it does not infer castling rights or count
repetitions from a picture. The distinction saves space while preserving the
occupancy/history contrasts essential to the chess profile.

## A failed action and its retained state need separate observations

The king-safety series exposed rivals that specialized scalar results did not
rule out. An attempted illegal move may leave the actual state unchanged while a
diagnostic picture shows why the hypothetical move failed. Treating either view
as the other yields plausible but wrong conclusions. Reusing a general attempt
operation, preserving literal operand fields, and showing both-side focal probes
supported six finite source-bound successor applications after those repairs.
This was not a controlled comparison of teaching efficacy. [The failed branch](../history/experiments.md#king-safety-and-retained-state) and
[successor analysis](../history/experiments.md#king-safety-and-retained-state) preserve that causal link.

## Primary view, whole record and event view are different roles

The c0038 integrated assessment had an incorrect primary-presentation interpretation
although many component facts were exact. A complete record, current requested
prefix and most recent event board cannot be substituted for one another. The
later presentation contract made those roles and complete extents explicit before
the affected successor assessment. Old failed answers were not rewritten.
The [prospective gate audit](../history/experiments.md#presentation-roles) records the
composed result and its assistance/condition limitations.

## Exact rules versus limited heuristics

Geometric control, legal movement, current draw-claim availability and common dead
classes are exact under the declared practical profile. Material1/3/3/5/9,
development, center and king-safety guidance are fallible conventions. A different
legal move is not automatically bad. A finite mating line does not prove a forced
win unless all relevant replies in the stated finite family are represented.

The course excludes a universal deadness solver, automatic fivefold/75-move law,
clocks and tournament procedures. These boundaries prevent convenience APIs from
becoming inaccurate general chess claims. See [lessons](lessons.md) and [spec/chess](../../spec/chess.md).

## Final appearance is fixed

The final panels, miniature glyphs, piece masks and lack of carried revision
labels define the canonical message. The current
PNG and packed square are checked against the exact reference identities in
the artifact manifest. Rendering choices are fixed properties of this message;
changing them creates a different candidate.

## Evidence cannot erase prior knowledge

Fresh context cannot erase a model's pretrained chess knowledge. Correct answers
must be separated from artifact-specific derivations, rival discrimination and
allowed-input reproducibility. Continued, cooperative and template-assisted work
are different conditions. Missing history limits claims even when code reruns.
The [trials chapter](trials.md) reports those limitations without converting finite
model demonstrations into human learning or universal comprehension.
