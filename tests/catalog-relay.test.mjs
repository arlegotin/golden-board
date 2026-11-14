import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync, readFileSync} from 'node:fs';

test('batch catalog preserves one continuous player and rejected operations', async()=>{
  const url=new URL('../mechanism/catalog-relay.mjs',import.meta.url);
  assert.ok(existsSync(url),'The neutral continuous batch adapter is missing');
  const {catalogRelay}=await import(url);
  const mini=Buffer.from(readFileSync(new URL('../spec/vectors/current-mini.hex',import.meta.url),'utf8').replace(/\s/g,''),'hex');
  const result=catalogRelay([[9,mini]],[{open:{document:9,entry:257}},{action:{seek:2}},{action:{seek:999}},{open:{document:999}}]);
  assert.deepEqual(result.operations.map(r=>r.ok),[true,true,false,false]);
  assert.deepEqual(result.operations[1].packet,result.operations[2].packet);
  assert.deepEqual(result.operations[2].packet,result.operations[3].packet);
  assert.equal(result.operations[1].packet.step,2);
  assert.ok(result.operations[1].packet.glyphs_sha256);
  assert.equal(result.operations[1].packet.glyphs,undefined);
});
