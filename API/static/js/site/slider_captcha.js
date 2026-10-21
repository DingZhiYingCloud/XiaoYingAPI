/* 官网 - 自研滑块验证码演示页
 *
 * 流程：GET /api/captcha_self/slider/generate 拿背景图 + 拼图块 →
 *      用户按住滑块拖动 → POST /api/captcha_self/slider/verify 提交位置与轨迹。
 *
 * 关键约定：
 *   1) 服务端不返回缺口横坐标，只返回拼图块纵坐标；横坐标必须由用户拖出来；
 *   2) 提交的 x 是「画布坐标」（0..width-piece），不是屏幕像素 —— 页面响应式缩放时
 *      按 stage 实际显示宽度换算；
 *   3) 轨迹格式 [{"x":画布坐标,"t":相对毫秒}]，服务端会校验点数 / 时长 / 时间单调 / 终点；
 *   4) 每次挑战只能校验一次，失败后自动换一张。
 */
(function () {
  'use strict';

  var root = document.getElementById('slider-captcha');
  if (!root) return;

  var generateUrl = root.getAttribute('data-generate-url') || '';
  var verifyUrl = root.getAttribute('data-verify-url') || '';

  var stage = root.querySelector('[data-stage]');
  var background = root.querySelector('[data-background]');
  var piece = root.querySelector('[data-piece]');
  var track = root.querySelector('[data-track]');
  var fill = root.querySelector('[data-fill]');
  var hint = root.querySelector('[data-track-hint]');
  var handle = root.querySelector('[data-handle]');

  var alertBox = document.querySelector('[data-alert]');
  var statusEl = document.querySelector('[data-status]');
  var refreshBtn = document.querySelector('[data-refresh]');

  function _t(s) {
    return (typeof window.gettext === 'function') ? window.gettext(s) : s;
  }

  function csrfToken() {
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input && input.value) return input.value;
    var m = document.cookie.match(/(?:^|;\s*)(?:xyapi_csrftoken|csrftoken)=([^;\s]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
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
    sliderId: '',
    width: 320,
    height: 160,
    pieceSize: 52,
    loaded: false
  };
  var drag = null;
  var busy = false;

  // 轨迹最多记 200 个点（服务端留到 2000 只防超大 payload）：
  // 60Hz 下拖 10 秒会产生 600 个点，不节流会被自己拒绝
  var MAX_TRACK_POINTS = 200;

  function resetDrag() {
    if (drag) drag = null;
    piece.style.left = '0';
    handle.style.left = '0';
    fill.style.width = '0';
    hint.classList.remove('hidden');
    handle.classList.remove('btn-success');
  }

  function loadChallenge() {
    if (busy) return;
    busy = true;
    state.loaded = false;
    resetDrag();
    setAlert('', '');
    setStatus(_t('加载中…'));

    fetch(generateUrl, { credentials: 'same-origin' })
      .then(function (res) { return res.json(); })
      .then(function (body) {
        if (!body || body.code !== 10000 || !body.data) {
          throw new Error((body && body.msg) || _t('加载失败，请重试'));
        }
        var data = body.data;
        state.sliderId = data.slider_id;
        state.width = Number(data.width) || 320;
        state.height = Number(data.height) || 160;
        state.pieceSize = Number(data.piece_size) || 52;

        background.src = data.background;
        piece.src = data.piece;
        piece.style.width = (state.pieceSize / state.width * 100) + '%';
        piece.style.top = (Number(data.piece_y) / state.height * 100) + '%';
        piece.classList.remove('hidden');

        state.loaded = true;
        busy = false;
        setStatus(_t('拖动滑块完成拼图'));
      })
      .catch(function (err) {
        busy = false;
        setStatus(_t('加载失败'));
        setAlert((err && err.message) || _t('加载失败，请重试'), 'error');
      });
  }

  function maxDrag() {
    return Math.max(1, track.clientWidth - handle.offsetWidth);
  }

  function maxImageX() {
    return Math.max(1, state.width - state.pieceSize);
  }

  function render(imageX, dx) {
    piece.style.left = (imageX / state.width * 100) + '%';
    handle.style.left = dx + 'px';
    fill.style.width = (dx + handle.offsetWidth) + 'px';
    hint.classList.add('hidden');
  }

  handle.addEventListener('pointerdown', function (event) {
    if (busy || !state.loaded) return;
    event.preventDefault();
    try { handle.setPointerCapture(event.pointerId); } catch (e) { /* ignore */ }
    drag = {
      startClientX: event.clientX,
      maxDrag: maxDrag(),
      maxImageX: maxImageX(),
      imageX: 0,
      startTime: (window.performance && performance.now) ? performance.now() : Date.now(),
      points: [{ x: 0, t: 0 }]
    };
    setAlert('', '');
    setStatus(_t('拖动中…'));
  });

  handle.addEventListener('pointermove', function (event) {
    if (!drag) return;
    event.preventDefault();
    var dx = clamp(event.clientX - drag.startClientX, 0, drag.maxDrag);
    var imageX = dx / drag.maxDrag * drag.maxImageX;
    drag.imageX = imageX;
    render(imageX, dx);

    var now = (window.performance && performance.now) ? performance.now() : Date.now();
    var t = Math.round(now - drag.startTime);
    var last = drag.points[drag.points.length - 1];
    if (drag.points.length < MAX_TRACK_POINTS) {
      // 采样节流：50ms 或位移 ≥2px 才记一个点
      if (t - last.t >= 50 || Math.abs(imageX - last.x) >= 2) {
        drag.points.push({ x: Math.round(imageX * 10) / 10, t: t });
      }
    } else {
      // 点数已满：只移动最后一个点，保证终点位置 / 时间仍然准确
      last.x = Math.round(imageX * 10) / 10;
      last.t = t;
    }
  });

  function finishDrag(event) {
    if (!drag) return;
    if (event) event.preventDefault();
    var current = drag;
    drag = null;

    var now = (window.performance && performance.now) ? performance.now() : Date.now();
    current.points.push({
      x: Math.round(current.imageX * 10) / 10,
      t: Math.round(now - current.startTime)
    });
    submit(current.imageX, current.points);
  }

  handle.addEventListener('pointerup', finishDrag);
  handle.addEventListener('pointercancel', function () {
    drag = null;
  });

  function submit(imageX, points) {
    if (!state.sliderId || busy) return;
    busy = true;
    state.loaded = false;
    setStatus(_t('校验中…'));

    var body = new URLSearchParams();
    body.append('slider_id', state.sliderId);
    body.append('x', imageX.toFixed(1));
    body.append('track', JSON.stringify(points));

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
    }).then(function (body) {
      if (body && body.code === 10000 && body.data && body.data.passed) {
        busy = false;
        setAlert(_t('验证通过'), 'success');
        setStatus(_t('验证通过'));
        handle.classList.add('btn-success');
        // 挑战已消费，展示成功状态后自动换一张
        setTimeout(loadChallenge, 2500);
        return;
      }
      throw new Error((body && body.msg) || _t('验证失败，请重试'));
    }).catch(function (err) {
      busy = false;
      setAlert((err && err.message) || _t('验证失败，请重试'), 'error');
      setStatus(_t('验证失败，正在换一张…'));
      setTimeout(loadChallenge, 1200);
    });
  }

  if (refreshBtn) {
    refreshBtn.addEventListener('click', function () {
      if (busy) return;
      loadChallenge();
    });
  }

  loadChallenge();
})();
