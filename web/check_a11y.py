# -*- coding: utf-8 -*-
"""check_a11y.py — 控件边界对比度（WCAG 1.4.11 要求 3:1）与首屏可交互时间"""
import json
import os
import time

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8777/docs/"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

JS = r"""
() => {
  function lum(c) {
    const m = c.match(/[\d.]+/g);
    if (!m) return null;
    const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(m[0]) + 0.7152 * f(m[1]) + 0.0722 * f(m[2]);
  }
  const ratio = (a, b) => {
    if (a === null || b === null) return null;
    const hi = Math.max(a, b), lo = Math.min(a, b);
    return Math.round(((hi + 0.05) / (lo + 0.05)) * 100) / 100;
  };
  const pageBg = getComputedStyle(document.body).backgroundColor;
  const lp = lum(pageBg);

  function probe(sel) {
    const el = document.querySelector(sel);
    if (!el) return { missing: true };
    const s = getComputedStyle(el);
    const bc = s.borderTopColor;
    const lb = lum(bc);
    // 1.4.11 要比的是「控件边界 vs 它的外侧邻色」——即页面底色。
    // 比「边框 vs 自身底色」对填充按钮毫无意义（边框与底色同色，恒为 1.00）。
    let ownBg = s.backgroundColor;
    const lo = (ownBg && ownBg !== 'rgba(0, 0, 0, 0)') ? lum(ownBg) : null;
    return {
      border: bc,
      vsPage: ratio(lb, lp),
      vsOwnBg: lo === null ? null : ratio(lb, lo),
    };
  }

  const rootCS = getComputedStyle(document.documentElement);
  const out = { _vars: {
    theme: document.documentElement.getAttribute('data-theme'),
    paper: rootCS.getPropertyValue('--paper').trim(),
    accent: rootCS.getPropertyValue('--accent').trim(),
    lineInput: rootCS.getPropertyValue('--line-input').trim(),
  } };
  ['.ask__field', '.chip', '.theme-btn', '.btn'].forEach(sel => { out[sel] = probe(sel); });
  return out;
}
"""

t = {}
with sync_playwright() as pw:
    try:
        br = pw.chromium.launch(headless=True)
    except Exception:
        br = pw.chromium.launch(executable_path=EDGE, headless=True)
    ctx = br.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()

    t0 = time.time()
    pg.goto(URL, wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_selector("#examples .chip", timeout=30000)
    t["interactive"] = int((time.time() - t0) * 1000)

    t1 = time.time()
    pg.wait_for_function("() => document.getElementById('panel').innerText.indexOf('描述你的处境') >= 0",
                         timeout=30000)
    t["idle_shown"] = int((time.time() - t1) * 1000)

    pg.wait_for_function("() => document.getElementById('demoMeta').innerText.indexOf('51/51') >= 0",
                         timeout=60000)
    t["index_ready_total"] = int((time.time() - t0) * 1000)

    print("== 首屏时序 ==")
    print("  可交互（示例按钮可点）      %6d ms" % t["interactive"])
    print("  静息态出现                  %6d ms" % t["idle_shown"])
    print("  索引就绪（从导航起算）      %6d ms" % t["index_ready_total"])

    print("\n== 控件边界对比度（1.4.11 要求边界对**外侧邻色** ≥ 3:1）==")
    res = pg.evaluate(JS)
    allok = True
    print("  主题变量:", res["_vars"])
    for sel, d in res.items():
        if sel == "_vars" or d.get("missing"):
            continue
        ok = (d["vsPage"] or 0) >= 3.0
        allok &= ok
        print("  %-14s border %-18s vs页面(外侧) %5.2f  vs自身底色 %s  %s"
              % (sel, d["border"], d["vsPage"] or -1,
                 ("%5.2f" % d["vsOwnBg"]) if d["vsOwnBg"] else "  n/a",
                 "✓" if ok else "✗ 未达标"))

    print("\n== 深色模式 ==")
    pg.evaluate("document.documentElement.setAttribute('data-theme','dark')")
    pg.wait_for_timeout(900)
    res2 = pg.evaluate(JS)
    print("  主题变量:", res2["_vars"])
    for sel, d in res2.items():
        if sel == "_vars" or d.get("missing"):
            continue
        ok = (d["vsPage"] or 0) >= 3.0
        allok &= ok
        print("  %-14s border %-18s vs页面(外侧) %5.2f  %s"
              % (sel, d["border"], d["vsPage"] or -1, "✓" if ok else "✗ 未达标"))

    print("\n总体:", "全部达标" if allok else "有未达标项")
    br.close()