# 小影 API 用户中心系统运行流程说明

> 本文档详细说明小影 API 统一认证中心（UAC，User Center）的运行流程、接入方式、签名机制与安全设计，供各子项目接入时参考。

---

## 一、系统概述

小影 API 用户中心是一套**统一认证中心**，为所有子项目提供集中的用户注册、登录、Token 签发与身份验证能力。任何项目（以下简称"子项目"）的注册 / 登录 / 用户验证都必须先经过用户中心完成统一认证。

**核心设计目标：**

- **用户池全局共享**：所有子项目共享同一套用户账号体系，用户无需在每个项目重复注册
- **账号系统分配**：账号由用户中心统一分配（纯数字 6-12 位、全局唯一、不可自定义、不可修改）
- **Token 绑定项目**：登录签发的 Token 绑定签发项目，不同项目的 Token 互不通用
- **签名防篡改**：所有接口调用必须携带 HMAC-SHA256 签名，防止参数篡改与重放攻击
- **项目级有效期**：Token 默认有效期由各项目在后台独立配置

---

## 二、核心概念

| 概念 | 说明 |
|------|------|
| **用户（User）** | 全局共享用户池中的一条用户记录。包含账号（account）、用户名（username）、密码（哈希存储）、状态（status） |
| **账号（account）** | 系统随机分配的纯数字串，长度 6-12 位，首位不为 0，全局唯一。用户登录凭据之一，不可自定义 |
| **用户名（username）** | 注册时由用户自定义，最长 50 字符。**允许重复**（唯一标识是账号） |
| **接入项目（UserApp）** | 经审核注册后获得接入资格的子项目。每个项目拥有独立的 APPID + APPSECRET |
| **APPID** | 项目公开标识，**系统自动生成**（`app_` 前缀 + 28 位随机 hex，共 32 字符），全局唯一，调用接口时携带，创建后固定不可修改 |
| **APPSECRET** | 项目签名密钥，**系统自动生成**（`sk_` 前缀 + 60 位随机 hex，共 63 字符），仅项目方与用户中心知晓，用于 HMAC-SHA256 签名，创建后固定。**严禁泄露** |
| **Token** | 登录成功后签发的身份凭证，绑定"用户 + 项目"，有过期时间，可主动注销 |
| **签名参数** | app_id / timestamp / nonce / sign 四个参数，所有用户中心接口必带 |

---

## 三、系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                        小影 API 管理后台                       │
│   · 注册接入项目（分配 APPID + APPSECRET）                     │
│   · 配置项目 Token 有效期、启停项目                            │
│   · 封禁 / 解封用户，查看 Token 使用情况                        │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                     用户中心 API 层                           │
│   · POST /api/user_center/users/register   用户注册          │
│   · POST /api/user_center/users/login      用户登录          │
│   · POST /api/user_center/users/logout     用户退出          │
│   · GET  /api/user_center/users/info       获取用户信息       │
│   · POST /api/user_center/users/verify     验证 Token        │
│   · GET  /api/user_center/projects/info    查询项目信息       │
│   每层统一：① 签名校验 → ② 参数校验 → ③ 业务处理 → ④ 统一响应   │
└──────────────▲──────────────────┬───────────────────────────┘
               │                  │
               │ 签名请求          │ 签名请求
        ┌──────┴──────┐   ┌───────▼───────┐
        │   子项目 A    │   │   子项目 B     │
        │ (APPID_A)   │   │  (APPID_B)    │
        └─────────────┘   └───────────────┘
```

---

## 四、运行流程详解

### 4.1 子项目接入流程（前置条件）

任何子项目**必须先接入，才能调用用户中心接口**。

```
步骤 1：子项目方向小影 API 管理员提交接入申请
步骤 2：管理员在后台「接入项目」中创建项目，填写项目名称（全局唯一，不可重复）
步骤 3：系统自动生成唯一的 APPID + APPSECRET（无需手动输入），发放给项目方
步骤 4：项目方确认 Token 默认有效期（默认 7 天，后台可调）
步骤 5：项目方开始调用用户中心接口
```

**密钥自动生成说明：**

- APPID / APPSECRET 由用户中心系统自动生成，**管理员无需也不能手动输入**
- APPID 格式：`app_` + 28 位随机 hex（共 32 字符）
- APPSECRET 格式：`sk_` + 60 位随机 hex（共 63 字符）
- 两者均全局唯一，创建后**固定不可修改**（后台保存时强制保留原值，防止误改导致已接入子项目全部失效）
- 应用名称（name）全局唯一：重复名称创建将被拒绝

**接入后项目方应妥善保管：**

| 凭证 | 格式 | 用途 | 保密级别 |
|------|------|------|----------|
| APPID | `app_` + 28 位随机 hex（32 字符） | 接口调用时公开携带 | 公开 |
| APPSECRET | `sk_` + 60 位随机 hex（63 字符） | 计算签名 | **机密，严禁泄露** |

> 项目停用后（后台 status=false），该项目所有接口调用将直接返回「接入项目已被停用」，已签发的 Token 也随之失效。

---

### 4.2 用户注册流程

```
用户（通过子项目） ──> 子项目 ──POST /users/register──> 用户中心
```

| 步骤 | 动作 | 说明 |
|------|------|------|
| 1 | 子项目收集用户名 + 密码 | username（≤50字符）、password（6-64字符） |
| 2 | 子项目构造签名参数 | app_id / timestamp / nonce / sign（详见第五章） |
| 3 | 子项目调用注册接口 | 请求体：`application/x-www-form-urlencoded` 表单 |
| 4 | 用户中心校验签名 | 失败返回 20011（签名参数缺失 / 过期 / 不匹配 / 项目未注册或停用） |
| 5 | 用户中心校验参数 | username 缺失→20001；长度超限→20002；password 缺失→20001；长度不符→20002 |
| 6 | 系统分配账号 | 随机生成 6-12 位纯数字账号（首位非 0），保证全局唯一 |
| 7 | 密码加密存储 | PBKDF2 加盐哈希（`make_password`），**绝不存储明文** |
| 8 | 创建用户 | 写入全局用户池，status 默认启用 |
| 9 | 返回结果 | 成功返回 `{user_id, account, username}`；账号需展示给用户用于后续登录 |

**注册成功响应示例：**

```json
{
  "code": 10000,
  "msg": "注册成功",
  "data": {
    "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "account": "837120465",
    "username": "test_user"
  }
}
```

**要点：**
- 注册**不签发 Token**，用户需调用登录接口获取 Token
- 用户名允许重复（相同用户名可对应不同账号），系统不以此为唯一标识
- 极端并发下账号唯一冲突时，系统自动重试重新生成账号（最多 3 次）

---

### 4.3 用户登录流程

```
用户 ──> 子项目 ──POST /users/login──> 用户中心
              <──────── Token + 用户信息 <────────
```

| 步骤 | 动作 | 说明 |
|------|------|------|
| 1 | 子项目收集账号 + 密码 | account（系统分配账号）、password |
| 2 | 构造签名参数并调用 | 表单提交 account/password/app_id/timestamp/nonce/sign |
| 3 | 签名校验 | 失败返回 20011 |
| 4 | 参数校验 | account / password 缺失→20001 |
| 5 | 查询用户 | 按 account 查询全局用户池 |
| 6 | 校验状态与密码 | 用户被封禁→20011「账号已被封禁」；密码错误→20011「账号或密码错误」 |
| 7 | 签发 Token | 生成 64 位 hex 随机 Token，绑定（用户, 项目, 过期时间） |
| 8 | 计算过期时间 | `当前时间 + 项目 token_expire_days`（项目可配，默认 7 天） |
| 9 | 返回结果 | 返回 `{user_id, account, username, token, expire_time}` |

**登录成功响应示例：**

```json
{
  "code": 10000,
  "msg": "登录成功",
  "data": {
    "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "account": "837120465",
    "username": "test_user",
    "token": "5f4dcc3b5aa765d61d8327deb882cf99e6a3c8a4b1f9e2d4c6a8b0c1d2e3f4a5",
    "expire_time": "2026-09-06 12:00:00"
  }
}
```

**安全要点：**
- 账号或密码错误时**统一提示**「账号或密码错误」，不暴露账号是否存在（防账号枚举）
- Token 只绑定当前项目：同一用户在不同项目登录会得到**不同**的 Token，且不能跨项目使用
- 支持多端并存：同一用户在同一项目可同时持有多个有效 Token（并发数由子项目自行控制）
- Token 过期时间以服务器时间为准，返回格式 `yyyy-MM-dd HH:mm:ss`

---

### 4.4 验证 Token 流程（子项目核心调用）

子项目在每次需要确认用户身份时（如访问受保护资源），调用验证接口。

```
用户请求子项目受保护资源（携带 Token）
         │
         ▼
子项目 ──POST /users/verify──> 用户中心
              <── {valid:true, user_id, account, username} <──
         │
         ▼
子项目放行 / 拒绝
```

| 步骤 | 动作 | 说明 |
|------|------|------|
| 1 | 子项目携带用户 Token 调用验证接口 | 表单：token + 签名参数 |
| 2 | 签名校验 | 失败返回 20011 |
| 3 | 参数校验 | token 缺失→20001 |
| 4 | 查询 Token | 必须在当前项目下（`app + token` 联合查询） |
| 5 | 有效性检查 | 过期 / 用户封禁 / 项目停用 → 任一即判定失效 |
| 6 | 更新活跃时间 | 记录 last_active_time 便于后台审计 |
| 7 | 返回身份 | `{valid: true, user_id, account, username}` |

**验证成功响应示例：**

```json
{
  "code": 10000,
  "msg": "Token 有效",
  "data": {
    "valid": true,
    "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "account": "837120465",
    "username": "test_user"
  }
}
```

**Token 失效原因对照：**

| 场景 | 返回码 | 提示 |
|------|--------|------|
| Token 不存在或不属于当前项目 | 20010 | Token 无效: 不存在或不属于当前项目 |
| Token 已过期 | 20010 | Token 已失效: 已过期 / 用户封禁 / 项目停用 |
| 用户被后台封禁 | 20010 | Token 已失效: 已过期 / 用户封禁 / 项目停用 |
| 项目被后台停用 | 20011 | 接入项目已被停用（签名层直接拦截） |

---

### 4.5 获取用户信息流程

查询类接口，携带 Token 获取当前用户的账号与用户名。

```
子项目 ──GET /users/info?token=xxx&签名参数──> 用户中心
              <── {user_id, account, username, expire_time} <──
```

**说明：**
- 与验证接口的区别：验证接口返回 `valid` 标记（面向子项目身份确认），信息接口返回 Token 的过期时间（面向用户展示）
- 校验逻辑相同：Token 必须属于当前项目且未失效
- 失败场景与 4.4 一致（20010 / 20011 / 20001）

**成功响应示例：**

```json
{
  "code": 10000,
  "msg": "查询成功",
  "data": {
    "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "account": "837120465",
    "username": "test_user",
    "expire_time": "2026-09-06 12:00:00"
  }
}
```

---

### 4.6 用户退出流程

```
子项目 ──POST /users/logout──> 用户中心
              <── 删除 Token <──
```

| 步骤 | 动作 | 说明 |
|------|------|------|
| 1 | 子项目携带用户 Token 调用退出接口 | 表单：token + 签名参数 |
| 2 | 签名校验 | 失败返回 20011 |
| 3 | 参数校验 | token 缺失→20001 |
| 4 | 删除 Token | 仅删除**当前项目下**该 Token 记录 |
| 5 | 返回结果 | 成功返回 code=10000，data 为 null |

**说明：**
- 退出为**立即生效**：删除后该 Token 无法再通过验证 / 信息接口
- 跨项目不影响：只删除当前项目绑定的 Token，其他项目的 Token 不受影响
- 对不存在 / 已失效 / 不属于当前项目的 Token 调用退出，返回 20003「Token 不存在或不属于当前项目」（不会报服务器错误）

---

### 4.7 查询项目信息流程

子项目核对自身配置时调用。

```
子项目 ──GET /projects/info?app_id&timestamp&nonce&sign──> 用户中心
              <── {project_id, name, app_id, token_expire_days, status} <──
```

**成功响应示例：**

```json
{
  "code": 10000,
  "msg": "查询成功",
  "data": {
    "project_id": "6d5f2a9e-1234-4b56-8c90-abcdef123456",
    "name": "我的子项目",
    "app_id": "app_5f3a9c2b7e6d8f1a2b3c4d5e6f7a8b9c",
    "token_expire_days": 7,
    "status": true
  }
}
```

---

## 五、签名机制（重要）

所有用户中心接口调用都必须携带 4 个签名公共参数，用于**身份识别 + 防篡改 + 防重放**。

### 5.1 签名公共参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| app_id | string | 是 | 项目 APPID（后台自动生成，`app_` 前缀） |
| timestamp | string | 是 | 10 位时间戳（秒），与服务器时间差须在 ±5 分钟内 |
| nonce | string | 是 | 随机字符串，每次请求唯一（建议 16+ 位随机 hex） |
| sign | string | 是 | 签名值（64 位小写 hex） |

### 5.2 签名算法（HMAC-SHA256）

```
1. 取除 sign 外的所有参数（含 app_id / timestamp / nonce / 业务参数）
2. 按键名 ASCII 升序排序
3. 拼接为 key=value&key=value&...
4. 以 app_secret 为密钥做 HMAC-SHA256
5. 输出小写 hex 字符串即为 sign
```

### 5.3 Python 签名示例

```python
import hashlib, hmac, time, secrets, urllib.parse

def build_sign(params: dict, app_secret: str) -> str:
    """生成签名（小写 hex）"""
    items = sorted((k, str(v)) for k, v in params.items()
                   if k != 'sign' and v not in (None, ''))
    raw = '&'.join(f'{k}={v}' for k, v in items)
    return hmac.new(app_secret.encode(), raw.encode(), hashlib.sha256).hexdigest()

# 登录示例（APPID / APPSECRET 由用户中心后台自动生成并发放）
params = {
    'app_id': 'app_5f3a9c2b7e6d8f1a2b3c4d5e6f7a8b9c',
    'timestamp': str(int(time.time())),
    'nonce': secrets.token_hex(8),
    'account': '837120465',
    'password': '123456',
}
params['sign'] = build_sign(params, 'sk_9c8b7a6f5e4d3c2b1a0f9e8d7c6b5a4f0e1d2c3b4a596877')

# 发送请求（表单）
url = 'https://your-domain/api/user_center/users/login'
body = urllib.parse.urlencode(params)
```

### 5.4 安全校验规则

| 校验项 | 失败返回 |
|--------|----------|
| 四个签名参数必须同时提供 | 20011 签名参数缺失 |
| timestamp 必须为数字 | 20011 参数格式错误: timestamp 必须为 10 位时间戳(秒) |
| timestamp 与服务器时间差 ≤ ±5 分钟 | 20011 签名过期: timestamp 超出有效窗口(±5分钟) |
| app_id 必须已注册 | 20011 未注册的接入项目: app_id 不存在 |
| 项目必须处于启用状态 | 20011 接入项目已被停用 |
| sign 必须与本地计算一致（常数时间比较，防时序攻击） | 20011 签名校验失败: sign 不匹配 |

**防重放说明：**
- timestamp 窗口（±5 分钟）+ nonce 唯一性：同一 nonce 在窗口内重复使用会被识别
- 校验使用 `hmac.compare_digest` 常数时间比较，防止时序侧信道攻击
- 建议子项目每次请求都生成全新 nonce

---

## 六、统一响应格式与状态码

### 6.1 统一响应格式

所有接口返回 HTTP 200 + JSON：

```json
{
  "code": 10000,
  "msg": "成功",
  "data": { }
}
```

### 6.2 用户中心相关状态码

| code | 含义 | 说明 |
|------|------|------|
| 10000 | 成功 | 业务处理成功 |
| 20001 | 参数缺失 | 缺少必填参数（如 username / password / token） |
| 20002 | 参数格式错误 | 参数长度 / 类型不合法（如 username 超 50 字符、password 长度不符） |
| 20003 | 参数值非法 | 参数值不符合业务规则（如退出的 Token 不存在） |
| 20010 | 未认证 | Token 无效 / 已过期 / 用户封禁 |
| 20011 | 认证失败 | 签名校验失败 / 账号密码错误 / 账号封禁 / 项目停用 |
| 405 | 方法不允许 | 使用错误 HTTP 方法访问接口 |

**状态码分类规则：** 1xxxx=成功，2xxxx=客户端错误，3xxxx=业务逻辑错误，4xxxx=外部服务错误，5xxxx=系统内部错误。

---

## 七、安全设计要点

1. **密码安全**：PBKDF2 加盐哈希存储，永不存储明文；登录统一错误提示防账号枚举
2. **签名防篡改**：HMAC-SHA256 覆盖全部业务参数，任何参数被修改都会导致签名校验失败
3. **重放防护**：timestamp ±5 分钟窗口 + nonce 唯一性
4. **Token 隔离**：Token 绑定项目，跨项目不可用；伪造 / 超长 / 未知 Token 一律按无效处理
5. **状态联动**：用户封禁 → 该用户所有 Token 立即失效；项目停用 → 该项目所有 Token 失效
6. **接口方法限制**：注册 / 登录 / 退出 / 验证仅允许 POST，信息查询仅允许 GET，违规返回 405
7. **传输安全**：建议全站 HTTPS，防止请求参数与 Token 在传输中被窃听
8. **密钥管理**：APPSECRET 严禁写入前端代码 / 提交到仓库，子项目后端保管

---

## 八、接口总览

| 方法 | 路径 | 目录 | 功能 | 请求体 |
|------|------|------|------|--------|
| POST | /api/user_center/users/register | 用户 API | 用户注册（系统分配账号） | 表单 |
| POST | /api/user_center/users/login | 用户 API | 用户登录（签发 Token） | 表单 |
| POST | /api/user_center/users/logout | 用户 API | 用户退出（注销 Token） | 表单 |
| GET | /api/user_center/users/info | 用户 API | 获取用户信息 | Query |
| POST | /api/user_center/users/verify | 用户 API | 验证 Token | 表单 |
| GET | /api/user_center/projects/info | 项目 API | 查询项目自身信息 | Query |

---

## 九、典型接入时序（完整示例）

以下演示子项目"视频分析站"接入用户中心的完整调用序列：

```
① 接入：小影管理员后台创建项目「视频分析站」，系统自动生成并发放
   APPID = app_5f3a9c2b7e6d8f1a2b3c4d5e6f7a8b9c
   APPSECRET = sk_9c8b7a6f5e4d3c2b1a0f9e8d7c6b5a4f0e1d2c3b4a596877

② 用户注册（用户首次使用）：
   子项目表单提交 {username: "张三", password: "abc123", app_id, timestamp, nonce, sign}
   ← 返回 {user_id, account: "837120465", username: "张三"}
   子项目展示「您的账号为：837120465，请妥善保管」

③ 用户登录：
   子项目表单提交 {account: "837120465", password: "abc123", app_id, timestamp, nonce, sign}
   ← 返回 {user_id, account, username, token: "t_xxxx...", expire_time}
   子项目将 token 返回给用户端（前端）保存

④ 用户访问受保护功能（如发起视频分析）：
   用户携带 token 请求子项目 → 子项目 POST /users/verify {token, 签名参数}
   ← 返回 {valid: true, user_id, account, username}
   子项目确认身份后放行，将 user_id 与业务数据关联

⑤ 用户退出登录：
   用户点击退出 → 子项目 POST /users/logout {token, 签名参数}
   ← 返回 code=10000
   该 token 立即失效
```

---

## 十、常见问题（FAQ）

**Q1：用户名可以重复吗？**
可以。用户唯一标识是系统分配的账号（account），用户名允许重复，不同用户可同名。

**Q2：账号能自己改吗？**
不能。账号由系统随机分配（纯数字 6-12 位、全局唯一），不可自定义、不可修改。

**Q3：忘记账号怎么办？**
账号在注册成功后由系统返回，建议子项目在注册成功页面向用户明确展示并提示保存。

**Q4：Token 有效期如何配置？**
在管理后台「接入项目」中修改该项目 token_expire_days（默认 7 天），修改后新签发的 Token 按新配置生效。

**Q5：用户被封禁后，已签发的 Token 会怎样？**
立即失效。该用户的所有 Token（所有项目）在验证 / 信息接口均返回失效。

**Q6：项目被停用后，已签发的 Token 会怎样？**
该项目的所有接口调用（含签名层）直接返回「接入项目已被停用」，Token 随之失效。

**Q7：签名计算时哪些参数要参与？**
除 sign 自身外，所有请求参数（app_id、timestamp、nonce 以及业务参数）都要参与排序与拼接，缺失任何一个都会导致签名不匹配。

**Q8：timestamp 为什么不能用本地时间？**
服务器校验时与服务器时间比对（±5 分钟）。子项目应使用服务器下发的标准时间或 NTP 校时，避免客户端时钟偏差导致签名过期。

---

*文档版本：v1.0  ·  适用系统：小影 API 用户中心（UAC）*
