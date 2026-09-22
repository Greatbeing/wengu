# -*- coding: utf-8 -*-
"""
build_corpus.py — 把《资治通鉴》《史记》原文解析为可检索的段落单元（JSONL）

产出：
  corpus/zztj_units.jsonl   — 通鉴每卷按 [编号] 切分为段（原文+白话+出处）
  corpus/shiji_units.jsonl  — 史记按卷切分为段（原文+出处）

格式事实（已逐行验证）：
  - 通鉴 JY0284 库 chapters/*.md 为「严格行级交替」：偶数行=古文原文，奇数行=白话译文；
    首两行为「时间原文」「时间译文」；段落以 [编号] 起始，同段多行原文与多行译文交替。
  - 史记 daizhigev20 库 shiji.txt 前 130 行为目录，正文从「卷一 五帝本纪第一」起，
    卷标题格式「卷N 篇名第M」；正文为「一行一句」，无空行分段。

用法：python build_corpus.py   （仅标准库）
"""
import json
import os
import re
import glob

HERE = os.path.dirname(os.path.abspath(__file__))
from corpus_path import resolve_corpus  # noqa: E402
from zuozhuan_parse import parse_zuozhuan  # noqa: E402
CORPUS = resolve_corpus()
ZZTJ_DIR = os.path.join(CORPUS, "zizhitongjian-main", "chapters")
SHIJI_TXT = os.path.join(CORPUS, "shiji.txt")

VOL_RE = re.compile(r"^(\d+)_资.通.第([一二三四五六七八九十百零]+)卷\((.+)\)\.md$")
CN_TIME_RE = re.compile(r"^[\u4e00-\u9fa5]+纪[一二三四五六七八九十]+\s")


def cn2int(cn: str) -> int:
    digits = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9}
    # 「零」只作占位（一百零一 / 二百零九），去掉后按普通中文数字规则处理
    cn = cn.replace("零", "")
    if not cn:
        return 0
    if cn == "十":
        return 10
    if "百" in cn:
        parts = cn.split("百")
        left = digits.get(parts[0], 1) if parts[0] else 1
        rest = parts[1] if len(parts) > 1 else ""
        return left * 100 + (cn2int(rest) if rest else 0)
    if "十" in cn:
        parts = cn.split("十")
        left = digits.get(parts[0], 1) if parts[0] else 1
        right = digits.get(parts[1], 0) if len(parts) > 1 and parts[1] else 0
        return left * 10 + right
    return digits.get(cn, 0)


def parse_zztj() -> list:
    units = []
    files = sorted(glob.glob(os.path.join(ZZTJ_DIR, "*.md")))
    for fp in files:
        m = VOL_RE.match(os.path.basename(fp))
        if not m:
            continue
        juan = cn2int(m.group(2))
        reign = m.group(3)
        raw = open(fp, encoding="utf-8").read()
        body = re.sub(r"^资治通鉴第[^\)\n]*\)\s*\n", "", raw, count=1)
        lines = [l.strip().lstrip("\u3000").strip()
                 for l in body.split("\n")]
        lines = [l for l in lines if l]
        if not lines:
            continue

        # 行级交替：i 偶=原文，i 奇=译文。前两行是时间行。
        cur_time = ""
        cur_no = None
        orig_lines, tran_lines = [], []

        def flush():
            nonlocal cur_no, orig_lines, tran_lines
            if cur_no is None:
                return
            orig = "\n".join(orig_lines).strip()
            tran = "\n".join(tran_lines).strip()
            if len(orig) >= 20:
                units.append({
                    "source": "资治通鉴",
                    "juan": juan,
                    "reign": reign,
                    "seq": cur_no,
                    "time": cur_time,
                    "text": orig,
                    "translation": tran,
                    "cite": "《资治通鉴》卷%d（%s）[%d]" % (juan, reign, cur_no),
                    "chars": len(orig),
                })
            cur_no, orig_lines, tran_lines = None, [], []

        for i, l in enumerate(lines):
            if i == 0:
                cur_time = l          # 时间原文
                continue
            if i == 1:
                cur_time = cur_time + " / " + l   # 时间白话
                continue
            is_orig = (i % 2 == 0)    # 0,2,4... 原文；1,3,5... 译文（含前两行时间）
            mn = re.match(r"^\[(\d+)\](.*)$", l)
            if mn and is_orig:
                flush()
                cur_no = int(mn.group(1))
                rest = mn.group(2).strip()
                if rest:
                    orig_lines.append(rest)
            elif is_orig:
                if cur_no is None:
                    cur_no = 0
                orig_lines.append(l)
            else:
                # 译文行可能也带 [N] 前缀
                t = re.sub(r"^\[\d+\]", "", l).strip()
                if t:
                    tran_lines.append(t)
        flush()
    return units


SHIJI_VOL_RE = re.compile(r"^卷([一二三四五六七八九十百]+)\s+(.+?)(第[一二三四五六七八九十百]+)\s*$")
SENT_END = "。！？；"


def parse_shiji() -> list:
    t = open(SHIJI_TXT, encoding="utf-8").read()
    lines = t.split("\n")
    start = 0
    for i, l in enumerate(lines):
        if l.strip() == "卷一 五帝本纪第一":
            start = i
            break
    units = []
    cur_title, cur_juan = "", 0
    buf = []

    def flush():
        nonlocal buf
        if not buf:
            return
        text = "".join(buf)
        # 按句末标点切分为「语义段」，每段约 60-200 字
        segs = re.split(r"(?<=[。！？])", text)
        chunk, chunk_len = [], 0
        for s in segs:
            s = s.strip()
            if not s:
                continue
            chunk.append(s)
            chunk_len += len(s)
            if chunk_len >= 80:
                para = "".join(chunk).strip()
                if len(para) >= 30:
                    units.append({
                        "source": "史记",
                        "juan": cur_juan,
                        "title": cur_title,
                        "text": para,
                        "translation": "",
                        "cite": "《史记》卷%d %s" % (cur_juan, cur_title),
                        "chars": len(para),
                    })
                chunk, chunk_len = [], 0
        if chunk:
            para = "".join(chunk).strip()
            if len(para) >= 30:
                units.append({
                    "source": "史记",
                    "juan": cur_juan,
                    "title": cur_title,
                    "text": para,
                    "translation": "",
                    "cite": "《史记》卷%d %s" % (cur_juan, cur_title),
                    "chars": len(para),
                })
        buf = []

    for l in lines[start:]:
        ls = l.strip()
        m = SHIJI_VOL_RE.match(ls)
        if m:
            flush()
            cur_juan = cn2int(m.group(1))
            cur_title = m.group(2)
            continue
        buf.append(l)
    flush()
    return units


CLS_CHARS = "之者也矣曰其於而乃是以焉乎哉夫"
MOD_CHARS = "的了是我你他这那们很就都"


def _cls(t):
    """粗略古典度：古字计正分，现代字重罚（现代字几乎不出现在文言里）"""
    c = sum(t.count(ch) for ch in CLS_CHARS)
    m = sum(t.count(ch) for ch in MOD_CHARS)
    return (c - 4 * m) / max(1, len(t))


def filter_broken(units):
    """质量闸门：剔除原文/译文错位分配的卷

    判据：同一卷内「译文古典度 − 原文古典度」的中位数为正，
          说明交替结构不成立（该卷是占位稿，或格式与其余卷不同）。
    为什么必须剔除而不是照单全收：错位的卷会把白话当古文引用，
          在推演卡里以「原文出处（逐字）」呈现——那等于伪造史料。
    返回 (干净单元, {卷号: 中位差值})。
    """
    import statistics
    by = {}
    for u in units:
        by.setdefault(u["juan"], []).append(u)
    clean, bad = [], {}
    for j in sorted(by):
        us = by[j]
        # 单元级过滤一：占位符（[todo] 等未完成标记，不是史料内容）
        us = [u for u in us if "todo" not in u["text"].lower()]
        # 单元级过滤二：单条即错位（译文明显比原文更「古」，留 0.5 安全边际）
        keep = []
        for u in us:
            if u.get("translation"):
                d = _cls(u["translation"]) - _cls(u["text"])
                if d > 0.5:
                    bad.setdefault(j, 0)
                    continue
            keep.append(u)
        us = keep
        ds = [_cls(u["translation"]) - _cls(u["text"])
              for u in us if u.get("translation")]
        if len(ds) >= 5:
            med = statistics.median(ds)
            if med > 0:
                bad[j] = round(med, 4)
                continue
        clean.extend(us)
    return clean, bad


def main():
    print("[1/3] 解析资治通鉴 ...")
    zz = parse_zztj()
    zz, broken = filter_broken(zz)
    with open(os.path.join(CORPUS, "zztj_units.jsonl"), "w", encoding="utf-8") as f:
        for u in zz:
            f.write(json.dumps(u, ensure_ascii=False) + "\n")
    print("      通鉴段落单元: %d" % len(zz))
    # 数据质量报告：被剔除的卷必须留痕，不允许静默丢数据
    qp = os.path.join(CORPUS, "data_quality.json")
    with open(qp, "w", encoding="utf-8") as f:
        json.dump({"dropped_juan": broken,
                   "reason": "译文整体比原文更『古』，说明原文/译文错位分配，"
                             "或该卷为不完整占位稿（含 [todo]）",
                   "kept_units": len(zz)}, f, ensure_ascii=False, indent=2)
    if broken:
        print("      ⚠ 剔除结构异常卷 %d 个: %s" % (len(broken), sorted(broken)))
        print("        详见 %s" % qp)

    print("[2/3] 解析史记 ...")
    sj = parse_shiji()
    with open(os.path.join(CORPUS, "shiji_units.jsonl"), "w", encoding="utf-8") as f:
        for u in sj:
            f.write(json.dumps(u, ensure_ascii=False) + "\n")
    print("      史记段落单元: %d" % len(sj))

    print("[3/3] 解析左传 ...")
    zz2 = parse_zuozhuan()
    with open(os.path.join(CORPUS, "zuozhuan_units.jsonl"), "w", encoding="utf-8") as f:
        for u in zz2:
            f.write(json.dumps(u, ensure_ascii=False) + "\n")
    print("      左传段落单元: %d" % len(zz2))

    zchars = sum(u["chars"] for u in zz)
    schars = sum(u["chars"] for u in sj)
    zt = sum(1 for u in zz if u["translation"])
    print("\n通鉴字数(段): %s   其中带白话译文: %d (%.1f%%)"
          % ("{:,}".format(zchars), zt, 100.0 * zt / max(1, len(zz))))
    print("史记字数(段): %s" % "{:,}".format(schars))
    z2chars = sum(u["chars"] for u in zz2)
    print("左传字数(段): %s" % "{:,}".format(z2chars))
    print("输出目录: %s" % CORPUS)


if __name__ == "__main__":
    main()
