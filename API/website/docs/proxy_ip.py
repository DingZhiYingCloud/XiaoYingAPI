"""代理 IP 服务 - 接口文档与在线调试数据

数据与 API/apis/ProxyIp/ 实际实现对齐（服务策略 /api/ProxyIp/ 默认需签名）：
- juliang：巨量代理 IP（独享代理产品，key/sign 双模式凭据）
- 51daili：51代理 IP（动态提取，账号三件套 + 套餐 ID 整组传参）
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ServiceSpec


def _num(name, label, default, desc=''):
    return ParamSpec(name, label, kind='number', default=str(default), desc=desc)


def _flag_sel(name, label, desc='', yes='1=是', no='0=否'):
    """0/1 开关型参数（官方文档中以 0/1 表示开关）"""
    return ParamSpec(name, label, kind='select',
                     options=[{'value': '', 'label': '不传'},
                              {'value': '1', 'label': yes},
                              {'value': '0', 'label': no}],
                     desc=desc)


SERVICE = ServiceSpec(
    slug='proxy_ip',
    name='代理 IP',
    prefix='/api/ProxyIp/',
    summary='国内动态代理 IP：巨量代理与 51代理两条线路，均按次提取、返回结构化 ip:port 列表。',
    keywords='代理IP API,动态代理IP,HTTP代理接口,国内代理IP',
    intro=[
        '代理 IP 服务提供两条国内动态代理线路：巨量代理（独享代理产品，key / sign 双模式凭据）'
        '与 51代理（参数名与官方提取链接一致，账密可整组自带）。调用方按需选择线路即可，'
        '不必分别对接各平台的协议与参数。',
        '动态代理的有效期普遍很短（数十秒到数分钟），提取后可立即用于采集；用尽或过期后重新调用即可。'
        '所有线路均需项目签名。',
    ],
    channels=[
        ChannelSpec(
            slug='juliang',
            name='巨量代理 IP',
            provider='juliangip.com（独享代理产品，国内动态 IP）',
            auth_note='auth',
            note='按次提取国内动态代理 IP。官方签名与参数集严格绑定（改任何参数都会验签失败），故提供两种凭据模式（二选一）：'
                 'key 模式 = 传业务密钥，由服务端按官方规则代算签名，可自由传 num / area / isp 等任意参数；'
                 'custom_sign 模式 = 传自己算好的签名，参数原样透传、服务端不补任何默认值。'
                 '业务编号 / 密钥 / 代理账密默认由平台 .env 持有，调用方也可传自己的（使用自己购买的订单）。'
                 '注：官方文档里的签名参数叫 sign，本接口对外叫 custom_sign——'
                 '平台自身的鉴权参数已占用 sign，服务端会把 custom_sign 原样传给官方接口的 sign 字段。',
            endpoints=[
                EndpointSpec('proxies', '获取动态代理', 'GET', '/api/ProxyIp/juliang/proxies',
                             summary='提取巨量代理动态 IP，返回解析好的 ip:port 列表（默认 JSON 格式）。',
                             params=[
                                 _num('num', '数量', 1, desc='选填：单次提取数量，1-100，默认 1'),
                                 ParamSpec('trade_no', '业务编号', kind='text', placeholder='如 1483587531995538',
                                           desc='选填：巨量代理业务编号；不传则用平台 .env（PROXY_JULIANG_TRADE_NO）'),
                                 ParamSpec('key', '业务密钥', kind='password',
                                           desc='选填：由服务端代算签名，可自由传其它参数；与 custom_sign 二选一；'
                                                '不传则用平台 .env（PROXY_JULIANG_KEY）'),
                                 ParamSpec('custom_sign', '自算签名', kind='password',
                                           desc='选填：按官方规则算好的 32 位小写 MD5（服务端会作为官方的 sign 发送）；'
                                                '与 key 二选一；传 custom_sign 时参数原样透传，服务端不做任何补全'),
                                 ParamSpec('username', '代理账号', kind='text',
                                           desc='选填：代理认证账号，与 password 成对；不传则用平台 .env（PROXY_JULIANG_USERNAME）'),
                                 ParamSpec('password', '代理密码', kind='password',
                                           desc='选填：与 username 成对；不传则用平台 .env（PROXY_JULIANG_PASSWORD）'),
                                 ParamSpec('pt', '代理协议', kind='select',
                                           options=[{'value': '', 'label': '不传（默认 1=HTTP）'},
                                                    {'value': '1', 'label': '1=HTTP'},
                                                    {'value': '2', 'label': '2=SOCKS5'}],
                                           desc='选填'),
                                 ParamSpec('area', '地区筛选', kind='text', placeholder='如 北京,上海',
                                           desc='选填：按地区筛选，多个用英文逗号分隔'),
                                 ParamSpec('isp', '运营商筛选', kind='text', placeholder='如 电信',
                                           desc='选填：按运营商筛选（电信 / 联通 / 移动）'),
                                 ParamSpec('result_type', '返回格式', kind='select',
                                           options=[{'value': '', 'label': '不传（默认 json）'},
                                                    {'value': 'json', 'label': 'json'},
                                                    {'value': 'text', 'label': 'text'}],
                                           desc='选填：不支持 xml（无法解析出 ip:port）'),
                                 ParamSpec('split', '文本分隔符', kind='select',
                                           options=[{'value': '', 'label': '不传（默认 1）'},
                                                    {'value': '1', 'label': '1=回车换行'},
                                                    {'value': '2', 'label': '2=换行'},
                                                    {'value': '3', 'label': '3=空格'},
                                                    {'value': '4', 'label': '4=竖线'}],
                                           desc='选填：仅 result_type=text 时生效'),
                                 _flag_sel('auto_white', '自动加白名单',
                                           desc='选填：提取时自动把调用方 IP 加入白名单'),
                                 _flag_sel('filter', '过滤今日已提取',
                                           desc='选填：过滤掉今天已提取过的 IP'),
                                 _flag_sel('city_name', '返回城市名', desc='选填：在附加列返回城市名'),
                                 _flag_sel('city_code', '返回城市编码', desc='选填：在附加列返回城市编码'),
                                 _flag_sel('ip_remain', '返回剩余时长', desc='选填：在附加列返回该 IP 剩余可用时长'),
                                 _flag_sel('auth_info', '返回认证信息', desc='选填：在附加列返回账密认证信息'),
                             ],
                             notes=['key 与 custom_sign 只能二选一，同传返回 20003。',
                                    '两者都不传时：用平台 .env 的密钥走 key 模式；平台未配置则返回 20011/40001。',
                                    'custom_sign 模式（自算签名）的签名与参数集严格绑定，'
                                    '改动任何参数都必须重算签名，否则上游接口返回 401。',
                                    'username 与 password 必须成对出现（传一个会返回 20001）；'
                                    '成对提供时每条代理附带可直接使用的 proxy 字段。',
                                    '附加列参数（city_name / ip_remain / auth_info 等）开启后，'
                                    '该 IP 的附加内容统一放在 extra 字段，不影响 ip / port 解析。']),
            ],
        ),
        ChannelSpec(
            slug='51daili',
            name='51代理 IP',
            provider='51daili.com（bapi.51daili.com getapi2，国内动态 IP）',
            auth_note='auth',
            note='按次提取国内动态代理 IP。参数名与官方控制台生成的提取链接完全一致，可直接照抄。'
                 '账号三件套（uid / accessName / accessPassword）与套餐标识（packid / rid）'
                 '默认由平台 .env 持有，调用方也可**整套**传自己的（使用自己购买的套餐）——'
                 '只传其中一部分会被拒绝，因为混用两个账号的凭据没有意义。'
                 '其余参数（qty / time / port / format / field / linePoolIndex）不传则用平台默认值。',
            endpoints=[
                EndpointSpec('proxies', '获取动态代理', 'GET', '/api/ProxyIp/51daili/proxies',
                             summary='提取 51代理动态 IP，返回解析好的 ip:port 列表（默认 JSON 格式）。',
                             params=[
                                 _num('qty', '数量', 1, desc='选填：单次提取数量，>=1，默认 1，最大 100'),
                                 ParamSpec('port', '代理协议', kind='select',
                                           options=[{'value': '', 'label': '不传（默认 1=HTTP/HTTPS）'},
                                                    {'value': '1', 'label': '1=HTTP/HTTPS'},
                                                    {'value': '2', 'label': '2=Socks5'}],
                                           desc='选填'),
                                 ParamSpec('time', '稳定使用时长', kind='text', default='31',
                                           desc='选填：官方文档标注取值范围 1-6，本线路默认 31；'
                                                '实际可用时长以账号套餐为准'),
                                 ParamSpec('format', '返回格式', kind='select',
                                           options=[{'value': '', 'label': '不传（默认 json）'},
                                                    {'value': 'json', 'label': 'json'},
                                                    {'value': 'txt', 'label': 'txt'}],
                                           desc='选填：不支持 html（无法解析出 ip:port）'),
                                 ParamSpec('field', '返回字段', kind='text',
                                           default='ipport,expiretime,regioncode,isptype',
                                           desc='选填：英文逗号分隔；不含 ipport 时上游会把 ip / port 拆成两个字段'),
                                 ParamSpec('linePoolIndex', '线路池索引', kind='text', default='-1',
                                           desc='选填：-1=不限'),
                                 ParamSpec('uid', '账号 ID', kind='text',
                                           desc='选填：不传则用平台 .env（PROXY_51DAILI_UID）'),
                                 ParamSpec('accessName', '账号名', kind='text',
                                           desc='选填：不传则用平台 .env（PROXY_51DAILI_ACCESS_NAME）'),
                                 ParamSpec('accessPassword', '账号密码', kind='password',
                                           desc='选填：不传则用平台 .env（PROXY_51DAILI_ACCESS_PASSWORD）'),
                                 ParamSpec('packid', '套餐 ID', kind='text',
                                           desc='选填：不传则用平台 .env（PROXY_51DAILI_PACKID）'),
                                 ParamSpec('rid', '提取标识', kind='text',
                                           desc='选填：控制台提取链接上的 rid；不传则用平台 .env（PROXY_51DAILI_RID）'),
                             ],
                             notes=['uid / accessName / accessPassword / packid 必须**整组**传入：'
                                    '只传一部分返回 20001，一个都不传则整组回退平台 .env。',
                                    '平台 .env 未配置凭据时返回 40001（并说明缺哪些变量）。',
                                    '每条代理含 ip / port / protocol / region（地区名）/ region_code（地区码）'
                                    '/ isp（运营商）/ end_time（到期时间）。',
                                    'format=txt 时上游改回文本行（ip:port|地区|到期时间|运营商），'
                                    '服务端同样会解析成结构化字段；该模式下拿不到上游错误码，'
                                    '解析不出 ip:port 时会把上游原文作为失败原因返回。',
                                    '账号密码错误时上游返回 10102，服务端会剥掉消息里的账号名前缀再返回。']),
            ],
        ),
    ],
)
