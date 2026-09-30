/* 全局交互：daisyUI 弹窗 + 页头下拉框 + 提示条关闭
 * - XYConfirm(message, opts) -> Promise<boolean>：daisyUI <dialog class="modal"> 确认框
 * - 声明式用法：给任意 <form data-confirm="提示文案">，提交前自动弹确认；
 *   可选 data-confirm-title / data-confirm-ok / data-confirm-danger="1"。
 * - 下拉框：页头的主题 / 语言 / 用户菜单 / 移动端菜单都是 <details class="dropdown">，
 *   浏览器原生行为只支持「再点一次 summary」收起，点页面其它地方不会关；
 *   这里统一补上「点外部即收起」，并保证同时只展开一个。
 * - 提示条：给容器加 data-dismissable、给关闭按钮加 data-dismiss，点击即移除该容器
 *   （纯前端移除，不落库；刷新后消息本身已不在会话里）。
 */
(function () {
  'use strict';

  var dialog = null;
  var msgEl = null;
  var titleEl = null;
  var okBtn = null;
  var resolveFn = null;

  function ensureDialog() {
    if (dialog) return dialog;
    dialog = document.createElement('dialog');
    dialog.className = 'modal';
    dialog.innerHTML =
      '<div class="modal-box max-w-sm">' +
        '<h3 class="text-base font-bold" data-xy-title>' + gettext('确认操作') + '</h3>' +
        '<p class="mt-2 text-sm text-base-content/70" data-xy-msg></p>' +
        '<div class="modal-action">' +
          '<button type="button" class="btn btn-ghost btn-sm" data-xy-cancel>' + gettext('取消') + '</button>' +
          '<button type="button" class="btn btn-primary btn-sm" data-xy-ok>' + gettext('确认') + '</button>' +
        '</div>' +
      '</div>' +
      '<form method="dialog" class="modal-backdrop"><button>' + gettext('关闭') + '</button></form>';

    titleEl = dialog.querySelector('[data-xy-title]');
    msgEl = dialog.querySelector('[data-xy-msg]');
    okBtn = dialog.querySelector('[data-xy-ok]');

    function settle(result) {
      if (resolveFn) { var fn = resolveFn; resolveFn = null; fn(result); }
    }
    dialog.querySelector('[data-xy-cancel]').addEventListener('click', function () { settle(false); dialog.close(); });
    okBtn.addEventListener('click', function () { settle(true); dialog.close(); });
    dialog.addEventListener('cancel', function (e) { e.preventDefault(); settle(false); dialog.close(); });

    document.body.appendChild(dialog);
    return dialog;
  }

  /**
   * 确认弹窗
   * @param {string} message 提示文案
   * @param {{title?:string, confirmText?:string, danger?:boolean}} [opts]
   * @returns {Promise<boolean>}
   */
  function XYConfirm(message, opts) {
    opts = opts || {};
    ensureDialog();
    titleEl.textContent = opts.title || gettext('确认操作');
    msgEl.textContent = message || '';
    okBtn.textContent = opts.confirmText || gettext('确认');
    okBtn.className = 'btn btn-sm ' + (opts.danger ? 'btn-error' : 'btn-primary');
    return new Promise(function (resolve) {
      resolveFn = resolve;
      dialog.showModal();
    });
  }

  window.XYConfirm = XYConfirm;

  // 声明式：<form data-confirm="…"> 提交前统一走 daisyUI 确认框
  document.addEventListener('submit', function (e) {
    var form = e.target.closest('form[data-confirm]');
    if (!form || form.dataset.xyConfirmed === '1') return;
    e.preventDefault();
    XYConfirm(form.dataset.confirm, {
      title: form.dataset.confirmTitle || gettext('确认操作'),
      confirmText: form.dataset.confirmOk || gettext('确认'),
      danger: form.dataset.confirmDanger === '1',
    }).then(function (ok) {
      if (!ok) return;
      form.dataset.xyConfirmed = '1';
      form.submit();
    });
  });

  /* ---------- 页头下拉框：点外部自动收起 ----------
   * 只做「收起」，不干预展开：点 summary 的展开/收起仍由浏览器原生 details 行为负责。
   * 时序上本监听器先于浏览器的默认动作（切换 open）执行，因此：
   *   点外部 → 关掉全部；点另一个下拉 → 关掉除它以外的；点下拉内部（选主题等）→ 保持展开。 */
  document.addEventListener('click', function (e) {
    var current = e.target.closest('details.dropdown');
    document.querySelectorAll('details.dropdown[open]').forEach(function (box) {
      if (box !== current) box.open = false;
    });
  });

  /* ---------- 提示条关闭 ----------
   * 声明式：容器加 data-dismissable，内部关闭按钮加 data-dismiss。
   * 只做移除，不做动画 —— 未加载本脚本时按钮不显示（见模板里的 .hidden 兜底由属性驱动）。 */
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-dismiss]');
    if (!btn) return;
    var box = btn.closest('[data-dismissable]');
    if (box) box.remove();
  });
})();
