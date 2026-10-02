# Golden Board

Golden Board is a public pet project to build one deterministic square binary
bitplane that can teach a bounded, practical form of orthodox chess while
remaining recoverable under a declared accidental-damage model. The claim is
deliberately narrow: the finished artifact will be judged only against its
specified recipient model, source, tests, and validation evidence.

M0–M2 established the source/chess foundation and a qualified full-carrier
feasibility checkpoint. Complete content and final artifact validation are later
work. Current milestone status is maintained only in
[roadmap Section 13](docs/roadmap.md#13-project-status--sole-mutable-authority).

## Bootstrap

Project development and the M2 checkpoint use these exact tools:

- [uv 0.11.29](https://github.com/astral-sh/uv/releases/tag/0.11.29);
- CPython 3.14.6, selected by `.python-version`; and
- Rust/Cargo 1.97.1 with `rustfmt`, selected by `rust-toolchain.toml`.

Install the selected runtimes explicitly; project checks never install tools:

```sh
uv --version
uv python install 3.14.6
rustup toolchain install 1.97.1 --profile minimal --component rustfmt
```

Acquire the committed dependency graphs once while network access is explicit:

```sh
uv sync --locked
rustup run 1.97.1 cargo fetch --locked
```

Ordinary checks are then locked and offline. The complete public command surface
is:

```sh
scripts/check fast
scripts/check checkpoint
scripts/check focused source
scripts/check focused identity
scripts/check focused chess
scripts/check focused curriculum
scripts/check focused content
scripts/check focused transport
scripts/check focused damage
scripts/check focused repo
scripts/check components
scripts/check linux
scripts/check full
scripts/check release
```

`scripts/check linux` uses an already acquired verifier image. Acquisition is
the one explicitly network-enabled step and is never performed by an ordinary
check:

```sh
tools/linux/acquire.sh
scripts/check linux
```

The verifier is pinned to `linux/arm64` and the Debian 13 slim digest recorded
by M0. In the restored frozen M2 repository, verification runs `scripts/check full`
with container networking off,
without host language caches, from a disposable reconstruction of the current
HEAD, index, worktree, deletions, and nonignored untracked files. If the image
or its local acquisition evidence is missing, the command fails and prints the
acquisition command; it does not download or rebuild anything.

At the M2 Candidate-ready boundary, `scripts/check release` composes one host
`full` run, the network-disabled clean-Linux run, and cheap report/freeze
assertions. It does not build a public release package or perform a third
candidate reproduction.

## Source-doctor evidence

Ordinary checks compare a fresh report with the tracked evidence and never
rewrite it. To review an intentional update, generate into ignored authoring
storage first:

```sh
PYTHONPATH="$PWD/python" uv run --locked --offline --no-python-downloads \
  python -c 'from pathlib import Path; Path("artifacts").mkdir(exist_ok=True)'
PYTHONPATH="$PWD/python" uv run --locked --offline --no-python-downloads \
  python -m golden_board.source_doctor > artifacts/source-doctor.candidate.json
```

After reviewing that complete candidate, install it with a same-directory
temporary file and atomic replace; do not redirect output over the tracked
report:

```sh
PYTHONPATH="$PWD/python" uv run --locked --offline --no-python-downloads \
  python -c 'import os,tempfile; from pathlib import Path; s=Path("artifacts/source-doctor.candidate.json"); d=Path("reports/source-doctor.json"); d.parent.mkdir(exist_ok=True); f=tempfile.NamedTemporaryFile(dir=d.parent,delete=False); p=f.name; f.write(s.read_bytes()); f.close(); os.replace(p,d)'
```

## M2 checkpoint and M3 handoff

Start with [M2 results and inherited lessons](studies/m2/participant-learnings-v1.md)
and [the cleanup/evidence map](docs/m2.5-closeout.md). `scripts/check checkpoint`
hashes the retained completed source/evidence without rerunning production gates.
It rejects missing evidence. A fresh clone has source and tracked reports, but
must restore the documented private evidence before this historical check.

To restore the original ordinary repository for explicit M2 reproduction:

```sh
PYTHONPATH=python uv run --locked --offline --no-python-downloads python \
  tools/m2/verify_gate8_v2.py restore-checkpoint --destination /absolute/fresh/path
```

That directory contains the original source, roadmap, candidate, Gate8, acquisition
receipt, transition archive, required legacy snapshots/policy owners and
qualification preimages. Full/Linux/release use
their original runners there. Live full/release rejects reuse of M2's old result;
current focused checks continue to check development source. Material recipient
or transport changes follow the existing reopening rules.

For M3 development, run the affected focused checks; `scripts/check components`
runs the complete code/component suites without launching the M2 producer campaign.

## Repository map

- `docs/roadmap.md` — product contract, milestone gates, and status authority
- `docs/m0-spec.md` — M0 implementation contract
- `docs/m0-plan.md` — historical M0 execution record
- `docs/m1-spec.md` — M1 execution contract and design rationale
- `docs/m1-plan.md` — historical M1 execution record
- `docs/m2-spec.md` — M2 execution contract and design rationale
- `docs/m2-plan.md` — historical M2 execution record
- `docs/sources.md` — retained reference ledger and rights limits
- `docs/64_games.md` — authoritative, immutable-for-M0 anthology input
- `inputs/source-lock.toml` — exact input and reference receipts
- `spec/identity-v0.md` — sole identity/canonical-manifest byte contract
- `conformance/` — hand-authored shared identity, chess, source, and content fixtures
- `python/` and `crates/` — independent identity, chess, source, and content implementations
- `reports/` — retained source-doctor and agreed source-compilation evidence
- `scripts/check` — current focused checks and checkpoint/reproduction entry points
- `AGENTS.md` — concise repository safety rules


- [M2 results and learnings](studies/m2/participant-learnings-v1.md) — canonical study narrative, all attempts and 31 findings/C01–C11
- [M2 qualification](studies/m2/qualification-v2.json) — immutable reviewed human result
- [M2 checkpoint](studies/m2/checkpoint-v1.json) — exact completed source/evidence identities
- [M2.5 closeout](docs/m2.5-closeout.md) — retained private evidence, disk recovery and restoration
- `artifacts/` — required frozen evidence and documented private study proof; generation work is disposable

`spec/gate8-policy-v2.toml` and `spec/gate8-execution-v2.md` own current M2
evidence entry points; `spec/bootstrap-v2.md`, `spec/recovery-provenance-v2.md`,
`spec/content-teaching-v2.md` and `spec/slice-v1.md` own the active recipient,
recovery, teaching and selected content contracts. Older v0/v1 owners remain
where these contracts or conformance checks inherit them; version age alone
does not make a file obsolete.
