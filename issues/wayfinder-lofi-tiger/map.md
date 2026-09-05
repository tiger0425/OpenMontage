# 地图：YouTube lofi 小老虎音乐频道流水线（lofi-tiger）

label: wayfinder:map
状态: complete（2026-09-03 全部 8 张工单关闭，首条试点成片与全套资产交付）

## Destination

一条落在 OpenMontage 的可复用流水线（暂名 lofi-tiger / `bin/lofi_tiger.py`）：输入场景与氛围主题（如 "rainy night study with cozy tea"），产出：
1. **英文 YouTube 开号与品牌资产包**：10 组频道名候选与定位、Logo 生图 prompt、Banner 生图 prompt、英文 SEO 简介与长尾关键词标签池（源自 Capybara Prompt Kit 的小老虎完整移植）；
2. **1-3 小时 lofi 音乐与氛围横屏长视频（16:9）**：AI 原创 lofi 音乐无缝循环 + 环境白噪音（雨声/壁炉等）+ chibi 小老虎与伴侣场景的平滑微动循环（呼吸、眨眼、雨丝热气）；
3. **可验收试点视频包**：1 条完整试点视频（含封面、标题、简介、标签），用于音画质检与手动发布验收。

地图走完的标志：一个不了解这段历史的执行者，拿着产出物（管线 manifest 设计定案 + 小老虎角色圣经 + 音乐与音频长循环方案 + 视觉微动方案 + 试点成片验收标准）能直接开跑第一条试点视频，途中无需再做任何待决策。

## Notes

- 域：OpenMontage 视频生产系统。任何会话先读 `AGENT_GUIDE.md`；本上下文术语见同目录 `CONTEXT.md`；与「好奇实验室」「火柴人频道」「二创解说」的分界见根 `CONTEXT-MAP.md`。
- 相关 skills：`acestep`、`music`、`sound-effects`、`ffmpeg`、`hyperframes`、`character-animation`、`visual-style`、`youtube-upload`。
- 工具现状基线：
  - 音频：`minimax_music`（music-2.6）已配置并可用（0.01 美元/次，30s/60s/120s 槽位）；`freesound_music`、`pixabay_music` 可用于氛围白噪音检索；`audio_mixer` 可用。
  - 生图：`minimax_image`（image-01，支持 seed 与参考图）已配置并可用；`google_imagen` 429 额度已尽。
  - 合成引擎：FFmpeg 可用；HyperFrames（Node >= 22）可用；Remotion 未安装。
  - 视频生成：`minimax_video_direct`（图生视频）已配置可用。
- 内容方法论输入：用户的 Google Doc《CHILL LOFI CAPYBARA MUSIC STUDY — PROMPT KIT》（仓库外）。其 6 大核心模块（命名、Logo、Banner、SEO、内容组合、生图/动效模板）完整继承，角色由水豚替换为 chibi 小老虎。
- 本地 markdown tracker 约定：本目录即 tracker。map=`map.md`，工单=`tickets/*.md`，调研产物=`findings/*.md`。阻塞关系用工单元数据 `阻塞于:` 表达；认领 = 把 `指派:` 改为会话标识。引用一律用《工单名》而非编号。
- 已拍板决策（交接会话已定案，不再重开）：
  - 独立管线 lofi-tiger；
  - 独立业务上下文（第四上下文）；
  - 照搬 Capybara 文档的 lofi 音乐频道形态；
  - 完整 Prompt Kit 全都要（命名/logo/banner/SEO/模板）；
  - 接入仓库自动化流水线（bin/ 脚本）；
  - 100% 全原创 AI 生成（AI 音乐 + AI 动画 + AI 背景），不做搬运；
  - 仅 YouTube 横屏（16:9），英文 SEO；
  - 完整小老虎角色圣经；
  - 首波先做 1 条试点跑通，再接完整管线；
  - 技术栈先调研仓库现成能力再定。

## Decisions so far

- 《lofi 小老虎频道与既有领域模型的关系》— 判定为第四独立业务上下文，在 CONTEXT-MAP.md 中分域注册，独立运作。（交接会话决议，已登记）
- 《平台、画幅与语言规范》— 确定为 YouTube 独占平台、16:9 横屏 1080p、全英文 SEO 体系。（交接会话定案）
- 《内容原创性与版权基线》— 全链路原创 AI 生成，无侵权/搬运风险，无二创改写红线限制。（交接会话定案）
- 《首波推进策略》— 先产出 1 条可验收试点视频 + 成套品牌资产，人审定案后再建完整流水线。（交接会话定案）
- 《本机与云端能力摸底与长循环技术预研》— 完成摸底：MiniMax Music (30/60/120s $0.01) + Freesound 氛围混音 + acrossfade 算法消除接缝，推荐 3 首 120s 乐段 Mini-EP 轮播机制；视觉锁定 MiniMax Image 16:9 治愈系 + MiniMax Video Direct 中段交叉淡化（Mid-Crossfade Loop）生成 100% 无缝微动母本；长视频（1-3h）采用 FFmpeg `-stream_loop -1 -c:v copy` 极速流式混流架构，1 小时视频秒级完成交付，规避逐帧渲染性能死结。详见 `findings/01-repo-capabilities.md`。
- 《小老虎角色圣经原型》— 定案：主角锁定为 chibi 幼态小老虎 Tora（大圆头/2.5~3 头身/暖蜜色 `#F5A642`+奶白 `#FFF6E5`+柔巧克力棕纹 `#5C3A21`，严禁纯黑猛兽条纹）；标配燕麦绿大卫衣+复古大耳机；5 大迷你伴侣池（山雀 Pip/树蛙 Mochi/仓鼠 Kuri/白猫 Bao/垂耳兔 Sprout）；5 大经典雨夜/木屋/咖啡馆场景（16:9 黄金分割偏侧构图）；呼吸/眨眼/耳尖抖动分级微动与跨模型正负向 Prompt 锁定契约就绪。详见 `prototypes/character-bible.md` 与 `findings/02-character-bible.md`。
- 《Prompt Kit 迁移与小老虎品牌资产》— 定案：频道名锁定为 `Tiger & Tea`，并建立「四重立体补偿系统」（频道展示名 `Tiger & Tea | Cozy Lo-Fi & Rain Ambience`、单集标题双核公式、封面 1 HOUR LO-FI 视效角标、三级 SEO 标签池）；产出 1:1 Logo 与 2560x1440 Banner 生图 Prompt 模板（安全区适配）；5×5×5=125 种内容组合生成矩阵与一键拼装模板。详见 `findings/03-prompt-kit-brand-assets.md`。
- 《lofi 音乐与环境白噪音长时无缝循环技术方案》— 实测定案：发现 MiniMax Music 停运新 API 事实，架构解耦为本地精品库+算法粉红噪音雨声（免 key 高稳定）；验证自回环交叉淡化算法（Self-Crossfade Loop），93.5s 乐段首尾 3s acrossfade 消除接缝爆音；72% 音乐 + 28% 雨声双轨混音并标准化至 YouTube -14 LUFS；15 分钟长音轨流式拼接实测仅耗时 0.324 秒。详见 `findings/04-audio-loop-ambience.md`。
- 《视觉微动母本方案选型与技术预研》— 实测定案：生成首张 16:9 绝美主视觉母图（`tora_study_master.png`）；MiniMax Video Direct 图生 6s 微动视频；独创中段交叉淡化（Mid-Crossfade Loop）算法（1.75 秒完成处理），将 6s 视频对半调换叠化，实现 100% 绝对平滑闭环微动母本（`tora_seamless_5s.mp4`），彻底杜绝跳帧抽搐。详见 `findings/05-visual-micro-loop.md`。
- 《1-3 小时长视频极速混流架构》— 实测定案：确立「短微动母本 + 长音轨 + FFmpeg -stream_loop -1 -c:v copy」解耦流式混流架构；首条 15 分钟长视频（`tiger_tea_pilot_15min.mp4`，159.25 MB）**实测混流合成仅耗时 0.59 秒**！推导 1 小时视频仅需约 2.4 秒，彻底破除逐帧渲染性能死结。详见 `findings/06-stream-loop-architecture.md`。

- 《管线 manifest 与 CLI 阶段设计》— 定案：确立六阶段标准架构（brand-kit -> scene-spec -> audio-prep【闸门A】 -> visual-prep【闸门B】 -> stream-compose【Worker】 -> package）；轻重分离与 Log Barrier 保护；沉淀 `bin/lofi_tiger.py` 命令集规范。详见 `findings/07-pipeline-manifest-design.md`。
- 《试点视频验收标准与首条样片交付》— 定案：首条 15 分钟全规格成片（`tiger_tea_pilot_15min.mp4`，15.10 min，159.25 MB，-14.0 LUFS）实测质检全部达标通过；配套双核 SEO 标题与分章节简介就绪。详见 `findings/08-pilot-acceptance.md`。

## 地图完成

**全部 8 张工单已全部关闭，地图圆满走完。** 执行者可直接基于以下落地成果开跑并放量：

- **品牌资产与 Prompt Kit**：`findings/03-prompt-kit-brand-assets.md`（锁定 `Tiger & Tea` 专属品牌包、Logo/Banner 模板、SEO 词库、125 种组合矩阵）
- **角色圣经原型**：`prototypes/character-bible.md` + `findings/02-character-bible.md`（Tora 3 头身 Chibi、配色契约、伴侣池、场景库与 Prompt 锚点）
- **核心主视觉母图**：`projects/lofi-tiger-pilot/assets/images/tora_study_master.png`（超高清 16:9 吉卜力治愈风）
- **闭环微动母本**：`projects/lofi-tiger-pilot/assets/video/tora_seamless_5s.mp4`（Mid-Crossfade 100% 绝对无缝闭环视频母本）
- **音频循环引擎**：`projects/lofi-tiger-pilot/scripts/test_audio_loop.py` + `findings/04-audio-loop-ambience.md`（自回环消除爆音，雨声混音，-14 LUFS，15min 仅需 0.32s）
- **极速混流引擎**：`projects/lofi-tiger-pilot/scripts/test_video_loop.py` + `findings/06-stream-loop-architecture.md`（15 分钟视频 0.59s 极速交付，1 小时仅需 2.4s）
- **首条 15 分钟试点成片**：`projects/lofi-tiger-pilot/renders/tiger_tea_pilot_15min.mp4`（15.10 min，音画合规）
- **管线架构规范**：`findings/07-pipeline-manifest-design.md`（六阶段、双闸门、轻重分离 CLI 规范）

## Not yet specified

无。全部关键决策与技术路径均已通过真实实测闭环，无任何待决策悬空项。


## Out of scope

- 竖屏短视频（抖音/TikTok/小红书）：用户明确仅 YouTube 横屏 16:9。
- 中文配音与解说字幕：lofi 音乐频道纯纯器乐背景音 + 环境声 + 视觉陪伴，无口播与解说。
- 试点阶段自动发布：试点期采用手动上传 YouTube，稳定后再评估接入自动通道。
- 复杂故事情节或多机位叙事：定位为常驻背景音视频，画面严格保持稳定微动，不做多机位剧情剪辑。
