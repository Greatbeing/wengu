# NOTICE

本仓库为**混合许可（mixed-license）**项目。不同部分适用不同条款，**不可整体套用任一许可**。

根目录 [`LICENSE`](LICENSE) 为 MIT 全文，**仅覆盖本项目的自有创作**；
其余内容按下列条款处理。完整逐项说明见 **[`corpus/LICENSES.md`](corpus/LICENSES.md)**。

---

## 一、范围表

| 路径 | 许可 | 说明 |
|---|---|---|
| `scripts/` | **MIT** | 检索、推演、审计、测试脚本（自有创作） |
| `SKILL.md` | **MIT** | 技能定义 |
| `references/` | **MIT** | 实现说明、场景定义、已知问题 |
| `samples/` | **MIT** | 样例输出 |
| `README.md`、`NOTICE.md` | **MIT** | 仓库说明 |
| `corpus/zizhitongjian-main/chapters/` | **GPL-3.0** | 上游语料，逐字复制 |
| `corpus/zizhitongjian-main/LICENSE` | **GPL-3.0** 全文 | 上游许可，原样保留 |
| `corpus/zizhitongjian-main/README.md` | **GPL-3.0** | 上游自述，原样保留 |
| `corpus/zztj_units.jsonl` | **GPL-3.0** | 上游语料的衍生物 |
| `corpus/index.json` | **GPL-3.0** | 含 GPL 衍生成分 |
| `corpus/patterns.json` | **GPL-3.0** | 含 GPL 衍生成分 |
| `corpus/data_quality.json` | **GPL-3.0** | 含 GPL 衍生成分 |
| `corpus/shiji.txt` | 底本公有领域；转录来源未声明许可 | 见第三节 |
| `corpus/zuozhuan_raw.txt` | 同上 | 见第三节 |
| `corpus/shiji_units.jsonl` | 同上 | 衍生自上述文本 |
| `corpus/zuozhuan_units.jsonl` | 同上 | 衍生自上述文本 |
| `docs/index.html`、`docs/app.js`、`docs/engine.js`、`docs/styles.css` | **MIT** | 网站前端（自有创作） |
| `docs/assets/` | **MIT** | 水墨配图（本项目生成） |
| `docs/data/meta.json.gz` | **GPL-3.0** | 语料衍生物（特征向量与候选表） |
| `docs/data/scenes.json` | **GPL-3.0**（含 GPL 成分） | 内核定义（MIT）+ IDF 表（衍生） |
| `docs/data/shards/*.json.gz` | **GPL-3.0** | 语料衍生物（正文与白话分片） |

**为何 `scripts/` 能保持 MIT**：本项目脚本为独立创作，未复制上游代码；
它们只是*读取* GPL 数据并*产出*衍生数据。衍生数据受 GPL-3.0 约束，脚本本身不受约束。

网站前端同理：`docs/engine.js` 移植的是本项目的 `scripts/retrieve.py`（自有代码），
不是上游仓库的代码，故保持 MIT；而它读取的 `docs/data/` 是语料衍生物，仍受 GPL-3.0 约束。

---

## 二、GPL-3.0 修改声明（第 5(a) 条）

> 本仓库包含对 [JY0284/zizhitongjian](https://github.com/JY0284/zizhitongjian)
> 的修改。修改日期：**2026-09**。

修改方式：

1. **解析与结构化** — 将 `chapters/*.md` 的行级「原文／白话」交替文本切分为
   含 `juan` / `seq` / `text` / `translation` / `cite` 字段的 JSONL 单元
   （`scripts/build_corpus.py`）。
2. **删减** — 不再分发上游中本项目未使用的部分（`data.json`、
   `adapted_book.json`、`model/`、`visualization/`、notebook、测试等，约 47 MB），
   仅保留 `chapters/`、`LICENSE`、`README.md`。
3. **合并与索引** — 与《史记》《左传》单元合并为 6,707 个事件单元，
   构建倒排索引与 IDF 表（`scripts/build_index.py`）。

上述修改产物按 **GPL-3.0** 分发。上游 GPL-3.0 全文保留于
`corpus/zizhitongjian-main/LICENSE`。

---

## 三、已知权利风险

`corpus/shiji.txt` 与 `corpus/zuozhuan_raw.txt` 取自
[garychowcmu/daizhigev20](https://github.com/garychowcmu/daizhigev20)，
该仓库**未附加任何许可声明**（GitHub API 返回 `license: null`，
其 `使用须知.md` 仅说明检索方法，无授权条款）。

本项目的事实基础与立场：

- 底本《史记》（约前 90 年成书）与《左传》（先秦）均为**公有领域**作品；
- 本项目取用的是**完整作品的全部文本**，非摘录选集；
- 上游文件为纯文本转录，本项目未见其主张任何校勘、标点或注释的独创性贡献。

因此本项目不对该文本主张任何权利，并按公有领域处理。
**但须明确：上游未声明许可一事本身构成不确定性，这是本仓库已知的权利风险点。**
如需彻底消除，应改用许可明确的替代底本重新构建（尚未执行）。

---

## 四、公有领域声明

- 《资治通鉴》原文为公有领域（1084 年成书）。GPL-3.0 覆盖的是上游的白话译文与结构化数据。
- 本项目不对任何古籍原文主张权利。

> 本文件为项目方的许可整理，**不构成法律意见**。
