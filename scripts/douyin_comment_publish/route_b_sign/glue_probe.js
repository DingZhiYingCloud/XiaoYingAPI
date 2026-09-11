/**
 * 路线 B 第二步探路：把 webmssdk + sdk-glue 也塞进 node 环境，看能不能加载、
 * 以及它们是否会把 bd-ticket-guard 那套请求头挂到 XHR 上。
 *
 * 用法：node scripts/douyin_comment_publish/route_b_sign/glue_probe.js
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { buildSandbox, fireMouseEvents, missing } = require('./env');

const JS_DIR = path.join(__dirname, '..', 'js');
const COOKIE_FILE = path.join(__dirname, '..', 'cookie.txt');

// 页面里三个脚本的加载顺序（[实测] 来自 <script src> DOM 顺序）
const SCRIPTS = ['webmssdk.es5.js', 'sdk-glue.js', 'bdms_1.0.1.19_fix.js'];

const log = [];

function installXHR(sandbox) {
  function XMLHttpRequest() {
    this.readyState = 1;
    this.status = 200;
    this.responseText = '{}';
    this.withCredentials = false;
  }
  const proto = XMLHttpRequest.prototype;
  proto.open = function (m, u) { log.push(['open', m, String(u)]); };
  proto.setRequestHeader = function (k, v) { log.push(['setRequestHeader', k, String(v).slice(0, 160)]); };
  proto.send = function (b) { log.push(['send', b == null ? null : String(b).slice(0, 200)]); };
  proto.abort = function () {};
  proto.addEventListener = function () {};
  proto.getAllResponseHeaders = function () { return ''; };
  sandbox.XMLHttpRequest = XMLHttpRequest;
  return XMLHttpRequest;
}

const sandbox = buildSandbox();
installXHR(sandbox);

// ticket-guard 的签名依赖 Cookie（bd_ticket_guard_ts_sign_id / bd_ticket_guard_client_data 等）
if (fs.existsSync(COOKIE_FILE)) {
  sandbox.document.cookie = fs.readFileSync(COOKIE_FILE, 'utf8').trim();
  const n = sandbox.document.cookie.split(';').filter(Boolean).length;
  console.log(`已注入 ${n} 个 Cookie 到 document.cookie`);
} else {
  console.log('未找到 cookie.txt（ticket-guard 可能算不出签名）');
}

vm.createContext(sandbox);

for (const name of SCRIPTS) {
  const file = path.join(JS_DIR, name);
  if (!fs.existsSync(file)) {
    console.log(`[跳过] ${name} 不存在`);
    continue;
  }
  const code = fs.readFileSync(file, 'utf8');
  const before = new Set(Object.getOwnPropertyNames(sandbox));
  try {
    vm.runInContext(code, sandbox, { filename: name, timeout: 30000 });
    const added = Object.getOwnPropertyNames(sandbox).filter((k) => !before.has(k));
    console.log(`[OK] ${name} (${code.length} 字节) 新增全局: ${JSON.stringify(added.slice(0, 12))}`);
  } catch (e) {
    console.log(`[失败] ${name}: ${(e && e.message) || e}`);
    break;
  }
}

console.log('\n关键全局:');
for (const k of ['bdms', 'byted_acrawler', 'webmssdk', 'bytedAcrawler', 'SecSDK', '_0x1a2b']) {
  console.log(`  window.${k} = ${typeof sandbox[k]}`);
}

// 试着驱动一次请求，看 SDK 是否会挂上 ticket-guard 请求头
if (typeof sandbox.bdms === 'object' && sandbox.bdms.init) {
  try {
    sandbox.bdms.init({
      aid: 6383, pageId: 6241,
      paths: ['^/webcast/', '^/aweme/v1/', '^/aweme/v2/', '/v1/message/send', '^/live/', '^/captcha/', '^/ecom/'],
      boe: false, ddrt: 8.5, ic: 8.5,
    });
    fireMouseEvents(sandbox);

    const url = '/aweme/v1/web/comment/publish/?device_platform=webapp&aid=6383&aweme_id=7400000000000000000&text=probe';
    const xhr = new sandbox.XMLHttpRequest();
    xhr.bdmsInvokeList = [
      { args: ['POST', url, true], func() {} },
      { args: ['Accept', 'application/json, text/plain, */*'], func() {} },
      { args: ['bd-ticket-guard-web-version', 2], func() {} },
      { args: ['bd-ticket-guard-version', 2], func() {} },
      { args: ['bd-ticket-guard-iteration-version', 1], func() {} },
    ];
    xhr.open('POST', url, true);
    xhr.setRequestHeader('Accept', 'application/json, text/plain, */*');
    xhr.send('aweme_id=7400000000000000000&text=probe');
  } catch (e) {
    console.log('驱动请求失败:', (e && e.message) || e);
  }
}

console.log('\n===== XHR 调用日志（看 SDK 加了哪些头） =====');
for (const item of log) console.log('  ', JSON.stringify(item));

console.log('\n缺什么（补环境清单，最多 30 个）:', [...missing].slice(0, 30));
process.exit(0);
