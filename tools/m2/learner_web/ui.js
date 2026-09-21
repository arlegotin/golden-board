(function () {
    "use strict";
    const $ = id => document.getElementById(id);
    const element = (tag, className, text) => {
        const node=document.createElement(tag);
        if(className) node.className=className;
        if(text!==undefined) node.textContent=String(text);
        return node;
    };
    let runner, bytes, options, attempt=1, dirty=false, busy=false, examplesSeen=[], visits=[], example=null;
    let zoom=1,resizePending=false;
    const selectHex = id => "0100" + id.toString(16).padStart(4,"0");
    const actionDescription = value => value.startsWith("01") ? "Select region " + parseInt(value.slice(4),16) : value.startsWith("02") ? "Reset" : "Commit";

    function matrixScroll(node) {
        return {left:node.scrollLeft,top:node.scrollTop,cell:Number(node.dataset.cellPixels)||0};
    }
    function sizeMatrix(outer, saved=matrixScroll(outer)) {
        if(!outer.clientWidth) return;
        const matrix=outer.firstElementChild;
        let width=outer.clientWidth,layout;
        // A vertical scrollbar can reduce clientWidth after the first resize.
        // At most two measurements are needed; never iterate to convergence.
        for(let pass=0;pass<2;pass++) {
            layout=globalThis.GBLearnerLayout.matrixLayout({rows:Number(outer.dataset.rows),columns:Number(outer.dataset.columns),
                digits:Number(outer.dataset.digits),availableWidth:width,zoom});
            matrix.style.setProperty("--cell",layout.cellPixels+"px");
            if(outer.clientWidth===width) break;
            width=outer.clientWidth;
        }
        outer.dataset.cellPixels=String(layout.cellPixels);
        outer.dataset.overflow=String(layout.overflowX);
        const ratio=saved.cell?layout.cellPixels/saved.cell:1;
        // Retain the same numeric cell at the viewport origin on both axes.
        // The browser clamps positions when a smaller diagram now fits.
        outer.scrollLeft=saved.left*ratio; outer.scrollTop=saved.top*ratio;
    }
    function resizeDiagrams() {
        let overflow=false,canShrink=false,canGrow=false;
        for(const id of ["presentation","example-display","feedback"]) {
            for(const node of $(id).querySelectorAll(".matrix-window")) if(node.clientWidth) {
                sizeMatrix(node); overflow ||= node.dataset.overflow==="true";
                const pixels=Number(node.dataset.cellPixels);
                canShrink ||= pixels>Math.max(24,Number(node.dataset.digits)*8+8);
                canGrow ||= pixels<96;
            }
        }
        $("fit-width").setAttribute("aria-pressed",String(zoom===1));
        $("zoom-out").disabled=zoom<=0.5 || !canShrink;
        $("zoom-in").disabled=zoom>=3 || !canGrow;
        $("display-size").textContent=(!canShrink?"Minimum readable size":zoom===1?"Fit width":Math.round(zoom*100)+"% of fit")+(overflow?" · scroll for more":"");
    }
    function setZoom(value) {
        zoom=Math.max(0.5,Math.min(3,value));
        resizeDiagrams();
    }

    function renderGraph(container, graph, settings={}) {
        const scroll=new Map(Array.from(container.querySelectorAll(".matrix-window"),node=>[node.dataset.matrixKey,matrixScroll(node)]));
        container.replaceChildren();
        if(!graph) return;
        const records=new Map(graph.records.map(record=>[record.record_id,record]));
        const pending=[{id:graph.root_record_id,parent:container,ancestors:new Set()}];
        let remaining=100000,matrixIndex=0;
        while(pending.length) {
            if(--remaining<0) throw new Error("display_limit");
            const {id,parent,ancestors}=pending.pop(),record=records.get(id);
            if(!record || ancestors.has(id)) throw new Error("invalid_display");
            if(record.kind===1) continue; // TEXT labels remain suppressed.
            if(record.kind===4) {
                const outer=element("div","matrix-window");
                outer.dataset.matrixKey=graph.root_record_id+":"+record.record_id+":"+matrixIndex++;
                outer.dataset.rows=String(record.rows); outer.dataset.columns=String(record.columns);
                const matrix=element("div","matrix");
                matrix.style.setProperty("--rows",record.rows); matrix.style.setProperty("--columns",record.columns);
                matrix.setAttribute("role","group"); matrix.setAttribute("aria-label",record.rows+" rows by "+record.columns+" columns");
                let digits=1;
                for(let index=0;index<record.atoms.length;index++) {
                    if(--remaining<0) throw new Error("display_limit");
                    const value=record.atoms[index],row=Math.floor(index/record.columns),column=index%record.columns;
                    digits=Math.max(digits,String(value).length);
                    const cell=element("div","cell",value);
                    cell.style.gridRow=String(row+1); cell.style.gridColumn=String(column+1);
                    cell.style.setProperty("--hue",String((value*137.508)%360));
                    cell.style.setProperty("--shade",String(96-(value*37)%13)+"%");
                    cell.title="Row "+(row+1)+", column "+(column+1)+": "+value;
                    matrix.append(cell);
                }
                if(record.record_id===settings.surfaceId) for(const region of settings.regions || []) {
                    if(!(region.flags&1)) continue;
                    const button=element("button","region-overlay"),selected=(settings.selected || []).includes(region.region_id);
                    button.type="button"; button.classList.toggle("selected",selected);
                    button.style.gridRow=(region.row_start+1)+" / "+(region.row_end+1);
                    button.style.gridColumn=(region.column_start+1)+" / "+(region.column_end+1);
                    button.setAttribute("aria-label","Select region "+region.region_id);
                    button.setAttribute("aria-pressed",String(selected));
                    button.dataset.region=String(region.region_id);
                    button.disabled=!settings.interactive || !settings.available.includes(selectHex(region.region_id));
                    button.append(element("span","region-number",region.region_id));
                    if(settings.interactive) button.addEventListener("click",()=>perform(selectHex(region.region_id)));
                    matrix.append(button);
                }
                outer.dataset.digits=String(digits);
                outer.append(matrix); parent.append(outer);
            } else if(record.kind===6) {
                // The graph's record table is ID-sorted, but presentation follows
                // field/reference order. Never render the table as the layout.
                const work=[];
                for(const field of record.fields) {
                    const section=element("div","tuple-field"); parent.append(section);
                    if(field.atoms.length) {
                        const values=element("div","atoms");
                        for(const value of field.atoms) values.append(element("span","atom",value));
                        section.append(values);
                    }
                    for(const reference of field.record_refs) work.push({id:reference,parent:section,ancestors:new Set([...ancestors,id])});
                }
                pending.push(...work.reverse());
            } else if(record.kind===3) {
                const values=element("div","atoms");
                for(const value of record.atoms) values.append(element("span","atom",value));
                parent.append(values);
            } else if(record.kind===9) {
                parent.append(element("div","raw-data",record.opaque_data.join(" ")));
            } else throw new Error("unsupported_display_kind");
        }
        for(const outer of container.querySelectorAll(".matrix-window")) sizeMatrix(outer,scroll.get(outer.dataset.matrixKey));
    }

    function update() {
        const frame=runner.frame(),mechanics=runner.mechanics();
        if(visits.at(-1)!==frame.current_node_id) visits.push(frame.current_node_id);
        $("mode").textContent=mechanics.role===3?"Example":mechanics.answerMode===1?"Practice":mechanics.answerMode===2?"Response":"Explore";
        $("page-label").textContent="Page "+visits.length;
        $("attempt-label").textContent="Attempt "+attempt;
        renderGraph($("presentation"),frame.presentation,{surfaceId:mechanics.surfaceMatrixId,regions:frame.regions,
            selected:frame.selection_buffer,available:frame.available_actions_hex,interactive:true});
        $("choices").replaceChildren();
        for(const region of frame.regions) {
            if(!(region.flags&1)) continue;
            const selected=frame.selection_buffer.includes(region.region_id);
            const button=element("button","choice"+(selected?" selected":""),"Region "+region.region_id);
            button.setAttribute("aria-pressed",String(selected)); button.disabled=!frame.available_actions_hex.includes(selectHex(region.region_id));
            button.addEventListener("click",()=>perform(selectHex(region.region_id))); $("choices").append(button);
        }
        $("watch").hidden=!frame.passive; $("watch").disabled=busy;
        $("reset").disabled=busy || !frame.available_actions_hex.includes("02000000");
        $("commit").disabled=busy || !frame.available_actions_hex.includes("03000000");
        $("next").disabled=busy || !frame.can_advance;
        $("selection").textContent=frame.phase===2 ? "Response committed." : "Selected: "+(frame.selection_buffer.length?frame.selection_buffer.join(" → "):"none");
        $("budget").textContent=frame.local_remaining+" actions left here · "+frame.global_remaining+" in this attempt";
        $("feedback-panel").hidden=frame.phase!==2;
        if(frame.phase===2) {
            $("feedback-label").textContent=frame.outcome===1?"Match":frame.outcome===2?"Try again":"Response recorded";
            renderGraph($("feedback"),frame.feedback);
        }
        $("notice").classList.remove("error");
        $("notice").textContent=frame.phase===3?"No actions remain. Export your progress, or export and restart for a new attempt.":
            frame.phase===2 && !frame.next_node_ref?"This attempt is complete. Export your progress to keep it.":
            frame.phase===2?"Choose Next when you are ready.":mechanics.role===3?"Watch the example one step at a time. Commit when you are ready to continue.":"";
        $("event-log").textContent=frame.events.length?frame.events.map((event,index)=>(index+1)+". Item "+event.node_id+" · "+actionDescription(event.action_hex)).join("\n"):"No actions yet.";
        resizeDiagrams();
    }

    function perform(value) {
        if(busy) return;
        try { runner.perform(value); dirty=true; update(); }
        catch(error) { showError(error); }
    }
    function showError(error) {
        $("notice").classList.add("error");
        $("notice").textContent="That action could not be completed ("+error.message+"). You can still export your progress.";
    }

    function openExample() {
        const frame=runner.frame(); if(!frame.passive) return;
        example={node:frame.current_node_id,passive:frame.passive,surfaceId:runner.mechanics().passiveSurfaceMatrixId,
            shape:runner.mechanics().responseShape,index:0,selected:[],committed:[],saved:false};
        $("example-panel").hidden=false; showExample();
        $("example-panel").scrollIntoView({behavior:"smooth",block:"nearest"});
        $("example-step").focus({preventScroll:true});
    }
    function showExample() {
        if(!example) return;
        const finished=example.index===example.passive.actions_hex.length;
        const graph=finished && example.passive.resulting_presentation ? example.passive.resulting_presentation : example.passive.presentation;
        renderGraph($("example-display"),graph,{surfaceId:example.surfaceId,regions:example.passive.regions,
            selected:finished?example.committed:example.selected,available:[],interactive:false});
        $("example-steps").replaceChildren();
        example.passive.actions_hex.forEach((value,index)=>{
            const item=element("li",index<example.index?"done":"",actionDescription(value));
            item.classList.toggle("current",index===example.index-1); $("example-steps").append(item);
        });
        $("example-status").textContent=finished?"Example complete. Committed regions: "+(example.committed.length?example.committed.join(" → "):"none")+". Inspect the result, or replay it.":
            "Step "+example.index+" of "+example.passive.actions_hex.length+". Choose Next example step to continue.";
        $("example-step").disabled=finished;
        resizeDiagrams();
    }
    function stepExample() {
        if(!example || example.index>=example.passive.actions_hex.length) return;
        const value=example.passive.actions_hex[example.index++];
        if(value.startsWith("01")) {
            example.selected.push(parseInt(value.slice(4),16));
            if(example.shape!==3) example.selected.sort((a,b)=>a-b);
        } else {
            if(value.startsWith("03")) example.committed=[...example.selected];
            example.selected=[];
        }
        if(example.index===example.passive.actions_hex.length && !example.saved) {
            examplesSeen.push({node_id:example.node,actions_hex:[...example.passive.actions_hex]}); example.saved=true; dirty=true;
        }
        showExample();
    }
    function closeExample() { example=null; $("example-panel").hidden=true; resizeDiagrams(); }

    function exportProgress() {
        if(!runner) return;
        const output={...runner.session(attempt),examples_seen:examplesSeen.map(value=>({node_id:value.node_id,actions_hex:[...value.actions_hex]}))};
        const blob=new Blob([JSON.stringify(output,null,2)+"\n"],{type:"application/json"});
        const url=URL.createObjectURL(blob),link=element("a");
        link.href=url; link.download="learner-attempt-"+attempt+".json";
        document.body.append(link); link.click(); link.remove();
        setTimeout(()=>URL.revokeObjectURL(url),1000); dirty=false;
        $("notice").textContent="Progress exported for attempt "+attempt+".";
    }
    async function restart() {
        if(busy || !runner) return;
        exportProgress(); busy=true;
        try {
            const next=await globalThis.GBLearner.createRunner(bytes,options);
            runner=next; attempt++; examplesSeen=[]; visits=[]; closeExample(); dirty=false;
        } catch(error) { showError(error); }
        finally { busy=false; update(); }
    }

    async function boot() {
        try {
            const data=globalThis.LESSON_DATA;
            if(!data || data.schema!=="golden-board.learner-prototype-data/v0" || typeof data.content_base64!=="string" || data.content_base64.length>1400000) throw new Error("missing_lesson_data");
            const binary=atob(data.content_base64); bytes=Uint8Array.from(binary,char=>char.charCodeAt(0));
            options={contentBytes:data.content_bytes,contentSha256:data.content_sha256,rootId:data.root_id};
            runner=await globalThis.GBLearner.createRunner(bytes,options);
            $("reset").addEventListener("click",()=>perform("02000000"));
            $("commit").addEventListener("click",()=>perform("03000000"));
            $("next").addEventListener("click",()=>{if(busy)return;try{runner.advance();dirty=true;closeExample();update();}catch(error){showError(error);}});
            $("watch").addEventListener("click",openExample);
            $("example-step").addEventListener("click",stepExample);
            $("example-replay").addEventListener("click",()=>{if(example){example.index=0;example.selected=[];example.committed=[];example.saved=false;showExample();}});
            $("example-close").addEventListener("click",()=>{closeExample();$("watch").focus();});
            $("export").addEventListener("click",exportProgress); $("restart").addEventListener("click",restart);
            $("fit-width").addEventListener("click",()=>setZoom(1));
            $("zoom-out").addEventListener("click",()=>setZoom(zoom-0.25));
            $("zoom-in").addEventListener("click",()=>setZoom(zoom+0.25));
            window.addEventListener("resize",()=>{
                if(resizePending) return;
                resizePending=true;
                window.requestAnimationFrame(()=>{resizePending=false;resizeDiagrams();});
            });
            window.addEventListener("beforeunload",event=>{if(dirty){event.preventDefault();event.returnValue="";}});
            $("loading").hidden=true; $("lesson").hidden=false; $("export").disabled=false; $("restart").disabled=false;
            update();
        } catch(error) {
            $("loading").hidden=true; $("load-error").hidden=false;
            $("load-error").textContent="The lesson could not be opened ("+error.message+"). Keep all packet files together in the same folder.";
        }
    }
    boot();
})();
