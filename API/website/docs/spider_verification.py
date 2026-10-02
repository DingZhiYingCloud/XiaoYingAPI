"""爬虫验证服务 - 接口文档与在线调试数据

数据与 API/apis/SpiderVerification/ 实际实现对齐（服务策略 /api/spider_verification/ 默认需签名）：
- sv4759：4759 蜘蛛 IP 验证 —— 判断某个 IP 是否属于搜索引擎爬虫。
后续接入更多验证线路时在 channels 追加即可。
"""
from .schema import (ChannelSpec, EndpointSpec, ParamSpec, ResponseFieldSpec,
                     ServiceSpec)

SERVICE = ServiceSpec(
    slug='spider_verification',
    name='爬虫验证',
    prefix='/api/spider_verification/',
    summary='识别自动化/爬虫环境：验证指定 IP 是否属于搜索引擎爬虫。当前接入 4759 验证线路。',
    keywords='爬虫验证API,环境检测接口,自动化检测',
    intro=[
        '爬虫验证服务用于判断一个 IP 是否来自搜索引擎爬虫：提交 IP，服务端查询蜘蛛 IP 库并返回识别结论'
        '与来源类型，可用于访问日志分析、来源统计，或做「真爬虫才给收录内容」这类判断的辅助依据。',
        '只读查询接口，支持 IPv4 与 IPv6。查询需访问外部 IP 库，单次耗时可能偏长，属正常现象。',
        '本服务需项目签名。识别结果依赖第三方 IP 库的覆盖范围，建议作为参考而非唯一判定条件。',
    ],
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
                                    '对外部服务查询耗时可能较长，属正常。'],
                             response_fields=[
                                 ResponseFieldSpec('ip', 'string', '被验证的 IP'),
                                 ResponseFieldSpec('is_spider', 'bool', '是否为搜索引擎爬虫'),
                                 ResponseFieldSpec('spider_type', 'string', '蜘蛛类型；非蜘蛛为「非蜘蛛」'),
                                 ResponseFieldSpec('ptr_domain', 'string', '反向解析域名（PTR）'),
                                 ResponseFieldSpec('matched_domain', 'string', '匹配的官方域名后缀；未匹配为「未匹配」'),
                                 ResponseFieldSpec('verify_method', 'string', '验证方式'),
                                 ResponseFieldSpec('result', 'string', '结果描述（如「查询成功」）'),
                             ],
                             response_example='''{
  "ip": "66.249.65.205",
  "is_spider": true,
  "spider_type": "谷歌蜘蛛",
  "ptr_domain": "crawl-66-249-65-205.googlebot.com",
  "matched_domain": "googlebot.com",
  "verify_method": "反向DNS验证",
  "result": "查询成功"
}'''),
            ],
        ),
    ],
)
