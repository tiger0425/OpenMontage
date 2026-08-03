# Idea Director — Vox Paper Collage

## 职责

执行 VOX 引擎 STATE 0/1/2：吸收可选的 Source Material PDF（若有），确定领域（niche），产出 10 个带钩子的视频选题，用户选定一个。产出 `brief` artifact。

## 输入

| 来源 | 处理方式 |
|------|----------|
| 用户提供 Source Material PDF（可选） | 吸收写作 DNA / 风格块 / 节拍规则 / 缩略图 DNA 覆盖内置默认（本管线 forge 时未附 PDF，使用内置默认） |
| 用户输入领域 | 走引擎 STATE 1 选项或自定义 |

## 流程

1. **可选源材料**：若用户提供 PDF，读取并吸收；无则用内置规则（本 skill 即内置默认）
2. **领域选择（STATE 1）**：向用户呈现引擎选项
   ```
   "What niche are we in today? Options:
   1. crime and documentary (house default)
   2. history
   3. money and power
   4. disasters and survival
   5. mysteries and the unexplained
   6. technology
   7. sports
   8. your own: type it
   Reply with a number or a niche."
   ```
3. **十选题（STATE 2）**：在该领域生成恰好 10 个选题。规则：
   - 没有两个选题落在同一子领域
   - 标题为陈述或疑问式，轻标点，无 clickbait。形状：`How [event] Unfolded`、`The Hunt for [target]`、`The [adjective] Story of [subject]`、`Why [place] [did X]`、`[Event] Explained`、`The Man/Woman Who [impossible act]`、`What Really Happened to [subject]`
   - 每个选题必须有具体钩子：日期、名字、数字或地点
4. **用户选择**：呈现编号列表，用户挑选一个（或描述不同话题）
5. 产出 `brief`

## 质量要求

- 标题无 em dash（用逗号/冒号/括号/普通连字符）
- 钩子必须具体（"November 24, 1971" 优于 "1970s"）
- 输出编号列表，无多余修饰

## 成功标准

- `brief` 含 niche、10 个候选选题（各带 hook）、用户选定项
