# Project source ledger

This ledger says exactly what M0/M1 used and what that evidence does not prove.
Machine identities are owned by [`inputs/source-lock.toml`](../inputs/source-lock.toml);
ordinary checks use those frozen receipts and never fetch an external source.

## M0 locked sources

| Source | Edition, locator, and locked identity | Role and supported conclusion | Does not establish | Retention and rights |
|---|---|---|---|---|
| *Sixty-Four Masterpieces of Chess*; Golden Board project | Current tracked bytes; [`anthology`](../inputs/source-lock.toml) | Authoritative M0 input; fixes the exact file inspected by the source doctor | Provenance, redistribution permission, PGN/SAN validity, chess legality, or final artifact content | Tracked payload. Upstream provenance and redistribution basis remain unresolved. |
| *FIDE Laws of Chess taking effect 1 January 2023*; International Chess Federation (FIDE) | Effective 2023-01-01; [official PDF](https://rcc.fide.com/wp-content/uploads/2022/11/Laws_of_Chess-2023.pdf); accessed 2026-08-14; [`fide-laws-2023`](../inputs/source-lock.toml) | Frozen future authority for the orthodox chess rules M1 may select explicitly | Golden Board conformance, its practical rule subset, source grammar, or redistribution permission | Receipt only; external bytes are not vendored; redistribution not established. |
| Steven J. Edwards, *Portable Game Notation Specification and Implementation Guide* | Revised 1994-03-12; [preserved text](https://archive.org/download/pgn-standard-1994-03-12/PGN_standard_1994-03-12.txt); accessed 2026-08-14; [`pgn-guide-1994`](../inputs/source-lock.toml) | Historical background for PGN tags, movetext, SAN, and result markers | A maintained standards-body grammar or Golden Board's accepted grammar | Receipt only; external bytes are not vendored; redistribution not established. |
| NIST, *FIPS PUB 180-4: Secure Hash Standard* | 2015 update; [official PDF](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.180-4.pdf); accessed 2026-08-14; [`nist-fips-180-4`](../inputs/source-lock.toml) | Defines SHA-256 | The correctness or conformance of either Golden Board implementation | Receipt only; external bytes are not vendored; redistribution not established. |
| NIST CAVP byte-oriented Secure Hash vector archive | Frozen download; [official ZIP](https://csrc.nist.gov/CSRC/media/Projects/Cryptographic-Algorithm-Validation-Program/documents/shs/shabytetestvectors.zip); accessed 2026-08-14; [`nist-sha-byte-vectors-archive`](../inputs/source-lock.toml) | Container provenance for the consumed SHA-256 known answers | NIST validation of Golden Board or authority over identity framing | Receipt only; archive is not vendored; redistribution not established. |
| NIST CAVP `shabytetestvectors/SHA256ShortMsg.rsp` | CAVS 11.0, generated 2011-03-15; member of the locked archive; [`nist-sha256-short-message-vectors`](../inputs/source-lock.toml) | Independent basis for the retained empty-message and one-byte `d3` SHA-256 cases | Coverage beyond those cases, project conformance, or formal CAVP validation | Receipt only; only two small attributed values are retained; redistribution not established. |

## M1 design references

These references informed [`docs/m1-spec.md`](m1-spec.md). They are not runtime
inputs, expected-answer generators, or substitutes for project specifications
and conformance evidence, so M1 does not add mutable copies to the source lock.

| Source and locator (accessed 2026-08-14) | Design use | Does not establish | Retention |
|---|---|---|---|
| Miguel Ambrona, “A Practical Algorithm for Chess Unwinnability,” FUN 2022, [DOI](https://doi.org/10.4230/LIPIcs.FUN.2022.2) | Shows why broad unwinnability/dead-position inference is harder than a casual material rule; supports the deliberately closed common-dead subset | Correctness of Golden Board's subset or any unimplemented general classifier | Citation only; no external bytes vendored. |
| Niklas Fiekas and the python-chess project, python-chess 1.11.2 [core API documentation](https://python-chess.readthedocs.io/en/latest/core.html) | Documents the isolated development oracle's permissive SAN/push/FEN/outcome boundaries | Wire/source authority, tracked expected answers, or project conformance | Citation plus development-only lock when M1 implements the oracle; never runtime/artifact input. |
| John Sweller and Graham A. Cooper, “The Use of Worked Examples as a Substitute for Problem Solving in Learning Algebra” (1985), [DOI](https://doi.org/10.1207/s1532690xci0201_3); Robert K. Atkinson, Alexander Renkl, and Mary Margaret Merrill, “Transitioning From Studying Examples to Solving Problems: Effects of Self-Explanation Prompts and Fading Worked-Out Steps” (2003), [DOI](https://doi.org/10.1037/0022-0663.95.4.774) | Background for worked examples, fading, and explicit novice guidance | Effectiveness of Golden Board or a mandatory lesson count | Citations only; no external bytes vendored. |
| Michelene T. H. Chi, Miriam Bassok, Matthew W. Lewis, Peter Reimann, and Robert Glaser, “Self-Explanations: How Students Study and Use Examples in Learning to Solve Problems” (1989), [DOI](https://doi.org/10.1207/s15516709cog1302_1) | Motivates bounded reason selection/self-explanation prompts while keeping claims faithful to the actual interface | That finite selections measure unrestricted natural-language explanation | Citation only; no external bytes vendored. |
| Henry L. Roediger III and Jeffrey D. Karpicke, “Test-Enhanced Learning: Taking Memory Tests Improves Long-Term Retention” (2006), [DOI](https://doi.org/10.1111/j.1467-9280.2006.01693.x); Lindsey E. Richland, Nate Kornell, and Liche S. Kao, “The Pretesting Effect: Do Unsuccessful Retrieval Attempts Enhance Learning?” (2009), [DOI](https://doi.org/10.1037/a0016496); Andrew C. Butler and Henry L. Roediger III, “Feedback Enhances the Positive Effects and Reduces the Negative Effects of Multiple-Choice Testing” (2008), [DOI](https://doi.org/10.3758/MC.36.3.604) | Supports treating pre/post tests as learning events and withholding result feedback through delayed measurement | Artifact-only causation, durable retention, or the project's exact delay/form policy | Citations only; no external bytes vendored. |
| American Educational Research Association, American Psychological Association, and National Council on Measurement in Education, *Standards for Educational and Psychological Testing* (2014 edition), [PDF](https://www.testingstandards.net/uploads/7/6/6/4/76643089/standards_2014edition.pdf); National Board of Medical Examiners, *Item-Writing Guide: Constructing Written Test Questions for the Health Sciences*, sixth edition (preface August 2020; PDF cover October 2024), [PDF](https://www.nbme.org/sites/default/files/2021-02/NBME_Item%20Writing%20Guide_R_6.pdf) | Guardrails for a declared blueprint, held-out cases, scoring, response cues, and narrow interpretation | Psychometric equivalence, population inference, or validation of Golden Board's forms | Citations only; no external bytes vendored. |
| IETF RFC 8949, *Concise Binary Object Representation (CBOR)* (December 2020), [official text](https://www.rfc-editor.org/rfc/rfc8949.html) | Background for definite-length deterministic framing; M1 deliberately uses a much smaller project grammar | CBOR compatibility or a reason to add a CBOR implementation/dependency | Citation only; no external bytes vendored. |

## Boundaries

- The historical PGN guide is not the Golden Board grammar; M1's
  `spec/source-v0.md` will own that contract.
- M1 design references above remain explanatory citations unless a later
  implementation consumes exact external bytes; such a consumer must first add
  a locked receipt and rights note.
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
