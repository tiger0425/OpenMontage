# Proposal Director — Vox Paper Collage

## 职责

执行 VOX 引擎 STATE 3（DURATION）：确定视频时长，锁定 render_runtime、预算、旁白语言，产出 `proposal_packet` + `decision_log`。这是成本与治理决策点。

## 流程

1. **时长选择**：向用户呈现引擎选项
   ```
   "How long should the video be? Options: 30 seconds, 1 minute, 2 minutes,
   3 minutes, or 5 minutes. Reply with a length."
   ```
2. **字数目标**：先定 `narration_language`（默认 `en`，可切换 `zh`），再按 `bilingual-spec.md §1` 对应语言查表（en 2.5 wps：30s≈75 词 … 5min≈750 词；zh 4.7 字/秒：30s≈140 字 … 5min≈1400 字）。容差 ±5%。中英常数只在 bilingual-spec 维护，此处不复制。
3. **锁定 render_runtime = hyperframes**（基于注册表实测：若 remotion 可用则按 AGENT_GUIDE 双运行时 HARD RULE 先呈现两种选项并记录 `options_considered`；若只有 hyperframes 可用，则锁定并记录 `rejected_because: runtime not available`。引擎 FINAL RULE 要求确定性动画，hyperframes 是合规路径）。在 `decision_log` 记录 `category: "render_runtime_selection"`
4. **预算估算**：
   - 图像：节拍数 × $0.05（约等于字数目标/6，因为每节拍 5-8 词）
   - 配音：indextts_tts 本地免费
   - 音乐：pixabay_music 免费
   - 纸 ASMR：freesound_music 免费
   - 默认总预算上限 $3.00
5. **旁白语言**：`narration_language` 默认 `en`，可切换 `zh`。影响：script 字数表（§1）、标题句式（§3）、TTS 语速（§10）、缩略图文字（§11）——全部见 `bilingual-spec.md`
6. 产出 `proposal_packet`，含概念、工具路径、成本明细、approval 状态

## 质量要求

- 工具绑定来自注册表实测：image_selector（google_imagen 首选，flux/FAL_KEY 升级路径）、tts_selector（indextts_tts）、pixabay_music、freesound_music、video_compose（hyperframes）
- 预算明细 itemized，免费路径明确标注
- 无 approvaal 前不进入任何付费生成

## 数据真实性规划（2026-08 用户确认，proposal 阶段必须完成）

**这是新闻/纪录片题材的硬性要求：涉及真实数据/事实的视觉元素，其数据必须真实可查证，禁止 AI 编造。** 必须在 proposal 阶段就识别并锁定，不能等到 assets 阶段才处理。

### 元素分类（proposal 阶段逐节拍标记）

| 类别 | 定义 | 生成方式 | 示例 |
|------|------|---------|------|
| **真实数据类** | 含数字/排名/行情/参数等可查证数据 | **真实数据 → 参照图 → img2img** | K线图、榜单排名、参数对比、股价涨幅 |
| **真实内容类** | 真实人物/地点/产品（无数据） | **真实图参照 → img2img** 或纯文生图 | 发布会外景、产品 logo、公司总部 |
| **创意元素类** | 抽象概念/装饰 | 纯文生图（VOX 风格） | 神经网络示意、世界地图、印章 |
| **CSS 装饰类** | 文字图章/标签/胶带/图钉 | CSS 纯渲染（零成本） | TOP2、+7%、日期章、未来已来 |

### 数据来源锁定（proposal 阶段记录到 decision_log）

对每个"真实数据类"元素，规划阶段就要明确：
1. **数据来源**：yfinance/官方发布/权威榜单/新闻稿
2. **关键数据点**：具体数字（如 9988.HK 8月3日 +7.01%）
3. **获取方式**：`yfinance` 拉取 / 官方文档 / 已核实事实
4. **参照图生成**：matplotlib 用真实数据画图（作为 img2img 参照底图）
5. **AI 幻觉红线**：模型名/数字/日期必须来自数据源，提示词中显式写出精确值（Qwen 3.8-MAX = Fable 5，禁止 Gemini 幻觉）

### 预算影响

- 真实数据类元素 = 2 次生成成本（matplotlib 本地 0 成本 + img2img 1 次 $0.05）
- proposal 预算按此估算，不按单次文生图

## 成功标准

- `proposal_packet` 含 duration、word_target、render_runtime、cost_estimate（line_items）
- `decision_log` 记录 render_runtime_selection 与预算决策
- `proposal_packet` 含 `data_authenticity_plan`（真实数据类元素清单 + 数据来源 + 关键数据点）
- `approval.status` 为 approved 或 approved_with_changes 后才继续
