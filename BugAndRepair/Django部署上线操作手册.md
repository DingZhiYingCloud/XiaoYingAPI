# Django 项目上线部署手册（小影API）

> **适用环境**：宝塔面板 + Python 3.12 + uWSGI + SQLite + Nginx
> **本文档以本项目「小影API」为例**（settings 模块 `XiaoYingAPI.settings`）；部署其它 Django 项目时，把路径 / 域名 / 端口 / settings 模块替换为你自己的即可，踩过的坑是通用的。
> 本手册总结了实际上线中踩过的所有坑，请**按顺序**执行，每步都有验证方法。
> 宝塔新装环境的初始化流程见 `宝塔搭建好之后的初始化.md`（其中 3.5 为本项目专属部署清单）。

---

## 一、环境信息（先填好，后面命令要用）

| 项 | 小影API 的值 | 你的项目（填） |
|------|--------------|----------------|
| 项目根目录 | `{PROJECT_ROOT}` | __________ |
| settings 模块 | `XiaoYingAPI.settings` | __________ |
| wsgi 文件 | `XiaoYingAPI/wsgi.py` | __________ |
| 域名 | `{DEPLOY_DOMAIN}` | __________ |
| uwsgi 端口 | `10000` | __________ |
| Python 路径 | `{PYTHON_BIN}` | 同左 |
| uwsgi 路径 | `{UWSGI_BIN}` | 同左 |
| 运行用户 | `www` | `www` |
| Java | **Linux 服务器要装 JDK 17** 并设 `HONGGUO_JAVA_BIN`（仓库内置 `jre/` 是 Windows 版，Linux 用不了） | __________ |
| ffmpeg | 需在 PATH 上；**仅**红果短剧线路「第 4 集及以后」解密用（不部署该线路可忽略） | __________ |
| Node.js | **要装 Node.js（≥ 18）**：海角社区的视频播放列表要调 `node derive_key.js` 还原真密钥，抖音评论发布也要 node；内置脚本无 npm 依赖，装个 node 二进制即可，装在非默认位置时设 `HAIJIAO_NODE_BIN` | __________ |
| NapCat WebUI 子域名 | `napcat.{DEPLOY_DOMAIN}`（仅用于扫码，见第九节） | __________ |
| NapCat 事件回调中转端口 | `18080`（**只监听 127.0.0.1**，见第九节） | __________ |

> 后续命令默认在**项目根目录**下执行：`cd {PROJECT_ROOT}`
> 为简洁，用变量 `$PY` 代表 Python 路径，执行前先设：
> ```bash
> PY={PYTHON_BIN}
> ```

---

## 二、部署清单（Checklist）

| # | 步骤 | 要点 | 完成 |
|---|------|------|------|
| 1 | 环境检查（Python / pip） | 版本正确、可执行；**短剧线路另需 `ffmpeg` 与 JDK 17**（内置 `jre/` 是 Windows 版，Linux 用不了）；**海角 / 抖音线路另需 Node.js（≥ 18）** | ☐ |
| 2 | 安装项目依赖 | `requirements.txt` 含构建期依赖 `zhconv` | ☐ |
| 3 | 确认前端产物已随代码入库 | `output.css` / `locale/**/*.mo` / `migrations/*.py` / `hongguo_sign/jre/`；**线上不重新生成** | ☐ |
| 4 | 配置 `.env` 环境变量 | 至少 `SECRET_KEY`、`DEBUG=False`、`ALLOWED_HOSTS` | ☐ |
| 5 | 收集静态文件 | `collectstatic --noinput` | ☐ |
| 6 | 校验迁移文件已入库（A-05） | 线上只 `migrate`，禁止 `makemigrations` | ☐ |
| 7 | 执行数据库迁移 | `migrate`；迁移 `0062` 会**删除额度 / 单价 / 扣点体系**（整表 + 字段）、`0063` 会**删除「上游故障告警」两张表**、`0064` 会**新建「平台账号」表**（`platform_account`），均**不需要任何后续操作** | ☐ |
| 8 | ~~重建 API 服务分类树~~ | **已废弃（分类树已移除）**：改用「服务策略」（服务/线路/端点三级继承），随迁移 `0028` 自动写入公开节点，无需命令 | ☐ |
| 8.1 | ~~给接入项目充值额度~~ | **已废弃（计费体系已下线）**：项目启用 + 签名通过即可调用全部接口，不按次计费、无额度门槛 | ☐ |
| 8.2 | ~~设置调用单价~~ | **已废弃（线路价格页已删除）** | ☐ |
| 8.3 | 配置在线支付（按需） | 控制台「支付设置」`/console/pay/`：填**商户ID**、粘贴**商户私钥**与**平台公钥**（AES-GCM 密文落库、页面不回显）、勾选可用支付方式并启用渠道；再设单笔最低金额与人工退款告知天数。**密钥不入库，只能在这一页粘贴**。对外调用 `/api/pay/create` 必须传 `user_id`（本站注册用户的 UUID），付款成功后按订单金额给该用户加账户余额 | ☐ |
| 8.4 | 确认退款方式（按需） | 迁移 `0057` 后：渠道未开通平台自助退款（易支付当前即如此）时，「支付设置」里该渠道的**退款方式保持「人工受理」**。此时退款不报错，而是进「退款申请」队列 —— 需在支付平台后台退款后，回本页点「标记已退款」以对齐订单状态与用户余额 | ☐ |
| 8.5 | IP 封禁（按需） | 迁移 `0059` 后新增安全模块「IP 封禁」（`/console/ip-bans/`）：**默认封 7 天**，可选 1/3/7/30 天档位、自定义天数或永久；**必须填原因**（会展示给被封访客）。被封 IP 的 `/api/**` 一律返回 `20022 IP_BANNED`，官网前台页头下方同步显示原因与解禁时间。**控制台与 `/admin/` 永不参与判定**，本机 / 内网地址不允许封禁 | ☐ |
| 8.6 | 配置豆包（火山方舟）密钥（按需） | 迁移 `0060` 会种下 `ark` 厂商与 `doubao-seed-2-0-mini` 模型，但**不含 API Key**（密钥不入代码）。要用豆包需在控制台「AI 模型」`/console/ai/models/` 给 `ark` 厂商粘贴方舟 API Key（AES-GCM 密文落库、页面不回显）；该模型为全模态，已在本地实测支持视频与音频理解，可在模型弹窗勾选「支持视频理解 / 支持音频理解」并设上限 | ☐ |
| 8.7 | 反馈审核连附件一起送审（按需） | 迁移 `0061` 后 AI 对话多出 `audios` 参数（音频走 `input_audio` 块）。**问题反馈**的 AI 审核默认就会把用户上传的图片 / 视频**从本地读出后内联**送给模型（图片先压到长边 1280 的 JPEG，视频不大于 8MB 也内联），因此**无需任何配置**；只需把「反馈中心设置」的审核模型换成勾了「支持视觉 / 支持视频理解」的模型（推荐豆包 `doubao-seed-2-0-mini`）。可选：在 `.env` 配 `XYAPI_SITE_URL=https://你的域名`，让**超过 8MB 的超大视频**也能送审（改由上游按公网地址抓取）；不配只是这类大视频被跳过，图片与小视频照常审 | ☐ |
| 8.8 | 录入平台账号（按需） | 迁移 `0064` 后新增「数据运营 → 账号管理」`/console/accounts/`：托管各平台账号与登录凭据（Cookie）。要用**知乎热榜**（`/api/zhihu/hot`）或**微博服务**（`/api/weibo/feed`）时，在这里新增对应平台（知乎 / 微博）的账号并粘贴登录 Cookie、点「校验」确认状态变「有效」，接口就会自动取用（**微博必须登录才能取内容**，不配则接口返回 50002）。**若接入方在自己那边传 `cookie`（调用方自带凭据优先），则平台不必配置**。凭据与密码 AES 加密落库、页面与接口都不回显 | ☐ |
| 9 | 创建超级管理员 | `createsuperuser`；**登录入口是 `/login/`** | ☐ |
| 10 | 配置 uwsgi.ini | 仅监听回环地址 | ☐ |
| 11 | 启动 uwsgi 并验证 | 看日志 `ready` + curl 首页 | ☐ |
| 12 | 配置 Nginx 反向代理 | 指向 `127.0.0.1:{端口}` | ☐ |
| 13 | 配置 SSL 证书 | 强制 HTTPS | ☐ |
| 14 | 上线验证 | 官网页面 + 语言切换 + 接口签名 | ☐ |
| 15 | 配置数据库自动备份 | 加一条 cron 跑 `scripts/backup_db.py`；**必须用 `www` 用户执行**；详见第八节 | ☐ |
| 16 | 部署 QQBot（NapCat，按需） | 用 docker，容器名固定 `napcat`；**已有同名容器就复用、绝不再 `docker run`**（会因名字冲突返回 **125**，且重建会丢 QQ 登录态）；推荐 `--network host` + 只绑回环；**必须配本机 Nginx 中转解 chunked**，否则消息一条都收不到；详见第九节 | ☐ |
| 17 | 依赖 QQBot 的功能自检（按需） | `/console/qqbot/`「测试连接」通 + 私聊一句能落库；**代练搬单的 QQ 接待复用同一个 NapCat 实例**，务必先走通再开搬单「自动运行」 | ☐ |
| 18 | 部署代练搬单（按需） | `.env` 配 `DAILIAN_SIGN_KEY` + `DLT_OSS_*`；「账号管理」录入 `dlt` / `dlwz` 两个平台并校验；后台填**我们的 QQ 号**与**撤销凭证图 URL**；**先 `run_order_migration --once --dry-run` 再开「自动运行」**；多 worker 靠数据库锁互斥。详见第十节 | ☐ |

---

## 三、详细步骤

### 步骤 1：环境检查

确认 Python 和 pip 可用，版本正确。

```bash
$PY --version          # 应显示 Python 3.12.x
$PY -m pip --version   # 应显示 pip 版本
```

红果短剧线路（可选）另需两项外部依赖：

```bash
ffmpeg -version        # 第 4 集及以后的 CENC 解密用
java -version          # 第 4 集及以后的 metasec 签名用（需 17+）
```

- **Java 必须装（Linux 线上）**：红果签名器是 unidbg（Java）程序。仓库里那个 `scripts/hongguo_sign/jre/` 是 **Windows 版**（只有 `java.exe` 与 `.dll`，128 个文件），**Linux 上跑不了**，所以线上要装 JDK 17 并在 `.env` 显式指定：
  ```dotenv
  HONGGUO_JAVA_BIN=/usr/bin/java
  ```
  该变量**优先级高于内置 `jre/`**（见 `sign_service._java_bin()`）。不设的话代码会先找不存在的 `jre/bin/java`，再回退 PATH 上的 `java`——而 uwsgi 的 PATH 往往很干净，容易找不到。
- **ffmpeg 必须可用**：默认取 PATH 上的 `ffmpeg`，也可用 `HONGGUO_FFMPEG_BIN` 指定绝对路径。**缺失时只有红果短剧「第 4 集及以后」会取流失败**（前 3 集是源站明链，不受影响）。
- **签名器运行物要单独补齐（不入库，git 拉不到）**：`sign/unidbg-sign.jar`（约 32MB）与 `capture/fq_oversea/` 下的 `libmetasec_ml.so`、`libc++_shared.so`、`ms_16777218.bin` 属第三方二进制，按 `scripts/hongguo_sign/start_sign_service.bat` 顶部说明获取后放到相同相对路径。**漏这一步的典型症状是：前 3 集能播，点播第 4 集报「红果离线签名服务的运行物缺失」**（本次线上就踩了这个坑）。

**验证**：

```bash
ffmpeg -version | head -1
java -version 2>&1 | head -1
ls -l scripts/hongguo_sign/sign/unidbg-sign.jar scripts/hongguo_sign/capture/fq_oversea/
```

四者的哈希应与开发机一致（`sha256sum` 比对即可），保证二进制没传坏。

---

### 步骤 2：安装项目依赖

```bash
cd {PROJECT_ROOT}
$PY -m pip install -r requirements.txt
```

> `requirements.txt` 若带 `-i https://pypi.tuna.tsinghua.edu.cn/simple` 镜像，pip 会自动使用。
> 注意：本项目的 `zhconv` 标注为**仅构建期**依赖（用于生成繁体词条），生产环境装了也不影响运行。

⚠️ **常见坑**：

- **IDE 终端有代理**会导致 pip 走 `localhost:8888` 失败。如果报连接错误，清除代理再装：
  ```bash
  env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY $PY -m pip install -r requirements.txt
  ```
- **requirements.txt 不全**：代码里 import 了但 requirements 没声明的包（如 `loguru`、`pycryptodome`），启动时会 `ModuleNotFoundError`。装完依赖后，执行步骤 11 前先用 `$PY manage.py check` 验证，看是否还缺包。

**验证**：

```bash
$PY manage.py check    # 应输出：System check identified no issues.
```

---

### 步骤 3：确认前端产物已随代码入库

本项目有以下**生成产物**，都随代码提交、**线上不重新生成**（线上也没有生成条件）：

| 产物 | 生成方式 | 何时需要重新生成（都在本地做） |
|------|----------|------------------------------|
| `API/static/css/output.css` | `tailwindcss.exe` 编译 | 新增 / 修改了 daisyUI、Tailwind 类名 |
| `locale/**/*.mo` | `python scripts/compile_locale.py` | 新增 / 修改了 `.po` 词条 |
| `API/migrations/*.py` | `manage.py makemigrations` | 模型变更 |
| `scripts/hongguo_sign/jre/` | `jlink`（命令见该目录 `start_sign_service.bat` 顶部） | **仅 Windows 用得上**；Linux 线上改用系统 JDK 17（见步骤 1） |
| `scripts/hongguo_sign/sign/`、`capture/` | **第三方二进制，不入库，需单独获取**（见步骤 1） | 首次部署 / 换机器——`git pull` 拿不到，漏了会让第 4 集点播报「运行物缺失」 |

> 本地生成命令见 README 第八章；**若这些文件缺失或过期，线上会出现「样式全乱」「语言切不动」等问题**。
> 改过文案后，本地生成顺序是：`check_i18n.py`（自查漏包翻译 / 词条缺失 / 跨行 `{# #}` 注释）→ `make_zh_hant.py`（繁体）→ `compile_locale.py`（`.mo`），再把 `.mo` 随代码提交。
> `jre/` 虽随代码入库（约 32MB），但它是 **Windows 版**：Linux 线上要装 JDK 17 并设 `HONGGUO_JAVA_BIN`（见步骤 1）。
> 同目录的 `sign/unidbg-sign.jar` 与 `capture/` 是第三方二进制、**不入库**，`git pull` 拿不到，必须按步骤 1 单独补齐。

**验证**：

```bash
ls API/static/css/output.css
ls locale/en/LC_MESSAGES/ locale/zh_Hant/LC_MESSAGES/
ls API/migrations/00*.py | tail -3
ls scripts/hongguo_sign/jre/bin/                       # 红果短剧线路：内置 JRE（仅 Windows 有效）
ls scripts/hongguo_sign/sign/unidbg-sign.jar scripts/hongguo_sign/capture/fq_oversea/
                                                       # 红果短剧线路：第三方运行物（不入库，必须手工补齐）
sha256sum scripts/hongguo_sign/sign/unidbg-sign.jar scripts/hongguo_sign/capture/fq_oversea/*
                                                       # 与开发机比对，确认二进制没传坏
```

---

### 步骤 4：配置 .env

确保 `.env` 文件内容正确，关键项：

```dotenv
SECRET_KEY=<生产环境重新生成，禁止使用开发值>
DEBUG=False                         # 上线必须 False
ALLOWED_HOSTS=你的域名,.你的域名,127.0.0.1,localhost   # 不要填 *
# 要覆盖子域必须写成**前导点**形式 `.你的域名`（同时也覆盖主域本身）；
# 写成 `*.你的域名` 不生效，Django 会直接返回 400 Bad Request（实测踩过）。
# 生产环境不设置 XYAPI_COOKIE_ISOLATION（或设为 false）→ 自动进入生产安全模式：
# 标准 Cookie 名 + 强制 HTTPS Cookie（SESSION_COOKIE_SECURE=True）
```

⚠️ **两个必须注意的点**：

1. **`SECRET_KEY` 上线后不可再变更**：它还用于 `app_secret`、**AI 厂商的 API Key** 等凭据的密文派生，变更后已加密数据（接入项目的 APPSECRET、后台维护的 AI Key）将无法解密，需要重新发放 / 重新填写。请备份，且生产与开发用不同值。
2. **`.env` 含中文 + 系统未生成 `zh_CN.UTF-8` locale** 会导致应用加载失败。

关于第 2 点的细节：系统的 `LANG=zh_CN.UTF-8`，但实际**没生成**这个 locale（只有 `C.utf8` 和 `en_US.utf8`）。Python 启动时发现 locale 无效，退回 **ascii 编码**。`load_dotenv()` 把中文键或中文值写入 `os.environ` 时会报 `UnicodeEncodeError: 'ascii' codec can't encode characters`。

**三种解决方案（任选其一，推荐方案 B）**：

- **方案 A（最稳，但限制大）**：.env 的键和值都用纯 ASCII。站点名等中文值改成英文，代码里再中文化。❌ 不适合必须存中文的场景。
- **方案 B（项目级，推荐）**：在 `uwsgi.ini` 加一行 `env = LANG=C.UTF-8`（见步骤 10），让 uwsgi 的 Python 用 UTF-8 编码。C.UTF-8 是系统已有的 locale，无需额外生成。
  注：本项目的默认站点名（`XYAPI_WEB_APP_NAME`，默认「小影API官网」）在代码里有中文兜底，不写进 `.env` 就不会触发该问题。
- **方案 C（系统级治本）**：执行 `locale-gen zh_CN.UTF-8 && update-locale`，生成缺失的 locale。一劳永逸，但改的是系统全局。

**验证**：.env 配置是否生效（用项目 python 测）：

```bash
$PY -c "import os; os.environ['DJANGO_SETTINGS_MODULE']='XiaoYingAPI.settings'; import django; django.setup(); from django.conf import settings; print('DEBUG=', settings.DEBUG); print('ALLOWED_HOSTS=', settings.ALLOWED_HOSTS)"
```

---

### 步骤 5：收集静态文件

⚠️ **前提**：`settings.py` 必须配置 `STATIC_ROOT`（收集到的静态文件存放目录）：

```python
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')   # 收集目录
```

执行收集：

```bash
cd {PROJECT_ROOT}
$PY manage.py collectstatic --noinput
```

⚠️ **常见坑**：

- **STATIC_ROOT 和 STATICFILES_DIRS 重叠**：如果 `STATICFILES_DIRS` 也指向 `STATIC_ROOT` 同目录，collectstatic 会报警告。把 STATICFILES_DIRS 指向**源码静态目录**，STATIC_ROOT 用单独目录。
- **权限**：用 www 用户执行，确保收集的文件 www 可读：
  ```bash
  runuser -u www -- $PY manage.py collectstatic --noinput
  ```
- **产物不随代码更新**：`static/` 目录不入库，每次改过前端资源后都要重新收集并重启 uwsgi，否则线上仍是旧文件。

**验证**：

```bash
ls static/css/output.css        # 前端样式产物（缺失会导致页面样式全乱）
ls static/js/site/              # 站点脚本
```

---

### 步骤 6：确认迁移文件已随代码入库（A-05 整改）

> 迁移文件（`*/migrations/00xx_*.py`）现在随代码入库，**禁止在线上运行 `makemigrations`**——
> 线上生成的迁移名/依赖会与代码库不一致，造成迁移漂移（历史事故根因之一）。
> 模型变更统一在本地 `makemigrations` 生成后随代码提交，线上只执行 `migrate`。

**验证（在代码目录）**：

```bash
git ls-files | grep migrations/    # 应能看到 00xx_*.py 迁移文件已被 git 跟踪
```

> 注：若你是从旧版本升级（此前迁移文件未入库、线上已自行生成过迁移），请先核对线上
> `django_migrations` 已应用记录与代码库迁移文件一致（`python manage.py showmigrations`），
> 不一致时以代码库迁移集为准补齐后再走步骤 7。

---

### 步骤 7：执行数据库迁移

```bash
runuser -u www -- $PY manage.py migrate
```

> 用 `www` 用户执行，确保 `db.sqlite3` 及其 `-wal`/`-shm` 文件归 www 所有，uwsgi 进程能读写。

⚠️ **常见坑**：

- **db.sqlite3 是空文件（0 字节）**：说明从未迁移过，执行本步后会建表。
- **表不存在报错 `no such table: xxx`**：就是没迁移。本步解决。
- **locale 问题导致 migrate 都跑不起来**：加 `LANG=C.UTF-8`：
  ```bash
  runuser -u www -- env LANG=C.UTF-8 $PY manage.py migrate
  ```

**验证**：

```bash
$PY manage.py showmigrations    # 所有迁移应为 [X]（已应用）
```

> ⚠️ **历史提示（`0053` / `0054` 的额度体系）——该体系已在迁移 `0062` 整体下线**：下面的「充值额度 / 设置单价」已不再需要，此块仅作历史备查。当前口径是**项目启用 + 签名通过即可调用全部 `/api/` 接口，不按次计费、无额度门槛**；迁移 `0062` 会把 `api_price_policy` / `appcreditledger` 两张表与 `UserApp.balance` / `owner`、`PaySetting.points_per_yuan`、统计表的 `cost_points` 等字段一并删除，**migrate 即完成，无需任何连带操作**。

> 补充（迁移 `0055_payment`）：新增第三方支付相关表（`pay_setting` / `pay_provider` / `pay_order` / `pay_notify_log` / `user_balance_ledger`）并给 `user` 加 `balance`（账户余额，元）字段，**纯结构迁移、无数据回填**，`migrate` 即完成。上线后若要开在线支付，到控制台「支付设置」页 `/console/pay/` 填商户ID与两把密钥并启用渠道（见步骤 8.3）；支付回调地址由系统按当前站点域名自动生成（`/pay/notify/<渠道>/`），**无需在商户后台手工填路径**，但需保证域名公网 HTTPS 可达。

> 补充（迁移 `0056_pay_free_price`）**已随 `0062` 失效**：该迁移当时给「线路价格」表插了一条 `/api/pay/ = 0 点/次`，用于避免支付接口被单价门槛拦下。计费体系下线后不再有单价，这张表与这条记录都已被 `0062` 删除。

> 补充（迁移 `0064_platformaccount`）：新增**通用平台账号表** `platform_account`（`PlatformAccount`，托管第三方平台账号与登录凭据 Cookie，密码 / 凭据 AES 加密落库），**纯结构迁移、无数据回填**，`migrate` 即完成。上线后到「数据运营 → 账号管理」`/console/accounts/` 录入知乎 / 微博等平台的账号与 Cookie；要用知乎热榜（`/api/zhihu/hot`）或微博服务（`/api/weibo/feed`）必须先在这里配一条有效凭据（见步骤 8.8）。

> 补充（迁移 `0065_open_weibo_video`）：把微博**视频代理播放**端点 `/api/weibo/video` 写成**端点级「开放」策略**（免项目签名；`<video>` 带不了签名，且拖动进度条会发多次 Range 请求、撞上一次性 nonce 的重放拦截），鉴权改由 `feed` 下发的时效令牌承担。**纯数据迁移、无结构变更**，`migrate` 即完成；该路径另有代码内免签名单兜底（`API/common/middleware.py` 的 `PUBLIC_PATHS`），即使漏跑迁移也能正常播放。

---

### 步骤 8：重建 API 服务分类树（⚠️ 本项目必做）

> **已废弃（分类树已移除）**：以下步骤针对已移除的「API 服务分类」分类树与 `rebuild_category_tree` 命令，现已不再需要。认证与对外状态改由「服务策略」（`ApiServicePolicy`，服务/线路/端点三级逐级继承）管理，公开节点（图形验证码 / 调用统计）的开放策略由迁移 `0028` 自动写入；未命中任何策略的 `/api/` 路径按 fail-closed 需要签名。

「API 服务分类」数据由管理命令（扫描 `API/apis/` 目录）生成，**不依赖迁移**。所以线上 `migrate` 只建空表、**没有分类数据**；而 A-01 之后新增服务默认「需要认证」，分类树为空会导致接口匿名请求被直接拒绝（返回 20011）。

```bash
runuser -u www -- $PY manage.py rebuild_category_tree
```

该命令**幂等**、可重复执行：按当前 `API/apis/` 目录实时扫描生成/同步分类树，不覆盖手工配置过的认证模式与启用状态；后续新增服务目录后重新执行即可同步（执行后自动使认证缓存失效）。

**验证**：命令输出应显示各服务分类已生成；也可直接调用一个公开接口（如 `/api/captcha_auth/aliyun/config`）确认可匿名访问。

---

### 步骤 9：创建超级管理员账号

```bash
$PY manage.py createsuperuser
```

按提示输入用户名、邮箱、密码。

⚠️ **注意**：本项目**没有 `/admin/` 后台**（`django.contrib.admin` 与 `django-simpleui` 已移除，访问 `/admin/` 返回 404）。管理入口是官网自带的「超级管理员控制台」：

1. 浏览器打开 `https://{DEPLOY_DOMAIN}/login/`；
2. 用「账号 + 密码」方式输入刚才创建的超管账号；
3. 服务端识别为超管后建立超管会话并回跳首页，页头随即出现「超级管理员」入口，点击进入 `/console/projects/` 管理接入项目。
4. 若站点要用 AI 服务（`/api/ai/`）：进入 `/console/ai/models/` 维护厂商与模型。升级场景下迁移 `0038` 已把旧 `.env` 的 `DEEPSEEK_API_KEY` / `DEEPSEEK_API_URL` 自动搬进库，此处只需核对掩码、用行内「测试」按钮确认连通性；新增厂商（Kimi / 豆包 / 千问等）同样是加一条记录，**无需改代码、不用重启**。AI 的 Key 只以密文落库、页面不回显原文，编辑时留空即不修改（详见 README 第七章第 8 节）。

**验证**：记住刚才创建的账号密码，步骤 14 登录测试。

---

### 步骤 10：配置 uwsgi.ini

完整模板（本项目可直接用，注意替换 `{PROJECT_ROOT}`、`{LOG_ROOT}`）：

```ini
[uwsgi]
# 项目目录
chdir={PROJECT_ROOT}

# wsgi 文件
wsgi-file={PROJECT_ROOT}/XiaoYingAPI/wsgi.py

# application 变量名
callable=application

# 虚拟环境与依赖路径（必须指定，否则用系统 Python 找不到 django）
virtualenv={PROJECT_ROOT}/.venv
pythonpath={PROJECT_ROOT}/.venv/lib/python3.12/site-packages

# 进程 / 线程
processes=4
threads=2

# pid 文件（用于停止/重启）
pidfile={PROJECT_ROOT}/uwsgi.pid

# 监听地址（S-11：生产仅监听回环，由本机 Nginx 反代对外，禁止 0.0.0.0 裸监听）
http=127.0.0.1:10000

# 运行用户
uid=www
gid=www

# 主进程
master=true

# 关键（SQLite + prefork 必加）：让每个 worker 各自加载应用
# uwsgi 默认在 master 里加载应用再 fork。本应用的 AppConfig.ready() 会启动
# 「反馈中心 AI 审核线程」并立刻读库，于是 master 先建好 SQLite 连接；fork 之后
# 各 worker 共享同一个 fd，并发写 WAL 库即报 `sqlite3.OperationalError: disk I/O error`
# （现象：页面正常，但凡需签名 / 写库的接口随机 500）。加上本项即可根治，详见第七节与第四节的排查表。
lazy-apps=true

# 缓冲区
buffer-size=32768

# 后台运行 + 日志
daemonize={LOG_ROOT}/uwsgi.log

# 静态文件映射（注意：/static= 前面有挂载点路径）
static-map=/static={PROJECT_ROOT}/static

# 清除继承的代理变量，避免爬虫走无效代理（localhost:8888）
unset-env=http_proxy,https_proxy,HTTP_PROXY,HTTPS_PROXY

# 关键：让 Python 用 UTF-8 编码，避免 .env 中文值导致 ascii 编码失败
env=LANG=C.UTF-8
```

⚠️ **五个高频坑**：

| 坑 | 错误写法 | 正确写法 | 后果 |
|----|----------|----------|------|
| static-map 缺挂载点 | `static-map=/www/.../static` | `static-map=/static=/www/.../static` | uwsgi 拒绝启动 |
| 代理继承 | 不写 unset-env | `unset-env=http_proxy,...` | 爬虫走 localhost:8888 失败 |
| locale 编码 | 不写 env | `env=LANG=C.UTF-8` | .env 中文值导致应用加载失败 |
| 缺 virtualenv | 只写 chdir | `virtualenv` + `pythonpath` | `No module named 'django'` |
| **缺 lazy-apps** | 不写 lazy-apps | `lazy-apps = true` | 多 worker 共享 master 的数据库连接，**需签名 / 写库的接口随机 500**（`disk I/O error`） |

---

### 步骤 11：启动 uwsgi 并验证

```bash
cd {PROJECT_ROOT}
{UWSGI_BIN} --ini uwsgi.ini
```

> 如果在 IDE 终端启动，加 `env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY` 前缀，避免继承代理。宝塔面板或 SSH 启动则不需要。

**验证 1：看日志，确认应用加载成功**

```bash
tail -20 {LOG_ROOT}/uwsgi.log
```

看到这行就成功：

```
WSGI app 0 (mountpoint='') ready in 0 seconds
```

如果看到 `unable to load app 0` 或 `no app loaded`，说明加载失败，看日志里的 Traceback 排查（通常是缺依赖或 .env 编码）。

**验证 2：curl 测试首页**

```bash
curl -s -o /dev/null -w "%{http_code}\n" -H "Host: {DEPLOY_DOMAIN}" http://127.0.0.1:10000/
```

返回 `200` 即正常。返回 `500` 说明运行时有错，看日志或临时把 DEBUG 设 True 排查。

**停止 / 重启 uwsgi**：

```bash
# 停止
{UWSGI_BIN} --stop uwsgi.pid
# 重启（先 stop 再 start；改了 .env / 模板 / .mo 词条都必须完全重启，--reload 不生效）
```

> **红果短剧线路（可选）**：取流签名服务是 API 进程**按需自动拉起的 Java 子进程**（运行时用仓库内置的 `scripts/hongguo_sign/jre/`），**无需单独守护、也不必写进 uWSGI 配置**——端口已监听则直接复用，进程退出后下次请求会自动重新拉起。首次签名需等 JVM + unidbg 初始化（端口约 2 秒就绪，首个签名请求会排队等初始化完成，实测 1~3 秒），等待上限由 `HONGGUO_SIGN_START_TIMEOUT` 控制（默认 90 秒）；该进程的日志在 `logs/hongguo_sign.log`。

---

### 步骤 12：配置 Nginx 反向代理

在宝塔面板操作：

1. **网站 → 添加站点**：域名填 `{DEPLOY_DOMAIN}`，PHP 版本选「纯静态」，不创建数据库。
2. 进入站点设置 → **反向代理 → 添加反向代理**：
   - 代理名称：`uwsgi`
   - 目标 URL：`http://127.0.0.1:10000`
   - 发送域名：`$host`
3. 保存。

⚠️ **常见坑**：

- 反代目标端口要和 uwsgi.ini 的 `http=` 端口一致（10000）。
- 如果用 `socket=` 模式，nginx 要配 `uwsgi_pass` 而非 http 反代。新手建议用 `http=` 模式（本手册方案）。
- 宝塔已生成 `location /` 后，**禁止**再新增第二个 `location /`，否则 nginx 报 `duplicate location "/"`。

**验证**：浏览器访问 `http://你的域名/`（注意是 http，还没 SSL），应看到官网首页。

---

### 步骤 13：配置 SSL 证书

宝塔面板：站点设置 → **SSL → Let's Encrypt**，勾选域名，申请并强制 HTTPS。

⚠️ 生产模式 Cookie 强制 Secure（仅 HTTPS 传输），Nginx 必须向 Django 透传来源协议，否则会「登录成功但立即跳回登录页」：

```nginx
proxy_set_header X-Forwarded-Proto https;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header Host $host;
```

**验证**：浏览器访问 `https://你的域名/`，锁图标正常，首页可访问。

---

### 步骤 14：上线验证

逐项检查：

| 验证项 | 方法 | 期望结果 |
|--------|------|----------|
| 首页 | `https://你的域名/` | 200，正常显示 |
| 静态样式 | 查看首页源码里的 `/static/css/output.css` | 200（**不是** 404，也不是旧样式） |
| 登录页 | `https://你的域名/login/` | 200，登录表单正常 |
| 登录功能 | 输入错误密码 | 200 + 错误提示（不是 500） |
| 超管入口 | 用超管账号登录 | 登录成功、回跳首页、页头出现「超级管理员」 |
| 超管控制台 | 进入 `/console/projects/` | 200，可增删改查接入项目 |
| 控制台首页 | 进入 `/console/` | 200，左侧导航「概览 / 安全 / 接口治理 / 数据运营 / 用户支持」五组齐全 |
| 后台入口隐身 | 退出登录后访问 `/console/` | 404（默认开启，与访问不存在的地址一致，**不是** 302 跳登录页；可在 `/console/security/` 关掉） |
| 反馈中心与联系方式 | 进入 `/console/feedback/`、`/console/contacts/` | 200，可筛选反馈；联系方式页可维护平台字典与各项目联系方式 |
| 官网页脚「联系我们」 | 查看首页页脚 | 显示后台为「官网项目」（`WEB_APP_NAME`）配置的联系方式；一条都没配时整块隐藏（不报错） |
| 文档中心 | `https://你的域名/docs/` | 200，左侧服务菜单完整 |
| 在线调试 | `/docs/email/` 对开放端点发一次请求 | 返回真实响应 |
| 多语言 | 页头「语言」切到 `English` / `繁體中文` | 页面文案随语言切换，刷新后保持 |
| 旧后台 | 访问 `https://你的域名/admin/` | 404（本项目已移除后台，符合预期） |
| 接口签名 | 调用一个需认证接口（无签名） | 返回 20011（需认证），符合 fail-closed |
| uwsgi 日志无错误 | `tail {LOG_ROOT}/uwsgi.log` | 无 Traceback |

---

## 四、常见问题排查

| 现象 | 根因 | 解决 |
|------|------|------|
| `unable to load app 0` / `no app loaded` | 应用加载失败（缺依赖 / .env 编码 / import 错误） | 看日志 Traceback；`$PY manage.py check` 查缺包；检查 .env 中文 |
| `ModuleNotFoundError: No module named 'xxx'` | 依赖没装或 requirements 不全 | `$PY -m pip install xxx` |
| `No module named 'django'`（uwsgi 日志） | uwsgi 未加载虚拟环境 | uwsgi.ini 补 `virtualenv` + `pythonpath`，完全重启 |
| `UnicodeEncodeError: 'ascii' codec` | locale 未生成，Python 退回 ascii | uwsgi.ini 加 `env=LANG=C.UTF-8`，或 `locale-gen zh_CN.UTF-8` |
| `no such table: xxx` | 数据库没迁移 | 迁移文件已随代码入库，直接 `$PY manage.py migrate`（缺迁移时在本地生成并提交，勿在线上 makemigrations） |
| 500 但日志无 Traceback | DEBUG=False，异常被吞 | 临时把 .env 的 `DEBUG=True` 复现看 Traceback，排查后改回 False |
| 静态文件 404 | 没 collectstatic 或 static-map 错 | 执行 collectstatic；检查 `static-map=/static=...` |
| **页面样式全乱 / 新加的类名不生效** | `output.css` 未重编译或线上未 collectstatic | 本机重编译 `output.css` → 提交 → 线上 `collectstatic` → 重启 uwsgi |
| **语言切不动 / 英文或繁体页面还是中文** | ① `locale` 子目录名写成了 `zh-hant`（必须是 `zh_Hant`，否则 Django 静默找不到 `.mo`）② 改了 `.po` 没跑 `scripts/compile_locale.py` ③ 没重启 uwsgi | 逐条排查：核对目录名 → 本机编译并提交 `.mo` → 线上 collectstatic / 重启 |
| 爬虫/外网请求失败 | 继承了 IDE 代理 | uwsgi.ini 加 `unset-env=http_proxy,...` |
| 接口匿名调用返回 20011 | 该服务为「需要签名」（fail-closed 默认） | 到 `/console/services/` 的「服务策略」把对应服务/线路/端点设为「开放」或检查签名参数（原分类树与 `rebuild_category_tree` **已废弃**） |
| 登录成功但立即跳回登录页 | 生产 Cookie 强制 Secure，但 Nginx 没透传 `X-Forwarded-Proto https`，浏览器拒写 Cookie | 按步骤 13 补协议头 + 确认 HTTPS 证书生效 |
| uwsgi 进程在但请求 500 | 应用没加载成功（no app） | 重启 uwsgi；看日志是否 `ready` |
| 页脚「联系我们」整块不见了 | 后台没给「官网项目」（`WEB_APP_NAME`）配任何联系方式；按设计一条都没配就整块隐藏 | 到 `/console/contacts/` 选中官网项目，逐条新增平台与值 |
| 控制台页面样式错乱 / 弹窗打不开 | `output.css` 未重编译，或 `console_forms.js` 未 collectstatic / 引用处的 `?v=` 未 bump（浏览器仍在用旧缓存） | 本机重编译 `output.css`、确认 `console_forms.js` 的 `?v=` 已改 → 线上 collectstatic → 重启 uwsgi |
| **页面能打开，但需签名 / 写库的接口随机 500**，日志 `sqlite3.OperationalError: disk I/O error` | uwsgi 默认在 master 加载应用；本应用 `AppConfig.ready()` 启动的「反馈中心 AI 审核线程」会立刻读库，于是 master 先建好 SQLite 连接，fork 后各 worker 共享同一 fd，并发写 WAL 即冲突 | uwsgi.ini 加 **`lazy-apps = true`**（每个 worker 各自加载应用与连接），完全重启。验证：`lsof 项目/db.sqlite3` 里 master 进程不应再出现 |
| 短剧**点播第 4 集**报「红果离线签名服务的运行物缺失」 | `sign/unidbg-sign.jar` 或 `capture/fq_oversea/*` 没放（**第三方二进制不入库，`git pull` 拿不到**）；前 3 集走源站明链所以不受影响 | 按步骤 1 补齐那 4 个文件，`sha256sum` 与开发机比对一致；无需重启（签名服务按需拉起） |
| 短剧点播第 4 集报「找不到可用的 Java」 | Linux 线上没装 JDK 17，或 `.env` 没设 `HONGGUO_JAVA_BIN`（代码会先找内置 `jre/bin/java`，而那是 Windows 版） | `apt/dnf install` JDK 17，`.env` 设 `HONGGUO_JAVA_BIN=/usr/bin/java`，**完全重启 uwsgi** |
| 海角「视频播放列表」报 `视频密钥派生失败（node 调用异常）: [Errno 13] Permission denied: 'node'` | **服务器压根没装 node**，不是权限问题 —— PATH 里混着当前用户不可访问的目录（root 启动 uwsgi 会带上 `/root/bin`）时，Linux 把「文件不存在」误报成 `Permission denied`，照这条信息去 chmod 会查错方向 | 装 Node.js（官方静态包即可），或 `.env` 设 `HAIJIAO_NODE_BIN=/usr/local/bin/node`，**完全重启 uwsgi**。验证：`runuser -u www -- node -v` 能打印版本 |
| 短剧点播**长时间**停在「正在生成播放地址，请稍候重试」 | ① 确实在转（软编一集 30~40 秒，机器没有硬件编码器时更慢）；② **部署重启 uwsgi 打断转码留下的僵尸锁**；③ 上游取流卡住 | 先 `ps -ef | grep ffmpeg` + `tail logs/app.log \| grep hongguo`：**没有 ffmpeg 却一直 running = 状态卡死**。再看 `cache/dramas/hongguo_stream/*/*/*.lock` 里的属主 pid 是否还在（`ps -p <pid>`）——不在就删掉该锁，下一次点播自动重转（修复后此判断已内置，无需人工） |
| 控制台「一键部署」报 `docker: Error response from daemon: Conflict. The container name "napcat" is already in use`，紧随 `部署失败：命令返回码 125` | 机器上**已有同名容器**（服务器重启后它按 `--restart unless-stopped` 自动拉起了），而旧版脚本仍无条件 `docker run --name napcat` | **不要删容器重建**（QQ 登录态在容器里，重建必须重新扫码）。直接复用：先 `docker ps -a --filter name=^napcat$` 确认，再 `docker start napcat`。代码已内置探测（`API/apis/push/qqbot/setup.py` 的 `_pipeline_linux()` 命中即走复用分支），升级到该版本后「一键部署」可反复点 |
| QQBot **好友消息一条都不落库**：NapCat 显示已上报、我们回 200，但 `qq_private_message` 没有新记录；日志 `QQBot 事件上报体为空（Transfer-Encoding=chunked）` | NapCat 用 **chunked** 发请求体，而 **uwsgi 不解 chunked** —— 上报地址直连 uwsgi 时 Django 拿到的 `request.body` 是空的 | 让上报**绕本机 Nginx**（`proxy_request_buffering on` + `proxy_set_header Transfer-Encoding ""`），地址填 `http://127.0.0.1:18080/hook/qqbot/{hook_secret}/`；详见第九节第 3 步 |
| QQBot 的 HTTP 服务端端口（默认 `3000`）没在监听、`/console/qqbot/` 的「测试连接」连不上 | NapCat **还没扫码登录 QQ**（未登录时它不起 OneBot 服务）；或容器被重建 / 重启过导致登录态丢失 | 打开 NapCat WebUI 扫码。注意**登录态跟着容器走**：`docker rm` 重建必丢，实测某些版本连 `docker restart` 也丢 —— 见第九节第 4 步 |
| 代练搬单**一条都发不出去**；命令启动时打印 `警告：未配置 ORDER_MIGRATION_QQ` | 后台「代练搬单」页的**「我们的 QQ 号」为空** —— 发单时要把联系方式填进丸子订单，缺失则每单必失败 | 到 `/console/order-migration/` 填上我们的 QQ 号（页面优先于 `.env`，见第十节第 4 步） |
| 代练通相关接口全部失败；「账号管理」校验凭据返回 `DAILIAN_SIGN_KEY 未配置，无法校验` | `.env` 没配代练通接口签名密钥 | 补 `.env` 的 `DAILIAN_SIGN_KEY`（以及 `DLT_OSS_ACCESS_KEY_ID` / `DLT_OSS_ACCESS_KEY_SECRET`），重启 uwsgi |
| 代练通能发单，但**自动接单总是失败** | `dlt` 平台账号的凭据里缺 `pay_pass`（支付密码） | 重新登录代练通，把**含 `pay_pass` 的完整 JSON** 粘回「账号管理」并点校验（见第十节第 3 步） |

---

## 五、关键坑总结（血泪经验）

1. **依赖要装全**：`requirements.txt` 常常漏写（如 loguru、pycryptodome）。装完跑 `$PY manage.py check` 验证。
2. **locale 是隐形杀手**：系统声称 `zh_CN.UTF-8` 却没生成，Python 退回 ascii。只要 `.env` 有中文（键或值），`load_dotenv` 就炸。**每个项目 uwsgi.ini 都加 `env=LANG=C.UTF-8`**，或一次性 `locale-gen zh_CN.UTF-8`。
3. **数据库必须迁移**：迁移文件随代码入库（A-05），线上直接 `$PY manage.py migrate`，**禁止线上 `makemigrations`**。（原额外步骤 `rebuild_category_tree` **已废弃**——分类树已移除，认证改由「服务策略」管理，公开节点的开放策略由迁移 `0028` 自动写入。）
4. **static-map 语法**：`static-map=/static=绝对路径`，挂载点 `/static` 不能漏。
5. **代理变量继承**：IDE 终端启动 uwsgi 会继承 localhost:8888 代理，爬虫全废。加 `unset-env`。
6. **DEBUG=False 隐藏错误**：上线 500 时日志没 Traceback，临时开 DEBUG 排查，改完关掉。
7. **用 www 用户操作文件**：migrate、collectstatic 用 `runuser -u www --` 执行，避免 root 产生的文件 www 读不了。
8. **生成产物要在本地生成并提交**：`output.css`、`locale/**/*.mo`、`migrations/*.py` 线上都不重新生成。
9. **改了 .env / 模板 / .mo 必须完全重启 uwsgi**：`--reload` 对这几类不生效。
10. **SQLite + prefork 必须写 `lazy-apps = true`**：否则应用在 master 里加载、先建好数据库连接，fork 后各 worker 共享同一个 fd，并发写就 `disk I/O error` —— 而**页面还是好的**，只有接口随机 500，极易误判成「业务报错」。
11. **第三方二进制 `git pull` 拉不到**：红果签名器的 `sign/unidbg-sign.jar` 与 `capture/` 不入库，换机器 / 首次部署必须手工补齐；且内置 `jre/` 是 **Windows 版**，Linux 线上要另装 JDK 17 —— 文档里「Java 无需安装」只对 Windows 成立。**验证方式**：真跑一集第 4 集的转码（签 `app_api.get_episode_vids()` 能返回集数即说明签名通了）。
12. **`[Errno 13] Permission denied: '<命令>'` 未必是权限问题**：`subprocess` 调一个 PATH 里**根本不存在**的命令时，只要 PATH 里还混着当前用户**不可访问的目录**（root 启动 uwsgi 就会把 `/root/bin` 带进进程 PATH，见 `uwsgi.ini` 的启动方式），Linux 会把「文件不存在(ENOENT)」报成「权限不足(EACCES)」—— glibc 的 `execvp` 在有 EACCES 时优先报 EACCES。于是「服务器没装 node」被写成 `Permission denied: 'node'`，照它去 chmod 会查错方向（线上真踩过，见变更记录）。**排查口诀：先 `runuser -u www -- which <命令>`，确认文件到底在不在。**
13. **跑调试脚本要用运行用户**：以 root 跑探针 / 调试脚本会把 `cache/**`、`media/**` 下的文件写成 **root 属主**，而 Django 的文件缓存文件是 **0600** —— `www` 的 worker 立刻读不了，线上表现为接口随机 500（日志里是 `PermissionError: ... .djcache`）。统一用 `runuser -u www -- $PY <脚本>`；万一写脏了：`chown -R www:www cache media`。
14. **QQBot 的 NapCat 容器「已存在就复用」，绝不 `docker run` 第二次、更不删容器重建**：容器名固定 `napcat`，服务器重启后它按 `--restart unless-stopped` 自动拉起；此时再 `docker run --name napcat` 会因**名字冲突返回 125**（控制台表现为「一键部署」直接失败）。而**删掉重建更糟** —— **QQ 登录态存在容器里**，重建会被 NapCat 判为新设备、必须重新扫码。正确姿势：`docker ps -a --filter name=^napcat$` 先探测，存在就只 `docker start`。代码已内置该判断（`_pipeline_linux()`），复用时不回填本次新生成的 token，只同步容器自身的 `NAPCAT_TOKEN`（避免把能用的配置改坏）。**顺带**：`--filter name=` 是**包含**匹配，必须锚定成 `^napcat$`，否则 `napcat-old` 这类名字会被误判。
15. **NapCat 的事件上报必须过一层本机 Nginx**：它用 `Transfer-Encoding: chunked` 发请求体，而 **uwsgi 不解 chunked** —— 直连的结果是「NapCat 显示推了、我们回 200、但一条都没落库」（日志 `QQBot 事件上报体为空（Transfer-Encoding=chunked）`）。用一个只监听 `127.0.0.1:18080` 的 vhost 打开 `proxy_request_buffering` 并清掉 `Transfer-Encoding` 头即可。另：`/hook/qqbot/` **必须挂在 `/api/` 之外** —— 项目签名中间件只放行 `/api/`，而 NapCat 带不了我们的签名，来源可信度靠回调地址里的随机密钥（`PushSetting.hook_secret`）自证。
16. **QQ 登录态跟着容器走，别为了「干净重装」去 `docker rm`**：实测该版本**连 `docker restart` 都会丢**登录态，换网络模式重建（bridge → host 之类）同样会丢。所以容器要 `--restart unless-stopped`，而**能不停就不停**；真需要重建，就先准备好重新扫码。
17. **代练搬单在 `lazy-apps` 多 worker 下必须靠数据库互斥**：`AppConfig.ready()` 会在**每个 worker 里各起一份搬单线程**，且它们同步唤醒 —— 不加锁就会把**同一笔代练通订单重复发到丸子**（丸子余额重复扣、代练通双金重复冻结）。代码用「条件 UPDATE 抢本轮执行权」（`OrderMigrationSetting.run_lock_until`，占用最多 300 秒自动失效）解决，所以看到「**已有进程正在执行本轮**」的提示是**正常现象、不是故障**。同理：后台「自动运行」与常驻 `run_order_migration` 命令**不要同时开**。

---

## 六、安全加固要点（S-07 ~ S-12）

上线前对照以下清单逐项确认：

1. **CSRF 已恢复（S-07）**：系统已全局启用 CSRF 防护并仅豁免 `/api/` 前缀；官网表单（登录 / 注册 / 超管控制台）缺 `csrfmiddlewaretoken` 的 POST 会被 403 拒绝。若出现 403，检查 Nginx 是否吞掉 Cookie/表单字段，而非回退关闭 CSRF。
2. **SECRET_KEY 与 ALLOWED_HOSTS（S-08）**：`.env` 必须配置 `SECRET_KEY`（缺失服务拒绝启动）；`ALLOWED_HOSTS` 请填真实访问域名/IP，**不要**填 `*`（缺省仅允许 `127.0.0.1` / `localhost`）。SECRET_KEY 同时用于凭据密文派生，务必备份且上线后不再变更。
3. **uWSGI 仅监听回环（S-11）**：`http = 127.0.0.1:端口`，禁止 `0.0.0.0` 裸监听；对外统一由本机 Nginx 反代。
4. **Nginx 安全响应头**：`/media/` 等静态 location 追加 `add_header X-Content-Type-Options nosniff;`，对 `.svg/.html/.xml/.js/.php` 等用 `map` 按扩展名返回 `Content-Disposition: attachment`，防止上传文件被内联执行。
5. **db.sqlite3 防下载与备份加密**：Nginx 中必须显式拒绝数据库与敏感文件下载：
   ```nginx
   location ~* ^/(db\.sqlite3|\.env|uwsgi\.ini|.*\.py)$ { deny all; }
   ```
   定时备份 `db.sqlite3` 时应先 `stop` 或用 sqlite `.backup`，对备份文件做加密（如 `openssl enc -aes-256-cbc`）后再异地存放。
6. **管理入口收敛 + 后台入口隐身（S-12）**：本项目**已无 `/admin/` 后台**（该路由不存在），管理入口是官网超管控制台 `/console/projects/`，其访问条件是「持有 Django `is_superuser` 账号并通过 `/login/` 登录」。系统默认开启**后台入口隐身**（`SecuritySetting.hide_console`，控制台 `/console/security/` 可关）：未登录 / 非超管访问 `/console/**` **一律返回 404**（与访问不存在的地址完全一致），而不是 302 跳登录页 —— 避免后台入口被路径探测发现。**代价是超管本人也要先从 `/login/` 登录**再访问后台。建议额外限制：给超管账号设强密码 + 开启登录防爆破（系统已按 IP/账号锁定，见 S-03），必要时在 Nginx 层对 `/console/` 做 IP 白名单。
7. **存量凭据回填**：若项目含 S-06 存储改造，上线后执行一次 `python manage.py security_backfill`（一次性，带迁移标记）。
8. **A-01 fail-closed（重大行为变更）**：未命中任何策略的 `/api/` 路径默认「需要认证」——此前免签开放的能力型服务（upload/ddddocr/email/ai/ProxyIp/music/dlt/dlwz/seo/spider_verification 等）现在必须携带 app_id/timestamp/nonce/sign 签名才能调用；仅被显式设为「开放」的服务 / 线路 / 端点（如 captcha_auth/aliyun 与公开 GET 路径）可匿名。对接方需接入签名后再切流量。原「API 服务分类」分类树与 `rebuild_category_tree` **已废弃**，公开节点（图形验证码 / 调用统计）的开放策略由迁移 `0028` 自动写入；请在超管页面 **`/console/services/`** 的「服务策略」核对各服务 / 线路 / 端点的认证模式（服务→线路→端点三级继承，页面显示真实生效结果，保存即时生效）。
9. **A-05 日志与迁移**：`logs/` 目录由应用自动创建（相对项目根），确保运行用户（www）对其可写；上线错误排查优先看 `logs/error.log`（带 request_id，可到 `logs/app.log` 按 request_id 关联整条请求链路）。迁移文件已随代码入库，部署只跑 `migrate`。

---

## 七、本地开发 与 生产 的环境差异（别把开发口径带上线）

同一份代码，本机与线上的差别集中在下面几项上，**全是「宽松 vs 收紧」的关系**，而且基本都与安全相关。上线时逐项对照，**不要整体拷贝本机 `.env` 上去**（本机的 `DEBUG=True` / `ALLOWED_HOSTS=*` / 空的中转地址会直接把线上搞坏）。

| 配置 | 本地开发（怎么宽松都行，不外网暴露） | 生产（必须收紧） | 为什么 |
|------|--------------------------------------|------------------|--------|
| `DEBUG` | `True`（报错页直观） | **`False`** | `True` 会把源码 / 设置 / SQL 暴露给任何访问者，静态文件也由 Django 托管 |
| `ALLOWED_HOSTS` | `*`，或 `127.0.0.1,localhost` | 真实域名，如 `example.com,.example.com,127.0.0.1,localhost` | 生产填 `*` 等于关掉 Host 头校验（S-08）；**覆盖子域要用前导点 `.example.com`**，写成 `*.example.com` 不生效、会 400 |
| `XYAPI_COOKIE_ISOLATION` | `true`（与其他本地项目共用域名时不打架、不强制 HTTPS） | **删除或 `false`** | 生产要标准 Cookie 名 + 强制 HTTPS Cookie；需 Nginx 透传 `X-Forwarded-Proto` |
| uwsgi `http=` | 可以 `0.0.0.0:端口`（局域网 / 手机调试方便） | **`127.0.0.1:端口`** | `0.0.0.0` 会把应用端口裸暴露到公网，绕过 Nginx 的 HTTPS 与安全响应头（S-11） |
| uwsgi `lazy-apps` | 无所谓（`runserver` 单进程，用不到） | **`true`** | 见本手册步骤 10 与第五节第 10 条：多 worker 共享库连接会 `disk I/O error` |
| Java / 签名器 | Windows 本机有内置 `jre/`，开箱可用 | 装 **JDK 17** + 设 `HONGGUO_JAVA_BIN=/usr/bin/java` | 内置 `jre/` 只有 `java.exe` / `.dll`，是 **Windows 版**，Linux 跑不了 |
| Node.js | 开发机通常已装 | **必须自行安装 Node.js（≥ 18）**，装在非默认位置再设 `HAIJIAO_NODE_BIN` | 海角社区视频密钥派生（`node derive_key.js`）与抖音评论发布都靠 node；Linux 线上默认不带。少了它，海角取流会报「视频密钥派生失败（node 调用异常）」 |
| 签名器运行物 | 本机已放好 `sign/` 与 `capture/` | 首次部署要**手工补齐**（不入库） | 第三方二进制，`git pull` 拿不到；漏了第 4 集点播会报「运行物缺失」 |
| `SECRET_KEY` | 随意（可直接用 `django-insecure-` 开发值） | **与本地不同，且上线后固定不变** | 它参与库内 `app_secret` / AI Key 的密文派生，变更即这些数据无法解密 |
| `PROXY_JULIANG_API_BASE` | 留空（直连官方） | 海外服务器填**国内中转地址** | 巨量代理的取 IP 接口只认国内来源 |
| `PROXY_51DAILI_API_BASE` | 留空（直连官方） | 海外服务器填**国内中转地址**（nginx 反代） | 51代理 的取 IP 接口只认国内来源 |
| `PROXY_RELAY_URL`、`PROXY_RELAY_SECRET` | 留空 | 填**国内中转出口**地址与密钥 | 51代理 的**代理 IP 本身**也只在国内网络可达：海外服务器直连提取出来的 IP 一律 TCP 超时（实测 0/5）。中转机部署见 `scripts/hj_relay/hj_relay.py` 顶部说明 |
| `HAIJIAO_REGISTER_PROXY` | 留空（默认 `51daili`） | `relay` | 让海角自动注册的默认出口走国内中转；不设的话默认仍是「51代理（直连）」，在海外**必然失败** |
| 静态文件 | `runserver` 直接读源码目录 | `collectstatic --clear` 后由 Nginx 的 `alias` 提供 | 线上不跑 Django 的静态托管；改过 JS/CSS 还要同步 bump 模板 `?v=` |

> 一句话记法：**本地四项（`DEBUG` / `ALLOWED_HOSTS` / `XYAPI_COOKIE_ISOLATION` / uwsgi 监听地址）怎么宽松都行，生产一律反过来。**
> `.env.example` 与本节是这两套口径的权威说明；本机 `.env` 里 `XYAPI_COOKIE_ISOLATION`、`PROXY_JULIANG_API_BASE` 的注释也标了两种取值，改 `.env` 前先读那几行。

---

## 八、数据库自动备份与恢复

库是 SQLite（`db.sqlite3`），备份脚本为 `scripts/backup_db.py`（在线备份 + 完整性校验 + gzip + 按份数轮转）。

### 1. 为什么不能直接 `cp db.sqlite3`

库是**多 worker 并发写**的（uwsgi prefork + 后台巡检线程 + 批量导入），而且开了 WAL。`cp` 出来的副本很可能停在「写了一半」的状态——恢复时轻则丢最近的写入、重则直接 `database disk image is malformed`。脚本用的是 SQLite 官方的**在线备份接口**（`Connection.backup()`）：在事务边界上分页拷贝，**不用停服务、不阻塞写入**，产出的副本与源库自洽；落盘前还会对副本跑一次 `PRAGMA integrity_check`，不通过就报错退出并丢弃半成品（**绝不把坏备份留在备份目录里**）。

### 2. 手工跑一次（先确认能用）

```bash
cd /www/XiaoYing/XiaoYingAPI
runuser -u www -- .venv/bin/python scripts/backup_db.py            # 产出 ./backups/db-YYYYmmdd-HHMMSS.sqlite3.gz
runuser -u www -- .venv/bin/python scripts/backup_db.py --keep 30  # 保留最新 30 份（默认 14）
```

常用参数：`--db`（源库，默认 `<项目根>/db.sqlite3`）、`--out`（输出目录，默认 `<项目根>/backups`）、`--keep`（保留份数，`0` = 不轮转）、`--no-compress`（直接产出 `.sqlite3`）。

**必须用 `runuser -u www`**：以 root 跑会把产物写成 root 属主（第五节第 13 条），之后 `www` 自己反而删不掉、轮转失败。退出码约定：`0` 成功、`1` 失败（cron / 监控据此判断，失败不会静默）。

### 3. 配置 cron（每天 03:30）

```bash
# 编辑 www 自己的 crontab（避免 root 属主问题，也免得 cron 环境缺 PATH/LANG）
sudo -u www crontab -e
```

```cron
# 每天 03:30 备份数据库，日志追加到 logs/backup.log
# 注意：cron 的默认 PATH 很干净，用绝对路径；先 cd 进项目根，脚本按相对位置找 .venv
30 3 * * * cd /www/XiaoYing/XiaoYingAPI && .venv/bin/python scripts/backup_db.py >> logs/backup.log 2>&1
```

> 用 `sudo -u www crontab -e` 而不是 `sudo crontab -e`：后者以 root 运行，产物会变成 root 属主。
> 若坚持写在 root 的 crontab 里，命令必须包一层 `runuser -u www -- bash -c '...'`。

**检查是否在跑**：`tail -n 5 logs/backup.log` 应能看到 `完成：db-….sqlite3.gz（… MB，校验通过）`；`ls -lh backups/` 里最新一份的时间应是当天。

### 4. 备份目录不要暴露给 Nginx

备份产物放在项目根的 `backups/`（已在 `.gitignore` 中忽略，不会入库）。**不要**把它放到 `static/` 或 `media/` 下——那两个目录由 Nginx 直接对外提供，等于把整库公开下载。第六节第 5 条的 Nginx 拦截规则（`location ~* ^/(db\.sqlite3|\.env|uwsgi\.ini|.*\.py)$ { deny all; }`）建议再补一条备份文件名模式：

```nginx
location ~* ^/backups/ { deny all; }
```

### 5. 恢复（先停服务，再覆盖）

```bash
cd /www/XiaoYing/XiaoYingAPI
sudo systemctl stop <你的 uwsgi 服务名>          # 或 uwsgi --stop <pidfile>

cp db.sqlite3 db.sqlite3.broken.$(date +%s)     # 先把坏库挪开，别直接毁掉
gunzip -c backups/db-YYYYmmdd-HHMMSS.sqlite3.gz > db.sqlite3
rm -f db.sqlite3-wal db.sqlite3-shm             # WAL/SHM 是旧库的伴生文件，必须一并清掉

chown www:www db.sqlite3                        # 属主要对（见第五节第 13 条）
sudo systemctl start <你的 uwsgi 服务名>
runuser -u www -- .venv/bin/python manage.py migrate   # 若备份早于当前代码，补跑迁移
```

### 6. 异地副本要加密

备份与源库同盘时，不加密不会新增暴露面（数据本来就在那儿）；但**拷到异地 / 对象存储前应当加密**，例如：

```bash
openssl enc -aes-256-cbc -pbkdf2 -in backups/db-xxx.sqlite3.gz -out db-xxx.sqlite3.gz.enc
```

顺带一提：备份里含**接入项目的 APPSECRET 与后台维护的 AI Key 的密文**，而它们的解密依赖 `.env` 的 `SECRET_KEY`——所以 `SECRET_KEY` 也必须单独妥善备份，否则只恢复数据库也解不开这些凭据（见第六节第 2 条）。

### 7. 上线验证清单

| 项 | 期望 |
| --- | --- |
| 手工跑一次 | 退出码 0，`backups/` 出现当天的 `.sqlite3.gz`，日志含「校验通过」 |
| 产物属主 | `ls -l backups/` 是 `www:www`（不是 root） |
| 恢复演练 | 随便挑一份备份按第 5 节恢复到一个**临时目录**下的库，`PRAGMA integrity_check` 返回 `ok` |
| cron 生效 | 等到下一个 03:30（或临时把时间改成 1 分钟后）看 `logs/backup.log` 是否新增一行 |
| 轮转 | 连续跑几次后 `ls backups/` 的份数不超过 `--keep` |

---

## 九、QQBot（NapCat）部署与坑位

> **只在需要 QQ 机器人时部署**（消息推送 `/api/push/qqbot/send`、好友消息落库与 AI 自动回复、代练搬单的「打手 QQ 接待」）；不部署不影响主站。
> 控制台入口 `/console/qqbot/`（超管专属）。页面上的**「一键部署」按钮只负责「首次安装」**：机器上已经有 NapCat 时，请看第 2 条。

### 1. 前置：docker

NapCat 官方只提供 docker 镜像与 Windows 安装包，Linux 一律走 docker。

```bash
docker info                     # 确认已装且守护进程在跑
usermod -aG docker www          # 让运行用户也能操作；改完需重新登录生效
```

### 2. 起容器：**已有同名容器就复用，绝不再 `docker run`**

容器名固定 `napcat`。**首次**部署：

```bash
docker run -d --name napcat --restart unless-stopped \
  --network host \
  -e NAPCAT_TOKEN={自己生成一串随机串，须与「QQBot」页里填的一致} \
  mlikiowa/napcat-docker:latest
```

两个必须坚持的口径：

| 口径 | 为什么 |
| --- | --- |
| **`--network host` + 让 NapCat 只监听 `127.0.0.1`** | 与主站同一条安全原则（S-11：对外一律经本机 Nginx）。**不要用 `-p 3000:3000 -p 6099:6099`** —— docker 发布端口是直接往 iptables 的 `DOCKER` 链插 DNAT 规则，**早于 ufw / firewalld 的规则生效**，也就是说主机防火墙对这些端口形同虚设（云厂商的安全组在网络层仍然拦得住，但别指望主机防火墙）。一旦漏配安全组，等于把 NapCat 的 OneBot API（仅一个 token 保护）挂到公网 |
| **`--restart unless-stopped`** | 服务器重启后容器自动拉起，机器人不用人工恢复（**且登录态保留**，见第 4 条） |

**⚠️ 机器上已经有 `napcat` 容器时，不要再执行上面的 `docker run`。** 它会因**名字冲突**直接失败：

```
docker: Error response from daemon: Conflict. The container name "napcat" is already in use
部署失败：命令返回码 125
```

这正是控制台点「一键部署」会看到的那条报错。**更不能「先删掉再重建」** —— QQ 登录态存在容器里，重建会被 NapCat 判定为新设备、**必须重新扫码**。

正确做法是先探测、再决定：

```bash
docker ps -a --filter name=^napcat$ --format '{{.Names}} {{.Status}}'   # 必须用 ^ ... $ 锚定
docker start napcat                                                     # 已存在但没在跑 → 只启动
```

> 代码已内置这个判断：`API/apis/push/qqbot/setup.py` 的 `_pipeline_linux()` 会先探测同名容器，命中就走**复用分支**（不新建、也不回填本次新生成的 token，只把容器自身的 `NAPCAT_TOKEN` 同步回「QQBot」页）。**所以「一键部署」可以反复点，不会再破坏已配好的环境。**
>
> 界面上的「一键部署」在 Linux 下**执行的正是上面这条命令**（`--network host`、不再发布端口），口径已对齐 —— 首次安装可以直接用它。

> 关于「只监听回环」怎么落地：`--network host` 解决了「docker 绕过主机防火墙」的问题（端口回到普通进程手上，ufw / firewalld 重新生效），但 **NapCat 自己的配置里还有 `host` 字段**（`webui.json` 与 `onebot11.json` 的 `httpServers`），默认可能是 `0.0.0.0`。生产口径是把它改成 `127.0.0.1`，即**主机防火墙 + 应用自身**两层都收在回环上：WebUI（`6099`）只有经本机 Nginx 反代才能访问，OneBot HTTP（`3000`）只给本机用。

### 3. 事件回调：必须过一层本机 Nginx 解 chunked（否则一条消息都收不到）

NapCat 上报事件用的是 `Transfer-Encoding: chunked`，而 **uwsgi 不解 chunked**。让 NapCat 直连 uwsgi 的结果是：NapCat 显示上报成功、我们回 200，但 Django 拿到的 `request.body` 是空的，好友消息**一条都不落库**（日志 `QQBot 事件上报体为空（Transfer-Encoding=chunked）`）。

所以在**本机**起一个只监听回环的中转，由 Nginx 把请求体读完整再转发：

```nginx
# /www/server/panel/vhost/nginx/hook_local_{项目名}.conf
server {
    listen 127.0.0.1:18080;                 # 只回环，公网不可达
    server_name _;
    access_log /www/wwwlogs/{项目名}.hook.log;
    client_max_body_size 20m;

    location /hook/qqbot/ {
        proxy_pass http://127.0.0.1:{uwsgi端口};
        proxy_http_version 1.1;
        proxy_request_buffering on;             # 关键：先把 chunked 读完整
        proxy_set_header Transfer-Encoding "";  # 关键：去掉 chunked 头，改按 Content-Length 转发
        proxy_set_header Host {DEPLOY_DOMAIN};
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto http;
    }
    location / { return 404; }
}
```

再把这段地址填进 NapCat 的「HTTP 客户端 / 事件上报」：

```
http://127.0.0.1:18080/hook/qqbot/{hook_secret}/
```

`{hook_secret}` 取自 `/console/qqbot/` 页（即 `PushSetting.hook_secret`，只写进 NapCat 配置、不对外暴露）。改完 Nginx 记得 `nginx -t && nginx -s reload`。

> **为什么 `/hook/qqbot/` 不放在 `/api/` 下**：项目签名中间件只对 `/api/` 放行，而 NapCat 带不了我们的项目签名 —— 来源可信度靠回调地址里的随机密钥自证。

### 4. 扫码登录（唯一的人工步骤）

```bash
docker logs --tail 40 napcat         # 终端里会打印二维码 / 解码 URL
```

更省事的方式是把它的 WebUI 反代到一个子域名（同样只经本机回环访问容器端口）：

```nginx
# /www/server/panel/vhost/nginx/napcat.{DEPLOY_DOMAIN}.conf
server {
    listen 443 ssl http2;
    server_name napcat.{DEPLOY_DOMAIN};

    ssl_certificate     /www/server/panel/vhost/cert/{证书目录}/fullchain.pem;
    ssl_certificate_key /www/server/panel/vhost/cert/{证书目录}/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:6099;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;      # WebUI 走 WebSocket
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_buffering off;
    }
}
```

浏览器打开 `https://napcat.{DEPLOY_DOMAIN}/webui/?token={webui.json 里的 token}` 扫码。

**登录态是跟着容器走的**（实测口径）：

| 操作 | 登录态 |
| --- | --- |
| 服务器重启（容器按 `--restart unless-stopped` 自动拉起） | **保留** |
| `docker restart napcat` | **实测会丢**（该版本如此），需重新扫码 |
| `docker rm` 后重建 | **必丢** |
| `docker commit` 存快照后改用别的网络模式重建 | **会丢**（网络模式变了，NapCat 视作新设备） |

> 结论：**能不停就不停，能不改网络模式就不改**。这也是第 2 条强调「已存在就复用」的根本原因。

### 5. 回填配置与自检

1. 到 `/console/qqbot/` 填：HTTP 地址 `http://127.0.0.1:3000`、token（与容器 `NAPCAT_TOKEN` 一致）、**机器人 QQ 号**；
2. 点「测试连接」→ 应返回机器人昵称与 QQ 号；
3. 私聊机器人一句，控制台「好友消息」面板应实时出现该条，且库里能查到：

```bash
runuser -u www -- sqlite3 db.sqlite3 \
  "select id,direction,user_id,substr(content,1,30) from qq_private_message order by id desc limit 5;"
```

方向 `in` = 对方发来、`out` = 机器人（含 AI 自动回复）发出。**两条都在**，说明 `NapCat → 回环 Nginx → uwsgi → 落库 → 自动回复` 整条链路通了。

> NapCat 是**按账号**保存配置的：扫码后若端口仍不通，回 `/console/qqbot/` **填上机器人 QQ 号**再点一次「一键部署」—— 它才能把 HTTP 服务端写进该账号的配置。
> 扫码后 `3000` 端口才会开始监听（未登录时 NapCat 不起 OneBot 服务），这是「测试连接连不上」最常见的原因。

### 6. 依赖 QQBot 的功能

- **消息推送**：`/api/push/qqbot/send`（需签名），记录进「推送日志」`/console/push-logs/`。
- **AI 自动回复**：`/console/qqbot/` 页开关 + 三种内置人格；只回「值得回」的私聊，回复同样落进「好友消息」。
- **代练搬单的「打手 QQ 接待」**：复用同一个 NapCat 实例与 `/hook/qqbot/` 回调 —— **先把本节全部走通，再开搬单的「自动运行」**。搬单另有一条跨进程互斥要求（多 worker 下会重复发单），见 [变更记录.md](变更记录.md) 第 11 条与 `../API/apis/order_migration/utils.py`。

---

## 十、代练搬单部署（代练通订单 → 代练丸子发单）

> **只在需要搬单时部署**。它比主站多两层外部依赖（两个代练平台 + QQBot），**建议最后部署**，并且先 dry-run 观察再正式开跑。
> 控制台入口 `/console/order-migration/`（超管专属）。后台线程由 `API/apps.py` 的 `AppConfig.ready()` 启动（只在「对外提供服务」的进程里），**但只有开启「自动运行」才会真正发单**。

### 1. 它在干什么

每轮顺序固定：**取实时余额 → 抓单 → 过滤 → 随机抽单 → 逐条「余额够才发」→ 监控**。

| 阶段 | 说明 |
| --- | --- |
| 抓单 | 代练通王者公开池 + 搜索池，再映射成丸子可发的形态 |
| 发单 | 按「代练通双金 / 丸子发单成本」判断余额是否够，够才发；**任一余额不足即中断本轮发单**（已发的保留），避免「代练通已停接、丸子还在收单」的无效等待 |
| 监控 | 先查代练通原单还能不能接，再查丸子是否被接单 → 回到代练通接单取账号 |
| 验收巡检 | 丸子打手申请验收后，把完单图转传到代练通并申请完单 |
| 结算巡检 | 代练通验收结算后，自动去丸子「同意验收」给打手结账 |

### 2. 前置依赖

1. **QQBot 必须先走通**（第九节）：打手加好友后的「自动接待、索要丸子订单号」复用同一个 NapCat 实例与 `/hook/qqbot/` 回调。QQBot 不通 → 打手联系不上你，整条链路白跑。
2. **代练通相关 `.env`**（缺了接口直接失败）：

```bash
DAILIAN_SIGN_KEY=            # 代练通接口签名密钥；缺失时凭据校验直接返回「DAILIAN_SIGN_KEY 未配置」
DLT_OSS_ACCESS_KEY_ID=       # 代练通 OSS 直传凭据（「上传首图」等转存图片用）
DLT_OSS_ACCESS_KEY_SECRET=
```

3. **`.env` 的 `ORDER_MIGRATION_*` 只是兜底**：`ORDER_MIGRATION_QQ / INTERVAL / PRICE_MIN / PRICE_MAX` 都有对应的**后台页面配置**，且**页面优先、.env 回落**。新服务器可以只配页面。

### 3. 录入两个平台账号（`dlt` / `dlwz`）

搬单要同时登录代练通（进货）与代练丸子（出货），凭据都托管在「账号管理」`/console/accounts/`，**平台代码分别是 `dlt` 与 `dlwz`**。

凭据怎么拿：调各自的登录接口 —— **`code_type=Password` 可以直接用密码登录**，返回的就是要粘贴的那段凭据。

```bash
# 代练通 → platform=dlt
curl -X POST 'https://{DEPLOY_DOMAIN}/api/dlt/auth/login' \
  -d 'phone={手机号}&code={密码}&code_type=Password'

# 代练丸子 → platform=dlwz
curl -X POST 'https://{DEPLOY_DOMAIN}/api/dlwz/auth/login' \
  -d 'phone={手机号}&code={密码}&code_type=Password'
```

（需要短信验证码时用 `code_type=VerificationCode`，先调 `.../auth/send-code`。这两个接口需签名，实际调用见文档中心的在线调试。）

把返回的凭据整段粘进「账号管理」对应平台，点「校验」确认状态变「有效」。两个平台的凭据格式：

| 平台 | 凭据 | 备注 |
| --- | --- | --- |
| `dlt`（代练通） | JSON：`{"user_id": "...", "token": "...", "uid": "USR...", "pay_pass": "支付密码"}` | **`pay_pass` 不能少** —— 全自动「接单」要用它，缺了接单会失败 |
| `dlwz`（代练丸子） | 登录返回的 `data`（含 `accessToken`） | 校验时读的是 `accessToken` |

### 4. 后台设置（`/console/order-migration/`）

| 项 | 要点 |
| --- | --- |
| **我们的 QQ 号** | **必配**。发单时把它填进丸子的账号 / 密码 / 角色名与联系方式，引导打手加好友后私下交接；**留空则发单全部失败**（命令启动时会直接警告） |
| **撤销凭证图 URL** | 抢接失败要「申请撤销」时丸子强制至少一张图；**留空则撤销不了时只告警、不自动撤销** |
| 双金倍数 | 丸子双金 = 发布价 × 该倍数，两项均分，默认 2 |
| 价格区间 / 标题关键词 | 只搬该区间 / 含关键词的代练通订单；关键词最适合自测时「只搬自己发的单」 |
| 严选发单 / 接单门槛 | 是否要求打手 Lv2+ |
| 每轮发布上限 / 轮询间隔 | 间隔最小 5 秒，也是「被接单」检测的最坏延迟 |
| 通知 | 被接单可发邮件 / 浏览器语音播报（页面需开着）/ 私聊管理员 QQ（走 QQBot） |

### 5. 先 dry-run，再开自动运行

```bash
cd {PROJECT_ROOT}

# 只抓单 + 映射，不联网查余额、不真实发单 / 接单 / 撤单
runuser -u www -- $PY manage.py run_order_migration --once --dry-run

# 真实跑一轮（仍不开常驻）
runuser -u www -- $PY manage.py run_order_migration --once
```

确认抓单、映射、余额判断都正常，**最后**才回后台打开「自动运行」。

### 6. 两种驱动别同时用

| 驱动 | 开法 | 适用 |
| --- | --- | --- |
| 后台线程 | 后台页「自动运行」开关 | 常规方式；随服务起，跟着 uwsgi 走 |
| 常驻命令 | `manage.py run_order_migration`（可选 `--interval` / `--publish-limit`） | 排查 / 临时托管 |

**同时开会让同一批订单被两路抢**（第 7 条的锁虽能兜住，但没必要）。

### 7. 多 worker 必须靠数据库互斥（重要）

生产 uwsgi 是 `lazy-apps` + 多 worker，`AppConfig.ready()` 会在**每个 worker 里各起一份搬单线程**，而它们启动时刻几乎相同、循环又是「跑一轮 + 固定 sleep」，于是**同步唤醒**。不加锁的话，同一笔代练通订单会被多个 worker 同时发到丸子 —— **丸子余额重复扣、代练通双金重复冻结**。

代码用**一次条件 UPDATE 抢「本轮执行权」**解决（与反馈中心 AI 审核同一手法）：抢不到的进程直接跳过本轮；进程被 kill 时占用标记最多留 `RUN_LOCK_TTL_SECONDS`（300 秒）即自动失效，不会把锁永久占死。

所以看到「已有进程正在执行本轮，请稍后重试」的提示（或命令打印「已有进程在执行本轮，跳过」）**属正常现象，不是故障**。

### 8. 自检

```bash
runuser -u www -- sqlite3 db.sqlite3 \
  "select our_qq, price_min, price_max, auto_run, last_run_time, last_run_summary, last_error
     from order_migration_setting;"
```

`last_error` 为空、`last_run_summary` 形如「抓取 N / 发布 N / 丸子被接 N / 代练通接 N / 兜底 N」即属正常。
