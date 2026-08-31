# 09 中文 TTS 音色选型（定案）

> 工单《TTS音色样音》产出（2026-08-25 用户听选定案）。

## 定案

- **音色：`D:/index-tts/my_voice.wav`**（4 个候选样音中用户选定，听感匹配柴米角色）
- 引擎：IndexTTS2.5，`use_emo_text=false`（纯净克隆，不传 emo_vector，防声纹漂移/女声化）
- 路由：`tts_selector` → `indextts_tts`（AGENTS.md 强制 selector 路由）
- 样音产物：`prototypes/tts-samples/sample_*.wav`（voice_05/09/11/my_voice 四候选，留档备查）

## 固定参数（管线资产阶段引用）

```python
# apps/indextts-bridge/client.py IndexTTSSession
voice_ref = "D:/index-tts/my_voice.wav"
model_version = "2.5"
lang = "ZH"
emotion = "calm"        # 纯净克隆，仅作默认；情绪调节走 use_emo_text 走廊（另议）
seed = 42               # 固定 seed 保跨集音色一致
```

## 备注

- 若后续柴米人设需更年轻/更沉稳，可从 `examples/voice_*.wav` 池再选，但**跨集不得混用多音色**（一致性铁律）。
- 重算力合成必须派 Compute Worker，`--json` 单行回报（对齐 auto-dub 契约）。
