# Fabric Promotion - Publish Copy Director v4.0

## Role
产出 B 站 / 小红书平台文案 + 封面文字层合成。HyperFrames 没有这两个平台的发布规范 —— 这是 OpenMontage 这层保留此 stage 的原因。

> v3.0 调整：render_report 现在由 STAGE 4 `hyperframes_compose` 显式产出，
> `required_artifacts_in` 中引用就到位；不再像 v2.3 那样悬空引用。

## Input
- `brief`（品牌名、系列名、面料卖点、调性）
- `asset_manifest`（含成衣图、封面底图、面料原图）
- `render_report`（**v3.0 由 STAGE 4 hyperframes_compose stage 产出**，
  提供成片 `renders/video.mp4` 路径，本 stage 不负责渲染）
- `visual_design.json`（**v4.0 标准 artifact**）：用于读取 palette / typography，保证封面文字层排版与视频各场字幕风格一致

## Process

> **⚠️ 路径规范核心警告**：  
> Universal Harness (omo.py) 始终在 OpenMontage 根目录执行！因此所有针对项目内工件的读取/写入（如 `artifacts/...`, `assets/...`）以及生成素材的路径，都**必须带有 `projects/{project_name}/` 前缀**。切勿直接写相对路径，否则会污染根目录！

### Step 1: 封面文字层合成
从 `asset_manifest` 中取 `kind=cover_base_image` 的封面底图，叠加文字层：
- B 站：1920×1080，横版主图 + 品牌名大字标题
- 小红书：1080×1440，竖版主图 + 三行标题移入面料卡片（不遮挡主体）

字体 / 颜色 v4.0 来源：`visual_design.json`（OpenMontage 标准 artifact）——与视频字幕同源同步。

```python
import json
from pathlib import Path

# 请自行替换为实际的项目名
project_name = "<project_name>"
project_dir = Path(f"projects/{project_name}")

# v4.0 验证来源
with open(project_dir / "artifacts/visual_design.json", encoding="utf-8") as f:
    visual_design = json.load(f)
assert visual_design["typography"]["heading"]["family"]   # 字体
assert visual_design["palette"]["text"]                    # 主文字色
# 这两个字段是 cover 字体选型的源 —— 与视频字幕同源同步
```

输出：
- `projects/<project-name>/renders/bilibili_cover.png`（1920×1080）
- `projects/<project-name>/renders/xiaohongshu_cover.png`（1080×1440）

### Step 2: B 站文案
- **标题** ≤80 字，突出核心卖点（1 个稀有性 + 1 个工艺）
- **简介** 300~500 字，前三行含核心关键词，分三段：卖点 → 工艺 → 穿搭场景
- **标签** ≤10 个

### Step 3: 小红书文案
- **标题** ≤20 字，含 1 个 emoji，口语化有钩子（与封面三行标题呼应同一卖点）
- **正文** 150~300 字，结构：钩子句 → 卖点列表（emoji 起头）→ 穿搭建议 → 互动
- **话题标签** 5~8 个（`#高端面料 #时尚 #穿搭` 等受众锚点）

### Step 4: 合规审查
- 禁绝对化用语（第一 / 最好 / 100% / 唯一 / 顶级）
- 禁医疗 / 功效暗示（"护肤级"、"抗菌"未经备案）
- 禁与面料实际克重 / 姆米不符的量词

### Step 5: 写出
```json
{
  "version": "1.0",
  "platforms": {
    "bilibili": {
      "title": "<≤80字>",
      "description": "<300~500字>",
      "tags": ["..."],
      "cover_ref": "projects/<project-name>/renders/bilibili_cover.png"
    },
    "xiaohongshu": {
      "title": "<≤20字含emoji>",
      "body": "<150~300字>",
      "hashtags": ["#...", "..."],
      "cover_ref": "projects/<project-name>/renders/xiaohongshu_cover.png"
    }
  }
}
```

## Reviewer Self-Review
- [ ] B 站封面 1920×1080 / 小红书封面 1080×1440
- [ ] 封面素材 100% 来自项目内 assets/
- [ ] visual_design.json 的 typography / palette 被正确读取（字体与色值与视频字幕同源同步）
- [ ] render_report.output.video_path 路径存在（不再重新渲染）
- [ ] 字数 / 标签数符合平台规范
- [ ] 无虚假宣传 / 绝对化用语
- [ ] 文案与封面呼应同一卖点

## Output
`publish_copy` artifact（文案）+ `cover_manifest` artifact（封面路径引用）。