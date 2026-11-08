# Global Asset Library

跨项目共享的本地素材库，用于存放外部来源素材（用户上传、互联网搜索、购买/授权）。AI 生成内容不归档。

## 目录结构

```
assets/shared_library/
├── images/
│   ├── photos/          # 真实照片参考图（人物、地点、产品）
│   ├── textures/         # 背景纹理、纸张纹理
│   └── decals/           # CSS 装饰贴图（胶带、图钉、印章、标签）
├── audio/
│   ├── music/            # 音乐素材
│   └── sfx/              # 音效素材（纸张 ASMR、转场等）
├── fonts/                # 字体文件
└── videos/               # 视频片段或透明通道素材
```

## 元数据格式

每个素材必须配一个 `.meta.json` 文件：

```json
{
  "version": "1.0",
  "source_type": "user_upload | web_search | purchased | licensed | project_preset",
  "source_url": "https://example.com/photo.jpg",
  "source_description": "Historical photo of D.B. Cooper from FBI archives",
  "tags": ["real_content", "person", "crime", "fbi", "1971"],
  "source_provider": "wikimedia",
  "license": "public_domain | cc0 | cc_by | cc_by_sa | no_known_restrictions | rights_managed | commercial | unknown",
  "license_url": "https://commons.wikimedia.org/wiki/File:...",
  "license_checked": true,
  "creator": "Author / photographer / institution",
  "usage_count": 0,
  "first_used_project": "vox-paper-collage-db-cooper-2026-08",
  "date_added": "2026-08-05",
  "file_type": "image/png",
  "dimensions": [1024, 1024]
}
```

## 真实素材源（asset_sources）

`tools/graphics/asset_sources.py` 提供四个真实素材源，搜索、下载、许可日志一条龙：

| 源 | 内容 | 许可 |
|---|---|---|
| Poly Haven | 纹理、HDRI、3D 模型 | CC0 |
| ambientCG | PBR 材质 | CC0 |
| Wikimedia Commons | 真实档案图片 | 逐文件（PD / CC BY / CC BY-SA） |
| Library of Congress | 真实档案图片 | 逐项（PD / 无已知限制 / 需核查） |

Mixamo（人物动画）和 ActionVFX（火焰/烟雾/粉尘包）需要账号且逐包许可，不自动下载；按需人工归档并填写 `.meta.json`。

### CLI

```bash
# 搜索
python bin/asset.py search --provider polyhaven --category texture --query "old paper"
python bin/asset.py search --provider wikimedia --category image --query "1946 map"

# 下载并归档（默认写入 assets/shared_library，自动写 .meta.json）
python bin/asset.py download \
  --provider polyhaven --asset-id brick_4 \
  --license cc0 --license-url https://polyhaven.com/license \
  --source-url https://polyhaven.com/a/brick_4 \
  --title "Brick 4" --tags brick,paper-collage --creator "Rob Tuytel"
```

### Python

```python
from tools.graphics.asset_sources import AssetSources
tool = AssetSources()
tool.execute({"operation": "search", "provider": "any", "category": "texture", "query": "paper"})
tool.execute({
    "operation": "download", "provider": "polyhaven", "asset_id": "brick_4",
    "kind": "texture", "resolution": "1k", "license": "cc0",
    "license_url": "https://polyhaven.com/license",
    "source_url": "https://polyhaven.com/a/brick_4", "title": "Brick 4",
})
```

下载归档时会记录 `source_provider`、`license`、`license_url`、`license_checked`、`creator`，便于审计。LoC 的 `rights` 经常为空，工具会如实标 `license=unknown` 并保留 item 页面链接，需要人工核查。

## 使用流程

1. **assets 阶段先搜库**：调用 `asset_library` 工具（operation=search）按标签/类型/关键词检索本地素材库。
2. 找到匹配素材则直接使用，并调用 `touch` 增加 `usage_count`。
3. 找不到则按 Real Photo Cascade 获取（用户上传 → Wikimedia → 内置搜图 → Bing/Google → 生成）。
4. 外部来源素材（用户上传、搜索下载、购买/授权）获取后，调用 `add` 自动归档到对应目录并生成 `.meta.json`。
5. AI 生成内容（包括 style-transferred 图像、TTS 音频、BGM）不归档。
6. 找不到真实照片的 real_content 元素，写入 `asset_manifest.missing_photos[]`，统一提交用户决策（C7）。

## 工具调用

通过 OpenMontage 工具系统调用 `asset_library`：

```python
# 搜索素材库（必须先生图）
tool.execute({"operation": "search", "query": "blackrock building", "category": "photo"})

# 归档外部来源素材
tool.execute({
    "operation": "add",
    "file_path": "/path/to/photo.jpg",
    "category": "photo",
    "tags": ["real_content", "place", "blackrock"],
    "source_type": "web_search",
    "source_url": "https://...",
    "license": "cc_by",
    "description": "BlackRock headquarters New York"
})

# 使用计数 +1
tool.execute({"operation": "touch", "asset_path": "assets/shared_library/images/photos/blackrock.jpg"})

# 缺失照片清单（C7）
tool.execute({"operation": "missing", "asset_path": "path/to/asset_manifest.json"})
```

## 索引

目前使用文件目录 + 每个素材的 `.meta.json` 进行检索。未来可升级为 SQLite 或向量索引。
