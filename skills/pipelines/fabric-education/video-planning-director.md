# 面料教育 - Video Planning Director（视频规划总监）

## 角色
根据 `fabric_edu_brief` 的知识深度评级（knowledge_depth），决定视频产出路径——深度完整视频或短知识切片。产出 `edit_decisions` 和 `render_report`。

## 输入
- `fabric_edu_brief`（含知识深度评级、pitfalls、educational_angle）
- `note_manifest`（核心长文，可提取配音稿素材）
- Provider Lockdown 规则

## 流程

> **⚠️ 路径规范**：所有相对路径必须带 `projects/{project_name}/` 前缀。

### Step 0: 读取 Provider Lockdown
**强制动作**：在执行任何生成任务前，必须加载 `.agents/skills/provider-lockdown/SKILL.md`。

### Step 1: 路由决策
读取 `fabric_edu_brief.knowledge_depth`：

- **`deep`** → 执行 Path A（完整知识视频 3-8 分钟）
- **`basic`** → 执行 Path B（知识切片 15-30 秒）
- 如果用户在 checkpoint 处要求跳过视频，直接输出空的 edit_decisions 和 render_report（status=skipped）

### Step 2: 脚本与场景规划

#### Path A — 深度视频（3-8 分钟）

教育叙事骨架（5 段）：

| 段 | 名称 | 时长 | 内容 | 画面 |
|----|------|------|------|------|
| 1 | 钩子 | 15-30s | 提出一个让消费者警惕的问题 | 面料特写 + 问题文字 |
| 2 | 问题 | 30-60s | 这个坑的来龙去脉 | 对比图 / 测试场景 |
| 3 | 拆解 | 60-120s | 核心知识讲解 + 辨别方法 | 微距特写 / 对比测试 / 示意图 |
| 4 | 解决方案 | 30-60s | 怎么选/怎么用/怎么打理 | 使用演示 / 产品成品 |
| 5 | 总结 | 15-30s | 核心结论 + 引导关注 | 总结文字 + 面料展示 |

配音稿从 `note_manifest.core_article` 提取，按 5 段切分。

#### Path B — 知识切片（15-30 秒）

从 `fabric_edu_brief.pitfalls` 或 `educational_angle` 中提取**一个**核心知识点。

典型结构：
```
5s 钩子："90% 的人不知道 XX 面料的这个秘密"
10-15s 正文：快速讲解核心辨别方法
5s 结尾："我是 XX，教你挑好料子"
```

### Step 3: 素材生成

| 素材类型 | 工具 | 备注 |
|---------|------|------|
| 配音 | `tts_selector`（preferred_provider="voxcpm"） | 多段音色一致（chain cloning） |
| BGM | `pixabay_music` | 面料调性匹配（亚麻→轻音乐，科技面料→电子） |
| 面料动态 | `comfyui_video`（img2img 模式） | 以面料原图为基础，展示垂坠/光泽 |
| 配图 | `image_selector`（img2img 模式） | 对比/微距/测试场景 |

#### 所有面料画面必须 img2img
绝对禁止 text-to-image 生成面料画面。如果不支持 img2img 的 provider 不可用，宁可阻塞也不要降级。

### Step 4: 编辑决策

产出 `edit_decisions.json`：

- `render_runtime: "hyperframes"`
- 每个场景对应一个 cut
- cuts 的 source 指向实际生成的 asset 路径
- 字幕风格：教育类 > 清晰可读，字体大小适中（≥24px）

### Step 5: 合成

通过 `video_compose` 执行合成：

```python
video_compose.execute({
    "edit_decisions": edit_decisions,
    "asset_manifest": asset_manifest,
    "render_runtime": "hyperframes",
    "profile": "xiaohongshu" if Path B else "bilibili",
    "fps": 30,
    "quality": "high",
})
```

### Step 6: 自检

- ffprobe 验证时长、分辨率、编码
- 如果是 Path B，确认时长 ≤ 60s
- 如果是 Path A，确认时长在 180-480s 之间
- 配音清晰度检查
- BGM 音量 ≤ 0.2（旁白优先）
