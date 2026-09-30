/* 海角社区视频密钥派生（node 脚本）
 *
 * 背景：源站对视频做了自定义保护 —— 播放列表里 #EXT-X-KEY 指向的 enc_xxx.key 是「假密钥」，
 * 真实 AES-128 密钥由源站自带的 jquery.wasm 用 jquery_key(假key, 盐) 就地改写得到；
 * 盐取自同名 <m3u8>.jpg 的内容（base64）。标准播放器拿假密钥解不开分片，故需在此还原。
 *
 * 用法：node derive_key.js <假key十六进制> <盐十六进制>
 * 输出：stdout 末行 REAL_KEY=<真key十六进制>
 *
 * 注：jquery.wasm 为源站产物（约 12.5KB，随代码入库）。源站改版导致派生失败时重新抓取：
 *     https://haijiao.com/js/jquery.wasm
 */
const fs = require('fs');
const path = require('path');

async function main() {
  const [fakeKeyHex, saltHex] = process.argv.slice(2);
  if (!fakeKeyHex || !saltHex) {
    throw new Error('用法: node derive_key.js <假key十六进制> <盐十六进制>');
  }

  const wasm = fs.readFileSync(path.join(__dirname, 'jquery.wasm'));
  // 该模块导入极少（wasm 侧仅用内存），stub 掉环境与 wasi 的少量符号即可实例化
  const imports = {
    env: {
      _abort_js: () => {},
      emscripten_resize_heap: () => 1,
    },
    wasi_snapshot_preview1: {
      fd_close: () => 0,
      fd_write: () => 0,
      fd_seek: () => 0,
    },
  };
  const { instance } = await WebAssembly.instantiate(wasm, imports);
  const ex = instance.exports;
  if (ex.__wasm_call_ctors) ex.__wasm_call_ctors();

  const key = Buffer.from(fakeKeyHex, 'hex');
  const salt = Buffer.from(saltHex, 'hex');
  const keyPtr = ex.malloc(key.length);
  const saltPtr = ex.malloc(salt.length);
  new Uint8Array(ex.memory.buffer, keyPtr, key.length).set(key);
  new Uint8Array(ex.memory.buffer, saltPtr, salt.length).set(salt);

  // jquery_key 就地把 keyPtr 处的字节改写为真密钥
  ex.jquery_key(keyPtr, key.length, saltPtr, salt.length);
  const real = Buffer.from(new Uint8Array(ex.memory.buffer, keyPtr, key.length)).toString('hex');
  ex.free(keyPtr);
  ex.free(saltPtr);

  process.stdout.write('REAL_KEY=' + real + '\n');
}

main().catch((e) => {
  console.error(String(e && e.message ? e.message : e));
  process.exit(1);
});
