//! Source-intent assessment, independently checked against recovered lesson cells.
use crate::recovery_provenance_v2::RecoveryProvenanceV2;
use gb_chess as chess;
use gb_content::{RecordPayload as P, Region};
use gb_foundation::{ManifestValue as V, serialize_manifest, validate_canonical_manifest};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;

const CONTENT_SHA: &str = "141168a051b44f978667f7c562070300d79368ace3fee47f5d19082de7642c17";
const FIXTURE_SHA: &str = "9a63aa74a32761bf1f8919278e895f532e4d4f305a30f74ddd1d0c4acec6a639";
const GAMES_SHA: &str = "e883055cd0417061cf04d596cbca75d039948a987180d26a80bd6d6888f4764e";
const IDENTITIES: [(&str, &str, &str); 12] = [
    ("final-grid", "grid", "occupancy"),
    ("final-turn", "turn", "transition"),
    ("final-sliding", "sliding", "transition"),
    ("final-knight", "knight", "transition"),
    ("final-capture", "capture", "transition"),
    ("final-control", "attack", "control"),
    ("final-castling", "castling", "transition"),
    ("final-en-passant", "en_passant", "transition"),
    ("final-self-check", "self_check", "transition"),
    ("final-promotion", "promotion", "transition"),
    ("final-history", "history", "history"),
    ("final-game", "game", "record_transition"),
];
const LITERAL_PATHS: [&str; 8] = [
    "recipient/READ-ME.txt",
    "recipient/index.html",
    "recipient/layout.js",
    "recipient/ui.js",
    "recipient/viewer.js",
    "recipient/learner_runner.py",
    "recipient/learner_runner_v1.py",
    "owner/READ-ME.txt",
];

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum LearnerBundleError {
    Input,
    Source,
    Chess,
    Content,
    Picture,
    Result,
}
impl std::fmt::Display for LearnerBundleError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "learner-bundle-v2: {self:?}")
    }
}
impl std::error::Error for LearnerBundleError {}
type Result<T> = std::result::Result<T, LearnerBundleError>;
fn require(ok: bool, error: LearnerBundleError) -> Result<()> {
    if ok { Ok(()) } else { Err(error) }
}
fn hash(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}
fn hex(raw: &[u8]) -> String {
    raw.iter().map(|b| format!("{b:02x}")).collect()
}
fn unhex(text: &str) -> Result<Vec<u8>> {
    require(
        text.len() <= 256
            && text.len().is_multiple_of(4)
            && text
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
        LearnerBundleError::Source,
    )?;
    text.as_bytes()
        .chunks_exact(2)
        .map(|b| {
            let text = std::str::from_utf8(b).map_err(|_| LearnerBundleError::Source)?;
            u8::from_str_radix(text, 16).map_err(|_| LearnerBundleError::Source)
        })
        .collect()
}
fn s(value: impl Into<String>) -> V {
    V::String(value.into())
}
fn n(value: usize) -> V {
    V::U64(value as u64)
}
fn object<const N: usize>(rows: [(&str, V); N]) -> V {
    V::Object(rows.into_iter().map(|(k, v)| (k.into(), v)).collect())
}
fn numbers(values: &[u8]) -> V {
    V::Array(values.iter().map(|v| n(*v as usize)).collect())
}
fn field<'a>(value: &'a V, key: &str) -> Result<&'a V> {
    match value {
        V::Object(o) => o.get(key).ok_or(LearnerBundleError::Source),
        _ => Err(LearnerBundleError::Source),
    }
}
fn string(value: &V) -> Result<&str> {
    if let V::String(v) = value {
        Ok(v)
    } else {
        Err(LearnerBundleError::Source)
    }
}
fn array(value: &V) -> Result<&[V]> {
    if let V::Array(v) = value {
        Ok(v)
    } else {
        Err(LearnerBundleError::Source)
    }
}

/// Literals are README, four browser sources, two runner sources, owner README.
#[derive(Clone, Copy)]
pub struct LearnerBundleSourcesV2<'a> {
    pub intent: &'a [u8],
    pub chess_fixture: &'a [u8],
    pub game_set: &'a [u8],
    pub literals: [&'a [u8]; 8],
}
impl Default for LearnerBundleSourcesV2<'static> {
    fn default() -> Self {
        Self {
            intent: include_bytes!("../../../studies/m2/learner-assessment-v2.toml"),
            chess_fixture: include_bytes!("../../../conformance/chess-v0.json"),
            game_set: include_bytes!("../../../reports/game-set-v0.bin"),
            literals: [
                include_bytes!("../../../studies/m2/templates/learner/instructions-v1.txt"),
                include_bytes!("../../../tools/m2/learner_web/index.html"),
                include_bytes!("../../../tools/m2/learner_web/layout.js"),
                include_bytes!("../../../tools/m2/learner_web/ui.js"),
                include_bytes!("../../../tools/m2/learner_web/viewer.js"),
                include_bytes!("../../../tools/m2/learner_runner.py"),
                include_bytes!("../../../tools/m2/learner_runner_v1.py"),
                include_bytes!("../../../studies/m2/templates/learner/owner-instructions-v2.txt"),
            ],
        }
    }
}

struct Question {
    id: String,
    family: String,
    kind: String,
    ordinal: usize,
    prefix_kind: String,
    prefix_value: String,
    prefix_plies: usize,
    suffix: String,
    options: Vec<String>,
    reverse: bool,
}
fn questions(raw: &[u8]) -> Result<Vec<Question>> {
    require(
        !raw.is_empty() && raw.len() <= 16384,
        LearnerBundleError::Input,
    )?;
    let text = std::str::from_utf8(raw).map_err(|_| LearnerBundleError::Input)?;
    let value: toml::Value = toml::from_str(text).map_err(|_| LearnerBundleError::Input)?;
    let root = value.as_table().ok_or(LearnerBundleError::Input)?;
    require(
        root.len() == 2
            && root.get("schema").and_then(toml::Value::as_str)
                == Some("golden-board.m2-learner-assessment-source/v2"),
        LearnerBundleError::Source,
    )?;
    let rows = root
        .get("questions")
        .and_then(toml::Value::as_array)
        .ok_or(LearnerBundleError::Source)?;
    require(rows.len() == 12, LearnerBundleError::Source)?;
    rows.iter()
        .enumerate()
        .map(|(i, row)| {
            let q = row.as_table().ok_or(LearnerBundleError::Source)?;
            let keys = [
                "id",
                "family",
                "kind",
                "page_ordinal",
                "prefix_kind",
                "prefix_value",
                "prefix_plies",
                "suffix",
                "option_moves",
                "reverse",
            ];
            require(
                q.len() == keys.len() && keys.iter().all(|k| q.contains_key(*k)),
                LearnerBundleError::Source,
            )?;
            let st = |key| -> Result<String> {
                let v = q
                    .get(key)
                    .and_then(toml::Value::as_str)
                    .ok_or(LearnerBundleError::Source)?;
                require(v.is_ascii() && v.len() <= 256, LearnerBundleError::Source)?;
                Ok(v.into())
            };
            let num = |key| -> Result<usize> {
                usize::try_from(
                    q.get(key)
                        .and_then(toml::Value::as_integer)
                        .ok_or(LearnerBundleError::Source)?,
                )
                .map_err(|_| LearnerBundleError::Source)
            };
            let values = q["option_moves"]
                .as_array()
                .ok_or(LearnerBundleError::Source)?;
            require(values.len() <= 2, LearnerBundleError::Source)?;
            let options = values
                .iter()
                .map(|v| {
                    let v = v.as_str().ok_or(LearnerBundleError::Source)?;
                    require(v.len() <= 5 && v.is_ascii(), LearnerBundleError::Source)?;
                    Ok(v.to_string())
                })
                .collect::<Result<Vec<_>>>()?;
            let out = Question {
                id: st("id")?,
                family: st("family")?,
                kind: st("kind")?,
                ordinal: num("page_ordinal")?,
                prefix_kind: st("prefix_kind")?,
                prefix_value: st("prefix_value")?,
                prefix_plies: num("prefix_plies")?,
                suffix: st("suffix")?,
                options,
                reverse: q["reverse"].as_bool().ok_or(LearnerBundleError::Source)?,
            };
            require(
                out.ordinal == 53 + i
                    && out.prefix_plies <= 64
                    && (out.id.as_str(), out.family.as_str(), out.kind.as_str()) == IDENTITIES[i],
                LearnerBundleError::Source,
            )?;
            Ok(out)
        })
        .collect()
}
fn line(text: &str) -> Result<Vec<u8>> {
    let tokens: Vec<_> = text.split_whitespace().collect();
    require(tokens.len() <= 64, LearnerBundleError::Source)?;
    let mut raw = vec![];
    for token in tokens {
        let b = token.as_bytes();
        require(
            (b.len() == 4 || b.len() == 5)
                && (b'a'..=b'h').contains(&b[0])
                && (b'1'..=b'8').contains(&b[1])
                && (b'a'..=b'h').contains(&b[2])
                && (b'1'..=b'8').contains(&b[3]),
            LearnerBundleError::Source,
        )?;
        let p = if b.len() == 4 {
            0
        } else {
            match b[4] {
                b'q' => 1,
                b'r' => 2,
                b'b' => 3,
                b'n' => 4,
                _ => return Err(LearnerBundleError::Source),
            }
        };
        let a = (b[0] - b'a') as u16 + 8 * (b[1] - b'1') as u16;
        let d = (b[2] - b'a') as u16 + 8 * (b[3] - b'1') as u16;
        let wire = ((a << 10) | (d << 4) | (p << 1)).to_be_bytes();
        chess::decode_move(&wire).map_err(|_| LearnerBundleError::Chess)?;
        raw.extend(wire);
    }
    Ok(raw)
}
fn moves(raw: &[u8]) -> Result<Vec<chess::Move>> {
    require(raw.len().is_multiple_of(2), LearnerBundleError::Source)?;
    raw.chunks_exact(2)
        .map(|b| chess::decode_move(b).map_err(|_| LearnerBundleError::Chess))
        .collect()
}
fn replay(raw: &[u8]) -> Result<chess::ReplayState> {
    chess::replay_from_start(&moves(raw)?).map_err(|_| LearnerBundleError::Chess)
}
fn game(raw: &[u8]) -> Result<&[u8]> {
    require(raw.starts_with(&[0, 64]), LearnerBundleError::Source)?;
    let mut at = 2;
    let mut total = 0;
    let mut previous: &[u8] = &[];
    let mut first = &[][..];
    for i in 0..64 {
        let header = raw.get(at..at + 2).ok_or(LearnerBundleError::Source)?;
        let count = u16::from_be_bytes([header[0], header[1]]) as usize;
        total += count;
        require(
            (1..=4096).contains(&count) && total <= 65535,
            LearnerBundleError::Source,
        )?;
        let end = at + 3 + 2 * count;
        let record = raw.get(at..end).ok_or(LearnerBundleError::Source)?;
        require(
            record[record.len() - 1] <= 2 && (i == 0 || previous < record),
            LearnerBundleError::Source,
        )?;
        if i == 0 {
            first = record;
        }
        previous = record;
        at = end;
    }
    require(at == raw.len(), LearnerBundleError::Source)?;
    let score =
        chess::Score::from_code(first[first.len() - 1]).ok_or(LearnerBundleError::Source)?;
    chess::validate_source_record(&moves(&first[2..first.len() - 1])?, score)
        .map_err(|_| LearnerBundleError::Chess)?;
    Ok(first)
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct Matrix {
    rows: usize,
    cols: usize,
    cells: Vec<u8>,
}
fn matrix(rows: usize, cols: usize, cells: Vec<u8>) -> Matrix {
    debug_assert_eq!(rows * cols, cells.len());
    Matrix { rows, cols, cells }
}
fn board(raw: &[u8; 67]) -> Matrix {
    let mut cells = vec![];
    for r in (0..8).rev() {
        cells.extend(&raw[r * 8..r * 8 + 8]);
    }
    cells.extend([255; 8]);
    cells.extend(&raw[64..]);
    cells.extend([255; 5]);
    matrix(10, 8, cells)
}
fn mask(values: &[u8]) -> Matrix {
    let mut cells = vec![];
    for r in (0..8).rev() {
        cells.extend(&values[r * 8..r * 8 + 8]);
    }
    matrix(8, 8, cells)
}
fn compose(mut panels: Vec<Matrix>, options: &[Matrix]) -> (P, Vec<Region>) {
    let rows = options.iter().map(|p| p.rows).max().unwrap();
    let cols = options.iter().map(|p| p.cols).sum::<usize>() + 1;
    let mut choice = matrix(rows, cols, vec![255; rows * cols]);
    let mut regions = vec![];
    let mut left = 0;
    for (i, p) in options.iter().enumerate() {
        for r in 0..p.rows {
            choice.cells[r * cols + left..r * cols + left + p.cols]
                .copy_from_slice(&p.cells[r * p.cols..(r + 1) * p.cols]);
        }
        regions.push(Region {
            region_id: (i + 1) as u16,
            label_ref: 0,
            row_start: 0,
            row_end: p.rows as u16,
            column_start: left as u16,
            column_end: (left + p.cols) as u16,
            flags: 1,
        });
        left += p.cols + 1;
    }
    panels.push(choice);
    let (mut top, mut left, mut height, mut width) = (0, 0, 0, 0);
    let mut positions = vec![];
    for p in &panels {
        if left > 0 && left + p.cols > 36 {
            top += height + 2;
            left = 0;
            height = 0;
        }
        positions.push((top, left));
        width = width.max(left + p.cols);
        height = height.max(p.rows);
        left += p.cols + 2;
    }
    let rows = top + height;
    let mut cells = vec![255u32; rows * width];
    for (p, (top, left)) in panels.iter().zip(&positions) {
        for r in 0..p.rows {
            for col in 0..p.cols {
                cells[(top + r) * width + left + col] = p.cells[r * p.cols + col] as u32;
            }
        }
    }
    let (top, left) = positions[positions.len() - 1];
    for r in &mut regions {
        r.row_start += top as u16;
        r.row_end += top as u16;
        r.column_start += left as u16;
        r.column_end += left as u16;
    }
    (
        P::Matrix {
            atom_schema_ref: 1,
            rows: rows as u16,
            columns: width as u16,
            cells,
        },
        regions,
    )
}
fn move_fields(raw: &[u8]) -> (usize, usize, u8) {
    let v = u16::from_be_bytes([raw[0], raw[1]]);
    (
        (v >> 10) as usize,
        ((v >> 4) & 63) as usize,
        ((v >> 1) & 7) as u8,
    )
}
fn proposed(before: &[u8; 67], mv: &[u8]) -> [u8; 67] {
    let (origin, dest, promotion) = move_fields(mv);
    let mut raw = *before;
    let code = before[origin];
    let kind = if code == 0 { 0 } else { (code - 1) % 6 + 1 };
    let side = if code == 0 {
        before[64]
    } else {
        (code - 1) / 6
    };
    raw[origin] = 0;
    raw[dest] = code;
    raw[64] ^= 1;
    raw[66] = 0;
    if kind == 1 {
        if before[dest] == 0
            && before[66] as usize == dest + 1
            && (origin % 8).abs_diff(dest % 8) == 1
        {
            raw[(origin / 8) * 8 + dest % 8] = 0;
        }
        if origin % 8 == dest % 8 && (origin / 8).abs_diff(dest / 8) == 2 {
            raw[66] = ((origin + dest) / 2 + 1) as u8;
        }
        if promotion != 0 {
            raw[dest] = 6 * side + [0, 5, 4, 3, 2][promotion as usize];
        }
    }
    if kind == 6 {
        raw[65] &= if side == 0 { 12 } else { 3 };
        let pair = match (origin, dest) {
            (4, 6) => Some((7, 5)),
            (4, 2) => Some((0, 3)),
            (60, 62) => Some((63, 61)),
            (60, 58) => Some((56, 59)),
            _ => None,
        };
        if let Some((a, b)) = pair {
            raw[a] = 0;
            raw[b] = before[a];
        }
    }
    for (square, bit, rook) in [(7, 1, 4), (0, 2, 4), (63, 4, 10), (56, 8, 10)] {
        if (origin == square && code == rook) || (dest == square && before[square] == rook) {
            raw[65] &= 15 ^ bit;
        }
    }
    raw
}
struct Derived {
    matrix: P,
    regions: Vec<Region>,
    correct: Vec<V>,
    evidence: V,
}
fn derive(q: &Question, fixture: &V, game: &[u8], game_set: &[u8]) -> Result<Derived> {
    let mut prefix = match q.prefix_kind.as_str() {
        "literal" => {
            require(q.prefix_plies == 0, LearnerBundleError::Source)?;
            line(&q.prefix_value)?
        }
        "fixture" => {
            require(q.prefix_plies == 0, LearnerBundleError::Source)?;
            let cases = array(field(fixture, "cases")?)?;
            let selected = cases
                .iter()
                .filter(|v| {
                    field(v, "name")
                        .and_then(string)
                        .is_ok_and(|s| s == q.prefix_value)
                })
                .collect::<Vec<_>>();
            require(selected.len() == 1, LearnerBundleError::Source)?;
            unhex(string(field(field(selected[0], "input")?, "moves_hex")?)?)?
        }
        "game" => {
            require(
                q.prefix_value.is_empty() && q.prefix_plies <= (game.len() - 3) / 2,
                LearnerBundleError::Source,
            )?;
            game[2..2 + q.prefix_plies * 2].to_vec()
        }
        _ => return Err(LearnerBundleError::Source),
    };
    prefix.extend(line(&q.suffix)?);
    require(prefix.len() <= 128, LearnerBundleError::Source)?;
    let state = replay(&prefix)?;
    let before = chess::encode_position(state.position());
    let mut ev = BTreeMap::from([
        ("kind".into(), s(&q.kind)),
        ("prefix_hex".into(), s(hex(&prefix))),
        ("before_hex".into(), s(hex(&before))),
    ]);
    let mut panels = vec![board(&before)];
    let mut options = vec![];
    let mut accepted = vec![];
    if q.kind == "transition" || q.kind == "record_transition" {
        let mut option_moves = q
            .options
            .iter()
            .map(|m| line(m))
            .collect::<Result<Vec<_>>>()?;
        require(
            option_moves.iter().all(|v| v.len() == 2),
            LearnerBundleError::Source,
        )?;
        let mut record_move = vec![];
        if q.kind == "record_transition" {
            require(
                q.prefix_kind == "game"
                    && q.suffix.is_empty()
                    && option_moves.len() == 1
                    && q.prefix_plies < (game.len() - 3) / 2,
                LearnerBundleError::Source,
            )?;
            record_move = game[2 + prefix.len()..4 + prefix.len()].to_vec();
            option_moves.insert(0, record_move.clone());
            if q.reverse {
                option_moves.reverse();
            }
        } else {
            require(
                option_moves.len() == 2 && !q.reverse,
                LearnerBundleError::Source,
            )?;
        }
        require(
            option_moves[0] != option_moves[1],
            LearnerBundleError::Source,
        )?;
        let mut facts = vec![];
        let mut outcomes = vec![];
        for (i, wire) in option_moves.iter().enumerate() {
            let mv = chess::decode_move(wire).map_err(|_| LearnerBundleError::Chess)?;
            let mut fact = BTreeMap::from([
                ("region_id".into(), n(i + 1)),
                ("move_hex".into(), s(hex(wire))),
            ]);
            let after = match chess::apply_move(&state, mv) {
                Ok(next) => {
                    let p = chess::encode_position(next.position());
                    fact.insert("legal".into(), V::Bool(true));
                    fact.insert("after_hex".into(), s(hex(&p)));
                    accepted.push(true);
                    p
                }
                Err(error) => {
                    let p = proposed(&before, wire);
                    fact.insert("legal".into(), V::Bool(false));
                    fact.insert("rejection".into(), n(error.code as usize));
                    fact.insert("proposed_hex".into(), s(hex(&p)));
                    accepted.push(false);
                    p
                }
            };
            options.push(board(&after));
            outcomes.push(after);
            facts.push(V::Object(fact));
        }
        ev.insert("options".into(), V::Array(facts));
        if q.kind == "record_transition" {
            require(
                accepted.iter().all(|v| *v) && outcomes[0][64..] == outcomes[1][64..],
                LearnerBundleError::Chess,
            )?;
            accepted = option_moves.iter().map(|m| m == &record_move).collect();
            let (a, b, p) = move_fields(&record_move);
            panels.insert(
                0,
                matrix(
                    2,
                    3,
                    vec![record_move[0], record_move[1], 255, a as u8, b as u8, p],
                ),
            );
            panels.insert(0, matrix(1, 1, vec![245]));
            ev.extend([
                ("game_path".into(), s("reports/game-set-v0.bin")),
                ("game_set_sha256".into(), s(hash(game_set))),
                ("game_sha256".into(), s(hash(game))),
                ("game_ordinal".into(), n(0)),
                ("ply_index".into(), n(q.prefix_plies)),
                ("record_move_hex".into(), s(hex(&record_move))),
                (
                    "record_diagram".into(),
                    object([
                        ("wire_bytes", numbers(&record_move)),
                        ("origin", n(a)),
                        ("destination", n(b)),
                        ("promotion", n(p as usize)),
                    ]),
                ),
            ]);
        }
    } else {
        require(q.options.is_empty(), LearnerBundleError::Source)?;
        match q.kind.as_str() {
            "occupancy" => {
                let mut values = vec![];
                for sq in 0..64 {
                    let value = chess::evaluate_predicate(
                        b"chess.occupancy",
                        chess::PredicateInput::Occupancy(
                            state.position().clone(),
                            chess::Square::from_index(sq).unwrap(),
                            chess::OccupancyMatch::Occupied,
                        ),
                    )
                    .map_err(|_| LearnerBundleError::Chess)?;
                    let chess::PredicateResult::Bool(value) = value else {
                        return Err(LearnerBundleError::Chess);
                    };
                    values.push(u8::from(value));
                }
                ev.insert("mask".into(), numbers(&values));
                panels.insert(0, matrix(1, 1, vec![253]));
                options = vec![
                    mask(&values),
                    mask(&values.iter().map(|v| 1 - v).collect::<Vec<_>>()),
                ];
                accepted = vec![true, false];
            }
            "control" => {
                let values = (0..64)
                    .map(|sq| {
                        u8::from(
                            !chess::controls_square(
                                state.position(),
                                chess::Side::FIRST,
                                chess::Square::from_index(sq).unwrap(),
                            )
                            .is_empty(),
                        )
                    })
                    .collect::<Vec<_>>();
                let mut legal = vec![0; 64];
                for mv in chess::legal_moves(&state) {
                    let (_, b, _) = move_fields(&chess::encode_move(mv));
                    legal[b] = 1;
                }
                require(values != legal, LearnerBundleError::Chess)?;
                ev.extend([
                    ("side".into(), n(0)),
                    ("control_mask".into(), numbers(&values)),
                    ("legal_destination_mask".into(), numbers(&legal)),
                ]);
                panels.insert(0, matrix(1, 6, vec![1, 2, 3, 4, 5, 6]));
                panels.insert(0, matrix(1, 1, vec![254]));
                options = vec![mask(&values), mask(&legal)];
                accepted = vec![true, false];
            }
            "history" => {
                let positions = (0..=prefix.len())
                    .step_by(2)
                    .map(|n| Ok(chess::encode_position(replay(&prefix[..n])?.position())))
                    .collect::<Result<Vec<_>>>()?;
                let rows = positions.len().div_ceil(3) * 12 - 1;
                let mut story = matrix(rows, 26, vec![255; rows * 26]);
                for (i, p) in positions.iter().enumerate() {
                    let (top, left) = (i / 3 * 12, i % 3 * 9);
                    story.cells[top * 26 + left] = i as u8;
                    let b = board(p);
                    for r in 0..10 {
                        let at = (top + 1 + r) * 26 + left;
                        story.cells[at..at + 8].copy_from_slice(&b.cells[r * 8..r * 8 + 8]);
                    }
                }
                let result = chess::evaluate_predicate(
                    b"chess.history_claim",
                    chess::PredicateInput::History(state.clone()),
                )
                .map_err(|_| LearnerBundleError::Chess)?;
                let chess::PredicateResult::History(h) = result else {
                    return Err(LearnerBundleError::Chess);
                };
                ev.extend([
                    ("occurrences".into(), n(h.current_key_occurrences as usize)),
                    ("threefold_available".into(), V::Bool(h.threefold_available)),
                    (
                        "positions_hex".into(),
                        V::Array(positions.iter().map(|p| s(hex(p))).collect()),
                    ),
                ]);
                panels = vec![matrix(1, 1, vec![247]), story, board(&before)];
                options = vec![matrix(1, 1, vec![0]), matrix(1, 1, vec![1])];
                accepted = vec![!h.threefold_available, h.threefold_available];
            }
            _ => return Err(LearnerBundleError::Source),
        }
        if q.reverse {
            options.reverse();
            accepted.reverse();
        }
    }
    require(
        accepted.iter().any(|v| *v) && options[0] != options[1],
        LearnerBundleError::Chess,
    )?;
    let correct = accepted
        .iter()
        .enumerate()
        .filter_map(|(i, v)| v.then_some(n(i + 1)))
        .collect();
    let (matrix, regions) = compose(panels, &options);
    Ok(Derived {
        matrix,
        regions,
        correct,
        evidence: V::Object(ev),
    })
}

pub fn build_learner_assessment_v2(
    required: &[u8],
    intent: &[u8],
    chess_fixture: &[u8],
    game_set: &[u8],
) -> Result<Vec<u8>> {
    require(
        required.len() == 42432 && hash(required) == CONTENT_SHA,
        LearnerBundleError::Content,
    )?;
    require(
        !chess_fixture.is_empty()
            && chess_fixture.len() <= 2097152
            && !game_set.is_empty()
            && game_set.len() <= 327677,
        LearnerBundleError::Input,
    )?;
    require(
        hash(chess_fixture) == FIXTURE_SHA && hash(game_set) == GAMES_SHA,
        LearnerBundleError::Source,
    )?;
    let questions = questions(intent)?;
    let fixture =
        validate_canonical_manifest(chess_fixture).map_err(|_| LearnerBundleError::Source)?;
    let game = game(game_set)?;
    let projection =
        gb_content::stream_validation(required).map_err(|_| LearnerBundleError::Content)?;
    let view = gb_content::projection_view(&projection);
    let encoded = gb_content::encode_content_v0(
        &gb_content::authoring_from_validated(&view).map_err(|_| LearnerBundleError::Content)?,
    )
    .map_err(|_| LearnerBundleError::Content)?;
    require(
        encoded == required && view.root_record_id() == 588,
        LearnerBundleError::Content,
    )?;
    let records = view
        .records()
        .iter()
        .map(|r| (r.record_id(), r.payload()))
        .collect::<BTreeMap<_, _>>();
    let nodes = view
        .records()
        .iter()
        .filter(|r| matches!(r.payload(), P::LessonNode { .. }))
        .collect::<Vec<_>>();
    require(nodes.len() == 65, LearnerBundleError::Content)?;
    require(
        records[&588]
            == &P::Root {
                entry_node_ref: nodes[0].record_id(),
                global_event_budget: 4160,
            },
        LearnerBundleError::Content,
    )?;
    let mut counts = [0usize; 4];
    for node in &nodes {
        let P::LessonNode {
            role,
            response_shape,
            answer_mode,
            flags,
            max_selections,
            item_event_budget,
            ..
        } = node.payload()
        else {
            unreachable!()
        };
        require((1..=3).contains(answer_mode), LearnerBundleError::Content)?;
        counts[*answer_mode as usize] += 1;
        require(
            *role == if *answer_mode == 3 { 3 } else { 5 }
                && *response_shape == 1
                && *flags == 0
                && *max_selections == 1
                && *item_event_budget == 16,
            LearnerBundleError::Content,
        )?;
    }
    require(counts == [0, 7, 12, 46], LearnerBundleError::Content)?;
    let mut pages = vec![];
    for q in questions {
        let node = nodes[q.ordinal];
        let P::LessonNode {
            answer_mode,
            presentation_ref,
            region_set_ref,
            predicate_result_ref,
            passive_trace_ref,
            cases,
            default_feedback_ref,
            default_next_node_ref,
            ..
        } = node.payload()
        else {
            unreachable!()
        };
        let next = nodes.get(q.ordinal + 1).map_or(0, |n| n.record_id());
        require(
            *answer_mode == 2
                && *predicate_result_ref == 0
                && *passive_trace_ref == 0
                && cases.is_empty()
                && *default_next_node_ref == next,
            LearnerBundleError::Content,
        )?;
        require(
            records[default_feedback_ref]
                == &P::Feedback {
                    feedback_code: 1,
                    display_ref: *presentation_ref,
                    predicate_result_ref: 0,
                },
            LearnerBundleError::Content,
        )?;
        let d = derive(&q, &fixture, game, game_set)?;
        require(
            records[presentation_ref] == &d.matrix
                && records[region_set_ref]
                    == &P::RegionSet {
                        surface_matrix_ref: *presentation_ref,
                        regions: d.regions,
                    },
            LearnerBundleError::Picture,
        )?;
        pages.push(object([
            ("id", s(q.id)),
            ("family", s(q.family)),
            ("phase", s("heldout")),
            ("node_id", n(node.record_id() as usize)),
            ("surface_matrix_id", n(*presentation_ref as usize)),
            ("region_set_id", n(*region_set_ref as usize)),
            ("correct", V::Array(d.correct)),
            ("evidence", d.evidence),
        ]));
    }
    serialize_manifest(&object([
        ("schema", s("golden-board.m2-lesson-owner/v2")),
        ("assessment_source_sha256", s(hash(intent))),
        ("content_sha256", s(hash(required))),
        ("content_bytes", n(required.len())),
        ("root_id", n(588)),
        ("pages", V::Array(pages)),
        ("local_budget", n(16)),
        ("global_budget", n(4160)),
    ]))
    .map_err(|_| LearnerBundleError::Result)
}
pub fn validate_learner_assessment_v2(
    raw: &[u8],
    required: &[u8],
    intent: &[u8],
    fixture: &[u8],
    game_set: &[u8],
) -> Result<()> {
    validate_canonical_manifest(raw).map_err(|_| LearnerBundleError::Result)?;
    require(
        raw == build_learner_assessment_v2(required, intent, fixture, game_set)?,
        LearnerBundleError::Result,
    )
}
fn base64(raw: &[u8]) -> String {
    const DIGITS: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(raw.len().div_ceil(3) * 4);
    for b in raw.chunks(3) {
        let v = ((b[0] as u32) << 16)
            | ((b.get(1).copied().unwrap_or(0) as u32) << 8)
            | b.get(2).copied().unwrap_or(0) as u32;
        out.push(DIGITS[((v >> 18) & 63) as usize] as char);
        out.push(DIGITS[((v >> 12) & 63) as usize] as char);
        out.push(if b.len() > 1 {
            DIGITS[((v >> 6) & 63) as usize] as char
        } else {
            '='
        });
        out.push(if b.len() > 2 {
            DIGITS[(v & 63) as usize] as char
        } else {
            '='
        });
    }
    out
}
pub fn build_learner_bundle_v2(
    recovered: &RecoveryProvenanceV2,
    sources: LearnerBundleSourcesV2<'_>,
) -> Result<BTreeMap<String, Vec<u8>>> {
    let required = recovered.required_stream();
    let assessment = build_learner_assessment_v2(
        required,
        sources.intent,
        sources.chess_fixture,
        sources.game_set,
    )?;
    let locked = LearnerBundleSourcesV2::default();
    let mut files = BTreeMap::new();
    for (i, path) in LITERAL_PATHS.iter().enumerate() {
        let raw = sources.literals[i];
        require(
            !raw.is_empty()
                && raw.len() <= 262144
                && std::str::from_utf8(raw).is_ok()
                && raw == locked.literals[i],
            LearnerBundleError::Source,
        )?;
        files.insert((*path).into(), raw.to_vec());
    }
    let mut metadata = serialize_manifest(&object([
        ("schema", s("golden-board.learner-prototype-data/v0")),
        ("content_base64", s(base64(required))),
        ("content_bytes", n(required.len())),
        ("content_sha256", s(hash(required))),
        ("root_id", n(588)),
    ]))
    .map_err(|_| LearnerBundleError::Result)?;
    require(metadata.pop() == Some(b'\n'), LearnerBundleError::Result)?;
    let mut js = b"globalThis.LESSON_DATA = ".to_vec();
    js.extend(metadata);
    js.extend(b";\n");
    files.insert("recipient/lesson-data.js".into(), js);
    files.insert("recipient/lesson.content-v0.bin".into(), required.to_vec());
    files.insert("owner/semantic-evaluation.json".into(), assessment);
    Ok(files)
}
