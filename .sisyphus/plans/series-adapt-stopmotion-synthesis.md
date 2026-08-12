# series-adapt 定格合成路径研究

推荐：采用 **C 混合路径**，以 HyperFrames/GSAP 负责纸张、标签、背景和时间线，以本地 ComfyUI + Klein 产出的 PNG 作为离散状态帧，状态按 `hold_frames` 或明确时长硬切；默认仍以 30fps 输出，不把 ComfyUI VHS 视频工作流作为主路径。

## 现有节奏先例

### vox-paper-collage 的定格节奏

- 纸拼贴的现有视觉契约已经明确要求 `stepped easing`、`2-3 frame holds` 和“cutting on twos”，并明确禁止平滑 CGI 动作。证据：`skills/pipelines/vox-paper-collage/templates/video_prompt.md:4-6`。
- 该契约把每个 clip 分成前约 70% 的 `BUILD-ON` 和后约 30% 的 `LIVING PAPER POSTER`；元素落位后不再改变位置，最后阶段只保留极小的纸角、网点、绳子和阴影微动。证据：`skills/pipelines/vox-paper-collage/templates/video_prompt.md:10-12`、`skills/pipelines/vox-paper-collage/edit-director.md:17-21`。
- 编辑规则将动画时长绑定到语音段，`build-on` 结束点默认是 `segment_duration * 0.7`，元素入场为句子开始时间加 0.2 秒，并把 step easing、2-3 帧停顿写入每个 clip 的决策。证据：`skills/pipelines/vox-paper-collage/edit-director.md:25-33`。
- compose-director 已把上述规则落到 HyperFrames：镜头锁定、最终帧必须与源图一致、入场使用 step easing/2-3 帧停顿，并要求渲染前通过 lint/validate、渲染后抽关键帧。证据：`skills/pipelines/vox-paper-collage/compose-director.md:30-40`。

### series-adapt 的单图/场景驱动方式

- `series-adapt` 当前是“每个 scene 一张图 + GSAP 场景动效”的模型：scene plan 为每幕指定 `scene_type`、`animation_type`、时间窗口和 narration master clock；动画类型包括 `pan-zoom-in`、`chart-reveal`、`map-marker`、`typewriter` 等。证据：`skills/pipelines/series-adapt/scene-director.md:34-46`、`skills/pipelines/series-adapt/scene-director.md:54-61`。
- 现有时间窗口以语音边界为主，并要求 hold、连续窗口和交叉溶解；长段可拆成多个 sub-shot，但仍由旁白作为主时钟。证据：`skills/pipelines/series-adapt/scene-director.md:63-73`。
- 每幕还要求 `camera_move`、`element_motion`、`highlight` 和 `visual_beat_seconds`；元素落地后静止，只保留微呼吸，超过 12 秒的场景要拆成 2 个以上 sub-shot。证据：`skills/pipelines/series-adapt/scene-director.md:117-124`。
- `vox-motion-library` 明确把“元素运动”而非单一相机推近作为能量来源，定义了 `static/push_in/pull_out/pan/tilt/parallax/element` 相机词表，以及 `drift/sway/ripple/flutter/slide/pivot/bob/pulse/shimmer/settle` 等刚性纸片动词；同时规定落地即停。证据：`skills/pipelines/series-adapt/references/vox-motion-library.md:11-19`、`skills/pipelines/series-adapt/references/vox-motion-library.md:21-52`。
- 现有生成器把每个 sub-shot 映射成一张 PNG：`img = '%s_%d.png'`，HTML 中每幕只有一个 `<img src="assets/...">`；随后由 GSAP 对照片、标签、图钉和纸片做 `fromTo`/`to` 动画。证据：`skills/pipelines/series-adapt/tools/build_episode_parts.py:57-65`、`skills/pipelines/series-adapt/tools/build_episode_parts.py:109-110`、`skills/pipelines/series-adapt/tools/build_episode_parts.py:124-166`。
- `assemble_episode.py` 也只按 scene 编号复制一张 PNG 到 HyperFrames workspace，并将旁白、BGM、SFX 作为独立媒体复制进去。证据：`skills/pipelines/series-adapt/tools/assemble_episode.py:24-52`。
- 现有 scene plan schema 已有 `beats`、`elements.box`、`elements.family`、`elements.micro` 和 `elements.sfx`，这些字段足以继续描述纸感合成层，但没有离散帧序列字段。证据：`schemas/artifacts/scene_plan.schema.json:131-208`。

### Klein 与 provider 边界

- 本研究按用户修正采用本地 ComfyUI + Klein。vox-paper-collage 的工具绑定明确写明只用本地 ComfyUI + Klein，不使用云图像服务或其他工作流；并列出 `Klein-txt2image.json`、`Klein-img2image.json` 和双参考工作流的 output node 与输入关系。证据：`skills/pipelines/vox-paper-collage/assets-director.md:51-61`。
- `comfyui_image` 的输入契约支持自定义 workflow、output node 和 reference image，但其能力是 `text_to_image`，副作用是写入图像文件；返回数据的格式固定为 `png`。证据：`tools/graphics/comfyui_image.py:65-83`、`tools/graphics/comfyui_image.py:85-153`、`tools/graphics/comfyui_image.py:290-305`。
- Klein 文生图工作流的输出节点是 `SaveImage`，不是视频输出节点。证据：`tools/_comfyui/workflows/Klein-txt2image.json:2-10`。
- Klein 图生图工作流同样以 `SaveImage` 结束，并通过 `LoadImage` 接收参考图；它没有 `VHS_VideoCombine` 或其他视频输出节点。证据：`tools/_comfyui/workflows/Klein-img2image.json:2-22`。
- 因此 Klein 的职责应限定为“产出有顺序的 PNG 状态帧”；状态帧进入合成的职责属于 HyperFrames/GSAP 或 FFmpeg，不属于 Klein 工作流本身。证据：`tools/graphics/comfyui_image.py:178-305`、`tools/_comfyui/workflows/Klein-txt2image.json:2-10`。
- `series-adapt/asset-director.md` 仍写着 `image_selector -> flux_image` 以及 `gemini-3.1-flash-lite-image`，这与本 issue 的 Klein 修正不一致；该文件应视为通用/过时的 provider 描述，不能作为本路径的 provider 选择依据。证据：`skills/pipelines/series-adapt/asset-director.md:22-24`、`skills/pipelines/series-adapt/asset-director.md:43-49`；Klein 专用约束见 `skills/pipelines/vox-paper-collage/assets-director.md:51-61`。

## HyperFrames/GSAP

### 已有支持

- `video_compose` 将 `render_runtime="hyperframes"` 路由到 `hyperframes_compose`，并禁止运行时静默切换到 Remotion 或 FFmpeg。证据：`tools/video/video_compose.py:7-26`、`tools/video/video_compose.py:1368-1385`、`tools/video/video_compose.py:1483-1509`。
- HyperFrames compose 会把 asset manifest 中的文件复制到 workspace 的 `assets/`，因为 HTML 的 `src` 必须位于 composition workspace 树内。证据：`tools/video/hyperframes_compose.py:1021-1033`、`tools/video/hyperframes_compose.py:1068-1111`。
- 现有 HyperFrames 生成器支持一张 PNG 作为一个 `img.clip`，为它生成 `data-start`、`data-duration`、`data-track-index`，并附带入口 tween；其 Phase 1 明确列出的媒体类型是 still image、video、text card、narration 和 music。证据：`tools/video/hyperframes_compose.py:1235-1256`、`tools/video/hyperframes_compose.py:1428-1457`、`tools/video/hyperframes_compose.py:1507-1533`。
- `series-adapt` 的 compose-director 已经以 HyperFrames/GSAP 为主路径，并说明 scene plan、asset manifest、设计系统和 motion library 是合成输入；episodes 2+ 使用参数化生成器生成 workspace、index、交叉溶解、有限重复微动效和多元素入场。证据：`skills/pipelines/series-adapt/compose-director.md:7-21`、`skills/pipelines/series-adapt/compose-director.md:38-57`。
- GSAP 现有实践偏好 `fromTo`，并且有限重复而不是无限循环，因为 HyperFrames 的确定性 seek 不能解析无限 loop。证据：`skills/pipelines/series-adapt/compose-director.md:142-154`。

### 对离散状态帧的适配

- **A 可行但不是现成开关。** 可以把每个 Klein PNG 状态视为一个独立 `img.clip`，按状态持续时间依次排在同一 scene 或相邻 cuts 中，并用 `tl.set`/透明度切换实现硬切；纸背景、标签、SFX 和状态图仍可由同一个 HyperFrames timeline 管理。现有单图生成、asset staging 和 `img.clip` 能支撑这个模型。证据：`tools/video/hyperframes_compose.py:1021-1111`、`tools/video/hyperframes_compose.py:1507-1533`。
- **当前未实现“一 cut 多 PNG 状态序列”。** `hyperframes_compose` 的 `_cut_to_html` 只从单个 `cut.source` 推导一个扩展名并生成一个 `<img>`；现有 `edit_decisions.cuts[]` 也只有单个 `source`、`in_seconds` 和 `out_seconds`，没有 `frames[]`、`hold_frames` 或 `state_durations`。证据：`tools/video/hyperframes_compose.py:1428-1443`、`tools/video/hyperframes_compose.py:1511-1529`、`schemas/artifacts/edit_decisions.schema.json:10-64`。
- **HyperFrames 不应直接把 12fps 当最终输出设置。** series-adapt 的已知问题记录指出 HyperFrames CLI 的 12fps 渲染会导致音频提取失败，建议统一 30fps 渲染，把 Vox 的 12fps 感交给 stepped keyframes 或 2-3 帧停顿实现。证据：`skills/pipelines/series-adapt/known-issues.md:141-147`；compose-director 的渲染说明同样要求 `--fps 30`。证据：`skills/pipelines/series-adapt/compose-director.md:249-258`。
- **现有先例更接近 C 而不是纯 A。** `series-adapt` 生成器保留静态照片，同时叠加 foreground frame、vignette、headline、pin、string 和有限循环微动；这证明“PNG 作为画面状态 + HTML/GSAP 纸感层”与现有构成方式兼容。证据：`skills/pipelines/series-adapt/tools/build_episode_parts.py:64-74`、`skills/pipelines/series-adapt/tools/build_episode_parts.py:128-189`。

## FFmpeg

### 已有 PNG sequence / frame-rate / concat 事实

- 仓库中已有底层 FFmpeg PNG sequence 重建先例：`green_screen_processor` 用 `-vf fps=<fps>` 抽帧为 `frame_%06d.png`，再用 `-framerate <fps> -i frame_%06d.png` 重建 MP4，并指定缩放、编码和像素格式。证据：`tools/video/green_screen_processor.py:410-440`、`tools/video/green_screen_processor.py:574-594`。
- 另一个本地预览工具也使用 `-framerate` 输入 PNG 序列，并以 `-r` 指定输出帧率。证据：`tools/character/character_animation.py:70-106`。
- `video_stitch` 的 `target_fps` 只用于把已有视频 clip 归一化；其输入 schema 的 `clips` 描述为视频文件列表，内部 concat 也是对 MP4 等视频文件建立 concat list，而不是读取 PNG sequence。证据：`tools/video/video_stitch.py:59-105`、`tools/video/video_stitch.py:481-607`。
- `video_compose._compose` 的 FFmpeg 路径同样是“视频 cut -> 临时 MP4 -> concat demuxer”：它明确说明只处理 video source，并且遇到 still image 会直接失败，要求改走 `render`/Remotion。证据：`tools/video/video_compose.py:381-387`、`tools/video/video_compose.py:454-475`、`tools/video/video_compose.py:581-595`。
- `video_compose` 的显式 FFmpeg runtime 最终只是调用上述 `_compose`；因此当前 `render_runtime="ffmpeg"` 并不等于“已支持 PNG sequence”。证据：`tools/video/video_compose.py:1602-1634`。

### 对定格合成的限制

- **B 的底层能力存在，但管线入口未实现。** 直接使用 FFmpeg 的 image2 输入可以把连续编号 PNG 按恒定帧率编码成视频，但仓库现有 `video_compose`/`video_stitch` 没有接收 sequence 目录、帧列表或每帧 hold 的公开字段；这部分能力是“底层示例已有、统一合成入口未实现”。证据：`tools/video/green_screen_processor.py:574-594`、`tools/video/video_compose.py:73-199`、`tools/video/video_stitch.py:59-105`。
- `-framerate` 只能表达统一输入节奏；要表达每个状态 2-3 帧或不等时长停顿，必须在输入目录中重复 PNG，或新增使用 concat 文件的逐帧 `duration` 处理。当前仓库没有面向 PNG 状态帧的这层语义化工具。证据：现有重建命令只有单一 `-framerate` 和编号模式，见 `tools/video/green_screen_processor.py:582-593`；现有 concat 只接收已编码 clip，见 `tools/video/video_stitch.py:591-607`。
- FFmpeg 路径不能自然复用 HyperFrames 的 HTML/GSAP 纸感叠层、语音句级入场、纸片 SFX 位置和 seek-safe timeline；这些能力目前写在 HyperFrames/GSAP compose-director 中。证据：`skills/pipelines/series-adapt/compose-director.md:77-100`、`skills/pipelines/series-adapt/compose-director.md:124-154`、`skills/pipelines/series-adapt/compose-director.md:229-237`。
- ComfyUI 中确实存在 `VHS_VideoCombine` 示例，但它属于 Qwen Layered 工作流，输入是图像批次、输出格式是 H.264 MP4；它不是 Klein 的输出路径，也不提供 OpenMontage 的 scene-plan/asset-manifest/HyperFrames 合成契约。证据：`tools/_comfyui/workflows/Qwen-Layered-txt2img.json:115-147`、`tools/_comfyui/workflows/Qwen-Layered-i2i.json:163-187`；Klein 的输出仍是 `SaveImage`，见 `tools/_comfyui/workflows/Klein-txt2image.json:2-10`。
- `comfyui_video` 是 WAN 2.2 的 text-to-video/image-to-video 生成工具，默认 81 帧、16fps；它不是“把 Klein PNG 序列合成视频”的工具。证据：`tools/video/comfyui_video.py:1-5`、`tools/video/comfyui_video.py:114-157`、`tools/video/comfyui_video.py:356-370`。

## 路径对比表

| 路径 | 机制 | 需要改动 | 成本 | 兼容性 | 主要风险 | 结论 |
|---|---|---|---|---|---|---|
| A HyperFrames/GSAP 状态硬切 | 每个 Klein PNG 是一个离散状态；timeline 在状态边界用 `set` 或短时 opacity 切换，不做帧间插值。纸感背景和标签可继续由 GSAP 管理。现有 HyperFrames 已支持单 PNG `img.clip` 和 `data-start/data-duration`。证据：`tools/video/hyperframes_compose.py:1507-1533`。 | 低到中：可以先把每个状态展开成独立 cut；若希望一个 scene 内维护序列，需要扩展 `cut` 的 sequence 语义并让 HyperFrames 生成多个状态节点。当前 schema 没有 sequence 字段。证据：`schemas/artifacts/edit_decisions.schema.json:10-64`。 | 媒体生成成本为 0 增量；工程成本中等；HyperFrames 仍需要 Node/FFmpeg/浏览器渲染和 lint/check。证据：`tools/video/video_compose.py:293-312`、`tools/video/hyperframes_compose.py:888-987`。 | 对现有 vox-paper-collage 和 series-adapt 最高；保留 seek-safe、场景级音频、纸感层和最终帧校验。证据：`skills/pipelines/vox-paper-collage/compose-director.md:30-40`。 | 当前生成器默认一个 cut 对应一个 PNG，状态序列若手工展开会使 cuts 和 SFX 变长；错误的 `from`/无限 loop 会触发 HyperFrames seek/lint 问题。证据：`skills/pipelines/series-adapt/compose-director.md:142-154`、`skills/pipelines/series-adapt/compose-director.md:168-176`。 | 适合最小验证和纯定格版；是 C 的基础实现。 |
| B FFmpeg PNG 序列 | 用 `-framerate` + `frame_%06d.png` 编码 PNG 序列，再用已有视频 concat/封装。仓库已有底层重建先例，但不是通用 sequence 入口。证据：`tools/video/green_screen_processor.py:574-594`。 | 中：新增 `png_sequence_to_video` 之类的 `video_post` 工具，或扩展 `video_compose` 接收目录/帧列表；还要定义重复帧或 concat duration 规则。现有 `_compose` 对 still image 直接失败。证据：`tools/video/video_compose.py:381-387`、`tools/video/video_compose.py:466-475`。 | 编码 CPU/磁盘成本低到中；实现成本低于完整 HTML 组合，但逐帧 PNG 会增加 IO 和中间盘占用。现有工具资源画像为本地 CPU/磁盘路径。证据：`tools/video/video_stitch.py:137-143`。 | 对“纯 PNG 定格 -> MP4”兼容性高；对纸张叠层、句级显示、SFX 落点和 HTML 视觉系统兼容性低。证据：`tools/video/video_compose.py:15-16`、`skills/pipelines/series-adapt/compose-director.md:229-237`。 | 不支持现成的每状态 hold 语义；默认恒定帧率容易把 2-3 帧停顿编码成错误节奏；无法自然表达 HyperFrames 的状态和覆盖层。证据：`tools/video/green_screen_processor.py:582-593`。 | 作为离线预合成/兜底路径，不作为 series-adapt 主路径。 |
| C 混合：HyperFrames 纸感 + 离散帧状态 | Klein PNG 只负责状态图；HyperFrames 保留纸张背景、标签、pins、string、SFX、字幕/旁白和场景时间线；状态图在指定边界硬切，纸感层可以独立微动。现有生成器已经采用“照片 + foreground + label + pin + 有限微动”的组合。证据：`skills/pipelines/series-adapt/tools/build_episode_parts.py:64-74`、`skills/pipelines/series-adapt/tools/build_episode_parts.py:168-189`。 | 中：新增 sequence 状态描述和一个确定性展开器，或把 sequence 在 compose 前展开成现有 cuts；不需要新图像 provider，也不需要 VHS 视频工作流。 | 媒体成本无新增；工程成本中等偏高于 A；渲染成本与现有 HyperFrames 相同，并增加 PNG 状态复制/加载。 | 与现有两套 pipeline 的设计字段、HyperFrames workspace、asset manifest 和 QA 最一致。证据：`skills/pipelines/series-adapt/compose-director.md:13-21`、`tools/video/hyperframes_compose.py:1021-1111`。 | 若状态帧与纸感 overlay 的时间轴没有统一时钟，会出现图像已切换但标签/SFX 未同步；需要验证总时长、边界和最终状态。已有连续窗口/边界规则可复用。证据：`skills/pipelines/series-adapt/scene-director.md:69-73`、`skills/pipelines/series-adapt/compose-director.md:195-207`。 | **推荐**：最能保留既有 Vox 纸感，又能引入 Klein 离散帧；B 可作为导出兜底。 |

## 推荐路径与需要新增的最小字段/工具

### 推荐实现边界

1. 把 Klein 定位为 **PNG 状态帧生产器**，不改成 `comfyui_video`，不接 Qwen/VHS `VHS_VideoCombine`，不使用 `google_imagen`。依据是 Klein 工作流只输出 `SaveImage`，而 VHS 示例是另一套 Qwen Layered 工作流。证据：`tools/_comfyui/workflows/Klein-txt2image.json:2-10`、`tools/_comfyui/workflows/Qwen-Layered-txt2img.json:115-147`。
2. 把“状态帧序列”放在合成层，保留 `render_runtime="hyperframes"`；不要新增名为 `stopmotion` 的 runtime。当前 runtime 合法值只有 `remotion`、`hyperframes`、`ffmpeg`，定格只是 HyperFrames 内的 composition mode/asset 语义。证据：`schemas/artifacts/edit_decisions.schema.json:194-207`。
3. 首版按 30fps 输出，在状态切换处使用 2-3 个渲染帧的 hold；不要用 HyperFrames CLI 的 12fps 作为输出帧率。证据：`skills/pipelines/series-adapt/known-issues.md:141-147`、`skills/pipelines/series-adapt/compose-director.md:249-258`。
4. 每个状态帧必须是可追溯的 asset manifest image，最终状态仍需通过最终帧/关键帧检查；现有 asset manifest 已支持 image 类型、路径、source_tool、scene_id、seed、model、format 等基本 provenance 字段。证据：`schemas/artifacts/asset_manifest.schema.json:10-35`。

### 最小字段建议

- `asset_manifest.assets[]`：首版不必新增结构字段，每个 Klein 输出按现有 `type: "image"`、`path`、`source_tool`、`scene_id`、`model`、`seed`、`format` 记录；`kind` 已可作为 `png_frame` 这类 pipeline-specific 标记。证据：`schemas/artifacts/asset_manifest.schema.json:10-35`、`schemas/artifacts/asset_manifest.schema.json:62-65`。
- `edit_decisions.cuts[]`：新增一个可选 `frame_sequence` 对象即可，不要把 provider/workflow 信息塞入该字段。建议最小形状：`{"mode":"hard_cut","frames":["asset_id_001","asset_id_002"],"fps":30,"hold_frames":[3,2]}`。现有 cuts 已有 `source`、`in_seconds`、`out_seconds`、transition 字段，且 `additionalProperties:false`，因此需要显式扩 schema。证据：`schemas/artifacts/edit_decisions.schema.json:10-64`。
- `frame_sequence.mode`：首版只支持 `hard_cut`，明确禁止插值、补帧和跨状态 tween；这与 Vox 的 stopped-easing、落地即停和离散 hold 规则一致。证据：`skills/pipelines/vox-paper-collage/templates/video_prompt.md:6-12`、`skills/pipelines/series-adapt/references/vox-motion-library.md:41-52`。
- `frame_sequence.fps`：建议默认 30；`hold_frames` 表示每个 PNG 状态持续多少个输出帧，且 `sum(hold_frames) / fps` 必须等于该 cut 的可见时长。这样可以精确表达 2-3 帧停顿，而不依赖文件重复命名。
- `frame_sequence.frames`：只放 asset ID，不直接放 provider 名称、ComfyUI 节点号或绝对路径；asset manifest 继续承担路径和 provenance。当前 `video_compose` 已支持从 asset ID 解析为路径。证据：`tools/video/video_compose.py:1323-1337`。

### 最小工具/代码改动点

- 新增一个 **HyperFrames sequence expander**，优先放在 `hyperframes_compose` 的 asset/cut materialization 边界：读取 `frame_sequence`，把每个状态展开成带准确 `data-start`/`data-duration` 的 `<img>` 状态节点，或在生成 HTML 前展开成现有 cuts。当前 HyperFrames 只支持一个 cut 一个 `<img>`，所以这是 C 的必要改动。证据：`tools/video/hyperframes_compose.py:1428-1457`、`tools/video/hyperframes_compose.py:1507-1533`。
- expander 必须生成硬切状态边界，并为背景/标签/纸片层保留独立 GSAP timeline；不要把所有 PNG 合并成一个视频后再交给 HyperFrames，否则会丢失现有 scene/element/SFX 时序。现有 compose-director 已把场景、元素和 SFX 分开定义。证据：`skills/pipelines/vox-paper-collage/compose-director.md:10-21`、`skills/pipelines/series-adapt/compose-director.md:229-237`。
- 新增 sequence 校验：文件存在且为 PNG、帧数与 `hold_frames` 数量一致、所有帧分辨率一致、`sum(hold_frames)/fps` 与 cut duration 容差一致、最后一个状态是预期 final state。现有 HyperFrames/compose 已有资产存在性、ffprobe、抽帧和最终审查入口，可复用其 QA 方向。证据：`tools/video/hyperframes_compose.py:1027-1111`、`tools/video/video_compose.py:1990-2118`。
- 只有在明确选择 B 时，才新增独立的 **PNG sequence -> MP4 FFmpeg 工具**，复用 `-framerate` + `%06d.png` 的底层模式；不要先扩展 `video_stitch`，因为它的契约是视频 clip 列表。证据：`tools/video/green_screen_processor.py:574-594`、`tools/video/video_stitch.py:59-105`。
- B 工具若要支持不等 hold，应把 `hold_frames` 展开为重复文件或生成带 `duration` 的 concat 输入；不能假设现有 image2 恒定帧率输入自动理解每状态停顿。现有重建函数只有恒定 `-framerate`，未实现逐状态 duration。证据：`tools/video/green_screen_processor.py:582-593`。

### 最小验证顺序

- 先验证一幕、少量 Klein PNG 状态，确认状态边界和 `hold_frames`；不生成新的媒体 provider 调用。
- 再验证纸感层：background、hero/state、label、pin/string、SFX 是否共享同一 scene clock；现有 scene/element 字段和 paper SFX 规则可作为验收基线。证据：`schemas/artifacts/scene_plan.schema.json:131-208`、`skills/pipelines/series-adapt/compose-director.md:229-237`。
- 最后运行 HyperFrames lint/check/渲染，并抽查 early/mid/final；现有 compose-director 要求渲染前 lint/validate、渲染后关键帧抽查。证据：`skills/pipelines/vox-paper-collage/compose-director.md:40`、`skills/pipelines/series-adapt/compose-director.md:239-258`。

### 明确未实现/不支持清单

- 当前 `video_compose` 的 FFmpeg compose 不支持把 PNG still 当作 cuts 输入；遇到 still image 会直接返回错误。证据：`tools/video/video_compose.py:466-475`。
- 当前 `video_stitch` 不支持把 PNG sequence 当作 `clips` 直接拼接；其输入和 concat 实现面向视频文件。证据：`tools/video/video_stitch.py:59-105`、`tools/video/video_stitch.py:481-607`。
- 当前 `hyperframes_compose` 不支持一个 cut 内的 `frames[] + hold_frames[]` sequence 字段；只支持单一 `source` 对应一个媒体节点。证据：`tools/video/hyperframes_compose.py:1428-1457`、`tools/video/hyperframes_compose.py:1507-1533`。
- 当前 Klein 工作流不负责视频编码；其输出是 `SaveImage` PNG。证据：`tools/_comfyui/workflows/Klein-txt2image.json:2-10`、`tools/_comfyui/workflows/Klein-img2image.json:2-10`。
- 当前没有证据表明 Qwen Layered 的 `VHS_VideoCombine` 已接入 `series-adapt` 或 `vox-paper-collage` 的标准合成契约，因此它不是本 issue 的首选实现。证据：VHS 仅出现在 `tools/_comfyui/workflows/Qwen-Layered-txt2img.json:128-147` 和 `tools/_comfyui/workflows/Qwen-Layered-i2i.json:172-187`；两套 pipeline 的 compose 入口仍是 HyperFrames，见 `skills/pipelines/series-adapt/compose-director.md:7-9` 和 `skills/pipelines/vox-paper-collage/compose-director.md:30-40`。
