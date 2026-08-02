# Vox Story Library — 叙事层参考库（series-adapt）

叙事骨架库：为 series-adapt 单集改写阶段提供叙事弧、开场钩子与节奏规则。
与 `vox-look-library.md`（视觉层）、`vox-motion-library.md`（动效层）配套使用。
由 `rewrite-director.md` 引用。

> 来源：提炼自 vox-director（Alisa0808/vox-director, MIT）的 `references/beat-layer.md`，
> 按其原始来源（StudioBinder 三幕结构 / Pixar story spine / AIDA-PAS-BAB 广告框架 /
> Vox 纪录片案例研究等）保留，并适配 series-adapt 的 10 分钟纪录片制式。
> 本项目明确不采用其 AI 视频模型动画路线，仅借用叙事骨架与节奏规则。

## 1. 叙事弧库（改写前必选）

每个弧是一个"beat 形状"——决定开头、转折、收尾落在哪里。改写时按本集内容选一条弧，
然后把 `knowledge_brief.json` 的事实按弧位次重排（不是按源视频顺序照搬）。

| 弧（token） | 适用场景 | beat 形状 |
|---|---|---|
| `timeline` | 历史/演进类（99追忆大多数集） | 起点 → 事件 → 事件 → 转折点 → 现状 → 收尾感悟 |
| `three_act` | 任何有完整叙事的 60s+ 长片 | 建立 → 对抗（上升）→ 解决 |
| `man_in_hole` | 人物故事/低谷反弹/案例 | 风光 → 跌落 → 深化 → 爬出 → 比从前更好 |
| `hook_payoff` | 单一观点集；最安全默认 | 钩子 → 背景 → 展开 → 兑现 → 按钮 |
| `myth_buster` | 纠正误解/争议话题 | 事实先行 → 误区 → 揭穿 → 应信什么 → 收尾 |
| `how_it_works` | 技术原理/系统讲解集 | 钩子 → 是什么 → 2–3 个演示步骤 → 价值 → 收尾 |
| `story_spine` | 团队/单位/个人传奇 | 曾经… → 每天… → 直到有一天… → 因为… → 直到最后… → 从此… |
| `origin` | 创始/起源叙事 | 世界 → 火花 → 一跃 → 挣扎 → 突破 → 今天 |
| `listicle` | "N 种方式/装备对比" | 承诺 → 条目 → 条目 → … → #1 → 总结 |
| `pas` / `bab` / `aida` | 广告属性强的集（武器外贸宣传类） | 痛点→激化→解法→证明→CTA / 前→后→桥→CTA / 注意→兴趣→渴望→行动 |

**topic→arc 启发式**（99追忆适用举例）：
- 历史推进/某型号研制全程 → `timeline`
- 总师/人物传记单集 → `man_in_hole` 或 `story_spine`
- 某一技术难点（装甲、火炮、发动机）→ `how_it_works`
- 纠正外界偏见/争议（"99式抄袭 T-72？"）→ `myth_buster`
- 外贸型号推销类 → `pas` / `bab`

**选择规则**：同一季内弧位次可重复，但**相邻两集不得使用同一条弧的相同位次模板**（如
连续两集都是"起点→事件→…→收尾感悟"读作流水账）。当 brief 事实结构支持多条弧时，
优先 `man_in_hole`（vox-director 实测评分最高的弧）。

## 2. 开场钩子（第一句就要兑现承诺）

短片标准是 hook ≤3s；10 分钟纪录片放宽为：**开场第一句（≤15s）必须完成承诺建立**——
观众在句尾就知道"这集要回答什么"。

hook 模式库（每集开场选一个，避免"在 XX 年，XX 国……"式平铺）：

| 模式 | 结构 | 例子（坦克史向） |
|---|---|---|
| `surprising_stat` | 反直觉数字开篇 | "1999 年阅兵，世界第一次见到它时，没人相信这是中国造的——直到它顶住了 T-80U 的正面一击。" |
| `direct_question` | 提问制造悬念 | "为什么西方情报机构直到 2009 年还在争论：那辆阅兵坦克里装的到底是不是中国炮？" |
| `secret_reveal` | 宣称秘密/不为人知 | "这辆坦克的炮塔里，藏着一个从 1959 年就开始的赌局。" |
| `pattern_interrupt` | 反常识场景切入 | "1961 年，北京郊区一个兵工厂的夜班工人，正在手敲一辆苏联坦克的装甲板。" |
| `outcome_tease` | 先给结果再倒叙 | "它是世界上第一辆装备主动防护的现役主战坦克。但它差一点根本没机会上阅兵场。" |
| `mistake_callout` | 指出一个普遍错误认知 | "大多数资料说 99 式是从 T-72 抄来的。这个说法错在两个地方。" |
| `pain_point` | 指出当时的困境 | "1984 年，中国陆军的装甲部队还在用 1959 年的底盘，而苏联已经服役了 T-80。" |
| `urgent_warning` | 紧迫性开场 | "如果 1985 年那场边境演习多持续两周，中国装甲兵的历史会被彻底改写。" |
| `experiment_story` | 小实验/小场景钩子 | "1987 年深冬，一位 60 岁的老人爬进了一辆样车，里面连座椅都是手工焊的。" |

**禁止**：以"大家好，今天我们来聊……"开场；以年份平铺开场超过一句。

## 3. 节奏规则（10 分钟纪录片适配）

vox-director 的短片节奏（30s→6–8 beats / 60s→10–12 beats，单镜 3–6s）不能直接照搬。
纪录片适配为**分层节拍**：

| 层级 | 规则 |
|---|---|
| 全片三幕 | 开场 hook（30–60s）→ 主体（70–80% 时长）→ 收尾（30–60s，回扣开场钩子） |
| 小节拍点 | **每 60–90s 必须有一个小节拍点**：一个关键引语、一个反直觉数据、一个转折、一次亮相（新坦克/新人物/新工厂）。小节拍点是"情绪呼吸点"，也是 compose 阶段预留高光动画的锚点 |
| 视觉变化密度 | 每 4–7s 一个视觉事件（元素入场/图表更新/子镜头切换/字幕卡）——长场景不等于死静画面，见 `vox-motion-library.md` 的 element_motion 规则 |
| 场景窗口 | 场景切换跟随 voice boundaries（永不句中切），0.5–0.7s 句后 hold，情绪重拍 1.5–3.4s（scene-director 既有规则，保持不变） |
| 结尾三选一 | `hard_cut`（高光句戛然而止，驱动重看）· `quick_cta`（订阅/下一集预告 ≤15s）· `loop_close`（末句回扣首句） |

**每集必有一个"高光节拍"**：全片视觉能量最高的 10–15s（如阅兵亮相、首射成功、总师语录），
它是 hero 飞行元素（见 motion-library）与动效峰值唯一的落点。

## 4. 词表（copy-paste）

```
ARCS:  timeline three_act man_in_hole hook_payoff myth_buster how_it_works
       story_spine origin listicle pas bab aida
HOOKS: surprising_stat direct_question secret_reveal pattern_interrupt
       outcome_tease mistake_callout pain_point urgent_warning experiment_story
BEATS: 开场 hook 30-60s · 小节拍点每 60-90s · 视觉事件每 4-7s · 结尾三选一
```

## 5. 与既有改写规范的衔接

- 本库补充 `rewrite-director.md` 的 Step 2（结构叙事）：先选弧，再按弧位次组织 hook/context/body/climax/conclusion 五段
- `visual_direction` 的 `animation` 字段可标注"高光节拍"（`highlight: true`），compose 阶段据此分配 hero 元素与动效峰值
- 保持 rewrite-director 既有的 speech-rate 数学、术语表、无破折号等规则不变
