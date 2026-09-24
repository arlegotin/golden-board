use gb_bootstrap::first_use_v2::{FirstUseInputs, build_first_use_v2, validate_first_use_v2};
use gb_foundation::{ManifestValue as V, serialize_manifest, validate_canonical_manifest};
use std::collections::BTreeMap;
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
fn number(value: &V) -> usize {
    let V::U64(value) = value else {
        panic!("integer")
    };
    usize::try_from(*value).unwrap()
}

#[test]
fn packed_node_fields_partition_only_actual_observed_bytes() {
    let value = validate_canonical_manifest(proof()).unwrap();
    let prefix = &prefixes()[0];
    let mut at = 64;
    let package = loop {
        let size = u32::from_be_bytes(prefix[at + 4..at + 8].try_into().unwrap()) as usize;
        if prefix[at + 1] == 5 {
            break &prefix[at + 8..at + 8 + size];
        }
        at += 8 + size;
    };
    let mut fields: BTreeMap<(usize, usize), Vec<Vec<usize>>> = BTreeMap::new();
    for field in rows(&value, "node_field_rows") {
        let V::Array(field) = field else {
            panic!("field")
        };
        let field: Vec<_> = field.iter().map(number).collect();
        fields.entry((field[0], field[1])).or_default().push(field);
    }
    for node in rows(&value, "node_rows") {
        let V::Array(node) = node else { panic!("node") };
        let key = (number(&node[0]), number(&node[1]));
        let mut cursor = number(&node[3]);
        for field in fields.remove(&key).unwrap() {
            assert_eq!(field[4], cursor);
            cursor += field[5];
            if field[2] == 0 {
                assert_eq!(field[5], 1);
                assert_eq!(usize::from(package[field[4]] & 31), number(&node[5]));
                assert_eq!(usize::from(package[field[4]] >> 5), number(&node[6]));
            } else {
                let bytes = &package[field[4]..cursor];
                assert!(bytes[..bytes.len() - 1].iter().all(|b| b & 128 != 0));
                assert_eq!(bytes[bytes.len() - 1] & 128, 0);
                assert!(bytes.len() == 1 || bytes[bytes.len() - 1] != 0);
                let observed = bytes.iter().enumerate().fold(0u64, |value, (i, byte)| {
                    value | (u64::from(byte & 127) << (7 * i))
                });
                let expected = match field[2] {
                    1 => &node[7],
                    2 => {
                        let V::Array(args) = &node[8] else {
                            panic!("arguments")
                        };
                        let V::Array(arg) = &args[field[3] - 1] else {
                            panic!("argument")
                        };
                        &arg[0]
                    }
                    3 | 4 => {
                        let V::Array(values) = &node[if field[2] == 3 { 9 } else { 10 }] else {
                            panic!("field value")
                        };
                        &values[usize::from(field[2] == 4)]
                    }
                    _ => panic!("field kind"),
                };
                assert_eq!(expected, &V::U64(observed));
            }
        }
        assert_eq!(cursor, number(&node[3]) + number(&node[4]));
    }
    assert!(fields.is_empty());
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
        ("node_rows", 2991),
        ("recipe_rows", 41),
        ("table_rows", 19),
        ("node_field_rows", 11937),
        ("opcode_rows", 25),
        ("literal_rows", 37),
    ] {
        assert_eq!(rows(&value, key).len(), count);
    }
    let operational: Vec<_> = rows(&value, "use_rows")
        .iter()
        .filter_map(|row| {
            let V::Array(row) = row else {
                panic!("use row")
            };
            (number(&row[0]) == 0).then(|| number(&row[1]))
        })
        .collect();
    assert_eq!(operational, [30, 109, 113, 120, 123, 127, 202]);
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
        "node_field_rows",
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
