# 小影 API（XiaoYingAPI）

一个致力于构建通用 API 服务的项目，基于 Django 聚合了爬虫、AI、代理IP、SEO 等多个领域的 API 服务。

---

## 一、技术栈

| 组件 | 说明 |
|------|------|
| Python / Django | 后端框架（Django 5.x） |
| SQLite | 默认数据库（`db.sqlite3`，已配置 20s 写锁等待） |
| django-simpleui | 后台主题（替换默认 admin 样式） |
| django-cors-headers | 跨域请求支持 |
| requests / httpx / lxml | HTTP 请求与网页解析 |
| pycryptodome | 加解密（Crypto） |
| ddddocr | 验证码识别 |
| python-dotenv | 环境变量加载（`.env`） |

---

## 二、目录结构

```
XiaoYingAPI/
├── manage.py                  # Django 管理入口
├── requirements.txt           # Python 依赖
├── .env                       # 环境变量（不入库）
├── XiaoYingAPI/               # 项目配置目录（settings/urls/wsgi/asgi）
├── API/
│   ├── common/                # 公共模块（状态码/统一响应/兜底视图/中间件）
│   ├── models/                # 数据模型汇总（Music、FriendLink 等）
│   ├── apis/                  # 各业务 API 服务（urls.py + request.py + utils.py 三件套）
│   ├── middlewares/           # 自定义中间件（cloak_guard 斗篷守卫等）
│   └── migrations/            # 数据库迁移文件（⚠️ 部署时需手动创建，见第五章）
├── SpiderServices/            # 爬虫服务源码（被 API 层调用）
├── BugAndRepair/              # 部署事故记录与修复手册
├── scripts/                   # 辅助脚本
├── media/                     # 媒体文件（上传目录）
└── static/                    # 静态文件
```

**API 分层约定**：每个 API 服务按「三件套」组织——`urls.py`（路由）、`request.py`（请求参数校验/视图）、`utils.py`（业务逻辑/爬虫调用），统一返回 `{"code": int, "msg": str, "data": ...}`。

---

## 三、快速开始（本地运行）

```bash
# 1. 创建虚拟环境并安装依赖
python -m venv .venv
# Windows: .venv\Scripts\activate     Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt

# 2. 配置环境变量（复制 .env 参考项，填入真实值）
#    核心必填: SECRET_KEY、ALLOWED_HOSTS

# 3. 数据库迁移（⚠️ 先确认 API/migrations 文件夹存在，见第五章）
python manage.py makemigrations
python manage.py migrate

# 4. 创建后台管理员（可选）
python manage.py createsuperuser

# 5. 启动服务
python manage.py runserver 0.0.0.0:10000
```

---

## 四、环境变量（.env）

| 变量 | 必填 | 说明 |
|------|------|------|
| `SECRET_KEY` | 是 | Django 密钥，生产环境必须替换 |
| `DEBUG` | 否 | `True`/`False`，默认 `False` |
| `ALLOWED_HOSTS` | 是 | 允许访问的域名，逗号分隔，默认 `*` |
| `CORS_ORIGIN_ALLOW_ALL` | 否 | 是否允许所有跨域来源，默认 `False` |
| `QQ_MAIL_ACCOUNT` | 否 | QQ 邮箱发件账号（邮件服务用） |
| `QQ_MAIL_AUTH_CODE` | 否 | QQ 邮箱 SMTP 授权码 |
| `DEEPSEEK_API_KEY` | 否 | DeepSeek API Key（AI 服务用） |
| `DEEPSEEK_API_URL` | 否 | DeepSeek API 地址，默认 `https://api.deepseek.com` |
| `PROXY_STATIC_JSON_PATH` | 否 | 静态代理 IP JSON 文件路径，默认 `SpiderServices/ProxyIp/ProxyIP_Static/proxies.json` |

---

## 五、数据库迁移（⚠️ 部署必读）

本项目模型（`Music`、`FriendLink` 等）的迁移文件位于 `API/migrations/`。

> **⚠️ 重要：部署上线后，如果服务器上还没有 `API/migrations` 文件夹，必须先在 `/项目根目录/API` 下创建 `migrations` 文件夹，并在其中创建空的 `__init__.py` 文件，否则执行 `python manage.py migrate` 会直接失败。**
>
> 原因：`.gitignore` 中忽略了 `migrations/` 目录，迁移文件不会随代码上传到服务器，需要手动创建目录占位后再执行迁移。

```bash
# 部署后执行迁移前，先确认目录存在
mkdir -p API/migrations
touch API/migrations/__init__.py   # 必须创建空的 __init__.py

# 再执行迁移
python manage.py makemigrations
python manage.py migrate
python manage.py collectstatic --noinput
```

> 提示：若 `makemigrations` 因环境缺失第三方模块（如 Crypto）报错，可加 `--skip-checks` 跳过检查：
> `python manage.py makemigrations API --name <迁移名> --skip-checks`

---

## 六、部署上线说明

线上推荐 uWSGI + Nginx 方式部署，宝塔面板可直接使用 Python 项目管理器。完整流程与踩坑记录见 `BugAndRepair/` 目录：

- `宝塔搭建好之后的初始化.md` — 新装宝塔环境初始化 + 部署全流程（含 uwsgi 安装）
- `Django部署上线操作手册.md` — 通用部署手册
- `Nginx配置被PowerShell破坏导致子域名静态资源404.md` / `事故报告-Nginx无限重定向.md` — Nginx 相关事故修复

关键点：
1. `.env` 中 `ALLOWED_HOSTS` 必须包含线上域名，修改后需完全重启 uwsgi（仅 `--reload` 不生效）。
2. 先按第五章创建 `API/migrations` 文件夹，再执行迁移。
3. 静态/媒体文件在 `DEBUG=False` 时由 Django `serve` 视图提供（已配置），或交给 Nginx 处理。

---

## 七、开发规范

- **API 结构**：每个服务按 `urls.py` + `request.py` + `utils.py` 三件套组织，路由统一注册到 `API/apis/urls.py`。
- **响应格式**：统一走 `{"code", "msg", "data"}`，禁止直接返回 Django HTML。
- **请求体**：业务提交类接口统一使用 `application/x-www-form-urlencoded` 表单提交（如友情链接 CRUD），不使用 JSON body。
- **爬虫与 API 分离**：爬虫源码在 `SpiderServices/`，API 层通过 `utils.py` 调用。
- **文档同步**：API 接口文档统一维护在 Apifox，新接口上线后需同步更新（使用表单请求体，先 `cli-schema validate` 再 `endpoint create/update`）。

---

## 八、API 文档

所有接口的参数说明、请求示例与响应示例，请查看 Apifox 在线文档：

- **Apifox 文档**: https://b7hm6mvwv6.apifox.cn/

---

## 联系方式

- 微信: duyanbz
- TG: https://t.me/xiaoying1216
