# Profile-8 carrier construction — development owner

This owner composes slice-v1, bootstrap-v2, body-codec-v1 and route-v2 without
changing historical candidate bytes. It authorizes deterministic development
construction, not promotion or a passing gate. Full independent generation,
limits, knowledge-use, accidental damage and lifecycle evidence remain required.

Logical capacity derives from the existing candidate-neutral curriculum/role
policy and historical capacity prototypes, with the actual new slice lengths.
All 105277 future authoring bytes remain. Let C be the uncompressed body and
tier payload bytes plus the complete16384-byte inventory allowance and future
authoring bytes. Reserve is `max(382,ceil(C/19))`; the present slice gives9353.
No compression saving reduces this promise. Probe payloads are never compressed.

Real bodies are whole-record section assignments of slice-v1. Independently
encode each with body-codec-v1, selecting its version1 bytes only if strictly
shorter than the raw version0 body. Tier frames preserve exact decoded lengths,
record counts, body IDs and terminal ROOT frames. Their sections stay version0.
All stored payloads are1..16384 bytes. Whole-unit factors are5 for inventory,
both tiers and bodies16/17/18;1 for other bodies; capacity factor2 for
replicated-core0-2 and1 for nonreplicated-core3-4; reserve2; load1.

Probe IDs start211. Iterate the candidate-neutral capacity envelope's buckets
and their sections in owned order, omitting zero-length needs. Then append
reserve partitions and load partitions. Actual body IDs retain their slice
assignments. Sort final sections by numeric ID. All semantic copy IDs are0.
Inventory2 includes itself and every section. Its exact payload length is
`8+20*entry_count+4*dependency_count`, bounded by16384; only the two tiers
have dependencies, exactly their body sets. Section/envelope length is
`18+4*dependency_count+payload_bytes+4`, so fragment count is its ceiling/157.

Search side64..2048 ascending by8 and width8..min(128,(side-8)//2) ascending
by8. Each geometry must admit all four actual route prefixes plus unchanged
headroom and the exact table17/full mapping domains. Let Q=floor((S-2W)^2/1728).
For each geometry try load-section count ascending from zero, bounded by both
4096 total entries and inventory payload size. Recompute inventory length and
factor-five fragment charge for that count. Subtract all mandatory physical
units from Q. The residual must be zero for zero load sections, or admit at
least one fragment per load section and at most105 fragments per section.
The first admissible count is selected. Greedily allocate each load section
up to105 fragments while leaving one per later section; its payload is
`min(16384,157*fragments-22)`. Refragmentation must give exactly that count.
The first geometry satisfying all constraints is the construction geometry;
every earlier failure remains available in a bounded search ledger.

Probe bytes followed by interior pad bytes use the existing bounded
`GB-M2-FILL-v0\0 || decoded_all_stream_sha256_bytes || counter:u64` SHA256
stream, counter starting0. Consume capacity, reserve, then load payloads in
assigned-ID order; pad consumes the immediately following bits, MSB first.
The mandatory decoded transport pad remains a separate zero byte.

Encode each sorted section's envelope and fragments, then replicate each
entire216-byte EH72 unit according to its factor before proceeding to the next
fragment. Physical IDs start1. The five first IDs are the first inventory
fragment. The complete physical count must equal Q. Place unit/bit by the
full profile8 mapping; place deterministic tail bits at affine images of
logical indices1728Q..I²-1. The four oriented shell sectors occupy the remaining
cells. Every cell has exactly one owner; no hole, overlap, omitted probe or
unaccounted padding is allowed. Hard maximum remains2048² bits/512KiB.
The stored carrier retains the existing four-byte big-endian cell count,
followed by the row-major MSB packed square matrix. These four framing bytes
are outside the physical artifact; the side is the exact integer square root.
This is distinct from the supplied participant CELL_MATRIX observation ABI,
which uses a u16 side and unpacked observation cells.

Clean recovery must extract observations from the actual matrix, independently
decode EH/common/envelope/inventory/tier/content, and recover the exact source
streams. It cannot reuse builder section dictionaries as decoder inputs or
substitute saved learner bytes. This development roundtrip is necessary but
does not replace fresh full damage or Gate8/release evidence.
