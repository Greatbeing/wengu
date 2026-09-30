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
import sys
import time

from playwright.sync_api import sync_playwright

# 默认验线上；也可传本地地址快速自测本脚本：
#   python audit_site_live.py http://127.0.0.1:8777/docs/
LIVE = sys.argv[1] if len(sys.argv) > 1 else "https://greatbeing.github.io/wengu/"
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
            """返回 (请求数, 分片字节, 其他字节)。

            分片是按需拉取、会随查询变化的量；其余（manifest/scenes/meta）是缓存里的
            固定量。混在一起会把每次内核浏览的成本算高一倍以上。
            """
            sub = REQ[n:]
            sb = sum(x["bytes"] for x in sub if "shards/" in x["url"])
            ob = sum(x["bytes"] for x in sub if "shards/" not in x["url"])
            return len(sub), sb, ob

        out = {}

        # ── 载入 ──
        pg.goto(LIVE, wait_until="domcontentloaded", timeout=120000)
        pg.wait_for_selector("#examples .chip", timeout=120000)
        pg.wait_for_function("() => document.querySelector('#demoMeta').textContent.indexOf('51/51') >= 0",
                             timeout=180000)
        n, b, ob = since(0)
        out["A_首屏"] = {"请求数": n, "分片KB": round(b / 1024, 1), "其他KB": round(ob / 1024, 1),
                         "静息态": pg.eval_on_selector("#panel", "e=>e.textContent.replace(/\\s+/g,' ').trim().slice(0,60)"),
                         "示例数": pg.eval_on_selector_all("#examples .chip", "e=>e.length")}

        # ── B 输入检索 ──
        m0 = mark()
        pg.fill("#askInput", QUERY)
        pg.keyboard.press("Enter")
        pg.wait_for_selector(".case", timeout=120000)
        pg.wait_for_timeout(800)
        n, b, ob = since(m0)
        out["B_检索"] = {
            "案例数": pg.eval_on_selector_all(".case", "e=>e.length"),
            "面板": pg.eval_on_selector("#demoMeta", "e=>e.textContent.trim()"),
            "请求数": n, "按需分片KB": round(b / 1024, 1), "缓存量KB": round(ob / 1024, 1),
            "分片": sorted({x["url"] for x in REQ[m0:] if "shards/" in x["url"]}),
            "白话可见": pg.eval_on_selector_all(".case__tran", "e=>e.filter(x=>x.offsetParent!==null).length"),
            "URL": pg.url.split("?")[-1][:60],
        }

        # ── C 按内核浏览 ──
        # 内核入口只在静息态/无命中态出现（结果态没有）。所以先造一个无命中态把 13 个内核 id 取出来，
        # 再逐个走 ?s=<内核> 深链接——顺带把「深链接按内核」这条路径也一起测了。
        pg.fill("#askInput", "zzzzqqqq")
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(2200)
        pg.eval_on_selector('[data-act="kernels"]', "e=>e.click()")
        pg.wait_for_timeout(600)
        sids = [b.get_attribute("data-scene") for b in pg.query_selector_all("[data-scene]")]
        out["C_内核"] = {"内核数": len(sids), "逐个": []}
        for sid in sids:
            m0 = mark()
            try:
                pg.goto(LIVE + "?s=" + sid, wait_until="domcontentloaded", timeout=120000)
                pg.wait_for_selector(".case", timeout=90000)
                pg.wait_for_timeout(400)
                n, b, ob = since(m0)
                out["C_内核"]["逐个"].append({
                    "scene": sid,
                    "案例": pg.eval_on_selector_all(".case", "e=>e.length"),
                    "新请求": n, "按需分片KB": round(b / 1024, 1),
                    "新分片": len({x["url"] for x in REQ[m0:] if "shards/" in x["url"]}),
                })
            except Exception as e:
                out["C_内核"]["逐个"].append({"scene": sid, "错误": str(e)[:70]})

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