"""代理 IP 服务 - 接口文档与在线调试数据

数据与 API/apis/ProxyIp/ 实际实现对齐（分类树 /api/ProxyIp/ 默认需签名）：
- 66daili：66 免费代理（聚合，可验证可用性并排序）
- qy：青雨动态代理（短期存活）
- 91http：91HTTP 动态代理
- static：静态代理（JSON 文件存储的管理）
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


def _json_path_param():
    return ParamSpec('json_path', 'JSON 文件路径(绝对)', kind='text', desc=_JSON_PATH_HINT)


SERVICE = ServiceSpec(
    slug='proxy_ip',
    name='代理 IP',
    prefix='/api/ProxyIp/',
    summary='多源代理 IP 聚合：66 免费代理、青雨动态代理、91HTTP 动态代理与静态代理管理，支持可用性验证。',
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
            note='动态短期代理，每次调用返回全新 IP；订单号/Token 由平台侧持有，调用方无需提供。',
            endpoints=[
                EndpointSpec('proxies', '获取动态代理', 'GET', '/api/ProxyIp/qy/proxies',
                             summary='获取青雨动态代理 IP（存活约 1-3 分钟）。',
                             params=[_num('num', '数量', 1, desc='选填：返回条数，>=1，默认 1（需多个请调大）')]),
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
    ],
)
