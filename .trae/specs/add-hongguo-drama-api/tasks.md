# Tasks

> change-id: `add-hongguo-drama-api`
> 目标：把红果短剧**网页版**能做到的能力（榜单 / 分类 / 搜索 / 详情 / 前 3 集播放）全部上线；第 4 集起返回「开发中」占位。

- [x] Task 1: 缓存配置：为红果线路新增独立缓存与两档 TTL
  - [x] SubTask 1.1: `XiaoYingAPI/settings.py` 新增 `HONGGUO_DATA_CACHE_TTL`（默认 1440 分钟）与 `HONGGUO_MEDIA_CACHE_TTL`（默认 30 分钟），支持 `.env` 覆盖
  - [x] SubTask 1.2: `settings.py` 的 `CACHES` 新增 `'hongguo'` 项，`LOCATION` 指向 `cache/dramas/hongguo/`，结构与 `movie_555` 保持一致
  - [x] 验证：`python manage.py shell -c "from django.core.cache import caches; c=caches['hongguo']; c.set('k','v',60); print(c.get('k'))"` 输出 `v`，且 `cache/` 目录下出现 `dramas/hongguo/`

- [x] Task 2: 爬虫线路 `SpiderServices/dramas/hongguo/`
  - [x] SubTask 2.1: `utils.py` —— 集中管理 `BASE_URL`、UA、超时/重试常量、URL 构建（榜单 / 分类 / 搜索 / 详情 / 播放页）与 SSR 数据提取正则（含 `\u002F` 反转义）；**实现前先抓官网首页导航，枚举真实可用的分类频道 slug 并写入常量**
  - [x] SubTask 2.2: `cache.py` —— 复用 `movie_555` 的 `get_or_fetch` 形态，暴露 `DATA_TTL` / `MEDIA_TTL`
  - [x] SubTask 2.3: `main.py` —— `HongguoDramaSpider`，方法：
    - `get_rank(type, page)` 榜单
    - `get_categories()` 分类清单
    - `get_list(category, page)` 分类列表
    - `get_search(keyword, page)` 搜索
    - `get_detail(series_id)` 详情（含全量 `vid_list` → `episodes` + `playable` 标注）
    - `get_play(series_id, ep)` 播放（`ep<=3` 抓播放页取 `main_url`；`ep>3` 返回不支持标记）
  - [x] SubTask 2.4: 每条爬取路径按数据类（DATA_TTL）/ 媒体类（MEDIA_TTL）挂缓存
  - [x] 验证：写一次性脚本直接实例化爬虫，逐个方法打印返回；重点确认 `detail` 的 `episodes` 长度 == `episode_cnt`、`play(ep=2)` 能拿到 `http` 直链、`play(ep=4)` 返回不支持标记

- [x] Task 3: API 三件套与路由注册
  - [x] SubTask 3.1: `API/apis/dramas/hongguo/utils.py` —— 对爬虫的薄封装，统一 `(ok, data/message)` 返回
  - [x] SubTask 3.2: `API/apis/dramas/hongguo/request.py` —— 6 个视图（`rank` / `categories` / `list` / `search` / `detail` / `play`），含参数校验与 `_json_response`；`play` 对 `ep>3` 返回 `50002` 占位
  - [x] SubTask 3.3: `API/apis/dramas/hongguo/urls.py` —— 路由与 `name`（`dramas_hongguo_*`）
  - [x] SubTask 3.4: `API/apis/dramas/urls.py` —— 聚合服务根，仅 include 线路
  - [x] SubTask 3.5: `API/apis/urls.py` —— 追加一行 `path('dramas/', include('API.apis.dramas.urls')), # 短剧服务路由`
  - [x] 验证：`python manage.py check` 无错；逐个 `curl` 直连端点（本地可临时用匿名策略）确认成功 / 参数缺失 / 参数非法 / 第 4 集占位四类返回

- [x] Task 4: 文档中心接入
  - [x] SubTask 4.1: 新建 `API/website/docs/drama.py`，用 `ServiceSpec/ChannelSpec/EndpointSpec/ParamSpec` 声明 6 个端点
  - [x] SubTask 4.2: `API/website/docs/__init__.py` 的 `_SERVICES` 追加注册
  - [x] 验证：访问 `/docs/drama/` 页面渲染正常，6 个端点参数齐全，可在线调试并拿到真实响应

- [x] Task 5: 冒烟测试覆盖
  - [x] SubTask 5.1: `scripts/api_smoke_config.json` 追加短剧用例：榜单 / 分类 / 列表 / 搜索 / 详情 / 播放(第 2 集) / 播放(第 4 集，期望 `50002`) / 缺参 / 参数非法
  - [x] SubTask 5.2: 追加所需变量到 `vars_help` 与 `vars`（如短剧搜索关键词、示例 `series_id`）
  - [x] 验证：运行 `python scripts/test_all_api.py`，短剧相关用例全部按期望码通过

# Task Dependencies

- Task 2 依赖 Task 1（缓存实例与 TTL 必须先就位）
- Task 3 依赖 Task 2（视图层调用爬虫封装）
- Task 4 依赖 Task 3（文档声明需与实际路由对齐）
- Task 5 依赖 Task 3（冒烟需端点已可访问）
