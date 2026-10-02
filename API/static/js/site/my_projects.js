/* 我的项目 · 项目详情页交互
   - 复制凭据（APPID / APPSECRET；密钥处于打码状态时也复制真实值）
   - 显示 / 隐藏 APPSECRET
   - 危险操作二次确认（form[data-confirm]）
   仅项目详情页加载（见 templates/my_projects/detail.html 的 {% block js %}）。
   提示文案一律由模板的 data-* 属性传入，本文件不含硬编码文案。 */
(function () {
  'use strict';

  // 复制文本：优先异步剪贴板 API，非安全上下文回退 execCommand
  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    var area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.top = '-1000px';
    document.body.appendChild(area);
    area.select();
    try { document.execCommand('copy'); } catch (e) { /* 复制失败不阻断页面 */ }
    document.body.removeChild(area);
    return Promise.resolve();
  }

  // 取复制按钮所在容器里的被复制内容
  function sourceText(button) {
    var box = button.parentElement;
    var source = box ? box.querySelector('[data-copy-source]') : null;
    if (!source) return '';
    // 密钥区块：明文在 hidden 的 span 里，打码时也应复制到真实值
    var real = source.querySelector('[data-secret-real]');
    return (real ? real.textContent : source.textContent).trim();
  }

  // 复制成功后把按钮文案短暂换成"已复制"
  function flashLabel(button) {
    var label = button.querySelector('[data-copy-label]');
    var copied = button.getAttribute('data-copied');
    if (!label || !copied) return;
    var original = label.textContent;
    label.textContent = copied;
    setTimeout(function () { label.textContent = original; }, 1200);
  }

  function bindCopy() {
    document.querySelectorAll('[data-copy-target]').forEach(function (button) {
      button.addEventListener('click', function () {
        copyText(sourceText(button)).then(function () { flashLabel(button); });
      });
    });
  }

  function bindSecretToggle() {
    document.querySelectorAll('[data-secret-toggle]').forEach(function (button) {
      button.addEventListener('click', function () {
        var box = button.parentElement;
        if (!box) return;
        var real = box.querySelector('[data-secret-real]');
        var masked = box.querySelector('[data-secret-masked]');
        if (!real || !masked) return;
        var show = real.hidden;          // 当前打码 → 本次切换为显示
        real.hidden = !show;
        masked.hidden = show;
        var label = button.querySelector('[data-secret-toggle-label]');
        if (label) {
          label.textContent = show ? button.getAttribute('data-label-hide')
                                   : button.getAttribute('data-label-show');
        }
      });
    });
  }

  function bindConfirm() {
    document.querySelectorAll('form[data-confirm]').forEach(function (form) {
      form.addEventListener('submit', function (event) {
        if (!window.confirm(form.getAttribute('data-confirm'))) {
          event.preventDefault();
        }
      });
    });
  }

  bindCopy();
  bindSecretToggle();
  bindConfirm();
})();
