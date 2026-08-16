use std::collections::{BTreeMap, BTreeSet};
use std::fs::OpenOptions;
use std::io::Read;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::{Path, PathBuf};

use gb_content::{
    ContentProjection, ContentReject, FieldValue, RecordPayload, advance_committed,
    encode_run_state, new_run, step, stream_validation, validate_run_state,
};
use gb_foundation::{ManifestValue as V, parse_manifest, validate_canonical_manifest};

const FIXTURE_BYTES: usize = 150_587;
#[cfg(any(target_os = "linux", target_os = "android"))]
const O_NOFOLLOW: i32 = 0x20_000;
#[cfg(any(target_os = "macos", target_os = "ios"))]
const O_NOFOLLOW: i32 = 0x100;
#[cfg(any(target_os = "linux", target_os = "android"))]
const O_NONBLOCK: i32 = 0x800;
#[cfg(any(target_os = "macos", target_os = "ios"))]
const O_NONBLOCK: i32 = 0x4;

fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap()
}

fn safe_read(relative: &str, cap: usize) -> Vec<u8> {
    assert!(!relative.is_empty());
    assert!(relative.split('/').all(|part| {
        !part.is_empty()
            && part != "."
            && part != ".."
            && part
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.'))
    }));
    let mut path = root();
    let parts: Vec<_> = relative.split('/').collect();
    for part in &parts[..parts.len() - 1] {
        path.push(part);
        let metadata = path.symlink_metadata().unwrap();
        assert!(metadata.file_type().is_dir() && !metadata.file_type().is_symlink());
    }
    path.push(parts.last().unwrap());
    let before = path.symlink_metadata().unwrap();
    assert!(before.file_type().is_file() && !before.file_type().is_symlink());
    assert!(before.len() <= cap as u64);
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(O_NOFOLLOW | O_NONBLOCK)
        .open(path)
        .unwrap();
    let after = file.metadata().unwrap();
    assert!(after.file_type().is_file());
    assert_eq!((before.dev(), before.ino()), (after.dev(), after.ino()));
    let mut bytes = Vec::with_capacity(after.len() as usize);
    file.take(cap as u64 + 1).read_to_end(&mut bytes).unwrap();
    assert!(bytes.len() <= cap);
    bytes
}

fn object<'a>(value: &'a V, keys: &[&str]) -> &'a BTreeMap<String, V> {
    let V::Object(fields) = value else {
        panic!("object")
    };
    assert_eq!(
        fields.keys().map(String::as_str).collect::<BTreeSet<_>>(),
        keys.iter().copied().collect::<BTreeSet<_>>()
    );
    fields
}

fn array(value: &V) -> &[V] {
    let V::Array(values) = value else {
        panic!("array")
    };
    values
}

fn text(value: &V) -> &str {
    let V::String(value) = value else {
        panic!("string")
    };
    value
}

fn number(value: &V) -> usize {
    let V::U64(value) = value else { panic!("u64") };
    usize::try_from(*value).unwrap()
}

fn optional<'a>(fields: &'a BTreeMap<String, V>, key: &str) -> Option<&'a V> {
    fields.get(key)
}

fn field<'a>(fields: &'a BTreeMap<String, V>, key: &str) -> &'a V {
    fields.get(key).unwrap()
}

fn u(value: impl Into<u64>) -> V {
    V::U64(value.into())
}

fn s(value: impl Into<String>) -> V {
    V::String(value.into())
}

fn a(values: Vec<V>) -> V {
    V::Array(values)
}

fn o(values: Vec<(&str, V)>) -> V {
    V::Object(
        values
            .into_iter()
            .map(|(key, value)| (key.to_owned(), value))
            .collect(),
    )
}

fn projection_value(projection: &ContentProjection) -> V {
    let records = projection
        .records()
        .iter()
        .map(|record| {
            let mut values = vec![("record_id", u(record.record_id()))];
            match record.payload() {
                RecordPayload::Text(text) => {
                    values.extend([("kind", s("TEXT")), ("text", s(text))]);
                }
                RecordPayload::AtomSchema {
                    atom_class,
                    atom_width,
                    entries,
                    min_value,
                    max_value,
                    allowed_mask,
                } => {
                    values.extend([
                        ("kind", s("ATOM_SCHEMA")),
                        ("atom_class", u(*atom_class)),
                        ("atom_width", u(*atom_width)),
                        ("entry_count", u(entries.len() as u64)),
                    ]);
                    if let (Some(minimum), Some(maximum)) = (min_value, max_value) {
                        values.extend([("min_value", u(*minimum)), ("max_value", u(*maximum))]);
                    } else {
                        if let Some(mask) = allowed_mask {
                            values.push(("allowed_mask", u(*mask)));
                        }
                        values.push((
                            "entries",
                            a(entries
                                .iter()
                                .map(|entry| {
                                    if allowed_mask.is_some() {
                                        o(vec![
                                            ("one_hot_bit", u(entry.code)),
                                            ("label_text_ref", u(entry.label_text_ref)),
                                        ])
                                    } else {
                                        o(vec![
                                            ("code", u(entry.code)),
                                            ("label_text_ref", u(entry.label_text_ref)),
                                        ])
                                    }
                                })
                                .collect()),
                        ));
                    }
                }
                RecordPayload::AtomVector {
                    atom_schema_ref,
                    atoms,
                } => values.extend([
                    ("kind", s("ATOM_VECTOR")),
                    ("atom_schema_ref", u(*atom_schema_ref)),
                    ("atom_count", u(atoms.len() as u64)),
                    ("atoms", a(atoms.iter().copied().map(u).collect())),
                ]),
                RecordPayload::Matrix {
                    atom_schema_ref,
                    rows,
                    columns,
                    cells,
                } => values.extend([
                    ("kind", s("MATRIX")),
                    ("atom_schema_ref", u(*atom_schema_ref)),
                    ("rows", u(*rows)),
                    ("columns", u(*columns)),
                    ("cells", a(cells.iter().copied().map(u).collect())),
                ]),
                RecordPayload::FieldSchema { fields } => values.extend([
                    ("kind", s("FIELD_SCHEMA")),
                    ("field_count", u(fields.len() as u64)),
                    (
                        "fields",
                        a(fields
                            .iter()
                            .map(|field| {
                                o(vec![
                                    ("name_text_ref", u(field.name_text_ref)),
                                    ("storage", u(field.storage)),
                                    ("type", u(field.type_code)),
                                    ("count", u(field.count)),
                                ])
                            })
                            .collect()),
                    ),
                ]),
                RecordPayload::Tuple {
                    field_schema_ref,
                    field_values,
                } => values.extend([
                    ("kind", s("TUPLE")),
                    ("field_schema_ref", u(*field_schema_ref)),
                    (
                        "field_values",
                        a(field_values
                            .iter()
                            .map(|value| match value {
                                FieldValue::Atoms(atoms) => {
                                    o(vec![("atoms", a(atoms.iter().copied().map(u).collect()))])
                                }
                                FieldValue::RecordRefs(refs) => o(vec![(
                                    "record_refs",
                                    a(refs.iter().copied().map(u).collect()),
                                )]),
                            })
                            .collect()),
                    ),
                ]),
                RecordPayload::RegionSet {
                    surface_matrix_ref,
                    regions,
                } => values.extend([
                    ("kind", s("REGION_SET")),
                    ("surface_matrix_ref", u(*surface_matrix_ref)),
                    ("region_count", u(regions.len() as u64)),
                    (
                        "regions",
                        a(regions
                            .iter()
                            .map(|region| {
                                o(vec![
                                    ("region_id", u(region.region_id)),
                                    ("label_ref", u(region.label_ref)),
                                    ("row_start", u(region.row_start)),
                                    ("row_end", u(region.row_end)),
                                    ("column_start", u(region.column_start)),
                                    ("column_end", u(region.column_end)),
                                    ("flags", u(region.flags)),
                                ])
                            })
                            .collect()),
                    ),
                ]),
                RecordPayload::SemanticBinding {
                    binding_class,
                    namespace_id,
                    semantic_code,
                    argument,
                    auxiliary,
                } => values.extend([
                    ("kind", s("SEMANTIC_BINDING")),
                    ("binding_class", u(*binding_class)),
                    ("namespace_id", u(*namespace_id)),
                    ("semantic_code", u(*semantic_code)),
                    ("argument", u(*argument)),
                    ("auxiliary", u(*auxiliary)),
                ]),
                RecordPayload::OpaqueData {
                    data_binding_ref,
                    data,
                } => values.extend([
                    ("kind", s("OPAQUE_DATA")),
                    ("data_binding_ref", u(*data_binding_ref)),
                    ("data", a(data.iter().copied().map(u).collect())),
                ]),
                RecordPayload::PredicateResult {
                    predicate_binding_ref,
                    subject_opaque_data_ref,
                    result_atom_vector_ref,
                } => values.extend([
                    ("kind", s("PREDICATE_RESULT")),
                    ("predicate_binding_ref", u(*predicate_binding_ref)),
                    ("subject_opaque_data_ref", u(*subject_opaque_data_ref)),
                    ("result_atom_vector_ref", u(*result_atom_vector_ref)),
                ]),
                RecordPayload::Feedback {
                    feedback_code,
                    display_ref,
                    predicate_result_ref,
                } => values.extend([
                    ("kind", s("FEEDBACK")),
                    ("feedback_code", u(*feedback_code)),
                    ("display_ref", u(*display_ref)),
                    ("predicate_result_ref", u(*predicate_result_ref)),
                ]),
                RecordPayload::PassiveTrace {
                    presentation_ref,
                    region_set_ref,
                    resulting_presentation_ref,
                    limitation_text_ref,
                    actions,
                    expected_outcome,
                    expected_feedback_ref,
                    expected_next_node_ref,
                } => values.extend([
                    ("kind", s("PASSIVE_TRACE")),
                    ("presentation_ref", u(*presentation_ref)),
                    ("region_set_ref", u(*region_set_ref)),
                    ("resulting_presentation_ref", u(*resulting_presentation_ref)),
                    ("limitation_text_ref", u(*limitation_text_ref)),
                    ("action_count", u(actions.len() as u64)),
                    (
                        "actions",
                        a(actions
                            .iter()
                            .map(|action| {
                                s(action
                                    .iter()
                                    .map(|byte| format!("{byte:02x}"))
                                    .collect::<String>())
                            })
                            .collect()),
                    ),
                    ("expected_outcome", u(*expected_outcome)),
                    ("expected_feedback_ref", u(*expected_feedback_ref)),
                    ("expected_next_node_ref", u(*expected_next_node_ref)),
                ]),
                RecordPayload::LessonNode {
                    role,
                    response_shape,
                    answer_mode,
                    flags,
                    presentation_ref,
                    region_set_ref,
                    predicate_result_ref,
                    passive_trace_ref,
                    max_selections,
                    item_event_budget,
                    cases,
                    default_feedback_ref,
                    default_next_node_ref,
                } => values.extend([
                    ("kind", s("LESSON_NODE")),
                    ("role", u(*role)),
                    ("response_shape", u(*response_shape)),
                    ("answer_mode", u(*answer_mode)),
                    ("flags", u(*flags)),
                    ("presentation_ref", u(*presentation_ref)),
                    ("region_set_ref", u(*region_set_ref)),
                    ("predicate_result_ref", u(*predicate_result_ref)),
                    ("passive_trace_ref", u(*passive_trace_ref)),
                    ("max_selections", u(*max_selections)),
                    ("item_event_budget", u(*item_event_budget)),
                    ("case_count", u(cases.len() as u64)),
                    (
                        "cases",
                        a(cases
                            .iter()
                            .map(|case| {
                                o(vec![
                                    ("case_class", u(case.case_class)),
                                    ("selection_count", u(case.region_ids.len() as u64)),
                                    (
                                        "region_ids",
                                        a(case.region_ids.iter().copied().map(u).collect()),
                                    ),
                                    ("feedback_ref", u(case.feedback_ref)),
                                    ("next_node_ref", u(case.next_node_ref)),
                                ])
                            })
                            .collect()),
                    ),
                    ("default_feedback_ref", u(*default_feedback_ref)),
                    ("default_next_node_ref", u(*default_next_node_ref)),
                ]),
                RecordPayload::Root {
                    entry_node_ref,
                    global_event_budget,
                } => values.extend([
                    ("kind", s("ROOT")),
                    ("entry_node_ref", u(*entry_node_ref)),
                    ("global_event_budget", u(*global_event_budget)),
                ]),
            }
            o(values)
        })
        .collect();
    o(vec![
        ("version", u(projection.version())),
        ("root_record_id", u(projection.root_record_id())),
        ("records", a(records)),
    ])
}

fn hex(value: &str) -> Vec<u8> {
    assert!(value.len().is_multiple_of(2));
    value
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            let digit = |byte| match byte {
                b'0'..=b'9' => byte - b'0',
                b'a'..=b'f' => byte - b'a' + 10,
                _ => panic!("lowercase hex"),
            };
            digit(pair[0]) << 4 | digit(pair[1])
        })
        .collect()
}

fn sha256(bytes: &[u8]) -> String {
    const K: [u32; 64] = [
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4,
        0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe,
        0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f,
        0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
        0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
        0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
        0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116,
        0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
        0xc67178f2,
    ];
    let mut data = bytes.to_vec();
    let bit_len = (data.len() as u64) * 8;
    data.push(0x80);
    while data.len() % 64 != 56 {
        data.push(0);
    }
    data.extend_from_slice(&bit_len.to_be_bytes());
    let mut h = [
        0x6a09e667u32,
        0xbb67ae85,
        0x3c6ef372,
        0xa54ff53a,
        0x510e527f,
        0x9b05688c,
        0x1f83d9ab,
        0x5be0cd19,
    ];
    for chunk in data.chunks_exact(64) {
        let mut w = [0u32; 64];
        for (index, word) in chunk.chunks_exact(4).enumerate() {
            w[index] = u32::from_be_bytes([word[0], word[1], word[2], word[3]]);
        }
        for index in 16..64 {
            let s0 = w[index - 15].rotate_right(7)
                ^ w[index - 15].rotate_right(18)
                ^ (w[index - 15] >> 3);
            let s1 = w[index - 2].rotate_right(17)
                ^ w[index - 2].rotate_right(19)
                ^ (w[index - 2] >> 10);
            w[index] = w[index - 16]
                .wrapping_add(s0)
                .wrapping_add(w[index - 7])
                .wrapping_add(s1);
        }
        let mut v = h;
        for index in 0..64 {
            let s1 = v[4].rotate_right(6) ^ v[4].rotate_right(11) ^ v[4].rotate_right(25);
            let choose = (v[4] & v[5]) ^ (!v[4] & v[6]);
            let t1 = v[7]
                .wrapping_add(s1)
                .wrapping_add(choose)
                .wrapping_add(K[index])
                .wrapping_add(w[index]);
            let s0 = v[0].rotate_right(2) ^ v[0].rotate_right(13) ^ v[0].rotate_right(22);
            let majority = (v[0] & v[1]) ^ (v[0] & v[2]) ^ (v[1] & v[2]);
            let t2 = s0.wrapping_add(majority);
            v = [
                t1.wrapping_add(t2),
                v[0],
                v[1],
                v[2],
                v[3].wrapping_add(t1),
                v[4],
                v[5],
                v[6],
            ];
        }
        for index in 0..8 {
            h[index] = h[index].wrapping_add(v[index]);
        }
    }
    h.iter().map(|word| format!("{word:08x}")).collect()
}

fn fixture() -> V {
    let bytes = safe_read("conformance/content-v0.json", FIXTURE_BYTES);
    assert_eq!(bytes.len(), FIXTURE_BYTES);
    validate_canonical_manifest(&bytes).unwrap();
    parse_manifest(&bytes).unwrap()
}

fn expected_rejection(expected: &V) -> Option<ContentReject> {
    let fields = object(
        expected,
        &[
            if matches!(expected, V::Object(map) if map.contains_key("rejection")) {
                "rejection"
            } else {
                "success"
            },
        ],
    );
    let rejection = optional(fields, "rejection")?;
    let rejection = object(rejection, &["code", "raw_end", "raw_start"]);
    Some(ContentReject {
        code: number(field(rejection, "code")) as u16,
        raw_start: number(field(rejection, "raw_start")) as u32,
        raw_end: number(field(rejection, "raw_end")) as u32,
    })
}

fn generic_base(top: &BTreeMap<String, V>) -> Vec<u8> {
    let bases = array(field(top, "bases"));
    assert_eq!(bases.len(), 1);
    let base = object(
        &bases[0],
        &[
            "name",
            "projection",
            "stream_hex",
            "stream_length",
            "stream_sha256",
        ],
    );
    assert_eq!(text(field(base, "name")), "generic-base");
    let bytes = hex(text(field(base, "stream_hex")));
    assert_eq!(bytes.len(), number(field(base, "stream_length")));
    bytes
}

fn patch_base(recipe: &BTreeMap<String, V>, base: &[u8]) -> Vec<u8> {
    let parameters = object(field(recipe, "input"), &["base", "patches"]);
    assert_eq!(text(field(parameters, "base")), "generic-base");
    let mut output = base.to_vec();
    let mut prior_start = usize::MAX;
    for patch in array(field(parameters, "patches")) {
        let patch = object(patch, &["new_hex", "old_hex", "start"]);
        let start = number(field(patch, "start"));
        let old = hex(text(field(patch, "old_hex")));
        let new = hex(text(field(patch, "new_hex")));
        assert!(start < prior_start);
        assert!(
            start
                .checked_add(old.len())
                .is_some_and(|end| end <= prior_start)
        );
        assert_eq!(&output[start..start + old.len()], old);
        output.splice(start..start + old.len(), new);
        prior_start = start;
    }
    output
}

fn push_u16(bytes: &mut Vec<u8>, value: u16) {
    bytes.extend_from_slice(&value.to_be_bytes());
}

fn record(bytes: &mut Vec<u8>, id: u16, kind: u16, payload: &[u8]) {
    push_u16(bytes, id);
    push_u16(bytes, kind);
    bytes.extend_from_slice(&(payload.len() as u32).to_be_bytes());
    bytes.extend_from_slice(payload);
}

fn record_bytes(id: u16, kind: u16, payload: &[u8]) -> Vec<u8> {
    let mut bytes = Vec::new();
    record(&mut bytes, id, kind, payload);
    bytes
}

fn stream_records(records: &[Vec<u8>]) -> Vec<u8> {
    let mut bytes = vec![0, 0];
    push_u16(&mut bytes, records.len() as u16);
    for row in records {
        bytes.extend_from_slice(row);
    }
    bytes
}

fn schema(id: u16) -> Vec<u8> {
    record_bytes(id, 2, &[1, 1, 0, 0, 0, 0])
}

fn vector(id: u16, schema: u16, count: usize) -> Vec<u8> {
    let mut payload = Vec::new();
    push_u16(&mut payload, schema);
    push_u16(&mut payload, count as u16);
    payload.resize(4 + count, 0);
    record_bytes(id, 3, &payload)
}

fn matrix(id: u16, schema: u16, rows: u16, columns: u16, count: usize) -> Vec<u8> {
    let mut payload = Vec::new();
    for value in [schema, rows, columns] {
        push_u16(&mut payload, value);
    }
    payload.resize(6 + count, 0);
    record_bytes(id, 4, &payload)
}

fn wrong_root(mut records: Vec<Vec<u8>>, id: u16, entry: u16) -> Vec<u8> {
    let mut payload = Vec::new();
    push_u16(&mut payload, entry);
    push_u16(&mut payload, 1);
    records.push(record_bytes(id, 14, &payload));
    stream_records(&records)
}

fn maximum_support_stream() -> Vec<u8> {
    let mut stream = vec![0, 0, 0, 14];
    record(&mut stream, 1, 1, b"cell");
    record(&mut stream, 2, 2, &[1, 1, 0, 0, 0, 0]);
    let mut payload = Vec::new();
    push_u16(&mut payload, 2);
    push_u16(&mut payload, 64);
    push_u16(&mut payload, 64);
    payload.resize(6 + 4096, 0);
    record(&mut stream, 3, 4, &payload);

    payload.clear();
    push_u16(&mut payload, 3);
    push_u16(&mut payload, 4096);
    for index in 0..4096u16 {
        push_u16(&mut payload, index + 1);
        push_u16(&mut payload, 1);
        push_u16(&mut payload, index / 64);
        push_u16(&mut payload, index / 64 + 1);
        push_u16(&mut payload, index % 64);
        push_u16(&mut payload, index % 64 + 1);
        payload.extend_from_slice(&[1, 0]);
    }
    record(&mut stream, 4, 7, &payload);
    payload = vec![1, 0];
    for value in [1, 1, 2, 1] {
        push_u16(&mut payload, value);
    }
    record(&mut stream, 5, 8, &payload);
    payload = vec![0, 5, 0];
    record(&mut stream, 6, 9, &payload);
    payload = vec![0, 2, 0, 1, 0];
    record(&mut stream, 7, 3, &payload);
    payload = vec![2, 0];
    for value in [1, 2, 5, 2] {
        push_u16(&mut payload, value);
    }
    record(&mut stream, 8, 8, &payload);
    payload.clear();
    for value in [8, 6, 7] {
        push_u16(&mut payload, value);
    }
    record(&mut stream, 9, 10, &payload);
    for (id, code) in [(10, 2), (11, 3)] {
        payload.clear();
        for value in [code, 1, 9] {
            push_u16(&mut payload, value);
        }
        record(&mut stream, id, 11, &payload);
    }

    payload.clear();
    for value in [3, 4, 0, 0, 4097] {
        push_u16(&mut payload, value);
    }
    for id in 1..=4096u16 {
        payload.extend_from_slice(&[1, 0]);
        push_u16(&mut payload, id);
    }
    payload.extend_from_slice(&[3, 0, 0, 0, 1, 0]);
    push_u16(&mut payload, 10);
    push_u16(&mut payload, 0);
    record(&mut stream, 12, 12, &payload);

    payload = vec![5, 2, 1, 0];
    for value in [3, 4, 9, 12, 4096, 65535, 1] {
        push_u16(&mut payload, value);
    }
    payload.extend_from_slice(&[1, 0]);
    push_u16(&mut payload, 4096);
    for id in 1..=4096u16 {
        push_u16(&mut payload, id);
    }
    push_u16(&mut payload, 10);
    push_u16(&mut payload, 0);
    push_u16(&mut payload, 11);
    push_u16(&mut payload, 13);
    record(&mut stream, 13, 13, &payload);
    payload.clear();
    push_u16(&mut payload, 13);
    push_u16(&mut payload, 65535);
    record(&mut stream, 14, 14, &payload);
    assert_eq!(stream.len(), 86_252);
    stream
}

fn boundary_recipe(tag: &str, input: &BTreeMap<String, V>) -> Vec<u8> {
    let n = |key| number(field(input, key));
    match tag {
        "stream-byte-cap" => vec![0; n("byte_count")],
        "stream-bytes-boundary" => {
            let mut bytes = vec![0; n("byte_count")];
            bytes[4..].fill(b'a');
            bytes
        }
        "record-count-boundary" => {
            let mut bytes = vec![0, 0];
            push_u16(&mut bytes, n("record_count") as u16);
            bytes
        }
        "record-id-boundary" => {
            wrong_root(vec![record_bytes(1, 1, b"a")], n("record_id") as u16, 1)
        }
        "text-bytes-boundary" => {
            if text(field(input, "boundary")) == "exact" {
                wrong_root(vec![record_bytes(1, 1, &vec![b'a'; n("text_bytes")])], 2, 1)
            } else {
                let mut bytes = vec![0, 0, 0, 2, 0, 1, 0, 1];
                bytes.extend_from_slice(&(n("declared_text_bytes") as u32).to_be_bytes());
                bytes.extend_from_slice(&record_bytes(2, 14, &[0, 1, 0, 1]));
                bytes
            }
        }
        "per-kind-records-boundary" => {
            let count = n("text_record_count");
            let rows: Vec<_> = (1..=count)
                .map(|id| record_bytes(id as u16, 1, b"a"))
                .collect();
            wrong_root(rows, (count + 1) as u16, 1)
        }
        "enum-entries-boundary" => {
            let count = n("entry_count");
            let mut rows: Vec<_> = (1..=4096).map(|id| record_bytes(id, 1, b"a")).collect();
            let mut payload = vec![2, 2];
            push_u16(&mut payload, count as u16);
            for index in 0..count {
                push_u16(&mut payload, index as u16);
                push_u16(
                    &mut payload,
                    if count == 4096 { index as u16 + 1 } else { 1 },
                );
            }
            rows.push(record_bytes(4097, 2, &payload));
            wrong_root(rows, 4098, 4097)
        }
        "vector-atoms-boundary" => wrong_root(vec![schema(1), vector(2, 1, n("atom_count"))], 3, 2),
        "matrix-cells-boundary" => wrong_root(
            vec![
                schema(1),
                matrix(2, 1, n("rows") as u16, n("columns") as u16, n("cell_count")),
            ],
            3,
            2,
        ),
        "field-schema-fields-boundary" => {
            let count = n("field_count");
            let mut rows: Vec<_> = (1..=count)
                .map(|id| record_bytes(id as u16, 1, format!("f{id}").as_bytes()))
                .collect();
            rows.push(schema(258));
            let mut payload = Vec::new();
            push_u16(&mut payload, count as u16);
            for index in 1..=count {
                push_u16(&mut payload, index as u16);
                payload.extend_from_slice(&[1, 0]);
                push_u16(&mut payload, 258);
                push_u16(&mut payload, 1);
            }
            rows.push(record_bytes(259, 5, &payload));
            wrong_root(rows, 260, 259)
        }
        "tuple-slots-boundary" => {
            let count = n("slot_count");
            let mut fields = vec![0, 1, 0, 1, 2, 0, 0, 1];
            push_u16(&mut fields, count as u16);
            if count == 4096 {
                let mut tuple = vec![0, 2];
                tuple.extend(std::iter::repeat_n([0, 1], count).flatten());
                wrong_root(
                    vec![
                        record_bytes(1, 1, b"refs"),
                        record_bytes(2, 5, &fields),
                        record_bytes(3, 6, &tuple),
                    ],
                    4,
                    3,
                )
            } else {
                wrong_root(
                    vec![record_bytes(1, 1, b"refs"), record_bytes(2, 5, &fields)],
                    3,
                    2,
                )
            }
        }
        "opaque-atoms-boundary" => {
            let count = n("atom_count");
            let mut binding = vec![1, 0, 0, 1, 0, 1, 0, 1];
            push_u16(&mut binding, count as u16);
            if count == 4096 {
                let mut opaque = vec![0, 2];
                opaque.resize(2 + count, 0);
                wrong_root(
                    vec![
                        schema(1),
                        record_bytes(2, 8, &binding),
                        record_bytes(3, 9, &opaque),
                    ],
                    4,
                    3,
                )
            } else {
                wrong_root(vec![schema(1), record_bytes(2, 8, &binding)], 3, 2)
            }
        }
        "regions-boundary" => {
            let count = n("region_count");
            let mut regions = Vec::new();
            push_u16(&mut regions, 3);
            push_u16(&mut regions, count as u16);
            for index in 0..count {
                push_u16(&mut regions, index as u16 + 1);
                push_u16(&mut regions, 1);
                push_u16(&mut regions, (index / 64) as u16);
                push_u16(&mut regions, (index / 64 + 1) as u16);
                push_u16(&mut regions, (index % 64) as u16);
                push_u16(&mut regions, (index % 64 + 1) as u16);
                regions.extend_from_slice(&[1, 0]);
            }
            wrong_root(
                vec![
                    record_bytes(1, 1, b"cell"),
                    schema(2),
                    matrix(3, 2, 64, 64, 4096),
                    record_bytes(4, 7, &regions),
                ],
                5,
                4,
            )
        }
        "lesson-nodes-boundary" => {
            let count = n("lesson_node_count");
            let rows: Vec<_> = (1..=count)
                .map(|id| record_bytes(id as u16, 13, &[0; 22]))
                .collect();
            wrong_root(rows, (count + 1) as u16, 1)
        }
        "cases-per-node-boundary" => {
            let count = n("case_count");
            let mut payload = vec![5, 3, 1, 1];
            payload.extend_from_slice(&[0; 8]);
            push_u16(&mut payload, 4096);
            push_u16(&mut payload, 65535);
            push_u16(&mut payload, count as u16);
            for index in 1..=count {
                payload.extend_from_slice(&[1, 0, 0, 1]);
                push_u16(&mut payload, index as u16);
                payload.extend_from_slice(&[0; 4]);
            }
            payload.extend_from_slice(&[0; 4]);
            stream_records(&[
                record_bytes(1, 13, &payload),
                record_bytes(2, 14, &[0, 1, 255, 255]),
            ])
        }
        "record-payload-bytes-boundary" => {
            let mut bytes = vec![0, 0, 0, 2, 0, 1, 0, 3];
            bytes.extend_from_slice(&(n("declared_payload_bytes") as u32).to_be_bytes());
            bytes
        }
        other => panic!("unhandled boundary recipe {other}"),
    }
}

fn control_stream(extra: bool) -> Vec<u8> {
    let mut rows = vec![
        record_bytes(1, 1, b"cell"),
        schema(2),
        matrix(3, 2, 1, 3, 3),
    ];
    let mut payload = Vec::new();
    push_u16(&mut payload, 3);
    push_u16(&mut payload, 3);
    for index in 0..3u16 {
        for value in [index + 1, 1, 0, 1, index, index + 1] {
            push_u16(&mut payload, value);
        }
        payload.extend_from_slice(&[1, 0]);
    }
    rows.push(record_bytes(4, 7, &payload));
    payload = vec![1, 0];
    for value in [1, 1, 2, 1] {
        push_u16(&mut payload, value);
    }
    rows.push(record_bytes(5, 8, &payload));
    rows.push(record_bytes(6, 9, &[0, 5, 0]));
    rows.push(vector(7, 2, 1));
    payload = vec![2, 0];
    for value in [1, 2, 5, 2] {
        push_u16(&mut payload, value);
    }
    rows.push(record_bytes(8, 8, &payload));
    rows.push(record_bytes(9, 10, &[0, 8, 0, 6, 0, 7]));
    for (id, code) in [(10, 2), (11, 3), (12, 4)] {
        let mut feedback = Vec::new();
        for value in [code, 1, 9] {
            push_u16(&mut feedback, value);
        }
        rows.push(record_bytes(id, 11, &feedback));
    }
    let first_node = 4109u16;
    for index in 0..4096u16 {
        let next = if index < 4095 {
            first_node + index + 1
        } else {
            0
        };
        payload.clear();
        for value in [3, 4, 0, 0, 1] {
            push_u16(&mut payload, value);
        }
        payload.extend_from_slice(&[3, 0, 0, 0, 1, 0]);
        push_u16(&mut payload, 10);
        push_u16(&mut payload, next);
        rows.push(record_bytes(13 + index, 12, &payload));
    }
    for index in 0..4096u16 {
        let node_id = first_node + index;
        let success = if index < 4095 { node_id + 1 } else { 0 };
        let mut alternatives = vec![vec![1], vec![2]];
        if index == 4095 {
            alternatives.push(vec![3]);
            if extra {
                alternatives.push(vec![1, 1]);
            }
        }
        payload = vec![5, 3, 1, 1];
        for value in [3, 4, 9, 13 + index, 2, 3, 1 + alternatives.len() as u16] {
            push_u16(&mut payload, value);
        }
        payload.extend_from_slice(&[1, 0, 0, 0]);
        push_u16(&mut payload, 10);
        push_u16(&mut payload, success);
        for ids in alternatives {
            payload.extend_from_slice(&[2, 0]);
            push_u16(&mut payload, ids.len() as u16);
            for id in ids {
                push_u16(&mut payload, id);
            }
            push_u16(&mut payload, 12);
            push_u16(&mut payload, node_id);
        }
        push_u16(&mut payload, 11);
        push_u16(&mut payload, node_id);
        rows.push(record_bytes(node_id, 13, &payload));
    }
    let mut root = Vec::new();
    push_u16(&mut root, first_node);
    push_u16(&mut root, 12287);
    rows.push(record_bytes(first_node + 4096, 14, &root));
    stream_records(&rows)
}

#[test]
fn registered_fixture_inventory_and_generic_base_projection() {
    let fixture = fixture();
    let top = object(&fixture, &["bases", "cases", "recipes", "schema"]);
    assert_eq!(
        text(field(top, "schema")),
        "golden-board.content-v0-fixtures/v0"
    );
    assert_eq!(array(field(top, "cases")).len(), 55);
    assert_eq!(array(field(top, "recipes")).len(), 173);
    let bases = array(field(top, "bases"));
    assert_eq!(bases.len(), 1);
    let base = object(
        &bases[0],
        &[
            "name",
            "projection",
            "stream_hex",
            "stream_length",
            "stream_sha256",
        ],
    );
    assert_eq!(text(field(base, "name")), "generic-base");
    assert_eq!(number(field(base, "stream_length")), 575);
    let stream = hex(text(field(base, "stream_hex")));
    assert_eq!(stream.len(), 575);

    let projection = stream_validation(&stream).unwrap();
    assert_eq!(projection.version(), 0);
    assert_eq!(projection.root_record_id(), 29);
    assert_eq!(projection.records().len(), 29);
    assert_eq!(
        projection_value(&projection),
        field(base, "projection").clone()
    );
}

#[test]
fn all_literal_and_patch_stream_cases_match_exact_rejections() {
    let fixture = fixture();
    let top = object(&fixture, &["bases", "cases", "recipes", "schema"]);
    let base = generic_base(top);
    let mut executed = 0usize;

    for case in array(field(top, "cases")) {
        let case = object(case, &["covers", "expected", "input", "name", "operation"]);
        if text(field(case, "operation")) != "stream_validation" {
            continue;
        }
        let input = object(field(case, "input"), &["stream_hex"]);
        let bytes = hex(text(field(input, "stream_hex")));
        let expected = expected_rejection(field(case, "expected"));
        assert_eq!(
            stream_validation(&bytes).err(),
            expected,
            "{}",
            text(field(case, "name"))
        );
        executed += 1;
    }
    for recipe in array(field(top, "recipes")) {
        let recipe = object(
            recipe,
            &[
                "count_cap",
                "covers",
                "expected",
                "input",
                "input_bytes",
                "input_sha256",
                "name",
                "operation",
                "recipe",
            ],
        );
        if text(field(recipe, "operation")) != "stream_validation"
            || text(field(recipe, "recipe")) != "patch-base"
        {
            continue;
        }
        let bytes = patch_base(recipe, &base);
        let expected = expected_rejection(field(recipe, "expected"));
        assert_eq!(
            stream_validation(&bytes).err(),
            expected,
            "{}",
            text(field(recipe, "name"))
        );
        executed += 1;
    }
    assert_eq!(executed, 136 + 9);
}

#[test]
fn all_literal_runtime_cases_match_exact_bytes_and_rejections() {
    let fixture = fixture();
    let top = object(&fixture, &["bases", "cases", "recipes", "schema"]);
    let mut executed = 0usize;
    for case in array(field(top, "cases")) {
        let case = object(case, &["covers", "expected", "input", "name", "operation"]);
        let operation = text(field(case, "operation"));
        if operation == "stream_validation" {
            continue;
        }
        let name = text(field(case, "name"));
        let input_value = field(case, "input");
        let input = match operation {
            "new_run" => object(input_value, &["stream_hex"]),
            "step" => object(input_value, &["action_hex", "state_hex", "stream_hex"]),
            "advance_committed" => object(input_value, &["state_hex", "stream_hex"]),
            "validate_run_state" => object(input_value, &["state_hex", "stream_hex"]),
            other => panic!("unknown operation {other}"),
        };
        let projection = stream_validation(&hex(text(field(input, "stream_hex")))).unwrap();
        let expected = field(case, "expected");
        match operation {
            "new_run" => {
                let expected = object(expected, &["success"]);
                let success = object(field(expected, "success"), &["state_hex"]);
                assert_eq!(
                    encode_run_state(&new_run(&projection)),
                    hex(text(field(success, "state_hex"))),
                    "{name}"
                );
            }
            "step" => {
                let state_bytes = hex(text(field(input, "state_hex")));
                let state = validate_run_state(&projection, &state_bytes)
                    .unwrap_or_else(|error| panic!("{name}: {error:?}"));
                let (state, result) =
                    step(&projection, state, &hex(text(field(input, "action_hex"))));
                let expected = object(expected, &["success"]);
                let V::Object(success) = field(expected, "success") else {
                    panic!("success")
                };
                assert_eq!(
                    result as usize,
                    number(field(success, "interaction_result")),
                    "{name} result"
                );
                assert_eq!(
                    encode_run_state(&state),
                    hex(text(field(success, "state_hex"))),
                    "{name} state"
                );
                if let Some(value) = success.get("outcome") {
                    assert_eq!(state.outcome() as usize, number(value), "{name} outcome");
                }
                if let Some(value) = success.get("feedback_ref") {
                    assert_eq!(
                        state.feedback_ref() as usize,
                        number(value),
                        "{name} feedback"
                    );
                }
                if let Some(value) = success.get("next_node_ref") {
                    assert_eq!(state.next_node_ref() as usize, number(value), "{name} next");
                }
            }
            "advance_committed" => {
                let state_bytes = hex(text(field(input, "state_hex")));
                let state = validate_run_state(&projection, &state_bytes)
                    .unwrap_or_else(|error| panic!("{name}: {error:?}"));
                let advanced = advance_committed(&projection, &state);
                let expected_fields = object(
                    expected,
                    &[
                        if matches!(expected, V::Object(map) if map.contains_key("success")) {
                            "success"
                        } else {
                            "invalid_host_state"
                        },
                    ],
                );
                if let Some(success) = optional(expected_fields, "success") {
                    let success = object(success, &["state_hex"]);
                    assert_eq!(
                        encode_run_state(&advanced.unwrap()),
                        hex(text(field(success, "state_hex"))),
                        "{name}"
                    );
                } else {
                    assert!(advanced.is_err(), "{name}");
                }
            }
            "validate_run_state" => {
                let state_bytes = hex(text(field(input, "state_hex")));
                let actual = validate_run_state(&projection, &state_bytes);
                if let Some(expected) = expected_rejection(expected) {
                    assert_eq!(actual.err(), Some(expected), "{name}");
                } else {
                    assert_eq!(encode_run_state(&actual.unwrap()), state_bytes, "{name}");
                }
            }
            _ => unreachable!(),
        }
        executed += 1;
    }
    assert_eq!(executed, 46);
}

#[test]
fn maximum_support_and_run_state_boundaries_are_typed_and_bounded() {
    let stream = maximum_support_stream();
    assert_eq!(
        sha256(&stream),
        "a211f3d3cba3344b62f96b80c2759789e66a72dbc0cc517a86ca8fd1ff902c83"
    );
    let projection = stream_validation(&stream).unwrap();
    assert_eq!(projection.records().len(), 14);
    let mut cap_over = stream.clone();
    cap_over[78_030..78_032].copy_from_slice(&4097u16.to_be_bytes());
    assert_eq!(
        sha256(&cap_over),
        "144d0ad6c31afb9ca4459ac97dccf4ee0f756529cb771fd54256d52de3bbe14f"
    );
    assert_eq!(
        stream_validation(&cap_over).unwrap_err(),
        ContentReject {
            code: 26,
            raw_start: 78_030,
            raw_end: 78_032
        }
    );

    let mut committed = new_run(&projection);
    for _ in 0..61_438 {
        let (next, result) = step(&projection, committed, &[]);
        assert_eq!(result, 4);
        committed = next;
    }
    for id in 1..=4096u16 {
        let action = [1, 0, (id >> 8) as u8, id as u8];
        let (next, result) = step(&projection, committed, &action);
        assert_eq!(result, 1);
        committed = next;
    }
    let (committed, result) = step(&projection, committed, &[3, 0, 0, 0]);
    assert_eq!(result, 3);
    let committed_bytes = encode_run_state(&committed);
    assert_eq!(committed_bytes.len(), 466_958);
    assert_eq!(
        sha256(&committed_bytes),
        "db2c72090a0f01c9cde48f131f69009c3a66339a351ec75c917b75c82af5facb"
    );
    assert_eq!(
        encode_run_state(&validate_run_state(&projection, &committed_bytes).unwrap()),
        committed_bytes
    );
    let mut over = committed_bytes.clone();
    over.push(0);
    assert_eq!(
        validate_run_state(&projection, &over).unwrap_err(),
        ContentReject {
            code: 1,
            raw_start: 466_958,
            raw_end: 466_959
        }
    );

    let mut exhausted = new_run(&projection);
    for id in 1..=4096u16 {
        let action = [1, 0, (id >> 8) as u8, id as u8];
        exhausted = step(&projection, exhausted, &action).0;
    }
    for _ in 0..61_439 {
        exhausted = step(&projection, exhausted, &[]).0;
    }
    let exhausted_bytes = encode_run_state(&exhausted);
    assert_eq!(exhausted_bytes.len(), 466_955);
    assert_eq!(
        sha256(&exhausted_bytes),
        "db7f9bb5b5980599e5ace4b88cbb7841476cc01c83bb7f5a76d3b97e5d830c43"
    );
    assert_eq!(
        encode_run_state(&validate_run_state(&projection, &exhausted_bytes).unwrap()),
        exhausted_bytes
    );
    let (unchanged, result) = step(&projection, exhausted.clone(), &[3, 0, 0, 0]);
    assert_eq!(result, 9);
    assert_eq!(unchanged, exhausted);
    let mut exhausted_over = exhausted_bytes.clone();
    exhausted_over.push(0);
    assert_eq!(
        validate_run_state(&projection, &exhausted_over).unwrap_err(),
        ContentReject {
            code: 1,
            raw_start: 466_955,
            raw_end: 466_956
        }
    );

    let mut actions = Vec::with_capacity(262_144);
    for id in 1..=4096u16 {
        actions.extend_from_slice(&[1, 0, (id >> 8) as u8, id as u8]);
    }
    actions.resize(actions.len() + 61_439 * 4, 0);
    actions.extend_from_slice(&[3, 0, 0, 0]);
    assert_eq!(actions.len() / 4, 65_536);
    assert_eq!(
        sha256(&actions),
        "f73e21fa418d3720bf49fe7535ba26910061f779913ded2be610811ca6abf341"
    );
}

#[test]
fn every_non_graph_boundary_recipe_matches_receipt_and_exact_rejection() {
    let fixture = fixture();
    let top = object(&fixture, &["bases", "cases", "recipes", "schema"]);
    let excluded = [
        "patch-base",
        "maximum-support-stream",
        "maximum-selection-cap-over",
        "maximum-committed-state",
        "maximum-exhausted-state",
        "maximum-state-byte-over",
        "typed-step-sequence",
        "control-edge-boundary",
    ];
    let mut executed = 0;
    for recipe in array(field(top, "recipes")) {
        let recipe = object(
            recipe,
            &[
                "count_cap",
                "covers",
                "expected",
                "input",
                "input_bytes",
                "input_sha256",
                "name",
                "operation",
                "recipe",
            ],
        );
        let tag = text(field(recipe, "recipe"));
        if excluded.contains(&tag) {
            continue;
        }
        let input = object(
            field(recipe, "input"),
            &match tag {
                "stream-byte-cap" => vec!["byte_count"],
                "stream-bytes-boundary" => vec!["boundary", "byte_count"],
                "record-count-boundary" => vec!["boundary", "record_count"],
                "record-id-boundary" => vec!["boundary", "record_id"],
                "text-bytes-boundary" => vec![
                    "boundary",
                    if text(field(recipe, "name")).ends_with("plus-one") {
                        "declared_text_bytes"
                    } else {
                        "text_bytes"
                    },
                ],
                "per-kind-records-boundary" => vec!["boundary", "text_record_count"],
                "enum-entries-boundary" => vec!["boundary", "entry_count"],
                "vector-atoms-boundary" | "opaque-atoms-boundary" => {
                    vec!["atom_count", "boundary"]
                }
                "matrix-cells-boundary" => {
                    vec!["boundary", "cell_count", "columns", "rows"]
                }
                "field-schema-fields-boundary" => vec!["boundary", "field_count"],
                "tuple-slots-boundary" => vec!["boundary", "slot_count"],
                "regions-boundary" => vec!["boundary", "region_count"],
                "lesson-nodes-boundary" => vec!["boundary", "lesson_node_count"],
                "cases-per-node-boundary" => vec!["boundary", "case_count"],
                "record-payload-bytes-boundary" => {
                    vec!["boundary", "declared_payload_bytes"]
                }
                other => panic!("unexpected recipe {other}"),
            },
        );
        let bytes = boundary_recipe(tag, input);
        assert_eq!(bytes.len(), number(field(recipe, "input_bytes")));
        assert_eq!(
            sha256(&bytes),
            text(field(recipe, "input_sha256")),
            "{}",
            text(field(recipe, "name"))
        );
        assert_eq!(
            stream_validation(&bytes).unwrap_err(),
            expected_rejection(field(recipe, "expected")).unwrap(),
            "{}",
            text(field(recipe, "name"))
        );
        executed += 1;
    }
    assert_eq!(executed, 28);
}

#[test]
fn both_control_edge_recipes_are_bounded_before_graph_traversal() {
    let fixture = fixture();
    let top = object(&fixture, &["bases", "cases", "recipes", "schema"]);
    let mut executed = 0;
    for recipe in array(field(top, "recipes")) {
        let V::Object(recipe) = recipe else {
            panic!("recipe")
        };
        if text(field(recipe, "recipe")) != "control-edge-boundary" {
            continue;
        }
        let input = object(field(recipe, "input"), &["control_edges", "lesson_nodes"]);
        assert_eq!(number(field(input, "lesson_nodes")), 4096);
        let bytes = control_stream(number(field(input, "control_edges")) == 16385);
        assert_eq!(bytes.len(), number(field(recipe, "input_bytes")));
        assert_eq!(sha256(&bytes), text(field(recipe, "input_sha256")));
        assert_eq!(
            stream_validation(&bytes).unwrap_err(),
            expected_rejection(field(recipe, "expected")).unwrap()
        );
        executed += 1;
    }
    assert_eq!(executed, 2);
}

#[test]
fn runtime_properties_preserve_order_replay_and_terminal_immutability() {
    let fixture = fixture();
    let top = object(&fixture, &["bases", "cases", "recipes", "schema"]);
    let bytes = generic_base(top);
    let projection = stream_validation(&bytes).unwrap();
    assert_eq!(projection, stream_validation(&bytes).unwrap());

    let mut state = new_run(&projection);
    state = step(&projection, state, &[1, 0, 0, 1]).0;
    let (committed, result) = step(&projection, state, &[3, 0, 0, 0]);
    assert_eq!(result, 3);
    let mut state = advance_committed(&projection, &committed).unwrap();
    state = step(&projection, state, &[1, 0, 0, 3]).0;
    state = step(&projection, state, &[1, 0, 0, 1]).0;
    assert_eq!(state.buffer(), &[1, 3]);
    let encoded = encode_run_state(&state);
    assert_eq!(
        encode_run_state(&validate_run_state(&projection, &encoded).unwrap()),
        encoded
    );
    let committed = step(&projection, state, &[3, 0, 0, 0]).0;
    let mut sequence = advance_committed(&projection, &committed).unwrap();
    sequence = step(&projection, sequence, &[1, 0, 0, 2]).0;
    sequence = step(&projection, sequence, &[1, 0, 0, 1]).0;
    assert_eq!(sequence.buffer(), &[2, 1]);
    let committed = step(&projection, sequence, &[3, 0, 0, 0]).0;
    let before = encode_run_state(&committed);
    for raw in [vec![], vec![0, 0, 0, 0], vec![1, 0, 0, 1]] {
        let (after, result) = step(&projection, committed.clone(), &raw);
        assert_eq!(result, 8);
        assert_eq!(encode_run_state(&after), before);
    }
}

#[test]
fn production_dependency_surface_is_generic_content_only() {
    let manifest = safe_read("crates/gb-content/Cargo.toml", 4096);
    let library = safe_read("crates/gb-content/src/lib.rs", 200_000);
    for bytes in [&manifest, &library] {
        let text = std::str::from_utf8(bytes).unwrap();
        assert!(!text.contains("gb-chess"));
        assert!(!text.contains("gb_chess"));
        assert!(!text.contains("8x8"));
    }
    assert!(
        std::str::from_utf8(&manifest)
            .unwrap()
            .contains("gb-foundation")
    );
}
