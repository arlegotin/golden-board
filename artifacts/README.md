# Private retained evidence

Read [M2.5 closeout](../docs/m2.5-closeout.md) for the retention map and offline
restoration, and [M2 results and lessons](../studies/m2/participant-learnings-v1.md)
for conclusions. Current status belongs to the [roadmap](../docs/roadmap.md).

- `candidates/` holds the one complete qualified v1 candidate.
- `gate8/` holds its exact original projections, receipts and recipient bundles.
- `linux/` holds acquisition evidence and legacy snapshots still read by tests.
- `executables/` preserves the exact original receipt-bound native Rust binary
  before deletion of the Cargo cache; fresh production builds its own binary.
- `history/` holds the unchanged pinned transition/clarification archives and
  explicitly compacted historical records. A historical manifest does not mean
  every original file is still installed; use the closeout's preimage map.
- `quiz/` holds private authored study evidence and the compact final independent
  proof. Earlier working expansions were removed after their learning and
  assistance history were consolidated. No folder's presence establishes a pass.
- `.m2.5-preservation.json` and `.m2.5-work/` record preservation, removal mappings
  and bounded verification. They are cleanup evidence, not candidate inputs.

Keep frozen manifest-owned trees exact. Put future disposable generation in a
clearly named working directory and retain only evidence needed by its owning
contract. Do not publish participant material from this private folder.
