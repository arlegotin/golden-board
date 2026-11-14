// Independent original-SAN path: no production parser/move stream is imported.
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { Chess } = require(process.argv[3]);
const text = readFileSync(process.argv[2], 'utf8');
const first = text.split(/\n(?=\[Event )/)[0];
const parts = first.split(/\r?\n[ \t]*\r?\n/);
if (parts.length < 2) throw Error('Missing independent record boundary');
const tag = parts[0].match(/^\[Result "(1-0|0-1|1\/2-1\/2)"\]$/m);
if (!tag) throw Error('Missing concluded result');
const game = new Chess(); const moves = []; const positions = [];
const observe = () => { const [board, turn] = game.fen().split(' '); positions.push({ board, turn: turn === 'w' ? 0 : 1 }); };
const cell = name => (8 - Number(name[1])) * 8 + name.charCodeAt(0) - 97;
const promotion = { q: 1, r: 2, b: 3, n: 4 };
observe();
const tokens = parts.slice(1).join('\n\n').trim().split(/\s+/);
let result = null;
for (let index = 0; index < tokens.length; index++) {
  const token = tokens[index];
  if (/^[1-9][0-9]*\.(\.\.)?$/.test(token)) continue;
  if (/^(1-0|0-1|1\/2-1\/2)$/.test(token)) {
    if (index !== tokens.length - 1 || token !== tag[1]) throw Error('Mismatched independent result');
    result = token; break;
  }
  const move = game.move(token, { strict: true });
  moves.push([cell(move.from), cell(move.to), promotion[move.promotion] ?? 0]); observe();
}
if (!result) throw Error('Missing independent final marker');
console.log(JSON.stringify({ moves, positions }));
