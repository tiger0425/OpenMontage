# IndexTTS2 语音去数码味与去机械感研究报告

> 结论先行：**数码味**主要来自 BigVGAN 22kHz 声码器的高频梳齿伪影，被「扩散步数过少 + FP16 全程推理 + 22050Hz 输出」放大；**机械感**主要来自「固定 calm 情感向量 + `repetition_penalty=10.0` 异常值 + beam search」的组合。修法与优先级：**源头参数（A）> 后处理 DSP（B）> 混音（C）**，且层次 A 中「情感策略」与「repetition_penalty」两项改进最大、成本最低。

---

## 1 摘要

本报告基于对 `D:/index-tts/indextts/infer_v2.py`（推理主链）、`D:/index-tts/indextts_server.py`（常驻服务桥）、`D:/index-tts/checkpoints/config.yaml`（模型配置）以及 OpenMontage 侧 `tools/audio/indextts_tts.py`、`apps/auto-dub` 的逐行研读，定位 IndexTTS2 生成语音「数码味（digital / metallic artifact）」与「机械感（robotic feel）」的可验证根因，并给出**三层解决方案矩阵**与**落地路径**。

关键发现：

- 数码味主频带集中在 **~8–11kHz**（BigVGAN 22kHz vocoder 高频伪影 + 扩散步数不足导致的高频能量失真）。
- 机械感的第一来源不是音质，而是**情感/韵律策略**：项目默认把所有句子压成固定 calm 向量，剥夺了语调起伏。
- `infer_v2.py` 中 `repetition_penalty = 10.0` 属于异常值（正常语义采样通常 1.0–1.3），是韵律生硬的高度可疑来源，**需 A/B 实验确认**。

本报告为纯研究文档，不含任何代码改动。

---

## 2 背景

IndexTTS2 是 IndexTeam 的开源 TTS 模型（零样本音色克隆 + 8 维情感控制 + 精确时长控制），在 OpenMontage 中承担多条流水线的本地配音/旁白：

| 使用场景 | 入口 | 情感策略 |
|----------|------|----------|
| Auto-Dub（默认引擎） | `apps/auto-dub` → `pipeline_automator` → subprocess 常驻服务 | 默认 `use_emo_text` 自动判情感 |
| series-adapt / repo-to-video | `tts_selector` → `tools/audio/indextts_tts.py` | 通常显式传 calm 向量 |
| markhasara | `apps/markhasara/index_tts.py` | `calm` / `excited` 二选一 |
| vox-paper-collage | `tts_selector` → `indextts_tts` | 显式传 `emo_vector=[0,...,1.0]`（平静纪录片） |

调用链统一为：

```
indextts_tts.py / index_tts.py / pipeline_automator
        │  JSON 行协议（stdin/stdout）
        ▼
indextts_server.py  （常驻进程，FP16，模型只加载一次）
        │
        ▼
infer_v2.py  （IndexTTS2 推理主链：GPT → DiT/CFM 扩散 → BigVGAN）
```

全链路受 `lib/gpu_lock.py` 跨进程 GPU 互斥保护（8–16GB VRAM）。

---

## 3 架构梳理：三段式生成链

IndexTTS2 是经典「语义 token → 扩散 Mel → 神经声码器」三段式：

```
文本 → TextNormalizer/TextTokenizer
  → 语义 GPT（UnifiedVoice, 1280 维, 24 层, conformer_perceiver 条件）
      自回归采样出语义 code（VQ, codebook=8192, 4 个 quantizer）
  → s2mel（DiT 13 层 + CFM 条件流匹配, 25 步扩散）
      把语义 code 转成 Mel（80 维, sr=22050）
  → BigVGAN v2 声码器（22kHz, 80 band, 256x）
      把 Mel 合成 22050Hz 波形 → int16 WAV
```

关键参数（含证据位置）：

| 参数 | 值 | 位置 | 备注 |
|------|-----|------|------|
| 输出采样率 | 22050 Hz | `infer_v2.py:535` | 低于训练配置的 24000 |
| 扩散步数 | 25 | `infer_v2.py:645` | CFM 步数 |
| CFG 率 | 0.7 | `infer_v2.py:646` | 分类器自由引导强度 |
| 采样参数 | do_sample=True, top_p=0.8, top_k=30, temperature=0.8 | `infer_v2.py:527-529` | GPT 自回归采样 |
| 解码参数 | num_beams=3, repetition_penalty=10.0 | `infer_v2.py:532-533` | **repetition_penalty 异常高** |
| 训练采样率 | 24000 | `config.yaml:3` | dataset.sample_rate |
| 声码器 | bigvgan_v2_22khz_80band_256x | `config.yaml:117-119` | 22kHz vocoder |
| FP16 | 是 | `infer_v2.py:95-98`、`indextts_server.py:72-73` | GPT 与 s2mel 均 `.half()` |
| 段间静音 | 200ms | `infer_v2.py:368, 685` | `interval_silence` |
| 单段 token 上限 | 120 | `infer_v2.py:512` | `max_text_tokens_per_segment` |
| 输出量化 | int16 + 峰值钳到 ±32767 | `infer_v2.py:672, 705` | 先 clamp 再保存 |
| 服务端归一化 | RMS→3500，峰值压到 0.95 | `indextts_server.py:42-62` | 二次限幅 |
| 情感向量偏置 | emo_bias，总和 >0.8 时缩放到 0.8 | `infer_v2.py:348-362` | 抑制易出怪声的情感 |

---

## 4 数码味根因分析

「数码味」的听感特征：金属感、齿音刺耳、电子底噪、词尾"发毛"。以下按贡献度排序。

| # | 根因 | 机制 | 证据 | 严重度 |
|---|------|------|------|--------|
| 1 | **BigVGAN 22kHz 高频伪影** | vocoder 在高频段（~8–11kHz）产生梳齿状频谱纹路，是人声 vocoder 的固有代偿伪影；22kHz vocoder 在 11kHz 以上无信息，能量在奈奎斯特边界附近堆积成"咝/毛"感 | `config.yaml:119` 指定 22kHz vocoder | **主因** |
| 2 | **扩散步数过少（25 步）** | CFM 步数低 → Mel 高频能量分布不收敛、残留噪点，被声码器放大成刺耳齿音与"数码底噪" | `infer_v2.py:645` | 高 |
| 3 | **FP16 全程推理** | GPT 与 s2mel 均 `.half()`，低能量区（气音、词尾、呼吸）的浮点舍入误差被扩散迭代放大 | `infer_v2.py:95-98` | 中 |
| 4 | **22050Hz 输出低于训练 24000Hz** | 训练 mel 基于 24000Hz，推理按 22050 采样率走 s2mel（`config.yaml:55` sr=22050），两者不齐导致轻微频谱错位；>11kHz 能量缺失并硬切 | `infer_v2.py:535` vs `config.yaml:3` | 中 |
| 5 | **服务端峰值限幅二次削波** | `normalize_volume` 把峰值压到 0.95（RMS 目标 3500，约 −19dBFS），齿音/爆破音瞬态被硬削成"咔哒碎音"；随后又钳到 int16 ±32767 | `indextts_server.py:58-59`、`infer_v2.py:672` | 中 |
| 6 | **无 dither 直接 int16 量化** | 16bit 输出无抖动，低电平段出现量化阶梯噪声，放大"数码感" | `infer_v2.py:705` | 低 |

### 4.1 数码味主频带的量化判断方法

在动任何参数前，先对一段合成样本做频谱快照存档（建议含「参考人声」「当前合成」「改后合成」三者对比）：

```powershell
# 生成对数尺度频谱图，肉眼定位 5–11kHz 的能量堆积/梳齿
ffmpeg -i sample.wav -lavfi showspectrumpic=s=1200x600:legend=1 spectrum.png -y
# 或逐帧显示频谱
ffmpeg -i sample.wav -lavfi showspectrum=s=1280x720:mode=combined spectrum.mp4 -y
```

`librosa` 也可输出精确频带能量表：

```python
import librosa, numpy as np
y, sr = librosa.load("sample.wav", sr=None)
# 分频带 RMS，重点看 5–8k 与 8–11k
for lo, hi in [(0, 3e3), (3e3, 5e3), (5e3, 8e3), (8e3, 11e3)]:
    band = librosa.stft(y, sr=sr, n_fft=2048)
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    mask = (freqs >= lo) & (freqs < hi)
    print(lo, hi, np.sqrt((np.abs(band[mask])**2).mean()))
```

用数据确认「哪条根因实际贡献最大」，再决定改动优先级（见第 7 节实验矩阵）。

---

## 5 机械感根因分析

「机械感」的听感特征：平调、朗读腔、韵律生硬、句与句之间断裂。**大部分根因在情感/韵律策略而非音质**。

| # | 根因 | 机制 | 证据 | 严重度 |
|---|------|------|------|--------|
| 1 | **固定 calm 情感向量** | 项目默认 `use_emo_text=False` + `emo_vector=[0,...,0,1.0]`，把**所有**句子压成无起伏的平静腔。calm 向量本身没问题，问题在"全句恒定"——没有任何语调起伏来源 | `tools/audio/indextts_tts.py:45`、`resolve_emotion_mode`（:51-71） | **主因** |
| 2 | **`repetition_penalty = 10.0` 异常高** | 正常语义采样该值通常 1.0–1.3；10.0 会强抑制音高/音节/语义 code 的重复结构，导致生硬的韵律跳变与"逐字蹦"。**高度可疑，需 A/B 确认**（也可能是官方对语义 token 的刻意设置，需实验验证实际作用） | `infer_v2.py:533` | 高（待验证） |
| 3 | **beam search（num_beams=3）** | beam 解码倾向最"安全"的序列，产生单调、无口语气息起伏的"播音腔" | `infer_v2.py:532` | 中 |
| 4 | **`temperature=0.8` + `top_k=30` + `top_p=0.8` 组合偏保守** | 采样自由度偏低，韵律多样性不足 | `infer_v2.py:527-529` | 中 |
| 5 | **段间 200ms 静音 + 每段独立采样** | 多句拼接时每句独立起止，句间韵律断裂、听感"一格一格" | `infer_v2.py:368, 685`、`interval_silence` | 低 |
| 6 | **voice_ref 质量不足** | 参考音频过短/含噪/采样率低 → 克隆音色趋近"平均腔"，丢失说话人韵律特征 → 机械感。项目 lessons-learned 已确认「源头稳定克隆优先」 | `docs/.../localization-dub/lessons-learned.md` 铁律 A / 反模式 7 | 中 |
| 7 | **文本情感自动判定的波动** | `use_emo_text=True` 时 Qwen 判情感随文本波动，短句偶发"突然变调"；项目部分流水线为避免波动改固定向量，代价是失去起伏 | `infer_v2.py:409-416`、`QwenEmotion` | 低 |

### 5.1 情感策略的正确打开方式（核心结论）

问题的本质是**「全固定」vs「全自动」两个极端**。正确策略应分级：

| 场景 | 推荐策略 | 理由 |
|------|----------|------|
| 短句配音（auto-dub 逐句） | `use_emo_text=True` + `emo_alpha≈0.3–0.5` | 保留自然起伏但抑制突变；长文本用 0.6 默认 |
| 长旁白（纪录片/讲解） | 显式固定向量，但**不要全 calm**——可给 `neutral`/`calm` 分配主权重 + 少量情绪分量 | 稳定但不死板 |
| 强调句/高潮句 | 逐句覆盖 `emo_vector` | 定点注入起伏 |
| 多说话人 | 每人独立 voice_ref + 各自情感策略 | 见 auto-dub multi-speaker 计划 |

> 注意：`normalize_emo_vec`（`infer_v2.py:348-362`）会先把向量乘以偏置再约束总和 ≤0.8，calm 偏置 0.5625、surprised 偏置 0.6875——**直接传满值 1.0 会被缩小**。传 `[0,0,0,0,0,0,0,1.0]` 实际生效的是 calm≈0.5625，这也会弱化情感表达。

---

## 6 三层解决方案矩阵

### 层次 A：源头参数（最有效，需改 `D:/index-tts/infer_v2.py` + 服务端透传）

> 现状：`indextts_server.py` 只透传 `text / output_path / voice_ref / seed / emo_vector / use_emo_text / emo_alpha`，`diffusion_steps / repetition_penalty / num_beams / temperature / 采样率` 均为 `infer_v2.py` 硬编码。**落地需给服务端协议增加透传字段**（`infer_v2.py` 的 `infer_generator` 已通过 `**generation_kwargs` 支持大部分采样参数覆盖）。

| 改动 | 现状 → 建议 | 预期收益 | 成本 |
|------|------------|----------|------|
| **情感策略** | 全固定 calm → 分级策略（见 5.1） | 机械感下降最明显 | 低（纯调用侧，服务端零改动） |
| **`repetition_penalty`** | 10.0 → 1.0–1.2（**先 A/B 验证**） | 韵律自然度 | 低（`generation_kwargs` 透传） |
| **`num_beams`** | 3 → 1（纯采样） | 去掉朗读腔 | 低 |
| **`temperature`** | 0.8 → 0.6–0.7 | 韵律多样性；过低会呆，需试听 | 低 |
| **扩散步数** | 25 → 50/100 | 高频齿音/数码底噪显著下降，最直接对付数码味 | 中（推理耗时约线性上升） |
| **输出采样率** | 22050 → 24000 | 与训练对齐，缓解 >11kHz 能量缺失 | 中（需改 s2mel sr 与保存 sr，并核对 vocoder 输出） |
| **FP16 → FP32（局部）** | 关键路径 FP32 | 低能量区噪声下降 | 高（VRAM 需 ≥16GB；3090 24GB 可承载） |
| **段间静音** | 200ms → 100ms | 句间衔接更紧 | 低 |
| **CFG 率** | 0.7 → 0.6–0.7 微调 | 过度引导会产生"过分干净"的 vocoder 味 | 低（需试听） |

### 层次 B：后处理 DSP（立即可用，FFmpeg / `tools/audio/audio_enhance.py` 预设）

> 推荐落地为 `audio_enhance` 的新预设（如 `tts_naturalize`）或独立 DSP 链路，**不要**写 ad-hoc 脚本直接调 ffmpeg 外的库。优先级从上到下。

| 步骤 | 手法 | 目标频带/作用 | 备注 |
|------|------|--------------|------|
| 1. 高频柔和 | 轻量低通/搁架衰减：`equalizer=f=9000:t=shelf:g=-2..-3` 或 `lowpass=f=13000` | 8–11kHz vocoder 数码味主频带 | **保留 5–8kHz 清晰度**，不要一刀切 |
| 2. De-esser | 对 5–8kHz 做动态衰减（见下） | 齿音 | 先于压缩器执行 |
| 3. True-peak limiter | `alimiter=limit=-1.0dB:attack=1:release=10` | 替代服务端 0.95 硬削的咔哒 | 置于链尾 |
| 4. 保守模拟饱和 | 极轻微（`acontrast`/软削波），让高频"暖" | 掩盖数码感 | **过饱和会放大伪影**，宁可不用 |
| 5. 动态塑形 | 轻压缩：`acompressor=threshold=-20dB:ratio=2..3:attack=10:release=100` | 一致性 | 不要重压（压平 = 机械感） |
| 6. 重采样 + dither | `aresample=48000` + `dither_rect` | 量化噪声 | 48k/24bit 交付 |

**De-esser 的 FFmpeg 实现**（FFmpeg 无内置 deesser 滤镜，用侧链压缩近似）：

```powershell
# 齿音频段(5–8k)作侧链，压缩主信号对应成分
ffmpeg -y -i in.wav -filter_complex \
  "[0:a]asplit=2[a][key];[key]highpass=f=5000,lowpass=f=8000,acompressor=threshold=-35dB:ratio=4[kc];\
  [a][kc]sidechaincompress=threshold=0.05:ratio=3:attack=1:release=30[out]" \
  -map "[out]" out.wav
```

> 若追求专业去齿音/降噪，可 `pip install pedalboard`（Spotify 开源 DSP，自带 `DeEsser`、`LadderFilter`、`Limiter`），工具注册时标记可选依赖。

**⚠️ 反模式**：**禁止对整个音轨做宽带降噪**（`afftdn` 全段、noisereduce 全段）。audio-mixing-mastering 技能明确：宽带降噪会让 AI 伪影更糟，应做局部修复（逐句重生成、削 click、频谱修复）而非全局滤波。

### 层次 C：混音层（`tools/audio/audio_mixer.py`）

| 手法 | 作用 | 备注 |
|------|------|------|
| 极短而轻的 room reverb（`aecho`/`afir`，<100ms） | 让声音"坐进空间"，缓解干瘪机械感 | 讲解 VO 混响宁短勿长 |
| 克制 presence 提升 | audio-mixing-mastering 明确：aggressive presence boost 会让 AI 语音更假 | 若需要 3kHz 微提 ≤ +1dB |
| BGM 侧链 duck（`sidechaincompress`） | 音乐轻声压住 TTS 高频毛边，掩盖数码味 | 已有 `full_mix` 支持 |
| 底噪/呼吸处理 | 逐句手动清，不用全局降噪 | 见铁律 B |

---

## 7 优先级与落地路径

### 7.1 改动优先级排序

1. **P0（免费、纯调用侧、收益最大）**：情感策略分级（5.1）——不动任何源码即可实施，机械感下降最明显。
2. **P1（低代码、服务端透传）**：`repetition_penalty`、`num_beams`、`temperature` 透传 + A/B；`diffusion_steps` 25→50 透传（直接对抗数码味）。
3. **P2（中代码）**：输出采样率 24000 对齐、段间静音 100ms。
4. **P3（DSP）**：`audio_enhance` 新增 `tts_naturalize` 预设（高频柔和 + de-esser + limiter + dither），跑通后决定是否进入各流水线的 compose 阶段。
5. **P4（研究性）**：FP32 关键路径、CFG 微调、pedalboard 专业链。

### 7.2 A/B 实验矩阵

控制变量逐项验证，避免一次改多导致无法归因：

| 实验 | 变量 | 对照组 | 听感验收 |
|------|------|--------|----------|
| E1 情感 | 全 calm → 分级/自动 | 同文本同 ref | 起伏是否自然、有无突变 |
| E2 韵律 | penalty 10.0 → 1.1 | 同 E1 组 | 生硬感是否下降 |
| E3 采样 | beams 3 → 1, temp 0.8 → 0.65 | 同 E2 组 | 朗读腔是否减弱 |
| E4 扩散 | steps 25 → 50 → 100 | 同 E3 组 | 齿音/数码底噪是否下降 |
| E5 采样率 | 22050 → 24000 | 同 E4 组 | 高频是否更自然 |
| E6 DSP | 原始 → tts_naturalize | 同 E5 组 | 数码味 vs 清晰度权衡 |

每步保留频谱快照 + 波形对比，**盲听**（随机 AB，用户选更自然者）代替主观记忆对比。

### 7.3 与现有流水线规则的兼容性

- 逐句变速铁律（±5%）与后处理 DSP **不冲突**：DSP 只做频域/动态塑形，不改时长。
- 「零变速、零 atempo」规则不受影响。
- 情感策略改动**不影响** `indextts_server.py` 协议，可先纯调用侧落地。

---

## 8 验证策略

1. **频谱基线**：对当前合成样本生成 `showspectrumpic` 快照存档（含参考人声、改前、改后）。
2. **分频带能量表**：librosa 输出 5–8k / 8–11k 频带 RMS，量化数码味主频带变化。
3. **A/B 盲听**：每项实验 3 组样本，用户盲选，记录偏好比。
4. **端到端验收**：经 auto-dub 完整流程产出一段成品，B 站/耳机语感验收；确认无静音伪文件、无重叠、字幕对齐不回归。
5. **确定性回归**：同 seed + 同 ref 重试音色一致性不受参数透传影响（`torch.manual_seed` 逻辑不变）。

---

## 9 风险与约束

| 风险/约束 | 说明 | 对策 |
|-----------|------|------|
| 改 `infer_v2.py` 需与 `indextts_server.py` 两边同步 | 服务端黑盒化，改动契约需显式文档化 | 新增透传字段集中在 server 协议层，注释标明与 OpenMontage 侧 `resolve_emotion_mode` 同步 |
| `repetition_penalty=10.0` 可能是官方刻意设置 | 语义 token 与文本 token 的惩罚语义不同，直接降值可能引入文本重复 | **先 A/B 实验再决定**，禁止未验证直接上线 |
| FP16 回退 FP32 | VRAM 需求上升，可能触发 GPU 锁排队 | 仅关键路径回退；3090 24GB 可承载，16GB 卡谨慎 |
| 扩散步数上升 | 单句合成耗时线性上升，批量任务总时长增加 | 按需分级：短视频 50 步，高价值长片 100 步 |
| 采样率对齐 24000 | 涉及 s2mel sr、保存 sr、下游混音/字幕对齐的采样率一致性 | 改动后跑一次完整 auto-dub 端到端回归 |
| 后处理过度 | 高频衰减过多丢清晰度、饱和过度放大伪影 | DSP 链默认保守参数，出成品前听感验收 |
| 宽带降噪 | 让 AI 伪影更糟（audio-mixing-mastering 明确） | **禁止**，只做局部修复 |

---

## 10 参考

### 项目内文件
- `tools/audio/indextts_tts.py` — IndexTTS2 工具注册与 `resolve_emotion_mode` 三态情感语义
- `tools/audio/audio_enhance.py` — FFmpeg 音频增强预设（DSP 落点）
- `tools/audio/audio_mixer.py` — 混音/侧链 duck（层次 C 落点）
- `apps/auto-dub/config.yaml` — 逐句对齐、tempo_budget、chunk 等配置
- `skills/pipelines/localization-dub/lessons-learned.md` — 变速铁律、voice_ref 源头稳定克隆、合成重试策略
- `apps/auto-dub/batch/pipeline_automator.py` — 常驻服务桥与 GPU 锁
- `lib/gpu_lock.py` — 跨进程 GPU 互斥

### 模型仓库文件（`D:/index-tts/`）
- `indextts/infer_v2.py` — 推理主链（采样/解码/扩散/声码器参数）
- `indextts_server.py` — 常驻服务桥与音量归一化
- `checkpoints/config.yaml` — 模型/声码器/采样率配置

### 外部技能
- `audio-mixing-mastering`（全局技能）— 对话处理、限幅安全、禁止宽带降噪、presence 克制、AI 伪影局部修复原则
- `dialogue-editing-adr`（全局技能）— 对话修复与 ADR 定向原则（本报告未展开，落地阶段可补充参考）
