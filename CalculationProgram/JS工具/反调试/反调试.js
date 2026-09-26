/**
 * 反调试（客户端 JS）
 * ----------------------------------------------------------------------------
 * 立即执行（IIFE），不需要等到被调用：加载时先同步自检一次（早于页面渲染与业务放行），
 * 之后按固定间隔复检；一旦命中（正在被调试 / 控制台在渲染日志 / 关键原生函数被替换或包装），
 * 就进入 debugger 心跳，并对业务层持续返回「不通过」。
 *
 * ── 设计要点 ──
 * 1) 难被"基本手段"绕开：
 *    · 出厂原生引用：检测与自身循环全部使用加载瞬间捕获的原生函数。替换或删除
 *      window.setTimeout / setInterval / console.log / performance.now / document.createElement
 *      既绕不过检测（身份比对），也停不掉循环（循环不读全局）。
 *    · 身份校验为主：比对"引用是否还是出厂那一个"，不看字符串 —— 伪造
 *      Function.prototype.toString 的返回串无效；另按轮次抽检"实现字符串"，
 *      用于发现"本脚本加载之前就已被 hook"的情况。
 *    · 接口防改写：antiDebugCheck / stopAntiDebug 以不可写、不可配置方式挂在 window 上，
 *      禁止 "window.antiDebugCheck = () => true" 这类把业务放行前置架空的写法。
 *    · debugger 语句每次动态生成（带随机后缀）："不在此处停留 / 忽略此脚本"拉黑的是上一个
 *      脚本，下一次又是新脚本，一次点不掉。
 * 2) 不卡死页面：
 *    · 心跳是按需的 —— 真被暂停时立刻再拦（按继续就再停）；没被暂停时（如全局停用了断点）
 *      退避成低频心跳，不再以最快速率空转，CPU 不会被吃满，标签页始终可响应。
 *    · 每轮检测只有常数级工作：几次引用比对 +（每 5 轮）几次正则 + 一条极小的动态函数，
 *      不产生 DOM 改动、不发网络请求。
 *
 * ── 对外接口（只这两个，均为只读属性）──
 * window.antiDebugCheck()  同步复检，返回 true / false；**业务放行前必须调用**，false 时不允许放行
 * window.stopAntiDebug()   只"静音"debugger 心跳（页面恢复可操作，方便自己人排查），
 *                          **不放行**：命中过之后 antiDebugCheck() 仍然返回 false。
 *                          要彻底不拦，就别引入本脚本（或在本地副本上改）。
 *
 * ── 检测手段 ──
 * 1. debugger 计时：执行一条动态生成的 debugger 语句，真被暂停则耗时必然异常变长；
 *    performance.now 与 Date.now 双时钟取大者，单一计时器被替换也能测出。
 * 2. 控制台探针：给临时元素挂 id getter 再 console.log，只有控制台真的在渲染这个对象时
 *    才会触发 getter；不依赖暂停，因此"停用断点"之类的开关绕不过它。
 * 3. 原生函数身份 / 实现校验：替换或包装 setInterval、setTimeout、performance.now、Date.now、
 *    console.log、document.createElement、Object.defineProperty、Function、
 *    Function.prototype.toString 中的任意一个即命中。
 *    注意：Zone.js、部分埋点 SDK 与安全类扩展也会包装这些函数，可能误判 —— 这类页面请先实测；
 *    误判时可用 stopAntiDebug() 静音心跳（但业务层仍视为未通过，需你自行决定是否放行）。
 *
 * ── 必须清楚的局限 ──
 * 纯客户端手段只能提高分析成本，不能阻止抓源码 / 代理改包 / 无调试器环境；
 * 若攻击者把所有断点全局停用（Chrome 的 Ctrl+F8）且始终不切到 Console 面板，
 * 脚本无法强迫调试器暂停 —— 此时仍能拦住"放行"（业务复检恒为 false），但拦不住他阅读已下发的代码。
 */
(() => {
  'use strict';

  // ── 0. 出厂原生引用：检测与自身循环全部走这里，避免"替换全局"既绕不过也停不掉 ──
  const _setTimeout = window.setTimeout;
  const _setInterval = window.setInterval;
  const _perfNow = performance.now;
  const _dateNow = Date.now;
  const _consoleLog = console.log;
  const _createElement = document.createElement;
  const _defineProperty = Object.defineProperty;
  const _toString = Function.prototype.toString;
  const _Function = Function;

  // 拼接出 debugger 关键字，避免源码里出现完整字面量被静态扫描命中
  const BREAK = ['debu', 'gger'].join('');

  const CHECK_INTERVAL = 1000;   // 复检间隔（毫秒）
  const PAUSE_THRESHOLD = 200;   // 单次 debugger 耗时超过该值，即认定"正在被调试"（毫秒）
  const TRAP_PAUSE_DELAY = 0;    // 心跳：确实被暂停时下一次的间隔 —— 0 = 按继续立刻再拦
  const TRAP_IDLE_DELAY = 1000;  // 心跳：命中但没被暂停时（如断点被全局停用）的退避间隔，防空转吃满 CPU
  const SOURCE_CHECK_EVERY = 5;  // 每 N 轮复检做一次"实现字符串"校验（引用比对每轮都做，更省也更准）

  let muted = false;    // stopAntiDebug() 置位：只静音心跳，不改变检测结论
  let trapped = false;  // 是否已命中；一旦命中就保持，antiDebugCheck() 从此恒为 false
  let ticks = 0;        // 已复检轮次

  /** 只静音 debugger 心跳（页面恢复可操作）；不清理复检、不放行 —— 见文件头说明 */
  function stopAntiDebug() {
    muted = true;
  }

  /** 动态生成一条 debugger 语句并执行（带随机后缀，"不在此处停留"无法永久拉黑） */
  function pause() {
    try {
      _Function(BREAK + '//' + Math.random())();
    } catch (e) {
      // CSP 等环境禁用了 eval 类构造：本手段自然失效，交给其余手段兜底，
      // 不能让异常把后续检测一并打断
    }
  }

  /** 手段 1：靠 debugger 的阻塞耗时判断是否处于暂停状态 */
  function paused() {
    // 双时钟取大者：performance.now / Date.now 任一被换掉或静止，另一个仍能测出耗时
    const startP = _perfNow.call(performance);
    const startD = _dateNow();
    pause();
    return _perfNow.call(performance) - startP > PAUSE_THRESHOLD ||
      _dateNow() - startD > PAUSE_THRESHOLD;
  }

  /** 手段 2：控制台探针，判断控制台是否在渲染日志（不依赖暂停） */
  function consoleOpened() {
    let opened = false;
    const decoy = _createElement.call(document, 'div');
    _defineProperty(decoy, 'id', {
      get() { opened = true; return ''; },
      configurable: true,
    });
    _consoleLog.call(console, decoy);
    return opened;
  }

  /** 实现字符串校验：用于发现"本脚本加载之前就已被 hook"的情况 */
  function nativeCode(fn) {
    return typeof fn === 'function' && /\{\s*\[native code\]\s*\}/.test(_toString.call(fn));
  }

  /** 手段 3：原生函数被替换 / 包装即命中（身份比对为主，字符串抽检为辅） */
  function tampered() {
    if (window.setTimeout !== _setTimeout) return true;
    if (window.setInterval !== _setInterval) return true;
    if (performance.now !== _perfNow) return true;
    if (Date.now !== _dateNow) return true;
    if (console.log !== _consoleLog) return true;
    if (document.createElement !== _createElement) return true;
    if (Object.defineProperty !== _defineProperty) return true;
    if (Function.prototype.toString !== _toString) return true;
    if (Function !== _Function) return true;
    if (ticks % SOURCE_CHECK_EVERY === 0) {
      return !(nativeCode(_setTimeout) && nativeCode(_setInterval) &&
        nativeCode(_perfNow) && nativeCode(_consoleLog) && nativeCode(_toString));
    }
    return false;
  }

  /**
   * 同步复检一次，并把结论提供给业务层。
   * @returns {boolean} true = 通过（没被调试、关键原生函数没被替换）；false = 命中，不应放行
   */
  function antiDebugCheck() {
    if (trapped) return false;   // 命中过就一直拦（muted 也一样，这是刻意的）

    const hit = tampered() || paused() || consoleOpened();
    ticks += 1;

    if (hit) {
      trapped = true;
      startTrap();   // 只在这里启动一次心跳
      return false;
    }
    return true;
  }

  /** debugger 心跳：真被暂停 → 立刻再拦；没被暂停 → 退避成低频，避免空转把页面 CPU 打满 */
  function startTrap() {
    if (muted) return;           // 已被 stopAntiDebug() 静音：停止骚扰，但 trapped 仍为 true
    const didPause = paused();
    // 用捕获的原生 setTimeout 重排：外部替换 window.setTimeout 停不掉这个循环
    _setTimeout.call(window, startTrap, didPause ? TRAP_PAUSE_DELAY : TRAP_IDLE_DELAY);
  }

  // 对外接口：不可写、不可配置 —— 防"window.antiDebugCheck = () => true"把业务放行前置架空
  try {
    _defineProperty(window, 'antiDebugCheck', {
      value: antiDebugCheck, writable: false, configurable: false,
    });
    _defineProperty(window, 'stopAntiDebug', {
      value: stopAntiDebug, writable: false, configurable: false,
    });
  } catch (e) {
    // 重复引入（属性已被上一次定义为不可配置）或环境不支持：退化为"缺啥补啥"，
    // 不能让异常打断下面的自检与复检
    try {
      if (!window.antiDebugCheck) { window.antiDebugCheck = antiDebugCheck; }
      if (!window.stopAntiDebug) { window.stopAntiDebug = stopAntiDebug; }
    } catch (e2) {
      // 已有同名只读属性：保留现状，继续跑检测
    }
  }

  // ① 加载即自检：必须早于页面渲染与业务放行
  antiDebugCheck();

  // ② 持续复检：兜住"页面打开之后才打开控制台"的情况
  //    stopAntiDebug() 之后这条复检**依然运行**（否则"先静音再开控制台"就绕过了），
  //    命中后 antiDebugCheck() 会在第 3 行直接短路返回，开销近似为 0。
  _setInterval.call(window, antiDebugCheck, CHECK_INTERVAL);
})();
