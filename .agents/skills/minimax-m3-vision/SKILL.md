---
name: minimax-m3-vision
description: |
  使用 OpenCode 内置 minimax-cn-coding-plan 提供商的 MiniMax-M3 多模态模型分析图片和视频内容。
  适用于：（1）分析单张/多张图片内容，（2）通过帧提取分析视频内容，（3）结构化输出分析结果给主代理。
---

# minimax-m3-vision

子代理 skill：使用 MiniMax-M3 模型对图片和视频进行多模态分析，返回结构化 JSON。

## 依赖

- `ffmpeg` + `ffprobe`（视频帧提取用）
- `requests`（Python 内置或 pip install）
- 已配置的 `minimax-cn-coding-plan` provider（OpenCode 内置，API key 在 `auth.json` 中）

## 使用方式

### 分析图片

```bash
python3 .agents/skills/minimax-m3-vision/scripts/analyze_media.py image.jpg
python3 .agents/skills/minimax-m3-vision/scripts/analyze_media.py image.jpg -p "详细描述这张图片的内容"
python3 .agents/skills/minimax-m3-vision/scripts/analyze_media.py image1.jpg image2.jpg -o result.json
```

### 分析视频

```bash
python3 .agents/skills/minimax-m3-vision/scripts/analyze_media.py video.mp4
python3 .agents/skills/minimax-m3-vision/scripts/analyze_media.py video.mp4 --max-frames 10
python3 .agents/skills/minimax-m3-vision/scripts/analyze_media.py video.mp4 -p "分析视频的场景变化"
```

### 分析多个文件

```bash
python3 .agents/skills/minimax-m3-vision/scripts/analyze_media.py image.jpg video.mp4 --context "这是同一个项目的素材"
```

## CLI 参数

| 参数 | 说明 |
|------|------|
| `path` | 图片/视频文件路径（必填，支持多个） |
| `-p, --prompt` | 自定义分析提示词（默认：图片分析内容/视频分析场景） |
| `--max-frames` | 视频最大帧数（默认：8） |
| `--interval` | 视频帧提取模式：`scene`（场景检测）、`interval`（等间隔） |
| `-o, --output` | 输出到文件 |
| `-q, --quiet` | 静默模式 |

## 子代理调用模式

在主代理中通过 `delegate_task` 工具调用：

```
goal: 分析附件图片/视频的内容
context: 文件路径列表 + 分析需求
toolset: ["terminal", "file"]
```

脚本自动读取 OpenCode 的 `auth.json` 获取 `minimax-cn-coding-plan` 的 API key，
并通过 MiniMax 的 OpenAI 兼容接口调用 `MiniMax-M3` 模型。

## 输出格式

输出为结构化 JSON（详见 `references/output-format.md`）：

```json
{
  "success": true,
  "model": "MiniMax-M3",
  "provider": "minimax-cn-coding-plan",
  "media_type": "image|video",
  "files": [...],
  "analysis": {
    "summary": "...",
    "scenes": [...],
    "details": {...}
  }
}
```

## 限制

- MiniMax-M3 是文本+视觉模型，视频分析通过帧采样实现
- 视频较长时建议只用关键场景帧（--max-frames 控制）
- 当前仅支持本地文件（图片支持 URL）
