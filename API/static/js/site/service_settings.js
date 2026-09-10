/* 服务设置弹窗（全局，随 base 模板加载）
 *
 * 交互结构（两级，便于后续扩展）：
 *  1. 功能主页：列出该服务可设置的功能入口（后端 sections 自动生成入口卡片）；
 *  2. 功能详情：点某个入口后进入对应设置界面，可“返回全部功能”。
 *
 * 地基设计：
 *  - 后端 console.services_api：GET ?url_prefix= 返回该服务全部“设置分组”sections
 *    （每个分组：id / icon / title / desc / <同 id 的载荷字段>）；
 *  - 本文件维护分组渲染注册表 SECTIONS：{id: renderer(bodyEl, payload, ctx)}；
 *  - 以后新增设置：后端 sections 追加一个分组，前端 register() 登记同名渲染器，
 *    功能主页会自动出现新入口，无需改动其它代码。
 */
(function () {
  'use strict';

  var API_URL = '/console/services/api/';
  var CSRF_RE = /(?:^|;\s*)(?:xyapi_csrftoken|csrftoken)=([^;\s]+)/;

  var dialog = document.getElementById('service-settings-modal');
  var titleEl = document.getElementById('service-settings-title');
  var subEl = document.getElementById('service-settings-sub');
  var alertEl = document.getElementById('service-settings-alert');
  var bodyEl = document.getElementById('service-settings-body');

  var state = { prefix: '', name: '', data: null };

  /* ---------------- 分组渲染注册表（地基入口） ---------------- */
  var SECTIONS = {};
  function register(id, renderer) {
    SECTIONS[id] = renderer;
  }

  /* ---------------- 通用工具 ---------------- */
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function getCsrfToken() {
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input && input.value) return input.value;
    var m = document.cookie.match(CSRF_RE);
    return m ? m[1] : '';
  }

  /* 统一把响应解析成 {code,msg,data}（含 302 登录跳转 / 非 JSON / 断网兜底） */
  function parseResponse(res) {
    if (res.redirected) {
      return Promise.resolve({ code: -1, msg: gettext('管理员登录状态已失效，请重新登录'), data: null });
    }
    return res.text().then(function (text) {
      var payload = null;
      try { payload = JSON.parse(text); } catch (e) { payload = null; }
      if (payload && typeof payload.code !== 'undefined') return payload;
      return {
        code: -1,
        msg: res.status === 403
          ? gettext('安全校验失败，请刷新页面后重试')
          : interpolate(gettext('请求失败（HTTP %(status)s），请稍后重试'), { status: res.status || gettext('未知') }, true),
        data: null
      };
    });
  }

  function apiGet(params) {
    var qs = Object.keys(params).map(function (k) {
      return encodeURIComponent(k) + '=' + encodeURIComponent(params[k] || '');
    }).join('&');
    return fetch(API_URL + '?' + qs, { credentials: 'same-origin' })
      .then(parseResponse)
      .catch(function () {
        return { code: -1, msg: gettext('网络异常，请检查网络后重试'), data: null };
      });
  }

  function apiPost(data) {
    if (!getCsrfToken()) {
      return Promise.resolve({ code: -1, msg: gettext('页面安全校验信息缺失，请刷新页面后重试'), data: null });
    }
    var body = new URLSearchParams();
    Object.keys(data).forEach(function (k) {
      if (data[k] !== undefined && data[k] !== null && data[k] !== '') body.append(k, data[k]);
    });
    return fetch(API_URL, {
      method: 'POST',
      headers: {
        'X-CSRFToken': getCsrfToken(),
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'
      },
      body: body.toString(),
      credentials: 'same-origin'
    }).then(parseResponse).catch(function () {
      return { code: -1, msg: gettext('网络异常，请检查网络后重试'), data: null };
    });
  }

  /* 刷新 lucide 图标（动态插入的内容需重新渲染） */
  function refreshIcons() {
    if (window.lucide && lucide.createIcons) lucide.createIcons();
  }

  /* ---------------- 弹窗通用状态 ---------------- */
  function showGlobalAlert(type, text) {
    if (!alertEl) return;
    alertEl.classList.remove('hidden', 'alert-success', 'alert-error', 'alert-info');
    if (type) alertEl.classList.add(type === 'success' ? 'alert-success' : (type === 'error' ? 'alert-error' : 'alert-info'));
    alertEl.textContent = text || '';
  }

  function hideGlobalAlert() {
    if (alertEl) alertEl.classList.add('hidden');
  }

  function setHeader(name, prefix) {
    if (titleEl) titleEl.textContent = name;
    if (subEl) subEl.textContent = prefix;
  }

  function setBusy(btn, busy, busyText) {
    if (!btn) return;
    if (busy) {
      btn.dataset.originalText = btn.textContent;
      btn.textContent = busyText || gettext('请稍候…');
      btn.disabled = true;
      btn.classList.add('btn-disabled');
    } else {
      btn.textContent = btn.dataset.originalText || btn.textContent;
      btn.disabled = false;
      btn.classList.remove('btn-disabled');
    }
  }

  /* ---------------- 打开弹窗：拉取数据并展示“功能主页” ---------------- */
  function openSettings(prefix, name) {
    if (!dialog || !prefix) return;
    state.prefix = prefix;
    state.name = name || '';
    state.data = null;
    setHeader(state.name, prefix);
    hideGlobalAlert();
    if (bodyEl) {
      bodyEl.innerHTML = '';
      bodyEl.appendChild(el('p', 'py-2 text-sm text-base-content/60', gettext('加载设置中…')));
    }
    dialog.showModal();

    apiGet({ url_prefix: prefix }).then(function (res) {
      if (res.code !== 10000) {
        if (bodyEl) bodyEl.innerHTML = '';
        showGlobalAlert('error', res.msg || gettext('加载失败，请稍后重试'));
        return;
      }
      state.data = res.data || {};
      renderHome();
    });
  }

  function currentSections() {
    return (state.data && state.data.sections) || [];
  }

  /* ---------------- 视图 1：功能主页（入口列表） ---------------- */
  function renderHome() {
    if (!bodyEl) return;
    bodyEl.innerHTML = '';
    var sections = currentSections();

    var hint = el('p', 'text-xs text-base-content/60', gettext('选择要设置的功能：'));
    bodyEl.appendChild(hint);

    if (!sections.length) {
      bodyEl.appendChild(el('p', 'py-2 text-sm text-base-content/60', gettext('该服务暂无可用设置项。')));
      return;
    }

    var list = el('div', 'mt-2 space-y-2');
    sections.forEach(function (sec) {
      var payload = sec[sec.id] || {};
      var card = el('button', 'group flex w-full items-center gap-3 rounded-box border border-base-300 bg-base-100 p-3 text-left transition-colors hover:border-primary/40 hover:bg-base-200/60');
      card.type = 'button';

      var iconBox = el('span', 'flex h-9 w-9 shrink-0 items-center justify-center rounded-box bg-base-200 text-base-content/70');
      iconBox.appendChild(el('i', 'h-4 w-4', null));
      iconBox.lastChild.setAttribute('data-lucide', sec.icon || 'settings');
      card.appendChild(iconBox);

      var info = el('span', 'flex min-w-0 flex-1 flex-col gap-0.5');
      var titleRow = el('span', 'flex flex-wrap items-center gap-2 text-sm font-semibold');
      titleRow.appendChild(el('span', '', sec.title || sec.id));
      // 若该分组带“当前状态”摘要，在入口右侧展示（仅展示，不做别的）
      if (payload.current_label && payload.current_badge) {
        titleRow.appendChild(el('span', 'badge ' + payload.current_badge + ' badge-xs', payload.current_label));
      }
      info.appendChild(titleRow);
      if (sec.desc) info.appendChild(el('span', 'text-xs leading-relaxed text-base-content/60', sec.desc));
      card.appendChild(info);

      var chevron = el('i', 'h-4 w-4 shrink-0 text-base-content/30 transition-colors group-hover:text-base-content/60', null);
      chevron.setAttribute('data-lucide', 'chevron-right');
      card.appendChild(chevron);

      card.addEventListener('click', function () { renderDetail(sec); });
      list.appendChild(card);
    });
    bodyEl.appendChild(list);
    refreshIcons();
  }

  /* ---------------- 视图 2：功能详情（渲染注册表对应的分组内容） ---------------- */
  function renderDetail(sec) {
    if (!bodyEl) return;
    hideGlobalAlert();
    bodyEl.innerHTML = '';

    // 顶部：返回 + 功能名
    var nav = el('div', 'flex items-center gap-2 border-b border-base-300 pb-3');
    var backBtn = el('button', 'btn btn-ghost btn-xs gap-1', null);
    backBtn.type = 'button';
    var backIcon = el('i', 'h-3.5 w-3.5', null);
    backIcon.setAttribute('data-lucide', 'arrow-left');
    backBtn.appendChild(backIcon);
    backBtn.appendChild(document.createTextNode(gettext('全部设置')));
    backBtn.addEventListener('click', renderHome);
    nav.appendChild(backBtn);
    nav.appendChild(el('span', 'text-xs text-base-content/40', '/'));
    nav.appendChild(el('span', 'text-sm font-semibold', sec.title || sec.id));
    bodyEl.appendChild(nav);

    if (sec.desc) {
      bodyEl.appendChild(el('p', 'mt-3 text-xs leading-relaxed text-base-content/60', sec.desc));
    }

    var renderer = SECTIONS[sec.id];
    var content = el('div', 'mt-3 rounded-box border border-base-300 bg-base-100 p-4');
    if (renderer) {
      try {
        renderer(content, sec[sec.id] || {});
      } catch (e) {
        content.appendChild(el('p', 'text-xs text-error', interpolate(gettext('该设置功能渲染失败：%(error)s'), { error: e.message }, true)));
      }
    } else {
      content.appendChild(el('p', 'text-xs text-base-content/50', gettext('该设置功能暂未实现渲染。')));
    }
    bodyEl.appendChild(content);
    refreshIcons();
  }

  /* ============================================================
   * 设置分组：API 服务状态（status）
   * ============================================================ */
  register('status', function (box, payload) {
    if (!payload || !payload.options) {
      box.appendChild(el('p', 'text-xs text-error', gettext('服务状态数据缺失')));
      return;
    }
    var isManual = !!payload.manual;

    /* 当前状态摘要 */
    var summary = el('div', 'flex flex-wrap items-center gap-2 text-xs');
    summary.appendChild(el('span', 'text-base-content/70', gettext('当前状态：')));
    summary.appendChild(el('span', 'badge ' + payload.current_badge + ' badge-sm', payload.current_label));
    summary.appendChild(el('span', 'badge ' + (isManual ? 'badge-soft badge-warning' : 'badge-ghost') + ' badge-sm',
      isManual ? gettext('手动指定') : gettext('默认')));
    summary.appendChild(el('span', 'text-base-content/50', interpolate(gettext('默认：%(label)s'), { label: payload.default_label }, true)));
    box.appendChild(summary);

    /* 状态单选项 */
    var list = el('div', 'mt-3 space-y-1.5');
    payload.options.forEach(function (opt) {
      var label = el('label', 'flex cursor-pointer items-start gap-2 rounded-box border border-base-300 p-2 text-sm hover:bg-base-200/50');
      var radio = el('input', 'radio radio-sm mt-0.5');
      radio.type = 'radio';
      radio.name = 'svc-settings-status';
      radio.value = opt.key;
      if (opt.key === payload.current) radio.checked = true;
      var info = el('span', 'flex min-w-0 flex-1 flex-col gap-1');
      info.appendChild(el('span', 'badge w-fit ' + opt.badge + ' badge-sm', opt.label));
      info.appendChild(el('span', 'text-xs text-base-content/60', opt.desc));
      label.appendChild(radio);
      label.appendChild(info);
      list.appendChild(label);
    });
    box.appendChild(list);

    /* 操作区 */
    var actions = el('div', 'mt-3 flex flex-wrap items-center gap-2');
    var saveBtn = el('button', 'btn btn-primary btn-sm', gettext('保存状态'));
    saveBtn.type = 'button';
    actions.appendChild(saveBtn);

    var resetBtn = null;
    if (isManual) {
      resetBtn = el('button', 'btn btn-outline btn-error btn-sm', gettext('恢复默认'));
      resetBtn.type = 'button';
      actions.appendChild(resetBtn);
    }
    box.appendChild(actions);

    var tip = el('p', 'mt-2 text-xs text-base-content/50',
      isManual ? gettext('恢复默认后，将按“已接入文档=开放 / 未接入文档=建设中”自动派生。') : gettext('保存成功后页面自动刷新生效。'));
    box.appendChild(tip);

    function checkedValue() {
      var checked = box.querySelector('input[name="svc-settings-status"]:checked');
      return checked ? checked.value : '';
    }

    saveBtn.addEventListener('click', function () {
      var value = checkedValue();
      if (!value) return;
      setBusy(saveBtn, true, gettext('保存中…'));
      apiPost({ action: 'set_status', url_prefix: state.prefix, status: value }).then(function (res) {
        setBusy(saveBtn, false);
        if (res.code !== 10000) {
          tip.textContent = res.msg || gettext('保存失败，请稍后重试');
          tip.className = 'mt-2 text-xs text-error';
          return;
        }
        tip.textContent = res.msg || gettext('已保存');
        tip.className = 'mt-2 text-xs text-success';
        setTimeout(function () { location.reload(); }, 800);
      });
    });

    if (resetBtn) {
      resetBtn.addEventListener('click', function () {
        window.XYConfirm(interpolate(gettext('确认恢复「%(name)s」为默认状态？'), { name: state.name || gettext('该服务') }, true), {
          title: gettext('恢复默认状态'),
          confirmText: gettext('恢复默认'),
          danger: true,
        }).then(function (ok) {
          if (!ok) return;
          setBusy(resetBtn, true, gettext('恢复中…'));
          apiPost({ action: 'reset_status', url_prefix: state.prefix }).then(function (res) {
            setBusy(resetBtn, false);
            if (res.code !== 10000) {
              tip.textContent = res.msg || gettext('操作失败，请稍后重试');
              tip.className = 'mt-2 text-xs text-error';
              return;
            }
            tip.textContent = res.msg || gettext('已恢复默认');
            tip.className = 'mt-2 text-xs text-success';
            setTimeout(function () { location.reload(); }, 800);
          });
        });
      });
    }
  });

  /* ---------------- 事件绑定 ---------------- */
  document.querySelectorAll('[data-open-service-settings]').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      // 齿轮可能位于 details/summary 内，阻止它触发菜单展开/折叠
      e.preventDefault();
      e.stopPropagation();
      openSettings(btn.dataset.prefix, btn.dataset.name);
    });
  });

  /* 静态图标初始渲染（齿轮 / 关闭按钮等） */
  refreshIcons();
})();
