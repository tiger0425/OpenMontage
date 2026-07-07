# Fabric Promotion Directed 流水线扩展手册

> 本文件面向希望维护 / 扩展 `fabric-promotion-directed` 流水线的人。
> 阅读前请确认已理解：
> - `pipeline_defs/fabric-promotion-directed.yaml`（stage 与 artifact 编排）
> - `skills/pipelines/fabric-promotion/` 下的 6 个 director
> - `AGENTS.md` 的 4 条红线：NO AD-HOC SCRIPTS / USE SELECTORS ONLY / RESPECT CHECKPOINTS / NO SINGLE-SHOT HTML GENERATION
> - `skills/core/hyperframes.md`（OpenMontage 原生 HyperFrames 桥接文档）
> - `tools/video/hyperframes_compose.py`（实际合成工具）

---

## 1. 扩展模型（四层）

本流水线把"可扩展性"切成四个正交层，每层只改一处，不污染其他层：

| 层级 | 名称 | 控制什么 | 对应文件 | 是否影响其他层 |
|---|---|---|---|---|
| Layer 0 | 叙事骨架（Narrative Skeleton） | 视频的结构/节奏/幕数 | `visual-planning-director.md` Step 1 | 会改变 scene_plan 的 scenes 数与 frame_blueprint 的帧数，但不改变单帧语法 |
| Layer 1 | 复盘可调参数（Retrospective Tunables） | 同面料/同平台再次运行时的默认值 | `.retrospectives/latest.md` + 各 director 的 `Step 0` | 只影响默认值，不改变 pipeline 结构 |
| Layer 2 | 视觉设计系统（Visual Design System） | palette、typography、lighting、motion profile | `visual-planning-director.md` Step 3 + `visual_design.schema.json` | 只影响 OpenMontage 标准 `visual_design.json`，不修改合成工具内部 |
| Layer 3 | 素材生成参数（img2img / TTS / video-gen） | 具体 provider 调用参数 | `directed-asset-gen.md` + 各 Layer 3 provider skill（`image_selector` / `video_selector` / `tts_selector`） | 只影响 asset 质量，不破坏 frame_blueprint 语义 |

**核心原则**：扩展时先判断改哪一层，再动手。不要同时跨两层改。

**v4.0 重大变更**：
- v3.2 及以前错误地把 Layer 2 定义为"引用外部 HyperFrames skill 的语法"（`blueprints-index.md` / `rules-index.md` / `cut-catalog.md` / `frame-presets`）。
- v4.0 纠正为：OpenMontage 有自己的标准视觉设计 artifact（`visual_design.json`），合成交给项目内 `tools/video/hyperframes_compose.py` 的 `hyperframes_compose` 工具。因此 Layer 2 不再引用外部 HF 语法。

---

## 2. Layer 0：添加新的叙事骨架

### 2.1 什么时候加骨架

当现有 8 个骨架（Hook→Reveal→Payoff、Provoke→Justify→Reprise、One-Garment Hero、Garment Cascade、Call and Response、Progression、Monolith、Documentary Frame）都无法服务某种新 brief 类型时，再添加。

常见触发信号：
- 新平台要求（如 YouTube Shorts 的"竖屏 3 秒 hook + 评论区互动"节奏）
- 新面料类型（如科技面料需要"功能证明"结构）
- 新营销目标（如直播切片预告、KOL 二创）

### 2.2 修改步骤

1. 打开 `visual-planning-director.md` Step 1.1。
2. 在骨架列表底部加入新骨架，格式：

   ```markdown
   - **骨架名**（一句话适用场景）：<30 字描述。
     适合 <面料类型 / 平台 / 时长>。
   ```

3. 在 Step 1.2 的"场数示例"里补一条该骨架的典型场数范围。
4. 在 Step 1 的"严禁"列表里增加该骨架**特有的反模式**：
   - 不要让它退化成"5 场固定模板"
   - 不要让它与已有骨架重复（如果重复，说明不该新建，该改现有骨架）
5. 如果新骨架需要特殊时长校验（如必须 6 秒前出现第一个 hook），在 Step 1.3 增加 `assert` 示例。
6. 更新本文件第 7 节的版本号（见 7.1）。

### 2.3 验收标准

- 新骨架不是已有骨架的换皮
- 新骨架有明确的面料 / 平台 / 时长适用范围
- 新骨架有对应的 pitfall 条目，retrospective stage 能识别
- 自洽性脚本仍通过

---

## 3. Layer 1：调整 Retrospective Tunables

### 3.1 Tunables 的语义

Tunables 是"同面料 / 同平台再次运行时，把上次好的参数变成默认值"。它**不是**通用规则，而是经验缓存。

当前 tunables 覆盖：
- `img2img_strength`（面料纹理保留强度）
- `comfyui_denoise_strength`（视频去噪，控制动作稳定性 vs 面料细节）
- `comfyui_steps`（采样步数，影响动作一致性）
- `caption_font_weight`（字幕字重，受平台可读性影响）
- `tts_voice_id`（voxcpm 音色，同平台历史 proven）
- `visual_design` 推荐 palette / typography（同面料历史 proven）

### 3.2 新增一个 tunable

1. 在 `retrospective-director.md` Step 4 的示例代码中增加新的 tunable 提取逻辑。
2. 在 `retrospective-director.md` Step 6 的 markdown 模板里增加对应字段（如 `## 🔧 可调参数` 增加一行）。
3. 在 `idea-director.md` Step 0 和 `visual-planning-director.md` Step 0 增加该 tunable 的读取与落地逻辑。
4. 如果该 tunable 影响 asset 生成，在 `directed-asset-gen.md` 的默认值段引用它。
5. 更新本文件第 7 节的版本号。

### 3.3 调整现有 tunable 的默认值

- 只改 `retrospective-director.md` 的提取逻辑，**不要**在 director 里写死新默认值。
- 原因：默认值应该来自真实运行，而不是维护者的直觉。
- 如果必须给冷启动（无历史）一个默认值，写在 `visual-planning-director.md` Step 0 的 `fallback` 分支里，并标注"无历史时的基线"。

---

## 4. Layer 2：调整视觉设计系统（Visual Design System）

### 4.1 本层边界

v4.0 的视觉设计系统完全由 OpenMontage 标准 artifact `visual_design.json` 承载，由 `visual_design.schema.json` 定义。它包含：

- `palette`：背景、文字、强调、主色、辅色
- `typography`：heading / body 字体、字重、字号
- `design_system`：background_color、lighting_style、global_mood
- `motion_profile`：pace、easing、camera_language

`visual_design.json` 在 `hyperframes_compose` 工具内部被翻译成 HyperFrames CSS 自定义属性（`--color-bg`、`--color-fg`、`--font-heading` 等），具体翻译逻辑由 `tools/video/hyperframes_compose.py` 和 `lib/hyperframes_style_bridge.py` 负责。

### 4.2 添加新的视觉设计字段

1. 若需新增字段，先改 `schemas/artifacts/visual_design.schema.json`。
2. 在 `visual-planning-director.md` Step 3 说明该字段的取值规则。
3. 如果字段会影响合成工具的视觉呈现，检查 `tools/video/hyperframes_compose.py` 的 `_style_bridge` 是否已消费；若未消费，需同步更新（这属于工具层变更，升 major version）。
4. 更新本文件第 7 节版本号。

### 4.3 调整 palette / typography 默认值

- 颜色必须从用户面料原图提取，不能从模板复制。
- 字体必须在 HyperFrames-safe 白名单内：Outfit、Montserrat、Inter、JetBrains Mono、Poppins、Playfair Display。
- 新面料/新平台的推荐 palette 可在 `visual-planning-director.md` 的"面料类型 × design_system"表中增加一行。

### 4.4 与 HyperFrames 的边界

v4.0 不再引用外部 HF skill 的 `frame-presets/`、`blueprints-index.md`、`rules-index.md`、`cut-catalog.md`。这些都不再是 OpenMontage 的扩展点。因此：

- 不要在本流水线的任何 director 中引用 `<HF_SKILL_DIR>` 路径。
- 不要产出 `storyboard.md` / `SCRIPT.md` / `frame.md` / `tokens.json` 等 HF 原生 workspace 文件。
- 不要调用 `build-frame.mjs` / `stage-assets.mjs` / `assemble-index.mjs` / `transitions.mjs` / `audio.mjs` 等外部脚本。

合成阶段唯一入口是 `tools/video/hyperframes_compose.py` 的 `hyperframes_compose` 工具。

---

## 5. Layer 3：新增 / 调整 img2img 参数

### 5.1 为什么所有图像/视频必须用 img2img

面料推广的核心是"保留面料纹理"。文生图（text-to-image）会破坏面料的微观结构，因此：

- 所有 garment image → `image_selector` 走 img2img 模式
- 所有 garment video → `video_selector` 走 `comfyui_video` 的 img2img workflow（默认 `ltx23_i2v` 或同类）
- 任何新增 provider 必须先支持 img2img，否则不予接入

### 5.2 新增一个 img2img 参数

1. 打开 `directed-asset-gen.md`。
2. 在"每帧 asset 生成"的参数字典中增加该参数，并标注：
   - 参数名（英文，与 provider API 一致）
   - 默认值（来自 `brief` 或 `.retrospectives/latest.md`）
   - 影响什么（纹理 / 动作 / 稳定性 / 颜色）
   - 典型调参方向（高更好还是低更好）
3. 如果该参数应被 retrospective 学习，在 `retrospective-director.md` Step 4 增加提取逻辑。
4. 在 `directed-asset-gen.md` 的 review_focus 中增加该参数的校验点。
5. 更新本文件第 7 节的版本号。

### 5.3 调整已有参数

- 只改默认值（优先在 retrospective 中改），不改参数名。
- 参数名必须与 provider API 名一致，避免在生成时做二次映射。
- 如果 provider API 改名，在 `directed-asset-gen.md` 旧名拒绝、新名替换。

---

## 6. 横向扩展：新面料 / 新平台 / 新比例

### 6.1 新面料类型

1. 在 `visual-planning-director.md` Step 3 的"面料类型 × design_system"推荐表中增加一行。
2. 在 `idea-director.md`（如果面料影响前期意图措辞）增加面料描述参考词。
3. 在 `directed-asset-gen.md` 的 img2img 参数说明中补充该面料的特殊注意事项（如"真丝反光强，img2img_strength 不超过 0.75"）。
4. 跑至少一次端到端测试，确认 frame_blueprint 的 `motion_rules` 不自造非法名。
5. 更新本文件第 7 节版本号。

### 6.2 新平台

1. 检查平台输出规格是否已在 OpenMontage 的 `Platform Output Profiles` 中支持（见 README）。
2. 在 `visual-planning-director.md` Step 3 的 palette / typography 推荐表中增加平台备注（如竖版 9:16 的字号可能需要放大）。
3. 在 `publish-copy-director.md` 的平台文案段增加该平台话术模板（标题、标签、正文三段）。
4. 在 `compose-director.md` 阶段 C 的 `profile` 映射中增加新平台到 OpenMontage media profile 的映射（如 `youtube_shorts` → `tiktok`）。
5. 在 `idea-director.md` 的时长→幕数映射中确认新平台的典型时长已被覆盖。
6. 更新本文件第 7 节版本号。

### 6.3 新比例

1. 新比例必须同时被：
   - `image_selector` 的 aspect_ratio 枚举支持
   - `video_selector` 的 comfyui workflow 支持
   - OpenMontage 的 media profile 支持（见 `lib/media_profiles.py`）
2. 在 `visual-planning-director.md` Step 3 的 palette / typography 推荐中说明比例限制（如 1:1 与 9:16 的字号差异）。
3. 如果新比例只影响 asset 而不影响设计，只需改 `directed-asset-gen.md`。
4. 如果新比例影响排版安全区，在 `visual-planning-director.md` 的 `subtitle_box_position` 字段说明中体现。

---

## 7. 版本与同步规则

### 7.1 版本号定义

本流水线使用 SemVer，但把三个版本绑定：

- `pipeline_defs/fabric-promotion-directed.yaml` 顶层的 `version`
- 6 个 director 文件头部的版本标记（如 `v4.0`）
- 本文件 `EXTENDING.md` 的版本（文末标注）

### 7.2 什么时候升版本

| 变更类型 | 版本升级 | 例子 |
|---|---|---|
| 只改文字、修复拼写、更新示例 | 不升 | typo fix |
| 新增 Layer 1 tunable、新增 Layer 0 骨架、新增 Layer 2 视觉字段 | 升 minor | v4.0 → v4.1 |
| 改变 artifact schema、改变 stage 顺序、改变合成工具调用边界、移除已有 artifact | 升 major | v4.x → v5.0 |
| 破坏性重命名 frame_blueprint 字段 | 升 major | v4.x → v5.0 |

### 7.3 同步清单

每次发布新版本，必须同时改：

- [ ] `pipeline_defs/fabric-promotion-directed.yaml`：`version` 字段
- [ ] `idea-director.md` 头部版本标记
- [ ] `visual-planning-director.md` 头部版本标记
- [ ] `directed-asset-gen.md` 头部版本标记
- [ ] `compose-director.md` 头部版本标记
- [ ] `publish-copy-director.md` 头部版本标记
- [ ] `retrospective-director.md` 头部版本标记
- [ ] `EXTENDING.md` 文末版本标注
- [ ] 运行 YAML schema 校验（`lib.pipeline_loader.load_pipeline`）
- [ ] 运行 artifact 依赖闭环检查
- [ ] 运行 AGENTS.md 4 红线检查，确保全部 PASS
- [ ] 运行外部 HF 引用 grep，确保无 `<HF_SKILL_DIR>` / `build-frame.mjs` / `assemble-index.mjs` / `stage-assets.mjs` / `transitions.mjs` / `audio.mjs` 残留

---

## 8. 测试与验证清单

任何扩展 PR 在合并前必须完成以下检查：

### 8.1 结构检查

- [ ] 自洽性脚本通过：所有 `required_artifacts_in` 都有 producing stage
- [ ] 6 个 director 文件都在 `skills/pipelines/fabric-promotion/` 中，无孤儿文件
- [ ] YAML 的 `required_skills` 列表与实际文件一一对应
- [ ] 版本号已同步（见 7.3）

### 8.2 AGENTS.md 红线检查

- [ ] NO AD-HOC SCRIPTS：没有新增一次性 Python 脚本绕过 harness
- [ ] USE SELECTORS ONLY：新增 provider 调用通过 `image_selector` / `video_selector` / `tts_selector`
- [ ] RESPECT CHECKPOINTS：新增 stage 有正确的 `checkpoint_required` / `human_approval_default`
- [ ] NO SINGLE-SHOT HTML：合成仍走 `hyperframes_compose` 工具，没有新增自写 HTML 的 step

### 8.3 OpenMontage 标准 Artifact 检查

- [ ] `scene_plan.json` 满足 `schemas/artifacts/scene_plan.schema.json`
- [ ] `script.json` 满足 `schemas/artifacts/script.schema.json`
- [ ] `visual_design.json` 满足 `schemas/artifacts/visual_design.schema.json`
- [ ] `asset_manifest.json` 满足 `schemas/artifacts/asset_manifest.schema.json`
- [ ] `edit_decisions.json` 满足 `schemas/artifacts/edit_decisions.schema.json`
- [ ] `render_report.json` 满足 `schemas/artifacts/render_report.schema.json`

### 8.4 扩展点检查

- [ ] Layer 0 变更：新骨架有反模式条目，不与其他骨架重复
- [ ] Layer 1 变更：新 tunable 被 `retrospective-director.md` 提取并被 `idea-director` / `visual-planning-director` 读取
- [ ] Layer 2 变更：新字段已入 `visual_design.schema.json`，且 `visual-planning-director.md` 有取值规则
- [ ] Layer 3 变更：新增参数仍支持 img2img，不引入 text-to-image 路径

---

## 9. 常见错误与正确做法

| 错误 | 为什么错 | 正确做法 |
|---|---|---|
| 在 `visual-planning-director.md` 里引用外部 HF `blueprints-index.md` | v4.0 不再使用外部 HF 语法 | 用 OpenMontage 标准 `visual_design.json` + `frame_blueprint.motion_rules` |
| 在 `directed-asset-gen.md` 里直接 import `GoogleImagen` | 违反 USE SELECTORS ONLY | 走 `image_selector` |
| 在 `compose-director.md` 里写 `window.__timelines.push` 或引用 `<HF_SKILL_DIR>/scripts/...` | 外部 API 不存在或不可控 | 只调用项目内 `hyperframes_compose` 工具 |
| 新增参数时同时改 `frame_blueprint.json` schema 和 `directed-asset-gen.md` | 跨两层改，容易漏 | 先判断参数属于 Layer 3，只改 asset 生成层 |
| 给新面料写死一套默认参数 | 没经过真实运行验证 | 先跑 baseline，用 retrospective 沉淀 |
| 版本号只改 YAML 不改 director | 版本不一致会导致 agent 读错 skill | 按 7.3 同步清单全部改 |
| 产出 `storyboard.md` / `SCRIPT.md` / `frame.md` / `tokens.json` | 这些不是 OpenMontage 标准 artifacts | 产出 `scene_plan.json` / `script.json` / `visual_design.json` / `frame_blueprint.json` |

---

## 10. 扩展示例：添加一个"功能证明"骨架

假设科技面料 brief 增多，需要"功能证明"骨架：

1. 在 `visual-planning-director.md` Step 1.1 增加：

   ```markdown
   - **Proof by Function**（功能证明）：每一幕先展示面料的一项功能（透气/防水/抗
     皱），然后用成衣动作证明它。适合科技面料 / 运动服 brief。
   ```

2. 在 Step 1.2 增加场数示例：

   ```markdown
   - Proof by Function 可能 4-6 场（每个功能 1 场 + hook + 收尾）
   ```

3. 在 Step 1 的"严禁"列表增加：

   ```markdown
   - 把功能证明写成"5 个功能各 1 场"的固定 5 幕模板（除非 brief 真需要 5 个功能）
   - 用"旁白念参数"代替"画面展示功能"（如"透气率 99%"应配汗水蒸发的视觉）
   ```

4. 在 Step 1.3 的时长校验里，可补充：

   ```python
   # Proof by Function 每个功能至少 3 秒才能被看清
   if skeleton == "Proof by Function":
       for scene in scene_plan["scenes"]:
           if scene.get("kind") == "feature_proof":
               assert scene["end_seconds"] - scene["start_seconds"] >= 3.0
   ```

5. 更新 `EXTENDING.md` 文末版本号。
6. 运行验证脚本，确认通过。

---

## 11. 与 HyperFrames 版本解耦策略

HF 本身会升级，但本流水线不应频繁随 HF 升 major。解耦原则：

- HF 新增 CLI flag / 命令：`hyperframes_compose` 工具内部处理；若 director 需用新 flag，升 minor。
- HF 删除/改名 CLI 命令：`hyperframes_compose` 工具内部处理；若影响本 pipeline 的调用参数，升 major。
- HF 新增 registry block：不影响本 pipeline，除非用户主动使用。
- HF 改变 HTML/CSS 契约：`hyperframes_compose` 工具内部处理，升 major。

**v4.0 之后，本流水线不再依赖 HF 的 `storyboard-format.md` / `script-format.md` / `frame-presets` / `blueprints-index.md` / `rules-index.md` / `cut-catalog.md`。HF 升级对这些文件无直接影响。**

---

## 12. HyperFrames 版本管理

HyperFrames CLI 更新频繁。本流水线的版本管理完全由项目内 `tools/video/hyperframes_compose.py` 负责：

- 工具首次运行时会通过 `npm view hyperframes version` 探测可用版本。
- 运行时要求 Node.js ≥ 22、FFmpeg、npx 都在 PATH 上。
- 如果环境不满足，工具会返回 `runtime_available: false` 及安装说明。

本流水线的 director 不应再手动探测或锁定 HF 版本。`render_report.json` 中记录的 `hyperframes.cli_version` 由 `hyperframes_compose` 工具返回的 `data.steps` 提供。

如需 reproducible builds，应通过固定 OpenMontage 代码版本（commit / tag）而非固定 HF CLI 版本，因为 `hyperframes_compose` 工具内部的调用方式才是本 pipeline 的受控接口。

---

**EXTENDING.md 版本：v4.0**
