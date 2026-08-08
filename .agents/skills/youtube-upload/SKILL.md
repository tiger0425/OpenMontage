---
name: youtube-upload
description: >
  OpenMontage 内建的通用 YouTube 管理技能：上传视频、上传字幕、
  创建/复用播放列表、批量归档视频到分类合集、设置可见性、更新元数据。
  凭证自动复用 %USERPROFILE%\\.youtube-upload\\ 下的 client_secret.json 与 token.json，
  无需每次手动找凭证。触发词：上传YouTube、youtube上传、创建播放列表、
  整理视频合集、归档视频、添加视频到播放列表、设置视频可见性、上传字幕、
  搬运视频到YouTube。
metadata:
  tags: "youtube, upload, playlist, captions, video-archive, oauth"
---

# YouTube 通用管理技能（youtube-upload）

## 📌 概述

统一入口 CLI：`python bin/youtube.py`。

它把「凭证查找 → OAuth 刷新 → 上传 → 字幕 → 播放列表 → 可见性 → 元数据」
全部封装为一个可复用命令，替代过去每次手写临时脚本的方式。

**凭证位置（自动查找，无需手动指定）：**
- client_secret.json：环境变量 `YOUTUBE_CLIENT_SECRET` → `%USERPROFILE%\.youtube-upload\client_secret.json` → 项目根 → `bin/../client_secret.json`
- token.json：与 client_secret 同目录（可用 `YOUTUBE_TOKEN` 覆盖）
- token 过期自动刷新并回写；没有 token 时首次运行会弹出浏览器授权，之后无需再授权。

---

## 🚀 CLI 命令速查

所有命令在 `E:\YifuAIForge\OpenMontage` 目录下执行：

```bash
# 凭证状态（不弹浏览器，先查这个）
python bin/youtube.py auth status

# 列出本人全部播放列表（标题 + ID）
python bin/youtube.py playlist list

# 创建播放列表
python bin/youtube.py playlist create --title "我的合集" --desc "描述" --privacy unlisted

# 查看播放列表内视频（按标题或 ID）
python bin/youtube.py playlist items --pl "Pi Agent - 实战玩法"

# 往播放列表添加视频（可多个）
python bin/youtube.py playlist add --pl "我的合集" --video VID1 --video VID2

# 上传视频（推荐 --privacy unlisted，上传后可加字幕/播放列表）
python bin/youtube.py upload out.mp4 --title "标题" --desc "描述" --tags "a,b" --privacy unlisted
# 上传后直接设为公开:
python bin/youtube.py upload out.mp4 --title "标题" --privacy public
# 上传并加入播放列表、附带字幕:
python bin/youtube.py upload out.mp4 --title "标题" --privacy unlisted --playlist "我的合集" --caption en=sub.srt

# 单独上传字幕
python bin/youtube.py caption VID --lang en --name "English" sub.srt

# 设置可见性（private/unlisted/public）
python bin/youtube.py visibility VID --privacy public

# 更新标题/描述/标签
python bin/youtube.py metadata VID --title "新标题" --desc "新描述" --tags "a,b"
```

---

## 📦 批量建合集（playlist build）

一次性把大量视频归档进「总表 + 多个分类子表」的场景，
用 manifest JSON 驱动，已创建/已添加的条目自动跳过，支持断点续传、可重复执行：

```json
{
  "master": "Pi Agent - 学习合集 (All Videos)",
  "master_desc": "全部学习视频的总表",
  "playlists": [
    {
      "title": "Pi Agent - 零基础入门",
      "description": "从零上手",
      "privacy": "unlisted",
      "videos": ["N30XGyPrr6I", "BZ0w0JhPQ9o"]
    },
    {
      "title": "Pi Agent - 架构与原理",
      "description": "深入剖析",
      "privacy": "unlisted",
      "videos": ["gTeujlv8qK0", "qo1QNxWcm28"]
    }
  ]
}
```

```bash
python bin/youtube.py playlist build manifests/my.json
```

规则：
- `master` 可选：所有子表里的视频也会自动并入该总表。
- 同名播放列表已存在 → 复用；访问返回 404 的坏列表 → 自动删除重建。
- 视频已在列表中 → 跳过，不会重复添加。
- 每个子表的视频同时保证在总表里，重复执行安全。

---

## 🧩 典型工作流

### 场景 A：上传一个新视频并归档
```bash
python bin/youtube.py upload final.mp4 --title "xxx" --desc "yyy" --privacy unlisted --playlist "我的合集"
```
上传后得到 `https://youtu.be/<VID>`。

### 场景 B：把一批现有视频整理成合集
1. 收集视频 ID（可用 `bin/yt_dlp.py` 或手动）。
2. 写 manifest JSON（见上）。
3. `python bin/youtube.py playlist build manifest.json`。

### 场景 C：审核后公开
```bash
python bin/youtube.py visibility VID --privacy public
```

---

## ⚠️ 注意事项

1. **中文显示乱码**：PowerShell 控制台用 GBK 显示 Python 的 UTF-8 输出时部分中文会变 `�?`，**这只是显示问题**，API 里的标题/描述是正确的。需要确认时用 `playlist items` 或把输出重定向到文件查看。
2. **重试策略**：上传走 resumable 且自动重试（`YT_UPLOAD_ATTEMPTS` 可调，默认 5）；HTTP 409/500/503 自动指数退避重试。
3. **分类 ID**：默认 Science & Technology(28)，可用 `--category` 覆盖。
4. **字幕格式**：`.srt` 文件即可，工具自动按 ttml 上传。
5. **不要把 token.json / client_secret.json 提交进 git**（已在 .gitignore 或位于用户目录）。
6. **错误处理**：任何子命令失败先跑 `python bin/youtube.py auth status` 确认凭证，再检查是否是临时服务错误（重跑即可）。

---

## 🔧 参考

- 通用 CLI 源码：`bin/youtube.py`
- 旧版专用脚本（series-adapt 系列，勿用于通用场景）：`bin/upload_youtube.py`
- OAuth 凭据目录：`%USERPROFILE%\.youtube-upload\`
