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
 *    样式零依赖自注入：配色跟随宿主站点的 daisyUI 主题变量（--color-*），取不到变量时
 *    回退为内置浅色方案，因此脱离本站也能独立使用。
 *   XYCaptchaSelf.init({
 *     onReady:  function () { ... },        // 验证码已就绪
 *     onResult: function (res) {            // 每次校验完成都回调：res.passed / res.msg
 *       // 成功：弹窗自动关闭，放行业务；失败：弹窗保留并自动换新图，可继续输入
 *     },
 *     onClose:  function () { ... },        // 用户主动关闭弹窗（取消 / 右上角 / ESC）
 *     onError:  function (msg) { ... },     // 获取验证码失败
 *     kind: 'char',                         // 可选：char（默认）/ arithmetic / slider / click / random
 *                                           // random = 每次从三种自研验证码里按权重随机抽一种
 *     length: 4,                            // 可选：字符个数，仅 kind=char 生效（4-6）
 *   });
 *   XYCaptchaSelf.show();                   // 就绪后弹出（未就绪会自动先取一张）
 *
 * ⚠️ 交给自己后端校验时（如官网登录 / 注册表单）必须传 autoVerify: false：
 *   XYCaptchaSelf.init({
 *     autoVerify: false,                    // 默认 true：客户端调对应 verify 校验并回调 onResult
 *                                           // 传 false：不调服务端校验，只把参数交给接入方后端
 *     onValidate: function (data) { ... },  // 仅 autoVerify=false 时回调
 *                                           // data.captcha_type 为 char / arithmetic / slider / click，
 *                                           // 其余字段随类型不同：
 *                                           //   字符 / 算术：captcha_id + answer
 *                                           //   滑块：slider_id + x + track
 *                                           //   汉字点选：challenge_id + points
 *   });
 *   验证码是一次性的：客户端先校验会把凭证消费掉，导致后端复验失败，所以必须由后端校验。
 *
 * 说明：验证码为一次性——verify 提交后无论对错都已失效，故失败后会自动换新（随机模式下换的
 * 类型也会重新抽，避免连续卡在同一种验证码上）。
 */
(function (global) {
  'use strict';

  // ── 服务端点（与后端接口严格对应） ──
  var GENERATE_URL = '/api/captcha_self/generate';
  var VERIFY_URL = '/api/captcha_self/verify';
  var SLIDER_GENERATE_URL = '/api/captcha_self/slider/generate';
  var SLIDER_VERIFY_URL = '/api/captcha_self/slider/verify';
  var CLICK_GENERATE_URL = '/api/captcha_self/click/generate';
  var CLICK_VERIFY_URL = '/api/captcha_self/click/verify';

  // 随机模式的权重：字符最快、算术次之，滑块 / 点选体验更重但能挡住更多脚本
  var RANDOM_WEIGHTS = [
    { kind: 'char', weight: 40 },
    { kind: 'arithmetic', weight: 20 },
    { kind: 'slider', weight: 25 },
    { kind: 'click', weight: 15 }
  ];

  // 轨迹最多记 200 个点（服务端留到 2000 只防超大 payload）：
  // 60Hz 下拖 10 秒会产生 600 个点，不节流会被自己拒绝
  var MAX_TRACK_POINTS = 200;

  // 文案走 i18n（词条在 djangojs.po，由 /jsi18n/ 下发）；
  // 宿主页面未加载 gettext 时退化为原文，保证本文件可独立使用。
  var _t = (typeof global.gettext === 'function')
    ? global.gettext
    : function (text) { return text; };

  // 插值同理：先取译文再做 %(name)s 替换（与项目其它 JS 的 interpolate(gettext(...), …, true) 口径一致）
  var _i = (typeof global.interpolate === 'function')
    ? function (text, params) { return global.interpolate(_t(text), params, true); }
    : function (text, params) {
      return String(_t(text)).replace(/%\((\w+)\)s/g, function (all, key) {
        return Object.prototype.hasOwnProperty.call(params, key) ? params[key] : all;
      });
    };

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

  /** 通用 GET：resolve(data)；服务端业务失败时 reject(Error) */
  function _fetchJson(url) {
    return fetch(url, { credentials: 'same-origin' })
      .then(function (res) { return res.json(); })
      .then(function (body) {
        if (!body || body.code !== 10000 || !body.data) {
          throw new Error((body && body.msg) || _t('验证码获取失败'));
        }
        return body.data;
      });
  }

  /** 通用 POST 表单：resolve({passed, msg})（网络异常时 reject） */
  function _postForm(url, params) {
    var body = new URLSearchParams(params);
    return fetch(url, { method: 'POST', body: body, credentials: 'same-origin' })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        return {
          passed: !!(data && data.code === 10000 && data.data && data.data.passed),
          msg: (data && data.msg) || ''
        };
      });
  }

  /** 提交答案校验：resolve({passed, msg})（网络异常时 reject） */
  function _postVerify(captchaId, answer) {
    return _postForm(VERIFY_URL, { captcha_id: captchaId, answer: answer });
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
  var _popup = {
    options: {},
    kind: '',
    lastKind: '',
    ready: false,
    busy: false,
    captchaId: '',
    sliderId: '',
    challengeId: ''
  };

  /** 注入弹窗样式（只注入一次；样式全部限定在 .xycs-* 前缀内，不污染宿主页面）
   *
   * 配色跟随站点 daisyUI 主题：--color-* 由 <html data-theme> 下发，弹窗挂在 body 下可直接继承；
   * 变量不存在（脱离本站独立使用）时回退为内置浅色值。
   */
  function _injectStyle() {
    if (document.getElementById(STYLE_ID)) { return; }
    var style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = [
      // 主题色板：只在 .xycs-dialog 作用域内声明，不污染宿主页面
      '.xycs-dialog{--xycs-surface:var(--color-base-100,#fff);',
      '--xycs-surface-2:var(--color-base-200,#f6f8fb);',
      '--xycs-border:var(--color-base-300,#d1d5db);',
      '--xycs-text:var(--color-base-content,#1f2937);',
      '--xycs-primary:var(--color-primary,#2563eb);',
      '--xycs-primary-content:var(--color-primary-content,#fff);',
      '--xycs-error:var(--color-error,#dc2626);',
      // 显式声明居中：宿主页面的 Tailwind preflight（*,*::before,*::after{margin:0}）
      // 会覆盖浏览器给 dialog 的默认 margin:auto，不写就会贴到左上角
      'position:fixed;inset:0;width:fit-content;height:fit-content;max-width:100%;max-height:100%;',
      'margin:auto;border:0;padding:0;background:transparent;',
      // 出现动效：@starting-style 属渐进增强，不支持的浏览器直接静态出现，功能不受影响
      'opacity:0;transform:translateY(-8px) scale(.98);transition:opacity .16s ease,transform .16s ease;}',
      '.xycs-dialog[open]{opacity:1;transform:none;}',
      '@starting-style{.xycs-dialog[open]{opacity:0;transform:translateY(-8px) scale(.98);}}',
      '.xycs-dialog::backdrop{background:rgba(0,0,0,.45);transition:background .16s ease;}',
      '@starting-style{.xycs-dialog[open]::backdrop{background:rgba(0,0,0,0);}}',
      '@media (prefers-reduced-motion:reduce){.xycs-dialog,.xycs-dialog::backdrop{transition:none;}}',
      '.xycs-panel{width:320px;max-width:92vw;box-sizing:border-box;padding:18px;border-radius:12px;',
      'background:var(--xycs-surface);color:var(--xycs-text);font-family:inherit;',
      'box-shadow:0 12px 40px rgba(0,0,0,.22);}',
      '.xycs-head{display:flex;align-items:center;gap:7px;font-size:15px;font-weight:600;}',
      '.xycs-head svg{width:16px;height:16px;flex:none;color:var(--xycs-primary);}',
      '.xycs-close{margin-left:auto;border:0;background:transparent;padding:0 2px;font-size:20px;line-height:1;',
      'color:inherit;opacity:.45;cursor:pointer;}',
      '.xycs-close:hover{opacity:.9;}',
      '.xycs-tip{margin:10px 0 0;font-size:12px;line-height:1.6;opacity:.65;min-height:1.6em;}',
      '.xycs-expire{margin-left:6px;white-space:nowrap;}',
      // 图片按原始像素居中显示（后端出图 180×64）：不再 object-fit:fill 拉满整行，拉伸会让字符变形发虚
      '.xycs-imgbox{position:relative;display:flex;align-items:center;justify-content:center;height:64px;',
      'margin-top:12px;border-radius:8px;background:var(--xycs-surface-2);cursor:pointer;overflow:hidden;}',
      '.xycs-img{display:block;max-width:100%;height:100%;width:auto;}',
      '.xycs-img.is-loading{visibility:hidden;}',
      '.xycs-mask{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;gap:6px;',
      'font-size:12px;opacity:.7;background:var(--xycs-surface-2);z-index:2;}',
      '.xycs-mask[hidden]{display:none;}',
      '.xycs-spinner{width:14px;height:14px;flex:none;border:2px solid currentColor;border-top-color:transparent;',
      'border-radius:50%;animation:xycs-spin .7s linear infinite;}',
      '@keyframes xycs-spin{to{transform:rotate(360deg)}}',
      '.xycs-hint{position:absolute;inset:auto 0 0 0;padding:1px 0;text-align:center;font-size:11px;',
      'background:rgba(0,0,0,.55);color:#fff;opacity:0;pointer-events:none;transition:opacity .12s ease;}',
      '.xycs-imgbox:hover .xycs-hint{opacity:1;}',
      '.xycs-imgbox.is-loading .xycs-hint{opacity:0;}',
      '.xycs-row{display:flex;gap:8px;margin-top:10px;}',
      '.xycs-input{flex:1;min-width:0;height:36px;box-sizing:border-box;padding:0 10px;',
      'border:1px solid var(--xycs-border);border-radius:8px;background:var(--xycs-surface);',
      'color:inherit;font-size:14px;letter-spacing:.08em;outline:none;}',
      '.xycs-input::placeholder{color:inherit;opacity:.4;letter-spacing:0;}',
      '.xycs-input:focus{border-color:var(--xycs-primary);box-shadow:0 0 0 3px rgba(37,99,235,.15);}',
      '@supports (color:color-mix(in oklab,red,blue)){.xycs-input:focus{',
      'box-shadow:0 0 0 3px color-mix(in oklab,var(--xycs-primary) 25%,transparent);}}',
      '.xycs-refresh{height:36px;padding:0 12px;border:1px solid var(--xycs-border);border-radius:8px;',
      'background:transparent;color:inherit;font-size:13px;white-space:nowrap;cursor:pointer;}',
      '.xycs-refresh:enabled:hover{border-color:var(--xycs-primary);color:var(--xycs-primary);}',
      '.xycs-refresh:disabled{opacity:.5;cursor:not-allowed;}',
      '.xycs-err{margin:8px 0 0;min-height:16px;font-size:12px;color:var(--xycs-error);}',
      '.xycs-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:14px;}',
      '.xycs-btn{height:34px;padding:0 16px;border:1px solid transparent;border-radius:8px;font-size:13px;cursor:pointer;}',
      '.xycs-btn[hidden]{display:none;}',
      '.xycs-btn:disabled{opacity:.6;cursor:not-allowed;}',
      '.xycs-btn-ghost{border-color:var(--xycs-border);background:transparent;color:inherit;}',
      '.xycs-btn-ghost:enabled:hover{border-color:var(--xycs-primary);color:var(--xycs-primary);}',
      '.xycs-btn-primary{background:var(--xycs-primary);color:var(--xycs-primary-content);}',
      '.xycs-btn-primary:enabled:hover{opacity:.88;}',
      '.xycs-btn:focus-visible,.xycs-refresh:focus-visible,.xycs-close:focus-visible{',
      'outline:2px solid var(--xycs-primary);outline-offset:2px;}',
      // ── 滑块 / 点选两种交互的舞台 ──
      '.xycs-stage[hidden]{display:none;}',
      '.xycs-media{position:relative;margin-top:12px;border-radius:8px;overflow:hidden;',
      'background:var(--xycs-surface-2);touch-action:none;user-select:none;}',
      '.xycs-media img{display:block;width:100%;height:auto;pointer-events:none;}',
      '.xycs-slider-piece{position:absolute;left:0;top:0;width:auto;}',
      '.xycs-slider-track{position:relative;height:36px;margin-top:10px;border-radius:8px;overflow:hidden;',
      'background:var(--xycs-surface-2);border:1px solid var(--xycs-border);}',
      '.xycs-slider-fill{position:absolute;left:0;top:0;height:100%;width:0;',
      'background:color-mix(in oklab,var(--xycs-primary) 18%,transparent);}',
      '.xycs-slider-handle{position:absolute;left:0;top:0;width:36px;height:36px;border-radius:8px;',
      'background:var(--xycs-primary);color:var(--xycs-primary-content);display:flex;align-items:center;',
      'justify-content:center;cursor:grab;touch-action:none;}',
      '.xycs-slider-handle:active{cursor:grabbing;}',
      '.xycs-slider-handle svg{width:16px;height:16px;}',
      '.xycs-chars{display:flex;flex-wrap:wrap;align-items:center;gap:4px;margin-top:10px;font-size:14px;}',
      '.xycs-char{display:inline-flex;align-items:center;justify-content:center;min-width:24px;height:24px;',
      'padding:0 6px;border-radius:6px;font-weight:600;color:var(--xycs-primary);',
      'background:color-mix(in oklab,var(--xycs-primary) 14%,transparent);}',
      '.xycs-char-arrow{opacity:.4;font-size:12px;}',
      '.xycs-click-img{cursor:crosshair;}',
      '.xycs-click-marker{position:absolute;transform:translate(-50%,-50%);display:flex;align-items:center;',
      'justify-content:center;width:20px;height:20px;border-radius:50%;font-size:12px;font-weight:600;',
      'background:var(--xycs-primary);color:var(--xycs-primary-content);pointer-events:none;z-index:1;}',
    ].join('');
    document.head.appendChild(style);
  }

  /** 图片区域状态：loading=取图中 / error=取图失败（点图可重试）/ ready=可作答 */
  function _setImgState(state, msg) {
    if (!_dialog) { return; }
    _dialog.maskLoading.hidden = state !== 'loading';
    _dialog.maskError.hidden = state !== 'error';
    if (state === 'error') { _dialog.maskError.textContent = msg || _t('加载失败，点击重试'); }
    _dialog.img.classList.toggle('is-loading', state !== 'ready');
    _dialog.imgbox.classList.toggle('is-loading', state === 'loading');
    // 取图途中禁用「换一张」，避免连点并发取图
    _dialog.refresh.disabled = state === 'loading';
  }

  function _setError(msg) {
    if (_dialog) { _dialog.err.textContent = msg || ''; }
  }

  /** 按验证码类型调整输入体验：算术走数字键盘；字符按本次出图长度限制输入长度 */
  function _applyInputMode() {
    var isMath = _popup.kind === 'arithmetic';
    var length = parseInt(_popup.options.length, 10);
    if (!(length >= 4 && length <= 6)) { length = 4; }   // 与后端未传 length 时的默认值保持一致
    _dialog.input.maxLength = isMath ? 4 : length;
    _dialog.input.setAttribute('inputmode', isMath ? 'numeric' : 'text');
  }

  /** 有效期提示：每次取图后按后端返回的 expire_in 刷新 */
  function _setExpireHint(seconds) {
    var value = parseInt(seconds, 10);
    if (!(value > 0)) { _dialog.expire.textContent = ''; return; }
    var minutes = Math.max(1, Math.round(value / 60));
    _dialog.expire.textContent = _i('%(minutes)s 分钟内有效', { minutes: minutes });
  }

  /** 校验请求中：锁住输入与按钮，避免重复提交或改动作答内容 */
  function _setVerifying(on) {
    _popup.busy = on;
    _dialog.input.disabled = on;
    _dialog.refresh.disabled = on;
    _dialog.submit.disabled = on;
    _dialog.submit.textContent = on ? _t('请求中…') : _t('确认');
  }

  /** 切换舞台：字符 / 算术共用一个文本舞台，滑块与点选各有独立舞台 */
  function _showStage(kind) {
    var isText = kind === 'char' || kind === 'arithmetic';
    _dialog.stageText.hidden = !isText;
    _dialog.stageSlider.hidden = kind !== 'slider';
    _dialog.stageClick.hidden = kind !== 'click';
    // 滑块 / 点选是「动作即提交」，不需要确认按钮
    _dialog.submit.hidden = !isText;
  }

  /** 构建弹窗（幂等）：结构 + 事件绑定 */
  function _buildDialog() {
    if (_dialog) { return _dialog; }
    _injectStyle();

    var dialog = document.createElement('dialog');
    dialog.className = 'xycs-dialog';
    dialog.setAttribute('aria-labelledby', 'xycaptcha-self-title');
    dialog.setAttribute('aria-describedby', 'xycaptcha-self-tip');
    dialog.innerHTML =
      '<div class="xycs-panel">' +
        '<div class="xycs-head">' +
          // 内联 SVG 盾牌：不依赖 lucide 等外部图标库，脱离本站也能正常显示
          '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
          'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
          '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>' +
          '<span id="xycaptcha-self-title">' + _t('安全验证') + '</span>' +
          '<button type="button" class="xycs-close" aria-label="' + _t('关闭') + '">&times;</button>' +
        '</div>' +
        '<p id="xycaptcha-self-tip" class="xycs-tip">' +
          '<span class="xycs-tip-text"></span><span class="xycs-expire"></span>' +
        '</p>' +
        // ── 文本舞台（字符 / 算术） ──
        '<div class="xycs-stage xycs-stage-text">' +
          '<div class="xycs-imgbox" title="' + _t('点击换一张') + '">' +
            '<img class="xycs-img" alt="' + _t('验证码') + '">' +
            '<span class="xycs-mask xycs-mask-loading"><i class="xycs-spinner"></i>' + _t('加载中…') + '</span>' +
            '<span class="xycs-mask xycs-mask-error" hidden></span>' +
            '<span class="xycs-hint">' + _t('点击换一张') + '</span>' +
          '</div>' +
          '<div class="xycs-row">' +
            '<input id="xycaptcha-self-input" class="xycs-input" type="text" autocomplete="off" ' +
            'autocapitalize="characters" spellcheck="false" enterkeyhint="done" placeholder="' + _t('请输入验证码') + '">' +
            '<button type="button" class="xycs-refresh">' + _t('换一张') + '</button>' +
          '</div>' +
        '</div>' +
        // ── 滑块舞台 ──
        '<div class="xycs-stage xycs-stage-slider" hidden>' +
          '<div class="xycs-media">' +
            '<img class="xycs-slider-bg" alt="' + _t('滑块验证码') + '">' +
            '<img class="xycs-slider-piece" alt="">' +
            '<span class="xycs-mask xycs-slider-mask"><i class="xycs-spinner"></i>' + _t('加载中…') + '</span>' +
          '</div>' +
          '<div class="xycs-slider-track">' +
            '<span class="xycs-slider-fill"></span>' +
            '<span class="xycs-slider-handle" role="slider" tabindex="0" aria-label="' + _t('拖动滑块') + '">' +
              '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
              'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
              '<path d="M5 12h14M13 6l6 6-6 6"/></svg>' +
            '</span>' +
          '</div>' +
        '</div>' +
        // ── 汉字点选舞台 ──
        '<div class="xycs-stage xycs-stage-click" hidden>' +
          '<div class="xycs-chars"></div>' +
          '<div class="xycs-media xycs-click-media">' +
            '<img class="xycs-click-img" alt="' + _t('汉字点选验证码') + '">' +
            '<span class="xycs-mask xycs-click-mask"><i class="xycs-spinner"></i>' + _t('加载中…') + '</span>' +
          '</div>' +
        '</div>' +
        '<p class="xycs-err" role="alert"></p>' +
        '<div class="xycs-actions">' +
          '<button type="button" class="xycs-btn xycs-btn-ghost xycs-cancel">' + _t('取消') + '</button>' +
          '<button type="button" class="xycs-btn xycs-btn-primary xycs-submit">' + _t('确认') + '</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(dialog);

    _dialog = {
      dialog: dialog,
      stageText: dialog.querySelector('.xycs-stage-text'),
      stageSlider: dialog.querySelector('.xycs-stage-slider'),
      stageClick: dialog.querySelector('.xycs-stage-click'),
      imgbox: dialog.querySelector('.xycs-imgbox'),
      img: dialog.querySelector('.xycs-img'),
      tip: dialog.querySelector('.xycs-tip-text'),
      expire: dialog.querySelector('.xycs-expire'),
      maskLoading: dialog.querySelector('.xycs-mask-loading'),
      maskError: dialog.querySelector('.xycs-mask-error'),
      input: dialog.querySelector('.xycs-input'),
      err: dialog.querySelector('.xycs-err'),
      refresh: dialog.querySelector('.xycs-refresh'),
      submit: dialog.querySelector('.xycs-submit'),
      cancel: dialog.querySelector('.xycs-cancel'),
      close: dialog.querySelector('.xycs-close'),
      // 滑块
      sliderBg: dialog.querySelector('.xycs-slider-bg'),
      sliderPiece: dialog.querySelector('.xycs-slider-piece'),
      sliderMask: dialog.querySelector('.xycs-slider-mask'),
      sliderTrack: dialog.querySelector('.xycs-slider-track'),
      sliderFill: dialog.querySelector('.xycs-slider-fill'),
      sliderHandle: dialog.querySelector('.xycs-slider-handle'),
      // 点选
      clickChars: dialog.querySelector('.xycs-chars'),
      clickMedia: dialog.querySelector('.xycs-click-media'),
      clickImg: dialog.querySelector('.xycs-click-img'),
      clickMask: dialog.querySelector('.xycs-click-mask'),
    };

    // 用户主动关闭（取消 / 右上角）：点击时同步通知；ESC 由浏览器关闭，走下方 close 事件兜底
    _dialog.cancel.addEventListener('click', function () { _closePopup(true); });
    _dialog.close.addEventListener('click', function () { _closePopup(true); });
    dialog.addEventListener('close', function () { _notifyClose(); });
    // 点图换一张：绑在图片容器上——加载/失败遮罩会盖住 <img>，绑在 img 上时点遮罩没反应
    _dialog.imgbox.addEventListener('click', function () {
      if (_dialog.refresh.disabled) { return; }   // 取图途中忽略连点
      _setError('');
      _refreshPopup();
    });
    _dialog.refresh.addEventListener('click', function () {
      _setError('');
      _refreshPopup();
    });
    _dialog.submit.addEventListener('click', function () { _submitPopup(); });
    _dialog.input.addEventListener('input', function () {
      // 归一化：去掉空格（移动端输入法容易插入）并统一大写，与后端比对口径一致
      var cleaned = _dialog.input.value.replace(/\s+/g, '').toUpperCase();
      if (cleaned !== _dialog.input.value) { _dialog.input.value = cleaned; }
      _setError('');
    });
    _dialog.input.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') {
        // 必须阻止默认行为：弹窗会在 _submitPopup 里同步关闭，焦点随即回到外层表单控件，
        // 若不阻止，这次回车会继续触发外层 <form> 的隐式提交 → 重复提交，
        // 且此时验证码已交付后端（captchaId 置空），重复提交会重新拉一张验证码并再次弹窗
        event.preventDefault();
        _submitPopup();
      }
    });
    _bindSlider();
    _bindClick();
    return _dialog;
  }

  /* ---------- 随机类型 ---------- */

  /** 按 kind 选项决定本次出什么题：random 时按权重抽，且尽量不和上一次重复 */
  function _pickKind() {
    var configured = _popup.options.kind || 'char';
    if (configured !== 'random') { return configured; }
    var picked = _weightedKind();
    if (picked === _popup.lastKind) { picked = _weightedKind(); }
    _popup.lastKind = picked;
    return picked;
  }

  function _weightedKind() {
    var total = 0;
    var index;
    for (index = 0; index < RANDOM_WEIGHTS.length; index += 1) {
      total += RANDOM_WEIGHTS[index].weight;
    }
    var point = Math.random() * total;
    for (index = 0; index < RANDOM_WEIGHTS.length; index += 1) {
      point -= RANDOM_WEIGHTS[index].weight;
      if (point <= 0) { return RANDOM_WEIGHTS[index].kind; }
    }
    return 'char';
  }

  /* ---------- 取题 ---------- */

  /** 取一张新验证码渲染到弹窗（不清空错误提示，由调用方决定） */
  function _refreshPopup() {
    if (!_dialog) { return Promise.reject(new Error(_t('验证码获取失败'))); }
    var kind = _pickKind();
    _popup.kind = kind;
    _popup.captchaId = '';
    _popup.sliderId = '';
    _popup.challengeId = '';
    _popup.sliderAnswer = null;
    _popup.busy = false;
    _showStage(kind);
    _setExpireHint(0);
    if (kind === 'slider') { return _loadSlider(); }
    if (kind === 'click') { return _loadClick(); }
    return _loadText(kind);
  }

  function _loadText(kind) {
    _setImgState('loading');
    // 提示语随类型变化：字符类照抄字符，算术类填计算结果
    _dialog.tip.textContent = (kind === 'arithmetic')
      ? _t('请计算下图算式的结果，完成安全验证')
      : _t('请输入下图中的字符，完成安全验证');
    _applyInputMode();
    return _fetchCaptcha(kind, _popup.options.length || null)
      .then(function (data) {
        _popup.captchaId = data.captcha_id;
        _dialog.img.src = data.image;
        _dialog.input.value = '';
        _setExpireHint(data.expire_in);
        _setImgState('ready');
        _dialog.input.focus();
        return data;
      })
      .catch(function (err) {
        // 取图失败：提示落在图片区（「点击重试」），不再占用输入框下方的答案错误位
        _setImgState('error', (err && err.message) || _t('验证码获取失败'));
        throw err;
      });
  }

  function _loadSlider() {
    _dialog.tip.textContent = _t('拖动下方滑块，将拼图块对齐缺口');
    _dialog.sliderMask.hidden = false;
    _resetSlider();
    return _fetchJson(SLIDER_GENERATE_URL)
      .then(function (data) {
        _popup.sliderId = data.slider_id;
        _popup.slider = {
          width: Number(data.width) || 320,
          height: Number(data.height) || 160,
          pieceSize: Number(data.piece_size) || 52
        };
        _dialog.sliderBg.src = data.background;
        _dialog.sliderPiece.src = data.piece;
        _dialog.sliderPiece.style.width =
          (_popup.slider.pieceSize / _popup.slider.width * 100) + '%';
        _dialog.sliderPiece.style.top =
          (Number(data.piece_y) / _popup.slider.height * 100) + '%';
        _setExpireHint(data.expire_in);
        _dialog.sliderMask.hidden = true;
        return data;
      })
      .catch(function (err) {
        _dialog.sliderMask.hidden = true;
        _setError((err && err.message) || _t('验证码获取失败'));
        throw err;
      });
  }

  function _loadClick() {
    _dialog.clickChars.textContent = '';
    _dialog.clickMask.hidden = false;
    _clearClickPoints();
    return _fetchJson(CLICK_GENERATE_URL)
      .then(function (data) {
        _popup.challengeId = data.challenge_id;
        _popup.click = {
          width: Number(data.width) || 360,
          height: Number(data.height) || 200,
          count: Number(data.count) || (data.chars ? data.chars.length : 0),
          points: [],
          startTime: 0
        };
        _dialog.clickImg.src = data.image;
        _renderClickChars(data.chars || []);
        _dialog.tip.textContent = _i('请依次点击图中的 %(count)s 个汉字，完成安全验证',
          { count: _popup.click.count });
        _setExpireHint(data.expire_in);
        _dialog.clickMask.hidden = true;
        return data;
      })
      .catch(function (err) {
        _dialog.clickMask.hidden = true;
        _setError((err && err.message) || _t('验证码获取失败'));
        throw err;
      });
  }

  /* ---------- 滑块交互 ---------- */

  function _resetSlider() {
    _popup.drag = null;
    if (!_dialog) { return; }
    _dialog.sliderPiece.style.left = '0';
    _dialog.sliderHandle.style.left = '0';
    _dialog.sliderFill.style.width = '0';
  }

  function _bindSlider() {
    var handle = _dialog.sliderHandle;

    handle.addEventListener('pointerdown', function (event) {
      if (_popup.busy || !_popup.slider || _popup.kind !== 'slider') { return; }
      event.preventDefault();
      try { handle.setPointerCapture(event.pointerId); } catch (e) { /* ignore */ }
      var maxDrag = Math.max(1, _dialog.sliderTrack.clientWidth - handle.offsetWidth);
      _popup.drag = {
        startClientX: event.clientX,
        maxDrag: maxDrag,
        maxImageX: Math.max(1, _popup.slider.width - _popup.slider.pieceSize),
        imageX: 0,
        startTime: _now(),
        points: [{ x: 0, t: 0 }]
      };
      _setError('');
    });

    handle.addEventListener('pointermove', function (event) {
      var drag = _popup.drag;
      if (!drag) { return; }
      event.preventDefault();
      var dx = _clamp(event.clientX - drag.startClientX, 0, drag.maxDrag);
      var imageX = dx / drag.maxDrag * drag.maxImageX;
      drag.imageX = imageX;
      _dialog.sliderPiece.style.left = (imageX / _popup.slider.width * 100) + '%';
      _dialog.sliderHandle.style.left = dx + 'px';
      _dialog.sliderFill.style.width = (dx + handle.offsetWidth) + 'px';

      var t = Math.round(_now() - drag.startTime);
      var last = drag.points[drag.points.length - 1];
      if (drag.points.length < MAX_TRACK_POINTS) {
        // 采样节流：50ms 或位移 ≥2px 才记一个点
        if (t - last.t >= 50 || Math.abs(imageX - last.x) >= 2) {
          drag.points.push({ x: Math.round(imageX * 10) / 10, t: t });
        }
      } else {
        // 点数已满：只移动最后一个点，保证终点位置 / 时间仍然准确
        last.x = Math.round(imageX * 10) / 10;
        last.t = t;
      }
    });

    function finish(event) {
      var drag = _popup.drag;
      if (!drag) { return; }
      if (event) { event.preventDefault(); }
      _popup.drag = null;
      drag.points.push({
        x: Math.round(drag.imageX * 10) / 10,
        t: Math.round(_now() - drag.startTime)
      });
      _popup.sliderAnswer = { x: drag.imageX, track: drag.points };
      _submitPopup();
    }

    handle.addEventListener('pointerup', finish);
    handle.addEventListener('pointercancel', function () { _popup.drag = null; });
  }

  /* ---------- 汉字点选交互 ---------- */

  function _renderClickChars(chars) {
    _dialog.clickChars.textContent = '';
    chars.forEach(function (char, index) {
      if (index > 0) {
        var arrow = document.createElement('span');
        arrow.className = 'xycs-char-arrow';
        arrow.textContent = '→';
        _dialog.clickChars.appendChild(arrow);
      }
      var badge = document.createElement('span');
      badge.className = 'xycs-char';
      badge.textContent = char;
      _dialog.clickChars.appendChild(badge);
    });
  }

  function _clearClickPoints() {
    if (!_dialog) { return; }
    var marks = _dialog.clickMedia.querySelectorAll('.xycs-click-marker');
    for (var i = 0; i < marks.length; i += 1) { marks[i].remove(); }
    if (_popup.click) { _popup.click.points = []; }
  }

  function _bindClick() {
    _dialog.clickMedia.addEventListener('click', function (event) {
      var click = _popup.click;
      if (_popup.busy || !click || _popup.kind !== 'click') { return; }
      if (click.points.length >= click.count) { return; }

      var rect = _dialog.clickImg.getBoundingClientRect();
      if (!rect.width || !rect.height) { return; }
      var x = (event.clientX - rect.left) / rect.width * click.width;
      var y = (event.clientY - rect.top) / rect.height * click.height;
      if (x < 0 || y < 0 || x > click.width || y > click.height) { return; }

      var now = _now();
      if (!click.points.length) { click.startTime = now; }
      click.points.push({
        x: Math.round(x * 10) / 10,
        y: Math.round(y * 10) / 10,
        t: Math.round(now - click.startTime)
      });

      var mark = document.createElement('span');
      mark.className = 'xycs-click-marker';
      mark.style.left = (x / click.width * 100) + '%';
      mark.style.top = (y / click.height * 100) + '%';
      mark.textContent = String(click.points.length);
      _dialog.clickMedia.appendChild(mark);
      _setError('');

      // 点够目标数即提交（与滑块「动作结束即提交」保持一致）
      if (click.points.length >= click.count) { _submitPopup(); }
    });
  }

  /* ---------- 通用 ---------- */

  function _now() {
    return (global.performance && global.performance.now)
      ? global.performance.now()
      : Date.now();
  }

  function _clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function _openPopup() {
    _closeNotified = false;
    _setError('');   // 上次残留的错误提示不带到这一次
    // 已打开时跳过（重复调用 show() 不应报 InvalidStateError）
    if (!_dialog.dialog.open) {
      if (_dialog.dialog.showModal) { _dialog.dialog.showModal(); }
      else { _dialog.dialog.setAttribute('open', ''); }
    }
    if (_popup.kind === 'char' || _popup.kind === 'arithmetic') {
      _dialog.input.focus();
    } else if (_popup.kind === 'slider') {
      _resetSlider();          // 上次可能拖到一半就关了，重新打开从头拖
    } else if (_popup.kind === 'click') {
      _clearClickPoints();     // 同理：清掉上次的点击标记，重新按顺序点
    }
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

  /** 组装本次作答（返回 null 表示还没答完） */
  function _buildSubmission() {
    var kind = _popup.kind;
    if (kind === 'slider') {
      var answer = _popup.sliderAnswer;
      if (!_popup.sliderId || !answer) { return null; }
      return {
        url: SLIDER_VERIFY_URL,
        payload: {
          slider_id: _popup.sliderId,
          x: Number(answer.x).toFixed(1),
          track: JSON.stringify(answer.track)
        },
        handoff: {
          captcha_type: 'slider',
          slider_id: _popup.sliderId,
          x: Number(answer.x).toFixed(1),
          track: JSON.stringify(answer.track)
        }
      };
    }
    if (kind === 'click') {
      var click = _popup.click;
      if (!_popup.challengeId || !click || click.points.length !== click.count) { return null; }
      var points = JSON.stringify(click.points);
      return {
        url: CLICK_VERIFY_URL,
        payload: { challenge_id: _popup.challengeId, points: points },
        handoff: {
          captcha_type: 'click',
          challenge_id: _popup.challengeId,
          points: points
        }
      };
    }
    var answerText = _dialog.input.value.trim();
    if (!answerText) { _setError(_t('请填写验证码')); return null; }
    if (!_popup.captchaId) { _setError(_t('验证码获取失败')); return null; }
    return {
      url: VERIFY_URL,
      payload: { captcha_id: _popup.captchaId, answer: answerText },
      handoff: {
        captcha_type: kind === 'arithmetic' ? 'arithmetic' : 'char',
        captcha_id: _popup.captchaId,
        answer: answerText
      }
    };
  }

  function _submitPopup() {
    if (_popup.busy) { return; }
    var submission = _buildSubmission();
    if (!submission) { return; }

    // autoVerify=false：不调服务端校验，只把参数交给接入方后端消费
    // （验证码一次性，客户端先校验会让后端复验失败）
    if (_popup.options.autoVerify === false) {
      _resetIds();               // 已交给后端，下次 show() 必须重新取一张
      _closePopup(false);        // 流程性关闭，不算“用户主动取消”
      if (typeof _popup.options.onValidate === 'function') {
        _popup.options.onValidate(submission.handoff);
      }
      return;
    }

    _setError('');
    _setVerifying(true);

    _postForm(submission.url, submission.payload).then(function (res) {
      // 先复位忙碌态，失败分支紧接着的 _refreshPopup 会把「换一张」重新置为不可点
      _setVerifying(false);

      if (res.passed) {
        _resetIds();             // 已消费
        _closePopup(false);      // 成功自动关闭：不触发 onClose（非用户主动关闭）
      } else {
        _setError(res.msg || _t('验证未通过，请重新验证'));
        _refreshPopup();         // 一次性已消费，失败必须换新题
      }
      if (_popup.options && typeof _popup.options.onResult === 'function') {
        _popup.options.onResult({ passed: res.passed, msg: res.msg || '' });
      }
    }).catch(function () {
      _setVerifying(false);
      _setError(_t('校验请求失败，请重试'));
      _refreshPopup();
    });
  }

  function _resetIds() {
    _popup.captchaId = '';
    _popup.sliderId = '';
    _popup.challengeId = '';
    _popup.sliderAnswer = null;
  }

  global.XYCaptchaSelf = {
    /** 内联模式：把验证码渲染到页面已有元素上 */
    create: create,

    /** 弹窗模式 - 初始化：预取一张验证码，就绪后回调 onReady */
    init: function (options) {
      _popup.options = options || {};
      _popup.ready = false;
      _popup.lastKind = '';
      _buildDialog();
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
      if (_popup.captchaId || _popup.sliderId || _popup.challengeId) { _openPopup(); return; }
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
