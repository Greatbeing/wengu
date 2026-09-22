# -*- coding: utf-8 -*-
"""
推演引擎 —— 把检索到的历史抉择案例，加工成「人生抉择推演卡」

设计原则（对应 SOUL.md 的诚实铁律）：
  1. 绝不虚构原文。所有引用必须来自语料库真实段落，逐字呈现。
  2. 绝不虚构史实。选项/结果/代价若原文未载，必须标注「原文未载」。
  3. 判断与推测分开。原文直接支持的归「原文可见」，推理得出的归「推演」。
  4. 多派并列。同一案例若有不同解读，并列呈现，不钦定一派。

核心函数：
  extract_choices(text)     — 从原文中切出「当时人的选项与主张」
  extract_outcome(text)     — 从原文中定位「实际结果」
  analyze_costs(text, ...)  — 显性代价 / 隐性代价分层
  render_card(...)          — 输出 Markdown 推演卡
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# ── 选项识别：古人表达主张的句式 ──────────────────────────────
PROPOSE_PAT = [
    (r"(?:^|[。；\s])([^。；：]{1,20}?)(?:谏|谓|言|说|曰|对|奏|白|启)[曰:]",
     "主张者发言"),
    (r"(或曰|或谓|或言|或谏)[:：\"“]?(.{5,120}?)(?:[\"”。]|$)", "或人说"),
    (r"(臣|下|某|愚|窃)[以为](.{5,100}?)(?:[\"”。]|$)", "臣议"),
]

# 「接受 / 拒绝 / 犹豫」的决断信号
DECIDE_ACCEPT = ["从之", "以为然", "善之", "许之", "纳之", "用之", "听之",
                 "乃从", "遂从", "王善", "上善", "帝善", "主善", "从其计",
                 "拜受", "乃许", "许之", "以为善", "大悦", "说之"]
DECIDE_REJECT = ["不听", "弗听", "不用", "弗用", "不从", "拒之", "不许",
                 "怒", "不悦", "不纳", "不用其言", "罢之", "斥之", "疏之",
                 "浸疏", "寖疏", "出之", "左迁", "贬"]
DECIDE_HESITATE = ["疑", "未决", "犹豫", "未有所决", "不知所从", "莫之敢",
                   "未敢", "难于", "患之", "忧之", "不知所出"]

# 结果 / 后果信号（用于从原文抓结局）
OUTCOME_PAT = [
    r"(?:遂|乃|卒|竟|于是|由是|以故|是以|其后|已而|无何|顷之|居)[^。]{4,80}。",
    r"(?:果|后果|后)[^。]{4,80}(?:灭|亡|败|死|杀|诛|族|禽|虏|降|走|奔|破)[^。]{0,40}。",
]

# 代价分类：显性（原文直接记载的损失） vs 隐性（需推理的代价）
# 用词原则：宁取多字明确词，不取单字歧义词。
#   反例：「禽」常见于「驱禽除路」（鸟兽）、「罢」常见于「罢驽」（自谦庸劣）、
#        「贫」常见于「民贫流亡」（描述他人）——这些都不是决策者的代价，
#        混进来会让读者误判。原则：歧义词必须与搭配字同现才计。
EXPLICIT_COST = {
    "身亡": ["死", "杀", "诛", "族灭", "夷三族", "斩", "鸩", "自裁", "自杀",
             "伏剑", "刎颈", "身死", "见杀", "伏诛", "弃市"],
    "失位": ["免官", "免归", "罢官", "罢免", "罢之", "夺爵", "废", "左迁",
             "贬", "下狱", "系狱", "收捕", "去位", "解印", "免相", "收印"],
    "丧师": ["大败", "败绩", "覆没", "丧师", "溃", "奔北", "鼓破",
             "为虏", "见禽", "禽获", "败走", "尽没", "歼"],
    "破国": ["国亡", "亡国", "灭国", "绝其祀", "宗庙不", "社稷倾",
             "国除", "灭其国", "屠城"],
    "失地": ["割地", "失地", "削地", "弃地", "分其地", "取其地", "献地",
             "归于", "入于"],
    "失财": ["府库空", "仓廪空", "三空", "财尽", "匮乏", "贫乏", "无以为",
             "耗", "空竭", "虚耗"],
}

# 隐性代价维度（结构性代价，需结合场景判断，原文常不直书）
IMPLICIT_COST_DIMS = [
    ("信用折损", "一次背信后，长期互信被重新定价；他人对你的承诺自动打折"),
    ("人身依附", "选择站队即交出部分自主权，主败则连带清算，主疑则先行被剪除"),
    ("沉默成本锁定", "继续投入旧路径以证明先前正确，导致错过转向窗口"),
    ("士气与内部信任", "公开的屈从或反复，使下属/同伴重新评估你的可预期性"),
    ("道德账户透支", "一次同流合污的账，往往要在多年后以更高利率偿还"),
    ("信息权丧失", "退让或沉默导致被排除在决策圈外，从此只能被动接受"),
    ("先手权丧失", "等待过久，他人已替你把选项锁死，你的选择变成在别人的局里选"),
    ("历史评价反转", "当时的「聪明」常是后世的把柄，身后的名与身前的情难两全"),
]


def split_sentences(text):
    """按中文句末标点切句，保留标点。

    关键：引号（“ ” 「 」 『 』）内部的句号不是句子边界——
    「智果曰：'不如宵也。瑶之贤于人者五'」若在引号内断开，
    会把一次完整主张切碎，导致后续选项提取失败。
    """
    out = []
    buf = []
    depth = 0
    pairs = {"“": "”", "「": "」", "『": "』", "《": "》"}
    closers = set(pairs.values())
    for ch in text:
        buf.append(ch)
        if ch in pairs:
            depth += 1
        elif ch in closers:
            depth = max(0, depth - 1)
        elif ch in "。！？；" and depth == 0:
            out.append("".join(buf).strip())
            buf = []
    if buf:
        out.append("".join(buf).strip())
    return [s for s in out if s]


def extract_choices(text, limit=8):
    """从原文切出「当时人的选项与主张」——支持一句内多位发言者

    古汉语发言句式的主语极不稳定，常见三种：
      A) 完整式   「智果曰：'不如宵也'」      → 说话人在「曰」前
      B) 承前省略 「召问之，对曰：'臣...'」    → 说话人在上文（标「承前省略」）
      C) 无主式   「或曰：'...'」              → 说话人不明（标「或」）

    实现要点：
      1. 引号内的「曰」不算发言点（避免嵌套引语误切）；
         用引号深度计数找出句内**所有**发言点，逐个解析——
         这一步修掉了「段规曰…康子曰…」只出第一个人的老问题。
      2. 极短主张（善/可/然/诺/不可/非也）不是「选项」而是「决断」，
         标 kind=assent/dissent，供上层单独呈现，不混进选项列表。
    """
    out, seen = [], set()
    # 称谓/人称字，用于判定「曰」前那截是人名还是动词
    NOUN_HINT = r"[王公侯伯子男人臣将相帅使尹尉守令史君大夫陛下主帝后妃夫人公子处士先生客或]"
    ASSENT = {"善", "可", "然", "诺", "好", "是", "从之", "许之", "善之",
              "可矣", "善哉", "甚善", "是也", "宜然", "当从", "从", "许"}
    DISSENT = {"不可", "非也", "不然", "未可", "否", "非", "难", "未可也",
               "不可以", "不可也", "未许", "不许", "不从", "不听"}

    for s in split_sentences(text):
        # ── 找出句内所有「不在引号内」的发言点 ──
        # 古汉语引出发言不只「曰」：奏称/上言/对曰/谏曰/白/启/论 亦常见。
        # 统一为两种形式：① X曰  ② X+（称|奏|言|对|谏|白|启|论）：
        spots, depth = [], 0
        opens, closes = set("“‘「『"), set("”’」』")
        for i, ch in enumerate(s):
            if ch in opens:
                depth += 1
                continue
            if ch in closes:
                depth = max(0, depth - 1)
                continue
            if depth != 0:
                continue
            if ch == "曰":
                spots.append(i)
            elif ch == "：":
                # 「光弼奏称：」这类形式；「曰：」已被上一条覆盖，跳过避免重复
                head = s[max(0, i - 4):i]
                if head and head[-1] in "称奏言对谏白启论" and "曰" not in head[-1:]:
                    spots.append(i - 1)   # 以动词位为发言点
        if not spots:
            continue

        # ── 逐个解析说话人 ──
        parsed = []
        for idx in spots:
            before = s[:idx]
            speaker, name_start = "承前省略（原文未复述其名）", idx
            ma = re.search(r"([\u4e00-\u9fa5]{1,8})$", before)
            if ma:
                cand2 = ma.group(1)
                # 1) 「嚭因说吴王曰」「苏代乃谓齐王曰」→ 说话人是动词前的部分
                m2 = re.match(r"^(.{1,4}?)(?:因说|说|谓|谏|劝|告|问)", cand2)
                if m2 and m2.group(1) and len(cand2) > len(m2.group(1)):
                    cand2 = m2.group(1)
                # 2) 反复剥离尾部动词/礼节词/副词：
                #    「种顿首言曰」→种，「子胥进谏曰」→子胥，「苏代乃」→苏代
                for _ in range(4):
                    c3 = re.sub(
                        r"(顿首|再拜|稽首|膝行|涕泣|泣|拜|进言|进|"
                        r"召问之|问之|因说|说|言|谏|奏|白|启|对|称|"
                        r"问|谓|告|谋|请|敢|谨|窃|"
                        r"乃|遂|既|复|又|则|且|亦|皆|遽)$", "", cand2)
                    if c3 == cand2:
                        break
                    cand2 = c3
                # 3) 副词/连词不是人名（「乃曰」的「乃」）
                if cand2 in ("乃", "遂", "因", "故", "于是", "既", "复",
                             "又", "而", "则", "且", "终", "竟", "亦", "皆"):
                    cand2 = ""
                if cand2 and re.search(NOUN_HINT, cand2[-1]):
                    speaker, name_start = cand2[-4:], idx - len(cand2)
                elif cand2 and 1 <= len(cand2) <= 4:
                    speaker, name_start = cand2, idx - len(cand2)
            parsed.append({"idx": idx, "speaker": speaker,
                           "name_start": name_start})

        # ── 主张 = 本发言点到下一个发言点之间 ──
        for k, p in enumerate(parsed):
            end = parsed[k + 1]["name_start"] if k + 1 < len(parsed) else len(s)
            zone = s[p["idx"] + 1:end].lstrip(":： ")
            if zone[:1] in ("“", "「", "『"):
                oq = zone[0]
                cq = {"“": "”", "「": "」", "『": "』"}[oq]
                e = zone.find(cq)
                claim = zone[1:e] if e > 0 else re.split(r"[。！？]", zone[1:])[0]
            else:
                claim = re.split(r"[。！？]", zone)[0]
            claim = claim.strip(" \"“”「』」]：:，、；。！？")
            if not claim:
                continue
            bare = claim.rstrip("。！？")
            if bare in ASSENT:
                kind = "assent"
            elif bare in DISSENT:
                kind = "dissent"
            elif len(bare) <= 2 and re.fullmatch(r"[善可然诺好是非否难]", bare):
                kind = "assent" if bare in "善可然诺好是" else "dissent"
            else:
                kind = "propose"
            if kind == "propose" and len(claim) < 6:
                continue
            key = claim[:24]
            if key in seen:
                continue
            seen.add(key)
            out.append({"speaker": p["speaker"], "claim": claim,
                        "kind": kind, "sentence": s})
            if len(out) >= limit:
                return out
    return out


def extract_outcome(text, limit=4):
    """从原文抓「实际结果」句"""
    sents = split_sentences(text)
    out = []
    for pat in OUTCOME_PAT:
        for s in sents:
            if re.search(pat, s) and s not in out:
                out.append(s)
        if len(out) >= limit:
            break
    return out[:limit]


def detect_decision(text):
    """判定最终决断：采纳 / 拒绝 / 悬而未决 / 原文未载"""
    for w in DECIDE_REJECT:
        if w in text:
            return "拒绝/未纳（原文可见信号：%s）" % w
    for w in DECIDE_ACCEPT:
        if w in text:
            return "采纳/施行（原文可见信号：%s）" % w
    for w in DECIDE_HESITATE:
        if w in text:
            return "犹豫未决（原文可见信号：%s）" % w
    return "原文未载明最终决断"


def analyze_costs(text, scene=None, max_per_cat=2):
    """显性代价（原文直载）分层

    诚实原则（重要）：
      代价词可能属于决策者，也可能属于相关方（敌国、被牵连者、他人）。
      原文常不点明归属，故不能只报「已发生」——那会把别人的死
      误记成你的代价。这里同时给出词所在的原句，归属由读者判断。
    """
    found = {}
    sents = split_sentences(text)
    for cat, words in EXPLICIT_COST.items():
        hits, used = [], set()
        for w in words:
            for s in sents:
                if w in s and s not in used:
                    used.add(s)
                    hits.append({"word": w, "sentence": excerpt(s, 90)})
                    break
            if len(hits) >= max_per_cat:
                break
        if hits:
            found[cat] = hits
    return found


IMPLICIT_CUES = [
    ("信任折损", ["疑", "不信", "疏", "隙", "怨", "谗", "谮"],
     "关系已从合作转为戒备，此后再难复原"),
    ("关系转为长期对立", ["仇", "报", "畔", "叛", "背", "负"],
     "一次决裂把对方推向长期敌对面，成本远超当下得失"),
    ("时间与消耗战", ["久", "累年", "数岁", "连年", "相持", "顿兵"],
     "僵持把资源消耗在时间里，胜者也一并透支"),
    ("事后追悔", ["悔", "恨", "惜", "不及", "无及"],
     "代价在当时未被计入，事后才显形——说明它不在当时的账本上"),
    ("位置与自主权丧失", ["免", "罢", "废", "夺", "收", "迁"],
     "位置一旦交出，自主权随之丧失，再入场门槛陡升"),
    ("信息盲区", ["骄", "轻", "慢", "易", "不备", "懈"],
     "优势方进入信息盲区，这常是败因的起点"),
    ("连带他人", ["族", "坐", "连", "并及"],
     "代价不止于决策者，牵连范围常超出决策时的预期"),
]


def implicit_from_case(text, limit=4):
    """从案例文本推导结构性代价线索（按文本触发，非固定查找表）

    与旧版的关键区别：旧版按内核查表 → 同一内核所有案例输出完全一样，
    是「看起来定制、实则模板」。现改为只有文本真的出现线索词才输出，
    并附触发词，读者可自行核对。
    """
    out = []
    for name, cues, gloss in IMPLICIT_CUES:
        hit = sorted({w for w in cues if w in text})
        if hit:
            out.append({"dim": name, "cue": "/".join(hit[:4]), "gloss": gloss})
        if len(out) >= limit:
            break
    return out


def scene_implicit_dims(scene_id):
    """按场景给出最相关的隐性代价维度（取前4项，避免模板化）"""
    focus = {
        "choose-side": ["人身依附", "信用折损", "先手权丧失", "信息权丧失"],
        "stay-or-go": ["沉默成本锁定", "先手权丧失", "信息权丧失", "士气与内部信任"],
        "successor": ["士气与内部信任", "信用折损", "沉默成本锁定", "历史评价反转"],
        "remonstrate": ["信用折损", "信息权丧失", "道德账户透支", "士气与内部信任"],
        "war-or-peace": ["沉默成本锁定", "先手权丧失", "信用折损", "道德账户透支"],
        "employ-person": ["信用折损", "信息权丧失", "人身依附", "道德账户透支"],
        "risk-return": ["沉默成本锁定", "先手权丧失", "信用折损", "历史评价反转"],
        "faith-or-interest": ["信用折损", "道德账户透支", "历史评价反转", "信息权丧失"],
        "timing": ["先手权丧失", "沉默成本锁定", "信息权丧失", "信用折损"],
        "endure": ["士气与内部信任", "信用折损", "沉默成本锁定", "历史评价反转"],
        "family-wealth": ["士气与内部信任", "沉默成本锁定", "信用折损", "历史评价反转"],
        "moral-trial": ["道德账户透支", "历史评价反转", "信用折损", "人身依附"],
    }
    keys = focus.get(scene_id, [k for k, _ in IMPLICIT_COST_DIMS[:4]])
    return [(k, dict(IMPLICIT_COST_DIMS)[k]) for k in keys]


def excerpt(text, n=320):
    """截取可读片段，保留首尾关键信息"""
    t = re.sub(r"\s+", "", text)
    if len(t) <= n:
        return t
    return t[: n - 12] + "……" + t[-10:]


def focus_span(text, scene, width=560):
    """把「事件单元」聚焦到真正的抉择现场

    问题：通鉴一个 [编号] 段常含一年内多件事，滑窗合并后（最多4段）
          可能塞进互不相关的数个事件。若在其上直接抽选项，
          会抽到别的故事的发言（如核心是「乞骸骨」，却抽到「谏猎」）。
    解法：以场景古典信号词的**首个命中点**为锚，取前后 width 字的窗口，
          并把窗口对齐到句边界，使 ②③④ 的分析围绕同一个决策现场。
    返回 (span, anchored)：anchored 表示是否真的找到了锚点。
    """
    best = None
    for w in scene["classical"]:
        i = text.find(w)
        if i >= 0 and (best is None or i < best):
            best = i
    if best is None:
        return text[:width], False
    half = width // 2
    start = max(0, best - half)
    end = min(len(text), best + half)
    span = text[start:end]
    # 对齐到句首：若截断处不在句读之后，向后推到下一个句读
    if start > 0:
        m = re.search(r"[。！？；]", span)
        if m and m.end() < len(span) // 2:
            span = span[m.end():]
    return span.strip(), True


def render_card(case, user_text, scene, rank=1):
    """渲染单个案例的推演卡（Markdown）"""
    L = []
    cite = case["cite"]
    L.append("### 案例 %d｜%s" % (rank, cite))
    if case.get("time"):
        tt = case["time"].split(" / ")[0]
        L.append("**年代**：%s　**场景内核**：%s" % (tt, scene["name"]))
    else:
        L.append("**场景内核**：%s" % scene["name"])

    # 聚焦到抉择现场：整段可能含多个事件，分析必须围绕同一个决策展开
    span, anchored = focus_span(case["text"], scene)
    if len(span) < len(case["text"]):
        L.append("**抉择现场**：已从该段 %d 字中聚焦到 %d 字"
                 % (len(case["text"]), len(span)))
    L.append("")

    # 1) 原文出处（逐字）
    L.append("**① 原文出处（逐字）**")
    L.append("> " + span.replace("\n", "\n> "))
    if case.get("translation"):
        L.append(">")
        L.append("> 【白话参考】" + excerpt(case["translation"], 300))
    L.append("")
    L.append("> 完整出处：%s" % cite)
    L.append("")

    # 2) 当时的选项（仅 propose；assent/dissent 归入决断）
    choices = extract_choices(span)
    proposals = [c for c in choices if c["kind"] == "propose"]
    reactions = [c for c in choices if c["kind"] in ("assent", "dissent")]

    def _name(sp):
        return "（承前）" if sp.startswith("承前") else sp

    L.append("**② 古人当时的选项**")
    if proposals:
        for i, c in enumerate(proposals, 1):
            sp = ("**%s**：" % _name(c["speaker"])) if c["speaker"] else ""
            L.append("- 选项 %d %s%s" % (i, sp, excerpt(c["claim"], 170)))
    else:
        L.append("- 原文未载明并列选项（该段为结果陈述，非决策现场）")
    L.append("")

    # 3) 决断与结果
    L.append("**③ 结果判断**")
    L.append("- 最终决断：%s" % detect_decision(span))
    for r in reactions[:4]:
        mark = "采纳" if r["kind"] == "assent" else "否决"
        L.append("  - %s表态「%s」→ %s" % (_name(r["speaker"]), r["claim"], mark))
    outs = extract_outcome(span)
    if outs:
        for o in outs:
            L.append("- 后果：%s" % excerpt(o, 150))
    else:
        L.append("- 后果：原文未在此段载明（需回溯上下文或相邻卷次）")
    L.append("")

    # 4) 代价
    costs = analyze_costs(span)
    L.append("**④ 代价分层**")
    if costs:
        L.append("- **显性代价**（本段出现的代价信号；归属可能是决策者，"
                 "也可能是相关方——附原句供你判断）：")
        for cat, hits in costs.items():
            for h in hits:
                L.append("  - %s：「%s」→ %s" % (cat, h["word"], h["sentence"]))
    else:
        L.append("- 显性代价：此段未见直接记载")
    L.append("- **隐性代价**（从本案例文本推导，附触发词可自行核对）：")
    ic = implicit_from_case(span)
    if ic:
        for d in ic:
            L.append("  - **%s**（触发「%s」）— %s"
                     % (d["dim"], d["cue"], d["gloss"]))
    else:
        L.append("  - 本段未见结构性代价线索（该段可能只是决策片段，"
                 "代价需回溯后续卷次）")
    L.append("- 该内核的一般代价方向（提示，非本案例结论）：%s"
             % scene["cost_axis"])
    L.append("")
    return "\n".join(L)


def main():
    pass


if __name__ == "__main__":
    main()
