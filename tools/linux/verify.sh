#!/bin/sh

set -eu

case "$#" in
    0) ;;
    *) printf 'usage: tools/linux/verify.sh\n' >&2; exit 2 ;;
esac

case "$0" in
    */*) script_path=$0 ;;
    *) script_path=$(command -v "$0") || exit 1 ;;
esac
SCRIPT_DIR=$(CDPATH= cd "${script_path%/*}" && pwd) || exit 1
ROOT=$(CDPATH= cd "$SCRIPT_DIR/../.." && pwd) || exit 1

# This file contains only project-owned literal assignments.
. "$SCRIPT_DIR/image.env"

fail() {
    printf 'linux verify: %s\n' "$1" >&2
    exit 1
}

new_private_directory() {
    directory=$(mktemp -d "${TMPDIR:-/tmp}/golden-board-linux.XXXXXX") || return 1
    chmod 700 "$directory" || return 1
    printf '%s\n' "$directory"
}

cleanup_directory() {
    directory=$1
    case "$directory" in
        "${TMPDIR:-/tmp}"/golden-board-linux.*|/tmp/golden-board-linux.*|/private/tmp/golden-board-linux.*) ;;
        *) return 1 ;;
    esac
    rm -rf "$directory"
}

command -v git >/dev/null 2>&1 || fail 'missing git'
command -v docker >/dev/null 2>&1 || fail 'missing docker'

actual_root=$(git -C "$ROOT" rev-parse --show-toplevel 2>/dev/null) || \
    fail 'repository root is not a Git worktree'
[ "$actual_root" = "$ROOT" ] || fail 'tools/linux is not inside the repository root'

evidence=$ROOT/artifacts/linux/verifier-v0.env
[ -f "$evidence" ] || fail \
    'verifier image acquisition evidence is missing; run tools/linux/acquire.sh'

schema_line=
image_line=
image_id_line=
platform_line=
contract_line=
base_line=
dockerfile_line=
extra_line=
{
    IFS= read -r schema_line || fail 'truncated acquisition evidence'
    IFS= read -r image_line || fail 'truncated acquisition evidence'
    IFS= read -r image_id_line || fail 'truncated acquisition evidence'
    IFS= read -r platform_line || fail 'truncated acquisition evidence'
    IFS= read -r contract_line || fail 'truncated acquisition evidence'
    IFS= read -r base_line || fail 'truncated acquisition evidence'
    IFS= read -r dockerfile_line || fail 'truncated acquisition evidence'
    if IFS= read -r extra_line; then
        fail 'acquisition evidence has trailing fields'
    fi
} < "$evidence"

[ "$schema_line" = schema=m2-linux-image-v0 ] || fail 'acquisition evidence schema mismatch'
[ "$image_line" = "image=$GB_LINUX_IMAGE" ] || fail 'acquisition image name mismatch'
[ "$platform_line" = "platform=$GB_LINUX_PLATFORM" ] || fail 'acquisition platform mismatch'
[ "$contract_line" = "contract=$GB_LINUX_CONTRACT" ] || fail 'acquisition contract mismatch'
[ "$base_line" = "base=$GB_LINUX_BASE" ] || fail 'acquisition base mismatch'
image_id=${image_id_line#image_id=}
dockerfile_sha256=${dockerfile_line#dockerfile_sha256=}
[ "image_id=$image_id" = "$image_id_line" ] || fail 'malformed acquired image identity'
[ "dockerfile_sha256=$dockerfile_sha256" = "$dockerfile_line" ] || \
    fail 'malformed Dockerfile identity'
case "$image_id" in
    sha256:????????????????????????????????????????????????????????????????) ;;
    *) fail 'malformed acquired image identity' ;;
esac
case "$dockerfile_sha256" in
    ????????????????????????????????????????????????????????????????) ;;
    *) fail 'malformed Dockerfile identity' ;;
esac

observed_id=$(docker image inspect --format '{{.Id}}' "$GB_LINUX_IMAGE" 2>/dev/null) || \
    fail 'verifier image is missing; run tools/linux/acquire.sh'
[ "$observed_id" = "$image_id" ] || fail 'verifier image differs from acquisition evidence'
observed_platform=$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$GB_LINUX_IMAGE")
[ "$observed_platform" = "$GB_LINUX_PLATFORM" ] || fail 'verifier image platform mismatch'
observed_contract=$(docker image inspect \
    --format '{{index .Config.Labels "org.golden-board.contract"}}' \
    "$GB_LINUX_IMAGE")
[ "$observed_contract" = "$GB_LINUX_CONTRACT" ] || fail 'verifier contract label mismatch'
observed_base=$(docker image inspect \
    --format '{{index .Config.Labels "org.golden-board.base"}}' \
    "$GB_LINUX_IMAGE")
[ "$observed_base" = "$GB_LINUX_BASE" ] || fail 'verifier base label mismatch'

current_dockerfile_sha256=$(docker run --rm \
    --network none \
    --platform "$GB_LINUX_PLATFORM" \
    --mount "type=bind,source=$ROOT,target=/golden-board-host,readonly" \
    "$GB_LINUX_IMAGE" \
    python /golden-board-host/tools/linux/snapshot.py file-sha256 \
        /golden-board-host/tools/linux/Dockerfile)
[ "$current_dockerfile_sha256" = "$dockerfile_sha256" ] || \
    fail 'Dockerfile changed after acquisition; run tools/linux/acquire.sh'

host_snapshot_sha256=$(docker run --rm \
    --network none \
    --platform "$GB_LINUX_PLATFORM" \
    --mount "type=bind,source=$ROOT,target=/golden-board-host,readonly" \
    "$GB_LINUX_IMAGE" \
    python /golden-board-host/tools/linux/snapshot.py digest /golden-board-host)
case "$host_snapshot_sha256" in
    ????????????????????????????????????????????????????????????????) ;;
    *) fail 'host execution-snapshot identity is malformed' ;;
esac

# A partial revised transition must reject in v2, never enter the old path.
if grep -F -x '| Roadmap revision | 11 |' "$ROOT/docs/roadmap.md" >/dev/null || \
    [ -e "$ROOT/artifacts/history/m2-pre-participant-revision-v1" ] || \
    [ -L "$ROOT/artifacts/history/m2-pre-participant-revision-v1" ]; then
    exec sh "$SCRIPT_DIR/verify-v2.sh" "$ROOT" "$host_snapshot_sha256" "$image_id"
fi

report=$ROOT/reports/m2-feasibility-v0.json
gate8=$ROOT/artifacts/gate8
if [ ! -e "$report" ] && [ ! -e "$gate8" ]; then
    if [ -n "${GB_M2_GATE8_BOOTSTRAP_OUTPUT:-}" ]; then
        case "$GB_M2_GATE8_BOOTSTRAP_OUTPUT" in /*) ;; *) fail 'bootstrap output path is not absolute' ;; esac
        [ -d "$GB_M2_GATE8_BOOTSTRAP_OUTPUT" ] || fail 'bootstrap output directory is missing'
        [ -z "$(find "$GB_M2_GATE8_BOOTSTRAP_OUTPUT" -mindepth 1 -maxdepth 1 -print -quit)" ] || \
            fail 'bootstrap output directory is not empty'
        docker run --rm \
            --network none \
            --platform "$GB_LINUX_PLATFORM" \
            --mount "type=bind,source=$ROOT,target=/input,readonly" \
            --mount "type=bind,source=$GB_M2_GATE8_BOOTSTRAP_OUTPUT,target=/gate8-output" \
            "$GB_LINUX_IMAGE" \
            sh /input/tools/linux/container-verify.sh /input "$host_snapshot_sha256" \
                gate8-producers || fail 'clean Linux Gate-8 producers failed'
        [ "$(find "$GB_M2_GATE8_BOOTSTRAP_OUTPUT" -mindepth 1 -maxdepth 1 -type f -print | wc -l | tr -d ' ')" = 2 ] || \
            fail 'clean Linux producers returned an invalid receipt set'
        exit 0
    fi
    docker run --rm \
        --network none \
        --platform "$GB_LINUX_PLATFORM" \
        --mount "type=bind,source=$ROOT,target=/input,readonly" \
        "$GB_LINUX_IMAGE" \
        sh /input/tools/linux/container-verify.sh /input "$host_snapshot_sha256" || \
        fail 'clean Linux full suite failed'
    exit 0
fi
[ -f "$report" ] && [ -d "$gate8" ] || fail 'partial Gate-8 lifecycle state'

native_input=$(new_private_directory) || fail 'cannot create native-input directory'
linux_output=$(new_private_directory) || {
    cleanup_directory "$native_input"
    fail 'cannot create Linux receipt directory'
}
trap 'cleanup_directory "$native_input"; cleanup_directory "$linux_output"' 0 1 2 3 15

if [ -n "${GB_M2_RELEASE_NATIVE_RECEIPTS:-}" ]; then
    case "$GB_M2_RELEASE_NATIVE_RECEIPTS" in /*) ;; *) fail 'release receipt path is not absolute' ;; esac
    native_receipts=$GB_M2_RELEASE_NATIVE_RECEIPTS
    input_mode=release-fresh
    native_python_container=/native-receipts/native-python.json
    native_rust_container=/native-receipts/native-rust.json
else
    native_receipts=$gate8/receipts
    input_mode=standalone-retained
    native_python_container=/input/artifacts/gate8/receipts/native-python.json
    native_rust_container=/input/artifacts/gate8/receipts/native-rust.json
fi
[ -f "$native_receipts/native-python.json" ] && \
    [ -f "$native_receipts/native-rust.json" ] || fail 'native receipts are missing'

docker run --rm \
    --network none \
    --platform "$GB_LINUX_PLATFORM" \
    --workdir /input \
    --env PYTHONPATH=/input/python \
    --mount "type=bind,source=$ROOT,target=/input,readonly" \
    --mount "type=bind,source=$native_receipts,target=/native-receipts,readonly" \
    --mount "type=bind,source=$native_input,target=/gate8-native-input-output" \
    "$GB_LINUX_IMAGE" \
    python /input/tools/m2/generate_gate8.py prepare-linux-input \
        --mode "$input_mode" \
        --native-python-receipt "$native_python_container" \
        --native-rust-receipt "$native_rust_container" \
        --output-dir /gate8-native-input-output || \
    fail 'clean Linux native-input preparation failed'

docker run --rm \
    --network none \
    --platform "$GB_LINUX_PLATFORM" \
    --mount "type=bind,source=$ROOT,target=/input,readonly" \
    --mount "type=bind,source=$evidence,target=/gate8-verifier-input,readonly" \
    --mount "type=bind,source=$native_input,target=/gate8-native-input,readonly" \
    --mount "type=bind,source=$linux_output,target=/gate8-output" \
    "$GB_LINUX_IMAGE" \
    sh /input/tools/linux/container-verify.sh /input "$host_snapshot_sha256" \
        candidate-ready || fail 'clean Linux Candidate-ready full suite failed'

[ "$(find "$linux_output" -mindepth 1 -maxdepth 1 -type f -print | wc -l | tr -d ' ')" = 2 ] || \
    fail 'clean Linux returned an invalid receipt set'
cmp "$linux_output/linux-python.json" "$gate8/receipts/linux-python.json" >/dev/null || \
    fail 'clean Linux Python receipt changed'
cmp "$linux_output/linux-rust.json" "$gate8/receipts/linux-rust.json" >/dev/null || \
    fail 'clean Linux Rust receipt changed'
