# 输出格式参考

## 图片分析输出

```json
{
  "success": true,
  "model": "MiniMax-M3",
  "provider": "minimax-cn-coding-plan",
  "media_type": "image",
  "files": [
    {"path": "/abs/path/image.jpg", "type": "image"}
  ],
  "analysis": {
    "summary": "一张城市夜景照片，CBD 天际线，蓝色时刻...",
    "scenes": [
      {
        "timestamp": "frame_1",
        "description": "城市天际线全景，高层建筑群",
        "elements": ["摩天大楼", "灯光", "天空"]
      }
    ],
    "details": {
      "composition": "三分法构图，地平线位于下三分之一处",
      "colors": "蓝色为主调，暖色灯光点缀",
      "text_content": "无",
      "objects": ["建筑", "天空", "灯光", "街道"]
    }
  },
  "usage": {
    "prompt_tokens": 850,
    "completion_tokens": 320,
    "total_tokens": 1170
  },
  "elapsed_seconds": 4.5
}
```

## 视频分析输出

```json
{
  "success": true,
  "model": "MiniMax-M3",
  "provider": "minimax-cn-coding-plan",
  "media_type": "video",
  "file": {
    "path": "/abs/path/video.mp4",
    "duration": 120.5
  },
  "frames": [
    {"path": "/tmp/frame_0001.jpg", "timestamp": 0.0, "timestamp_formatted": "00:00"},
    {"path": "/tmp/frame_0002.jpg", "timestamp": 15.0, "timestamp_formatted": "00:15"}
  ],
  "analysis": {
    "summary": "产品演示视频，展示产品开箱到使用全过程",
    "scenes": [
      {
        "timestamp": "00:00",
        "description": "开箱场景，白色包装盒",
        "elements": ["包装盒", "产品", "桌面"]
      },
      {
        "timestamp": "00:30",
        "description": "产品正面特写，屏幕亮起",
        "elements": ["屏幕", "界面", "操作"]
      }
    ],
    "details": {
      "composition": "中心构图，产品居中",
      "colors": "白色背景，产品深灰色",
      "text_content": "无",
      "objects": ["产品", "包装", "配件"]
    }
  },
  "usage": {
    "prompt_tokens": 4200,
    "completion_tokens": 680,
    "total_tokens": 4880
  },
  "elapsed_seconds": 18.3
}
```

## 错误输出

```json
{
  "success": false,
  "error": "文件不存在: /path/to/nonexistent.jpg"
}
```

## 主代理消费示例

主代理通过 `delegate_task` 工具使用本子代理后，从返回结果中提取：

```python
{
  "success": bool,
  "analysis": {
    "summary": "分析摘要文本",
    "scenes": [{"timestamp": "...", "description": "..."}],
    "details": {"objects": [...], "text_content": "..."}
  }
}
```
