# Edit Director — Vox Paper Collage

## 职责

执行 VOX 引擎 STATE 8（UNIVERSAL VIDEO PROMPT）的编辑侧：为每个节拍定义一个**按语音段时长**确定性动画的剪辑决策（build-on 占前 ~70%、living poster 占最后 ~30%、锁定镜头、最终帧=源图）。产出 `edit_decisions`。

## 输入

- scene_plan（节拍顺序与每节拍语音段时间边界）
- asset_manifest（图像资产路径）
- script / 时间戳文件（可选，用于确认每段时长）

## UNIVERSAL VIDEO PROMPT（模板 verbatim，见 `templates/video_prompt.md`）

关键约束（引擎逐字，但时长按语音段缩放）：

- **CAMERA, STRICT**：整段 clip 镜头完全锁定。无 zoom、pan、tilt、rotation、orbit、dolly、tracking、handheld shake、focus pulls、reframing、cuts、transitions、morphing、object replacement、time skips。一个连续静态镜头。
- **BUILD-ON PHASE（约前 70% 的语音段时长）**：开场只有空白背景板（老报纸/档案表面及其污渍、纹理、固定脚手架）。元素按叙事顺序逐层进入（后到前）：背景碎片先落定，英雄剪贴滑入（纸拖拽+小幅安定），支撑剪贴掉落或用图钉（2 帧图章安定），胶带按下，打字机条滑入，图章拍上，红线从钉到钉自画，标记下划线与箭头最后自画。每次进入带微小手工弹跳与真实分层阴影。落地后元素不再移动。到 build-on 结束时画面与源图完全一致。
- **LIVING PAPER POSTER（剩余 ~30% 的语音段时长）**：一切保持位置。仅存微妙生命：纸角在气流中抬起一毫米、半色调点微闪、弦张力颤抖一次、阴影呼吸、图章墨迹微亮。无位置变化、无缩放、无显著旋转、无进无出。
- **AUDIO**（clip 内）：无音乐、无旁白、无语音。仅特写纸 ASMR 与微弱场景环境音（纸滑动、卡纸敲击、胶带按压、图章闷响、弦拉、图钉咔哒、柔和房间底噪），全部微妙。
- **FINAL RULE**：完成 clip 必须像真实的编辑拼贴画在桌上自组装，然后作为活的 poster 保持，从 build-on 结束到结尾与源图精确一致。

## 流程

1. 对每个节拍取对应图像资产与 scene_plan 中的语音段时长 `segment_duration`（例如 2.8s、5.1s、12.4s 等，来自 whisper 时间戳）
2. 为每个节拍写一个按 `segment_duration` 裁剪的 clip 决策：
   - 动画时长 = `segment_duration`（clip 之间交叉溶解 0.5s，奇偶 track 交替，fade out 结束于边界前 ≥0.1s）
   - build-on 结束点 = `segment_duration * 0.7`（保留足够时间让元素落定；若 segment < 1.5s，可压缩到 60% 或整段 build-on）
   - living-poster 起始点 = build-on 结束点
   - 元素入场时间 = 对应语音句子的开始时间 + 0.2s 缓冲（sync_sentence 语音驱动，禁止固定顺序）——动效风格参考：纸拖拽 + 安定 + 微小手工弹跳，stopped-easing（step easing，2-3 帧停顿，"cutting on twos"）
   - living-poster 微动效参数（角抬 1mm、点闪、弦颤、阴影呼吸）
   - 锁定镜头（无任何摄像机运动）
   - 最终帧 = 源图（FINAL RULE 校验点）
3. 节拍序列与 scene_plan 语音时间边界对齐
4. 音频层决策：clip 内仅 ASMR；旁白/音乐/成片 ASMR 在 compose 混音

## 质量要求

- 每个 clip 的时长必须等于 scene_plan 中对应语音段的时长，不固定为 10s
- build-on / living-poster 分界按 70/30 缩放，短 segment 可压缩 build-on 比例但不破坏 FINAL RULE
- clip 间交叉溶解 0.5s（奇偶 track 交替），fade out 结束于边界前 ≥0.1s；无硬切
- 元素入场 = sync_sentence 时间戳 + 0.2s，动画时长 = 句长 × 0.8；禁止开场一股脑全部展示
- em dash 禁止
- render_runtime = hyperframes 传递（不换）

## 成功标准

- `edit_decisions` 通过 schema 校验
- 每节拍有 clip 决策，其 `duration` 等于 scene_plan 中对应语音段长度
- 锁定镜头 + 最终帧一致规则逐 clip 记录
- build-on / living-poster 分界点写入每个 clip 决策
