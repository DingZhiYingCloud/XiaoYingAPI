/* 全局交互弹窗（daisyUI 实现，替代浏览器原生 confirm/alert）
 * - XYConfirm(message, opts) -> Promise<boolean>：daisyUI <dialog class="modal"> 确认框
 * - 声明式用法：给任意 <form data-confirm="提示文案">，提交前自动弹确认；
 *   可选 data-confirm-title / data-confirm-ok / data-confirm-danger="1"。
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
})();
