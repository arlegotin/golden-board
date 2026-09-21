"use strict";

// Run: node tools/m2/learner_web/test-viewer.js BASELINE_STREAM [LESSON_STREAM REFERENCE_JSON]
// The Python oracle uses only the repository's public content and runner APIs.
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const path = require("node:path");
const fs = require("node:fs");
const vm = require("node:vm");
const {spawnSync} = require("node:child_process");
const root = path.resolve(__dirname, "../../..");
const {matrixLayout} = require("./layout.js");
const [baselinePath,lessonPath,referencePath,...extra] = process.argv.slice(2);
assert.ok(baselinePath && !extra.length && Boolean(lessonPath)===Boolean(referencePath),
    "Supply a baseline content stream, optionally followed by a lesson stream and its Python reference transcript");
const oracle = String.raw`
import base64, dataclasses, hashlib, json, sys
from pathlib import Path
from golden_board import content, m2_runner
raw = Path(sys.argv[1]).read_bytes()
def wire(value):
    if isinstance(value, bytes): return value.hex()
    if dataclasses.is_dataclass(value):
        result = {}
        for field in dataclasses.fields(value):
            key = field.name
            if key == 'committed_response': key = 'committed_response_hex'
            elif key == 'available_actions': key = 'available_actions_hex'
            elif key == 'actions': key = 'actions_hex'
            elif key in ('action', 'action_bytes'): key = 'action_hex'
            result[key] = wire(getattr(value, field.name))
        return result
    if isinstance(value, (tuple, list)): return [wire(item) for item in value]
    return value
def run(name, data, commands):
    runner = m2_runner.GenericRunner(data, label_suppressed=True)
    frames = [wire(runner.frame())]; results=[]; error=None
    for command in commands:
        try:
            result = runner.perform(bytes.fromhex(command)) if command != 'advance' else runner.advance()
            results.append(result if command != 'advance' else 'advanced')
            frames.append(wire(runner.frame()))
        except m2_runner.RunnerError as failure:
            error=str(failure); break
    return dict(name=name, content=base64.b64encode(data).decode(), sha=hashlib.sha256(data).hexdigest(),
                root=content.projection_view(content.stream_validation(data)).root_record_id,
                commands=commands,frames=frames,results=results,error=error)
select=lambda number: '0100'+number.to_bytes(2,'big').hex()
commit='03000000'; reset='02000000'; advance='advance'
normal=[select(2),commit,advance,select(1),commit,advance,select(3),select(1),commit,advance,select(3),select(1),commit]
cases=[run('frozen semantic path',raw,normal),
       run('empty responses',raw,[commit,advance,commit,advance,commit,advance,commit]),
       run('wrong practice and retry',raw,[commit,advance,select(2),commit,advance,select(1),commit]),
       run('reset exhaustion',raw,[select(1),reset,commit]),
       run('duplicate unavailable',raw,[select(1),select(1)])]
author=content.authoring_from_validated(content.projection_view(content.stream_validation(raw)))
for rows,columns in [(5,7),(7,5),(35,42)]:
    records=[]
    for record in author.records:
        value=record.payload
        if record.record_id==12:
            value=dataclasses.replace(value,rows=rows,columns=columns,cells=tuple(i%6 for i in range(rows*columns)))
        if record.record_id==181: value=dataclasses.replace(value,item_event_budget=8)
        if record.record_id==182: value=dataclasses.replace(value,global_event_budget=64)
        records.append(dataclasses.replace(record,payload=value))
    data=content.encode_content_v0(dataclasses.replace(author,records=tuple(records)))
    cases.append(run(f'rectangle {rows}x{columns} reset and reselect',data,[select(1),reset,select(3),commit,advance,select(1),commit]))
    cases.append(run(f'rectangle {rows}x{columns} reset and empty commit',data,[select(1),reset,commit]))
print(json.dumps(cases,separators=(',',':')))
`;

async function main() {
    const {createRunner} = require("./viewer.js");
    const result = spawnSync("python3", ["-B", "-c", oracle, path.resolve(baselinePath)], {
        cwd: root, env: {...process.env, PYTHONPATH: path.join(root, "python")},
        encoding: "utf8", maxBuffer: 32 * 1024 * 1024,
    });
    assert.equal(result.status, 0, result.stderr);
    const cases = JSON.parse(result.stdout);
    for (const test of cases) {
        const bytes = Buffer.from(test.content, "base64");
        const options = {contentBytes: bytes.length, contentSha256: test.sha, rootId: test.root};
        const runner = await createRunner(bytes, options);
        assert.deepEqual(runner.frame(), test.frames[0], test.name + " initial frame");
        let index = 0, actualError = null;
        for (const command of test.commands) {
            try {
                const actual = command === "advance" ? (runner.advance(), "advanced") : runner.perform(command);
                assert.equal(actual, test.results[index], test.name + " result");
                assert.deepEqual(runner.frame(), test.frames[++index], test.name + " frame " + index);
            } catch (error) {
                if (error instanceof assert.AssertionError) throw error;
                actualError = error.message;
                break;
            }
        }
        assert.equal(actualError, test.error, test.name + " rejection");
        // Returned frames are detached; callers cannot alter authority state.
        const frame = runner.frame(); frame.selection_buffer.push(999); frame.events.length = 0;
        assert.deepEqual(runner.frame(), test.frames[index], test.name + " immutable view");
        const saved = runner.session(1);
        const replay = await createRunner(bytes, options);
        for (const command of saved.commands) command.advance ? replay.advance() : replay.perform(command.action_hex);
        assert.deepEqual(replay.frame(), runner.frame(), test.name + " export replay");
        for(const availableWidth of [240,1180]) for(const zoom of [0.5,1,1.25,2,3]) {
            const scaled=await createRunner(bytes,options);
            function fit() {
                const frame=scaled.frame(),before=JSON.stringify(scaled.session(1));
                for(const graph of [frame.presentation,frame.feedback,frame.passive?.presentation,frame.passive?.resulting_presentation]) {
                    for(const record of graph?.records || []) if(record.kind===4) {
                        const digits=record.atoms.reduce((width,value)=>Math.max(width,String(value).length),1);
                        matrixLayout({rows:record.rows,columns:record.columns,availableWidth,zoom,digits});
                    }
                }
                assert.equal(JSON.stringify(scaled.session(1)),before,test.name+" layout does not use actions");
            }
            fit();
            for(const command of saved.commands) {
                command.advance ? scaled.advance() : scaled.perform(command.action_hex);
                fit();
            }
            assert.deepEqual(scaled.session(1),saved,test.name+" exact session at "+availableWidth+"px / "+zoom);
        }
        console.log("PASS", test.name);
    }
    const first = cases[0], original = Buffer.from(first.content, "base64");
    const pin = data => ({contentBytes:data.length, contentSha256:crypto.createHash("sha256").update(data).digest("hex"),rootId:first.root});
    const damaged = Buffer.from(original); damaged[damaged.length-1] ^= 1;
    await assert.rejects(createRunner(damaged, pin(original)), /content_stream_identity/);
    await assert.rejects(createRunner(original.subarray(0,-1),pin(original)), /content_stream_identity/);
    await assert.rejects(createRunner(original, {...pin(original),rootId:1}), /invalid_content/);
    const locate = id => { let at=4; while(at<original.length) { if(original.readUInt16BE(at)===id) return at+8; at+=8+original.readUInt32BE(at+4); } throw Error("missing record"); };
    for (const [name,offset,value] of [["missing matrix schema",locate(12),65535],["zero rows",locate(12)+2,0],["missing control node",locate(181)+20,65535]]) {
        const bad=Buffer.from(original); bad.writeUInt16BE(value,offset);
        await assert.rejects(createRunner(bad,pin(bad)), /invalid_content/,name);
        console.log("PASS",name);
    }
    const badFlags=Buffer.from(original); badFlags[locate(181)+3]=128;
    await assert.rejects(createRunner(badFlags,pin(badFlags)), /invalid_content/);
    const truncated=original.subarray(0,-1);
    await assert.rejects(createRunner(truncated,pin(truncated)), /invalid_content/);
    const viewer=fs.readFileSync(path.join(__dirname,"viewer.js"),"utf8");
    const ui=fs.readFileSync(path.join(__dirname,"ui.js"),"utf8");
    assert.doesNotMatch(viewer+ui,/\b(fetch|XMLHttpRequest|WebSocket)\s*\(/);
    console.log("PASS identity, malformed input, bounds and offline source checks");
    const isolated={Uint8Array,Int32Array,DataView,TextDecoder};
    vm.runInNewContext(viewer,isolated,{timeout:1000});
    const fallback=await isolated.GBLearner.createRunner(original,pin(original));
    assert.deepEqual(JSON.parse(JSON.stringify(fallback.frame())),cases[0].frames[0]);
    console.log("PASS SHA-256 fallback with no browser crypto or Node imports");
    if(lessonPath) {
        const reference=JSON.parse(fs.readFileSync(referencePath,"utf8"));
        const lesson=fs.readFileSync(lessonPath);
        let cursor=4,rootId=0;
        while(cursor<lesson.length) { rootId=lesson.readUInt16BE(cursor); cursor+=8+lesson.readUInt32BE(cursor+4); }
        assert.equal(cursor,lesson.length,"complete lesson record sequence");
        const options={contentBytes:lesson.length,contentSha256:crypto.createHash("sha256").update(lesson).digest("hex"),rootId};
        const runner=await createRunner(lesson,options);
        assert.deepEqual(runner.frame(),reference.frames[0]);
        for(let index=0;index<reference.commands.length;index++) {
            const command=reference.commands[index];
            command.advance ? runner.advance() : runner.perform(command.action_hex);
            assert.deepEqual(runner.frame(),reference.frames[index+1],"new lesson frame "+(index+1));
        }
        assert.deepEqual(runner.session(1).commands,reference.commands);
        assert.equal(runner.frame().next_node_ref,0);
        console.log("PASS complete new lesson:",reference.frames.length,"Python reference frames and",reference.commands.length,"exported commands");
    }
}
main().catch(error => { console.error(error); process.exitCode=1; });
