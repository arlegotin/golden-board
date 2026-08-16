# Golden Board

Golden Board is a public pet project to build one deterministic square binary
bitplane that can teach a bounded, practical form of orthodox chess while
remaining recoverable under a declared accidental-damage model. The claim is
deliberately narrow: the finished artifact will be judged only against its
specified recipient model, source, tests, and validation evidence.

The project is pre-artifact and has not yet demonstrated its reconstruction or
learning claims. Current milestone status is maintained only in
[roadmap Section 13](docs/roadmap.md#13-project-status--sole-mutable-authority).

## Bootstrap

M0 uses these exact project tools:

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
scripts/check focused source
scripts/check focused identity
scripts/check focused chess
scripts/check focused curriculum
scripts/check focused content
scripts/check focused repo
scripts/check full
```

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

## Repository map

- `docs/roadmap.md` — product contract, milestone gates, and status authority
- `docs/m0-spec.md` — M0 implementation contract
- `docs/m0-plan.md` — ordered M0 execution plan
- `docs/m1-spec.md` — M1 execution contract and design rationale
- `docs/m1-plan.md` — flexible, ordered M1 execution plan
- `docs/sources.md` — retained reference ledger and rights limits
- `docs/64_games.md` — authoritative, immutable-for-M0 anthology input
- `inputs/source-lock.toml` — exact input and reference receipts
- `spec/identity-v0.md` — sole identity/canonical-manifest byte contract
- `conformance/` — hand-authored shared identity/manifest fixtures
- `python/` and `crates/gb-foundation/` — independent implementations and tests
- `reports/source-doctor.json` — deterministic lexical reconnaissance evidence
- `scripts/check` — M0 root check dispatcher
- `AGENTS.md` — concise repository safety rules
