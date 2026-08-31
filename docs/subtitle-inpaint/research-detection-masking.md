# 字幕/水印检测与遮罩生成模块研究（硬字幕去除 · 搬运/翻译场景）

> **Ticket #35** · Part of #33（`subtitle-inpaint` 探索地图）。为「去掉英文硬字幕再烧中文」的搬运/翻译场景，做**检测 + 遮罩生成**模块的架构选型：自研 vs 复用。本报告只研究「检测与遮罩」，视频补全（inpainting）见姊妹 ticket #36。
>
> **结论先行（Reuse-vs-Build）**：**模块整体走「复用 + 薄封装」，不全新自研检测器**。(A) 字幕检测与遮罩生成，直接**复用 [`YaoFANGUK/video-subtitle-remover`（VSR）的 detect + create_mask + 时序分组管线**（Apache-2.0，检测=深度 DBNet/PaddleOCR，遮罩=矩形框填充），把它的「手动框选区」改造为「半自动初定位 + 自动跟踪」。(B) 仅做**一层薄的自研**负责两件 VSR 没有做好 / 不做的事：① 字幕 vs 场景内文字的判别（VSR 的 `ch` 检测模型对中文/英文以外的重叠文字有误伤，Issue #176/#170）；② 用并行「检测 + Inpainting 补全（ProPainter）」解耦，使检测不在每一帧都跑。理由详见末尾推荐节。

---

## 目录

1. [背景与场景约束](#1-背景与场景约束)
2. [子问题 1：主流检测方案与在「视频字幕」上的表现](#2-子问题-1主流检测方案与在视频字幕上的表现)
3. [子问题 2：字幕叠加 vs 画面内真实文字](#3-子问题-2字幕叠加-subtitle-overlay-vs-画面内真实文字)
4. [子问题 3：逐帧检测的时序稳定性](#4-子问题-3逐帧检测的时序稳定性)
5. [子问题 4：遮罩精度 vs 补全质量](#5-子问题-4遮罩精度-vs-补全质量)
6. [子问题 5：VSR 与专门字幕检测项目，哪个最值得复用](#6-子问题-5哪个现有方案最值得复用)
7. [子问题 6：全自动 vs 半自动取舍](#7-子问题-6全自动-vs-半自动取舍)
8. [复用/自研推荐与理由](#8-复用自研推荐与理由)
9. [来源汇总](#9-来源汇总)

---

## 1. 背景与场景约束

- **真实场景**：搬运/翻译 —— 去掉原始（通常英文）硬字幕，再烧新语言（中文）字幕；**精度优先，可接受慢**。
- **硬件**：本地单机 NVIDIA GPU，与 auto-dub 的 VoxCPM TTS 同机，需要 GPU 锁互斥（`lib/gpu_lock.py`）。
- **本质**：硬字幕去除是**视频时空 inpainting**（检测 → 遮罩 → 时序补全），**不是逐帧图像修复**。检测与遮罩的质量直接决定补全质量。
- **参考基础**：`YaoFANGUK/video-subtitle-remover`（本文称 **VSR**），本地、无损分辨率、核心用视频补全网络（STTN → ProPainter / LaMa）。许可证 **Apache-2.0**。
- **本报告关键校正**：VSR 的检测机制是**深度文字检测（PaddleOCR DBNet / PP-OCRv5）**，遮罩是**检测框填充的矩形**，**不是**「手动框选 + 二值阈值 + 膨胀/腐蚀 + 逐像素 subtitle-detect 核」。原地图笔记(`map-body.md`)对此的假设需要修正（详见 §6 与 §8）。

---

## 2. 子问题 1：主流检测方案与在「视频字幕」上的表现

### 2.1 方案分类与机理

| 方案 | 机理 | GPU 可行性 | 对「视频字幕」的优势 | 劣势 |
|---|---|---|---|---|
| **手动区域选择（固定字幕 ROI）** | 用户在画面下方带手绘一个/多个框，工具在该区域生成遮罩并补全 | 零推理成本 | 零误检、天然时序稳定、易实现调试 | 花字/上三分之一标题/多行/移动字幕无效；每片视频要重框一次 |
| **传统 CV（形态学/边缘/MSER/时序差分）** | 边缘+形态学膨胀成文字行；时序差分把「静止高对比」字幕从动态背景中剥离；MSER 提取稳定极值区域 | CPU 即可，近实时 | 时序差分天然解决「仅在字幕出现时检测」；实现简单 | 对抗锯齿/彩色字/复杂背景脆弱；单帧无法区分字幕与画面内静态文字 |
| **OCR 引擎作检测器（PaddleOCR / EasyOCR / Tesseract）** | 用其内置文字检测子网络（region proposal）做检测 | PaddleOCR/EasyOCR 支持 CUDA；Tesseract 基本 CPU | PaddleOCR 对高对比小字召回强，多语言，GPU 实时 | 会连带检出画面内场景文字，需 ROI/遮罩约束；Tesseract 检测弱、需裁剪放大 |
| **深度文字检测器（DBNet/EAST/CRAFT/TextFuseNet）** | 判界回归文字框 | GPU 可行，DBNet 最快 | 精度高；但训练/评测集中在**场景文字**基准，非视频字幕 | EAST 对小字召回弱；CRAFT 较重；TextFuseNet 是 Mask-RCNN 系、过重 |
| **DETR/DINO 系视频文字检测（TransDETR 等）** | 端到端视频文字 spotting + 跟踪 | 研究级 | **唯一真正面向「视频文字」**（ICDAR15 video / RoadText-Video） | 研究级，未打包成去字幕产品 |

### 2.2 关键事实与证据

- **社区产品几乎都走「固定字幕带 / ROI + classical CV + OCR + 补全」而非「神经检测器逐帧跑」**。三个最流行的开源工具（`video-subtitle-extractor`、`video-subtitle-remover`/VSR、`pyvideotrans`）皆然。字幕位于可预期的底部带，工具要么让用户框区域，要么用经典 CV 建一个**跨帧共享的遮罩**，只用 OCR 作检测器+识别器。证据：[VSR README](https://github.com/YaoFANGUK/video-subtitle-remover)、[video-subtitle-extractor](https://github.com/YaoFANGUK/video-subtitle-extractor)、[pyvideotrans](https://github.com/jianchang512/pyvideotrans)。
- **PaddleOCR PP-OCRv5 是社区默认引擎**，也是 VSR 内嵌的检测器（PP-OCRv4→v5）。GPU 上检测行 tens-of-ms，实时（10–30+ fps）可行；但只需**关键帧**跑一次，不必逐帧。证据：[PaddleOCR det DB 文档](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version2.x/algorithm/text_detection/algorithm_det_db.en.md)、[PP-OCRv5 文档](https://github.com/cuicong01/PaddleOCR/blob/main/docs/version3.x/algorithm/PP-OCRv5/PP-OCRv5.en.md)、[模型列表（CPU/GPU 时延）](https://www.paddleocr.ai/latest/version3.x/model_list.html)。
- **DBNet**（AAAI 2020）——概率图 + 可学习阈值二值化，场景文字又快又准，是 PaddleOCR/EasyOCR/MMOCR 的骨干。[arXiv:1911.08947](https://arxiv.org/abs/1911.08947) · [MMOCR DBNet++](https://github.com/open-mmlab/mmocr/blob/main/configs/textdet/dbnetpp/README.md)
- **EAST**（CVPR 2017）——全卷积直接回归旋转框，OpenCV 传统默认文字检测。[CVPR 2017 开放获取](https://openaccess.thecvf.com/content_cvpr_2017/html/Zhou_EAST_An_Efficient_CVPR_2017_paper.html)
- **CRAFT**（2019）——字符级 region + affinity map，任意形状词框精确但较重。[arXiv:1904.01941](https://arxiv.org/abs/1904.01941) · [官方代码](https://github.com/clovaai/CRAFT-pytorch)
- **TextFuseNet**（IJCAI 2020）——Mask-RCNN 系实例分割式，过重，只对场景文字评测。[IJCAI 2020](https://www.ijcai.org/Proceedings/2020/72)
- **视频字幕是独立且欠测的分支**：ICDAR 有视频文字竞标任务、RoadText-Video 是视频文字跟踪/识别基准。**场景文字检测器都没在「视频字幕」上预训练**，实际视频上需配 ROI + 时序 mask。[ICDAR Text in Videos](https://rrc.cvc.uab.es/?ch=3&com=evaluation&task=4) · [RoadText-Video](https://cdn.iiit.ac.in/cdn/cvit.iiit.ac.in/images/ConferencePapers/2023/RoadText_Video.pdf)
- **TransDETR**（arXiv:2203.10539）是唯一面向视频文字的 DETR 系，含跟踪、在视频文字基准评测，但研究级。[arxiv.org/abs/2203.10539](https://arxiv.org/abs/2203.10539) · [代码](https://github.com/weijiawu/TransDETR)

> **对视频字幕的结论**：手动 ROI + 经典 CV 是「强精度、零误检」的起点；PaddleOCR-DBNet 是最务实的深度检测器（GPU 实时、多语言）。EAST/CRAFT 过时或偏重；TextFuseNet、DETR/DINO 文字检测是研究负载，**不值得为去字幕自建**。**任何神经检测器在真实视频上都需要底部带 ROI + 时序 mask 约束，这正是社区工具的做法。**

---

## 3. 子问题 2：字幕叠加（subtitle overlay）vs 画面内真实文字（scene text）

### 3.1 是不是必答问题？

**是，且是「正确输出 vs 毁掉源内容」的分水岭。** 任何把「所有检测到的文字框」直接喂给补全器的管线，都会抹掉画面里的物理文字（招牌、屏幕、衣服印花、书本）。两类失败不对称且都致命：

- **场景文字误判为字幕** → 你会补全掉一个店面招牌/TV 屏幕/衣服 logo，补全器发明替代文字/纹理，伪影比原文更显眼。
- **字幕漏判** → 硬字幕残留，成品对目标平台无用。

学术上把 **video decaptioning**（去字幕）与 **scene-text removal** 当作独立任务、独立数据集。[Deep Blind Video Decaptioning（CVPR 2019）](https://www.openaccess.thecvf.com/content_CVPR_2019/html/Kim_Deep_Blind_Video_Decaptioning_by_Temporal_Aggregation_and_Recurrence_CVPR_2019_paper.html) 正是把去字幕当**需跨帧时序聚合**的独立问题（字幕是瞬时叠加物，非静态场景元素）。

### 3.2 判别手段（按信息量排序）

1. **时序一致性（最强判别信号）**：字幕随对白变化、跨镜头存续、**被屏幕锁定不随相机动**；场景文字物理锚定在画面里、**随相机/刚体一致运动**。经典主源：[Temporal Integration for Word-Wise Caption and Scene Text Identification（ICDAR 2017）](https://ieeexplore.ieee.org/abstract/document/8269996)；后续用锐度/对比度随时间的稳定性判别。[ACPR 2017 锐度/对比度判别](https://ieeexplore.ieee.org/document/8575807)。
2. **空间先验（title-safe / safe-area 带）**：字幕放在画面下缘（或上缘标题）的安全区内（约 80–90% 画面内）。工具自身就展示 safe-area overlay。[Final Cut Pro viewer overlays](https://support.apple.com/en-az/guide/final-cut-pro/verded6d49d7/10.6.2/mac/11.5.1)。位置只是先验/门，不是决策（画面内文字可能也在带上、音乐视频有中段字幕）。
3. **OCR 语义先验**：字幕像对白/句子片段，场景文字像标签/牌匾。最强语义锚是**把 OCR 文本与音频转写对齐**——字幕应对得上说的话，场景文字通常对不上。
4. **专门的「superimposed text」判别研究线**：区分叠加文字与场景文字。[Detecting both superimposed and scene text …（MTAP 2013）](https://dl.acm.org/doi/10.1007/s11042-012-1201-2) · [区分场景与叠加文字以提升识别（SPIE 2015）](https://ui.adsabs.harvard.edu/abs/2015SPIE.9445E..09Q/abstract)。注意：「DeepFusion」这个名字的著名 CV 工作是 LiDAR-相机的 3D 目标检测，**不是**字幕判别器——不要引错。

### 3.3 已有开源实现

- **VSR**：PaddleOCR 检测 → 只对选中字幕带做遮罩 → 补全。但**它在字幕带里会把「带内重叠文字」也误当字幕**（Issue #176：带内移动文字被补全导致不稳定/模糊）。[Issue #176](https://github.com/YaoFANGUK/video-subtitle-remover/issues/176)
- **STRIVE**（ICCV 2021）：在**实例轨迹（track）级**做视频文字替换——是「只改字幕类字形、不碰场景文字」的视频原生做法，最贴合需求。[CVF ICCV 2021](https://openaccess.thecvf.com/content/ICCV2021/html/G_STRIVE_Scene_Text_Replacement_in_Videos_ICCV_2021_paper.html) · [代码](https://github.com/striveiccv2021/STRIVE-ICCV2021)
- **SAMText**（ViTAE-Transformer 2023）：视频文字 spotting 数据集，**提供区分字幕/叠加文字轨迹与场景文字轨迹的 mask 级标注**，可训练判别器。[GitHub](https://github.com/ViTAE-Transformer/SAMText)

> **给本模块的结论**：剪辑后处理方案 = 检测 → 按底部带/几何门控 → 时序投票/持久化过滤（持久跨整镜、随相机动的场景文字**不入遮罩**）→ 只对保留的字幕框建遮罩。**从不拿原始全量文字检测结果建遮罩。** 这是自研薄层要承担的核心判别能力之一。

---

## 4. 子问题 3：逐帧检测的时序稳定性

### 4.1 为什么会抖动

逐帧独立检测/OCR，无共享状态，导致：
- **独立逐帧打分**：同样文字在置信阈值上线内闪跳；OCR 更严，某帧可读性瞬时下降就**漏掉整帧遮罩**——补全器把该帧当「无可做之事」，形成**单帧 unmasked 闪灭**（最坏抖动）。[Overlay Text Extraction From TV News Broadcast（跟踪范式）](https://ar5iv.labs.arxiv.org/html/1604.00470)
- **置信度贴阈值**：淡入淡出/抗锯齿细字/颜色贴近背景 → 框 on/off、边缘振荡。
- **压缩/上采样伪影**在文字上逐帧加噪。

### 4.2 处置方法（按成熟度）

1. **检测→跟踪（track）**：检测后跨帧关联，得到稳定轨迹与稳定框；单帧噪声被平滑、掉帧被桥接。[ICDAR 2017 多帧跟踪]·[视频文字跟踪综述（Neurocomputing 2024）](https://www.sciencedirect.com/science/article/abs/pii/S0925231224011913) ·[视频文字 rediscovery/跨间隙预测（Wiley CIN 2025，淡入淡出场景）](https://onlinelibrary.wiley.com/doi/abs/10.1111/coin.12686)。
2. **坐标低通/中值/EMA/Kalman**：静态文字框几乎不该动；对框角+尺寸做窗口中值或 EMA 或 Kalman（Kalman 还能在检测失败时靠预测桥接缺口）。[ICDAR 2013 Temporal Integration](https://www.sciencedirect.com/science/article/abs/pii/S0925231224011913)。
3. **关键帧检测 + 插值传播遮罩**：在稀疏关键帧严检 mask，跨中间帧复用同一 mask。这是去字幕工具的主流工程做法——**又快又稳**（跨窗口恒定 mask 比逐帧重打分更稳，也省 GPU）。[ProPainter（mask 需跨窗一致）](https://arxiv.org/abs/2309.03897)。
4. **镜头/场景检测重置**：用 PySceneDetect 找镜头切点，在那里重置跟踪/插值/平滑状态；淡入淡出**不是**场景切，绝不能重置（否则重新引入抖动）。[PySceneDetect](https://github.com/Breakthrough/PySceneDetect) · [检测器文档](https://www.scenedetect.com/docs/head/api/detectors.html)。

### 4.3 真实工具怎么做（直接抄的模式）

- **VSR**（源码级验证，见 §6）：`find_subtitle_frame_no()` **自适应采样**（按 FPS 每 2–4 帧 OCR，≈≥8 帧/秒）→ `max_gap` 内插值补帧 → `unify_regions` 区域合并（±20px 容差）→ `find_continuous_ranges_with_same_mask` 归「同 mask」连续区间 → 用 `scenedetect` 切镜头分组 → `expand_frame_ranges` 前后扩展 3 帧盖住淡入淡出/偏移帧。`backend/tools/subtitle_detect.py` · `backend/tools/inpaint_tools.py`。
- **补全端假设**：E2FGVI/ProPainter 的流引导/传播**假定 mask 在窗口内稳定**，闪烁 mask 直接破坏输出。[E2FGVI](https://github.com/bzy-ai/E2FGVI) · [ProPainter](https://arxiv.org/abs/2309.03897)。
- **检测频率策略**：**不要逐帧跑检测器**（就是抖动来源 + 浪费 GPU）。按段检测、切点触发新关键帧、其间用廉价 Nth 帧探针验证字幕仍存在、偏差超容差才重检。补全才是重成本阶段（ProPainter 每窗静态 mask 限显存）。[Volcengine：E2FGVI vs ProPainter 分析](https://developer.volcengine.com/articles/7644756006559940662)

---

## 5. 子问题 4：遮罩精度 vs 补全质量

### 5.1 权衡本质

遮罩是影响补全质量**唯一主导因素**。需同时满足「完整盖住每根笔画含抗锯齿边缘」与「不吃到合法内容」。字幕笔画细（720p 约 3–6px，1080p 约 4–9px），失败模式**双峰**：

- **欠盖（mask 太小）** → 残留字形边缘/「鬼影」轮廓、彩色边带。OpenCV 的 `inpaintMask` 只修非零像素，mask 外一律不动——若 mask 止于笔画抗锯齿边缘内，该边缘就永远残留。[OpenCV Inpainting 文档](https://docs.opencv.org/3.4.20/d7/d8b/group__photo__inpaint.html)。
- **过盖（mask 太大）** → 补全吃到真实内容（文字、皮肤、纹理、重叠图形），产生糊斑、bleed、细节丢失。

**正确策略是不对称的**：**略偏过盖（膨胀）+ 受控边距**，靠补全器重建。因为「残留 1px 字边」远比「补全重建的几像素内容」显眼，而现代补全器（LaMa/MAT，视频端 ProPainter/STTN）擅长重建大块干净区域。

### 5.2 膨胀/腐蚀最佳实践（按笔画宽而非字号）

1. **先盖抗锯齿边缘**：最小膨胀 **1–2px** 是任何抗锯齿字幕的下限。
2. **再按笔画宽缩放**：常用规则 ≈ **1px + 笔画宽约 0.25–0.5×**（720p 正文 +2–3px，1080p 正文 +2–4px，粗标题 +4–6px）。VSR 源码用固定 `SubtitleAreaDeviationPixel = 10` px 的矩形 padding（而非按笔画宽），对多字号不最优——自研时可改为按检测框尺寸自适应。
3. **先 pad 检测框再膨胀**：检测框不含完整抗锯齿/下缘/斜体 overrun，先在字幕带四周 pad 数像素（下缘额外加 descender），再形态学膨胀。
4. **保持 mask 二值**：对 LaMa/MAT/ProPainter/STTN **保持二值 + 略膨胀**；羽化（feather）主要在 OpenCV 经典 Telea/NS 才有意义（软化接缝）。深模型训练时期望硬边界。[LaMa 论文](https://arxiv.org/pdf/2109.07161v1) · [MAT（Mask-Aware Transformer，mask 是权威边界）](https://openaccess.thecvf.com/content/CVPR2022/papers/Li_MAT_Mask-Aware_Transformer_for_Large_Hole_Image_Inpainting_CVPR_2022_paper.pdf)。
5. **MORPH_CLOSE 填内部孔洞**：字形内部计数孔/笔画间隙若不入 mask，补全器当成可信源而**保留鬼影内部形状**。膨胀后再对 mask 做 `MORPH_CLOSE` 桥接成实心区域。[OpenCV 形态学（erode/dilate/morphologyEx）](https://docs.opencv.org/4.10.0/d4/d86/group__imgproc__filter.html)。
6. **视频端要求 mask 时序一致**：ProPainter 的流引导传播会在跨帧 mask 不一致处读取/写入接缝并 smear——**同一字幕事件的每帧 mask 必须同一 footprint**（同 pad/dilate/close）。[ProPainter](https://arxiv.org/abs/2309.03897)。

> **关于 LaMa 「1–2px margin」**：LaMa 论文本身**没有**写死 1–2px；那是使用惯例（IOPaint/lama-cleaner 包装建议），且针对普通对象。**对文字要按笔画宽走更宽**，不要把这数字引到论文头上。[IOPaint](https://github.com/Sanster/IOPaint) · [LaMa 官方](https://github.com/saic-mdal/lama)。
> **VSR 现状**：VSR 遮罩是检测框的**实心矩形**（`create_mask` + `cv2.rectangle` + 10px pad），再按需求合并成全宽条带（`get_inpaint_area_by_mask` 连通域合并）——它**不做像素级笔画提取**，所以对「字形内鬼影」「抗锯齿边带」的处理是把整条矩形带全部补全。这在大面积字幕带上**会吃到字幕带内真实内容**（尤其当文字只占带的下部时）。VSR Issue #213（STTN 残帧）、#194（模糊）部分源于此。

---

## 6. 子问题 5：哪个现有方案最值得复用

### 6.1 VSR 的实际检测机制（源码级验证，校正原地图假设）

> 这一段是 VSR 源码（通过 GitHub API `gh api` 逐文件/逐 commit 核对）得出的**第一手事实**。**重要校正**：VSR 的检测不是「手动框 + 二值阈值 + 膨胀/腐蚀 + 逐像素 subtitle-detect 核」，而是**深度文字检测（PaddleOCR DBNet）**。

- **定位本地**：`backend/tools/subtitle_detect.py` 的 `SubtitleDetect.detect_subtitle(img)` → `paddleocr.TextDetection`（即 PP-OCRv5 `*_det`）。模型配置在 `backend/tools/model_config.py`（`PP-OCRv5_mobile_det`/`PP-OCRv5_server_det`），`backend/models/V5/ch_det/inference.yml` 确认 **`PostProcess.name: DBPostProcess, thresh:0.3, box_thresh:0.6, unclip_ratio:1.5`**（DBNet 检测器）。v1.0.0（根 commit）即已走 PaddleOCR `predict_det.py` 的 DB 路径——**从始至终是 OCR 检测**。
- **可选约束**：`detect_subtitle()` 可选地把检测结果裁剪到用户框 `self.sub_areas`（CLI `--subtitle-area-coords`），但**不是必须**；`STTN-auto`/`STTN_SKIP_DETECTION` 模式则**完全跳过检测**，直接补全整条选中带。
- **遮罩生成**：`backend/tools/inpaint_tools.py` 的 `create_mask(size, coords_list)` —— `np.zeros` + 对每个检测框 `cv2.rectangle(..., thickness=-1)` **实心白色矩形**，pad = `config.subtitleAreaDeviationPixel`（默认 10px）。然后 `get_inpaint_area_by_mask` 用 `cv2.connectedComponentsWithStats` 把矩形合并成**全宽条带**（高 `h`）并对齐补全器 `multiple`——这是**为补全器做区域合并，不是文字/背景分离**。代码里 grep 不到 `threshold/dilate/erode/medianBlur/MOG2/BackgroundSub` —— 确认无「阈值+腐蚀膨胀+逐像素核」机制。
- **时序处理**：`find_subtitle_frame_no()`（详见 §4.3）自适应采样 + 插值 + 区域一致(±20px) + `find_continuous_ranges_with_same_mask` + `scenedetect` 分镜 + `expand_frame_ranges` ±3 帧。
- **依赖/运行**：Python 3.12+；`paddleocr==3.4.0`、`opencv-python==4.11.0.86`、paddlepaddle-gpu 3.0.0 + torch 2.7.0；CUDA/CPU/DirectML/macOS。补全用 Torch（STTN/LaMa/ProPainter），OCR 检测走 PaddlePaddle。README 提供 CUDA 11.8/12.6/12.8 + Docker 镜像。
- **许可证**：**Apache-2.0**（`LICENSE` 全文确认，与 README badge 一致）——商用/二次集成友好。
- **已知局限（README + Issues）**：
  - **`STTN_SKIP_DETECTION=True` 风险**（FAQ 明示）：跳过检测会导致「该去的字幕遗漏」或「误伤无关帧」。
  - **Issue #176**：选中字幕带内的**重叠/移动屏幕文字**被误当字幕补全 → 帧间不稳定/模糊。（正是「字幕 vs 场景文字」判别缺位。）
  - **Issue #213**：STTN 模式部分帧干净部分残帧；其他补全器报错。
  - **Issue #170**：内置检测模型是**中文(ch)** 系列（`ch_det`/`ch_det_fast`），非中文脚本支持要自行调整。
  - **Issue #194**：去字幕但画质变模糊（部分源自大矩形带遮蔽）。

### 6.2 专门做字幕检测/提取的开源项目

- **`YaoFANGUK/video-subtitle-extractor`**（同为 YaoFANGUK，作者与 VSR 相同）——**深度学习字幕区域检测 + 内容提取（PaddleOCR）**，GUI、支持用户选字幕区、GPU 版。其「字幕区域检测 + PaddleOCR 提取」正是「检测」部分最贴近需求的现成实现。[GitHub](https://github.com/YaoFANGUK/video-subtitle-extractor) · [README_en](https://github.com/CuminumBeef/video-subtitle-extractor/blob/main/README_en.md) · [ROI 预设讨论 #163](https://github.com/YaoFANGUK/video-subtitle-extractor/discussions/163)。注：它有多个 fork（含 CTPN+CRNN 版 [eritpchy/video-subtitle-extractor](https://github.com/eritpchy/video-subtitle-extractor)），检测主干可选。
- **`jianchang512/pyvideotrans`** —— 最流行的开源视频翻译/配音工具，英语字幕→中文用 Whisper（语音）+ PaddleOCR（硬字幕提取/去除）。其字幕处理问题归档在 issues 里。[GitHub](https://github.com/jianchang512/pyvideotrans) · [releases](https://github.com/jianchang512/pyvideotrans/releases) · [字幕 issue #489](https://github.com/jianchang512/pyvideotrans/issues/489)
- **`SysAdminDoc/VideoSubtitleRemover`** —— STTN + LaMa + ProPainter GUI，硬字幕/文字水印去除，围绕显式 mask 阶段。[GitHub](https://github.com/SysAdminDoc/VideoSubtitleRemover)
- **`Purfview/InpaintDelogo`** —— AviSynth 的 delogo 插件，对程序化遮罩区域（底部带）做补全，ffmpeg 生态。[README](https://raw.githubusercontent.com/Purfview/InpaintDelogo/main/README.md)；配 [VideoHelp 去字幕讨论](https://forum.videohelp.com/threads/408516-Removing-subtitles)。

### 6.3 复用取舍（为什么 VSR 的检测是首选底座）

| 候选 | 检测引擎 | 遮罩方式 | 时序处理 | 许可证 | 复用价值 |
|---|---|---|---|---|---|
| **VSR（=video-subtitle-remover）** | PaddleOCR DBNet(PP-OCRv5) 自动 + 可选 ROI | 检测框实心矩形 + 连通域合并条带 | 采样+插值+分镜分组+前后扩展 | Apache-2.0 | **最高**：完整「检测+遮罩+时序」三件套现成，本地 GPU，可拆 `backend` 复用 |
| video-subtitle-extractor | 深度学习字幕检测 + PaddleOCR | 面向「提取」，不面向补全遮罩 | 有其时序 | Apache-2.0 | 高：若目标含「读字幕文本」可用；纯去字幕则 VSR 已含检测 |
| pyvideotrans | Whisper + PaddleOCR | 走去除+补全 | 有 | (含其他组件) | 中：更偏端到端翻译产品，集成面大 |
| SysAdminDoc/VideoSubtitleRemover | 同 VSR | 显式 mask 阶段 | 有 | — | 中：适合借鉴 GUI/mask 阶段 |
| InpaintDelogo | — | 程序化遮罩 | 按整带 | — | 低：仅补全，无检测 |

> **「最值得复用」结论**：**首选复用 VSR 的 `backend` 检测+遮罩管线**。理由：① 它已把「深度 DBNet 检测 + 矩形填充遮罩 + 采样/插值/分镜时序」封装成**本地、无损、Apache-2.0、可拆后端**，恰好覆盖本模块四分之三的工作；② 它是社区去字幕默认底座，既有问题（#176/#170/#213/#194）已知，可针对性规避；③ 姊妹 ticket #34（VSR 机理）与 #36（补全选型）都围绕它，复用可最大化与其它模块选型的一致性。**不建议**自研 DBNet/TransDETR 等检测器——对视频字幕无预训练优势，成本高。**自制层**专注于 VSR 没有：字幕 vs 场景文字判别 + 自适应（按笔画宽）遮罩膨胀。

---

## 7. 子问题 6：全自动 vs 半自动取舍

### 7.1 两案定义（结合本场景）

- **全自动（detect → auto-mask）**：检测器跑整片视频，自动定位字幕带、生成遮罩、补全。人只做成品抽检。
- **半自动（人工初定位 + 自动跟踪）**：用户在开头若干帧框一个字幕带（或选默认底部带），系统在该 ROI 内自动跟踪/检测变化并补全。

### 7.2 可靠性与人机成本

| 维度 | 全自动 | 半自动 |
|---|---|---|
| **误检场景文字** | 高（需额外判别层兜底，§3） | 低——只在用户 ROI 内动作，天然规避画面中间文字 |
| **字幕漏检** | 中（检测置信/淡入淡出时漏帧） | 低——ROI 把搜索空间锁死，配合时序插值覆盖淡入淡出 |
| **彩色/花字/多行字幕** | 仍需判别/检测改进 | bug ROI 内形态学+OCR 处理，更可控 |
| **人机成本** | 单次成品抽检 | 每片一次「初定位」（几秒~几十秒），批量下摊薄 |
| **批量（搬运/翻译，多片）** | 零初定位成本，但错误批量扩散 | 初定位被片子数均摊；**准确率显著高于全自动** |
| **适合场景** | 单语、规则硬字幕、可接受抽检返工 | 搬运/翻译大批量、精度优先、花字/多语言并存 |

### 7.3 证据与社区实践

- VSR 本身就是**半自动起点**：用户先手动框选字幕区（或选 STTN-auto 全带），系统做检测+补全；README 明确 SKIP_DETECTION 有遗漏/误伤风险——说明**纯全自动在现成工具里并不稳健**。[VSR README](https://github.com/YaoFANGUK/video-subtitle-remover)
- **批量短剧出海/译制工程实践中普遍采「打样 + 模板化 ROI + 人审」半自动**：先单集人工打样（含选字幕带/说话人/术语），再批量套模板，配人工审校闸口。（短剧出海工程实践，二手/社区来源，用于佐证「半自动 + 模板 + 人审」是批量场景工程主流。）[短剧漫剧批量译制工程实践](https://cloud.tencent.com.cn/developer/article/2697684?policyId=1004) · [ASR+OCR+LLM 三重校对到 95%+ 准确率](https://cloud.tencent.com.cn/developer/article/2680801) · [AI 多语字幕 3 天案例（含 LQA 人审）](https://www.welocalize.com/insights/case-study-ai-powered-multilingual-subtitling-in-3-days) · [字幕 LQA 最佳实践（审校环节）](https://elia-association.org/2025/03/ensuring-quality-in-subtitling-best-practices-for-review-and-language-quality-assurance-lqa-in-film-translation/)
- 定位准确性直接影响误伤：在底部带内把「移动屏幕文字」当字幕（VSR Issue #176）正是**必须有人为 ROI 初定位或判别层**的实证。[VSR Issue #176](https://github.com/YaoFANGUK/video-subtitle-remover/issues/176)

> **给本模块的结论**：在「精度优先、可接受慢、可批量」的搬运/翻译场景，**半自动（人工初定位 + 自动跟踪）是更可靠的默认**；全自动作为「规则硬字幕 + 源可信」的可选快速通道。二者共享同一检测/遮罩/时序内核，只是**输入判别**不同（用户 ROI vs 自动判别层）。**Auto-Dub 已有 `awaiting_review` 人审闸口（ticket #8/#9/#11）**，半自动初定位 + 人审可无缝嵌入现有 stage 流。

---

## 8. 复用/自研推荐与理由

### 推荐

> **检测与遮罩生成 = 复用 VSR 的后端（detect + create_mask + 时序分组）+ 一层薄自研（字幕/场景判别 + 自适应膨胀）。不全新自研检测器。**

### 理由

1. **四分之三的工作已由 VSR 现成封装且免费可商用（Apache-2.0）**：深度 DBNet 检测、实心框遮罩、采样/插值/分镜/前后扩展的时序一致性、本地无损编码——正是「检测 + 遮罩 + 时序」模块的主体。自研检测器（DBNet/EAST/CRAFT/TransDETR）对视频字幕**无预训练优势**（场景文字基准 ≠ 视频字幕），纯属重复造轮子。
2. **VSR 的短板正是「判别 + 精度」，恰好是本场景的成败点，做薄自研即够**：
   - **判别（字幕 vs 场景文字）**：VSR 只对选中带做遮罩，但带内重叠/移动文字会误伤（Issue #176），且只内置中文检测模型（Issue #170）。自研薄层按 §3 加「ROI 门控 + 时序投票/持久化过滤 + OCR-音频转写对齐」即可阻断。**至少先以半自动 ROI（§7）规避大部分误伤，把判别成本降到最低。**
   - **遮罩精度**：VSR 用固定 10px + 全宽矩形带，会吃到带内真实内容、留抗锯齿边带（关联 #213 残帧、#194 模糊）。自研薄层改为「按检测框尺寸自适应的 pad + 形态学 CLOSE 填孔 + 保持二值」（§5），改善大/小字幕双峰失败。
3. **与姊妹 ticket 强一致**：#34（VSR 机理）、#35（本模块）、#36（STTN/ProPainter）都围绕 VSR/ProPainter 生态，统一复用可让「自研 vs 复用边界」的 grilling（#37）有单一、可引用的底座，降低集成风险。
4. **GPU 约束支持复用而非自研**：本地显卡与 VoxCPM TTS 同机需锁互斥（`lib/gpu_lock.py`）。复用 VSR 打包好的 CUDA/DirectML/ONNX 路径 + 补全端（STTN/LaMa/ProPainter），比从零调一个检测-补全栈少了大量调试显存/时延的成本。
5. **半自动默认、全自动可选（§7）**：为「精度优先、可批量」的搬运/翻译场景，人工初定位 ROI（几秒）把误伤风险压到最低，且能挂到 Auto-Dub 已有的 `awaiting_review` 人审闸口。

### 明确不做的（Boundary）

- ❌ 不自研 DBNet/EAST/CRAFT/TextFuseNet/DETR/DINO 文字检测训练或推理栈。
- ❌ 不引入 Mask-Free 端到端方法（如 SEDiT/CLEAR/EVE 论文路线）作为**首个**版本——它们还很新、研究级、需要全量重写检测+补全；候选未来 CV 版本。
- ✅ 保留一手：把「检测 + 补全」解耦成**两个异步/分段 GPU 任务**，检测只需关键帧，补全逐窗补，节省显存并与 TTS 锁互斥调度友好（检测早跑、补全晚跑）。

### 回写地图注意事项

- 修正 `map-body.md` / 相关笔记里对 VSR 检测机制的错误假设：VSR 用的是 **PaddleOCR DBNet 自动检测 + 矩形填充遮罩 + 采样/插值时序**，而非「手动框 + 二值/腐蚀膨胀 + 逐像素核」。
- 新增「字幕 vs 场景文字判别」为**必答子问题**（VSR 未解决，见 Issue #176）——是自研薄层的核心差异化之一。

---

## 9. 来源汇总

> 主源（论文/官方文档/官方 repo/模型卡）用于事实判断；社区/二手来源明确标注、仅用于佐证采纳与工程实践。全部结论可追溯到下列 URL。

### 9.1 论文（arXiv / 官方开放获取）

- DBNet —《Real-time Scene Text Detection with Differentiable Binarization》(AAAI 2020): https://arxiv.org/abs/1911.08947
- EAST —《An Efficient and Accurate Scene Text Detector》(CVPR 2017): https://openaccess.thecvf.com/content_cvpr_2017/html/Zhou_EAST_An_Efficient_CVPR_2017_paper.html
- CRAFT —《Character Region Awareness for Text Detection》: https://arxiv.org/abs/1904.01941 · 官方: https://github.com/clovaai/CRAFT-pytorch
- TextFuseNet —《Scene Text Detection with Richer Fused Features》(IJCAI 2020): https://www.ijcai.org/Proceedings/2020/72
- TransDETR —《End-to-End Video Text Spotting with Transformer》: https://arxiv.org/abs/2203.10539 · https://github.com/weijiawu/TransDETR
- LaMa —《Resolution-robust Large Mask Inpainting with Fourier Convolutions》(WACV 2022): https://arxiv.org/pdf/2109.07161v1 · 官方: https://github.com/saic-mdal/lama
- MAT —《Mask-Aware Transformer for Large Hole Image Inpainting》(CVPR 2022): https://openaccess.thecvf.com/content/CVPR2022/papers/Li_MAT_Mask-Aware_Transformer_for_Large_Hole_Image_Inpainting_CVPR_2022_paper.pdf · https://ar5iv.labs.arxiv.org/html/2203.15270 · https://github.com/momalave/MAT
- ProPainter —《Improving Propagation and Transformer for Video Inpainting》(ICCV 2023): https://arxiv.org/abs/2309.03897 · https://www.openaccess.thecvf.com/content/ICCV2023/html/Zhou_ProPainter_Improving_Propagation_and_Transformer_for_Video_Inpainting_ICCV_2023_paper.html
- E2FGVI —《Towards An End-to-End Framework for Flow-Guided Video Inpainting》(CVPR 2022): https://github.com/bzy-ai/E2FGVI
- STTN —《Learning Joint Spatial-Temporal Transformations for Video Inpainting》(ECCV 2020): https://browse.arxiv.org/abs/2007.10247
- Deep Blind Video Decaptioning by Temporal Aggregation (CVPR 2019): https://www.openaccess.thecvf.com/content_CVPR_2019/html/Kim_Deep_Blind_Video_Decaptioning_by_Temporal_Aggregation_and_Recurrence_CVPR_2019_paper.html
- Temporal Integration for Word-Wise Caption and Scene Text Identification (ICDAR 2017): https://ieeexplore.ieee.org/abstract/document/8269996
- Sharpness/Contrast Based Word-Wise Video Type Classification (ACPR 2017): https://ieeexplore.ieee.org/document/8575807
- Detecting both superimposed and scene text in video (MTAP 2013): https://dl.acm.org/doi/10.1007/s11042-012-1201-2
- General & domain-specific techniques for superimposed text in video: https://ieeexplore.ieee.org/document/1038093
- Improving text recognition by distinguishing scene and overlay text (SPIE 2015): https://ui.adsabs.harvard.edu/abs/2015SPIE.9445E..09Q/abstract
- Overlay Text Extraction From TV News Broadcast (跟踪范式): https://ar5iv.labs.arxiv.org/html/1604.00470
- Video text tracking with transformer (Neurocomputing 2024): https://www.sciencedirect.com/science/article/abs/pii/S0925231224011913
- Video text rediscovery: predicting/tracking text across complex scenes (Wiley CIN 2025): https://onlinelibrary.wiley.com/doi/abs/10.1111/coin.12686
- Recognition of Video Text through Temporal Integration (ICDAR 2013): https://www.sciencedirect.com/science/article/abs/pii/S0925231224011913
- RoadText-Video 基准 (ICDAR21/23 视频文字跟踪/识别): https://cdn.iiit.ac.in/cdn/cvit.iiit.ac.in/images/ConferencePapers/2023/RoadText_Video.pdf
- ICDAR "Text in Videos" 评测: https://rrc.cvc.uab.es/?ch=3&com=evaluation&task=4
- STRIVE —《Scene Text Replacement in Videos》(ICCV 2021): https://openaccess.thecvf.com/content/ICCV2021/html/G_STRIVE_Scene_Text_Replacement_in_Videos_ICCV_2021_paper.html · https://github.com/striveiccv2021/STRIVE-ICCV2021
- SAMText — Scalable Mask Annotation for Video Text Spotting (2023): https://github.com/ViTAE-Transformer/SAMText
- 可见水印去除/补全家系参考（Removing Interference… Visible Watermark Removal）: https://ar5iv.labs.arxiv.org/html/2312.14383

### 9.2 官方文档 / 模型卡 / SDK

- PaddleOCR 主仓库: https://github.com/PaddlePaddle/PaddleOCR · 检测 DB 文档: https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version2.x/algorithm/text_detection/algorithm_det_db.en.md · PP-OCRv5: https://github.com/cuicong01/PaddleOCR/blob/main/docs/version3.x/algorithm/PP-OCRv5/PP-OCRv5.en.md · 模型列表(CPU/GPU): https://www.paddleocr.ai/latest/version3.x/model_list.html
- MMOCR DBNet/DBNet++: https://github.com/open-mmlab/mmocr/blob/main/configs/textdet/dbnetpp/README.md
- OpenCV Inpainting（Telea/NS，mask 语义）: https://docs.opencv.org/3.4.20/d7/d8b/group__photo__inpaint.html · OpenCV 形态学: https://docs.opencv.org/4.10.0/d4/d86/group__imgproc__filter.html
- PySceneDetect（镜头检测）: https://github.com/Breakthrough/PySceneDetect · docs: https://www.scenedetect.com/docs/head/api/detectors.html
- Final Cut Pro viewer overlays（safe-area 先验）: https://support.apple.com/en-az/guide/final-cut-pro/verded6d49d7/10.6.2/mac/11.5.1

### 9.3 VSR 及去字幕开源项目（第一手源码/readme/issues）

- **VSR（YaoFANGUK/video-subtitle-remover）**: [GitHub](https://github.com/YaoFANGUK/video-subtitle-remover) · [README_en](https://github.com/YaoFANGUK/video-subtitle-remover/blob/main/README_en.md) · 源码关键文件:
  - `backend/tools/subtitle_detect.py`（SubtitleDetect / find_subtitle_frame_no / unify_regions）: https://github.com/YaoFANGUK/video-subtitle-remover/blob/main/backend/tools/subtitle_detect.py
  - `backend/tools/inpaint_tools.py`（create_mask / get_inpaint_area_by_mask / expand_frame_ranges）: https://github.com/YaoFANGUK/video-subtitle-remover/blob/main/backend/tools/inpaint_tools.py
  - `backend/tools/ocr.py`（get_coordinates）: https://github.com/YaoFANGUK/video-subtitle-remover/blob/main/backend/tools/ocr.py
  - `backend/tools/model_config.py`（PP-OCRv5_*_det）: https://github.com/YaoFANGUK/video-subtitle-remover/blob/main/backend/tools/model_config.py
  - `backend/models/V5/ch_det/inference.yml`（DBPostProcess, thresh/box_thresh/unclip_ratio）: https://github.com/YaoFANGUK/video-subtitle-remover/blob/main/backend/models/V5/ch_det/inference.yml
  - v1.0.0 检测路径证明: https://github.com/YaoFANGUK/video-subtitle-remover/blob/1.0.0/backend/main.py · https://github.com/YaoFANGUK/video-subtitle-remover/blob/1.0.0/backend/tools/infer/predict_det.py
  - `LICENSE`（Apache-2.0）: https://github.com/YaoFANGUK/video-subtitle-remover/blob/main/LICENSE · `requirements.txt`: https://github.com/YaoFANGUK/video-subtitle-remover/blob/main/requirements.txt
  - Issues: [#176 带内移动文字误补](https://github.com/YaoFANGUK/video-subtitle-remover/issues/176) · [#213 STTN 残帧](https://github.com/YaoFANGUK/video-subtitle-remover/issues/213) · [#170 语言范围(中文模型)](https://github.com/YaoFANGUK/video-subtitle-remover/issues/170) · [#194 去完变模糊](https://github.com/YaoFANGUK/video-subtitle-remover/issues/194)
- video-subtitle-extractor（同作者，深度学习字幕检测+PaddleOCR）: https://github.com/YaoFANGUK/video-subtitle-extractor · README_en: https://github.com/CuminumBeef/video-subtitle-extractor/blob/main/README_en.md · ROI 预设讨论: https://github.com/YaoFANGUK/video-subtitle-extractor/discussions/163 · CTPN+CRNN fork: https://github.com/eritpchy/video-subtitle-extractor
- pyvideotrans: https://github.com/jianchang512/pyvideotrans · releases · 字幕 issue #489: https://github.com/jianchang512/pyvideotrans/issues/489
- SysAdminDoc/VideoSubtitleRemover（STTN+LaMa+ProPainter）: https://github.com/SysAdminDoc/VideoSubtitleRemover
- InpaintDelogo（AviSynth）: https://raw.githubusercontent.com/Purfview/InpaintDelogo/main/README.md · VideoHelp 去字幕讨论: https://forum.videohelp.com/threads/408516-Removing-subtitles
- IOPaint / lama-cleaner（LaMa 包装）: https://github.com/Sanster/IOPaint
- RapidOCR（PaddleOCR→ONNX，可作为无 PaddlePaddle 依赖的替代）: https://github.com/zhengliwen/RapidOCR

### 9.4 社区/二手（仅佐证采纳、工程实践与成本，不作为权威事实）

- VSR 多区域框选/筛选逻辑（CSDN 深潜）: https://blog.csdn.net/qq_45053161/article/details/152075362 · VSR PP-OCRv4→v5 检测升级: https://blog.csdn.net/qq_45053161/article/details/154532055
- Volcengine：E2FGVI vs ProPainter（补全端实践/显存指导）: https://developer.volcengine.com/articles/7644756006559940662
- 短剧漫剧批量译制工程实践（半自动打样+模板+人审）: https://cloud.tencent.com.cn/developer/article/2697684?policyId=1004 · ASR+OCR+LLM 三重校对 95%+: https://cloud.tencent.com.cn/developer/article/2680801
- Welocalize：AI 多语字幕 3 天案例（含人审）: https://www.welocalize.com/insights/case-study-ai-powered-multilingual-subtitling-in-3-days · ELIA 字幕 LQA 最佳实践（审校）: https://elia-association.org/2025/03/ensuring-quality-in-subtitling-best-practices-for-review-and-language-quality-assurance-lqa-in-film-translation/
- EAST quads → inpaint mask 实例（整带遮罩比逐字形稳）: https://dev.to/wladradchenko/removing-text-without-removing-the-wall-behind-it-east-quads-to-an-inpaint-mask-245n

### 9.5 已确认依赖关系 / 参考姊妹 ticket

- 探索地图: `docs/../.scratch/subtitle-inpaint/map-body.md`（记录 #33 决策与子票 #34/#35/#36/#37/#38）
- VSR 原理深潜 = 子票 #34；video inpainting 选型 = 子票 #36；UI 边界 grilling = #37
- Auto-Dub 嵌入点：`bin/auto_dub.py`、`apps/auto-dub`、人审闸口 `awaiting_review`（ticket #8/#9/#11）、`lib/gpu_lock.py` 显存互斥
