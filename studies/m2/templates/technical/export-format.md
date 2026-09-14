# Export format

Return one UTF-8 JSON object followed by one line feed. Use exactly these keys:

- `artifact_state`: `exact`, `degraded`, `ambiguous`, `failure`, or
  `resource-limit`;
- `claims`: an array of short strings in dependency order;
- `recovered_content_sha256`: a lowercase SHA-256 digest or `none`;
- `rival_hypotheses`: an array of short strings;
- `notes`: an array of short strings describing uncertainty or tool failure.

Do not include raw private notes, timestamps, names, or machine-specific paths.
