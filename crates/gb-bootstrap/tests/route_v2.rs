use gb_bootstrap::carrier::{CarrierError, ShellOwner};
use gb_bootstrap::route_v2::{build_route_images, build_route_prefixes};
use gb_bootstrap::teaching_recipe_v2::build_teaching_recipe_package;

fn slice() -> gb_slice::SliceCompilation {
    gb_slice::compile_slice_v1(
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
    .unwrap()
}

fn u16_at(raw: &[u8], offset: usize) -> u16 {
    u16::from_be_bytes(raw[offset..offset + 2].try_into().unwrap())
}

fn u32_at(raw: &[u8], offset: usize) -> usize {
    u32::from_be_bytes(raw[offset..offset + 4].try_into().unwrap()) as usize
}

fn records(raw: &[u8]) -> Vec<(u8, u8, u16, &[u8])> {
    let mut cursor = 64;
    let mut rows = Vec::new();
    while cursor < raw.len() {
        let end = cursor + 8 + u32_at(raw, cursor + 4);
        rows.push((
            raw[cursor],
            raw[cursor + 1],
            u16_at(raw, cursor + 2),
            &raw[cursor + 8..end],
        ));
        cursor = end;
    }
    assert_eq!(cursor, raw.len());
    rows
}

#[test]
fn complete_routes_have_exact_v2_framing_order_and_one_complete_package() {
    let compiled = slice();
    let prefixes = build_route_prefixes(&compiled).unwrap();
    let package = build_teaching_recipe_package().unwrap();
    for (sector, prefix) in prefixes.iter().enumerate() {
        assert_eq!(&prefix[32..40], b"GBROUTE\0");
        assert_eq!(u16_at(prefix, 40), 2);
        assert_eq!(&prefix[42..44], &[sector as u8; 2]);
        assert_eq!(u16_at(prefix, 44), 8);
        assert_eq!(u16_at(prefix, 46), 48);
        assert_eq!(u32_at(prefix, 48), prefix.len() - 64);
        assert_eq!(u32_at(prefix, 52), package.len());
        assert_eq!(u32_at(prefix, 56), prefix.len() * 8);
        assert_eq!(&prefix[60..64], &[1, 0, 0, 0]);
        let rows = records(prefix);
        assert_eq!(rows.len(), 48);
        assert!(!rows.iter().any(|row| row.1 == 4));
        let mut expected_ids = Vec::new();
        for fact in 1..=12 {
            expected_ids.extend([fact * 100 + 1, fact * 100 + 2, fact * 100 + 3]);
            if fact == 6 {
                expected_ids.extend(610..=615);
            }
            if fact == 10 {
                expected_ids.push(1004);
            }
            if fact == 12 {
                expected_ids.extend([1210, 1211]);
            }
        }
        expected_ids.extend([6001, 7001, 7002]);
        assert_eq!(
            rows.iter().map(|row| row.2).collect::<Vec<_>>(),
            expected_ids
                .iter()
                .map(|id| id + sector as u16 * 10000)
                .collect::<Vec<_>>()
        );
        assert_eq!(
            rows[45],
            (5, 5, sector as u16 * 10000 + 6001, package.as_slice())
        );
        assert_eq!(rows[46].3, [0, 0, 0, 1]);
        assert!(rows[47].3.is_empty());
    }
    assert_eq!(build_route_prefixes(&compiled).unwrap(), prefixes);
}

#[test]
fn definition_descriptors_and_all_example_lengths_bind_their_actual_bytes() {
    let prefixes = build_route_prefixes(&slice()).unwrap();
    let expected_lengths = [16, 64, 306, 296, 236, 228, 636, 544, 464, 478, 314];
    for prefix in &prefixes {
        for (_, kind, _, payload) in records(prefix) {
            if kind == 1 {
                let fact = u16_at(payload, 0);
                assert_eq!(u16_at(payload, 2), fact);
                assert_eq!(&payload[4..6], &[3, 0]);
                assert_eq!(u32_at(payload, 6), payload.len() - 14);
                assert_eq!(u32_at(payload, 10), 1);
                if fact < 12 {
                    assert_eq!(payload.len() - 14, expected_lengths[usize::from(fact - 1)]);
                }
            } else if kind == 2 || kind == 3 {
                let input_length = u32_at(payload, 4);
                let output_length = u32_at(payload, 8);
                assert_eq!(payload.len(), 12 + input_length + output_length);
                assert!(output_length >= 2);
                if u16_at(payload, 12 + input_length) != 0 {
                    assert_eq!(output_length, 2);
                }
            }
        }
    }
    for sector in 1..4 {
        let rows = records(&prefixes[sector]);
        let first = records(&prefixes[0]);
        for (row, original) in rows.iter().zip(first) {
            if row.1 == 1 || matches!(row.2 % 10000, 602 | 603 | 610..=615 | 1210 | 1211) {
                assert_eq!(row.3, original.3);
            }
        }
    }
}

#[test]
fn complete_construction_examples_invoke_the_same_kernel_and_physical_identity() {
    use gb_bootstrap::recipe_wire_v2::decode_recipe_package_v2;
    use gb_bootstrap::recovery_recipe_v2::evaluate_serialized_recovery_native;
    let package = decode_recipe_package_v2(&build_teaching_recipe_package().unwrap(), 8).unwrap();
    for prefix in build_route_prefixes(&slice()).unwrap() {
        let rows = records(&prefix);
        let definition = &rows.iter().find(|r| r.2 % 10000 == 1001).unwrap().3[14..];
        assert_eq!(definition.len(), 478);
        assert_eq!(
            &definition[..22],
            &[
                0, 123, 0, 124, 0, 120, 0, 125, 0, 126, 0, 127, 0, 24, 0, 25, 0, 26, 0, 27, 8, 57
            ]
        );
        for (case, row) in definition[22..].chunks_exact(57).enumerate() {
            assert_eq!(row[4] as usize, case);
            assert_eq!(u32_at(row, 0), if case == 7 { 11 } else { 6 });
            assert_eq!(
                evaluate_serialized_recovery_native(&package, 126, &row[..5]).unwrap(),
                row[5..]
            );
        }
        for (id, case) in [(1002, 4), (1003, 6), (1004, 7)] {
            let example = rows.iter().find(|r| r.2 % 10000 == id).unwrap().3;
            assert_eq!(u16_at(example, 2), 126);
            assert_eq!(
                &example[12..],
                &definition[22 + 57 * case..22 + 57 * (case + 1)]
            );
        }
    }
}

#[test]
fn complete_images_charge_every_cell_and_reject_geometry_and_insufficient_fit() {
    let compiled = slice();
    let prefixes = build_route_prefixes(&compiled).unwrap();
    let images = build_route_images(&compiled, 2048, 112).unwrap();
    assert_eq!(prefixes[0].len(), 25424);
    assert_eq!(
        build_route_images(&compiled, 2008, 112).unwrap_err(),
        CarrierError::RouteFit
    );
    let total: usize = prefixes.iter().map(|prefix| prefix.len() * 8).sum();
    assert_eq!(images.instruction_cells, total as u64);
    assert_eq!(images.headroom_cells, total.div_ceil(20).max(1024) as u64);
    assert_eq!(
        images
            .sectors
            .iter()
            .map(|row| row.headroom_cells)
            .sum::<u64>(),
        images.headroom_cells
    );
    for (sector, image) in images.sectors.iter().enumerate() {
        assert_eq!(image.bits.len(), 112 * (2048 - 112));
        assert!(image.bits.iter().all(|bit| *bit <= 1));
        assert_eq!(
            image.route_prefix_cells,
            (prefixes[sector].len() * 8) as u64
        );
        let packed: Vec<u8> = image.bits[..prefixes[sector].len() * 8]
            .chunks_exact(8)
            .map(|bits| bits.iter().fold(0, |byte, bit| byte * 2 + bit))
            .collect();
        assert_eq!(packed, prefixes[sector]);
        let mut next = 0;
        for span in &image.spans {
            assert_eq!(span.first_cell, next);
            next += span.cell_count;
        }
        assert_eq!(next as usize, image.bits.len());
        assert_eq!(
            image
                .spans
                .iter()
                .filter(|span| span.owner == ShellOwner::Headroom)
                .map(|span| span.cell_count)
                .sum::<u64>(),
            image.headroom_cells
        );
    }
    for (side, width) in [(63, 8), (2047, 128), (2048, 111), (2048, 129), (64, 32)] {
        assert_eq!(
            build_route_images(&compiled, side, width).unwrap_err(),
            CarrierError::Geometry
        );
    }
    assert_eq!(
        build_route_images(&compiled, 64, 8).unwrap_err(),
        CarrierError::RouteFit
    );
}

#[test]
fn position_suffix_is_source_extracted_and_distinguishes_tag_and_wire_admission() {
    let value = gb_bootstrap::route_v2::build_position_teaching_v2(&slice()).unwrap();
    let raw = value.value();
    assert_eq!(raw.len(), 408);
    assert_eq!(u16_at(raw, 0), 2);
    assert_eq!(&raw[146..149], &[1, 15, 21]);
    assert_eq!(raw[161], 1);
    assert_eq!(&raw[162..229], &raw[229..296]);
    assert_eq!(u16_at(raw, 314), 12);
    for (index, row) in raw[316..388].chunks_exact(6).enumerate() {
        assert_eq!(row[5], u8::from(matches!(index, 0..=4 | 8 | 9)));
    }
    assert_eq!(&raw[388..394], &[0, 1, 2, 77, 0, 69]);
}
