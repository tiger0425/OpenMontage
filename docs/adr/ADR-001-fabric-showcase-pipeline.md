# ADR-001: fabric-showcase 管线设计决策

- **状态**: Accepted
- **日期**: 2026-07-14
- **决策者**: 用户 + AI Agent (grill-with-docs session)
- **影响范围**: OpenMontage 管线体系

## 背景

在 `videos/fabric-promo` 项目中，我们手工完成了一条 17 秒竖版面料广告视频。
流程为：ComfyUI Klein 图 → LTX23 视频 → HyperFrames 合成 → edge-tts + MusicGen 音频 → 渲染 → Pillow 封面。

该流程需要固化为 OpenMontage 的可复用管线，使后续面料广告能自动走管线生产。

现有管线（hybrid, animated-explainer, cinematic, animation 等）无法直接适用：
1. 无源 footage（与 hybrid 的 anchor 矛盾）
2. 面料有不可虚构的事实属性（现有管线无 Truth-Gate 机制）
3. 商业种草广告而非叙事/教育（目标不同）

## 决策

### D1: 管线名为 `fabric-showcase`

限定面料/纺织品领域。不改名为通用 `material-showcase`，因为领域语言围绕面料构建（成分、手感、垂坠、适用产品）。后续若有皮革/木材等可另建管线。

### D2: Category 设为 `product_promo`（新增 enum）

不使用现有 `generated` 分类。在 `pipeline_manifest.schema.json` 的 category enum 中新增 `product_promo`，精确区分商业产品推广与话题解说。

### D3: 4 阶段压缩结构

```
brief → assets → compose → publish
```

- 合并 script + scene_plan → `brief`（旁白稿和场景大纲并入 fabric_brief）
- 去掉独立 research 阶段（面料事实由用户提供，不搜网）
- 去掉 edit 阶段（HyperFrames 合成层直接处理剪辑逻辑）

### D4: 单一工件 `fabric_brief`（含 Truth-Gate）

不拆分为 `fabric_facts` + `fabric_brief` 两个工件。`fabric_brief` 内部有结构化的 `fabric_facts` 区块，后续阶段通过 `review_focus` 检查项引用该区块实现 Truth-Gate。

### D5: ComfyUI 自定义工具注册到 registry

在 `tools/` 下新增 `ComfyUIImageGen` 和 `ComfyUIVideoGen`（继承 BaseTool），注册到 registry。不使用 `custom_scripts` 绕过 registry，保持工具发现一致性。TTS 用现有 `tts_selector`，BGM 用现有 `music_gen`。

### D6: 封面注册为 `cover_gen` 工具

Python Pillow 封面生成注册为 `cover_gen` 工具类（capability: image_generation, runtime: LOCAL）。在 publish 阶段的 `tools_available` 中引用。

### D7: compose 阶段仅 hyperframes

`tools_available` 只列 `hyperframes_compose` + `audio_mixer`，不列 remotion。面料广告的 HTML/CSS/GSAP 动画风格与 HyperFrames 原生匹配。不存在 proposal 阶段做运行时选择，所以直接锁定。

### D8: 不绑定 playbook

`compatible_playbooks` 留空，`custom_allowed: true`。面料广告风格多样（复古/文艺/现代），不预设固定 playbook。

### D9: EP 模式保留但简化

```
budget_default_usd: 0.50
max_revisions_per_stage: 2
max_send_backs: 1
max_wall_time_minutes: 8
```

### D10: reference_input 浅度支持

`supported: true, analysis_depth: transcript_only`。允许用户提供竞品广告参考，但不做深度视频分析。

### D11: 人审策略

```
brief:     human_approval_default: true   (面料事实必须确认)
assets:    human_approval_default: true   (生成素材必须审核)
compose:   human_approval_default: false  (自动推进)
publish:   human_approval_default: true   (最终发布确认)
```

## 后果

- **正面**: 4 阶段管线轻量高效，$0.50 预算适合本地 ComfyUI + 免费工具链；Truth-Gate 保护面料事实不被虚构
- **负面**: 压缩阶段后无法走 EP 的 research→proposal→script→scene_plan 标准流程，backlot board 可能显示较少的工件检查点
- **风险**: 新增 `product_promo` category 到全局 schema，后续管线可复用该分类但需要更新 AGENT_GUIDE.md 的管线表格
