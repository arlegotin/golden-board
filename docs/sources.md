# M0 source ledger

This ledger says exactly what M0 used and what that evidence does not prove.
Machine identities are owned by [`inputs/source-lock.toml`](../inputs/source-lock.toml);
ordinary checks use those frozen receipts and never fetch an external source.

| Source | Edition, locator, and locked identity | Role and supported conclusion | Does not establish | Retention and rights |
|---|---|---|---|---|
| *Sixty-Four Masterpieces of Chess*; Golden Board project | Current tracked bytes; [`anthology`](../inputs/source-lock.toml) | Authoritative M0 input; fixes the exact file inspected by the source doctor | Provenance, redistribution permission, PGN/SAN validity, chess legality, or final artifact content | Tracked payload. Upstream provenance and redistribution basis remain unresolved. |
| *FIDE Laws of Chess taking effect 1 January 2023*; International Chess Federation (FIDE) | Effective 2023-01-01; [official PDF](https://rcc.fide.com/wp-content/uploads/2022/11/Laws_of_Chess-2023.pdf); accessed 2026-08-14; [`fide-laws-2023`](../inputs/source-lock.toml) | Frozen future authority for the orthodox chess rules M1 may select explicitly | Golden Board conformance, its practical rule subset, source grammar, or redistribution permission | Receipt only; external bytes are not vendored; redistribution not established. |
| Steven J. Edwards, *Portable Game Notation Specification and Implementation Guide* | Revised 1994-03-12; [preserved text](https://archive.org/download/pgn-standard-1994-03-12/PGN_standard_1994-03-12.txt); accessed 2026-08-14; [`pgn-guide-1994`](../inputs/source-lock.toml) | Historical background for PGN tags, movetext, SAN, and result markers | A maintained standards-body grammar or Golden Board's accepted grammar | Receipt only; external bytes are not vendored; redistribution not established. |
| NIST, *FIPS PUB 180-4: Secure Hash Standard* | 2015 update; [official PDF](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.180-4.pdf); accessed 2026-08-14; [`nist-fips-180-4`](../inputs/source-lock.toml) | Defines SHA-256 | The correctness or conformance of either Golden Board implementation | Receipt only; external bytes are not vendored; redistribution not established. |
| NIST CAVP byte-oriented Secure Hash vector archive | Frozen download; [official ZIP](https://csrc.nist.gov/CSRC/media/Projects/Cryptographic-Algorithm-Validation-Program/documents/shs/shabytetestvectors.zip); accessed 2026-08-14; [`nist-sha-byte-vectors-archive`](../inputs/source-lock.toml) | Container provenance for the consumed SHA-256 known answers | NIST validation of Golden Board or authority over identity framing | Receipt only; archive is not vendored; redistribution not established. |
| NIST CAVP `shabytetestvectors/SHA256ShortMsg.rsp` | CAVS 11.0, generated 2011-03-15; member of the locked archive; [`nist-sha256-short-message-vectors`](../inputs/source-lock.toml) | Independent basis for the retained empty-message and one-byte `d3` SHA-256 cases | Coverage beyond those cases, project conformance, or formal CAVP validation | Receipt only; only two small attributed values are retained; redistribution not established. |

## Boundaries

- The historical PGN guide is not the Golden Board grammar; M1's
  `spec/source-v0.md` will own that contract.
- CRC, ECC, interleave, transport, and profile material remains only a roadmap
  reading list until M2 has a concrete consumer and measured choice.
- References inform decisions; they do not prove Golden Board conformance.
- Ordinary checks are offline and do not refetch moving pages or frozen files.
- Local read-only M0/M1 analysis may continue while anthology provenance and
  redistribution rights are unresolved.

A locator proves provenance, not permission, and an owner risk decision is not
permission either. Further public redistribution of the anthology or derived
collection requires source provenance plus an applicable licence, permission,
public-domain status, or another concrete rights basis for the exact retained
material. Material without that basis must be removed or narrowed before such a
release.
