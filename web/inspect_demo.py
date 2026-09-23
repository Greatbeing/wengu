# -*- coding: utf-8 -*-
"""inspect_demo.py — 直接读渲染后的 DOM，不信视觉模型的转述"""
import json
import os
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8777/docs/?q=" + __import__("urllib.parse", fromlist=["quote"]).quote("要不要辞职换个方向")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

JS = r"""
() => {
  const cs = [].slice.call(document.querySelectorAll('.case'));
  return {
    count: cs.length,
    cases: cs.map(c => {
      const tr = c.querySelector('[data-tr]');
      const st = c.querySelector('.case__text');
      return {
        cite: c.querySelector('.case__cite').innerText,
        scoreLine: c.querySelector('.case__score').innerText.replace(/\s+/g, ' '),
        textLen: st.innerText.length,
        textLines: st.innerText.split('\n').length,
        textHead: st.innerText.slice(0, 46),
        tranExists: !!tr,
        tranVisible: tr ? !tr.classList.contains('is-hidden') : null,
        tranHead: tr ? tr.innerText.slice(0, 34) : null,
        reasons: c.querySelector('.case__reasons').innerText.slice(0, 70),
      };
    }),
    trToggleLabel: document.getElementById('trToggle').innerText,
    demoMeta: document.getElementById('demoMeta').innerText,
    scenesTag: [].slice.call(document.querySelectorAll('.scene-tag')).map(e => e.innerText.replace(/\s+/g,' ')),
    coreQ: document.querySelector('.scenes__q') ? document.querySelector('.scenes__q').innerText : null,
  };
}
"""

with sync_playwright() as pw:
    try:
        br = pw.chromium.launch(headless=True)
    except Exception:
        br = pw.chromium.launch(executable_path=EDGE, headless=True)
    pg = br.new_context(viewport={"width": 1440, "height": 900}).new_page()
    pg.goto(URL, wait_until="networkidle", timeout=90000)
    pg.wait_for_timeout(3000)
    print(json.dumps(pg.evaluate(JS), ensure_ascii=False, indent=2))
    br.close()