# M2 full-carrier bootstrap and transport feasibility implementation plan

| Field | Value |
|---|---|
| Prepared | 2026-08-20 |
| Roadmap | Revision 10, M2 Linux verifier provenance refresh |
| Execution contract | [`docs/m2-spec.md`](m2-spec.md) |
| Baseline | `0feaf4b559f48507f2457e6d203f25c969a98589` (`m2` branch) |
| Plan status | Gates 1–7 remain exact for the sole R3 v7 candidate; gate 8 is reopened only for the acquired Linux verifier provenance refresh |

**Goal:** Execute M2 on the current branch and leave a bounded, independently
reproducible proof that an elite technical recipient unit can recover a real
generic content stream from the full raw-bit carrier, while a fresh
chess-naive learner can use that exact stream through the generic runner. The
milestone compares a simple and a stronger protected transport fairly, retains
at most two lowest-complexity finalists, and records one provisional preference
without pretending M2 has selected the final M4 profile or dimensions.

**R3 supersession:** The original comparison text records the R1/R2 work and
must not be rerun as if it were pending. Every R2 candidate failed before gate
7. Revision 9 admits only the pre-result v7 candidate. Its exact owner/route
barrier in [`docs/m2-r3-design.md`](m2-r3-design.md) first closed, and gates
1–5 passed for an independently reproduced tree. A final pre-D audit first
closed the v1 damage-evidence schema and then the exact independence-proof
witness counts and violation units. The dependent owner DAG was atomically
re-frozen, Python and Rust independently reproduced the same canonical tree,
and gates 1–5 passed. Two complete gate-6 attempts then ended in
independent/tooling disagreement and wrote nothing. The pre-attempt tree is
archived. After the bounded convergence repairs, the complete rerun converged
across the oracle, fresh Python decoder, and persistent Rust decoder and
atomically published the canonical gate-6 bundle. Its raw SHA-256 is
`77697d720bf0df357217d739935931b470cdfda24f7ed3be4b92fc2e6f10e497`
and manifest identity is
`b7024bed03ef0ee4b7c0f89bd5ac626a285dc35c39d8642a3d820570670e7177`.
The D0–D7 counts are `[16, 4, 256, 128, 1841, 21, 7364, 408]` (10,038
total); all eight families and four boundary KATs pass with zero wrong
accepts. Gate 7 then atomically added the independently byte-identical proof,
raw SHA-256
`e73a4a186af1a79d1bea3ec73911aa9c4da7cde09e74f36d08e8019d26082964`,
identity
`303b3f710c17517072221156bc5376841970720da3081ae82193243ce009eb04`;
all nine predicates pass with zero violations. The candidate passes gates
1–7 and awaits gate 8; no finalist or preference is declared.

**Architecture:** Freeze the shared normative owners, build the real content
slice, then freeze every result-sensitive policy against that actual input.
Build bootstrap routes and candidate implementations independently in Python
and Rust; generate complete provisional carriers before running the frozen
damage policy; reproduce every gate-8 candidate natively and in clean Linux
before selection; then expose only the preferred frozen carrier to simple,
checkpointed technical and learner pilots.
Ignored working artifacts feed one compact tracked report. No raw participant
workspace, release package, service, database, or workflow system is part of
the architecture.

**Tech stack:** the existing CPython 3.14.6/`uv`, Rust 1.97.1/Cargo, POSIX
`sh`, Git, canonical-manifest-v0, SHA-256, TOML and JSON subset; one pinned
`linux/arm64` container image for clean verification; standard-library code by
default. New dependencies require a concrete smaller implementation than a
bounded local implementation and must work in locked offline checks.

## 1. How to use this plan

This is a nonnormative execution aid. It owns packet order, parallel-work
boundaries, practical check cadence, and review points only. Normative authority
remains, in order:

1. [`docs/roadmap.md`](roadmap.md) for mission, recipient claims, gates,
   milestone scope, and status;
2. [`docs/m2-r3-design.md`](m2-r3-design.md) for the incompatible pre-result R3
   restart until its exact owners are promoted together;
3. [`docs/m2-spec.md`](m2-spec.md) for the unchanged M2 execution contract until
   each smaller owner is promoted;
4. the exact owners under `spec/` for their declared byte, algorithm, policy,
   limit, damage, and Gate-8 evidence domains, including the active-R3
   `spec/gate8-policy-v0.toml`; and
5. fixtures, candidate artifacts, implementations, reports, and participant
   statements as evidence, never authority over a conflicting owner.

Do not copy normative wire constants, rejection precedence, damage seeds,
candidate parameters, report shapes, or human thresholds from this plan into
code. Read the owning specification. If two owners disagree, pause only the
affected lane, repair the smallest owner, add a case that exposes the conflict,
and resume. A convenient implementation, external library, participant guess,
or already-generated carrier never resolves normative ambiguity.

The checkboxes show executable progress; they do not prescribe commit count,
branch strategy, or a meeting/sign-off process. Adjacent packets may be
combined, an oversized packet may be split, and independent lanes may run in
parallel if every stated dependency and freeze remains true. No publication,
push, purchase, participant outreach, or destructive cleanup is implied by a
checkbox. Human outreach begins only with the owner's ordinary authorization
and the plain participation note in the M2 specification.

Writing or reviewing the original plan did not change roadmap M2 from
`Not started`. M2 is now `In progress` because R1/R2 executed and the
revision-9 pre-result restart design is admitted; only roadmap Section 13 may
change that state.
Likewise, completing all automated packets without fresh human evidence yields
`Candidate ready — independent validation pending`, not a fabricated M2 pass.

## 2. Completion boundary

M2 is complete only when all of these are true together:

- the promoted bootstrap, candidate-policy, provisional-limit, damage-policy,
  and amended content owners are closed and have live consumers;
- four complete shell routes and both recipe interpreters satisfy the
  knowledge-use, held-out, ablation, headroom, and bounded-work gates;
- the real M2 `ContentStream`, slice, all sixty-four atomic games, inventory,
  capacity/reserve/load-probe sections, and carrier ownership reconcile exactly;
- the simple extended-Hamming/copy path and stronger `RS(255,191)` path use the
  same common grammar, semantic envelope, mapping family, damage policy, and
  objective comparison harness;
- both languages independently agree on every required KAT, protected byte,
  carrier bit, state, ledger, damage observation, and recovered output for each
  passing candidate;
- every retained candidate passes automated gates 1--8, including its native
  and clean-Linux reproduction, before the deterministic finalist/preference
  rule is applied;
- the preferred full carrier is independently reconstructed by one qualifying
  fresh elite recipient unit under the exact information condition, clock,
  checkpoint, held-out, and retry rules;
- one fresh individual learner passes the latest label-suppressed micro-slice
  using the exact independently recovered content-stream bytes;
- the compact M2 report, pilot envelope, and one concise decision entry
  regenerate and remain internally consistent without private participant data
  or self-referential hashes;
- `scripts/check release` passes as the M2 orchestrator; and
- roadmap status changes to Complete only after all of the above evidence is
  installed and checked.

M2 does **not** freeze final `profile-v0`, final dimensions, the production
M3 transducer/curriculum, actual RT0--RT4 closure, a release package, the M6
explorer, population-level human claims, or public redistribution rights. It
does not add CI hosting, telemetry, a database, an issue workflow, an approval
matrix, an NDA, remote proctoring, or a research-management platform.

## 3. Fixed boundaries and useful flexibility

### 3.1 Must remain fixed

- Deterministic bytes, exact transforms, candidate tuples, CRC/ECC conventions,
  recovery states, validation precedence, limits, and damage promises come from
  their smallest owner and fail closed.
- `spec/constants-v0.toml` stays byte-identical during M2 because completed M1
  evidence hashes the entire file. M2-only codes live in their M2 owners and
  have independently checked language mirrors.
- Python and Rust implement transport, recipes, candidate codecs, mapping, and
  recovery independently. Shared inputs are owning specs, small reviewed
  fixtures, the real semantic stream, and declared policies—not another
  implementation's code or generated answers.
- The common 191-byte plain-block/section grammar and the same complete
  semantic/capacity harness apply to every candidate. A candidate does not get
  friendlier content, a private framing shortcut, or a different damage corpus.
- Candidate tuples, recipe-language union, mapping family, damage
  operators/seeds, objective metrics, and selection rules freeze before their
  result-bearing outputs are observed.
- Provisional limits derive before outcomes across the full predeclared
  candidate-tuple set. Real complete carriers exist before D0--D7 is realized.
  Every gate-8 candidate is reproduced before finalist selection.
- Result-bearing participant material, tasks, success rules, help taxonomy,
  expected answers, and release order freeze before exposure. No threshold,
  stop rule, or rubric is lowered after an unsuccessful round.
- A technical recipient unit is one elite individual or one fixed team of two
  to four whose skills may be collective. A team result remains explicitly a
  team result. Trial, error, backtracking, multiple sessions, and a small pool
  of hypotheses are expected rather than penalized.
- Recipients are told the sequence is intentional, finite, important,
  potentially profound, benign/nonhostile, and worth sustained work. They are
  not told its project name, square shape, code, chess content, or answer.
- The first human attempt need not succeed. The exact retry/redesign/freshness
  rules prevent both first-attempt fragility and recruiting indefinitely until
  a favorable result appears.
- Friendly participants receive one understandable participation note and may
  stop. Raw working data stays private and permission-aware. This does not
  become secrecy theatre, compliance ceremony, or a bureaucracy.
- Normal checks never execute participant-submitted code from discovery paths;
  the evaluator handles it explicitly in a disposable, bounded, network-off
  environment.

### 3.2 The implementing agent may choose

Without amending this plan, the implementing agent may:

- choose private module, crate, helper, and test-file layout;
- choose which language or candidate family lands first, while keeping the
  independent lanes clean until comparison;
- implement an exact bounded algorithm differently in each language;
- combine or split packets and review checkpoints when the dependency graph
  remains true;
- parallelize content authoring, container acquisition, neutral pilot-template
  work, hand-vector review, and independent language implementations;
- choose temporary-directory and ignored-artifact organization;
- keep a helper local until a second real consumer appears, or factor it when
  doing so makes the exact boundary easier to review;
- use direct tests, generated bounded tests, exhaustive small domains, and
  named mutants in any sensible mixture that closes the required matrix;
- recruit an elite individual or a complementary team, and schedule any number
  of sessions inside the frozen total clock; and
- use equivalent plain email/filesystem coordination for friendly participants
  instead of special-purpose study software.

The agent may not add a result-aware candidate, silently change a seed, use a
participant answer as an expected vector, make one implementation an oracle,
weaken a failure into `not_evaluated`, generalize one pilot beyond its frozen
envelope, or report a diagnostic/hinted/prior-contaminated result as the
qualifying pass.

## 4. Lean target shape

These public artifacts are stable enough to plan against:

| Purpose | Intended path |
|---|---|
| Bootstrap/common grammar/recipe owner | `spec/bootstrap-v0.md` |
| Candidate tuples and selection owner | `spec/profile-policy-v0.toml` |
| Pre-result union limits | `spec/profile-limits-v0.toml` |
| Candidate-independent damage owner | `spec/damage-policy-v0.toml` |
| Generic content bytes/API owner | `spec/content-v0.md` |
| Generic runner/evidence owner | `spec/runner-v0.md` |
| Small transport conformance vectors | `conformance/` plus `conformance/registry.toml` |
| Reviewed real M2 slice declaration | `studies/m2/slice-v0.json` |
| Clean Linux implementation | `.dockerignore` and `tools/linux/` |
| Active-R3 Gate-8 evidence/report overlay owner | `spec/gate8-policy-v0.toml` |
| Blank human-work templates | `studies/m2/templates/` |
| Compact automated/human evidence | `reports/m2-feasibility-v0.json` |
| Consequential finalist decision | one short entry in `docs/decisions.md` |

R3 keeps those v0 paths as historical fixture owners. Its exact executable
owners are `spec/bootstrap-v1.md`, `spec/profile-policy-v1.toml`,
`spec/damage-policy-v1.toml`, `spec/route-data-v1.json`, and
`spec/profile-limits-v1.toml`, with `conformance/m2-r3-owner-v1.json` and the
admission record in `spec/m2-r3-owner-promotion-v1.toml`. The smallest
outcome-independent owner for pending Gate-8 paths, schemas, preimages,
selection, bundles, Linux integration, and the report overlay is
`spec/gate8-policy-v0.toml`. Python and Rust
reproduced the final generated owner bytes independently. The final damage,
limits, and promotion SHA-256 values are respectively
`b3b28f00d3ba04addbed4517eb1abb4ecd02796176eaaecdbc1d47f1f39509df`,
`32c2bd0cb978eb800bed7f8ac1c7db223b593b4cf3bad951a9ce4cdc3a568902`,
and `8c30ae216f5a3fd8ee13f2821d38412afa6c50303c9140cbe54da8610df9cd8d`.
The current canonical v7 gates-1--5 tree is exact with candidate-manifest
identity
`d783917d34bc6fb472ea7e20c989562092707c516195019434e01f2bc6f68681`
and raw manifest SHA-256
`38839aa28561ff2bec0997a80d8dc938e876526c25f40e23b6a78844f8fc1d86`.
Python and Rust produced all six files byte for byte, and the read-only
generation check passes. The preceding raw manifest
`4439abb20aeb4943d9f3dddd4b2b914c08f3a411b791d2ced797533351168019`
with identity
`69b4052299e43a675683361e6a7fa83798b7b3646c873233cfbdd18432ac4cf4`
remains immutable history under the pre-gate-6 convergence archive.
Two complete gate-6 attempts executed R3 D0–D7 but ended in
independent/tooling disagreement and wrote no canonical damage bundle. After
the bounded repairs, the complete rerun converged and published the canonical
gate-6 bundle with raw SHA-256
`77697d720bf0df357217d739935931b470cdfda24f7ed3be4b92fc2e6f10e497`.
Gate 7 passed all nine independence predicates and published proof SHA-256
`e73a4a186af1a79d1bea3ec73911aa9c4da7cde09e74f36d08e8019d26082964`.

One reasonable private code shape is:

```text
python/golden_board/transport.py
python/golden_board/bootstrap.py
python/golden_board/m2_evidence.py
python/tests/test_transport.py
python/tests/test_m2_evidence.py

crates/gb-transport/
  src/lib.rs
  tests/transport.rs

tools/linux/
  Dockerfile
  verify.sh
  snapshot.sh
```

This is illustrative, not a required framework. Keeping bootstrap and transport
in one bounded module/crate is preferable if it is clearer. Splitting evidence
generation into a tiny executable is reasonable if both language libraries
remain independently testable. Do not create one crate/package per wire type,
a plugin architecture, a general codec framework, a participant web app, or a
generic report platform.

Large candidate carriers, damage corpora, execution snapshots, private pilot
instances, minimized failures, and raw logs stay under ignored `artifacts/` or
temporary directories. Only small hand-reviewed fixtures, promoted owners,
blank templates, the provisional limits file, compact report, and decision note
are tracked.

## 5. Dependency and parallel-work map

```text
P0 baseline
  |
  v
P1 phase admission + real clean-Linux foundation
  |
  v
P2 promote shared grammar/content owners + exact reference receipts
  |
  v
P3 implement shared grammar and the real semantic slice
  |
  v
P4a co-freeze result-sensitive policy and full-tuple limits
  |---------------------------|
  v                           v
P4b four shell routes         P5 independent candidate codecs/checks
  |---------------------------|
  |
  v
P6 complete limit-consistent carrier/capacity/ownership manifestations
  |
  v
P7 frozen D0--D7 + gates 1--7 + objective metrics
  |
  v
P8 gate-8 native/Linux reproduction -> selection -> Candidate-ready report
  |
  v
P9 qualifying technical reconstruction
  |
  v
P10 exact-stream learner micro-pilot
  |
  v
P11 final report/decision/release/status closure
```

Within P3, the two content-authoring/common-grammar language lanes can proceed
in parallel. After P4's policy/limits freeze, P4 route work may proceed beside
P5; within P5, Python/Rust and Hamming/RS/check lanes can proceed in parallel
from the same owners. Neutral recruitment preparation and blank templates may
proceed alongside P3--P8, but
no task-specific material is exposed until P8 freezes the preferred carrier and
bundle. Container-image acquisition may also happen early; result-bearing
native/Linux candidate reproduction waits for P7.

The four hard barriers are:

1. no result-bearing candidate/damage comparison before P4's policies freeze;
2. no damage realization before P6's complete candidate carriers exist;
3. no finalist/preference selection before all reached gate-8 reproductions;
4. no human exposure before the exact candidate, bundle, questions, clocks,
   evaluator answers, and release order are sealed.

## 6. Working method for every packet

Use a small evidence-first loop:

1. Identify the exact owning rule and the next observable behavior.
2. Add the smallest direct test, hand vector, or generated bounded case that
   fails for the intended reason.
3. Implement only enough bounded behavior to satisfy that rule.
4. Run the direct test and nearest live focused check.
5. Add boundary-plus-one, malformed/ambiguous, atomic-failure, and stable-state
   evidence at each trust boundary.
6. Compare completed independent candidates only after each has validated its
   own output.
7. Run `scripts/check fast` after a coherent slice; run expensive generation,
   damage, Linux, and full checks only at the review points below.

Generated tools write to a new ignored/temp candidate path and compare with
tracked evidence. Ordinary checks never rewrite tracked output. Promote a
candidate only through an explicit reviewed copy/patch after its independent
derivation and validation pass. A crash leaves the last tracked evidence
untouched.

When a packet finds a genuine spec defect, stop only that dependency lane.
Record the smallest failing case, repair the smallest normative owner, rerun
all consumers of that fact, and continue. When a candidate simply fails a
predeclared gate, retain the failure evidence and progress according to the
frozen policy; do not repair the gate around the result.

## 7. Packet P0 — Preserve and verify the M1 baseline

**Purpose:** Start from known-good completed M1 evidence without overwriting the
owner's current branch or confusing planning work with M2 execution.

**Actions**

- [ ] Read `AGENTS.md`, roadmap M2/status, M2 spec, this plan, and the complete
  current diff.
- [ ] Record in working context—not a new tracked log—the current branch, HEAD,
  tracked/untracked changes, toolchain availability, and whether any change
  overlaps intended M2 files.
- [ ] Verify the baseline with the current public command before executable M2
  edits:

```sh
scripts/check full
```

- [ ] Recompute/check the existing M1 report and `spec/constants-v0.toml`
  identities using the existing suite. Do not regenerate or edit them.
- [ ] Confirm roadmap M2 remains `Not started` throughout this packet.

**Acceptance gate**

- M0/M1 evidence remains byte-identical and green.
- Existing user changes are preserved.
- Any baseline failure has a concrete cause before M2 code is added.
- No dependency, container image, report, or participant operation is created
  merely to satisfy preflight.

If baseline verification is blocked only by a missing declared cache/tool,
follow its documented explicit acquisition route. Do not make ordinary checks
install or fetch it implicitly.

## 8. Packet P1 — Admit M2 and make clean Linux real

**Depends on:** P0.

**Purpose:** Retire M1's intentional future-path guards only as their first real
M2 consumers land, and establish the promised environment-independent check
before transport results need it.

**Actions**

- [ ] With the first executable M2 deliverable, change only roadmap M2 to
  `In progress` and keep the derived header/status grammar consistent.
- [ ] Replace the exact M1 prohibitions on `.dockerignore`, `tools/linux/`, and
  later `docs/decisions.md` with phase-aware admission. Admit a decision file
  only for P11's measured selection or for a roadmap-Section-3.5 incompatible
  pre-result restart such as R3; the latter contains no finalist claim.
- [ ] Make repository hygiene cover every tracked regular text file plus every
  nonignored untracked file, retaining only the exact existing reviewed binary
  exclusions.
- [ ] Add the Linux image acquisition and verify path from M2 spec Section 15.7:
  pinned digest **and** exact `linux/arm64` platform, explicit one-time
  network-enabled acquisition, cache-hidden/network-disabled verification, and
  disposable project build/test storage.
- [ ] Preserve the complete host execution input's HEAD/index/worktree/untracked
  layers, including staged-plus-unstaged bytes, deletions, modes, and
  tombstones. Compare the transient complete snapshot identity without storing
  that self-referential hash inside the repository.
- [ ] Make `scripts/check linux` dispatch before Python/Rust host preflight so
  its host dependencies are only Git plus the declared container runtime.
- [ ] Run current root `full` inside Linux from the exact snapshot. Do not add a
  `linux` mode that merely checks a Dockerfile or echoes success.
- [ ] Update CLI tests, README/AGENTS command text, and usage together when the
  live mode lands. Keep `release` absent until P8 has a real M2 report consumer.
- [ ] Extend phase-aware required-path tests only for files that now exist.

**Direct checks**

```sh
scripts/check focused repo
scripts/check linux
scripts/check fast
```

The Linux test suite also exercises a host without `uv`, Rustup, or project
caches; wrong platform/digest, a network-enabled verify, a changed Git layer,
and a source-snapshot mismatch must fail actionably.

**Acceptance gate**

- Native and clean-Linux current `full` consume the same exact source state and
  pass offline.
- No host cache or old `HEAD` can substitute for current dirty bytes.
- M2 paths enter repository hygiene as real consumers, not placeholders.
- Existing M1 source report/constants evidence remains unchanged.

## 9. Packet P2 — Promote shared owners and lock exact references

**Depends on:** P1. Shared-owner drafting and exact reference acquisition may
proceed in parallel. Result-sensitive candidate/damage/selection policy freezes
only after P3 supplies the real semantic slice.

**Purpose:** Close the candidate-neutral byte, recipe-language, content-API,
and external-reference foundations needed to build the real semantic input,
without prematurely choosing outcomes from an invented slice.

**Actions**

- [ ] Promote the candidate-neutral parts of `spec/bootstrap-v0.md`: common
  fragment/section/inventory/tier-frame grammar, exact singular content-stream
  assembly, closed recipe data language/types, shell grounding primitives, and
  rejection/state behavior. Candidate-specific recipes wait for P4/P5.
- [ ] Amend `spec/content-v0.md` only for the bounded checked authoring input,
  immutable projection view, committed-response/run-event view, and ownership
  needed by the M2 generic runner. Keep content wire bytes and M1 parser/
  transition truth unchanged unless an explicit smaller-owner defect requires
  reopening M1.
- [ ] Define the candidate-neutral semantic/slice/assembly manifest schemas and
  M2-only common-grammar codes in `spec/bootstrap-v0.md`. Keep
  `spec/constants-v0.toml` byte-frozen and test its identity. Candidate- and
  damage-specific schemas/codes freeze in P4.
- [ ] Acquire and lock only exact external reference editions that supply a
  parameter or retained KAT to a tuple being prepared for the bounded P4
  comparison. Extend both source-lock consumers' closed role/inventory table
  additively, preserve every M0 receipt byte/meaning, and keep their exact
  outer/string bounds. Do not lock general reading-list material.
- [ ] Freeze only the shared common block/section/assembly and recipe-operation
  type system needed by P3. Stage independently derived Hamming/RS/CRC values
  for the P4 policy review, but do not call a candidate tuple/policy promoted
  until the real semantic stream and envelope exist.
- [ ] Add small candidate-neutral grammar/content rejection fixtures to the
  existing closed conformance registry only when both consumers exist. KATs for
  candidate profiles land after their P4 owner and P5 consumers are live. Full
  carriers and large generated boundary corpora stay out of the registry.
- [ ] Review every live `measured`/`generated` field: its derivation and gate
  must be exact even though its future value is not invented in the spec.
- [ ] Run a placeholder/ambiguity review, then inspect every apparent hit rather
  than treating keyword absence as proof:

```sh
rg -n 'TODO|TBD|FIXME|XXX|PLACEHOLDER' \
  spec docs/m2-spec.md inputs/source-lock.toml conformance
```

**Acceptance gate**

- Every candidate-neutral byte, state, bound, manifest preimage, and ordering
  needed by P3 has one smallest owner.
- The exact implementation references needed for P4 policy are locally locked
  without pretending they already selected a candidate.
- Source receipts are additive and exact; completed M0/M1 evidence still passes.
- No promoted candidate/damage/selection policy, candidate-specific damage
  manifest, provisional winner, final dimension, or human answer exists yet.

## 10. Packet P3 — Build the common grammar and real semantic slice

**Depends on:** P2.

**Purpose:** Produce one real, bounded semantic input and one exact common
transport grammar so candidate comparison cannot hide behind filler or an
unimplemented content bridge.

**Actions**

- [ ] Implement the checked content authoring input/builder independently in
  Python and Rust, with build-time errors distinct from raw-byte parse rejects.
- [ ] Implement the smallest immutable projection/run-event/committed-response
  views required by a generic runner. Add no chess semantics to `gb-content` or
  the Python content module.
- [ ] Implement the common 191-byte plain-block, fragment, local-check, section,
  copy/inventory, tier-frame, and singular stream-assembly path in both
  languages with exact validation precedence and atomic states.
- [ ] Author the real M2 vertical slice through the checked builder: bootstrap
  entry/inventory, representative content/lesson/game use, generic learner
  path, and all sixty-four existing game payloads as atomic records.
- [ ] Build the candidate-neutral semantic-capacity envelope and ordered atomic
  record-slot manifest from the real slice, every curriculum-derived mandatory
  role bundle/heuristic dependency, generic support, every content kind, and
  the full provisional maxima. This defines required logical work before a
  candidate's transport overhead can influence policy.
- [ ] Pack every content record without splitting it across content-body
  sections. Bind the exact `m2_required` and `m2_all` frames and their one
  canonical `ContentStream` header/body identities.
- [ ] Build the generic runner and M1 semantic adapters at the owner boundary.
  Prove the runner itself has no chess import/link and consumes only public
  content views.
- [ ] Add the label-suppressed execution mode: required paths and exact event
  sequences remain identical with semantic `TEXT` removed; no Unicode glyph or
  font identity is required.
- [ ] Independently encode, parse back, compare projections/events, and compare
  the exact complete stream in both languages.

**Direct checks**

- content-authoring valid/boundary/invalid direct suites in each language;
- common-grammar KAT and malformed/duplicate/conflict/truncation suites;
- exact 64-game inventory, ordinal, score, and byte equality;
- parser round-trip and no-accepted-prefix checks;
- generic dependency-firewall and label-suppressed equivalence checks; and
- nearest live `focused content`, `focused chess`, and transport direct tests.

**Acceptance gate**

- One exact real M2 content stream is independently constructed and parsed.
- All sixty-four game records are inventoried and atomic.
- The full semantic/atomic-slot capacity envelope is exact, candidate-neutral,
  and ready for pre-result tuple formulas.
- Candidate-neutral framing and the singular section-to-stream bridge are
  executable, bounded, and fail closed.
- The runner is generic and language-independent in the precise product sense,
  without pulling full M3 authoring or presentation forward.

## 11. Packet P4 — Co-freeze result policy, then teach four complete routes

**Depends on:** P3. Policy promotion is the result-sensitive barrier; shell
implementation follows it and may then proceed in parallel by route/language.

For R3, the original P4 checklist below is retained execution history. Replace
its six-profile/v0 promotion action with the atomic v1 barrier in
`spec/m2-r3-owner-promotion-v1.toml`: compact ABI and owner KATs may be
implemented while it is `blocked`, but route/package bytes, full-set v7 limits,
all final hashes, and both reproduction receipts must land together before
carrier generation or D0--D7. That v1 barrier is now closed at
`pre-result-frozen`; no carrier or damage observation was used to close it.

**Purpose:** Freeze every candidate/damage/selection choice against the real
semantic input, then make the bootstrap discoverable and reconstructible from
the artifact itself instead of relying on a modern format name or one fragile
magic header.

**Actions**

- [ ] Promote `spec/profile-policy-v0.toml` with the full predeclared candidate
  tuples/IDs/classes, objective/resource/work metrics, exact gate order,
  candidate lower-bound rules, mapping/side family, and deterministic
  complexity-first selection.
- [ ] Promote `spec/damage-policy-v0.toml` with typed channels, D0--D7
  operators/order/seeds, promise enums, state aggregation, attempts/work, and
  wrong-accept definition.
- [ ] Freeze the exact Hamming/RS/copy/check tuples, candidate recipe-operation
  union, mapping family, damage policies/seeds, metric counting, selection
  rules, capacity-bucket derivation, and report/pilot evidence projections
  before observing any result-bearing candidate output.
- [ ] Define every candidate/damage generated manifest/ledger schema and M2-only
  state/code in its smallest profile/bootstrap/damage owner. Reject arbitrary
  extra evidence rows or unowned JSON shapes.
- [ ] Bind the policy/source/semantic identities and independently reviewed
  exact KAT derivations.
- [ ] Prove every tuple supplies a finite checked conservative limit derivation
  from the shared semantic/atomic-slot envelope. If one cannot, P4 policy is not
  ready to freeze; revise the tuple/policy before candidate outcomes.
- [ ] Immediately after the policy/formulas freeze—and before interpreting a
  shell route or running a candidate KAT—generate and review
  `spec/profile-limits-v0.toml` as the exact componentwise union of finite
  semantic, section, fragment, dependency, output, work, and scratch bounds for
  **every** tuple in the full frozen set. Selection/damage/pilot values are not
  inputs.
- [ ] Independently regenerate the exact canonical TOML bytes from the P3
  semantic/atomic-slot envelope plus P4 tuple formulas, compare the tracked
  file byte-for-byte, and validate both language loaders/mirrors. If any tuple
  cannot derive a finite checked bound, emit no limits/outcome: reopen P4
  policy. Never omit it or invent a sentinel.

The preceding actions are P4's internal **pre-result freeze barrier**. Once
they pass, the remaining four-route work may run in parallel with P5's
independent candidate-codec lanes. P6 waits for both P4 and P5 acceptance. For
R3, the corresponding v1 barrier and final independence-witness refreeze have
passed, and Python and Rust independently reproduced the exact canonical v7
tree through gates 1–5. Two complete gate-6 attempts subsequently executed the
damage corpus but ended in independent/tooling disagreement and wrote nothing.
After the bounded repairs, the complete rerun converged and atomically
published the 10,038-case gate-6 bundle with zero wrong accepts. Gate 7 then
published the independently byte-identical nine-predicate proof with zero
violations. Gates 1–7 are complete; gate 8 remains pending.

- [ ] Implement two independent bounded recipe interpreters from the data-only
  grammar. They reject cycles, unknown operations, bad types, overflow,
  out-of-range indexing, excessive work/output, and trailing bytes before
  partial acceptance.
- [ ] Generate all sixteen square-dihedral/polarity entry hypotheses and accept
  only a uniquely complete validated route; semantic plausibility never breaks
  a tie.
- [ ] Build four asymmetric rotated shell sectors, each containing a complete
  route with its own calibration, notation, tables, worked examples, held-outs,
  and downstream inventory entry.
- [ ] Build the dependency/knowledge-use graph and prove every artifact-specific
  convention used by the decoder is either taught by a prior shell node or is
  explicitly permitted prior knowledge.
- [ ] Compute exact instructional-cell count and formula-based shell headroom,
  distribute it under the frozen rule, and charge all four copies.
- [ ] Run ablations removing or corrupting each teaching dependency; the
  intended later operation must become unavailable or fail explicitly rather
  than remain secretly implementable from code assumptions.
- [ ] Add wrong transform/polarity/grouping/order/profile discriminators and
  held-out examples that are independent of the worked examples.
- [ ] Keep QR/Data Matrix/HDLC recognizability out of the claim: every
  project-specific meaning must be taught locally.

**Acceptance gate**

- Every result-sensitive candidate/damage/selection fact has one frozen owner
  bound to the exact P3 semantic input before outcomes.
- The full-tuple provisional limits are frozen and independently reproducible
  before shell/KAT/gate evidence.
- For every manifestation that passes gate 2, each one of its four sector
  routes is independently complete and fits with exact headroom. An exact
  closure/fit failure is retained as gate-2 evidence rather than called a
  partial route.
- The recipe graph is acyclic, bounded, and dual-interpreted.
- Knowledge-use and ablation evidence catches a missing teaching step.
- Every wrong entry hypothesis fails structurally before protected semantic
  bytes are accepted.

## 12. Packet P5 — Implement candidate codecs and complete recipes independently

**Depends on:** P4's internal pre-result policy/limits freeze barrier, not the
completion of all four P4 routes. Non-result-aware algorithm spikes may begin
from P2's exact references, but conformance claims and complete recipes use only
the promoted P4 tuples/policy. P6 waits for both packets to finish.

**Purpose:** Build the simple and stronger transport choices from exact owners
without letting either language, an external library, or a generated candidate
define the other's expected behavior.

**Actions**

- [ ] Implement shortened extended-Hamming `[72,64,4]`, syndrome/state
  handling, two-copy baseline, and predeclared third-copy contingency in Python
  and Rust from the exact profile.
- [ ] Implement the complete `RS(255,191)` field, systematic encoder, the
  no-shortening/no-puncturing invariant, syndrome, erasure/error decoder, mixed-boundary handling, stable
  failure states, and resource ceilings independently in both languages.
- [ ] Implement the exact CRC-32C and CRC-64/ECMA tuples, local/section
  preimages, stored byte order, and comparison variants.
- [ ] Attempt each candidate's complete recipient recipe using only the frozen
  recipe-language union. A surviving recipe may require no implementation-only
  shortcut; an exact manifestation that cannot close is a gate-2 failure, not a
  partially accepted route.
- [ ] Run the exact hand KATs first, then exhaustive small-domain and bounded
  generated cases, boundary mixtures, malformed inputs, wrong parameters,
  shortened blocks, noncanonical pad, and stable beyond-radius failure cases.
- [ ] Derive expected KAT values independently from the specification/reference
  procedure. Register only small directly reviewed vectors after Python and
  Rust both agree with the independent derivation.
- [ ] Count primitive work, scratch, tables, operation kinds, conventions, and
  recipe nodes using the pre-frozen policy. Do not optimize a metric definition
  after observing candidate totals.
- [ ] Add named mutants for field polynomial/root/order, Hamming parity/index,
  bit/byte order, shortening, stored CRC order, incorrect-erasure treatment,
  copy voting, and silent beyond-radius acceptance.
- [ ] Keep any third-party codec strictly outside the product/evidence path as a
  diagnostic comparator. It cannot emit retained expected bytes or close a
  project gate.
- [ ] Add `scripts/check focused transport` only after its direct Python/Rust
  consumers are live, and add its cheap deterministic subset to `fast`. Update
  CLI tests and public command text together; no empty focused mode is allowed.

**Parallel lanes**

```text
Python EH72/copies ----┐
Rust EH72/copies ------┤
Python RS -------------┼-> common exact candidate comparison
Rust RS ---------------┤
independent KAT review -┤
CRC/check variants -----┘
```

The lanes may exchange only approved specs and reviewed small fixtures until
each implementation has validated its complete direct candidate output. The
hash-bound final recipe package is shared only under the Section 15.1 boundary;
failure to validate its complete closure is preserved at gate 2. A mismatch is
reduced to the first differing primitive/input; neither direct implementation
is rewritten to match the other's bytes by inspection.

**Acceptance gate**

- Each required candidate/check tuple has two independent bounded direct
  implementations. Its exact recipient recipe either passes complete closure
  in both interpreters or is preserved as the ordinary gate-2 failure that
  eliminates that manifestation, with no invented later-gate evidence.
- Direct-codec KAT, negative, boundary, resource, and mutant evidence passes;
  every surviving recipe passes the corresponding exact-package evidence.
- Candidate metrics are reproducible under the frozen counting policy.
- No candidate is yet called a finalist or preferred.

## 13. Packet P6 — Generate complete limit-consistent manifestations

**Depends on:** P3, P4, and P5.

**Purpose:** Turn exact semantic bytes and candidate primitives into full
provisional carrier candidates under the already-frozen full-tuple limits,
before running damage or choosing a winner.

**Actions**

- [ ] Load and cross-check the exact P3 semantic/atomic-slot envelope and P4
  full-tuple limits identities before producing any manifestation/gate output.
  A missing, stale, or underivable limit stops the batch and reopens P4; P6
  never repairs/widens it around a candidate result.
- [ ] Realize the frozen ordered atomic-record slot packing from M2 spec Section
  10.3. Never collapse record boundaries into a scalar byte total that
  undercounts section headers/checks/copies.
- [ ] Assign every future physical record exactly once to one capacity bucket;
  audit any multi-concept logical credit separately from physical byte charge.
- [ ] Generate the common section, copy, protected-fragment, recipe, shell,
  reserve, load-probe, pad, and alignment charge for each exact candidate tuple
  without exceeding or redefining the frozen union bounds.
- [ ] Enumerate the exact admissible side/shell-width family and lower bounds in
  canonical order. Choose each candidate's smallest fitting provisional pair
  at or below the hard ceiling; prove any candidate-specific narrowing.
- [ ] Generate complete shell/interior carriers, forward/inverse maps, exact
  cell ownership, codeword/copy failure-domain placement, capacity/density/
  work/scratch ledgers, and deterministic fixed filler/pad.
- [ ] Check shell headroom, protected reserve, whole load probes, alignment,
  realistic density/regularity, run/row/column bounds, and every cell exactly
  once. Unused cells need the one declared fixed-pad owner.
- [ ] For an early checked lower-bound elimination, generate exactly the
  complete prior-gate evidence and eliminating bound required by the report;
  invent no later carrier, damage, or cross-language row.
- [ ] Keep full carriers and detailed ledgers in new ignored candidate
  directories. Bind them through canonical manifest identities rather than
  copying them into the eventual report.

**Direct checks**

- exact section-count overhead for adversarial record-size patterns;
- slot exhaustion, record one byte too large, extra mandatory role, and changed
  copy-class cases;
- fixed-point reserve floor and two-fragment alternative boundaries;
- side/width lower-bound and exact 2048-side ceiling cases;
- map/inverse totality, ownership overlap/gap, copy-domain independence, and
  density/run/tile bounds;
- limits-file clean regeneration and stale/manual edit detection; and
- two-language complete carrier/ledger byte equality before damage.

**Acceptance gate**

- Every non-eliminated candidate has one complete valid provisional carrier and
  reconciled semantic/physical/resource ledgers.
- The tracked provisional limits still regenerate from the full predeclared
  tuple set and predate every shell/KAT/gate result; every manifestation fits
  without post-result widening.
- Every charged bit/cell has exactly one owner and every claimed independent
  copy has a machine-checked failure domain.
- The preferred profile, human bundle, and damage results still do not exist.

## 14. Packet P7 — Run frozen damage and gates 1 through 7

**Depends on:** P6. The candidate-independent policy and case derivation must
still match their pre-result P4 identities.

**Purpose:** Evaluate correctness, capacity, resilience, bounded work, and
physical independence on the actual complete candidate manifestations without
result-aware case replacement.

**Actions**

- [ ] Recompute gates 1--5 from each candidate's bound KAT/recipe/grammar/
  resource/capacity evidence in the exact policy order.
- [ ] A candidate reaching gate 6 gets one candidate-specific damage-manifest
  identity and exactly D0 through D7 from the frozen common operators/seeds and
  its own complete carrier.
- [ ] Render one closed v1 damage bundle: the root, exactly eight family
  manifests, and the canonical nonempty shards. Enforce the owned per-file,
  row, file-count, aggregate-byte, path, allowlist, identity, and partition
  limits before writing.
- [ ] Require explicit create mode for the first result-bearing run. Compare
  oracle, Python, and Rust canonical bytes in bounded staging, then fsync and
  atomically publish the complete directory; ordinary check mode must never
  initiate the corpus.
- [ ] Generate typed `OBS_BITS`, `OBS_MATRIX`, and `OBS_UNITS` observations in
  the exact operation order, with independent generator/oracle and decoder
  paths.
- [ ] For D0/D1/D5 require every declared M2 section exact; for D2/D3/D4/D6
  require the exact `m2_required_closure` and report every other section state;
  for D7 require correct checked recovery or the specified explicit failure.
- [ ] Exercise every deterministic placement/residue required by the policy and
  exactly 128 seeded D3 cases per candidate manifestation. Do not discard or
  replace an inconvenient seed.
- [ ] Count wrong accepts against the one named clean candidate. Any checked
  canonical semantic bytes different from it fail; chess plausibility cannot
  repair transport bytes.
- [ ] Verify conflict/state aggregation, attempt caps, resource/work limits,
  state precedence, duplicate quality, missing/incomplete sections, and
  ambiguity independent of observation order.
- [ ] Run the physical-independence proof as gate 7 using the same ownership
  ledger that produced the carrier. Add the independently matching v1 proof
  atomically only after gate 6 passes, retaining either a pass or fail proof
  without rewriting the gate-6 bundle.
- [ ] Record the first failed gate and mark only genuinely unrun later gates
  `not_evaluated`. A losing candidate is valid evidence; the repository fails
  only if the report misstates or cannot reproduce that evidence.
- [ ] Compute objective metric rows under the frozen rules, but do **not** apply
  finalist/preference selection yet.

**Acceptance gate**

- Every damage-evaluated candidate has exactly one common manifest and eight
  complete result rows.
- Gate 6 passes if and only if all required D0--D7 results pass with zero wrong
  accepts; gate 7 matches the exact ownership proof.
- Seeds, operators, manifests, limits, and candidate parameters retain their
  pre-result identities.
- The set of candidates passing gates 1--7 is exact and ready for gate 8; none
  is yet a finalist.

## 15. Packet P8 — Reproduce gate 8, select, and freeze Candidate-ready evidence

**Depends on:** P7.

**Purpose:** Finish candidate-specific cross-language/environment reproduction
before selection, then produce the exact preferred carrier and sealed human
bundles without claiming human success.

**Actions**

- [ ] Implement the complete Gate-8 validators/generators, standalone learner
  runner, tracked neutral templates, and `scripts/check release` surface first.
  Freeze those source bytes before rendering the final evidence-source
  projection; `release` itself remains Candidate-ready-only and is run after
  the report exists.
- [ ] For **every** candidate passing gates 1--7, independently regenerate and
  compare common/content bytes, complete carrier, mapping/ledgers, D0--D7
  observations, recovery states, and normalized output in Python and Rust,
  natively and through clean Linux.
- [ ] Record each candidate's gate-8 pass/fail in its own cross-language
  manifest. A genuine mismatch eliminates that candidate; a mismatch between
  the recorded result and the rerun fails the repository.
- [ ] Only after all reached gate-8 runs finish, independently recompute the
  lowest passing complexity class, bounded near-minimum set, at-most-two
  finalists, and deterministic provisional preference from the frozen policy.
- [ ] Generate the preferred full carrier and complete ownership/capacity/
  density evidence. Aggregate equality booleans cover exactly the retained
  finalist set; a losing gate-8 mismatch remains candidate-specific.
- [ ] Use the already frozen neutral recipient condition from
  `spec/gate8-policy-v0.toml`: `individual`, headcount 1. P8 contacts nobody
  and makes no human-success claim. P9 may recruit one matching unit only after
  ordinary owner authorization; a pre-exposure condition change requires a new
  bundle/report identity and affected freeze checks.
- [ ] Freeze the exact technical and learner bundle manifests, neutral opening
  prompt, clean question, channel schemas/mechanics fixtures, selectors,
  held-out observations, evaluator answers, help taxonomy, clocks, stop/retry
  rule, facilitation mode, and release order. Expected bytes/hashes stay out of
  participant-visible bundles.
- [ ] Create only blank tracked templates under `studies/m2/templates/`; confirm
  instantiated work, answers, source, recordings, identities, and evaluator
  material are ignored/private.
- [ ] Generate the non-self-referential evidence-source projection only after
  all tracked Gate-8 code/templates land. It includes every byte in the five
  exact unignored R3 history archives while live candidate/Gate-8 trees remain
  ignored/regenerated. Generate the exact evidence manifest from that closed
  projection. Exclude the report itself and downstream files carrying its
  identity; compare the full host/container execution snapshot only
  transiently.
- [ ] Admit the exact Linux acquisition receipt and observed local image under
  `linux_acquisition_receipt` in `spec/gate8-policy-v0.toml`. Treat its Docker
  image ID as per-refresh run provenance, not as an output reproducible from a
  pinned base and Dockerfile alone. For the current changed receipt, run only
  the exact `reopen-verifier` transition in
  `spec/gate8-verifier-refresh-v0.toml`: archive the prior tree/report/roadmap,
  advance to revision 10 and `In progress`, and remove canonical stale output.
  Then land all source changes, regenerate four fresh producer receipts and the
  complete Gate-8 closure, and reuse ordinary `assemble --mode generate` so
  tree, report, and Candidate-ready roadmap authority install in their existing
  order. Never restore unavailable prior-image evidence as Candidate-ready.
  Future acquisition must fail before `docker build` can retag an admitted
  image unless another explicit reopen owner already exists.
- [ ] Use the exact two-phase verification ABI in
  `spec/gate8-policy-v0.toml`: pre-report `full` privately regenerates and
  discards Gates 1--7. Candidate-ready standalone `linux` stays
  Git-plus-container-only and uses strictly validated retained native receipts;
  composed `release` instead supplies freshly generated native receipts from
  its preceding host `full`. Both pass the source-bound transient input plus the
  separately mounted exact admitted acquisition receipt to clean Linux. Install
  that receipt only at its ignored owner path after snapshot equality, then
  recompute and require the same snapshot identity before continuing. Both
  generate fresh Linux receipts and derive the complete
  Gate-8/report closure before reading the tracked report solely for final byte
  comparison; only composed `release` proves four fresh producers in one run.
- [ ] Generate the first tracked `reports/m2-feasibility-v0.json` in
  Candidate-ready form: exact finalist/candidate/damage/evidence rows, empty or
  pending human summaries only where the schema permits, immutable M2 pilot
  envelope, and no placeholders/private biography.
- [ ] Render that report from the live pre-Gate-8 roadmap without requiring a
  Candidate-ready preclaim. Stage and validate the prospective transition,
  install the complete Gate-8 tree, then the report, and change only the
  status-derived roadmap bytes last. Final admission requires the exact
  Candidate-ready header/M2 row and installed-report hash; partial installation
  rolls back to the exact pre-Gate-8 roadmap.
- [ ] Run the already implemented `scripts/check release`. At M2 it
  orchestrates host `full`, network-off `linux`, report/freeze staleness, and
  no-premature-package assertions; it does not build a nonexistent release
  package. Its children independently regenerate into bounded temporary roots;
  they do not read the ignored retained candidate as generated evidence.
- [ ] If matching human recruitment is unavailable **after** automated,
  clean-Linux, and bundle gates pass, set the truthful roadmap state to
  `Candidate ready — independent validation pending` and stop.
- [ ] If the Docker image/daemon/path is unavailable, gate 8 is not complete:
  remain `In progress` while practical work continues, or use
  `Blocked — <specific clean-Linux prerequisite>` at a real external impasse.
  Do not create a Candidate-ready report or substitute paperwork/an unrun
  environment.

**Direct checks**

```sh
scripts/check focused transport
scripts/check release
```

Use standalone `full` or `linux` while diagnosing/converging gate 8 if useful;
the immutable P8 barrier runs the composed `release` once rather than running
both children and then immediately running them again.

Also mutate one candidate byte, evidence identity, source-projection row,
manifest role, report gate, finalist order, Linux platform/digest, and bundle
file in disposable copies. Each must fail the smallest applicable validation
without rewriting tracked evidence.

**Acceptance gate**

- Every retained candidate has gates 1--8 exactly pass and every eliminated
  candidate has a truthful first failure/not-evaluated suffix.
- Selection/preference recomputes from policy and evidence; it is not a
  narrative choice.
- Native/Linux source inputs and retained facts agree exactly.
- The preferred recipient-visible material and evaluator answers are sealed
  and distinct.
- The Candidate-ready report is canonical, non-self-referential, reproducible,
  and still makes no human claim.

## 16. Packet P9 — Run the technical full-carrier recipient-unit pilot

**Depends on:** P8 and ordinary owner authorization to contact friendly
participants.

**Purpose:** Test the actual hardest claim with one elite individual or fixed
elite team while allowing realistic trial, error, collaboration, and multiple
sessions—without answer-aware help or open-ended recruitment until success.

### 16.1 Prepare the pool without cueing the solution

- [ ] Recruit from credible prior technical work or an open-ended
  recommendation/portfolio basis. Do not send a checklist naming matrices,
  binary, reverse engineering, CRC/ECC, chess, candidate profiles, project
  name, repository, or searchable phrase.
- [ ] Form one recipient unit matching P8's frozen mode/headcount: one person or
  a fixed complementary team of two to four. Record each opaque member,
  collective ability basis, freshness, and availability before exposure. A
  different mode/headcount requires the explicit pre-exposure refreeze path,
  not an informal substitution.
- [ ] Use one plain page/email explaining the neutral reconstruction purpose,
  important/profound/benign premise, expected trial/error and time, collected
  files, private access, publication/retention choices, voluntary stop, and
  temporary no-search/no-sharing request.
- [ ] Obtain affirmative agreement from each member. Keep recording,
  quotation, and attribution as separate opt-ins; default to no audio/video.
- [ ] Prepare multiple fresh units in an availability pool if useful, but
  assign them only under the frozen retry rule. A pool is not permission to
  keep sampling until one passes.

The private working shape stays ordinary files:

```text
artifacts/private/m2-pilots/
├── pools/{technical.md,learner.md}
├── work/T001/
│   ├── participant.md
│   └── R01/
│       ├── round.md
│       ├── sessions/01.md ...
│       ├── 01-reconstruction/{question.md,files/,answer.md,submitted/}
│       ├── 02-channel-adapter/{question.md,files/,answer.md,submitted/}
│       ├── 03-held-outs/{question.md,files/,answer.md,submitted/}
│       ├── 04-final-account/{question.md,answer.md}
│       ├── 90-debrief/{question.md,answer.md}
│       └── result.md
├── identity-consent/T001/M01.md ...
└── evaluator/R01/{expected.json,bundle-manifest.json}
```

Never share a parent directory. At each phase share only that phase's exact
`question.md` and `files/`, then receive `answer.md`/`submitted/`. No database,
survey platform, ticket workflow, NDA, or transcription service is needed.
Each `answer.md` starts empty apart from a heading/provenance line and is filled
afterward by the participant or a clearly marked, participant-confirmed owner
transcription.

### 16.2 Run and checkpoint the round

- [ ] Freeze/hash the unit membership, information condition, exact carrier and
  bundle, allowed tools, clocks, questions, evaluator answers, and release
  order before first access.
- [ ] Deliver only `N`, indexed `OBS_BITS`, and the neutral important/profound/
  benign prompt. The unit may try bounded shapes, transformations, grouping,
  programs, and wrong hypotheses and may keep its notes across sessions.
- [ ] Allow any number of sessions within the one total 16-unit-active-hour/
  seven-day envelope. Record each member's intervals, their union as unit-active
  time, person-time sum, admin pauses, and unattended bounded computation.
- [ ] At declaration-ready or the clean cap, seal checkpoint A over decoder
  core, derivation, choices, clean recovered bytes/states, notes, and output.
  Give no correctness feedback.
- [ ] Release only the pre-frozen neutral channel schemas/mechanics fixtures.
  Permit only the thin declared input adapter inside the remaining total clock,
  then seal checkpoint B before any actual held-out observation.
- [ ] Release all held-outs together. Evaluate the generic record/transition
  selectors, within-profile unknown-error, known-erasure/spatial, missing-unit,
  and wrong-parameter/beyond-profile negative with no intermediate feedback.
- [ ] Run submitted code only in the explicit disposable bounded network-off
  evaluator. Reproduce exact output/state and seal the result before debrief.
- [ ] Debrief only afterward for detailed prior profiles, guesses,
  alternatives, ambiguity, stopping points, and design suggestions. Revealed
  answers make later work diagnostic.

### 16.3 Classify failure and retry honestly

- [ ] A no-show or withdrawal **before exposure** may be replaced without using
  a retry.
- [ ] An owner bundle/evaluator/environment defect is
  `invalid_environment`; repair and use a fresh unit. Participant-chosen tool
  setup trouble remains normal scored work.
- [ ] A critical hint, answer revelation, new teammate, task-specific search,
  repository discovery, or cross-unit communication ends the result-bearing
  round; continuation may remain useful diagnostic work.
- [ ] An exact-profile-prior pass requires corroboration by a distinct fresh
  `no_material_prior` unit.
- [ ] After one valid unresolved round on an unchanged carrier, allow at most
  one fresh unchanged-carrier retry—and only after recording a factual unit/
  condition difference, the prediction it tests, and the stop rule before
  exposure.
- [ ] Two valid unresolved rounds on the unchanged carrier require a diagnosed
  redesign, explicit scope change, or open failed gate. Do not recruit a third
  unchanged unit.
- [ ] A material recipient-visible change requires a new fresh unit. It resets
  the unchanged retry count only when it addresses the recorded failure
  mechanism, not when bytes/wording change cosmetically.
- [ ] Preserve every permitted exposed-round summary, including failures and
  diagnostics. If withdrawal requires deletion, retain only the expressly
  permitted nonidentifying count or nothing round-linked.

**Acceptance gate**

- One latest-bundle fresh eligible recipient unit passes every frozen technical
  task inside the clock, with zero critical hints, zero answer revelations,
  zero unresolved rivals/conventions, evaluator reproduction pass, and exact
  `prior_assessment=no_material_prior`. `exact_profile_prior`,
  `other_material_prior`, and `unknown` rounds remain useful evidence but do not
  supply the qualifying report ID.
- Its independently recovered content-stream hash equals the expected exact
  `m2_all` stream and is bound for learner input.
- The claim states individual/team size and exact information condition.
- Unsuccessful/diagnostic rounds remain visible subject to permission; the
  process did not rely on first-attempt luck or unbounded recruitment.

## 17. Packet P10 — Run the exact-stream learner micro-pilot

**Depends on:** a qualifying P9 technical recovered stream and the already
sealed latest learner bundle.

**Purpose:** Establish narrow representation feasibility with a fresh
chess-naive individual, not population efficacy or transport reconstruction.

**Actions**

- [ ] Verify the learner input manifest binds the exact qualifying technical
  unit's recovered content-stream bytes; no developer-decoded substitute or
  semantic rewrite is allowed.
- [ ] Select one fresh eligible chess-naive **individual**. A team/collaborative
  learner session may be formative but cannot close G7.
- [ ] Freeze protocol ID, slice bytes, label-suppressed runner mode, item
  selectors, thresholds, scoring, feedback schedule, clocks, and evaluator
  predicates before exposure.
- [ ] Run familiarization, instruction/practice, and held-out commits through
  the generic interface without verbal chess teaching, semantic `TEXT`, Unicode
  glyph identity, or font identity.
- [ ] Keep the simple question/files/answer/submitted folder convention and no
  more than the specified two sessions/clock.
- [ ] Recompute every score/outcome from exact runner events; narrative
  judgement does not override a failed predicate.
- [ ] If the first learner reveals material ambiguity, diagnose and revise the
  representation under a new protocol/bundle identity, then use a fresh second
  learner. Do not lower the rubric or reuse the exposed learner to close the
  revised gate.
- [ ] A passing first learner on the latest bundle is qualifying; additional
  unchanged-bundle sessions are diagnostic rather than opportunities to choose
  a nicer result.

**Acceptance gate**

- One fresh individual passes the frozen latest-bundle predicates and
  thresholds in label-suppressed mode.
- Exact event sequences and scored semantic paths remain valid without
  natural-language/Unicode/font cues.
- The result is reported only as narrow feasibility under the exact person,
  content, interface, and timing condition.

## 18. Packet P11 — Seal evidence, decision, release gate, and status

**Depends on:** P8 automated evidence plus qualifying P9 and P10 results.

**Purpose:** Install the smallest durable evidence M3/M4 need and close M2
truthfully without publishing a product or preserving unnecessary raw data.

**Actions**

- [ ] Regenerate every automated report field and compare with the tracked
  report. Review human summaries for schema, permission, bundle identity,
  timing, task, checkpoint, evaluator, retry, and bridge consistency.
- [ ] Require both qualifying round IDs, exact recovered/learner stream bridge,
  retained gate 1--8 passes, preferred human gate pass, D0--D7 zero wrong
  accepts, full candidate/source/evidence closure, and exact pilot envelope.
- [ ] Keep M2 evidence identities immutable. M3/M4 will store their new content
  hashes in their own evidence and compare the recipient-visible invariance
  envelope; they do not rewrite this report.
- [ ] Append one concise dated measured-selection entry to
  `docs/decisions.md`, preserving any earlier pre-result restart entry. Name
  eliminated candidates, at most two finalists, provisional preference,
  important limitations, and the mandatory actual-content M4 rerun. Do not
  copy metric tables, raw logs, human biographies, or approval prose.
- [ ] Run the full adversarial matrix and trace every M2 spec exit row to a
  runnable test, exact generated identity, or permitted human summary.
- [ ] Inspect the final diff for large artifacts, private data, host paths,
  timestamps in deterministic bytes, secrets, hidden network dependencies,
  stale generators, unregistered normative files, accidental M3/M4 work, and
  unrelated owner changes.
- [ ] Run the final public gates:

```sh
scripts/check fast
scripts/check focused transport
scripts/check release
git diff --check
```

- [ ] Compute the final compact report identity. Only after every gate passes,
  set roadmap M2 to `Complete — <date and candidate/report identity>` and keep
  the derived header/current milestone exact.
- [ ] Re-run `scripts/check focused repo` after the status-only edit. The
  pre-status `release` already closed the expensive gate; rerun it only if that
  edit also changed an input within its declared source/evidence projection.
- [ ] Delete private material when its plain retention note requires it; retain
  only the permitted durable summaries. Do not publish or push as part of M2
  closure.

**Acceptance gate**

- M2's compact report, decision entry, roadmap status, promoted owners, and
  root commands agree exactly.
- The preferred carrier and finalist tuples can be reproduced from declared
  inputs in native and clean Linux environments.
- G5--G8 close with their exact automated/human evidence and narrow claims.
- M3 receives a real semantic envelope; M4 receives at most two finalists and
  an immutable pilot-change envelope, not a falsely final profile.

## 19. Failure and recovery guide

| Situation | Required response |
|---|---|
| Baseline M0/M1 failure | Diagnose before M2 edits; repair only a demonstrated regression in its existing owner and keep completed evidence honest |
| Normative ambiguity | Pause the affected lane, repair the smallest owner, add the exposing case, rerun its consumers |
| Existing M1 constants/report would change | Stop; keep `spec/constants-v0.toml` frozen or explicitly reopen M1 rather than silently regenerating completed evidence |
| External reference unavailable or changed | Do not substitute a moving summary; retain/acquire the exact approved edition and receipt or revise the candidate tuple before results |
| Python/Rust KAT or primitive disagreement | Reduce to the first exact differing input; consult owner/independent derivation; neither implementation becomes authority |
| Content authoring cannot express the real slice | Repair the generic authoring/view owner if genuinely incomplete; do not inject raw byte hacks or M3 chess semantics |
| Shell route needs untaught convention | Repair route/grounding and rerun ablations before exposure; do not call recipient guessing “permitted prior” after the fact |
| Provisional tuple has no finite bound | Stop before emitting limits/outcomes, reopen P4 policy, and fix or remove the tuple through the pre-result policy rule; never omit it from a purported full-set union or invent a sentinel |
| Capacity exceeds 512 KiB | Apply the frozen failure order or eliminate candidate; do not split atomic records, hide overhead, truncate content, or change the ceiling casually |
| Profile limits are exceeded during M2 | Repair an incorrect derivation and rerun every affected candidate, or revise the owner/policy before further outcomes; never widen only the failing consumer |
| D0--D7 case fails | Preserve exact seed/operator/manifest/result and eliminate or redesign under the spec fallback; do not replace the case |
| Any wrong canonical accept | Candidate fails the applicable damage gate; semantic plausibility, CRC width, or “unlikely” reasoning cannot waive it |
| No candidate passes gates 1--7 | Stop before human exposure; use the predeclared fallback order or record `Needs revision`/`Stopped` truthfully |
| Gate-8 candidate differs across language/environment | Record candidate-specific failure and recompute selection; root checks pass only if they reproduce that truthful failure |
| Docker daemon/image unavailable | Preserve automated native work and record the exact blocker; do not claim gate 8 or M2 completion |
| Complete execution snapshot differs | Diagnose Git layer/platform/cache/acquisition mismatch; never hash the snapshot into the report or substitute a clean `HEAD` clone |
| Report dependency row missing/stale/self-referential | Reject the whole report; repair the closed projection/preimage, regenerate in temporary storage, and compare again |
| Human recruitment unavailable | Stop at `Candidate ready — independent validation pending`; no simulated/developer round substitutes |
| No-show or pre-exposure withdrawal | Reschedule or replace normally; no result-bearing exposure occurred |
| Owner bundle/evaluator defect | Mark `invalid_environment`, repair, and use a fresh unit; preserve the permitted summary |
| Participant tool/setup problem | Count it as ordinary work unless it is demonstrably owner-caused; do not silently pause the clock or reclassify after outcome |
| Hint, answer, repository discovery, new teammate, or outside help | Seal the pre-event state; later work is diagnostic under the changed information condition |
| First valid unchanged-carrier unresolved round | Permit at most one pre-justified fresh retry with factual difference, prediction, and stop rule |
| Second valid unchanged-carrier unresolved round | Redesign, narrow, or leave the gate open; do not recruit a third unchanged unit |
| Technical pass used exact-profile prior | Keep as evidence but obtain a distinct fresh `no_material_prior` pass before G6 closes |
| Learner fails latest frozen representation | Diagnose without lowering rubric; material revision gets new protocol/bundle identity and a fresh individual |
| Permission changes or withdrawal requires deletion | Delete covered member-linked material; retain only the expressly allowed nonidentifying count or nothing, never a hidden gating summary |
| M3 later exceeds an M2 capacity slot/limit | Reopen the affected M2 envelope or candidate evidence; do not truncate authored content or rewrite frozen M2 pilot evidence |
| Anthology rights remain unresolved | Local M2 work may continue within the recorded boundary; no public redistribution is authorized |

## 20. Check cadence

Use the cheapest check that closes the current risk, then composed gates at
dependency barriers:

| Moment | Required check shape |
|---|---|
| Before executable M2 work | existing `scripts/check full` once |
| Repository/source-lock/Linux admission | direct tests, `focused source`, `focused repo`, `linux`, then `fast` |
| Content authoring and real slice | direct Python/Rust tests, existing `focused content`/relevant chess-curriculum checks, then `fast` |
| Bootstrap/candidate primitive slices | direct language/KAT tests and the real `focused transport`; `fast` after coherent changes |
| Complete carriers and D0--D7 convergence | dedicated candidate/damage tests and host `full` |
| Gate 8 and Candidate-ready freeze | direct/focused convergence, then one composed `release` (`full` plus `linux` plus freeze assertions) |
| Immediately before human exposure | exact frozen bundle/evaluator hashes plus last green applicable automated evidence; never mutate released bytes |
| Final closure | `fast`, focused transport, one composed `release`, and final diff/status check |

`fast` owns only cheap transport/schema/direct cases. Host `full` owns complete
candidate, damage, and report reproduction once those consumers exist. `linux`
runs inner `full` against the exact snapshot. `release` orchestrates host
`full`, `linux`, and cheap freeze/no-premature-package assertions; it does not
perform a third complete generation.

During ordinary implementation, do not rerun 128-seed damage, complete carrier
generation, both full environments, and report regeneration after every local
helper edit. Run the smallest affected direct/focused suite, then pay the
expensive cost at the packet barrier that can actually invalidate its result.

## 21. Optional review checkpoints

These are useful diff/review boundaries, not mandatory commits or approvals:

1. M2 admitted and current M1 suite reproduced in real clean Linux.
2. External receipts and smallest M2 owners frozen before outcomes.
3. Real content stream/common grammar and four bootstrap routes separately
   green.
4. Both independent candidate-codec lanes complete their direct evidence.
5. Complete carriers, capacity/ownership ledgers, and full-set provisional
   limits converge.
6. Frozen D0--D7 and physical-independence results close gates 1--7.
7. Every survivor completes gate 8, then selection and Candidate-ready bundles
   freeze.
8. Technical qualifying or diagnosed retry/redesign boundary.
9. Exact-stream learner qualifying or diagnosed representation-revision
   boundary.
10. Compact report, decision entry, release gate, and truthful status closure.

Combine checkpoints when the smaller intermediate diff would be invalid. Split
one when it materially improves independent review or keeps human exposure
separate from implementation changes. A checkpoint does not require a meeting,
review ticket, sign-off document, or fixed commit message.

## 22. Plan traceability

| Required M2 result | Primary packets | Closing evidence |
|---|---|---|
| Narrow M2 admission and completed-M1 preservation | P0--P2 | baseline/full checks, phase-aware repository/source-lock tests, frozen constants identity |
| Real clean Linux verification | P1, P8, P11 | pinned-platform network-off inner `full`, exact execution-input equality and attestation |
| Common grammar and singular content bridge | P2--P3 | dual assembly/parse equality, atomic section states and one exact `ContentStream` |
| Real M2 slice and all 64 games | P3, P6 | authoring manifest, content/game identities, inventory and capacity ledgers |
| G5 complete self-description | P4--P6 | four routes, dual interpreters, knowledge-use linter, ablations and headroom |
| Simple and stronger fair comparison | P4--P8 | frozen tuple/policy identities, dual KATs, common harness, exact metric/gate rows |
| Candidate-independent D0--D7 | P4, P6--P7 | policy identity, candidate manifests, complete case rows and zero wrong accepts |
| Exact mapping/independence/capacity | P6--P7 | map inverse, total ownership, failure-domain proof, reserve/load/density ledgers |
| G8 lowest-complexity finalists/preference | P7--P8 | every reached gate-8 result and deterministic selection recomputation |
| G6 independent full-carrier reconstruction | P8--P9 | frozen bundle, checkpoints A/B, exact recovered stream/states, evaluator summary |
| G7 language-light representation feasibility | P3, P8, P10 | exact technical-to-learner byte bridge, label-suppressed events and learner summary |
| Multiple sessions/pools without cherry-picking | P9--P10 | versioned simple folders, time/member intervals, freshness/retry/diagnosis history |
| Durable M3/M4 handoff | P4, P8, P11 | full-set limits, exact finalist tuples, compact report and immutable pilot envelope |
| Lean public repository | all, especially P1/P11 | no placeholder checks, large/private data ignored, one decision entry, no premature package |
| Honest completion | P11 | final release check and roadmap transition only after every earlier row passes |

The implementing agent is free to improve the local route between these
evidence points. It is not free to weaken, skip, or reinterpret them.

## 23. Plan stress-review record

Two adversarial loops and one final authority/simplicity pass were applied to
this plan before it was marked ready.

### 23.1 Loop 1 — dependency, result integrity, and reproducibility

This loop walked the plan through partial candidates, early failures, dirty Git
state, stale generated evidence, cross-language disagreement, and the exact
freeze/selection order.

| Stress | Weakness tested | Plan strengthening |
|---|---|---|
| Limits derived after a winner or even a gate result exists | a selected subset could understate later M3 needs or circularly justify selection | P3 freezes the semantic/slot envelope and P4 derives the componentwise union from every tuple before shell/KAT/gate evidence |
| Damage run on a prototype carrier | section/copy/mapping overhead could be fictional | P6 completes carriers/ownership first; P7 alone realizes D0--D7 |
| Selection before Linux | a “finalist” could subsequently fail required gate 8 | P8 reproduces every gate-1--7 survivor before applying selection |
| Losing candidate mismatch makes root suite red forever | truthful negative candidate evidence would become unrecordable | candidate gate-8 results are local; repository passes when rerun and report agree |
| One implementation supplies expected vectors | cross-language equality could be two copies of one mistake | P5 requires independent derivation/self-validation before comparison |
| Atomic record sizes collapsed to a byte total | capacity probes could undercount section envelopes | P6 carries ordered record slots through exact section packing |
| Dirty tree copied as `HEAD` | Linux could test older bytes and falsely pass | P1 snapshots HEAD/index/worktree/untracked layers exactly |
| Full snapshot hash embedded in its own report | deterministic fixed point is impossible | only transient complete equality is recorded; report uses a closed non-self-referential source projection |
| Early elimination fabricates later evidence | report could contain carrier/damage hashes for work never done | each packet emits only reached-gate roles and a checked eliminating bound |
| Candidate policies tuned after partial output | fairness becomes narrative | P4 freezes all result-sensitive policy against P3's real semantic input before candidate comparison |
| One tuple has no finite limit formula | a “full-set union” could omit the hard tuple or use a fake sentinel | P4 requires a finite derivation; P6 stops/reopens policy before emitting any outcome if it is absent |
| Docker is unavailable after native work | Candidate-ready could falsely imply gate 8/Linux passed | P8 reserves Candidate-ready for green Linux plus missing humans; a clean-Linux impasse remains In progress or specifically Blocked |

After strengthening, the plan has an executable single direction from owners to
content/routes to candidates to carriers to damage to reproduction to selection.
There is no result-aware backward edge or self-hash cycle.

### 23.2 Loop 2 — human robustness and pet-project simplicity

This loop walked the plan through an elite fixed team working asynchronously,
first-attempt failure, owner packaging failure, hints/exposure, exact-profile
prior, withdrawal, learner redesign, and unavailable people or Docker.

| Stress | Weakness tested | Plan strengthening |
|---|---|---|
| First strong unit does not finish | one-shot gate is fragile; unlimited retries cherry-pick | one diagnosed unchanged retry maximum, then redesign/narrow/open gate |
| Team members work in parallel sessions | “16 hours” could hide 40 person-hours or forbid normal teamwork | record unit-active union and person-time separately; fixed team skills may be collective |
| Report freezes “individual” before a team is available | bundle/report could be fictional or silently stale | P8 freezes exact target mode/headcount from neutral availability and requires a matching P9 unit or explicit pre-exposure refreeze |
| New member joins after exposure | information condition silently changes | fixed membership; continuation becomes diagnostic |
| Facilitator suggests a decoding direction | helpful conversation could be called independent success | exact help taxonomy; critical hint seals result-bearing work |
| Exact-profile expert succeeds | untaught step could be supplied by prior knowledge | preserve result but require fresh no-material-prior corroboration |
| Prior is material but not the exact profile, or is unknown | a round could look acceptable in prose but fail the closed report enum | only exact `no_material_prior` can supply the qualifying report ID |
| Owner supplied broken files | recipient is unfairly scored or retry pool consumed | `invalid_environment`, repair, and fresh unit |
| Member withdraws after a team round | public report conflicts with deletion promise | retain only expressly permitted nonidentifying count or nothing linked; round cannot gate improperly |
| Learner material changes after failure | exposed learner can no longer prove acquisition | new bundle/protocol identity and fresh individual; rubric stays frozen |
| Recruitment or Docker unavailable | pressure to invent a pass | explicit Candidate-ready/blocker state preserves all valid work |
| Friendly participation becomes a “study platform” | ceremony overwhelms a personal project | plain note/email, ordinary folders, recording off, no NDA/database/committee/statistics |
| Closing commands run `full`, `linux`, then `release` | the same expensive carrier/damage work runs twice at one barrier | convergence may call children directly; each immutable barrier calls the composed `release` once |

The final pass checked the plan against roadmap/M2-spec ownership, current
repository command status, the completed M1 constants/report lock, and the M2
non-goals. It also removed any need for a fixed calendar, fixed commit sequence,
mandatory review role, participant-management service, or third full candidate
generation. The complexity that remains directly protects deterministic bytes,
candidate fairness, independent reconstruction, honest retries, or the exact
technical-to-learner bridge.
