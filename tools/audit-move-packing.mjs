// Narrow independent bit-mask interpretation. No chess rules or source import.
import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {decodeDocument,Player} from '../mechanism/player.mjs';
import {Catalog} from '../mechanism/catalog.mjs';
const input=JSON.parse(readFileSync(0,'utf8'));
const old=decodeDocument(Buffer.from(input.original,'hex')),packed=decodeDocument(Buffer.from(input.packed,'hex'));
assert.deepEqual(old.entries,packed.entries);let moves=0,frames=0,reverseSeeks=0;
const catalog=new Catalog([[2,Buffer.from(input.packed,'hex')]]);
assert.deepEqual(catalog.list(),[{id:2,entries:old.entries}]);
for(const entry of old.entries){
  const a=old.records[entry],b=packed.records[entry];
  assert.deepEqual(a.initial,b.initial);assert.deepEqual(a.steps,b.steps);
  assert.deepEqual(packed.records[b.data[2]].values,[16,1,6,6,3]);
  const source=old.records[a.data[0]],table=packed.records[b.data[0]];assert.equal(table.cols,1);
  const values=[];
  for(const v of table.values){
    assert.equal(v&0x8000,0);assert(v%8<=4);
    values.push((v&0x7e00)>>>9,(v&0x01f8)>>>3,v&0x0007);moves++;
  }
  assert.deepEqual(values,source.values);
  assert.deepEqual(old.records[a.data[1]],packed.records[b.data[1]]);
  const p=new Player(old,entry);assert.equal(catalog.open(2,entry).ok,true);const q=catalog;
  for(let i=0;i<=a.steps.length;i++){
    assert.equal(p.action({seek:i}).ok,true);assert.equal(q.action({seek:i}).ok,true);
    assert.deepEqual(p.packet().frame,q.packet().frame);frames++;
  }
  for(const i of [a.steps.length,0,Math.floor(a.steps.length/2),a.steps.length,Math.floor(a.steps.length/2)]){
    p.action({seek:i});assert.equal(q.action({seek:i}).ok,true);assert.deepEqual(p.packet().frame,q.packet().frame);reverseSeeks++;
  }
}
process.stdout.write(JSON.stringify({games:old.entries.length,moves,frames,reverse_seeks:reverseSeeks,actual_catalog_entries:old.entries.length,all_moves_exact:true,all_literal_playback_exact:true})+'\n');
