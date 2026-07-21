# 面料知识教育管线 — Spec（PRD）

## 问题陈述

作为面料商，用户有面料实物（照片、成分、克重），想用 OpenMontage 系统批量生产**教育性面料知识内容**，在各个平台建立专家权威。现有管线（`fabric-promotion-directed`）专注**销售转化**——展示面料美感和成衣效果，让观众想买。但用户需要的是**另一条内容线**：让观众变聪明、学会辨别面料好坏、避开常见坑。两者目标、内容结构、产出形态完全不同，不应混用同一管线。

## 解决方案

新建 `fabric-education` 管线，以**笔记先行、视频可选**为核心理念。每块面料输入后，Agent 先分析面料事实并生成多平台适配的图文笔记；用户看笔记质量后再决定是否/如何出视频。贵重的、知识点丰富的面料进入深度视频管线，普通面料只出知识切片或仅停在笔记。

## User Stories

1. 作为一个面料商，我希望上传**一张面料照片和基础资料**（名称、成分、克重），Agent 就能自动产出内容，减少我的人工参与
2. 作为一个面料商，我希望 Agent 在面料信息不足时能**主动追问**（如织物组织、后整理工艺、适用季节），而不是凭猜想写错内容
3. 作为一个面料商，我希望系统先产出**图文笔记**让我审核，确认面料事实准确后再决定是否出视频，避免把错误扩散到视频
4. 作为一个面料商，我希望同一块面料的笔记能**自动适配小红书、公众号、知乎、朋友圈**四个平台的格式和风格
5. 作为一个面料商，我希望小红书笔记是**图文结合**的（多张配图+扼要文字），图片由 Agent 用面料原图生成辅助说明图
6. 作为一个面料商，我希望公众号文章是**深度长文**，可以系统性地讲清楚一个知识点
7. 作为一个面料商，我希望知乎内容是**偏测评/科普风格**，有干货论证
8. 作为一个面料商，我希望朋友圈文案是**短平快**的（150 字以内），引导去长内容平台看全文
9. 作为一个面料商，我希望系统根据面料知识深度**自动评级**（普通/深度），并给出视频产出建议
10. 作为一个面料商，对于**深度面料**，我希望系统自动生产完整知识视频（B站/视频号，3-8分钟），包含配音、BGM、面料特写和对比测试画面
11. 作为一个面料商，对于**普通面料**，我希望系统只出 1 条 15-30 秒的竖版知识切片（小红书/朋友圈），不浪费资源做长视频
12. 作为一个面料商，当面料知识量不大时，我希望可以**选择不出视频**，只发笔记即可
13. 作为一个面料商，我希望深度视频的**配音音色在多段之间一致**（用 VoxCPM chain cloning），不跳戏
14. 作为一个面料商，我希望**所有生成的面料画面必须忠实于实物**（通过 img2img 保留纹理），不虚构面料属性
15. 作为一个面料商，我希望**笔记和视频中的面料知识点必须基于事实**（fabric_facts 不可虚构），Truth-Gate 跟现有推广管线一致
16. 作为一个面料商，我希望视频的**背景音乐风格与面料调性匹配**（如亚麻配轻音乐，科技面料配电子）
17. 作为一个面料商，我希望**完整知识视频的时长在 3-8 分钟**，有完整的叙事结构（提出问题→分析原因→给出结论）
18. 作为一个面料商，我希望完整视频能生产**知识切片**（15-60s），用于小红书/朋友圈分发
19. 作为一个面料商，我希望系统产出后自动生成各平台的**发布文案**（标题、标签、摘要）
20. 作为一个面料商，我希望每次生产结束后系统**自动复盘**，记录面料类型、平台、参数和经验，持续优化后续内容

## Implementation Decisions

### 1. 新增 `fabric-education` 管线（独立于推广管线）

新建 `pipeline_defs/fabric-education.yaml`，六个 stage：

| Stage | 名称 | 产出 | 审批点 |
|-------|------|------|--------|
| 1 | `brief` | `fabric_edu_brief` | ✅ 用户确认面料事实 |
| 2 | `notes` | `note_manifest` | ✅ 用户审核笔记内容 |
| 3 | `decide` | N/A（决策路由） | ✅ 决定出不出视频 |
| 4 | `video` | `edit_decisions` + `render_report` | ❌ 自动（短）或 ✅（长） |
| 5 | `publish` | `publish_copy` | ✅ 发布文案确认 |
| 6 | `retrospective` | `retrospective` | ❌ 自动 |

### 2. 新增 artifact schema

**`fabric_edu_brief.schema.json`** — 教育版面料简报：
- `fabric_name`, `composition`, `weight`（来自用户）
- `weave`, `finishing`, `season`（Agent 可追问）
- `knowledge_depth`（`basic` / `deep`，Agent 自动评级）
- `pitfalls`（该面料常见的坑，Agent 从行业知识推导）
- `comparison_materials`（易混淆的材质清单，如"真丝 vs 天丝 vs 醋酸"）
- `educational_angle`（此面料的推荐教育切入点）

**`note_manifest.schema.json`** — 笔记产出清单：
- `core_article`（核心长文，Markdown）
- `platform_versions[]`：每个平台一个版本
  - `platform`: bilibili / xiaohongshu / wechat_public / zhihu / moments
  - `title`
  - `body`
  - `images[]`：配图路径
  - `tags[]`
- `images[]`：生成的配图清单，每张图标注 `educational_role`（如 `microscopic_detail`, `comparison_diagram`, `care_label_explained`）
- `fabric_origin_image`：用户原始面料图路径

### 3. 无新工具——完全复用

| 能力 | Provider | 路由方式 |
|------|----------|----------|
| 图片生成 | Google Imagen | `image_selector`（img2img 模式） |
| 配音 | VoxCPM（fallback Piper） | `tts_selector` |
| 音乐 | Pixabay | 直接调用 |
| 视频生成 | ComfyUI + LTX 2.3 | `comfyui_video`（img2img 模式） |
| 视频合成 | HyperFrames | `video_compose`（render_runtime="hyperframes"） |

均沿用现有 Provider Lockdown 规则。教育管线所需配图（对比图、示意图、原理图）也通过 img2img 生成，以面料原图为底图进行风格化。

### 4. Stage 2（notes）的配图策略

这是教育管线与推广管线的关键差异之一。推广管线配图是为了好看（展示成衣），教育管线配图是为了**说明知识点**。Agent 在生成配图时按需选择：

- 面料微距特写（展示织法、密度）
- 对比图（如正品 vs 仿品、不同支数对比）
- 示意图（如"面料如何织造"示意）
- 洗护标签解析（用面料原图生成标注版）
- 燃烧/水洗测试场景（关键避坑）

所有配图以用户面料原图为底图，走 `image_selector` 的 img2img 模式。

### 5. Stage 3（decide）决策逻辑

`fabric_edu_brief.knowledge_depth` 决定了路由：

- `deep` → 走 Stage 4a（full video, 3-8min）
  - 自动产出完整脚本、场景规划、配音、BGM
  - 产出后自动切出 1-2 条知识切片（用于小红书/朋友圈）
  - 需要审批
- `basic` → 走 Stage 4b（short clip, 15-30s）
  - 只出一条竖版核心知识切片
  - 自动推进
- 如果用户仅想多发笔记不产出视频，在 Stage 3 选中止管线

### 6. 知识视频叙事结构

深度视频使用教育性叙事骨架，非推广管线的展示性骨架。推荐 5 段结构：

```
1. 钩子（15-30s）："90% 的人不知道 XX 面料有个坑"
2. 问题（30-60s）：这个坑是什么？为什么消费者常踩？
3. 拆解（60-120s）：用测试/对比/微距展示真相
4. 解决方案（30-60s）：怎么辨别/选择/打理
5. 总结 + 引导（15-30s）：记住这一条就够了
```

### 7. 扩展目录结构

```
skills/pipelines/fabric-education/
├── brief-director.md       # Stage 1
├── notes-director.md        # Stage 2
├── video-planning-director.md  # Stage 4a/4b
└── publish-director.md      # Stage 5

schemas/artifacts/
├── fabric_edu_brief.schema.json   # 新增
└── note_manifest.schema.json      # 新增
```

`retrospective` stage 复用现有 `retrospective-director.md` 模式，知识点沉淀入 `.retrospectives/fabric-education/`。

## Testing Decisions

### 测试哲学

遵循代码库现有模式：只测公开行为（artifact schema、pipeline 结构、工具接口），不测 Agent 的 LLM 输出质量。

### 测试模块

**1. Schema 合约测试**（最高 seam，优先，无需新 seam）

遵循 `tests/contracts/test_phase0_contracts.py` 的 `TestSchemas` 模式：

- 新增 `sample_artifact("fabric_edu_brief")` 返回最小 schema-valid 样本
- 新增 `sample_artifact("note_manifest")` 返回最小 schema-valid 样本
- `test_fabric_edu_brief_validates` — 验证有效样本
- `test_fabric_edu_brief_rejects_invalid` — 验证缺失必填字段被拒绝
- `test_note_manifest_validates` — 同理
- `test_note_manifest_rejects_invalid` — 同理

**2. Pipeline 结构测试**

遵循 `test_phase0_contracts.py` 的 `TestPipelineManifests` 模式：

- `test_fabric_education_manifest_loads` — 加载 YAML 不抛异常
- `test_fabric_education_stages_have_skills` — 所有 stage 有 skill 引用
- `test_fabric_education_artifact_dependencies_close` — 所有 `required_artifacts_in` 都能被上游 stage produce

**3. Note 产出结构的端到端验收**（可选，若提供 note_gen 工具）

如果 `notes` stage 被实现为一个受控工具（而非纯 LLM 自由写），则按 `tests/tools/test_*.py` 模式增加工具级别测试：

- 输入 fabric_edu_brief 样本
- 输出 note_manifest 且 schema-valid
- 输出涵盖所有四个平台
- 不检测文案质量，只检测结构合规

### Prior Art

- `tests/contracts/test_phase0_contracts.py::TestSchemas` — schema 验证测试
- `tests/contracts/test_phase0_contracts.py::TestPipelineManifests` — pipeline 加载测试
- `tests/contracts/test_phase1_contracts.py` — artifact 依赖闭环检查
- `tests/tools/test_hyperframes_compose.py` — 工具级别测试

## Out of Scope

- **不修改现有推广管线**（`fabric-promotion`, `fabric-promotion-directed`, `fabric-showcase`）
- **不新增底层 provider**（沿用现有 Provider Lockdown）
- **不修改现有 tool**（只有 `hyperframes_compose` 等已有工具）
- **不支持交互式直播/实时问答内容**
- **不支持电商带货风格的口播**
- **不接入新的图片/视频/语音生成服务商**
- **不处理生产流程外的环节**（如面料仓储管理、销售跟进、客服）

## Further Notes

### 与 `fabric-promotion-directed` 管线的关系

两条管线**平行共存**，面向不同内容目标。同一块面料可同时走两条管线：一条产出销售型视频（推广），一条产出知识型笔记+视频（教育）。用户根据发布节奏自主选择。

### Provider Lockdown 一致性

教育管线受同样 Provider Lockdown 约束。这是由 `AGENT_GUIDE.md` 和 `AGENTS.md` 的 Provider Lockdown skill 强制保证的——Agent 在启动任何管线前必须加载该 skill。

### 内容 Truth-Gate

教育管线的 Truth-Gate 比推广管线更严格：推广管线要求"面料成分不虚构"，教育管线进一步要求"知识点有行业经验的背书"。Agent 在 `fabric_edu_brief` 中列出的 pitfall（常见坑）必须基于用户作为面料商的真实经验，不能编造。

### 知识沉淀

每次运行结束后，retrospective stage 记录：
- 该面料的 pitfall 关键词
- 哪个平台的笔记互动预期最高
- 配图风格偏好（写实 vs 卡通 vs 对比图）
- 视频叙事框架的有效性评估

持续积累后，相同面料类型（如所有亚麻类）的知识点可逐步模板化。
