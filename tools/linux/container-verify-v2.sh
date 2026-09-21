#!/bin/sh
# Private clean-Linux execution; never publishes a candidate or an attestation.
set -eu
umask 077
case "$#" in
    5) source_root=$1; expected_snapshot_sha256=$2; native=$3; output=$4; acquisition=$5 ;;
    *) printf 'usage: container-verify-v2.sh SOURCE_ROOT EXPECTED_SNAPSHOT_SHA256 NATIVE_RECEIPTS OUTPUT ACQUISITION\n' >&2; exit 2 ;;
esac
fail() { printf 'linux verify v2: %s\n' "$1" >&2; exit 1; }
[ "${#expected_snapshot_sha256}" = 64 ] || fail 'invalid execution-snapshot identity'
case "$expected_snapshot_sha256" in *[!0-9a-f]*) fail 'invalid execution-snapshot identity' ;; esac
[ "$(uname -s)/$(uname -m)" = Linux/aarch64 ] || fail 'Linux ARM64 required'
for directory in "$source_root" "$native" "$output"; do
    case "$directory" in /*) ;; *) fail 'directory is not absolute' ;; esac
    [ -d "$directory" ] && [ ! -L "$directory" ] || fail 'missing or linked mount'
done
[ "$(find "$output" -maxdepth 0 -type d -perm 0700 -print)" = "$output" ] || fail 'output mode is not 0700'
[ -z "$(find "$output" -mindepth 1 -maxdepth 1 -print -quit)" ] || fail 'output is not empty'
[ ! -L "$acquisition" ] && [ "$(find "$acquisition" -maxdepth 0 -type f -links 1 -print)" = "$acquisition" ] || fail 'unsafe acquisition'
PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=$source_root/python:$source_root
export PYTHONDONTWRITEBYTECODE PYTHONPATH
cd "$source_root"
source_sha256=$(python tools/m2/verify_gate8_v2.py linux-input --native-receipts "$native") || fail 'installed transition/native input admission failed'
[ "${#source_sha256}" = 64 ] || fail 'invalid source identity'
case "$source_sha256" in *[!0-9a-f]*) fail 'invalid source identity' ;; esac

private=$(mktemp -d "${TMPDIR:-/tmp}/golden-board-linux-v2.XXXXXX")
chmod 700 "$private"
target=$private/source
observed=$(python "$source_root/tools/linux/snapshot.py" materialize "$source_root" "$target")
[ "$observed" = "$expected_snapshot_sha256" ] || fail 'snapshot changed during transfer'
chmod 700 "$target"
# Preserve the raw index bound by the snapshot during read-only Git checks.
git -C "$target" config --local diff.autoRefreshIndex false
GIT_OPTIONAL_LOCKS=0
export GIT_OPTIONAL_LOCKS
observed=$(python "$target/tools/linux/snapshot.py" digest "$target")
[ "$observed" = "$expected_snapshot_sha256" ] || fail 'materialized snapshot differs'

# Acquisition is ignored provenance, copied before any component check.
verifier_target=$target/artifacts/linux/verifier-v0.env
[ ! -e "$verifier_target" ] && [ ! -L "$verifier_target" ] || fail 'acquisition target already exists'
mkdir -p "$target/artifacts/linux"
cp "$acquisition" "$verifier_target"
chmod 644 "$verifier_target"
cmp "$acquisition" "$verifier_target" >/dev/null || fail 'acquisition copy differs'
PYTHONPATH=$target/python:$target
export PYTHONPATH
cd "$target"
python - "$verifier_target" <<'PY'
from pathlib import Path
import sys
from golden_board.m2_gate8 import parse_linux_acquisition_receipt
parse_linux_acquisition_receipt(Path(sys.argv[1]).read_bytes(),Path('spec/gate8-policy-v0.toml').read_bytes())
PY
observed=$(python tools/linux/snapshot.py digest "$target")
[ "$observed" = "$expected_snapshot_sha256" ] || fail 'acquisition changed the source snapshot'
scripts/check components || fail 'component checks failed'

rustup run 1.97.1 cargo build -p gb-bootstrap --bin gb-m2-gate8-v2 \
    --release --locked --offline >"$private/rust-build.out" 2>"$private/rust-build.err" || {
    sed -n '1,80p' "$private/rust-build.err" >&2
    fail 'Rust producer build failed'
}
mkdir "$private/bin" "$private/pair"
cp target/release/gb-m2-gate8-v2 "$private/bin/gb-m2-gate8-v2"
chmod 500 "$private/bin/gb-m2-gate8-v2"
uv run --locked --offline --no-python-downloads python tools/m2/verify_gate8_v2.py \
    pair --kind linux --workers 8 --rust-binary "$private/bin/gb-m2-gate8-v2" \
    --work-root "$private/pair" --native-receipts "$native" || fail 'fresh Linux producer pair failed'

container_snapshot_sha256=$(python tools/linux/snapshot.py digest "$target")
[ "$container_snapshot_sha256" = "$expected_snapshot_sha256" ] || fail 'container source changed'
host_snapshot_sha256=$(python tools/linux/snapshot.py digest "$source_root")
[ "$host_snapshot_sha256" = "$expected_snapshot_sha256" ] || fail 'host source changed'
# Each producer froze its own source and executable. Only their admitted receipts
# leave this private container; full candidate/bundle trees are not host inputs.
python - "$private/pair" "$output" "$source_sha256" "$expected_snapshot_sha256" "$verifier_target" <<'PY'
from hashlib import sha256
import os
from pathlib import Path
import stat
import sys
from golden_board import canonical_manifest as manifest
from golden_board.m2_gate8_policy_v2 import load_gate8_policy_v2
from golden_board.m2_gate8_receipts_v2 import admit_producer_receipt_v2
from golden_board.m2_source_v2 import build_source_projection_v2
def require(ok,reason):
    if not ok:raise ValueError('linux export: '+reason)
def identity(value):
    return (value.st_dev,value.st_ino,value.st_mode,value.st_nlink,value.st_size,
            value.st_mtime_ns,value.st_ctime_ns)
pair,output=map(Path,sys.argv[1:3])
def read(path,maximum=1048576):
    before=path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and 0<before.st_size<=maximum,'unsafe pair output')
    require(stat.S_IMODE(before.st_mode)==0o644,'pair output mode')
    with path.open('rb') as stream:raw=stream.read(maximum+1)
    require(len(raw)==before.st_size and identity(path.lstat())==identity(before),'pair output changed')
    return raw
policy=load_gate8_policy_v2(Path('spec/gate8-policy-v2.toml').read_bytes())
source=read(pair/'source.json')
require(sha256(source).hexdigest()==sys.argv[3] and source==build_source_projection_v2(Path.cwd(),policy),'source binding')
receipts={name:read(pair/'receipts'/(name+'.json')) for name in ('linux-python','linux-rust')}
tables=[]
for producer,raw in receipts.items():
    value=manifest.validate_canonical_manifest(raw)
    paths=tuple(row['path'] for row in value['file_rows']
                if row['path']=='resource-limits.json' or row['path'].startswith('damage/'))
    value=admit_producer_receipt_v2(raw,policy,source,paths)
    require(value['producer_id']==producer,'receipt role')
    tables.append(manifest.serialize_manifest({'rows':value['file_rows']}))
require(tables[0]==tables[1],'receipt tables differ')
record=manifest.serialize_manifest(dict(schema='golden-board.m2-linux-verification/v2',
    source_projection_sha256=sys.argv[3],acquisition_sha256=sha256(read(Path(sys.argv[5]),4096)).hexdigest(),
    host_snapshot_sha256=sys.argv[4],container_snapshot_sha256=sys.argv[4],components='pass',pair='pass',
    linux_receipt_sha256={k:sha256(v).hexdigest() for k,v in receipts.items()}))
require(len(record)<=4096 and not list(output.iterdir()),'output changed')
for name,raw in [*((k+'.json',v) for k,v in receipts.items()),('verification.json',record)]:
    fd=os.open(output/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(raw);stream.flush();os.fchmod(stream.fileno(),0o644);os.fsync(stream.fileno())
fd=os.open(output,os.O_RDONLY|os.O_DIRECTORY)
try:os.fsync(fd)
finally:os.close(fd)
PY
