#!/bin/sh

set -eu

case "$#" in
    2) source_root=$1; expected_snapshot_sha256=$2; phase=pre-gate8-clean ;;
    3) source_root=$1; expected_snapshot_sha256=$2; phase=$3 ;;
    *) printf 'usage: container-verify.sh SOURCE_ROOT EXPECTED_SNAPSHOT_SHA256 [candidate-ready|gate8-producers]\n' >&2; exit 2 ;;
esac

case "$phase" in
    pre-gate8-clean|candidate-ready|gate8-producers) ;;
    *) printf 'linux verify: invalid Gate-8 phase\n' >&2; exit 2 ;;
esac

case "$expected_snapshot_sha256" in
    ????????????????????????????????????????????????????????????????) ;;
    *) printf 'linux verify: invalid expected execution-snapshot identity\n' >&2; exit 1 ;;
esac

target=/work/golden-board
observed_snapshot_sha256=$(python "$source_root/tools/linux/snapshot.py" \
    materialize "$source_root" "$target")
[ "$observed_snapshot_sha256" = "$expected_snapshot_sha256" ] || {
    printf 'linux verify: execution snapshot changed during transfer\n' >&2
    exit 1
}

container_snapshot_sha256=$(python "$target/tools/linux/snapshot.py" digest "$target")
[ "$container_snapshot_sha256" = "$expected_snapshot_sha256" ] || {
    printf 'linux verify: materialized execution snapshot mismatch\n' >&2
    exit 1
}

if [ "$phase" = candidate-ready ]; then
    verifier_input=/gate8-verifier-input
    verifier_target=$target/artifacts/linux/verifier-v0.env
    [ -f "$verifier_input" ] && [ ! -L "$verifier_input" ] || {
        printf 'linux verify: verifier provenance input is missing or unsafe\n' >&2
        exit 1
    }
    [ "$(find "$verifier_input" -maxdepth 0 -type f -links 1 -print)" = \
        "$verifier_input" ] || {
        printf 'linux verify: verifier provenance input link count is unsafe\n' >&2
        exit 1
    }
    [ "$(wc -c < "$verifier_input" | tr -d ' ')" = 378 ] || {
        printf 'linux verify: verifier provenance input byte length mismatch\n' >&2
        exit 1
    }
    verifier_input_sha256=$(
        python "$target/tools/linux/snapshot.py" file-sha256 "$verifier_input"
    )
    [ "$verifier_input_sha256" = \
        315f9021f83ee8c6640af6ea6bcd58387287bcef42e7b27eaaf5f76b2187f6a2 ] || {
        printf 'linux verify: verifier provenance input identity mismatch\n' >&2
        exit 1
    }
    [ ! -e "$verifier_target" ] && [ ! -L "$verifier_target" ] || {
        printf 'linux verify: verifier provenance target already exists\n' >&2
        exit 1
    }
    mkdir -p "$target/artifacts/linux"
    cp "$verifier_input" "$verifier_target"
    chmod 644 "$verifier_target"
    [ "$(find "$verifier_target" -maxdepth 0 -type f -links 1 -print)" = \
        "$verifier_target" ] || {
        printf 'linux verify: verifier provenance target link count is unsafe\n' >&2
        exit 1
    }
    cmp "$verifier_input" "$verifier_target" >/dev/null || {
        printf 'linux verify: verifier provenance copy mismatch\n' >&2
        exit 1
    }
    provenance_snapshot_sha256=$(
        python "$target/tools/linux/snapshot.py" digest "$target"
    )
    [ "$provenance_snapshot_sha256" = "$expected_snapshot_sha256" ] || {
        printf 'linux verify: provenance changed execution snapshot\n' >&2
        exit 1
    }
fi

mkdir -p /tmp/golden-board-home
HOME=/tmp/golden-board-home
PYTHONDONTWRITEBYTECODE=1
UV_CACHE_DIR=/opt/uv-cache
UV_PYTHON_INSTALL_DIR=/opt/uv-python
CARGO_HOME=/opt/cargo
RUSTUP_HOME=/opt/rustup
export HOME PYTHONDONTWRITEBYTECODE UV_CACHE_DIR UV_PYTHON_INSTALL_DIR
export CARGO_HOME RUSTUP_HOME

cd "$target"
printf 'linux verify: execution snapshot %s\n' "$container_snapshot_sha256"
if [ "$phase" = candidate-ready ] || [ "$phase" = gate8-producers ]; then
    [ -d /gate8-output ] || {
        printf 'linux verify: Gate-8 mounts are missing\n' >&2
        exit 1
    }
    candidate_python=$(mktemp -d /tmp/golden-board-gate8-linux-python.XXXXXX)
    candidate_rust=$(mktemp -d /tmp/golden-board-gate8-linux-rust.XXXXXX)
    chmod 700 "$candidate_python" "$candidate_rust"
    uv run --locked --offline --no-python-downloads python \
        tools/m2/generate_gate8.py producer --mode generate \
        --producer-id linux-python --candidate-root "$candidate_python" \
        --output-dir /gate8-output
    rustup run 1.97.1 cargo build -p gb-bootstrap --bin gb-m2-gate8 \
        --release --locked --offline >/tmp/golden-board-gate8-rust-build.out \
        2>/tmp/golden-board-gate8-rust-build.err || {
        sed -n '1,80p' /tmp/golden-board-gate8-rust-build.err >&2
        exit 1
    }
    target/release/gb-m2-gate8 producer --mode generate \
        --producer-id linux-rust --candidate-root "$candidate_rust" \
        --output-dir /gate8-output
    [ -z "$(find "$candidate_python" -mindepth 1 -maxdepth 1 -print -quit)" ] && \
        [ -z "$(find "$candidate_rust" -mindepth 1 -maxdepth 1 -print -quit)" ] || {
        printf 'linux verify: producer work root was not cleaned\n' >&2
        exit 1
    }
    rmdir "$candidate_python" "$candidate_rust"
fi
if [ "$phase" = gate8-producers ]; then
    exit 0
fi
if [ "$phase" = candidate-ready ]; then
    [ -d /gate8-native-input ] || {
        printf 'linux verify: native-input mount is missing\n' >&2
        exit 1
    }
    GB_M2_LINUX_CANDIDATE_READY=1
    GB_M2_GATE8_NATIVE_INPUT=/gate8-native-input
    GB_M2_GATE8_LINUX_OUTPUT=/gate8-output
    export GB_M2_LINUX_CANDIDATE_READY GB_M2_GATE8_NATIVE_INPUT
    export GB_M2_GATE8_LINUX_OUTPUT
fi
scripts/check full
