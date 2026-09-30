/* API 文档中心 - 接口公告条（渐进增强）
 *
 * 触发条件：文档页渲染出公告（模板片段 API/templates/docs/_announcements.html，
 * 由 docs_views._attach_announcements 提供数据）时，随页面加载本脚本。
 *
 * 三个增强点（脚本不加载时页面依然完整可读，控件默认不显示）：
 *   1) 超长正文折叠：正文超过 4 行时收起并显示「展开全部」，点开看全文；
 *      是否溢出用 scrollHeight / clientHeight 实测，不靠字数猜。
 *   2) 关闭单条公告：写入 localStorage（键 xyapi:announcement:closed，按公告 ID 记录），
 *      下次访问不再提示；仅影响本机浏览器，不影响后台数据与他人。
 *   3) 窗口尺寸变化后重新判定折叠状态（用户手动展开过的不回收）。
 *
 * 依赖：无（不依赖 jQuery / hls 等）。颜色与结构全部在 input.css 的 .announce 组件里。
 */
(function () {
  'use strict';

  // 本机已关闭的公告 ID 列表
  var STORE_KEY = 'xyapi:announcement:closed';
  // 判定「正文是否超过折叠行数」的像素容差：避免亚像素/行高舍入把刚好 4 行误判为溢出
  var OVERFLOW_TOLERANCE = 2;
  // 窗口尺寸变化的去抖时间（ms）
  var RESIZE_DEBOUNCE = 150;

  function readClosed() {
    try {
      var list = JSON.parse(localStorage.getItem(STORE_KEY) || '[]');
      return Array.isArray(list) ? list : [];
    } catch (e) {
      return [];                          // 隐私模式 / 存储被禁用：静默降级为「不记忆」
    }
  }

  function writeClosed(list) {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(list));
    } catch (e) { /* 写不进去不影响本次浏览 */ }
  }

  var closed = readClosed();

  function toggleLabel(toggle, open) {
    var more = toggle.querySelector('[data-announce-more]');
    var less = toggle.querySelector('[data-announce-less]');
    if (more) more.classList.toggle('hidden', open);
    if (less) less.classList.toggle('hidden', !open);
  }

  /* 实测正文是否溢出：先按折叠态量一次，没溢出就撤掉折叠类（不留空白按钮） */
  function syncClamp(card, body) {
    if (card.classList.contains('is-open')) return;   // 用户已展开，不回收
    card.classList.add('is-clamped');
    if (body.scrollHeight <= body.clientHeight + OVERFLOW_TOLERANCE) {
      card.classList.remove('is-clamped');
    }
  }

  function initCard(card, box) {
    var body = card.querySelector('[data-announce-body]');
    var toggle = card.querySelector('[data-announce-toggle]');
    var close = card.querySelector('[data-announce-close]');

    card.classList.add('is-ready');     // 脚本可用后才显示关闭按钮

    if (body && toggle) {
      syncClamp(card, body);
      toggle.addEventListener('click', function () {
        var open = card.classList.toggle('is-open');
        toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        toggleLabel(toggle, open);
      });
    }

    if (close) {
      close.addEventListener('click', function () {
        var id = card.dataset.announcement;
        if (id && closed.indexOf(id) === -1) {
          closed.push(id);
          writeClosed(closed);
        }
        card.remove();
        // 全部关掉后容器会留一块空白，一并移除
        if (!box.querySelector('[data-announcement]')) box.remove();
      });
    }
  }

  function initBox(box) {
    Array.prototype.forEach.call(box.querySelectorAll('[data-announcement]'), function (card) {
      if (closed.indexOf(card.dataset.announcement) !== -1) {
        card.remove();                  // 本机已关闭过，直接不展示
        return;
      }
      initCard(card, box);
    });
    if (!box.querySelector('[data-announcement]')) box.remove();
  }

  Array.prototype.forEach.call(document.querySelectorAll('[data-announcements]'), initBox);

  var resizeTimer = null;
  window.addEventListener('resize', function () {
    if (resizeTimer) window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(function () {
      Array.prototype.forEach.call(document.querySelectorAll('.announce.is-ready'), function (card) {
        var body = card.querySelector('[data-announce-body]');
        if (body) syncClamp(card, body);   // 栏宽变化后行数会变，重新判定
      });
    }, RESIZE_DEBOUNCE);
  });
})();
