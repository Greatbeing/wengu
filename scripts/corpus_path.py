# -*- coding: utf-8 -*-
"""
corpus_path.py — 语料目录定位（让脚本脱离开发目录也能跑）

优先级：
  1. 环境变量 WENGU_CORPUS
  2. 脚本上级目录的 corpus/（开发布局：<root>/scripts/ + <root>/corpus/）
  3. 脚本同级 corpus/
  4. 默认安装位置 D:\\HermesOutput\\wengu\\corpus
  5. ~/AppData/Local/hermes/wengu-corpus

判定标准：目录内存在 index.json（建好索引）或 zztj_units.jsonl（已解析语料）。
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULT_CORPUS = r"D:\HermesOutput\wengu\corpus"

MARKERS = ("index.json", "zztj_units.jsonl", "shiji_units.jsonl",
           "zuozhuan_units.jsonl")


def candidates():
    out = []
    env = os.environ.get("WENGU_CORPUS")
    if env:
        out.append(env)
    out.append(os.path.normpath(os.path.join(HERE, "..", "corpus")))
    out.append(os.path.join(HERE, "corpus"))
    out.append(DEFAULT_CORPUS)
    out.append(os.path.join(os.path.expanduser("~"), "AppData", "Local",
                            "hermes", "wengu-corpus"))
    return out


def resolve_corpus(create=None):
    """返回可用语料目录；找不到已存在的则返回 create（或默认位置）。"""
    for c in candidates():
        if c and any(os.path.exists(os.path.join(c, m)) for m in MARKERS):
            return c
    return create or DEFAULT_CORPUS


if __name__ == "__main__":
    print(resolve_corpus())