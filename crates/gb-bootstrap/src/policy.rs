//! Closed, result-free M2 policy loaders and union-limit renderer.

use std::collections::BTreeSet;
use std::fmt::Write;

use gb_slice::SliceCompilation;
use sha2::{Digest, Sha256};
use toml::Value;

use crate::candidate_recipe::{r3_recipe_package_metrics, r3_recipe_resource_rows};
use crate::carrier::R3RouteOwnerGeneration;

const BYTE_MAX: usize = 65_536;
const PROFILE_SHA256: &str = "c180c2ad312c21e7559a33d9d6aee7ae5ecdc287e94197061242985c57b02265";
const DAMAGE_SHA256: &str = "9cbb185dd5d7d3fec1d4ce4aa978fa77d92e7a4ef272c2f038f0ada769c376e4";
const BOOTSTRAP_SHA256: &str = "82c25776871ac48184d5a7f15663bcc1d192618d66df72ff5fbf3a252aa564c2";
const CAPACITY_SHA256: &str = "9c70306eaed963c682652b5b61b4cf8136e5652bbaf995cc49a4e1edd12a407d";
const SLICE_SHA256: &str = "de7e22f0aa4316d9f32d9435287dd19bd6c04519aae1dc9bd816613f26929671";
const RECIPE_FIXTURE_SHA256: &str =
    "50862edb1d0c9654e5c903735f86b41c7ca2958a1e36cffb70a7622ee9a20845";
const RS_FIXTURE_SHA256: &str = "d4dcc0cc441f42c66dc19d6db636733fc577751baf073dc7f951cd3c3dd23f72";
const ROLE_IDS: [&str; 8] = [
    "grounded_rule",
    "contrasting_worked",
    "active_prediction_feedback",
    "distinct_held_out",
    "passive_trace",
    "heuristic",
    "assessment_item",
    "integrated_item",
];
const OBS_UNITS_RESOURCE_PROFILES: [(&str, &str, u64, u64); 6] = [
    (
        "eh72-r2-crc32c-v0",
        "f030732cd966fd9570149f6fd2d1befb5eed66319eb248b609693e868f977941",
        80_435,
        4_613,
    ),
    (
        "eh72-r2-crc64-ecma-v0",
        "cce1758613d7f10278533409e07103ae15162972fcf30030e17c233e39664011",
        80_435,
        4_613,
    ),
    (
        "eh72-r3-crc32c-v0",
        "8c91ba74f9bbed97aed89191e8d8d30a9a0c4d32bd5ac98b63a4c19ed71fb0e7",
        80_435,
        4_613,
    ),
    (
        "eh72-r3-crc64-ecma-v0",
        "de237fcd9d53581710404bd8b00152cb68f50adef48e715fdd4572e786bae4b8",
        80_435,
        4_613,
    ),
    (
        "rs255-191-crc32c-v0",
        "2dd94f23f63bd4fbeb8d56565a9cc9a7e0a2054d3483e364cfb60e7751058e91",
        1_698_049,
        7_688,
    ),
    (
        "rs255-191-crc64-ecma-v0",
        "1c05a1f57394d292487f46561492619358fe2d12e42e3a20194d5917f351e555",
        1_698_049,
        7_688,
    ),
];

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PolicyError {
    ByteLimit,
    OwnerIdentity,
    Toml,
    Shape,
    CapacityDrift,
    LimitsDrift,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ProfileRow {
    pub id: String,
    pub version: u16,
    pub transport: String,
    pub check_bytes: u64,
    pub required_copies: u64,
    pub unit_bytes: u64,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ProfilePolicy {
    pub sha256: String,
    pub profiles: Vec<ProfileRow>,
    pub role_bundles: Vec<(String, [u64; 14])>,
    pub maximum_content_body_payload: u64,
    pub maximum_probe_payload: u64,
    pub generic_support_fraction_numerator: u64,
    pub generic_support_fraction_denominator: u64,
    pub generic_support_minimum_cycles: u64,
    pub raw_bits: u64,
    pub side_max: u64,
    pub shell_width_min: u64,
    pub shell_width_max: u64,
    pub section_payload: u64,
    pub dependency_max: u64,
    pub inventory_entry_max: u64,
    pub section_attempts: u64,
    pub recipe_package: u64,
    pub recipe_tables: u64,
    pub recipe_table_bytes: u64,
    pub recipe_nodes: u64,
    pub recipe_edges: u64,
    pub recipe_steps: u64,
    pub recipe_scratch: u64,
    pub expected_capacity: [u64; 12],
    pub expected_slots_by_kind: [u64; 14],
    pub expected_generic_cycle_count: u64,
    pub expected_generic_slot_count: u64,
    pub expected_generic_section_count: u64,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DamagePolicy {
    pub sha256: String,
    pub transform_formulas: Vec<(String, String)>,
    pub d2_placements: u64,
    pub d3_seed_first: u64,
    pub d3_seed_count: u64,
    pub d3_seed_step: u64,
    pub d5_cases: u64,
    pub d7_common: u64,
    pub d7_eh_code: u64,
    pub d7_eh_algebra: u64,
    pub d7_rs_code: u64,
    pub d7_rs_algebra: u64,
    pub obs_units_resource_profiles: Vec<(u16, String, String, u64, u64)>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct CapacityProjection {
    values: [u64; 12],
    slots_by_kind: [u64; 14],
}

fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn document(raw: &[u8], expected: &str, schema: &str) -> Result<Value, PolicyError> {
    if raw.is_empty() || raw.len() > BYTE_MAX {
        return Err(PolicyError::ByteLimit);
    }
    if digest(raw) != expected {
        return Err(PolicyError::OwnerIdentity);
    }
    let text = std::str::from_utf8(raw).map_err(|_| PolicyError::Toml)?;
    let value: Value = toml::from_str(text).map_err(|_| PolicyError::Toml)?;
    if value.get("schema").and_then(Value::as_str) != Some(schema) {
        return Err(PolicyError::Shape);
    }
    Ok(value)
}

fn table<'a>(value: &'a Value, key: &str) -> Result<&'a toml::Table, PolicyError> {
    value
        .get(key)
        .and_then(Value::as_table)
        .ok_or(PolicyError::Shape)
}

fn integer(table: &toml::Table, key: &str) -> Result<u64, PolicyError> {
    table
        .get(key)
        .and_then(Value::as_integer)
        .and_then(|value| u64::try_from(value).ok())
        .ok_or(PolicyError::Shape)
}

fn text<'a>(table: &'a toml::Table, key: &str) -> Result<&'a str, PolicyError> {
    table
        .get(key)
        .and_then(Value::as_str)
        .ok_or(PolicyError::Shape)
}

fn array<'a>(table: &'a toml::Table, key: &str) -> Result<&'a [Value], PolicyError> {
    table
        .get(key)
        .and_then(Value::as_array)
        .map(Vec::as_slice)
        .ok_or(PolicyError::Shape)
}

pub fn load_profile_policy(raw: &[u8]) -> Result<ProfilePolicy, PolicyError> {
    let value = document(raw, PROFILE_SHA256, "golden-board.profile-policy/v0")?;
    let root = value.as_table().ok_or(PolicyError::Shape)?;
    let candidate = table(&value, "candidate_set")?;
    let ids = array(candidate, "profile_ids")?
        .iter()
        .map(|item| item.as_str().map(str::to_owned).ok_or(PolicyError::Shape))
        .collect::<Result<Vec<_>, _>>()?;
    let rows = root
        .get("profile")
        .and_then(Value::as_array)
        .ok_or(PolicyError::Shape)?;
    if ids.len() != 6 || rows.len() != 6 {
        return Err(PolicyError::Shape);
    }
    let mut profiles = Vec::new();
    for (index, row) in rows.iter().enumerate() {
        let row = row.as_table().ok_or(PolicyError::Shape)?;
        let id = text(row, "id")?.to_owned();
        let version =
            u16::try_from(integer(row, "profile_version")?).map_err(|_| PolicyError::Shape)?;
        let transport = text(row, "transport_id")?.to_owned();
        let check = text(row, "section_check_id")?;
        if id != ids[index] || usize::from(version) != index + 1 {
            return Err(PolicyError::Shape);
        }
        profiles.push(ProfileRow {
            id,
            version,
            check_bytes: match check {
                "crc32c-v0" => 4,
                "crc64-ecma-v0" => 8,
                _ => return Err(PolicyError::Shape),
            },
            required_copies: integer(row, "required_copy_count")?,
            unit_bytes: match transport.as_str() {
                "eh72-replicated-v0" => 216,
                "rs255-191-v0" => 255,
                _ => return Err(PolicyError::Shape),
            },
            transport,
        });
    }
    let capacity = table(&value, "capacity")?;
    let generic_support_fraction_numerator =
        integer(capacity, "generic_support_fraction_numerator")?;
    let generic_support_fraction_denominator =
        integer(capacity, "generic_support_fraction_denominator")?;
    let generic_support_minimum_cycles = integer(capacity, "generic_support_minimum_cycles")?;
    if generic_support_fraction_denominator == 0
        || generic_support_minimum_cycles == 0
        || text(capacity, "generic_support_rounding")? != "ceil"
    {
        return Err(PolicyError::Shape);
    }
    let role_rows = capacity
        .get("role_bundle")
        .and_then(Value::as_array)
        .ok_or(PolicyError::Shape)?;
    if role_rows.len() != ROLE_IDS.len() {
        return Err(PolicyError::Shape);
    }
    let mut role_bundles = Vec::new();
    for (index, row) in role_rows.iter().enumerate() {
        let row = row.as_table().ok_or(PolicyError::Shape)?;
        if text(row, "id")? != ROLE_IDS[index] {
            return Err(PolicyError::Shape);
        }
        let source = array(row, "kind_multiplicity")?;
        if source.len() != 14 {
            return Err(PolicyError::Shape);
        }
        let mut counts = [0_u64; 14];
        for (target, item) in counts.iter_mut().zip(source) {
            *target = item
                .as_integer()
                .and_then(|value| u64::try_from(value).ok())
                .filter(|value| *value <= 4096)
                .ok_or(PolicyError::Shape)?;
        }
        if counts.iter().sum::<u64>() == 0 {
            return Err(PolicyError::Shape);
        }
        role_bundles.push((ROLE_IDS[index].to_owned(), counts));
    }
    let expected = capacity
        .get("expected_envelope")
        .and_then(Value::as_table)
        .ok_or(PolicyError::Shape)?;
    let expected_capacity = [
        integer(expected, "concept_minima_bytes")?,
        integer(expected, "assessment_bytes")?,
        integer(expected, "integrated_bytes")?,
        integer(expected, "generic_shared_support_bytes")?,
        integer(expected, "authoring_payload_bytes")?,
        integer(expected, "bucket_count")?,
        integer(expected, "slot_count")?,
        integer(expected, "section_count")?,
        integer(expected, "real_content_body_payload_bytes")?,
        integer(expected, "required_tier_frame_payload_bytes")?,
        integer(expected, "all_tier_frame_payload_bytes")?,
        integer(expected, "real_slice_payload_excluding_inventory")?,
    ];
    let expected_slot_values = array(expected, "slot_count_by_kind")?;
    if expected_slot_values.len() != 14 {
        return Err(PolicyError::Shape);
    }
    let mut expected_slots_by_kind = [0_u64; 14];
    for (target, value) in expected_slots_by_kind.iter_mut().zip(expected_slot_values) {
        *target = value
            .as_integer()
            .and_then(|value| u64::try_from(value).ok())
            .ok_or(PolicyError::Shape)?;
    }
    let geometry = table(&value, "geometry")?;
    let resource = table(&value, "resource_policy")?;
    let bindings = table(&value, "bindings")?;
    if text(bindings, "capacity_module_sha256")? != CAPACITY_SHA256
        || text(bindings, "slice_semantic_sha256")? != SLICE_SHA256
        || text(bindings, "recipe_fixture_sha256")? != RECIPE_FIXTURE_SHA256
        || text(bindings, "rs_fixture_sha256")? != RS_FIXTURE_SHA256
    {
        return Err(PolicyError::Shape);
    }
    Ok(ProfilePolicy {
        sha256: PROFILE_SHA256.to_owned(),
        profiles,
        role_bundles,
        maximum_content_body_payload: integer(capacity, "maximum_content_body_payload")?,
        maximum_probe_payload: integer(capacity, "maximum_probe_payload")?,
        generic_support_fraction_numerator,
        generic_support_fraction_denominator,
        generic_support_minimum_cycles,
        raw_bits: integer(geometry, "raw_bits_max")?,
        side_max: integer(geometry, "side_max")?,
        shell_width_min: integer(geometry, "shell_width_min")?,
        shell_width_max: integer(geometry, "shell_width_max")?,
        section_payload: integer(resource, "section_payload_bytes_max")?,
        dependency_max: integer(resource, "dependency_count_max")?,
        inventory_entry_max: integer(resource, "inventory_entry_count_max")?,
        section_attempts: integer(resource, "section_attempt_ceiling")?,
        recipe_package: integer(resource, "recipe_encoded_bytes_max")?,
        recipe_tables: integer(resource, "recipe_tables_max")?,
        recipe_table_bytes: integer(resource, "recipe_table_bytes_max")?,
        recipe_nodes: integer(resource, "recipe_nodes_max")?,
        recipe_edges: integer(resource, "recipe_edges_max")?,
        recipe_steps: integer(resource, "recipe_primitive_steps_max")?,
        recipe_scratch: integer(resource, "recipe_scratch_bytes_max")?,
        expected_capacity,
        expected_slots_by_kind,
        expected_generic_cycle_count: integer(expected, "generic_cycle_count")?,
        expected_generic_slot_count: integer(expected, "generic_slot_count")?,
        expected_generic_section_count: integer(expected, "generic_section_count")?,
    })
}

pub fn load_damage_policy(raw: &[u8]) -> Result<DamagePolicy, PolicyError> {
    let value = document(raw, DAMAGE_SHA256, "golden-board.damage-policy/v0")?;
    let d2 = table(&value, "d2")?;
    let d3 = table(&value, "d3")?;
    let d5 = table(&value, "d5")?;
    let d7 = table(&value, "d7")?;
    let d7_counts = d7
        .get("case_count")
        .and_then(Value::as_table)
        .ok_or(PolicyError::Shape)?;
    let decoder = table(&value, "decoder")?;
    let row_keys = [
        "profile_version",
        "profile_id",
        "recipient_package_sha256",
        "decoder_30_primitive_steps",
        "decoder_30_peak_scratch_bytes",
    ];
    let declared_row_keys = array(decoder, "obs_units_resource_profile_row_keys")?;
    let resource_rows = array(decoder, "obs_units_resource_profile")?;
    let transforms = value
        .get("transform")
        .and_then(Value::as_array)
        .ok_or(PolicyError::Shape)?;
    if transforms.len() != 8
        || transforms.iter().enumerate().any(|(index, row)| {
            row.get("id").and_then(Value::as_integer) != i64::try_from(index).ok()
        })
        || integer(d3, "seed_count")? != 128
        || integer(d3, "stratum_size")? != 32
        || declared_row_keys.len() != row_keys.len()
        || declared_row_keys
            .iter()
            .zip(row_keys)
            .any(|(observed, expected)| observed.as_str() != Some(expected))
        || text(decoder, "obs_units_resource_profile_order")?
            != "profile-version-ascending-exactly-1-through-6"
        || text(decoder, "obs_units_resource_metric_source")?
            != "exact-recipe-30-derived-metrics-of-the-pre-damage-canonical-recipient-manifestation-package-bound-by-recipient-package-sha256-not-an-independent-standalone-helper-package"
        || text(decoder, "obs_units_resource_charge")?
            != "for-each-logically-tried-profile-and-observed-input-id-pair-charge-the-matching-row-even-when-package-construction-or-transport-evaluation-is-cached"
        || resource_rows.len() != OBS_UNITS_RESOURCE_PROFILES.len()
    {
        return Err(PolicyError::Shape);
    }
    let obs_units_resource_profiles = resource_rows
        .iter()
        .enumerate()
        .map(|(index, value)| {
            let row = value.as_table().ok_or(PolicyError::Shape)?;
            let expected = OBS_UNITS_RESOURCE_PROFILES[index];
            let version =
                u16::try_from(integer(row, "profile_version")?).map_err(|_| PolicyError::Shape)?;
            if row.len() != row_keys.len()
                || row.keys().any(|key| !row_keys.contains(&key.as_str()))
                || usize::from(version) != index + 1
                || text(row, "profile_id")? != expected.0
                || text(row, "recipient_package_sha256")? != expected.1
                || integer(row, "decoder_30_primitive_steps")? != expected.2
                || integer(row, "decoder_30_peak_scratch_bytes")? != expected.3
            {
                return Err(PolicyError::Shape);
            }
            Ok((
                version,
                expected.0.to_owned(),
                expected.1.to_owned(),
                expected.2,
                expected.3,
            ))
        })
        .collect::<Result<Vec<_>, _>>()?;
    Ok(DamagePolicy {
        sha256: DAMAGE_SHA256.to_owned(),
        transform_formulas: transforms
            .iter()
            .map(|row| {
                let row = row.as_table().ok_or(PolicyError::Shape)?;
                Ok((
                    text(row, "row_formula")?.to_owned(),
                    text(row, "column_formula")?.to_owned(),
                ))
            })
            .collect::<Result<Vec<_>, _>>()?,
        d2_placements: integer(d2, "placement_target")?,
        d3_seed_first: integer(d3, "seed_first")?,
        d3_seed_count: integer(d3, "seed_count")?,
        d3_seed_step: integer(d3, "seed_step")?,
        d5_cases: u64::try_from(array(d5, "fixed_permutations")?.len())
            .map_err(|_| PolicyError::Shape)?
            + integer(d5, "fisher_yates_seed_count")?,
        d7_common: integer(d7_counts, "common_excluding_code_and_algebra")?,
        d7_eh_code: integer(d7_counts, "eh_code_cases")?,
        d7_eh_algebra: integer(d7_counts, "eh_algebra_cases")?,
        d7_rs_code: integer(d7_counts, "rs_code_cases")?,
        d7_rs_algebra: integer(d7_counts, "rs_algebra_cases")?,
        obs_units_resource_profiles,
    })
}

fn pack_sections(lengths: &[u64], maximum: u64) -> Result<u64, PolicyError> {
    let mut sections = 0_u64;
    let mut length = 0_u64;
    for item in lengths {
        if *item > maximum {
            return Err(PolicyError::CapacityDrift);
        }
        if length != 0 && *item > maximum - length {
            sections += 1;
            length = 0;
        }
        length += item;
    }
    Ok(sections + u64::from(length != 0))
}

fn bundle_lengths(bundle: &[u64; 14], prototypes: &[u64; 14]) -> Vec<u64> {
    bundle
        .iter()
        .zip(prototypes)
        .flat_map(|(count, length)| std::iter::repeat_n(*length, *count as usize))
        .collect()
}

fn derive_capacity(
    policy: &ProfilePolicy,
    compiled: &SliceCompilation,
    curriculum_raw: &[u8],
) -> Result<CapacityProjection, PolicyError> {
    if digest(compiled.all_stream()) != SLICE_SHA256 {
        return Err(PolicyError::CapacityDrift);
    }
    let curriculum: Value =
        toml::from_str(std::str::from_utf8(curriculum_raw).map_err(|_| PolicyError::Toml)?)
            .map_err(|_| PolicyError::Toml)?;
    let mut prototypes = [0_u64; 14];
    if compiled.capacity_prototypes().len() != 14 {
        return Err(PolicyError::CapacityDrift);
    }
    for (index, row) in compiled.capacity_prototypes().iter().enumerate() {
        if usize::from(row.kind()) != index + 1 {
            return Err(PolicyError::CapacityDrift);
        }
        prototypes[index] = u64::from(row.frame_length());
    }
    let mut bundle_values = Vec::new();
    for (_, counts) in &policy.role_bundles {
        bundle_values.push((bundle_lengths(counts, &prototypes), *counts));
    }
    let heuristic_ids = table(&curriculum, "authoring_minimums")?
        .get("heuristic_role_required_concept_ids")
        .and_then(Value::as_array)
        .ok_or(PolicyError::Shape)?
        .iter()
        .map(|item| item.as_str().map(str::to_owned).ok_or(PolicyError::Shape))
        .collect::<Result<BTreeSet<_>, _>>()?;
    let concepts = curriculum
        .get("concept")
        .and_then(Value::as_array)
        .ok_or(PolicyError::Shape)?;
    let families = curriculum
        .get("family")
        .and_then(Value::as_array)
        .ok_or(PolicyError::Shape)?;
    let integrated = curriculum
        .get("integrated_task")
        .and_then(Value::as_array)
        .ok_or(PolicyError::Shape)?;
    let essential = table(&curriculum, "sets")?
        .get("E")
        .and_then(Value::as_array)
        .ok_or(PolicyError::Shape)?
        .iter()
        .map(|item| item.as_str().map(str::to_owned).ok_or(PolicyError::Shape))
        .collect::<Result<BTreeSet<_>, _>>()?;

    let mut concept_bytes = 0_u64;
    let mut assessment_bytes = 0_u64;
    let mut integrated_bytes = 0_u64;
    let mut bucket_count = 0_u64;
    let mut slot_count = 0_u64;
    let mut section_count = 0_u64;
    let mut slots_by_kind = [0_u64; 14];
    for concept in concepts {
        let row = concept.as_table().ok_or(PolicyError::Shape)?;
        let mut lengths = Vec::new();
        for index in 0..5 {
            lengths.extend_from_slice(&bundle_values[index].0);
            for (target, count) in slots_by_kind.iter_mut().zip(bundle_values[index].1) {
                *target += count;
            }
        }
        if heuristic_ids.contains(text(row, "id")?) {
            lengths.extend_from_slice(&bundle_values[5].0);
            for (target, count) in slots_by_kind.iter_mut().zip(bundle_values[5].1) {
                *target += count;
            }
        }
        concept_bytes += lengths.iter().sum::<u64>();
        slot_count += lengths.len() as u64;
        section_count += pack_sections(&lengths, policy.maximum_content_body_payload)?;
        bucket_count += 1;
    }
    for family in families {
        let row = family.as_table().ok_or(PolicyError::Shape)?;
        let occurrences = if essential.contains(text(row, "id")?) {
            15
        } else {
            12
        };
        let lengths = bundle_values[6].0.repeat(occurrences);
        assessment_bytes += lengths.iter().sum::<u64>();
        slot_count += lengths.len() as u64;
        for (target, count) in slots_by_kind.iter_mut().zip(bundle_values[6].1) {
            *target += count * occurrences as u64;
        }
        section_count += pack_sections(&lengths, policy.maximum_content_body_payload)?;
        bucket_count += 1;
    }
    for task in integrated {
        let row = task.as_table().ok_or(PolicyError::Shape)?;
        let occurrences = usize::try_from(integer(row, "minimum_per_form")? * 3)
            .map_err(|_| PolicyError::Shape)?;
        let lengths = bundle_values[7].0.repeat(occurrences);
        integrated_bytes += lengths.iter().sum::<u64>();
        slot_count += lengths.len() as u64;
        for (target, count) in slots_by_kind.iter_mut().zip(bundle_values[7].1) {
            *target += count * occurrences as u64;
        }
        section_count += pack_sections(&lengths, policy.maximum_content_body_payload)?;
        bucket_count += 1;
    }
    let base = concept_bytes + assessment_bytes + integrated_bytes;
    let (largest_index, _) = ROLE_IDS
        .iter()
        .enumerate()
        .map(|(index, id)| (index, (bundle_values[index].0.iter().sum::<u64>(), *id)))
        .max_by(|left, right| {
            left.1
                .0
                .cmp(&right.1.0)
                .then_with(|| right.1.1.cmp(left.1.1))
        })
        .ok_or(PolicyError::Shape)?;
    let mut cycle = prototypes.to_vec();
    cycle.extend_from_slice(&bundle_values[largest_index].0);
    let cycle_bytes = cycle.iter().sum::<u64>();
    if policy.generic_support_fraction_denominator == 0 || cycle_bytes == 0 {
        return Err(PolicyError::CapacityDrift);
    }
    let target = base
        .checked_mul(policy.generic_support_fraction_numerator)
        .ok_or(PolicyError::CapacityDrift)?
        .div_ceil(policy.generic_support_fraction_denominator);
    let cycles = policy
        .generic_support_minimum_cycles
        .max(target.div_ceil(cycle_bytes));
    let generic = cycle_bytes * cycles;
    let generic_lengths = cycle.repeat(cycles as usize);
    let generic_section_count =
        pack_sections(&generic_lengths, policy.maximum_content_body_payload)?;
    if cycles != policy.expected_generic_cycle_count
        || generic_lengths.len() as u64 != policy.expected_generic_slot_count
        || generic_section_count != policy.expected_generic_section_count
    {
        return Err(PolicyError::CapacityDrift);
    }
    section_count += generic_section_count;
    bucket_count += 1;
    slot_count += generic_lengths.len() as u64;
    for target in &mut slots_by_kind {
        *target += cycles;
    }
    for (target, count) in slots_by_kind.iter_mut().zip(bundle_values[largest_index].1) {
        *target += count * cycles;
    }
    let real_body = u64::try_from(compiled.all_stream().len() - 4 - 12)
        .map_err(|_| PolicyError::CapacityDrift)?;
    let required_tier = 22 + 4 + compiled.tier_roots()[0].frame().len() as u64;
    let all_body_count = compiled.assignments().len() as u64;
    let all_tier = 22 + 4 * all_body_count + compiled.tier_roots()[1].frame().len() as u64;
    let values = [
        concept_bytes,
        assessment_bytes,
        integrated_bytes,
        generic,
        base + generic,
        bucket_count,
        slot_count,
        section_count,
        real_body,
        required_tier,
        all_tier,
        real_body + required_tier + all_tier,
    ];
    if values != policy.expected_capacity {
        return Err(PolicyError::CapacityDrift);
    }
    Ok(CapacityProjection {
        values,
        slots_by_kind,
    })
}

#[derive(Clone, Debug)]
struct LimitRow {
    profile: ProfileRow,
    units: u64,
    encoded: u64,
    envelope: u64,
    fragments: u64,
    damage: u64,
    obs_units: u64,
}

pub fn render_profile_limits(
    policy: &ProfilePolicy,
    damage: &DamagePolicy,
    compiled: &SliceCompilation,
    curriculum: &[u8],
) -> Result<Vec<u8>, PolicyError> {
    let capacity = derive_capacity(policy, compiled, curriculum)?;
    if capacity.slots_by_kind != policy.expected_slots_by_kind {
        return Err(PolicyError::CapacityDrift);
    }
    let inventory_entries = policy
        .inventory_entry_max
        .min((policy.section_payload - 8) / 20);
    let envelope = 18 + 4 * policy.dependency_max + policy.section_payload + 8;
    let fragments = envelope.div_ceil(157);
    let before_reserve = capacity.values[11] + capacity.values[4] + policy.section_payload;
    let reserve = ((before_reserve + 18) / 19).max(382);
    let mut rows = Vec::new();
    for profile in &policy.profiles {
        let units = policy.raw_bits / (profile.unit_bytes * 8);
        let algebra = if profile.transport == "eh72-replicated-v0" {
            damage.d7_eh_code + damage.d7_eh_algebra
        } else {
            damage.d7_rs_code + damage.d7_rs_algebra
        };
        let cases = 16
            + 4
            + damage.d2_placements
            + damage.d3_seed_count
            + units
            + damage.d5_cases
            + 4 * units
            + damage.d7_common
            + algebra;
        rows.push(LimitRow {
            profile: profile.clone(),
            units,
            encoded: units * profile.unit_bytes,
            envelope: envelope - (8 - profile.check_bytes),
            fragments,
            damage: cases,
            obs_units: 4 + units * (6 + profile.unit_bytes),
        });
    }
    let max_units = rows.iter().map(|row| row.units).max().unwrap();
    let max_encoded = rows.iter().map(|row| row.encoded).max().unwrap();
    let max_damage = rows.iter().map(|row| row.damage).max().unwrap();
    let max_obs_units = rows.iter().map(|row| row.obs_units).max().unwrap();
    let d3_weight = 64_u64.max(
        (policy.side_max - 2 * policy.shell_width_min)
            .pow(2)
            .div_ceil(2000),
    );
    let ids = policy
        .profiles
        .iter()
        .map(|row| format!("\"{}\"", row.id))
        .collect::<Vec<_>>()
        .join(", ");
    let mut out = String::new();
    writeln!(out, "schema = \"golden-board.profile-limits/v0\"").unwrap();
    writeln!(
        out,
        "generation = \"componentwise-union-of-all-six-pre-result-profile-ledgers\""
    )
    .unwrap();
    writeln!(out, "profile_policy_sha256 = \"{}\"", policy.sha256).unwrap();
    writeln!(out, "damage_policy_sha256 = \"{}\"", damage.sha256).unwrap();
    writeln!(out, "bootstrap_spec_sha256 = \"{BOOTSTRAP_SHA256}\"").unwrap();
    writeln!(out, "capacity_module_sha256 = \"{CAPACITY_SHA256}\"").unwrap();
    writeln!(out, "slice_semantic_sha256 = \"{SLICE_SHA256}\"").unwrap();
    writeln!(out, "profile_ids = [{ids}]").unwrap();
    write!(out, "\n[raw]\nbits = {}\nside = {}\ncells = {}\nentry_hypotheses = 16\nshell_sectors = 4\nshell_width = {}\n", policy.raw_bits, policy.side_max, policy.raw_bits, policy.shell_width_max).unwrap();
    write!(out, "\n[semantic_capacity]\nprototype_kinds = 14\ncurriculum_concepts = 29\ncurriculum_families = 20\nintegrated_tasks = 3\nbuckets = {}\nslots = {}\nsimulated_sections = {}\nauthoring_payload_bytes = {}\nreal_content_body_sections = 77\nreal_content_body_payload_bytes = {}\ntier_frame_sections = 2\ntier_frame_payload_bytes = {}\nreal_slice_payload_excluding_inventory = {}\ninventory_payload_bytes = {}\ncontent_capacity_before_reserve_bytes = {}\nreserve_payload_bytes = {}\nreserve_probe_sections = {}\nprotected_logical_capacity_bytes = {}\n", capacity.values[5], capacity.values[6], capacity.values[7], capacity.values[4], capacity.values[8], capacity.values[9] + capacity.values[10], capacity.values[11], policy.section_payload, before_reserve, reserve, reserve.div_ceil(policy.maximum_probe_payload), before_reserve + reserve).unwrap();
    write!(out, "\n[bootstrap]\ncommon_block_bytes = 191\ncommon_payload_bytes = 157\ncommon_blocks = {max_units}\ncommon_plain_bytes = {}\nsection_payload_bytes = {}\nsection_envelope_bytes = {envelope}\nfragments_per_semantic_copy = {fragments}\nfragment_observations = {max_units}\nsemantic_copies_per_section = 3\nsections = {inventory_entries}\ninventory_entries = {inventory_entries}\ndependencies_per_section = {}\ndependency_edges = {}\nsection_attempts = {}\nassembled_content_bytes = 1048576\noutput_bytes = 1048576\n", max_units * 191, policy.section_payload, policy.dependency_max, inventory_entries * policy.dependency_max, policy.section_attempts).unwrap();
    write!(out, "\n[transport]\nprofile_tuples = 6\nprotected_units = {max_units}\nprotected_unit_bytes = 255\nencoded_transport_bytes = {max_encoded}\neh_codewords_per_unit = 24\neh_codeword_candidate_constructions = 144\nrs_symbols_per_unit = 255\nrs_erasures_per_unit = 64\nrs_unknown_errors_per_unit = 32\n").unwrap();
    write!(out, "\n[recipe]\npackage_bytes = {}\nrecipes = 256\ntables = {}\ntable_payload_bytes = {}\nnodes = {}\nedges = {}\niteration_count = 1048576\nprimitive_steps = {}\nscratch_bytes = {}\nroute_records = 256\nroute_sector_capacity_formula = \"shell_width_times_side_minus_shell_width_div_8\"\nroute_sector_capacity_bytes = 30720\n", policy.recipe_package, policy.recipe_tables, policy.recipe_table_bytes, policy.recipe_nodes, policy.recipe_edges, policy.recipe_steps, policy.recipe_scratch).unwrap();
    write!(out, "\n[damage]\ncases = {max_damage}\nd2_placements = {}\nd3_seeds = {}\nd3_substitutions = {d3_weight}\nchanged_or_erased_coordinates = {}\nsample_attempts = {}\nobs_bits_bytes = {}\nobs_matrix_bytes = {}\nobs_units_bytes = {max_obs_units}\nwrong_accepts = 0\n", damage.d2_placements, damage.d3_seed_count, policy.raw_bits, policy.raw_bits * 64 + 1024, 4 + policy.raw_bits.div_ceil(8), 2 + policy.raw_bits).unwrap();
    write!(out, "\n[content]\nstream_bytes = 1048576\nrecords = 65535\nrecords_per_non_root_kind = 4096\npayload_bytes = 1048576\ntext_bytes = 4096\nenum_entries = 4096\nvector_atoms = 65535\nmatrix_cells = 65535\nfield_schema_fields = 256\ntuple_slots = 4096\nopaque_atoms = 4096\nregions = 4096\nlesson_nodes = 4096\ncases_per_node = 4096\ncontrol_edges = 16384\nselections = 4096\nevent_budget = 65535\nrun_state_bytes = 466958\n").unwrap();
    for row in rows {
        write!(out, "\n[[profile]]\nid = \"{}\"\nprofile_version = {}\ncheck_bytes = {}\nrequired_copy_count = {}\nprotected_unit_bytes = {}\nprotected_units = {}\nencoded_transport_bytes = {}\nsection_envelope_bytes = {}\nfragments_per_semantic_copy = {}\ndamage_cases = {}\nobs_units_bytes = {}\n", row.profile.id, row.profile.version, row.profile.check_bytes, row.profile.required_copies, row.profile.unit_bytes, row.units, row.encoded, row.envelope, row.fragments, row.damage, row.obs_units).unwrap();
    }
    Ok(out.into_bytes())
}

pub fn load_profile_limits(
    raw: &[u8],
    policy: &ProfilePolicy,
    damage: &DamagePolicy,
    compiled: &SliceCompilation,
    curriculum: &[u8],
) -> Result<Value, PolicyError> {
    if raw.len() > BYTE_MAX
        || raw != render_profile_limits(policy, damage, compiled, curriculum)?.as_slice()
    {
        return Err(PolicyError::LimitsDrift);
    }
    toml::from_str(std::str::from_utf8(raw).map_err(|_| PolicyError::Toml)?)
        .map_err(|_| PolicyError::Toml)
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct R3ProjectedPolicyOwners {
    pub profile_policy: Vec<u8>,
    pub profile_policy_sha256: String,
    pub damage_policy: Vec<u8>,
    pub damage_policy_sha256: String,
    pub bootstrap_spec_sha256: String,
}

fn replace_table_string(
    raw: &[u8],
    table_name: &str,
    key: &str,
    replacement: &str,
) -> Result<Vec<u8>, PolicyError> {
    let source = std::str::from_utf8(raw).map_err(|_| PolicyError::Toml)?;
    let mut current_table = "";
    let mut replaced = 0_u8;
    let mut output = String::with_capacity(source.len());
    for line in source.split_inclusive('\n') {
        let trimmed = line.trim_end_matches('\n');
        if trimmed.starts_with('[') && trimmed.ends_with(']') {
            current_table = trimmed;
        }
        if current_table == table_name && trimmed.starts_with(&format!("{key} = \"")) {
            writeln!(output, "{key} = \"{replacement}\"").unwrap();
            replaced = replaced.checked_add(1).ok_or(PolicyError::Shape)?;
        } else {
            output.push_str(line);
        }
    }
    if replaced != 1 || !source.ends_with('\n') {
        return Err(PolicyError::Shape);
    }
    Ok(output.into_bytes())
}

fn replace_table_literal(
    raw: &[u8],
    table_name: &str,
    key: &str,
    literal: &str,
) -> Result<Vec<u8>, PolicyError> {
    let source = std::str::from_utf8(raw).map_err(|_| PolicyError::Toml)?;
    let mut current_table = "";
    let mut replaced = 0_u8;
    let mut output = String::with_capacity(source.len());
    for line in source.split_inclusive('\n') {
        let trimmed = line.trim_end_matches('\n');
        if trimmed.starts_with('[') && trimmed.ends_with(']') {
            current_table = trimmed;
        }
        if current_table == table_name && trimmed.starts_with(&format!("{key} = ")) {
            writeln!(output, "{key} = {literal}").unwrap();
            replaced = replaced.checked_add(1).ok_or(PolicyError::Shape)?;
        } else {
            output.push_str(line);
        }
    }
    if replaced != 1 || !source.ends_with('\n') {
        return Err(PolicyError::Shape);
    }
    Ok(output.into_bytes())
}

fn insert_table_before(
    raw: &[u8],
    marker: &str,
    table_bytes: &str,
) -> Result<Vec<u8>, PolicyError> {
    let source = std::str::from_utf8(raw).map_err(|_| PolicyError::Toml)?;
    if source.contains("\n[generated]\n") || !table_bytes.starts_with("[generated]\n") {
        return Err(PolicyError::Shape);
    }
    let needle = format!("\n{marker}\n");
    if source.matches(&needle).count() != 1 {
        return Err(PolicyError::Shape);
    }
    Ok(source
        .replacen(&needle, &format!("\n{table_bytes}\n{marker}\n"), 1)
        .into_bytes())
}

fn remove_table_before(raw: &[u8], table: &str, marker: &str) -> Result<Vec<u8>, PolicyError> {
    let source = std::str::from_utf8(raw).map_err(|_| PolicyError::Toml)?;
    let start_needle = format!("\n[{table}]\n");
    if !source.contains(&start_needle) {
        return Ok(raw.to_vec());
    }
    if source.matches(&start_needle).count() != 1 {
        return Err(PolicyError::Shape);
    }
    let start = source.find(&start_needle).ok_or(PolicyError::Shape)?;
    let marker_needle = format!("\n{marker}\n");
    let relative_end = source[start + 1..]
        .find(&marker_needle)
        .ok_or(PolicyError::Shape)?;
    let end = start
        .checked_add(1)
        .and_then(|value| value.checked_add(relative_end))
        .ok_or(PolicyError::Shape)?;
    let mut output = String::with_capacity(source.len());
    output.push_str(&source[..start]);
    output.push_str(&source[end..]);
    Ok(output.into_bytes())
}

/// Project the exact status-neutral profile and damage owners that the atomic
/// promotion write-set will contain.  The hash dependency order is bootstrap,
/// profile, then damage; neither upstream policy hashes profile-limits.
pub fn project_r3_policy_owners(
    route: &R3RouteOwnerGeneration,
) -> Result<R3ProjectedPolicyOwners, PolicyError> {
    let draft = &route.draft;
    let metrics = r3_recipe_package_metrics().map_err(|_| PolicyError::LimitsDrift)?;
    if metrics.package_sha256 != draft.recipient_package_sha256
        || usize::try_from(metrics.package_bytes).ok() != Some(draft.recipient_package.len())
    {
        return Err(PolicyError::LimitsDrift);
    }
    let physical_unit_count = draft.mapping.unit_slot_count;
    let encoded_transport_bytes = physical_unit_count
        .checked_mul(216)
        .ok_or(PolicyError::LimitsDrift)?;
    let package = &draft.recipient_package;
    if package.len() < 64 {
        return Err(PolicyError::LimitsDrift);
    }
    let recipient_package_node_count =
        u64::from(u32::from_be_bytes(package[20..24].try_into().unwrap()));
    let recipient_package_edge_count =
        u64::from(u32::from_be_bytes(package[24..28].try_into().unwrap()));
    let recipient_package_primitive_steps = u64::from_be_bytes(package[36..44].try_into().unwrap());
    let recipient_package_peak_scratch_bytes =
        u64::from(u32::from_be_bytes(package[44..48].try_into().unwrap()));
    let interior_side = u64::from(draft.mapping.interior_side);
    let d2_square_side = 32_u64.max(interior_side / 32);
    let d3_sample_retry_max = draft
        .mapping
        .population
        .checked_mul(64)
        .and_then(|value| value.checked_add(1_024))
        .ok_or(PolicyError::LimitsDrift)?;
    let d3_weight = 64_u64.max(draft.mapping.population.div_ceil(2_000));
    let d3_window_side = 32_u64.max(interior_side / 8);
    let d4_case_count = physical_unit_count;
    let d6_case_count = physical_unit_count
        .checked_mul(4)
        .ok_or(PolicyError::LimitsDrift)?;
    let damage_case_count = 16_u64
        .checked_add(4)
        .and_then(|value| value.checked_add(256))
        .and_then(|value| value.checked_add(128))
        .and_then(|value| value.checked_add(d4_case_count))
        .and_then(|value| value.checked_add(21))
        .and_then(|value| value.checked_add(d6_case_count))
        .and_then(|value| value.checked_add(408))
        .ok_or(PolicyError::LimitsDrift)?;
    let obs_units_bytes = r3_obs_units_bytes(physical_unit_count)?;
    let resources = r3_recipe_resource_rows().map_err(|_| PolicyError::LimitsDrift)?;
    let resource = |id| {
        resources
            .iter()
            .find(|row| row.recipe_id == id)
            .ok_or(PolicyError::LimitsDrift)
    };
    let decoder = resource(30)?;
    let repetition = resource(113)?;
    let route_example_scratch = decimal_array([metrics.route_peak_scratch_bytes; 4]);
    let route_example_steps =
        decimal_array([metrics.route_worked_held_primitive_steps_per_sector; 4]);
    let bootstrap_spec_sha256 = digest(include_bytes!("../../../spec/bootstrap-v1.md"));
    let profile_draft = remove_table_before(
        include_bytes!("../../../spec/profile-policy-v1.toml"),
        "generated",
        "[candidate_set]",
    )?;
    let profile_bound = replace_table_string(
        &profile_draft,
        "[bindings]",
        "bootstrap_sha256",
        &bootstrap_spec_sha256,
    )?;
    let profile_generated = format!(
        "[generated]\nencoded_transport_bytes = {encoded_transport_bytes}\nphysical_unit_count = {physical_unit_count}\nrecipient_package_bytes = {}\nrecipient_package_edge_count = {recipient_package_edge_count}\nrecipient_package_node_count = {recipient_package_node_count}\nrecipient_package_peak_scratch_bytes = {recipient_package_peak_scratch_bytes}\nrecipient_package_primitive_steps = {recipient_package_primitive_steps}\nrecipient_package_sha256 = \"{}\"\nroute_data_path = \"spec/route-data-v1.json\"\nroute_data_sha256 = \"{}\"\nshell_width = {}\nside = {}\n",
        draft.recipient_package.len(),
        draft.recipient_package_sha256,
        route.route_data_sha256,
        draft.shell_width,
        draft.side,
    );
    let profile_policy =
        insert_table_before(&profile_bound, "[candidate_set]", &profile_generated)?;
    let _: Value =
        toml::from_str(std::str::from_utf8(&profile_policy).map_err(|_| PolicyError::Toml)?)
            .map_err(|_| PolicyError::Toml)?;
    let profile_policy_sha256 = digest(&profile_policy);

    let damage_draft = remove_table_before(
        include_bytes!("../../../spec/damage-policy-v1.toml"),
        "generated",
        "[common]",
    )?;
    let damage_bound = replace_table_string(
        &damage_draft,
        "",
        "profile_policy_sha256",
        &profile_policy_sha256,
    )?;
    let damage_bound = replace_table_string(
        &damage_bound,
        "",
        "bootstrap_sha256",
        &bootstrap_spec_sha256,
    )?;
    let damage_generated = format!(
        "[generated]\nd2_square_side = {d2_square_side}\nd3_sample_retry_max = {d3_sample_retry_max}\nd3_weight = {d3_weight}\nd3_window_side = {d3_window_side}\nd4_case_count = {d4_case_count}\nd6_case_count = {d6_case_count}\ndamage_case_count = {damage_case_count}\nobs_units_bytes = {obs_units_bytes}\nphysical_unit_count = {physical_unit_count}\nprofile_limits_path = \"spec/profile-limits-v1.toml\"\nrecipient_package_sha256 = \"{}\"\nrepetition_113_peak_scratch_bytes = {}\nrepetition_113_primitive_steps = {}\nroute_data_path = \"spec/route-data-v1.json\"\nroute_data_sha256 = \"{}\"\nroute_example_peak_scratch_bytes_by_sector = {route_example_scratch}\nroute_example_primitive_steps_by_sector = {route_example_steps}\nroute_static_reject_primitive_steps = 0\nshell_width = {}\nside = {}\nv7_decoder_30_peak_scratch_bytes = {}\nv7_decoder_30_primitive_steps = {}\n",
        draft.recipient_package_sha256,
        repetition.peak_scratch_bytes,
        repetition.primitive_steps,
        route.route_data_sha256,
        draft.shell_width,
        draft.side,
        decoder.peak_scratch_bytes,
        decoder.primitive_steps,
    );
    let damage_policy = insert_table_before(&damage_bound, "[common]", &damage_generated)?;
    let _: Value =
        toml::from_str(std::str::from_utf8(&damage_policy).map_err(|_| PolicyError::Toml)?)
            .map_err(|_| PolicyError::Toml)?;
    let damage_policy_sha256 = digest(&damage_policy);
    Ok(R3ProjectedPolicyOwners {
        profile_policy,
        profile_policy_sha256,
        damage_policy,
        damage_policy_sha256,
        bootstrap_spec_sha256,
    })
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct R3ProfileLimitsGeneration {
    pub canonical_bytes: Vec<u8>,
    pub sha256: String,
    pub python_reproduction_receipt: Vec<u8>,
    pub python_reproduction_sha256: String,
    pub rust_reproduction_receipt: Vec<u8>,
    pub rust_reproduction_sha256: String,
}

fn decimal_array(values: impl IntoIterator<Item = u64>) -> String {
    format!(
        "[{}]",
        values
            .into_iter()
            .map(|value| value.to_string())
            .collect::<Vec<_>>()
            .join(", ")
    )
}

fn quoted_array<'a>(values: impl IntoIterator<Item = &'a str>) -> String {
    format!(
        "[{}]",
        values
            .into_iter()
            .map(|value| format!("\"{value}\""))
            .collect::<Vec<_>>()
            .join(", ")
    )
}

fn r3_obs_units_bytes(physical_units: u64) -> Result<u64, PolicyError> {
    // The maximum admitted v7-shaped OBS_UNITS record is the D7 cross-profile
    // splice with five RS255 source units, not the all-EH clean record.
    let eh_units = physical_units
        .checked_sub(5)
        .ok_or(PolicyError::LimitsDrift)?;
    4_u64
        .checked_add(
            eh_units
                .checked_mul(6 + 216)
                .ok_or(PolicyError::LimitsDrift)?,
        )
        .and_then(|value| value.checked_add(5 * (6 + 255)))
        .ok_or(PolicyError::LimitsDrift)
}

fn r3_limits_receipt(
    implementation_id: &str,
    profile_limits_sha256: &str,
    route_data_sha256: &str,
) -> Result<Vec<u8>, PolicyError> {
    let value = gb_foundation::ManifestValue::Object(std::collections::BTreeMap::from([
        (
            "implementation_id".to_owned(),
            gb_foundation::ManifestValue::String(implementation_id.to_owned()),
        ),
        (
            "profile_limits_sha256".to_owned(),
            gb_foundation::ManifestValue::String(profile_limits_sha256.to_owned()),
        ),
        (
            "route_data_sha256".to_owned(),
            gb_foundation::ManifestValue::String(route_data_sha256.to_owned()),
        ),
        (
            "schema".to_owned(),
            gb_foundation::ManifestValue::String(
                "golden-board.m2-r3-limits-reproduction/v1".to_owned(),
            ),
        ),
    ]));
    gb_foundation::serialize_manifest(&value).map_err(|_| PolicyError::LimitsDrift)
}

/// Independently derive the complete selected-v7 limits owner.  This consumes
/// route/package owner bytes and the hash-bound semantic inputs, but no carrier
/// or damage result.
pub fn render_r3_profile_limits(
    route: &R3RouteOwnerGeneration,
    compiled: &SliceCompilation,
    curriculum: &[u8],
) -> Result<R3ProfileLimitsGeneration, PolicyError> {
    let projected_owners = project_r3_policy_owners(route)?;
    let base_policy = load_profile_policy(include_bytes!("../../../spec/profile-policy-v0.toml"))?;
    let capacity = derive_capacity(&base_policy, compiled, curriculum)?;
    if capacity.slots_by_kind != base_policy.expected_slots_by_kind {
        return Err(PolicyError::CapacityDrift);
    }
    let expected_capacity = [
        39_518, 61_698, 2_637, 1_424, 105_277, 53, 4_174, 53, 13_628, 38, 342, 14_008,
    ];
    if capacity.values != expected_capacity {
        return Err(PolicyError::CapacityDrift);
    }
    let draft = &route.draft;
    let physical_units = draft.mapping.unit_slot_count;
    let encoded_transport_bytes = physical_units
        .checked_mul(216)
        .ok_or(PolicyError::LimitsDrift)?;
    let protected_cells = physical_units
        .checked_mul(1_728)
        .ok_or(PolicyError::LimitsDrift)?;
    if physical_units != 1_841
        || encoded_transport_bytes != 397_656
        || protected_cells != 3_181_248
        || draft.mapping.population != 3_182_656
        || draft.mapping.fixed_pad_cells != 1_408
        || draft.inventory_dependency_count != 78
        || draft.inventory_entry_count != 138
        || draft.inventory_fragment_count != 20
        || draft.inventory_payload_bytes != 3_080
    {
        return Err(PolicyError::LimitsDrift);
    }
    let cells = u64::from(draft.side)
        .checked_mul(u64::from(draft.side))
        .ok_or(PolicyError::LimitsDrift)?;
    let carrier_bytes = cells / 8;
    let maximum_section_envelope_bytes = 18_u64 + 16_384 + 4;
    let maximum_fragments_per_section = maximum_section_envelope_bytes.div_ceil(157);
    let repeated_groups = draft
        .factor_2_group_count
        .checked_add(draft.factor_5_group_count)
        .ok_or(PolicyError::LimitsDrift)?;
    let clean_path_eh_decoder_invocations = physical_units
        .checked_add(repeated_groups)
        .and_then(|value| value.checked_mul(24))
        .ok_or(PolicyError::LimitsDrift)?;
    let clean_path_repetition_symbol_invocations = repeated_groups
        .checked_mul(1_728)
        .ok_or(PolicyError::LimitsDrift)?;
    let d2_square_side = 32_u64.max(u64::from(draft.mapping.interior_side) / 32);
    let d3_weight = 64_u64.max(draft.mapping.population.div_ceil(2_000));
    let d3_window_side = 32_u64.max(u64::from(draft.mapping.interior_side) / 8);
    let d3_sample_retry_max = draft
        .mapping
        .population
        .checked_mul(64)
        .and_then(|value| value.checked_add(1_024))
        .ok_or(PolicyError::LimitsDrift)?;
    let d4_cases = physical_units;
    let d6_cases = physical_units
        .checked_mul(4)
        .ok_or(PolicyError::LimitsDrift)?;
    let damage_cases = 16_u64
        .checked_add(4)
        .and_then(|value| value.checked_add(256))
        .and_then(|value| value.checked_add(128))
        .and_then(|value| value.checked_add(d4_cases))
        .and_then(|value| value.checked_add(21))
        .and_then(|value| value.checked_add(d6_cases))
        .and_then(|value| value.checked_add(408))
        .ok_or(PolicyError::LimitsDrift)?;
    let obs_bits_bytes = 4_u64
        .checked_add(cells.div_ceil(8))
        .ok_or(PolicyError::LimitsDrift)?;
    let obs_matrix_bytes = 2_u64.checked_add(cells).ok_or(PolicyError::LimitsDrift)?;
    let obs_units_bytes = r3_obs_units_bytes(physical_units)?;
    if maximum_section_envelope_bytes != 16_406
        || maximum_fragments_per_section != 105
        || clean_path_eh_decoder_invocations != 55_512
        || clean_path_repetition_symbol_invocations != 815_616
        || d2_square_side != 55
        || d3_weight != 1_592
        || d3_window_side != 223
        || damage_cases != 10_038
        || obs_units_bytes != 408_901
    {
        return Err(PolicyError::LimitsDrift);
    }
    let package = &draft.recipient_package;
    if package.len() < 64 {
        return Err(PolicyError::LimitsDrift);
    }
    let recipe_count = u64::from(u16::from_be_bytes(package[16..18].try_into().unwrap()));
    let table_count = u64::from(u16::from_be_bytes(package[18..20].try_into().unwrap()));
    let package_nodes = u64::from(u32::from_be_bytes(package[20..24].try_into().unwrap()));
    let package_edges = u64::from(u32::from_be_bytes(package[24..28].try_into().unwrap()));
    let package_table_payload = u64::from(u32::from_be_bytes(package[28..32].try_into().unwrap()));
    let package_bytes = u64::from(u32::from_be_bytes(package[32..36].try_into().unwrap()));
    let package_steps = u64::from_be_bytes(package[36..44].try_into().unwrap());
    let package_scratch = u64::from(u32::from_be_bytes(package[44..48].try_into().unwrap()));
    let route_records_per_sector = draft
        .route_prefixes
        .iter()
        .map(|raw| u64::from(u16::from_be_bytes(raw[46..48].try_into().unwrap())))
        .collect::<Vec<_>>();
    if route_records_per_sector.iter().any(|value| *value != 52) {
        return Err(PolicyError::LimitsDrift);
    }
    let profile_policy_sha256 = &projected_owners.profile_policy_sha256;
    let damage_policy_sha256 = &projected_owners.damage_policy_sha256;
    let bootstrap_spec_sha256 = &projected_owners.bootstrap_spec_sha256;
    let capacity_module_sha256 = digest(include_bytes!("../../../python/golden_board/capacity.py"));
    let load_fragment_counts = decimal_array(draft.load_fragment_counts.iter().copied());
    let load_payload_bytes = decimal_array(draft.load_payload_bytes.iter().copied());
    let physical_replica_counts = decimal_array([1, 2, 5]);
    let held_record_bytes = decimal_array(draft.held_out_record_bytes_by_sector);
    let worked_record_bytes = decimal_array(draft.worked_record_bytes_by_sector);
    let route_example_steps = decimal_array([15_134; 4]);
    let route_example_scratch = decimal_array([6_163; 4]);
    let route_headroom = decimal_array(
        draft
            .route_images
            .sectors
            .iter()
            .map(|row| row.headroom_cells),
    );
    let route_prefix_cells = decimal_array(
        draft
            .route_images
            .sectors
            .iter()
            .map(|row| row.route_prefix_cells),
    );
    let route_prefix_hashes = quoted_array(
        draft
            .route_prefix_sha256_by_sector
            .iter()
            .map(String::as_str),
    );
    let profile_ids = quoted_array(["eh72-hier-r5-r2-r1-crc32c-v0"]);
    let mut out = String::new();
    writeln!(out, "schema = \"golden-board.profile-limits/v1\"").unwrap();
    writeln!(out, "generation = \"componentwise-full-v7-ledger-after-route-and-load-fixed-point-with-policy-ceilings-kept-separate-from-selected-values\"").unwrap();
    writeln!(out, "profile_policy_sha256 = \"{profile_policy_sha256}\"").unwrap();
    writeln!(out, "damage_policy_sha256 = \"{damage_policy_sha256}\"").unwrap();
    writeln!(out, "bootstrap_spec_sha256 = \"{bootstrap_spec_sha256}\"").unwrap();
    writeln!(out, "route_data_sha256 = \"{}\"", route.route_data_sha256).unwrap();
    writeln!(out, "capacity_module_sha256 = \"{capacity_module_sha256}\"").unwrap();
    writeln!(out, "slice_semantic_sha256 = \"{SLICE_SHA256}\"").unwrap();
    writeln!(out, "profile_ids = {profile_ids}").unwrap();
    write!(out, "\n[policy_ceiling]\nassembled_content_bytes = 1048576\ncarrier_bytes = {}\ndependency_count_per_section = {}\nentry_hypotheses = 16\ninventory_entries = {}\noutput_bytes = 1048576\nraw_bits = {}\nrecipe_edges = {}\nrecipe_iteration_count = 1048576\nrecipe_nodes = {}\nrecipe_package_bytes = {}\nrecipe_primitive_steps = {}\nrecipe_scratch_bytes = {}\nrecipe_table_payload_bytes = {}\nrecipe_tables = {}\nrecipes = 256\nroute_records = 256\nsection_attempts = {}\nsection_payload_bytes = {}\nshell_sectors = 4\nside = {}\nshell_width = {}\n",
        base_policy.raw_bits / 8, base_policy.dependency_max, base_policy.inventory_entry_max,
        base_policy.raw_bits, base_policy.recipe_edges, base_policy.recipe_nodes,
        base_policy.recipe_package, base_policy.recipe_steps, base_policy.recipe_scratch,
        base_policy.recipe_table_bytes, base_policy.recipe_tables, base_policy.section_attempts,
        base_policy.section_payload, base_policy.side_max, base_policy.shell_width_max).unwrap();
    write!(out, "\n[semantic_capacity]\nauthoring_payload_bytes = {}\nbuckets = {}\ncontent_capacity_before_reserve_bytes = 135669\ncurriculum_concepts = 29\ncurriculum_families = 20\nintegrated_tasks = 3\ninventory_payload_ceiling_bytes = {}\nprotected_logical_capacity_bytes = 142810\nprototype_kinds = 14\nreal_content_body_payload_bytes = {}\nreal_content_body_sections = 77\nreal_slice_payload_excluding_inventory = {}\nreserve_payload_bytes = 7141\nreserve_probe_sections = 1\nsimulated_sections = {}\nslots = {}\ntier_frame_payload_bytes = {}\ntier_frame_sections = 2\n",
        capacity.values[4], capacity.values[5], base_policy.section_payload, capacity.values[8],
        capacity.values[11], capacity.values[7], capacity.values[6], capacity.values[9] + capacity.values[10]).unwrap();
    write!(out, "\n[selected_manifestation]\ncarrier_bytes = {carrier_bytes}\ncell_inverse_multiplier = {}\ncell_multiplier = {}\ncell_offset = {}\ncells = {cells}\ndependency_edges = 78\nencoded_transport_bytes = {encoded_transport_bytes}\nfactor_1_group_count = {}\nfactor_2_group_count = {}\nfactor_5_group_count = {}\nfixed_pad_cells = {}\ninterior_side = {}\ninventory_dependency_count = {}\ninventory_entry_count = {}\ninventory_fragment_count = {}\ninventory_payload_bytes = {}\nload_fragment_counts = {load_fragment_counts}\nload_payload_bytes = {load_payload_bytes}\nlogical_group_count = {}\nmandatory_physical_unit_count = 1465\nmaximum_fragments_per_section = {maximum_fragments_per_section}\nmaximum_section_envelope_bytes = {maximum_section_envelope_bytes}\nphysical_unit_count = {physical_units}\npopulation = {}\nprotected_cells = {protected_cells}\nsector_capacity_bytes = {}\nsemantic_copy_count = 1\nseparation_window = {}\nshell_width = {}\nside = {}\nslot_inverse_multiplier = {}\nslot_multiplier = {}\n",
        draft.mapping.inverse_cell_multiplier, draft.mapping.cell_multiplier, draft.mapping.cell_offset,
        draft.factor_1_group_count, draft.factor_2_group_count, draft.factor_5_group_count,
        draft.mapping.fixed_pad_cells, draft.mapping.interior_side, draft.inventory_dependency_count,
        draft.inventory_entry_count, draft.inventory_fragment_count, draft.inventory_payload_bytes,
        draft.logical_group_count, draft.mapping.population, draft.sector_capacity_bytes,
        draft.mapping.window_side, draft.shell_width, draft.side,
        draft.mapping.inverse_slot_multiplier, draft.mapping.slot_multiplier).unwrap();
    write!(out, "\n[transport]\nclean_path_eh_decoder_invocations = {clean_path_eh_decoder_invocations}\nclean_path_repetition_candidate_groups = {repeated_groups}\nclean_path_repetition_symbol_invocations = {clean_path_repetition_symbol_invocations}\nencoded_transport_bytes = {encoded_transport_bytes}\neh_codewords_per_physical_unit = 24\nmaximum_group_candidates = 6\nphysical_replica_counts = {physical_replica_counts}\nphysical_unit_bytes = 216\nphysical_units = {physical_units}\nprofile_tuples = 1\n").unwrap();
    write!(out, "\n[route_package]\nheld_out_record_bytes_by_sector = {held_record_bytes}\nrecipe_count = {recipe_count}\nrecipient_package_bytes = {package_bytes}\nrecipient_package_edge_count = {package_edges}\nrecipient_package_node_count = {package_nodes}\nrecipient_package_peak_scratch_bytes = {package_scratch}\nrecipient_package_primitive_steps = {package_steps}\nrecipient_package_sha256 = \"{}\"\nrecipient_package_table_count = {table_count}\nrecipient_package_table_payload_bytes = {package_table_payload}\nroute_example_peak_scratch_bytes_by_sector = {route_example_scratch}\nroute_example_primitive_steps_by_sector = {route_example_steps}\nroute_headroom_cells_by_sector = {route_headroom}\nroute_prefix_cells_by_sector = {route_prefix_cells}\nroute_prefix_sha256_by_sector = {route_prefix_hashes}\nroute_records_per_sector = 52\nroute_sha256 = \"{}\"\nworked_record_bytes_by_sector = {worked_record_bytes}\n",
        draft.recipient_package_sha256, draft.route_sha256).unwrap();
    write!(out, "\n[damage]\ncases = {damage_cases}\nchanged_or_erased_coordinates = {cells}\nd0_cases = 16\nd1_cases = 4\nd2_cases = 256\nd2_square_side = {d2_square_side}\nd3_cases = 128\nd3_sample_retry_max = {d3_sample_retry_max}\nd3_weight = {d3_weight}\nd3_window_side = {d3_window_side}\nd4_cases = {d4_cases}\nd5_cases = 21\nd6_cases = {d6_cases}\nd7_cases = 408\nobs_bits_bytes = {obs_bits_bytes}\nobs_matrix_bytes = {obs_matrix_bytes}\nobs_units_bytes = {obs_units_bytes}\nwrong_accepts = 0\n").unwrap();
    write!(out, "\n[content]\ncases_per_node = 4096\ncontrol_edges = 16384\nenum_entries = 4096\nevent_budget = 65535\nfield_schema_fields = 256\nlesson_nodes = 4096\nmatrix_cells = 65535\nopaque_atoms = 4096\npayload_bytes = 1048576\nrecords = 65535\nrecords_per_non_root_kind = 4096\nregions = 4096\nrun_state_bytes = 466958\nselections = 4096\nstream_bytes = 1048576\ntext_bytes = 4096\ntuple_slots = 4096\nvector_atoms = 65535\n").unwrap();
    write!(out, "\n[[profile]]\ncheck_bytes = 4\ndamage_cases = {damage_cases}\nencoded_transport_bytes = {encoded_transport_bytes}\nfragments_per_semantic_copy = {maximum_fragments_per_section}\nid = \"eh72-hier-r5-r2-r1-crc32c-v0\"\nobs_units_bytes = {obs_units_bytes}\nphysical_replica_counts = {physical_replica_counts}\nprofile_version = 7\nprotected_unit_bytes = 216\nprotected_units = {physical_units}\nsection_envelope_bytes = {maximum_section_envelope_bytes}\nsemantic_copy_count = 1\n").unwrap();
    let canonical_bytes = out.into_bytes();
    if canonical_bytes.last() != Some(&b'\n') || canonical_bytes.len() > BYTE_MAX {
        return Err(PolicyError::LimitsDrift);
    }
    let _: Value =
        toml::from_str(std::str::from_utf8(&canonical_bytes).map_err(|_| PolicyError::Toml)?)
            .map_err(|_| PolicyError::Toml)?;
    let sha256 = digest(&canonical_bytes);
    let python_reproduction_receipt =
        r3_limits_receipt("python", &sha256, &route.route_data_sha256)?;
    let rust_reproduction_receipt = r3_limits_receipt("rust", &sha256, &route.route_data_sha256)?;
    let python_reproduction_sha256 = digest(&python_reproduction_receipt);
    let rust_reproduction_sha256 = digest(&rust_reproduction_receipt);
    if python_reproduction_sha256 == rust_reproduction_sha256 {
        return Err(PolicyError::LimitsDrift);
    }
    Ok(R3ProfileLimitsGeneration {
        canonical_bytes,
        sha256,
        python_reproduction_receipt,
        python_reproduction_sha256,
        rust_reproduction_receipt,
        rust_reproduction_sha256,
    })
}

pub fn admit_r3_profile_limits(
    raw: &[u8],
    route: &R3RouteOwnerGeneration,
    compiled: &SliceCompilation,
    curriculum: &[u8],
) -> Result<R3ProfileLimitsGeneration, PolicyError> {
    let expected = render_r3_profile_limits(route, compiled, curriculum)?;
    if raw != expected.canonical_bytes {
        return Err(PolicyError::LimitsDrift);
    }
    Ok(expected)
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct R3PromotedOwnerBundle {
    pub route: R3RouteOwnerGeneration,
    pub projected_policies: R3ProjectedPolicyOwners,
    pub limits: R3ProfileLimitsGeneration,
    pub promotion_manifest: Vec<u8>,
    pub promotion_manifest_sha256: String,
}

fn replace_draft_owner_hashes(
    raw: &[u8],
    expected: &std::collections::BTreeMap<&str, String>,
) -> Result<Vec<u8>, PolicyError> {
    let source = std::str::from_utf8(raw).map_err(|_| PolicyError::Toml)?;
    let mut in_row = false;
    let mut path: Option<&str> = None;
    let mut replaced = BTreeSet::new();
    let mut output = String::with_capacity(source.len());
    for line in source.split_inclusive('\n') {
        let trimmed = line.trim_end_matches('\n');
        if trimmed == "[[draft_owner]]" {
            in_row = true;
            path = None;
        } else if trimmed.starts_with('[') && trimmed.ends_with(']') {
            in_row = false;
            path = None;
        }
        if in_row && trimmed.starts_with("path = \"") && trimmed.ends_with('"') {
            path = Some(&trimmed[8..trimmed.len() - 1]);
        }
        if in_row && trimmed.starts_with("sha256 = \"") {
            let owner_path = path.ok_or(PolicyError::Shape)?;
            let hash = expected.get(owner_path).ok_or(PolicyError::Shape)?;
            writeln!(output, "sha256 = \"{hash}\"").unwrap();
            if !replaced.insert(owner_path.to_owned()) {
                return Err(PolicyError::Shape);
            }
        } else {
            output.push_str(line);
        }
    }
    if replaced.len() != expected.len() || !source.ends_with('\n') {
        return Err(PolicyError::Shape);
    }
    Ok(output.into_bytes())
}

fn replace_generated_owner_blocks(
    raw: &[u8],
    route: &R3RouteOwnerGeneration,
    limits: &R3ProfileLimitsGeneration,
) -> Result<Vec<u8>, PolicyError> {
    let parsed: Value = toml::from_str(std::str::from_utf8(raw).map_err(|_| PolicyError::Toml)?)
        .map_err(|_| PolicyError::Toml)?;
    let rows = parsed
        .get("generated_owner")
        .and_then(Value::as_array)
        .ok_or(PolicyError::Shape)?;
    if rows.len() != 2 {
        return Err(PolicyError::Shape);
    }
    let required = |index: usize| -> Result<Vec<&str>, PolicyError> {
        rows[index]
            .get("required_fields")
            .and_then(Value::as_array)
            .ok_or(PolicyError::Shape)?
            .iter()
            .map(|value| value.as_str().ok_or(PolicyError::Shape))
            .collect()
    };
    if rows[0].get("path").and_then(Value::as_str) != Some("spec/route-data-v1.json")
        || rows[1].get("path").and_then(Value::as_str) != Some("spec/profile-limits-v1.toml")
    {
        return Err(PolicyError::Shape);
    }
    let route_fields = quoted_array(required(0)?);
    let limits_fields = quoted_array(required(1)?);
    let replacement = format!(
        "[[generated_owner]]\npath = \"spec/route-data-v1.json\"\npython_reproduction_sha256 = \"{}\"\nrequired_fields = {route_fields}\nrust_reproduction_sha256 = \"{}\"\nschema = \"golden-board.route-data/v1\"\nsha256 = \"{}\"\nstate = \"independently-reproduced\"\n\n[[generated_owner]]\npath = \"spec/profile-limits-v1.toml\"\npython_reproduction_sha256 = \"{}\"\nrequired_fields = {limits_fields}\nrust_reproduction_sha256 = \"{}\"\nschema = \"golden-board.profile-limits/v1\"\nsha256 = \"{}\"\nstate = \"independently-reproduced\"\n",
        route.python_reproduction_sha256,
        route.rust_reproduction_sha256,
        route.route_data_sha256,
        limits.python_reproduction_sha256,
        limits.rust_reproduction_sha256,
        limits.sha256,
    );
    let source = std::str::from_utf8(raw).map_err(|_| PolicyError::Toml)?;
    let start_needle = "[[generated_owner]]\n";
    let start = source.find(start_needle).ok_or(PolicyError::Shape)?;
    let end_needle = "[algebraic_binding]\n";
    let relative_end = source[start..].find(end_needle).ok_or(PolicyError::Shape)?;
    let end = start.checked_add(relative_end).ok_or(PolicyError::Shape)?;
    if source[start..end].matches(start_needle).count() != 2 {
        return Err(PolicyError::Shape);
    }
    let mut output = String::with_capacity(source.len() + replacement.len());
    output.push_str(&source[..start]);
    output.push_str(&replacement);
    output.push_str(&source[end..]);
    Ok(output.into_bytes())
}

/// Render the complete five-file pre-result-frozen owner bundle in acyclic
/// hash order without writing tracked files.
pub fn render_r3_promoted_owner_bundle(
    compiled: &SliceCompilation,
    curriculum: &[u8],
) -> Result<R3PromotedOwnerBundle, PolicyError> {
    let route = crate::carrier::generate_r3_route_owner().map_err(|_| PolicyError::LimitsDrift)?;
    let projected_policies = project_r3_policy_owners(&route)?;
    let limits = render_r3_profile_limits(&route, compiled, curriculum)?;
    let promotion_draft = include_bytes!("../../../spec/m2-r3-owner-promotion-v1.toml");
    let promotion = replace_table_literal(promotion_draft, "", "status", "\"pre-result-frozen\"")?;
    let promotion = replace_table_literal(&promotion, "", "damage_observation_authorized", "true")?;
    let promotion = replace_table_literal(
        &promotion,
        "[freeze_barrier]",
        "draft_hashes_may_change_before_freeze",
        "false",
    )?;
    let owner_fixture = include_bytes!("../../../conformance/m2-r3-owner-v1.json");
    let hashes = std::collections::BTreeMap::from([
        (
            "spec/bootstrap-v1.md",
            projected_policies.bootstrap_spec_sha256.clone(),
        ),
        (
            "spec/profile-policy-v1.toml",
            projected_policies.profile_policy_sha256.clone(),
        ),
        (
            "spec/damage-policy-v1.toml",
            projected_policies.damage_policy_sha256.clone(),
        ),
        ("conformance/m2-r3-owner-v1.json", digest(owner_fixture)),
    ]);
    let promotion = replace_draft_owner_hashes(&promotion, &hashes)?;
    let promotion_manifest = replace_generated_owner_blocks(&promotion, &route, &limits)?;
    let parsed: Value =
        toml::from_str(std::str::from_utf8(&promotion_manifest).map_err(|_| PolicyError::Toml)?)
            .map_err(|_| PolicyError::Toml)?;
    if parsed.get("status").and_then(Value::as_str) != Some("pre-result-frozen")
        || parsed
            .get("damage_observation_authorized")
            .and_then(Value::as_bool)
            != Some(true)
        || parsed
            .get("freeze_barrier")
            .and_then(|value| value.get("draft_hashes_may_change_before_freeze"))
            .and_then(Value::as_bool)
            != Some(false)
    {
        return Err(PolicyError::Shape);
    }
    let promotion_manifest_sha256 = digest(&promotion_manifest);
    Ok(R3PromotedOwnerBundle {
        route,
        projected_policies,
        limits,
        promotion_manifest,
        promotion_manifest_sha256,
    })
}

/// Strictly admit the same complete promoted owner bundle in Rust.  Exact byte
/// equality to independent regeneration rejects unknown, partial, stale,
/// cyclic, receipt, and cross-hash mutations before any carrier is built.
#[allow(clippy::too_many_arguments)]
pub fn admit_r3_promoted_owner_bundle(
    bootstrap_spec: &[u8],
    profile_policy: &[u8],
    damage_policy: &[u8],
    route_data: &[u8],
    profile_limits: &[u8],
    promotion_manifest: &[u8],
    owner_fixture: &[u8],
    compiled: &SliceCompilation,
    curriculum: &[u8],
) -> Result<R3PromotedOwnerBundle, PolicyError> {
    if bootstrap_spec != include_bytes!("../../../spec/bootstrap-v1.md")
        || owner_fixture != include_bytes!("../../../conformance/m2-r3-owner-v1.json")
    {
        return Err(PolicyError::OwnerIdentity);
    }
    let expected = render_r3_promoted_owner_bundle(compiled, curriculum)?;
    if profile_policy != expected.projected_policies.profile_policy
        || damage_policy != expected.projected_policies.damage_policy
        || route_data != expected.route.route_data
        || profile_limits != expected.limits.canonical_bytes
        || promotion_manifest != expected.promotion_manifest
    {
        return Err(PolicyError::OwnerIdentity);
    }
    crate::carrier::admit_r3_route_data(route_data).map_err(|_| PolicyError::Shape)?;
    admit_r3_profile_limits(profile_limits, &expected.route, compiled, curriculum)?;
    Ok(expected)
}
