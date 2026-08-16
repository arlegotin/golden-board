use gb_foundation::constants::*;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ChessReject {
    pub code: u16,
}
type Result<T> = std::result::Result<T, ChessReject>;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct WirePosition {
    bytes: [u8; 67],
}

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub struct Move(u16);

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Event {
    kind: EventKind,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum EventKind {
    Move(Move),
    Resignation(Side),
    DrawAgreement,
    ClaimThreefold,
    ClaimFiftyMove,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Score {
    FirstWin,
    SecondWin,
    Draw,
}
impl Score {
    pub fn code(self) -> u8 {
        match self {
            Self::FirstWin => SCORE_FIRST_WIN,
            Self::SecondWin => SCORE_SECOND_WIN,
            Self::Draw => SCORE_DRAW,
        }
    }
    pub fn from_code(code: u8) -> Option<Self> {
        match code {
            SCORE_FIRST_WIN => Some(Self::FirstWin),
            SCORE_SECOND_WIN => Some(Self::SecondWin),
            SCORE_DRAW => Some(Self::Draw),
            _ => None,
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub struct Side(u8);

impl Side {
    pub const FIRST: Self = Self(SIDE_FIRST);
    pub const SECOND: Self = Self(SIDE_SECOND);

    pub fn from_code(code: u8) -> Option<Self> {
        match code {
            SIDE_FIRST => Some(Self::FIRST),
            SIDE_SECOND => Some(Self::SECOND),
            _ => None,
        }
    }

    pub fn code(self) -> u8 {
        self.0
    }
}

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub struct Square(u8);

impl Square {
    pub fn from_index(index: u8) -> Option<Self> {
        (index < CHESS_SQUARE_COUNT as u8).then_some(Self(index))
    }

    pub fn index(self) -> u8 {
        self.0
    }
}

fn side(code: u8) -> Side {
    Side(code)
}

fn square(index: u8) -> Square {
    Square(index)
}

fn reject(code: u16) -> ChessReject {
    ChessReject { code }
}

pub fn decode_position(bytes: &[u8]) -> Result<WirePosition> {
    if bytes.len() != CHESS_POSITION_BYTES as usize {
        return Err(reject(CHESS_POSITION_LENGTH));
    }
    for &square in &bytes[..64] {
        if square > SQUARE_SECOND_KING {
            return Err(reject(CHESS_POSITION_SQUARE_CODE));
        }
    }
    if bytes[64] != SIDE_FIRST && bytes[64] != SIDE_SECOND {
        return Err(reject(CHESS_POSITION_SIDE_CODE));
    }
    let all_castling = CASTLING_FIRST_KINGSIDE
        | CASTLING_FIRST_QUEENSIDE
        | CASTLING_SECOND_KINGSIDE
        | CASTLING_SECOND_QUEENSIDE;
    if bytes[65] & !all_castling != 0 {
        return Err(reject(CHESS_POSITION_CASTLING_RESERVED));
    }
    if bytes[66] > 64 {
        return Err(reject(CHESS_POSITION_EN_PASSANT_CODE));
    }
    let mut out = [0; 67];
    out.copy_from_slice(bytes);
    Ok(WirePosition { bytes: out })
}
pub fn encode_position(position: &WirePosition) -> [u8; 67] {
    position.bytes
}

pub fn decode_move(bytes: &[u8]) -> Result<Move> {
    if bytes.len() != 2 {
        return Err(reject(CHESS_MOVE_LENGTH));
    }
    let value = u16::from_be_bytes([bytes[0], bytes[1]]);
    let value32 = value as u32;
    if value32 & CHESS_MOVE_RESERVED_MASK != 0 {
        return Err(reject(CHESS_MOVE_RESERVED));
    }
    let promotion = ((value32 & CHESS_MOVE_PROMOTION_MASK) >> CHESS_MOVE_PROMOTION_SHIFT) as u8;
    if !matches!(
        promotion,
        PROMOTION_NONE | PROMOTION_QUEEN | PROMOTION_ROOK | PROMOTION_BISHOP | PROMOTION_KNIGHT
    ) {
        return Err(reject(CHESS_MOVE_PROMOTION_CODE));
    }
    if (value32 & CHESS_MOVE_ORIGIN_MASK) >> CHESS_MOVE_ORIGIN_SHIFT
        == (value32 & CHESS_MOVE_DESTINATION_MASK) >> CHESS_MOVE_DESTINATION_SHIFT
    {
        return Err(reject(CHESS_MOVE_SAME_SQUARE));
    }
    Ok(Move(value))
}
pub fn encode_move(mv: Move) -> [u8; 2] {
    mv.0.to_be_bytes()
}

pub fn decode_event(bytes: &[u8]) -> Result<Event> {
    let Some(&tag) = bytes.first() else {
        return Err(reject(CHESS_EVENT_LENGTH));
    };
    let (event, n) = match tag {
        EVENT_MOVE => {
            if bytes.len() < 3 {
                return Err(reject(CHESS_EVENT_LENGTH));
            }
            (
                Event {
                    kind: EventKind::Move(decode_move(&bytes[1..3])?),
                },
                3,
            )
        }
        EVENT_RESIGNATION => {
            if bytes.len() < 2 {
                return Err(reject(CHESS_EVENT_LENGTH));
            }
            if !matches!(bytes[1], SIDE_FIRST | SIDE_SECOND) {
                return Err(reject(CHESS_EVENT_SIDE_CODE));
            }
            (
                Event {
                    kind: EventKind::Resignation(side(bytes[1])),
                },
                2,
            )
        }
        EVENT_DRAW_AGREEMENT => (
            Event {
                kind: EventKind::DrawAgreement,
            },
            1,
        ),
        EVENT_CLAIM_THREEFOLD => (
            Event {
                kind: EventKind::ClaimThreefold,
            },
            1,
        ),
        EVENT_CLAIM_50_MOVE => (
            Event {
                kind: EventKind::ClaimFiftyMove,
            },
            1,
        ),
        _ => return Err(reject(CHESS_EVENT_CODE)),
    };
    if bytes.len() != n {
        return Err(reject(CHESS_EVENT_TRAILING));
    }
    Ok(event)
}
pub fn encode_event(event: Event) -> Vec<u8> {
    match event.kind {
        EventKind::Move(m) => {
            let b = encode_move(m);
            vec![EVENT_MOVE, b[0], b[1]]
        }
        EventKind::Resignation(s) => vec![EVENT_RESIGNATION, s.code()],
        EventKind::DrawAgreement => vec![EVENT_DRAW_AGREEMENT],
        EventKind::ClaimThreefold => vec![EVENT_CLAIM_THREEFOLD],
        EventKind::ClaimFiftyMove => vec![EVENT_CLAIM_50_MOVE],
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct LocallyAdmissiblePosition {
    wire: WirePosition,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ReplayState {
    position: WirePosition,
    moves: Vec<Move>,
    keys: Vec<[u8; 67]>,
    halfmove: u16,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum BoardTerminal {
    None,
    Checkmate(Side),
    Stalemate,
    CommonDead,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum BoardClosure {
    Checkmate(Side),
    Stalemate,
    CommonDead,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ClosureCause {
    Board(BoardClosure),
    Resignation(Side),
    DrawAgreement,
    ClaimThreefold,
    ClaimFiftyMove,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct GameState {
    replay: ReplayState,
    status: u8,
    cause: Option<ClosureCause>,
    score: Option<Score>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RecordResult {
    pub final_replay: ReplayState,
    pub score: Score,
    pub board_terminal: BoardTerminal,
    pub threefold_available: bool,
    pub fifty_move_available: bool,
}

impl ReplayState {
    pub fn position(&self) -> &WirePosition {
        &self.position
    }
    pub fn played_plies(&self) -> usize {
        self.moves.len()
    }
    pub fn halfmove_clock(&self) -> u16 {
        self.halfmove
    }
    pub fn nominal_en_passant(&self) -> Option<Square> {
        self.position.bytes[66].checked_sub(1).map(square)
    }
    pub fn current_key_occurrences(&self) -> u16 {
        let k = repetition_key(self);
        self.keys.iter().filter(|x| **x == k).count() as u16
    }
    pub fn threefold_available(&self) -> bool {
        self.current_key_occurrences() as u32 >= CHESS_THREEFOLD_OCCURRENCES
    }
    pub fn fifty_move_available(&self) -> bool {
        self.halfmove as u32 >= CHESS_FIFTY_MOVE_PLIES
    }
}
impl GameState {
    pub fn replay(&self) -> &ReplayState {
        &self.replay
    }
    pub fn status(&self) -> u8 {
        self.status
    }
    pub fn closure_cause(&self) -> Option<ClosureCause> {
        self.cause
    }
    pub fn score(&self) -> Option<Score> {
        self.score
    }
}
impl BoardTerminal {
    pub fn code(self) -> u8 {
        match self {
            Self::None => BOARD_TERMINAL_NONE,
            Self::Checkmate(_) => BOARD_TERMINAL_CHECKMATE,
            Self::Stalemate => BOARD_TERMINAL_STALEMATE,
            Self::CommonDead => BOARD_TERMINAL_COMMON_DEAD,
        }
    }
}

fn piece_side(code: u8) -> Option<u8> {
    match code {
        1..=6 => Some(SIDE_FIRST),
        7..=12 => Some(SIDE_SECOND),
        _ => None,
    }
}
fn piece_kind(code: u8) -> u8 {
    match code {
        1 | 7 => 1,
        2 | 8 => 2,
        3 | 9 => 3,
        4 | 10 => 4,
        5 | 11 => 5,
        6 | 12 => 6,
        _ => 0,
    }
}
fn code(side: u8, kind: u8) -> u8 {
    if side == SIDE_FIRST { kind } else { kind + 6 }
}
fn file(s: u8) -> i8 {
    (s % 8) as i8
}
fn rank(s: u8) -> i8 {
    (s / 8) as i8
}
fn sq(f: i8, r: i8) -> Option<u8> {
    if (0..8).contains(&f) && (0..8).contains(&r) {
        Some((r * 8 + f) as u8)
    } else {
        None
    }
}
fn origin(m: Move) -> u8 {
    ((m.0 as u32 & CHESS_MOVE_ORIGIN_MASK) >> CHESS_MOVE_ORIGIN_SHIFT) as u8
}
fn destination(m: Move) -> u8 {
    ((m.0 as u32 & CHESS_MOVE_DESTINATION_MASK) >> CHESS_MOVE_DESTINATION_SHIFT) as u8
}
fn promotion(m: Move) -> u8 {
    ((m.0 as u32 & CHESS_MOVE_PROMOTION_MASK) >> CHESS_MOVE_PROMOTION_SHIFT) as u8
}
fn make_move(a: u8, b: u8, p: u8) -> Move {
    Move(((a as u16) << 10) | ((b as u16) << 4) | ((p as u16) << 1))
}

pub fn validate_local(wire: &WirePosition) -> Result<LocallyAdmissiblePosition> {
    let b = &wire.bytes;
    for (side, error) in [
        (SIDE_FIRST, CHESS_LOCAL_FIRST_KING_COUNT),
        (SIDE_SECOND, CHESS_LOCAL_SECOND_KING_COUNT),
    ] {
        if b[..64].iter().filter(|&&x| x == code(side, 6)).count() != 1 {
            return Err(reject(error));
        }
    }
    for (side, error) in [
        (SIDE_FIRST, CHESS_LOCAL_FIRST_PAWN_COUNT),
        (SIDE_SECOND, CHESS_LOCAL_SECOND_PAWN_COUNT),
    ] {
        if b[..64].iter().filter(|&&x| x == code(side, 1)).count() > CHESS_MAX_SIDE_PAWNS as usize {
            return Err(reject(error));
        }
    }
    for (side, error) in [
        (SIDE_FIRST, CHESS_LOCAL_FIRST_PIECE_COUNT),
        (SIDE_SECOND, CHESS_LOCAL_SECOND_PIECE_COUNT),
    ] {
        if b[..64]
            .iter()
            .filter(|&&x| piece_side(x) == Some(side))
            .count()
            > CHESS_MAX_SIDE_PIECES as usize
        {
            return Err(reject(error));
        }
    }
    for s in 0..64 {
        if piece_kind(b[s]) == 1 && (s < 8 || s >= 56) {
            return Err(reject(CHESS_LOCAL_PAWN_ON_LAST_RANK));
        }
    }
    let k1 = b[..64]
        .iter()
        .position(|&x| x == code(SIDE_FIRST, 6))
        .unwrap() as u8;
    let k2 = b[..64]
        .iter()
        .position(|&x| x == code(SIDE_SECOND, 6))
        .unwrap() as u8;
    if (file(k1) - file(k2)).abs() <= 1 && (rank(k1) - rank(k2)).abs() <= 1 {
        return Err(reject(CHESS_LOCAL_KINGS_ADJACENT));
    }
    let c1 = !controls_square_raw(wire, SIDE_SECOND, k1).is_empty();
    let c2 = !controls_square_raw(wire, SIDE_FIRST, k2).is_empty();
    if c1 && c2 {
        return Err(reject(CHESS_LOCAL_BOTH_KINGS_CHECKED));
    }
    let inactive = if b[64] == SIDE_FIRST {
        SIDE_SECOND
    } else {
        SIDE_FIRST
    };
    if (inactive == SIDE_FIRST && c1) || (inactive == SIDE_SECOND && c2) {
        return Err(reject(CHESS_LOCAL_INACTIVE_KING_CHECKED));
    }
    for (bit, side, ks, rs, e) in [
        (
            CASTLING_FIRST_KINGSIDE,
            SIDE_FIRST,
            4,
            7,
            CHESS_LOCAL_CASTLING_FIRST_KINGSIDE,
        ),
        (
            CASTLING_FIRST_QUEENSIDE,
            SIDE_FIRST,
            4,
            0,
            CHESS_LOCAL_CASTLING_FIRST_QUEENSIDE,
        ),
        (
            CASTLING_SECOND_KINGSIDE,
            SIDE_SECOND,
            60,
            63,
            CHESS_LOCAL_CASTLING_SECOND_KINGSIDE,
        ),
        (
            CASTLING_SECOND_QUEENSIDE,
            SIDE_SECOND,
            60,
            56,
            CHESS_LOCAL_CASTLING_SECOND_QUEENSIDE,
        ),
    ] {
        if b[65] & bit != 0 && (b[ks] != code(side, 6) || b[rs] != code(side, 4)) {
            return Err(reject(e));
        }
    }
    if b[66] != 0 {
        let t = b[66] - 1;
        let side = b[64];
        let wanted_rank = if side == SIDE_FIRST { 5 } else { 2 };
        if rank(t) != wanted_rank {
            return Err(reject(CHESS_LOCAL_EN_PASSANT_RANK));
        }
        if b[t as usize] != 0 {
            return Err(reject(CHESS_LOCAL_EN_PASSANT_TARGET_OCCUPIED));
        }
        let pawn_sq = (t as i16 + if side == SIDE_FIRST { -8 } else { 8 }) as usize;
        if b[pawn_sq] != code(1 - side, 1) {
            return Err(reject(CHESS_LOCAL_EN_PASSANT_PAWN));
        }
        let old = (t as i16 + if side == SIDE_FIRST { 8 } else { -8 }) as usize;
        if b[old] != 0 {
            return Err(reject(CHESS_LOCAL_EN_PASSANT_ORIGIN_OCCUPIED));
        }
    }
    Ok(LocallyAdmissiblePosition { wire: wire.clone() })
}

fn controls_from(w: &WirePosition, from: u8, to: u8) -> bool {
    let pc = w.bytes[from as usize];
    let side = match piece_side(pc) {
        Some(x) => x,
        None => return false,
    };
    let df = file(to) - file(from);
    let dr = rank(to) - rank(from);
    let kind = piece_kind(pc);
    match kind {
        1 => dr == if side == SIDE_FIRST { 1 } else { -1 } && df.abs() == 1,
        2 => matches!((df.abs(), dr.abs()), (1, 2) | (2, 1)),
        6 => df.abs() <= 1 && dr.abs() <= 1 && (df != 0 || dr != 0),
        3 | 4 | 5 => {
            let diag = df.abs() == dr.abs() && df != 0;
            let straight = (df == 0) ^ (dr == 0);
            if !((kind == 3 && diag)
                || (kind == 4 && straight)
                || (kind == 5 && (diag || straight)))
            {
                return false;
            }
            let sf = df.signum();
            let sr = dr.signum();
            let (mut f, mut r) = (file(from) + sf, rank(from) + sr);
            while let Some(s) = sq(f, r) {
                if s == to {
                    return true;
                }
                if w.bytes[s as usize] != 0 {
                    return false;
                }
                f += sf;
                r += sr
            }
            false
        }
        _ => false,
    }
}
fn controls_square_raw(w: &WirePosition, side: u8, target: u8) -> Vec<u8> {
    let mut v = Vec::new();
    for s in 0..64u8 {
        if piece_side(w.bytes[s as usize]) == Some(side) && controls_from(w, s, target) {
            v.push(s)
        }
    }
    v
}
pub fn controls_square(w: &WirePosition, side: Side, target: Square) -> Vec<Square> {
    controls_square_raw(w, side.code(), target.index())
        .into_iter()
        .map(square)
        .collect()
}
fn king_in_check_raw(p: &LocallyAdmissiblePosition, side: u8) -> bool {
    let k = p.wire.bytes[..64]
        .iter()
        .position(|&x| x == code(side, 6))
        .unwrap() as u8;
    !controls_square_raw(&p.wire, 1 - side, k).is_empty()
}
pub fn king_in_check(p: &LocallyAdmissiblePosition, side: Side) -> bool {
    king_in_check_raw(p, side.code())
}

fn pseudo_for(w: &WirePosition, from: u8) -> Vec<Move> {
    let mut out = Vec::new();
    let pc = w.bytes[from as usize];
    let Some(side) = piece_side(pc) else {
        return out;
    };
    if side != w.bytes[64] {
        return out;
    }
    let k = piece_kind(pc);
    let mut add = |to: u8, p: u8| {
        if piece_side(w.bytes[to as usize]) != Some(side) {
            out.push(make_move(from, to, p))
        }
    };
    match k {
        2 => {
            for (df, dr) in [
                (1, 2),
                (2, 1),
                (-1, 2),
                (-2, 1),
                (1, -2),
                (2, -1),
                (-1, -2),
                (-2, -1),
            ] {
                if let Some(t) = sq(file(from) + df, rank(from) + dr) {
                    add(t, 0)
                }
            }
        }
        6 => {
            for df in -1..=1 {
                for dr in -1..=1 {
                    if df != 0 || dr != 0 {
                        if let Some(t) = sq(file(from) + df, rank(from) + dr) {
                            if piece_kind(w.bytes[t as usize]) != 6 {
                                add(t, 0)
                            }
                        }
                    }
                }
            }
            for (to, bit, rook, path) in if side == 0 {
                [
                    (6, CASTLING_FIRST_KINGSIDE, 7, &[5u8, 6][..]),
                    (2, CASTLING_FIRST_QUEENSIDE, 0, &[1u8, 2, 3][..]),
                ]
            } else {
                [
                    (62, CASTLING_SECOND_KINGSIDE, 63, &[61u8, 62][..]),
                    (58, CASTLING_SECOND_QUEENSIDE, 56, &[57u8, 58, 59][..]),
                ]
            } {
                if w.bytes[65] & bit != 0
                    && w.bytes[rook] == code(side, 4)
                    && path.iter().all(|&s| w.bytes[s as usize] == 0)
                {
                    out.push(make_move(from, to, 0))
                }
            }
        }
        3 | 4 | 5 => {
            let dirs: &[(i8, i8)] = if k == 3 {
                &[(1, 1), (1, -1), (-1, 1), (-1, -1)]
            } else if k == 4 {
                &[(1, 0), (-1, 0), (0, 1), (0, -1)]
            } else {
                &[
                    (1, 1),
                    (1, -1),
                    (-1, 1),
                    (-1, -1),
                    (1, 0),
                    (-1, 0),
                    (0, 1),
                    (0, -1),
                ]
            };
            for &(df, dr) in dirs {
                let (mut f, mut r) = (file(from) + df, rank(from) + dr);
                while let Some(t) = sq(f, r) {
                    if w.bytes[t as usize] == 0 {
                        out.push(make_move(from, t, 0))
                    } else {
                        if piece_side(w.bytes[t as usize]) == Some(1 - side)
                            && piece_kind(w.bytes[t as usize]) != 6
                        {
                            out.push(make_move(from, t, 0))
                        }
                        break;
                    }
                    f += df;
                    r += dr
                }
            }
        }
        1 => {
            let d = if side == 0 { 1 } else { -1 };
            if let Some(t) = sq(file(from), rank(from) + d) {
                if w.bytes[t as usize] == 0 {
                    if rank(t) == if side == 0 { 7 } else { 0 } {
                        for p in 1..=4 {
                            out.push(make_move(from, t, p))
                        }
                    } else {
                        out.push(make_move(from, t, 0));
                        let home = if side == 0 { 1 } else { 6 };
                        if rank(from) == home {
                            let t2 = sq(file(from), rank(from) + 2 * d).unwrap();
                            if w.bytes[t2 as usize] == 0 {
                                out.push(make_move(from, t2, 0))
                            }
                        }
                    }
                }
            }
            for df in [-1, 1] {
                if let Some(t) = sq(file(from) + df, rank(from) + d) {
                    let capture = piece_side(w.bytes[t as usize]) == Some(1 - side)
                        && piece_kind(w.bytes[t as usize]) != 6;
                    let ep = w.bytes[66] != 0 && w.bytes[66] - 1 == t && w.bytes[t as usize] == 0;
                    if capture || ep {
                        if rank(t) == if side == 0 { 7 } else { 0 } {
                            for p in 1..=4 {
                                out.push(make_move(from, t, p))
                            }
                        } else {
                            out.push(make_move(from, t, 0))
                        }
                    }
                }
            }
        }
        _ => {}
    }
    out.sort();
    out.dedup();
    out
}
pub fn pseudo_legal_moves(p: &LocallyAdmissiblePosition) -> Vec<Move> {
    let mut v = Vec::new();
    for s in 0..64 {
        v.extend(pseudo_for(&p.wire, s))
    }
    v.sort();
    v.dedup();
    v
}

fn initial() -> WirePosition {
    decode_position(&[
        4, 2, 3, 5, 6, 3, 2, 4, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 7, 7, 7, 7, 7, 7, 7, 7, 10, 8, 9, 11,
        12, 9, 8, 10, 0, 15, 0,
    ])
    .unwrap()
}

fn checked_after(w: &WirePosition, m: Move) -> Option<(WirePosition, bool)> {
    let a = origin(m);
    let b = destination(m);
    let side = w.bytes[64];
    let pc = w.bytes[a as usize];
    let mut n = w.clone();
    let mut capture = n.bytes[b as usize] != 0;
    n.bytes[66] = 0;
    n.bytes[a as usize] = 0;
    if piece_kind(pc) == 1 && file(a) != file(b) && w.bytes[b as usize] == 0 {
        let cap = (b as i16 + if side == 0 { -8 } else { 8 }) as usize;
        if n.bytes[cap] == code(1 - side, 1) {
            n.bytes[cap] = 0;
            capture = true
        } else {
            return None;
        }
    }
    let promoted = match promotion(m) {
        0 => pc,
        1 => code(side, 5),
        2 => code(side, 4),
        3 => code(side, 3),
        4 => code(side, 2),
        _ => return None,
    };
    n.bytes[b as usize] = promoted;
    if piece_kind(pc) == 6 && (file(a) - file(b)).abs() == 2 {
        let (rf, rt) = if b > a {
            (a + 3, a + 1)
        } else {
            (a - 4, a - 1)
        };
        n.bytes[rf as usize] = 0;
        n.bytes[rt as usize] = code(side, 4);
    }
    let rights = &mut n.bytes[65];
    if piece_kind(pc) == 6 {
        *rights &= if side == 0 {
            !(CASTLING_FIRST_KINGSIDE | CASTLING_FIRST_QUEENSIDE)
        } else {
            !(CASTLING_SECOND_KINGSIDE | CASTLING_SECOND_QUEENSIDE)
        }
    }
    for (home, bit) in [
        (7, CASTLING_FIRST_KINGSIDE),
        (0, CASTLING_FIRST_QUEENSIDE),
        (63, CASTLING_SECOND_KINGSIDE),
        (56, CASTLING_SECOND_QUEENSIDE),
    ] {
        if a == home || b == home {
            *rights &= !bit
        }
    }
    if piece_kind(pc) == 1 && (rank(a) - rank(b)).abs() == 2 {
        n.bytes[66] = ((a + b) / 2) + 1
    }
    n.bytes[64] = 1 - side;
    let king = n.bytes[..64].iter().position(|&x| x == code(side, 6))? as u8;
    if !controls_square_raw(&n, 1 - side, king).is_empty() {
        return None;
    }
    Some((n, capture))
}

fn castle_safe(w: &WirePosition, m: Move) -> bool {
    let a = origin(m);
    let b = destination(m);
    let side = w.bytes[64];
    if piece_kind(w.bytes[a as usize]) != 6 || (file(a) - file(b)).abs() != 2 {
        return true;
    }
    if !controls_square_raw(w, 1 - side, a).is_empty() {
        return false;
    }
    let transit = if b > a { a + 1 } else { a - 1 };
    let mut probe = w.clone();
    probe.bytes[a as usize] = 0;
    probe.bytes[transit as usize] = code(side, 6);
    if !controls_square_raw(&probe, 1 - side, transit).is_empty() {
        return false;
    }
    true
}
fn legal_raw(state: &ReplayState) -> Vec<Move> {
    let local = LocallyAdmissiblePosition {
        wire: state.position.clone(),
    };
    let mut out = Vec::new();
    for m in pseudo_legal_moves(&local) {
        if castle_safe(&state.position, m) && checked_after(&state.position, m).is_some() {
            out.push(m)
        }
    }
    out.sort();
    out
}
pub fn common_dead(state: &ReplayState) -> bool {
    let mut pieces = Vec::new();
    for &p in &state.position.bytes[..64] {
        if p != 0 && piece_kind(p) != 6 {
            pieces.push(piece_kind(p))
        }
    }
    matches!(pieces.as_slice(), [] | [2] | [3])
}
pub fn board_terminal(state: &ReplayState) -> BoardTerminal {
    let legal = legal_raw(state);
    if legal.is_empty() {
        let side = state.position.bytes[64];
        let local = LocallyAdmissiblePosition {
            wire: state.position.clone(),
        };
        if king_in_check_raw(&local, side) {
            BoardTerminal::Checkmate(Side(1 - side))
        } else {
            BoardTerminal::Stalemate
        }
    } else if common_dead(state) {
        BoardTerminal::CommonDead
    } else {
        BoardTerminal::None
    }
}
pub fn legal_moves(state: &ReplayState) -> Vec<Move> {
    if board_terminal(state) == BoardTerminal::None {
        legal_raw(state)
    } else {
        Vec::new()
    }
}

fn diagnose(state: &ReplayState, m: Move) -> u16 {
    let w = &state.position;
    let a = origin(m);
    let b = destination(m);
    let pc = w.bytes[a as usize];
    let side = w.bytes[64];
    let dest = w.bytes[b as usize];
    if pc == 0 {
        return CHESS_MOVE_EMPTY_ORIGIN;
    }
    if piece_side(pc) != Some(side) {
        return CHESS_MOVE_WRONG_SIDE;
    }
    if piece_side(dest) == Some(side) {
        return CHESS_MOVE_FRIENDLY_DESTINATION;
    }
    if piece_kind(dest) == 6 {
        return CHESS_MOVE_KING_CAPTURE;
    }
    let k = piece_kind(pc);
    let prom = promotion(m);
    if k == 1 && rank(b) == if side == 0 { 7 } else { 0 } && prom == 0 {
        return CHESS_MOVE_PROMOTION_MISSING;
    }
    if prom != 0 && (k != 1 || rank(b) != if side == 0 { 7 } else { 0 }) {
        return CHESS_MOVE_PROMOTION_UNNEEDED;
    }
    if k == 6
        && matches!(
            (side, a, b),
            (SIDE_FIRST, 4, 6) | (SIDE_FIRST, 4, 2) | (SIDE_SECOND, 60, 62) | (SIDE_SECOND, 60, 58)
        )
    {
        let bit = match (side, b > a) {
            (0, true) => CASTLING_FIRST_KINGSIDE,
            (0, false) => CASTLING_FIRST_QUEENSIDE,
            (1, true) => CASTLING_SECOND_KINGSIDE,
            _ => CASTLING_SECOND_QUEENSIDE,
        };
        if w.bytes[65] & bit == 0 {
            return CHESS_MOVE_CASTLING_RIGHT;
        }
        let (rook, path): (u8, &[u8]) = if b > a {
            (a + 3, &[1, 2])
        } else {
            (a - 4, &[1, 2, 3])
        };
        if w.bytes[rook as usize] != code(side, 4)
            || path.iter().any(|d| {
                w.bytes[(a as i16 + if b > a { *d as i16 } else { -(*d as i16) }) as usize] != 0
            })
        {
            return CHESS_MOVE_CASTLING_PATH;
        }
        if !controls_square_raw(w, 1 - side, a).is_empty() {
            return CHESS_MOVE_CASTLING_FROM_CHECK;
        }
        let transit = if b > a { a + 1 } else { a - 1 };
        let mut p = w.clone();
        p.bytes[a as usize] = 0;
        p.bytes[transit as usize] = code(side, 6);
        if !controls_square_raw(&p, 1 - side, transit).is_empty() {
            return CHESS_MOVE_CASTLING_THROUGH_CHECK;
        }
        return CHESS_MOVE_CASTLING_INTO_CHECK;
    }
    let df = file(b) - file(a);
    let dr = rank(b) - rank(a);
    if k == 1 && df.abs() == 1 && dest == 0 {
        if w.bytes[66] == 0 || w.bytes[66] - 1 != b {
            return CHESS_MOVE_EN_PASSANT_TARGET;
        }
        let need = if side == 0 { 1 } else { -1 };
        let cap = (b as i16 + if side == 0 { -8 } else { 8 }) as usize;
        if dr != need || w.bytes[cap] != code(1 - side, 1) {
            return CHESS_MOVE_EN_PASSANT_GEOMETRY;
        }
    }
    if k != 1 && !controls_from(w, a, b) {
        if matches!(k, 3 | 4 | 5) {
            let df = file(b) - file(a);
            let dr = rank(b) - rank(a);
            let valid = (k == 3 && df.abs() == dr.abs())
                || (k == 4 && ((df == 0) ^ (dr == 0)))
                || (k == 5 && (df.abs() == dr.abs() || ((df == 0) ^ (dr == 0))));
            if valid {
                return CHESS_MOVE_BLOCKED;
            }
        }
        return CHESS_MOVE_GEOMETRY;
    }
    if pseudo_for(w, a).contains(&m) {
        return CHESS_MOVE_SELF_CHECK;
    }
    if k == 1 {
        if df == 0 {
            if dest != 0 {
                return CHESS_MOVE_PAWN_ADVANCE;
            }
            if dr.abs() == 2 {
                return CHESS_MOVE_PAWN_DOUBLE;
            }
            return CHESS_MOVE_PAWN_ADVANCE;
        } else if df.abs() == 1 {
            return CHESS_MOVE_PAWN_CAPTURE;
        } else {
            return CHESS_MOVE_PAWN_ADVANCE;
        }
    }
    CHESS_MOVE_SELF_CHECK
}
pub fn apply_move(state: &ReplayState, m: Move) -> Result<ReplayState> {
    if board_terminal(state) != BoardTerminal::None {
        return Err(reject(CHESS_GAME_CLOSED));
    }
    if state.moves.len() >= MAX_HISTORY_PLIES as usize {
        return Err(reject(CHESS_RESOURCE_HISTORY_PLIES));
    }
    if !legal_raw(state).contains(&m) {
        return Err(reject(diagnose(state, m)));
    }
    let pc = state.position.bytes[origin(m) as usize];
    let (position, capture) = checked_after(&state.position, m).unwrap();
    let mut n = state.clone();
    n.position = position;
    n.moves.push(m);
    n.halfmove = if piece_kind(pc) == 1 || capture {
        0
    } else {
        n.halfmove + 1
    };
    let key = repetition_key(&n);
    n.keys.push(key);
    Ok(n)
}
pub fn replay_from_start(moves: &[Move]) -> Result<ReplayState> {
    let mut s = ReplayState {
        position: initial(),
        moves: Vec::new(),
        keys: Vec::new(),
        halfmove: 0,
    };
    let k = repetition_key(&s);
    s.keys.push(k);
    for &m in moves.iter().take(MAX_HISTORY_PLIES as usize + 1) {
        s = apply_move(&s, m)?
    }
    Ok(s)
}
pub fn repetition_key(state: &ReplayState) -> [u8; 67] {
    let mut b = state.position.bytes;
    if !effective_ep_no_recurse(state) {
        b[66] = 0
    }
    b
}
fn effective_ep_no_recurse(state: &ReplayState) -> bool {
    let Some(t) = state.position.bytes[66].checked_sub(1) else {
        return false;
    };
    let side = state.position.bytes[64];
    let r = rank(t) - if side == 0 { 1 } else { -1 };
    for df in [-1, 1] {
        if let Some(a) = sq(file(t) + df, r) {
            if state.position.bytes[a as usize] == code(side, 1)
                && checked_after(&state.position, make_move(a, t, 0)).is_some()
            {
                return true;
            }
        }
    }
    false
}

pub fn new_game() -> GameState {
    GameState {
        replay: replay_from_start(&[]).expect("initial position is valid"),
        status: GAME_STATUS_ACTIVE,
        cause: None,
        score: None,
    }
}

fn close_board(mut game: GameState) -> GameState {
    match board_terminal(&game.replay) {
        BoardTerminal::None => game,
        BoardTerminal::Checkmate(winner) => {
            game.status = GAME_STATUS_CHECKMATE;
            game.cause = Some(ClosureCause::Board(BoardClosure::Checkmate(winner)));
            game.score = Some(if winner == Side::FIRST {
                Score::FirstWin
            } else {
                Score::SecondWin
            });
            game
        }
        BoardTerminal::Stalemate => {
            game.status = GAME_STATUS_STALEMATE;
            game.cause = Some(ClosureCause::Board(BoardClosure::Stalemate));
            game.score = Some(Score::Draw);
            game
        }
        BoardTerminal::CommonDead => {
            game.status = GAME_STATUS_COMMON_DEAD;
            game.cause = Some(ClosureCause::Board(BoardClosure::CommonDead));
            game.score = Some(Score::Draw);
            game
        }
    }
}

pub fn apply_event(game: &GameState, event: Event) -> Result<GameState> {
    if game.status != GAME_STATUS_ACTIVE || board_terminal(&game.replay) != BoardTerminal::None {
        return Err(reject(CHESS_GAME_CLOSED));
    }
    match event.kind {
        EventKind::Move(mv) => {
            let mut next = game.clone();
            next.replay = apply_move(&next.replay, mv)?;
            Ok(close_board(next))
        }
        EventKind::Resignation(side) => {
            let mut next = game.clone();
            next.status = GAME_STATUS_RESIGNED;
            next.cause = Some(ClosureCause::Resignation(side));
            next.score = Some(if side == Side::FIRST {
                Score::SecondWin
            } else {
                Score::FirstWin
            });
            Ok(next)
        }
        EventKind::DrawAgreement => {
            if game.replay.played_plies() < CHESS_AGREEMENT_MIN_PLIES as usize {
                return Err(reject(CHESS_EVENT_AGREEMENT_TOO_EARLY));
            }
            let mut next = game.clone();
            next.status = GAME_STATUS_AGREED;
            next.cause = Some(ClosureCause::DrawAgreement);
            next.score = Some(Score::Draw);
            Ok(next)
        }
        EventKind::ClaimThreefold => {
            if !game.replay.threefold_available() {
                return Err(reject(CHESS_EVENT_THREEFOLD_UNAVAILABLE));
            }
            let mut next = game.clone();
            next.status = GAME_STATUS_CLAIMED_THREEFOLD;
            next.cause = Some(ClosureCause::ClaimThreefold);
            next.score = Some(Score::Draw);
            Ok(next)
        }
        EventKind::ClaimFiftyMove => {
            if !game.replay.fifty_move_available() {
                return Err(reject(CHESS_EVENT_50_MOVE_UNAVAILABLE));
            }
            let mut next = game.clone();
            next.status = GAME_STATUS_CLAIMED_50_MOVE;
            next.cause = Some(ClosureCause::ClaimFiftyMove);
            next.score = Some(Score::Draw);
            Ok(next)
        }
    }
}

pub fn validate_source_record(moves: &[Move], score: Score) -> Result<RecordResult> {
    if moves.is_empty() {
        return Err(reject(CHESS_RECORD_EMPTY));
    }
    let replay = replay_from_start(moves)?;
    let terminal = board_terminal(&replay);
    match terminal {
        BoardTerminal::Checkmate(winner)
            if score
                != if winner == Side::FIRST {
                    Score::FirstWin
                } else {
                    Score::SecondWin
                } =>
        {
            return Err(reject(CHESS_RECORD_CHECKMATE_SCORE));
        }
        BoardTerminal::Stalemate | BoardTerminal::CommonDead if score != Score::Draw => {
            return Err(reject(CHESS_RECORD_DRAW_SCORE));
        }
        _ => {}
    }
    Ok(RecordResult {
        threefold_available: replay.threefold_available(),
        fifty_move_available: replay.fifty_move_available(),
        final_replay: replay,
        score,
        board_terminal: terminal,
    })
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum OccupancyMatch {
    Empty,
    Occupied,
    Exact { side: Side, piece: u8 },
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Defender {
    Any,
    Exact(Square),
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct TreeEdge {
    pub mv: Move,
    pub child: u16,
}
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TreeNode {
    pub edges: Vec<TreeEdge>,
}
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum PredicateInput {
    Initial(WirePosition),
    CurrentSide(ReplayState, Side),
    Occupancy(WirePosition, Square, OccupancyMatch),
    MoveLegality(ReplayState, Move),
    Control(WirePosition, Side, Square),
    Defended(WirePosition, Square, Defender),
    KingCheck(LocallyAdmissiblePosition, Side),
    AbsolutePin(LocallyAdmissiblePosition, Square),
    Fork(ReplayState, Move, Vec<Option<Square>>),
    Discovered(ReplayState, Move, Option<Square>, Option<Square>),
    Escape(WirePosition, Side, Square),
    PassedPawn(LocallyAdmissiblePosition, Square),
    OpenFile(WirePosition, u8),
    SemiOpenFile(WirePosition, Side, u8),
    PromotionTree(ReplayState, Vec<TreeNode>),
    MatingTree(ReplayState, Option<Side>, Vec<TreeNode>),
    TerminalTransition(ReplayState, Move),
    History(ReplayState),
    Declaration(GameState, Event),
    SourceScore(Vec<Move>, Score),
    MoveBytes(Vec<u8>),
    MoveRecord(Vec<Move>, Score),
    Wrong,
}
#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub enum RaceOutcome {
    FirstPromotes,
    SecondPromotes,
    NoPromotion,
}
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct HistoryClaimResult {
    pub nominal_ep: Option<Square>,
    pub effective_ep: Option<Square>,
    pub current_key_occurrences: u16,
    pub halfmove_clock: u16,
    pub played_plies: u16,
    pub threefold_available: bool,
    pub fifty_move_available: bool,
}
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum MoveRecordResult {
    Decoded(Move),
    Replayed(RecordResult),
    Rejected(u16),
}
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum PredicateResult {
    Bool(bool),
    Squares(Vec<Square>),
    MoveLegality(std::result::Result<(), u16>),
    Race(Vec<RaceOutcome>),
    Mating {
        mating_side: Side,
        all_branches_mate: bool,
        max_plies: u8,
    },
    Terminal(BoardTerminal),
    History(HistoryClaimResult),
    Declaration(std::result::Result<GameState, u16>),
    SourceScore(std::result::Result<BoardTerminal, u16>),
    MoveRecord(MoveRecordResult),
}

fn absolute_pin(p: &LocallyAdmissiblePosition, at: u8) -> bool {
    if at >= 64 {
        return false;
    }
    let pc = p.wire.bytes[at as usize];
    let Some(side) = piece_side(pc) else {
        return false;
    };
    if piece_kind(pc) == 6 || king_in_check_raw(p, side) {
        return false;
    }
    let king = p.wire.bytes[..64]
        .iter()
        .position(|&x| x == code(side, 6))
        .unwrap() as u8;
    let mut removed = p.wire.clone();
    removed.bytes[at as usize] = 0;
    controls_square_raw(&removed, 1 - side, king)
        .into_iter()
        .any(|from| matches!(piece_kind(removed.bytes[from as usize]), 3 | 4 | 5))
}
fn passed_pawn(p: &LocallyAdmissiblePosition, at: u8) -> bool {
    if at >= 64 {
        return false;
    }
    let pc = p.wire.bytes[at as usize];
    if piece_kind(pc) != 1 {
        return false;
    }
    let side = piece_side(pc).unwrap();
    for s in 0..64u8 {
        if p.wire.bytes[s as usize] == code(1 - side, 1)
            && (file(s) - file(at)).abs() <= 1
            && if side == SIDE_FIRST {
                rank(s) > rank(at)
            } else {
                rank(s) < rank(at)
            }
        {
            return false;
        }
    }
    true
}
fn discovered(state: &ReplayState, mv: Move, slider: u8, target: u8) -> Result<bool> {
    let moved = origin(mv);
    let side = state.position.bytes[64];
    let next = apply_move(state, mv)?;
    if slider >= 64 || target >= 64 || slider == moved {
        return Ok(false);
    }
    let pc = state.position.bytes[slider as usize];
    if piece_side(pc) != Some(side) || !matches!(piece_kind(pc), 3 | 4 | 5) {
        return Ok(false);
    }
    let df = file(target) - file(slider);
    let dr = rank(target) - rank(slider);
    let valid = match piece_kind(pc) {
        3 => df.abs() == dr.abs() && df != 0,
        4 => (df == 0) ^ (dr == 0),
        5 => (df.abs() == dr.abs() && df != 0) || ((df == 0) ^ (dr == 0)),
        _ => false,
    };
    if !valid {
        return Ok(false);
    }
    let (sf, sr) = (df.signum(), dr.signum());
    let (mut f, mut r) = (file(slider) + sf, rank(slider) + sr);
    let mut first = None;
    while let Some(x) = sq(f, r) {
        if x == target {
            break;
        }
        if state.position.bytes[x as usize] != 0 {
            first = Some(x);
            break;
        }
        f += sf;
        r += sr
    }
    Ok(first == Some(moved) && controls_from(&next.position, slider, target))
}

fn tree_resource_screen(nodes: &[TreeNode]) -> Result<()> {
    if nodes.len() > CHESS_MAX_PREDICATE_NODES as usize {
        return Err(reject(CHESS_RESOURCE_PREDICATE_INPUT));
    }
    let mut checked_size = nodes
        .len()
        .checked_mul(std::mem::size_of::<TreeNode>())
        .ok_or_else(|| reject(CHESS_RESOURCE_PREDICATE_INPUT))?;
    let mut total = 0usize;
    for n in nodes {
        if n.edges.len() > CHESS_MAX_PREDICATE_EDGES_PER_NODE as usize {
            return Err(reject(CHESS_RESOURCE_PREDICATE_INPUT));
        }
        let edge_size = n
            .edges
            .len()
            .checked_mul(std::mem::size_of::<TreeEdge>())
            .ok_or_else(|| reject(CHESS_RESOURCE_PREDICATE_INPUT))?;
        checked_size = checked_size
            .checked_add(edge_size)
            .ok_or_else(|| reject(CHESS_RESOURCE_PREDICATE_INPUT))?;
        total = total
            .checked_add(n.edges.len())
            .ok_or_else(|| reject(CHESS_RESOURCE_PREDICATE_INPUT))?;
    }
    if total > CHESS_MAX_PREDICATE_EDGES as usize {
        return Err(reject(CHESS_RESOURCE_PREDICATE_INPUT));
    }
    Ok(())
}

fn derive_tree_screened(
    root: &ReplayState,
    nodes: &[TreeNode],
) -> Result<Vec<(ReplayState, u8, Option<u8>)>> {
    if nodes.is_empty() {
        return Err(reject(CHESS_PREDICATE_TREE));
    }
    fn walk(
        parent: usize,
        state: &ReplayState,
        depth: u8,
        nodes: &[TreeNode],
        incoming: &mut [u8],
        next: &mut usize,
        derived: &mut [Option<(ReplayState, u8, Option<u8>)>],
    ) -> Result<()> {
        if depth > CHESS_MAX_PREDICATE_DEPTH as u8 {
            return Err(reject(CHESS_PREDICATE_TREE));
        }
        let edges = &nodes[parent].edges;
        if edges.windows(2).any(|w| w[0].mv >= w[1].mv) {
            return Err(reject(CHESS_PREDICATE_TREE));
        }
        for e in edges {
            let child = e.child as usize;
            if child >= nodes.len() || child <= parent || child != *next {
                return Err(reject(CHESS_PREDICATE_TREE));
            }
            *next += 1;
            incoming[child] = incoming[child].saturating_add(1);
            if incoming[child] != 1 {
                return Err(reject(CHESS_PREDICATE_TREE));
            }
            let ns = apply_move(state, e.mv).map_err(|_| reject(CHESS_PREDICATE_TREE))?;
            let promoted = if promotion(e.mv) == 0 {
                None
            } else {
                Some(state.position.bytes[64])
            };
            if promoted.is_some() && !nodes[child].edges.is_empty() {
                return Err(reject(CHESS_PREDICATE_TREE));
            }
            derived[child] = Some((ns.clone(), depth + 1, promoted));
            walk(child, &ns, depth + 1, nodes, incoming, next, derived)?;
        }
        Ok(())
    }
    let mut incoming = vec![0u8; nodes.len()];
    let mut next = 1usize;
    let mut derived: Vec<Option<(ReplayState, u8, Option<u8>)>> = vec![None; nodes.len()];
    derived[0] = Some((root.clone(), 0, None));
    walk(0, root, 0, nodes, &mut incoming, &mut next, &mut derived)?;
    if next != nodes.len() || incoming.iter().skip(1).any(|&x| x != 1) {
        return Err(reject(CHESS_PREDICATE_TREE));
    }
    Ok(derived.into_iter().map(Option::unwrap).collect())
}
fn derive_tree(
    root: &ReplayState,
    nodes: &[TreeNode],
) -> Result<Vec<(ReplayState, u8, Option<u8>)>> {
    tree_resource_screen(nodes)?;
    derive_tree_screened(root, nodes)
}
fn promotion_tree(root: &ReplayState, nodes: &[TreeNode]) -> Result<Vec<RaceOutcome>> {
    let states = derive_tree(root, nodes)?;
    let mut out = Vec::new();
    for (i, (_, _, promoted)) in states.iter().enumerate() {
        if nodes[i].edges.is_empty() {
            out.push(match promoted {
                Some(SIDE_FIRST) => RaceOutcome::FirstPromotes,
                Some(SIDE_SECOND) => RaceOutcome::SecondPromotes,
                _ => RaceOutcome::NoPromotion,
            })
        }
    }
    out.sort();
    out.dedup();
    Ok(out)
}
fn mating_tree(root: &ReplayState, mating_side: Side, nodes: &[TreeNode]) -> Result<(bool, u8)> {
    let side = mating_side.code();
    if root.position.bytes[..64]
        .iter()
        .filter(|&&x| x != 0)
        .count()
        != 3
        || root.position.bytes[..64]
            .iter()
            .filter(|&&x| piece_kind(x) == 6)
            .count()
            != 2
        || root.position.bytes[..64]
            .iter()
            .filter(|&&x| piece_side(x) == Some(side) && matches!(piece_kind(x), 4 | 5))
            .count()
            != 1
    {
        return Err(reject(CHESS_PREDICATE_TREE));
    }
    let states = derive_tree_screened(root, nodes)?;
    let mut all = true;
    let mut max = 0;
    for (i, (state, depth, _)) in states.iter().enumerate() {
        max = max.max(*depth);
        let legal = legal_moves(state);
        let term = board_terminal(state);
        let supplied: Vec<_> = nodes[i].edges.iter().map(|e| e.mv).collect();
        if term != BoardTerminal::None {
            if !supplied.is_empty() {
                return Err(reject(CHESS_PREDICATE_TREE));
            }
            all &= term == BoardTerminal::Checkmate(mating_side)
        } else if state.position.bytes[64] == side {
            if supplied.len() != 1 {
                return Err(reject(CHESS_PREDICATE_TREE));
            }
        } else if supplied != legal {
            return Err(reject(CHESS_PREDICATE_TREE));
        }
    }
    Ok((all, max))
}

pub fn evaluate_predicate(id: &[u8], input: PredicateInput) -> Result<PredicateResult> {
    const IDS: [&[u8]; 20] = [
        b"chess.setup_turn",
        b"chess.occupancy",
        b"chess.move_legality",
        b"chess.control",
        b"chess.defended",
        b"chess.king_check",
        b"chess.absolute_pin",
        b"chess.fork_double_attack",
        b"chess.discovered_attack_check",
        b"chess.escape_square_control",
        b"chess.passed_pawn",
        b"chess.open_file",
        b"chess.semi_open_file",
        b"chess.finite_promotion_race",
        b"chess.finite_mating_geometry",
        b"chess.terminal_transition",
        b"chess.history_claim",
        b"chess.declaration_event",
        b"chess.source_score_relation",
        b"chess.move_record_replay",
    ];
    let Some(which) = IDS.iter().position(|x| *x == id) else {
        return Err(reject(CHESS_PREDICATE_UNKNOWN));
    };
    let signature = || reject(CHESS_PREDICATE_SIGNATURE);
    match (which, input) {
        (0, PredicateInput::Initial(p)) => Ok(PredicateResult::Bool(p == initial())),
        (0, PredicateInput::CurrentSide(r, s)) => {
            Ok(PredicateResult::Bool(r.position.bytes[64] == s.code()))
        }
        (1, PredicateInput::Occupancy(p, sq, m)) => {
            let pc = p.bytes[sq.index() as usize];
            let value = match m {
                OccupancyMatch::Empty => pc == 0,
                OccupancyMatch::Occupied => pc != 0,
                OccupancyMatch::Exact { side, piece } if (1..=6).contains(&piece) => {
                    pc == code(side.code(), piece)
                }
                _ => return Err(signature()),
            };
            Ok(PredicateResult::Bool(value))
        }
        (2, PredicateInput::MoveLegality(r, m)) => Ok(PredicateResult::MoveLegality(
            apply_move(&r, m).map(|_| ()).map_err(|e| e.code),
        )),
        (3, PredicateInput::Control(p, s, t)) => {
            Ok(PredicateResult::Squares(controls_square(&p, s, t)))
        }
        (4, PredicateInput::Defended(p, t, d)) => {
            let pc = p.bytes[t.index() as usize];
            let v = if let Some(piece_side) = piece_side(pc) {
                controls_square(&p, side(piece_side), t)
                    .into_iter()
                    .any(|x| {
                        x != t
                            && match d {
                                Defender::Any => true,
                                Defender::Exact(y) => x == y,
                            }
                    })
            } else {
                false
            };
            Ok(PredicateResult::Bool(v))
        }
        (5, PredicateInput::KingCheck(p, s)) => Ok(PredicateResult::Bool(king_in_check(&p, s))),
        (6, PredicateInput::AbsolutePin(p, s)) => {
            Ok(PredicateResult::Bool(absolute_pin(&p, s.index())))
        }
        (7, PredicateInput::Fork(r, m, targets)) => {
            if board_terminal(&r) != BoardTerminal::None {
                return Err(reject(CHESS_GAME_CLOSED));
            }
            if targets.len() > CHESS_MAX_FORK_TARGETS as usize {
                return Err(reject(CHESS_RESOURCE_PREDICATE_INPUT));
            }
            if targets.len() < CHESS_MIN_FORK_TARGETS as usize
                || targets.iter().any(Option::is_none)
                || targets.windows(2).any(|w| w[0] >= w[1])
            {
                return Err(signature());
            }
            let side = r.position.bytes[64];
            let next = apply_move(&r, m)?;
            let at = destination(m);
            Ok(PredicateResult::Bool(targets.into_iter().all(|t| {
                let t = t.unwrap().index();
                piece_side(next.position.bytes[t as usize]) == Some(1 - side)
                    && controls_from(&next.position, at, t)
            })))
        }
        (8, PredicateInput::Discovered(r, m, s, t)) => {
            if board_terminal(&r) != BoardTerminal::None {
                return Err(reject(CHESS_GAME_CLOSED));
            }
            let (Some(s), Some(t)) = (s, t) else {
                return Err(signature());
            };
            Ok(PredicateResult::Bool(discovered(
                &r,
                m,
                s.index(),
                t.index(),
            )?))
        }
        (9, PredicateInput::Escape(p, s, t)) => {
            Ok(PredicateResult::Bool(!controls_square(&p, s, t).is_empty()))
        }
        (10, PredicateInput::PassedPawn(p, s)) => {
            Ok(PredicateResult::Bool(passed_pawn(&p, s.index())))
        }
        (11, PredicateInput::OpenFile(p, f)) if f < 8 => Ok(PredicateResult::Bool(
            (0..64u8)
                .filter(|s| file(*s) == f as i8)
                .all(|s| piece_kind(p.bytes[s as usize]) != 1),
        )),
        (12, PredicateInput::SemiOpenFile(p, s, f)) if f < 8 => {
            let s = s.code();
            let pawns: Vec<_> = (0..64u8)
                .filter(|x| file(*x) == f as i8 && piece_kind(p.bytes[*x as usize]) == 1)
                .collect();
            Ok(PredicateResult::Bool(
                !pawns
                    .iter()
                    .any(|&x| piece_side(p.bytes[x as usize]) == Some(s))
                    && pawns
                        .iter()
                        .any(|&x| piece_side(p.bytes[x as usize]) == Some(1 - s)),
            ))
        }
        (13, PredicateInput::PromotionTree(r, n)) => {
            Ok(PredicateResult::Race(promotion_tree(&r, &n)?))
        }
        (14, PredicateInput::MatingTree(r, s, n)) => {
            tree_resource_screen(&n)?;
            let Some(s) = s else {
                return Err(signature());
            };
            let (a, m) = mating_tree(&r, s, &n)?;
            Ok(PredicateResult::Mating {
                mating_side: s,
                all_branches_mate: a,
                max_plies: m,
            })
        }
        (15, PredicateInput::TerminalTransition(r, m)) => Ok(PredicateResult::Terminal(
            board_terminal(&apply_move(&r, m)?),
        )),
        (16, PredicateInput::History(r)) => Ok(PredicateResult::History(HistoryClaimResult {
            nominal_ep: r.nominal_en_passant(),
            effective_ep: if effective_ep_no_recurse(&r) {
                r.nominal_en_passant()
            } else {
                None
            },
            current_key_occurrences: r.current_key_occurrences(),
            halfmove_clock: r.halfmove_clock(),
            played_plies: r.played_plies() as u16,
            threefold_available: r.threefold_available(),
            fifty_move_available: r.fifty_move_available(),
        })),
        (17, PredicateInput::Declaration(g, e)) => Ok(PredicateResult::Declaration(
            apply_event(&g, e).map_err(|e| e.code),
        )),
        (18, PredicateInput::SourceScore(m, s)) => Ok(PredicateResult::SourceScore(
            validate_source_record(&m, s)
                .map(|x| x.board_terminal)
                .map_err(|e| e.code),
        )),
        (19, PredicateInput::MoveBytes(b)) => {
            Ok(PredicateResult::MoveRecord(match decode_move(&b) {
                Ok(m) => MoveRecordResult::Decoded(m),
                Err(e) => MoveRecordResult::Rejected(e.code),
            }))
        }
        (19, PredicateInput::MoveRecord(m, s)) => Ok(PredicateResult::MoveRecord(
            match validate_source_record(&m, s) {
                Ok(r) => MoveRecordResult::Replayed(r),
                Err(e) => MoveRecordResult::Rejected(e.code),
            },
        )),
        _ => Err(signature()),
    }
}
