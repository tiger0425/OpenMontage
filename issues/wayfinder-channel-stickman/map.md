# 地图：YouTube 频道 → 中文火柴人短视频流水线

label: wayfinder:map

## Destination

一条落在 OpenMontage 的可复用流水线（暂名 channel-stickman）：输入一个 YouTube 频道 URL，产出 ① 中文新账号资产包（简介 / logo / banner / 抖音+小红书两套 SEO 标签）；② 3-5 条试点中文火柴人解说短视频——SVG 角色动作 + AI 无字背景，单集约 2 分钟，超长原片按内容拆多集，自动叠加「AI 生成」标识。脚本闸门人审，手动发布。

地图走完的标志：一个不了解这段历史的执行者，拿着产出物（管线设计定案 + 角色圣经 + 各项规则）能直接开跑第一条试点视频，途中无需再做任何待决策。

## Notes

- 域：OpenMontage 视频生产系统。任何会话先读 `AGENT_GUIDE.md`；本上下文术语见同目录 `CONTEXT.md`；与「好奇实验室」上下文的分界见根 `CONTEXT-MAP.md`。
- 相关 skills：`auto-dub`（下载/转录/混音参考）、`character-animation`（SVG rig 与动作库）、`animation`（管线模式参照）、`video-download`、`voxcpm-tts`。
- 生图路线（绘图会话后拍板）：minimax_image（image-01，原生 aspect_ratio/seed）为主、google_imagen 为备的双路；「gemini flow」澄清为继续使用 Gemini 生图。MINIMAX_API_KEY 已配置并冒烟通过。
- 内容方法论输入：用户的 Google Doc 火柴人 prompt 工具包（仓库外）。其角色一致性纪律必须继承，技术实现以本仓库工具为准。
- 本地 markdown tracker 约定：本目录即 tracker。map=`map.md`，工单=`tickets/*.md`，调研产物=`findings/*.md`。阻塞关系用工单元数据 `阻塞于:` 表达；认领 = 把 `指派:` 改为会话标识。引用一律用《工单名》而非编号。
- 已拍板决策（绘图会话定案，不再重开）：新建独立管线；前期「结构借鉴+改写」档位；抖音为主兼容小红书；按内容拆集每集约 2 分钟；SVG rig 做角色动画、AI 生图只做背景与品牌物料；全新原创形象；内置 AI 标识；无字底稿+后期叠字；脚本闸门人审+手动发布；先 3-5 条试点；独立上下文（不动「好奇实验室」术语）。

## Decisions so far

- 《火柴人频道与既有领域模型的关系》— 判定为独立业务上下文，新建 CONTEXT-MAP.md 分域，「原创汇编」标准不适用本线。（绘图会话内即时决议，未开工单）
- 《BGM 来源盘点》— 库存仅 ep01_bgm.mp3（93.5s 需循环）；推荐库存复用 > 配 key 生成 > 无声；基调三方向：温暖钢琴弦乐 / 极简 ambient / 轻快 pluck。详见工单决议与 findings/10-bgm-sources.md。
- 《imagen 无字底稿模板调研》— google_imagen 实为 Gemini Flash 图像、参数被忽略、无 seed；竖屏与一致性靠模板补齐，三套无字底稿模板 + 11 项验证清单就绪（findings/05-imagen-template.md）。
- 《生图双路决策》— minimax_image 为主、google_imagen 为备。（绘图会话内即时决议）
- 《配置 MINIMAX_API_KEY 并验证生图》— key 入 .env（不入库），四件套解锁（image 3/11、music 1/3、tts 5/8、video 2/18），image-01 竖屏冒烟通过。
- 《SVG 火柴人角色圣经原型》— 人审定案：3 头身/7px 黑线/白头+思考橙；表情库 7 + 动作 clip 映射 9；**肢体动作走 ink-theater InkPuppet 真实动捕（CMU 12 clips），表情层保留 SVG RIG，禁止手调 transform**。圣经文档 `prototypes/character-bible.md`。
- 《分集切分规则细则》— 定案（用户确认两 ⚖ 项）：LLM 切点提案 + `split_review.md` 人审两段式；单集目标 90–170s；拆后 <60s 并回相邻集；标题 `{钩子}｜第N集`。详见 `findings/03-episode-splitting.md`。
- 《「结构借鉴+改写」红线操作定义》— 定案（阈值经确认：单句 ≥0.75 红、整篇 ≥0.45 黄）：白名单（观点/骨架/案例主题）+ 改写义务五项 + 红线五条禁止；相似度自动扫描与三查抽查挂载脚本闸门。详见 `findings/04-adaptation-redlines.md`。
- 《管线 manifest 与阶段设计》— 定案：七阶段 ingest → brand-kit(一次性人审) → select-split【闸门A】→ script【闸门B·红线0.75/0.45】→ assets → compose → package；三处人审、发布手动；TTS=tts_selector 本地 GPU 主、生图 minimax 主/imagen 备、动画 InkPuppet 动捕；轻 1–4 / 重 5–7 派 Worker。详见 `findings/06-pipeline-manifest-design.md`。
- 《账号定位与频道名候选》— 定案：源频道 @PeleExplainss（12.4w 订阅，人体冷知识/死亡警示/脑科学混合）；定位轴=**生活冷知识**（规避医疗监管）；火柴人角色名=**柴米 ChaiMi**；账号名=**柴米说**；标题格式 `柴米：{钩子}｜第N集`；选题配比 60/25/15；片尾合规免责行。详见 `findings/07-account-positioning.md`。
- 《TTS 音色选型样音》— 定案（用户听选④）：音色=`D:/index-tts/my_voice.wav`，IndexTTS2.5 纯净克隆（use_emo_text=false）seed 42，tts_selector 路由，跨集不混音色。详见 `findings/09-tts-voice.md`。
- 《minimax 生图适配》— 定案：场景背景**按内容逐场景生成**（非模板），布局契约=柴米 620px 中左偏中/对象中上偏右/字幕底部（`prototypes/layout-diagram.html`）；背景 prompt 禁用 empty/plain 词（实测近白图）；minimax 主路线验证通过（preferred_provider=minimax，seed 有效），imagen 备 429 额度耗尽待用户提额。详见 `findings/12-scene-backgrounds.md`。

## Not yet specified

- 单集动效语言细化：呼吸感微动 vs 局部肢体动作的幅度边界——待《SVG 火柴人角色圣经原型》定案后才能表述清楚。
- AI 背景 + SVG 角色的合成方式：矢量直叠还是渲染合成；帧率/分辨率规范——依赖角色圣经与 imagen 模板两项产出。
- 字幕样式与烧录规范：字体、位置、安全区，抖音与小红书的规格差异。
- 片头片尾与关注引导模板。
- 手动发布操作手册：双平台上传步骤、标签填写、声明勾选清单。
- 小红书是否需要额外的图文笔记形态。
- 断点续跑与失败重试策略：对齐仓库 checkpoint 协议的具体做法。
- SVG 动效不够看时的升级走廊：MINIMAX key 已顺带解锁 minimax_video_direct（图生视频），若试点期判定伪动效不足可评估启用——与已拍板的 SVG 主路线不冲突，属备选。

## Out of scope

- 「观点级重创作」升格：用户明确等试点稳定后再启动，届时另起一张地图。
- 批量化 / 多频道放量：试点通过后才考虑。
- 自动发布到抖音/小红书：已拍板手动发布，不建自动上传通道。
