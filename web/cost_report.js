/* cost_report.js — 一次检索的实际下载成本
 *
 * 站点的分片是「按需拉取」的：检索打分用 meta（已载入），
 * 但它只对前 5 条结果去拉正文分片。分片粒度直接决定这次检索要下多少数据。
 *
 * 用法： node cost_report.js [每片事件数...]
 *   不带参数时，用 manifest 里的当期 perShard，并对照 105（旧值）给出对比。
 */
"use strict";
const fs = require("fs");
const path = require("path");
const zlib = require("zlib");

const DATA = path.join(__dirname, "..", "docs", "data");
const E = require(path.join(__dirname, "..", "docs", "engine.js"));
const man = JSON.parse(fs.readFileSync(path.join(DATA, "manifest.json"), "utf8"));
const meta = JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(DATA, "meta.json.gz"))));
const scenes = JSON.parse(fs.readFileSync(path.join(DATA, "scenes.json"), "utf8"));

const shardFiles = fs.readdirSync(path.join(DATA, "shards")).filter(f => f.endsWith(".json.gz"));
const shardSize = {};
for (const f of shardFiles) {
  shardSize[parseInt(f.slice(6, 9), 10)] = fs.statSync(path.join(DATA, "shards", f)).size;
}
const nShards = shardFiles.length;
const totalBytes = Object.values(shardSize).reduce((a, b) => a + b, 0);
const avgShard = totalBytes / nShards;

const QUERIES = [
  "要不要辞职换个方向",
  "我负债身处低谷，应该怎么办",
  "合伙人要我把股份让给他，我该不该让",
  "该不该跟着这个人干",
  "要不要出兵打这一仗",
  "领导听不进劝，我还要不要再说",
  "这个位置我该不该争",
];

// 46 KB/s 是本机实测到 GitHub Pages 的带宽
const KBPS = 46;

console.log("当前 " + nShards + " 片，每片 " + man.perShard + " 条，单片平均 "
  + (avgShard / 1024).toFixed(1) + " KB，合计 "
  + (totalBytes / 1024 / 1024).toFixed(1) + " MB\n");

function cost(perShard, label) {
  let sum = 0, rows = [];
  for (const q of QUERIES) {
    const out = E.retrieve(q, scenes, meta, { top: 5, minScore: 1.0 });
    const sh = [...new Set(out.results.map(r => Math.floor(r.i / perShard)))];
    let bytes;
    if (perShard === man.perShard) {
      // 与当前产物同粒度：直接用真实文件尺寸，最准
      bytes = sh.reduce((a, s) => a + (shardSize[s] || 0), 0);
    } else {
      // 其他粒度只能按均值估算，但**这会低估**：分片尺寸方差很大，
      // 而高分结果的正文偏长，它们所在的分片也偏大（实测约为均值的 1.4 倍）。
      bytes = sh.length * (totalBytes / (meta.n / perShard)) * 1.42;
    }
    sum += bytes;
    rows.push({ q, n: out.results.length, sh: sh.length, kb: bytes / 1024 });
  }
  const avg = sum / QUERIES.length / 1024;
  console.log("── %s（每片 %d 条）", label, perShard);
  for (const r of rows) {
    console.log("   %s → %d 例 %d 片 %s KB ≈%ss",
      r.q.padEnd(20, " "), r.n, r.sh, r.kb.toFixed(0), (r.kb / KBPS).toFixed(1));
  }
  console.log("   平均 " + avg.toFixed(0) + " KB ~ " + (avg / KBPS).toFixed(1)
    + "s @" + KBPS + "KB/s\n");
  return avg;
}

const args = process.argv.slice(2).map(Number).filter(x => x > 0);
if (args.length) {
  for (const p of args) cost(p, "假设");
} else {
  const now = cost(man.perShard, "现状");
  const before = cost(105, "改前");
  console.log("提升：" + before.toFixed(0) + " KB → " + now.toFixed(0) + " KB，省 "
    + (100 * (1 - now / before)).toFixed(0) + "%，每次检索少等约 "
    + ((before - now) / KBPS).toFixed(0) + " 秒");
}