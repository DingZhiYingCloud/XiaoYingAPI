/* 自研图形验证码服务文档页：在线调试内的“真实弹窗联调”小部件
 *
 * 思路：自研验证码的校验链路是「generate 取图 → 用户在弹窗内作答 → verify 校验」，
 * 无法“发个请求就测通”。本文件在文档页放一个按钮，点击后弹出真实验证码弹窗，
 * 用户输入图中字符即可跑通完整链路，结果直接展示。
 *
 * 本文件只在 captcha_self 服务文档页加载（见 docs/service.html 的 doc.slug 判断），
 * 复用已封装的 window.XYCaptchaSelf 弹窗模式（init 预取 → show 弹出 → 校验回调）。
 */
(function () {
  'use strict';

  var VERIFY_PATH = '/api/captcha_self/verify';
  var sendBtn = document.querySelector('button[data-run-endpoint][data-path="' + VERIFY_PATH + '"]');
  if (!sendBtn || !window.XYCaptchaSelf) return; // 非该接口或无封装客户端则不初始化

  var card = sendBtn.closest('article');
  if (!card) return;

  var started = false; // 是否已调用 XYCaptchaSelf.init
  var ready = false;   // 验证码是否就绪

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  /* ---------- 构建联调面板 ---------- */
  var box = el('div', 'mt-3 space-y-3 rounded-box border border-dashed border-primary/40 bg-primary/5 p-3');

  var head = el('div', 'flex flex-wrap items-center gap-2');
  head.appendChild(el('span', 'text-sm font-semibold', gettext('自研验证码联调（真实弹窗）')));
  head.appendChild(el('span', 'badge badge-soft badge-info badge-xs', gettext('模拟前端完成验证')));
  box.appendChild(head);

  box.appendChild(el('p', 'text-xs leading-relaxed text-base-content/60',
    gettext('点击下方按钮会弹出自研验证码弹窗（本页真实调用 generate 与 verify 两个接口）；') +
    gettext('输入图中字符后确认即可完成校验。验证码为一次性，失败会自动换新图。')));

  var opRow = el('div', 'flex flex-wrap items-center gap-2');
  var startBtn = el('button', 'btn btn-primary btn-sm', gettext('开始图形验证'));
  startBtn.type = 'button';
  opRow.appendChild(startBtn);

  var statusEl = el('span', 'text-xs text-base-content/60', gettext('尚未开始'));
  opRow.appendChild(statusEl);
  box.appendChild(opRow);

  // 验证类型选择：字符图片 / 算术（切换后按新类型重新获取验证码）
  var typeRow = el('div', 'flex flex-wrap items-center gap-2');
  typeRow.appendChild(el('span', 'text-xs text-base-content/70', gettext('验证类型')));
  var kindSelect = el('select', 'select select-bordered select-sm w-36');
  [['char', gettext('字符图片')], ['arithmetic', gettext('算术')]].forEach(function (item) {
    var opt = el('option', null, item[1]);
    opt.value = item[0];
    kindSelect.appendChild(opt);
  });
  typeRow.appendChild(kindSelect);
  box.appendChild(typeRow);

  var resultBox = el('pre', 'hidden max-h-72 overflow-auto rounded-box border border-base-300 bg-base-100 p-3 font-mono text-xs');
  box.appendChild(resultBox);

  /* ---------- 状态与回调 ---------- */
  function setStatus(text, type) {
    statusEl.className = 'text-xs ' + (type === 'ok' ? 'text-success' : (type === 'bad' ? 'text-error' : 'text-base-content/60'));
    statusEl.textContent = text || '';
  }

  function showResult(title, data) {
    resultBox.classList.remove('hidden');
    resultBox.textContent = title + '\n' + JSON.stringify(data, null, 2);
  }

  function ensureStarted() {
    if (started) { if (ready) window.XYCaptchaSelf.show(); return; }
    started = true;
    setStatus(gettext('正在加载验证码资源…'));
    startBtn.disabled = true;
    startBtn.textContent = gettext('加载中…');
    window.XYCaptchaSelf.init({
      kind: kindSelect.value,
      onReady: function () {
        ready = true;
        startBtn.disabled = false;
        startBtn.textContent = gettext('重新图形验证');
        setStatus(gettext('验证码已就绪，正在弹出…'));
        window.XYCaptchaSelf.show(); // 就绪后自动弹窗，用户一次点击即可完成
      },
      onResult: function (res) {
        if (res && res.passed) {
          setStatus(gettext('验证通过'), 'ok');
          showResult(gettext('校验通过，data 如下：'), res);
        } else {
          setStatus(gettext('验证未通过，请重新验证'), 'bad');
          showResult(gettext('验证未通过：'), res || {});
        }
      },
      onClose: function () {
        setStatus(gettext('已关闭，可再次点击「开始图形验证」'));
      },
      onError: function (msg) {
        startBtn.disabled = true;
        setStatus(interpolate(gettext('初始化失败：%(error)s'), { error: msg || gettext('未知错误') }, true), 'bad');
      },
    });
  }

  startBtn.addEventListener('click', ensureStarted);

  // 切换类型：重置状态，下次点击按新类型重新获取（避免继续用旧类型的验证码）
  kindSelect.addEventListener('change', function () {
    started = false;
    ready = false;
    startBtn.textContent = gettext('开始图形验证');
    setStatus(gettext('尚未开始'));
  });

  // 面板插到「发送请求 / 清空」操作栏之前（操作栏位于 .card-body 内层）
  var actions = card.querySelector('.card-actions');
  if (actions) {
    actions.parentNode.insertBefore(box, actions);
  } else {
    card.appendChild(box);
  }
})();
