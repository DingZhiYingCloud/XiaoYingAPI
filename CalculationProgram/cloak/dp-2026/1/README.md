# dp-2026-1 斗篷脚本 · 分析与优化报告

> 分析对象：[dp-code.js](./dp-code.js)（已补充详细中文注释）
> 关联文件：`辅助工具/tg.html`（落地页样例）、`辅助工具/通用注入代码.txt`（页面注入模板）
> 本版本状态：已移除反调试自保护与移动端 `mousemove` 触发逻辑；遮罩改为"真正移除"而非置透明

## 0. 结论速览

1. 当前流程为**三关卡闸门**式判定：参数齐全 → 关键词命中 → 桌面环境，全部通过才切换页面，否则一律保持"空白 + Loading"。结构清晰，无冗余分支。
2. 上线前唯一的阻断项是配置：`confArr` 仍是占位值 `['Name', 'Link']`，整条链路实际处于空转状态（P0-01）。
3. 已修复的高危缺陷：遮罩此前只被"置为透明"，而 `.haoniuwlls` 覆盖全屏且未设置 `pointer-events: none`，会导致**页面看得见却点不动**；现在改为真正 `remove()`。
4. 仍需业务侧决策的：移动端命中后**永久白屏**（真实移动用户同样如此）（P1-04）。

***

## 1. 文件与依赖清单

| 文件                  | 角色                     | 关键点                                            |
| ------------------- | ---------------------- | ---------------------------------------------- |
| `dp-code.js`        | 斗篷主逻辑                  | 参数校验 + 关键词匹配 + 桌面判定 + 页面替换 + 遮罩移除               |
| `辅助工具/通用注入代码.txt`   | 注入到宿主页的片段              | 提供 `<ul class='haoniuwlls'>` 遮罩占位 + 外部 CSS 引用     |
| `辅助工具/tg.html`     | 落地页样例                  | iframe 的目标页；其内部把全站 `<a>` 的 `href` 统一改写为固定地址    |
| 外部 `custom.css`     | 遮罩样式（squarespace 域名托管）  | 全屏白底遮罩 + Loading 转圈动画，均由此文件定义；**未加载则遮罩完全失效** |

依赖关系：`dp-code.js` 能否命中"空白 + Loading"这一前置状态，完全取决于注入模板的 DOM 结构（`.haoniuwlls`）与外部 CSS 是否同时生效。

***

## 2. 执行流程

### 2.1 页面初始状态：空白 + Loading（由 CSS 提供，非 JS 生成）

遮罩来自宿主页**注入的 HTML 结构**（`<ul class='haoniuwlls'><li></li></ul>`），样式来自外部 `custom.css`，实际内容如下：

```css
*{padding:0;margin:0}
body{min-height:100vh}
img{width:100%;cursor:pointer}
ul.haoniuwlls{width:100%;height:100%;position:fixed;left:0;top:0;
              background:rgba(255,255,255,.99);z-index:1000}
ul.haoniuwlls li{width:5vh;height:5vh;border:4px solid #e3e3e3;
                 border-top:4px solid #09f;border-radius:50%;
                 animation:haoniuwllsiwuyh 1s linear infinite;
                 margin:auto;margin-top:47.5vh;list-style:none}
@keyframes haoniuwllsiwuyh{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}
```

要点：

* `position: fixed` + `100% × 100%` + `z-index: 1000` + `rgba(255,255,255,.99)` → 全屏近不透明遮罩。
* `li` 的 `border-top` 蓝色 + 无限旋转动画 → 即肉眼看到的 **Loading 转圈**。
* **没有 `pointer-events: none`** → 只要该元素还在 DOM 里，它就会截获全屏点击（这正是必须 `remove()` 的原因）。

### 2.2 三道关卡

| 关卡 | 判定内容                                                                                        | 不通过的结果          |
| -- | ------------------------------------------------------------------------------------------- | --------------- |
| 1  | URL 同时存在 `kw`、`gclid`、`gad_campaignid`                                                       | 直接 `return`，保持空白 + Loading |
| 2  | 归一化后的 `kw` 命中 `confArr` 中某条正则                                                                 | 直接 `return`，保持空白 + Loading |
| 3  | `isDesktopLike()` 返回 `true`                                                                  | 直接 `return`，保持空白 + Loading |

补充说明：

* 关卡 1 只读这 3 个参数（**不是"读取全部参数"**），其余查询参数一律忽略。
* `kw` 归一化：转小写 + 去掉**全部空格**（含词中间空格），使 `Air Pods` 与 `airpods` 命中同一规则。
* 关卡 2 是"三参数齐全"之外的必要条件——**参数齐全 ≠ 一定切换**，未命中关键词同样什么都不做。
* 关卡 3 的 `screen.height !== screen.availHeight` 本质是"系统是否存在任务栏/菜单栏"，属经验判断。

### 2.3 通过后的动作

1. `swapBodyToIframe(url)`：`document.title` 改写为硬编码的 `'site'`，再用 `body.innerHTML` 把整页替换为「全屏 iframe（`100% × 100vh`）+ 空的 `<ul class="haoniuwlls">`」。原页面 DOM 被整体丢弃，但**已加载的脚本、定时器、监听器仍在后台运行**。
2. 移除遮罩：`document.getElementsByClassName(OVERLAY_CLASS)[0].remove()`，真正把全屏遮罩从 DOM 中摘除，恢复页面可点击。

### 2.4 完整流程

```
用户进入页面
 └─ 外部 custom.css 生效：全屏白底遮罩 + Loading 转圈（空白 + Loading）
脚本加载 → DOMContentLoaded
 ├─ 关卡 1：kw / gclid / gad_campaignid 齐全？
 │    └─ 否 → return（保持空白 + Loading）
 ├─ kw 归一化（小写 + 去空格）
 ├─ 关卡 2：命中 confArr 中某条关键词？
 │    └─ 否 → return（保持空白 + Loading）
 ├─ 关卡 3：是桌面环境？
 │    └─ 否 → return（保持空白 + Loading，移动端即走此分支）
 ├─ swapBodyToIframe(命中配置的 URL)：整页替换为全屏 iframe
 └─ 移除 .haoniuwlls 遮罩
```

### 2.5 分支结果矩阵

| 参数齐全 | 命中关键词 | 桌面环境 | 结果                       |
| ---- | ----- | ---- | ------------------------ |
| ✗    | —     | —    | 保持空白 + Loading           |
| ✓    | ✗     | —    | 保持空白 + Loading           |
| ✓    | ✓     | ✗    | 保持空白 + Loading（移动端不处理）    |
| ✓    | ✓     | ✓    | 全屏替换为 iframe，遮罩被移除        |

***

## 3. 问题清单

### P0 · 阻断上线

| 编号    | 位置             | 问题                              | 影响                                                                                     | 建议                                       |
| ----- | -------------- | ------------------------------- | -------------------------------------------------------------------------------------- | ---------------------------------------- |
| P0-01 | `confArr`（配置表） | 仍是占位值 `['Name', 'Link']`        | 关卡 2 几乎不可能命中；即便命中，`iframe src="Link"` 也是无效地址                                             | 填入真实 `[关键词, 落地页URL]`，并确认目标页允许被 iframe 嵌套 |
| P0-02 | 外部依赖           | 遮罩结构与 `custom.css` 均为外部依赖，脚本内无兜底 | 移除遮罩处直接取 `[0]`；若注入缺失，该值为 `undefined`（当前有 `if (overlay)` 保护，但缺失时页面会漏出原始内容而非白页）             | 上线前用 `辅助工具/tg.html` + 注入模板做全链路自测          |

### P1 · 高风险

| 编号    | 位置                                     | 问题                                                         | 影响                                                     | 建议                                             |
| ----- | -------------------------------------- | ---------------------------------------------------------- | ------------------------------------------------------ | ---------------------------------------------- |
| P1-01 | `kw.toLowerCase().replaceAll(' ', '')` | `String.prototype.replaceAll` 属 ES2021，老 WebView / 旧浏览器不支持 | 抛 `TypeError` → 整个 `DOMContentLoaded` 回调中断，任意关卡都不会执行 | 改为 `replace(/\s+/g, '')`                       |
| P1-02 | `swapBodyToIframe`                     | 无 `onerror`、无加载超时兜底                                         | 目标站返回 `X-Frame-Options: DENY` 或 CSP `frame-ancestors` 限制时，遮罩已被移除，用户看到纯白屏且无法回退 | 增加加载超时检测，失败时保留遮罩或恢复原页面                         |
| P1-03 | 关卡 1                                   | 只校验参数"存在"，不校验取值与来源                                          | 手工拼接 `?kw=xxx&gclid=1&gad_campaignid=1` 即可复现切换效果，斗篷可被人工/竞品轻易验证  | 校验 `gclid` 长度与字符集，叠加 `document.referrer` 等辅助判断 |
| P1-04 | 关卡 3                                   | 非桌面环境（移动端）直接 `return`，遮罩永不移除                                 | **移动端真实用户与审查流量一样，永远停在空白 + Loading**，若该落地页有移动端投放会 100% 无转化 | 确认这是预期策略；若否，需增加移动端处理分支                         |
| P1-05 | 遮罩 CSS                                 | `z-index` 仅 `1000`，且为外链加载                                     | 宿主页若有不低于 1000 的元素（如 bootstrap 的 `.navbar-static-top` 同样是 1000），白页可能漏出内容；外链 CSS 下载完成前原页面内容可见（内容闪现） | 用 DevTools 逐一核对层叠关系；CSS 可考虑内联关键样式               |

### P2 · 健壮性

| 编号    | 位置                    | 问题                                                                         | 影响                                    | 建议                                    |
| ----- | --------------------- | -------------------------------------------------------------------------- | ------------------------------------- | ------------------------------------- |
| P2-01 | `new RegExp(confArr[i][0])` | 配置片段直接参与正则构造，未转义；关键词含 `+ ? ( ) [` 等元字符会异常匹配或抛 `SyntaxError`，且未包 `try/catch` | 异常中断整个回调（同 P1-01 的后果）                 | 转义配置片段后再构造正则，并把匹配包进 `try/catch`       |
| P2-02 | 整体缺少异常兜底              | `DOMContentLoaded` 回调与两个函数均无错误处理                                           | 任一环节抛错都会让页面停在空白 + Loading，且（反调试已移除后）报错会直接出现在控制台 | 对外层回调做一次统一 `try/catch`，失败时保持遮罩不动      |

### P3 · 可维护性与性能

| 编号    | 位置                     | 问题                                                     | 建议                                               |
| ----- | ---------------------- | ------------------------------------------------------ | ------------------------------------------------ |
| P3-01 | `confArr` 结构           | 用下标表达"关键词 / 落地页"，可读性差                                   | 改为对象数组：`{ pattern: 'xxx', url: 'https://...' }` |
| P3-02 | 配置分散                   | `'site'` 标题、`OVERLAY_CLASS`、`confArr` 分散在文件各处            | 统一收敛到顶部 `CONFIG` 区块，并注明修改注意事项                    |
| P3-03 | `swapBodyToIframe`     | 先把 `body` 换成「iframe + 空的遮罩占位」，随后又立刻移除该占位                 | 可直接不创建该 `<ul>`，少一次 DOM 变更                        |
| P3-04 | 可观测性                   | 无任何命中/异常上报，线上无法评估效果                                    | 用 `navigator.sendBeacon` 上报命中事件（需自行评估合规风险）         |
| P3-05 | 正则构造                   | 循环内重复 `new RegExp`                                      | 配置量增大时预编译缓存                                      |
| P3-06 | 原页面残留                  | `body.innerHTML` 整体替换后，原页面的脚本、定时器、监听器仍在后台运行            | 若非必要，替换前先清理页面级定时器/监听                             |

***

## 4. 修复建议片段

### 4.1 关键词正则转义（P2-01）

```js
// 把配置中的关键词转义为字面量，避免 + ? ( ) [ ] 等元字符破坏匹配
function escapeRegExp(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

try {
  if (new RegExp(escapeRegExp(confArr[i][0].toLowerCase())).test(kw)) { /* ... */ }
} catch (e) {
  // 匹配异常不应影响后续流程
}
```

### 4.2 兼容老浏览器（P1-01）

```js
// replaceAll 属 ES2021，老 WebView 不支持
kw = kw.toLowerCase().replace(/\s+/g, '');
```

### 4.3 iframe 加载失败兜底（P1-02）

```js
// 加载超时则移除 iframe 并恢复遮罩，避免用户停在纯白屏
var timer = setTimeout(function () {
  document.body.innerHTML = '';
  document.body.appendChild(overlay);
}, 8000);
```

### 4.4 配置结构化（P3-01 / P3-02）

```js
var CONFIG = {
  OVERLAY_CLASS: 'haoniuwlls',
  PAGE_TITLE: 'site',
  RULES: [
    { pattern: 'telegram|tg|飞机', url: 'https://xxx.example.com/lp/index.html' },
  ],
};
```

***

## 5. 上线前检查清单

- [ ] `confArr` 已填入真实关键词与落地页地址，并逐条验证命中效果（P0-01）
- [ ] 目标落地页允许被 iframe 嵌套（无 `X-Frame-Options` / CSP `frame-ancestors` 限制）（P1-02）
- [ ] 宿主页已注入 `.haoniuwlls` 结构，外部 `custom.css` 可正常加载，白页不漏内容（P0-02、P1-05）
- [ ] 桌面端验证：命中后 iframe 显示正常，且**页面可以正常点击**（遮罩已移除）
- [ ] 移动端验证：确认"永久空白 + Loading"是预期行为（P1-04）
- [ ] 在目标机型的最低版本浏览器中验证脚本无 API 报错（P1-01）
- [ ] 确认手工拼接 `kw/gclid/gad_campaignid` 无法被轻易复现（P1-03）

***

## 6. 待确认事项

1. **移动端"永久空白 + Loading"是否为最终策略？** 该分支目前对所有移动端访问者生效，包括真实用户。
2. **关键词配置的维护方式？** 人工改代码，还是后续接入接口/配置中心下发。
3. **是否需要多落地页分流？** 影响 `confArr` 的结构设计（P3-01）。
4. **iframe 加载失败时的期望表现？** 停留白屏，还是回退到遮罩/原页面（P1-02）。

***

## 7. 合规提示

本脚本的实现目标是根据 `kw`、`gclid`、`gad_campaignid` 等参数，对不同来源的访问者呈现不同内容（并向非目标环境展示空白页）。此类做法通常与主流广告平台（含 Google Ads）关于落地页一致性和审查规避的政策相冲突，可能引发账户封禁、投放受限等后果。建议在实际投放前完成合规评估，并由业务方明确风险承担方式。
