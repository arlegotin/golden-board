//! Source-derived conservative receiver bounds, separate from measured usage.
//!
//! No carrier, observation, measured result or generated limits document enters
//! construction. Historical registry counts are inherited neutral ceilings.

use std::collections::BTreeMap;

use gb_foundation::{ManifestValue as V, serialize_manifest, validate_canonical_manifest};
use sha2::{Digest, Sha256};

const PROFILE: &str = "eh72-hier-r5-r2-r1-lzss-crc32c-v1";
const MAX_DOCUMENT: usize = 1_048_576;
const KERNELS: [&str; 22] = [
    "observation",
    "square-view",
    "shell-read",
    "route-frame",
    "recipe-parse",
    "program-refinement",
    "route-example",
    "definition-validation",
    "mapping-search",
    "unit-extraction",
    "lane-adapter",
    "repetition-adapter",
    "common-frame",
    "section-assembly",
    "section-check",
    "inventory",
    "group-layout",
    "dependency-closure",
    "body-adapter",
    "content-validation",
    "result-selection",
    "result-render",
];
type Object = BTreeMap<String, V>;
type Result<T> = std::result::Result<T, ReceiverBoundsError>;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ReceiverBoundsError {
    SourceIdentity,
    SourceShape,
    Arithmetic,
    Manifest,
    MeasuredShape,
    Exceeded,
}
impl std::fmt::Display for ReceiverBoundsError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "receiver bounds: {self:?}")
    }
}
impl std::error::Error for ReceiverBoundsError {}

/// Exact source owners; injected bytes permit explicit source-drift tests.
#[derive(Clone, Copy)]
pub struct ReceiverBoundSources<'a> {
    pub profile_policy: &'a [u8],
    pub profile_limits: &'a [u8],
    pub damage_policy: &'a [u8],
    pub resource_accounting: &'a [u8],
    pub receiver_bounds: &'a [u8],
}
impl Default for ReceiverBoundSources<'static> {
    fn default() -> Self {
        Self {
            profile_policy: include_bytes!("../../../spec/profile-policy-v2.toml"),
            profile_limits: include_bytes!("../../../spec/profile-limits-v2.toml"),
            damage_policy: include_bytes!("../../../spec/damage-policy-v2.toml"),
            resource_accounting: include_bytes!("../../../spec/resource-accounting-v2.md"),
            receiver_bounds: include_bytes!("../../../spec/receiver-bounds-v2.md"),
        }
    }
}
impl<'a> ReceiverBoundSources<'a> {
    fn rows(self) -> [(&'static str, &'a [u8]); 5] {
        [
            ("spec/profile-policy-v2.toml", self.profile_policy),
            ("spec/profile-limits-v2.toml", self.profile_limits),
            ("spec/damage-policy-v2.toml", self.damage_policy),
            ("spec/resource-accounting-v2.md", self.resource_accounting),
            ("spec/receiver-bounds-v2.md", self.receiver_bounds),
        ]
    }
}

fn add(a: u64, b: u64) -> Result<u64> {
    a.checked_add(b).ok_or(ReceiverBoundsError::Arithmetic)
}
fn mul(a: u64, b: u64) -> Result<u64> {
    a.checked_mul(b).ok_or(ReceiverBoundsError::Arithmetic)
}
fn sub(a: u64, b: u64) -> Result<u64> {
    a.checked_sub(b).ok_or(ReceiverBoundsError::Arithmetic)
}
fn sum(values: impl IntoIterator<Item = u64>) -> Result<u64> {
    values.into_iter().try_fold(0, add)
}
fn n(v: u64) -> V {
    V::U64(v)
}
fn s(v: &str) -> V {
    V::String(v.into())
}
fn obj<const N: usize>(rows: [(&str, V); N]) -> V {
    V::Object(rows.into_iter().map(|(k, v)| (k.to_owned(), v)).collect())
}
fn parse_toml(raw: &[u8]) -> Result<toml::Value> {
    toml::from_str(std::str::from_utf8(raw).map_err(|_| ReceiverBoundsError::SourceShape)?)
        .map_err(|_| ReceiverBoundsError::SourceShape)
}
fn toml_number(v: &toml::Value) -> Result<u64> {
    v.as_integer()
        .and_then(|v| u64::try_from(v).ok())
        .ok_or(ReceiverBoundsError::SourceShape)
}
fn toml_field<'a>(v: &'a toml::Value, key: &str) -> Result<&'a toml::Value> {
    v.as_table()
        .and_then(|v| v.get(key))
        .ok_or(ReceiverBoundsError::SourceShape)
}
fn field_number(v: &toml::Value, key: &str) -> Result<u64> {
    toml_number(toml_field(v, key)?)
}
fn admitted_sources(sources: ReceiverBoundSources<'_>) -> Result<toml::Value> {
    for ((_, raw), (_, exact)) in sources
        .rows()
        .into_iter()
        .zip(ReceiverBoundSources::default().rows())
    {
        if raw.is_empty() || raw.len() > MAX_DOCUMENT || raw != exact {
            return Err(ReceiverBoundsError::SourceIdentity);
        }
    }
    let policy = parse_toml(sources.profile_policy)?;
    let limits = parse_toml(sources.profile_limits)?;
    let damage = parse_toml(sources.damage_policy)?;
    for (value, schema) in [
        (&policy, "golden-board.profile-policy/v2"),
        (&limits, "golden-board.profile-limits/v2"),
        (&damage, "golden-board.damage-policy/v2"),
    ] {
        if toml_field(value, "schema")?.as_str() != Some(schema)
            || field_number(value, "policy_version")? != 2
        {
            return Err(ReceiverBoundsError::SourceShape);
        }
    }
    let candidate = toml_field(&policy, "candidate")?;
    if toml_field(candidate, "id")?.as_str() != Some(PROFILE)
        || field_number(candidate, "profile_version")? != 8
    {
        return Err(ReceiverBoundsError::SourceShape);
    }
    let registry = toml_field(toml_field(&policy, "registry")?, "order")?
        .as_array()
        .ok_or(ReceiverBoundsError::SourceShape)?;
    if registry
        .iter()
        .map(toml_number)
        .collect::<Result<Vec<_>>>()?
        != [8, 2, 3, 4, 5, 6, 7]
    {
        return Err(ReceiverBoundsError::SourceShape);
    }
    Ok(toml_field(&limits, "policy_ceiling")?.clone())
}

// The five direct owners transitively inherit this exact historical registry.
// These compile-time source files are included in the build/source snapshot;
// no revised selected geometry or result supplies a count.
fn registry_maximum() -> Result<u64> {
    let mut counts = BTreeMap::new();
    for raw in [
        include_bytes!("../../../spec/profile-limits-v0.toml").as_slice(),
        include_bytes!("../../../spec/profile-limits-v1.toml").as_slice(),
    ] {
        let doc = parse_toml(raw)?;
        for row in toml_field(&doc, "profile")?
            .as_array()
            .ok_or(ReceiverBoundsError::SourceShape)?
        {
            let version = field_number(row, "profile_version")?;
            if (2..=7).contains(&version)
                && counts
                    .insert(version, field_number(row, "protected_units")?)
                    .is_some()
            {
                return Err(ReceiverBoundsError::SourceShape);
            }
        }
    }
    if counts.keys().copied().collect::<Vec<_>>() != [2, 3, 4, 5, 6, 7] {
        return Err(ReceiverBoundsError::SourceShape);
    }
    counts
        .values()
        .copied()
        .max()
        .ok_or(ReceiverBoundsError::SourceShape)
}

fn content_workspace(bytes: u64, records: u64, regions: u64) -> Result<u64> {
    let actions = 65535.min(bytes / 4);
    let selections = 4096.min(actions);
    let lessons = 4096.min(records);
    let edges = 16384.min(bytes / 2);
    let dependency = add(mul(4, bytes)?, mul(24, records)?)?;
    let passive = sum([
        mul(64, actions)?,
        mul(32, selections)?,
        mul(24, lessons)?,
        256,
    ])?;
    let graph = add(mul(48, edges)?, mul(192, lessons)?)?;
    sum([
        mul(32, bytes)?,
        mul(128, records)?,
        mul(8, regions)?,
        dependency.max(passive).max(graph),
    ])
}

/// Derive canonical conservative bounds from owned source ceilings alone.
pub fn derive_receiver_bounds_v2(sources: ReceiverBoundSources<'_>) -> Result<Vec<u8>> {
    let c = admitted_sources(sources)?;
    let ceiling = |key: &str| field_number(&c, key);
    let views = ceiling("square_view_hypotheses")?;
    let paths = ceiling("route_path_hypotheses")?;
    let width = ceiling("shell_width")?;
    let side = ceiling("side")?;
    if width % 8 != 0 || side % 8 != 0 {
        return Err(ReceiverBoundsError::SourceShape);
    }
    let q = ceiling("physical_units")?.max(registry_maximum()?);
    let i = ceiling("inventory_entries")?;
    let d = ceiling("dependency_count_per_section")?;
    let b = ceiling("content_stream_bytes")?;
    let r = ceiling("content_records")?;
    let output = ceiling("output_bytes")?;
    let steps = ceiling("recipe_primitive_steps")?;
    let scratch = ceiling("recipe_scratch_bytes")?;
    let route_records = ceiling("route_records")?;
    let package = ceiling("recipe_package_bytes")?;
    let nodes = ceiling("recipe_nodes")?;
    let edges = ceiling("recipe_edges")?;
    let tables = ceiling("recipe_tables")?;
    let recipes = ceiling("recipes")?;
    let payload = ceiling("section_payload_bytes")?;
    let attempts = ceiling("section_attempts")?;
    let raw_bits = ceiling("raw_bits")?;
    let g = 7;
    let a = mul(mul(views, width / 8)?, 4)?;
    let f = mul(width, side)? / 8;
    let j = sum([paths, g, 1])?;
    let l = mul(j, q)?;
    let k = mul(3, l)?;
    let e = sum([18, mul(4, d)?, payload, 8])?;
    let ea = 1048576;
    let el = sum([18, mul(4, d)?, u64::from(u32::MAX), 8])?;
    let fragments = add(el, 156)? / 157;
    let u = mul(mul(i, fragments)?, 5)?;
    let h = mul(i, d)?;
    let calls = mul(j, add(mul(3, q)?, mul(2, i)?)?)?;
    let inventories = mul(j, add(q, 1)?)?;
    let bodies = mul(j, i)?;
    let storage = sum([
        package,
        mul(3, ceiling("recipe_expanded_package_bytes")?)?,
        mul(64, nodes)?,
        mul(64, tables)?,
        mul(128, recipes)?,
        mul(8, ceiling("recipe_table_payload_bytes")?)?,
    ])?;
    let parsing = sum([
        storage,
        mul(48, nodes)?,
        mul(8, edges)?,
        mul(16, tables)?,
        mul(32, recipes)?,
    ])?;
    let refine = sum([mul(32, nodes)?, mul(8, edges)?, mul(8, tables)?])?;
    let miniature = content_workspace(577, 29, mul(29, 577 / 14)?)?;
    let definition = add(mul(8, f)?, parsing.max(add(storage, mul(4, miniature)?)?))?;
    let content = content_workspace(b, r, mul(4096, 4096)?)?;
    let result = sum([
        mul(add(i, mul(g, q)?)?, add(48, e)?)?,
        mul(add(u, mul(g, q)?)?, 40 + 191)?,
        mul(48, paths)?,
        mul(2, b)?,
    ])?;
    let route_calls = mul(a, add(route_records, 3)?.max(62))?;
    let primitive = mul(
        sum([route_calls, mul(24, l)?, mul(1728 + 24, k)?, bodies])?,
        steps,
    )?;
    let inventory_payload = sub(e, 22)?;
    // Tuple fields are calls, units per call, local workspace.
    let rows = [
        (1, ceiling("observation_frame_bytes")?, 0),
        (views, raw_bits, 0),
        (mul(2, a)?, mul(8, f)?, f),
        (a, f, mul(8, route_records)?),
        (mul(a, route_records)?, package, parsing),
        (add(a, bodies)?, nodes, refine),
        (route_calls, f, sum([f, mul(64, package)?, 8 * 128])?),
        (a, f, definition),
        (a, mul(4, q)?, 64),
        (j, mul(q, 255 * 8)?, mul(q, 8 + 2 * 255)?),
        (l, 255, 255 + 191),
        (k, 5 * 1728, 216 + 2 * 1728),
        (add(l, k)?, 191, 191),
        (calls, mul(191, q)?, add(ea, mul(24, q)?)?),
        (attempts, e, e),
        (inventories, inventory_payload, mul(16, inventory_payload)?),
        (inventories, u, add(mul(128, u)?, mul(64, i)?)?),
        (inventories, h, add(mul(24, i)?, mul(8, h)?)?),
        (bodies, payload, add(payload, 32768)?),
        (mul(2, j)?, b, content),
        (j, mul(j, result)?, result),
        (2, mul(2, add(output, 1)?)?, add(output, 256)?),
    ];
    let largest_local = rows
        .iter()
        .map(|row| row.2)
        .max()
        .ok_or(ReceiverBoundsError::SourceShape)?;
    let peak = sum([
        raw_bits,
        mul(q, sum([8, 2 * 255, mul(g, 199)?])?)?,
        mul(mul(a, route_records)?, storage)?,
        mul(a, add(f, mul(16, route_records)?)?)?,
        mul(attempts, add(e, 8)?)?,
        sum([
            mul(16, inventory_payload)?,
            mul(128, u)?,
            mul(64, i)?,
            mul(8, h)?,
        ])?,
        add(mul(i, add(ceiling("decoded_body_bytes")?, 8)?)?, mul(2, b)?)?,
        mul(j, result)?,
        add(mul(128, a)?, mul(48, paths)?)?,
        add(64, f)?,
        largest_local,
        scratch,
    ])?;
    let owners = V::Object(
        sources
            .rows()
            .into_iter()
            .map(|(path, raw)| (path.to_owned(), s(&format!("{:x}", Sha256::digest(raw)))))
            .collect(),
    );
    let terms = [
        ("A", a),
        ("Q", q),
        ("G", g),
        ("J", j),
        ("L", l),
        ("K", k),
        ("E", e),
        ("Ea", ea),
        ("El", el),
        ("N", fragments),
        ("U", u),
        ("H", h),
        ("C", calls),
        ("Y", inventories),
        ("M", bodies),
        ("S", storage),
        ("Sp", parsing),
        ("X", content),
        ("Zr", result),
    ];
    let adapters = rows
        .into_iter()
        .zip(KERNELS)
        .map(|((calls, units, workspace), kernel)| {
            Ok(obj([
                ("kernel", s(kernel)),
                ("calls", n(calls)),
                ("reference_input_units", n(mul(calls, units)?)),
                ("peak_workspace_bytes", n(workspace)),
            ]))
        })
        .collect::<Result<Vec<_>>>()?;
    serialize_manifest(&obj([
        ("schema", s("golden-board.m2-receiver-bounds/v2")),
        ("profile_id", s(PROFILE)),
        ("source_owners", owners),
        (
            "derivation",
            V::Object(terms.into_iter().map(|(k, v)| (k.into(), n(v))).collect()),
        ),
        (
            "maximum_resource",
            obj([
                ("section_attempts", n(attempts)),
                ("primitive_steps", n(primitive)),
                ("peak_scratch_bytes", n(peak)),
            ]),
        ),
        ("adapter_bounds", V::Array(adapters)),
    ]))
    .map_err(|_| ReceiverBoundsError::Manifest)
}

fn object(v: &V) -> Result<&Object> {
    match v {
        V::Object(v) => Ok(v),
        _ => Err(ReceiverBoundsError::MeasuredShape),
    }
}
fn array(v: &V) -> Result<&[V]> {
    match v {
        V::Array(v) => Ok(v),
        _ => Err(ReceiverBoundsError::MeasuredShape),
    }
}
fn number(v: &V) -> Result<u64> {
    match v {
        V::U64(v) => Ok(*v),
        _ => Err(ReceiverBoundsError::MeasuredShape),
    }
}
fn closed<'a>(v: &'a V, keys: &[&str]) -> Result<&'a Object> {
    let v = object(v)?;
    if v.len() != keys.len() || keys.iter().any(|k| !v.contains_key(*k)) {
        return Err(ReceiverBoundsError::MeasuredShape);
    }
    Ok(v)
}
fn digest(v: &V) -> bool {
    matches!(v,V::String(v) if v.len()==64 && v.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b)))
}
fn compare(actual: &V, bound: &V, keys: &[&str]) -> Result<()> {
    let actual = closed(actual, keys)?;
    let bound = object(bound)?;
    for key in keys {
        if number(&actual[*key])? > number(&bound[*key])? {
            return Err(ReceiverBoundsError::Exceeded);
        }
    }
    Ok(())
}

/// Admit a measured aggregate's exact shape and componentwise source bounds.
/// Corpus coverage and observation identities remain the caller's obligation.
pub fn admit_resource_limits_v2(raw: &[u8], sources: ReceiverBoundSources<'_>) -> Result<()> {
    let bounds = validate_canonical_manifest(&derive_receiver_bounds_v2(sources)?)
        .map_err(|_| ReceiverBoundsError::Manifest)?;
    let bounds = object(&bounds)?;
    let value = validate_canonical_manifest(raw).map_err(|_| ReceiverBoundsError::Manifest)?;
    let value = closed(
        &value,
        &[
            "schema",
            "corpus_sha256",
            "case_count",
            "case_resources_sha256",
            "source_owners",
            "maximum_resource",
            "adapter_maxima",
        ],
    )?;
    if value["schema"] != s("golden-board.m2-resource-limits/v2")
        || !digest(&value["corpus_sha256"])
        || !digest(&value["case_resources_sha256"])
        || !(1..=65535).contains(&number(&value["case_count"])?)
    {
        return Err(ReceiverBoundsError::MeasuredShape);
    }
    let mut owners = object(&bounds["source_owners"])?.clone();
    owners.remove("spec/receiver-bounds-v2.md");
    if value["source_owners"] != V::Object(owners) {
        return Err(ReceiverBoundsError::SourceIdentity);
    }
    compare(
        &value["maximum_resource"],
        &bounds["maximum_resource"],
        &["section_attempts", "primitive_steps", "peak_scratch_bytes"],
    )?;
    let actual = array(&value["adapter_maxima"])?;
    let expected = array(&bounds["adapter_bounds"])?;
    if actual.len() != KERNELS.len() {
        return Err(ReceiverBoundsError::MeasuredShape);
    }
    for ((actual, bound), kernel) in actual.iter().zip(expected).zip(KERNELS) {
        let actual = closed(
            actual,
            &[
                "kernel",
                "calls",
                "reference_input_units",
                "peak_workspace_bytes",
            ],
        )?;
        if actual["kernel"] != s(kernel) {
            return Err(ReceiverBoundsError::MeasuredShape);
        }
        for key in ["calls", "reference_input_units", "peak_workspace_bytes"] {
            if number(&actual[key])? > number(&object(bound)?[key])? {
                return Err(ReceiverBoundsError::Exceeded);
            }
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn arithmetic_never_wraps_or_saturates() {
        assert_eq!(add(u64::MAX, 1), Err(ReceiverBoundsError::Arithmetic));
        assert_eq!(mul(u64::MAX, 2), Err(ReceiverBoundsError::Arithmetic));
        assert_eq!(sub(0, 1), Err(ReceiverBoundsError::Arithmetic));
        assert_eq!(content_workspace(577, 29, 29 * (577 / 14)).unwrap(), 51080);
    }
}
