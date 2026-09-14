use gb_bootstrap::candidate_recipe::build_eh_recipe_package;
use gb_bootstrap::carrier::{build_r3_gate_one_through_five, build_route_images};
use gb_bootstrap::damage_v1::{decode_bits_v1, route_conflict_v1};
use gb_bootstrap::policy::{
    PolicyError, admit_r3_promoted_owner_bundle, load_damage_policy, load_profile_limits,
    load_profile_policy, render_profile_limits, render_r3_promoted_owner_bundle,
};
use gb_foundation::{ManifestValue, serialize_manifest, validate_canonical_manifest};
use gb_slice::{SliceInputs, compile_slice_v0};
use sha2::{Digest, Sha256};

fn sha256(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn slice() -> gb_slice::SliceCompilation {
    compile_slice_v0(SliceInputs {
        declaration: include_bytes!("../../../studies/m2/slice-v0.json"),
        content_fixture: include_bytes!("../../../conformance/content-v0.json"),
        chess_fixture: include_bytes!("../../../conformance/chess-v0.json"),
        game_set: include_bytes!("../../../reports/game-set-v0.bin"),
        content_spec: include_bytes!("../../../spec/content-v0.md"),
        constants: include_bytes!("../../../spec/constants-v0.toml"),
        curriculum: include_bytes!("../../../spec/curriculum-v0.toml"),
    })
    .unwrap()
}

#[test]
fn exact_policy_owners_and_full_set_limits_are_independently_derived() {
    let profile_raw = include_bytes!("../../../spec/profile-policy-v0.toml");
    let damage_raw = include_bytes!("../../../spec/damage-policy-v0.toml");
    let limits_raw = include_bytes!("../../../spec/profile-limits-v0.toml");
    let curriculum = include_bytes!("../../../spec/curriculum-v0.toml");
    let profile = load_profile_policy(profile_raw).unwrap();
    let damage = load_damage_policy(damage_raw).unwrap();
    assert_eq!(profile.profiles.len(), 6);
    assert_eq!(profile.profiles[0].id, "eh72-r2-crc32c-v0");
    assert_eq!(profile.profiles[5].id, "rs255-191-crc64-ecma-v0");
    assert_eq!(damage.d3_seed_first, 0x4742_4d32_0000_0000);
    assert_eq!(damage.d3_seed_count, 128);
    assert_eq!(
        damage.obs_units_resource_profiles,
        vec![
            (
                1,
                "eh72-r2-crc32c-v0".to_owned(),
                "f030732cd966fd9570149f6fd2d1befb5eed66319eb248b609693e868f977941".to_owned(),
                80_435,
                4_613
            ),
            (
                2,
                "eh72-r2-crc64-ecma-v0".to_owned(),
                "cce1758613d7f10278533409e07103ae15162972fcf30030e17c233e39664011".to_owned(),
                80_435,
                4_613
            ),
            (
                3,
                "eh72-r3-crc32c-v0".to_owned(),
                "8c91ba74f9bbed97aed89191e8d8d30a9a0c4d32bd5ac98b63a4c19ed71fb0e7".to_owned(),
                80_435,
                4_613
            ),
            (
                4,
                "eh72-r3-crc64-ecma-v0".to_owned(),
                "de237fcd9d53581710404bd8b00152cb68f50adef48e715fdd4572e786bae4b8".to_owned(),
                80_435,
                4_613
            ),
            (
                5,
                "rs255-191-crc32c-v0".to_owned(),
                "2dd94f23f63bd4fbeb8d56565a9cc9a7e0a2054d3483e364cfb60e7751058e91".to_owned(),
                1_698_049,
                7_688
            ),
            (
                6,
                "rs255-191-crc64-ecma-v0".to_owned(),
                "1c05a1f57394d292487f46561492619358fe2d12e42e3a20194d5917f351e555".to_owned(),
                1_698_049,
                7_688
            ),
        ]
    );
    assert_eq!(
        damage.transform_formulas,
        [
            ("r", "c"),
            ("side_minus_1_minus_c", "r"),
            ("side_minus_1_minus_r", "side_minus_1_minus_c"),
            ("c", "side_minus_1_minus_r"),
            ("r", "side_minus_1_minus_c"),
            ("side_minus_1_minus_c", "side_minus_1_minus_r"),
            ("side_minus_1_minus_r", "c"),
            ("c", "r"),
        ]
        .map(|(row, column)| (row.to_owned(), column.to_owned()))
    );
    let compiled = slice();
    assert_eq!(
        render_profile_limits(&profile, &damage, &compiled, curriculum).unwrap(),
        limits_raw
    );
    let loaded = load_profile_limits(limits_raw, &profile, &damage, &compiled, curriculum).unwrap();
    assert_eq!(
        loaded["profile_ids"].as_array().unwrap().len(),
        profile.profiles.len()
    );
    assert_eq!(loaded["damage"]["cases"].as_integer(), Some(12_968));
}

#[test]
fn owner_identity_and_generated_limit_drift_fail_closed() {
    let profile_raw = include_bytes!("../../../spec/profile-policy-v0.toml");
    let damage_raw = include_bytes!("../../../spec/damage-policy-v0.toml");
    let limits_raw = include_bytes!("../../../spec/profile-limits-v0.toml");
    let curriculum = include_bytes!("../../../spec/curriculum-v0.toml");

    let mut mutation = profile_raw.to_vec();
    let middle = mutation.len() / 2;
    mutation[middle] ^= 1;
    assert_eq!(
        load_profile_policy(&mutation).unwrap_err(),
        PolicyError::OwnerIdentity
    );
    let mut mutation = damage_raw.to_vec();
    let middle = mutation.len() / 2;
    mutation[middle] ^= 1;
    assert_eq!(
        load_damage_policy(&mutation).unwrap_err(),
        PolicyError::OwnerIdentity
    );

    let profile = load_profile_policy(profile_raw).unwrap();
    let damage = load_damage_policy(damage_raw).unwrap();
    let compiled = slice();
    let mut mutation = limits_raw.to_vec();
    let offset = mutation
        .windows(b"cases = 12968".len())
        .position(|window| window == b"cases = 12968")
        .unwrap();
    mutation[offset + b"cases = 1296".len()] = b'9';
    assert_eq!(
        load_profile_limits(&mutation, &profile, &damage, &compiled, curriculum).unwrap_err(),
        PolicyError::LimitsDrift
    );
}

fn replace_once(raw: &[u8], before: &[u8], after: &[u8]) -> Vec<u8> {
    let offset = raw
        .windows(before.len())
        .position(|window| window == before)
        .expect("named owner field");
    assert_eq!(
        raw[offset + before.len()..]
            .windows(before.len())
            .position(|window| window == before),
        None,
        "named owner field must be unique"
    );
    let mut output = Vec::with_capacity(raw.len() - before.len() + after.len());
    output.extend_from_slice(&raw[..offset]);
    output.extend_from_slice(after);
    output.extend_from_slice(&raw[offset + before.len()..]);
    output
}

fn route_generated(
    value: &mut ManifestValue,
) -> &mut std::collections::BTreeMap<String, ManifestValue> {
    let ManifestValue::Object(root) = value else {
        panic!("route root")
    };
    let ManifestValue::Object(generated) = root.get_mut("generated").unwrap() else {
        panic!("generated object")
    };
    generated
}

#[test]
fn strict_r3_promoted_owner_bundle_and_hash_dag_are_exact() {
    let compiled = slice();
    let curriculum = include_bytes!("../../../spec/curriculum-v0.toml");
    let bundle = render_r3_promoted_owner_bundle(&compiled, curriculum).unwrap();
    assert_eq!(
        bundle.route.route_data_sha256,
        "94df79d9a3fb01b69014417683a0f48f2222fea9fe991361bc99aa0c30dc663e"
    );
    assert_eq!(
        bundle.projected_policies.profile_policy_sha256,
        "44215d993e3fdfdd1630c404f1ee969e8abc6e4928fda83365fc6940e5cfd412"
    );
    assert_eq!(
        bundle.projected_policies.damage_policy_sha256,
        "b3b28f00d3ba04addbed4517eb1abb4ecd02796176eaaecdbc1d47f1f39509df"
    );
    assert_eq!(
        bundle.limits.sha256,
        "32c2bd0cb978eb800bed7f8ac1c7db223b593b4cf3bad951a9ce4cdc3a568902"
    );
    assert_eq!(
        bundle.promotion_manifest_sha256,
        "8c30ae216f5a3fd8ee13f2821d38412afa6c50303c9140cbe54da8610df9cd8d"
    );
    assert_eq!(
        bundle.limits.python_reproduction_sha256,
        "08c030afabe1291b3fa0b20a27666e480a242801fc1978f27992a161cf50b883"
    );
    assert_eq!(
        bundle.limits.rust_reproduction_sha256,
        "d52a1e9770438e53354599ca899ec0aad328c46739b42d27dec048ec9977750b"
    );
    let damage: toml::Value =
        toml::from_str(std::str::from_utf8(&bundle.projected_policies.damage_policy).unwrap())
            .unwrap();
    assert_eq!(
        damage["gate6_convergence_refreeze"]["precursor_archive_manifest_sha256"].as_str(),
        Some("d1ece9d02628a624d58837b9a1c1994dfb521e96303df66758c95880b2d378e4")
    );
    assert_eq!(
        damage["admission"]["canonical_regeneration_precondition"].as_str(),
        Some(
            "all-four-owned-eleven-file-archive-manifests-exist-match-and-verify-and-the-canonical-v7-candidate-path-is-absent"
        )
    );
    let limits: toml::Value =
        toml::from_str(std::str::from_utf8(&bundle.limits.canonical_bytes).unwrap()).unwrap();
    assert_eq!(
        limits["damage"]["obs_units_bytes"].as_integer(),
        Some(408_901)
    );
    assert_eq!(limits["damage"]["cases"].as_integer(), Some(10_038));
    assert_eq!(
        limits["transport"]["clean_path_eh_decoder_invocations"].as_integer(),
        Some(55_512)
    );
    admit_r3_promoted_owner_bundle(
        include_bytes!("../../../spec/bootstrap-v1.md"),
        &bundle.projected_policies.profile_policy,
        &bundle.projected_policies.damage_policy,
        &bundle.route.route_data,
        &bundle.limits.canonical_bytes,
        &bundle.promotion_manifest,
        include_bytes!("../../../conformance/m2-r3-owner-v1.json"),
        &compiled,
        curriculum,
    )
    .unwrap();
}

#[test]
fn final_convergence_gates_one_through_five_hash_kat() {
    let compiled = slice();
    let result = build_r3_gate_one_through_five(
        include_bytes!("../../../spec/bootstrap-v1.md"),
        include_bytes!("../../../spec/profile-policy-v1.toml"),
        include_bytes!("../../../spec/damage-policy-v1.toml"),
        include_bytes!("../../../spec/route-data-v1.json"),
        include_bytes!("../../../spec/profile-limits-v1.toml"),
        include_bytes!("../../../spec/m2-r3-owner-promotion-v1.toml"),
        include_bytes!("../../../conformance/m2-r3-owner-v1.json"),
        &compiled,
        include_bytes!("../../../spec/curriculum-v0.toml"),
    )
    .unwrap();
    assert_eq!(result.gate_passes, [true; 5]);
    assert_eq!(
        sha256(&result.artifacts.candidate_manifest),
        "38839aa28561ff2bec0997a80d8dc938e876526c25f40e23b6a78844f8fc1d86"
    );
    assert_eq!(
        result.artifacts.candidate_manifest_identity,
        "d783917d34bc6fb472ea7e20c989562092707c516195019434e01f2bc6f68681"
    );
    assert_eq!(
        result.artifacts.carrier_sha256,
        "c6309da5f199a237b8fc79292a5135581ad0f9b517fbe9516770ebaf084d49b0"
    );
    assert_eq!(
        result.artifacts.ownership_sha256,
        "fe82dc8119d77a855e7227dea95a673e3fb2ffb5a9c513cf31a169ea53ee5d12"
    );
    assert_eq!(
        result.artifacts.capacity_ledger_sha256,
        "a6e4a9b5e6a78a3ecf7d42ebbe75b0fa84258b6931183e37109dc927d0f9d2c6"
    );
    assert_eq!(
        result.artifacts.density_ledger_sha256,
        "6e931df836f063e1de96ee73514ca91b4ddd59071bc8338bdd5a79244fcbee61"
    );
    let archived = include_bytes!(
        "../../../artifacts/history/m2-r3-pre-gate6-convergence-clarification/eh72-hier-r5-r2-r1-crc32c-v0/candidate-manifest.json"
    );
    assert_eq!(
        sha256(archived),
        "4439abb20aeb4943d9f3dddd4b2b914c08f3a411b791d2ced797533351168019"
    );
    let archived = validate_canonical_manifest(archived).unwrap();
    let ManifestValue::Object(archived) = archived else {
        panic!("archive candidate object")
    };
    assert_eq!(
        archived.get("manifest_identity"),
        Some(&ManifestValue::String(
            "69b4052299e43a675683361e6a7fa83798b7b3646c873233cfbdd18432ac4cf4".to_owned()
        ))
    );

    let legacy_package = build_eh_recipe_package(3).unwrap();
    let legacy_routes = build_route_images(
        include_bytes!("../../../spec/route-data-v0.json"),
        3,
        &legacy_package,
        result.core.side,
        result.core.shell_width,
    )
    .unwrap();
    let legacy_sector = &legacy_routes.sectors[0];
    assert_eq!(legacy_sector.route_prefix_cells % 8, 0);
    let mut legacy_prefix = vec![0_u8; legacy_sector.route_prefix_cells as usize / 8];
    for (bit, value) in legacy_sector.bits[..legacy_sector.route_prefix_cells as usize]
        .iter()
        .copied()
        .enumerate()
    {
        legacy_prefix[bit / 8] |= value << (7 - bit % 8);
    }
    let conflict = route_conflict_v1(&result.core, &legacy_prefix).unwrap();
    let decoded = decode_bits_v1(&conflict).unwrap();
    let v7_path = 15_134_u64 + 1_841 * 24 * 80_435 + 472 * (1_728 * 24 + 24 * 80_435);
    // The archived v3 route executes recipe 30 for both fact-8 examples.
    // The v7 route uses recipe 113 there, so projecting the v7 recipe-ID list
    // into v3 and merely dropping 113 undercharges exactly two recipe-30 runs.
    let legacy_route = 15_086_u64 + 2 * 80_435;
    let legacy_path = legacy_route + 1_841 * 24 * 80_435;
    assert_eq!(
        (
            decoded.resource.section_attempts,
            decoded.resource.primitive_steps,
            decoded.resource.peak_scratch_bytes,
        ),
        (138, 3 * v7_path + legacy_path, 6_163)
    );
    assert_eq!(decoded.resource.primitive_steps, 17_008_208_910);
}

#[test]
fn strict_r3_bundle_rejects_named_stale_partial_unknown_and_cycle_mutants() {
    let compiled = slice();
    let curriculum = include_bytes!("../../../spec/curriculum-v0.toml");
    let bundle = render_r3_promoted_owner_bundle(&compiled, curriculum).unwrap();
    let bootstrap = include_bytes!("../../../spec/bootstrap-v1.md");
    let fixture = include_bytes!("../../../conformance/m2-r3-owner-v1.json");
    let mut cases: Vec<(&str, Vec<u8>, Vec<u8>, Vec<u8>, Vec<u8>, Vec<u8>)> = Vec::new();
    cases.push((
        "profile-generated-value",
        replace_once(
            &bundle.projected_policies.profile_policy,
            b"physical_unit_count = 1841",
            b"physical_unit_count = 1842",
        ),
        bundle.projected_policies.damage_policy.clone(),
        bundle.route.route_data.clone(),
        bundle.limits.canonical_bytes.clone(),
        bundle.promotion_manifest.clone(),
    ));
    cases.push((
        "profile-partial-generated",
        replace_once(
            &bundle.projected_policies.profile_policy,
            b"recipient_package_bytes = 25930\n",
            b"",
        ),
        bundle.projected_policies.damage_policy.clone(),
        bundle.route.route_data.clone(),
        bundle.limits.canonical_bytes.clone(),
        bundle.promotion_manifest.clone(),
    ));
    cases.push((
        "profile-unknown-cycle-binding",
        replace_once(
            &bundle.projected_policies.profile_policy,
            b"[candidate_set]\n",
            b"profile_limits_sha256 = \"0000000000000000000000000000000000000000000000000000000000000000\"\n\n[candidate_set]\n",
        ),
        bundle.projected_policies.damage_policy.clone(),
        bundle.route.route_data.clone(),
        bundle.limits.canonical_bytes.clone(),
        bundle.promotion_manifest.clone(),
    ));
    cases.push((
        "damage-obs-units-clean-only",
        bundle.projected_policies.profile_policy.clone(),
        replace_once(
            &bundle.projected_policies.damage_policy,
            b"obs_units_bytes = 408901",
            b"obs_units_bytes = 408706",
        ),
        bundle.route.route_data.clone(),
        bundle.limits.canonical_bytes.clone(),
        bundle.promotion_manifest.clone(),
    ));
    cases.push((
        "damage-convergence-archive-binding",
        bundle.projected_policies.profile_policy.clone(),
        replace_once(
            &bundle.projected_policies.damage_policy,
            b"precursor_archive_manifest_sha256 = \"d1ece9d02628a624d58837b9a1c1994dfb521e96303df66758c95880b2d378e4\"",
            b"precursor_archive_manifest_sha256 = \"0000000000000000000000000000000000000000000000000000000000000000\"",
        ),
        bundle.route.route_data.clone(),
        bundle.limits.canonical_bytes.clone(),
        bundle.promotion_manifest.clone(),
    ));
    cases.push((
        "limits-stale-profile-hash",
        bundle.projected_policies.profile_policy.clone(),
        bundle.projected_policies.damage_policy.clone(),
        bundle.route.route_data.clone(),
        replace_once(
            &bundle.limits.canonical_bytes,
            bundle.projected_policies.profile_policy_sha256.as_bytes(),
            b"0000000000000000000000000000000000000000000000000000000000000000",
        ),
        bundle.promotion_manifest.clone(),
    ));
    cases.push((
        "promotion-status",
        bundle.projected_policies.profile_policy.clone(),
        bundle.projected_policies.damage_policy.clone(),
        bundle.route.route_data.clone(),
        bundle.limits.canonical_bytes.clone(),
        replace_once(
            &bundle.promotion_manifest,
            b"\nstatus = \"pre-result-frozen\"",
            b"\nstatus = \"blocked\"",
        ),
    ));
    cases.push((
        "promotion-authorization",
        bundle.projected_policies.profile_policy.clone(),
        bundle.projected_policies.damage_policy.clone(),
        bundle.route.route_data.clone(),
        bundle.limits.canonical_bytes.clone(),
        replace_once(
            &bundle.promotion_manifest,
            b"\ndamage_observation_authorized = true",
            b"\ndamage_observation_authorized = false",
        ),
    ));
    cases.push((
        "promotion-stale-draft-owner-hash",
        bundle.projected_policies.profile_policy.clone(),
        bundle.projected_policies.damage_policy.clone(),
        bundle.route.route_data.clone(),
        bundle.limits.canonical_bytes.clone(),
        replace_once(
            &bundle.promotion_manifest,
            bundle.projected_policies.damage_policy_sha256.as_bytes(),
            b"0000000000000000000000000000000000000000000000000000000000000000",
        ),
    ));
    cases.push((
        "promotion-route-receipt",
        bundle.projected_policies.profile_policy.clone(),
        bundle.projected_policies.damage_policy.clone(),
        bundle.route.route_data.clone(),
        bundle.limits.canonical_bytes.clone(),
        replace_once(
            &bundle.promotion_manifest,
            bundle.route.rust_reproduction_sha256.as_bytes(),
            b"0000000000000000000000000000000000000000000000000000000000000000",
        ),
    ));
    cases.push((
        "promotion-limits-receipt",
        bundle.projected_policies.profile_policy.clone(),
        bundle.projected_policies.damage_policy.clone(),
        bundle.route.route_data.clone(),
        bundle.limits.canonical_bytes.clone(),
        replace_once(
            &bundle.promotion_manifest,
            bundle.limits.rust_reproduction_sha256.as_bytes(),
            b"0000000000000000000000000000000000000000000000000000000000000000",
        ),
    ));
    for (name, profile, damage, route, limits, promotion) in cases {
        assert!(
            admit_r3_promoted_owner_bundle(
                bootstrap, &profile, &damage, &route, &limits, &promotion, fixture, &compiled,
                curriculum,
            )
            .is_err(),
            "named mutant admitted: {name}"
        );
    }
}

#[test]
fn route_data_generated_schema_and_all_malformed_prefixes_fail_closed() {
    let owner = gb_bootstrap::carrier::generate_r3_route_owner().unwrap();
    gb_bootstrap::carrier::admit_r3_route_data(&owner.route_data).unwrap();
    let clean = validate_canonical_manifest(&owner.route_data).unwrap();
    let mut mutants = Vec::new();
    let mut value = clean.clone();
    route_generated(&mut value).remove("recipient_package_bytes");
    mutants.push(("missing-generated-key", value));
    let mut value = clean.clone();
    route_generated(&mut value).insert("unknown".to_owned(), ManifestValue::Bool(true));
    mutants.push(("unknown-generated-key", value));
    let mut value = clean.clone();
    let ManifestValue::Array(items) = route_generated(&mut value)
        .get_mut("route_prefix_cells_by_sector")
        .unwrap()
    else {
        panic!("sector array")
    };
    items.pop();
    mutants.push(("short-sector-array", value));
    let mut value = clean.clone();
    *route_generated(&mut value)
        .get_mut("recipient_package_bytes")
        .unwrap() = ManifestValue::U64(0);
    mutants.push(("zero-numeric", value));
    for key in [
        "reproduction_projection_sha256",
        "python_reproduction_sha256",
        "rust_reproduction_sha256",
    ] {
        let mut value = clean.clone();
        let ManifestValue::String(text) = route_generated(&mut value).get_mut(key).unwrap() else {
            panic!("digest string")
        };
        text.replace_range(..1, if text.starts_with('0') { "1" } else { "0" });
        mutants.push((key, value));
    }
    let mut value = clean.clone();
    let python = route_generated(&mut value)["python_reproduction_sha256"].clone();
    route_generated(&mut value).insert("rust_reproduction_sha256".to_owned(), python);
    mutants.push(("equal-receipts", value));
    for (name, value) in mutants {
        let raw = serialize_manifest(&value).unwrap();
        assert!(
            gb_bootstrap::carrier::admit_r3_route_data(&raw).is_err(),
            "route owner mutant admitted: {name}"
        );
    }
    for row in &owner.malformed_cases {
        assert!(
            gb_bootstrap::carrier::admit_r3_route_prefix(&row.mutant, 0, &owner).is_err(),
            "malformed prefix admitted: {}",
            row.case_id
        );
    }
}
