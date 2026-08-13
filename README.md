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

Dependency acquisition commands will be added with the native lockfiles. Root
check commands will be documented when the real dispatcher exists.

## Repository map

- `docs/roadmap.md` — product contract, milestone gates, and status authority
- `docs/m0-spec.md` — M0 implementation contract
- `docs/m0-plan.md` — ordered M0 execution plan
- `docs/64_games.md` — authoritative, immutable-for-M0 anthology input
- `AGENTS.md` — concise repository safety rules
