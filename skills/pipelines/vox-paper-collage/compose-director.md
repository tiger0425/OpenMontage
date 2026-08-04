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

- edit_decisions（每 clip = 语音段时长，来自 whisper 时间戳）
- asset_manifest（图像 / 旁白 / 音乐 / ASMR 资产）

## 流程

### 1. HyperFrames 渲染（每 clip = 语音段时长）

按 edit_decisions 的 clip 定义，用 `video_compose`（render_runtime=hyperframes）渲染：

- build-on（前 ~70% 语音段时长）：空白背景板开场 → 元素按 sync_sentence 时间戳逐层组装（纸拖拽、安定、微小手工弹跳、分层阴影）
- living-poster（后 ~30%）：living paper poster 微动效（角抬 1mm、点闪、弦颤一次、阴影呼吸）
- 镜头全程锁定（HTML/CSS 固定视口，无 transform 摄像机层）
- 最终帧与源图精确一致（FINAL RULE 硬性）
- 入场动画用 step easing / 2-3 帧停顿，杜绝平滑 CGI 感

**强制**：渲染前必须 `hyperframes lint` 与 `hyperframes validate` 通过。渲染后抽关键帧自检每 clip 最终帧与源图一致。

### 2. 混音

- 旁白：主线（calm deadpan documentary read）
- 音乐：Epic Egyptian trailer（低音量铺底，旁白 ducking，−14 dB 左右）
- 纸 ASMR：clip 内环境音 + 成片点缀
- 响度目标：旁白优先，音乐 −14 dB 左右 ducking

### 3. 拼接

- clip 顺序 = scene_plan 节拍顺序
- clip 间交叉溶解 0.5s（奇偶 track 交替），fade out 结束于边界前 ≥0.1s
- 总时长 = 语音段时长总和 + 结尾余量（±5% 目标）

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

## 句子级语音同步（2026-08 用户确认，最高优先级）

**元素展示必须与语音内容同步出现——禁止"开场一股脑全部展示"。** 用户原话：有些标签和元素是语音中的内容（+7%、未来已来），应该配合语音读出来后显示。

### 同步规则（硬性）

- **元素入场时间 = 对应语音句子的开始时间 + 0.2s 缓冲**
- **动画时长 = 句子时长 × 0.8**（句子说完前动画完成，留 20% 停顿呼吸空间——用户明确要求"动画时间应该比这句话的时长短一些，留下一点停顿空间"）
- 每个句子对应一个独立元素（scene_plan 已绑定 sync_sentence）
- 句子间的间隙（0.2-0.8s）画面保持微动效（hero breathe / 标签 lift），不静止

### 语义 → 动画 family（scene_plan 已定义，此处只执行）

中英双语语义识别见 `bilingual-spec.md §12`（zh：发布→drop…；en：release→drop…），family 值两语言共用：

| family | 入场效果 | 典型句子 |
|--------|---------|---------|
| `drop` | 落下+弹跳 | 发布/推出 |
| `rise` | 上浮升起 | 上涨/大涨 |
| `shake` | 抖动+冲击 | 震惊/震动 |
| `pop` | 缩放弹出 | 排名/数字 |
| `slide` | 并排滑入 | 相当/超越 |
| `grow` | 生长展开 | 规模/参数 |
| `pulse` | 脉冲放大 | 增加/数百亿 |
| `slap` | 重拍定格 | 未来/悬念结尾 |
| `fade` | 轻淡入 | 短句/语气词 |

### 短句处理

- 句子 <1s：不单独做元素，并入相邻句（fade 或与前句元素同批）
- 长句 >3s：可拆为 2 个元素错峰（但总时长仍按 句长×0.8 分配）

### 标签尺寸红线（2026-08 用户确认）

- 竖屏 1080×1920：headline ≥ 100px（核心数字 150-200px）、stamp ≥ 64px、tstrip ≥ 38-44px
- 标签必须醒目（手机竖屏可读），宁可少而大，不可多而小

## HyperFrames HTML 编写规范（2026-08 沉淀，参考 alibaba-qwen38 项目）

**这是经过多轮踩坑验证的正确写法。不要自己发明新结构，直接照抄此模式。**

### 场景结构（每场景一个 section + 内部 board）

```html
<section class="clip" id="scene-s1" data-start="0" data-duration="10" data-track-index="0">
  <div class="board" id="bd-s1">   <!-- board 默认 CSS opacity:0 -->
    <div class="bgimg" id="s1-bg"><img src="assets/bg_s1.png" /></div>
    <div class="cutout" id="s1-hero" style="left:..;top:..;width:..;">
      <img src="assets/scene1_hero_cut.png" />
    </div>
    <div class="headline" id="s1-voice" style="...">文字</div>
    <div class="tape" id="s1-dec0" style="..."></div>
  </div>
</section>
```

关键规则：
1. **场景 = section.clip**，内部必须有一层 **`.board`（CSS `opacity:0`）** 包所有元素；GSAP 控制 board 的显隐，不要直接在 section 上做 opacity（会与 clip 可见性机制打架）
2. **data-track-index 交替**（0,1,0,1...），相邻场景不同 track，避免重叠冲突
3. audio 只有 `data-start` 无 `data-duration`（让媒体自然播完），旁白与 SFX 都直接是 root 的子元素

### GSAP 时间线写法（错误示范勿抄）

| 错误写法 | 后果 |
|---|---|
| `tl.from(el, {opacity:0}, t)` + CSS `opacity:0` | **空屏**：from 是从 0 动画到当前值（也是 0）→ 永远透明 |
| `tl.from(el, ...)` 依赖 immediateRender | 与 HyperFrames seek 渲染机制打架，元素状态不可靠 |
| 元素入场时间不 clamp | 动画没播完场景就切走 → **元素一闪就没** |

**正确写法（全用 fromTo）**：

```js
// board 交叉溶解（前一 board end-0.45 淡出，后一 board start-0.4 淡入，重叠 0.5s）
tl.fromTo("#bd-s1", {opacity:0}, {opacity:1, duration:0.5, ease:"power1.out"}, 0.05);
tl.to("#bd-s1",   {opacity:0, duration:0.45, ease:"power1.in"}, 9.55);
tl.set("#bd-s1",  {opacity:0}, 10.00);   // 场景结束后确保隐藏

// 元素入场：一律 fromTo（from 起始态 → to 目标态）
tl.fromTo("#s1-hero", {y:-90, opacity:0}, {y:0, opacity:1, duration:1.2, ease:"power2.out"}, 0.3);
// hero 微动：入场后慢速 breathe 到场景结束（living poster）
tl.to("#s1-hero", {scale:1.05, duration:7.6, ease:"power1.inOut"}, 1.5);
```

### 元素入场节奏（三层设计，2026-08 用户确认）

**不是所有元素都跟语音**。分三层：

| 层 | 元素 | 入场时间 | 跟语音？ |
|---|---|---|---|
| 视觉骨架 | hero | `scene_start + 0.3s`（短场景 +0.2s）| ❌ 固定 |
| 视觉骨架 | l3 支撑图 | `scene_start + 1.2s`（短场景 +0.8s）| ❌ 固定 |
| 视觉骨架 | decor 装饰 | `scene_start + 2.0s` 起错峰 0.5s（短场景 +1.3s）| ❌ 固定 |
| 内容标签 | voice（数字/关键词）| 语音句子时间 + 0.2s | ✅ 跟语音 |

- **短场景判定**：`dur <= 7s` → 所有元素快速入场（hero 0.2 / l3 0.8 / voice 1.2 / decor 1.3），**绝不跟语音**（短场景语音句在末尾，跟语音必然一闪）
- **voice 可见时间红线**：`v_t = min(句子时间+0.2, end - 2.5)`，保证出现后至少可见 2.5s
- **所有入场 clamp 红线**：`t + 动画时长 <= scene_end`，否则动画被截断 = 元素一闪
- 原因：whisper 句子时间戳常落在场景后段，全量跟语音导致元素太晚出现/一闪而过

### 渲染注意事项

- 渲染命令：`npx hyperframes render -o <输出路径> --fps 30 --quality standard`
- **EPERM 坑**：`hyperframes/renders/` 目录可能被残留 chrome 进程/杀软锁定（rename 失败），**输出到 `projects/<slug>/renders/`**（项目级目录）可绕过
- 渲染前必须 `npx hyperframes lint`（0 errors）+ `npx hyperframes validate`（No console errors）
- 渲染后抽帧验证：每场景 early(+1s)/mid(+5s)/final(70%) 三帧，std 应 >15（有内容），且 final 不塌缩（元素持续可见）

## 成功标准

- `render_report` 通过 schema 校验
- 输出文件存在且 ffprobe 通过
- `self_review_completed` 为 true，逐 clip 质量记录
