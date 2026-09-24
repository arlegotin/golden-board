# Source-derived receiver bounds

This is the participant revision's pre-result finite resource derivation for
M2 §10.3. It complements static-projection-v2's source-built selected geometry
and semantic envelope. It does not use damage outcomes, measured maxima,
selected winners, participant answers or a saved limits document. The active
candidate set contains only profile8; foreign registry procedures contribute
diagnostic work bounds, not additional selectable candidates.

Keep three projections separate: exact static construction, these conservative
source bounds, and measured complete-corpus resource maxima. Production checks
independent Python/Rust equality for all three and requires measured maxima to
fit these bounds. These are upper bounds, never reported as measured usage or
new runtime thresholds. Neutral source owners and existing rejection thresholds
remain unchanged. The generated canonical JSON replaces the historical limits
TOML format only for this revised derivation; historical admissions stay exact.

Inputs are the exact three neutral v2 policy source documents and exact
resource-accounting-v2 source. All products/sums below use checked u64 arithmetic.
Reject wrong identities, types or overflow. All bounded serialized observations
up to the neutral observation-frame ceiling are covered. Arbitrarily oversized
host buffers are outside this artifact input domain. No computation cache
reduces a bound.

## Derivation

Use policy ceilings: views V, paths P, maximum shell width W, physical input
count Q0, inventory entries I, dependency count D, content bytes B, content
records R, output O, per-program steps T and scratch Z. Let Q be the maximum
of Q0 and every exact diagnostic registry profile's physical-unit count.
The historical diagnostic count is conservative even when square geometry
permits fewer units. Let G be the registry length.

- Route scans A = V × (W/8) ×4; maximum prefix F = W×side/8.
- Combined logical paths J = P+G+1. Adding exclusive square/unit paths and
  the final registry-wide fallback is conservative.
- Lane visits L = J×Q; present repetition groups K = 3×J×Q. Each present
  group consumes at least one observed unit; the factor3 covers initial
  bootstrap, catalog traversal and fallback even before group deduplication.
- Eligible envelope maximum E = 18+4D+section_payload_bytes+8. The common
  header may advertise Ea=1048576 before complete-envelope admission.
  Foreign inventory entries can declare a u32 payload before physical-count
  rejection: El=18+4D+(2^32−1)+8, N=ceil(El/157), layout rows U=I×N×5,
  declared edges H=I×D. Keep this raw-layout bound separate from admitted
  physical units and the eligible stored-check envelope bound.
- Section assembly calls C = J×(3Q+2I). Discovery/fallback each group at
  most Q observed identities; admitted catalog/tier copies at most I.
- Inventory/layout call bound Y = J×(Q+1), allowing every discovered
  inventory candidate before unique admission.
- Body calls M = J×I; assembled tiers at most2J.
- Route VM calls A×max(route_records+3,44). Legacy route records contribute
  at most one call each plus three mapping calls. Exact route2 contributes33
  framed calls, three mapping calls and eight complete constructions:44. The neutral256-record
  ceiling already yields259; this explicit maximum preserves that conservative
  bound without omitting any new call. Lane calls24L, repetition calls
  (1728+24)K, active complete recovery calls at most K and roster calls at most K,
  and body calls M. Including mutually exclusive old/new schedules is
  conservative. Missing groups still consume distinct physical ranges, so K
  also bounds all-missing complete calls. Multiply their sum by T. Per-program scratch
  is Z; it is not the aggregate observation workspace.

Program storage S = Vp+3Xp+64Np+64Tp+128Pp+8Dp from resource-accounting-v2,
using the neutral package/expanded-package/node/table/recipe/table-byte maxima.
Program parsing workspace Sp = S+48Np+8Ep+16Tp+32Pp. At most A×route_records
distinct programs survive, including legacy packages retained before rejection.
Definitions retain at most A×(F+16×route_records) bytes. DEFINE workspace is
8F+max(Sp,S+4×content_workspace(577,29,29×floor(577/14))).
Content workspace X uses the exact resource-accounting formula at B,R and
Hcontent=4096². Result footprint Zr is bounded by
`(I+GQ)×(48+E)+(U+GQ)×(40+191)+48P+2B`.
This includes every possible section/fragment slot, raw retained envelope/common
block, hypothesis and both streams; bounds may coexist although real lifetimes
often do not.

The canonical adapter bounds are rows in resource-accounting kernel order.
Each row has calls, reference_input_units and peak_workspace_bytes. The middle
column below gives units per call; multiply by calls for the emitted total.

| Kernel | Calls | Units per call | Local workspace |
|---|---:|---:|---:|
| observation | 1 | observation_frame_bytes | 0 |
| square-view | V | raw_bits | 0 |
| shell-read | 2A | 8F | F |
| route-frame | A | F | 8×route_records |
| recipe-parse | A×route_records | recipe_package_bytes | Sp |
| program-refinement | A+P+M | recipe_nodes | 32Np+8Ep+8Tp |
| route-example | A×max(route_records+3,44) | F | F+64×recipe_package_bytes+8×128 |
| definition-validation | A | F | DEFINE workspace |
| mapping-search | A | 4Q | 64 |
| unit-extraction | J | Q×255×8 | Q×(8+2×255) |
| lane-adapter | L | 255 | 255+191 |
| repetition-adapter | K | 5×1728 | 216+2×1728 |
| common-frame | L+K | 191 | 191 |
| section-assembly | C | 191Q | Ea+24Q |
| section-check | section_attempts | E | E |
| inventory | Y | E−22 | 16×(E−22) |
| group-layout | Y | U | 128U+64I |
| dependency-closure | Y | H | 24I+8H |
| body-adapter | M | section_payload_bytes | section_payload_bytes+32768 |
| content-validation | 2J | B | X |
| result-selection | J | J×Zr | Zr |
| result-render | 2 | 2×(O+1) | O+256 |

Peak reference scratch conservatively adds all potentially retained classes:
raw_bits; Q×(8+2×255+G×199); A×route_records×S;
A×(F+16×route_records); section_attempts×(E+8);
16×(E−22)+128U+64I+8H;
I×(decoded_body_bytes+8)+2B; J×Zr; 128A+48P; 64+F;
plus the largest local workspace in the table and Z. The header/prefix may
remain live during downstream parsing; a VM call may overlap its adapter
workspace. These sums intentionally
include mutually exclusive phases. Adapter work units retain their separate
dimensions and are never added into a fictitious VM instruction count.
The route-example reservation allows all64 declared output descriptors at the
maximum byte width and all64 input/output descriptor pairs, including an
example that later fails output equality. Its outputs need not fit the prefix.
The inventory parser charges the complete supplied payload before rejection;
a checked generic section may supply E−22 bytes even when it exceeds the
valid inventory payload ceiling. OBS_UNITS rejects lane lengths outside1..255
during framing, before normalized-pool reservation or lane processing.

## Bytes and admission

Emit exactly schema `golden-board.m2-receiver-bounds/v2`, profile_id,
source_owners (the four exact input paths plus this owner), derivation (the
named integer terms A,Q,G,J,L,K,E,Ea,El,N,U,H,C,Y,M,S,Sp,X,Zr), maximum_resource
(section_attempts, primitive_steps, peak_scratch_bytes), and adapter_bounds.
Each adapter row has kernel and the three counters, in the closed kernel order.
Canonical-manifest-v0 serialization owns exact bytes and trailing LF.

Measured-limit admission re-derives these bytes from source, strictly admits
the resource-limits/v2 shape, requires the same four accounting source owners,
and compares every resource and adapter counter componentwise. Missing/extra
rows, booleans, unknown keys, reordered kernels and out-of-bound counters reject.
The caller must separately establish complete-corpus coverage and observation
identities; a small subset fitting these bounds does not establish Gate6.
