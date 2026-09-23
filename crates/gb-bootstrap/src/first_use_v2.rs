//! Finite first-use coverage from observed route bytes. No source construction.
use crate::damage::ResourceProjection;
use crate::recipe_wire_v1::{decode_recipe_package_v1, evaluate_serialized_recipe_v1};
use crate::route_receiver_v2::admit_route_prefix;
use gb_foundation::{ManifestValue as V, serialize_manifest, validate_canonical_manifest};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};

const LIMIT: usize = 1_048_576;
const DEPS: [&[usize]; 12] = [
    &[],
    &[1],
    &[1],
    &[2, 3],
    &[3, 4],
    &[5],
    &[6],
    &[6, 7],
    &[6, 8],
    &[7, 8, 9],
    &[10],
    &[11],
];

#[derive(Clone, Copy)]
pub struct FirstUseInputs<'a> {
    pub prefixes: [&'a [u8]; 4],
    pub side: u16,
    pub width: u16,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum FirstUseError {
    Input,
    Route,
    Partition,
    Grounding,
    Cycle,
    Unused,
    Evidence,
}
impl std::fmt::Display for FirstUseError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "first-use-v2: {self:?}")
    }
}
impl std::error::Error for FirstUseError {}
type Result<T> = std::result::Result<T, FirstUseError>;
fn need(ok: bool, error: FirstUseError) -> Result<()> {
    if ok { Ok(()) } else { Err(error) }
}
fn uint(raw: &[u8], at: usize, width: usize) -> Result<u64> {
    let bytes = raw
        .get(at..at.checked_add(width).ok_or(FirstUseError::Partition)?)
        .ok_or(FirstUseError::Partition)?;
    need(width <= 8, FirstUseError::Partition)?;
    Ok(bytes.iter().fold(0, |n, b| (n << 8) | u64::from(*b)))
}
fn num(raw: &[u8], at: usize, width: usize) -> Result<usize> {
    usize::try_from(uint(raw, at, width)?).map_err(|_| FirstUseError::Partition)
}
fn n(value: usize) -> V {
    V::U64(value as u64)
}
fn s(value: &str) -> V {
    V::String(value.into())
}
fn row(values: impl IntoIterator<Item = usize>) -> V {
    V::Array(values.into_iter().map(n).collect())
}
fn rows(values: impl IntoIterator<Item = V>) -> V {
    V::Array(values.into_iter().collect())
}
fn object<const N: usize>(values: [(&str, V); N]) -> V {
    V::Object(values.into_iter().map(|(k, v)| (k.into(), v)).collect())
}
fn hash(raw: &[u8]) -> V {
    s(&format!("{:x}", Sha256::digest(raw)))
}
fn identity(raw: &[u8]) -> V {
    object([("bytes", n(raw.len())), ("sha256", hash(raw))])
}

struct Routes {
    rows: Vec<V>,
    examples: Vec<[usize; 7]>,
    package: Vec<u8>,
    definitions: Vec<Vec<u8>>,
}
fn observe(input: FirstUseInputs<'_>) -> Result<Routes> {
    let side = usize::from(input.side);
    let width = usize::from(input.width);
    need(
        (64..=2048).contains(&side)
            && side % 8 == 0
            && (8..=128).contains(&width)
            && width % 8 == 0
            && 2 * width + 8 <= side,
        FirstUseError::Input,
    )?;
    let mut result = Routes {
        rows: vec![],
        examples: vec![],
        package: vec![],
        definitions: vec![],
    };
    for (sector, raw) in input.prefixes.iter().enumerate() {
        need(
            (64..=32768).contains(&raw.len()) && raw.len() * 8 <= width * (side - width),
            FirstUseError::Input,
        )?;
        let admitted = admit_route_prefix(
            raw,
            input.side,
            input.width,
            sector as u8,
            &mut ResourceProjection::default(),
        )
        .map_err(|_| FirstUseError::Route)?
        .ok_or(FirstUseError::Route)?;
        if sector == 0 {
            result.package = admitted.package().encoded.clone();
            result.definitions = admitted.definitions().to_vec();
        } else {
            need(
                result.package == admitted.package().encoded
                    && result.definitions == admitted.definitions(),
                FirstUseError::Route,
            )?;
        }
        let mut at = 64;
        let mut frames = vec![];
        let mut definitions = vec![];
        let mut examples = vec![];
        let mut package_at = None;
        while at < raw.len() {
            need(frames.len() < 48, FirstUseError::Partition)?;
            let stage = num(raw, at, 1)?;
            let kind = num(raw, at + 1, 1)?;
            let id = num(raw, at + 2, 2)?;
            let size = num(raw, at + 4, 4)?;
            let end = at + 8 + size;
            need(end <= raw.len(), FirstUseError::Partition)?;
            frames.push(row([stage, kind, id, at, size + 8]));
            let p = at + 8;
            match kind {
                1 => {
                    need(size >= 14, FirstUseError::Partition)?;
                    definitions.push(row([num(raw, p, 2)?, p + 14, size - 14]));
                }
                2 | 3 => {
                    let ilen = num(raw, p + 4, 4)?;
                    let olen = num(raw, p + 8, 4)?;
                    let e = [
                        num(raw, p, 2)?,
                        num(raw, p + 2, 2)?,
                        id,
                        p + 12,
                        ilen,
                        p + 12 + ilen,
                        olen,
                    ];
                    examples.push(row(e));
                    if sector == 0 {
                        result.examples.push(e);
                    }
                }
                5 => package_at = Some(p),
                _ => {}
            }
            at = end;
        }
        need(
            frames.len() == 48 && definitions.len() == 12 && examples.len() == 33,
            FirstUseError::Partition,
        )?;
        result.rows.push(object([
            ("sector_id", n(sector)),
            ("bytes", n(raw.len())),
            ("sha256", hash(raw)),
            (
                "package_offset",
                n(package_at.ok_or(FirstUseError::Partition)?),
            ),
            ("definition_spans", rows(definitions)),
            ("frame_spans", rows(frames)),
            ("example_spans", rows(examples)),
        ]));
    }
    Ok(result)
}

struct Layout {
    start: usize,
    pairs: Vec<(usize, usize)>,
}
#[derive(Clone)]
struct Node {
    recipe: usize,
    index: usize,
    value: usize,
    start: usize,
    length: usize,
    opcode: usize,
    kind: usize,
    width: usize,
    args: Vec<[usize; 4]>,
    aux: Vec<usize>,
    immediate: Option<(usize, u64)>,
}
impl Node {
    fn manifest(&self) -> V {
        V::Array(vec![
            n(self.recipe),
            n(self.index),
            n(self.value),
            n(self.start),
            n(self.length),
            n(self.opcode),
            n(self.kind),
            n(self.width),
            rows(self.args.iter().copied().map(row)),
            row(self.aux.clone()),
            self.immediate
                .map_or_else(|| row([]), |(at, v)| V::Array(vec![n(at), V::U64(v)])),
        ])
    }
}
struct Scan {
    layouts: Vec<Layout>,
    fields: Vec<V>,
    tables: Vec<[usize; 8]>,
    recipes: Vec<[usize; 6]>,
    descriptors: Vec<[usize; 8]>,
    nodes: Vec<Node>,
    calls: Vec<[usize; 3]>,
}
fn fields(
    out: &mut Vec<V>,
    layouts: &[Layout],
    layout: usize,
    owner: usize,
    item: usize,
    start: usize,
) {
    for (i, (at, width)) in layouts[layout].pairs.iter().enumerate() {
        out.push(row([
            layout,
            owner,
            item,
            i,
            start + at,
            *width,
            layouts[layout].start + 2 + 4 * i,
        ]));
    }
}
fn scan(raw: &[u8], definitions: &[Vec<u8>]) -> Result<Scan> {
    let mut out = Scan {
        layouts: vec![],
        fields: vec![],
        tables: vec![],
        recipes: vec![],
        descriptors: vec![],
        nodes: vec![],
        calls: vec![],
    };
    let mut at = 0;
    for size in [32, 8, 64, 16, 32, 12] {
        let start = at;
        let count = num(&definitions[4], at, 2)?;
        at += 2;
        need((1..=32).contains(&count), FirstUseError::Partition)?;
        let mut pairs = vec![];
        let mut end = 0;
        for _ in 0..count {
            let pos = num(&definitions[4], at, 2)?;
            let width = num(&definitions[4], at + 2, 2)?;
            at += 4;
            need(pos == end && width > 0, FirstUseError::Partition)?;
            end += width;
            pairs.push((pos, width));
        }
        need(end == size, FirstUseError::Partition)?;
        out.layouts.push(Layout { start, pairs });
    }
    fields(&mut out.fields, &out.layouts, 2, 0, 0, 0);
    let table_count = num(raw, 18, 2)?;
    let recipe_count = num(raw, 16, 2)?;
    need(
        table_count <= 256 && recipe_count <= 256 && raw.len() <= 32768,
        FirstUseError::Input,
    )?;
    at = 64;
    for _ in 0..table_count {
        let id = num(raw, at, 2)?;
        let payload = num(raw, at + 12, 4)?;
        out.tables.push([
            id,
            at,
            16 + payload,
            at + 16,
            payload,
            num(raw, at + 2, 1)?,
            num(raw, at + 4, 4)?,
            num(raw, at + 8, 4)?,
        ]);
        fields(&mut out.fields, &out.layouts, 3, id, 0, at);
        at += 16 + payload;
    }
    for _ in 0..recipe_count {
        let start = at;
        let id = num(raw, at, 2)?;
        let ni = num(raw, at + 4, 2)?;
        let no = num(raw, at + 6, 2)?;
        let nn = num(raw, at + 8, 4)?;
        let size = num(raw, at + 28, 4)?;
        need(
            nn <= 4096 && out.nodes.len() + nn <= 4096 && ni <= 4096 && no <= 4096,
            FirstUseError::Input,
        )?;
        out.recipes.push([id, start, size, ni, no, nn]);
        fields(&mut out.fields, &out.layouts, 4, id, 0, start);
        at += 32;
        let mut values = BTreeMap::new();
        let mut outputs = BTreeMap::new();
        for (io, count) in [ni, no].into_iter().enumerate() {
            for index in 1..=count {
                out.descriptors.push([
                    id,
                    io,
                    index,
                    num(raw, at, 2)?,
                    at,
                    num(raw, at + 2, 1)?,
                    num(raw, at + 4, 4)?,
                    num(raw, at + 8, 4)?,
                ]);
                fields(&mut out.fields, &out.layouts, 5, id, index + io * 65536, at);
                if io == 0 {
                    values.insert(index, (at, 12));
                } else {
                    outputs.insert(index, (at, 12));
                }
                at += 12;
            }
        }
        for index in 1..=nn {
            let node_start = at;
            let opcode = num(raw, at, 1)?;
            let kind = num(raw, at + 1, 1)?;
            let width = num(raw, at + 2, 4)?;
            need(
                (1..=25).contains(&opcode) && kind <= 5,
                FirstUseError::Partition,
            )?;
            let shape = &definitions[5][(opcode - 1) * 6..opcode * 6];
            let arity = usize::from(shape[1]);
            let ab = shape[3];
            let ib = shape[4];
            need(
                arity <= 3 && matches!(ab, 0 | 2) && matches!(ib, 0 | 8),
                FirstUseError::Partition,
            )?;
            at += 6;
            let mut args = vec![];
            for _ in 0..arity {
                let value = num(raw, at, 2)?;
                let &(pos, len) = values.get(&value).ok_or(FirstUseError::Grounding)?;
                args.push([value, at, pos, len]);
                at += 2;
            }
            let mut aux = vec![];
            let mut immediate = None;
            if ab != 0 {
                let target = num(raw, at, 2)?;
                let (pos, len) = match opcode {
                    2 => {
                        let t = out
                            .tables
                            .iter()
                            .find(|t| t[0] == target)
                            .ok_or(FirstUseError::Grounding)?;
                        (t[1], t[2])
                    }
                    5 => *outputs.get(&target).ok_or(FirstUseError::Grounding)?,
                    22 => {
                        need(target < id, FirstUseError::Grounding)?;
                        let r = out
                            .recipes
                            .iter()
                            .find(|r| r[0] == target)
                            .ok_or(FirstUseError::Grounding)?;
                        out.calls.push([id, index, target]);
                        (r[1], r[2])
                    }
                    _ => return Err(FirstUseError::Partition),
                };
                aux = vec![target, at, pos, len];
                at += 2;
            }
            if ib != 0 {
                immediate = Some((at, uint(raw, at, 8)?));
                at += 8;
            }
            need(
                at - node_start == usize::from(shape[5]),
                FirstUseError::Partition,
            )?;
            out.nodes.push(Node {
                recipe: id,
                index,
                value: ni + index,
                start: node_start,
                length: at - node_start,
                opcode,
                kind,
                width,
                args,
                aux,
                immediate,
            });
            values.insert(ni + index, (node_start, at - node_start));
        }
        need(at == start + size, FirstUseError::Partition)?;
    }
    need(
        at == raw.len() && out.fields.len() <= 65536,
        FirstUseError::Partition,
    )?;
    Ok(out)
}

fn opcode_order(deps: &BTreeMap<usize, BTreeSet<usize>>) -> Result<Vec<usize>> {
    need(
        deps.values().flatten().all(|d| deps.contains_key(d)),
        FirstUseError::Grounding,
    )?;
    let mut done: Vec<usize> = vec![];
    while done.len() < deps.len() {
        let id = deps
            .iter()
            .find(|(id, ds)| !done.contains(id) && ds.iter().all(|d| done.contains(d)))
            .map(|(id, _)| *id)
            .ok_or(FirstUseError::Cycle)?;
        done.push(id);
    }
    Ok(done)
}
fn anchor(scan: &Scan, value: usize, ni: usize) -> Result<[usize; 2]> {
    if value <= ni {
        return Ok([0, value]);
    }
    let node = scan
        .nodes
        .iter()
        .find(|n| n.recipe == 211 && n.value == value)
        .ok_or(FirstUseError::Grounding)?;
    match node.opcode {
        1 => return Ok([1, node.index]),
        2 => return Ok([2, node.aux[0]]),
        25 => return Ok([4, node.index]),
        _ => {}
    }
    let mut slots = vec![];
    for emit in scan.nodes.iter().filter(|n| {
        n.recipe == 211
            && n.opcode == 5
            && n.args[0][0] == value
            && n.immediate.map(|i| i.1) == Some(0)
    }) {
        let slot = emit.aux[0];
        let descriptor = scan
            .descriptors
            .iter()
            .find(|d| d[0] == 211 && d[1] == 1 && d[2] == slot)
            .ok_or(FirstUseError::Grounding)?;
        if descriptor[5] == node.kind && descriptor[6] == node.width {
            slots.push(slot);
        }
    }
    Ok([3, *slots.iter().min().ok_or(FirstUseError::Grounding)?])
}
fn grounding(scan: &Scan) -> Result<BTreeMap<String, V>> {
    let ni = scan
        .recipes
        .iter()
        .find(|r| r[0] == 211)
        .ok_or(FirstUseError::Grounding)?[3];
    let mut dependencies: BTreeMap<usize, BTreeSet<usize>> =
        (1..=25).map(|op| (op, BTreeSet::new())).collect();
    let mut witnesses: BTreeMap<usize, Vec<usize>> = (1..=25).map(|op| (op, vec![])).collect();
    let mut literal = vec![];
    let mut copies = vec![];
    for node in scan.nodes.iter().filter(|n| n.recipe == 211) {
        witnesses.get_mut(&node.opcode).unwrap().push(node.index);
        if node.opcode == 5 {
            if node.args[0][0] <= ni {
                copies.push([
                    node.index,
                    node.args[0][0],
                    node.aux[0],
                    node.immediate.unwrap().1 as usize,
                ]);
            }
            continue;
        }
        let args: Vec<_> = node
            .args
            .iter()
            .map(|a| anchor(scan, a[0], ni))
            .collect::<Result<_>>()?;
        let result = anchor(scan, node.value, ni)?;
        let deps = dependencies.get_mut(&node.opcode).unwrap();
        if result[0] == 3 {
            deps.insert(5);
        }
        for a in &args {
            match a[0] {
                1 => {
                    deps.insert(1);
                }
                2 => {
                    deps.insert(2);
                }
                4 => {
                    deps.insert(25);
                }
                _ => {}
            }
        }
        if node.opcode == 22 {
            let mut pending = vec![node.aux[0]];
            let mut visited = BTreeSet::new();
            while let Some(id) = pending.pop() {
                if !visited.insert(id) {
                    continue;
                }
                for child in scan.nodes.iter().filter(|n| n.recipe == id) {
                    deps.insert(child.opcode);
                    if child.opcode == 22 {
                        pending.push(child.aux[0]);
                    }
                }
            }
        }
        literal.push(V::Array(vec![
            n(node.index),
            n(node.opcode),
            rows(args.into_iter().map(row)),
            row(result),
        ]));
    }
    need(
        copies
            == [
                [70, 1, 33, 0],
                [71, 2, 33, 8],
                [72, 4, 34, 0],
                [73, 4, 34, 3],
            ],
        FirstUseError::Grounding,
    )?;
    for node in scan.nodes.iter().filter(|n| n.recipe == 213) {
        dependencies.get_mut(&22).unwrap().insert(node.opcode);
    }
    dependencies.get_mut(&25).unwrap().extend([1, 5]);
    need(
        witnesses.values().all(|v| !v.is_empty()),
        FirstUseError::Grounding,
    )?;
    let order = opcode_order(&dependencies)?;
    Ok([
        ("literal_rows".into(), rows(literal)),
        ("copy_rows".into(), rows(copies.into_iter().map(row))),
        ("opcode_order".into(), row(order)),
        (
            "type_rows".into(),
            rows((0..6).map(|t| row([t, 150 + 10 * t, 10]))),
        ),
        (
            "opcode_rows".into(),
            rows((1..=25).map(|op| {
                V::Array(vec![
                    n(op),
                    n(6 * (op - 1)),
                    row(dependencies[&op].iter().copied()),
                    row(witnesses[&op].clone()),
                ])
            })),
        ),
    ]
    .into_iter()
    .collect())
}
fn closure(scan: &Scan, root: usize) -> Result<(BTreeSet<usize>, BTreeSet<usize>)> {
    let mut recipes = BTreeSet::new();
    let mut tables = BTreeSet::new();
    let mut pending = vec![root];
    while let Some(id) = pending.pop() {
        need(
            scan.recipes.iter().any(|r| r[0] == id),
            FirstUseError::Grounding,
        )?;
        if !recipes.insert(id) {
            continue;
        }
        for node in scan.nodes.iter().filter(|n| n.recipe == id) {
            match node.opcode {
                2 => {
                    tables.insert(node.aux[0]);
                }
                22 => pending.push(node.aux[0]),
                _ => {}
            }
        }
    }
    Ok((recipes, tables))
}
fn uses(scan: &Scan, routes: &Routes) -> Result<(V, V)> {
    let mut roots = vec![];
    let mut conventions = vec![];
    for fact in 1..=12 {
        let examples: Vec<_> = routes.examples.iter().filter(|e| e[0] == fact).collect();
        need(
            !examples.is_empty() && DEPS[fact - 1].iter().all(|p| *p < fact),
            FirstUseError::Grounding,
        )?;
        conventions.push(V::Array(vec![
            n(fact),
            row(DEPS[fact - 1].iter().copied()),
            n(routes.definitions[fact - 1].len()),
            row(examples.iter().map(|e| e[2])),
        ]));
        for e in examples {
            if !roots.contains(&(fact, e[1])) {
                roots.push((fact, e[1]));
            }
        }
        if fact == 10 {
            roots.push((fact, num(&routes.definitions[9], 158, 2)?));
        }
        if fact == 8 {
            roots.push((8, 108));
        }
    }
    roots.extend([30, 109, 113, 202].map(|id| (0, id)));
    let mut all_recipes = BTreeSet::new();
    let mut all_tables = BTreeSet::from([17]);
    let mut use_rows = vec![];
    for (fact, id) in roots {
        let (recipes, tables) = closure(scan, id)?;
        use_rows.push(V::Array(vec![
            n(fact),
            n(id),
            row(recipes.iter().copied()),
            row(tables.iter().copied()),
        ]));
        all_recipes.extend(recipes);
        all_tables.extend(tables);
    }
    need(
        all_recipes == scan.recipes.iter().map(|r| r[0]).collect()
            && all_tables == scan.tables.iter().map(|t| t[0]).collect(),
        FirstUseError::Unused,
    )?;
    let types: BTreeSet<_> = scan
        .nodes
        .iter()
        .map(|n| n.kind)
        .chain(scan.descriptors.iter().map(|d| d[5]))
        .collect();
    need(types == (0..6).collect(), FirstUseError::Unused)?;
    Ok((rows(use_rows), rows(conventions)))
}
fn adapters(routes: &Routes) -> Result<V> {
    let package = decode_recipe_package_v1(&routes.package, 8).map_err(|_| FirstUseError::Route)?;
    let mut result = vec![];
    for (block, base) in [134, 325].into_iter().enumerate() {
        for lane in 0..24 {
            let segments = if lane < 23 {
                vec![[7, base + 8 * lane, 8]]
            } else {
                vec![[7, base + 184, 7], [8, 15, 1]]
            };
            let input: Vec<u8> = segments
                .iter()
                .flat_map(|[fact, at, len]| {
                    routes.definitions[fact - 1][*at..at + len].iter().copied()
                })
                .collect();
            let offset = 112 + 216 * block + 9 * lane;
            let expected = &routes.definitions[7][offset..offset + 9];
            let actual = evaluate_serialized_recipe_v1(&package, 108, &input)
                .map_err(|_| FirstUseError::Grounding)?;
            need(
                actual.len() == 11 && actual[..2] == [0, 0] && actual[2..] == *expected,
                FirstUseError::Grounding,
            )?;
            result.push(V::Array(vec![
                n(8),
                n(108),
                n(block),
                n(lane),
                rows(segments.into_iter().map(row)),
                row([8, offset, 9]),
            ]));
        }
    }
    Ok(rows(result))
}

fn literal_copy(source: &[u8], kind: usize, destination: &[u8], offset: usize) -> Result<()> {
    need(kind == 3 || offset % 8 == 0, FirstUseError::Grounding)?;
    let start = if kind == 3 { offset } else { offset / 8 };
    let end = start
        .checked_add(source.len())
        .ok_or(FirstUseError::Grounding)?;
    need(
        destination.get(start..end) == Some(source),
        FirstUseError::Grounding,
    )
}
fn literal_constraints(prefix: &[u8], scan: &Scan, routes: &Routes) -> Result<()> {
    let chunks = |io, mut start| -> Result<BTreeMap<usize, (&[u8], usize)>> {
        let mut result = BTreeMap::new();
        for d in scan
            .descriptors
            .iter()
            .filter(|d| d[0] == 211 && d[1] == io)
        {
            let size = if d[5] == 3 { d[6] } else { d[6].div_ceil(8) };
            let raw = prefix
                .get(start..start + size)
                .ok_or(FirstUseError::Grounding)?;
            result.insert(d[2], (raw, d[5]));
            start += size;
        }
        Ok(result)
    };
    for example in routes.examples.iter().filter(|e| matches!(e[2], 602 | 603)) {
        let inputs = chunks(0, example[3])?;
        let outputs = chunks(1, example[5])?;
        for node in scan
            .nodes
            .iter()
            .filter(|n| n.recipe == 211 && n.opcode == 5 && n.args[0][0] <= 5)
        {
            let (raw, kind) = inputs[&node.args[0][0]];
            literal_copy(
                raw,
                kind,
                outputs[&node.aux[0]].0,
                node.immediate.unwrap().1 as usize,
            )?;
        }
        need(outputs[&1].0 == [0, 0], FirstUseError::Grounding)?;
    }
    let failure = routes
        .examples
        .iter()
        .find(|e| e[1] == 212)
        .ok_or(FirstUseError::Grounding)?;
    need(
        failure[4] == 0
            && failure[6] == 2
            && prefix.get(failure[5]..failure[5] + 2) == Some(&[0, 4]),
        FirstUseError::Grounding,
    )?;
    let p: Vec<_> = scan.nodes.iter().filter(|n| n.recipe == 212).collect();
    need(
        p.len() == 4 && p.iter().map(|n| n.opcode).collect::<Vec<_>>() == [1, 5, 25, 5],
        FirstUseError::Grounding,
    )?;
    need(
        p[0].immediate.map(|i| i.1) == Some(7)
            && p[1].args[0][0] == 1
            && p[1].aux[0] == 2
            && p[1].immediate.map(|i| i.1) == Some(0)
            && p[2].immediate.map(|i| i.1) == Some(4)
            && p[3].args[0][0] == 3
            && p[3].aux[0] == 1
            && p[3].immediate.map(|i| i.1) == Some(0),
        FirstUseError::Grounding,
    )
}

/// Generate complete finite coverage. Caller provenance is an external binding.
pub fn build_first_use_v2(input: FirstUseInputs<'_>) -> Result<Vec<u8>> {
    let routes = observe(input)?;
    let scan = scan(&routes.package, &routes.definitions)?;
    literal_constraints(input.prefixes[0], &scan, &routes)?;
    let mut value = grounding(&scan)?;
    let (uses, conventions) = uses(&scan, &routes)?;
    value.insert("use_rows".into(), uses);
    value.insert("convention_rows".into(), conventions);
    value.insert("adapter_rows".into(), adapters(&routes)?);
    let table = scan
        .tables
        .iter()
        .find(|t| t[0] == 17)
        .ok_or(FirstUseError::Grounding)?;
    let index = usize::from((input.side - 2 * input.width) / 8);
    need(
        table[5..] == [0, 8, 256] && index < table[7],
        FirstUseError::Grounding,
    )?;
    value.insert(
        "mapping_use".into(),
        row([
            9,
            17,
            index,
            table[3] + index,
            usize::from(routes.package[table[3] + index]),
            0,
            464,
        ]),
    );
    value.insert("schema".into(), s("golden-board.m2-first-use/v2"));
    value.insert(
        "scope".into(),
        s("finite-carried-convention-coverage-development"),
    );
    value.insert(
        "inputs".into(),
        object([
            ("side", n(usize::from(input.side))),
            ("shell_width", n(usize::from(input.width))),
            ("package", identity(&routes.package)),
        ]),
    );
    value.insert("route_rows".into(), rows(routes.rows));
    value.insert(
        "layout_rows".into(),
        rows(scan.layouts.iter().enumerate().map(|(i, l)| {
            V::Array(vec![
                n(i),
                n(l.start),
                rows(l.pairs.iter().map(|(at, width)| row([*at, *width]))),
            ])
        })),
    );
    value.insert(
        "table_rows".into(),
        rows(scan.tables.iter().copied().map(row)),
    );
    value.insert(
        "recipe_rows".into(),
        rows(scan.recipes.iter().copied().map(row)),
    );
    value.insert(
        "descriptor_rows".into(),
        rows(scan.descriptors.iter().copied().map(row)),
    );
    value.insert(
        "node_rows".into(),
        rows(scan.nodes.iter().map(Node::manifest)),
    );
    value.insert(
        "call_rows".into(),
        rows(scan.calls.iter().copied().map(row)),
    );
    let length = |key: &str| match &value[key] {
        V::Array(v) => v.len(),
        _ => 0,
    };
    let summary = object([
        ("result", s("pass")),
        ("route_count", n(4)),
        ("package_bytes", n(routes.package.len())),
        ("field_count", n(scan.fields.len())),
        ("node_count", n(scan.nodes.len())),
        (
            "constant_count",
            n(scan.nodes.iter().filter(|n| n.immediate.is_some()).count()),
        ),
        ("table_count", n(scan.tables.len())),
        ("recipe_count", n(scan.recipes.len())),
        ("opcode_count", n(length("opcode_rows"))),
        ("literal_count", n(length("literal_rows"))),
        ("copy_count", n(length("copy_rows"))),
    ]);
    value.insert("field_rows".into(), rows(scan.fields));
    value.insert("summary".into(), summary);
    let raw = serialize_manifest(&V::Object(value)).map_err(|_| FirstUseError::Evidence)?;
    need(raw.len() <= LIMIT, FirstUseError::Evidence)?;
    Ok(raw)
}
pub fn validate_first_use_v2(raw: &[u8], input: FirstUseInputs<'_>) -> Result<()> {
    need(raw.len() <= LIMIT, FirstUseError::Evidence)?;
    validate_canonical_manifest(raw).map_err(|_| FirstUseError::Evidence)?;
    need(raw == build_first_use_v2(input)?, FirstUseError::Evidence)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn missing_and_circular_definitions_never_receive_a_topological_order() {
        let ordered = BTreeMap::from([(1, BTreeSet::new()), (2, BTreeSet::from([1]))]);
        assert_eq!(opcode_order(&ordered).unwrap(), vec![1, 2]);
        for bad in [
            BTreeMap::from([(1, BTreeSet::from([2]))]),
            BTreeMap::from([(1, BTreeSet::from([2])), (2, BTreeSet::from([1]))]),
            BTreeMap::from([(1, BTreeSet::from([1]))]),
        ] {
            assert!(opcode_order(&bad).is_err());
        }
    }
    #[test]
    fn copied_literal_bits_and_bytes_are_checked_without_a_vm() {
        assert!(literal_copy(&[6], 0, &[0, 6], 8).is_ok());
        assert!(literal_copy(b"abc", 3, b"abcabc", 3).is_ok());
        assert!(literal_copy(&[6], 0, &[0, 7], 8).is_err());
        assert!(literal_copy(&[6], 0, &[0, 6], 1).is_err());
        assert!(literal_copy(b"abc", 3, b"abca", 3).is_err());
    }
}
