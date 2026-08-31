# 地图：参考视频 → 中文竖屏二创解说管线（ref-remake）

label: wayfinder:map
状态: complete（2026-08-26 全部工单关闭）

## Destination

一条落在 OpenMontage 的可复用管线（ref-remake / 二创解说）：输入一条 YouTube 参考视频 URL（兼容本地文件），产出 ① 中文竖屏 9:16 二创解说视频（阿黄 + V2 点缀式 + 参考图锚点 + IndexTTS 克隆配音 + HyperFrames 合成）；② 双平台成品包（抖音+小红书标题/简介/封面图）；③ 小红书图文笔记变体（抽帧+文案，轻量内置）。脚本闸门人审 + 最终质检人审，发布手动。

地图走完的标志：一个不了解这段历史的执行者，拿着产出物（管线 manifest 定案 + 各阶段 director skills + 风格 playbook + 锚点资产 + 脚本模板 + 工具补强）能直接开跑第一条二创视频，途中无需再做任何待决策。

## Notes

- 域：OpenMontage 视频生产系统。任何会话先读 `AGENT_GUIDE.md`；本上下文术语见同目录 `CONTEXT.md`；与「好奇实验室」「火柴人频道」的分界见根 `CONTEXT-MAP.md`。
- 相关 skills：`hyperframes`（合成）、`minimax-m3-vision`（视觉分析/质检）、`voxcpm-tts` / IndexTTS（配音）、`video-download` / `video-understand`（下载转录）、`ffmpeg` / `video-edit`（抽帧/测时长）、`visual-style`（风格规范）、`video-reference-analyst`（参考视频分析，AGENT_GUIDE 要求）、`agent-reach`（元数据抓取）。
- 交接基线：`openmontage_handoff_20260826.md`（2026-08-26 会话交接）——3 条已验证成片 + 全部踩坑记录；本项目把其中即兴流程固化。交接文档提及的路径均真实存在（`projects/outsmart-cn/scripts/*.py` 等模板脚本）。
- 工具现状：MiniMax image-01 支持参考图，但 `tools/graphics/minimax_image.py` 工具类**不支持**参考图参数（现用 requests 直调 API）→ 工具补强走工单；IndexTTS 类名 `IndexTTS2TTS`（不是 IndexTTSTTS）；Google Imagen 429 月度额度用尽，勿用。
- 本地 markdown tracker 约定：本目录即 tracker。map=`map.md`，工单=`tickets/*.md`，调研产物=`findings/*.md`。阻塞关系用工单元数据 `阻塞于:` 表达；认领 = 把 `指派:` 改为会话标识。引用一律用《工单名》而非编号。
- 已拍板决策（绘图会话定案，不再重开）：独立管线 ref-remake；全新独立上下文；结构借鉴+改写档位（红线 0.75/0.45）；阿黄+V2 点缀式默认 + 锚点随管线沉淀；抖音+小红书双平台 + 图文笔记（抽帧+文案轻量内置）；完整正式管线（manifest + director skills + playbook + schemas + 脚本模板 + 工具补强）；脚本闸门 + 最终质检人审；YouTube URL 为主兼容本地文件；单集为主、超长可选拆、提案人审；默认无 BGM 预留可选；手动发布 + 成品包。

## Decisions so far

- 《二创线领域定位》— 判定为第三独立业务上下文，注册进 CONTEXT-MAP.md；「原创汇编」（好奇实验室）与「结构借鉴+改写」（火柴人线）标准不混用。（绘图会话内即时决议，未开工单）
- 《管线命名》— ref-remake / 二创解说。（用户确认）
- 《输入与时长》— YouTube URL 为主、兼容本地文件；单集为主，超长（>8 分钟且内容可分）可选拆 2 集并提案人审；成片按内容定长。（用户确认）
- 《视觉系统默认》— 阿黄 + V2 点缀式；参考图锚点随管线沉淀。（用户确认）
- 《平台与发布》— 抖音+小红书双平台；图文笔记=独立干货型，生成原图+排版层文字卡片（06 定案细化）；手动发布 + 成品包，不建自动上传。（用户确认）
- 《音乐》— 默认无 BGM，预留可选接口。（用户确认）
- 《闸门》— 脚本闸门 + 最终质检人审。（用户确认）
- 《落地正式度》— 完整正式管线；MiniMaxImage 工具补强 reference_image 参数。（用户确认）
- 《管线 manifest 与阶段设计定案》— 定案八阶段：fetch → brief(含参考视频分析子阶段) → script【闸门A】→ scene_plan → assets → compose → review【人审】→ package；拆集提案入 brief 随脚本闸门一并人审；时间轴=TTS 实测段长+字数比例兜底；checkpoint 策略 guided；红线扫描入 script 产物为闸门必需附件；assets/compose 派 Compute Worker；全复用既有 schema（publish_copy/cover_manifest 执行期补 douyin 分支）。详见 `findings/01-pipeline-manifest-design.md`。
- 《二创改写红线操作定义》— 定案（四项决策全部按推荐）：以火柴人线 findings/04 为基线 + 二创微调独立成文（白名单 + 义务五项 + 禁止五条 + 0.75/0.45）；相似度扫描（轻量 n-gram 脚本 + LLM 自查）并入 01 执行期清单、不单开工单；参考视频分析只服务概念与风格、产出不进分镜；通用红线 + 双平台合规节（科普/健康措辞降级、AI 标识必填）。详见 `findings/02-adaptation-redlines.md`。
- 《MiniMaxImage 工具补强 reference_image 参数》— 完成（AFK）：工具类新增 `reference_image`/`reference_instruction` 参数（messages 参考图格式，参考图模式 prompt_optimizer 默认 OFF）；真实 API 冒烟通过（锚点→9:16 竖屏）。详见 `findings/03-minimax-tool-reference-image.md`。
- 《V2 风格规范与锚点沉淀》— 完成（AFK）：`styles/ref-remake.yaml` playbook 落盘并通过 schema 校验（V2 风格块 verbatim 为 image_prompt_prefix）；锚点沉淀至 `background_library/ref-remake/anchor/ahhuang_anchor.png`；使用规范见 `background_library/ref-remake/README.md`。详见 `findings/04-v2-style-spec-settling.md`。
- 《图文笔记双平台规格调研》— 完成（research，子代理）：抖音长图文官方口径 8000 字/30 图、普通图文第三方 35 图、首图推荐 3:4（1080×1440）；小红书标题 ≤20 字、正文常规 1000 字可超、图片常规 18 张（6-9 安全）、首图 3:4；双平台发布须勾选 AI 生成声明（《标识办法》2025-09-01 施行），未标处罚抖音最高封号/小红书限流扣流量；封面双平台共用 3:4；9:16→3:4 抽帧裁上下保留中部。部分数字标注第三方/留白（以发布页为准）。详见 `findings/05-image-note-platform-specs.md`。
- 《图文笔记文案模板》— 定案（用户确认五项，含自定义）：独立干货型定位；图片=生成原图+文字卡片（排版层叠加，6-9 张 3:4 1080×1440）；标题 ≤20 字钩子 + 正文 钩子/要点/互动引导/AI 声明（≤1000 字）；话题 主题+定位+长尾 3-6 个；正文固定 AI 声明 + 发布勾选。详见 `findings/06-image-note-copy-template.md`。

## 地图完成

**全部 6 张工单已关闭，地图走完。** 执行者可直接按以下产出物开跑第一条二创视频：

- 管线设计：`findings/01-pipeline-manifest-design.md`（八阶段 + 双闸门 + 执行期落码清单）
- 改写红线：`findings/02-adaptation-redlines.md`（0.75/0.45 + 双平台合规）
- 工具补强：`tools/graphics/minimax_image.py`（reference_image 已支持）+ `findings/03-minimax-tool-reference-image.md`
- 风格与锚点：`styles/ref-remake.yaml` + `background_library/ref-remake/`（锚点图 + 使用规范）
- 图文规格：`findings/05-image-note-platform-specs.md` + 文案模板 `findings/06-image-note-copy-template.md`
- 落地执行（本图不落码）：按 `findings/01` 第五节执行期清单推进（manifest yaml → director skills → schema 补 douyin → 脚本模板沉淀 → 相似度扫描脚本）

## Not yet specified

- 时间轴分配细则：按字数比例（已验证 3 条）vs whisper 时间戳（更准）——随《管线 manifest 与阶段设计定案》一并定。✅ 已随工单 01 定案：TTS 实测段长 + 字数比例兜底，不再用 whisper 时间戳前置。
- 角色一致性漂移兜底：锚点+强约束仍有 20-25% 漂移（实测 75-80%），漂移帧的补救策略——待锚点沉淀与首条试用反馈。
- 片头片尾与关注引导模板（双平台规格）。
- 竖屏安全区与字幕样式规范（抖音 vs 小红书差异）。
- IndexTTS 语速策略：~250 字/分偏快；按内容定长时多数不需降速，如需接近原片可 0.85 重跑。
- 超长片拆集的集间衔接（集数标识/引流）——随 manifest 定案。✅ 拆集提案已定案入 brief+闸门；集间衔接的具体格式仍待定。
- 断点续跑与失败重试：对齐仓库 checkpoint 协议的具体做法。

## Out of scope

- 自动发布（抖音/小红书）：已拍板手动发布，不建自动上传通道。
- 图文笔记不引入独立视觉设计流程：图片=复用管线生成原图 + 排版层文字卡片（06 定案），不做全新画面设计/重排版服务。
- 观点级重创作升格：稳定后另起地图。
- 批量化 / 多频道放量。
- BGM 默认环节：已拍板默认无。
