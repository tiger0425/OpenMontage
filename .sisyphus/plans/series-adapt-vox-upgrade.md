# Series-Adapt Vox 风格升级计划（借鉴 vox-director）

## 摘要

基于对外部项目 [Alisa0808/vox-director](https://github.com/Alisa0808/vox-director)（930★，MIT，Vox 纸拼贴解说视频的端到端 Agent Skill）的深入研究，将其经实战验证的 Vox 拼贴方法论翻译为 HyperFrames/GSAP 路线的可执行规范，注入 `series-adapt` 管线的 4 个导演技能（rewrite / scene / asset / compose）。目标：提升系列视频的视觉节奏密度、拼贴真实感与跨集一致性，不改变既有管线结构、不引入 AI 视频模型路线。

## 背景

### vox-director 核心方法论（研究结论）

1. **LOOK 层**：图像提示词 5 部分结构——STYLE BLOCK（每 beat 逐字复用，保证一部影片感）+ SCENE 以独立剪贴片描述（clear edges + 各自 drop shadow，为动效提供可分离图层）+ 每 beat 一个大胆纯色背景 + 内嵌大标题（文字烘烤进图，视频模型会糊字）+ 技术参数。附 9 个主题预设（american-retro / swiss-modern / punk-zine / soviet-constructivist / chinese-ink 等）。
2. **STORY 层**：14 种叙事弧库 + topic→arc 启发式 + hook≤3s + beat 计数表（30s→6–8 beats，60s→10–12 beats）。
3. **节奏层**：每 beat 拆 2 shots（wide 定场 + detail 切入），单 shot 3–6s 且 ≤7s；camera_move 硬约束词表（static/push_in/pull_out/pan/tilt/parallax/element），相邻不重复，static 只留给 payoff。
4. **能量引擎**：element_motion 是动效能量的来源——每 shot 多元素同时动（刚性纸片，禁止 morph/warp），hero 元素（纸鸟/硬币）偶尔飞过全场作为关键节拍，不是每帧都用。
5. **本地关键帧引擎**（与我们 HyperFrames 思路最接近）：逐元素飞入组装、模糊占位解决 ghost 重影、`back` 弹性落地纸感、`pop_settle` 原地放大。

### 我们现状与差距

| 维度 | 现状 | 差距 |
|---|---|---|
| 图像提示 | `image_prompt_prefix` 风格块存在，但 `generation_direction` 无结构化模板 | 缺 5 部分结构、缺"独立剪贴片描述"、缺"每场景单色背景"规则 |
| 叙事结构 | rewrite 阶段自由撰写 | 无系统化叙事弧库与 hook 模式库 |
| 运动规则 | 11 种入场动画 + 相邻不同（较松散） | 缺 camera_move 硬约束词表、缺 static 留给 payoff 的规则 |
| 动效密度 | GSAP 动效偏保守（pan-zoom / chart-reveal 为主） | 缺 element_motion 多元素同时动、缺 hero 飞行元素 |
| 纸感细节 | 有 paper SFX | 缺 GSAP 纸感动效（back 弹性、模糊占位、pop_settle） |

## 目标

1. 将 vox-director 的 LOOK / STORY / 节奏三层方法论固化为 series-adapt 管线的参考库与导演技能规范
2. 提升单集视觉节奏密度：长场景内每 4–7s 一个视觉事件，杜绝"死静长场景"
3. 提升拼贴真实感：图像天生有层次（独立剪贴片 + 单色背景），GSAP 动效带纸感
4. 保持系列一致性：纸语言（纹理/边缘/halftone）全系列锁定，主题预设仅作调色/排版微调轴
5. 向后兼容：已完成集的规范不回改，新规范只约束新生产场景

## 范围

### 包含

| 组件 | 说明 |
|---|---|
| `skills/pipelines/series-adapt/references/vox-story-library.md` | 新增：叙事弧库 + hook 模式 + 节奏规则（vox-director beat-layer 翻译适配） |
| `skills/pipelines/series-adapt/references/vox-look-library.md` | 新增：图像提示 5 部分结构 + 维度词库 + 9 主题预设 + 一致性规则 |
| `skills/pipelines/series-adapt/references/vox-motion-library.md` | 新增：camera_move 词表 + element_motion 引擎 + GSAP 纸感动效实现清单 + 反单调规则 |
| `skills/pipelines/series-adapt/rewrite-director.md` | 修订：新增"叙事弧选择"步骤，引用 story-library |
| `skills/pipelines/series-adapt/scene-director.md` | 修订：generation_direction 改为 5 部分结构；新增 camera_move 约束与场景内视觉节拍规则 |
| `skills/pipelines/series-adapt/asset-director.md` | 修订：image prompt 拼接规范（scene_plan.generation_direction → 5 部分完整 prompt） |
| `skills/pipelines/series-adapt/compose-director.md` | 修订：element_motion 引擎 + GSAP 纸感动效 + hero 飞行元素 + 反单调 |

### 不包含

- 不引入 Atlas Cloud / AI 视频模型动画路线（与 HyperFrames 确定性渲染和版权策略冲突）
- 不实现 A-roll（真人视频重风格）——与"独立重写、弃用原画面"策略冲突
- 不修改 `pipeline_defs/series-adapt.yaml`（无新阶段、无新状态）
- 不回改已完成集（ep-01 等已渲染场景保持现状）
- 不实现本地关键帧引擎的 Python 代码（其理念以 GSAP 写法形式注入 compose-director）

## 技术决策

| # | 决策项 | 结论 | 理由 |
|---|---|---|---|
| 1 | 借鉴载体 | **参考库文件（references/）+ 导演技能引用**，而非改写 styles/ YAML | director skill 保持聚焦；styles/ 受 schema 验证约束，不适合放文档型词库 |
| 2 | 图像提示结构 | 采用 5 部分结构，其中 STYLE BLOCK 仍取 `styles/vox-collage.yaml` → `image_prompt_prefix` 逐字复用 | 与现有资产管线零冲突，只改 `generation_direction` 的组织方式 |
| 3 | 主题预设定位 | 预设仅作**微调轴**（调色板/排版/印花纹理），基础纸语言锁定 | 系列品牌一致性的前提是纹理语言不变，颜色可随主题/年代变化 |
| 4 | 节奏适配 | vox 的"3–6s/镜"不适配 10 分钟纪录片；改为**场景内视觉节拍**：每 4–7s 一个视觉事件（元素入场/图表更新/子镜头切换） | 长场景 ≠ 死静；保留场景窗口跟随 voice boundaries 的现有规则 |
| 5 | 2-shots 适配 | 长场景（>12s）内拆 2+ 子镜头（wide + detail），子镜头间 cross-dissolve 或推近过渡 | vox 的"旁白连续、画面句中切"正是我们已遵循的模式，量化为子镜头规则 |
| 6 | element_motion 边界 | 刚性纸片：slide/flap/scatter/pivot 允许；morph/warp/融化禁止 | vox-director 实测验证的安全边界，直接沿用 |
| 7 | GSAP 纸感实现 | 翻译 local-engine 经验：`back.out` 弹性落地、目标位模糊占位防 ghost、`pop_settle` 原地 1.35→1.0、`stamp-appear` | 纯 GSAP 可表达，无需新依赖 |
| 8 | hero 飞行元素 | 关键节拍（转折点/高光）≤1 个 hero 元素飞过全场，非每场景 | 每帧都用会读作公式（vox-director 原话） |

## 验证策略

### 文件级验证

- 3 个参考文件存在且章节完整（含词表、示例、出处）
- 4 个导演技能修订后仍通过"技能文件可读性"检查（引用路径真实存在）
- 修订后的 director skill 与 `pipeline_defs/series-adapt.yaml` 阶段映射无冲突

### 试点验证（选择 99追忆 下一集未生产的集，如 ep-02+）

| 验证项 | 通过标准 |
|---|---|
| 5 部分结构检查 | 每场景 `generation_direction` 含 STYLE BLOCK 引用、SCENE 剪贴片描述、背景色、内嵌标签 4 要素 |
| 图像层次检查 | 抽查 3 张生成图：可见独立剪贴片边缘 + 阴影分离 |
| 动效密度检查 | 渲染后抽帧：每 4–7s 有视觉事件；相邻场景运动族不重复；无 morph/warp 元素 |
| hero 元素检查 | 全片 hero 飞行元素 ≤2 处，且仅出现在关键节拍 |
| 纸感检查 | 元素落地带 back 弹性或 pop_settle；目标位无 ghost 重影 |

### 回归验证

- 已完成集（ep-01）不受影响：无文件被回改，`hyperframes lint` 通过

## 执行策略

| 优先级 | 任务 | 依赖 | 预估工作量 |
|---|---|---|---|
| **P0** | 创建 `references/vox-story-library.md` | 无 | 1 会话 |
| **P0** | 创建 `references/vox-look-library.md` | 无 | 1 会话 |
| **P0** | 创建 `references/vox-motion-library.md` | 无 | 1 会话 |
| **P1** | 修订 `scene-director.md`（5 部分结构 + camera_move + 视觉节拍） | P0 | 1 会话 |
| **P1** | 修订 `asset-director.md`（prompt 拼接规范） | P0（look-library） | 0.5 会话 |
| **P1** | 修订 `compose-director.md`（element_motion + GSAP 纸感） | P0（motion-library） | 1 会话 |
| **P1** | 修订 `rewrite-director.md`（叙事弧选择） | P0（story-library） | 0.5 会话 |
| **P2** | 试点：生产下一集 scene_plan + 3 张图像 + 1 个场景动效 | P1 全部 | 1-2 会话 |
| **P2** | 试点验证 + 经验回写参考文件 | P2 | 0.5 会话 |

## 待办事项

### Phase 0：参考库（P0）

- [ ] 创建 `skills/pipelines/series-adapt/references/vox-story-library.md`
    - 14 种叙事弧 + topic→arc 启发式（timeline / three_act / man_in_hole / hook_payoff / myth_buster 等）
    - hook 模式库（surprising_stat / direct_question / pain_point / secret_reveal 等）
    - 节奏规则：hook 窗口 ≤15s（纪录片适配）、每 60–90s 一个小节拍点、结尾三选一（hard_cut / quick_cta / loop_close）
    - 出处标注（vox-director beat-layer.md + 原始来源）
- [ ] 创建 `skills/pipelines/series-adapt/references/vox-look-library.md`
    - 图像提示 5 部分结构（STYLE BLOCK / SCENE 剪贴片 / 背景 / 标题 / 技术）
    - 7 个图像维度词库（媒介/年代/构图/配色/字体/印花/氛围）+ 单行结构
    - 9 个主题预设表（适配我们的 palette，标注"微调轴"）
    - 一致性规则：STYLE BLOCK 逐场景复用、纸语言锁定、标题 ≤4 词烘烤进图
- [ ] 创建 `skills/pipelines/series-adapt/references/vox-motion-library.md`
    - camera_move 硬约束词表（safe 7 个 + banned 列表）+ 相邻不重复 + static 留给 payoff
    - element_motion 引擎规则：≥2 元素同动、刚性纸片边界、hero 飞行元素 ≤1/关键节拍
    - GSAP 纸感动效清单：fly_in（back.out）/ slap / drop（bounce）/ pop_settle / stamp-appear / 模糊占位防 ghost
    - 反单调：相邻场景运动族（scale ↔ translate ↔ opacity）轮换

### Phase 1：导演技能修订（P1）

- [ ] 修订 `scene-director.md`
    - `generation_direction` 改为 5 部分结构模板（引用 look-library）
    - 新增 camera_move 字段与约束词表（引用 motion-library）
    - 新增"场景内视觉节拍"规则：每 4–7s 一个视觉事件；>12s 场景拆 2+ 子镜头（wide + detail）
    - 更新质量规则：相邻场景运动族不重复、static 留给 payoff 场景
- [ ] 修订 `asset-director.md`
    - 新增 image prompt 拼接规范：scene_plan.generation_direction 4 要素 + 风格块 → 完整 prompt
    - 保留现有 img2img 参考帧机制（真实人物/车辆保真）
- [ ] 修订 `compose-director.md`
    - 新增 element_motion 实现规则（每场景 ≥2 元素动，刚性纸片边界）
    - 新增 GSAP 纸感动效清单（back 弹性 / pop_settle / 模糊占位 / stamp-appear）
    - 新增 hero 飞行元素规则（≤1/关键节拍）
- [ ] 修订 `rewrite-director.md`
    - 新增"叙事弧选择"步骤（引用 story-library，按集内容选弧：历史集 → timeline，人物故事集 → man_in_hole）
    - 新增 hook 规则：开场 15s 内必须建立 payoff 承诺

### Phase 2：试点验证（P2）

- [ ] 在 99追忆 下一未生产集应用新规范
- [ ] 验证 scene_plan 5 部分结构完整（抽查 3 个场景）
- [ ] 生成 3 张图像，检查剪贴片层次与单色背景
- [ ] 编写 1 个场景的 GSAP 动效（含 hero 元素或 pop_settle）
- [ ] 渲染抽帧验证动效密度与纸感
- [ ] 把试点发现回写到 3 个参考文件（如必要）

## 风险与约束

| 风险 | 级别 | 缓解措施 |
|---|---|---|
| 改动幅度过大导致现有集风格断裂 | 中 | 明确向后兼容：已完成集不回改；新规范仅约束新场景 |
| 主题预设调色板与 `styles/vox-collage.yaml` 冲突 | 低 | 预设仅作用于调色/排版/印花微调轴；纹理/边缘/halftone 纸语言锁定不变 |
| 5 部分结构增加 image prompt 长度导致生成成本/失败率上升 | 低 | 结构是组织方式，非内容膨胀；复用风格块不增加 token 负担；失败时回退现用 prompt |
| 视觉节拍规则与"场景窗口跟随 voice boundaries"冲突 | 低 | 视觉事件不改变场景窗口，只在窗口内增加动画触发点；字幕/旁白不受影响 |
| 过度借鉴失去自身特色 | 低 | 明确排除 AI 视频模型 / A-roll / Atlas 依赖三项；参考库仅作词库与规则，不引入外部引擎 |

## 成功标准

### 文件级

- [ ] 3 个参考文件创建完成，含词表/示例/出处，且被对应 director skill 引用
- [ ] 4 个 director skill 修订完成，引用路径真实可读
- [ ] `pipeline_defs/series-adapt.yaml` 零改动，`hyperframes lint` 回归通过

### 试点级

- [ ] 试点集 scene_plan 通过 5 部分结构抽查（每场景含 4 要素）
- [ ] 抽查图像显示独立剪贴片边缘 + 阴影分离
- [ ] 渲染抽帧：每 4–7s 有视觉事件，相邻场景运动族不重复
- [ ] hero 飞行元素全片 ≤2 处，仅出现在关键节拍
- [ ] 已完成集（ep-01）文件零改动

### 系列级（远期）

- [ ] 第 1 季 10 集视觉节奏密度一致（无死静长场景）
- [ ] 跨集纸语言一致（纹理/边缘/halftone 锁定生效）
- [ ] 跨集主题微调轴按集内容合理变化（年代感/地域感随题材走）
