# Extract Director — Pipeline Forge

## 职责

从源文档全文解析"风格 DNA"，产出 `style_dna` artifact。**模板块逐字保留是本阶段的质量红线**：任何模板被缩短、改写、合并都会让下游生成的图/动画偏离引擎设定，EP 会在本阶段后做逐字核对。

## 风格 DNA 的 7 个组成部分

| 组成部分 | 说明 | 提取规则 |
|----------|------|----------|
| `role_declaration` | 文档开头的角色声明（"You are an Elite ..."） | 逐字 |
| `state_machine` | 状态列表 + 每个状态的指令（STATE 0 / STATE 1 ...） | 结构化：每状态 {id, title, instruction}；**"STOP. WAIT." 等交互边界保留** |
| `script_rules` | 脚本写作规则（字数数学、句子/节拍规则、结尾模式） | 提炼为可执行规则 + 保留原文引用 |
| `template_blocks` | 图像提示词模板块（STYLE BLOCK、CLOSER、缩略图 DNA 等） | **逐字，独立成块**，禁止任何编辑 |
| `video_prompt` | UNIVERSAL VIDEO PROMPT 全文 | **逐字**，独立成块 |
| `thumbnail_dna` | 缩略图规则（若有） | 逐字规则 + 模板 |
| `music_prompt` | 音乐提示词全文 | **逐字**（可能有多个变体） |

## 流程

1. 读取 `assets/source_document.txt` 全文
2. 按上表逐段提取，模板块存入 `template_blocks`（每块一个 key）
3. 对每个模板块，记录 `verbatim: true` 与源文本哈希（用于 validate 阶段复核）
4. 状态机提取时保留原文指令的**关键精确措辞**（如 "one input at a time"、"no skipping ahead"）——这些是引擎的交互契约，映射阶段会翻译为管线行为
5. 产出 `style_dna`：

```json
{
  "version": "1.0",
  "role_declaration": "verbatim text",
  "state_machine": { "form": "engine_state_machine", "states": [{"id": "STATE 0", "title": "...", "instruction": "..."}] },
  "script_rules": { "word_rate": 2.5, "duration_word_table": {...}, "rules": ["..."], "endings": ["..."] },
  "template_blocks": { "style_block": {"text": "...", "verbatim": true, "source_hash": "..."}, "closer": {...} },
  "video_prompt": {"text": "...", "verbatim": true, "source_hash": "..."},
  "thumbnail_dna": {...},
  "music_prompts": [{"text": "...", "verbatim": true}],
  "completeness_check": {"sections_found": ["..."], "sections_missing": []}
}
```

## 质量要求

- **逐字判定**：模板块必须与源文档对应段落逐字一致。宁可多保留（包括格式痕迹），不可少留
- **完整性自检**：对照源文档标题结构逐节核对，`sections_missing` 必须为空
- 源文档引用（`source_hash`）用简单哈希（如 md5 前 8 位）即可，供 validate 复核

## 成功标准

- `style_dna` 含全部 7 个组成部分（无对应内容的字段为 null 或空数组并注明）
- 所有模板块 `verbatim: true`
- `sections_missing` 为空
