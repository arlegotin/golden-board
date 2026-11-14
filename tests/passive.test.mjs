import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { exportPassive } from '../mechanism/passive.mjs';
import { decodeDocument, Player } from '../mechanism/player.mjs';

const bytes = Buffer.from(readFileSync(new URL('../spec/vectors/current-mini.hex', import.meta.url), 'utf8').replace(/\s/g, ''), 'hex');

test('complete non-chess traces retain intermediate states and carried table', () => {
  // A final-packet-only export would lose both the initial and middle frames.
  const result = exportPassive(bytes);
  const trace = result.nodes.find(node => node.frames[0].node === 516);
  assert.deepEqual(trace.frames.map(packet => packet.frame.cells), [
    [0, 1, 1, 1, 0, 1], [1, 1, 1, 1, 0, 1], [1, 1, 1, 1, 0, 0]]);
  assert.deepEqual(trace.frames.map(packet => packet.step), [0, 1, 2]);
  assert.deepEqual(trace.frames[1].data[0].values, [0, 1, 2, 3, 4, 5]);
  assert.equal(trace.frames[1].data[0].rows, 2);
  assert.equal(trace.frames[1].data[0].cols, 3);
  assert.equal(trace.frames[1].frame.regions[1][1], 5);
});

test('cyclic passive closure uses original entries and exposed links only', () => {
  const result = exportPassive(bytes);
  assert.deepEqual(result.entries, [512, 257]);
  assert.deepEqual(result.nodes.map(node => node.frames[0].node).sort((a, b) => a - b), [257, 512, 516, 517, 518]);
  assert.equal(result.nodes.reduce((sum, node) => sum + node.frames.length, 0), 9);
  for (const node of result.nodes) {
    const player = new Player(decodeDocument(bytes), node.entry);
    for (const action of node.actions) {
      assert.deepEqual(Object.keys(action), ['link']);
      assert.equal(player.action(action).ok, true);
    }
    assert.equal(player.packet().node, node.frames[0].node);
  }
  assert.equal(JSON.stringify(result).includes('"accepted"'), false);
});

test('a different matrix shape is exported without changing or interpreting input', () => {
  const fixture = Buffer.from(bytes);
  // Change the literal six-cell initial matrix from 2x3 to 1x6.
  let offset = 10;
  while (fixture.readUInt16BE(offset + 1) !== 256) offset += 7 + fixture.readUInt32BE(offset + 3);
  fixture[offset + 7] = 1; fixture[offset + 8] = 6;
  const before = Buffer.from(fixture);
  const result = exportPassive(fixture);
  assert.equal(result.nodes[0].frames[0].frame.rows, 1);
  assert.equal(result.nodes[0].frames[0].frame.cols, 6);
  assert.deepEqual(fixture, before);
});
