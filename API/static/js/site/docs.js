/* API 文档中心交互：线路切换 / 鉴权本机保存 / 在线调试代调 / 响应展示
 * 依赖：页面含 {% csrf_token %}（#docs-auth-form 内）；调试结果由服务端 /docs/_call/ 代调返回。 */
(function () {
  'use strict';

  var AUTH_KEY = 'xyapi_docs_auth';
  var CSRF_RE = /(?:^|;\s*)(?:xyapi_csrftoken|csrftoken)=([^;\s]+)/;

  function getCsrfToken() {
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input && input.value) return input.value;
    var m = document.cookie.match(CSRF_RE);
    return m ? m[1] : '';
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  /* ---------- 左侧导航：按 URL/hash 自动高亮并展开祖先 ---------- */
  function markActive(li) {
    if (li) li.classList.add('menu-active');
  }

  function activateDocsNav() {
    var path = location.pathname;

    // 文档中心首页
    var root = document.querySelector('[data-docs-nav-root]');
    if (root && path === '/docs/') {
      markActive(root.closest('li'));
      return;
    }

    // 先找子线路（leaf）精确匹配当前页
    var matched = null;
    document.querySelectorAll('[data-docs-leaf]').forEach(function (a) {
      if (matched) return;
      try {
        if (new URL(a.href, location.href).pathname === path) matched = a;
      } catch (e) { /* ignore */ }
    });
    if (matched) {
      var group = matched.closest('details');
      if (group) group.open = true;
      markActive(matched.closest('li'));
      return;
    }

    // 未命中子线路：展开并高亮当前服务分组（如 /docs/email/）
    document.querySelectorAll('[data-docs-group]').forEach(function (details) {
      try {
        if (new URL(details.dataset.activeUrl, location.href).pathname === path) {
          details.open = true;
          markActive(details.closest('li'));
        }
      } catch (e) { /* ignore */ }
    });
  }

  // 依据 URL hash（#channel-<slug>）切换到对应线路并滚动到可见
  function openChannelByHash() {
    var m = (location.hash || '').match(/^#channel-(.+)$/);
    if (!m) return;
    var slug = m[1];
    var tab = document.querySelector('[data-doc-tab="' + slug + '"]');
    var panel = document.querySelector('[data-channel-panel="' + slug + '"]');
    if (tab && tab.getAttribute('role') === 'tab') {
      // 复用 tab 点击逻辑切换面板
      var active = tab.parentElement.querySelector('[data-doc-tab].tab-active');
      if (active) active.classList.remove('tab-active');
      tab.classList.add('tab-active');
      document.querySelectorAll('[data-channel-panel]').forEach(function (p) {
        p.classList.toggle('hidden', p.dataset.channelPanel !== slug);
      });
    }
    // 同步左侧子菜单高亮（同一服务的线路切换）
    var hit = null;
    document.querySelectorAll('[data-docs-leaf]').forEach(function (a) {
      var li = a.closest('li');
      if (li) li.classList.remove('menu-active');
      try {
        var u = new URL(a.href, location.href);
        if (u.pathname === location.pathname && u.hash === '#channel-' + slug) hit = a;
      } catch (e) { /* ignore */ }
    });
    if (hit) {
      var group = hit.closest('details');
      if (group) group.open = true;
      var hitLi = hit.closest('li');
      if (hitLi) hitLi.classList.add('menu-active');
    }
    if (panel) {
      setTimeout(function () {
        panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 60);
    }
  }

  activateDocsNav();
  openChannelByHash();
  window.addEventListener('hashchange', openChannelByHash);

  /* ---------- 线路 Tab 切换 ---------- */
  var tabBtns = document.querySelectorAll('[data-doc-tab]');
  tabBtns.forEach(function (btn) {
    btn.addEventListener('click', function () {
      var slug = btn.dataset.docTab;
      tabBtns.forEach(function (b) { b.classList.remove('tab-active'); });
      btn.classList.add('tab-active');
      document.querySelectorAll('[data-channel-panel]').forEach(function (panel) {
        panel.classList.toggle('hidden', panel.dataset.channelPanel !== slug);
      });
    });
  });

  /* ---------- 鉴权设置：本机保存/回填 ---------- */
  var authId = document.getElementById('doc-app-id');
  var authSecret = document.getElementById('doc-app-secret');
  var authSave = document.getElementById('docs-auth-save');

  if (authSave && authId && authSecret) {
    try {
      var saved = JSON.parse(localStorage.getItem(AUTH_KEY) || 'null');
      if (saved && saved.app_id) authId.value = saved.app_id;
      if (saved && saved.app_secret) authSecret.value = saved.app_secret;
    } catch (e) { /* 忽略损坏的本地数据 */ }

    authSave.addEventListener('click', function () {
      localStorage.setItem(AUTH_KEY, JSON.stringify({
        app_id: authId.value.trim(),
        app_secret: authSecret.value.trim()
      }));
      var old = authSave.textContent;
      authSave.textContent = gettext('已保存到本机');
      setTimeout(function () { authSave.textContent = old; }, 1500);
    });
  }

  /* ---------- 在线调试代调 ---------- */
  function runEndpoint(btn) {
    var card = btn.closest('article');
    var path = btn.dataset.path;
    var method = btn.dataset.method;
    var resId = 'res-' + btn.dataset.res;
    var resBox = document.getElementById(resId);
    var params = {};
    var fileFields = {};

    card.querySelectorAll('[data-param-name]').forEach(function (field) {
      var name = field.dataset.paramName;
      if (field.type === 'file') {
        // 文件字段：只取已选择的真实文件
        if (field.files && field.files.length) {
          fileFields[name] = field.files[0];
        }
        return;
      }
      var value = field.value;
      if (field.hasAttribute('data-repeatable')) {
        // 多值字段：按逗号/换行拆成数组，服务端以“同名多次传参”接收
        var parts = String(value).split(/[\s,，]+/).map(function (s) { return s.trim(); }).filter(Boolean);
        if (parts.length) params[name] = parts.length > 1 ? parts : parts[0];
      } else if (String(value).trim() !== '') {
        params[name] = value.trim();
      }
    });

    btn.disabled = true;
    var oldText = btn.textContent;
    btn.textContent = gettext('请求中…');
    resBox.classList.remove('hidden');
    resBox.innerHTML = '';
    resBox.appendChild(el('div', 'text-sm text-base-content/60 py-2', interpolate(gettext('正在请求 %(path)s …'), { path: path }, true)));

    var app_id = (authId ? authId.value.trim() : '');
    var app_secret = (authSecret ? authSecret.value.trim() : '');

    var hasFile = Object.keys(fileFields).length > 0;

    function parseDone(res) { return res.json(); }
    function showErr() {
      resBox.innerHTML = '';
      resBox.appendChild(el('p', 'text-sm text-error', gettext('网络异常，请检查网络后重试')));
    }

    if (hasFile) {
      // 含真实文件 → 以 multipart/form-data 提交，由服务端代调转发
      var fd = new FormData();
      fd.append('path', path);
      fd.append('method', method);
      if (app_id) fd.append('app_id', app_id);
      if (app_secret) fd.append('app_secret', app_secret);
      Object.keys(params).forEach(function (k) {
        var v = params[k];
        if (Array.isArray(v)) {
          v.forEach(function (item) { fd.append(k, item); });
        } else {
          fd.append(k, v);
        }
      });
      Object.keys(fileFields).forEach(function (k) { fd.append(k, fileFields[k]); });

      fetch('/docs/_call/', {
        method: 'POST',
        headers: { 'X-CSRFToken': getCsrfToken() }, // Content-Type 由浏览器按 FormData 自动设置
        body: fd
      }).then(parseDone).then(function (data) {
        renderResult(resBox, data);
      }).catch(showErr).finally(function () {
        btn.disabled = false;
        btn.textContent = oldText;
      });
      return;
    }

    var payload = {
      path: path,
      method: method,
      params: params,
      app_id: app_id,
      app_secret: app_secret
    };

    fetch('/docs/_call/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken()
      },
      body: JSON.stringify(payload)
    }).then(parseDone).then(function (data) {
      renderResult(resBox, data);
    }).catch(showErr).finally(function () {
      btn.disabled = false;
      btn.textContent = oldText;
    });
  }

  function renderResult(resBox, data) {
    resBox.innerHTML = '';
    var wrap = el('div', 'rounded-box border border-base-300 bg-base-100 p-3');
    var head = el('div', 'flex flex-wrap items-center gap-2');

    var http = data.http_status || 0;
    var parsed = data.json || null;
    var isOk = http >= 200 && http < 300 && parsed && parsed.code === 10000;
    var statusBadge = el('span', 'badge badge-sm ' + (isOk ? 'badge-success' : 'badge-error'),
      'HTTP ' + http);
    head.appendChild(statusBadge);
    if (data.elapsed_ms !== undefined) {
      head.appendChild(el('span', 'text-xs opacity-60', interpolate(gettext('耗时 %(ms)s ms'), { ms: data.elapsed_ms }, true)));
    }
    if (parsed && typeof parsed.code !== 'undefined') {
      var codeBadge = el('span', 'badge badge-sm ' + (parsed.code === 10000 ? 'badge-soft badge-primary' : 'badge-soft badge-warning'),
        'code=' + parsed.code);
      head.appendChild(codeBadge);
    }
    wrap.appendChild(head);

    if (parsed && parsed.msg) {
      wrap.appendChild(el('p', 'mt-2 text-sm ' + (isOk ? 'text-success' : 'text-error'), parsed.msg));
    }

    var body = parsed ? JSON.stringify(parsed, null, 2) : (data.text || gettext('(空响应)'));
    var pre = el('pre', 'mt-2 max-h-96 overflow-auto rounded-box bg-base-200 p-3 font-mono text-xs');
    pre.textContent = body;
    wrap.appendChild(pre);
    resBox.appendChild(wrap);
  }

  /* 发送 / 清空 */
  document.querySelectorAll('[data-run-endpoint]').forEach(function (btn) {
    btn.addEventListener('click', function () { runEndpoint(btn); });
  });
  document.querySelectorAll('[data-clear-result]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var box = document.getElementById('res-' + btn.dataset.res);
      if (box) { box.classList.add('hidden'); box.innerHTML = ''; }
    });
  });
})();
