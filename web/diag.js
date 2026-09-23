/* diag.js — 用未舍入的 raw_sc 定位残留差异（舍入会掩盖真实差值） */
"use strict";
const fs = require("fs"), path = require("path"), zlib = require("zlib");
const HERE = __dirname, DATA = path.join(HERE, "..", "docs", "data");
const meta = JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(DATA, "meta.json.gz"))));
const scenesData = JSON.parse(fs.readFileSync(path.join(DATA, "scenes.json"), "utf8"));
const py = JSON.parse(fs.readFileSync(path.join(HERE, "python_results.json"), "utf8"));
const E = require(path.join(HERE, "..", "docs", "engine.js"));

let n = 0, bad = 0;
for (const q of Object.keys(py)) {
  const want = py[q].results;
  const got = E.retrieve(q, scenesData, meta, { top: 5 }).results;
  const m = Math.min(want.length, got.length);
  for (let i = 0; i < m; i++) {
    n++;
    const a = want[i].raw_sc, b = got[i].sc_raw;
    if (a === null || a === undefined || b === undefined) continue;
    if (Math.abs(a - b) > 1e-12) {
      bad++;
      console.log("问句:", q, " 位置", i);
      console.log("  cite      :", want[i].cite);
      console.log("  py raw_sc :", a.toPrecision(20));
      console.log("  js raw_sc :", b.toPrecision(20));
      console.log("  差        :", (b - a).toExponential(3));
      console.log("  py quality:", want[i].quality, " np:", want[i].nprop);
      console.log("  js quality:", got[i].quality, " np:", got[i].n_proposals);
      console.log("  py score  :", want[i].score);
      console.log("  js score  :", got[i].score);
      console.log();
    }
  }
}
console.log(`比对 ${n} 条案例，raw_sc 不一致 ${bad} 条`);
