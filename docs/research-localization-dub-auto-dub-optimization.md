# localization-dub 框架借鉴与 Auto-Dub 优化研究报告

> 结论先行：**localization-dub 不是与 Auto-Dub 竞争的「另一条管线」，而是 Auto-Dub 赖以运行的通用「框架」**；Auto-Dub 是它针对 YouTube→B站 中文配音场景的 headless 自动化实例。真正值得从框架借鉴的不是「能力」（Auto-Dub 早已覆盖甚至超越），而是它的**规范工程**。本次研究据此落地了 6 项优化（5 项代码/文档落地 + 1 项 Deferred），核心是把「英文 wps → 中英膨胀率」这个**量纲错位**彻底纠正过来。

---

## 1 摘要

本报告基于对 `pipeline_defs/localization-dub.yaml`、`skills/pipelines/localization-dub/`（8 个 director 技能 + lessons-learned 铁律）、`schemas/artifacts/`（全套产物 schema）、`skills/meta/`（checkpoint-protocol / reviewer），以及 Auto-Dub 完整实现（`apps/auto-dub/` 的 `pipeline_automator.py` 约 4900 行 + `batch_runner.py` + `auto_reviewer.py`）的逐行研读，回答两个问题：

1. localization-dub 框架有哪些值得 Auto-Dub 借鉴的地方？
2. 借鉴落地后，Auto-Dub 的质量与治理改进了什么？

**核心发现**：

- **架构关系**：Auto-Dub 用 `pipeline_type="localization-dub"` 复用同一个 checkpoint 状态机，把 EP 该人肉做的事程序化自动化。二者不是两套竞争管线。
- **量纲错位（本次研究最重要的发现）**：框架 `scene-director.md` 的 `wps > 4.0` 是「**英文**单词/秒」，而 Auto-Dub 翻译预算消费的是「**中文**字/秒」。英文 wps 与中文 cps **不可比**，不能直接串联。
- **Auto-Dub 的「先验证 cps」是对的**：它绕开英文侧，直接实测中文 TTS 语速（`_calibrate_indextts_cps` → `_budget_cps` → `measured_char_budget`），预算主链只用中文一个量纲。真正的缺口是「英文信息密度 → 中文字数」这个**英→中膨胀率**从未被标定。
- **框架文档与 Auto-Dub 实现存在 atempo 矛盾**：`compose-director.md` / `edit-director.md` 仍写「绝对禁止 atempo」，而实现早已三级变速（逐句 ±5% + 全局 ±4%）。

本报告含少量代码改动与全部 commit 记录；详见 ADR-006。

---

## 2 背景：localization-dub 是「框架」不是「实现」

localization-dub 由三层构成：

| 层 | 是什么 | 具体文件 |
|---|---|---|
| 声明层 | 阶段定义 + 工具 + 质量门 + 审批政策 | `pipeline_defs/localization-dub.yaml` |
| 指令层 | EP 编排 + 7 个 director 技能 + 避坑铁律 | `skills/pipelines/localization-dub/*.md` |
| 契约层 | 每个产物的 JSON schema | `schemas/artifacts/*.schema.json` |

Auto-Dub 是第四条「执行层」——程序化复用同一状态机，把 EP 决策自动化。因此：

- 你感受到的「规范」很大一部分**本来就是 Auto-Dub 实践的沉淀**（lessons-learned 铁律标注来源都是 `auto-dub-*` 项目）。
- 框架真正比 Auto-Dub 强的，是「**把决策变成显式工件 / 把风险前向标注**」，而不是藏着算法里。

---

## 3 研究发现：三个问题 + 一个决定性洞察

### 3.1 P0-1：`timing_risk_map` 是「只写不读」的死数据，且量纲错位

- `_run_scene_plan_stage`（pipeline_automator）确实算了 `wps = 英文词数/dur`（阈值 `>4.0`），写了 `drift_risk` 和 `timing_risk_map`。
- 但全仓库 grep：`timing_risk_map` **无任何代码读取它**，是纯装饰数据。
- 更严重：执行顺序是 `script（先翻译）→ scene_plan（后算 risk）`，风险算出来时翻译早已完成并 checkpoint，物理上无法前向驱动。
- **量纲错位**：`wps` 是英文量纲，翻译预算 `_char_budget_for` 消费的是中文 cps——不可比。

### 3.2 P0-2 / P0-3 / P1-1 / P1-2 / P1-3（其余问题）

- **P0-2**：框架的 `hybrid_covered` / `on_screen_text_replacement_map`（口型遮罩/画面文字替换）概念，Auto-Dub 只有 `caption_overlay`（easyocr 窄实现），未泛化。
- **P0-3**：publish 阶段 QA 上下文（静音兜底、全局 atempo 等）未随包走，人审不可见。
- **P1-1**：框架 `compose/edit-director.md` 写「禁止 atempo」，与实现「三级变速」矛盾。
- **P1-2**：`edit_decisions` 的 localization 字段被塞进 `metadata` 逃逸 schema 校验。
- **P1-3**：Auto-Dub 缺 decision_log 审计。

### 3.3 决定性洞察：为什么 Auto-Dub「先验证 wps / cps」是对的

Auto-Dub 没有盲套框架的英文 `4.0` 阈值，而是**绕开英文侧、直接对目标语言中文做实测标定**。预算主链：

```
_calibrate_indextts_cps（真机合成固定中文文本 → cps）
  → _budget_cps（× cps_safety_factor 0.7 折成短句真实 cps ≈ 4.1）
  → measured_char_budget(dur, 中文cps, min_budget)
```

**结论**：Auto-Dub 的预算从头到尾只用「中文」一个量纲，这是对的。真正缺口是「英文信息密度 → 中文字数」的膨胀率从未被标定——不能用框架的英文 `4.0` 代替。

---

## 4 关键数据：英→中膨胀率实测标定

用 53 个历史 `script.json`、7648 句逐句中英对照标定：

| 指标 | 实测值 |
|---|---|
| `zh_chars_per_en_word` 全局膨胀率 | **1.046**（94150 英文词 → 98437 中文字）|
| 逐句比值中位数 / 均值 | 1.050 / 1.087（p10=0.571, p90=1.583）|
| 按句长分桶（<1s / 1-3s / 3-6s / ≥6s） | 1.046 / 1.041 / 0.993 / 1.127 |
| 英文 wps 中位数 / p90 / `>4.0` 占比 | 3.618 / 5.441 / 35.5% |
| 用 cps=4.1 反推「预估超预算」句占比 | 46.2%（平均超额 1.37×）|

**两个关键结论**：

1. 膨胀率 **≈1.05**（不是拍脑袋的 1.8），且**不随句长变化** → D1 用单一全局常数即可，设计大幅简化。
2. **`预估超预算`句占 46~68% 是常态而非异常**（靠既有逐句变速 + 溢出推挤无害吸收）。因此折扣必须**极其保守**，只对极端密集句（overrun > 1.3）触发，`FLOOR=0.9` 起测，避免「过度砍删」违反铁律。

---

## 5 落地决策与实现（ADR-006）

| 决策 | 内容 | 落地 | Commit |
|---|---|---|---|
| **D6** | 修框架文档漂移：「绝对禁止 atempo」→「三级变速」 | ✅ 4 个 director/lessons 文档 | `984d493` |
| **D1-D3** | 英→中膨胀率校准 + 前向驱动折扣 + 报告风险维度 | ✅ 代码 + config + 测试 | `276354c` |
| **D5** | publish 包带 QA 上下文（`_meta.json` 合入 `qa`） | ✅ 代码 + 测试 | `5d2780c` |
| **D7** | edit_decisions 顶层新增 localization 字段 + 修 `forbidden` 残留 | ✅ schema + 代码 | `10c33a9` |
| **D8** | 项目级 decision_log 审计（TTS/混音/字幕/封面 4 决策） | ✅ 代码 + 测试 | `edaa8a1` |
| **D4** | 泛化 hybrid_covered / on_screen_text_replacement | ⏸️ **Deferred**（暂缓） | `1e400bb` |

### 5.1 D1/D2/D3 核心实现

新增纯函数 `_density_risk_discount(en_text, dur, budget)`：

```
estimated_zh_chars = 英文词数 × 1.046
overrun           = estimated / budget
触发折扣  ⇔  overrun > 1.3（risk_trigger_threshold）
discount  = clamp(1/overrun, 0.9, 1.0)   # FLOOR
final_budget = budget × discount
```

- `_translate_utterances` / `_translate_blocks` 翻译前调此函数，仅极端密集句收紧预算。
- `alignment_report.json` 补 `en_words / density_risk / risk_discount / pre_budget_chars / post_budget_chars` 维度，让「事前预测 vs 事后漂移」可对账。

### 5.2 测试结果

新增测试类（纯函数/静态方法，无 tmp_path fixture，沙箱可跑）：

- `TestDensityRiskDiscount`（4 用例）——D1/D2/D3 折扣逻辑
- `TestExtractQaContext`（4 用例）——D5 QA 提取
- `TestBuildConfigDecisionEntries`（5 用例）——D8 决策条目

全部 PASS。pytest 的 `tmp_path` fixture 用例在受限沙箱下因 `PermissionError: WinError 5`（临时目录被拦）无法跑，已用工作区内等价脚本验证了 assets 报告维度的端到端逻辑。

---

## 6 遗留问题与后续建议

1. **`zh_chars_per_en_word` 目前用单一全局常数 1.046**，待确认是否需按「科技域/对话域」分套。
2. **FLOOR（0.9）与 trigger_threshold（1.3）需靠 D3 的对账数据迭代**——对齐报告已经能产出对账维度，跑一段时间后据此调参。
3. **D4 的再启用条件**：当确有「口型遮罩」或「画面文字成体系替换」需求时，参考 ADR-006 原始 D4 设计重新评估。`caption_overlay` 目前继续作为独立 config 开关存在（`subtitle_mode: caption_overlay`），实测 OCR 不稳、默认关闭。
4. **工作区有一批历史遗留未跟踪文件**（`out_*.json`、`snap_*/`、`models/voxcpm/*.safetensors` 等），与本次优化无关，建议另立任务清理/纳入 gitignore。
5. **一个未落地的观察**：Auto-Dub 的 `_run_edit_stage` 曾长期把 `speed_modification: "forbidden"` 硬编码进 edit_decisions（与真实行为矛盾），本次 D7 已修。任何「实现写死某策略值」的地方都建议用 config 驱动 + schema 校验来约束。

---

## 7 纯研究结论（不依赖实现）

- localization-dub 与 Auto-Dub 是「框架 vs 生产化实例」，借鉴应聚焦「规范工程」而非「能力」。
- Auto-Dub「实测目标语言 cps」而非抄框架源语言 wps 阈值的做法，是跨语言预算的正确范式，值得推广到其他本地化管线。
- 框架内部的文档–实现漂移（如 atempo）是系统性风险；修的方向应是「文档跟上实现」，并辅以 schema 校验来堵住「塞 metadata 逃逸」漏洞。

---

**关联文档**：
- ADR 决策：`docs/adr/ADR-006-auto-dub-timing-risk-forward-driving.md`（含原始设计、标定数据、回退方案、Deferred 说明）
- 框架铁律：`skills/pipelines/localization-dub/lessons-learned.md`
- 相关 ADR：`docs/adr/ADR-003-auto-dub-per-utterance-alignment.md`、`docs/adr/ADR-004-indextts-2.5-upgrade.md`
