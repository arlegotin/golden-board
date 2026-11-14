// A generic document/entry opening adapter. Content, actions and feedback are
// exact carried records; this module has no subject rules or second corpus.
import {decodeDocument,Player} from './player.mjs';

export class Catalog {
  constructor(entries) {
    if(!Array.isArray(entries)||!entries.length)throw Error('A nonempty document inventory is required');
    this.documents=new Map();this.player=null;this.id=null;
    for(const [id,bytes] of entries){
      if(!Number.isInteger(id)||id<1||id>=65535||this.documents.has(id))throw Error('Invalid or duplicate document identity');
      this.documents.set(id,decodeDocument(bytes));
    }
  }
  list(){return [...this.documents].sort(([a],[b])=>a-b).map(([id,d])=>({id,entries:[...d.entries]}));}
  packet(){return this.player?{document:this.id,...this.player.packet()}:null;}
  open(id,entry){
    try{
      const d=this.documents.get(id);if(!d)throw Error('Unavailable document');
      const target=entry===undefined?d.entries[0]:entry;
      if(!d.entries.includes(target))throw Error('Entry is not declared by this document');
      const player=new Player(d,target);this.player=player;this.id=id;
      return {ok:true,packet:this.packet()};
    }catch(error){return {ok:false,error:error.message,packet:this.packet()};}
  }
  action(action){
    if(!this.player)return {ok:false,error:'Open a document first',packet:null};
    const result=this.player.action(action);return {...result,packet:this.packet()};
  }
}
