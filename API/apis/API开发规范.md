# API 服务开发规范

> 本规则约束 `API/apis/` 下**新建**与**后续调整** API 服务的组织与实现方式
> （文件夹 / 文件如何搭、路由怎么注册、契约如何统一）。
> 核心一句话：**文件夹按服务建，服务用「三件套」分文件，根 urls.py 汇总一行 include（注释即分类名），响应统一走 StatusCode。**
>
> 配套文档：[数据库模型创建规则.md](../models/数据库模型创建规则.md)（服务需要落库时按其建模型）。

---

## 一、核心思想

| 维度 | 规则 | 示例 |
|------|------|------|
| 文件夹 | 代表一个**API 服务**，对应 `/api/` 下的一个前缀 | `uploads/`、`musics/`、`user_center/` |
| 文件 | 一个服务固定拆为**三件套**：路由 / 视图 / 逻辑 | `urls.py` + `request.py` + `utils.py` |
| 汇总 | 根 `API/apis/urls.py` **每行**注册一个服务前缀，行尾注释即分类树节点名 | `path('upload/', include('API.apis.uploads.urls')), # 文件上传` |
| 层级 | **最多两层**：服务文件夹 → 线路（子服务）文件夹 → 三件套 | `API/apis/musics/xiaoying/request.py` |
| 契约 | 所有接口统一返回 `{"code", "msg", "data"}`，状态码取自 `API.common.StatusCode` | `{'code': 10000, 'msg': '成功', 'data': {...}}` |
| 认证 | `/api/` 请求由中间件按**分类树**统一判定，视图不自行校验签名 | `request.auth_app` |

---

## 二、目录组织规则

```
API/apis/
├── urls.py                    # 根汇总：每行注册一个服务前缀 + 中文注释（= 分类名）
├── <服务>/                     # 既有服务（存量）
│   ├── urls.py                # 单体服务：三件套直接放服务根
│   ├── request.py
│   └── utils.py
└── <服务>/                     # 聚合服务：服务根只放汇总 urls.py，线路放下层
    ├── urls.py                # 仅 include 各线路
    └── <线路>/
        ├── urls.py
        ├── request.py
        └── utils.py
```

### 2.1 文件夹 = 一个服务

- 一个服务文件夹对应一个 `/api/` 前缀，服务内部的多个接口写在同一个服务文件夹内。
- 同一业务域的能力**优先并入已有服务**（同一文件夹追加端点），不重复建同类服务。
- 服务文件夹的命名不要求与 URL 前缀字面一致（如 `emails/` ↔ `/api/email/`、`musics/` ↔ `/api/music/`），前缀以根 `urls.py` 中的声明为准。

### 2.2 两种服务形态

| 形态 | 结构 | 适用 | 现有示例 |
|------|------|------|----------|
| 单体服务 | 服务根直接放三件套 | 只有一个来源 / 一组强关联接口 | `uploads/`、`feedback/`、`statistics/`、`DaiLianTong/` |
| 聚合服务 | 服务根只放 `urls.py`，各「线路 / 平台」放子文件夹（各含三件套） | 同一能力有多个来源 / 平台 | `musics/`（2t58、xiaoying）、`ProxyIp/`（66daili、91http…）、`captcha_auth/`（aliyun） |

- 聚合服务的服务根 `urls.py` **只做 include 聚合**，不写业务逻辑：

```python
# API/apis/musics/urls.py
from django.urls import path, include

urlpatterns = [
    path('2t58/', include('API.apis.musics.music_2t58.urls')),  # 爱听音乐网
    path('xiaoying/', include('API.apis.musics.xiaoying.urls')),  # 小影音乐
]
```

### 2.3 层级与命名

- **最多两层**：`服务文件夹 → 线路文件夹 → 三件套`，**禁止**继续嵌套。
- 单体服务 = 一层；聚合服务 = 两层。

### 2.4 路由保留（服务关闭 / 迁移）

服务下线或能力迁移后，若旧前缀已被对接方使用，**保留路由并返回统一占位响应**，避免调用方拿到 404 无法区分：

```python
# API/apis/VideoAnalysis/urls.py
from django.urls import path
from API.common.views import service_building_view

urlpatterns = [
    path('<path:rest>', service_building_view, name='video_analysis_building'),
]
```

> 占位响应：`{"code": 50002, "msg": "服务建设中，暂不可用", "data": null}`。
> 确无对接方使用的服务可直接删除整个文件夹 + 根 urls.py 注册行 + 分类树节点。

---

## 三、三件套职责与「同文件聚合」规则

一个服务的代码**固定按职责拆为三个文件**，禁止混写：

| 文件 | 职责 | 必须做 | 禁止做 |
|------|------|--------|--------|
| `urls.py` | 路由声明 | `urlpatterns` + `name`；聚合服务只 include | 写视图、写业务逻辑 |
| `request.py` | **视图层**：参数解析 / 校验 / 调用 utils / 组装响应 | `@require_http_methods`、`StatusCode`、本地 `_json_response` | 直接访问 DB / 发外部请求 / 写爬虫逻辑 |
| `utils.py` | **业务层**：核心逻辑、DB 操作、外部 / 爬虫调用 | 纯逻辑，返回 `(ok, data/message)` 元组 | 组装 HTTP 响应、读 `request` 对象 |

### 3.1 判定「哪些接口写进同一文件」

满足以下任一条件即写进同一服务的同一文件：

1. **同一服务前缀**：挂在同一个 service 文件夹下的所有端点，视图集中在同一 `request.py`，逻辑集中在同一 `utils.py`。
2. **共享解析 / 响应辅助**：同服务内多个视图复用同一 `_json_response`、`_parse_body` / `_parse_params` 等辅助函数，写在同一文件，避免重复定义。
3. **强关联实体操作**：同一聚合根的多端点（列表 / 详情 / 创建 / 更新 / 删除）写在同一 `request.py`；播放源等子实体的 CRUD 也归在同一文件（如 `musics/xiaoying/request.py` 的 Music + MusicSource）。

### 3.2 反例（应拆分的情形）

- 把 DB 查询 / 外部抓取逻辑直接写进 `request.py` → 逻辑必须下沉到 `utils.py`。
- 多个不相关服务凑进一个 `request.py` → 每个服务独立文件夹与三件套。
- 在 `utils.py` 里 `import JsonResponse` / 读 `request.GET` → 业务层与 HTTP 层必须解耦。
- 为「将来可能的多线路」提前抽象分层 → 单体服务就用单体形态，出现第二个线路时再升级为聚合形态。

### 3.3 现有代码对照（参考）

| 文件 | 形态 | 说明 |
|------|------|------|
| `uploads/urls.py` | 单体 | 3 个上传端点，共用 `_handle_upload` |
| `feedback/urls.py` | 单体 | create/reply/list/detail/replies，共用 `_require_app`、`_fail_response` |
| `musics/xiaoying/urls.py` | 聚合-线路 | Music + MusicSource 强关联聚合于同一三件套 |
| `ProxyIp/ProxyIP_66daili/urls.py` | 聚合-线路 | 每个代理来源一条线路，结构完全一致 |
| `VideoAnalysis/urls.py` | 占位 | 能力已迁移，仅返回「服务建设中」 |

---

## 四、统一接口契约

### 4.1 响应体

所有接口（成功 / 失败）统一返回三字段 JSON：

```python
def _json_response(code, data=None, msg=None):
    """统一响应格式: {"code", "msg", "data"}"""
    return JsonResponse({
        'code': code,
        'msg': msg or StatusCode.get_message(code),  # 未传 msg 时取状态码默认描述
        'data': data,
    })
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | int | 5 位状态码，`10000` 表示成功 |
| `msg` | str | 面向调用方的中文提示；缺省用 `StatusCode.get_message(code)` |
| `data` | any | 业务数据；无数据时为 `null` |

- 每个 `request.py` 内定义本服务私有的 `_json_response`（现状如此），**不跨服务复用私有函数**。
- 成功统一用 `StatusCode.SUCCESS`，失败按下方状态码选择，**禁止自造裸数字**。

### 4.2 状态码

状态码集中定义在 [API/common/status_code.py](../common/status_code.py)，编码规则：首位标识类别。

| 类别 | 段位 | 常用状态码 |
|------|------|-----------|
| 成功 | 1xxxx | `SUCCESS`(10000) |
| 客户端错误 | 2xxxx | `PARAM_MISSING`(20001)、`PARAM_FORMAT_ERROR`(20002)、`PARAM_VALUE_INVALID`(20003)、`UNAUTHORIZED`(20010)、`AUTH_FAILED`(20011)、`NOT_FOUND`(20030)、`RATE_LIMITED`(20040)、`METHOD_NOT_ALLOWED`(20041) |
| 业务逻辑错误 | 3xxxx | `BUSINESS_RULE_RESTRICTED`(30001)、`DATA_CONFLICT`(30003) |
| 外部服务错误 | 4xxxx | `EXTERNAL_API_FAILED`(40001)、`EXTERNAL_API_TIMEOUT`(40002)、`EXTERNAL_API_ABNORMAL`(40003) |
| 系统内部错误 | 5xxxx | `INTERNAL_ERROR`(50001)、`SERVICE_UNAVAILABLE`(50002) |

### 4.3 参数错误码约定

| 场景 | 状态码 |
|------|--------|
| 必填参数缺失 / 请求体为空 | `20001`（`msg` 以 `参数缺失` 开头） |
| 类型 / 编码 / 解析失败 | `20002`（`msg` 以 `参数格式错误` 开头） |
| 值越界 / 枚举非法 / 业务校验不通过 | `20003`（`msg` 以 `参数值非法` 开头） |

视图层按此前缀语义返回，便于调用方与测试脚本稳定识别。

### 4.4 请求方法与参数解析

- 必须用 `@require_http_methods([...])` 声明允许的方法，方法不符由框架返回 405。
- 参数来源与解析方式：

| 场景 | 取值方式 |
|------|----------|
| GET 查询串 | `request.GET.get('k', '').strip()` |
| POST 表单 | `request.POST` |
| PATCH/DELETE 表单 | `request.POST` 为空，需手动 `QueryDict(request.body.decode('utf-8'))` |
| multipart 文件 | `request.FILES.get('file')`，字段名固定 `file` |
| 公开 GET 豁免 | 见第五章 5.3 |

- 签名参数（`app_id/timestamp/nonce/sign`）由中间件统一校验，**视图内不再重复校验**；需要项目上下文时取 `request.auth_app`。

### 4.5 分页规范

- 参数名固定 `page` / `page_size`；`page` 从 1 开始，`1 ≤ page_size ≤ 100`。
- 返回 `data` 内含 `total`（总数）与列表字段，便于前端分页。

### 4.6 异常与兜底

- 视图层**不写裸 `except` 吞异常**；未捕获异常由 `ApiRequestLogMiddleware` 记录堆栈到 `logs/error.log`（带 `request_id`），并由全局 `handler500` 返回统一 JSON。
- `/api/` 未匹配路径由 `ApiJson404Middleware` / `handler404` 统一返回 `{"code":20030,...}`，不受 `DEBUG` 影响。
- 业务层预期内的失败（参数非法、资源不存在、外部调用失败）用 `(ok, message)` 元组返回，由视图映射为对应状态码，**不要抛异常做流程控制**。

---

## 五、认证与分类树

### 5.1 统一由中间件判定（fail-closed）

- `/api/` 请求由 `ApiAuthMiddleware` 按 `ApiCategory` 分类树判定：请求路径按**最长前缀**命中节点，再沿父链向上取第一个非 `inherit` 的模式（`auth` 需认证 / `open` 开放）。
- **A-01 起 fail-closed**：未命中分类 / 全链 inherit / 分类停用 → 一律要求签名；新增服务**默认不可匿名访问**，需显式配置为 `open` 才免签。
- 需要认证的接口：通过后把项目对象挂到 `request.auth_app`，视图据此做数据隔离（租户维度）。

### 5.2 分类节点名 = 根 urls.py 的注释

分类树由管理命令**扫描 `API/apis/urls.py` 的 include 行**生成，行尾注释即节点名称：

```python
path('upload/', include('API.apis.uploads.urls')),  # 文件上传
```

- include 语句必须**写成一行**，且注释与 include 同行，否则节点名会退化为模块末段（如 `uploads`）。
- 子服务 / 线路的层级同样由被 include 的 `urls.py` 递归解析得到。

### 5.3 匿名访问

- 仅两类可免签名：分类树中**显式 `open`** 的节点；`ApiAuthMiddleware.PUBLIC_GET_PATHS` 列出的公开 GET 路径（如邮箱激活链接）。
- 新增服务需要匿名时，走后台 `/console/categories/` 将对应节点设为 `open`（会同时展示真实生效结果），**不要**在视图里绕过中间件。

### 5.4 重建时机

- 新增 / 删除服务文件夹或调整根 `urls.py` 后，执行：

```bash
python manage.py rebuild_category_tree
```

- 命令**幂等**：已存在的分类只同步名称与父子层级，**不覆盖**后台手动配置的 `auth_mode` / `status`。
- 新部署必执行一次，否则分类树为空、所有接口匿名被拒（`20011`）。

---

## 六、命名规范

| 对象 | 规范 | 示例 |
|------|------|------|
| 服务文件夹 | snake_case（新建）；历史 PascalCase 目录保留不动 | 新建 `captcha_self/`；存量 `DaiLianTong/`、`ProxyIp/` |
| 线路 / 子文件夹 | snake_case 或来源 / 平台原名，保持可读 | `xiaoying/`、`music_2t58/`、`VMEmail/`、`aliyun/` |
| 三件套文件名 | **固定**为 `urls.py` / `request.py` / `utils.py` | — |
| 视图函数 | snake_case，以 `_view` 结尾 | `image_upload_view`、`create_view`、`musics_view` |
| 路由 name | `服务_动作` 或 `线路_动作`，全局唯一 | `upload_image`、`feedback_create`、`xiaoying_musics` |
| 路由 path | 不带尾斜杠；如需兼容客户端带斜杠，再补 `<name>/` 变体 | `path('create', ...)` + `path('create/', ...)` |
| 私有辅助函数 | 模块内以 `_` 前缀 | `_json_response`、`_parse_body`、`_require_app` |
| include 注释 | 中文服务 / 线路名（= 分类树节点名） | `# 文件上传` |

> 命名约束**只针对新建与后续调整**；存量服务的文件夹名、视图名不强制迁移（见第十一章）。

---

## 七、导入与导出

- 根 `API/apis/urls.py` 一律用**绝对导入**（`include('API.apis.<服务>.urls')`）。
- 服务内部：跨目录用绝对导入（`from API.apis.uploads.utils import FileUploader`），同目录可用相对导入（`from . import utils`）——两种现状并存，同一文件内保持一致即可。
- 每个 `urls.py` 顶部用一行注释标明**域名前缀**，便于定位：

```python
# 域名前缀: /api/upload/
```

- `__init__.py` 非必需（URL 模块走隐式命名空间包），部分服务目录保留；新建服务可省略。

---

## 八、安全与复用要求

- **优先复用 `API/common/`**，禁止在服务内重复实现：`StatusCode`、`credential_crypto`、`security_guard`、`url_safety`。
- 抓取 / 代理任意外部 URL：必须走 `API/common/url_safety.py` 校验（协议白名单 + 拒绝内网 / 回环 / 链路本地），并限制重定向与批量次数（S-09）。
- 文件上传：扩展名**白名单 + 文件头（magic bytes）校验**，禁止可内联执行 / 可渲染类型（S-02）。
- 敏感凭据（`app_secret`、Token、密钥）不得写入日志、不得明文落盘；需要存储时用 `credential_crypto`。

---

## 九、文档接入

新增服务上线必须同步文档——站内文档中心（声明式，自动生成页面与在线调试）：

- 新建 `API/website/docs/<服务>.py`，用 `ServiceSpec / ChannelSpec / EndpointSpec / ParamSpec` 描述「服务 → 线路 → 端点 → 参数」，`auth_note` 填 `open` / `auth` / `inherit`；
- 在 `API/website/docs/__init__.py` 的 `_SERVICES` 注册一行，左侧导航、文档页、调试白名单自动生效。

---

## 十、新建服务决策流程

新增一个 API 服务时，按以下顺序执行：

1. **归属哪个服务域？** → 能力可并入已有服务则直接追加端点；确属新服务则新建服务文件夹（snake_case）。
2. **是单体还是聚合？** → 只有一个来源用单体（根目录三件套）；多来源 / 多平台用聚合（服务根 `urls.py` + 线路子文件夹）。
3. **建三件套** → `urls.py`（路由 + `name`）、`request.py`（视图 + `_json_response`）、`utils.py`（业务逻辑）。
4. **注册根路由** → 在 `API/apis/urls.py` 追加**一行**：

   ```python
   path('<前缀>/', include('API.apis.<服务>.urls')),  # <中文服务名>
   ```

5. **补齐实现** → 视图用 `@require_http_methods` + `StatusCode`；逻辑放 `utils.py` 并返回 `(ok, data)`。
6. **需要落库？** → 按[数据库模型创建规则.md](../models/数据库模型创建规则.md) 建模型，再补迁移（本地 `makemigrations` → 随代码入库）。
7. **补文档** → `API/website/docs/<服务>.py` + `__init__.py` 注册（见第九章）。
8. **重建并核对认证** → 执行 `rebuild_category_tree`，到 `/console/categories/` 核对节点认证模式（默认需认证，确需匿名再设 `open`）。
9. **自测** → 补充 / 运行 `scripts/` 回归脚本，验证成功、参数错误、认证拒绝等分支。

---

## 十一、存量与生效范围

- **约束范围**：本规则约束**新建**与**后续调整**的服务组织与实现方式。
- **存量现状**：服务文件夹命名新旧混用（snake_case 与 PascalCase 并存）；单体 / 聚合两种形态并存；服务内部私有辅助函数各自实现。存量保稳，不强制迁移。
- **调整存量服务**时：只改组织方式与导入路径，**不改**URL 前缀、响应契约、状态码语义与认证模式；确需破坏性变更（改路径 / 改契约）须评估对接方影响并同步文档与分类树。
- 新增服务一律按本规则组织；新增模型一律按《数据库模型创建规则.md》组织。
