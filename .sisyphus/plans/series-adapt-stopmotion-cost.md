# series-adapt 逐帧生成单集成本模型

## 一句话结论

在已确定的本地 `comfyui_image` + Klein workflow 主路径下，现状每 beat 1 图与逐帧每 beat 2/3/4 图的**现金 API 图像成本均为 0 美元**；逐帧方案的真实增量转移为 GPU 时间、模型下载、硬件折旧和 QA 时间，而这些资源没有仓库可核验的现金单价。直接视频只能写成 `B × P_clip` 的云端上限锚点，当前不能给出可信美元数。

## 单集结构/beat 推算

### 已确定的单集参数

| 参数 | 仓库依据 | 取值/解释 |
|---|---|---|
| 单集目标时长 | `apps/series-adapt/config.yaml:16-18` | 600 秒，10 分钟 |
| 配置展示语速 | `apps/series-adapt/config.yaml:18` | 150 WPM，仅是配置值 |
| 实测语速 | `apps/series-adapt/config.yaml:25` | 2.98 words/s，即约 178.8 WPM |
| 改写阶段实际依据 | `skills/pipelines/series-adapt/rewrite-director.md:21-31` | 优先使用 `measured_wps`，不是固定 150 WPM |
| 总词数预算 | `rewrite-director.md:28` | `round(duration_seconds × measured_wps × 1.05)`；本集约 `round(600 × 2.98 × 1.05) = 1,877` 词 |
| 视觉事件节奏 | `skills/pipelines/series-adapt/references/vox-story-library.md:62-76`；`scene-director.md:117-124` | 每 4–7 秒一个视觉事件；每 60–90 秒一个小节拍点；每集一个高光节拍 |
| 长场景拆分 | `scene-director.md:121-124` | 超过 12 秒必须拆成 2 个或更多 sub-shot |
| 场景主时钟 | `scene-director.md:56-73` | 最终以 TTS 实测时长和语音边界为准，不能用词数均分替代 |

### beat 不能凭空取一个整数

仓库没有把 `beat_count` 定义成 `series-adapt` 的固定配置字段。这里需要区分三个单位：

1. **语义 section**：改写脚本的 hook/context/body/climax/outro 等段落。
2. **视觉事件 beat**：4–7 秒一次的入场、图表更新或 sub-shot 切换；不一定每次都生成新图。
3. **独立图像资产 beat**：真正需要独立生成一张图片的单位，是成本模型中的 `B`。

因此，成本模型使用：

```text
B = 经批准的 scene_plan 中独立图像资产单位数量
```

如果暂时只能按视觉事件密度做敏感性分析：

```text
B_event(τ) = ceil(600 / τ)，τ ∈ [4, 7] 秒
```

得到的边界是 86–150 个事件。下表只表示敏感性，不是对每集 beat 数的假设：

| 视觉事件间隔 τ | 单集 B_event | 100 集 B_event |
|---:|---:|---:|
| 7 秒 | 86 | 8,600 |
| 6 秒 | 100 | 10,000 |
| 5 秒 | 120 | 12,000 |
| 4 秒 | 150 | 15,000 |

### 现有 EP02 只能作为结构校准样本

仓库中的 EP02 暴露了“beat”口径不能混用：

- `adaptation_script.json:8-10` 是 485 秒、1,526 词的脚本版本，并含 10 个 section（`adaptation_script.json:14-134`）。
- `scene_plan.json:5` 为 552.5 秒；10 个顶层 scene 各自包含 sub-shot 数量，按文件中的数组范围计数为 `6+6+6+5+8+6+6+6+4+2 = 55` 个 sub-shot（`scene_plan.json:33-1443`）。
- `asset_manifest.json:2-103` 实际只登记了 10 张图片，即每个顶层 section 一张，而不是 55 个 sub-shot 一张。
- `asset-director.md:84-85` 已明确规定每个 sub-shot 必须生成独立图像，不能复制 hero 图；`compose-director.md:180-182` 也要求构成族按 sub-shot 分配。

结论是：EP02 的 10 张资产是现有 artifact 的低密度基线，55 个 sub-shot 是更接近逐帧资产单位的结构样本，但两者都不能替代后续每集批准的 `B`。锁定成本前必须先明确本项目把 `B` 定义为 section、sub-shot，还是独立视觉事件。

## 成本公式与表格

### 变量和现金成本口径

```text
N ∈ {1, 2, 3, 4}                 每 beat 的独立图像数
P_img_local = 0.00 USD/image     本地 ComfyUI/Klein 现金 API 单价
P_clip                              云端直接视频单 clip 单价，当前缺失
B                                  单集独立图像资产 beat 数
```

只统计本 issue 要求的图像/视频生成现金成本，不把本地 GPU 资源、TTS、素材下载、人工审核、HyperFrames/FFmpeg 运行时间冒充成 API 单价。

```text
I_image_episode(N) = B × N
C_image_episode(N) = B × N × P_img_local = 0
C_image_100(N) = 100 × B × N × P_img_local = 0

I_video_episode = B clips
C_video_episode = B × P_clip
C_video_100 = 100 × B × P_clip
```

若未来供应商按秒计费，且每个 clip 时长为 `L` 秒、单价为 `p_sec`：

```text
P_clip = L × p_sec
C_video_episode = B × L × p_sec
```

这只是符号公式。`series-adapt` 当前没有选定直接视频 provider、模型、clip 时长、是否带音频或重试预算，因此不能把某个通用 provider 的代码默认值写成 issue #3 的基线。

### 方案对比：每集与 100 集

| 方案 | 单集图像/clip 数 | 单集现金成本 | 100 集图像/clip 数 | 100 集现金成本 |
|---|---:|---:|---:|---:|
| 现状：每 beat 1 图 | `B` | `B × 0 = $0` | `100B` | `100B × 0 = $0` |
| 逐帧：每 beat 2 图 | `2B` | `2B × 0 = $0` | `200B` | `200B × 0 = $0` |
| 逐帧：每 beat 3 图 | `3B` | `3B × 0 = $0` | `300B` | `300B × 0 = $0` |
| 逐帧：每 beat 4 图 | `4B` | `4B × 0 = $0` | `400B` | `400B × 0 = $0` |
| 直接视频：每 beat 1 clip | `B` clips | `B × P_clip` | `100B` clips | `100B × P_clip` |

### 图像数量敏感性表

下表把 `B` 取为 4–7 秒视觉事件规则产生的敏感性点；现金图像成本在所有档位均为 0，数量变化代表 GPU 工作量和资产 QA 工作量的线性放大。

| B | 现状 1 图/beat：单集 | 逐帧 2 图/beat：单集 | 逐帧 3 图/beat：单集 | 逐帧 4 图/beat：单集 | 现状 1 图/beat：100 集 | 逐帧 2 图/beat：100 集 | 逐帧 3 图/beat：100 集 | 逐帧 4 图/beat：100 集 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 86 | 86 | 172 | 258 | 344 | 8,600 | 17,200 | 25,800 | 34,400 |
| 100 | 100 | 200 | 300 | 400 | 10,000 | 20,000 | 30,000 | 40,000 |
| 120 | 120 | 240 | 360 | 480 | 12,000 | 24,000 | 36,000 | 48,000 |
| 150 | 150 | 300 | 450 | 600 | 15,000 | 30,000 | 45,000 | 60,000 |

作为已存在 artifact 的参照，若暂把 EP02 的 55 个 sub-shot 当作 `B`，则单集图像数为 55/110/165/220，100 集为 5,500/11,000/16,500/22,000；这不是全系列 beat 假设，也不覆盖当前 artifact 中每 section 一张的 10 张低密度基线。

### 直接视频上限锚点

仓库没有为 `series-adapt` 配置直接视频路线的单价。当前应保留：

```text
单集云端上限锚点 = B × P_clip
100 集云端上限锚点 = 100B × P_clip
```

仓库代码确实存在 provider-specific 的估算函数，但它们不是本管线已锁定的价格基线：

- `tools/video/kling_video.py:107-114` 按 5 秒归一化给出 standard/pro/master 的代码估值 `$0.10/$0.20/$0.30`。
- `tools/video/veo_video.py:150-168` 按秒、分辨率、音频开关分支计算估值。
- 这些实现没有被 `apps/series-adapt/config.yaml` 选为直接视频 provider，也没有 issue #3 的统一 clip 时长和重试假设。因此本研究不把它们硬套进数值总成本；确定 provider 后再将其代入 `P_clip`。

## 本地 GPU 资源成本说明

### 已确认的本地路径

- `tools/graphics/comfyui_image.py:45-55`：工具名为 `comfyui_image`，provider 为 `comfyui`，`runtime = ToolRuntime.LOCAL_GPU`。
- `comfyui_image.py:73-76`：明确把“local GPU generation without API costs”列为适用场景。
- `comfyui_image.py:147-150`：资源下限为 2 CPU、8 GB RAM、8 GB VRAM、500 MB disk，`network_required=False`。这只是工具契约下限，不是 Klein 全流程的实测资源账单。
- `comfyui_image.py:166-167`：`estimate_cost()` 直接返回 `0.0`。
- `comfyui_image.py:178-223`、`:265-283`：支持 `workflow_json`/`workflow_path`，并执行自定义 ComfyUI workflow；这覆盖 Klein workflow 路径。
- `comfyui_image.py:290-310`：结果中的 `cost_usd=0.0`，同时保留 provider、model、workflow provenance、seed 和耗时字段。

### Klein workflow 证据

- `tools/_comfyui/workflows/Klein-txt2image.json:31-39` 使用 `flux-2-klein-9b_int8_convrot.safetensors`；`:111-119` 使用 `qwen_3_8b_fp8mixed.safetensors`；`:177-194` 使用 `flux2-vae.safetensors` 和 1MP/16:9 分辨率；`:147-151` 有 seed；`:197-210` 为 4 steps。
- `Klein-img2image.json:15-22` 使用参考图；`:204-221` 使用同一 Klein/Qwen/VAE 模型栈；`:239-243` 有 seed；`:248-258` 是状态提示词；`:261-268` 是 Klein UNet。
- `Klein-img2image-dual-reference.json:15-31` 同时接收视觉锚点和当前状态；`:124-138` 为 4 steps；`:281-309` 分别缩放锚点和当前状态；`:311-340` 有 seed、`Keep the anchor composition and the current state unchanged. Apply only the requested state delta.` 和 Klein 模型。
- `Klein-txt2image.json`、`Klein-img2image.json`、`Klein-img2image-dual-reference.json` 及其他 Klein workflow 中没有 `cost_usd`、`price` 或 `unit_cost` 字段；它们描述的是节点、模型、采样、参考图和保存输出，不提供美元资源费率。

### 不应被写成 `$0` 的项目

本地路径的“现金 API 成本为 0”不等于总经济成本为 0。仓库没有以下量的可核验单价或实测记录：

- **GPU 时间**：生成数量从 `B` 增到 `N×B`，GPU 时间通常至少按调用数线性增加，但实际还受 batch、显存、分辨率、workflow、缓存和并发影响。
- **模型下载**：Klein workflow 引用的模型文件名已记录，但文件大小、下载流量和下载费用未记录。
- **硬件折旧与电力**：没有 GPU 小时费率、设备购置价、寿命小时数、电价或功耗实测。
- **返工与 QA**：`asset-director.md:77-88` 对人物图、参考帧、重复画面和脸部保护都有强制 QA；逐帧数量增大时，人工/视觉检查工作也会增长。

若未来需要内部核算，可使用符号项而不是编造费率：

```text
C_gpu = image_count × measured_gpu_seconds_per_image / 3600 × R_gpu_hour
C_model = one_time_model_download_cost + amortized_storage_cost
C_hw = allocated_depreciation + electricity_cost
C_local_total = C_gpu + C_model + C_hw + QA_cost
```

当前 `R_gpu_hour`、模型下载成本、硬件折旧、电费和 QA 工时费率均为缺失字段，不能从本仓库推出美元数。

## 结论与敏感因素

1. **主路径成立，但成立的是现金 API 成本假设。** 本地 Klein 图像调用的代码估算和执行结果都为 `$0.00`，所以 N=2/3/4 不会增加现金 API 支出。
2. **逐帧资源量严格按 N 倍增长。** 在相同 `B` 下，N=4 相比现状多 4 倍图像调用；GPU 时间、显存占用机会、输出磁盘、QA 和失败重试压力都应按 N 作为第一阶敏感因素。
3. **B 是最大的未锁定变量。** 4 秒与 7 秒视觉事件密度对应 150 与 86 个事件，数量相差约 1.74 倍；但视觉事件不必等于独立图像，因此最终必须从每集批准的 scene_plan 统计 `B`。
4. **现有 EP02 artifact 有口径冲突。** 10 个 section、55 个 sub-shot、10 张已登记图片分别代表不同密度；不能把 10、55 或 86–150 任何一个数字静默当成全季基线。
5. **直接视频只适合作为云端上限锚点。** 在 `P_clip` 未确定时只报告 `B×P_clip` 和 `100B×P_clip`。如果未来选择按秒计费的 provider，还要明确 clip 时长、音频开关、分辨率和重试率。
6. **配置存在待同步风险，但本研究不改配置。** `apps/series-adapt/config.yaml:39-40` 仍写着 `image_selector` + `gemini-3.1-flash-lite-image`/`google_imagen`；这与本 issue 已确定的本地 Klein 主路径不一致。该冲突应在后续决策或配置变更任务中处理，不纳入本次研究改动。

## 证据文件和行号

| 证据 | 关键行号 | 用途 |
|---|---|---|
| `apps/series-adapt/config.yaml` | `16-18`, `25`, `39-40` | 100 集、600 秒、150 WPM、2.98 WPS，以及仍残留的旧云端图像配置 |
| `pipeline_defs/series-adapt.yaml` | `43-46`, `103-113`, `157-166`, `191-201` | 默认预算为 `$0.00`、脚本时长门、资产阶段图像要求、组合验收 |
| `skills/pipelines/series-adapt/rewrite-director.md` | `21-31`, `49-60`, `83-89` | 实测语速、词数预算、10 分钟结构和词数门禁 |
| `skills/pipelines/series-adapt/references/vox-story-library.md` | `62-76`, `78-92` | 4–7 秒视觉事件、60–90 秒小节拍和高光节拍 |
| `skills/pipelines/series-adapt/scene-director.md` | `56-73`, `93-124`, `172-185` | TTS 主时钟、语音边界、sub-shot 拆分和独立视觉资产要求 |
| `skills/pipelines/series-adapt/asset-director.md` | `41-61`, `63-85`, `147-154` | 生图尺寸、模型锁定、每 sub-shot 独立图、时长校正 |
| `skills/pipelines/series-adapt/compose-director.md` | `122`, `156-182` | 视觉事件节奏和 sub-shot 级构成要求 |
| `tools/graphics/comfyui_image.py` | `45-76`, `85-150`, `166-170`, `178-223`, `265-310` | `LOCAL_GPU`、无 API 成本、资源下限、自定义 workflow、`estimate_cost()=0.0` 和结果成本 |
| `tools/base_tool.py` | `83-88`, `108-115`, `127-136`, `278-310` | runtime、资源 profile、`ToolResult.cost_usd` 和成本估算契约 |
| `tools/_comfyui/workflows/Klein-txt2image.json` | `31-39`, `111-119`, `147-210` | Klein 模型、文本编码器、seed、分辨率和 4 steps |
| `tools/_comfyui/workflows/Klein-img2image.json` | `15-22`, `204-268` | 单参考图、Klein 模型栈和状态提示词 |
| `tools/_comfyui/workflows/Klein-img2image-dual-reference.json` | `15-31`, `124-138`, `165-258`, `281-340` | 双参考图、4 steps、锚点/当前状态和 state delta |
| `projects/series-adapt-99/ep-02/adaptation_script.json` | `8-10`, `14-134` | EP02 脚本时长、词数和 10 个 section |
| `projects/series-adapt-99/ep-02/scene_plan.json` | `5`, `19-1443` | EP02 的 10 个顶层 scene、55 个 sub-shot 和 4 秒 visual beat 字段 |
| `projects/series-adapt-99/ep-02/asset_manifest.json` | `2-103` | EP02 当前实际登记的 10 张图片 |
| `tools/video/kling_video.py` | `107-114` | 仓库内存在但未锁定的 Kling 代码估价 |
| `tools/video/veo_video.py` | `150-168` | 仓库内存在但未锁定的 Veo 代码估价 |
