# Django 项目上线部署手册

> **适用环境**:宝塔面板 + Python 3.12 + uWSGI + SQLite + Nginx
> 以「小影聊天」项目为示例。部署其他项目时,把路径 / 域名 / 端口 / settings 模块替换为你自己的即可。
> 本手册总结了实际上线中踩过的所有坑,请**按顺序**执行,每步都有验证方法。

---

## 一、环境信息(先填好,后面命令要用)

| 项 | 小影聊天的值 | 你的项目(填) |
|------|--------------|----------------|
| 项目根目录 | `/www/wwwroot/xiaoying/小影聊天` | __________ |
| settings 模块 | `XiaoYingCMS.settings` | __________ |
| wsgi 文件 | `XiaoYingCMS/wsgi.py` | __________ |
| 域名 | `m-xiaoying-chat.com.cn` | __________ |
| uwsgi 端口 | `10001` | __________ |
| Python 路径 | `/www/server/pyporject_evn/versions/3.12.13/bin/python` | 同左 |
| uwsgi 路径 | `/www/server/pyporject_evn/versions/3.12.13/bin/uwsgi` | 同左 |
| 运行用户 | `www` | `www` |

> 后续命令默认在**项目根目录**下执行:`cd /www/wwwroot/xiaoying/小影聊天`
> 为简洁,用变量 `$PY` 代表 Python 路径,执行前先设:
> ```bash
> PY=/www/server/pyporject_evn/versions/3.12.13/bin/python
> ```

---

## 二、部署清单(Checklist)

| # | 步骤 | 小影聊天当前状态 | 完成 |
|---|------|------------------|------|
| 1 | 环境检查(Python / pip) | ✅ 已就绪 | ☐ |
| 2 | 安装项目依赖 | ✅ 已安装 | ☐ |
| 3 | 配置 .env 环境变量 | ⚠️ 需确认 | ☐ |
| 4 | 收集静态文件 | ❌ 待执行 | ☐ |
| 5 | 生成数据库迁移文件 | ✅ 已生成 | ☐ |
| 6 | 执行数据库迁移 | ✅ 已执行 | ☐ |
| 7 | 创建超级管理员账号 | ❌ 待执行 | ☐ |
| 8 | 配置 uwsgi.ini | ✅ 已配置 | ☐ |
| 9 | 启动 uwsgi 并验证 | ❌ 你手动执行 | ☐ |
| 10 | 配置 Nginx 反向代理 | ⚠️ 需确认 | ☐ |
| 11 | 配置 SSL 证书 | ⚠️ 需确认 | ☐ |
| 12 | 上线验证 | ❌ 待执行 | ☐ |

> 上面「小影聊天当前状态」是排查时已经帮你做好的部分,你可以直接跳到**未完成**的步骤。如果是新项目,请从步骤 1 全部走一遍。

---

## 三、详细步骤

### 步骤 1:环境检查

确认 Python 和 pip 可用,版本正确。

```bash
$PY --version          # 应显示 Python 3.12.13
$PY -m pip --version   # 应显示 pip 版本
```

**验证**:两条命令都有正常输出,不报 command not found。

---

### 步骤 2:安装项目依赖

```bash
cd /www/wwwroot/xiaoying/小影聊天
$PY -m pip install -r requirements.txt
```

> `requirements.txt` 第一行通常带 `-i https://pypi.tuna.tsinghua.edu.cn/simple` 镜像,pip 会自动用。

⚠️ **常见坑**:
- **IDE 终端有代理**会导致 pip 走 `localhost:8888` 失败。如果报连接错误,清除代理再装:
  ```bash
  env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY $PY -m pip install -r requirements.txt
  ```
- **requirements.txt 不全**:代码里 import 了但 requirements 没声明的包(如 `loguru`、`pycryptodome`),启动时会 `ModuleNotFoundError`。装完依赖后,执行步骤 9 前先用 `$PY manage.py check` 验证,看是否还缺包。

**验证**:
```bash
$PY manage.py check    # 应输出:System check identified no issues.
```

---

### 步骤 3:配置 .env

确保 `.env` 文件内容正确,关键项:

```dotenv
SECRET_KEY=django-insecure-xxxxx   # 改成你自己的随机串
DEBUG=False                         # 上线必须 False
ALLOWED_HOSTS=你的域名,www.你的域名
# 其他业务配置...
```

⚠️ **最大坑:.env 含中文 + 系统未生成 zh_CN.UTF-8 locale**

系统的 `LANG=zh_CN.UTF-8`,但实际**没生成**这个 locale(只有 `C.utf8` 和 `en_US.utf8`)。Python 启动时发现 locale 无效,退回 **ascii 编码**。`load_dotenv()` 把中文键或中文值写入 `os.environ` 时会报 `UnicodeEncodeError: 'ascii' codec can't encode characters`,导致应用加载失败。

**三种解决方案(任选其一,推荐方案 B)**:

- **方案 A(最稳,但限制大)**:.env 的键和值都用纯 ASCII。站点名等中文值改成英文,代码里再中文化。❌ 不适合必须存中文的场景(如 `SITE_NAME=小影CMS管理系统`)。
- **方案 B(项目级,推荐)**:在 `uwsgi.ini` 加一行 `env = LANG=C.UTF-8`(见步骤 8),让 uwsgi 的 Python 用 UTF-8 编码。C.UTF-8 是系统已有的 locale,无需额外生成。
- **方案 C(系统级治本)**:执行 `locale-gen zh_CN.UTF-8 && update-locale`,生成缺失的 locale。一劳永逸,所有项目受益,但改的是系统全局。

**验证**:.env 配置是否生效(用项目 python 测):
```bash
$PY -c "import os; os.environ['DJANGO_SETTINGS_MODULE']='XiaoYingCMS.settings'; import django; django.setup(); from django.conf import settings; print('DEBUG=', settings.DEBUG); print('ALLOWED_HOSTS=', settings.ALLOWED_HOSTS)"
```

---

### 步骤 4:收集静态文件

⚠️ **前提**:`settings.py` 必须配置 `STATIC_ROOT`(收集到的静态文件存放目录):
```python
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')   # 收集目录
```

执行收集:
```bash
cd /www/wwwroot/xiaoying/小影聊天
$PY manage.py collectstatic --noinput
```

⚠️ **常见坑**:
- **STATIC_ROOT 和 STATICFILES_DIRS 重叠**:如果 `STATICFILES_DIRS` 也指向 `STATIC_ROOT` 同目录,collectstatic 会报警告。把 STATICFILES_DIRS 指向**源码静态目录**(如 `assets/`),STATIC_ROOT 用单独目录(如 `staticfiles/`)。
- **权限**:用 www 用户执行,确保收集的文件 www 可读:
  ```bash
  runuser -u www -- $PY manage.py collectstatic --noinput
  ```

**验证**:
```bash
ls static/admin/      # 应有 admin 静态文件(css/js)
```

---

### 步骤 5:生成数据库迁移文件

> 如果项目已有 `migrations/` 目录且含 `0001_initial.py`,跳过本步。
> 小影聊天已执行过,跳过。

```bash
$PY manage.py makemigrations
```

⚠️ **常见坑**:
- **模型定义在 `models/` 包里**(不是单文件 `models.py`):必须确保 `models/__init__.py` 把所有模型 import 进来,否则 Django 不识别。
- **不带 app 名时报 "No changes detected"**:但明明有模型没迁移。这时**指定 app 名**强制生成:
  ```bash
  $PY manage.py makemigrations XiaoYingAdmin    # 换成你的 app 名
  ```

**验证**:
```bash
ls XiaoYingAdmin/migrations/    # 应有 0001_initial.py
```

---

### 步骤 6:执行数据库迁移

```bash
runuser -u www -- $PY manage.py migrate
```

> 用 `www` 用户执行,确保 `db.sqlite3` 及其 `-wal`/`-shm` 文件归 www 所有,uwsgi 进程能读写。

⚠️ **常见坑**:
- **db.sqlite3 是空文件(0 字节)**:说明从未迁移过,执行本步后会建表。
- **表不存在报错 `no such table: xxx`**:就是没迁移。本步解决。
- **locale 问题导致 migrate 都跑不起来**:加 `LANG=C.UTF-8`:
  ```bash
  runuser -u www -- env LANG=C.UTF-8 $PY manage.py migrate
  ```

**验证**:
```bash
$PY manage.py showmigrations    # 所有迁移应为 [X](已应用)
```

---

### 步骤 7:创建超级管理员账号

```bash
$PY manage.py createsuperuser
```

按提示输入用户名、邮箱、密码。

⚠️ **注意**:小影聊天的后台地址是 `/xiaoying_admin/`(自定义后台,不是默认 `/admin/`)。登录地址:`https://你的域名/xiaoying_admin/`

**验证**:记住刚才创建的账号密码,步骤 12 登录测试。

---

### 步骤 8:配置 uwsgi.ini

完整模板(小影聊天已配好,新项目参考):

```ini
[uwsgi]
# 项目目录
chdir=/www/wwwroot/xiaoying/小影聊天

# wsgi 文件
wsgi-file=/www/wwwroot/xiaoying/小影聊天/XiaoYingCMS/wsgi.py

# application 变量名
callable=application

# 进程 / 线程
processes=4
threads=2

# pid 文件(用于停止/重启)
pidfile=/www/wwwroot/xiaoying/小影聊天/uwsgi.pid

# 端口
http=0.0.0.0:10001

# 运行用户
uid=www
gid=www

# 主进程
master=true

# 缓冲区
buffer-size=32768

# 后台运行 + 日志
daemonize=/www/wwwlogs/python/小影聊天/uwsgi.log

# 静态文件映射(注意:/static= 前面有挂载点路径)
static-map=/static=/www/wwwroot/xiaoying/小影聊天/static

# 清除继承的代理变量,避免爬虫走无效代理(localhost:8888)
unset-env=http_proxy,https_proxy,HTTP_PROXY,HTTPS_PROXY

# 关键:让 Python 用 UTF-8 编码,避免 .env 中文值导致 ascii 编码失败
env=LANG=C.UTF-8
```

⚠️ **三个高频坑**:

| 坑 | 错误写法 | 正确写法 | 后果 |
|----|----------|----------|------|
| static-map 缺挂载点 | `static-map=/www/.../static` | `static-map=/static=/www/.../static` | uwsgi 拒绝启动 |
| 代理继承 | 不写 unset-env | `unset-env=http_proxy,...` | 爬虫走 localhost:8888 失败 |
| locale 编码 | 不写 env | `env=LANG=C.UTF-8` | .env 中文值导致应用加载失败 |

---

### 步骤 9:启动 uwsgi 并验证

```bash
cd /www/wwwroot/xiaoying/小影聊天
/www/server/pyporject_evn/versions/3.12.13/bin/uwsgi --ini uwsgi.ini
```

> 如果在 IDE 终端启动,加 `env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY` 前缀,避免继承代理。宝塔面板或 SSH 启动则不需要。

**验证 1:看日志,确认应用加载成功**
```bash
tail -20 /www/wwwlogs/python/小影聊天/uwsgi.log
```
看到这行就成功:
```
WSGI app 0 (mountpoint='') ready in 0 seconds
```
如果看到 `unable to load app 0` 或 `no app loaded`,说明加载失败,看日志里的 Traceback 排查(通常是缺依赖或 .env 编码)。

**验证 2:curl 测试首页**
```bash
curl -s -o /dev/null -w "%{http_code}\n" -H "Host: m-xiaoying-chat.com.cn" http://127.0.0.1:10001/
```
返回 `200` 即正常。返回 `500` 说明运行时有错,看日志或临时把 DEBUG 设 True 排查。

**停止 / 重启 uwsgi**:
```bash
# 停止
/www/server/pyporject_evn/versions/3.12.13/bin/uwsgi --stop uwsgi.pid
# 重启(先 stop 再 start)
```

---

### 步骤 10:配置 Nginx 反向代理

在宝塔面板操作:

1. **网站 → 添加站点**:域名填 `m-xiaoying-chat.com.cn`,PHP 版本选「纯静态」,不创建数据库。
2. 进入站点设置 → **反向代理 → 添加反向代理**:
   - 代理名称:`uwsgi`
   - 目标 URL:`http://127.0.0.1:10001`
   - 发送域名:`$host`
3. 保存。

⚠️ **常见坑**:
- 反代目标端口要和 uwsgi.ini 的 `http=` 端口一致(10001)。
- 如果用 `socket=` 模式,nginx 要配 `uwsgi_pass` 而非 http 反代。新手建议用 `http=` 模式(本手册方案)。

**验证**:浏览器访问 `http://你的域名/`(注意是 http,还没 SSL),应看到首页。

---

### 步骤 11:配置 SSL 证书

宝塔面板:站点设置 → **SSL → Let's Encrypt**,勾选域名,申请并强制 HTTPS。

**验证**:浏览器访问 `https://你的域名/`,锁图标正常,首页可访问。

---

### 步骤 12:上线验证

逐项检查:

| 验证项 | 方法 | 期望结果 |
|--------|------|----------|
| 首页 | `https://你的域名/` | 200,正常显示 |
| 后台登录 | `https://你的域名/xiaoying_admin/` | 200,登录页 |
| 后台登录功能 | 输入错误密码 | 200 + 错误提示(不是 500) |
| 后台登录成功 | 输入超级用户账号密码 | 进入后台 |
| 静态文件 | `https://你的域名/static/admin/css/base.css` | 200(css 内容) |
| uwsgi 日志无错误 | `tail /www/wwwlogs/python/小影聊天/uwsgi.log` | 无 Traceback |

---

## 四、常见问题排查

| 现象 | 根因 | 解决 |
|------|------|------|
| `unable to load app 0` / `no app loaded` | 应用加载失败(缺依赖 / .env 编码 / import 错误) | 看日志 Traceback;`$PY manage.py check` 查缺包;检查 .env 中文 |
| `ModuleNotFoundError: No module named 'xxx'` | 依赖没装或 requirements 不全 | `$PY -m pip install xxx` |
| `UnicodeEncodeError: 'ascii' codec` | locale 未生成,Python 退回 ascii | uwsgi.ini 加 `env=LANG=C.UTF-8`,或 `locale-gen zh_CN.UTF-8` |
| `no such table: xxx` | 数据库没迁移 | `$PY manage.py makemigrations && $PY manage.py migrate` |
| 500 但日志无 Traceback | DEBUG=False,异常被吞 | 临时把 .env 的 `DEBUG=True` 复现看 Traceback,排查后改回 False |
| 静态文件 404 | 没 collectstatic 或 static-map 错 | 执行 collectstatic;检查 `static-map=/static=...` |
| 爬虫/外网请求失败 | 继承了 IDE 代理 | uwsgi.ini 加 `unset-env=http_proxy,...` |
| admin 登录输错密码返回 500 | auth_user 表不存在 | 执行 migrate |
| uwsgi 进程在但请求 500 | 应用没加载成功(no app) | 重启 uwsgi;看日志是否 `ready` |

---

## 五、关键坑总结(血泪经验)

1. **依赖要装全**:`requirements.txt` 常常漏写(如 loguru、pycryptodome)。装完跑 `$PY manage.py check` 验证。
2. **locale 是隐形杀手**:系统声称 `zh_CN.UTF-8` 却没生成,Python 退回 ascii。只要 `.env` 有中文(键或值),`load_dotenv` 就炸。**每个项目 uwsgi.ini 都加 `env=LANG=C.UTF-8`**,或一次性 `locale-gen zh_CN.UTF-8`。
3. **数据库必须迁移**:新项目/新模型一定要 `makemigrations` + `migrate`。模型在 `models/` 包时确保 `__init__.py` 导入。
4. **static-map 语法**:`static-map=/static=绝对路径`,挂载点 `/static` 不能漏。
5. **代理变量继承**:IDE 终端启动 uwsgi 会继承 localhost:8888 代理,爬虫全废。加 `unset-env`。
6. **DEBUG=False 隐藏错误**:上线 500 时日志没 Traceback,临时开 DEBUG 排查,改完关掉。
7. **用 www 用户操作文件**:migrate、collectstatic 用 `runuser -u www --` 执行,避免 root 产生的文件 www 读不了。
