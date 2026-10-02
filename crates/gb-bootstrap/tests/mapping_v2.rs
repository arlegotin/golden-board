use gb_bootstrap::candidate_recipe::r3_slot_multiplier_table;
use gb_bootstrap::carrier::{CarrierError, HierarchicalMap};
use gb_bootstrap::mapping_v2;

#[test]
fn fixed_projection_uses_profile8_offset_without_changing_frozen_v7() {
    let old = HierarchicalMap::derive(1952, 128).unwrap();
    let map = mapping_v2::derive(1952, 128).unwrap();
    assert_eq!(
        (map.side(), map.shell_width(), map.interior_side()),
        (1952, 128, 1696)
    );
    assert_eq!((map.population(), map.unit_slot_count()), (2_876_416, 1664));
    assert_eq!(
        (map.slot_multiplier(), map.inverse_slot_multiplier()),
        (15, 111)
    );
    assert_eq!(
        (map.cell_multiplier(), map.inverse_cell_multiplier()),
        (3391, 2_873_023)
    );
    assert_eq!(map.cell_offset(), 356_920);
    assert_eq!(map.fixed_pad_cells(), 1024);
    assert_eq!(old.cell_offset, 316_417);
    for (unit, bit) in [
        (1, 0),
        (1, 1727),
        (111, 0),
        (112, 1727),
        (1664, 0),
        (1664, 1727),
    ] {
        let physical = map.forward(unit, bit).unwrap();
        assert_eq!(
            physical,
            (old.forward_unit_bit(unit - 1, bit).unwrap() + 40_503) % map.population()
        );
        assert_eq!(map.inverse(physical).unwrap(), (0, unit, bit));
    }
    assert_eq!(HierarchicalMap::derive(1952, 128).unwrap(), old);
}

#[test]
fn current_geometry_composes_one_based_units_slot_wrap_and_cell_affine_map() {
    let table = r3_slot_multiplier_table();
    for (side, width) in [(1952, 128), (2048, 112)] {
        let map = mapping_v2::derive(side, width).unwrap();
        let interior = u64::from(side - 2 * width);
        let population = interior * interior;
        let slots = population / 1728;
        let multiplier = u64::from(table[interior as usize / 8]);
        assert_eq!(map.population(), population);
        assert_eq!(map.unit_slot_count(), slots);
        assert_eq!(map.slot_multiplier(), multiplier);
        assert_eq!(
            map.cell_offset(),
            (8 * 40503 + u64::from(width) * 257) % population
        );
        for unit in 1..=slots {
            for bit in [0u16, 1, 1727] {
                let slot = multiplier * (unit - 1) % slots;
                let logical = 1728 * slot + u64::from(bit);
                let expected = ((2 * interior - 1) * logical + 8 * 40503 + u64::from(width) * 257)
                    % population;
                assert_eq!(map.forward(unit, bit).unwrap(), expected);
                assert_eq!(map.inverse(expected).unwrap(), (0, unit, bit));
            }
        }
        // Every fixed-pad cell, including the first and last logical cells,
        // produces exactly the pad tuple rather than a wrapped unit ID.
        for logical in slots * 1728..population {
            let physical = ((2 * interior - 1) * logical + map.cell_offset()) % population;
            assert_eq!(map.inverse(physical).unwrap(), (1, 0, 0));
        }
    }
}

#[test]
fn exact_table_domain_and_zero_entries_determine_mapping_admission() {
    let table = r3_slot_multiplier_table();
    for interior in (48u16..=2032).step_by(8) {
        let expected = u64::from(table[usize::from(interior / 8)]);
        let result = mapping_v2::derive(interior + 16, 8);
        if expected == 0 {
            assert_eq!(result.unwrap_err(), CarrierError::Geometry);
        } else {
            let map = result.unwrap();
            assert_eq!(map.slot_multiplier(), expected);
            assert_eq!(
                map.slot_multiplier() * map.inverse_slot_multiplier() % map.unit_slot_count(),
                1
            );
        }
    }
}

#[test]
fn geometry_and_every_public_index_domain_reject_instead_of_wrapping() {
    for (side, width) in [
        (0, 8),
        (63, 8),
        (2047, 112),
        (2056, 112),
        (u16::MAX, 8),
        (2048, 0),
        (2048, 7),
        (2048, 111),
        (2048, 129),
        (2048, u16::MAX),
        (64, 32),
        (64, 40),
        (64, 8),
        (64, 24),
    ] {
        assert_eq!(
            mapping_v2::derive(side, width).unwrap_err(),
            CarrierError::Geometry
        );
    }
    let map = mapping_v2::derive(2048, 112).unwrap();
    for unit in [0, map.unit_slot_count() + 1, u64::MAX] {
        assert_eq!(map.forward(unit, 0).unwrap_err(), CarrierError::Geometry);
    }
    for bit in [1728, u16::MAX] {
        assert_eq!(map.forward(1, bit).unwrap_err(), CarrierError::Geometry);
    }
    for physical in [map.population(), u64::MAX] {
        assert_eq!(map.inverse(physical).unwrap_err(), CarrierError::Geometry);
    }
    assert!(map.inverse(0).is_ok());
    assert!(map.inverse(map.population() - 1).is_ok());
}

#[test]
fn every_physical_cell_has_exactly_one_unit_bit_or_pad_classification() {
    let map = mapping_v2::derive(1952, 128).unwrap();
    let mut pad_count = 0;
    for physical in 0..map.population() {
        let (kind, unit, bit) = map.inverse(physical).unwrap();
        match kind {
            0 => {
                assert!((1..=map.unit_slot_count()).contains(&unit));
                assert!(bit < 1728);
                assert_eq!(map.forward(unit, bit).unwrap(), physical);
            }
            1 => {
                assert_eq!((unit, bit), (0, 0));
                pad_count += 1;
            }
            other => panic!("unexpected classification {other}"),
        }
    }
    assert_eq!(pad_count, map.fixed_pad_cells());
}
