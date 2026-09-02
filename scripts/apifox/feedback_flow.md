# 小影 API 问题反馈中心系统运行流程说明

> 本文档详细说明小影 API 问题反馈中心（Feedback Center）的运行流程、接入方式、数据隔离、签名与身份校验机制、安全设计，供各子项目接入时参考。

---

## 一、系统概述

小影 API 问题反馈中心是一套**多租户问题反馈系统**，为所有子项目提供集中的问题反馈收集、评论回复、状态流转与广场展示能力。任何子项目（以下简称"子项目"）的用户均可通过子项目搭建的反馈广场提交问题、参与讨论，站长可在统一广场集中查看、跟进所有子项目的反馈，无需逐个访问子项目。

**核心设计目标：**

- **数据按项目隔离**：反馈数据以子项目（UserApp）为租户维度，子项目之间互不可见
- **项目内公开**：同一子项目内的所有用户可见该项目的全部反馈与评论（类似 GitHub Issues）
- **评论树（无限嵌套）**：A 提问题 → B 评论 → C 回复 B → D 回复 C……支持任意层级嵌套；站长同样可参与（回复问题或回复任意评论），所有评论**项目内全部人可见**
- **身份真实性校验**：提交反馈 / 评论 / 回复必须携带用户登录 Token，评论人身份以 Token 校验结果为准，子项目无法伪造用户 ID
- **签名防篡改**：所有接口调用必须携带 HMAC-SHA256 签名，防止参数篡改与重放攻击
- **评论分级分页**：一级评论按页返回（默认 20 条 / 页，最大 100），每条一级评论内嵌**二级评论首页**（默认 5 条，取全部子孙中时间最前 N 条）；某条评论的**全部二级评论**（无论嵌套多深，B、C、D……均属二级评论，不分三级/N级）通过「评论回复列表」接口分页获取，单条反馈数千上万条评论时接口性能稳定
- **站长统一广场**：站长在管理后台集中查看所有子项目反馈，支持筛选、状态流转、回复、删除

---

## 二、核心概念

| 概念 | 说明 |
|------|------|
| **反馈（Feedback）** | 一条问题记录。包含所属项目（app）、反馈用户（user）、标题（title）、内容（content）、状态（status） |
| **评论（FeedbackReply）** | 反馈下的讨论记录，支持无限嵌套的评论树。包含所属反馈（feedback）、父评论（parent）、评论者（user）、身份类型（author_role）、内容（content）。**语义只有一级/二级两类**：直接评论问题=一级（parent 空）；回复在别人评论底下=二级（parent 非空，**无论嵌套多深**，不存在三级/N级） |
| **父评论（parent）** | 自引用关系。为空=一级评论（直接评论问题）；非空=回复某条评论（可回复任意层级）。删除父评论会级联删除其全部子孙回复 |
| **身份类型（author_role）** | `user`=子项目用户评论 / `admin`=站长回复。站长回复时 user 为空，展示名为「站长」 |
| **状态（status）** | `pending` 待处理 / `processing` 处理中 / `resolved` 已解决 / `closed` 已关闭，由站长在后台流转 |
| **接入项目（UserApp）** | 经审核注册后获得接入资格的子项目。每个项目拥有独立的 APPID + APPSECRET |
| **APPID** | 项目公开标识，**系统自动生成**（`app_` 前缀 + 28 位随机 hex，共 32 字符），全局唯一，调用接口时携带，创建后固定不可修改 |
| **APPSECRET** | 项目签名密钥，**系统自动生成**（`sk_` 前缀 + 60 位随机 hex，共 63 字符），用于 HMAC-SHA256 签名，创建后固定。**严禁泄露** |
| **用户 Token** | 用户在用户中心登录后签发的身份凭证，绑定「用户 + 项目」。提交反馈 / 评论 / 回复时必须携带，用于校验评论人身份真实性 |
| **签名参数** | app_id / timestamp / nonce / sign 四个参数，所有反馈中心接口必带 |

---

## 三、系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                        小影 API 管理后台                       │
│   · 注册接入项目（分配 APPID + APPSECRET）                     │
│   · 统一反馈广场：集中查看所有子项目反馈（按项目/状态/时间筛选）  │
│   · 状态流转：待处理 → 处理中 → 已解决 / 已关闭                 │
│   · 站长回复：可回复问题或回复任意评论（进入评论树）             │
│   · 删除反馈与评论（仅站长）                                   │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                   问题反馈中心 API 层                         │
│   · POST /api/feedback/create   提交反馈                      │
│   · POST /api/feedback/reply    追加/回复评论（parent_id 嵌套）│
│   · GET  /api/feedback/list     项目内反馈列表（分页）          │
│   · GET  /api/feedback/detail   反馈详情+评论树（一级+二级首页）│
│   · GET  /api/feedback/replies  评论回复列表（二级评论，全部子孙）  │
│   每层统一：① 签名校验 → ② 参数校验 → ③ 身份校验 → ④ 业务处理 → ⑤ 统一响应 │
└──────────────▲──────────────────┬───────────────────────────┘
               │                  │
               │ 签名请求          │ 签名请求
        ┌──────┴──────┐   ┌───────▼───────┐
        │   子项目 A    │   │   子项目 B     │
        │ (APPID_A)   │   │  (APPID_B)    │
        │ 只看项目 A    │   │ 只看项目 B    │
        └─────────────┘   └───────────────┘
```

> 所有接口均需签名；`create` / `reply` 另需用户 Token 校验身份真实性。数据以 APPID 为租户维度隔离：子项目 A 的反馈对子项目 B 不可见。

---

## 四、运行流程详解

### 4.1 子项目接入流程（前置条件）

任何子项目**必须先接入，才能调用问题反馈中心接口**。

```
步骤 1：子项目方向小影 API 管理员提交接入申请
步骤 2：管理员在后台「接入项目」中创建项目，系统自动生成唯一的 APPID + APPSECRET
步骤 3：子项目用户需先在用户中心注册/登录（获取用户 Token），后续提交反馈需携带
步骤 4：子项目调用反馈中心接口
```

**接入后项目方应妥善保管：**

| 凭证 | 格式 | 用途 | 保密级别 |
|------|------|------|----------|
| APPID | `app_` + 28 位随机 hex（32 字符） | 接口调用时公开携带 | 公开 |
| APPSECRET | `sk_` + 60 位随机 hex（63 字符） | 计算签名 | **机密，严禁泄露** |

> 部署注意：反馈中心接口依赖签名认证，上线后请在后台将「问题反馈中心」分类设为**需要认证**（auth），否则接口将返回 20011「接口未配置项目认证，无法识别接入项目」。
>
> 项目停用后（后台 status=false），该项目所有接口调用将直接返回「接入项目已被停用」。

---

### 4.2 提交反馈流程

```
子项目用户 ──> 子项目 ──POST /api/feedback/create──> 反馈中心
                    <── {feedback_id, status: "pending"} <──
```

**请求方式：** 表单提交（application/x-www-form-urlencoded）

| 参数 | 必填 | 说明 |
|------|------|------|
| title | 是 | 反馈标题，1-100 字符 |
| content | 是 | 反馈内容（纯文本） |
| token | 是 | 用户登录 Token（UAC 签发，绑定当前项目），用于校验反馈人身份真实性 |
| app_id / timestamp / nonce / sign | 是 | 签名公共参数 |

| 步骤 | 动作 | 说明 |
|------|------|------|
| 1 | 子项目收集反馈内容 | title（1-100 字符）、content（纯文本） |
| 2 | 子项目构造签名参数 | app_id / timestamp / nonce / sign（详见第五章） |
| 3 | 子项目调用提交接口 | 表单：title + content + token + 签名参数 |
| 4 | 反馈中心校验签名 | 失败返回 20011（签名参数缺失 / 过期 / 不匹配 / 项目未注册或停用） |
| 5 | 反馈中心校验参数 | title 缺失→20001；title 超 100 字符→20002；content 缺失→20001 |
| 6 | 校验用户 Token 真实性 | Token 缺失→20001；伪造 / 过期 / 跨项目→20010（详见 5.4） |
| 7 | 创建反馈 | 状态初始为 `pending`，反馈人身份以 Token 校验结果为准（**忽略子项目自传的用户身份**） |
| 8 | 返回结果 | 返回 `{feedback_id, status}` |

**成功响应示例：**

```json
{
  "code": 10000,
  "msg": "反馈已提交",
  "data": {
    "feedback_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "status": "pending"
  }
}
```

**要点：**
- 反馈人（user）由 Token 校验确定，**子项目无法伪造用户 ID**；即便子项目后端被攻破，也无法冒充任意用户提交反馈
- 反馈创建后状态为 `pending`，后续由站长在后台流转状态

---

### 4.3 追加 / 回复评论流程（评论树，无限嵌套）

```
子项目用户 ──> 子项目 ──POST /api/feedback/reply──> 反馈中心
                    <── {reply_id} <──
```

**请求方式：** 表单提交（application/x-www-form-urlencoded）

| 参数 | 必填 | 说明 |
|------|------|------|
| feedback_id | 是 | 反馈唯一 ID（提交反馈接口返回） |
| content | 是 | 评论内容（纯文本） |
| parent_id | 否 | 被回复的评论 ID。**为空=一级评论**（直接评论问题）；**非空=回复指定评论**，支持任意层级嵌套 |
| token | 是 | 用户登录 Token（绑定当前项目） |
| app_id / timestamp / nonce / sign | 是 | 签名公共参数 |

| 步骤 | 动作 | 说明 |
|------|------|------|
| 1 | 子项目收集评论内容 | feedback_id + content + parent_id(可选) |
| 2 | 构造签名参数并调用 | 表单：feedback_id + content + parent_id + token + 签名参数 |
| 3 | 签名校验 | 失败返回 20011 |
| 4 | 参数校验 | feedback_id / content 缺失→20001 |
| 5 | 校验用户 Token 真实性 | 伪造 / 过期 / 跨项目→20010 |
| 6 | 校验反馈归属 | 反馈不存在 **或不属于当前项目**→20030「反馈不存在或不属于当前项目」 |
| 7 | 校验父评论（若传 parent_id） | 父评论不存在 / 不属于当前反馈→20030「父评论不存在或不属于当前反馈」 |
| 8 | 创建评论 | author_role = `user`，评论者身份以 Token 校验结果为准，挂载到父评论下（若无 parent 则为一级评论） |
| 9 | 返回结果 | 返回 `{reply_id}`（可作为后续回复的 parent_id） |

**评论树结构说明：**

```
反馈（A 提出问题）
 ├─ 评论 B（parent_id 为空，一级）
 │   ├─ 回复 C（parent_id = B）      ← 二级
 │   │   └─ 回复 D（parent_id = C）  ← 二级（无论多深均属二级）
 │   └─ 回复 E（parent_id = B）
 └─ 评论 F（parent_id 为空，一级）
```

- 同一反馈下所有评论组成**评论树**，**项目内全部人可见**
- 支持**无限嵌套**：可回复任意层级的评论（不限制深度）
- 站长在后台回复时同样进入评论树（`author_role = "admin"`，可回复问题或回复任意评论）
- 每个用户可多次评论 / 回复（无次数限制）
- 删除父评论会**级联删除**其全部子孙回复

---

### 4.4 查询反馈列表流程

子项目广场页据此渲染反馈列表。

```
子项目 ──GET /api/feedback/list?status=&page=&page_size=&签名参数──> 反馈中心
                    <── {total, page, page_size, total_pages, items} <──
```

**查询参数（query string）：**

| 参数 | 必填 | 说明 |
|------|------|------|
| status | 否 | 状态筛选：pending / processing / resolved / closed，缺省返回全部 |
| page | 否 | 页码，从 1 开始，默认 1 |
| page_size | 否 | 每页条数，默认 10，最大 100 |
| app_id / timestamp / nonce / sign | 是 | 签名公共参数 |

**数据隔离：** 只返回**当前项目（app_id）**下的反馈，子项目之间互不可见。

**成功响应示例：**

```json
{
  "code": 10000,
  "msg": "查询成功",
  "data": {
    "total": 1,
    "page": 1,
    "page_size": 10,
    "total_pages": 1,
    "items": [
      {
        "feedback_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "title": "登录页白屏",
        "status": "pending",
        "username": "test_user",
        "reply_count": 3,
        "create_time": "2026-09-01 12:00:00"
      }
    ]
  }
}
```

**说明：**
- 列表按创建时间**倒序**（最新反馈在前）
- `reply_count` 为该反馈**评论总数**（所有嵌套层级，含站长回复），由数据库聚合一次得出，无 N+1 查询
- `status` 传非法值时不筛选，返回全部（不报错）
- 分页参数非法时自动归一化（非数字→默认值，负数→1，超大→上限 100）

---

### 4.5 查询反馈详情流程（评论树）

子项目广场页据此渲染反馈详情与评论区。

```
子项目 ──GET /api/feedback/detail?feedback_id=&page=&page_size=&签名参数──> 反馈中心
                    <── {feedback_id, title, content, status, username, create_time,
                         total, page, page_size, total_pages, replies(一级+二级首页)} <──
```

**查询参数（query string）：**

| 参数 | 必填 | 说明 |
|------|------|------|
| feedback_id | 是 | 反馈唯一 ID |
| page | 否 | **一级评论**页码，从 1 开始，默认 1 |
| page_size | 否 | 每页条数，默认 20，最大 100 |
| app_id / timestamp / nonce / sign | 是 | 签名公共参数 |

**评论语义与分页说明（重要，防海量评论撑爆响应）：**
- 评论只有两类：**一级评论**=直接评论问题的评论（parent 为空）；**二级评论**=所有回复在别人评论底下的评论，**无论嵌套多深**（B 回复 A、C 回复 B、D 回复 C……全部算二级评论，不存在三级/N级概念）
- **一级评论**按创建时间**正序分页**返回（查看最新一级评论请翻到最后一页，`page = total_pages`）
- 每条一级评论**内嵌二级评论首页**（默认 5 条，正序）：取该一级评论**全部子孙**按时间正序的前 N 条，深层回复（如 D）也会出现在首页
- 每条评论带 `parent_id`（标明回复了谁）、`children_total`（直接子回复数）、`reply_total`（二级评论总数=全部子孙数）
- 内嵌的二级评论**不再递归嵌套**（`replies` 为空数组）；该一级评论的**全部二级评论**通过「评论回复列表」接口（见 4.6）按 `parent_id` 分页获取
- `total` / `total_pages` 指**一级评论**的分页信息

**成功响应示例：**

```json
{
  "code": 10000,
  "msg": "查询成功",
  "data": {
    "feedback_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "title": "登录页白屏",
    "content": "点击登录后页面无响应",
    "status": "pending",
    "username": "test_user",
    "create_time": "2026-09-01 12:00:00",
    "total": 1,
    "page": 1,
    "page_size": 20,
    "total_pages": 1,
    "replies": [
      {
        "reply_id": "6b1f2e9a-3c4d-4e5f-8a9b-0c1d2e3f4a5b",
        "parent_id": "",
        "author_role": "user",
        "username": "test_user",
        "content": "B: 我遇到过",
        "create_time": "2026-09-01 12:05:00",
        "reply_total": 2,
        "children_total": 1,
        "replies": [
          {
            "reply_id": "7c2f3e9b-4d5e-5f6a-9b0c-1d2e3f4a5b6c",
            "parent_id": "6b1f2e9a-3c4d-4e5f-8a9b-0c1d2e3f4a5b",
            "author_role": "user",
            "username": "other_user",
            "content": "C: 怎么解决的",
            "create_time": "2026-09-01 12:06:00",
            "reply_total": 1,
            "children_total": 1,
            "replies": []
          },
          {
            "reply_id": "8d3f4e9c-5e6f-6a7b-9c0d-1e2f3a4b5c6d",
            "parent_id": "7c2f3e9b-4d5e-5f6a-9b0c-1d2e3f4a5b6c",
            "author_role": "user",
            "username": "test_user",
            "content": "D: 重启就好了",
            "create_time": "2026-09-01 12:07:00",
            "reply_total": 0,
            "children_total": 0,
            "replies": []
          }
        ]
      }
    ]
  }
}
```

**说明：**
- `replies` 中每条评论的 `author_role`：`user`=子项目用户（username 为评论者用户名）/ `admin`=站长（username 固定为「站长」）
- `parent_id`：该评论回复的父评论 ID（一级评论为空字符串）；`children_total`：**直接子回复数**（直接回复本条评论的条数）；`reply_total`：**二级评论总数**（本条评论下的全部子孙回复数，无论嵌套多深）
- 上面示例中，D 回复了 C（而非直接回复 B），但**同样属于 B 的二级评论**，会出现在 B 内嵌的二级评论首页
- 服务端**一次查询 + 内存建树**组装评论树，无逐层查询、无递归深度限制；返回体大小恒定（一级 20 条 × 二级评论首页 5 条），单条一级评论上万条回复也不影响详情接口
- 跨项目查询返回 20030「反馈不存在或不属于当前项目」

---

### 4.6 查询评论回复列表流程（二级评论，分页）

详情接口只内嵌二级评论首页（全部子孙前 5 条），本接口用于**分页查看某条评论的全部二级评论**。

**评论语义**：二级评论=所有回复在别人评论底下的评论，**无论嵌套多深**。因此本接口返回 `parent_id` 的**全部子孙回复**（B 回复 A、C 回复 B、D 回复 C……全部返回），扁平列表按时间正序分页，**不存在三级/N级概念**；每条带 `parent_id` 标明它回复了谁。

```
子项目 ──GET /api/feedback/replies?feedback_id=&parent_id=&page=&page_size=&签名参数──> 反馈中心
                    <── {parent_id, total, page, page_size, total_pages, items} <──
```

**查询参数（query string）：**

| 参数 | 必填 | 说明 |
|------|------|------|
| feedback_id | 是 | 反馈唯一 ID |
| parent_id | 是 | 被查看的评论 ID（该评论的全部二级评论），可为**任意层级**评论的 reply_id |
| page | 否 | 页码，从 1 开始，默认 1 |
| page_size | 否 | 每页条数，默认 20，最大 100 |
| app_id / timestamp / nonce / sign | 是 | 签名公共参数 |

**分页说明：**
- 返回 `parent_id` 的**全部子孙回复**分页（按时间正序，与详情接口内嵌首页排序一致，翻页连续）
- 每条回复含 `parent_id`（回复了谁）、`reply_total`（该评论的全部子孙数）与 `children_total`（直接子回复数），**不含递归嵌套**
- 查看任意一条子孙评论的二级评论：以其 `reply_id` 作为新的 `parent_id` 再次调用本接口

**成功响应示例（查看一级评论 B 的全部二级评论）：**

```json
{
  "code": 10000,
  "msg": "查询成功",
  "data": {
    "parent_id": "6b1f2e9a-3c4d-4e5f-8a9b-0c1d2e3f4a5b",
    "total": 2,
    "page": 1,
    "page_size": 20,
    "total_pages": 1,
    "items": [
      {
        "reply_id": "7c2f3e9b-4d5e-5f6a-9b0c-1d2e3f4a5b6c",
        "parent_id": "6b1f2e9a-3c4d-4e5f-8a9b-0c1d2e3f4a5b",
        "author_role": "user",
        "username": "other_user",
        "content": "C: 怎么解决的",
        "create_time": "2026-09-01 12:06:00",
        "reply_total": 1,
        "children_total": 1,
        "replies": []
      },
      {
        "reply_id": "8d3f4e9c-5e6f-6a7b-9c0d-1e2f3a4b5c6d",
        "parent_id": "7c2f3e9b-4d5e-5f6a-9b0c-1d2e3f4a5b6c",
        "author_role": "user",
        "username": "test_user",
        "content": "D: 重启就好了",
        "create_time": "2026-09-01 12:07:00",
        "reply_total": 0,
        "children_total": 0,
        "replies": []
      }
    ]
  }
}
```

> 示例中 D 回复的是 C（并非直接回复 B），但同样属于 B 的二级评论，会与本页一起返回——这正是"二级评论=全部子孙，不分层级"的体现。

**说明：**
- `feedback_id` 不存在或不属于当前项目 → 20030「反馈不存在或不属于当前项目」
- `parent_id` 不存在 / 不属于该反馈 → 20030「父评论不存在或不属于当前反馈」
- 分页参数非法时自动归一化（同详情接口），不报错

**二级评论分页读取逻辑（前端渲染视角）：**

以「一级评论 B 下有 123 条二级评论（含深层的 C、D…）」为例，前端完整读取流程：

```
① 加载评论区：调用详情接口，一级评论分页渲染（默认 20 条 / 页）；
   每条一级评论内嵌二级评论首页（默认 5 条，全部子孙中按时间正序的前 5 条），
   并返回 reply_total=123（二级评论总数）
② 判断是否展示入口：123 > 5（内嵌首页条数）→ 评论 B 下渲染「查看全部 123 条回复」
③ 用户点击入口 → 调用 /replies 拉取第 1 页：
   GET /api/feedback/replies?feedback_id=...&parent_id=B&page=1&page_size=20
   ← 返回 {total: 123, page: 1, page_size: 20, total_pages: 7, items: 20 条}
   （items 是 B 的全部子孙，无论嵌套多深，每条带 parent_id 标明回复了谁）
④ 继续翻页：page(1) < total_pages(7) → 渲染「下一页」，依次请求 page=2、3……7，直至取全
⑤ 查看某条子孙评论自己的二级评论：以它的 reply_id 作为新的 parent_id 再次调用 /replies
```

- 内嵌二级评论首页与 /replies 分页均按创建时间正序，翻页连续、不重不漏
- 是否还有更多回复依据 `reply_total` / `total` 判断，无需额外接口
- 任意层级的回复量（千、万、十万级）都无需一次性加载，不影响单次接口响应大小

**接口调用示例（Python，含签名）：**

```python
import hashlib, hmac, time, secrets, urllib.parse, urllib.request

APP_ID = 'app_5f3a9c2b7e6d8f1a2b3c4d5e6f7a8b9c'
APP_SECRET = 'sk_9c8b7a6f5e4d3c2b1a0f9e8d7c6b5a4f0e1d2c3b4a596877'

def build_sign(params: dict, app_secret: str) -> str:
    """生成签名（小写 hex）"""
    items = sorted((k, str(v)) for k, v in params.items()
                   if k != 'sign' and v not in (None, ''))
    raw = '&'.join(f'{k}={v}' for k, v in items)
    return hmac.new(app_secret.encode(), raw.encode(), hashlib.sha256).hexdigest()

def signed_get(url, **params):
    """带签名 GET 请求，返回 JSON 文本"""
    params.update({'app_id': APP_ID,
                   'timestamp': str(int(time.time())),
                   'nonce': secrets.token_hex(8)})
    params['sign'] = build_sign(params, APP_SECRET)
    qs = urllib.parse.urlencode(params)
    return urllib.request.urlopen(f'{url}?{qs}').read().decode()

# ① 反馈详情：一级评论第 1 页（每条一级评论内嵌二级评论首页 5 条）
detail = signed_get('https://your-domain/api/feedback/detail',
                    feedback_id='3fa85f64-5717-4562-b3fc-2c963f66afa6',
                    page=1, page_size=20)

# ② 查看一级评论 B 的全部二级评论第 1 页（每页 20 条，返回 B 的全部子孙，不分层级）
page1 = signed_get('https://your-domain/api/feedback/replies',
                   feedback_id='3fa85f64-5717-4562-b3fc-2c963f66afa6',
                   parent_id='6b1f2e9a-3c4d-4e5f-8a9b-0c1d2e3f4a5b',
                   page=1, page_size=20)

# ③ 翻页：page < total_pages 时继续 page+1；查看某条子孙的二级评论以其 reply_id 作为新 parent_id
```

**接口调用示例（curl，sign 需按 5.2 算法自行计算）：**

```bash
# 反馈详情：一级评论第 1 页（每条内嵌二级评论首页 5 条）
curl -G 'https://your-domain/api/feedback/detail' \
  -d 'app_id=app_5f3a9c2b7e6d8f1a2b3c4d5e6f7a8b9c' \
  -d 'timestamp=1756800000' \
  -d 'nonce=9f2c4a6e8b1d3f5a7c9e0b2d4f6a8c1e' \
  -d 'sign=<计算出的签名值>' \
  -d 'feedback_id=3fa85f64-5717-4562-b3fc-2c963f66afa6' \
  -d 'page=1' -d 'page_size=20'

# 查看一级评论 B 的全部二级评论第 1 页（每页 20 条）
curl -G 'https://your-domain/api/feedback/replies' \
  -d 'app_id=app_5f3a9c2b7e6d8f1a2b3c4d5e6f7a8b9c' \
  -d 'timestamp=1756800000' \
  -d 'nonce=9f2c4a6e8b1d3f5a7c9e0b2d4f6a8c1e' \
  -d 'sign=<计算出的签名值>' \
  -d 'feedback_id=3fa85f64-5717-4562-b3fc-2c963f66afa6' \
  -d 'parent_id=6b1f2e9a-3c4d-4e5f-8a9b-0c1d2e3f4a5b' \
  -d 'page=1' -d 'page_size=20'
```

---

### 4.7 站长处理流程（统一广场）

站长在**管理后台**的「问题反馈」管理页集中处理所有子项目反馈，无需逐个访问子项目。

| 能力 | 说明 |
|------|------|
| 集中查看 | 列表中显示所有子项目反馈（所属项目 / 标题 / 状态 / 反馈人 / 评论数 / 时间） |
| 筛选 | 按项目 / 状态 / 创建时间筛选，按标题 / 内容 / 用户名搜索 |
| 状态流转 | 待处理（橙）→ 处理中（蓝）→ 已解决（绿）/ 已关闭（灰） |
| 回复 | 反馈详情页展示**评论树预览**（嵌套缩进、身份徽章，前 10 条）；进入「评论管理页」（详情页顶部入口）分页查看全部评论（20 条 / 页，标注"回复了谁"），页内站长回复表单：`parent` 可选，留空=回复问题本身，选择=回复指定评论（支持嵌套），author_role 自动置 `admin` |
| 删除 | **仅站长（superuser）** 可删除反馈与评论（评论管理页内删除，级联删除其子孙回复）；子项目用户无删除权限 |

> 站长回复会进入该反馈的评论树，子项目用户通过「反馈详情」接口可见（`author_role = "admin"`）。

---

### 4.8 数据隔离与可见性说明

| 场景 | 行为 |
|------|------|
| 子项目 A 查询列表 / 详情 / 评论回复列表 | 只能看到子项目 A 的反馈与评论 |
| 子项目 B 查询子项目 A 的反馈 | 详情返回 20030「反馈不存在或不属于当前项目」；列表为空 |
| 评论 / 回复子项目 B 的反馈 | 返回 20030「反馈不存在或不属于当前项目」 |
| 回复 / 查看不属于当前反馈的评论 | 返回 20030「父评论不存在或不属于当前反馈」 |
| 同一子项目内的用户 | 可见该项目的全部反馈与评论树（项目内公开） |
| 站长 | 后台统一广场可见所有子项目反馈 |

---

## 五、签名与身份校验机制（重要）

问题反馈中心接口**全部**需要签名；其中提交反馈 / 评论回复**另需**用户 Token 校验身份真实性。

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

# 回复评论示例（APPID / APPSECRET 由后台自动生成并发放；token 为用户登录 Token）
params = {
    'app_id': 'app_5f3a9c2b7e6d8f1a2b3c4d5e6f7a8b9c',
    'timestamp': str(int(time.time())),
    'nonce': secrets.token_hex(8),
    'token': '5f4dcc3b5aa765d61d8327deb882cf99e6a3c8a4b1f9e2d4c6a8b0c1d2e3f4a5',
    'feedback_id': '3fa85f64-5717-4562-b3fc-2c963f66afa6',
    'content': 'C: 怎么解决的',
    'parent_id': '6b1f2e9a-3c4d-4e5f-8a9b-0c1d2e3f4a5b',  # 回复 B 的评论（可留空=一级评论）
}
params['sign'] = build_sign(params, 'sk_9c8b7a6f5e4d3c2b1a0f9e8d7c6b5a4f0e1d2c3b4a596877')

# 发送请求（表单）
url = 'https://your-domain/api/feedback/reply'
body = urllib.parse.urlencode(params)
```

### 5.4 用户 Token 身份校验规则（create / reply）

提交反馈与评论回复时，`token` 由反馈中心调用用户中心校验，规则如下：

| 校验项 | 失败返回 |
|--------|----------|
| token 缺失 | 20001 参数缺失 |
| token 不存在或不属于当前项目 | 20010 Token 无效: 不存在或不属于当前项目 |
| token 已过期 | 20010 Token 已失效: 已过期 |
| 用户被后台封禁 | 20010 Token 已失效: 用户封禁 |
| 项目被后台停用 | 20011 接入项目已被停用（签名层直接拦截） |

> **身份来源**：反馈人 / 评论人身份以 Token 校验返回的 `user_id` 为准，接口不接收子项目自行传入的用户 ID，杜绝身份伪造。

### 5.5 签名安全校验规则

| 校验项 | 失败返回 |
|--------|----------|
| 四个签名参数必须同时提供 | 20011 签名参数缺失 |
| timestamp 必须为数字 | 20011 参数格式错误: timestamp 必须为 10 位时间戳(秒) |
| timestamp 与服务器时间差 ≤ ±5 分钟 | 20011 签名过期: timestamp 超出有效窗口(±5分钟) |
| app_id 必须已注册 | 20011 未注册的接入项目: app_id 不存在 |
| 项目必须处于启用状态 | 20011 接入项目已被停用 |
| sign 必须与本地计算一致（常数时间比较，防时序攻击） | 20011 签名校验失败: sign 不匹配 |
| 接口未配置项目认证 | 20011 接口未配置项目认证，无法识别接入项目 |

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

### 6.2 问题反馈中心相关状态码

| code | 含义 | 说明 |
|------|------|------|
| 10000 | 成功 | 业务处理成功 |
| 20001 | 参数缺失 | 缺少必填参数（如 title / content / feedback_id / token / 签名参数） |
| 20002 | 参数格式错误 | 参数长度 / 类型不合法（如 title 超 100 字符） |
| 20010 | 未认证 | 用户 Token 无效 / 已过期 / 用户封禁 |
| 20011 | 认证失败 | 签名校验失败 / 项目停用 / 接口未配置认证 |
| 20030 | 资源不存在 | 反馈不存在或不属于当前项目；父评论不存在或不属于当前反馈 |
| 405 | 方法不允许 | 使用错误 HTTP 方法访问接口 |

**状态码分类规则：** 1xxxx=成功，2xxxx=客户端错误，3xxxx=业务逻辑错误，4xxxx=外部服务错误，5xxxx=系统内部错误。

---

## 七、安全设计要点

1. **签名防篡改**：HMAC-SHA256 覆盖全部业务参数，任何参数被修改都会导致签名校验失败
2. **重放防护**：timestamp ±5 分钟窗口 + nonce 唯一性
3. **身份真实性**：反馈人 / 评论人由 UAC Token 校验确定，子项目无法伪造用户 ID；跨项目 Token 一律无效
4. **数据隔离**：所有查询以签名确定的项目为租户维度，子项目之间互不可见；回复必须指向当前反馈下的评论（跨反馈/跨项目一律拒绝）
5. **状态联动**：用户封禁 → 其 Token 失效，无法提交反馈；项目停用 → 该项目全部接口被签名层拦截
6. **评论分级分页**：一级评论强制分页（默认 20 / 页，最大 100），每条一级评论只内嵌二级首页（默认 5 条，全部子孙中时间最前 N 条），返回体大小恒定，单条一级评论上万条回复不影响详情接口响应
7. **二级评论分页**：任意评论的**全部二级评论**（无论嵌套多深）通过「评论回复列表」接口分页获取（默认 20 / 页，最大 100）；详情接口一次查询 + 内存组装评论树，无逐层 N+1 查询、无 Python 递归深度限制（50 层深嵌套实测正常）
8. **列表聚合查询**：评论数用数据库聚合一次算出，避免 N+1 查询，大数据量下列表稳定
9. **级联清理**：删除父评论会级联删除其全部子孙回复，不残留孤儿数据
10. **纯文本存储**：反馈与评论为纯文本字段，服务端不渲染富文本，前端展示时自行转义（防 XSS）
11. **删除权限收敛**：仅站长（superuser）可删除反馈与评论，子项目用户无删除能力
12. **接口方法限制**：提交 / 评论仅允许 POST，列表 / 详情仅允许 GET，违规返回 405
13. **传输安全**：建议全站 HTTPS，防止请求参数与 Token 在传输中被窃听
14. **密钥管理**：APPSECRET 严禁写入前端代码 / 提交到仓库，子项目后端保管

---

## 八、接口总览

| 方法 | 路径 | 功能 | 签名 | 身份校验 | 请求体 |
|------|------|------|------|----------|--------|
| POST | /api/feedback/create | 提交反馈（title / content / token） | 签名 | Token 校验 | 表单 |
| POST | /api/feedback/reply | 追加/回复评论（feedback_id / content / parent_id? / token） | 签名 | Token 校验 | 表单 |
| GET | /api/feedback/list | 项目内反馈列表（status / page / page_size） | 签名 | 仅签名 | Query |
| GET | /api/feedback/detail | 反馈详情+评论树（feedback_id / page / page_size） | 签名 | 仅签名 | Query |
| GET | /api/feedback/replies | 评论回复列表（二级评论，返回全部子孙不分层级，feedback_id / parent_id / page / page_size） | 签名 | 仅签名 | Query |

---

## 九、典型接入时序（完整示例）

以下演示子项目"视频分析站"搭建问题反馈广场并接入反馈中心的完整调用序列：

```
① 接入：小影管理员后台创建项目「视频分析站」，系统自动生成并发放
   APPID = app_5f3a9c2b7e6d8f1a2b3c4d5e6f7a8b9c
   APPSECRET = sk_9c8b7a6f5e4d3c2b1a0f9e8d7c6b5a4f0e1d2c3b4a596877
   并将反馈中心分类设为「需要认证」

② 用户登录（走用户中心，获取绑定本项目的 Token）：
   用户已在用户中心注册并登录「视频分析站」
   ← 获得 token = 5f4dcc3b5aa765d61d8327deb882cf99e6a3c8a4b1f9e2d4c6a8b0c1d2e3f4a5

③ 用户 A 提交问题反馈：
   子项目表单提交 {title: "登录页白屏", content: "点击登录后页面无响应",
                  token, app_id, timestamp, nonce, sign}
   ← 返回 {feedback_id: "3fa85f64-5717-4562-b3fc-2c963f66afa6", status: "pending"}
   子项目将 feedback_id 与页面跳转关联

④ 用户 B 评论问题（一级评论）：
   子项目表单提交 {feedback_id: "3fa85f64-...", content: "B: 我遇到过",
                  token, app_id, timestamp, nonce, sign}
   ← 返回 {reply_id: "6b1f2e9a-3c4d-4e5f-8a9b-0c1d2e3f4a5b"}

⑤ 用户 C 回复 B 的评论（二级，parent_id = B 的 reply_id）：
   子项目表单提交 {feedback_id: "3fa85f64-...", parent_id: "6b1f2e9a-...",
                  content: "C: 怎么解决的", token, app_id, timestamp, nonce, sign}
   ← 返回 {reply_id: "7c2f3e9b-4d5e-5f6a-9b0c-1d2e3f4a5b6c"}

⑥ 用户 D 回复 C（仍属二级评论，无限嵌套）：
   子项目表单提交 {feedback_id: "3fa85f64-...", parent_id: "7c2f3e9b-...",
                  content: "D: 重启就好了", token, app_id, timestamp, nonce, sign}

⑦ 子项目广场首页渲染反馈列表：
   子项目 GET /api/feedback/list?status=&page=1&page_size=10&签名参数
   ← 返回 {total, items: [{feedback_id, title, status, username, reply_count, create_time}]}

⑧ 用户查看反馈详情与评论区（一级分页，每条内嵌二级首页；某条评论的全部二级评论按 parent_id 分页获取全部子孙）：
   子项目 GET /api/feedback/detail?feedback_id=3fa85f64-...&page=1&page_size=20&签名参数
   ← 返回 {feedback_id, title, content, status, username,
           total, page, page_size, total_pages,
           replies: [{reply_id, author_role, username, content, create_time,
                      reply_total, children_total, replies: [二级首页...]}]}
   用户点击"查看全部回复"（parent_id = B 的 reply_id）：
   子项目 GET /api/feedback/replies?feedback_id=3fa85f64-...&parent_id=6b1f2e9a-...&page=1&page_size=20&签名参数
   ← 返回 {parent_id, total, page, page_size, total_pages,
           items: [{reply_id, author_role, username, content, create_time,
                    reply_total, children_total, replies: []}]}
   查看某条子孙评论自己的二级评论：以返回项 reply_id 作为新 parent_id 再次调用 /replies

⑨ 站长处理（后台统一广场，与子项目无交互）：
   站长在后台看到该反馈 → 状态流转 pending → processing → resolved
   站长回复问题或回复任意评论（author_role=admin）
   ← 子项目用户下次拉取详情时可见站长回复（评论树中）
```

---

## 十、常见问题（FAQ）

**Q1：子项目之间的反馈会互相看到吗？**
不会。反馈数据以项目（APPID）为租户维度隔离，子项目 A 查询不到子项目 B 的任何反馈与评论（详情返回 20030，列表为空）。

**Q2：同一子项目内，用户能看到别人提的反馈吗？**
可以。同一子项目内**所有用户**可见该项目的全部反馈与评论树（项目内公开，类似 GitHub Issues），可互相参考、共同讨论。

**Q3：评论支持互相回复吗？怎么嵌套？**
支持。评论为**评论树（无限嵌套）**：A 提问题 → B 评论 → C 回复 B → D 回复 C……可回复任意层级的评论。**评论只有一级/二级两类**：直接评论问题=一级（parent 空）；回复在别人评论底下=二级（parent 非空，**无论嵌套多深**，不存在三级/N级）。调用「追加/回复评论」接口时传 `parent_id` 即可，不传则为一级评论。查看时一级评论分页、每条内嵌二级首页（全部子孙前 5 条），某条评论的**全部二级评论**通过「评论回复列表」接口（4.6）分页获取。

**Q4：一条反馈的评论很多，接口会卡吗？**
不会。一级评论强制分页（默认 20 条 / 页，最大 100），每条一级评论只内嵌二级首页（默认 5 条，全部子孙中时间最前 N 条），全部二级评论通过「评论回复列表」接口分页获取（默认 20 条 / 页，最大 100）；经 1050 条一级评论、单条一级评论下 1000 条回复、50 层深嵌套等极限场景验证，接口性能稳定。

**Q5：提交反馈为什么必须带 token？不带会怎样？**
`token` 用于校验反馈人 / 评论人身份真实性，防止子项目伪造用户身份。不带（20001）、伪造 / 过期 / 跨项目（20010）均被拒绝。列表 / 详情接口只需签名即可调用（项目内公开数据）。

**Q6：评论人身份怎么确定的？**
以用户 Token 校验结果为准。反馈中心调用用户中心校验 Token，取校验返回的 `user_id` 作为评论人，接口不接受子项目自传的用户 ID。

**Q7：反馈状态是谁改的？怎么改？**
站长在后台「问题反馈」管理页流转：待处理（橙）→ 处理中（蓝）→ 已解决（绿）/ 已关闭（灰）。子项目通过列表 / 详情接口读取状态展示。

**Q8：用户能删除自己提的反馈或评论吗？**
不能。仅站长（superuser）可在后台删除反馈与评论；删除评论会级联删除其全部子孙回复。子项目用户只有提交和评论能力。

**Q9：站长回复用户能看到吗？**
能。站长回复进入该反馈的评论树（`author_role = "admin"`，username 为「站长」），可回复问题本身或回复任意评论；子项目用户调用详情接口即可看到，项目内全部用户可见。

**Q10：反馈和评论内容支持图片 / Markdown 吗？**
暂不支持。当前为**纯文本**存储与返回，前端可自行对内容做转义渲染（防 XSS）。后续如需富文本可扩展。

**Q11：APPSECRET 泄露了怎么办？**
立即联系小影 API 管理员。当前 APPID / APPSECRET 创建后固定不可修改，泄露可能被他人冒用身份提交反馈；可考虑停用项目后重新创建接入。

**Q12：详情接口的分页是什么含义？**
`page` / `page_size` / `total` / `total_pages` 针对**一级评论**：一级评论按时间正序分页返回（查看最新一级评论请翻到最后一页）。每条一级评论只内嵌**二级首页**（默认 5 条，全部子孙中时间最前 N 条），`children_total` 为直接子回复数、`reply_total` 为二级评论总数（全部子孙数）；全部二级评论通过「评论回复列表」接口按 `parent_id` 分页获取，查看某条子孙评论自己的二级评论以其 `reply_id` 作为新 `parent_id` 再次调用。

**Q13：非法分页参数会报错吗？**
不会。分页参数非法时自动归一化：非数字→默认值，负数→1，超过上限→100，返回 code=10000 与归一化后的分页结果。

**Q14：能回复或查看其他反馈下的评论吗？**
不能。`parent_id` 必须属于当前反馈，跨反馈 / 跨项目回复或查看其回复均返回 20030「父评论不存在或不属于当前反馈」。

---

*文档版本：v1.4（二级评论语义更正：全部子孙，不分层级）  ·  更新时间：2026-09-02  ·  适用系统：小影 API 问题反馈中心（Feedback Center）*
