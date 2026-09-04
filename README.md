# 小影 API（XiaoYingAPI）

一个致力于构建通用 API 服务的项目，基于 Django 聚合了爬虫、AI、代理IP、音乐、SEO、用户中心等多个领域的 API 服务，统一接入签名认证与标准响应格式。

---

## 一、技术栈

| 组件 | 说明 |
|------|------|
| Python / Django | 后端框架（Django 5.x） |
| SQLite | 默认数据库（`db.sqlite3`，已配置 20s 写锁等待） |
| django-simpleui | 后台主题（替换默认 admin 样式） |
| django-cors-headers | 跨域请求支持 |
| whitenoise | 生产模式静态文件服务 |
| requests / httpx / lxml | HTTP 请求与网页解析 |
| pycryptodome | 加解密（Crypto） |
| ddddocr | 验证码识别 |
| python-dotenv | 环境变量加载（`.env`） |

---

## 二、目录结构总览

```
XiaoYingAPI/
├── manage.py                  # Django 管理入口（启动/迁移/创建管理员等）
├── requirements.txt           # Python 依赖清单
├── .env                       # 环境变量（不入库，见第五章）
├── .gitignore                 # git 忽略规则
├── XiaoYingAPI/               # 项目配置目录（settings / urls / wsgi / asgi）
├── API/                       # 主应用：所有业务逻辑所在
│   ├── apis/                  # 各业务 API 服务（三件套：urls/request/utils）
│   ├── common/                # 公共模块（状态码/响应/中间件/基础模型/ORM）
│   ├── models/                # 数据模型汇总（用户/项目/分类/音乐）
│   ├── middlewares/           # 独立中间件组件（cloak_guard 斗篷守卫）
│   ├── static/                # 应用内静态文件（后台自定义样式等）
│   ├── tests/                 # 单元测试
│   ├── admin.py               # 后台自动配置 + 数据仪表盘
│   └── apps.py                # 应用配置
├── SpiderServices/            # 爬虫服务源码（被 API 层调用，与业务解耦）
├── BugAndRepair/              # 部署事故记录与修复手册
├── scripts/                   # 辅助脚本（回归测试 / Apifox 文档生成）
├── media/                     # 媒体文件（上传目录 / 后台 logo 等）
├── static/                    # 静态文件（collectstatic 产物，不入库）
├── templates/                 # 全局模板（覆盖 admin 默认模板）
├── .apifox/                   # Apifox 项目配置
└── .trae/                     # Trae AI 技能配置
```

### 各目录/文件作用详解

| 路径 | 作用 |
|------|------|
| `manage.py` | Django 命令行入口，所有管理命令（runserver / migrate / collectstatic / createsuperuser）都通过它执行 |
| `XiaoYingAPI/` | **项目配置目录**：`settings.py`（全局配置）、`urls.py`（根路由：`/admin/` 后台 + `/api/` 接口 + 404/500 JSON 兜底）、`wsgi.py` / `asgi.py`（部署入口） |
| `API/` | **主应用**，全站业务核心。注册在 `INSTALLED_APPS` 中，包含 API 服务、数据模型、公共模块三大部分 |
| `API/apis/` | **业务 API 服务目录**。每个服务按「三件套」组织：`urls.py`（路由）、`request.py`（请求校验/视图）、`utils.py`（业务/爬虫调用）。路由统一在 `API/apis/urls.py` 汇总，域名前缀均为 `/api/`（详见第三章服务清单） |
| `API/common/` | **公共模块**（全站复用，禁止在业务里重复实现）：
  - `status_code.py`：统一状态码（10000 成功 / 2xxxx 客户端错误 / 3xxxx 业务错误 / 4xxxx 外部错误 / 5xxxx 系统错误）
  - `views.py`：全局 JSON 兜底（404 / 500 统一返回 JSON）
  - `middleware.py`：`ApiAuthMiddleware`（分类树签名认证）+ `ApiJson404Middleware`（/api/ 未匹配路径返回 JSON）
  - `base.py`：`BaseModel` 基础模型（含 create_time / updated_time 自动字段）
  - `sqlite_orm.py`：独立的 SQLite3 ORM 工具库（仅标准库，可单独复用） |
| `API/models/` | **数据模型**（按业务域目录组织，组织规则见 `API/models/数据库模型创建规则.md`）：
  - `Auth/category.py`：API 服务分类树（`ApiCategory`，自关联树形结构，三级认证模式）
  - `Projects/app.py`：接入项目管理（`UserApp`，自动生成 APPID/APPSECRET）
  - `Users/user.py`：用户中心（`User` 用户主表 + `UserToken` 登录凭证 + `UserVerifyRecord` 验证记录）；`Users/auth_method.py`（`AuthMethod` 认证方式开关）
  - `Email/email_template.py`：邮件模板（`EmailTemplate`，后台自定义验证邮件）
  - `Feedback/feedback.py`：问题反馈（`Feedback` + `FeedbackReply` 追加评论树）
  - `Music/music.py`：音乐数据模型（`Music` 元数据 + `MusicSource` 播放源） |
| `API/middlewares/` | **独立中间件组件**：`cloak_guard/` 请求访问策略守卫（斗篷中间件），按「类型→动作」模型对 spider/human/direct/unknown 请求差异化处理，用于 SEO 斗篷场景。默认不启用（`CLOAK_GUARD_ENABLED=False`），需要时在 settings 注册 |
| `API/static/` | **应用内静态文件**：`API/admin/apicategory_admin.css` 后台分类页专属样式，collectstatic 自动收集，不依赖 simpleui 包内文件 |
| `API/tests/` | 单元测试目录（如 `test_music_import.py`） |
| `API/admin.py` | 后台自动化：自动注册模型生成 SmartModelAdmin、数据统计仪表盘（`/admin/dashboard/`）、API 分类树专属后台 |
| `SpiderServices/` | **爬虫服务源码**，与 API 层解耦。API 的 `utils.py` 调用这里的爬虫逻辑（音乐 / 代理IP / 视频分析 / 代练 / ddddocr 等） |
| `BugAndRepair/` | **部署与运维手册**：宝塔初始化流程、Nginx 配置、事故记录与修复方案 |
| `scripts/` | **辅助脚本**：回归测试（`test_user_center.py` / `test_sms_verify.py` / `test_api_auth_policy.py` / `test_captcha_auth.py` / `test_live_http.py`）、测试数据生成（`generate_import_test_data.py`）、Apifox 文档脚本（`apifox/`） |
| `media/` | **媒体文件**：后台 logo、上传文件存储目录（`MEDIA_ROOT`） |
| `static/` | **静态文件收集目录**（`STATIC_ROOT`）：`collectstatic` 产物（含 simpleui 静态文件），部署时重新生成，不入库 |
| `templates/` | **全局模板目录**：覆盖 Django 内置模板（如 `admin/base_site.html` 自定义后台 favicon/标题） |
| `.apifox/` | Apifox 项目配置（projectId） |
| `.trae/` | Trae AI 的技能定义（如 spider-to-api 爬虫转 API 技能） |

---

## 三、API 服务清单（API/apis/）

所有服务统一挂在 `/api/` 前缀下，路由注册于 [API/apis/urls.py](API/apis/urls.py)。各服务内部的三件套结构（urls/request/utils）不再展开，接入方式见 Apifox 文档。

| 服务 | URL 前缀 | 说明 |
|------|----------|------|
| 邮箱服务 | `/api/email/` | 邮箱 v1、VMEmail 虚拟邮箱收发 |
| 音乐服务 | `/api/music/` | 爱听音乐网（2t58）、小影音乐 |
| 文件上传 | `/api/upload/` | 通用文件上传 |
| 视频分析 | `/api/video_analysis/` | 视频解析（抖音） |
| AI 服务 | `/api/ai/` | 内置模型服务 |
| 爬虫验证 | `/api/spider_verification/` | 爬虫验证（sv4759） |
| Bing 服务 | `/api/bing/` | 必应搜索、网页抓取、IndexNow 提交 |
| 代练通 | `/api/dlt/` | 代练订单信息查询 |
| 代练丸子 | `/api/dlwz/` | 代练丸子数据 |
| 验证码识别 | `/api/ddddocr/` | ddddocr 验证码识别 |
| 代理 IP | `/api/ProxyIp/` | 66免费 / 91HTTP / 青雨 / 静态代理 IP |
| SEO 服务 | `/api/seo/` | 友情链接等 SEO 相关 |
| 用户中心 | `/api/user_center/` | 统一认证中心（项目接入 / 用户注册登录） |
| 验证码认证 | `/api/sms_verify/` | 短信验证码认证（阿里云） |
| 图形认证 | `/api/captcha_auth/` | 图形验证码集成（阿里云） |

---

## 四、快速开始（本地运行流程）

```bash
# 1. 创建虚拟环境并安装依赖
python -m venv .venv
# Windows: .venv\Scripts\activate     Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt

# 2. 配置环境变量
#    复制 .env 参考项，至少填写 SECRET_KEY、ALLOWED_HOSTS（见第五章）

# 3. 数据库迁移（migrations 目录随代码入库，见第六章；本地改模型后先 makemigrations 再 migrate）
python manage.py migrate

# 4. 收集静态文件（后台主题样式依赖，简单场景可跳过）
python manage.py collectstatic --noinput

# 5. 创建后台管理员（首次运行）
python manage.py createsuperuser

# 6. 启动服务
python manage.py runserver 0.0.0.0:10000
```

启动后：
- 管理后台：`http://127.0.0.1:10000/admin/`
- API 入口：`http://127.0.0.1:10000/api/...`

**上线部署**：线上推荐 uWSGI + Nginx 方式（宝塔面板），完整流程见 `BugAndRepair/` 目录与第八章。

---

## 五、环境变量（.env）

| 变量 | 必填 | 说明 |
|------|------|------|
| `SECRET_KEY` | 是 | Django 密钥，生产环境必须替换 |
| `DEBUG` | 否 | `True`/`False`，默认 `False`（生产必须为 False） |
| `ALLOWED_HOSTS` | 是 | 允许访问的域名，逗号分隔，默认 `*` |
| `CORS_ORIGIN_ALLOW_ALL` | 否 | 是否允许所有跨域来源，默认 `False` |
| `QQ_MAIL_ACCOUNT` | 否 | QQ 邮箱发件账号（邮件服务用） |
| `QQ_MAIL_AUTH_CODE` | 否 | QQ 邮箱 SMTP 授权码 |
| `DEEPSEEK_API_KEY` | 否 | DeepSeek API Key（AI 服务用） |
| `DEEPSEEK_API_URL` | 否 | DeepSeek API 地址，默认 `https://api.deepseek.com` |
| `ALIYUN_ACCESS_KEY_ID` | 否 | 阿里云 AccessKey ID（短信/图形认证等用） |
| `ALIYUN_ACCESS_KEY_SECRET` | 否 | 阿里云 AccessKey Secret |
| `PROXY_STATIC_JSON_PATH` | 否 | 静态代理 IP JSON 文件路径，默认 `SpiderServices/ProxyIp/ProxyIP_Static/proxies.json` |
| `XYAPI_COOKIE_ISOLATION` | 否 | **环境模式单一开关**：`true`=本地开发（独立 Cookie 名隔离多项目 + 不强制 HTTPS）；删除或 `false`=生产（标准 Cookie 名 + 强制 HTTPS Cookie），默认 `false`。生产部署务必不设置或设为 `false` |

---

## 六、数据库迁移（⚠️ 部署必读）

模型迁移文件位于 `API/migrations/`，**随代码入库（A-05 整改）**：模型变更在本地用 `makemigrations` 生成迁移文件并提交，线上**只执行 `migrate`**，严禁在线上运行 `makemigrations`（会与代码库中的迁移集不一致，造成迁移漂移）。

```bash
# 部署后执行迁移（迁移文件已随代码入库，直接 migrate）
python manage.py migrate
python manage.py collectstatic --noinput
```

> 开发流程：本地修改模型 → `python manage.py makemigrations API --name <迁移名>` → 提交迁移文件 → 线上 `migrate`。
> 存量数据回填 / 数据类操作不要写进迁移文件，使用一次性管理命令（如 `security_backfill`）。

### 分类树重建（⚠️ 新部署必执行）

「API服务分类」数据由管理命令（扫描 `API/apis/` 目录）生成，不依赖迁移。**线上 `migrate` 只建空表、没有分类数据**（后台分类页显示 0 条），且 A-01 后新增服务默认需认证，部署完成后必须执行一次重建命令：

```bash
python manage.py rebuild_category_tree
```

该命令幂等、可重复执行：根据当前 `API/apis/` 目录实时扫描生成/同步分类树，不覆盖后台手动配置的认证模式与启用状态；后续新增服务目录后重新执行即可同步（执行后自动使认证缓存失效）。

---

## 七、后台使用说明

### 1. 接入项目（用户中心）
进入后台「接入项目」，点击「增加」创建项目，系统自动生成：
- `app_id`：公开标识（`app_` 前缀，32 字符）
- `app_secret`：签名密钥（`sk_` 前缀，63 字符，**仅展示一次，需妥善保存**）

创建后 APPID/APPSECRET 固定不可修改。未注册项目无法调用用户中心接口。

### 2. API 服务分类认证（分类树）
后台「API服务分类」管理各服务的认证策略，层级与 `API/apis/` 目录一致：

| 认证模式 | 含义 |
|----------|------|
| `跟随上级`（inherit） | 继承父级分类的认证配置 |
| `需要认证`（auth） | 该分类下所有接口必须携带签名 |
| `开放`（open） | 无需签名，直接访问 |

**生效规则**：请求路径按「最长前缀」命中分类节点，再沿父链向上取第一个非 `跟随上级` 的配置；整条链全为继承 / 未命中任何节点时按全局默认处理——**默认需要认证（fail-closed，A-01）**。新增服务在后台显式配置前不可匿名访问，公开接口需显式设为 `开放`。

**覆盖能力**：父级设为「需要认证」后，可单独把某个子级设为「开放」，实现「父级认证、子级开放」。

### 3. 签名认证契约（需要认证的接口）
调用「需要认证」的接口必须携带 4 个参数：
- `app_id`：项目 APPID
- `timestamp`：10 位时间戳（校验 ±5 分钟窗口，防重放）
- `nonce`：每次请求唯一的随机字符串
- `sign`：HMAC-SHA256 签名

签名算法：除 `sign` 外所有参数按键名 ASCII 升序拼为 `k=v&k=v...`，以 `app_secret` 为密钥做 HMAC-SHA256，输出小写 hex。参考实现见 [API/apis/user_center/sign.py](API/apis/user_center/sign.py) 的 `build_sign` / `verify_sign`。

---

## 八、部署上线说明

线上推荐 uWSGI + Nginx 方式部署，宝塔面板可直接使用 Python 项目管理器。完整流程与踩坑记录见 `BugAndRepair/` 目录：

- `宝塔搭建好之后的初始化.md` — 新装宝塔环境初始化 + 部署全流程（含 uwsgi 安装）
- `Django部署上线操作手册.md` — 通用部署手册
- `Nginx配置被PowerShell破坏导致子域名静态资源404.md` / `事故报告-Nginx无限重定向.md` — Nginx 相关事故修复

### 1. 生产环境 `.env` 配置

```bash
SECRET_KEY=<生产环境重新生成，禁止使用开发值>
DEBUG=False
ALLOWED_HOSTS=api.你的域名.com
# 生产环境不设置 XYAPI_COOKIE_ISOLATION（或设为 false）→ 自动进入生产安全模式：
# 标准 Cookie 名 + 强制 HTTPS Cookie（SESSION/CSRF_COOKIE_SECURE=True）
```

> `XYAPI_COOKIE_ISOLATION` 为环境模式单一开关（见第五章）：本地开发设 `true`（独立 Cookie 名隔离 + 不强制 HTTPS）；**生产务必不设置或设为 `false`**，否则安全 Cookie 不会开启。

### 2. Nginx 反代必须配置 HTTPS 协议头

生产模式 Cookie 强制 Secure（仅 HTTPS 传输）。Nginx 必须向 Django 透传来源协议，否则浏览器会拒绝写入 Cookie（典型症状：后台登录成功但立即跳回登录页）：

```nginx
proxy_set_header X-Forwarded-Proto https;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header Host $host;
```

同时需为域名配置 HTTPS 证书（宝塔 SSL / Certbot）。若 Django 直接对外（无 Nginx 反代），需在 `settings.py` 取消注释 `SECURE_SSL_REDIRECT = True` 强制跳转 HTTPS。

### 3. 数据库迁移

按第六章操作：迁移文件随代码入库，线上**只执行 `migrate`**（禁止线上 `makemigrations`，避免漂移）；部署完成后执行 `rebuild_category_tree` 重建分类树数据（A-01 起新增服务默认需认证，漏建会导致接口匿名被拒）。

### 4. 静态文件与后台样式

`DEBUG=False` 时静态文件由 WhiteNoise 服务（先执行 `collectstatic --noinput`）。后台自定义样式/脚本存放在应用内 `API/static/`，但 `collectstatic` 产物（`static/` 目录）不入库、不随代码更新——每次修改后台样式后必须重新 `collectstatic` 并重启 uwsgi，否则线上仍显示旧样式。

### 5. 启动与验证

- 修改 `ALLOWED_HOSTS` 等 `.env` 配置后需**完全重启 uwsgi**（仅 `--reload` 不生效）。
- 验证清单：HTTPS 正常访问 → 后台登录成功且不跳回 → 浏览器 Cookie 带 `Secure` 标志 → 接口签名认证正常。

---

## 九、测试与脚本（scripts/）

| 脚本 | 作用 |
|------|------|
| `test_user_center.py` | 用户中心回归测试（注册/登录/token/签名安全/封禁/并发，结束时清理测试数据） |
| `test_sms_verify.py` | 短信验证码测试（含真实端到端发送） |
| `test_api_auth_policy.py` | 分类树认证策略测试（继承/覆盖/并发/停用，结束自动恢复分类配置） |
| `test_captcha_auth.py` | 图形认证集成测试 |
| `test_live_http.py` | 对运行中服务器发真实 HTTP 请求验证签名认证行为 |
| `generate_import_test_data.py` | 生成批量导入测试数据 |
| `apifox/` | Apifox 文档脚本与生成的接口文档（JSON/MD） |

> 测试脚本使用真实数据库，多数在结束时自动清理创建的数据，不会污染线上配置。

---

## 十、开发规范

- **API 结构**：每个服务按 `urls.py` + `request.py` + `utils.py` 三件套组织，路由统一注册到 `API/apis/urls.py`。
- **响应格式**：统一走 `{"code", "msg", "data"}`，状态码使用 `API/common/status_code.py` 常量，禁止直接返回 Django HTML。
- **请求体**：业务提交类接口统一使用 `application/x-www-form-urlencoded` 表单提交（如友情链接 CRUD），不使用 JSON body。
- **爬虫与 API 分离**：爬虫源码在 `SpiderServices/`，API 层通过 `utils.py` 调用，不直接混写。
- **模型**：业务模型继承 `API/common/base.py` 的 `BaseModel`（自动带创建/更新时间），主键统一 UUID。
- **文档同步**：API 接口文档统一维护在 Apifox，新接口上线后需同步更新（使用表单请求体，先 `cli-schema validate` 再 `endpoint create/update`）。
- **后台样式**：后台专属样式放 `API/static/` 并在 `admin.py` 通过 `Media` 注入，不修改 simpleui 包内文件。

---

## 十一、API 文档

所有接口的参数说明、请求示例与响应示例，请查看 Apifox 在线文档：

- **Apifox 文档**: https://b7hm6mvwv6.apifox.cn/

---

## 联系方式

- 微信: duyanbz
- TG: https://t.me/xiaoying1216
