"""API 调用统计服务 - 接口文档与在线调试数据

数据与 API/apis/statistics/ 实际实现对齐（分类树 /api/statistics/ 为开放，无需签名）：
- statistics：公开口径的调用量查询（仅调用次数），供任何人在文档中心或第三方页面引用。
超管看板的完整统计（项目 / 失败率 / 耗时）不在本服务暴露，见 /console/stats/。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ServiceSpec

SERVICE = ServiceSpec(
    slug='statistics',
    name='调用统计',
    prefix='/api/statistics/',
    summary='公开查询 API 调用量：某个接口被调用了多少次、各服务调用量排行。仅公开调用次数，不含项目与耗时。',
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
                                    '返回 data = {path, total_calls, today_calls}。',
                                    'path 未登记时返回 code=20003；未传时返回 code=20001。']),
                EndpointSpec('services', '各服务调用量排行', 'GET', '/api/statistics/services',
                             summary='返回各服务的累计与今日调用次数，按累计调用量降序。',
                             notes=['公开接口，无需项目签名。',
                                    '返回 data = {services: [{service, name, total_calls, today_calls}, ...]}。']),
            ],
        ),
    ],
)
