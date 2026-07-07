# 面料推广 - Retrospective Director（自我学习与复盘）v4.0

> v3.0 新增。每次流水线跑完后采集本次的经验，沉淀到 `.retrospectives/fabric-promotion/`
> 知识库，下一次启动时 idea / visual_planning stage 必读 `.retrospectives/latest.md`，
> 让本条流水线在多次运行后真正"越用越准"。

## 角色

音频/视频关闭、文案落地之后，让 agent 给本次运行做一次复盘：

- 哪些步骤做对了，下一轮继续保留
- 哪些步骤踩坑了，下一轮规避
- 哪些参数调过值后效果更好，下一轮默认用新值
- 哪些关键决策与理由（避免下次重新争论同一问题）

输出落到两个位置：

1. `artifacts/retrospective.json` — 标准 artifact（可被 schema 校验）
2. `.retrospectives/fabric-promotion/<project>.md`  — 人类可读复盘日记
3. `.retrospectives/latest.md`  — 软链接 / 副本，指向最近一次

## 输入

- `brief`（含 budget / render_runtime_selection 决策）
- `scene_plan.json`
- `script.json`
- `visual_design.json`
- `frame_blueprint.json`
- `asset_manifest.json`（含 img2img_source 与生成时长）
- `edit_decisions.json`
- `render_report.json`（含 tool_invocation 与 self_review）
- `publish_copy.json` 与 `cover_manifest.json`
- 实际 cost_tracker 日志（pipeline 真实成本）
- 实际 wall-clock time per stage（来自 checkpoints）
- `.retrospectives/previous.md`（如果本次启动时 hits 同面料 / 同平台历史）

## 强制流程

### Step 1: 统计本次实际数据

```python
# 阶段实际耗时
stage_times = {
    stage: checkpoint[stage].finished_at - checkpoint[stage].started_at
    for stage in ["idea", "visual_planning", "directed_assets",
                  "hyperframes_compose", "publish_copy"]
}

# 实际成本
real_cost = cost_tracker.snapshot()

# 与 brief 预算的超/省
delta = real_cost.total_usd - budget_default_usd
```

### Step 2: 扫描 review_focus 命中情况

把 YAML 各 stage 的 review_focus 列表逐条对照本次 agent 实际行为：

```python
review_foci = yaml评审 focus from manifest
hits = []
for stage, foci in review_foci.items():
    for focus in foci:
        actual_behavior = extract_from_run_log(stage, focus)
        status = "honored" | "violated" | "missed"
        if status != "honored":
            hits.append({
                "stage": stage,
                "focus_rule": focus,
                "status": status,
                "evidence": actual_behavior,
                "fix_required": True/False,
            })
```

违反项与遗漏项全部入 retrospective.pitfalls。

### Step 3: 抓 render_report 关键标记

```python
audit = render_report.get("tool_invocation", {})
self_review = render_report.get("self_review", {})
red_flags = []

# AGENTS.md #4 红线：NO SINGLE-SHOT HTML GENERATION
if not audit.get("tool") == "hyperframes_compose":
    red_flags.append("CRITICAL #4: 合成阶段未走项目内 hyperframes_compose 工具")
if self_review.get("passed") is not True:
    red_flags.append("CRITICAL: post-render self-review 未通过")

# 标准 artifact 校验
if not Path("artifacts/edit_decisions.json").exists():
    red_flags.append("CRITICAL: edit_decisions.json 缺失")
```

### Step 4: 提取可调参数（tunables）

收集本次各 frame 实际用的参数与效果，找出"如果调一下会更好"的项：

```python
tunables = []
for frame in frame_blueprint.frames:
    rendered_quality = assess_frame_quality(render_report, frame.frame_id)
    if rendered_quality == "weak" and frame.asset_kind == "garment_video":
        tunables.append({
            "frame_id": frame.frame_id,
            "parameter": "comfyui_denoise_strength",
            "current": 0.85,
            "suggestion": 0.9,
            "rationale": "面料细节偏糊；下次同类克重试 0.9 保留更多原图信息"
        })
    if rendered_quality == "drift" and frame.asset_kind == "garment_video":
        tunables.append({
            "frame_id": frame.frame_id,
            "parameter": "comfyui_steps",
            "current": 12,
            "suggestion": 14,
            "rationale": "动作飘移；增加步数以提升运动一致性"
        })
```

### Step 5: 归档决策与理由

把本次 pipeline 中真正影响产出形态的决策点写入 retrospective.decisions：
- render_runtime 的 options_considered 与最终选定 + 理由
- design_system 调色板取色策略（如"亚麻暖调 + 银白点缀"）
- 字体选择（如 Outfit for subhead / Playfair Display for headline）
- visual_design.json 的 lighting_style / global_mood 选择
- TTS voice_id（voxcpm 的具体 voice）
- comfyui workflow_path（ltx23_i2v 等）
- OpenMontage profile 选择（bilibili → youtube_landscape / xiaohongshu → tiktok_vertical）

理由必填，避免下次 agent 再争论一次。

### Step 6: 写入 knowledge base（人类可读 markdown）

```
.retrospectives/fabric-promotion/<project-name>.md
────────────────────────────────────────────────────
# 复盘：<project-name>
日期：YYYY-MM-DD
面料类型：<如真丝 / 亚麻 / 棉 / 天鹅绒>
目标平台：<bilibili / xiaohongshu>
总时长：<秒>
实际成本：$ X.XX（预算 $ Y.YY，偏差 Z%）

## ✅ 做对了什么 (wins)
- <逐条记录表现好的>

## ⚠️ 踩坑了什么 (pitfalls)
- [Stage_name / Review focus rule] <事实描述 + 修复方法 + 是否落实>

## 🔧 可调参数 (tunables)
- <frame_id>.<parameter>: <current_value → suggestion>，理由：…

## 🎯 关键决策 (decisions)
- render_runtime: <chosen> ✓（候选 <rejected[]>）— 理由：…
- 字体策略: <family / weight>，理由：…
- HyperFrames template: <name>，理由：…
- TTS voice: <provider.id>，理由：…

## 🚀 改进点 (improvements)
- <给下次 pipeline 启动者的一句行动建议>

## 📦 附 artifacts 路径
- artifacts/scene_plan.json
- artifacts/script.json
- artifacts/visual_design.json
- artifacts/frame_blueprint.json
- artifacts/asset_manifest.json
- artifacts/edit_decisions.json
- artifacts/render_report.json
- artifacts/publish_copy.json
- artifacts/cover_manifest.json
- renders/final.mp4
────────────────────────────────────────────────────
```

### Step 7: 刷新 `.retrospectives/latest.md`

把新写的复盘 markdown **拷贝** 为 `.retrospectives/latest.md`（软链接也可以，但 Windows
扫不开软链，写副本更稳）。下次启动 fabric-promotion pipeline 时，`idea-director` 与
`visual-planning-director` 先读它：

```python
# idea-director 启动时
latest_retro = read(".retrospectives/latest.md", fallback=None)
if latest_retro:
    if latest_retro.fabric_type == current_brief.fabric_type:
        brief.tunables_inherited = latest_retro.tunables
        print(f"📚 已继承上轮 retrospective：{latest_retro.date} · {latest_retro.fabric_type}")
    else:
        print(f"📚 上轮 retrospective 与本面料类型不符，无 tunables 继承")
```

## 输出

### `artifacts/retrospective.json`

```json
{
  "version": "3.0",
  "pipeline": "fabric-promotion-directed",
  "project_name": "<project-name>",
  "fabric_type": "<如 cotton/silk>",
  "target_platform": "<bilibili/xiaohongshu>",
  "duration_total_seconds": 30,
  "real_cost_usd": 0.92,
  "budget_usd": 3.00,
  "delta_cost_pct": -69.3,
  "stage_times_seconds": {
    "idea": 122,
    "visual_planning": 184,
    "directed_assets": 1342,
    "hyperframes_compose": 2104,
    "publish_copy": 86
  },
  "wins": [
    "...",
  ],
  "pitfalls": [
    {
      "stage": "hyperframes_compose",
      "focus_rule": "CRITICAL #4: 发现一次性写出 index.html 即视为 critical 失败",
      "status": "honored",
      "evidence": "frame HTML 拆为 5 个文件，无一次性写 index.html"
    }
  ],
  "tunables": [
    {"frame_id": "f3_garment_a_video", "parameter": "comfyui_denoise_strength",
     "current": 0.85, "suggestion": 0.9, "rationale": "..."}
  ],
  "decisions": [
    {"decision": "render_runtime",
     "selected": "hyperframes",
     "rejected": ["remotion"],
     "rationale": "CSS/GSAP 排版符合面料推广产品感呈现"}
  ],
  "improvements": [
    "下次亚麻面料建议 visual_planning Strength 提高 0.05"
  ],
  "artifacts_paths": {
    "scene_plan": "artifacts/scene_plan.json",
    "script": "artifacts/script.json",
    "visual_design": "artifacts/visual_design.json",
    "frame_blueprint": "artifacts/frame_blueprint.json",
    "asset_manifest": "artifacts/asset_manifest.json",
    "edit_decisions": "artifacts/edit_decisions.json",
    "render_report": "artifacts/render_report.json",
    "video": "renders/final.mp4",
    "publish_copy": "artifacts/publish_copy.json",
    "cover_manifest": "artifacts/cover_manifest.json"
  }
}
```

### `.retrospectives/fabric-promotion/<project>.md`

按 Step 6 模板的人类可读 markdown。

### `.retrospectives/latest.md`

最新一份的副本。

## Reviewer Self-Review

- [ ] retrospective.json schema 合法，含全 5 个必填字段：wins / pitfalls / improvements / decisions / tunables
- [ ] .retrospectives/fabric-promotion/<project>.md 已落盘
- [ ] .retrospectives/latest.md 已刷新（content 为最新本次）
- [ ] stage_times 已识别耗时最长的 stage，并在 improvements 给出优化提示
- [ ] pitfalls 列表覆盖本次 review_focus 全部 violated / missed 项
- [ ] decisions 列表至少含 render_runtime / 字体 / visual_design / TTS_voice 4 项
- [ ] tunables 列表对每个失败帧给出 current→suggestion 与 rationale
- [ ] artifacts_paths 引用全部存在于磁盘
- [ ] 修正动作可机器解析（下轮 idea-director 能读 .retrospectives/latest.md 自动继承 tunables）

## 与其他 stage 的契约

- 上游：idea / visual_planning / directed_assets / hyperframes_compose / publish_copy
- 下游：下次同 pipeline 启动时，idea-director 与 visual-planning-director
  必读 `.retrospectives/latest.md`，把其中的 tunables 注入到新一次
  frame_blueprint

## 失败场景

- 若上游某 stage 失败未产出 artifact：本 stage 仍可跑，但只记录本次实际状态
  在 pitfalls，输入缺失项放 `missing_artifacts: [...]`，不让 retrospective 失败。
- 若实际拍摄素材不存在（用户跑一半删除）：在 wins 末尾记录"asset 已损坏"
  在 pitfalls 中标注，写 retrospective 但不写 tunables。

## 反模式

- ❌ 把 retrospective 写成笼统的"做得不错、有点不够" — 必须具体到 stage / frame_id / parameter
- ❌ tunables 不给 rationale — 下次启动不知道该不该再调一次
- ❌ decisions 不写 rejected 选项 — 下轮还会争论同一问题
- ❌ latest.md 不刷新，老经验覆盖新经验