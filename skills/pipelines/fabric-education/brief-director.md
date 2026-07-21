# 面料教育 - Brief Director（简报总监）

## 角色
接收用户提供的面料照片和基础资料，分析面料，产出 `fabric_edu_brief` artifact。本 stage 是 Truth-Gate 的第一道防线——所有后续内容都基于本 stage 的面料事实。

## 输入
- 用户面料实拍图（手机拍摄，至少 1 张）
- 基础资料：面料名称、成分、克重
- Agent 可能追问：织物组织（weave）、后整理工艺（finishing）、适用季节

## 流程

> **⚠️ 路径规范**：所有相对路径必须带 `projects/{project_name}/` 前缀。

### Step 0: 读取 Provider Lockdown
**强制动作**：在执行任何生成任务前，必须加载 `.agents/skills/provider-lockdown/SKILL.md`。

### Step 1: 接收用户输入
```
用户提供的面料信息：
- 名称：{fabric_name}
- 成分：{composition}
- 克重：{weight}
- 图片路径：{origin_image}
```

### Step 2: 信息完整性评估
检查用户提供的信息是否足够生成有意义的 edu_brief：

| 字段 | 来源 | 是否必须 |
|------|------|---------|
| fabric_name | 用户提供 | ✅ 必须 |
| composition | 用户提供 | ✅ 必须 |
| weight | 用户提供 | ✅ 必须 |
| origin_image | 用户提供 | ✅ 必须 |
| weave | 可追问 | ⭕ 建议 |
| finishing | 可追问 | ⭕ 建议 |
| season | 可追问 | ⭕ 建议 |

如果缺失建议字段（weave/finishing/season），Agent 应生成自然语言追问问题一次性问用户。

### Step 3: 面料分析
使用视觉能力分析面料图片，记录：
1. 面料类型推断（棉、麻、丝、毛、化纤、混纺等）
2. 质感特征（光滑/粗糙、梭织/针织、密实/疏松）
3. 图案/颜色（纯色/花色、明度、色相）
4. 光泽度（哑光/丝光/高光）
5. 风格关联（优雅/休闲/奢华/运动/复古）

### Step 4: 知识深度评级
根据面料类型、成分、克重和行业知识，判断此面料的知识深度：

- **basic**：日常常见面料、知识点较少（如普通纯棉、常规化纤）
  - 适合：仅出笔记，最多一条 15-30s 切片
- **deep**：贵重/复杂面料、知识点丰富（如真丝、羊绒、高支棉、科技面料）
  - 适合：笔记 + 完整知识视频 3-8 分钟 + 切片
  - 评分维度：
    - 是否有常见仿冒品/混淆材质
    - 是否有专业辨别方法（燃烧/水洗/手感）
    - 是否有保养/打理知识可讲
    - 是否有行业经验/内幕可分享

评级理由要记录到 brief.metadata 中。

### Step 5: Pitfall 识别
基于面料商行业经验，列出该面料最常见的消费者误区/坑。例如：

- "化纤冒充纯棉"
- "支数虚标"
- "真丝 vs 天丝混淆"
- "羊毛含量虚标"
- "缩水率不告知"

每个 pitfall 应具体、可教育，而非空泛。

### Step 6: 易混淆材质清单
列出消费者容易与本次面料混淆的其他材质。例如：

- 真丝 → [天丝、醋酸、粘胶]
- 纯棉 → [化纤混纺]
- 亚麻 → [棉麻混纺、化纤仿麻]

### Step 7: 教育切入点确定
推荐此面料最合适的教育角度。好角度应是：

- 有实用价值（用户学了能用到）
- 有行业壁垒（体现了"老手经验"）
- 可视觉化（能配图/配视频说明）

例如：
- "从手感、燃烧、水洗三步辨别纯棉真假"
- "为什么你的真丝洗几次就坏了？保养方法全解析"
- "300 支和 60 支的床品到底差在哪？"

### Step 8: 产出 fabric_edu_brief artifact

```json
{
  "version": "1.0",
  "fabric_name": "100%新疆长绒棉",
  "composition": "100% cotton, 60支",
  "weight": "180g/m² 中厚",
  "knowledge_depth": "basic",
  "pitfalls": ["化纤冒充纯棉", "支数虚标"],
  "educational_angle": "从手感、燃烧、水洗三步辨别纯棉真假",
  "weave": "平纹",
  "finishing": "丝光",
  "season": "四季",
  "comparison_materials": ["化纤混纺", "普通棉"],
  "origin_image": "projects/{project_name}/assets/fabric_source/origin.jpg"
}
```

产出后使用 `schemas/artifacts/__init__.py` 的 `validate_artifact` 校验。
