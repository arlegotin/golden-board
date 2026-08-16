use std::collections::BTreeMap;

use gb_chess::*;
use gb_foundation::{ManifestValue as V, validate_canonical_manifest};

fn obj(entries: impl IntoIterator<Item = (&'static str, V)>) -> V {
    V::Object(entries.into_iter().map(|(k, v)| (k.into(), v)).collect())
}
fn u(n: u64) -> V {
    V::U64(n)
}
fn s(x: impl Into<String>) -> V {
    V::String(x.into())
}
fn b(x: bool) -> V {
    V::Bool(x)
}
fn field<'a>(v: &'a V, k: &str) -> &'a V {
    let V::Object(o) = v else { panic!("object") };
    o.get(k).unwrap()
}
fn text(v: &V) -> &str {
    let V::String(x) = v else { panic!("string") };
    x
}
fn num(v: &V) -> u64 {
    let V::U64(x) = v else { panic!("u64") };
    *x
}
fn side_value(v: &V) -> Side {
    Side::from_code(num(v) as u8).unwrap()
}
fn square_value(v: &V) -> Square {
    Square::from_index(num(v) as u8).unwrap()
}
fn square_field(v: &V) -> Option<Square> {
    u8::try_from(num(v)).ok().and_then(Square::from_index)
}
fn array(v: &V) -> &[V] {
    let V::Array(x) = v else { panic!("array") };
    x
}
fn hex(s: &str) -> Vec<u8> {
    assert!(s.len() % 2 == 0);
    s.as_bytes()
        .chunks_exact(2)
        .map(|p| {
            let n = |c| match c {
                b'0'..=b'9' => c - b'0',
                b'a'..=b'f' => c - b'a' + 10,
                _ => panic!("hex"),
            };
            n(p[0]) << 4 | n(p[1])
        })
        .collect()
}
fn hexed(bytes: &[u8]) -> String {
    const H: &[u8] = b"0123456789abcdef";
    let mut out = String::with_capacity(bytes.len() * 2);
    for &x in bytes {
        out.push(H[(x >> 4) as usize] as char);
        out.push(H[(x & 15) as usize] as char)
    }
    out
}
fn moves(v: &V) -> Vec<Move> {
    hex(text(v))
        .chunks_exact(2)
        .map(|x| decode_move(x).unwrap())
        .collect()
}
fn score(v: &V) -> Score {
    Score::from_code(num(v) as u8).unwrap()
}
fn success(value: V) -> V {
    obj([("success", value)])
}
fn failure(code: u16) -> V {
    obj([("rejection", u(code as u64))])
}

fn neutral_cycle_observations() -> bool {
    const POSITION: &str = concat!(
        "0402030506030204010101010101010100000000000000000000000000000000",
        "0000000000000000000000000000000007070707070707070a08090b0c09080a",
        "000f00",
    );
    const LEGAL: &str = concat!(
        "05000520195019702100218025102590292029a02d302db0314031c0355035d0",
        "396039e03d703df0",
    );
    let cycle: Vec<_> = hex("1950fad05460b7e01950fad05460b7e0")
        .chunks_exact(2)
        .map(|bytes| decode_move(bytes).unwrap())
        .collect();
    for (plies, halfmove, occurrences, threefold) in [
        (0usize, 0u16, 1u16, false),
        (4, 4, 2, false),
        (8, 8, 3, true),
    ] {
        let replay = replay_from_start(&cycle[..plies]).unwrap();
        if hexed(&encode_position(replay.position())) != POSITION
            || hexed(&repetition_key(&replay)) != POSITION
            || hexed(
                &legal_moves(&replay)
                    .iter()
                    .flat_map(|mv| encode_move(*mv))
                    .collect::<Vec<_>>(),
            ) != LEGAL
            || replay.played_plies() != plies
            || replay.halfmove_clock() != halfmove
            || replay.current_key_occurrences() != occurrences
            || replay.threefold_available() != threefold
            || board_terminal(&replay) != BoardTerminal::None
        {
            return false;
        }
        let local = validate_local(replay.position()).unwrap();
        if king_in_check(&local, Side::FIRST) || king_in_check(&local, Side::SECOND) {
            return false;
        }
        let PredicateResult::History(history) =
            evaluate_predicate(b"chess.history_claim", PredicateInput::History(replay)).unwrap()
        else {
            return false;
        };
        if history.played_plies as usize != plies
            || history.halfmove_clock != halfmove
            || history.current_key_occurrences != occurrences
            || history.threefold_available != threefold
        {
            return false;
        }
    }
    true
}

fn terminal_value(t: BoardTerminal) -> V {
    u(t.code() as u64)
}
fn replay_facts(r: &ReplayState, expected: &V) -> V {
    let V::Object(fields) = field(expected, "success") else {
        panic!()
    };
    let terminal = board_terminal(r);
    V::Object(
        fields
            .keys()
            .map(|k| {
                (
                    k.clone(),
                    match k.as_str() {
                        "common_dead" => b(common_dead(r)),
                        "terminal" => terminal_value(terminal),
                        "winning_side" => match terminal {
                            BoardTerminal::Checkmate(x) => u(x.code() as u64),
                            _ => panic!(),
                        },
                        "played_plies" => u(r.played_plies() as u64),
                        _ => panic!("unknown replay fact {k}"),
                    },
                )
            })
            .collect(),
    )
}
fn cause_value(c: ClosureCause) -> V {
    match c {
        ClosureCause::Board(BoardClosure::Checkmate(side)) => obj([
            ("kind", s("board")),
            ("terminal", u(1)),
            ("winning_side", u(side.code() as u64)),
        ]),
        ClosureCause::Board(BoardClosure::Stalemate) => {
            obj([("kind", s("board")), ("terminal", u(2))])
        }
        ClosureCause::Board(BoardClosure::CommonDead) => {
            obj([("kind", s("board")), ("terminal", u(3))])
        }
        ClosureCause::Resignation(side) => {
            obj([("kind", s("resignation")), ("side", u(side.code() as u64))])
        }
        ClosureCause::DrawAgreement => obj([("kind", s("draw-agreement"))]),
        ClosureCause::ClaimThreefold => obj([("kind", s("claim-threefold"))]),
        ClosureCause::ClaimFiftyMove => obj([("kind", s("claim-fifty-move"))]),
    }
}

fn position(v: &V) -> WirePosition {
    decode_position(&hex(text(v))).unwrap()
}
fn replay(v: &V) -> ReplayState {
    replay_from_start(&moves(v)).unwrap()
}
fn local(v: &V) -> LocallyAdmissiblePosition {
    let p = position(v);
    validate_local(&p).unwrap()
}
fn tree_nodes(v: &V) -> Vec<TreeNode> {
    array(v)
        .iter()
        .map(|n| TreeNode {
            edges: array(field(n, "edges"))
                .iter()
                .map(|e| TreeEdge {
                    mv: decode_move(&hex(text(field(e, "move_hex")))).unwrap(),
                    child: num(field(e, "child")) as u16,
                })
                .collect(),
        })
        .collect()
}
fn predicate_input(v: &V) -> PredicateInput {
    let variant = text(field(v, "variant"));
    match variant {
        "initial" => PredicateInput::Initial(position(field(v, "position_hex"))),
        "occupancy" => {
            let m = field(v, "match");
            let mode = match text(field(m, "kind")) {
                "empty" => OccupancyMatch::Empty,
                "occupied" => OccupancyMatch::Occupied,
                "exact" => OccupancyMatch::Exact {
                    side: side_value(field(m, "side")),
                    piece: num(field(m, "piece")) as u8,
                },
                _ => panic!(),
            };
            PredicateInput::Occupancy(
                position(field(v, "position_hex")),
                square_value(field(v, "square")),
                mode,
            )
        }
        "move-legality" => PredicateInput::MoveLegality(
            replay(field(v, "moves_hex")),
            decode_move(&hex(text(field(v, "move_hex")))).unwrap(),
        ),
        "control" => PredicateInput::Control(
            position(field(v, "position_hex")),
            side_value(field(v, "side")),
            square_value(field(v, "target")),
        ),
        "defended" => {
            let d = field(v, "defender");
            let d = match text(field(d, "kind")) {
                "any" => Defender::Any,
                "exact" => Defender::Exact(square_value(field(d, "square"))),
                _ => panic!(),
            };
            PredicateInput::Defended(
                position(field(v, "position_hex")),
                square_value(field(v, "target")),
                d,
            )
        }
        "king-check" => PredicateInput::KingCheck(
            local(field(v, "position_hex")),
            side_value(field(v, "side")),
        ),
        "absolute-pin" => PredicateInput::AbsolutePin(
            local(field(v, "position_hex")),
            square_value(field(v, "origin")),
        ),
        "fork-double-attack" => PredicateInput::Fork(
            replay(field(v, "moves_hex")),
            decode_move(&hex(text(field(v, "move_hex")))).unwrap(),
            array(field(v, "targets"))
                .iter()
                .map(square_field)
                .collect(),
        ),
        "discovered-line" => PredicateInput::Discovered(
            replay(field(v, "moves_hex")),
            decode_move(&hex(text(field(v, "move_hex")))).unwrap(),
            square_field(field(v, "slider_origin")),
            square_field(field(v, "target")),
        ),
        "escape-control" => PredicateInput::Escape(
            position(field(v, "position_hex")),
            side_value(field(v, "side")),
            square_value(field(v, "candidate")),
        ),
        "passed-pawn" => PredicateInput::PassedPawn(
            local(field(v, "position_hex")),
            square_value(field(v, "pawn_square")),
        ),
        "open-file" => PredicateInput::OpenFile(
            position(field(v, "position_hex")),
            num(field(v, "file")) as u8,
        ),
        "semi-open-file" => PredicateInput::SemiOpenFile(
            position(field(v, "position_hex")),
            side_value(field(v, "side")),
            num(field(v, "file")) as u8,
        ),
        "finite-promotion-tree" => PredicateInput::PromotionTree(
            replay(field(v, "moves_hex")),
            tree_nodes(field(v, "nodes")),
        ),
        "finite-mating-tree" => PredicateInput::MatingTree(
            replay(field(v, "moves_hex")),
            Side::from_code(num(field(v, "mating_side")) as u8),
            tree_nodes(field(v, "nodes")),
        ),
        "terminal-transition" => PredicateInput::TerminalTransition(
            replay(field(v, "moves_hex")),
            decode_move(&hex(text(field(v, "move_hex")))).unwrap(),
        ),
        "history-claim" => PredicateInput::History(replay(field(v, "moves_hex"))),
        "declaration-event" => {
            let mut g = new_game();
            for e in array(field(v, "events_hex")) {
                g = apply_event(&g, decode_event(&hex(text(e))).unwrap()).unwrap()
            }
            PredicateInput::Declaration(g, decode_event(&hex(text(field(v, "event_hex")))).unwrap())
        }
        "source-score" => {
            PredicateInput::SourceScore(moves(field(v, "moves_hex")), score(field(v, "score")))
        }
        "move-bytes" => PredicateInput::MoveBytes(hex(text(field(v, "move_hex")))),
        "record" => {
            PredicateInput::MoveRecord(moves(field(v, "moves_hex")), score(field(v, "score")))
        }
        "wrong" => PredicateInput::Wrong,
        _ => panic!("variant {variant}"),
    }
}
fn ep_value(x: Option<Square>) -> V {
    match x {
        None => obj([("kind", s("none"))]),
        Some(square) => obj([("kind", s("square")), ("square", u(square.index() as u64))]),
    }
}
fn predicate_value(value: PredicateResult) -> V {
    match value {
        PredicateResult::Bool(value) => obj([("value", b(value))]),
        PredicateResult::Squares(xs) => obj([(
            "squares",
            V::Array(xs.into_iter().map(|x| u(x.index() as u64)).collect()),
        )]),
        PredicateResult::MoveLegality(Ok(())) => obj([("kind", s("legal"))]),
        PredicateResult::MoveLegality(Err(code)) => {
            obj([("kind", s("illegal")), ("rejection", u(code as u64))])
        }
        PredicateResult::Race(xs) => obj([(
            "outcomes",
            V::Array(
                xs.into_iter()
                    .map(|x| {
                        s(match x {
                            RaceOutcome::FirstPromotes => "first-promotes",
                            RaceOutcome::SecondPromotes => "second-promotes",
                            RaceOutcome::NoPromotion => "no-promotion-in-branch",
                        })
                    })
                    .collect(),
            ),
        )]),
        PredicateResult::Mating {
            mating_side,
            all_branches_mate,
            max_plies,
        } => obj([
            ("all_branches_mate", b(all_branches_mate)),
            ("mating_side", u(mating_side.code() as u64)),
            ("max_plies", u(max_plies as u64)),
        ]),
        PredicateResult::Terminal(t) => {
            let mut m = BTreeMap::new();
            m.insert("terminal".into(), terminal_value(t));
            if let BoardTerminal::Checkmate(x) = t {
                m.insert("winning_side".into(), u(x.code() as u64));
            }
            V::Object(m)
        }
        PredicateResult::History(h) => obj([
            (
                "current_key_occurrences",
                u(h.current_key_occurrences as u64),
            ),
            ("effective_ep", ep_value(h.effective_ep)),
            ("fifty_move_available", b(h.fifty_move_available)),
            ("halfmove_clock", u(h.halfmove_clock as u64)),
            ("nominal_ep", ep_value(h.nominal_ep)),
            ("played_plies", u(h.played_plies as u64)),
            ("threefold_available", b(h.threefold_available)),
        ]),
        PredicateResult::Declaration(Ok(g)) => {
            let mut m = BTreeMap::new();
            m.insert("kind".into(), s("accepted"));
            m.insert("status".into(), u(g.status() as u64));
            if let Some(c) = g.closure_cause() {
                m.insert("cause".into(), cause_value(c));
            }
            if let Some(sc) = g.score() {
                m.insert("score".into(), u(sc.code() as u64));
            }
            V::Object(m)
        }
        PredicateResult::Declaration(Err(code)) => {
            obj([("kind", s("rejected")), ("rejection", u(code as u64))])
        }
        PredicateResult::SourceScore(Ok(t)) => {
            obj([("kind", s("accepted")), ("terminal", terminal_value(t))])
        }
        PredicateResult::SourceScore(Err(code)) => {
            obj([("kind", s("rejected")), ("rejection", u(code as u64))])
        }
        PredicateResult::MoveRecord(MoveRecordResult::Decoded(m)) => obj([
            ("kind", s("decoded")),
            ("move_hex", s(hexed(&encode_move(m)))),
        ]),
        PredicateResult::MoveRecord(MoveRecordResult::Replayed(r)) => obj([
            ("kind", s("replayed")),
            ("score", u(r.score.code() as u64)),
            ("terminal", terminal_value(r.board_terminal)),
        ]),
        PredicateResult::MoveRecord(MoveRecordResult::Rejected(code)) => {
            obj([("kind", s("rejected")), ("rejection", u(code as u64))])
        }
    }
}

fn run_direct(case: &V) -> Option<V> {
    let operation = text(field(case, "operation"));
    let input = field(case, "input");
    let expected = field(case, "expected");
    macro_rules! result {
        ($e:expr,$ok:expr) => {
            match $e {
                Ok(v) => success($ok(v)),
                Err(e) => failure(e.code),
            }
        };
    }
    Some(match operation {
        "decode_position" => result!(
            decode_position(&hex(text(field(input, "position_hex")))),
            |p| obj([("position_hex", s(hexed(&encode_position(&p))))])
        ),
        "decode_move" => result!(decode_move(&hex(text(field(input, "move_hex")))), |m| obj(
            [("move_hex", s(hexed(&encode_move(m))))]
        )),
        "decode_event" => result!(
            decode_event(&hex(text(field(input, "event_hex")))),
            |e| obj([("event_hex", s(hexed(&encode_event(e))))])
        ),
        "validate_local" => result!(
            decode_position(&hex(text(field(input, "position_hex"))))
                .and_then(|p| validate_local(&p)),
            |_| obj([])
        ),
        "controls_square" => {
            let p = decode_position(&hex(text(field(input, "position_hex")))).unwrap();
            success(obj([(
                "squares",
                V::Array(
                    controls_square(
                        &p,
                        side_value(field(input, "side")),
                        square_value(field(input, "target")),
                    )
                    .into_iter()
                    .map(|x| u(x.index() as u64))
                    .collect(),
                ),
            )]))
        }
        "pseudo_legal_moves" => {
            let p = decode_position(&hex(text(field(input, "position_hex")))).unwrap();
            result!(validate_local(&p), |p| obj([(
                "moves_hex",
                s(hexed(
                    &pseudo_legal_moves(&p)
                        .into_iter()
                        .flat_map(encode_move)
                        .collect::<Vec<_>>()
                ))
            )]))
        }
        "replay_from_start" => result!(replay_from_start(&moves(field(input, "moves_hex"))), |r| {
            replay_facts(&r, expected)
        }),
        "legal_moves" => result!(replay_from_start(&moves(field(input, "moves_hex"))), |r| {
            obj([(
                "moves_hex",
                s(hexed(
                    &legal_moves(&r)
                        .into_iter()
                        .flat_map(encode_move)
                        .collect::<Vec<_>>(),
                )),
            )])
        }),
        "repetition_key" => result!(replay_from_start(&moves(field(input, "moves_hex"))), |r| {
            obj([("repetition_key_hex", s(hexed(&repetition_key(&r))))])
        }),
        "apply_move" => {
            let ms = moves(field(input, "moves_hex"));
            let mv = decode_move(&hex(text(field(input, "move_hex")))).unwrap();
            match replay_from_start(&ms).and_then(|r| apply_move(&r, mv)) {
                Err(e) => failure(e.code),
                Ok(r) => {
                    let V::Object(fields) = field(expected, "success") else {
                        panic!()
                    };
                    success(V::Object(
                        fields
                            .keys()
                            .map(|k| {
                                (
                                    k.clone(),
                                    match k.as_str() {
                                        "position_hex" => s(hexed(&encode_position(r.position()))),
                                        "halfmove_clock" => u(r.halfmove_clock() as u64),
                                        "terminal" => terminal_value(board_terminal(&r)),
                                        "king_in_check" => {
                                            let l = validate_local(r.position()).unwrap();
                                            b(king_in_check(
                                                &l,
                                                Side::from_code(encode_position(r.position())[64])
                                                    .unwrap(),
                                            ))
                                        }
                                        _ => panic!("apply fact {k}"),
                                    },
                                )
                            })
                            .collect(),
                    ))
                }
            }
        }
        "apply_event" => {
            let mut g = new_game();
            let prior = (|| -> Result<(), ChessReject> {
                for x in array(field(input, "events_hex")) {
                    g = apply_event(&g, decode_event(&hex(text(x)))?)?;
                }
                Ok(())
            })();
            match prior
                .and_then(|_| apply_event(&g, decode_event(&hex(text(field(input, "event_hex"))))?))
            {
                Err(e) => failure(e.code),
                Ok(g) => {
                    let mut x = BTreeMap::new();
                    x.insert("status".into(), u(g.status() as u64));
                    if let Some(c) = g.closure_cause() {
                        x.insert("cause".into(), cause_value(c));
                    }
                    if let Some(sc) = g.score() {
                        x.insert("score".into(), u(sc.code() as u64));
                    }
                    success(V::Object(x))
                }
            }
        }
        "validate_source_record" => result!(
            validate_source_record(
                &moves(field(input, "moves_hex")),
                score(field(input, "score"))
            ),
            |r: RecordResult| {
                let V::Object(fields) = field(expected, "success") else {
                    panic!()
                };
                V::Object(
                    fields
                        .keys()
                        .map(|k| {
                            (
                                k.clone(),
                                match k.as_str() {
                                    "score" => u(r.score.code() as u64),
                                    "terminal" => terminal_value(r.board_terminal),
                                    "threefold_available" => b(r.threefold_available),
                                    "fifty_move_available" => b(r.fifty_move_available),
                                    _ => panic!(),
                                },
                            )
                        })
                        .collect(),
                )
            }
        ),
        "evaluate_predicate" => result!(
            evaluate_predicate(
                text(field(input, "predicate_id")).as_bytes(),
                predicate_input(field(input, "input"))
            ),
            |x| obj([("result", predicate_value(x))])
        ),
        _ => panic!("operation {operation}"),
    })
}

#[test]
fn approved_direct_fixture_rows() {
    let bytes = include_bytes!("../../../conformance/chess-v0.json");
    assert!(bytes.len() < 1_048_576);
    let fixture = validate_canonical_manifest(bytes).unwrap();
    let cases = array(field(&fixture, "cases"));
    assert_eq!(cases.len(), 224);
    let mut checked = 0;
    for case in cases {
        if let Some(actual) = run_direct(case) {
            checked += 1;
            assert_eq!(
                actual,
                *field(case, "expected"),
                "{}",
                text(field(case, "name"))
            );
        }
    }
    assert_eq!(checked, 224);
}

#[test]
fn neutral_cycle_convergence_recipe() {
    assert!(neutral_cycle_observations());
}

#[test]
fn approved_bounded_history_recipes() {
    let fixture =
        validate_canonical_manifest(include_bytes!("../../../conformance/chess-v0.json")).unwrap();
    let recipes = array(field(&fixture, "recipes"));
    assert_eq!(recipes.len(), 3);
    for recipe in recipes {
        assert_eq!(text(field(recipe, "recipe")), "knight-cycle-history");
        assert_eq!(num(field(recipe, "count_cap")), 4097);
        let input = field(recipe, "input");
        let count = num(field(input, "ply_count")) as usize;
        assert!(count <= 4097);
        let cycle = hex(text(field(input, "cycle_moves_hex")));
        let final_move = hex(text(field(input, "final_move_hex")));
        let mut bytes = Vec::with_capacity(count * 2);
        for i in 0..count {
            if i + 1 == count && !final_move.is_empty() {
                bytes.extend_from_slice(&final_move)
            } else {
                let at = (i % (cycle.len() / 2)) * 2;
                bytes.extend_from_slice(&cycle[at..at + 2])
            }
        }
        assert_eq!(bytes.len() as u64, num(field(recipe, "input_bytes")));
        let ms: Vec<_> = bytes
            .chunks_exact(2)
            .map(|x| decode_move(x).unwrap())
            .collect();
        let actual = match replay_from_start(&ms) {
            Ok(r) => success(obj([("played_plies", u(r.played_plies() as u64))])),
            Err(e) => failure(e.code),
        };
        assert_eq!(
            actual,
            *field(recipe, "expected"),
            "{}",
            text(field(recipe, "name"))
        );
    }
}

#[test]
fn bounded_deterministic_legal_walk_properties() {
    let mut seed = 0x6a09_e667_f3bc_c909u64;
    for case in 0..64 {
        let mut state = replay_from_start(&[]).unwrap();
        for ply in 0..32 {
            let legal = legal_moves(&state);
            assert!(
                legal.windows(2).all(|w| w[0] < w[1]),
                "seed={seed:x} case={case} ply={ply}"
            );
            if legal.is_empty() {
                break;
            }
            seed = seed
                .wrapping_mul(6364136223846793005)
                .wrapping_add(1442695040888963407);
            let mv = legal[(seed as usize) % legal.len()];
            assert_eq!(decode_move(&encode_move(mv)).unwrap(), mv);
            let mover = Side::from_code(encode_position(state.position())[64]).unwrap();
            state = apply_move(&state, mv).unwrap();
            let rejected_snapshot = state.clone();
            assert!(apply_move(&state, mv).is_err());
            assert_eq!(state, rejected_snapshot);
            let round = decode_position(&encode_position(state.position())).unwrap();
            assert_eq!(round, *state.position());
            let local = validate_local(state.position()).unwrap();
            assert!(
                !king_in_check(&local, mover),
                "seed={seed:x} case={case} ply={ply}"
            );
        }
    }
}

fn changed_indices(before: &[u8; 67], after: &[u8; 67]) -> Vec<usize> {
    before
        .iter()
        .zip(after)
        .enumerate()
        .filter_map(|(index, (left, right))| (left != right).then_some(index))
        .collect()
}

#[test]
fn bounded_controller_pseudo_legal_and_replay_properties() {
    let prefixes = [
        "",
        "31c0",
        "31c0fad0",
        "31c0d2401950e6a014c0fad0",
        "2180e6a06200def08280be70a3109df0",
    ];
    for (case, encoded) in prefixes.into_iter().enumerate() {
        let moves = move_list(encoded);
        let replay = replay_from_start(&moves).unwrap();
        assert_eq!(replay, replay_from_start(&moves).unwrap(), "case={case}");
        let local = validate_local(replay.position()).unwrap();
        let pseudo = pseudo_legal_moves(&local);
        let legal = legal_moves(&replay);
        assert!(
            pseudo.windows(2).all(|pair| pair[0] < pair[1]),
            "case={case}"
        );
        assert!(
            legal.windows(2).all(|pair| pair[0] < pair[1]),
            "case={case}"
        );
        assert!(
            legal.iter().all(|mv| pseudo.binary_search(mv).is_ok()),
            "case={case}"
        );

        let bytes = encode_position(replay.position());
        let opposing_king = if bytes[64] == 0 { 12 } else { 6 };
        for mv in &pseudo {
            let packed = u16::from_be_bytes(encode_move(*mv));
            let destination = ((packed as u32 & 0x03f0) >> 4) as usize;
            assert_ne!(bytes[destination], opposing_king, "case={case}");
        }
        for side in [Side::FIRST, Side::SECOND] {
            for target in 0..64u8 {
                let controllers =
                    controls_square(replay.position(), side, Square::from_index(target).unwrap());
                assert!(
                    controllers.windows(2).all(|pair| pair[0] < pair[1]),
                    "case={case} side={} target={target}",
                    side.code()
                );
            }
        }
    }
}

#[test]
fn exact_state_field_and_promotion_properties() {
    let initial = replay_from_start(&[]).unwrap();
    let e4 = apply_move(&initial, decode_move(&hex("31c0")).unwrap()).unwrap();
    let initial_bytes = encode_position(initial.position());
    let e4_bytes = encode_position(e4.position());
    assert_eq!(changed_indices(&initial_bytes, &e4_bytes), [12, 28, 64, 66]);
    assert_eq!((e4_bytes[64], e4_bytes[65], e4_bytes[66]), (1, 15, 21));
    assert_eq!(e4.halfmove_clock(), 0);
    let key = repetition_key(&e4);
    assert_eq!(&key[..66], &e4_bytes[..66]);
    assert_eq!(key[66], 0);

    let nf6 = apply_move(&e4, decode_move(&hex("fad0")).unwrap()).unwrap();
    let nf6_bytes = encode_position(nf6.position());
    assert_eq!(changed_indices(&e4_bytes, &nf6_bytes), [45, 62, 64, 66]);
    assert_eq!((nf6_bytes[64], nf6_bytes[65], nf6_bytes[66]), (0, 15, 0));
    assert_eq!(nf6.halfmove_clock(), 1);
    assert_eq!(repetition_key(&nf6), nf6_bytes);

    let rook_return = replay_from_start(&move_list("3d70c2801cf0a2003c70c690")).unwrap();
    assert_eq!(encode_position(rook_return.position())[65], 14);
    let effective_ep = replay_from_start(&move_list("2100ce3041808db031c0")).unwrap();
    assert_eq!(
        repetition_key(&effective_ep),
        encode_position(effective_ep.position())
    );
    assert_eq!(
        replay_from_start(&move_list("1950fad05460b7e0"))
            .unwrap()
            .halfmove_clock(),
        4
    );
    assert_eq!(
        replay_from_start(&move_list("31c0ce307230"))
            .unwrap()
            .halfmove_clock(),
        0
    );

    let promotion_root = replay_from_start(&move_list("2180e6a06200def08280be70a3109df0")).unwrap();
    let legal = legal_moves(&promotion_root);
    let choices = ["c792", "c794", "c796", "c798"];
    for (encoded, piece) in choices.into_iter().zip([5, 4, 3, 2]) {
        let mv = decode_move(&hex(encoded)).unwrap();
        assert!(legal.binary_search(&mv).is_ok());
        let promoted = apply_move(&promotion_root, mv).unwrap();
        let bytes = encode_position(promoted.position());
        assert_eq!(bytes[57], piece);
        assert_eq!(promoted.halfmove_clock(), 0);
    }
}

#[test]
fn named_chess_event_mutants_are_killed_directly() {
    let fixture =
        validate_canonical_manifest(include_bytes!("../../../conformance/chess-v0.json")).unwrap();
    let cases = array(field(&fixture, "cases"));
    let actual = |name: &str| {
        let case = cases
            .iter()
            .find(|c| text(field(c, "name")) == name)
            .unwrap();
        run_direct(case).unwrap()
    };
    let pinned = actual("geometry-pinned-piece-still-controls");
    assert_ne!(
        field(field(&pinned, "success"), "squares"),
        &V::Array(vec![]),
        "mutant: pinned pieces do not control"
    );
    assert_ne!(
        actual("geometry-king-capture-removes-blocker-self-check"),
        success(obj([])),
        "mutant: king safety checked before capture removal"
    );
    assert_ne!(
        actual("castling-failure-origin-safe-transit-attack"),
        success(obj([])),
        "mutant: castling skips transit"
    );
    assert_ne!(
        actual("castling-attacked-rook-allowed"),
        failure(46),
        "mutant: attacked rook forbids castle"
    );
    assert_ne!(
        actual("castling-queenside-b-square-attacked-allowed"),
        failure(46),
        "mutant: attacked b square forbids castle"
    );
    assert_ne!(
        actual("en-passant-pinned-self-exposing-capture"),
        success(obj([])),
        "mutant: captured EP pawn remains during king-safety test"
    );
    let ep = actual("en-passant-nominal-key-normalizes-away");
    assert_eq!(
        text(field(field(&ep, "success"), "repetition_key_hex"))
            .as_bytes()
            .last(),
        Some(&b'0'),
        "mutant: nominal EP always enters repetition"
    );
    assert_ne!(
        actual("promotion-missing"),
        success(obj([])),
        "mutant: omitted promotion becomes queen"
    );
    let terminal = actual("terminal-stalemate-precedes-common-dead");
    assert_eq!(
        num(field(field(&terminal, "success"), "terminal")),
        2,
        "mutant: stalemate tested as mate/dead first"
    );
    let occurrence = actual("history-repetition-occurrence-one");
    assert_eq!(
        num(field(
            field(field(&occurrence, "success"), "result"),
            "current_key_occurrences"
        )),
        1,
        "mutant: initial occurrence omitted"
    );
    for name in [
        "history-pawn-move-resets-halfmove",
        "history-capture-resets-halfmove",
    ] {
        let x = actual(name);
        assert_eq!(
            num(field(
                field(field(&x, "success"), "result"),
                "halfmove_clock"
            )),
            0,
            "mutant: pawn/capture does not reset halfmove"
        );
    }
    for name in ["event-agreement-zero-plies", "event-agreement-one-ply"] {
        assert_eq!(
            actual(name),
            failure(56),
            "mutant: premature agreement allowed"
        );
    }
}

fn move_list(encoded: &str) -> Vec<Move> {
    hex(encoded)
        .chunks_exact(2)
        .map(|bytes| decode_move(bytes).unwrap())
        .collect()
}

#[test]
fn public_side_codes_are_closed() {
    assert_eq!(Side::from_code(0).unwrap().code(), 0);
    assert_eq!(Side::from_code(1).unwrap().code(), 1);
    assert_eq!(Side::from_code(2), None);
}

#[test]
fn public_square_indices_are_closed() {
    assert_eq!(Square::from_index(0).unwrap().index(), 0);
    assert_eq!(Square::from_index(63).unwrap().index(), 63);
    assert_eq!(Square::from_index(64), None);
}

#[test]
fn public_terminal_and_closure_payloads_use_validated_side() {
    let first = Side::FIRST;
    let mate = BoardTerminal::Checkmate(first);
    assert_eq!(mate.code(), 1);
    let cause = ClosureCause::Board(BoardClosure::Checkmate(first));
    assert!(matches!(
        cause,
        ClosureCause::Board(BoardClosure::Checkmate(side)) if side == first
    ));
}

#[test]
fn local_count_precedence_checks_both_kings_first() {
    let mut bytes = encode_position(&position(&s(
        "0402030506030204010101010101010100000000000000000000000000000000\
         0000000000000000000000000000000007070707070707070a08090b0c09080a\
         000f00",
    )));
    bytes[60] = 0;
    bytes[20] = 1;
    assert_eq!(
        validate_local(&decode_position(&bytes).unwrap())
            .unwrap_err()
            .code,
        17
    );
}

#[test]
fn off_home_two_file_king_move_is_geometry() {
    let state = replay_from_start(&move_list("3960dae03140c28010c0a200")).unwrap();
    let error = apply_move(&state, decode_move(&hex("30e0")).unwrap()).unwrap_err();
    assert_eq!(error.code, 50);
}

#[test]
fn occupied_pawn_double_destination_is_pawn_advance() {
    let state = replay_from_start(&move_list("2100d240418091c0")).unwrap();
    let error = apply_move(&state, decode_move(&hex("31c0")).unwrap()).unwrap_err();
    assert_eq!(error.code, 52);
}

#[test]
fn closed_discovered_transition_precedes_square_shape() {
    let state = replay_from_start(&move_list("3550d24039e0edf0")).unwrap();
    let result = evaluate_predicate(
        b"chess.discovered_attack_check",
        PredicateInput::Discovered(state, decode_move(&hex("4180")).unwrap(), None, None),
    );
    assert_eq!(result.unwrap_err().code, 34);
}

#[test]
fn mating_aggregate_resources_precede_side_and_material() {
    let initial = replay_from_start(&[]).unwrap();
    let nodes = vec![TreeNode { edges: vec![] }; 4097];
    assert_eq!(
        evaluate_predicate(
            b"chess.finite_mating_geometry",
            PredicateInput::MatingTree(initial.clone(), None, nodes),
        )
        .unwrap_err()
        .code,
        36
    );
    let edge = TreeEdge {
        mv: decode_move(&hex("4180")).unwrap(),
        child: 0,
    };
    assert_eq!(
        evaluate_predicate(
            b"chess.finite_mating_geometry",
            PredicateInput::MatingTree(
                initial,
                Some(Side::FIRST),
                vec![TreeNode {
                    edges: vec![edge; 257]
                }],
            ),
        )
        .unwrap_err()
        .code,
        36
    );
}
