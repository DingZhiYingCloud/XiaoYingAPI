"""电影服务 - 接口文档与在线调试数据

数据与 API/apis/movies/ 实际实现对齐（服务策略 /api/movies/ 默认需签名）：
- movie_555  555电影线路（苹果CMS 站，实时爬取 + 文件缓存）

接入方拿到授权后，可按「分类列表 → 筛选条件 → 列表 → 详情 → 播放地址」跑通完整影视站流程。
后续接入更多线路（如爱奇艺 / 腾讯等）时在 channels 追加即可。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ResponseFieldSpec, ServiceSpec

SERVICE = ServiceSpec(
    slug='movie',
    name='电影',
    prefix='/api/movies/',
    summary='电影聚合服务：提供影视的分类、列表、详情、选集与播放地址（m3u8）能力，'
            '按「列表 → 详情 → 播放」流程即可搭建完整影视站。',
    keywords='电影API,影视API接口,免费电影接口,m3u8播放地址,影视解析API,影片搜索接口',
    intro=[
        '电影服务聚合影视站数据，提供分类、筛选条件、首页推荐、列表、详情、选集与播放地址（m3u8）等'
        '完整链路，按「分类 → 列表 → 详情 → 播放地址」的顺序即可搭起一个影视站，'
        '搜索接口则支持按片名关键词查片。',
        '关键 ID 有固定的传递顺序：分类接口返回的 id 传给列表接口的 type_id，列表中的 id 传给详情接口的 vod_id，'
        '详情中的 sid / nid 再传给播放接口取地址，串起来就是一条完整的播放流程。',
        '数据类信息（片名、简介、集数等）缓存时间较长；播放地址（m3u8）因为带时效只做较短缓存，'
        '请勿在客户端长期缓存播放地址。本服务需项目签名。',
    ],
    channels=[
        ChannelSpec(
            slug='movie_555',
            name='555电影',
            provider='555电影（5dy4.vip）',
            auth_note='auth',
            note='实时爬取源站并缓存。数据类（片名/详情/集数）缓存较久，'
                 '播放地址（m3u8）缓存较短以便及时刷新。',
            endpoints=[
                EndpointSpec('categories', '分类列表', 'GET',
                             '/api/movies/movie_555/categories',
                             summary='获取可用分类（主分类 / 子分类 / 专题）。',
                             notes=['用于搭建站点导航：main 为主分类，sub 为连续剧的子分类，'
                                    '返回的 id 都可直接传给「列表」接口的 type_id。'],
                             response_fields=[
                                 ResponseFieldSpec('main', 'array', '主分类列表'),
                                 ResponseFieldSpec('main[].id', 'int', '分类 ID，传给列表接口 type_id'),
                                 ResponseFieldSpec('main[].name', 'string', '分类名称'),
                                 ResponseFieldSpec('sub', 'array', '连续剧的子分类列表'),
                                 ResponseFieldSpec('sub[].id', 'int', '子分类 ID，同样可传 type_id'),
                                 ResponseFieldSpec('sub[].name', 'string', '子分类名称'),
                                 ResponseFieldSpec('labels', 'array', '首页专题（label）列表'),
                                 ResponseFieldSpec('labels[].key', 'string', '专题标识'),
                                 ResponseFieldSpec('labels[].name', 'string', '专题名称'),
                             ],
                             response_example="""{
  "main": [
    {"id": 1, "name": "电影"},
    {"id": 2, "name": "连续剧"}
  ],
  "sub": [
    {"id": 13, "name": "热门连续剧"}
  ],
  "labels": [
    {"key": "netflix", "name": "Netflix 专区"}
  ]
}"""),
                EndpointSpec('filters', '筛选条件', 'GET',
                             '/api/movies/movie_555/filters',
                             summary='获取某分类可用的筛选条件：子分类、地区、题材、语言、年份、排序。',
                             params=[
                                 ParamSpec('type_id', '分类 ID', kind='number', required=True,
                                           placeholder='1',
                                           desc='必填：分类 ID（见「分类列表」接口），如 1=电影 2=连续剧。'),
                             ],
                             notes=['返回 data.sub_types（子分类，value 回传给 type_id）与 data.groups。',
                                    'data.groups 含地区 / 题材 / 语言 / 年份 / 排序五组，value 回传给「列表」接口的同名参数。',
                                    '各分类的可用值不同（例如动漫有「日本 / 欧美」，综艺有「真人秀 / 脱口秀」），'
                                    '年份还会随站点上新自动增加，建议由本接口动态渲染筛选栏，不要在客户端写死。'],
                             response_fields=[
                                 ResponseFieldSpec('type_id', 'int', '分类 ID（回带入参）'),
                                 ResponseFieldSpec('sub_types', 'array', '该分类的子分类'),
                                 ResponseFieldSpec('sub_types[].name', 'string', '子分类名称'),
                                 ResponseFieldSpec('sub_types[].value', 'string', '值，回传给列表接口 type_id'),
                                 ResponseFieldSpec('groups', 'array', '筛选条件分组（地区/题材/语言/年份/排序）'),
                                 ResponseFieldSpec('groups[].key', 'string', '参数名（area/genre/lang/year/order）'),
                                 ResponseFieldSpec('groups[].name', 'string', '分组名称'),
                                 ResponseFieldSpec('groups[].options', 'array', '该组的可选值'),
                                 ResponseFieldSpec('groups[].options[].name', 'string', '选项名称'),
                                 ResponseFieldSpec('groups[].options[].value', 'string', '选项值，回传给同名参数'),
                             ],
                             response_example="""{
  "type_id": 1,
  "sub_types": [{"name": "动作片", "value": "6"}],
  "groups": [
    {"key": "area", "name": "地区", "options": [{"name": "大陆", "value": "大陆"}]}
  ]
}"""),
                EndpointSpec('home', '首页聚合', 'GET',
                             '/api/movies/movie_555/home',
                             summary='获取首页聚合数据：轮播图与各推荐区块（本周/本月最佳、各榜单等）。',
                             notes=['一次返回首页全部推荐区块，便于直接渲染站点首页。'],
                             response_fields=[
                                 ResponseFieldSpec('carousel', 'array', '轮播图'),
                                 ResponseFieldSpec('carousel[].id', 'string', '影片 ID'),
                                 ResponseFieldSpec('carousel[].name', 'string', '片名'),
                                 ResponseFieldSpec('carousel[].url', 'string', '详情页地址'),
                                 ResponseFieldSpec('carousel[].cover', 'string', '封面图地址'),
                                 ResponseFieldSpec('carousel[].note', 'string', '角标/备注'),
                                 ResponseFieldSpec('carousel[].intro', 'string', '一句话简介'),
                                 ResponseFieldSpec('blocks', 'array', '推荐区块列表'),
                                 ResponseFieldSpec('blocks[].title', 'string', '区块标题'),
                                 ResponseFieldSpec('blocks[].items', 'array', '区块内影片'),
                                 ResponseFieldSpec('blocks[].items[].id', 'string', '影片 ID'),
                                 ResponseFieldSpec('blocks[].items[].name', 'string', '片名'),
                                 ResponseFieldSpec('blocks[].items[].url', 'string', '详情页地址'),
                                 ResponseFieldSpec('blocks[].items[].cover', 'string', '封面图地址'),
                                 ResponseFieldSpec('blocks[].items[].note', 'string', '角标/备注'),
                                 ResponseFieldSpec('blocks[].items[].douban', 'string', '豆瓣评分'),
                             ],
                             response_example="""{
  "carousel": [
    {"id": "812640", "name": "示例影片", "url": "https://5dy4.vip/voddetail/812640.html", "cover": "https://img.example.com/812640.jpg", "note": "", "intro": ""}
  ],
  "blocks": [
    {"title": "本周最佳", "items": [
      {"id": "812640", "name": "示例影片", "url": "https://5dy4.vip/voddetail/812640.html", "cover": "https://img.example.com/812640.jpg", "note": "", "douban": "8.0"}
    ]}
  ]
}"""),
                EndpointSpec('list', '分类列表', 'GET',
                             '/api/movies/movie_555/list',
                             summary='按分类获取影片列表，支持分页、排序与年份 / 地区 / 题材 / 语言组合筛选。',
                             params=[
                                 ParamSpec('type_id', '分类 ID', kind='number', required=True,
                                           placeholder='1',
                                           desc='必填：分类 ID，1=电影 2=连续剧 3=综艺纪录 4=动漫 124=福利 126=擦边短剧（子分类见「分类列表」接口的 sub）。'),
                                 ParamSpec('page', '页码', kind='number', default='1',
                                           placeholder='1',
                                           desc='可选：页码，从 1 开始，默认 1。'),
                                 ParamSpec('order', '排序方式', kind='select',
                                           options=[
                                               {'value': '', 'label': '默认'},
                                               {'value': 'time', 'label': '按时间'},
                                               {'value': 'hits', 'label': '按人气'},
                                               {'value': 'score', 'label': '按评分'},
                                           ],
                                           desc='可选：排序方式 time/hits/score。'),
                                 ParamSpec('year', '年份', kind='number',
                                           placeholder='2026',
                                           desc='可选：按年份筛选，如 2026（取值见「筛选条件」接口的 year 组）。'),
                                 ParamSpec('area', '地区', placeholder='大陆',
                                           desc='可选：按地区筛选，如 大陆（取值见「筛选条件」接口的 area 组）。'),
                                 ParamSpec('genre', '题材', placeholder='动作',
                                           desc='可选：按题材筛选，如 动作（取值见「筛选条件」接口的 genre 组）。'),
                                 ParamSpec('lang', '语言', placeholder='国语',
                                           desc='可选：按语言筛选，如 国语（取值见「筛选条件」接口的 lang 组）。'),
                             ],
                             notes=['返回 data.items（影片列表）与 data.pagination（分页信息）。',
                                    '地区 / 题材 / 语言 / 年份 / 排序可任意组合，源站按交集返回；'
                                    '组合后没有匹配影片时 data.items 为空数组，不会报错。'],
                             response_fields=[
                                 ResponseFieldSpec('type_id', 'int', '分类 ID（回带入参）'),
                                 ResponseFieldSpec('page', 'int', '当前页码'),
                                 ResponseFieldSpec('items', 'array', '影片列表'),
                                 ResponseFieldSpec('items[].id', 'string', '影片 ID（传给详情接口 vod_id）'),
                                 ResponseFieldSpec('items[].name', 'string', '片名'),
                                 ResponseFieldSpec('items[].url', 'string', '详情页地址'),
                                 ResponseFieldSpec('items[].cover', 'string', '封面图地址'),
                                 ResponseFieldSpec('items[].note', 'string', '角标/备注'),
                                 ResponseFieldSpec('items[].douban', 'string', '豆瓣评分'),
                                 ResponseFieldSpec('pagination', 'object', '分页信息'),
                                 ResponseFieldSpec('pagination.current', 'int', '当前页码'),
                                 ResponseFieldSpec('pagination.total', 'int', '总页数'),
                             ],
                             response_example="""{
  "type_id": 1,
  "page": 1,
  "items": [
    {"id": "812640", "name": "示例影片", "url": "https://5dy4.vip/voddetail/812640.html", "cover": "https://img.example.com/812640.jpg", "note": "更新至10集", "douban": "8.0"}
  ],
  "pagination": {"current": 1, "total": 44}
}"""),
                EndpointSpec('detail', '影片详情', 'GET',
                             '/api/movies/movie_555/detail',
                             summary='获取影片详情：简介、导演/演员等元数据、播放源与选集列表。',
                             params=[
                                 ParamSpec('vod_id', '影片 ID', kind='number', required=True,
                                           placeholder='812640',
                                           desc='必填：影片 ID（取自列表/搜索结果中的 id）。'),
                             ],
                             notes=['返回 data.sources（播放源），每个源含 episodes（选集），'
                                    '选集里的 sid/nid 用于「播放地址」接口。',
                                    '影片不存在时返回 40001。'],
                             response_fields=[
                                 ResponseFieldSpec('id', 'string', '影片 ID'),
                                 ResponseFieldSpec('name', 'string', '片名'),
                                 ResponseFieldSpec('cover', 'string', '封面图地址'),
                                 ResponseFieldSpec('intro', 'string', '剧情简介'),
                                 ResponseFieldSpec('info', 'object', '元数据键值对（导演/主演/上映等）'),
                                 ResponseFieldSpec('sources', 'array', '播放源列表'),
                                 ResponseFieldSpec('sources[].sid', 'string', '播放源序号，传给播放接口'),
                                 ResponseFieldSpec('sources[].name', 'string', '播放源名称'),
                                 ResponseFieldSpec('sources[].episodes', 'array', '该源的选集列表'),
                                 ResponseFieldSpec('sources[].episodes[].nid', 'string', '集数序号，传给播放接口'),
                                 ResponseFieldSpec('sources[].episodes[].name', 'string', '集数名称'),
                                 ResponseFieldSpec('sources[].episodes[].url', 'string', '播放页地址'),
                             ],
                             response_example="""{
  "id": "812640",
  "name": "示例影片",
  "cover": "https://img.example.com/812640.jpg",
  "intro": "",
  "info": {"导演": "张三", "主演": "李四", "上映": "2026"},
  "sources": [
    {"sid": "3", "name": "线路1", "episodes": [
      {"nid": "1", "name": "第1集", "url": "https://5dy4.vip/vodplay/812640-3-1.html"}
    ]}
  ]
}"""),
                EndpointSpec('play', '播放地址', 'GET',
                             '/api/movies/movie_555/play',
                             summary='获取指定播放源/集数的 m3u8 播放地址。',
                             params=[
                                 ParamSpec('vod_id', '影片 ID', kind='number', required=True,
                                           placeholder='812640'),
                                 ParamSpec('sid', '播放源序号', kind='number', required=True,
                                           placeholder='3',
                                           desc='必填：播放源序号，取自详情接口 sources[].sid。'),
                                 ParamSpec('nid', '集数序号', kind='number', required=True,
                                           placeholder='1',
                                           desc='必填：集数序号，取自选集 episodes[].nid（电影通常为 1）。'),
                             ],
                             notes=['返回 data.m3u8 为可播放地址；该地址带时效，已做较短缓存（默认 30 分钟）。',
                                    '源站地址直出，不做代理转发。',
                                    'sid / nid 越界或源站无有效地址时返回 40001。',
                                    '页面下方提供在线播放器：请求成功后自动加载播放，也可粘贴任意 m3u8 地址测试。'],
                             player=True,
                             response_fields=[
                                 ResponseFieldSpec('id', 'string', '影片 ID（回带入参）'),
                                 ResponseFieldSpec('sid', 'int', '播放源序号（回带入参）'),
                                 ResponseFieldSpec('nid', 'int', '集数序号（回带入参）'),
                                 ResponseFieldSpec('name', 'string', '片名'),
                                 ResponseFieldSpec('episode', 'string', '集数名称'),
                                 ResponseFieldSpec('m3u8', 'string', 'm3u8 播放地址（带时效）'),
                                 ResponseFieldSpec('from', 'string', '源站标识'),
                                 ResponseFieldSpec('encrypt', 'int', '是否加密（源站字段，通常 0）'),
                             ],
                             response_example="""{
  "id": "812640",
  "sid": 3,
  "nid": 1,
  "name": "示例影片",
  "episode": "第1集",
  "m3u8": "https://cdn.example.com/812640/1000.m3u8",
  "from": "dyttm3u8",
  "encrypt": 0
}"""),
                EndpointSpec('search', '搜索影片', 'GET',
                             '/api/movies/movie_555/search',
                             summary='按关键词搜索影片，支持分页。',
                             params=[
                                 ParamSpec('keyword', '搜索关键词', required=True,
                                           placeholder='保姆',
                                           desc='必填：搜索关键词（片名）。'),
                                 ParamSpec('page', '页码', kind='number', default='1',
                                           placeholder='1',
                                           desc='可选：页码，从 1 开始，默认 1。'),
                             ],
                             notes=['返回 data.results（影片列表，字段与列表接口一致）'
                                    '与 data.pagination（分页信息，total 为总页数）。'],
                             response_fields=[
                                 ResponseFieldSpec('keyword', 'string', '搜索关键词（回带入参）'),
                                 ResponseFieldSpec('page', 'int', '当前页码'),
                                 ResponseFieldSpec('results', 'array', '搜索结果列表'),
                                 ResponseFieldSpec('results[].id', 'string', '影片 ID'),
                                 ResponseFieldSpec('results[].name', 'string', '片名'),
                                 ResponseFieldSpec('results[].url', 'string', '详情页地址'),
                                 ResponseFieldSpec('results[].cover', 'string', '封面图地址'),
                                 ResponseFieldSpec('results[].note', 'string', '角标/备注'),
                                 ResponseFieldSpec('results[].category', 'string', '分类名称'),
                                 ResponseFieldSpec('pagination', 'object', '分页信息'),
                                 ResponseFieldSpec('pagination.current', 'int', '当前页码'),
                                 ResponseFieldSpec('pagination.total', 'int', '总页数'),
                             ],
                             response_example="""{
  "keyword": "保姆",
  "page": 1,
  "results": [
    {"id": "812640", "name": "示例影片", "url": "https://5dy4.vip/voddetail/812640.html", "cover": "https://img.example.com/812640.jpg", "note": "", "category": "动作片"}
  ],
  "pagination": {"current": 1, "total": 5}
}"""),
            ],
        ),
    ],
)
