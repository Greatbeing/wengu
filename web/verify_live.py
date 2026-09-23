# -*- coding: utf-8 -*-
"""verify_live.py — 线上站点端到端验收

本地跑通不等于线上跑通：线上走 HTTPS + CDN，.json.gz 的解压链路
（Content-Encoding 不被二次处理、CORS、DecompressionStream）必须在真域名上验。

对比的是当场跑出的 Python 引擎结果，不是旧文件。
"""
import json
import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

LIVE = "https://greatbeing.github.io/wengu/"
QUERY = "要不要辞职换个方向"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "shots")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def main():
    os.makedirs(OUT, exist_ok=True)
    rep = {}
    console, failed, resp = [], [], []

    with sync_playwright() as pw:
        try:
            br = pw.chromium.launch(headless=True)
            rep["browser"] = "bundled chromium"
        except Exception:
            br = pw.chromium.launch(executable_path=EDGE, headless=True)
            rep["browser"] = "system Edge"

        ctx = br.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()
        pg.on("console", lambda m: console.append(m.type + ": " + m.text)
              if m.type in ("error", "warning") else None)
        pg.on("pageerror", lambda e: console.append("pageerror: " + str(e)))
        pg.on("requestfailed", lambda r: failed.append(r.url + " :: " + str(r.failure)))
        pg.on("response", lambda r: resp.append((r.url, r.status, r.headers.get("content-type", ""))))

        t0 = time.time()
        # 不用 networkidle：GitHub Pages 首次冷启动时它可能一直等不到静默期。
        # 改为 domcontentloaded + 显式等元素，语义也更明确。
        pg.goto(LIVE, wait_until="domcontentloaded", timeout=90000)
        pg.wait_for_selector("#examples .chip", timeout=60000)
        rep["load_ms"] = int((time.time() - t0) * 1000)
        pg.wait_for_timeout(2000)

        rep["title"] = pg.title()
        rep["engine_present"] = pg.evaluate("typeof window.WenguEngine")
        rep["demo_meta_before"] = pg.inner_text("#demoMeta")
        rep["panel_before"] = pg.inner_text("#panel")[:90]

        # 用 UI 路径跑一次真实检索
        pg.fill("#askInput", QUERY)
        pg.click("button[type=submit]")
        pg.wait_for_selector(".case", timeout=90000)
        pg.wait_for_timeout(2000)

        cases = pg.eval_on_selector_all(".case", r"""els => els.map(e => ({
            cite: e.querySelector('.case__cite').innerText,
            score: e.querySelector('.case__score').innerText.replace(/\s+/g,' '),
            text: e.querySelector('.case__text').innerText.slice(0,120),
            textLen: e.querySelector('.case__text').innerText.length,
            tranVisible: (()=>{const t=e.querySelector('[data-tr]'); return t ? !t.classList.contains('is-hidden') : null;})(),
            loaded: e.querySelector('.case__text').innerText.indexOf('正文载入中') < 0,
        }))""")
        rep["case_count"] = len(cases)
        rep["all_bodies_loaded"] = all(c["loaded"] for c in cases)
        rep["all_tran_visible"] = all(c["tranVisible"] for c in cases)
        rep["first"] = cases[0] if cases else None
        rep["demo_meta_after"] = pg.inner_text("#demoMeta")

        # 地址栏是否同步（可分享）
        rep["url_after"] = pg.url

        # 与 Python 引擎实时对比
        sdir = os.path.join(os.environ.get("LOCALAPPDATA", ""), "hermes", "skills", "wengu", "scripts")
        if os.path.isdir(sdir) and sdir not in sys.path:
            sys.path.insert(0, sdir)
        try:
            import retrieve as R
            pyout = R.retrieve(QUERY, keywords=[], top=5)
            pyc = [{"cite": r["cite"], "score": r["score"], "text": (r.get("text") or "")[:120]}
                   for r in pyout["results"]]
            diffs = []
            if len(pyc) != len(cases):
                diffs.append("条数 Py=%d UI=%d" % (len(pyc), len(cases)))
            for i in range(min(len(pyc), len(cases))):
                if pyc[i]["cite"] != cases[i]["cite"]:
                    diffs.append("第%d条出处 Py=%s UI=%s" % (i + 1, pyc[i]["cite"], cases[i]["cite"]))
                ui_s = float(re.sub(r"[^\d.]", "", cases[i]["score"].split("·")[0]))
                if abs(pyc[i]["score"] - ui_s) > 1e-9:
                    diffs.append("第%d条分数 Py=%s UI=%s" % (i + 1, pyc[i]["score"], ui_s))
                if not pyc[i]["text"][:100].startswith(cases[i]["text"][:60]):
                    diffs.append("第%d条正文不符" % (i + 1))
            rep["live_parity"] = (len(diffs) == 0)
            rep["live_parity_diffs"] = diffs
            rep["py_scores"] = [c["score"] for c in pyc]
        except Exception as e:
            rep["live_parity"] = "未执行: %s" % e

        # 关键资源的线上响应头（确认 .gz 没被二次编码）
        gz = [(u, s, ct) for (u, s, ct) in resp if u.endswith(".json.gz")]
        rep["gz_responses"] = [{"url": u.split("/wengu/")[-1], "status": s, "ctype": ct} for u, s, ct in gz[:4]]
        rep["gz_count"] = len(gz)
        rep["total_requests"] = len(resp)
        bad = [(u.split("/wengu/")[-1], s) for (u, s, ct) in resp if s >= 400]
        rep["http_errors"] = bad[:10]

        pg.screenshot(path=os.path.join(OUT, "live-desktop.png"))

        # 移动端：单独包起来，失败不影响上面已取得的桌面结论
        try:
            import urllib.parse
            ctx2 = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                                  is_mobile=True, has_touch=True)
            pg2 = ctx2.new_page()
            pg2.on("pageerror", lambda e: console.append("mobile pageerror: " + str(e)))
            pg2.goto(LIVE + "?q=" + urllib.parse.quote(QUERY),
                     wait_until="domcontentloaded", timeout=90000)
            pg2.wait_for_selector(".case", timeout=60000)
            pg2.wait_for_timeout(2000)
            rep["mobile_cases"] = pg2.locator(".case").count()
            rep["mobile_overflow"] = pg2.evaluate(
                "document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
            pg2.screenshot(path=os.path.join(OUT, "live-mobile.png"))
        except Exception as e:
            rep["mobile_error"] = str(e)[:200]

        br.close()

    rep["console_errors"] = console[:12]
    rep["error_count"] = len(console)
    rep["failed_count"] = len(failed)
    rep["failed_requests"] = failed[:8]

    print(json.dumps(rep, ensure_ascii=False, indent=2))
    with open(os.path.join(HERE, "verify_live_report.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()