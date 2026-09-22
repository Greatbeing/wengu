# -*- coding: utf-8 -*-
"""
derive_patterns.py — 从语料导出每个内核的结构统计（优化 P0-2）

背景（为什么要做这个）：
  旧版「规律启发」是写死在 tuiliyan.PATTERNS 里的格言，却对外宣称
  「史书上反复出现的结构性倾向」——这是未经测量的断言，属于伪定制。
  本脚本把规律改为**可复现的语料统计**：每个内核取 top-K 案例，
  统计进言被采纳/被拒的比例、并列选项比例、代价类型分布，
  每条结论都附「n 例中的多少例」与实际出处，可被独立复核。

产出：corpus/patterns.json

用法：python derive_patterns.py
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import deduce  # noqa: E402
from retrieve import retrieve  # noqa: E402
from scenes import SCENES  # noqa: E402
from corpus_path import resolve_corpus  # noqa: E402

CORPUS = resolve_corpus()
OUT = os.path.join(CORPUS, "patterns.json")
K = 40          # 每内核取前 K 个案例做统计
MIN_Q = 3.0     # 案例质量下限


def stats_for_scene(scene):
    res = retrieve("", scene_ids=[scene["id"]], top=K, min_score=MIN_Q)["results"]
    n = 0
    debate = 0
    rej = acc = hes = unk = 0
    costs = {}
    n_prop_sum = 0
    samples = []
    for r in res:
        span, _ = deduce.focus_span(r["text"], scene)
        ch = deduce.extract_choices(span)
        n_prop = sum(1 for c in ch if c["kind"] == "propose")
        d = deduce.detect_decision(span)
        cs = deduce.analyze_costs(span)
        n += 1
        n_prop_sum += n_prop
        if n_prop >= 2:
            debate += 1
        if "拒绝" in d:
            rej += 1
        elif "采纳" in d:
            acc += 1
        elif "犹豫" in d:
            hes += 1
        else:
            unk += 1
        for cat in cs:
            costs[cat] = costs.get(cat, 0) + 1
            # 抽样出处要求：类别未抽过，且该出处未出现过。
            # 注意必须对「实时」samples 判断——若在循环外缓存 cites，
            # 同一个案例会因多个代价类别被重复抽中（已踩过）。
            if (cat not in {s[0] for s in samples}
                    and r["cite"] not in {s[1] for s in samples}):
                samples.append((cat, r["cite"], r["text"][:60]))
    if n == 0:
        return None
    return {
        "n_cases": n,
        "avg_proposals": round(n_prop_sum / n, 2),
        "debate_rate": round(100.0 * debate / n, 1),
        "rejected_rate": round(100.0 * rej / n, 1),
        "accepted_rate": round(100.0 * acc / n, 1),
        "hesitate_rate": round(100.0 * hes / n, 1),
        "unrecorded_rate": round(100.0 * unk / n, 1),
        "cost_dist": dict(sorted(costs.items(), key=lambda kv: -kv[1])),
        "sample_cites": [{"cost": c, "cite": ct, "text": tx}
                         for c, ct, tx in samples[:3]],
    }


def main():
    out = {}
    for s in SCENES:
        st = stats_for_scene(s)
        if not st:
            continue
        out[s["id"]] = st
        print("### %s（%s）n=%d" % (s["name"], s["id"], st["n_cases"]))
        print("    平均并列选项 %.2f ｜ 有多方案争执 %.1f%%"
              % (st["avg_proposals"], st["debate_rate"]))
        print("    进言被拒 %.1f%% ｜ 被采纳 %.1f%% ｜ 犹豫 %.1f%% ｜ 未载 %.1f%%"
              % (st["rejected_rate"], st["accepted_rate"],
                 st["hesitate_rate"], st["unrecorded_rate"]))
        print("    代价分布: %s" % st["cost_dist"])
        print()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"k": K, "min_quality": MIN_Q, "scenes": out,
                   "note": "统计对象为《资治通鉴》《史记》《左传》语料库中的事件单元，"
                           "非对历史总体的推断；样本偏向上层政治军事决策。"},
                  f, ensure_ascii=False, indent=2)
    print("已写入 %s" % OUT)


if __name__ == "__main__":
    main()