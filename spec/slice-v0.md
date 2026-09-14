# M2 slice-v0 declaration

Status: normative owner for the reviewed, candidate-neutral P3 semantic slice.

This file owns only the build-time declaration in
`studies/m2/slice-v0.json` and the deterministic compilation that turns it into
the required/all content-v0 feasibility streams. It does not own content-v0 bytes, chess truth, a
transport profile, carrier geometry, damage results, a selected candidate, or
participant evidence. Those remain with their smaller existing or later M2
owners.

## 1. Inputs and trust boundary

`compile_slice_v0` accepts seven byte strings: the slice declaration, the
content conformance fixture, the chess conformance fixture, the M1 game-set,
`spec/content-v0.md`, `spec/constants-v0.toml`, and
`spec/curriculum-v0.toml`. All are untrusted until checked. The declaration and
both conformance inputs must be canonical-manifest-v0 JSON. Every other input
is bound by the literal SHA-256 recorded under `inputs`.

The declaration is canonical JSON with the exact root keys:

```text
asymmetry_probe
capacity_prototypes
chess_fixture_cases
content_base
game_record_plan
inputs
records
schema
section_plan
selected_curriculum_families
```

`schema` is exactly `golden-board.m2-slice/v0`. Every object below is closed:
an unknown, duplicate, missing, mistyped, out-of-range, or noncanonical value
rejects. No omitted value means a default.

## 2. Bound inputs

`inputs` has exactly `chess_fixture`, `constants`, `content_fixture`,
`content_spec`, `curriculum`, and `game_set`. File bindings have exactly `path`
and `sha256`. The game-set binding additionally has `count` and `identity`.
Paths and digests are literal reviewed identifiers; compilation receives
bytes directly and never follows a declaration-controlled path.

The game-set identity is independently recomputed as identity-v0 over the
single complete game-set field and the literal domain
`golden-board:game-set:v0\0`. The fixed count is 64. The game-set reader is
bounded to 327,677 bytes and reads exactly:

```text
u16_be(64) || 64 * (u16_be(ply_count) || ply_count * Move16 || Score8)
```

Each `ply_count` is in `1..4096`, the sum is at most 65,535, complete GameBytes
are strictly bytewise increasing, and EOF follows game 63. This local reader
does not import a source compiler or chess implementation. The locked whole-
file digest and identity make it an independent derivation of the retained M1
truth, not a new authority for accepting arbitrary game sets.

## 3. Exact retained base

`content_base` has exactly `fixture_name`, `retain_record_ids`,
`removed_root_record_id`, `stream_length`, and `stream_sha256`. It selects one
exact named base from the hash-bound content fixture. Its stream bytes must
match both recorded length/digest and the fixture's own length/digest, parse as
content-v0, and expose the declared root. The retained IDs are an explicit
strictly increasing list and must equal every base record except that root.

For v0 the base is `generic-base`, records 1 through 28 are retained, and root
29 is removed. Compilation converts the accepted public projection view to the
public authoring value and never reaches into parser-private records.

## 4. Game-record plan and atomic assignment

`game_record_plan` has exactly `assignments`, `binding_record`, and
`opaque_record`. The two record templates are literal substitution templates,
not defaults:

- `binding_record` is a content-v0 `SEMANTIC_BINDING`, class `BINDING_DATA`,
  namespace 2 (`m1-canonical-game-v0`), semantic code
  `game_ordinal + 1`, argument record 29 (the byte atom schema), record ID from
  `binding_record_id`, and auxiliary equal to the complete GameBytes length;
- `opaque_record` is content-v0 `OPAQUE_DATA`, its record ID comes from
  `opaque_record_id`, its binding reference comes from `binding_record_id`,
  and its data is the complete independently sliced
  `canonical_game_bytes[game_ordinal]`.

There are exactly 64 closed assignment objects, each with
`binding_record_id`, `closure`, `game_ordinal`, `opaque_record_id`,
`section_id`, and `semantic_copy_id`. In array order, ordinal is `0..63`,
binding ID is `30 + 2 * ordinal`, opaque ID is the following integer, closure
is `m2_all_only`, semantic copy is zero, and section ID is `100 + ordinal`.
Section IDs are distinct. A binding/opaque pair is one indivisible logical
game assignment; neither record may be assigned elsewhere and no other game
shares its section.

## 5. Serialized chess fixture records

`chess_fixture_cases` has exactly `assignments`, `binding_record`,
`opaque_record`, and `payload_encoding`. The payload encoding is literally
`slice-v0-chess-fixture-binary`. Its ten ordered assignments bind the same
case names and roles listed below, plus ordinal `0..9`, binding IDs
`158 + 2 * ordinal`, following opaque IDs, section IDs `200 + ordinal`,
closure `m2_all_only`, and semantic copy zero. Each pair is an indivisible atomic
content-body assignment.

The binding template is `BINDING_DATA`, namespace 3
(`m1-chess-fixture-v0`), semantic code `fixture_ordinal + 1`, argument 29, and
auxiliary equal to the opaque payload byte length. The opaque template carries
`chess_fixture_binary[fixture_ordinal]`. The compiler locates each exact named
case in the hash-bound chess fixture and emits this compact binary packet:

```text
u8  version = 0
u8  fixture_kind = fixture_ordinal + 1
u16 prior_moves_byte_length
     prior Move16 bytes
u16 subject_byte_length
     subject bytes                 # Move16 for apply_move; empty for history
u16 expected_byte_length
     expected bytes
```

The expected bytes begin with one variant byte:

| variant | exact remaining bytes |
|---:|---|
| 1 | `Position67` |
| 2 | `u16 halfmove_clock || Position67` |
| 3 | `Position67 || u8 king_in_check || u8 terminal` |
| 4 | `u16 chess_rejection_code` |
| 5 | `u16 played_plies || u16 halfmove_clock || u16 current_key_occurrences || u8 nominal_kind || u8 nominal_square_or_ff || u8 effective_kind || u8 effective_square_or_ff || u8 fifty_move_available || u8 threefold_available` |

Kinds 1/2 are successful kingside/queenside castling, kind 3 is successful en
passant, kinds 4..7 are queen/rook/bishop/knight promotions, kind 8 is a
self-check rejection, and kinds 9/10 are the nominal-ineffective and
effective en-passant history contrast. Square kind is zero for `none` and one
for `square`; absent square is `0xff`; booleans are exactly zero or one. All
hex input fields must have even length and the known wire lengths. The packet
contains only numeric tags and actual M1 fixture wire/result bytes—no case
name, prose, JSON key, SAN, or transport interpretation. The case names remain
declaration/evaluator bindings and are not serialized into content.

## 6. Other authored records

`records` is an ordered array of six complete typed records. Their kind-specific
objects use the same field meanings as the public content-v0 authoring API:

1. record 29: unsigned one-byte atom schema, range `0..255`;
2. record 178: one record-reference field named by TEXT 3, kind
   `OPAQUE_DATA`, count 74;
3. record 179: one tuple field containing all 64 game opaque IDs followed by
   all 10 fixture opaque IDs in ordinal order;
4. record 180: neutral feedback displaying aggregate TUPLE 179 with no
   predicate, which makes all game records reachable without giving content-v0
   chess semantics;
5. record 181: a case-free external-answer practice node, presenting MATRIX
   12 over REGION_SET 15, with default feedback 180 and next node 26; and
6. record 182: the `m2_all` final root, entering node 181 with global budget
   10.

The declaration spells every logical field, including empty case/entry arrays
and tuple references. Kind-specific absence is grammar, not defaulting. The
compiler preserves declaration order and IDs; it never sorts or infers a
record.

`section_plan` has exactly `support_assignments` and `tier_roots`. Required
content-body section 16 contains records 1 through 28. All-only content-body
section 17 contains record 29, while all-only section 210 contains records 178
through 181. The required tier-frame
section 2 carries the original generic-base ROOT frame 29; the all tier-frame
section 3 carries authored ROOT frame 182. Root frames are tier-frame bytes,
not content-body assignments.

The required frame therefore assembles the exact original 575-byte,
29-record `generic-base` stream. The all frame assembles shared records 1..28,
all-only atom/game/fixture/support records, and root 182. Both complete streams
must independently pass content-v0. The all frame lists required section 16
plus all-only sections 17, 100..163, 200..209, and 210 in increasing order.
Concatenating body record IDs in that exact section order must yield precisely
`1..181`; this is checked before either tier is accepted.
Together with the 64 game and 10 fixture assignments, each body record is
assigned exactly once in its tier, while required body bytes are reused by the
all tier. These are logical atomic assignments only; candidate transport
overhead and fragmentation remain outside slice-v0.

## 7. Capacity prototypes

`capacity_prototypes` is ordered by content-v0 kind number. Each closed entry
has `kind`, `prototype_id`, `role`, and `source_record_id`. Role is literally
`nonsemantic-capacity-only`. The source record is selected from the complete,
parser-valid, hash-bound `generic-base` projection before root removal. There
is exactly one entry for each kind 1 through 14, and its selected record has
that kind. Therefore each entry identifies a complete explicit valid
authoring projection plus one exact record frame within it without copying the
same 575 canonical bytes fourteen times. These records are capacity inputs
only and are never appended to the slice stream or shown to a learner.

The compiler exposes each checked prototype as the immutable tuple `(kind,
prototype_id, source_record_id, complete_frame_length)`. In kind order, the v0
complete-frame lengths are exactly `15, 14, 14, 20, 34, 19, 54, 18, 11, 14,
14, 28, 58, 12` bytes. These are candidate-neutral `L[k]` inputs. The capacity
engine derives them from the independently re-encoded base stream; a profile
policy may bind the result but must not restate a different length.

## 8. Bound semantic fixtures and asymmetry probe

Every fixture case name must occur exactly once in the hash-bound chess-v0
fixture. The compiler validates and projects only the exact wire/numeric fields
specified in Section 5; it does not execute chess or promote a new chess truth.

`asymmetry_probe` exactly binds the retained 2-by-3 MATRIX 12, its row-major
cells `[0,1,2,3,4,5]`, REGION_SET 15, the ordered region IDs `[1,2,3]`, and
the node-181 region-2 select/commit action path. The unequal dimensions,
non-palindromic cells, narrow `0..5` atom domain, and exact region/action bytes
make transpose, reflection, row/column exchange, polarity inversion, and
per-byte bit reversal observable. The compiler proves only these concrete
inequalities and field bindings; candidate transport KATs still own transport
orientation/polarity claims. The path begins at external node 181 and leads to
the original entry node 26.

`selected_curriculum_families` is an explicit ordered subset of family IDs in
the hash-bound curriculum. It is a planning/binding statement, not a claim
that this small P3 stream completes M3 teaching or human validation.

## 9. Compilation and rejection

After all bindings and closed-shape checks pass, the compiler independently
checks the retained required stream and constructs the all-tier public
authoring records. It calls `encode_content_v0`, passes every emitted byte of
both tiers through production `stream_validation`, and exposes only immutable
public projection views. It checks exact per-tier body/root/section coverage,
64 game payloads, 10 serialized fixture payloads, and both final roots. Exact
stream lengths, hashes, and record counts are immutable compilation results
and direct-test facts, not success claims stored in the reviewed declaration.

Any failure raises `SliceError(reason, path)` before a partial result escapes.
Reasons and paths are build-time diagnostics, not content-v0 raw rejection
codes. Computation is bounded by the locked input caps and existing content-v0
limits.
