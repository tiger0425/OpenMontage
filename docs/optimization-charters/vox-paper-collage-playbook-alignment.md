# vox-paper-collage 管线优化宣言

## 目标

将 `made-by-ai-playbook-zh.md` 中的 VOX 纪录片创作理念注入 `vox-paper-collage` 管线，提升最终视频的画面质感、叙事吸引力、内容与画面一致性，同时保留 Pipeline 的 8 阶段工程结构和人工审批机制。

## 核心痛点

1. 画面不像 Playbook 描述得有质感。
2. 创意不够，视频单调、不吸引人。
3. 内容与画面不符。
4. 选题和引爆点不如 Playbook。
5. 脚本结构不如 Playbook。
6. 动画节奏有问题（当前 voice-led 分镜不适合）。

## 优化原则

1. **阶段结构不变**：保留 idea → proposal → script → scene_plan → assets → edit → compose → publish 的 8 阶段结构。
2. **逐个阶段推进**：按顺序修改每个阶段，生成 sample artifact，通过人工审批后进入下一阶段。
3. **Playbook 理念注入，非复制**：吸收 Playbook 的选题、脚本、视觉、动画理念，但输出仍为 Pipeline 可消费的产物格式。
4. **工程可验证**：每个阶段修改必须同步更新 skill 文档、产物 schema（如需要）、示例产物和验证清单。
5. **默认中文旁白**：本次优化后默认 `narration_language = zh`，但保留英文能力。
6. **真实内容可追溯**：真实人物、地点、产品必须有真实照片参考；真实数据必须基于真实数据源。
7. **素材复用**：建立全局素材库，外部来源素材自动归档，支持跨项目复用。
8. **前期不做预算控制**：删除预算公式，优化阶段不阻塞成本估算。

## 决策摘要

| 决策点 | 原 Pipeline | 优化后 |
|---|---|---|
| 阶段结构 | 8 阶段 | 不变 |
| 默认旁白语言 | 英文 | 中文 |
| 选题数量 | 固定 10 个 | 由领域动态决定，不固定 |
| 领域范围 | 8 个 niche | 扩展到多个领域 |
| 标题风格 | 固定纪录片句式 | 由 `target_platform` 决定 |
| 选题去重 | 无 | 仅已发布选题进入黑名单 |
| 脚本结构 | Fern DNA | 6 段式作为检查清单叠加在 Fern DNA 上 |
| 分镜方式 | Voice-led | Semantic scene + semantic beat |
| 段落结构 | 固定 | 按时长动态压缩（3/4/5/6 段式） |
| 视觉方向 | 默认旧报纸 | 按 niche 默认推荐，用户可 override，可选国风等 |
| 真实照片参考 | real_content 可纯生成 | 真实人物/地点/产品必须有照片参考 |
| 真实数据 | 用 matplotlib 参考图 | 真实数据源 → 参考图 → 风格化 |
| CSS 装饰 | 纯 CSS | 优先使用素材库 SVG/PNG 贴图，CSS 做动画 |
| 全局素材库 | 无 | 建立 `assets/shared_library/`，不进 Git |
| 素材归档 | 无 | 仅归档外部来源素材 |
| 预算公式 | 有 | 删除 |
| HyperFrames | 默认 | 保留 |

## 修改范围

以下文件在本次优化范围内，按阶段逐步修改：

### 管线定义
- `pipeline_defs/vox-paper-collage.yaml`

### Skill 文档（8 个 director + EP + bilingual-spec）
- `skills/pipelines/vox-paper-collage/idea-director.md`
- `skills/pipelines/vox-paper-collage/proposal-director.md`
- `skills/pipelines/vox-paper-collage/script-director.md`
- `skills/pipelines/vox-paper-collage/scene-plan-director.md`
- `skills/pipelines/vox-paper-collage/assets-director.md`
- `skills/pipelines/vox-paper-collage/edit-director.md`
- `skills/pipelines/vox-paper-collage/compose-director.md`
- `skills/pipelines/vox-paper-collage/publish-director.md`
- `skills/pipelines/vox-paper-collage/executive-producer.md`
- `skills/pipelines/vox-paper-collage/bilingual-spec.md`

### 视觉模板
- `skills/pipelines/vox-paper-collage/templates/style_block.md`
- `skills/pipelines/vox-paper-collage/templates/closer.md`
- `skills/pipelines/vox-paper-collage/templates/thumbnail_dna.md`
- `skills/pipelines/vox-paper-collage/templates/video_prompt.md`
- `skills/pipelines/vox-paper-collage/templates/music_prompt.md`

### 产物 Schema（如需要字段变更）
- `schemas/artifacts/brief.schema.json`
- `schemas/artifacts/proposal_packet.schema.json`
- `schemas/artifacts/script.schema.json`
- `schemas/artifacts/scene_plan.schema.json`
- `schemas/artifacts/asset_manifest.schema.json`
- `schemas/artifacts/edit_decisions.schema.json`
- `schemas/artifacts/render_report.schema.json`
- `schemas/artifacts/publish_log.schema.json`
- `schemas/artifacts/decision_log.schema.json`

### 新增基础设施
- `assets/shared_library/`（全局素材库，`.gitignore` 排除）
- 素材库索引规则与 `.meta.json` 格式
- 可能新增工具/脚本：素材库检索、真实照片搜索、国风风格模板等

## 阶段推进计划

每个阶段按以下步骤执行：

1. **修改阶段 skill 和 schema**：根据决策调整该阶段定义。
2. **生成 sample artifact**：用该 stage 的 skill 产出一份示例产物（如 `brief.json`、`proposal_packet.json`）。
3. **人工审批**：你检查 sample artifact 是否满足 review_focus 和 success_criteria。
4. **通过后进入下一阶段**。

### 阶段顺序

1. **idea**：扩展领域、动态选题数量、平台化标题风格、已发布选题去重。
2. **proposal**：动态段落压缩、语义分镜、视觉方向选择、默认中文、删除预算公式。
3. **script**：6 段式检查清单叠加 Fern DNA、paragraph_labels 字段。
4. **scene_plan**：Semantic scene/beat、段落级视觉切换。
5. **assets**：全局素材库集成、真实照片参考、CSS 装饰贴图化。
6. **edit**：基于语义 beat 的动画节奏、build-on/living-paper 比例。
7. **compose**：素材库素材使用、段落级视觉切换渲染。
8. **publish**：素材库归档外部来源素材、缩略图风格适配。

## 验证方式

- **Schema 校验**：每个 sample artifact 必须通过对应该 schema。
- **Review Focus 检查**：对照该阶段 review_focus 逐项确认。
- **人工审批**：你阅读 sample artifact 后回复"通过"或"修改意见"。
- **领域上下文同步**：每阶段新术语实时写入 `CONTEXT.md`。

## 退出条件

- 8 个阶段全部修改并审批通过。
- 生成一份端到端 sample run（从 idea 到 publish 的示例产物链）。
- 更新 `docs/adr/ADR-002-vox-paper-collage-playbook-alignment.md` 记录最终决策。

## 风险

1. **全局素材库增长**：外部来源素材持续累积，需要后续设计生命周期管理。
2. **真实照片版权**：自动搜索的照片需记录来源和版权状态，不能默认商用。
3. **语义分镜主观性**：scene/beat 边界由语义判断，需要 sample artifact 反复校准。
4. **国风风格适配**：现有 VOX 模板偏西方档案，国风需要独立设计模板集合。

## 下一步

结束 grilling session，开始实施 **idea 阶段**。
