# 中文 TTS 音色选型样音

---
状态: done
类型: wayfinder:grilling
指派: opencode 主会话
阻塞于: 无
---

> 定案（2026-08-25 用户听选）：音色=`D:/index-tts/my_voice.wav`，IndexTTS2.5 纯净克隆 seed 42，tts_selector 路由。详见 `findings/09-tts-voice.md`；样音在 `prototypes/tts-samples/`。

## 问题

本机已配置 voxcpm / indextts / google_tts 三种中文可用 TTS。用同一段约 15 秒心理学旁白各生成一版样音，供人试听后拍板：

- 主音色与备用顺序
- 多集之间音色一致性的调用参数（固定 voice/seed 的方式）
- 语速与情绪基调（解说感 vs 陪伴感）

注意：本地 GPU TTS 走仓库 GPU 锁协议；样音文件路径记入决议。
