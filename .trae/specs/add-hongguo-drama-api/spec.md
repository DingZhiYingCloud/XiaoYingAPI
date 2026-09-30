# 红果短剧 网页版 API 服务 Spec

## Why

小影 API 需要接入「红果短剧」内容。红果 App 的全量播放能力依赖字节 native 签名（已评估：unidbg 不可行），短期内无法拿到第 4 集及以后的播放地址；但**官网网页版**已可稳定获取全部剧集元数据、全量集号与前 3 集播放直链。

因此本期先把**网页版能做的部分全部做完并上线**，把 App 能力留成明确定义的占位（第 4 集起返回「开发中」），避免调用方拿到 404 无法区分。

## What Changes

- 新增短剧服务域 `API/apis/dramas/`（聚合形态），线路 `hongguo/`（红果短剧网页版）
- 新增爬虫线路 `SpiderServices/dramas/hongguo/`（`utils.py` + `cache.py` + `main.py`）
- `XiaoYingAPI/settings.py` 新增本线路独立的文件缓存项与两档 TTL
- 根路由 `API/apis/urls.py` 新增一行 `dramas/` 注册
- 文档中心新增 `API/website/docs/drama.py` 并注册
- 冒烟测试 `scripts/api_smoke_config.json` 追加短剧用例
- 第 4 集及以后：`play` 接口返回 `50002`「开发中」占位，**不实现**取流

## Impact

- Affected specs: 短剧内容服务（新增）；调用方「影视站」搭建流程
- Affected code:
  - `API/apis/dramas/`（新增）
  - `SpiderServices/dramas/hongguo/`（新增）
  - `API/apis/urls.py`、`XiaoYingAPI/settings.py`、`API/website/docs/__init__.py`、`scripts/api_smoke_config.json`（各追加少量内容）

## 已核实的官网能力（本 Spec 的事实基础）

| 能力 | 源站地址 | 实测结果 |
|------|----------|----------|
| 榜单 | `/rank/hot-drama`、`/rank/hot-real-drama`、`/rank/hot-ai-drama` | 200，每页 20 部 |
| 分类列表 | `/category/real-drama`（分类频道，站点共 34 页） | 200，每页 24 部 |
| 搜索 | `/search/{关键词}`（关键词在路径段） | 200，每页 10 部 |
| 详情 | `/detail?series_id={id}` | 200，SSR 含剧名/封面/简介/标签/集数/全量集号 `vid_list` |
| 播放（前 3 集） | `/player/{series_id}/{video_id}` | 200，SSR 含 `video_player_info.main_url` |
| 播放（第 4 集起） | 同上 | **404（服务端硬限制，前端无可绕过钩子）** |

> 官网页面为服务端渲染（SSR），数据以 JSON 形式内嵌在 HTML 中（`\u002F` 转义），无需浏览器渲染即可解析。

## ADDED Requirements

### Requirement: 短剧服务域与线路
系统 SHALL 提供 `/api/dramas/` 服务域，其下 `hongguo/` 线路对应红果短剧网页版，遵循《API 服务开发规范》三件套与统一响应契约。

#### Scenario: 服务可用
- **WHEN** 调用方以合规签名请求 `/api/dramas/hongguo/detail?series_id=7686894628578020414`
- **THEN** 返回 `{"code":10000,"msg":"成功","data":{...}}` 且 `data.series_id` 与请求一致

### Requirement: 榜单接口
系统 SHALL 提供 `GET /api/dramas/hongguo/rank`，按榜单类型与页码返回短剧列表。

#### Scenario: 拉取热播榜
- **WHEN** 请求 `rank?type=hot-drama&page=1`
- **THEN** 返回该页短剧列表，每条含 `series_id`、`name`、`cover`、`heat`（热度）、`rank`（名次）等字段

#### Scenario: 榜单类型非法
- **WHEN** 请求 `rank?type=unknown`
- **THEN** 返回 `20003 参数值非法`

### Requirement: 分类与列表接口
系统 SHALL 提供 `GET /api/dramas/hongguo/categories` 返回官网真实分类频道清单，并 SHALL 提供 `GET /api/dramas/hongguo/list` 按分类与页码返回列表。

#### Scenario: 获取分类清单
- **WHEN** 请求 `categories`
- **THEN** 返回 `data.categories`，每项含 `slug`、`name`，`slug` 可直接传给 `list` 接口

#### Scenario: 分类分页
- **WHEN** 请求 `list?category=real-drama&page=2`
- **THEN** 返回该分类第 2 页列表与分页信息

### Requirement: 搜索接口
系统 SHALL 提供 `GET /api/dramas/hongguo/search`，按关键词搜索短剧。

#### Scenario: 关键词搜索
- **WHEN** 请求 `search?keyword=保姆`
- **THEN** 返回匹配的短剧列表

#### Scenario: 缺少关键词
- **WHEN** 请求 `search` 未传 `keyword`
- **THEN** 返回 `20001 参数缺失`

### Requirement: 详情接口
系统 SHALL 提供 `GET /api/dramas/hongguo/detail`，返回剧集元数据与**完整集列表**，并对每集标注是否可播。

#### Scenario: 正常详情
- **WHEN** 请求 `detail?series_id=7686894628578020414`
- **THEN** 返回 `name`、`cover`、`intro`、`tags`、`episode_cnt`、`playable_cnt` 与 `episodes`；`episodes` 长度等于 `episode_cnt`，每项含 `ep`、`episode_id`、`playable`

#### Scenario: 可播集标注
- **WHEN** 查看 `episodes`
- **THEN** `ep <= 3` 的项 `playable=true`，`ep > 3` 的项 `playable=false`

#### Scenario: 剧集不存在
- **WHEN** 请求不存在的 `series_id`，或该剧在 SSR 数据中无对应条目
- **THEN** 返回 `40001`，`msg` 说明剧集不存在

### Requirement: 播放接口（前 3 集）
系统 SHALL 提供 `GET /api/dramas/hongguo/play`。当 `ep <= 3` 时返回可播放直链。

#### Scenario: 第 1~3 集取流
- **WHEN** 请求 `play?series_id=7686894628578020414&ep=2`
- **THEN** 返回 `code=10000`，`data` 含 `series_id`、`ep`、`episode_id`、`url`（CDN 直链）、`playable=true`

#### Scenario: 集号越界
- **WHEN** 请求的 `ep` 大于该剧总集数
- **THEN** 返回 `20003 参数值非法`

### Requirement: 播放接口（第 4 集起，占位）
系统 SHALL 在 `ep > 3` 时返回明确的「开发中」占位，而非 404 或假成功。

#### Scenario: 请求第 4 集
- **WHEN** 请求 `play?series_id=7686894628578020414&ep=4`
- **THEN** 返回 `code=50002`，`msg` 说明该集需要 App 能力、功能开发中，`data` 含 `series_id`、`ep`、`status="developing"`

#### Scenario: 占位不缓存为播放数据
- **WHEN** 同一请求重复调用
- **THEN** 行为稳定一致，且不写入播放地址缓存

### Requirement: 缓存
系统 SHALL 为红果线路提供独立缓存目录与两档 TTL：数据类（榜单/分类/列表/搜索/详情）与媒体类（播放直链）。

#### Scenario: 数据类缓存
- **WHEN** 重复请求同一详情
- **THEN** 命中缓存，不重复回源

#### Scenario: 缓存目录隔离
- **WHEN** 写入缓存
- **THEN** 落盘目录为 `cache/dramas/hongguo/`，与 `cache/movies/movie_555/` 互不影响

### Requirement: 文档接入
系统 SHALL 在站内文档中心提供「短剧」服务文档，可在线调试上述端点。

#### Scenario: 文档可见
- **WHEN** 访问 `/docs/` 并进入「短剧」
- **THEN** 可见 `hongguo` 线路的 6 个端点与参数说明，且可发起调试请求

### Requirement: 回归覆盖
系统 SHALL 在冒烟配置中覆盖短剧端点，含正常路径与参数错误分支。

#### Scenario: 冒烟执行
- **WHEN** 运行 `scripts/test_all_api.py`
- **THEN** 短剧用例出现在结果中，成功用例返回 `10000`，参数错误用例返回对应 `2xxxx`，第 4 集用例返回 `50002`

## REMOVED Requirements

无。

## 明确不在本期范围

| 项目 | 原因 | 处理 |
|------|------|------|
| 第 4 集及以后的取流 | 需 App 签名接口（native 签名，unidbg 已评估不可行） | 占位返回 `50002`，后续独立 change 处理 |
| `vid → ttvid` 映射采集 | 需云主机 + MuMu + Frida 预热器 | 后续独立 change |
| `fplay` 换流、直链时效刷新 | 依赖上一项的 ttvid | 后续独立 change |
| 多清晰度/多线路 | 官网播放页只提供单一 `main_url` | 以官网实际返回为准 |
| 短剧 App 端能力（登录态、收藏等） | 超出网页版范围 | 不做 |
