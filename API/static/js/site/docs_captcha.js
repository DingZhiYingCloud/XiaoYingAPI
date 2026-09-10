/* 图形验证服务文档页：在线调试内的“真实图形验证联调”小部件
 *
 * 思路：图形验证的 verify 接口无法“发个请求就测通”，必须先在浏览器里真实弹出
 * 阿里云官方滑块/拼图，人手动完成后拿到 lot_number/captcha_output/pass_token/gen_time，
 * 再拿去服务端二次校验。
 *
 * 本文件只在 captcha_auth 服务文档页加载（见 docs/service.html 的 doc.slug 判断），
 * 复用已封装的 window.XYCaptcha（加载官方 ct4.js → 取 appId → 弹窗验证 → 自动二次校验），
 * 并把验证参数回填到下方调试表单，用户也可再用「发送请求」走平台代调再验一次。
 */
(function () {
  'use strict';

  var VERIFY_PATH = '/api/captcha_auth/aliyun/verify';
  var sendBtn = document.querySelector('button[data-run-endpoint][data-path="' + VERIFY_PATH + '"]');
  if (!sendBtn || !window.XYCaptcha) return; // 非该接口或无封装客户端则不初始化

  var card = sendBtn.closest('article');
  if (!card) return;

  var started = false; // 是否已调用 XYCaptcha.init
  var ready = false;   // 验证码是否就绪

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function paramInput(name) {
    return card.querySelector('[data-param-name="' + name + '"]');
  }

  /* ---------- 构建联调面板 ---------- */
  var box = el('div', 'mt-3 space-y-3 rounded-box border border-dashed border-primary/40 bg-primary/5 p-3');

  var head = el('div', 'flex flex-wrap items-center gap-2');
  head.appendChild(el('span', 'text-sm font-semibold', gettext('图形验证联调（真实弹窗）')));
  head.appendChild(el('span', 'badge badge-soft badge-info badge-xs', gettext('模拟前端完成验证')));
  box.appendChild(head);

  box.appendChild(el('p', 'text-xs leading-relaxed text-base-content/60',
    gettext('点击下方按钮会弹出阿里云官方图形验证，拖动/点选通过后自动完成服务端二次校验；') +
    gettext('四个验证参数会自动回填到上方表单，你也可以再用「发送请求」走平台代调复验。')));

  var opRow = el('div', 'flex flex-wrap items-center gap-2');
  var startBtn = el('button', 'btn btn-primary btn-sm', gettext('开始图形验证'));
  startBtn.type = 'button';
  opRow.appendChild(startBtn);

  var statusEl = el('span', 'text-xs text-base-content/60', gettext('尚未开始'));
  opRow.appendChild(statusEl);
  box.appendChild(opRow);

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

  function fillParams(validate) {
    var map = {
      lot_number: validate.lot_number,
      captcha_output: validate.captcha_output,
      pass_token: validate.pass_token,
      gen_time: validate.gen_time,
    };
    Object.keys(map).forEach(function (name) {
      var input = paramInput(name);
      if (input && map[name] !== undefined) input.value = map[name];
    });
  }

  function ensureStarted() {
    if (started) { if (ready) XYCaptcha.show(); return; }
    started = true;
    setStatus(gettext('正在加载验证码资源…'));
    startBtn.disabled = true;
    startBtn.textContent = gettext('加载中…');
    XYCaptcha.init({
      onReady: function () {
        ready = true;
        startBtn.disabled = false;
        startBtn.textContent = gettext('重新图形验证');
        setStatus(gettext('验证码已就绪，正在弹出…'));
        XYCaptcha.show(); // 就绪后自动弹窗，用户一次点击即可完成
      },
      onValidate: function (validate) {
        fillParams(validate);
        setStatus(gettext('验证通过，参数已自动回填，正在二次校验…'));
      },
      onResult: function (data) {
        if (data && data.passed) {
          setStatus(gettext('图形验证 + 二次校验通过'), 'ok');
          showResult(gettext('二次校验通过，data 如下：'), data);
        } else {
          setStatus((data && data.reason) || gettext('验证未通过，请重新验证'), 'bad');
          showResult(gettext('验证未通过：'), data || {});
          ready = true; // 失败后允许再次点击重新验证
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

  // 面板插到「发送请求 / 清空」操作栏之前（操作栏位于 .card-body 内层）
  var actions = card.querySelector('.card-actions');
  if (actions) {
    actions.parentNode.insertBefore(box, actions);
  } else {
    card.appendChild(box);
  }
})();
