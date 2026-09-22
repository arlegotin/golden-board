use gb_bootstrap::carrier_v2::{
    build_carrier, derive_capacity, recover_clean_matrix, verify_clean_carrier,
};

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

#[test]
fn capacity_preserves_uncompressed_authoring_promise_and_all_actual_bodies() {
    let compiled = slice();
    let capacity = derive_capacity(&compiled).unwrap();
    assert_eq!(capacity.future_authoring_bytes(), 105277);
    assert_eq!(capacity.reserve_bytes(), 9353);
    assert_eq!(capacity.body_count(), 78);
    assert_eq!(capacity.capacity_probe_count(), 53);
    assert!(capacity.stored_body_bytes() < capacity.uncompressed_body_bytes());
}

#[test]
fn independent_carrier_search_and_matrix_recovery_close_every_owned_cell() {
    let compiled = slice();
    let carrier = build_carrier(&compiled).unwrap();
    assert_eq!(
        (carrier.side(), carrier.shell_width(), carrier.unit_count()),
        (2048, 112, 1925)
    );
    assert_eq!(carrier.packed_bytes().len(), 4 + 2048 * 2048 / 8);
    assert!(carrier.packed_bytes().len() - 4 <= 512 * 1024);
    assert_eq!(carrier.search_ledger().last().unwrap().accepted, true);
    assert!(
        carrier.search_ledger()[..carrier.search_ledger().len() - 1]
            .iter()
            .all(|row| !row.accepted)
    );
    let recovered = recover_clean_matrix(carrier.packed_bytes(), carrier.shell_width()).unwrap();
    assert_eq!(
        recovered.required_bytes.as_deref(),
        Some(compiled.required_stream())
    );
    assert_eq!(recovered.all_bytes.as_deref(), Some(compiled.all_stream()));
    verify_clean_carrier(&compiled, carrier.packed_bytes(), carrier.shell_width()).unwrap();
    let mut changed = carrier.packed_bytes().to_vec();
    changed[4] ^= 0x80;
    assert!(verify_clean_carrier(&compiled, &changed, carrier.shell_width()).is_err());
    let mapping = gb_bootstrap::mapping_v2::derive(carrier.side(), carrier.shell_width()).unwrap();
    let cell = mapping.forward(1, 0).unwrap() as usize;
    let inner = usize::from(mapping.interior_side());
    let width = usize::from(carrier.shell_width());
    let absolute = (cell / inner + width) * usize::from(carrier.side()) + cell % inner + width;
    let mut changed = carrier.packed_bytes().to_vec();
    changed[4 + absolute / 8] ^= 1 << (7 - absolute % 8);
    assert!(recover_clean_matrix(&changed, carrier.shell_width()).is_err());
    assert!(mapping.fixed_pad_cells() > 0);
    let logical = mapping.unit_slot_count() * 1728;
    let physical =
        (mapping.cell_multiplier() * logical + mapping.cell_offset()) % mapping.population();
    assert_eq!(mapping.inverse(physical).unwrap(), (1, 0, 0));
    let absolute = (physical as usize / inner + width) * usize::from(carrier.side())
        + physical as usize % inner
        + width;
    let mut changed = carrier.packed_bytes().to_vec();
    changed[4 + absolute / 8] ^= 1 << (7 - absolute % 8);
    assert!(recover_clean_matrix(&changed, carrier.shell_width()).is_err());
    assert!(
        recover_clean_matrix(
            &carrier.packed_bytes()[..carrier.packed_bytes().len() - 1],
            carrier.shell_width()
        )
        .is_err()
    );
    assert!(recover_clean_matrix(carrier.packed_bytes(), 111).is_err());
}
