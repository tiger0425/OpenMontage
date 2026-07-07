---
name: voxcpm-tts
description: |
  本地 GPU 语音合成（VoxCPM2）的使用指南，涵盖多段音色一致性、参数调优、以及在 OpenMontage pipeline 中正确调用的完整流程。
  触发条件：使用 voxcpm_tts 工具、需要离线 GPU TTS、需要中文语音合成、需要保证多段配音音色一致。
---

# VoxCPM TTS — Agent 使用指南

VoxCPM2 是本地 GPU 语音合成工具，支持中文/多语言，48kHz 高质量输出，完全离线运行。
工具路径：`tools/audio/voxcpm_tts.py`，通过 `tts_selector` 或直接调用均可。

---

## ⚠️ 最关键规则：多段音色一致性

VoxCPM2 是**自回归扩散模型**（LocEnc → TSLM → RALM → LocDiT）。
每次生成消耗的随机状态数与文本长度相关，不同文本长度会产生不同音色。
**官方文档明确说明：** *"Voice Design results may vary between runs"*

### 唯一可靠方案：参考音频链式克隆

```
第 1 段  →  生成  →  保存为 voice_ref.wav
第 2 段  →  reference_wav_path=voice_ref.wav  →  生成（音色与第1段一致）
第 3 段  →  reference_wav_path=voice_ref.wav  →  生成（音色与第1段一致）
...
```

**标准调用模式（Pipeline 中必须遵守）：**

```python
from tools.audio.voxcpm_tts import VoxCPMTTS

tool = VoxCPMTTS()

# ── 第 1 段：正常生成，seed=42 自动生成声音锚点 ──
r1 = tool.execute({
    "text": "第一段旁白文字。",
    "output_path": "projects/my-video/assets/audio/seg_01.wav",
    "voice_description": "温暖成熟的男性配音员，语调沉稳",  # 可选，描述音色风格
    "seed": 42,        # 固定 seed → 工具内部生成并缓存声音锚点
})
assert r1.success
voice_ref = r1.data["output"]  # 保存第 1 段路径作为后续参考

# ── 第 2、3...段：显式传入第 1 段作为 reference_wav_path ──
segments = [
    ("第二段旁白文字。", "seg_02.wav"),
    ("第三段旁白文字。", "seg_03.wav"),
]
for text, filename in segments:
    r = tool.execute({
        "text": text,
        "output_path": f"projects/my-video/assets/audio/{filename}",
        "reference_wav_path": voice_ref,   # ← 关键：始终引用第 1 段
    })
    assert r.success
```

---

## 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `text` | str | 必填 | 要合成的文字 |
| `output_path` | str | `voxcpm_output.wav` | 输出 WAV 路径（48kHz） |
| `reference_wav_path` | str | — | **多段一致性关键参数**。传入后以声音克隆模式生成，音色锁定到此文件 |
| `voice_description` | str | — | 自然语言音色描述，仅在无 `reference_wav_path` 时生效（用于第1段的锚点生成） |
| `seed` | int | `42` | 控制内部声音锚点生成的随机种子。`-1` = 每次随机，不建议多段使用 |
| `cfg_value` | float | `3.0` | 扩散引导强度，无需调整 |
| `inference_timesteps` | int | `10` | 扩散步数，`10` 是官方推荐值，速度与质量的最优平衡 |

---

## 音色风格（voice_description）写法

`voice_description` 在括号内作为前缀插入文本，引导模型生成对应音色。仅对**第 1 段**（无 reference 时）有效。

**推荐写法：**

| 风格 | 描述示例 |
|---|---|
| 专业男声 | `"温暖成熟的男性配音员，语调沉稳，清晰有力"` |
| 活泼女声 | `"年轻活泼的女性主播，语速适中，充满活力"` |
| 新闻播报 | `"标准普通话播音员，语调平稳，字正腔圆"` |
| 知识讲解 | `"耐心的科普讲解员，语速稍慢，亲切易懂"` |

**不要写：** `"a voice"` / `"好的声音"` — 太模糊，模型无法有效响应。

---

## 性能参考

| 阶段 | 耗时（RTX 4090） | 说明 |
|---|---|---|
| 模型加载（首次） | ~15s | 8GB 权重，进程内缓存，只加载一次 |
| 声音锚点生成（首次） | ~80s | 存储到 `%TEMP%/voxcpm_anchors/`，后续进程直接读取 |
| 正常生成（每段） | 10~30s | 取决于文本长度 |
| 声音克隆（reference_wav_path）| 10~30s | 与正常生成相当，无额外开销 |

> **注意：** 首段因包含模型加载+锚点生成约需 100s，第 2 段起约 10~30s。

---

## 在 Pipeline 的 Assets 阶段使用

Asset director 调用 TTS 时，遵循以下顺序：

```
1. 读取 script 的所有 narration 分段
2. 用第 1 段调用 voxcpm_tts（无 reference_wav_path）
3. 保存第 1 段路径为 voice_ref
4. 循环其余分段，全部传入 reference_wav_path=voice_ref
5. 检查每段 r.success，失败则重试或上报 blocker
```

输出路径规范：`projects/<project>/assets/audio/seg_NN.wav`

---

## 常见错误

| 现象 | 原因 | 解决 |
|---|---|---|
| 多段音色不一致 | 没有传 `reference_wav_path` | 第2段起必须传第1段路径 |
| `Badcase detected, retrying...` | 在 `prompt_text` 传入了错误转写 | **不要**传 `prompt_wav_path`/`prompt_text` 参数，工具本身不使用它们 |
| `VoxCPM TTS not available` | 没有 CUDA GPU 或未安装 voxcpm | 检查 `torch.cuda.is_available()`，或改用 ElevenLabs TTS |
| 生成音频过长或乱码 | 文本包含特殊符号或过长 | 单段建议不超过 200 字，特殊符号转义 |
