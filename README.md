# Golden Board

Golden Board is a deterministic, self-teaching, damage-tolerant chess artifact whose eventual canonical message is one square binary bitplane. M0 establishes only the safe repository, identity, manifest, source-reconnaissance, and evidence foundations; it does not select a transport or implement chess.

## Setup

Dependency acquisition is explicit and may use the network:

```sh
scripts/setup
```

Setup uses the exact project-local `.venv`, `artifacts/uv-cache`,
`artifacts/uv-python`, `artifacts/cargo-home`, and `artifacts/cargo-target`
paths. It resolves the committed `uv.lock` and `Cargo.lock` with `--no-config`
and installs nothing globally. All repository checks after acquisition are
offline.

## M0 checks

```sh
scripts/check
scripts/check fast
scripts/check focused foundation
scripts/check focused dependencies
scripts/check focused identity
scripts/check focused manifest
scripts/check focused source
scripts/check full
scripts/check release
```

`scripts/check release` remains unavailable until the M2 architecture freeze
and exits with status 2; it never reports a placeholder pass.

See [Roadmap status](docs/roadmap.md#13-project-status--sole-mutable-authority). README is not a status authority.
