# M0 foundation and source reconnaissance implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute M0 on the current branch and leave a small, reproducible
foundation that locks the real anthology, inventories it without claiming chess
semantics, and proves one identity/manifest contract through independent Python
and Rust implementations.

**Architecture:** One byte-level specification and two independent identity
consumers sit beside a single Python source-doctor core and a thin locked-file
adapter. Hand-authored conformance fixtures and the source lock are the only
shared inputs. One POSIX-shell dispatcher composes the real checks after those
consumers exist. The milestone closes with a deterministic report and roadmap
evidence, not a framework or service.

**Tech stack:** POSIX `sh`; Git; `uv` 0.11.29 with CPython 3.14.6 and the Python
standard library; Rust 1.97.1 with `sha2`, `serde_json`, and test-only `toml`
(`serde`/`serde_core` may be direct only if the duplicate-key visitor imports
its traits); TOML; canonical-manifest v0 JSON; SHA-256.

## Global constraints

The implementation is governed, in order, by:

1. [`docs/roadmap.md`](roadmap.md) for product scope, M0 outcomes, G1, and
   status;
2. [`docs/m0-spec.md`](m0-spec.md) for the M0 implementation contract;
3. `spec/identity-v0.md`, once created, for identity and canonical-manifest
   bytes; and
4. fixtures and code as evidence, never as silent replacements for an owner.

The following are hard constraints:

- Work on the current branch. Do not create a parallel worktree for M0.
- Treat `docs/64_games.md` as immutable input. Every success and failure path
  must leave it byte-identical.
- Keep the Python and Rust identity/manifest implementations independent. They
  may share only the owning spec, hand-authored fixtures, registry, and ordinary
  SHA/JSON libraries.
- Checks are locked and offline after the explicit acquisition step. They do
  not fetch references, rewrite evidence, auto-format, or repair input.
- Spend validation and failure-handling code at the source, manifest, and path
  trust boundaries. Do not spend it on process ceremony.
- Do not add chess/PGN semantics, canonical games, selected transport/ECC/CRC,
  future registry slots, neutral constants, a release report, Docker files, CI,
  Nix, a task runner, a test framework, a Python or additional formatter, a
  schema framework, or a decision log without a real roadmap Section 3.5
  decision.
- Do not vendor the external references. Retain only their receipts and the two
  consumed, attributed NIST SHA-256 known answers.
- Do not weaken a gate to make it pass. If code exposes an ambiguity in a
  byte-affecting rule, repair the smallest owning specification first.
- Preserve unrelated user changes. M0 checks must work in a dirty worktree and
  must not require a globally clean repository.

### Flexibility envelope

This plan fixes observable contracts, not private code shape. The implementing
agent may, without amending the plan:

- rename or regroup private helpers;
- split a source file only when it becomes materially easier to review;
- combine or split the suggested commits;
- reorder independent work after the dependency is available;
- choose iterative or bounded-recursive internals within the specified limits;
- group test cases differently while preserving the fast/focused/full cadence;
  and
- use an equivalent standard-library implementation that produces the same
  bytes, rejection behavior, and bounds.

The agent may not silently change public command forms, fixture meaning,
canonical bytes, report fields, source-lock meaning, independent-consumer
boundaries, exit codes, resource ceilings, or M0 claims. A harmless local choice
needs no decision note. A consequential choice needs only the single concise
roadmap Section 3.5 note, and only if that class of choice actually occurs.

### Working method

- Begin each logic slice with the smallest test that can fail for the intended
  reason, then implement only enough to pass the slice.
- Use direct pinned commands until `scripts/check` is real. Never add a stub
  command that reports success for an unimplemented area.
- Finish each packet with its review gate. A packet may be committed there, but
  commit count and message wording are discretionary.
- Keep generated boundary payloads in tests or temporary directories; do not
  commit megabyte fixtures.
- If a packet uncovers a spec defect, pause only the affected path, fix the
  owner, add the failing example, and continue. Independent packets need not
  stop.
- If a required input or tool is genuinely unavailable, leave M0 non-complete
  and record the exact prerequisite; do not invent evidence.

## Dependency and responsibility map

```text
1 start/toolchains ──> 2 identity owner/fixtures ──> 3 Python identity ─┐
                         └─────────────────────────> 4 Rust identity ───┤
1 start/toolchains ──> 5 source lock/ledger ──────> 6 source doctor ───┤
                                                                      v
                                                          7 root orchestration
                                                                      |
                                                                      v
                                                               8 G1 closure
```

Packets 3 and 4 can proceed in parallel after Packet 2. Packet 5 is data and
prose only, so it can proceed in parallel with Packets 2–4. Packet 6 needs the
Python manifest serializer and the source lock. Packet 7 composes completed
consumers rather than creating placeholder ones.

| Boundary | Required interface | Flexible detail |
|---|---|---|
| Identity | bytes domain + ordered byte fields → lowercase SHA-256 hex, with checked `u16`/`u32` framing | helper names and allocation strategy |
| Manifest | bounded bytes ↔ v0 value; canonical serialize; canonical validate | internal value representation and parser organization |
| Scanner core | bounded source bytes + already-validated lock facts → bounded lexical report value | scanner/helper decomposition |
| Source adapter | repository root + locked relative path → stdout report or safe diagnostic/exit | private filesystem helper names |
| Root check | exact `fast`, `focused source|identity|repo`, and `full` interface | nonduplicative internal ordering |

Use the smallest stable API needed by the next packet. A practical Python seam is
`identity_hex(domain, fields)`, `serialize_manifest(value)`,
`canonicalize_manifest(data)`, and `validate_canonical_manifest(data)`. A
practical Rust seam is the same four operations over byte slices and a local
manifest value. These names are recommendations, not a second normative API;
tests and callers may move together if an equally small interface is clearer.

## Preflight and acquisition

These checks observe the host; they do not enter semantic inputs or the report.

- [ ] Confirm the current branch and inspect, but do not discard, existing
  changes:

  ```sh
  git branch --show-current
  git status --short
  ```

  Expected: the branch is the user's current M0 branch. A dirty worktree is not
  itself a failure; overlapping changes must be preserved or surfaced.

- [ ] Check the bootstrap tools. If an exact tool is missing, use the documented
  explicit acquisition route; do not make checks install it implicitly:

  ```sh
  uv --version
  rustup toolchain list
  git --version
  ```

  Expected M0 selections: uv 0.11.29, CPython 3.14.6, Rust/Cargo 1.97.1 with
  `rustfmt`. Git's observed version is not byte-defining.

- [ ] If the exact runtimes are absent, acquire them explicitly after confirming
  the selected pins. Initial lockfile resolution in Packets 3 and 4 may also use
  the network. Once a lockfile exists, its tests and checks may not:

  ```sh
  uv python install 3.14.6
  rustup toolchain install 1.97.1 --profile minimal --component rustfmt
  ```

- [ ] With the pinned Python now available, confirm the locked anthology before
  any implementation edit:

  ```sh
  uv run --no-project --python 3.14.6 --offline --no-python-downloads \
    python -c 'from pathlib import Path; import hashlib; p=Path("docs/64_games.md"); b=p.read_bytes(); print(len(b), hashlib.sha256(b).hexdigest())'
  ```

  Expected SHA-256:
  `33d44f7167ab190cc793e3fdfd8190d89ed13c1dc507c20854cf64751c7be7da`;
  expected size: `165145` bytes.

- [ ] After each native lockfile exists, acquire its declared dependencies:

  ```sh
  uv sync --locked
  rustup run 1.97.1 cargo fetch --locked
  ```

  A machine with already-populated caches may do no network I/O. Ordinary checks
  below must still use locked offline flags.

## Packet 1: Start M0 and create the native foundation

**Files:**

- Modify: `docs/roadmap.md`
- Create: `AGENTS.md`
- Create: `README.md`
- Create: `.gitignore`
- Create: `.python-version`
- Create: `rust-toolchain.toml`

This packet starts the milestone and creates only information already selected
by the roadmap/spec. It does not create a pretend check runner.

- [x] Change the M0 row in roadmap Section 13 to `In progress`; update the two
  derived header rows to `Project state = In progress` and `Current milestone =
  M0 — Foundation and source reconnaissance`. Do not touch later milestone
  states.

- [x] Write the six roadmap Section 3.1 rules into `AGENTS.md` with links to the
  roadmap and M0 spec. Keep it to roughly one screen and do not add generic
  agent-process policy. Packet 7 adds the root commands after they exist.

- [x] Draft `README.md` with the product thesis, bounded/pre-artifact warning,
  exact tool versions and runtime acquisition, a link to roadmap Section 13
  instead of copied status, and a map containing only paths that exist at that
  point. Packet 7 adds the check commands after they are real.

- [x] Write exactly the M0 ignore entries:

  ```text
  .DS_Store
  .venv/
  __pycache__/
  *.py[cod]
  target/
  artifacts/
  ```

  Do not ignore lockfiles, reports, fixtures, source, or broad document/source
  patterns.

- [x] Pin `.python-version` to `3.14.6`. Pin `rust-toolchain.toml` to channel
  `1.97.1`, profile `minimal`, with the `rustfmt` component.

- [x] Review the packet directly:

  ```sh
  uv --version
  rustup run 1.97.1 rustc --version
  rustup run 1.97.1 cargo fmt --version
  uv run --no-project --python 3.14.6 --offline --no-python-downloads \
    python -c 'from pathlib import Path; import hashlib; b=Path("docs/64_games.md").read_bytes(); print(hashlib.sha256(b).hexdigest())'
  ```

  Expected: exact selected versions are reachable and the source digest is
  unchanged. Inspect the short entry files in full; Packet 7's repo gate later
  performs the whole-file whitespace check. Do not require `scripts/check` yet.

**Review gate:** M0 is visibly in progress, entry docs are concise and honest,
pins are exact, and no project/future scaffold exists.

**Suggested checkpoint:** `Start M0 foundation`.

## Packet 2: Promote the identity owner and hand-author conformance data

**Files:**

- Create: `spec/identity-v0.md`
- Create: `conformance/identity-v0.json`
- Create: `conformance/manifest-v0.json`
- Create: `conformance/registry.toml`
- Modify: `docs/m0-spec.md`

- [ ] Move the exact identity/canonical-manifest wire contract from M0 spec
  Sections 7.1–7.7 into `spec/identity-v0.md`. In the same change, replace the
  duplicate wire prose in `docs/m0-spec.md` with a short owner link and an
  acceptance checklist for framing, domains, data model, serialization, limits,
  fixtures, and registry. Update remaining M0-spec and plan cross-references to
  point to the new owner headings, then search for duplicated normative
  algorithms before proceeding.

- [ ] Write `conformance/identity-v0.json` as a canonical manifest with the
  cases under `spec/identity-v0.md` “Conformance fixtures”: NIST empty and
  one-byte `d3` SHA-256 cases, zero
  fields versus one empty field, ambiguous-looking field boundaries, two local
  test domains, binary bytes, count/length helper boundaries, and lowercase
  output.

- [ ] Write `conformance/manifest-v0.json` with lowercase-hex payloads and
  expected canonical/rejection outcomes covering the valid, noncanonical,
  invalid, depth, integer, Unicode, duplicate-key, escape, UTF-8, and size cases
  under the owning spec's data-model, serialization, limits, and fixtures
  headings. Describe size/depth boundary recipes compactly; construct the large
  values in each implementation's tests.

- [ ] Independently spot-check the hand-authored bytes before any implementation
  can bless them:

  - manually expand at least zero fields, one empty field, `a|bc`, and `ab|c`
    into their exact big-endian preimages;
  - verify the two NIST digests against the locked member receipt in the M0
    spec/source research;
  - verify the canonical empty object, key-order, escaping, `U+007F`, and
    terminal-LF cases byte by byte; and
  - confirm fixture-local `test:*` domains are not registered product domains.

- [ ] Create `conformance/registry.toml` only after both payloads exist. Give
  each entry its unique ID, path, spec/version, SHA-256, consumers `python` and
  `rust`, and provenance `hand-authored`. Register exactly these two suites;
  every other future category stays absent rather than empty.

- [ ] Validate shape and hashes with a disposable standard-library command or
  review snippet. Do not add a fixture generator, updater, or schema package.
  Re-run:

  ```sh
  uv run --no-project --python 3.14.6 --offline --no-python-downloads \
    python -c 'import hashlib, pathlib, sys; print("\n".join(f"{hashlib.sha256(pathlib.Path(n).read_bytes()).hexdigest()}  {n}" for n in sys.argv[1:]))' \
    conformance/identity-v0.json conformance/manifest-v0.json
  ```

  Compare the two hashes to the registry values. Verify each JSON payload has
  one terminal LF and no BOM.

**Review gate:** `spec/identity-v0.md` is the sole wire owner; both fixture files
are hand-reviewable and independently derived; the registry is closed over only
the two files that exist.

**Suggested checkpoint:** `Freeze identity v0 fixtures`.

## Packet 3: Implement the Python identity/manifest path test-first

**Files:**

- Create: `pyproject.toml`
- Create: `uv.lock`
- Create: `python/golden_board/__init__.py`
- Create: `python/golden_board/identity.py`
- Create: `python/golden_board/canonical_manifest.py`
- Create: `python/tests/test_foundation.py`

- [ ] Define the root Python project for exactly CPython 3.14.6 with
  `[tool.uv] package = false`, no build backend, no runtime dependency, and
  standard-library `unittest`. Generate `uv.lock` with uv 0.11.29.

- [ ] Add failing identity tests that read the shared registry and fixture
  directly. Cover framing byte examples, domain rules, field order/boundaries,
  binary fields, `u16`/`u32` maxima and one-over rejection, NIST raw SHA cases,
  and fixed lowercase digest rendering. Assert fixtures remain unchanged across
  the run.

- [ ] Implement only the byte-oriented identity operations needed by those
  tests using `hashlib`, explicit big-endian conversions, and checked bounds.
  Reject bad domains and overflows before constructing an output. Do not accept
  text implicitly or normalize bytes.

- [ ] Add failing canonical-manifest tests in manageable groups:

  1. valid scalar/container/ordering and round-trip cases;
  2. noncanonical-but-parseable cases;
  3. invalid JSON/subset/UTF-8/duplicate-key/surrogate cases;
  4. depth, input-size, output-size, and `u64` boundaries; and
  5. idempotence, insertion-order independence, NFC/NFD distinction, and exact
     terminal-LF properties.

- [ ] Implement parse, serialize, canonicalize, and canonical-validate behavior
  with `json` hooks plus explicit subset, Unicode-scalar, key, depth, integer,
  and byte-count checks. Reject oversized input before parsing, enforce depth
  before descending to level 33, and count output while emitting so an oversized
  result is never constructed and returned. Do not rely on Python's permissive
  defaults for floats, constants, duplicate keys, or surrogate-containing
  strings.

- [ ] Run the Python gate after each group:

  ```sh
  PYTHONPATH="$PWD/python" uv run --locked --offline --no-python-downloads \
    python -m unittest discover -s python/tests -p 'test_*.py' -v
  ```

  Expected: the intended new tests fail before implementation, then all pass;
  fixture and lock bytes remain unchanged.

- [ ] Review for accidental ambient inputs and hidden dependencies:

  ```sh
  uv lock --check --offline --no-python-downloads
  git status --short
  ```

  The only Python import root used by checks will be the repository's `python/`
  directory; no editable/global install or caller `PYTHONPATH` is part of the
  contract.

**Review gate:** Python independently passes every identity/manifest fixture and
boundary with exact canonical bytes, no runtime dependency, and no fixture
rewrites.

**Suggested checkpoint:** `Implement Python identity v0`.

## Packet 4: Implement the Rust identity/manifest path independently

**Files:**

- Create: `Cargo.toml`
- Create: `Cargo.lock`
- Create: `crates/gb-foundation/Cargo.toml`
- Create: `crates/gb-foundation/src/lib.rs`
- Create: `crates/gb-foundation/tests/conformance.rs`

Packets 3 and 4 may be assigned to separate agents or contexts. The Rust author
must implement from `spec/identity-v0.md` and the hand fixtures, not from Python
source or Python-generated output.

- [ ] Create a one-member Cargo workspace and one library crate. Add only
  `sha2` and `serde_json` as ordinary dependencies and `toml` as a dev
  dependency. A direct `serde` or `serde_core` entry is permitted only if code
  imports its visitor traits; in that case first make the same narrow correction
  to M0 spec Section 4.3. Resolve and commit the root lockfile.

- [ ] Add failing Rust conformance tests that parse the registry and both fixture
  payloads themselves. Mirror the behavior categories, not the Python code
  organization. Include direct framing/preimage assertions and the two NIST
  raw-digest cases so cross-language agreement is not the only oracle.

- [ ] Implement checked identity framing and digest rendering using `sha2`.
  Reject domain/count/length violations before truncation or unchecked
  allocation.

- [ ] Implement the manifest subset over a small local value/error model or an
  equally direct representation. Use `serde_json` lexical machinery, with a
  custom visitor where duplicate-key preservation/rejection requires it. Add
  explicit UTF-8, scalar, key, subset, `u64`, depth, canonical-byte, and output
  limit enforcement; do not inherit `serde_json` defaults as the spec.

- [ ] Run the pinned Rust gate repeatedly:

  ```sh
  rustup run 1.97.1 cargo test --workspace --all-targets --locked --offline
  rustup run 1.97.1 cargo fmt --all --check
  ```

- [ ] Run both language suites without one invoking the other and compare their
  fixture outcomes. The shared expected data must still be the hand-authored
  files, never an output copied from the first implementation.

- [ ] Audit the dependency boundary:

  ```sh
  rustup run 1.97.1 cargo metadata --locked --offline
  ```

  Expected: one workspace crate and no project CLI, error-derive, schema,
  logging, native binding, build script, or generated code. Review the full
  locked graph once for build scripts, proc macros, native links, and other
  executable surfaces; retain only what the three consumed libraries actually
  require. This is a change-triggered dependency review, not a recurring report.

**Review gate:** Rust independently passes the same hand-authored cases and exact
limits, Python still passes, and neither implementation executes or imports the
other.

**Suggested checkpoint:** `Implement Rust identity v0`.

## Packet 5: Lock the real inputs and write the human source ledger

**Files:**

- Create: `inputs/source-lock.toml`
- Create: `docs/sources.md`

- [ ] Author the small TOML lock with one authoritative source entry and exact
  receipts for the FIDE 2023 PDF, historical PGN text, FIPS 180-4 PDF, NIST byte
  vector archive, and consumed `SHA256ShortMsg.rsp` member. Use the identities in
  M0 spec Section 2.3; do not refetch moving pages during ordinary validation.

- [ ] Keep tool versions, host/Docker observations, report hashes, future
  semantic inputs, and all CRC/ECC/profile candidates out of this lock.

- [ ] Write `docs/sources.md` as one compact human ledger. For each retained
  source record title/organization, exact edition and access date, stable
  locator and locked identity, role, concrete supported conclusion, explicit
  non-conclusion, retention, provenance, and redistribution status. Link to the
  machine lock rather than duplicating a second inventory.

- [ ] Include the five M0-wide conclusions explicitly: the PGN guide is not the
  project grammar; CRC/ECC material remains deferred until M2 has a consumer;
  references do not prove Golden Board conformance; ordinary checks never fetch
  them; and anthology provenance/redistribution rights remain unresolved unless
  the owner supplies a concrete basis.

- [ ] State the rights boundary plainly: a URL or owner risk decision is not
  redistribution permission. Local read-only M0/M1 analysis may continue, but
  further public redistribution needs source provenance plus an applicable
  licence, permission, public-domain status, or other concrete basis for the
  exact retained material.

- [ ] Run:

  ```sh
  PYTHONPATH="$PWD/python" uv run --locked --offline --no-python-downloads \
    python -c 'from pathlib import Path; import hashlib; b=Path("docs/64_games.md").read_bytes(); print(len(b), hashlib.sha256(b).hexdigest())'
  ```

  Expected: the hand-reviewed lock values match M0 spec Section 2.3 and the
  anthology bytes; no command performs network I/O or changes the anthology.
  Packet 6A supplies executable lock-mutation rejection.

**Review gate:** The lock identifies the exact anthology and retained reference
receipts offline, its closed shape is hand-reviewable, and the human ledger
remains honest about what each source and rights record does not prove.

**Suggested checkpoint:** `Lock M0 sources`.

## Packet 6: Build the source doctor and deterministic report

**Files:**

- Create: `python/golden_board/source_doctor.py`
- Modify: `python/tests/test_foundation.py`
- Modify: `crates/gb-foundation/tests/conformance.rs`
- Create: `reports/source-doctor.json`

This is the largest packet because fence, tag, movetext, and report fields form
one observational contract. Implement it in the four slices below, keeping one
module and one test file unless reviewability clearly demands a consumed split.

### Slice 6A: Locked-file trust boundary

- [ ] Add failing lock-document tests for duplicate IDs, malformed digest/size,
  missing or extra fields, absolute or escaping paths, wrong entry classes, and
  forbidden future selections.

- [ ] Implement the consumed lock parser with `tomllib`. Accept only the closed
  M0 shape, keep tracked paths inside the supplied repository root, reject
  duplicate/future selections, and never fetch remote references.

- [ ] Add failing adapter tests for exact source, missing path, symlink,
  directory and portable FIFO/socket cases, path escape, unreadable/non-regular
  objects, just-below/at/above 1,048,576 bytes, same-length replacement, append,
  deletion, and mismatched lock size/hash combinations.

- [ ] Implement the locked-path adapter with an `lstat` rejection of obvious
  symlink/non-regular objects, then a read-only nonblocking open with no-follow
  support where available, followed by immediate `fstat` as the authoritative
  file-kind check. This prevents a swapped-in FIFO from blocking between the
  precheck and descriptor check. Read at most the limit plus one byte; require a
  contained repository-relative path and exact size/hash comparison. Unsafe
  objects fail before scanning with empty stdout and a concise stderr
  diagnostic. A safely read mismatch is scanned, emits `lock_match=false`, and
  exits nonzero.

### Slice 6B: Pure byte scanner

- [ ] Add small table-driven tests for encoding, BOM, NFC availability, newline
  forms, controls, tabs/trailing whitespace by region, exact fences and near
  misses, orphan/nested/unclosed cases, completed-candidate spans, separators,
  tags, malformed/duplicate tags, escapes, tag orders, and punctuation. Assert
  every span round-trips by slicing the original bytes.

- [ ] Implement a pure scanner whose inputs are bounded bytes and validated lock
  facts and whose output is a bounded manifest value. It must not consult the
  filesystem, network, time, environment, locale, randomness, subprocesses, or
  chess logic. Only exact completed fence pairs contribute blocks.

### Slice 6C: Movetext inventory, duplicates, and report schema

- [ ] Add tests for every lexical class and construct in M0 spec Sections
  8.6–8.8, including line wrapping, result agreement states, empty movetext,
  unknowns, SAN-shaped features, tag/movetext punctuation separation, raw and
  token-sequence duplicates, deterministic ordering, sample truncation, and
  exact fragment spans.

- [ ] Add adversarial long-line/token, fence-dense, unique-tag-dense, invalid
  UTF-8, CRLF, and report-growth cases. Verify the single input/report ceiling,
  32 examples per sampled category, 256 retained bytes per sample, checked
  canonical size accounting, and the exact `report_limit` error manifest. Use
  anchored/linear matching; no input-dependent catastrophic regex.

- [ ] Implement the exact closed report shape, fixed strings, ranges, hashes,
  sample fragments, sort orders, duplicate equality confirmation, and
  lexical-only field allowlist in M0 spec Section 8.8. Both implementations must
  accept normal report bytes as canonical manifest; Python additionally checks
  the exact source-doctor schema and non-claim allowlist.

### Slice 6D: Current-source evidence

- [ ] Expose one thin module command that asks Git for the enclosing worktree,
  loads its lock, reads only the locked anthology, and writes candidate report
  bytes to stdout. It accepts no arbitrary source path or source-derived shell
  command, executes no input, and never writes the tracked report itself.

- [ ] Test the command from the checkout root and a nested working directory.
  A safe bounded read emits a report; the gate exits 0 only when size/hash,
  UTF-8/no-BOM, locked LF/final-LF, controls, 64 candidates, and orphan/nested/
  unclosed-fence invariants all pass. Lock, encoding, newline, control, count,
  or pairing drift emits the bounded observational report and exits 1. Near
  misses alone remain nonblocking. Unsafe input leaves stdout empty and exits 1;
  report overflow emits only the exact `report_limit` manifest and exits 1.

- [ ] Create ignored authoring storage with pinned Python and generate a
  candidate there, never directly over the tracked report. Review it against
  M0 spec Section 2.2 and the Section 8.8 schema. Install approved bytes by
  writing a same-directory temporary file under `reports/`, closing it, and
  calling `os.replace`; never redirect or copy over the tracked path. Document
  that explicit candidate-review/atomic-replace workflow in README so an
  interrupted generation leaves either the old complete report or the new one.

- [ ] Add the focused-source harness: capture one fresh full-source generation
  in `tempfile.TemporaryDirectory`, compare it byte-for-byte to the tracked
  report, validate all spans/order/non-claim invariants, and compare the source
  digest before and after. Ordinary tests never update the report.

- [ ] Extend the Rust conformance test to validate the tracked report bytes as
  canonical manifest v0 without learning the Python source-report schema. The
  source-focused Python tests remain the sole checker of report-specific fields
  and spans.

- [ ] Run after every slice and once over the real source:

  ```sh
  PYTHONPATH="$PWD/python" uv run --locked --offline --no-python-downloads \
    python -m unittest discover -s python/tests -p 'test_*.py' -v
  PYTHONPATH="$PWD/python" uv run --locked --offline --no-python-downloads \
    python -c 'from pathlib import Path; Path("artifacts").mkdir(exist_ok=True)'
  PYTHONPATH="$PWD/python" uv run --locked --offline --no-python-downloads \
    python -m golden_board.source_doctor > artifacts/source-doctor.candidate.json
  # After reviewing the candidate only:
  PYTHONPATH="$PWD/python" uv run --locked --offline --no-python-downloads \
    python -c 'import os,tempfile; from pathlib import Path; s=Path("artifacts/source-doctor.candidate.json"); d=Path("reports/source-doctor.json"); d.parent.mkdir(exist_ok=True); f=tempfile.NamedTemporaryFile(dir=d.parent,delete=False); p=f.name; f.write(s.read_bytes()); f.close(); os.replace(p,d)'
  PYTHONPATH="$PWD/python" uv run --locked --offline --no-python-downloads \
    python -c 'import hashlib, pathlib, sys; print("\n".join(f"{hashlib.sha256(pathlib.Path(n).read_bytes()).hexdigest()}  {n}" for n in sys.argv[1:]))' \
    docs/64_games.md reports/source-doctor.json
  ```

  These are authoring commands, not ordinary checks. Expected current facts
  include 165,145 bytes, 4,376 LF, 64 candidates, 895 recognized tags, 7,456
  tokens, 4,915 SAN-shaped lexical tokens, no raw/token-projection duplicate
  group, and no semantic/chess claim.

**Review gate:** Synthetic mutation cases fail or report exactly as specified;
the real report is canonical, deterministic, bounded, lexical-only, and bound
to the unchanged source; interrupted generation cannot damage tracked evidence.

**Suggested checkpoints:** one after the pure scanner is reviewable and one
after the tracked report is reviewed. Combining them is fine if the diff remains
easy to inspect.

## Packet 7: Compose the real root checks and finish entry docs

**Files:**

- Create: `scripts/check`
- Modify: `python/tests/test_foundation.py`
- Modify: `README.md`
- Modify: `AGENTS.md`

- [ ] Add failing tests for the public CLI contract: no argument, unknown mode,
  missing/unknown focused area, and extra arguments return 2 with usage; a
  failed prerequisite/child returns 1 and names the area/command; success
  returns 0. Avoid invoking `fast` or `full` recursively from inside its own
  unit suite.

- [ ] Implement one portable POSIX-shell dispatcher with exactly:

  ```text
  scripts/check fast
  scripts/check focused source
  scripts/check focused identity
  scripts/check focused repo
  scripts/check full
  ```

  Resolve the repository root, set an absolute repository `python/` path for
  child Python processes, validate Git presence and exact uv/Python/Rust tools
  once, stop at the first failure, and emit concise human output. Git's version
  is reported only as a prerequisite, not pinned or recorded in evidence. Do
  not implement `release`, `linux`, or future focused areas.

- [ ] Set the dispatcher executable in the working tree, then record that mode
  when staging its first commit. Use the already-pinned Python runtime rather
  than adding another bootstrap utility:

  ```sh
  PYTHONPATH="$PWD/python" uv run --locked --offline --no-python-downloads \
    python -c 'import os,stat; p="scripts/check"; os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)'
  git add scripts/check
  test -x scripts/check
  git ls-files --stage scripts/check
  ```

  Expected index mode: `100755`. The final repo check rejects a missing working
  executable bit or a non-`100755` tracked mode.

- [ ] Before the first `full` run, inspect every intended M0 path and stage each
  one explicitly. Never unstage or otherwise rewrite unrelated index entries;
  do not use `git add -A` or broad directory pathspecs in a dirty worktree:

  ```sh
  git status --short
  git diff --cached --name-status -- <exact intended M0 paths>
  git diff --cached --check -- <exact intended M0 paths>
  ```

  Add omitted intended paths by exact name. If an intended path contains
  overlapping user work that cannot be separated safely, stop and surface that
  overlap. Unrelated staged or unstaged paths remain untouched. This lets the
  repo check prove that every intended deliverable and executable mode will
  survive a clone without taking ownership of unrelated changes.

- [ ] Compose the areas without duplicated expensive work:

  - `identity`: registry/fixture hashes and closure; independent Python and Rust
    identity, manifest, rejection, and boundary cases.
  - `source`: lock/current descriptor checks; complete scanner mutation set; one
    fresh full report comparison; report canonicality in both languages; and
    span/order/non-claim/source-unchanged checks.
  - `repo`: `sh -n`, pinned `cargo fmt --check`, scoped `git diff --check --`,
    direct whole-file whitespace/conflict-marker checks over M0-authored text
    (excluding the locked anthology), required/nonempty/tracked M0 artifacts
    including this plan, executable script mode, registry closure,
    README/AGENTS target checks, and roadmap status/header derivation. It also
    rejects the small named set of
    premature M1+ artifacts from M0 spec Sections 3.2/4, forbidden source-lock
    selection fields, and empty/future registry slots. Required/tracked/mode and
    premature-artifact checks inspect the candidate index/tracked tree with
    Git, not unrelated untracked filesystem paths; exact M0 content checks
    inspect their working bytes. `docs/decisions.md` is allowed only if
    execution actually made and recorded a roadmap Section 3.5 decision. This
    is a targeted M0 guard, not a closed repository allowlist.
  - `fast`: preflight, repo, current source/lock invariants, and ordinary
    Python/Rust unit/conformance tests; skip the large mutation set and fresh
    full report generation.
  - `full`: all three focused areas once in a nonduplicative order.

  Test-class names and internal order are flexible. If one test file is used,
  route `fast` and `focused` to explicit `unittest` classes rather than adding a
  test plugin or environment-controlled skip framework.

- [ ] Ensure every ordinary Python child uses:

  ```text
  uv run --locked --offline --no-python-downloads
  ```

  and every dependency-resolving Cargo child uses pinned Rust with `--locked
  --offline`. Run pinned `cargo fmt` without unsupported lock/offline flags.

- [ ] Verify dirty-worktree safety. The checks may inspect M0-owned diffs but
  must neither fail merely because unrelated changes exist nor modify, stash,
  restore, clean, or reset them. Temporary test objects must be self-created and
  removed through `TemporaryDirectory` or an equally scoped standard-library
  mechanism.

- [ ] Finalize README: list only existing paths; document exact
  setup/acquisition and all real check forms; document the
  candidate-first report-authoring command; link rather than copy status; retain
  the pre-artifact/unvalidated warning. Finalize AGENTS with the same real root
  command surface.

- [ ] Exercise every public form from the repository root:

  ```sh
  scripts/check fast
  scripts/check focused identity
  scripts/check focused source
  scripts/check focused repo
  scripts/check full
  ```

  Then exercise missing/unknown/extra arguments and one controlled failed-child
  path. Expected exit codes are 0, 2, and 1 respectively. Repeat the valid forms
  from a `TemporaryDirectory` by invoking the checkout's absolute
  `<repo>/scripts/check` path; a bare relative `scripts/check` is not expected to
  resolve outside the checkout. The dispatcher must still locate and operate on
  its own repository rather than the caller's current directory.

- [ ] Repeat deterministic checks under changed `TZ`, locale variables, and
  caller `PYTHONPATH`. Output bytes must not change. Confirm the checks make no
  network request after acquisition because every resolving invocation is
  explicitly offline; actual network isolation remains the named M2 Linux
  obligation. Confirm checks do not rewrite locks, fixtures, report, source, or
  roadmap status.

**Review gate:** Every documented root command is real; `full` covers all M0
evidence once; failures are actionable; ordinary checks are offline,
non-mutating, path-independent, and safe in a dirty worktree.

**Suggested checkpoint:** `Add M0 root checks`.

## Packet 8: Stress the candidate, close G1, and advance status

**Files:**

- Modify only if needed: implementation/tests/specs from Packets 1–7
- Modify last: `docs/roadmap.md`

### Candidate audit before completion

- [ ] Run the full command and record actual report/fixture/registry identities
  for the status evidence:

  ```sh
  scripts/check full
  PYTHONPATH="$PWD/python" uv run --locked --offline --no-python-downloads \
    python -c 'import hashlib, pathlib, sys; print("\n".join(f"{hashlib.sha256(pathlib.Path(n).read_bytes()).hexdigest()}  {n}" for n in sys.argv[1:]))' \
    reports/source-doctor.json conformance/registry.toml \
    conformance/identity-v0.json conformance/manifest-v0.json docs/64_games.md
  ```

- [ ] Trace each roadmap M0 exit criterion and M0 spec Section 14 row to an
  executable check or exact evidence artifact. A prose assertion alone does not
  close a row. Later-milestone claims remain deferred rather than waived.

- [ ] Confirm M0 spec Section 10 still records the verified Docker 25.0.3
  `linux/arm64` mechanism, pinned Debian multi-architecture digest, offline
  image-bundle shape, and pre-M2 deadline. If execution evidence contradicts the
  recorded host fact, amend that section with the exact blocker/owner action;
  do not add Docker files or a second Linux mechanism during M0.

- [ ] Review the complete diff for:

  - any edit to `docs/64_games.md`;
  - fixture expectations generated by one implementation;
  - duplicated identity wire ownership;
  - host/time/path facts in deterministic output;
  - permissive JSON defaults or unchecked length/depth arithmetic;
  - source-derived shell commands or semantic chess interpretation;
  - network use in ordinary checks;
  - generated evidence that a check can silently rewrite;
  - empty/future-facing files and unused dependencies; and
  - Docker/CI/release/profile/CRC/ECC work pulled forward.

- [ ] Audit `scripts/check full` coverage for the high-risk cases already built
  in Packets 3–7: equal-length source replacement; symlink/path escape; invalid
  UTF-8 and mixed newlines; 63/65 and nested/unclosed fences; empty movetext;
  duplicate tag/result ambiguity; pathological line/token; report limit;
  manifest duplicate keys, `u64::MAX`, and exact/one-over depth and size;
  fixture tamper; dirty worktree; different cwd/locale/timezone; explicit
  locked/offline flags and actionable failure when a disposable cache lacks a
  dependency; and controlled child failure. Do not require cache-hidden success
  or network isolation at M0—that belongs to the pre-M2 Linux path. Add only a
  genuinely missing case, then let `full` execute the corpus once.

- [ ] Check the repository remains intentionally small:

  ```sh
  git status --short
  scripts/check focused repo
  git diff --stat
  git diff --cached --stat
  ```

  Delete unused scaffolding instead of documenting it. Keep a consumed split
  only when it makes the implemented behavior materially easier to review.

- [ ] Create the cold-start candidate commit while M0 still says `In progress`.
  Include every intended M0 implementation/evidence path and no unrelated user
  change. Earlier packet commits may already contain most of it; this checkpoint
  only requires that the current candidate be fully reconstructible from Git.
  Use a path-scoped commit (`git commit --only -- <exact intended M0 paths>`) so
  unrelated staged entries remain untouched.

- [ ] From a standard-library `TemporaryDirectory`, clone that exact candidate
  commit without local hardlinks, run the documented runtime/dependency
  acquisition, then run `scripts/check full`. The harness may invoke Git and the
  documented bootstrap tools through `subprocess`; it must delete only its own
  temporary checkout. Do not carry uncommitted files or host project directories
  into the clone. If implementation or evidence fails, keep M0 `In progress`,
  fix the current branch, create a new path-scoped candidate commit, and repeat.
  If the run cannot acquire a required runtime/dependency because an external
  prerequisite is unavailable, set M0 to `Blocked — <exact prerequisite>`, set
  the derived header to `Project state = Blocked` with current milestone M0, and
  commit that roadmap-only status before stopping. Do not mislabel an external
  prerequisite as a code revision.

### Status transition

- [ ] Only after the candidate audit is green, change M0's roadmap row to:

  ```text
  Complete — <actual date>; scripts/check full; <report and registry identities>
  ```

  Update the derived header to `Project state = In progress` and `Current
  milestone = M1 — Chess truth, source grammar, and assessment blueprint`.
  Leave M1 itself `Not started`. This is the last semantic M0 edit.

- [ ] Re-run after the status edit:

  ```sh
  scripts/check focused repo
  scripts/check full
  PYTHONPATH="$PWD/python" uv run --locked --offline --no-python-downloads \
    python -c 'from pathlib import Path; import hashlib; b=Path("docs/64_games.md").read_bytes(); print(hashlib.sha256(b).hexdigest())'
  ```

  If any command fails, do not leave M0 marked complete. Repair it immediately;
  a roadmap-only correction may be rerun in place. Any implementation,
  evidence, fixture, lock, or entry-document change invalidates the cloned
  candidate: restore M0 to `In progress`, create a new path-scoped candidate
  commit, and rerun the clone gate. If work cannot continue, persist the honest
  recovery state before stopping: `Needs revision — <specific failed internal
  gate>` for a code/spec/evidence defect, or `Blocked — <exact unavailable
  prerequisite>` for an external prerequisite. Update the derived header to the
  same leading state and current milestone M0, then make a path-scoped
  roadmap-only status commit. Never leave a failed tree labelled `Complete`.

- [ ] Commit the status/header transition after the post-status `full` passes;
  assert its diff names only `docs/roadmap.md`, then commit that exact path with
  path-scoped/`--only` semantics. Do not mix it with implementation or evidence
  changes or disturb unrelated index entries. The preceding candidate clone
  proves cold-start behavior, and this final local `full` proves the roadmap
  status relationship. A second clone of that status commit is optional, not
  an M0 ceremony.

**Review gate:** G1 is backed by a passing full suite and exact artifacts; M0 is
complete only in the sole status authority; a fresh checkout of the green
candidate reproduced the implementation/evidence; the final status-only change
also passes `full`; and no later milestone was guessed into existence.

**Required final checkpoint:** `Complete M0` after the candidate-clone and
post-status gates pass. Earlier commit boundaries remain flexible.
