/* 代练丸子「发布订单」面板：游戏 / 大区 / 代练类型 / 任务字段 联动选择，免填 JSON。
 *
 * 选项实时来自 /docs/_dlwz_games/ 与 /docs/_dlwz_options/（服务端用托管账号代为拉取上游）；
 * 选好后把 game_id / region_name / leveling_type_name / tasks 写进同名字段，
 * 由 docs.js 的在线调试原样提交。任务字段按「服务端预设」预填，做到进来就是对的。
 */
(function () {
  'use strict';

  var panels = document.querySelectorAll('[data-dlwz-publish]');
  if (!panels.length) return;

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function getJSON(url) {
    return fetch(url, {headers: {'X-Requested-With': 'XMLHttpRequest'}})
      .then(function (r) { return r.json(); });
  }

  /* 填下拉：优先选中 prefer（预设值）；没有预设且**没有占位项**时取第一项；
     有占位项（如「请选择」）且无预设时保持占位——可选字段就该是「不填」。 */
  function fillSelect(select, items, placeholder, prefer) {
    select.innerHTML = '';
    if (placeholder) {
      var ph = el('option', null, placeholder);
      ph.value = '';
      select.appendChild(ph);
    }
    (items || []).forEach(function (it) {
      var opt = el('option', null, it.label);
      opt.value = it.value;
      select.appendChild(opt);
    });
    var target = '';
    if (prefer !== undefined && prefer !== null && prefer !== '') {
      for (var i = 0; i < select.options.length; i++) {
        if (String(select.options[i].value) === String(prefer)) { target = String(prefer); break; }
      }
    }
    if (target === '' && !placeholder && items && items.length) target = String(items[0].value);
    select.value = target;
  }

  function buildPanel(panel) {
    var gamesUrl = panel.dataset.gamesUrl;
    var optionsUrl = panel.dataset.optionsUrl;
    var gameSel = panel.querySelector('[data-dlwz-game]');
    var regionSel = panel.querySelector('[data-dlwz-region]');
    var typeSel = panel.querySelector('[data-dlwz-type]');
    var fieldsBox = panel.querySelector('[data-dlwz-fields]');
    var tasksInput = panel.querySelector('[data-dlwz-tasks]');
    var status = panel.querySelector('[data-dlwz-status]');

    var presets = [];
    try { presets = JSON.parse(panel.dataset.presets || '[]') || []; } catch (e) { presets = []; }

    var IDLE_TIP = gettext('选好游戏 / 大区 / 代练类型，下方的任务字段会跟着变；无需手写 JSON。');
    var typeIds = {};      // 代练类型名 -> id（拉字段时要用 id）
    var presetTasks = {};  // 任务字段名 -> 预设取值（用于预填）

    function presetOf(gameId) {
      var hit = null;
      presets.some(function (p) { if (String(p.game_id) === String(gameId)) { hit = p; return true; } return false; });
      return hit;
    }

    function setStatus(text) { if (status) status.textContent = text; }

    /* 把当前字段取值序列化成 tasks（JSON），写进隐藏字段 */
    function buildTasks() {
      var specs = [];
      fieldsBox.querySelectorAll('[data-dlwz-field]').forEach(function (box) {
        var type = box.dataset.dlwzType;
        var spec = {name: box.dataset.dlwzField};
        if (type === '6') {
          var s = box.querySelector('[data-dlwz-start]');
          var e = box.querySelector('[data-dlwz-end]');
          if (!s || !e || !s.value || !e.value) return;
          spec.start = s.value;
          spec.end = e.value;
        } else if (type === '5') {
          var num = box.querySelector('[data-dlwz-num]');
          if (!num || num.value === '') return;
          spec.value = Number(num.value);
        } else if (type === '1' || type === '2') {
          var sel = box.querySelector('[data-dlwz-select]');
          if (!sel || !sel.value) return;
          spec.value = sel.value;
        } else {
          return;   // 暂不支持的字段类型不提交
        }
        specs.push(spec);
      });
      tasksInput.value = specs.length ? JSON.stringify(specs) : '';
    }

    function renderFields(list) {
      fieldsBox.innerHTML = '';
      (list || []).forEach(function (f) {
        var type = String(f.type);
        var preset = presetTasks[f.name] || {};
        var box = el('div', 'sm:col-span-2');
        box.dataset.dlwzField = f.name;
        box.dataset.dlwzType = type;
        box.appendChild(el('label', 'fieldset-label', f.name + (f.is_must ? ' *' : '')));

        if (type === '6') {
          var levels = (f.levels || []).map(function (l) { return {value: l.name, label: l.name}; });
          var wrap = el('div', 'flex flex-wrap items-center gap-2');
          var start = el('select', 'select select-bordered select-sm min-w-0 flex-1 text-sm');
          start.setAttribute('data-dlwz-start', '');
          fillSelect(start, levels, gettext('起始段位'), preset.start);
          var end = el('select', 'select select-bordered select-sm min-w-0 flex-1 text-sm');
          end.setAttribute('data-dlwz-end', '');
          fillSelect(end, levels, gettext('目标段位'), preset.end);
          start.addEventListener('change', buildTasks);
          end.addEventListener('change', buildTasks);
          wrap.appendChild(start);
          wrap.appendChild(end);
          box.appendChild(wrap);
        } else if (type === '5') {
          var num = el('input', 'input input-bordered input-sm w-full text-sm');
          num.type = 'number';
          num.placeholder = gettext('请输入数字');
          if (f.min_val !== undefined && f.min_val !== null) num.min = f.min_val;
          if (f.max_val !== undefined && f.max_val !== null) num.max = f.max_val;
          if (preset.value !== undefined && preset.value !== null) num.value = preset.value;
          num.setAttribute('data-dlwz-num', '');
          num.addEventListener('input', buildTasks);
          box.appendChild(num);
        } else if (type === '1' || type === '2') {
          var sel = el('select', 'select select-bordered select-sm w-full text-sm');
          sel.setAttribute('data-dlwz-select', '');
          fillSelect(sel, (f.options || []).map(function (o) { return {value: o.name, label: o.name}; }),
                     gettext('请选择'), preset.value);
          sel.addEventListener('change', buildTasks);
          box.appendChild(sel);
        } else {
          return;   // 未支持的字段类型（如指定英雄 / 胜率）先不渲染
        }
        fieldsBox.appendChild(box);
      });
      buildTasks();
    }

    function loadFields() {
      var gameId = gameSel.value;
      var typeId = typeIds[typeSel.value] || '';
      if (!gameId || !typeId) { renderFields([]); return; }
      setStatus(gettext('加载中…'));
      getJSON(optionsUrl + '?game_id=' + encodeURIComponent(gameId)
              + '&leveling_type_id=' + encodeURIComponent(typeId))
        .then(function (res) {
          renderFields((((res || {}).data || {}).fields) || []);
          setStatus(IDLE_TIP);
        })
        .catch(function () { renderFields([]); setStatus(gettext('加载失败，请重试')); });
    }

    function loadOptions() {
      var gameId = gameSel.value;
      if (!gameId) { fillSelect(regionSel, [], ''); fillSelect(typeSel, [], ''); renderFields([]); return; }
      setStatus(gettext('加载中…'));
      getJSON(optionsUrl + '?game_id=' + encodeURIComponent(gameId))
        .then(function (res) {
          var data = (res || {}).data || {};
          var preset = presetOf(gameId) || {};
          presetTasks = {};
          (preset.tasks || []).forEach(function (t) { presetTasks[t.name] = t; });

          fillSelect(regionSel, (data.regions || []).map(function (r) {
            return {value: r.region_name, label: r.region_name};
          }), '', preset.region);
          typeIds = {};
          fillSelect(typeSel, (data.leveling_types || []).map(function (t) {
            typeIds[t.leveling_type_name] = t.leveling_type_id;
            return {value: t.leveling_type_name, label: t.leveling_type_name};
          }), '', preset.type);
          setStatus(IDLE_TIP);
          loadFields();
        })
        .catch(function () { setStatus(gettext('加载失败，请重试')); });
    }

    function loadGames() {
      setStatus(gettext('加载中…'));
      getJSON(gamesUrl)
        .then(function (res) {
          var items = (((res || {}).data) || []).map(function (g) {
            return {value: g.game_id, label: g.game_name};
          });
          if (!items.length) { setStatus(gettext('加载失败，请重试')); return; }
          fillSelect(gameSel, items, '', (presets[0] || {}).game_id);
          loadOptions();
        })
        .catch(function () { setStatus(gettext('加载失败，请重试')); });
    }

    gameSel.addEventListener('change', loadOptions);
    typeSel.addEventListener('change', loadFields);
    loadGames();
  }

  panels.forEach(buildPanel);
})();
