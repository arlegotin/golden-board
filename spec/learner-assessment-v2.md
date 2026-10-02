# Revised learner assessment and bundle v2

This owner binds the twelve existing final questions to the unchanged 65-page
required stream. It does not define new questions, scoring thresholds, human
evidence, or a release. Historical authoring/owner-v1 files remain unchanged.

## Inputs and scope

`studies/m2/learner-assessment-v2.toml` is authored question intent, not an
evaluation result. It contains no correct regions, legality judgments, result
positions, masks, or repetition counts. Each implementation derives those
values with its own public chess implementation. Neither consumes the other's
owner JSON or authored page output. The two implementations share authored
question intent, rules and templates; this is implementation independence, not
independent question authorship.

The pure assessment input is the actual recovered required stream and raw
intent, chess-fixture and game-set source bytes. The bundle wrapper takes the
actual `RecoveryProvenanceV2` value, obtains its required stream, and copies the
locked source templates. It must not manufacture recovery or substitute a
source-equivalent stream. Full typed content validation and re-encoding must
agree with the input. The required bytes are exactly 42432, SHA-256
`141168a051b44f978667f7c562070300d79368ace3fee47f5d19082de7642c17`, ROOT 588.
The fixture is canonical manifest JSON, at most 2097152 bytes, SHA-256
`9a63aa74a32761bf1f8919278e895f532e4d4f305a30f74ddd1d0c4acec6a639`.
The game set is at most 327677 bytes, SHA-256
`e883055cd0417061cf04d596cbca75d039948a987180d26a80bd6d6888f4764e`.
Its exactly 64 records have u16 ply count 1..4096, two bytes per move, score
0..2, strict increasing byte order, total plies <=65535, and exact EOF. Replay
and validate the complete ordinal-zero record before selecting any prefix.

## Intent grammar

The TOML input is UTF-8, at most 16384 bytes, with only `schema` and `questions`.
Schema is `golden-board.m2-learner-assessment-source/v2`; questions are twelve
tables in page ordinal order 53..64. Every table has exactly:
`id,family,page_ordinal,kind,prefix_kind,prefix_value,prefix_plies,suffix,
option_moves,reverse`. IDs/families and their order are the exact table below.
All strings are ASCII, at most 256 bytes; every integer is nonnegative and
typed (booleans are not integers). `reverse` is a boolean. `option_moves` has
0..2 UCI coordinates. Coordinates are `[a-h][1-8][a-h][1-8]` with optional
`q,r,b,n`, encoded using the existing Move16 grammar. A UCI sequence has at
most 64 plies. `prefix_kind` is `literal`, `fixture`, or `game`:

* literal: prefix_value is a UCI sequence, prefix_plies=0;
* fixture: prefix_value selects exactly one named source case's
  `input.moves_hex`, prefix_plies=0;
* game: prefix_value is empty, prefix_plies selects ordinal-zero game plies.

Append the UCI `suffix`, then replay the entire prefix legally. Total prefix
is at most 64 plies. No fixture expected answer is a truth oracle.

|Ordinal|ID|Family|Kind|
|---|---|---|---|
|53|final-grid|grid|occupancy|
|54|final-turn|turn|transition|
|55|final-sliding|sliding|transition|
|56|final-knight|knight|transition|
|57|final-capture|capture|transition|
|58|final-control|attack|control|
|59|final-castling|castling|transition|
|60|final-en-passant|en_passant|transition|
|61|final-self-check|self_check|transition|
|62|final-promotion|promotion|transition|
|63|final-history|history|history|
|64|final-game|game|record_transition|

Transitions have exactly two distinct option moves and reverse=false.
Record transition has one alternate move and a game prefix: pair the next
canonical move with the alternate, then reverse when requested. Both must be
legal, have equal final three-byte Position footers, and differ. The correct
record region is exact Move16 equality to the canonical move, not mere
legality. Other kinds have zero option moves. Occupancy asks occupied squares;
control asks side-zero control, compared with legal destination squares;
history asks threefold claim availability, not automatic termination.

## Derived pictures and admission

Use the public chess oracle for every true position, control square, legal
destination, transition, repetition count and claim. Position board diagrams
are 10x8: ranks 7 down to 0, eight 255 separators, then bytes 64..66 and five
255 separators. Masks are 8x8 in that rank order. Two choice matrices are
placed side by side with one 255 column; regions 1 and 2 exactly cover them.

Transition panels are the before board then the two after/proposed boards.
Illegal proposed diagrams are explicitly hypothetical: clear origin, set
destination to mover, toggle side, clear EP; pawn EP removes the bypassed
pawn when nominal target and diagonal request match; straight double pawn
requests set nominal middle+1; promotion replaces pawn with requested piece.
King requests clear own rights and requested castling moves the corresponding
rook. Moving a home rook or capturing it on its home square removes its bit.
These diagram operations do not legalize a rejected move.

Occupancy panels are 1x1 badge253, before board, then occupied and inverse
masks. Control panels are badge254, 1x6 values1..6, before board, then control
and legal-destination masks; require the masks differ. History panels are
badge247, chronological storyboard, final board, then scalar choices 0 and1.
Storyboard includes every prefix including initial/final, three boards per
row, width26, height `ceil(frame_count/3)*12-1`; each frame has ply number at
`(12*(i/3),9*(i%3))` and its board one row below. Reverse only the choices
where intent requests it. Record panels prepend badge245 and 2x3 cells
`[move_hi,move_lo,255,origin,destination,promotion]` before transition panels.

Pack whole panels greedily with two columns between panels and maximum row
width36. If the next panel exceeds36, start a new row two rows below the
previous row's tallest panel. Initialize all gaps to255; translate final
choice regions by its panel origin. Compare the entire matrix and exact
regions (including zero labels and flags1) with actual recovered records.

Parse all65 lesson nodes in record order and require roles/modes/counts:
46 role3/mode3 teach, seven role5/mode1 practice, twelve terminal role5/mode2
heldout nodes. All response shapes1, flags0, max selections1, local budget16;
ROOT global budget4160. For finals require predicate/trace0, no cases,
default feedback class1 displaying their matrix with predicate0; next node
is the next final node or0 at the end. These checks plus exact stream identity
bind the whole lesson; independent final derivation additionally checks its
semantic assessment. No answer is added to recipient content.

## Closed owner output

Canonical manifest-v0 JSON with LF, at most1MiB. Exactly root keys:
`schema,assessment_source_sha256,content_sha256,content_bytes,root_id,pages,
local_budget,global_budget`. Schema `golden-board.m2-lesson-owner/v2`; budgets
and root as above; assessment source hash covers the exact intent bytes.
`pages` contains only the twelve final rows, each exactly
`id,family,phase,node_id,surface_matrix_id,region_set_id,correct,evidence`.
Phase is `heldout`; correct is a nonempty increasing array of region IDs.

Evidence is a closed tagged union. All kinds have `kind,prefix_hex,before_hex`.

* occupancy adds `mask` (64 integer bits).
* control adds `side` (0), `control_mask,legal_destination_mask` (64 bits each).
* transition adds `options`: region-order rows exactly
  `region_id,move_hex,legal,after_hex` when legal, otherwise
  `region_id,move_hex,legal,rejection,proposed_hex`; rejection is public u16.
* record_transition adds the same options plus
  `game_path,game_set_sha256,game_sha256,game_ordinal,ply_index,
  record_move_hex,record_diagram`; path `reports/game-set-v0.bin`, ordinal0,
  diagram exactly `wire_bytes,origin,destination,promotion`.
* history adds `occurrences,threefold_available,positions_hex`; the last is
  every chronological Position, including initial and final.

Validation regenerates the assessment from source and recovered bytes and
requires exact canonical bytes, rather than trusting claimed correct IDs.

## Exact bundle files

The nine recipient paths and two owner paths are gate8-policy-v2's learner
contract. Copy instructions from
`studies/m2/templates/learner/instructions-v1.txt` byte-for-byte (the former
package_learner_v1 literal, unchanged), and owner instructions from
`studies/m2/templates/learner/owner-instructions-v2.txt`. Copy four existing
`tools/m2/learner_web/{index.html,layout.js,ui.js,viewer.js}` and two existing
`tools/m2/{learner_runner.py,learner_runner_v1.py}` exact source bytes.
The Rust default supplies compile-time locked bytes; explicit source inputs
must equal those defaults, preventing stale or forged viewer/runner/template
substitution. Each is nonempty UTF-8 <=262144 bytes. No file is executable.

`lesson.content-v0.bin` is the recovered stream. `lesson-data.js` is ASCII
`globalThis.LESSON_DATA = ` + compact sorted JSON (no LF inside) + `;\n`.
Its five metadata keys are `schema,content_base64,content_bytes,content_sha256,
root_id`; schema `golden-board.learner-prototype-data/v0`, standard padded
base64, and all other values from the admitted recovered stream. The owner
evaluation is only `owner/semantic-evaluation.json`. These eleven raw files
are preimages for the separately owned bundle manifest, never a release or
claim of fresh human success.
