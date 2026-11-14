// Narrow independent original-SAN reference, never consumes Python move output.
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { Chess } = require(process.argv[3]);
const raw = readFileSync(process.argv[2]);
const spans = raw.toString('utf8').split(/\r?\n(?=\[Event )/);
const score = { '1-0': 0, '0-1': 1, '1/2-1/2': 2 };
const promotions = { q: 1, r: 2, b: 3, n: 4 };
const cell = name => (8 - Number(name[1])) * 8 + name.charCodeAt(0) - 97;

function parse(text, sourceOrdinal) {
  const moves = [], positions = [];
  try {
    const boundary = /\r?\n[ \t]*\r?\n/.exec(text);
    if (!boundary) throw Error('Missing header boundary');
    const header = text.slice(0, boundary.index), body = text.slice(boundary.index + boundary[0].length);
    const tags = new Map();
    for (const line of header.split(/\r?\n/)) {
      const tag = /^\[([A-Za-z0-9_]+) "((?:[^"\\]|\\["\\])*)"\]$/.exec(line);
      if (!tag || tags.has(tag[1])) throw Error('Malformed or duplicate tag');
      tags.set(tag[1], tag[2]);
    }
    if (tags.has('FEN') || tags.has('Variant') || (tags.get('SetUp') ?? '0') !== '0' || !Object.hasOwn(score, tags.get('Result'))) {
      throw Error('Unsupported start/variant or unconcluded Result');
    }
    const game = new Chess();
    function ending() {
      if (game.isCheckmate()) return 'checkmate';
      if (game.isStalemate()) return 'stalemate';
      const pieces = game.board().flat().filter(Boolean);
      if (pieces.length === 2 || (pieces.length === 3 && pieces.filter(p => p.type === 'b' || p.type === 'n').length === 1)) return 'common-dead';
      return 'active';
    }
    function observe(move = null) {
      const native = game.fen({ forceEnpassantSquare: true });
      // This diagnostic convention retains every immediate double-move target.
      // The pinned engine may have discarded a target with no adjacent pawn.
      const double = move?.piece === 'p' && Math.abs(Number(move.from[1]) - Number(move.to[1])) === 2;
      const target = double ? move.from[0] + String((Number(move.from[1]) + Number(move.to[1])) / 2) : '-';
      const fields = native.split(' '); fields[3] = target;
      positions.push({ fen: fields.join(' '), native_fen: native,
        ep_derivation: { target, pawn_double_move: double, from: move?.from ?? null, to: move?.to ?? null,
          scope: 'Immediate diagnostic target; not a legal-en-passant repetition key.' } });
    }
    observe();
    const tokens = body.trim().split(/\s+/); let numbered = false, result = null;
    for (let index = 0; index < tokens.length; index++) {
      const token = tokens[index];
      const number = /^([1-9][0-9]*)(\.|\.\.\.)$/.exec(token);
      if (number) {
        if (numbered || Number(number[1]) !== Number(game.fen().split(' ')[5]) || number[2] !== (game.turn() === 'w' ? '.' : '...')) throw Error('Wrong move number');
        numbered = true; continue;
      }
      if (Object.hasOwn(score, token) || token === '*') {
        if (numbered || index !== tokens.length - 1 || token !== tags.get('Result') || token === '*') throw Error('Unfinished/mismatched/trailing result');
        result = token; break;
      }
      if (game.turn() === 'w' && !numbered) throw Error('Missing white move number');
      if (ending() !== 'active') throw Error('Continuation after board ending');
      const move = game.move(token, { strict: true });
      if (move.san !== token) throw Error('Noncanonical SAN: ' + token + ' versus ' + move.san);
      moves.push([cell(move.from), cell(move.to), promotions[move.promotion] ?? 0]);
      observe(move); numbered = false;
    }
    if (result === null || !moves.length) throw Error('Missing complete main line/result');
    const end = ending(), value = score[result];
    if (end === 'checkmate' && value !== (game.turn() === 'w' ? 1 : 0)) throw Error('Score contradicts checkmate');
    if ((end === 'stalemate' || end === 'common-dead') && value !== 2) throw Error('Score contradicts board draw');
    return { source_ordinal: sourceOrdinal, status: 'accepted', game: { moves, positions, score: value, board_end: end } };
  } catch (error) {
    return { source_ordinal: sourceOrdinal, status: 'rejected', error: error.message,
      next_ply: moves.length + 1, partial_moves: moves, partial_positions: positions };
  }
}

console.log(JSON.stringify({ source_sha256: createHash('sha256').update(raw).digest('hex'),
  node_version: process.version, scope: 'Independent original SAN legal-core and diagnostic FEN; no automatic fivefold/75-move adjudication',
  records: spans.map((span, index) => parse(span, index + 1)) }));
