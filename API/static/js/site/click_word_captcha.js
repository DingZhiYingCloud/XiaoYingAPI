/* 官网 - 自研汉字点选验证码演示页
 *
 * 流程：GET /api/captcha_self/click/generate 拿图片与目标字 →
 *      用户按顺序点击图片 → 点够目标数 POST /api/captcha_self/click/verify。
 *
 * 关键约定：
 *   1) 服务端只返回目标字文本，不返回坐标；点击点按画布坐标提交（响应式缩放时换算）；
 *   2) 点击点格式 [{"x":画布x,"y":画布y,"t":相对毫秒}]，t 以第一次点击为 0；
 *   3) 每次挑战只能校验一次，失败后自动换一张。
 */
(function () {
  'use strict';

  var root = document.getElementById('click-captcha');
  if (!root) return;

  var generateUrl = root.getAttribute('data-generate-url') || '';
  var verifyUrl = root.getAttribute('data-verify-url') || '';

  var charsEl = root.querySelector('[data-chars]');
  var stage = root.querySelector('[data-stage]');
  var image = root.querySelector('[data-image]');
  var progressEl = root.querySelector('[data-progress]');
  var undoBtn = root.querySelector('[data-undo]');
  var refreshBtn = root.querySelector('[data-refresh]');

  var alertBox = document.querySelector('[data-alert]');
  var statusEl = document.querySelector('[data-status]');

  function _t(s) {
    return (typeof window.gettext === 'function') ? window.gettext(s) : s;
  }

  function csrfToken() {
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input && input.value) return input.value;
    var m = document.cookie.match(/(?:^|;\s*)(?:xyapi_csrftoken|csrftoken)=([^;\s]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  function setAlert(msg, kind) {
    if (!alertBox) return;
    alertBox.textContent = msg || '';
    alertBox.className = 'alert w-full text-sm ' + (msg ? '' : 'hidden ') +
      (kind === 'success' ? 'alert-success' : kind === 'info' ? 'alert-info' : 'alert-error');
    if (!msg) alertBox.classList.add('hidden');
  }

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text;
  }

  var state = {
    challengeId: '',
    width: 360,
    height: 200,
    count: 0,
    points: [],
    startTime: 0,
    loaded: false
  };
  var busy = false;
  var markers = [];

  function clearMarkers() {
    markers.forEach(function (mark) { mark.remove(); });
    markers = [];
  }

  function updateProgress() {
    if (progressEl) progressEl.textContent = state.points.length + ' / ' + state.count;
    undoBtn.disabled = busy || !state.points.length;
  }

  function resetClicks() {
    state.points = [];
    state.startTime = 0;
    clearMarkers();
    updateProgress();
  }

  function renderChars(chars) {
    charsEl.textContent = '';
    chars.forEach(function (char, index) {
      if (index > 0) {
        var arrow = document.createElement('span');
        arrow.className = 'mx-1 text-base-content/40';
        arrow.textContent = '→';
        charsEl.appendChild(arrow);
      }
      var badge = document.createElement('span');
      badge.className = 'badge badge-primary badge-sm';
      badge.textContent = char;
      charsEl.appendChild(badge);
    });
  }

  function loadChallenge() {
    if (busy) return;
    busy = true;
    state.loaded = false;
    resetClicks();
    setAlert('', '');
    setStatus(_t('加载中…'));
    charsEl.textContent = _t('加载中…');

    fetch(generateUrl, { credentials: 'same-origin' })
      .then(function (res) { return res.json(); })
      .then(function (body) {
        if (!body || body.code !== 10000 || !body.data) {
          throw new Error((body && body.msg) || _t('加载失败，请重试'));
        }
        var data = body.data;
        state.challengeId = data.challenge_id;
        state.width = Number(data.width) || 360;
        state.height = Number(data.height) || 200;
        state.count = Number(data.count) || (data.chars ? data.chars.length : 0);
        image.src = data.image;
        renderChars(data.chars || []);

        state.loaded = true;
        busy = false;
        updateProgress();
        setStatus(_t('请按顺序点击图片中的汉字'));
      })
      .catch(function (err) {
        busy = false;
        charsEl.textContent = '-';
        setStatus(_t('加载失败'));
        setAlert((err && err.message) || _t('加载失败，请重试'), 'error');
      });
  }

  function addMarker(x, y, index) {
    var mark = document.createElement('span');
    mark.className = 'badge badge-primary badge-sm';
    mark.style.position = 'absolute';
    mark.style.left = (x / state.width * 100) + '%';
    mark.style.top = (y / state.height * 100) + '%';
    mark.style.transform = 'translate(-50%, -50%)';
    mark.style.pointerEvents = 'none';
    mark.textContent = String(index);
    stage.appendChild(mark);
    markers.push(mark);
  }

  stage.addEventListener('click', function (event) {
    if (busy || !state.loaded) return;
    if (state.points.length >= state.count) return;

    var rect = image.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    var x = (event.clientX - rect.left) / rect.width * state.width;
    var y = (event.clientY - rect.top) / rect.height * state.height;
    if (x < 0 || y < 0 || x > state.width || y > state.height) return;

    var now = (window.performance && performance.now) ? performance.now() : Date.now();
    if (!state.points.length) state.startTime = now;
    var t = Math.round(now - state.startTime);

    state.points.push({
      x: Math.round(x * 10) / 10,
      y: Math.round(y * 10) / 10,
      t: t
    });
    addMarker(x, y, state.points.length);
    updateProgress();

    if (state.points.length >= state.count) submit();
  });

  function undo() {
    if (busy || !state.points.length) return;
    state.points.pop();
    var mark = markers.pop();
    if (mark) mark.remove();
    updateProgress();
  }

  function submit() {
    if (!state.challengeId || busy) return;
    busy = true;
    state.loaded = false;
    setStatus(_t('校验中…'));
    updateProgress();

    var body = new URLSearchParams();
    body.append('challenge_id', state.challengeId);
    body.append('points', JSON.stringify(state.points));

    fetch(verifyUrl, {
      method: 'POST',
      headers: {
        'X-CSRFToken': csrfToken(),
        'Content-Type': 'application/x-www-form-urlencoded'
      },
      body: body,
      credentials: 'same-origin'
    }).then(function (res) {
      return res.json().catch(function () {
        return { code: -1, msg: _t('服务返回异常，请稍后重试。') };
      });
    }).then(function (result) {
      if (result && result.code === 10000 && result.data && result.data.passed) {
        busy = false;
        setAlert(_t('验证通过'), 'success');
        setStatus(_t('验证通过'));
        setTimeout(loadChallenge, 2500);
        return;
      }
      throw new Error((result && result.msg) || _t('验证失败，请重试'));
    }).catch(function (err) {
      busy = false;
      setAlert((err && err.message) || _t('验证失败，请重试'), 'error');
      setStatus(_t('验证失败，正在换一张…'));
      setTimeout(loadChallenge, 1200);
    });
  }

  undoBtn.addEventListener('click', undo);
  refreshBtn.addEventListener('click', function () {
    if (!busy) loadChallenge();
  });

  loadChallenge();
})();
