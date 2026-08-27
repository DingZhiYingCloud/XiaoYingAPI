# cloak_guard - 请求访问策略守卫（斗篷）中间件

纯**本地判定**的 Django 中间件（**判定零网络依赖**）。按「类型 → 动作」策略模型，对不同类型的请求执行不同动作，**可用于 SEO 斗篷**（只想给搜索引擎蜘蛛看，不想给真人看）。

- 当前版本：**1.1.0**（`from cloak_guard import __version__`）

## 一、目录结构

```
cloak_guard/
├── __init__.py     # 版本号 + 导出 CloakGuardMiddleware
├── middleware.py   # Django 中间件入口：开关/路径排除/IP白名单/标记注入
├── classifier.py   # 请求分类器（Referer 优先 + UA 特征库）
├── actions.py      # 动作执行器（pass / redirect / not_found / render）
└── README.md
```

## 二、能做什么

| 类型 | 判定依据 | 可配置动作 |
|---|---|---|
| `spider` 搜索引擎蜘蛛 | UA 命中 Googlebot / bingbot / baiduspider 等 | 放行 / 302 / 404 / render |
| `human` 真人浏览器 | UA 命中 Chrome / Firefox / Safari / Edge 等 | 放行 / 302 / 404 / render |
| `direct` 直接访问 | **无 Referer**（最高优先级） | 404 / 302 / 放行 / render |
| `unknown` 脚本爬虫或未知 | UA 命中 python-requests / curl 等 | 404 / 302 / 放行 / render |

**动作类型**：
- `pass`：放行（继续处理请求）
- `redirect`：302 跳转（需配 `url`）
- `not_found`：返回 404
- `render`：**直接返回指定内容**，内容来源 5 种（按优先级 `html > template > file > url > domain`）——斗篷内容差异化核心

> **判定优先级（Referer 优先）**：先看有无 Referer，无 Referer 直接归为 `direct`；有 Referer 才按 UA 判 `spider` / `human` / `unknown`。
> 例：Chrome 直接输网址访问（无 Referer）→ 按 `direct` 处理。

## 三、接入步骤

### 1. 放置文件

将整个 `cloak_guard/` 目录复制到你的 Django 项目根目录的 `middlewares/` 文件夹：

```
your_project/
├── middlewares/
│   └── cloak_guard/          # 整个目录复制过来
├── manage.py
└── your_project/
    └── settings.py
```

### 2. 配置 settings.py

```python
# ── cloak_guard 请求访问策略守卫（斗篷）中间件配置 ──
CLOAK_GUARD_ENABLED = True  # 是否启用（默认 False）

CLOAK_GUARD_ACTIONS = {
    # 斗篷典型用法：蜘蛛放行看真内容，真人不给看
    'spider':  {'action': 'pass'},                                                              # 蜘蛛 → 放行
    'human':   {'action': 'redirect', 'url': 'https://example.com/redirect'},                  # 真人 → 302 跳走
    'direct':  {'action': 'not_found'},                                                         # 直接访问 → 404
    'unknown': {'action': 'render', 'html': '<h1>访问受限</h1>'},                               # 脚本爬虫 → 返回指定内容
    # render 内容来源示例（优先级 html > template > file > url > domain）:
    # 'spider':  {'action': 'render', 'template': 'cloak/real.html'},                                             # ② Django 模板
    # 'human':   {'action': 'render', 'file': 'cloak/fake.html'},                                                # ③ 本地文件（相对路径基于 BASE_DIR）
    # 'human':   {'action': 'render', 'url': 'https://xiaoyingapi.com/static/cloak/fake.html'},                  # ④ 远程 http 链接
    # 'unknown': {'action': 'render', 'domain': 'baidu.com'},                                                     # ⑤ 域名 iframe 渲染
}

# IP 白名单（支持单个 IP 和 CIDR），命中直接放行（方便自己调试查看真实页面）
CLOAK_GUARD_WHITELIST = ['127.0.0.1', '192.168.1.0/24']

# 路径前缀排除：这些路径不参与判定，直接放行（后台/静态/接口）
CLOAK_GUARD_EXEMPT_PATHS = ['/admin', '/static', '/api', '/media']
```

> 任何类型都可省略不配：`spider`/`human` 默认放行，`direct`/`unknown` 默认 404。

### 3. 注册中间件

```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # ... 其他中间件 ...
    'middlewares.cloak_guard.CloakGuardMiddleware',  # 建议放在 CommonMiddleware 之前
    'django.middleware.common.CommonMiddleware',
    # ...
]
```

## 四、配置项说明

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `CLOAK_GUARD_ENABLED` | `False` | 是否启用中间件 |
| `CLOAK_GUARD_ACTIONS` | 见默认动作表 | 各类型动作配置 |
| `CLOAK_GUARD_WHITELIST` | `[]` | IP 白名单（支持单个 IP 与 CIDR 网段） |
| `CLOAK_GUARD_EXEMPT_PATHS` | `[]` | 路径前缀排除列表 |

`CLOAK_GUARD_ACTIONS` 每项格式：
```python
'类型': {
    'action':   'pass' | 'redirect' | 'not_found' | 'render',
    'url':      '跳转地址',       # redirect 必填
    # render 内容来源（按优先级 html > template > file > url > domain，取第一个命中的）:
    'html':     'HTML 字符串',    # ① 直接字符串
    'template': '模板名',         # ② Django 模板（render_to_string 渲染）
    'file':     '文件路径',       # ③ 本地文件（绝对路径；相对路径基于 settings.BASE_DIR 解析）
    'url':      'http(s) 链接',   # ④ 拉取远程 HTML 内容返回（需 pip install requests）
    'domain':   '域名',           # ⑤ iframe 渲染该域名网站（如 baidu.com）
}
```

**默认动作**（类型缺省配置时）：

| 类型 | 默认动作 |
|---|---|
| `spider` | `pass` |
| `human` | `pass` |
| `direct` | `not_found` |
| `unknown` | `not_found` |

> `redirect` 缺 `url`、`render` 无任何内容来源或来源获取失败（模板不存在 / 文件读取失败 / 链接超时）、非法动作 → 均回退为放行并记 warning 日志。

## 五、标记注入（视图层斗篷）

无论是否放行，中间件都会在 `request` 上注入判定标记，**视图内可据此渲染不同内容**：

```python
def my_view(request):
    if request.is_spider:
        return render(request, 'real_page.html')      # 蜘蛛 → 真实内容
    if request.is_human:
        return render(request, 'cloak_page.html')     # 真人 → 假内容
    # request.guard_type: 'spider' / 'human' / 'direct' / 'unknown'
```

注入的属性：`request.guard_type`、`request.is_spider`、`request.is_human`、`request.is_direct`、`request.is_unknown`

## 六、判定逻辑

```
请求进入
 ├─ 路径命中 CLOAK_GUARD_EXEMPT_PATHS → 放行
 ├─ IP 命中 CLOAK_GUARD_WHITELIST      → 放行
 ├─ 有无 Referer？
 │    ├─ 无 → direct（直接访问）
 │    └─ 有 → UA 特征匹配：
 │         ├─ 命中蜘蛛特征（googlebot/bingbot/...）→ spider
 │         ├─ 命中浏览器特征（chrome/firefox/safari/...）→ human
 │         └─ 其他（python-requests/curl/未知）→ unknown
 └─ 按类型执行动作（pass / 302 / 404 / render）
```

UA 特征库位于 `classifier.py` 顶部三个常量，可自行增删：
- `SPIDER_UA_PATTERNS`：搜索引擎蜘蛛（Google/Bing/Baidu/Yandex/DuckDuckGo/360/搜狗 等）
- `HUMAN_UA_PATTERNS`：真实浏览器（Chrome/Firefox/Safari/Edge/Opera/IE）
- `SCRIPT_UA_PATTERNS`：脚本爬虫（python-requests/curl/wget/Go/okhttp/scrapy 等）

## 七、版本记录

| 版本 | 日期 | 变更 |
|---|---|---|
| 1.1.0 | 2026-08-27 | render 内容来源扩展：新增 `file`（本地文件路径）、`url`（远程 http 拉取）、`domain`（iframe 域名渲染）三种来源，优先级 html > template > file > url > domain |
| 1.0.0 | 2026-08-27 | 初版：本地判定（Referer 优先）+ 四动作（pass/redirect/not_found/render）+ 标记注入 + IP 白名单（CIDR）+ 路径排除 + 包结构 |

## 八、注意事项

1. **判定为启发式**：UA/Referer 均可被伪造，仅用于常规反爬/斗篷场景，不适用于高安全要求场景
2. `direct` 默认 404 会**误伤直接输网址的真人**（分享链接/书签访问），如需放行改配 `pass`
3. **斗篷有被搜索引擎判站的风险**（cloaking 是违反谷歌站长规范的行为），请评估后果后使用
4. `render` 的 `url` 来源需要客户端安装 `pip install requests`；拉取超时 5 秒，失败自动回退放行
5. **`url` 拉取是服务端发起的网络请求**，请只配置可信来源的链接（避免 SSRF 风险）
6. `domain` iframe 方式受目标站 `X-Frame-Options`/CSP 限制，部分网站（如百度）可能拒绝被嵌入，属正常现象
7. 日志 logger 名：`cloak_guard`，便于统一采集
