# -*- coding: utf-8 -*-
"""
test_skill.py — 回归测试：场景识别 + 选项抽取 + 代价归属

跑法：python test_skill.py
退出码 0 = 全部通过；非 0 = 有失败项（打印明细）。
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import deduce  # noqa: E402
from retrieve import match_scenes, retrieve  # noqa: E402

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("%s %s%s" % ("[PASS]" if cond else "[FAIL]", name,
                       ("  → " + detail) if detail and not cond else ""))


# ── 1. 场景识别（从 eval_queries.json 加载真实风格问法）──
print("=" * 62)
print("1. 场景识别")
_qp = os.path.join(HERE, "eval_queries.json")
try:
    SCENE_CASES = [(q, e) for q, e in json.load(open(_qp, encoding="utf-8"))]
except Exception as ex:
    SCENE_CASES = []
    print("  [warn] 无法加载 eval_queries.json: %s" % ex)

hits, misses = 0, []
ambig = []
for q, expect in SCENE_CASES:
    m = match_scenes(q)
    top = m[0][1] if m else None
    exps = expect if isinstance(expect, list) else [expect]
    if top in exps:
        hits += 1
    else:
        misses.append((q, "|".join(exps), top))
    # 区分度：强信号场景数（>1 说明词表对这句话有歧义）
    strong = [x for x in m if x[0] >= 1.0]
    if len(strong) > 2:
        ambig.append((q, len(strong)))

n = len(SCENE_CASES)
print("  样本 %d 条（自拟标注，非独立人工验证）" % n)
for q, e, g in misses:
    print("  [错] %-24s 期望 %-18s 实际 %s" % (q[:22], e, g))
check("场景命中率 %.1f%% (%d/%d) 且 >= 70%%"
      % (100.0 * hits / max(1, n), hits, n), hits >= 0.7 * n)
print("  区分度：强信号场景 >2 个的查询 %d 条" % len(ambig))
for q, k in ambig[:6]:
    print("      歧义(%d): %s" % (k, q[:26]))

# ── 2. 选项抽取（多发言者）──
print("=" * 62)
print("2. 选项抽取")
t1 = '智伯请地于韩康子，康子欲弗与。段规曰：“智伯好利而愎，不与，将伐我；不如与之。”康子曰：“善。”'
cs = deduce.extract_choices(t1)
speakers = [c["speaker"] for c in cs]
kinds = [c["kind"] for c in cs]
check("多发言者：段规+康子均抽出", len(cs) == 2 and "段规" in speakers and "康子" in speakers,
      str(speakers))
check("表态识别：康子「善」= assent", "assent" in kinds, str(kinds))

t2 = '上敕李光弼等进取东京。光弼奏称：“贼锋尚锐，未可轻进。”'
cs2 = deduce.extract_choices(t2)
check("非「曰」标记（奏称）", any("光弼" in c["speaker"] for c in cs2),
      str([c["speaker"] for c in cs2]))

t3 = '邓潜之谏曰：“国家安危，在此一举。”无忌不听。'
cs3 = deduce.extract_choices(t3)
check("嵌套引语不误切", any(c["speaker"] == "邓潜之" for c in cs3),
      str([c["speaker"] for c in cs3]))

# 说话人剥离：礼节词 / 动宾结构 / 副词
SPK = [
    ('种顿首言曰：“愿大王赦句践之罪。”', "种", "礼节词：种顿首言→种"),
    ('嚭因说吴王曰：“越以服为臣，若将赦之，此国之利也。”', "嚭",
     "动宾：嚭因说吴王→嚭（非吴王）"),
    ('子胥进谏曰：“今不灭越，后必悔之。”', "子胥", "连动：子胥进谏→子胥"),
    ('富辰谏曰：“凡我周之东徙。”', "富辰", "常规：富辰谏→富辰"),
    ('苏代乃谓齐王曰：“今秦之伐赵也。”', "苏代", "副词尾：苏代乃→苏代"),
]
for text, want, label in SPK:
    got = [c["speaker"] for c in deduce.extract_choices(text)]
    check("说话人 %s" % label, want in got, str(got))

cs4 = deduce.extract_choices('乃曰：“陛下素骄淮南王。”')
check("副词不当作人名（乃）", cs4 and cs4[0]["speaker"].startswith("承前"),
      str([c["speaker"] for c in cs4]))

# ── 3. 决断判定 ──
print("=" * 62)
print("3. 决断判定")
check("拒绝信号：弗听", "拒绝" in deduce.detect_decision("智果曰：\"不如宵也。\"弗听。"))
check("采纳信号：用之", "采纳" in deduce.detect_decision("上以为然，乃用之。"))
check("无信号 → 原文未载", "未载" in deduce.detect_decision("黄帝者，少典之子。"))

# ── 4. 代价归属（不带歧义误报）──
print("=" * 62)
print("4. 代价归属")
c_ok = deduce.analyze_costs("龟自知必为冀所害，不食七日而死。")
check("真代价：「死」被捕获", "身亡" in c_ok)
c_bad = deduce.analyze_costs("光禄勋陈蕃上疏谏曰：“今失其劝种之时，而令给驱禽除路之役。”")
check("歧义：「驱禽」不计为丧师", "丧师" not in c_bad, str(list(c_bad.keys())))
c_bad2 = deduce.analyze_costs("庆幸得待罪丞相，罢驽无以辅治。")
check("歧义：「罢驽」不计为失位", "失位" not in c_bad2, str(list(c_bad2.keys())))

# ── 5. 端到端检索 ──
print("=" * 62)
print("5. 端到端检索")
for q in ["该不该向领导提出反对意见", "要不要跟竞争对手打价格战"]:
    out = retrieve(q, top=3, min_score=3.0)
    rs = out["results"]
    check("检索有结果: %s" % q[:14], len(rs) >= 2, "n=%d" % len(rs))
    if rs:
        # 验证引用真实存在
        check("引用格式正确: %s" % rs[0]["cite"][:22],
              "《资治通鉴》" in rs[0]["cite"] or "《史记》" in rs[0]["cite"]
              or "《左传》" in rs[0]["cite"])

print("=" * 62)
print("通过 %d / 失败 %d" % (len(PASS), len(FAIL)))
if FAIL:
    print("失败项：")
    for f in FAIL:
        print("  -", f)
sys.exit(1 if FAIL else 0)