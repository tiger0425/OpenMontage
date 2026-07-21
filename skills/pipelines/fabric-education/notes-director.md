# 面料教育 - Notes Director（笔记总监）

## 角色
将 `fabric_edu_brief` 转化为多平台适配的图文笔记。这是教育管线最独特的 stage——产出质量直接决定后续视频是否值得做。

## 输入
- `fabric_edu_brief`（面料事实、pitfalls、educational_angle）
- 面料原图路径

## 流程

> **⚠️ 路径规范**：所有相对路径必须带 `projects/{project_name}/` 前缀。

### Step 0: 读取 Provider Lockdown
**强制动作**：在执行任何生成任务前，必须加载 `.agents/skills/provider-lockdown/SKILL.md`。

### Step 1: 编写核心长文（core_article）

基于 `fabric_edu_brief` 的面料事实、pitfalls 和 educational_angle，写一篇完整的 Markdown 知识长文。

核心长文结构建议：

```
# 标题

## 开头（建立身份 + 抛出问题）
- 我是谁（面料行业 x 年老手）
- 今天要讲什么面料
- 为什么这个话题重要

## 面料基本介绍
- 成分、特点、用途
- 行业地位/档次定位

## 常见误区（pitfalls 展开）
- 误区 1：解释 + 为什么消费者会被骗
- 误区 2：解释 + 真相是什么
- ......

## 辨别方法（最核心的干货）
- 方法 1：手感/眼看
- 方法 2：燃烧测试（如需）
- 方法 3：水洗测试（如需）

## 使用与保养
- 怎么洗、怎么晾、怎么熨
- 避坑关键点

## 结尾
- 总结核心结论
- 引导关注
```

字数：小红书版 500-1000 字，公众号版 1500-3000 字。核心长文应取最完整的版本。

### Step 2: 配图规划

教育配图与推广配图不同——不是为了好看，而是为了**说明知识点**。

#### 配图类型选择

| 教育角色 | 说明 | 适用场景 |
|---------|------|---------|
| `microscopic_detail` | 微距特写展示织法/密度 | 讲面料品质、支数差别 |
| `comparison_diagram` | 正品 vs 仿品/不同等级对比 | 讲辨别方法、避免踩坑 |
| `care_label_explained` | 洗护标识解析 | 讲保养 |
| `test_scene` | 燃烧/水洗/揉搓测试 | 讲辨别方法 |
| `diagram` | 示意图/原理图 | 讲织造工艺、纤维结构 |

所有配图通过 `image_selector`（img2img 模式）以面料原图为底图生成。如果 img2img 不可用，宁可阻塞也不要 text-to-image。

#### 配图 Prompt 指引

配图 prompt 要包含：
- 面料原图作为 init_image
- 清晰说明教育用途（不是广告展示）
- 保持面料纹理真实
- 风格偏写实/教育插图，非商业大片

### Step 3: 多平台适配

从 core_article 提取内容，为每个平台生成适配版本。

#### 小红书平台

- 标题 ≤20 字，有 emoji，有钩子
- 正文 500-1000 字
- 图文混排（在正文中用引用标记配图位置）
- 语言口语化、亲切

```
标题：🔥 别再被骗了！3步辨别 XX 真假

正文：
{开头段}

👉 第一步：看标签
{说明文字}
[配图：标签解析]

👉 第二步：摸手感
{说明文字}
[配图：手感对比]
```

#### 公众号平台

- 深度长文（可复用 core_article 全文）
- 有标题、摘要、正文
- 可含更多背景知识
- 语言正式但有温度

#### 知乎平台

- 偏问答/科普风格
- 开头直接回应问题
- 中间有干货论证
- 结尾可加引导

#### 朋友圈平台

- ≤150 字
- 开头一句话钩子
- 中间快速价值点
- 结尾引导去其他平台看完整版

```
干了 x 年面料，今天说个真相：
XX 面料的水有多深？
我教你 3 步避坑👇
看完整版请移步我的小红书 [链接]
```

### Step 4: 产出 note_manifest artifact

```json
{
  "version": "1.0",
  "core_article": "# 标题\n\n全文...",
  "platform_versions": [
    {
      "platform": "xiaohongshu",
      "title": "🔥 标题",
      "body": "正文...",
      "images": ["assets/images/xhs_1.jpg"],
      "tags": ["#面料", "#避坑"]
    },
    {
      "platform": "wechat_public",
      "title": "标题",
      "body": "全文..."
    }
  ],
  "images": [
    {
      "path": "assets/images/micro_1.jpg",
      "educational_role": "microscopic_detail",
      "description": "60支棉 vs 40支棉微距对比"
    }
  ],
  "fabric_origin_image": "projects/{project_name}/assets/fabric_source/origin.jpg"
}
```

产出后使用 `schemas/artifacts/__init__.py` 的 `validate_artifact` 校验。

### Step 5: 视频决策建议

在 checkpoint 中向用户提供视频产出建议：

```
本面料的视频建议：
- 知识深度评级：{basic / deep}
- 推荐路径：{不产出 / 短切片 15-30s / 完整视频 3-8min}
- 理由：{简要说明}
```
