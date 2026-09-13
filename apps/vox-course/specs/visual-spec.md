# VOX 视觉风格与动效设计规范 (visual-spec.md)

本规范定义了 VOX 科技纪录片/硬核技术课程的视觉语言、CSS 变量、物理质感组件与 GSAP 时间轴编排标准。

---

## 1. 调色板 (Color System)

| 变量名 | 色值 | 视觉含义 | 典型应用 |
|---|---|---|---|
| `--paper-cream` | `#F3ECE0` | 复古米黄糙纸 | 浅色调查档案卡背景 |
| `--paper-white` | `#FAF8F2` | 报告纯白纸张 | 官方文件、对比卡片 |
| `--paper-dark` | `#16181D` | 工业暗灰纸板 | 极客终端、深色底板 |
| `--paper-manila` | `#E6DBC6` | 牛皮纸档案袋 | 重点标牌、分类附签 |
| `--ink` | `#181614` | 印刷油墨纯黑 | 浅色卡片文字正文 |
| `--terminal-green` | `#00FF41` | CRT 终端荧光绿 | 终端日志、通过印章、字幕左强调条 |
| `--warning-orange` | `#FF5F1F` | 工业警示橙 | 章节编号、警告印章、关键词高亮 |
| `--deep-orange` | `#8C2A00` | 灼烧深橙 | 阴影修饰、警示边框 |
| `--stamp-red` | `#B71C1C` | 官方核准印章红 | 绝密、翻车、废除印章 |
| `--tape-tan` | `rgba(235, 218, 168, 0.72)` | 半透明封箱胶带 | 贴合在卡片边缘的胶带 |

---

## 2. 物理拟真质感与图层堆叠

页面从底到顶的标准 Z-Index 图层结构：

```
z-index: 1   -> 宇宙黑底背景 (#121316)
z-index: 2   -> 背景图片与半透明技术网格 (opacity: 0.35, contrast: 1.15)
z-index: 4   -> 穿梭巨型水印字 (kinetic-massive, 210px font, opacity: 0.16)
z-index: 8   -> 纸张边缘便签与小标签 (tstrip)
z-index: 10  -> 纸张主体卡片 (paper-card, paper-card-dark)
z-index: 11  -> 封箱胶带 (tape, clip-path 梯形)
z-index: 12  -> 黄铜/红色别针与大头针 (pin-brass, pin-red)
z-index: 14  -> 手绘 SVG 标记层 (svg-layer, 红色手绘圈、连线、箭头)
z-index: 15  -> 官方核查重击印章 (stamp, stamp-green, stamp-orange)
z-index: 82  -> 全屏动态高对比字幕条 (#vox-sub-container)
z-index: 85  -> 镜头暗角渐变 (vignette)
z-index: 86  -> CRT 4px 扫描线 (scanlines)
z-index: 90  -> SVG 噪点胶片微粒 (grain, pointer-events: none)
```

---

## 3. 核心 CSS 结构代码

### 3.1 撕纸轮廓 (Torn Paper Clip-Path)
```css
.torn-paper {
  clip-path: polygon(
    0% 2px, 2% 0px, 5% 3px, 9% 1px, 14% 3px, 18% 0px, 23% 3px, 28% 1px, 34% 3px, 39% 0px, 45% 3px, 51% 1px, 57% 3px, 63% 0px, 69% 3px, 75% 1px, 81% 3px, 87% 0px, 93% 3px, 97% 1px, 100% 2px,
    99% 15%, 100% 28%, 99% 42%, 100% 56%, 99% 70%, 100% 84%, 99% 98%,
    98% 100%, 94% 98%, 89% 100%, 83% 97%, 77% 100%, 71% 98%, 65% 100%, 59% 97%, 53% 100%, 47% 98%, 41% 100%, 35% 97%, 29% 100%, 23% 98%, 17% 100%, 11% 97%, 5% 100%, 2% 98%, 0% 99%,
    1% 85%, 0% 70%, 1% 55%, 0% 40%, 1% 25%, 0% 10%
  );
}
```

### 3.2 动态同步字幕条 (VOX Subtitle Box)
```css
#vox-sub-container {
  position: absolute;
  left: 50%;
  bottom: 40px;
  transform: translateX(-50%);
  z-index: 82;
  pointer-events: none;
  text-align: center;
  width: 1600px;
}
.sub-box {
  display: inline-block;
  max-width: 1500px;
  background: rgba(14, 16, 20, 0.94);
  border: 1px solid rgba(255, 95, 31, 0.5);
  border-left: 6px solid var(--terminal-green);
  padding: 12px 32px;
  border-radius: 4px;
  box-shadow: 0 10px 30px rgba(0,0,0,0.85);
  font-family: var(--font-sans);
  font-size: 27px;
  font-weight: 800;
  color: #FFFFFF;
  letter-spacing: 0.8px;
}
.sub-hl {
  color: var(--terminal-green);
  font-weight: 900;
}
.sub-warn {
  color: var(--warning-orange);
  font-weight: 900;
}
```

---

## 4. GSAP 动效编排铁律

1. **印章重击**：
   - 必须有从天而降的重击感：`scale: 2.5 ~ 3.0 -> scale: 1.0`，时长 `0.4 ~ 0.5s`，曲线必须使用 `power3.out` 或 `power4.out`，严禁线性。
   - 伴随微角度回弹（例如初始 -20°，落点 -8°）。
2. **手绘与折线生长**：
   - SVG Path 生长必须使用 `strokeDashoffset` 动画，时长在 `1.5 ~ 4.5s`，配合解说节奏逐渐拉出差距。
3. **字幕进出场微动效**：
   - 字幕显示时轻微浮起（`opacity: 0 -> 1, y: 12 -> 0, duration: 0.25`）。
   - 字幕切换前轻微上移收回（`opacity: 1 -> 0, y: 0 -> -8, duration: 0.20`）。
4. **尾声留白**：
   - 最后一幕解说结束后，画面定格保持 3.5 ~ 4.0 秒，BGM 渐弱淡出：
     `tl.to("#bgm", { volume: 0, duration: 4.0, ease: "power1.in" }, audio_end_time);`
