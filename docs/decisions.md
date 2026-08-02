# Decision Ledger

This ledger records only the consequential decisions named by [roadmap Section 3.5](roadmap.md#35-lean-decisions-and-evidence). It is not a task log, approval matrix, tool-observation log, or recurring sign-off process.

## When an entry is required

An entry is required only for:

- selecting or incompatibly changing the transport/bootstrap profile;
- changing the hard artifact ceiling or mandatory product scope;
- changing the source path/profile or chess scope;
- changing a result-bearing damage or human threshold after exposure; or
- replacing `docs/64_games.md`.

Tool observations and the clean-Linux mechanism belong in `inputs/source-lock.toml`. Measurements and generated acceptance evidence belong to their owning specs, reports, or ignored artifacts; they do not create ceremonial decision entries.

## Entry format

Each decision is one level-two heading containing an ISO 8601 date, an em dash, and a short title. Its body contains exactly these five bullets:

- **Trigger:** the matching consequential category above.
- **Decision:** the selected or changed value and its effective scope.
- **Reason and rejected alternatives:** the evidence-based reason and the bounded alternatives not chosen.
- **Affected owners and evidence:** the exact specs, tests, reports, or pilot that must change or repeat.
- **Revisit condition:** the explicit evidence or incompatibility that can reopen the decision.

One dated entry is sufficient. No approval matrix, committee, meeting, or duplicate status field is added.

## Current entries

None. Establishing the M0 source, reference, toolchain, and clean-Linux lock recorded observations and frozen identities; it did not trigger a consequential decision listed above.
