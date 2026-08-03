# Publish Director — Vox Paper Collage

## 职责

执行 VOX 引擎 STATE 9（THUMBNAIL PROMPTS）：为成片生成 3 张缩略图（遵循 Thumbnail DNA，louder 处理），产出 `publish_log`。

## Thumbnail DNA（引擎逐字规则）

1. 与视频相同的新闻纸拼贴世界，但更响亮：更大的字、更热的红、更硬的对比，设计为 200 像素宽仍可读。
2. 构图：一个主导半色调主体剪贴（人物用黑色审查条遮眼——当暗示真实人物时；物体或地点），一到两个撕裂标签文字块（condensed all-caps，各 1-3 词，词选自视频钩子：EXPOSED、VANISHED、FOUND、年份、金额），一个红色或黄色高亮装置（粗糙记号笔圈、图章框或下划线），老报纸底，撕裂边缘出血出框。
3. 图中文字：最多 2 个文字元素，每个最多 3 词，巨大、condensed、全大写。
4. 16:9、超详细、高对比、无缩略图尺寸下消失的小细节、无 watermark、无 logos。

每个提示词以 STATE 7 的同一 CLOSER 结尾，其中 "no text beyond the specified label" 调整为 "no text beyond the specified thumbnail words"。

## 流程

1. 从 video hook 选 2-3 个短词（EXPOSED / VANISHED / FOUND / 年份 / 金额）
2. 写 3 个完整自足缩略图提示词：THUMBNAIL DNA 构图 + 调整版 CLOSER
3. 经 `image_selector` 生成 3 张图（google_imagen 首选；调用前读 Layer 3 技能）
4. 组装发布包：成片 + 3 张缩略图 + 元数据（标题、描述、标签）

## 质量要求

- 缩略图必须用调整版 CLOSER（thumbnail words），不是原 CLOSER
- 文字 ≤ 2 元素 × ≤ 3 词，巨大 condensed all-caps
- 200px 可读性检查（缩放预览）
- 无 em dash

## 成功标准

- `publish_log` 通过 schema 校验
- 3 张缩略图存在，遵循 Thumbnail DNA
- 发布包含成片与缩略图输出
