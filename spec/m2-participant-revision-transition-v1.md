# M2 participant revision: archive-first local transition v1

This owner defines a local historical transition, not a candidate promotion or
gate result. The command is prepared during development; it MUST NOT run against
the primary repository until the owner requests the transition. It neither
publishes material nor changes participant instructions. Existing verifier-only
and test-only reopen commands retain their historical meanings.

## Interface and scope

`tools/m2/reopen_participant_revision.py prepare --historical-root ABS
--output-dir ABS` reads a normal source repository and creates a new private
directory. It does not write the source repository. Its output is an archive
package and a SHA-256 of `archive-manifest.json`.

`tools/m2/reopen_participant_revision.py apply --repository-root ABS
--prepared ABS --manifest-sha256 HEX` consumes that exact package. The digest is
an integrity binding to the prepared bytes, not an approval or evidence phase.
The command may run from a development checkout against the still-historical
repository. Source replacement follows reopening; a changed historical source
preimage rejects. The repository must have an actual `.git` directory; this
does not weaken the production source snapshot rule for linked worktrees.

The fixed archive destination is
`artifacts/history/m2-pre-participant-revision-v1`. It is never overwritten.
The only removed original paths are `reports/m2-feasibility-v0.json` and
`artifacts/gate8/`. The old candidate remains at its distinct historical ID
`eh72-hier-r5-r2-r1-crc32c-v0`; it is excluded from the revised active candidate
set. No new candidate ID, outcome, receipt, finalist, or gate pass is invented.

## Exact prior tuple

The prior source projection is the exact `m2-evidence-source-v0` projection
with raw SHA-256
`1943409374c64366f2619d76e807f7f2e1a415aecb3b3afbba73ced006c077b1`.
Every named source file must match its length, mode and SHA-256. The source
projection is archived together with its actual preimage files; mutable path
references are insufficient. Required direct historical identities are:

| Path | SHA-256 |
|---|---|
| `docs/roadmap.md` | `695e28fa0432da10a6dc6dbdb61ca2bd8764ea6006bbbeb558c3b8f20933b4c9` |
| `reports/m2-feasibility-v0.json` | `2315d001d3cceadeeacd1dfeedefeb681b6be3a32b787541fc6260502881d1b3` |
| `artifacts/gate8/generated-evidence-v0.json` | `d06134324aa0e0d89c46f4c5366f105dd949f5cf7b94700446f605bdf73413f9` |
| `artifacts/linux/verifier-v0.env` | `315f9021f83ee8c6640af6ea6bcd58387287bcef42e7b27eaaf5f76b2187f6a2` |

The preserved file set is the deduplicated union of source projection paths,
the roadmap and report, and every regular file under these complete roots:

- `artifacts/candidates/eh72-hier-r5-r2-r1-crc32c-v0/`, including damage and proof;
- `artifacts/gate8/`, including source/generated projections and four receipts;
- `artifacts/quiz/`, including original submissions, exposed packets and analyses;
- `artifacts/linux/`, including acquisition and historical refresh provenance;
- `artifacts/history/`, including earlier immutable candidate/owner archives.

The newly installed archive itself is excluded when comparing the original
history root. No other implicit ignore pattern exists. Private development
outputs outside those roots are not part of the tuple. Acquisition bytes remain
environment provenance, never a fresh execution receipt.

The historical Gate8 policy and its two bundle manifests define the canonical
69-file view. Validate that view with the existing historical bundle validator,
including modes, exact file bindings and canonical manifests. This transition
does not rerun the historical gates. One observed incidental file is separately
admitted as archived data only:

`artifacts/gate8/bundles/learner/participant/__pycache__/m2-learner-runner.cpython-314.pyc`

Its length is 45,017, mode 0644, SHA-256
`54820a16d61653dab4f043a0abcb41c8ef2f23edf4eec6de21414403f9a830cb`.
Store it below `incidental/` with its original path recorded. It is not a
canonical Gate8 file, is never imported, and is not evidence of a 70-file pass.
Every other extra under Gate8 rejects. Other preserved roots are historical
data, not executable inputs; their exact enumerated contents are preserved.

## Bounds and package

Use at most 4,096 files, 8 MiB per file, 512 MiB aggregate original bytes,
4,096 directories, 255 bytes per original relative path, and 2 MiB of manifest
JSON. Paths use printable ASCII POSIX components without slash at either end,
backslash, empty, `.` or `..` components. No symlink, hardlink, special file,
or symlink ancestor is admitted. Original regular-file modes are exactly 0600,
0644 or 0755. These are private archive bounds, independent of the unchanged
512 KiB carrier ceiling. Streaming reads use at most 1 MiB at a time.

The canonical manifest is sorted-key compact JSON with one final LF, schema
`golden-board.m2-participant-revision-transition/v1`, and exactly `schema`,
`files`, `directories`, `pending` keys. Each file row has `archive_path`,
`byte_length`, `mode`, `path`, `sha256`. Rows are original-path byte sorted,
unique. `mode` is the four-octal-digit original mode. Historical archive paths
are `prior/` plus original path; only the named incidental file uses
`incidental/`. Directory paths are the exact sorted directory set below the
five roots, including roots and empty directories. The archive preserves these
directories under `prior/`; the incidental file has its own parent chain.

`pending` has exactly four rows in byte-sorted path order, with the same keys
and `pending/` archive prefixes: `docs/roadmap.md`, `docs/m2-spec.md`,
`docs/m2-plan.md`, `docs/decisions.md`. They contain the exact deterministic
replacements described below. Every package file is private mode 0600 and
every directory mode 0700; original modes are retained in the manifest for
historical reconstruction. Only the manifest, enumerated payloads, their parent
directories and preserved original directories may exist. Links and extras
reject. Count and hashes are measured from actual preparation, not predicted
new outcomes. The prepared package is checked against its manifest after copy.

## Pending authority and document projection

Roadmap revision becomes 11, date 2026-09-16, derived project state `In progress`,
and the Section 13 M2 status becomes `In progress`. M0/M1 rows and all preceding
timeline text remain byte-identical. The final current-pass sentence in the M2
row is retained as explicitly historical, followed by a sentence reopening
Gates 1–8 for the participant-driven semantic and transport revision. The new
sentence denies any current Candidate-ready claim and retains the 512 KiB
ceiling; technical and learner validation remains pending.

The M2 specification and plan table rows are changed to revision 11 and all
Gates 1–8 reopened. A short notice before their first substantive section
distinguishes prior R3 history from the current pending revision and refers to
this owner. The previous decision text is retained and one dated decision is
appended explaining the same scope and archive. The command requires each
old replacement anchor exactly once. No pending document is installed before
the roadmap has become In progress. No fresh receipt or gate outcome is added.

## Application order and interruption

1. Validate the exact prepared package and digest, all original live preimages,
   directory/file sets and direct historical bindings. Refuse an existing
   mismatched archive, tombstone, replacement temporary file, or partial tuple.
2. Copy the package to a private stage below `artifacts/`, outside the preserved
   roots and on the destination filesystem; fsync payloads/directories;
   verify exact bytes and manifest; atomically install with no replacement;
   verify the installed archive again. An already exact archive is reusable.
3. Recheck live preimages. Install the exact pending roadmap with an atomic
   replacement and directory fsync. This is the authority boundary.
4. Under In progress authority, install the other three exact pending documents
   in path order. Each must be either its exact old or exact new bytes.
5. Verify remaining stale outputs against archived originals. Remove the report
   if present. Rename Gate8 with no replacement to the fixed sibling
   `artifacts/.gate8-participant-revision-remove-v1`, then delete only its exact
   archived files and directories. Fsync affected directories.

Before step 3, failure leaves the complete original authority/output tuple
unchanged and any completed archive intact. After step 3, failure never restores
stale Candidate-ready authority. Exact old/new document combinations and exact
remaining stale-output subsets may be resumed under the pending roadmap; an
unexpected file, changed remaining byte, or simultaneous live/tombstone Gate8
rejects. An interrupted private stage is never mistaken for the installed
archive. A complete pending tuple is success with no writes. Other states reject.

Archive validation and lifecycle completion prove byte preservation and status
transition only. Future source freeze, fresh four-producer evidence, revised
Gates 1–8 and authority-last Candidate-ready installation remain separate work.
