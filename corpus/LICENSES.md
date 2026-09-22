# 语料来源与许可 / Corpus Provenance & Licensing

本目录内容**不受**仓库根目录 `LICENSE`（MIT）覆盖。逐项如下。

---

## 一、自有创作（MIT）

| 路径 | 许可 |
|---|---|
| `scripts/` | MIT |
| `SKILL.md`、`references/`、`samples/`、`README.md` | MIT |

## 二、第三方文本与数据

| 路径 | 来源 | 许可状态 |
|---|---|---|
| `corpus/zizhitongjian-main/chapters/`（294 卷） | [JY0284/zizhitongjian](https://github.com/JY0284/zizhitongjian) | **GPL-3.0**，逐字复制，未修改 |
| `corpus/zizhitongjian-main/LICENSE` | 同上 | GPL-3.0 全文，原样保留 |
| `corpus/zizhitongjian-main/README.md` | 同上 | GPL-3.0，原样保留（上游自述文件） |
| `corpus/shiji.txt` | [garychowcmu/daizhigev20](https://github.com/garychowcmu/daizhigev20) | **上游未声明许可**（`license: null`），底本《史记》为公有领域 |
| `corpus/zuozhuan_raw.txt` | 同上 | **上游未声明许可**，底本《左传》为公有领域 |

## 三、本项目的衍生作品 — 许可证跟随上游

以下文件由本项目的解析脚本从上述语料生成，**属于 GPL-3.0 衍生作品**，
依 GPL-3.0 第 5 条以 **GPL-3.0** 授权：

| 路径 | 由何生成 | 许可 |
|---|---|---|
| `corpus/zztj_units.jsonl` | 解析 `zizhitongjian-main/chapters/` | **GPL-3.0** |
| `corpus/shiji_units.jsonl` | 解析 `shiji.txt` | 见第四节 |
| `corpus/zuozhuan_units.jsonl` | 解析 `zuozhuan_raw.txt` | 见第四节 |
| `corpus/index.json` | 构建自上述三份 units | **GPL-3.0**（含 GPL 成分） |
| `corpus/patterns.json` | 统计自上述 units | **GPL-3.0**（含 GPL 成分） |
| `corpus/data_quality.json` | 统计自上述 units | **GPL-3.0**（含 GPL 成分） |

---

## 四、GPL-3.0 合规声明（第 5(a) 条）

> **本仓库包含对 JY0284/zizhitongjian 的修改。修改日期：2026-09。**

修改方式：

1. **解析与结构化** — 将 `chapters/*.md` 的行级「原文／白话」交替文本切分为
   带 `juan` / `seq` / `text` / `translation` / `cite` 字段的 JSONL 单元
   （`scripts/build_corpus.py`）。
2. **删减** — 未使用其中约 47 MB 的代码、notebook、可视化与派生数据
   （`data.json`、`adapted_book.json`、`model/`、`visualization/` 等），
   本仓库不再分发这些部分；仅保留 `chapters/` 与 `LICENSE`、`README.md`。
3. **合并与索引** — 与《史记》《左传》单元合并为 6,707 个事件单元，
   构建倒排索引与 IDF 表（`scripts/build_index.py`）。

上述修改产物（`zztj_units.jsonl`、`index.json` 等）按 GPL-3.0 分发。
**本项目的自有脚本（`scripts/`）不衍生自上游代码，保持 MIT。**

## 五、关于 `daizhigev20` 语料的说明

`shiji.txt` 与 `zuozhuan_raw.txt` 取自 `garychowcmu/daizhigev20`，该仓库
**未附加任何许可声明**（GitHub API 返回 `license: null`，其 `使用须知.md`
仅说明检索方法，无授权条款）。

本项目的事实基础与立场：

- 底本《史记》（约前 90 年成书）与《左传》（先秦）均为**公有领域**作品；
- 本项目取用的是**完整作品的全部文本**，非摘录选集；
- 上游文件为**纯文本转录**，本项目未见其主张任何校勘、标点或注释的独创性贡献。

因此本项目不对该文本主张任何权利，并按公有领域处理。
**但须明确：上游未声明许可一事本身构成不确定性，这是本仓库已知的权利风险点。**
如需彻底消除，应改用许可明确的替代底本重新构建（尚未执行）。

## 六、引文与出处

技能输出的所有引文均逐字取自上述语料，并标注出处
（`《资治通鉴》卷N（纪名）[seq]`、`《史记》卷N 篇名`、`《左传》X公年份`）。
引用保真度由 `scripts/audit_skill.py` 的 B 项自动校验，实测 84/84 = 100%。
