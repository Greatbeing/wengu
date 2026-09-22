# -*- coding: utf-8 -*-
"""
zuozhuan_parse.py — 《左传》解析（独立模块）

源：daizhigev20 儒藏/春秋/春秋左传.txt（简体，含【经】【传】分标，255 年全覆盖）

结构：
    卷首目录（12 公）→ 每公一节 → 节内以 ◇X公Y年 标记年份 → 【经】+【传】

处理要点：
  1. 卷首目录：正文起于「隐公（元年～十一年）」第二次出现处
  2. 相邻公标题混入：源文件在每公结尾会重复下一公的目录标题行，
     表现为形如「X公（元年～N年）」的孤立标题，必须剔除
  3. 该源无白话译文，translation 留空（与《史记》同等处理）
  4. 长年（>1000 字）按段落切分，出处保持一致以保证引用可核对

单独成模块的原因：解析逻辑有较多反斜杠，写在独立文件比 shell heredoc
里拼接安全（heredoc 会吃掉一层反斜杠，本会话已踩过多次）。
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
import sys
sys.path.insert(0, HERE)
from corpus_path import resolve_corpus  # noqa: E402

CORPUS = resolve_corpus()
ZUO_TXT = os.path.join(CORPUS, "zuozhuan_raw.txt")

HDR = "隐公（元年～十一年）"   # 目录与正文共用同一节标题
NL = chr(10)
# 公标题行形如「桓公（元年～十八年）」——孤立出现即目录残留
DUKE_HDR_RE = re.compile(r"^(\S{1,2}公)（元年[～~](\S+)年）$")


def _clean(year_name, text):
    """剔除混入正文的公目录标题行与【经】部编年流水账

    【经】是《春秋》的编年简目（「春王正月。三月，公及邾仪父盟于蔑。」），
    是年鉴不是抉择叙事——检索时它会把「日食」「大水」「崔杼伐莒」这类
    无决策内容的条目顶到前列，挤掉真正的「国君听谏→决策→后果」现场。
    本技能只做抉择推演，故【经】整体剔除，只保留【传】。
    """
    out = []
    for ln in text.split(NL):
        s = ln.strip()
        m = DUKE_HDR_RE.match(s)
        if m:
            continue
        # 【经】部整块剔除：从「【经】」标记起，到下一个「【传】」标记前
        out.append(ln)
    txt = NL.join(out)
    if "【经】" in txt:
        # 只保留第一个【传】及其后
        k = txt.find("【传】")
        if k >= 0:
            txt = txt[k:]
        else:
            txt = txt.replace("【经】", "")
    return txt


def _chunks(text, limit=1000, target=600):
    """过长文本按段落切分，控制在 target 字左右，保持叙事连续"""
    if len(text) <= limit:
        return [text]
    out, buf = [], ""
    for para in re.split(r"\n+", text):
        para = para.strip()
        if not para:
            continue
        buf = (buf + NL + para) if buf else para
        if len(buf) >= target:
            out.append(buf)
            buf = ""
    if buf:
        out.append(buf)
    return out


def parse_zuozhuan(path=None):
    """返回左传事件单元列表（与其它语料同构的 dict）"""
    fp = path or ZUO_TXT
    if not os.path.exists(fp):
        return []
    raw = open(fp, encoding="utf-8").read()

    # 跳过卷首目录：正文起于节标题第二次出现处
    i1 = raw.find(HDR)
    i2 = raw.find(HDR, i1 + 1) if i1 >= 0 else -1
    body = raw[i2:] if i2 > 0 else raw

    parts = re.split(r"◇", body)
    preamble, year_segs = parts[0], parts[1:]
    units = []

    def push(duke, year, text):
        text = _clean(year, text).strip()
        if len(text) < 40:
            return
        cite = ("《左传》%s%s" % (duke, year)) if year else ("《左传》%s（序）" % duke)
        chs = _chunks(text)
        for k, ch in enumerate(chs):
            units.append({
                "source": "左传",
                "duke": duke,
                "year": year,
                "juan": 0,
                "title": "%s%s" % (duke, year or ""),
                "text": ch,
                "translation": "",
                "cite": cite + ("（第%d段）" % (k + 1) if len(chs) > 1 else ""),
                "chars": len(ch),
            })

    # 序言（惠公、隐公、桓公出身）
    push("隐公", "", preamble)
    for seg in year_segs:
        head = re.match(r"([^\n【]{2,10})", seg)
        name = head.group(1).strip() if head else ""
        dm = re.match(r"(\S+?公)(\S+)", name)
        duke, year = (dm.group(1), dm.group(2)) if dm else ("", name)
        push(duke, year, seg[len(name):] if name else seg)
    return units


def main():
    us = parse_zuozhuan()
    print("左传单元: %d" % len(us))
    if us:
        print("覆盖年数: %d" % len({u["title"] for u in us}))
        tiny = [u for u in us if u["chars"] < 120]
        print("碎片(<120字): %d (%.1f%%)" % (len(tiny), 100.0 * len(tiny) / len(us)))
        stray = [u for u in us if "元年～" in u["text"]]
        print("公标题残留: %d" % len(stray))
        print("首条: %s | %s" % (us[0]["cite"], us[0]["text"][:50]))
        print("末条: %s | %s" % (us[-1]["cite"], us[-1]["text"][:50]))


if __name__ == "__main__":
    main()
