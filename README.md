# 问古 (wengu)

带一个现代抉择去问古人。

输入「我该不该劝领导」「合伙人要散伙怎么办」，输出《资治通鉴》《史记》《左传》中
场景相似的**历史抉择案例**：古人当时有哪些选项、各自结果、付出了什么代价，
全部逐字标注原文出处。

不是给你答案，是把两千年前做过同样选择的人当时的处境摊开给你看。

---

## 能问什么

13 个决策内核：

| 内核 | 触发词（部分） |
|---|---|
| 进谏 | 劝谏、忠言逆耳、该不该说 |
| 求退 | 功成身退、急流勇退、交权 |
| 站队 | 选边、党争、跟谁 |
| 用忍 | 忍辱、胯下、卧薪尝胆 |
| 破局 | 困兽、绝地、翻盘 |
| 止损 | 割肉、沉没、认赔 |
| 固权 | 集权、削藩、控制 |
| 择嗣 | 立贤立长、接班、传位 |
| 伐交 | 联吴抗曹、合纵连横 |
| 择时 | 时机、过早、过晚 |
| 权衡 | 风险收益、值不值 |
| 分化 | 敌人的敌人、逐个击破 |
| 翻身 | 困厄、低谷、翻盘 |

完整触发词见 `references/scenes.md`。

---

## 输出结构（必守）

1. **抉择定位** — 命中哪个决策内核
2. **历史抉择案例** — 每案例四段：①原文出处（逐字）②古人当时的选项 ③结果判断 ④代价分层（显性/隐性）
3. **规律启发** — 该内核在语料中反复出现的结构性倾向，由 `derive_patterns.py` 从语料统计导出
4. **风险提醒** — 方法边界（幸存者偏差、古今结构差异、通鉴不记细故）

## 诚实铁律

- **绝不虚构原文**：所有引用逐字取自语料，可用 grep 复核（`audit_skill.py` B 项实测 84/84 = 100%）
- **原文未载就写「原文未载」**：不补写，不把推测写成史实
- **「原文可见」与「推演」分开标注**
- **多派并列**：同一案例有不同解读时并列呈现，不钦定一派
- **代价归属存疑时附原句**：让读者自己判断，不替古人下结论

---

## 用法

```bash
cd scripts
python tuiliyan.py "我该不该向领导提出反对意见" --top 3 --md out.md
python tuiliyan.py --list-scenes        # 列出 13 个决策内核
python test_skill.py                    # 回归测试（当前 21/21）
python audit_skill.py                   # 实证审计
```

依赖 Python 3.8+，**仅用标准库**，无第三方依赖。

---

## 语料库

语料随本仓库提交，位于 `corpus/`（403 文件，约 136MB）。

| 库 | 规模 | 来源 |
|---|---|---|
| 资治通鉴 | 294 卷，文白对照 | [JY0284/zizhitongjian](https://github.com/JY0284/zizhitongjian) |
| 史记 | 130 篇 | [garychowcmu/daizhigev20](https://github.com/garychowcmu/daizhigev20) |
| 左传 | 12 公 255 年，仅【传】 | 同上 |

解析为事件单元后聚段，共 **6,707 个事件单元**（通鉴 4,320 + 史记 2,151 + 左传 220），
倒排索引 427 词。

### 从零重建（可选）

```bash
cd corpus/zizhitongjian-main && git sparse-checkout init --cone \
  && git sparse-checkout set chapters data.json adapted_book.json
cd ../../scripts
python build_corpus.py     # 原始语料 → *_units.jsonl
python build_index.py      # *_units.jsonl → index.json
```

---

## 实测指标

`audit_skill.py` 输出（跑 `python audit_skill.py` 可复现）：

| 项 | 值 |
|---|---|
| A 语料完整性 | 通鉴 292/294 卷（3 卷已被剔除，见 known-issues） |
| B 引用保真 | **84/84 = 100%**（三点指纹，逐字比对源文件） |
| C1 场景识别 | 50/51 = 98.0%（自拟标注，非独立人工验证） |
| C4 检索一致性 | 51/51 = 100% |
| C5 案例内核命中 | 50/51 = 98.0% |
| C2 空结果查询 | 0 |
| C3 top-3 平均并列选项 | 4.15 |

已知边界、踩坑记录、放弃的设计决策见 `references/known-issues.md`。

---

## 实现要点

| 文件 | 作用 |
|---|---|
| `scenes.py` | 13 个决策内核 + 各库专有锚点词 |
| `retrieve.py` | 三源聚段 + IDF 倒排检索 + 8 项打分 |
| `deduce.py` | 拆选项、判结果、挖显性/隐性代价 |
| `build_corpus.py` | 三库解析（含《左传》独立解析器逻辑） |
| `build_index.py` | 倒排索引 + IDF 构建 |
| `derive_patterns.py` | 规律从语料统计导出（非手写） |
| `audit_skill.py` | 实证审计：完整性 / 保真 / 检索 / 覆盖 |
| `test_skill.py` | 21 项回归测试 |
| `eval_queries.json` | 51 条带标签测评集 |

详见 `references/impl.md`。

---

## 许可与归属

- 本仓库自有代码（`scripts/`、`SKILL.md`、`references/`、`samples/`）：**MIT**
- `corpus/zizhitongjian-main/` 来自 [JY0284/zizhitongjian](https://github.com/JY0284/zizhitongjian)，**GPL-3.0**，其 LICENSE 原样保留于 `corpus/zizhitongjian-main/LICENSE`
- 《史记》《左传》语料来自 [garychowcmu/daizhigev20](https://github.com/garychowcmu/daizhigev20)，**该仓库未声明许可**（`license: null`，`使用须知.md` 亦无授权条款）
- 《资治通鉴》原文为公有领域（1084 年成书），GPL-3.0 仅覆盖 JY0284 的白话译文与结构化数据

> **法律提示**：`daizhigev20` 未声明许可即默认保留全部权利，这是本仓库**明确的法律风险点**，
> 风险等级高于 GPL-3.0 部分。GPL 与无许可部分的边界判定属法律问题，本仓库不提供法律意见。
> 如做商业分发，建议自行评估或替换为明确许可的语料源。
