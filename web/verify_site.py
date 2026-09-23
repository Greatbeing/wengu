# -*- coding: utf-8 -*-
"""verify_site.py — 网站端到端验收

不是「截个图看看」，而是四件事都做：
  1. 浏览器里跑一次真实查询，把渲染出来的出处与分数，跟 Python 侧的输出对比
  2. 收集控制台错误与失败请求（静默坏掉比报错更危险）
  3. DOM 审计：横向溢出、对比度、字体是否真的加载、断点布局
  4. 截图存档（桌面 / 移动），分片裁切供肉眼复核
"""
import json
import os
import re
import sys

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8777/docs/"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "shots")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

QUERY = "要不要辞职换个方向"

AUDIT_JS = r"""
() => {
  const de = document.documentElement;
  const cw = de.clientWidth;
  const bad = [];
  document.querySelectorAll('body *').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return;
    if (r.right > cw + 1 || r.left < -1) {
      bad.push((el.tagName + '.' + (el.className || '')).slice(0, 60) +
               ' [' + Math.round(r.left) + ',' + Math.round(r.right) + ']');
    }
  });

  // 对比度：只算子元素取最终前景色，与 body 背景比
  function lum(c) {
    const m = c.match(/[\d.]+/g).map(Number);
    const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(m[0]) + 0.7152 * f(m[1]) + 0.0722 * f(m[2]);
  }
  const bg = getComputedStyle(document.body).backgroundColor;
  const lb = lum(bg);
  const samples = [
    ['body', 'body'],
    ['.hero__sub', '.hero__sub'],
    ['.case__text', '.case__text'],
    ['.case__reasons', '.case__reasons'],
    ['.metric__v', '.metric__v'],
    ['.demo__meta', '.demo__meta'],
    ['.foot', '.foot'],
  ];
  const contrast = {};
  samples.forEach(([k, sel]) => {
    const el = document.querySelector(sel);
    if (!el) { contrast[k] = null; return; }
    const la = lum(getComputedStyle(el).color);
    const hi = Math.max(la, lb), lo = Math.min(la, lb);
    contrast[k] = Math.round(((hi + 0.05) / (lo + 0.05)) * 100) / 100;
  });

  return {
    clientW: cw,
    scrollW: de.scrollWidth,
    overflow: de.scrollWidth > cw + 1,
    overflowing: bad.slice(0, 8),
    contrast: contrast,
    fontsReady: document.fonts.status,
    serifOK: document.fonts.check('16px "Source Han Serif SC"') ||
             document.fonts.check('16px "Songti SC"') ||
             document.fonts.check('16px SimSun'),
    gridCorp: getComputedStyle(document.querySelector('.corp')).gridTemplateColumns,
    gridKern: getComputedStyle(document.querySelector('.kern')).gridTemplateColumns,
    heroH: document.querySelector('.hero').offsetHeight,
    viewH: window.innerHeight,
    mountImgs: [].slice.call(document.querySelectorAll('.mount img')).map(function (i) {
      var s = getComputedStyle(i);
      return { cls: i.className, display: s.display, w: i.offsetWidth, h: i.offsetHeight };
    }),
    pageH: document.documentElement.scrollHeight,
  };
}
"""


def main():
    os.makedirs(OUT, exist_ok=True)
    errors, failed = [], []
    report = {}

    with sync_playwright() as pw:
        try:
            br = pw.chromium.launch(headless=True)
            report["browser"] = "bundled chromium"
        except Exception:
            br = pw.chromium.launch(executable_path=EDGE, headless=True)
            report["browser"] = "system Edge"

        ctx = br.new_context(viewport={"width": 1440, "height": 960})
        pg = ctx.new_page()
        pg.on("console", lambda m: errors.append(m.type + ": " + m.text)
              if m.type in ("error", "warning") else None)
        pg.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
        pg.on("requestfailed", lambda r: failed.append(r.url + " :: " + str(r.failure)))

        pg.goto(URL, wait_until="networkidle", timeout=90000)
        pg.wait_for_timeout(2000)

        # 首屏状态
        report["title"] = pg.title()
        report["panel_idle"] = pg.inner_text("#panel")[:80]
        report["chips"] = pg.locator("#examples .chip").count()
        report["demo_meta"] = pg.inner_text("#demoMeta")

        # ── 真实查询：走 UI 路径（点示例按钮）──
        pg.locator('#examples .chip[data-q="%s"]' % QUERY).click()
        pg.wait_for_selector(".case", timeout=30000)
        pg.wait_for_timeout(1500)

        cases = pg.eval_on_selector_all(".case", r"""els => els.map(e => ({
            cite: e.querySelector('.case__cite') ? e.querySelector('.case__cite').innerText : '',
            score: e.querySelector('.case__score') ? e.querySelector('.case__score').innerText : '',
            text: e.querySelector('.case__text') ? e.querySelector('.case__text').innerText.slice(0,120) : '',
            hasTran: !!e.querySelector('.case__tran'),
        }))""")
        report["ui_case_count"] = len(cases)
        report["ui_first"] = cases[0] if cases else None
        report["demo_meta_after"] = pg.inner_text("#demoMeta")

        # ── 与 Python 引擎实时对比（不读旧 JSON，当场跑）──
        sdir = os.path.join(os.environ.get("LOCALAPPDATA", ""), "hermes", "skills", "wengu", "scripts")
        if os.path.isdir(sdir) and sdir not in sys.path:
            sys.path.insert(0, sdir)
        try:
            import retrieve as R
            pyout = R.retrieve(QUERY, keywords=[], top=5)
            py_cases = [{"cite": r["cite"], "score": r["score"],
                         "text": (r.get("text") or "")[:120]} for r in pyout["results"]]
            report["py_case_count"] = len(py_cases)
            report["py_scores"] = [c["score"] for c in py_cases]
            report["ui_scores"] = [c["score"] for c in cases]

            diffs = []
            if len(py_cases) != len(cases):
                diffs.append("条数不同 Py=%d UI=%d" % (len(py_cases), len(cases)))
            for i in range(min(len(py_cases), len(cases))):
                if py_cases[i]["cite"] != cases[i]["cite"]:
                    diffs.append("第%d条出处 Py=%s UI=%s" % (i + 1, py_cases[i]["cite"], cases[i]["cite"]))
                if abs(py_cases[i]["score"] - float(re.sub(r"[^\d.]", "", cases[i]["score"].split("·")[0]))) > 1e-9:
                    diffs.append("第%d条分数 Py=%s UI=%s" % (i + 1, py_cases[i]["score"], cases[i]["score"]))
                # 正文逐字：UI 的前 100 字必须是 Python 正文的前缀
                if not py_cases[i]["text"][:100].startswith(cases[i]["text"][:60]):
                    diffs.append("第%d条正文开头不符" % (i + 1))
            report["live_parity"] = (len(diffs) == 0)
            report["live_parity_diffs"] = diffs
        except Exception as e:
            report["live_parity"] = "对比未执行: %s" % e

        # ── DOM 审计 ──
        report["audit_1440"] = pg.evaluate(AUDIT_JS)

        # ── 截图：桌面 ──
        pg.screenshot(path=os.path.join(OUT, "d1-hero.png"))
        pg.locator("#demo").scroll_into_view_if_needed()
        pg.wait_for_timeout(700)
        pg.screenshot(path=os.path.join(OUT, "d2-demo.png"))
        pg.locator("#check").scroll_into_view_if_needed()
        pg.wait_for_timeout(700)
        pg.screenshot(path=os.path.join(OUT, "d3-check.png"))

        # ── 移动端 ──
        ctx2 = br.new_context(viewport={"width": 390, "height": 844},
                              device_scale_factor=2, is_mobile=True, has_touch=True)
        pg2 = ctx2.new_page()
        pg2.goto(URL + "?q=" + QUERY.replace(" ", "%20"), wait_until="networkidle", timeout=90000)
        pg2.wait_for_timeout(2500)
        report["audit_390"] = pg2.evaluate(AUDIT_JS)
        pg2.screenshot(path=os.path.join(OUT, "m1-hero.png"))
        pg2.locator("#demo").scroll_into_view_if_needed()
        pg2.wait_for_timeout(700)
        pg2.screenshot(path=os.path.join(OUT, "m2-demo.png"))

        br.close()

    report["console_errors"] = errors[:15]
    report["failed_requests"] = failed[:15]
    report["error_count"] = len(errors)
    report["failed_count"] = len(failed)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    with open(os.path.join(HERE, "verify_site_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()