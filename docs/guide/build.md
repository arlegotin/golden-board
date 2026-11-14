# Reproduction and development

The supported host is **Python 3.14 and Node 22**. The builder uses chess 1.11.2;
chess.js 1.4.0 is a separate original-SAN reference checker. Setuptools 80.9.0
supports offline installation. Exact original archives, hashes and notices are
retained under [inputs/dependencies](../../inputs/dependencies/lock.json).
No npm installation, browser, network index or private cache is required.
The repository disables automatic Git line-ending conversion to preserve artifact
and hash-bound source bytes across checkouts.

## Start from a clean checkout

From the repository root:

```sh
python3.14 gb setup --offline
./gb verify
./gb check fast
```

The first command creates `.venv/` and installs from retained archives with
`--no-index`, `--no-cache-dir` and required hashes. Missing or changed archives
fail before installation. Python and Node themselves must already be installed;
the project does not distribute those host runtimes.

`gb` reexecutes through the local environment when it exists. `build/` is generated
scratch output and is created when needed. The `gb build`, `reproduce` and extraction commands refuse existing output
destinations, preserving prior diagnostics and user files. Low-level file writers
and headless JS export helpers write their explicit output path; use fresh paths.

## Rebuild the exact final message

```sh
./gb reproduce --output build/reproduced
```

The current Python pipeline authors lessons, imports exact qualified derivatives,
checks frames/actions through Node, assembles the square and writes:

```text
build/reproduced/
  GOLDEN-BOARD.bitplane    # equal to artifacts/GOLDEN-BOARD.bin
  serial.txt               # equal to artifacts/GOLDEN-BOARD.txt
  GOLDEN-BOARD.png          # equal to artifacts/GOLDEN-BOARD.png
  documents/1.bin ... 5.bin
  content/                 # authored groups/cases/bindings/truth
  layout.json, content-ledger.json, report.json, COMPLETE.json
  REPRODUCED.json
```

`reproduce` requires byte equality for all three forms and the five body hashes.
`./gb build --output build/candidate` runs the same builder without asserting the
result against the frozen release. Its report deliberately remains native and
`release_ready:false`: automated generation does not reperform recipient trials.
It never overwrites the canonical set.

Qualified foundation/anthology/source derivatives are required retained inputs,
listed in [architecture](architecture.md). A reproduction from them is not a claim
to recreate every earlier research result. Full original-SAN qualification is
separately available below. Historical developer labels in reports are not fields
inside the carried grammar.

## Check established behavior

```sh
./gb check fast
./gb check integration
./gb check focused source
./gb verify --transforms
```

Fast checks exercise current codec, carrier, foundation, canonical integrity and
CLI behavior plus generic JS mechanism tests. Integration runs all retained
Python regression modules, the generic JS tests and the pinned reference-package
smoke. It includes complete build identity and deterministic repeat construction.
Focused source checks additionally replay every original SAN through Python and
chess.js, compare every-ply state, then verify literal playback. This is stronger
than a PGN hash or final-board comparison.

Other focused areas are `rules`, `content`, `carrier`, `player` and `artifacts`.
The old `protocol` scope and trial/explorer commands were retired with their
subsystems. None of the supported checks launches a recipient trial. Logs under
`build/checks/` state actual test counts, failures, source identity and scope.

The original reference distinguishes immediately recorded en-passant FEN targets
from legally usable en-passant rights. Its explicit projection resolves package
representation differences without changing a move or defining repetition by an
unusable target. See [games](games.md).

## Regenerate the guide images

The [bootstrap illustrations](bootstrap.md) are exact crops of the canonical BIN.
Regenerate all four panel sheets and the complete strip into a fresh directory:

```sh
python3.14 tools/render-guide-images.py --output build/guide-images
```

The sheets enlarge each panel four times with white margins and gutters. They add
no corner digits or captions; all marks inside the original panels are preserved.
The complete strip is enlarged eight times. The generator checks the source hash,
uses the existing binary PNG renderer and refuses an existing output directory.

## Inspect and operate documents offline

```sh
./gb inspect
./gb inspect --output build/documents
```

Inspection first verifies the canonical forms and complete native extraction.
It lists document roots, record counts and hashes; with `--output`, it writes the
five exact bodies and an inventory to a new directory.

The generic mechanism can operate those files directly. For the miniature, first
create a fresh example directory (the following low-level helpers write files):

```sh
mkdir build/mini-example
python3.14 -c "from pathlib import Path; Path('build/mini-example/mini.bin').write_bytes(bytes.fromhex(Path('spec/vectors/current-mini.hex').read_text()))"
python3.14 -c 'import json; from pathlib import Path; Path("build/mini-example/request.json").write_text(json.dumps({"entry":512,"actions":[{"select":10},{"commit":True}]}))'
node mechanism/relay.mjs build/mini-example/mini.bin build/mini-example/request.json build/mini-example/packet.json
```

`packet.json` records literal frames, glyphs, current selection/commitment and
successful/refused operations. `Player` also exports `renderSvg(packet)` for
standalone frame inspection. [passive.mjs](../../mechanism/passive.mjs) exports
complete reachable passive routes; [catalog-relay.mjs](../../mechanism/catalog-relay.mjs)
maintains document selection and action history across a request list. These
consume only carried data and neutral actions; they supply no chess answers.
There is no supported browser application in this repository.

## Maintain or extend independently

Read [architecture](architecture.md), [the grammar](format.md), the practical
[chess profile](../../spec/chess.md), [predicates](../../spec/predicates.md) and
[coverage](../../content/coverage.toml) before changing semantics. Preserve original
source moves separately from editorial metadata, native reconstruction separately
from interpretation evidence, and exact predicates separately from heuristics.

Work on a separately named candidate. Add a focused regression for a demonstrated
risk, inspect critical intermediate states and compare the complete affected
output. Do not update a hash merely to make qualification pass. Historical receipts
refer to exact historical source; changing active code requires current evidence
rather than retroactive alteration. Source changes require new source identity and
all affected source/teaching/playback checks. Future research needs a separate scope and evidence from the immutable final set.

The [release verification record](../release/verification.json) identifies the
actual checks performed after curation, including a fresh source export without
ignored/private/build inputs. It states the host and practical limits of those
results rather than promising every future platform will emit identical wrappers.
