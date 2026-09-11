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
        msg: gettext('页面安全校验信息缺失，请刷新页面后重试'),
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
          ? gettext('安全校验失败，页面可能已过期，请刷新后重试')
          : interpolate(gettext('请求失败（HTTP %(status)s），请稍后重试'), { status: res.status || gettext('未知') }, true);
        return { code: -1, msg: msg, data: null };
      });
    }).catch(function () {
      // 只有真正断网/请求无法发出才提示网络异常
      return { code: -1, msg: gettext('网络异常，请检查网络后重试'), data: null };
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
      btn.textContent = busyText || gettext('请稍候…');
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
        btn.textContent = btn.dataset.originalText || gettext('获取验证码');
      } else {
        btn.textContent = interpolate(gettext('%(seconds)ss 后重发'), { seconds: left }, true);
      }
    }, 1000);
  }

  /* ---------- 图形验证（自研验证码） ----------
   * 以服务端二次校验为准：这里只负责「先让用户完成图形验证，再把 captcha_id + answer 并入请求交给后端」。
   * 因此弹窗必须用 autoVerify:false —— 客户端先校验会把一次性验证码消费掉，后端复验必然失败。
   * 后端可用 CAPTCHA_SELF_ENABLED=false 关闭校验，页面据 window.XY_CAPTCHA_ENABLED 同步不弹，前后端口径一致。
   */
  var captchaStarted = false; // 是否已初始化（惰性初始化：不提交就不取验证码）
  var captchaReady = false;   // 验证码是否已就绪
  var captchaPending = null;  // 等待图形验证的提交 { payload, post, alertEl }

  function captchaNeeded() {
    return window.XY_CAPTCHA_ENABLED === true && !!window.XYCaptchaSelf;
  }

  /* 提交：需要图形验证时先弹验证码，用户填写后把验证参数并入 payload 真正提交 */
  function submitWithCaptcha(payload, post, alertEl) {
    if (!captchaNeeded()) return post(payload);
    captchaPending = { payload: payload, post: post, alertEl: alertEl };
    if (captchaReady) {
      XYCaptchaSelf.show();
    } else if (!captchaStarted) {
      startCaptcha(alertEl);
    }
    // 已在初始化中：等 onReady 回调自动弹出
  }

  /* 首次提交时才初始化（会顺带取一张验证码），就绪后自动弹出 */
  function startCaptcha(alertEl) {
    captchaStarted = true;
    setAlert(alertEl, 'info', gettext('正在加载图形验证，请稍候…'));
    XYCaptchaSelf.init({
      autoVerify: false,   // 交后端二次校验；客户端先校验会消耗掉一次性验证码
      onReady: function () {
        captchaReady = true;
        if (captchaPending) XYCaptchaSelf.show();
      },
      onValidate: function (data) {   // data = {captcha_id, answer}
        var job = captchaPending;
        captchaPending = null;
        if (job) job.post(Object.assign({}, job.payload, data));
      },
      onClose: function () {
        var job = captchaPending;
        captchaPending = null;
        if (job) setAlert(job.alertEl, 'info', gettext('已取消图形验证'));
      },
      onError: function (msg) {
        captchaStarted = false;   // 初始化失败：允许下次提交重新初始化
        var job = captchaPending;
        captchaPending = null;
        setAlert(job ? job.alertEl : null, 'error', msg || gettext('图形验证加载失败，请刷新页面后重试'));
      }
    });
  }

  /* 当前页面类型：login / register / reset（决定面板表单与提示元素的 id 前缀） */
  function pageKind() {
    if (location.pathname.indexOf('/reset-password') === 0) return 'reset';
    if (location.pathname.indexOf('/register') === 0) return 'register';
    return 'login';
  }

  function panelFormId(tab) {
    return pageKind() + '-' + tab + '-form';
  }

  /* 注册成功展示：提示账号并引导去登录 */
  function showRegisterDone(alertEl, panelForm, data) {
    panelForm.classList.add('hidden');
    var text = interpolate(gettext('注册成功！您的账号为 %(account)s，请妥善保存。'), { account: data.account }, true);
    setAlert(alertEl, 'success', text);

    var link = document.createElement('a');
    link.href = '/login/';
    link.className = 'link link-primary font-medium';
    link.textContent = gettext('去登录');
    var hint = document.createElement('p');
    hint.className = 'mt-1 text-sm';
    hint.textContent = gettext('现在 ');
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
      var alertEl = document.getElementById(pageKind() + '-alert');
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
        if (!account || !password) return setAlert(alertEl, 'error', gettext('请输入账号和密码'));
        submitWithCaptcha({
          login_type: 'account',
          account: account,
          password: password,
          next: (document.getElementById('login-next') || { value: '' }).value
        }, function (payload) {
          setBusy(btn, true, gettext('登录中…'));
          return apiPost('/login/', payload)
            .then(function (res) {
              if (res.code === SUCCESS) {
                setAlert(alertEl, 'success', gettext('登录成功，正在跳转…'));
                window.location.href = (res.data && res.data.redirect) || '/';
              } else {
                setBusy(btn, false);
                setAlert(alertEl, 'error', res.msg || gettext('登录失败，请稍后重试'));
              }
            })
            .catch(function () { setBusy(btn, false); setAlert(alertEl, 'error', gettext('网络异常，请稍后重试')); });
        }, alertEl);
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
        if (!credential || !code) return setAlert(alertEl, 'error', interpolate(gettext('请填写%(type)s和验证码'), { type: method === 'email' ? gettext('邮箱') : gettext('手机号') }, true));
        var params = {
          login_type: method,
          code: code,
          next: (document.getElementById('login-next') || { value: '' }).value
        };
        params[method] = credential;
        submitWithCaptcha(params, function (payload) {
          setBusy(btn, true, gettext('登录中…'));
          return apiPost('/login/', payload)
            .then(function (res) {
              if (res.code === SUCCESS) {
                setAlert(alertEl, 'success', gettext('登录成功，正在跳转…'));
                window.location.href = (res.data && res.data.redirect) || '/';
              } else {
                setBusy(btn, false);
                setAlert(alertEl, 'error', res.msg || gettext('登录失败，请稍后重试'));
              }
            })
            .catch(function () { setBusy(btn, false); setAlert(alertEl, 'error', gettext('网络异常，请稍后重试')); });
        }, alertEl);
      });
    });

    // 发送登录验证码
    document.querySelectorAll('[data-send-code]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var prefix = btn.dataset.sendCode; // 形如 login-email / login-phone
        var method = prefix.indexOf('phone') > -1 ? 'phone' : 'email';
        var credEl = document.getElementById(prefix + '-credential');
        var credential = credEl.value.trim();
        if (!credential) return setAlert(alertEl, 'error', interpolate(gettext('请先填写%(type)s'), { type: method === 'email' ? gettext('邮箱') : gettext('手机号') }, true));
        submitWithCaptcha({ method: method, credential: credential }, function (payload) {
          btn.disabled = true;
          return apiPost('/login/send-code/', payload)
            .then(function (res) {
              if (res.code === SUCCESS) {
                setAlert(alertEl, 'success', res.msg || gettext('验证码已发送'));
                startCountdown(btn, 60);
              } else {
                btn.disabled = false;
                setAlert(alertEl, 'error', res.msg || gettext('发送失败，请稍后重试'));
              }
            })
            .catch(function () { btn.disabled = false; setAlert(alertEl, 'error', gettext('网络异常，请稍后重试')); });
        }, alertEl);
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
        if (!username) return setAlert(alertEl, 'error', gettext('请输入用户名'));
        if (password.length < 8) return setAlert(alertEl, 'error', gettext('密码长度至少 8 位'));
        submitWithCaptcha({ username: username, password: password }, function (payload) {
          setBusy(btn, true, gettext('注册中…'));
          return apiPost('/register/', payload)
            .then(function (res) {
              if (res.code === SUCCESS) {
                showRegisterDone(alertEl, usernameForm, res.data);
              } else {
                setBusy(btn, false);
                setAlert(alertEl, 'error', res.msg || gettext('注册失败，请稍后重试'));
              }
            })
            .catch(function () { setBusy(btn, false); setAlert(alertEl, 'error', gettext('网络异常，请稍后重试')); });
        }, alertEl);
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
          if (!credential) return setAlert(alertEl, 'error', interpolate(gettext('请填写%(type)s'), { type: method === 'email' ? gettext('邮箱') : gettext('手机号') }, true));
          if (password.length < 8) return setAlert(alertEl, 'error', gettext('密码长度至少 8 位'));
          var params = { password: password };
          if (username) params.username = username;
          params[method] = credential;
          submitWithCaptcha(params, function (payload) {
            setBusy(btn, true, gettext('提交中…'));
            return apiPost('/register/', payload).then(function (res) {
              if (res.code === SUCCESS && res.data && res.data.step === 'verify') {
                // 记录凭证进入校验步骤
                form.dataset.credential = credential;
                echoEl.textContent = credential;
                fieldsBlock.classList.add('hidden');
                verifyBlock.classList.remove('hidden');
                setBusy(btn, false);
                setAlert(alertEl, 'success', res.msg || gettext('验证码已发送'));
                startCountdown(resendBtn, 60);
              } else {
                setBusy(btn, false);
                if (res.code === SUCCESS && res.data) {
                  showRegisterDone(alertEl, form, res.data); // 纯用户名兜底
                } else {
                  setAlert(alertEl, 'error', res.msg || gettext('注册失败，请稍后重试'));
                }
              }
            }).catch(function () { setBusy(btn, false); setAlert(alertEl, 'error', gettext('网络异常，请稍后重试')); });
          }, alertEl);
        } else {
          // 第二步：校验验证码，通过后建号发放账号
          var code = codeEl.value.trim();
          if (!code) return setAlert(alertEl, 'error', gettext('请输入验证码'));
          setBusy(btn, true, gettext('注册中…'));
          apiPost('/register/verify/', {
            method: method, credential: form.dataset.credential, code: code
          }).then(function (res) {
            if (res.code === SUCCESS) {
              showRegisterDone(alertEl, form, res.data);
            } else {
              setBusy(btn, false);
              setAlert(alertEl, 'error', res.msg || gettext('验证失败，请稍后重试'));
            }
          }).catch(function () { setBusy(btn, false); setAlert(alertEl, 'error', gettext('网络异常，请稍后重试')); });
        }
      });

      // 重发注册验证码
      resendBtn.addEventListener('click', function () {
        if (!form.dataset.credential) return;
        submitWithCaptcha({ method: method, credential: form.dataset.credential }, function (payload) {
          return apiPost('/register/resend/', payload)
            .then(function (res) {
              if (res.code === SUCCESS) {
                setAlert(alertEl, 'success', res.msg || gettext('验证码已重新发送'));
                startCountdown(resendBtn, 60);
              } else {
                setAlert(alertEl, 'error', res.msg || gettext('发送失败，请稍后重试'));
              }
            })
            .catch(function () { setAlert(alertEl, 'error', gettext('网络异常，请稍后重试')); });
        }, alertEl);
      });
    });
  }

  /* 重置成功展示：提示并引导去登录 */
  function showResetDone(alertEl, panelForm) {
    panelForm.classList.add('hidden');
    setAlert(alertEl, 'success', gettext('密码已重置，请用新密码登录。'));

    var link = document.createElement('a');
    link.href = '/login/';
    link.className = 'link link-primary font-medium';
    link.textContent = gettext('去登录');
    var hint = document.createElement('p');
    hint.className = 'mt-1 text-sm';
    hint.textContent = gettext('现在 ');
    hint.appendChild(link);
    alertEl.appendChild(hint);
  }

  /* ---------- 重置密码（忘记密码） ---------- */
  function bindReset() {
    var alertEl = document.getElementById('reset-alert');

    ['email', 'phone'].forEach(function (method) {
      var form = document.getElementById('reset-' + method + '-form');
      if (!form) return;
      var credEl = document.getElementById('reset-' + method + '-credential');
      var codeEl = document.getElementById('reset-' + method + '-code');
      var pwdEl = document.getElementById('reset-' + method + '-password');
      var pwd2El = document.getElementById('reset-' + method + '-password2');
      var sendBtn = form.querySelector('[data-reset-send]');
      var label = method === 'email' ? gettext('邮箱') : gettext('手机号');

      // 发送重置验证码（需先通过图形验证）
      sendBtn.addEventListener('click', function () {
        var cred = credEl.value.trim();
        if (!cred) return setAlert(alertEl, 'error', interpolate(gettext('请先填写%(type)s'), { type: label }, true));
        var payload = { method: method };
        payload[method] = cred;
        submitWithCaptcha(payload, function (p) {
          sendBtn.disabled = true;
          return apiPost('/reset-password/', p)
            .then(function (res) {
              if (res.code === SUCCESS) {
                setAlert(alertEl, 'success', res.msg || gettext('验证码已发送'));
                startCountdown(sendBtn, 60);
              } else {
                sendBtn.disabled = false;
                setAlert(alertEl, 'error', res.msg || gettext('发送失败，请稍后重试'));
              }
            })
            .catch(function () { sendBtn.disabled = false; setAlert(alertEl, 'error', gettext('网络异常，请稍后重试')); });
        }, alertEl);
      });

      // 提交重置（校验验证码 + 设置新密码）
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        var btn = form.querySelector('[type="submit"]');
        var cred = credEl.value.trim();
        var code = codeEl.value.trim();
        var pwd = pwdEl.value;
        if (!cred) return setAlert(alertEl, 'error', interpolate(gettext('请填写%(type)s'), { type: label }, true));
        if (!code) return setAlert(alertEl, 'error', gettext('请输入验证码'));
        if (pwd.length < 8) return setAlert(alertEl, 'error', gettext('密码长度至少 8 位'));
        if (pwd !== pwd2El.value) return setAlert(alertEl, 'error', gettext('两次输入的密码不一致'));
        var params = { method: method, code: code, password: pwd };
        params[method] = cred;
        setBusy(btn, true, gettext('提交中…'));
        apiPost('/reset-password/submit/', params)
          .then(function (res) {
            setBusy(btn, false);
            if (res.code === SUCCESS) {
              showResetDone(alertEl, form);
            } else {
              setAlert(alertEl, 'error', res.msg || gettext('重置失败，请稍后重试'));
            }
          })
          .catch(function () { setBusy(btn, false); setAlert(alertEl, 'error', gettext('网络异常，请稍后重试')); });
      });
    });
  }

  if (pageKind() === 'register') {
    bindRegister();
  } else if (pageKind() === 'reset') {
    bindReset();
  } else {
    bindLogin();
  }
})();
