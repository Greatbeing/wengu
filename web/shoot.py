# -*- coding: utf-8 -*-
"""shoot.py — 按区块精确取图（verify_site.py 的取图顺序有误，截图前会被 smooth scroll 带偏）

要点：先关掉 smooth scroll，再用 scrollTo 精确定位，每张截图前等一帧。
"""
import os
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8777/docs/"
# 带上问句：既让演示区有真结果可看，也顺带验证 ?q= 深链接
URL_Q = URL + "?q=" + __import__("urllib.parse", fromlist=["quote"]).quote("要不要辞职换个方向")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "shots")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

SECTIONS = ["#demo", "#how", "#kern", "#corpus", "#check", "#use"]


def shoot(pg, prefix):
    # 关掉平滑滚动，否则定位与截图不同步
    pg.evaluate("document.documentElement.style.scrollBehavior='auto'")
    pg.wait_for_timeout(300)
    pg.evaluate("window.scrollTo(0,0)")
    pg.wait_for_timeout(500)
    pg.screenshot(path=os.path.join(OUT, prefix + "0-hero.png"))
    for i, sel in enumerate(SECTIONS, 1):
        pg.evaluate("""(sel)=>{const e=document.querySelector(sel);
            window.scrollTo(0, e.getBoundingClientRect().top + window.scrollY - 70);}""", sel)
        pg.wait_for_timeout(600)
        pg.screenshot(path=os.path.join(OUT, "%s%d-%s.png" % (prefix, i, sel[1:])))
        print("  ok", prefix + sel)


def main():
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as pw:
        try:
            br = pw.chromium.launch(headless=True)
        except Exception:
            br = pw.chromium.launch(executable_path=EDGE, headless=True)

        ctx = br.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()
        pg.goto(URL_Q, wait_until="networkidle", timeout=90000)
        pg.wait_for_timeout(2500)
        print("[桌面 1440]")
        shoot(pg, "x")

        ctx2 = br.new_context(viewport={"width": 390, "height": 844},
                              device_scale_factor=2, is_mobile=True, has_touch=True)
        pg2 = ctx2.new_page()
        pg2.goto(URL_Q, wait_until="networkidle", timeout=90000)
        pg2.wait_for_timeout(2500)
        print("[移动 390]")
        shoot(pg2, "y")

        br.close()
    print("Done ->", OUT)


if __name__ == "__main__":
    main()