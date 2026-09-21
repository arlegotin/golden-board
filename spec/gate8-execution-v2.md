# Revised M2 execution and publication

This is the execution adapter for `gate8-policy-v2.toml`, not another gate.
Its scope is private computation and the existing archive-first/status-last
lifecycle. It changes no participant task, promise, ceiling or human result.

## Independent producers

Python entry is `tools/m2/generate_gate8_v2.py`; Rust entry is
`gb-m2-gate8-v2`. Both accept exactly this ordered argument vector:

```
producer --producer-id ID --workers N --work-root ABSOLUTE_DIRECTORY
```

Python admits native-python/linux-python; Rust admits native-rust/linux-rust.
N is a decimal integer1..8 without signs or leading zeroes. The working
directory is the ordinary source repository, with a directory `.git`.
The work root already exists, is empty, mode0700, and has no link ancestor.
It is outside the source repository and neither equals nor contains the
repository or executable. All directories created below it are0700; evidence
files are0644 regular nonhardlinks. Inputs and outputs never alias.

Each producer independently snapshots current complete source, binds the actual
Python interpreter or immutable private mode0500 Rust executable, reads its own
source inputs, builds its own22-file preflight and checks Gates1–5 prerequisites.
Rust additionally verifies all build-bound transitive source preimages against
the live frozen source. No foreign output enters source construction or recovery.
Linux labels require Linux/ARM64 and the exact acquired verifier receipt at
`artifacts/linux/verifier-v0.env`; actual image admission is the outer verifier's
separate duty. Native labels use the current OS/architecture and literal none
for image and acquisition. Recheck source/executable identities at every boundary.
Hash executable files in chunks no larger than65536 bytes with a separate
536870912-byte ceiling; this host input bound changes no artifact ceiling.

The producer writes `source.json` and `preflight/{22 core paths}` privately,
then emits exactly one canonical JSON line on stdout, at most16384 bytes:

```
{schema:golden-board.m2-preflight-ready/v2,producer_id,
 source_projection_sha256,core_rows}
```

`core_rows` is the complete22-file path-sorted array, with exact
`path,mode,bytes,sha256` keys and mode100644. This is readiness, not a receipt.
The coordinator checks actual preimages and compares both independently built
native cores before any D0–D7. The Linux coordinator also compares its fresh
cores with the core rows in both source-bound native receipts. Comparison-only
inputs remain outside producers. A disagreement releases neither producer.

After comparison the coordinator sends one canonical stdin line, at most4096
bytes, with exactly:

```
{schema:golden-board.m2-preflight-release/v2,source_projection_sha256,
 core_rows_sha256}
```

`core_rows_sha256` hashes the canonical object
`{schema:golden-board.m2-preflight-files/v2,rows:core_rows}`, including LF.
Both identities must match the producer's own current source and fresh core.
The coordinator closes stdin after the line. Read through EOF with the4096-byte
bound; EOF before a complete canonical line, extra fields/bytes, mismatch or a
3600-second wait expiry rejects before damage. The release carries no candidate
or expected result.

The producer then generates `candidate/` through its own complete replay and
proof, and `bundles/{technical-v2,learner-v2}/` through actual semantic kit
construction. Each bundle root has its exact raw files plus
`bundle-manifest.json`; the candidate gains `bundle-preimages.json`.
No losing Gate6/7 or invalid bundle emits a success receipt. Keep failed private
evidence for diagnosis; a later gate stays unevaluated. On success, rehash every
actual staged candidate file and verify its complete recursive set/modes and
the source/executable freeze, then atomically create `receipt.json` as the last
file. Exit0 follows only a complete receipt. No further stdout is permitted;
bounded diagnostics use stderr. No canonical repository output is written.

## Coordinator and clean Linux

`tools/m2/verify_gate8_v2.py` owns the two-producer handshake, fresh assembly and
check/release integration. A pair uses isolated producer work roots and an
immutable private Rust executable. It reads readiness with a bounded pipe,
compares source/core preimages, releases both, waits for both successful exits,
and admits both complete receipts. If a child fails, close its peer's stdin
and terminate/reap owned process groups; never continue to a success receipt.

The non-Gate8 portion of the existing full check is available as the internal
`scripts/check components` command: repo, identity, chess/oracle, source,
curriculum, content, transport and damage, in the existing order. It alone
cannot claim host_full, linux_full, Gate8 or Candidate ready. A full host/Linux
verification combines those checks with the fresh independent local producer
pair and complete current evidence comparison. During initial bootstrap the
same checks precede fresh generation and assembly; no not-yet-created report
or retained evidence is required as a generation input.

Clean Linux keeps the existing pinned acquired image and Dockerfile. Verify
the exact acquisition bytes and observed image ID/platform/labels, disable
networking, mount source read-only, materialize a private ordinary repository
using the existing execution-snapshot contract, and compare host/container
snapshot digests before and after. Mount native receipts for coordinator
comparison only; mount a separate private output directory. Copy the exact
acquisition receipt as provenance, never an outcome. Run components and the
fresh Linux pair. Export only the two receipts and a transient verification
record containing source and matching snapshot identities and actual check
outcomes. Snapshot identity remains outside report/source-stable attestation.

The pair CLI uses ordered options
`pair --kind native|linux --workers N --rust-binary ABS --work-root ABS`,
followed only for Linux by `--native-receipts ABS`. Its successful private
output includes `source.json` and `receipts/{two producer IDs}.json`.
The read-only `linux-input --native-receipts ABS` coordinator command admits
the host's exact current transition/roadmap and both native receipts against
its actual source, then prints only the64-hex source projection hash and LF.
Run that host-side admission against `/input` before materialization; the
ignored historical archive is not a fresh producer generation input.
The installed archive is the already prepared exact manifest with SHA-256
`6c9c4e7a70bd8d281425885416aef77c237fdf827a547300b6dc5c7eb5928d25`.
Admit its full preserved tuple and the exact pending roadmap (or its owned
Candidate-ready projection), and reject historical or partial live authority.

Linux exported output has exactly `linux-python.json`, `linux-rust.json` and
`verification.json`. The verification file is canonical JSON with exact keys
`schema,source_projection_sha256,acquisition_sha256,host_snapshot_sha256,
container_snapshot_sha256,components,pair,linux_receipt_sha256`. Its schema is
`golden-board.m2-linux-verification/v2`; all hashes are bare lowercase64-hex,
components and pair are literal pass only after their actual successful exits,
and linux_receipt_sha256 is exactly the two producer-ID-to-raw-receipt-hash map.
The wrapper rechecks host snapshot after the container and validates all three
output files. This is transient execution evidence, not a Gate8 attestation.

## Assembly and release

Assembly independently builds a fresh Python preflight, compares its entire
core with the already compared native cores, then freshly regenerates full
candidate and bundles. It compares all actual file preimages with all four
receipts and renders the exact cross-language, Linux, selection, generated
evidence and report projections. Rehash the complete staged tree and validate
the prospective roadmap before any canonical write.

Apply the admitted archive-first transition before source replacement. Install
only an absent candidate (or retain an exactly identical existing one), then
Gate8 tree, report and roadmap status, in that order. Use fsynced private stages
and atomic no-replace publication. Roll back only outputs created by this
transaction; restore exact prior roadmap bytes on status-write failure.
An existing unequal tree, partial authority, changed source or stale archive
rejects. Check mode writes no canonical path. Historical v0 dispatch stays exact.

Release runs the full host and clean-Linux flow afresh against the installed
revision and verifies unchanged source, report, complete evidence and roadmap.
Only a successful release enables the existing simple participant handoff.
Fresh qualifying human evidence is still required to finish M2.

Coordinator commands `bootstrap`, `full` and `release` take no additional
arguments. Each owns its actual component-check exit and fresh native pair.
Bootstrap requires the pending transition, runs clean Linux and publishes the
fresh assembly. Full requires Candidate ready, freshly regenerates native and
assembly evidence and compares the exact retained Linux bindings. Release
requires Candidate ready, reruns clean Linux too, and compares the unchanged
complete installed result. Private work directories and logs are diagnostic;
they never replace the successful process exits or checked evidence.

## Installed-candidate test repair

The first revised bootstrap completed all automated gates, but its following
release rejected the installed v2 candidate in a legacy ownership test that
dispatched every non-v1 manifest to the v0 validator. Repair that test with
explicit v2 physical-evidence recomputation, retaining v0/v1 coverage and
rejecting unknown schemas. No candidate promise or acceptance rule changes.

Before replacing source, preserve the completed tuple with source SHA-256
`ab893af5baeb8f3cfe4125e666def41a2896c547b19b59887837031558ab78fc`
and report SHA-256
`5a0155eb55e4d35c45fb36e16c614b5abb02e67c6679275336702149eb0cb2cd`
under `artifacts/history/m2-v2-before-partition-test-repair-v1`.
Its canonical `archive-manifest.json` has SHA-256
`6d89ed10197d0bb9c6034bd3d87ea20922083e6b72641c56b3b855f4a26c4005`.
It binds all997 prior source, candidate, Gate8, report and authority-document
files, their modes and raw identities, exact output directories, and the
existing owned pending roadmap. Verify the complete archive before atomic
no-replace installation, then recheck it and every live preimage. Preserve the
original participant-revision archive and all participant submissions.

Restore that exact pending roadmap before removing the archived v2 report,
Gate8 tree and revised candidate. Remove only matching archived files and
their exact directories; reject differences, extras, links or replacements.
An interruption leaves authority pending; reconcile only against the installed
archive before continuing. Apply the repaired source only after those stale
outputs are absent. Fresh bootstrap and release must independently regenerate
all producer, assembly and release evidence against the new frozen source.
The archived success is history, and the failed release cannot enable handoff.
