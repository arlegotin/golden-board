#!/bin/sh
# Internal continuation: verify.sh already admitted the exact acquired image.
set -eu

case "$#" in
    3) source_root=$1; expected_snapshot_sha256=$2; image_id=$3 ;;
    *) printf 'usage: verify-v2.sh SOURCE_ROOT EXPECTED_SNAPSHOT_SHA256 ADMITTED_IMAGE_ID\n' >&2; exit 2 ;;
esac
fail() { printf 'linux verify v2: %s\n' "$1" >&2; exit 1; }
hex_digest() {
    [ "${#1}" = 64 ] || return 1
    case "$1" in *[!0-9a-f]*) return 1 ;; esac
}
safe_directory() {
    case "$1" in /*) ;; *) fail 'directory path is not absolute' ;; esac
    case "$1" in *','*|*'
'*) fail 'unsafe mount path' ;; esac
    [ -d "$1" ] && [ "$1" != / ] || fail 'directory is missing'
    [ "$(CDPATH= cd "$1" && pwd -P)" = "$1" ] || fail 'directory path is not canonical'
    current=$1
    while [ "$current" != / ]; do
        [ ! -L "$current" ] || fail 'directory has a link ancestor'
        current=${current%/*}
        [ -n "$current" ] || current=/
    done
}
hex_digest "$expected_snapshot_sha256" || fail 'invalid execution-snapshot identity'
output=${GB_M2_GATE8_V2_OUTPUT:-}
native=${GB_M2_GATE8_V2_NATIVE_RECEIPTS:-}
safe_directory "$source_root"
safe_directory "$output"
safe_directory "$native"
[ -d "$source_root/.git" ] && [ ! -L "$source_root/.git" ] || fail 'ordinary repository required'
case "$output/" in "$source_root/"*|"$native/"*) fail 'output overlaps an input' ;; esac
case "$source_root/" in "$output/"*) fail 'output contains the source' ;; esac
case "$native/" in "$output/"*) fail 'output contains native inputs' ;; esac
[ "$(find "$output" -maxdepth 0 -type d -perm 0700 -print)" = "$output" ] || fail 'output mode is not 0700'
[ -z "$(find "$output" -mindepth 1 -maxdepth 1 -print -quit)" ] || fail 'output is not empty'
[ "$(find "$native" -mindepth 1 -maxdepth 1 -print | wc -l | tr -d ' ')" = 2 ] || fail 'native receipt set differs'
for producer in native-python native-rust; do
    receipt=$native/$producer.json
    [ ! -L "$receipt" ] && [ "$(find "$receipt" -maxdepth 0 -type f -links 1 -perm 0644 -print)" = "$receipt" ] || fail 'unsafe native receipt'
done
. "$source_root/tools/linux/image.env"
evidence=$source_root/artifacts/linux/verifier-v0.env
[ ! -L "$evidence" ] && [ "$(find "$evidence" -maxdepth 0 -type f -links 1 -print)" = "$evidence" ] || fail 'unsafe acquisition receipt'
case "$image_id" in sha256:*) ;; *) fail 'invalid acquired image identity' ;; esac
hex_digest "${image_id#sha256:}" || fail 'invalid acquired image identity'
[ "$(sed -n 's/^image_id=//p' "$evidence")" = "$image_id" ] || fail 'acquisition changed after image admission'

admit_input() {
    docker run --rm --network none --platform "$GB_LINUX_PLATFORM" \
        --workdir /input --env PYTHONPATH=/input/python:/input \
        --env PYTHONDONTWRITEBYTECODE=1 \
        --mount "type=bind,source=$source_root,target=/input,readonly" \
        --mount "type=bind,source=$native,target=/native-receipts,readonly" \
        "$image_id" python /input/tools/m2/verify_gate8_v2.py \
        linux-input --native-receipts /native-receipts
}
source_sha256=$(admit_input) || fail 'native receipt or installed transition admission failed'
hex_digest "$source_sha256" || fail 'invalid source identity'

docker run --rm --network none --platform "$GB_LINUX_PLATFORM" \
    --mount "type=bind,source=$source_root,target=/input,readonly" \
    --mount "type=bind,source=$native,target=/native-receipts,readonly" \
    --mount "type=bind,source=$evidence,target=/gate8-verifier-input,readonly" \
    --mount "type=bind,source=$output,target=/gate8-output" \
    "$image_id" sh /input/tools/linux/container-verify-v2.sh \
        /input "$expected_snapshot_sha256" /native-receipts /gate8-output \
        /gate8-verifier-input || fail 'clean Linux components or producer pair failed'

observed_snapshot_sha256=$(docker run --rm --network none --platform "$GB_LINUX_PLATFORM" \
    --mount "type=bind,source=$source_root,target=/input,readonly" \
    "$image_id" python /input/tools/linux/snapshot.py digest /input) || fail 'final snapshot failed'
[ "$observed_snapshot_sha256" = "$expected_snapshot_sha256" ] || fail 'host source changed during Linux verification'
[ "$(admit_input)" = "$source_sha256" ] || fail 'native inputs or source changed during Linux verification'

# Re-admit the exact exported set after the final host freeze check. These
# transient hashes are never inserted into the stable attestation or report.
docker run --rm -i --network none --platform "$GB_LINUX_PLATFORM" \
    --mount "type=bind,source=$output,target=/gate8-output,readonly" \
    --mount "type=bind,source=$evidence,target=/gate8-verifier-input,readonly" \
    "$image_id" python - "$source_sha256" "$expected_snapshot_sha256" /gate8-output /gate8-verifier-input <<'PY'
import hashlib,json,pathlib,stat,sys
def require(ok,reason):
    if not ok:raise ValueError('linux verification: '+reason)
def identity(value):
    return (value.st_dev,value.st_ino,value.st_mode,value.st_nlink,value.st_size,
            value.st_mtime_ns,value.st_ctime_ns)
out=pathlib.Path(sys.argv[3])
expected={'linux-python.json','linux-rust.json','verification.json'}
require({p.name for p in out.iterdir()}==expected,'output set')
def read(path,maximum,mode=0o644):
    before=path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size<=maximum,'unsafe output')
    require(mode is None or stat.S_IMODE(before.st_mode)==mode,'output mode')
    with path.open('rb') as stream:raw=stream.read(maximum+1)
    require(len(raw)==before.st_size and identity(path.lstat())==identity(before),'output changed')
    return raw
def canonical(raw):
    value=json.loads(raw)
    require(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()+b'\n'==raw,'noncanonical output')
    return value
receipts={name:read(out/(name+'.json'),1048576) for name in ('linux-python','linux-rust')}
record=canonical(read(out/'verification.json',4096))
acquisition=read(pathlib.Path(sys.argv[4]),4096,None)
require(record==dict(schema='golden-board.m2-linux-verification/v2',source_projection_sha256=sys.argv[1],
    acquisition_sha256=hashlib.sha256(acquisition).hexdigest(),host_snapshot_sha256=sys.argv[2],
    container_snapshot_sha256=sys.argv[2],components='pass',pair='pass',
    linux_receipt_sha256={k:hashlib.sha256(v).hexdigest() for k,v in receipts.items()}),'verification binding')
for producer,raw in receipts.items():
    value=canonical(raw)
    require(value['producer_id']==producer and value['source_projection_sha256']==sys.argv[1],'receipt binding')
PY
