"""短剧服务 - 接口文档与在线调试数据

数据与 API/apis/dramas/ 实际实现对齐（服务策略 /api/dramas/ 默认需签名）：
- hongguo  红果短剧网页版线路（实时爬取源站 SSR 数据 + 文件缓存；
  超出源站明链范围的集数由服务端走 App 内部接口取流并解密）

接入方拿到授权后，可按「榜单/分类 → 列表 → 详情 → 播放」跑通短剧站流程。
后续接入更多线路（如其它短剧平台）时在 channels 追加即可。
"""
from API.apis.dramas.hongguo.utils import DEFAULT_QUALITY, QUALITY_WIDTHS

from .schema import ChannelSpec, EndpointSpec, ParamSpec, ServiceSpec

# 出流画质档位直接取后端白名单，避免「文档里能选、接口却报参数非法」——
# 真实可选值只有一个来源（API/apis/dramas/hongguo/utils.py 的 QUALITY_WIDTHS）。
# 画质下拉选项：值是输出宽度上限（短剧是竖屏，1080 即 1080×1920，也就是日常说的 1080p）
_QUALITY_EXTRA_LABEL = {1080: '（源站最高，推荐）'}
_QUALITY_OPTIONS = [
    {'value': str(w), 'label': f'{w}p{_QUALITY_EXTRA_LABEL.get(w, "")}'}
    for w in QUALITY_WIDTHS
]

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
        '已上架到外部平台的集优先返回外部地址，其余走本站直出（首次点播需等待数十秒生成，'
        '之后即刻返回）。',
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
                             summary='获取短剧榜单，支持热播榜 / 真人剧热播榜 / AI剧热播榜与分页。',
                             params=[
                                 ParamSpec('type', '榜单类型', kind='select',
                                           default='hot-drama',
                                           options=[
                                               {'value': 'hot-drama', 'label': '热播榜'},
                                               {'value': 'hot-real-drama', 'label': '真人剧热播榜'},
                                               {'value': 'hot-ai-drama', 'label': 'AI剧热播榜'},
                                           ],
                                           desc='可选：榜单类型，默认 hot-drama（热播榜）。'),
                                 ParamSpec('page', '页码', kind='number', default='1',
                                           placeholder='1',
                                           desc='可选：页码，从 1 开始，默认 1。'),
                             ],
                             notes=['榜单类型非法时返回 PARAM_VALUE_INVALID。',
                                    '返回 data 为榜单剧集列表（字段与「分类列表」接口一致）。']),
                EndpointSpec('categories', '分类清单', 'GET',
                             '/api/dramas/hongguo/categories',
                             summary='获取可用分类清单（slug -> 中文名）。',
                             notes=['返回的 slug 可直接传给「分类列表」接口的 category 参数。']),
                EndpointSpec('list', '分类列表', 'GET',
                             '/api/dramas/hongguo/list',
                             summary='按分类获取短剧列表，支持分页。',
                             params=[
                                 ParamSpec('category', '分类', kind='select', required=True,
                                           options=[
                                               {'value': 'real-drama', 'label': '真人剧'},
                                               {'value': 'comic-drama', 'label': '漫剧'},
                                               {'value': 'ai-drama', 'label': 'AI剧'},
                                               {'value': 'comic', 'label': '漫画'},
                                           ],
                                           desc='必填：分类 slug（取值见「分类清单」接口）。'),
                                 ParamSpec('page', '页码', kind='number', default='1',
                                           placeholder='1',
                                           desc='可选：页码，从 1 开始，默认 1。'),
                             ],
                             notes=['category 缺失或非法时返回 PARAM_MISSING / PARAM_VALUE_INVALID。']),
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
                             notes=['源站搜索不支持分页，恒返回单页（page 传入也仅返回同一批结果）。']),
                EndpointSpec('detail', '剧集详情', 'GET',
                             '/api/dramas/hongguo/detail',
                             summary='获取剧集详情与全量集列表。',
                             params=[
                                 ParamSpec('series_id', '剧集 ID', required=True,
                                           placeholder='7686894628578020414',
                                           desc='必填：剧集 ID（取自列表/搜索结果）。'),
                             ],
                             notes=['返回 data.episodes 为全量集列表，每项含 ep / episode_id / playable；'
                                    'playable 已合并「已登记外链」——第 4 集及以后一旦登记了外部播放地址，'
                                    '该集 playable 即为 true，与「播放地址」接口的可用性一致。',
                                    'data.playable_cnt 为源站直链的连续范围（前 N 集）；'
                                    'data.listed_cnt 为实际可播集数（源站直链 + 已登记外链，可能不连续）。'
                                    '需要判断「某集能不能播」请用 episodes[].playable，不要用 playable_cnt 推算。',
                                    '剧集不存在时返回 EXTERNAL_API_FAILED（外部API调用失败）。']),
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
                                    'H.265（浏览器无法解码），改由本站出流，data.source 区分来源：',
                                    '· external —— 已上架到外部平台的地址（data.url 为第三方地址）；',
                                    '· stream —— 本站直出：data.url 为可直接交给 <video> 播放的地址'
                                    '（明文 H.264、支持 HTTP Range 拖动），画质见 data.quality，'
                                    'data.ready=false 表示该画质首次被点播、服务端正在生成（约数十秒），'
                                    '请轮询该地址，返回 200 即可播放。',
                                    '该地址的鉴权由 data.url 里的时效令牌承担（默认 2 小时），'
                                    '过期后重新调用本接口换取新地址。',
                                    'ep 越界（超出总集数）返回 PARAM_VALUE_INVALID。',
                                    '源站直链带时效，请勿长期缓存。'],
                             player=True),
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
                                    '解密并转成 H.264（约数十秒），轮询到 200 即可播放；'
                                    '产物落盘永久复用，此后再播为即刻返回。',
                                    '令牌无效或过期返回 403，需重新调用「播放地址」接口获取新地址。']),
            ],
        ),
    ],
)
