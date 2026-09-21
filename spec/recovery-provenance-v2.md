# Actual-observation recovery provenance v2

This finite producer connects the revised static carrier to the exact inputs
of knowledge-use-v2 and first-use-v2. It is not a gate receipt, physical proof,
human acquisition result or promotion. Historical development evidence and
its schemas remain unchanged. The caller independently constructs and admits
the source/static candidate; this component proves the recovery binding of
the supplied immutable bytes, not their origin merely from their hashes.

The pure constructor receives carrier.bin, candidate-manifest.json,
capacity-ledger.json, ownership-ledger.json and semantic-envelope.json, plus
the three exact neutral v2 policy byte strings. It receives no prefix, section,
body, content stream, saved decoder result or existing evidence. No file reads,
source/route/carrier builder, expected-result fallback or recovery cache supplies
any recovered value. A matching validator reruns the complete construction
and requires exact canonical provenance bytes.

## Admission and actual recovery

1. Bound each immutable JSON/policy input to1MiB before parsing; carrier.bin is
   at most524292 bytes including its four-byte count. Reuse the closed static
   input admission of physical-evidence-v2, without enumerating predicates.
   It checks candidate self identity, all supplied file hashes/lengths, table
   shapes, geometry, section/unit domains and cross-bindings. This is admission
   of those inputs, not a successful eight-predicate proof. Bind the three
   policy hashes to candidate source_identities and use strict neutral policy
   admission. Historical public policy/decoder admissions remain unchanged.
2. Require carrier bytes/hash equal its candidate file row and both ledgers;
   require its count S² and length4+S²/8 for the admitted side. Run the actual
   ObservationDecoderV2 / decode_observation_v2 with channel OBS_BITS and these
   exact bytes. Require profile8, established inventory, exact availability,
   both streams and every capacity section verified. Canonicalize that actual
   result using result-v2; do not create an expected result from static rows.
3. Require exactly four accepted hypotheses, one per sector0..3, transform0,
   polarity0 and profile8. The static candidate is in canonical physical
   orientation; this constructor is not a damaged/rotated-candidate adapter.
   Read each sector's first64 bytes from the actual packed matrix using the
   inherited sector-cell formulas at admitted S/W. The observed u32 prefix
   cell count at byte56 must be divisible by8, at least512, at most32768×8,
   and fit W(S−W). Extract exactly that prefix from the same matrix. Compare
   its bytes/hash with the corresponding candidate route row and its cell
   count with the ownership shell row. No route file supplies these bytes.
4. Require the recovered section-ID set equal the static capacity set. Decode
   each actual checked envelope and match section ID/type/version/closure/check,
   dependencies, payload/envelope length and hashes to its capacity row.
   Decode inventory2 with the public codec; its complete section set must agree.
   Decode every type3 body from that checked envelope through body-codec-v1,
   using its actual section version. Match the decoded byte length to capacity.
   Required/all bytes come directly from the actual observation result; their
   hashes must equal both static source-identity bindings. No stream assembly
   or content authoring supplies replacement bytes.
5. Run existing build_knowledge_use_v2 on the four extracted prefixes, actual
   geometry, both recovered streams and all decoded bodies. Its per-sector
   mapping commitments must equal the four accepted hypotheses and the SHA256
   of the canonical ownership mapping object. Then run build_first_use_v2 on
   those same extracted prefixes and geometry. These fresh checks retain their
   existing scopes; neither proof's output/schema is redefined here.

All section/body orders ascend ID. Body IDs are exactly16,17,18,100..163,
200..210 under inventory2. At most4096 section rows,2389 physical units and
78 decoded bodies are retained; each decoded body is at most16384 bytes and
the aggregate at most1048576. Each stream is4..1048576 bytes. Sector extraction
visits at most4×32768×8 cells. No output document exceeds1MiB. Use checked u64
arithmetic for lengths/products; booleans do not satisfy integer fields.

## Output and reusable recovered facts

Return immutable recovered prefix/body/stream bytes for later bundle creation,
the actual canonical decoder result, fresh knowledge/first-use bytes, and the
canonical provenance document. There is no filesystem or publication action.

The provenance has exactly schema,profile_id,scope,inputs,policy_sha256,
geometry,decoder_result,prefix_rows,stream_rows,body_rows,knowledge_use,
first_use,result. Values are:

* schema=`golden-board.m2-recovery-provenance/v2`, profile_id=
  `eh72-hier-r5-r2-r1-lzss-crc32c-v1`, scope=
  `actual-observation-to-carried-knowledge`, result=`pass` within that scope.
* inputs has candidate_manifest,capacity_ledger,ownership_ledger,
  semantic_envelope,carrier, each an identity object.
* policy_sha256 has exactly the three paths spec/profile-policy-v2.toml,
  spec/profile-limits-v2.toml,spec/damage-policy-v2.toml, each its raw SHA256.
* geometry has side,shell_width. decoder_result,knowledge_use,first_use are
  identity objects. An identity object has exactly bytes,sha256, referring
  to complete bytes (canonical JSON includes its final LF).
* prefix_rows has four rows in sector order, exactly sector_id,bytes,sha256.
* stream_rows has two rows, section_id2 then3, each section_id,bytes,sha256.
* body_rows has78 ascending rows, each section_id,section_version,envelope,
  stored,decoded; the last three are identity objects for the actual checked
  envelope, stored payload and decoded payload.

Canonical-manifest-v0 owns serialization. No proof hashes itself, and no
knowledge/first-use input points back to this provenance. Downstream promotion
must separately bind the complete source factory, fresh producer equality,
physical and damage evidence. This document supplies none of those passes.
