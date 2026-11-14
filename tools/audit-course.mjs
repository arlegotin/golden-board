// Course data/action boundary only; no subject rules, truth oracle or renderer fork.
import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {decodeDocument,Player} from '../mechanism/player.mjs';

const input=JSON.parse(readFileSync(0,'utf8'));
const documents=Object.fromEntries(Object.entries(input.documents).map(([id,data])=>[id,decodeDocument(Buffer.from(data,'hex'))]));
let frames=0,actions=0,rejected=0,scripted=0;
function act(player,action){
  const result=player.action(action);assert.equal(result.ok,true,result.error);actions++;return result.packet;
}
function refuse(player,action){
  const before=player.packet();const result=player.action(action);
  assert.equal(result.ok,false);assert.deepEqual(result.packet,before);rejected++;
}
function path(document,origin,target){
  const pending=[[origin,[]]],seen=new Set();
  while(pending.length){
    const [current,links]=pending.shift();if(current===target)return links;
    if(seen.has(current))continue;seen.add(current);
    for(const next of document.records[current].links??[])pending.push([next,[...links,next]]);
  }
  assert.fail(`Page ${target} is unreachable without a response from ${origin}`);
}
function navigate(player,target){
  for(const next of path(player.document,player.packet().node,target))act(player,{link:next});
}
for(const c of input.cases){
  const document=documents[c.section];assert(document);
  const player=()=>new Player(document,c.worked);
  const page=document.records[c.practice];
  assert.deepEqual(page.accepted,[c.expected]);
  let scriptFrame=0;
  const scriptPlayer=c.scripts?.length?player():null;
  if(scriptPlayer)navigate(scriptPlayer,c.practice);
  for(const script of c.scripts??[]){
    const p=scriptPlayer;
    for(const row of script){
      const before=p.packet().selection;
      if(row.action){
        if(row.ok)act(p,row.action);else refuse(p,row.action);
      }
      const packet=p.packet();
      assert.deepEqual(packet.selection,row.selection,'Scripted selection differs from the mechanism');
      assert.equal(packet.committed?.accepted??null,row.accepted,'Scripted commit differs from the mechanism');
      assert.equal(packet.node,row.accepted===null?c.practice:row.accepted?c.success:c.failure);
      if(c.display_contract){
        const contract=c.display_contract;
        const glyphs=values=>[...values.map(v=>contract.number_glyphs[v]),...Array(3-values.length).fill(contract.padding_glyph)];
        const shown=c.frames[c.script_display??c.worked][scriptFrame];
        assert.deepEqual(contract.before_cells.map(i=>shown[i]),glyphs(before));
        assert.deepEqual(contract.after_cells.map(i=>shown[i]),glyphs(packet.selection));
        assert.deepEqual(contract.response_cells.map(i=>shown[i]),glyphs(row.operation==='commit'?packet.committed.response:[]));
        assert.equal(shown[contract.commit_flag_cell],contract.number_glyphs[row.accepted===null?0:1]);
        assert.equal(shown[contract.feedback_cell],row.accepted===null?0:row.accepted?6:7);
        for(const cell of contract.selected_cells??[])
          assert.equal(shown[cell.cell],packet.selection.includes(cell.id)?5:cell.unselected,'Grouped pictured option differs from actual region selection');
      }
      scriptFrame++;
      scripted++;
    }
  }
  for(const [node,expectedFrames] of Object.entries(c.frames)){
    const p=player();navigate(p,+node);
    for(let index=0;index<expectedFrames.length;index++){
      if(p.packet().step_count)act(p,{seek:index});
      assert.deepEqual(p.packet().frame.cells,expectedFrames[index]);frames++;
    }
    if(p.packet().step_count){
      act(p,{seek:0});assert.deepEqual(p.packet().frame.cells,expectedFrames[0]);
      refuse(p,{seek:expectedFrames.length});
    }
  }
  const attempt=(values,accepted)=>{
    const p=player();navigate(p,c.practice);
    for(const value of values)act(p,{select:value});
    const packet=act(p,{commit:true});
    assert.equal(packet.committed.accepted,accepted);
    assert.equal(packet.node,accepted?c.success:c.failure);
    assert.deepEqual(packet.committed.response,page.shape===2?[...values].sort((a,b)=>a-b):values);
    refuse(p,{select:page.choices[0]});
    const number=packet.attempt;navigate(p,c.practice);
    assert.equal(p.packet().committed,null);assert(p.packet().attempt>number);
    return p;
  };
  const p=player();navigate(p,c.practice);const original=p.packet();
  act(p,{select:page.choices[0]});assert.equal(p.packet().committed,null);
  if(page.shape===2){act(p,{select:page.choices[0]});assert.deepEqual(p.packet().selection,[]);}
  if(page.shape===1&&page.choices.length>1){act(p,{select:page.choices[1]});assert.deepEqual(p.packet().selection,[page.choices[1]]);}
  act(p,{reset:true});assert.deepEqual(p.packet().selection,[]);assert.deepEqual(p.packet().frame,original.frame);
  refuse(p,{select:65535});
  if(page.shape===3){
    for(let i=0;i<page.choices.length;i++)act(p,{select:page.choices[0]});
    refuse(p,{select:page.choices[0]});act(p,{reset:true});
  }
  attempt(page.shape===2?[...c.expected].reverse():c.expected,true);
  attempt(c.expected.length?c.expected.slice(0,-1):[page.choices[0]],false);
  if(page.shape===3&&c.expected.length>1){
    const reordered=[...c.expected].sort((a,b)=>a-b);
    if(JSON.stringify(reordered)!==JSON.stringify(c.expected))attempt(reordered,false);
  }
  for(const query of c.queries??[]){
    assert(query.option_ids.includes(query.correct_region));
    const wrong=query.option_ids.find(id=>id!==query.correct_region);
    attempt(c.expected.map(id=>id===query.correct_region?wrong:id),false);
    const extra=[...c.expected,wrong];if(page.shape===2)attempt(extra,false);
  }
  const passive=player();navigate(passive,c.passive);assert.equal(passive.packet().shape,0);
}
console.log(JSON.stringify({cases:input.cases.length,all_frames_exact:true,all_actions_exact:true,
  passive_without_response:true,compared_frames:frames,successful_actions:actions,atomic_rejections:rejected,scripted_action_checks:scripted,
  scope:'Actual course records and generic mechanism only; no recipient understanding or full-course completion inferred'}));
