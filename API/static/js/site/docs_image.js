/* API 文档中心 - 图片解码预览
 *
 * 触发条件：端点在文档声明中提供 image_help 时，模板渲染 [data-image-panel] 与「解密说明」弹窗。
 * 功能：
 *   1) 粘贴加密图片地址 → 请求该服务的图片解码端点 → 直接显示解码后的真实图片；
 *   2) 「解密说明」按钮 → 弹出该端点在文档里声明的详细解密步骤。
 * 说明：图片解码端点是开放接口（返回的是图片二进制，<img> 无法给请求附带签名参数）。
 */
(function () {
  'use strict';

  // Django i18n 全局函数的安全包装（脚本加载顺序异常时退化为原文）
  function _t(s) { return (typeof gettext === 'function') ? gettext(s) : s; }
  function _ti(s, ctx) { return (typeof interpolate === 'function') ? interpolate(s, ctx, true) : s; }

  function setStatus(panel, text, isError) {
    var node = panel.querySelector('[data-image-status]');
    if (!node) return;
    node.textContent = text;
    node.classList.toggle('text-error', !!isError);
    node.classList.toggle('text-base-content/60', !isError);
  }

  /* 请求解码端点并把结果图片显示出来 */
  function load(panel, url) {
    var endpoint = panel.dataset.imageEndpoint;
    var box = panel.querySelector('[data-image-box]');
    var img = panel.querySelector('[data-image-preview]');
    if (!endpoint || !img) return;

    var src = endpoint + '?url=' + encodeURIComponent(url);
    setStatus(panel, _t('正在解码…'), false);

    // 先用 Image 预加载：失败时（地址不合法 / 源站不可达）不显示破图，只给提示
    var probe = new Image();
    probe.onload = function () {
      img.src = src;
      if (box) box.classList.remove('hidden');
      setStatus(panel, _ti('解码成功：%(w)s × %(h)s 像素', {
        w: probe.naturalWidth, h: probe.naturalHeight,
      }), false);
    };
    probe.onerror = function () {
      if (box) box.classList.add('hidden');
      setStatus(panel, _t('解码失败：请确认填的是加密图片地址（形如 …/xxxx_mini.jpg.txt），且为公网可访问地址'), true);
    };
    probe.src = src;
  }

  var panels = document.querySelectorAll('[data-image-panel]');
  panels.forEach(function (panel) {
    var input = panel.querySelector('[data-image-url]');
    var loadBtn = panel.querySelector('[data-image-load]');
    var helpBtn = panel.querySelector('[data-image-help]');

    if (loadBtn && input) {
      loadBtn.addEventListener('click', function () {
        var value = (input.value || '').trim();
        if (!value) { setStatus(panel, _t('请先填写加密图片地址'), true); return; }
        load(panel, value);
      });
      input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); loadBtn.click(); }
      });
    }

    if (helpBtn) {
      helpBtn.addEventListener('click', function () {
        var article = panel.closest('article');
        var dialog = article && article.querySelector('[data-image-dialog]');
        if (dialog && typeof dialog.showModal === 'function') dialog.showModal();
      });
    }
  });
})();
