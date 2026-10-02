# M2 provisional participant trials implementation plan

**Goal:** Make focused validation and participant feedback the default iteration
loop, and defer exhaustive verification until a stable provisional success.

**Architecture:** Use the existing source builders, bounded preflight replay and
participant packagers. Keep the current final gates, source bindings and
archive-first lifecycle; change exposure order and provisional-result rules.
No new participant administration or study platform.

**Spec:** [M2 participant trials](../../../spec/m2-participant-trials-v1.md).
The owner approved this bounded design in the conversation before implementation.

**Tech stack:** Existing Markdown/TOML owners, Python tools, Python/Rust focused
checks; no dependencies. Work directly on the owner's clean primary checkout
after preserving the complete previous validated tuple.

## Tasks and checks

- [x] Verify and archive the 997-file prior source/candidate/Gate8/report tuple;
  restore the existing owned In-progress roadmap and remove only archived
  canonical outputs. Preserve all participant data and incidental metadata.
- [x] Add the trial owner and make AGENTS, M2 spec/plan, promotion policy,
  Gate8 policy/execution and handoff templates consistently use it.
- [x] Remove the preview packager's blanket prohibition while keeping its
  incomplete-evidence warning. Require focused checks and pre-exposure freezing;
  packaging alone grants no provisional or final success.
- [x] Ensure the bounded Python/Rust replay includes every actual participant
  observation, especially D7/11, without expanding to the full corpus.
- [x] Rebind the exact Gate8 policy identity. Run targeted policy, preview,
  bundle, scheduling and replay-selection tests; run `scripts/check fast`
  (which includes the repository checks). Check diffs, links and unchanged final
  gates.
- [x] Record results here. Do not run bootstrap/full/Linux/release for this
  workflow edit. The substantive teaching repair is the next separate task.

## Review focus

- Provisional exposure must require actual source-built, independently checked
  observations; neither an old bundle nor a preview manifest alone suffices.
- A provisional success must not skip any final gate or silently populate a
  pending-only report schema.
- Checkpoint edits, help, changed expected answers and semantic source drift
  must keep affected results nonqualifying.
- Old participants/attempts and the exhausted unchanged retry stay historical.
- Archived green results must not appear to validate the edited source.

## Verification record

- The new replay regression first failed because the handed-out D7/11 case was
  absent. It passes after adding that case; the bounded selection now has 39
  cases. The full corpus and its acceptance rules are unchanged.
- All 34 targeted tests passed: replay CLI, Gate8 policy, technical preview,
  participant bundle and workflow execution (`0.822s`). These exercise selection,
  packaging and orchestration; they do not claim a fresh carrier or damage pass.
- Verified all 997 archived preimages against their lengths and SHA-256 values.
  The existing coordinator admits the exact pending roadmap, and the new trial
  owner is included in the source projection.
- Compared final gate, bounds, candidate, producer, cross-language, Linux,
  selection and metric contracts against the archived policy: unchanged.
- Verified all 11,974 round-10 submitted files against their recorded inventory:
  unchanged. Other participant folders were not modified.
- The first fast-check attempt found the archived report deletion still present
  in the Git index. Staging only that deletion resolved its two repository
  scan failures; no test was weakened. The replacement `scripts/check fast`
  completed with exit 0: 458 Python tests run (3 existing opt-in skips), and
  148 Rust tests passed (1 existing opt-in stress test ignored). The Python transport
  subset ran 324 tests in 802.321 seconds. Its log is
  `/private/tmp/gb-provisional-flow-fast.log`.
- All 38 local Markdown links across seven edited documents resolve; both
  working-tree/index whitespace checks pass. No
  bootstrap, complete damage, full, clean-Linux or release job was launched.

## Recovery-teaching implementation and next handoff

The owner then approved proceeding with the material repair. Preserve the
successful clean/VM/content teaching and replace the active fact10 primary
concatenation exercise with the group decision specified in
`spec/recipe-teaching-v2.md` and `spec/route-definitions-v2.md`.

- [x] Review revised trials08/10 against all earlier findings; append their
  exact success and saved-method limits to the participant-learning ledger.
- [x] Derive candidate equality from complete checked blocks, combine every
  lane and raw repetition, reject conflicts, and enforce physical identity.
  Add an executable trace of unknown symbols surviving failed individual EH.
- [x] Implement independent Python/Rust construction and observed validation;
  charge all ten embedded executions before numeric semantic validation.
  Preserve the32 framed examples and existing analytic limits.
- [ ] Run the affected regressions and `scripts/check fast`, then independently
  generate/compare the actual carrier and preflight evidence. Run the39-case
  Python/Rust/source-oracle selection, including all four participant held-outs.
- [ ] Freeze source, production technical files, expected results and unchanged
  acceptance/assistance conditions under the next ignored quiz folder. Verify
  every preimage before exposure and retain command logs there.
- [ ] Collect the fresh provisional technical result, then use its exact
  recovered required stream for the learner. Repair directly if unresolved;
  exhaustive verification follows only stable required provisional success.

The new package remains29 recipes/14 tables/47 records; its compact package
is18661 bytes and each route prefix25809 bytes. The old2040/112 geometry no
longer fits the required headroom;2048/112 does. Actual complete carrier and
independent observation checks still determine trial readiness. The previous
997-file archived tuple and participant originals remain historical evidence.
Results and handoff identities will be stored with the frozen trial so source
need not change merely to append a test log. No new human result is assumed.
