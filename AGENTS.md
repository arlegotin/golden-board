# Golden Board maintenance

Read [README](README.md), [the guide](docs/guide/README.md),
[status](docs/status.md), the [maintenance contract](docs/roadmap.md) and relevant
[format](spec/self-contained-format.md)/[chess](spec/chess.md) specifications.

Keep the branch ready to merge into main as one coherent, current project.
For an authorized message change, update the normal builder/decoder defaults,
canonical artifacts, manifests, generated images, tests and documentation together.
Do not leave approved changes only in an optional candidate mode or preview unless
the user explicitly asks for one. Remove superseded paths and temporary review
material introduced by the work instead of retaining parallel project versions.

Describe current behavior directly in guides, specifications and status reports.
Do not add development diaries, before/after implementation stories or comparisons
with arbitrary previous project versions. Keep documentation edits proportional
to the task: preserve the existing guide's structure and useful background;
this rule is not a reason to rewrite, move or reorganize its chapters.

Use Git as the default record of project evolution and as recovery for material
already committed. Do not keep obsolete copies or backup directories just for
history. Add historical explanation only when essential to understanding a current
constraint or the limits of evidence; keep it concise in docs/history/ and link
to it rather than repeating it in current-use documentation. Historical names
alone do not make active code, pinned inputs or regression fixtures obsolete:
check their current consumers and preserve required hash-bound material.

Preserve the canonical files in artifacts/ exactly unless the user explicitly
authorizes a message change. PNG, TXT and BIN represent one 2048 × 2048 message
with 146 teaching obligations, 64 complete games,
6890 plies and 6954 anthology states. Verify with `./gb verify`.

Keep one Python construction pipeline and an inert headless JavaScript mechanism.
No chess engine, move-ranking oracle, hidden rules or damaged-input recovery.
Source moves, editorial metadata, exact predicates and strategic heuristics remain
separate. Preserve hash-bound qualified inputs and frozen format-source bytes.

Use focused regression checks for changed behavior and deterministic reproduction
at relevant boundaries. Preserve existing unrelated work and outputs. Keep private
communications, personal information and operational records out of tracked files
and distribution archives. Documentation describes technical behavior and findings.

Do not push, publish, rewrite existing history, remove unique material or change
the canonical message without explicit authorization. Preserve unique uncommitted
material before cleanup. Keep status concise and factual.
