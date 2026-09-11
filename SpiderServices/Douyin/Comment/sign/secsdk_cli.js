/**
 * 产出 x-tt-session-dtrait（纯 node 补环境，无需浏览器）
 *
 * 用法：
 *   node secsdk_cli.js <COOKIE>
 *
 * 输出约定：
 *   - 成功：stdout 单行 `DTRAIT=<值>`，退出码 0
 *   - 失败：stdout 无该行，诊断信息走 stderr，退出码 1
 *
 * 背景：comment/publish 的风控只认两个头 —— x-tt-session-dtrait（内容严格校验，
 * 缺失时响应是 "HTTP 200 + 0 字节" 的静默拦截）和常量 x-secsdk-csrf-token: DOWNGRADE。
 * 前者由抖音 securitySDK 的 dtrait 模块产出，本脚本负责在 node 里把它跑出来。
 */
const fs = require('fs');
const path = require('path');
const { loadChunk, findEntryModuleId, DOUYIN_DIR, CHUNK } = require('./secsdk_env');

// dtrait 头按请求 path 生成；本服务只发评论，固定用发布接口的 path
const PUBLISH_PATH = '/aweme/v1/web/comment/publish';
const PROBE_URL = 'https://www.douyin.com' + PUBLISH_PATH + '/';
// SDK 初始化参数（与抖音 web 端一致；来自浏览器会话）
const AID = 6383;
const WEB_ID = '7642460349618275878';
// 看门狗：SDK 会留下定时器，避免进程挂住
const TIMEOUT_MS = 30000;

const cookie = process.argv[2] || '';
if (!cookie) {
  process.stderr.write('[secsdk_cli] 缺少参数：抖音登录 Cookie\n');
  process.exit(1);
}

function fail(msg) {
  process.stderr.write(`[secsdk_cli] ${msg}\n`);
  process.exit(1);
}

(async () => {
  const { sandbox, req } = loadChunk(cookie);
  req(findEntryModuleId(fs.readFileSync(path.join(DOUYIN_DIR, CHUNK), 'utf8')));
  const sdk = sandbox.securitySDK;
  if (!sdk) fail('未加载出 securitySDK（js/douyin 下的 chunk 可能已随抖音改版失效）');

  // 初始化顺序照抄浏览器里已初始化好的实例
  sdk.setWebId(WEB_ID);
  sdk.setContext({ aid: AID, webId: WEB_ID });
  sdk.setStorageType('next');
  sdk.setDisableCrossStorage(true);
  sdk.setEnableTrustedTimestamp(true);
  sdk.setLoginStatus(true);
  sdk.disableStorageProxy = true;
  sdk.setConfig({
    aid: AID,
    scene: 'web_protect',
    certType: 'cookie',
    signVersion: 2,
    consumerPathList: [PUBLISH_PATH],
  });

  await sdk.start();
  await sdk.startDTrait({ consumerPathList: [PUBLISH_PATH] });

  // dtrait 模块依赖 SDK 的 fetch 钩子链先就绪
  await sdk.secureProxy.installInterceptors();
  await sdk.secureProxy.fetchInterceptor.patchFetchMethod();

  // dtrait 实例：按浏览器侧 startDTrait 的入参构造
  const inst = new sandbox.DTraitSDK.default({
    aid: AID,
    webId: WEB_ID,
    consumerPathList: [PUBLISH_PATH],
    urlRewriteRules: [],
  });
  await inst.updateDTraitPath([PUBLISH_PATH]);
  await inst.updateDTraitHost(['www.douyin.com', 'www-hj.douyin.com']);
  await inst.init();

  const headers = await inst.getDTraitHeader({ url: PROBE_URL, method: 'POST' });
  const value = headers && headers['x-tt-session-dtrait'];
  if (!value) fail('getDTraitHeader 未产出 x-tt-session-dtrait');

  process.stdout.write('DTRAIT=' + value + '\n');
  process.exit(0);
})().catch((e) => fail((e && e.stack) || String(e)));

setTimeout(() => fail(`超时（${TIMEOUT_MS / 1000}s）未产出 dtrait`), TIMEOUT_MS);
