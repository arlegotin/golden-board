# Third-party materials

Project licensing does not replace upstream terms. Exact archives and hashes are
retained in [inputs/dependencies/lock.json](inputs/dependencies/lock.json).
Original archive notices remain authoritative.

- `chess-1.11.2.tar.gz`: GPL-3.0-or-later; complete original source and
  [licence](licenses/third-party/chess-LICENSE.txt) are included.
- `chess.js-1.4.0.tgz`: BSD-2-Clause;
  [notice](licenses/third-party/chess.js-LICENSE.txt).
- `setuptools-80.9.0-py3-none-any.whl`: MIT and bundled notices;
  [extracted notices](licenses/third-party/setuptools/).

The Python builder imports chess. The project's
[noncommercial software licence](LICENSE) does not replace its GPL terms and
is not GPL-compatible. Distribution of a combined work requires separate
permissions that resolve this incompatibility; retaining the GPL notice or
obtaining the project author's commercial permission alone does not resolve it.
The retained third-party archives and licence texts keep their original terms.

The anthology is retained as [PGN](inputs/anthology.pgn), with exact source identity
in [inputs/lock.json](inputs/lock.json). Technical legality and replay checks do not
establish redistribution rights. See [distribution](docs/guide/distribution.md).
