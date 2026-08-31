# setup-video 管线实战经验（LESSONS）

> 本文档沉淀 2026-08-27~28 原型→批量调试期踩过的坑与根因。**每条管线改动前必读**。
> 编号原则：按"现象 → 根因 → 修法 → 防复发"记录。

## A. 视觉模型读数（MiniMax-M3）

- **A1 [严重] `analyze_media.py` 会覆盖自定义 prompt**：`build_prompt()` 在给了 `-p` 时仍无条件追加它自带的"严格按 summary/scenes 格式输出"，两个冲突格式让模型随机二选一 → 表现为"每次跑结果都漂"。**已修复**（自定义 prompt 带 JSON 字样时不追加默认格式）。⚠️ 若再改该脚本，勿回退此逻辑。
- **A2 [严重] 320px 缩略图读不出 UI 小字**：稳定性采样用 320px 哈希帧，被顺手拿去读数 → 配置页全读空、"一个都查不到"。**修法**：段尾帧按原分辨率重抽（`scale=1280:-2`）再喂 M3。哈希仍用 320px（便宜）。
- **A3 模型格式不守约**：同一帧不同次读可能空/部分/全；`kind` 判定不可信 → **读数即分类**（能读出参数键值对的帧 = config），不依赖模型判 kind。
- **A4 类别判定**：页面归属**唯一依据 = 顶部 tab 栏选中 tab**（红框参数行只是正在调的项）；空类别页用参数名关键词反推（anti-roll→axles、spring→suspensions、rebound→dampers…），关键词必须全（"Anti-roll" 匹配不上 "axle"）。
- **A5 自动召回审计**（防漏页）：稳定帧网格图 → 1 次 M3 数"哪几秒是设置界面" → 与提取结果对账 → 缺秒自动定点补读 → 仍缺标 `ocr.needs_review`（review.html 红横幅）。误报示例：比赛成绩榜（带 tab 样式）会被当设置界面 → 人工确认后清 `needs_review`。

## B. 采样与去重（画面分析）

- **B1 定时采样（5s）会漏 1-2s 闪现页、切在转场半截** → 改**稳定段采样**：每秒 1 帧，相邻帧 8x8 哈希差异 >10 即切段，**所有段尾帧保留**（页面可能只闪现 1-2s，不能设最短停留门槛）。
- **B2 聚类/哈希去重会误并"同布局不同页面"**（EA WRC 的 UI 各页布局相似）→ 越并越少。**禁止用画面哈希做归并**；去重只按**读出的内容**：同类别+同参数名集合 = 同一配置项，**全局只留最后一次出现**（"取最后页"，300/312/322→322）。参数名会随调整变值不变名，这是"同一项"的可靠定义；不同参数名的同类别页（ALIGNMENT vs WHEELS）互不吞并。
- **B3 场景检测（scene>0.25）抓不到菜单内换 tab**（同机位低变化）→ 不用它做主采样。

## C. 素材制备

- **C1 [严重] 慢放方向**：`setpts=PTS/1.5` 是**加速**（5s→3.33s）；慢放要 `setpts=1.5*PTS`（5s→7.5s）。错了会 tpad 克隆补帧 → 首幕"停在那里等语音"。另：**源片段不足整幕时自动延长取景窗口**（`out` 后移），慢放倍率自适应 1.0-2.0，pad 只做兜底。
- **C2 徽标**：`assets/brand_logos/` 里部分品牌是**纯文字字标**（如 skoda.png=ŠKODA 字样），深色背景上几乎隐形。**硬规则：禁用字标做徽标**；映射优先 `episode.video.brand_badge` → 模板库 `<brand>_badge.*` → 模板 logos `<brand>.*` → 品牌库兜底。
- **C3 背景取景必须全程有运动**：固定取 40% 位置会踩中菜单/标题卡静止区 → 某几幕背景像图片（威尔士第二幕）。**修法**：本地运动检测（每 2s 采样 → 连续帧差异 >3% → 找 ≥成片长度 的持续运动窗口），零 API、确定性。
- **C4 BGM 第一集标准**：**纯环境声、绝无人声**。候选段提取后 **whisper 验声**（8s 切片转写非空即弃），最多试 5 段；提不出用模板引擎声兜底（`FALLBACK_BGM`）。不要图省事直接保留整段原声（会带口播/领航员声）。
- **C5 行驶主视觉（兜底顺序 2026-08-29 用户改定）**：视频可能**根本没有外部追车镜头**（菜单+主播+T恤网店+车内视角的极端案例）。外部探针（12 帧网格挑车外追车）失败时：**用户定：优先保留车内视角片段（动态优先，不要静止大图）**；静止大图 + Ken Burns 仅作最后兜底（外部、车内都没有时）。本视频内无可用外部镜头时如实上报，不硬凑。

## D. 配音与时长

- **D1 IndexTTS-2.5 实测语速 ≈5.0 字/秒**（短句；6 段 179 字 → 34.4s），比规划的 3.4 字/秒快 47%。成片时长闸 **40-67s**（原 55s 下限会误杀）。`approve-script` 预算按保守 3.4 规划（规划偏长），最终以渲染实测为准。
- **D2 情绪参数（2026-08-29 用户定改）**：~~`use_emo_text=True + emo_alpha=0.325 + seed 42 + INDEXTTS_USE_QWEN_EMO=1`~~ → **`use_emo_text=False`（固定 calm 情绪向量，emo_alpha 强制 1.0，seed 42）**。原因：auto 文本情绪让 6 段各自配腔调（钩子拖腔、讲解平、CTA 扬），用户反馈"每段语气不一样 + s1 语速慢"（s1 实测 3.94 字/s vs 基准 5）。fixed calm 实测 s1 5.94s（原 7.11s）、s6 4.31s（原 4.86s），节奏统一。统一客户端 IndexTTSSession 的 emotion="auto" 硬编码与定案不符，**走 `IndexTTS2TTS` 工具路径**。
- **D3 首段 TTS 冷启动数分钟**（模型加载），之后每段 ~10-15s；Worker 跑，勿前台。

## E. 状态机与工具

- **E1 异常崩溃会把状态卡在中间**（如 render 的 NameError 把 status 留在 qa）：`retry` 只认 failed。**教训**：stage 内所有异常路径要 `fail()` 落库；手动改库 `UPDATE videos SET status='ready_render'` 是应急手段。
- **E2 fetch 取标题被 Python 警告污染**（requests urllib3 警告进 stdout，sh 合并了 stderr）→ 取 stdout 最后一个非空行。
- **E3 GBK 控制台中文乱码**：CLI `main()` 里 `sys.stdout.reconfigure(encoding="utf-8")`；pwsh 里先 `[Console]::OutputEncoding = [Text.Encoding]::UTF8`。
- **E4 工具脚本**：`apps/setup-video/scripts/contact_sheet.py`（对照表网格对账）、`tmp/target_read.py`（定点补读任意秒）、`tmp/dense_probe.py`（密集外部视角探针）——新需求先看有没有现成工具。
- **E5 [严重] 同车同赛道两条视频 slug 碰撞**：slug=`slugify(title-track)`，两条同名视频（如 Skoda Fabia RS - GREECE ×2，503s vs 533s）会算出**完全相同的目录**。approve-script 迁移时目标目录已存在 → `shutil.move` 静默失败 → 第二条的 project_dir 仍指向第一条的目录 → 第二条 assets/render 用**第一条的 episode + 源视频**跑，**覆盖/伪造**了第一条的成片且第二条实际没被处理。**修法（2026-08-29 已改代码防复发）**：approve-script 落库逻辑已改为——当前项目完整且目标 slug 目录被占用时**保留现有 project_dir/slug，不迁移不覆盖**（冲突目录人工解析为 `-2` 后不再被冲掉）。**实测两轮复发教训**：uZKE(greece-2) 的 project_dir 被 approve-script 迁移逻辑两次指回 greece（撞 8bll），均靠 Worker/主代理发现后手工 UPDATE 修复；改码后不会再现。批量前仍建议 `SELECT slug,count(*) GROUP BY slug HAVING count>1` 排雷。
- **E6 [并发] `tmp/setup-video-queue/probe` 共享目录竞态**：`_find_exterior_span` 用固定 `tmp/setup-video-queue/probe` 存探针帧，**多个 assets 并发跑时互相删除对方 `*.jpg`**（FileNotFoundError 崩溃，DB 卡在 `assets`，需手工 reset 'ready' 重跑）。**修法**：assets 并发跑会用 DmoS 实测复现。**防复发**：探针/运动/m3 输出目录按 `video_id` 区分（`tmp/setup-video-queue/probe_<id>`），或 assets 阶段串行化（GPU 锁只锁 TTS，未锁素材提取）。

## F. 范围与决策（用户拍板，勿再翻）

- **F1 WRC 搁置，只做 ACR**（2026-08-28）：EA WRC 是另一款游戏 UI + 风景空镜风格，视觉读取不可靠。若重启 WRC：走"口播转写提数 + 人工秒标 + 定点 OCR"混合方案（存档于 map.md）。
- **F2 徽标禁字标**；**首幕不淡化、第二幕起背景压暗**；**背景=原视频连续截取成片长度**（非循环）；**BGM 去除人声**；**首幕行驶片段要外部追车视角**（无则车内视角——2026-08-29 用户定，静止大图仅最后兜底，见 C5）——以上均为用户验收标准。
- **F3 同类别配置页只留最后一张**（"取最后页"）；数值/页面归属以画面 OCR 为准，口播为意大利语且中段静音的源无口播数值可交叉。
- **F4 徽标统一按斯柯达徽章标准（2026-08-28 用户定）**：s1 车标必须是**近方形（圆形/盾形）图形徽章**，禁横向文字字标（放大到 height:210px 会超 1080 画布）。来源 `projects/setup-video-template/assets/logos/<brand>_badge.png`（512×512 透明方形），无图形徽章的品牌（如 2023 Lancia/Peugeot 官方即文字标）用 `cdn.worldvectorlogo.com/logos/<brand>-1.svg` + **node sharp** 光栅化（`sharp(buf).resize(600).png()`，Python 无 cairo 无法渲染 SVG）裁图形元素。模板徽标 img 已加 `max-height:210px;max-width:420px` 兜底防溢出。素材映射优先 `<brand>_badge`。
- **F5 v0.3 模板（2026-08-28 中改，样板=i20n-rally2-monte-carlo）**：① s1 去"调 校 方 法"大金字+三胶囊，加收益钩子大字（`video.hook`，top:1150，0.8s 弹入）；徽标/车名延后到 3.0/3.3s 出现，徽标放大 260px；② **s1-s5 全幕"片尾定格"提醒条**（`video.promise`，默认"⏳ 全参数片尾定格 · 长按保存"；s1@1500 / s2-4@1460 / s5@1340，填大图下方空区；用"片尾"不用"最后"——违禁词表"最"字面拦截）；③ 证据大图 940×680@730（CSS .evidence left:70 width:940）；④ **s6 尾垫 1.6→4.2s**（定格整幕 ~8.5s 供截图，approve-script 预算表 s6 尾垫同步 4.2）；⑤ s2-s4 入场动画收紧（evidence 0.9s 到位）。
- **F6 徽标配色分场景（2026-08-28 现代徽标案例）**：原 hyundai_badge 深蓝 H 贴深蓝椭圆 + 叠浅蓝车身 = 看不清（M3 实测 62/100）。**深色视频背景 + 可能叠浅色车身 → 必须用白/浅色版徽标**。现代版用 simple-icons 单路径剪影（`raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/hyundai.svg`）填白 + 深色描边 0.8，sharp 600px。判定流程：候选版合成到"深色帧+浅色车身帧"→ M3 对比可读性 → 选白描边版。验证显示尺寸时按实际 260px 高投放复测。

## G. v0.3 批量期新坑（2026-08-28/29）

- **G1 [严重] assets 的 TTS 缓存内容盲（2026-08-29 已代码化防复发）**：`stage_assets` 的 wav 复用只查"文件存在且时长>0.5s"，**不感知 narration 文本变化**。改口播后直接重跑 assets → tts_made=0，旧配音混进新片（本次 s1/s6 实测踩坑）。**修法（2026-08-29 内建代码）**：缓存命中 = 文件存在 + 时长>0.5s + `artifacts/tts_manifest.json` 里该段 `md5` 与当前 narration 一致 + TTS 参数签名（spk_audio_prompt/use_emo_text/emo_alpha/seed/speed）一致；不一致自动重录，**改口播/改 TTS 参数后直接重跑 assets 即可，不再靠手动删 wav**。注意：**无 tts_manifest.json 的旧项目（本批 11 条）一律视为缓存无效全量重录**（保证不混旧声；老项目本就不应重跑 assets——会覆盖专属裁剪）。定向重录单段仍可用"删对应 `assets/s{k}.wav`"触发该段重录，其余段靠指纹命中缓存不重录。
- **G2 [沙箱] GPU 锁路径被文件沙箱拦截 = filelock 静默重试死循环**：DSH 会话文件策略非 danger-full-access 时，`%LOCALAPPDATA%/openmontage/.gpu.lock` 写不进 → gpu_lock 每 0.05s 重试、打"[AutoDub] 等待 GPU 锁"心跳但锁无人持有，进程 CPU≈0 卡死（现象：10 分钟 1.5s CPU、无锁文件、无 server 进程）。**修法**：a) 重命令 Worker 直接 danger-full-access（管线既定授权）；b) 审批禁用时改用 `OPENMONTAGE_GPU_LOCK_PATH=E:\YifuAIForge\OpenMontage\tmp\setup-video-queue\.gpu.lock`（workspace 内）；c) 卡死时先 `Stop-Process` 残留 python + `UPDATE videos SET status='ready'` 复位再重跑。
- **G3 证据截图聚焦裁剪（3A，样板已用）**：ACR 调校界面全帧（2560×1440）= 顶 tab 栏 + 左右数值面板 + 中央车模（~15% 宽）+ **右侧说明栏 100% 被右缘截断**（'you ca…'/'remembe…' 等残字）+ 65% 重度模糊底图 → 观众"录屏壁纸感"。**裁剪 = 弃右栏 + 裁多余模糊底图**，分 2 组：组A 无底部面板（s2/s3/s5_1/s5_4）→ s2 `2210:1310:10:10`、s3 `2070:990:30:18`、s5_1 `2200:1100:0:0`、s5_4 `2310:1310:20:15`；组B 四角面板保全高（s4/s5_2/s5_3）→ s4 `2240:1440:0:0`、s5_2 `2490:1330:0:5`、s5_3 `2240:1440:0:0`。裁后 1.56–2.1:1 横版，模板证据卡 contain 显示。批量化建议：按"右侧竖分隔线锚点"做规则裁剪（M3 bbox 逐张太贵）。
- **G4 [严重] BGM 静音 bug（2026-08-29 修复）**：`make_bgm` 取源视频 10s 段 loudnorm 后只验"无人声"（whisper），**没验"有声音"** → 取到游戏静音段时 loudnorm 对纯静音无效 → bgm.mp3 全静音铺片（MC 实测 mean/max=-91dB，观众"没 BGM"）。**修法已内建**：候选段 ffmpeg volumedetect，`mean_volume > -40dB` 才收，5 段全静音则 fallback 公共备用引擎声（`projects/setup-video-template/assets/bgm.mp3`，-18.3dB 实测可听）。另：模板 BGM 音量 0.22（22%）偏轻是定案，用户如要音乐感需另议（acestep/music_library）。
- **G5 `video.hook` 漏填 = s1 无金句（2026-08-29 批量教训）**：v0.3 生成器按 `v.get("hook","")` 渲染 s1 金句，**空则整段跳过**（GSAP 仍引 #s1-hook 但 DOM 无节点）。原 v0.2 批量生成的 episode 全无 hook → 重出后 s1 缺金句（Wales 实测复现）。script-prompt.md 已把 hook 标为必填（"<赛段痛点解决> · <收益>"12 字内）。批量前逐条核对。
- **G6 s1 口播提速句式（2026-08-29 用户定，批量统一）**：用户反馈 s1 原钩子句（"…现代这台小钢炮又颠又推？抄这三个数。"）拖沓 + auto 情绪拖腔（3.94 字/s）。**定案句式：`<赛道痛点>别乱调，片尾全参数直接抄。`**（如"蒙特卡洛又窄又滑别乱调，片尾全参数直接抄。"，20-28 字内），配合 fixed calm 情绪（D2）→ s1 实测 5.6-5.9s。批量 8 条 s1 统一此句式（痛点从各条 badge/renhua/package.title 提炼）。
- **G7 裁剪矩形通用化（ACR 界面，Wales 复核 2026-08-29）**：同一游戏 ACR 调校界面布局一致 → **批量可直接套矩形组**（比逐条 M3 bbox 省）：A 组双面板（s2/s3）`2200:1230:0:0`；B 组四面板 s4 `2240:1430:0:0`、s5_2 `2240:1370:0:0`、s5_3 `2240:1440:0:0`；s5_1 `2200:950:0:0`、s5_4 `2250:1320:0:0`（Wales 实测，MC 同量级）。说明栏左缘锚点实测：s2≈2230/s3≈2160/s4≈2250/s5_1≈2215/s5_2≈2260-2300/s5_3≈2250/s5_4≈2330。批量后每条 M3 抽检 1-2 帧确认。
- **G8 Wales 源无外部追车（2026-08-29）**：i20-n-wales 源视频 350.1s（非 128.8s），结构=菜单(0-113s)→车内驾驶舱(146-321s)→片尾；44 采样点零外部追车。**C5 兜底顺序已由用户改为：外部追车 → 车内视角 → 静止大图**（用户明确"无外部就用车内，不用静止图"）。批量遇同情况照此执行。
- **G9 截图布局有视频级差异（2026-08-29，208 案例）**：G7 通用矩形在 Skoda/Hyundai 适用，但 **Peugeot 208 源视频带"主播摄像头 overlay"且说明栏左缘 x≈1982**（数值面板右缘 ≤1957）→ 通用右缘 2200+ 会留英文残字。208 专属矩形：7 张统一右缘 **1970**（`w` 改 1970，y/h 同 G7）。摄像头 overlay 是源素材固有（s4/s5_1-4 压在 REAR 卡右部），裁剪只能留 ~40px 薄条，数值未被遮挡，可接受；要完全无摄像头只能换帧/换素材。**批量规则：通用矩形打底 + 每条 M3 抽检 1-2 帧，发现残字/面板被裁再按该视频实测右缘微调（像素剖面定位说明栏左缘最可靠，M3 像素坐标不可靠）。**
- **G10 差速器讲解补全（2026-08-29 用户定"全量补上"）**：用户提供 ACR 差速器物理解析后核对发现——**OCR 差速器页全字段含 `Power/Coast Ramp + Preload Nm + Plates number`，但原 episode 设计只取前两者，片数漏用**（MC 前4后4、fabia 前6后8、208 前6 等）。**教训：episode 设计（script-prompt/schema）要与 OCR 全字段对齐，别只取"三招"丢参数**。补全呈现：① 卡2 标题"预载/片数 前/后"、u2="Nm · 前X后X片"；② 口诀统一"角度大=开放小=锁 · <实战句>"（角度反直觉规律放画面，不占口播预算）；③ s6 定格表差速器行加片数；④ **数据-文案一致性**：MC 口诀原"前紧后松"与数据（前 64/70 开放 + 预载前 50<后 70 → 前松后紧）方向相反——写口诀要按数据算松紧，不能套模板；⑤ **预算**：s3 口播补内容后 plan 超闸（impreza 67.8>67）→ 口播 ≤45 字，超了缩句（"前六片后五片"→"前六后五片"）。s3 口播统一句式："第二招差速器，<前P/C>，<后P/C>，预载<前后>，<片数>，<实战句>"（FWD 车只有前差）。
- **G11 [TTS] 破折号"——"会被 IndexTTS 读成"减减"杂音（2026-08-29 原理特辑实测）**：narration 里中文破折号"——"在部分位置被规范化成"减减"读出（s4 五处全中、s1/s5 读成停顿——位置相关不确定）。**修法：narration 一律不用破折号，用逗号/句号**（画面字幕可保留）。防复发：episode 落库前扫 narration 无"—"。
- **G12 [素材] BGM 必须铺满全片（2026-08-29 原理特辑实测）**：特辑复用批量项目的 bgm.mp3（~50-70s 短循环）直接铺 367s 成片 → 70s 后无 BGM，s6 定格尾垫（口播结束后）静音 → QA 静音洞。**修法（已代码化 render_explainer）**：渲染前 ffprobe bgm 时长 < 成片长度 → `-stream_loop 100 -t <total+2>` 循环扩展。批量管线（stage_assets 的 make_bgm）已按成片长度循环，不受影响。
- **G13 [TTS] whisper 会把中文数字读音转写成阿拉伯数字（2026-08-30 原理特辑 v3 实测）**：word 级高亮用 whisper 逐字时间戳对齐口播时，"四万一千二百"被转写成 `41200`、"-1.7" 等——**highlights trigger 必须用 whisper 转写形态（阿拉伯数字）**，中文读音 trigger 匹配不到会回退到估算（配合不准）。另：whisper small 对中文有错字（"参数不是抄来的"→"参数不是超来的"、"差速器"→"插速器"、繁简混杂），短语 trigger 要选转写里确认存在的短子串。
- **G14 [GSAP] fromTo 的 immediateRender 会立即应用 from 状态（2026-08-30 原理特辑 v4 实测）**：timeline 创建时 `tl.fromTo(el,{opacity:0.25},...)` 会把元素 opacity 立即设 0.25——**覆盖 CSS 初始 opacity:0**，导致"本该隐藏"的元素（如冰雪卡）一直半透明可见并与邻卡重叠。**修法：需要初始隐藏的元素不进通用高亮列表**，用专门 JS 控制（from 0）；或 from 值与 CSS 一致。
- **G15 [GSAP] boxShadow 字符串插值不可靠（2026-08-30）**：高亮用 boxShadow 光晕（'0 0 0 rgba(...)' ↔ '0 0 34px rgba(...)'）过渡时 GSAP 无法平滑插值 → 光晕残留（"幽灵高亮"）。**改用 borderColor 动画**（同结构颜色插值可靠），元素需有 border。
- **G16 [背景] 复用批量 bg_loop.mp4 会带入原视频广告/人物段（2026-08-30）**：批量 bg_loop 是"成片长度连续截取"，可能含博主广告段（T恤/人物出镜）。**修法（已代码化 regen_bg.py）**：从源视频 original.mp4 重新截取，**避开转写广告词时间窗**（merchandise/partner/patreon/discord 等）+ 抽帧验证有运动（C3）。广告窗表在 regen_bg.py 的 AD_WINDOWS。

## H. 发布文本（2026-08-29 用户定）

- **`publish.txt` = 标题 + 空行 + 简介 + 空行 + 推荐标签**（render 内建生成，读 `episode.package.tags`；抖音发布整段贴）。缺失 tags 时兜底 `["#AssettoCorsaRally", "#赛车调校", "#模拟赛车"]`。
- 标签集规范：通用 4 个（`#AssettoCorsaRally #赛车调校 #模拟赛车 #赛车游戏`）+ 品牌（#斯柯达/#标致/#蓝旗亚/#斯巴鲁/#现代）+ 赛道（#威尔士/#希腊/#蒙特卡洛/#阿尔萨斯）。
- 标题/简介仍是独立文件（title.txt/desc.txt），publish.txt 是三者合并的发布用副本。
