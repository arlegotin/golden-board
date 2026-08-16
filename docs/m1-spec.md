# M1 chess truth, source grammar, and assessment blueprint specification

| Field | Value |
|---|---|
| Status | Ready for execution |
| Date | 2026-08-14 |
| Roadmap | Revision 5, M1 |
| Branch | `m1` |
| Baseline | `5d0acbd` (`M0 (#3)`) |
| Scope | Chess truth, raw-source compilation, assessment blueprint, and the initial M2 content slice |

## 1. Purpose and authority

This document is the executable design for M1. It turns Sections 4–6 and the
M1 gate in [`docs/roadmap.md`](roadmap.md) into a bounded implementation
contract. It is deliberately a specification, not a brittle file-by-file coding
script. An implementing agent may reorder work, choose private module layouts,
and use smaller equivalent helpers when the observable contracts and
independence boundaries below remain intact.

Authority remains simple:

1. the roadmap owns product scope, milestone order, gate wording, and status;
2. this document owns the M1 execution design and the temporary draft choices
   below until each owning M1 specification exists;
3. `spec/identity-v0.md`, `spec/chess-v0.md`, `spec/source-v0.md`,
   `spec/content-v0.md`, and `spec/curriculum-v0.toml` become the sole owners of
   their respective wire/semantic facts as they land;
4. the machine-readable constants file owns shared numeric assignments while
   each chess/source/content/curriculum specification owns its codes' meanings;
   and
5. fixtures, implementations, external libraries, generated reports, and this
   document's research observations prove or motivate contracts but never
   silently redefine them.

If this document and the roadmap disagree, repair the smallest owning roadmap
rule first. If two owning specifications disagree, stop affected implementation
until one owner is made unambiguous. Never adjust an expected vector, source
grammar, learner denominator, or pass threshold merely to obtain a pass.

M1 is now `In progress` because its first executable repository deliverable has
landed. This design document does not complete it. M1 moves to `Complete` only
when every M1 deliverable/checklist item and all G2–G4 evidence below pass.

## 2. Evidence behind the design

### 2.1 Repository baseline

M0 is complete on branch `m1` at commit `5d0acbd`. The repository already has:

- a byte-locked anthology and external-reference ledger;
- a bounded, path-safe observational source doctor;
- independently implemented developer identity framing and canonical manifests;
- Python and Rust foundations with locked project-local dependencies;
- registered hand-authored conformance fixtures; and
- real `fast`, focused, and full root checks.

M1 reuses those trust-boundary and identity primitives. It does **not** reuse
the M0 doctor's fence, tag, or token recognition in either production compiler:
the doctor was intentionally observational and its findings are not a parse
tree.

Four existing repository assumptions must be repaired as ordinary M1 setup:

1. the M0 repository test currently rejects future `spec/chess-v0.md` and
   `spec/source-v0.md` files;
2. `scripts/check` checks whitespace only for an M0-era hard-coded file list;
3. `focused identity` should remain scoped to its owning Rust package once new
   crates or modules exist; and
4. each direct conformance payload must be registered, while oracle-only or
   generated scratch material must not masquerade as a shared hand-authored
   suite.

Those are small extensions of the existing foundation, not reasons to build a
new test runner, workspace framework, or manifest system.

### 2.2 Locked anthology facts

The authoritative input remains `docs/64_games.md`:

| Property | M0 observation |
|---|---:|
| Bytes | 165,145 |
| SHA-256 | `33d44f7167ab190cc793e3fdfd8190d89ed13c1dc507c20854cf64751c7be7da` |
| Encoding/newline | strict UTF-8, no BOM, 4,376 LF, final LF |
| Exact `pgn` blocks | 64 |
| Recognized tag lines | 895 across 21 names and 7 orders |
| Movetext tokens | 7,456 |
| SAN-shaped plies | 4,915, range 33–271 per record |
| Lexical results | 39 first-side wins, 22 second-side wins, 3 draws |
| Special shapes | 110 castlings, 5 promotions, 358 `+`, 5 `#` |
| Disambiguation shapes | 161 file, 18 rank, 0 full-square |
| Lexical duplicate projections | 0 |

These are reconnaissance facts, not expected chess output. In particular,
`CriticalFEN`, `FinalFEN`, `PlyCount`, `CriticalMove`, player/event data, and all
tags except exact `Result` are semantically opaque. M1 must deliberately mutate
apparently useful metadata to prove it is not acting as a hidden oracle.

A disposable, pinned python-chess 1.11.2 probe performed during this design pass
accepted all 64 records from the standard start and observed:

- 4,915 legal plies and 10,022 bytes under the proposed minimal game-IR formula;
- 110 castlings, 5 actual en-passant captures, and 5 queen promotions;
- 5 checkmate endings and no stalemate or selected common-dead ending;
- exact agreement between every one of the 4,915 source SAN tokens and the
  oracle's generated SAN, including all 363 check/mate suffixes;
- agreement of the opaque `PlyCount` and `FinalFEN` metadata with that library;
  and
- no duplicate move stream or complete minimal game key.

This probe is planning evidence only. It cannot close G2 or G3, supply tracked
expected bytes, broaden source acceptance, or resolve a disagreement between
the two project implementations.

### 2.3 Governing chess and notation references

The byte-locked FIDE Laws PDF effective 2023-01-01 remains the governing chess
source recorded by M0. The [official FIDE handbook entry](https://handbook.fide.com/chapter/E012023)
was still the current Laws entry when this design was checked. Profile v0
selects ordinary board rules while explicitly omitting tournament procedure.
One roadmap correction follows directly from Article 5.2.3: draw agreement is
available only after both players have made at least one move.

The 1994 [PGN specification and implementation guide](https://www.saremba.de/chessgml/standards/pgn/pgn-complete.htm)
is useful historical background for SAN structure, legal-mover disambiguation,
and result markers. It is not a maintained standards authority and it does not
own Golden Board's deliberately narrower source grammar. FIDE Appendix C also
does not define this project's SAN: it permits notation variants that M1 must
reject.

The limited `common_dead` classes stay limited. A general material shortcut is
not a sound replacement for the substantially harder unwinnability question;
[Ambrona 2022](https://doi.org/10.4230/LIPIcs.FUN.2022.2) provides useful
background. M1 implements only the three roadmap-named classes and returns no
invented answer for broader cases.

### 2.4 Assessment and learning research

The curriculum design uses research as guardrails, not as borrowed proof of
Golden Board's effectiveness:

- worked examples, explicit principles, and faded prompts are appropriate for
  novices ([Sweller and Cooper 1985](https://doi.org/10.1207/s1532690xci0201_3),
  [Atkinson, Renkl, and Merrill 2003](https://doi.org/10.1037/0022-0663.95.4.774));
- bounded reason selection is a workable artifact-native analogue of prompting
  explanation, without pretending to assess free-form prose
  ([Chi et al. 1989](https://doi.org/10.1207/s15516709cog1302_1));
- tests and even unsuccessful pretests can change later learning, while feedback
  changes retrieval effects ([Roediger and Karpicke 2006](https://doi.org/10.1111/j.1467-9280.2006.01693.x),
  [Richland, Kornell, and Kao 2009](https://doi.org/10.1037/a0016496),
  [Butler and Roediger 2008](https://doi.org/10.3758/MC.36.3.604)); and
- assessment interpretations must match the tested domain and population, and
  superficial response cues threaten validity
  ([AERA/APA/NCME Standards](https://www.testingstandards.net/uploads/7/6/6/4/76643089/standards_2014edition.pdf),
  [NBME item-writing guide](https://www.nbme.org/sites/default/files/2021-02/NBME_Item%20Writing%20Guide_R_6.pdf)).

Accordingly, M1 uses blueprint-matched held-out forms, withholds result-bearing
feedback through the delayed window, audits simple cue strategies, and makes a
narrow descriptive six-person claim. It does not add a control group,
significance tests, item-response modelling, formal equating, or psychometric
infrastructure that this pet project cannot support.

### 2.5 Why the roadmap gate changed

The former requirement that one common subset clear every family was
multiplicatively brittle. As a structural sensitivity check—not a model of real
learners—consider 12 families with two exact items each and 95% independent
item accuracy. One learner clears all 24 with probability `0.95^24 = 0.292`;
the probability that at least the same five of six do so is about `0.00964`.
Even at 98% item accuracy it is only about `0.259`.

The gate introduced in revision 3 and retained through revision 5 preserves strict
all-or-nothing family scoring but combines:

- per-family cohort gates, which expose systematic topic holes;
- baseline-failure acquisition gates, which exclude prior mastery; and
- broad per-person gates, which expose fragmented learning.

It removes the accidental cross-family perfection intersection and permits one
miss among the three-to-six baseline-deficient learners in a family. The latter
closes a small-cohort cliff: `ceil75(3)` required 3/3 acquisitions; with two-item
family passes and 95% independent item accuracy, clearing that condition across
11 families is only about 3.39%. The frozen `b-1` rule yields 2/3, 3/4, 4/5,
or 5/6 while the separate 5/6 or 4/6 attainment gate still exposes weak
families. These are pre-exposure validity repairs, not changes in response to
participant results; no final learner has been exposed.

## 3. M1 outcome, scope, and deferrals

### 3.1 Required outcome

M1 closes only when the repository can demonstrate all of the following from
frozen inputs:

1. Python and Rust independently implement the same bounded practical chess
   semantics and exact scored predicate truth (G2).
2. Independent Python and Rust raw-byte compilers accept the locked anthology,
   resolve every canonical SAN token through their own legal-move cores, and
   produce the same per-ply trace, 64 minimal game records, scores, ordering, and
   identities (G3).
3. Metadata, accepted line-ending form, source path, and source block order do
   not influence individual game bytes or the sorted semantic set, while any
   grammar or semantic defect rejects deterministically (G4).
4. The curriculum blueprint fixes what later human evidence means before broad
   lesson authoring.
5. The initial generic content grammar is sufficient for the actual M2
   bootstrap/learner slice without becoming a general object format or VM.

### 3.2 In scope

- exact semantic bytes, codes, identities, chess APIs, state transitions, and
  rejection precedence;
- independently written chess cores and source compilers;
- hand vectors, bounded generated properties, metamorphic cases, named mutants,
  and an isolated development oracle;
- exact Markdown/tag/movetext/SAN source grammar and raw error spans;
- minimal game IR, duplicate policy, sorted game set, compact dual-path audit,
  and actual size/score report;
- exact predicate definitions needed by the M1 blueprint;
- essential Core 1/2 and retained Core 3 families, strata, splits, cue controls,
  scoring, feedback policy, and cohort gates; and
- only the generic records that M2's real slice consumes.

### 3.3 Explicitly deferred

M1 does not implement or freeze:

- shell notation, transport, correction, damage placement, physical mapping,
  side length, or final record-family maxima (M2/M4);
- the complete authored curriculum, full lesson graphs, packed accepted sets,
  final predicate registry bindings, or all 64 content records (M3);
- concrete final human-assessment payloads, schedules, answer maps, or usable
  private seeds (M4, evaluator-only until delayed testing closes);
- final candidate bytes or participant evidence (M4/M5);
- a general dead-position solver, engine/evaluator, opponent, PGN implementation,
  serializer ecosystem, database, service, or web interface; or
- publication or redistribution of material whose rights are not established.

The local source may be compiled for M1 verification because it is already the
declared repository input. No push, publication, licensing conclusion, or
external distribution is implied by this design.

## 4. Selected architecture and rejected complexity

### 4.1 Selected shape

The smallest design that satisfies independence is:

```text
locked raw bytes
  -> Python lexer/SAN resolver -> Python chess core -> trace P -> game set P
  -> Rust lexer/SAN resolver   -> Rust chess core   -> trace R -> game set R

hand-authored spec vectors ------> both cores/compilers
development chess library --------> normalized diagnostic comparisons only
```

The two paths meet only at reviewed specifications, a tiny numeric constants
source, hand-authored fixtures, and the final equality check. Once their
normalized traces agree, one compact canonical trace is retained rather than
two copies of identical evidence.

### 4.2 Rejected alternatives

| Alternative | Why M1 does not use it |
|---|---|
| One shared parser/core with Python and Rust wrappers | It cannot expose independent misunderstandings and fails the roadmap boundary. |
| A mature chess or PGN library as production authority | Its accepted grammar, FEN/en-passant defaults, terminal profile, and permissive calls do not match project semantics. |
| One compiler consuming the other compiler's tokens or IR | Agreement would be circular rather than evidence. |
| Full PGN, FEN starts, comments, RAVs, NAGs, repair mode | None is needed by the locked source; each widens ambiguity and test surface. |
| CBOR, Protocol Buffers, generic JSON content, or a VM | Their unused features and dependencies add bootstrap work; a flat definite-length record grammar is enough. |
| A mutation-testing/property framework | Named test-only mutants and bounded deterministic generators close the actual risks without another toolchain. |
| Two verbose retained per-ply reports | A single compact agreed trace proves the same fact and stays under M0's 1 MiB manifest cap. |
| Population statistics or formal test equating | Six purposively screened learners support only bounded descriptive product evidence. |

python-chess may be pinned as an isolated development dependency because it has
a live diagnostic consumer. It must not enter runtime, source parsing,
canonical serialization, expected fixtures, the generic transducer, or release
bytes. Its permissive `parse_san`, non-validating `push`, default FEN en-passant
normalization, and extra automatic draw outcomes are specifically outside the
comparison surface; see its [core API documentation](https://python-chess.readthedocs.io/en/latest/core.html).

## 5. Normative owners and minimum artifact surface

### 5.1 One owner per fact

| Owner | Sole normative responsibility after M1 |
|---|---|
| `docs/roadmap.md` | Mission, scope, milestone/gate order/intent, cohort size, protocol timing, bounded claim, status |
| `docs/m1-spec.md` | M1 execution envelope and rationale only |
| `docs/m1-plan.md` | Nonnormative dependency order, work packets, and review checkpoints |
| `spec/identity-v0.md` | Developer hash framing and registered product domains |
| neutral constants source | Numeric codes shared across languages |
| `spec/chess-v0.md` | Semantic bytes, chess truth, APIs, predicates, transitions, rejection precedence |
| `spec/source-v0.md` | Raw Markdown/tag/token/SAN grammar, spans, compiler errors, game IR |
| `spec/content-v0.md` | Generic stream/record/interaction bytes and state machine |
| `spec/curriculum-v0.toml` | Family/stratum/split IDs, predicate references, item/family scoring, executable gate formulas/constants, cue rules, caps, cut order |
| generated source audit/game set | Evidence and canonical output, never rules |
| later private assessment manifest | Concrete cases, seeds, schedules, accepted sets, answer hashes |
| reports/logs | Reproducible observations only |

The curriculum references stable predicate and error IDs from the chess/content
specifications. It never copies chess formulas. M3 may add the authored registry
that binds records to those IDs, but it may not reinterpret predicate truth.
The roadmap owns cohort/screening, eligibility/selection, timing, denominator,
feedback, help, interruption, privacy/reveal, and claim-ceiling protocol. Any
such field in the curriculum TOML is a checked roadmap mirror, not a second
protocol owner. This design states the gates for human review; a generated check
must reject drift from either owning source.

### 5.2 Required artifacts

M1 should add only artifacts with an immediate check or consumer:

- `spec/chess-v0.md`;
- one canonical machine-readable chess/content constants source and generated
  Python/Rust constants;
- `spec/source-v0.md`;
- `spec/curriculum-v0.toml`;
- the initial `spec/content-v0.md`;
- independent minimal Python/Rust content decoders/validators plus hand-authored
  generic interaction fixtures (not the M2/M3 transducer);
- the four new domains and vectors in `spec/identity-v0.md`/conformance data;
- small hand-authored chess and source conformance payloads, registered only
  after they exist;
- Python and Rust chess/source modules and their focused tests;
- one tracked canonical 64-game-set byte object; and
- one compact canonical source-compilation report with actual score/size facts.

The M1 change also updates `docs/sources.md` for references actually used and
updates README/AGENTS root-check snippets when the new focused areas become live.

Private package/crate/file names may follow the existing repository layout. One
module per language is acceptable until size or ownership gives a concrete
reason to split it. `docs/m1-plan.md` may sequence this approved design but never
owns bytes, gates, or private implementation shape. Do not add a framework,
empty registry slot, database, code-generation library, generalized CLI, or
decision log. A short decision entry is needed only if execution changes
roadmap-owned chess/source scope rather than implementing this design.

## 6. Canonical chess bytes and identity

Sections 6–10 retain the reviewed design rationale and evidence checklist. The
promoted [`spec/chess-v0.md`](../spec/chess-v0.md) is now the sole normative
owner of chess bytes, types, APIs, semantics, predicates, and rejection order;
[`spec/identity-v0.md`](../spec/identity-v0.md) owns identity framing/domains,
and `spec/constants-v0.toml` owns shared numeric assignments once it lands. Any
implementation detail or draft spelling below is a nonnormative synopsis and
does not override those smaller owners.

### 6.1 Primitive conventions

- all canonical integers are unsigned big-endian;
- square order is `a1,b1,...,h1,a2,...,h8` and square index is `0..63`;
- first side is White and code `0`; second side is Black and code `1`;
- bounds are checked before indexing, multiplication, allocation, or output;
- reserved bits/codes reject and are never masked or normalized; and
- no host enum layout, struct padding, FEN string, locale, or iteration order is
  canonical.

### 6.2 Position bytes

Canonical `Position` is exactly 67 bytes:

```text
64 × u8 square_code in a1..h8 order
u8 side_to_move
u8 castling_rights
u8 nominal_en_passant
```

Square codes are:

| Code | Meaning | Code | Meaning |
|---:|---|---:|---|
| 0 | empty | 7 | second-side pawn |
| 1 | first-side pawn | 8 | second-side knight |
| 2 | first-side knight | 9 | second-side bishop |
| 3 | first-side bishop | 10 | second-side rook |
| 4 | first-side rook | 11 | second-side queen |
| 5 | first-side queen | 12 | second-side king |
| 6 | first-side king | 13..255 | invalid |

Castling bits are `0 first kingside`, `1 first queenside`, `2 second
kingside`, and `3 second queenside`; high bits must be zero. A right means the
corresponding king and original rook have not moved and still occupy their home
squares. Rights disappear on the king move, that rook's move, or capture of the
entitled rook on its home square. They never return when another or promoted
rook reaches that square.

Nominal en-passant is `0` for none, otherwise `square_index + 1`. It records the
passed-over square after **every** legal double pawn push, even if no capture is
available. A locally admissible nonzero value requires the correct rank for the
side to move, an empty target, the opponent pawn on the just-reached square, and
the corresponding origin square empty. It does not require an adjacent
capturing pawn. Any move other than a double pawn push clears it.

The exact standard initial bytes are:

```text
0402030506030204010101010101010100000000000000000000000000000000
0000000000000000000000000000000007070707070707070a08090b0c09080a
000f00
```

The line wrapping above is presentation only. Concatenation is 67 bytes.

### 6.3 Move and result bytes

The roadmap's 16-bit move is unchanged:

```text
bits 15..10 origin square
bits  9..4  destination square
bits  3..1  promotion: 0 none, 1 Q, 2 R, 3 B, 4 N
bit      0  reserved zero
```

It is serialized as `u16_be`. Origin equals destination, promotion codes 5–7,
or a set reserved bit reject before board lookup. Castling is the king move;
en passant is the pawn move; all effects derive from state.

Minimal source scores are:

| Code | Meaning |
|---:|---|
| 0 | first-side win (`1-0`) |
| 1 | second-side win (`0-1`) |
| 2 | draw (`1/2-1/2`) |
| 3..255 | invalid |

Other event, status, predicate, role, feedback, and rejection codes are declared
once in the neutral constants source before either implementation consumes
them. `0` is reserved for `none`/`ok` only where the owning type has that value;
codes are explicit and append-only within v0. The generator rejects duplicate
numbers/names, holes not declared reserved, unknown fields, and generated-file
drift. It emits boring language constants; it does not generate algorithms or
types.

### 6.4 Repetition-key bytes

The repetition key uses the same 67-byte layout as `Position`, except the final
byte is zero unless at least one **fully legal** en-passant capture is available
to the side to move. A pseudo-capture that exposes that side's king does not
preserve the en-passant field in the key.

Thus two nominal positions may have different `Position` bytes but identical
repetition-key bytes. Halfmove clock, occurrence counts, played plies, game
status, record identity, score, and transport state never enter the key.

### 6.5 Identity domains

M1 extends `spec/identity-v0.md` with these literal domains:

```text
golden-board:position:v0\0
golden-board:repetition-key:v0\0
golden-board:game:v0\0
golden-board:game-set:v0\0
```

Each identity has exactly one framed byte field under the existing identity-v0
algorithm:

| Domain | Field bytes |
|---|---|
| position | exact 67-byte `Position` |
| repetition key | exact normalized 67-byte repetition key |
| game | `u16_be(ply_count) || moves || u8(score)` |
| game set | exact canonical game-set container below |

The initial-position identity is
`7d578698cdb2095a1b818234f12b3e6d4f19bbadb414887f26e6a8d52417a186`.
The initial repetition-key identity is
`b12da42c15cc340394688be5d771ad8936241e9dcb03592b2791e06b9dbe33e3`.
Both become independent hand vectors; implementations must not generate their
own expected digests at test time.

After duplicate rejection, canonical games sort lexicographically by complete
game bytes. The exact set container is:

```text
u16_be(game_count) || sorted_game_0 || ... || sorted_game_(count-1)
```

Each game is self-delimiting through its leading ply count and fixed move/score
width. The general source-v0 encoder accepts `1..65,535` unique valid records;
the Golden Board anthology object requires `game_count == 64`. No source
ordinal, length wrapper, metadata, filename, or raw source hash enters it. M1
does not invent a history-state identity because no M1 consumer needs one.

## 7. Chess validation layers and pure APIs

### 7.1 Validation layers

The implementation preserves the roadmap's four layers:

1. `WirePosition`: exactly 67 bytes and valid field codes/reserved bits.
2. `LocallyAdmissiblePosition`: exactly one king per side; kings nonadjacent;
   at most eight pawns and sixteen pieces per side; no pawn on rank 1/8; not
   both kings checked; side not to move not checked; coherent castling pieces;
   coherent nominal en-passant geometry.
3. `ReplayState`: an opaque, inseparable reached-`Position`/`HistoryState` pair
   produced only by bounded, closure-aware legal replay from the standard start.
4. artifact-bound input: verified content retains whether its input is a full
   `ReplayState` or only a locally admissible board-local diagram; candidate
   binding never upgrades that authority.

No constructor clears rights, removes a malformed en-passant target, repairs a
piece code, inserts a king, or upgrades a lower layer by assertion. Legal moves,
history/declaration/terminal predicates, source replay, and
stateful packed lessons accept only `ReplayState`. A locally admissible diagram
may be used only for explicitly board-local occupancy/control predicates; it
makes no reachability, legal-move, history, event, terminal, or source claim.

`GameState` is one opaque `ReplayState` plus active/closed status and, when
closed, the exact board-terminal or declaration cause and its derived result.
No public constructor accepts independently supplied position, history,
status, cause, or result fields.

### 7.2 Logical API

The exact closed operation list is owned by chess-v0: `decode_position`,
`encode_position`, `decode_move`, `encode_move`, `decode_event`, `encode_event`,
`validate_local`, `controls_square`, `king_in_check`, `pseudo_legal_moves`,
`replay_from_start`, `legal_moves`, `apply_move`, `repetition_key`,
`board_terminal`, `common_dead`, `new_game`, `apply_event`,
`validate_source_record`, and `evaluate_predicate`. Chess-v0 owns their exact
argument/result types and sorting.

`controls_square` is total over typed, structurally decoded occupancy and does
not need a unique king. `king_in_check` requires local admissibility because it
selects the side's unique king. All returned controller squares and legal/
pseudo-legal moves sort in ascending unsigned numeric encoding. No API consults
global mutable state, time, randomness, hash-map iteration order, source
metadata, or transport state.

`legal_moves(ReplayState)` returns the empty set when `board_terminal` is
checkmate, stalemate, or selected common-dead; an internal board-move generator
may be used to compute terminal truth but cannot authorize continuation.

Every rejection leaves caller-owned semantic state unchanged. Implementations
may use immutable values or transactional copies; observable partial mutation is
forbidden.

## 8. Exact chess semantics

### 8.1 Control, movement, and king safety

Control is capture geometry with blockers, not legal-move filtering:

- a pinned or otherwise constrained piece still controls according to its
  geometry;
- pawns control their two forward diagonals regardless of occupancy and never
  control forward;
- kings control adjacent squares, including a friendly-occupied target;
- knights ignore intervening occupancy;
- a slider controls through empty squares, includes the first occupied square,
  and stops there; and
- friendly occupancy may be controlled/defended but may not be captured.

Pseudo-legal generation enforces piece geometry, blockers, side to move,
friendly occupancy, pawn direction/double-step conditions, promotion context,
en-passant geometry, and only castling rights/pieces/path. Legal castling then
performs all three explicit origin/transit/destination checks in Section 8.2.
Every other move is legal only after its complete effects leave the moving
side's king uncontrolled. Capturing either king is never a move.

A king capture is checked on the fully applied candidate, including any slider
line opened by removing the captured piece. En passant removes the captured pawn
before king safety. These operation orders are normative, not implementation
optimizations.

### 8.2 Castling

Castling requires:

- the relevant right bit;
- king and entitled rook on their home squares;
- every square between them empty;
- the king not currently checked;
- the transit square not controlled in a probe with the king moved there, its
  origin empty, and the rook still on its original square; and
- the destination not controlled in the fully applied final position with the
  rook relocated.

The move is encoded only as king origin/destination. There is no alternate rook
move encoding. Moving the king or entitled rook clears rights even if it later
returns. Capturing an entitled home rook clears that side's corresponding bit.
No promoted or replacement rook revives a bit.

### 8.3 En passant

After a legal double pawn push, nominal en-passant stores the passed-over square
for exactly the opponent's next ply. A capture requires an adjacent pawn of the
side to move, the correct diagonal destination, the matching opponent pawn on
the bypassed square, and legality after that pawn is removed. Any intervening
move clears the nominal field. A nominal target with no legal capturer remains
part of `Position` but normalizes away in the repetition key.

### 8.4 Promotion

A pawn move to the last rank must carry exactly one of Q/R/B/N. A promotion code
on any other move rejects. Omitting the choice rejects; there is no implicit
queen. Capture/noncapture truth is derived from the pre-state and all four
choices remain distinct canonical moves.

### 8.5 History and claim availability

`HistoryState` contains:

- played ply count, initially zero;
- halfmove clock, initially zero;
- the ordered repetition-key sequence including the initial key; and
- occurrence counts derivable from that sequence.

`MAX_HISTORY_PLIES` is 4,096. The sequence therefore has at most 4,097 keys,
including the initial key, and each occurrence count is an unsigned value able
to represent 4,097. When played plies already equal the maximum, the next move
attempt returns `chess.resource.history_plies` before transition and leaves the
entire state unchanged; no count truncates or wraps.

The sequence is authoritative; a count cache may be retained only if checked
against it. The current position's key begins at occurrence one. After every
legal move, append the new key and increment its count. The halfmove clock resets
after any pawn move or capture, including en passant, and otherwise increments.
Completed full moves are `floor(played_plies / 2)` and the display fullmove
number for the current side-to-move slot is `floor(played_plies / 2) + 1`; no
redundant mutable fullmove counter exists.

Threefold is currently claimable when the current key count is at least three.
The practical 50-move draw is currently claimable at a halfmove clock of at
least 100. Profile v0 omits intended-move paperwork, claim penalties, automatic
fivefold/75-move endings, and any automatic ending merely because a claim is
available. Source records may legally continue.

### 8.6 Board terminal state and events

After a legal move, apply this exact order:

1. update position, castling, nominal en-passant, history, and played plies;
2. if the next side has no legal move and is checked, close as checkmate and
   award the mover a win;
3. else if the next side has no legal move, close as stalemate/draw;
4. else if the position matches a frozen `common_dead` class, close as draw;
5. else remain active and expose current claim availability.

`common_dead` is true only for K versus K, K+B versus K, and K+N versus K, in
either color direction, with no other material. It returns false—not a guessed
general theorem—for every broader material configuration.

The exact public event sum is:

```text
Event := move(Move)
       | resignation(side)
       | draw_agreement
       | claim_threefold
       | claim_50_move
```

`new_game()` is the sole public initial `GameState` constructor. While active:

- either named side may resign, regardless of side to move, and the other side
  wins;
- draw agreement is accepted only after at least two played plies, so both sides
  have made a move;
- a threefold/50-move claim belongs to the side to move and is accepted only
  when currently available; and
- rejected declarations change nothing.

Every move or event after any board terminal or accepted declaration rejects.
The rare official resignation exception that requires general mating-possibility
analysis is explicitly outside profile v0.

### 8.7 Source scores

A source score is an opaque record outcome until checked against the final board:

- checkmate requires the mating side's win code;
- stalemate or a selected common-dead final position requires draw;
- a legal nonterminal position may carry any of the three scores without an
  inferred resignation/agreement/claim cause;
- claim availability alone does not constrain the score; and
- another SAN token after a board terminal state rejects at that next token.

`FinalFEN`, comments, or prose can never supply a termination cause. The score
closes only the source record; it does not change the legal moves of the final
position.

## 9. Scored predicates and rejection semantics

### 9.1 Predicate contract

`spec/chess-v0.md` assigns a stable ID, typed input, exact output, and exhaustive
definition to every predicate that M1 permits the curriculum to score:

| Predicate family | Exact v0 meaning |
|---|---|
| setup/turn | standard initial arrangement, named side to move, and alternation after a shown legal replay |
| occupancy | piece/empty and optional exact piece/side at named squares |
| move legality | encoded move is legal, or one frozen primary illegality family |
| control | named origin(s) control a named square under Section 8.1 |
| defended | a same-side occupied target is controlled by another named/any same-side piece |
| king check | opponent controls the side's king square |
| absolute pin | removing a named non-king piece from its current square, with all else unchanged, exposes its own previously safe king to an opposing slider |
| fork/double attack | after the shown legal move, the moved piece controls at least two explicitly named opposing targets |
| discovered attack/check | the shown legal move vacates a line so a separately named same-side slider newly controls the named target/king |
| escape-square control | the named candidate king square is controlled/uncontrolled; full king-move legality is a separate predicate |
| passed pawn | no opposing pawn lies ahead on the pawn's file or either adjacent file |
| open file | no pawn of either side occupies the named file |
| semi-open file | relative to a named side, no friendly pawn and at least one opposing pawn occupies the named file |
| finite race | exact result over the complete packed legal line/tree, with no engine evaluation |
| finite mating geometry | exact step/relation over a complete packed queen-or-rook mating branch |
| terminal transition | exact checkmate/stalemate result after the shown move with all legal replies enumerated |
| history/claim | exact nominal/effective state, repetition occurrence, halfmove boundary/reset, and current claim availability from one verified replay |
| declaration/event | exact acceptance/result/closure of resignation, agreement, or a current-side claim |
| source score relation | exact distinction between board terminal cause, declaration availability, and a record's minimal score |
| move-record replay | decode one canonical move/score atom, replay a complete bounded sequence, or return the exact semantic result |

Named-target predicates do not smuggle material value or tactical preference
into the definition. “Fork” means the exact two targets supplied, not “good
fork.” False from the deliberately partial `common_dead` predicate means only
“not in a recognized v0 class.”

Terms such as `best`, `winning`, `activity`, `direct threat`, `forcing`,
`overload`, and `favourable` remain unscored unless a later roadmap revision
adds a complete finite definition. M3 cannot make them exact by assigning an ID
to prose.

This table is exhaustive only for chess-owned scoreable truth. `content-v0`
separately owns atomic structural acceptance or rejection of one logical
content record/stream: exact bytes are valid; malformed, truncated, or trailing
bytes reject. M2 owns every `TransportState` meaning (`verified`, `recovered`,
`incomplete`, `corrupt`, `ambiguous`, and `unknown`). `record_replay` composes
those transport outcomes with chess move/score predicates only after M2 exists;
M1 freezes the curriculum family and its future binding without moving either
truth definition into the curriculum.

### 9.2 Primary rejection layers

The public chess API's only canonical cross-language rejection datum is the
stable primary machine code. Richer diagnostic context is optional,
noncanonical, and not compared or scored. Chess-v0 owns the complete code list
and precedence; the design-level layers are:

1. malformed byte length/encoding, reserved bit, or invalid encoded code;
2. local position incoherence;
3. closed game;
4. resource limit;
5. illegal move;
6. invalid declaration/claim event; and
7. source-record contradiction.

Within illegal move, the chess spec freezes enough distinct families for exact
feedback and the critical-error policy, including at least:

- origin equals destination or a valid promotion code used in the wrong move
  context (reserved bits and codes 5–7 are malformed encoding above);
- empty origin or wrong side;
- friendly destination or attempted king capture;
- piece geometry, blocker, pawn advance/capture, or double-step failure;
- promotion missing, unnecessary, or invalid;
- castling right, path, current check, transit check, or destination check;
- en-passant target/geometry/expiry failure; and
- own king left or moved into check.

The exact same primary code is required where both language APIs receive the
same validated-layer input. An implementation may retain richer diagnostics,
but scoring and cross-language comparison use only the frozen primary code.

### 9.3 Closure-aware transition

Public `apply_move(ReplayState, Move)` and `replay_from_start` reject before
transition after checkmate, stalemate, or selected common-dead state;
`apply_move` also enforces the history cap. `apply_event(GameState, ...)` rejects
those board terminals and every accepted declaration. An unchecked board-
transition helper, if useful internally, is private and cannot produce
authoritative replay state.

`apply_event` is the authoritative ordinary-game transition. `apply_move` is the
replay-level board/history transition and cannot observe declaration closure.
Source compilation starts each record with `new_game()` and feeds every SAN move
through `apply_event(..., move(move))`. This prevents a selected `common_dead`
position—which may still have geometric moves—from accepting a continuation
through a lower-level helper.

## 10. Chess evidence strategy

### 10.1 Hand-authored vectors

Hand vectors are small explicit semantic bytes/moves/expected results reviewed
without either implementation. At minimum they cover every roadmap case plus:

- exact initial Position/repetition bytes, hashes, 20 initial legal moves, and
  ascending move order;
- every piece's movement, capture, friendly occupancy, and blocker boundary;
- pinned control versus pinned legal movement;
- adjacent kings and a king capture that opens a slider line;
- castling on both sides/colors, lost/nonrestored rights, an attacked rook,
  queenside `b`-file attack, and a transit-only attack with the origin safe;
- en-passant storage with no capturer, legal capture, expiry, two candidate
  capturers, and a geometrically available capture exposing the king;
- quiet/capture promotion to Q/R/B/N, missing promotion, and immediate
  check/mate truth;
- checkmate, stalemate, each selected common-dead class, a
  stalemate/common-dead overlap (stalemate wins precedence), and K+NN versus K
  returning false from the partial classifier;
- repeated initial position on occurrences one/two/three, lost castling rights,
  nominal versus effective en-passant, and halfmove 99/100 plus resets;
- draw agreement at 0/1/2 plies, agreement while in nonterminal check, every
  valid claim, every invalid/premature event, and every post-terminal event;
- nonterminal source results without invented cause and every terminal score
  contradiction; and
- every rejection layer, multiply invalid precedence, and no-mutation result.

Human-readable FEN may label a hand fixture for review, but it is never
authority and no production FEN parser is needed. A board-local fixture's
canonical Position bytes authorize only occupancy/control checks. Every
legal-move, history, claim, terminal, declaration, or source fixture carries a
complete canonical move sequence from the standard start; the independently
derived `ReplayState` plus expected result are the authoritative test input.

### 10.2 Bounded properties and metamorphic checks

Each language may use a different internal deterministic generator. Every run is
seeded, case-count-bounded, and reports the seed/case index on failure. Required
properties include:

- below the history cap, every returned legal move is pseudo-legal, applies
  successfully, and leaves the mover's king safe;
- an applied legal move toggles side, updates exactly the declared fields, and
  round-trips through Position bytes;
- legal move and controller output is sorted and duplicate-free;
- replaying a move prefix twice yields byte-identical positions/history;
- no move captures a king and every promotion-to-last-rank has four choices;
- replay-derived positions validate locally;
- repetition keys ignore only the declared non-effective fields;
- identity is the only universally valid chess transform; every nonidentity
  transform is exercised only after the transformed state/replay validates in
  the actual input domain and the named predicate plus accepted response are
  independently shown invariant;
- adding/changing opaque source metadata cannot change a compiled game; and
- source block permutation changes raw spans/source ordinals but not sorted game
  bytes or semantic identities.

Exhaustive bounded microboards may be used where cheaper than random generation.
No property may allocate or search an unbounded state space.

### 10.3 Named mutants

Tests contain deliberately wrong, test-only alternatives or transformed
expectations for at least these faults:

| Mutant | Required killer |
|---|---|
| pinned pieces do not control | pinned-control hand case |
| king safety checked before capture removal | opened-slider king-capture case |
| castling checks destination but skips transit | origin-safe transit-attack case |
| attacked rook or queenside `b` square forbids castle | castling boundary cases |
| en-passant pawn remains during self-check | discovered-line case |
| nominal EP always enters repetition | no-legal-capture repetition case |
| omitted promotion becomes queen | missing-promotion case |
| stalemate tested as mate or dead first | terminal-precedence cases |
| initial repetition occurrence omitted | knight-cycle occurrence case |
| pawn/capture fails to reset halfmove | 99/100 boundary case |
| premature agreement allowed | 0/1-ply agreement cases |
| source suffix trusted or ignored | exact suffix matrix |
| source disambiguation uses geometric movers | pinned-disambiguation case |
| source continues through terminal | terminal-continuation case |

There is no mutation score, dashboard, production feature flag, or mutation
framework. A mutant exists only to prove that a specific independent oracle can
detect the named misunderstanding.

### 10.4 External oracle boundary

The external library receives normalized project positions/moves only after the
project parser has accepted a hand/generated semantic case. Comparisons are
component-specific:

- legal move set after mapping to canonical 16-bit moves;
- post-move occupancy, side, rights, strict nominal en-passant, and check truth;
- checkmate/stalemate for states where both profiles agree; and
- current repetition/halfmove facts under an explicitly matched history.

Do not compare raw FEN strings, source token acceptance, SAN parser behavior,
generic `outcome()`, broad insufficient-material results, intended-move claim
helpers, or native move order. A disagreement creates a diagnostic failure for
human investigation; it never overwrites fixtures or selects the external
answer automatically.

## 11. Raw source grammar

Sections 11–13 retain reviewed grammar rationale and evidence requirements.
The promoted [`spec/source-v0.md`](../spec/source-v0.md) is now the sole
normative owner of raw grammar, project SAN, spans, rejection precedence, game
records/sets, candidate comparison, and retained source evidence. Draft shapes
or process wording below are nonnormative and cannot override that owner. Both
compilers still start from the same locked raw bytes and implement their state
machines independently without a Markdown, PGN, regex, or parser-generator
dependency.

### 11.1 Resource and byte profile

- input is checked at the existing 1,048,576-byte ceiling before decode;
- UTF-8 is strict and an initial BOM rejects;
- NUL, DEL, and C0 controls other than HT, LF, and CR reject;
- newline form is uniformly LF or uniformly CRLF, with a final newline required;
- bare CR or mixed forms reject;
- `HWS` is ASCII SP or HT only; other Unicode whitespace is data or invalid by
  its enclosing grammar;
- a source block's exact half-open fence span (opener through closer newline)
  has at most 65,535 raw bytes, 64 tags, 8,192 tokens, and 4,096 plies; token
  count includes move numbers, SAN tokens, and the result marker; a tag name has
  at most 32 ASCII bytes and a raw value at most 1,024 bytes between quotes
  before escape decoding; and
- the complete source has exactly 64 blocks and at most 65,535 plies.

These are M1 source-language safety limits, owned by `source-v0`; they do not
preempt M2's smaller artifact/runtime profile limits. They comfortably contain
the observed maximum 2,250-byte candidate, 1,701-byte movetext, 21 tags, and 271
plies without a configuration system.

Every reported span is a zero-based half-open **raw byte** interval into the
original LF/CRLF input. UTF-8 character indices and newline-normalized offsets
are forbidden. A deterministic UTF-8 error rule and EOF zero-width span are
frozen in source-v0 and covered by multibyte-prefix fixtures.

### 11.2 Fence grammar

Logical lines exclude their newline bytes. A recognized opener is the literal
three bytes `` ``` ``, followed immediately by `pgn` and then `HWS*`, at column
zero. Its closer is the literal three bytes `` ``` `` followed by `HWS*`, also
at column zero.
Anything after `pgn` or the closer other than HWS rejects. Indented, uppercase,
four-backtick, nested, orphan-close, or unclosed forms reject; exactly 64 valid
pairs are required. Other column-zero backtick-fence shapes reject rather than
creating an alternate Markdown interpretation.

Outside valid fences, UTF-8/control/newline validity and fence recognition are
checked, then bytes are semantically ignored. Existing outer trailing spaces are
therefore harmless. Outer prose, headings, comments, or embedded words such as
SAN-looking text never reach tag/movetext scanning.

### 11.3 Tag and framing grammar

Each fence contains:

1. one or more contiguous tag lines;
2. exactly one empty logical separator line with zero bytes; and
3. one nonempty linear movetext token stream, which may wrap across physical
   lines but contains no empty line.

A tag line is exactly:

```text
"[" name SP "\"" value "\"" "]"
name  = ASCII letter (ASCII letter | digit | "_")*
value = valid UTF-8 bytes except unescaped quote/backslash;
        only \" and \\ escapes are admitted
```

There is no leading/trailing HWS and exactly one SP separates name/value.
The global ASCII control/newline rules in Section 11.1 still apply; every other
Unicode scalar, including C1 code points, is opaque data and no Unicode category
test is performed. Decoded names are case-sensitive and unique. Exact `SetUp`, `FEN`, and `Variant`
reject. Exact `Result` is required once and is the only semantic tag. Its decoded
value must be `1-0`, `0-1`, or `1/2-1/2`. Every other tag/value is opaque,
including `PlyCount`, `CriticalFEN`, `FinalFEN`, and `CriticalMove`.

Changing opaque tags can change diagnostics/raw spans but cannot change
acceptance when the changed bytes still satisfy this grammar, resolved moves,
score, or game IR. Comments are forbidden inside fenced movetext; “outer
comments are ignored” is not a comment syntax inside PGN.

### 11.4 Movetext state machine

Every physical movetext line is nonempty and starts/ends with a non-HWS byte;
there is no leading separator, trailing HWS, or HWS-only line. Within a line,
tokens are separated by one or more HWS bytes; a newline separates the final
token of one line from the first token of the next. Physical wrapping otherwise
has no semantic role. The token sequence is exactly:

```text
1. WhiteSAN [BlackSAN] 2. WhiteSAN [BlackSAN] ... Result
```

More precisely:

- an ASCII decimal `n.` standalone token precedes every first-side SAN;
- `n` begins at 1, has no leading zero, and increments exactly by one;
- a second-side SAN follows without a move-number token;
- the result marker may follow either side's SAN;
- at least one SAN is required;
- marker and decoded `Result` tag must be byte-equal;
- `*`, ellipsis starts, attached move numbers, null moves, or tokens after the
  result reject; and
- comments, semicolon comments, `%` escape lines, RAV, NAG, annotation suffix,
  `0-0`, `e.p.`, `++`, LAN/UCI, and repair/fallback forms reject.

“One main line” means this one variation-free token stream, not one physical
line.

## 12. Exact source SAN and replay

### 12.1 Canonical SAN subset

The accepted move token is exactly the project's canonical spelling:

- pawn quiet move: destination plus mandatory promotion where applicable;
- pawn capture: origin file, `x`, destination, plus mandatory promotion;
- piece move: `KQRBN`, minimum required legal-mover disambiguation, `x`
  mandatory if and only if a capture occurs, then destination;
- castle: `O-O` or `O-O-O` with letter `O`; and
- exact terminal suffix: none for no check, `+` for check without mate, `#` for
  checkmate.

Promotion is exactly `=Q`, `=R`, `=B`, or `=N`. Kings have no disambiguation.
Capture markers, destination, promotion, and suffix must reflect the actual
transition. Unnecessary as well as missing disambiguation rejects.

Although historical PGN often permits check/mate suffix omission in importers,
the locked anthology already spells every observed check/mate exactly. Requiring
canonical suffixes removes a relaxation, a duplicate surface spelling, and an
otherwise pointless repair branch without changing the source.

### 12.2 Legal-mover disambiguation

For a non-pawn piece move, collect all **legal**, same-type, same-side moves to
the destination before considering source disambiguation. If there is one,
emit none. Otherwise:

1. emit the origin file if no other candidate shares it;
2. else emit the origin rank if no other candidate shares it;
3. else emit the complete origin square.

Pinned pseudo-movers do not participate. The resolver parses a bounded SAN
shape, matches its stem against the independently generated legal set, and then
requires exact canonical spelling. Zero legal matches returns
`source.san.no_match`; more than one is a defensive
`source.san.ambiguous`; a unique move with noncanonical surface details returns
the appropriate frozen noncanonical/suffix code. There is no later independent
legality failure after a unique legal-set match.

### 12.3 Replay order

For each expected SAN slot:

1. if the current `GameState` is closed and another non-result token exists,
   reject `source.game.after_terminal` at that token without trying a move;
2. parse bounded token shape;
3. enumerate the current core's canonical legal moves;
4. match and require exact canonical stem;
5. apply the unique move through closure-aware event handling;
6. compare exact check/mate suffix truth; and
7. record the trace row only after the whole step succeeds.

The compiled record remains provisional until its final marker/tag/terminal
score are consistent. A failed step exposes no shorter accepted prefix.

## 13. Source rejection, compilation, and evidence

### 13.1 Stable rejection order

`source-v0` freezes stable string/numeric codes and one primary order:

1. input size;
2. UTF-8/BOM/control/newline profile;
3. fence shape/pairing/count and per-block fence-span limit;
4. tag count/name/value limits and tag syntax/escape/duplicate/forbidden/result;
5. separator/movetext framing and token/per-record-ply/total-ply limits;
6. move-number/result-token structure, tag/marker mismatch, and any token after
   the result marker;
7. terminal continuation;
8. SAN shape, legal-set match, ambiguity, and canonical stem;
9. check/mate suffix truth;
10. terminal score consistency; and
11. duplicate move streams across otherwise valid records.

The lowest raw start wins within a category; equal starts use the code order
declared by source-v0. Category precedence wins over byte position so both
implementations can diagnose after independent passes. Missing required bytes
use a zero-width span at the position where they were required; cross-record
duplicates point at the later record's opener and include the earlier source
ordinal only as noncanonical diagnostic context.

At minimum the stable family contains codes for too-large input, UTF-8/BOM,
control/newline, bad/orphan/nested/unclosed fence, wrong fence count, tag
syntax/escape/duplicate/forbidden/missing or bad Result, separator/movetext,
move number, result token/mismatch/trailing token, SAN shape/no-match/ambiguity/
noncanonical/suffix, terminal continuation/score, resource bound, and duplicate
stream. Free-form messages, library exceptions, and language-specific offsets
are never compared.

Every resource code belongs to the stage above: raw input size to 1, block bytes
and fence count to 3, tag count/name/value to 4, and token/record-ply/total-ply
to 5. A multiply invalid input cannot choose a resource error from a later stage
merely because it is cheaper to notice.

### 13.2 Independence boundary

Path P and Path R each:

- read the locked regular file under M0-equivalent path/size safeguards;
- scan the complete raw bytes directly;
- implement their own newline/fence/tag/token/SAN state machine;
- call only their own chess core;
- produce provisional per-ply and game outputs; and
- fail closed before publishing any object.

They may share only owning specs, numeric constants, hand-authored raw fixtures,
and identity algorithms already proved independent. They may not share a
normalized source copy, lexer output, parse tree, SAN encoder/resolver, move
trace, generated expected result, or game IR. The M0 doctor is run alongside as
a source-lock observation, never imported as parser code.

### 13.3 Per-ply equality

Every resolved ply is compared, not sampled. Source-v0 owns the exact trace row,
candidate/report schemas, cross-field validation, and 1 MiB cap. Each producer
independently emits candidate facts, trace, and game-set bytes without a
producer/agreement assertion. The coordinator validates both candidates,
compares every candidate-trace and game-set byte, and only then constructs and
atomically installs the single retained report with fixed producer labels. The
retained report has no self-hash or trace-identity domain.

### 13.4 Game IR, duplicates, and sorting

Each record is exactly:

```text
u16_be(ply_count) || ply_count * u16_be(move) || u8(score)
```

For source-v0, `1 <= ply_count <= 4,096` and the count must equal the complete
resolved move list before serialization.

The compiler must:

1. successfully compile all 64 provisional records;
2. reject identical move streams before sorting, whether scores match or differ;
3. compare full move bytes, never only hashes;
4. sort complete game bytes by unsigned lexicographic byte order;
5. assign canonical ordinals 0–63 from that order; and
6. serialize the exact set container from Section 6.5 atomically.

No suffix spelling, raw whitespace, metadata, raw path, source ordinal, or hash
collision can evade duplicate detection or break a sort tie. The expected
10,022 total game-key bytes from the diagnostic probe is not hard-coded as an
oracle; the dual compilers must measure it.

### 13.5 Noninterference transformations

Starting from a valid fixture/source projection, tests separately mutate:

- every opaque tag value, including plausible FEN/count metadata;
- opaque tag presence/order and player/event/date names;
- outer Markdown prose/comments and trailing HWS;
- uniform LF versus CRLF;
- source filename and safe containing path;
- physical fence order; and
- accepted token spacing/wrapping.

When moves and exact `Result` remain unchanged and the mutation remains within
the accepted grammar, individual game bytes/identities and the sorted set must
remain identical. Raw source identity, audit spans, and source ordinals may
change. In-fence comments, malformed whitespace, mixed newlines, alternate
starts, or other rejected forms are negative grammar cases, not
noninterference promises.

## 14. Curriculum blueprint

This section is a checked human-readable synopsis of
[`spec/curriculum-v0.toml`](../spec/curriculum-v0.toml), which owns the closed
concept, family, stratum, evidence, split, formula, cue, form, cap, and cut data.
M1 verifies that blueprint with synthetic manifests only; it does not require or
publish a concrete lesson, result-bearing form, seed, schedule, answer,
commitment, candidate, or participant record.

### 14.1 Essential Core 1/2 families

`spec/curriculum-v0.toml` freezes these eleven essential families and references
only stable predicate/validation IDs owned by chess-v0 or content-v0. The
content-v0 reference is confined to logical-record stream validity:

| ID | Mandatory strata |
|---|---|
| `setup_turn` | 8×8 layout, all initial pieces, first side, alternating turn |
| `ordinary_move_capture` | all six identities, sliders/blockers, knight, pawn forward/capture contrast, initial double, friendly occupancy |
| `control_vs_legal` | pawn control, defended friendly target, pinned controller, king adjacency, control versus move |
| `king_safety` | check, evasion, self-check, king capture safety, double check |
| `mate_stalemate` | checkmate versus check, stalemate, legal-reply exhaustiveness |
| `castling` | rights/pieces/path, current/transit/destination check, lost rights, rook relocation |
| `en_passant` | immediate window, expiry, removed pawn, self-check, nominal versus effective state |
| `promotion` | quiet/capture, mandatory Q/R/B/N, check/mate after promotion, invalid contexts |
| `position_history_draw` | same board/different history, repetition key/occurrence, 100-halfmove boundary/reset, claims not automatic |
| `termination_score` | board terminals, selected common-dead scope, declarations, post-terminal rejection, score versus cause |
| `record_replay` | canonical move decode, short replay, score, atomic logical-record valid/malformed/truncated behavior; M2/M3 later bind transport-state strata |

The family count is small on purpose. Mandatory strata prevent a broad family
from hiding an omitted rule; strata are content coverage requirements, not
separate post-hoc statistical families.

### 14.2 Retained Core 3 families

The nine roadmap-required relation families are retained exactly:

```text
attacked_defended
absolute_pin
fork_double_attack
discovered_attack_check
escape_square_control
passed_pawn
open_semi_open_file
finite_promotion_race
queen_or_rook_mating_geometry
```

Material values, strategy tendencies, and the bounded move-check routine are
taught/practised only through exact visible facts and explicit limitations.
They are not move-quality assessment families.

### 14.3 Teaching/practice minimums

For every retained concept, authoring later provides at least:

- one grounded rule/relation;
- one contrasting worked transition including a boundary/counterexample;
- one active packed bounded prediction/reason selection with immediate exact
  feedback;
- one distinct held-out practice case; and
- one complete passive trace of that packed practice's exposed action set.

Support may fade by omitting a shown next step or reason in later practice. The
blueprint does not mandate a learner-adaptive engine, rigid lesson count, or
free-form natural-language explanation. “Complete alternatives” means all
actions exposed by that node, unless the node explicitly claims `all_legal_moves`
and packs that exact complete set.

Every mandatory family stratum appears in teaching/practice and at least one
held-out posttest or delayed case; every Core 3 stratum appears in posttest
because delayed testing covers only essential families. Self-check, castling
from/through/into check, en-passant self-check, post-terminal continuation, and
score-versus-cause each appear in posttest. One well-formed multi-target item
may cover several strata only when each referenced stratum's typed owner call
independently recomputes and passes; there is no forced one-item-per-stratum
bureaucracy. A bare family or stratum label never proves coverage.

### 14.4 Record roles, splits, and leakage keys

Every curriculum record retains exactly one roadmap Section 6.4 role such as
`exact_rule`, `worked_example`, or `practice`. Independently, every case has one
assessment split:

```text
teaching | practice | pretest | posttest | delayed
```

Each item has exactly one nonorthogonal primary generator: `training`,
`formative`, `pretest`, `final_transfer`, or `delayed`, mapped respectively to
the five splits above. `cue_control` is only an optional orthogonal posttest
generator/pair flag, not a competing record role, primary generator, or split.

Result-bearing forms are blueprint-matched, not claimed statistically equivalent
or equated. Minimums are:

- pretest: at least two items for every family used in an acquisition claim;
- pretest integrated screening: one legal-play task;
- posttest: at least two held-out items per essential/retained family, including
  one rendering-matched relation-flipping counterfactual pair;
- posttest integrated: one disjoint held-out short legal sequence plus one
  evaluator-generated legal canonical-format record-reading task, never an
  anthology study record;
  and
- delayed: at least one independently held-out item per essential Core 1/2
  family, with more only to cover an otherwise absent mandatory stratum.

Case equality uses the full structural tagged value, never an author-provided
hash or opaque key. Its authority is exactly one of board-local `Position`
bytes, complete replay `Move`s, complete game `Event`s plus derived status,
source `GameBytes`, or content bytes. The value also includes shown moves,
sorted unique case-pattern IDs, ordered owner-call IDs and typed argument bytes,
semantic prompt targets, and the complete accepted semantic-response set.
Declaration state requires complete game-event authority and is never inferred
from replay alone.

The linter applies the fixed `identity`, file-reflection,
rank-reflection-plus-color-swap, and 180-degree-plus-color-swap candidates using
the TOML's exact per-predicate input/result mapping. Each transformed authority
is independently validated and must preserve predicate result and accepted
responses; a rejected/unmappable authority is inapplicable, not an author opt
out. None of the four transforms is globally safe. Answer order is audited as a
cue rather than made artificially unique.

Blueprint response/prompt schemas and near-transfer
`structural_template_id` values may repeat without permitting semantic-case
reuse. Every essential/Core 3 family includes at least one posttest
assessment-only structural template absent from teaching and practice. Its
counterfactual pair may satisfy the two-item posttest minimum; no third item is
forced.

Passive examples participate in leakage checks. A new glyph or shuffled order
does not make a memorized semantic case held out. Delayed cases are disjoint
from posttest as well as instruction. The private manifest freezes at most three
counterbalanced forms and every screened slot assignment (six to eight) before
result-bearing pretest. A form may serve more than one participant; every form
uses the same multiset of family, split, sorted unique strata, response shape,
and maximum selections. Pre/post matching omits only split. Integrated tasks are
excluded from that family multiset and match separately by task ID, response
shape, and maximum selections. Shared schemas/structural templates keep the
forms blueprint-matched without creating hundreds of one-off cases.
The later private assessment manifest owns each concrete seeded display order
and its recorded realization; curriculum-v0 freezes only that those private
fields will be required, not their values.

### 14.5 Response and item scoring

This subsection is a checked human synopsis. The promoted
[`spec/content-v0.md`](../spec/content-v0.md) is the sole normative owner of
generic content bytes, role/mode compatibility, action precedence, budgets,
outcomes, and run-state replay.

The learner actions remain `select(region_id)`, `reset`, and `commit`. A node
declares a single, unordered-set, or ordered-sequence response; a mechanical
selection cap and repeat policy; a local item-event budget; and one of the
closed packed-practice, external, or unscored modes. The final root separately
declares the global run budget. Empty commit is always well-formed. Only an
explicit packed accepted case makes it accepted; external validity and every
result-bearing accepted alternative remain evaluator-side.

Malformed raw actions normalize to one canonical invalid sentinel. A
well-framed select of zero, a missing region, or a nonselectable region remains
the original action and returns invalid-region. Every active call consumes one
event. Duplicate precedes over-limit, a final-event commit succeeds, and later
committed or exhausted calls are immutable and unlogged. A non-learner advance
moves a committed nonterminal edge without replenishing global budget.

Canonical responses contain one shape byte, one fixed `u16` count, and fixed
`u16` region IDs. Single permits zero or one, set is sorted and unique, and
sequence preserves order and permitted multiplicity. Packed practice alone
contains exact accepted/special cases and correctness feedback. External and
unscored nodes have no correctness branch; there is no partial credit,
learner-visible answer cardinality, administrator override, or inferred early
completion.

A critical label applies only to a committed incorrect response, never a
transient buffered selection later reset. It is reported/emphasized and makes
that item/family fail through the ordinary all-items-correct rule; it is not an
extra cross-family veto. Critical labels are a short closed list:

- accepting a move that leaves/moves one's king into check;
- accepting castling from, through, or into check;
- accepting en passant that exposes one's king;
- accepting a move/event after a terminal state; and
- treating a source score as proof of a termination cause.

The label is derived only by recomputing its typed owner predicate and exact
wrong-response condition/rejection code. A supplied label string or family
membership is never evidence that an error was critical.

Other wrong responses remain wrong without being inflated into critical errors.

### 14.6 Eligibility and gates

Before pretest, every learner completes one unscored, repeatable non-chess
familiarization fixture demonstrating every response shape/mechanic used by the
form, including select, reset, empty commit, nonempty commit, set, and sequence.
Inability to complete it is a setup failure before artifact exposure, not a
chess baseline fail. Eligibility then requires:

- `requires_no_prior_full_game_unaided = true`;
- failure of the pretest integrated legal-play screening task;
- failure of `king_safety`; and
- failure of at least two among `castling`, `en_passant`, `promotion`, and
  `record_replay`.

Selection also requires every pretest family and the integrated screen to be
complete, valid, and unhinted. A baseline family fail means that every item
reached a valid commit and at least one committed response was incorrect.
Missing, uncommitted, budget-exhausted, hinted, or otherwise invalid baseline
data are `unavailable`, never evidence of a chess deficit; that screened slot
cannot be selected or supply baseline coverage/acquisition. There is no
same-item baseline retry.

There is no raw `<40%` cutoff: its chance level changes with item/cardinality
shape and adds nothing to those construct-specific criteria. Up to two reserves
may complete the frozen pretest; predeclared eligibility/coverage rules choose
the final six before artifact instruction/practice. Those six collectively
supply at least three baseline failures for every essential Core 1/2 family and
every retained Core 3 family, unconditionally. Only the requirement that at
least four learners each have a baseline-failed retained Core 3 family is
conditional on enabling the combined individual Core 3 claim.

Family pass means every item correct; a committed critical response is already
incorrect and separately labelled. Acquisition in a family means baseline
family fail followed by posttest family pass. Define
`ceil75(n) = ceil(3*n/4)` only for checked integer `0 <= n <= 11`. Define
`family_acquisition(b)` as `no_claim` for `b < 3`, `b-1` for `3 <= b <= 6`,
and `invalid_protocol` for `b > 6`. Any required E/C family with `b < 3` makes
the selected protocol unclaimable. All arithmetic is checked integer arithmetic.

For executable scoring, define:

```text
E = {setup_turn, ordinary_move_capture, control_vs_legal, king_safety,
     mate_stalemate, castling, en_passant, promotion,
     position_history_draw, termination_score, record_replay}
S = {castling, en_passant, promotion, record_replay}
C = the nine exact Core 3 IDs in Section 14.2

F_i  = {f in E | learner i failed f at baseline}
A_i  = {f in F_i | learner i passed f at posttest}
CF_i = {f in C | learner i failed f at baseline}
CA_i = {f in CF_i | learner i passed f at posttest}
D_i  = {f in E | learner i passed the delayed item(s) for f}

b_f = count of learners who failed family f at baseline
a_f = count of those learners who passed f at posttest
p_f = count of all six learners who passed f at posttest
d_f = count of all six learners who passed f at delayed
```

The posttest integrated item IDs are exactly
`integrated_legal_sequence_post` and `integrated_record_reading_post`; the
eligibility screen is the disjoint `integrated_legal_sequence_pre`.

The final frozen gates are exactly the revision-5 roadmap gates:

1. for every `f in E`, `p_f >= 5` and
   `a_f >= family_acquisition(b_f)`;
2. at least four learners satisfy `|A_i| >= ceil75(|F_i|)`,
   `king_safety in A_i`, `|A_i intersect S| >= 2`, and pass both named posttest
   integrated items;
3. for every `f in C`, `p_f >= 4` and
   `a_f >= family_acquisition(b_f)`;
4. if a combined Core 3 claim is made, at least four learners satisfy
   `|CF_i| >= 1` and `|CA_i| >= ceil75(|CF_i|)`;
5. for every `f in E`, `d_f >= 4`, and at least four learners satisfy
   `|D_i| >= ceil75(|E|)`, `king_safety in D_i`, and
   `|D_i intersect S| >= 2`; and
6. no counted result used a semantic hint or answer-revealing behavior.

Prior mastery may count toward posttest attainment but never acquisition. At
first artifact instruction/practice exposure, the six-person denominator is
immutable. Missing, out-of-window, hinted, restudied, malformed, or otherwise
invalid/non-gating participant results count as failures for every affected
gate; there is no replacement, retry, or post-hoc exclusion, and unaffected
completed results remain reported. A candidate/evaluator defect invalidates the
affected form/candidate rather than being charged to a learner. A family with
fewer than three baseline failures has no acquisition claim even if attainment
is high. The full protocol and thresholds never change after the first
result-bearing pretest; the six-person denominator never changes after artifact
instruction begins.

### 14.7 Feedback, private forms, and cue audit

Practice supplies immediate exact corrective feedback. Pretest, posttest, and
delayed items expose only one presentation-identical neutral acknowledgement.
Result-bearing feedback for every screened slot, including unused reserves, is
withheld until every selected learner's normal or fallback feedback window
resolves below. Before then no interface or report reveals correctness, accepted
region/cardinality, relation label, score, answer-dependent branch, or
answer-dependent schedule. Early posttest correctness contaminates delayed
evidence; pretest or form-answer leakage invalidates the affected current and
later evidence and the affected form. Immediate posttesting is itself retrieval practice,
so delayed evidence is honestly described as short-delay performance after
curriculum plus pre/post retrieval, not artifact-only or long-term retention.

From each screened slot's result-bearing pretest until the final six-person
denominator freezes, every screened participant receives one neutral
no-external-chess-study/help/sharing instruction. When unused-reserve status
becomes final, that reserve's study/help restriction ends, but the no-sharing
and feedback embargo continues until release. Selected learners continue the
study/help/sharing restriction through posttest and use only the recovered
artifact stream in controlled sessions; artifact instruction starts within 24
hours after pretest. After posttest, the artifact/practice session closes and a
no-restudy instruction continues through delayed testing. Available session
logs and participant report are sufficient—no invasive monitoring is required.
Reported/observed outside semantic study, help, sharing, or artifact reuse makes
the affected acquisition/delayed result a fixed-denominator gate failure.

A learner's first delayed attempt is the only attempt. It is valid only in the
closed interval from 36 through 60 hours after that learner's complete valid
posttest, provided that posttest itself finishes by the slot's frozen posttest
deadline. An early, late, invalid, or missed first attempt is reported and
fails every affected
delayed gate without retry. The feedback window still resolves only on a valid
in-window completion or at the +60-hour fallback deadline. If posttest is not
complete and valid by its frozen deadline, posttest/delayed results are missing
failures, no delayed submission can count, and the feedback embargo for that
slot resolves 60 hours after that deadline. Feedback may be released only after
the last selected normal or fallback window resolves.

Because this repository is public, concrete result-bearing payloads, accepted
sets, usable seeds, and display schedules stay in one evaluator-only canonical
bundle outside the learner bundle and public checkout before authorized reveal.
Before the first screened candidate or reserve starts result-bearing pretest,
publish a tracked salted commitment that binds the frozen private protocol and
assessment bundle. Exact commitment byte framing belongs to the later private
assessment-manifest specification. Keep the bundle and salt private, then reveal
and verify both only after all selected windows resolve. A private digest is not
a commitment, and a public generator plus public seed is not a private form.

The deterministic cue audit covers what a learner can observe:

- region/option ordinal, area, count, highlight count, and selectable count;
- record/payload length, node/branch count, and visible schema/type labels;
- focus/tab order, accessibility attributes, hover/cursor/clickability/disabled
  state;
- acknowledgement content/schedule and error shape;
- answer sequence patterns, alternating answers, and `same_as_prior`; and
- accepted response cardinality.

Every family has a rendering-matched counterfactual pair that flips exact truth.
Pairs are not labelled or adjacent. Each predeclared strategy (`first`, `last`,
`shortest`, `longest`, `largest_region`, `most_highlighted`, `alternating`,
`same_as_prior`, `empty_commit`, and `select_all_visible`) makes at least one
error in every family and scores no more than one-half across each frozen form.
Each is a total deterministic function: visible ordinal breaks ties; a missing
feature or no selectable region falls back to empty commit; `alternating` starts
with first; and `select_all_visible` selects ascending visible ordinals up to
the declared cap before commit. `same_as_prior` maps every prior accepted
response to a visible-ordinal vector, sorts/uniques sets, preserves sequence
order, and only the adversarial strategy chooses the lexicographically smallest
vector. After the no-selectable-region or zero-cap empty commit, resolution
order is exact: an absent prior item selects first; a present empty prior
response commits empty; a mechanically valid mapped response replays; and an
incompatible mapping selects first. It never creates a preferred scoring
answer. Response timing
is a declared deterministic schedule/work feature, never noisy wall time. A
small feature/strategy table is enough; no classifier platform is built.

The calibrated 4–8-hour initial active-time clock includes familiarization,
pretest, artifact instruction/practice, and immediate posttest. Breaks and
neutral administration are excluded and reported; delayed active time is
reported separately. Result-bearing runs checkpoint only after a committed
item. After a host interruption the same candidate/form resumes at the next
unpresented item with its canonical log unchanged; an interrupted uncommitted
item is not retried. It makes a baseline form unavailable before selection, or
is a missing/incorrect item after the denominator freezes.

### 14.8 Reporting claim

The final report publishes screened/eligible/selected/reserve counts, the frozen
selection rule, and raw numerator/denominator trajectories by opaque slot ID and
family, including missing sessions, help, and frozen exclusions. It contains no
name, contact data, or free text; plain consent for this public granularity and
the private identity mapping remain evaluator-side. It may say, only if true:

> The selected six-person chess-naive cohort met held-out post-use criteria for
> the declared rules/relation families and approximately two-day short-delay
> criteria for the essential core-rule families under this protocol.

It does not claim population effectiveness, causal efficacy, psychometric
equivalence, durable retention, or a general chess-learning result. It does not
use p-values, inferred population percentages, or a qualitative override.

## 15. Initial generic content-v0 slice

This section is a checked rationale and implementation synopsis. The promoted
[`spec/content-v0.md`](../spec/content-v0.md) is the sole normative owner of
generic content bytes, records, references, interaction semantics, run-state
bytes, rejection spans/precedence, and pre-profile content limits. A conflict
is repaired in that smaller owner before implementation continues.

The selected format remains one atomic, flat, definite-length stream with
strictly increasing nonzero IDs, earlier typed dependencies, bounded control
references, exactly one final root, and no partial prefix acceptance. The root
payload is four bytes: one entry lesson-node reference and one independent
global event budget. Each node has its own local item budget. Success edges form
a terminating DAG whose worst path's complete local-budget sum fits the global
budget; rejected/default cycles terminate because every traversal consumes a
global event.

The closed fourteen kinds cover text; unsigned/enum/mask atom schemas; atom
vectors; matrices; field schemas and tuples; regions; semantic bindings and
opaque data; predicate results; feedback; standalone per-node passive traces;
lesson nodes; and the root. Presentations either are the region surface matrix
or contain that exact matrix once through typed tuple references. Semantic
namespaces and atoms stay opaque: structural validation cannot create
`ReplayState` or evaluate chess.

The exact role/mode table prevents correctness data from entering external or
unscored paths. Packed practice alone contains accepted/special cases and exact
feedback. Passive traces replay one node from a fresh empty local state and end
at commit; they do not create a cross-node trace protocol. Malformed raw actions
normalize to one zero sentinel, while well-framed invalid-region selects remain
unchanged. A final-event commit succeeds. Advancing a nonterminal commit with
zero global budget reaches an immutable exhausted target.

The exact largest valid run state is 466,958 bytes; the exhausted-buffer maximum
is 466,955 bytes. The content stream remains capped at 1,048,576 bytes, with the
smaller structural count/field limits owned and exhaustively listed in the
content specification. M2 measures lower physical/profile maxima from real
content. M1 adds no generic serializer, VM, renderer, concrete lesson graph,
assessment form, or transport profile.

## 16. Implementation and repository contract

### 16.1 Dependency policy

Use the existing project environments and the simplest available tools:

- Python standard library for core/parser/tests/reporting;
- Rust standard library plus dependencies already justified by M0;
- existing canonical-manifest and identity code where its contract applies;
- a single pinned python-chess development group only for the diagnostic oracle;
  and
- POSIX `sh`, `uv`, and Cargo through `scripts/check`.

Do not add pytest, Hypothesis, proptest/quickcheck, a PGN/Markdown/parser
framework, a serialization framework, a mutation service, a database, or a CLI
framework. A new dependency is allowed only when execution finds a concrete
mandatory consumer that cannot be met safely by this stack; record the reason
and keep it outside artifact-critical/runtime paths when possible.

### 16.2 Independent implementation rules

Python and Rust may choose arrays, bitboards, or another bounded internal board
representation independently. Observable bytes and ordering come only from the
spec. Neither implementation may translate or bind the other, shell out to the
other during normal semantics, or ingest expected cases generated solely by the
other.

Shared hand fixtures are reviewed inputs. Generated property cases may be
language-local. Cross-language differential input must come from a neutral hand
or independently reproduced generator definition, never “Python output is the
Rust expected file.” The final source trace is installed only after both
candidates exist and compare equal.

### 16.3 Bounded and fail-closed behavior

All public parsers and semantic operations:

- validate declared lengths/counts before arithmetic or allocation;
- use checked integer arithmetic;
- bound loops, histories, recursion (prefer none), reports, and event graphs;
- reject unknown versions/codes/reserved bits/trailing bytes;
- never recover by truncation, default promotion, fallback parser, metadata,
  hash equality alone, or external-library guess;
- return stable structured codes/spans rather than comparing prose; and
- publish no partial state/output on failure.

Repository text, PGN metadata, fixture descriptions, external pages, exception
strings, and generated strings are data, never instructions.

### 16.4 Deterministic generation

Generated constants, reports, and game bytes must reproduce under different:

- working directories and safe path spellings;
- `TZ`, locale, hash-randomization/iteration order, and temporary directory;
- Python/Rust process order; and
- clean native environments with the locked inputs/dependencies available.

Outputs contain no timestamps, absolute paths, host facts, dependency cache
paths, random temp names, or compiler diagnostics. Candidate output is written
outside its tracked target, bounded and parsed back, then atomically replaces
the target only after all independent equality and registry checks pass.

No normal check rewrites a tracked file. An explicit regeneration/check command
may write an ignored candidate and show the comparison; installation is an
intentional implementation action.

### 16.5 Root checks

M1 extends the existing dispatcher rather than replacing it:

```text
scripts/check fast
scripts/check focused identity
scripts/check focused chess
scripts/check focused source
scripts/check focused curriculum
scripts/check focused content
scripts/check focused repo
scripts/check full
```

Only areas with live tests are admitted; unknown areas fail. `fast` covers
format/schema/generated drift and focused units. `full` runs both language
implementations, all registered fixtures, bounded differential/property/mutant
checks, source regeneration comparison, and repository policy. The external
oracle may be a declared full-check development step but must work offline from
the lock/cache once dependencies are synchronized.

The whitespace check must cover all tracked and untracked candidate files in
the intended diff without overwriting the user's dirty worktree. Rust focused
areas target owning packages/tests rather than accidentally running the entire
future workspace multiple times.

### 16.6 Conformance and generated-data placement

- register only stable hand-authored cross-language payloads directly under
  `conformance/`;
- record payload hash, spec/version, consumers, and honest provenance;
- keep oracle fixtures, generated fuzz/property cases, candidates, and failure
  minimizations outside the shared registry unless promoted by human review;
- use full semantic bytes for equality and sorting; hashes identify/report them
  but never replace collision-free comparison; and
- keep one final game-set object and one compact audit rather than parallel
  presentation copies.

## 17. Required verification matrix

The following scenarios are minimum evidence, not an exhaustive prescription of
test-file layout.

### 17.1 G2 — chess truth

| Scenario | Required result |
|---|---|
| Initial Position/repetition bytes and domains | Exact Section 6 vectors and 20 sorted moves in both languages |
| Pinned piece controls but cannot expose king | Control true; illegal move absent/rejected |
| King capture removes a blocker on an enemy ray | Reject self-check after complete capture |
| Castle with attacked rook or attacked queenside `b` square only | Legal if every king condition passes |
| Castle from/through/into check, including origin-safe transit attack | Reject exact family; state unchanged |
| EP is nominal but no legal capture exists | Position differs; repetition key normalizes EP away |
| EP capture geometrically exists but exposes king | Move illegal; repetition key omits EP |
| Quiet/capture underpromotion | Four exact moves and correct immediate suffix/terminal truth |
| Initial key repeats by knight cycles | Counts 1, 2, then 3; current threefold becomes available |
| Halfmove reaches 99/100 then pawn/capture | Claim false/true then clock resets |
| Stalemate also matches selected material class | Terminal cause is stalemate |
| K+NN versus K or broader material | Partial `common_dead` returns false, no invented general claim |
| Agreement at 0, 1, 2 plies | Reject, reject, accept while active |
| Position/history values from different replays are offered together | No public pairing constructor; typed input rejects |
| Move at history plies 4,095/4,096 | First may reach cap; next rejects atomically without wrap |
| Any event after any close cause | Stable rejection and byte-identical prior state |
| Several input defects coexist | Same frozen primary code in Python/Rust |

Recommended concrete histories/positions, converted to authoritative Position
bytes in the hand fixtures, include:

- threefold: `1.Nf3 Nf6 2.Ng1 Ng8 3.Nf3 Nf6 4.Ng1 Ng8`;
- lost rights after rook returns;
- nominal/non-effective EP after `1.e4` versus the same later occupancy with no
  target;
- legal EP after a black pawn reaches d4 and White plays e2-e4; and
- a pinned EP capturer with a rook line opened by removing the captured pawn.

### 17.2 G3 — source compilation

| Scenario | Required result |
|---|---|
| Locked source | Both paths compile 64 records and agree at every ply/score/byte |
| Canonical no-check/check/mate token | Respectively no suffix/`+`/`#` accepted; every omission or mismatch rejects |
| Pinned geometric SAN candidate | Disambiguation considers only legal movers |
| Necessary file/rank/full disambiguation | Exact minimum accepted; missing/redundant rejected |
| `0-0`, `e.p.`, `++`, LAN, annotation | Source-shape rejection, no repair |
| Promotion missing/wrong context | Reject before output; all Q/R/B/N positive boundaries exist |
| Valid token after mate/stalemate/common-dead | Terminal-continuation rejection at next raw token |
| Terminal score contradicts board | Result contradiction; nonterminal arbitrary score preserved |
| Same stream with same/different score | Later record rejected before sorting |
| 63/65 blocks or one-over resource bound | Reject atomically and allocate only within cap |
| One path or external oracle disagrees | M1 stays open; no majority vote or expected rewrite |

### 17.3 G4 — noninterference

| Mutation | Required invariant |
|---|---|
| Corrupt `FinalFEN`, `CriticalFEN`, `PlyCount`, names/dates while grammar-valid | Same game bytes/set |
| Reorder/add/remove opaque tags | Same game bytes/set |
| Rewrite outer prose/comments/trailing spaces | Same game bytes/set |
| Uniform LF to CRLF | Same game bytes/set; raw identity/spans may differ |
| Safe filename/directory changes | Same game bytes/set |
| Permute 64 fence blocks | Same sorted bytes/identities/ordinals |
| Rewrap tokens/change accepted separators | Same game bytes/set |
| Put comment inside movetext or mix newlines | Reject; not a noninterference promise |

### 17.4 Curriculum/content boundary

| Scenario | Required result |
|---|---|
| Choose-all zero/several selections | Explicit commit terminates; cardinality is not leaked |
| Duplicate/reset/off-board repeated | Stable no-mutation result; budget eventually terminates |
| Response committed twice | First response/log/score immutable |
| Multiple exact answers | Packed practice encodes every exact accepted case; external/result-bearing alternatives remain evaluator-side and all validate without a preferred move |
| Undefined or heuristic score term | Curriculum linter rejects or marks unscored |
| Exact case/parameterization or independently valid transformed equivalent reused across splits | Split linter rejects leakage |
| Shared schema/template with new semantic case | Accepted when every split/leakage key remains distinct |
| Counterfactual pair adjacent or any total cue strategy scores above 1/2 | Schedule/cue audit fails before pretest |
| Hover/focus/disabled/timing reveals answer | Bundle/audit fails |
| Result-bearing payload/seed/map enters public learner bundle | Form invalid before result-bearing pretest |
| Posttest correctness released before delayed closure | Affected delayed evidence invalid |
| One different participant slips in each family | Frozen per-family/person gates decide; no perfection subset |
| One family is weak for everyone | Per-family gate fails despite broad individual performance |
| Participant mastered a family at baseline | Attainment reported, no acquisition credit |
| Family baseline-failure count is 2/3/4/5/6 | No claim, then exact acquisition thresholds 2/3/4/5 |
| Delayed absence | Counts as failure in fixed denominator; immediate data retained |
| Early/late delayed submission | Reported but fixed-denominator delayed failure; no retry |
| Host interruption after/before item commit | Resume next item with immutable log / interrupted item is missing |
| Unequal per-family burden across frozen forms | Form linter rejects before pretest |
| Generic non-chess fixture | Both content decoders validate/step it without chess dependency |
| Missing/multiple/nonfinal root, orphan, unknown record, forward dependency, one-over bound | Fail closed without partial stream |

### 17.5 Repository and reproducibility

- registry rejects missing, unregistered, duplicate-ID, or hash-mismatched suites;
- generated constants drift is detected without rewriting;
- audit/game-set tampering is detected;
- tests pass from repository root and a different working directory where the
  command supports it;
- locale/timezone/hash iteration changes preserve canonical outputs;
- boundary and boundary-plus-one input/output limits are covered;
- a failed/interrupted generation preserves the last accepted artifact; and
- `scripts/check fast`, every live focused area, and `scripts/check full` pass
  without network after the declared environment is prepared.

## 18. Flexible execution envelope

The implementing agent may interleave or reorder work. These are dependency
checkpoints, not prescribed commits:

1. **Contract freeze:** repair M1-era repository guards; land owning specs,
   numeric constants, identity domains, and hand vectors before either language
   treats bytes as canonical.
2. **Semantic convergence:** independently implement/test both cores; investigate
   all fixture/property/mutant/oracle disagreements until the spec or both paths
   are coherent.
3. **Source convergence:** independently implement raw compilers, compare every
   ply, then atomically install the game set/report.
4. **Blueprint closure:** validate curriculum ownership, family/strata/split/
   scoring/cue rules and the minimal content slice without authoring M3.
5. **Milestone audit:** run the full verification matrix, inspect generated
   evidence/diff, and only then update roadmap status.

Useful flexibility includes module layout, internal algorithms, which language
lands first, local test naming, and whether chess/source work proceeds in
parallel. It does **not** include byte/code assignment after consumers ship,
shared semantic implementations, one compiler becoming the other's oracle,
grammar repair, result-threshold changes, or skipped boundary evidence.

If a normative ambiguity appears, resolve it in the smallest owner before
continuing affected work. If the anthology fails the frozen grammar/semantics,
preserve the exact failure and decide explicitly whether the source or profile
is wrong; do not teach either parser to guess. If rights remain unresolved, M1
may complete locally but no publication action is authorized.

## 19. Exit traceability

| M1 deliverable/gate | Required closing evidence |
|---|---|
| `spec/chess-v0.md` + constants | Spec lint, generated drift check, hand identity/semantic vectors |
| Independent chess cores | Cross-language hand/property/metamorphic equality; every named mutant killed; isolated oracle diagnostic |
| `spec/source-v0.md` + compilers | Raw negative/precedence fixtures and all-4,915-ply equality |
| Minimal 64-game IR | Full-byte duplicate check, sorted set bytes/identity, score/size audit |
| Metadata/order noninterference | G4 mutation suite with invariant semantic identities |
| `spec/curriculum-v0.toml` | Schema/linter proves family, stratum, predicate, split, cue, scoring, cap, and cut-order rules |
| Initial `spec/content-v0.md` | Python/Rust hand vectors for stream/primitives/interaction plus non-chess fixture |
| Repository integration | Fast/all focused/full pass; deterministic report regeneration; clean diff checks |

M1 is not complete because all current source games happen to pass one library,
because Python and Rust agree only on final positions, or because prose claims a
predicate exists. Exact independently produced bytes and executable negative
evidence are required.

## 20. Design stress-review record

### 20.1 First adversarial loop — semantic and parser boundaries

The first design review attacked state identity, terminal sequencing, and raw
grammar. It found and this specification closes:

- nominal en-passant bytes versus legal-capture repetition identity;
- separately pairable position/history values and an unbounded history;
- undefined `king_in_check` on zero/multiple kings;
- moves after `common_dead` bypassing a low-level move API;
- castling transit occupancy, an impossible origin-x-ray mutant, and rights
  restoration ambiguity;
- draw agreement before both players move;
- a fictitious separate legality stage after legal-set SAN resolution;
- optional suffix spelling despite an already exact source;
- metadata FEN/count fields becoming accidental validators;
- Unicode character offsets instead of raw byte spans;
- physical-line assumptions in wrapped movetext;
- duplicate detection after sorting/hash-only comparison; and
- a verbose doubled/undefined trace identity threatening the established report
  cap;
- a generic content stream with no entry root or field-schema kind.

### 20.2 Second adversarial loop — learner evidence and pet-project fit

The second review tested fatigue/slips, public-repository leakage, and process
cost. It found and this specification closes:

- same-subset/all-family gates measuring accidental perfection rather than the
  intended family/person evidence;
- the 3/3 small-cohort acquisition cliff despite otherwise high item accuracy;
- no unambiguous end action for choose-all/empty answers;
- a chance-dependent raw 40% eligibility cutoff;
- exact or independently valid transformed case reuse posing as transfer, while
  shared near-transfer templates were incorrectly treated as leaks;
- posttest feedback contaminating delayed evidence;
- public seeds/answers leaking an unexposed form;
- hundreds of participant-unique cases adding complexity without proportionate
  protection, replaced by at most three frozen counterbalanced forms;
- an anthology study record posing as held-out record reading;
- visible cardinality, focus, hover, timing, or order leaking answers;
- language claiming “explanation” that a selection-only interface cannot assess;
- a 48-hour result being overstated as durable retention;
- early/no-show timing, reserve feedback, interruption, and post-baseline freeze
  loopholes; and
- unnecessary controls, classifiers, equating, statistics, frameworks, and
  general serialization machinery.

The resulting contract is strict at semantic/trust boundaries and intentionally
plain elsewhere: fixed bytes, pure functions, flat records, small hand fixtures,
bounded generators, one dev oracle, exact raw counts, and descriptive human
evidence.

## 21. Known limitations accepted by M1

- FIDE 2023 is frozen by locked PDF identity; M1 does not track moving live HTML.
- The practical profile intentionally diverges on rare resignation
  mating-possibility outcomes and omits tournament automatic/procedural rules.
- `common_dead` is useful but deliberately incomplete; false is not proof that
  mate is possible.
- The source grammar accepts only the locked project's canonical subset, not
  arbitrary PGN.
- The external oracle is fallible and profile-mismatched; it is diagnostic only.
- Six selected learners and an approximately two-day delay support only the
  narrow claim in Section 14.8.
- Pre/post retrieval itself may improve delayed performance; the report must say
  so.
- M1 parser-safety caps do not establish M2/M4 physical capacity.
- Anthology provenance/redistribution remains a release concern; this milestone
  makes no rights claim.

These are honest scope boundaries, not deferred infrastructure. Revisit one only
when a later milestone has a concrete consumer or the owner changes product
scope.

## 22. M1 completion checklist

Before changing roadmap M1 status to `Complete`, verify all boxes from generated
or directly runnable evidence:

- [ ] every owning specification exists, is self-contained, and has no
  unresolved normative placeholder;
- [ ] numeric constants and generated language files agree exactly;
- [ ] identity domains/vectors are registered and independently pass;
- [ ] both chess cores pass hand, bounded property/metamorphic, and named-mutant
  evidence;
- [ ] the isolated external diagnostic has no unresolved disagreement;
- [ ] both raw compilers independently accept exactly the locked 64 records and
  agree on every ply, score, game byte, sort order, and identity;
- [ ] source error code/span and boundary cases agree;
- [ ] exact canonical game set and compact report regenerate byte-for-byte;
- [ ] metadata/newline/path/order noninterference passes;
- [ ] curriculum and initial content schemas/lints/vectors pass, including
  interaction, split, cue, feedback, and private-form rules;
- [ ] no M2 transport, M3 full curriculum, private final items, or release work
  has been pulled forward;
- [ ] `scripts/check fast`, every live focused area, and `scripts/check full`
  pass; and
- [ ] the final diff contains no generated scratch data, secrets, host paths,
  timestamps, unrelated user changes, or unexplained dependency.

If any required evidence is unavailable, leave M1 open with the exact blocker.
Do not weaken a gate or mark prose-only completion.
