"""邮箱服务 - 接口文档与在线调试数据（首个接入服务）

数据与 API/apis/emails/ 与 API/apis/VMEmail_mailcx/ 实际实现对齐：
- 邮箱v1（发送邮件）：POST /api/email/v1/send（默认需签名）
- VMEmail(mail.cx)（mail.cx 临时邮箱）：GET domains/emails/email_detail、POST generate（需签名）
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ResponseFieldSpec, ServiceSpec

SERVICE = ServiceSpec(
    slug='email',
    name='邮箱服务',
    prefix='/api/email/',
    summary='邮件发送与虚拟邮箱收发能力。当前接入 2 条线路，后续可继续扩展更多平台/线路。',
    keywords='临时邮箱API,虚拟邮箱接口,邮箱验证码API,邮件发送接口',
    intro=[
        '邮箱服务把「发信」和「收信」拆成两条线路：邮箱 v1 用平台邮箱发送业务邮件，适合验证码、通知、'
        '告警等场景；VMEmail(mail.cx) 提供临时邮箱（虚拟邮箱）能力，可随机生成一个邮箱地址'
        '并接收来信，常用于注册验证、接口联调、自动化测试等需要一次性邮箱的场合。',
        '两条线路均需项目签名。',
        '临时邮箱的收件是长轮询：没有新邮件时请求会挂起约 25 秒后返回空列表，属正常行为，'
        '请不要按短超时判定为失败；邮件有留存期限，重要内容请及时取回。',
    ],
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
                        '发送失败归为外部服务错误。',
                    ],
                    # data 由本接口显式拼装，结构固定，写出字段表
                    response_fields=[
                        ResponseFieldSpec('subject', 'string', '邮件标题'),
                        ResponseFieldSpec('recipients', 'array', '收件人邮箱列表'),
                        ResponseFieldSpec('count', 'int', '收件人数量'),
                    ],
                    response_example='{"subject": "Welcome", "recipients": ["a@example.com", "b@example.com"], "count": 2}',
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
                    # data 是从上游 config 里抽出的域名字符串数组（无字段名），用说明而非字段表
                    response_note='data 为可用后缀域名组成的字符串数组；上游异常时回退为内置默认域名。',
                    response_example='["ddker.com", "9k3r.com", "uqu.me"]',
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
                    notes=['请求体为 application/x-www-form-urlencoded 表单。'],
                    response_fields=[
                        ResponseFieldSpec('address', 'string', '临时邮箱地址'),
                        ResponseFieldSpec('domain', 'string', '后缀域名'),
                        ResponseFieldSpec('client_id', 'string', '客户端标识，查询邮件时回传'),
                    ],
                    response_example='{"address": "abc123@uqu.me", "domain": "uqu.me", "client_id": "0f8b2e1c-3a4d-4f6e-9c12-7d5a8b3e2f01"}',
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
                           '完整正文用列表里的 id 查「获取邮件详情」。'],
                    # data 直接来自上游 mail.cx，字段由上游决定，不逐个承诺
                    response_note='data 为上游 mail.cx 的邮件摘要列表，每项含 id / from_name / from_email / '
                                  'subject / preview_text / preview_status / size / created_at 等字段，以实际返回为准。',
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
                    notes=['邮件不存在（或已过期，保留约 1 小时）返回 20030。'],
                    # data 为上游邮件详情原始 JSON，字段由上游定义
                    response_note='data 为上游 mail.cx 返回的邮件详情原始 JSON，含 id / from / from_email / '
                                  'from_name / to / subject / text_body / html_body / attachments / date / '
                                  'created_at 等字段，以实际返回为准。',
                ),
            ],
        ),
    ],
)
