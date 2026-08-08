# ADR-002: vox-paper-collage 管线对齐 made-by-ai-playbook-zh.md 优化决策

- **状态**: Accepted
- **日期**: 2026-08-05
- **决策者**: 用户 + AI Agent (grill-with-docs session)
- **影响范围**: `vox-paper-collage` 管线及其 skill、schema、模板、产物

## 背景

`vox-paper-collage` 管线已存在并运行，但产出的视频存在画面质感不足、创意单调、内容与画面不符、选题和脚本结构不如 `made-by-ai-playbook-zh.md`、动画节奏不适合等问题。用户希望将 Playbook 的创作理念注入 Pipeline，但保留 8 阶段工程结构，按阶段逐个修改并验证。

本次 grilling session 确定了以下关键决策。

## 决策

### D1: 阶段结构不变

保留 idea → proposal → script → scene_plan → assets → edit → compose → publish 的 8 阶段顺序和名称，仅修改每个阶段内部规则与产物。

### D2: 默认旁白语言改为中文

`narration_language` 默认从 `en` 改为 `zh`。英文能力保留，bilingual-spec 仍然双语言维护。

### D3: Idea 阶段多样化

- 领域从 8 个 niche 扩展到多个领域。
- 候选选题数量由 stage 根据领域动态决定，不再固定 10 个。
- 标题风格由 `target_platform` 决定：YouTube/TikTok/Bilibili 偏好奇心爆款；LinkedIn/企业宣传偏克制纪录片。
- 仅已发布选题进入黑名单，防止重复选题；idea/proposal 阶段放弃的选题不进入黑名单。

### D4: Proposal 阶段全局参数调整

- 时长：按 platform 推荐，用户可 override。
- 视觉方向：按 niche 默认推荐（crime/disaster → 旧报纸，technology → 蓝图，money → 账本，space → 星图），同时列出可选风格集合（旧报纸、国风、蓝图、羊皮纸、现代杂志等）。用户可提供参考图或描述 override。
- 国风风格：可选，不默认按语言触发。
- 删除预算公式：前期不做预算控制，成本估算可保留为可选占位字段。
- HyperFrames 保留为默认 render_runtime。

### D5: 脚本结构采用 6 段式检查清单叠加 Fern DNA

脚本输出形式仍为连续旁白（Fern DNA），但内部生成必须满足 6 段式内容检查：Viral Hook → Quick Introduction → Main Story → Turning Point → Big Picture → Powerful Ending。`script` artifact 增加 `paragraph_labels` 字段，标记每段属于 6 段式中的哪一段。

### D6: 动态段落压缩

根据 `target_duration` 将 6 段式压缩为：
- 30s–1min：3 段式（Hook → Core → Ending）
- 1–2min：4 段式（Hook → Story → Turning → Ending）
- 3–5min：5 段式（Hook → Intro → Story → Turning → Ending）
- 8min+：6 段式

### D7: 分镜从 voice-led 改为语义分镜

- Scene 边界由 6 段式段落决定（语义分镜）。
- Beat 是段落内的语义单元，时长由内容复杂度决定，而非语音 segment 或固定秒数。
- 简单 beat 3-5s，标准 5-8s，复杂 8-12s，关键 reveal 可达 15s。
- 总时长约束 target_duration ±5%。

### D8: 段落级视觉切换

`scene_plan` 阶段根据 `paragraph_labels` 为不同段落设计不同视觉功能。例如 Hook 用强冲击画面，Turning Point 用对比视觉，Big Picture 用宏观图，Ending 用极简留白。

### D9: 数据真实性与参考图规则

- `real_data`（含数字/排名/行情）：使用真实数据源（yfinance、官方文档），生成 matplotlib 参考图，再走生图风格化。禁止 AI 编造数字。
- `real_content`（真实人物/地点/产品）：必须基于真实照片或用户提供图像做参考图，再走生图风格化。不允许纯生成。
- `creative`（抽象概念）：纯生成。
- `css`（装饰）：优先使用素材库贴图，CSS 负责动画。

### D10: 建立全局素材库

- 位置：`assets/shared_library/`，被 `.gitignore` 排除。
- 内容：图片、音频、字体、视频片段。
- 索引：文件目录 + 每个素材配 `.meta.json` 元数据（标签、来源、描述、使用次数等）。
- 归档规则：仅归档外部来源素材（用户上传、互联网搜索、购买/授权）；AI 生成内容不归档。
- 使用流程：优先在本地素材库搜索，找不到再搜索互联网或用户上传，获取后自动归档。

### D11: CSS 装饰贴图化

CSS 装饰（胶带、图钉、印章、标签、文字等）不再依赖纯 CSS 绘制，优先从全局素材库取精美 SVG/PNG 贴图，CSS 仅负责定位、入场动画和微动。

## 后果

### 正面

- 视频画面质感、叙事吸引力、内容与画面一致性显著提升。
- 真实内容可追溯，降低 AI 幻觉风险。
- 中文视频默认路径更自然，国风风格可选。
- 全局素材库减少重复搜索和生成成本。

### 负面与风险

- 全局素材库持续增长，需后续生命周期管理。
- 真实照片搜索需处理版权和来源记录。
- 语义分镜边界主观，需通过 sample artifact 反复校准。
- 国风风格需要独立设计模板，不能简单复用西方档案模板。
- 删除预算公式后，成本意识在 proposal 阶段变弱，需要后续重新评估是否恢复。

## 相关文件

- `CONTEXT.md`
- `docs/optimization-charters/vox-paper-collage-playbook-alignment.md`
- `pipeline_defs/vox-paper-collage.yaml`
- `skills/pipelines/vox-paper-collage/*.md`
- `skills/pipelines/vox-paper-collage/templates/*.md`
- `schemas/artifacts/*.schema.json`
