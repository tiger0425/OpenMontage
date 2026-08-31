# BGM 来源盘点

---
状态: closed
类型: wayfinder:research
指派: 绘图会话（子代理）
阻塞于: 无
---

## 问题

盘点成片 BGM 的可行走廊并给出推荐排序。

## 决议

详见 [findings/10-bgm-sources.md](../findings/10-bgm-sources.md)。要点：

- 库存现状：`music_library/` 仅 `ep01_bgm.mp3`（3.6MB，93.5 秒，不足 2 分钟需循环）
- music_generation 族三工具均需各自 key：music_gen(ELEVENLABS_API_KEY)、minimax_music(MINIMAX_API_KEY)、suno_music(SUNO_API_KEY)
- 推荐排序：A 库存/自备导入 > B 配 key 生成 > C 无 BGM 仅人声
- 情绪基调方向：温暖钢琴弦乐 / 极简 ambient / 轻快 pluck，一律无人声低强度
- 备注（绘图会话后更新）：MINIMAX_API_KEY 已配好，minimax_music 已随之解锁，走廊 B 的成本障碍对 MiniMax 一项已消除；选型仍待《中文 TTS 音色选型样音》同期试听定夺
