# WRC 成品包规格（v1）

> 所属地图：[wayfinder:map - WRC拉力视频→中文抖音竖屏流水线](https://github.com/tiger0425/OpenMontage/issues/58)
> 决议来源：[grilling: 成品包规格（标题/封面/简介/BGM）](https://github.com/tiger0425/OpenMontage/issues/67)（2026-08-23 定稿）
> 消费方：`bin/wrc.py package` 命令（pipeline-cli-spec.md）

## 成品包结构（每集一目录，人工上传抖音）

```
projects/wrc-<id>/package/<集序号>/
├── video.mp4        # 定版成片（含 BGM）
├── cover.jpg        # 9:16 竖屏封面（1080x1920）
├── title.txt        # 主标题（备选在 title_alt.txt）
├── title_alt.txt    # 备选标题（可选）
└── desc.txt         # 简介（含 hashtags + credit）
```

## 标题（Q1）

- `package` 阶段由 LLM 按模板生成 **1 主标题 + 1 备选**，写入集 JSON 的 `title_main` / `title_alt`（人可直接改）。
- 风格规则：含**关键数字 / 反差 / 悬念**（如"34万进WRC？小厂真玩得起？"）；**≤30 字**；**不剧透结尾**；可带 🏁 类 emoji。
- 内部集标题（脚本阶段）≠ 抖音标题：抖音标题由成品阶段二创，保留钩子感。

## 封面（Q2）

- **9:16 竖屏**（1080x1920 JPG）。
- 版式：从定版视频抽一帧**精彩画面**（默认开场钩子帧，可指定秒数）→ 底部黑色压底（rgba(10,14,26,0.85) 渐变）→ 叠加**集标题大字**（白字粗体）+ **红字"第X集"角标**（#ff3b30）。
- 与成片同源，保证画面对题。

## 简介（Q3）

模板（LLM 生成主体 + 固定行）：

```
<开场钩子句：从 s0 文案提炼，1 句>
<内容要点 2-3 条：幕标题串（如 "燃料不用愁｜零件像拼乐高｜改装大佬也能上"）>
<追更引导：关注我，下条…>
#WRC #拉力赛 #赛车
Footage credit: WRC / DirtFish 等 + 原视频链接
```

## BGM（Q4）

- 全系列**固定 `bgm_epic.mp3`**：0.25 音量 + 1.5s 淡入淡出（三集已验证参数）。
- `music_library/` 作为可选手动替换；**暂不做自动选曲**（留作未来增强）。

## 上传

- **人工上传抖音**（自动发布已证伪，#19/#20）。
- 上传时：视频 + 封面 + 标题 + 简介，一目录一集，复制即发。
