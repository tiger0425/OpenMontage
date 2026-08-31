# 04 V2 风格规范与锚点沉淀（完成）

> 工单《V2 风格规范与锚点沉淀》决议（2026-08-26，AFK 任务票，已完成）。

## 产出物

| 文件 | 内容 |
|---|---|
| `styles/ref-remake.yaml` | 管线 playbook，**已通过 `schemas/styles/playbook.schema.json` 校验**。identity / visual_language / typography / motion / audio / asset_generation / quality_rules 全字段；V2 风格块（米白底 #FCFBF7 + 阿黄 60% 居中 + 1-3 点缀元素 + 防 3D/墨镜/堆砌）作为 `image_prompt_prefix` verbatim 模板 |
| `background_library/ref-remake/anchor/ahhuang_anchor.png` | 阿黄锚点图沉淀（源 `projects/times-you-almost-died-cn/assets/images/v2/01_opening_title.png`，复制 96987 字节） |
| `background_library/ref-remake/README.md` | 锚点使用规范：工具调用方式（`reference_image` 参数）、直调等价 payload、防漂移关键词清单、实测基线 |

## 关键定案

- **锚点落位**：管线级 `background_library/ref-remake/anchor/`（复用仓库既有惯例，同 wrc 的背景库），不复制进每个单集项目；单集项目内引用该路径。
- **playbook 来源**：`projects/healthy-body-cn/artifacts/visual_style_v2.md` + `character_consistency_guide.md` 提炼，风格块全文 verbatim 保留（不缩短/不改写）。
- **与工具对接**：锚点经工单《MiniMaxImage 工具补强 reference_image 参数》的工具参数传入（reference_instruction 默认文案与实测脚本一致）。
- **质检规则入 playbook**：无字底稿、主体 50%+ 居中、点缀 ≤3、眼镜透明镜片、422 敏感帧跳过、index.sample.html 清理、@font-face 中文声明、AI 标识角标、健康类措辞降级——全部写进 quality_rules。

## 与管线对接

- assets 阶段（见 findings/01）生图统一读 `styles/ref-remake.yaml` 的 `image_prompt_prefix` + `background_library/ref-remake/anchor/ahhuang_anchor.png`。
- review 阶段角色一致性质检对照锚点图（M3 抽帧）。
