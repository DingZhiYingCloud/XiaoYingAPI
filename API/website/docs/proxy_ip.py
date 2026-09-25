"""代理 IP 服务 - 接口文档与在线调试数据

数据与 API/apis/ProxyIp/ 实际实现对齐（分类树 /api/ProxyIp/ 默认需签名）：
- 66daili：66 免费代理（聚合，可验证可用性并排序）
- qy：青雨动态代理（短期存活，凭据可由调用方自带）
- qy_res：青雨住宅长效代理（提取节点，带到期时间）
- juliang：巨量代理 IP（独享代理产品，key/sign 双模式凭据）
- 91http：91HTTP 动态代理
- static：静态代理（JSON 文件存储的管理）
- thordata：Thordata 动态住宅代理（网关型，入口固定、出口 IP 轮换）
后续新增代理源时在 channels 追加即可。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ServiceSpec

_BOOL_TF = [
    {'value': 'true', 'label': 'true'},
    {'value': 'false', 'label': 'false'},
]

_JSON_PATH_HINT = '选填：自定义 JSON 文件绝对路径；默认使用平台配置路径。涉及服务器文件读写，非必要请勿传。'


def _bool_sel(name, label, default='true', desc=''):
    return ParamSpec(name, label, kind='select', options=_BOOL_TF,
                     default=default, desc=desc)


def _num(name, label, default, desc=''):
    return ParamSpec(name, label, kind='number', default=str(default), desc=desc)


def _flag_sel(name, label, desc='', yes='1=是', no='0=否'):
    """0/1 开关型参数（官方文档中以 0/1 表示开关）"""
    return ParamSpec(name, label, kind='select',
                     options=[{'value': '', 'label': '不传'},
                              {'value': '1', 'label': yes},
                              {'value': '0', 'label': no}],
                     desc=desc)


def _json_path_param():
    return ParamSpec('json_path', 'JSON 文件路径(绝对)', kind='text', desc=_JSON_PATH_HINT)


SERVICE = ServiceSpec(
    slug='proxy_ip',
    name='代理 IP',
    prefix='/api/ProxyIp/',
    summary='多源代理 IP 聚合：66 免费代理、青雨动态代理与住宅长效、巨量代理 IP、91HTTP 动态代理、静态代理管理与 Thordata 动态住宅代理，支持可用性验证。',
    channels=[
        ChannelSpec(
            slug='66daili',
            name='66 免费代理',
            provider='66daili 聚合（支持可用性验证）',
            auth_note='auth',
            note='获取代理并可选验证连通性；verify=true 时按速度排序返回最快的代理。',
            endpoints=[
                EndpointSpec('proxies', '获取可用代理', 'GET', '/api/ProxyIp/66daili/proxies',
                             summary='返回指定数量、可选验证的可用代理列表。',
                             params=[
                                 _num('count', '数量', 10, desc='选填：返回条数，必须为正整数，默认 10'),
                                 ParamSpec('sources', '代理源', kind='text', default='66daili',
                                           desc='选填：代理源名称，多个用英文逗号分隔，如 "66daili,qy"'),
                                 _bool_sel('verify', '验证可用性', desc='选填：默认 true（验证并按速度排序）'),
                             ]),
            ],
        ),
        ChannelSpec(
            slug='qy',
            name='青雨动态代理',
            provider='qydailiip.com（短期存活 1-3 分钟）',
            auth_note='auth',
            note='动态短期代理，每次调用返回全新 IP；订单号/apikey 默认由平台侧持有，'
                 '调用方也可传自己的 order/apikey 使用自己购买的订单。',
            endpoints=[
                EndpointSpec('proxies', '获取动态代理', 'GET', '/api/ProxyIp/qy/proxies',
                             summary='获取青雨动态代理 IP（存活约 1-3 分钟）。',
                             params=[
                                 _num('num', '数量', 1, desc='选填：返回条数，>=1，默认 1（需多个请调大）'),
                                 ParamSpec('order', '订单号', kind='text',
                                           desc='选填：青雨订单号，与 apikey 成对出现；不传则用平台 .env（PROXY_QY_ORDER）'),
                                 ParamSpec('apikey', '账户 apikey', kind='password',
                                           desc='选填：账户 token，与 order 成对出现；不传则用平台 .env（PROXY_QY_APIKEY）'),
                             ],
                             notes=['订单到期或凭据错误时，服务端会返回真实原因（如「您的订单已到期」）。']),
            ],
        ),
        ChannelSpec(
            slug='qy_res',
            name='青雨住宅长效代理',
            provider='qydailiip.com（住宅长效节点，提取后可用至到期）',
            auth_note='auth',
            note='住宅长效节点由青雨侧提取得到一组固定连接信息（主机/端口/账号/密码），节点带到期时间、到期需重新提取，'
                 '故返回的是可直接使用的代理地址而非 IP 列表。连接信息可由调用方传入（使用自己购买的节点），'
                 '不传则用平台 .env 配置；verify=true 会真实经代理发一次请求。',
            endpoints=[
                EndpointSpec('proxies', '获取住宅长效代理', 'GET', '/api/ProxyIp/qy_res/proxies',
                             summary='返回可直接使用的住宅长效代理地址（含账号密码）。',
                             params=[
                                 ParamSpec('host', '连接主机', kind='text', placeholder='如 183.131.35.91',
                                           desc='选填：不传则用平台 .env（PROXY_QY_RES_HOST）'),
                                 ParamSpec('port', '端口', kind='text', placeholder='如 20277',
                                           desc='选填：1-65535；不传则用平台 .env（PROXY_QY_RES_PORT）'),
                                 ParamSpec('username', '账号', kind='text',
                                           desc='选填：不传则用平台 .env（PROXY_QY_RES_USERNAME）'),
                                 ParamSpec('password', '密码', kind='password',
                                           desc='选填：不传则用平台 .env（PROXY_QY_RES_PASSWORD）'),
                                 _bool_sel('verify', '验证可用性', default='false',
                                           desc='选填：默认 false（仅拼装）；true 时真实经代理发一次请求'),
                             ],
                             notes=['username 与 password 必须成对出现（传一个会返回 20001）。',
                                    'data.proxies[0].proxy 即完整代理地址，可直接用作 requests 的 proxies。',
                                    'verify=true 时每项额外返回 available / speed_ms / external_ip。',
                                    'host 指向内网 / 回环 / 保留地址会被拒绝（20003，仅 verify=true 时会做该连通性校验）。',
                                    '节点到期后连接会失败，需重新提取并在 .env 更新，或由调用方传入新节点信息。']),
            ],
        ),
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
            slug='91http',
            name='91HTTP 动态代理',
            provider='api.91http.com（国内动态代理）',
            auth_note='auth',
            note='支持白名单或账号密码两种认证方式，二选一即可；修改授权后约 5 分钟生效。',
            endpoints=[
                EndpointSpec('proxies', '获取动态代理', 'GET', '/api/ProxyIp/91http/proxies',
                             summary='获取 91HTTP 动态代理，可指定协议/白名单/过期时间等。',
                             params=[
                                 _num('num', '数量', 10, desc='选填：>=1，默认 10'),
                                 ParamSpec('protocol', '协议类型', kind='select',
                                           options=[{'value': '', 'label': '不传（默认 HTTP）'},
                                                    {'value': '1', 'label': '1=HTTP'},
                                                    {'value': '2', 'label': '2=HTTPS'},
                                                    {'value': '3', 'label': '3=SOCKS5'},
                                                    {'value': '4', 'label': '4=HTTP(S)'}],
                                           desc='选填'),
                                 ParamSpec('auto_white', '自动白名单', kind='select',
                                           options=[{'value': '', 'label': '不传（默认 1）'},
                                                    {'value': '1', 'label': '1=是'},
                                                    {'value': '0', 'label': '0=否'}],
                                           desc='选填'),
                                 ParamSpec('time', '返回过期时间', kind='select',
                                           options=[{'value': '', 'label': '不传（默认 1）'},
                                                    {'value': '1', 'label': '1=是'},
                                                    {'value': '0', 'label': '0=否'}],
                                           desc='选填'),
                                 ParamSpec('username', '认证用户名', kind='text',
                                           desc='选填：账号密码认证模式，与 password 成对出现'),
                                 ParamSpec('password', '认证密码', kind='password',
                                           desc='选填：与 username 成对出现；使用该模式无需白名单'),
                             ],
                             notes=['白名单认证：不传 username/password，需先在 91HTTP 后台加白本机公网 IP。',
                                    '账号密码认证：返回每条代理附带 proxy 字段（含账号密码的完整地址）。']),
            ],
        ),
        ChannelSpec(
            slug='static',
            name='静态代理',
            provider='JSON 文件存储（平台本地）',
            auth_note='auth',
            note='静态代理以 JSON 文件管理：查询 / 新增 / 按 ip:port 删除 / 重新加载。写操作会改动平台文件，请谨慎。',
            endpoints=[
                EndpointSpec('list', '获取静态代理列表', 'GET', '/api/ProxyIp/static/proxies',
                             summary='返回全部静态代理。', params=[_json_path_param()]),
                EndpointSpec('add', '新增静态代理', 'POST', '/api/ProxyIp/static/proxies',
                             summary='向 JSON 文件新增一条静态代理。',
                             params=[
                                 ParamSpec('ip', 'IP 地址', kind='text', required=True, placeholder='如 1.2.3.4'),
                                 ParamSpec('port', '端口', kind='text', required=True, placeholder='如 8080'),
                                 ParamSpec('username', '用户名', kind='text', desc='选填'),
                                 ParamSpec('password', '密码', kind='password', desc='选填'),
                                 _json_path_param(),
                             ]),
                EndpointSpec('delete', '删除静态代理', 'DELETE', '/api/ProxyIp/static/proxies',
                             summary='按 ip:port 从 JSON 文件删除一条静态代理。',
                             params=[
                                 ParamSpec('ip', 'IP 地址', kind='text', required=True),
                                 ParamSpec('port', '端口', kind='text', required=True),
                                 _json_path_param(),
                             ]),
                EndpointSpec('reload', '重新加载静态代理', 'POST', '/api/ProxyIp/static/proxies/reload',
                             summary='重新从 JSON 文件加载代理列表（配置更新后调用）。',
                             params=[_json_path_param()]),
            ],
        ),
        ChannelSpec(
            slug='thordata',
            name='Thordata 动态住宅代理',
            provider='thordata.com（海外住宅网关，出口 IP 按请求轮换）',
            auth_note='auth',
            note='网关型代理：入口主机 / 端口固定，出口 IP 由 Thordata 侧轮换，故返回的是可直接使用的入口地址，而非 IP 列表。'
                 '主机 / 端口 / 账号 / 密码可由调用方传入，不传则用平台 .env 配置；verify=true 会真实经代理发一次请求（消耗住宅流量）。',
            endpoints=[
                EndpointSpec('proxies', '获取住宅代理', 'GET', '/api/ProxyIp/thordata/proxies',
                             summary='返回可直接使用的住宅代理入口地址（含账号密码）。',
                             params=[
                                 ParamSpec('host', '网关主机', kind='text',
                                           placeholder='如 1rdjtq76.pr.thordata.net',
                                           desc='选填：不传则用平台 .env（PROXY_THORDATA_HOST）'),
                                 ParamSpec('port', '网关端口', kind='text', placeholder='如 9999',
                                           desc='选填：1-65535；不传则用平台 .env（PROXY_THORDATA_PORT）'),
                                 ParamSpec('username', '账号', kind='text',
                                           desc='选填：不传则用平台 .env（PROXY_THORDATA_USERNAME）'),
                                 ParamSpec('password', '密码', kind='password',
                                           desc='选填：不传则用平台 .env（PROXY_THORDATA_PASSWORD）'),
                                 _bool_sel('verify', '验证可用性', default='false',
                                           desc='选填：默认 false（仅拼装，不消耗流量）；true 时真实经代理发一次请求'),
                             ],
                             notes=['username 与 password 必须成对出现（传一个会返回 20001）。',
                                    'data.proxies[0].proxy 即完整代理地址，可直接用作 requests 的 proxies。',
                                    'verify=true 时每项额外返回 available / speed_ms / external_ip。',
                                    'host 指向内网 / 回环 / 保留地址会被拒绝（20003，仅 verify=true 时会做该连通性校验）。',
                                    '未传 username/password 而使用平台默认账号时，响应会把该账号回显给调用方。']),
            ],
        ),
    ],
)
