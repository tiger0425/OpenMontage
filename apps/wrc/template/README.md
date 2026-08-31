# WRC 竖屏合成模板生成器（v1，已验收）

> 所属地图：[wayfinder:map - WRC拉力视频→中文抖音竖屏流水线](https://github.com/tiger0425/OpenMontage/issues/58)
> 决议来源：[prototype: hyperframes 风格模板生成器](https://github.com/tiger0425/OpenMontage/issues/65)（2026-08-23 用户验收通过）
> 消费方：管线落地（#66）——本生成器即管线的**合成（compose）环节**

## 用法

```bash
python generate_composition.py <episode.json> <assets_dir> <out_index.html>
```

- `episode.json`：单集脚本（wrc_episode.schema.json 契约 + 每幕 `display` 块 + `visuals[].asset_path` + `audio_s`），见 `episode-lower-display.json` 示例
- `assets_dir`：该集资产目录（sN.wav、scene*.jpg/mp4、背景视频）
- 输出：hyperframes@0.7.109 兼容 index.html（1080x1920 竖屏），然后 `npx hyperframes@0.7.109 render` 出片

## 布局原型（display.layout）

| 原型 | 适用 | 结构 |
|---|---|---|
| `split` | 上图+玻璃卡（s1/s3/s4/s5 类）| 媒体区(0~1000px) + 红分隔线(1000) + 玻璃卡(flex:1 到底) |
| `center` | 全屏居中列（s0/s2/s6 类）| 徽章/标题/钩子 + 媒体盒 + 列表/数字卡 + punch |
| `ending` | 结尾（s7 类）| 媒体盒 + 标题 + 钩子 + 关注 CTA |

## display 块字段（split/center/ending 通用子集）

- `badge` 红胶囊徽章 · `question` 大标题 · `hook{main,sub}` 红字钩子（+副字）
- `tag` 玻璃卡标签 · `title{main,highlight}` 标题（红色强调段）· `sub` 副文
- `list[{emoji,text,badge,hot}]` 列表卡 · `numbers[{key,label,value,countup,highlight}]` 数字卡（countup 滚动）
- `vs{before{label,value},after{label,value}}` 以前/现在对比行 · `label` 胶囊副文
- `punch` 金句 · `cta` 关注按钮 · `extra_img` 玻璃卡底部附图
- `visuals[]`：`{type: image|clip, desc, asset_path, offset_hint?}`（clip 为源视频动态片段）

## 用户验收的几何参数（勿随意改）

- 媒体区高 **1000px**；钩子 top **166px**；图片 center top **66%**、宽 86%、max-height **560px**（`object-fit:contain` 黑底）
- 红分隔线 = 玻璃卡 `border-top:3px solid #ff3b30`，位于 y=1000
- 玻璃卡 `flex:1` 铺满到底，`padding:56px 48px 100px`（底部留 100px，内容不贴底）
- **对比行/副文必须渲染在玻璃卡内部末尾**（margin 16/14px）——绝不要做成媒体区悬浮层
- 背景：单 `<video loop muted>` brightness 0.62 全屏循环（不要双视频 track-0，lint 会报重叠）
- 媒体元素必须有 `id`（GSAP 交叉淡化 `#s{i}-v{k}` 定位）；非首张 `opacity:0` 起步

## 关键坑（历史教训，改代码前必读）

1. **每幕外层 div 必须 `class="clip"` + data-start/duration/track-index**——漏了整片冻结在首帧（PSNR≈41dB 全同）
2. **悬浮卡定位锚**：`position:absolute;bottom:36` 若挂在媒体区**兄弟**节点，会锚到整个场景(1920px) → 落到屏幕最底压水印。vs/label 只能进玻璃卡内部
3. split 图片必须**居中卡片式**（透明底露背景），不能整块不透明铺满（会挡住背景飞驰）
4. 钩子元素要有 `id`（GSAP 引用），不能只有 data-hf-id
5. 渲染需 `danger-full-access` + `$env:npm_config_cache` 指工作区（地图 Notes）
6. **场景媒体片段（type=clip 的 video）绝不能加 `loop`**——循环播放会压到下一幕内容上（背景循环视频的 loop 在 bgv 处单独保留）
7. **场景媒体视频必须有 `data-start`/`data-duration` 时间窗**——否则 hyperframes 不拥有播放权，片段播完后的帧会**脱离场景容器持续显示**（表现为"有一张图一直在中间没消"，且 lint 报 `media_missing_data_start`）。实测坑：
   - `data-start` 要设为**交叉淡入时刻**（场景起点 + 该 visual 的淡入偏移），`data-duration` = 幕长 − 淡入偏移。
   - 若 `data-start` = 场景起点，片段会在不可见阶段（opacity:0）就把前段播完——可见时已是片段**尾巴**（可能是不相关的采访/人像帧），观众以为"视频被取消了"。
   - 片段文件时长建议 ≥ 幕长（本项目 15s/16s vs 幕长 ~13s/14s），保证可见窗口内始终在动。
8. **split 媒体卡的 img 尺寸 CSS 是雷区**（实测组合坑，勿改回）：
   - `width:86%;height:auto;max-height:560px;object-fit:contain` **直接放 img 上** → 本渲染环境下高度计算异常，卡片被放大到 ~790px 高，压住玻璃卡。
   - 正确做法：**div 包裹**（`width:58%;max-height:400px;overflow:hidden`），内层 img/video 用 `width:100%;height:auto;display:block;object-fit:contain`。
   - 包裹层内层**不要加 `height:100%`**（auto 高度父容器里会再次异常放大）。
   - id 挂在包裹层上（GSAP 交叉淡化 `#s{i}-v{k}` 定位它），`opacity:0` 初始态也在包裹层。
9. **`render_split` 的 tag 渲染**：`el()` 的第 5 个位置参数是 `cls` 不是 `inner`——tag 的 `<span>` 要传 inner（第 4 位），否则 class 属性里塞进 HTML、标签胶囊不显示。

## 验证状态

- 下集数据（8 幕，126.63s）全流程跑通：生成 → lint 0 结构 error → 渲染 → 用户逐幕验收
- 8 幕逐帧核验：split 幕背景全幅透出（YAVG 74~91），无遮挡、无悬浮卡压图、水印不被挡
- 2026-08-23 第二单（Citroën Xsara 悬挂漏洞，10 幕）补坑后验收：片段正片可见、无残留帧、卡片 625×353 不压玻璃卡、年份语音按"年"正确朗读
