# imagen 无字底稿模板调研

---
状态: closed
类型: wayfinder:research
指派: 绘图会话（子代理）
阻塞于: 无
---

## 问题

为 AI 生图环节起草无字底稿 prompt 模板与参数规范（竖屏背景 / 封面 / logo 三套），并摸清 google_imagen 能力边界。

## 决议

调研完成，详见 [findings/05-imagen-template.md](../findings/05-imagen-template.md)。要点：

- google_imagen 实际是 Gemini Flash(Lite) 图像模型 + 纯 prompt 输入；aspect_ratio/张数等参数被静默忽略，无 seed、无负面词
- 竖屏与跨幕一致性只能靠模板技巧补齐（调研已给出三条竖屏策略）
- 三套模板就绪：竖屏背景 A / 封面 B / logo C，含公共风格锚定块与硬约束块，附 11 项试点期验证清单
- 后续：生图改为 minimax 主 + imagen 备的双路（见绘图会话决议），minimax_image 的模板适配另开工单
