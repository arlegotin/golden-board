import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { decodeDocument, Player, renderSvg } from '../mechanism/player.mjs';

const bytes = Buffer.from(readFileSync(new URL('../spec/vectors/current-mini.hex', import.meta.url), 'utf8').replace(/\s/g, ''), 'hex');
const document = () => decodeDocument(bytes);

test('literal miniature is decoded as non-chess data', () => {
  const doc = document();
  assert.deepEqual(doc.entries, [512, 257]);
  assert.equal(Object.keys(doc.records).length, 15);
  const player = new Player(doc);
  assert.deepEqual(player.packet().frame.cells, [0, 1, 1, 1, 0, 1]);
  assert.match(renderSvg(player.packet()), /<svg/);
});

test('select does not commit; reset leaves empty commit distinguishable', () => {
  const player = new Player(document());
  assert.equal(player.action({ select: 10 }).ok, true);
  assert.equal(player.packet().node, 512);
  assert.equal(player.packet().committed, null);
  assert.deepEqual(player.packet().selection, [10]);
  player.action({ reset: true });
  assert.deepEqual(player.packet().selection, []);
  player.action({ commit: true });
  assert.equal(player.packet().node, 515);
  assert.deepEqual(player.packet().committed.response, []);
  assert.deepEqual(player.packet().frame.cells, [2, 2, 2, 2, 2, 2]);
});

test('carried correct/wrong feedback and retry start separate attempts', () => {
  const player = new Player(document());
  player.action({ select: 20 }); player.action({ commit: true });
  assert.equal(player.packet().node, 515);
  const committed = structuredClone(player.packet().committed);
  assert.equal(player.action({ reset: true }).ok, false);
  assert.deepEqual(player.packet().committed, committed);
  player.action({ link: 512 }); player.action({ select: 10 }); player.action({ commit: true });
  assert.equal(player.packet().node, 514);
  assert.deepEqual(player.packet().committed.response, [10]);
  assert.equal(player.packet().attempt, 2);
});

test('partial updates preserve every unaffected cell and seek is exact', () => {
  const player = new Player(document());
  player.action({ link: 516 }); player.action({ seek: 1 });
  assert.deepEqual(player.packet().frame.cells, [1, 1, 1, 1, 0, 1]);
  player.action({ seek: 2 });
  assert.deepEqual(player.packet().frame.cells, [1, 1, 1, 1, 0, 0]);
  const before = player.packet();
  assert.equal(player.action({ seek: 3 }).ok, false);
  assert.deepEqual(player.packet(), before);
  player.action({ link: 518 });
  assert.deepEqual(player.packet().frame.cells, [1, 1, 1, 1, 0, 0]);
});

test('single and sequence shapes follow data with bounded buffers', () => {
  const one = document(); one.records[512].shape = 1;
  const single = new Player(one);
  single.action({ select: 20 }); single.action({ select: 10 });
  assert.deepEqual(single.packet().selection, [10]);
  const ordered = document(); ordered.records[512].shape = 3;
  ordered.records[512].accepted = [[20, 10]];
  const sequence = new Player(ordered);
  sequence.action({ select: 20 }); sequence.action({ select: 10 });
  assert.equal(sequence.action({ select: 10 }).ok, false);
  assert.deepEqual(sequence.packet().selection, [20, 10]);
  sequence.action({ commit: true }); assert.equal(sequence.packet().node, 514);
});

test('unknown, combined and out-of-scope actions are atomic', () => {
  const player = new Player(document()); const before = player.packet();
  for (const action of [{ select: 99 }, { link: 999 }, { seek: 1 },
    { select: 10, commit: true }, { commit: false }, { unknown: 1 }]) {
    assert.equal(player.action(action).ok, false);
    assert.deepEqual(player.packet(), before);
  }
  const packet = player.packet(); packet.frame.cells[0] = 99;
  assert.deepEqual(player.packet(), before);
});

test('different dimensions and token count need no player changes', () => {
  const doc = document();
  doc.records[256].rows = 1; doc.records[256].cols = 6;
  const player = new Player(doc);
  assert.equal(player.packet().frame.rows, 1);
  assert.equal(player.packet().frame.cols, 6);
  assert.equal(Object.keys(player.packet().glyphs).length, 3);
});

test('malformed binary lengths, mask padding and unknown types fail', () => {
  assert.throws(() => decodeDocument(Buffer.concat([bytes, Buffer.of(0)])));
  assert.throws(() => decodeDocument(bytes.subarray(0, bytes.length - 1)));
  const huge = Buffer.from(bytes); huge.fill(255, 13, 17);
  assert.throws(() => decodeDocument(huge));
  const padding = Buffer.from(bytes); padding[29] |= 1;
  assert.throws(() => decodeDocument(padding));
  const unknown = Buffer.from(bytes); unknown[10] = 99;
  assert.throws(() => decodeDocument(unknown));
});
