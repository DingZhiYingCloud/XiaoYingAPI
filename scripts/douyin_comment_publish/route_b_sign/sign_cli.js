/**
 * 路线 B 通用签名器：给它 method + url (+ body)，它返回 bdms 签名后的请求。
 *
 * 用法：
 *   node sign_cli.js <METHOD> <URL> [BODY]
 * 例：
 *   node sign_cli.js GET "/aweme/v1/web/comment/list/?aid=6383&aweme_id=123"
 *   node sign_cli.js POST "/aweme/v1/web/comment/publish/?aid=6383" "aweme_id=123&text=hi"
 *
 * 输出（stdout 只有一行 JSON，便于被 Python 解析；调试信息走 stderr）：
 *   {"signedUrl": "...", "signedBody": "...", "urlChanged": true, "bodyChanged": false}
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { buildSandbox, fireMouseEvents, missing } = require('./env');

const JS_DIR = path.join(__dirname, '..', 'js');
const TARGET = process.env.BDMS_JS || 'bdms_1.0.1.19_fix.js';

const method = (process.argv[2] || 'GET').toUpperCase();
const rawUrl = process.argv[3] || '/';
const rawBody = process.argv[4] || null;

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
  proto.setRequestHeader = function (k, v) { log.push(['setRequestHeader', k, String(v).slice(0, 120)]); };
  proto.send = function (b) { log.push(['send', b == null ? null : String(b)]); };
  proto.abort = function () {};
  proto.addEventListener = function () {};
  proto.getAllResponseHeaders = function () { return ''; };
  sandbox.XMLHttpRequest = XMLHttpRequest;
}

const code = fs.readFileSync(path.join(JS_DIR, TARGET), 'utf8');
const sandbox = buildSandbox();
installXHR(sandbox);

let error = null;
try {
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox, { filename: TARGET, timeout: 20000 });
  sandbox.bdms.init({
    aid: 6383,
    pageId: 6241,
    paths: ['^/webcast/', '^/aweme/v1/', '^/aweme/v2/', '/v1/message/send', '^/live/', '^/captcha/', '^/ecom/'],
    boe: false, ddrt: 8.5, ic: 8.5,
  });
} catch (e) {
  error = (e && e.message) || String(e);
}

let signedUrl = rawUrl;
let signedBody = rawBody;
if (!error) {
  fireMouseEvents(sandbox);   // 新版 bdms 要求页面至少有一次鼠标事件
  try {
    const xhr = new sandbox.XMLHttpRequest();
    xhr.bdmsInvokeList = [
      { args: [method, rawUrl, true], func() {} },
      { args: ['Accept', 'application/json, text/plain, */*'], func() {} },
      { args: ['bd-ticket-guard-web-version', 2], func() {} },
      { args: ['bd-ticket-guard-version', 2], func() {} },
      { args: ['bd-ticket-guard-iteration-version', 1], func() {} },
    ];
    xhr.open(method, rawUrl, true);
    xhr.setRequestHeader('Accept', 'application/json, text/plain, */*');
    xhr.send(rawBody);

    const openEntry = log.find((x) => x[0] === 'open');
    const sendEntry = log.find((x) => x[0] === 'send');
    if (openEntry) signedUrl = openEntry[2];
    if (sendEntry && sendEntry[1] != null) signedBody = sendEntry[1];
  } catch (e) {
    error = (e && e.message) || String(e);
  }
}

// 调试信息 → stderr（不污染 stdout 的 JSON）
process.stderr.write(`[sign_cli] executed=${!error} missing=${JSON.stringify([...missing])}\n`);
if (error) process.stderr.write(`[sign_cli] error=${error}\n`);
for (const item of log) process.stderr.write(`[sign_cli] ${JSON.stringify(item)}\n`);

process.stdout.write(JSON.stringify({
  signedUrl: signedUrl,
  signedBody: signedBody,
  urlChanged: signedUrl !== rawUrl,
  bodyChanged: signedBody !== rawBody,
  error: error,
}) + '\n');

// bdms 会留下定时器，必须显式退出，否则进程挂住、挡住调用方
process.exit(0);
