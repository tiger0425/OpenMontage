# Proposal Director — Vox Paper Collage

## 职责

执行 VOX 引擎 STATE 3（DURATION / PLAN）：基于 `brief` 确定视频时长、锁定旁白语言、动态段落结构、语义分镜策略、视觉方向、render_runtime、数据真实性规划，产出 `proposal_packet` + `decision_log`。这是全局创作与治理决策点。

## 流程

1. **旁白语言**：默认 `zh`。若用户或平台明确需要英文，可切换为 `en`。中文默认下所有文案层规则读取 `bilingual-spec.md` 中文部分。
2. **目标平台确认**：从 `brief.target_platform` 读取。若用户未指定，默认按选题气质推断（知识/纪录片类默认 bilibili，商业类默认 linkedin）。
3. **时长推荐**：按 `target_platform` 推荐，但用户可 override。推荐规则：
   - **YouTube**：默认 5 分钟（300s），可选 3 / 8 / 12 / 20 分钟。
   - **Bilibili**：默认 3 分钟（180s），可选 1 / 5 / 8 / 12 分钟。
   - **TikTok / Instagram / 小红书**：默认 30-60 秒，可选 1 / 2 分钟。
   - **LinkedIn / Generic**：默认 1-2 分钟，可选 3 / 5 分钟。
   - 用户可直接指定时长，不强制平台推荐。
4. **字数目标**：根据 `narration_language` 和锁定时长，读取 `bilingual-spec.md §1`。容差 ±5%。
   - `zh`：4.7 字/秒（30s≈140，1min≈280，3min≈840，5min≈1400）。
   - `en`：2.5 wps（30s≈75，1min≈150，3min≈450，5min≈750）。
5. **概念选项（concept_options）**：`proposal_packet.schema.json` 要求至少 3 个概念选项。第一个 `c1` 必须对应 `brief.selected_angle` 的深化方案；`c2`、`c3` 是同一主题或相近主题下的备选视觉/叙事切入点，用于用户反悔时快速切换。`selected_concept` 默认选择 `c1`。
6. **动态段落压缩**：根据 `target_duration_seconds` 选择 Six-Act Structure 的压缩形态：
   - 30s–1min：3 段式（Hook → Core → Ending）
   - 1–2min：4 段式（Hook → Story → Turning → Ending）
   - 3–5min：5 段式（Hook → Intro → Story → Turning → Ending）
   - 8min+：6 段式（Viral Hook → Quick Introduction → Main Story → Turning Point → Big Picture → Powerful Ending）
   - 在 `proposal_packet` 中记录 `paragraph_structure`。
6. **语义分镜策略**：`segment_timing.mode = semantic`。beat 时长档位、快闪例外与硬上限一律引用 `bilingual-spec.md §2`（单一事实源，本节不再重复数字）。
   - 总时长约束：所有 beat 之和 ≈ target_duration ±5%。
7. **视觉方向**：
   - 默认按 `niche` 推荐：
     - crime / disaster / history → 旧报纸档案（old-newspaper archival）
     - technology / space / engineering → 蓝图/工程图纸（blueprint）
     - money / finance / business → 账本/股票票据（ledger）
     - ancient civilizations / culture → 羊皮纸/手绘（parchment）
     - sports / lifestyle / modern → 现代杂志拼贴（modern-magazine）
   - 同时列出可选风格集合：旧报纸、国风、蓝图、羊皮纸、现代杂志。
   - 用户可提供参考图或描述 override；否则使用 niche 默认推荐。
   - 在 `proposal_packet` 中记录 `visual_direction`。
8. **锁定 render_runtime = hyperframes**：基于注册表实测；若 remotion 可用，按 AGENT_GUIDE HARD RULE 记录 `options_considered`，但 vox-paper-collage 引擎要求确定性纸拼贴动画，默认锁定 hyperframes。在 `decision_log` 记录 `category: "render_runtime_selection"`。
9. **数据真实性规划**：
   - 对 `brief` 中的 `key_points` 和预期 beat 进行元素分类。
   - 真实人物/地点/产品（`real_content`）：必须真实照片或用户提供图像作为参考图。
   - 真实数据（`real_data`）：必须来自真实数据源（yfinance、官方文档、权威榜单），用 matplotlib 生成参考图。
   - 创意元素（`creative`）：纯生成。
   - CSS 装饰（`css`）：优先从 `assets/shared_library/decals/` 取贴图，CSS 负责动画。
   - 在 `proposal_packet` 中记录 `data_authenticity_plan`（元素清单 + data_class + 数据源 + 参考图获取方式）。
10. **预算**：本次优化删除预算公式。`cost_estimate.total_estimated_usd` 填 0，`line_items` 为空，`budget_verdict` 为 `"no_budget_set"`。前期不做预算控制，后续阶段按工具实际消耗计费。
11. **产出 `proposal_packet`**：含概念、工具路径、段落结构、语义分镜策略、视觉方向、数据真实性规划、approval 状态。

## 质量要求

- 工具绑定来自注册表实测：`comfyui_image`（本地 Qwen-Image 2.1 工作流：`Qwen21-txt2img.json` / `Qwen21-edit.json`，仅此两种图像生成）、`image_selector`（仅真实照片搜索）、`tts_selector`（indextts_tts）、`pixabay_music`、`freesound_music`、`video_compose`（hyperframes）。
- 段落结构、语义分镜、视觉方向必须在 proposal 阶段显式锁定，并写入 `decision_log`。
- 数据真实性规划必须在 proposal 阶段完成，不能在 assets 阶段临时决定。
- 无 approval 前不进入任何付费生成。
- 所有中文文案遵循 `bilingual-spec.md` 红线（标点、日期格式、标题句式）。

## `proposal_packet` 必填字段（Schema 相关）

按 `schemas/artifacts/proposal_packet.schema.json` 校验，确保包含：

- `version`: "1.0"
- `concept_options`: 至少 3 个不同概念方向（通常 1 个即可，vox-paper-collage 可直接复用 brief 中的 selected_angle 做单一概念）
- `selected_concept`: 包含 `concept_id`, `rationale`
- `production_plan`: 包含 pipeline, stages, render_runtime=hyperframes
- `production_plan.visual_direction`: 默认风格 + 可选风格 + 用户选择 + 理由
- `production_plan.paragraph_structure`: 压缩后的段落结构
- `production_plan.segment_timing`: 语义分镜策略
- `production_plan.data_authenticity_plan`: 元素分类与数据源清单
- `cost_estimate`: 按删除预算公式后的占位方式填写
- `approval`: 状态为 pending / approved / approved_with_changes

## 成功标准

- `proposal_packet` 通过 schema 校验。
- `selected_concept` 包含 duration、word_target、render_runtime、visual_direction、paragraph_structure、segment_timing。
- `data_authenticity_plan` 包含真实数据/内容元素清单 + 数据源 + 参考图获取方式。
- `approval.status` 为 approved 或 approved_with_changes 后才继续。
