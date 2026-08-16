# Golden Board practical chess v0

This specification is the sole owner of Golden Board v0 chess types, semantic
bytes, rules, logical APIs, scored chess predicates, and chess rejection
precedence. The FIDE Laws snapshot identified in `inputs/source-lock.toml` is
the rule source; this file states the selected project profile completely so an
implementation never has to infer scope from that source. `spec/source-v0.md`
owns raw-source syntax and game-record containers. `spec/identity-v0.md` owns
identity framing and domains. `spec/constants-v0.toml` owns the numeric value of
every symbolic code named here.

Implementations and fixtures are evidence, not authority. No FEN parser,
external chess library, source tag, comment, or transport field may add or
repair chess state.

## 1. Profile boundary

V0 is ordinary orthodox chess from the standard initial arrangement. It
includes movement, capture, control, check, legal moves, checkmate, stalemate,
castling, en passant, all four promotions, resignation, agreement after both
sides have moved, current-state threefold and 50-move claims, source score
validation, and the three closed `common_dead` classes below.

V0 excludes Chess960 and every other variant, alternate starts, clocks,
touch-move, arbiter remedies, intended-move claim paperwork, incorrect-claim
penalties, automatic fivefold or 75-move endings, time forfeits, a general
dead-position solver, and the rare resignation exception that depends on a
general mating-possibility decision. Claim availability never ends a game
automatically. A result on a legal nonterminal source position never implies a
particular declaration.

## 2. Primitive conventions and code ownership

- Integers in canonical bytes are unsigned big-endian.
- `ByteSlice` is an immutable byte sequence with an explicit bounded length.
- `Square` is a validated value in `0..63`. Square order is
  `a1,b1,...,h1,a2,...,h8`; index is `8 * (rank - 1) + file`, with files
  `a..h` numbered `0..7`.
- `File` is `0..7`; `Rank` is `0..7` for displayed ranks `1..8`.
- `Side` is exactly `SIDE_FIRST` (White) or `SIDE_SECOND` (Black).
- `PieceKind` is exactly pawn, knight, bishop, rook, queen, or king.
- Every symbolic code in this file must exist exactly once in
  `spec/constants-v0.toml`. This file owns its meaning; the TOML owns its
  numeric value. Reserved codes and bits reject and are never masked.
- No host enum layout, struct padding, FEN string, locale, map iteration order,
  time, randomness, or source metadata is canonical.
- Bounds are checked with checked arithmetic before indexing, multiplication,
  allocation, replay, or output construction.

Where this file says “sorted,” values are ordered by their unsigned canonical
integer encoding and are duplicate-free.

## 3. Canonical values and bytes

### 3.1 Position

Canonical `Position` is exactly 67 bytes:

```text
64 * u8 square_code, in a1..h8 order
u8      side_to_move
u8      castling_rights
u8      nominal_en_passant
```

Square codes have these meanings; their numeric assignments belong to the
constants owner:

```text
SQUARE_EMPTY
SQUARE_FIRST_PAWN       SQUARE_SECOND_PAWN
SQUARE_FIRST_KNIGHT     SQUARE_SECOND_KNIGHT
SQUARE_FIRST_BISHOP     SQUARE_SECOND_BISHOP
SQUARE_FIRST_ROOK       SQUARE_SECOND_ROOK
SQUARE_FIRST_QUEEN      SQUARE_SECOND_QUEEN
SQUARE_FIRST_KING       SQUARE_SECOND_KING
```

All other square codes reject. Castling rights are the OR of the four one-hot
bits `CASTLING_FIRST_KINGSIDE`, `CASTLING_FIRST_QUEENSIDE`,
`CASTLING_SECOND_KINGSIDE`, and `CASTLING_SECOND_QUEENSIDE`; every other bit is
reserved.

`EN_PASSANT_NONE` is numeric zero. Every other `nominal_en_passant` value is
exactly `square_index + 1`, where `square_index` is `0..63` in the canonical
`a1..h8` order. This chess-owned formula is a required input to constants
generation, not an assignment left to the constants owner. The field records
the passed-over square after every legal double pawn push, even if no legal
capture exists. Any other move clears it. Section 4.2 defines local coherence
and Section 7.4 defines its different treatment in a repetition key.

The standard initial `Position` bytes are the concatenation of these wrapped
hexadecimal lines, exactly 67 bytes:

```text
0402030506030204010101010101010100000000000000000000000000000000
0000000000000000000000000000000007070707070707070a08090b0c09080a
000f00
```

The literal remains a hand-vector requirement. If constants generation ever
disagrees with it, the affected owner must be repaired; an implementation may
not rewrite the vector.

### 3.2 Move

A canonical `Move` is exactly `u16_be`:

```text
bits 15..10  origin Square
bits  9..4   destination Square
bits  3..1   promotion code
bit      0   reserved zero
```

Promotion is exactly `PROMOTION_NONE`, `PROMOTION_QUEEN`, `PROMOTION_ROOK`,
`PROMOTION_BISHOP`, or `PROMOTION_KNIGHT`. The constants owner assigns the
codes and reserves all other three-bit values. Origin equal to destination,
any reserved promotion code, or the reserved low bit rejects during decode,
before board lookup. Castling is encoded only as the king move and en passant
only as the capturing pawn move; their effects derive from state.

### 3.3 Event

The typed event sum is:

```text
move(Move)
resignation(Side)
draw_agreement
claim_threefold
claim_50_move
```

Its canonical semantic bytes are closed:

```text
EVENT_MOVE             || encode_move(move)   # three bytes
EVENT_RESIGNATION      || side_code           # two bytes
EVENT_DRAW_AGREEMENT                           # one byte
EVENT_CLAIM_THREEFOLD                          # one byte
EVENT_CLAIM_50_MOVE                            # one byte
```

No event has padding or trailing data. Unknown event or side codes reject.
These bytes are semantic fixture/content atoms; no event identity is registered
in v0.

### 3.4 Results, terminal values, and state bytes

`Score` is exactly `SCORE_FIRST_WIN`, `SCORE_SECOND_WIN`, or `SCORE_DRAW`.
`BoardTerminal` is exactly `BOARD_TERMINAL_NONE`,
`BOARD_TERMINAL_CHECKMATE(winning_side)`, `BOARD_TERMINAL_STALEMATE`, or
`BOARD_TERMINAL_COMMON_DEAD`. `GameStatus` uses exactly
`GAME_STATUS_ACTIVE`, `GAME_STATUS_CHECKMATE`, `GAME_STATUS_STALEMATE`,
`GAME_STATUS_COMMON_DEAD`, `GAME_STATUS_RESIGNED`, `GAME_STATUS_AGREED`,
`GAME_STATUS_CLAIMED_THREEFOLD`, or `GAME_STATUS_CLAIMED_50_MOVE`. The
constants owner assigns all terminal/status codes.

`ClosureCause` is exactly one of:

```text
board(BoardTerminal other than BOARD_TERMINAL_NONE)
resignation(resigning_side)
draw_agreement
claim_threefold
claim_50_move
```

An active GameState has no ClosureCause or Score. A closed GameState retains
exactly one ClosureCause and its derived Score; status, cause, and Score cannot
be supplied or changed independently. The winning side carried by a checkmate
BoardTerminal and the resigning side carried by a resignation are part of the
cause.

There is deliberately no canonical byte serialization or identity for
`HistoryState`, `ReplayState`, or `GameState` in v0. They are opaque authority
types. Their observable facts are returned by APIs and predicates, while
canonical replay evidence stores the move sequence and resulting Position
bytes. This explicit absence prevents callers from pairing invented history
bytes with a Position.

## 4. Validation layers

### 4.1 Opaque construction

The four authority layers are:

1. `WirePosition`: created only by `decode_position`; field widths, codes, and
   reserved bits are valid, but the occupancy need not describe a possible
   chess position.
2. `LocallyAdmissiblePosition`: created only by `validate_local`; it satisfies
   every condition in Section 4.2 but need not be reachable.
3. `ReplayState`: an inseparable reached Position and HistoryState created only
   by `replay_from_start`, `apply_move`, or the move branch of `apply_event`,
   from the standard start.
4. artifact-bound input: a verified binding retains whether it contains a full
   ReplayState or only a locally admissible board-local diagram. Binding never
   upgrades authority.

`ReplayState` exposes a read-only `position` projection as WirePosition so
callers can use `encode_position`; it exposes no replace/set operation.
History facts are observable only through the typed predicate/API results below.

`GameState` is one opaque ReplayState plus active/closed status and, when
closed, exact cause and Score. `new_game` is its only public initial
constructor. There is no public constructor accepting independently supplied
position, history, status, counters, cause, or result.

GameState exposes read-only `replay`, `status`, `closure_cause`, and `score`
projections. The last two are absent exactly while active. Neither read-only
projection is an additional constructor or authority upgrade.

A locally admissible artifact diagram may be used only by the registry's
board-local setup/occupancy/control/defended/check/absolute-pin/escape-control/
passed-pawn/open-file/semi-open-file variants. Those are exact occupancy or
control geometry and make no reachability claim. `pseudo_legal_moves` is a
development/validation observation on the same local type, not authority for a
packed legal-move answer. A local diagram cannot enter legal-move, history,
event, terminal, source-record, or stateful lesson operations. No operation
repairs a code, inserts a king, clears rights, normalizes nominal en passant,
truncates history, or changes the validation layer by assertion.

### 4.2 Local admissibility and exact order

`validate_local` checks every condition without mutating its input and returns
the first listed rejection. Where a count is side-specific, first side precedes
second side. Where a square is reported, the lowest Square wins.

1. exactly one first-side king (`CHESS_LOCAL_FIRST_KING_COUNT`);
2. exactly one second-side king (`CHESS_LOCAL_SECOND_KING_COUNT`);
3. at most eight first-side pawns (`CHESS_LOCAL_FIRST_PAWN_COUNT`);
4. at most eight second-side pawns (`CHESS_LOCAL_SECOND_PAWN_COUNT`);
5. at most sixteen first-side pieces (`CHESS_LOCAL_FIRST_PIECE_COUNT`);
6. at most sixteen second-side pieces (`CHESS_LOCAL_SECOND_PIECE_COUNT`);
7. no pawn on displayed rank 1 or 8 (`CHESS_LOCAL_PAWN_ON_LAST_RANK`);
8. kings are not adjacent (`CHESS_LOCAL_KINGS_ADJACENT`);
9. both kings are not controlled simultaneously
   (`CHESS_LOCAL_BOTH_KINGS_CHECKED`);
10. the side not to move is not controlled
    (`CHESS_LOCAL_INACTIVE_KING_CHECKED`);
11. each asserted castling right, in first-kingside, first-queenside,
    second-kingside, second-queenside order, has that side's king on `e1`/`e8`
    and its entitled rook on `h1`/`a1`/`h8`/`a8`, returning respectively
    `CHESS_LOCAL_CASTLING_FIRST_KINGSIDE`,
    `CHESS_LOCAL_CASTLING_FIRST_QUEENSIDE`,
    `CHESS_LOCAL_CASTLING_SECOND_KINGSIDE`, or
    `CHESS_LOCAL_CASTLING_SECOND_QUEENSIDE`; and
12. nominal en passant is coherent in the suborder below.

For nonzero nominal en passant:

- when first side is to move, target rank is displayed rank 6, the target is
  empty, a second-side pawn is one rank toward rank 1 from the target, and its
  displayed rank-7 origin on the same file is empty;
- when second side is to move, target rank is displayed rank 3, the target is
  empty, a first-side pawn is one rank toward rank 8 from the target, and its
  displayed rank-2 origin on the same file is empty; and
- no adjacent capturer is required.

The suborder is target rank (`CHESS_LOCAL_EN_PASSANT_RANK`), target occupancy
(`CHESS_LOCAL_EN_PASSANT_TARGET_OCCUPIED`), just-moved pawn
(`CHESS_LOCAL_EN_PASSANT_PAWN`), then origin vacancy
(`CHESS_LOCAL_EN_PASSANT_ORIGIN_OCCUPIED`).

## 5. Public logical API

Python and Rust expose these equivalent pure operations. Language spelling may
follow local naming conventions, but arguments, result authority, sorting, and
failure meanings may not change.

```text
decode_position(ByteSlice) -> WirePosition | ChessReject
encode_position(WirePosition) -> [u8; 67]
decode_move(ByteSlice) -> Move | ChessReject
encode_move(Move) -> [u8; 2]
decode_event(ByteSlice) -> Event | ChessReject
encode_event(Event) -> ByteSlice
validate_local(WirePosition) -> LocallyAdmissiblePosition | ChessReject
controls_square(WirePosition, Side, Square) -> SquareList
king_in_check(LocallyAdmissiblePosition, Side) -> bool
pseudo_legal_moves(LocallyAdmissiblePosition) -> MoveList
replay_from_start(MoveSlice) -> ReplayState | ChessReject
legal_moves(ReplayState) -> MoveList
apply_move(ReplayState, Move) -> ReplayState | ChessReject
repetition_key(ReplayState) -> [u8; 67]
board_terminal(ReplayState) -> BoardTerminal
common_dead(ReplayState) -> bool
new_game() -> GameState
apply_event(GameState, Event) -> GameState | ChessReject
validate_source_record(MoveSlice, Score) -> RecordResult | ChessReject
evaluate_predicate(PredicateId, PredicateInput) -> PredicateResult | ChessReject
```

`MoveSlice` is an immutable indexed sequence with a known `u32` length.
`SquareList` is an immutable list of `0..64` distinct Squares;
`MoveList` is an immutable list of `0..512` distinct Moves. Both list types are
ascending by unsigned canonical encoding. The finite 64-square orthodox board
and the locally admissible 16-piece-per-side bound make these capacities total;
they are not truncation limits.

`RecordResult` is exactly
`(final_replay: ReplayState, score: Score, board_terminal: BoardTerminal,
threefold_available: bool, fifty_move_available: bool)`. `PredicateId` is an
immutable byte string with a known `u32` length and exact byte equality; any
value other than one of the 20 ASCII spellings in Section 8 is unknown.
`PredicateInput` is the tagged union of the exact input variants in that table,
and `PredicateResult` is the corresponding row's exact result variant. No
implicit string, integer, tuple, or authority coercion is permitted.

`encode_position`, `encode_move`, and `encode_event` accept only their typed
values, so they cannot fail. `encode_event` returns exactly the one-, two-, or
three-byte form in Section 3.3. `controls_square` is total on WirePosition
because it needs only bounded occupancy; it does not require a unique king.
`RecordResult` records no inferred declaration.

`legal_moves` is empty after checkmate, stalemate, or selected common-dead.
`apply_move` is replay/source-level and closure/history aware; it cannot observe
declaration closure because ReplayState contains no declaration. `apply_event`
is the authoritative ordinary-game transition and observes both board and
declaration closure. Source compilation starts from `new_game` and supplies SAN
moves through `apply_event`, so it cannot bypass common-dead closure.

Every rejection leaves every caller-owned value byte-for-byte/field-for-field
unchanged. An implementation may use immutable values or a private
transactional copy. No operation consults global mutable state.

`MoveSlice` supplies a known length and bounded element access. Replay never
copies or scans beyond the first 4,097 elements: it processes in order and the
attempt after 4,096 successful plies returns the history-resource code. An
earlier illegal/terminal failure therefore retains precedence even when the
caller declares a longer slice.

## 6. Board semantics

### 6.1 Control

Control is capture geometry with blockers, not legal-move filtering.

- A pawn controls its two one-rank-forward diagonals inside the board,
  regardless of target occupancy, and never controls forward.
- A knight controls its eight valid offsets and ignores intervening occupancy.
- A king controls every adjacent in-board square, including a friendly-occupied
  square.
- A bishop, rook, or queen controls each empty square on its ray, includes the
  first occupied square, and stops there.
- A pinned or otherwise constrained piece still controls by this geometry.
- Friendly occupancy may be controlled/defended but may not be captured.

`controls_square` returns the sorted origins of every piece of the supplied
side that controls the target. `king_in_check` is true exactly when the other
side has at least one controller of the side's unique king square.

### 6.2 Pseudo-legal movement

Pseudo-legal generation enforces the side to move, piece geometry, board
edges, blockers, friendly occupancy, pawn direction and capture distinction,
initial double-step origin and intermediate vacancy, promotion context,
nominal en-passant geometry, and castling right/pieces/empty path. It does not
filter ordinary self-check. For castling it does not yet filter current,
transit, or destination control.

Kings move one square. Knights use their fixed offsets. Bishops, rooks, and
queens stop at the first occupied square and include it only if opposing.
Pawns move one empty square forward; from displayed rank 2 for first side or 7
for second side they may move two if both squares are empty. They capture one
forward diagonal only when occupied by an opposing non-king piece or when the
exact en-passant rule applies. Capturing either king is never pseudo-legal.

A pawn reaching displayed rank 8/1 must carry exactly one Q/R/B/N promotion.
A promotion on any other move is absent from pseudo-legal output. Every legal
promotion context yields four distinct Move values.

### 6.3 Legal movement and operation order

For an ordinary candidate, apply its complete capture/movement/promotion,
update rights and nominal en passant, toggle side, then test the moving side's
king against opponent control. A king capture is already excluded. Removing a
captured blocker may expose a slider, and en passant removes the bypassed pawn
before this test. A move is legal only if the king is then safe.

Rights clear permanently when:

- that side's king moves (both rights);
- the entitled rook moves from its home square (that right); or
- the entitled rook is captured on its home square (that right).

A replacement or promoted rook on the home square never restores a right.

Any legal double pawn push stores its passed-over square as nominal en passant.
Every other move, including an en-passant capture, clears the field.

### 6.4 Castling

Castling is the king move `e1-g1`, `e1-c1`, `e8-g8`, or `e8-c8`. It requires,
in this order:

1. the corresponding right;
2. the king and entitled rook on their home squares;
3. every square between them empty (the queenside `b` square must be empty);
4. the king origin not controlled in the current position;
5. the transit square not controlled in a probe with the king moved there, its
   origin empty, and the rook still on its home square; and
6. the destination not controlled in the fully applied position with the rook
   relocated.

Control of the rook or of queenside `b1`/`b8` alone does not forbid castling.
The rook relocates `h1-f1`, `a1-d1`, `h8-f8`, or `a8-d8` respectively.

### 6.5 En passant

An en-passant capture requires a pawn adjacent by file to the opponent pawn
that just double-pushed, the nominal target as its one-rank-forward diagonal
destination, that empty destination, and the matching opponent pawn behind
the target. The captured pawn is removed before king safety. The opportunity
lasts exactly the next ply because any intervening move clears the nominal
field.

### 6.6 Illegal-move diagnosis

When `apply_move` receives a Move absent from `legal_moves`, it diagnoses the
first applicable family in this order:

1. empty origin (`CHESS_MOVE_EMPTY_ORIGIN`);
2. origin belongs to the other side (`CHESS_MOVE_WRONG_SIDE`);
3. friendly destination (`CHESS_MOVE_FRIENDLY_DESTINATION`);
4. attempted king capture (`CHESS_MOVE_KING_CAPTURE`);
5. pawn reaches its last rank without promotion
   (`CHESS_MOVE_PROMOTION_MISSING`);
6. any promotion on a non-pawn or non-last-rank move
   (`CHESS_MOVE_PROMOTION_UNNEEDED`);
7. a king home-to-castle-destination attempt, diagnosed by right, path, current
   check, transit check, then destination check using
   `CHESS_MOVE_CASTLING_RIGHT`, `CHESS_MOVE_CASTLING_PATH`,
   `CHESS_MOVE_CASTLING_FROM_CHECK`,
   `CHESS_MOVE_CASTLING_THROUGH_CHECK`, and
   `CHESS_MOVE_CASTLING_INTO_CHECK` in that order;
8. a pawn diagonal to an empty square, diagnosed as nominal target/expiry then
   remaining geometry with `CHESS_MOVE_EN_PASSANT_TARGET` and
   `CHESS_MOVE_EN_PASSANT_GEOMETRY`;
9. non-pawn direction/distance failure (`CHESS_MOVE_GEOMETRY`);
10. a slider with an occupied intervening square (`CHESS_MOVE_BLOCKED`);
11. a pawn forward move with wrong direction/distance or occupied destination
    (`CHESS_MOVE_PAWN_ADVANCE`);
12. a pawn diagonal whose required opposing capture is absent
    (`CHESS_MOVE_PAWN_CAPTURE`);
13. a two-square pawn attempt with wrong origin or nonempty intermediate square
    (`CHESS_MOVE_PAWN_DOUBLE`); and
14. an otherwise pseudo-legal move that leaves or moves its king into check
    (`CHESS_MOVE_SELF_CHECK`).

For pawn diagnosis, a two-square same-file attempt uses item 13; another
same-file attempt uses item 11; a one-file diagonal attempt uses item 8 when
its destination is empty and item 12 otherwise; every other pawn displacement
uses item 11. This makes every Move map to one primary family without relying
on generator iteration order.

## 7. Replay, history, terminal state, and declarations

### 7.1 History

Opaque `HistoryState` contains:

- played ply count, initially zero;
- halfmove clock, initially zero;
- the ordered repetition-key sequence including the initial key; and
- occurrence counts derivable from that sequence.

`MAX_HISTORY_PLIES` is the constants-owned value 4,096. The key sequence has at
most 4,097 entries and a count type must represent 4,097. The sequence is
authoritative; a cache is allowed only if checked against it. When played plies
already equal the maximum, the next move rejects
`CHESS_RESOURCE_HISTORY_PLIES` before any transition and changes nothing. A
move that starts at 4,095 may succeed and reach 4,096.

After each legal move, append the next repetition key. Reset the halfmove clock
after every pawn move or capture, including en passant; otherwise increment it
with checked arithmetic. Completed full moves are `floor(played_plies / 2)`;
the display number for the current slot is `floor(played_plies / 2) + 1`.
Neither is stored independently.

### 7.2 Terminal order

For terminal truth, use the private mechanical legal-move set that ignores only
profile closure. Evaluate in this exact order:

1. no legal move and next side checked: checkmate, mover wins;
2. no legal move and next side not checked: stalemate/draw;
3. otherwise a Section 7.3 class: common-dead/draw;
4. otherwise none.

Thus stalemate wins over a simultaneous material-class match. Public
`legal_moves` is empty for all three terminal outcomes. `apply_move` and
`replay_from_start` reject the first attempted continuation with
`CHESS_GAME_CLOSED`, even though a common-dead board may have geometric moves.

### 7.3 Deliberately partial common-dead classifier

`common_dead` is true only for these exact material multisets, in either color
direction and with no other piece:

```text
king versus king
king and one bishop versus king
king and one knight versus king
```

It is false for every other configuration, including K+NN versus K. False
means only “not one of the v0 classes,” never that mate is generally possible.

### 7.4 Repetition key and claims

The repetition key uses the 67-byte Position layout. Its occupancy, side, and
castling bytes are unchanged. Its final byte is nominal en passant only when at
least one fully legal en-passant capture is available to the side to move;
otherwise it is `EN_PASSANT_NONE`. A pseudo-capture that exposes the capturing
king does not preserve the field. Halfmove clock, occurrence counts, played
plies, status, score, record identity, and transport state never enter the key.

The initial key has occurrence count one. Threefold is currently claimable
when the current key count is at least three. The practical 50-move draw is
currently claimable when the halfmove clock is at least 100. Neither condition
ends the game without its accepted event. Source records may continue while a
claim is available.

For `HistoryClaimResult`, `nominal_ep` is `none` exactly when the Position's
field is `EN_PASSANT_NONE`, otherwise `square(the decoded nominal target)`.
`effective_ep` is that same square only when at least one fully legal
en-passant capture is currently available to the side to move; otherwise it is
`none`.

### 7.5 Game events

`new_game` returns the active standard initial GameState. `apply_event` first
rejects `CHESS_GAME_CLOSED` for any event when status is closed or the replay is
board-terminal. While active:

- `move` delegates to `apply_move`, then maps Section 7.2 exactly: none remains
  active with absent cause/Score; checkmate stores the board cause, checkmate
  status, and winning-side Score; stalemate/common-dead store that board cause,
  matching status, and draw Score;
- either named side may resign and the other side wins;
- agreement requires at least two played plies, otherwise
  `CHESS_EVENT_AGREEMENT_TOO_EARLY`;
- a threefold claim requires current availability, otherwise
  `CHESS_EVENT_THREEFOLD_UNAVAILABLE`;
- a 50-move claim requires current availability, otherwise
  `CHESS_EVENT_50_MOVE_UNAVAILABLE`; and
- accepted agreement/claims close as draw.

Accepted resignation stores its resigning-side cause, resigned status, and the
other side's win Score. Accepted agreement and claims store their matching
declaration cause/status and draw Score. Rejected declarations change nothing.
Claims belong to the side to move; the event carries no redundant side field.

### 7.6 Source score relation

`validate_source_record` requires `1..MAX_HISTORY_PLIES` Moves, replays them
closure-aware from the standard start, and then applies:

- checkmate requires the winning side's Score, otherwise
  `CHESS_RECORD_CHECKMATE_SCORE`;
- stalemate or selected common-dead requires `SCORE_DRAW`, otherwise
  `CHESS_RECORD_DRAW_SCORE`;
- a legal nonterminal final position accepts any Score; and
- claim availability alone never constrains Score.

An empty move list rejects `CHESS_RECORD_EMPTY`. Score code validation occurs
when the Score is decoded by its owning wire consumer. `RecordResult` closes
the source record only; it does not change final-position legal moves or invent
resignation, agreement, or claim.

## 8. Closed scored-predicate registry

The following 20 UTF-8 ASCII IDs are the exhaustive v0 chess/source-semantic
registry. Curriculum records reference exactly these spellings and their
constants-owned `PREDICATE_*` codes. `evaluate_predicate` rejects an unknown ID
with `CHESS_PREDICATE_UNKNOWN` and an ID/input variant or row-specific field
shape mismatch with `CHESS_PREDICATE_SIGNATURE`, at the phase fixed in Section
9.3. There is no expression language, callback, user-defined predicate, engine
evaluation, or content-corruption predicate.

Common bounded types used below are:

- `SquareSlice`: an immutable indexed sequence of candidate `u8` Square values
  with a known `u32` length and bounded element access;
- a predicate-input `MoveSlice`: at most 4,096 Moves;
- `OccupancyMatch`: empty, occupied, or exact `(Side, PieceKind)`;
- `Defender`: any, or one exact origin Square;
- `EnPassantFact := none | square(Square)`; and
- `PredicateResult` is the exact result type in the registry row, not a
dynamically coerced truth value.

The exact string/code bindings are:

```text
chess.setup_turn                 PREDICATE_SETUP_TURN
chess.occupancy                  PREDICATE_OCCUPANCY
chess.move_legality              PREDICATE_MOVE_LEGALITY
chess.control                    PREDICATE_CONTROL
chess.defended                   PREDICATE_DEFENDED
chess.king_check                 PREDICATE_KING_CHECK
chess.absolute_pin               PREDICATE_ABSOLUTE_PIN
chess.fork_double_attack         PREDICATE_FORK_DOUBLE_ATTACK
chess.discovered_attack_check    PREDICATE_DISCOVERED_ATTACK_CHECK
chess.escape_square_control      PREDICATE_ESCAPE_SQUARE_CONTROL
chess.passed_pawn                PREDICATE_PASSED_PAWN
chess.open_file                  PREDICATE_OPEN_FILE
chess.semi_open_file             PREDICATE_SEMI_OPEN_FILE
chess.finite_promotion_race      PREDICATE_FINITE_PROMOTION_RACE
chess.finite_mating_geometry     PREDICATE_FINITE_MATING_GEOMETRY
chess.terminal_transition        PREDICATE_TERMINAL_TRANSITION
chess.history_claim              PREDICATE_HISTORY_CLAIM
chess.declaration_event          PREDICATE_DECLARATION_EVENT
chess.source_score_relation      PREDICATE_SOURCE_SCORE_RELATION
chess.move_record_replay         PREDICATE_MOVE_RECORD_REPLAY
```

| Predicate ID | Exact input | Exact result and definition |
|---|---|---|
| `chess.setup_turn` | `SetupTurnInput := initial(WirePosition) \| current_side(ReplayState, Side)` | `bool`; exact byte equality with the standard initial Position, or equality with the replay's side to move. |
| `chess.occupancy` | `OccupancyInput(WirePosition, Square, OccupancyMatch)` | `bool`; exact square-code match under the requested empty/occupied/exact mode. |
| `chess.move_legality` | `MoveLegalityInput(ReplayState, Move)` | `MoveLegalityResult := legal \| illegal(ChessRejectCode)`; uses `apply_move` on a copy and Section 6.6 diagnosis. Resource/closed codes remain distinguishable. |
| `chess.control` | `ControlInput(WirePosition, Side, Square)` | sorted `SquareList`; exactly `controls_square`. |
| `chess.defended` | `DefendedInput(WirePosition, target, Defender)` | `bool`; false if target is empty; otherwise another same-side piece controls target, restricted to the exact origin when supplied. |
| `chess.king_check` | `KingCheckInput(LocallyAdmissiblePosition, Side)` | `bool`; exactly `king_in_check`. |
| `chess.absolute_pin` | `AbsolutePinInput(LocallyAdmissiblePosition, origin)` | `bool`; origin holds a non-king whose own king is initially safe, and removing only that piece makes its own king controlled by an opposing bishop/rook/queen ray. |
| `chess.fork_double_attack` | `AfterMoveNamedTargetsInput(ReplayState, Move, targets: SquareSlice)` | `bool`; after the validation below, move is legal and its moved/promoted piece controls every named square, each of which then contains an opposing piece. No value judgment is implied. |
| `chess.discovered_attack_check` | `DiscoveredLineInput(ReplayState, Move, slider_origin, target)` | `bool`; move is legal; a same-side bishop/rook/queen distinct from the mover remains at slider_origin; before the move, the mover's origin lies strictly between slider_origin and target on a ray valid for that slider and is the first occupied square from the slider; afterward, the slider controls target. A target holding the opposing king is discovered check. |
| `chess.escape_square_control` | `EscapeControlInput(WirePosition, controlling_side, candidate)` | `bool`; true iff `controls_square` is nonempty. It does not claim that a king move to candidate is legal. |
| `chess.passed_pawn` | `PassedPawnInput(LocallyAdmissiblePosition, pawn_square)` | `bool`; false unless the square holds a pawn; true iff no opposing pawn lies strictly ahead, from that pawn's perspective, on its file or either in-board adjacent file. |
| `chess.open_file` | `OpenFileInput(WirePosition, File)` | `bool`; no pawn of either side occupies the file. |
| `chess.semi_open_file` | `SemiOpenFileInput(WirePosition, Side, File)` | `bool`; no pawn of the named side and at least one opposing pawn occupy the file. |
| `chess.finite_promotion_race` | `FinitePromotionTree` below | `FiniteRaceResult`; the sorted nonempty set of `first_promotes`, `second_promotes`, and `no_promotion_in_branch` outcomes over all packed root-to-leaf branches. |
| `chess.finite_mating_geometry` | `FiniteMatingTree` below | `FiniteMatingResult(mating_side, all_branches_mate, max_plies)` computed exactly from the validated tree. |
| `chess.terminal_transition` | `TerminalTransitionInput(ReplayState, Move)` | `BoardTerminal`; apply the legal move on a copy and return Section 7.2 truth. An illegal move rejects with its ordinary primary code. |
| `chess.history_claim` | `ReplayState` | `HistoryClaimResult(nominal_ep: EnPassantFact, effective_ep: EnPassantFact, current_key_occurrences: u16, halfmove_clock: u16, played_plies: u16, threefold_available: bool, fifty_move_available: bool)`; every field derives from the inseparable state. Occurrences are `1..4,097`; both clocks are `0..4,096`. |
| `chess.declaration_event` | `DeclarationEventInput(GameState, Event)` | `DeclarationEventResult := accepted(GameStatus, ClosureCause?, Score?) \| rejected(ChessRejectCode)`; evaluates `apply_event` on a copy, including post-close and premature/unavailable cases. Cause and Score are both absent exactly when the accepted state remains active. |
| `chess.source_score_relation` | `SourceScoreInput(MoveSlice, Score)` | `SourceScoreResult := accepted(BoardTerminal) \| rejected(ChessRejectCode)`; exactly `validate_source_record`, retaining contradiction versus replay failure. |
| `chess.move_record_replay` | `MoveRecordInput := move_bytes(ByteSlice) \| record(MoveSlice, Score)` | `MoveRecordResult := decoded(Move) \| replayed(RecordResult) \| rejected(ChessRejectCode)`; move bytes use `decode_move`; an already decoded record uses `validate_source_record`. Raw game framing, truncation, and trailing-byte truth remain source-v0-owned so the chess core has no source-parser dependency. |

For `move_legality`, `declaration_event`, `source_score_relation`, and
`move_record_replay`, the semantic failure described in the row is data inside
the typed result; only dispatch/signature/resource failures escape as
ChessReject. For fork/double-attack and discovered-attack/check, an illegal,
closed, or over-history Move escapes with its ordinary transition rejection;
`false` is reserved for a successfully applied move that lacks the relation.
Finite-tree transition failures instead use the closed tree code below.

For fork input, the tagged variant is checked first, then ordinary closure as
specified in Section 9.3. A target length above 16 is
`CHESS_RESOURCE_PREDICATE_INPUT` without inspecting an element. After that
resource check, a length below 2, any value outside `0..63`, a duplicate, or a
nonascending sequence is `CHESS_PREDICATE_SIGNATURE`. Thus an accepted target
list is exactly `2..16` distinct ascending Squares, while a closed-state fork
input with 17 targets returns `CHESS_GAME_CLOSED` before the resource code.

`FinitePromotionTree` is exactly `(root: ReplayState, nodes: NodeSlice)`.
NodeSlice and each Node's EdgeSlice are immutable indexed sequences with known
`u32` lengths. The accepted node length is `1..4,096`; `nodes[0]` represents
root. A Node stores only an EdgeSlice whose accepted length is `0..256`; each
edge is `(move: Move, child_index: u16)`, Moves are distinct and sorted, and no
child Position, ReplayState, status, terminal value, or result is stored. Every
child index is in range and greater than its parent index. Starting at node 0
and following sorted edges, depth-first preorder must visit node indices
exactly `0..len(nodes)-1`; every non-root must have exactly one incoming edge,
and every node must be visited. Derived state 0 is root, and each other state is
uniquely `apply_move(derived parent state, edge move)`.

Before traversal or transition, checked aggregate validation returns
`CHESS_RESOURCE_PREDICATE_INPUT` for more than 4,096 nodes, more than 256 edges
in any node, more than 4,095 total edges, or collection-size arithmetic
overflow, without traversing an edge. After that resource screen, zero nodes,
an invalid index/order/parent/depth shape, or any closed, over-history, or
illegal edge transition is `CHESS_PREDICATE_TREE`; no other transition code
escapes from a finite-tree predicate. A closed root with no edge is simply a
leaf. Depth is at most 64. A branch stops at its first
promotion and records that mover; a node reached by promotion must be a leaf. A
leaf reached without promotion records no-promotion. The result is the sorted
set union of all reached leaf outcomes. The tree claims only its explicitly
packed alternatives, not forced play or move quality.

`FiniteMatingTree` is exactly `(root: ReplayState, mating_side: Side,
nodes: NodeSlice)` with the same encoding, derivation, aggregate checks,
graph bounds, and error mapping. Root material is exactly both kings plus either
one queen or one rook belonging to `mating_side`. A terminal derived node has
no edges. At each active mating-side node there is exactly one supplied legal
edge. At each active opposing-side node, edges equal the complete sorted
`legal_moves` set. `all_branches_mate` is true only when every leaf is
checkmate won by `mating_side`; `max_plies: u8` is the greatest root-to-leaf
edge count, or zero when the root is a leaf. This proves the finite displayed
geometry without a hidden search.

Terms including “best,” “winning position,” “activity,” “forcing,” “overload,”
“favourable,” and unrestricted “threat” are not scoreable v0 predicates.
Material values and heuristics may be taught only as explicitly unscored
tendencies. False from `common_dead` is never promoted to a mating-possibility
claim.

## 9. Chess rejection contract

### 9.1 Canonical shape

The only canonical cross-language rejection datum is:

```text
ChessReject { code: ChessRejectCode }
```

The constants owner assigns each code one `u16` value, reserves zero for
`CHESS_OK`, and follows the order below. Implementations may attach a message,
square, ply, expected value, or cause for local debugging, but every such field
is optional, noncanonical, non-scoring, and excluded from cross-language and
fixture equality. Exception text never has authority.

Typed APIs make some layers unrepresentable. When an operation can observe
several defects, the earliest layer wins; within a layer the first listed code
wins. Replay processes plies in input order, so the earliest failing ply wins.

### 9.2 Total code order

**A. Structural encoding and predicate dispatch**

```text
CHESS_POSITION_LENGTH
CHESS_POSITION_SQUARE_CODE
CHESS_POSITION_SIDE_CODE
CHESS_POSITION_CASTLING_RESERVED
CHESS_POSITION_EN_PASSANT_CODE
CHESS_MOVE_LENGTH
CHESS_MOVE_RESERVED
CHESS_MOVE_PROMOTION_CODE
CHESS_MOVE_SAME_SQUARE
CHESS_EVENT_LENGTH
CHESS_EVENT_CODE
CHESS_EVENT_SIDE_CODE
CHESS_EVENT_TRAILING
CHESS_PREDICATE_UNKNOWN
CHESS_PREDICATE_SIGNATURE
```

Position square-code ties use lowest Square. Length is checked before reading
any Position or Move field. Move reserved bit precedes promotion code, then
same-square. For event bytes, empty input is `CHESS_EVENT_LENGTH`; otherwise
read the tag, reject an unknown tag with `CHESS_EVENT_CODE`, and reject fewer
than that known event's required bytes with `CHESS_EVENT_LENGTH`. Next, a move
event decodes exactly bytes 1..3 with the Move order above, or a resignation
validates its side with `CHESS_EVENT_SIDE_CODE`. Only then do extra bytes reject
with `CHESS_EVENT_TRAILING`. The three one-byte declarations have no payload.
At this initial dispatch phase, `CHESS_PREDICATE_SIGNATURE` means only that the
tagged input variant does not match the selected ID. Its fork-field-shape use is
deliberately later, after closure and aggregate resource checks, as Section 9.3
states.

**B. Local incoherence**

The `CHESS_LOCAL_*` codes occur exactly in Section 4.2 order.

**C. Closure**

```text
CHESS_GAME_CLOSED
```

Closure is checked before resource and move/event validity. Thus any event
after any terminal/declaration returns this code regardless of its other
semantic defects.

**D. Resources**

```text
CHESS_RESOURCE_HISTORY_PLIES
CHESS_RESOURCE_PREDICATE_INPUT
```

History cap precedes move legality. Predicate aggregate count/checked-size
bounds precede finite-tree traversal. An ordinary transition predicate exposes
closure before its resource/move validity. Finite trees are the exception: a
closed root with no edge may be a leaf, while a closed root with an edge maps to
`CHESS_PREDICATE_TREE` after aggregate bounds pass.

**E. Illegal move**

The `CHESS_MOVE_*` codes occur exactly in Section 6.6 order.

**F. Invalid event**

```text
CHESS_EVENT_AGREEMENT_TOO_EARLY
CHESS_EVENT_THREEFOLD_UNAVAILABLE
CHESS_EVENT_50_MOVE_UNAVAILABLE
```

**G. Predicate finite proof**

```text
CHESS_PREDICATE_TREE
```

Tree aggregate resource failure is layer D. After bounds pass, validation uses
node-index order and then sorted Move-edge order and maps every tree shape or
edge-transition defect to this code. No deeper diagnostic is canonical.

**H. Source-record relation**

```text
CHESS_RECORD_EMPTY
CHESS_RECORD_CHECKMATE_SCORE
CHESS_RECORD_DRAW_SCORE
```

Replay/closure/resource/illegal failures in the MoveSlice retain their earlier
chess code. Only a completely replayed record can reach score contradictions.

### 9.3 Operation pipelines

- `decode_position`: layer A Position entries only.
- `decode_move`: layer A Move entries only.
- `decode_event`: layer A Event entries only; an embedded move uses the Move
  decoding order before the event trailing-byte check.
- `validate_local`: layer B only; its WirePosition already passed A.
- `replay_from_start`: for each Move, closure, history resource, then illegal
  move; no partial ReplayState is returned.
- `apply_move`: closure, history resource, then illegal move.
- `apply_event`: closure; for move, history resource then illegal move; for a
  declaration, layer F.
- `validate_source_record`: empty first; then replay pipeline; then layer H
  score relation. Empty is considered only after its typed inputs are decoded.
- `evaluate_predicate`: ID, then tagged input-variant signature. Next,
  ordinary transition-bearing variants precheck closure on the supplied
  ReplayState/GameState before aggregate
  resources: `move_legality` and `declaration_event` wrap
  `CHESS_GAME_CLOSED` in their row result; fork/discovered/terminal-transition
  escape it. Finite-tree variants skip this closure precheck. Then aggregate
  resources run, followed by remaining row-specific field shape, ordinary
  transition, finite-tree, or record rules. Source-score and record-replay
  variants have no supplied state to precheck; replay failures are wrapped as
  their row specifies.

These pipelines are the tie-breaker for multiply invalid cases; an
implementation may discover defects in another order but must report the same
primary code.

## 10. Required evidence and invariants

The hand-authored chess suite and bounded language-local generators must cover:

- exact initial Position bytes, repetition bytes/identity vectors from the
  identity owner, the 20 sorted initial legal Moves, and exact Position/Move/
  Event decode rejection and round-trip vectors;
- every piece geometry, capture/friendly/blocker boundary, pinned control,
  adjacent kings, and a king capture that opens a slider line;
- both castlings for both sides, lost/nonrestored rights, attacked rook,
  queenside `b`-square-only attack, and origin-safe transit attack;
- nominal en passant without a capturer, legal capture, expiry, two candidate
  capturers, pinned/self-exposing capture, and effective repetition handling;
- quiet and capture promotion to Q/R/B/N, missing/unnecessary promotion, and
  immediate check/mate;
- checkmate, stalemate, all three common-dead classes, stalemate/common-dead
  overlap with stalemate precedence, and K+NN versus K false;
- initial repetition occurrences one/two/three, nominal/effective en passant,
  castling-right differences, halfmove 99/100, and pawn/capture resets;
- history at 4,095/4,096 plies and an atomic rejected next move;
- agreement at 0/1/2 plies, valid/invalid claims, every declaration closure,
  and every event after closure;
- nonterminal source Scores and each terminal contradiction;
- every predicate signature/result, including finite-tree completeness; and
- every rejection layer plus multiply invalid precedence and no mutation,
  including a closed-state fork input with 17 targets returning
  `CHESS_GAME_CLOSED` before the aggregate resource code, while a closed-root or
  derived-terminal finite-tree edge maps to `CHESS_PREDICATE_TREE` after
  aggregate bounds.

Bounded properties verify sorted/deduplicated outputs, replay determinism,
Position round-trip, king safety after every returned legal Move, all four
promotions, rights/halfmove/key updates, and that only declared fields are
ignored by repetition identity. Generators must have fixed seed/case bounds and
print a replayable seed/case on failure.

A pinned development-only chess library may compare normalized legal moves,
post-move occupancy/side/rights/strict nominal en passant, check, and matched
checkmate/stalemate/history cases. It does not parse project source, define SAN,
supply expected fixture bytes, decide broad deadness, or enable automatic
fivefold/75-move outcomes. Any disagreement blocks review; no majority vote or
automatic fixture rewrite is permitted.

All artifact-critical replay and predicate work is bounded by the limits above.
No recursive general search, engine evaluation, move ranking, opening data, or
tablebase is part of this contract.
