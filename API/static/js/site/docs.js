/* API 文档中心交互：线路切换 / 鉴权本机保存 / 在线调试代调 / 响应展示
 * 依赖：页面含 {% csrf_token %}（#docs-auth-form 内）；调试结果由服务端 /docs/_call/ 代调返回。
 * 响应分两种：普通 JSON 一次性渲染；text/event-stream（AI 接口 stream=true）由服务端逐块透传，
 * 这里用 ReadableStream 逐帧读取并逐字打印（见 renderStream）。 */
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

  // 切到指定线路（Tab 高亮 + 面板显隐）：Tab 点击与锚点定位共用
  function activateChannel(slug) {
    var tab = document.querySelector('[data-doc-tab="' + slug + '"]');
    document.querySelectorAll('[data-doc-tab]').forEach(function (b) {
      b.classList.toggle('tab-active', b === tab);
    });
    document.querySelectorAll('[data-channel-panel]').forEach(function (p) {
      p.classList.toggle('hidden', p.dataset.channelPanel !== slug);
    });
  }

  // 滚动到目标节点并短暂高亮，避免长页面里“跳过去也不知道在哪”
  function revealNode(node) {
    node.scrollIntoView({ behavior: 'smooth', block: 'start' });
    node.classList.add('ring-2', 'ring-primary');
    setTimeout(function () { node.classList.remove('ring-2', 'ring-primary'); }, 1600);
  }

  // 依据 URL hash 定位：接口锚点（#ep-<线路>-<端点>）先切线路再滚动；线路锚点（#channel-<线路>）只切线路
  function openByHash() {
    var hash = (location.hash || '').slice(1);
    if (!hash) return;

    var epNode = document.getElementById(hash);
    if (epNode && epNode.dataset.epChannel) {
      activateChannel(epNode.dataset.epChannel);
      setTimeout(function () { revealNode(epNode); }, 60);
      return;
    }

    var m = hash.match(/^channel-(.+)$/);
    if (!m) return;
    var slug = m[1];
    var panel = document.querySelector('[data-channel-panel="' + slug + '"]');
    activateChannel(slug);
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
  openByHash();
  window.addEventListener('hashchange', openByHash);

  /* ---------- 线路 Tab 切换 ---------- */
  document.querySelectorAll('[data-doc-tab]').forEach(function (btn) {
    btn.addEventListener('click', function () { activateChannel(btn.dataset.docTab); });
  });

  /* ---------- 接口目录（右侧栏模块）：搜索 / 按请求方法筛选 / 点击直达详情 ---------- */
  (function initToc() {
    var toc = document.querySelector('[data-doc-toc]');
    if (!toc) return;

    var links = Array.prototype.slice.call(toc.querySelectorAll('[data-toc-link]'));
    var groups = Array.prototype.slice.call(toc.querySelectorAll('[data-toc-group]'));
    var searchBox = toc.querySelector('[data-toc-search]');
    var methodBox = toc.querySelector('[data-toc-methods]');
    var emptyBox = toc.querySelector('[data-toc-empty]');
    var countBox = toc.querySelector('[data-toc-count]');
    var method = '';                           // '' = 不限请求方法

    // 搜索文本预先转小写缓存，避免每次输入都重新解析 DOM
    links.forEach(function (link) {
      link.dataset.tocKey = (link.dataset.tocKey || '').toLowerCase();
    });

    function makeChip(label, value, num) {
      var btn = el('button', 'btn btn-xs');
      btn.type = 'button';
      btn.dataset.tocMethod = value;
      btn.appendChild(document.createTextNode(label));
      btn.appendChild(el('span', 'badge badge-xs', String(num)));
      return btn;
    }

    // 方法筛选按钮按本服务**实际用到**的方法生成（不写死）；只有一种方法时不显示
    var ORDER = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];
    var counts = {};
    links.forEach(function (link) {
      var m = link.dataset.epMethod || '';
      counts[m] = (counts[m] || 0) + 1;
    });
    var methods = Object.keys(counts).sort(function (a, b) {
      var ia = ORDER.indexOf(a), ib = ORDER.indexOf(b);
      if (ia < 0) ia = ORDER.length;
      if (ib < 0) ib = ORDER.length;
      return ia - ib || (a < b ? -1 : 1);
    });

    var chips = [];
    if (methods.length > 1) {
      methodBox.classList.remove('hidden');
      chips.push(makeChip(gettext('全部'), '', links.length));
      methods.forEach(function (m) { chips.push(makeChip(m, m, counts[m])); });
      chips.forEach(function (btn) { methodBox.appendChild(btn); });
    }

    function applyFilter() {
      var q = (searchBox.value || '').trim().toLowerCase();
      var shown = 0;
      links.forEach(function (link) {
        var hit = (!method || link.dataset.epMethod === method)
          && (!q || link.dataset.tocKey.indexOf(q) >= 0);
        link.classList.toggle('hidden', !hit);
        if (hit) shown += 1;
      });
      groups.forEach(function (group) {
        group.classList.toggle('hidden', !group.querySelector('[data-toc-link]:not(.hidden)'));
      });
      emptyBox.classList.toggle('hidden', shown > 0);
      countBox.textContent = interpolate(gettext('显示 %(shown)s / %(total)s 个接口'),
        { shown: shown, total: links.length }, true);
      chips.forEach(function (btn) {
        btn.classList.toggle('btn-active', btn.dataset.tocMethod === method);
      });
    }

    if (chips.length) {
      methodBox.addEventListener('click', function (ev) {
        var btn = ev.target.closest('[data-toc-method]');
        if (!btn) return;
        method = btn.dataset.tocMethod;
        applyFilter();
      });
    }
    searchBox.addEventListener('input', applyFilter);
    searchBox.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Escape') return;
      if (searchBox.value) { searchBox.value = ''; applyFilter(); }
      else { toc.open = false; }
    });

    // 展开时聚焦搜索框；收起时清掉筛选条件，保证下次打开看到的是完整目录
    toc.addEventListener('toggle', function () {
      if (toc.open) {
        setTimeout(function () { searchBox.focus(); }, 50);
      } else {
        searchBox.value = '';
        method = '';
        applyFilter();
      }
    });

    applyFilter();

    // 点击接口直达详情
    links.forEach(function (link) {
      link.addEventListener('click', function (ev) {
        var node = document.getElementById((link.getAttribute('href') || '').slice(1));
        if (!node) return;
        ev.preventDefault();
        // 必须先把目标所在线路切出来：目标还在 display:none 的面板里时，
        // 浏览器对锚点的原生跳转会直接落空（实测跨线路点击不滚动）
        activateChannel(node.dataset.epChannel);
        if (location.hash === '#' + node.id) {
          openByHash();                        // hash 未变化不会触发 hashchange，手动定位
        } else {
          location.hash = node.id;             // 触发 hashchange → openByHash 定位
        }
      });
    });
  })();

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

  /* ---------- 供扩展模块复用：服务端代调（自动补签名） ----------
   * 用法：window.DocsCall(path, method, params) → Promise<{http_status, elapsed_ms, json, text}>
   * 签名参数由服务端 /docs/_call/ 生成，APPID/APPSECRET 取页面鉴权卡片（本机保存值）。 */
  window.DocsCall = function (path, method, params) {
    return fetch('/docs/_call/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken()
      },
      body: JSON.stringify({
        path: path,
        method: method || 'GET',
        params: params || {},
        app_id: (authId ? authId.value.trim() : ''),
        app_secret: (authSecret ? authSecret.value.trim() : '')
      })
    }).then(function (res) { return res.json(); });
  };

  /* ---------- 流式（SSE）响应：逐帧读取并逐字打印 ----------
   * 服务端 /docs/_call/ 对 text/event-stream 是逐块透传的（不再读完再返回），
   * 这里用 ReadableStream 边收边渲染。帧格式：
   *   data: {"reasoning": "…"}  思考过程，仅推理模型有，与答案分开渲染（灰色小字）
   *   data: {"content": "…"}    答案正文
   *   data: {"code": 40001, …}  流开始前出错（如上游 401），只有一帧
   *   data: [DONE]              结束标记 */
  function renderStream(res, resBox) {
    var wrap = el('div', 'rounded-box border border-base-300 bg-base-100 p-3');
    var head = el('div', 'flex flex-wrap items-center gap-2');
    head.appendChild(el('span', 'badge badge-sm ' + (res.ok ? 'badge-success' : 'badge-error'),
      'HTTP ' + res.status));
    var tip = el('span', 'text-xs opacity-60', gettext('流式接收中…'));
    head.appendChild(tip);
    wrap.appendChild(head);
    var think = el('p', 'mt-2 hidden text-xs whitespace-pre-wrap opacity-60');
    var pre = el('pre', 'mt-2 max-h-96 overflow-auto rounded-box bg-base-200 p-3 font-mono text-xs whitespace-pre-wrap');
    wrap.appendChild(think);
    wrap.appendChild(pre);
    resBox.innerHTML = '';
    resBox.appendChild(wrap);

    var answer = '';
    var thinking = '';
    var buf = '';
    var failed = false;

    function applyFrame(frame) {
      frame.split('\n').forEach(function (line) {
        if (line.indexOf('data:') !== 0) return;
        var body = line.slice(5).trim();
        if (!body || body === '[DONE]') return;
        var obj;
        try { obj = JSON.parse(body); } catch (e) { return; }
        if (obj.reasoning) {
          thinking += obj.reasoning;
          think.textContent = thinking;
          think.classList.remove('hidden');
        }
        if (obj.content) {
          answer += obj.content;
          pre.textContent = answer;
        }
        if (obj.code && obj.code !== 10000) {
          failed = true;
          pre.textContent = (answer ? answer + '\n\n' : '') + (obj.msg || gettext('请求失败'));
        }
      });
    }

    // SSE 以空行分帧；\r\n 先归一化，避免分片边界把 \r 与 \n 拆到两次 read
    function drain(final) {
      buf = buf.replace(/\r\n/g, '\n');
      var i;
      while ((i = buf.indexOf('\n\n')) >= 0) {
        applyFrame(buf.slice(0, i));
        buf = buf.slice(i + 2);
      }
      if (final && buf) { applyFrame(buf); buf = ''; }
    }

    function finish() {
      tip.className = 'text-xs ' + (failed ? 'text-error' : 'opacity-60');
      tip.textContent = failed ? gettext('请求失败') : gettext('流式接收完成');
      if (!answer && !thinking && !failed) pre.textContent = gettext('(空响应)');
      document.dispatchEvent(new CustomEvent('docs:result', {
        detail: { resKey: resBox.id.replace(/^res-/, ''), parsed: null, http: res.status }
      }));
    }

    // 老浏览器没有 ReadableStream：退化为一次性读取（仍可用，只是不逐字）
    if (!res.body || !res.body.getReader) {
      return res.text().then(function (text) { buf = text; drain(true); finish(); });
    }
    var reader = res.body.getReader();
    var decoder = new TextDecoder();
    function pump() {
      return reader.read().then(function (r) {
        if (r.done) { drain(true); finish(); return; }
        buf += decoder.decode(r.value, { stream: true });
        drain(false);
        return pump();
      });
    }
    return pump();
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
    }).then(function (res) {
      // 流式端点（AI 接口 stream=true）：服务端逐块透传，这里逐帧渲染、逐字打印
      if ((res.headers.get('content-type') || '').indexOf('text/event-stream') === 0) {
        return renderStream(res, resBox);
      }
      return res.json().then(function (data) { renderResult(resBox, data); });
    }).catch(showErr).finally(function () {
      btn.disabled = false;
      btn.textContent = oldText;
    });
  }

  /* 一行「地址」：标签 + 等宽地址（可选中复制，或直接做成可点击链接）+ 可选的打开按钮。
   * 两种用法：① 二进制响应（面板不回显正文，只给地址）—— 地址当普通文本 +「在新窗口打开」按钮；
   *           ② 响应正文里的播放地址 —— 地址直接做成链接，点一下就开。 */
  function addressRow(label, url, asLink) {
    var row = el('div', 'mt-2 flex flex-wrap items-center gap-2');
    row.appendChild(el('span', 'shrink-0 text-xs font-semibold', label));
    var nodeClass = 'min-w-0 flex-1 break-all font-mono text-xs';
    if (asLink) {
      var link = el('a', nodeClass + ' link link-primary', url);
      link.href = url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      row.appendChild(link);
      return row;
    }
    // 地址本身不做链接：旁边已经有一个「在新窗口打开」按钮，这里负责让人能选中复制
    row.appendChild(el('code', nodeClass + ' rounded-box bg-base-200 px-2 py-1', url));
    var btn = el('a', 'btn btn-outline btn-xs shrink-0', gettext('在新窗口打开'));
    btn.href = url;
    btn.target = '_blank';
    btn.rel = 'noopener noreferrer';
    row.appendChild(btn);
    return row;
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

    // 二进制 / 流式响应（如短剧出流）：正文不回显，就把这条可直接打开的地址给出来
    if (data.open_url) {
      wrap.appendChild(addressRow(gettext('可打开的地址'), data.open_url, false));
      if (data.needs_sign) {
        wrap.appendChild(el('p', 'mt-1 text-xs text-warning',
          gettext('该接口需要项目签名，浏览器直接打开会被拒；上面这条不含签名参数（签名是一次性的，不能复用）。')));
      }
    }

    // 响应正文里的播放地址（与在线播放器同一口径：优先 m3u8，其次 url）直接给成可点击链接
    var playUrl = parsed && parsed.data ? (parsed.data.m3u8 || parsed.data.url) : '';
    if (typeof playUrl === 'string' && /^https?:\/\//i.test(playUrl)) {
      wrap.appendChild(addressRow(gettext('播放地址'), playUrl, true));
      if (parsed.data.ready === false) {
        wrap.appendChild(el('p', 'mt-1 text-xs text-warning',
          gettext('该集地址仍在生成中（首次点播约需数十秒），稍后重新点「发送请求」即可播放。')));
      }
    }

    var body = parsed ? JSON.stringify(parsed, null, 2) : (data.text || gettext('(空响应)'));
    var pre = el('pre', 'mt-2 max-h-96 overflow-auto rounded-box bg-base-200 p-3 font-mono text-xs');
    pre.textContent = body;
    wrap.appendChild(pre);
    resBox.appendChild(wrap);

    // 广播响应结果，供扩展模块消费（如在线播放器自动加载响应中的 m3u8 地址）
    document.dispatchEvent(new CustomEvent('docs:result', {
      detail: { resKey: resBox.id.replace(/^res-/, ''), parsed: parsed, http: http }
    }));
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
