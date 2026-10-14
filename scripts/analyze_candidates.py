# -*- coding: utf-8 -*-
"""analyze_candidates.py — 量化每个古典词对候选集的边际贡献

背景：candidate_indices() 取该场景全部古典词的命中并集。单字泛词
（利/害/时/机/家/门/战/救…）在史书里遍地都是，一个词就能捞进几千条，
使候选集形同虚设（risk-return 召回 81.5%），精确率全靠打分兜底。

本脚本回答「删掉某个词要付什么代价」：

  覆盖数    该词单独命中多少事件
  独占数    只被**这一个词**捞到的事件数 —— 删它，这些就永久出局
  独占占比  独占数 / 该场景候选总数
  该词IDF   越低越泛（1.0 表示在几乎全部事件里出现）

判据：覆盖大 且 独占占比低 → 可安全降级为「仅计分、不入选」。
"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scenes import SCENES, CANDIDATE_DF_MAX  # noqa: E402
import retrieve as R  # noqa: E402
from retrieve import load_index  # noqa: E402


def main():
    index = load_index()
    inv = index["inverted"]
    idf = index.get("idf") or {}
    n_events = len(index["events"])

    print("语料 %d 个事件单元\n" % n_events)
    print("%-18s %7s %7s %6s %7s %6s  %s"
          % ("内核", "原始池", "召回率", "词数", "生效池", "降级", "占用最重的泛词（覆盖/独占/独占占比/IDF）"))
    print("-" * 108)

    report = {}
    for s in SCENES:
        sid = s["id"]
        words = s["classical"]
        support = defaultdict(int)   # 每个词覆盖多少事件
        holders = defaultdict(list)  # 每个事件被哪些词捞到

        for w in words:
            for i in inv.get(w, ()):
                support[w] += 1
                holders[i].append(w)

        pool = len(holders)
        sole = defaultdict(int)
        for i, ws in holders.items():
            if len(ws) == 1:
                sole[ws[0]] += 1

        rows = []
        for w in words:
            c = support[w]
            sl = sole[w]
            rows.append((w, c, sl, (sl / pool if pool else 0), idf.get(w, 0.0)))
        rows.sort(key=lambda r: -r[1])

        # 实际生效的候选池（已经过泛词降级）——必须报这个，报原始并集会骗人
        eff = R.candidate_indices(s, index)
        dropped = [w for w in words
                   if len(inv.get(w, ())) >= CANDIDATE_DF_MAX * n_events]

        top = rows[:6]
        desc = "  ".join("%s:%d/%d/%.1f%%/%.2f" % (w, c, sl, frac * 100, w_idf)
                         for w, c, sl, frac, w_idf in top)
        print("%-18s %7d %6.1f%% %6d %7d %6.0f%%  %s"
              % (s["name"], pool, 100.0 * pool / n_events, len(words),
                 len(eff), 100 * (1 - len(eff) / max(1, pool)), desc))
        report[sid] = {
            "name": s["name"], "pool": pool, "words": len(words),
            "effective": len(eff),
            "dropped": dropped,
            "rows": [{"w": w, "cover": c, "sole": sl, "frac": frac, "idf": w_idf}
                     for w, c, sl, frac, w_idf in rows],
        }

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                       "web", "candidate_report.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    print("\n明细已写入 %s" % os.path.abspath(out))

    # 全局：跨内核重复出现的泛词
    print("\n=== 跨内核出现的同一个词（说明它是通用词，不是内核信号）===")
    where = defaultdict(list)
    for s in SCENES:
        for w in s["classical"]:
            where[w].append(s["id"])
    multi = [(w, ids) for w, ids in where.items() if len(ids) > 1]
    multi.sort(key=lambda x: -len(x[1]))
    for w, ids in multi[:12]:
        print("  %-6s 出现在 %d 个内核: %s" % (w, len(ids), "、".join(ids)))


if __name__ == "__main__":
    main()