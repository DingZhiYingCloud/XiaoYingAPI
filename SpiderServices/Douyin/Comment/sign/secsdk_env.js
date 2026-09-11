/**
 * 抖音 securitySDK 补环境加载器
 *
 * 抖音的 securitySDK 本体不是独立脚本，而是藏在主站 webpack 的**异步 chunk** 里：
 *   js/douyin/20021.*.js  内部形如
 *   (self.webpackChunkdouyin_web = self.webpackChunkdouyin_web || [])
 *     .push([["20021"], { 832738: function(module, exports, __webpack_require__){...}, ... }])
 *
 * 本模块给这些 chunk 补一个**最小 webpack runtime + 浏览器环境**，让 SDK 能在 node 里跑起来，
 * 从而离线产出 x-tt-session-dtrait（不再需要浏览器 / 不再需要抓包借头）。
 *
 * 对外接口：
 *   loadChunk(cookie) -> { sandbox, req }
 *     - sandbox: 沙箱全局对象（window / document / crypto / localStorage 等）
 *     - req:     最小 webpack require，用法 req(入口模块id)
 *   findEntryModuleId(code): 在 chunk 源码里定位「设置 window.securitySDK」的入口模块 id
 *
 * 注意：js/douyin/ 下的 chunk 是按抖音某个版本固化的（文件名带哈希）。抖音改版后需要重新下载，
 * 下载方式见项目 API 文档「抖音自动评论」服务说明。
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { webcrypto } = require('crypto');
const { buildSandbox } = require('./env');

const JS_DIR = path.join(__dirname, '..', 'js');
const DOUYIN_DIR = path.join(JS_DIR, 'douyin');
// 唯一入口 chunk（其余依赖从 DOUYIN_DIR 全量注册 / 按需加载）
const CHUNK = '20021.3fff349b.js';
// webpack runtime 会接管 chunkLoadingGlobal.push，先把我们自己的注册器藏起来
const EXCLUDE = /^runtime/;

const rawFetch = globalThis.fetch;

/**
 * 最小 webpack runtime：支持同步 require + 按需加载磁盘 chunk。
 *
 * @param {Object} moduleMap 模块表（各 chunk 的 push 会往里灌模块）
 * @param {(chunkId: string) => (string|null)} loadChunkById 按 chunkId 加载磁盘上的异步 chunk
 */
function createWebpackRuntime(moduleMap, loadChunkById) {
  const cache = {};
  function req(id) {
    if (cache[id]) return cache[id].exports;
    const fn = moduleMap[id];
    if (!fn) throw new Error(`模块 ${id} 不在已注册的 chunk 里`);
    const mod = { id, loaded: false, exports: {} };
    cache[id] = mod;
    fn(mod, mod.exports, req);
    mod.loaded = true;
    return mod.exports;
  }
  req.d = (exports, definition) => {
    for (const key in definition) {
      if (Object.prototype.hasOwnProperty.call(definition, key)
        && !Object.prototype.hasOwnProperty.call(exports, key)) {
        Object.defineProperty(exports, key, { enumerable: true, get: definition[key] });
      }
    }
  };
  req.r = (exports) => {
    if (typeof Symbol !== 'undefined' && Symbol.toStringTag) {
      Object.defineProperty(exports, Symbol.toStringTag, { value: 'Module' });
    }
    Object.defineProperty(exports, '__esModule', { value: true });
  };
  req.n = (m) => {
    const getter = m && m.__esModule ? () => m.default : () => m;
    req.d(getter, { a: getter });
    return getter;
  };
  req.o = (obj, prop) => Object.prototype.hasOwnProperty.call(obj, prop);
  req.p = 'https://lf-douyin-pc-web.douyinstatic.com/obj/douyin-pc-web/ies/douyin_web/';
  req.e = (chunkId) => {
    const loaded = loadChunkById(String(chunkId));
    return loaded
      ? Promise.resolve()
      : Promise.reject(new Error(`异步 chunk ${chunkId} 不在本地`));
  };
  req.u = (chunkId) => `${chunkId}.js`;
  req.f = {};
  req.m = moduleMap;
  req.c = cache;
  return req;
}

/**
 * 可用的 XMLHttpRequest 桩。
 *
 * SDK 拉证书、上报埋点都走 XHR，空壳会让它报 "get cert timeout"；
 * 这里用 node 原生 fetch 作为底层传输，并自动带上 Cookie。
 */
function makeXHR(sandbox) {
  function XMLHttpRequest() {
    this.readyState = 0;
    this.status = 0;
    this.statusText = '';
    this.responseText = '';
    this.response = '';
    this.responseType = '';
    this.withCredentials = false;
    this._headers = {};
    this._respHeaders = {};
    this._listeners = {};
  }
  const p = XMLHttpRequest.prototype;
  p.open = function (method, url) {
    this._method = method;
    this._url = url;
    this.readyState = 1;
    this._fire('readystatechange');
  };
  p.setRequestHeader = function (k, v) { this._headers[k] = v; };
  p.getResponseHeader = function (k) { return this._respHeaders[String(k).toLowerCase()] || null; };
  p.getAllResponseHeaders = function () {
    return Object.entries(this._respHeaders).map(([k, v]) => `${k}: ${v}`).join('\r\n');
  };
  p.addEventListener = function (type, fn) {
    (this._listeners[type] = this._listeners[type] || []).push(fn);
  };
  p.removeEventListener = function () {};
  p.abort = function () {};
  p._fire = function (type) {
    const ev = { type, target: this, currentTarget: this };
    try {
      if (typeof this[`on${type}`] === 'function') this[`on${type}`](ev);
    } catch (e) { /* 忽略 SDK 回调自身异常，不影响主流程 */ }
    (this._listeners[type] || []).forEach((fn) => {
      try { fn(ev); } catch (e) { /* 同上 */ }
    });
  };
  p.send = function (body) {
    const headers = Object.assign({}, this._headers);
    if (sandbox.document.cookie && !Object.keys(headers).some((k) => k.toLowerCase() === 'cookie')) {
      headers.Cookie = sandbox.document.cookie;
    }
    rawFetch(this._url, {
      method: this._method || 'GET',
      headers,
      body: body === undefined || body === null || body === '' ? undefined : body,
    }).then(async (r) => {
      this.status = r.status;
      this.statusText = r.statusText;
      this.responseText = await r.text();
      this.response = this.responseText;
      r.headers.forEach((v, k) => { this._respHeaders[k] = v; });
      this.readyState = 4;
      this._fire('readystatechange');
      this._fire('load');
      this._fire('loadend');
    }).catch(() => {
      this.status = 0;
      this.readyState = 4;
      this._fire('readystatechange');
      this._fire('error');
      this._fire('loadend');
    });
  };
  XMLHttpRequest.DONE = 4;
  return XMLHttpRequest;
}

/**
 * 构建浏览器沙箱。
 *
 * @param {string} cookie 抖音登录 Cookie（SDK 注册客户端证书、上报时都要用）
 */
function buildEnv(cookie) {
  const sandbox = buildSandbox();
  sandbox.crypto = webcrypto;
  sandbox.msCrypto = webcrypto;
  sandbox.Response = Response;
  sandbox.Request = Request;
  sandbox.Headers = Headers;
  sandbox.XMLHttpRequest = makeXHR(sandbox);
  sandbox.performance = {
    now: () => Date.now(), timeOrigin: Date.now(),
    getEntriesByType: () => [], getEntries: () => [], mark() {}, measure() {},
  };
  sandbox.document.cookie = cookie || '';
  // 预置「反自动化工具检测」SDK，跳过它的动态脚本注入（与 dtrait 签名无关）
  sandbox.ucSecureToolDetect = { preload: async () => true, getResult: async () => ({}) };
  return sandbox;
}

/**
 * 加载 js/douyin/ 下全部 chunk 并注册模块表。
 *
 * @param {string} cookie 抖音登录 Cookie
 * @return {{sandbox: Object, req: Function, moduleIds: string[]}}
 */
function loadChunk(cookie) {
  const sandbox = buildEnv(cookie);
  const moduleMap = {};

  // chunkId -> 文件名索引（异步 chunk 命名为 <chunkId>.<hash>.js）
  const files = fs.readdirSync(DOUYIN_DIR).filter((f) => f.endsWith('.js'));
  const chunkFileIndex = {};
  for (const f of files) {
    const m = /^(\d+)\.[0-9a-f]+\.js$/.exec(f);
    if (m) chunkFileIndex[m[1]] = f;
  }

  const registry = [];
  registry.push = (payload) => {
    Object.assign(moduleMap, payload[1]);
    return 0;
  };
  sandbox.webpackChunkdouyin_web = registry;

  vm.createContext(sandbox);

  const loaded = new Set();
  function runFile(name) {
    if (loaded.has(name)) return;
    loaded.add(name);
    vm.runInContext(fs.readFileSync(path.join(DOUYIN_DIR, name), 'utf8'), sandbox, {
      filename: name, timeout: 60000,
    });
  }
  const loadChunkById = (chunkId) => {
    const name = chunkFileIndex[chunkId];
    if (!name) return null;
    try { runFile(name); } catch (e) { return null; }
    return name;
  };

  // 全量注册：SDK 的模块图横跨多个 chunk，逐个按需解析易漏；一次性灌进去最稳
  for (const f of files.filter((x) => !EXCLUDE.test(x))) {
    try { runFile(f); } catch (e) { /* 单个 chunk 失败不影响其他 chunk 注册 */ }
  }

  const req = createWebpackRuntime(moduleMap, loadChunkById);
  sandbox.__webpack_require__ = req;
  return { sandbox, req, moduleIds: Object.keys(moduleMap) };
}

/**
 * 在 chunk 源码里定位「设置 window.securitySDK」的那个入口模块 id。
 *
 * @param {string} code 入口 chunk 源码
 */
function findEntryModuleId(code) {
  const idx = code.indexOf('securitySDK');
  if (idx < 0) throw new Error('入口 chunk 里找不到 securitySDK');
  const re = /(\d{3,7}):function\(/g;
  let last = null;
  let m;
  while ((m = re.exec(code)) && m.index < idx) last = m[1];
  if (!last) throw new Error('定位入口模块失败');
  return last;
}

module.exports = { loadChunk, findEntryModuleId, DOUYIN_DIR, CHUNK };
