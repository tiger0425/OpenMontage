# Vox Layout Library — 布局契约（series-adapt）

系列化资产化定格的**布局契约**：从叙事意图推导元素摆放（box / z / rot / timing）的可执行规则。
与 `vox-look-library.md`（视觉层）、`vox-motion-library.md`（动效层）、`vox-story-library.md`（叙事层）、
`vox-stopmotion-prompt-spec.md`（mask/inpaint 局部变化）配套使用。
由 `scene-director.md`（layout_intent 选型）与 `compose-director.md`（GSAP 装配）引用。

> 本库解决 series-adapt 核心难题的**构图/表达**侧：元素摆放必须由叙事意图驱动，
> 而不是 AI 随机放置。来源：借鉴 vox-paper-collage 的 spec 契约
> （kind/box/rot/z/family/micro/sfx，已跑通的纸拼贴定格合成），适配 series-adapt
> 的真实帧派生资产与 1920×1080 制式。

## 0. 核心原则（两条不可破）

1. **布局是推导的，不是临场的。** 每个元素的 box/z/rot/timing 必须在 scene_plan 阶段
   由叙事意图按本库规则推导出来，compose 阶段只按契约执行，不临场摆位。
2. **背景板零漂移。** 背景板（L1）一旦生成即冻结，元素在其上作纸片动作；
   不允许整幅背景被重新采样（见 `vox-stopmotion-prompt-spec.md` 核心原则 1）。

## 1. 叙事意图 → 布局模式（layout_intent 词表）

每个 sub_shot / 元素组声明一个 `layout_intent`，它决定该组的布局模式与 box 推导：

| layout_intent | 语义 | 对应 composition_family | 典型场景 |
|---|---|---|---|
| `hero` | 单主体展示 | full-bleed / letterbox | 坦克特写、人物肖像、关键实物 |
| `compare` | 对比两个主体/前后 | left-right-split / diagonal-split | 59式 vs T-54A、改前改后 |
| `sequence` | 时序推进/地图展开 | timeline-band / top-title-cascade | 工厂扩散、时间线 |
| `change_zone` | 局部变化区（爆破/发展） | center-change / blueprint-draw | 爆破点、缺口、翻新区 |

**布局模式 = 骨架，叙事意图 = 为什么选它。** 同一 layout_intent 可映射到不同
composition_family（实现变体），但骨架必须支撑该意图的构图。

## 2. box 推导规则（每个元素必填 [left, top, width, height] %）

统一以 **1920×1080 画布百分比** 为坐标单位（与 schema `box` 字段一致）。

### 2.1 按 layout_intent 的 box 模板

| layout_intent | 主元素（L2/L3）box 模板 | 负空间 |
|---|---|---|
| `hero` | 主体居中或中偏左：`[30, 20, 40, 60]`；满幅变体 `[10, 5, 80, 90]` | ≥30% |
| `compare` | 左面板 `[5, 25, 42, 50]` + 右面板 `[53, 25, 42, 50]` | 面板间留 6% 缝 |
| `sequence` | 时间轴条带 `[10, 70, 80, 12]` + 事件节点沿轴错开 | 上方留白给叙事 |
| `change_zone` | 主体 `[20, 20, 55, 60]` + 变化区标记 `[right: 55-70, 变化处]` | 变化区外留白 |

**模板是起点，不是终点**：在模板基础上按画面内容微调（主体占位、真实帧裁剪）。
微调必须保持叙事意图可读（hero 仍最大、对比仍对称、时序仍有序）。

### 2.2 box 硬规则（违反即 BLOCKED，不做随机重排）

- **hero 主体** 宽度 ≥ 画面 40%，且高度 ≥ 画面 50%（保证主体主导力）
- **对比面板** 两面板宽度差 ≤ 10%（对称才叫对比）
- **时序节点** 必须沿轴单调排布（左→右 或 上→下），禁止乱序
- **所有元素** 必须在画布内（`0 ≤ left`，`left+width ≤ 100`），禁止半出画布
- **相邻 sub_shot 禁止同 composition_family**（复用 scene-director 反单调规则）

## 3. z 分层规则（叠压，不平铺）

| 层 | 内容 | z-index | 说明 |
|---|---|---|---|
| L1 bg | 背景板（生成一次，冻结） | 0 | 永不改 |
| L2 hero | 主主体剪贴（真实帧派生） | 3 | 视觉焦点 |
| L3 elements | 支撑元素（标签/数据/道具） | 4-6 | 可叠压 hero 边缘 |
| L4 decor | CSS 装饰（图钉/胶带/印章/红绳） | 7-8 | 最高，盖住连接点 |

**叠压铁律**：L3 必须与 L2 有重叠（叠压连接，不平铺并列）；L4 盖在连接/固定点。
**人脸保护**：任何叠压不得覆盖真实人物脸部（K-04，人物图禁止标签进图，标签走 HTML 叠加）。

## 4. rot 推导规则（纸片感微倾斜）

| 元素角色 | rot 范围 | 规则 |
|---|---|---|
| 主体剪贴（L2） | -2° ~ +2° | 小幅，保持真实感 |
| 支撑标签（L3） | -3° ~ +3° | 比主体略歪，形成"手工感" |
| 装饰（L4） | -8° ~ +8° | 印章/标签条可明显歪 |
| 相邻元素 | 方向相反 | 一个 +2° 则相邻 -2°，避免同向呆板 |

**rot 红线**：主体 ≤3°（过歪读作"放错了"而非"手工拼贴"）；对比面板对称倾斜（左 -2° 右 +2°）。

## 5. timing 推导规则（元素入场时间）

沿用 series-adapt 已沉淀的时序体系（voice boundaries 主时钟 + 句子级同步），
在**元素级**补充入场时机推导：

| 元素角色 | 入场时间 | 依据 |
|---|---|---|
| 背景板（L1） | scene_start + 0.1 | 固定 |
| hero 主体（L2） | scene_start + 0.3（短场景 +0.2） | 固定，不跟语音 |
| 支撑元素（L3） | scene_start + 1.2（短场景 +0.8） | 固定，错峰 |
| 装饰（L4） | scene_start + 2.0 起，错峰 0.5s | 固定，错峰 |
| **内容标签/数据（voice 类）** | **对应语音句 start + 0.2s** | **句子级同步** |
| 变化区标记（change_zone） | 变化发生的语音句 start + 0.2s | 句子级同步 |

**规则**：
- **短场景**（duration ≤ 7s）：所有元素快速入场，绝不跟语音（语音句在末尾，跟语音必一闪）
- **voice 元素可见红线**：`v_t = min(句时间 + 0.2, scene_end - 2.5)`，保证出现后可见 ≥2.5s
- **clamp 红线**：`入场时间 + 动画时长 ≤ scene_end`，否则动画被截断 = 元素一闪
- **每元素声明 `sync_sentence`**（对应旁白句文本），供 compose 做句子级对齐

## 6. 元素契约 schema（scene_plan 落库）

在 scene_plan 的每个元素上落以下字段（schema `beats[].elements[]` 已支持，
本库补充 layout 专属字段语义）：

```json
{
  "element_id": "s01e01",
  "layout_intent": "hero | compare | sequence | change_zone",
  "layer": "bg | hero | element | decor",
  "kind": "img | css",
  "box": [left, top, width, height],
  "rot": 角度,
  "z": 层级,
  "family": "slide | drop | slap | pop | unfold | wipe | mask_reveal | rotate | fade",
  "micro": "sway | lift | pulse | breathe | none",
  "sfx": "paper_slide | tape_press | stamp_thud | string_zip | pin_click | paper_tap | none",
  "sync_sentence": "对应旁白句",
  "entrance_time": "推导后的绝对入场秒数"
}
```

**验收**：每个元素 4 项推导字段（box/rot/z/entrance_time）在 scene_plan 阶段填齐，
compose 阶段只读不改。

## 7. 与现有规范的衔接

- **scene-director**：sub_shot 增加 `layout_intent` 字段；composition_family 由
  layout_intent 推导（§1 映射表），不再凭空选。
- **asset-director**：元素资产按 box 生成/裁剪；背景板独立生成并冻结；真实帧派生
  主体按 box 区域 img2img（`keep-exact-same`）。
- **compose-director**：按元素契约装配（box 定位、rot 旋转、z 叠压、entrance_time
  入场、family/micro/sfx 执行），不临场摆位。
- **反单调规则不变**：相邻 sub_shot 不同 composition_family + 不同 camera_move。

## 8. 词表（copy-paste）

```
LAYOUT_INTENT: hero compare sequence change_zone
BOX: 元素占画布百分比 [left,top,width,height]；hero ≥40%宽+≥50%高；对比面板宽差≤10%
Z:   bg=0 hero=3 element=4-6 decor=7-8   (叠压不平铺；人脸不覆盖)
ROT: 主体≤3° 标签±3° 装饰±8°  相邻反向
TIMING: bg+0.1 hero+0.3 l3+1.2 decor+2.0错峰0.5 voice=句+0.2 clamp end-2.5
RULE: 背景板冻结零漂移 · 布局由意图推导不临场 · 短场景≤7s全快入不跟语音
```
