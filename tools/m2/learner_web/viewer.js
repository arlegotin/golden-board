(function (global) {
    "use strict";

    // This is a bounded interpreter for a packet whose bytes have already been
    // validated by its author. The packet pins those exact bytes. It is not a
    // replacement for the complete content-v0 authoring/conformance validator.
    const MAX_BYTES = 1048576;
    const DISPLAY = new Set([1, 3, 4, 6, 9]);
    const fail = (reason = "invalid_content") => { throw new Error(reason); };
    const requireValue = value => { if (!value) fail(); };
    const hex = bytes => Array.from(bytes, value => value.toString(16).padStart(2, "0")).join("");
    const action = region => "0100" + region.toString(16).padStart(4, "0");
    const response = (shape, ids) => shape.toString(16).padStart(2, "0") +
        ids.length.toString(16).padStart(4, "0") + ids.map(id => id.toString(16).padStart(4, "0")).join("");
    const copy = value => JSON.parse(JSON.stringify(value));

    async function digest(bytes) {
        if (global.crypto && global.crypto.subtle) {
            return hex(new Uint8Array(await global.crypto.subtle.digest("SHA-256", bytes)));
        }
        if (typeof module === "object" && module.exports) {
            return require("node:crypto").createHash("sha256").update(bytes).digest("hex");
        }
        // Some browsers omit SubtleCrypto on file: pages. Keep disk opening
        // offline with the same bounded SHA-256 calculation in that case.
        const constants = [
            0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
            0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
            0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
            0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
            0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
            0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
            0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
            0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2,
        ];
        const hash = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
        const padded = new Uint8Array(Math.ceil((bytes.length + 9) / 64) * 64);
        padded.set(bytes); padded[bytes.length] = 128;
        const view = new DataView(padded.buffer);
        view.setUint32(padded.length - 4, bytes.length * 8, false);
        const rotate = (n, by) => (n >>> by) | (n << (32 - by));
        const words = new Int32Array(64);
        for (let offset = 0; offset < padded.length; offset += 64) {
            for (let i = 0; i < 64; i++) {
                if (i < 16) words[i] = view.getInt32(offset + i * 4, false);
                else {
                    const x = words[i - 15], y = words[i - 2];
                    words[i] = (words[i - 16] + (rotate(x, 7) ^ rotate(x, 18) ^ (x >>> 3)) +
                        words[i - 7] + (rotate(y, 17) ^ rotate(y, 19) ^ (y >>> 10))) | 0;
                }
            }
            let [a,b,c,d,e,f,g,h] = hash;
            for (let i = 0; i < 64; i++) {
                const t1 = (h + (rotate(e,6)^rotate(e,11)^rotate(e,25)) + ((e&f)^(~e&g)) + constants[i] + words[i]) | 0;
                const t2 = ((rotate(a,2)^rotate(a,13)^rotate(a,22)) + ((a&b)^(a&c)^(b&c))) | 0;
                [a,b,c,d,e,f,g,h] = [(t1+t2)|0,a,b,c,(d+t1)|0,e,f,g];
            }
            [a,b,c,d,e,f,g,h].forEach((value,index) => { hash[index] = (hash[index] + value) | 0; });
        }
        return hash.map(value => (value >>> 0).toString(16).padStart(8,"0")).join("");
    }

    class Reader {
        constructor(bytes) { this.bytes = bytes; this.view = new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength); this.at = 0; }
        take(count) { requireValue(Number.isInteger(count) && count >= 0 && this.at + count <= this.bytes.length); const value = this.bytes.subarray(this.at,this.at+count); this.at += count; return value; }
        number(width) { requireValue([1,2,4].includes(width)); const at=this.at; this.take(width); return width===1 ? this.view.getUint8(at) : width===2 ? this.view.getUint16(at,false) : this.view.getUint32(at,false); }
        u8() { return this.number(1); }
        u16() { return this.number(2); }
        u32() { return this.number(4); }
        zero() { requireValue(this.u8() === 0); }
        end() { requireValue(this.at === this.bytes.length); }
    }

    function parse(bytes, rootId) {
        const input=new Reader(bytes), records=new Map();
        requireValue(input.u16()===0);
        const count=input.u16(); requireValue(count>=2);
        let previous=0, roots=0;
        function get(id, kind) {
            const found=records.get(id);
            requireValue(found && (kind===undefined || found.kind===kind)); return found.value;
        }
        function display(id) { requireValue(records.has(id) && DISPLAY.has(records.get(id).kind)); return id; }
        function atoms(r,schemaId,count) {
            const schema=get(schemaId,2); requireValue(count>=0 && count<=65535);
            const values=[];
            for(let i=0;i<count;i++) {
                const value=r.number(schema.atom_width);
                if(schema.atom_class===1) requireValue(value>=schema.min_value && value<=schema.max_value);
                else if(schema.atom_class===2) requireValue(schema.entries.some(entry=>entry[0]===value));
                else requireValue(((value & ~schema.allowed_mask) >>> 0)===0);
                values.push(value);
            }
            return values;
        }
        for(let index=0;index<count;index++) {
            const id=input.u16(),kind=input.u16(),length=input.u32();
            requireValue(id>previous && kind>=1 && kind<=14);
            const r=new Reader(input.take(length)); let value;
            switch(kind) {
            case 1:
                try { value=new TextDecoder("utf-8",{fatal:true}).decode(r.take(length)); } catch (_) { fail(); }
                break;
            case 2: {
                const cls=r.u8(),width=r.u8(),count=r.u16();
                requireValue([1,2,3].includes(cls) && [1,2,4].includes(width) && count<=4096);
                value={atom_class:cls,atom_width:width,entries:[],min_value:null,max_value:null,allowed_mask:null};
                if(cls===1) { requireValue(count===0); value.min_value=r.number(width); value.max_value=r.number(width); requireValue(value.min_value<=value.max_value); }
                else {
                    requireValue(count>0);
                    if(cls===3) value.allowed_mask=r.number(width);
                    let prior=-1;
                    for(let n=0;n<count;n++) { const code=r.number(width),label=r.u16(); get(label,1); requireValue(code>prior); prior=code; value.entries.push([code,label]); }
                }
                break;
            }
            case 3: {
                const schema=r.u16(),n=r.u16(); requireValue(n>=1 && n<=4096);
                value={atom_schema_ref:schema,atoms:atoms(r,schema,n)}; break;
            }
            case 4: {
                const schema=r.u16(),rows=r.u16(),columns=r.u16();
                requireValue(rows>0 && columns>0 && rows*columns<=65535);
                value={atom_schema_ref:schema,rows,columns,cells:atoms(r,schema,rows*columns)}; break;
            }
            case 5: {
                const n=r.u16(); requireValue(n>=1 && n<=256); const fields=[]; let slots=0;
                for(let j=0;j<n;j++) {
                    const name_text_ref=r.u16(),storage=r.u8(); r.zero(); const type_code=r.u16(),count=r.u16();
                    get(name_text_ref,1); requireValue(count>=1 && count<=4096 && (slots+=count)<=4096);
                    if(storage===1) get(type_code,2); else requireValue(storage===2 && DISPLAY.has(type_code));
                    fields.push({name_text_ref,storage,type_code,count});
                }
                value={fields}; break;
            }
            case 6: {
                const schema=r.u16(),fields=get(schema,5).fields,values=[];
                for(const field of fields) {
                    if(field.storage===1) values.push({atoms:atoms(r,field.type_code,field.count),record_refs:[]});
                    else { const refs=[]; for(let j=0;j<field.count;j++) { const ref=r.u16(); get(ref,field.type_code); refs.push(ref); } values.push({atoms:[],record_refs:refs}); }
                }
                value={field_schema_ref:schema,field_values:values}; break;
            }
            case 7: {
                const surface=r.u16(),matrix=get(surface,4),n=r.u16(); requireValue(n>=1 && n<=4096);
                const regions=[]; let prior=0;
                for(let j=0;j<n;j++) {
                    const region_id=r.u16(),label_ref=r.u16(),row_start=r.u16(),row_end=r.u16(),column_start=r.u16(),column_end=r.u16(),flags=r.u8(); r.zero();
                    requireValue(region_id>prior && flags<=1 && row_start<row_end && row_end<=matrix.rows && column_start<column_end && column_end<=matrix.columns);
                    if(label_ref) display(label_ref); prior=region_id;
                    regions.push({region_id,label_ref,row_start,row_end,column_start,column_end,flags});
                }
                value={surface_matrix_ref:surface,regions}; break;
            }
            case 8: {
                const binding_class=r.u8(); r.zero(); const namespace_id=r.u16(),semantic_code=r.u16(),argument=r.u16(),auxiliary=r.u16();
                requireValue(namespace_id>0 && semantic_code>0 && [1,2].includes(binding_class));
                if(binding_class===1) { get(argument,2); requireValue(auxiliary>=1 && auxiliary<=4096); }
                else { requireValue(get(argument,8).binding_class===1); get(auxiliary,2); }
                value={binding_class,namespace_id,semantic_code,argument,auxiliary}; break;
            }
            case 9: {
                const data_binding_ref=r.u16(),binding=get(data_binding_ref,8); requireValue(binding.binding_class===1);
                value={data_binding_ref,data:atoms(r,binding.argument,binding.auxiliary)}; break;
            }
            case 10: {
                const predicate_binding_ref=r.u16(),subject_opaque_data_ref=r.u16(),result_atom_vector_ref=r.u16();
                const binding=get(predicate_binding_ref,8),subject=get(subject_opaque_data_ref,9),vector=get(result_atom_vector_ref,3);
                requireValue(binding.binding_class===2 && subject.data_binding_ref===binding.argument && vector.atom_schema_ref===binding.auxiliary && vector.atoms.length===1);
                value={predicate_binding_ref,subject_opaque_data_ref,result_atom_vector_ref}; break;
            }
            case 11: {
                const feedback_code=r.u16(),display_ref=display(r.u16()),predicate_result_ref=r.u16();
                requireValue(feedback_code>=1 && feedback_code<=5);
                if([1,5].includes(feedback_code)) requireValue(predicate_result_ref===0); else get(predicate_result_ref,10);
                value={feedback_code,display_ref,predicate_result_ref}; break;
            }
            case 12: {
                const presentation_ref=display(r.u16()),region_set_ref=r.u16(); get(region_set_ref,7);
                const resulting_presentation_ref=r.u16(),limitation_text_ref=r.u16(),n=r.u16();
                if(resulting_presentation_ref) display(resulting_presentation_ref); if(limitation_text_ref) get(limitation_text_ref,1); requireValue(n>0);
                const actions=[];
                for(let j=0;j<n;j++) { const raw=r.take(4); requireValue([1,2,3].includes(raw[0]) && raw[1]===0 && (raw[0]===1 || (raw[2]===0 && raw[3]===0))); actions.push(hex(raw)); }
                const expected_outcome=r.u8(); r.zero(); const expected_feedback_ref=r.u16(),expected_next_node_ref=r.u16();
                requireValue([1,2,3].includes(expected_outcome) && actions.at(-1)==="03000000"); get(expected_feedback_ref,11);
                value={presentation_ref,region_set_ref,resulting_presentation_ref,limitation_text_ref,actions,expected_outcome,expected_feedback_ref,expected_next_node_ref}; break;
            }
            case 13: {
                const role=r.u8(),response_shape=r.u8(),answer_mode=r.u8(),flags=r.u8(),presentation_ref=display(r.u16()),region_set_ref=r.u16(),predicate_result_ref=r.u16(),passive_trace_ref=r.u16(),max_selections=r.u16(),item_event_budget=r.u16(),n=r.u16();
                requireValue(role>=1 && role<=5 && response_shape>=1 && response_shape<=3 && answer_mode>=1 && answer_mode<=3 && flags<=1 && (flags===0 || response_shape===3));
                requireValue(max_selections<=4096 && (response_shape!==1 || max_selections===1) && item_event_budget>=max_selections+1 && n<=4096);
                const regionSet=get(region_set_ref,7); if(predicate_result_ref) get(predicate_result_ref,10); if(passive_trace_ref) get(passive_trace_ref,12);
                const cases=[]; let previousResponse="";
                for(let j=0;j<n;j++) {
                    const case_class=r.u8(); r.zero(); const count=r.u16(); requireValue([1,2].includes(case_class) && count<=max_selections);
                    const region_ids=[];
                    for(let k=0;k<count;k++) { const selected=r.u16(); requireValue(regionSet.regions.some(region=>region.region_id===selected && region.flags===1)); region_ids.push(selected); }
                    if(response_shape!==3) requireValue(region_ids.every((v,k)=>k===0 || v>region_ids[k-1]));
                    else if(!flags) requireValue(new Set(region_ids).size===region_ids.length);
                    const encoded=response(response_shape,region_ids); requireValue(encoded>previousResponse); previousResponse=encoded;
                    const feedback_ref=r.u16(),next_node_ref=r.u16(); get(feedback_ref,11); cases.push({case_class,region_ids,feedback_ref,next_node_ref});
                }
                const default_feedback_ref=r.u16(),default_next_node_ref=r.u16(); get(default_feedback_ref,11);
                if(answer_mode!==1) requireValue(cases.length===0);
                value={role,response_shape,answer_mode,flags,presentation_ref,region_set_ref,predicate_result_ref,passive_trace_ref,max_selections,item_event_budget,cases,default_feedback_ref,default_next_node_ref}; break;
            }
            case 14: {
                const entry_node_ref=r.u16(),global_event_budget=r.u16(); get(entry_node_ref,13);
                requireValue(global_event_budget>0); value={entry_node_ref,global_event_budget}; roots++; break;
            }
            default: fail();
            }
            r.end(); records.set(id,{kind,value}); previous=id;
        }
        input.end(); requireValue(previous===rootId && roots===1); const root=get(rootId,14);
        // Control edges may point forward. Resolve every one before a frame is
        // exposed, including passive and unused practice branches.
        for(const record of records.values()) {
            const value=record.value;
            if(record.kind===12 && value.expected_next_node_ref) get(value.expected_next_node_ref,13);
            if(record.kind===13) {
                requireValue(value.item_event_budget<=root.global_event_budget);
                if(value.default_next_node_ref) get(value.default_next_node_ref,13);
                for(const entry of value.cases) if(entry.next_node_ref) get(entry.next_node_ref,13);
                const wanted=get(value.region_set_ref,7).surface_matrix_ref;
                const pending=[value.presentation_ref],seen=new Set(),matrices=new Set();
                while(pending.length) {
                    const id=pending.pop(); if(seen.has(id)) continue; seen.add(id);
                    const row=records.get(id); if(row.kind===4) matrices.add(id);
                    if(row.kind===6) for(const field of row.value.field_values) pending.push(...field.record_refs);
                }
                requireValue(matrices.size===1 && matrices.has(wanted));
            }
        }
        return {records,root,get};
    }

    async function createRunner(input, options) {
        if(!(input instanceof Uint8Array) || !options || !Number.isInteger(options.contentBytes) ||
            options.contentBytes<4 || options.contentBytes>MAX_BYTES || !/^[0-9a-f]{64}$/.test(options.contentSha256) ||
            !Number.isInteger(options.rootId) || options.rootId<1 || options.rootId>65535) fail("content_stream_identity");
        const bytes=new Uint8Array(input);
        if(bytes.length!==options.contentBytes || await digest(bytes)!==options.contentSha256) fail("content_stream_identity");
        const {records,root,get}=parse(bytes,options.rootId),commands=[],commitments=[];
        const identity=options.contentSha256;
        let state={current_node_id:root.entry_node_ref,global_remaining:root.global_event_budget,
            local_remaining:get(root.entry_node_ref,13).item_event_budget,phase:1,outcome:0,
            selection_buffer:[],committed_response_hex:"",feedback_ref:0,next_node_ref:0,events:[]};
        const node=()=>get(state.current_node_id,13);
        const regions=id=>get(id,7).regions.map(region=>({region_id:region.region_id,label:null,row_start:region.row_start,row_end:region.row_end,column_start:region.column_start,column_end:region.column_end,flags:region.flags}));
        const schema=id=>{const s=get(id,2);return {allowed_mask:s.allowed_mask,atom_class:s.atom_class,atom_width:s.atom_width,entries:s.entries.map(e=>({label:null,value:e[0]})),max_value:s.max_value,min_value:s.min_value};};
        function graph(id) {
            const pending=[id],emitted=new Map();
            while(pending.length) {
                const current=pending.pop(); if(emitted.has(current)) continue;
                const record=records.get(current),v=record.value;
                const out={atom_schema:null,atoms:[],columns:0,fields:[],kind:record.kind,opaque_data:[],record_id:current,rows:0,text:null};
                if(record.kind===3) { out.atom_schema=schema(v.atom_schema_ref); out.atoms=[...v.atoms]; }
                else if(record.kind===4) { out.atom_schema=schema(v.atom_schema_ref); out.atoms=[...v.cells]; out.columns=v.columns; out.rows=v.rows; }
                else if(record.kind===6) {
                    const fields=get(v.field_schema_ref,5).fields;
                    out.fields=fields.map((field,index)=>{ const value=v.field_values[index]; pending.push(...value.record_refs); return {atoms:[...value.atoms],count:field.count,name:null,record_refs:[...value.record_refs],storage:field.storage,type_code:field.type_code}; });
                } else if(record.kind===9) out.opaque_data=[...v.data];
                else requireValue(record.kind===1);
                emitted.set(current,out);
            }
            return {records:[...emitted.values()].sort((a,b)=>a.record_id-b.record_id),root_record_id:id};
        }
        function available() {
            if(state.phase!==1) return [];
            const n=node(),selected=state.selection_buffer,repeated=n.response_shape===3 && (n.flags&1);
            const values=[];
            if(selected.length<n.max_selections) for(const region of get(n.region_set_ref,7).regions) {
                if(region.flags&1 && (!selected.includes(region.region_id) || repeated)) values.push(action(region.region_id));
            }
            return [...values,"02000000","03000000"];
        }
        function frame() {
            const n=node(); let passive=null;
            if(n.passive_trace_ref) {
                const p=get(n.passive_trace_ref,12);
                passive={actions_hex:[...p.actions],limitation:null,presentation:graph(p.presentation_ref),regions:regions(p.region_set_ref),resulting_presentation:p.resulting_presentation_ref?graph(p.resulting_presentation_ref):null};
            }
            return {...copy(state),available_actions_hex:available(),can_advance:state.phase===2 && state.next_node_ref!==0,
                feedback:state.feedback_ref?graph(get(state.feedback_ref,11).display_ref):null,
                passive,presentation:graph(n.presentation_ref),regions:regions(n.region_set_ref)};
        }
        function perform(actionHex) {
            if(typeof actionHex!=="string" || !/^[0-9a-f]{8}$/.test(actionHex) || !available().includes(actionHex)) fail("action_not_available");
            const n=node(),tag=parseInt(actionHex.slice(0,2),16),id=parseInt(actionHex.slice(4),16);
            state.global_remaining--; state.local_remaining--;
            state.committed_response_hex=""; state.outcome=0; state.feedback_ref=0; state.next_node_ref=0;
            if(tag===1) { state.selection_buffer.push(id); if(n.response_shape!==3) state.selection_buffer.sort((a,b)=>a-b); }
            else if(tag===2) state.selection_buffer=[];
            else {
                state.committed_response_hex=response(n.response_shape,state.selection_buffer);
                const chosen=n.cases.find(c=>c.region_ids.length===state.selection_buffer.length && c.region_ids.every((v,i)=>v===state.selection_buffer[i]));
                state.feedback_ref=chosen?chosen.feedback_ref:n.default_feedback_ref;
                state.next_node_ref=chosen?chosen.next_node_ref:n.default_next_node_ref;
                state.outcome=chosen?(chosen.case_class===1?1:2):(n.answer_mode===1?2:3);
                state.selection_buffer=[];
            }
            state.events.push({node_id:state.current_node_id,action_hex:actionHex,result:tag});
            state.phase=tag===3?2:(!state.global_remaining || !state.local_remaining?3:1);
            commands.push({action_hex:actionHex});
            if(tag===3) commitments.push({node_id:state.current_node_id,committed_response_hex:state.committed_response_hex,outcome:state.outcome,feedback_ref:state.feedback_ref,next_node_ref:state.next_node_ref});
            return tag;
        }
        function advance() {
            if(state.phase!==2 || !state.next_node_ref) fail("advance_not_available");
            const target=get(state.next_node_ref,13);
            state={...state,current_node_id:state.next_node_ref,local_remaining:Math.min(target.item_event_budget,state.global_remaining),
                phase:state.global_remaining?1:3,outcome:0,selection_buffer:[],committed_response_hex:"",feedback_ref:0,next_node_ref:0};
            commands.push({advance:true});
        }
        function mechanics() {
            const n=node();
            return {role:n.role,answerMode:n.answer_mode,responseShape:n.response_shape,surfaceMatrixId:get(n.region_set_ref,7).surface_matrix_ref,
                passiveSurfaceMatrixId:n.passive_trace_ref?get(get(n.passive_trace_ref,12).region_set_ref,7).surface_matrix_ref:null};
        }
        function session(attempt=1) {
            if(!Number.isInteger(attempt) || attempt<1) fail("invalid_attempt");
            return {schema:"golden-board.learner-prototype-session/v0",content_stream_sha256:identity,attempt,
                commands:copy(commands),events:copy(state.events),commitments:copy(commitments),final_state:copy(state)};
        }
        return Object.freeze({frame,perform,advance,mechanics,session});
    }
    const api=Object.freeze({createRunner});
    global.GBLearner=api;
    if(typeof module==="object" && module.exports) module.exports=api;
})(globalThis);
