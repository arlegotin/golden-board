# Distribution and licences

Project code uses [MIT](../../LICENSE). The original message, explanatory content
and original illustrations use [CC BY-NC 4.0](../../LICENSE-CONTENT.md). Third-party
materials keep their own terms.

The original content may be shared and adapted for noncommercial purposes with
attribution. Commercial use of that content requires separate written permission
from the copyright holder identified in the [README](../../README.md). The code's
MIT licence permits commercial use of the software.

| Component | Included material and terms |
|---|---|
| chess 1.11.2 | Complete pinned source archive and GPL-3.0-or-later licence |
| chess.js 1.4.0 | Complete pinned archive and BSD-2-Clause notice |
| setuptools 80.9.0 | Exact wheel, MIT licence and bundled notices |
| Anthology | One PGN input, its source metadata and exact-byte lock |

[Third-party notices](../../THIRD_PARTY_NOTICES.md) link the archives and accessible
licence text. The Python construction pipeline imports chess; its GPL terms remain
applicable. No chess dependency is embedded in the generic JavaScript mechanism.
The project licence does not relicense dependencies.

## Source provenance

[inputs/lock.json](../../inputs/lock.json) pins the exact anthology bytes, source
order and record count. The supplied metadata is retained in the PGN and
[human game index](game-index.md), while the message carries moves, minimal scores
and literal playback only. No independent upstream collection licence or source
URL accompanies the input. Move/state verification establishes technical fidelity,
not a legal conclusion about redistribution.

## Reproduction scope

The public source tree includes the current runtime, exact package inputs,
qualified source derivatives, literal vectors, tests and documentation needed to
reproduce the final artifact. Python 3.14 and Node 22 are host prerequisites.
Follow [build and development](build.md); the
[verification summary](../release/verification.json) records measured outputs.

[Development findings](../history/experiments.md) describe important investigations
and their limits. They are technical summaries rather than a complete public
trial dataset. Current native checks can be rerun from this checkout; historical
model demonstrations are not rerun by the build.
