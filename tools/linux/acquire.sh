#!/bin/sh

set -eu

case "$#" in
    0) ;;
    *) printf 'usage: tools/linux/acquire.sh\n' >&2; exit 2 ;;
esac

case "$0" in
    */*) script_path=$0 ;;
    *) script_path=$(command -v "$0") || exit 1 ;;
esac
SCRIPT_DIR=$(CDPATH= cd "${script_path%/*}" && pwd) || exit 1
ROOT=$(CDPATH= cd "$SCRIPT_DIR/../.." && pwd) || exit 1

evidence_dir=$ROOT/artifacts/linux
evidence=$evidence_dir/verifier-v0.env
report=$ROOT/reports/m2-feasibility-v0.json
gate8_root=$ROOT/artifacts/gate8

guard_frozen_output() {
    for target in "$evidence" "$report" "$gate8_root"; do
        if [ -e "$target" ] || [ -L "$target" ]; then
            printf 'linux acquire: verifier evidence is frozen; explicit refresh owner required\n' >&2
            exit 2
        fi
    done
}

# The build itself can replace the fixed tag, so this guard is deliberately
# before every Docker lookup, pull, build, or tag operation.
guard_frozen_output

# This file contains only project-owned literal assignments.
. "$SCRIPT_DIR/image.env"

command -v git >/dev/null 2>&1 || {
    printf 'linux acquire: missing git\n' >&2
    exit 1
}
command -v docker >/dev/null 2>&1 || {
    printf 'linux acquire: missing docker\n' >&2
    exit 1
}

git -C "$ROOT" rev-parse --show-toplevel >/dev/null 2>&1 || {
    printf 'linux acquire: repository root is not a Git worktree\n' >&2
    exit 1
}

printf 'linux acquire: building %s for %s with network access\n' \
    "$GB_LINUX_IMAGE" "$GB_LINUX_PLATFORM"
docker build \
    --platform "$GB_LINUX_PLATFORM" \
    --pull \
    --file "$SCRIPT_DIR/Dockerfile" \
    --tag "$GB_LINUX_IMAGE" \
    "$ROOT"

image_id=$(docker image inspect --format '{{.Id}}' "$GB_LINUX_IMAGE")
observed_platform=$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$GB_LINUX_IMAGE")
observed_contract=$(docker image inspect \
    --format '{{index .Config.Labels "org.golden-board.contract"}}' \
    "$GB_LINUX_IMAGE")
observed_base=$(docker image inspect \
    --format '{{index .Config.Labels "org.golden-board.base"}}' \
    "$GB_LINUX_IMAGE")

case "$image_id" in
    sha256:????????????????????????????????????????????????????????????????) ;;
    *) printf 'linux acquire: invalid image identity: %s\n' "$image_id" >&2; exit 1 ;;
esac
[ "$observed_platform" = "$GB_LINUX_PLATFORM" ] || {
    printf 'linux acquire: expected platform %s, got %s\n' \
        "$GB_LINUX_PLATFORM" "$observed_platform" >&2
    exit 1
}
[ "$observed_contract" = "$GB_LINUX_CONTRACT" ] || {
    printf 'linux acquire: verifier contract label mismatch\n' >&2
    exit 1
}
[ "$observed_base" = "$GB_LINUX_BASE" ] || {
    printf 'linux acquire: verifier base label mismatch\n' >&2
    exit 1
}

dockerfile_sha256=$(docker run --rm \
    --network none \
    --platform "$GB_LINUX_PLATFORM" \
    --mount "type=bind,source=$ROOT,target=/golden-board-host,readonly" \
    "$GB_LINUX_IMAGE" \
    python /golden-board-host/tools/linux/snapshot.py file-sha256 \
        /golden-board-host/tools/linux/Dockerfile)

case "$dockerfile_sha256" in
    ????????????????????????????????????????????????????????????????) ;;
    *) printf 'linux acquire: invalid Dockerfile identity\n' >&2; exit 1 ;;
esac

guard_frozen_output
[ ! -L "$ROOT/artifacts" ] || {
    printf 'linux acquire: artifacts directory must not be a symlink\n' >&2
    exit 1
}
[ ! -L "$evidence_dir" ] || {
    printf 'linux acquire: evidence directory must not be a symlink\n' >&2
    exit 1
}
mkdir -p "$evidence_dir"
case "$evidence_dir" in
    */../*|*/./*) printf 'linux acquire: invalid evidence directory\n' >&2; exit 1 ;;
esac
temporary=$(mktemp "$evidence_dir/.verifier-v0.env.XXXXXX") || exit 1
trap 'rm -f "$temporary"' EXIT HUP INT TERM
chmod 600 "$temporary"
{
    printf 'schema=m2-linux-image-v0\n'
    printf 'image=%s\n' "$GB_LINUX_IMAGE"
    printf 'image_id=%s\n' "$image_id"
    printf 'platform=%s\n' "$observed_platform"
    printf 'contract=%s\n' "$observed_contract"
    printf 'base=%s\n' "$observed_base"
    printf 'dockerfile_sha256=%s\n' "$dockerfile_sha256"
} > "$temporary"

guard_frozen_output
if ! ln "$temporary" "$evidence"; then
    printf 'linux acquire: receipt publication raced or already exists\n' >&2
    exit 1
fi
rm -f "$temporary"
trap - EXIT HUP INT TERM

printf 'linux acquire: recorded %s in %s\n' "$image_id" "$evidence"
