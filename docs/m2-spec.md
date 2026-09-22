# M2 full-carrier bootstrap and transport feasibility specification

| Field | Value |
|---|---|
| Status | In progress; Gates 1–8 reopened; prior R3 results are historical |
| Roadmap | Revision 11, M2 participant-driven semantic and transport revision |
| Repository baseline | `0feaf4b559f48507f2457e6d203f25c969a98589` (`m2` branch) |
| Prepared | 2026-08-20 |
| Scope | Raw-symbol discovery, bootstrap notation, protected transport comparison, provisional full carrier, early technical reconstruction, and learner representation feasibility |

**Revision 11 current scope:** M2 is In progress; Gates 1–8 reopen for the
participant-driven semantic and transport revision. Prior R3 descriptions
below are historical evidence, not current gate outcomes. M0/M1 and the
512 KiB ceiling are unchanged. The archive-first transition is owned by
[`spec/m2-participant-revision-transition-v1.md`](../spec/m2-participant-revision-transition-v1.md).
Fresh production evidence and affected human validation remain pending.

For this revision, the active source, evidence and lifecycle binding is
[`spec/m2-participant-revision-promotion-v2.toml`](../spec/m2-participant-revision-promotion-v2.toml),
with the exact report/bundle contract in
[`spec/gate8-policy-v2.toml`](../spec/gate8-policy-v2.toml) and execution in
[`spec/gate8-execution-v2.md`](../spec/gate8-execution-v2.md). Their explicit
replacements govern the revised candidate; historical R1/R2/R3 descriptions,
bytes and outcomes below remain preserved in their original domains. Section
19.2 states the current report binding. No result in this source document
advances the roadmap or substitutes for fresh production evidence.

**Default participant iteration:**
[`spec/m2-participant-trials-v1.md`](../spec/m2-participant-trials-v1.md)
permits a frozen provisional blind trial after focused source/clean/held-out
checks, before exhaustive damage, Gate8 or release. Failed trials return directly
to repair. Successful technical and exact-stream learner trials remain pending
until the same stable candidate passes every final automated gate and its trial
bindings reconcile. This explicitly supersedes release-before-exposure ordering
in the historical sections below, without changing final thresholds, freshness,
assistance, saved-method checkpoints or retry limits. No names, dates, timers,
agreements or new participant forms are introduced.

## 1. Purpose, authority, and completion meaning

This document turns roadmap M2 into an executable development contract. It is
deliberately detailed where a wire choice, damage claim, or human-evidence
condition could otherwise drift. It deliberately leaves ordinary module
layout, helper names, internal algorithms, and the order of independent work
flexible.

The authority order is:

1. [`docs/roadmap.md`](roadmap.md) owns the product, recipient claims,
   milestone gates, and status;
2. [`docs/m2-r3-design.md`](m2-r3-design.md) records the pre-result R3 changes
   not superseded by their complete exact promoted owners;
3. the promoted files under `spec/` own their exact byte and policy domains;
   [`spec/gate8-policy-v0.toml`](../spec/gate8-policy-v0.toml) is the
   outcome-independent active-R3 owner for Gate-8 evidence paths, schemas,
   preimages, selection, bundles, Linux integration, and the report overlay,
   while
   [`spec/gate8-verifier-refresh-v0.toml`](../spec/gate8-verifier-refresh-v0.toml)
   owns only the post-result historical reopen from the superseded local
   verifier identity;
4. this file owns how M2 must design, compare, implement, and validate those
   files; and
5. code, fixtures, reports, external documents, and participant statements are
   evidence, never authority over a conflicting specification.

The R3 overlay is an incompatible restart reached only after every R2
candidate failed. It does not reinterpret R1/R2 bytes. Its freeze barrier
closed without a v7 carrier or R3 D0--D7 observation. After the mapping-owner
clarification was re-frozen, Python and Rust independently regenerated the
same v7 gates-1--5 tree. Final pre-D audits then closed the v1 result-artifact
framing and persistence contract and the exact proof witness counts and
violation units. The dependent owner DAG was atomically frozen, Python and Rust
independently reproduced the same canonical tree, and gates 1--5 passed. Two
subsequent complete gate-6 create attempts executed R3 D0--D7, but each ended
in independent/tooling disagreement and took the owned write-nothing path. The
pre-attempt tree is archived. After the bounded convergence repairs, the
complete rerun converged across the oracle, fresh Python decoder, and
persistent Rust decoder and atomically published the canonical gate-6 bundle.
Its raw SHA-256 is
`77697d720bf0df357217d739935931b470cdfda24f7ed3be4b92fc2e6f10e497`
and manifest identity is
`b7024bed03ef0ee4b7c0f89bd5ac626a285dc35c39d8642a3d820570670e7177`.
The 10,038 cases and four boundary KATs pass with zero wrong accepts. Gate 7
then atomically added the independently byte-identical proof, raw SHA-256
`e73a4a186af1a79d1bea3ec73911aa9c4da7cde09e74f36d08e8019d26082964`,
identity
`303b3f710c17517072221156bc5376841970720da3081ae82193243ce009eb04`;
all nine predicates pass with zero violations. Gate 8 remains pending.

M0 and M1 remain closed. If M2 discovers an ambiguity in identity, chess,
source, content, or curriculum truth, work on the affected path stops until the
smallest existing owner is repaired. M2 must not disguise a semantic change as
transport work.

The words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are
normative. A value labelled *measured* or *generated* is intentionally not
invented in this pre-execution document; its algorithm, admissible range, and
gate are fixed here and its value is installed only from real M2 evidence.

Writing this specification does not complete M2. M2 closes only after the two
independent implementations, candidate comparison, clean-Linux run, technical
pilot, learner micro-pilot, durable report, and every exit check below exist and
pass. Until then roadmap Section 13 remains truthful.

## 2. Evidence behind the design

### 2.1 Repository baseline and inherited facts

The implementation starts from a green M1 repository with these relevant
facts:

- Python and Rust independently implement identity, orthodox-chess truth,
  source compilation, and content-v0 parsing/interaction;
- the agreed sixty-four-game binary is 10,024 bytes including its frame and
  carries 10,022 bytes of game IR across 4,915 plies;
- content-v0 is one strict, big-endian, definite-length stream with fourteen
  closed record kinds, typed earlier references, exactly one root, and no
  accepted prefix or trailing bytes;
- content-v0's 1 MiB stream and roughly 467 KiB run-state bounds are parser
  safety ceilings, not promises that such content fits a Golden Board carrier;
- content-v0 intentionally has no build-time serializer or complete presenter
  yet, so M2 needs a small generic authoring path and slice runner before a real
  vertical slice can exist;
- `spec/curriculum-v0.toml` already owns the essential family inventory,
  dependencies, roles, splits, and scoring blueprint; M2 must not edit it merely
  to store pilot paperwork;
- `conformance/registry.toml` admits small, directly reviewed cross-language
  vectors, not generated full carriers or raw participant material; and
- ordinary checks are locked and offline, but the promised clean-Linux verifier
  has not yet been introduced.

M2 also inherits three deliberate one-milestone admission guards that now have
real consumers:

- the repository test forbids `.dockerignore`, `tools/linux/`, and
  `docs/decisions.md`;
- `scripts/check` has neither `linux` nor `release`; and
- the source-lock parser accepts exactly the five M0 reference identities even
  though M0 explicitly reserved additive M2 CRC/ECC receipts.

M2 retires those guards narrowly. It does not weaken tracking, source identity,
offline behavior, or premature-release checks.

### 2.2 Observation-model consequence: no stream synchronizer

The result-bearing raw channel supplies the exact total count and exactly that
many indexed bits. Profile v0 excludes insertions, deletions, shifted tails,
and unknown-length truncation. Therefore HDLC/PPP flags, COBS, byte stuffing,
bit stuffing, comma codes, and repeated synchronization markers solve a channel
the project does not claim. They would add an escaping convention and a new
failure mode before the recipient even reaches the useful shell.

The M2 decoder instead requires a perfect-square count, derives the one integer
side, and tests only the eight square dihedral transforms crossed with two
polarities. There are exactly sixteen machine entry hypotheses. A human may
explore other factor pairs or views, but the artifact must make the square route
survive its complete structural checks. No semantic plausibility score chooses
among entry hypotheses.

RFC 1662 is useful negative evidence here: delimiter framing requires explicit
transparency/stuffing so data cannot imitate its flag. Golden Board has fixed
cell ownership and exact length, so importing that mechanism would be needless
protocol rather than robustness.

### 2.3 Self-description and blind-message evidence

The Voyager cover demonstrates a useful pattern rather than a reusable
protocol: calibration, repeated relationships, exact raster consequences, and
a first decoded result that lets a recipient detect a wrong interpretation.
Golden Board applies that lesson through complete asymmetric shell routes,
worked known answers, and held-out discriminators. It does not copy optical,
audio, or analogue timing assumptions.

QR/Data Matrix designs similarly show that asymmetric location motifs,
orientation support, and error correction can coexist. Their camera model,
quiet zones, perspective correction, standard symbol tables, and assumed
decoder ecosystem are out of scope. M2 may use simple visual motifs, but it
must teach every Golden Board-specific meaning rather than borrow recognizability
from a modern barcode.

Busch and Reddick's blind SETI-message exercise and Heller's larger public
challenge support four protocol decisions: allow substantial iteration, record
prior knowledge, distinguish fixed-team collaboration from cross-unit
contamination, and preserve guesses/hints/stopping points. Heller reports that
roughly half of correct responses benefited from public discussion or spoilers;
an answer without its information condition is not independent evidence.
Neither exercise establishes Golden Board's time limit or success rate.

### 2.4 Error-control findings

Code names do not define an interoperable profile. A selected code still needs
an exact field representation, generator, coefficient order, parity order,
shortening/padding rule, cell-to-symbol rule, mixed error/erasure boundary,
decoder failure behavior, mapping, work bound, and known answers.

The simple initial candidate is shortened extended Hamming `[72,64,4]` over
independently placed complete checked fragment copies. Its parity relations are
small enough to teach with worked binary examples and decode by bounded
enumeration. Two copies cost `2 * 216 / 191`, about 2.26 protected bytes per
common-block byte, below raw three-way bit repetition; the predeclared
three-copy contingency costs about 3.39 and is not claimed to be smaller.
Local and section checks reject the frozen malformed/damage corpus after
bounded code recovery. They do not universally detect every beyond-radius
corruption or make a CRC collision impossible.

The stronger initial candidate is a fully pinned systematic
`RS(255,191)` byte-symbol code. ETSI EN 301 192 V1.8.1 (2025-06) supplies a
current concrete starting profile: GF(256) under
`x^8 + x^4 + x^3 + x^2 + 1`, primitive element `0x02`, 64 consecutive roots,
32 unknown-byte corrections, or 64 erasures. Golden Board imports only those
code parameters and independently specifies all project framing and decoder
details. DVB tables, MPEG transport, puncturing, signalling, and CRC framing
are not inherited.

As a model check, with independent bit substitution probability about 0.0005,
a 72-bit extended-Hamming block has probability about 0.00062 of receiving at
least two faults. Near the 4,194,304-bit carrier ceiling that is roughly 36
multi-fault blocks in expectation. This is not a damage guarantee, but it is
enough to show that an unreplicated Hamming layer is not a credible D3
candidate. The initial baseline therefore evaluates two and three separately
placed complete checked copies. The decision can be revised only before
results are known or after both predeclared families fail a hard gate.

The corresponding independent-fault illustration for `RS(255,191)` is about
1.02 erroneous bytes per 255-byte word. That explains why it is worth testing;
it does not prove D2 or D3. Cluster performance belongs to the exact mapping
proof and frozen damage corpus. Interleaving literature motivates spatial
dispersion, while only the generated Golden Board ownership matrix proves the
project's claims.

### 2.5 Integrity-check findings

M2 compares complete CRC-32C and CRC-64/ECMA tuples. RFC 9260 is a useful
CRC-32C bit/byte reference and ECMA-182 supplies the CRC-64 polynomial, but
their SCTP and tape preimages are application-specific. Golden Board freezes
its own preimages and stored byte order.

CRC distance depends on the polynomial and protected length. Width alone does
not justify a minimum-distance statement or a `2^-k` wrong-acceptance
probability for structured faults. M2 uses exact known answers, any
length-specific properties it actually computes or cites within their range,
and a finite structured-negative corpus. CRCs detect accidental inconsistency;
they do not authenticate importance, origin, or benign intent.

### 2.6 Human-evidence findings

M2 is an elite-recipient feasibility exercise, not a study of average users.
The technical reconstruction unit may be one strong person or a fixed small
team whose skills are collective. A one-unit result demonstrates existence
under that exact condition; it does not estimate a population rate or prove an
individual could reproduce a team result.

Mandatory directed explanation can change performance and increases completion
time. The result-bearing reconstruction therefore relies on submitted notes,
source, outputs, and a sealed post-run debrief. Natural team discussion and
spontaneous remarks are allowed; continuous think-aloud and mid-task “why”
prompts are not required.

Friendly participation still benefits from one plain information note:
purpose at a safe level, approximate time, collected material, voluntary stop,
who sees raw files, publication plan, retention, and separate recording or
attribution choices. No NDA, committee workflow, research platform,
demographic survey, transcription service, or statistical apparatus is a
default M2 dependency.

### 2.7 Chosen and rejected architecture

| Choice | M2 decision | Reason |
|---|---|---|
| Entry framing | exact square plus 16 transform/polarity hypotheses | matches `OBS_BITS`; bounded and sufficient |
| Delimiter/synchronizer | excluded | insert/delete synchronization is outside profile v0 |
| Shell | four asymmetric, rotated, complete routes | sector loss cannot remove the only explanation |
| Recipe | closed bounded data DAG | teachable and lintable without artifact-executed code |
| Simple candidate | extended Hamming `[72,64,4]` with a two-copy baseline and predeclared three-copy contingency | elementary binary parity; the two-copy form is cheaper than raw triplication, while the three-copy form is retained only if its measured margin justifies its greater cost |
| Strong candidate | exact `RS(255,191)` | credible density/damage alternative with a pin-able reference profile |
| Bare SECDED | excluded from initial set | weak sparse-fault scaling without another layer |
| Candidate block size | one common 191-byte plain block | removes payload/framing bias from the code comparison |
| Local check | CRC-32C | one compact early localization procedure |
| Section checks | CRC-32C and CRC-64/ECMA comparison | roadmap-required measured choice at actual lengths |
| Directory | replicated protected inventory, not one central catalog | completeness survives a single dependency loss |
| Full-carrier capacity | valid deterministic capacity/reserve/load probe sections plus explicit fixed pad | every charged cell exercises the real transport or has one exact nonsemantic owner; no conspicuously easy all-zero interior |
| Human evidence | sealed decoder checkpoint then held-outs | prevents answer-aware decoder repair |
| Pilot retries | preserved rounds plus one diagnosed unchanged retry | supports ordinary failure without success fishing |
| Session data | simple files under ignored private storage | easy to operate and delete; no database |
| Clean Linux | the one Docker path already selected by M0 | one real consumer, no portability framework |

## 3. M2 outcome, scope, and non-goals

### 3.1 Required outcome

M2 is complete only if the repository can support this evidence-backed claim:

> From a realistic provisional full carrier, one fresh eligible technical
> recipient unit recovered the exact generic vertical-slice stream starting
> from `OBS_BITS`, then handled the predeclared named held-out channels, without
> a critical hint or unresolved
> artifact-specific convention, while the selected profile passed the frozen
> automated damage, capacity, resource, independence, reproducibility, and
> clean-Linux gates. At least one fresh chess-naive learner then acquired the
> intended representation slice through the generic transducer without verbal
> chess teaching.

The report binds the unit size, tools, candidate, carrier, time, and information
condition. It does not turn this one feasibility result into a universal or
population claim.

### 3.2 In scope

M2 includes:

- the complete discovery-shell dependency graph;
- the closed recovery-recipe notation and two independent interpreters;
- a common protected fragment and section grammar;
- the predeclared repetition and Reed–Solomon candidates;
- exact CRC candidates and known-answer/negative vectors;
- candidate-independent damage channels and operators D0 through D7;
- exact candidate mapping/ownership proofs and bounded recovery;
- a generic build-time content-v0 serializer sufficient for a real slice;
- a small no-chess slice presenter over verified content-v0 bytes;
- actual Core 0, lesson, chess-transition, and sixty-four-game-derived bytes;
- provisional union-safe semantic/profile limits and capacity ledgers;
- a realistically dense provisional full carrier for the preferred candidate;
- host/Linux byte equality and an offline clean-Linux verification path;
- technical and learner pilot templates, bundles, protocols, and result checks;
- durable candidate, pilot-envelope, and decision evidence; and
- the exact repository/check/source-lock migrations these consumers require.

### 3.3 Explicit non-goals

M2 does not:

- freeze the final side, shell width, final content reserve, or final
  `GOLDEN-BOARD.bitplane`; M4 owns that actual-content choice;
- author the complete M3 curriculum, full transducer, or final assessment;
- run the six-person final learner cohort or final technical reconstruction;
- claim optical scanning, material durability, insert/delete recovery,
  arbitrary scratches, adversarial tampering, authentication, or secrecy;
- introduce a general VM, script language, compression framework, archive
  format, database, web app, hosted service, CI platform, telemetry, or
  enterprise security process;
- use a chess library or semantic plausibility to repair transport bytes;
- resolve anthology redistribution rights by implication;
- publish raw participant identity, contact, recordings, answers, or source;
- create release packages or `reports/release-summary.json` before M4; or
- mark a gate passed from simulated or invented human results.

## 4. Normative owners and minimal repository surface

### 4.1 One owner per M2 fact

| Fact | Sole owner after promotion |
|---|---|
| Shell cells, bootstrap grammar, dependency graph, recipe binary/semantics, common fragment/section/tier-frame layout and assembly, knowledge-use rules | `spec/bootstrap-v0.md` |
| Exact twelve-fact route values, exported recipe ABI, canonical worked/held-out bytes, selective mask slots, and profile bindings | `spec/route-data-v0.json` |
| Initial candidate IDs, exact repetition/RS/CRC tuples and numeric block-size constant, complexity classes, comparison metrics, selection algorithm | `spec/profile-policy-v0.toml` |
| Channels, damage operators, coordinate/order rules, frozen seeds, required tiers, attempt/work ceilings | `spec/damage-policy-v0.toml` |
| Provisional M2 parser/work/allocation limits safe for every finalist | `spec/profile-limits-v0.toml` |
| Generic content bytes and new build-time serializer behavior | `spec/content-v0.md` |
| Bootstrap/transport numeric assignments | their existing smallest M2 owner: `spec/bootstrap-v0.md`, `spec/profile-policy-v0.toml`, or `spec/damage-policy-v0.toml`; generated language mirrors are nonnormative |
| Bootstrap/transport rejection conditions and precedence | the smallest owning bootstrap/profile/damage prose spec; generated constants only mirror codes |
| Candidate-specific realized geometry, ownership, hashes, and damage outcomes | generated ignored candidate manifest, bound by the tracked M2 report |
| Retained finalists, preferred profile, pilot envelope, measured result | `reports/m2-feasibility-v0.json` |
| Consequential selection rationale | one concise entry in `docs/decisions.md` |
| Raw pilot answers and identity link | private ignored/out-of-repository workspace, never normative |
| Milestone state | roadmap Section 13 only |

`spec/profile-v0.md` remains an M4 final-profile owner. M2 MUST NOT create it as
an alias for a provisional winner. M2's exact candidate tuples live in the
policy so ignored fixtures cannot become authority.

The table above is the retained R1/R2 owner map. R3 does not rewrite those v0
bytes. Its exact candidate owners are `spec/bootstrap-v1.md`,
`spec/profile-policy-v1.toml`, `spec/damage-policy-v1.toml`,
`spec/route-data-v1.json`, and `spec/profile-limits-v1.toml`. Their atomic
admission record is `spec/m2-r3-owner-promotion-v1.toml`; any partial hash DAG
rejects. The final damage, limits, and promotion SHA-256 values are
`b3b28f00d3ba04addbed4517eb1abb4ecd02796176eaaecdbc1d47f1f39509df`,
`32c2bd0cb978eb800bed7f8ac1c7db223b593b4cf3bad951a9ce4cdc3a568902`,
and `8c30ae216f5a3fd8ee13f2821d38412afa6c50303c9140cbe54da8610df9cd8d`.
The current canonical v7 gates-1--5 tree has candidate-manifest identity
`d783917d34bc6fb472ea7e20c989562092707c516195019434e01f2bc6f68681`
and raw manifest SHA-256
`38839aa28561ff2bec0997a80d8dc938e876526c25f40e23b6a78844f8fc1d86`.
Python and Rust reproduced its exact six files independently. The preceding
raw manifest
`4439abb20aeb4943d9f3dddd4b2b914c08f3a411b791d2ced797533351168019`
with identity
`69b4052299e43a675683361e6a7fa83798b7b3646c873233cfbdd18432ac4cf4`
is retained only in the immutable pre-gate-6 convergence archive.
Two complete gate-6 attempts executed R3 D0--D7 but ended in
independent/tooling disagreement and wrote no canonical damage bundle. After
the bounded repairs, the complete rerun converged and published the canonical
gate-6 bundle. Gate 7 passed all nine independence predicates and published
the byte-identical proof. Gates 1–7 are complete and gate 8 remains pending.

### 4.2 Files introduced only with a live consumer

The implementation SHOULD add no more surface than:

~~~text
docs/m2-spec.md
docs/m2-plan.md                          nonnormative execution aid
docs/decisions.md                         after the measured decision exists
spec/bootstrap-v0.md
spec/route-data-v0.json
spec/profile-policy-v0.toml
spec/profile-limits-v0.toml
spec/damage-policy-v0.toml
conformance/                              small new bootstrap/transport vectors
python/golden_board/                      M2 modules beside existing cores
python/tests/                              M2 tests
crates/gb-transport/                      one new pure Rust crate
studies/m2/templates/                     blank participant/session/question files
studies/m2/slice-v0.json                  small reviewed authoring declaration
reports/m2-feasibility-v0.json            compact reproducible public evidence
tools/linux/Dockerfile
tools/linux/                              one build/acquisition helper if needed
.dockerignore
scripts/check                             extended dispatcher
artifacts/candidates/                     ignored generated carriers/manifests
artifacts/private/m2-pilots/              ignored instantiated human material
~~~

For the R3 restart, add only the v1 draft/generated paths and promotion
manifest named in Section 4.1; retain every v0 path as an R2 fixture/evidence
owner.

Names inside the Python package and `gb-transport` are implementation choices.
Do not split shell, code, CRC, mapping, and damage into separate crates merely
because they have separate concepts. The content-v0 serializer remains in the
content owner, and the pilot presenter may be a small local tool rather than a
new application framework.

### 4.3 M2 admission migrations

Before new artifacts are treated as valid, M2 MUST:

1. update the repository contract so `.dockerignore`, `tools/linux/`, and the
   first real `docs/decisions.md` are allowed and required at the phase that
   consumes them, while `.github/workflows/`, `release/`, `schemas/`, `web/`,
   and other future surfaces remain rejected. Every newly tracked M2
   spec/code/test/vector/template/report path enters the phase-aware admitted
   inventory. Repository text hygiene enumerates every tracked regular file
   plus every nonignored untracked regular file, with
   `reports/game-set-v0.bin` as the sole current binary exclusion, so a tracked
   file omitted from an old hand-maintained REQUIRED tuple cannot evade LF,
   trailing-space, conflict-marker, or path checks;
2. extend source-lock validation so the exact M0 source and five M0 receipts
   remain mandatory, while every additional reference must appear in a closed,
   deliberately reviewed ID-to-role allowlist and must use exact keys, a unique
   valid ID, nonempty metadata, size, SHA-256, retention, and redistribution
   fields; an unlisted ID or role mismatch fails;
3. add exact receipts only for external documents whose bytes supply an M2
   implementation parameter or retained known answer;
4. update the root-command tests, README, and `AGENTS.md` together when M2
   commands actually exist; and
5. keep `spec/constants-v0.toml` byte-identical to its M1 evidence input and put
   M2-only opcodes, IDs, states, and rejection codes in the smallest bootstrap,
   profile-policy, or damage-policy owner; mirror each into both transport
   implementations with exact-closure tests; and
6. make the roadmap-status parser accept only the exact Section 13 grammar:
   literal `Not started` or `In progress`; `Blocked — ` and
   `Needs revision — ` followed by a bounded nonempty specific reason; exact
   `Candidate ready — independent validation pending`;
   `Complete — ` followed by the required date/candidate/report identity; or
   exact `Stopped — redesign required`. Unknown prefixes, empty suffixes, and
   placeholders reject. The M2 report is required and non-stale whenever M2 is
   Candidate-ready or Complete; Complete also requires the measured decision
   entry. A report preserved after a later Needs-revision state remains
   non-stale failure history, never completion evidence.

The existing M1 source-compilation report hashes the complete
`spec/constants-v0.toml` bytes. Appending transport groups would invalidate
retained M1 evidence even when no M1 meaning changed. M2 therefore does not
append to that file, rewrite the completed report, or invent an evidence
snapshot. If execution discovers a numeric assignment genuinely consumed
across the M1/M2 boundary, resolve that new fact first by defining and testing a
frozen M1-relevant evidence projection or explicitly reopening M1; do not
silently update the report hash.

An expected additive M2 reference receipt does not reopen completed M0.
Changing or removing the anthology or an existing M0 receipt does. Changing an
M2 implementation receipt reopens M2 and every candidate/result that consumed
it.

## 5. Recipient and claim contract

### 5.1 Technical recipient unit

A **recipient unit** is either one person or a fixed cooperating team of two to
four people. Every member is listed before exposure. Skills may be
collective; freshness, prior exposure, allowed-tool, and information rules
apply to every member.

The unit is told only that the observation is an intentional, finite message
that is important, potentially profound, benign/nonhostile, and worth sustained
effort; incorrect starts and bounded backtracking are expected. This premise is
part of the experiment's recipient model and not evidence decoded from the
carrier.

The unit may count, calculate, program, debug, retain notes between sessions,
enumerate finite alternatives, and use ordinary offline language/compiler/
standard-library documentation. It may not use:

- this repository, its specifications, its issue/discussion history, or a
  prepared Golden Board decoder;
- the project name, selected profile name, expected hashes, or answer keys;
- a chess, PGN, barcode, checksum, or ECC implementation library;
- task-specific web search or communication outside the fixed unit; or
- a new teammate after exposure.

Generic prior knowledge of chess, CRCs, codes, reverse engineering, and file
formats is allowed and recorded. Every artifact-specific parameter still needs
artifact-grounded evidence. Exact selected-profile expertise that could fill a
missing shell step prevents that run from closing G6 alone.

### 5.2 Trial, guess, and ambiguity semantics

A temporary guess is legitimate when later artifact evidence rejects or
confirms it. An **unresolved convention** is a selected artifact-specific value
for which the final derivation has neither an artifact-grounded discriminator
nor a permitted generic-prior derivation. Any unresolved convention or
non-equivalent surviving interpretation fails the bootstrap gate.

Human hypotheses are not transport candidate attempts. The machine counter in
the decoder is authoritative only when a distinct complete section candidate
reaches the section-check comparison defined by the roadmap.

Multiple rejected hypotheses are expected evidence of the intended process,
not participant errors. Reports describe where the reconstruction path stopped
or became ambiguous; they do not label people as failures.

### 5.3 Claim ceiling

A passing M2 result may name the exact unit headcount and say that this unit
demonstrated feasibility under the bound candidate, tools, time, and prompt. It
MUST NOT say:

- capable recipients generally succeed;
- one individual succeeded when a team did;
- a percentage succeeded when the denominator is one or two;
- M2 proves the final M4 carrier is reconstructible after recipient-visible
  changes; or
- the learner slice establishes broad chess-learning effectiveness.

Automated measurements compare transport candidates. Different humans exposed
to different candidates never form a valid human ranking of those candidates.

## 6. Discovery shell and bootstrap closure

### 6.1 Root assumptions and entry enumeration

The machine dependency root is exactly:

~~~text
intentional finite binary sequence + exact total symbol count
~~~

The raw preflight MUST:

1. reject zero, non-binary, length-mismatched, over-limit, and non-square input;
2. compute the integer square root with checked arithmetic;
3. map the exact bits to a provisional square without silently padding; and
4. enumerate transform IDs in one frozen order across all eight
   dihedral-square transforms
   and both polarities.

At most sixteen shell hypotheses reach stage-0 validation. Byte grouping,
physical mapping, checks, or chess content are not consulted at this point.

### 6.2 Four complete routes

The shell has four 90-degree-related sectors. Each sector independently carries
the complete instructional route from a matrix hypothesis to the fixed Core 0
entry identities. A sector MAY repeat shared mathematical examples but MUST NOT
depend on a table, directory, constant, or recipe stored only in another
sector.

`spec/bootstrap-v0.md` freezes:

- side and shell-width derivation;
- exact half-open cell ownership, including every corner;
- sector traversal and rotation;
- asymmetric orientation marks and complement-aware polarity calibration;
- every repeated relation, integer example, grouping example, and held-out
  discriminator;
- fixed entry IDs and inventory-copy expectations;
- the exact cells occupied by instructions, examples, headroom, and fixed pad;
  and
- a formula/inverse for extracting each shell record.

No cell is “visually obvious” by specification. It has one enumerated owner and
one byte/bit consequence or is explicit fixed padding/headroom.

### 6.3 Grounding sequence

Each complete route grounds, in an acyclic order:

1. repetition, complement, equality, and asymmetry;
2. the canonical transform discriminator and polarity;
3. small unsigned integers and ordered comparison;
4. row/column traversal, fixed-width groups, and MSB-first significance;
5. bootstrap fixed-width record framing and exact lengths;
6. recipe record framing, types, operations, and limits;
7. the common 191-byte plain fragment block and local-check procedure;
8. the selected extended-Hamming or RS procedure through worked and held-out cases;
9. the candidate's exact physical-map inverse;
10. fragment identity, conflict behavior, and section assembly;
11. section-check and inventory validation; and
12. the first verified content-v0 grammar/root entry.

A definition is not grounded merely because a developer recognizes a familiar
code. At least one worked example demonstrates every artifact-specific
convention, and at least one disjoint example or downstream invariant detects a
wrong convention.

### 6.4 Stage-0 validity and hypothesis selection

Stage 0 may use only grounded geometry, equality, repetition, complements,
asymmetric relationships, and worked primitive consequences. It MUST NOT use:

- a CRC or ECC syndrome not yet taught;
- a profile ID inferred from a developer registry;
- a content parser or text/chess plausibility;
- a central catalog; or
- an implementation's preferred transform as a tie-break.

A transform/polarity route becomes canonical only when the complete shell,
transport, inventory, known-answer, and section chain is valid. If two
non-equivalent complete routes survive, the result is `ambiguous`; selecting
one because its content resembles chess is forbidden.

### 6.5 Dependency graph and knowledge-use linter

The bootstrap specification contains a canonical graph with stable node IDs.
Each node declares:

- facts it defines;
- facts and operations it consumes;
- exact shell records/cells carrying it;
- worked and held-out example IDs;
- maximum parsed bytes, operations, and outputs; and
- downstream nodes unlocked.

The graph is a finite DAG. A generated topological order is checked rather than
hand-maintained. A knowledge-use linter rejects the first field, operation,
constant, table, traversal, or code convention used before its defining node.
Unused definitions and unreachable required endpoints also fail.

The ablation corpus removes or corrupts each defining node in turn. A route
must then fail at that node or a declared dependent, not succeed through an
unstated decoder default. This is the executable proof that developer knowledge
is not silently filling a bootstrap gap.

### 6.6 Shell headroom

Before candidate results, `spec/bootstrap-v0.md` freezes one candidate-neutral
additional discriminator/calibration block template of exactly `d` cells and
its four rotated sector placements. For one candidate, `I` is the exact count
of every occupied shell cell in all four complete routes—including orientation,
framing, instruction, recipe, table, and worked/held-out-example cells—but
excluding headroom and explicit fixed pad. Required headroom is exactly

~~~text
H = max((I + 19) // 20, 4 * d)
~~~

with checked integer arithmetic. Each sector first receives its complete
frozen `d`-cell block placement; the remaining `H-4*d` headroom cells are
assigned one at a time in sector-ID order to the next canonical unused
headroom position under the promoted formula. All exactly `H` cells are
explicit, fixed-valued, excluded from parsing, and counted in the ledger. They
are not parity, candidate padding, accidental slack, or cells borrowed from
another sector. Candidate-specific recipe size may change `I` honestly, but
neither `d`, the arithmetic, nor placement may change after a result. M2
records the exact headroom envelope so M4 can tell whether a shell change
requires another fresh pilot.

## 7. Recovery-recipe notation

### 7.1 Purpose and trust boundary

The recipe is a compact, declarative description for a capable human to
reconstruct the bounded decoder. It is not artifact-executed bytecode and not a
production plugin API.

Production decoders parse the selected profile directly. The two recipe
interpreters exist to prove that the artifact's stated procedure is complete
and unambiguous; they accept only trusted conformance recipes and never provide
filesystem, network, clock, randomness, process, or host callbacks.

### 7.2 Closed type and operation set

Before results, the notation freezes the union of operations needed to express
both predeclared initial candidate recipes. Candidate complexity counts only
the operation kinds/tables that candidate actually uses; the preferred shell
teaches only its selected recipe subset. The closed language contains:

- bounded unsigned values with explicit widths;
- fixed-size bit arrays, byte arrays, and immutable tables;
- constants, slice, concatenate, and fixed-position emit;
- checked add, subtract, multiply, quotient, and remainder;
- AND, OR, XOR, mask, shifts, equality, and unsigned order;
- checked fixed-array read/write and immutable table lookup;
- fixed-count iteration over a statically bounded range;
- finite conditional DAG edges; and
- explicit success/failure.

Division by zero, underflow, overflow, invalid shift, out-of-range index,
duplicate output write, uninitialized read, type mismatch, noncanonical
encoding, and step exhaustion fail with stable codes. There is no recursion,
dynamic-length allocation, arbitrary jump, opaque `crc`, `rs`, `decode`, or
chess primitive, or data-dependent unbounded loop. A code-specific procedure
must be expressed using grounded generic operations rather than hidden behind
its name.

### 7.3 Canonical framing and validation

`spec/bootstrap-v0.md` freezes instruction IDs, operand widths, static typing,
record order, binary framing, and validation precedence. Each recipe declares:

- input and output widths;
- immutable table bytes;
- node and edge count;
- worst-case primitive-step count;
- peak live scratch bytes; and
- every possible explicit fail output.

Validation completes before evaluation. Recipes with a cycle, forward use of
an uninitialized value, unreachable node, undeclared table, overlapping output,
wrong result width, trailing byte, or a boundary-plus-one count reject without
partial output.

### 7.4 Independent interpretation and teaching gate

One interpreter is written in Python from the specification. The other is
written in Rust without reading the Python implementation. They share only the
promoted spec and small hand-authored vectors. They must agree on valid,
malformed, maximum, and boundary-plus-one cases and on exact step/scratch
counts.

Every notation operation used by the preferred recipe appears in the shell
before first use. Each individual sector contains the complete preferred
recipe, all of its required tables, worked/held-out examples, and framing as
part of that sector's independent route. The capacity ledger charges four
copies; after any one sector is erased, any one remaining sector suffices while
the whole shell still retains required headroom. A candidate that needs an
ungrounded primitive or does not fit is ineligible regardless of byte
efficiency.

## 8. Common protected grammar

### 8.1 Common 191-byte plain block

Both initial transports protect the same 191-byte plain block. This makes
candidate size and recovery differences attributable to the transport rather
than to a friendlier header or payload size.

The promoted policy freezes one common layout with these required fields inside
the protected/check scope:

~~~text
profile version
fragment grammar version
section ID
semantic copy ID
section type and version
reserved-zero flags
fragment index and count
valid payload length
section envelope length including stored section check
reserved-zero field
fixed payload area
local CRC-32C
~~~

The implementation MAY adjust individual integer widths before the policy is
promoted, but the final layout MUST:

- total exactly 191 bytes for every fragment;
- use only fixed-width big-endian integers;
- permit every generated M2 union-safe limit without a sentinel overload;
- leave at least one explicit reserved-zero field;
- expose a fixed payload capacity shared by both candidates;
- cover the complete header, valid payload, and fixed zero padding with the
  local check; and
- have one canonical byte representation.

Once candidate comparison starts, this layout is frozen. A later layout change
invalidates every candidate carrier, vector, capacity result, and technical
pilot using it.

### 8.2 Local-check preimage

The local-check preimage is an exact shell-taught domain byte vector followed
by all common-block bytes except the stored local check. Fixed payload padding
is zero and covered. The CRC semantic integer is stored big-endian. The domain
vector is numeric data taught by examples; recognizing an ASCII coincidence is
neither required nor accepted as grounding.

The local check localizes and rejects bad fragment candidates after transport
recovery. It is not a section identity and cannot make an incomplete or
conflicting section valid.

### 8.3 Semantic section envelope

Before fragmentation, every section has one canonical envelope containing:

- envelope version;
- section ID, type, version, and recovery tier;
- selected section-check ID;
- a strictly increasing bounded dependency list;
- exact logical payload length and bytes; and
- the stored section check.

The section-check preimage is a separate shell-taught domain vector plus all
semantic envelope fields except the stored check. It excludes physical copy ID,
fragment indices, candidate placement, and observed order. Therefore two
semantic copies have byte-identical envelopes even though their protected
fragment headers and cells differ.

The envelope is fragmented in ascending byte order into the common payload
areas. Let `P` be the fixed common payload capacity, `L` the complete envelope
length including its stored section check, and `F=ceil(L/P)`. Every fragment for
one semantic-copy identity must agree exactly on section ID/type/version,
semantic copy ID, `F`, and `L`; indices are exactly `0..F-1`. Every nonfinal
fragment has valid payload length `P`. The final length is exactly
`L-P*(F-1)`, lies in `1..P`, and all remaining payload bytes are zero. Empty
logical section payload is allowed only for a named type that permits it, but
its envelope/check still make `L` nonzero.

After assembly, fragment-header section ID/type/version and `L` must equal the
decoded envelope fields/length. Envelope type/version, dependency list,
recovery/closure class, and check ID must exactly match the authoritative
inventory. The check ID is a whitelisted consistency value; it never dispatches
to an unchecked algorithm or overrides the selected profile.

### 8.4 Discovery, inventory, and copies

Fragments are self-identifying and may arrive in arbitrary order. Identical
duplicates deduplicate. The same fragment identity with different locally
valid bytes is `ambiguous`; no arrival order or majority over
different valid semantic bytes chooses one.

Each independently protected M2 Core-0-entry copy contains the complete
provisional mandatory inventory. The shell knows those fixed entry IDs,
avoiding a directory self-reference. Every inventory lists exact section IDs,
types, versions, semantic copy expectations, dependencies, provisional
closure/recovery class, and game ordinal range. Conflicting valid inventories
fail. Loss of every inventory prevents a completeness/closure claim even if
isolated fragments survive.

Every section in `m2_required_closure` that exercises the final Core 0–2
resilience class has at least two complete semantic copies in proved
independent failure domains. A third semantic copy is permitted only by a
predeclared measured damage/capacity rule. This is a provisional placement and
copy-domain proof, not a claim that M3's actual Core 0–2 content exists; M4
replaces it with and verifies the complete actual closure. A convenience
catalog may exist for developer navigation but is never carrier authority.

### 8.5 Exact singular content-stream assembly

The transport does not hand the learner a bag of section payloads and does not
ask the content parser to accept a prefix. It reconstructs exactly one complete
canonical content-v0 stream for the selected recovery tier.

A `content-body` semantic section carries the exact concatenation of one or
more complete, already encoded, non-root content-v0 record frames. A semantic
section boundary may occur only between complete records; transport fragments
may split that section as usual. Each anthology game record occupies its own
content-body section, so a game is never shared across two semantic sections.

Each tier has a small protected `tier-frame` semantic section containing:

- frame version and exact tier ID;
- the strictly ordered, duplicate-free content-body section ID list;
- the exact four-byte content-v0 stream header `u16_be version || u16_be
  record_count`;
- the exact complete final root-record bytes for that tier; and
- exact assembled byte and record counts.

Those bytes and the ordered list are inside the tier-frame section check and
normal copy/inventory rules. They are artifact data, not values recomputed from
developer knowledge. To assemble a tier, the decoder selects the sole canonical
checked bytes for every listed body section, concatenates

~~~text
stored content-v0 stream header
|| listed content-body payloads in frame order
|| stored final root record
~~~

and verifies exact counts/length before calling `stream_validation`. The
production content parser must then accept the entire result with its one final
root and no trailing byte. A missing listed section makes that tier incomplete;
nonidentical checked alternatives make it ambiguous. No header/root is patched,
no record is reordered, and no lower-tier prefix is treated as valid.

The final architecture uses cumulative frames for RT0 through RT4: a higher
tier lists every body section needed by lower tiers plus its own closure, with a
tier-appropriate exact root. The clean canonical generic content stream is the
RT4 assembly. Under damage, the report names every complete tier and returns
the exact stream for the highest complete tier requested by the caller; it
never concatenates separate valid streams or silently substitutes a lower tier.
Byte-identical semantic copies deduplicate before this choice.

M2 does not yet possess M3's complete curriculum. Its carrier therefore uses
two explicitly non-RT frames: `m2_required`, containing the roadmap's exact
`m2_required_closure`, and `m2_all`, adding every other real carried M2 content
section. They exercise the same frame, copy-domain, dependency, and D0–D7
placement machinery but MUST NOT be reported as completed product RT0–RT4
content. M4 replaces them with the actual cumulative RT frames. The clean
technical pilot recovers `m2_all`, and the learner runner consumes those exact
bytes; damaged cases may return `m2_required` only where the damage policy says
so.

The two content encoders first produce each feasibility-tier stream from its
typed projection. An independent splitter may then derive body/root boundaries,
but reassembly MUST equal the original encoder bytes exactly in both languages.
One encoder's split or bytes are never the other's input.

### 8.6 Validation order and atomicity

The decoder validates in this order:

1. observation channel, total length, and generated resource preflight;
2. bounded transform/shell hypotheses;
3. map inverse and protected-unit extraction;
4. bounded transport recovery;
5. common header ranges, reserved zeros, padding, and local check;
6. identity deduplication/conflicts;
7. exact section assembly and envelope framing;
8. section check;
9. inventory, tier-frame, and dependency closure;
10. exact singular tier-stream assembly;
11. atomic content-v0 validation; and only then
12. evaluator-side chess/lesson/game assertions.

No valid prefix, partial fragment, locally checked but incomplete section, or
unverified content record contributes canonical bytes. Missing bytes are never
filled from zeros, chess legality, the evaluator's expected answer, or another
candidate profile.

## 9. Predeclared transport and integrity candidates

### 9.1 Candidate-set freeze

Before either candidate is run against D2/D3 results, the canonical
`spec/profile-policy-v0.toml` is promoted with exactly these initial transport
families:

~~~text
eh72-replicated-v0       copy_count in the frozen set {2,3}
rs255-191-v0
~~~

and exactly these section-check families:

~~~text
crc32c-v0
crc64-ecma-v0
~~~

The comparison expands the two Hamming copy counts and both section checks as
exact profile realizations, but shared results are computed once and referenced
rather than duplicated. The smallest Hamming copy count passing every hard
gate is the family's result; a checked proof may eliminate a copy count before
full carrier generation. Local fragment checks are always `crc32c-v0` in M2.

No result-aware third candidate, changed polynomial, extra copy, friendlier
mapping, or hand-selected seed may be introduced. A candidate may be added only
by revising this specification and policy before its relevant results are
observed, or after every predeclared candidate fails a hard gate and the failure
is preserved. Such a revision restarts the complete comparison for every
affected candidate.

The preserved R1 comparison reached that fallback boundary: the two-copy
CRC32C manifestation recorded zero wrong accepts but failed 25 of 256 D2 rows
and 47 of 128 D3 rows because corresponding copy fragments shared correlated
physical neighborhoods; the other initial profiles had already failed gates 2
or 5. Its common damage-manifest SHA-256 is
`8b064872f65a03d6f7f42c4e4f9ad1e97173e38e77177fcfd0a8246e95deb36b`.
R2 therefore restarts the full comparison using the already predeclared third
EH copy. It changes physical unit order to copy-major order and reduces only
the optional generic shared-support capacity fraction from `1/4` to `1/100`
(still at least one complete generic cycle); concept minima, assessment,
integrated-task allowances, actual slice bytes, damage operators/seeds,
thresholds, checks, and the 512 KiB ceiling are unchanged. The earlier failed
artifacts remain evidence and are never reclassified as passing.

Before any R2 damage outcome was evaluated, the D7 owner was clarified to name
the exact bytes for its already-declared mapping and route-resource mutants:
mapping mutants retain the clean shell routes and rewrite only protected-unit
placements under the named mutant map, while each route-resource mutant changes
only the named big-endian resource field in sector 0's unique recipe-package
record. This closes an exact-byte ambiguity; it does not change a case family,
seed, threshold, correction promise, or expected result.

For D4/D6 and `OBS_UNITS`, one **protected unit** is exactly one encoded
physical representation of one 191-byte common block: 216 bytes containing 24
EH72 codewords for `eh72-replicated-v0`, or one 255-byte RS codeword for
`rs255-191-v0`. Its semantic fragment identity is learned only from the decoded,
locally checked common header. A replica lane/copy placement is physical
metadata, not a second semantic identity. D4 removes exactly one complete such
unit observation; it never means one EH codeword or one arbitrary byte.

### 9.2 `eh72-replicated-v0`

The simple candidate appends one required zero transport-pad byte to the common
191-byte block, producing exactly 192 bytes. In block order, each consecutive
eight bytes becomes one shortened extended-Hamming `[72,64,4]` codeword, for 24
codewords and 216 encoded bytes per complete physical copy. The transport pad
is protected and checked after decoding but is not part of the common block or
local CRC preimage.

For one codeword:

- positions are numbered `1..72`;
- Hamming parity positions are `1,2,4,8,16,32,64`;
- 64 input data bits fill every other position in ascending order;
- data bytes and encoded positions are serialized MSB first;
- each Hamming parity equation covers only positions `1..71` whose binary
  position number contains that parity bit, including the parity position;
- position 72 is excluded from those seven equations and is the overall
  parity bit; and
- the overall equation over all positions `1..72` has even parity.

The decoder is intentionally simple bounded enumeration. For `s` erased code
bits, it enumerates every binary fill of those positions and up to
`floor((3-s)/2)` changed known positions, but only when `0 <= s <= 3`. It
retains complete 72-bit codewords satisfying all parity equations, canonicalizes
identical results, and returns the sole candidate when exactly one exists and
`2e+s <= 3`; otherwise the present codeword observation is `corrupt`. A
completely absent protected-unit observation is classified `missing` before
this decoder is called. Because the code has minimum distance four, two
different candidates cannot both satisfy this radius. Observing that condition
is an internal implementation/profile-invariant failure, not an artifact
`ambiguous` state.

The exact candidate constructions examined per codeword are:

| Erased bits `s` | Maximum constructions |
|---:|---:|
| 0 | `1 + 72 = 73` |
| 1 | `2 * (1 + 71) = 144` |
| 2 | `4` |
| 3 | `8` |

More than three erasures reject before enumeration.

All 24 blocks must decode, the appended transport pad must be zero, and the
recovered 191-byte common block must pass its local CRC before a physical copy
is valid. Byte-identical valid copies deduplicate. Different fully valid copies
make the fragment/section `ambiguous`; the decoder never bit-votes across copies or changes
bits merely to satisfy the CRC.

Copy count is predeclared as exactly two or three. Placement must prove for
every promised D2/D4/D6 case that every copied section needed by
`m2_required_closure` retains one complete valid copy. “Far apart” and
different copy labels are not proof.

Minimum encoding KATs are:

| Eight data bytes | Nine encoded bytes |
|---|---|
| `00 00 00 00 00 00 00 00` | `00 00 00 00 00 00 00 00 00` |
| `80 00 00 00 00 00 00 00` | `e0 00 00 00 00 00 00 00 01` |
| `01 23 45 67 89 ab cd ef` | `11 12 1a 2a 9e 26 af 36 de` |
| `ff ff ff ff ff ff ff ff` | `ff ff ff ff ff ff ff ff ff` |

Vectors additionally cover every one of the 72 changed positions, every one-
bit erasure position, representative `(e,s)` pairs on `2e+s=3`, their
one-beyond forms, the distance-four proof/no-within-radius-ambiguity invariant,
nonzero transport padding, and a parity-valid recovered block whose local CRC
fails.

### 9.3 `rs255-191-v0` field and code

The stronger candidate uses this exact algebraic profile:

| Parameter | Value |
|---|---|
| Symbol | one byte, represented by its unsigned value `0..255` |
| Field basis | polynomial basis over GF(2) |
| Field modulus | `x^8 + x^4 + x^3 + x^2 + 1` (`0x11d`) |
| Primitive element | `alpha = 0x02` |
| Nonzero element convention | `alpha^i`, exponent modulo 255 |
| Code length | 255 symbols |
| Data length | 191 symbols |
| Parity length | 64 symbols |
| Generator roots | `alpha^0` through `alpha^63`, inclusive |
| Generator | product of `(x + alpha^i)` for `i=0..63` |
| Layout | systematic: 191 data symbols then 64 parity symbols |
| Shortening/puncturing | none; every common block is exactly 191 bytes |
| Unknown-error radius | at most 32 byte symbols |
| Mixed boundary | `2 * errors + erasures <= 64` |
| Cell order within symbol | data byte bits MSB first |

To eliminate coefficient-order ambiguity, let transmitted bytes
`c[0]..c[254]` represent

~~~text
c(x) = c[0] * x^254 + c[1] * x^253 + ... + c[254]
~~~

and let data bytes `m[0]..m[190]` occupy `c[0]..c[190]`. The encoder chooses
the unique final 64 coefficients for which `c(x)` is divisible by the generator
polynomial. Field addition is XOR. Multiplication, inverse, exponent order, and
zero handling are specified through the bit-level polynomial algorithm as well
as optional generated log/antilog tables; the tables are consequences, not a
second authority.

For review and shell/KAT construction, the 65 generator coefficients from
`x^64` through `x^0` are:

~~~text
01 c1 0a ff 3a 80 b7 73 8c 99 93 5b c5 db dd dc
8e 1c 78 15 a4 93 06 cc 28 e6 b6 0e 79 30 8f 4d
e4 51 55 2b a2 10 c3 a3 23 95 9a 23 84 64 64 33
b0 0b a1 86 d0 84 f4 b0 c0 dd e8 ab 7d 9b e4 f2 f5
~~~

### 9.4 RS decoding and failure behavior

The promoted bootstrap spec chooses and completely describes one bounded
errors-and-erasures decoder using the generic recipe operations. It MUST pin:

- syndrome coefficient/order conventions;
- erasure-locator construction and index-to-power mapping;
- error-locator update algorithm and discrepancy order;
- root search order and position conversion;
- evaluator/magnitude formula and derivative convention;
- maximum intermediate polynomial lengths;
- correction order and duplicate-position rejection; and
- exact post-correction validation.

Let `s` be the number of unique erased symbol positions and let `e_obs` be the
number of non-erased positions where the proposed codeword differs from the
received observation. The logical success condition is algorithm-independent:
return the unique codeword reached by the selected algorithm only when
`2*e_obs+s <= 64`, all 64 post-correction syndromes are zero, and the recovered
191-byte common block passes its local check. The decoder fails, without
exposing partially corrected bytes, on:

- more than 64 erasures;
- malformed or duplicate erasure positions;
- locator degree/roots mismatch;
- a root outside `0..254` or repeated correction position;
- checked-arithmetic or work-limit exhaustion;
- nonzero post-correction syndrome;
- `2*e_obs+s > 64` or any requested search outside that boundary; or
- local-check failure.

The decoder never searches or accepts this protected unit outside the observed
mixed radius. In a D7 case, another independently valid physical/semantic copy
may still supply the correct fragment; otherwise explicit failure is expected.
The finite D7 corpus must never silently accept wrong canonical bytes. The
implementation does not claim that every possible beyond-bound corruption is
detectable by a CRC; it claims only this bounded decoder and the frozen
zero-wrong-accept corpus.

### 9.5 RS known-answer minimum

Small hand-authored conformance vectors must include:

- 191 zero data bytes and its all-zero codeword;
- 190 zero bytes followed by `01`, with all 255 expected bytes;
- data bytes `0x00,0x01,...,0xbe`, with all 255 expected bytes;
- a nonpalindromic data block that detects reversed coefficient/parity order;
- clean verification;
- one unknown error at each boundary position class;
- exactly 32 unknown errors and 33 unknown errors;
- exactly 64 erasures and 65 erasures;
- at least four mixed `(errors, erasures)` pairs on `2e+s=64` and the
  corresponding one-beyond pairs;
- an erasure whose surviving byte bits would otherwise look useful;
- duplicate/out-of-range erasure rejection; and
- a wrong modulus, first root, parity order, and bit order.

Expected parity bytes are generated independently by two temporary derivations,
reviewed against the defining polynomial, then installed as literal fixtures.
The test suite never regenerates expected bytes with the implementation under
test.

The expected parity for the final-byte-one vector is:

~~~text
c1 0a ff 3a 80 b7 73 8c 99 93 5b c5 db dd dc 8e
1c 78 15 a4 93 06 cc 28 e6 b6 0e 79 30 8f 4d e4
51 55 2b a2 10 c3 a3 23 95 9a 23 84 64 64 33 b0
0b a1 86 d0 84 f4 b0 c0 dd e8 ab 7d 9b e4 f2 f5
~~~

The expected parity for data bytes `00,01,...,be` is:

~~~text
8c 1b e6 94 d0 57 75 7c 84 ad 11 47 37 f1 17 51
d3 d4 33 c6 e3 3e 53 6f f7 bb c6 d1 36 ae 4b d0
15 62 6f bc 94 c5 2c c5 ab eb e5 3f dc f0 a2 4e
22 fa 23 87 d8 74 49 c7 be d4 ce eb 9c 94 c6 f9
~~~

### 9.6 CRC-32C tuple

`crc32c-v0` is defined by this direct byte algorithm:

~~~text
register = 0xffffffff
for byte in preimage order:
    register = register XOR byte
    repeat 8 times:
        if register bit 0 is 1:
            register = (register >> 1) XOR 0x82f63b78
        else:
            register = register >> 1
result = register XOR 0xffffffff
~~~

All operations are width-32. This corresponds to width 32, normal polynomial
`0x1edc6f41`, reflected input/output, all-one initialization, and all-one final
XOR. The stored semantic integer is four bytes big-endian; host memory and RFC
packet-field layout are irrelevant.

Minimum KATs are:

| Preimage bytes | Result integer | Stored bytes |
|---|---:|---|
| empty | `0x00000000` | `00 00 00 00` |
| ASCII byte values for `123456789` | `0xe3069283` | `e3 06 92 83` |
| `00` | `0x527d5351` | `52 7d 53 51` |
| `ff` | `0xff000000` | `ff 00 00 00` |
| `00 01 02 03` | `0xd9331aa3` | `d9 33 1a a3` |
| `00 01 ... 0f` | `0xd9c908eb` | `d9 c9 08 eb` |

The second input is defined by its nine byte values in the conformance fixture;
recognizing the text is not part of the artifact route. Local and section
domain/preimage vectors add project KATs with exact stored bytes before freeze.

### 9.7 CRC-64/ECMA tuple

`crc64-ecma-v0` is defined by this direct byte algorithm:

~~~text
register = 0x0000000000000000
for byte in preimage order:
    register = register XOR (byte << 56)
    repeat 8 times:
        if register bit 63 is 1:
            register = (register << 1) XOR 0x42f0e1eba9ea3693
        else:
            register = register << 1
result = register
~~~

All operations are width-64. Input/output are not reflected; initialization and
final XOR are zero. The result is stored as eight big-endian bytes.

Minimum KATs are:

| Preimage bytes | Result integer | Stored bytes |
|---|---:|---|
| empty | `0x0000000000000000` | eight zero bytes |
| byte values for `123456789` | `0x6c40df5f0b497347` | `6c 40 df 5f 0b 49 73 47` |
| `ff` | `0x9afce626ce85b507` | `9a fc e6 26 ce 85 b5 07` |
| `00 01 02 03` | `0xf805609ece1ecbf3` | `f8 05 60 9e ce 1e cb f3` |
| `00 01 ... 0f` | `0xf9c42d91abaf3b55` | `f9 c4 2d 91 ab af 3b 55` |

Golden Board does not inherit ECMA-182's tape-field length or bit numbering.
The direct algorithm and project preimages above are authoritative.

### 9.8 Section-check comparison

Both checks run over the same semantic field layout, dependency list, and
logical payload at every actual M2 allowed section-length class. Their frozen
domain/check-ID bytes and stored-check width necessarily differ and are counted
explicitly; no other candidate-friendly preimage difference is allowed. The
comparison records:

- complete tuple and KAT agreement in both languages;
- added common-block, shell-recipe, and carrier cells;
- operation/table/dependency-depth cost;
- protected maximum length;
- any guaranteed burst/distance properties established for those exact
  lengths, with method and range;
- every frozen structured-negative result; and
- candidate-attempt interaction and worst-case work.

If both close every hard gate and no length-specific property materially favors
CRC-64, CRC-32C wins because it is smaller and already taught for local checks.
CRC-64 may win only through a predeclared hard/property margin, not because
64 “sounds safer.” No probability is inferred from width.

## 10. Mapping, geometry, density, and capacity

### 10.1 Exact cell ownership

Every candidate generator produces a total ownership table and independently
checked inverse for:

~~~text
observed cell
  -> canonical matrix cell
  -> shell/interior owner
  -> transport symbol and bit
  -> protected unit
  -> common block byte
  -> fragment payload byte
  -> section byte
~~~

Each matrix cell belongs exactly once to a shell lesson/example/headroom/pad,
real protected data/parity/check, protected capacity/reserve/load probe, or
explicit fixed pad. Overlap, gap, duplicate logical bit, unreachable cell, or
non-invertible parameter fails candidate construction.

### 10.2 Bounded mapping family

The policy freezes a small formula-based placement family before candidate
damage results. It MAY use affine permutations, lane/tile transposition, or a
composition of the two, provided:

- parameter domains are finite and stated;
- only bijective parameters are admitted by a checked number-theoretic rule;
- candidates are enumerated in canonical lexicographic order;
- the inverse is expressed in the recipe without a giant coordinate table;
- replica/codeword bits are dispersed across declared row, column, tile, lane,
  and shell failure domains; and
- an independent ownership oracle derives placements from the promoted
  formulas rather than consuming the production decoder's table.

The coding agent may choose the smallest formula family that proves the gates.
It must not add a more complex mapping after observing which D2/D3 seeds fail
without revising the frozen comparison and rerunning every candidate.

The first M2 comparison used `affine-interior-v0`, whose multiplier `N-1`
advanced consecutive logical bits by one interior row and minus one column. It
produced a structurally valid carrier but failed the separately frozen local
density gate. Revision R1 replaces it for every candidate with the single
candidate-neutral `affine-interior-v1` formula. For interior side `N` and
population `P=N^2`, its multiplier is `2N-1`, its inverse multiplier is
`P-2N-1`, and the unchanged offset is
`(40503*profile_version + 257*shell_width) mod P`. The identity
`(2N-1)(P-2N-1) = 1 mod P` proves bijectivity. This is a new pre-result
comparison freeze, not a geometry retry or weaker realism threshold; every
affected package, carrier, ledger, and later gate must be regenerated.

### 10.3 Provisional semantic slice and envelope

M2 serializes real bytes before selecting a provisional side. The semantic
ledger includes:

- the complete bootstrap grammar and Core 0 inventory/schema entry copies;
- the learner slice in Section 14;
- asymmetric chess-transition and special-move fixtures derived from the M1
  chess owners;
- all sixty-four canonical game payloads, each individually atomic in inventory;
- every mandatory section/check/copy/dependency overhead;
- a generated bucketed M3 authoring allowance derived by the frozen formula
  below from M1 curriculum minima and valid content-record prototypes;
- protected content reserve of at least the greater of five percent of
  protected logical capacity and two maximum-sized fragment payloads including
  their headers/checks; and
- exact fixed padding required by each candidate.

Before any candidate result, `spec/profile-policy-v0.toml` freezes the ordered
capacity buckets, role-bundle record-kind multiplicities, eventual tier/copy
class, and this integer calculation. `studies/m2/slice-v0.json` supplies at
least one canonical, parser-valid, nonsemantic capacity prototype for every one
of content-v0's fourteen record kinds. Prototypes are encoded independently in
both languages and are not packed or shown to a learner. For kind `k`,
`L[k]` is the maximum complete encoded record-frame length among its declared
prototypes. A role-bundle byte size is exactly
`sum(record_kind_multiplicity[k] * L[k])`; a missing kind/prototype,
cross-language length disagreement, or zero multiplicity for a curriculum-
required role rejects before geometry search.

Scalar bytes alone are not the capacity model. Each role-bundle occurrence
expands, in content-v0 record-kind order, to an ordered sequence of atomic
capacity slots `(bucket_id, role_ordinal, kind, prototype_id, L[k])`, with one
slot per multiplicity. A stable lowest prototype ID breaks equal-maximum ties.
No slot may exceed the pre-frozen maximum content-body section payload and no
slot may be split across sections. Within each bucket, a deterministic
next-fit scan appends the next whole slot when it fits and otherwise closes the
current section and opens the next; buckets never share a simulated section.
The policy freezes that maximum and scan before results. This deliberately
conservative atomic layout, not a repartitioned sum, determines simulated
section count, lengths, headers, fragments, checks, copies, and parity.

The ordered logical-byte buckets are:

1. `concept_minima/<concept_id>`, for every registered curriculum concept in
   file order: one each of the frozen grounded-rule, contrasting-worked,
   active-prediction-with-feedback, distinct-held-out, and passive-trace role
   bundles required by `authoring_minimums`; when that concept ID appears in
   `heuristic_role_required_concept_ids`, add one distinct heuristic bundle
   whose multiplicities include `ROLE_HEURISTIC`, its observable basis, its
   required `FEEDBACK_LIMITATION`, and one limitation/counterexample
   dependency. The list is read from curriculum-v0 rather than hardcoded, and
   the extra bundle takes that concept's tier/copy charge;
2. `assessment/<family_id>`, for every family in file order: three forms
   times two pretest plus two posttest item bundles, plus three times one
   delayed item bundle for each family in set `E`; the counterfactual pair and
   assessment-only template must occupy the already counted posttest slots and
   do not create hidden extra bytes;
3. `integrated/<task_id>`, for every registered integrated task in file
   order: three forms times its declared `minimum_per_form` item bundle; and
4. `generic_shared_support`: one support cycle consists of one `L[k]` slot for
   every one of the fourteen record kinds in content-v0 order, followed by the
   complete atom sequence of the largest frozen role bundle (ties by frozen
   role ID). Its target is the greater of one complete cycle and
   `ceil((concept_minima + assessment + integrated) / 4)`. The policy repeats
   the complete cycle until its whole-slot sum reaches that target; the final
   atom/cycle is never truncated, and the resulting full sum is the charged
   bucket size.

In that formula, `concept_minima`, `assessment`, and `integrated` are the exact
whole-atom byte subtotals of buckets 1--3 before transport overhead. All
arithmetic is checked `u64`; `ceil(x/4)=(x+3)//4`. A concept/family
bucket takes its curriculum tier; Core 0–2 buckets use the replicated M2
protection class, Core 3–4 buckets use the nonreplicated class, integrated uses
Core 3, and `generic_shared_support` is conservatively charged to the
replicated Core-0 class. The policy records these assignments explicitly and
the physical ledger applies each candidate's exact header/check/ECC/copy cost.
There is no post-result manual override. Changing a prototype, multiplicity,
form count, fraction, tier, or copy class restarts every capacity/damage result.

These buckets explicitly cover generic untagged grounding and integrated/shared
support that curriculum family caps exclude. They remain below M1 parser safety
caps and are hard provisional M3 maxima: M3 either fits or explicitly reopens
M2. They are not a prediction that authors will use every byte.

The M3 authoring manifest assigns every newly authored physical content record
exactly once to one unused capacity slot of the same kind and with encoded
frame length at most that slot's `L[k]`. Integrated-task records use their task
bucket; scored assessment records use their sole family bucket; records and
dependencies owned by one concept-role occurrence use that concept bucket;
genuinely shared, generic, or multi-concept support uses
`generic_shared_support`. A record may earn the curriculum's permitted logical
credit for multiple concepts/families, but its physical bytes are never charged
twice. The manifest audits those two views separately. A missing matching slot,
longer per-kind frame, changed role multiplicity, or excess shared support
explicitly reopens the M2 capacity envelope before M3 can claim fit.

Let `C` be the conservative pre-result logical allowance recorded as
`semantic_capacity.content_capacity_before_reserve_bytes` in
`spec/profile-limits-v0.toml`: exact real M2 and bucket payload bytes plus the
full frozen 16,384-byte inventory allowance, before
section/fragment/check/ECC/copy overhead and before reserve. The realized
inventory is reported separately but cannot reduce this frozen allowance.
Let `B=191` bytes be one maximum common-block fragment footprint, including
the fragment header/payload/local-check space. The required reserve logical
payload is exactly
`R=max((C+18)//19, 2*B)`. Here protected logical capacity is `C+R`, so
`R>=ceil((C+R)/20)`; load probes and physical overhead are outside that
promised logical capacity. This deliberately charges the two-fragment floor as
application payload and then additionally charges its envelopes and transport
overhead, so it is conservative rather than silently excluding headers or
checks. Only `R` bytes of `reserve-probe` application
payload count as reserve; its envelopes, headers, checks, parity, copies, pad,
and spare geometry do not. This pins the five-percent denominator, ceiling,
unit, and two-fragment alternative without floating point. P6 reads the
resulting exact reserve value from the regenerated limits owner and never
shrinks it per candidate.

`spec/profile-limits-v0.toml` contains the union-safe semantic, section,
fragment, dependency, output, work, and scratch maxima for the full
predeclared M2 candidate-tuple set, and therefore for every possible retained
finalist. It deliberately omits final side, shell width, final placement,
realized inventory size, and selected-profile-only counts; its reserve is the
frozen conservative full-inventory-allowance value above. M4 regenerates the realized values
from complete actual content.

The file is generated, but still normative and reviewed. Before any candidate
outcome is observed, the generator derives a finite conservative ledger for
every exact tuple in the frozen candidate policy from that tuple's checked
formulas and the common semantic envelope. A tuple that cannot supply a finite
checked bound is invalid at gate 1; it is not silently omitted. Host `full`
independently derives the exact canonical TOML bytes as the componentwise union
of that complete pre-result ledger set, compares them byte-for-byte with the
tracked file, and then requires the Python and Rust loaders/generated mirrors
to expose the same values. Selection, damage results, and pilot results are not
inputs to this derivation. A hand-edited or stale limits hash cannot pass merely
because both implementations read the same stale file.

### 10.4 Provisional side selection

For each candidate combination, the harness evaluates the roadmap's admissible
`S` and `W` family in canonical order. The M2 provisional carrier uses the
smallest pair that fits:

- the real M2 slice;
- the full provisional semantic envelope;
- exact shell and transport overhead;
- required shell headroom and protected reserve; and
- every M2 candidate-specific alignment rule.

The preferred profile's pair becomes its pilot carrier. The report calls it
“M2 provisional,” never final, minimal-final, or `GOLDEN-BOARD.bitplane`.
No candidate above 2048 squared cells is eligible. A narrower admissible side
family must be proved, not asserted from implementation convenience.

### 10.5 Deterministic full-load probes and fixed pad

Un-authored but capacity-charged M3 content is represented by valid
transport-level `capacity-probe` sections, not harmless unparsed cells. In
bucket order, their section boundaries and payload lengths exactly mirror the
atomic next-fit slot realization in Section 10.3. Fill bytes stand in for each
whole record slot, but the ledger retains every slot boundary and never splits
or coalesces simulated records merely to reduce header/fragment overhead.
Their section counts, fragment counts, payload lengths, copy classes, and
placement tiers therefore realize exactly—not at least—the frozen allowance.
The exact `R` reserve bytes above, which do not simulate authored records, are
partitioned into the fewest checked fixed `reserve-probe` sections allowed by
the pre-frozen maximum probe-section payload. Both kinds are declared in
inventory and exercise codewords, correction, checks, attempts, work, scratch,
mapping, and damage, but no tier frame lists them and no content parser/learner
sees them.

Probe logical payload and any unavoidable final alignment-pad cells use this
byte/bit stream:

~~~text
SHA256("GB-M2-FILL-v0\0" || slice_semantic_sha256 || counter_u64_be)
~~~

The quoted domain is the exact thirteen ASCII bytes `GB-M2-FILL-v0` followed
by one zero byte, exactly
`47 42 2d 4d 32 2d 46 49 4c 4c 2d 76 30 00` in hexadecimal.
`slice_semantic_sha256` is SHA-256 of the exact canonical `m2_all`
ContentStream bytes produced before transport splitting, supplied as the raw
32-byte digest rather than hexadecimal text. Counter starts at zero, increments
without wrapping, and overflow rejects. Each SHA-256 result contributes its raw
32 bytes in digest order and each byte MSB first. Probe payload bytes consume
the stream first for every capacity probe in ascending
`(section_id, payload_offset)` order, then every reserve probe, then every load
probe in that same order. One cursor spans all three classes and is never
restarted for a section or class. Any remaining alignment-pad cells consume
the next bits in canonical row-major cell order; a final partial digest uses its
shortest required prefix. This is a developer generator, not an artifact
decoder primitive.

The first capacity-probe section ID is 211, one above the greatest reviewed
real-slice ID. Capacity IDs are contiguous in global bucket/section order,
reserve IDs continue contiguously, and load IDs follow them. Physical protected
units are ordered by `(semantic_copy_id, section_id, fragment_index)`, receive
contiguous one-based IDs, and contribute their encoded bytes MSB-first.

After real, exact-capacity, and exact-reserve sections are packed in the
smallest selected geometry, every residual whole protected-unit slot is owned
by inventoried `load-probe` sections under the selected profile's ordinary
nonreplicated optional-section class. For a hypothetical load-section count
`L`, `Q(L)` is the residual whole-unit count after charging an inventory that
already contains those `L` entries. The generator chooses the smallest `L`
that can hold `Q(L)` positive fragment counts under the frozen per-section
maximum. It assigns lexicographically largest fragment counts in section-ID
order and, for each count, the largest payload no greater than the frozen probe
maximum whose checked envelope has exactly that count. A missing fixed point
or an empty declared load section rejects that geometry. Load-probe bytes stress density,
checks, ECC, work, mapping, and damage but count as neither authoring allowance
nor reserve. Residual cells that cannot form another protected unit are
explicit fixed-pad owners using the stream above. There are no unowned or
`unused` cells. A later content regeneration replaces capacity probes through
the normal section grammar; it never reinterprets capacity, reserve, load, or
fixed-pad bytes as content.

The generator report measures one/zero counts and density separately for shell,
real protected content, capacity/reserve/load probes, fixed pad, and complete
interior. Run, tile, and repeated-row/column metrics use the complete
rectangular interior only:

- longest horizontal and vertical equal-bit run;
- aligned 32-by-32 tile density extrema where such tiles exist;
- repeated-row and repeated-column counts; and
- fixed-pad/capacity-probe/reserve-probe/load-probe counts.

The full carrier fails the realism gate if the protected interior is all one
value or any aligned 32-by-32 interior tile is all one value solely because of
probes/padding. Before any candidate full carrier is generated, the policy also
freezes exact acceptable density, equal-run, repeated-row/column, and tile
ranges and applies them equally to every profile. A visual impression or a
threshold chosen after seeing a carrier cannot pass or fail this gate. The
metrics remain in the durable pilot envelope so M4 can detect a materially
different density or regularity condition.

### 10.6 Capacity and physical-independence ledgers

Each candidate ledger has exact integer rows for:

- logical bytes by section/closure/copy and by real versus capacity-probe/
  reserve-probe/load-probe;
- envelope, fragment header, zero pad, local/section check, repetition/parity,
  and mapping alignment;
- shell instruction, example, recipe, headroom, and fixed pad cells;
- shell, real protected, capacity-probe, reserve-probe, load-probe, and fixed-pad cells,
  whose sum equals `S*S`, with `unused_cells == 0`;
- protected-unit/codeword/replica counts;
- minimum surviving `m2_required_closure` instances under every guaranteed
  M2 operator; and
- worst-case attempts, work units, scratch, and output.

An independent ledger implementation recomputes every total from promoted
inputs. A one-bit discrepancy or unexplained “overhead” row fails. The
placement/dependency matrix proves the roadmap's copy, sector, D2, D4, and D6
independence predicates; labels such as copy A/copy B are not evidence.

## 11. Damage and fail-closed recovery

### 11.1 Policy/realization separation

`spec/damage-policy-v0.toml` contains only candidate-independent channels,
coordinates, transforms, operators, formulas, seeds, promises, state meanings,
and limits. It contains no candidate hash, realized coordinate, or favorable
expected result.

For each candidate, the generator writes an ignored
`artifacts/candidates/<id>/damage/damage-manifest.json` with exact candidate and
observation hashes, realized coordinates, ownership consequences, expected
fragment/section states, and ledger identities. Its bounded family manifests
and case shards live in the same `damage/` directory. The tracked M2 report
binds the manifest hash and summary. Expected states come from the independent
ownership oracle, not from the decoder under test.

For the active v7 candidate, `spec/damage-policy-v1.toml` replaces every v0
result-artifact schema explicitly. The exact `damage/` bundle contains one v1
root, eight v1 family manifests, and a canonical nonempty v1 shard partition.
Each canonical file is at most 1 MiB, each shard contains at most 256 cases,
and the complete directory obeys its owned file-count and aggregate-byte
ceilings. The root binds the common case-row projection and boundary-KAT
results; shards bind the root identity; family manifests bind the root identity
and raw shard hashes. Gate 7 separately adds exactly one v1 independence proof
only after gate 6 passes. Unknown paths, partial states, links, or mismatched
existing bytes reject without overwrite.

The first gate-6 corpus requires explicit create mode. Oracle, Python, and Rust
outputs are rendered in bounded staging and must agree byte for byte before the
complete directory is fsynced and atomically published. A converged candidate
failure is persisted as losing evidence. An implementation disagreement is a
tooling blocker and writes nothing. Ordinary check mode validates an existing
bundle and cannot initiate the first result-bearing run.

### 11.2 Typed channels and operation order

The exact roadmap channel distinction is preserved:

- `OBS_BITS`: exact count and ordered known bits;
- `OBS_MATRIX`: recovered coordinates with known or erased cells; and
- `OBS_UNITS`: artifact-derived protected-unit identities/observations.

Damage is applied in this order:

~~~text
canonical clean matrix
  -> selected physical transform and polarity
  -> frozen operator in observed coordinates
  -> exact named channel serialization
~~~

The policy freezes origin, row-major index, half-open rectangles, duplicate and
out-of-range rejection, overlap semantics, erased-cell encoding, and coordinate
order. Evaluator-known clean bytes, operator, and expected state do not reach
the decoder unless the named channel explicitly carries the fact.

Each case starts a fresh decoder. Its only case-specific input is the exact
serialized observation. Candidate manifests, ownership ledgers, clean bytes or
hashes, case/operator labels, parameters, coordinates, expected states, and
generated expected route/package bytes remain evaluator-only. Tracked generic
parsers, the frozen profile algorithms, and resource ceilings are code, not
candidate truth. `OBS_BITS` and `OBS_MATRIX` enumerate exactly the bounded
sixteen transform/polarity square views and at most four sector route paths per
view, and must extract and fully validate whatever shell routes survive in the
observation; an erased route bit makes that route unavailable. They recover
profile, geometry, mapping, inventory, and semantic
identities from those observed bytes. `OBS_UNITS` receives only its serialized
artifact-derived IDs and unit bytes, tries the frozen profiles within their
bounds, and derives semantic identity from valid common headers and the
authoritative recovered inventory. It never consults evaluator unit rows.
Byte-identical complete outputs deduplicate. Nonidentical complete valid route
packages are all enumerated, but route disagreement alone is not ambiguity;
the artifact is `ambiguous` only when at least two nonidentical complete
checked downstream canonical results survive.

Both implementations emit the closed decoder-result projection owned by the
damage policy. The evaluator separately compares its section bytes and stream
hashes with the clean candidate, assigns wrong accepts, and requires the
decoder-result SHA-256 to match across languages. Accepted physical hypotheses
are diagnostics and never alter canonical semantic bytes.

### 11.3 Cell-to-symbol conversion

For `rs255-191-v0`, any erased bit erases the entire containing byte symbol.
Surviving bits in that byte are discarded. A byte with no erasure and at least
one changed bit is one unknown erroneous symbol regardless of the number of
changed bits.

For `eh72-replicated-v0`, every changed/erased cell affects its one numbered
code bit in its one complete physical copy and the bounded parity-candidate
rules in Section 9.2 apply. Neither profile receives an evaluator label
identifying the damaged codeword or semantic copy unless `OBS_UNITS`
legitimately contains the recovered artifact ID.

### 11.4 D0 through D7

M2 implements every roadmap family without weakening its channel, but it uses
the roadmap's named `m2_required_closure` rather than falsely claiming M3's
unfinished RT2/RT4 content:

- **D0:** clean preferred carrier under all sixteen transform/polarity views;
  every declared carried section recovers exactly;
- **D1:** erase each one complete declared shell sector; another route and every
  declared interior section recover exactly;
- **D2:** the exact square interior erasure over every proved mapping residue
  class or every explicitly sampled placement when equivalence is unproved;
  `m2_required_closure` recovers and all other section states are explicit;
- **D3:** all 128 pre-frozen stratified substitution seeds at exact `K` with the
  same required closure and explicit remaining states;
- **D4:** remove every protected unit in turn through `OBS_UNITS` with the same
  required closure and exact affected optional states;
- **D5:** assembly is a pure function of the validated protected-unit multiset;
  canonical ID sorting, duplicate handling, and conflict behavior recover every
  declared section under every order, tested exhaustively on small fixtures and
  by frozen metamorphic permutations on full carriers;
- **D6:** every shell-sector plus protected-unit combined case required by the
  proof partition recovers `m2_required_closure` without evaluator help; and
- **D7:** wrong parameters, conflicting routes/copies, cross-profile splices,
  and one-beyond geometry, fault, missing-unit, attempt, work, and algebraic
  boundaries return a correct checked result through an eligible surviving path
  or an exact explicit failure.

No failed D3 seed is replaced. If a D2 residue-class equivalence proof fails,
the claim is narrowed to the finite placements actually run rather than using
an unproved representative.

### 11.5 Deterministic sampling

D3 uses the roadmap counter stream and unbiased rejection sampling without
replacement. Both languages independently generate the exact same coordinates
and damaged-observation hashes from only the policy, candidate, and seed. Tests
cover duplicate-word rejection during sampling, partial final digest use,
counter boundary, `K=0`, `K=population`, and boundary-plus-one.

The policy is frozen before candidate seed outcomes. Candidate construction may
not choose a seed-dependent map; the map is fixed before D3 is evaluated.

### 11.6 States, conflicts, and attempts

Fragment and section states remain the roadmap's disjoint closed sets. Assign
exactly one state at each reported level:

| Fragment state | Exact condition |
|---|---|
| `verified` | the named observation decodes without changing/filling a bit and its complete header/pad/local check is valid |
| `recovered` | exactly one valid fragment value is obtained only after an in-bound correction or erasure fill |
| `missing` | the inventory names the fragment/unit observation and it is absent; the transport decoder is not called |
| `corrupt` | an observation is present but every bounded candidate fails code, structure, pad, or local integrity |
| `ambiguous` | two or more nonidentical fully locally valid fragment values survive for one semantic identity |
| `unknown` | no valid profile/identity was established, so the observation cannot be assigned to a named fragment |

| Section state | Exact condition |
|---|---|
| `verified` | exactly one complete section value passes its check using only selected `verified` fragments |
| `recovered` | exactly one complete section value passes and at least one selected fragment is `recovered` |
| `incomplete` | the expected identity is known but required fragments/dependencies are absent and no complete valid candidate exists |
| `corrupt` | no complete valid candidate exists and at least one present candidate fails structure, agreement, or section integrity |
| `ambiguous` | two or more nonidentical complete section values pass every structural and section check, or valid inventories/tier frames conflict |
| `unknown` | no valid profile/inventory establishes that section identity |

Invalid alternate physical copies are reported separately and never override a
unique fully valid semantic value; nonidentical *valid* alternatives always
produce `ambiguous`. After byte-identical valid witnesses deduplicate, the
semantic fragment/section is `verified` when at least one complete witness is
all-verified; otherwise it is `recovered`. This choice is independent of arrival
order and every physical-copy diagnostic remains visible. When no valid section
exists and missing plus corrupt facts coexist, the per-input facts remain
visible and the section takes `corrupt`, matching the roadmap severity order.
Complete shell routes that normalize to different valid semantic results make
the artifact result `ambiguous`.

The artifact report always exposes the per-section vector and, at M2, complete
`m2_required`/`m2_all` availability; only M4 may report actual RT0–RT4. Compact
severity never hides a surviving closure.

The artifact-wide complete-section candidate ceiling is at most 4096 and is
frozen to one exact `section_attempt_ceiling` in the policy. Canonical
byte-identical candidates deduplicate before counting. Attempt number
`section_attempt_ceiling` is allowed; the next returns the stable resource-limit
failure before comparing its section check. Local-check failures have their own
generated bound and do not consume section attempts. Neither Hamming parity nor
copy count votes between different checked section bytes.

### 11.7 Wrong-acceptance scope

A wrong accept is checked canonical semantic bytes different from the named
clean candidate after a frozen accidental operator. D0–D6 must achieve their
exact required M2 result or the candidate fails; explicit failure is not a pass.
D7 permits correct checked recovery or an exact explicit failure. Every family
requires zero wrong accepts.

A separately authored self-consistent artifact with recomputed checks is a
different artifact, not accidental corruption. CRCs do not authenticate which
self-consistent artifact is profound, benign, or original.

## 12. Complexity, resources, and candidate selection

### 12.1 Predeclared complexity classes

Initial profiles are classified before results:

| Class | Allowed bootstrap machinery | Initial member |
|---|---|---|
| C0 — direct | uncorrected fixed framing or raw bit repetition/majority only | none initially |
| C1 — binary algebraic | fixed binary parity equations, bounded candidate enumeration, checked complete copies, CRC, formula mapping | `eh72-replicated-v0` |
| C2 — nonbinary locator | GF(256), polynomial locator/root/magnitude procedure | `rs255-191-v0` |

Class membership cannot be lowered by hiding tables or code-specific behavior
inside a recipe primitive. If the Hamming/copy family fails a hard gate, C2 may
win. If C1 passes, a smaller C2 carrier cannot displace it under the roadmap's
complexity-first rule. Full three-way bit repetition was considered as C0 and
left outside the initial bounded set before results: the checked EH72 baseline
already exercises direct binary teaching and correction, while a second
replication-only family would add implementation/pilot work without testing a
distinct required claim. This is not an elimination proof or a claim that
three-way repetition is always inferior. It may return only through the
predeclared candidate-set revision rule after the initial families fail.

### 12.2 Objective metrics

For every transport/check combination, one generated row records:

- distinct recipe operation kinds;
- explicit table count and bytes;
- graph nodes, edges, and maximum dependency depth;
- complete recipe, worked-example, held-out-example, and shell cells;
- independent conventions/parameters;
- plain, protected, shell, reserve, and total bits;
- guaranteed and sampled damage margins by family;
- worst-case primitive work units and scratch bytes;
- Python/Rust measured time as noncanonical context;
- pilot unit-active time, person-time, unresolved conventions, and critical
  hints for the preferred profile only; and
- every hard-gate result and elimination reason.

A work unit is one primitive operation in the promoted reference algorithm;
scratch is peak simultaneously live temporary bytes excluding immutable input
and final output. Counting rules are specified before comparison. Wall-clock
time never resolves a deterministic tie.

### 12.3 Hard-gate order

Candidates are filtered in this exact order:

1. complete exact profile and cross-language KAT agreement;
2. bootstrap dependency/recipe closure and shell fit/headroom;
3. common grammar, atomic recovery, and state correctness;
4. generated resource/attempt limits;
5. provisional semantic capacity at or below the hard carrier ceiling;
6. D0–D7 required automated behavior and zero wrong accepts;
7. physical independence proof;
8. native/Linux reproducibility; and
9. preferred-profile human feasibility.

A candidate is “damage-evaluated” exactly when it passes gates 1 through 5 and
therefore reaches gate 6. It then has one candidate damage-manifest identity
and exactly eight D0..D7 result rows derived from it. Gate 6 is `pass` if and
only if all eight rows have their family-required passing result and zero wrong
accepts; otherwise it is `fail`. A candidate eliminated before gate 6 has no
invented damage rows and marks gate 6 and every later unrun gate
`not_evaluated`.

A checked lower-bound elimination may stop implementation before a later gate
only if it uses the same semantic envelope and omits no candidate-favorable
capacity. The report retains the proof and marks all later metrics
`not_evaluated`, not failed or passed.

The gate-5 lower-bound preimage is the closed
`golden-board.m2-elimination-bound/v0` object owned by
`spec/profile-policy-v0.toml`. It charges the exact no-load inventory, both
tier frames, every real-content body, every capacity probe, and the frozen
reserve probe, then adds all four exact candidate route prefixes. Only shell
headroom, alignment pad, and load probes may be omitted. Exact lower-bound
rows and any complete carrier are regenerated from the current frozen
mapping/package identities. A lower-bound survivor receives no gate credit:
it is only permission to construct the ordinary first-fit gate-5 evidence.
Geometry is never retried to hide a realism failure, and no D0--D7 evidence
exists unless the regenerated candidate passes the complete gate.

Every candidate that passes gates 1 through 7 reaches gate 8 and is reproduced
before finalist selection. Candidate-specific gate-8 failure is an ordinary
fail-closed elimination: the harness records it, while the repository check
passes only when the report and independent rerun agree that it failed. Root
`full` does not turn an accurately reproduced losing-candidate result into a
false repository failure, and no candidate is called retained or preferred
before its own gate 8 is exactly `pass`.

### 12.4 Finalist and provisional-preference rule

After automated hard gates:

1. discard every class above the lowest passing class;
2. retain at most two profiles in that class using the roadmap's bounded
   near-minimum, robustness, work, bit-count, and reserve ordering;
3. select one retained profile as the provisional M2 pilot preference with the
   same deterministic order; and
4. after the pilot, discard or redesign it if G6 fails rather than promoting a
   more complex profile by narrative judgment.

Candidate IDs are unique. “Passing” above means gates 1 through 8 in Section
12.3 are each exactly `pass`, never `not_evaluated`; gate 9 is separately
`preferred_human` and may be pending only before human evidence. The report
validator independently recomputes every gate status from the bound evidence,
then the lowest passing class, near-minimum/top-two survivor set, deterministic
preference, and every intermediate selection step from the frozen policy and
metric rows. Each `SelectionRow` lists the exact surviving candidates before
its named rule, names the rule's exact outcome, and hashes the canonical
recomputation evidence. A hand-authored disposition, reordered candidate ID,
or selection narrative cannot create a finalist.

CRC variants count as distinct exact profiles but not fictitious transport
families. If two retained profiles differ only in a check, M4 still reruns both
on actual content. A single retained finalist is valid when it is the only or
deterministically preferred passing profile in the lowest class.

### 12.5 Failure response

If no candidate passes, use the roadmap fallback order: simplify shell/recipe,
use the already predeclared third Hamming copy or more direct replication,
narrow the named damage claim, reduce optional
future content allowance, enlarge within 512 KiB, or stop for scope revision.
Do not keep a complex candidate solely because implementation effort was
already spent, and do not weaken a seed, state, or wrong-accept gate to obtain a
green report.

## 13. Content authoring and the real vertical slice

### 13.1 Minimal build-time content serializer

M2 adds a deterministic build-time operation to the content-v0 owner:

~~~text
encode_content_v0(ContentAuthoringProjection) -> bytes | ContentAuthoringError
authoring_from_validated(ContentProjectionView) -> ContentAuthoringProjection
    | ContentAuthoringError
~~~

The signature is conceptual: the current Python projection can be created only
by its parser and the current Rust record fields are private. M2 therefore also
adds the smallest build-only typed constructors or authoring-projection value
needed to state every field used by the slice. Every encoded field is explicit;
there are no inferred IDs, defaults, record sorting, or implicit references. A
parse-then-re-emit wrapper alone does not satisfy this authoring requirement.
The conversion from a validated read-only view is a field-for-field checked
copy used to prove canonical re-encoding; it cannot invent or normalize a
field.

The encoder is not an artifact VM or a second wire grammar. It accepts the
already specified logical projection, emits exactly the bytes owned by
`spec/content-v0.md`, and rejects the same invalid ranges, references, graph
shapes, budgets, and noncanonical order that parsing rejects. Because an
invalid in-memory value has no raw byte spans, `ContentAuthoringError` is a
build-only symbolic reason plus bounded field/index path; it never fabricates a
`ContentReject` span. The content spec fixes deterministic authoring validation
order, while only `stream_validation` owns canonical raw-byte rejection spans.

The authoring value is untrusted until the emitted bytes pass the production
parser. This is build tooling and is not linked into a result-bearing
participant transducer unless needed to create a noncanonical test input.

Python and Rust implement the encoder independently. Required properties are:

- `parse(encode(valid_authoring_projection))` equals its complete public
  projection view;
- `encode(authoring_from_validated(parse(canonical_bytes)))` equals every valid
  hand-authored fixture byte-for-byte;
- no alternate normalization, record reordering, default insertion, or unknown
  extension exists;
- invalid projections reject before partial output escapes; and
- boundary and boundary-plus-one size/count cases remain bounded.

M2 updates the content spec/API deliberately. It does not add a broad object
serialization framework or pre-author M3's full curriculum.

### 13.2 Slice manifest

A small tracked, reviewed `studies/m2/slice-v0.json` manifest declares which
existing truths the M2 slice uses. Its closed authoring-only schema rejects
duplicate/unknown/missing fields and implicit defaults. It contains the
selected M2-facing curriculum families, every intended content record with all
explicit typed payload values, its role/semantic-binding ID, actual lesson/
passive/practice/held-out membership, and section/tier/copy assignment. It
also has a separate `capacity_prototypes` array, ordered by content-v0 record
kind then prototype ID, containing at least one complete explicit valid
authoring projection for every one of the fourteen kinds and the literal role
`nonsemantic-capacity-only`. Those prototype entries supply only the `L[k]`
calculation in Section 10.3: they are parser-checked in both implementations,
never packed into the content stream, and never shown to a learner. The
manifest contains no generated success claim and does not become a second
content-wire owner or a participant-facing file.

The generated slice evidence then binds that declaration to the content-v0
spec/constants identity, curriculum-v0 identity, exact M1 game-set identity,
exact content stream bytes/hash, and evaluator-side chess-transition expected
identities. Both implementations must derive the same binding independently;
one implementation's bytes are not the other's authoring input.

Neither form contains a participant answer or private assessment revelation.
The candidate generator consumes the verified byte result; transport code does
not understand its chess semantics.

### 13.3 Required raw-to-content vertical slice

The full preferred carrier contains real, non-placeholder records sufficient
to demonstrate:

- the complete bootstrap grammar and one verified content-v0 grammar/root;
- generic scalars, enums/masks, vectors, matrices, tuples, regions, opaque
  bindings, assertions, feedback, lesson nodes, passive trace, and root;
- an asymmetric matrix and move/region path that catches transpose, reflection,
  polarity, row/column, and bit-order mistakes;
- both castlings, en passant, and all four promotions in the fixture bundle;
- at least one legal and one self-check transition;
- a board-local versus history-dependent contrast;
- one short opaque move record and its complete replay/score binding;
- canonical derived payloads for all sixty-four games in distinct atomic
  sections; and
- complete inventory/dependency and provisional `m2_required`/`m2_all`
  assembly behavior, without an M3-era recovery-tier claim.

The slice's chess answers are generated by the two existing chess cores and
must agree before content packing. Transport never invokes chess to accept,
repair, rank, or disambiguate bytes.

### 13.4 Realistic game use without M3 overreach

Because the sixty-four canonical game payloads already exist and are small, M2
packs all of them into individually inventoried atomic content-body sections in
`m2_all`. The capacity ledger uses their exact byte-identical M1 payloads and
exact per-game envelope/fragment overhead; D4/D5 inventory tests exercise
ordinal completeness `0..63`. M2 may not substitute a representative subset or
estimate game bytes from average plies.

Game records contain no descriptive players, events, dates, openings,
annotations, or prose. Their source/semantic truth remains M1-owned.

## 14. Minimal generic transducer and learner slice

The exact candidate-neutral runner surface and automated semantic-path
evidence are owned by [`../spec/runner-v0.md`](../spec/runner-v0.md). This
section owns their M2 product requirements and learner boundary.

### 14.1 M2/M3 boundary

M2 implements only the production-shaped minimum needed to expose the real
serialized slice to a learner. M3 later completes every generic presentation,
lesson, predicate binding, authoring path, and integrated formative flow.

The current Python projection/run state and event chain are private; Rust
exposes records but not an event-log view. M2 therefore adds the smallest
read-only generic view API to `spec/content-v0.md` and both implementations. It
accepts only already validated authority-created projections/states and exposes:

- version, root ID, and ordered records with every already encoded generic
  field through immutable typed values or bounded indexed accessors; and
- current node, budgets, phase/outcome, selection buffer, exact immutable
  canonical `committed_response` bytes, feedback/next-node values, and the
  ordered `(node_id, action_bytes, result)` event sequence.

The exact exported fields and cross-language equality are specified before the
runner uses them. The view has no mutator, parser bypass, evaluator answer,
chess interpretation, new JSON/wire representation, or access to private
implementation fields. The runner MUST use this public view rather than
reaching into `_ContentProjection`, `_RunState`, Rust-private storage, or
decoding run-state bytes with an unofficial parser.

This additive build/view API does not alter M1's content bytes, accepted
language, rejection spans/precedence, or transition results and therefore does
not reopen completed M1. A change to any of those existing observable contracts
does reopen the M1 content owner before M2 continues. Exact-public-surface tests
are updated deliberately for only the new authoring/view operations.

The M2 runner:

- accepts only a completely verified content-v0 stream;
- uses the existing generic content projection and run-state operations;
- renders bounded artifact-carried labels, atoms, matrices, tuples, masks,
  regions, passive steps, feedback, and navigation;
- submits only canonical finite actions through `step`/`advance_committed`;
- visibly distinguishes select, commit, reset, feedback, exhaustion, and
  terminal state;
- can export an exact event log for evaluator scoring; and
- has no hidden chess truth or transport repair.

It may be a small offline terminal/local-window tool. It does not need a
browser, Wasm, CSS system, account, telemetry, accessibility conformance claim,
or polished public packaging. Interface mechanics must nevertheless be clear
enough that they do not masquerade as a representation failure.

### 14.2 No-chess dependency firewall

The runner and generic content library MUST NOT contain or import:

- an `8`, `64`, or initial-position constant used as a board rule;
- piece, side, square, attack, legal-move, castling, en-passant, promotion,
  terminal, score, PGN, or game semantics;
- a chess library/core dependency;
- evaluator answers for held-out learner cases; or
- an alternate decoded slice.

Static dependency checks plus runtime canaries exercise at least:

- non-chess matrices with dimensions 5-by-7 and 7-by-5;
- a three-valued non-chess enum and a mask with a non-chess width;
- a non-chess state graph, passive trace, selection/commit/reset path, and
  exhausted budget; and
- arbitrary opaque binding bytes that remain uninterpreted.

A runner that only works because the pilot slice resembles chess fails G7 even
when the learner happens to complete it.

### 14.3 Learner slice content

The actual serialized slice teaches and tests, in a language-light sequence:

1. cell grid, locations, occupancy, and two distinguishable sides;
2. alternating turn;
3. one sliding piece and the knight;
4. movement versus capture;
5. attack versus legal move;
6. self-check;
7. one contrast covering castling, en passant, and promotion;
8. board-local versus history-dependent information;
9. one complete passive trace;
10. one finite selection/practice path; and
11. one short opaque move record and replay consequence.

Every representation fact appears in demonstrations before its scored
held-out use. Practice feedback may be artifact-carried; held-out expected
answers remain evaluator-side. The slice uses actual content-v0 bytes that were
packed through the preferred transport, then independently recovered for the
pilot runner. A developer-only hand-built equivalent stream does not close the
bridge.

Language independence is an executable G7 condition, not a descriptive label.
The runner has a frozen label-suppressed mode in which every `TEXT` payload on
a required teaching, practice, navigation, or scored semantic path is absent
from the rendered interface. Internal binding IDs remain opaque and are not
rendered as substitute semantic labels. The complete path must remain
navigable through its structural/artifact-carried relations, and
the available actions, committed semantic bindings, evaluator predicates, and
content-v0 event sequence must be exactly identical to the ordinary rendering.
The learner result-bearing bundle uses this label-suppressed mode. No required
distinction may depend on a Unicode code point's identity, a font/glyph
rendering, English, another natural language, or a current chess-notation
token.

Separate neutral interface help may use ordinary prose for mechanics such as
select, commit, reset, file access, or error display. Its exact bytes and use
are logged as interface assistance; it may not teach a semantic relation,
piece meaning, rule, answer, or artifact-specific decoding convention.

### 14.4 Interface and evaluator separation

The participant-facing runner may explain only neutral mechanics such as how
to select a region, commit, reset, or continue. The evaluator separately maps
opaque semantic bindings to M1-owned chess predicates and scores exact commits.

If the facilitator supplies a piece meaning, movement rule, legal answer,
special-rule interpretation, history fact, or move-record meaning verbally,
the affected acquisition result is non-gating and the event is a representation
failure. The learner may ask questions; the neutral response is to restate
interface mechanics or point back to artifact material without identifying the
answer.

## 15. Independent implementation, conformance, and reproducibility

### 15.1 Python/Rust boundary

Python and Rust independently implement:

- common block/envelope parsing and construction;
- extended-Hamming encoding/decoding;
- GF(256), RS encoding, and the selected errors/erasures decoder;
- both CRC algorithms and project preimages;
- mapping/inverse, fragment/section assembly, inventory, state taxonomy, and
  attempt/resource accounting;
- damage-channel parsing and deterministic sampling;
- recipe parsing/validation/evaluation; and
- candidate packing and recovery sufficient to reproduce the same carriers.

They may share promoted specifications, generated numeric constants whose
source is checked, and hand-authored conformance bytes. They MUST NOT share an
ECC/CRC/transport implementation through FFI, generated source copied between
languages, a common library, subprocess invocation, or one implementation's
serialized intermediate truth.

The single recipient-visible recipe package bound by a candidate's
`recipe_manifest` is a final artifact input, not serialized intermediate
truth. One bounded deterministic builder MAY emit those exact bytes after both
direct codecs and both recipe interpreters are independently complete. Before
the package enters a carrier, the other language must parse the complete bytes
and independently execute every exported interface plus the required KAT,
negative, boundary, and resource cases against its already-frozen direct
implementation. Both independent carrier packers then consume the same
hash-bound package bytes. Sharing this final artifact does not permit either
direct codec, interpreter, expected result, state decision, packer, or recovery
path to come from the other implementation, and does not require a second
serializer whose only product would be identical package framing.

No external ECC library is used by either artifact-critical implementation or
provided to the technical pilot. A temporary independent calculator may help
review vectors before installation, but it is not runtime authority and its
outputs become fixed reviewed bytes.

### 15.2 Candidate harness fairness

Both candidates consume the same semantic slice, common fragment/envelope
serializer, damage policy, seed list, geometry search rules, ledger schema,
state expectations, and report generator. Candidate-specific code is limited
to the promoted transport tuple and mapping parameters.

The harness MUST NOT:

- use candidate-specific easier probe/reserve/pad or semantic bytes;
- omit headers/parity/padding from a damage case;
- give one decoder evaluator truth or known damage positions unavailable on its
  channel;
- select different failed seeds, section maxima, or reserves;
- compare a debug implementation to an optimized implementation by wall time;
  or
- count shared shell/content costs for only one candidate.

### 15.3 Conformance placement

Tracked conformance suites contain only small, directly reviewed, literal
valid/invalid bytes and declare exact Python and Rust consumers. They cover:

- shell/bootstrap and recipe primitives;
- common blocks, sections, copies, inventories, and states;
- Hamming, RS, CRC, transform, mapping, and channel KATs;
- stable malformed/boundary rejection codes; and
- small cross-language pack/recover examples.

Full provisional carriers, 128-seed outcomes, large boundary objects, exhaustive
single-position loops, fuzz/mutation cases, and participant bundles remain
generated tests or ignored artifacts. No conformance payload exceeds the
existing registry limit merely to make a report self-contained.

### 15.4 Bounded malformed-input behavior

All observation, shell, recipe, block, section, manifest, and report parsers:

- validate the outer byte limit before decoding nested fields;
- validate counts before multiplication/allocation/looping;
- use checked integer arithmetic and exact consumed length;
- reject duplicate keys/IDs, noncanonical order, reserved bits, nonzero pad,
  overlap, dangling dependencies, and trailing bytes;
- expose no accepted prefix or repaired partial bytes;
- cap diagnostics and output independently of attacker-declared counts; and
- return one stable primary rejection according to the promoted precedence.

Fuzzing and mutation retain small regressions but never replace the finite
conformance/damage gates. Participant-submitted code and files are untrusted
attachments and are never discovered or executed by ordinary repository
checks.

### 15.5 Deterministic generation

Candidate generation is a pure function of tracked semantic inputs, promoted
specifications/policies, exact candidate ID, and declared generator version.
It does not depend on locale, timezone, current date, map order, thread count,
host path, process ID, RNG, cache state, or network.

For every candidate that reaches gate 8, Python and Rust independently attempt
to produce and compare:

- common/section/content bytes;
- shell and complete provisional matrix bits;
- packed row-major bytes;
- mapping and capacity totals;
- D0–D7 observations for the frozen deterministic cases; and
- normalized recovery bytes/states.

The candidate passes gate 8 only when every listed comparison is identical in
the native and clean-Linux runs. Reports may be generated by one implementation
only after the other supplies independently compared facts. A report never
resolves a cross-language disagreement; an exact disagreement eliminates that
candidate and remains reproducible evidence rather than making a different
candidate's valid result disappear.

For the active R3 candidate, `spec/gate8-policy-v0.toml` closes the four
producer receipts, eight exact comparison preimages, complete 72-file damage
bundle inventory, candidate-specific cross-language manifest, and ignored
Gate-8 path allowlist. Each Python/Rust native/Linux producer regenerates the
complete candidate, all 10,038 damage cases and canonical result artifacts,
and the nine-predicate proof. It may stream complete file hashes, but it may
not use the retained Gate-6 tree or another implementation's receipt as its
generated values. Gate-8 files never enter or expand the frozen candidate-root
allowlist.

The dynamic bundle-file cap is exactly 4,161,602 bytes, the complete
`OBS_MATRIX` framing `u16_be(2040) || 2040*2040 cell-state bytes`. The required
D3-000000 unknown-error and D2-000000 known-erasure observations attain that
cap; every other dynamic role is smaller. The independent aggregate cap remains
67,108,864 bytes across all 44 files and is checked from their exact lengths.

Each producer also rebuilds every required legacy v2--v6 recipient package
from the frozen v0 owners in its own language. Only the v3 route prefix consumed
by D7 route-conflict is built; route prefixes for v2/v4/v5/v6 are not applicable
and are not invented. Python's v3 input is independently built: neither a Rust
helper nor a retained archive is an allowed generation preimage. Retained
legacy bytes may be checked only after independent generation.

### 15.6 Source receipts

Before an implementation parameter is frozen from an external document, add an
exact receipt to `inputs/source-lock.toml` and its exact ID-to-role pair to the
validator's closed allowlist. The receipt includes immutable title/version,
locator, access date, byte length, SHA-256, retention, redistribution status,
and the one allowed role. At minimum, execution is expected to lock the exact
ETSI, RFC 9260, and ECMA-182 artifacts if their parameters remain in the
comparison.

Both source-lock loaders reject from the outer file metadata/read after 16,384
bytes; Python reads at most 16,385 bytes rather than calling an unbounded
`read_bytes`, matching the already-live Rust ceiling. Every decoded metadata
string is nonempty UTF-8 of at most 1,024 bytes, with the tighter existing ID,
path, digest, date/status, and closed-role grammars still applied. Reference
count is exactly the closed allowlist count. File/string/reference cap and
cap-plus-one fixtures run in both languages before TOML-driven allocation.

Theory/design citations such as Hamming, Reed–Solomon, interleaving, Voyager,
SETI exercises, or think-aloud research remain in `docs/sources.md` unless
their exact bytes become an implementation input. Do not lock unrelated
reading merely to make the ledger look comprehensive.

### 15.7 Clean Linux path

Before any candidate architecture, pilot bundle, or wire-visible M2 report is
frozen, implement the single Docker/OCI mechanism selected by M0:

- `tools/linux/Dockerfile` uses the exact Debian 13 slim multi-architecture
  digest recorded by M0 and both acquisition and verification explicitly select
  `--platform=linux/arm64` until an explicit provenance/platform refresh is
  reviewed;
- `.dockerignore` starts from an excluded context and positively admits only
  files needed to build the acquisition/verifier image;
- one explicit network-enabled acquisition/build command verifies tool payload
  identities and bakes immutable Python/Cargo/toolchain inputs into the image;
- ordinary Linux verification never rebuilds the verifier image or downloads;
  it does build and test the project offline inside disposable storage;
- the run uses `--network none`, no host language caches, and a real clean Git
  checkout in disposable writable container storage; and
- the in-container command is exactly the root `full` suite under the same
  locked/offline language flags.

The root `full` contract is Git-aware: repository checks consume HEAD, index,
worktree, tracked-file discovery, and every nonignored untracked path. The run
helper therefore creates an **ephemeral complete execution snapshot** of those
three layers, excluding only ignored paths under the same checked rule. Its
canonical-manifest-v0 object has exact top-level keys
`schema,head_oid,raw_index_sha256,entries`, schema value
`m2-execution-snapshot-v0`, and byte-sorted unique entries with exact keys
`path,head_mode,head_sha256,index_mode,index_sha256,worktree_mode,`
`worktree_byte_length,worktree_sha256,git_class`. A mode is `100644`, `100755`,
or `absent`; a digest is lowercase hex or `absent`; absent worktree has byte
length zero. `git_class` is derived from those layers and is exactly one of
`tracked_clean | index_modified | worktree_modified |
index_and_worktree_modified | index_added | index_added_worktree_modified |
index_deleted | worktree_deleted | index_modified_worktree_deleted |
index_deleted_worktree_present | untracked`. Rename/copy/unmerged states,
symlinks, and special files reject this release snapshot instead of being
flattened.

The helper copies the required Git objects and base HEAD, reconstructs the
exact index layer, then installs exact worktree bytes/modes. It independently
verifies every layer, `git diff --check`, `git diff --cached --check`, status
classification, and the manifest hash before running container `full`.
Staged bytes A plus different unstaged bytes B, a tombstone, and an untracked
file therefore remain distinct. Host and container execution-snapshot hashes
must be equal. That complete hash is deliberately transient: it is never
embedded in the report or any file inside the snapshot, which would be
self-referential once the report and roadmap status are included. The tracked
report instead binds the closed non-self-referential evidence-source projection
defined in Section 19.2 and records only that complete execution snapshots were
equal. A local no-hardlink clone is sufficient only for a clean source tree; a
plain clone must never silently replace dirty current bytes with `HEAD`.
It must not merely `COPY` a source-only tree. `.dockerignore` governs
image-build acquisition context; it is not a substitute for the
evidence-bearing checkout and does not admit host caches.

The verifier image is build provenance, not semantic input. Refreshing it reruns
Linux/reproducibility gates but does not change candidate bytes unless a real
cross-environment difference exposes a bug.

The small `m2-linux-attestation-v0` canonical manifest has exact keys
`schema,image_digest,platform,evidence_source_projection_sha256,host_full,`
`linux_full,execution_snapshots_equal,canonical_bytes_equal,states_equal,`
`ledgers_equal`. Digest/platform equal the acquired pinned image and
`linux/arm64`; both statuses are literal `pass`. `execution_snapshots_equal`
covers the complete host/container execution inputs. The other three equality
booleans cover exactly the deterministically selected retained-finalist set,
in preference order, and are literal true. A gate-8 losing candidate's unequal
facts remain in its candidate-specific `cross_language_manifest`; they are not
silently included in, or contradicted by, the retained-set aggregate. The
attestation contains neither complete execution-snapshot hash, report hash,
decision hash, nor mutable roadmap status, so its identity is non-self-
referential. The report and generated-evidence role cross-check every field.

If the coding sandbox cannot reach the Docker daemon, record the exact command
for the owner-controlled host. A denied daemon is not a pass and M2 cannot
close until the real run succeeds.

For R3, `image_digest` is exactly the literal per-refresh `image_id` value in
the strictly admitted `artifacts/linux/verifier-v0.env`: `sha256:` followed by
64 lowercase hexadecimal characters. It is not the image tag or Dockerfile
base-image digest. The receipt is the exact seven-line, 378-byte object frozen
by `linux_acquisition_receipt` in `spec/gate8-policy-v0.toml`; its raw hash,
tag, platform, contract, pinned base, Dockerfile hash, and image ID all match,
and `docker image inspect` independently returns that ID, platform, and both
owned labels. Verification still runs the exact image with `--network none`.
The local Docker image ID is acquired run provenance, not a claim that the
pinned base and Dockerfile determine byte-identical OCI output. Pinning mutable
APT package names alone is insufficient to make that stronger claim.

A different acquisition receipt or observed image ID invalidates the current
Linux attestation and every downstream Gate-8/report binding. It cannot be
silently accepted or overwrite an admitted receipt. The exact post-result
owner [`spec/gate8-verifier-refresh-v0.toml`](../spec/gate8-verifier-refresh-v0.toml)
first validates and privately archives the old 69-file tree, report, and
roadmap, increments the roadmap to revision 10, lowers M2 to `In progress`, and
removes the canonical old report/tree. The unavailable prior image is never
restored as Candidate-ready on failure. Gates 1--7 remain byte-identical. After
all owner/code/test bytes freeze, the ordinary pre-report path produces one new
source projection and four fresh producer receipts, and ordinary `assemble
--mode generate` installs the regenerated tree, report, and Candidate-ready
roadmap authority last. No old output supplies an expected new value. A future
changed acquisition needs another explicit transition; `acquire.sh` must fail
before `docker build` could retag an admitted image, and ordinary acquisition,
`full`, `linux`, and `release` never perform the refresh.

The source projection and both execution snapshots include every regular
nonignored byte under the five exact R3 history roots named by
`spec/gate8-policy-v0.toml`; live candidate and Gate-8 working trees remain
ignored and are regenerated. The pre-report/full and Candidate-ready/full
states are the two closed lifecycle states in that policy. A partial report or
Gate-8 tree rejects, removing the report/full bootstrap cycle without weakening
the final `release` check.

In pre-report state, host and Linux `full` invoke the policy's exact
`phase-check` command, which regenerates, validates, and discards Gates 1--7 in
an empty private work root and creates no Gate-8 receipt or report. In
Candidate-ready state, clean Linux receives a transient canonical manifest and
two native receipt byte strings bound to the independently rendered
evidence-source projection. Composed `release` supplies receipts freshly
generated by its preceding host `full`. Standalone `scripts/check linux` keeps
the Section 15.8 Git-plus-container-only host boundary: the pinned network-off
verifier strictly validates the retained Candidate-ready native receipts and
prepares the same transient input without running host Python or Rust. That
exact three-file directory is read-only and is neither source nor retained
evidence.

The exact admitted `artifacts/linux/verifier-v0.env` is supplied separately as
one read-only Candidate-ready provenance mount; it is never added to that
three-file directory or treated as a producer receipt. Only after host and
materialized-container execution-snapshot identities compare equal does the
container copy those exact 378 bytes to the receipt's ignored owner path in the
disposable materialized root. It requires exact byte equality and then
independently recomputes the complete execution-snapshot identity, which must
remain equal because the receipt is ignored run provenance rather than a
snapshot or source-projection entry. The copied receipt is destroyed with the
container. Missing, extra, linked, malformed, changed, prematurely installed,
or snapshot-visible provenance fails closed before Candidate-ready `full`.

Both modes generate fresh Linux receipts and derive the whole
Gate-8/report closure without opening the tracked report or ignored Gate-8
tree; only composed `release` establishes four fresh producers in one run.
Linux only then compares its complete derived report bytes with the tracked
report. It never fabricates a native column or uses the report to generate an
expected value. The exact modes, mounts, manifest rows, commands, read barrier,
and cleanup rules are owned by `spec/gate8-policy-v0.toml`.

Initial or post-refresh assembly does not require the live roadmap to preclaim
Candidate-ready. It renders from the exact live pre-Gate-8 roadmap; the
refreshed report serializes only revision 10 and the status-invariant normative
projection above. The assembler
stages and validates the prospective final state, installs the complete ignored
Gate-8 tree, installs the tracked report as generated-evidence authority, and
then changes the mutable roadmap status last. That last edit changes only the
derived `Project state` row and the Section 13 M2 status/evidence suffix frozen
by `roadmap_transition` in `spec/gate8-policy-v0.toml`. A failure rolls the new
tree and report back and preserves the pre-Gate-8 roadmap. Final installed
admission requires the exact Candidate-ready header and M2 row, preferred
candidate ID, and raw installed-report SHA-256; tree/report presence with the
old roadmap is a rejecting partial transition.

### 15.8 Root command closure

When M2 implementation exists, the public root surface adds only:

~~~text
scripts/check focused transport
scripts/check linux
scripts/check release
~~~

`focused transport` covers bootstrap, recipe, profile, damage, capacity,
transducer-slice, and cheap M2 report/schema units without redundantly running
every existing semantic suite or the complete 128-seed/full-carrier
reproduction. Existing focused areas remain unchanged. Host `full` is the sole
owner of that complete native reproduction and tracked-report staleness check.
Root `fast` invokes this same cheap focused-transport body alongside the
existing cheap areas; it does not call the expensive complete reproduction.

`linux` uses the already acquired verifier image and runs root `full` in the
network-disabled clean environment. It does not recursively call `release` and
does not auto-build the image.

The dispatcher recognizes `linux` and performs its mode-specific Git/Docker/
snapshot preflight before any host Python, uv, Rust, or rustup preflight. The
host needs no language toolchain to enter the independent verifier; those
tools come only from the acquired image. CLI tests exercise a host with those
language tools absent and require dispatch to reach the Docker invocation.

At M2, `release` is only an orchestrator: host `full`, then `linux`, then cheap
freeze assertions that the tracked report is the already-checked identity and
that no premature release package exists. It does not perform a third candidate
generation. M4 may add real package checks when a package has a consumer.
Unknown modes, extra arguments, missing image/acquisition evidence,
network-enabled verify, or inner-command drift fail. README, AGENTS, CLI tests,
and usage text move together.

## 16. Technical full-carrier pilot protocol

### 16.1 Terminology

- **participant:** one human;
- **recipient unit:** one participant or a fixed team of up to four;
- **pool:** unexposed units available for assignment;
- **round:** one candidate/protocol/unit combination;
- **session:** one contiguous active period in a round;
- **exposure:** first access to Golden Board-specific challenge material;
- **checkpoint:** immutable submitted source/notes/output state; and
- **diagnostic continuation:** useful post-hint/post-held-out work that cannot
  close the gate.

People are never called candidates in pilot files because transport/artifact
candidates already use that word.

### 16.2 Freshness and ability description

The elite-unit condition is selected before exposure, not inferred after a
failure. An individual or the fixed team collectively must have credible prior
work showing both substantial ordinary programming/debugging and success with
an unfamiliar structured-data, file-format, protocol, or reconstruction
problem. An existing portfolio, recommendation, or open-ended work description
is enough; there is no quiz, credential, demographic screen, or certification.
The frozen rule ID and its pass/fail result appear in the durable summary. One
anonymous sentence explaining the actual basis remains in the private
evaluator record while permission permits; it is not turned into a distinctive
public biography or a hash commitment to private biography text.

Recruitment itself must not teach the likely solution. Before exposure, each
member is asked only to describe, in their own words:

- difficult technical work they have done and how they approached it;
- languages and ordinary tools they expect to use;
- whether they have seen any unpublished message/challenge material, files, or
  links previously sent by this organizer or carrying the supplied opaque
  recruitment code; and
- voluntary access needs.

There is no participant-facing checklist naming binary techniques, matrices,
file-format families, reverse engineering, checksums, error correction, chess,
the project, or candidate profiles, and no tailored follow-up that supplies
those labels. A recruiter may use already-known portfolio facts privately.

Only after every result-bearing output is sealed does the debrief collect the
detailed prior inventory—including binary/matrix/parser/reverse-engineering,
checksum/ECC and exact profiles, chess, and project/repository knowledge—while
asking what was known before the run. Volunteered pre-run facts are recorded but
not probed with leading labels.

No unrelated demographics are collected. Seeing the project name, URL,
distinctive searchable phrase, challenge bits, decoded content, implementation,
shell/profile hint, or repository material makes that person exposed for later
fresh technical gates. They may still help diagnose revisions formatively.

### 16.3 Neutral opening prompt

The participant receives this meaning-equivalent prompt and no structural
hint:

> You have an indexed sequence of binary symbols. It is an intentional,
> finite message that is important, potentially profound, benign/nonhostile,
> and worth sustained effort. Wrong starts and backtracking are expected. Using
> only these symbols, your listed teammates, and ordinary
> bounded programming tools, recover the most defensible structure and content
> you can. Do not accept an interpretation only because its content looks
> plausible. Submit runnable source, exact recovered outputs and states, the
> observation evidence for every artifact-specific choice, every surviving
> rival interpretation, and every convention supplied by prior knowledge or
> guesswork.

The prompt/bundle MUST NOT mention a square, row-major order, sector, shell,
chess, grouping, CRC/ECC, profile, expected dimension/hash/output, repository,
or project name. It supplies total `N` and exactly `N` indexed bits in a simple
documented export format. A brief request not to search for or share
task-specific material until the round closes is sufficient; no NDA or secrecy
program is needed.

### 16.4 Round freeze

Before exposure, freeze and hash:

- candidate bitplane, profile/policy/spec identities, `N`, density envelope,
  and challenge bundle;
- recipient-unit membership and the neutral pre-run eligibility/freshness
  descriptions from Section 16.2 (not the post-seal profile inventory);
- allowed tools, information condition, facilitation/think-aloud mode;
- the seven-day/16-unit-active-hour total window, with a clean-phase cap of 12
  unit-active hours and five elapsed days so later work remains inside the
  total;
- all clean and held-out questions/observations, neutral later-channel storage
  schemas/mechanics fixtures, adapter boundary, and release order;
- evaluator expected bytes/states kept outside the participant share;
- exact success criteria, help taxonomy, and timeout/work limits; and
- participant information/data-retention note.

No expected hash, answer, generator seed, candidate source, profile name, or
evaluator manifest appears in participant-visible files.

### 16.5 Sessions and time accounting

The unit chooses the number and length of sessions within 16 hours of
**unit-active time** and seven elapsed days, beginning at first successful
challenge-file access. Unit-active time is the union of
intervals in which at least one member reads, reasons, codes, inspects output,
or discusses the task; parallel teammates do not multiply this clock.

**Person-time** is the sum of each member's active intervals and is reported
descriptively. Breaks, unrelated time, and evaluator-caused setup repair are
excluded and logged. Unattended computation is separately logged with command,
input/checkpoint, elapsed time, and the decoder's frozen operation/resource
count. It remains inside the elapsed window and cannot bypass machine work
ceilings.

Membership is fixed. Notes and source may persist across sessions. A new member,
outside-unit help, task-specific search, or solution-bearing cross-unit contact
changes the information condition and makes later work diagnostic.

### 16.6 Facilitation and help

Default work is silent individual work or natural fixed-team conversation.
Continuous think-aloud is not mandatory. If used, it asks only for thoughts
already occurring, uses no directed explanation, and becomes part of the
recorded pilot envelope. All causal “why?” probes wait until the sealed debrief.

Interventions use only this taxonomy:

| Kind | Example | Gating effect |
|---|---|---|
| Administrative/interface | repair bundle access, pause clock, restate file mechanics | allowed; exact event logged |
| Exact prompt repetition | repeat already visible neutral text | allowed; logged |
| Artifact-specific hint | suggest square, transform, grouping, code, parameter, location, or next decoding step | result-bearing round ends; continuation diagnostic |
| Answer revelation | supply expected bytes/state/meaning or confirm a hypothesis | result-bearing round ends; continuation diagnostic |

A safe response to a confirmation request is: “The observation and your
ordinary tools are the available evidence; I cannot confirm an interpretation.”
No hidden help is traded for a favorable time result.

### 16.7 Clean checkpoint and held-outs

For the active revision, pre-exposure automated readiness and provisional
qualification follow `spec/m2-participant-trials-v1.md`. Full release is not an
entry requirement. The saved-method boundary and staged information below remain
mandatory; the active no-timers/no-forms participant policy supersedes historical
administrative clock wording.

The unit first receives only the clean `OBS_BITS` reconstruction question. When
it declares the decoder ready—or at the first of 12 unit-active hours or five
elapsed days—the facilitator makes **checkpoint A** by copying and SHA-256
hashing:

- decoder core/source and dependency-free run instructions;
- derivation notes and artifact-specific choice table;
- normalized transform/mapping/grouping result;
- recovered stream/section states; and
- open-ended tool/document/help/prior-knowledge account.

No correctness feedback is given. Only after checkpoint A does the facilitator
release the pre-frozen neutral storage schemas and tiny nonsemantic mechanics
fixtures for later `OBS_MATRIX` and `OBS_UNITS` inputs. They were sealed before
initial exposure but withheld so they could not cue matrix/unit discovery. They
contain no candidate dimensions, actual operator, damage coordinates, profile
parameter, selector, or expected result.

If necessary, the unit may now add or change only a thin input-adapter file
that converts those documented storage forms into the observation types its
checkpoint-A core already declared. Adapter work counts as active time. The
core, derivation, recovered clean bytes/states, and artifact-specific logic stay
byte-identical; a substantive change makes the held-out result diagnostic.
The facilitator reviews only that narrow boundary, then seals **checkpoint B**
over core plus adapter before any actual held-out is shown.

All held-outs are then released together. The checkpoint-B program must:

- answer pre-frozen generic-record and chess-transition selectors against the
  already recovered clean stream;
- recover one within-profile unknown-error case;
- recover one known-erasure/spatial case;
- return the required missing-unit state; and
- explicitly reject one wrong-parameter/beyond-profile negative.

The four damage observations are separately named and carry their predeclared
channel. They do not reveal expected classification, operator label, clean
pre-damage values, evaluator-only placement/coordinates, hash, or answer beyond
the coordinates, erasure markers, or unit IDs inherently present in that named
channel. There is no intermediate correctness feedback. A core/adapter changed
after actual release remains useful diagnostic evidence; it cannot
retroactively pass either checkpointed gate.

Clean work, adapter work, selectors, held-outs, and the final account all stay
inside the same 16-unit-active-hour/seven-day total. Reaching the checkpoint-A
cap without a gating-ready clean submission is an unresolved clean-phase
result; later work may continue diagnostically but cannot escape the clock.

### 16.8 Required final account

The unit submits:

- runnable checkpointed source and exact command;
- canonical matrix/transform, grouping, map, and extracted bytes;
- per-section states and `m2_required`/`m2_all` availability;
- required held-out outputs/rejections;
- every complete recovered game/score record present in the pilot carrier;
- for every artifact-specific choice: selected value, observation evidence,
  alternatives rejected and how, and prior/unresolved status;
- rejected hypotheses and surviving rival interpretations;
- tools and generic documentation used;
- all assistance, accidental exposure, and outside communication; and
- unit-active time, person-time, session count, and unattended computation.

The evaluator computes developer-specific hashes afterward. A unit is never
failed for not knowing an untaught project identity domain.

The debrief may ask for a special-rule or record interpretation as useful
diagnostic feedback. It is not an M2 G6 transport gate: the pre-frozen generic
record/chess-transition selectors above provide the required semantic-boundary
check, while G7 separately tests representation acquisition with a chess-naive
learner.

### 16.9 Evaluator run and debrief

Participant source is untrusted data. After simple review, run it network-off
in a disposable bounded directory/container with explicit read-only inputs,
output directory, timeout, memory/output limit, and no repository secrets. This
is ordinary pet-project isolation, not a general sandbox product.

Seal the result before debrief. Then ask neutral retrospective questions about
ambiguities, evidence, stopping points, and likely improvements. Hints and
project revelation may follow, but every subsequent output is diagnostic.
Retrospective recollection supports design diagnosis; it is not proof of the
exact cognitive path.

### 16.10 Pass and retry rule

A successful predeclared provisional blind trial can qualify after complete
automated verification of its matching final candidate; it need not be repeated
solely because those checks ran later. Preserve its source/package, expected
results and conditions and reconcile them under `spec/m2-participant-trials-v1.md`.
Until then its result is pending. Formative or helped work cannot be relabeled,
and changing the workflow does not reset an exhausted unchanged-candidate retry.

A result-bearing round passes only when all roadmap tasks succeed within the
envelope, the evaluator reproduces the submitted outputs, critical hints are
zero, unresolved conventions/rivals are zero, and no member's exact-profile
prior supplied an untaught step.

M2 requires one qualifying fresh-unit pass after the latest material
recipient-visible change. It is not rigidly tied to the first person approached:

- a no-show/withdrawal before exposure may be rescheduled or replaced;
- a demonstrated defect in the frozen bundle, owner-supplied environment, or
  evaluator makes the round `invalid_environment`, not a recipient failure,
  but an exposed unit is no longer fresh for the repaired bundle; a
  participant's own tool choice/setup trouble is ordinary scored work;
- a hinted, contaminated, or answer-revealed round may continue diagnostically;
- an ambiguity or missing teaching step requires candidate revision and a new
  fresh unit;
- after one otherwise valid unresolved round on an unchanged candidate, one
  further fresh unchanged-candidate unit is allowed only after a factual
  difference in the units/conditions, the prediction that difference tests,
  and a stop rule are recorded before exposure; and
- two valid unresolved rounds on the unchanged candidate require redesign,
  scope narrowing, or an open gate—not open-ended recruitment until success.

A passing first unit with material exact-profile prior requires another fresh
unit. A material bootstrap/profile change after a pass also requires another.
A redesign resets the unchanged-candidate retry count only when it addresses a
recorded failure mechanism and materially changes recipient-visible evidence;
cosmetic bytes or wording do not. The first failure remains visible even if the
retry passes. The first fresh `no_material_prior` pass on the latest bundle is
the qualifying round; after it exists, any further unchanged-bundle work is
diagnostic rather than another opportunity to choose a preferred success.

Every exposed round with continuing data permission remains in the final
history, including failures, withdrawals, invalid environments, and diagnostic
successes. When a withdrawal requires deletion, retain only the explicitly
permitted non-identifying administrative count from Section 18.4 and never use
that round as a pass.

## 17. Learner micro-pilot protocol

### 17.1 Purpose and eligibility

The M2 learner micro-pilot asks whether the real generic representation is
learnable enough to justify full M3 authoring. It does not estimate population
performance or close M5 assessment gates.

A result-bearing learner is one chess-naive adult who has not completed a legal
orthodox game unaided and does not already know the slice's tested rule set.
Record a brief relevant prior description, not the full M5 selection machine.
Technical aptitude is welcome; the claim is about representation acquisition,
not average interface familiarity.

Learner acquisition evidence is individual. A collaborating learner team can
be a useful formative design session but cannot show which person acquired a
rule rather than receiving it from a teammate.

### 17.2 Bundle and flow

Before exposure, freeze the recovered content-stream hash, generic runner,
label-suppressed result-bearing mode, slice manifest, neutral interface
familiarization, teaching/practice order,
held-out cases/answers, event/time budgets, and help rules.

The learner:

1. completes one non-chess mechanics familiarization;
2. works through the real artifact-carried representation/demonstrations;
3. uses the finite practice/feedback path;
4. commits each held-out response once without correctness feedback; and
5. completes a sealed debrief after scoring.

The ceiling is three active hours across at most two sessions. Breaks and
administration are excluded and logged. The same frozen runner and
facilitation mode are used when interpreting timing.

### 17.3 Gating result

The exact M2 slice predicates and minimum acquisition rule are frozen before
the first learner. At minimum, a passing result must demonstrate the intended
board/side/turn, movement/capture, attack/legal/self-check, special/history
contrast, passive trace, finite selection, and opaque-record consequences
without verbal chess semantics.

An interface-mechanics clarification is allowed and logged. Any supplied chess
meaning/answer makes the affected result diagnostic and records the exact
representation gap. Missing, uncommitted, budget-exhausted, or malformed
responses are unavailable/failing, not silently omitted.

The pass rule, required predicates, and treatment of missing/malformed answers
cannot be weakened after any learner result is observed. A material
representation revision receives a new protocol/bundle identity and fresh
learner but keeps the same acceptance floor. A genuine reduction of the claimed
slice requires an explicit roadmap/spec revision that preserves the earlier
failure; it is not an ordinary formative edit.

### 17.4 Iteration and freshness

One or two learner micro-pilots are the default. Exposed learners may be reused
to diagnose small formative changes, but a material representation, symbol,
lesson-order, or answer-cue change requires one fresh learner to close G7.
Additional redesign rounds are allowed when they fix recorded gaps; every
round and prior exposure remains visible while summary permission continues,
with Section 18.4 controlling withdrawal/deletion. Repeating the unchanged
material
with a succession of learners until one happens to pass is not an acceptance
strategy.

If the first learner exposes a clear ambiguity, revise before M3 and use the
second fresh learner on the revision. If recruitment is temporarily unavailable,
the truthful M2 state is validation pending, not a fabricated pass.
The first fresh eligible pass on the latest learner bundle is qualifying;
later unchanged-bundle sessions are diagnostic.

## 18. Simple pilot folders and data handling

### 18.1 Tracked templates, private instances

Blank reusable templates live in `studies/m2/templates/`. Actual identity,
consent, notes, answers, submitted source, recordings, and evaluator keys live
under ignored `artifacts/private/m2-pilots/` or an owner-controlled directory
outside the repository.

The instantiated tree is:

~~~text
m2-pilots-private/
├── protocol.md
├── pools/
│   ├── technical.md
│   └── learner.md
├── work/
│   └── T001/
│       ├── participant.md
│       └── R01/
│           ├── round.md
│           ├── sessions/
│           │   ├── 01.md
│           │   └── 02.md
│           ├── 01-reconstruction/
│           │   ├── question.md
│           │   ├── files/
│           │   │   └── observation.bits
│           │   ├── answer.md
│           │   └── submitted/
│           ├── 02-channel-adapter/
│           │   ├── question.md
│           │   ├── files/
│           │   │   ├── channel-formats.md
│           │   │   └── mechanics-fixtures/
│           │   ├── answer.md
│           │   └── submitted/
│           ├── 03-held-outs/
│           │   ├── question.md
│           │   ├── files/
│           │   │   ├── content-query.md
│           │   │   ├── unknown-error.obs
│           │   │   ├── known-erasure.obs
│           │   │   ├── missing-unit.obs
│           │   │   └── negative.obs
│           │   ├── answer.md
│           │   └── submitted/
│           ├── 04-final-account/
│           │   ├── question.md
│           │   └── answer.md
│           ├── 90-debrief/
│           │   ├── question.md
│           │   └── answer.md
│           └── result.md
├── identity-consent/
│   └── T001/
│       ├── M01.md
│       └── M02.md
└── evaluator/
    └── R01/
        ├── expected.json
        └── bundle-manifest.json
~~~

Learner units use `L` IDs and question names appropriate to familiarization,
instruction/practice, held-out commits, and debrief. A unit may have multiple
versioned rounds and any number of session files inside the protocol ceiling.
Old rounds are never overwritten.

### 18.2 File contents

`participant.md` is owner-side and contains only opaque member IDs,
individual/team mode, neutral pre-run eligibility basis, post-seal detailed
abilities/prior exposure, tools, access needs, and freshness. For a team it
describes which abilities are collective without copying a distinctive public
biography.

`round.md` contains candidate/bundle/protocol hashes, fixed membership,
information condition, allowed tools, window/clock, facilitation/recording
mode, release order, and checkpoint identity.

Each session file contains each member's active half-open time intervals, the
derived unit-active union and person-time sum, files released, break/admin time,
exact participant questions and facilitator replies, outside/accidental
exposure, environment problems, and checkpoints.

Every participant-facing question directory contains:

- `question.md`: exactly the prompt asked;
- `files/`: exact files shown;
- `answer.md`: initially empty except for a heading and provenance field, then
  filled by the participant or marked `owner_transcription`; a transcription is
  participant-confirmed or explicitly remains unconfirmed; and
- `submitted/`: exact participant-created files, absent when none.

The technical answer template has compact sections for recovered outputs,
program/run command, artifact-specific choice/evidence/alternatives/prior,
surviving rivals, tools, and help/exposure. `result.md` records
`gating_pass`, `gating_fail`, `diagnostic_only`, `invalid_environment`, or
`withdrawn`, plus each gate, times, counters, hints, priors, unresolved facts,
and next action.

Pool files need only:

~~~text
unit ID | individual/team | opaque member IDs | fresh for gate yes/no | status | availability
~~~

No participant-management database or workflow service is introduced.

### 18.3 Separation and contamination rules

`work/`, `identity-consent/`, and `evaluator/` are owner-side and are never
shared wholesale. At each phase the owner releases only that current phase's
exact `question.md` and `files/` under a fresh share directory, records their
hashes, and receives the corresponding answer/submitted files. Future phases,
`participant.md`, `round.md`, sessions, results, debrief, and evaluator material
remain private until their stated release. A synced parent directory is never
the sharing mechanism.

Expected hashes/answers, candidate implementation/profile names, and generator
inputs never appear in a released subset before debrief.

- first task-specific file access changes every member to exposed;
- a candidate byte change opens a new round;
- a new teammate after exposure makes the round diagnostic;
- cross-unit sharing merges the information condition or contaminates both
  nominal rounds;
- repository discovery is logged and the continuation becomes diagnostic;
- a critical hint seals the pre-hint state and makes later work diagnostic;
- an evaluator packaging defect is not charged to the unit; and
- unsuccessful and invalid exposed rounds remain in summarized history while
  continuing permission exists; withdrawal/deletion follows Section 18.4.

### 18.4 Proportionate participation note

Use one plain page or equivalent email reply stating:

- owner/contact and a neutral high-level message-reconstruction or
  representation-learning purpose; for technical units, the exact project
  name/topic and solution-domain details are temporarily withheld to avoid
  cueing and are revealed after the result is sealed;
- what will happen, benign message premise, approximate time, and expected
  trial/error;
- data collected and who can access raw material;
- what anonymized facts may be published;
- concrete retention/deletion dates;
- voluntary participation and how to stop/withdraw before anonymized aggregate
  publication;
- temporary no-search/no-sharing request; and
- separate optional choices for audio/screen recording, direct quotation, and
  attribution.

Every member affirmatively agrees before exposure, with one small record linked
to that opaque member, unit, and round. Silence or a teammate's agreement is not
agreement. Recording, quotation, and attribution are separate opt-ins; refusing
them has no effect on participation.

Default is no audio/video recording. Source, notes, answers, timestamps, and a
debrief are sufficient. Use opaque IDs; keep name/contact mapping separate;
sanitize usernames/home paths; publish no contact, distinctive biography,
recording, quote, screenshot, or raw source without the specific permission.
Delete recruitment contacts when no longer needed, recordings after verified
notes, and raw pseudonymous working material after the report/retention window.

Withdrawal stops that member's participation immediately. Delete the covered
identity and member-addressable raw material according to the note. A team round
that used the member's contribution becomes non-gating unless every retained
joint artifact remains within every contributor's permission. The note may ask
to retain only one truly non-identifying administrative count such as “one
exposed round withdrew”; if a member does not affirm that narrow retention, no
unit ID, hash, timing, trait, quote, or unit-linked summary survives. A deleted
round is never silently converted into a pass or denominator success.

This is a respectful evidence practice, not a claim that a particular research
regulation applies. If the project later involves minors, vulnerable people,
institutional research, or identifiable public recordings, reassess before
continuing. Compensation, if any, is owner-authorized, time-based rather than
success-based, and disclosed; M2 does not create a purchasing workflow.

## 19. Durable evidence and downstream envelope

### 19.1 Candidate artifacts versus tracked evidence

Large candidate outputs remain under ignored `artifacts/candidates/<id>/`:

- provisional matrix and packed bytes;
- exact capacity/work/scratch/ownership ledgers;
- D0–D7 observations and candidate damage manifest;
- independent-generator comparisons and diagnostic logs; and
- failed/eliminated candidate outputs worth retaining during development.

Ignored artifacts are reproducible evidence, not normative owners. The compact
tracked `reports/m2-feasibility-v0.json` binds every input/spec/policy/candidate
and the SHA-256 of every generated manifest/ledger on which an M2 conclusion
depends. Ordinary checks regenerate automated evidence in temporary storage and
compare the tracked report fields; they never rewrite it.

### 19.2 Report schema

#### Revision 11 current report and evidence binding

This section remains the report-shape owner. For the revised M2 candidate,
[`spec/gate8-policy-v2.toml`](../spec/gate8-policy-v2.toml) is incorporated by
reference for its closed report keys, replacements, source identities,
selection, metrics, bundles, generated-evidence projection and lifecycle.
Its `report.base` reuses the row keys/types and top-level shapes below only
where that owner does not explicitly replace them. The current schema is
`m2-feasibility-v2`, the roadmap revision is 11, and the tracked path is
`reports/m2-feasibility-v2.json`. Historical v0/R3 report and pilot projections
in Sections 19.1–19.5 remain historical; they cannot be admitted as the current
result. The exact roadmap-normative-v0 byte projection below is still reused.

The active profile and unchanged policy ceilings come from
`spec/profile-policy-v2.toml` and `spec/profile-limits-v2.toml`; promotion and
unchanged gate order are bound by
`spec/m2-participant-revision-promotion-v2.toml`. The current report derives
exactly the v2 owner's 23 metrics from admitted current evidence. It retains
the sole active candidate only after automated gates 1–8 pass. A failed gate
leaves later unrun gates `not_evaluated`; no partial or losing run publishes a
Candidate-ready report. Historical candidates remain distinct diagnostic or
archive inputs, never alternative active finalists.

The required evidence follows these owning boundaries:

| Evidence | Exact owner |
|---|---|
| Independently source-built carrier, streams, capacity, ownership, density and static limits | `spec/static-projection-v2.md`, `spec/carrier-v2.md`, `spec/slice-v1.md` |
| Actual observed prefixes, checked body envelopes and recovered required/all streams | `spec/recovery-provenance-v2.md` |
| Finite carried relationship/use evidence from those observed bytes | `spec/knowledge-use-v2.md`, `spec/first-use-v2.md` |
| Source-derived bounds and exact observed logical accounting | `spec/receiver-bounds-v2.md`, `spec/resource-accounting-v2.md` |
| Full accidental damage, separate reauthored boundary probes and compact complete evidence | `spec/damage-corpus-v2.md`, `spec/damage-oracle-v2.md`, `spec/damage-replay-v2.md`, `spec/complete-damage-v2.md`, `spec/boundary-kat-v2.md` |
| Fresh physical predicates and complete damage-promise binding | `spec/physical-evidence-v2.md`, `spec/complete-damage-v2.md` |
| Four independent source-bound receipts, exact released files, comparison, selection and report | `spec/gate8-policy-v2.toml` |
| Archive-first source replacement and fresh execution/publication | `spec/m2-participant-revision-transition-v1.md`, `spec/gate8-execution-v2.md` |

The actual recovered required stream supplies the generic learner bundle;
source-equivalent reconstructed bytes cannot replace observation recovery.
The twelve unchanged final questions use authored intent and independent
public-chess derivation under `spec/learner-assessment-v2.md`; their answers
remain owner-only. `spec/runner-v1.md` preserves the old runner admission and
derives revised command/output bounds from the validated stream. Technical
recipient and owner files follow the v2 policy's exact roles and release order.
Finite software checks and shared question authorship are not fresh human
acquisition evidence.

The source projection and generated-evidence manifest use their v2 closed
schemas. The report binds all five semantic input identities and every
normative-owner path named by the v2 policy. Generated file identities flatten
the complete admitted candidate and Gate8 trees; source, receipts, report and
roadmap are ordered so none hashes itself. The acquisition receipt proves the
admitted environment only. Host/container execution-snapshot hashes are
compared transiently and never inserted into the source-stable attestation.

Current Candidate-ready output has empty technical/learner summary and
administrative-count arrays, qualifying IDs `none`, and human gate 9
`not_evaluated`. The v2 pilot object is exactly `validation-pending`. This
binding introduces no human-success schema, form, timer or additional
participant phase; fresh affected human validation remains necessary for M2.
The historical participation and completed-trial material below is preserved,
not reissued as revised participant instructions.

Apply and verify the exact archive-first transition before replacing primary
source. Keep its pending revision-11 roadmap unchanged during generation.
After all source owners, code, tests and templates are final, fresh producers
and assembly follow `spec/gate8-execution-v2.md`; install candidate, Gate8,
report and derived roadmap status in that order. `scripts/check components`
is only the non-Gate8 prerequisite suite. Revised `full` and `release` use the
v2 coordinator; release requires fresh native and clean-Linux reproduction.
No development comparison or retained historical pass enables handoff.

#### Preserved v0 and R3 report contract

The following text preserves its historical schemas, evidence and field
meanings. Only the explicitly inherited shapes and roadmap projection above
are reused by the current v2 report.

`docs/m2-spec.md` Section 19.2 is the M2 report-shape owner. For the active R3
candidate, the exact Gate-8-only paths, preimages, submanifest schemas, v1
bindings, and field derivations in `spec/gate8-policy-v0.toml` are incorporated
by reference and supersede only the v0 transport projections explicitly named
there. The report is
serialized as canonical-manifest-v0 bytes exactly as defined by
`spec/identity-v0.md`; it therefore has canonical UTF-8/LF JSON, sorted keys,
bounded values, no duplicate keys, and no `null`. Its top-level key set is
exactly:

~~~text
schema
roadmap_revision
m1_repository_baseline
semantic_input_identities
spec_policy_limit_source_lock_identities
candidate_rows
retained_finalist_ids
provisional_preferred_id
selection_steps
provisional_capacity_envelope
preferred_carrier_identity_and_density
damage_summary_D0_through_D7
cross_language_and_linux_results
technical_round_summaries
qualifying_technical_round_id
learner_round_summaries
qualifying_learner_round_id
m2_pilot_envelope
permitted_administrative_counts
accepted_limitations
generated_evidence_hashes
~~~

`schema` is exactly `m2-feasibility-v0`; `roadmap_revision` is the promoted
unsigned revision; and `m1_repository_baseline` is exactly
`0feaf4b559f48507f2457e6d203f25c969a98589`, the audited green M1 commit from
which M2 started. It is not the commit later containing this report and cannot
self-reference. Every identity/hash is a lowercase 64-hex string unless its
named owner defines another exact syntax. Arrays are present even when empty.
Each qualifying-round field is either its opaque round-ID string or the literal
string `none` in Candidate-ready state; it is never `null`, omitted, or an
empty guessed value.

`ReportId` is ASCII matching `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`; `none` is
reserved and never a real ID. `Hash` is 64 lowercase hexadecimal characters.
`Note` is 1–1024 printable ASCII bytes. All status values come from the closed
sets below. An object with a missing/extra key, an out-of-order/duplicate array
identity, an unregistered enum, or an out-of-bound value rejects.

Reusable exact row shapes are:

| Row | Exact keys and value types |
|---|---|
| `IdentityRow` | `kind: ReportId`, `name: ReportId or checked repository-relative POSIX path`, `sha256: Hash` |
| `TaskRow` | `task_id: ReportId`, `result: pass | fail | not_evaluated | diagnostic` |
| `SelectionRow` | inherited `golden-board.m2-selection-row/v0` keys `step, surviving_before, outcome, evidence_sha256`; step is one of the six frozen policy steps in order, `surviving_before` is an ordered unique candidate-ID array, and `outcome` is such an array or literal `no-passing-result` |
| `DamageRow` | `candidate_id: ReportId`, `family_id: D0..D7`, `manifest_sha256: Hash` of the complete matching `damage-Di.json` family-manifest bytes (never the root or a shard), `guarantee_id: all_declared_m2_sections_exact | m2_required_closure | correct_or_explicit_failure`, `result: pass | fail | not_evaluated`, `wrong_accept_count: u64` |
| `AdministrativeCountRow` | `kind: technical_withdrawn | learner_withdrawn`, `count: positive u64` |

A checked repository-relative POSIX path is nonempty printable ASCII, has no
leading slash, backslash, empty/`.`/`..` component, or trailing slash, and is
at most 255 bytes.

#### Dependency and evidence projections

The report does not accept arbitrary identity rows. It derives one
canonical-manifest-v0 `m2-evidence-source-v0` object with exact keys
`schema,roadmap_normative_sha256,entries`. `entries` contains every regular
nonignored repository file inspected by host `full`, using exact closed keys
`path,mode,byte_length,sha256`, mode `100644 | 100755`, `u64` length, lowercase
digest, and byte-sorted unique paths, except exactly
`docs/roadmap.md`, `docs/decisions.md`, and
`reports/m2-feasibility-v0.json`. M2 still forbids downstream release files.
The exclusions prevent report/decision/status identities from feeding back
into the report; they are not permission to omit code, tests, locks, specs,
tools, or generated limits.

`roadmap_normative_sha256` is SHA-256 over
`"golden-board:roadmap-normative:v0\0" || u64_be(len(immutable_prefix)) ||
immutable_prefix || u64_be(len(suffix)) || suffix`. Start with the exact roadmap
bytes before the unique `## 13. Project status` heading and remove the two
complete LF-terminated derived display rows whose unique prefixes are
`| Project state | ` and `| Current milestone | `; the remaining bytes, in
their original order, are `immutable_prefix`. Each removed row must have no
additional `|` before its literal ` |` line ending. `suffix` begins at the
unique `## 14. Adversarial stress matrix` heading and runs through EOF. Missing,
duplicate, reversed, or non-LF boundaries and missing/duplicate/malformed
derived rows reject. Changing only those two derived rows or Section 13 cannot
change this digest; changing any other roadmap byte must change it. Thus
mutable status may bind the report hash without a cryptographic cycle, while
every other roadmap byte remains bound. `evidence_source_projection_sha256`
is SHA-256 of the exact canonical source-projection object.

`semantic_input_identities` is exactly the source-projection rows for
`docs/64_games.md`, `reports/source-doctor.json`,
`reports/source-compilation-v0.json`, `reports/game-set-v0.bin`, and
`studies/m2/slice-v0.json`, with `kind=semantic_input`.
`spec_policy_limit_source_lock_identities` is exactly the rows for
`docs/m0-spec.md`, `docs/m1-spec.md`, `docs/m2-spec.md`, the virtual roadmap
normative projection, `inputs/source-lock.toml`, `conformance/registry.toml`,
and `spec/identity-v0.md`, `spec/chess-v0.md`, `spec/source-v0.md`,
`spec/content-v0.md`, `spec/curriculum-v0.toml`, `spec/constants-v0.toml`,
`spec/bootstrap-v0.md`, `spec/profile-policy-v0.toml`,
`spec/profile-limits-v0.toml`, and `spec/damage-policy-v0.toml`, with
`kind=normative_owner`. Names are exact paths except the virtual name
`roadmap-normative-v0`; each file row's SHA is its matching entry's raw-file
SHA, while the virtual row uses the normative projection digest. Every row hash must equal its source-projection entry or
the virtual digest; missing/extra/substituted rows reject. Exact M2 external
reference IDs are closed by the bound source lock and candidate policy rather
than copied into a second mutable list.

The active R3 report replaces the live v0 transport-owner subset with the
exact `report_r3_overlay.normative_owner_paths` set in
`spec/gate8-policy-v0.toml`. That set includes bootstrap/profile/damage/route/
limits/promotion v1, the R3 KAT and design, and the Gate-8 policy itself. The
historical v0 transport owners remain bound through the v1 base/archive
admission; duplicating their mutable live paths as active report rows rejects.

The generated-evidence preimage is a canonical-manifest-v0 object with exact
keys `schema,shared_identities,candidate_evidence,round_summary_identities` and
schema `m2-generated-evidence-v0`. `shared_identities` has exactly one
IdentityRow for each role
`content_stream, vertical_slice, semantic_envelope, profile_limits_derivation,
side_search_policy, evidence_source_projection, selection_recomputation, linux_attestation,
technical_bundle, learner_bundle`. The pilot envelope is report-owned and is
deliberately not hashed into this manifest because it contains the manifest
hash. `candidate_evidence` is in policy order and has exact keys
`candidate_id,identities`. Its identities are the concatenation, in gate order,
of this exact reached-gate table:

| Gate | Required evidence roles when evaluated normally |
|---:|---|
| 1 | `parameter_manifest`, `known_answer_manifest` |
| 2 | `shell_manifest`, `recipe_manifest` |
| 3 | `grammar_state_manifest` |
| 4 | `work_scratch_ledger` |
| 5 | `carrier`, `ownership_ledger`, `capacity_ledger`, `density_ledger` |
| 6 | `damage_manifest`, `damage_D0` through `damage_D7` |
| 7 | `independence_proof` |
| 8 | `cross_language_manifest` |

A checked lower-bound shortcut includes prior passed-gate roles then one
`elimination_bound` role for the failed gate and no later-gate roles. A
normally evaluated failed gate includes that gate's complete roles and no later
roles. Thus an early elimination cannot fabricate a carrier, damage run, or
cross-language identity, while every retained finalist necessarily has the
full gate-1-through-8 role closure. `round_summary_identities` has exactly one
canonical-row identity for every retained technical/learner `RoundSummary`,
sorted by `(kind,name)`.

Shared rows use `kind` equal to the displayed role and these exact `name`
values/preimages:

| Role | Name | Hashed bytes |
|---|---|---|
| `content_stream` | `m2_all` | exact raw `m2_all` ContentStream bytes |
| `vertical_slice` | `slice-v0` | canonical slice-binding manifest from Section 13.2 |
| `semantic_envelope` | `capacity-envelope-v0` | canonical bucket/atomic-slot/copy-class manifest from Section 10.3 |
| `profile_limits_derivation` | `profile-limits-v7` for active R3 | exact owner projection and source rows owned by `spec/gate8-policy-v0.toml` |
| `side_search_policy` | `side-search-v7` for active R3 | exact owner projection and source rows owned by `spec/gate8-policy-v0.toml` |
| `evidence_source_projection` | `m2-evidence-source-v0` | exact source-projection manifest above |
| `selection_recomputation` | `selection-v0` | canonical gate/metric/step/finalist recomputation manifest |
| `linux_attestation` | `linux-v0` | canonical image/platform/source-projection/result attestation from Section 15.7; no complete execution-snapshot hash |
| `technical_bundle` | `technical-v0` | exact canonical released-file bundle manifest frozen before technical exposure |
| `learner_bundle` | `learner-v0` | exact canonical released-file/input-stream bundle manifest frozen before learner exposure |

Candidate rows use `kind` equal to their displayed role, `name` equal to the
candidate ID, and hash exact raw carrier bytes only for `carrier`; every other
role hashes the canonical-manifest-v0 bytes of the like-named generated
manifest/ledger owned by the bootstrap, profile-policy, or damage specification.
D-family rows hash the complete family observation/result manifest, not an
individual convenient seed. Round-summary rows use
`kind=technical_round_summary | learner_round_summary`, `name=round_id`, and
the canonical RoundSummary object bytes. Before generation, each smallest owner
freezes its closed manifest keys; an unowned JSON blob is not a valid preimage.

For active R3, Gate-1-through-4 roles hash the eight exact owner-projection
schemas/paths in `spec/gate8-policy-v0.toml`; Gates 5--7 hash the unchanged
canonical candidate/damage bytes, and Gate 8 hashes the eight-row four-producer
cross-language manifest. The matching `DamageRow.manifest_sha256` hashes the
family manifest. Its `damage_manifest_identity` must bind the sole admitted
root damage manifest, so family evidence cannot be transplanted between roots.

`generated_evidence_manifest_sha256` is SHA-256 of those exact canonical
manifest bytes. `generated_evidence_hashes` is exactly the unique flattening of
all three identity collections, sorted by `(kind,name)`, and every CandidateRow,
DamageRow, bundle, and summary field cross-checks its corresponding row. The
report schema directly checks the pilot envelope without putting it inside its
own hash closure. The shared `evidence_source_projection` row and
`cross_language_and_linux_results.evidence_source_projection_sha256` both equal
the source-projection hash above. `provisional_capacity_envelope.retained_ledger_identities` is exactly the
ownership, capacity, density, work/scratch, and damage-manifest rows for each
retained finalist, serialized once in unique `(kind,name)` order; finalist
preference affects set derivation, not this array's canonical sort. No ignored
large artifact is copied into the report; its required manifest identity is.

A `CandidateRow` has exactly
`candidate_id, tuple_identity, policy_identity, complexity_class, metrics,`
`hard_gates, disposition, reason_code, reason`. `candidate_id` is a
`ReportId`; `tuple_identity` and `policy_identity` are `Hash`; class is
`C0 | C1 | C2`; disposition is
`eliminated | retained | preferred`; reason code is `ReportId`; reason is a
`Note`. `metrics` is the exact-set unsigned metric map frozen in
`profile-policy-v0.toml`; `hard_gates` is its exact-set gate-ID object with
only `pass | fail | not_evaluated`. No report may add a metric or gate after
seeing a candidate result.

For R3, the exact tuple canonical object, policy hash preimage, metric keys and
derivations, gate-key order, factual reason, and disposition values are those
in `spec/gate8-policy-v0.toml`. In particular, `policy_identity` hashes raw
`spec/profile-policy-v1.toml` bytes, and the tuple includes profile version 7,
the hierarchical transport, CRC-32C checks, two-stage map, one semantic copy,
and physical factors `[1,2,5]`. No v0 `copy_count` field is inferred.

A technical or learner `RoundSummary` has exactly
`round_id, unit_id, candidate_id, headcount, mode, fresh, eligibility_rule_id,`
`eligibility_result, information_condition_id, prior_assessment, bundle_sha256,`
`checkpoint_a_sha256, checkpoint_b_sha256,`
`output_sha256, content_stream_role, content_stream_sha256,`
`evaluator_reproduction, session_count, unit_active_seconds,`
`person_time_seconds, elapsed_seconds,`
`administrative_help_count, prompt_repeat_count, critical_hint_count,`
`answer_revelation_count, unresolved_rival_count, task_results, gating_status,`
`permission_state`. IDs/hashes use the types above; either checkpoint hash and
`output_sha256` may be `none` only when that item does not exist; mode is `individual |
team`; `fresh` is a boolean; eligibility result is `pass | fail`; prior
assessment is `no_material_prior | exact_profile_prior |
other_material_prior | unknown`; gating status is `gating_pass | gating_fail |
diagnostic_only | invalid_environment | withdrawn`; permission state is
`summary_permitted`; counts are `u64`, `headcount` is `1..4`, and
`task_results` contains every frozen task exactly once in protocol order.
A round without continuing summary permission has no row at all.
`content_stream_role` is `recovered | learner_input | none`; its hash is a
`Hash` exactly for the first two and the literal `none` for the last.
`evaluator_reproduction` is `pass | fail | not_evaluated`.

The remaining top-level value types/shapes are exact:

| Key | Exact type/shape |
|---|---|
| `semantic_input_identities`, `spec_policy_limit_source_lock_identities`, `generated_evidence_hashes` | the exact nonempty `IdentityRow` projections/flattening defined above, sorted uniquely by `(kind,name)` |
| `candidate_rows` | nonempty `CandidateRow` array with unique IDs in frozen policy enumeration order |
| `retained_finalist_ids` | one or two unique `ReportId` values in deterministic preference order |
| `provisional_preferred_id` | the first retained finalist ID |
| `selection_steps` | exactly six `SelectionRow` values in inherited policy step order; rows contain no ordinal/rule-ID aliases |
| `provisional_capacity_envelope` | exactly `profile_limits_sha256: Hash`, `semantic_envelope_sha256: Hash`, `side_search_policy_sha256: Hash`, `retained_ledger_identities: nonempty IdentityRow array sorted uniquely by (kind,name)`; active R3 hashes raw `spec/profile-limits-v1.toml` and the v7 projections |
| `preferred_carrier_identity_and_density` | exactly `candidate_id: ReportId`, `carrier_sha256: Hash`, `ownership_ledger_sha256: Hash`, `density_ledger_sha256: Hash`, and `N,S,W: u64` |
| `damage_summary_D0_through_D7` | exactly eight `DamageRow` values per evaluated candidate, candidate policy order then D0..D7 |
| `cross_language_and_linux_results` | exactly `evidence_source_projection_sha256: Hash`, literal `host_full: pass`, literal `linux_full: pass`, and literal-true `execution_snapshots_equal, canonical_bytes_equal, states_equal, ledgers_equal`; the first equality covers the complete host/container execution inputs, the other three cover exactly the retained-finalist set in preference order, and complete execution-snapshot hashes are compared transiently and never embedded |
| `technical_round_summaries`, `learner_round_summaries` | `RoundSummary` arrays sorted by round ID; empty is allowed before independent validation |
| `permitted_administrative_counts` | unique `AdministrativeCountRow` array in the displayed enum order; absence of a kind makes no claim that its real count was zero |
| `accepted_limitations` | unique nonempty `Note` array sorted by ASCII bytes |
| `m2_pilot_envelope` | the exact three-object shape in Section 19.3 |

Unless a field above declares semantic order, every `IdentityRow` array sorts
uniquely by `(kind,name)`, every candidate-ID array uses frozen policy
enumeration order, and every `{N,S}` pair array sorts uniquely by `(N,S)`.
Protocol task arrays preserve frozen protocol order; selection steps preserve
the exact six-step policy order; finalist IDs alone preserve deterministic
preference order.

Before human validation, active R3 has empty technical/learner summary arrays,
both qualifying IDs `none`, and an empty `permitted_administrative_counts`
array. Its two exact accepted-limitations strings, technical/learner bundle
schemas and role-to-path/preimage maps, singleton geometry proof, and every
`m2_pilot_envelope` field derivation are frozen in
`spec/gate8-policy-v0.toml`. Bundle self-hashes or arbitrary role files cannot
satisfy those mappings.

Cross-field validation is fail-closed:

- `mode=individual` requires `headcount=1`; `mode=team` requires
  `headcount=2..4`; a gating pass requires `fresh=true`,
  `eligibility_result=pass`, no critical hint or answer revelation, and zero
  unresolved rivals, a non-`none` output, and `pass` for every frozen task.
  Its evaluator reproduction is `pass` and its session count is positive.
  Technical gating passes additionally require both checkpoint hashes,
  `content_stream_role=recovered`, `unit_active_seconds<=57600`, and
  `elapsed_seconds<=604800`; learner gating passes require individual mode,
  `content_stream_role=learner_input`, `session_count<=2`, and
  `unit_active_seconds<=10800`. Always
  `unit_active_seconds<=elapsed_seconds`; individual person-time equals
  unit-active time, while team time satisfies
  `unit_active_seconds<=person_time_seconds<=headcount*unit_active_seconds`
  under checked arithmetic;
- every summary's candidate exists in `candidate_rows`; exactly one candidate
  row is `preferred`; `retained_finalist_ids` is exactly the preferred row
  followed by any `retained` row, and equals no eliminated row;
  `provisional_preferred_id` and the preferred-carrier candidate equal that
  first ID. A retained/preferred row has no failed hard gate; an eliminated row
  names the first failed gate or checked lower-bound elimination in the frozen
  gate order and every later unrun gate is `not_evaluated`;
- a qualifying-round field is `none` exactly when there is no unique eligible
  fresh `gating_pass` summary for the preferred candidate, matching technical
  or learner bundle identity, and `prior_assessment=no_material_prior`;
  otherwise it names that row. An `exact_profile_prior` technical pass cannot
  itself qualify and requires a distinct fresh `no_material_prior` pass to
  close G6. Once a qualifying row exists, a later unchanged-bundle row cannot
  also be result-bearing;
- D0, D1, and D5 rows use `all_declared_m2_sections_exact`, covering real
  content plus every capacity/reserve/load-probe and other inventoried section,
  not merely the `m2_all` content frame; D2, D3, D4, and D6 use
  `m2_required_closure`; D7 uses `correct_or_explicit_failure`. An RT0--RT4
  guarantee name is invalid in an M2 report; any row with nonzero
  `wrong_accept_count` has `result=fail`, and no passing row has one; and
- every tracked report already represents Candidate-ready automated evidence,
  so host/Linux full are unconditionally pass, their transient complete
  execution snapshots are equal, and canonical bytes, states, and ledgers are
  equal for exactly the retained finalists in preference order. Each eliminated
  gate-8 candidate instead cross-checks its own pass/fail and differing facts
  against its candidate-specific manifest. A failed or pending host/Linux run
  remains ignored diagnostic evidence and cannot be serialized as a green
  tracked report;

The preferred-carrier `N`, `S`, and `W` equal `raw_geometry.observed_N`,
`raw_geometry.observed_S`, and `technical_invariance.shell.W`; its carrier hash
equals `evidence_identities.carrier_sha256`, and its candidate equals
`technical_invariance.transport.candidate_id`. Its ownership and density
ledger hashes equal the like-named evidence identities. The qualifying
technical and learner summary bundle hashes, when their qualifying IDs are
non-`none`, equal, respectively,
`evidence_identities.technical_bundle_sha256` and
`evidence_identities.learner_bundle_sha256`.
When both qualifying IDs are non-`none`, both summaries'
`content_stream_sha256` equal
`evidence_identities.m2_all_content_stream_sha256`: the first is the technical
unit's independently recovered stream and the second is the learner's actual
input. The frozen learner bundle/input manifest contains and checks that same
hash; a developer-decoded substitute cannot satisfy the bridge.
`learner_invariance.content_stream_sha256` equals
`evidence_identities.m2_all_content_stream_sha256`, and
`learner_invariance.slice_sha256` equals
`evidence_identities.vertical_slice_sha256`. Every admitted geometry has
checked `N=S*S`, `S` divisible by eight, and `64<=S<=2048`. The observed pair
is present. Every ppm bound is at most 1,000,000. These equalities are validated
with checked integer arithmetic, not inferred from matching filenames.

Every retained/preferred candidate has `pass` for every policy gate marked
`automated` (gates 1--8) and exactly one D0--D7 row per family, all sharing that
candidate's one damage-manifest identity and all passing with zero wrong
accepts and the family-specific guarantee above. For every damage-evaluated
candidate, hard gate 6 is pass if and only if those eight rows pass; a
pre-gate-6 elimination has no rows. The policy freezes each gate's
`automated | preferred_human` phase before results. An M2 completion report
also has `pass` for the preferred candidate's `preferred_human` gate, both
qualifying IDs non-`none`, and the qualifying rows required above. Before that,
Candidate-ready evidence may use `none` for a genuinely pending qualifying ID;
it cannot spell a pending human gate as pass.

The tracked report first exists only after automated Candidate-ready facts
exist, so finalist, preferred-carrier, and generated-evidence fields are never
placeholder-empty. The full canonical report remains within identity-v0's
1 MiB/depth bounds. Automated fields are regenerated by host `full` and
compared to the tracked bytes. Reviewed human summaries are schema- and
cross-field-checked but are durable evidence, not regenerated from private
files after permitted deletion.

Each candidate row has its exact tuple/policy identity, class, complete metric
row, hard-gate vector, eliminated/retained/preferred state, and stable factual
reason. A non-run gate is `not_evaluated`; it is never encoded as pass.

Human summaries use opaque round/unit IDs and include headcount, information
condition, prior-exposure/profile-prior assessment, sessions, unit-active and
person-time, help counts, checkpoint/bundle/output identities, every task
result, unresolved rival count, and gating status. They contain no name,
contact, biography, quote, raw source, or recording. Raw unit counts are
reported; no percentage, p-value, confidence interval, or population language
is computed.

Private raw data may later be deleted under the participation note. The durable
report keeps only the reviewed minimal facts and hashes necessary to interpret
the claim; a hash is not treated as consent to publish the hashed private file.

### 19.3 Exact M2 pilot envelope

The report must preserve enough recipient-visible detail for downstream change
decisions. `m2_pilot_envelope` contains three explicitly separate objects:
`technical_invariance`, `learner_invariance`, and `evidence_identities`.

`evidence_identities` has exactly
`m2_all_content_stream_sha256, vertical_slice_sha256, carrier_sha256,`
`exact_cell_count_ledger_sha256, ownership_ledger_sha256,`
`density_ledger_sha256, technical_bundle_sha256,`
`learner_bundle_sha256, generated_evidence_manifest_sha256`, each a `Hash`.
This object binds the exact M2 bytes and exact
real/capacity-probe/reserve-probe/load-probe/pad counts that were tested. Those
facts are evidence identities, not automatically an M4 G6
rerun condition.

Duplicate convenience fields are exact equalities, never independently
authored hashes:

| Report field | Must equal |
|---|---|
| `evidence_identities.m2_all_content_stream_sha256` | shared `content_stream` row |
| `evidence_identities.vertical_slice_sha256` | shared `vertical_slice` row |
| `evidence_identities.carrier_sha256` | preferred candidate `carrier` row |
| `evidence_identities.exact_cell_count_ledger_sha256` | preferred candidate `capacity_ledger` row |
| `evidence_identities.ownership_ledger_sha256` | preferred candidate `ownership_ledger` row |
| `evidence_identities.density_ledger_sha256` | preferred candidate `density_ledger` row |
| `evidence_identities.technical_bundle_sha256` | shared `technical_bundle` row |
| `evidence_identities.learner_bundle_sha256` | shared `learner_bundle` row |
| `evidence_identities.generated_evidence_manifest_sha256` | recomputed exact `m2-generated-evidence-v0` bytes |
| `provisional_capacity_envelope.profile_limits_sha256` | raw-file SHA in the active limits normative-owner row: `spec/profile-limits-v1.toml` for R3, otherwise v0 |
| `provisional_capacity_envelope.semantic_envelope_sha256` | shared `semantic_envelope` row |
| `provisional_capacity_envelope.side_search_policy_sha256` | shared `side_search_policy` row |
| preferred carrier/ownership/density fields | the same preferred candidate rows above |
| `technical_invariance.transport.parameter_manifest_sha256` | preferred candidate `parameter_manifest` row |

Every other hash nested inside a generated manifest is recomputed from that
manifest's owning schema before its outer IdentityRow is accepted. A mismatch
is report staleness, not a second valid identity.

`technical_invariance` has exactly these nested objects and no scalar shortcut:

| Object | Exact keys |
|---|---|
| `raw_geometry` | `observed_N: u64`, `observed_S: u64`, `admitted_N_S_pairs: nonempty array of exact `{N:u64,S:u64}` objects sorted uniquely by `(N,S)`, `equivalence_proof_sha256: Hash` |
| `shell` | `W: u64`, `complete_bytes_sha256: Hash`, `complete_cells_sha256: Hash`, `sector_ownership_sha256: Hash` |
| `bootstrap` | `framing_sha256, dependency_graph_sha256, recipe_sha256, operation_set_sha256, tables_sha256, discriminator_sha256: Hash`; `grouping_id, bit_order_id, traversal_id: ReportId` |
| `transport` | `candidate_id: ReportId`; `parameter_manifest_sha256, common_grammar_sha256, protected_semantics_sha256, state_semantics_sha256: Hash` |
| `mapping` | `formula_id: ReportId`; `parameters_sha256, inverse_proof_sha256: Hash` |
| `interior_bounds` | `density_min_ppm, density_max_ppm, tile_density_min_ppm, tile_density_max_ppm, max_horizontal_run, max_vertical_run, max_repeated_rows, max_repeated_columns: u64` |
| `challenge` | `export_format_sha256, neutral_prompt_sha256, heldout_class_manifest_sha256: Hash` |
| `recipient_condition` | `mode: individual | team`, `headcount: 1..4`, `allowed_tools_sha256, session_policy_sha256, facilitation_sha256, think_aloud_sha256: Hash`, `active_time_ceiling_seconds, elapsed_time_ceiling_seconds: u64` |

The ppm ranges are inclusive integer counts per million; minima do not exceed
maxima. The complete technical object therefore carries every fact on the
roadmap's M4 trigger list while leaving current M2 content/probe cell counts in
`evidence_identities`. The comparison implementation requires exact equality
for fixed fields and membership of the exact `(N,S)` pair in
`admitted_N_S_pairs`. Interior and every aligned tile density must lie inside
their respective inclusive stored min/max range; each observed horizontal
run, vertical run, repeated-row count, and repeated-column count must be less
than or equal to its named stored maximum. There is no generic “similar”
branch.

`learner_invariance` has exactly
`content_stream_sha256, slice_sha256, runner_sha256,`
`label_suppressed_config_sha256, teaching_practice_order_sha256,`
`semantic_path_sha256, facilitation_sha256, learner_condition_sha256,`
`time_policy_sha256`, each a `Hash`.

The default admitted `N`/side equivalence class contains only the exact
observed `N` and `S`; its proof manifest records that singleton fact. A wider
side family counts only when the finite class and checked proof were frozen
before exposure and show that every member has the same complete shell
bytes/routes, bootstrap operations, parameter derivation, and predeclared
density/regularity conditions. `equivalence_proof_sha256` binds that exact
manifest. Merely sharing a formula or fitting an admissible roadmap family
does not generalize one run.

At M4, any fact on the roadmap trigger list outside `technical_invariance`
causes the fresh selected-candidate technical pilot. Changed M3 lesson/content
bytes that keep all those transport-visible facts inside their predeclared
range do not trigger G6 merely because their hashes differ. The M2 report and
its `evidence_identities` remain immutable; M3/M4 record their new hashes in
their own evidence and compare their technical facts with this envelope.
Learner-affecting changes require the fresh learner evidence owned by G7/M3/M5.
A change confined to already piloted fixed reserve/padding inside the technical
envelope does not trigger G6. If a trigger field is absent or too vague to
compare, M4 assumes it changed and reruns the technical pilot.

### 19.4 Decision note

An incompatible pre-result restart reached through roadmap Section 3.5 may
create `docs/decisions.md` with one concise dated design entry that explicitly
claims no new candidate outcome. After measured selection, append one concise
dated M2 selection entry without rewriting an earlier restart entry. The
selection entry contains:

- candidates/checks considered;
- hard eliminations and retained finalists;
- provisional preference and report hash;
- why the lowest passing complexity class won;
- accepted limitations; and
- explicit M4 actual-content rerun obligation.

It does not reproduce metric tables, raw logs, or approvals and does not become
a recurring meeting/governance journal.

### 19.5 Status transition

Roadmap M2 remains `Not started` while only this design exists. Once executable
M2 work begins, the owner may set it `In progress`. It becomes:

- `Candidate ready — independent validation pending` when automated candidate,
  Linux, and bundle gates pass but a qualifying technical or learner unit is
  unavailable;
- `Needs revision — <specific failed gate>` when real evidence exposes a
  correctable M2 design failure;
- `Blocked — <specific external prerequisite>` only for a concrete external
  blocker; or
- `Complete — <date and candidate/report identity>` only after G5–G8 and
  `scripts/check release` pass.

The completion row names the retained/preferred IDs and tracked report hash. No
check edits the status automatically.

## 20. Flexible execution envelope

### 20.1 Dependency order

This is a dependency order, not a day-by-day project plan:

1. **Admission:** promote roadmap/spec clarifications; extend source-lock and
   repository guards narrowly; add the real clean-Linux acquisition/run path.
2. **Shared bytes and real slice:** freeze common block/section/inventory/
   tier-frame framing and CRC tuples; add the bounded content authoring/view
   APIs, actual Core 0, learner/chess/all-game bytes, generic runner, and
   non-chess/language-independence canaries.
3. **Co-frozen policies:** before candidate outcomes, promote the exact
   Hamming/RS/copy/check tuples, recipe-language union, bounded mapping family,
   damage channels/operators/seeds, complexity/work metrics, and selection
   rules.
4. **Candidate primitives and recipes:** implement independent codecs,
   recipe interpreters, all four complete shell routes, knowledge-use linter,
   KATs, negative vectors, ablations, and exhaustive small cases.
5. **Complete manifestations:** generate each complete shell,
   real/capacity/reserve/load-probe carrier, map/inverse,
   ownership/capacity/work/scratch ledger, and provisional
   union-safe limits over the full frozen candidate-tuple set from the same
   semantic envelope, before observing candidate outcomes.
6. **Damage realization:** derive the candidate-specific manifests only after
   those carriers exist, then run D0–D7 without replacing failures or changing
   the frozen policy.
7. **Automated reproduction and selection:** run the generic runner and semantic
   bindings, reproduce complete native/Linux facts for every candidate that
   passed gates 1 through 7, then compute the gate-8 passing finalists and
   preference.
8. **Technical evidence:** freeze bundles/held-outs, run qualifying technical
   rounds using the retry rules, and seal reviewed summaries.
9. **Learner evidence:** run/revise the label-suppressed micro-slice with fresh evidence after
    the last material representation change.
10. **Freeze:** regenerate and review the compact report, add the one decision
    note, run `scripts/check release`, and update status truthfully.

The coding agent may parallelize independent language implementations,
container acquisition, template work, and non-result-aware vectors. It may
rename private modules, factor helpers, optimize after equivalence tests, and
choose the simplest bounded algorithm satisfying an exact behavior. It may not
observe candidate damage/human answers before freezing a policy that selects
among them.

### 20.2 Freeze points

These transitions require an explicit reviewed diff and fresh generation:

- candidate set/tuple and comparison policy before candidate results;
- damage policy/seeds before candidate D3 results;
- common grammar before cross-candidate size comparison;
- preferred candidate/carrier before technical exposure;
- technical checkpoint before held-outs;
- learner runner/slice/forms before learner exposure; and
- report/decision/status only after raw evidence is sealed.

“Freeze” means immutable for that evidence round, not a bureaucracy or promise
that later milestones can never reopen it.

### 20.3 Change and rerun matrix

| Change | Earliest required rerun |
|---|---|
| Existing M0 anthology/reference/identity changed | M0 and downstream, per roadmap |
| Add exact expected M2 implementation receipt | M2 source-lock/check and every consumer; M0 remains complete |
| Content-v0 bytes/serializer semantics changed | repair M1 owner, rerun M1 content plus all M2 slice/candidates |
| Chess/source/game-set bytes changed | repair/reopen M1, regenerate entire M2 semantic path |
| Shell/recipe/common block/code/check/map/damage changed | rerun M2 automated comparison and fresh technical gate |
| Only candidate implementation optimized with bytes/behavior/work count unchanged | focused/full/Linux equivalence; no new human by itself |
| Learner representation/lesson order/cues materially changed | fresh learner micro-pilot; transport only if bytes/envelope change |
| Provisional allowance raised | rerun every finalist capacity/damage/geometry and technical gate if carrier-visible |
| Docker/toolchain provenance changed only | host/Linux/reproducibility and dependency-surface review |
| Private template wording changes before exposure only | refreeze bundle; no code rerun unless information condition changes |
| M3 exceeds a provisional hard maximum | reopen M2; never silently widen a parser/profile limit |

### 20.4 Failure diagnosis

On a failing human round, distinguish before changing the artifact:

- bootstrap missing/ambiguous relation;
- code/check procedure too costly or incomplete;
- physical-map or inventory misunderstanding;
- generic representation/chess meaning gap;
- participant prior/mismatch or cross-unit contamination;
- facilitation/bundle/environment defect; or
- time/resource ceiling.

The diagnosis determines the smallest owner and next fresh evidence. It does
not override the observed failure. If a qualifying unit cannot be recruited,
software work may stop at validation pending without weakening recipient
eligibility.

## 21. Required verification and adversarial matrix

### 21.1 Entry, shell, and bootstrap

| Case | Required result |
|---|---|
| `N=0`, count mismatch, non-binary symbol, non-square, or `N>2048²` | preflight rejection before matrix allocation |
| exact smallest admitted square and boundary-plus-one side | exact acceptance/rejection per generated limit |
| all-zero/all-one matrix | no accepted shell/profile |
| all sixteen clean transforms/polarities | one canonical extraction and identical semantic bytes |
| column-major temptation, serpentine, cyclic shift, crop, insert, delete | no unsupported alternate search/acceptance |
| first discriminator matches wrong transform | later independent discriminator rejects it |
| marker-like interior decoy | cannot accept without complete route/check chain |
| any one complete sector erased | another full route recovers every declared M2 section exactly |
| two valid routes normalize identically | canonical deduplication |
| two coherently valid routes disagree | exact `ambiguous` artifact result |
| wrong grouping/bit significance/traversal/polarity | held-out/bootstrap chain rejection |
| graph cycle, missing definition, use-before-teach, unreachable endpoint | linter rejection |
| each defining-node ablation | fail at declared node/dependent, never decoder default |
| recipe max nodes/steps/table/array/output and each max+1 | boundary success and stable limit rejection |
| malformed recipe opcode/type/index/shift/divisor/write/trailing byte | exact fail, no partial emit |
| both recipe interpreters | byte/result/failure/work/scratch agreement |

### 21.2 Common grammar, copies, and inventory

| Case | Required result |
|---|---|
| common block min/max valid payload | exact round trip and zero-pad coverage |
| nonzero reserved field or payload/transport pad | rejection after bounded decode |
| fragment count/index/length inconsistency | rejection before allocation/assembly |
| missing middle/final fragment | incomplete unless independent complete copy supplies it |
| identical duplicate | deduplicate without extra semantic byte |
| same identity with different locally valid bytes | exact `ambiguous` fragment result |
| fragments in forward/reverse/frozen arbitrary order | identical exact section bytes |
| truncated/extended/trailing section | atomic rejection |
| dependency duplicate/order/dangle/cycle | stable rejection/no tier inflation |
| one inventory copy lost | remaining complete inventory owns completeness |
| every inventory copy lost | no completeness/tier claim |
| valid inventories/copies conflict | exact `ambiguous`, never majority |
| whole game ordinal absent | `m2_all` is incomplete and the missing ordinal is explicit; M2 makes no RT4 claim |
| valid chess bytes behind failed check | no semantic parse or repair |
| configured section-attempt ceiling and ceiling+1 | last allowed; next resource-limit failure |

### 21.3 Hamming baseline

| Case | Required result |
|---|---|
| four literal encode KATs | exact nine-byte agreement in both languages |
| every one of 72 single changed bits | exact original eight bytes, recovered |
| every one of 72 single erasures | exact original bytes under bounded enumeration |
| `(e,s)` on `2e+s<=3` | unique recovery when the code relation supplies it |
| corresponding one-beyond frozen observations | no wrong common-block/section accept; an independent valid copy may recover, otherwise exact `corrupt` |
| more than three erasures | bounded failure, no fill explosion |
| exhaustive radius/distance invariant | no two distinct codewords can survive inside the declared radius; a multiple-candidate result is an internal invariant failure, never arrival-order choice |
| all 24 blocks valid and pad zero | one candidate common block |
| one block corrupt, another complete copy valid | copy recovery per state |
| two complete checked copies disagree | exact `ambiguous` fragment/section result |
| parity-valid beyond-radius block with bad local CRC | rejected before fragment exposure |
| copy counts two and three | exact capacity/damage rows; smallest passing selected |

### 21.4 Reed–Solomon

| Case | Required result |
|---|---|
| generator coefficients and three parity KATs | exact cross-language bytes |
| every single symbol position, several magnitudes | correction and local-check success |
| errors confined to data, local-check bytes, and parity | exact behavior/no special omission |
| exact frozen 32-error / 33-error vectors | 32-error recovery; 33-error protected-unit failure and no wrong accept |
| exact frozen 64-erasure / 65-erasure vectors | 64-erasure recovery; 65-erasure predecode failure |
| `(1,62)`, `(16,32)`, `(31,2)` | exact equality-bound recovery |
| `(1,63)`, `(16,33)`, `(32,1)` | protected-unit failure under the observed-radius rule; no wrong accept |
| any bit erased in one symbol | complete byte erasure; surviving bits ignored |
| duplicate/out-of-range erasure | predecode rejection |
| locator degree/root mismatch or nonzero post-syndrome | rejection/no partial bytes |
| modulus `0x11b`, roots from one, reversed parity/bytes/bits | KAT/held-out rejection |
| selected beyond-radius plausible codeword | protected-unit decoder rejects outside observed radius; frozen corpus has no wrong canonical accept |
| decoder operation/table/max polynomial and max+1 | deterministic bound |

### 21.5 CRC and section integrity

| Case | Required result |
|---|---|
| every literal CRC KAT including empty/high-bit/range | exact semantic integer and big-endian storage |
| wrong init/reflection/xor/polynomial/storage order | KAT/project-vector rejection |
| local/section domain swapped | rejection |
| identity/type/version/dependency/length/payload bit changed | section check or structural rejection |
| fragment placement/copy ID changed without semantic change | same semantic section identity, valid local physical header only |
| min/max allowed section lengths | exact bounded check |
| truncated/extended preimage | mismatch/rejection |
| CRC-32C and CRC-64 comparison row | actual lengths/cost/properties, no width probability |
| minimum distance not computed | report explicitly says not established |

### 21.6 Mapping, capacity, and damage

| Case | Required result |
|---|---|
| every interior slot | mapping and inverse round trip; one owner |
| non-coprime/out-of-domain formula parameter | construction rejection |
| shell/header/data/check/parity/pad/real/capacity-probe/reserve-probe/load-probe | all present in ownership/capacity totals |
| ledger sum | exactly `S*S`; independent ledger identical |
| edge, corner, row-wrap, tile/lane/copy boundary | included in placement audit |
| D0 all sixteen views | unique canonical result |
| D1 every sector | another complete route and every declared M2 section recover exactly |
| D2 every proved residue/all explicit placements | `m2_required_closure`/explicit remaining states/no wrong accept, or narrowed sampled claim |
| D2 one cell larger | D7 correct-or-fail, never wrong accept |
| D3 all 128 frozen seeds | `m2_required_closure` and explicit remaining states; no wrong accept or seed replacement |
| D3 `K+1` and boundary concentrations | unclaimed correct-or-fail |
| D4 every unit and one beyond promise | exact surviving/incomplete states |
| D5 multiple arbitrary orders | canonical order restored |
| D6 every proof partition combination | `m2_required_closure`/no evaluator hint |
| cross-profile splice/wrong map/check/code | explicit failure/ambiguity |
| simultaneous erased/changed bits in a byte | erasure takes the defined symbol path |
| capacity/reserve/load-probe and pad density metrics | no prohibited easy tile/pattern; exact deterministic regeneration |
| union-safe provisional envelope for each finalist | fit at or below ceiling or hard elimination |

### 21.7 Content and runner

| Case | Required result |
|---|---|
| parse/encode every canonical content fixture | exact projection and bytes in both languages |
| invalid projection order/reference/graph/budget/size | reject before partial output |
| real M2 stream packed/recovered/parsed | exact original bytes and root |
| 5-by-7 and 7-by-5 non-chess canaries | complete presentation/interaction without chess code |
| arbitrary opaque semantic bindings | unchanged/uninterpreted by runner |
| select/commit/reset/feedback/exhaustion/terminal paths | content-v0 exact transitions/event logs |
| runner given unverified/incomplete transport bytes | refuses input |
| chess dependency/static term audit | no hidden rule/constants/answers |
| ordinary versus label-suppressed full semantic paths | same available actions, semantic commits, evaluator predicates, and content events; no required natural-language/Unicode/font dependency |
| two chess cores on slice expectations | exact agreement before packing |
| all packed game sections | M1 identities/scores and ordinal `0..63` unchanged |

### 21.8 Reproducibility, repository, and Linux

| Case | Required result |
|---|---|
| Python versus Rust pack/recover | byte/state/ledger agreement |
| repeated run, locale/timezone/hash-seed/CPU variation | identical tracked/generated bytes |
| clean checkout without generated dirs | full regeneration succeeds offline |
| source lock with original five plus exact M2 receipts | accepted; anthology/M0 receipts unchanged |
| unknown role/ID duplicate/malformed digest/extra key | fail closed |
| `.dockerignore` context | only declared files admitted |
| verifier image missing | `linux` fails with acquisition command; no auto-download |
| Linux run network enabled/host cache mounted/inner command changed | contract test failure |
| host `full` pass but Linux or byte equality fail | `release` fails; no architecture freeze |
| future `release/`, `web/`, workflow/schema surface appears | repository guard still rejects |
| dirty unrelated worktree | checks inspect intended files without overwriting them |
| full carrier placed in conformance | registry/repository policy rejects oversized wrong surface |

### 21.9 Human protocol and evidence

| Case | Required result |
|---|---|
| individual across multiple sessions | one round; retained notes; union active time |
| team members work partly in parallel | one fixed unit; union time plus summed person-time; team-bound claim |
| member joins after exposure | diagnostic only |
| no-show before exposure | remains fresh/reschedulable |
| withdrawal/illness after exposure | stop immediately; retain `withdrawn` only with continuing summary permission, otherwise only the agreed nonidentifying count or nothing; new unit allowed under retry rule |
| exact-profile prior | artifact evidence still required; another fresh unit closes gate |
| facilitator suggests grouping/code/location | critical hint; continuation diagnostic |
| decoder changed after held-out release | checkpoint owns result; revision diagnostic |
| two units communicate | merged/cross-contaminated information condition, not independent evidence |
| unit finds public repository | exposure logged; continuation diagnostic |
| submitted code attempts network/destructive path | isolated evaluator prevents mutation; round safely diagnosed |
| candidate/bundle bytes change mid-round | old round closed; fresh unit for material revision |
| first valid unit cannot finish | one diagnosed unchanged retry maximum; then redesign/open gate |
| learner requires verbal chess rule | representation failure; acquisition non-gating |
| learner refuses recording | no penalty; recording is optional/default off |
| consent withdrawal within stated window | opaque mapping locates/deletes covered raw data |
| private raw data absent from checkout | normal checks still validate templates/redacted report only |
| unsuccessful exposed rounds | remain in summary while permission continues; never silently dropped or converted to a pass |

## 22. M2 exit traceability

| Roadmap gate/deliverable | M2 closing evidence |
|---|---|
| `spec/bootstrap-v0.md` and acyclic route | promoted spec, graph/linter, dual interpreters, ablation suite |
| simple and stronger candidates | exact Hamming/copy and RS tuples, dual implementations, common harness |
| check comparison | exact CRC tuples, actual-length property/cost/negative report |
| damage policy D0–D7 | promoted TOML, dual generators, candidate manifest hashes, zero wrong accepts |
| exact cell-to-observation/mapping | formulas/inverses, total ownership and independent proof matrix |
| full realistic provisional carrier | carrier hash, capacity/density/capacity-reserve-load-probe/pad ledger, preferred profile |
| real Core 0/content/chess/lesson/game slice | slice/content/game identities and raw-to-parser cross-check |
| clean Linux path | acquired-image identity, network-off `full`, host/Linux byte equality |
| G5 bootstrap complete | knowledge-use/ablation/recipe pass with shell headroom |
| G6 independent reconstruction | qualifying fresh-unit checkpointed technical round |
| G7 representation feasibility | qualifying fresh individual learner round on latest material |
| G8 complexity-first finalists | complete deterministic metric/elimination/retention decision |
| at most two finalists and one preference | tracked exact IDs/tuples and M4 rerun obligation |
| provisional maxima for M3 | union-safe `profile-limits-v0.toml`, capacity report |
| one short decision note | concise `docs/decisions.md` entry bound to report |
| durable M4 pilot-change comparison | complete tracked M2 pilot envelope |
| architecture freeze cadence | `scripts/check release` passes and report is non-stale |

The G6 pilot is not a substitute for automated candidate correctness, and G5
automated closure is not a substitute for a fresh recipient. The G7 learner
uses exact recovered bytes; a developer-side substitute cannot bridge the
claims.

## 23. Design stress-review record

### 23.1 First adversarial loop — channel and transport architecture

The first loop tested the draft against fixed-length entry, correlated damage,
candidate fairness, and repository ownership.

| Stress | Weakness found | Strengthening applied |
|---|---|---|
| Raw data framed like a serial link | delimiter/sync schemes would solve excluded insert/delete faults and introduce stuffing | restricted machine entry to integer square plus exactly sixteen D4/polarity hypotheses |
| Pure bit triplication is a tempting extra “simplest” family | it duplicates the direct-replication question without a distinct required initial claim | bounded the first comparison to checked EH72 copies and RS; repetition may return only through the frozen revision rule after failure |
| Bare SECDED at D3 density | many multi-fault blocks expected at ceiling | predeclared two/three complete copies and exact mixed erasure enumeration |
| RS named without full convention | field/root/coefficient/parity/decoder ambiguity | froze full polynomial profile, generator coefficients, parity KATs, and failure checklist |
| Barcode finder copied wholesale | optical assumptions and known standard decoder would become hidden prior | retained only asymmetric/repeated motifs; every meaning remains shell-taught |
| One central directory or shared shell table | single loss destroys completeness/bootstrap | required four complete routes and replicated protected inventories |
| Candidate gets custom block/semantic data | comparison could reward friendly framing | fixed one 191-byte common block and one semantic/capacity/damage harness |
| Simple interleave called “independent” | D2 cluster may overload one codeword/copy | required total ownership, every placement or residue proof, and independent oracle |
| Provisional side mistaken for final | M2 representative content could freeze a false minimum | named provisional envelope, omitted final dimensions from limits/profile, required M4 rerun |
| M1 guards reject M2's real consumers | Docker, decision note, source receipts, commands cannot land | specified narrow admission migrations and unambiguous `linux`/`release` ownership |

After these changes the architecture has no obvious unbounded search,
single-directory dependency, result-aware candidate addition, or unsupported
channel claim.

### 23.2 Second adversarial loop — human evidence and downstream durability

The second loop tested teams, repeated sessions/pools, normal failure, leakage,
learner redesign, private data, and M4 reuse.

| Stress | Weakness found | Strengthening applied |
|---|---|---|
| Two-to-four-person elite team | singular “pilot” and 16 hours hid parallel contribution | defined fixed recipient unit, union active time, person-time, and team-bound wording |
| First capable unit does not solve unchanged carrier | first-attempt fragility versus recruiting until pass | allowed one pre-diagnosed unchanged retry; two unresolved rounds force redesign/open gate |
| Decoder patched after seeing expected behavior | held-out evidence becomes answer-aware | immutable clean source/notes/output checkpoint before held-out release |
| Facilitator casually says “try bytes” | useful diagnosis could be misreported as independent pass | tiny exact help taxonomy; critical hint ends gating round |
| Team/member/cross-pool communication changes | unclear independence | freshness per member, fixed membership, merge/contamination rule, and permission-aware exposed-round history |
| Learner reused after representation rewrite | prior material teaches the new answer | reuse only for diagnosis; latest material needs a fresh individual to close G7 |
| Natural-language labels quietly teach the semantics | a learner could pass while the canonical language-independence contract fails | made the result-bearing learner mode suppress/opaque-replace `TEXT` labels and required identical semantic paths/predicates |
| Ability questionnaire names likely solution domains | the prompt itself cues matrices/codes/chess or makes the public project searchable | select elite units from neutral portfolio/open-ended history and collect exact-profile history only after outputs are sealed |
| Future held-outs are shared in one parent folder | sync/search can expose later channels or expected structure before checkpoint | release only each current question/files subset from owner-side storage and hash every phase |
| Later channel adapter changes decoder logic | damage results become answer-aware or exceed the one total clock | pre-freeze neutral schemas, allow only a thin checkpointed adapter, and keep both checkpoints plus held-outs inside 16 hours/seven days |
| Rubric weakened after a learner failure | redesign could manufacture a pass | freeze predicates/thresholds before exposure; revisions require a new protocol identity and fresh learner |
| Friendly participant data committed publicly | unnecessary identity/recording risk and hard deletion | blank tracked templates, ignored private instances, opaque IDs, recording default off, simple retention note |
| Participant source contains unsafe command | evidence run could mutate owner workspace | explicit untrusted offline disposable evaluator with resource/output bounds |
| Raw pilot files later deleted | M4 cannot tell whether carrier left pilot envelope | tracked report binds every recipient-visible envelope fact and opaque result summary |
| Human recruitment unavailable | temptation to invent or weaken a gate | explicit validation-pending state with software evidence preserved |

After this loop the protocol supports multiple sessions, fixed teams, different
fresh pools, diagnostic reuse, and material revisions without either requiring
first-attempt luck or allowing silent cherry-picking. No obvious need remains
for a database, NDA, committee, statistical framework, or elaborate study
platform.

## 24. Accepted limitations and execution checklist

### 24.1 Known limitations accepted by M2

- The raw observation is exact-length and phase-aligned; insertions, deletions,
  cyclic shifts, crops, and physical scanning are outside v0.
- The intentional/important/potentially-profound/benign premise is given to
  recipients; it is not inferred from checks or authenticated by the carrier.
- D1 begins after matrix adjacency is available, and D4–D6 use typed later
  channels; they are not raw-bit resynchronization claims.
- CRC and ECC cannot distinguish an accidentally damaged original from a fully
  reauthored self-consistent alternative in all possible worlds.
- D3 is finite deterministic empirical evidence; independent-fault calculations
  are design intuition only.
- The selected mapping need only prove the frozen 2D damage policy, not every
  conceivable scratch/material accident.
- One technical recipient unit and a tiny learner micro-pilot demonstrate
  feasibility under exact conditions, not frequency, population efficacy, or
  universal comprehension.
- A team result is not an individual result. M4/M5 must preserve the team-size
  envelope or run fresh evidence under the changed condition.
- The M2 runner and slice are intentionally incomplete; M3 owns complete
  curriculum/transducer integration.
- Provisional semantic maxima may force M2 to reopen during M3; they do not
  justify silent truncation or weaker content.
- The M2 carrier is not final and no minimum-size claim is made.
- The Docker verifier needs one explicit network-enabled acquisition build; the
  evidence-bearing verification itself is cache-hidden and network-disabled.
- Human participation evidence ultimately depends on honest recorded conduct;
  this pet project does not build surveillance or remote proctoring.
- Public anthology redistribution remains blocked on its independent rights
  basis and is not cured by transport work.

### 24.2 Pre-implementation review

- [ ] roadmap revision and human-unit/retry/source-owner clarifications agree
  with this spec;
- [ ] M0/M1 status and exact completed evidence remain unchanged;
- [ ] no final profile, dimension, package, viewer, or release surface is
  introduced;
- [ ] external implementation-profile editions are current and exact receipts
  are planned only for real consumers;
- [ ] Hamming, RS, CRC tuples/KATs have two independent derivations;
- [ ] candidate/mapping/damage policies freeze before outcomes;
- [ ] blank pilot templates are simple and private-instance separation is
  clear; and
- [ ] no unresolved normative ambiguity remains in an existing smaller owner.

### 24.3 Automated freeze

- [ ] four complete shell routes, graph, knowledge-use linter, ablations, and
  dual recipe interpreters pass;
- [ ] common block/section/inventory grammar and stable states reject every
  malformed/boundary case fail-closed;
- [ ] both languages independently agree on Hamming, RS, CRC, pack, map,
  damage, recovery, and content bytes;
- [ ] both code families use the same real semantic envelope/harness;
- [ ] all D0–D7 cases and zero-wrong-accept corpus pass without seed changes;
- [ ] capacity/ownership/work/scratch ledgers reconcile exactly and every
  retained finalist fits union-safe limits at or below 512 KiB;
- [ ] real content serializer, runner, non-chess canaries, label-suppressed
  semantic-path equivalence, and M1 semantic bindings pass;
- [ ] at most two lowest-class finalists and one deterministic preference are
  recorded;
- [ ] native and clean-Linux `full` produce identical candidate/report facts;
  and
- [ ] `scripts/check release` passes without a premature release package.

### 24.4 Human and completion freeze

- [ ] technical prompt, bundle, held-outs, expected data, participant note, and
  round envelope were frozen before exposure;
- [ ] every technical member was eligible/fresh and all sessions/help/prior/
  exposure were recorded;
- [ ] the clean decoder/derivation was hashed before held-outs;
- [ ] one qualifying latest-candidate technical round passed every task with
  zero critical hints/unresolved conventions;
- [ ] learner runner/slice/forms were frozen and one fresh individual passed
  the latest material without verbal chess teaching;
- [ ] unsuccessful/diagnostic/withdrawn/invalid exposed rounds remain in the
  permitted summarized history, with only an agreed nonidentifying count or no
  round-linked data where withdrawal required deletion;
- [ ] the tracked report binds exact finalists, evidence, pilot envelope, and
  limitations without private identifiers;
- [ ] one concise decision note exists and states the M4 rerun obligation;
- [ ] `scripts/check release` and report-staleness checks pass once more; and
- [ ] only then is roadmap M2 marked complete with date, preferred/finalist IDs,
  and report hash.
