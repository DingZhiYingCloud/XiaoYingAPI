"""爬虫验证服务 - 接口文档与在线调试数据

数据与 API/apis/SpiderVerification/ 实际实现对齐（分类树 /api/spider_verification/ 为需签名）：
- sv4759：4759 蜘蛛 IP 验证 —— 判断某个 IP 是否属于搜索引擎爬虫。
后续接入更多验证线路时在 channels 追加即可。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ServiceSpec

SERVICE = ServiceSpec(
    slug='spider_verification',
    name='爬虫验证',
    prefix='/api/spider_verification/',
    summary='识别自动化/爬虫环境：验证指定 IP 是否属于搜索引擎爬虫。当前接入 4759 验证线路。',
    channels=[
        ChannelSpec(
            slug='sv4759',
            name='4759 蜘蛛 IP 验证',
            provider='4759 蜘蛛/爬虫 IP 库',
            auth_note='auth',
            note='只读查询接口：提交一个 IP，服务端查证其是否为搜索引擎（如百度/谷歌等）爬虫来源。',
            endpoints=[
                EndpointSpec('verify', '验证 IP 是否爬虫', 'GET', '/api/spider_verification/sv4759/verify',
                             summary='验证给定 IP 是否为搜索引擎爬虫，返回识别结论与类型信息。',
                             params=[
                                 ParamSpec('ip', '待验证 IP', kind='text', required=True,
                                           placeholder='如 66.249.65.205（Google 爬虫）',
                                           desc='必填：合法的 IPv4 或 IPv6 地址'),
                             ],
                             notes=['GET 查询接口；本服务需项目签名。',
                                    '对外部服务查询耗时可能较长，属正常；接口返回 data 为爬虫验证结果（含是否为爬虫及来源类型，以实际返回为准）。']),
            ],
        ),
    ],
)
