# OpenMontage Vox-Paper-Collage 领域上下文

本上下文记录 vox-paper-collage 管线与 made-by-ai-playbook-zh.md 优化项目中的领域术语。

## 核心概念

**Vox-Paper-Collage Pipeline**：
一条将 VOX 风格纪录片转化为纸拼贴动画视频的生产管线，由 idea、proposal、script、scene_plan、assets、edit、compose、publish 八个阶段组成。

**Made-by-AI Playbook**：
一份中文 VOX 纪录片创作提示词手册，提供脚本、插画、单图动画、多图剪辑四个 Master Prompt 的创作指南。

## 阶段（Stage）

**Stage**：
管线中一个具有明确输入产物、输出产物、审核规则和成功标准的步骤。vox-paper-collage 当前包含 8 个 stage。

**Artifact**：
Stage 产生的结构化文件，作为后续 stage 的输入。例如 brief、proposal_packet、script、scene_plan、asset_manifest、edit_decisions、render_report、publish_log。

**Checkpoint**：
Stage 结束时的 gates，决定是否允许进入下一阶段。包含 human_approval_default 和 checkpoint_required 两个控制位。

**Review Focus**：
每个 stage 中必须人工或自动检查的要点清单，用于确保产物符合创作规范。

**Success Criteria**：
Stage 产物必须满足的可验证条件，通常包含 schema-valid、字段存在、数量范围等。

## 内容规范

**Fern DNA**：
vox-paper-collage 脚本风格：连续旁白、无章节标签、无镜头指示、冷静 deadpan 男声。

**Cold Open**：
脚本开头的钩子，前 3-4 句内出现，包含精确日期、地点和一个具体小动作。

**Cliffhanger**：
脚本结尾的悬念句，英文 ≤12 词，中文 ≤15 字。

**Six-Act Structure**：
Playbook 脚本内容结构：Viral Hook → Quick Introduction → Main Story → Turning Point → Big Picture → Powerful Ending。

**Dynamic Paragraph Compression**：
根据 target_duration 将 Six-Act Structure 压缩为 3/4/5/6 段式：30s-1min 用 3 段，1-2min 用 4 段，3-5min 用 5 段，8min+ 用 6 段。

**Paragraph Label**：
Script artifact 中标记每个段落属于 Six-Act Structure 中哪一段的字段，供 scene_plan 阶段做段落级视觉切换。

**Semantic Scene**：
分镜的一级单元，对应一个 Six-Act Structure 段落，边界由语义内容决定，而非固定秒数或语音 segment。

**Semantic Beat**：
Scene 内的一个语义完整叙事单元，由 2-4 个短句或 1 个复杂句组成，时长由内容复杂度决定（简单 3-5s，标准 5-8s，复杂 8-12s，关键 reveal 可达 15s）。

**Voice-Led（Deprecated in this optimization）**：
原分镜方式，以语音 segment 边界决定 scene 时长。本次优化替换为 semantic scene/beat。

**Beat**：
Scene 内的一个叙事节奏单元。在本次优化前对应 2-3 秒旁白（约 5-8 英文词）；优化后等同于 Semantic Beat。

## 视觉结构

**Layer**：
每个 scene 的视觉分层。当前定义 4 层：L1 bg（背景纹理）、L2 hero（主体透明 cutout）、L3 elements（语音同步元素）、L4 CSS decor（CSS 装饰）。

**Element**：
Scene 中的视觉对象，绑定到具体 narration sentence，携带 semantic_family 和 data_class。

**Data Class**：
元素的数据来源分类：real_data、real_content、creative、css。

**Real Data**：
含数字/排名/行情的可查证数据元素。用真实数据源（yfinance、官方文档）生成 matplotlib 参考图，再走生图风格化。禁止 AI 编造数字。

**Real Content**：
真实人物、地点、产品等无数据实体。必须基于真实照片或用户提供图像做参考图，再走生图风格化。不允许纯生成。

**Creative**：
抽象概念/装饰元素（如神经网络、时间沙漏、印章）。纯生成，无需真实照片参考。

**CSS Decor**：
文字、胶带、图钉、印章等装饰层。CSS 只负责定位、变形、叠压和动画；具有具体材质或形状的视觉外观必须来自 SVG、透明 PNG 或提取出的视觉资产，不能用简单 CSS 线条替代。

**Visual Asset**：
具有不可替代的材质、纹理、形状或手工痕迹的可见对象，例如红绳、纸胶带、印章、手绘箭头和纸片。Visual Asset 与运动行为分离：资产提供外观，HyperFrames/CSS 提供位置和动画。

**Motion Layer**：
绑定一个或多个 Visual Asset 的可动画层，包含其初始位置、层级、遮挡关系和入场/微动行为。Motion Layer 不是视觉素材本身，也不应通过降低视觉精度来换取动画便利。

**Mega-Grid**：
将多个 L2/L3 元素合并到一张参考图中生成，再通过 PIL 裁剪和颜色阈值抠图为透明 PNG 的成本优化技术。本次优化中，real_content 和 creative 元素仍可使用 mega-grid；但 real_content 的参考图必须来自真实照片。

**Asset Production Unit（2026-08 决策，方案 3 替代原 A3）**：
assets 阶段的三层产物模式改为：多宫格参考图（成品预览确认）→ 视觉蓝图（每 beat 一张完整拼贴图，按 scene_plan box 位置驱动生成）→ 独立元素 PNG（独立文生图，非提取）。蓝图是视觉参考，不要求终帧逐像素匹配。

**Beat Full Collage / Visual Blueprint（2026-08 决策）**：
每 beat 一张完整拼贴图作为**视觉蓝图**——定义构图、风格、叠压关系，但不作为终帧锚点。生成时 prompt 按 scene_plan 每个元素的 box 描述位置，让模型按规划布局。

**Element Production（2026-08 决策，替代 B3）**：
元素**独立文生图**生成（Klein-txt2image），不再从完整图 img2img 提取（Klein 图生图"提取"不可控：楼变 4 层/线稿化）。元素描述与蓝图 prompt 逐字一致（Recurring Subject Rule）。位置在 compose 阶段按 scene_plan box 摆放。

**Box Position（2026-08 决策）**：
scene_plan 每个元素的 [left%, top%, width%, height%] 位置字段。生成蓝图时翻译为 prompt 文字描述（center-left/upper-middle/occupying 40% width），compose 时决定摆放位置。

**Box-to-Prompt Rule（2026-08 决策）**：
box → prompt 文字转换规则：left% → left edge/center-left/center/center-right/right edge；top% → top/upper-middle/center/lower-middle/bottom；width/height% → occupying about X% of frame width/height。hero 层强制 dominant。

**Entrance Rhythm（2026-08 决策 D1）**：
beat 动画节奏参数并入 scene_plan（可选字段 + 默认值）：build_on_ratio 默认 0.7、stagger_ms 默认 400、entrance_order 默认数组顺序。只有例外才显式声明。

**Entrance Order（2026-08 决策 E3）**：
入场顺序默认遵循 Playbook：bg → 几何/标题 → hero → 辅助元素 → 装饰/纹理。entrance_order 字段留给特殊情况覆盖。

**Editorial Title as CSS（2026-08 决策 F3）**：
Editorial Title 用 CSS 大字渲染（零成本、支持中文、可入场动画），蓝图里仍画标题作为视觉参考，compose 时用 CSS 重新渲染。

**Print-Grade CSS（2026-08 决策 G1-G4）**：
提升 CSS 装饰质感的四项：G1 素材库字体（Oswald/Anton/BebasNeue 英文 + 思源黑/宋 + 马善政/龙藏 国风 + IBM Plex Mono）、G2 素材库 SVG 装饰（胶带/图钉/印章框/红绳/箭头）、G3 印刷质感 CSS（多层 text-shadow 墨迹 + mix-blend-mode: multiply + 纸张颗粒 + 撕裂边缘 + 高亮）、G4 PIL 预渲染 PNG（后续增强）。

**Real Photo Cascade（2026-08 决策 C4）**：
real_content 真实照片获取的级联渠道：用户上传 → Wikimedia Commons → OpenMontage 内置搜图（image_selector: pixabay/pexels）→ Bing/Google（仅参考）→ 生图描述生成（stylized representation）。

**Missing Photo Fallback（2026-08 决策 C7）**：
找不到真实照片时，将缺失清单交给用户决策（放弃、换图或降级为 creative），不允许自行纯生成。

**Asset Library Tool（2026-08 决策 D3）**：
素材库注册为 OpenMontage 工具（`tools/asset_library.py`，capability: asset_management），提供 search/add/touch/missing 子命令。assets 阶段在 YAML 中声明为 required_tools，强制"先搜库再生成"。

**Editorial Title（2026-08 按 Playbook 强化）**：
每张 beat 完整图**必选**的 1-4 词杂志封面级大字标题（如 AGING CRISIS / GOLD / 10.5 TRILLION），融入构图，与 hero 主体叠压。不再是"仅带数字时才加"。

**Guofeng Playbook（2026-08 决策 F1）**：
国风视觉方向落地为独立 playbook YAML（`styles/vox-paper-collage-guofeng.yaml`），宣纸/水墨/朱红印章/书法体/红绳，通过 playbook.schema.json 校验。

**Locked Camera**：
动画中相机完全静止，禁止 zoom、pan、tilt、rotation、orbit 或 cut。

**Build-On**：
Animation 的第一阶段，元素按叙事顺序逐个入场，约占 segment 时长 70%。

**Living-Paper**：
Animation 的第二阶段，构图完整后仅允许极细微的微动（2-5 px、1°-2°、1%-2% 缩放），约占 segment 30%。

**Build-On State Frame**：
Build-On 过程中的一张完整构图状态帧。它保留统一的纸张、构图和视觉层级，只改变当前已出现的元素集合或元素的轻微运动状态；它不是独立元素素材，也不是最终视频帧。

**Frame Interpolation**：
在相邻状态帧之间补足中间视频帧的过程。它用于连续化已有对象的位移、旋转和微动，不负责可靠地生成新元素、恢复遮挡关系或纠正构图漂移。

**Paper-Collage Cadence**：
纸拼贴动画采用较低的动作频率来保留逐格制作感，当前倾向以 12 fps 作为创作节奏，而不是默认追求 24/30 fps 的连续运动。

**Visual Direction**：
Proposal 阶段确定的全局视觉方向，包括风格模板、色彩、字体、背景纹理、装饰体系。默认按 niche 自动推荐（如 crime/disaster 用旧报纸档案，technology 用蓝图/工程图纸，history 用羊皮纸/手绘，money 用账本/股票票据，space 用星图/工程图纸）。同时 proposal 阶段列出可选风格集合（旧报纸、国风、蓝图、羊皮纸、现代杂志等），用户可提供参考图或详细描述 override 默认推荐。

**Guofeng Style**：
国风/中国风格视觉方案，可选风格之一。包含宣纸、线装书、朱红印章、毛笔字、水墨纹理等元素。适用于中文历史/文化/艺术题材或用户主动选择。不默认按 narration_language 触发。

## 工具与产物

**TTS Selector**：
选择并调用 TTS provider 生成语音的工具抽象。

**Image Selector**：
选择并调用图像生成 provider 的工具抽象。

**Asset Manifest**：
assets 阶段产物，记录所有生成素材、来源、层信息、数据溯源和 provenance。本次优化后需包含 beat 完整图 + 独立元素 + 多宫格参考图 + 缺失照片清单的完整记录。

**Missing Photo List（2026-08 决策 C7）**：
assets 阶段收集的无法找到真实照片的 real_content 元素清单，最终统一提交用户决策。它是 asset_manifest 的一部分。

**Render Report**：
compose 阶段产物，包含输出文件、ffprobe 验证结果、self-review 质量笔记。

**Publish Log**：
publish 阶段产物，包含 3 张缩略图和最终导出包。

**Artifact Schema**：
定义产物 JSON 结构的 schema 文件，位于 `schemas/artifacts/` 目录。

**Sample Artifact**：
用于阶段验证的示例产物实例，证明该阶段的 skill/schema/工具链能产出合格输出。

**Global Asset Library**：
跨项目共享的本地素材库，位于 `assets/shared_library/`（被 `.gitignore` 排除）。包含外部来源的图片、音频、字体、视频片段。每个素材配 `.meta.json` 索引。

**External Asset Archiving Rule**：
仅归档外部来源素材（用户上传、互联网搜索、购买/授权）到 Global Asset Library；AI 生成内容不归档。

**Asset Meta JSON**：
每个素材的索引文件，记录路径、类型、标签、来源、描述、使用次数、版权信息。

## 分层动画探索（2026-08 实测结论）

**Element Layering（2026-08 实测）**：
从 AI 生成整图拆出"干净独立元素图层"的结论：分层准确度约 70% 取决于**蓝图生成时的分层友好设计**，工具（Qwen-Image-Layered）只是放大器。同色系暖色叠压（金色 STUCK / 褐色沙岸 / 米色纸）必然分层失败；纯黑/纯红/纯白/深褐/米色五色域分离的蓝图分层明显更好。

**Layer-Friendly Blueprint（2026-08 决策草案）**：
生成蓝图前必须遵守：① 每个元素占独立色域（黑字/深黑船/亮红集装箱/纯白便签/褐沙岸/米纸），禁止同暖色叠压；② 撕裂边缘清晰、遮挡关系简单；③ 背景提供质感但不干扰元素色相（旧报纸纹理优于纯米纸）；④ 主画面显著元素 ≤ 4-5 个（匹配 Qwen-Layered 层数上限）；⑤ 生成 prompt 禁用 `muted colors` / `no oversaturated colors` 等压制分离度的词。尚未固化到 assets-director.md。

**Qwen-Image-Layered（2026-08 实测）**：
阿里巴巴开源模型，可将图像分解为多个 RGBA 透明图层。本机 ComfyUI 可用（`qwen_image_layered_int8_convrot.safetensors` + `EmptyQwenImageLayeredLatentImage` 节点 + Lightning LoRA 加速）。单次层数上限 5（int8 量化 + 8 步 Lightning = 快但分层粗；官方 50 步全精度 = 准但太慢不可用）。官方确认：**提示词只描述整体内容，不能逐层控制**；应写完整场景叙事并明确描述被遮挡元素（如被船挡住的 STUCK）。混合层可用"迭代分层"（把输出层再喂回模型）继续拆。

**分层提示词写法（2026-08 实测）**：
不是写"第 1 层是什么、第 2 层是什么"，而是写**一张包含所有被遮挡元素的完整场景叙事**（例："...船身后面是纯黑大字 STUCK，部分被船身遮挡，被遮挡的字母属于文字层..."）。官方 README 明确 prompt 不能显式控制每层语义。

**已生成的分层友好蓝图（2026-08）**：
`b1.6_choked.png`（报纸背景 + 纯黑 STUCK + 深黑船 + 亮红集装箱 + 船堵死海峡叙事）分层效果明显优于 b1.1；`b1.7_layerfriendly.png`（b1.1 构图 + 五色域分离）。均位于 `projects/ever-given-suez/assets/blueprints/`。

## 优化治理

**Optimization Charter**：
本优化项目的宣言文档，明确目标、原则、阶段顺序、验证方式和退出条件。

**Human Approval Gate**：
阶段产物通过人工审查后才能进入下一阶段的 checkpoint。由用户或其他指定审批者执行。

**Playbook Alignment Gap**：
Playbook 与 Pipeline 之间的差异点。例如选题数量、脚本结构、分镜粒度、动画节奏等。

**Platform-Driven Title Style**：
Idea 阶段标题风格由 target_platform 决定：YouTube/TikTok/Bilibili 偏好奇心爆款；LinkedIn/企业宣传偏克制纪录片。

**Platform-Driven Duration Recommendation**：
Proposal 阶段时长由 target_platform 推荐，但用户可 override。

**Published Idea Blacklist**：
已发布选题的黑名单，防止重复选题。只有进入 publish 阶段的选题才会进入黑名单。

**Budget Formula Removal**：
本次优化中删除 proposal 阶段的预算公式，前期不做预算控制。cost_estimate 可保留为可选占位字段。

**Default Narration Language**：
本次优化中默认旁白语言从英文改为中文（zh）。

---

# Auto-Dub 领域上下文

本上下文记录 Auto-Dub 流水线（YouTube 英文视频 → 中文配音）中「分句」与「逐句时长对齐」领域的术语。

## 分句与对齐

**Auto-Dub Pipeline**：
批量搬运英文 YouTube 视频并产出中文配音版的流水线。阶段链路：转录 → 翻译 → TTS 合成 → 混音 → 压制，每个原句一条字幕、一段可感知的语音。

**Segment（转录段）**：
Whisper 转录的原始输出单元，按句末标点与静音切分。它是合并前的原子单元，不直接作为字幕或对齐单位。

**Utterance（原句）**：
转录后把 Whisper Segment 按规则合并得到的英文完整句，是字幕与时长对齐的**锚点单位**。合并规则：句末标点（`. ! ?`）+ 相邻段时间间隙 < 0.5s + 单句上限 15s（超长单句不硬并）。一段 Utterance = N 个合成子块 = 1 条字幕。

**Sentence Clutter（碎句）**：
原句被拆成多条过短字幕（单条 < 2s）的现象。成因包括 Whisper 分段过细与翻译后按中文标点二次拆分，是本次优化要消除的目标。

**Chunk（合成子块）**：
Utterance 内按中文标点切出的 TTS 合成单元，一个 Chunk 一个 WAV。Chunk 是对齐与变速的操作单位，不直接对应字幕条。

**Per-Utterance Alignment（逐句对齐）**：
以变速使中文音频时长贴合原句时长的机制。闭环：合成 → 实测时长 → 逐句变速 → 校验。TTS 引擎无语速参数，合成时长不可预测，故只能事后测量再变速。

**Tempo Budget（变速预算）**：
逐句 atempo 允许的变速上限，±5%。超限的句子不强行变速，回退为 LLM 重翻改写译文长度。

**Alignment Tolerance（对齐容差）**：
逐句时长允许的偏差范围，±15%。验收标准：新处理视频逐句达标率 ≥ 95%，单句最长偏差 < 0.5s。

**Retranslation（重翻）**：
变速不可达（超 Tempo Budget）时由 LLM 改写译文长度以进入可变速范围的手段。重翻只调整译文文本，不改变原句/子块结构。

**Merge Gap（合并间隙阈值）**：
Whisper Segment 合并且为 Utterance 时的最大时间间隙，0.5s。

**Queue Gap（排队间隔）**：
混音串行排队在相邻音频间的硬间隔，100ms。逐句对齐时从变速目标时长中扣除，避免句尾贴合时间隔累积成漂移。

**Drift（漂移）**：
配音总时长相对原视频时长的偏差。分为整体漂移（现状已由字数预算 + 全局 atempo + 缩短重翻控制）与逐句漂移（本次优化的目标）。

**Inherently-Long Sentence（物理不可达句）**：
原句本身过短（访谈回应词等 < 1s），中文朗读时长物理上不可能贴合原句、变速与重翻均不可达的句子。标记为 `inherently_long`，允许超对齐容差，验收达标率统计时排除，避免浪费变速/重翻算力。

## 多人说话人与音色

**Speaker Cluster（说话人簇）**：
pyannote 说话人分离输出的标签（SPEAKER_00/01/…）。在重叠访谈上，pyannote 常把一个真实说话人分裂成多个 cluster（3 人 → 4 cluster），是音色错配的根因。

**Cluster Merge（簇合并）**：
对每个 cluster 的 voice_ref 提 speaker embedding，余弦相似度 ≥ 0.7 时合并为同一说话人。**必须用拼接后的 voice_ref 提 embedding**（可靠），原始波形切片不准。

**Word-Level Speaker Split（词级说话人切分）**：
同一 Whisper segment 内跨说话人的句子，按每个 word 的时间中点归属 speaker_turn，在说话人切换处切分子段。pyannote 不产生边界的极短插话仍切不开（模型边界）。

**Voice Ref（声纹参考）**：
克隆某说话人音色用的参考音频。当前做法：多段择优拼接至 ~30s（甜点段 1.5-12s 优先），供 IndexTTS2 克隆。同一真实说话人必须只有一个 voice_ref（经 Cluster Merge）。

**Speaker Review Gate（说话人审校闸门）**：
多人（≥2 说话人）流程中，转录后生成审校文档（音色数量 + 每音色说的话），人工确认/修正后才继续翻译。单人默认自动通过（可配置强制）。这是多人访谈全自动完成率差的解决方案（见 wayfinder map）。

**Translation Review Gate（翻译审校闸门）**：
翻译后生成全量中英对照审校文档，人工修改后才进入合成。与说话人审校闸门配套。

## 变速与预算（2026-08-09 修订）

**Tempo Budget（变速预算）**：
逐句 atempo 允许的变速上限，默认 ±5%。**听感已验证的上限**；代码中 `clamp_tempo_factor` 支持 `max_ratio=1.15`（来自 tachidubb），但 **15% 变速的中文听感未真机验证，默认不应触发**——变速必须保听感，变怪宁可溢出推挤或缩短译文。

**Budget CPS（预算语速）**：
翻译字数预算用的 cps = 实测 cps × `cps_safety_factor`(0.7)。因为 IndexTTS2 短句真实 cps（3.1-4.2）远低于长文本校准值（~5.8），固定下限 15 字会让短句译文过长。

**Global Tempo（全局调速）**：
末段兜底手段。漂移 > drift_budget(1.5s) 且 ≤ max_drift 才触发整段 atempo；漂移在预算内由逐句对齐 + 溢出推挤吸收。
