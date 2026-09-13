"""邮箱服务 - 接口文档与在线调试数据（首个接入服务）

数据与 API/apis/emails/ 实际实现对齐：
- 邮箱v1（发送邮件）：POST /api/email/v1/send（分类树中为 inherit→需签名）
- VMEmail（minmail.app 临时邮箱）：POST generate / GET emails（分类树显式 open，免签名）
- VMEmail(mail.cx)（mail.cx 临时邮箱）：GET domains/emails/email_detail、POST generate（需签名）
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ServiceSpec

SERVICE = ServiceSpec(
    slug='email',
    name='邮箱服务',
    prefix='/api/email/',
    summary='邮件发送与虚拟邮箱收发能力。当前接入 3 条线路，后续可继续扩展更多平台/线路。',
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
        ChannelSpec(
            slug='mailcx',
            name='VMEmail(mail.cx)',
            provider='VMEmail（mail.cx）临时邮箱（仅收信）',
            auth_note='auth',
            note='mail.cx 临时邮箱：地址本地随机生成、无需注册，地址即唯一标识（邮件保留约 1 小时）；'
                 '服务端不保存会话，查询邮件需回传 address。需项目签名调用。',
            endpoints=[
                EndpointSpec(
                    slug='domains',
                    name='获取可用域名列表',
                    method='GET',
                    path='/api/VMEmail_mailcx/domains',
                    summary='获取当前可用的全部后缀域名，用于生成邮箱时指定 domain。',
                    params=[],
                    notes=['返回 data 为域名字符串数组，如 ["ddker.com","9k3r.com","uqu.me"]；'
                           '上游异常时返回内置默认域名，保证可用。'],
                ),
                EndpointSpec(
                    slug='generate',
                    name='生成临时邮箱',
                    method='POST',
                    path='/api/VMEmail_mailcx/generate',
                    summary='生成一个临时邮箱地址（仅收信），返回邮箱地址与客户端标识。',
                    params=[
                        ParamSpec('domain', '后缀域名', kind='select', required=False, default='uqu.me',
                                  desc='选填：指定后缀域名，缺省使用默认域名 uqu.me',
                                  options=[{'value': 'uqu.me', 'label': 'uqu.me（默认）'},
                                           {'value': 'ddker.com', 'label': 'ddker.com'},
                                           {'value': '9k3r.com', 'label': '9k3r.com'}]),
                        ParamSpec('client_id', '客户端标识', kind='text', required=False,
                                  placeholder='留空自动生成 UUID',
                                  desc='选填：客户端标识（X-Client-ID）；不传由服务端随机生成，传已有值可复用同一身份'),
                    ],
                    notes=['请求体为 application/x-www-form-urlencoded 表单。',
                           '返回 data：{address, domain, client_id}；address 为邮箱地址，'
                           'client_id 建议保存并在后续查询邮件时回传。'],
                ),
                EndpointSpec(
                    slug='emails',
                    name='获取邮件列表',
                    method='GET',
                    path='/api/VMEmail_mailcx/emails',
                    summary='拉取指定邮箱的邮件摘要列表（长轮询，无新邮件时挂起约 25 秒后返回空列表）。',
                    params=[
                        ParamSpec('address', '邮箱地址', kind='email', required=True,
                                  placeholder='如 abc123@uqu.me',
                                  desc='必填：邮箱地址，来自「生成临时邮箱」的返回值'),
                        ParamSpec('since', '增量时间戳(秒)', kind='number', required=False,
                                  placeholder='如 1725000000',
                                  desc='选填：非负整数时间戳（秒）；不传返回当前全部邮件，'
                                       '传入后仅返回该时间之后的新邮件'),
                        ParamSpec('client_id', '客户端标识', kind='text', required=False,
                                  desc='选填：与生成邮箱时的 client_id 保持一致'),
                    ],
                    notes=['上游为长轮询：无新邮件时会挂起约 25 秒后返回空列表，客户端 HTTP 超时应大于 35 秒。',
                           '返回 data 为邮件摘要数组（id / from_name / from_email / subject / '
                           'preview_text / preview_status / size / created_at）；完整正文用 id 查「获取邮件详情」。'],
                ),
                EndpointSpec(
                    slug='detail',
                    name='获取邮件详情',
                    method='GET',
                    path='/api/VMEmail_mailcx/email_detail',
                    summary='按邮件 id 获取完整详情（含完整正文与附件）。',
                    params=[
                        ParamSpec('email_id', '邮件 ID', kind='text', required=True,
                                  placeholder='来自邮件列表的 id 字段',
                                  desc='必填：邮件唯一标识（长度上限 128）'),
                        ParamSpec('client_id', '客户端标识', kind='text', required=False,
                                  desc='选填：与生成邮箱时的 client_id 保持一致'),
                    ],
                    notes=['返回 data 含 id / from / from_email / from_name / to / subject / text_body / '
                           'html_body / attachments / date / created_at，以实际返回为准。',
                           '邮件不存在（或已过期，保留约 1 小时）返回 20030。'],
                ),
            ],
        ),
    ],
)
