# 面料推广 - Compose Director（HyperFrames 合成总监）v4.0

## 角色

把 STAGE 2/3 产出的 OpenMontage 标准 artifacts 翻译成 `edit_decisions.json`，然后调用**项目内** `tools/video/hyperframes_compose.py` 的 `hyperframes_compose` 工具完成合成。

> v4.0 彻底纠正 v3.2 的错误：v3.2 委托外部系统 skill `product-launch-video`，引用 `<HF_SKILL_DIR>/scripts/build-frame.mjs` / `stage-assets.mjs` / `assemble-index.mjs` 等虚构/外部 API，实际跑会全失败。v4.0 只走 OpenMontage 原生工具：标准 `edit_decisions` + `asset_manifest` + `playbook` → `hyperframes_compose`。

**核心红线**（违反任一即 critical）：
- 不手写任何 HTML，不一次性写 `index.html`
- 不调用外部 HyperFrames skill 的脚本
- 不修改 `brief.render_runtime`（已锁）
- 不在本 stage 重新做视觉设计

> **⚠️ 路径规范核心警告**：  
> Universal Harness (omo.py) 始终在 OpenMontage 根目录执行！因此所有针对项目内工件的读取/写入（如 `artifacts/...`, `renders/...`）以及工具调用的参数路径，都**必须带有 `projects/{project_name}/` 前缀**。切勿直接写 `artifacts/` 或 `hyperframes`，否则会污染根目录！

## 输入

- `brief`（`render_runtime` 已锁定，本 stage 只读）
- `artifacts/scene_plan.json`
- `artifacts/script.json`
- `artifacts/visual_design.json`
- `artifacts/frame_blueprint.json`
- `artifacts/asset_manifest.json`
- 当前激活 playbook（如 `styles/clean-professional.yaml` 或 `flat-motion-graphics.yaml`）

## 输出

- `artifacts/edit_decisions.json`（`edit_decisions.schema.json`）
- `artifacts/render_report.json`（`render_report.schema.json`）
- `renders/final.mp4`

## 强制流程

### Step 0: 强制读取上游 Artifacts 并回显（防漂移红线）
为了绝对防止在大模型跨 Session 运行中出现“对上游决策不知情而自由发挥”的问题，你**必须首先调用文件查看工具读取以下上游 Artifacts 文件的实际内容**：
* `projects/{project_name}/artifacts/brief.json`
* `projects/{project_name}/artifacts/frame_blueprint.json`
* `projects/{project_name}/artifacts/scene_plan.json`
* `projects/{project_name}/artifacts/script.json`
* `projects/{project_name}/artifacts/visual_design.json`
* `projects/{project_name}/artifacts/asset_manifest.json`

在执行后续的合成步骤之前，你**必须首先在回复中以 Markdown 表格的形式回显（Print）出上游的核心决策与匹配关系**，包括：
1. 每一帧的 `frame_id` 及其在 `asset_manifest.json` 中匹配的实际物理文件路径
2. 约定的 `render_runtime` 选项（必须与 `brief.json` 中的 render_runtime_selection 对齐）
3. 设计系统中约定的全局 `palette` 颜色白名单及 `typography` 字体设置
4. 每一帧对应的配音文本与物理音频文件的对齐状态

**⚠️ 绝对违规警示**：如果在未通过工具读取并以 Markdown 表格回显上述上游契约数据的情况下，直接编写 edit_decisions 或调用合成工具（hyperframes_compose），将被视为重大运行违约。

### 阶段 A：契约校验

```python
import json
import os
from pathlib import Path
from schemas.artifacts import validate_artifact

# 请自行替换为实际的项目名
project_name = "<project_name>"
project_dir = Path(f"projects/{project_name}")

def _load_json(path: str) -> dict:
    with open(project_dir / path, encoding="utf-8") as f:
        return json.load(f)

brief = _load_json("artifacts/brief.json")
scene_plan = _load_json("artifacts/scene_plan.json")
script = _load_json("artifacts/script.json")
visual_design = _load_json("artifacts/visual_design.json")
frame_bp = _load_json("artifacts/frame_blueprint.json")
asset_manifest = _load_json("artifacts/asset_manifest.json")

assert brief["metadata"]["render_runtime_selection"]["selected"] == "hyperframes", \
    "本 pipeline 仅服务 HyperFrames runtime；若要切换，回 idea stage 重批"

assert len(frame_bp["frames"]) > 0, "frame_blueprint 至少一帧"
assert all(f.get("frame_id") for f in frame_bp["frames"]), "每帧必须有 frame_id"

asset_lookup = {a["id"]: a for a in asset_manifest["assets"]}
linked_ids = {a["linked_frame_id"] for a in asset_manifest["assets"] if a.get("linked_frame_id")}
missing = [f["frame_id"] for f in frame_bp["frames"] if f["frame_id"] not in linked_ids]
assert not missing, f"asset_manifest 缺帧素材：{missing}"

# 校验 OpenMontage 标准 artifacts
for artifact_name, path in [
    ("scene_plan", "artifacts/scene_plan.json"),
    ("script", "artifacts/script.json"),
    ("visual_design", "artifacts/visual_design.json"),
    ("asset_manifest", "artifacts/asset_manifest.json"),
]:
    data = _load_json(path)
    validate_artifact(artifact_name, data)

# 校验 scene_plan 与 script 总时长一致
sp_total = max(s["end_seconds"] for s in scene_plan["scenes"])
sc_total = script["total_duration_seconds"]
assert abs(sp_total - sc_total) < 0.5, f"scene_plan 总时长 {sp_total} 与 script {sc_total} 不一致"
```

任一失败 → critical finding，**禁止继续**。

### 阶段 B：生成 edit_decisions.json

`edit_decisions` 是 OpenMontage 合成阶段标准 artifact，必须满足 `edit_decisions.schema.json`。每个 `frame_blueprint` 的帧对应一个 `cut`。

```python
edit_decisions = {
    "version": "1.0",
    "render_runtime": "hyperframes",
    "renderer_family": "product-reveal",
    "cuts": [],
    "audio": {
        "narration": {"segments": []},
        "music": None
    },
    "subtitles": {
        "enabled": False,
        "style": "sentence"
    }
}

for i, frame in enumerate(frame_bp["frames"]):
    # 找到本帧对应的 asset（优先 garment_image / garment_video）
    frame_assets = [a for a in asset_manifest["assets"] if a.get("linked_frame_id") == frame["frame_id"]]
    primary = next(
        (a for a in frame_assets if a["kind"] in ("garment_image", "garment_video", "fabric_macro_video", "cover_base_image")),
        None
    )
    if not primary:
        primary = frame_assets[0]

    cut = {
        "id": frame["frame_id"],
        "source": primary["id"],  # OpenMontage 工具通过 asset_id 解析路径
        "in_seconds": frame["time_range"]["start"],
        "out_seconds": frame["time_range"]["end"],
        "type": frame["asset_kind"],
        "layer": "primary",
        "transform": {
            "scale": 1.0,
            "position": "center",
            "animation": _animation_from_motion(frame.get("motion_rules", []))
        },
        "transition_in": _map_cut_in(frame.get("cut_in", "")),
        "transition_duration": _cut_duration(frame.get("cut_in", "")),
        "reason": f"frame {frame['frame_id']}: {frame.get('composition_rule', '')}"
    }
    edit_decisions["cuts"].append(cut)

    # 文字叠加层：把 blueprint 里的 text_overlay 传给 edit_decisions cut
    if frame.get("text_overlay"):
        to = frame["text_overlay"]
        overlay_text = ""
        pos = "bottom_left"
        if isinstance(to, dict):
            overlay_text = to.get("text") or to.get("title") or to.get("badge") or ""
            pos = to.get("position") or "bottom_left"
            if not overlay_text and "specs_card" in to:
                sc = to["specs_card"]
                if isinstance(sc, dict):
                    overlay_text = " · ".join(sc.values())
        else:
            overlay_text = str(to)
            
        if overlay_text:
            cut["text_overlay"] = {
                "text": overlay_text,
                "position": pos
            }

    # narration 段：每个 tts_segment_id 对应 script.sections 一段
    if frame.get("tts_segment_id"):
        nar_asset = next(
            (a for a in frame_assets if a["kind"] == "narration_wav"),
            None
        )
        if nar_asset:
            edit_decisions["audio"]["narration"]["segments"].append({
                "asset_id": nar_asset["id"],
                "start_seconds": frame["time_range"]["start"],
                "end_seconds": frame["time_range"]["end"]
            })

# 全局音乐：若 asset_manifest 中有 music 类型
music_assets = [a for a in asset_manifest["assets"] if a["type"] == "music"]
if music_assets:
    edit_decisions["audio"]["music"] = {
        "asset_id": music_assets[0]["id"],
        "volume": 0.15,
        "fade_in_seconds": 0.5,
        "fade_out_seconds": 0.5,
        "ducking": True
    }

# 字幕：若 brief 要求且 script 有 enhancement overlay 需求
if brief.get("delivery_promise", {}).get("subtitles_required", False):
    edit_decisions["subtitles"]["enabled"] = True
    # 词级字幕：用 asset_manifest 中的 narration_timestamps
    ts_asset = next(
        (a for a in asset_manifest["assets"] if a["kind"] == "narration_timestamps"),
        None
    )
    if ts_asset:
        edit_decisions["subtitles"]["source"] = ts_asset["id"]
        edit_decisions["subtitles"]["style"] = "word-by-word"
```

#### 辅助函数：转场映射

`frame_blueprint.cut_in` 字符串形如 `"crossfade:0.4s"`。映射到 `edit_decisions` 的 `transition_in` + `transition_duration`：

```python
def _map_cut_in(cut_in: str) -> str:
    if not cut_in:
        return "cut"
    name = cut_in.split(":")[0].strip()
    # 兼容 edit_decisions 常用转场名
    mapping = {
        "fade-from-black": "fade",
        "crossfade": "dissolve",
        "wipe-left": "wipe",
        "wipe-right": "wipe",
        "dissolve": "dissolve",
        "morph": "dissolve",
        "cut": "cut"
    }
    return mapping.get(name, name)

def _cut_duration(cut_in: str, default: float = 0.4) -> float:
    if not cut_in:
        return default
    parts = cut_in.split(":")
    if len(parts) > 1:
        try:
            return float(parts[1].replace("s", ""))
        except ValueError:
            return default
    return default

def _animation_from_motion(motion_rules: list) -> str:
    # 按 HyperFrames 可消费的 animation 名称返回
    if not motion_rules:
        return "static"
    # 优先取第一个非摄影机动作
    for rule in motion_rules:
        if rule in ("drape-reveal", "reveal-from-below", "warm-light-sweep"):
            return "ken-burns-slow-zoom"
        if rule in ("model-turn-30-left", "model-turn-30-right"):
            return "pan-left"
        if rule in ("camera-push-in", "zoom-in"):
            return "slow-zoom"
    return "static"
```

写完 `edit_decisions.json` 后，用 `edit_decisions.schema.json` 校验：

```python
ed_data = json.load(open("artifacts/edit_decisions.json", encoding="utf-8"))
validate_artifact("edit_decisions", ed_data)
```

### 阶段 C：调用 hyperframes_compose 工具

只准调用项目内工具 `tools/video/hyperframes_compose.py` 的 `hyperframes_compose` capability。输入参数严格按工具 `input_schema`：

```python
from tools.tool_registry import registry
registry.discover()
tool = registry.get("hyperframes_compose")

profile_name = brief.get("target_platform", "xiaohongshu")  # bilibili / xiaohongshu
# bilibili 横版 16:9，小红书竖版 9:16
if profile_name == "bilibili":
    profile = "youtube_landscape"
else:
    profile = "tiktok_vertical"

import yaml
playbook = yaml.safe_load(open(f"styles/{brief.get('style', 'clean-professional')}.yaml", "r", encoding="utf-8")) # 或项目 styles 目录

result = tool.execute({
    "operation": "render",
    "workspace_path": f"projects/{project_name}/hyperframes",
    "output_path": f"projects/{project_name}/renders/final.mp4",
    "edit_decisions": edit_decisions,
    "asset_manifest": asset_manifest,
    "playbook": playbook,
    "profile": profile,
    "quality": "high",      # final 交付用 high
    "fps": 30,
    "strict": True,         # lint 不过即失败
    "skip_contrast": False  # final 必须过 WCAG 对比度
})

assert result.success, f"hyperframes_compose render failed: {result.error}"
print(f"Rendered: {result.data['output']}")
```

#### 工具调用结果处理

`hyperframes_compose` 内部已经执行：
1. `scaffold_workspace` — 生成 `hyperframes/index.html` + CSS + assets/
2. `lint` — 静态契约检查
3. `validate` — 浏览器运行检查
4. `render` — 输出 `renders/final.mp4`

工具返回 `result.data` 含 `output`, `workspace`, `width`, `height`, `fps`, `quality`, `steps`（含 lint/validate/render 的 exit_code 与日志 tail）。

如果失败，按 `result.error` 和 `result.data["steps"]` 定位：
- `scaffold` 失败 → 检查 `edit_decisions.cuts` 非空、source 路径存在、asset_id 对齐
- `lint` 失败 → 修 `edit_decisions` 或 `asset_manifest` 字段
- `validate` 失败 → 可能是 contrast/字体/路径问题，检查 `visual_design.json`
- `render` 失败 → 查看 `steps["render"]["stderr_tail"]`，常见为 Node 版本 < 22 或 FFmpeg 缺失

### 阶段 D：post-render 自检

```python
import subprocess, json
from pathlib import Path

video_path = Path("renders/final.mp4")
assert video_path.exists(), "render output missing"

# ffprobe 基础信息
ffprobe = subprocess.run(
    [
        "ffprobe", "-v", "error", "-select_streams", "v",
        "-show_entries", "stream=width,height,r_frame_rate,duration",
        "-of", "json", str(video_path)
    ],
    capture_output=True, text=True, check=True
)
video_info = json.loads(ffprobe.stdout)
stream = video_info["streams"][0]

# 帧抽样（25/50/75/99%）
duration = float(stream["duration"])
for pct in [25, 50, 75, 99]:
    t = duration * pct / 100
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(t), "-i", str(video_path),
         "-frames:v", "1", f"renders/sample_{pct}.png"],
        check=True
    )

# 音频静默检测
silence = subprocess.run(
    ["ffmpeg", "-i", str(video_path), "-af", "silencedetect=n=-30dB:d=0.5",
     "-f", "null", "-"],
    capture_output=True, text=True
)
has_silence = "silence_duration" in silence.stderr

# 音频爆音检测（True peak > -1 dBTP）
loud = subprocess.run(
    ["ffmpeg", "-i", str(video_path), "-af", "loudnorm=print_format=json",
     "-f", "null", "-"],
    capture_output=True, text=True
)
```

### 阶段 E：写 render_report.json

```json
{
  "version": "4.0",
  "pipeline_stage": "hyperframes_compose",
  "render_runtime_used": "hyperframes",
  "runtime_swap_detected": false,
  "output": {
    "video_path": "renders/final.mp4",
    "resolution": "1080x1920",
    "fps": 30,
    "duration_seconds": 30.0,
    "codec": "h264"
  },
  "tool_invocation": {
    "tool": "hyperframes_compose",
    "operation": "render",
    "workspace_path": "hyperframes",
    "profile": "tiktok",
    "quality": "high",
    "strict": true,
    "skip_contrast": false
  },
  "self_review": {
    "passed": true,
    "ffprobe_ok": true,
    "frame_samples_ok": true,
    "audio_levels_ok": true,
    "fabric_texture_visible_in_samples": true,
    "no_silent_segments": false,
    "no_clipping": true,
    "delivery_promise_honored": true
  },
  "quality_notes": "edit_decisions 每个 frame_blueprint frame 对应一个 cut；source 均指向 asset_manifest 实际生成路径；无手写 HTML；调用项目内 hyperframes_compose 工具"
}
```

注意：如果 `no_silent_segments` 为 true（检测到静默），应记录为 finding 但不一定是 critical——短视频开头/结尾常有刻意留白。

## 绝对禁区（违规即 critical）

- ❌ 手写 `hyperframes/index.html` 整页
- ❌ 一次性写所有 frame HTML
- ❌ 调用 `<HF_SKILL_DIR>/scripts/assemble-index.mjs` / `transitions.mjs` / `build-frame.mjs` / `stage-assets.mjs` / `audio.mjs` 等外部脚本
- ❌ 使用 `npx hyperframes init` / `npx hyperframes render --skill=...` 等需要 HF skill 工作流的命令
- ❌ 修改 `brief.render_runtime` 或 `edit_decisions.render_runtime`
- ❌ 在 asset_manifest 外引用未生成文件路径
- ❌ 跳过 `validate` 或 `lint` 直接 `render`

## 失败回退

| 失败环节 | 回退到 | 备注 |
|---|---|---|
| 阶段 A 工件校验失败 | 对应上游 stage | 上游补齐 |
| `edit_decisions` schema 失败 | 修本 stage 映射逻辑 | 不上游 |
| `hyperframes_compose` scaffold 失败 | 检查 `cuts[].source` / asset 路径 / `linked_frame_id` | |
| `hyperframes_compose` lint 失败 | 修 `edit_decisions` 或 `visual_design` | |
| `hyperframes_compose` validate 失败 | 检查 contrast / 字体 / 缺失 asset | |
| `hyperframes_compose` render 失败 | 看 `stderr_tail`；常见 Node/FFmpeg 环境问题 | |
| post-render 自检失败 | 判核心问题：video 存在则记 finding；核心问题回阶段 C | |

## Reviewer Self-Review

- [ ] 上游 5 件工件齐全且已通过 checkpoint
- [ ] `brief.render_runtime` 为 `hyperframes`
- [ ] `edit_decisions.json` schema-valid
- [ ] `edit_decisions.cuts` 数量 == `frame_blueprint.frames` 数量
- [ ] 每个 `cut.source` 都指向 asset_manifest 中实际存在的 `path`
- [ ] `edit_decisions.render_runtime` = `hyperframes`，`renderer_family` = `product-reveal`
- [ ] 只调用项目内 `hyperframes_compose` 工具，无外部 HF skill 脚本调用
- [ ] 未手写 `hyperframes/index.html`
- [ ] `hyperframes_compose` 返回 success，`renders/final.mp4` 存在
- [ ] ffprobe 输出符合 brief 目标平台分辨率 / fps / 时长
- [ ] 4 张 sample frame 抽样已生成
- [ ] 音频无过长静默、无爆音
- [ ] `render_report.self_review.passed` = true

## 与下游 stage 的契约

- **STAGE 5 publish_copy**：读 `render_report.json` 和 `asset_manifest.json`，不重新渲染
- **STAGE 6 retrospective**：读 `render_report.json` 和 `edit_decisions.json`

## 引用来源

- 权威 HyperFrames 桥接文档：`skills/core/hyperframes.md`
- 实际合成工具：`tools/video/hyperframes_compose.py`
- 标准 artifact 校验：`schemas/artifacts/edit_decisions.schema.json`
- `asset_manifest` 校验：`schemas/artifacts/asset_manifest.schema.json`
