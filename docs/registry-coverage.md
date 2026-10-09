# 动效资源覆盖对照：官方 registry vs UI2V

> 快照日期：2026-09-30
> 用途：回答「某个题材该去哪儿找」——官方 `hyperframes add` 还是 UI2V `ui2v_fetch`。
> 这是一份**会过期的快照**，末尾附复现命令，需要时重新生成。

## 1. 两个池子的总量与形态

| | 官方 registry | UI2V |
| --- | --- | --- |
| 条目数 | **394** | **1262** |
| 构成 | 164 `block` + 222 `component` + 8 `example` | 1262 个 `hyperframes:block`（无 component） |
| 元数据 | 丰富：`title` / `description` / `tags`（386/394 有 tags） | 名称 + `capabilityTags`（实为安全标签：`crypto`/`can-make-purchases`，**不是题材标签**） |
| 画面比例 | — | 横屏 1156 / 竖屏 104 |
| 组织方式 | 按**原语/类型**分类（motion-primitive / transition / typography / overlay / shader…） | 按**内容系列**聚集（kallaway / vox / hero…） |
| 时长特征 | 多为原语级短片 | `5.0s` 一个值就占 **671 条（53%）**，是统一批次的卡片 |

一句话概括：**官方 = 可组合的原语 + 组件效果片段；UI2V = 成品段落 + 成套卡片系列。**

## 2. 按题材对照（名称/标签匹配，方向性参考）

`倍数 = UI2V ÷ 官方`。同一作品可能同时命中多个题材，列和 > 总数属正常。

| 题材 | 官方 | UI2V | 倍数 | 谁更深 |
| --- | --- | --- | --- | --- |
| 讲解 / 教育 / 图解 | 13 | 110 | **8.5×** | UI2V |
| 标题 / 章节 / 分节卡 | 13 | 92 | **7.1×** | UI2V |
| 数据可视化 / 图表 / 统计 | 21 | 125 | **6.0×** | UI2V |
| 金融 / 商业 | 1 | 4 | 4.0× | UI2V（样本小） |
| 角色 / 吉祥物 / 虚拟形象 | 3 | 8 | 2.7× | UI2V（样本小） |
| 音乐 / 节拍 / 音频可视化 | 5 | 12 | 2.4× | UI2V |
| AI / 对话 / Agent | 10 | 21 | 2.1× | UI2V |
| 地图 / 地理 | 8 | 16 | 2.0× | UI2V |
| 轮播 / 画廊 / 图片堆叠 | 37 | 66 | 1.8× | UI2V |
| Logo / 片头 / 片尾 | 13 | 18 | 1.4× | 接近 |
| 字幕 / 标题条 | 17 | 18 | 1.1× | 接近 |
| Lower Third | 13 | 13 | 1.0× | 接近 |
| 3D / 景深 / 运镜 | 44 | 46 | 1.0× | 接近 |
| 社交 / 竖屏 / 短视频 | 34 | 34 | 1.0× | 接近 |
| 粒子 / VFX | 33 | 29 | 0.9× | 接近 |
| 代码 / 终端 / 开发者 | 24 | 18 | 0.8× | 接近 |
| 手绘 / 白板 | 13 | 11 | 0.8× | 接近 |
| 背景 / 氛围 / 纹理 | 26 | 17 | 0.7× | 官方 |
| UI 样机 / 设备 / App | 49 | 35 | 0.7× | 官方 |
| 转场 / 擦除 | 75 | 42 | 0.6× | 官方 |
| 着色器 / WebGL / GPU | 33 | 16 | 0.5× | 官方 |
| 动态字体 / 文字特效 | 63 | 25 | 0.4× | 官方 |
| 产品 / 展示 / 电商 | 90 | 34 | 0.4× | 官方 |
| B-roll / 实拍素材 | 29 | 10 | 0.3× | 官方 |
| 播客 / 访谈 / 出镜 | 10 | 1 | 0.1× | 官方 |

> 匿名分类只能覆盖 UI2V 的 **648/1262（51%）**；剩下的一半是品牌/项目名，无法从名称判断题材。

## 3. UI2V 独有的东西——不是"某个题材"，而是"整套系列"

严格说，**官方没有任何一个题材是为 0 的**（每个题材官方都有 1–13 个打底）。
UI2V 的独有性体现在下面三层，官方**没有对应的"系列"概念**：

### 3.1 成套卡片 / Lower-third 变体库（最大差异）

| 系列 | 数量 | 占比 | 是什么 |
| --- | --- | --- | --- |
| `kallaway-*` | **300** | 24% | 一律题为 `… — Kallaway Style Card`，大量 `t2-lt-*`（lower third 变体：waveband / underbar / typedname / titlebar / ticker / tagrow / statline / spotlightname / social…） |
| `vox-*` | **107** | 8% | 一律题为 `… — Vox Explainer Style Card`，同样一套 `vox-explainer-t2-lt-*`（typecard / sticky / stamp / ribbon / rail / indextab / highlight / bracket…） |

这两族合计 **407 条（32%）**，本质是"同一个 lower-third/卡片母题 × 数百种变体"。
官方对应的 `lower-third` 只有 **13 条**。**这是 UI2V 唯一真正"官方给不了"的量级差异。**

### 3.2 风格化的 hero 动效原语

`hero-*` **74** 条：`hero-glass-refract`、`hero-tape-wipe`、`hero-loader-morph`、
`hero-card-flip3d`、`hero-orbit-nodes`、`hero-liquid-blob`、`hero-grid-ripple`、
`hero-ribbon-sweep`、`hero-constellation`… 属于同一类"hero 动效"，但**美术风格**官方没有同款。

### 3.3 其它成套系列

`creator-*` 20（章节/引用/时间线/关系图，含中文标题）、`studio-*` 8（12s 长成品段）、
`transitions-*` 13（按 scale/radial/push/light/grid/distortion… 成组）、`carousel-*` 22、
`caption-*` 17、`code-*` 13、`broll-*` 10。

## 4. 官方更深的题材（优先用官方）

官方在这些题材上**既有量又有体系**，且是第一方、`hyperframes add` 一行装好、路径自动重映射：

- **产品 / 展示 / 电商**（90 vs 34）、**UI 样机 / 设备 / App**（49 vs 35）
- **转场 / 擦除**（75 vs 42，含 14 个内置 GPU shader 转场）
- **动态字体 / 文字特效**（63 vs 25）、**着色器 / WebGL**（33 vs 16）
- **播客 / 访谈 / 出镜**（10 vs 1）、**B-roll / 实拍**（29 vs 10）
- **组件类效果片段**：官方有 222 个 `component`（grain / shimmer / 各类 overlay），UI2V 完全没有 component。

## 5. 结论：什么时候去哪个池子

| 你要的东西 | 去哪儿 | 怎么拿 |
| --- | --- | --- |
| 转场、着色器、文字特效、粒子、grain/overlay 等**原语与组件** | **官方** | `npx hyperframes add <name>` |
| 产品展示、UI 样机、播客、B-roll | **官方** | `npx hyperframes add <name>` |
| **成套 lower-third / 卡片变体**（挑风格） | **UI2V** | `ui2v_fetch` → `list`(capability_tag/关键词) → `install` |
| **VOX 式讲解卡 / 数据统计卡** | **UI2V** | 同上（`vox-*` / `kallaway-*`） |
| 风格化 hero 段、12s 成品镜头 | **UI2V** | 同上 |
| Hero/atelier 定制动效 | **都不用** | 自己写（注册表积木在 atelier 模式被禁） |

**判定顺序**：先 `npx hyperframes catalog --json` 找官方 → 官方没有**同量级的成套方案**时，再去 UI2V → 拿到后用 `hyperframes_compose` 渲染。

## 6. 数据局限

- UI2V 的**题材标签不可用**：`capabilityTags` 是安全/权限标签（`crypto`、`can-make-purchases`），
  题材只能从 slug / title 猜，分类覆盖率仅 51%。
- 官方 tags 由作者维护，颗粒度不统一（`motion-primitive` 这类"类型"标签与 `podcast` 这类"题材"标签混在一起）。
- 数量 ≠ 质量。UI2V 有大量同一母题的近似变体（5.0s 批次占 53%），去重后有效多样性远低于 1262。
- 社区包各有 license，进商用前逐个核（详见 `ui2v-community-blocks.md`）。

## 7. 复现命令

```bash
# 官方：全量清单
curl -s https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry/registry.json

# 官方：单条目元数据（含 tags / description）
curl -s https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry/blocks/<name>/registry-item.json

# UI2V：总量
curl -s https://convex.illli.cc/api/query -H "Content-Type: application/json" \
  -H "Convex-Client: npm-1.31.0" \
  -d '{"path":"motions:countPublicSkills","args":{},"format":"json"}'

# UI2V：分页全量（cursor 翻页，numItems<=100）
curl -s https://convex.illli.cc/api/query -H "Content-Type: application/json" \
  -H "Convex-Client: npm-1.31.0" \
  -d '{"path":"motions:listPublicPageV4","args":{"sort":"newest","numItems":50},"format":"json"}'

# 或者直接用本项目的工具
python -c "
import json
from tools.tool_registry import registry
registry.discover()
t = registry.get('ui2v_fetch')
print(json.dumps(t.execute({'operation':'count'}).data))
print(json.dumps(t.execute({'operation':'list','sort':'newest','limit':5}).data, indent=1))
"

# 重建本地发现索引（官方 + UI2V；离线可用）
python -c "from tools.tool_registry import registry; registry.discover(); \
print(registry.get('ui2v_fetch').execute({'operation':'refresh_index'}).data)"
```
