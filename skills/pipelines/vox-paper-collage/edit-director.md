# Edit Director — Vox Paper Collage

## 职责

执行 VOX 引擎 STATE 8（UNIVERSAL VIDEO PROMPT）的编辑侧：为每张图定义 10 秒确定性动画的剪辑决策（0-7s 组装、7-10s 微动效、锁定镜头、最终帧=源图）。产出 `edit_decisions`。

## 输入

- scene_plan（节拍顺序与时间码）
- asset_manifest（图像资产路径）

## UNIVERSAL VIDEO PROMPT（模板 verbatim，见 `templates/video_prompt.md`）

关键约束（引擎逐字）：

- **CAMERA, STRICT**：整段 clip 镜头完全锁定。无 zoom、pan、tilt、rotation、orbit、dolly、tracking、handheld shake、focus pulls、reframing、cuts、transitions、morphing、object replacement、time skips。一个连续静态镜头。
- **0 TO 7 SECONDS, BUILD-ON ASSEMBLY**：开场只有空白背景板（老报纸/档案表面及其污渍、纹理、固定脚手架）。元素按叙事顺序逐层进入（后到前）：背景碎片先落定，英雄剪贴滑入（纸拖拽+小幅安定），支撑剪贴掉落或用图钉（2 帧图章安定），胶带按下，打字机条滑入，图章拍上，红线从钉到钉自画，标记下划线与箭头最后自画。每次进入带微小手工弹跳与真实分层阴影。落地后元素不再移动。到 7 秒时画面与源图完全一致。
- **7 TO 10 SECONDS, LIVING PAPER POSTER**：一切保持位置。仅存微妙生命：纸角在气流中抬起一毫米、半色调点微闪、弦张力颤抖一次、阴影呼吸、图章墨迹微亮。无位置变化、无缩放、无显著旋转、无进无出。
- **AUDIO**（clip 内）：无音乐、无旁白、无语音。仅特写纸 ASMR 与微弱场景环境音（纸滑动、卡纸敲击、胶带按压、图章闷响、弦拉、图钉咔哒、柔和房间底噪），全部微妙。
- **FINAL RULE**：完成 clip 必须像真实的编辑拼贴画在桌上自组装，然后作为活的 poster 保持，从 7 秒到结尾与源图精确一致。

## 流程

1. 对每个节拍取对应图像资产
2. 为每张图写 10 秒 clip 决策：
   - 动画时长 10s（每图一个 clip，clip 之间硬切）
   - 元素入场顺序（按叙事与视觉层级：背景→英雄→支撑→胶带→打字机条→图章→红线→标记）
   - 入场动效参数：纸拖拽 + 安定 + 微小手工弹跳，stopped-easing（step easing，2-3 帧停顿，"cutting on twos"）
   - 7-10s 微动效参数（角抬 1mm、点闪、弦颤、阴影呼吸）
   - 锁定镜头（无任何摄像机运动）
   - 最终帧 = 源图（FINAL RULE 校验点）
3. 节拍序列与旁白时间码对齐（scene_plan）
4. 音频层决策：clip 内仅 ASMR；旁白/音乐/成片 ASMR 在 compose 混音

## 质量要求

- 每张图恰一个 10s clip
- 无过渡（硬切）—— 引擎禁止 transitions
- em dash 禁止
- render_runtime = hyperframes 传递（不换）

## 成功标准

- `edit_decisions` 通过 schema 校验
- 每节拍有 10s clip 决策，含入场顺序与微动效
- 锁定镜头 + 最终帧一致规则逐 clip 记录
