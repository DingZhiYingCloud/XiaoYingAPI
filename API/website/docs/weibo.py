"""微博服务文档（声明式）

约定（见 docs/__init__.py 顶部说明）：中文为源语言，**不要在声明处调用 gettext**；
渲染前由 docs.localize() 对副本逐字段翻译，译文词条在 locale/*/LC_MESSAGES 里维护。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ResponseFieldSpec, ServiceSpec

SERVICE = ServiceSpec(
    slug='weibo',
    name='微博',
    prefix='/api/weibo/',
    summary='微博内容聚合：按频道（分类）取内容 —— 正文、图片、视频直链、转发原微博、作者与互动数，'
            '长文自动展开全文；频道分类（我的频道 / 频道推荐）单独给一个接口。',
    keywords='微博API,微博热门接口,微博频道分类,微博内容采集,微博长文,微博视频直链',
    intro=[
        '微博内容聚合接口：先调 `/api/weibo/channels` 拿到**频道分类**，再用 '
        '`/api/weibo/feed` 按频道取内容 —— 每条微博给出正文、图片、视频直链、'
        '被转发的原微博、作者与转发 / 评论 / 点赞数。',
        '**频道（分类）**：微博热门页 `https://weibo.com/hot/weibo/102803` 里的 `102803` '
        '就是频道 ID（= 热门）。分类接口返回「我的频道」（当前登录账号的频道）与'
        '「频道推荐」两组，每组都给出频道名、ID 与 `containerid` —— '
        '取内容时两个 ID 都要带上（微博要求它们分别传，且取值不同）。',
        '**长文自动展开**：正文被截断的长微博会自动回源取全文，`content` 就是完整正文，'
        '不需要调用方再点一次「展开全文」。',
        '**登录凭据两种用法**：一是在请求里带上 `cookie`（你自己的微博登录 Cookie，'
        '仅本次生效、我们不存储）；不带则回落到**平台统一托管**的账号 —— '
        '平台在后台「账号管理」维护微博账号与登录 Cookie，接口自动取一份可用凭据去访问。'
        '在文档页右侧栏「本机凭据」粘贴并「保存到本机浏览器」，在线调试会自动带上。'
        '若平台托管的凭据失效，接口会明确提示需要重新登录，并把该账号标记为「已过期」。',
        '`/api/weibo/check` 用于校验一份微博凭据是否仍然有效：带上 `cookie` 就校验你自己那份'
        '（完全不碰平台账号），不带则校验平台托管的账号并把结果回写到账号状态。',
    ],
    channels=[
        ChannelSpec(
            slug='weibo',
            name='微博',
            provider='微博（weibo.com）',
            auth_note='auth',
            note='数据来自微博官方 web 接口；调用方可自带登录 Cookie，不传则用平台托管的账号。',
            endpoints=[
                EndpointSpec(
                    slug='channels',
                    name='频道分类',
                    method='POST',
                    path='/api/weibo/channels',
                    summary='微博频道分类：「我的频道」与「频道推荐」两组，含频道名 / ID / containerid。',
                    params=[
                        ParamSpec('cookie', '微博登录 Cookie', kind='textarea', local=True,
                                  placeholder='在右侧栏「本机凭据」粘贴并保存到本机',
                                  desc='可选。填了就用你这份 Cookie 访问（仅本次生效、不落库、'
                                       '不会上传给我们）；留空则用平台统一托管的账号。'),
                    ],
                    notes=[
                        '**频道 ID 就是网页里的数字**：`https://weibo.com/hot/weibo/102803` 的 '
                        '`102803` 即频道 ID（热门）；换别的频道就是换这个数字。',
                        '**两组都返回**，用 `section` 区分：「我的频道」随登录账号而变，'
                        '「频道推荐」是微博推荐的通用频道。',
                        '**`containerid` 要一起带上**：取内容时微博要求 `group_id` 传频道 ID、'
                        '`containerid` 传它自己的值，两者对多数频道**并不相同**'
                        '（如 明星 `1028034288` / `102803_ctg1_4288_-_ctg1_4288`）。',
                        '该接口本身不校验登录态（不带 Cookie 也能返回游客默认频道），'
                        '但「我的频道」会随账号不同而变化。',
                        '也接受 GET（此时参数走 query 串）；因微博 Cookie 较长，推荐用 POST 放表单体。',
                    ],
                    response_fields=[
                        ResponseFieldSpec('count', 'int', '两组加起来的频道总数'),
                        ResponseFieldSpec('groups[].section', 'string', '分组名：我的频道 / 频道推荐'),
                        ResponseFieldSpec('groups[].count', 'int', '该分组下的频道数'),
                        ResponseFieldSpec('groups[].channels[].id', 'string',
                                          '频道 ID（= 网页 /hot/weibo/{id} 里的数字）'),
                        ResponseFieldSpec('groups[].channels[].name', 'string', '频道名'),
                        ResponseFieldSpec('groups[].channels[].containerid', 'string',
                                          '频道 containerid（取内容时与 id 一起传）'),
                        ResponseFieldSpec('groups[].channels[].url', 'string', '频道网页地址'),
                    ],
                ),
                EndpointSpec(
                    slug='feed',
                    name='按频道取内容',
                    method='POST',
                    path='/api/weibo/feed',
                    summary='按频道取内容：正文、图片、视频直链、转发原微博、作者与互动数。',
                    params=[
                        ParamSpec('channel', '频道 ID', default='102803',
                                  placeholder='如 102803',
                                  desc='可选，默认 102803（热门）。取值 = '
                                       '`/api/weibo/channels` 返回的频道 ID。'),
                        ParamSpec('containerid', '频道 containerid', default='',
                                  placeholder='留空自动解析',
                                  desc='可选。取值 = `/api/weibo/channels` 返回的 containerid；'
                                       '留空时服务端会按 channel 自动解析（多一次请求）。'),
                        ParamSpec('limit', '返回条数', kind='number', default='20',
                                  placeholder='如 20',
                                  desc='可选，1~50，默认 20。'),
                        ParamSpec('since_id', '翻页游标', default='0',
                                  placeholder='如 0',
                                  desc='可选，默认 0。翻页时把上一次返回的 `next_since_id` 填进来。'),
                        ParamSpec('cookie', '微博登录 Cookie', kind='textarea', local=True,
                                  placeholder='在右侧栏「本机凭据」粘贴并保存到本机',
                                  desc='可选。填了就用你这份 Cookie 访问（仅本次生效、不落库、'
                                       '不会上传给我们）；留空则用平台统一托管的账号。'),
                    ],
                    notes=[
                        '**长文自动展开**：`is_long_text` 为 `true` 的长微博，服务端会回源取全文'
                        '（取到的更长才替换），`content` 即完整正文（不是摘要、无需再点「展开全文」）。',
                        '**图片**：`content_html` 是 HTML 原文（可直接渲染），`images` 是抽好的'
                        '图片地址数组（大图优先、已去重）。',
                        '**视频**：`video.url` 是 mp4 直链（高清优先，**已统一升级为 https**），'
                        '另有封面 / 标题 / 时长 / 视频页地址；没有视频时 `video` 为 `null`。',
                        '**视频直链有防盗链**：`video.url` 是微博 CDN 的 mp4 直链，请求时必须带 '
                        '`Referer: https://weibo.com/` 才能取到（无 Referer 或第三方域名一律返回 '
                        '403），且地址带 `Expires` 签名、**限时有效**。要在网页里直接播放，请用 '
                        '`video.stream_url`（本站代理，见「视频代理播放」端点）；`video.url` 更适合'
                        '你服务端下载后再自行处理。',
                        '**转发**：被转发的原微博在 `retweeted`（裁剪版，不再向下展开它的转发与长文）；'
                        '没有转发时为 `null`。',
                        '**翻页**：把返回的 `next_since_id` 作为下一次的 `since_id`；'
                        '`next_since_id` 为 `null`（`has_more` 为 `false`）表示上游没有给出下一页游标。',
                        '`containerid` 留空时服务端会先查一次频道分类来解析它；'
                        '想省这次请求，就把 `/api/weibo/channels` 返回的 `containerid` 一起带上。',
                        '也接受 GET（此时参数走 query 串）；因微博 Cookie 较长，推荐用 POST 放表单体。',
                    ],
                    response_fields=[
                        ResponseFieldSpec('channel', 'string', '频道 ID（原样回传）'),
                        ResponseFieldSpec('containerid', 'string', '频道 containerid（原样回传）'),
                        ResponseFieldSpec('count', 'int', '本次返回的条数'),
                        ResponseFieldSpec('total', 'int', '上游给出的该频道总条数（翻页参考）'),
                        ResponseFieldSpec('since_id', 'string', '本次请求使用的翻页游标'),
                        ResponseFieldSpec('next_since_id', 'string',
                                          '下一页游标（null 表示没有下一页）'),
                        ResponseFieldSpec('has_more', 'bool', '是否还有下一页'),
                        ResponseFieldSpec('list[].id', 'string', '微博 ID'),
                        ResponseFieldSpec('list[].mid', 'string', '微博 mid'),
                        ResponseFieldSpec('list[].mblogid', 'string', '微博短 ID（网页地址用它拼）'),
                        ResponseFieldSpec('list[].url', 'string', '微博网页地址（可直接打开）'),
                        ResponseFieldSpec('list[].content', 'string',
                                          '正文纯文本（长文已展开为全文）'),
                        ResponseFieldSpec('list[].content_html', 'string',
                                          '正文 HTML 原文（含 @ / 话题 / 链接标签）'),
                        ResponseFieldSpec('list[].is_long_text', 'bool', '是否为长文'),
                        ResponseFieldSpec('list[].images', 'array', '图片地址（大图优先）'),
                        ResponseFieldSpec('list[].video', 'object', '视频信息（无视频为 null）'),
                        ResponseFieldSpec('list[].video.url', 'string',
                                          '微博 CDN 的 mp4 直链（https、高清优先；有 Referer 防盗链）'),
                        ResponseFieldSpec('list[].video.stream_url', 'string',
                                          '本站代理播放地址（<video> 直接可用、长期有效）'),
                        ResponseFieldSpec('list[].video.cover', 'string', '视频封面地址'),
                        ResponseFieldSpec('list[].video.title', 'string', '视频标题'),
                        ResponseFieldSpec('list[].video.duration', 'int', '视频时长（秒）'),
                        ResponseFieldSpec('list[].video.page_url', 'string', '视频页地址'),
                        ResponseFieldSpec('list[].retweeted', 'object',
                                          '被转发的原微博（无转发为 null）'),
                        ResponseFieldSpec('list[].retweeted.content', 'string', '原微博正文'),
                        ResponseFieldSpec('list[].retweeted.author.name', 'string', '原作者昵称'),
                        ResponseFieldSpec('list[].retweeted.url', 'string', '原微博网页地址'),
                        ResponseFieldSpec('list[].author.id', 'string', '作者 ID'),
                        ResponseFieldSpec('list[].author.name', 'string', '作者昵称'),
                        ResponseFieldSpec('list[].author.url', 'string', '作者主页地址'),
                        ResponseFieldSpec('list[].author.avatar', 'string', '作者头像地址'),
                        ResponseFieldSpec('list[].author.verified', 'bool', '作者是否认证'),
                        ResponseFieldSpec('list[].reposts_count', 'int', '转发数'),
                        ResponseFieldSpec('list[].comments_count', 'int', '评论数'),
                        ResponseFieldSpec('list[].attitudes_count', 'int', '点赞数'),
                        ResponseFieldSpec('list[].created_at', 'int', '发布时间（Unix 秒）'),
                        ResponseFieldSpec('list[].source', 'string', '来源（如 iPhone客户端）'),
                        ResponseFieldSpec('list[].region', 'string', '地区（可能为空）'),
                        ResponseFieldSpec('list[].is_ad', 'bool', '是否广告'),
                    ],
                ),
                EndpointSpec(
                    slug='video',
                    name='视频代理播放',
                    method='GET',
                    path='/api/weibo/video',
                    summary='微博视频代理播放：本站取流后转发，普通 <video> 标签直接播放。',
                    params=[
                        ParamSpec('token', '播放令牌', required=True,
                                  placeholder='由 feed 接口的 video.stream_url 携带',
                                  desc='必填：由 `/api/weibo/feed` 下发的时效令牌，'
                                       '无需项目签名（浏览器加不了签名）。'),
                    ],
                    notes=[
                        '**为什么需要代理**：微博视频 CDN 有 Referer 防盗链，只认微博系域名 —— '
                        '第三方页面的 `<video>` 带的是自己的域名，一律 403；直链又是 `http://`，'
                        'https 页面还会被浏览器按混合内容直接拦掉。本端点带 `Referer` 取流后原样转发。',
                        '地址由 `/api/weibo/feed` 的 `video.stream_url` 给出、**长期有效**：'
                        '令牌里只有微博 id，播放时按 id 现场解析新鲜直链（微博直链带 `Expires` 会过期）。',
                        '**本端点不带项目签名**：浏览器加不了签名，且拖动进度条产生的多次 Range 请求'
                        '会撞上「nonce 一次性」的重放拦截，故鉴权由 URL 里的时效令牌承担。',
                        '支持 HTTP Range（200 整段 / 206 分片）：可拖动进度条、可断点续传。',
                        '令牌无效或过期返回 403（重新调用 feed 拿新地址即可）；'
                        '上游取流失败走统一错误码（40001 / 50002）。',
                    ],
                    response_note='成功返回视频二进制流（video/mp4，支持 Range），**不是统一 JSON 信封**；'
                                  '令牌无效或过期返回 403。',
                ),
                EndpointSpec(
                    slug='check',
                    name='校验登录凭据',
                    method='POST',
                    path='/api/weibo/check',
                    summary='校验微博登录凭据是否有效（自带 cookie 校验你自己那份，否则校验平台托管的账号）。',
                    params=[
                        ParamSpec('cookie', '微博登录 Cookie', kind='textarea', local=True,
                                  placeholder='在右侧栏「本机凭据」粘贴并保存到本机',
                                  desc='可选。填了就只校验你这份（不碰平台账号、不回写任何状态）；'
                                       '留空则校验平台托管的账号并把结果回写其状态。'),
                    ],
                    notes=[
                        '凭据无效**不算接口调用失败**：仍返回成功码，把 `valid=false` 与原因放在 data 里，'
                        '由调用方自行决定是否提示用户重新登录。',
                        '微博接口在未登录时**仍返回 HTTP 200**（body 是 `ok: -100` 的登录跳转），'
                        '本接口按此判定凭据是否有效，因此比只看状态码可靠。',
                        '校验平台托管的账号时会更新其「凭据状态」与「最近校验结果」，'
                        '在后台「账号管理」页可直接看到；自带 Cookie 校验不涉及平台账号。',
                        '也接受 GET（此时参数走 query 串）；因微博 Cookie 较长，推荐用 POST 放表单体。',
                    ],
                    response_fields=[
                        ResponseFieldSpec('valid', 'bool', '凭据是否有效'),
                        ResponseFieldSpec('account', 'string', '被校验的账号标识（自带 Cookie 校验时为空）'),
                        ResponseFieldSpec('message', 'string', '校验说明'),
                    ],
                ),
            ],
        ),
    ],
)
