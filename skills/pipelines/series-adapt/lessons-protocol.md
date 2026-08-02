# Lessons Loop Protocol — series-adapt Pipeline

经验 → 规范闭环的"写"侧。读侧由 Rule Zero 保证（每阶段必读 director skill）；本协议保证每次生产跑完，新经验自动回流到规范文档，下一集自动继承。

## 何时触发

每次 `review` 阶段（`human_approval_default: true`）。Reviewer 与用户一起评审成片时，同时评审"本集学到了什么"。

## 审查问题（Reviewer 在最终评审时逐条自问）

1. 本集有没有**踩坑后绕过的**事？修复方法值得写进规范吗？（例：google_imagen 模型 ID 404 → 改用 gemini-3.1-flash-image）
2. 本集有没有**做对了但规范没写**的事？（例：分镜切在语音句子中间 → 规范只说了"语音是主时钟"没说怎么对齐）
3. 本集有没有**发现规范过时/错误**的地方？（例：rewrite 假设 150wpm，实测 183wpm）
4. 用户有没有给出**风格偏好**？（例：交叉溶解不要硬切、字幕卡拉OK高亮要保留、动效字要够大）
5. 有没有**值得沉淀的资产**？（例：6 个 ffmpeg 合成纸艺 SFX 配方）

## 输出格式

`final_review.json` 增加 `lessons` 数组，每条：

```json
{
  "id": "L-001",
  "episode": 1,
  "category": "pacing | motion | subtitles | audio | visuals | workflow | tooling",
  "what_happened": "一句话：本集发生了什么",
  "rule": "一句话规则：以后应当怎么做",
  "target_file": "skills/pipelines/series-adapt/scene-director.md",
  "target_section": "Step 2b: Scene windows follow VOICE BOUNDARIES",
  "approved": true
}
```

- `target_file` 必须是 `skills/`、`styles/`、`pipeline_defs/`、`apps/series-adapt/config.yaml` 下的真实路径
- 规则必须写成"以后怎么做"的祈使句，不能是"本集遇到了 X"的叙述
- `approved` 由用户在 review 审批时确认：同意才回写

## 回写动作（审批通过后，Reviewer 执行）

1. 按 `target_file`/`target_section` 定位文档
2. 把 `rule` 合并进对应章节——**优先合并进已有段落**，避免文档无限膨胀；同主题规则超过 5 条时归档到该文件的 `## Historical notes` 一节
3. 若规则涉及跨阶段（如 rewrite 词数影响 scene_plan），在相关各 director skill 各写一句互相引用
4. 更新 `final_review.lessons[].approved = true`，在 `final_review.summary` 里说明"已回写 N 条经验到 X"
5. 若规则只对单一剧集有效（不通用），标记 `approved: false` 并写进 `projects/<series>/<ep>/notes.md` 留存即可，不回写全局规范

## 防膨胀规则

- 单条规则 ≤ 2 句
- 优先合并进已有章节，不新建重复章节
- 每次回写前检查：`grep` 目标文档，若已有等价规则则跳过并记录"duplicate, skipped"
- 剧本类（配色/字号/音效/字幕）经验回写到 `styles/vox-collage.yaml`，不进 director skill

## 闭环验证（下一集怎么确认生效）

下一集执行到对应阶段时，agent 读到的 director skill 已含新规则。Reviewer 在下一集 review 时验证：`lessons` 中上一集的规则是否被遵守（抽查 1-2 条），没遵守的标注为 `regression` 并回写。
