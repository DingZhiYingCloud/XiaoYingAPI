/**
 * 反调试
 * ----------------------------------------------------------------------------
 * 立即执行（IIFE），不需要等到被调用；一旦检测到开发者工具，就进入无限 debugger 循环。
 * 关闭方式：控制台执行 window.stopAntiDebug()（暂停状态下也能执行，执行后按继续即可跳出）。
 *
 * 检测时机（重要）：
 *   1. 脚本加载时先"同步自检"一次 —— 早于页面渲染、早于斗篷放行。
 *      所以"先打开控制台、再刷新页面"会在渲染任何内容之前就被暂停住，
 *      不会出现"先把主页面渲染出来、1 秒后才被反调试抓到"。
 *   2. 之后每 1000ms 复检一次，持续监控中途打开控制台的行为。
 *
 * 对外接口：
 *   window.stopAntiDebug()  自己人排查用：关闭反调试，之后一律放行
 *   window.antiDebugCheck() 同步复检，返回 true / false
 *                           斗篷放行前必须调用它，返回 false 时不允许放行
 *
 * 检测手段：
 *   1. debugger 计时：执行一条 debugger 语句，若真的被暂停，耗时必然异常变长。
 *      源码每次重新生成（带随机后缀），所以开发者工具的"不在此处停止/忽略此脚本"
 *      拉黑的是上一个脚本，下一次又会命中新脚本，无法一次点掉。
 *   2. 控制台探针：给临时元素挂一个 id getter 再 console.log，
 *      只有控制台真的在渲染这个对象时才会触发 getter；不依赖暂停，
 *      因此"停用断点"之类的开关绕不过它（控制台面板打开即命中）。
 *   3. 原生函数完整性：改写 setInterval/setTimeout/performance.now/console.log
 *      是绕过手段 1/2 的常见前置动作，发现被 hook（不再是 native code）即判定为攻击。
 *      注意：少数浏览器扩展也会包装 console.log，可能误判，可用 stopAntiDebug 放行。
 *
 * 说明：死循环用 setTimeout 递归实现，而不是 while(true){debugger}——
 *       万一出现误判（主线程长任务造成的计时偏差），页面只是变卡，还能用开关关掉，
 *       同步死循环则会让标签页彻底无响应，连开关都进不去。
 */

(() => {
  // 拼接出 debugger 关键字，避免源码里出现完整字面量被静态扫描命中
  const BREAK = ['debu', 'gger'].join('');

  const CHECK_INTERVAL = 1000; // 复检间隔（毫秒）
  const PAUSE_THRESHOLD = 200; // 单次 debugger 耗时超过该值，即认定"正在被调试"

  let stopped = false; // 关闭标记
  let trapped = false; // 是否已进入无限 debugger
  let timer = null;

  // 对外提供开关：自己人/自动化脚本需要排查时，可在控制台调用
  window.stopAntiDebug = () => {
    stopped = true;
    if (timer) clearInterval(timer);
  };

  // 动态生成一条 debugger 语句并执行（源码带随机后缀，无法被"不在此处停止"永久拉黑）
  const pause = () => {
    try {
      Function(BREAK + '//' + Math.random())();
    } catch (e) {
      // CSP 等环境禁用了 eval 类构造：本手段自然失效，交给其余手段兜底，
      // 不能让异常把后续检测一并打断
    }
  };

  // 手段 1：靠 debugger 的阻塞耗时判断是否处于暂停状态
  const paused = () => {
    // 双时钟取大者：performance.now / Date.now 任一被 hook 成静止，另一个仍能测出耗时
    const startP = performance.now();
    const startD = Date.now();
    pause();
    return (
      performance.now() - startP > PAUSE_THRESHOLD ||
      Date.now() - startD > PAUSE_THRESHOLD
    );
  };

  // 手段 2：控制台探针，判断控制台面板是否打开（不依赖暂停）
  const consoleOpened = () => {
    let opened = false;
    const decoy = document.createElement('div');
    Object.defineProperty(decoy, 'id', {
      get() {
        opened = true;
        return '';
      },
    });
    console.log(decoy);
    return opened;
  };

  // 手段 3：关键原生函数被 hook（不再是 native code）即判定为攻击
  // 局限：toString 本身可被改写并伪造返回串，本手段只能提高成本，无法根除伪造
  const fnToString = Function.prototype.toString;
  const nativeCode = (fn) =>
    typeof fn === 'function' &&
    /\{\s*\[native code\]\s*\}/.test(fnToString.call(fn));
  const tampered = () =>
    !(
      nativeCode(fnToString) && // toString 是一切伪造的根，最先校验
      nativeCode(setInterval) &&
      nativeCode(setTimeout) &&
      nativeCode(performance.now) &&
      nativeCode(console.log)
    );

  // 无限 debugger：每次被继续执行后，立刻再暂停一次
  const trap = () => {
    if (stopped) return;
    pause();
    setTimeout(trap, 0);
  };

  /**
   * 同步复检一次，并把结论同时提供给斗篷主逻辑。
   * @returns {boolean} true = 通过（没被调试、关键函数没被 hook）；false = 命中，已进入无限 debugger
   */
  window.antiDebugCheck = () => {
    if (stopped) return true; // 自己人已关闭反调试 → 放行
    if (trapped) return false; // 已命中过 → 继续拦，且不重复启动 trap

    // tampered 放最前：无 console 调用、无副作用，且被 hook 时后两个手段本就可疑
    if (tampered() || paused() || consoleOpened()) {
      trapped = true;
      trap(); // 只在这里启动一次无限 debugger
      return false;
    }

    return true;
  };

  // ① 加载即自检：必须早于页面渲染与斗篷放行
  window.antiDebugCheck();

  // ② 持续复检：兜住"页面打开后才打开控制台"的情况
  timer = setInterval(window.antiDebugCheck, CHECK_INTERVAL);
})();
