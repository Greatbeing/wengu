# -*- coding: utf-8 -*-
"""diagnose_live.py — 线上检索失败的真实原因（捕获全部控制台输出与面板状态）"""
import json
import os
from playwright.sync_api import sync_playwright

LIVE = "https://greatbeing.github.io/wengu/"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

msgs = []

with sync_playwright() as pw:
    try:
        br = pw.chromium.launch(headless=True)
    except Exception:
        br = pw.chromium.launch(executable_path=EDGE, headless=True)
    pg = br.new_context(viewport={"width": 1440, "height": 900}).new_page()
    pg.on("console", lambda m: msgs.append("[%s] %s" % (m.type, m.text)))
    pg.on("pageerror", lambda e: msgs.append("[PAGEERROR] %s" % e))
    pg.on("requestfailed", lambda r: msgs.append("[REQFAIL] %s :: %s" % (r.url, r.failure)))
    pg.on("response", lambda r: msgs.append("[RESP %d] %s" % (r.status, r.url.split("/wengu/")[-1]))
          if r.status >= 400 else None)

    pg.goto(LIVE, wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_selector("#examples .chip", timeout=60000)
    pg.wait_for_timeout(2500)

    print("=== 初始面板 ===")
    print(pg.inner_text("#panel")[:300])
    print("\n=== 引擎是否就位 ===", pg.evaluate("typeof window.WenguEngine"))

    # 直接在页面上下文里手测取数链路，逐条报状态
    probe = pg.evaluate(r"""
    async () => {
      const out = {};
      const tryFetch = async (u, gz) => {
        try {
          const r = await fetch(u);
          out[u] = { status: r.status, ok: r.ok, ctype: r.headers.get('content-type') };
          if (gz && r.ok) {
            try {
              const j = await new Response(r.body.pipeThrough(new DecompressionStream('gzip'))).json();
              out[u].gz_ok = true;
              out[u].keys = Object.keys(j).slice(0, 6);
            } catch (e) { out[u].gz_ERR = String(e); }
          }
          return r;
        } catch (e) { out[u] = { ERR: String(e) }; }
      };
      out.canDS = (typeof DecompressionStream !== 'undefined');
      await tryFetch('data/manifest.json', false);
      await tryFetch('data/scenes.json', false);
      await tryFetch('data/meta.json.gz', true);
      await tryFetch('data/shards/shard-000.json.gz', true);
      return out;
    }
    """)
    print("\n=== 取数链路手测 ===")
    print(json.dumps(probe, ensure_ascii=False, indent=2))

    # 走 UI 路径触发一次
    pg.fill("#askInput", "要不要辞职换个方向")
    pg.click("button[type=submit]")
    pg.wait_for_timeout(6000)
    print("\n=== 检索后面板 ===")
    print(pg.inner_text("#panel")[:400])
    print("\n=== 检索后 demoMeta ===", pg.inner_text("#demoMeta"))

    # 直接调引擎，看纯逻辑是否可用
    direct = pg.evaluate(r"""
    () => {
      try {
        if (!window.WenguEngine) return {err: 'engine 缺失'};
        return {err: null, note: '引擎存在', api: Object.keys(window.WenguEngine)};
      } catch (e) { return {err: String(e)}; }
    }
    """)
    print("\n=== 引擎 API ===", direct)
    br.close()

print("\n=== 全部控制台输出 ===")
for m in msgs[:60]:
    print(m)