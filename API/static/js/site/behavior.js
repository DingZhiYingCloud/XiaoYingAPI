/**
 * 行为验证 · 影子采集（小影API）
 *
 * 当前阶段只采集、不上报拦截决策：每次表单提交时把一组**聚合特征**发给
 * `POST /api/captcha_self/behavior`，后端打分并落样本，供监控面板校准阈值。
 *
 * 采集边界（隐私优先）：
 *   - 只记指针移动次数 / 总距离、击键间隔、修正次数、焦点与可见性切换次数、环境信号；
 *   - **不读取任何输入内容、不记录坐标轨迹**，键间隔最多保留 200 个；
 *   - 用 `sendBeacon` 发送，不阻塞、不影响表单提交；失败静默。
 *
 * 场景由路径推断：/login、/register、/reset-password、/feedback、其它。
 */
(function (global) {
  'use strict';

  var ENDPOINT = '/api/captcha_self/behavior';
  var MAX_INTERVALS = 200;

  var startedAt = Date.now();
  var pointerMoves = 0;
  var pointerDistance = 0;
  var lastPoint = null;
  var keyCount = 0;
  var corrections = 0;
  var intervals = [];
  var lastKeyAt = 0;
  var focusChanges = 0;
  var hiddenCount = 0;
  var userAgent = navigator.userAgent || '';

  document.addEventListener('pointermove', function (event) {
    pointerMoves += 1;
    if (lastPoint) {
      var dx = event.clientX - lastPoint.x;
      var dy = event.clientY - lastPoint.y;
      pointerDistance += Math.sqrt(dx * dx + dy * dy);
    }
    lastPoint = { x: event.clientX, y: event.clientY };
  }, { passive: true, capture: true });

  document.addEventListener('keydown', function (event) {
    keyCount += 1;
    var now = Date.now();
    if (lastKeyAt) {
      if (intervals.length < MAX_INTERVALS) { intervals.push(now - lastKeyAt); }
      else { intervals[intervals.length - 1] = now - lastKeyAt; }
    }
    lastKeyAt = now;
    if (event.key === 'Backspace' || event.key === 'Delete') { corrections += 1; }
  }, true);

  global.addEventListener('blur', function () { focusChanges += 1; });

  document.addEventListener('visibilitychange', function () {
    if (document.hidden) { hiddenCount += 1; }
  });

  function scene() {
    var path = global.location.pathname || '';
    if (path.indexOf('/register') === 0) { return 'register'; }
    if (path.indexOf('/reset-password') === 0) { return 'reset'; }
    if (path.indexOf('/feedback') === 0) { return 'feedback'; }
    if (path.indexOf('/login') === 0) { return 'login'; }
    return 'other';
  }

  /** 当前页面的聚合特征（调试时可直接调用查看） */
  function snapshot() {
    return {
      dwell_ms: Date.now() - startedAt,
      pointer_moves: pointerMoves,
      pointer_distance: Math.round(pointerDistance),
      key_count: keyCount,
      key_intervals: intervals.slice(-MAX_INTERVALS),
      key_corrections: corrections,
      focus_changes: focusChanges,
      hidden_count: hiddenCount,
      webdriver: !!navigator.webdriver,
      ua_headless: /HeadlessChrome|PhantomJS|SlimerJS/i.test(userAgent),
      timezone_offset: new Date().getTimezoneOffset()
    };
  }

  /** 上报一次（影子模式：失败静默，不影响业务） */
  function send() {
    var body = JSON.stringify({ scene: scene(), features: snapshot() });
    try {
      if (navigator.sendBeacon) {
        var blob = new Blob([body], { type: 'application/json' });
        if (navigator.sendBeacon(ENDPOINT, blob)) { return; }
      }
      fetch(ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: body,
        keepalive: true,
        credentials: 'same-origin'
      }).catch(function () { /* 影子采集：失败忽略 */ });
    } catch (error) {
      /* 影子采集：失败忽略 */
    }
  }

  // 捕获阶段监听：先于业务脚本的 submit 处理（业务脚本通常会 preventDefault）
  document.addEventListener('submit', send, true);

  global.XYBehavior = { snapshot: snapshot, send: send, scene: scene };
})(window);
