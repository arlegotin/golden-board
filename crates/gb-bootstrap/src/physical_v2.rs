//! Independent physical evidence from four bounded, canonically bound manifests.
//! No carrier, recipe, decoder, source builder, saved proof, or damage outcome is
//! accepted here. The eight rows deliberately cannot constitute a Gate-7 proof.
use gb_foundation::{
    ManifestValue as V, identity_hex, serialize_manifest, validate_canonical_manifest,
};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
const PROFILE: &str = "eh72-hier-r5-r2-r1-lzss-crc32c-v1";
const IDS: [&str; 8] = [
    "two-stage-map-bijection",
    "matrix-owner-total-partition",
    "shell-sector-total-partition",
    "physical-group-total-partition",
    "owner-factor-ledger-reconciliation",
    "final-cell-lane-separation",
    "d2-d4-d6-required-closure-survival",
    "section-dependency-inventory-closure",
];
const REQUIRED: [u64; 6] = [1, 2, 3, 16, 17, 18];
/// Admit only the four closed input documents; no physical predicates are run.
pub fn admit_physical_inputs_v2(
    candidate: &[u8],
    capacity: &[u8],
    ownership: &[u8],
    semantic: &[u8],
) -> std::result::Result<(), PhysicalError> {
    admit(candidate, capacity, ownership, semantic).map(|_| ())
}
type Object = BTreeMap<String, V>;
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PhysicalError {
    Manifest,
    Binding,
    Bounds,
    Arithmetic,
}
type Result<T> = std::result::Result<T, PhysicalError>;
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PredicateRowV2 {
    id: &'static str,
    witness: u64,
    violations: u64,
}
impl PredicateRowV2 {
    pub fn predicate_id(&self) -> &'static str {
        self.id
    }
    pub fn witness_count(&self) -> u64 {
        self.witness
    }
    pub fn violation_count(&self) -> u64 {
        self.violations
    }
    pub fn passed(&self) -> bool {
        self.witness > 0 && self.violations == 0
    }
}
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PhysicalEvidenceV2 {
    raw: Vec<u8>,
    rows: Vec<PredicateRowV2>,
}
impl PhysicalEvidenceV2 {
    pub fn canonical_bytes(&self) -> &[u8] {
        &self.raw
    }
    pub fn rows(&self) -> &[PredicateRowV2] {
        &self.rows
    }
}
fn need(v: bool) -> Result<()> {
    if v {
        Ok(())
    } else {
        Err(PhysicalError::Manifest)
    }
}
fn bound(v: bool) -> Result<()> {
    if v {
        Ok(())
    } else {
        Err(PhysicalError::Bounds)
    }
}
fn bind(v: bool) -> Result<()> {
    if v {
        Ok(())
    } else {
        Err(PhysicalError::Binding)
    }
}
fn add(a: u64, b: u64) -> Result<u64> {
    a.checked_add(b).ok_or(PhysicalError::Arithmetic)
}
fn mul(a: u64, b: u64) -> Result<u64> {
    a.checked_mul(b).ok_or(PhysicalError::Arithmetic)
}
fn sum(v: impl IntoIterator<Item = u64>) -> Result<u64> {
    v.into_iter().try_fold(0, add)
}
fn obj(v: &V) -> Result<&Object> {
    if let V::Object(v) = v {
        Ok(v)
    } else {
        Err(PhysicalError::Manifest)
    }
}
fn arr(v: &V) -> Result<&[V]> {
    if let V::Array(v) = v {
        Ok(v)
    } else {
        Err(PhysicalError::Manifest)
    }
}
fn n(v: &V) -> Result<u64> {
    if let V::U64(v) = v {
        Ok(*v)
    } else {
        Err(PhysicalError::Manifest)
    }
}
fn s(v: &V) -> Result<&str> {
    if let V::String(v) = v {
        need(v.is_ascii() && !v.bytes().any(|b| b.is_ascii_uppercase()))?;
        Ok(v)
    } else {
        Err(PhysicalError::Manifest)
    }
}
fn f<'a>(v: &'a Object, k: &str) -> Result<&'a V> {
    v.get(k).ok_or(PhysicalError::Manifest)
}
fn nv(v: &Object, k: &str) -> Result<u64> {
    n(f(v, k)?)
}
fn sv<'a>(v: &'a Object, k: &str) -> Result<&'a str> {
    s(f(v, k)?)
}
fn keys(v: &Object, ks: &str) -> Result<()> {
    let keys = ks.split(',').collect::<Vec<_>>();
    need(v.len() == keys.len() && keys.iter().all(|k| v.contains_key(*k)))
}
fn hash(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}
fn sha(v: &V) -> Result<&str> {
    let h = s(v)?;
    need(
        h.len() == 64
            && h.bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
    )?;
    Ok(h)
}
fn doc(raw: &[u8], kind: &str, ks: &str) -> Result<V> {
    bound(!raw.is_empty() && raw.len() <= 1048576)?;
    let v = validate_canonical_manifest(raw).map_err(|_| PhysicalError::Manifest)?;
    let o = obj(&v)?;
    keys(o, ks)?;
    need(
        sv(o, "schema")? == format!("golden-board.m2-{kind}/v2") && sv(o, "profile_id")? == PROFILE,
    )?;
    Ok(v)
}
fn numbers(v: &V, max: usize, limit: u64) -> Result<Vec<u64>> {
    let a = arr(v)?;
    bound(a.len() <= max)?;
    a.iter()
        .map(|v| {
            let z = n(v)?;
            bound(z <= limit)?;
            Ok(z)
        })
        .collect()
}
fn table<'a>(
    o: &'a Object,
    name: &str,
    fields: &str,
    types: &str,
    max: usize,
) -> Result<Vec<&'a [V]>> {
    let fs = arr(f(o, &format!("{name}_fields"))?)?;
    let fields = fields.split(',').collect::<Vec<_>>();
    need(fs.len() == fields.len())?;
    for (v, e) in fs.iter().zip(&fields) {
        need(s(v)? == *e)?;
    }
    let rows = arr(f(o, &format!("{name}_rows"))?)?;
    bound(rows.len() <= max)?;
    rows.iter()
        .map(|v| {
            let r = arr(v)?;
            need(r.len() == fields.len() && r.len() == types.len())?;
            for (v, t) in r.iter().zip(types.bytes()) {
                match t {
                    b'n' => {
                        n(v)?;
                    }
                    b's' => {
                        s(v)?;
                    }
                    b'h' => {
                        sha(v)?;
                    }
                    b'a' => {
                        numbers(v, 65535, u32::MAX as u64)?;
                    }
                    _ => return Err(PhysicalError::Manifest),
                }
            }
            Ok(r)
        })
        .collect()
}
fn source_ids(v: &V) -> Result<()> {
    let o = obj(v)?;
    keys(
        o,
        "inherited_profile_policy_sha256,profile_policy_sha256,profile_limits_source_sha256,damage_policy_sha256,required_content_sha256,all_content_sha256",
    )?;
    for h in o.values() {
        sha(h)?;
    }
    Ok(())
}
fn vo(rows: impl IntoIterator<Item = (&'static str, V)>) -> V {
    V::Object(rows.into_iter().map(|(k, v)| (k.into(), v)).collect())
}
fn vs(s: impl Into<String>) -> V {
    V::String(s.into())
}
#[derive(Clone)]
struct Section {
    id: u64,
    kind: u64,
    version: u64,
    closure: u64,
    check: u64,
    copies: u64,
    factor: u64,
    owner: String,
    deps: Vec<u64>,
    stored: u64,
    decoded: u64,
    envelope: u64,
    fragments: u64,
    first: u64,
    last: u64,
}
#[derive(Clone)]
struct Unit {
    id: u64,
    section: u64,
    copy: u64,
    fragment: u64,
    replica: u64,
    factor: u64,
    bytes: u64,
    slot: u64,
    first: u64,
    count: u64,
    mapped: String,
}
struct Shell {
    prefix: u64,
    head: u64,
    pad: u64,
    spans: Vec<(u64, u64, String)>,
    complete: bool,
}
#[derive(Clone)]
struct Expected {
    kind: u64,
    version: u64,
    closure: u64,
    factor: u64,
    owner: String,
    deps: Vec<u64>,
    stored: u64,
    decoded: u64,
}
struct Evidence {
    side: u64,
    width: u64,
    inner: u64,
    p: u64,
    q: u64,
    b: u64,
    bi: u64,
    a: u64,
    ai: u64,
    offset: u64,
    map_bad: bool,
    sections: Vec<Section>,
    units: Vec<Unit>,
    shell: Vec<Shell>,
    ledger: BTreeMap<String, u64>,
    expected: BTreeMap<u64, Expected>,
    semantic_good: bool,
    pad_first: u64,
    pad_count: u64,
    table_count: u64,
    table_hash: String,
}
const LEDGER: &str = "stored_payload_bytes,decoded_body_payload_bytes,replicated_payload_bytes,envelope_header_bytes,section_check_bytes,fragment_header_bytes,fragment_zero_pad_bytes,local_check_bytes,transport_pad_bytes,parity_bytes,encoded_transport_bytes,logical_group_count,factor_1_group_count,factor_2_group_count,factor_5_group_count,physical_unit_count,codeword_count,real_protected_cells,capacity_probe_cells,reserve_probe_cells,load_probe_cells,shell_instruction_cells,shell_example_cells,shell_recipe_cells,shell_headroom_cells,shell_fixed_pad_cells,interior_fixed_pad_cells,unused_cells,total_cells";
fn admit(
    candidate_raw: &[u8],
    capacity_raw: &[u8],
    ownership_raw: &[u8],
    semantic_raw: &[u8],
) -> Result<Evidence> {
    let candidate = doc(
        candidate_raw,
        "candidate-manifest",
        "schema,profile_id,profile_version,status,source_identities,files,manifest_identity",
    )?;
    let ca = obj(&candidate)?;
    need(nv(ca, "profile_version")? == 8 && sv(ca, "status")? == "static-projection-only")?;
    source_ids(f(ca, "source_identities")?)?;
    sha(f(ca, "manifest_identity")?)?;
    let mut omitted = ca.clone();
    omitted.remove("manifest_identity");
    bind(
        identity_hex(
            b"golden-board:manifest:v0\0",
            &[&serialize_manifest(&V::Object(omitted)).map_err(|_| PhysicalError::Manifest)?],
        )
        .map_err(|_| PhysicalError::Manifest)?
            == sv(ca, "manifest_identity")?,
    )?;
    let names = [
        "capacity-ledger.json",
        "carrier.bin",
        "density-ledger.json",
        "geometry-search.json",
        "ownership-ledger.json",
        "route-0.bin",
        "route-1.bin",
        "route-2.bin",
        "route-3.bin",
        "semantic-envelope.json",
        "static-limits.json",
    ];
    let files = arr(f(ca, "files")?)?;
    need(files.len() == names.len())?;
    let mut file_values = BTreeMap::new();
    for (row, name) in files.iter().zip(names) {
        let row = obj(row)?;
        keys(row, "path,bytes,sha256")?;
        need(sv(row, "path")? == name)?;
        let size = nv(row, "bytes")?;
        bound(size > 0 && size <= 1048576)?;
        file_values.insert(name, (size, sha(f(row, "sha256")?)?));
    }
    for (name, raw) in [
        ("capacity-ledger.json", capacity_raw),
        ("ownership-ledger.json", ownership_raw),
        ("semantic-envelope.json", semantic_raw),
    ] {
        bind(file_values[name] == (raw.len() as u64, hash(raw).as_str()))?;
    }
    let capacity = doc(
        capacity_raw,
        "capacity-ledger",
        "schema,profile_id,carrier_sha256,semantic_envelope_sha256,section_fields,section_rows,unit_fields,unit_rows,ledger",
    )?;
    let c = obj(&capacity)?;
    bind(
        sha(f(c, "carrier_sha256")?)? == file_values["carrier.bin"].1
            && sha(f(c, "semantic_envelope_sha256")?)? == hash(semantic_raw),
    )?;
    let ownership = doc(
        ownership_raw,
        "ownership-ledger",
        "schema,profile_id,carrier_sha256,capacity_ledger_sha256,side,shell_width,mapping,shell_fields,shell_rows,unit_fields,unit_rows,interior_fixed_pad,cell_table,cell_table_sha256",
    )?;
    let o = obj(&ownership)?;
    bind(
        sha(f(o, "carrier_sha256")?)? == file_values["carrier.bin"].1
            && sha(f(o, "capacity_ledger_sha256")?)? == hash(capacity_raw),
    )?;
    let side = nv(o, "side")?;
    let width = nv(o, "shell_width")?;
    bound(
        (64..=2048).contains(&side)
            && side % 8 == 0
            && (8..=128).contains(&width)
            && width % 8 == 0
            && 2 * width + 8 <= side,
    )?;
    let inner = side - 2 * width;
    let p = inner * inner;
    let q = p / 1728;
    bound(q > 0 && q <= 2389)?;
    bind(file_values["carrier.bin"].0 == 4 + side * side / 8)?;
    let derived =
        crate::mapping_v2::derive(side as u16, width as u16).map_err(|_| PhysicalError::Bounds)?;
    let mapping = obj(f(o, "mapping")?)?;
    keys(
        mapping,
        "id,interior_side,population,unit_population,unit_multiplier,unit_inverse_multiplier,cell_multiplier,offset,cell_inverse_multiplier",
    )?;
    need(sv(mapping, "id")? == "affine-slot-then-interior-v2")?;
    let values = [
        ("interior_side", inner),
        ("population", p),
        ("unit_population", q),
        ("unit_multiplier", derived.slot_multiplier()),
        ("unit_inverse_multiplier", derived.inverse_slot_multiplier()),
        ("cell_multiplier", derived.cell_multiplier()),
        ("offset", derived.cell_offset()),
        ("cell_inverse_multiplier", derived.inverse_cell_multiplier()),
    ];
    let mut map_bad = false;
    for (k, expected) in values {
        let v = nv(mapping, k)?;
        bound(v <= 4194304)?;
        map_bad |= v != expected;
    }
    let b = nv(mapping, "unit_multiplier")?;
    let bi = nv(mapping, "unit_inverse_multiplier")?;
    let a = nv(mapping, "cell_multiplier")?;
    let ai = nv(mapping, "cell_inverse_multiplier")?;
    let offset = nv(mapping, "offset")?;
    bound(b < q && bi < q && a < p && ai < p && offset < p)?;
    let lr = obj(f(c, "ledger")?)?;
    keys(lr, LEDGER)?;
    let ledger = lr
        .iter()
        .map(|(k, v)| Ok((k.clone(), n(v)?)))
        .collect::<Result<BTreeMap<_, _>>>()?;
    let rows = table(
        c,
        "section",
        "section_id,section_type,section_version,closure_class,check_id,semantic_copy_count,physical_replica_count,owner_id,dependency_ids,stored_payload_bytes,decoded_payload_bytes,payload_sha256,envelope_sha256,envelope_bytes,fragment_count,first_physical_unit,last_physical_unit",
        "nnnnnnnsan nhhnnnn".replace(' ', "").as_str(),
        4096,
    )?;
    let mut sections = Vec::with_capacity(rows.len());
    let mut prior = 0;
    let mut group_units = 0;
    for r in rows {
        let deps = numbers(&r[8], 4095, u32::MAX as u64)?;
        let section = Section {
            id: n(&r[0])?,
            kind: n(&r[1])?,
            version: n(&r[2])?,
            closure: n(&r[3])?,
            check: n(&r[4])?,
            copies: n(&r[5])?,
            factor: n(&r[6])?,
            owner: s(&r[7])?.into(),
            deps,
            stored: n(&r[9])?,
            decoded: n(&r[10])?,
            envelope: n(&r[13])?,
            fragments: n(&r[14])?,
            first: n(&r[15])?,
            last: n(&r[16])?,
        };
        bound(
            section.id > prior
                && section.id <= u32::MAX as u64
                && section.version <= 65535
                && (1..=6).contains(&section.kind)
                && [128, 129].contains(&section.closure)
                && [1, 2, 5].contains(&section.factor)
                && section.copies <= 65535
                && section.check <= 65535
                && (1..=16384).contains(&section.stored)
                && section.decoded <= 16384
                && section.envelope <= 32790
                && (1..=209).contains(&section.fragments)
                && section.first <= 2389
                && section.last <= 2389,
        )?;
        prior = section.id;
        group_units = add(group_units, section.fragments)?;
        bound(group_units <= 2389)?;
        sections.push(section);
    }
    let ownership_units = table(o, "unit", "physical_unit_id,mapped_cell_sha256", "nh", 2389)?;
    let mut mapped = BTreeMap::new();
    for r in ownership_units {
        let id = n(&r[0])?;
        bound((1..=2389).contains(&id))?;
        need(mapped.insert(id, sha(&r[1])?.to_owned()).is_none())?;
    }
    let rows = table(
        c,
        "unit",
        "physical_unit_id,section_id,semantic_copy_id,fragment_index,replica_index,physical_replica_count,encoded_bytes,encoded_sha256,slot,logical_bit_first,logical_bit_count",
        "nnnnnnnhnnn",
        2389,
    )?;
    let mut units = Vec::with_capacity(rows.len());
    for r in rows {
        let u = Unit {
            id: n(&r[0])?,
            section: n(&r[1])?,
            copy: n(&r[2])?,
            fragment: n(&r[3])?,
            replica: n(&r[4])?,
            factor: n(&r[5])?,
            bytes: n(&r[6])?,
            slot: n(&r[8])?,
            first: n(&r[9])?,
            count: n(&r[10])?,
            mapped: mapped.remove(&n(&r[0])?).unwrap_or_default(),
        };
        bound(
            (1..=q).contains(&u.id)
                && u.section <= u32::MAX as u64
                && u.copy <= 65535
                && u.fragment <= 65535
                && u.replica <= 5
                && [1, 2, 5].contains(&u.factor)
                && u.bytes <= 16384
                && u.slot < q
                && u.first < p
                && u.count <= 4194304,
        )?;
        units.push(u);
    }
    let mut semantic_good = mapped.is_empty();
    // Spans are typed triples, not a string; admit their nested grammar separately.
    let fields = arr(f(o, "shell_fields")?)?;
    let expected_fields =
        "sector_id,route_prefix_cells,headroom_cells,fixed_pad_cells,image_sha256,spans"
            .split(',')
            .collect::<Vec<_>>();
    need(fields.len() == 6)?;
    for (a, b) in fields.iter().zip(expected_fields) {
        need(s(a)? == b)?;
    }
    let shell_rows = arr(f(o, "shell_rows")?)?;
    need(shell_rows.len() == 4)?;
    let mut shell = Vec::new();
    for (i, r) in shell_rows.iter().enumerate() {
        let r = arr(r)?;
        need(r.len() == 6 && n(&r[0])? == i as u64)?;
        sha(&r[4])?;
        let prefix = n(&r[1])?;
        let head = n(&r[2])?;
        let pad = n(&r[3])?;
        bound(prefix <= side * width && head <= side * width && pad <= side * width)?;
        let spans = arr(&r[5])?;
        bound(spans.len() <= 4096)?;
        let mut parsed = Vec::new();
        let mut at = 0;
        let mut complete = true;
        let mut byclass = [0; 5];
        let mut last = "";
        for sp in spans {
            let sp = arr(sp)?;
            need(sp.len() == 3)?;
            let first = n(&sp[0])?;
            let count = n(&sp[1])?;
            let owner = s(&sp[2])?;
            let class = match owner {
                "instruction" => 0,
                "example" => 1,
                "recipe" => 2,
                "headroom" => 3,
                "fixed-pad" => 4,
                _ => return Err(PhysicalError::Manifest),
            };
            bound(first <= side * width && count <= side * width)?;
            complete &= first == at && count > 0 && owner != last;
            at = add(first, count)?;
            complete &= match class {
                0..=2 => at <= prefix,
                3 => first >= prefix && at <= prefix + head,
                _ => first >= prefix + head && at <= prefix + head + pad,
            };
            byclass[class] = add(byclass[class], count)?;
            parsed.push((first, count, owner.to_owned()));
            last = owner;
        }
        complete &= at == width * (side - width)
            && sum(byclass[..3].iter().copied())? == prefix
            && byclass[3] == head
            && byclass[4] == pad
            && prefix == file_values[format!("route-{i}.bin").as_str()].0 * 8
            && prefix > 0;
        shell.push(Shell {
            prefix,
            head,
            pad,
            spans: parsed,
            complete,
        });
    }
    let pad = obj(f(o, "interior_fixed_pad")?)?;
    keys(pad, "logical_bit_first,logical_bit_count,fill_order")?;
    need(sv(pad, "fill_order")? == "affine-images-of-ascending-logical-tail")?;
    let pad_first = nv(pad, "logical_bit_first")?;
    let pad_count = nv(pad, "logical_bit_count")?;
    bound(pad_first <= 4194304 && pad_count <= 4194304)?;
    let ct = obj(f(o, "cell_table")?)?;
    keys(
        ct,
        "row_bytes,row_count,row_order,owner_kind_ids,owner_id_rule,owner_bit_offset_rule",
    )?;
    need(
        nv(ct, "row_bytes")? == 9
            && sv(ct, "row_order")? == "canonical-matrix-row-major"
            && sv(ct, "owner_id_rule")?
                == "sector-id-for-shell-kinds-physical-unit-id-for-protected-unit-zero-for-interior-fixed-pad"
            && sv(ct, "owner_bit_offset_rule")? == "zero-based-offset-within-named-owner",
    )?;
    let kinds = arr(f(ct, "owner_kind_ids")?)?;
    need(kinds.len() == 5)?;
    for (a, b) in kinds.iter().zip([
        "1-shell-route",
        "2-shell-headroom",
        "3-shell-fixed-pad",
        "4-protected-unit",
        "5-interior-fixed-pad",
    ]) {
        need(s(a)? == b)?;
    }
    let table_count = nv(ct, "row_count")?;
    let table_hash = sha(f(o, "cell_table_sha256")?)?.to_owned();
    let semantic = doc(
        semantic_raw,
        "semantic-envelope",
        "schema,profile_id,source_identities,prototype_fields,prototype_rows,real_section_fields,real_section_rows,tier_frame_fields,tier_frame_rows,bucket_fields,bucket_rows,capacity_section_fields,capacity_section_rows,slot_fields,slot_rows,totals",
    )?;
    let se = obj(&semantic)?;
    source_ids(f(se, "source_identities")?)?;
    bind(f(se, "source_identities")? == f(ca, "source_identities")?)?;
    let (expected, good) = semantic_expected(se, &sections)?;
    semantic_good &= good;
    let domain = sum(sections.iter().map(|section| {
        section.fragments
            * expected
                .get(&section.id)
                .map_or(section.factor, |owner| owner.factor)
    }))?;
    bound(domain <= 2389)?;
    Ok(Evidence {
        side,
        width,
        inner,
        p,
        q,
        b,
        bi,
        a,
        ai,
        offset,
        map_bad,
        sections,
        units,
        shell,
        ledger,
        expected,
        semantic_good,
        pad_first,
        pad_count,
        table_count,
        table_hash,
    })
}
fn semantic_expected(se: &Object, sections: &[Section]) -> Result<(BTreeMap<u64, Expected>, bool)> {
    let prototypes = table(
        se,
        "prototype",
        "kind,prototype_id,source_record_id,frame_bytes",
        "nsnn",
        14,
    )?;
    let real = table(
        se,
        "real_section",
        "section_id,closure_class,physical_replica_count,decoded_payload_bytes,stored_payload_bytes,section_version,record_ids,game_ordinal,fixture_ordinal",
        "nnnnnnann",
        4096,
    )?;
    let tiers = table(
        se,
        "tier_frame",
        "section_id,physical_replica_count,payload_bytes,dependency_ids,assembled_stream_bytes,assembled_record_count,root_record_bytes",
        "nnnannn",
        2,
    )?;
    let buckets = table(
        se,
        "bucket",
        "bucket_id,tier,protection_class,payload_bytes,slot_count,section_count",
        "sssnnn",
        4096,
    )?;
    let capacity = table(
        se,
        "capacity_section",
        "section_id,bucket_id,section_ordinal,tier,protection_class,first_slot_ordinal,slot_count,payload_bytes",
        "nsnssnnn",
        4096,
    )?;
    let slots = table(
        se,
        "slot",
        "bucket_id,slot_ordinal,role_ordinal,role_id,kind,prototype_id,frame_bytes",
        "snnsnsn",
        65535,
    )?;
    let totals = obj(f(se, "totals")?)?;
    keys(
        totals,
        "prototype_count,real_section_count,tier_frame_count,bucket_count,capacity_section_count,slot_count,authoring_payload_bytes,real_decoded_body_payload_bytes,real_stored_body_payload_bytes,tier_payload_bytes,content_capacity_before_reserve_bytes,reserve_payload_bytes,protected_logical_capacity_bytes",
    )?;
    for value in totals.values() {
        n(value)?;
    }
    let mut good = prototypes.len() == 14 && tiers.len() == 2;
    let mut expected = BTreeMap::new();
    let mut raw_sum = 0;
    let mut stored_sum = 0;
    let mut tier_sum = 0;
    let mut real_ids = BTreeSet::new();
    let mut required_ids = BTreeSet::new();
    let mut used_records = BTreeSet::new();
    for (i, r) in prototypes.iter().enumerate() {
        good &= n(&r[0])? == i as u64 + 1;
        bound(n(&r[3])? <= 16384)?;
    }
    for r in &real {
        let id = n(&r[0])?;
        let closure = n(&r[1])?;
        let factor = if REQUIRED.contains(&id) { 5 } else { 1 };
        let decoded = n(&r[3])?;
        let stored = n(&r[4])?;
        let version = n(&r[5])?;
        bound(
            id > 3
                && id <= u32::MAX as u64
                && decoded <= 16384
                && (1..=16384).contains(&stored)
                && version <= 1,
        )?;
        good &= real_ids.insert(id)
            && closure == if factor == 5 { 128 } else { 129 }
            && n(&r[2])? == factor;
        if REQUIRED.contains(&id) {
            required_ids.insert(id);
        }
        let records = numbers(&r[6], 65535, 65535)?;
        good &= !records.is_empty() && records.iter().all(|id| *id > 0 && used_records.insert(*id));
        good &= n(&r[7])?
            == if (100..=163).contains(&id) {
                id - 100
            } else {
                65535
            }
            && n(&r[8])?
                == if (200..=209).contains(&id) {
                    id - 200
                } else {
                    65535
                };
        raw_sum = add(raw_sum, decoded)?;
        stored_sum = add(stored_sum, stored)?;
        expected.insert(
            id,
            Expected {
                kind: 3,
                version,
                closure: if factor == 5 { 128 } else { 129 },
                factor,
                owner: format!("body:{id}"),
                deps: vec![],
                stored,
                decoded,
            },
        );
    }
    let owned_bodies = [16, 17, 18]
        .into_iter()
        .chain(100..=163)
        .chain(200..=210)
        .collect::<BTreeSet<_>>();
    good &= real_ids == owned_bodies && required_ids == BTreeSet::from([16, 17, 18]);
    for (i, r) in tiers.iter().enumerate() {
        let id = n(&r[0])?;
        let payload = n(&r[2])?;
        let deps = numbers(&r[3], 4095, u32::MAX as u64)?;
        bound(
            payload > 0
                && payload <= 16384
                && n(&r[4])? <= 1048576
                && n(&r[5])? <= 65535
                && n(&r[6])? <= 16384,
        )?;
        let wanted = if id == 2 {
            required_ids.iter().copied().collect::<Vec<_>>()
        } else {
            real_ids.iter().copied().collect()
        };
        good &= id == i as u64 + 2 && n(&r[1])? == 5 && deps == wanted;
        let source_deps = wanted;
        expected.insert(
            id,
            Expected {
                kind: 2,
                version: 0,
                closure: 128,
                factor: 5,
                owner: format!("tier:{id}"),
                deps: source_deps,
                stored: payload,
                decoded: payload,
            },
        );
        tier_sum = add(tier_sum, payload)?;
    }
    let mut bucket_map = BTreeMap::new();
    for r in &buckets {
        let id = s(&r[0])?;
        let tier = s(&r[1])?;
        let class = s(&r[2])?;
        let expected_class = match tier {
            "core0" | "core1" | "core2" => "replicated-core0-2",
            "core3" | "core4" => "nonreplicated-core3-4",
            _ => return Err(PhysicalError::Manifest),
        };
        good &= class == expected_class
            && bucket_map
                .insert(id, (tier, class, n(&r[3])?, n(&r[4])?, n(&r[5])?))
                .is_none();
    }
    let mut capacity_sums: BTreeMap<&str, (u64, u64, u64)> = BTreeMap::new();
    let mut future = 0;
    for (i, r) in capacity.iter().enumerate() {
        let id = n(&r[0])?;
        let bucket = s(&r[1])?;
        let ordinal = n(&r[2])?;
        let tier = s(&r[3])?;
        let class = s(&r[4])?;
        let payload = n(&r[7])?;
        bound(
            id <= u32::MAX as u64
                && payload > 0
                && payload <= 16384
                && n(&r[5])? <= 65535
                && n(&r[6])? <= 65535,
        )?;
        let factor = match class {
            "replicated-core0-2" => 2,
            "nonreplicated-core3-4" => 1,
            _ => return Err(PhysicalError::Manifest),
        };
        good &= id == 211 + i as u64
            && bucket_map
                .get(bucket)
                .is_some_and(|r| r.0 == tier && r.1 == class);
        let sums = capacity_sums.entry(bucket).or_default();
        good &= ordinal == sums.2 && n(&r[5])? == sums.1;
        sums.0 = add(sums.0, payload)?;
        sums.1 = add(sums.1, n(&r[6])?)?;
        sums.2 = add(sums.2, 1)?;
        future = add(future, payload)?;
        expected.insert(
            id,
            Expected {
                kind: 4,
                version: 0,
                closure: 129,
                factor,
                owner: format!("capacity:{bucket}:{ordinal}"),
                deps: vec![],
                stored: payload,
                decoded: payload,
            },
        );
    }
    for (id, (_, _, bytes, count, sections)) in &bucket_map {
        good &= capacity_sums.get(id).copied().unwrap_or_default() == (*bytes, *count, *sections);
    }
    let mut slot_sums: BTreeMap<&str, (u64, u64)> = BTreeMap::new();
    for r in &slots {
        let id = s(&r[0])?;
        let q = slot_sums.entry(id).or_default();
        good &= n(&r[1])? == q.1 && bucket_map.contains_key(id);
        bound(n(&r[4])? <= 14 && n(&r[6])? <= 16384)?;
        q.0 = add(q.0, n(&r[6])?)?;
        q.1 = add(q.1, 1)?;
    }
    for (id, (_, _, bytes, count, _)) in &bucket_map {
        good &= slot_sums.get(id).copied().unwrap_or_default() == (*bytes, *count);
    }
    let before = sum([raw_sum, tier_sum, 16384, future])?;
    let reserve = before.div_ceil(19).max(382);
    let mut remaining = reserve;
    let mut next = 211 + capacity.len() as u64;
    let mut ordinal = 0;
    while remaining > 0 {
        bound(expected.len() < 4096)?;
        let payload = remaining.min(16384);
        expected.insert(
            next,
            Expected {
                kind: 5,
                version: 0,
                closure: 129,
                factor: 2,
                owner: format!("reserve:{ordinal}"),
                deps: vec![],
                stored: payload,
                decoded: payload,
            },
        );
        remaining -= payload;
        next += 1;
        ordinal += 1;
    }
    for (i, section) in sections.iter().filter(|s| s.kind == 6).enumerate() {
        good &= section.id == next + i as u64;
        expected.insert(
            section.id,
            Expected {
                kind: 6,
                version: 0,
                closure: 129,
                factor: 1,
                owner: format!("load:{i}"),
                deps: vec![],
                stored: section.stored,
                decoded: section.stored,
            },
        );
    }
    let dependencies = sum(expected.values().map(|owner| owner.deps.len() as u64))?;
    let inventory = sum([8, mul(sections.len() as u64, 20)?, mul(dependencies, 4)?])?;
    bound(inventory <= 16384)?;
    expected.insert(
        1,
        Expected {
            kind: 1,
            version: 2,
            closure: 128,
            factor: 5,
            owner: "inventory".into(),
            deps: vec![],
            stored: inventory,
            decoded: inventory,
        },
    );
    for (k, value) in [
        ("prototype_count", prototypes.len() as u64),
        ("real_section_count", real.len() as u64),
        ("tier_frame_count", tiers.len() as u64),
        ("bucket_count", buckets.len() as u64),
        ("capacity_section_count", capacity.len() as u64),
        ("slot_count", slots.len() as u64),
        ("authoring_payload_bytes", future),
        ("real_decoded_body_payload_bytes", raw_sum),
        ("real_stored_body_payload_bytes", stored_sum),
        ("tier_payload_bytes", tier_sum),
        ("content_capacity_before_reserve_bytes", before),
        ("reserve_payload_bytes", reserve),
        ("protected_logical_capacity_bytes", add(before, reserve)?),
    ] {
        good &= nv(totals, k)? == value;
    }
    Ok((expected, good))
}
impl Evidence {
    fn forward(&self, logical: u64) -> u64 {
        (self.a * logical + self.offset) % self.p
    }
    fn inverse(&self, physical: u64) -> u64 {
        self.ai * ((physical + self.p - self.offset) % self.p) % self.p
    }
    fn lane(&self, u: &Unit, bit: u64) -> u64 {
        self.forward(u.first + bit)
    }
    fn ledger(&self, k: &str) -> u64 {
        self.ledger[k]
    }
    fn expected_factor(&self, s: &Section) -> u64 {
        self.expected
            .get(&s.id)
            .map_or(s.factor, |owner| owner.factor)
    }
    fn section_good(&self, s: &Section) -> bool {
        self.expected.get(&s.id).is_some_and(|e| {
            s.kind == e.kind
                && s.version == e.version
                && s.closure == e.closure
                && s.factor == e.factor
                && s.owner == e.owner
                && s.stored == e.stored
                && s.decoded == e.decoded
                && s.check == 1
                && s.copies == 1
        })
    }
    fn shell_owner(&self, row: u64, col: u64) -> Option<(usize, u64)> {
        let last = self.side - 1;
        let extent = self.side - self.width;
        let (sector, u, v) = if row < self.width && col < extent {
            (0, row, col)
        } else if col >= extent && row < extent {
            (1, last - col, row)
        } else if row >= extent && col >= self.width {
            (2, last - row, last - col)
        } else if col < self.width && row >= self.width {
            (3, col, last - row)
        } else {
            return None;
        };
        Some((sector, u * extent + v))
    }
}
struct Group<'a> {
    section: &'a Section,
    fragment: u64,
    lanes: Vec<&'a Unit>,
    bad: bool,
}
fn groups(e: &Evidence) -> Vec<Group<'_>> {
    let mut out = Vec::new();
    for s in &e.sections {
        for fragment in 0..s.fragments {
            out.push(Group {
                section: s,
                fragment,
                lanes: e
                    .units
                    .iter()
                    .filter(|u| u.section == s.id && u.fragment == fragment)
                    .collect(),
                bad: false,
            });
        }
    }
    out
}
fn enumerate(e: &Evidence) -> Result<([u64; 8], [u64; 8])> {
    let mut violations = [0u64; 8];
    let protected = e.q * 1728;
    let mut target_counts = vec![0u16; e.p as usize];
    let mut targets = vec![None; e.p as usize];
    let mut wrong = vec![false; e.p as usize];
    for ordinal in 0..e.q {
        for bit in 0..1728 {
            let identity = (ordinal * 1728 + bit) as usize;
            if let Some(u) = e.units.get(ordinal as usize) {
                let physical = e.lane(u, bit);
                let logical = e.inverse(physical);
                let inverse_ordinal = e.bi * (logical / 1728) % e.q;
                targets[identity] = Some(physical);
                target_counts[physical as usize] =
                    target_counts[physical as usize].saturating_add(1);
                wrong[identity] = e.map_bad
                    || u.id != ordinal + 1
                    || logical % 1728 != bit
                    || inverse_ordinal != ordinal
                    || e.forward(logical) != physical;
            } else {
                wrong[identity] = true;
            }
        }
    }
    for logical in protected..e.p {
        let physical = e.forward(logical);
        targets[logical as usize] = Some(physical);
        target_counts[physical as usize] = target_counts[physical as usize].saturating_add(1);
        wrong[logical as usize] = e.map_bad || e.inverse(physical) != logical;
    }
    for (i, target) in targets.iter().enumerate() {
        if wrong[i] || target.is_none_or(|p| target_counts[p as usize] != 1) {
            violations[0] += 1;
        }
    }
    let mut hash_table = Sha256::new();
    let mut classes = [0u64; 8];
    let mut sector_counts = [0u64; 4];
    let mut shell_detail = [0u64; 5];
    let section_types = e
        .sections
        .iter()
        .map(|s| (s.id, s.kind))
        .collect::<BTreeMap<_, _>>();
    for row in 0..e.side {
        for col in 0..e.side {
            let mut bad = false;
            let (kind, id, offset, class) = if let Some((sector, local)) = e.shell_owner(row, col) {
                sector_counts[sector] += 1;
                let sh = &e.shell[sector];
                let matches = sh
                    .spans
                    .iter()
                    .filter(|(start, count, _)| *start <= local && local < start + count)
                    .collect::<Vec<_>>();
                bad |= matches.len() != 1;
                if let Some((_, _, owner)) = matches.first() {
                    let index = match owner.as_str() {
                        "instruction" => 0,
                        "example" => 1,
                        "recipe" => 2,
                        "headroom" => 3,
                        _ => 4,
                    };
                    shell_detail[index] += 1;
                    let wanted = if local < sh.prefix {
                        0
                    } else if local < sh.prefix + sh.head {
                        1
                    } else {
                        2
                    };
                    bad |= (wanted == 0 && index > 2)
                        || (wanted == 1 && index != 3)
                        || (wanted == 2 && index != 4);
                }
                if local < sh.prefix {
                    (1u8, sector as u64, local, 0)
                } else if local < sh.prefix + sh.head {
                    (2, sector as u64, local - sh.prefix, 1)
                } else {
                    (3, sector as u64, local - sh.prefix - sh.head, 2)
                }
            } else {
                let physical = (row - e.width) * e.inner + col - e.width;
                let logical = e.inverse(physical);
                bad |= target_counts[physical as usize] != 1 || e.forward(logical) != physical;
                if logical < protected {
                    let ordinal = e.bi * (logical / 1728) % e.q;
                    let bit = logical % 1728;
                    let unit = e.units.get(ordinal as usize);
                    bad |= unit.is_none_or(|u| u.id != ordinal + 1 || e.lane(u, bit) != physical);
                    let id = unit.map_or(ordinal + 1, |u| u.id);
                    let kind = unit.and_then(|u| section_types.get(&u.section)).copied();
                    let class = match kind {
                        Some(1..=3) => 3,
                        Some(4) => 4,
                        Some(5) => 5,
                        Some(6) => 6,
                        _ => {
                            bad = true;
                            3
                        }
                    };
                    (4, id, bit, class)
                } else {
                    (5, 0, logical - protected, 7)
                }
            };
            classes[class] += 1;
            violations[1] += u64::from(bad);
            hash_table.update([kind]);
            hash_table.update((id as u32).to_be_bytes());
            hash_table.update((offset as u32).to_be_bytes());
        }
    }
    if e.table_count != e.side * e.side || format!("{:x}", hash_table.finalize()) != e.table_hash {
        violations[1] += 1;
    }
    let allprefix = sum(e.shell.iter().map(|s| s.prefix))?;
    let headroom = allprefix.div_ceil(20).max(1024);
    let extra = headroom - 1024;
    let mut shell_complete = [false; 4];
    for (i, s) in e.shell.iter().enumerate() {
        shell_complete[i] =
            s.complete && s.head == 256 + extra / 4 + u64::from((i as u64) < extra % 4);
        if sector_counts[i] != e.width * (e.side - e.width)
            || s.prefix + s.head + s.pad != sector_counts[i]
            || !shell_complete[i]
        {
            violations[2] += 1;
        }
    }
    let mut groups = groups(e);
    let mut factors = [0u64; 3];
    let mut actual_factor_units = [0u64; 3];
    let mut expected_first = 1;
    let mut mapped_hashes = Vec::with_capacity(e.units.len());
    for u in &e.units {
        let mut h = Sha256::new();
        for bit in 0..1728 {
            h.update((e.lane(u, bit) as u32).to_be_bytes());
        }
        mapped_hashes.push(format!("{:x}", h.finalize()));
    }
    for group in &mut groups {
        let s = group.section;
        let factor = e.expected_factor(s);
        let factor_index = match factor {
            1 => 0,
            2 => 1,
            _ => 2,
        };
        factors[factor_index] += 1;
        actual_factor_units[factor_index] += group.lanes.len() as u64;
        let factor_bad = !e.section_good(s)
            || group.lanes.len() as u64 != factor
            || group
                .lanes
                .iter()
                .any(|u| u.factor != factor || u.copy != 0);
        let contiguous_bad = group
            .lanes
            .iter()
            .enumerate()
            .any(|(i, u)| u.id != expected_first + i as u64 || u.replica != i as u64)
            || group.lanes.len() as u64 != factor
            || s.first + group.fragment * factor != expected_first
            || s.last != s.first + s.fragments * factor - 1;
        let mut slots = BTreeSet::new();
        let distinct_bad = group
            .lanes
            .iter()
            .any(|u| !slots.insert(u.slot) || u.slot != e.b * (u.id - 1) % e.q);
        let span_bad = group
            .lanes
            .iter()
            .any(|u| u.first != u.slot * 1728 || u.count != 1728 || u.bytes != 216);
        let mut cell_set = BTreeSet::new();
        let mut cell_bad = false;
        for u in &group.lanes {
            let ordinal = e
                .units
                .iter()
                .position(|known| std::ptr::eq(known, *u))
                .ok_or(PhysicalError::Binding)?;
            cell_bad |= mapped_hashes[ordinal] != u.mapped;
            for bit in 0..1728 {
                cell_bad |= !cell_set.insert(e.lane(u, bit));
            }
        }
        for bad in [factor_bad, contiguous_bad, distinct_bad, span_bad, cell_bad] {
            violations[3] += u64::from(bad);
            group.bad |= bad;
        }
        violations[7] += u64::from(group.bad);
        let members = (0..factor)
            .map(|replica| {
                let candidates = group
                    .lanes
                    .iter()
                    .copied()
                    .filter(|unit| unit.replica == replica)
                    .collect::<Vec<_>>();
                if candidates.len() == 1 && candidates[0].id == expected_first + replica {
                    Some(candidates[0])
                } else {
                    None
                }
            })
            .collect::<Vec<_>>();
        expected_first += factor;
        if factor > 1 {
            for left in 0..factor as usize {
                for right in left + 1..factor as usize {
                    for bit in 0..1728 {
                        let separated = match (members[left], members[right]) {
                            (Some(a), Some(b)) => {
                                let a = e.lane(a, bit);
                                let b = e.lane(b, bit);
                                (a / e.inner)
                                    .abs_diff(b / e.inner)
                                    .max((a % e.inner).abs_diff(b % e.inner))
                                    >= 32.max(e.inner / 8)
                            }
                            _ => false,
                        };
                        violations[5] += u64::from(!separated);
                    }
                }
            }
        }
    }
    let owned_classes = [
        sum([
            e.ledger("shell_instruction_cells"),
            e.ledger("shell_example_cells"),
            e.ledger("shell_recipe_cells"),
        ])?,
        e.ledger("shell_headroom_cells"),
        e.ledger("shell_fixed_pad_cells"),
        e.ledger("real_protected_cells"),
        e.ledger("capacity_probe_cells"),
        e.ledger("reserve_probe_cells"),
        e.ledger("load_probe_cells"),
        e.ledger("interior_fixed_pad_cells"),
    ];
    for i in 0..8 {
        violations[4] += u64::from(classes[i] != owned_classes[i]);
    }
    let class_sum = sum(classes)?;
    violations[4] += u64::from(class_sum != e.side * e.side);
    let factor_keys = [
        "factor_1_group_count",
        "factor_2_group_count",
        "factor_5_group_count",
    ];
    for i in 0..3 {
        let factor = [1, 2, 5][i];
        let capacity_groups = e
            .sections
            .iter()
            .filter(|section| section.factor == factor)
            .map(|section| section.fragments)
            .sum::<u64>();
        let claimed_units = e.units.iter().filter(|unit| unit.factor == factor).count() as u64;
        violations[4] += u64::from(
            factors[i] != e.ledger(factor_keys[i])
                || actual_factor_units[i] != factor * factors[i]
                || capacity_groups != factors[i]
                || claimed_units != factor * factors[i],
        );
    }
    let ids = e
        .sections
        .iter()
        .map(|s| (s.id, s))
        .collect::<BTreeMap<_, _>>();
    let mut edges = 0;
    for (id, expected) in &e.expected {
        for dependency in &expected.deps {
            edges += 1;
            let declared = ids.get(id);
            let bad = !ids.contains_key(dependency)
                || declared.is_none_or(|section| !section.deps.contains(dependency));
            violations[7] += u64::from(bad);
        }
    }
    for removed in 0..4 {
        violations[7] += u64::from(
            shell_complete
                .iter()
                .enumerate()
                .filter(|(i, complete)| *i != removed && **complete)
                .count()
                != 3,
        );
    }
    let mut ledger_good = e.semantic_good
        && e.sections.iter().all(|s| {
            e.expected
                .get(&s.id)
                .is_some_and(|owner| s.deps == owner.deps)
        })
        && e.expected.len() == e.sections.len()
        && e.sections.iter().all(|s| e.expected.contains_key(&s.id))
        && expected_first - 1 == e.q
        && e.units.len() as u64 == e.q
        && e.pad_first == protected
        && e.pad_count == e.p - protected
        && class_sum == e.side * e.side
        && sum(actual_factor_units)? == e.q
        && groups.len() as u64 == sum(factors)?;
    let stored = sum(e.sections.iter().map(|s| s.stored))?;
    let decoded = sum(e.sections.iter().filter(|s| s.kind == 3).map(|s| s.decoded))?;
    let replicated = sum(e.sections.iter().map(|s| s.factor * s.stored))?;
    let headers = sum(e
        .sections
        .iter()
        .map(|s| s.factor * (18 + 4 * s.deps.len() as u64)))?;
    let checks = sum(e.sections.iter().map(|s| s.factor * 4))?;
    let envelopes = sum(e.sections.iter().map(|s| s.factor * s.envelope))?;
    let pad = 157 * e.q;
    ledger_good &= envelopes <= pad;
    for s in &e.sections {
        ledger_good &= s.envelope == 22 + 4 * s.deps.len() as u64 + s.stored
            && s.fragments == s.envelope.div_ceil(157);
    }
    for (k, expected) in [
        ("stored_payload_bytes", stored),
        ("decoded_body_payload_bytes", decoded),
        ("replicated_payload_bytes", replicated),
        ("envelope_header_bytes", headers),
        ("section_check_bytes", checks),
        ("fragment_header_bytes", 30 * e.q),
        ("fragment_zero_pad_bytes", pad.saturating_sub(envelopes)),
        ("local_check_bytes", 4 * e.q),
        ("transport_pad_bytes", e.q),
        ("parity_bytes", 24 * e.q),
        ("encoded_transport_bytes", 216 * e.q),
        ("logical_group_count", groups.len() as u64),
        ("physical_unit_count", e.q),
        ("codeword_count", 24 * e.q),
        ("unused_cells", 0),
        ("total_cells", e.side * e.side),
    ] {
        ledger_good &= e.ledger(k) == expected;
    }
    ledger_good &= sum([
        replicated,
        headers,
        checks,
        30 * e.q,
        pad.saturating_sub(envelopes),
        4 * e.q,
        e.q,
        24 * e.q,
    ])? == 216 * e.q;
    for (i, key) in [
        "shell_instruction_cells",
        "shell_example_cells",
        "shell_recipe_cells",
        "shell_headroom_cells",
        "shell_fixed_pad_cells",
    ]
    .iter()
    .enumerate()
    {
        let equal = shell_detail[i] == e.ledger(key);
        violations[4] += u64::from(!equal);
        ledger_good &= equal;
    }
    ledger_good &= classes == owned_classes
        && factors
            .iter()
            .enumerate()
            .all(|(i, g)| *g == e.ledger(factor_keys[i]));
    violations[7] += u64::from(!ledger_good);
    violations[6] = closure_violations(e, &groups)?;
    let witnesses = [
        e.p,
        e.side * e.side,
        e.side * e.side - e.p,
        protected,
        e.side * e.side,
        1728 * (factors[1] + 10 * factors[2]),
        6 * (256 + 5 * e.q),
        groups.len() as u64 + edges + 5,
    ];
    Ok((witnesses, violations))
}
fn placements(inner: u64) -> Result<Vec<(u64, u64)>> {
    let size = 32.max(inner / 32);
    bound(inner >= size)?;
    let last = inner - size;
    let width = last + 1;
    let mut anchors = BTreeSet::new();
    let mut rows = Vec::new();
    for r in [0, last / 2, last] {
        for c in [0, last / 2, last] {
            if anchors.insert(r * width + c) {
                rows.push((r, c));
            }
        }
    }
    let sampled = crate::damage::sample_without_replacement(
        (width * width) as usize - anchors.len(),
        256 - rows.len(),
        5_134_751_402_299_490_304,
    )
    .map_err(|_| PhysicalError::Bounds)?;
    for rank in sampled {
        let mut flat = rank as u64;
        for excluded in &anchors {
            if *excluded <= flat {
                flat += 1;
            }
        }
        bound(flat < width * width && !anchors.contains(&flat))?;
        rows.push((flat / width, flat % width));
    }
    need(rows.len() == 256)?;
    Ok(rows)
}
fn closure_violations(e: &Evidence, groups: &[Group<'_>]) -> Result<u64> {
    let mut count = 0;
    let size = 32.max(e.inner / 32);
    let required_groups = groups
        .iter()
        .enumerate()
        .filter(|(_, g)| REQUIRED.contains(&g.section.id))
        .collect::<Vec<_>>();
    // Resolve physical membership independently of unrelated metadata checks.
    // Missing or nonunique replicas remove that lane, not the whole fragment.
    let mut first = 1;
    let mut usable = Vec::with_capacity(groups.len());
    for group in groups {
        let factor = e.expected_factor(group.section);
        let lanes = (0..factor)
            .filter_map(|replica| {
                let candidates = group
                    .lanes
                    .iter()
                    .copied()
                    .filter(|unit| unit.replica == replica)
                    .collect::<Vec<_>>();
                if candidates.len() == 1 && candidates[0].id == first + replica {
                    Some(candidates[0])
                } else {
                    None
                }
            })
            .collect::<Vec<_>>();
        usable.push(lanes);
        first += factor;
    }
    // The complete forward enumeration is an index for each D2 cell's inverse
    // physical-owner lookup; unlike a unique inverse it retains collisions.
    let mut physical_members = Vec::new();
    for (index, _) in &required_groups {
        for (lane, unit) in usable[*index].iter().enumerate() {
            for bit in 0..1728 {
                physical_members.push((e.lane(unit, bit), *index, lane, bit));
            }
        }
    }
    physical_members.sort_unstable();
    for (top, left) in placements(e.inner)? {
        let mut erased = BTreeMap::<(usize, usize), [u16; 24]>::new();
        let mut bit_lanes = BTreeMap::<(usize, u64), BTreeSet<usize>>::new();
        for row in top..top + size {
            for col in left..left + size {
                let physical = row * e.inner + col;
                let start = physical_members.partition_point(|entry| entry.0 < physical);
                let end = physical_members.partition_point(|entry| entry.0 <= physical);
                for &(_, group, lane, bit) in &physical_members[start..end] {
                    let words = erased.entry((group, lane)).or_insert([0; 24]);
                    words[(bit / 72) as usize] += 1;
                    bit_lanes.entry((group, bit)).or_default().insert(lane);
                }
            }
        }
        let mut unresolved = BTreeMap::<usize, [u16; 24]>::new();
        for ((group, bit), lanes) in bit_lanes {
            if lanes.len() == usable[group].len() {
                unresolved.entry(group).or_insert([0; 24])[(bit / 72) as usize] += 1;
            }
        }
        for section in REQUIRED {
            let mut survives = true;
            let mut seen = false;
            for (index, g) in &required_groups {
                if g.section.id != section {
                    continue;
                }
                seen = true;
                let mut lane_ok = false;
                for lane in 0..usable[*index].len() {
                    lane_ok |= erased
                        .get(&(*index, lane))
                        .is_none_or(|w| w.iter().all(|n| *n <= 3));
                }
                let repetition_ok = unresolved
                    .get(index)
                    .is_none_or(|w| w.iter().all(|n| *n <= 3));
                survives &= !usable[*index].is_empty() && (lane_ok || repetition_ok);
            }
            count += u64::from(!seen || !survives);
        }
    }
    let interior_groups = required_groups
        .iter()
        .map(|(index, _group)| {
            let mut good = true;
            for unit in &usable[*index] {
                for bit in 0..1728 {
                    good &= e.lane(unit, bit) < e.p;
                }
            }
            (*index, good)
        })
        .collect::<BTreeMap<_, _>>();
    for family in 0..5 {
        for omitted in 1..=e.q {
            for section in REQUIRED {
                let mut survives = true;
                let mut seen = false;
                for (index, g) in &required_groups {
                    if g.section.id != section {
                        continue;
                    }
                    seen = true;
                    let remaining = usable[*index].iter().filter(|u| u.id != omitted).count();
                    survives &= remaining > 0;
                    // D6 removes one shell sector in addition to this unit. Every lane target
                    // is independently checked to remain inside the protected interior.
                    if family > 0 {
                        survives &= interior_groups[index];
                    }
                }
                count += u64::from(!seen || !survives);
            }
        }
    }
    Ok(count)
}
/// The input order matches the file binding graph, not source construction.
pub fn build_physical_evidence_v2(
    candidate_manifest: &[u8],
    capacity_ledger: &[u8],
    ownership_ledger: &[u8],
    semantic_envelope: &[u8],
) -> Result<PhysicalEvidenceV2> {
    let evidence = admit(
        candidate_manifest,
        capacity_ledger,
        ownership_ledger,
        semantic_envelope,
    )?;
    let (witnesses, violations) = enumerate(&evidence)?;
    let rows = IDS
        .into_iter()
        .zip(witnesses)
        .zip(violations)
        .map(|((id, witness), violations)| PredicateRowV2 {
            id,
            witness,
            violations,
        })
        .collect::<Vec<_>>();
    let value = vo([
        ("schema", vs("golden-board.m2-physical-evidence/v2")),
        ("profile_id", vs(PROFILE)),
        ("scope", vs("physical-predicates-only")),
        (
            "input_sha256",
            vo([
                ("candidate_manifest", vs(hash(candidate_manifest))),
                ("capacity_ledger", vs(hash(capacity_ledger))),
                ("ownership_ledger", vs(hash(ownership_ledger))),
                ("semantic_envelope", vs(hash(semantic_envelope))),
            ]),
        ),
        (
            "predicate_rows",
            V::Array(
                rows.iter()
                    .map(|r| {
                        vo([
                            ("predicate_id", vs(r.id)),
                            ("witness_count", V::U64(r.witness)),
                            ("minimum_surviving_count", V::U64(1)),
                            ("violation_count", V::U64(r.violations)),
                            ("result", vs(if r.passed() { "pass" } else { "fail" })),
                        ])
                    })
                    .collect(),
            ),
        ),
    ]);
    let raw = serialize_manifest(&value).map_err(|_| PhysicalError::Manifest)?;
    Ok(PhysicalEvidenceV2 { raw, rows })
}
