# lofi 音乐与环境白噪音长时无缝循环技术方案

---
状态: done
类型: wayfinder:research
指派: 1293e4db
阻塞于: 无
---

> 已产出 `findings/04-audio-loop-ambience.md`

## 问题

解决 lofi 长视频的核心声学工程问题——如何产出平稳、治愈、无接缝突兀感的 1-3 小时高质量音频流：

1. **基础乐段生成**：
   - 验证 `minimax_music`（music-2.6）在 lofi 风格（lofi hip hop, dusty chillhop, mellow Rhodes piano, vinyl crackle, gentle drums）上的质量与可用性；
   - 评估生成单段 120s 乐段 vs 批量生成 3-5 首不同段落（形成专辑轮播感）的策略对比。
2. **环境声音白噪音融合**：
   - 获取高品质无版权环境白噪音（雨声、壁炉火星、远雷、微风）；
   - 利用 `audio_mixer` 实现分轨无损混音，确定最佳混音比例（如音乐 70% + 雨声 30%），消除频段冲突。
3. **音频无缝循环（Crossfade Loop）算法**：
   - 设计 FFmpeg 自动化交叉淡化脚本：设定合理的淡化区间（例如 2.5s~5s `acrossfade`），测试消除循环接缝处瞬态失真（clicks/pops）的最佳参数；
   - 实现将 120s 或多段乐段无缝扩展至 60 分钟 / 180 分钟的批处理命令行。
4. **响度标准化（Loudness Normalization）**：
   - 对齐 YouTube 官方推荐的音频响度标准（-14 LUFS，True Peak ≤ -1 dBTP），防止音量忽大忽小或被 YouTube 强行压缩衰减。

产出：`findings/04-audio-loop-ambience.md`
