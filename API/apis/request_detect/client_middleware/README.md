# 请求身份识别 - 客户端 Django 中间件

## 一、简介

本中间件是小影API「请求身份识别」服务（`/api/request_detect/detect`）的客户端接入组件。
接入方在自己的 Django 项目里启用本中间件后，**每个请求**都会：

1. 自动提取请求头 → 调用小影API `detect` 接口
2. 获取判定结果（`type`：真人/蜘蛛/爬虫或未知，含置信度与来源分析）
3. **exec 执行**服务端返回的「该类型」对应的全部 Python 代码片段

代码片段由你在服务端 `code_snippets/` 目录维护，**按类型分目录**：

| 目录 | 触发类型 | 典型用途 |
|---|---|---|
| `code_snippets/human/` | 真人浏览器访问 | 埋点、统计、放行标记 |
| `code_snippets/spider/` | 搜索引擎蜘蛛（Googlebot 等） | 放行蜘蛛、SEO 抓取统计 |
| `code_snippets/unknown/` | 脚本爬虫 / 无法识别来源 | 拦截、记录、下发验证码 |

## 二、项目结构要求

本中间件按以下通用结构接入你的 Django 项目：

```
your_project/
├── middlewares/
│   └── request_detect.py      # 中间件（复制自本目录 request_detect.py）
├── .env                       # XIAOYING_API_BASE=https://xiaoyingapi.com
├── manage.py
└── your_project/
    └── settings.py
```

## 三、接入步骤

### 1. 安装依赖

```bash
pip install requests
```

### 2. 放置中间件文件

将 `request_detect.py` 复制到项目根目录的 `middlewares/` 文件夹：

```
middlewares/
└── request_detect.py
```

### 3. 确认 .env 配置

在 `.env` 中配置小影API基础地址（`python-dotenv` 已在 settings 中 `load_dotenv()`）：

```
XIAOYING_API_BASE=https://xiaoyingapi.com
```

> 即使不配置，中间件也有兜底默认值 `https://xiaoyingapi.com`，可跳过此步。

### 4. 配置 settings.py

在 settings.py 中追加（`os` 模块一般已导入，用于 `os.getenv`）：

```python
# ── 请求身份识别中间件配置 ──
REQUEST_DETECT_API_URL   = f'{os.getenv("XIAOYING_API_BASE", "https://xiaoyingapi.com")}/api/request_detect/detect'  # 小影API地址
REQUEST_DETECT_ENABLED   = True    # 是否启用本中间件（默认 False）
REQUEST_DETECT_FAIL_OPEN = True    # 检测接口不可用时: True=放行, False=拒绝(403)
REQUEST_DETECT_TIMEOUT   = 5       # 调用 detect 接口的超时秒数（默认 5）
```

### 5. 注册中间件

```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # ... 其他中间件 ...
    'middlewares.request_detect.RequestDetectMiddleware',  # 建议放在 CommonMiddleware 之前
    'django.middleware.common.CommonMiddleware',
    # ...
]
```

### 6. 维护代码片段

在**服务端** `API/apis/request_detect/code_snippets/<type>/` 目录放置你的 Python 代码。
该目录下**所有** `.py` 文件都会在命中对应类型时被返回并执行（按文件名排序）。

## 四、配置项说明

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `REQUEST_DETECT_API_URL` | `{XIAOYING_API_BASE}/api/request_detect/detect` | 小影API detect 接口地址 |
| `REQUEST_DETECT_ENABLED` | `False` | 是否启用中间件 |
| `REQUEST_DETECT_FAIL_OPEN` | `True` | 检测接口不可用时: `True` 放行 / `False` 返回 403 |
| `REQUEST_DETECT_TIMEOUT` | `5` | 调用 detect 的超时秒数 |

> 全部配置项均可缺省，中间件会自动取默认值，开箱即用。

## 五、代码片段编写规范

exec 执行时注入以下全局变量，可直接在你的代码中引用：

| 变量 | 说明 |
|---|---|
| `request` | 客户端当前请求对象（Django `HttpRequest`） |
| `detect_result` | detect 接口返回的 data 字典，含 `type/confidence/reasons/referer/is_spider/is_human/is_direct_access/ua` |
| `logger` | `logging.Logger`（name=`request_detect`），可直接打印日志 |

示例（`code_snippets/unknown/example.py`）：

```python
# 爬虫/未知来源：记录并拦截
logger.warning('拦截疑似爬虫: UA=%s confidence=%s', detect_result.get('ua'), detect_result.get('confidence'))

# 如需直接拒绝请求，可抛出异常或返回响应（需自行实现）
```

> 注意：代码在请求处理早期（中间件阶段）执行，请勿执行耗时或 IO 密集的操作，避免拖慢所有请求。

## 六、接口响应结构（供参考）

`POST /api/request_detect/detect`，表单参数全部可选，常用：

| 参数 | 说明 |
|---|---|
| `headers` | 原请求头 JSON 字符串（中间件自动提取，无需手动传） |
| `site` | 你的站点域名，用于判断 referer 是否为同站导航（可选） |
| `ip` | 客户端 IP，仅记录（可选） |

返回 `data` 关键字段：

```json
{
  "type": "unknown",
  "is_spider": false,
  "is_human": false,
  "is_direct_access": true,
  "confidence": 50,
  "reasons": ["未提供 User-Agent", "缺少 Sec-Fetch-* 系列头", "无 Referer（直接访问）"],
  "referer": { "present": false, "type": "direct", "raw": null },
  "code_files": [ { "filename": "example.py", "content": "..." } ],
  "ip": null,
  "ua": null
}
```

## 七、安全警告（务必阅读）

> **⚠️ 本中间件会 exec 执行 detect 接口返回的 Python 代码，属于远程代码执行（RCE）风险。**

请确保以下前提**同时满足**再投入生产：

1. **内网或完全可信环境**，detect 接口地址必须为 HTTPS
2. 服务端 `code_snippets/` 目录的代码**来自可信来源且经过评审**，禁止他人直接写入
3. 定期核查服务端代码片段内容，防止被恶意篡改后下发到所有接入客户端

若无法满足以上前提，建议改用「本地预置模式」：服务端只返回代码文件名，客户端从本地目录加载执行，代码不经网络传输。

## 八、常见问题

**Q: 检测接口挂了，请求会失败吗？**
A: 默认 `REQUEST_DETECT_FAIL_OPEN=True`，检测失败时放行请求并记录 error 日志；设为 `False` 则返回 403。

**Q: 代码执行失败会影响请求吗？**
A: 不会。单个代码文件执行失败会记录 error 日志并继续执行后续文件，不阻断请求。

**Q: 如何调试？**
A: 将 `REQUEST_DETECT_ENABLED` 打开后观察日志（logger name=`request_detect`）。也可先用 curl 直接调 detect 接口验证返回：
```bash
curl -X POST https://xiaoyingapi.com/api/request_detect/detect \
  -d 'headers={"User-Agent":"python-requests/2.31.0"}'
```
