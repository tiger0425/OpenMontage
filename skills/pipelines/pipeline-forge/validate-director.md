# Validate Director — Pipeline Forge

## 职责

对 generate 的三件套做发布前验收，产出 `validation_report`。**全绿才允许向用户发布新管线**。本阶段需要人工审批（管线发布决策点）。

## 校验清单

### 1. Manifest schema 校验

```
python -c "
from lib.pipeline_loader import load_pipeline
m = load_pipeline('<slug>')   # 加载失败即红
print('OK', [s['name'] for s in m['stages']])
"
```

必须通过 `schemas/pipelines/pipeline_manifest.schema.json`（load_pipeline 内置校验）。

### 2. Playbook schema 校验

```
python -c "
import yaml, jsonschema, json
from pathlib import Path
with open('styles/<slug>.yaml', encoding='utf-8') as f:
    data = yaml.safe_load(f)
with open('schemas/styles/playbook.schema.json', encoding='utf-8') as f:
    schema = json.load(f)
jsonschema.validate(instance=data, schema=schema)
print('OK')
"
```

必填字段：identity / visual_language / typography / motion / audio / asset_generation / quality_rules。

### 3. Director skill 结构 checklist

- manifest 每个 stage 的 `skill` 路径对应的文件存在
- `required_skills` 中声明的全部 skill 存在
- `templates/` 目录包含 blueprint 要求的全部模板文件（style_block / closer / video_prompt / thumbnail_dna(如有) / music_prompt(如有)）

### 4. 模板逐字复核（红线）

- 对每个 templates/*.md，剔除文件头注释后与 style_dna 的 verbatim 块做 md5 对比
- 不一致 = 红 = 必须打回 generate

### 5. Harness 兼容检查

- `lib/checkpoint.py` 的 `CANONICAL_STAGE_ARTIFACTS` 覆盖新管线全部阶段名（非标准阶段名必须先加映射，否则 submit-artifact 会拒绝）
- 新管线 `default_checkpoint_policy` 为 manual_all
- `category` 在 schema 枚举内

## 产出 `validation_report`：

```json
{
  "version": "1.0",
  "slug": "<slug>",
  "checks": [
    {"name": "manifest_schema", "passed": true, "detail": ""},
    {"name": "playbook_schema", "passed": true, "detail": ""},
    {"name": "director_skill_structure", "passed": true, "detail": ""},
    {"name": "template_verbatim", "passed": true, "detail": "5/5 blocks match"},
    {"name": "harness_compatibility", "passed": true, "detail": ""}
  ],
  "overall": "pass | fail",
  "release_notes": "简要说明新管线能力"
}
```

## 质量要求

- 有任何红项 → overall fail → 打回 generate（或 map/extract 取决于问题根因）
- 人工审批时把 validation_report 与 release_notes 呈现给用户，等待"发布 / 打回"决定

## 成功标准

- `validation_report` 含全部 5 项检查结果
- 全绿后经人工审批，新管线发布
