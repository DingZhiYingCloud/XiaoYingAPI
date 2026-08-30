/**
 * 阿里云图形认证 - 小影API封装客户端（极简接入）
 *
 * 将「加载官方 SDK(ct4.js) + 获取 appId + 初始化 + 二次校验」完整封装，
 * 接入方无需了解阿里云 SDK 细节，只需引入本文件并调用两个方法：
 *
 * 用法：
 *   <script src="/static/js/captcha_auth/aliyun/captcha-client.js"></script>
 *   <script>
 *     XYCaptcha.init({
 *       onReady:  function () { ... },  // 验证码就绪时回调（可提示用户）
 *       onResult: function (data) {
 *         // 用户完成验证且服务端二次校验完成后回调
 *         // data.passed === true  → 放行业务
 *         // data.passed === false → 拦截，让用户重新验证
 *         // data.reason           → 失败原因（如 pass_token expire）
 *       },
 *       onError:  function (msg) { ... },  // SDK 加载/初始化失败时回调
 *     });
 *     // 用户点击触发：XYCaptcha.show();
 *   </script>
 *
 * 依赖：本项目托管的官方 SDK `/static/js/captcha_auth/aliyun/ct4.js`
 *       （ct4.js 仅能从阿里云控制台下载，本项目已托管于自身静态服务，接入方无需再下载）
 */
(function (global) {
  'use strict';

  // ── 服务端点（与后端接口严格对应） ──
  var CONFIG_URL = '/api/captcha_auth/aliyun/config';        // 获取图形认证配置（appId）
  var VERIFY_URL = '/api/captcha_auth/aliyun/verify';        // 图形认证二次校验
  var CT4_SRC = '/static/js/captcha_auth/aliyun/ct4.js';     // 官方 SDK（本项目托管）
  var DEFAULT_APP_ID = '296d0fabf47beeacfe50cbc01f8cd4d7';   // config 接口不可用时的兜底 appId

  var _options = null;       // 接入方配置（回调）
  var _captchaObj = null;    // 官方 SDK 实例
  var _initialized = false;  // 是否初始化完成

  function _error(msg) {
    if (_options && typeof _options.onError === 'function') {
      _options.onError(msg);
    }
  }

  /** 动态加载官方 SDK（幂等，重复调用只加载一次） */
  function _loadSdk(callback) {
    if (global.initAlicom4) { callback(); return; } // 已加载
    var script = document.createElement('script');
    script.src = CT4_SRC;
    script.async = true;
    script.onload = function () { callback(); };
    script.onerror = function () { _error('官方 SDK 加载失败，请检查静态资源: ' + CT4_SRC); };
    document.head.appendChild(script);
  }

  /** 获取 appId：优先 config 接口，失败用内置兜底值 */
  function _fetchAppId() {
    return fetch(CONFIG_URL)
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (data && data.code === 10000 && data.data && data.data.app_id) {
          return data.data.app_id;
        }
        return DEFAULT_APP_ID;
      })
      .catch(function () { return DEFAULT_APP_ID; });
  }

  /** 调用二次校验接口，结果交给 onResult 回调 */
  function _verify(validate) {
    var body = new URLSearchParams(validate);
    fetch(VERIFY_URL, { method: 'POST', body: body })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (_options && typeof _options.onResult === 'function') {
          if (data && data.code === 10000) {
            _options.onResult(data.data || { result: 'fail', passed: false, reason: 'unknown', captcha_args: {} });
          } else {
            _options.onResult({ result: 'fail', passed: false, reason: (data && data.msg) || '校验接口异常', captcha_args: {} });
          }
        }
      })
      .catch(function () {
        if (_options && typeof _options.onResult === 'function') {
          _options.onResult({ result: 'fail', passed: false, reason: '校验接口请求失败', captcha_args: {} });
        }
      });
  }

  /** 初始化官方 SDK（initAlicom4）并绑定回调 */
  function _initSdk(appId) {
    global.initAlicom4({ captchaId: appId, product: 'bind' }, function (obj) {
      _captchaObj = obj;
      obj.onNextReady(function () {
        _initialized = true;
        if (_options && typeof _options.onReady === 'function') { _options.onReady(); }
      });
      // 用户图形验证通过 → 自动完成二次校验
      obj.onSuccess(function () {
        var validate = (obj.getValidate && obj.getValidate()) || {};
        if (validate && validate.lot_number) {
          _verify(validate);
        } else if (_options && typeof _options.onResult === 'function') {
          _options.onResult({ result: 'fail', passed: false, reason: '验证参数获取失败', captcha_args: {} });
        }
      });
      obj.onFail(function () {
        if (_options && typeof _options.onResult === 'function') {
          _options.onResult({ result: 'fail', passed: false, reason: '图形验证未通过', captcha_args: {} });
        }
      });
      obj.onError(function () {
        if (_options && typeof _options.onResult === 'function') {
          _options.onResult({ result: 'fail', passed: false, reason: '图形验证出错', captcha_args: {} });
        }
      });
    });
  }

  var XYCaptcha = {
    /**
     * 初始化图形认证（自动加载 SDK → 获取 appId → 初始化）
     * @param {Object} options { onReady, onResult, onError }
     */
    init: function (options) {
      _options = options || {};
      _loadSdk(function () {
        _fetchAppId().then(_initSdk);
      });
    },

    /** 调起图形验证码（需在 init 的 onReady 回调后再调用） */
    show: function () {
      if (_captchaObj) { _captchaObj.showCaptcha(); }
    },

    /** 是否初始化完成 */
    isReady: function () {
      return _initialized;
    },
  };

  global.XYCaptcha = XYCaptcha;
})(window);
