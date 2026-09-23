/* verify_engine.js — 对拍：浏览器端引擎 vs Python 真引擎
 *
 * 用法： node verify_engine.js
 * 前置： 先跑 python dump_python_results.py 生成 python_results.json
 *
 * 比对四个字段：命中场景（含权重）、每个案例的 scene / score / quality / cite。
 * 任何一条不等都打印出来，最后给一致率。不做「大致相同」的判断。
 */
"use strict";
const fs = require("fs");
const path = require("path");
const zlib = require("zlib");

const HERE = __dirname;
const DATA = path.join(HERE, "..", "docs", "data");

const meta = JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(DATA, "meta.json.gz"))));
const scenesData = JSON.parse(fs.readFileSync(path.join(DATA, "scenes.json"), "utf8"));
const py = JSON.parse(fs.readFileSync(path.join(HERE, "python_results.json"), "utf8"));
const E = require(path.join(HERE, "..", "docs", "engine.js"));

let qTotal = 0, qOk = 0;
const problems = [];

for (const q of Object.keys(py)) {
  qTotal++;
  const want = py[q];
  const got = E.retrieve(q, scenesData, meta, { top: 5 });

  // 场景侧
  const gotMatched = got.matched.slice(0, 3).map(m => ({ id: m.id, score: m.score }));
  const mOk = JSON.stringify(gotMatched) === JSON.stringify(want.matched);

  // 结果侧：只比对这四个字段（Python 侧还带 raw_sc/nprop，用于更细的诊断）
  const gotRes = got.results.map(r => ({
    scene: r.scene, score: r.score, quality: r.quality, cite: meta.events[r.i][0],
  }));
  const wantRes = want.results.map(r => ({
    scene: r.scene, score: r.score, quality: r.quality, cite: r.cite,
  }));
  const rOk = JSON.stringify(gotRes) === JSON.stringify(wantRes);

  if (mOk && rOk) { qOk++; continue; }

  problems.push({ q, mOk, rOk, want, got: { matched: gotMatched, results: gotRes } });
}

console.log("== 对拍结果 ==");
console.log("问句总数     :", qTotal);
console.log("完全一致     :", qOk, `(${(100 * qOk / qTotal).toFixed(1)}%)`);
console.log("有差异       :", problems.length);

if (problems.length) {
  console.log("\n== 差异明细（最多 5 条）==");
  problems.slice(0, 5).forEach(p => {
    console.log("\n问句:", p.q);
    console.log("  场景一致:", p.mOk, " 结果一致:", p.rOk);
    console.log("  Python 场景:", JSON.stringify(p.want.matched));
    console.log("  JS     场景:", JSON.stringify(p.got.matched));
    const n = Math.max(p.want.results.length, p.got.results.length);
    for (let i = 0; i < Math.min(n, 3); i++) {
      const a = p.want.results[i], b = p.got.results[i];
      const same = JSON.stringify(a) === JSON.stringify(b);
      console.log(`   [${i}] ${same ? "OK  " : "DIFF"}`);
      if (!same) {
        console.log("        py:", JSON.stringify(a));
        console.log("        js:", JSON.stringify(b));
      }
    }
  });
}

// 逐字段统计，便于定位是舍入问题还是逻辑问题
let fScene = 0, fScore = 0, fQuality = 0, fCite = 0, fLen = 0, n = 0;
for (const q of Object.keys(py)) {
  const want = py[q].results;
  const got = E.retrieve(q, scenesData, meta, { top: 5 }).results.map(r => ({
    scene: r.scene, score: r.score, quality: r.quality, cite: meta.events[r.i][0],
  }));
  if (want.length !== got.length) fLen++;
  const m = Math.min(want.length, got.length);
  for (let i = 0; i < m; i++) {
    n++;
    if (want[i].scene !== got[i].scene) fScene++;
    if (want[i].score !== got[i].score) fScore++;
    if (want[i].quality !== got[i].quality) fQuality++;
    if (want[i].cite !== got[i].cite) fCite++;
  }
}
console.log("\n== 逐字段差异（共比对 %d 条案例）==", n);
console.log("  scene   :", fScene);
console.log("  score   :", fScore);
console.log("  quality :", fQuality);
console.log("  cite    :", fCite);
console.log("  条数不等:", fLen);
process.exit(problems.length ? 1 : 0);
