/* API 文档中心 - 在线播放器（m3u8 播放测试）
 *
 * 触发条件：端点在文档声明中标记 player=True 时，模板渲染 [data-player] 容器。
 * 功能：
 *   1) 点击「发送请求」成功后，自动取响应中的 data.m3u8 加载播放（监听 docs:result 事件）；
 *   2) 也可在输入框粘贴任意 m3u8 地址，点「加载播放」验证地址是否可用。
 * 实现：Chrome/Edge/Firefox 用 hls.js（懒加载 vendor 脚本）；
 *       Safari / iOS 原生支持 HLS，回退到 <video> 直接播放。
 */
(function () {
  'use strict';

  // Django i18n 全局函数的安全包装（脚本加载顺序异常时退化为原文）
  function _t(s) { return (typeof gettext === 'function') ? gettext(s) : s; }
  function _ti(s, ctx) { return (typeof interpolate === 'function') ? interpolate(s, ctx, true) : s; }

  /* ---------- hls.js 懒加载（首次需要时才下载） ---------- */
  var hlsQueue = [];
  var hlsLoading = false;

  function loadHls(cb) {
    if (window.Hls) { cb(window.Hls); return; }
    hlsQueue.push(cb);
    if (hlsLoading) return;
    hlsLoading = true;

    var holder = document.querySelector('[data-player][data-hls-src]');
    var src = holder ? holder.dataset.hlsSrc : '/static/js/vendor/hls.min.js';
    var script = document.createElement('script');
    script.src = src;
    script.onload = function () { flushQueue(window.Hls); };
    script.onerror = function () { flushQueue(null); };
    document.head.appendChild(script);
  }

  function flushQueue(Hls) {
    var queue = hlsQueue;
    hlsQueue = [];
    hlsLoading = false;
    queue.forEach(function (fn) { fn(Hls); });
  }

  /* ---------- 状态提示 ---------- */
  function setStatus(container, text, isError) {
    var node = container.querySelector('[data-player-status]');
    if (!node) return;
    node.textContent = text;
    node.classList.toggle('text-error', !!isError);
    node.classList.toggle('text-base-content/60', !isError);
  }

  /* ---------- 加载并播放 ---------- */
  function play(container, url) {
    var video = container.querySelector('[data-player-video]');
    if (!video) return;

    // 释放上一次的 hls 实例，避免重复加载泄漏
    if (container._hls) {
      try { container._hls.destroy(); } catch (e) { /* ignore */ }
      container._hls = null;
    }
    video.removeAttribute('src');
    video.load();

    if (!url) { setStatus(container, _t('未获取到播放地址'), true); return; }

    // Safari / iOS：原生支持 HLS
    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = url;
      setStatus(container, _t('使用浏览器原生 HLS 播放'));
      video.play().catch(function () { /* 自动播放被拦截时忽略 */ });
      return;
    }

    setStatus(container, _t('正在加载 hls.js …'));
    loadHls(function (Hls) {
      if (!Hls || !Hls.isSupported()) {
        setStatus(container, _t('当前浏览器不支持 HLS 播放，请改用 Chrome / Edge / Safari'), true);
        return;
      }
      var hls = new Hls({ enableWorker: true });
      container._hls = hls;
      hls.loadSource(url);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, function () {
        setStatus(container, _ti('已加载，共 %(n)s 个清晰度', { n: hls.levels.length }));
        video.play().catch(function () { /* ignore */ });
      });
      hls.on(Hls.Events.ERROR, function (evt, data) {
        if (!data || !data.fatal) return;
        var msg = '播放失败: ' + data.type + ' / ' + data.details;
        if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
          msg += _t('（可能是地址已过期或源站不可达）');
          hls.startLoad();            // 网络类错误尝试重载一次
        } else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
          hls.recoverMediaError();    // 媒体类错误尝试恢复
        } else {
          hls.destroy();
          container._hls = null;
        }
        setStatus(container, msg, true);
      });
    });
  }

  /* ---------- 绑定交互 ---------- */
  var containers = document.querySelectorAll('[data-player]');
  if (!containers.length) return;

  containers.forEach(function (container) {
    var loadBtn = container.querySelector('[data-player-load]');
    var urlInput = container.querySelector('[data-player-url]');
    if (loadBtn && urlInput) {
      loadBtn.addEventListener('click', function () {
        var url = urlInput.value.trim();
        if (!url) { setStatus(container, _t('请先填写 m3u8 地址'), true); return; }
        play(container, url);
      });
    }
  });

  // 调试响应返回后，若响应体含 m3u8 地址则自动加载播放
  document.addEventListener('docs:result', function (ev) {
    var detail = ev.detail || {};
    var container = document.querySelector('[data-player][data-player-res="' + detail.resKey + '"]');
    if (!container) return;
    var parsed = detail.parsed;
    var url = parsed && parsed.data && parsed.data.m3u8;
    if (url) play(container, url);
  });
})();
