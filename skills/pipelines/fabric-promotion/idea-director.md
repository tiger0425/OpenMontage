# 面料推广 - Idea Director（创意总监）v4.0

## 角色
分析面料特性，定义面料推广视频的创作方向。同时负责 **render_runtime 声明**（按 AGENT_GUIDE 治理要求）。

> v3.0 调整：本 stage 只产出面料分析的"前期意图"——design_system 给全
> 局色调 / 光影基调，beat_plan 每幕一句 composition_rule 即可。
> **不要把镜头级规划塞进 brief** —— 镜头级规划交给 STAGE 2
> visual_planning (visual-planning-director) 展开。本 stage 一旦想
> 写"每帧要 X 动作"、"字幕在第几秒出现"就停手；那是 STAGE 2 的工作。

## 输入
- 用户面料实拍图（用户提供）
- 品牌信息（品牌名、系列名）
- 目标平台与时长
- `.retrospectives/latest.md`（若存在）— 上次同面料 / 同平台运行沉淀的经验

## 流程

> **⚠️ 路径规范核心警告**：  
> Universal Harness (omo.py) 始终在 OpenMontage 根目录执行！因此所有针对项目内工件的读取/写入（如 `artifacts/...`, `assets/...`, `renders/...`）都**必须带有 `projects/{project_name}/` 前缀**。切勿直接写相对路径，否则会污染根目录！全局复盘可放在 `.retrospectives/` 下。

### Step 0: 读取全局知识库（自我学习接口）
<!-- NOTE: Next run MUST read the knowledge base from .retrospectives/knowledge_base.md to inherit tuned parameters and avoid past mistakes. -->

**⚠️ 强制动作**：
你不能仅仅是假装执行下面的伪代码！作为 Agent，你**必须在此时立刻使用文件查看工具（如 `view_file`）读取根目录下的 `.retrospectives/knowledge_base.md`**（如果文件存在的话）。

读取后，你必须执行以下动作：
1. **吸收全局经验**：仔细阅读知识库中的“全局避坑指南 (Global Practices)”，在后续的整个流程中严格避开这些已知的坑。
2. **提取专属参数**：查找知识库中是否有针对你即将分析的面料类型（如 `Tweed`, `Linen` 等）的专属条目。如果有，将对应的 `tunables` 采纳并准备传递给 STAGE 2 visual_planning。

```python
# 伪代码演示逻辑：
kb_content = read(".retrospectives/knowledge_base.md")
# 1. 记下全局避坑规则
# 2. 如果后续查明面料为 "Linen"，则在 kb_content 寻找 Linen 专属的 tunables
```

提取到的 tunables **不在本 stage 实施，具体实施在 STAGE 2 frame_blueprint**。本 step 只
负责把它们转写到 brief.metadata.tunables_inherited。

### Step 1: 面料分析
使用 agent 视觉能力（或 `visual_qa` 工具，如注册可用）分析面料：

```
分析此面料图像，提供：
1. 面料类型（真丝、棉、羊毛、亚麻、天鹅绒等）
2. 质感特征（光滑、粗糙、梭织、针织等）
3. 图案类型（纯色、花卉、几何、抽象等）
4. 色彩组成（主色、辅色、点缀色）
5. 克重与垂感（轻薄、中等、厚重）
6. 视觉质感（光泽、哑光、反光等）
7. 风格关联（优雅、休闲、奢华、运动等）
8. 推荐应用场景
```

### Step 2: 产出 3 个成衣概念
基于面料分析，提出 3 个差异化的成衣方向：

**概念 A - 正式/优雅**
- 成衣类型：[如：晚礼服、西服套装、鸡尾酒裙]
- 剪影：[合体、流线、结构化]
- 目标场合：[如：晚宴、婚礼、正式场合]
- 视觉重点：[如：垂坠动态、光泽高光]

**概念 B - 日常/实穿**
- 成衣类型：[如：衬衫、休闲连衣裙、开衫]
- 剪影：[宽松、半合体]
- 目标场合：[如：办公、早午餐、旅行]
- 视觉重点：[如：质感细节、色彩表现]

**概念 C - 潮流/个性**
- 成衣类型：[如：个性外套、先锋设计]
- 剪影：[夸张、建筑感]
- 目标场合：[如：时尚编辑、秀场、展示]
- 视觉重点：[如：运动感、戏剧化光影]

### Step 3: 视觉意图（前期动机，非镜头级规划）
> v3.0 重命名（原"视觉与分镜规划"）— 不在本 stage 写 storyboard。
> 本 step 写的只是给 STAGE 2 visual_planning 的"初始语义"。

"视觉前置"是核心原则：在生成任何素材前，必须先定下视觉调性的初始意图。
本 stage 只写"前期意图"——基调色彩 + 每幕一句构图意图——不写镜头级
描述（动作 / 时长 / 转场）。

1. **定义全局视觉意图 (Design System 基调)**：确定全局背景色（`background_color`，
   如 `#08050a` 暗黑调或 `#f3f4f6` 明亮调）和光影风格（`lighting_style`）。
2. **定义分镜节拍 (Beat Plan，每幕一句)**：按概念性质与 target_duration 适配场数
   （短 15s 约 2-3 幕、30s 约 3-5 幕、60s+ 约 5-8 幕——**不硬编码**，仅给出适配区间；
   具体骨架与场数交给 STAGE 2 visual_planning 的骨架菜单决定）。
   为每一幕（Scene）强制设定一句话**构图意图 (`composition_rule`)**。
   - ⚠️ **核心分离原则**：生图只负责"主体+纯净背景"，排版留白交给合成阶段。
   - 每幕的 composition_rule 应是"写给合成阶段用的排版意图"，**非镜头动作描述**
     （如.getPosition asset in left flex column, text in right flex column 是适合的；
     "model_turn 30° right, camera push-in" 这种动作描述应留到 STAGE 2 frame_blueprint
     的 motion_rule 字段）。

### Step 4: render_runtime 声明
按 AGENT_GUIDE **"Present Both Composition Runtimes (HARD RULE)"** 执行：

1. 运行 preflight 检查 Remotion 与 HyperFrames 可用性
2. **当两者均可用时**：向用户呈现两个选项，附简要说明：
   - **HyperFrames（推荐）**：CSS/GSAP 排版适合面料推广的产品感呈现，OpenMontage 通过 `hyperframes_compose` 工具原生调用
   - **Remotion**：React 组件栈适合数据图表密集型内容，但与本流水线无现成组件复用
3. 等待用户确认后锁定 `render_runtime`
4. 在 brief 的 `metadata.render_runtime_selection` 中记录决策（含 `options_considered`、`selected`、`rationale`）

**当仅一个可用时**：说明原因并直接使用，但仍需记录决策。

### Step 5: 写入 brief artifact
按 `schemas/artifacts/brief.schema.json` 校验，确保包含：
- `target_platform`: `"bilibili"` 或 `"xiaohongshu"`（面料推广的主投放平台）
- `target_duration_seconds`: 建议 30~90 秒（面料推广视频的有效时长区间）
- 3 个成衣概念写入 `angle_options`
- 面料分析结果写入 `key_points`
- **`design_system` 和 `beat_plan`**：仅写"前期意图"（背景基调 + 每幕一句构图意图），
  不写镜头级 motion_rule / 时间码 / 转场规范——后者归 STAGE 2 visual_planning
- `metadata.render_runtime_selection` 包含完整的决策记录
- `metadata.tunables_inherited`（若 Step 0 命中历史 retrospective）：把_TUNABLES
  从 `.retrospectives/latest.md` 转入，给 STAGE 2 visual_planning 的
  frame_blueprint.json 强制注入默认参数

## 输出
Schema-valid `brief` artifact，包含：
- 面料分析结果
- 3 个成衣概念（含详细描述）
- 目标平台与时长
- 视觉风格方向
- 品牌信息
- render_runtime 决策记录
