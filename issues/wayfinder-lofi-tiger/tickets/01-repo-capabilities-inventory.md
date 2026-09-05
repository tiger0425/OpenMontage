# 本机与云端能力摸底与长循环技术预研

---
状态: done
类型: wayfinder:research
指派: 1293e4db
阻塞于: 无
---

> 已产出 `findings/01-repo-capabilities.md`

## 问题

为 lofi-tiger 管线摸清软硬件与工具链家底，重点评估 lofi 长时视频（1-3h）的四大技术支柱：

1. **音乐与音效能力**：
   - `minimax_music`（music-2.6）的 lofi 风格生成表现与参数控制（prompt、时长 30/60/120s）；
   - 仓库内氛围白噪音来源（`freesound_music`、`pixabay_music` 或本地库存音效）；
   - `audio_mixer` 对多轨混音（音乐 + 雨声/壁炉）的音量平衡与降噪处理。
2. **长音频无缝循环能力**：
   - 短乐段（如 1-2 分钟）如何通过 FFmpeg `acrossfade` 或类似音频平滑拼接算法消除首尾跳音，拼接成 1-3 小时连续长音频？
3. **视觉生成与微动能力**：
   - `minimax_image` 生成 16:9 横屏高清动漫/治愈场景的表现；
   - 视觉微动方案初探：MiniMax Video Direct（图生视频 5s/10s）首尾无缝平滑回环可行性，vs 静态背景 + HyperFrames/Canvas 粒子叠加。
4. **合成引擎性能瓶颈评估**：
   - 评估 1-3 小时 1080p 视频的渲染方案：为什么不能逐帧跑 HyperFrames/Remotion？FFmpeg `-stream_loop` 的资源消耗与渲染效率如何？

产出：`findings/01-repo-capabilities.md`
