# 08 — Stage 5 director: publish-director.md

**What to build:** 新建 `skills/pipelines/fabric-education/publish-director.md`，生成各平台发布文案和封面。

**Blocked by:** 03 (Pipeline manifest: fabric-education.yaml)

**Status:** ready-for-agent

- [ ] 遵循现有 `fabric-promotion/publish-copy-director.md` 的平台文案生成模式
- [ ] 产出标准 `publish_copy` artifact，覆盖 5 个平台：
  - **B站**：标题 ≤80 字，正文 300-500 字，标签 ≤10 个
  - **小红书**：标题 ≤20 字（可 emoji），正文 150-300 字，话题标签 5-8 个
  - **公众号**：标题、摘要、正文
  - **知乎**：标题、正文（科普/测评风格）
  - **朋友圈**：短文案 ≤150 字
- [ ] 封面图生成（通过 `image_selector` img2img）：
  - 小红书封面 3:4（1080×1440）
  - B站封面 16:9（1920×1080）
  - 封面文字层颜色/字体与面料调性一致
- [ ] 文案无夸张违禁词（绝对化用语、虚假宣称）
- [ ] 素材 100% 来自项目 assets/ 目录
