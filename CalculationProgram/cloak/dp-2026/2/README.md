# dp-2026-2 斗篷

> **定位**：该斗篷仅用于本地复现 —— 只用 JS 完成客户端斗篷，用于研究斗篷原理、给检测方提供样本以强化检测系统；**不用于服务端，避免用于灰产**。
> **执行端**：客户端浏览器　**语言**：JavaScript

## 0. 一句话说明

页面一进来先被 CSS 盖成"全屏空白 + Loading"；JS 随即启动反调试，并在 `DOMContentLoaded` 后依次过三层判断（第四层鼠标行为检测已写好、当前**未启用**）。全部通过才插入 iframe 显示落地页，并把遮罩透明化；**任何一层不通过就直接 return，页面永远停在空白 + Loading**。

***

## 1. 目录与文件清单

```
2/
├── dp-code.js              # 主逻辑：URL 参数解析 + 三层判断 + 放行
├── README.md
└── 辅助工具/
    ├── 斗篷页面.html        # 演示宿主页（"白页"）：只放遮罩结构，不放任何内容
    ├── 斗篷辅助CSS.css      # 遮罩样式：全屏空白 + 居中旋转圆环 + 淡出态
    ├── 反调试.js            # 反调试：IIFE 立即执行，检测到 DevTools 进无限 debugger
    └── 主页面.html          # 演示落地页（被 iframe 嵌入的目标页）
```

| 文件            | 关键内容                                                                                                               |
| ------------- | ------------------------------------------------------------------------------------------------------------------ |
| `dp-code.js`  | `urlParams` 参数读取、`firstCheck` / `secondCheck` / `thirdCheck` / `fourthCheck`、`showMainPage` 放行、`closeMask` 备用关闭    |
| `斗篷辅助CSS.css` | `.dp-mask`（全屏遮罩，`z-index: 2147483647`）、`.dp-mask--fade-out`（透明化 + `pointer-events: none`）、`.dp-mask-spinner`（旋转圆环） |
| `反调试.js`      | `debugger` 计时、控制台探针、原生函数完整性校验；开关 `window.stopAntiDebug()`                                                          |
| `斗篷页面.html`   | `<head>` 里按顺序引入 CSS → 反调试.js → dp-code.js；`<body>` 里放遮罩 DOM                                                        |
| `主页面.html`    | 演示用落地页，实际投放时换成你自己的落地页地址                                                                                            |

**加载顺序（照抄即可）**

```html
<link rel="stylesheet" href="斗篷辅助CSS.css">
<script src="./反调试.js"></script>
<script src="../dp-code.js"></script>
...
<body>
  <div class="dp-mask">
    <div class="dp-mask-spinner"></div>
  </div>
</body>
```

两点注意：

1. `dp-code.js` 放在 `<head>` 是安全的 —— 它在加载期只读 `location.search`，**所有 DOM 操作都在** **`DOMContentLoaded`** **里**。
2. 遮罩 DOM 要贴在 `<body>` 直属层级，**不要放进带** **`transform`** **/** **`filter`** **的容器**，否则 `position: fixed` 会以该容器为参照，遮罩覆盖不满全屏。

***

## 2. 运行流程

### 2.1 阶段一：CSS 先出"空白 + Loading"

遮罩不是 JS 生成的，而是宿主页里写死的 DOM（`.dp-mask` + `.dp-mask-spinner`），样式全部来自 `斗篷辅助CSS.css`：纯色铺满 + 圆环旋转动画。所以**JS 还没执行时，页面已经是"加载中"的样子**；即使 JS 报错，页面也只是永远"加载中"。

### 2.2 阶段二：反调试立即启动

`反调试.js` 是 IIFE，引入即执行，不等任何调用。**检测节奏是这一层的重点**：

1. **加载时先同步自检一次** —— 早于页面渲染、早于斗篷放行。所以"先打开控制台、再刷新页面"会在渲染任何内容之前就被暂停住，**不会出现"主页面先渲染出来、1 秒后才被反调试抓到"**；
2. 之后每 1000ms 复检一次，兜住"页面打开之后才打开控制台"的情况。

三种检测手段：

| 手段            | 原理                                                                                                                                    |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `debugger` 计时 | 执行动态生成的 `debugger` 语句，被暂停则耗时 > 200ms；`performance.now` 与 `Date.now` 双时钟取大者，防单一计时器被 hook。源码每次带随机后缀重新生成，"不在此处停止"点不掉                     |
| 控制台探针         | 给临时元素挂 `id` getter 再 `console.log`，控制台真在渲染才会触发 —— 不依赖暂停，绕过"停用断点"                                                                      |
| 原生函数完整性       | 校验 `Function.prototype.toString`/`setInterval`/`setTimeout`/`performance.now`/`console.log` 是否仍为 `native code` —— 改写它们是绕过前两种手段的常见前置动作 |

命中任意一条即进入无限 `debugger`（`setTimeout` 递归实现，避免误判时把标签页彻底卡死）。

对外提供两个接口：

| 接口                        | 用途                                                       |
| ------------------------- | -------------------------------------------------------- |
| `window.antiDebugCheck()` | 同步复检，返回 `true` / `false`。**斗篷放行前必须调用**，返回 `false` 时不允许放行 |
| `window.stopAntiDebug()`  | 关闭反调试，之后 `antiDebugCheck()` 恒为 `true`（自己人排查用）            |

### 2.3 阶段三：主核心判断（`DOMContentLoaded`）

| 层 | 函数                  | 判什么                                                                         | 不通过的结果                  |
| - | ------------------- | --------------------------------------------------------------------------- | ----------------------- |
| 零 | `antiDebugPassed()` | 反调试脚本已加载，且复检通过（没被调试、关键原生函数没被 hook）                                          | `return`，保持空白 + Loading |
| 一 | `firstCheck()`      | URL 必须同时带 `kw`、`gad_source`、`gad_campaignid`、`gclid`，且 `gad_source === '1'` | `return`，保持空白 + Loading |
| 二 | `secondCheck()`     | `kw`（可能是 base64）命中 `kw_db` 里任意一组名称                                          | `return`，保持空白 + Loading |
| 三 | `thirdCheck()`      | 是否桌面（电脑）环境                                                                  | `return`，保持空白 + Loading |
| 四 | `fourthCheck()`     | 鼠标行为是否像人                                                                    | **当前未启用**（代码保留，注释状态）    |

> **第零层是放行的硬前置**：反调试是 1s 轮询的，而斗篷在 `DOMContentLoaded`（几十毫秒）就会放行；只靠轮询挡不住"先开控制台再刷新"。把复检放在最前，等于在放行前再同步确认一次，把窗口压到最小。
> 代价：`dp-code.js` 因此**依赖** `反调试.js` —— 没引入它（或被拦截）时不会放行，页面永远停在空白 + Loading。

### 2.4 阶段四：放行

```js
showMainPage();
```

1. 取第二层命中规则的第 2 项作为 iframe 地址；
2. 用 `insertAdjacentHTML('beforeend', ...)` **追加**一个全屏 iframe（`position:fixed; 100%×100%`，`z-index: 2147483646`）；
3. 给遮罩加 `.dp-mask--fade-out` —— 遮罩渐隐成透明（`opacity: 0` + `pointer-events: none`），**元素保留在 DOM 里**。

> 顺序不能反：先插 iframe 再淡出遮罩，才能做到"遮罩淡出、下面就是落地页"。也**不能用** **`body.innerHTML`** **整体覆盖** —— 那样遮罩会被一起销毁，就没有淡出效果了。

### 2.5 完整流程

```
用户进入页面
 ├─ CSS 生效：全屏空白 + Loading
 └─ 反调试.js 加载 → 立即同步自检一次（DevTools 已开则当场暂停，什么都渲染不出来）
DOMContentLoaded
 ├─ 第零层 antiDebugPassed() 复检不通过 / 反调试缺失 ─→ return（保持空白 + Loading）
 ├─ 第一层 firstCheck()      参数不齐 / gad_source ≠ 1 ─→ return
 ├─ 第二层 secondCheck()     kw 不在 kw_db             ─→ return
 ├─ 第三层 thirdCheck()      非桌面环境                 ─→ return
 ├─ 第四层 fourthCheck()     ← 已写好，当前注释未启用
 └─ 放行 showMainPage()
      ├─ 追加全屏 iframe（src = 命中规则的落地页）
      └─ 遮罩加 .dp-mask--fade-out（透明化，元素保留）
```

***

## 3. 各层判定细节

### 3.1 第一层：参数完整性

- `kw`：广告关键词，由你在最终到达网址里用跟踪模板传入（如 `{keyword}`）；
- `gclid`、`gad_campaignid`：Google 点击后自动附加；
- `gad_source`：Google 自动附加，这里**强校验必须等于** **`'1'`**，其它来源（如 `2`）一律拒绝；
- 四个值只要有一个为空（缺失或空串）就返回 `false`。注意第一层用的是 `!kw` 真值判断，所以"参数不存在"和"参数存在但为空"都会被拦。

### 3.2 第二层：关键词命中

- 命中规则：把 `kw_db` 每组的第 1 项按 `|` 拆开，逐个 `trim` + 转小写，用 `indexOf` 做**包含匹配**，命中任意一个即通过；
- 命中后会把这一组记进全局 `matchedRule`，放行时取它的第 2 项当 iframe 地址；
- 用 `indexOf` 而不用 `new RegExp`：名称里带 `+ ? ( )` 这类字符时不会被当成正则元字符（抛错或错配）；
- 空名称（如写成 `'有道|'`）会被跳过 —— 否则 `indexOf('')` 恒为 0，任何 `kw` 都会命中。

**base64 关键词**：`kw` 会先经 `tryDecodeBase64()` 尝试解码，解码失败则按原文处理。判定顺序是「字符集 + 长度是 4 的倍数 → `atob` 解码 → 解码结果必须是合法 UTF-8 文本」，最后一步是必需的 —— 否则 `test` 这种本身合法的 base64 会被误判成编码值。

### 3.3 第三层：桌面环境判定

移动端伪装很多（**iPadOS 13+ 的 UA 与桌面 Mac 完全一致**、安卓可开"桌面版网站"），所以不做单点判断，而是"硬信号 + 多路加权打分"。

硬信号（命中任意一条即判非桌面）：

| 信号                                               | 说明                       |
| ------------------------------------------------ | ------------------------ |
| `navigator.userAgentData.mobile === true`        | Chromium 的 UA-CH，浏览器自己声明 |
| UA 命中 `Android / iPhone / iPad / Mobile / …`     | 常规移动端标识                  |
| `platform === 'MacIntel'` 且 `maxTouchPoints > 1` | 唯一可靠的 iPadOS 识别方式        |

软信号打分（`score > 0` 才认定为桌面）：

| 信号                                               | 权重      |
| ------------------------------------------------ | ------- |
| `(hover: hover) and (pointer: fine)` —— 主输入是鼠标   | +2      |
| `(hover: none) and (pointer: coarse)` —— 主输入是触摸  | −2      |
| `maxTouchPoints === 0`（完全没有触摸）                   | +2      |
| `innerWidth >= 1024` / `< 768`                   | +2 / −2 |
| `screen.availHeight < screen.height`（有任务栏/菜单栏占位） | +1 / −1 |
| `platform` 命中移动正则 / 桌面正则                         | −2 / +1 |
| UA 含 `Windows NT / Macintosh / X11 / CrOS`       | +1      |

视口那一项特意给中间段（768–1023）**不给分** —— 安卓"桌面版网站"模式会把视口撑到 980 左右，正好落在该区间，不能让它加分。

### 3.4 第四层：鼠标行为检测（已写好，当前未启用）

异步：鼠标行为需要观察，所以它不返回布尔值，而是把结论交给回调。

硬信号（立刻否决）：`e.isTrusted === false`（脚本伪造的事件）、坐标 `(0, 0)`、同一时刻（`dt ≤ 1ms`）移动超过 300px。

行为统计：对采样点算两个**变异系数**（标准差 ÷ 平均值）—— 相邻移动的时间间隔、移动速度。机器人的典型特征是两者都恒定（`setInterval` + 等距位移），判定规则是「**有一项呈不规则波动就算人**」，宁可放过也不误杀真实用户。

***

## 4. 使用说明

### 4.1 本地复现（最快上手）

**第一步**：用浏览器打开演示宿主页，并带上四个参数（中文参数建议 `encodeURIComponent`）：

```
file:///P:/XiaoYingAPI/CalculationProgram/cloak/dp-2026/2/辅助工具/斗篷页面.html?kw=有道&gad_source=1&gad_campaignid=123&gclid=abc
```

**第二步**：桌面浏览器下应当看到"全屏空白 + 圆环转约 0.35 秒 → 露出 `主页面.html` 的内容"。若看不到变化，见 [第 5 节](#5-常见问题)。

**测试矩阵**（`kw_db` 默认有两组：`有道|有道翻译`、`雷电`）：

| URL 情况                                                | 预期结果                     |
| ----------------------------------------------------- | ------------------------ |
| `?kw=有道&gad_source=1&gad_campaignid=123&gclid=abc`    | **放行**，显示落地页             |
| `?kw=有道翻译&gad_source=1&…`                             | **放行**（包含匹配）             |
| `?kw=有道&gad_campaignid=123&gclid=abc`（缺 `gad_source`） | 一直空白 + Loading           |
| `?kw=有道&gad_source=2&gad_campaignid=123&gclid=abc`    | 一直空白 + Loading           |
| `?kw=微信&gad_source=1&gad_campaignid=123&gclid=abc`    | 一直空白 + Loading（`kw` 不在库） |
| `?kw=5pyJ6YGT&gad_source=1&…`                         | **放行**（base64 解出"有道"）    |
| 以上任一，用手机打开                                            | 一直空白 + Loading（第三层拒绝）    |

### 4.2 换成 base64 关键词

把 `kw_db` 里名称保持明文即可（第二层会自动解码传入的 `kw`）。生成编码值的写法：

```js
// 浏览器控制台：把关键词编成 UTF-8 的 base64
var encoded = btoa(String.fromCharCode.apply(null, new TextEncoder().encode('有道')));
// "5pyJ6YGT"
// 拼 URL 时必须再 encodeURIComponent，否则 base64 里的 + 会被解析成空格
'?kw=' + encodeURIComponent(encoded) + '&gad_source=1&gad_campaignid=123&gclid=abc';
```

### 4.3 接到真实站点上

1. 在目标页 `<head>` 里按顺序引入 `斗篷辅助CSS.css`、`反调试.js`、`dp-code.js`（实际投放建议内联或托管到自己的域名）；
2. 在 `<body>` 直属层级贴上遮罩 DOM（`<div class="dp-mask"><div class="dp-mask-spinner"></div></div>`）；
3. 修改 `dp-code.js` 顶部的 `kw_db`：

```js
var kw_db = [
    ['有道|有道翻译', 'https://你的落地页地址/'],   // [名称组（| 分隔）, 落地页URL]
    ['雷电', 'https://另一个落地页/'],
];
```

1. 在 Google Ads 的最终到达网址里带上 `kw`：

```
https://你的域名/landing?kw={keyword}&gclid={gclid}&gad_campaignid={campaignid}&gad_source=1
```

> `gclid`、`gad_campaignid`、`gad_source` 由 Google 自动附加，`kw` 需要你自己用值跟踪模板传入。

### 4.4 调试技巧

| 场景                 | 做法                                                                                                |
| ------------------ | ------------------------------------------------------------------------------------------------- |
| DevTools 一开就被反调试卡住 | 在 Console 里执行 `window.stopAntiDebug()`，再按继续（F8）即可跳出；**被暂停时也能执行**                                  |
| 页面一直空白，想知道卡在哪层     | Console 依次执行 `antiDebugPassed()` / `firstCheck()` / `secondCheck()` / `thirdCheck()`，看谁返回 `false` |
| 自己测试时不想被反调试拦       | 先执行 `window.stopAntiDebug()`，第零层就会直接通过（`antiDebugCheck()` 恒为 `true`）                              |
| 想跳过判断直接看落地页        | `secondCheck(); showMainPage();` —— `showMainPage` 依赖 `matchedRule`，必须由 `secondCheck()` 先写入       |
| 想彻底移除遮罩（而不是只透明）    | 调用 `closeMask()`（备用实现：淡出后把元素从 DOM 移除）                                                             |

### 4.5 启用 / 停用第四层

主核心里第四层当前是**注释状态**，取消注释即可启用（启用后"没等到真实鼠标移动一律不放行"，意味着无鼠标的自动化会话将永远看到空白页）：

```js
/* 取消这段注释即启用第四层 */
fourthCheck(function (isHuman) {
    if (!isHuman) return;
    showMainPage();
});
// 同时注释掉下面这行"直接放行"
// showMainPage();
```

### 4.6 换配色、调节奏

```css
/* 斗篷辅助CSS.css · .dp-mask 顶部 */
--dp-mask-bg: #fff;              /* 遮罩背景色 */
--dp-mask-spinner-track: #e3e3e3;/* 圆环底色 */
--dp-mask-spinner-active: #09f;  /* 圆环旋转高亮色 */
--dp-mask-fade-duration: 0.35s;  /* 淡出时长 */
```

***

## 5. 常见问题

| 现象                                      | 原因 / 处理                                                                                                                                                               |
| --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 永远停在空白 + Loading                        | 逐层排查（见 4.4）。最常见是 `gad_source` 不等于 `1`、`kw` 不在 `kw_db`、或用了手机/模拟器                                                                                                       |
| 页面永远空白，而且 DevTools 也没被卡住                | 第零层拦下的：`反调试.js` 没引入或被拦截（`window.antiDebugCheck` 不存在），或被浏览器扩展包装了 `console.log` 导致 `tampered()` 判真。控制台看 `typeof window.antiDebugCheck` 与 `window.antiDebugCheck()` 即可确认 |
| 遮罩透明了但页面点不动                             | 不该出现：`.dp-mask--fade-out` 自带 `pointer-events: none`。若你改过类名/样式，这条要保留                                                                                                   |
| iframe 区域白屏                             | 目标站返回了 `X-Frame-Options: DENY/SAMEORIGIN` 或 CSP `frame-ancestors` 限制，不允许被嵌套                                                                                           |
| 遮罩没盖住页面某些内容                             | 两个检查点：① 遮罩 DOM 是否被放进了带 `transform/filter` 的容器（`fixed` 参照系被改变）② `斗篷辅助CSS.css` 是否真的加载成功。宿主页元素的 `z-index` 不可能超过遮罩的 `2147483647`                                          |
| 控制台每秒多一条 `<div>` 记录                     | 那是反调试的**控制台探针**（`console.log(decoy)`），属于正常现象，不是报错；执行 `stopAntiDebug()` 后不再增长                                                                                          |
| 改了 `--dp-mask-fade-duration` 后淡出变慢/兜底过晚 | CSS 变量与 `MASK_FADE_FALLBACK_MS`（`closeMask` 兜底 600ms）是两处配置，一起改                                                                                                        |
| 演示页换路径后 iframe 加载不出来                    | `kw_db` 里写的是绝对路径 `P:\\XiaoYingAPI\\...`；换机器/换目录后改成相对路径或新的绝对路径                                                                                                         |

***

## 6. 配置项速查

| 位置            | 配置                                                         | 默认                               | 作用                    | <br />         |
| ------------- | ---------------------------------------------------------- | -------------------------------- | --------------------- | :------------- |
| `dp-code.js`  | `kw_db`                                                    | 两组演示数据                           | \`\[名称组（              | 分隔）, 落地页URL]\` |
| `dp-code.js`  | `MASK_SELECTOR` / `MASK_FADE_CLASS`                        | `.dp-mask` / `dp-mask--fade-out` | 必须与 CSS、HTML 一致       | <br />         |
| `dp-code.js`  | `MASK_FADE_FALLBACK_MS`                                    | `600`                            | `closeMask` 的兜底移除时长   | <br />         |
| `dp-code.js`  | `DESKTOP_SCORE_THRESHOLD`                                  | `0`                              | 第三层阈值，调大更严格（更容易判为非桌面） | <br />         |
| `dp-code.js`  | `MOUSE_WATCH_MS` / `MOUSE_MIN_MOVES` / `MOUSE_VARIANCE_CV` | `3000` / `4` / `0.2`             | 第四层观察时长、最少移动次数、波动门槛   | <br />         |
| `斗篷辅助CSS.css` | `--dp-mask-*`                                              | 见 4.6                            | 遮罩配色与淡出时长             | <br />         |
| `反调试.js`      | `CHECK_INTERVAL` / `PAUSE_THRESHOLD`                       | `1000` / `200`                   | 检测间隔、判定为"被调试"的耗时门槛    | <br />         |
| `反调试.js`      | `window.stopAntiDebug()`                                   | —                                | 关闭反调试                 | <br />         |

***

## 7. 已知局限与风险

1. **客户端判断都可被伪造**：UA、`platform`、`maxTouchPoints`、事件都能被脚本或代理改写。这些层只能挡住"无意的伪装"（如 iPad 桌面 UA、安卓桌面版网站），挡不住刻意针对。
2. **反调试只提高成本**：`view-source:`、curl/代理直接抓源码、禁用 JS、换无调试器的浏览器都不受影响；其 `toString` 校验本身也可被伪造返回串。
3. **第三层会误伤**：树莓派这类 ARM Linux 桌面（`platform` 含 `armv/aarch64`）会被扣分；Windows 平板在"平板模式"下主指针变粗，也可能被判非桌面。
4. **第四层会误杀真实用户**：没动鼠标（例如进来就用键盘）的人不放行 —— 这是它换取"挡机器人"能力的固有代价。
5. **`closeMask()`** **当前没有调用方**：`showMainPage()` 已改为"只透明、不移除"，`closeMask` 作为备用实现保留。
6. **第零层是"不通过就不放行"**：反调试脚本缺失/被拦截/被误判为 hook 时，斗篷不会放行 —— 这是有意的安全默认。若你只想部署 `dp-code.js`，需要自己删掉主核心里的第零层那一行。
7. **反调试的时序已收紧，但仍有窗口**：加载时同步自检 + 放行前复检，把"先开控制台再刷新"堵住了；但"页面打开之后、复检之前"（毫秒级）打开控制台，仍然只可能被 1s 轮询抓到。想更紧就调小 `CHECK_INTERVAL`。

***

## 8. 合规提示

本斗篷的实现目标是：按 `kw`、`gclid`、`gad_campaignid`、`gad_source` 等参数识别流量来源，对非目标环境（移动端、审查环境、无鼠标行为的自动化会话）持续展示一个"空白 + Loading"页，对目标流量展示落地页；同时用反调试对抗页面分析。

此类"对审查方展示与用户不同内容"的做法，与主流广告平台（含 Google Ads）关于落地页一致性与审查规避的政策相冲突，可能引发账户封禁、投放受限等后果。本目录仅用于本地复现与研究（含为检测方提供样本以强化检测），**请勿用于线上投放或灰产场景**；如确需评估投放，请先完成法务与合规确认，并由业务方明确风险承担方式。
