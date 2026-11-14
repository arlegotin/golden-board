// Continuous generic document/entry/action relay; no subject rules or answers.
import {readFileSync,writeFileSync,realpathSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {Catalog} from './catalog.mjs';

export function catalogRelay(documents,operations){
  if(!Array.isArray(operations))throw Error('An operations array is required');
  const catalog=new Catalog(documents);const log=[];
  for(const operation of operations){
    if(!operation||Object.keys(operation).length!==1)throw Error('Exactly one open or action operation required');
    let result;
    if(operation.open){
      const {document,entry}=operation.open;
      result=catalog.open(document,entry);
    }else if(operation.action)result=catalog.action(operation.action);
    else throw Error('Unknown catalog operation');
    let packet=result.packet;
    if(packet){
      const {glyphs,...rest}=packet;
      packet={...rest,glyphs_sha256:createHash('sha256').update(JSON.stringify(glyphs)).digest('hex')};
    }
    log.push({operation,ok:result.ok,...(result.ok?{}:{error:result.error}),packet});
  }
  return {inventory:catalog.list(),operations:log};
}

if(process.argv[1]&&import.meta.url===pathToFileURL(realpathSync(process.argv[1])).href){
  const [,,requestPath,outputPath]=process.argv;
  const request=JSON.parse(readFileSync(requestPath,'utf8'));
  const documents=request.documents.map(([id,path])=>[id,readFileSync(path)]);
  writeFileSync(outputPath,JSON.stringify(catalogRelay(documents,request.operations))+'\n');
}
