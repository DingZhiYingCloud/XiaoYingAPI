/**
 * 路线 B 公共环境桩（node 补环境）
 *
 * 被 try_node.js / sign_abogus.js 复用。这里只提供「够 bdms 加载与初始化」的最小浏览器环境，
 * 并按补环境迭代需要额外记录：
 *   - 事件监听注册表（新版 bdms 要求页面至少触发过一次鼠标事件，需要能合成事件）
 *   - 读取了但不存在的全局属性（缺失清单，下一步就补它们）
 */
const missing = new Set();
const listeners = new Map();   // "window:mousemove" -> [fn, ...]

function recordMissing(prop) {
  if (typeof prop === 'string' && !missing.has(prop)) missing.add(prop);
}

function addListener(target, type, fn) {
  const key = `${target}:${type}`;
  if (!listeners.has(key)) listeners.set(key, []);
  listeners.get(key).push(fn);
}

function makeElement(tag) {
  const el = {
    tagName: String(tag || '').toUpperCase(),
    style: {}, dataset: {}, children: [], childNodes: [], attributes: {},
    classList: { add() {}, remove() {}, contains: () => false },
    appendChild(c) { el.children.push(c); return c; },
    removeChild() {}, insertBefore() {}, cloneNode: () => makeElement(tag),
    setAttribute() {}, getAttribute: () => null, removeAttribute() {},
    addEventListener(type, fn) { addListener(`el:${tag}`, type, fn); },
    removeEventListener() {}, dispatchEvent: () => true,
    attachShadow: () => makeElement('shadow'),
    getContext: () => ({
      getImageData: () => ({ data: new Uint8ClampedArray(0) }),
      fillText() {}, measureText: () => ({ width: 0 }), drawImage() {},
    }),
    toDataURL: () => 'data:image/png;base64,',
    getBoundingClientRect: () => ({ width: 1536, height: 742, top: 0, left: 0, right: 1536, bottom: 742 }),
  };
  return el;
}

function buildSandbox() {
  const documentStub = {
    cookie: '',
    title: '抖音-记录美好生活',
    readyState: 'complete',
    referrer: 'https://www.douyin.com/',
    createElement: makeElement,
    createElementNS: (ns, tag) => makeElement(tag),
    createTextNode: () => ({}),
    getElementById: () => null,
    getElementsByTagName: (tag) => {
      const t = String(tag || '').toLowerCase();
      if (t === 'head') return [documentStub.head];
      if (t === 'body') return [documentStub.body];
      return [];
    },
    getElementsByClassName: () => [],
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener(type, fn) { addListener('document', type, fn); },
    removeEventListener() {},
    documentElement: Object.assign(makeElement('html'), { clientWidth: 1536, clientHeight: 742 }),
    body: makeElement('body'),
    head: makeElement('head'),
  };

  const navigatorStub = {
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    platform: 'Win32', language: 'zh-CN', languages: ['zh-CN', 'zh'], webdriver: false,
    cookieEnabled: true, onLine: true, hardwareConcurrency: 16, deviceMemory: 8,
    plugins: { length: 5, item: () => null, namedItem: () => null, refresh() {} },
    mimeTypes: { length: 4, item: () => null, namedItem: () => null },
    userAgentData: { brands: [{ brand: 'Chromium', version: '130' }], mobile: false, platform: 'Windows' },
  };

  const store = () => {
    const m = {};
    return {
      getItem: (k) => (k in m ? m[k] : null),
      setItem: (k, v) => { m[k] = String(v); },
      removeItem: (k) => { delete m[k]; },
      clear() {}, key: () => null, get length() { return Object.keys(m).length; },
    };
  };

  const base = {
    console, setTimeout, clearTimeout, setInterval, clearInterval, queueMicrotask,
    Math, Date, JSON, Promise, Array, Object, String, Number, Boolean, Error, RegExp, Map, Set, WeakMap,
    TextEncoder, TextDecoder, URL, URLSearchParams, Buffer, Symbol, Reflect, Proxy,
    // 二进制类型必须用宿主 realm 的：vm 子 realm 的 ArrayBuffer/TypedArray 传给 node 的
    // WebCrypto(subtle.importKey 等) 会被判定为「不是 BufferSource」而报错
    ArrayBuffer, SharedArrayBuffer, DataView,
    Uint8Array, Uint8ClampedArray, Uint16Array, Int8Array, Int16Array, Uint32Array, Int32Array,
    Float32Array, Float64Array, BigInt64Array, BigUint64Array,
    // Fetch API 与相关 Web 全局：webmssdk 会直接用它们（node 20 自带，直接用真实现）
    fetch, Request, Response, Headers, FormData, Blob, File,
    AbortController, AbortSignal, Event, EventTarget, CustomEvent, MessageChannel, MessagePort,
    structuredClone, ReadableStream, WritableStream, TransformStream,
    atob: (s) => Buffer.from(s, 'base64').toString('binary'),
    btoa: (s) => Buffer.from(s, 'binary').toString('base64'),
    performance: { now: () => Date.now(), timeOrigin: Date.now() },
    screen: { width: 1536, height: 864, availWidth: 1536, availHeight: 824, colorDepth: 24, pixelDepth: 24 },
    devicePixelRatio: 1,
    innerWidth: 1536, innerHeight: 742, outerWidth: 1536, outerHeight: 864, scrollX: 0, scrollY: 0,
    location: {
      href: 'https://www.douyin.com/', protocol: 'https:', host: 'www.douyin.com',
      hostname: 'www.douyin.com', pathname: '/', search: '', hash: '', origin: 'https://www.douyin.com',
      reload() {}, replace() {}, assign() {},
    },
    history: { length: 2, state: null, pushState() {}, replaceState() {}, back() {}, forward() {}, go() {} },
    localStorage: store(),
    sessionStorage: store(),
    crypto: { getRandomValues: (a) => { for (let i = 0; i < a.length; i++) a[i] = Math.floor(Math.random() * 256); return a; } },
    document: documentStub,
    navigator: navigatorStub,
    addEventListener(type, fn) { addListener('window', type, fn); },
    removeEventListener() {}, dispatchEvent: () => true,
    requestAnimationFrame: (cb) => setTimeout(() => cb(Date.now()), 16),
    cancelAnimationFrame: clearTimeout,
    getComputedStyle: () => ({ getPropertyValue: () => '' }),
    matchMedia: () => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {} }),
  };
  base.window = base;
  base.self = base;
  base.globalThis = base;
  base.top = base;
  base.parent = base;
  return base;
}

/** 触发合成鼠标事件（新版 bdms 要求至少一次鼠标事件才出有效签名） */
function fireMouseEvents(sandbox) {
  const types = ['mousemove', 'mousedown', 'mouseup', 'click'];
  let fired = 0;
  for (const [key, fns] of listeners.entries()) {
    const [target, type] = key.split(':');
    if (!types.includes(type)) continue;
    for (const fn of fns) {
      try {
        fn.call(sandbox, {
          type, clientX: 700 + fired, clientY: 400 + fired, screenX: 700, screenY: 400,
          button: 0, buttons: 0, target: sandbox.document.body, preventDefault() {}, stopPropagation() {},
          isTrusted: true, timeStamp: Date.now(),
        });
        fired += 1;
      } catch (e) { /* 合成事件失败不影响主流程，忽略 */ }
    }
  }
  return { fired, registered: listeners.size };
}

/** 用 Proxy 记录读取但未定义的全局属性（补环境清单） */
function withMissingLogger(target) {
  return new Proxy(target, {
    get(t, prop) {
      if (!(prop in t)) recordMissing(prop);
      return t[prop];
    },
    has: () => true,
  });
}

module.exports = { buildSandbox, fireMouseEvents, withMissingLogger, missing, listeners };
