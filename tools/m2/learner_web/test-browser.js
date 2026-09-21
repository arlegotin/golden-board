"use strict";
// Exercises actual offline HTML controls and a downloaded answer file via CDP.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const [scratch,packet,ownerPath]=process.argv.slice(2);
if(!scratch)throw new Error('provide the owned browser scratch directory');
const port=fs.readFileSync(path.join(scratch,'profile/DevToolsActivePort'),'utf8').split('\n')[0];
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function main(){
 const targets=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();
 const target=targets.find(value=>value.type==='page');
 const socket=new WebSocket(target.webSocketDebuggerUrl),pending=new Map(),errors=[],requests=[];let serial=0;
 socket.onmessage=event=>{const value=JSON.parse(event.data);if(value.id){const promise=pending.get(value.id);pending.delete(value.id);value.error?promise.reject(new Error(JSON.stringify(value.error))):promise.resolve(value.result);}else if(value.method==='Runtime.exceptionThrown')errors.push(value.params);else if(value.method==='Network.requestWillBeSent')requests.push(value.params.request.url);};
 await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
 const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});
 const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw new Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
 const click=selector=>evaluate(`(()=>{const node=document.querySelector(${JSON.stringify(selector)});if(!node||node.disabled||node.hidden)throw new Error('unavailable control '+${JSON.stringify(selector)});node.click();return true;})()`);
 try{
  await send('Page.enable');await send('Runtime.enable');await send('Network.enable');
  await send('Network.setBlockedURLs',{urls:['http://*','https://*']});
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1050,deviceScaleFactor:1,mobile:false});
  fs.mkdirSync(path.join(scratch,'downloads'),{recursive:true});
  const downloadDir=fs.mkdtempSync(path.join(scratch,'downloads/run-'));
  await send('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:downloadDir});
   await send('Page.navigate',{url:pathToFileURL(path.join(packet,'index.html')).href});
  for(let i=0;i<100;i++){if(await evaluate("!!document.getElementById('lesson') && !document.getElementById('lesson').hidden"))break;await sleep(50);}
  assert.equal(await evaluate("document.getElementById('lesson').hidden"),false);
  const capture=async name=>{const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(path.join(scratch,name+'.png'),Buffer.from(shot.data,'base64'));};
  await capture('initial');
  await click('#watch');for(let step=0;step<4;step++)await click('#example-step');
  assert.match(await evaluate("document.getElementById('example-status').textContent"),/complete/i);
  assert.equal(await evaluate("document.querySelectorAll('#example-display .region-overlay.selected').length"),1);
  await capture('example');await click('#example-close');
  const owner=JSON.parse(fs.readFileSync(ownerPath));let retried=false,wrongFinal=false,zoomChecked=false;
  for(const page of owner.pages){
   if(page.id==='attack-is-not-move'||page.id==='history-claim-comparison')await capture(page.id);
   if(page.id==='history-claim-comparison'){
    await send('Emulation.setDeviceMetricsOverride',{width:640,height:960,deviceScaleFactor:1,mobile:false});
    await sleep(60);
    assert.equal(await evaluate("document.getElementById('zoom-out').disabled"),true,'no ineffective shrink at readable minimum');
    assert.match(await evaluate("document.getElementById('display-size').textContent"),/Minimum readable size/);
    await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1050,deviceScaleFactor:1,mobile:false});
    await sleep(60);
    await evaluate("(()=>{const node=document.querySelector('#presentation .matrix-window');node.scrollLeft=250;node.scrollTop=150;})()");
    const before=await evaluate("(()=>{const n=document.querySelector('#presentation .matrix-window');return {x:n.scrollLeft,y:n.scrollTop,cell:Number(n.dataset.cellPixels)};})()");
    await click('#zoom-in');
    const after=await evaluate("(()=>{const n=document.querySelector('#presentation .matrix-window');return {x:n.scrollLeft,y:n.scrollTop,cell:Number(n.dataset.cellPixels)};})()");
    assert.ok(after.cell>before.cell);assert.ok(Math.abs(after.y/after.cell-before.y/before.cell)<1);
    await click('#fit-width');zoomChecked=true;
   }
   let answer=page.correct[0];
   if(page.phase==='practice'&&!retried){
    await click(`#choices button:nth-child(${3-answer})`);await click('#commit');
    assert.equal(await evaluate("document.getElementById('feedback-label').textContent"),'Try again');
    await click('#next');retried=true;
    await click('#choices button:first-child');await click('#reset');
    assert.equal(await evaluate("document.getElementById('selection').textContent"),'Selected: none');
   }
   if(page.phase==='heldout'&&!wrongFinal){answer=3-answer;wrongFinal=true;}
   await click(`#choices button:nth-child(${answer})`);await click('#commit');
   if(page.phase==='heldout')assert.equal(await evaluate("document.getElementById('feedback-label').textContent"),'Response recorded');
   if(page!==owner.pages.at(-1))await click('#next');
  }
  assert.ok(zoomChecked,'history zoom was exercised');
  assert.match(await evaluate("document.getElementById('notice').textContent"),/complete/);
  await capture('complete');await click('#export');
  const downloaded=path.join(downloadDir,'learner-attempt-1.json');
  for(let i=0;i<100&&!fs.existsSync(downloaded);i++)await sleep(50);
  assert.ok(fs.existsSync(downloaded),'actual download');
  const session=JSON.parse(fs.readFileSync(downloaded));
  assert.equal(session.examples_seen.length,1);assert.equal(session.commitments.length,owner.pages.length+1);
  assert.ok(!Object.hasOwn(session,'name'));assert.ok(!Object.hasOwn(session,'date'));
  assert.deepEqual(errors,[]);assert.deepEqual(requests.filter(url=>/^https?:/.test(url)),[]);
  const summary={pages:owner.pages.length,commands:session.commands.length,commitments:session.commitments.length,watched_examples:session.examples_seen.length,practice_retry:true,reset_clears:true,history_zoom_preserves_scroll:true,deliberately_wrong_final:1,downloads:1,external_requests:0,javascript_exceptions:0,session:downloaded};
  fs.writeFileSync(path.join(scratch,'browser-check.json'),JSON.stringify(summary,null,2)+'\n');
  console.log(JSON.stringify(summary));
 }finally{socket.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
