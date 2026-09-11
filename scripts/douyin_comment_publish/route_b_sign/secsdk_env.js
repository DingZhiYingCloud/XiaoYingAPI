/**
 * 方案 1 核心：给抖音 webpack 异步 chunk 补一个最小 webpack runtime + 浏览器环境，
 * 把里面的 securitySDK 加载出来，并支持按需加载磁盘上的兄弟 chunk。
 *
 * chunk 形态：
 *   (self.webpackChunkdouyin_web = self.webpackChunkdouyin_web || [])
 *     .push([["20021"], { 832738: function(module, exports, __webpack_require__){...}, ... }])
 *
 * 用法：node scripts/douyin_comment_publish/route_b_sign/secsdk_env.js
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { webcrypto } = require('crypto');
const { buildSandbox, missing } = require('./env');

const JS_DIR = path.join(__dirname, '..', 'js');
// 抖音 chunk 与生产目录共用一份（避免 19.6MB 重复入库；抖音改版时只需更新生产目录）
const DOUYIN_DIR = path.join(__dirname, '..', '..', '..',
  'SpiderServices', 'Douyin', 'Comment', 'js', 'douyin');
// 唯一入口 chunk（其余依赖从 DOUYIN_DIR 全量注册 / 按需加载）
const CHUNK = '20021.3fff349b.js';
// webpack runtime 会接管 chunkLoadingGlobal.push，先排除
const EXCLUDE = /^runtime/;

/**
 * 最小 webpack runtime：支持同步 require + 按需加载磁盘 chunk。
 * @param {Object} moduleMap 模块表（由各 chunk 的 push 填充）
 * @param {(chunkId:string)=>string|null} loadChunkById 按 chunkId 加载磁盘 chunk
 */
function createWebpackRuntime(moduleMap, loadChunkById) {
  const cache = {};
  function req(id) {
    if (cache[id]) return cache[id].exports;
    const fn = moduleMap[id];
    if (!fn) throw new Error(`module ${id} not found in registered chunks`);
    const mod = { id, loaded: false, exports: {} };
    cache[id] = mod;
    fn(mod, mod.exports, req);
    mod.loaded = true;
    return mod.exports;
  }
  req.d = (exports, definition) => {
    for (const key in definition) {
      if (Object.prototype.hasOwnProperty.call(definition, key) && !Object.prototype.hasOwnProperty.call(exports, key)) {
        Object.defineProperty(exports, key, { enumerable: true, get: definition[key] });
      }
    }
  };
  req.r = (exports) => {
    if (typeof Symbol !== 'undefined' && Symbol.toStringTag) Object.defineProperty(exports, Symbol.toStringTag, { value: 'Module' });
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
      : Promise.reject(new Error(`chunk ${chunkId} 不在本地（需先下载）`));
  };
  req.u = (chunkId) => `${chunkId}.js`;
  req.f = {};
  req.m = moduleMap;
  req.c = cache;
  return req;
}

const rawFetch = globalThis.fetch;

/**
 * 可用的 XMLHttpRequest 桩：SDK 拉证书/上报都走 XHR，空壳会让它超时。
 * 这里用 node 原生 fetch 作为底层传输，并自动带上 sandbox 里的 Cookie。
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
  p.addEventListener = function (type, fn) { (this._listeners[type] = this._listeners[type] || []).push(fn); };
  p.removeEventListener = function () {};
  p.abort = function () {};
  p._fire = function (type) {
    const ev = { type, target: this, currentTarget: this };
    try { if (typeof this[`on${type}`] === 'function') this[`on${type}`](ev); } catch (e) { /* 忽略业务回调异常 */ }
    (this._listeners[type] || []).forEach((fn) => { try { fn(ev); } catch (e) { /* 同上 */ } });
  };
  p.send = function (body) {
    const headers = Object.assign({}, this._headers);
    if (sandbox.document.cookie && !Object.keys(headers).some((k) => k.toLowerCase() === 'cookie')) {
      headers.Cookie = sandbox.document.cookie;
    }
    if (Array.isArray(sandbox.__xhrLog)) {
      sandbox.__xhrLog.push({ method: this._method, url: String(this._url).slice(0, 160), headers });
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

function buildEnv() {
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
  const COOKIE_FILE = path.join(__dirname, '..', 'cookie.txt');
  if (fs.existsSync(COOKIE_FILE)) {
    sandbox.document.cookie = fs.readFileSync(COOKIE_FILE, 'utf8').trim();
  }
  // 预置「反自动化工具检测」SDK，跳过它的动态脚本注入（与 dtrait 签名无关）
  sandbox.ucSecureToolDetect = { preload: async () => true, getResult: async () => ({}) };
  sandbox.__xhrLog = [];
  return sandbox;
}

/** 加载 DOUYIN_DIR 下全部 chunk，返回 { sandbox, req, moduleIds } */
function loadChunk() {
  const sandbox = buildEnv();
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

  let ok = 0;
  for (const f of files.filter((x) => !EXCLUDE.test(x)).sort()) {
    try { runFile(f); ok += 1; } catch (e) { /* 单个 chunk 失败不影响其他 */ }
  }
  console.log(`已注册 ${ok}/${files.length} 个 chunk，模块总数 ${Object.keys(moduleMap).length}`);

  const req = createWebpackRuntime(moduleMap, loadChunkById);
  sandbox.__webpack_require__ = req;
  return { sandbox, req, moduleIds: Object.keys(moduleMap), loadChunkById };
}

/** 在 chunk 源码里定位「设置 window.securitySDK」的那个入口模块 id */
function findEntryModuleId(code) {
  const idx = code.indexOf('securitySDK');
  if (idx < 0) throw new Error('chunk 里找不到 securitySDK');
  const re = /(\d{3,7}):function\(/g;
  let last = null;
  let m;
  while ((m = re.exec(code)) && m.index < idx) last = m[1];
  if (!last) throw new Error('定位入口模块失败');
  return last;
}

function main() {
  const { sandbox, req } = loadChunk();
  const entryCode = fs.readFileSync(path.join(DOUYIN_DIR, CHUNK), 'utf8');
  const entryId = findEntryModuleId(entryCode);
  console.log('入口模块 id:', entryId);

  try {
    req(entryId);
  } catch (e) {
    console.log('执行入口模块失败:', (e && e.message) || e);
  }

  const sdk = sandbox.securitySDK;
  console.log('window.securitySDK =', typeof sdk, sdk ? `| keys=${Object.keys(sdk).length}` : '');
  console.log('\n缺失全局（最多 40 个）:', [...missing].slice(0, 40));
  process.exit(0);
}

if (require.main === module) main();
module.exports = { loadChunk, createWebpackRuntime, buildEnv, findEntryModuleId, DOUYIN_DIR, CHUNK };
