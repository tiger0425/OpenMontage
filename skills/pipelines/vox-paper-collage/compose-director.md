# Compose Director — Vox Paper Collage

## 职责

读 scene_plan 的元素清单 → 自动生成 HyperFrames index.html + GSAP 时间线 → lint → render。
**scene_plan 是唯一契约**，compose 阶段不临场发挥——所有元素的类型/位置/动画/SFX 都在 scene_plan 中定义完毕。

## spec-driven 生成规则

scene_plan 中每个元素声明了完整的渲染契约：

```json
{"kind": "img|chart|tape|pin|string|headline|label|stamp|underline|vignette",
 "box": [left, top, width, height],
 "rot": 角度, "z": z-index,
 "family": "slide|rise|drop|slap|press|draw|pop|fade",
 "micro": "sway|lift|pulse|none",
 "sfx": "paper_slide|tape_press|stamp_thud|string_zip|pin_click|paper_tap"}
```

生成器按此契约逐元素渲染 HTML + GSAP tween，不临场决定动画形式。

## 输入

- edit_decisions（每图 10s clip 决策）
- asset_manifest（图像 / 旁白 / 音乐 / ASMR 资产）

## 流程

### 1. HyperFrames 渲染（每图一个 10s clip）

按 edit_decisions 的 clip 定义，用 `video_compose`（render_runtime=hyperframes）渲染：

- 0-7s：空白背景板开场 → 元素按叙事顺序逐层组装（纸拖拽、安定、微小手工弹跳、分层阴影）
- 7-10s：living paper poster 微动效（角抬 1mm、点闪、弦颤一次、阴影呼吸）
- 镜头全程锁定（HTML/CSS 固定视口，无 transform 摄像机层）
- 最终帧与源图精确一致（FINAL RULE 硬性）
- 入场动画用 step easing / 2-3 帧停顿，杜绝平滑 CGI 感

**强制**：渲染前必须 `hyperframes lint` 与 `hyperframes validate` 通过。渲染后抽关键帧自检每 clip 最终帧与源图一致。

### 2. 混音

- 旁白：主线（calm deadpan documentary read）
- 音乐：Pixabay Epic Egyptian trailer（低音量铺底，旁白 ducking）
- 纸 ASMR：clip 内环境音 + 成片点缀
- 响度目标：旁白优先，音乐 −14 dB 左右 ducking

### 3. 拼接

- clip 顺序 = scene_plan 节拍顺序，硬切
- 时长 = 节拍数 × 10s（±5% 目标）

## 冒烟片沉淀（2026-08）：元素动画规格

### 微动效：hero 慢缓动 + 辅助元素常规循环（用户确认，2026-08）

**hero 图微动 = 整个分镜一次极慢缓动**（电影推镜感），不是快速循环抖动。**仅 hero 图适用**；辅助/装饰元素按各自节奏（见下表）：

| 元素 | 微动方式 | 效果 |
|---|---|---|
| **hero 图（breathe）** | 单次 `scale 1→1.07`，duration=分镜剩余时长，ease power1.inOut | 极慢 push-in |
| 辅助图（sway） | 常规慢循环 `y` 摇曳（周期 3.2s，yoyo） | 轻微浮动 |
| 标签（lift） | 常规循环角抬（周期 2.8s，yoyo） | 纸角轻抬 |
| 图钉（pulse） | 常规循环脉动（周期 1.8s，yoyo） | 呼吸感 |

**规则**：
- **hero 图**：微动从入场 settle 后（at+0.8）开始，单次缓动持续到分镜结束（e-0.7），duration = `e - 0.7 - (at + 0.8)`，ease power1.inOut，**禁止 yoyo/repeat**
- **辅助/装饰元素**：可用常规 yoyo 循环（`repeat = floor(wnd/cycle) - 1`，yoyo:true，overwrite:auto），周期 1.8-3.2s
- 关键帧采样验证：hero 0.25s 间隔帧差应 ≈2-4（缓慢连续），不是 0（静止）也不是大幅跳变

### 生成器运行坑（2026-08 实测）

- **gen_v10.py 必须从项目根运行**（workdir=项目根），不要从 hyperframes 子目录——相对路径 WS 会解析错误，index.html 写错位置，渲染出旧文件（横竖屏混淆事故根因）
- 渲染必须从 `projects/<slug>/hyperframes` 目录运行 `npx hyperframes lint/render`
- 横竖切换：改 gen_v10.py 内 scene_plan 路径 → 从项目根 gen → 从 hyperframes 渲染 → 保存 → 切回
- 渲染后必须 ffprobe 验证分辨率（竖 1080×1920 / 横 1920×1080），防止错配

### 入场 family

| kind | 入场 family | 落地 SFX |
|---|---|---|
| img（真实新闻图/AI 元素） | drop(下坠+bounce)/rise(上浮)/slide(滑入)/pop(缩放)/fade | paper_slide.wav |
| chart（图表） | fade（整幅淡入） | paper_slide.wav |
| headline（粗体标题） | slide | paper_tap.wav |
| stamp（印章） | slap(缩放拍下 0.3s) | stamp_thud.wav |
| label（标签条） | slide | tape_press.wav |
| tape（胶带） | press(按下) | tape_press.wav |
| pin（图钉） | press | pin_click.wav |
| string（红绳） | draw(scaleX 0→1) | string_zip.wav |
| underline（下划线） | draw | paper_tap.wav |
| vignette（暗角） | fade | — |

- 元素错峰入场：0.35-0.45s 间隔
- 板间交叉溶解 0.5s（奇偶 track 交替），fade out 结束于边界前 ≥0.1s
- 6 拍 × 8-12 元素 ≈ 66 处 SFX
- 横竖双版本同一 scene_plan 结构，仅 canvas 尺寸与坐标不同

## 质量要求

- `hyperframes lint` / `validate` 不通过不得渲染
- 每 clip 最终帧与源图一致（抽帧核对）
- 输出 ffprobe 校验：时长、分辨率、编码、音频轨
- render_runtime 与 edit_decisions / proposal 一致（hyperframes，无静默换）

## 成功标准

- `render_report` 通过 schema 校验
- 输出文件存在且 ffprobe 通过
- `self_review_completed` 为 true，逐 clip 质量记录
