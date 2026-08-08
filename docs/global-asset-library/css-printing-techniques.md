# VOX 印刷质感 CSS 技术方案（G3）

收集自平面印刷/纸张拼贴设计的常用 CSS 技法，用于替换"简陋的纯 CSS 装饰"。

## 1. 标题印刷质感（.headline 增强）

### 1.1 墨迹印刷（ink press）— 多层 text-shadow 模拟印刷压力

```css
.headline-ink {
  font-family: 'Oswald', 'NotoSansSC-Black', sans-serif;
  font-weight: 900;
  color: #1A1A1A;
  /* 模拟印刷压力：深墨核心 + 轻微扩散 + 纸面阴影 */
  text-shadow:
    0 1px 0 rgba(255,255,255,0.4),          /* 纸面高光 */
    0 2px 1px rgba(0,0,0,0.15),              /* 印刷压痕 */
    0 0 2px rgba(26,25,23,0.8),              /* 墨迹边缘 */
    0 6px 18px rgba(60,45,20,0.28);          /* 纸张投影 */
}
```

### 1.2 套色印刷（duotone overprint）— 混合模式叠加红/黄

```css
.headline-overprint {
  color: var(--ink);
  position: relative;
}
.headline-overprint::after {
  content: attr(data-text);
  position: absolute; left: 0; top: 0;
  color: var(--red);
  mix-blend-mode: multiply;
  transform: translate(2px, 1px);  /* 套色错位 */
  opacity: 0.35;
}
```

### 1.3 反白标题（white on paper）— 高对比块

```css
.headline-inverse {
  background: var(--ink);
  color: #F1E8D0;
  padding: 0.05em 0.2em;
  box-shadow: 0 4px 12px rgba(60,45,20,0.35);
}
```

## 2. 纸张颗粒（grain）— SVG noise 增强

```css
.grain {
  /* 现有 baseFrequency=0.8 太细，印刷颗粒用 0.35-0.5 更明显 */
  background-image: url("data:image/svg+xml,..."); /* baseFrequency 0.45 */
  opacity: 0.35;  /* 比现在 0.09 强，才有纸张粗糙感 */
  mix-blend-mode: multiply;
}
```

## 3. 胶带（tape）— 素材库 SVG 替代纯 CSS

```css
.tape {
  background-image: url('../../assets/shared_library/images/decals/tape_mustard.svg');
  background-size: 100% 100%;
  /* 不再用 background: rgba(212,168,61,0.40) 纯色 */
}
```

## 4. 印章（stamp）— 素材库 SVG 框 + 文字

```css
.stamp {
  font-family: 'NotoSerifSC-Bold', serif;
  background: url('../../assets/shared_library/images/decals/stamp_ring_red.svg') no-repeat center/100% 100%;
  color: var(--red);
  mix-blend-mode: multiply;   /* 印章墨迹融入纸面 */
  -webkit-mask-image: radial-gradient(ellipse, black 85%, transparent 98%);  /* 边缘虚化像盖章 */
}
```

## 5. 图钉（pin）— 素材库 SVG

```css
.pin {
  background-image: url('../../assets/shared_library/images/decals/pin_brass.svg');
  background-size: 100% 100%;
}
```

## 6. 红绳（string）— 素材库 SVG

```css
.string {
  background-image: url('../../assets/shared_library/images/decals/string_red.svg');
  background-repeat: repeat-x;
  background-size: auto 100%;
}
```

## 7. 手绘箭头 — 素材库 SVG

```css
.arrow {
  background-image: url('../../assets/shared_library/images/decals/arrow_ink.svg');
  background-size: 100% 100%;
}
```

## 8. 纸张边缘（torn edge）— clip-path 撕裂

```css
.torn {
  clip-path: polygon(
    0% 3%, 4% 0%, 9% 2%, 15% 0%, 22% 3%, 30% 1%, 38% 4%,
    45% 0%, 52% 2%, 60% 0%, 68% 3%, 76% 1%, 84% 2%, 92% 0%, 100% 3%,
    99% 50%, 100% 97%, 94% 100%, 87% 98%, 79% 100%, 70% 97%,
    62% 100%, 54% 98%, 46% 100%, 38% 97%, 30% 100%, 21% 98%,
    13% 100%, 6% 97%, 0% 100%
  );
}
```

## 9. 高亮标记（marker highlight）— 半透明黄

```css
.highlight {
  background: linear-gradient(100deg, transparent 3%, rgba(212,168,61,0.55) 8%, rgba(212,168,61,0.55) 92%, transparent 97%);
  padding: 0 0.1em;
  box-decoration-break: clone;
}
```

## 字体加载（G1）— @font-face 指向素材库

```css
@font-face { font-family: 'Oswald'; src: url('../../assets/shared_library/fonts/Oswald-Bold.ttf'); }
@font-face { font-family: 'NotoSansSC'; src: url('../../assets/shared_library/fonts/NotoSansSC-Black.ttf'); }
@font-face { font-family: 'NotoSerifSC'; src: url('../../assets/shared_library/fonts/NotoSerifSC-Bold.ttf'); }
@font-face { font-family: 'MaShanZheng'; src: url('../../assets/shared_library/fonts/MaShanZheng.ttf'); }
@font-face { font-family: 'IBM Plex Mono'; src: url('../../assets/shared_library/fonts/IBM-Plex-Mono.ttf'); }
```

## 使用原则

1. 装饰质感来自**素材库素材**（SVG 贴图），CSS 只做定位/动画
2. 印刷感靠**多层 text-shadow + mix-blend-mode: multiply**（墨迹融入纸面）
3. 中文标题优先 NotoSansSC-Black / MaShanZheng（国风）
4. 英文标题优先 Oswald / Anton / BebasNeue
5. 所有素材路径相对 compose 项目目录引用
