# -*- coding: utf-8 -*-
"""dump_python_results.py — 用真 Python 引擎跑测评集，导出结果供对拍

配套 web/verify_engine.js 使用：两边跑同一批问句，逐条比对
（场景、score、quality、cite），不一致就报出来，不靠肉眼判断。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SKILL_SCRIPTS = os.path.join(
    os.environ.get("LOCALAPPDATA", ""), "hermes", "skills", "wengu", "scripts")
if not os.path.isdir(SKILL_SCRIPTS):
    SKILL_SCRIPTS = os.path.join(REPO, "scripts")
sys.path.insert(0, SKILL_SCRIPTS)

import retrieve as R  # noqa: E402
import deduce as D     # noqa: E402


def main():
    ev = os.path.join(SKILL_SCRIPTS, "eval_queries.json")
    with open(ev, encoding="utf-8") as f:
        items = json.load(f)
    queries = []
    for it in items:
        q = it[0] if isinstance(it, (list, tuple)) else (it.get("query") if isinstance(it, dict) else it)
        if isinstance(q, str) and q.strip():
            queries.append(q)

    # cite → 事件，用于回查未舍入的原始分（舍入会掩盖真实差异）
    idx = R.load_index()
    by_cite = {}
    for i, e in enumerate(idx["events"]):
        by_cite.setdefault(e["cite"], []).append(i)

    out = {}
    for q in queries:
        res = R.retrieve(q, keywords=[], top=5)
        # matched_scenes 只透出 id/name/hits，不含权重；
        # 直接调 match_scenes 取原始 (score, id, hits) 三元组，才能逐值对拍。
        raw_matched = R.match_scenes(q)
        scene_map = {s["id"]: s for s in R.SCENES}
        idf = idx.get("idf") or {}
        rows = []
        for r in res["results"]:
            raw_sc = None
            nprop = None
            for i in by_cite.get(r["cite"], []):
                e = idx["events"][i]
                if e["text"][:40] == r["text"][:40]:
                    sc, _ = R.score_unit(e, scene_map[r["scene"]], [], idf)
                    raw_sc = sc
                    span, _a = D.focus_span(e["text"], scene_map[r["scene"]])
                    nprop = sum(1 for c in D.extract_choices(span) if c["kind"] == "propose")
                    break
            rows.append({
                "scene": r["scene"], "score": r["score"], "quality": r["quality"],
                "cite": r["cite"], "raw_sc": raw_sc, "nprop": nprop,
            })
        out[q] = {
            "matched": [{"id": m[1], "score": m[0]} for m in raw_matched[:3]],
            "results": rows,
        }

    dst = os.path.join(HERE, "python_results.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("已导出 %d 条问句 → %s" % (len(out), dst))


if __name__ == "__main__":
    main()
