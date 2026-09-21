# M2 participant-revision slice v1 (development contract)

This is a new slice. It does not change slice-v0 bytes, its completed trials,
or the identity of any released candidate. Promotion and fresh carrier gates
are required before this slice has a Candidate-ready claim.

The canonical-manifest-v0 declaration has exactly `schema`,
`legacy_declaration_sha256`, and `lesson_records`. The schema is
`golden-board.m2-slice/v1`. The legacy digest binds the unchanged slice-v0
declaration. Both independent compilers validate that declaration and its six
source inputs using their v0 compiler, obtaining the same 64 complete games,
ten binary chess fixtures, curriculum families and capacity prototypes.
Neither compiler consumes the other compiler's binary output.

`lesson_records` is a nonempty array of at most 4096 logical content-v0 records,
with consecutive IDs starting at one. Its final record is its only ROOT.
Each record has exactly `record_id`, `kind`, and `payload`. The payload uses
the public content authoring field names. The admitted kinds are unsigned
byte ATOM_SCHEMA (2), ATOM_VECTOR (3), MATRIX (4), REGION_SET (7),
SEMANTIC_BINDING (8), OPAQUE_DATA (9), PREDICATE_RESULT (10), FEEDBACK (11),
PASSIVE_TRACE (12), LESSON_NODE (13), and ROOT (14). All fields are required,
with these specific representations:

- ATOM_SCHEMA has exactly `atom_class=1`, `atom_width=1`, `min_value=0`,
  `max_value=255`; it has no nullable or unused fields.
- PASSIVE_TRACE `actions` is an array of eight-character lowercase hexadecimal
  strings, each encoding one four-byte action.
- REGION_SET `regions` and LESSON_NODE `cases` are arrays of objects using
  exactly the public authoring fields. All other sequences are JSON arrays
  of unsigned integers. Booleans are not integers.

The total declaration is bounded by manifest-v0's 1 MiB / depth-32 limits.
Content-v0's existing type, reference, reachability, trace and resource limits
remain unchanged. Both compilers encode then independently validate the
required stream. Its first record must be the byte schema; its entry node
must have selectable regions 1 and 2 and a valid predicate result. This is
the asymmetric non-chess interaction demonstration.

The required stream contains every teaching, practice and final page. Final
pages use external evaluation, without packed answer assertions or examples.
Owner-side page names, expected choices and chess checks are separate build
evidence; the viewer interprets only content-v0.

The all stream shares every required non-root record byte for byte. At the
required root's former ID, it appends the 64 game binding/payload pairs in
ordinal order (namespace 2), then the ten fixture pairs (namespace 3). Each
pair binds byte schema 1, semantic code ordinal+1 and exact payload length.
It then appends, in order: TEXT `0`; TEXT `1`; limitation TEXT
`Inspecting raw records alone does not establish their chess meaning.`;
a byte MATRIX with one row, one column
and cell 74; REGION_SET with one region (ID 1, label 0, full matrix, flags 1);
FIELD_SCHEMA with two fields named respectively by those texts, storage 2, respectively
type MATRIX (4)/count 1 and type OPAQUE_DATA (9)/count 74; TUPLE referencing
that matrix and the 74 payload records; limitation FEEDBACK (5) displaying
that tuple with predicate 0; PASSIVE_TRACE; one unscored LESSON_NODE; and the
sole all ROOT.

The library introduction has unscored guidance role 4 (HEURISTIC), single
response shape 1, answer mode 3,
flags 0, max selections 1, local budget 16, no predicate or cases. Its
presentation/regions are the dedicated matrix/region set. Its default feedback
is the library feedback; its default next is the required entry. The trace
selects 1 then commits, expects neutral outcome 3, the same library feedback
and required entry; initial presentation is the matrix, resulting presentation
is the tuple, limitation refers to that earlier limitation text. The tuple
contains exactly the same one selectable
matrix, preserving content-v0 presentation validity while revealing payloads.
The all ROOT enters that node and adds 64 to the required global budget.
The required learner stream starts directly at its non-chess mechanics;
the all stream first allows neutral anthology inspection. No wrong matching
answer is accepted to implement navigation, and no viewer semantics are added.

Section assignment is deterministic. Required non-root frames are packed
greedily in record order into sections 16..31, each at most 16,384 bytes;
one frame cannot be split. More than 16 sections or one oversized frame
rejects. Games occupy sections 100..163, fixtures 200..209, and the ten
library-support non-root records section 210. All have semantic copy ID 0.
Tier-root sections are 2 (required) and 3 (all). Body sections plus the
separate header/root frames must reconstruct each stream exactly.

The historical capacity prototypes are sourced and verified from the bound
v0 stream, not looked up under coincident IDs in v1. Their 105,277-byte
allowance remains unchanged. A v1 capacity adapter must verify both source
streams and explicitly use this separate prototype source. The actual new
required closure retains the current fivefold protection policy. Reserve,
inventory, route costs and fit must be derived afresh; this contract provides
no carrier fit or damage pass by itself.
