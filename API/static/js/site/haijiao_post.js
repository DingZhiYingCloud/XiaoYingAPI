/* 官网 - 海角社区发帖页
 *
 * 纯前端页面：板块 / 标签 / 媒体上传 / 发帖都调本站的海角接口，
 * 统一走 /docs/_call/ 服务端代签（APPID / APPSECRET 取本机保存值，与文档页共用一份）。
 * 海角账号凭据由使用者在页面上填写（用户ID + Token），同样只存本机 localStorage。
 *
 * 关键约定（与源站一致）：
 *   1) 上传与发帖都必须带海角登录态；
 *   2) 正文里的图片 / 视频靠 data-id 关联附件：图片 <img src="真实地址" data-id="附件ID"/>、
 *      视频 <video src="" data-id="附件ID"></video>（由«上传媒体»返回的 data.html 提供）；
 *   3) 源站限制：视频一次只能 1 个、图片最多 20 张（单张 ≤10MB）；
 *   4) 源站对所有新帖走人工审核，提交成功但拿不到帖子 ID 时即为「待审核」。
 *
 * 媒体与正文解耦：媒体在独立模块里增删 / 排序，发布时按顺序附到正文末尾。
 */
(function () {
  'use strict';

  var CRED_KEY = 'xyapi_haijiao_cred';     // 海角账号凭据（用户ID + Token）
  var AUTH_KEY = 'xyapi_docs_auth';        // 接入鉴权（APPID + APPSECRET），与文档页共用
  var DRAFT_KEY = 'xyapi_haijiao_draft';   // 草稿（标题 / 正文 / 板块 / 标签 / 媒体清单）

  var MAX_IMAGES = 20;                     // 源站限制：图片最多 20 张
  var MAX_IMAGE_BYTES = 10 * 1024 * 1024;  // 源站限制：单张图片 ≤10MB
  var IMAGE_EXTS = ['.png', '.jpg', '.jpeg', '.gif', '.bmp'];
  var VIDEO_EXTS = ['.mp4'];

  // 源站根地址：海角域名不固定，由后端统一注入（唯一出处是 SpiderServices/haijiao/utils.py 的 BASE_URL）
  var SITE_BASE = (function () {
    var holder = document.querySelector('[data-site-base]');
    return holder ? (holder.getAttribute('data-site-base') || '') : '';
  })();

  // 源站帖子详情页地址
  function topicUrl(topicId) {
    return SITE_BASE + '/post/details?pid=' + topicId;
  }

  function _t(s) { return (typeof gettext === 'function') ? gettext(s) : s; }
  function _ti(s, ctx) { return (typeof interpolate === 'function') ? interpolate(s, ctx, true) : s; }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function csrfToken() {
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return input ? input.value : '';
  }

  function extOf(name) {
    var i = String(name || '').lastIndexOf('.');
    return i >= 0 ? String(name).slice(i).toLowerCase() : '';
  }

  function humanSize(bytes) {
    if (bytes >= 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + 'MB';
    return Math.max(1, Math.round(bytes / 1024)) + 'KB';
  }

  var form = document.getElementById('post-form');
  if (!form) return;
  var statusBox = form.querySelector('[data-post-status]');

  function setStatus(text, isError) {
    if (!statusBox) return;
    statusBox.textContent = text || '';
    statusBox.classList.toggle('text-error', !!isError);
    statusBox.classList.toggle('text-success', !isError && !!text);
    statusBox.classList.toggle('text-base-content/60', !isError && !text);
  }

  /* ==================== 本机保存的凭据与鉴权 ==================== */
  var credUserId = document.querySelector('[data-cred-user-id]');
  var credToken = document.querySelector('[data-cred-user-token]');
  var appIdInput = document.querySelector('[data-auth-app-id]');
  var appSecretInput = document.querySelector('[data-auth-app-secret]');

  function loadSaved() {
    try {
      var cred = JSON.parse(localStorage.getItem(CRED_KEY) || 'null');
      if (cred) {
        if (cred.user_id) credUserId.value = cred.user_id;
        if (cred.user_token) credToken.value = cred.user_token;
      }
      var auth = JSON.parse(localStorage.getItem(AUTH_KEY) || 'null');
      if (auth) {
        if (auth.app_id) appIdInput.value = auth.app_id;
        if (auth.app_secret) appSecretInput.value = auth.app_secret;
      }
    } catch (e) { /* 忽略损坏的本地数据 */ }
  }

  function saveTo(key, payload, btn) {
    localStorage.setItem(key, JSON.stringify(payload));
    var old = btn.textContent;
    btn.textContent = _t('已保存到本机');
    setTimeout(function () { btn.textContent = old; }, 1500);
  }

  var credSaveBtn = document.querySelector('[data-cred-save]');
  credSaveBtn.addEventListener('click', function () {
    saveTo(CRED_KEY, {
      user_id: credUserId.value.trim(),
      user_token: credToken.value.trim(),
    }, credSaveBtn);
  });

  var authSaveBtn = document.querySelector('[data-auth-save]');
  authSaveBtn.addEventListener('click', function () {
    saveTo(AUTH_KEY, {
      app_id: appIdInput.value.trim(),
      app_secret: appSecretInput.value.trim(),
    }, authSaveBtn);
  });

  loadSaved();

  /* ==================== 调用本站接口（服务端代签） ==================== */
  function apiCall(method, path, params) {
    return fetch('/docs/_call/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
      body: JSON.stringify({
        path: path,
        method: method,
        params: params || {},
        app_id: appIdInput.value.trim(),
        app_secret: appSecretInput.value.trim(),
      }),
    }).then(function (res) { return res.json(); });
  }

  /* 媒体上传走 multipart（文件字段名 file）；用 XHR 是为了拿到上传进度 */
  function apiUpload(path, params, file, onProgress) {
    return new Promise(function (resolve, reject) {
      var fd = new FormData();
      fd.append('path', path);
      fd.append('method', 'POST');
      if (appIdInput.value.trim()) fd.append('app_id', appIdInput.value.trim());
      if (appSecretInput.value.trim()) fd.append('app_secret', appSecretInput.value.trim());
      Object.keys(params).forEach(function (k) { if (params[k]) fd.append(k, params[k]); });
      fd.append('file', file, file.name);

      var xhr = new XMLHttpRequest();
      xhr.open('POST', '/docs/_call/');
      xhr.setRequestHeader('X-CSRFToken', csrfToken());
      xhr.upload.onprogress = function (e) {
        if (onProgress && e.lengthComputable) onProgress(Math.round(e.loaded / e.total * 100));
      };
      xhr.onload = function () {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch (err) {
          reject(new Error(_t('接口无响应，请稍后重试')));
        }
      };
      xhr.onerror = function () { reject(new Error(_t('网络异常，请检查网络后重试'))); };
      xhr.send(fd);
    });
  }

  /* 取接口返回的业务数据；失败时抛出可直接展示的原因 */
  function unwrap(res, fallbackMsg) {
    var body = (res && res.json) || null;
    if (!body) throw new Error(fallbackMsg || _t('接口无响应'));
    if (body.code !== 10000) throw new Error(body.msg || fallbackMsg || _t('请求失败'));
    return body.data;
  }

  /* ==================== 板块：一级 → 二级 → 三级联动 ==================== */
  var selects = [
    form.querySelector('[data-node-level="1"]'),
    form.querySelector('[data-node-level="2"]'),
    form.querySelector('[data-node-level="3"]'),
  ];
  var LEVEL_HINTS = ['', _t('请选择板块'), _t('可选：二级板块'), _t('可选：三级板块')];
  var nodeTree = [];

  function nodeOptions(select, nodes, level) {
    select.innerHTML = '';
    var head = el('option', null, LEVEL_HINTS[level] || _t('可选'));
    head.value = '';
    select.appendChild(head);
    nodes.forEach(function (node) {
      var opt = el('option', null, node.name);
      opt.value = String(node.node_id);
      select.appendChild(opt);
    });
    select.classList.toggle('hidden', nodes.length === 0);
    select.value = '';
  }

  function pickedNodeId() {
    var picked = '';
    selects.forEach(function (select) {
      if (!select.classList.contains('hidden') && select.value) picked = select.value;
    });
    return picked;
  }

  function bindLevel(level) {
    selects[level - 1].addEventListener('change', function () {
      var nodes = nodeTree;
      for (var i = 0; i < level; i++) {
        var value = selects[i].value;
        if (!value) break;
        var hit = nodes.filter(function (n) { return String(n.node_id) === value; })[0];
        nodes = hit ? hit.children : [];
      }
      if (level < 3) nodeOptions(selects[level], nodes, level + 1);
      scheduleDraft();
    });
  }
  bindLevel(1);
  bindLevel(2);

  /* 只保留源站发帖菜单里可见的板块（display === 1） */
  function visibleNodes(nodes) {
    return (nodes || [])
      .filter(function (n) { return n.display === 1; })
      .map(function (n) {
        return { node_id: n.node_id, name: n.name, children: visibleNodes(n.children) };
      });
  }

  /* 在板块树里找出到目标板块的完整路径（用于草稿恢复） */
  function findNodePath(nodes, targetId, path) {
    path = path || [];
    for (var i = 0; i < nodes.length; i++) {
      var next = path.concat([nodes[i]]);
      if (String(nodes[i].node_id) === String(targetId)) return next;
      var sub = findNodePath(nodes[i].children || [], targetId, next);
      if (sub) return sub;
    }
    return null;
  }

  function restoreNode(nodeId) {
    if (!nodeId || !nodeTree.length) return;
    var path = findNodePath(nodeTree, nodeId);
    if (!path) return;
    for (var i = 0; i < path.length && i < selects.length; i++) {
      selects[i].value = String(path[i].node_id);
      selects[i].dispatchEvent(new Event('change'));
    }
  }

  function loadNodes() {
    apiCall('GET', '/api/haijiao/topic/nodes').then(function (res) {
      nodeTree = visibleNodes(unwrap(res).list);
      nodeOptions(selects[0], nodeTree, 1);
      restoreNode(restoredDraft ? restoredDraft.node_id : '');
    }).catch(function (err) {
      nodeOptions(selects[0], [], 1);
      setStatus(_t('板块加载失败：') + err.message, true);
    });
  }

  /* ==================== 标签：已选 chips + 自定义 + 标签池 ==================== */
  var tagsBox = form.querySelector('[data-post-tags]');
  var tagInput = form.querySelector('[data-tag-input]');
  var tagList = form.querySelector('[data-tag-list]');
  var tagPanel = form.querySelector('[data-tag-panel]');
  var tagFilter = form.querySelector('[data-tag-filter]');
  var tagPageLabel = form.querySelector('[data-tag-page]');
  var selectedTags = [];
  var poolTags = [];
  var poolPage = 1;

  function renderTags() {
    tagsBox.innerHTML = '';
    if (!selectedTags.length) {
      tagsBox.appendChild(el('span', 'text-xs text-base-content/50', _t('还没有选择标签')));
      return;
    }
    selectedTags.forEach(function (name) {
      // max-w-full + truncate：超长标签名也不会撑破容器
      var chip = el('span', 'badge badge-primary badge-sm max-w-full gap-1');
      chip.appendChild(el('span', 'truncate', name));
      var close = el('button', 'shrink-0 cursor-pointer', '×');
      close.type = 'button';
      close.addEventListener('click', function () {
        selectedTags = selectedTags.filter(function (t) { return t !== name; });
        renderTags();
        renderTagPool();
        scheduleDraft();
      });
      chip.appendChild(close);
      tagsBox.appendChild(chip);
    });
  }

  function addTag(name) {
    name = (name || '').trim().replace(/^#/, '');
    if (!name || selectedTags.indexOf(name) >= 0) return;
    selectedTags.push(name);
    renderTags();
    scheduleDraft();
  }

  form.querySelector('[data-tag-add]').addEventListener('click', function () {
    addTag(tagInput.value);
    tagInput.value = '';
  });
  tagInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      addTag(tagInput.value);
      tagInput.value = '';
    }
  });
  form.querySelector('[data-tag-pool]').addEventListener('click', function () {
    tagPanel.classList.toggle('hidden');
    if (!tagPanel.classList.contains('hidden') && !poolTags.length) loadTagPool(1);
  });

  function renderTagPool() {
    var keyword = tagFilter.value.trim();
    tagList.innerHTML = '';
    var shown = poolTags.filter(function (t) {
      return !keyword || t.tag_name.indexOf(keyword) >= 0;
    });
    if (!shown.length) {
      tagList.appendChild(el('span', 'text-xs text-base-content/50', _t('本页没有匹配的标签')));
      return;
    }
    shown.forEach(function (tag) {
      var active = selectedTags.indexOf(tag.tag_name) >= 0;
      var chip = el('button', 'btn btn-xs max-w-full truncate ' + (active ? 'btn-primary' : 'btn-outline'),
        tag.tag_name);
      chip.type = 'button';
      chip.addEventListener('click', function () {
        if (active) {
          selectedTags = selectedTags.filter(function (t) { return t !== tag.tag_name; });
        } else {
          addTag(tag.tag_name);
        }
        renderTags();
        renderTagPool();
      });
      tagList.appendChild(chip);
    });
  }

  function loadTagPool(page) {
    tagList.innerHTML = '';
    tagList.appendChild(el('span', 'text-xs text-base-content/50', _t('加载中…')));
    apiCall('GET', '/api/haijiao/topic/tags', { page: String(page) }).then(function (res) {
      var data = unwrap(res);
      var totalPage = data.pagination.total_page || 1;
      if (page > totalPage) { loadTagPool(totalPage); return; }
      poolPage = data.pagination.page;
      poolTags = data.results;
      tagPageLabel.textContent = _ti('第 %(p)s / %(t)s 页（共 %(n)s 个标签）',
        { p: poolPage, t: totalPage, n: data.pagination.total });
      renderTagPool();
    }).catch(function (err) {
      tagList.innerHTML = '';
      tagList.appendChild(el('span', 'text-xs text-error', _t('标签加载失败：') + err.message));
    });
  }

  tagFilter.addEventListener('input', renderTagPool);
  form.querySelector('[data-tag-prev]').addEventListener('click', function () {
    if (poolPage > 1) loadTagPool(poolPage - 1);
  });
  form.querySelector('[data-tag-next]').addEventListener('click', function () {
    loadTagPool(poolPage + 1);
  });

  renderTags();

  /* ==================== 正文编辑器 ==================== */
  var editor = form.querySelector('[data-editor]');
  var editorCount = form.querySelector('[data-editor-count]');

  try { document.execCommand('defaultParagraphSeparator', false, 'p'); } catch (e) { /* 非关键 */ }

  function updateCount() {
    var text = (editor.innerText || '').replace(/\s+/g, '');
    editorCount.textContent = text.length ? _ti('%(n)s 字', { n: text.length }) : '0';
  }
  editor.addEventListener('input', updateCount);

  /* 工具栏：命令类（execCommand）与块级（formatBlock）分开绑定 */
  form.querySelectorAll('[data-editor-cmd]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      editor.focus();
      document.execCommand(btn.dataset.editorCmd, false, null);
      updateCount();
      scheduleDraft();
    });
  });
  form.querySelectorAll('[data-editor-block]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      editor.focus();
      document.execCommand('formatBlock', false, btn.dataset.editorBlock);
      updateCount();
      scheduleDraft();
    });
  });
  form.querySelector('[data-editor-clear-format]').addEventListener('click', function () {
    editor.focus();
    document.execCommand('removeFormat', false, null);
    document.execCommand('formatBlock', false, 'P');
    updateCount();
    scheduleDraft();
  });

  /* 粘贴清洗：外部页面带来的 class/style/脚本会让源站排版错乱，这里只保留正文标签 */
  var PASTE_BLOCK_TAGS = { SCRIPT: 1, STYLE: 1, IFRAME: 1, OBJECT: 1, EMBED: 1, LINK: 1, META: 1, FORM: 1, INPUT: 1 };
  var PASTE_KEEP_ATTRS = { href: 1, src: 1, alt: 1 };

  function sanitizeHtml(html) {
    var doc = new DOMParser().parseFromString(html, 'text/html');
    var walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_ELEMENT, null);
    var drop = [];
    while (walker.nextNode()) {
      var node = walker.currentNode;
      if (PASTE_BLOCK_TAGS[node.tagName]) { drop.push(node); continue; }
      Array.prototype.slice.call(node.attributes).forEach(function (attr) {
        if (!PASTE_KEEP_ATTRS[attr.name.toLowerCase()]) node.removeAttribute(attr.name);
      });
    }
    drop.forEach(function (node) { node.parentNode && node.parentNode.removeChild(node); });
    return doc.body.innerHTML;
  }

  editor.addEventListener('paste', function (e) {
    e.preventDefault();
    var data = e.clipboardData || window.clipboardData;
    var html = data.getData('text/html');
    var text = data.getData('text/plain');
    var insert = html ? sanitizeHtml(html)
      : text.replace(/[&<>]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]; })
        .replace(/\n{2,}/g, '</p><p>').replace(/\n/g, '<br>');
    document.execCommand('insertHTML', false, insert.indexOf('<') === 0 ? insert : '<p>' + insert + '</p>');
    updateCount();
    scheduleDraft();
  });

  /* ==================== 媒体模块（独立于正文） ==================== */
  var mediaList = form.querySelector('[data-media-list]');
  var mediaStatus = form.querySelector('[data-media-status]');
  var imageInput = form.querySelector('[data-media-image-input]');
  var videoInput = form.querySelector('[data-media-video-input]');
  var mediaItems = [];      // [{attachment_id, category, url, html, name, size, thumbNode?}]
  var uploading = false;
  var mediaMenu = form.querySelector('[data-media-menu]');
  var mediaInfo = form.querySelector('[data-media-info]');
  var menuIndex = -1;

  function setMediaStatus(text, isError) {
    mediaStatus.textContent = text || '';
    mediaStatus.classList.toggle('text-error', !!isError);
  }

  function imageCount() {
    return mediaItems.filter(function (m) { return m.category !== 'video'; }).length;
  }
  function hasVideo() {
    return mediaItems.some(function (m) { return m.category === 'video'; });
  }

  /* 缩略图网格：只显示画面与顺序号，附件信息与操作都收进右键菜单 */
  function renderMedia() {
    mediaList.innerHTML = '';
    if (!mediaItems.length) {
      mediaList.appendChild(el('div',
        'col-span-full rounded-box border border-dashed border-base-300 p-4 text-center text-xs text-base-content/50',
        _t('还没有添加图片或视频')));
      return;
    }
    mediaItems.forEach(function (item, index) {
      var cell = el('div',
        'group relative aspect-square overflow-hidden rounded-box border border-base-300 bg-base-200');
      cell.dataset.mediaIndex = String(index);
      cell.title = item.name || '';

      if (item.category === 'video') {
        var box = el('div',
          'absolute inset-0 flex flex-col items-center justify-center gap-1 px-1 text-base-content/60');
        box.appendChild(el('span', 'text-xs font-semibold', _t('视频')));
        box.appendChild(el('span', 'w-full truncate text-center text-[10px]', item.name || ''));
        cell.appendChild(box);
      } else {
        // 缩略图节点按附件缓存复用：重排 / 删除时不重复请求图片
        if (!item.thumbNode) {
          // 绝对定位填满格子：图片固有比例不会把方格撑变形
          var thumb = el('img', 'absolute inset-0 h-full w-full object-cover');
          thumb.loading = 'lazy';
          thumb.alt = _t('已添加的图片');
          // 源站图片是混淆地址（.txt），借本站「图片解码」接口出缩略图
          thumb.src = '/api/haijiao/image?url=' + encodeURIComponent(item.url);
          item.thumbNode = thumb;
        }
        cell.appendChild(item.thumbNode);
      }

      cell.appendChild(el('span',
        'badge badge-sm absolute left-1 top-1 border-0 bg-base-100/85 text-[10px]', String(index + 1)));

      // 鼠标端靠右键；触屏没有右键，故留一个轻量入口（大屏悬停才明显）
      var dots = el('button',
        'btn btn-circle btn-xs absolute right-1 top-1 border-0 bg-base-100/85 opacity-70 transition '
        + 'lg:opacity-0 lg:group-hover:opacity-100', '⋯');
      dots.type = 'button';
      dots.dataset.mediaDots = String(index);
      dots.title = _t('更多操作');
      cell.appendChild(dots);

      mediaList.appendChild(cell);
    });
  }

  function closeMenu() {
    mediaMenu.classList.add('hidden');
    menuIndex = -1;
  }

  /* 菜单按点击位置显示，并夹在视口内，避免贴边时被裁掉 */
  function openMenu(index, x, y) {
    menuIndex = index;
    mediaMenu.classList.remove('hidden');
    var left = Math.max(8, Math.min(x, window.innerWidth - mediaMenu.offsetWidth - 8));
    var top = Math.max(8, Math.min(y, window.innerHeight - mediaMenu.offsetHeight - 8));
    mediaMenu.style.left = left + 'px';
    mediaMenu.style.top = top + 'px';
    mediaMenu.querySelector('[data-menu-act="up"]').disabled = index === 0;
    mediaMenu.querySelector('[data-menu-act="down"]').disabled = index === mediaItems.length - 1;
  }

  /* 右键缩略图 → 菜单 */
  mediaList.addEventListener('contextmenu', function (e) {
    var cell = e.target.closest('[data-media-index]');
    if (!cell) return;
    e.preventDefault();
    openMenu(Number(cell.dataset.mediaIndex), e.clientX, e.clientY);
  });

  /* 点 ⋯ → 同一个菜单（触屏可用） */
  mediaList.addEventListener('click', function (e) {
    var dots = e.target.closest('[data-media-dots]');
    if (!dots) return;
    e.preventDefault();
    e.stopPropagation();
    var rect = dots.getBoundingClientRect();
    openMenu(Number(dots.dataset.mediaDots), rect.left, rect.bottom + 4);
  });

  document.addEventListener('click', function (e) {
    if (!mediaMenu.classList.contains('hidden') && !mediaMenu.contains(e.target)) closeMenu();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeMenu();
  });
  window.addEventListener('resize', closeMenu);
  window.addEventListener('scroll', closeMenu, true);

  mediaMenu.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-menu-act]');
    if (!btn || btn.disabled) return;
    var index = menuIndex;
    var act = btn.dataset.menuAct;
    closeMenu();
    if (index < 0 || index >= mediaItems.length) return;

    if (act === 'info') { showInfo(index); return; }
    if (act === 'del') {
      var removed = mediaItems.splice(index, 1)[0];
      setMediaStatus(_ti('已删除 %(name)s', { name: removed.name || '' }), false);
      renderMedia();
      scheduleDraft();
      return;
    }
    var target = index + (act === 'up' ? -1 : 1);
    if (target < 0 || target >= mediaItems.length) return;
    var tmp = mediaItems[index];
    mediaItems[index] = mediaItems[target];
    mediaItems[target] = tmp;
    renderMedia();
    scheduleDraft();
  });

  /* ==================== 附件信息弹窗 ==================== */
  function clipboardCopy(text) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
    return new Promise(function (resolve, reject) {
      var area = el('textarea', 'fixed left-[-9999px] top-0');
      area.value = text;
      document.body.appendChild(area);
      area.select();
      var ok = false;
      try { ok = document.execCommand('copy'); } catch (err) { ok = false; }
      document.body.removeChild(area);
      ok ? resolve() : reject(new Error('copy failed'));
    });
  }

  function infoRow(label, value, copyable) {
    var row = el('div', 'rounded-box border border-base-300 bg-base-100 p-2');
    row.appendChild(el('div', 'text-base-content/60', label));
    var line = el('div', 'mt-1 flex items-start gap-2');
    // break-all：长地址也不会撑破弹窗
    line.appendChild(el('div', 'min-w-0 flex-1 break-all font-mono', value));
    if (copyable) {
      var btn = el('button', 'btn btn-ghost btn-xs shrink-0', _t('复制'));
      btn.type = 'button';
      btn.addEventListener('click', function () {
        clipboardCopy(value).then(function () {
          btn.textContent = _t('已复制');
          setTimeout(function () { btn.textContent = _t('复制'); }, 1200);
        }).catch(function () {
          setMediaStatus(_t('复制失败，请手动选择复制'), true);
        });
      });
      line.appendChild(btn);
    }
    row.appendChild(line);
    return row;
  }

  function showInfo(index) {
    var item = mediaItems[index];
    if (!item) return;
    var isVideo = item.category === 'video';
    form.querySelector('[data-info-title]').textContent = isVideo ? _t('视频信息') : _t('图片信息');
    var body = form.querySelector('[data-info-body]');
    body.innerHTML = '';
    body.appendChild(infoRow(_t('类型'), isVideo ? _t('视频') : _t('图片')));
    body.appendChild(infoRow(_t('文件名'), item.name || '-'));
    body.appendChild(infoRow(_t('大小'), humanSize(item.size || 0)));
    body.appendChild(infoRow(_t('发布顺序'), _ti('第 %(n)s 个', { n: index + 1 })));
    body.appendChild(infoRow(_t('附件 ID'), String(item.attachment_id), true));
    body.appendChild(isVideo
      ? infoRow(_t('视频路径'), _t('源站不返回视频地址（视频靠附件 ID 关联播放器）'))
      : infoRow(_t('图片路径'), item.url || '-', true));
    body.appendChild(infoRow(_t('正文片段'), item.html || '-', true));

    var preview = form.querySelector('[data-info-preview]');
    preview.disabled = isVideo || !item.url;
    preview.dataset.infoUrl = isVideo ? '' : (item.url || '');
    mediaInfo.showModal();
  }

  form.querySelector('[data-info-preview]').addEventListener('click', function () {
    var url = this.dataset.infoUrl;
    if (url) window.open('/api/haijiao/image?url=' + encodeURIComponent(url), '_blank', 'noopener');
  });
  form.querySelectorAll('[data-info-close]').forEach(function (node) {
    node.addEventListener('click', function () { mediaInfo.close(); });
  });

  function pickFiles(kind) {
    if (uploading) { setMediaStatus(_t('正在上传，请稍候'), true); return; }
    if (kind === 'video' && hasVideo()) {
      setMediaStatus(_t('已有 1 个视频（源站一次只允许 1 个），请先删除后再添加'), true);
      return;
    }
    var input = kind === 'video' ? videoInput : imageInput;
    input.value = '';
    input.click();
  }

  form.querySelectorAll('[data-media-pick]').forEach(function (btn) {
    btn.addEventListener('click', function () { pickFiles(btn.dataset.mediaPick); });
  });

  form.querySelector('[data-media-clear]').addEventListener('click', function () {
    if (!mediaItems.length) return;
    mediaItems = [];
    renderMedia();
    setMediaStatus(_t('已清空媒体'), false);
    scheduleDraft();
  });

  function handleFiles(kind, files) {
    var list = Array.prototype.slice.call(files || []);
    if (!list.length) return;

    var accepted = [];
    var errors = [];
    list.forEach(function (file) {
      var ext = extOf(file.name);
      if (kind === 'video') {
        if (VIDEO_EXTS.indexOf(ext) < 0) { errors.push(_ti('%(name)s：只支持 mp4 视频', { name: file.name })); return; }
        accepted.push(file);
        return;
      }
      if (IMAGE_EXTS.indexOf(ext) < 0) {
        errors.push(_ti('%(name)s：只支持 png / jpg / jpeg / gif / bmp', { name: file.name }));
        return;
      }
      if (file.size > MAX_IMAGE_BYTES) { errors.push(_ti('%(name)s：图片超过 10MB', { name: file.name })); return; }
      accepted.push(file);
    });

    if (kind === 'video') {
      if (accepted.length > 1) {
        errors.push(_t('源站一次只能上传 1 个视频，已只保留第一个'));
        accepted = accepted.slice(0, 1);
      }
      if (hasVideo()) { setMediaStatus(_t('已有 1 个视频，请先删除'), true); return; }
    } else {
      var room = MAX_IMAGES - imageCount();
      if (accepted.length > room) {
        errors.push(_ti('图片最多 %(n)s 张，超出部分已忽略', { n: MAX_IMAGES }));
        accepted = accepted.slice(0, Math.max(0, room));
      }
    }

    if (!accepted.length) {
      setMediaStatus(errors.join('；') || _t('没有可上传的文件'), true);
      return;
    }
    if (errors.length) setMediaStatus(errors.join('；'), true);

    uploadSerial(kind, accepted, 0);
  }

  /* 串行上传：逐张提交，避免并发触发源站风控，也便于逐张显示进度 */
  function uploadSerial(kind, files, index) {
    var file = files[index];
    uploading = true;
    apiUpload('/api/haijiao/topic/upload', {
      user_id: credUserId.value.trim(),
      user_token: credToken.value.trim(),
    }, file, function (percent) {
      setMediaStatus(_ti('正在上传 %(i)s/%(n)s · %(p)s%%',
        { i: index + 1, n: files.length, p: percent }), false);
    }).then(function (res) {
      var data = unwrap(res, _t('上传失败'));
      mediaItems.push({
        attachment_id: data.attachment_id,
        category: data.category,
        url: data.url || '',
        html: data.html,
        name: file.name,
        size: file.size,
      });
      renderMedia();
      var messages = [_ti('已添加 %(name)s', { name: file.name })];
      if (index + 1 < files.length) messages.push(_ti('继续上传 %(n)s 个…', { n: files.length - index - 1 }));
      setMediaStatus(messages.join('；'), false);
      scheduleDraft();
      return next(kind, files, index + 1);
    }).catch(function (err) {
      setMediaStatus(_t('上传失败：') + err.message, true);
    }).finally(function () {
      uploading = false;
    });
  }

  function next(kind, files, index) {
    if (index >= files.length) return null;
    return uploadSerial(kind, files, index);
  }

  imageInput.addEventListener('change', function () { handleFiles('image', imageInput.files); });
  videoInput.addEventListener('change', function () { handleFiles('video', videoInput.files); });

  renderMedia();

  /* ==================== 草稿：本机暂存，刷新不丢 ==================== */
  var restoredDraft = null;
  var draftTimer = null;

  function draftPayload() {
    return {
      node_id: pickedNodeId(),
      title: form.querySelector('[data-post-title]').value,
      tags: selectedTags.slice(),
      content: editor.innerHTML,
      media: mediaItems.map(function (m) {
        return { attachment_id: m.attachment_id, category: m.category, url: m.url, html: m.html, name: m.name, size: m.size };
      }),
    };
  }

  function scheduleDraft() {
    if (draftTimer) clearTimeout(draftTimer);
    draftTimer = setTimeout(function () {
      try { localStorage.setItem(DRAFT_KEY, JSON.stringify(draftPayload())); } catch (e) { /* 容量不足则忽略 */ }
    }, 600);
  }

  function clearDraft() {
    try { localStorage.removeItem(DRAFT_KEY); } catch (e) { /* 忽略 */ }
  }

  function applyDraft(draft) {
    if (!draft) return;
    if (draft.title) form.querySelector('[data-post-title]').value = draft.title;
    if (draft.content) editor.innerHTML = draft.content;
    if (draft.tags && draft.tags.length) selectedTags = draft.tags.slice();
    if (draft.media && draft.media.length) mediaItems = draft.media.slice();
    renderTags();
    renderMedia();
    updateCount();
    setStatus(_t('已恢复上次未发布的草稿'), false);
  }

  try { restoredDraft = JSON.parse(localStorage.getItem(DRAFT_KEY) || 'null'); } catch (e) { restoredDraft = null; }
  if (restoredDraft) applyDraft(restoredDraft);

  form.querySelector('[data-post-title]').addEventListener('input', scheduleDraft);
  editor.addEventListener('input', scheduleDraft);

  /* ==================== 帖子类型：出售 / 悬赏才需要货币与金额 ==================== */
  var typeSelect = form.querySelector('[data-post-type]');
  var moneyBox = form.querySelector('[data-money-box]');
  var amountBox = form.querySelector('[data-amount-box]');
  var rewardBox = form.querySelector('[data-reward-box]');
  typeSelect.addEventListener('change', function () {
    var type = typeSelect.value;
    moneyBox.classList.toggle('hidden', type === '0');
    amountBox.classList.toggle('hidden', type === '0');
    rewardBox.classList.toggle('hidden', type !== '2');
  });

  form.querySelector('[data-post-clear]').addEventListener('click', function () {
    editor.innerHTML = '';
    updateCount();
    setMediaStatus('', false);
    scheduleDraft();
  });

  /* ==================== 提交 ==================== */
  /* 媒体按顺序附到正文末尾：图片包一层 <p>（与源站正文一致），视频直接跟在后面 */
  function buildContent() {
    var mediaHtml = mediaItems.map(function (item) {
      return item.category === 'video' ? item.html : '<p>' + item.html + '</p>';
    }).join('');
    return (editor.innerHTML.trim() + mediaHtml).trim();
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var nodeId = pickedNodeId();
    var title = form.querySelector('[data-post-title]').value.trim();
    var content = buildContent();
    var userId = credUserId.value.trim();
    var userToken = credToken.value.trim();

    if (!nodeId) { setStatus(_t('请选择板块'), true); return; }
    if (!selectedTags.length) { setStatus(_t('请至少添加一个标签'), true); return; }
    if (!title) { setStatus(_t('请填写标题'), true); return; }
    if (!content) { setStatus(_t('请填写正文或添加图片 / 视频'), true); return; }
    if (!userId || !userToken) { setStatus(_t('请填写海角账号的用户ID与Token'), true); return; }
    if (!appIdInput.value.trim() || !appSecretInput.value.trim()) {
      setStatus(_t('请填写接入鉴权的 APPID / APPSECRET'), true);
      return;
    }
    if (uploading) { setStatus(_t('媒体还在上传，请稍候'), true); return; }

    var submitBtn = form.querySelector('[data-post-submit]');
    submitBtn.disabled = true;
    setStatus(_t('正在发布…'), false);

    apiCall('POST', '/api/haijiao/topic/create', {
      node_id: nodeId,
      title: title,
      content: content,
      tags: selectedTags.join(','),
      type: typeSelect.value,
      money_type: form.querySelector('[data-post-money-type]').value,
      amount: form.querySelector('[data-post-amount]').value || '0',
      reward_hours: form.querySelector('[data-post-reward-hours]').value || '0',
      user_id: userId,
      user_token: userToken,
    }).then(function (res) {
      var data = unwrap(res);
      clearDraft();
      loadMine(1);      // 发布后刷新「我的帖子」看板，方便直接看到结果
      if (data.pending) {
        setStatus(_t('发布成功，待源站审核通过后即可查看'), false);
        return;
      }
      statusBox.innerHTML = '';
      statusBox.appendChild(el('span', null, _t('发帖成功：')));
      var link = el('a', 'link link-primary', topicUrl(data.topic_id));
      link.href = topicUrl(data.topic_id);
      link.target = '_blank';
      link.rel = 'noopener';
      statusBox.appendChild(link);
      statusBox.classList.remove('text-error');
      statusBox.classList.add('text-success');
    }).catch(function (err) {
      setStatus(_t('发布失败：') + err.message, true);
    }).finally(function () {
      submitBtn.disabled = false;
    });
  });

  /* ==================== 我的帖子看板（发布成功 / 审核中 / 审核失败） ==================== */
  var mineTabs = Array.prototype.slice.call(document.querySelectorAll('[data-mine-status]'));
  var mineList = document.querySelector('[data-mine-list]');
  var mineHint = document.querySelector('[data-mine-hint]');
  var minePageLabel = document.querySelector('[data-mine-page]');
  var mineStatus = mineTabs.length ? mineTabs[0].dataset.mineStatus : 'published';
  var minePage = 1;
  var mineTotalPage = 1;

  function setMineHint(text, isError) {
    mineHint.textContent = text || '';
    mineHint.classList.toggle('text-error', !!isError);
  }

  function mineItemNode(item) {
    var row = el('div', 'flex gap-3 rounded-box border border-base-300 bg-base-100 p-3');

    var images = item.images || [];
    if (images.length) {
      var thumb = el('img', 'h-16 w-16 shrink-0 rounded-box border border-base-300 object-cover');
      thumb.loading = 'lazy';
      thumb.alt = _t('帖子配图');
      // 源站图片是混淆地址（.txt），借本站「图片解码」接口出缩略图
      thumb.src = '/api/haijiao/image?url=' + encodeURIComponent(images[0]);
      row.appendChild(thumb);
    }

    var body = el('div', 'min-w-0 flex-1');
    var head = el('div', 'flex flex-wrap items-center gap-2');
    if (item.topic_id) {
      var link = el('a', 'link link-primary min-w-0 text-sm font-medium', item.title || '');
      link.href = topicUrl(item.topic_id);
      link.target = '_blank';
      link.rel = 'noopener';
      head.appendChild(link);
    } else {
      head.appendChild(el('span', 'min-w-0 text-sm font-medium', item.title || ''));
    }
    if (item.node && item.node.name) head.appendChild(el('span', 'badge badge-ghost badge-sm', item.node.name));
    if (item.has_video) head.appendChild(el('span', 'badge badge-ghost badge-sm', _t('视频')));
    else if (item.has_pic) head.appendChild(el('span', 'badge badge-ghost badge-sm', _t('图文')));
    if (!item.topic_id) {
      head.appendChild(el('span', 'badge badge-ghost badge-sm', _ti('待审 ID %(id)s', { id: item.pending_id || '-' })));
    }
    body.appendChild(head);

    if (item.excerpt) {
      body.appendChild(el('p', 'mt-1 break-words text-xs text-base-content/60', item.excerpt));
    }
    if (item.remarks) {
      body.appendChild(el('p', 'mt-1 break-words rounded-box border border-base-300 bg-base-200/40 px-2 py-1 text-xs text-error',
        _t('驳回原因：') + item.remarks));
    }
    body.appendChild(el('div', 'mt-1 text-xs text-base-content/50',
      _ti('%(time)s · 浏览 %(v)s · 评论 %(c)s · 赞 %(l)s', {
        time: item.create_time || '', v: item.view_count, c: item.comment_count, l: item.like_count,
      })));
    row.appendChild(body);
    return row;
  }

  function loadMine(page) {
    var userId = credUserId.value.trim();
    var userToken = credToken.value.trim();
    if (!userId || !userToken) {
      setMineHint(_t('填好右侧的账号凭据后即可查看自己的帖子'), true);
      return;
    }
    if (!appIdInput.value.trim() || !appSecretInput.value.trim()) {
      setMineHint(_t('请先填写接入鉴权的 APPID / APPSECRET'), true);
      return;
    }
    setMineHint(_t('加载中…'), false);
    mineList.innerHTML = '';
    apiCall('GET', '/api/haijiao/topic/mine', {
      status: mineStatus, page: String(page), user_id: userId, user_token: userToken,
    }).then(function (res) {
      var data = unwrap(res);
      minePage = data.pagination.page;
      mineTotalPage = data.pagination.total_page || 1;
      mineList.innerHTML = '';
      if (!data.results.length) {
        mineList.appendChild(el('div',
          'rounded-box border border-dashed border-base-300 p-4 text-center text-xs text-base-content/50',
          _t('这里还没有帖子')));
      } else {
        data.results.forEach(function (item) { mineList.appendChild(mineItemNode(item)); });
      }
      setMineHint(_ti('共 %(n)s 条', { n: data.pagination.total }), false);
      minePageLabel.textContent = _ti('第 %(p)s / %(t)s 页', { p: minePage, t: mineTotalPage });
    }).catch(function (err) {
      setMineHint(_t('查询失败：') + err.message, true);
    });
  }

  mineTabs.forEach(function (btn) {
    btn.addEventListener('click', function () {
      mineTabs.forEach(function (b) { b.classList.remove('tab-active'); });
      btn.classList.add('tab-active');
      mineStatus = btn.dataset.mineStatus;
      loadMine(1);
    });
  });
  document.querySelector('[data-mine-refresh]').addEventListener('click', function () { loadMine(minePage); });
  document.querySelector('[data-mine-prev]').addEventListener('click', function () {
    if (minePage > 1) loadMine(minePage - 1);
  });
  document.querySelector('[data-mine-next]').addEventListener('click', function () {
    if (minePage < mineTotalPage) loadMine(minePage + 1);
  });

  loadNodes();
  loadMine(1);
})();
