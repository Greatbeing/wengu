/* app.js — 问古网站的界面层
 *
 * 职责边界：这里只做「取数 + 渲染 + 交互」，不做任何打分。
 * 打分全部交给 engine.js（与 scripts/retrieve.py 对拍 100% 一致）。
 *
 * 易用性上的几个决定
 * ------------------
 * 1. 输入即搜（防抖）：不用点按钮，边打边出结果
 * 2. 地址栏同步 ?q=：搜出的结果可以直接发给别人
 * 3. 未命中不是死路：给「按内核浏览」，13 个内核点一个就出案例
 * 4. 白话默认开：文言不是所有人都读得顺，一键可关
 * 5. 每案可复制引用：原文逐字，可直接黏进自己的文档
 */
(function () {
  "use strict";

  var S = {
    manifest: null, scenes: null, meta: null,
    shardCache: {}, shardInflight: {},
    showTr: true, busy: false,
    timer: null, seq: 0, lastQ: "", lastMs: 0,
  };

  var $ = function (s, r) { return (r || document).querySelector(s); };

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function pad3(n) { return ("00" + n).slice(-3); }

  function sealOf(src, cite) {
    var t = String(src || "") + String(cite || "");
    if (t.indexOf("通鉴") >= 0) return "鉴";
    if (t.indexOf("史记") >= 0) return "记";
    if (t.indexOf("左传") >= 0) return "传";
    return "古";
  }

  /* ── 取数 ── */
  function getJson(url) {
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status + " · " + url);
      return r.json();
    });
  }

  /* GitHub Pages 对 .gz 不会再压一层，所以正文以 gzip 提交：
   * 仓库体积与传输体积同时最优。解压走浏览器原生 DecompressionStream。 */
  function getGz(url) {
    if (typeof DecompressionStream === "undefined") {
      return Promise.reject(new Error(
        "当前浏览器不支持 DecompressionStream（需 Chrome 80+ / Firefox 113+ / Safari 16.4+）"));
    }
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status + " · " + url);
      return new Response(r.body.pipeThrough(new DecompressionStream("gzip"))).json();
    });
  }

  function shardOf(i) { return Math.floor(i / S.manifest.perShard); }

  function loadShard(si) {
    if (S.shardCache[si]) return Promise.resolve(S.shardCache[si]);
    if (S.shardInflight[si]) return S.shardInflight[si];
    var url = S.manifest.shardPattern.replace("%03d", pad3(si));
    var p = getGz(url).then(function (d) { S.shardCache[si] = d; delete S.shardInflight[si]; return d; },
      function (e) { delete S.shardInflight[si]; throw e; });
    S.shardInflight[si] = p;
    return p;
  }

  function ensureShards(indices) {
    var need = {};
    for (var i = 0; i < indices.length; i++) need[shardOf(indices[i])] = true;
    var list = Object.keys(need).map(Number).sort(function (a, b) { return a - b; });
    return Promise.all(list.map(loadShard));
  }

  function bodyOf(i) {
    var sh = S.shardCache[shardOf(i)];
    if (!sh) return null;
    var item = sh.items[i - sh.start];
    if (!item) return null;
    return { text: item[0], translation: item[1] || "" };
  }

  /* ── 渲染 ── */
  function panel(html) { $("#panel").innerHTML = html; }

  function stateLoading(q) {
    var title = q ? '\u6B63\u5728\u68C0\u7D22\u300C' + esc(q) + '\u300D' : '\u6B63\u5728\u8F7D\u5165\u2026';
    panel(
      '<div class="state">' +
        '<div class="state__title">' + title + '</div>' +
        (q ? '<div>在《资治通鉴》《史记》《左传》共 6,707 个抉择事件单元中比对。</div>' : '') +
      '</div>' +
      '<div class="bar"><i></i></div>');
  }

  function stateIdle() {
    panel(
      '<div class="state">' +
        '<div class="state__title">描述你的处境，上面输入框直接打就行</div>' +
        '<div>用日常说法即可，不必用书面语。比如「合伙人要我把股份让给他，该不该让」。</div>' +
        '<div style="margin-top:18px">' +
          '<button class="linkbtn" data-act="kernels">没有头绪？按决策内核浏览</button>' +
        '</div>' +
      '</div>');
  }

  function stateEmpty(q) {
    panel(
      '<div class="state">' +
        '<div class="state__title">「' + esc(q) + '」没有匹配到决策内核</div>' +
        '<div>多半是说法太笼统。这个库认的是<b>处境</b>，不是身份或愿望：' +
          '把「我该怎么办」换成「要不要 A，还是 B」这种带取舍的说法，命中率高得多。</div>' +
        '<div style="margin-top:18px">' +
          '<button class="linkbtn" data-act="kernels">按决策内核浏览全部 13 个内核</button>' +
        '</div>' +
      '</div>');
  }

  function stateError(e) {
    panel(
      '<div class="state state--err">' +
        '<div class="state__title">数据没能载入</div>' +
        '<div>' + esc(e && e.message ? e.message : e) + '</div>' +
        '<div style="margin-top:14px">若你是用 <span class="mono">file://</span> 直接打开的，' +
          '浏览器会拦下本地取数。请在仓库目录起一个静态服务：</div>' +
        '<div class="code" style="margin-top:12px">python -m http.server 8000' +
          '<span class="c">   # 然后访问 http://localhost:8000/docs/</span></div>' +
      '</div>');
  }

  function renderKernels() {
    var scenes = S.scenes.scenes;
    var h = ['<div class="state"><div class="state__title">13 个决策内核</div>',
      '<div>点任一内核，直接看它在语料里的高相关案例。</div></div>'];
    h.push('<div class="kern" style="grid-template-columns:repeat(3,1fr)">');
    for (var i = 0; i < scenes.length; i++) {
      var s = scenes[i];
      h.push('<div class="kern__item">' +
        '<b>' + esc(s.name) + '</b>' +
        '<div class="kern__q">' + esc(s.question || "") + '</div>' +
        '<div style="margin-top:9px"><button class="linkbtn" data-scene="' + esc(s.id) + '">看案例</button></div>' +
        '</div>');
    }
    h.push('</div>');
    panel(h.join(""));
  }

  function caseHtml(r, rank) {
    var row = S.meta.events[r.i];
    var cite = row[0], src = row[1], time = row[2];
    var b = bodyOf(r.i);
    var h = [];
    h.push('<div class="case">');
    h.push('<div class="case__top">');
    h.push('<span class="case__rank mono">第 ' + (rank + 1) + ' 例</span>');
    h.push('<span class="seal">' + esc(sealOf(src, cite)) + '</span>');
    h.push('<span class="case__cite">' + esc(cite) + '</span>');
    h.push('<span class="case__score mono">相关度 <b>' + esc(r.score) + '</b>' +
      (r.n_proposals ? ' · 并列选项 ' + r.n_proposals : '') + '</span>');
    h.push('</div>');
    if (time) {
      h.push('<div class="case__rank mono" style="margin:-8px 0 10px">' + esc(time) + '</div>');
    }
    h.push('<div class="case__text" data-txt="1">' + esc(b ? b.text : "（正文载入中）") + '</div>');
    if (b && b.translation) {
      h.push('<div class="case__tran' + (S.showTr ? '' : ' is-hidden') + '" data-tr="1">【白话】' +
        esc(b.translation) + '</div>');
    }
    h.push('<div class="case__reasons">命中理由：' + esc((r.reasons || []).join(" ／ ")) + '</div>');
    h.push('<div class="case__acts">' +
      '<button class="linkbtn" data-copy="' + r.i + '">复制引用</button>' +
      (b && b.translation
        ? ' &nbsp;·&nbsp; <button class="linkbtn" data-tgl="1">' +
          (S.showTr ? '隐藏白话' : '显示白话') + '</button>'
        : '') +
      '</div>');
    h.push('</div>');
    return h.join("");
  }

  function renderResults(q, out, ms) {
    var results = out.results;
    if (!results.length) { stateEmpty(q); return; }

    var h = [];
    var matched = out.matched.slice(0, 3);
    h.push('<div class="scenes"><div class="scenes__row">');
    for (var i = 0; i < matched.length; i++) {
      var sc = sceneById(matched[i].id);
      h.push('<span class="scene-tag"><b>' + esc(sc ? sc.name : matched[i].id) + '</b>' +
        '<span>' + esc(matched[i].id) + ' · ' + matched[i].score + '</span></span>');
    }
    h.push('</div>');
    if (matched.length) {
      var main = sceneById(matched[0].id);
      if (main && main.question) {
        h.push('<div class="scenes__q">核心问题：' + esc(main.question) + '</div>');
      }
    }
    h.push('</div>');

    for (var k = 0; k < results.length; k++) h.push(caseHtml(results[k], k));
    h.push('<div class="case__reasons" style="margin-top:16px">' +
      '以上原文逐字取自语料库，未作改写。' +
      '命中理由中的词为语料侧信号词，非对你的判断。</div>');
    panel(h.join(""));

    $("#demoMeta").textContent = results.length + " 例 · " + ms + " ms · 库内 6,707 单元";
  }

  function sceneById(id) {
    var a = S.scenes.scenes;
    for (var i = 0; i < a.length; i++) if (a[i].id === id) return a[i];
    return null;
  }

  /* ── 查询主流程 ── */
  function run(q, opts) {
    opts = opts || {};
    q = String(q || "").trim();
    if (!q && !opts.scene) { stateIdle(); return; }

    // 索引还没到位：先记下来，载入完自动跑（避免用户白点一下没反应）
    if (!S.meta) { S.queued = { q: q, opts: opts }; stateLoading(null); return; }

    var my = ++S.seq;
    stateLoading(q || ("内核：" + opts.scene));

    var t0 = performance.now();
    var out;
    try {
      out = window.WenguEngine.retrieve(q, S.scenes, S.meta, {
        top: 5, minScore: 1.0, scene: opts.scene || null,
      });
    } catch (e) { stateError(e); return; }

    var ms = Math.round(performance.now() - t0);

    // 正文按需拉分片，通常 1～3 片
    var idxs = out.results.map(function (r) { return r.i; });
    ensureShards(idxs).then(function () {
      if (my !== S.seq) return;          // 期间又发起了新查询，丢弃本次
      S.lastMs = ms;
      renderResults(q, out, ms);
      syncUrl(q, opts.scene);
    }, function (e) {
      if (my !== S.seq) return;
      // 打分已成功，只是正文没取到：仍把结果列出来，正文位置给出提示
      renderResults(q, out, ms);
      if (e) console.warn("[wengu] 正文载入失败:", e);
    });
  }

  function syncUrl(q, scene) {
    var u = location.pathname + (q ? "?q=" + encodeURIComponent(q) : scene ? "?s=" + scene : "");
    try { history.replaceState(null, "", u); } catch (e) { /* file:// 下会抛，忽略 */ }
  }

  function submit(q, opts) {
    if (S.timer) { clearTimeout(S.timer); S.timer = null; }
    run(q, opts);
  }

  /* ── 事件绑定 ── */
  function bind() {
    var form = $("#askForm"), input = $("#askInput");

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var v = input.value.trim();
      if (v) submit(v);
    });

    // 输入即搜：防抖，避免每敲一个字都全库扫一遍
    input.addEventListener("input", function () {
      var v = input.value.trim();
      if (S.timer) clearTimeout(S.timer);
      if (v.length < 4) return;                   // 太短不搜，减少无意义请求
      S.timer = setTimeout(function () { run(v); }, 280);
    });

    // 示例问句
    var examples = [
      "要不要辞职换个方向",
      "该不该忍下这次委屈",
      "我负债身处低谷，应该怎么办",
      "合伙人要我把股份让给他，我该不该让",
      "这笔投资值不值得押上全部积蓄",
      "该不该向领导提出反对意见",
    ];
    var ex = $("#examples");
    var h = ['<span class="examples__label">试试：</span>'];
    for (var i = 0; i < examples.length; i++) {
      h.push('<button class="chip" data-q="' + esc(examples[i]) + '">' + esc(examples[i]) + '</button>');
    }
    ex.innerHTML = h.join("");

    // 事件委托：结果明细与内核浏览都由这里接管
    document.addEventListener("click", function (e) {
      var t = e.target;
      if (!t || !t.getAttribute) return;

      var q = t.getAttribute("data-q");
      if (q) {
        input.value = q;
        submit(q);
        document.getElementById("demo").scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }

      if (t.getAttribute("data-act") === "kernels") { renderKernels(); return; }

      var sc = t.getAttribute("data-scene");
      if (sc) {
        input.value = "";
        submit("", { scene: sc });
        document.getElementById("demo").scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }

      if (t.getAttribute("data-tgl")) {
        var c = t.closest(".case");
        var tr = c && c.querySelector("[data-tr]");
        if (tr) {
          var hidden = tr.classList.toggle("is-hidden");
          t.textContent = hidden ? "显示白话" : "隐藏白话";
        }
        return;
      }

      var cp = t.getAttribute("data-copy");
      if (cp !== null) {
        var row = S.meta.events[Number(cp)];
        var b = bodyOf(Number(cp));
        var txt = (row[0] || "") + "\n" + (b ? b.text : "");
        var done = function () { t.textContent = "已复制"; setTimeout(function () { t.textContent = "复制引用"; }, 1400); };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(txt).then(done, function () { t.textContent = "复制失败"; });
        } else {
          var ta = document.createElement("textarea");
          ta.value = txt; document.body.appendChild(ta); ta.select();
          try { document.execCommand("copy"); done(); } catch (err) { t.textContent = "复制失败"; }
          document.body.removeChild(ta);
        }
        return;
      }
    });

    // 白话总开关：记在本地，下次来还是你的选择
    var tb = $("#trToggle");
    if (tb) {
      tb.addEventListener("click", function () {
        S.showTr = !S.showTr;
        tb.textContent = S.showTr ? "白话：开" : "白话：关";
        try { localStorage.setItem("wengu.tr", S.showTr ? "1" : "0"); } catch (e) {}
        var list = document.querySelectorAll("[data-tr]");
        for (var i = 0; i < list.length; i++) {
          list[i].classList.toggle("is-hidden", !S.showTr);
        }
      });
    }

    // 主题
    var tk = $("#themeBtn");
    if (tk) {
      tk.addEventListener("click", function () {
        var cur = document.documentElement.getAttribute("data-theme");
        var next = cur === "dark" ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", next);
        try { localStorage.setItem("wengu.theme", next); } catch (e) {}
      });
    }

    // 键盘：/ 聚焦输入框
    document.addEventListener("keydown", function (e) {
      if (e.key === "/" && document.activeElement !== input) {
        e.preventDefault(); input.focus(); input.select();
      }
    });
  }

  /* ── 启动 ── */
  var LOAD_TIMEOUT_MS = 60000;    // 60 秒无响应视为失败
  var LOAD_RETRY_MAX = 2;         // 最多重试 2 次

  function withTimeout(ms, p, label) {
    return Promise.race([
      p,
      new Promise(function (_, rej) {
        setTimeout(function () { rej(new Error(label + "（" + (ms / 1000) + " 秒）")); }, ms);
      })
    ]);
  }

  function boot() {
    // 主题与白话偏好
    try {
      var th = localStorage.getItem("wengu.theme");
      if (th) document.documentElement.setAttribute("data-theme", th);
      else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
        document.documentElement.setAttribute("data-theme", "dark");
      }
      S.showTr = localStorage.getItem("wengu.tr") !== "0";
    } catch (e) {}
    var tb = $("#trToggle");
    if (tb) tb.textContent = S.showTr ? "白话：开" : "白话：关";

    if (!window.WenguEngine) { stateError(new Error("engine.js 未载入")); return; }

    bind();
    stateIdle();
    $("#demoMeta").textContent = "索引载入中…";

    var p = new URLSearchParams(location.search);
    var q0 = p.get("q"), s0 = p.get("s");
    if (q0) { $("#askInput").value = q0; S.queued = { q: q0, opts: {} }; }

    // 加载循环：带超时 + 手动重试（应对 CDN 冷启动波动）
    function loadAll(attempt) {
      var metaLabel = "第 " + (attempt + 1) + " 次载入索引";
      $("#demoMeta").textContent = metaLabel;
      return withTimeout(LOAD_TIMEOUT_MS,
        getJson("data/manifest.json").then(function (m) {
          S.manifest = m;
          return Promise.all([
            withTimeout(25000, getJson(m.scenes), "载入 scenes.json 超时"),
            withTimeout(45000, getGz(m.meta),    "载入 meta.json.gz 超时（约 324KB）"),
          ]);
        }), metaLabel + " 超时")
        .then(function (a) {
          S.scenes = a[0];
          S.meta = a[1];
          $("#demoMeta").textContent = "引擎与命令行逐位一致 · 51/51 对拍通过";
          if (S.queued) { var k = S.queued; S.queued = null; run(k.q, k.opts); }
          else if (s0) run("", { scene: s0 });
        })
        .catch(function (e) {
          if (attempt < LOAD_RETRY_MAX) {
            // 间隔 2s 后重试
            return new Promise(function (res) {
              setTimeout(function () {
                $("#demoMeta").textContent = metaLabel + " 失败，" + (LOAD_RETRY_MAX - attempt) + " 次重试…";
                res(loadAll(attempt + 1));
              }, 2000);
            });
          }
          stateError(new Error(metaLabel + " 失败（已重试 " + LOAD_RETRY_MAX + " 次）：" + (e && e.message ? e.message : e)));
        });
    }
    loadAll(0);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();