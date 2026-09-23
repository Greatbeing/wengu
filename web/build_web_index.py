# -*- coding: utf-8 -*-
"""
build_web_index.py — 为问古配套网站构建浏览器端索引

设计要点
--------
网页演示要在浏览器里跑**真引擎**（不是假数据、不是预录结果），但语料全量
gzip 后仍有 5～11 MB，不适合首屏加载。因此拆成两层：

  meta.json    只装「打分所需的一切」——把 score_unit 的 8 项里 7 项
               在构建期算成特征向量，浏览器端打分退化为纯算术。
               约数百 KB。（第 4 项「用户关键词」网页版不用：网页主路径是
               「描述处境→场景匹配」，关键词直检属 CLI 功能。）
  shards/*.json 事件正文（原文＋白话），按事件下标分片，按需拉取。
               一次查询通常只命中 1～3 片，约 100～300 KB。

另外把「并列选项数」也在构建期用 deduce 的真实现例算好（n_prop），
避免把 deduce.py 的 460 行移植到 JS —— 少一份实现，就少一份不一致。

用法：
    python build_web_index.py [--out ../../docs/data] [--shards 24]
"""
import argparse
import json
import os
import sys
import re

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

# 复用技能脚本（真引擎），不重写
SKILL_SCRIPTS = os.path.join(
    os.environ.get("LOCALAPPDATA", ""), "hermes", "skills", "wengu", "scripts")
if not os.path.isdir(SKILL_SCRIPTS):
    SKILL_SCRIPTS = os.path.join(REPO, "scripts")
sys.path.insert(0, SKILL_SCRIPTS)

import retrieve as R          # noqa: E402
import deduce as D            # noqa: E402
from scenes import SCENES, STEMS, EXTRA_STEMS, WEAK_STEMS  # noqa: E402


def load_index():
    p = os.path.join(R.CORPUS, "index.json")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def build(outdir, n_shards):
    idx = load_index()
    events = idx["events"]
    idf = idx.get("idf") or {}
    print("[1/5] 载入事件单元 %d 条" % len(events))

    # ── 词表：古典信号词全集（各场景并集），外加证据词、后果词 ──
    cls_vocab, cls_pos = [], {}
    for s in SCENES:
        for w in s["classical"]:
            if w not in cls_pos:
                cls_pos[w] = len(cls_vocab)
                cls_vocab.append(w)

    evd_vocab, evd_pos = [], {}
    for w in R.EVIDENCE:
        if w not in evd_pos:
            evd_pos[w] = len(evd_vocab)
            evd_vocab.append(w)

    cq_vocab, cq_pos = [], {}
    for w in R.CONSEQUENCE:
        if w not in cq_pos:
            cq_pos[w] = len(cq_vocab)
            cq_vocab.append(w)

    print("[2/5] 词表：古典 %d ／ 证据 %d ／ 后果 %d"
          % (len(cls_vocab), len(evd_vocab), len(cq_vocab)))

    # 场景 → 其古典词在词表中的 id 集合（供 JS 求交）
    scene_cls_ids = []
    for s in SCENES:
        scene_cls_ids.append(sorted({cls_pos[w] for w in s["classical"]}))

    # ── 逐事件抽特征（与 score_unit 的 8 项一一对应）──
    rows = []
    for i, e in enumerate(events):
        text = e["text"]
        rows.append([
            e.get("cite", ""),
            e.get("source", ""),
            e.get("time", ""),
            len(text),                                        # 7) 长度
            1 if e.get("translation") else 0,                 # 5) 有白话
            1 if re.search(r"曰[:：\"“」『]", text) else 0,                   # 3) 选项对立
            # 写成字面字符而非 \uXXXX：两者编译结果等价（re 模块会解释 \u 转义，
            # 实测 6707 条语料判定完全一致），但字面写法可直接肉眼核对。
            (1 if re.search(r"(或曰|或谓|或言|人曰|客曰|臣曰|对曰|谏曰|说曰)", text) else 0)
            + (1 if re.search(r"(遂|乃|于是|卒|竟|竟以|以故|由是|其后|已而|无何|顷之|居)", text) else 0),
            1 if re.search(r"(谏|说|对|谋|议|言于|上疏|奏|问)", text) else 0,   # 8) 进言
            1 if re.search(r"(从之|不听|弗听|不用|不纳|许之|纳之|以为然|拒之|不许|善之|怒|乃许|乃从)", text) else 0,
            [cls_pos[w] for w in cls_vocab if w in text],     # 1) 古典信号
            [evd_pos[w] for w in evd_vocab if w in text],     # 2) 抉择证据
            [cq_pos[w] for w in cq_vocab if w in text],       # 6) 后果信息
        ])
        if (i + 1) % 2000 == 0:
            print("      特征 %d/%d" % (i + 1, len(events)))
    print("[3/5] 特征提取完成")

    # ── 预计算并列选项数（用真 deduce，避免移植）──
    nprop = {}
    scene_map = {s["id"]: s for s in SCENES}
    total = 0
    for si, s in enumerate(SCENES):
        cands = R.candidate_indices(s, idx)
        m = {}
        for i in cands:
            if i >= len(events):
                continue
            try:
                span, _ = D.focus_span(events[i]["text"], s)
                ch = D.extract_choices(span)
                m[i] = sum(1 for c in ch if c["kind"] == "propose")
            except Exception:
                continue
        nprop[s["id"]] = m
        total += len(m)
        print("      场景 %-16s 候选 %5d" % (s["id"], len(m)))
    print("[4/5] 并列选项预计算完成（%d 对）" % total)

    # ── 输出 ──
    # 说明：正文以 .json.gz 提交（仓库只增约 11MB，而非 25MB 裸 JSON）。
    # GitHub Pages 对 .gz 不会再压一层，客户端用 DecompressionStream 解压，
    # 因此「仓库体积」与「传输体积」同时最优。
    os.makedirs(outdir, exist_ok=True)
    shard_dir = os.path.join(outdir, "shards")
    os.makedirs(shard_dir, exist_ok=True)

    scenes_out = []
    for k, s in enumerate(SCENES):
        scenes_out.append({
            "id": s["id"], "name": s["name"], "question": s["question"],
            "clsIds": scene_cls_ids[k],
            "modern": list(s["modern"]),
            "stems": list(STEMS.get(s["id"], [])) + list(EXTRA_STEMS.get(s["id"], [])),
            "weak": sorted(WEAK_STEMS.get(s["id"], [])),
        })

    def wjson(path, obj, gz=False):
        data = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if gz:
            import gzip
            with gzip.GzipFile(path, "wb", compresslevel=9, mtime=0) as f:
                f.write(data)
        else:
            with open(path, "wb") as f:
                f.write(data)
        return len(data)

    scenes_p = os.path.join(outdir, "scenes.json")
    wjson(scenes_p, {"scenes": scenes_out, "idf": idf})

    meta = {
        "n": len(events),
        "shards": n_shards,
        "clsVocab": cls_vocab,
        "evdVocab": evd_vocab,
        "cqVocab": cq_vocab,
        "evdIdf": {w: idf.get(w, 1.0) for w in evd_vocab},
        "cqIdf": {w: idf.get(w, 1.0) for w in cq_vocab},
        "clsIdf": {w: idf.get(w, 1.0) for w in cls_vocab},
        "nprop": nprop,
        "events": rows,
    }
    meta_p = os.path.join(outdir, "meta.json.gz")
    wjson(meta_p, meta, gz=True)

    size = len(events)
    per = (size + n_shards - 1) // n_shards
    for si in range(n_shards):
        lo, hi = si * per, min(size, (si + 1) * per)
        items = [[events[i]["text"], events[i].get("translation", "") or ""]
                 for i in range(lo, hi)]
        wjson(os.path.join(shard_dir, "shard-%03d.json.gz" % si),
              {"start": lo, "items": items}, gz=True)

    wjson(os.path.join(outdir, "manifest.json"), {
        "n": size, "shards": n_shards, "perShard": per,
        "meta": "data/meta.json.gz", "scenes": "data/scenes.json",
        "shardPattern": "data/shards/shard-%03d.json.gz",
    })

    print("[5/5] 输出完成")
    for p in (scenes_p, meta_p):
        print("      %-24s %8.1f KB (原始)" % (os.path.basename(p), os.path.getsize(p) / 1024))
    tot = sum(os.path.getsize(os.path.join(shard_dir, x)) for x in os.listdir(shard_dir))
    print("      %-24s %8.1f KB (%d 片)" % ("shards/", tot / 1024, n_shards))
    return {"events": size, "shards": n_shards}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(REPO, "docs", "data"))
    ap.add_argument("--shards", type=int, default=64)
    a = ap.parse_args()
    build(a.out, a.shards)


if __name__ == "__main__":
    main()
