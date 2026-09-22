# -*- coding: utf-8 -*-
"""
audit_skill.py v2 — 修正版实证审计

v1 的两个方法论 bug（已修）：
  1. A3 忘了剥掉文件首行标题，导致奇偶错位一格 → 把原文/译文标签搞反，
     误报「293/294 卷异常」。修法：与 build_corpus.py 用同样的标题剥离。
  2. B1 只在单元侧去空白、没在源文件侧去空白 → 跨源行拼接的指纹必然失配。
     修法：两侧都归一化空白后再比对。
教训：审计工具本身必须先自证，否则会产出「看起来很严重的假问题」。
"""
import glob
import io
import json
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from corpus_path import resolve_corpus  # noqa: E402
CORPUS = resolve_corpus()
NL = chr(10)

CLASSICAL = "之者也矣曰其於而乃是以焉乎哉夫"
MODERN = "的了是我你他这那们很就都"


def cls_score(t):
    c = sum(t.count(ch) for ch in CLASSICAL)
    m = sum(t.count(ch) for ch in MODERN)
    return (c - m * 4) / max(1, len(t)) * 100.0


def load(name):
    return [json.loads(l) for l in open(os.path.join(CORPUS, name),
                                        encoding="utf-8")]


print("=" * 64)
print("A. 语料完整性 —— 原文/白话交替是否全库成立")
zz, sj = load("zztj_units.jsonl"), load("shiji_units.jsonl")
zzz = load("zuozhuan_units.jsonl")
print("通鉴单元 %d ／ 史记单元 %d ／ 左传单元 %d" % (len(zz), len(sj), len(zzz)))

no_tran = sum(1 for u in zz if not u["translation"])
swapped = sum(1 for u in zz if u["translation"]
              and cls_score(u["translation"]) > cls_score(u["text"]))
print("A1 无译文单元: %d (%.2f%%)" % (no_tran, 100.0 * no_tran / len(zz)))
print("A2 单元级疑似对调: %d (%.2f%%)" % (swapped, 100.0 * swapped / len(zz)))

zzdir = os.path.join(CORPUS, "zizhitongjian-main", "chapters")
files = sorted(glob.glob(os.path.join(zzdir, "*.md")))
bad, checked = [], 0
for fp in files:
    raw = open(fp, encoding="utf-8").read()
    # ★ 修正1：剥标题行，与 build_corpus.py 一致
    # 标题形如「001_资治通鉴第一卷(周纪)」「052_资冶通鉴第五十二卷」，
    # 卷名后可能没有括号内容，故用宽松匹配到行尾
    body = re.sub(r"^[^" + NL + r"]*资.通.第[^" + NL + r"]*" + NL, "", raw, count=1)
    lines = [l.strip().lstrip("　").strip() for l in body.split(NL)]
    lines = [l for l in lines if l]
    if len(lines) < 6:
        continue
    checked += 1
    ev, od = lines[0::2], lines[1::2]      # 0=原文 1=译文（前两行是时间对）
    a = sum(cls_score(x) for x in ev) / max(1, len(ev))
    b = sum(cls_score(x) for x in od) / max(1, len(od))
    if b >= a:
        bad.append((os.path.basename(fp), round(a, 2), round(b, 2)))
print("A3 逐卷交替检查: %d 卷中异常 %d 卷" % (checked, len(bad)))
for f in bad[:5]:
    print("     异常:", f[0], "原文均分", f[1], "译文均分", f[2])

print("=" * 64)
print("B. 引用保真 —— 正文是否逐字存在于源文件")
random.seed(42)
# ★ 修正2：源侧也归一化空白，一次性构建
zz_pool = re.sub(r"\s+", "", "".join(
    open(f, encoding="utf-8").read() for f in files))
sj_pool = re.sub(r"\s+", "", open(os.path.join(CORPUS, "shiji.txt"),
                                  encoding="utf-8").read())
sample = random.sample(zz, 60) + random.sample(sj, 40)
ok, miss, n = 0, [], 0
for u in sample:
    t = re.sub(r"\s+", "", u["text"])
    if len(t) < 40:
        continue
    n += 1
    pool = zz_pool if u["source"] == "资治通鉴" else sj_pool
    # 3 点指纹：任一命中即算保真。
    # 单点指纹会被源文件换行截断而误报失配（实测假阴性约 4-10%）。
    frs = [t[int(len(t) * f):int(len(t) * f) + 16] for f in (0.2, 0.4, 0.6)]
    if any(f in pool for f in frs):
        ok += 1
    else:
        miss.append((u["cite"], frs[1]))
print("B1 抽样 %d 条, 指纹命中 %d 条 (%.1f%%)" % (n, ok, 100.0 * ok / max(1, n)))
for m in miss[:5]:
    print("     未命中:", m[0], "|", m[1])

print("=" * 64)
print("C. 检索质量")
from retrieve import retrieve  # noqa: E402
QUERIES = []
try:
    import json as _json
    QUERIES = [(q, e) for q, e in _json.load(
        open(os.path.join(HERE, "eval_queries.json"), encoding="utf-8"))]
except Exception as _ex:
    print("  [warn] eval_queries.json 加载失败: %s" % _ex)
from retrieve import match_scenes as _ms
n_id = n_case = n_consist = n_empty = ncase = nprop = 0
for q, expect in QUERIES:
    exps = expect if isinstance(expect, list) else [expect]

    # C1 识别口径：match_scenes 的首位内核是否命中（与 test_skill.py 一致）
    m = _ms(q)
    top1 = m[0][1] if m else None
    if top1 in exps:
        n_id += 1
    else:
        print("  [识别错] %-22s 期望 %-18s 实际 %s"
              % (q[:20], "|".join(exps), top1))
    top2 = {x[1] for x in m[:2]}

    rs = retrieve(q, top=3, min_score=3.0)["results"]
    if not rs:
        n_empty += 1
        continue

    # C4 一致性：首位案例的内核是否在识别的前二之内
    if rs[0]["scene"] in top2:
        n_consist += 1

    # C5 案例口径：首位案例的内核是否命中期望（与识别口径分开统计）
    if rs[0]["scene"] in exps:
        n_case += 1

    for r in rs:
        ncase += 1
        nprop += r.get("n_proposals", 0)

N = len(QUERIES)
print("C1 场景识别命中率: %d/%d = %.1f%%  ← 自拟标注，非独立人工验证"
      % (n_id, N, 100.0 * n_id / max(1, N)))
print("C2 空结果查询: %d" % n_empty)
print("C3 top-3 平均并列选项数: %.2f" % (nprop / max(1, ncase)))
print("C4 检索一致性（首位案例内核在识别前二内）: %d/%d = %.1f%%"
      % (n_consist, N, 100.0 * n_consist / max(1, N)))
print("C5 案例内核命中率（首位案例 ⊆ 期望）: %d/%d = %.1f%%"
      % (n_case, N, 100.0 * n_case / max(1, N)))

print("=" * 64)
print("D. 候选覆盖度（倒排索引可召回量 —— 占比过高说明该场景几乎不过滤）")
idx = json.load(open(os.path.join(CORPUS, "index.json"), encoding="utf-8"))
inv, total = idx["inverted"], len(idx["events"])
from scenes import SCENES  # noqa: E402
rows = []
for s in SCENES:
    cand = set()
    for w in s["classical"]:
        cand.update(inv.get(w, ()))
    rows.append((len(cand), s["id"], len(s["classical"])))
rows.sort(reverse=True)
for cnt, sid, nw in rows:
    flag = "  ← 泛词过多，几乎不过滤" if cnt > total * 0.5 else ""
    print("  %-20s %5d / %d = %4.1f%%%s" % (sid, cnt, total,
                                            100.0 * cnt / total, flag))