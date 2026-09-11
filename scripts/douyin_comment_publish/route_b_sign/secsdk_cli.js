/**
 * 方案 1 驱动：在 node 里把 securitySDK 初始化到能产出 x-tt-session-dtrait。
 *
 * 配置项抄自浏览器里已初始化的实例：
 *   webid=7642460349618275878, storageType="next", disableStorageProxy=true,
 *   enableSecureTimestamp=false, enableTrustedTimestamp=true, _isLogin="1"
 *
 * 用法：node scripts/douyin_comment_publish/route_b_sign/secsdk_cli.js
 */
const fs = require('fs');
const path = require('path');
const { loadChunk, findEntryModuleId, DOUYIN_DIR, CHUNK } = require('./secsdk_env');

const PROBE = 'https://www.douyin.com/aweme/v1/web/comment/publish/?aweme_id=7400000000000000000';
const WEB_ID = '7642460349618275878';

const log = [];
const rawFetch = globalThis.fetch;

function headersToObj(h) {
  const o = {};
  if (!h) return o;
  try { new Headers(h).forEach((v, k) => { o[k] = v; }); } catch (e) { o.__err = String(e); }
  return o;
}

const { sandbox, req } = loadChunk();

// 记录器必须在 securitySDK 构造之前装好：
// secureProxy 在构造时就把当时的 window.fetch 记作「原始 fetch」
const hookedFetch = (input, init) => {
  const url = String((input && input.url) || input);
  const entry = { url, method: (init && init.method) || 'GET', headers: headersToObj(init && init.headers) };
  log.push(entry);
  if (url.includes('/aweme/v1/web/comment/publish')) {
    entry.status = 'STUB';
    return Promise.resolve(new Response('{"status_code":0,"captured":true}', {
      status: 200, headers: { 'content-type': 'application/json' },
    }));
  }
  return rawFetch(input, init).then((r) => { entry.status = r.status; return r; })
    .catch((e) => { entry.status = 'ERR:' + ((e && e.message) || e); throw e; });
};
sandbox.fetch = hookedFetch;

req(findEntryModuleId(fs.readFileSync(path.join(DOUYIN_DIR, CHUNK), 'utf8')));
const sdk = sandbox.securitySDK;
console.log('securitySDK =', typeof sdk);

process.on('unhandledRejection', (e) => {
  console.log('[unhandledRejection]', (e && e.message) || e);
});
process.on('uncaughtException', (e) => {
  console.log('[uncaughtException]', (e && e.message) || e);
  dumpLog();
  process.exit(1);
});

function dumpLog() {
  console.log('\n===== XHR 日志 =====');
  for (const it of (sandbox.__xhrLog || [])) {
    console.log(' ', it.method, it.url);
  }
  console.log('\n===== fetch 日志 =====');
  for (const it of log) {
    console.log(' ', it.method, it.url.slice(0, 130), '->', it.status);
    console.log('     ', JSON.stringify(it.headers).slice(0, 600));
  }
}

const step = (name, fn) => (async () => {
  try { const r = await fn(); console.log(`[OK] ${name}`, r === undefined ? '' : r); return true; }
  catch (e) { console.log(`[失败] ${name}: ${(e && e.message) || e}`); return false; }
})();

let dtInstance = null;

(async () => {
  await step('setWebId', () => sdk.setWebId(WEB_ID));
  await step('setContext', () => sdk.setContext({ aid: 6383, webId: WEB_ID }));
  await step('setStorageType', () => sdk.setStorageType('next'));
  await step('setDisableCrossStorage', () => sdk.setDisableCrossStorage(true));
  await step('setEnableTrustedTimestamp', () => sdk.setEnableTrustedTimestamp(true));
  await step('setLoginStatus', () => sdk.setLoginStatus(true));
  sdk.disableStorageProxy = true;

  console.log('状态:', JSON.stringify({
    aid: sdk.aid, webid: sdk.webid, storageType: sdk.storageType,
    disableStorageProxy: sdk.disableStorageProxy, _isLogin: sdk._isLogin,
  }));

  await step('setConfig', () => sdk.setConfig({
    aid: 6383,
    scene: 'web_protect',
    certType: 'cookie',
    signVersion: 2,
    consumerPathList: ['/aweme/v1/web/comment/publish', '/aweme/v1/web/comment/list'],
  }));

  await step('start', () => sdk.start());
  await step('startDTrait', () => sdk.startDTrait({ consumerPathList: ['/aweme/v1/web/comment/publish'] }));

  // securitySDK 的 fetch/xhr 拦截器
  await step('secureProxy.installInterceptors', () => sdk.secureProxy.installInterceptors());
  await step('fetchInterceptor.patchFetchMethod', () => sdk.secureProxy.fetchInterceptor.patchFetchMethod());
  try {
    const fi = sdk.secureProxy.fetchInterceptor;
    console.log('fetchInterceptor: initialized =', fi.isInitialized(), '| PATCHED_FLAG =', fi.PATCHED_FLAG);
  } catch (e) { console.log('fetchInterceptor 读取失败:', e.message); }
  console.log('fetch 是否已被 patch:', sandbox.fetch !== hookedFetch,
    '| window.fetch 标记:', !!(sandbox.fetch && sandbox.fetch._bd_ticket_guard_patched));

  // dtrait 实例：用完整 config 构造并 init，再直接产出 dtrait 头
  await step('dtrait 实例', async () => {
    const inst = new sandbox.DTraitSDK.default({
      aid: 6383,
      webId: WEB_ID,
      consumerPathList: ['/aweme/v1/web/comment/publish'],
      urlRewriteRules: [],
    });
    await step('updateDTraitPath', () => inst.updateDTraitPath(['/aweme/v1/web/comment/publish']));
    await step('updateDTraitHost', () => inst.updateDTraitHost(['www.douyin.com', 'www-hj.douyin.com']));
    await step('init', () => inst.init());
    console.log('   字段:', JSON.stringify({
      centralVersion: inst.centralVersion,
      edgeVersion: inst.edgeVersion,
      centralRsaPubLen: String(inst.centralRsaPub || '').length,
      edgeRsaPubLen: String(inst.edgeRsaPub || '').length,
      aesKeyLen: String(inst.aesKey || '').length,
      dTraitToken: String(inst.dTraitToken || '').slice(0, 60),
      libraGroup: inst.libraGroup,
      collectStatus: inst.collectStatus,
      hooksPath: inst.dTraitHooksPath,
      hooksHost: inst.dTraitHooksHost,
    }));
    dtInstance = inst;
    return 'ok';
  });

  if (dtInstance) {
    await step('getDTraitHeader', async () => {
      const h = await dtInstance.getDTraitHeader({ url: PROBE, method: 'POST' });
      const v = h && h['x-tt-session-dtrait'];
      if (v) {
        // 给外部脚本（publish 链路）解析用的机器可读输出
        console.log('DTRAIT=' + v);
      }
      return v ? `len=${v.length}` : '空';
    });
    await step('monkeyPatchRequest', () => dtInstance.monkeyPatchRequest());
  }

  try {
    const r = await sandbox.fetch(PROBE, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
    console.log('\n探测请求 status =', r.status, '| body =', (await r.text()).slice(0, 120));
  } catch (e) {
    console.log('\n探测请求失败:', (e && e.message) || e);
  }

  dumpLog();
  process.exit(0);
})();

// 看门狗：SDK 会留定时器，避免进程挂住
setTimeout(() => {
  console.log('\n[watchdog] 到达 25s，打印日志后退出');
  dumpLog();
  process.exit(0);
}, 25000);
