# 红果短剧 网页版 API 服务 Spec

> **本文件已按当前实现更新（2026-09-30）**，描述的是线路**现在**的对外契约。
>
> 最初版本只覆盖「前 3 集可播、第 4 集起返回 `50002` 占位」。此后第 4 集及以后分两步补齐，占位需求已被取代：
> ① **外部托管 + 链接登记**（人工上架，`play` 返回 `source=external`）；
> ② **本站「网页直出」**（按需解密 + 转 H.264，`play` 返回 `source=stream`，产物落盘复用）。
>
> 两处最容易出错的口径（`detail` 与 `play` 对同一集可用性必须一致、`playable_cnt` 保持原义）见下面「详情接口」小节。

## Why

小影 API 需要接入「红果短剧」内容。红果 App 的全量播放能力依赖字节 native 签名（已评估：unidbg 不可行），短期内无法拿到第 4 集及以后的播放地址；但**官网网页版**已可稳定获取全部剧集元数据、全量集号与前 3 集播放直链。

因此第一期先把**网页版能做的部分全部做完并上线**，把 App 能力留成明确定义的占位（第 4 集起返回「开发中」），避免调用方拿到 404 无法区分。**该占位已在后续两期被真实能力取代**（见上方说明）。

## What Changes

- 新增短剧服务域 `API/apis/dramas/`（聚合形态），线路 `hongguo/`（红果短剧网页版）
- 新增爬虫线路 `SpiderServices/dramas/hongguo/`（`utils.py` + `cache.py` + `main.py`）
- `XiaoYingAPI/settings.py` 新增本线路独立的文件缓存项与两档 TTL
- 根路由 `API/apis/urls.py` 新增一行 `dramas/` 注册
- 文档中心新增 `API/website/docs/drama.py` 并注册
- 冒烟测试 `scripts/api_smoke_config.json` 追加短剧用例
- **（第一期）** 第 4 集及以后：`play` 接口返回 `50002`「开发中」占位，**不实现**取流
- **（已补齐）** 第 4 集及以后由本服务补齐：① 已登记外部链接优先（`source=external`）；② 未登记则本站「网页直出」按需解密 + 转 H.264（`source=stream`，对应 `/api/dramas/hongguo/stream`）

## Impact

- Affected specs: 短剧内容服务（新增）；调用方「影视站」搭建流程
- Affected code:
  - `API/apis/dramas/`（新增）
  - `SpiderServices/dramas/hongguo/`（新增）
  - `API/apis/urls.py`、`XiaoYingAPI/settings.py`、`API/website/docs/__init__.py`、`scripts/api_smoke_config.json`（各追加少量内容）

## 已核实的官网能力（本 Spec 的事实基础）

| 能力 | 源站地址 | 实测结果 |
|------|----------|----------|
| 榜单 | `/rank/hot-drama`、`/rank/hot-real-drama`、`/rank/hot-ai-drama`、`/rank/hot-comic-drama` | 200，每页 20 部 |
| 分类（一级） | `/category/real-drama`、`/category/comic-drama`、`/category/ai-drama`、`/category/comic` | 200，每页 24 部 |
| 分类（二级题材） | `/category/real-drama/romance`（爱情）、`/category/real-drama/period`（年代）等 | 200，结构同一级，共 40 个（真人剧 24 / 漫剧 8 / AI剧 8 / 漫画 0） |
| 搜索 | `/search/{关键词}`（关键词在路径段） | 200，每页 10 部 |
| 详情 | `/detail?series_id={id}` | 200，SSR 含剧名/封面/简介/标签/集数/全量集号 `vid_list` |
| 播放（前 3 集） | `/player/{series_id}/{video_id}` | 200，SSR 含 `video_player_info.main_url` |
| 播放（第 4 集起） | 同上 | **404（服务端硬限制，前端无可绕过钩子）** → 源站只给 DRM 加密的 H.265，由本站「网页直出」补齐 |

> 官网页面为服务端渲染（SSR），数据以 JSON 形式内嵌在 HTML 中（`\u002F` 转义），无需浏览器渲染即可解析。

## ADDED Requirements

### Requirement: 短剧服务域与线路
系统 SHALL 提供 `/api/dramas/` 服务域，其下 `hongguo/` 线路对应红果短剧网页版，遵循《API 服务开发规范》三件套与统一响应契约。

#### Scenario: 服务可用
- **WHEN** 调用方以合规签名请求 `/api/dramas/hongguo/detail?series_id=7686894628578020414`
- **THEN** 返回 `{"code":10000,"msg":"成功","data":{...}}` 且 `data.series_id` 与请求一致

### Requirement: 榜单接口
系统 SHALL 提供 `GET /api/dramas/hongguo/rank`，按榜单类型与页码返回短剧列表；
榜单类型 SHALL 覆盖站点全部 4 种：`hot-drama`（热播榜）/ `hot-real-drama`（真人剧榜）/
`hot-ai-drama`（AI剧榜）/ `hot-comic-drama`（漫剧榜）。

#### Scenario: 拉取热播榜
- **WHEN** 请求 `rank?type=hot-drama&page=1`
- **THEN** 返回该页短剧列表，每条含 `series_id`、`name`、`cover`、`heat`（热度）、`rank`（名次）等字段，
  **且不包含页面头部面包屑等非榜单条目**（每条都必须有 `series_id` 与 `name`，`rank` 从 1 连续）

#### Scenario: 榜单类型非法
- **WHEN** 请求 `rank?type=unknown`
- **THEN** 返回 `20003 参数值非法`

### Requirement: 分类与列表接口
系统 SHALL 提供 `GET /api/dramas/hongguo/categories` 返回官网真实分类**树**，并 SHALL 提供
`GET /api/dramas/hongguo/list` 按分类与页码返回列表。

分类 SHALL 反映站点的**两级**结构：一级是内容形态（真人剧 / 漫剧 / AI剧 / 漫画），
二级是题材（爱情 / 年代 / 逆袭 …，共 40 个）。取值形式上，一级即其 slug（`real-drama`），
二级为「一级/二级」（`real-drama/romance`）。

#### Scenario: 获取分类清单
- **WHEN** 请求 `categories`
- **THEN** 返回 `data.categories`，每个一级项含 `slug`、`name`、`url` 与 `children`（二级项数组，
  每项同样含 `slug`、`name`、`url`）；无二级的一级（漫画）`children` 为空数组；
  每个节点的 `slug` 都可直接传给 `list` 接口

#### Scenario: 按一级分类分页
- **WHEN** 请求 `list?category=real-drama&page=2`
- **THEN** 返回该一级分类第 2 页列表与分页信息

#### Scenario: 按二级题材分页
- **WHEN** 请求 `list?category=real-drama/romance`
- **THEN** 返回「真人剧 · 爱情」的列表（题材确实生效：结果与一级不是同一批）

#### Scenario: 分类取值非法
- **WHEN** 请求 `list?category=real-drama/nope`
- **THEN** 返回 `20003 参数值非法`

### Requirement: 搜索接口
系统 SHALL 提供 `GET /api/dramas/hongguo/search`，按关键词搜索短剧。

#### Scenario: 关键词搜索
- **WHEN** 请求 `search?keyword=保姆`
- **THEN** 返回匹配的短剧列表

#### Scenario: 缺少关键词
- **WHEN** 请求 `search` 未传 `keyword`
- **THEN** 返回 `20001 参数缺失`

### Requirement: 详情接口
系统 SHALL 提供 `GET /api/dramas/hongguo/detail`，返回剧集元数据与**完整集列表**，并对每集标注**是否可播**与**可播来源**。

#### Scenario: 正常详情
- **WHEN** 请求 `detail?series_id=7686894628578020414`
- **THEN** 返回 `name`、`cover`、`intro`、`tags`、`episode_cnt`、`playable_cnt`、`listed_cnt`、`external_cnt` 与 `episodes`；`episodes` 长度等于 `episode_cnt`，每项含 `ep`、`episode_id`、`playable`（可播时另含 `source`）

#### Scenario: 可播集标注（与 play 口径一致）
- **WHEN** 查看 `episodes`
- **THEN** `playable` 与「播放地址」接口对同一集的结论**始终一致**：源站直链 / 已登记外链 / 本站网页直出三条路任一可用即为 `true`
- **AND** `source` 标出走的哪条路：`origin`（源站直链，前若干集）/ `external`（已登记外链）/ `stream`（本站直出）
- **AND** 本站直出默认可用，故第 4 集及以后的 `playable` 通常也为 `true`（不再是「前 3 集之外一律 false」）

#### Scenario: 三个计数的口径
- **WHEN** 读取计数
- **THEN** `playable_cnt` 为源站直链的**连续**范围（前 N 集，保持原义）；`listed_cnt` 为**实际可播集数**（= `playable` 为 true 的集数）；`external_cnt` 为**已登记外部链接**的集数
- **AND** 判断「某集能不能播」只可用 `episodes[].playable`，不得用 `playable_cnt` 推算

#### Scenario: 剧集不存在
- **WHEN** 请求不存在的 `series_id`，或该剧在 SSR 数据中无对应条目
- **THEN** 返回 `40001`，`msg` 说明剧集不存在

### Requirement: 播放接口（三条路择优）
系统 SHALL 提供 `GET /api/dramas/hongguo/play`，按 **① 源站直链 → ② 已登记外链 → ③ 本站网页直出** 的顺序返回可播地址，`data.source` 标出来源。

#### Scenario: 前若干集取流（源站直链）
- **WHEN** 请求 `play?series_id=7686894628578020414&ep=2`
- **THEN** 返回 `code=10000`，`data` 含 `series_id`、`ep`、`episode_id`、`url`（CDN 直链）、`playable=true`、`source=origin`

#### Scenario: 第 4 集及以后（已登记外链优先）
- **WHEN** 请求 `play?...&ep=4`，且该集已登记外部播放地址
- **THEN** 返回 `code=10000`，`data.source=external`，`data.url` 为第三方地址，`data.url_type` 为 `mp4` / `m3u8`

#### Scenario: 第 4 集及以后（本站直出兜底）
- **WHEN** 请求 `play?...&ep=4`，该集未登记外部地址，且本站直出可用
- **THEN** 返回 `code=10000`，`data.source=stream`，`data.url` 为带**时效令牌**的出流地址（默认 2 小时），`data.quality` 为出流画质，`data.ready=false` 表示该画质首次被点播、服务端正在生成

#### Scenario: 集号越界
- **WHEN** 请求的 `ep` 大于该剧总集数
- **THEN** 返回 `20003 参数值非法`

#### Scenario: 直出也不可用时（兜底）
- **WHEN** 该集既未登记外链，本站直出又不可用（未配置出流目录）
- **THEN** 返回 `50002`，`msg` 给出「该集暂未上架」的说明

### Requirement: 网页直出流端点
系统 SHALL 提供 `GET|HEAD /api/dramas/hongguo/stream`，把本站转码产物以明文 H.264 出流，供 `<video>` 直接播放。

#### Scenario: 首次点播该画质
- **WHEN** 带有效令牌请求某集某画质，且产物尚未生成
- **THEN** 返回 `202` 且带 `Retry-After: 3`，服务端在后台取流 → CENC 解密 → 转 H.264 → 落盘；调用方轮询该地址

#### Scenario: 产物就绪后出流
- **WHEN** 再次请求（产物已在）
- **THEN** 返回 `200`；带 `Range` 头时返回 `206` + `Content-Range`，支持拖动进度条与断点续传；产物按 `{HONGGUO_STREAM_DIR}/{series_id}/{画质宽度}/001.mp4` 永久复用

#### Scenario: 令牌鉴权
- **WHEN** 令牌缺失、被篡改或超过有效期（默认 2 小时）
- **THEN** 返回 `403`，需重新调用「播放地址」接口换取新地址（该端点免项目签名，`<video>` 带不了签名）

### Requirement: 外部链接登记（仅后台内部使用）
系统 SHALL 允许超级管理员把「预处理导出的地址」批量登记到某集，登记后 `play` 优先返回该外链、`detail` 的 `source` 变为 `external`。

#### Scenario: 批量登记
- **WHEN** 在超管控制台按「集号 + 分隔符 + 链接」批量粘贴提交
- **THEN** 按 `series_id + ep` 幂等 upsert；任一行非法则整批不落库
- **AND** 登记**不提供对外接口**，仅后台内部使用

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
- **THEN** 可见 `hongguo` 线路的 7 个端点（`rank` / `categories` / `list` / `search` / `detail` / `play` / `stream`）与参数说明，且可发起调试请求

### Requirement: 回归覆盖
系统 SHALL 用回归脚本守住「`detail` 与 `play` 口径一致」这条契约，并覆盖参数错误分支。

#### Scenario: 口径一致回归
- **WHEN** 运行 `scripts/test_hongguo_drama.py`
- **THEN** 逐条校验：`episodes[].playable` / `source` 与 `play` 的结论一致；`playable_cnt` 保持原义；`listed_cnt` / `external_cnt` 随登记行增减正确变化；登记与删除后不清缓存也能立即反映；爬虫层原始结果不被就地修改

#### Scenario: 冒烟执行
- **WHEN** 运行 `scripts/test_all_api.py`
- **THEN** 短剧用例出现在结果中，成功用例返回 `10000`，参数错误用例返回对应 `2xxxx`

## REMOVED Requirements

- **播放接口（第 4 集起，占位）**：原「`ep > 3` 返回 `50002` 开发中占位」已被真实能力取代，见「播放接口（三条路择优）」与「网页直出流端点」。保留此条仅为追溯：**接口不再存在 `status="developing"` 这类占位返回**。

## 明确不在本期范围

| 项目 | 原因 | 处理 |
|------|------|------|
| ~~第 4 集及以后的取流~~ | **已补齐** | ① 已登记外链优先；② 未登记则本站「网页直出」（按需解密 + 转 H.264，产物落盘复用） |
| `vid → ttvid` 映射采集 | 需云主机 + MuMu + Frida 预热器 | 后续独立 change（直出已用另一种方式拿到流，不再是阻塞项） |
| `fplay` 换流、直链时效刷新 | 依赖上一项的 ttvid | 后续独立 change |
| 多清晰度/多线路 | 官网播放页只提供单一 `main_url` | 出流侧改为按宽度分档（`1080 / 720 / 540 / 480 / 360`），见 `QUALITY_WIDTHS` |
| 短剧 App 端能力（登录态、收藏等） | 超出网页版范围 | 不做 |
