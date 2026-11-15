# Distribution and licences

Original project code uses the
[Golden Board Noncommercial Software License](../../LICENSE). The original
message, explanatory content and original illustrations use
[CC BY-NC 4.0](../../LICENSE-CONTENT.md). Third-party materials keep their own terms.

Original code and content may be shared, studied, modified and built upon for
noncommercial purposes, with attribution and the required licence notices.
Commercial use of either requires prior written permission from Artem Legotin
under a separate agreement. Noncommercial status depends on the purpose of the
use, not simply whether access is free or the user is a nonprofit. Applicable
copyright exceptions and permissions already granted under another licence
remain unaffected.

| Component | Included material and terms |
|---|---|
| chess 1.11.2 | Complete pinned source archive and GPL-3.0-or-later licence |
| chess.js 1.4.0 | Complete pinned archive and BSD-2-Clause notice |
| setuptools 80.9.0 | Exact wheel, MIT licence and bundled notices |
| Anthology | One PGN input, its source metadata and exact-byte lock |

[Third-party notices](../../THIRD_PARTY_NOTICES.md) link the archives and accessible
licence text. The Python construction pipeline imports chess. The noncommercial
software licence is not GPL-compatible: distributing a combined work requires
separate permissions that resolve that incompatibility. Preserving a GPL notice
or obtaining the project author's commercial permission alone is insufficient.
The retained third-party archives keep their original terms. No chess dependency
is embedded in the generic JavaScript mechanism. The project licence does not
relicense dependencies or establish rights to third-party material.

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
