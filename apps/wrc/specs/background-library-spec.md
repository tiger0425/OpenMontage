# 背景视频库规格（v1）

> 所属地图：[wayfinder:map - WRC拉力视频→中文抖音竖屏流水线](https://github.com/tiger0425/OpenMontage/issues/58)
> 决议来源：[grilling: 背景视频库：选片标准、库结构与拼接规格](https://github.com/tiger0425/OpenMontage/issues/63)（2026-08-23 定稿）
> 素材源调研：[research: 拉力飞驰背景素材源盘点](https://github.com/tiger0425/OpenMontage/issues/62)（14 候选源 + Top5）
> 消费方：hyperframes 模板生成器（#65）、管线落地（#66）

## 术语

- **背景素材（raw clip）**：从网上下载的原始精彩片段（含源视频、时间戳段）
- **背景视频（loop）**：拼接/处理后的可循环 9:16 成品（如现有 `youtube_rally_vertical.mp4`，1080x1920，39s 芬兰跳跃）
- **背景库**：存放上述素材与成品的共享目录

## 库结构

```
background_library/wrc/
├── raw/<source>/          # 下载的原始素材，按来源分目录（如 wrc_official/、dirtfish/）
│   └── <video>_<start>-<end>.mp4   # 截好的精彩段（可选：也可只存整段原片）
├── loops/<name>.mp4       # 处理好的循环背景成品（40~60s，1080x1920，静音）
├── loops/<name>.jpg       # 每条的封面缩略图（便于预览选片）
├── loops/manifest.json    # 元数据：名称 / 来源 URL / 画面类型标签 / 时长 / 清晰度 / 制作日期
└── README.md              # 使用说明 + 合规备注
```

位置约定：仓库根 `background_library/wrc/`（与 `music_library/` 并列，gitignored）。

## 选片标准（"精彩飞驰"）

1. **车载 onboard 优先**：车居画面中央、无比分条、无解说字幕 → 竖屏中心裁切几乎无损（DirtFish Onboards、80km 长车载、车队 onboard）。
2. **画面类型**（标签枚举）：`jump` 跳跃/跳台、`drift` 漂移甩尾、`high_speed` 高速弯、`snow` 雪地、`gravel` 砂石、`tarmac` 柏油、`heli` 直升机航拍。
3. **排除**：带比分条/角标/解说字幕的画面、静止画面、PPT 讲解、惨烈事故镜头。
4. **片段长度**：每段 5~15s 精彩段，从长素材（season review 60~120min / 长车载 15~80min / highlight 5~20min）截取。

## 拼接规格

- 竖屏：横屏素材**中心裁 1080x1920**（不用模糊填充）。
- 转场：片段间 **0.4s 交叉淡化**。
- 每条 loop 总长 **40~60s**。
- 循环：首尾帧尽量接近做无缝循环（不完美可接受，背景上会叠画面和字）。
- 音轨：**静音**（配音是主音轨，BGM 后期另混）。

## 使用规则

- **一个系列共用一条背景**（上/中/下同款，风格统一 + 循环复用）；仅当整集主题强烈需要（如整集讲雪地）才换内容匹配的背景。
- 库内维护多条 loop，不同系列轮换避免审美疲劳。

## 合规

- 只收录**官方/低风险源**：WRC 官方（@wrc）、官方车队（TGR / Hyundai / M-Sport）、DirtFish Onboards、FIA ERC / World RX、分站官方。
- **不收录**个人合集素材（Mr. M、MGRallyVideos 等——下架风险 + 双重版权）。
- 成品简介标注 "Footage credit: WRC / DirtFish 等 + 原视频链接"。
- 优先不开盈利/个人账号场景。
- 注意：WRC 官方部分视频有地区限制（德国等）；中国内地访问 YouTube 需代理。

## 首批入库目标（task 票执行）

按 #62 推荐 Top5 下载素材并拼 **3 条**循环背景（建议覆盖：跳跃/车载、漂移/砂石、雪地/直升机），落 `background_library/wrc/loops/` + 元数据 + 封面缩略图。
