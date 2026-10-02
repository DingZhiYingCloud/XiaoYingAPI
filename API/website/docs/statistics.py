"""API 调用统计服务 - 接口文档与在线调试数据

数据与 API/apis/statistics/ 实际实现对齐（服务策略 /api/statistics/ 为开放，无需签名）：
- statistics：公开口径的调用量查询（仅调用次数），供任何人在文档中心或第三方页面引用。
超管看板的完整统计（项目 / 失败率 / 耗时）不在本服务暴露，见 /console/stats/。
"""
from .schema import (ChannelSpec, EndpointSpec, ParamSpec, ResponseFieldSpec,
                     ServiceSpec)

SERVICE = ServiceSpec(
    slug='statistics',
    name='调用统计',
    prefix='/api/statistics/',
    summary='公开查询 API 调用量：某个接口被调用了多少次、各服务调用量排行。仅公开调用次数，不含项目与耗时。',
    keywords='API调用统计,接口调用量查询',
    intro=[
        '调用统计服务对外公开每个接口的调用量：可以查某个接口被调用了多少次（累计与今日），'
        '也可以查各服务的调用量排行，适合做公开的运营数据展示，或写入自己的监控面板。',
        '这是本站唯一无需签名的开放服务，未登录也能直接调用。统计口径只包含调用次数，'
        '不包含调用方项目、失败率与耗时等敏感信息。',
        '数据按天预聚合，写入最多延迟数秒，因此刚发生的调用可能不会立刻体现在结果里。',
    ],
    channels=[
        ChannelSpec(
            slug='statistics',
            name='调用量查询',
            provider='小影API 内置调用统计（按天预聚合）',
            auth_note='open',
            note='调用量为公开信息，接口开放（免签名）。数据按天聚合，写入最多延迟数秒；'
                 '统计范围仅 /api/ 业务接口，认证被拒与未匹配路由同样计入。',
            endpoints=[
                EndpointSpec('api_calls', '查询单个接口调用量', 'GET', '/api/statistics/api_calls',
                             summary='返回某个接口的累计调用次数与今日调用次数。',
                             params=[
                                 ParamSpec('path', '接口路径', kind='text', required=True,
                                           placeholder='/api/email/v1/send',
                                           desc='必填：文档中心已登记的接口路径；带路径参数的接口按文档写法传占位符，'
                                                '如 /api/music/xiaoying/musics/<uuid>'),
                             ],
                             notes=['公开接口，无需项目签名。',
                                    'path 未登记时返回 code=20003；未传时返回 code=20001。'],
                             response_fields=[
                                 ResponseFieldSpec('path', 'string', '查询的接口路径'),
                                 ResponseFieldSpec('total_calls', 'int', '累计调用次数'),
                                 ResponseFieldSpec('today_calls', 'int', '今日调用次数'),
                             ],
                             response_example='''{
  "path": "/api/email/v1/send",
  "total_calls": 12345,
  "today_calls": 67
}'''),
                EndpointSpec('services', '各服务调用量排行', 'GET', '/api/statistics/services',
                             summary='返回各服务的累计与今日调用次数，按累计调用量降序。',
                             notes=['公开接口，无需项目签名。'],
                             response_fields=[
                                 ResponseFieldSpec('services', 'array', '各服务调用量列表（按累计降序）'),
                                 ResponseFieldSpec('services[].service', 'string', '服务前缀（如 /api/email/）'),
                                 ResponseFieldSpec('services[].name', 'string', '服务名称'),
                                 ResponseFieldSpec('services[].total_calls', 'int', '累计调用次数'),
                                 ResponseFieldSpec('services[].today_calls', 'int', '今日调用次数'),
                             ],
                             response_example='''{
  "services": [
    {"service": "/api/email/", "name": "邮箱服务", "total_calls": 12345, "today_calls": 67}
  ]
}'''),
            ],
        ),
    ],
)
