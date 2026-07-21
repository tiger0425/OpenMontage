# 06 — Stage 2 director: notes-director.md

**What to build:** 新建 `skills/pipelines/fabric-education/notes-director.md`，将 fabric_edu_brief 转化为多平台适配的图文笔记（note_manifest）。

**Blocked by:** 05 (Stage 1 director: brief-director.md)

**Status:** ready-for-agent

- [ ] 核心长文生成：基于 brief 写一篇完整的面料知识长文（Markdown），包括：
  - 面料基本介绍
  - 常见误区/坑（brief.pitfalls）
  - 辨别方法（可配图说明）
  - 使用建议和保养
- [ ] 四个平台版本适配：
  - **小红书**：≤1000 字，封面 3:4，标题有 emoji 和钩子，正文图文混排
  - **公众号**：深度长文无字数限制，可引用更多背景知识，可含购买引导
  - **知乎**：偏测评/科普风格，有数据支撑或行业经验背书
  - **朋友圈**：≤150 字，引导语指向其他平台看全文
- [ ] 配图生成指引：
  - 按知识点需要决定配图类型（微距/对比/示意图/测试场景）
  - 所有配图通过 `image_selector` 以面料原图为底图（img2img）生成
  - 配图目的为说明知识点，非展示美感
  - 每张图打 `educational_role` 标签
- [ ] 产出 `note_manifest` artifact，校验 schema
- [ ] Truth-Gate：笔记内容忠于 fabric_facts，不虚构知识点
