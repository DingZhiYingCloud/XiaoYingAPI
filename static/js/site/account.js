/* 官网账号页公共交互（登录页 / 注册页共用，不依赖任何前端框架）
 * 依赖：页面中存在 {% csrf_token %} 生成的隐藏输入（name=csrfmiddlewaretoken）。
 * 服务端统一返回 {"code", "msg", "data"}；code === 10000 表示成功。
 */
(function () {
  'use strict';

  var SUCCESS = 10000;
  /* 兼容生产(csrftoken)与本地隔离(xyapi_csrftoken)两种 Cookie 名 */
  var CSRF_RE = /(?:^|;\s*)(?:xyapi_csrftoken|csrftoken)=([^;\s]+)/;

  function getCsrfToken() {
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input && input.value) return input.value;
    var m = document.cookie.match(CSRF_RE);
    return m ? m[1] : '';
  }

  /* POST 表单请求（application/x-www-form-urlencoded）
   * 统一把任何响应（含 403/500/非 JSON）解析成 {code,msg,data}，避免“网络异常”误报。 */
  function apiPost(path, data) {
    if (!getCsrfToken()) {
      return Promise.resolve({
        code: -1,
        msg: '页面安全校验信息缺失，请刷新页面后重试',
        data: null
      });
    }
    var body = new URLSearchParams();
    Object.keys(data).forEach(function (k) {
      if (data[k] !== undefined && data[k] !== null && data[k] !== '') body.append(k, data[k]);
    });
    return fetch(path, {
      method: 'POST',
      headers: {
        'X-CSRFToken': getCsrfToken(),
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'
      },
      body: body.toString(),
      credentials: 'same-origin'
    }).then(function (res) {
      return res.text().then(function (text) {
        var payload = null;
        try { payload = JSON.parse(text); } catch (e) { payload = null; }
        if (payload && typeof payload.code !== 'undefined') return payload;
        // 非 JSON（如 CSRF 403 页面、网关错误）：给出可操作的提示而非笼统网络异常
        var msg = res.status === 403
          ? '安全校验失败，页面可能已过期，请刷新后重试'
          : ('请求失败（HTTP ' + (res.status || '未知') + '），请稍后重试');
        return { code: -1, msg: msg, data: null };
      });
    }).catch(function () {
      // 只有真正断网/请求无法发出才提示网络异常
      return { code: -1, msg: '网络异常，请检查网络后重试', data: null };
    });
  }

  function setAlert(alertEl, type, text) {
    if (!alertEl) return;
    alertEl.classList.remove('hidden', 'alert-success', 'alert-error', 'alert-info');
    if (type) alertEl.classList.add(type === 'success' ? 'alert-success' : (type === 'info' ? 'alert-info' : 'alert-error'));
    alertEl.textContent = text || '';
  }

  /* 提交按钮忙碌态：保留原文案用于恢复 */
  function setBusy(btn, busy, busyText) {
    if (!btn) return;
    if (busy) {
      btn.dataset.originalText = btn.textContent;
      btn.textContent = busyText || '请稍候…';
      btn.classList.add('btn-disabled', 'pointer-events-none', 'opacity-70');
    } else {
      btn.textContent = btn.dataset.originalText || btn.textContent;
      btn.classList.remove('btn-disabled', 'pointer-events-none', 'opacity-70');
    }
  }

  /* 获取验证码按钮倒计时 */
  function startCountdown(btn, seconds) {
    if (!btn) return;
    btn.disabled = true;
    btn.dataset.originalText = btn.dataset.originalText || btn.textContent;
    var left = seconds;
    var timer = setInterval(function () {
      left -= 1;
      if (left <= 0) {
        clearInterval(timer);
        btn.disabled = false;
        btn.textContent = btn.dataset.originalText || '获取验证码';
      } else {
        btn.textContent = left + 's 后重发';
      }
    }, 1000);
  }

  /* 在当前页面找出所属面板表单：登录页/注册页各自前缀 */
  function isRegisterPage() {
    return location.pathname.indexOf('/register') === 0;
  }

  function panelFormId(tab) {
    return (isRegisterPage() ? 'register-' : 'login-') + tab + '-form';
  }

  /* 注册成功展示：提示账号并引导去登录 */
  function showRegisterDone(alertEl, panelForm, data) {
    panelForm.classList.add('hidden');
    var text = '注册成功！您的账号为 ' + data.account + '，请妥善保存。';
    setAlert(alertEl, 'success', text);

    var link = document.createElement('a');
    link.href = '/login/';
    link.className = 'link link-primary font-medium';
    link.textContent = '去登录';
    var hint = document.createElement('p');
    hint.className = 'mt-1 text-sm';
    hint.textContent = '现在 ';
    hint.appendChild(link);
    alertEl.appendChild(hint);
  }

  /* ---------- 登录方式 Tab ---------- */
  var tabBtns = document.querySelectorAll('[data-auth-tab]');
  tabBtns.forEach(function (btn) {
    btn.addEventListener('click', function () {
      var tab = btn.dataset.authTab;
      // 同 tablist 内切换高亮
      var tabs = btn.parentElement.querySelectorAll('[data-auth-tab]');
      tabs.forEach(function (b) { b.classList.remove('tab-active'); });
      btn.classList.add('tab-active');
      // 切换面板
      document.querySelectorAll('.auth-panel').forEach(function (f) {
        f.classList.toggle('hidden', f.id !== panelFormId(tab));
      });
      // 清空提示
      var alertEl = document.getElementById(isRegisterPage() ? 'register-alert' : 'login-alert');
      if (alertEl) alertEl.classList.add('hidden');
    });
  });

  /* ---------- 登录 ---------- */
  function bindLogin() {
    var alertEl = document.getElementById('login-alert');

    var accountForm = document.getElementById('login-account-form');
    if (accountForm) {
      accountForm.addEventListener('submit', function (e) {
        e.preventDefault();
        var btn = accountForm.querySelector('[type="submit"]');
        var account = document.getElementById('login-account').value.trim();
        var password = document.getElementById('login-password').value;
        if (!account || !password) return setAlert(alertEl, 'error', '请输入账号和密码');
        setBusy(btn, true, '登录中…');
        apiPost('/login/', {
          login_type: 'account',
          account: account,
          password: password,
          next: (document.getElementById('login-next') || { value: '' }).value
        })
          .then(function (res) {
            if (res.code === SUCCESS) {
              setAlert(alertEl, 'success', '登录成功，正在跳转…');
              window.location.href = (res.data && res.data.redirect) || '/';
            } else {
              setBusy(btn, false);
              setAlert(alertEl, 'error', res.msg || '登录失败，请稍后重试');
            }
          })
          .catch(function () { setBusy(btn, false); setAlert(alertEl, 'error', '网络异常，请稍后重试'); });
      });
    }

    ['email', 'phone'].forEach(function (method) {
      var form = document.getElementById('login-' + method + '-form');
      if (!form) return;
      var credEl = document.getElementById('login-' + method + '-credential');
      var codeEl = document.getElementById('login-' + method + '-code');

      form.addEventListener('submit', function (e) {
        e.preventDefault();
        var btn = form.querySelector('[type="submit"]');
        var credential = credEl.value.trim();
        var code = codeEl.value.trim();
        if (!credential || !code) return setAlert(alertEl, 'error', '请填写' + (method === 'email' ? '邮箱' : '手机号') + '和验证码');
        setBusy(btn, true, '登录中…');
        var params = {
          login_type: method,
          code: code,
          next: (document.getElementById('login-next') || { value: '' }).value
        };
        params[method] = credential;
        apiPost('/login/', params)
          .then(function (res) {
            if (res.code === SUCCESS) {
              setAlert(alertEl, 'success', '登录成功，正在跳转…');
              window.location.href = (res.data && res.data.redirect) || '/';
            } else {
              setBusy(btn, false);
              setAlert(alertEl, 'error', res.msg || '登录失败，请稍后重试');
            }
          })
          .catch(function () { setBusy(btn, false); setAlert(alertEl, 'error', '网络异常，请稍后重试'); });
      });
    });

    // 发送登录验证码
    document.querySelectorAll('[data-send-code]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var prefix = btn.dataset.sendCode; // 形如 login-email / login-phone
        var method = prefix.indexOf('phone') > -1 ? 'phone' : 'email';
        var credEl = document.getElementById(prefix + '-credential');
        var credential = credEl.value.trim();
        if (!credential) return setAlert(alertEl, 'error', '请先填写' + (method === 'email' ? '邮箱' : '手机号'));
        btn.disabled = true;
        apiPost('/login/send-code/', { method: method, credential: credential })
          .then(function (res) {
            if (res.code === SUCCESS) {
              setAlert(alertEl, 'success', res.msg || '验证码已发送');
              startCountdown(btn, 60);
            } else {
              btn.disabled = false;
              setAlert(alertEl, 'error', res.msg || '发送失败，请稍后重试');
            }
          })
          .catch(function () { btn.disabled = false; setAlert(alertEl, 'error', '网络异常，请稍后重试'); });
      });
    });
  }

  /* ---------- 注册 ---------- */
  function bindRegister() {
    var alertEl = document.getElementById('register-alert');

    // 纯用户名注册（直接建号）
    var usernameForm = document.getElementById('register-username-form');
    if (usernameForm) {
      usernameForm.addEventListener('submit', function (e) {
        e.preventDefault();
        var btn = usernameForm.querySelector('[type="submit"]');
        var username = document.getElementById('reg-username-name').value.trim();
        var password = document.getElementById('reg-username-password').value;
        if (!username) return setAlert(alertEl, 'error', '请输入用户名');
        if (password.length < 8) return setAlert(alertEl, 'error', '密码长度至少 8 位');
        setBusy(btn, true, '注册中…');
        apiPost('/register/', { username: username, password: password })
          .then(function (res) {
            if (res.code === SUCCESS) {
              showRegisterDone(alertEl, usernameForm, res.data);
            } else {
              setBusy(btn, false);
              setAlert(alertEl, 'error', res.msg || '注册失败，请稍后重试');
            }
          })
          .catch(function () { setBusy(btn, false); setAlert(alertEl, 'error', '网络异常，请稍后重试'); });
      });
    }

    // 邮箱 / 手机号两步注册
    ['email', 'phone'].forEach(function (method) {
      var form = document.getElementById('register-' + method + '-form');
      if (!form) return;
      var nameEl = document.getElementById('reg-' + method + '-name');
      var credEl = document.getElementById('reg-' + method + '-credential');
      var pwdEl = document.getElementById('reg-' + method + '-password');
      var codeEl = document.getElementById('reg-' + method + '-code');
      var echoEl = form.querySelector('[data-reg-credential-echo]');
      var resendBtn = form.querySelector('[data-reg-resend]');
      var fieldsBlock = form.querySelector('[data-reg-fields]');
      var verifyBlock = form.querySelector('[data-reg-verify]');

      form.addEventListener('submit', function (e) {
        e.preventDefault();
        var btn = form.querySelector('[type="submit"]');

        if (!form.dataset.credential) {
          // 第一步：提交注册意向（发码暂存，不建号）
          var username = nameEl.value.trim();
          var credential = credEl.value.trim();
          var password = pwdEl.value;
          if (!credential) return setAlert(alertEl, 'error', '请填写' + (method === 'email' ? '邮箱' : '手机号'));
          if (password.length < 8) return setAlert(alertEl, 'error', '密码长度至少 8 位');
          setBusy(btn, true, '提交中…');
          var params = { password: password };
          if (username) params.username = username;
          params[method] = credential;
          apiPost('/register/', params).then(function (res) {
            if (res.code === SUCCESS && res.data && res.data.step === 'verify') {
              // 记录凭证进入校验步骤
              form.dataset.credential = credential;
              echoEl.textContent = credential;
              fieldsBlock.classList.add('hidden');
              verifyBlock.classList.remove('hidden');
              setBusy(btn, false);
              setAlert(alertEl, 'success', res.msg || '验证码已发送');
              startCountdown(resendBtn, 60);
            } else {
              setBusy(btn, false);
              if (res.code === SUCCESS && res.data) {
                showRegisterDone(alertEl, form, res.data); // 纯用户名兜底
              } else {
                setAlert(alertEl, 'error', res.msg || '注册失败，请稍后重试');
              }
            }
          }).catch(function () { setBusy(btn, false); setAlert(alertEl, 'error', '网络异常，请稍后重试'); });
        } else {
          // 第二步：校验验证码，通过后建号发放账号
          var code = codeEl.value.trim();
          if (!code) return setAlert(alertEl, 'error', '请输入验证码');
          setBusy(btn, true, '注册中…');
          apiPost('/register/verify/', {
            method: method, credential: form.dataset.credential, code: code
          }).then(function (res) {
            if (res.code === SUCCESS) {
              showRegisterDone(alertEl, form, res.data);
            } else {
              setBusy(btn, false);
              setAlert(alertEl, 'error', res.msg || '验证失败，请稍后重试');
            }
          }).catch(function () { setBusy(btn, false); setAlert(alertEl, 'error', '网络异常，请稍后重试'); });
        }
      });

      // 重发注册验证码
      resendBtn.addEventListener('click', function () {
        if (!form.dataset.credential) return;
        apiPost('/register/resend/', { method: method, credential: form.dataset.credential })
          .then(function (res) {
            if (res.code === SUCCESS) {
              setAlert(alertEl, 'success', res.msg || '验证码已重新发送');
              startCountdown(resendBtn, 60);
            } else {
              setAlert(alertEl, 'error', res.msg || '发送失败，请稍后重试');
            }
          })
          .catch(function () { setAlert(alertEl, 'error', '网络异常，请稍后重试'); });
      });
    });
  }

  if (isRegisterPage()) { bindRegister(); } else { bindLogin(); }
})();
