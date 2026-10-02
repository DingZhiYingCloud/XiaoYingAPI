"""短剧服务 - 接口文档与在线调试数据

数据与 API/apis/dramas/ 实际实现对齐（服务策略 /api/dramas/ 默认需签名）：
- hongguo  红果短剧网页版线路（实时爬取源站 SSR 数据 + 文件缓存；
  超出源站明链范围的集数由服务端走 App 内部接口取流并解密）

接入方拿到授权后，可按「榜单/分类 → 列表 → 详情 → 播放」跑通短剧站流程。
后续接入更多线路（如其它短剧平台）时在 channels 追加即可。
"""
from API.apis.dramas.hongguo.utils import CATEGORY_OPTIONS, DEFAULT_QUALITY, QUALITY_WIDTHS

from .schema import ChannelSpec, EndpointSpec, ParamSpec, ResponseFieldSpec, ServiceSpec

# 出流画质档位直接取后端白名单，避免「文档里能选、接口却报参数非法」——
# 真实可选值只有一个来源（API/apis/dramas/hongguo/utils.py 的 QUALITY_WIDTHS）。
# 画质下拉选项：值是输出宽度上限（短剧是竖屏，1080 即 1080×1920，也就是日常说的 1080p）
_QUALITY_EXTRA_LABEL = {1080: '（源站最高，推荐）'}
_QUALITY_OPTIONS = [
    {'value': str(w), 'label': f'{w}p{_QUALITY_EXTRA_LABEL.get(w, "")}'}
    for w in QUALITY_WIDTHS
]

# 分类下拉选项同理取后端分类树（4 个一级 + 40 个二级题材），不在这里另抄一份 ——
# 站点加题材时只改爬虫 utils.py 的 CATEGORIES，文档页自动跟上。
_CATEGORY_OPTIONS = [{'value': value, 'label': label} for value, label in CATEGORY_OPTIONS]

SERVICE = ServiceSpec(
    slug='drama',
    name='短剧',
    prefix='/api/dramas/',
    summary='短剧服务：提供短剧的榜单、分类、搜索、详情与播放直链能力，'
            '按「榜单/分类 → 列表 → 详情 → 播放」流程即可搭建短剧站。',
    keywords='短剧API,短剧接口,免费短剧API,红果短剧接口,短剧播放直链,短剧搜索接口',
    intro=[
        '短剧服务聚合短剧站数据，提供榜单、分类、搜索、详情与播放直链等能力，'
        '按「榜单/分类 → 列表 → 详情 → 播放」的顺序即可搭起一个短剧站，'
        '搜索接口则支持按剧名关键词查剧。',
        '播放能力：前 3 集由源站直接下发明文直链；第 4 集及以后源站只下发 DRM 加密的'
        'H.265（浏览器无法直接解码），由本服务在服务端解密并转成 H.264 后出流，'
        '播放接口返回的地址可直接交给浏览器的「视频」标签播放，支持拖动进度条。'
        '第 4 集及以后首次点播需等待数十秒生成，之后即刻返回。',
        '播放接口返回的源站直链为 MP4 且带时效，请勿在客户端长期缓存；'
        '剧集元数据与集列表缓存较久，播放直链缓存较短以便及时刷新。本服务需项目签名。',
    ],
    channels=[
        ChannelSpec(
            slug='hongguo',
            name='红果短剧',
            provider='红果短剧（hongguoduanju.com）网页版',
            auth_note='auth',
            note='实时爬取源站 SSR 数据并缓存。剧集元数据/集列表缓存较久；播放直链缓存较短。',
            endpoints=[
                EndpointSpec('rank', '榜单', 'GET',
                             '/api/dramas/hongguo/rank',
                             summary='获取短剧榜单，支持热播榜 / 真人剧热播榜 / AI剧热播榜 / '
                                     '漫剧热播榜与分页。',
                             params=[
                                 ParamSpec('type', '榜单类型', kind='select',
                                           default='hot-drama',
                                           options=[
                                               {'value': 'hot-drama', 'label': '热播榜'},
                                               {'value': 'hot-real-drama', 'label': '真人剧热播榜'},
                                               {'value': 'hot-ai-drama', 'label': 'AI剧热播榜'},
                                               {'value': 'hot-comic-drama', 'label': '漫剧热播榜'},
                                           ],
                                           desc='可选：榜单类型，默认 hot-drama（热播榜）。'),
                                 ParamSpec('page', '页码', kind='number', default='1',
                                           placeholder='1',
                                           desc='可选：页码，从 1 开始，默认 1。'),
                             ],
                             notes=['榜单类型非法时返回 PARAM_VALUE_INVALID。',
                                    '返回 data 为榜单剧集列表（字段与「分类列表」接口一致）。'],
                             response_fields=[
                                 ResponseFieldSpec('type', 'string', '榜单类型（回带入参）'),
                                 ResponseFieldSpec('page', 'int', '当前页码'),
                                 ResponseFieldSpec('total_page', 'int', '总页数'),
                                 ResponseFieldSpec('results', 'array', '榜单剧集列表'),
                                 ResponseFieldSpec('results[].rank', 'int', '排名'),
                                 ResponseFieldSpec('results[].series_id', 'string', '剧集 ID（传给详情/播放接口）'),
                                 ResponseFieldSpec('results[].name', 'string', '剧名'),
                                 ResponseFieldSpec('results[].cover', 'string', '封面图地址'),
                                 ResponseFieldSpec('results[].url', 'string', '详情页地址'),
                                 ResponseFieldSpec('results[].heat', 'string', '热度（无则 null）'),
                                 ResponseFieldSpec('results[].score', 'string', '评分（无则 null）'),
                                 ResponseFieldSpec('results[].favorite', 'string', '收藏数（无则 null）'),
                                 ResponseFieldSpec('results[].like', 'string', '点赞数（无则 null）'),
                                 ResponseFieldSpec('results[].tags', 'array', '题材标签'),
                                 ResponseFieldSpec('results[].intro', 'string', '剧情简介'),
                             ],
                             response_example="""{
  "type": "hot-drama",
  "page": 1,
  "total_page": 3,
  "results": [
    {"rank": 1, "series_id": "7686894628578020414", "name": "示例短剧", "cover": "https://img.example.com/1.jpg", "url": "https://www.hongguoduanju.com/detail/7686894628578020414", "heat": "1234", "score": "9.2", "favorite": "120", "like": "56", "tags": ["逆袭", "甜宠"], "intro": ""}
  ]
}"""),
                EndpointSpec('categories', '分类清单', 'GET',
                             '/api/dramas/hongguo/categories',
                             summary='获取分类树（一级 -> 二级题材）。',
                             notes=['分类是两级的：一级是内容形态（真人剧 / 漫剧 / AI剧 / 漫画），'
                                    '二级是题材（爱情 / 年代 / 逆袭 …）。',
                                    '每个节点的 slug 都可直接传给「分类列表」接口的 category：'
                                    '一级取该一级全部，二级只取该题材（形如 real-drama/romance）；'
                                    '无二级的一级（漫画）children 为空数组。'],
                             response_fields=[
                                 ResponseFieldSpec('categories', 'array', '分类树（一级）'),
                                 ResponseFieldSpec('categories[].slug', 'string', '一级分类标识（传给列表接口 category）'),
                                 ResponseFieldSpec('categories[].name', 'string', '一级分类名称'),
                                 ResponseFieldSpec('categories[].url', 'string', '分类页地址'),
                                 ResponseFieldSpec('categories[].children', 'array', '二级题材（无则为空数组）'),
                                 ResponseFieldSpec('categories[].children[].slug', 'string', '二级标识（一级/二级形式）'),
                                 ResponseFieldSpec('categories[].children[].name', 'string', '二级题材名称'),
                                 ResponseFieldSpec('categories[].children[].url', 'string', '分类页地址'),
                             ],
                             response_example="""{
  "categories": [
    {"slug": "real-drama", "name": "真人剧", "url": "https://www.hongguoduanju.com/category/real-drama", "children": [
      {"slug": "real-drama/romance", "name": "爱情", "url": "https://www.hongguoduanju.com/category/real-drama/romance"}
    ]}
  ]
}"""),
                EndpointSpec('list', '分类列表', 'GET',
                             '/api/dramas/hongguo/list',
                             summary='按分类获取短剧列表，支持分页。',
                             params=[
                                 ParamSpec('category', '分类', kind='select', required=True,
                                           options=_CATEGORY_OPTIONS,
                                           desc='必填：分类取值 —— 一级 slug（如 real-drama）'
                                                '或「一级/二级」（如 real-drama/romance），'
                                                '完整取值见「分类清单」接口。'),
                                 ParamSpec('page', '页码', kind='number', default='1',
                                           placeholder='1',
                                           desc='可选：页码，从 1 开始，默认 1。'),
                             ],
                             notes=['category 缺失或非法时返回 PARAM_MISSING / PARAM_VALUE_INVALID。'],
                             response_fields=[
                                 ResponseFieldSpec('category', 'string', '分类标识（回带入参）'),
                                 ResponseFieldSpec('page', 'int', '当前页码'),
                                 ResponseFieldSpec('results', 'array', '短剧列表'),
                                 ResponseFieldSpec('results[].series_id', 'string', '剧集 ID（传给详情/播放接口）'),
                                 ResponseFieldSpec('results[].name', 'string', '剧名'),
                                 ResponseFieldSpec('results[].cover', 'string', '封面图地址'),
                                 ResponseFieldSpec('results[].url', 'string', '详情页地址'),
                                 ResponseFieldSpec('results[].tags', 'array', '题材标签'),
                                 ResponseFieldSpec('results[].intro', 'string', '剧情简介'),
                                 ResponseFieldSpec('results[].rank', 'null', '榜单专有字段，列表接口恒为 null'),
                                 ResponseFieldSpec('results[].heat', 'null', '榜单专有字段，列表接口恒为 null'),
                                 ResponseFieldSpec('results[].score', 'null', '榜单专有字段，列表接口恒为 null'),
                                 ResponseFieldSpec('results[].favorite', 'null', '榜单专有字段，列表接口恒为 null'),
                                 ResponseFieldSpec('results[].like', 'null', '榜单专有字段，列表接口恒为 null'),
                                 ResponseFieldSpec('pagination', 'object', '分页信息'),
                                 ResponseFieldSpec('pagination.current', 'int', '当前页码'),
                                 ResponseFieldSpec('pagination.total', 'int', '总页数'),
                             ],
                             response_example="""{
  "category": "real-drama",
  "page": 1,
  "results": [
    {"series_id": "7686894628578020414", "name": "示例短剧", "cover": "https://img.example.com/1.jpg", "url": "https://www.hongguoduanju.com/detail/7686894628578020414", "tags": ["逆袭"], "intro": "", "rank": null, "heat": null, "score": null, "favorite": null, "like": null}
  ],
  "pagination": {"current": 1, "total": 2}
}"""),
                EndpointSpec('search', '搜索', 'GET',
                             '/api/dramas/hongguo/search',
                             summary='按关键词搜索短剧。',
                             params=[
                                 ParamSpec('keyword', '搜索关键词', required=True,
                                           placeholder='短剧名',
                                           desc='必填：搜索关键词（剧名）。'),
                                 ParamSpec('page', '页码', kind='number', default='1',
                                           placeholder='1',
                                           desc='可选：页码，从 1 开始，默认 1。'),
                             ],
                             notes=['源站搜索不支持分页，恒返回单页（page 传入也仅返回同一批结果）。'],
                             response_fields=[
                                 ResponseFieldSpec('keyword', 'string', '搜索关键词（回带入参）'),
                                 ResponseFieldSpec('page', 'int', '当前页码'),
                                 ResponseFieldSpec('results', 'array', '搜索结果列表'),
                                 ResponseFieldSpec('results[].series_id', 'string', '剧集 ID（传给详情/播放接口）'),
                                 ResponseFieldSpec('results[].name', 'string', '剧名'),
                                 ResponseFieldSpec('results[].cover', 'string', '封面图地址'),
                                 ResponseFieldSpec('results[].url', 'string', '详情页地址'),
                                 ResponseFieldSpec('results[].tags', 'array', '题材标签'),
                                 ResponseFieldSpec('results[].intro', 'string', '剧情简介'),
                                 ResponseFieldSpec('results[].rank', 'null', '榜单专有字段，列表接口恒为 null'),
                                 ResponseFieldSpec('results[].heat', 'null', '榜单专有字段，列表接口恒为 null'),
                                 ResponseFieldSpec('results[].score', 'null', '榜单专有字段，列表接口恒为 null'),
                                 ResponseFieldSpec('results[].favorite', 'null', '榜单专有字段，列表接口恒为 null'),
                                 ResponseFieldSpec('results[].like', 'null', '榜单专有字段，列表接口恒为 null'),
                                 ResponseFieldSpec('pagination', 'object', '分页信息'),
                                 ResponseFieldSpec('pagination.current', 'int', '当前页码'),
                                 ResponseFieldSpec('pagination.total', 'int', '总页数（搜索恒为 1）'),
                             ],
                             response_example="""{
  "keyword": "短剧",
  "page": 1,
  "results": [
    {"series_id": "7686894628578020414", "name": "示例短剧", "cover": "https://img.example.com/1.jpg", "url": "https://www.hongguoduanju.com/detail/7686894628578020414", "tags": ["逆袭"], "intro": "", "rank": null, "heat": null, "score": null, "favorite": null, "like": null}
  ],
  "pagination": {"current": 1, "total": 1}
}"""),
                EndpointSpec('detail', '剧集详情', 'GET',
                             '/api/dramas/hongguo/detail',
                             summary='获取剧集详情与全量集列表。',
                             params=[
                                 ParamSpec('series_id', '剧集 ID', required=True,
                                           placeholder='7686894628578020414',
                                           desc='必填：剧集 ID（取自列表/搜索结果）。'),
                             ],
                             notes=['返回 data.episodes 为全量集列表，每项含 ep / episode_id / playable / source。',
                                    'episodes[].playable 的口径与「播放地址」接口**完全一致**：'
                                    '源站直链 / 本站网页直出两条路任一可用即为 true；'
                                    'source 标出走的哪条路 —— origin（源站直链）'
                                    '/ stream（本站直出，首播需等数十秒生成）。本站直出默认可用，'
                                    '所以第 4 集及以后通常也是 playable=true。',
                                    'data.playable_cnt 为源站直链的连续范围（前 N 集，保持原义）；'
                                    'data.listed_cnt 为实际可播集数（= playable 为 true 的集数）。'
                                    '需要判断「某集能不能播」请用 episodes[].playable，不要用 playable_cnt 推算。',
                                    '剧集不存在时返回 EXTERNAL_API_FAILED（外部API调用失败）。'],
                             response_fields=[
                                 ResponseFieldSpec('series_id', 'string', '剧集 ID（回带入参）'),
                                 ResponseFieldSpec('name', 'string', '剧名'),
                                 ResponseFieldSpec('cover', 'string', '封面图地址'),
                                 ResponseFieldSpec('intro', 'string', '剧情简介'),
                                 ResponseFieldSpec('tags', 'array', '题材标签'),
                                 ResponseFieldSpec('episode_cnt', 'int', '总集数'),
                                 ResponseFieldSpec('playable_cnt', 'int', '源站直链的连续可播集数'),
                                 ResponseFieldSpec('listed_cnt', 'int', '实际可播集数（playable=true 的集数）'),
                                 ResponseFieldSpec('episodes', 'array', '全量集列表'),
                                 ResponseFieldSpec('episodes[].ep', 'int', '集号（从 1 开始）'),
                                 ResponseFieldSpec('episodes[].episode_id', 'string', '源站集 ID'),
                                 ResponseFieldSpec('episodes[].playable', 'bool', '该集是否可播'),
                                 ResponseFieldSpec('episodes[].source', 'string', '来源：origin 源站直链 / stream 本站直出'),
                             ],
                             response_example="""{
  "series_id": "7686894628578020414",
  "name": "示例短剧",
  "cover": "https://img.example.com/1.jpg",
  "intro": "",
  "tags": ["逆袭"],
  "episode_cnt": 60,
  "playable_cnt": 3,
  "listed_cnt": 60,
  "episodes": [
    {"ep": 1, "episode_id": "123", "playable": true, "source": "origin"},
    {"ep": 4, "episode_id": "456", "playable": true, "source": "stream"}
  ]
}"""),
                EndpointSpec('play', '播放地址', 'GET',
                             '/api/dramas/hongguo/play',
                             summary='获取指定集的播放地址（网页可直接播放）。',
                             params=[
                                 ParamSpec('series_id', '剧集 ID', required=True,
                                           placeholder='7686894628578020414'),
                                 ParamSpec('ep', '集数', kind='number', required=True,
                                           placeholder='1',
                                           desc='必填：集数，从 1 开始。'),
                                 ParamSpec('q', '画质', kind='select', default=str(DEFAULT_QUALITY),
                                           options=_QUALITY_OPTIONS,
                                           desc='选填：本站直出的画质，取值是输出宽度上限'
                                                '（短剧是竖屏，1080 即 1080×1920，也就是日常说的 1080p）。'
                                                '每档产物各存一份；换画质要重新调本接口换地址。'),
                             ],
                             notes=['前 3 集返回源站明文 MP4 直链；第 4 集及以后源站只下发 DRM 加密的'
                                    ' H.265（浏览器无法解码），改由本站出流。data.source 区分来源'
                                    '（取值与「剧集详情」的 episodes[].source 一致）：',
                                    '· origin —— 源站明文直链（前若干集）；',
                                    '· stream —— 本站直出：data.url 为可直接交给 <video> 播放的地址'
                                    '（明文 H.264、支持 HTTP Range 拖动），画质见 data.quality，'
                                    'data.ready=false 表示该画质首次被点播、服务端正在生成（约数十秒），'
                                    '请轮询该地址：202=正在生成、503=生成失败（响应体里有原因）、'
                                    '200/206=可播放，别只按 HTTP 200 判定。',
                                    '该地址的鉴权由 data.url 里的时效令牌承担（默认 2 小时），'
                                    '过期后重新调用本接口换取新地址。',
                                    'ep 越界（超出总集数）返回 PARAM_VALUE_INVALID。',
                                    '源站直链带时效，请勿长期缓存。'],
                             player=True,
                             response_fields=[
                                 ResponseFieldSpec('series_id', 'string', '剧集 ID（回带入参）'),
                                 ResponseFieldSpec('ep', 'int', '集号（回带入参）'),
                                 ResponseFieldSpec('playable', 'bool', '是否可播（成功恒为 true）'),
                                 ResponseFieldSpec('source', 'string', '来源：origin 源站直链 / stream 本站直出'),
                                 ResponseFieldSpec('url', 'string', '播放地址（带时效）'),
                                 ResponseFieldSpec('url_type', 'string', '仅 source=stream：地址类型（mp4）'),
                                 ResponseFieldSpec('quality', 'int', '仅 source=stream：出流画质（宽度上限）'),
                                 ResponseFieldSpec('ready', 'bool', '仅 source=stream：产物是否已生成（false 需轮询）'),
                                 ResponseFieldSpec('episode_id', 'string', '仅 source=origin：源站集 ID'),
                                 ResponseFieldSpec('duration', 'int', '仅 source=origin：时长'),
                                 ResponseFieldSpec('width', 'int', '仅 source=origin：视频宽'),
                                 ResponseFieldSpec('height', 'int', '仅 source=origin：视频高'),
                                 ResponseFieldSpec('poster', 'string', '仅 source=origin：封面图地址'),
                             ],
                             response_example="""{
  "series_id": "7686894628578020414",
  "ep": 1,
  "episode_id": "123",
  "playable": true,
  "url": "https://www.hongguoduanju.com/xxx.mp4",
  "duration": 90000,
  "width": 720,
  "height": 1280,
  "poster": "https://img.example.com/1.jpg",
  "source": "origin"
}"""),
                EndpointSpec('stream', '网页直出流', 'GET',
                             '/api/dramas/hongguo/stream',
                             summary='第 4 集及以后的「网页可播」流地址（普通 <video> 标签直接播放）。',
                             params=[
                                 ParamSpec('token', '播放令牌', required=True,
                                           placeholder='由「播放地址」接口的 data.url 携带',
                                           desc='必填：由「播放地址」接口下发的时效令牌，无需项目签名。'),
                             ],
                             notes=['该地址由「播放地址」接口返回，供 <video> 标签直接播放，'
                                    '不带项目签名（浏览器加不了签名），鉴权用 URL 里的时效令牌。',
                                    '画质由「播放地址」的 q 参数决定、已写在令牌里，本端点不需要再传 —— '
                                    '同一集不同画质是不同的地址，各自独立缓存。',
                                    '支持 HTTP Range（206）：可拖动进度条、可断点续传。',
                                    '首次点播该集的某一画质时返回 202（Retry-After: 3），服务端在后台'
                                    '解密并转成 H.264（约数十秒），200 / 206 才是可播放；'
                                    '生成失败返回 503（响应体里有失败原因），请勿只按 HTTP 200 判定。'
                                    '产物落盘永久复用，此后再播为即刻返回。',
                                    '令牌无效或过期返回 403，需重新调用「播放地址」接口获取新地址。'],
                             response_note='成功返回视频二进制流（video/mp4，支持 Range）；'
                                           '生成中返回 202、生成失败 503、令牌无效或过期 403，均非统一 JSON 信封。'),
            ],
        ),
    ],
)
