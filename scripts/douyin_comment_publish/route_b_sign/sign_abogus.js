/**
 * 路线 B 核心尝试：在 node 里驱动 bdms 生成 a_bogus
 *
 * 做法：补最小环境 → 执行 bdms → 调用 bdms.init（参数取自公开逆向文章的页面实测值）
 *      → 合成鼠标事件 → 构造带日志的 XMLHttpRequest 发一次请求 → 观察 bdms 到底
 *        把签名加在哪里（或是否直接暴露取签名的接口）。
 *
 * 用法：node scripts/douyin_comment_publish/route_b_sign/sign_abogus.js
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { buildSandbox, fireMouseEvents, withMissingLogger, missing } = require('./env');

const JS_DIR = path.join(__dirname, '..', 'js');
const TARGET = process.env.BDMS_JS || 'bdms_1.0.1.19_fix.js';

// 目标请求（commented/list 只读接口，避免任何写操作）
const PROBE_URL =
  '/aweme/v1/web/comment/list/?device_platform=webapp&aid=6383&channel=channel_pc_web' +
  '&pc_client_type=1&version_code=190500&version_name=19.5.0&cookie_enabled=true&platform=PC' +
  '&aweme_id=7400000000000000000&cursor=0&count=20&item_type=0';

const log = [];
let signature = {};

function installXHR(sandbox) {
  function XMLHttpRequest() {
    this.readyState = 1;
    this.status = 200;
    this.responseText = '{}';
    this.withCredentials = false;
  }
  const proto = XMLHttpRequest.prototype;
  proto.open = function (method, url, async) {
    log.push(['open', method, String(url), async]);
    this._method = method;
    this._url = url;
  };
  proto.setRequestHeader = function (k, v) {
    log.push(['setRequestHeader', k, String(v).slice(0, 200)]);
  };
  proto.send = function (body) {
    log.push(['send', body == null ? null : String(body).slice(0, 300)]);
    // 签名若被追加到请求上，通常体现在：本次调用前后 url/header 的变化，或全局变量
  };
  proto.abort = function () {};
  proto.addEventListener = function () {};
  proto.getAllResponseHeaders = function () { return ''; };
  sandbox.XMLHttpRequest = XMLHttpRequest;
  return XMLHttpRequest;
}

function dumpGlobals(sandbox) {
  const names = Object.getOwnPropertyNames(sandbox).filter(
    (k) => !['console', 'Math', 'Date', 'JSON', 'Promise', 'Array', 'Object', 'String', 'Number', 'Boolean',
      'Error', 'RegExp', 'Map', 'Set', 'WeakMap', 'Symbol', 'Reflect', 'Proxy', 'URL', 'URLSearchParams',
      'TextEncoder', 'TextDecoder', 'Buffer', 'Uint8Array', 'Uint8ClampedArray'].includes(k)
  );
  console.log('[全局对象中的可疑项]');
  for (const k of names) {
    const v = sandbox[k];
    const t = typeof v;
    if (k.toLowerCase().includes('bogus') || k.toLowerCase().includes('sign') || k === 'bdms' || t === 'function') {
      console.log(`  ${k} = ${t}${t === 'object' ? ` keys=${JSON.stringify(Object.keys(v || {}).slice(0, 20))}` : ''}`);
    }
  }
  return names;
}

const code = fs.readFileSync(path.join(JS_DIR, TARGET), 'utf8');
console.log(`目标脚本: ${TARGET} (${code.length} 字节)\n`);

const sandbox = buildSandbox();
installXHR(sandbox);
let failedAt = null;

try {
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox, { filename: TARGET, timeout: 20000 });
  console.log('[1] bdms 脚本执行完成，window.bdms =', typeof sandbox.bdms);
} catch (e) {
  failedAt = `执行脚本: ${e && e.message}`;
}

if (!failedAt && sandbox.bdms) {
  console.log('[2] bdms 暴露的键:', JSON.stringify(Object.getOwnPropertyNames(sandbox.bdms).slice(0, 30)));
  try {
    // 参数取自公开逆向文章：bdms.init({aid:6383, pageId:6241, paths:[...], boe:false, ddrt:8.5, ic:8.5})
    sandbox.bdms.init({
      aid: 6383,
      pageId: 6241,
      paths: ['^/webcast/', '^/aweme/v1/', '^/aweme/v2/', '/v1/message/send', '^/live/', '^/captcha/', '^/ecom/'],
      boe: false, ddrt: 8.5, ic: 8.5,
    });
    console.log('[3] bdms.init 调用成功');
  } catch (e) {
    failedAt = `bdms.init: ${(e && e.message) || e}`;
  }
}

if (!failedAt) {
  const r = fireMouseEvents(sandbox);
  console.log(`[4] 合成鼠标事件: 注册监听 ${r.registered} 组，触发 ${r.fired} 个`);
  dumpGlobals(sandbox);

  try {
    const xhr = new sandbox.XMLHttpRequest();
    // 公开文章里驱动签名的方式：给 xhr 挂 bdmsInvokeList 后 open+send
    xhr.bdmsInvokeList = [
      { args: ['GET', PROBE_URL, true], func() {} },
      { args: ['Accept', 'application/json, text/plain, */*'], func() {} },
      { args: ['bd-ticket-guard-web-version', 2], func() {} },
      { args: ['bd-ticket-guard-version', 2], func() {} },
      { args: ['bd-ticket-guard-iteration-version', 1], func() {} },
    ];
    xhr.open('GET', PROBE_URL, true);
    xhr.setRequestHeader('Accept', 'application/json, text/plain, */*');
    xhr.send(null);
    console.log('[5] 已发起（桩）请求');
  } catch (e) {
    failedAt = `驱动签名: ${(e && e.message) || e}`;
  }
}

console.log('\n===== XHR 调用日志（bdms 是否介入） =====');
if (log.length === 0) {
  console.log('  （空：bdms 未拦截这次请求）');
} else {
  for (const item of log) console.log('  ', JSON.stringify(item));
}

console.log('\n===== 是否出现签名 =====');
for (const k of Object.getOwnPropertyNames(sandbox)) {
  const v = sandbox[k];
  if (typeof v === 'string' && v.length > 40) signature[k] = v.slice(0, 80);
  if (v && typeof v === 'object' && 'a_bogus' in v) signature[k] = v.a_bogus;
}
console.log(signature);

// 关键产物：bdms 改写后的签名 URL（含 a_bogus），供 verify_signed.py 真实回放验证
const signedEntry = log.find((x) => x[0] === 'open' && typeof x[2] === 'string' && x[2].includes('a_bogus='));
if (signedEntry) {
  fs.writeFileSync(path.join(__dirname, 'signed_url.txt'), signedEntry[2], 'utf8');
  console.log('\n[6] 已把签名 URL 写入 signed_url.txt：');
  console.log('   ', signedEntry[2]);
} else {
  console.log('\n[6] 未在 XHR open 参数里发现 a_bogus（bdms 未介入或未生成签名）');
}

console.log('\n===== 缺什么（补环境清单，最多列 25 个） =====');
console.log(' ', [...missing].slice(0, 25));

if (failedAt) console.log(`\n[失败点] ${failedAt}`);

// bdms 会留下定时器，不显式退出 node 会一直挂着（也会挡住后续 shell 步骤）
process.exit(0);
