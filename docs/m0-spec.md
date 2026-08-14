# M0 foundation and source reconnaissance specification

| Field | Value |
|---|---|
| Status | Draft for execution |
| Date | 2026-08-14 |
| Roadmap | Revision 2, M0 |
| Branch | `m0` |
| Scope | Foundation, locked inputs, identity contract, and source reconnaissance only |

## 1. Purpose and authority

This document is the executable design for M0. It turns the M0 milestone in
[`docs/roadmap.md`](roadmap.md) into an implementable, testable contract without
pulling M1 or later work forward.

Authority is deliberately simple:

1. the roadmap owns product scope, milestone order, acceptance gates, and status;
2. this document owns the M0 implementation design and temporarily carries the
   identity draft only until its owning file exists;
3. `spec/identity-v0.md`, created while executing M0, becomes the sole owner of
   the exact identity and canonical-manifest wire rules; Section 7's duplicated
   draft is removed in the same change; and
4. executable fixtures and checks prove implementations, but never silently
   redefine a specification.

If this document and the roadmap disagree, repair the roadmap first. If code and
`spec/identity-v0.md` disagree, repair the code or the specification explicitly;
never adjust expected vectors merely to make tests pass.

M0 is complete only after its checked artifacts exist and all M0 exit conditions
pass. Writing this design does not itself start or complete M0, so the roadmap
status remains `Not started` until execution begins.

## 2. Evidence behind the design

### 2.1 Repository reality

At the start of this design pass, the branch is `m0` at commit `c676055`. The
tracked repository contains only:

- `docs/roadmap.md`; and
- `docs/64_games.md`.

The short history matters because it shows what *not* to restore blindly:

- the initial README contained only a title;
- a generic 116-line `AGENTS.md` was added and then intentionally removed; and
- the current roadmap was added as the cold-start authority.

Therefore M0 creates concise, project-specific entry documents. It does not
resurrect generic process boilerplate or infer architecture from deleted
scaffolding.

### 2.2 Exact anthology baseline

The reconnaissance scan read the complete source as raw bytes. The following are
verified observations, not source grammar or chess-validity claims:

| Property | Observed value |
|---|---:|
| Path | `docs/64_games.md` |
| File kind | non-symlink regular file, mode `0644` |
| Bytes | 165,145 |
| SHA-256 | `33d44f7167ab190cc793e3fdfd8190d89ed13c1dc507c20854cf64751c7be7da` |
| Encoding | strict UTF-8, no BOM, NFC as currently stored |
| Line endings | 4,376 LF; no CRLF or bare CR; final LF present |
| Controls | no NUL, unexpected control byte, or tab |
| Exact column-zero `pgn` fences | 64 opener/closer pairs |
| Lexically recognized tag-pair lines | 895 across 21 distinct tag names |
| Movetext tokens | 7,456 lexical tokens |
| SAN-shaped tokens | 4,915; not legality-checked |
| Lexical ply range per candidate | 33–271 |
| Result markers | 39 `1-0`, 22 `0-1`, 3 `1/2-1/2`, 0 `*` |

The 21 tag names and counts are:

| Tag | Count | Tag | Count | Tag | Count |
|---|---:|---|---:|---|---:|
| `Event` | 64 | `Site` | 64 | `Date` | 64 |
| `Round` | 64 | `White` | 64 | `Black` | 64 |
| `Result` | 64 | `WhiteElo` | 18 | `BlackElo` | 18 |
| `WhiteTitle` | 1 | `BlackTitle` | 1 | `WhiteFideId` | 1 |
| `BlackFideId` | 1 | `ECO` | 63 | `Opening` | 2 |
| `EventDate` | 22 | `PlyCount` | 64 | `CriticalMove` | 64 |
| `CriticalFEN` | 64 | `FinalFEN` | 64 | `SourceCollection` | 64 |

Important source-shape findings that constrain the doctor and M1 planning:

- tag order is not uniform: seven distinct orders occur, so M0 must not freeze
  one observed tag order;
- `CriticalMove` tag values contain `!`, `!!`, and ellipsis, so scanners for SAN
  annotations and ellipsis starts must be restricted to movetext;
- movetext wraps independently of move boundaries: some lines end at a move
  number, some begin at SAN, and some contain only a result marker;
- castling, check, mate, disambiguation, and promotion shapes occur;
- comments, recursive annotation variations, numeric annotation glyphs,
  annotation suffixes, ellipsis starts, alternate starts, unfinished results,
  `0-0`, `e.p.`, `++`, and LAN/UCI-shaped moves were not observed in recognized
  movetext; punctuation with other meanings does occur in tags and outer prose;
- `SetUp`, `FEN`, and `Variant` do not occur as tag names;
- byte-exact movetext and whitespace-token projections have no duplicate
  candidates; and
- none of these lexical facts proves SAN correctness, chess legality, terminal
  correctness, score correctness, or semantic uniqueness.

The checked source-doctor report must regenerate these observations from the
locked bytes. This table is review context, not a second source of truth.

### 2.3 External-reference findings

M0 freezes exact references, not whatever a live page happens to say later.
Verification on 2026-08-14 established:

| Reference | Exact retained identity | M0 role |
|---|---|---|
| [FIDE Laws PDF, effective 2023-01-01](https://rcc.fide.com/wp-content/uploads/2022/11/Laws_of_Chess-2023.pdf) | 862,953 bytes; SHA-256 `1b46ade85c91110538c9ad2ad90fb6aba1b04125d54f5241d3cb46ef96c40f81` | future chess authority |
| [PGN guide, revised 1994-03-12](https://archive.org/download/pgn-standard-1994-03-12/PGN_standard_1994-03-12.txt) | 121,009 bytes; SHA-256 `fe892515f096e268794811ca25099acdd64ebff6dacacff90879cbaae76be961` | historical format background only |
| [NIST FIPS 180-4 PDF](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.180-4.pdf) | 833,315 bytes; SHA-256 `0455b406d89648d20cbde375561e19c245b9815e894164c2670772e3d54deb82` | SHA-256 definition |
| [NIST byte-oriented SHA vectors](https://csrc.nist.gov/CSRC/media/Projects/Cryptographic-Algorithm-Validation-Program/documents/shs/shabytetestvectors.zip) | 4,909,729 bytes; SHA-256 `929ef80b7b3418aca026643f6f248815913b60e01741a44bba9e118067f4c9b8` | independent known-answer source |

Candidate CRC/ECC references researched during planning remain in roadmap Section
16 as a later reading list. M0 does not lock them because no M0 implementation
consumes them; M2 must re-verify and retain only candidates it actually compares.

Two cautions are material:

- the selected FIDE edition is frozen by date and bytes rather than a moving
  “latest” label; and
- this M0 review identified no maintained canonical standards-body PGN grammar.
  The 1994
  guide is historical background, while `spec/source-v0.md` in M1 will be the
  project parser authority.

M0 conservatively records `redistribution = "not_established"` for external
documents unless their source supplies an explicit applicable permission. It
does not vendor the FIDE/PGN documents or the 4.9 MB NIST vector archive; only
small attributed SHA-256 test values actually consumed by M0 are retained.

The exact consumed NIST member is
`shabytetestvectors/SHA256ShortMsg.rsp`: 10,299 CRLF-preserved bytes, SHA-256
`75e1cb83994638481808e225b9eb0c1ebd0c232d952ac42b61abce6363be283c`,
CAVS 11.0, generated 2011-03-15. The fixture copies only the empty and one-byte
`d3` cases with attribution: respectively
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` and
`28969cdfa74a12c82f3bad960b0b000aca2ac329deea5c2328ebc6f2ba9802c1`.
Passing them is an informal implementation check, not NIST CAVP validation.

The existing public repository also lacks a complete per-upstream anthology
redistribution ledger. That uncertainty does not block local read-only M0/M1
analysis, but `docs/sources.md` must record it honestly. Before any further public
redistribution of the anthology or a derived collection, establish source
provenance separately from rights, then identify an applicable licence,
permission, public-domain status, or other concrete rights basis for the exact
material retained. An internal owner risk decision or a source URL is not
permission; the owner may instead remove or narrow material whose basis remains
unresolved.

### 2.4 Approaches considered

Three shapes were considered:

1. **Literal roadmap scaffolding.** Create every listed schema, future registry
   slot, decision log, build allowlist, and release report immediately. Rejected:
   most would have no consumer and would contradict the roadmap's own
   path-on-demand rule.
2. **Reconnaissance only.** Record the source hash and postpone executable
   identity work. Rejected: later milestones need a trustworthy cross-language
   byte identity before producing canonical source IR.
3. **Lean corrected foundation.** Create only entry docs, native toolchain locks,
   the identity/manifest contract and its two consumers, a pure source scanner,
   one deterministic report, and one root check. Selected.

The selected approach spends complexity at trust boundaries and nowhere else.

## 3. M0 scope

### 3.1 Required outcomes

M0 must leave the repository able to answer, mechanically:

1. What exact anthology bytes are the project starting from?
2. Which exact external references informed those choices?
3. What lexical structures actually occur in the anthology?
4. What does the doctor explicitly *not* validate?
5. How are developer identities and canonical manifests encoded?
6. Do independently written Python and Rust implementations agree?
7. Can one documented root command reproduce every M0 result?
8. Is there a credible, bounded route to clean Linux verification before M2?

### 3.2 Explicit non-goals

M0 does not:

- parse or validate chess legality;
- freeze the M1 Markdown/PGN grammar or SAN resolver;
- create canonical game bytes, semantic game IDs, or game ordinals;
- select a CRC, ECC, interleave, transport, shell, dimensions, or profile limits;
- create neutral constants without two current consumers;
- add future conformance slots;
- add a Dockerfile, `.dockerignore`, CI workflow, cache service, Nix setup, or
  cross-platform wrapper before the Linux check has a real M2 consumer;
- create `docs/decisions.md` in the absence of a roadmap-qualified decision;
- create a release-summary schema before candidate reports exist at M4;
- add a PGN library, chess library, test framework, Python formatter, task runner,
  schema framework, or documentation generator;
- modify `docs/64_games.md`; or
- claim that source provenance or redistribution rights have been resolved.

## 4. Exact M0 repository surface

Execution requires this surface. Consumed split modules, a licence file, and
roadmap-permitted disposable experiments may also exist; M0 must not create
empty future-facing placeholders merely to fill the long-term tree:

```text
AGENTS.md
README.md
.gitignore
.python-version
pyproject.toml
uv.lock
rust-toolchain.toml
Cargo.toml
Cargo.lock
docs/m0-spec.md
docs/roadmap.md
docs/sources.md
docs/64_games.md
inputs/source-lock.toml
spec/identity-v0.md
conformance/registry.toml
conformance/identity-v0.json
conformance/manifest-v0.json
python/golden_board/__init__.py
python/golden_board/canonical_manifest.py
python/golden_board/identity.py
python/golden_board/source_doctor.py
python/tests/test_foundation.py
crates/gb-foundation/Cargo.toml
crates/gb-foundation/src/lib.rs
crates/gb-foundation/tests/conformance.rs
reports/source-doctor.json
scripts/check
```

Minor source-file splitting is allowed only if a file becomes materially harder
to review; it must not introduce a generic framework or duplicate an owner.

### 4.1 Entry documents

`AGENTS.md` contains the six rules from roadmap Section 3.1, the root check
commands, and a pointer to the roadmap. It should fit on one screen.

`README.md` contains:

- the project thesis and deliberately bounded claim;
- current development status as a link to roadmap Section 13, not copied status;
- exact bootstrap versions and setup commands;
- `scripts/check fast`, focused, and full examples;
- a repository map containing only existing paths; and
- a warning that the project is pre-artifact and not yet validated.

`.gitignore` ignores only observed or immediately produced local output:

```text
.DS_Store
.venv/
__pycache__/
*.py[cod]
target/
artifacts/
```

Do not ignore checked reports, lockfiles, fixtures, or broad source patterns.

### 4.2 Python project

The Python implementation is a normal `uv` project rooted at the repository:

- `.python-version` pins `3.14.6`;
- `pyproject.toml` requires exactly Python `3.14.6` for M0;
- `[tool.uv] package = false`, so M0 needs no build backend merely to import
  three local modules;
- `uv.lock` is committed;
- runtime dependencies are empty;
- tests use `unittest` from the standard library; and
- TOML, JSON, SHA-256, Unicode, filesystem, and subprocess needs use Python's
  standard library.

`scripts/check` sets `PYTHONPATH` to the absolute repository `python/` directory
for the child process and runs the interpreter through `uv`; tests never depend
on the caller's `PYTHONPATH`. No editable/global install, user-site package, or
build backend is required at M0.

### 4.3 Rust project

The Rust workspace contains one library crate, `gb-foundation`:

- `rust-toolchain.toml` pins Rust `1.97.1`, profile `minimal`, plus `rustfmt`
  because `scripts/check` invokes it;
- the root `Cargo.lock` is committed;
- `sha2` supplies SHA-256;
- `serde_json` supplies lexical JSON machinery, with a custom visitor where
  needed to preserve duplicate-key detection and the project subset;
- `serde` is a direct dependency because that visitor imports its traits;
- `toml` is a test-only dependency used to consume the shared conformance
  registry; and
- no CLI framework, error-derivation crate, schema crate, or logging crate is
  added.

The dependency requirements selected during initialization are ordinary
compatible ranges; `Cargo.lock` records the exact resolved graph. The project
specification and fixtures, not library defaults, control accepted JSON.

Checks invoke Cargo through `rustup run 1.97.1 ...` and set `RUSTC` from
`rustup which --toolchain 1.97.1 rustc`. This keeps unrelated Homebrew Cargo and
Rust binaries earlier on `PATH` from bypassing either pin. The toolchain file
still documents the standard directory override for hosts using Rustup proxies.

The host happened to have Rust 1.94.0, but M0 deliberately selects
[Rust 1.97.1](https://blog.rust-lang.org/2026/07/16/Rust-1.97.1/): that official
point release fixes an LLVM miscompilation present since at least Rust 1.87.
Installing the project toolchain is already required, so retaining the affected
ambient version would buy no meaningful simplicity.

### 4.4 Independence boundary

Python and Rust may share only:

- `spec/identity-v0.md`;
- hand-authored conformance payloads;
- the registry that locates those payloads; and
- ordinary external SHA/JSON libraries.

They must not share generated code, generated expected outputs, a native library
binding, a subprocess call into the other implementation, or an implementation
of framing/serialization. Each test reads the same fixture independently.

The source doctor needs only one implementation at M0 because it is an
observational development tool, not an artifact-critical semantic compiler.

## 5. Bootstrap and toolchain contract

### 5.1 Declared bootstrap surface

The only ambient executables required for native M0 are:

| Tool | M0 contract |
|---|---|
| POSIX `sh` | runs `scripts/check`; no Bash-only syntax |
| Git | repository root discovery and whitespace checks; observed `2.49.0`, not byte-defining |
| `uv` | exact [`0.11.29`](https://github.com/astral-sh/uv/releases/tag/0.11.29) for the M0 lock/check environment |
| CPython | exact [`3.14.6`](https://www.python.org/downloads/release/python-3146/), selected by `.python-version` |
| Rust/Cargo | exact `1.97.1`, selected by `rust-toolchain.toml` |

The README gives a check command and an exact-version installation route for
`uv`, plus `rustup toolchain install 1.97.1 --profile minimal --component
rustfmt`. It does not auto-install software when tests run. Missing or wrong
tools produce one actionable preflight failure rather than a cascade of
secondary errors.

Host OS version, CPU, inode, absolute paths, environment variables, clocks, and
cache locations are observations, not semantic inputs. They never enter a
checked deterministic report.

### 5.2 Network and lock behavior

- setup/acquisition may use the network explicitly;
- setup uses explicit `uv sync --locked` and `rustup run 1.97.1 cargo fetch
  --locked` acquisition commands;
- ordinary checks never fetch references or rewrite a lockfile;
- Python commands use `uv run --locked --offline --no-python-downloads`;
- Rust commands select both pinned Cargo and pinned `RUSTC`, then use
  `--locked --offline`;
- a lock mismatch fails with the command needed to repair it;
- cache-hidden and network-disabled release verification is deferred to the
  concrete Linux path before M2 closes; and
- no claim of offline reproducibility is made at M0.

## 6. Locked input and source-ledger contract

### 6.1 `inputs/source-lock.toml`

The lock is hand-reviewable TOML with this conceptual shape:

```toml
schema = "golden-board.source-lock/v0"

[[source]]
id = "anthology"
role = "authoritative_input"
path = "docs/64_games.md"
bytes = 165145
sha256 = "33d44f7167ab190cc793e3fdfd8190d89ed13c1dc507c20854cf64751c7be7da"
encoding = "utf-8"
newline = "lf"

[[reference]]
id = "fide-laws-2023"
role = "normative_future_input"
title = "FIDE Laws of Chess taking effect 1 January 2023"
version = "2023-01-01"
locator = "https://rcc.fide.com/wp-content/uploads/2022/11/Laws_of_Chess-2023.pdf"
accessed = "2026-08-14"
bytes = 862953
sha256 = "1b46ade85c91110538c9ad2ad90fb6aba1b04125d54f5241d3cb46ef96c40f81"
retention = "receipt_only"
redistribution = "not_established"
```

Required entry classes are:

1. the tracked anthology;
2. the frozen FIDE rules edition;
3. the historical PGN reference;
4. FIPS 180-4 and the byte-oriented NIST vector source.

CRC/ECC candidate material is deliberately absent; M2 adds only references it
actually uses.

Rules:

- `id` values are unique lowercase ASCII kebab-case;
- tracked paths are repository-relative, contain no `..`, and resolve inside the
  repository;
- SHA-256 text is exactly 64 lowercase hexadecimal characters;
- `bytes` is an exact nonnegative integer for a fetched byte artifact;
- live HTML is not substituted for a locked PDF/text artifact;
- `role` distinguishes authority, historical background, known-answer source,
  and design precedent;
- `retention` distinguishes tracked payload, receipt only, and ignored local
  cache;
- uncertain redistribution is recorded as uncertain, never guessed;
- selected CRC/ECC/profile fields are invalid at M0; and
- tool versions, host facts, report hashes, and future semantic inputs do not
  belong in this lock.

Standard checks validate local tracked inputs and the lock's structure without
network access. Remote hashes are verified once while authoring the lock and are
not refetched on every test run.

### 6.2 `docs/sources.md`

The source ledger is prose for humans and has one compact table row per retained
source/reference:

- exact title and author/organization;
- edition/version and access date;
- stable locator and locked artifact identity;
- role in Golden Board;
- concrete conclusion supported;
- explicit non-conclusion;
- retention choice; and
- known provenance/redistribution status.

The ledger links to the lock for machine values rather than duplicating large
inventories. It explicitly says:

- the PGN guide does not define Golden Board's accepted grammar;
- CRC/ECC references remain a roadmap reading list until M2 has a real consumer;
- external references do not prove project conformance;
- no external source is fetched during ordinary checks; and
- anthology redistribution evidence remains unresolved if the owner cannot yet
  provide it.

`docs/decisions.md` is absent unless execution makes a choice in one of roadmap
Section 3.5's consequential classes. Selecting standard M0 file layout,
toolchain pins, or the already-required Docker route is recorded here and in
native files, not inflated into a decision process.

## 7. Identity and canonical-manifest contract

[`spec/identity-v0.md`](../spec/identity-v0.md) is now the sole owner of exact
framing, identity domains, the canonical-manifest data model and serialization,
resource limits, conformance fixtures, and registry rules. M0 acceptance checks
all seven topics independently in Python and Rust. Exact wire prose is not
duplicated here.

## 8. Source doctor contract

### 8.1 Trust boundary and I/O

The production CLI has no arbitrary-path default. It locates the Git worktree,
loads `inputs/source-lock.toml`, and opens the locked anthology path.

The adapter:

1. rejects an absolute path, `..`, symlink, missing path, directory, socket, or
   other non-regular input;
2. opens read-only, using no-follow support where available;
3. checks the opened descriptor with `fstat` before reading;
4. reads at most 1,048,576 bytes plus one byte, then fails if the bound is
   exceeded;
5. hashes exactly the bytes read and records whether locked size/hash match;
6. passes every safely read bounded byte string to the pure scanner even when
   its lock identity differs, so an ordinary-sized report can explain
   encoding/fence drift;
7. fails the source gate *after* scanning when locked size/hash differ; and
8. never writes beside, renames, normalizes, or repairs the source.

Only an unsafe/unreadable object (missing, non-regular, symlinked, or over the
1,048,576-byte bound) prevents scanning. In that case stdout stays empty, the
adapter prints a concise input diagnostic on stderr, and it exits nonzero rather than
pretending to have a normal doctor report. Tests assert the failure class, not
host-specific OS error wording. A lock mismatch
normally produces a candidate report on stdout with `lock_match = false`; it
cannot replace the tracked report and the check exits nonzero. A pathological
bounded input whose canonical report would exceed the manifest-v0 output limit
instead returns the deterministic `report_limit` error defined in Section 8.9
and fails the gate.

This is sufficient for an owner-controlled pet-project checkout. It does not
pretend to defend against a privileged process maliciously replacing an open file
or the repository itself.

The pure scanner accepts bytes and returns a bounded data value. It has no
filesystem, network, clock, environment, subprocess, locale, or randomness
access. Tests call the pure scanner directly with tiny synthetic cases.

### 8.2 Observation versus validation

The doctor may say:

- “64 exact fenced candidates were observed”;
- “4,915 tokens match the configured SAN-shape lexer”; or
- “no byte-exact movetext duplicates were observed.”

It may not say:

- “64 valid PGN games”;
- “all SAN is correct”;
- “all games replay legally”;
- “scores match terminal chess states”;
- “all games are semantically unique”; or
- “these are the canonical game bytes.”

M0 source checks own raw lock/encoding/fence invariants. M1's source grammar,
chess cores, and dual compilers own every syntax and semantic claim.

### 8.3 Mechanical fence model

For the checked M0 report, an exact M0-recognized opener is the six body bytes
`60 60 60 70 67 6e` (three backticks and lowercase `pgn`) followed by byte `0a`.
An exact M0-recognized closer is the three body bytes `60 60 60` followed by byte
`0a`. Both start at column zero. These names describe the current-form M0 scan;
they do not pre-empt M1's accepted source grammar.

A two-state byte-line scanner makes malformed pairing deterministic:

1. outside a candidate, an exact opener enters `inside` and remembers its span;
2. inside, an exact closer completes that candidate and returns to `outside`;
3. outside, an exact closer is an orphan-closer anomaly and changes no state;
4. inside, another exact opener is a nested-opener anomaly, remains content of
   the outer candidate, and does not reset its remembered opener; and
5. EOF while inside is an unclosed-opener anomaly.

Only completed opener/closer pairs contribute to `candidate_count` and `blocks`.
An unclosed region is scanned only for bounded raw anomalies, not as a completed
block. Indented, case-varied, longer-backtick, language-varied, CRLF-terminated,
or trailing-space fence-like lines are listed as near misses, not silently
recognized. Text outside completed candidates is not parsed as tags or movetext.

A near miss is a non-recognized physical line whose body, after removing one LF
if present, starts after zero or more spaces/tabs with a run of at least three
backticks or at least three tildes. Exact opener/closer classification takes
precedence. This includes CRLF forms because the retained CR prevents an exact
match; backticks later in ordinary prose are not fence-like.

The M0 source gate blocks exactly when the adapter cannot safely read a bounded
regular non-symlink, the observed length/hash differs from the lock, UTF-8 is
invalid, a BOM is present, any CRLF/bare-CR or missing final LF violates the
locked LF profile, an unexpected control occurs, `candidate_count != 64`, or any
orphan closer, nested opener, or unclosed opener occurs. Near misses and
tag/movetext observations do not independently block M0; they inform M1. A near
miss that also changes the locked bytes still blocks through the lock mismatch.

The doctor reports these exact current-source mechanics. M1 may deliberately
admit a slightly broader grammar, but doing so cannot retroactively change what
the M0 report measured.

### 8.4 Candidate spans

Every candidate uses zero-based half-open byte spans `[start, end)` and one-based
line numbers. For the LF current form, spans are exact:

- fence: opener start through the byte after the closer LF;
- content: byte after the opener LF through the closer start;
- tag region: every pre-separator line including each terminating LF;
- separator: the exact empty-line LF; and
- movetext: byte after the separator LF through the closer start, including the
  final movetext LF when present.

It reports:

- one-based ordinal in source encounter order, consecutive from 1 and used only
  for reconnaissance;
- opener and closer line numbers;
- complete fence span, including delimiter lines;
- inner content span;
- tag-region span;
- separator-line span;
- movetext span; and
- movetext line count; every region byte count is the difference between its
  reported span endpoints.

Span invariants are executable: nested spans are contained, adjacent regions do
not overlap, slicing the source by a reported span reproduces the scanned bytes,
and the last end never exceeds source length. A region's physical-line count is
the number of LF delimiters it contains; an unterminated final fragment, where a
synthetic malformed case has one, counts as one additional physical line. If no
exact separator exists, `separator_state` is `missing`, the separator/movetext
spans are empty arrays, the tag region is the full content span, and an anomaly
is reported. Present spans always have exactly two integers; absence is never
encoded as JSON `null`, which manifest v0 forbids.

### 8.5 Tag inventory

The first exact empty line (one LF with no preceding body byte) partitions a
completed candidate into pre-separator tag lines and post-separator movetext.
Before that separator, a tag-pair body is recognized only when its raw bytes
match:

```text
^\[([A-Za-z][A-Za-z0-9_]*) "((?:[^"\\\r\n]|\\["\\])*)"\]$
```

The first capture is the ASCII tag name. The second is the raw value; only `\"`
and `\\` are recognized escapes, each decoding to its quoted byte. A pre-separator
line that does not match is reported as malformed and does not become a tag. A
second empty line is part of movetext and is reported there. If the whole source
is not strict UTF-8, byte inventories still work but decoded scalar facts are
unavailable and the current-source gate fails.

Tag order is the exact recognized-name array before the first separator;
malformed lines are omitted from that array but reported separately. Punctuation
is measured on each raw value body: the suffix histogram increments once for the
complete terminal `[!?]+` run when present; ellipsis/question counts increment at
most once per value when it contains `...`/`?`. Escape counts are the
non-overlapping escape units recognized left-to-right by the tag grammar: `\\`
(key `backslash`) and `\"` (key `quote`).

Across completed candidates, the global report records:

- total tag lines;
- name/count and maximum decoded/raw value byte lengths;
- observed exact tag-name sequences and counts;
- duplicate tag names;
- malformed tag-like lines;
- quote/backslash escape occurrence;
- bounded punctuation aggregates by tag name and context: a histogram of the
  exact terminal `[!?]+` run, number of values containing `...`, and number of
  values containing at least one `?`, without copying values;
- `SetUp`, `FEN`, and `Variant` presence; and
- separator-line facts.

Tag values remain opaque, untrusted strings. The doctor does not treat
`PlyCount`, FEN-like tags, ratings, dates, critical moves, or collection names as
truth. It does not copy complete tag values into the report, avoiding needless
metadata replication.

### 8.6 Movetext inventory

The scanner first reports tabs, other ASCII whitespace, trailing horizontal
whitespace, and repeated spaces. A token is then a maximal nonempty byte sequence
containing neither ASCII space (`20`) nor LF (`0a`); tabs and CR therefore remain
visible in unknown tokens rather than silently acting as separators.

Classification uses these ASCII full-token patterns:

```text
move_number  ^[1-9][0-9]{0,19}\.$ with numeric value <= u64::MAX
result       ^(1-0|0-1|1/2-1/2|\*)$
castle       ^O-O(?:-O)?[+#]?$
piece        ^[KQRBN](?:[a-h]|[1-8]|[a-h][1-8])?x?[a-h][1-8][+#]?$
pawn_capture ^[a-h]x[a-h][1-8](?:=[QRBN])?[+#]?$
pawn_quiet   ^[a-h][1-8](?:=[QRBN])?[+#]?$
```

Each token has exactly one primary class in this precedence: move number, result,
castle, piece, pawn capture, pawn quiet, unknown. Orthogonal feature counters may
overlap: for example `exf1=Q+` is a pawn capture and also increments capture,
promotion, and check. Piece disambiguation is separately classified as file,
rank, or full-square from the optional bytes between the piece letter and `x` or
destination. `O-O` and `O-O-O` are counted separately.

`lexical_ply_count` is the count of tokens whose primary class is castle, piece,
pawn capture, or pawn quiet, irrespective of move-number correctness. Its final
slot is `white` for an odd count, `black` for an even nonzero count, and `none`
for zero; this is parity terminology only, not verified side-to-move. Move-number
sequence facts restart in each candidate and compare recognized number tokens in
encounter order to `1, 2, ...`; they do not use SAN to repair gaps. A longer or
out-of-range decimal token is `unknown`, so the scanner never constructs an
unbounded integer. Line-wrap facts count each physical movetext line by the
report class of its first and last token. Castle, piece, pawn-capture, and
pawn-quiet primary classes map to `san`; move-number, result, and unknown retain
their names; a line with no tokens maps to `empty` for both ends and increments
`empty_lines`.

Line counters are byte-defined: `tab_lines` counts movetext lines containing at
least one tab; `repeated_space_lines` counts lines containing `20 20`; and
`trailing_horizontal_whitespace_lines` counts lines whose body ends in at least
one space or tab. Each is a per-line presence count. Feature counters are also
per recognized SAN-shaped token: `capture` sees `x`, kingside/queenside use the
two castle bases, `check`/`mate` use the terminal `+`/`#`, promotion sees `=`, and
piece quiet/capture and disambiguation come from the named piece-pattern groups.

Construct scans are also movetext-only and byte-exact: braces, parentheses,
any `;` byte, `(?m)^%`, `\$[0-9]+`, token-final `[!?]+`, token containing
`...`, token containing `0-0`, exact token `e.p.` or `ep`, token containing `++`,
UCI shape `^[a-h][1-8][a-h][1-8][qrbn]?$`, and LAN shape
`^[KQRBN]?[a-h][1-8][-x][a-h][1-8](?:=[QRBN])?[+#]?$`. These scans inventory
suspicious forms; they do not assert PGN invalidity.

All five `*_byte` construct keys count matching byte occurrences; `escape_line`
counts physical lines whose first body byte is `%`;
`nag` counts non-overlapping `\$[0-9]+` matches. Every `*_token` construct key
counts each token satisfying its predicate above once, even if the triggering
substring occurs more than once in that token.

The doctor records:

- total tokens and token byte-length range;
- standalone move-number tokens, their value range, sequence anomalies, and
  line-wrap positions;
- lexical SAN-shape categories: pawn quiet/capture, piece quiet/capture,
  disambiguation, castling, promotion, check, and mate suffixes;
- final result-token counts and lexical agreement with the `Result` tag;
- unknown tokens with bounded token/count examples;
- movetext-only occurrences of braces, semicolon bytes, parentheses,
  numeric annotation glyphs, annotation suffixes, ellipsis starts, `0-0`,
  `e.p.`, `++`, LAN/UCI-shaped forms, and `*`;
- candidate movetext byte/line/token/lexical-ply ranges; and
- lexical final-slot parity, without claiming chess side-to-move.

The shape lexer is anchored and linear. It does not resolve pieces, infer board
state, interpret `+`/`#`, or repair notation. Counts of “ply” are explicitly
labelled lexical.

`result_agreement` is `match` only when exactly one recognized `Result` tag
exists, exactly one result token exists, that token is final, and their decoded
value bytes match. It is `mismatch` when those singleton/final conditions hold
but bytes differ, and `indeterminate` otherwise, including when strict UTF-8
decoding is unavailable. The report gives tag/token
agreement-state totals and global final-token totals; it never chooses among
duplicate tags or multiple markers.

### 8.7 Duplicate candidates

The doctor reports groups with two or more equal projections under:

1. byte-exact movetext spans, including the final LF where present; and
2. the exact byte-token arrays produced by Section 8.6's space/LF tokenizer.

It does not remove move numbers, normalize SAN, replay moves, compare positions,
or use metadata. An empty duplicate list means only that no duplicate was found
under those two named projections.

### 8.8 Deterministic report

`reports/source-doctor.json` is serialized with the canonical-manifest v0
serializer. The following type notation is normative: `u64`, `bool`, and
`string` mean manifest-v0 scalars; `[T]` is an array; `{...}` is an object with
exactly the named keys; `span` and `range` are either `[]` or exactly two `u64`
values. A present span is `[start, end]` with `start <= end`; a nonempty range is
`[minimum, maximum]`. Extra keys and wrong types reject.

All source-derived samples use one shape:

```text
sample = {
  byte_length: u64,       # full observed fragment length
  byte_start: u64,        # zero-based offset in the source
  bytes_hex: string,      # lowercase hex of the first at most 256 bytes
  kind: string,           # closed category named by the parent inventory
  line: u64,              # one-based physical line
  region: string,         # outer_markdown|fence|tags|separator|movetext
  sha256: string,         # digest of the full observed fragment
  truncated: bool
}

sampled = {
  count: u64,             # total occurrences, including omitted examples
  examples: [sample],
  omitted_count: u64      # count - length(examples)
}

histogram_entry = { count: u64, key: string }
```

The report is exactly:

```text
{
  blocks: [block],
  duplicate_candidates: {
    raw_movetext: [duplicate_group],
    token_sequence: [duplicate_group]
  },
  fences: {
    candidate_count: u64,
    near_misses: sampled,
    nested_openers: sampled,
    orphan_closers: sampled,
    recognized_closers: u64,
    recognized_openers: u64,
    unclosed_openers: sampled
  },
  movetext: {
    constructs: [histogram_entry],
    feature_counts: {
      capture: u64,
      castle_kingside: u64,
      castle_queenside: u64,
      check: u64,
      disambiguation_file: u64,
      disambiguation_rank: u64,
      disambiguation_square: u64,
      mate: u64,
      piece_capture: u64,
      piece_quiet: u64,
      promotion: u64
    },
    final_slot_counts: { black: u64, none: u64, white: u64 },
    line_wrap: {
      empty_lines: u64,
      first_class: [histogram_entry],
      last_class: [histogram_entry],
      repeated_space_lines: u64,
      tab_lines: u64,
      trailing_horizontal_whitespace_lines: u64
    },
    move_numbers: {
      count: u64,
      sequence_anomalies: sampled,
      value_range: range
    },
    primary_counts: {
      castle: u64,
      move_number: u64,
      pawn_capture: u64,
      pawn_quiet: u64,
      piece: u64,
      result: u64,
      unknown: u64
    },
    ranges: {
      candidate_bytes: range,
      content_bytes: range,
      lexical_ply: range,
      movetext_bytes: range,
      movetext_lines: range,
      tokens_per_candidate: range
    },
    result_agreement_counts: {
      indeterminate: u64,
      match: u64,
      mismatch: u64
    },
    result_counts: {
      black_win: u64,
      draw: u64,
      unfinished: u64,
      white_win: u64
    },
    token_bytes: range,
    total_tokens: u64,
    unknown_tokens: sampled
  },
  schema: string,
  scope: string,
  source: {
    bom: bool,
    expected_bytes: u64,
    expected_sha256: string,
    file_kind: string,
    final_lf: bool,
    line_endings: { bare_cr: u64, crlf: u64, lf: u64 },
    lock_match: bool,
    nfc_state: string,
    observed_bytes: u64,
    observed_sha256: string,
    path: string,
    symlink: bool,
    tab_count: u64,
    trailing_horizontal_whitespace: [region_samples],
    unexpected_controls: sampled,
    utf8_valid: bool
  },
  tags: {
    duplicate_blocks: duplicate_blocks,
    escape_counts: { backslash: u64, quote: u64 },
    malformed_lines: sampled,
    name_stats: [tag_name_stat],
    orders: [tag_order],
    punctuation: [tag_punctuation],
    recognized_lines: u64,
    separator_states: { missing: u64, present: u64 },
    special_name_counts: { FEN: u64, SetUp: u64, Variant: u64 }
  }
}
```

The named compound types are exactly:

```text
block = {
  closer_line: u64,
  content_span: span,
  fence_span: span,
  lexical_final_slot: string,
  lexical_ply_count: u64,
  movetext_lines: u64,
  movetext_span: span,
  opener_line: u64,
  ordinal: u64,
  raw_movetext_sha256: string,
  result_agreement: string,
  separator_span: span,
  separator_state: string,
  tag_count: u64,
  tag_span: span,
  token_count: u64,
  token_projection_sha256: string
}

duplicate_group = { ordinals: [u64], projection_sha256: string }
region_samples = { count: u64, examples: [sample], omitted_count: u64,
                   region: string }
duplicate_block_example = { block: u64, names: [string] }
duplicate_blocks = { count: u64, examples: [duplicate_block_example],
                     omitted_count: u64 }
tag_name_stat = { count: u64, decoded_value_bytes_max: u64,
                  decoded_values_valid: bool, name: string,
                  raw_value_bytes_max: u64 }
tag_order = { count: u64, first_ordinal: u64, names: [string] }
tag_punctuation = { ellipsis_value_count: u64, name: string,
                    question_value_count: u64,
                    suffixes: [histogram_entry] }
```

Fixed strings are:

- `schema = "golden-board.source-doctor/v0"`;
- `scope = "lexical_observation"`;
- `file_kind = "regular"` and `symlink = false` for every normal report;
- `nfc_state` is `valid_nfc`, `valid_non_nfc`, or `unavailable`;
- `separator_state` is `present` or `missing`;
- `lexical_final_slot` is `white`, `black`, or `none`;
- `result_agreement` is `match`, `mismatch`, or `indeterminate`;
- line-wrap histogram keys are exactly `empty`, `move_number`, `result`, `san`,
  and `unknown`, following the mapping in Section 8.6; and
- `constructs` contains, in ASCII-key order and even when zero, exactly
  `annotation_suffix_token`, `brace_close_byte`, `brace_open_byte`,
  `double_check_token`, `ellipsis_token`, `en_passant_text_token`,
  `escape_line`, `lan_token`, `nag`, `parenthesis_close_byte`,
  `parenthesis_open_byte`, `semicolon_byte`, `uci_token`,
  `unfinished_result_token`, and `zero_castling_token`.

`expected_*` values come from `source-lock.toml`; `observed_*` values come from
the opened bytes. `path` is the locked repository-relative anthology path.
`lock_match` is equality of both byte length and digest. LF is
an `0a` not immediately preceded by `0d`; CRLF counts non-overlapping `0d 0a`
pairs; bare CR is an `0d` not followed by `0a`. `unexpected_controls` counts each
byte in `00..08`, `0b`, `0c`, `0e..1f`, or `7f`; tabs are counted separately.

For an invalid UTF-8 source, `utf8_valid = false`, `nfc_state = "unavailable"`,
and byte inventories remain populated. For a tag name whose recognized raw values
do not all decode after the two permitted escape substitutions,
`decoded_values_valid = false` and `decoded_value_bytes_max = 0`. Otherwise the
maximum is over decoded UTF-8 byte lengths. A block with no separator has empty
separator/movetext spans, zero movetext counts, the SHA-256 of empty bytes for its
raw movetext digest, and the SHA-256 of `u32_be(0)` for its empty token
projection.

Each complete candidate contributes one `block`. `tags` and `movetext` are global
aggregates over completed candidates only. In a duplicate group,
`projection_sha256` hashes exactly the raw movetext span or the token projection
`u32_be(token_count) || concat(u32_be(len(token)) || token)` respectively; this
hash groups candidates but is not a canonical game identity. A group is emitted
only after equal hashes are confirmed by direct projection equality.

`candidate_bytes`, `content_bytes`, and `movetext_bytes` are respectively the
lengths of `fence_span`, `content_span`, and `movetext_span`; the remaining
candidate-derived ranges (`candidate_bytes`, `content_bytes`, `lexical_ply`,
`movetext_bytes`, `movetext_lines`, and `tokens_per_candidate`) use their
like-named block values and are empty exactly when there are no completed
candidates. `token_bytes` is empty exactly when there are no tokens;
`move_numbers.value_range` is empty exactly when there are no recognized
move-number tokens. `result_counts` counts recognized result tokens only when
they are the final token of their candidate and maps `1-0`,
`0-1`, `1/2-1/2`, and `*` to `white_win`, `black_win`, `draw`, and `unfinished`.
`recognized_openers` and `recognized_closers` count every exact delimiter line,
including a delimiter observed in the wrong scanner state.

Every field named `sha256` or ending `_sha256` is exactly 64 lowercase
hexadecimal characters. Every `bytes_hex` value is lowercase, has even length,
and decodes to the exact retained prefix described by its sample.

The five `trailing_horizontal_whitespace` entries always appear in this order:
`outer_markdown`, `fence`, `tags`, `separator`, `movetext`. This distinction is
required because the current file has 192 outer-Markdown lines ending in two
spaces and none in fenced PGN content.

Every ordering/truncation rule is fixed:

- blocks sort by `ordinal`; duplicate-group ordinals sort numerically, and groups
  sort by their first ordinal then full ordinal array;
- sample occurrences sort by `(byte_start, byte_length, kind, bytes_hex)`; retain
  the first 32 and set `omitted_count = count - length(examples)`;
- a sample's `bytes_hex` is the first `min(byte_length, 256)` source bytes and
  `truncated` is exactly `byte_length > 256`;
- histogram entries, tag-name stats, tag punctuation, and named construct entries
  sort by raw ASCII `key`/`name`; suffix histograms contain only observed nonzero
  suffixes;
- tag orders sort by `first_ordinal` and store the full name arrays rather than a
  hash; `first_ordinal` is the first block using that sequence;
- duplicate-block examples sort by block then ASCII tag name, retain the first 32
  blocks, and sort each `names` array by ASCII bytes; and
- fixed-key histograms include every named key with zero where absent.

For `sampled`, `count` counts occurrences, not distinct byte strings. A parent
sets every example's `kind` to its own singular key (`near_miss`,
`nested_opener`, `orphan_closer`, `unclosed_opener`, `unexpected_control`,
`trailing_horizontal_whitespace`, `malformed_tag`,
`move_number_sequence_anomaly`, or `unknown_token`). This prevents free-form
diagnostic labels from entering the checked report.

The sampled fragment is exact for every category:

- fence near miss, nested opener, orphan closer, or unclosed opener: the complete
  physical line, including its line terminator when present; the unclosed sample
  is the opener line, not the remaining region;
- unexpected control: the single offending byte;
- trailing horizontal whitespace: the maximal nonempty run of space/tab bytes
  immediately before that physical line's terminator or EOF;
- malformed tag: the complete pre-separator physical line, including its line
  terminator when present;
- move-number sequence anomaly: the complete recognized move-number token that
  differs from the next expected value; and
- unknown token: the complete token from Section 8.6.

`byte_start`, `byte_length`, `bytes_hex`, and `sha256` all describe that fragment.
`line` is the one-based physical line containing its first byte. `region` is
`fence` for an exact delimiter or fence-like near-miss line; otherwise a fragment
inside a completed candidate uses the `tags`, `separator`, or `movetext` span
that contains its first byte, and everything else is `outer_markdown`. In a
`region_samples` entry, every example's region equals the parent `region`.

The closed nested field allowlist structurally prevents canonical game bytes,
resolved moves/positions, legality, semantic score status, or semantic identity
from entering M0 evidence. Both language implementations validate the report as
a canonical manifest; the source-focused test additionally validates this exact
lexical-only shape.

All samples that may contain arbitrary bytes use lowercase hex, length, and
SHA-256, never replacement-decoded text. The report contains no timestamp,
hostname, username, absolute path, inode, device, mtime, process ID, random ID,
elapsed time, tool version, or unordered map output.

The generation command writes to stdout. The source-focused Python harness uses
the pinned standard library's `tempfile.TemporaryDirectory`, captures the output
there, and compares it byte-for-byte with the tracked report inside the context.
The report is updated only by an explicit authoring command documented in the
README; an interrupted generation cannot truncate the tracked report.

### 8.9 Scanner bounds

The input and normal report share one 1,048,576-byte ceiling—over six times the
current anthology size. Every possible line, candidate, tag, and token count is
therefore already bounded by input length; M0 does not invent separate arbitrary
document ceilings. Stored anomaly examples are capped at 32 per category and 256
bytes per example, with total count and omitted count retained. Oversized example
text is represented by byte length and SHA-256 rather than copied in full.

A normal report must fit canonical manifest v0's 1,048,576-byte output limit.
The builder starts with the canonical size of the empty schema and charges the
serialized contribution of each finalized block, distinct tag/order entry,
duplicate group, punctuation entry, and sample before retaining it. If the next
entry cannot fit, it returns `report_limit` immediately; count digit growth and
all fixed fields are checked again by the final serializer. The serializer counts
bytes while emitting into a temporary result. On the first would-exceed event it
discards that result and returns exactly this canonical manifest instead:

```json
{"error":"report_limit","limit":1048576,"schema":"golden-board.source-doctor-error/v0"}
```

The shown value has exactly one terminal LF. It is a deterministic blocking
error, not a partial report, and cannot replace the checked current-source
report. This single ceiling also bounds cardinality-amplifying block, tag-order,
tag-name, punctuation, and duplicate arrays without separate arbitrary caps.

The scanner is a single bounded pass plus bounded hashing/sorting of compact
inventories. Regular expressions, if used, are anchored/linear and must not have
input-dependent catastrophic backtracking. Duplicate comparison hashes the named
projection and confirms byte equality before reporting a group.

## 9. Root check contract

`scripts/check` is one portable POSIX-shell dispatcher. It does not implement
product logic; it only validates arguments, performs tool preflight, and invokes
project commands.

### 9.1 Interface

```text
scripts/check fast
scripts/check focused source
scripts/check focused identity
scripts/check focused repo
scripts/check full
```

- no argument is a usage error; callers name the intended cadence explicitly;
- unknown mode, missing focused area, extra arguments, or unknown area exits 2
  after printing usage;
- a failed check or prerequisite exits 1;
- success exits 0;
- the first failure stops the run and names the failing area/command; and
- output is concise terminal text, not a premature evidence schema.

### 9.2 Areas

`focused identity`:

- validates registry and fixture hashes;
- runs Python and Rust framing/SHA identity tests;
- runs all valid, noncanonical, invalid, and boundary fixtures independently in
  Python and Rust;
- verifies canonical fixture files themselves; and
- compares every shared identity and canonical-manifest result.

`focused source`:

- validates the source-lock schema and the local anthology descriptor/bytes;
- runs pure-scanner unit/adversarial cases;
- generates the current report once and byte-compares it with the tracked report;
- verifies all report span/ordering/non-claim invariants; and
- verifies the source bytes/hash are unchanged after the run.

`focused repo`:

- runs `sh -n scripts/check`;
- runs `cargo fmt --check`;
- runs `git diff --check --` scoped to M0-owned paths without requiring a clean
  worktree;
- validates required paths and forbids dangling conformance entries;
- verifies the roadmap's derived header/status relationship;
- verifies README/AGENTS links and commands name existing targets; and
- rejects only known empty/placeholder M0 deliverables; it does not impose a
  closed repository allowlist.

`fast` performs preflight, the repo area, source-lock/current-source invariants,
and the ordinary Python/Rust unit and conformance tests. It skips the larger
source mutation set and repeated report generation.

`full` performs all three focused areas once in a nonduplicative order. The source
area's fresh output must be byte-identical to the tracked report; pure-scanner
unit cases establish repeat-call determinism without a redundant second full-file
generation. With warm caches the suite should remain comfortably small enough
for routine local use; no timing threshold is an acceptance gate.

### 9.3 Check implementation constraints

- all Python invocations use `uv run --locked --offline
  --no-python-downloads`;
- all Cargo invocations use `rustup run 1.97.1`; compiler invocations set
  `RUSTC` from the same toolchain; dependency-resolving commands add `--locked
  --offline`, while `cargo fmt` (which accepts neither lock flag) runs only the
  pinned `rustfmt` component;
- ordinary checks do not mutate lockfiles, checked reports, source, or status;
- ordinary checks make no network request;
- any temporary path is owned and cleaned by pinned Python's
  `tempfile.TemporaryDirectory`; the shell does not add an undeclared `mktemp`
  or cleanup-utility dependency;
- tests do not depend on locale, local timezone, current date, hash-map order, or
  CPU count;
- a dirty worktree is allowed; only M0-owned checked-byte drift fails; and
- no check auto-fixes formatting or rewrites fixtures.

## 10. Clean Linux path

M0 records and verifies the mechanism but does not add its build files yet.

### 10.1 Chosen mechanism

- engine: Docker/OCI container;
- current verified engine: Docker `25.0.3`, Linux daemon on `linux/arm64`;
- architecture-native container platform: `linux/arm64` on the Apple Silicon
  host, avoiding unnecessary x86 emulation;
- base image starting point:
  `debian:13-slim@sha256:3a39a0592364683e6bab97937b72cad5a8fa6dcbbee90edb3bb48c7f8e94f258`;
- required verification mode: container networking disabled, no mounted mutable
  host/global language-package caches, and a clean checkout copied into a
  disposable writable container directory so `.venv`, `target`, and bytecode
  never touch the host; only the immutable dependency/tool acquisition bundle
  baked into the verifier image is visible; and
- deadline: demonstrated and checked before M2 freezes a transport/wire
  candidate.

The multi-architecture digest and target platform are both recorded so a host
does not silently resolve a different image. A future base refresh is build
provenance, not semantic identity, but reruns clean checks.

### 10.2 M2 implementation shape

When M2 has a real consumer, add only:

- `tools/linux/Dockerfile` pinned by digest;
- `.dockerignore` as a positive minimal context contract;
- an explicit acquisition/build command that verifies downloaded tool payloads
  and produces a local verifier image; and
- `scripts/check linux`, which runs the same root `full` command with
  `--network none`, no host caches, and only the image-baked immutable
  acquisition bundle.

The verifier image is the local acquisition bundle: its network-enabled build
populates and configures an image-internal Cargo registry/source cache and any
Python payloads required by the lock, records their identities, and proves the
later `--offline` commands resolve solely from those immutable layers. The actual
verification container runs offline. Do not add Docker/Podman
abstraction, Nix, a VM, or a CI matrix unless this single path proves unusable.

### 10.3 Blocker semantics

M0 records one of:

- `verified`: daemon was reached and platform/base resolution was demonstrated;
  or
- `blocked`: exact failing command, error, owner action, and M2 deadline.

A sandbox denying daemon access is not evidence that Docker is absent. Verification
must be performed from the owner-controlled host context. The current host check
established `verified`, so no Linux blocker is carried into M0 execution.

## 11. Failure behavior and security posture

This is a public pet project, not an adversarial multi-tenant service. The design
uses cheap protections at real trust boundaries and declines enterprise ceremony.

| Condition | Required behavior |
|---|---|
| Source missing, symlinked, non-regular, or too large | fail safely before content scanning |
| Safely readable source has a size/hash mismatch | emit bounded observations with `lock_match = false`, then fail the source gate |
| Lock malformed, duplicated, path-escaping, or containing an M0-forbidden selection | fail with a stable check category plus entry ID/field in human diagnostics; do not guess |
| Invalid UTF-8/BOM/newline anomaly | doctor can report raw facts; current-source gate fails |
| Wrong exact-candidate count or orphan, nested, or unclosed exact fence | report bounded anomaly and fail the current exact-fence gate; near misses remain observations unless another locked-byte invariant fails |
| Unknown movetext token | inventory as lexical unknown; do not repair or interpret |
| Canonical JSON duplicate key or unsupported value | reject in both languages |
| Identity length/count overflow | reject before allocation or truncation |
| Both implementations agree on a wrong expected vector | independent NIST KAT plus human preimage/manifest spot checks must also pass; agreement alone cannot close M0 |
| Fixture expectation differs from both implementations | investigate spec/fixture first; never majority-vote |
| Python and Rust disagree | M0 remains open until the cause is resolved |
| Report generation is interrupted | tracked report remains unchanged |
| Tool/lock version drifts | preflight/locked command fails with repair guidance |
| Remote reference disappears | local checks still pass against the receipt; ledger marks retrieval risk |
| Reference edition changes upstream | no silent update; add/replace a locked entry explicitly |
| Anthology provenance/rights basis remains unknown | record the limitation; local read-only M0/M1 analysis may continue, but do not further redistribute the affected collection publicly without a documented concrete rights basis; an owner risk decision alone is not permission |
| Pathological bounded input would produce a report over 1,048,576 bytes | return the exact `report_limit` error and fail; never emit or accept a partial report |

Untrusted repository text is data. The doctor never executes tag values,
movetext, Markdown, URLs, filenames found inside source text, or generated strings.
No shell command is built from source content.

## 12. Implementation sequence

The sequence keeps every intermediate state coherent without requiring a large
scaffold:

1. Set roadmap M0 to `In progress`, refresh the derived header, and verify the
   simple status relationship manually before the check exists.
2. Add concise `AGENTS.md`, README, `.gitignore`, and native toolchain pins.
3. Initialize the no-dependency Python project and one-crate Rust workspace;
   generate and commit lockfiles.
4. Promote Section 7 into `spec/identity-v0.md`, replace the duplicated wire
   draft here with its link/checklist, and author identity/manifest fixtures.
5. Implement Python and Rust identity/canonical-manifest paths independently;
   make the focused identity check pass.
6. Create `inputs/source-lock.toml` and `docs/sources.md` from the verified
   receipts; validate them locally without network.
7. Implement the pure Python source scanner and thin locked-path adapter with
   synthetic adversarial tests.
8. Generate `reports/source-doctor.json` explicitly, review it against the known
   baseline, then make regeneration comparison pass.
9. Finish `scripts/check` modes and repo/status consistency checks.
10. Run every focused area, `fast`, and `full` from the documented setup.
11. Review the diff for speculative paths, accidental source modifications,
    generated-fixture circularity, and overstated claims.
12. Only after all exit evidence passes, update roadmap M0 to
    `Complete — <date>; scripts/check full; <report/registry identities>`, update
    the derived header to M1/In progress, and rerun `full`.

The status update is the last semantic M0 change. No report embeds the commit or
its own hash, so there is no self-reference cycle.

## 13. Verification and adversarial test matrix

### 13.1 Locked file/path cases

Tests use temporary files/directories and cover:

- exact source succeeds;
- missing source;
- empty source;
- directory, FIFO/socket where portable, and symlink input;
- relative path escape and absolute path in a mutated lock;
- one-byte append, deletion, and replacement with same byte length;
- lock size correct/hash wrong and hash correct/size wrong;
- uppercase, short, long, or non-hex digest text;
- duplicate source/reference IDs;
- source just below, at, and above 1,048,576 bytes without committing large
  fixtures; and
- source remains byte-identical after every success/failure path.

### 13.2 Encoding/newline cases

- empty bytes, ASCII, valid multibyte UTF-8, and current non-ASCII source text;
- UTF-8 BOM;
- invalid continuation, overlong form, surrogate encoding, and truncated scalar;
- LF, CRLF, mixed LF/CRLF, and bare CR;
- missing final newline;
- NUL and every unexpected C0 control class; and
- tab/trailing spaces inside and outside fenced content, distinguished in report.

### 13.3 Fence/region cases

- 0, 1, 63, 64, and 65 exact M0-recognized candidates;
- opener without closer and closer without opener;
- nested opener, adjacent candidates, empty content, and empty movetext;
- uppercase `PGN`, indentation, trailing spaces, four backticks, tilde fences,
  and other language labels as near misses;
- backtick-looking prose outside a candidate;
- CRLF line offsets in a synthetic observation even though the current lock gate
  requires LF;
- first/last-byte span boundaries and multibyte text before a fence; and
- slicing every reported span exactly reproduces its source segment.

### 13.4 Tag/movetext cases

- no tags, malformed tag, duplicate tag, escaped quote/backslash, one synthetic
  tag-order permutation, and verification of all seven actual-source orders;
- `SetUp`, `FEN`, and `Variant` inventory without interpreting their values;
- annotation punctuation in tag values does not count as movetext annotation;
- move number and SAN separated by line wrapping;
- result-only final line;
- each observed SAN lexical shape, unknown token, comments, RAV, NAG,
  annotation, ellipsis start, unfinished result, and trailing token;
- identical raw movetext, identical token stream with different whitespace, and
  superficially similar but byte-distinct movetext;
- result tag/marker lexical match and mismatch; and
- a maliciously long line/token remains bounded by the 1,048,576-byte document
  cap,
  truncates stored examples, and does not trigger catastrophic regex behavior;
  and
- a fence-dense or unique-tag-dense input that would exceed the report ceiling
  returns the exact `report_limit` error rather than a partial report.

### 13.5 Identity cases

- domain difference, field-order difference, field-boundary ambiguity attempts,
  empty list versus empty field, and binary/non-UTF-8 fields;
- exact big-endian byte examples for each primitive;
- count/length maxima in arithmetic helpers and one-over rejection;
- lowercase fixed-width digest output;
- the official empty/one-byte-`d3` SHA answers in both language libraries; and
- fixture expected outputs remain read-only during tests.

### 13.6 Manifest cases

The cases in Section 7.6 run through both implementations. Additional
metamorphic checks assert:

- serializing a parsed canonical manifest returns exactly the original bytes;
- serialization is idempotent;
- source object insertion order cannot affect bytes;
- swapping unequal array values usually changes bytes but never reorders them;
- NFC and NFD stay distinct;
- adding insignificant whitespace makes canonical validation fail;
- every accepted output is strict UTF-8 with exactly one terminal LF; and
- parsing/serialization never consults locale or float conversion.

### 13.7 Determinism and orchestration cases

- repeated pure-scanner/report serialization calls over the same bytes are
  identical, and one fresh full-source generation equals the tracked report;
- changing timezone, locale variables, and working directory leaves output
  identical;
- report and registry maps are explicitly sorted;
- `fast`, every valid focused area, and `full` exit zero on the checked state;
- missing/unknown/extra CLI arguments exit 2;
- deliberately failed child command propagates nonzero;
- checks work with unrelated uncommitted changes and do not modify them;
- offline flags prevent dependency retrieval after the documented acquisition
  step; actual network isolation is exercised by the M2 container; and
- README command snippets correspond to real accepted invocations.

## 14. M0 exit traceability

| Roadmap M0 requirement | Concrete evidence |
|---|---|
| Fresh checkout identifies and validates real source | source lock, descriptor checks, focused source tests |
| Exactly 64 fenced candidates and complete reconnaissance | deterministic doctor report plus lexical/anomaly tests |
| No canonical game bytes or semantic overclaim | lexical-only report field allowlist, dependency boundary, and review assertions |
| Python/Rust identity agreement | hand vectors consumed independently by both suites |
| Python/Rust canonical manifest agreement | valid/reject/boundary fixture parity |
| Real fast/focused/full commands | CLI contract and successful executions |
| No false future selection | source-lock allowlist and forbidden-artifact repo checks |
| No stale hand-copied source statistics | regenerated tracked report bound to locked hash |
| References and limitations are immutably identified | source lock plus human ledger |
| Clean Linux path is concrete | verified Docker mechanism, pinned base digest, M2 deadline |
| G1 is evidence-backed | `scripts/check full`, lock/ledger, report, registry, dual suites |

M0 may be marked complete only when every row has executable evidence and the
final clean diff contains no unexplained generated or future-facing file.

## 15. Deliberate deferrals

These are not omissions to “fill in later”; they have named owners:

| Deferred fact/artifact | Owner/deadline |
|---|---|
| Exact Markdown/PGN/SAN accepted grammar | M1 `spec/source-v0.md` |
| Chess semantics, replay, score consistency, semantic duplicates | M1 dual cores/compilers |
| Shared neutral constants schema | first milestone with two real constant consumers, expected M1 |
| Selected CRC/ECC/check/interleave/shell/profile | M2 measured selection |
| Dockerfile and build-context allowlist | before M2 profile freeze |
| Cache-hidden/network-disabled clean verification | clean Linux check before M2 closes |
| Canonical game/content/bitplane identities | owning M1–M4 specifications |
| Release summary | M4 when candidate acceptance reports exist |
| Hosted CI | optional when public automation has demonstrated value |
| Anthology provenance and concrete rights basis | before any further public redistribution; an owner risk decision alone is insufficient, and the issue must not silently wait for M6 |

No M0 file contains placeholder values for these facts.

## 16. Review checklist

Before execution begins, reviewers should be able to answer yes to all of these:

- Is every M0 deliverable consumed by an M0 check or reader?
- Is every byte-affecting rule stated without relying on Python/Rust defaults?
- Can malformed/untrusted source text be observed without being executed or
  promoted to chess truth?
- Can the doctor report be reproduced without network, time, host, or path noise?
- Can one implementation be wrong without generating the other's expected data?
- Are current source observations clearly separated from M1 validity claims?
- Are external references locked precisely while licensing uncertainty remains
  honest?
- Are selected transport/ECC/CRC/profile facts absent?
- Is the clean Linux plan specific enough to execute but not prematurely built?
- Does failure block the relevant gate instead of inviting silent repair?
- Is the total foundation still understandable by one maintainer without a
  governance layer?

There are no unresolved design questions required to begin M0. New evidence may
amend this document, but an amendment must remain within M0 or update the roadmap
owner first.
