# -*- coding: utf-8 -*-
"""
retrieve.py — 古籍抉择案例检索器

用法：
  python retrieve.py --scene choose-side --keywords 韩 信 萧何 --top 5
  python retrieve.py --query 该不该离开现在的公司 --top 5
  python retrieve.py --list-scenes

检索策略（三路混合，避免单路误判）：
  1) 场景匹配：用户输入命中 scenes.modern 词 → 得到候选场景
  2) 古典信号：在该场景的 classical 词内，统计命中密度
  3) 关键词：用户补充的人名/事件词，在原文中直接检索
最终排序 = 场景古典词命中密度 + 关键词命中 + 「抉择证据词」加权 + 段长归一

输出：JSON（含原文、白话、出处、命中理由），供上层推演使用。
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
from corpus_path import resolve_corpus  # noqa: E402
CORPUS = resolve_corpus()
sys.path.insert(0, HERE)
from scenes import SCENES, STEMS, EXTRA_STEMS, WEAK_STEMS  # noqa: E402
import deduce as _deduce  # noqa: E402  (deduce 不反向依赖 retrieve，无循环)

# 「这是抉择现场」的强证据词：出现这些，说明该段确实在记录一次决策，
# 而不是泛泛叙述。加权给足，因为这是本技能与普通古文检索器的分野。
EVIDENCE = [
    "谋曰", "议曰", "对曰", "曰：", "曰“", "曰「", "问曰", "谏曰", "说曰",
    "遂", "乃", "于是", "乃许", "乃许之", "不听", "弗听", "不用", "弗用",
    "许之", "拒之", "许", "拒", "从之", "不从", "以为然", "善", "非也",
    "不可", "未可", "果", "后", "卒", "竟", "于是乎", "以故", "由是",
]

# 用于判断段落是否含「后果/代价」信息——隐性代价分析靠这些段
CONSEQUENCE = [
    "灭", "亡", "败", "死", "杀", "诛", "族", "禽", "虏", "降", "走", "奔",
    "破", "残", "困", "饥", "乱", "叛", "畔", "祸", "咎", "殃", "及", "族灭",
    "身死", "国亡", "遂灭", "以灭", "果", "后", "卒", "竟", "于是", "由是",
    "是以", "以此", "故", "其后", "已而", "居", "无何", "顷之",
]


# 《左传》公爵历史顺序（隐桓庄闵僖文宣成襄昭定哀）——不能用 Unicode 排序，
# 否则「僖」会排到「隐」后，案例先后全乱
DUKE_ORDER = ('隐', '桓', '庄', '闵', '僖', '文', '宣', '成', '襄', '昭', '定', '哀')
DUKE_IDX = {d: i for i, d in enumerate(DUKE_ORDER)}


def duke_key(u):
    d = (u.get("duke") or " ")[0]
    return DUKE_IDX.get(d, 99)


CN_DIGIT = {'零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9, '十': 10, '百': 100}

def year_key(u):
    """从「三十三年」取数值 33

    必须按数值排序：字符串排序下「三十三」<「三」，
    会把三十三年排到三年前面，案例先后全错、出处区间倒退。
"""
    s = re.sub(r"[^一二三四五六七八九十百零]", "", u.get('year') or '')
    if not s:
        return 0
    if '百' in s:
        parts = s.split('百')
        hi = 0
        for ch in parts[0]:
            hi = hi * 10 + CN_DIGIT.get(ch, 0)
        lo = 0
        for ch in parts[1]:
            if ch == '十':
                lo = 10 if lo == 0 else lo * 10
            else:
                lo = CN_DIGIT.get(ch, 0)
        return hi * 100 + (lo or 0 if parts[1] else 0)
    total, prev = 0, 0
    for ch in s:
        v = CN_DIGIT[ch]
        if v == 10:
            total += 10 if prev == 0 else prev * 10
            prev = 0
        elif v == 100:
            total += 100 if prev == 0 else prev * 100
            prev = 0
        else:
            prev = v
    return total + prev


def load_units():
    out = []
    for name in ("zztj_units.jsonl", "shiji_units.jsonl", "zuozhuan_units.jsonl"):
        p = os.path.join(CORPUS, name)
        if not os.path.exists(p):
            print("[warn] 缺少语料 %s，先运行 build_corpus.py" % name, file=sys.stderr)
            continue
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    u = json.loads(line)
                    u.setdefault("n_segments", 1)
                    out.append(u)
    return out


def _merge(src, chunk):
    if len(chunk) == 1:
        u = dict(chunk[0])
        u["n_segments"] = 1
        return u
    text = "\n".join(c["text"] for c in chunk)
    tran = "\n".join(c.get("translation", "") for c in chunk)
    if src == "资治通鉴":
        seqs = [c["seq"] for c in chunk]
        cite = "《资治通鉴》卷%d（%s）[%d-%d]" % (
            chunk[0]["juan"], chunk[0]["reign"], min(seqs), max(seqs))
    elif src == "左传":
        c0 = chunk[0]
        if len(chunk) == 1 and c0.get("year"):
            cite = c0.get("cite") or ("《左传》%s" % c0["title"])
        else:
            cite = ("《左传》%s（%s～%s）" % (c0.get("duke", ""),
                                        chunk[0].get("year", ""), chunk[-1].get("year", "")))
    else:
        cite = "《史记》卷%d %s" % (chunk[0]["juan"], chunk[0]["title"])
    return {
        "source": src,
        "juan": chunk[0]["juan"],
        "reign": chunk[0].get("reign", ""),
        "title": chunk[0].get("title", ""),
        "seq": min(c.get("seq", 0) for c in chunk),
        "time": chunk[0].get("time", ""),
        "text": text,
        "translation": tran,
        "cite": cite,
        "chars": len(text),
        "n_segments": len(chunk),
    }


def build_event_units(units, window=4):
    """把相邻编号段合并为「事件单元」

    问题：通鉴按 [编号] 切段会把同一事件的前因后果切断——
          「卷2[1]」只剩「秦献公败三晋之师于石门」37字，
          而决策现场「齐威王救赵／孙膑献策」在后续段里。
    解法：同卷内按编号顺序滑窗合并，使检索单元 = 完整事件而非碎片。
    """
    events = []
    for src in ("资治通鉴", "史记", "左传"):
        rows = [u for u in units if u["source"] == src]
        if src == "史记":
            groups = {}
            for r in rows:
                groups.setdefault((r["juan"], r.get("title", "")), []).append(r)
            for _k, grp in sorted(groups.items()):
                for i in range(0, len(grp), 3):
                    events.append(_merge(src, grp[i:i + 3]))
        elif src == "左传":
            # 左传按「公」分组，公内按年滑窗合并。
            # window=2：左传已切到 600 字/段，两年合并约 1200 字，
            # 既保住「国君听谏→决策→后果」的完整链条，又不会过头。
            # 不合并跨公（不同公叙事不连续）。
            groups = {}
            for r in rows:
                groups.setdefault(r.get("duke", ""), []).append(r)
            for duke in sorted(groups, key=lambda d: DUKE_IDX.get((d or " ")[0], 99)):
                grp = sorted(groups[duke], key=year_key)
                for i in range(0, len(grp), 2):
                    events.append(_merge(src, grp[i:i + 2]))
        else:
            groups = {}
            for r in rows:
                groups.setdefault(r["juan"], []).append(r)
            for juan in sorted(groups):
                grp = sorted(groups[juan], key=lambda r: r["seq"])
                i = 0
                while i < len(grp):
                    chunk = [grp[i]]
                    j = i + 1
                    while j < len(grp) and len(chunk) < window:
                        if grp[j]["seq"] - grp[j - 1]["seq"] <= 1:
                            chunk.append(grp[j])
                            j += 1
                        else:
                            break
                    events.append(_merge(src, chunk))
                    i = j if j > i else i + 1
    return events


def load_event_units():
    return build_event_units(load_units())


def retrieve(user_text, keywords=None, scene_ids=None, top=5, min_score=1.0,
             units=None, verbose=False):
    keywords = keywords or []
    units = units if units is not None else load_event_units()


def match_scenes(user_text: str):
    """用户现代描述 → 场景 id 列表（加权排序）

    权重：完整词 3.0 ｜ 强碎片 1.0 ｜ 弱碎片 0.35 ｜ 单字 0.4（仅无更强信号时）

    两处去重（修过的 bug，勿删）：
      1. 与完整词重复的碎片不再计分——否则「房子」会既算 modern(3.0)
         又算 STEMS(1.0)，同一件事被算两遍。
      2. 互为子串的碎片只保留最长者——否则「撕破脸」会同时命中
         「撕破脸/撕破/撕」三条，同一信号被加 3 次权重。
    """
    text = user_text.lower()
    scored = []
    for s in SCENES:
        sid = s["id"]
        exact = [w for w in s["modern"] if w.lower() in text]
        exact_l = {w.lower() for w in exact}
        stems = list(STEMS.get(sid, [])) + list(EXTRA_STEMS.get(sid, []))
        weak = set(WEAK_STEMS.get(sid, []))

        raw = [w for w in stems if w in text]
        # 统一去重：把「现代完整词」与「碎片」放进同一场，
        # 按长度降序，任何是更长命中串子串（或与之相同）的条目一律丢弃。
        # 这样「撕破脸」(modern 3.0) 与「撕破」(stem 1.0) 不会再重复计分。
        cand, seen = [], set()
        for w in exact:
            if w not in seen:
                seen.add(w)
                cand.append((w, True))
        for w in raw:
            if w not in seen:
                seen.add(w)
                cand.append((w, False))
        cand.sort(key=lambda x: -len(x[0]))
        final = []
        for w, is_modern in cand:
            if any(w in o for o, _m in final):
                continue
            final.append((w, is_modern))

        exact = [w for w, m in final if m]
        kept = [w for w, m in final if not m]
        strong = [w for w in kept if len(w) >= 2 and w not in weak]
        wk = [w for w in kept if w in weak]
        short = [w for w in kept if len(w) == 1 and w not in weak]

        score = len(exact) * 3.0 + len(strong) * 1.0 + len(wk) * 0.35
        if not exact and not strong:
            score += len(short) * 0.4
        if score <= 0:
            continue
        hits = exact + strong + wk + short
        scored.append((round(score, 2), sid, hits))
    scored.sort(key=lambda x: (-x[0], -len(x[2]), x[1]))
    return scored


def score_unit(unit, scene, keywords, idf=None):
    """给单个事件单元打分。

    IDF 加权（优化 P0-1）：
      旧版按「命中词数 / 长度」计分，导致「利」「害」这类命中 5000+ 单元的
      泛词与「乞骸骨」这类稀有词同权，泛词主导排序。
      现改为 Σ IDF(词)：稀有词权重可达 7-8，泛词仅 1.0-1.3，
      让真正有区分度的信号决定排序。
    """
    text = unit["text"]
    sc = 0.0
    reasons = []
    L = max(1, len(text))
    idf = idf or {}

    def w_of(w):
        return idf.get(w, 1.0)

    # 1) 古典信号词：按稀有度加权，稀有词才是强信号
    #    次级键取词本身：idf 相同的词若顺序不定，浮点求和次序就不定，
    #    末位差异会在舍入边界上翻出 0.01 的分差（实测出现过一次）。
    hits = sorted({w for w in scene["classical"] if w in text},
                  key=lambda w: (-w_of(w), w))
    if hits:
        sc += min(6.5, sum(w_of(w) for w in hits) * 0.55)
        reasons.append("古典信号(按稀有度):" + "/".join(hits[:6]))

    # 2) 抉择证据词：判定「这是决策现场」而非背景叙述（同样按稀有度）
    ev = sorted({w for w in EVIDENCE if w in text}, key=lambda w: (-w_of(w), w))
    if ev:
        sc += min(3.0, sum(w_of(w) for w in ev) * 0.32)
        reasons.append("抉择证据:" + "/".join(ev[:5]))

    # 3) 选项对立结构：真正的人生抉择一定出现「多方案争执」
    opt = 0
    if re.search(r"曰[:：\"“」『]", text):
        opt += 1
    if re.search(r"(或曰|或谓|或言|人曰|客曰|臣曰|对曰|谏曰|说曰)", text):
        opt += 1
    if re.search(r"(遂|乃|于是|卒|竟|竟以|以故|由是|其后|已而|无何|顷之|居)", text):
        opt += 1
    if opt:
        sc += min(3.0, opt * 1.1)
        reasons.append("选项对立:%d层" % opt)

    # 4) 用户关键词（人名/事件/专有名词）—— 用户亲自给的词，权重最高
    kw = [k for k in keywords if k and k in text]
    if kw:
        sc += min(7.0, len(kw) * 2.2)
        reasons.append("关键词:" + "/".join(kw[:6]))

    # 5) 有白话译文加分（推演时可作校准）
    if unit.get("translation"):
        sc += 0.3

    # 6) 后果/代价信息（隐性代价分析需要）—— 按稀有度加权
    cq = sorted({w for w in CONSEQUENCE if w in text}, key=lambda w: (-w_of(w), w))
    if cq:
        sc += min(1.8, sum(w_of(w) for w in cq) * 0.22)
        reasons.append("后果信息:%d项" % len(cq))

    # 7) 长度归一：过短无推演价值；过长聚焦困难，但不重罚（事件完整性优先）
    if L < 60:
        sc -= 2.5
    elif 150 <= L <= 800:
        sc += 0.8

    # 8) 双向对话：既有进言、又有表态 → 真实的决策记录
    #    单方叙述（「某人死了」）推演价值低，必须让位给「谏—决」成交互的段落
    has_advice = bool(re.search(r"(谏|说|对|谋|议|言于|上疏|奏|问)", text))
    has_verdict = bool(re.search(
        r"(从之|不听|弗听|不用|不纳|许之|纳之|以为然|拒之|不许|善之|怒|乃许|乃从)", text))
    if has_advice and has_verdict:
        sc += 1.6
        reasons.append("双向对话:进言+表态")

    return sc, reasons


_INDEX_CACHE = {}


def load_index():
    """优先读预建索引；无索引则现场构建（慢但可用）"""
    if "idx" in _INDEX_CACHE:
        return _INDEX_CACHE["idx"]
    p = os.path.join(CORPUS, "index.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            idx = json.load(f)
        _INDEX_CACHE["idx"] = idx
        return idx
    events = load_event_units()
    inv = {}
    for i, e in enumerate(events):
        text = e["text"]
        seen = set()
        for s in SCENES:
            for w in s["classical"]:
                if w in text and w not in seen:
                    seen.add(w)
                    inv.setdefault(w, []).append(i)
    idx = {"events": events, "inverted": inv, "stats": {}}
    _INDEX_CACHE["idx"] = idx
    return idx


def candidate_indices(scene, index):
    """该场景古典词命中的候选事件下标（并集）

    返回**升序列表**而非 set —— 这是一处真实缺陷的修复：
    原先返回 set，遍历顺序取决于哈希桶内部布局，虽对 int 而言稳定，
    但属不可解释的实现细节。它决定了同分案例的先后，也就是说
    「同一个问题两次跑出不同案例」的风险藏在这里。
    改为升序（即语料顺序：通鉴卷序 → 史记 → 左传）后，
    同分排序有明确语义，且与浏览器端移植实现天然一致。
    """
    inv = index["inverted"]
    s = set()
    for w in scene["classical"]:
        for i in inv.get(w, ()):
            s.add(i)
    return sorted(s)


def retrieve(user_text, keywords=None, scene_ids=None, top=5, min_score=1.0,
             units=None, verbose=False):
    keywords = keywords or []
    index = load_index()
    events = units if units is not None else index["events"]
    idf = index.get("idf") or {}
    matched = match_scenes(user_text)
    scene_map = {s["id"]: s for s in SCENES}

    if scene_ids:
        # 显式指定场景：等权
        target = [(sid, 1.0) for sid in scene_ids if sid in scene_map]
    elif matched:
        # 按命中强度归一化为场景权重，主场景权重显著高于次场景
        total = sum(m[0] for m in matched[:3]) or 1.0
        target = [(m[1], m[0] / total) for m in matched[:3]]
    else:
        target = []

    pool = [(sid, scene_map[sid]) for sid, _w in target]

    results = []
    if pool:
        wmap = dict(target)
        for sid, scene in pool:
            w = wmap.get(sid, 1.0)
            # 只扫该场景的候选集（倒排索引），不扫全库
            for i in candidate_indices(scene, index):
                u = events[i]
                sc, reasons = score_unit(u, scene, keywords, idf)
                if sc < min_score:
                    continue
                # 最终分 = 案例质量 × 场景权重（用户语义主导）
                final = sc * (0.55 + 1.45 * w)
                reasons.append("场景权重:%.2f" % w)
                results.append({
                    "scene": sid,
                    "scene_name": scene["name"],
                    "quality": round(sc, 2),
                    "score": round(final, 2),
                    "reasons": reasons,
                    "source": u["source"],
                    "cite": u["cite"],
                    "time": u.get("time", ""),
                    "text": u["text"],
                    "translation": u.get("translation", ""),
                    "n_segments": u.get("n_segments", 1),
                })
    # 无场景命中时，退化为纯关键词检索
    if not pool and keywords:
        for u in units:
            kw = [k for k in keywords if k and k in u["text"]]
            if kw:
                results.append({
                    "scene": "raw",
                    "scene_name": "原文直检",
                    "score": len(kw) * 2.0,
                    "reasons": ["关键词:" + "/".join(kw)],
                    "source": u["source"],
                    "cite": u["cite"],
                    "time": u.get("time", ""),
                    "text": u["text"],
                    "translation": u.get("translation", ""),
                })

    results.sort(key=lambda r: -r["score"])

    # ── 二次排序：案例里真能抽出 ≥2 个并列选项，才是「多方案抉择现场」 ──
    # 单方叙述（「某人乞骸骨…死了」）虽有信号词，推演价值远低于
    # 「A 主张这样、B 主张那样、主上择其一」的辩论现场。
    # 只对已入前列的候选做（40 条封顶），成本可控。
    head = results[:40]
    for r in head:
        sc = scene_map.get(r["scene"])
        if not sc:
            continue
        try:
            span, _anchored = _deduce.focus_span(r["text"], sc)
            ch = _deduce.extract_choices(span)
        except Exception:
            continue
        n_prop = sum(1 for c in ch if c["kind"] == "propose")
        r["n_proposals"] = n_prop
        if n_prop >= 2:
            r["score"] = round(r["score"] * 1.18, 2)
            r["reasons"].append("并列选项:%d" % n_prop)
        elif n_prop == 0:
            r["score"] = round(r["score"] * 0.85, 2)
            r["reasons"].append("无并列选项")
    results.sort(key=lambda r: -r["score"])
    # 去重（同源同段可能多场景命中）
    seen, uniq = set(), []
    for r in results:
        k = (r["cite"], r["text"][:40])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
        if len(uniq) >= top:
            break
    return {
        "user_text": user_text,
        "matched_scenes": [{"id": m[1], "name": scene_map[m[1]]["name"],
                            "hits": m[2]} for m in matched],
        "keywords": keywords,
        "results": uniq,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", default=None)
    ap.add_argument("--query", default=None)
    ap.add_argument("--keywords", default="")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--min-score", type=float, default=1.0)
    ap.add_argument("--list-scenes", action="store_true")
    a = ap.parse_args()

    if a.list_scenes:
        for s in SCENES:
            print("%-16s %-8s %s" % (s["id"], s["name"], s["question"]))
            print("   现代: %s" % "、".join(s["modern"]))
        return

    user_text = a.query or ""
    kws = [k.strip() for k in a.keywords.replace("，", " ").split() if k.strip()]
    out = retrieve(user_text, keywords=kws,
                   scene_ids=[a.scene] if a.scene else None,
                   top=a.top, min_score=a.min_score)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
