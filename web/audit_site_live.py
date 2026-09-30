# -*- coding: utf-8 -*-
"""audit_site_live.py — 线上站点功能审计

不只验「打得开」，而是逐项走真实用户路径并记录数据成本：
  A 静息态文案
  B 输入检索（对照 Python 引擎）
  C 按内核浏览 —— 重点：实测它到底要下多少分片（候选集横跨 64 片，但展示只取前 5）
  D 无命中时的出路
  E 深链接 ?q=
  F 深色模式
  G 移动端溢出
  H 控制台 / 失败请求
"""
import json
import time

from playwright.sync_api import sync_playwright

LIVE = "https://greatbeing.github.io/wengu/"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
QUERY = "要不要辞职换个方向"

t0 = time.time()
REQ = []
CONSOLE = []
FAILED = []


def main():
    with sync_playwright() as pw:
        try:
            br = pw.chromium.launch(headless=True)
        except Exception:
            br = pw.chromium.launch(executable_path=EDGE, headless=True)
        ctx = br.new_context(viewport={"width": 1440, "height": 960})
        ctx.grant_permissions(["clipboard-read", "clipboard-write"])
        pg = ctx.new_page()

        pg.on("console", lambda m: CONSOLE.append("[%s] %s" % (m.type, m.text[:200])))
        pg.on("pageerror", lambda e: CONSOLE.append("[pageerror] %s" % str(e)[:250]))
        pg.on("requestfailed", lambda r: FAILED.append(r.url.replace(LIVE, "")))

        def on_resp(r):
            if not r.url.startswith(LIVE):
                return
            try:
                cl = int(r.header_value("content-length") or 0)
            except Exception:
                cl = 0
            REQ.append({"url": r.url.replace(LIVE, ""), "status": r.status,
                        "bytes": cl, "t": round(time.time() - t0, 2)})

        pg.on("response", on_resp)

        def mark():
            return len(REQ)

        def since(n):
            sub = REQ[n:]
            return len(sub), sum(x["bytes"] for x in sub)

        out = {}

        # ── 载入 ──
        pg.goto(LIVE, wait_until="domcontentloaded", timeout=120000)
        pg.wait_for_selector("#examples .chip", timeout=120000)
        pg.wait_for_function("() => document.querySelector('#demoMeta').textContent.indexOf('51/51') >= 0",
                             timeout=180000)
        n, b = since(0)
        out["A_首屏"] = {"请求数": n, "下载KB": round(b / 1024, 1),
                         "静息态": pg.eval_on_selector("#panel", "e=>e.textContent.replace(/\\s+/g,' ').trim().slice(0,60)"),
                         "示例数": pg.eval_on_selector_all("#examples .chip", "e=>e.length")}

        # ── B 输入检索 ──
        m0 = mark()
        pg.fill("#askInput", QUERY)
        pg.keyboard.press("Enter")
        pg.wait_for_selector(".case", timeout=120000)
        pg.wait_for_timeout(800)
        n, b = since(m0)
        out["B_检索"] = {
            "案例数": pg.eval_on_selector_all(".case", "e=>e.length"),
            "面板": pg.eval_on_selector("#demoMeta", "e=>e.textContent.trim()"),
            "请求数": n, "下载KB": round(b / 1024, 1),
            "分片": sorted({x["url"] for x in REQ[m0:] if "shards/" in x["url"]}),
            "白话可见": pg.eval_on_selector_all(".case__tran", "e=>e.filter(x=>x.offsetParent!==null).length"),
            "URL": pg.url.split("?")[-1][:60],
        }

        # ── C 按内核浏览（逐个点，记录每次的下载量）──
        pg.eval_on_selector('[data-act="kernels"]', "e=>e.click()") if pg.query_selector('[data-act="kernels"]') else None
        pg.wait_for_timeout(500)
        kb_btns = pg.query_selector_all("[data-scene]")
        out["C_内核"] = {"按钮数": len(kb_btns), "逐个": []}
        for i, btn in enumerate(kb_btns):
            sid = btn.get_attribute("data-scene")
            m0 = mark()
            try:
                btn.click()
                pg.wait_for_selector(".case", timeout=90000)
                pg.wait_for_timeout(400)
                n, b = since(m0)
                out["C_内核"]["逐个"].append({
                    "scene": sid,
                    "案例": pg.eval_on_selector_all(".case", "e=>e.length"),
                    "新请求": n, "新增KB": round(b / 1024, 1),
                    "新分片": len({x["url"] for x in REQ[m0:] if "shards/" in x["url"]}),
                })
            except Exception as e:
                out["C_内核"]["逐个"].append({"scene": sid, "错误": str(e)[:60]})
            # 回到内核列表
            if pg.query_selector('[data-act="kernels"]'):
                pg.eval_on_selector('[data-act="kernels"]', "e=>e.click()")
                pg.wait_for_timeout(300)
            kb_btns = pg.query_selector_all("[data-scene]")

        # ── D 无命中 ──
        m0 = mark()
        pg.fill("#askInput", "zzzzqqqq")
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(2500)
        out["D_无命中"] = {
            "面板": pg.eval_on_selector("#panel", "e=>e.textContent.replace(/\\s+/g,' ').trim().slice(0,90)"),
            "有出路按钮": bool(pg.query_selector("#panel [data-act='kernels']")),
        }

        # ── E 深链接 ──
        pg.goto(LIVE + "?q=" + QUERY, wait_until="domcontentloaded", timeout=120000)
        try:
            pg.wait_for_selector(".case", timeout=180000)
            out["E_深链接"] = {"自动出结果": True,
                               "案例数": pg.eval_on_selector_all(".case", "e=>e.length"),
                               "输入框已回填": pg.eval_on_selector("#askInput", "e=>e.value")}
        except Exception as e:
            out["E_深链接"] = {"自动出结果": False, "错误": str(e)[:80]}

        # ── F 深色 ──
        pg.eval_on_selector("#themeBtn", "e=>e.click()")
        pg.wait_for_timeout(600)
        out["F_深色"] = pg.evaluate("""() => {
          const cs = getComputedStyle(document.documentElement);
          return {theme: document.documentElement.getAttribute('data-theme'),
                  paper: cs.getPropertyValue('--paper').trim(),
                  lineInput: cs.getPropertyValue('--line-input').trim(),
                  stored: (()=>{try{return localStorage.getItem('wengu.theme')}catch(e){return null}})()};
        }""")

        # ── G 移动端 ──
        mp = ctx.new_page()
        mp.set_viewport_size({"width": 390, "height": 844})
        mp.goto(LIVE, wait_until="domcontentloaded", timeout=120000)
        mp.wait_for_function("() => document.querySelector('#demoMeta').textContent.indexOf('51/51') >= 0",
                             timeout=180000)
        out["G_移动"] = mp.evaluate("""() => ({
          overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
          scrollW: document.documentElement.scrollWidth,
          clientW: document.documentElement.clientWidth,
          heroH: Math.round(document.querySelector('.hero').getBoundingClientRect().height),
        })""")

        # ── H ──
        out["H_健康"] = {"控制台错误": [c for c in CONSOLE if "error" in c.lower()][:5],
                         "失败请求": FAILED[:5],
                         "HTTP非200": [x["url"] for x in REQ if x["status"] >= 400][:5]}

        print(json.dumps(out, ensure_ascii=False, indent=2))
        print("\n总请求 %d 个，总下载 %.1f KB" % (len(REQ), sum(x["bytes"] for x in REQ) / 1024))
        print("总耗时 %.1fs" % (time.time() - t0))
        br.close()


main()