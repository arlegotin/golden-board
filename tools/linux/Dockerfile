# syntax=docker/dockerfile:1@sha256:ecfaec9ed6d810b56388c508f4121597bfbba70d41a6dfeee4d8cad5f295fc32

FROM debian:13-slim@sha256:3a39a0592364683e6bab97937b72cad5a8fa6dcbbee90edb3bb48c7f8e94f258

ARG TARGETARCH
RUN test "$TARGETARCH" = arm64

ENV DEBIAN_FRONTEND=noninteractive \
    CARGO_HOME=/opt/cargo \
    RUSTUP_HOME=/opt/rustup \
    UV_CACHE_DIR=/opt/uv-cache \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python \
    PATH=/opt/cargo/bin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        build-essential ca-certificates curl git \
    && rm -rf /var/lib/apt/lists/*

ARG UV_VERSION=0.11.29
ARG UV_SHA256=94500fb064ae3c971a873cba64d94694c50677e0a4dbf78735c80509e7429919
RUN set -eu; \
    archive=/tmp/uv-aarch64-unknown-linux-gnu.tar.gz; \
    curl --fail --location --proto '=https' --tlsv1.2 \
        --output "$archive" \
        "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-aarch64-unknown-linux-gnu.tar.gz"; \
    printf '%s  %s\n' "$UV_SHA256" "$archive" | sha256sum --check --strict; \
    tar --extract --gzip --file "$archive" --directory /tmp; \
    install -m 0755 /tmp/uv-aarch64-unknown-linux-gnu/uv /usr/local/bin/uv; \
    install -m 0755 /tmp/uv-aarch64-unknown-linux-gnu/uvx /usr/local/bin/uvx; \
    rm -rf "$archive" /tmp/uv-aarch64-unknown-linux-gnu; \
    case "$(uv --version)" in \
        "uv ${UV_VERSION}"|"uv ${UV_VERSION} "*) ;; \
        *) exit 1 ;; \
    esac

ARG RUSTUP_INIT_VERSION=1.28.2
ARG RUSTUP_INIT_SHA256=e3853c5a252fca15252d07cb23a1bdd9377a8c6f3efa01531109281ae47f841c
RUN set -eu; \
    installer=/tmp/rustup-init; \
    curl --fail --location --proto '=https' --tlsv1.2 \
        --output "$installer" \
        "https://static.rust-lang.org/rustup/archive/${RUSTUP_INIT_VERSION}/aarch64-unknown-linux-gnu/rustup-init"; \
    printf '%s  %s\n' "$RUSTUP_INIT_SHA256" "$installer" | sha256sum --check --strict; \
    chmod 0755 "$installer"; \
    "$installer" --no-modify-path --profile minimal --default-toolchain none -y; \
    rm "$installer"; \
    rustup toolchain install 1.97.1 --profile minimal --component rustfmt; \
    test "$(rustup run 1.97.1 rustc --version | cut -d' ' -f1-2)" = "rustc 1.97.1"; \
    test "$(rustup run 1.97.1 cargo --version | cut -d' ' -f1-2)" = "cargo 1.97.1"

COPY .python-version pyproject.toml uv.lock /opt/acquire/
COPY Cargo.toml Cargo.lock rust-toolchain.toml /opt/acquire/
COPY crates /opt/acquire/crates

RUN set -eu; \
    cd /opt/acquire; \
    uv python install 3.14.6; \
    uv run --locked --all-groups --no-python-downloads \
        python -c 'import chess,sys; assert sys.version_info[:3] == (3,14,6); assert chess.__version__ == "1.11.2"'; \
    rustup run 1.97.1 cargo fetch --locked --target aarch64-unknown-linux-gnu; \
    mkdir -p /input /work /opt/golden-board; \
    { \
        printf 'schema=m2-linux-acquisition-v0\n'; \
        printf 'base=debian:13-slim@sha256:3a39a0592364683e6bab97937b72cad5a8fa6dcbbee90edb3bb48c7f8e94f258\n'; \
        printf 'platform=linux/arm64\n'; \
        uv --version; \
        uv run --locked --all-groups --no-python-downloads python --version; \
        rustup run 1.97.1 rustc --version; \
        rustup run 1.97.1 cargo --version; \
    } > /opt/golden-board/acquisition.txt

RUN test -x /opt/acquire/.venv/bin/python \
    && ln -s /opt/acquire/.venv/bin/python /usr/local/bin/python

LABEL org.golden-board.contract="m2-linux-verifier-v0" \
      org.golden-board.platform="linux/arm64" \
      org.golden-board.base="debian:13-slim@sha256:3a39a0592364683e6bab97937b72cad5a8fa6dcbbee90edb3bb48c7f8e94f258"

WORKDIR /work
