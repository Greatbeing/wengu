# -*- coding: utf-8 -*-
"""diagnose_live3.py — 抓住线上检索失败的真因

上一版只监听了 window.error，漏了 unhandledrejection ——
Promise 链里的异常会走后者。这里两者都捕获，并直接读 #panel 的真实内容。
"""
import json
import time

from playwright.sync_api import sync_playwright

URL = "https://greatbeing.github.io/wengu/"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

INIT = r"""
window.__errs = [];
window.addEventListener('error', function (e) {
  window.__errs.push({kind:'error', msg: String(e.message), src: String(e.filename) + ':' + e.lineno});
});
window.addEventListener('unhandledrejection', function (e) {
  var r = e.reason;
  window.__errs.push({kind:'rejection', msg: String(r && (r.stack || r.message || r))});
});
"""
t0 = time.time()
msgs = []

with sync_playwright() as pw:
    try:
        br = pw.chromium.launch(headless=True)
    except Exception:
        br = pw.chromium.launch(executable_path=EDGE, headless=True)
    ctx = br.new_context(viewport={"width": 1440, "height": 960})
    pg = ctx.new_page()
    pg.add_init_script(INIT)
    pg.on("console", lambda m: msgs.append("[%s] %s" % (m.type, m.text[:250])))
    pg.on("pageerror", lambda e: msgs.append("[pageerror] %s" % str(e)[:250]))

    pg.goto(URL, wait_until="domcontentloaded", timeout=120000)
    print("DOMContentLoaded @ %.1fs" % (time.time() - t0))

    pg.wait_for_selector("#examples .chip", timeout=120000)
    print("示例按钮出现 @ %.1fs" % (time.time() - t0))
    print("  #examples 里 chip 数:", pg.eval_on_selector_all("#examples .chip", "els => els.length"))
    print("  #panel 文本(点击前):", json.dumps(
        pg.eval_on_selector("#panel", "el => el.textContent.replace(/\\s+/g,' ').trim().slice(0,120)"),
        ensure_ascii=False))

    pg.query_selector("#examples .chip").click()
    print("\n已点击第一个示例 @ %.1fs" % (time.time() - t0))

    # 等 20 秒，再看面板
    for i in range(10):
        pg.wait_for_timeout(2000)
        n = pg.eval_on_selector_all(".case", "els => els.length")
        ptxt = pg.eval_on_selector("#panel", "el => el.textContent.replace(/\\s+/g,' ').trim()")
        print("  +%2ds  .case=%d  panel=%s" % ((i + 1) * 2, n, json.dumps(ptxt[:110], ensure_ascii=False)))
        if n:
            break

    print("\n=== 页面内捕获到的 JS 错误 ===")
    errs = pg.evaluate("window.__errs")
    if errs:
        for e in errs:
            print("  [%s] %s" % (e["kind"], e["msg"][:400]))
    else:
        print("  （无）")

    print("\n=== 引擎与状态自检 ===")
    print(json.dumps(pg.evaluate("""() => {
      const out = {
        engine: typeof window.WenguEngine,
        engineKeys: window.WenguEngine ? Object.keys(window.WenguEngine) : null,
        panelHTMLlen: (document.querySelector('#panel')||{}).innerHTML ? document.querySelector('#panel').innerHTML.length : 0,
        search: location.search,
        metaText: (document.querySelector('#demoMeta')||{}).textContent,
      };
      return out;
    }"""), ensure_ascii=False, indent=2))

    print("\n=== 控制台 ===")
    for m in (msgs[:15] or ["（无）"]):
        print("  " + m)

    print("\n总耗时 %.1fs" % (time.time() - t0))
    br.close()