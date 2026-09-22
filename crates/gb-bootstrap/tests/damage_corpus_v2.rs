use gb_bootstrap::damage::ObsUnits;
use gb_bootstrap::damage_corpus_v2::DamageCorpusV2;
use std::sync::OnceLock;

fn fixture() -> &'static DamageCorpusV2 {
    static VALUE: OnceLock<DamageCorpusV2> = OnceLock::new();
    VALUE.get_or_init(|| {
        let slice = gb_slice::compile_slice_v1(
            include_bytes!("../../../studies/m2/slice-v1.json"),
            gb_slice::SliceInputs {
                declaration: include_bytes!("../../../studies/m2/slice-v0.json"),
                content_fixture: include_bytes!("../../../conformance/content-v0.json"),
                chess_fixture: include_bytes!("../../../conformance/chess-v0.json"),
                game_set: include_bytes!("../../../reports/game-set-v0.bin"),
                content_spec: include_bytes!("../../../spec/content-v0.md"),
                constants: include_bytes!("../../../spec/constants-v0.toml"),
                curriculum: include_bytes!("../../../spec/curriculum-v0.toml"),
            },
        )
        .unwrap();
        let carrier = gb_bootstrap::carrier_v2::build_carrier(&slice).unwrap();
        DamageCorpusV2::new(
            &slice,
            &carrier,
            include_bytes!("../../../spec/route-data-v0.json"),
        )
        .unwrap()
    })
}

#[test]
fn accidental_inventory_is_separate_from_checked_boundary_reauthoring() {
    let corpus = fixture();
    assert_eq!(corpus.case_count("D7").unwrap(), 415);
    assert_eq!(corpus.case_count("B0").unwrap(), 21);
    assert_eq!(corpus.accidental_case_count(), 10465);
    for family in ["D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "B0"] {
        assert!(
            corpus
                .case(family, corpus.case_count(family).unwrap())
                .is_err()
        );
    }
    assert!(corpus.case("D8", 0).is_err());
    assert!(corpus.case("D7", u64::MAX).is_err());
}

#[test]
fn lazy_unit_cases_preserve_ids_and_new_foreign7_targets_exactly_five_lanes() {
    let corpus = fixture();
    let clean = ObsUnits::parse(corpus.case("D5", 0).unwrap().bytes()).unwrap();
    let missing = ObsUnits::parse(corpus.case("D4", 0).unwrap().bytes()).unwrap();
    assert_eq!(missing.entries, clean.entries[1..]);
    let foreign = corpus.case("D7", 414).unwrap();
    assert_eq!(foreign.operator(), "foreign-profile7-bootstrap");
    let foreign = ObsUnits::parse(foreign.bytes()).unwrap();
    assert_eq!(foreign.entries.len(), clean.entries.len());
    assert_eq!(foreign.entries[5..], clean.entries[5..]);
    for (a, b) in foreign.entries[..5].iter().zip(&clean.entries[..5]) {
        assert_eq!(a.physical_unit_id, b.physical_unit_id);
        assert_ne!(a.bytes, b.bytes);
    }
}

#[test]
fn every_new_case_exists_and_has_canonical_input_only_identity() {
    use gb_foundation::{ManifestValue as V, serialize_manifest, validate_canonical_manifest};
    use sha2::{Digest, Sha256};
    let corpus = fixture();
    for (family, ordinals) in [
        ("D7", (408..415).collect::<Vec<_>>()),
        ("B0", (0..21).collect()),
    ] {
        for ordinal in ordinals {
            let case = corpus
                .case(family, ordinal)
                .unwrap_or_else(|error| panic!("{family}-{ordinal}: {error:?}"));
            let identity = validate_canonical_manifest(case.identity_bytes()).unwrap();
            assert_eq!(
                serialize_manifest(&identity).unwrap(),
                case.identity_bytes()
            );
            let V::Object(identity) = identity else {
                panic!("identity")
            };
            assert_eq!(identity.len(), 9);
            assert_eq!(
                identity["observation_sha256"],
                V::String(format!("{:x}", Sha256::digest(case.bytes())))
            );
            assert_eq!(
                identity["case_id"],
                V::String(format!("{family}-{ordinal:06}"))
            );
            assert!(!identity.contains_key("result"));
        }
    }
}

fn common(entry: &gb_bootstrap::damage::UnitEntry, profile: u16) -> gb_bootstrap::CommonBlock {
    let decoded = gb_bootstrap::candidate::decode_eh_unit(
        &gb_bootstrap::candidate::EhObservation {
            encoded: entry.bytes.clone().try_into().unwrap(),
            erasures: vec![],
        },
        profile,
    )
    .unwrap();
    gb_bootstrap::decode_common_block(&decoded.common, profile).unwrap()
}

#[test]
fn checked_boundaries_reauthor_exactly_one_section_and_preserve_group_shapes() {
    use std::collections::BTreeMap;
    let corpus = fixture();
    let clean = ObsUnits::parse(corpus.case("D5", 0).unwrap().bytes()).unwrap();
    let clean_common: Vec<_> = clean.entries.iter().map(|entry| common(entry, 8)).collect();
    for ordinal in 0..20 {
        let observation = corpus.case("B0", ordinal).unwrap();
        let changed = ObsUnits::parse(observation.bytes()).unwrap();
        assert_eq!(clean.entries.len(), changed.entries.len());
        let mut target = None;
        let mut fragments = BTreeMap::new();
        let mut changed_count = 0;
        for ((old, actual), before) in clean
            .entries
            .iter()
            .zip(&changed.entries)
            .zip(&clean_common)
        {
            assert_eq!(old.physical_unit_id, actual.physical_unit_id);
            if old.bytes == actual.bytes {
                continue;
            }
            changed_count += 1;
            let after = common(actual, 8);
            assert_eq!(after.section_id, *target.get_or_insert(after.section_id));
            assert_eq!(
                (
                    after.fragment_index,
                    after.fragment_count,
                    after.section_envelope_length,
                    after.payload.len()
                ),
                (
                    before.fragment_index,
                    before.fragment_count,
                    before.section_envelope_length,
                    before.payload.len()
                )
            );
        }
        let target = target.unwrap();
        // Every lane of the target section remains valid local transport,
        // including fragments whose payload bytes did not change.
        for (actual, before) in changed
            .entries
            .iter()
            .zip(&clean_common)
            .filter(|(_, b)| b.section_id == target)
        {
            let after = common(actual, 8);
            assert_eq!(before.section_id, after.section_id);
            if let Some(previous) = fragments.insert(after.fragment_index, after.payload.clone()) {
                assert_eq!(previous, after.payload)
            }
        }
        assert!(changed_count > 0);
        let envelope: Vec<u8> = fragments.into_values().flatten().collect();
        let section = gb_bootstrap::decode_section(&envelope).unwrap();
        if ordinal < 14 {
            assert_eq!(target, if ordinal < 7 { 16 } else { 200 });
            assert!(
                gb_bootstrap::body_codec_v1::decode_body(section.section_version, &section.payload)
                    .is_err()
            );
        } else {
            assert_eq!(target, if ordinal < 17 { 2 } else { 3 });
            let original = clean_common
                .iter()
                .filter(|b| b.section_id == target)
                .fold(BTreeMap::new(), |mut m, b| {
                    m.insert(b.fragment_index, b.payload.clone());
                    m
                })
                .into_values()
                .flatten()
                .collect::<Vec<_>>();
            let original = gb_bootstrap::decode_section(&original).unwrap();
            let len = section.payload.len();
            let k = (ordinal - 14) % 3;
            let mut expected = original.payload;
            if k < 2 {
                let at = if k == 0 { len - 4 } else { len - 2 };
                expected[at..at + 2].fill(0);
            } else {
                let v = u32::from_be_bytes(expected[8..12].try_into().unwrap()) + 1;
                expected[8..12].copy_from_slice(&v.to_be_bytes());
            }
            assert_eq!(section.payload, expected);
        }
    }
}

fn unpack(raw: &[u8]) -> Vec<u8> {
    raw[4..]
        .iter()
        .flat_map(|b| (0..8).rev().map(move |n| (b >> n) & 1))
        .collect()
}
fn extract_prefix(bits: &[u8], side: usize, width: usize, sector: u8) -> Vec<u8> {
    let byte = |index: usize| {
        let mut value = 0;
        for n in 0..8 {
            let (row, col) =
                gb_bootstrap::sector_cell_at(side, width, sector, index * 8 + n).unwrap();
            value = (value << 1) | bits[row * side + col];
        }
        value
    };
    let cells = u32::from_be_bytes([byte(56), byte(57), byte(58), byte(59)]) as usize;
    (0..cells / 8).map(byte).collect()
}
fn package(raw: &[u8]) -> usize {
    let mut at = 64;
    while at < raw.len() {
        if raw[at + 1] == 5 {
            return at + 8;
        }
        at += 8 + u32::from_be_bytes(raw[at + 4..at + 8].try_into().unwrap()) as usize;
    }
    panic!("package")
}

#[test]
fn compact_mutants_change_exact_fields_in_all_four_complete_prefixes() {
    let corpus = fixture();
    let clean = unpack(corpus.case("D0", 0).unwrap().bytes());
    let side = 2048;
    for n in 0..6 {
        let actual = unpack(corpus.case("D7", 408 + n).unwrap().bytes());
        let mut expected = clean.clone();
        for sector in 0..4 {
            let mut prefix = extract_prefix(&clean, side, 112, sector);
            let p = package(&prefix);
            let mut recipe = p + 64;
            for _ in 0..u16::from_be_bytes(prefix[p + 18..p + 20].try_into().unwrap()) {
                recipe += 16
                    + u32::from_be_bytes(prefix[recipe + 12..recipe + 16].try_into().unwrap())
                        as usize;
            }
            match n {
                0 => prefix[p + 8..p + 10].fill(0),
                1 => prefix[p + 48] = 1,
                2 => {
                    let old = u32::from_be_bytes(prefix[p + 32..p + 36].try_into().unwrap());
                    prefix[p + 32..p + 36].copy_from_slice(&(old - 1).to_be_bytes());
                }
                3 | 4 => {
                    let descriptors = usize::from(u16::from_be_bytes(
                        prefix[recipe + 4..recipe + 6].try_into().unwrap(),
                    )) + usize::from(u16::from_be_bytes(
                        prefix[recipe + 6..recipe + 8].try_into().unwrap(),
                    ));
                    prefix[recipe + 32 + 12 * descriptors + usize::from(n == 4)] = 0;
                }
                5 => {
                    let old =
                        u64::from_be_bytes(prefix[recipe + 16..recipe + 24].try_into().unwrap());
                    prefix[recipe + 16..recipe + 24].copy_from_slice(&(old + 1).to_be_bytes());
                }
                _ => unreachable!(),
            }
            for bit in 0..prefix.len() * 8 {
                let (row, col) = gb_bootstrap::sector_cell_at(side, 112, sector, bit).unwrap();
                expected[row * side + col] = (prefix[bit / 8] >> (7 - bit % 8)) & 1;
            }
            assert_eq!(extract_prefix(&actual, side, 112, sector), prefix);
            let length = u32::from_be_bytes(prefix[p - 4..p].try_into().unwrap()) as usize;
            assert!(
                gb_bootstrap::recipe_wire_v1::decode_recipe_package_v1(&prefix[p..p + length], 8)
                    .is_err()
            );
        }
        assert_eq!(actual, expected);
        assert_ne!(actual, clean);
    }
}

#[test]
fn donor_conflict_uses_complete_source_built_prefix_at_width128() {
    let corpus = fixture();
    let clean = unpack(corpus.case("D0", 0).unwrap().bytes());
    let actual = unpack(corpus.case("D7", 10).unwrap().bytes());
    let side = 2048;
    let package = gb_bootstrap::candidate_recipe::build_eh_recipe_package(3).unwrap();
    let donor = gb_bootstrap::carrier::build_route_images(
        include_bytes!("../../../spec/route-data-v0.json"),
        3,
        &package,
        side,
        128,
    )
    .unwrap();
    let count = donor.sectors[0].route_prefix_cells as usize;
    assert_eq!(count / 8, 27714);
    assert!(count > 112 * (usize::from(side) - 112));
    let mut expected = clean.clone();
    let mut interior_changes = 0;
    for bit in 0..count {
        let (row, col) = gb_bootstrap::sector_cell_at(usize::from(side), 128, 0, bit).unwrap();
        let flat = row * usize::from(side) + col;
        expected[flat] = donor.sectors[0].bits[bit];
        if (112..usize::from(side) - 112).contains(&row)
            && (112..usize::from(side) - 112).contains(&col)
            && expected[flat] != clean[flat]
        {
            interior_changes += 1;
        }
    }
    assert!(interior_changes > 0);
    assert_eq!(actual, expected);
}

#[test]
fn inherited_positions_and_all_coordinate_strata_remain_present() {
    let corpus = fixture();
    for ordinal in [
        0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16, 17, 272, 273, 304, 305, 336, 337,
        368, 369, 400, 401, 402, 403, 404, 405, 406, 407,
    ] {
        assert!(!corpus.case("D7", ordinal).unwrap().bytes().is_empty());
    }
    for ordinal in [0, 32, 64, 96] {
        let case = corpus.case("D3", ordinal).unwrap();
        assert_eq!(case.channel(), "OBS_MATRIX");
    }
    assert_eq!(corpus.case("D6", 7699).unwrap().channel(), "OBS_MATRIX");
}

#[test]
fn undercoverage_reauthors_only_inventory_and_preserves_observed_unit_count() {
    use std::collections::BTreeMap;
    let corpus = fixture();
    let clean_bits = unpack(corpus.case("D0", 0).unwrap().bytes());
    let actual = unpack(corpus.case("B0", 20).unwrap().bytes());
    let clean = ObsUnits::parse(corpus.case("D5", 0).unwrap().bytes()).unwrap();
    let mapping = gb_bootstrap::mapping_v2::derive(2048, 112).unwrap();
    let mut inventory = BTreeMap::new();
    let mut before = BTreeMap::new();
    let mut expected = clean_bits.clone();
    for entry in &clean.entries {
        let block = common(entry, 8);
        if block.section_id != 1 {
            continue;
        }
        let mut encoded = vec![0; 216];
        for bit in 0..1728u16 {
            let physical = mapping
                .forward(u64::from(entry.physical_unit_id), bit)
                .unwrap();
            let row = physical as usize / 1824 + 112;
            let col = physical as usize % 1824 + 112;
            let flat = row * 2048 + col;
            encoded[usize::from(bit) / 8] |= actual[flat] << (7 - bit % 8);
            expected[flat] = actual[flat];
        }
        let changed = common(
            &gb_bootstrap::damage::UnitEntry {
                physical_unit_id: entry.physical_unit_id,
                bytes: encoded,
            },
            8,
        );
        assert_eq!(
            (
                block.fragment_index,
                block.fragment_count,
                block.section_envelope_length
            ),
            (
                changed.fragment_index,
                changed.fragment_count,
                changed.section_envelope_length
            )
        );
        if let Some(old) = inventory.insert(changed.fragment_index, changed.payload.clone()) {
            assert_eq!(old, changed.payload)
        }
        before.insert(block.fragment_index, block.payload);
    }
    assert_eq!(actual, expected);
    assert_ne!(actual, clean_bits);
    let decode = |blocks: BTreeMap<u16, Vec<u8>>| {
        gb_bootstrap::bootstrap_v2::decode_inventory(
            &gb_bootstrap::decode_section(&blocks.into_values().flatten().collect::<Vec<_>>())
                .unwrap()
                .payload,
        )
        .unwrap()
    };
    let old = decode(before);
    let new = decode(inventory);
    let mut expected = old.clone();
    let target = expected
        .entries
        .iter_mut()
        .filter(|entry| entry.section_type == gb_bootstrap::SECTION_LOAD_PROBE)
        .min_by_key(|entry| entry.section_id)
        .unwrap();
    target.logical_payload_length -= 157;
    assert_eq!(new, expected);
    assert_eq!(clean.entries.len(), 1925);
}

#[test]
fn square_parameter_is_observed_coordinate_of_actual_first_erased_cell() {
    use gb_foundation::{ManifestValue as V, validate_canonical_manifest};
    let case = fixture().case("D2", 0).unwrap();
    let matrix = gb_bootstrap::damage::ObsMatrix::parse(case.bytes()).unwrap();
    let first = matrix.values.iter().position(|value| *value == 2).unwrap();
    let V::Object(identity) = validate_canonical_manifest(case.identity_bytes()).unwrap() else {
        panic!("object")
    };
    let V::Array(parameters) = &identity["parameter_projection"] else {
        panic!("array")
    };
    let top_left = parameters
        .iter()
        .find_map(|row| {
            let V::Object(row) = row else { return None };
            (row["id"] == V::String("top_left".into())).then_some(&row["value"])
        })
        .unwrap();
    assert_eq!(
        *top_left,
        V::Array(vec![V::Array(vec![
            V::U64((first / matrix.side) as u64),
            V::U64((first % matrix.side) as u64)
        ])])
    );
}
