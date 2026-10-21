/* 官网 - 声音上传：网页录音
 *
 * 流程：getUserMedia 取麦克风 → MediaRecorder 录制 → 停止后本地试听 →
 *      POST /upload/record/upload/（官网会话 + CSRF，服务端复用 save_voice 校验）。
 *
 * 关键约定：
 *   1) 录音格式按浏览器能力挑（优先 MP4/AAC，Chrome 126+ / Safari 支持；
 *      不支持的浏览器回退 WebM/OGG），扩展名由实际 mimeType 决定，
 *      服务端白名单与魔数校验都认这些格式；
 *   2) 前端计时只用于展示与「到 60 秒自动停」，最终时长以服务端 ffprobe 为准；
 *   3) 录音必须是 HTTPS 或 localhost（浏览器安全上下文限制），否则直接提示；
 *   4) 录音文件仅在本机内存里，点「上传」后才发送。
 */
(function () {
  'use strict';

  var root = document.getElementById('voice-recorder');
  if (!root) return;

  var MIN = parseInt(root.getAttribute('data-min'), 10) || 3;
  var MAX = parseInt(root.getAttribute('data-max'), 10) || 60;
  var MAX_SIZE_MB = parseInt(root.getAttribute('data-max-size'), 10) || 20;
  var UPLOAD_URL = root.getAttribute('data-upload-url') || '';

  function _t(s) {
    return (typeof window.gettext === 'function') ? window.gettext(s) : s;
  }

  var els = {
    dot: root.querySelector('[data-state-dot]'),
    state: root.querySelector('[data-state-text]'),
    timer: root.querySelector('[data-timer]'),
    progress: root.querySelector('[data-progress]'),
    level: root.querySelector('[data-level]'),
    start: root.querySelector('[data-start]'),
    stop: root.querySelector('[data-stop]'),
    hint: root.querySelector('[data-hint]'),
    preview: root.querySelector('[data-preview]'),
    audio: root.querySelector('[data-audio]'),
    meta: root.querySelector('[data-meta]'),
    actions: root.querySelector('[data-actions]'),
    reset: root.querySelector('[data-reset]'),
    submit: root.querySelector('[data-submit]'),
    alert: root.querySelector('[data-alert]'),
    unsupported: root.querySelector('[data-unsupported]')
  };
  var result = {
    box: document.querySelector('[data-result]'),
    audio: document.querySelector('[data-result-audio]'),
    url: document.querySelector('[data-result-url]'),
    copy: document.querySelector('[data-copy]'),
    open: document.querySelector('[data-result-open]'),
    meta: document.querySelector('[data-result-meta]')
  };

  var recorder = null;
  var stream = null;
  var chunks = [];
  var blob = null;
  var ext = 'webm';
  var objectUrl = '';
  var startedAt = 0;
  var elapsed = 0;
  var ticker = null;
  var uploading = false;
  var audioCtx = null;
  var levelTimer = null;
  var peakLevel = 0;
  var meterWorked = false;

  function pad(n) { return (n < 10 ? '0' : '') + n; }

  function fmt(sec) {
    sec = Math.max(0, Math.round(sec));
    return pad(Math.floor(sec / 60)) + ':' + pad(sec % 60);
  }

  function humanSize(bytes) {
    if (bytes >= 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + 'MB';
    if (bytes >= 1024) return (bytes / 1024).toFixed(0) + 'KB';
    return bytes + 'B';
  }

  function csrfToken() {
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input && input.value) return input.value;
    var m = document.cookie.match(/(?:^|;\s*)(?:xyapi_csrftoken|csrftoken)=([^;\s]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  function setState(text, kind) {
    els.state.textContent = text;
    els.dot.className = 'status ' + (kind || 'status-neutral');
  }

  function showAlert(msg) {
    els.alert.textContent = msg;
    els.alert.classList.remove('hidden');
  }

  function clearAlert() {
    els.alert.textContent = '';
    els.alert.classList.add('hidden');
  }

  function setRecording(flag) {
    els.start.classList.toggle('hidden', flag);
    els.stop.classList.toggle('hidden', !flag);
  }

  function renderTimer() {
    els.timer.textContent = fmt(elapsed);
    els.progress.value = Math.min(elapsed, MAX);
  }

  function micError(err) {
    var name = (err && err.name) || '';
    if (name === 'NotAllowedError' || name === 'SecurityError') {
      return _t('麦克风权限被拒绝：请点地址栏左侧的权限图标，把麦克风改为「允许」后重试。');
    }
    if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
      return _t('没有找到可用的麦克风，请检查设备是否已连接。');
    }
    if (name === 'NotReadableError' || name === 'TrackStartError') {
      return _t('麦克风正被其它程序占用，请关闭占用它的程序后重试。');
    }
    return _t('无法打开麦克风，请检查系统录音权限后重试。');
  }

  function extOfMime(mime) {
    mime = String(mime || '').toLowerCase();
    if (mime.indexOf('mp4') >= 0 || mime.indexOf('m4a') >= 0) return 'm4a';
    if (mime.indexOf('ogg') >= 0) return 'ogg';
    if (mime.indexOf('mpeg') >= 0) return 'mp3';
    return 'webm';
  }

  function createRecorder(source) {
    // 优先 MP4/AAC：Chrome 126+ 与 Safari 都支持，录音自带时长元数据，
    // <audio> 试听与上传后的在线播放都最稳；不支持的浏览器回退 WebM/Opus
    //（服务端会把 WebM 转成 mp3）。
    var candidates = [
      'audio/mp4;codecs=mp4a.40.2',
      'audio/mp4',
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/ogg;codecs=opus'
    ];
    for (var i = 0; i < candidates.length; i++) {
      if (typeof MediaRecorder.isTypeSupported !== 'function') break;
      if (!MediaRecorder.isTypeSupported(candidates[i])) continue;
      try {
        return new MediaRecorder(source, { mimeType: candidates[i] });
      } catch (e) {
        /* 该格式创建失败就试下一个 */
      }
    }
    return new MediaRecorder(source);
  }

  /* ---------- 输入电平：录音时实时显示，并记录峰值用于判断是否真的录到声音 ---------- */
  function startLevelMeter(source) {
    try {
      var Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      audioCtx = new Ctx();
      if (audioCtx.state === 'suspended') audioCtx.resume();
      var srcNode = audioCtx.createMediaStreamSource(source);
      var analyser = audioCtx.createAnalyser();
      analyser.fftSize = 1024;
      srcNode.connect(analyser);   // 只连分析器，不接扬声器，避免回声
      var buf = new Uint8Array(analyser.fftSize);
      peakLevel = 0;
      meterWorked = true;
      levelTimer = setInterval(function () {
        analyser.getByteTimeDomainData(buf);
        var peak = 0;
        for (var i = 0; i < buf.length; i++) {
          var v = Math.abs(buf[i] - 128);
          if (v > peak) peak = v;
        }
        if (peak > peakLevel) peakLevel = peak;
        // 语音峰值一般 20~80，放大 2 倍让电平条更直观
        els.level.value = Math.min(100, Math.round(peak / 128 * 200));
      }, 100);
    } catch (e) {
      /* 电平表不可用不影响录音本身 */
      meterWorked = false;
    }
  }

  function stopLevelMeter() {
    if (levelTimer) {
      clearInterval(levelTimer);
      levelTimer = null;
    }
    if (audioCtx) {
      try { audioCtx.close(); } catch (e) { /* ignore */ }
      audioCtx = null;
    }
    if (els.level) els.level.value = 0;
  }

  function tick() {
    elapsed = (Date.now() - startedAt) / 1000;
    if (elapsed >= MAX) {
      elapsed = MAX;
      renderTimer();
      stopRecording();
      return;
    }
    renderTimer();
  }

  function startRecording() {
    clearAlert();
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
      showAlert(_t('当前浏览器不支持网页录音，请换用新版 Chrome / Edge / Safari。'));
      return;
    }
    if (!window.isSecureContext) {
      showAlert(_t('当前页面不是 HTTPS（或 localhost），浏览器会拒绝访问麦克风。请改用 https 地址打开。'));
      return;
    }

    els.start.disabled = true;
    navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true }
    }).then(function (source) {
      stream = source;
      chunks = [];
      startLevelMeter(source);
      recorder = createRecorder(source);
      recorder.ondataavailable = function (event) {
        if (event.data && event.data.size) chunks.push(event.data);
      };
      recorder.onstop = finishRecording;
      recorder.start(200);

      startedAt = Date.now();
      elapsed = 0;
      renderTimer();
      setRecording(true);
      setState(_t('正在录音…'), 'status-error animate-pulse');
      els.hint.textContent = _t('再点一次红色按钮停止；录到 60 秒会自动停止。');
      ticker = setInterval(tick, 200);
    }).catch(function (err) {
      els.start.disabled = false;
      setState(_t('无法开始录音'), 'status-error');
      showAlert(micError(err));
    });
  }

  function stopRecording() {
    if (ticker) {
      clearInterval(ticker);
      ticker = null;
    }
    stopLevelMeter();
    if (recorder && recorder.state !== 'inactive') {
      try { recorder.stop(); } catch (e) { /* 已停止则忽略 */ }
    }
    if (stream) {
      stream.getTracks().forEach(function (track) { track.stop(); });
      stream = null;
    }
    setRecording(false);
  }

  function finishRecording() {
    var type = (recorder && recorder.mimeType) || (chunks[0] && chunks[0].type) || 'audio/webm';
    ext = extOfMime(type);
    blob = new Blob(chunks, { type: type });
    chunks = [];

    if (!blob.size) {
      blob = null;
      setState(_t('录音失败'), 'status-error');
      showAlert(_t('没有录到声音，请检查麦克风后重试。'));
      return;
    }
    if (blob.size > MAX_SIZE_MB * 1024 * 1024) {
      blob = null;
      setState(_t('录音过长'), 'status-error');
      showAlert(_t('录音文件超过大小限制，请缩短后重试。'));
      return;
    }

    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = URL.createObjectURL(blob);
    els.audio.src = objectUrl;
    els.meta.textContent =
      _t('本次录音') + ' ' + elapsed.toFixed(1) + ' ' + _t('秒') + ' · ' + humanSize(blob.size);
    els.preview.classList.remove('hidden');
    els.actions.classList.remove('hidden');
    els.start.disabled = false;
    els.hint.textContent =
      _t('确认没问题就点「上传并获取链接」；不满意可以重新录制。');

    if (elapsed + 0.05 < MIN) {
      setState(_t('录音太短'), 'status-warning');
      showAlert(_t('录音需至少 3 秒，请点「重新录制」再录长一点。'));
      els.submit.disabled = true;
    } else if (meterWorked && peakLevel < 2) {
      // 电平表一路贴着 0：多半是麦克风被静音 / 选错输入设备，录出来是静音
      setState(_t('没有检测到声音'), 'status-warning');
      showAlert(_t('录音里没有检测到声音：请检查麦克风是否被静音、系统是否选对了输入设备，然后点「重新录制」。'));
      els.submit.disabled = false;
    } else {
      setState(_t('录音完成'), 'status-success');
      clearAlert();
      els.submit.disabled = false;
    }
    renderTimer();
  }

  function resetRecorder() {
    if (ticker) {
      clearInterval(ticker);
      ticker = null;
    }
    stopLevelMeter();
    peakLevel = 0;
    meterWorked = false;
    if (recorder) {
      recorder.onstop = null;
      recorder.ondataavailable = null;
      if (recorder.state !== 'inactive') {
        try { recorder.stop(); } catch (e) { /* 忽略 */ }
      }
      recorder = null;
    }
    if (stream) {
      stream.getTracks().forEach(function (track) { track.stop(); });
      stream = null;
    }
    if (objectUrl) {
      URL.revokeObjectURL(objectUrl);
      objectUrl = '';
    }
    chunks = [];
    blob = null;
    elapsed = 0;

    els.audio.removeAttribute('src');
    els.audio.load();
    els.preview.classList.add('hidden');
    els.actions.classList.add('hidden');
    els.meta.textContent = '';
    els.start.disabled = false;
    els.submit.disabled = false;
    els.submit.classList.remove('hidden');
    els.hint.textContent =
      _t('首次使用会请求麦克风权限，请选择「允许」；录音只在你的浏览器里进行。');
    setRecording(false);
    renderTimer();
    clearAlert();
    setState(_t('准备就绪'), 'status-neutral');
  }

  function showResult(data) {
    result.url.value = data.url || '';
    result.audio.src = data.url || '';
    result.open.href = data.url || '#';

    var parts = [];
    if (data.duration != null) parts.push(_t('时长') + ' ' + Number(data.duration).toFixed(1) + ' ' + _t('秒'));
    if (data.size_mb != null) parts.push(_t('大小') + ' ' + data.size_mb + 'MB');
    result.meta.textContent = parts.join(' · ');
    result.box.classList.remove('hidden');
    if (result.box.scrollIntoView) {
      result.box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  function submitRecording() {
    if (!blob || uploading) return;
    if (elapsed + 0.05 < MIN) {
      showAlert(_t('录音需至少 3 秒，请点「重新录制」再录长一点。'));
      return;
    }

    var form = new FormData();
    form.append('file', blob, 'record_' + Date.now() + '.' + ext);

    uploading = true;
    els.submit.disabled = true;
    els.reset.disabled = true;
    setState(_t('上传中…'), 'status-info');
    clearAlert();
    var succeeded = false;

    fetch(UPLOAD_URL, {
      method: 'POST',
      headers: { 'X-CSRFToken': csrfToken() },
      body: form,
      credentials: 'same-origin'
    }).then(function (res) {
      if (res.redirected) {
        throw new Error(_t('登录状态已失效，请刷新页面重新登录。'));
      }
      return res.json().catch(function () {
        return { code: -1, msg: _t('服务返回异常，请稍后重试。') };
      });
    }).then(function (body) {
      if (!body || body.code !== 10000) {
        throw new Error((body && body.msg) || _t('上传失败，请稍后重试。'));
      }
      succeeded = true;
      setState(_t('上传成功'), 'status-success');
      // 已上传就收起提交按钮，避免同一段录音被重复上传；重新录制后可再次提交
      els.submit.classList.add('hidden');
      els.hint.textContent = _t('已上传，复制下方链接即可使用；需要新录音请点「重新录制」。');
      showResult(body.data || {});
    }).catch(function (err) {
      setState(_t('上传失败'), 'status-error');
      showAlert((err && err.message) || _t('上传失败，请稍后重试。'));
    }).then(function () {
      uploading = false;
      if (!succeeded) els.submit.disabled = false;
      els.reset.disabled = false;
    });
  }

  els.start.addEventListener('click', startRecording);
  els.stop.addEventListener('click', stopRecording);
  els.reset.addEventListener('click', resetRecorder);
  els.submit.addEventListener('click', submitRecording);
  result.copy.addEventListener('click', function () {
    if (result.url.value) XY.copy(result.url.value, result.copy);
  });

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
    els.unsupported.textContent = _t('当前浏览器不支持网页录音（缺少 MediaRecorder）。请换用新版 Chrome / Edge / Safari，或改用 API 上传音频文件。');
    els.unsupported.classList.remove('hidden');
    els.start.disabled = true;
  }

  // 离开页面时释放麦克风，避免浏览器一直显示「正在录音」
  window.addEventListener('beforeunload', function () {
    if (stream) stream.getTracks().forEach(function (track) { track.stop(); });
  });

  renderTimer();
})();
