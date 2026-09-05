# 视觉微动母本方案选型与技术预研

---
状态: done
类型: wayfinder:research
指派: 1293e4db
阻塞于: 无
---

> 已产出 `findings/05-visual-micro-loop.md`

## 问题

针对 lofi 长视频「画面微动、静中有动、长时间观看无视觉跳变与疲劳」的视觉要求，对比并确定视觉微动母本（10s~30s）的最佳生产路径：

1. **路径 A：AI 图生视频（Image-to-Video Loop）**
   - 使用 `minimax_image` 生成超高清 16:9 静态母图；
   - 调用 `minimax_video_direct` 或 FAL Kling 生成 5s~10s 微动视频（要求极小幅度呼吸、眨眼、窗外雨景）；
   - 使用 FFmpeg 将 5s 视频前后半段做交叉淡化合成（Crossfade Blend），实现 100% 绝对平滑首尾相连的无缝 loop MP4。
2. **路径 B：静态背景 + 程序化微动（HyperFrames / Canvas Layer）**
   - 静态背景由 AI 生成；
   - 利用 HyperFrames / GSAP / Canvas 渲染透明微动层（下雨、玻璃流淌雨滴、咖啡冒热气、灯光呼吸微闪烁、飘落树叶）；
   - 角色采用半动态图层叠加或程序化呼吸轻微缩放。
3. **两路实测对比与选型**：
   - 画面治愈度与自然感评估（AI 原生视频 vs 粒子叠加）；
   - 循环平滑度与跳跃感；
   - 算力成本与生成时长对比；
   - 给出推荐主选与备选路径。

产出：`findings/05-visual-micro-loop.md`
