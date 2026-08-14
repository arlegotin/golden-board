# M1 chess truth, source grammar, and assessment blueprint implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan packet by packet.

| Field | Value |
|---|---|
| Date | 2026-08-14 |
| Roadmap | Revision 3, M1 |
| Execution contract | [`docs/m1-spec.md`](m1-spec.md) |
| Baseline | `5d0acbd` (`M0 (#3)`) |

**Goal:** Close M1 with independently implemented Python and Rust chess truth,
independent raw-source compilation of the locked anthology, one agreed canonical
game set and audit, and executable curriculum/content contracts that are ready
for M2 without pulling M2–M4 work forward.

**Architecture:** Freeze the small owning specifications and hand-authored
vectors first. Build the Python and Rust semantic paths independently from
those neutral inputs, converge them on exact bytes, and publish generated
evidence only after complete candidate equality. Build the generic content and
curriculum checks alongside that work, behind an explicit no-chess dependency
boundary. Root checks compose already-live evidence; they never manufacture a
pass or rewrite tracked outputs.

**Tech stack:** CPython 3.14.6 and `unittest` through locked `uv`; Rust 1.97.1
and Cargo; Python/Rust standard libraries plus the existing M0 dependencies; a
single isolated pinned python-chess development oracle; POSIX `sh`, Git,
SHA-256, canonical-manifest-v0, TOML, and small hand-authored JSON fixtures.

## 1. How to use this plan

This file is a nonnormative execution aid. It owns dependency order, runnable
work packets, and review checkpoints only. Normative authority remains:

1. [`docs/roadmap.md`](roadmap.md) for product scope, milestone gates, status,
   and bounded claims;
2. [`docs/m1-spec.md`](m1-spec.md) for the approved M1 design until the smaller
   owners land;
3. `spec/identity-v0.md`, `spec/chess-v0.md`, `spec/source-v0.md`,
   `spec/content-v0.md`, the neutral constants source, and
   `spec/curriculum-v0.toml` for their declared facts; and
4. hand-authored fixtures and implementations as evidence, never authority.

Do not copy normative byte layouts, code assignments, assessment formulas, or
error precedence into this plan. Follow the owning section directly. If two
owners disagree, pause only the affected lane, repair the smallest owner, and
then resume. A local test expectation, external library, or convenient current
source fact never wins such a disagreement.

The checkboxes are completion evidence, not a prescribed commit history. The
implementer may combine nearby packets, split a packet for review, or run
independent lanes in parallel as long as its dependency barrier and acceptance
gate remain true. No publication, push, release, purchase, or destructive
cleanup is part of this plan.

Writing this plan does not start M1. The first intentional executable M1
deliverable changes M1 to `In progress`; the plan alone leaves it
`Not started`.

## 2. Completion boundary

M1 is complete only when all of the following are true together:

- every M1 owning spec is closed, linted, and free of unresolved normative
  placeholders;
- each generated Python/Rust constants file exactly agrees with the neutral
  owner and its reviewed language-specific candidate;
- the four M1 identity domains and vectors are registered before generated
  semantic evidence is accepted;
- independent Python and Rust chess cores pass the complete evidence required
  by M1 spec Sections 10 and 17.1;
- independent Python and Rust raw compilers agree on every source token/ply,
  state byte string, suffix truth, score, complete game byte string, sort order,
  and identity required by Sections 11–13 and 17.2–17.3;
- one canonical 64-game set and one compact source report regenerate exactly;
- the curriculum TOML is executable and the initial generic content slice is
  decoded and stepped independently in both languages;
- every live root check passes without a network fetch; and
- the roadmap status is changed to `Complete` only after the final audit.

M1 does **not** author the full curriculum, concrete private assessment forms,
M2 transport/bootstrap profiles, M3 lesson/game records, a generic production
transducer, a viewer, a release, or a human-study operation. It also does not
introduce a database, parser/property/mutation framework, generalized CLI,
code-generation framework, CI platform, or governance process.

## 3. Fixed boundaries and useful flexibility

### 3.1 Must remain fixed

- Deterministic bytes, identity preimages/domains, code meanings, ordering, and
  rejection precedence come from their owning specs.
- Python and Rust chess/source semantics remain independent. They may share
  only specs, numeric constants, M0 identity framing, and reviewed hand data.
- Both raw compilers read the complete locked raw source themselves. Neither
  consumes the M0 doctor's recognized blocks/tokens or the other compiler's
  normalized data.
- Full semantic bytes decide equality and sorting. Hashes identify those bytes
  but never replace collision-free comparison.
- All parsing, replay, history, generation, reports, and interactions are
  bounded and fail closed without partial accepted output.
- The content decoder remains generic and has no chess semantic dependency.
- Curriculum gates, fixed denominators, split/leakage rules, and claim ceiling
  are not weakened to make synthetic data or later participants pass.
- Ordinary checks are read-only with respect to tracked generated artifacts.

### 3.2 The implementing agent may choose

- arrays, bitboards, or another bounded private board representation;
- private helper names, module subdivision, and test-file grouping;
- which language lane lands first, and whether content/curriculum runs in
  parallel with chess/source work;
- bounded deterministic property generators, seeds, and case counts, provided
  failures print enough information to replay the exact case;
- whether a small function stays local or is extracted after a second real
  consumer appears;
- whether adjacent review checkpoints become one or several commits; and
- a different private file/crate layout from the illustration below when it
  keeps the same dependency and check boundaries with fewer moving parts.

The agent may not postpone a required edge case as “future hardening,” invent
an expected vector from one implementation, add a focused check that performs
no real work, or resolve a failure by broadening grammar/limits without changing
the correct normative owner.

## 4. Lean target shape

These public artifacts are stable enough to plan against:

| Purpose | Intended path |
|---|---|
| Shared numeric owner | `spec/constants-v0.toml` |
| Chess owner | `spec/chess-v0.md` |
| Source owner | `spec/source-v0.md` |
| Generic content owner | `spec/content-v0.md` |
| Curriculum owner | `spec/curriculum-v0.toml` |
| Hand chess vectors | `conformance/chess-v0.json` |
| Hand raw-source vectors | `conformance/source-v0.json` |
| Hand generic-content vectors | `conformance/content-v0.json` |
| Accepted game set | `reports/game-set-v0.bin` |
| Accepted source audit | `reports/source-compilation-v0.json` |

If an owning spec needs a different public filename, settle it before a
consumer ships and update every reference in the same change. Do not create an
alias or migration layer for an M1 path that has never shipped.

One illustrative private layout is:

```text
python/golden_board/constants.py          generated, reviewed
python/golden_board/constants_codegen.py  tiny candidate/check emitter
python/golden_board/chess.py
python/golden_board/source_compiler.py
python/golden_board/content.py
python/golden_board/curriculum.py
python/tests/test_constants.py
python/tests/test_chess.py
python/tests/test_chess_oracle.py
python/tests/test_source_compiler.py
python/tests/test_content.py
python/tests/test_curriculum.py

crates/gb-foundation/src/constants.rs     generated neutral constants
crates/gb-chess/                          chess core and raw-source compiler
crates/gb-content/                        generic content only
```

Two small M1 Rust crates are a reasonable starting point because they make
“generic content does not link chess” mechanically visible. `gb-chess` may keep
source parsing in a module or bin until a concrete dependency forces a split.
Existing `gb-foundation` can retain identity/manifest and neutral constants.
Use an equivalent fewer-file layout when Cargo dependency inspection and tests
still prove the same separation.

Candidate outputs and failure minimizations go under ignored `artifacts/` or a
temporary directory. Do not retain separate Python/Rust reports, generated
property corpora, oracle snapshots, mutant dashboards, FEN authorities, or
private assessment material.

## 5. Dependency map

```text
P0 -> P1 -> P2
P2 -> P3-Python chess -> P4-Python source -----------┐
P2 -> P3-Rust chess ---> P4-Rust source -------------┼-> P5 source evidence
P3-Python + P3-Rust -> P3 convergence/oracle --------┘
P2 -> P6-Python content ─┐
P2 -> P6-Rust content ───┼-> P7 root integration
P2 -> P6 curriculum ─────┘
P5 ------------------------------------------------------> P7
P7 -> P8 milestone audit and status
```

The Python/Rust lanes are intentionally parallelizable. Keep their coding
contexts clean: each lane reads the owner and hand fixtures, not the other
lane's implementation or candidate output. Comparing completed outputs is a
review step, not an implementation shortcut.

## 6. Working method for every implementation packet

Use the smallest test-first loop that leaves durable evidence:

1. Identify the exact owning rule and add one failing direct test or fixture
   assertion for the next observable behavior.
2. Run only that direct test and confirm it fails for the expected reason, not
   because a module, fixture, or command is missing accidentally.
3. Implement the minimum bounded behavior.
4. Re-run the direct test and the nearest existing focused check.
5. Add boundary-plus-one, atomic-failure, and stable-code evidence where the
   behavior crosses a trust boundary.
6. Admit or expand a public focused area only when it has real tests in both
   required languages.
7. Run `scripts/check fast` after a coherent slice; reserve the expensive full
   differential/oracle/source work for convergence and closing checkpoints.

For generated files, the generator writes a candidate or returns comparison
status. A normal check must report drift without overwriting the tracked file.
For source evidence, each producer writes a complete ignored candidate. The
accepted pair is installed deliberately only after independent validation and
byte equality.

## 7. Packet P0 — Preserve and verify the baseline

**Purpose:** Establish a trustworthy starting point without rewriting the
owner's current worktree.

**Actions**

- [ ] Read `AGENTS.md`, roadmap M1, M1 spec, this plan, and the current diff.
- [ ] Inspect `git status --short`, the current branch/HEAD, and the existing
  diff in agent context; do not create a permanent execution log.
- [ ] Run the existing M0 suite once before executable M1 edits:

```sh
scripts/check full
```

**Acceptance gate**

- Baseline failures are understood before M1 code changes.
- Existing modified/untracked owner work is preserved.
- No dependency is installed and no tracked report is regenerated by this
  packet.

If the baseline fails, fix only a demonstrated M0 regression or record the
specific blocker. Do not obscure it with M1 scaffolding.

## 8. Packet P1 — Admit M1 without admitting empty checks

**Depends on:** P0.

**Primary files:** `docs/roadmap.md`, `python/tests/test_foundation.py`,
`scripts/check`, `README.md`, `AGENTS.md`.

**Actions**

- [ ] With the first executable M1 deliverable, change only roadmap M1 from
  `Not started` to `In progress`; keep the derived header consistent.
- [ ] Replace the M0 repository prohibition on `spec/chess-v0.md` and
  `spec/source-v0.md` with the M1 required-surface rules as files actually land.
- [ ] Make repository text/diff checks cover the whole intended tracked and
  untracked text change rather than an M0 hard-coded path list. Keep an exact
  exception for the reviewed binary game-set path instead of skipping a broad
  directory.
- [ ] Scope existing Rust identity checks to `gb-foundation` so later focused
  areas do not repeatedly run the entire workspace by accident.
- [ ] Keep the current public command list until a new focused area has real
  consumers and passing direct tests.

**Direct checks**

```sh
PYTHONPATH="$PWD/python" uv run --locked --offline --no-python-downloads \
  python -m unittest -v python.tests.test_foundation.RepoContract \
  python.tests.test_foundation.RootCheckCLI
scripts/check focused repo
scripts/check fast
```

**Acceptance gate**

- The repository permits only M1 paths that already have a consumer.
- A typo or trailing space in a newly added text file is not invisible because
  it was absent from an old allowlist.
- Unknown or not-yet-live focused areas still return usage failure.
- No stub crate, empty fixture registration, or always-green check exists.

## 9. Packet P2 — Freeze contracts before consumers

**Depends on:** P1. Chess, source, content, and curriculum drafting may be
parallel; constants, identity registration, and fixture review converge before
P3/P4/P6 consumers claim conformance.

### 9.1 Promote the owners

- [ ] Create `spec/constants-v0.toml` with one closed, typed assignment for
  every numeric value shared by languages. Meanings and precedence stay in the
  relevant semantic spec.
- [ ] Promote M1 spec Sections 6–10 into complete `spec/chess-v0.md`.
- [ ] Promote Sections 11–13 into complete `spec/source-v0.md`, including the
  candidate-versus-retained-report rule.
- [ ] Promote Section 15 into complete `spec/content-v0.md`, explicitly defining
  all record/field bytes, roots, bounds, and interaction results.
- [ ] Create `spec/curriculum-v0.toml` from Section 14 with closed family,
  stratum, predicate, role, split, scoring, cap, cue, and cut-order data.
- [ ] Keep `docs/sources.md` and the locked reference receipts exact for every
  source the promoted owners actually retain; remove explanatory research that
  has no surviving design use instead of padding the ledger.
- [ ] Replace conflicting duplicated normative prose in `docs/m1-spec.md` with
  owner references where needed; retain rationale and execution constraints.
- [ ] Run a placeholder scan and manually inspect each apparent hit:

```sh
rg -n 'TODO|TBD|FIXME|XXX' \
  spec docs/m1-spec.md
```

Schema/spec lint and review—not keyword matching—own detection of an unassigned
live byte, code, bound, formula, or precedence.

### 9.2 Generate neutral constants, narrowly

- [ ] Add a small standard-library generator/checker that reads only the closed
  constants TOML and emits deterministic candidate Python/Rust constants.
- [ ] Reject duplicate/unknown/out-of-range keys and checked-arithmetic errors.
- [ ] Generate reviewed `python/golden_board/constants.py` and
  `crates/gb-foundation/src/constants.rs`.
- [ ] Export the generated Rust module from `gb-foundation` without making the
  generated file a second normative owner.
- [ ] Prove check mode detects hand edits without rewriting them.
- [ ] Do not generate semantic functions, schemas, fixtures, docs, or a generic
  code-generation API.

Default direct check:

```sh
PYTHONPATH="$PWD/python" uv run --locked --offline --no-python-downloads \
  python -m unittest -v python.tests.test_constants
```

The exact tiny candidate interface may be a module function or module command;
it need not become a public CLI.

### 9.3 Register identities and hand fixtures

- [ ] Add the position, repetition-key, game, and game-set identity domains and
  exact hand vectors to `spec/identity-v0.md` and its conformance payload.
- [ ] Hand-author `conformance/chess-v0.json` from M1 spec Section 10.1 and the
  G2 matrix. Replay/history cases contain full standard-start construction
  histories; FEN is at most a human label.
- [ ] Hand-author `conformance/source-v0.json` from exact raw byte examples and
  bounded mutation recipes, preserving byte offsets and CRLF/multibyte cases.
- [ ] Hand-author `conformance/content-v0.json` around a valid non-chess lesson
  plus malformed/boundary interaction cases.
- [ ] Register each payload only after it exists. Include exact SHA-256,
  consumers, version/spec, and honest hand-authored provenance.
- [ ] Make both identity consumers reject missing, extra, duplicate-ID,
  path-escaping, unregistered, or hash-mismatched stable suites.
- [ ] Keep generated/property/oracle data unregistered unless a human later
  reviews and promotes a minimal case.

**Review barrier for P2**

- Every live byte and numeric code has one owner.
- Every stable expected byte is hand-derived/reviewed, not copied from Python,
  Rust, python-chess, or the anthology metadata.
- All size/count arithmetic has an exact maximum and boundary-plus-one case.
- The current anthology's opaque tags cannot become a validation oracle.
- No consumer is allowed to define a missing contract by convenience.

**Checks**

```sh
scripts/check focused identity
scripts/check focused repo
scripts/check fast
```

## 10. Packet P3 — Implement and converge chess truth

**Depends on:** P2 chess/constants/identity/fixture barrier.

Run the Python and Rust lanes independently. If separate agents are available,
give each only the owning specs, constants, and hand fixtures. If one agent does
both, finish and review one lane, clear implementation-specific assumptions,
then implement the second from the specs rather than transliterating code.

### 10.1 Python lane

**Default files:** `python/golden_board/chess.py`,
`python/tests/test_chess.py`.

- [ ] Implement the logical API and validation layering in M1 spec Section 7.
- [ ] Implement exact control, legal movement, special moves, repetition,
  bounded replay/history, terminal/event order, source-score separation, and
  predicate truth from Sections 8–9.
- [ ] Encode/decode exact Position and Move bytes, derive repetition-key bytes,
  and compute the registered position/repetition identities. Complete game and
  game-set construction remains P5 source-evidence work.
- [ ] Return stable structured rejection data and leave prior state byte-equal
  on every failed transition.
- [ ] Consume every hand fixture and add bounded language-local property and
  only-valid metamorphic checks. Print seed and case index on failure.
- [ ] Add direct tests that kill every chess/event mutant in Section 10.3; the
  three source-only mutants are deferred to P4. Use small test-only variants,
  not a mutation framework.

```sh
PYTHONPATH="$PWD/python" uv run --locked --offline --no-python-downloads \
  python -m unittest -v python.tests.test_chess
```

### 10.2 Rust lane

**Default files:** `crates/gb-chess/Cargo.toml`, `src/lib.rs`, private modules,
and `tests/chess.rs`.

- [ ] Independently implement the same public contract and consume the same
  hand fixture.
- [ ] Add the crate to the root Cargo workspace and update `Cargo.lock` only for
  dependencies with a live consumer.
- [ ] Choose a private representation on Rust's merits; do not translate the
  Python representation or call Python.
- [ ] Match exact bytes, ordering, structured rejections, cap behavior, and
  unchanged-state semantics.
- [ ] Add its own bounded property/metamorphic checks and chess/event
  named-mutant kills.

```sh
RUSTC="$(rustup which --toolchain 1.97.1 rustc)" \
  rustup run 1.97.1 cargo test -p gb-chess \
  --test chess --locked --offline
```

### 10.3 Convergence and development oracle

- [ ] Compare complete outputs for every shared hand case, not only final
  positions or hashes.
- [ ] Compare a small neutral differential subset of property/metamorphic cases
  as well. Its input/seed recipe must be hand-authored or independently
  reproduced from a language-neutral definition; neither lane's output may
  supply the other's expected value. Language-local extra generators remain
  welcome.
- [ ] Add one isolated locked development group containing the `chess==1.11.2`
  distribution (the python-chess module) only when its oracle test exists.
  Ordinary runtime modules must not import it.
- [ ] Compare only M1 spec Section 10.4's normalized overlap: legal move sets,
  matching post-move fields, matching-profile mate/stalemate, and explicitly
  constructed repetition/halfmove histories.
- [ ] Keep SAN acceptance, raw FEN strings, `push`, generic outcomes, automatic
  75-move/fivefold rules, and broad dead-material results outside the oracle.
- [ ] Treat an oracle disagreement as diagnostic evidence for human/spec review,
  not a vote and never permission to rewrite a hand vector automatically.
- [ ] Admit `scripts/check focused chess` only after both lanes, shared vectors,
  bounded checks, mutants, and the offline oracle command are real.

Suggested isolated oracle check after the locked group exists:

```sh
PYTHONPATH="$PWD/python" uv run --locked --offline --no-python-downloads \
  --group oracle python -m unittest -v python.tests.test_chess_oracle
```

**P3 acceptance gate**

- Every scenario in M1 spec Section 17.1 passes in both languages.
- `legal_moves` properties qualify replay state below the history resource cap;
  reaching the cap remains a resource condition, not a chess terminal result.
- A closed `GameState` cannot be bypassed through the authoritative event API.
- No expected chess result is derived solely from the external oracle.
- `scripts/check focused chess` and `scripts/check fast` pass.

## 11. Packet P4 — Implement two raw-source compilers

**Depends on:** P2 source owner/fixture. Each language lane may begin as soon as
its own P3 chess lane passes directly; it need not wait for the other language.
P5 still requires both source lanes and P3 cross-language convergence.

Each compiler exposes an equivalent pure operation:

```text
compile_source(raw_bytes) -> complete Compilation
compile_source(raw_bytes) -> SourceReject(primary_code, raw_span)
```

The exact language types are private. Success contains enough complete
source-order rows and provisional records to build the closed report and game
set. Failure exposes no accepted partial compilation.

### 11.1 Python path P

**Default files:** `python/golden_board/source_compiler.py`,
`python/tests/test_source_compiler.py`.

- [ ] Read locked raw bytes through the existing M0 trust-boundary behavior or
  a small neutral extraction of that behavior.
- [ ] Do not import/call `scan_source`, recognized blocks, token projections, or
  source-doctor report data.
- [ ] Implement raw newline/fence/tag/framing/token/SAN state machines and exact
  lowest-stage error precedence/spans directly from source-v0.
- [ ] Resolve SAN only against the Python legal set and replay through the
  Python core.
- [ ] Detect full move-stream duplicates before sorting, including different
  scores; compare full bytes before identities.
- [ ] Emit a complete ignored candidate report and game set through a narrow
  module entry point or test helper.

```sh
PYTHONPATH="$PWD/python" uv run --locked --offline --no-python-downloads \
  python -m unittest -v python.tests.test_source_compiler
```

### 11.2 Rust path R

**Default files:** source modules/tests and, if useful, one narrow candidate bin
inside `crates/gb-chess/`.

- [ ] Independently implement M0-equivalent regular-file/path/size/hash checks
  and direct raw-byte parsing. Reuse no Python or doctor parse result.
- [ ] Use only the Rust chess core for SAN resolution and replay.
- [ ] Match the same primary code/span, complete rows, game bytes, sorting, and
  report bytes from the neutral contracts.
- [ ] Add a new Rust dependency only if the safe locked-file boundary has a
  concrete gap that std/Cargo-lock contents cannot meet; record that narrow
  reason near the dependency.

```sh
RUSTC="$(rustup which --toolchain 1.97.1 rustc)" \
  rustup run 1.97.1 cargo test -p gb-chess \
  --test source --locked --offline
```

### 11.3 Shared negative and resource evidence

- [ ] Consume the same hand raw-byte fixture for encoding/control/newline,
  fence/tag/framing/token, SAN, terminal/score, duplicate, and resource cases.
- [ ] Verify raw byte spans for CRLF and UTF-8 multibyte prefixes, equal-start
  tie order, and zero-width missing-token errors.
- [ ] Exercise exact limits and one-over limits without allocating from an
  unvalidated declaration.
- [ ] Verify a rejection or interruption publishes neither a partial report nor
  a partial accepted game set.
- [ ] Kill the three source-only named mutants explicitly: trusting/ignoring the
  suffix, using geometric rather than legal movers for disambiguation, and
  continuing after terminal closure. Do not add a mutation framework.
- [ ] Keep current source facts measured. The two compilers must independently
  reach 64 records and 4,915 plies; those diagnostic counts do not substitute
  for row-by-row equality.

**P4 acceptance gate**

- Both compilers pass source-v0's positive, negative, precedence, and boundary
  fixtures independently.
- All source semantics come from each path's own chess core.
- No compiler reads `CriticalFEN`, `FinalFEN`, `PlyCount`, player/event tags, or
  comments as chess truth; exact `Result` is the only semantic tag.
- No candidate is tracked or used as the other compiler's expected output.

## 12. Packet P5 — Converge and install canonical source evidence

**Depends on:** P4 both lanes and P3 cross-language convergence/oracle review.

### 12.1 Produce and validate complete candidates

- [ ] Run both producers against the same verified locked file into separate
  fresh ignored/temporary directories. Producers must reject an existing
  nonempty destination rather than mixing old and new files. A reasonable
  narrow interface is:

```sh
candidate_root=$(mktemp -d)
PYTHONPATH="$PWD/python" uv run --locked --offline --no-python-downloads \
  python -m golden_board.source_compiler "$candidate_root/python"
RUSTC="$(rustup which --toolchain 1.97.1 rustc)" \
  rustup run 1.97.1 cargo run -p gb-chess --bin source-candidate \
  --locked --offline -- "$candidate_root/rust"
```

The executor may use an equivalently narrow candidate command; do not build a
general CLI solely to preserve these spellings.

- [ ] Have Python validate P with the Python identity/manifest path and Rust
  validate R with the Rust path, each under the cap and recomputing every report
  relationship in M1 spec Section 13.3. Only then may a coordinator byte-compare
  the two already validated candidates.
- [ ] Compare canonical report bytes, complete game-set bytes, all 4,915 trace
  rows, all 64 complete game IR values, scores, full-byte duplicate checks,
  sort order, and all registered identities.
- [ ] Confirm measured score distribution and IR size are derived from rebuilt
  rows rather than copied from M0 observations or probe notes.
- [ ] Reject both candidates on any disagreement. Preserve ignored diagnostic
  output long enough to locate the first differing field; do not majority-vote
  with python-chess.

### 12.2 Prove G4 noninterference

- [ ] Run every accepted transformation in Sections 13.5 and 17.3 separately.
- [ ] Prove opaque metadata, outer prose, safe path, accepted wrapping/newline,
  and physical record-order changes leave complete canonical game bytes/set
  invariant where promised.
- [ ] Keep raw source hashes, audit spans, and source ordinals free to change
  where the contract says they are observational.
- [ ] Treat comments inside movetext, mixed newlines, alternate starts, and
  malformed spacing as rejection cases, not transformations to normalize.

### 12.3 Install retained evidence deliberately

- [ ] Review the two complete equal candidates before touching tracked output.
- [ ] Install `reports/game-set-v0.bin` from the agreed candidate with a
  same-directory temporary file and atomic replace.
- [ ] Install `reports/source-compilation-v0.json` last, only after it parses
  back and binds the installed game-set identity. The report is the acceptance
  marker for the pair.
- [ ] If interrupted between the two replacements, fail closed on the visible
  report/game mismatch; restore the previously reviewed game-set candidate or
  complete the already-agreed install. Never accept the mixed pair.
- [ ] Normal regeneration writes only ignored/temporary candidates and compares
  them to tracked bytes.
- [ ] Remove no prior tracked evidence destructively; Git remains the recovery
  path for an intentional evidence update.

**P5 acceptance gate**

- `scripts/check focused source` includes the M0 doctor plus both raw compilers,
  full candidate equality, retained artifact comparison, G3, and G4.
- Report and game-set tampering are detected.
- Failure or interruption cannot produce an accepted mixed or partial pair.
- Only one report and one game set are retained; per-language candidates remain
  ignored.

## 13. Packet P6 — Close generic content and curriculum contracts

**Depends on:** P2 content/curriculum/constants/fixture barrier. These three
lanes may proceed while P3–P5 run.

### 13.1 Python generic content

**Default files:** `python/golden_board/content.py`,
`python/tests/test_content.py`.

- [ ] Decode/validate one independently accepted content-v0 logical stream
  atomically, with checked lengths, earlier-only schema/grounding/dependency
  references, one final root, reachability, live primitive schemas, and exact
  M1 safety caps. Compatible lesson control-flow may point forward or cycle only
  when exhaustive bounded-state/event-budget validation proves termination.
- [ ] Step `single`, `set`, and `sequence` interactions through select/reset/
  commit, including empty commit, caps, duplicate precedence, exhaustion, and
  immutable terminal calls.
- [ ] Validate compatible control-flow edges, selection-plus-commit capacity,
  role-gated accepted sets, exact packed practice feedback, and a
  dependency-complete passive trace for every practice node.
- [ ] Keep generic construction values opaque; content parsing cannot upgrade a
  board-like value into `ReplayState` or validate chess truth.
- [ ] Add a small import/dependency audit proving this module imports neither
  the project chess core nor the external oracle.

```sh
PYTHONPATH="$PWD/python" uv run --locked --offline --no-python-downloads \
  python -m unittest -v python.tests.test_content
```

### 13.2 Rust generic content

**Default files:** `crates/gb-content/`.

- [ ] Independently decode/validate/step the same hand fixture and rejection
  cases.
- [ ] Add the crate to the root Cargo workspace and update `Cargo.lock` only for
  dependencies with a live consumer.
- [ ] Keep `gb-content` free of `gb-chess` dependencies, imports, feature edges,
  and hidden test helpers; inspect the Cargo dependency graph as evidence.
- [ ] Match full decoded canonical projections and structured rejections, not
  merely accept/reject booleans.

```sh
RUSTC="$(rustup which --toolchain 1.97.1 rustc)" \
  rustup run 1.97.1 cargo test -p gb-content \
  --test content --locked --offline
```

### 13.3 Curriculum linter and gate arithmetic

**Default files:** `python/golden_board/curriculum.py`,
`python/tests/test_curriculum.py`.

- [ ] Parse the owning TOML with `tomllib`; reject unknown/duplicate/missing IDs,
  unresolved scored predicates, invalid dependencies, and checked-math errors.
- [ ] Validate every mandatory family/stratum/split/role/response shape,
  practice minimum, result-bearing minimum, initial cap, and cut-order rule by
  reference to the TOML owner.
- [ ] Exercise exact family/person/delayed formulas at all small denominator
  boundaries, including ineligible baseline counts and fixed-denominator
  missing/invalid outcomes. Tests read formula data; they do not restate an
  independent prose formula as authority.
- [ ] Check the roadmap/M1-spec human-readable gate summary against the TOML
  projection it summarizes. Keep this a small explicit drift assertion, not a
  general Markdown parser or document-generation system.
- [ ] Reject exact semantic or applicable validated-transform reuse across
  protected splits while permitting matched response schemas and genuinely new
  near-transfer cases.
- [ ] Implement the total deterministic cue strategies in Section 14.7,
  including always-empty commit, select-visible-up-to-cap, tie/fallback rules,
  first-item behavior, and schedule adjacency checks.
- [ ] Prove equal per-family item burden across frozen forms and reject public
  result-bearing seeds, accepted sets, schedules, or answer maps.
- [ ] Cover multiple exact evaluator-side answers without a preferred answer;
  focus/hover/tab/accessibility/disabled/timing/acknowledgement leakage;
  premature feedback; delayed early/late/absence and no-retry behavior; and
  interruption immediately before versus after commit with immutable resume
  state, using small synthetic fixtures.
- [ ] Use small synthetic cases only. Do not author private final forms, recruit
  people, collect personal data, or operationalize the M4 assessment.

```sh
PYTHONPATH="$PWD/python" uv run --locked --offline --no-python-downloads \
  python -m unittest -v python.tests.test_curriculum
```

**P6 acceptance gate**

- Every scenario in M1 spec Section 17.4 has executable evidence.
- Both languages accept and step the same non-chess fixture with no chess
  semantic dependency.
- Curriculum terms either resolve to an owning predicate or are explicitly
  unscored.
- No generic production transducer, transport profile, authored lesson graph,
  concrete assessment form, or human protocol execution has slipped into M1.
- `scripts/check focused content`, `scripts/check focused curriculum`, and
  `scripts/check fast` pass after the corresponding areas are admitted.

## 14. Packet P7 — Finalize the public repository checks

**Depends on:** P3, P5, and P6 acceptance gates.

**Primary files:** `scripts/check`, repository contract tests, `README.md`,
`AGENTS.md`, Cargo/uv lock files only for dependencies with live consumers.

- [ ] Reconcile the focused areas admitted by P3, P5, and P6. Add an area only
  after its direct suite is real:

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

- [ ] Keep `focused source` responsible for both the M0 doctor and M1 raw-source
  compilation/convergence. Do not create a second overlapping source command.
- [ ] Make each Rust focused area target its owning package/test instead of
  `--workspace --all-targets`.
- [ ] Let `fast` cover format/schema/generated drift and bounded unit subsets.
- [ ] Let each focused area cover its complete owning feature without silently
  depending on another language's candidate output.
- [ ] Let `full` compose each expensive suite once: hand vectors, properties,
  mutants, isolated oracle, both source regenerations, G4, artifact comparison,
  content/curriculum, and repository policy.
- [ ] Preserve usage error code 2 for unknown modes/areas and actionable failure
  labels for missing offline dependencies.
- [ ] Update README and AGENTS command snippets only when every listed command
  works; keep the existing M1 document links and keep AGENTS concise.
- [ ] Ensure no check writes tracked constants, reports, game bytes, or registry
  hashes as a side effect.

**Checks**

```sh
scripts/check fast
scripts/check focused identity
scripts/check focused chess
scripts/check focused source
scripts/check focused curriculum
scripts/check focused content
scripts/check focused repo
scripts/check full
```

**Acceptance gate**

- Each public area exercises the evidence its name claims.
- `full` does not multiply whole-workspace Rust runs unnecessarily.
- Commands work from repository root and supported nested working directories.
- Offline cache absence fails with a precise acquisition instruction; checks do
  not fetch automatically.

## 15. Packet P8 — Stress, audit, and close M1

**Depends on:** every earlier packet.

### 15.1 Candidate audit

- [ ] Run the entire M1 verification matrix in `docs/m1-spec.md` Section 17 and
  trace every completion-checklist item in Section 22 to runnable evidence. Do
  not turn the spec checkboxes into another mutable status ledger.
- [ ] Rebuild candidate constants, both source reports, and both game sets in
  fresh ignored/temp directories; compare without rewriting tracked files.
- [ ] Run deterministic variants for safe working directory/path, `TZ`, locale,
  Python hash seed/iteration order, temp directory, and producer order.
- [ ] Tamper one constant, fixture/registry hash, report field, and game byte in
  disposable copies and confirm each relevant gate fails closed.
- [ ] Simulate a producer failure and an interrupted evidence install; confirm
  no partial output is accepted and the retained pair can be recovered.
- [ ] Inspect the dependency graph: runtime code has no oracle dependency and
  generic content has no chess edge.
- [ ] Inspect the final diff for scratch/minimized cases, host paths,
  timestamps, secrets/private form material, unrelated owner changes, and
  unexplained dependencies.

### 15.2 Final commands

P7 has already exercised every public command independently. After the stress
fixes above, run the composed closing gate once:

```sh
scripts/check full
```

Record only the compact evidence needed for the roadmap status: date, full-check
result, accepted game-set identity, and source-report SHA-256. Raw logs and
candidate directories remain ignored and need not be preserved.

### 15.3 Status transition

- [ ] If every M1 deliverable, checklist item, and G2–G4 gate passes, change M1
  to `Complete — <date>; scripts/check full; game-set <identity>; report SHA-256
  <digest>` and update the derived header to current milestone M2.
- [ ] Re-run `scripts/check focused repo` after the status-only edit. Re-run
  `scripts/check full` only if that edit also changed executable/spec/evidence
  bytes.
- [ ] If an external prerequisite truly prevents progress, use
  `Blocked — <specific prerequisite>`.
- [ ] If an internal spec/code/evidence failure remains, use
  `Needs revision — <specific failed gate>` or leave `In progress` while work
  continues. Never mark complete because most examples pass.
- [ ] Do not publish or push. Rights limits remain as recorded in
  `docs/sources.md`.

## 16. Failure and recovery guide

| Situation | Required response |
|---|---|
| Normative ambiguity | Pause the affected lane; repair the smallest owner; rerun its fixture consumers |
| Python/Rust chess disagreement | Compare first complete differing input/state; no majority vote or shared rewrite |
| External oracle disagreement | Treat as diagnostic; inspect profile mismatch and project rule; never auto-update expected data |
| One compiler rejects/differs | Install nothing; retain bounded ignored diagnostics; M1 remains open |
| Source lock/path/file-kind/hash failure | Reject before parsing or publishing output |
| Generated constants drift | Fail and show candidate diff; explicit reviewed regeneration only |
| Missing/unregistered/hash-mismatched fixture | Fail closed; do not skip that suite |
| Report contradiction/oversize/noncanonical bytes | Reject whole report; remove duplicated presentation before considering a cap change |
| Crash during candidate generation | Discard incomplete candidate; tracked evidence remains untouched |
| Crash between reviewed pair installs | Old report cannot validate new game set; accept neither until the agreed pair is restored/completed |
| Environment/path/order changes bytes | Reproducibility failure; remove ambient input rather than allow variation |
| Locked source violates frozen grammar | Preserve exact code/span; decide explicitly whether source or spec owner is wrong |
| Oracle group absent offline | Ordinary checks remain usable; full reports the exact one-time sync prerequisite |
| Curriculum synthetic case fails a gate | Fix schema/linter or acknowledge failed gate; never lower the formula to pass |
| M2/M3 need appears during M1 | Record the concrete need and defer it unless M1's declared consumer cannot work without it |
| Rights remain unresolved | M1 may close locally; no publication is authorized |

## 17. Optional review checkpoints

These are useful diff boundaries, not mandatory commits:

1. M1 admitted; repository guards fixed.
2. Owners/constants/identity/hand fixtures frozen.
3. Both chess cores converged.
4. Both raw compilers and retained evidence converged.
5. Content/curriculum contracts closed.
6. Root integration and M1 completion audit.

Combine a checkpoint when the smaller diff would leave the repository invalid.
Split one when it materially improves independent review. Do not add empty
scaffolding merely to make the sequence look tidy.

## 18. Plan traceability

| Required outcome | Primary packet | Closing evidence |
|---|---|---|
| One owner per M1 fact | P2 | owner/placeholder review and generated drift checks |
| G2 independent chess truth | P3 | both direct suites, hand/property/metamorphic/mutant/oracle evidence |
| G3 raw-source equality | P4–P5 | raw negative suite and all-row/full-byte candidate equality |
| G4 source noninterference | P5 | transformation suite over complete semantic outputs |
| Canonical 64-game object/report | P5 | parse-back, recomputation, identity, tamper, regeneration checks |
| Executable assessment blueprint | P6 | curriculum linter and synthetic boundary/cue/leakage cases |
| Initial generic content slice | P6 | two independent decoders/steppers and non-chess fixture |
| Deterministic repository surface | P7–P8 | all public commands, environment variants, final diff audit |
| Honest milestone status | P8 | roadmap transition only after every earlier row passes |

The coding agent is free to improve the local route between these evidence
points. It is not free to weaken or reinterpret them.

## 19. Plan stress-review record

Two adversarial passes were applied before this plan was marked ready for use.

**Loop 1 — dependency and failure correctness** tested independent-lane
sequencing, generated expectations, malformed source, stale candidates,
content cycles, and interrupted evidence. It found and corrected:

- source-only mutants assigned too early to the chess-core packet;
- no neutral rule for cross-language property/metamorphic comparison;
- unnecessary blocking of one source lane on the other chess implementation;
- missing Cargo workspace/constant-module wiring;
- an overbroad “earlier-only” content-reference rule that excluded bounded
  lesson control flow;
- incomplete executable content/assessment leakage and interruption cases;
- reusable candidate directories that could retain stale output; and
- candidate comparison before each language had validated its own output.

**Loop 2 — pet-project simplicity and rigidity** tested the plan against a
solo maintainer, a dirty current branch, a missing offline oracle cache, and a
late spec disagreement. It removed a second status surface, made private layout
illustrative, narrowed placeholder scanning, allowed each language lane to
advance independently, admitted focused checks only when live, and reduced the
closing command repetition to one composed full run plus a status-only repo
check.

The review deliberately kept the expensive parts that protect Golden Board's
actual claim: independent chess/source semantics, complete 4,915-ply and
64-game byte comparison, stable raw errors, named mutants, bounded properties,
the diagnostic oracle, generic no-chess content proof, curriculum gate/cue
linting, and deterministic fail-closed evidence. It did not add a workflow
system or multi-file transaction manager: candidate generation never touches
tracked outputs, the report is installed last as the acceptance marker, a
mixed pair always rejects, and ordinary Git recovery is sufficient for this
explicit maintainer-only authoring action.
