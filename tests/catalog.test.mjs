import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {Catalog} from '../mechanism/catalog.mjs';

const mini=Buffer.from(readFileSync(new URL('../spec/vectors/current-mini.hex',import.meta.url),'utf8').replace(/\s/g,''),'hex');
test('generic catalog opens only declared document entries and preserves invalid state',()=>{
  const c=new Catalog([[9,mini],[2,mini]]);
  assert.deepEqual(c.list(),[{id:2,entries:[512,257]},{id:9,entries:[512,257]}]);
  assert.equal(c.open(9,257).ok,true);assert.equal(c.packet().document,9);
  assert.equal(c.action({seek:2}).ok,true);const before=c.packet();
  assert.equal(c.open(99,257).ok,false);assert.deepEqual(c.packet(),before);
  assert.equal(c.open(2,258).ok,false);assert.deepEqual(c.packet(),before);
  assert.equal(c.open(2,512).ok,true);assert.equal(c.packet().document,2);
  assert.equal(c.action({select:10}).ok,true);assert.equal(c.action({commit:true}).packet.committed.accepted,true);
  assert.throws(()=>new Catalog([[1,mini],[1,mini]]));
});

test('actual carried anthology catalog opens all64 entries and reverse seeks faithfully',()=>{
  const bytes=readFileSync(new URL('../evidence/S03-shared-anthology/actual-document.bin',import.meta.url));
  assert.equal(createHash('sha256').update(bytes).digest('hex'),'c677a9e407854f2388831573ad2fd2296f2523a160f509e938dfbf409a3ba737');
  const current=Buffer.concat([bytes.subarray(0,2),bytes.subarray(3)]);
  const c=new Catalog([[2,current]]);const entries=c.list()[0].entries;
  assert.equal(entries.length,64);
  for(const entry of entries){assert.equal(c.open(2,entry).ok,true);assert.equal(c.packet().node,entry);assert.equal(c.packet().step,0);}
  for(const ordinal of [1,12,32,55,64]){
    c.open(2,entries[ordinal-1]);const n=c.packet().step_count;
    assert.equal(c.action({seek:n}).ok,true);const final=c.packet().frame;
    assert.equal(c.action({seek:0}).ok,true);assert.equal(c.action({seek:n}).ok,true);
    assert.deepEqual(c.packet().frame,final);
    const before=c.packet();assert.equal(c.action({seek:n+1}).ok,false);assert.deepEqual(c.packet(),before);
  }
});
