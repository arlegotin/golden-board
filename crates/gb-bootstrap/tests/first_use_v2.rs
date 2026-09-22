use gb_bootstrap::first_use_v2::{FirstUseInputs, build_first_use_v2, validate_first_use_v2};
use gb_foundation::{ManifestValue as V, serialize_manifest, validate_canonical_manifest};
use std::sync::OnceLock;

fn prefixes() -> &'static [Vec<u8>; 4] {
    static VALUE: OnceLock<[Vec<u8>; 4]> = OnceLock::new();
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
        // Authoring is test setup only, absent from the pure evidence API.
        gb_bootstrap::route_v2::build_route_prefixes(&slice).unwrap()
    })
}
fn input() -> FirstUseInputs<'static> {
    FirstUseInputs {
        prefixes: prefixes().each_ref().map(Vec::as_slice),
        side: 2048,
        width: 112,
    }
}
fn proof() -> &'static Vec<u8> {
    static VALUE: OnceLock<Vec<u8>> = OnceLock::new();
    VALUE.get_or_init(|| build_first_use_v2(input()).unwrap())
}
fn rows(value: &V, key: &str) -> Vec<V> {
    let V::Object(root) = value else {
        panic!("object")
    };
    let V::Array(rows) = &root[key] else {
        panic!("array")
    };
    rows.clone()
}

#[test]
fn complete_observed_package_has_exact_finite_coverage() {
    println!("active first-use evidence {} bytes", proof().len());
    let value = validate_canonical_manifest(proof()).unwrap();
    assert_eq!(
        &rows(&value, "mapping_use")[..3],
        &[V::U64(9), V::U64(17), V::U64(228)]
    );
    for (key, count) in [
        ("route_rows", 4),
        ("node_rows", 1184),
        ("recipe_rows", 29),
        ("table_rows", 14),
        ("opcode_rows", 25),
        ("literal_rows", 37),
    ] {
        assert_eq!(rows(&value, key).len(), count);
    }
    assert_eq!(
        rows(&value, "copy_rows"),
        vec![
            V::Array(vec![V::U64(70), V::U64(1), V::U64(33), V::U64(0)]),
            V::Array(vec![V::U64(71), V::U64(2), V::U64(33), V::U64(8)]),
            V::Array(vec![V::U64(72), V::U64(4), V::U64(34), V::U64(0)]),
            V::Array(vec![V::U64(73), V::U64(4), V::U64(34), V::U64(3)]),
        ]
    );
    validate_first_use_v2(proof(), input()).unwrap();
}

#[test]
fn omitted_or_remapped_evidence_fails_closed() {
    for key in [
        "field_rows",
        "node_rows",
        "literal_rows",
        "use_rows",
        "table_rows",
    ] {
        let V::Object(mut value) = validate_canonical_manifest(proof()).unwrap() else {
            panic!()
        };
        let Some(V::Array(rows)) = value.get_mut(key) else {
            panic!()
        };
        rows.pop();
        assert!(
            validate_first_use_v2(&serialize_manifest(&V::Object(value)).unwrap(), input())
                .is_err()
        );
    }
}

#[test]
fn invalid_geometry_or_unframed_prefix_cannot_emit_proof() {
    assert!(
        build_first_use_v2(FirstUseInputs {
            width: 113,
            ..input()
        })
        .is_err()
    );
    let mut p = prefixes()[0].clone();
    p.push(0);
    let mut i = input();
    i.prefixes[0] = &p;
    assert!(build_first_use_v2(i).is_err());
    assert!(validate_first_use_v2(b"{}\n", input()).is_err());
}
