// Mechanical document relay. No domain rules or assessment answers.
import { readFileSync, writeFileSync, realpathSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { decodeDocument, Player } from './player.mjs';

export function relay(bytes, request) {
  if (!request || !Array.isArray(request.actions)) throw Error('An actions array is required');
  const player = new Player(decodeDocument(bytes), request.entry);
  const action_log = [];
  for (const action of request.actions) {
    const before = structuredClone(player.state);
    const result = player.action(action);
    action_log.push({ action, before, after: structuredClone(player.state), ok: result.ok,
      ...(result.ok ? {} : { error: result.error }) });
  }
  return { ...player.packet(), action_log };
}

if (process.argv[1] && import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href) {
  const [, , documentPath, requestPath, outputPath] = process.argv;
  const packet = relay(readFileSync(documentPath), JSON.parse(readFileSync(requestPath, 'utf8')));
  writeFileSync(outputPath, JSON.stringify(packet, null, 2) + '\n');
}
