# Ingest Director — Pipeline Forge

## 职责

接收风格引擎文档并规范化存档，为 extract 提供干净的全文输入。这是 forge 的第一阶段，产出 `ingest_log` artifact。

## 输入

| 来源类型 | 处理方式 |
|----------|----------|
| **URL** | Google Docs：`https://docs.google.com/document/d/<id>/export?format=txt`（已验证可行）。其他 URL：尝试抓取正文文本。失败时明确报错并给出手动方案 |
| **本地文件** | PDF / txt / md / docx：读取全文（PDF 需提取文本层，扫描件报错并建议用户转文本） |
| **粘贴文本** | 直接使用 |

## 流程

1. **识别来源类型**并读取全文
2. **判断文档形态**：
   - `engine_state_machine`：包含 "STATE 0 / STATE 1 ..." 或 "Follow the states in order" 等状态机标记（VOX / PAPERCUT 型）
   - `free_form_style_brief`：纯风格描述（无状态机）
3. **原文存档**：全文（含换行、编号、标记）写入项目工作区 `assets/source_document.txt`，**一字不改**。这是逐字抽取的溯源基准
4. **产出 `ingest_log`**：

```json
{
  "version": "1.0",
  "source_type": "url | file | paste",
  "source_ref": "原始 URL 或文件路径",
  "document_form": "engine_state_machine | free_form_style_brief",
  "archived_path": "assets/source_document.txt",
  "char_count": 12345,
  "state_count": 10,
  "notes": []
}
```

## 质量要求

- 原文存档必须与源文档逐字一致（这是 extract 逐字保留判定的基准）
- state_count 仅对状态机形态有意义；free_form 填 0
- 归档失败 = 阶段失败，不进入 extract

## 成功标准

- `ingest_log` 含 source_type、archived_path、document_form
- 存档文件存在且非空
