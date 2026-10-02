"use strict";

// Run: node tools/m2/learner_web/test-layout.js
const assert = require("node:assert/strict");
const {matrixLayout} = require("./layout.js");

// Width, rather than row count or a particular content shape, controls fit.
for(const test of [
    {rows:5,columns:7,availableWidth:228,want:{cellPixels:32,width:228,height:164,overflowX:false}},
    {rows:7,columns:5,availableWidth:228,want:{cellPixels:44,width:224,height:312,overflowX:false}},
    {rows:35,columns:42,availableWidth:1180,want:{cellPixels:28,width:1180,height:984,overflowX:false}},
    {rows:35,columns:42,availableWidth:360,want:{cellPixels:24,width:1012,height:844,overflowX:true}},
    {rows:5,columns:7,availableWidth:10000,want:{cellPixels:96,width:676,height:484,overflowX:false}},
    {rows:1,columns:65535,availableWidth:1,want:{cellPixels:24,width:1572844,height:28,overflowX:true}},
]) {
    const {want,...input}=test;
    assert.deepEqual(matrixLayout(input),want,`${input.rows}x${input.columns} at ${input.availableWidth}px`);
}

// Zoom changes only cell size; the numeric coordinates remain the same.
assert.deepEqual(matrixLayout({rows:35,columns:42,availableWidth:1180,zoom:1.5}),
    {cellPixels:42,width:1768,height:1474,overflowX:true});
assert.deepEqual(matrixLayout({rows:35,columns:42,availableWidth:1180,zoom:0.5}),
    {cellPixels:24,width:1012,height:844,overflowX:false});
assert.deepEqual(matrixLayout({rows:5,columns:7,availableWidth:10000,zoom:3}),
    {cellPixels:96,width:676,height:484,overflowX:false});

// Decimal atoms must remain readable, including the full u32 width.
assert.deepEqual(matrixLayout({rows:5,columns:7,availableWidth:228,digits:10}),
    {cellPixels:88,width:620,height:444,overflowX:true});

const valid={rows:5,columns:7,availableWidth:228};
for(const bad of [
    {rows:0},{columns:-1},{rows:1.5},{rows:65536},{rows:256,columns:256},
    {availableWidth:0},{availableWidth:NaN},{availableWidth:Infinity},
    {zoom:0.49},{zoom:3.01},{zoom:NaN},{digits:0},{digits:11},{digits:2.5},
]) assert.throws(()=>matrixLayout({...valid,...bad}),/invalid_layout/);

console.log("PASS rectangular fitting, zoom bounds, readable overflow and invalid layout rejection");
