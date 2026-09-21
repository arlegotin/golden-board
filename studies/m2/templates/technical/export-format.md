# Export format

For each observation, return one UTF-8 JSON object followed by one line feed.
Use exactly these keys:

- `artifact_state`: `exact`, `degraded`, `ambiguous`, `failure`, or
  `resource-limit`;
- `claims`: an array of short strings in dependency order;
- `recovered_content_sha256`: the lowercase SHA-256 digest of the accepted
  complete ContentStream, or `none` if that stream is unavailable;
- `rival_hypotheses`: an array of short strings;
- `notes`: an array of short strings describing uncertainty or tool failure.

Keep the artifact state separate from stream availability. `exact` requires
both validated streams and every inventory-declared section. `degraded`
requires validated required content; complete content may also be available
while another section is unavailable. Without validated required content,
surviving sections alone do not justify `degraded`. Report ambiguity or a
resource limit when the checks support that conclusion.

Include runnable source, the command needed to run it, and the files it
actually writes. Identify required and complete streams separately, with
their lengths and hashes. Section envelopes and individual content records
are separate objects. Keep diagnostic sections separate from accepted streams;
do not create replacement bytes for unavailable content.

Answer each content query from that observation's accepted stream. Identify
the record references followed. If the requested data is unavailable, report
that rather than importing an answer from another observation. A requested
canonical Position export is 67 bytes: 64 cell bytes followed by turn,
castling rights and nominal en-passant code, with no operation-status prefix.
The target code is zero for none, otherwise the zero-based square index plus
one. The evaluator computes any project-specific position identity.

No names, dates, personal notes or complete terminal recording are requested.
Use relative file names in the summary; ordinary prose in the string fields
is sufficient. JSON uses `\u0000` for a null character, not `\0`.
