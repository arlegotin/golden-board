# M2 participant revision implementation plan

**Scheduling update, 2026-09-22:** Use
[`spec/m2-participant-trials-v1.md`](../../../spec/m2-participant-trials-v1.md)
and [the current workflow plan](2026-09-22-m2-provisional-trials.md).
Focused-checked frozen participant trials now precede exhaustive verification
by default. Earlier release-before-exposure steps below are execution history,
not a requirement to spend another full run before each teaching experiment.

> Use superpowers:subagent-driven-development for independent tasks and review.
> Continue through implementation and verification; the owner's “proceed” is
> authorization, not a request for another approval cycle.

Goal: incorporate the technical and learner findings into the actual M2
carrier, with a teachable bounded slice and honest fresh evidence.

Architecture: preserve the exposed candidate and participant submissions;
author reviewed content using the existing public content/chess APIs; compile
it independently in Python and Rust; derive carrier owners from the resulting
bytes; reproduce and release before another qualifying human trial.

Tech: current locked offline Python/Rust toolchains and generic local browser
viewer. No dependencies, external services or participant administration.

Spec: docs/roadmap.md, docs/m2-spec.md, spec/content-v0.md,
spec/chess-v0.md and the smallest slice/transport/lifecycle owners. The
worktree's artifacts/work/participant-revision reports retain the evidence
audit and exact implementation rulings.

## Constraints

- This remains M2: a minimal representation slice, not the full M3 curriculum.
- Preserve deterministic bytes, strict bounds, independent generation and
  fail-closed gates; never change a threshold to obtain a pass.
- Original quiz packets/results and canonical Candidate-ready evidence remain
  historical inputs. A revised artifact receives new identities and evidence.
- Participant effort, trials and corrections are acceptable. Assistance must
  remain distinguishable from artifact-taught discovery.
- No names, dates, agreements, interviews, publication or outreach required.
- Viewer rendering and controls remain generic, with no chess truth or final
  answer table. Labels remain suppressed.

## Work and verification

- [x] Audit every participant stage into one evidence-to-change matrix. Check
  actual carried teaching where help was supplied; help alone proves neither
  successful self-description nor an absent artifact convention.
- [x] Author the revised slice in tools/m2/learner_content.py: non-chess
  mechanics; addresses before state; required movement/queen/king contrasts;
  exact permission/target/expiry examples; comparative history query; corrected
  self-check geometry; novel final record case with two legal alternatives.
  Use canonical game-set input, never ignored participant files. Prove chess
  truth and displayed geometry with python/tests/test_m2_learner_content.py.
- [x] Add generic fit/zoom to tools/m2/learner_web/{index.html,ui.js,viewer.js}.
  Verify no action/content changes at different scales, rectangular canaries,
  example playback, selection/reset/commit/export and full Python parity.
- [x] Resolve the minimal slice owner and independent compiler integration
  using the integration audit. Preserve the old contract for historical
  packages. Freeze the new declaration only after content and capacity checks.
- [x] Correct the technical fixtures and implement carried-teaching repairs
  demonstrated by the all-participant audit. Add targeted regressions.
- [x] Perform exact archive-first source/candidate reopening. Update roadmap
  status and dependent owners consistently; no stale Candidate-ready claim.
  The exact 3,296-file historical tuple is installed in the primary archive;
  revision11 is In progress and the previous live Gate8/report are absent.
- [x] Measure actual slice, route, reserve and load capacity. Independently
  regenerate Python/Rust semantic/transport facts before freezing new limits.
- [x] Bind current source integration to the v2 promotion/report/execution
  owners in docs/m2-spec.md Section 19.2 and docs/m2-plan.md, preserving the
  historical text. Development roadmap and decisions are exact archive-pending
  bytes; the admitted archive now preserves the prior primary tuple. Decouple temporary transition
  tests from live document revisions: twelve focused tests pass.
- [x] Close the bounded all-31 source/kit re-audit against
  studies/m2/participant-learnings-v1.md. Revalidate the actual required stream
  and twelve final assessment questions with public chess; no missing material
  teaching repair was found in that source/kit review. Preserve the original
  assistance distinctions and pending fresh human validation.
- [x] Repair the learner session command ceiling from the validated ContentRoot
  budget: an actual 8,320-command/4,160-commit exhausted attempt accepts,
  8,321 rejects, and ROOT8 rejects 17 commands despite inflated owner metadata.
  Fifteen session/assessment/runner tests pass; recipient bytes and questions
  are unchanged.
- [x] Independently compare all 36 technical/learner raw bundle files and the
  six foreign-profile D7 cases' twelve result/resource documents. Exact
  development comparison identities are recorded in the finding ledger; these
  comparisons do not replace a complete frozen four-producer run.
- [x] Implement clean-Linux v2 shell adapters and components/full/release
  dispatch. Twenty focused and inherited orchestration tests pass, including
  short-circuit failures, source drift and transient-output tampering. External
  jobs are explicit test fixtures; no Docker or full producer run is implied.
- [ ] Run scripts/check fast and relevant focused checks, then fresh native
  and pinned offline Linux producers, Gate-8 assembly and scripts/check release.
- [ ] Review the final change and package the exact revised carrier, learner
  viewer, answer replay and simple next human instructions. State the remaining
  human bridge requirement; do not relabel prior prototype results as a pass.

Ruling: use /private/tmp/golden-board-m2-participant-revision on the local
codex/m2-participant-revision branch. The primary checkout and all completed
participant work remain intact while a replacement is made concrete. Local
worktree creation is covered by the user's authorized implementation scope.

Ruling: the next final questions must be novel relative to the exposed trial;
the old audit's b1-c3 alternative is a regression example, not the next exam.
