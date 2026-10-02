# Complete revised damage evidence

This owns the compact retained projection of damage-replay-v2. Producers first
source-build every observation, independently derive its semantic expectation,
run their language's observation-only receiver and require exact convergence.
Only then may they compact the complete row. A projection function cannot infer
that execution from a supplied hash. Production binds fresh source/executable
identities and independent whole-tree reproduction under the promotion owner.

The exact active physical-unit count Q comes from the admitted source-built
static candidate/capacity tuple. Derive accidental counts
`[16,4,256,128,Q,21,4Q,415]` in D0..D7 order and21 separate B0 probes.
All counts, ordered case identities and observation bytes are freshly generated
by damage-corpus-v2. Neither a caller-selected subset nor a saved manifest can
replace them. Validate each complete input row against its exact fresh case,
complete ascending source section IDs and required closure1,2,3,16,17,18.
No duplicate, missing, extra or reordered case is accepted.

## Compact cases and shards

A compact case has exactly observation (the unchanged identity object),
decoder_result_sha256, artifact_state, stream_rows, section_states,
wrong_accept_count, promise_result, resource_projection_sha256, resource and
adapter_rows. Hashes bind the complete canonical result and resource sidecar
including their trailing LF. stream_rows contains exactly
`[2,required_available,required_sha256]` and
`[3,all_available,all_sha256]`. section_states is the complete ordered array
`[section_id,state]`. Resource and22 adapter rows retain their exact meanings
and counters; the four shared source-owner hashes live in the root manifest.
They suffice to reconstruct and rehash every original resource sidecar.
Availability booleans remain booleans; all counters/IDs remain exact u64.

This is a retention projection, not a replacement decoder-result schema.
Complete result bytes and complete replay rows are independently regenerated
during every producer/release run. Never compare only the compact projections
when asserting decoder/source-oracle agreement.

Each compact case is at most262144 bytes when serialized as a canonical object
with LF. Retain shards in case order, at most32 cases and524288 canonical bytes
per shard. Greedily append until the next case would exceed either bound, then
close the current shard. No empty shard. A single bounded case always fits.
Shards are `damage/{family}/{zero-based-shard-index-as-six-digits}.json`.
Each has exactly schema `golden-board.m2-damage-shard/v2`, profile_id,
family_id, first_ordinal, case_count and cases. Shards may not span families.
Use at most4096 files and536870912 total emitted bytes for this evidence tree;
these serialization bounds add no recovery promise or relaxed runtime ceiling.

## Family and root documents

`damage/{family}/manifest.json` has exactly schema
`golden-board.m2-damage-family/v2`, profile_id, carrier_sha256, family_id,
case_count, wrong_accept_count, failed_promise_count, result, cases_sha256 and
shards. cases_sha256 hashes concatenated compact canonical case objects, each
with its LF, in family order. Each shard row has path, bytes, sha256,
first_ordinal and case_count; paths are exact and sorted by ordinal.

An accidental family passes iff all its case promises pass and its wrong
accept count is zero. D7 additionally requires all four fresh boundary KATs.
B0 requires all21 converged rows; its wrong count remains a reauthenticated
diagnostic and is excluded from accidental totals. Preserve failed family
results. No threshold, case or seed may be replaced to obtain a pass.

`damage/boundary-kats.json` has exactly schema
`golden-board.m2-boundary-kats/v2`, profile_id and rows. Rows are the four
boundary-kat-v2 objects in the owned order, each wrapped as kat_id, result,
bytes and sha256; the hash/length cover the exact original canonical KAT
receipt. Both implementations produce these receipts from their own fixtures.
This file does not change D7's case count or add independence witnesses.

`damage/manifest.json` has exactly schema `golden-board.m2-damage-manifest/v2`,
profile_id, candidate_manifest_sha256, carrier_sha256, source_owners,
required_section_ids, section_ids, physical_units, accidental_case_count,
boundary_case_count, wrong_accept_count, result, corpus_sha256,
complete_replay_sha256, resource_limits_sha256, family_rows,
reauthored_boundary and boundary_kats. source_owners is exactly the four
accounting owners from the sidecars. corpus_sha256 hashes concatenated complete
observation identities with LF; complete_replay_sha256 hashes concatenated
complete damage-replay-v2 rows with LF. All three hashes are freshly computed
from the same ordered execution, not supplied as unchecked strings.
family_rows contains exactly eight rows, each family_id, case_count,
wrong_accept_count, result, path, bytes and sha256 of its family manifest.
reauthored_boundary has that same row shape for B0. boundary_kats is path,
bytes and sha256 of its manifest. Root result passes iff all eight accidental
families and the complete B0 projection pass. Retain the measured complete
resource aggregate separately as resource-limits.json.

All JSON uses canonical-manifest-v0 bytes. Strict retained admission rehashes
every named file, rejects unlisted/missing paths and recomputes compact counts,
promises, family results, reconstructed resource sidecars and maxima. It must
also bind the root candidate/capacity/complete-source identities; directory
presence or cross-language agreement on a malformed object never admits it.
Production additionally compares complete fresh executions. Every write occurs
inside private staging; a mismatch or partial iterator publishes no success.
The compact projection cannot reconstruct omitted full decoder result fields
or the complete replay hash. Retained admission checks that hash's shape and
the surrounding exact candidate/tree binding; only fresh complete execution
can reproduce it. It must never advertise retained admission as that execution.

## Complete independence wrapper

The existing physical-evidence-v2 eight rows stay unchanged and independently
usable. A complete proof binds their exact raw bytes, the same static input
hashes, fresh recovery-provenance/knowledge/first-use premise and the complete
damage-manifest identity. Its ninth row is damage-promise-binding, with one
witness for every D0..D7 case and none for B0 or the four KATs.
The inherited family-pass rule remains: every case in a nonpassing accidental
family contributes a violation. Consequently a failing boundary KAT makes all
415 D7 witnesses violate. Zero violations and every positive owned witness
count are necessary for pass. The outer gate order reaches this proof only
after Gates1–6 pass; an unrun proof remains not_evaluated.

The complete constructor receives the four static documents, their carrier,
three neutral policies, the source-built corpus and bounded read/names access
to the just-generated complete damage tree. It reconstructs and admits that
tree, independently runs physical-evidence-v2 from the four raw static inputs,
and runs recovery-provenance-v2 from the carrier/static/policy inputs. Neither
saved physical rows nor supplied recovery/knowledge/first-use results are
generation inputs. The production caller additionally enforces fresh complete
damage execution and gate order; retained tree admission alone is not that
execution. The proof's validator repeats this construction and compares bytes.

The canonical document has exactly schema=
`golden-board.m2-independence-proof/v2`, profile_id, input_sha256,
physical_evidence, recovery_provenance, knowledge_use, first_use,
damage_manifest, predicate_rows and result. input_sha256 is the same four-key
object as the fresh physical evidence. The five evidence identities each have
exactly bytes and sha256 of their complete canonical bytes. predicate_rows
contains the eight freshly computed physical rows, unchanged, followed by
damage-promise-binding. The ninth row has the same five keys as a physical row;
minimum_surviving_count=1, witness_count=sum of all eight accidental counts,
violation_count=sum of case_count for every failed accidental family, and
result=pass iff the witness count is positive and violation_count=0.
Overall result=pass iff all nine rows pass. A caller may inspect a diagnostic
failed proof, but it cannot advance the production gate sequence past failure.
No placeholder row or cached count substitutes for a fresh predicate.
