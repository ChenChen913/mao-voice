# mao-voice Logo / 应用图标 · 生图提示词

> 用法：主提示词直接复制给生图模型；备选概念按需替换。
> 目标：得到一个能在 16px 托盘图标里仍然认得出的 Windows 应用图标，而不是一张插画。

## 一、品牌简报

- 产品：mao-voice，Windows 本地语音输入工具。
- 名字里的「mao」接近「猫/喵」的发音，可以借用猫的听觉、警觉、轻盈，但**不要画成卡通猫**。
- 品牌性格：安静、聪明、可靠、贴近人、克制。
- 核心意象：声音、波形、倾听、把话变成文字。
- 视觉语言：几何、扁平、单色为主、少量蓝色强调；不发光、不 3D、不做拟物。
- 使用场景：Windows 任务栏 / 托盘 16px、桌面快捷方式 48px、开始菜单、安装包、GitHub 头像、README 顶部。

## 二、设计约束

- 图形必须在 16×16 像素下仍然可辨识，不能依赖细节。
- 只用一个视觉隐喻，不要同时塞猫、声波、对话气泡、字母、麦克风。
- 不包含任何文字、字母、单词、数字；不要出现「mao」「voice」字样。
- 不使用渐变、发光、霓虹、玻璃拟态、3D、投影、写实材质。
- 图形居中，四周留足安全边距（约图标宽度的 12%–16%）。
- 主色：炭黑 `#1E1E1E`；强调蓝 `#4A90D9`；浅色版纸白 `#F5F7FA`。
- 交付：1024×1024 主图、圆角方形版、透明背景符号版、单色版。

## 三、主推概念

**「三根声波构成的猫耳轮廓」**

三根粗细一致的垂直波形竖条居中排列，中间最高、两侧递减；最外侧两根的顶部微微向外折，形成两个极简的猫耳负形。远看是声波，近看才意识到是猫的耳朵。图形整体接近一个圆角方形里的「声音头像」，克制、可缩小。

### 主提示词（英文，直接复制）

```text
Design a flat vector app icon for a Windows desktop voice-input utility called mao-voice. Square 1024x1024 canvas, rounded-square icon with a subtle 22% corner radius, solid charcoal background #1E1E1E. Centered symbol: three vertical rounded soundwave bars of equal width, the center bar tallest and the two side bars shorter, forming a calm symmetrical waveform. The two outer bars bend slightly outward at their tops to suggest two minimal cat ears without drawing a literal cat. Symbol color: vivid calm blue #4A90D9, flat fill, no gradient. Generous safe padding around the symbol, about 14% of the canvas. Geometric, precise, minimal, premium, quiet instrument aesthetic. Crisp edges, high contrast, readable at 16x16 pixels. No text, no letters, no words, no numbers. No 3D, no bevel, no glow, no neon, no gradient, no drop shadow, no glassmorphism, no mockup, no device frame, no cartoon cat face, no microphone, no speech bubble. Flat vector only. Professional Windows 11 utility icon, not a marketing illustration.
```

### 负面提示词（英文，直接复制）

```text
text, letters, words, numbers, typography, logo text, "mao", "voice", gradient, glow, neon, light effect, 3D, bevel, emboss, drop shadow, glassmorphism, translucent, blur, cartoon cat, cat face, whiskers, tail, microphone, speech bubble, play button, sound equalizer UI, photo, realistic texture, mockup, phone screen, desktop screenshot, watermark, signature, clutter, multiple symbols, asymmetric composition, thin hairline strokes
```

## 四、备选概念

### 备选 A：声波折成 M

```text
Flat vector app icon for "mao-voice". Charcoal rounded square #1E1E1E background. A single continuous blue #4A90D9 waveform line starts low on the left, rises into two soft peaks and descends to the right, subtly echoing an M shape without being a letter. The line has uniform thickness, rounded caps, and generous padding. Minimal, geometric, calm, readable at 16px. No text, no letters, no gradient, no glow, no 3D, no shadow, no microphone, no cat face.
```

### 备选 B：倾听的负空间

```text
Minimal flat app icon for a voice-input tool. Rounded square charcoal #1E1E1E icon. A blue #4A90D9 rounded speech-bubble silhouette whose top edge has two soft upward notches, reading simultaneously as cat ears and as a listening ear. Inside the bubble, three short vertical waveform bars in negative space. Flat, geometric, one color, no text, no gradient, no glow, no 3D, no shadow, readable at 16px, generous padding, premium and quiet.
```

### 备选 C：只有波形，最抽象

```text
Flat vector Windows app icon. Charcoal #1E1E1E rounded square. Five vertical rounded bars in calm blue #4A90D9, symmetric, center tallest, forming a clean audio waveform with a subtle upward flare on the outermost bars. No cat reference, no text, no letters, no gradient, no glow, no 3D, no shadow. Simple, precise, legible at 16px, generous safe area.
```

## 五、变体提示词

### 浅色版

```text
Same icon design, light version: paper-white #F5F7FA rounded square background, charcoal #1E1E1E waveform symbol, same geometry and padding. Flat, minimal, no gradient, no shadow, no text.
```

### 单色 / 透明符号版

```text
Same symbol only, transparent background, solid charcoal #1E1E1E flat vector, no rounded square, no text, no effects, centered, generous padding, suitable for tray icon and monochrome UI.
```

### 16px 托盘简化版

```text
Simplified 16x16 tray icon version of the same concept: three vertical blue #4A90D9 bars only, no ears, no background, centered, crisp pixel-aligned edges, high contrast, no text, no gradient.
```

## 六、生成后怎么验收

1. 缩到 16×16：还能看出「声音」或「耳朵」的轮廓，没有糊成一团。
2. 放到深色和浅色任务栏：都能看清，不靠阴影。
3. 遮住颜色只看形状：仍然是一个有记忆点的符号，而不是通用波形。
4. 没有出现文字、字母、麦克风、卡通猫脸。
5. 图形与圆角方形边缘之间的留白均匀，没有贴边。
6. 主图、浅色版、透明版、单色版四套放在一起时，是同一个品牌。

## 七、交付清单

- `logo-1024.png`：主图，圆角方形，炭黑底 + 蓝色符号
- `logo-light-1024.png`：浅色版
- `logo-symbol-transparent-1024.png`：透明背景符号
- `logo-mono-1024.png`：单色版
- `favicon-16.png` / `favicon-32.png` / `favicon-48.png`
- `mao-voice.ico`：Windows 多尺寸图标（16/24/32/48/64/128/256）
- 一段 100 字以内的设计说明：符号含义、颜色含义、为什么能在 16px 下识别
