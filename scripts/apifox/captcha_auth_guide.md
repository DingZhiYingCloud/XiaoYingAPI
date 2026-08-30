# 阿里云图形认证集成服务使用教程

## 1. 服务简介

本服务提供**阿里云图形认证（Captcha）集成能力**：在 H5 页面集成阿里云图形验证码（点选/滑块等），由用户在客户端完成图形验证，服务端进行**二次校验**确认本次验证的真实有效，防止验证结果被伪造或重放。

**适用场景**：登录、注册、下单等需要人机校验的 H5 页面。

**服务目录**：`图形认证集成服务/阿里云图形认证集成服务`，包含：

| 资源 | 类型 | 说明 |
|------|------|------|
| 获取图形认证配置 | 接口 GET | `/api/captcha_auth/aliyun/config` 下发 appId |
| 图形认证二次校验 | 接口 POST | `/api/captcha_auth/aliyun/verify` 服务端校验 |
| captcha-client.js | 封装 JS | **推荐**：极简接入，已托管于本服务 |
| ct4.js | 官方 SDK | 已托管于本服务，接入方无需下载 |

**为什么要二次校验？**

前端 SDK 验证通过后产生的参数（lot_number / captcha_output / pass_token / gen_time）**不能直接信任**——攻击者可伪造或重放这些参数。必须由服务端拿着这些参数，配合机密密钥 appKey 生成签名，再次调用阿里云二次校验接口确认有效性。**只做前端验证、不调二次校验的接入是无效的。**

---

## 2. 接入前置条件

**零下载、零配置**：官方 SDK（`ct4.js`）与封装客户端（`captcha-client.js`）均已由小影 API 托管于自身静态服务，接入方**无需从任何地方下载文件**，只需在页面引入即可。

> 背景说明：阿里云的 H5 官方 SDK（ct4.js）仅能从阿里云控制台下载、无公开 CDN，且不能直接跨域使用第三方 CDN 副本。小影 API 已代为下载并托管，同时完成 appId/appKey 的代码层配置，接入方无需接触阿里云控制台。

---

## 3. 接入方式总览

| 方式 | 复杂度 | 说明 |
|------|--------|------|
| **方式一：封装客户端（推荐）** | 最低 | 引入 1 个 JS，两行代码完成「加载 SDK + 获取 appId + 二次校验」全流程 |
| 方式二：直接使用官方 SDK | 中等 | 引入本项目托管的 ct4.js，自行处理初始化与二次校验 |

---

## 4. 方式一：封装客户端接入（推荐）

只需引入本项目托管的 `captcha-client.js`，无需关心阿里云 SDK 细节。

### 4.1 引入文件

```html
<!-- 引入小影API图形认证封装客户端（自动加载官方 SDK） -->
<script src="/static/js/captcha_auth/aliyun/captcha-client.js"></script>
```

### 4.2 初始化

```html
<script>
  XYCaptcha.init({
    onReady: function () {
      // 验证码已就绪，可提示用户 / 启用"开始验证"按钮
    },
    onResult: function (data) {
      // 用户完成验证 + 服务端二次校验完成后回调，直接据此放行/拦截业务
      if (data.passed) {
        console.log('校验通过，放行业务');
      } else {
        console.log('校验失败:', data.reason, '，请重新验证');
      }
    },
    onError: function (msg) {
      // SDK 加载/初始化失败（如静态资源异常）
      console.error(msg);
    }
  });
</script>
```

### 4.3 调起验证码

```html
<button onclick="XYCaptcha.show()">开始图形验证</button>
```

### 4.4 完整示例（H5）

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>图形认证极简接入</title>
</head>
<body>
  <button id="btn" disabled>开始图形验证</button>

  <script src="/static/js/captcha_auth/aliyun/captcha-client.js"></script>
  <script>
    XYCaptcha.init({
      onReady: function () { document.getElementById('btn').disabled = false; },
      onResult: function (data) {
        if (data.passed) {
          alert('验证通过，放行业务');
        } else {
          alert('验证未通过: ' + data.reason);
        }
      }
    });
    document.getElementById('btn').onclick = function () { XYCaptcha.show(); };
  </script>
</body>
</html>
```

### 4.5 封装客户端 API

| 方法 | 参数 | 说明 |
|------|------|------|
| `XYCaptcha.init(options)` | `{ onReady, onResult, onError }` | 初始化（自动加载 SDK → 获取 appId → 初始化） |
| `XYCaptcha.show()` | - | 调起图形验证码（onReady 后再调用） |
| `XYCaptcha.isReady()` | - | 是否初始化完成 |

**onResult 回调参数（data）**：

| 字段 | 类型 | 说明 |
|------|------|------|
| passed | boolean | true=验证通过，false=未通过 |
| result | string | success / fail |
| reason | string | 失败原因（如 pass_token expire），成功时为空 |
| captcha_args | object | 阿里云验证输出参数（风控信息） |

---

## 5. 方式二：直接使用官方 SDK 接入

官方 SDK 已托管于本项目静态服务，直接引入即可。

### 5.1 引入文件

```html
<!-- 本项目托管的阿里云官方 SDK（无需从阿里云控制台下载） -->
<script src="/static/js/captcha_auth/aliyun/ct4.js"></script>
```

### 5.2 初始化与二次校验

```html
<script>
  // ① 获取 appId（config 接口失败时可用内置兜底值）
  async function fetchAppId() {
    try {
      const res = await fetch('/api/captcha_auth/aliyun/config');
      const data = await res.json();
      if (data.code === 10000 && data.data && data.data.app_id) {
        return data.data.app_id;
      }
    } catch (e) { /* 忽略 */ }
    return '296d0fabf47beeacfe50cbc01f8cd4d7'; // 兜底 appId
  }

  let captchaObj = null;

  (async function init() {
    const appId = await fetchAppId();
    // ② 初始化 SDK
    initAlicom4({ captchaId: appId, product: 'bind' }, function (obj) {
      captchaObj = obj;
      captchaObj.onNextReady(function () { console.log('验证码已就绪'); });
      // ③ 用户验证成功
      captchaObj.onSuccess(function () {
        const validate = captchaObj.getValidate(); // ④ 取出 4 个参数
        verify(validate);                          // ⑤ 调二次校验
      });
      captchaObj.onFail(function () { console.log('图形验证失败'); });
      captchaObj.onError(function () { console.log('图形验证出错'); });
    });
  })();

  // ⑤ 调用二次校验接口
  async function verify(v) {
    const body = new URLSearchParams(v);
    const data = await (await fetch('/api/captcha_auth/aliyun/verify', { method: 'POST', body })).json();
    console.log(data.code === 10000 && data.data.result === 'success'
      ? '校验通过，放行业务' : '校验失败，请重新验证');
  }
</script>
```

---

## 6. 接口使用说明

### 6.1 获取图形认证配置

**请求**

```http
GET /api/captcha_auth/aliyun/config
```

无参数，公开接口，无需签名。

**响应**

```json
{
  "code": 10000,
  "msg": "获取成功",
  "data": {
    "app_id": "296d0fabf47beeacfe50cbc01f8cd4d7"
  }
}
```

| 字段 | 说明 |
|------|------|
| app_id | 阿里云图形认证验证ID（appId），32 位，前端 SDK 初始化用 |

### 6.2 图形认证二次校验

**请求**

```http
POST /api/captcha_auth/aliyun/verify
Content-Type: application/x-www-form-urlencoded

lot_number=xxx&captcha_output=xxx&pass_token=xxx&gen_time=xxx
```

**参数表**

| 参数 | 必填 | 说明 |
|------|------|------|
| lot_number | 是 | 验证流水号，32 位（SDK 验证通过后生成，一次性） |
| captcha_output | 是 | 验证输出信息（SDK 回调返回，一次性） |
| pass_token | 是 | 验证通过标识（SDK 回调返回，一次性） |
| gen_time | 是 | 验证通过时间戳（SDK `getValidate()` 返回，10 位秒级） |

**响应**

```json
{
  "code": 10000,
  "msg": "校验完成",
  "data": {
    "result": "success",
    "passed": true,
    "reason": "",
    "captcha_args": {
      "used_type": "icon",
      "user_ip": "77.83.241.169",
      "lot_number": "424c60ea0f3b4301aac844ff0066709c",
      "scene": "其他",
      "client_type": "web"
    }
  }
}
```

**业务结果语义**（以 `data.result` 为准）：

| result | passed | 含义 | 处理建议 |
|--------|--------|------|----------|
| success | true | 验证有效 | 放行（登录/提交） |
| fail | false | 验证无效（pass_token 过期、流水号已使用等） | 拦截，让用户重新验证 |
| 接口返回 40001 | - | 阿里云服务异常 | 拦截并提示稍后重试 |

---

## 7. 服务端调用示例（Python）

```python
import requests

url = 'http://你的域名/api/captcha_auth/aliyun/verify'
data = {
    'lot_number': '424c60ea0f3b4301aac844ff0066709c',
    'captcha_output': 'Z7diZnyxNCpKC0JzLv92...',
    'pass_token': 'fcb6b3dfba5cf99c5916e305203ecd73...',
    'gen_time': '1788044650',
}
resp = requests.post(url, data=data, timeout=10).json()
if resp['code'] == 10000 and resp['data']['result'] == 'success':
    print('验证通过，放行业务')
else:
    print('验证未通过或服务异常，拦截')
```

---

## 8. 常见问题

### 8.1 前端报错 `Error code: 60500`（服务端 forbidden）

阿里云风控拦截。即使验证答案正确，当检测到单个 IP 短时间频繁操作（如 1 小时内超过 100 次）或环境异常（自动化浏览器、本地 localhost）时也会拦截。

**处理**：停止频繁重试，等待风控冷却；换普通浏览器/网络环境；生产环境正常用户不受影响。

### 8.2 二次校验返回 `fail`，`reason` 为 `pass_token expire`

验证参数有时效性，`pass_token` 过期后无法再校验。**处理**：让用户重新完成一次图形验证。

### 8.3 校验参数能否重复使用

不能。`lot_number` / `pass_token` / `captcha_output` 均为**一次性**，校验成功后立即失效，防止重放攻击。

### 8.4 appKey 如何获取

appKey 由服务端配置，**调用方无需获取**。appKey 仅用于服务端生成二次校验签名，绝不下发客户端，请勿在前端代码中出现。

### 8.5 captcha-client.js 加载失败

检查静态资源是否可访问（`/static/js/captcha_auth/aliyun/captcha-client.js` 应返回 200）；生产环境请确认已部署 WhiteNoise 或等效静态文件服务。

---

## 9. 注意事项

1. **二次校验不可省略**：只做前端验证不调 verify 接口的接入无效，验证参数可被伪造/重放。
2. **appKey 保密**：任何情况下不得暴露在客户端代码、日志或接口响应中。
3. **gen_time 取 SDK 返回值**：直接使用 `getValidate()` 返回的时间戳字段，不要自行拼接。
4. **校验参数一次性**：verify 成功后可销毁前端本地保存的验证参数。
5. **风控机制**：阿里云对高频/异常环境有自动拦截，生产接入请控制触发频率，避免短时间刷量。
