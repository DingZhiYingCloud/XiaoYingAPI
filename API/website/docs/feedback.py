"""问题反馈服务 - 接口文档与在线调试数据

数据与 API/apis/feedback/ 实际实现对齐（分类树 /api/feedback/ 为需签名）：
- 反馈中心：按接入项目隔离的反馈 + 评论树（类似项目 Issues）。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ServiceSpec

_STATUS_OPTS = [
    {'value': '', 'label': '全部（不传）'},
    {'value': 'pending', 'label': 'pending（待处理）'},
    {'value': 'processing', 'label': 'processing（处理中）'},
    {'value': 'resolved', 'label': 'resolved（已解决）'},
    {'value': 'closed', 'label': 'closed（已关闭）'},
]

_TOKEN_HINT = '用户登录 Token（用户中心签发）：create/reply 用它校验反馈人真实身份，子项目无法伪造用户。'


def _page_params(page_size_default=20, page_size_desc='每页条数（最大 100）'):
    return [
        ParamSpec('page', '页码', kind='number', default='1', desc='选填：默认 1'),
        ParamSpec('page_size', '每页条数', kind='number', default=str(page_size_default),
                  desc=f'选填：{page_size_desc}'),
    ]


SERVICE = ServiceSpec(
    slug='feedback',
    name='问题反馈',
    prefix='/api/feedback/',
    summary='问题反馈中心：提交反馈、追加/回复评论、查看项目内反馈与评论树。数据按接入项目隔离。',
    channels=[
        ChannelSpec(
            slug='center',
            name='问题反馈中心',
            provider='站内反馈库（按项目隔离）',
            auth_note='auth',
            note='全部接口需项目签名；create/reply 额外校验用户登录 Token（反馈人身份以此为准）。同项目内所有用户可见全部反馈与评论。',
            endpoints=[
                EndpointSpec('create', '提交反馈', 'POST', '/api/feedback/create',
                             summary='新建一条反馈（title/content 必填），反馈人身份由 token 校验。',
                             params=[
                                 ParamSpec('title', '标题', kind='text', required=True,
                                           placeholder='反馈标题', desc='必填'),
                                 ParamSpec('content', '内容', kind='textarea', required=True,
                                           placeholder='详细描述问题…', desc='必填'),
                                 ParamSpec('token', '用户 Token', kind='text', required=True,
                                           placeholder='用户中心登录后获取', desc=_TOKEN_HINT),
                             ]),
                EndpointSpec('reply', '追加 / 回复评论', 'POST', '/api/feedback/reply',
                             summary='给反馈追加评论；parent_id 为空=一级评论，非空=回复指定评论（支持嵌套）。',
                             params=[
                                 ParamSpec('feedback_id', '反馈 ID', kind='text', required=True,
                                           desc='必填：反馈编号（create 返回的 feedback_id）'),
                                 ParamSpec('content', '评论内容', kind='textarea', required=True,
                                           placeholder='评论内容…', desc='必填'),
                                 ParamSpec('parent_id', '上级评论 ID', kind='text',
                                           desc='选填：为空=直接评论反馈；非空=回复该评论（须属于同一反馈）'),
                                 ParamSpec('token', '用户 Token', kind='text', required=True,
                                           placeholder='用户中心登录后获取', desc=_TOKEN_HINT),
                             ]),
                EndpointSpec('list', '反馈列表', 'GET', '/api/feedback/list',
                             summary='当前项目内的反馈列表，支持按状态筛选。',
                             params=[
                                 ParamSpec('status', '状态', kind='select', options=_STATUS_OPTS,
                                           desc='选填：pending/processing/resolved/closed'),
                             ] + _page_params(10, '每页条数')),
                EndpointSpec('detail', '反馈详情+评论树', 'GET', '/api/feedback/detail',
                             summary='单条反馈详情：一级评论分页返回，每条内嵌二级评论首页（默认 5 条）。',
                             params=[
                                 ParamSpec('feedback_id', '反馈 ID', kind='text', required=True,
                                           desc='必填'),
                             ] + _page_params(20, '每页条数（最大 100）')),
                EndpointSpec('replies', '二级评论列表', 'GET', '/api/feedback/replies',
                             summary='某条评论的全部子孙回复（扁平、分页、不分层级），防海量评论撑爆响应。',
                             params=[
                                 ParamSpec('feedback_id', '反馈 ID', kind='text', required=True,
                                           desc='必填'),
                                 ParamSpec('parent_id', '上级评论 ID', kind='text', required=True,
                                           desc='必填：被查看的评论 ID'),
                             ] + _page_params(20, '每页条数（最大 100）')),
            ],
        ),
    ],
)
