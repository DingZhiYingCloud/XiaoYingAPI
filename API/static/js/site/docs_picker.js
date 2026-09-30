/* 文档页「参数选择器」：账号选择器（搜库内账号）+ 礼物面板（看图挑礼物）
 *
 * 两个面板都由端点的文档声明触发，脚本只负责渲染与回填：
 * - 账号选择器：服务声明了 account_search_path、且本端点带 account_id 参数时，模板会渲染
 *   [data-account-picker] 面板；这里负责搜库内账号 → 点一条 → 把 account_id / user_id 填进表单。
 * - 礼物面板：端点声明了 gift_picker_path 时渲染 [data-gift-picker]；这里负责按金币 / 钻石
 *   拉礼物列表（带图片与价格）→ 点一个 → 把 item_id 填进表单。
 *
 * 依赖：window.DocsCall（docs.js 提供，负责服务端代签转发）。 */
(function () {
  'use strict';

  // Django i18n 的全局函数（脚本加载顺序异常时退化为原文）
  function _t(s) { return (typeof gettext === 'function') ? gettext(s) : s; }
  function _ti(s, ctx) { return (typeof interpolate === 'function') ? interpolate(s, ctx, true) : s; }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function setStatus(node, text, isError) {
    if (!node) return;
    node.textContent = text || '';
    node.classList.toggle('text-error', !!isError);
  }

  // 调文档声明的数据接口，返回 data（失败时把 msg 抛出去，便于面板显示原因）
  function fetchData(path, params) {
    return window.DocsCall(path, 'GET', params || {}).then(function (res) {
      var body = res && res.json;
      if (!body || body.code !== 10000) {
        throw new Error((body && body.msg) || ('HTTP ' + (res && res.http_status)));
      }
      return body.data || {};
    });
  }

  /* ---------- 账号选择器：搜库内账号 → 回填 account_id / user_id ---------- */
  document.querySelectorAll('[data-account-picker]').forEach(function (panel) {
    var card = panel.closest('article');
    var endpoint = panel.dataset.pickerEndpoint;
    var keywordBox = panel.querySelector('[data-picker-keyword]');
    var listBox = panel.querySelector('[data-picker-list]');
    var statusBox = panel.querySelector('[data-picker-status]');

    function fill(item) {
      var filled = [];
      ['account_id', 'user_id'].forEach(function (name) {
        var field = card.querySelector('[data-param-name="' + name + '"]');
        if (field && item[name]) {
          field.value = item[name];
          filled.push(name);
        }
      });
      setStatus(statusBox, filled.length
        ? _ti('已填入 %(fields)s：%(user)s（%(id)s）',
              { fields: filled.join(' + '), user: item.username, id: item.user_id })
        : _t('该端点没有可自动填入的参数字段'), !filled.length);
    }

    function row(item) {
      var btn = el('button', 'flex w-full items-center gap-2 rounded-box border border-base-300 bg-base-100 px-2 py-1 text-left hover:border-primary');
      btn.type = 'button';
      btn.appendChild(el('span', 'badge badge-ghost badge-xs shrink-0', item.has_token ? _t('有 token') : _t('无 token')));
      var body = el('span', 'min-w-0 flex-1');
      body.appendChild(el('span', 'block truncate text-sm', item.username + ' · ' + item.user_id));
      var sub = [item.nickname, item.remark].filter(Boolean).join(' · ');
      body.appendChild(el('span', 'block truncate text-xs text-base-content/60', sub || _t('（无昵称 / 备注）')));
      btn.appendChild(body);
      btn.addEventListener('click', function () { fill(item); });
      return btn;
    }

    function search() {
      setStatus(statusBox, _t('查询中…'));
      listBox.innerHTML = '';
      fetchData(endpoint, { keyword: keywordBox.value.trim(), page: '1', page_size: '10' })
        .then(function (data) {
          var items = data.items || [];
          if (!items.length) {
            setStatus(statusBox, _t('没有匹配的账号'), true);
            return;
          }
          setStatus(statusBox, _ti('共 %(n)s 条，点一条即填入参数', { n: data.total }));
          items.forEach(function (item) { listBox.appendChild(row(item)); });
        })
        .catch(function (err) { setStatus(statusBox, _t('查询失败：') + err.message, true); });
    }

    panel.querySelector('[data-picker-search]').addEventListener('click', search);
    keywordBox.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter') { ev.preventDefault(); search(); }
    });
  });

  /* ---------- 礼物面板：金币 / 钻石礼物，看图挑一个 → 回填 item_id ---------- */
  document.querySelectorAll('[data-gift-picker]').forEach(function (panel) {
    var card = panel.closest('article');
    var endpoint = panel.dataset.pickerEndpoint;
    var listBox = panel.querySelector('[data-gift-list]');
    var statusBox = panel.querySelector('[data-gift-status]');
    var tabs = Array.prototype.slice.call(panel.querySelectorAll('[data-gift-kind]'));
    var kind = tabs.length ? tabs[0].dataset.giftKind : 'gold';
    var cache = {};              // 各类型礼物只拉一次
    var selected = null;

    function unitLabel(item) {
      return item.kind === 'diamond' ? _t('钻石') : _t('金币');
    }

    function giftNode(item) {
      var price = item.sale_price || item.price;
      var btn = el('button', 'flex items-center gap-2 rounded-box border border-base-300 bg-base-100 p-2 text-left hover:border-primary');
      btn.type = 'button';
      if (selected === item.item_id) btn.classList.add('border-primary');
      var img = el('img', 'h-10 w-10 shrink-0 rounded-box border border-base-300 object-cover');
      img.loading = 'lazy';
      img.alt = item.name;
      img.src = item.img;
      btn.appendChild(img);
      var body = el('span', 'min-w-0 flex-1');
      body.appendChild(el('span', 'block truncate text-sm', item.name));
      body.appendChild(el('span', 'block text-xs text-base-content/60', price + ' ' + unitLabel(item)));
      btn.appendChild(body);
      btn.title = (item.desc ? item.desc + '，' : '') + 'item_id=' + item.item_id;
      btn.addEventListener('click', function () {
        // 有 item_id 字段就顺手填进去；没有（如「礼物列表」端点）只提示选中了什么
        var field = card.querySelector('[data-param-name="item_id"]');
        if (field) field.value = String(item.item_id);
        selected = item.item_id;
        listBox.querySelectorAll('button').forEach(function (b) { b.classList.remove('border-primary'); });
        btn.classList.add('border-primary');
        setStatus(statusBox, _ti('已选中「%(name)s」：item_id=%(id)s，%(price)s %(unit)s / 个%(filled)s', {
          name: item.name, id: item.item_id, price: price, unit: unitLabel(item),
          filled: field ? _t('（已填入表单）') : '',
        }));
      });
      return btn;
    }

    function render(items) {
      listBox.innerHTML = '';
      if (!items.length) {
        setStatus(statusBox, _t('该类型下没有礼物'), true);
        return;
      }
      setStatus(statusBox, _ti('共 %(n)s 种，点一个即填入 item_id', { n: items.length }));
      items.forEach(function (item) { listBox.appendChild(giftNode(item)); });
    }

    function load() {
      listBox.innerHTML = '';
      if (cache[kind]) { render(cache[kind]); return; }
      setStatus(statusBox, '加载中…');
      fetchData(endpoint, { kind: kind })
        .then(function (data) {
          cache[kind] = data.results || [];
          render(cache[kind]);
        })
        .catch(function (err) { setStatus(statusBox, _t('加载失败：') + err.message, true); });
    }

    tabs.forEach(function (btn) {
      btn.addEventListener('click', function () {
        tabs.forEach(function (b) { b.classList.remove('tab-active'); });
        btn.classList.add('tab-active');
        kind = btn.dataset.giftKind;
        selected = null;
        load();
      });
    });

    load();
  });
})();
