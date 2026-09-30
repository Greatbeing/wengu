# -*- coding: utf-8 -*-
"""diagnose_live2.py — 线上逐请求计时 + 控制台事件 + 面板状态

不做判断，只采集事实：
  * 每个请求的 发起时刻 / 耗时 / 状态 / 传输字节
  * 所有 console 输出与 requestfailed
  * 检索后面板的真实文本（是报错、是载入中、还是出了结果）
"""
import json
import time

from playwright.sync_api import sync_playwright

URL = "https://greatbeing.github.io/wengu/"
QUERY = "要不要辞职换个方向"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

t0 = time.time()
events = []
msgs = []

with sync_playwright() as pw:
    try:
        br = pw.chromium.launch(headless=True)
    except Exception:
        br = pw.chromium.launch(executable_path=EDGE, headless=True)
    ctx = br.new_context(viewport={"width": 1440, "height": 960})
    pg = ctx.new_page()

    pg.on("console", lambda m: msgs.append("[%s] %s" % (m.type, m.text[:200])))
    pg.on("pageerror", lambda e: msgs.append("[pageerror] %s" % str(e)[:300]))

    inflight = {}

    def on_req(r):
        inflight[r] = time.time() - t0

    def on_resp(r):
        dt = time.time() - t0
        start = inflight.pop(r, None)
        try:
            body_len = r.header_value("content-length") or ""
        except Exception:
            body_len = ""
        if r.url.startswith(URL):
            events.append({
                "url": r.url.replace(URL, ""),
                "start": round(start, 2) if start else None,
                "end": round(dt, 2),
                "dur": round(dt - start, 2) if start else None,
                "status": r.status,
                "bytes": body_len,
            })

    pg.on("request", on_req)
    pg.on("response", on_resp)
    pg.on("requestfailed", lambda r: msgs.append(
        "[requestfailed] %s :: %s" % (r.url.replace(URL, ""), r.failure)))

    pg.goto(URL, wait_until="domcontentloaded", timeout=120000)
    print("domcontentloaded @ %.2fs" % (time.time() - t0))

    try:
        pg.wait_for_selector("#examples .chip", timeout=120000)
        print("示例按钮出现 @ %.2fs（可交互）" % (time.time() - t0))
    except Exception as e:
        print("示例按钮未出现 @ %.2fs  %s" % (time.time() - t0, str(e)[:80]))

    # 点一个示例 chip（走真实用户路径，比 fill+submit 更接近实际）
    try:
        pg.query_selector("#examples .chip").click()
        print("已点击第一个示例 @ %.2fs" % (time.time() - t0))
    except Exception as e:
        print("点击失败:", str(e)[:120])

    try:
        pg.wait_for_selector(".case", timeout=150000)
        print(".case 出现 @ %.2fs" % (time.time() - t0))
    except Exception:
        print(".case 未出现（等了 150s）")

    pg.wait_for_timeout(1500)

    state = pg.evaluate("""() => {
      const meta = document.querySelector('#demoMeta');
      const panel = document.querySelector('#demoPanel');
      return {
        metaText: meta ? meta.textContent.trim() : null,
        panelText: panel ? panel.textContent.replace(/\\s+/g,' ').trim().slice(0, 300) : null,
        caseCount: document.querySelectorAll('.case').length,
        chipCount: document.querySelectorAll('#examples .chip').length,
        inputVal: (document.querySelector('#askInput')||{}).value,
        hash: location.search,
      };
    }""")

    print("\n=== 面板状态 ===")
    print(json.dumps(state, ensure_ascii=False, indent=2))

    print("\n=== 请求明细（按发起时刻）===")
    tot = 0
    for e in sorted([x for x in events if x["start"] is not None], key=lambda x: x["start"]):
        b = int(e["bytes"]) if str(e["bytes"]).isdigit() else 0
        tot += b
        print("  %7.2fs → %7.2fs  %6.2fs  %3s  %9s  %s"
              % (e["start"], e["end"], e["dur"] or -1, e["status"],
                 ("%.1fKB" % (b / 1024)) if b else "?", e["url"]))
    print("  传输合计: %.1f KB" % (tot / 1024))

    slow = sorted([x for x in events if x["start"] is not None and (x["dur"] or 0) > 3],
                  key=lambda x: -(x["dur"] or 0))[:8]
    print("\n=== 最慢的请求 ===")
    for e in slow:
        print("  %6.2fs  %3s  %s" % (e["dur"], e["status"], e["url"]))

    print("\n=== 控制台 / 失败 ===")
    for m in msgs[:20]:
        print("  " + m)
    if not msgs:
        print("  （无）")

    print("\n总耗时 %.1fs" % (time.time() - t0))
    br.close()