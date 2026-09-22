# -*- coding: utf-8 -*-
"""
build_index.py — 预建检索索引 + IDF 表

产出 corpus/index.json：
  events    事件单元
  inverted  {词: [事件下标]}  倒排索引
  idf       {词: 权重}        逆文档频率（优化 P0-1）
  stats     统计

为什么必须算 IDF：
  语料里「利」「害」各命中 5000+ 单元，而「乞骸骨」只命中几十个。
  若同权，泛词会主导打分，精确率完全靠公式兜底。
  IDF 让稀有词说话、让泛词闭嘴——这是精确率的最大杠杆。

用法：python build_index.py
"""
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from retrieve import load_event_units, EVIDENCE, CONSEQUENCE  # noqa: E402
from scenes import SCENES  # noqa: E402
from corpus_path import resolve_corpus  # noqa: E402

CORPUS = resolve_corpus()
OUT = os.path.join(CORPUS, "index.json")


def scoring_words():
    """参与打分的全部词类——索引与 IDF 必须覆盖它们，否则回退默认权重"""
    ws = set(EVIDENCE) | set(CONSEQUENCE)
    for s in SCENES:
        ws |= set(s["classical"])
    return sorted(ws)


def main():
    t0 = time.time()
    print("[1/4] 构建事件单元 ...")
    events = load_event_units()
    N = len(events)
    print("      事件单元: %d (%.1fs)" % (N, time.time() - t0))

    words = scoring_words()
    print("[2/4] 建倒排索引 + IDF（%d 个打分词）..." % len(words))
    inv = {w: [] for w in words}
    df = {}
    for i, e in enumerate(events):
        text = e["text"]
        for w in words:
            if w in text:
                inv[w].append(i)
                df[w] = df.get(w, 0) + 1
    inv = {w: v for w, v in inv.items() if v}
    print("      命中的索引词: %d" % len(inv))

    # IDF = log((N+1)/(df+1)) + 1：df 越大权重越低，最低不小于 1（不出负权重）
    idf = {w: round(math.log((N + 1.0) / (df.get(w, 0) + 1.0)) + 1.0, 4)
           for w in words}

    hi = sorted(((v, k) for k, v in idf.items()), reverse=True)[:6]
    lo = sorted(((v, k) for k, v in idf.items()))[:6]
    print("      最稀有(高权): %s" % ", ".join("%s=%.1f" % (k, v) for v, k in hi))
    print("      最泛(低权)  : %s" % ", ".join("%s=%.1f" % (k, v) for v, k in lo))

    print("[3/4] 写盘 ...")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"events": events, "inverted": inv, "idf": idf,
                   "stats": {"n_events": N, "n_terms": len(inv),
                             "built_from": "zztj_units.jsonl + shiji_units.jsonl + zuozhuan_units.jsonl",
                             "idf_method": "log((N+1)/(df+1))+1"}},
                  f, ensure_ascii=False)
    sz = os.path.getsize(OUT) / 1024.0 / 1024.0
    print("      %s (%.1f MB)" % (OUT, sz))
    print("[4/4] 总耗时 %.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()