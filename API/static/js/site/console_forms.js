/* 控制台「字典类」表单的共用交互（反馈类型 / 联系方式平台 两页共用）
 *
 * 提供两块能力，都是声明式挂载、无需页面再写胶水代码：
 *
 * 1. XYConsoleForm.open(opts) —— 新增/编辑共用一个 <dialog> 表单的开关与回填
 *    新增时清空表单并按 `<prefix>_create` 提交，编辑时用触发按钮的 data-* 回填并按 `<prefix>_edit` 提交。
 *    opts:
 *      modalId / formId / titleId  三个 DOM id
 *      fields                      参与回填的字段名数组（data-* 的 key = 字段名里的 _ 换成 -）
 *      prefix                      动作前缀，如 'type' / 'platform'
 *      createTitle / editTitle     两种模式下的弹窗标题
 *      source                      触发编辑的那个按钮元素；传 null 即新增
 *      hasDefault                  是否需要处理 is_default（反馈类型专有）
 * 2. 图标集（[data-icon-open] 按钮 + #icon-picker-modal）
 *    点按钮开弹窗：默认列按用途分组的常用图标，点一下即回填并关闭；
 *    在搜索框输英文名，则从全部 lucide 图标里找。填进输入框的是 lucide 官方 kebab 名
 *    （如 message-circle），前台就用它渲染 <i data-lucide="…">。
 *
 * 为什么图标清单要等「点开弹窗」才构建：lucide.min.js 是 defer 加载的，本脚本执行时
 * window.lucide 还不存在（defer 要等 HTML 解析完才跑），此刻构建只会拿到空清单。
 * 用户点是点击后的事，那时图标库早就绪了。
 */
(function () {
  'use strict';

  var _t = window.gettext || function (s) { return s; };
  var _interpolate = window.interpolate || function (s) { return s; };

  /* ==================== 一、新增 / 编辑弹窗 ==================== */

  function setValue(form, name, value) {
    var el = form.querySelector('[name="' + name + '"]');
    if (!el) { return; }
    if (el.type === 'checkbox') { el.checked = value === '1'; }
    else { el.value = value || ''; }
  }

  function openForm(opts) {
    var modal = document.getElementById(opts.modalId);
    var form = document.getElementById(opts.formId);
    if (!modal || !form) { return; }
    var source = opts.source || null;
    var isEdit = !!source;

    form.querySelector('[name="action"]').value = opts.prefix + (isEdit ? '_edit' : '_create');
    form.querySelector('[name="id"]').value = isEdit ? (source.dataset.id || '') : '';
    document.getElementById(opts.titleId).textContent = isEdit ? opts.editTitle : opts.createTitle;

    (opts.fields || []).forEach(function (name) {
      // 模板里的属性写成 data-xxx-yyy（下划线换成短横线）。这里用 getAttribute 而不是
      // dataset[key]，是因为 dataset 的 key 是 camelCase（data-value-label → valueLabel），
      // 直接拿短横线形式去取 dataset 会永远拿到 undefined、编辑时静默回填成空。
      var attr = 'data-' + name.replace(/_/g, '-');
      var value = isEdit ? (source.getAttribute(attr) || '') : (name === 'sort' ? '0' : '');
      setValue(form, name, value);
    });
    setValue(form, 'enabled', isEdit ? source.dataset.enabled : '1');
    if (opts.hasDefault) { setValue(form, 'is_default', isEdit ? source.dataset.default : ''); }

    // 图标预览跟着输入框里的值走：新增时清空，编辑时显示已存的图标
    form.querySelectorAll('[data-icon-open]').forEach(function (btn) {
      refreshIconPreview(btn.parentNode.querySelector('input[name="icon"]'));
    });
    modal.showModal();
  }

  window.XYConsoleForm = { open: openForm };

  /* 「取消」等按钮：给按钮 data-modal-close="<dialogId>" 即可 */
  document.querySelectorAll('[data-modal-close]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var modal = document.getElementById(btn.dataset.modalClose);
      if (modal) { modal.close(); }
    });
  });

  /* ==================== 二、图标集 ==================== */

  var ICON_MODAL = document.getElementById('icon-picker-modal');
  if (!ICON_MODAL) { return; }            // 本页没有图标集就不往下走

  var ICON_GRID = document.getElementById('icon-picker-grid');
  var ICON_EMPTY = document.getElementById('icon-picker-empty');
  var ICON_SEARCH = document.getElementById('icon-picker-search');
  var ICON_SEARCH_LIMIT = 240;            // 搜索结果最多画多少个：一次铺几千个 DOM 会让弹窗卡住
  var ALL_ICONS = null;                   // 全部 lucide 图标名（kebab），首次开弹窗时构建
  var iconTarget = null;                  // 当前正在选图标的那个输入框

  var CURATED = [
    [_t('反馈类型'), [
      ['lightbulb', _t('功能建议')], ['sparkles', _t('优化升级')], ['circle-help', _t('使用求助')],
      ['bug', _t('故障 BUG')], ['message-square', _t('留言建议')], ['flag', _t('举报投诉')],
      ['shield-alert', _t('安全违规')], ['triangle-alert', _t('异常警告')], ['circle-x', _t('无法复现')],
      ['clock', _t('等待处理')], ['star', _t('体验评价')], ['trash-2', _t('无效内容')]
    ]],
    [_t('联系方式'), [
      ['send', _t('发送 / Telegram')], ['message-circle', _t('聊天 / 微信')], ['mail', _t('邮箱')],
      ['at-sign', _t('邮箱地址')], ['phone', _t('电话')], ['globe', _t('网站')],
      ['megaphone', _t('公告')], ['headphones', _t('在线客服')], ['users', _t('社群')],
      ['bot', _t('机器人')], ['link', _t('链接')], ['qr-code', _t('二维码')]
    ]],
    [_t('常用'), [
      ['check', _t('完成')], ['info', _t('说明')], ['bell', _t('通知')],
      ['user', _t('用户')], ['settings', _t('设置')], ['gift', _t('活动福利')],
      ['crown', _t('会员')], ['zap', _t('性能')], ['chart-bar', _t('数据统计')],
      ['heart', _t('点赞')], ['thumbs-up', _t('赞成')], ['thumbs-down', _t('反对')]
    ]]
  ];

  /* PascalCase → lucide 官方 kebab 名：
     MessageCircle → message-circle、AArrowDown → a-arrow-down、ArrowDown01 → arrow-down-01 */
  function iconKebab(name) {
    return name.replace(/([a-z0-9])([A-Z])/g, '$1-$2')
      .replace(/([A-Z])([A-Z][a-z])/g, '$1-$2')
      .replace(/([a-zA-Z])(\d)/g, '$1-$2')
      .toLowerCase();
  }

  function allIcons() {
    if (ALL_ICONS && ALL_ICONS.length) { return ALL_ICONS; }
    var names = Object.keys((window.lucide && window.lucide.icons) || {}).map(iconKebab).sort();
    if (names.length) { ALL_ICONS = names; }   // 图标库还没就绪就先别缓存，下次再取
    return names;
  }

  /* 输入框旁的小预览。只认 lucide 里确实存在的名字 —— 否则用户打错一个字母，
     createIcons 会在控制台刷一条警告，页面看起来像出了故障。 */
  function refreshIconPreview(input) {
    if (!input) { return; }
    var holder = input.parentNode.querySelector('[data-icon-preview]');
    if (!holder || holder.dataset.name === input.value) { return; }
    holder.dataset.name = input.value;
    holder.textContent = '';
    var name = (input.value || '').trim().toLowerCase();
    if (!name || !window.lucide || allIcons().indexOf(name) < 0) { return; }
    var el = document.createElement('i');
    el.setAttribute('data-lucide', name);
    el.className = 'h-4 w-4';
    holder.appendChild(el);
    window.lucide.createIcons();
  }

  function iconCell(name, label) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.title = name;
    btn.setAttribute('data-icon-name', name);
    btn.className = 'flex flex-col items-center gap-1 rounded-box border border-base-300 p-2 hover:border-primary hover:bg-primary/10';
    var el = document.createElement('i');
    el.setAttribute('data-lucide', name);
    el.className = 'h-5 w-5';
    var txt = document.createElement('span');
    txt.className = 'w-full truncate text-center text-[0.65rem] leading-tight opacity-60';
    txt.textContent = label || name;
    btn.appendChild(el);
    btn.appendChild(txt);
    return btn;
  }

  function renderIconGrid() {
    var q = (ICON_SEARCH.value || '').trim().toLowerCase();
    var groups, tip = '';
    if (q) {
      var hits = allIcons().filter(function (n) { return n.indexOf(q) >= 0; });
      groups = [['', hits.slice(0, ICON_SEARCH_LIMIT).map(function (n) { return [n, n]; })]];
      if (hits.length > ICON_SEARCH_LIMIT) {
        tip = _interpolate(_t('匹配 %(n)s 个，只显示前 %(limit)s 个，再输几个字母缩小范围。'),
          { n: hits.length, limit: ICON_SEARCH_LIMIT }, true);
      }
    } else {
      groups = CURATED;
    }

    var total = 0;
    ICON_GRID.textContent = '';
    groups.forEach(function (group) {
      if (group[0]) {
        var title = document.createElement('p');
        title.className = 'mb-2 text-xs font-semibold text-base-content/60';
        title.textContent = group[0];
        ICON_GRID.appendChild(title);
      }
      var wrap = document.createElement('div');
      wrap.className = 'mb-3 grid grid-cols-4 gap-2 sm:grid-cols-6 lg:grid-cols-8';
      group[1].forEach(function (item) {
        wrap.appendChild(iconCell(item[0], item[1]));
        total++;
      });
      ICON_GRID.appendChild(wrap);
    });
    if (tip) {
      var note = document.createElement('p');
      note.className = 'mt-1 text-center text-xs text-base-content/50';
      note.textContent = tip;
      ICON_GRID.appendChild(note);
    }
    ICON_EMPTY.classList.toggle('hidden', total > 0);
    if (window.lucide) { window.lucide.createIcons(); }
  }

  function openIconPicker(input) {
    iconTarget = input;
    ICON_SEARCH.value = '';
    renderIconGrid();
    ICON_MODAL.showModal();
    ICON_SEARCH.focus();
  }

  ICON_GRID.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-icon-name]');
    if (!btn || !iconTarget) { return; }
    iconTarget.value = btn.getAttribute('data-icon-name');
    refreshIconPreview(iconTarget);
    ICON_MODAL.close();
  });

  // 搜索时防抖：每敲一个字就重画 200+ 个图标会顿
  var iconSearchTimer = null;
  ICON_SEARCH.addEventListener('input', function () {
    clearTimeout(iconSearchTimer);
    iconSearchTimer = setTimeout(renderIconGrid, 120);
  });

  var clearBtn = document.getElementById('icon-picker-clear');
  if (clearBtn) {
    clearBtn.addEventListener('click', function () {
      if (iconTarget) {
        iconTarget.value = '';
        refreshIconPreview(iconTarget);
      }
      ICON_MODAL.close();
    });
  }

  document.querySelectorAll('[data-icon-open]').forEach(function (btn) {
    var input = btn.parentNode.querySelector('input[name="icon"]');
    if (!input) { return; }
    btn.addEventListener('click', function () { openIconPicker(input); });
    input.addEventListener('input', function () { refreshIconPreview(input); });
  });
})();
