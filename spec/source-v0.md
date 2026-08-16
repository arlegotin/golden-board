# Golden Board anthology source v0

This specification is the sole owner of Golden Board v0 raw Markdown/fenced
game grammar, project SAN, raw-byte rejection spans and precedence, source
compilation, minimal game records, canonical game-set construction, and source
agreement evidence. It is deliberately not a general Markdown, PGN, or SAN
standard.

`docs/64_games.md` is the sole anthology input and its receipt is owned by
`inputs/source-lock.toml`. `spec/chess-v0.md` owns chess truth and Move/Position
bytes. `spec/identity-v0.md` owns identity framing/domains.
`spec/constants-v0.toml` owns the numeric value of every symbolic code named
here. The 1994 PGN guide is historical background only; FIDE Appendix C does
not define this grammar.

Implementations, the M0 source doctor, source tags, comments, reports, and
external libraries are untrusted evidence, never grammar or chess authority.

## 1. Public values and operations

### 1.1 Values

```text
RawSpan { raw_start: u32, raw_end: u32 }
SourceReject { code: SourceRejectCode, raw_start: u32, raw_end: u32 }
GameRecord { moves: Move[1..4096], score: Score }
CompiledGame { source_ordinal, opener_span, token rows, GameRecord }
SourceCandidate { 64 CompiledGames, game-set bytes }
RetainedEvidence { retained report bytes, game-set bytes }
```

A RawSpan is zero-based, half-open, and indexes the exact supplied bytes. It
always satisfies `0 <= raw_start <= raw_end <= input_length`. The three fields
of SourceReject are the complete canonical cross-language rejection value.
Messages and richer context are optional, noncanonical, and not compared.

`Move`, `Score`, Position bytes, ReplayState, and chess rejections have exactly
their chess-v0 meanings. GameRecord, CompiledGame, and SourceCandidate are
opaque values produced only after their owning validation; callers cannot
inject a token row, move, score, ordinal, or derived byte field.

### 1.2 Logical API

The independent Python and Rust lanes expose equivalent pure operations:

```text
compile_source(ByteSlice) -> SourceCandidate | SourceReject
encode_game(GameRecord) -> GameBytes
decode_game(ByteSlice) -> GameRecord | SourceReject
validate_anthology(GameRecordSlice) -> GameRecordList | SourceReject
encode_game_set(GameRecordSlice) -> GameSetBytes | SourceReject
decode_game_set(ByteSlice) -> GameRecordList | SourceReject
encode_candidate_trace(SourceCandidate, EvidenceInputs) -> CandidateBytes | SourceReject
validate_candidate_trace(CandidateBytes, GameSetBytes, EvidenceInputs)
    -> ValidatedCandidate | SourceReject
coordinate_candidates(ValidatedCandidate, ValidatedCandidate)
    -> RetainedEvidence | SourceReject
validate_retained_evidence(ReportBytes, GameSetBytes, EvidenceInputs)
    -> ValidatedEvidence | SourceReject
```

`validate_anthology` requires exactly 64 already valid records with distinct
complete Move streams and preserves input order. `compile_source` uses that
profile before constructing its canonical set. `EvidenceInputs` contains the
exact locked raw source bytes, raw bytes of the chess/source/identity
specifications and constants file, and the registered identity operations. It
contains no expected moves, trace, report, or game set.

The host adapter that opens `docs/64_games.md` must use the M0-equivalent safe
relative path, regular-file, no-symlink, bounded-read, length, and digest checks
before `compile_source`. The pure compiler itself still checks byte length.
Every rejection returns no partial accepted record, trace, report, or set.

## 2. Input profile and spans

### 2.1 Resource limits

| Resource | Inclusive limit |
|---|---:|
| Raw source bytes | 1,048,576 |
| Recognized blocks | exactly 64 |
| One block fence span, opener through closer newline | 65,535 bytes |
| Tag lines per block | 64 |
| Tag name | 32 raw ASCII bytes |
| Raw tag value between quotes, before escape decoding | 1,024 bytes |
| Movetext tokens per block | 8,192 |
| Potential or accepted ply tokens per block | 4,096 |
| Potential or accepted ply tokens over the source | 65,535 |
| Decoded/encoded plies over one general game set | 65,535 |
| Candidate or retained canonical manifest, including final LF | 1,048,576 bytes |

Limits are checked before multiplication, allocation, collection growth, chess
replay, or output. A scanner may retain spans/indices into the immutable input;
it need not copy tag values or tokens. These are M1 source-language limits, not
future artifact/profile limits.

### 2.2 Byte profile

- Input is strict UTF-8 with no initial UTF-8 BOM.
- NUL, DEL, and C0 controls other than HT, LF, and CR reject.
- Newlines are uniformly LF or uniformly CRLF and the source ends in one of
  that form. Bare CR and mixed LF/CRLF reject.
- `HWS` is ASCII SP or HT. No Unicode category or locale whitespace test is
  used.
- Valid non-ASCII scalars are data and are accepted only where the enclosing
  grammar permits opaque text.
- Line recognition and tokenization operate on raw ASCII delimiter bytes after
  byte-profile validation; no normalization or re-encoding occurs.

### 2.3 Exact span rules

- A physical line span excludes its newline terminator. A token/tag-name/tag-
  value span covers only its raw lexeme. A fence span used as data includes the
  opener line, every content byte, the closer line, and its newline.
- The BOM span is `[0,3)`.
- Strict UTF-8 is defined by the Unicode scalar UTF-8 byte grammar, excluding
  overlong forms, surrogates, and values above U+10FFFF. Let `p` be the length
  of the maximal valid UTF-8 prefix. For an ill-formed subsequence, report
  `[p,p+1)`. For a valid lead whose required continuation bytes are missing at
  EOF, report `[p,input_length)`. This never delegates offset choice to a host
  decoder.
- A control error covers its one byte.
- A bare CR covers that CR. For mixed newline forms, the first newline
  terminator establishes the form and the first later terminator of the other
  form is reported: one byte for LF, two bytes for CRLF.
- A malformed line or token covers the complete offending raw line/token,
  excluding newline. A specific bad escape covers backslash plus its following
  byte, or just the final backslash when the value ends.
- An exceeded byte limit points to the first excess byte. An exceeded item
  count covers the first excess item. A missing required byte/token uses a
  zero-width span at the position where it was required; a source-global
  missing final item uses `[input_length,input_length)`.
- A duplicate tag covers the later decoded name. A duplicate move stream
  covers the later block's opener line.

At one rejection stage, the candidate with lowest `raw_start` wins; equal
starts use the code order printed in Section 8. Category/stage precedence wins
over raw position. Implementations may discover errors in another order, but
must return this result.

## 3. Fence and block grammar

Logical lines exclude newline bytes. A recognized opener at column zero is:

````text
```pgn HWS*
````

where the visible opener begins with exactly three backticks immediately
followed by lowercase `pgn`; only HWS may follow. A recognized closer at column
zero is exactly three backticks followed only by `HWS*`.

Outside a block, an exact closer is orphaned. Inside a block, an exact opener is
nested. An opener without a later closer is unclosed and uses a zero-width span
at EOF. Any column-zero line whose first three bytes are backticks but is
neither the exact opener nor exact closer is a bad fence shape, including
uppercase language, four backticks, suffix text, or leading/trailing non-HWS. A
line whose first non-HWS bytes are three backticks but that has leading HWS is
also `SOURCE_FENCE_SHAPE`, inside or outside a block. One or two backticks
remain ordinary bytes. No indented form can open or close a block.

From every recognized opener, block-byte counting starts at that opener's first
byte and continues over every raw byte while the block remains open. Reading
the first byte beyond 65,535 returns `SOURCE_FENCE_BLOCK_BYTES` even if EOF is
later reached without a closer. When an under-limit opener is unclosed, its
zero-width EOF error ties a short fence count at EOF and the printed Stage 3
code order selects `SOURCE_FENCE_UNCLOSED`.

Exactly 64 structurally valid opener/closer pairs are required. Bytes outside
valid pairs are ignored after byte/fence validation. They may contain Unicode,
headings, prose, comments, SAN-looking words, and trailing HWS. There is no
general Markdown interpretation.

## 4. Block content, tags, and tokenization

### 4.1 Framing

Each block content is exactly:

1. one or more contiguous tag lines;
2. exactly one empty logical line containing zero bytes; and
3. one or more nonempty movetext lines.

No movetext line begins or ends with HWS, is HWS-only, or is empty. A second
empty line immediately after the required separator is
`SOURCE_SEPARATOR_EXTRA`; an empty line after movetext has begun is
`SOURCE_MOVETEXT_EMPTY_LINE`. A missing separator is zero-width at the start of
the first nonempty line where the empty line was required. Missing movetext is
zero-width at block-content end. Within one line, one or more HWS bytes separate
tokens. A newline separates the final token of one line from the first token of
the next. Wrapping has no other meaning. A line beginning with `[` after the
separator is `SOURCE_MOVETEXT_TAG_LINE`; tag syntax never resumes.

### 4.2 Tag line

A tag line is byte-for-byte:

```text
"[" name SP "\"" raw_value "\"" "]"
name      = ASCII_LETTER (ASCII_LETTER | ASCII_DIGIT | "_")*
raw_value = UTF-8 bytes other than an unescaped quote or backslash
escape    = "\\\"" | "\\\\"
```

There is exactly one SP between name and opening quote and no other outer HWS.
Only quote and backslash escapes are accepted. Escapes decode to that literal
character; no control, Unicode, numeric, or other escape exists. Decoded names
are case-sensitive and unique. The first content line must begin with `[` and
be a valid tag. If it is absent or does not begin with `[`,
`SOURCE_TAG_SYNTAX` uses a zero-width span at block-content start or the whole
offending line respectively. After at least one valid tag, successive lines
beginning with `[` remain in the tag run; a first line not beginning with `[`
ends that run without consuming it. A malformed `[`-starting line is
`SOURCE_TAG_SYNTAX`; the framing stage diagnoses a nonempty would-be separator.

Exact names `SetUp`, `FEN`, and `Variant` reject. Exact `Result` is required
once and is the only semantic tag. Its decoded value is exactly `1-0`, `0-1`,
or `1/2-1/2`. Every other syntactically valid tag name/value is opaque,
including `PlyCount`, `CriticalFEN`, `FinalFEN`, and `CriticalMove`.

Opaque metadata may affect raw identity and diagnostic spans only. It is never
parsed as a date, integer, move, position, count, instruction, path, or result.
Comments are not a construct inside a block.

### 4.3 Tokens and resource counting

Token spans are the maximal non-HWS bytes within a movetext line. Token count
includes move-number, SAN, and result-marker tokens.

Before structural or chess interpretation, `potential_ply_count` is the count
of tokens that are neither an ASCII-decimal token ending in one dot nor one of
the three valid result markers. For a valid record it equals accepted plies.
The per-record and total ply resource checks use this conservative count. This
keeps invalid-token floods bounded without needing error recovery or allocating
a parse tree. `*` is a potential ply token until stage 6 rejects it.

## 5. Movetext structure

The accepted token sequence is:

```text
1. WhiteSAN [BlackSAN] 2. WhiteSAN [BlackSAN] ... Result
```

The deterministic structural state starts expecting move number 1:

1. A move-number token is one or more ASCII digits followed by exactly one dot.
   Its integer has no leading zero, fits `u32`, and equals the expected number.
2. The next token occupies a first-side SAN slot. A result marker here rejects.
3. After that SAN, either the result marker ends the record or the next token
   occupies a second-side SAN slot.
4. After a second-side SAN, either the result marker ends the record or the next
   token must be the incremented move number.
5. At least one SAN slot must be occupied. The final marker must equal the
   decoded Result tag. Any later token rejects.

The three valid result markers are exactly `1-0`, `0-1`, and `1/2-1/2`. `*`,
ellipsis starts, attached move numbers, leading-zero numbers, null moves,
comments, semicolon comments, `%` escape lines, recursive variations, NAGs,
annotation suffixes, and tokens after a marker reject. A main line means this
one variation-free logical token stream, not one physical line.

## 6. Project SAN and replay

### 6.1 Closed SAN spelling

The source token consists of one canonical stem and one exact suffix:

- pawn quiet: destination plus mandatory promotion when applicable;
- pawn capture: origin file, lowercase `x`, destination, plus mandatory
  promotion;
- piece move: uppercase `K`, `Q`, `R`, `B`, or `N`, minimum legal-mover
  disambiguation, `x` exactly for capture, destination;
- castle: uppercase-letter `O-O` or `O-O-O`; and
- suffix: absent for no check, `+` for check without mate, `#` for checkmate.

Squares use lowercase file and ASCII rank. Promotion is exactly `=Q`, `=R`,
`=B`, or `=N`. Kings have no disambiguation. `0-0`, `e.p.`, `++`, LAN/UCI,
lowercase pieces, missing/extra capture marker, omitted/redundant
disambiguation, omitted/incorrect suffix, and repair variants reject.

This is Golden Board project SAN, not FIDE Appendix C and not a promise to
accept all historical PGN SAN.

### 6.2 Minimum legal-mover disambiguation

For a non-pawn, non-king piece move, collect all legal same-side, same-kind
moves to the destination before source disambiguation. If exactly one candidate
exists, canonical disambiguation is empty. If two or more exist:

1. origin file when no other candidate shares that file;
2. else origin rank when no other candidate shares that rank;
3. else complete origin square.

Pinned pseudo-movers do not participate. A king never disambiguates. Pawn
captures always carry their origin file; pawn quiet moves carry none.

### 6.3 Resolution

For each structurally assigned SAN slot, a bounded shape parser extracts piece
kind, supplied disambiguation, capture flag, destination, promotion, and
suffix. It accepts only byte shapes that could be a spelling from Section 6.1;
it does not repair or normalize.

From the current GameState, enumerate sorted legal moves. Match piece kind,
destination, promotion, and supplied origin restriction; capture spelling is
checked during canonical comparison rather than used to invent legality. Zero
matches is `SOURCE_SAN_NO_MATCH`; more than one is
`SOURCE_SAN_AMBIGUOUS`. For one match, generate its exact canonical stem from
the legal set and compare bytes. Any difference is
`SOURCE_SAN_NONCANONICAL`.

Apply the unique move through `apply_event(game, move(move))`. From the resulting
state, suffix truth is:

```text
SUFFIX_NONE   when the next side is not checked
SUFFIX_CHECK  when checked and board terminal is not checkmate
SUFFIX_MATE   when board terminal is checkmate
```

The token suffix must be exactly the corresponding absent/`+`/`#` spelling.
The suffix code's numeric value belongs to the constants owner.

### 6.4 Reachable semantic scan and atomicity

Before interpreting a non-result token, if the current GameState is closed,
the token rejects `SOURCE_GAME_AFTER_TERMINAL`. This includes a move-number
token after a terminal second-side move. A result marker immediately after the
terminal move remains valid and is checked against the final board.

Shape, no-match, and ambiguity stop semantic replay of that record because
later state is unknowable. A canonical-stem or suffix mismatch does not change
the already unique move, so validation continues on a provisional copy to find
any higher-precedence terminal-continuation defect. No row is committed until
its complete stem, transition, and suffix pass, and no CompiledGame is returned
until marker, Result tag, terminal score, and every row pass.

Each block starts from `new_game`. A trace row is exactly:

```text
[raw_start, raw_end, move_u16_hex, post_position_bytes_hex, suffix_truth_code]
```

The raw span covers the complete SAN token including suffix. Move hex is four
lowercase hexadecimal characters. Position hex is 134 lowercase hexadecimal
characters. Pre-position is the prior row's post-position or the standard
initial Position for the first row.

### 6.5 Final score

After complete replay, call `validate_source_record` on the resolved Moves and
Result-derived Score. Checkmate requires its winner's score. Stalemate and
selected common-dead require draw. A legal nonterminal board permits any of the
three concluded scores without an inferred cause. Threefold/50-move
availability does not constrain the score.

## 7. Game records and canonical set

### 7.1 One game

Canonical GameBytes are:

```text
u16_be(ply_count) || ply_count * encode_move(move) || u8(score_code)
```

`1 <= ply_count <= 4,096`. The byte length is exactly
`2 + 2 * ply_count + 1`. `decode_game` uses this exact pipeline: fewer than two
bytes is `SOURCE_GAME_TRUNCATED` at EOF; otherwise count outside `1..4,096` is
`SOURCE_GAME_COUNT` over bytes 0..2; checked expected-length arithmetic follows;
a shorter body is `SOURCE_GAME_TRUNCATED` at EOF; each Move then decodes in
order, then Score, then the first trailing byte, then semantic replay and score
relation. These map respectively to `SOURCE_GAME_MOVE`, `SOURCE_GAME_SCORE`,
`SOURCE_GAME_TRAILING`, and `SOURCE_GAME_SEMANTIC` with the spans in Section
8.2. `encode_game` accepts only an opaque, already valid GameRecord. Its length
is therefore bounded and its checked length arithmetic cannot fail; it emits
GameBytes without a rejection branch.

### 7.2 General game-set container

Canonical GameSetBytes are:

```text
u16_be(game_count) || sorted_game_0 || ... || sorted_game_(game_count - 1)
```

The general `encode_game_set` accepts `1..65,535` already valid GameRecords,
requires their complete GameBytes to be unique, sorts those bytes by unsigned
lexicographic order, and emits them without a per-game length wrapper because
each leading ply count is self-delimiting. `decode_game_set` requires the same
count range, complete canonical sort, exact-record uniqueness, no trailing
bytes, and validates each game. At adjacent records, a later record bytewise
less than its predecessor is an order error and equality is a duplicate error;
thus those cases do not overlap.
Both operations require the sum of all declared ply counts to be at most
65,535, checked while reading counts and before collection, sorting, allocation,
or output. With the count and total-ply bounds, the maximum container is 327,677
bytes. Implementations may stream the already length-checked output instead of
retaining two copies.

This general operation deliberately permits a one-game identity vector. It
does not weaken the anthology profile.

### 7.3 Anthology profile

`compile_source` requires exactly 64 valid blocks and rejects any two records
with identical complete Move byte streams, whether their Scores match or
differ. It compares full move bytes, never hashes. Only after all records and
duplicate checks pass does it:

1. construct each complete GameBytes;
2. sort by complete GameBytes;
3. assign canonical ordinals `0..63` by sorted position; and
4. emit `u16_be(64)` plus sorted records atomically.

Source ordinal remains the physical valid-block order `0..63` for audit only.
It never enters GameBytes, set sorting, identities, or canonical ordinals.
Suffix spelling, whitespace, metadata, raw path, filename, and raw source hash
also never enter GameBytes or GameSetBytes.

## 8. Rejection codes and total precedence

### 8.1 Raw compilation stages

The constants owner assigns nonzero `u16` values in the order below. Within a
stage the Section 2.3 raw-position rule applies. A later stage is considered
only when every earlier stage is clean. Resource defects are in the stage that
first has enough bounded information to compute them.

**Stage 1 — raw input size**

```text
SOURCE_INPUT_TOO_LARGE
```

**Stage 2 — UTF-8, BOM, controls, and newlines**

```text
SOURCE_UTF8_BOM
SOURCE_UTF8_INVALID
SOURCE_CONTROL
SOURCE_NEWLINE_BARE_CR
SOURCE_NEWLINE_MIXED
SOURCE_NEWLINE_FINAL_MISSING
```

**Stage 3 — fences and block byte/count resources**

```text
SOURCE_FENCE_SHAPE
SOURCE_FENCE_ORPHAN_CLOSE
SOURCE_FENCE_NESTED_OPEN
SOURCE_FENCE_UNCLOSED
SOURCE_FENCE_BLOCK_BYTES
SOURCE_FENCE_COUNT
```

For more than 64 pairs, count points at the 65th opener. For fewer, it is
zero-width at EOF. Block-bytes points at the first byte beyond 65,535 measured
from the opener.

**Stage 4 — tags**

```text
SOURCE_TAG_COUNT
SOURCE_TAG_NAME_LENGTH
SOURCE_TAG_VALUE_LENGTH
SOURCE_TAG_SYNTAX
SOURCE_TAG_ESCAPE
SOURCE_TAG_DUPLICATE
SOURCE_TAG_FORBIDDEN
SOURCE_TAG_RESULT_MISSING
SOURCE_TAG_RESULT_VALUE
```

Tag-count points at line 65. Name/value length points at its first excess byte.
When no Result appeared in an otherwise valid tag run, the missing span is
zero-width at the separator start.

**Stage 5 — block framing and token/ply resources**

```text
SOURCE_SEPARATOR_MISSING
SOURCE_SEPARATOR_EXTRA
SOURCE_MOVETEXT_MISSING
SOURCE_MOVETEXT_EMPTY_LINE
SOURCE_MOVETEXT_TAG_LINE
SOURCE_MOVETEXT_LEADING_HWS
SOURCE_MOVETEXT_TRAILING_HWS
SOURCE_RESOURCE_TOKEN_COUNT
SOURCE_RESOURCE_RECORD_PLIES
SOURCE_RESOURCE_TOTAL_PLIES
```

The first excess token/potential-ply span wins. Total-ply counting follows
source ordinal and token order and stops at the first excess token.

**Stage 6 — move numbers and results**

```text
SOURCE_MOVE_NUMBER_SHAPE
SOURCE_MOVE_NUMBER_VALUE
SOURCE_MOVE_NUMBER_POSITION
SOURCE_RESULT_TOO_EARLY
SOURCE_RESULT_TOKEN
SOURCE_RESULT_MISSING
SOURCE_RESULT_MISMATCH
SOURCE_TOKEN_AFTER_RESULT
```

When a move number is required, a token other than `*` or a valid result marker
that is not ASCII digits plus exactly one dot is shape. Value covers leading
zero, `u32` overflow, or a number different from the expected value. Any token
having the digits-plus-dot shape in a SAN slot is position, without interpreting
its value. `SOURCE_RESULT_TOKEN` covers `*` in every structural state. A valid
result before the first SAN, or in a required first-side SAN slot, is too early;
after either SAN it closes the record. Missing marker, including EOF directly
after a move number, is zero-width at the last movetext line end. Mismatch covers
the marker; token-after-result covers the first later token.

**Stage 7 — reachable terminal continuation**

```text
SOURCE_GAME_AFTER_TERMINAL
```

Only a terminal state established by a fully resolved preceding prefix can
produce this code.

**Stage 8 — SAN shape and canonical stem**

```text
SOURCE_SAN_SHAPE
SOURCE_SAN_NO_MATCH
SOURCE_SAN_AMBIGUOUS
SOURCE_SAN_NONCANONICAL
```

**Stage 9 — exact suffix truth**

```text
SOURCE_SAN_SUFFIX
```

A present wrong suffix covers its suffix byte(s). A missing suffix uses a
zero-width span at token end.

**Stage 10 — terminal score**

```text
SOURCE_TERMINAL_SCORE
```

The span is the result marker. The noncanonical diagnostic may retain
`CHESS_RECORD_CHECKMATE_SCORE` or `CHESS_RECORD_DRAW_SCORE`, but only the source
code/span is compared.

**Stage 11 — cross-record duplicate move stream**

```text
SOURCE_DUPLICATE_MOVE_STREAM
```

Only otherwise valid records participate. The later source ordinal is primary;
its opener line is the span. An earlier ordinal may be attached only as
noncanonical context.

### 8.2 Binary game and set operations

For a byte decoder, spans index that byte input. For a typed encoder with no raw
input, aggregate failures use `[0,0)`. The list and prose order in this section
is the exact operation order except where the length prepasses below are stated
to run first. The first failing game/move in input order wins; embedded chess
decode/replay failures retain their chess meaning only in optional context and
map to the indicated source code.

```text
SOURCE_GAME_COUNT
SOURCE_GAME_TRUNCATED
SOURCE_GAME_MOVE
SOURCE_GAME_SCORE
SOURCE_GAME_TRAILING
SOURCE_GAME_SEMANTIC
SOURCE_GAME_SET_SIZE
SOURCE_GAME_SET_COUNT
SOURCE_GAME_SET_TRUNCATED
SOURCE_GAME_SET_TOTAL_PLIES
SOURCE_GAME_SET_ORDER
SOURCE_GAME_SET_DUPLICATE
SOURCE_GAME_SET_TRAILING
SOURCE_ANTHOLOGY_COUNT
SOURCE_ANTHOLOGY_DUPLICATE_STREAM
```

Game count is checked before length arithmetic. Truncated points at EOF; bad
Move/Score covers its exact bytes; trailing covers the first extra byte.
Semantic replay failure covers the first failing two-byte Move; terminal-score
contradiction covers the Score byte. Game-set byte input over 327,677 bytes is
rejected at the first excess byte before its count is read. Set count is then
checked before collecting games: fewer than two bytes is
`SOURCE_GAME_SET_TRUNCATED`, then a top-level count outside `1..65,535` is
`SOURCE_GAME_SET_COUNT`. A framing prepass processes game headers in order. A
missing header is `SOURCE_GAME_SET_TRUNCATED`; an embedded count outside
`1..4,096` is `SOURCE_GAME_COUNT` before any length arithmetic; the running
total is checked immediately after every valid count; and a missing body is
`SOURCE_GAME_SET_TRUNCATED`. The first count that makes the total exceed 65,535
gets `SOURCE_GAME_SET_TOTAL_PLIES` before its body is decoded or allocated.
Each game then follows the one-game order; sort/duplicate checks follow complete
decoding; trailing is last. Set order/duplicate covers the complete later
offending game span. `validate_anthology` uses `[0,0)` because its input is
typed; count precedes duplicate stream, and the lowest later input index wins
duplicate selection. During raw compilation that duplicate maps instead to the
later block opener and `SOURCE_DUPLICATE_MOVE_STREAM`.

### 8.3 Candidate/report operations

```text
SOURCE_EVIDENCE_SIZE
SOURCE_EVIDENCE_SHAPE
SOURCE_EVIDENCE_NONCANONICAL
SOURCE_EVIDENCE_HASH
SOURCE_EVIDENCE_CROSS_FIELD
SOURCE_CANDIDATE_MISMATCH
SOURCE_EVIDENCE_INSTALL
```

Manifest byte size is checked first. Invalid canonical-manifest syntax/data
model, closed fields, field types, fixed ranges, or lexical shapes (including
hex length/lowercase) are `SOURCE_EVIDENCE_SHAPE`. A syntactically parseable
value with an otherwise valid closed model whose canonical reserialization is
not byte-equal is `SOURCE_EVIDENCE_NONCANONICAL`. Only after both pass, a
well-shaped source/spec/constants digest that differs from EvidenceInputs is
`SOURCE_EVIDENCE_HASH`. A well-shaped derived byte, identity, count, ordinal,
row transition/span, Score, reconstructed GameBytes, or game-set relation that
does not recompute is `SOURCE_EVIDENCE_CROSS_FIELD`. Candidate mismatch follows
two individually valid candidates. Install is a host-adapter I/O failure and
never converts an uninstalled candidate into accepted evidence.

When `validate_candidate_trace` or `validate_retained_evidence` receives
supplied CandidateBytes/ReportBytes over the manifest limit, evidence size
covers that input's first excess byte. An output overflow while
`encode_candidate_trace` or `coordinate_candidates` operates on typed values
has no raw byte input and uses `[0,0)`. Every other evidence-stage code also
uses `[0,0)`; this avoids making host JSON-parser offsets or a choice between
the two equal-role candidate inputs canonical.

## 9. Independent compilation boundary

Path P and Path R each:

- read the locked regular source through its own safe host path;
- scan all raw bytes directly with its own newline/fence/tag/token/SAN state
  machines;
- call only its own chess core;
- construct all rows, GameRecords, candidate trace bytes, and GameSetBytes; and
- fail before exposing any accepted candidate if one stage fails.

They may share only owning specifications, numeric constants, identity
framing, and reviewed hand-authored fixtures. They may not share a normalized
source copy, source-doctor recognition, lexer output, parse tree, token stream,
SAN encoder/resolver, legal-move core, trace, generated expected result,
GameRecord, candidate, or one lane's output as the other's expectation.

The M0 source doctor remains a parallel lexical/source-lock observation. A
development chess library is diagnostic after project parsing; it cannot
broaden grammar or supply expected rows.

## 10. Candidate trace and retained report

### 10.1 Canonical candidate manifest

Each lane independently serializes one canonical-manifest-v0 candidate. The top
object has exactly these keys:

```text
constants_sha256
game_count
game_set_identity
games
initial_position_bytes
initial_position_identity
ir_bytes
ply_count
schema
score_counts
source_sha256
spec_sha256
```

`schema` is exactly `golden-board-source-candidate-v0`. `spec_sha256` is an
object with exactly `chess_v0`, `identity_v0`, and `source_v0`. One `games`
entry has exactly `game_identity`, `rows`, `score`, and `source_ordinal`.

- Every digest/identity is 64 lowercase hexadecimal characters.
- `initial_position_bytes` is 134 lowercase hexadecimal characters and is the
  chess-v0 standard initial Position.
- `game_count` is 64.
- `source_ordinal` values are the unique ascending sequence `0..63`; games are
  stored in that source order.
- `score` is the constants-owned u8 Score code.
- `rows` are the fixed five-element arrays in Section 6.4, in ply order.
- `score_counts` is three unsigned integers ordered first-side win,
  second-side win, draw and sums to 64.
- `ply_count` is the sum of row counts.
- `ir_bytes` is `sum(2 + 2 * len(rows) + 1)` and excludes the set's leading
  count.

There is no producer label, agreement flag, other producer hash, self-hash,
trace identity, timestamp, host/path/temp name, or free-form message in a
candidate.

Validation recomputes every field from the supplied EvidenceInputs, rows, and
GameSetBytes: source/spec/constants hashes; initial bytes/identity; raw row
spans and source-token bytes; pre/post transitions; suffix truth; row totals;
Scores/counts; every reconstructed GameBytes/game identity; IR size; sorted set
bytes; and game-set identity. Hash equality never substitutes for byte
equality.

### 10.2 Coordinator and retained report

The coordinator accepts candidates only after validating each independently
against the same EvidenceInputs and its own GameSetBytes. It then requires:

1. candidate manifest bytes are exactly equal, thereby comparing every trace
   row and fact byte;
2. GameSetBytes are exactly equal; and
3. the equality is rechecked after opening the staged files and before output.

Only the coordinator constructs the retained canonical-manifest-v0 report. It
copies the agreed candidate facts, changes `schema` to exactly
`golden-board-source-compilation-v0`, and adds the one exact top-level field:

```text
producer_labels = ["python", "rust"]
```

The retained top object therefore has the candidate's exact keys plus
`producer_labels`, and no other key. Fixed labels record which required lanes
were compared; they are not producer-supplied self-attestation. There is no
`agreed`, `verified`, candidate hash, self-hash, or trace identity field.

The coordinator canonicalizes, validates every retained cross-field rule again,
and returns report plus agreed set. Normal checks compare candidates/current
tracked evidence and never install. An explicit generation command writes
sibling temporary regular files on the destination filesystem, validates and
fsyncs them, installs the game set, then atomically replaces the retained report
as the final commit marker. It never exposes a partial report. An interruption
before report replacement preserves the prior report bytes; readers validate
the report and set together and fail closed if an interrupted set replacement
does not match that prior report. A rerun repairs that bounded state.

The only retained paths are `reports/game-set-v0.bin` and
`reports/source-compilation-v0.json`. Producer candidates and staging files are
ignored artifacts and never alternate accepted reports.

The retained report is at most 1,048,576 bytes including final LF. If the
closed row form exceeds the limit, M1 remains open and the owning spec must be
revised to remove duplicated presentation data; raising the cap or dropping
per-ply equality is not an implementation workaround.

## 11. Metadata noninterference

For a valid source or fixture, these independent grammar-preserving changes may
alter raw identity, spans, and source ordinal but must preserve each GameBytes,
game identity, sorted GameSetBytes, canonical ordinal, and game-set identity:

- change every opaque tag value, including plausible FEN/count/move metadata;
- add, remove, or reorder opaque tags within bounds while retaining Result;
- change player/event/date-like names and values;
- rewrite outer prose/comments or outer trailing HWS;
- convert every newline uniformly between LF and CRLF;
- rewrap tokens or change one-or-more HWS separators within the accepted form;
- change the safe source filename/containing path; and
- permute complete fence blocks.

The report trace and source hash are expected to change where raw spans/order or
bytes change. In-fence comments, mixed newlines, malformed whitespace,
alternate starts, a changed Result, or another rejected form are negative
grammar cases, not noninterference promises.

## 12. Required evidence

`conformance/source-v0.json` is the portable shared fixture. It owns exact
raw-byte and typed-operation cases through `SOURCE_EVIDENCE_CROSS_FIELD`.
`SOURCE_CANDIDATE_MISMATCH` is P5 coordinator evidence constructed only after
two individually valid candidates. `SOURCE_EVIDENCE_INSTALL` is language-local
host-adapter failure and interruption evidence. Neither latter case is a
portable shared-fixture input; both retain the owner-defined canonical span
`[0,0)`.

Hand-authored portable fixtures cover exact raw-byte or typed-operation inputs
and expected code/span for every rejection through
`SOURCE_EVIDENCE_CROSS_FIELD`, including:

- UTF-8 invalid lead, invalid continuation, overlong/surrogate/out-of-range,
  multibyte valid prefix, truncated EOF, BOM, controls, bare CR, mixed newline,
  and missing final newline;
- fence shape/orphan/nested/unclosed/count and 65,535/65,536 block bytes;
- tag syntax/escape/duplicates/forbidden/Result and every tag bound;
- separator/movetext/HWS/token/ply limits and boundary plus one;
- move numbers, half-move final marker, mismatch, `*`, and trailing token;
- canonical no-check/check/mate SAN, every suffix mismatch, pinned legal-mover
  disambiguation, exactly-one/no-disambiguation, required file/rank/full origin,
  redundant disambiguation, castling, en passant resolution, and all
  promotions;
- valid token after checkmate, stalemate, and selected common-dead;
- terminal score contradictions and arbitrary nonterminal scores;
- same move stream with same and different Score;
- unclosed-at-EOF versus block-size/count precedence; and
- game/set/report truncation, trailing data, sort, each evidence
  shape/noncanonical/hash/cross-field partition.

Large boundary inputs are deterministic hand-reviewed recipes; expected
codes/spans/bytes/digests are committed literals, not generated from either
production compiler. Later semantic cases may patch raw spans in a locked valid
base fixture, but the patch recipe itself is bounded and reviewed.

The locked source acceptance requires 64 records and complete equality of both
candidate manifests and game sets. Current reconnaissance counts and opaque
metadata are diagnostic observations, never hard-coded semantic expected
answers. A disagreement between lanes or with the diagnostic oracle blocks M1
until the smallest owning spec or implementation defect is resolved.
