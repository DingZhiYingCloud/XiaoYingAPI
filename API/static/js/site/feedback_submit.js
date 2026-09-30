/**
 * 问题反馈中心 · 提交页脚本（仅游客需要：提交前完成一次图形验证）
 *
 * 与官网登录 / 注册同一口径：图形验证以**服务端二次校验为准**，
 * 前端只负责收集 `captcha_id` + `answer` 并随表单一起提交，
 * 因此弹窗必须用 `autoVerify: false` —— 客户端先校验会把一次性验证码消费掉，
 * 后端复验必然失败。
 *
 * 表单是普通 multipart POST（要带附件），所以验证通过后调用 form.submit()
 * 原生提交（该方式不会再触发 submit 事件，天然避免死循环）。
 */
(function () {
  'use strict';

  var form = document.getElementById('fb-submit-form');
  if (!form) { return; }

  // 未启用图形验证（登录用户 / 后台关闭）时不做任何拦截，让表单正常提交
  if (window.XY_FB_CAPTCHA !== true || !window.XYCaptchaSelf) { return; }

  var captchaStarted = false;   // 是否已初始化（惰性：不提交就不取验证码）
  var captchaReady = false;     // 验证码是否已就绪
  var passed = false;           // 是否已通过验证（放行原生提交）

  function startCaptcha() {
    captchaStarted = true;
    window.XYCaptchaSelf.init({
      autoVerify: false,
      onReady: function () {
        captchaReady = true;
        window.XYCaptchaSelf.show();
      },
      onValidate: function (data) {
        document.getElementById('fb-captcha-id').value = data.captcha_id;
        document.getElementById('fb-captcha-answer').value = data.answer;
        passed = true;
        form.submit();
      },
      onError: function () {
        // 初始化失败：允许下次提交重新初始化
        captchaStarted = false;
      }
    });
  }

  form.addEventListener('submit', function (event) {
    if (passed) { return; }
    // 浏览器原生校验（required / maxlength 等）已在 submit 事件之前通过，这里只拦图形验证
    event.preventDefault();
    if (captchaReady) {
      window.XYCaptchaSelf.show();
      return;
    }
    if (!captchaStarted) { startCaptcha(); }
    // 已在初始化中：等 onReady 回调自动弹出
  });
})();
