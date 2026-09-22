# -*- coding: utf-8 -*-
"""
tuiliyan.py — 人生抉择推演主入口

用法：
  python tuiliyan.py "我在考虑要不要离开现在的公司跟朋友去创业"
  python tuiliyan.py "该不该向领导提出反对意见" --top 3 --keywords 袁盎 淮南王
  python tuiliyan.py --scene remonstrate --top 2
  python tuiliyan.py --list-scenes
  python tuiliyan.py "..." --json out.json --md out.md

流程：
  1) 场景匹配：用户现代处境 → 决策内核（12 个场景）
  2) 案例检索：倒排索引 + 质量打分（抉择现场判别 + 场景权重）
  3) 推演加工：逐字原文、选项拆解、结果判断、显性/隐性代价
  4) 规律启发 + 风险提醒
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from retrieve import retrieve  # noqa: E402
from corpus_path import resolve_corpus  # noqa: E402

_PATTERNS_CACHE = {}


def load_patterns():
    """读取 derive_patterns.py 导出的语料统计（可复核），失败则返回空"""
    if "p" in _PATTERNS_CACHE:
        return _PATTERNS_CACHE["p"]
    import json as _json
    fp = os.path.join(resolve_corpus(), "patterns.json")
    try:
        with open(fp, encoding="utf-8") as f:
            d = _json.load(f).get("scenes", {})
    except Exception:
        d = {}
    _PATTERNS_CACHE["p"] = d
    return d
from scenes import SCENES  # noqa: E402
import deduce  # noqa: E402
NL = chr(10)

SCENE_MAP = {s["id"]: s for s in SCENES}

# ── 规律启发：按场景给出「古人反复证明的结构」 ──────────────
PATTERNS = {
    "choose-side": [
        "古人择主，看的从不是「谁现在强」，而是「谁愿意听我说完」——范雎、商鞅皆因主听言而得行其道。",
        "投靠前的沉默成本极少被计入：一旦委质，你的进退就不再只由能力决定。",
        "良主的共同点是能容错，而非永远正确；错而能改者胜，正确而不能容人者速去。",
    ],
    "stay-or-go": [
        "通鉴里「功成身退」者少，「恋栈不去」者多——退的窗口通常在功劳最大时打开，一旦生疑即关闭。",
        "走与留的分界常不在你多想走，而在你「还能不能被问意见」；被排除在决策圈外即是信号。",
        "以逃离心境离开，往往在新处重演旧局——古人屡验「不去其故，虽迁无益」。",
    ],
    "successor": [
        "立嗣之争的核心不是选最贤，而是选「能让其余人不生异心」的那个——稳定优先于最优。",
        "只看长处不看短板，是智伯亡族的直接原因；五贤一不仁，足以覆宗。",
        "托孤重臣与储君的张力千古同构：授人以柄者，须预留制衡之手。",
    ],
    "remonstrate": [
        "谏言的效用与次数成反比：第一次是信息，第三次是立场，第七次是挑衅。",
        "古人谋士进言前先看「决策者的退路是否被封」——有台阶则谏有效，无台阶则谏招祸。",
        "知道言不用而仍言，多是为人格信用，不是为事功；两者须分清，否则怨心生焉。",
    ],
    "war-or-peace": [
        "通鉴中的大败，多败于「不该打而打」，而非「该打而败」。",
        "持重待时者常被讥为怯，但史书里先动手的一方胜率并不高——势未集而战，是赌不是决策。",
        "战前必须先算「不胜之代价」：不胜而能全身者，才配谈战。",
    ],
    "employ-person": [
        "古人识人重「临事」不重「言辞」：观其在小利、在危局、在无人见处的取舍。",
        "授权而不察，等于把情报权一并交出；察而不当，则逼出欺瞒。",
        "亲信背叛的根，多在授权结构而非人品——结构把好人逼成必须欺瞒的位置。",
    ],
    "risk-return": [
        "古人的「计」从不只算收益，必先算「不可逆」一项；可逆之失是学费，不可逆之失是终局。",
        "大利之后常跟大患，通鉴中的骤兴多以骤败收场；慢而稳者反能久。",
        "机会成本最易被忽略：押注一处的最大代价，是其余全部可能被关死。",
    ],
    "faith-or-interest": [
        "「夫信者，人君之大宝也」——信誉是唯一越用越值钱的资产，也是一次即崩的资产。",
        "背信之利当期到账，折价终身偿还；古人以国为注，仍常选守小信而失近利。",
        "但守信不等于愚信：约可改，须在未伤人之时明改，而非默背。",
    ],
    "timing": [
        "「将欲败之，必姑辅之」——古人最高的时机术，是等待而非制造。",
        "过早出手与过晚出手同败：一个暴露意图，一个丧失资格。",
        "判断时机的唯一硬指标是「势是否在你这边」，而非你的情绪是否已准备好。",
    ],
    "endure": [
        "忍的有效边界在于「忍时有蓄势之实」；无实之忍只是把痛苦延期。",
        "卧薪尝胆之后必须接一个明确的反击窗口，否则忍耐转为自我消耗。",
        "忍辱者最难承受的不是外部压力，而是内部人对你「可预期性」的重新评估。",
    ],
    "family-wealth": [
        "古人分家之乱，多起于「均分」而非「不公」——均产削其志，择贤授其业。",
        "范仲淹设义庄养族而不养赖，是「授之以业，不授之以饱」的老例。",
        "家业传承的真问题不是分多少，而是下一代有没有「必须自己赢过一次」的机会。",
    ],
    "moral-trial": [
        "两难无全解，古人只问一句：此事过后，我还能不能坦然照镜。",
        "「义不苟合」者在当时多付出性命代价，但通鉴给他们的篇幅远厚于得利者。",
        "最危险的不是作恶，是把作恶重新命名——一旦改名，代价便不再被计入。",
    ],
    "adversity-recovery": [
        "苏秦「大困而归」后被全家耻笑，他没有辩解一句，只「闭室不出，出其书遍观之」"
        "——低谷期的第一资源是注意力，用来解释就没了。",
        "张仪遭辱后只问妻子一句「视吾舌尚在不」——跌到底时先确认"
        "「哪一样是别人拿不走的」，其余都可以重来。",
        "范雎装死、匿藏、更名张禄，孙膑借齐使者「窃载与之齐」"
        "——六人中没有一个在原处硬扛，全都先换了环境。",
        "孙膑不急于一战而等「批亢捣虚」，勾践「十年生聚」"
        "——时间本身是变量；急着翻本的人先出局。",
        "韩信说「杀之无名，故忍而就於此」——忍不是性格，是算过的账。",
        "勾践的卧薪尝胆不只是自苦：他同时「折节下贤人，厚遇宾客，振贫吊死，"
        "与百姓同其劳」——重建必须和复仇同时进行。",
    ],
}

# ── 风险提醒：本技能的诚实边界 ─────────────────────────────
RISKS = [
    "**史料的幸存者偏差**：能写进《通鉴》的多为帝王将相，且多为「已成败论」的案例；"
    "那些同样抉择却默默无闻的多数，史书不载。别把史书中的选择当成全部可能性。",
    "**古今结构不同**：古人的选项往往是生死、族灭级别的不可逆，现代人多为可修复的损失。"
    "类比可用，等强度套用会失真。",
    "**结果已知带来的后视镜偏误**：我们看到结局，容易把偶然读成必然。"
    "古人当时面对的信息集远小于我们事后掌握的。",
    "**原文未必载全**：通鉴记大事不记细故，很多决策过程、被否决的方案已散佚。"
    "本技能遇到「原文未载」处会明标，不做补写。",
    "**规律是概率不是定律**：上面的语料统计只描述本库文本的性质，"
    "编者按也只是人的判断。两者都不构成对你处境的预测。"
    "你的处境细节可以整体推翻某个规律的适用性。",
]


def fmt_scene_header(user_text, matched):
    L = ["## 一、抉择定位"]
    if matched:
        L.append("你的描述命中的决策内核（按相关度）：")
        for m in matched[:3]:
            s = SCENE_MAP[m["id"]]
            L.append("- **%s**（命中：%s）" % (s["name"], "、".join(m["hits"][:5])))
        L.append("")
        L.append("核心问题：**%s**" % SCENE_MAP[matched[0]["id"]]["question"])
        L.append("隐性代价主要考察方向：%s" % SCENE_MAP[matched[0]["id"]]["cost_axis"])
    else:
        L.append("未匹配到明确场景内核。建议：换用更具体的处境描述，或用 `--scene` 直接指定。")
    L.append("")
    return NL.join(L)


def fmt_cases(results, top):
    L = ["## 二、历史抉择案例推演"]
    L.append("> 以下原文均逐字取自《资治通鉴》《史记》《左传》语料库，未作改写。"
             "凡原文未载处，明确标注「原文未载」。")
    L.append("")
    for i, r in enumerate(results[:top], 1):
        scene = SCENE_MAP[r["scene"]]
        L.append(deduce.render_card(r, "", scene, rank=i))
    return NL.join(L)

def fmt_patterns(matched):
    """规律启发：语料统计（可复核）与编者按（人的判断）严格分开

    为什么必须分开：旧版把写死的格言标成「史书上反复出现的结构性倾向」，
    属未经测量的断言。统计数字可被 audit 复核，人的判断必须自报家门。
    """
    L = ["## 三、规律启发"]
    if not matched:
        L.append("无匹配场景，跳过。")
        return ""
    sid = matched[0]["id"]
    name = SCENE_MAP[sid]["name"]
    st = load_patterns().get(sid)

    if st:
        L.append("**① 语料统计（可复核，非对历史的总体推断）**")
        L.append("")
        L.append("样本：本库「%s」内核检索得分前 %d 的案例，自动抽取、非人工挑选。"
                 % (name, st["n_cases"]))
        L.append("- 案例文本中出现「进言未被采纳」信号：**%.1f%%**"
                 % st["rejected_rate"])
        L.append("- 出现「进言被采纳」信号：%.1f%%　｜　悬而未决：%.1f%%　｜　"
                 "未载明决断：%.1f%%"
                 % (st["accepted_rate"], st["hesitate_rate"],
                    st["unrecorded_rate"]))
        L.append("- 含「多方案争执」（≥2 个并列选项）：**%.1f%%**，"
                 "平均 %.2f 个并列选项"
                 % (st["debate_rate"], st["avg_proposals"]))
        if st.get("cost_dist"):
            tot = st["n_cases"]
            cs = "、".join("%s %d例(%.0f%%)" % (k, v, 100.0 * v / tot)
                           for k, v in list(st["cost_dist"].items())[:4])
            L.append("- 原文出现显性代价信号：%s" % cs)
        if st.get("sample_cites"):
            L.append("")
            L.append("抽样出处（供自行复核）：")
            for s in st["sample_cites"][:2]:
                L.append("  - %s（%s 类）" % (s["cite"], s["cost"]))
        L.append("")
        L.append("> 读这组数字时必须注意：它统计的是**文本性质**，不是历史事实。"
                 "「被拒率高」部分反映史书的取材偏好——"
                 "「不听劝而败亡」比「听劝而平安」更有戏剧性，更容易被写下来。")
        L.append("")

    if PATTERNS.get(sid):
        L.append("**② 编者按（人的判断，非统计结论，请自行斟酌）**")
        for p in PATTERNS[sid]:
            L.append("- %s" % p)
        L.append("")
    return NL.join(L)


def fmt_risks():
    L = ["## 四、风险提醒（本方法的边界）"]
    for i, r in enumerate(RISKS, 1):
        L.append("%d. %s" % (i, r))
    L.append("")
    L.append("---")
    L.append("")
    L.append("**下一步**：把上面的案例当作「信息」而非「答案」。"
             "真正要问的是——这些古人面对的约束里，哪一条与我最像，哪一条已彻底消失？"
             "已消失的约束，往往正是你今天可以放手一搏的地方。")
    return NL.join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?", default=None)
    ap.add_argument("--scene", default=None)
    ap.add_argument("--keywords", default="")
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--min-score", type=float, default=3.0)
    ap.add_argument("--list-scenes", action="store_true")
    ap.add_argument("--json", default=None, help="保存原始检索结果为 JSON")
    ap.add_argument("--md", default=None, help="保存 Markdown 推演报告")
    a = ap.parse_args()

    if a.list_scenes:
        print("可用决策内核（--scene <id>）：")
        for s in SCENES:
            print("  %-16s %-8s %s" % (s["id"], s["name"], s["question"]))
            print("      现代说法：%s" % "、".join(s["modern"][:10]))
            print("      代价考察：", s["cost_axis"])

    if not a.query and not a.scene:
        ap.print_help()
        return

    user_text = a.query or ""
    kws = [k.strip() for k in a.keywords.replace("，", " ").split() if k.strip()]
    out = retrieve(user_text, keywords=kws,
                   scene_ids=[a.scene] if a.scene else None,
                   top=a.top, min_score=a.min_score)

    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print("[saved] %s" % a.json)

    matched = out["matched_scenes"]
    md = []
    md.append("# 人生抉择推演：%s" % (user_text or a.scene))
    md.append("")
    md.append("> 依据：《资治通鉴》（文白对照）+《史记》（130篇）")
    md.append("        +《左传》（255年，隐公至哀公）原文语料库")
    md.append("")
    md.append(fmt_scene_header(user_text, matched))
    if out["results"]:
        md.append(fmt_cases(out["results"], a.top))
    else:
        md.append("## 二、历史抉择案例推演\n\n未检索到高质量匹配案例。"
                  "可尝试降低 --min-score，或补充 --keywords。\n")
    md.append(fmt_patterns(matched))
    md.append(fmt_risks())
    report = "\n".join(md)

    if a.md:
        with open(a.md, "w", encoding="utf-8") as f:
            f.write(report)
        print("[saved] %s" % a.md)

    print(report)


if __name__ == "__main__":
    main()
