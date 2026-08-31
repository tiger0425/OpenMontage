# VSR（YaoFANGUK/video-subtitle-remover）技术原理深度研究报告

> 调研对象：开源项目 **YaoFANGUK/video-subtitle-remover (VSR)** — 基于 AI 去除视频/图片硬字幕与类文本水印的工具。
> 版本：以 `main` 分支（内部版本号 **1.4.0**，见 `backend/config.py:10`）为准。
> 方法：所有结论均追踪到一手来源（仓库源码文件 + 行号、依赖定义、GitHub issue、底层论文 arXiv/原文），并在每条结论标注 **「已确认事实 (confirmed)」** 或 **「推断 (inference)」**。非必需时不以二手博客为据。

---

## 0. 结论先行

- VSR 不是单一模型，而是一条 **「检测 → 生成 mask → 视频修复 → 无损合成输出」** 的流水线；同一套框架可挂载 5 种修复算法（`sttn-auto`、`sttn-det`、`lama`、`propainter`、`opencv`），默认 `sttn-auto`。
- **字幕检测是自动的**：基于 **PaddleOCR 的 PP-OCRv5 文本检测模型（det，server/mobile）**，默认 `PP-OCRv5_server_det`；用户手动框选区域是**可选约束**，用于把 OCR 检出框裁剪到指定区域（`sttn-auto` 模式则完全不用 OCR，直接用用户框选区域当 mask）。
- **修复模型以 STTN 为主**（Spnatial-Temporal Transformer，ECCV 2020）；ProPainter（ICCV 2023）作为「剧烈运动场景」的可选增强；LAMA（WACV 2022）主要用于**图片**与单帧兜底。
- **mask 不是像素二值化出的**，而是**由 OCR 检测框直接画的白色矩形**，并按 `subtitleAreaDeviationPixel`（默认 10px）四周膨胀。
- **“无损分辨率”指尺寸不变 + CRF 18 的 libx264 编码**（视觉近无损，非逐位无损）；音频用 copy 无损合并。
- 主要失败模式被 issue 反复证实：**多行字幕效果差**、**logo/复杂水印难除**、**动态/移动水印难除**、**某些帧字幕残留**、**处理后画质变糊**、**误伤非文字（如手）**。

---

## 1. 端到端流水线各阶段及其算法 / 模型 / 参数

**入口分层**（`backend/main.py`）：

- `SubtitleRemover.run()`（`backend/main.py:335-401`）按 `config.inpaintMode` 分派到：
  - `PROPAINTER` → `propainter_mode()`（`backend/main.py:159-245`）
  - `STTN_AUTO` → `sttn_auto_mode()`（`backend/main.py:247-258`）
  - `STTN_DET` / `LAMA` / `OPENCV` → 统一走 `video_inpaint()`（`backend/main.py:260-333`）

**阶段 1：选区 / 字幕检测（decide region & detect）**

- 若用户未提供区域，`run()` 里 `sub_areas` 为空时自动设为整帧 `(0, frame_height, 0, frame_width)` —— **默认全屏处理**（`backend/main.py:338-340`；GUI 侧相同逻辑 `ui/home_interface.py:343-345`）。
- STTN_DET / LAMA / OPENCV 路径调用 `SubtitleDetect`（`backend.tools.subtitle_detect`）做**自动文本检测**：按采样步长 `SAMPLE_STEP`（fps≥60→4，≥30→3，否则→2，即至少每秒采样 8 帧，`backend/tools/subtitle_detect.py:29-39`）抽帧跑 PaddleOCR 检测，找到字幕帧；再在两帧之间线性插值补帧（`find_subtitle_frame_no` 中 `max_gap = SAMPLE_STEP*2`，`backend/tools/subtitle_detect.py:84-132`）；再做区域统一（`unify_regions`）与区间合并（`filter_and_merge_intervals`，保证区间长度≥STTN 参考帧数，`backend/tools/subtitle_detect.py:181-293`）。
- PROCESAITER 路径额外做**场景切分**：`get_scene_div_frame_no()` 用 `scenedetect.ContentDetector` 找场景切换点，把字幕区间按场景切段，避免跨场景光流传播（`backend/tools/subtitle_detect.py:157-170`、`159-167`）。

**阶段 2：生成 mask**

- `create_mask(mask_size, coords_list)`：在 `(H, W)` 的全零 uint8 mask 上，对每个 `(xmin,xmax,ymin,ymax)` 框画**实心白色矩形**（`cv2.rectangle thickness=-1` = 255），每边再外扩 `subtitleAreaDeviationPixel`（默认 10px，`backend/config.py:61`）。（详见第 4 节。）
- mask 由检测框或用户框直接生成，**不做像素级二值化**；唯一一次阈值化出现在模型输入前把 0/255 mask 归一为 0/1（`backend/inpaint/sttn_auto_inpaint.py:48` 等，供模型使用）。

**阶段 3：视频修复（inpaint）**

- 按模式调用 STTN / LAMA / ProPainter / OpenCV 之一，对 `sub_areas` 内、mask 覆盖的区域做填补（详见第 2 节）。
- 视频帧经 `FramePrefetcher` 后台线程预解码，I/O 与推理重叠（`backend/tools/video_io.py:12-51`）。

**阶段 4：合成输出（composite & encode）**

- 修复帧写进 `FFmpegVideoWriter`（libx264 管道，参数见第 5 节），尺寸 `size = (width, height)` 与源视频一致（`backend/main.py:58`）。
- 修复区域与原始帧在 mask 处融合：截取当前帧在 `inpaint_area` 的行带，把模型输出的补全内容 `resize` 回原尺寸后 `mask_area*comp + (1−mask_area)*frame` 混合（STTN_AUTO `backend/inpaint/sttn_auto_inpaint.py:312-315`；STTN_DET `backend/inpaint/sttn_det_inpaint.py:93` 整带覆盖；LAMA/ProPainter 直接整带替换）。
- 最后 `merge_audio_to_video()`：ffmpeg 抽取原音频（`-acodec copy -vn`），再与修复视频合并（`-vcodec copy -acodec copy`）（`backend/main.py:418-460`）。

> **状态**：流水线各阶段及其调用关系 = **已确认事实**（逐行来自 `backend/main.py`、`backend/tools/*.py`）。

---

## 2. 视频修复模型：STTN 还是 ProPainter？

**两者都有，且 STTN 是默认**。VSR 提供了 5 种 `InpaintMode`（`backend/tools/constant.py:4-12`）；默认 `STTN_AUTO`（`backend/config.py:53`、CLI 默认 `backend/tools/args_handler.py:23`）。

### STTN（默认，两套子模型）

VSR 内置 **两个 STTN 变体**，模型、输入分辨率、mask 语义都不同：

| 变体 | 权重文件 | 模型定义 | 模型输入分辨率 (W×H) | mask 来源 | 是否 OCR 检测 |
|------|----------|----------|----------------------|-----------|---------------|
| **STTN_AUTO**（默认，`sttn-auto`） | `models/sttn-auto/infer_model.pth`（`backend/tools/model_config.py:14`） | `backend/inpaint/sttn/auto_sttn.py` 的 `InpaintGenerator` | **640 × 120**（`backend/inpaint/sttn_auto_inpaint.py:38`） | 整条用户框选行带（不带 OCR），`get_inpaint_area_by_mask` 取整条字幕区 | 否（跳过检测，`STTN_SKIP_DETECTION` 语义） |
| **STTN_DET**（`sttn-det`） | `models/sttn-det/sttn.pth`（`backend/tools/model_config.py:15`） | `backend/inpaint/sttn/network_sttn.py` 的 `mask`-aware `InpaintGenerator` | **432 × 240**（`backend/inpaint/sttn_det_inpaint.py:33`） | OCR 检测出的各字幕框（mask 还送入 transformer 参与 attention） | 是 |

- **架构（STTN_AUTO 与 DET 一致，均源自 STTN 论文）**：frame-level 2D 卷积 encoder → 8 层堆叠 TransformerBlock（每块 = MultiHeadedAttention + FeedForward，残差连接）→ frame-level decoder（`adconv` 上采样）。`channel=256`；STTN_AUTO patch sizes `[(80,15),(32,6),(10,5),(5,3)]`（`auto_sttn.py:67-73`）；STTN_DET patch sizes `[(108,60),(36,20),(18,10),(9,5)]`（`network_sttn.py:68-74`）。
- **时序机制**：模型一次喂入一批帧（clip），encoder 提取各帧特征后，在 **邻居帧窗口 + 全局参考帧** 上做多头 patch-based 时空注意力，再 decoder 重建。VSR 推理细节：
  - 邻居步长 `sttnNeighborStride`（默认 5，`backend/config.py:89`），对每帧取 `[f±stride]` 邻居（`auto_sttn.py` 的循环，`backend/inpaint/sttn_auto_inpaint.py:142-144`）。
  - 参考帧采样 `sttnReferenceLength`（默认 10），`get_ref_index` 每 `ref_length` 取一帧补充进注意力（`backend/inpaint/sttn_auto_inpaint.py:107-120`）。
  - 最大同时加载帧数 `sttnMaxLoadNum`（默认 50，`backend/config.py:93`），`getSttnMaxLoadNum` 会强制取 `max(sttnMaxLoadNum, stride*referenceLentlength)`（`backend/config.py:94`）；另有按显存动态下调 `clip_gap` 的 OOM 保护（`backend/inpaint/sttn_auto_inpaint.py:228-238`）。
  - 邻居窗口有重叠时，多 pass 结果按 `0.5+0.5` 平均融合（`backend/inpaint/sttn_auto_inpaint.py:159-162`）。
- **输入预处理**：每帧裁出字幕行带（STTN_AUTO 高度 `split_h = int(W_ori*3/16)`，`sttn_auto_inpaint.py:54`；STTN_DET 竖屏 `H*5/9`、横屏 `W*5/18`，`sttn_det_inpaint.py:48-51`），统一 resize 到 640×120 / 432×240 再进模型；输出另一路 resize 回行带原尺寸与原始帧 mix。
- **底层论文**：Zeng Yanhong 等，*Learning Joint Spatial-Temporal Transformations for Video Inpainting (STTN)*，**ECCV 2020**，arXiv:2007.10247。原模型训练/测试输入统一为 **432×240**（论文 Sec.4，见 ar5iv 版），与 VSR 的 STTN_DET 输入一致；patch-based 多头时空注意力沿空间与时序两个维度搜索（论文 Sec.3.2）。STTN_AUTO 的 640×120 为 VSR 自训变体（尺寸与论文原始 432×240 不同，**推断**为 VSR 针对“字幕条形区域”重训的窄条版本）。

### ProPainter（可选，用于剧烈运动）

- 权重目录 `models/propainter/`，内含 `ProPainter.pth` + `raft-things.pth` + `recurrent_flow_completion.pth`（`backend/tools/model_config.py:16`、`backend/inpaint/propainter_inpaint.py:168-187`）。
- 是官方 ProPainter 完整实现：**四个子阶段** = RAFT 双向光流 → Recurrent Flow Completion 光流补全 → image propagation → feature propagation + TemporalSparseTransformer（`propainter_inpaint.py:219-358`）。
- 架构参数（`backend/inpaint/video/model/propainter.py`）：`InpaintGenerator` encoder 含分组残差 `group=[1,2,4,8,1]`、通道 128 / hidden 512、SoftSplit/SoftComp（kernel/stride/pad = 7/3/3）、BidirectionalPropagation（img-prop `learnable=False`、feat-prop `learnable=True`，`DeformableAlignment` deform_groups=16）、`TemporalSparseTransformerBlock`（`depths=8`、`num_heads=4`、`window_size=(5,9)`）。
- 推理参数（`backend/inpaint/propainter_inpaint.py:140-158`）：`sub_video_length=80`（长视频分片）、`neighbor_length=10`、`ref_stride=10`、`raft_iter=20`、FP16（CPU 上自动关半精度）；按宽度切 RAFT 短片段 `short_clip_len`（≤640→12，≤720→8，≤1280→4，else→2，`propainter_inpaint.py:221-228`）；区域取 `multiple=8` 对齐（`propainter_inpaint.py:374`）。
- **底层论文**：Zhou Shangchen 等，*ProPainter: Improving Propagation and Transformer for Video Inpainting*，**ICCV 2023**，arXiv:2309.03897；官方模型训练用 432×240（ProPainter README/`inference_propainter.py` 示例）。
- **ProPainter 在 VSR 时序集成**：对字幕存在区间，`propainter_mode` 用 `FramePrefetcher` 读入整段帧，按 `propainterMaxLoadNum`（默认 70，`backend/config.py:100`）分批，调用 `propainter_inpaint(batch, mask)`；单帧的区间则退回 LAMA（`backend/main.py:217-224`）。

### LAMA（图片与单帧兜底）

- `big-lama.pt` 经 `torch.jit.load` 加载（`backend/inpaint/lama_inpaint.py:13`）。图片路径固定走 LAMA（`backend/main.py:353-369`）。输入按 `pad_img_to_modulo(…,8)` 对称补齐到 8 的倍数（`backend/inpaint/utils/lama_util.py:52-73`）。
- **底层论文**：Suvorov 等，*Resolution-Robust Large Mask Inpainting with Fourier Convolutions (LaMa)*，**WACV 2022**。

### OpenCV（最简兜底）

- `cv2.inpaint(frame, mask, 3, cv2.INTER_LINEAR)`（`backend/inpaint/opencv_inpaint.py:9`），逐帧 Telea/Criminisi 类修复。

> **状态**：两种模型同时存在 = **已确认**；STTN 为默认、ProPainter 可选 = **已确认**；各架构/分辨率/参数均 **已确认**（源码行号）；STTN_AUTO 640×120 为 VSR 自训窄条变体 = **推断**。

---

## 3. 字幕“检测”怎么做：手动框选还是自动 OCR？

**默认是自动 OCR（文本检测），手选区域是可选的约束**；且两种能力叠加：

- **自动检测（默认）**：`SubtitleDetect.text_detector` 使用 **PaddleOCR 的 `TextDetection` 文本检测模型**（`backend/tools/subtitle_detect.py:45-54`），依赖 `paddleocr==3.4.0`（`requirements.txt:9`）。模型名来自 `ModelConfig.DET_MODEL_NAME`：默认 `PP-OCRv5_server_det`（server 检测模型），或 `PP-OCRv5_mobile_det`（mobile）；对应权重目录 `models/V5/ch_det` 与 `models/V5/ch_det_fast`（`backend/tools/model_config.py:6-23`、`backend/config.py:55`）。检测在 CPU 上跑（`device="cpu"`），并检测到 ONNX 加速器时开启 `enable_hpi`（`subtitle_detect.py:47-54`）。
  - 注意：默认 `SubtitleDetectMode.PP_OCRv5_SERVER`（`backend/config.py:55`），旧配置里的“快速 / 精准”被迁移映射到 mobile / server（`backend/config.py:115-120`）。
- **手动框选（可选约束）**：GUI 里用户可在画面上拖框选择字幕区域（`ui/home_interface.py:546-559`、`594`、`614`、`633` 等的 `video_display_component` 拖拽）；这些区域存为 `sub_areas`，运行时**把 OCR 检出的框裁剪到用户框内**（单区域快速路径 `subtitle_detect.py:70-75`，多区域 `76-81`）。若用户不选，则**整帧为检测范围**（见第 1 节）。
  - 在 `sttn-auto` 模式中，**完全跳过 OCR**，直接用用户框选区域（或整帧）当 mask（`backend/main.py` 的 `sttn_auto_mode`，`247-258`；对应 README `STTN_SKIP_DETECTION`）。
- 检测框转矩形：`ocr.get_coordinates` 把四边形 4 点折成 `(xmin, xmax, ymin, ymax)`（`backend/tools/ocr.py:1-20`）。
- 检测是**“文本检测”而非“文字识别”**：VSR 只取文本**位置框**，不需要 OCR 识别出文字内容（`subtitle_detect.detect_subtitle` 只用 `res['dt_polys']`，`subtitle_detect.py:61-65`）。

> **状态**：自动 OCR（PP-OCRv5 det）为默认且必用的检测路径、手选区域为约束/或 skip-detection 时的唯一依据 = **已确认**。

---

## 4. Mask 如何生成：二值化阈值 / 膨胀因子 / 检测框输出？

- Mask **来源于检测框（或手选框）绘制的白色实心矩形**，不是对图像像素做二值化的结果。
- `create_mask(size, coords_list)`（`backend/tools/inpaint_tools.py:31-47`）：
  - 初始化全零 `uint8` mask；
  - 对每个 `(xmin,xmax,ymin,ymax)`，四边各外扩 `config.subtitleAreaDeviationPixel`（**默认 10 px**，`backend/config.py:61`），然后 `cv2.rectangle(..., thickness=-1)` 填成 255。
  - **膨胀因子**就是 `subtitleAreaDeviationPixel`，由配置统一作用于所有检测框（官方注释：防文本框过小导致修复后字幕边缘残留，`backend/config.py:60-61`）。
- 检测时对框的**几何过滤/合并参数**（`backend/config.py:57-66`）：
  - `subtitleYXAxisDifferencePixel=10`：若框高比宽大超过阈值则认为误检，丢弃（`backend/main.py:316-317`）。
  - `subtitleAreaYAxisDifferencePixel=20`：判定多个框是否同一行字幕（用于合并）。
  - `subtitleAreaPixelToleranceXPixel/YPixel=20`：判定相邻帧的框是否“同源/相似”，用于 `unify_regions` 做时序统一（`subtitle_detect.py:172-215`）。
- 给修复模型前，mask 会二次处理：STTN `cv2.threshold(...,127,1,THRESH_BINARY)` 归 0/1（`sttn_auto_inpaint.py:48`），ProPainter `read_mask` 中再做**二次膨胀**（`mask_dilates=4` 与 flow-mask 各自 `binary_dilation`，`propainter_inpaint.py:32-77`）。注意：ProPainter 的 4px 膨胀是自身推理逻辑，与 VSR 的 10px 框膨胀是两回事。
- ProPainter 还会用 `get_inpaint_area_by_mask(..., multiple=8)`（`inpaint_tools.py:49-242`）把各 mask 联通域合并成一条条行带并切成 8 的整数倍高度，供模型裁剪（`propainter_inpaint.py:374`）。

> **状态**：mask 由检测/手选框绘制 + `subtitleAreaDeviationPixel`(默认 10px) 膨胀 = **已确认**；ProPainter 内额外 4px 膨胀 = **已确认**；不存在像素二值化生成 mask = **已确认**。

---

## 5. “无损分辨率”输出如何保证：ffmpeg 编码参数

- 视频帧经 `FFmpegVideoWriter` 以 **ffmpeg 管道**编码（`backend/tools/video_io.py:54-104`），命令参数（`video_io.py:62-77`）：
  ```
  -y -f rawvideo -vcodec rawvideo -s WxH -pix_fmt bgr24 -r <fps> -i -
  -c:v libx264 -pix_fmt yuv420p -crf 18 -preset fast -loglevel error <out>
  ```
  → **`-c:v libx264` + `-crf 18` + `-preset fast` + `-pix_fmt yuv420p`**；尺寸 `-s WxH` 与源视频一致。
- 结论：「无损分辨率」=**尺寸与源一致、未缩放**，配合 **CRF 18（视觉近无损）** 的 libx264 编码。**不是逐位数学无损**（`yuv420p` + 有损编解码），但仍保留原像素分辨率。源码注释也明确“使用 FFmpeg libx264 编码，比 mp4v 质量更好、文件更小”（`backend/main.py:64`）。
- 音轨：ffmpeg 抽取原音频 `-acodec copy -vn`，合并时 `-vcodec copy -acodec copy`（`backend/main.py:421-441`）——音频为真·无损 copy。
- 说明：这是当前 `main` 分支行为。曾有 issue 反映输出“颜色空间/码率变化”（issue #48），与这里 `yuv420p`/`crf 18` 的设置相关。

> **状态**：具体编码参数 = **已确认**（源码）；“无损 = 分辨率保留 + CRF18” 的解读、以及“非逐位无损” = **推断**（基于参数语义）。

---

## 6. 已知失败模式

来自仓库 README 算法定性说明 + 源码约束 + **GitHub issue 实证**。逐项给出证据与“哪些失败、如何失败”。

| 场景 | 行为 / 失败方式 | 证据与来源 |
|------|------------------|-----------|
| **剧烈运动 / 运动背景** | STTN 效果较弱；VSR 官方建议这类用 **ProPainter**（“对运动非常剧烈的视频效果较好”）；ProPainter 更吃显存更慢 | README_en.md:240 == README.md:242；config.py:50 |
| **多行字幕** | 用户实测“多行字幕效果差强人意” | issue #108（标题即如此） |
| **动态/移动水印、闪烁** | “移动的,动态水印能处理吗”“动态水印去除的不是很好”“豆包…动态水印无法去除” 多票证实动态水印难 | issues #236、#232、#220、#247 |
| **logo / 复杂象形水印（非“类文字”）** | 用户实测“对文字效果很好，但 **logo 很难去**”；项目定位本来就是“文本及类文本” | issue #178（英文原文，作者自我定位）；README 描述"text-like watermarks" |
| **字幕残留于部分帧** | STTN 智能擦除下“有些帧去除了，有些帧没去掉”，处理后仍有**残影** | issues #213、#204 |
| **画质变模糊** | “成功去除字幕，但是画质变模糊了”；另有“处理后颜色空间/码率变低” | issues #194、#48 |
| **误伤非文字内容** | 会把 **手指**（含皮肤的复杂内容）当文字处理模糊掉 | issue #10（作者/用户反馈） |
| **恒定字幕（全程都有）** | 用户困惑“全程都有字幕是否无法去除”——实际 STTN 靠时序参考仍能补，但用户感知为去除不净；深层原因是检测采样+时序性，样例质量差异大 | issue #117（语义上归于感知/推断）、#213 |
| **文字边缘残留** | 用户反馈“字幕总会露出一点点（字体太大）”，提示需要调节 `subtitleAreaDeviationPixel` mask 膨胀或改选区 | issue #78（隐含于“指定区域”需求） |

**机制层面的推断解释（非 issue 直接声明）：**
- **闪烁字幕 / 快速切换**：检测按约每 8 帧采样一次 + 区间插值（`subtitle_detect.py:29-39,112-121`），若字幕出现/消失间隔小于采样步长或位于两采样点之间，可能漏检或错时——**推断**。
- **字幕与前景/运动物体重叠**：STTN/LAMA 是内容生成型填补，重叠区域前景无法从前后帧借位，易产生涂抹/伪影——**推断**。
- **渐变字幕（半透明/抗锯齿边缘）**：检测框按实心矩形画 mask，边缘渐变区域被整块覆盖重绘，易出现硬边或残留——**推断**。
- **多行字幕**：VSR 的 STTN 行带高度固定 `W*3/16` 或按比例，ProPainter 区域合并逻辑按同行合并；多行超出单条行带时被截断，需要多区域支持——**推断**（叠加 issue #108 实证）。

> **状态**：加粗的 issue # 行为 = **已确认事实（用户/官方在 issue 中的一手反馈）**；“机制层面的推断解释”部分 = **推断**（基于算法/参数，无 issue 直接词句，仅作分析供参考）。

---

## 7. 性能画像：延迟 / 显存 / CPU

### 显存（ProPainter，官方一手数据）
- VSR 自己的 `backend/config.py:97-100` 给出 ProPainter 显存指引：
  - **1280×720**：`MaxLoadNum=80` ≈ 25GB；`=50` ≈ 19GB；
  - **720×480**：`=80` ≈ 8GB；`=50` ≈ 7GB。
- 与官方 ProPainter README 的显存表一致（1280×720 @80帧 fp16=25G、@50帧=19G；720×480 @80=8G）：

| 分辨率 | 50 帧 | 80 帧 |
|--------|------|------|
| 1280×720 | 28G / 19G (fp32/fp16) | OOM / 25G |
| 720×480 | 11G / 7G | 13G / 8G |
> 来源：`sczhou/ProPainter` README（存储于本 repo 调研缓存 `_tmp/papers/ProPainter__README.md:190-195`）。VSR 默认 `propainterMaxLoadNum=70`。
- STTN `sttnMaxLoadNum` 默认 50，且带按显存动态下调 `clip_gap` 的 OOM 保护（`sttn_auto_inpaint.py:228-238`）。

### 速度（issue 一手数据，型号差异大）
- **STTN + OCR**：1920×1080 @30fps 一段视频 **约 2–3 分钟**（issue #96）。
- **STTN 智能擦除（跳过检测、整框扫描）**：同一段 **约 20 分钟**（issue #96 实测对比；因逐帧/整框特征处理量大）。
- **LAMA**：3090 / 3060Ti 下“太慢”“GPU 使用率 <20%”“17 分钟视频 20 分钟才 10%”——LAMA 为逐帧推理且 GPU 占用低（issues #87、#127、#119、#3）。
- 一个可持续参考：默认 STTN 路径（检测 + 窄条修复）是官方推荐的“快速版”，README 明确“改 `MODE=STTN` + `STTN_SKIP_DETECTION=True` 可大幅提速”（README_en.md:228-233）。
- **没有官方逐帧/每分钟 fps 一手基准表**：因型号/分辨率/算法差异巨大，具体速率只能给区间 → **推断**（基于 issues 实例）。

### CPU
- **CPU 可运行**：官方提供纯 CPU 安装（`pip install paddlepaddle==3.0.0 ... cpu` + 无 GPU torch，README：`setup` 第 (3) 节）；预构建包含 `vsr-windows-cpu.7z`（README.md:40）。检测（PaddleOCR）已固定跑 CPU；STTN/LAMA 在 `torch.device("cpu")` 上推理（`backend/main.py:257` 等），但 **CPU 上 ProPainter 自动关 FP16 且更慢**（`propainter_inpaint.py:145-147`）。
- CPU 无 GPU 时速度通常远慢于 GPU，issues 中大量“GPU 利用率低/速度慢”集中在 LAMA 与默认路径（见上）——属用户侧配置/算法差异，非 CPU 不支持。
- 硬件加速优先级：DirectML → CUDA → MPS → CPU（`hardware_accelerator.py:75-88,142-155`）；ONNX 加速器（Dml/ROCm/MIGraphX/VitisAI/OpenVINO/Metal/CoreML/CUDA）也会被检测并用于 OCR 的 HPI（`hardware_accelerator.py:44-66`）。

> **状态**：ProPainter 显存数值、CPU 可运行、默认 STTN 路径较快的官方表述 = **已确认**；具体每秒帧数 = **推断**（无一手基准，仅 issue 实例）。

---

## 8. Confirmed vs Inference（确认 vs 推断汇总）

### 已确认事实（源码行号 / issue 一手）
1. 五档修复算法与默认 `sttn-auto`（`backend/tools/constant.py:4-12`，`backend/config.py:53`）。
2. 端到端四阶段流水线：检测 → mask → 修复 → ffmpeg 合成（`backend/main.py:335-401`）。
3. 自动检测 = PaddleOCR `TextDetection`（PP-OCRv5 det，server 默认 / mobile 可选）（`backend/tools/subtitle_detect.py:45-54`、`model_config.py:6-23`、`requirements.txt:9`、`backend/config.py:55`）。
4. 手选区域是约束项、`sttn-auto` 完全跳过 OCR（`subtitle_detect.py:70-81`、`main.py:247-258`、`ui/home_interface.py:343-345`）。
5. mask = 检测框画实心矩形 + `subtitleAreaDeviationPixel`(默认10px) 膨胀（`inpaint_tools.py:31-47`、`config.py:61`）；ProPainter 内部另 +4px 膨胀（`propainter_inpaint.py:32-77`）。
6. STTN 两个变体：AUTO 640×120 / DET 432×240（`sttn_auto_inpaint.py:38`、`sttn_det_inpaint.py:33`）；STTN 邻居步长5/参考帧10/最大加载50（`config.py:89-94`）；架构 = 8×TransformerBlock, channel 256（`auto_sttn.py:67-73`、`network_sttn.py:68-74`）。
7. ProPainter = 官方完整实现（RAFT + Recurrent Flow Completion + propagation + transformer），4 阶段推理，SUB_VIDEO=80/neighbor=10/ref_stride=10/fp16（`propainter_inpaint.py:140-187,219-358`；`backend/inpaint/video/model/propainter.py`）。
8. LAMA = big-lama.pt torch.jit 加载，图片与单帧兜底（`lama_inpaint.py:13`、`main.py:353-369`）；输入补 8 倍数（`lama_util.py:52-73`）。
9. 输出编码 = libx264 + CRF18 + preset fast + yuv420p，尺寸不变（`video_io.py:62-77`）；音频 copy 无损（`main.py:421-441`）。
10. 底层论文：STTN=ECCV 2020 arXiv:2007.10247；ProPainter=ICCV 2023 arXiv:2309.03897；LaMa=WACV 2022。
11. ProPainter 显存实测（720p @80≈25G 等，`config.py:98-99` + 官方 README）；CPU 可运行（README 安装第(3)节、`vsr-windows-cpu` 包、`propainter_inpaint.py:145-147`）。
12. 失败模式实证：多行(#108)、logo(#178)、动态水印(#236/#232/#220)、残影(#204)、画质变糊(#194/#48)、误伤手(#10)、STTN 智能擦除留残留(#213)、滤镜/字形大导致露边(#78)。

### 推断（无一手直接词句，基于算法/参数的分析）
1. STTN_AUTO 640×120 窄条 = VSR 自训变体（论文原始 432×240）。
2. “无损 = 分辨率保留 + CRF18 视觉近无损，非逐位数学无损”。
3. 闪烁字幕漏检（采样步长 + 插值时窗）、“重叠前景易伪影”、“渐变/半透明字幕边缘硬边”、“多行超出单行带被截断”。
4. 具体每帧/每分钟 fps 数值（无官方基准表，仅 issue 实例区间）。

---

## 附：一手来源索引

| 主题 | 一手来源 |
|------|----------|
| 流水线、分派、音频合成、选区默认 | `backend/main.py`（本调研缓存 `_tmp/vsr/backend__main.py`） |
| 参数/枚举/默认 | `backend/config.py`、`backend/tools/constant.py` |
| 检测 | `backend/tools/subtitle_detect.py`、`backend/tools/ocr.py`、`backend/tools/model_config.py`、`requirements.txt` |
| mask / 区域 | `backend/tools/inpaint_tools.py` |
| 输出编码 | `backend/tools/video_io.py`、`backend/tools/ffmpeg_cli.py` |
| STTN 模型/推理 | `backend/inpaint/sttn_auto_inpaint.py`、`backend/inpaint/sttn_det_inpaint.py`、`backend/inpaint/sttn/auto_sttn.py`、`backend/inpaint/sttn/network_sttn.py`、`backend/inpaint/utils/sttn_utils.py` |
| ProPainter | `backend/inpaint/propainter_inpaint.py`、`backend/inpaint/video/model/propainter.py`、（官方 `sczhou/ProPainter` README/inference 缓存） |
| LAMA | `backend/inpaint/lama_inpaint.py`、`backend/inpaint/utils/lama_util.py` |
| 硬件加速 / 设备选择 | `backend/tools/hardware_accelerator.py` |
| README / 算法定性 / 性能建议 | `README_en.md`、`README.md`（缓存 `_tmp/vsr/main__README*.md`） |
| 失败模式 / 性能实证 | GitHub issues（缓存摘要 `_tmp/vsr/issues_dump.txt`，含 URL）；#108 #178 #236 #232 #220 #204 #194 #48 #10 #213 #78 #96 #87 #127 #119 #3 |
| 论文 | STTN ECCV 2020 arXiv:2007.10247；ProPainter ICCV 2023 arXiv:2309.03897；LaMa WACV 2022 |
