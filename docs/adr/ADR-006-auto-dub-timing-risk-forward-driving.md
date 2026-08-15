# ADR-006: Auto-Dub「漂移风险前向驱动 + 中英膨胀率校准」优化决策

- **状态**: Accepted（D6 / D1+D2+D3 / D5 / D7 / D8 已落地；D4 Deferred 暂缓）
- **日期**: 2026-08-XX
- **决策者**: 用户 + AI Agent（localization-dub 对比研究 session）
- **影响范围**: Auto-Dub 流水线（`apps/auto-dub/`）+ localization-dub 框架文档（`skills/pipelines/localization-dub/`）
- **关联 ADR**: ADR-003（逐句对齐）、ADR-004（IndexTTS-2.5 语速控制）——本 ADR 补的是「**事前**」缺口，与两者「事后」兜底互补，不取代。

---

## 背景

### 1. 研究结论：localization-dub 是「框架」，auto-dub 是「实现」

localization-dub（`pipeline_defs/localization-dub.yaml` + `skills/pipelines/localization-dub/*`）是 OpenMontage 的通用本地化配音**框架**：声明式 manifest + EP 编排 + 7 个 director 技能 + 铁律 + JSON schema。auto-dub（`bin/auto_dub.py` + `apps/auto-dub/`）复用同一个 checkpoint 状态机（`pipeline_type="localization-dub"`），把 EP 该人肉做的事程序化自动化。二者是「框架 vs 它的一个生产化实例」，不是两套竞争管线。

### 2. 研究发现的三个问题（P0/P1 的来源）

**(P0-1) `timing_risk_map` 是「只写不读」的死数据，且量纲错位**

- `_run_scene_plan_stage`（`pipeline_automator.py:1866-1895`）确实算了 `wps = 英文词数 / dur`，标注了 `drift_risk: high`（阈值 `wps > 4.0`），写进了 `timing_risk_map`。
- 但 grep 全仓库：`timing_risk_map` **只有 3 处出现**——定义、赋值、塞进 metadata，**没有任何代码读取它**。它是纯装饰数据。
- 更严重：执行顺序是 `script（先翻译）→ scene_plan（后算 risk）`，风险算出来时翻译早已完成并 checkpoint，物理上无法前向驱动。
- **量纲错位（本次研究最重要的发现）**：框架 `scene-director.md` 的 `4.0` 阈值是「**英文**单词/秒」（源语言密集度），而翻译预算 `_char_budget_for` 消费的是「**中文**字/秒」（目标语言语速，实测 cps 3.1–5.8）。**英文 wps 与中文 cps 根本不可比**，不能直接串联。

**(P0-2) `hybrid_covered` / `on_screen_text_replacement_map` 概念未被泛化**

框架在 scene 阶段就规划「哪些段落需 B-roll/图形/文字覆盖口型不匹配或画面英文」。auto-dub 只有 `caption_overlay`（easyocr 检测画面硬字幕 + drawbox 遮盖 + ASS 原位替换）这一窄实现，没有泛化成「口型覆盖」通用策略，也没有 `on_screen_text_replacement_map` 显式工件。

**(P0-3) publish 阶段「审阅上下文随包走」缺失**

框架铁律：QA 备注（发音警示、缺失 lip-sync、timing 警告）绝不能丢，必须写进 publish_log。auto-dub 的 `publish_log.entries[0].metadata_used` 只有 title/description，**没有把 `render_report.warnings` / `verification_notes`（如「第 N 段静音兜底」）带进 `_meta.json`**，人审时不可见。

**(P1-1) 框架文档内部自相矛盾（「禁止 atempo」vs 实现已三级变速）**

- `compose-director.md` 铁律：❌ 禁止任何 atempo/变速。
- `edit-director.md`：`speed_modification: "forbidden"`。
- 但 `lessons-learned.md`（2026-08-09 修订）已明确「铁律 A = 三级变速策略」，auto-dub 实现也早已逐句 ±5% + 全局兜底 atempo（`segment_timings.json` 甚至写 `speed_modification: "per_utterance_atempo"`）。

**(P1-2) `edit_decisions` 的 localization 字段被塞进 `metadata` 逃逸 schema 校验**

`edit-director.md` 必填的 `mix_algorithm` / `timing_drift_policy` / `min_pause_between_segments_ms` / `speed_modification`，在 auto-dub 实现里被塞进 `edit_decisions.metadata`（`pipeline_automator.py:4210-4218`）。而 `edit_decisions.schema.json` 根本没定义这些字段，且 `additionalProperties: false`——顶层定义会遭到拒绝，塞 metadata 是「逃过校验」的无奈之举。这暴露「localization-dub 缺一个专属 edit_decisions schema 变体」。

**(P1-3) auto-dub 缺 decision_log 审计**

框架要求每个重要决策（TTS 引擎、混音策略、封面风格）留痕 + ≥2 options_considered + 真实 reason。auto-dub 除 idea 阶段的片尾 render_runtime_selection 外，其余选择都是 config.yaml 的「隐式默认」，无审计。

---

## 核心洞察：为什么 auto-dub「先验证 wps / cps」是对的

这是本次研究的转折点，也是 P0-1 正确修复的钥匙。

- 框架 `scene-director.md:38` 的 `wps > 4.0` 是**未经验证、且是英文量纲**的静态魔法数字，给「Agent 人肉判软提示」用。
- auto-dub **没有盲套这个英文阈值**，而是绕开英文侧，直接对**目标语言中文做实测标定**：`_calibrate_indextts_cps`（每次真机合成固定中文参考文本，`cps = len(中文)/dur`）→ `_budget_cps`（× `cps_safety_factor 0.7` 折成短句真实 cps ≈ 4.1）→ `measured_char_budget`（用中文 cps 算中文预算）。
- **结论**：auto-dub 的预算主链从头到尾只用「中文」一个量纲，是对的。英文 wps 全程不参与预算，这正是「先验证 cps」的价值。

**真正的缺口不是「没接 wps」，而是「英文信息密度 → 中文膨胀率」这个换算从未被标定。** 这个膨胀率不能用框架的英文 `4.0`，必须用「每英文词 ≈ 几个中文字」的实测来定。

---

## 决策

### D1: 新建「英→中膨胀率」校准（P0-1 的核心修复）

**目标**：把「英文说得多密」正确翻译成「中文预算该收多紧」，填补从未被标定的换算环节。

**关键设计约束（本次研究得出，必须遵守）**：
1. **不能**在 script 阶段直接套用 scene 阶段的英文 `wps > 4.0` 阈值（量纲错位）。
2. **必须**用「英→中膨胀率」做语言换算，而不是把英文 wps 数值直接当折扣系数。
3. 折扣标定**必须用中文实测数据**，与现有中文 cps 校准共用「实测优先 + 缓存」机制。

**信号定义**：

```
estimated_zh_chars = 英文词数 × zh_chars_per_en_word   # 预估中文字数
density_risk      = estimated_zh_chars / budget_for_dur  # 预估译文 / 时长预算的比值
  - density_risk > 1.0  → 译文预估装不下 → 密集段（drift_risk: high）
  - density_risk <= 1.0 → 安全段
```

**实测标定结果（2026-08 采集，53 个 script.json / 7648 句）**：

| 指标 | 实测值 |
|------|--------|
| `zh_chars_per_en_word` 全局膨胀率 | **1.046**（94150 英文词 → 98437 中文字）|
| 逐句比值中位数 / 均值 | 1.050 / 1.087（p10=0.571, p90=1.583）|
| 按句长分桶（<1s / 1-3s / 3-6s / ≥6s） | 1.046 / 1.041 / 0.993 / 1.127 |

**标定结论（修正占位假设）**：
1. 膨胀率 **≈1.05，不是此前占位的 1.8**——中文「每字信息密度高」，每英文词约对应 1 个中文字，这是合理且稳定的。
2. 膨胀率**几乎不随句长变化**（1.04±0.13）→ **D1 无需按句长分档**，一个全局常数即可，设计大幅简化。
3. **`density_risk > 1` 是常态而非例外**：用历史数据反推，中文 cps=4.1 时 **46.2%** 的句子预估译文会超预算，cps=3.5 时高达 **67.9%**。这证明了「英文源普遍偏密，中译往往较长」是既有事实，也让 D1 的折扣必须**极其保守**——否则会大面积「过度砍删」，违反 lessons-learned 铁律「严禁为贴时长删有意义内容」。

**因此折扣函数改为「保守安全网」而非「默认动作」**：

```
# 只对「极端密集」句触发——用密度超标量而非「是否 >1」作为门槛
overrun     = estimated_zh_chars / budget_for_dur   # 预计超预算倍数
risk_discount = clamp(1.0 / overrun, FLOOR, 1.0)    # FLOOR 待实测（占位 0.9，非 0.7）
final_budget  = budget_for_dur × risk_discount
# 仅当 overrun 超过阈值（如 >1.3，即预估译文超预算 30%+）才收紧；
# overrun 在 1.0~1.3 的句子交给既有「逐句 ±5% atempo + 溢出推挤」吸收，不动预算。
```

- `FLOOR` 从占位 0.7 **上调至 0.9** 起测：因为标定显示 46~68% 句子都「超预算」却靠既有兜底无害通过，激进折扣（0.7）会误伤大量本可正常吸收的句子。0.9 是「只对极端句轻微收紧」的保守起点，需靠 D3 的对账数据再迭代。
- `trigger_threshold`（默认 `overrun > 1.3`）把折扣限定在「真正会漂移的极端密集句」上，呼应 lessons-learned 铁律 A「翻译预算控制是首选、但绝不强行变速/砍删」。

**膨胀率标定**：`zh_chars_per_en_word` 用历史 `script.json` 的 `sections[].text`（英文）与 `sections[].delivery_cues.provider_text`（中文）**逐句自带中英对照**，无需跨文件对齐（script.json 本身就有双语）。与中文 cps 一样走「实测优先 + 缓存」。

**标定数据源（只读，不改）**：`projects/auto-dub/*/script.json` 的 `sections[]`（每节同时含英文 `text` 与中文 `provider_text`），算 `sum(中文字数) / sum(英文词数)`。膨胀率稳定（跨句长 ±0.13），首版用单一全局常数，暂不分「科技域/对话域」。

### D2: 前向驱动时机——「翻译前算 density_risk」，不等 scene_plan

因为 `script` 先于 `scene_plan` 执行，且 risk 判定所需数据（英文 `text` + `start/end`）在 script 阶段本来就有，**不需要等 scene_plan**：

- 在 `_translate_utterances` / `_translate_blocks` 内，翻译每个 unit 前用现有 `text` + `dur` 直接算 `density_risk`（本地重复 `wps` 计算的英文部分，但**不套英文 4.0 阈值**，而是走 D1 的中文膨胀换算）。
- 保留 `_run_scene_plan_stage` 的 `timing_risk_map` 产出作为**审计/回溯维度**，但把它定位为「事后对照表」，不再宣称它是「前向驱动的风险信号」。

**为什么不走两遍制（先算 risk 再翻译）**：改动大、和 checkpoint 状态机耦合紧、且收益有限——因为 D1 的信号在 script 阶段即可自足计算，无需 scene_plan 先行。

### D3: 把 risk 维度写进对齐报告（验证闭环）

`alignment_report.json` 目前只记录 `target/actual/status`。补齐 risk 维度：

```json
"utterances": [
  {
    "id": "u3",
    "target": 2.85,
    "actual": 2.92,
    "status": "aligned",
    "en_wps": 5.2,
    "density_risk": 1.35,
    "risk_discount": 0.90,
    "pre_budget_chars": 11,
    "post_budget_chars": 10
  }
]
```

这样「**事前预测的 density_risk**」与「**事后实际漂移 status**」能对账，验证 D1 到底省了多少次重翻/变速，为折扣系数迭代提供数据。

### D4: 泛化 `hybrid_covered` / `on_screen_text_replacement_map`（P0-2）—— **【Deferred 暂缓】**

> **状态：Deferred（暂缓，不落地）。** 决策于 2026-08 研究 session 中做出。

原计划：在 `scene_plan` 的 `scene_localization_meta` 里新增 `on_screen_text_replacement` 字段（枚举：`none` / `caption_overlay` / `broll_cover` / `gfx_cover`），把现有 `caption_overlay` 定位为其中一种，`broll_cover` / `gfx_cover`（口型遮罩）作预留枚举。

**暂缓理由**（本次 session 实际探索后得出）：
1. **无真实需求**：auto-dub 定位是「整轨替换 + 不改画面」，口型不匹配是常态且被接受；`broll_cover` / `gfx_cover` 面向的「口型遮罩」功能**无人提出要做**，只是框架概念性存在。
2. **`caption_overlay` 本身是窄实现且不成熟**：它用 easyocr 检测画面中下部/底部硬字幕条并原位替换，作者已在 config 注释标明「实测 OCR 不稳（漏字、条不准）」且默认关闭。泛化它不会让它变得更可靠。
3. **避免空字段**：为一个「不存在、也不成熟」的能力在 schema/config 里加枚举占位，只会增加维护负担和语义漂移风险——与本次整体「先改文档/让实现对齐」的方向相悖。

**再启用条件**：当确有一个明确需求——「画面口型需遮罩」或「画面文字需成体系地检测并原位替换」——时，重新评估并落地；届时可参考本 ADR 的原始设计。在启用前，`caption_overlay` 继续作为独立 config 开关（`subtitle_mode: caption_overlay`）存在，不纳入 `on_screen_text_replacement` 语义体系。

### D5: publish 包带 QA 上下文（P0-3）

- `_run_publish_stage` 生成 `_meta.json` 时，把 `render_report.warnings` / `verification_notes` 里**对人审有意义**的条目写入新字段（如 `qa_warnings`、`qa_notes`）。
- 典型要带出的：静音兜底句（`synthesis_review` 遗留）、全局 atempo 是否触发并用了多少倍速、零重叠校验失败警告、漂移秒数。
- 规则沿用框架 publish-director 铁律：**审阅上下文绝不丢，warnings 必须随包走**。

### D6: 修框架文档漂移（P1-1）

- 更新 `compose-director.md` / `edit-director.md` 里过时的「绝对零变速 / speed_modification: forbidden」，对齐 `lessons-learned.md` 的「铁律 A：三级变速策略」。**修的方向是「让文档跟上实现」，不是反过来**。
- 具体：把「❌ 禁止任何 atempo」改为「❌ 禁止超出已验证听感的 atempo（逐句 ±5%、全局 ±4%）；漂移 ≤1.5s 由逐句对齐+溢出推挤吸收，不全局变速」。
- 一旦 D6 落地，P1-1 的「框架内部自相矛盾」即消除。

### D7: 为 localization-dub 定义专属 `edit_decisions` 字段（P1-2）

两条路，本 ADR **选路线 A**：

- **路线 A（推荐）**：在 `edit_decisions.schema.json` 顶层新增 localization 相关字段（`mix_algorithm`、`timing_drift_policy`、`min_pause_between_segments_ms`、`speed_modification`），让它们从 `metadata` 上浮到一等字段，纳入 schema 校验。
- 路线 B：为 localization-dub 单独建一个 `edit_decisions` schema 变体。
- 选 A 理由：改动小；这些字段对其他管线无害（可选字段，不影响既有 edit_decisions）；符合「contract-first」初衷，堵住「塞 metadata 逃逸校验」的漏洞。

### D8: auto-dub 增加轻量 decision_log 审计（P1-3）

- 复用 `decision_log.schema.json`，在 auto-dub 的关键决策点（TTS 引擎选择、mix_mode、字幕模式、封面引擎、漂移兜底策略）写入 `options_considered ≥ 2` + 真实 reason。
- **轻量原则**：批量流水线不宜每句都记，只在「每个项目一次」的配置级决策点记，控制在少数几条。
- 落地形式：`idea` 阶段已有 decision_log（片尾 render_runtime_selection），扩展为「项目级决策日志」，随 checkpoint 存档。

---

## 后果

### 正面
- **省钱省时间**：密集段事前收紧预算，事后 `out_of_budget` 缩短重翻（先翻译→合成→测超时→重翻的白跑）与逐句/全局 atempo 的触发次数下降。
- **信号量纲正确**：用「英→中膨胀率」做换算，避免英文 wps 与中文 cps 的错误串联。
- **可验证**：`alignment_report.json` 补齐 density_risk 维度，事前预测 vs 事后漂移可对账。
- **治理自洽**：修掉 compose/edit 文档「禁止 atempo」vs 实现「三级变速」的矛盾；localization 决策上浮进 schema；决策可审计。

### 负面 / 风险
- `zh_chars_per_en_word` 膨胀率需要历史数据标定与实测定参，首版可能不精确；需靠 D3 的对账数据迭代。
- 折扣过激可能让密集段译文过度精简（与「严禁过度砍删」铁律冲突）。标定已显示「超预算」句占比高达 46~68%，故 `FLOOR` 从 0.7 上调至 **0.9** 起测、且仅对 `overrun > 1.3` 的极端句触发，作为可回退的保守安全网；最终值需靠 D3 对账数据确认。
- D7 改 schema 会波及所有用 `edit_decisions.schema.json` 的管线，需回归确认新增字段为 optional、不影响既有产物校验。

### 回退方案
- **D1/D2/D3**：`risk_discount` 默认 1.0（不开折扣），等于退回到现状；`zh_chars_per_en_word` 未标定时回退到「不折扣」。整个 P0-1 是纯增量，可一开关关闭。
- **D5/D7**：均为「新增字段/枚举/文档」，不影响既有行为，可独立回退。
- **D6**：文档改动，可与 `git revert` 逐文件回退。
- **D4**：Deferred，无代码落地，无需回退。

---

## 实现路线（分阶段，本 ADR 不执行）

| 阶段 | 内容 | 风险 | 是否依赖实测 |
|------|------|------|-------------|
| 1 | D6 修文档漂移（compose/edit → 三级变速） | 低，纯文档 | 否 |
| 2 | D1+D2+D3 膨胀率校准 + 前向驱动 + 报告维度 | 中，需标定 | 是（历史数据） |
| 3 | D5 publish 带 QA 上下文 | 低 | 否 |
| 4 | D7 edit_decisions 字段上浮 | 中，schema 回归 | 否 |
| 5 | D8 轻量 decision_log | 低 | 否 |
| 6 | ~~D4 hybrid_covered 语义契约~~ **Deferred**（暂缓，见 D4 说明） | — | 否 |

**建议顺序**：先 1（快赢、纯文档）→ 再 2（核心价值，但需实测标定）→ 其余按需。D4 已 Deferred，不纳入本轮落地。

---

## 待定（Open Questions）

1. `zh_chars_per_en_word` 已实测为 **1.046**（首版用此全局常数，暂不分域）——待确认是否需按「科技域/对话域」再分套。
2. `FLOOR` 与 `trigger_threshold` 的最终值（占位 FLOOR=0.9、threshold=1.3，需靠 D3 对账确认与「严禁过度砍删」铁律的平衡点）。
3. D1 的 density_risk 是否要按 `segment_id` 做更细的聚类（而非全局单一膨胀率）。
4. D8 的 decision_log 记到多细（每项目一次 vs 每配置变化一次）。
