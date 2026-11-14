// Complete passive presentation of inert documents through the existing player.
import { readFileSync, writeFileSync, realpathSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { decodeDocument, Player } from './player.mjs';

export function exportPassive(bytes) {
  const document = decodeDocument(bytes);
  const queue = document.entries.map(entry => ({ entry, actions: [] }));
  const seen = new Set();
  const nodes = [];
  while (queue.length) {
    const route = queue.shift();
    const player = new Player(document, route.entry);
    for (const action of route.actions) {
      const result = player.action(action);
      if (!result.ok) throw Error(`Invalid passive route: ${result.error}`);
    }
    const initial = player.packet();
    if (seen.has(initial.node)) continue;
    seen.add(initial.node);
    const frames = [initial];
    for (let step = 1; step <= initial.step_count; step++) {
      const result = player.action({ seek: step });
      if (!result.ok) throw Error(`Invalid passive trace: ${result.error}`);
      frames.push(result.packet);
    }
    nodes.push({ ...route, frames });
    for (const link of initial.links)
      if (!seen.has(link)) queue.push({ entry: route.entry, actions: [...route.actions, { link }] });
  }
  return { entries: document.entries, nodes };
}

if (process.argv[1] && import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href) {
  const [, , input, output] = process.argv;
  writeFileSync(output, JSON.stringify(exportPassive(readFileSync(input)), null, 2) + '\n');
}
