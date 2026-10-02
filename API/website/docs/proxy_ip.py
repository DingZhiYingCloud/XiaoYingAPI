"""代理 IP 服务 - 接口文档与在线调试数据

数据与 API/apis/ProxyIp/ 实际实现对齐（服务策略 /api/ProxyIp/ 默认需签名）：
- juliang：巨量代理 IP（独享代理产品，key/sign 双模式凭据）
- 51daili：51代理 IP（动态提取，不限量套餐接口；账号三件套 + 套餐 ID + 不限量套餐 ID 整组传参）
"""
from .schema import (ChannelSpec, EndpointSpec, ParamSpec, ResponseFieldSpec,
                     ServiceSpec)


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
                                    '该 IP 的附加内容统一放在 extra 字段，不影响 ip / port 解析。'],
                             response_fields=[
                                 ResponseFieldSpec('proxies', 'array', '代理列表'),
                                 ResponseFieldSpec('proxies[].ip', 'string', '代理 IP'),
                                 ResponseFieldSpec('proxies[].port', 'string', '代理端口'),
                                 ResponseFieldSpec('proxies[].protocol', 'string', '协议：HTTP / SOCKS5'),
                                 ResponseFieldSpec('proxies[].region', 'string', '归属说明（固定为「国内动态」）'),
                                 ResponseFieldSpec('proxies[].extra', 'string', '附加列内容；仅开启附加列参数时出现'),
                                 ResponseFieldSpec('proxies[].username', 'string', '代理认证账号；随账密成对出现时才有'),
                                 ResponseFieldSpec('proxies[].password', 'string', '代理认证密码；随账密成对出现时才有'),
                                 ResponseFieldSpec('proxies[].proxy', 'string', '可直接使用的代理地址；随账密成对出现时才有'),
                                 ResponseFieldSpec('total', 'int', '返回总数'),
                                 ResponseFieldSpec('fetched', 'int', '本次返回数'),
                             ],
                             response_example='''{
  "proxies": [
    {"ip": "27.28.167.190", "port": "36629", "protocol": "HTTP", "region": "国内动态",
     "username": "user", "password": "pass",
     "proxy": "http://user:pass@27.28.167.190:36629"}
  ],
  "total": 1,
  "fetched": 1
}'''),
            ],
        ),
        ChannelSpec(
            slug='51daili',
            name='51代理 IP',
            provider='51daili.com（bapi.51daili.com 不限量套餐接口，国内动态 IP）',
            auth_note='auth',
            note='按次提取国内动态代理 IP，走 51代理 的**不限量套餐**提取接口。'
                 '参数名与官方控制台生成的提取链接完全一致，可直接照抄。'
                 '账号三件套（uid / accessName / accessPassword）与套餐标识（packid / pid）'
                 '默认由平台 .env 持有，调用方也可**整套**传自己的（使用自己购买的套餐）——'
                 '只传其中一部分会被拒绝，因为混用两个账号的凭据没有意义'
                 '（`pid` 是不限量套餐 ID，缺了上游会直接回「不限量套餐id不能为空」）。'
                 '其余参数（qty / time / port / format / field / linePoolIndex）不传则用平台默认值。',
            endpoints=[
                EndpointSpec('proxies', '获取动态代理', 'GET', '/api/ProxyIp/51daili/proxies',
                             summary='提取 51代理动态 IP，返回解析好的 ip:port 列表（默认 JSON 格式），'
                                     '每条另带一个 `proxy` 字段 —— 那是**经国内中转**、在任何网络下都能直接用的形态。',
                             params=[
                                 _num('qty', '数量', 1, desc='选填：单次提取数量，>=1，默认 1，最大 100'),
                                 ParamSpec('port', '代理协议', kind='select',
                                           options=[{'value': '', 'label': '不传（默认 1=HTTP/HTTPS）'},
                                                    {'value': '1', 'label': '1=HTTP/HTTPS'},
                                                    {'value': '2', 'label': '2=Socks5'}],
                                           desc='选填'),
                                 ParamSpec('time', '稳定使用时长', kind='text', default='2',
                                           desc='选填：本线路默认 2（照抄平台控制台生成的提取链接）；'
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
                                 ParamSpec('pid', '不限量套餐 ID', kind='text',
                                           desc='选填：本接口**必填项**（缺了上游回「不限量套餐id不能为空」）；'
                                                '不传则用平台 .env（PROXY_51DAILI_PID）'),
                                 ParamSpec('rid', '提取标识', kind='text',
                                           desc='选填：控制台提取链接上的 rid；不传则用平台 .env（PROXY_51DAILI_RID）'),
                             ],
                             notes=['uid / accessName / accessPassword / packid / pid 必须**整组**传入：'
                                    '只传一部分返回 20001，一个都不传则整组回退平台 .env。',
                                    '平台 .env 未配置凭据时返回 40001（并说明缺哪些变量）。',
                                    '⚠️ 51代理 的节点**只从中国内地网络可达**：海外服务器拿正确账密直连也是一律'
                                    ' TCP 超时（实测 0/5）。因此平台尽量再给每条补一个 `proxy` 字段 ——'
                                    ' 那是**经国内中转**的形态（`http://<会话键>:<密钥>@<中转机>:17890`），'
                                    ' 可直接塞进 requests 的 proxies（`{"http": proxy, "https": proxy}`），'
                                    ' 由国内中转机去连 51代理 节点并把数据回传，因此**任何网络环境都能用**。'
                                    ' 平台未配置中转（`.env` 的 PROXY_RELAY_URL / PROXY_RELAY_SECRET 为空）时，'
                                    ' 该字段不出现，返回与旧版一致。',
                                    '`proxy` 与同条的 ip/port **不保证是同一条节点**：中转形态的出口由中转机从'
                                    '同一个 51代理 账号实时取，ip/port/region 描述的是「直连形态会拿到什么」。',
                                    '同一个 `proxy` 反复使用会**粘住同一个出口 IP**（中转机按会话键复用，TTL 10 分钟）；'
                                    '换一条 `proxy` 就换一个出口。',
                                    '中转形态只对中转机白名单内的来源 IP 可用（见中转机 `hj_relay.env` 的'
                                    ' `HJ_RELAY_ALLOW_IPS`，目前是本机与备用出口两个 IP）；新机器接入需把它的出口 IP 加进去。',
                                    'format=txt 时上游改回文本行（ip:port|地区|到期时间|运营商），'
                                    '服务端同样会解析成结构化字段；该模式下拿不到上游错误码，'
                                    '解析不出 ip:port 时会把上游原文作为失败原因返回。',
                                    '账号密码错误时上游返回 10102，服务端会剥掉消息里的账号名前缀再返回。'],
                             response_fields=[
                                 ResponseFieldSpec('proxies', 'array', '代理列表'),
                                 ResponseFieldSpec('proxies[].ip', 'string', '代理 IP'),
                                 ResponseFieldSpec('proxies[].port', 'string', '代理端口'),
                                 ResponseFieldSpec('proxies[].protocol', 'string', '协议：HTTP / SOCKS5'),
                                 ResponseFieldSpec('proxies[].region', 'string', '地区名（可能为空）'),
                                 ResponseFieldSpec('proxies[].region_code', 'string', '地区编码（可能为空）'),
                                 ResponseFieldSpec('proxies[].isp', 'string', '运营商（可能为空）'),
                                 ResponseFieldSpec('proxies[].end_time', 'string', '到期时间（可能为空）'),
                                 ResponseFieldSpec('proxies[].proxy', 'string', '经国内中转的代理地址；未配置中转时无此字段'),
                                 ResponseFieldSpec('total', 'int', '返回总数'),
                                 ResponseFieldSpec('fetched', 'int', '本次返回数'),
                             ],
                             response_example='''{
  "proxies": [
    {"ip": "1.2.3.4", "port": "8080", "protocol": "HTTP", "region": "曲靖市",
     "region_code": "530300", "isp": "电信", "end_time": "2026-10-01 13:26:28",
     "proxy": "http://sess:secret@relay.example.com:17890"}
  ],
  "total": 1,
  "fetched": 1
}'''),
            ],
        ),
    ],
)
