/* 站点前端公共运行时（window.XY）
 *
 * 为什么要有这一层：站点各脚本原先各自实现「i18n 兜底 / 取 CSRF / 复制到剪贴板 /
 * 把请求失败原因转成人话」，同一段逻辑散在多个文件里各写一遍，改一处容易漏改别处；
 * 而且部分位置把原始技术信息（如 "HTTP 500"）直接显示给用户，不符合「报错要说人话」的口径。
 * 这里收敛为唯一实现，供各页面脚本调用。
 *
 * 加载顺序：必须在其它 site/ 脚本之前（见 templates/template.html）。
 * 注意：本文件里的中文字符串（msgid）需要出现在 locale 各语种的 LC_MESSAGES/djangojs.po 中，
 *      否则非中文语种下会回退成中文原文（scripts/check_i18n.py 会体检出来）。
 */
(function () {
  'use strict';

  var XY = window.XY || {};

  /* ---------- i18n 兜底：Django 的 gettext / interpolate 未就绪时退回原文 ---------- */
  XY.t = function (s) {
    return (typeof window.gettext === 'function') ? window.gettext(s) : s;
  };
  XY.ti = function (s, ctx) {
    return (typeof window.interpolate === 'function') ? window.interpolate(s, ctx, true) : s;
  };

  /* ---------- 取 CSRF Token ---------- */
  XY.csrf = function () {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  };

  /* ---------- 请求失败原因 → 给用户看的话 ----------
   * 优先用服务端返回的 msg（那是业务文案）；拿不到时，不再把 HTTP 状态码这类
   * 技术信息丢给用户，改用一句可读的兜底；原始信息只进控制台，便于排查。
   */
  XY.failText = function (res, fallback) {
    var body = res && res.json;
    if (body && body.msg) return body.msg;
    if (res) console.warn('[XY] request failed', res);
    return fallback || XY.t('请求失败，请稍后重试');
  };

  /* ---------- 复制到剪贴板（带按钮文字反馈） ---------- */
  XY.copy = function (text, btn) {
    function done() {
      if (!btn) return;
      var old = btn.textContent;
      btn.textContent = XY.t('已复制');
      setTimeout(function () { btn.textContent = old; }, 1200);
    }
    function fallback() {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      // 复制失败不阻塞页面，忽略即可
      try { document.execCommand('copy'); done(); } catch (e) { /* ignore */ }
      document.body.removeChild(ta);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, fallback);
    } else {
      fallback();
    }
  };

  window.XY = XY;
})();
