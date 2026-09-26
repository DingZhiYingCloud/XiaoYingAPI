"""电影服务 - 接口文档与在线调试数据

数据与 API/apis/movies/ 实际实现对齐（分类树 /api/movies/ 为需签名）：
- movie_555  555电影线路（苹果CMS 站，实时爬取 + 文件缓存）

接入方拿到授权后，可按「分类列表 → 筛选条件 → 列表 → 详情 → 播放地址」跑通完整影视站流程。
后续接入更多线路（如爱奇艺 / 腾讯等）时在 channels 追加即可。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ServiceSpec

SERVICE = ServiceSpec(
    slug='movie',
    name='电影',
    prefix='/api/movies/',
    summary='电影聚合服务：提供影视的分类、列表、详情、选集与播放地址（m3u8）能力，'
            '按「列表 → 详情 → 播放」流程即可搭建完整影视站。',
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
                                    '返回的 id 都可直接传给「列表」接口的 type_id。']),
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
                                    '年份还会随站点上新自动增加，建议由本接口动态渲染筛选栏，不要在客户端写死。']),
                EndpointSpec('home', '首页聚合', 'GET',
                             '/api/movies/movie_555/home',
                             summary='获取首页聚合数据：轮播图与各推荐区块（本周/本月最佳、各榜单等）。',
                             notes=['一次返回首页全部推荐区块，便于直接渲染站点首页。']),
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
                                    '组合后没有匹配影片时 data.items 为空数组，不会报错。']),
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
                                    '影片不存在时返回 40001。']),
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
                             player=True),
                EndpointSpec('search', '搜索影片', 'GET',
                             '/api/movies/movie_555/search',
                             summary='按关键词搜索影片。',
                             params=[
                                 ParamSpec('keyword', '搜索关键词', required=True,
                                           placeholder='交锋',
                                           desc='必填：搜索关键词（片名）。'),
                             ],
                             notes=['返回 data.results 影片列表，字段与列表接口一致。']),
            ],
        ),
    ],
)
