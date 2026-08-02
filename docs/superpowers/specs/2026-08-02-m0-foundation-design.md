# M0 Foundation and Source Reconnaissance Design

| Field | Value |
|---|---|
| Status | Approved for implementation |
| Date | 2026-08-02 |
| Roadmap authority | docs/roadmap.md, revision 1 |
| Milestone | M0 — Foundation and source reconnaissance |
| Branch | m0 |
| Design role | Non-normative execution design |

## 1. Authority and interpretation

docs/roadmap.md is the normative authority. It owns the product mission,
scope, milestone order, acceptance wording, and mutable project status. This
design translates M0 into concrete repository work; it does not amend the
roadmap or become a second owner of product semantics.

If this design conflicts with the roadmap, the roadmap wins. Any discovered
normative ambiguity must be resolved in the smallest owning specification
before affected implementation continues.

The current repository is a deliberate cold start. At design time it contains
only:

- docs/roadmap.md;
- docs/64_games.md; and
- this approved design document.

Historical deleted files are not active guidance. In particular, the generic
AGENTS.md deleted before the roadmap was introduced must not be restored.

Writing this design does not start or complete M0. M0 execution begins when
Section 13 of the roadmap is changed to In progress and its derived header is
updated consistently.

## 2. M0 outcome

M0 creates the smallest safe foundation that can:

1. identify the exact anthology input from a fresh checkout;
2. report the anthology's observed source shape without producing canonical
   game bytes;
3. freeze developer identity framing and canonical manifest bytes;
4. prove those identity and manifest rules independently in Python and Rust;
5. lock the external references and local toolchain facts that actually exist;
6. expose real fast, focused, and full root checks;
7. establish project-local dependency management and clean-cache verification;
8. define compact deterministic M0 evidence and report formats; and
9. record a concrete clean-Linux path that must become operational before M2
   freezes a transport candidate.

M0 closes only when every exit condition in roadmap Section 11.2 and G1 has
machine-verifiable evidence. Prose, anthology metadata, prior claims of legal
replay, branch names, or unregenerated statistics cannot close the milestone.

## 3. Scope boundaries

### 3.1 M0 work

M0 may:

- add the repository, toolchain, check, lock, fixture, and report foundations
  explicitly required by the roadmap;
- define developer identity preimages and canonical JSON;
- inspect the exact raw anthology bytes through a bounded read-only doctor;
- record candidate references for later integrity and recovery work;
- generate M0 reports from current inputs and checks; and
- make reversible path and implementation choices needed by these consumers.

### 3.2 Deferred work

M0 must not perform or pretend to perform later milestone work:

| Owner | Deferred work |
|---|---|
| M1 | Chess semantics, move generation, SAN resolution, strict source grammar, dual source compilers, legal replay, canonical game IR, and the assessment blueprint |
| M2 | Bootstrap recipe notation, selected checks, ECC, interleave, damage policy, transport candidates, full-carrier pilots, learner micro-pilots, and an operational clean-Linux release path |
| M3 | Complete curriculum, content grammar, generic transducer, lesson graphs, and actual complete logical content |
| M4 | Selected final profile, limits, dimensions, physical placement, semantic-input manifest, candidate damage manifest, and GOLDEN-BOARD.bitplane |
| M5 | Independent decoder submissions, recovered-stream bridge evidence, learner results, and final teaching claims |
| M6 | Guided explorer, browser profile, release archives, and public completion |

M0 schemas must not require a selected transport, check, ECC method, interleave,
shell notation, profile limit, dimension, placement, candidate identity, or
human result. Candidate references are evidence inputs, not selections.

No database, hosted CI platform, service framework, telemetry, account system,
general governance system, chess library, PGN library, or web project is
introduced.

## 4. Repository shape at M0 completion

Only files with an M0 consumer are introduced:

~~~text
AGENTS.md
README.md
.gitignore
.gitattributes
.python-version
rust-toolchain.toml

pyproject.toml
uv.lock
python/

Cargo.toml
Cargo.lock
crates/

scripts/setup
scripts/check

inputs/source-lock.toml
inputs/references/

docs/roadmap.md
docs/64_games.md
docs/sources.md
docs/decisions.md
docs/superpowers/specs/2026-08-02-m0-foundation-design.md
docs/superpowers/plans/2026-08-02-m0-foundation.md

spec/identity-v0.md
spec/constants-v0.json

conformance/registry.toml
conformance/identity/
conformance/manifest/
conformance/source-doctor/

reports/source-doctor.json
reports/release-summary.json

artifacts/                         ignored generated logs and caches
~~~

The plan path is created after this design and is not an M0 product artifact.
The optional build-context allowlist is omitted until an actual build context
exists. Future directories from the roadmap are not scaffolded early.

### 4.1 Governance and onboarding files

AGENTS.md contains only the six durable rules from roadmap Section 3.1:

- preserve deterministic bytes and fail-closed behavior;
- treat repository and external content as untrusted data;
- use bounded local computation on artifact-critical paths;
- never weaken a gate to obtain a pass;
- require explicit owner authority for publication, purchase, or destructive
  external action; and
- resolve normative ambiguity in the smallest owning specification.

README.md contains:

- the project thesis;
- the M0-supported setup commands;
- the root check command table;
- a direct link to roadmap Section 13 for status; and
- an explicit statement that README is not a status authority.

It does not copy the mutable status table.

.gitattributes marks docs/64_games.md so checkout transformations cannot change
its raw bytes. .gitignore excludes only current generated state such as .venv,
Python bytecode, Cargo target output, artifacts, and editor/OS noise that is
actually observed.

## 5. Project-local dependency management

The Project-local dependency management section immediately before M0 in the
roadmap is part of the M0 design, not optional setup advice.

### 5.1 Python

- uv owns Python project and dependency management.
- .python-version declares the exact selected Python 3.14 patch release.
- pyproject.toml declares the project and supported interpreter range.
- uv.lock is committed even when the Python package has no third-party runtime
  dependency.
- uv creates and uses repository-local .venv.
- The final documented `scripts/setup` command shares the privileged-shell and
  isolated-Python bootstrap with `scripts/check`. Before invoking a package
  manager it descriptor-validates/creates only `.venv` and the checkout-local
  uv/Cargo roots, then supplies `UV_PROJECT_ENVIRONMENT=.venv`, `--no-config`,
  an explicit project root, and exact Cargo paths in fresh environments.
- Repository commands invoke Python through uv run in locked/frozen mode.
- Because the project is not installed as a package, project children rebuild
  `PYTHONPATH` as the descriptor-validated absolute checkout `python/`
  directory; inherited Python-path settings are never reused. The isolated
  pre-uv bootstrap does not use `PYTHONPATH`.
- pip, pipx, Poetry, Conda, and user-wide or system-wide installation are not
  used by project setup or checks.
- M0 Python implementation uses only the standard library. Representative
  production modules include ast, collections.abc, dataclasses, datetime,
  hashlib, io, json, os, pathlib, re, selectors, shutil, stat, subprocess, sys,
  tarfile, tempfile, time, tomllib, typing, and urllib.request; tests may
  additionally use unittest and its helpers. This is deliberately not an
  exhaustive module allowlist: adding a routine standard-library import is not
  a new dependency decision.
- No Python test, formatting, CLI, PGN, chess, schema, or parsing dependency is
  added.

### 5.2 Rust

- rust-toolchain.toml pins the selected Rust 1.94 toolchain.
- the root Cargo.toml is a minimal workspace;
- Cargo.lock is committed;
- every dependency-resolving build, test, fetch, check, and metadata command
  uses --locked after lock creation where Cargo supports it; unlocked
  `cargo generate-lockfile` is permitted only for initial creation or the
  immediate reviewed regeneration after a committed-manifest dependency
  change, and every following resolve/build command is locked; non-resolving
  version and `cargo fmt` probes are the only other explicit exceptions;
- cargo install is never part of setup or checks;
- the Rust standard test harness is sufficient;
- direct M0 dependencies are limited to sha2 for SHA-256 and serde plus
  serde_json for strict JSON decoding and value handling;
- canonical emission, duplicate detection, type restrictions, and byte
  equality are project code rather than delegated to a library default; and
- dependency features are kept to those consumed by M0.

No Rust CLI framework, property-test framework, TOML parser, chess library, or
PGN library is added.

### 5.3 Declared command surface

Normal repository commands use only:

- the owner-supplied `python3.14` bootstrap interpreter pinned to 3.14.6,
  invoked with isolated/no-site/no-bytecode flags only for pre-uv path and
  environment validation;
- uv and that pinned Python interpreter for project code in `.venv`;
- Cargo and the pinned Rust toolchain;
- the primary host's declared `/usr/bin/cc` driver and the linker/SDK that a
  bounded driver trace proves it actually selects for Rust test/binary targets;
- the POSIX shell needed to dispatch scripts/check; and
- Git for fresh-checkout verification.

The pinned Linux image analogously probes and records its actual Git, C
linker driver, linker, C runtime, shell, and manifest-declared architecture
before use. Its immutable index, platform-manifest, and config-blob digests
jointly own those image-userland and manifest facts; acquisition verifies the
descriptor chain and exact config bytes. The Docker daemon/VM separately owns
the per-attempt running kernel and runtime-architecture observations. Only
Python, uv, Rust, and Cargo are cross-platform semantic version pins.

All selected versions and host facts are recorded in inputs/source-lock.toml.
The setup/check wrappers use privileged shell startup (`#!/bin/sh -p`) and verify
that both declared shells ignore startup-file/function variables before line
one; its Python bootstrap uses `-I -S -B`. Project logic still runs through
the sealed `uv run` environment.
A development-only generic SHA-256 command may be recorded and used once to
audit expected vector hashes, but it is not a runtime or check dependency.

### 5.4 Acquisition and cache isolation

Dependency and reference acquisition is an explicit, separately reported
networked step. It:

1. resolves only committed lockfiles and declared reference locators;
2. records exact downloaded identities;
3. uses isolated checkout-local uv and Cargo cache roots rather than ordinary
   user-global caches; and
4. leaves enough local material for a subsequent offline check.

Clean native verification then:

1. starts from a fresh checkout;
2. hides ordinary global uv and Cargo caches;
3. creates a project-local environment from uv.lock;
4. builds Rust from Cargo.lock;
5. sets uv and Cargo to their locked offline modes after acquisition and
   records that M0 native evidence as resolver-offline, not as an OS-level
   network-denial claim; and
6. runs scripts/check full successfully.

The pinned clean-Linux path supplies OS-level network denial with
`--network none` when it becomes operational by M2. M0 does not fabricate that
stronger evidence when the Docker prerequisite is unavailable.

Shared caches may accelerate ordinary development, but they cannot be the only
reason a check passes.

## 6. Normative ownership created at M0

The roadmap remains the mission, scope, milestone, gate, and status owner.
M0 introduces these narrower owners:

| Fact | Owner |
|---|---|
| Developer hash framing and canonical manifest bytes | spec/identity-v0.md |
| Neutral constants source shape and values | spec/constants-v0.json |
| Source/reference/tool identities | inputs/source-lock.toml |
| Used external-source consequences and limitations | docs/sources.md |
| Consequential project decisions only | docs/decisions.md |
| Known-answer and rejection vector inventory | conformance/registry.toml |
| Current generated source observations | reports/source-doctor.json |
| Current acceptance-gate summary | reports/release-summary.json |
| Mutable milestone status | docs/roadmap.md Section 13 only |

Generated Python and Rust constants are consumers, never normative owners.
The design and implementation plan are not product-semantic authorities.

## 7. Identity v0

spec/identity-v0.md is readable without code and freezes the framing rules
needed before M1 can produce canonical source IR.

### 7.1 Digest

SHA-256 is the developer identity digest. Digest bytes are rendered as exactly
64 lowercase ASCII hexadecimal characters when a text representation is
required. Uppercase or shortened hexadecimal is noncanonical.

### 7.2 Domain prefixes

Every domain prefix is registered in spec/identity-v0.md and
spec/constants-v0.json. A later semantic specification may require a new
domain, but it cannot create an unregistered prefix on its own.

Every registered prefix is:

- a literal with one documented semantic owner and purpose;
- printable ASCII followed by exactly one zero byte;
- nonempty before the zero byte;
- no more than 63 bytes including the terminator; and
- compared byte-for-byte.

M0 defines only domains with a live M0 consumer:

~~~text
GB-MANIFEST-v0\0
GB-IDENTITY-TEST-A-v0\0
GB-IDENTITY-TEST-B-v0\0
~~~

Later owning specifications may nominate literal v0 prefixes. Before first
use, the identity registry and constants source must add them and both
implementations must pass cross-domain vectors. This does not change the v0
framing algorithm, but it does reopen the earliest milestone whose semantic
identity would be affected. M0 does not invent later game, section, lesson,
transport, or candidate identities.

### 7.3 Scalar preimage

The scalar identity preimage is:

~~~text
domain_prefix
|| u32_be(payload_byte_length)
|| payload_bytes
~~~

payload length must fit u32. The length is the exact byte length, not a Unicode
scalar or character count.

### 7.4 List preimage

The list identity preimage is:

~~~text
domain_prefix
|| u16_be(item_count)
|| for each item in specified order:
     u32_be(item_byte_length)
     || item_bytes
~~~

The list count must fit u16 and every item length must fit u32. Unless another
owning specification explicitly defines a smaller fixed field, these are the
default length and count widths.

Empty payload and empty list are distinct preimages. Field order is semantic;
implementations do not sort framed list items unless the owning specification
requires sorting before framing.

### 7.5 Required vectors

Hand-audited vectors include:

- empty scalar payload;
- one-byte and multibyte payloads;
- empty list;
- one empty item versus zero items;
- multiple items with asymmetric lengths;
- u16 and u32 integer-encoding helper boundaries, including maximum and
  overflow, without allocating a maximum-sized payload;
- same payload under test domains A and B;
- altered item order; and
- lowercase rendering.

Expected hashes are admitted only after independent Python and Rust results and
one declared generic SHA-256 audit agree. Neither language implementation
generates the other's checked fixture.

## 8. Canonical developer JSON

Canonical developer manifests use a closed JSON subset.

### 8.1 Data model

Allowed values are:

- strings containing Unicode scalar values;
- booleans;
- nonnegative integers from 0 through 18446744073709551615;
- arrays; and
- objects with ASCII keys.

Forbidden values and forms include:

- null;
- floats, fractional notation, exponent notation, and negative zero;
- negative integers;
- integers above the u64 maximum;
- duplicate keys;
- invalid UTF-8;
- isolated UTF-16 surrogate escapes;
- comments;
- a byte-order mark; and
- bytes after the required final LF.

M0 manifest-processing limits are:

- 16 MiB input bytes including the required final LF;
- 64 nested array/object levels;
- 65,535 members in one object;
- 65,535 items in one array;
- 1,000,000 decoded scalar/container nodes in total; and
- 16 MiB UTF-8 bytes in one decoded string.

Every limit is checked before the corresponding recursion, collection growth,
or output growth. Later candidate-bound parsers use generated profile limits;
these M0 values bound developer manifests only.

### 8.2 Object ordering

After JSON decoding, every object key must consist only of ASCII code points
U+0000 through U+007F. Controls, quote, and backslash are allowed as decoded
key bytes and are emitted through the same canonical escaping algorithm as
other strings. Keys are recursively sorted by those decoded ASCII bytes.

### 8.3 String emission

Canonical string emission:

- writes quote as backslash-quote;
- writes backslash as two backslashes;
- uses the short escapes for backspace, tab, LF, form feed, and carriage return;
- writes other U+0000 through U+001F controls as lowercase backslash-u-00xx;
- never escapes slash;
- writes all other Unicode scalar values directly as UTF-8;
- performs no Unicode normalization; and
- rejects surrogate code points rather than emitting them.

An accepted surrogate pair in noncanonical input is decoded to its scalar,
then canonical emission writes that scalar directly as UTF-8. An isolated high
or low surrogate rejects.

### 8.4 Document framing

Canonical output has:

- no insignificant whitespace;
- no leading or trailing spaces;
- no newline within structural formatting; and
- exactly one final LF.

The final LF is part of the canonical bytes and therefore part of any identity
payload that hashes the manifest.

### 8.5 Strict acceptance

A strict manifest reader:

1. enforces the manifest input-byte and nesting limits;
2. validates UTF-8 and rejects a BOM;
3. decodes while preserving object key pairs so duplicates remain visible;
4. rejects invalid syntax or trailing bytes;
5. rejects duplicate keys;
6. rejects unsupported types, invalid keys or Unicode, and out-of-range
   integers;
7. canonicalizes the decoded value;
8. byte-compares canonical output with the original bytes; and
9. rejects any unequal original as noncanonical.

This deliberately rejects semantically equivalent but differently escaped,
ordered, or spaced JSON.

Stable M0 diagnostic precedence is:

~~~text
manifest.limit
manifest.utf8
manifest.syntax
manifest.trailing_data
manifest.duplicate_key
manifest.unsupported_type
manifest.integer_range
manifest.invalid_key
manifest.invalid_unicode
manifest.noncanonical
~~~

When several defects occur at the same precedence level, the first one in raw
document order is primary. Python and Rust must return the same primary ID for
multiply invalid registered fixtures.

### 8.6 Manifest conformance

Shared raw fixtures cover:

- recursive key ordering;
- prefix-related ASCII keys;
- every escape rule;
- raw non-ASCII UTF-8;
- accepted paired and rejected isolated surrogate escapes;
- integer zero, u64 maximum, boundary plus one, negatives, and exponent forms;
- duplicate keys at every nesting level;
- empty arrays and objects;
- whitespace, comments, BOM, invalid UTF-8, and trailing bytes; and
- exact final-LF behavior.

Python and Rust must return the same accepted canonical bytes or the same
stable fixture outcome. Exception messages are not normative.

## 9. Neutral constants and conformance registry

### 9.1 Constants source

spec/constants-v0.json is a canonical JSON document containing:

- schema version;
- each M0 domain prefix as its printable ASCII text without the terminator and
  as lowercase hexadecimal bytes including the final 00, which must agree;
- stable M0 diagnostic identifiers needed by both implementations; and
- no selected later-profile values.

A small generator produces Python and Rust constants. The generator output is
checked for drift. Generated language files identify the source file and its
SHA-256, but do not become authorities.

### 9.2 Registry

conformance/registry.toml contains one entry per actual M0 vector. Each entry
has:

- unique stable ID;
- family;
- input path and raw SHA-256;
- expected accepted bytes/hash or expected rejection ID;
- applicable implementations; and
- owning specification section.

Fixture paths must remain inside conformance, be regular files, and match their
recorded hashes. Duplicate IDs, missing payloads, path traversal, unexpected
files, stale hashes, and an unregistered fixture fail.

The registry schema permits later families, which satisfies the roadmap's
requirement for later-profile vector slots. M0 does not add fake empty vectors
or guessed selected-profile fields.

## 10. Source lock and reference ledger

### 10.1 Anthology lock

inputs/source-lock.toml records the current anthology as:

- repository-relative path docs/64_games.md;
- regular-file requirement;
- exact raw byte length;
- exact raw SHA-256;
- required strict UTF-8 decode;
- BOM policy;
- newline profile; and
- final-LF fact.

The lock is computed from worktree bytes after .gitattributes is in place.
The raw source hash is developer verification data. It never enters the
canonical bitplane or blind learner material.

### 10.2 Normative and design references

The lock and docs/sources.md cover, at minimum:

- the FIDE Laws snapshot/version selected by roadmap Section 16.1;
- the source-format reference snapshot/version;
- FIPS 180-4 and its SHA-256 known-answer source;
- concrete candidate references for CRC and error-correction comparison;
- retained self-describing-message precedents actually used by M0 design;
- local Python, uv, Rust, Cargo, Git, shell, and host facts; and
- the clean-Linux mechanism, including immutable index, selected platform
  manifest, and image-config identities.

Each retained local snapshot or immutable reference has an exact identifier or
SHA-256. Mutable URLs alone cannot close the lock. When redistribution is not
appropriate, the lock records an immutable public identifier and acquisition
hash rather than committing copyrighted bytes.

Candidate CRC/ECC references are labelled candidate_reference. They do not
select an algorithm, tuple, field convention, wire order, or profile.

### 10.3 Source ledger

docs/sources.md contains, for each source actually used:

- exact title;
- author or organization;
- edition or version;
- stable locator;
- access date;
- local snapshot path or immutable identifier when practical;
- role;
- exact Golden Board consequence; and
- explicit statement of what the source does not establish.

No unrelated citation is retained merely for apparent comprehensiveness.

### 10.4 Decision ledger

docs/decisions.md defines the lean dated-entry format from roadmap Section 3.5.
It records only decisions in the roadmap's consequential list. It is valid for
the ledger to contain no decision entries at M0 when none of those triggers
occurred. Tool observations and the clean-Linux mechanism belong in the source
lock rather than creating ceremonial decision notes.

## 11. Source doctor

### 11.1 Boundary

The M0 source doctor is bounded read-only reconnaissance. It is not the M1
source compiler and has no chess or canonical-game capability.

Its core accepts one immutable byte sequence and returns a structured report.
The host adapter alone opens the declared repository-relative path and writes
an explicitly requested report.

### 11.2 Safe input snapshot

The adapter:

1. rejects an absolute path, parent traversal, symlink, FIFO, device, socket,
   directory, or missing input;
2. opens the expected path without following a symlink where supported;
3. validates the opened descriptor as a regular file;
4. enforces a 16 MiB M0 diagnostic read ceiling before allocation;
5. reads the bytes once with checked length accounting;
6. verifies file identity and size did not change during the read;
7. computes length and SHA-256 from that same snapshot; and
8. compares those facts with inputs/source-lock.toml.

The 16 MiB ceiling is an M0 diagnostic work bound, not the M1 source grammar's
canonical size limit.

### 11.3 G1-blocking preflight

These facts prevent G1 from passing:

- source path absent or not a direct regular file;
- path, length, or hash differs from the lock;
- invalid UTF-8;
- UTF-8 BOM;
- disallowed control bytes;
- mixed or unsupported newline profile;
- missing final LF; or
- fenced-PGN block count other than exactly 64.

The doctor still returns deterministic diagnostics when it safely can, but a
diagnostic report from a failing input is not passing evidence.

### 11.4 Reconnaissance taxonomy

From the raw snapshot the doctor reports:

- raw identity and encoding/newline facts;
- column-zero PGN fence count;
- half-open raw-byte spans for opener, body, and closer;
- tag-name inventory, counts, duplicate occurrences, and byte-size maxima;
- blank-separator shape;
- move-number token shape inventory;
- SAN-like token shape buckets without resolving chess meaning;
- result-marker inventory and unfinished results;
- comments, semicolon comments, escape lines, recursive annotation variations,
  NAGs, annotation suffixes, and trailing-token observations;
- alternate-start tag observations;
- provisional per-record raw byte and lexical-ply ranges; and
- exact raw duplicate-movetext candidates identified by raw span hashes; and
- a separately labelled token-whitespace-normalized candidate inventory for
  M1 investigation, never treated as semantic equality.

Unknown or source-specific constructs are reported with bounded samples of raw
byte spans, not copied metadata values. They remain M1 source-spec inputs.

The doctor does not:

- accept or reject SAN semantically;
- generate legal moves;
- replay a position;
- trust PlyCount or Result tag claims as truth;
- create minimal game IR;
- sort or assign game ordinals;
- emit canonical game bytes; or
- infer duplicate semantic move streams.

### 11.5 Deterministic report

reports/source-doctor.json uses canonical developer JSON and contains:

- report schema version;
- repo-relative source path;
- raw source SHA-256 and byte length;
- doctor implementation identity;
- deterministic findings in raw-byte order or explicitly byte-sorted order;
- stable diagnostics;
- passing G1-preflight boolean; and
- explicit non-authority limitations.

It contains no timestamp, username, home path, hostname, absolute path,
environment dump, or descriptive PGN tag value.

Report generation writes a unique temporary file on the destination
filesystem, verifies the completed bytes, then renames it. Check mode
regenerates into a temporary location and byte-compares with the tracked
report; it never silently updates evidence.

### 11.6 Doctor fixtures

The source-doctor fixture corpus includes:

- minimum valid fenced records;
- the exact current source;
- missing/nonregular/symlink input adapter cases;
- stale length and hash;
- UTF-8 BOM and invalid UTF-8;
- NUL and other controls;
- LF, CRLF, mixed newline, and missing final LF;
- 63 and 65 fences;
- malformed, nested-looking, and unterminated fences;
- duplicate tags;
- comments, variations, NAGs, annotations, and alternate-start tags;
- hostile tag values that resemble instructions or terminal escapes;
- repeated raw movetext;
- boundary and boundary-plus-one diagnostic sizes; and
- deterministic repeated output.

Fixtures test reconnaissance behavior, not M1 grammar or chess legality.

## 12. Root check contract

scripts/check is a small allowlisted dispatcher. It never evaluates a focus
area or file path as shell code.

### 12.1 Commands

~~~text
scripts/check fast
scripts/check focused foundation
scripts/check focused dependencies
scripts/check focused identity
scripts/check focused manifest
scripts/check focused source
scripts/check full
~~~

No argument defaults to fast. Missing required arguments, extra arguments,
unknown modes, and unknown areas exit nonzero with concise usage.

The same sealed dispatcher also admits only these explicit maintainer
operations, which are not ordinary root checks and are not copied into the
README command table:

~~~text
scripts/check generate source-doctor
scripts/check generate release-summary
scripts/check generate release-summary --native-evidence artifacts/native-verification.json
scripts/check environment verify-native
scripts/check environment verify-native --write-evidence
scripts/check environment verify-linux
~~~

Generation may replace only the named fixed report destination. Environment
verification uses the same isolated outer uv launch, while its owned adapter
performs the explicitly reported acquisition/offline phases. No arbitrary
module, path, command, or output destination is accepted.

During M0, scripts/check release exits with status 2 and states that release
verification becomes operational at the M2 architecture freeze. It cannot
return a fake pass.

### 12.2 fast

fast runs:

- repository text/final-LF and executable-mode checks;
- roadmap status/header consistency;
- AGENTS and README contract checks;
- uv and Cargo locked-manifest checks;
- constants generation drift check;
- registry and report-schema validation;
- Python standard-library unit tests that do not require the real anthology;
- Rust formatting and focused unit tests; and
- identity/manifest known-answer vectors.

Python formatting uses a small repository text invariant check; M0 does not add
a formatter dependency solely for style.

### 12.3 focused areas

- foundation: required files, governance content, status derivation, report
  shape, and forbidden premature fields;
- dependencies: toolchain pins, committed lockfiles, declared direct
  dependencies, project-local command usage, and no global-install commands;
- identity: Python/Rust framing and SHA-256 vectors;
- manifest: Python/Rust valid, invalid, and boundary canonical-JSON fixtures;
- source: source lock, doctor unit/adapter fixtures, real-source regeneration,
  and exact report comparison.

### 12.4 full

full runs every M0 fast and focused check, then:

- Python and Rust differential result comparison;
- complete real-source doctor regeneration;
- stale/generated-output checks;
- fresh-report and release-summary generation validation;
- bounded mutation cases for identity/manifest/source-doctor rejection; and
- native isolated-cache verification when invoked by the clean-check harness.

No check downloads dependencies, rewrites source files, updates tracked
reports, or changes milestone status.

## 13. Status derivation

Section 13 is the only editable status table. A small parser and generator own
the two derived header rows.

### 13.1 Validation

The parser requires:

- exactly M0 through M6 in order;
- exactly one allowed status per row;
- required specific text for blocker/revision/completion forms; and
- no unknown or duplicate milestone.

### 13.2 Current milestone

Current milestone is the first M0 through M6 row whose status does not begin
with Complete. If all rows begin with Complete, the derived display is
Complete.

This permits M6 implementation to overlap M5 after M4 while still reporting M5
as the earliest unfinished milestone.

### 13.3 Project state

Project state is derived as:

1. Complete when every milestone is Complete;
2. Not started when every milestone is Not started;
3. the exact earliest unfinished status when it is Blocked, Needs revision,
   Candidate ready, or Stopped; or
4. In progress otherwise.

A generator may rewrite only the two derived header values from Section 13.
scripts/check validates and fails stale display; ordinary checks never fix it.

M0 execution updates Section 13 to In progress before implementation. M0 is
marked Complete only after all M0 evidence passes; completion text includes
the date and G1 report identity. The derived current milestone then becomes M1.

## 14. Generated reports

### 14.1 Source doctor

reports/source-doctor.json is the deterministic G1 source evidence described
in Section 11.

### 14.2 Release summary

reports/release-summary.json is generated and contains exactly one row for each
G1 through G18. Its schema includes:

- schema version;
- roadmap revision;
- generation input identities, excluding the report's own output identity;
- gate ID and owning milestone;
- result;
- command or protocol;
- evidence identities;
- candidate identity only when one exists; and
- limitations.

At M0 only G1 may pass. G2 through G18 are pending_owner_milestone, with no
invented candidate identity, command result, or evidence. A pending row is not
a failed gate and cannot be presented as completion.

Raw logs remain ignored under artifacts. The tracked summary contains no
timestamps or host-local paths. No status file, output hash, completion
manifest, repository commit, or report output hash enters its own defining
input graph.

## 15. Clean Linux plan

M0 selects Docker as the clean-Linux mechanism because a Docker client is
present on the primary host, while explicitly distinguishing client presence
from a proven working daemon and image.

Before M0 closes, inputs/source-lock.toml records:

- mechanism Docker;
- an exact Linux image name plus immutable OCI index, selected
  platform-manifest, and config-blob digests;
- target platform;
- selected Python, uv, Rust, and Cargo versions;
- fixed dependency-acquisition protocol identifier (executable argv is
  code-owned);
- fixed cache-isolated offline-verification protocol identifier (executable
  argv is code-owned);
- expected mounts and output locations;
- current status planned or verified; and
- a specific blocker if the image/daemon cannot yet run.

The Docker path:

1. resolves and version-checks an absolute Docker client, uses a fixed daemon
   endpoint and a fresh empty client configuration, and gives every host-side
   Docker child a new allowlist environment;
2. uses a fresh repository checkout or clean exported tree;
3. hides host dependency caches;
4. validates the pinned image's closed baked environment, then a fixed shell
   bootstrap unsets it and constructs the exact phase environment;
5. acquires only locked dependencies during the explicit networked phase;
6. reruns scripts/check full with `--network none` and `--pull=never`;
7. records image-owned userland/manifest facts separately from daemon-owned
   runtime kernel/architecture observations;
8. writes only to an explicit temporary workspace/cache; and
9. later compares canonical bytes when M4 introduces them.

M0 requires a concrete, pinned, executable plan. M2 requires the path to work
before any transport or wire candidate freezes. M0 does not fabricate a Linux
pass if the daemon or image is unavailable.

## 16. Data and control flow

### 16.1 Source evidence

~~~text
fresh checkout
  -> .gitattributes-preserved docs/64_games.md
  -> source-lock path/type/length/hash preflight
  -> one bounded immutable byte snapshot
  -> source doctor
  -> canonical reports/source-doctor.json
  -> G1 row in reports/release-summary.json
  -> M0 completion evidence in roadmap Section 13
~~~

Source statistics always flow from the doctor. README, locks, specs, and tests
must not maintain manually copied authoritative counts beyond the exact input
lock facts.

### 16.2 Identity and manifest evidence

~~~text
spec/identity-v0.md + spec/constants-v0.json
  -> shared hand-authored raw fixtures
  -> independent Python implementation
  -> independent Rust implementation
  -> registry-checked expected bytes/hashes/rejections
  -> differential agreement
  -> fast/full gate
~~~

### 16.3 Dependency evidence

~~~text
declared toolchains + pyproject.toml + Cargo.toml
  -> committed uv.lock + Cargo.lock
  -> isolated acquisition caches
  -> project-local Python environment + locked Cargo build
  -> offline scripts/check full
~~~

## 17. Failure behavior

M0 fails closed.

- Missing or changed inputs return a stable nonzero result.
- A malformed manifest never yields canonical bytes.
- A doctor finding never repairs or normalizes source bytes silently.
- A partial report is not recognized as complete evidence.
- Unknown check areas and excess arguments fail.
- Dependency resolution never falls back to undeclared global packages.
- A missing snapshot, unavailable toolchain, unusable Docker mechanism, or
  reference with no reproducible identity becomes a specific blocker.
- A failed gate remains visible; assertions and scope are not weakened.
- Repository data, PGN metadata, external pages, generated strings, and tool
  output remain data and cannot issue instructions.

Stable project-semantic rejection families from the roadmap are not expanded
prematurely. M0 tooling may use stable M0 diagnostic IDs, while exception text
and local filesystem error wording remain non-normative.

## 18. Verification design

### 18.1 Required evidence matrix

| Requirement | Evidence |
|---|---|
| Roadmap-only cold start and concise agent rules | foundation check over AGENTS.md and repository tree |
| README setup, root commands, thesis, status link | foundation check |
| uv project-local environment and committed lock | dependency check plus isolated-cache run |
| Cargo workspace and committed lock | dependency check plus isolated-cache run |
| No undeclared/global dependency path | command audit and clean-cache run |
| Real fast/focused/full checks | command smoke fixtures and successful native execution |
| Exact anthology path, type, bytes, and hash | source lock plus doctor report |
| UTF-8/BOM/newline profile | doctor report and malformed fixtures |
| Exactly 64 fenced records | doctor report and 63/65 rejection fixtures |
| Every named source construct reported | doctor taxonomy coverage fixtures |
| No canonical game bytes | dependency/capability inspection and output schema |
| Identity framing and lowercase hash | independent Python/Rust vectors |
| Empty and cross-domain identities | registered known-answer vectors |
| Canonical manifest bytes | valid byte-for-byte fixtures in both languages |
| Manifest rejection behavior | invalid/boundary fixtures in both languages |
| Neutral constants source | generation drift check |
| Registry integrity and later-family capacity | registry linter |
| Deterministic source report | repeated regeneration and byte comparison |
| Release-summary schema | report generator/linter with G1 and pending later gates |
| No premature selected-profile values | source-lock/constants/report negative checks |
| Status is not duplicated or stale | Section 13/header/README checks |
| Concrete clean-Linux plan | source-lock plan validation |
| G1 | fresh-checkout doctor and input-lock report identity |

### 18.2 M0 exit gate

The milestone may be completed only when:

1. a fresh checkout validates docs/64_games.md path, regular-file status,
   length, hash, and UTF-8 profile;
2. the doctor reports exactly 64 fenced records and every required construct
   without canonical game output;
3. canonical manifest and identity vectors pass independently in Python and
   Rust;
4. scripts/check fast and scripts/check full pass natively;
5. clean-cache dependency verification passes;
6. no selected ECC/check/profile value is required or asserted;
7. every authoritative source-derived statistic is regenerated by the doctor;
8. reports/source-doctor.json and reports/release-summary.json are current;
9. the clean-Linux plan is concrete and pinned, or a specific pre-M2 blocker is
   recorded exactly as the roadmap permits; and
10. Section 13 and the derived roadmap header are updated consistently with
    the G1 report identity.

## 19. Implementation sequence constraints

The later implementation plan may choose task granularity, but it preserves
these ordering constraints:

1. mark M0 In progress and add the minimal governance/line-ending foundation;
2. establish pinned project-local Python/Rust environments and lockfiles;
3. freeze identity/manifest/constants contracts and raw fixtures;
4. implement Python and Rust identity/manifest paths independently;
5. establish source/reference/tool locks and ledgers;
6. implement the source doctor and deterministic reports;
7. complete root checks and status/report generation;
8. run native, fresh-checkout, isolated-cache, and planned Linux-path evidence;
9. fix every M0 gate failure without weakening it;
10. commit coherent checkpoints; and
11. mark M0 Complete only after final verification.

Parallel subagents may work only on independent file sets with explicit
ownership. Shared contracts and generated outputs are integrated centrally.
Each checkpoint is reviewed and verified before its commit.

## 20. Resolved ambiguities

This design resolves the M0 ambiguities as follows:

- the source doctor report is reports/source-doctor.json;
- the neutral constants source is spec/constants-v0.json;
- release-summary schema is embodied by the generated and validated
  reports/release-summary.json rather than a second schema framework;
- source spans are half-open raw-byte ranges;
- direct symlinks and nonregular anthology inputs reject;
- M0 JSON integers are bounded to u64;
- canonical Unicode emission is direct UTF-8 with the exact escaping rules in
  Section 8;
- the final LF participates in manifest identities;
- status derivation follows Section 13;
- Docker is the clean-Linux mechanism with an M2 operational deadline;
- later conformance slots are registry schema capacity, not fake fixtures;
- Python is standard-library-only;
- Rust has only SHA-256 and strict-JSON direct dependencies;
- reports are tracked deterministic evidence while raw logs remain ignored;
  and
- scripts/check release fails explicitly until M2 rather than pretending to
  verify a release.

Any implementation discovery that invalidates one of these choices must be
reported against the roadmap, revised here or in the smaller owning
specification, and reviewed before affected code continues.

## 21. Design self-review criteria

Before the design is considered ready for planning:

- no unresolved marker, guessed result, or undecided requirement remains;
- every M0 deliverable has a path and consumer;
- every M0 exit condition has executable evidence;
- dependency management includes uv, project-local .venv, both committed
  lockfiles, declared commands, hidden-cache verification, and the Linux plan;
- source reconnaissance cannot become a source compiler;
- identity/manifest rules are independent of future physical profiles;
- status and reports cannot become competing authorities;
- no optional path without an M0 consumer is created; and
- no M1 through M6 work is disguised as M0.
