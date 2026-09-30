# Checklist

> change-id: `add-hongguo-drama-api`
> 逐项验证，通过后勾选。验证结论：**30 / 30 通过，0 失败**（独立验证，含真机实测）。

## 缓存与配置

- [x] `settings.py` 含 `HONGGUO_DATA_CACHE_TTL` / `HONGGUO_MEDIA_CACHE_TTL`，且可被 `.env` 覆盖（`os.getenv`，默认 1440 / 30；运行时实测取值正确）
- [x] `CACHES['hongguo']` 已配置，落盘目录为 `cache/dramas/hongguo/`，与 `movie_555` 互不干扰（实测 keys `['default','movie_555','hongguo']`，LOCATION 各自独立）

## 爬虫层

- [x] `SpiderServices/dramas/hongguo/` 三件套齐备（`utils.py` / `cache.py` / `main.py`）
- [x] `utils.py` 中的分类 slug 是通过**实际抓取官网导航**枚举得到的真实值，非臆造（代码 `{real-drama, comic-drama, ai-drama, comic}` 与官网 `/category/*` 实测完全一致）
- [x] `get_rank` 返回列表含 `series_id` 与排名/热度字段（实测 20 条，`rank`/`heat`/`score`/`favorite`/`like` 齐全）
- [x] `get_categories` 返回可直接传给 `get_list` 的 `slug`（4 个 slug，并已用 `real-drama` 调 `get_list` 成功）
- [x] `get_list(category, page)` 分页有效（第 1/2 页各 24 条，`series_id` 交集为 0）
- [x] `get_search(keyword, page)` 能返回匹配结果（实测「保姆」10 条）
- [x] `get_detail(series_id)` 的 `episodes` 长度等于 `episode_cnt`（222=222），且 `ep<=3` 标 `playable=true`、`ep>3` 标 `playable=false`
- [x] `get_play(series_id, 2)` 能取到 `http` 开头的 CDN 直链（实测 `https://v11-hgweb.qznovelvod.com/...`）
- [x] `get_play(series_id, 4)` 返回「不支持」标记（`playable=False` / `reason='need_app'`），且**不抛异常**
- [x] 数据类与媒体类分别使用 DATA_TTL / MEDIA_TTL 缓存（`main.py` 详情→DATA_TTL、播放→MEDIA_TTL；实测清缓存后首次 0.417s、二次 0.009s）

## API 层

- [x] `API/apis/dramas/hongguo/{urls,request,utils}.py` 三件套齐备
- [x] `API/apis/dramas/urls.py` 仅做 include 聚合，无业务逻辑
- [x] `API/apis/urls.py` 已追加 `dramas/` 注册行且带中文注释
- [x] 所有端点返回统一契约 `{code, msg, data}`，成功为 `10000`（6 个端点成功路径实测通过）
- [x] 缺参返回 `20001`；类型/枚举非法返回 `20002` / `20003`（实测：缺参 4 例→20001，非法枚举→20003，`series_id=abc`→20002）
- [x] `play` 接口 `ep=4` 返回 `50002` 且 `data.status == "developing"`（实测通过）
- [x] `play` 接口 `ep` 超过总集数返回 `20003`（`ep=99999` 实测通过）
- [x] 视图层未直接访问网络/爬虫逻辑（`request.py` 导入仅 `JsonResponse`/`require_http_methods`/`StatusCode`/本服务 `utils`）
- [x] `python manage.py check` 通过（`no issues (0 silenced)`）

## 文档中心

- [x] `API/website/docs/drama.py` 已创建并声明 6 个端点
- [x] `API/website/docs/__init__.py` 的 `_SERVICES` 已注册 `drama`
- [x] 访问 `/docs/drama/` 页面正常渲染，参数与说明齐全（实测 HTTP 200，6 个端点路径全部命中页面）
- [x] 文档页在线调试能拿到真实响应（实测 `POST /docs/_call/` 转发 `categories` 返回 `code=10000`；未注册路径被 404 拒绝，白名单生效）

## 回归测试

- [x] `scripts/api_smoke_config.json` 已追加短剧用例（正常 + 参数错误 + 第 4 集占位，共 14 条），JSON 合法
- [x] `python scripts/test_all_api.py` 中短剧用例按期望码通过（**通过 14 / 失败 0 / 跳过 0**）

## 范围守护

- [x] 未实现第 4 集及以后的取流（保持占位：爬虫返回 `need_app`、接口返回 `50002`）
- [x] 未引入 ttvid 映射 / fplay / 预热队列等属于后续 change 的内容（新增代码中检索 `ttvid|fplay|预热|warmup|prefetch|queue` 无匹配）
- [x] 未改动 `movie_555` 等既有服务的路由、契约与缓存配置（`git diff` 确认改动仅限本 change 涉及文件）

## 备注（不影响结论）

- `.env` 中尚未配置 `HONGGUO_*`，当前走默认值 1440 / 30 分钟；覆盖机制（`os.getenv`）本身已就位。
- 源站榜单实际存在第 4 个类型 `/rank/hot-comic-drama`（漫剧热播榜），本期按 spec 只开放 `hot-drama` / `hot-real-drama` / `hot-ai-drama` 三个，已在爬虫 `utils.py` 注释标注。
- 源站搜索不支持分页，`search` 如实返回单页（`pagination.total=1`）。
