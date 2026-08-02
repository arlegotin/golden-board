# Golden Board

Golden Board is a deterministic, self-teaching, damage-tolerant chess artifact whose eventual canonical message is one square binary bitplane. M0 establishes only the safe repository, identity, manifest, source-reconnaissance, and evidence foundations; it does not select a transport or implement chess.

## Setup

Dependency acquisition is explicit and may use the network:

```sh
UV_PROJECT_ENVIRONMENT=.venv UV_CACHE_DIR=artifacts/uv-cache UV_PYTHON_INSTALL_DIR=artifacts/uv-python UV_MANAGED_PYTHON=true uv --no-config sync --project . --locked
CARGO_HOME=artifacts/cargo-home CARGO_TARGET_DIR=artifacts/cargo-target cargo fetch --manifest-path Cargo.toml --locked
```

All repository checks after acquisition are offline and use project-local state.

## M0 checks

```sh
scripts/check fast
scripts/check focused foundation
scripts/check focused dependencies
scripts/check focused identity
scripts/check focused manifest
scripts/check focused source
scripts/check full
```

See [Roadmap status](docs/roadmap.md#13-project-status--sole-mutable-authority). README is not a status authority.
