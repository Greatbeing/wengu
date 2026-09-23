/* engine.js — 问古检索引擎的浏览器端移植（纯函数，无 DOM）
 *
 * 保真原则
 * --------
 * 本文件是 scripts/retrieve.py 中 match_scenes() 与 score_unit() 的逐句移植。
 * score_unit 的 8 项打分中，7 项所依赖的文本特征（古典词命中／证据词／
 * 后果词／选项对立正则／进言正则／表态正则／长度／有无白话）已由
 * web/build_web_index.py 在构建期用真 Python 引擎算成特征向量，
 * 因此这里只剩算术，不做任何「近似」。
 * 第 4 项（用户关键词）网页版不启用：网页主路径是「描述处境 → 场景匹配」，
 * 关键词直检属 CLI 功能。
 *
 * 并列选项数（n_prop）同样在构建期由 deduce.py 真实现算好，故 deduce 无需移植。
 *
 * 一致性由 web/verify_engine.js 对拍 Python 输出验证，不靠肉眼。
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.WenguEngine = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Python round() 对「精确值」做十进制舍入，.5 取偶（银行家舍入）。
  //
  // 不能用容差判断「是否恰好 .5」：像 39.235 这样的中点根本无法用二进制
  // 精确表示，它的真实双精度值是 39.23499999999999943…（严格小于中点），
  // 容差法会误判成平局而多进一位（实测多出 0.01）。
  // 因此这里把 double 精确分解为 m × 2^e，用 BigInt 做整数除法定舍入方向，
  // 保证与 Python 逐位一致。
  function pyround(x, n) {
    if (!isFinite(x) || x === 0) return x;
    var neg = x < 0;
    var ax = Math.abs(x);

    var dv = new DataView(new ArrayBuffer(8));
    dv.setFloat64(0, ax);
    var hi = dv.getUint32(0), lo = dv.getUint32(4);
    var be = (hi >>> 20) & 0x7ff;
    var m = (BigInt(hi & 0xfffff) << 32n) | BigInt(lo);
    var e;
    if (be === 0) { e = -1074; }                     // 次正规数
    else { m |= (1n << 52n); e = be - 1075; }
    // 现在 ax === m × 2^e

    var A = m * (10n ** BigInt(n));
    if (e < 0) {
      var D = 1n << BigInt(-e);
      var q = A / D, r = A % D, twice = r * 2n;
      if (twice > D) q += 1n;
      else if (twice === D && (q % 2n) === 1n) q += 1n;
      A = q;
    } else {
      A = A << BigInt(e);
    }

    var s = A.toString();
    var out;
    if (n > 0) {
      if (s.length <= n) s = new Array(n - s.length + 1 + 1).join("0") + s;
      out = Number(s.slice(0, s.length - n) + "." + s.slice(s.length - n));
    } else {
      out = Number(s);
    }
    return neg ? -out : out;
  }

  var SCORE_EVIDENCE_CAP = 6.5;
  var SCORE_ADVICE_CAP = 3.0;
  var SCORE_OPTION_CAP = 3.0;
  var SCORE_CONSEQ_CAP = 1.8;

  /* 按 IDF 降序、词本身升序比较。
   * 次级键不是装饰：idf 相同的词若顺序不定，浮点求和次序就不定，
   * 末位差异会在舍入边界翻出 0.01 分差。Python 侧已改为同一规则
   * （key=lambda w: (-idf(w), w)），两边必须一致。 */
  function cmpIdfWord(idfArr, vocab, x, y) {
    var d = idfArr[y] - idfArr[x];
    if (d !== 0) return d;
    var a = vocab[x], b = vocab[y];
    return a < b ? -1 : (a > b ? 1 : 0);
  }

  /* ── match_scenes() 移植 ──
   * 权重：完整现代词 3.0 ｜ 强碎片 1.0 ｜ 弱碎片 0.35 ｜ 单字 0.4（仅无更强信号时）
   * 两处去重与原实现一致：互为子串的命中只保留最长者；modern 与碎片同一场去重。
   */
  function matchScenes(userText, scenes) {
    var text = String(userText || "").toLowerCase();
    var out = [];

    for (var si = 0; si < scenes.length; si++) {
      var s = scenes[si];
      var exact = [];
      for (var a = 0; a < s.modern.length; a++) {
        if (text.indexOf(String(s.modern[a]).toLowerCase()) >= 0) exact.push(s.modern[a]);
      }
      var weak = {};
      for (var b = 0; b < s.weak.length; b++) weak[s.weak[b]] = true;

      var raw = [];
      for (var c = 0; c < s.stems.length; c++) {
        if (text.indexOf(s.stems[c]) >= 0) raw.push(s.stems[c]);
      }

      var cand = [], seen = {};
      for (var d = 0; d < exact.length; d++) {
        if (!seen[exact[d]]) { seen[exact[d]] = true; cand.push([exact[d], true]); }
      }
      for (var e = 0; e < raw.length; e++) {
        if (!seen[raw[e]]) { seen[raw[e]] = true; cand.push([raw[e], false]); }
      }
      cand.sort(function (x, y) { return y[0].length - x[0].length; });

      var final = [];
      for (var g = 0; g < cand.length; g++) {
        var w = cand[g][0], isSub = false;
        for (var h = 0; h < final.length; h++) {
          if (final[h][0].indexOf(w) >= 0) { isSub = true; break; }
        }
        if (!isSub) final.push(cand[g]);
      }

      var ex = [], kept = [];
      for (var k = 0; k < final.length; k++) {
        if (final[k][1]) ex.push(final[k][0]); else kept.push(final[k][0]);
      }
      var strong = [], wk = [], short = [];
      for (var m = 0; m < kept.length; m++) {
        var q = kept[m];
        if (weak[q]) wk.push(q);
        else if (q.length >= 2) strong.push(q);
        else if (q.length === 1) short.push(q);
      }

      var score = ex.length * 3.0 + strong.length * 1.0 + wk.length * 0.35;
      if (!ex.length && !strong.length) score += short.length * 0.4;
      if (score <= 0) continue;

      out.push({
        score: pyround(score, 2),
        id: s.id,
        hits: ex.concat(strong, wk, short),
      });
    }

    out.sort(function (x, y) {
      if (y.score !== x.score) return y.score - x.score;
      if (y.hits.length !== x.hits.length) return y.hits.length - x.hits.length;
      return x.id < y.id ? -1 : (x.id > y.id ? 1 : 0);
    });
    return out;
  }

  /* ── score_unit() 移植（特征来自构建期预计算）──
   * 返回 {sc, reasons}
   */
  function scoreEvent(i, scene, meta, sceneClsSet, clsIdfArr, evdIdfArr, cqIdfArr) {
    var row = meta.events[i];
    // 行格式见 build_web_index.py：
    // 0 cite, 1 source, 2 time, 3 chars, 4 hasTr, 5 optA, 6 optB,
    // 7 advice, 8 verdict, 9 clsIds, 10 evdIds, 11 cqIds
    var chars = row[3], hasTr = row[4];
    var opt = row[5] + row[6];
    var advice = row[7], verdict = row[8];
    var clsIds = row[9], evdIds = row[10], cqIds = row[11];

    var sc = 0.0;
    var reasons = [];

    // 1) 古典信号词：按稀有度加权（场景词 ∩ 命中词）
    var hits = [];
    for (var a = 0; a < clsIds.length; a++) {
      if (sceneClsSet[clsIds[a]]) hits.push(clsIds[a]);
    }
    if (hits.length) {
      hits.sort(function (x, y) { return cmpIdfWord(clsIdfArr, meta.clsVocab, x, y); });
      var sw = 0;
      for (var b = 0; b < hits.length; b++) sw += clsIdfArr[hits[b]];
      sc += Math.min(SCORE_EVIDENCE_CAP, sw * 0.55);
      var names = [];
      for (var c = 0; c < Math.min(6, hits.length); c++) names.push(meta.clsVocab[hits[c]]);
      reasons.push("古典信号(按稀有度):" + names.join("/"));
    }

    // 2) 抉择证据词
    if (evdIds.length) {
      var ev = evdIds.slice().sort(function (x, y) { return cmpIdfWord(evdIdfArr, meta.evdVocab, x, y); });
      var se = 0;
      for (var d = 0; d < ev.length; d++) se += evdIdfArr[ev[d]];
      sc += Math.min(SCORE_ADVICE_CAP, se * 0.32);
      var en = [];
      for (var f = 0; f < Math.min(5, ev.length); f++) en.push(meta.evdVocab[ev[f]]);
      reasons.push("抉择证据:" + en.join("/"));
    }

    // 3) 选项对立结构
    if (opt) {
      sc += Math.min(SCORE_OPTION_CAP, opt * 1.1);
      reasons.push("选项对立:" + opt + "层");
    }

    // 4) 用户关键词 —— 网页版不启用（见文件头说明）

    // 5) 有白话译文加分
    if (hasTr) sc += 0.3;

    // 6) 后果/代价信息
    if (cqIds.length) {
      var cq = cqIds.slice().sort(function (x, y) { return cmpIdfWord(cqIdfArr, meta.cqVocab, x, y); });
      var sq = 0;
      for (var g = 0; g < cq.length; g++) sq += cqIdfArr[cq[g]];
      sc += Math.min(SCORE_CONSEQ_CAP, sq * 0.22);
      reasons.push("后果信息:" + cq.length + "项");
    }

    // 7) 长度归一
    if (chars < 60) sc -= 2.5;
    else if (chars >= 150 && chars <= 800) sc += 0.8;

    // 8) 双向对话：既有进言、又有表态
    if (advice && verdict) {
      sc += 1.6;
      reasons.push("双向对话:进言+表态");
    }

    return { sc: sc, reasons: reasons };
  }

  /* ── retrieve() 移植 ──
   * 返回 {matched, results}；results 只含下标与打分，正文由调用方按需取。
   */
  function retrieve(userText, scenesData, meta, opts) {
    opts = opts || {};
    var top = opts.top || 5;
    var minScore = opts.minScore === undefined ? 1.0 : opts.minScore;

    var scenes = scenesData.scenes;
    var idf = scenesData.idf || {};
    var matched = matchScenes(userText, scenes);

    var byId = {};
    var sceneClsSet = {};
    var sceneClsIdf = {};
    for (var i = 0; i < scenes.length; i++) {
      var s = scenes[i];
      byId[s.id] = s;
      var set = {}, arr = [];
      for (var j = 0; j < s.clsIds.length; j++) {
        var wi = s.clsIds[j];
        set[wi] = true;
        arr.push(wi);
      }
      sceneClsSet[s.id] = set;
      sceneClsIdf[s.id] = arr;
    }

    // 每个词的 IDF（构建期已把三个词表的 IDF 展平成数组，与 id 对齐）
    var clsIdfArr = [], evdIdfArr = [], cqIdfArr = [];
    for (var a = 0; a < meta.clsVocab.length; a++) clsIdfArr.push(meta.clsIdf[meta.clsVocab[a]] || 1.0);
    for (var b = 0; b < meta.evdVocab.length; b++) evdIdfArr.push(meta.evdIdf[meta.evdVocab[b]] || 1.0);
    for (var c = 0; c < meta.cqVocab.length; c++) cqIdfArr.push(meta.cqIdf[meta.cqVocab[c]] || 1.0);

    var target = [];
    if (matched.length) {
      var head = matched.slice(0, 3);
      var total = 0;
      for (var d = 0; d < head.length; d++) total += head[d].score;
      if (!total) total = 1.0;
      for (var e = 0; e < head.length; e++) {
        target.push({ id: head[e].id, w: head[e].score / total });
      }
    }

    var results = [];
    for (var t = 0; t < target.length; t++) {
      var sid = target[t].id, w = target[t].w;
      var scene = byId[sid];
      if (!scene) continue;
      var sset = sceneClsSet[sid];

      for (var idx = 0; idx < meta.events.length; idx++) {
        var r = scoreEvent(idx, scene, meta, sset, clsIdfArr, evdIdfArr, cqIdfArr);
        if (r.sc < minScore) continue;
        var final = r.sc * (0.55 + 1.45 * w);
        results.push({
          i: idx,
          scene: sid,
          scene_name: scene.name,
          quality: pyround(r.sc, 2),
          sc_raw: r.sc,
          score: pyround(final, 2),
          reasons: r.reasons.concat(["场景权重:" + w.toFixed(2)]),
        });
      }
    }

    results.sort(function (x, y) { return y.score - x.score; });

    // 二次排序：并列选项数（构建期由 deduce.py 真实现算好）
    var head2 = results.slice(0, 40);
    for (var h = 0; h < head2.length; h++) {
      var rr = head2[h];
      var map = meta.nprop[rr.scene] || {};
      var np = map[rr.i];
      if (np === undefined) continue;
      rr.n_proposals = np;
      if (np >= 2) {
        rr.score = pyround(rr.score * 1.18, 2);
        rr.reasons.push("并列选项:" + np);
      } else if (np === 0) {
        rr.score = pyround(rr.score * 0.85, 2);
        rr.reasons.push("无并列选项");
      }
    }
    results.sort(function (x, y) { return y.score - x.score; });

    // 去重（同源同段可能多场景命中），取前 top 条
    var seen = {}, uniq = [];
    for (var u = 0; u < results.length; u++) {
      var key = results[u].i;
      if (seen[key]) continue;
      seen[key] = true;
      uniq.push(results[u]);
      if (uniq.length >= top) break;
    }

    return { matched: matched, results: uniq };
  }

  return {
    pyround: pyround,
    matchScenes: matchScenes,
    scoreEvent: scoreEvent,
    retrieve: retrieve,
  };
});
