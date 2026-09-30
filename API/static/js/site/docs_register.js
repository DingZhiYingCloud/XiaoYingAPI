/* API 文档中心 - 注册辅助（一键填写 + 批量注册）
 *
 * 触发条件：端点在文档声明中提供 auto_fill_path（一键填写）/ batch_register_path（批量注册面板）时，
 * 模板会渲染对应容器，本脚本负责交互。
 * 依赖：docs.js 暴露的 window.DocsCall（服务端代签代调，APPID/APPSECRET 取页面鉴权卡片）。
 *
 * 批量注册流程：填数量 → 逐张取验证码（每张一次独立会话，与手动取码同策略）→ 人工逐个填码 →
 * 「一键注册」→ 服务端按验证码数量自动生成 用户名/密码/邮箱（用户名统一 xy_ 前缀）并逐条注册。
 * 点某行的验证码图 = 看不清这张：二次确认后为该行换一张新验证码（原验证码与已填内容作废）。
 */
(function () {
  'use strict';

  var MAX_BATCH = 20;

  // Django i18n 全局函数的安全包装（脚本加载顺序异常时退化为原文）
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
    node.classList.toggle('text-base-content/60', !isError);
  }

  /* ---------- 一键填写：生成一组凭据并填入当前端点的表单 ---------- */
  document.querySelectorAll('[data-auto-fill]').forEach(function (box) {
    var btn = box.querySelector('[data-auto-fill-run]');
    var status = box.querySelector('[data-auto-fill-status]');
    if (!btn) return;

    btn.addEventListener('click', function () {
      var article = box.closest('article');
      btn.disabled = true;
      setStatus(status, _t('生成中…'), false);

      window.DocsCall(box.dataset.fillEndpoint, 'POST', {}).then(function (data) {
        var res = (data && data.json) || null;
        if (!res || res.code !== 10000 || !res.data) {
          setStatus(status, _t('生成失败：') + ((res && res.msg) || _t('未知错误')), true);
          return;
        }
        // 按接口返回的字段名（username / password / email）匹配本端点的同名输入框
        var filled = [];
        Object.keys(res.data).forEach(function (name) {
          var field = article ? article.querySelector('[data-param-name="' + name + '"]') : null;
          if (field) {
            field.value = res.data[name];
            filled.push(name);
          }
        });
        setStatus(status, filled.length
          ? _t('已填入：') + filled.join(' / ')
          : _t('未找到可填写的表单字段'), !filled.length);
      }).catch(function () {
        setStatus(status, _t('网络异常，请检查网络后重试'), true);
      }).finally(function () { btn.disabled = false; });
    });
  });

  /* ---------- 批量注册 ---------- */
  document.querySelectorAll('[data-batch-panel]').forEach(function (panel) {
    var list = panel.querySelector('[data-batch-list]');
    var countInput = panel.querySelector('[data-batch-count]');
    var fetchBtn = panel.querySelector('[data-batch-fetch]');
    var runBtn = panel.querySelector('[data-batch-run]');
    var status = panel.querySelector('[data-batch-status]');
    var article = panel.closest('article');

    // 取本端点表单里的 use_proxy（若该端点有该参数），让批量取码与手动取码走同一策略
    function captchaParams() {
      var field = article ? article.querySelector('[data-param-name="use_proxy"]') : null;
      var value = field ? String(field.value).trim() : '';
      return value ? { use_proxy: value } : {};
    }

    function buildRow(index) {
      var row = el('div', 'flex flex-wrap items-center gap-2 rounded-box border border-base-300 bg-base-100 p-2');
      row.setAttribute('data-batch-row', '');

      var no = el('span', 'badge badge-ghost badge-sm', String(index + 1));
      var image = el('img', 'max-h-12 cursor-pointer rounded-box border border-base-300 bg-base-100');
      image.setAttribute('data-batch-image', '');
      image.alt = _t('注册验证码');
      image.title = _t('看不清？点击更换一张');

      var input = el('input', 'input input-bordered input-sm w-32 font-mono text-sm');
      input.type = 'text';
      input.setAttribute('data-batch-code', '');
      input.placeholder = _t('验证码');
      input.autocomplete = 'off';

      var rowStatus = el('span', 'text-xs text-base-content/60', _t('待填写'));
      rowStatus.setAttribute('data-batch-row-status', '');

      // 点验证码图 = 看不清这张 → 二次确认后换一张新的（原验证码与输入一并作废）
      image.addEventListener('click', function () {
        if (row.dataset.loading) return;
        confirmRenew().then(function (ok) {
          if (!ok) return;
          if (input) input.value = '';
          loadCaptcha(row);
        });
      });

      row.appendChild(no);
      row.appendChild(image);
      row.appendChild(input);
      row.appendChild(rowStatus);
      if (list) list.appendChild(row);
      return row;
    }

    /* 二次确认框：确认后 resolve(true)；取消 / ESC / 点遮罩 resolve(false) */
    function confirmRenew() {
      var dialog = panel.querySelector('[data-batch-confirm]');
      if (!dialog || typeof dialog.showModal !== 'function') return Promise.resolve(false);
      return new Promise(function (resolve) {
        dialog.addEventListener('close', function onClose() {
          dialog.removeEventListener('close', onClose);
          resolve(dialog.returnValue === 'confirm');
        });
        dialog.showModal();
      });
    }

    function fillRow(row, data) {
      var res = (data && data.json) || null;
      var image = row.querySelector('[data-batch-image]');
      var rowStatus = row.querySelector('[data-batch-row-status]');
      if (!res || res.code !== 10000 || !res.data) {
        setStatus(rowStatus, (res && res.msg) || _t('获取失败'), true);
        return;
      }
      row.dataset.captchaToken = res.data.captcha_token || '';
      if (image) image.src = res.data.captcha_image || '';
      // 把本次取码的出口显式标出来：走代理时是代理 IP:端口，直连时写「直连」
      // （源站注册有 IP 限制，看不清走没走代理会让人误判「选了代理却还用本机 IP」）
      var via = res.data.proxy
        ? _ti('出口 %(proxy)s', { proxy: res.data.proxy })
        : _t('直连（本机 IP）');
      setStatus(rowStatus, _t('请填入图中验证码') + '（' + via + '）', false);
    }

    /* 为某一行取一张验证码（每张都是一次独立会话，与手动取码同策略） */
    function loadCaptcha(row) {
      var image = row.querySelector('[data-batch-image]');
      var rowStatus = row.querySelector('[data-batch-row-status]');
      row.dataset.loading = '1';
      row.dataset.captchaToken = '';
      if (image) image.classList.add('opacity-50');
      setStatus(rowStatus, _t('正在获取验证码…'), false);
      return window.DocsCall(panel.dataset.captchaEndpoint, 'POST', captchaParams())
        .then(function (data) { fillRow(row, data); })
        .catch(function () { setStatus(rowStatus, _t('网络异常，请检查网络后重试'), true); })
        .finally(function () {
          delete row.dataset.loading;
          if (image) image.classList.remove('opacity-50');
        });
    }

    if (fetchBtn) {
      fetchBtn.addEventListener('click', function () {
        var count = parseInt(String(countInput ? countInput.value : '').trim(), 10);
        if (!count || count < 1 || count > MAX_BATCH) {
          setStatus(status, _ti('数量需为 1-%(max)s 的整数', { max: MAX_BATCH }), true);
          return;
        }
        if (list) list.innerHTML = '';
        setStatus(status, _ti('正在获取 %(n)s 张验证码…', { n: count }), false);
        fetchBtn.disabled = true;

        var chain = Promise.resolve();
        for (var i = 0; i < count; i++) {
          (function (index) {
            // 串行获取：避免并发触发源站风控
            chain = chain.then(function () { return loadCaptcha(buildRow(index)); });
          })(i);
        }
        chain.finally(function () {
          fetchBtn.disabled = false;
          var ready = 0;
          if (list) {
            list.querySelectorAll('[data-batch-row]').forEach(function (row) {
              if (row.dataset.captchaToken) ready += 1;
            });
          }
          setStatus(status, ready
            ? _ti('已获取 %(n)s 张验证码，请逐张填入验证码后点“一键注册”', { n: ready })
            : _t('获取验证码失败，请重试'), !ready);
        });
      });
    }

    if (runBtn) {
      runBtn.addEventListener('click', function () {
        var rows = list ? Array.prototype.slice.call(list.querySelectorAll('[data-batch-row]')) : [];
        if (!rows.length) {
          setStatus(status, _t('请先获取验证码'), true);
          return;
        }

        var items = [];
        var usable = [];       // 与 items 顺序一一对应，便于把结果回填到对应行
        var missing = [];
        rows.forEach(function (row, index) {
          var token = row.dataset.captchaToken || '';
          if (!token) return;                       // 该行取码失败（或已用过），跳过
          var code = String(row.querySelector('[data-batch-code]').value || '').trim();
          if (!code) {
            missing.push(index + 1);
            return;
          }
          items.push({ captcha_token: token, captcha_code: code });
          usable.push(row);
        });
        if (missing.length) {
          setStatus(status, _ti('第 %(rows)s 行还没填验证码', { rows: missing.join('、') }), true);
          return;
        }
        if (!items.length) {
          setStatus(status, _t('没有可提交的验证码，请重新获取'), true);
          return;
        }

        runBtn.disabled = true;
        fetchBtn.disabled = true;
        setStatus(status, _ti('正在注册 %(n)s 个账号…', { n: items.length }), false);

        window.DocsCall(panel.dataset.batchEndpoint, 'POST', { items: JSON.stringify(items) })
          .then(function (data) {
            var res = (data && data.json) || null;
            if (!res || res.code !== 10000 || !res.data) {
              setStatus(status, (res && res.msg) || _t('注册失败'), true);
              return;
            }
            var results = res.data.items || [];
            var success = 0;
            usable.forEach(function (row, index) {
              var rowStatus = row.querySelector('[data-batch-row-status]');
              var item = results[index] || null;
              if (item && item.success) {
                success += 1;
                setStatus(rowStatus, _ti('成功：%(u)s / %(p)s',
                  { u: item.username, p: item.password }), false);
                rowStatus.classList.remove('text-base-content/60');
                rowStatus.classList.add('text-success');
              } else {
                setStatus(rowStatus, _t('失败：') + ((item && item.msg) || _t('未知原因')), true);
              }
              row.dataset.captchaToken = '';        // 验证码一次性，标记为已用
            });
            setStatus(status, _ti('完成：成功 %(ok)s / 共 %(total)s 条',
              { ok: success, total: items.length }), success === 0);
          })
          .catch(function () {
            setStatus(status, _t('网络异常，请检查网络后重试'), true);
          })
          .finally(function () {
            runBtn.disabled = false;
            fetchBtn.disabled = false;
          });
      });
    }
  });
})();
