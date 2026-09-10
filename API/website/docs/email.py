"""邮箱服务 - 接口文档与在线调试数据（首个接入服务）

数据与 API/apis/emails/ 实际实现对齐：
- 邮箱v1（发送邮件）：POST /api/email/v1/send（分类树中为 inherit→需签名）
- VMEmail（minmail.app 临时邮箱）：POST generate / GET emails（分类树显式 open，免签名）
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ServiceSpec

SERVICE = ServiceSpec(
    slug='email',
    name='邮箱服务',
    prefix='/api/email/',
    summary='邮件发送与虚拟邮箱收发能力。当前接入 2 条线路，后续可继续扩展更多平台/线路。',
    channels=[
        ChannelSpec(
            slug='v1',
            name='邮箱 v1',
            provider='发送邮件（默认线路）',
            auth_note='auth',
            note='发送文本/HTML 邮件，支持多个收件人。需项目签名调用。',
            endpoints=[
                EndpointSpec(
                    slug='send',
                    name='发送邮件',
                    method='POST',
                    path='/api/email/v1/send',
                    summary='发送一封邮件，可指定多个收件人。',
                    params=[
                        ParamSpec('subject', '邮件标题', kind='text', required=True,
                                  placeholder='邮件标题', desc='邮件标题（必填）'),
                        ParamSpec('body', '邮件正文', kind='textarea', required=True,
                                  placeholder='邮件正文内容', desc='邮件正文内容（必填）'),
                        ParamSpec('recipients', '收件人邮箱', kind='textarea', required=True,
                                  repeatable=True,
                                  repeat_hint='多个邮箱用逗号或换行分隔，也可通过同一字段多次传递',
                                  placeholder='a@example.com\nb@example.com',
                                  desc='收件人邮箱（必填，支持多个）'),
                    ],
                    notes=[
                        '收件人支持两种写法：同一字段重复传多次，或单个字段内用逗号分隔。',
                        '成功返回 data 含 subject / recipients / count；发送失败归为外部服务错误。',
                    ],
                ),
            ],
        ),
        ChannelSpec(
            slug='vmemail',
            name='VMEmail',
            provider='VMEmail（minmail.app）临时邮箱',
            auth_note='open',
            note='生成/复用临时邮箱并收取邮件；开放调用（免签名）。',
            endpoints=[
                EndpointSpec(
                    slug='generate',
                    name='生成/获取临时邮箱',
                    method='POST',
                    path='/api/email/VMEmail/minmail/generate',
                    summary='生成一个全新临时邮箱，或凭 visitor_id 复用已有邮箱。',
                    params=[
                        ParamSpec('visitor_id', '访客标识', kind='text',
                                  placeholder='UUID，如 3fa85f64-...',
                                  desc='选填：不传则随机生成；传入已有值可复用有效期内邮箱'),
                        ParamSpec('expire', '过期时间(分钟)', kind='number', default='1440',
                                  placeholder='1440',
                                  desc='选填：邮箱有效分钟数，正整数，默认 1440（24 小时）'),
                        ParamSpec('refresh', '强制新建', kind='select', default='false',
                                  options=[{'value': 'false', 'label': 'false（默认复用）'},
                                           {'value': 'true', 'label': 'true（丢弃原邮箱新建）'}],
                                  desc='选填：true 时强制生成新邮箱，原邮箱及其邮件将被丢弃'),
                    ],
                    notes=['generate 返回的 visitor_id 请妥善保存，查询邮件时需复用。'],
                ),
                EndpointSpec(
                    slug='emails',
                    name='获取邮件列表',
                    method='GET',
                    path='/api/email/VMEmail/minmail/emails',
                    summary='查询当前临时邮箱收到的邮件列表。',
                    params=[
                        ParamSpec('visitor_id', '访客标识', kind='text', required=True,
                                  placeholder='generate 返回的 UUID',
                                  desc='必填：generate 接口返回的 visitor_id'),
                    ],
                ),
            ],
        ),
    ],
)
