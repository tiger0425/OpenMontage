# IndexTTS-2.5 升级计划（OpenMontage 全链路）

> 2026-08-12 grilling 会话成果。领域术语见 `CONTEXT.md`「TTS 引擎与模型版本」章节；决策记录见 `docs/adr/ADR-004-indextts-2.5-upgrade.md`；ADR-003 的 D3 被部分取代。
> 前置事实：本地 `D:/index-tts` 克隆停在 IndexTTS-2（HEAD 1349584, 2026-07-14），无 `infer_v2_5.py`；GPU RTX 3090/24GB（空闲 ~22GB）；`D:` 剩余 25.5GB。

## ⚠️ 计划修订（2026-08-12 复核，开工前必读）

1. **源码来源修正**：官方 2.5 代码**不在 main**（main HEAD=3376228 无 `infer_v2_5.py`），在 **`feat/webui-default-2.5` 分支**（HEAD 663fb9c，94 文件差异，含 `indextts/infer_v2_5.py`）。原计划「`git pull`」改为：
   ```bash
   cd D:/index-tts
   git stash push -m "pre-2.5-local-changes"      # 先存本地 pyproject.toml/uv.lock 改动
   git fetch origin feat/webui-default-2.5
   git checkout feat/webui-default-2.5            # 2.5 代码 + 依赖
   ```
   - `indextts_server.py` / `indextts_bridge.py` / `checkpoints/config.yaml` 是 untracked，切分支不受影响、自动保留
   - feat 分支也改了 `pyproject.toml`（依赖变化），故必须先 stash 本地改动再切
   - 升级完成后按需 `git stash pop` 决定本地 pyproject/uv.lock 改动去留
2. **独立 skill 包同步（新增条目）**：auto-dub 已于 2026-08-12 拆分为独立仓库 `E:\YifuAIForge\auto-dub-skill`（vendoring 了 2.0 版 `indextts_server.py`）。**桥收编后的 2.5 版 server.py 必须同时回灌到 `auto-dub-skill/tools/audio/indextts_server.py`**，OpenMontage 与独立包两处协议同步。独立包侧 `_resolve_indextts_paths` 已支持 config/env 指向 2.5 部署（`<DATA_ROOT>/models/indextts`），升级后只需回灌 server.py + 在独立包 config 设 `tts_model_version`。
3. **`D:/index-tts` 本地未提交改动**：`pyproject.toml`/`uv.lock` 已修改（M），`indextts_server.py`/`indextts_bridge.py`/`checkpoints/config.yaml` 等 untracked——切分支前需按上文 stash。

## 摘要

将 OpenMontage 默认本地 GPU TTS 从 IndexTTS-2 升级到 **IndexTTS-2.5**，双版本并行（2.5 默认、2 保留做 A/B 与回退），并利用 2.5 的原生语速控制 `duration_factor` 重构逐句对齐机制。分两阶段落地：

1. **阶段一（止血）**：外部仓库升级 + 桥收编进仓库 + 协议/`lang` 透传 + 版本命名/缓存隔离，现有机制原样跑在 2.5 上。
2. **阶段二（机制重写）**：`duration_factor` 双次合成对齐（粗调）→ atempo（微调兜底），cps 职责收窄，重翻阈值放宽，qwen 开关管道就位。

阶段一与阶段二之间设 **A/B 验收门槛**（用户听 6–8 条样片 + 指标对照）。

## 背景

- IndexTTS-2.5（2026-08-10 发布）新增：五语种（`lang`）、原生语速 `duration_factor`（0.5–2.0×）、推理快 ~37%（RTF 0.206 vs 0.326）、`use_emo_text=True` 需 `use_qwen_emo=True` 构造、`emo_audio_prompt`、入口 `indextts/infer_v2_5.py`、构造 `use_bf16`。
- OpenMontage 现有对齐机制（cps 校准 × 0.7 打折、atempo ±5%、LLM 重翻回退）全部建立在 ADR-003 前提「IndexTTS2/VoxCPM 均无语速参数」上，该前提对 2.5 失效。
- 桥（`indextts_server.py`）当前 untracked 躺在外部仓库，stdin/stdout JSON 协议，`from indextts.infer_v2 import IndexTTS2`，`use_fp16=True`。另有废弃实验文件 `indextts_bridge.py`（单发式，不收编）。
- cps 缓存按引擎分文件（`voxcpm_cps_cache.json` / `indextts_cps_cache.json`），未按模型版本隔离。

## 目标

1. 全链路默认跑在 2.5，吃到加速（~37%）与五语能力，现有机制行为零回归。
2. 逐句对齐改由 `duration_factor` 原生语速主导，比 atempo 更自然。
3. 桥收编进仓库，消除外部 untracked 脆弱点与「双处同步」契约。
4. 2 保留可回退，直到 A/B 质检通过后择机下架。

## 范围

### 做（阶段一）
- 外部仓库：`git pull` → `uv sync --all-extras`（镜像源）→ 2 权重搬 `checkpoints_2` → 下载 2.5 到 `checkpoints`。
- 桥收编：`indextts_server.py` 移入 OpenMontage（`apps/indextts-bridge/`），加 `--version 2.5|2` 分支（import / `use_bf16`/`use_fp16` / 权重目录）。
- `tools/audio/indextts_tts.py`：`model="indextts-2.5"`，启动带 `--version`，协议透传 `lang` / `duration_factor` / `use_random`，预留 `emo_audio_prompt`，`use_emo_text` 加 qwen 前提校验，`duration_factor` 越界拒绝。
- `apps/auto-dub/batch/pipeline_automator.py` + `apps/markhasara/index_tts.py` + `apps/markhasara/pipeline.py`：同步桥协议与 `--version` 分支。
- 配置：4 个 config 加 `tts_model_version`（默认 "2.5"）+ `tts_lang`（缺省从 `target_language` 映射）+ `tts_use_qwen_emo: false`。
- cps 缓存按版本隔离（`indextts_cps_cache_<version>.json`），2.5 重测。
- provenance 补 `model_version`。
- 测试：9 个相关测试 + registry 自检适配新命名。

### 做（阶段二）
- 对齐路径：双次合成（自然合成测量 → `factor=目标时长/自然时长` → `duration_factor` 重合成）；factor 越界或仍失准降级 atempo。
- cps 职责收窄为仅服务翻译字数预算。
- 重翻回退保留但阈值放宽。
- qwen 开关管道：桥 `--use-qwen-emo` 启动分支；本轮无试点流水线。

### 不做
- 不换 vLLM / 官方 WebUI 集成。
- 本阶段不启用 `emo_audio_prompt` 与 `use_qwen_emo` 试点。
- 不自动逐句探测语言。

## 技术决策（摘要，详见 ADR-004）

1. 双版本并行，`tts_model_version` 维度，2 可回退。
2. 单桥 + `--version` 分支，收编进仓库。
3. `duration_factor` 粗调 + atempo 微调（Q6-C 双次合成）。
4. bf16 默认（3090 空闲 ~22GB 充裕）。
5. `lang` 显式配置，缺省从 `target_language` 映射。
6. 协议字段全集见 ADR-004 D4。

## 验证策略

- **阶段一验收门槛**：2–3 个既有项目（含已知坑：静音伪文件、前导静音、短句 cps、男声音高锚定）跑 2 vs 2.5 对照：
  - 指标：WER/SS（复用 `video-understand`/转录分析）、逐句对齐命中率、cps 重测值、RTF。
  - 用户亲听 6–8 条样片；不劣于 2 才切默认。
- 专项：`duration_factor` 是否线性命中目标时长；2.5 是否仍产前导静音（决定 `trim_audio_lead.py` 去留）；静音伪文件检测是否仍需要。
- 全量测试：`tests/tools/test_indextts_emo_semantics.py` 等 9 个测试适配后通过；registry `provider_menu_summary()` 自检。

## 执行策略

1. 阶段一落地（见范围；先按「计划修订」处理分支与本地改动）。
2. 跑验收门槛；不达标则回退默认 2，排查 2.5 问题后重试。
3. 阶段二机制重写 + 逐流水线 `tts_lang`。
4. 全部通过后更新相关 skill 文档（auto-dub SKILL.md、独立包 SKILL.md、repo-to-video/series-adapt director、localization-dub lessons-learned）并考虑下架 2。

## 待办事项

- [ ] 外部仓库：stash 本地改动 → fetch + checkout `feat/webui-default-2.5` → `uv sync --all-extras`（镜像源）→ 2 权重搬 `checkpoints_2` → 下载 2.5 到 `checkpoints`
- [ ] 桥收编 + `--version` 分支（`apps/indextts-bridge/`，import / `use_bf16`/`use_fp16` / 权重目录）
- [ ] 独立 skill 包同步：收编后的 2.5 `indextts_server.py` 回灌到 `auto-dub-skill/tools/audio/`（两处协议同步）
- [ ] 三处调用实现协议同步（pipeline_automator / markhasara index_tts / markhasara pipeline）
- [ ] 4 config 版本/lang/qwen 字段
- [ ] cps 缓存版本隔离 + 2.5 重测
- [ ] provenance 补 model_version
- [ ] 测试与 registry 自检适配
- [ ] A/B 验收（用户听样片）
- [ ] 阶段二：duration_factor 对齐
- [ ] skill 文档一致性修订（含独立包 SKILL.md）

## 风险与约束

- `duration_factor` 线性命中时长是经验假设，需实测；失准依赖 atempo ±5% 兜底。
- 双版本并行占磁盘 5–8GB、配置复杂度上升。
- 2.5 是否仍产前导静音/静音伪文件未知，影响 `trim_audio_lead.py` 与静音检测去留。
- GPU 锁（timeout 1800s / heartbeat 15s）沿用；A/B 只能串行。
- 桥收编后 git 历史中的外部版本不再可跑（2 兼容靠 `checkpoints_2` + `--version 2`）。
- **2.5 在 feat 分支**（`feat/webui-default-2.5`），官方 main 尚未合并；若官方后续重构接口，feat 分支的 API 可能漂移，升级后需锁定提交号。
- **独立包双处同步**：`auto-dub-skill` 与 OpenMontage 各持一份 `indextts_server.py`，升级必须同步回灌，否则独立包停在 2.0 协议。

## 成功标准

- 默认 `tts_model_version: "2.5"`，全链路无回归。
- A/B 对照指标不劣于 2，用户对样片满意。
- 逐句对齐命中率 ≥95%（±15% 容差，沿用 ADR-003 验收口径）。
- 桥在仓库内可版本化维护，无外部 untracked 依赖。
