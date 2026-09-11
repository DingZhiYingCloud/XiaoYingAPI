/**
 * 自研图形验证码 - 小影API 前端封装
 *
 * 提供两种接入形态：
 *
 * ① 内联模式（页面上常驻显示验证码，与表单一起提交）
 *   <img id="captcha-img"> <input id="captcha-input"> <button id="captcha-refresh">换一张</button>
 *   var captcha = XYCaptchaSelf.create({ img:'#captcha-img', input:'#captcha-input',
 *                                        refreshButton:'#captcha-refresh' });
 *   captcha.verify().then(function (res) { if (res.passed) { 提交表单 } });
 *
 * ② 弹窗模式（用户点击后才弹出验证码，自包含样式，与阿里云 SDK 弹窗的接入体验一致）
 *   XYCaptchaSelf.init({
 *     onReady:  function () { ... },        // 验证码已就绪
 *     onResult: function (res) {            // 每次校验完成都回调：res.passed / res.msg
 *       // 成功：弹窗自动关闭，放行业务；失败：弹窗保留并自动换新图，可继续输入
 *     },
 *     onClose:  function () { ... },        // 用户主动关闭弹窗（取消 / 右上角 / ESC）
 *     onError:  function (msg) { ... },     // 获取验证码失败
 *     kind: 'char',                         // 可选：char（默认）/ arithmetic
 *     length: 4,                            // 可选：字符个数，仅 kind=char 生效（4-6）
 *   });
 *   XYCaptchaSelf.show();                   // 就绪后弹出（未就绪会自动先取一张）
 *
 * ⚠️ 交给自己后端校验时（如官网登录 / 注册表单）必须传 autoVerify: false：
 *   XYCaptchaSelf.init({
 *     autoVerify: false,                    // 默认 true：客户端调 /verify 校验并回调 onResult
 *                                           // 传 false：不调服务端校验，只把参数交给接入方后端
 *     onValidate: function (data) { ... },  // 仅 autoVerify=false 时回调
 *                                           // data = {captcha_id, answer}
 *   });
 *   验证码是一次性的：客户端先校验会把凭证消费掉，导致后端复验失败，所以必须由后端校验。
 *
 * 说明：验证码为一次性——verify 提交后无论对错都已失效，故失败后会自动换新图。
 */
(function (global) {
  'use strict';

  // ── 服务端点（与后端接口严格对应） ──
  var GENERATE_URL = '/api/captcha_self/generate';
  var VERIFY_URL = '/api/captcha_self/verify';

  // 文案走 i18n（词条在 djangojs.po，由 /jsi18n/ 下发）；
  // 宿主页面未加载 gettext 时退化为原文，保证本文件可独立使用。
  var _t = (typeof global.gettext === 'function')
    ? global.gettext
    : function (text) { return text; };

  /** 选择器或 DOM 元素统一解析为元素 */
  function _resolve(target) {
    if (!target) { return null; }
    return typeof target === 'string' ? document.querySelector(target) : target;
  }

  /** 获取一张验证码：resolve(data) / reject(Error) */
  function _fetchCaptcha(kind, length) {
    var query = '?kind=' + encodeURIComponent(kind);
    if (length) { query += '&length=' + encodeURIComponent(length); }
    return fetch(GENERATE_URL + query)
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (!data || data.code !== 10000) {
          throw new Error((data && data.msg) || _t('验证码获取失败'));
        }
        return data.data;
      });
  }

  /** 提交答案校验：resolve({passed, msg})（网络异常时 reject） */
  function _postVerify(captchaId, answer) {
    var body = new URLSearchParams({ captcha_id: captchaId, answer: answer });
    return fetch(VERIFY_URL, { method: 'POST', body: body })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        return {
          passed: !!(data && data.code === 10000 && data.data && data.data.passed),
          msg: (data && data.msg) || '',
        };
      });
  }

  /* ==================== ① 内联模式 ==================== */

  function create(options) {
    var opts = options || {};
    var img = _resolve(opts.img);
    var input = _resolve(opts.input);
    var refreshButton = _resolve(opts.refreshButton);
    var kind = opts.kind || 'char';
    var length = opts.length || null;

    var captchaId = '';  // 当前待校验的验证码 ID

    /** 获取一张新验证码并渲染到 img */
    function refresh() {
      captchaId = '';
      if (input) { input.value = ''; }
      return _fetchCaptcha(kind, length).then(function (data) {
        captchaId = data.captcha_id;
        if (img) { img.src = data.image; }
        return data;
      });
    }

    /** 提交校验；失败（含请求异常）自动换新图 */
    function verify() {
      var answer = input ? input.value.trim() : '';
      if (!answer) { return Promise.resolve({ passed: false, msg: _t('请填写验证码') }); }
      if (!captchaId) { return Promise.resolve({ passed: false, msg: _t('验证码获取失败') }); }

      return _postVerify(captchaId, answer)
        .then(function (res) {
          // 验证码一次性：本次已消费，失败后立即换一张
          if (!res.passed) { refresh(); }
          return res;
        })
        .catch(function () {
          refresh();
          return { passed: false, msg: _t('校验请求失败，请重试') };
        });
    }

    if (refreshButton) { refreshButton.addEventListener('click', refresh); }
    refresh();

    return {
      refresh: refresh,   // 主动换一张
      verify: verify,     // 提交校验，返回 Promise<{passed, msg}>
    };
  }

  /* ==================== ② 弹窗模式（自包含，零依赖） ==================== */

  var STYLE_ID = 'xycaptcha-self-style';
  var _dialog = null;              // 弹窗元素与子节点引用
  var _closeNotified = true;       // 本次弹窗是否已通知过 onClose（true=未打开/已通知）
  var _popup = { options: {}, captchaId: '', ready: false };

  /** 注入弹窗样式（只注入一次；样式全部限定在 .xycs-* 前缀内，不污染宿主页面） */
  function _injectStyle() {
    if (document.getElementById(STYLE_ID)) { return; }
    var style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = [
      // 显式声明居中：宿主页面的 Tailwind preflight（*,*::before,*::after{margin:0}）
      // 会覆盖浏览器给 dialog 的默认 margin:auto，不写就会贴到左上角
      '.xycs-dialog{position:fixed;inset:0;width:fit-content;height:fit-content;max-width:100%;',
      'max-height:100%;margin:auto;border:0;padding:0;background:transparent;}',
      '.xycs-dialog::backdrop{background:rgba(0,0,0,.45);}',
      '.xycs-panel{width:320px;max-width:92vw;box-sizing:border-box;padding:18px;border-radius:12px;',
      'background:#fff;color:#1f2937;font-family:inherit;box-shadow:0 12px 40px rgba(0,0,0,.22);}',
      '.xycs-head{display:flex;align-items:center;justify-content:space-between;font-size:15px;font-weight:600;}',
      '.xycs-close{border:0;background:transparent;padding:0 2px;font-size:20px;line-height:1;color:#9ca3af;cursor:pointer;}',
      '.xycs-tip{margin:10px 0 0;font-size:12px;line-height:1.6;color:#6b7280;}',
      '.xycs-imgbox{position:relative;height:64px;margin-top:12px;}',
      '.xycs-img{display:block;width:100%;height:64px;border-radius:8px;background:#f6f8fb;cursor:pointer;object-fit:fill;}',
      '.xycs-img.is-loading{visibility:hidden;}',
      '.xycs-loading{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;',
      'border-radius:8px;background:#f6f8fb;font-size:12px;color:#9ca3af;}',
      '.xycs-row{display:flex;gap:8px;margin-top:10px;}',
      '.xycs-input{flex:1;min-width:0;height:36px;box-sizing:border-box;padding:0 10px;border:1px solid #d1d5db;',
      'border-radius:8px;font-size:14px;outline:none;}',
      '.xycs-input:focus{border-color:#2563eb;}',
      '.xycs-refresh{height:36px;padding:0 12px;border:1px solid #d1d5db;border-radius:8px;background:#fff;',
      'font-size:13px;white-space:nowrap;cursor:pointer;}',
      '.xycs-err{margin:8px 0 0;min-height:16px;font-size:12px;color:#dc2626;}',
      '.xycs-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:14px;}',
      '.xycs-btn{height:34px;padding:0 16px;border:1px solid transparent;border-radius:8px;font-size:13px;cursor:pointer;}',
      '.xycs-btn:disabled{opacity:.6;cursor:not-allowed;}',
      '.xycs-btn-ghost{border-color:#d1d5db;background:#fff;color:#374151;}',
      '.xycs-btn-primary{background:#2563eb;color:#fff;}',
    ].join('');
    document.head.appendChild(style);
  }

  function _setLoading(on) {
    if (!_dialog) { return; }
    _dialog.loading.style.display = on ? 'flex' : 'none';
    _dialog.img.classList.toggle('is-loading', on);
  }

  function _setError(msg) {
    if (_dialog) { _dialog.err.textContent = msg || ''; }
  }

  /** 构建弹窗（幂等）：结构 + 事件绑定 */
  function _buildDialog() {
    if (_dialog) { return _dialog; }
    _injectStyle();

    var dialog = document.createElement('dialog');
    dialog.className = 'xycs-dialog';
    dialog.innerHTML =
      '<div class="xycs-panel">' +
        '<div class="xycs-head">' +
          '<span>' + _t('安全验证') + '</span>' +
          '<button type="button" class="xycs-close" aria-label="' + _t('关闭') + '">&times;</button>' +
        '</div>' +
        '<p class="xycs-tip"></p>' +
        '<div class="xycs-imgbox">' +
          '<img class="xycs-img" alt="' + _t('验证码') + '">' +
          '<span class="xycs-loading">' + _t('加载中…') + '</span>' +
        '</div>' +
        '<div class="xycs-row">' +
          '<input id="xycaptcha-self-input" class="xycs-input" type="text" maxlength="8" autocomplete="off" placeholder="' + _t('请输入验证码') + '">' +
          '<button type="button" class="xycs-refresh">' + _t('换一张') + '</button>' +
        '</div>' +
        '<p class="xycs-err"></p>' +
        '<div class="xycs-actions">' +
          '<button type="button" class="xycs-btn xycs-btn-ghost xycs-cancel">' + _t('取消') + '</button>' +
          '<button type="button" class="xycs-btn xycs-btn-primary xycs-submit">' + _t('确认') + '</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(dialog);

    _dialog = {
      dialog: dialog,
      img: dialog.querySelector('.xycs-img'),
      tip: dialog.querySelector('.xycs-tip'),
      loading: dialog.querySelector('.xycs-loading'),
      input: dialog.querySelector('.xycs-input'),
      err: dialog.querySelector('.xycs-err'),
      refresh: dialog.querySelector('.xycs-refresh'),
      submit: dialog.querySelector('.xycs-submit'),
      cancel: dialog.querySelector('.xycs-cancel'),
      close: dialog.querySelector('.xycs-close'),
    };

    // 用户主动关闭（取消 / 右上角）：点击时同步通知；ESC 由浏览器关闭，走下方 close 事件兜底
    _dialog.cancel.addEventListener('click', function () { _closePopup(true); });
    _dialog.close.addEventListener('click', function () { _closePopup(true); });
    dialog.addEventListener('close', function () { _notifyClose(); });
    _dialog.refresh.addEventListener('click', function () {
      _setError('');
      _refreshPopup();
    });
    _dialog.img.addEventListener('click', function () {
      _setError('');
      _refreshPopup();
    });
    _dialog.submit.addEventListener('click', _submitPopup);
    _dialog.input.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') { _submitPopup(); }
    });
    return _dialog;
  }

  /** 取一张新验证码渲染到弹窗（不清空错误提示，由调用方决定） */
  function _refreshPopup() {
    _setLoading(true);
    // 提示语随类型变化：字符类照抄字符，算术类填计算结果
    _dialog.tip.textContent = (_popup.options.kind === 'arithmetic')
      ? _t('请计算下图算式的结果，完成安全验证')
      : _t('请输入下图中的字符，完成安全验证');
    return _fetchCaptcha(_popup.options.kind || 'char', _popup.options.length || null)
      .then(function (data) {
        _popup.captchaId = data.captcha_id;
        _dialog.img.src = data.image;
        _dialog.input.value = '';
        _dialog.input.focus();
        _setLoading(false);
        return data;
      })
      .catch(function (err) {
        _setLoading(false);
        _setError((err && err.message) || _t('验证码获取失败'));
        throw err;
      });
  }

  function _openPopup() {
    _closeNotified = false;
    // 已打开时跳过（重复调用 show() 不应报 InvalidStateError）
    if (!_dialog.dialog.open) {
      if (_dialog.dialog.showModal) { _dialog.dialog.showModal(); }
      else { _dialog.dialog.setAttribute('open', ''); }
    }
    _dialog.input.focus();
  }

  /** 通知「用户主动关闭」，每次打开只通知一次（ESC 与按钮点击不会重复触发） */
  function _notifyClose() {
    if (_closeNotified) { return; }
    _closeNotified = true;
    if (_popup.options && typeof _popup.options.onClose === 'function') { _popup.options.onClose(); }
  }

  /**
   * 关闭弹窗
   * :param notify: true=用户主动关闭（同步回调 onClose，不依赖异步的 close 事件——
   *                标签页被节流时该事件会明显延迟）；false=流程性关闭（如验证成功），不回调
   */
  function _closePopup(notify) {
    if (!_dialog) { return; }
    if (_dialog.dialog.close) { _dialog.dialog.close(); }
    else { _dialog.dialog.removeAttribute('open'); }
    if (notify) { _notifyClose(); } else { _closeNotified = true; }
  }

  function _submitPopup() {
    var answer = _dialog.input.value.trim();
    if (!answer) { _setError(_t('请填写验证码')); return; }
    if (!_popup.captchaId) { _setError(_t('验证码获取失败')); return; }

    // autoVerify=false：不调服务端校验，只把 captcha_id + answer 交给接入方后端消费
    // （验证码一次性，客户端先校验会让后端复验失败）
    if (_popup.options.autoVerify === false) {
      var handoff = { captcha_id: _popup.captchaId, answer: answer };
      _popup.captchaId = '';   // 已交给后端，下次 show() 必须重新取一张
      _closePopup(false);      // 流程性关闭，不算“用户主动取消”
      if (typeof _popup.options.onValidate === 'function') {
        _popup.options.onValidate(handoff);
      }
      return;
    }

    _setError('');
    _dialog.submit.disabled = true;
    _dialog.submit.textContent = _t('请求中…');

    _postVerify(_popup.captchaId, answer).then(function (res) {
      _dialog.submit.disabled = false;
      _dialog.submit.textContent = _t('确认');

      if (res.passed) {
        _popup.captchaId = '';   // 已消费
        _closePopup(false);      // 成功自动关闭：不触发 onClose（非用户主动关闭）
      } else {
        _setError(res.msg || _t('验证未通过，请重新验证'));
        _refreshPopup();                 // 一次性已消费，失败必须换新图
      }
      if (_popup.options && typeof _popup.options.onResult === 'function') {
        _popup.options.onResult({ passed: res.passed, msg: res.msg || '' });
      }
    }).catch(function () {
      _dialog.submit.disabled = false;
      _dialog.submit.textContent = _t('确认');
      _setError(_t('校验请求失败，请重试'));
      _refreshPopup();
    });
  }

  global.XYCaptchaSelf = {
    /** 内联模式：把验证码渲染到页面已有元素上 */
    create: create,

    /** 弹窗模式 - 初始化：预取一张验证码，就绪后回调 onReady */
    init: function (options) {
      _popup.options = options || {};
      _buildDialog();
      _popup.ready = false;
      _refreshPopup().then(function () {
        _popup.ready = true;
        if (typeof _popup.options.onReady === 'function') { _popup.options.onReady(); }
      }).catch(function (err) {
        if (typeof _popup.options.onError === 'function') {
          _popup.options.onError((err && err.message) || _t('验证码获取失败'));
        }
      });
    },

    /** 弹窗模式 - 弹出验证码（未就绪时自动先取一张） */
    show: function () {
      _buildDialog();
      if (_popup.captchaId) { _openPopup(); return; }
      _refreshPopup().then(_openPopup).catch(function (err) {
        if (_popup.options && typeof _popup.options.onError === 'function') {
          _popup.options.onError((err && err.message) || _t('验证码获取失败'));
        }
      });
    },

    /** 弹窗模式 - 验证码是否已就绪 */
    isReady: function () { return _popup.ready; },
  };
})(window);
