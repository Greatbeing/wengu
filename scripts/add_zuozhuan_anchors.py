# -*- coding: utf-8 -*-
"""
add_zuozhuan_anchors.py — 给 13 个抉择内核补《左传》专有词锚点

## 为什么必须补（不补的话左传等于不存在）

检索器的候选集来自 `scene["classical"]` 词的倒排并集。现有词表是围着
《资治通鉴》《史记》的官制词汇建的：「任之/信之/委任/奏除/超迁」——
这是秦汉以后的语言。左传的用人抉择发生在另一个词体系里。

实测缺口（2026-09-22）：
    employ-person   左传进候选 136/236
    successor       左传进候选  59/236
而子产在左传语料出现 155 次、叔向 99 次、宣子 134 次，
这些名字一个都不在古典词表里 —— 所以左传检索不到。

## 补什么：人物/事件锚点，不是翻译现代词

每个人名都先在语料里核实过语境，按真实抉择属性归类，不臆断：

  里克    「里克谏曰：大子奉冢祀…非大子之事也」      → remonstrate 谏诤
  骊姬    「骊姬嬖，欲立其子，赂外嬖梁五」            → successor 夺嫡
  荀息    「不济，则以死继之」                        → moral-trial 殉节
  介之推  「不言禄，禄亦弗及」「窃人之财犹谓之盗」    → stay-or-go 功成身退
  寺人披  「蒲城之役，君命一宿，女即至」              → remonstrate 进言
  祁奚    举善、韩厥言成季之勋无后                    → employ-person 举贤
  赵盾    「使能，国之利也」                          → employ-person 用人

## 修复的命令

python add_zuozhuan_anchors.py && python build_index.py

运行后必须 build_index：新词不建索引则倒排召不回，等于白加。

运行：python add_zuozhuan_anchors.py
"""
import ast
import os

HERE = os.path.dirname(os.path.abspath(__file__))
NL = chr(10)

# 每个内核补的左传专有词（已在语料核实语境）
ANCHORS = {
    "remonstrate": [
        "里克", "寺人披", "宫之奇", "荀首", "先轸", "叔仲", "士季",
        "裹粮坐甲", "辞服", "再发", "骤谏", "骤死",
    ],
    "successor": [
        "骊姬", "申生", "奚齐", "卓子", "夷吾", "重耳", "世子", "大子",
        "冢子", "冢嗣", "宗子", "余子", "嬖子", "外嬖", "二五",
    ],
    "moral-trial": [
        "荀息", "以死继之", "忠贞", "股肱之力", "死君", "殉", "伏死",
        "鉏麑", "触槐", "董狐", "太史书", "赵盾弑其君",
    ],
    "stay-or-go": [
        "介之推", "不言禄", "禄亦弗及", "贪天之功", "从亡", "赏从亡者",
        "去之", "出奔", "越垣", "徇曰",
    ],
    "employ-person": [
        "祁奚", "韩厥", "叔向", "子产", "宣子", "赵武", "先轸", "阳处父",
        "举善", "举不失职", "使能", "赵衰", "胥臣", "魏绛", "祁午",
    ],
    "choose-side": [
        "寺人披", "重耳", "出奔翟", "蒲城之役", "一国三公", "吾谁适从",
        "吕郤", "怀公", "惠公", "文公", "襄公",
    ],
    "endure": [
        "介之推", "不言禄", "禄亦弗及", "贪天之功", "隐忍", "贪天",
    ],
    "faith-or-interest": [
        "宫之奇", "假道于虞", "辅车相依", "唇亡齿寒", "贪人败类",
        "虞公", "虢", "荀息", "外府",
    ],
    "risk-return": [
        "宫之奇", "唇亡齿寒", "假道", "蠢兹有苗", "一薰一莸",
        "专之渝", "攘公之羭", "筮短龟长",
    ],
    "family-wealth": [
        "赵庄姬", "原屏", "赵同", "赵括", "赵婴", "谮之于晋侯",
        "栾郤", "武从姬氏",
    ],
    "timing": [
        "宫之奇", "再斯可矣", "亡不能厚", "将寻师焉", "三年", "寻师",
    ],
    "war-or-peace": [
        "城濮", "邲", "之师", "观兵", "按兵", "退三舍", "避其锋芒",
    ],
    "adversity-recovery": [
        "重耳", "出奔翟", "从亡", "介之推", "越垣", "逾垣而走",
        "之齐", "之秦", "之楚", "十九年",
    ],
}

# 不能与现有词重复，也不能与已存在的词互为子串造成重复计分
# （score_unit 已对完整词做过长度去重，这里只避完全重复）


def main():
    fp = os.path.join(HERE, "scenes.py")
    with open(fp, encoding="utf-8") as f:
        t = f.read()

    if "左传专有词锚点" in t:
        print("scenes.py 已含左传锚点，跳过")
    else:
        n_total = 0
        for sid, words in ANCHORS.items():
            # 定位该场景的 classical 列表
            key = '"id": "%s"' % sid
            k = t.find(key)
            if k < 0:
                print("!! 找不到场景 %s" % sid)
                continue
            # 找该场景块内的 "classical": [
            ks = t.find('"classical": [', k)
            if ks < 0:
                print("!! %s 无 classical" % sid)
                continue
            ke = t.find("]", ks)
            old = t[ks + len('"classical": ['):ke].rstrip()
            if old.endswith(","):
                old = old[:-1]
            new_words = [w for w in words if w not in old]
            if not new_words:
                continue
            add = "," + NL + "        " + ",".join('"%s"' % w for w in new_words)
            t = t[:ks + len('"classical": [') + len(
                old)] + add + t[ke:]
            n_total += len(new_words)
            print("  %-20s +%d 词" % (sid, len(new_words)))
        t = t.replace("import json" if "import json" in t else "import re",
                      "import re  # noqa: F401" + NL + "import json  # noqa: F401", 1)
        # 加注释标记
        t = t.replace("# ── 场景定义",
                      "# 左传专有词锚点（2026-09-22 补）：见 add_zuozhuan_anchors.py" + NL
                      + "# ── 场景定义", 1)
        try:
            ast.parse(t)
        except SyntaxError as e:
            print("!! scenes.py 语法错误: %s" % e)
            return
        with open(fp, "w", encoding="utf-8") as f:
            f.write(t)
        print()
        print("共补充 %d 个左传专有词" % n_total)


if __name__ == "__main__":
    main()
