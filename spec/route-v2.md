# Profile-8 carried route — development owner

This explicitly new route version is 2, profile 8. It preserves historical
route versions 0/1 and all their bytes. It is not a promoted candidate.
Complete carried knowledge, actual fit, damage, resource and fresh acquisition
evidence remain required; a successfully generated prefix alone is not a gate.

Each of the four shell sectors carries a complete independent route. Geometry,
orientation, calibration, row-major/MSB scan, sector masks, 32-byte calibration,
32-byte route envelope, eight-byte record framing and shell padding retain
their historical mathematical meanings. Route envelope fields are unchanged,
except route_version=2 and profile_version=8. Reserved fields are zero.
Prefix cells count calibration, envelope and all records. Counts/lengths must
be exact. Bytes after that declared prefix are not parsed as route records.

The twelve DEFINE values are the numeric constructions in
route-definitions-v2.md, with their owned stage/dependency order. Each payload
is fact_id:u16, the existing twelve-byte descriptor (value_id=fact_id,
type=BYTES, zero flags, actual width, count=1), then the exact value.
No English relation name substitutes for a carried definition.

For each fact in ascending order, emit DEFINE, WORKED and HELD_OUT with record
IDs `sector*10000 + fact*100 + 1/2/3`. Worked/held payloads retain the inherited
layout: fact:u16, recipe:u16, input_bytes:u32, output_bytes:u32, then both byte
strings. Output always begins with STATUS16; nonzero status has no data.

The primary example sources and sector variations retain the exact
bootstrap-v1 fact graph, except:

- Fact 6 uses the worked/held recipe-211 rows of recipe-teaching-v2.toml in
  all sectors. Its interface and literal outputs replace recipe106's pair.
- Fact 9 retains its exact sector input values but derives profile-8 outputs
  with the new offset. No profile-7 output is relabeled.
- Append the six `additional` rows of recipe-teaching-v2.toml immediately
  after fact6's primary pair, in source order. Their IDs end in 10..15 and
  their kinds are WORKED, HELD_OUT, WORKED, HELD_OUT, WORKED, HELD_OUT.
- Append recipe203's two body-codec examples immediately after fact12's pair,
  IDs ending 10/11, kinds WORKED/HELD_OUT. Inputs are nine token bytes then
  UINT16 prefix length: `00 31 32 33 34 35 36 37 38 / 0009` and
  `40 41 00 04 00 00 00 00 00 / 0004`; results are status0 plus `12345678`
  and `AAAAAAAA`. Full carried recipes201/202 perform general decompression.

Validate every example against the complete carried generic package and its
declared interface before returning bytes. Derive primary nontransport output
from the independent arithmetic/CRC relationship too. Fact6 literal outputs
and additional failures must match the frozen source. Encoder-backed examples
must decode exactly to their original source after prescribed corruption.

Exactly one PACKAGE record follows the facts, stage5/id sector*10000+6001.
It contains the complete compact profile-8 package: all inherited programs
except the now-unused106 (109 uses profile8), body recipes201–203, teaching recipes210–214, and all
their tables including21, each in increasing ID order. Version2 has **no
standalone TABLE records**: every table is already fully framed and carried
once inside that complete package. This is an explicit removal of redundant
copies, not table omission or a reference to host data. Fact5 teaches those
package/table boundaries. Then emit the unchanged stage5 endpoint record
id7001 (u32 section1) and end record id7002 (empty), relative to sector base.
There are exactly47 records before any separately owned further extension.

The exact29-recipe set is owned by recipe-teaching-v2. Omission of106 does
not alter its historical/base packages or permit omission of any live recipe.

All four prefixes must fit their actual shell sectors with the unchanged
total headroom `max(ceil(total_instruction_cells/20),4*256)`, evenly distributed
as before. Every shell cell belongs to calibration, envelope, an exact record,
headroom or deterministic fixed pad. There is no relaxed 512KiB ceiling,
truncated prefix, missing table or optional complete route.

Owner validation compares the independently generated definitions, examples,
record spans and complete package; acquisition validation must additionally
demonstrate use of the carried relationships rather than a host-only answer
table. Span/ablation evidence reports these scopes separately. Remaining
content/control semantics identified by C07 cannot be declared closed merely
because this framing or the host content validator passes.

## Observation-result mapping commitment

For an accepted route_version2, select only mapping ID
`affine-slot-then-interior-v2`. Its mapping object has exactly the nine keys
`id,interior_side,population,unit_population,unit_multiplier,unit_inverse_multiplier,cell_multiplier,offset,cell_inverse_multiplier`.
The numeric values are the observed geometry and derived bootstrap-v2 mapping,
including profile8's offset. Hash the canonical-manifest-v0 serialization of
that exact object, including its single trailing LF, as the accepted hypothesis's
mapping_sha256. Neither route_version nor a profile label is an additional
field in that preimage. Reject mismatched or unknown mapping variants before
adding an accepted row; never synthesize a zero hash. Route versions0/1 retain
the exact legacy/hierarchical variant selectors and preimages owned by
damage-policy-v1. This commitment identifies a checked mapping hypothesis;
it does not itself establish content, knowledge acquisition or uniqueness.
