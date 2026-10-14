# -*- coding: utf-8 -*-
"""simulate_demotion.py — 候选降级的对照实验

规则（先定后测，不事后调参）：
    古典词若 df/N ≥ 阈值，则不再具备预筛资格 —— 降级为「只计分、不入选」。
    打分环节完全不动（词仍参与匹配，IDF 照常加权），只改 candidate_indices() 的取词范围。

本脚本对若干阈值各跑一遍 51 条评测问法，与基线逐条对比：
    · 候选池收缩多少
    · 有多少问法的 top-5 集合变了、top-1 变了
    · 丢掉的案例长什么样（要人看：是噪声还是真信号）
    · C4 检索一致性（首位案例内核 ⊆ 识别前二内核）是否退化
"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import retrieve as R  # noqa: E402
from scenes import SCENES  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
THRESHOLDS = [0.00, 0.10, 0.15, 0.20, 0.25, 0.30]


def make_patched(threshold, index):
    """返回一个按阈值过滤取词的 candidate_indices"""
    n = len(index["events"])
    inv = index["inverted"]
    df = {w: len(inv.get(w, ())) for s in SCENES for w in s["classical"]}

    def patched(scene, _index):
        s = set()
        for w in scene["classical"]:
            if n and df[w] / n >= threshold:
                continue                      # 泛词：只计分，不入选
            for i in inv.get(w, ()):
                s.add(i)
        return sorted(s)
    return patched


def run_set(index, queries, top=5):
    out = {}
    for q, expect in queries:
        res = R.retrieve(q, top=top, min_score=1.0)["results"]
        out[q] = {
            "expect": expect,
            "cites": [r["cite"] for r in res],
            "scores": [r["score"] for r in res],
            "scenes": [r["scene"] for r in res],
        }
    return out


def c4_rate(result, index):
    """首位案例的内核 ⊆ 识别前二内核"""
    ok = 0
    for q, d in result.items():
        matched = R.match_scenes(q)
        top2 = {m[1] for m in matched[:2]}
        if d["scenes"] and d["scenes"][0] in top2:
            ok += 1
    return ok, len(result)


def main():
    index = R.load_index()
    with open(os.path.join(HERE, "eval_queries.json"), encoding="utf-8") as fh:
        queries = json.load(fh)
    n = len(index["events"])
    original = R.candidate_indices

    print("评测问法 %d 条，语料 %d 单元\n" % (len(queries), n))

    # 基线
    R.candidate_indices = original
    base = run_set(index, queries)
    base_c4, tot = c4_rate(base, index)
    pools_base = {s["id"]: len(original(s, index)) for s in SCENES}

    print("%-8s %10s %10s %9s %9s %9s  %s"
          % ("阈值", "池总规模", "池收缩", "top1变", "top5变", "C4", "各内核召回率"))
    print("-" * 118)
    print("%-8s %10d %9s%% %9s %9s %7.1f%%  %s"
          % ("基线", sum(pools_base.values()), "-", "-", "-", 100.0 * base_c4 / tot,
             " ".join("%.0f%%" % (100.0 * pools_base[s['id']] / n) for s in SCENES)))

    results = {}
    for th in THRESHOLDS:
        if th == 0.0:
            continue
        R.candidate_indices = make_patched(th, index)
        cur = run_set(index, queries)
        pools = {s["id"]: len(R.candidate_indices(s, index)) for s in SCENES}

        t1 = sum(1 for q in base if base[q]["cites"][:1] != cur[q]["cites"][:1])
        t5 = sum(1 for q in base if set(base[q]["cites"]) != set(cur[q]["cites"]))
        c4, _ = c4_rate(cur, index)

        print("%-8s %10d %8.0f%% %9d %9d %7.1f%%  %s"
              % ("%.0f%%" % (th * 100), sum(pools.values()),
                 100 * (1 - sum(pools.values()) / sum(pools_base.values())),
                 t1, t5, 100.0 * c4 / tot,
                 " ".join("%.0f%%" % (100.0 * pools[s['id']] / n) for s in SCENES)))
        results[th] = {"cur": cur, "pools": pools, "t1": t1, "t5": t5, "c4": c4}

    # 看丢掉的是什么：以 20% 阈值为例
    th = 0.20
    if th in results:
        cur = results[th]["cur"]
        print("\n=== 20% 阈值下：从 top-5 里消失的案例（人眼判断是噪声还是真信号）===")
        lost = []
        for q in base:
            gone = [c for c in base[q]["cites"] if c not in cur[q]["cites"]]
            for g in gone:
                lost.append((q, g))
        print("共消失 %d 条（分布在 %d 条问法上）\n"
              % (len(lost), len({q for q, _ in lost})))
        for q, g in lost[:14]:
            print("  问法: %s" % q)
            print("    消失: %s" % g)
        # 新增的
        added = []
        for q in base:
            new = [c for c in cur[q]["cites"] if c not in base[q]["cites"]]
            for x in new:
                added.append((q, x))
        print("\n新增 %d 条" % len(added))
        for q, x in added[:8]:
            print("  问法: %s" % q)
            print("    新增: %s" % x)

    out = os.path.join(HERE, "..", "web", "demotion_sim.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({
            "thresholds": {str(k): {"t1": v["t1"], "t5": v["t5"], "c4": v["c4"],
                                    "pool_total": sum(v["pools"].values())}
                           for k, v in results.items()},
            "baseline": {"c4": base_c4, "total": tot, "pool_total": sum(pools_base.values())},
        }, fh, ensure_ascii=False, indent=1)
    print("\n结果已写入 %s" % os.path.abspath(out))
    R.candidate_indices = original


if __name__ == "__main__":
    main()