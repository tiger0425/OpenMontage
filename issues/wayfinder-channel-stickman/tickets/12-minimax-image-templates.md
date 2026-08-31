# minimax 生图适配：场景背景生成（非模板）+ 品牌物料模板

---
状态: done
类型: wayfinder:research
指派: opencode 主会话
阻塞于: 无
---

> 定案（2026-08-25）：场景背景按内容逐场景生成（非模板），布局契约图 `prototypes/layout-diagram.html`（柴米 620px 中左偏中/对象中上偏右/字幕底部）；minimax 主路线验证通过（preferred_provider=minimax），imagen 备 429 额度耗尽待用户处理；背景 prompt 禁用 empty/plain 词。详见 `findings/12-scene-backgrounds.md`。

## 问题（2026-08-25 用户修正后范围）

**场景背景不是模板，是按内容逐场景生成**——画面必须与叙事匹配、与火柴人同框表达内容；一景一背景（空白背景+火柴人无法表达内容）。

修正后的分工：

1. **品牌物料**（logo C / banner / 封面 B）：继续用《imagen 无字底稿模板调研》的三套模板思路，适配 minimax 参数（aspect_ratio/width/height/seed）。
2. **场景背景（新增，主线）**：每集脚本的每个 scene，由 LLM 依据该 scene 的 narration 推导「无字背景 prompt」（场景主体+风格锁定+无文字约束）→ `image_selector`（minimax 主 / imagen 备）逐场景生成 → 火柴人 SVG 叠前景。
3. **验证**：
   - seed 固定能否带来跨场景/跨幕风格一致（imagen 无 seed，minimax 是核心收益）
   - 2-3 张样图对比 minimax vs imagen 对「扁平插画背景、无文字、留出火柴人站位」的服从度
   - 火柴人可读性：背景亮度/复杂度与黑色线条的对比规则

产出：场景背景生成流程（prompt 推导规范 + 合成规则 + 一致性策略）+ 品牌三模板 minimax 适配 + 对比结论。
