"""用户中心服务 - 接口文档与在线调试数据

数据与 API/apis/user_center/ 实际实现对齐（服务策略 /api/user_center/ 默认需签名）：
- users：账号体系（注册/登录/Token/两步注册验证）；
- projects：接入项目自身信息。
说明：本文档面向「接入项目开发者」；管理后台能力不在此暴露。
除标注「公开」的接口外，全部需要项目签名；返回的 token 绑定调用它的接入项目。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ResponseFieldSpec, ServiceSpec

_TOKEN_DESC = '必填：用户在该项目下持有的登录 Token（login 成功返回）'


def _token():
    return ParamSpec('token', '用户 Token', kind='password', required=True, desc=_TOKEN_DESC)


SERVICE = ServiceSpec(
    slug='user_center',
    name='用户中心',
    prefix='/api/user_center/',
    summary='统一账号中心（UAC）：全局用户池，多方式注册/登录、Token 签发与验证、两步注册邮箱/手机号校验。',
    keywords='用户中心API,统一认证,注册登录接口,Token验证',
    intro=[
        '用户中心是一套统一账号系统（UAC）：所有接入项目共用一个全局用户池，'
        '用户在一个项目下注册的账号，在其它项目下同样可以登录，不必每个项目各建一套账号体系。',
        '登录态用 Token 承载，Token 绑定签发它的接入项目。注册仅支持邮箱或手机号，且为两步流程——'
        '先提交凭证发验证码，校验通过后才真正创建账号，可有效防止恶意批量注册；'
        '忘记密码同样走「先发码、再校验改密」，重置成功后会作废该用户的全部 Token。',
        '除「可用注册/登录方式」与邮箱激活链接（公开 GET）外，其余接口均需项目签名。'
        '客户端建议先查注册/登录方式接口，再按返回结果渲染表单，不要在前端写死支持方式。',
    ],
    channels=[
        ChannelSpec(
            slug='users',
            name='用户账号体系',
            provider='统一账号池（Token 绑定接入项目）',
            auth_note='auth',
            note='除 methods 与邮箱激活链接(GET) 外均需项目签名。邮箱/手机号两步注册流程：先 register（仅暂存+发验证码），'
                 '再调 verify/email 或 verify/phone 校验通过后才创建账号。忘记密码流程：先调 password/send 发码，'
                 '再调 password/reset 校验通过后改密（并作废该用户全部 Token）。',
            endpoints=[
                EndpointSpec('methods', '可用注册/登录方式', 'GET', '/api/user_center/users/methods',
                             summary='返回后台启用的注册/登录方式（公开，免签名）。',
                             params=[],
                             notes=['返回 data={methods:[email,phone], username:false}；客户端先查此接口再渲染表单，'
                                    'username=false 表示"用户名+密码注册"已停用。'],
                             response_fields=[
                                 ResponseFieldSpec('methods', 'array', '后台启用的注册/登录方式列表'),
                                 ResponseFieldSpec('methods[]', 'string', '取值 email / phone'),
                                 ResponseFieldSpec('username', 'bool', '用户名+密码注册是否可用（恒为 false）'),
                             ],
                             response_example="""{
  "methods": ["email", "phone"],
  "username": false
}"""),
                EndpointSpec('register', '注册', 'POST', '/api/user_center/users/register',
                             summary='注册（只支持邮箱 / 手机号）：提交邮箱或手机号 + 密码走两步注册，先发验证码。',
                             params=[
                                 ParamSpec('username', '用户名', kind='text',
                                           desc='选填：仅用于展示，不作为注册凭证'),
                                 ParamSpec('email', '邮箱', kind='email',
                                           desc='提供 email → 两步注册第一步，需再验证邮箱'),
                                 ParamSpec('phone', '手机号', kind='text', placeholder='13800138000',
                                           desc='提供 phone → 两步注册第一步，需再验证手机号'),
                                 ParamSpec('password', '密码', kind='password', required=True),
                             ],
                             notes=['email / phone 至少提供一个；两步注册时 data.need_verify=true，'
                                    '需再调 verify/email 或 verify/phone 校验通过后才创建账号。',
                                    '只提供 username（即"用户名+密码注册"）已停用，'
                                    '返回 30001 业务规则限制。'],
                             response_fields=[
                                 ResponseFieldSpec('username', 'string', '选填：注册时提交的展示名，原样回带'),
                                 ResponseFieldSpec('email', 'string', '本次注册绑定的邮箱（提交邮箱时返回）'),
                                 ResponseFieldSpec('verify_email_sent', 'bool', '验证邮件是否发送成功'),
                                 ResponseFieldSpec('phone', 'string', '本次注册绑定的手机号（提交手机号时返回）'),
                                 ResponseFieldSpec('verify_phone_sent', 'bool', '注册短信是否发送成功'),
                                 ResponseFieldSpec('need_verify', 'bool', '恒为 true：需完成验证后才发放账号'),
                             ],
                             response_example="""{
  "email": "user@example.com",
  "verify_email_sent": true,
  "need_verify": true
}"""),
                EndpointSpec('send_login_code', '发送登录验证码', 'POST', '/api/user_center/users/login/send',
                             summary='邮箱/手机号验证码登录第一步：校验已注册后发码（60 秒冷却）。',
                             params=[
                                 ParamSpec('email', '邮箱', kind='email'),
                                 ParamSpec('phone', '手机号', kind='text'),
                             ],
                             response_note='成功时 data 为 null：接口只下发验证码，不返回业务数据。'),
                EndpointSpec('login', '登录', 'POST', '/api/user_center/users/login',
                             summary='登录：账号/邮箱/手机号+密码；或邮箱/手机号+验证码。成功返回绑定项目的 Token。',
                             params=[
                                 ParamSpec('account', '账号', kind='text',
                                           desc='账号+密码登录：系统发放的账号'),
                                 ParamSpec('email', '邮箱', kind='email',
                                           desc='邮箱+密码登录，或邮箱+code 验证码登录'),
                                 ParamSpec('phone', '手机号', kind='text',
                                           desc='手机号+密码登录，或手机号+code 验证码登录'),
                                 ParamSpec('password', '密码', kind='password',
                                           desc='不带 code 时必填：account/email/phone 任一标识 + 密码'),
                                 ParamSpec('code', '验证码', kind='text',
                                           desc='带 code 即走邮箱/手机号验证码登录（免密码）'),
                             ],
                             notes=['密码登录的标识三选一：account / email / phone（邮箱与手机号需已注册）。',
                                    '同一项目+凭证+IP 连续失败 5 次锁定 15 分钟（返回 20040）。'],
                             response_fields=[
                                 ResponseFieldSpec('user_id', 'string', '用户唯一 ID（UUID）'),
                                 ResponseFieldSpec('account', 'string', '系统分配的账号（6-12 位数字）'),
                                 ResponseFieldSpec('username', 'string', '用户名（可空）'),
                                 ResponseFieldSpec('token', 'string', '登录 Token，绑定本项目'),
                                 ResponseFieldSpec('expire_time', 'string', 'Token 过期时间（Y-m-d H:M:S）'),
                                 ResponseFieldSpec('email', 'string', '已绑定邮箱（未绑定时不返回）'),
                                 ResponseFieldSpec('phone', 'string', '已绑定手机号（未绑定时不返回）'),
                             ],
                             response_example="""{
  "user_id": "0f8a1c2d-3e4b-5a6c-7d8e-9f0a1b2c3d4e",
  "account": "123456",
  "username": "demo",
  "token": "9f2c1a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f",
  "expire_time": "2026-10-09 12:00:00",
  "email": "user@example.com"
}"""),
                EndpointSpec('send_reset_code', '发送重置密码验证码', 'POST', '/api/user_center/users/password/send',
                             summary='忘记密码第一步：校验邮箱/手机号已注册后发码（60 秒冷却）。',
                             params=[
                                 ParamSpec('email', '邮箱', kind='email'),
                                 ParamSpec('phone', '手机号', kind='text'),
                             ],
                             notes=['仅支持已绑定邮箱/手机号的账号；纯用户名账号没有可验证通道，无法自助重置。'],
                             response_note='成功时 data 为 null：接口只下发验证码，不返回业务数据。'),
                EndpointSpec('reset_password', '重置密码', 'POST', '/api/user_center/users/password/reset',
                             summary='忘记密码第二步：校验验证码通过后设置新密码。',
                             params=[
                                 ParamSpec('email', '邮箱', kind='email'),
                                 ParamSpec('phone', '手机号', kind='text'),
                                 ParamSpec('code', '验证码', kind='text', required=True),
                                 ParamSpec('password', '新密码', kind='password', required=True,
                                           desc='8-64 位，需同时包含字母和数字'),
                             ],
                             notes=['重置成功会作废该用户全部已签发 Token（所有已登录设备需重新登录）。'],
                             response_fields=[
                                 ResponseFieldSpec('user_id', 'string', '用户唯一 ID（UUID）'),
                                 ResponseFieldSpec('account', 'string', '系统分配的账号（6-12 位数字）'),
                                 ResponseFieldSpec('username', 'string', '用户名（可空）'),
                                 ResponseFieldSpec('email', 'string', '已绑定邮箱（未绑定时不返回）'),
                                 ResponseFieldSpec('phone', 'string', '已绑定手机号（未绑定时不返回）'),
                             ],
                             response_example="""{
  "user_id": "0f8a1c2d-3e4b-5a6c-7d8e-9f0a1b2c3d4e",
  "account": "123456",
  "username": "demo",
  "email": "user@example.com"
}"""),
                EndpointSpec('verify_token', '验证 Token', 'POST', '/api/user_center/users/verify',
                             summary='供子项目确认用户身份：校验 token 有效性。',
                             params=[_token()],
                             notes=['成功返回 data={valid, user_id, account, username}。'],
                             response_fields=[
                                 ResponseFieldSpec('valid', 'bool', 'Token 是否有效（成功恒为 true）'),
                                 ResponseFieldSpec('user_id', 'string', '用户唯一 ID（UUID）'),
                                 ResponseFieldSpec('account', 'string', '系统分配的账号（6-12 位数字）'),
                                 ResponseFieldSpec('username', 'string', '用户名（可空）'),
                                 ResponseFieldSpec('email', 'string', '已绑定邮箱（未绑定时不返回）'),
                                 ResponseFieldSpec('email_verified', 'bool', '邮箱是否已验证'),
                                 ResponseFieldSpec('phone', 'string', '已绑定手机号（未绑定时不返回）'),
                                 ResponseFieldSpec('phone_verified', 'bool', '手机号是否已验证'),
                             ],
                             response_example="""{
  "valid": true,
  "user_id": "0f8a1c2d-3e4b-5a6c-7d8e-9f0a1b2c3d4e",
  "account": "123456",
  "username": "demo",
  "email": "user@example.com",
  "email_verified": true
}"""),
                EndpointSpec('logout', '退出登录', 'POST', '/api/user_center/users/logout',
                             summary='删除当前项目下该 Token。', params=[_token()],
                             response_note='成功时 data 为 null：接口只返回操作结果。'),
                EndpointSpec('info', '用户信息', 'GET', '/api/user_center/users/info',
                             summary='按 token 查询用户信息。', params=[_token()],
                             response_fields=[
                                 ResponseFieldSpec('user_id', 'string', '用户唯一 ID（UUID）'),
                                 ResponseFieldSpec('account', 'string', '系统分配的账号（6-12 位数字）'),
                                 ResponseFieldSpec('username', 'string', '用户名（可空）'),
                                 ResponseFieldSpec('expire_time', 'string', 'Token 过期时间（Y-m-d H:M:S）'),
                                 ResponseFieldSpec('email', 'string', '已绑定邮箱（未绑定时不返回）'),
                                 ResponseFieldSpec('email_verified', 'bool', '邮箱是否已验证'),
                                 ResponseFieldSpec('phone', 'string', '已绑定手机号（未绑定时不返回）'),
                                 ResponseFieldSpec('phone_verified', 'bool', '手机号是否已验证'),
                             ],
                             response_example="""{
  "user_id": "0f8a1c2d-3e4b-5a6c-7d8e-9f0a1b2c3d4e",
  "account": "123456",
  "username": "demo",
  "expire_time": "2026-10-09 12:00:00",
  "email": "user@example.com",
  "email_verified": true
}"""),
                EndpointSpec('verify_email', '邮箱两步验证(验证码)', 'POST', '/api/user_center/users/verify/email',
                             summary='邮箱验证码校验，通过后创建账号并发放。',
                             params=[
                                 ParamSpec('email', '邮箱', kind='email', required=True),
                                 ParamSpec('code', '验证码', kind='text', required=True),
                             ],
                             response_fields=[
                                 ResponseFieldSpec('user_id', 'string', '用户唯一 ID（UUID）'),
                                 ResponseFieldSpec('account', 'string', '系统分配的账号（6-12 位数字）'),
                                 ResponseFieldSpec('username', 'string', '用户名（可空）'),
                                 ResponseFieldSpec('email', 'string', '本次注册绑定的邮箱'),
                                 ResponseFieldSpec('email_verified', 'bool', '邮箱是否已验证'),
                             ],
                             response_example="""{
  "user_id": "0f8a1c2d-3e4b-5a6c-7d8e-9f0a1b2c3d4e",
  "account": "123456",
  "username": "demo",
  "email": "user@example.com",
  "email_verified": true
}"""),
                EndpointSpec('verify_email_resend', '重发验证邮件', 'POST', '/api/user_center/users/verify/email/resend',
                             summary='重发两步注册验证邮件（60 秒冷却）。',
                             params=[ParamSpec('email', '邮箱', kind='email', required=True)],
                             response_note='成功时 data 为 null：接口只重发验证邮件。'),
                EndpointSpec('verify_phone', '手机号两步验证', 'POST', '/api/user_center/users/verify/phone',
                             summary='手机验证码校验，通过后创建账号并发放。',
                             params=[
                                 ParamSpec('phone', '手机号', kind='text', required=True),
                                 ParamSpec('code', '验证码', kind='text', required=True),
                             ],
                             response_fields=[
                                 ResponseFieldSpec('user_id', 'string', '用户唯一 ID（UUID）'),
                                 ResponseFieldSpec('account', 'string', '系统分配的账号（6-12 位数字）'),
                                 ResponseFieldSpec('username', 'string', '用户名（可空）'),
                                 ResponseFieldSpec('phone', 'string', '本次注册绑定的手机号'),
                                 ResponseFieldSpec('phone_verified', 'bool', '手机号是否已验证'),
                             ],
                             response_example="""{
  "user_id": "0f8a1c2d-3e4b-5a6c-7d8e-9f0a1b2c3d4e",
  "account": "123456",
  "username": "demo",
  "phone": "13800138000",
  "phone_verified": true
}"""),
                EndpointSpec('verify_phone_send', '发送注册短信', 'POST', '/api/user_center/users/verify/phone/send',
                             summary='发送两步注册的手机短信验证码（60 秒冷却）。',
                             params=[ParamSpec('phone', '手机号', kind='text', required=True)],
                             response_note='成功时 data 为 null：接口只重发注册短信。'),
            ],
        ),
        ChannelSpec(
            slug='email_activation',
            name='邮箱激活链接（公开 GET）',
            provider='邮件内链接专用（浏览器访问）',
            auth_note='open',
            note='邮箱激活链接：用户在邮件里点击的链接，GET 免签名，返回友好 HTML 结果页（非 JSON）。',
            endpoints=[
                EndpointSpec('activate', '邮箱激活链接', 'GET', '/api/user_center/users/verify/email',
                             summary='浏览器打开邮件内激活链接，校验通过后创建账号并发放。',
                             params=[ParamSpec('token', '激活令牌', kind='text',
                                               desc='链接中的 token（系统生成），正常由用户点邮件链接触发')],
                             notes=['返回 HTML 结果页；在线调试会得到 HTML 原文，属正常。'],
                             response_note='成功/失败均返回 HTML 结果页（非 JSON），data 不适用；调试面板显示 HTML 原文属正常。'),
            ],
        ),
        ChannelSpec(
            slug='projects',
            name='接入项目信息',
            provider='项目自身配置查询',
            auth_note='auth',
            note='查询调用方（签名所属项目）自身信息，用于核对配置。',
            endpoints=[
                EndpointSpec('project_info', '项目信息', 'GET', '/api/user_center/projects/info',
                             summary='返回当前接入项目配置（含 Token 默认有效期等）。',
                             params=[], notes=['仅需项目签名参数，无需业务参数。'],
                             response_fields=[
                                 ResponseFieldSpec('project_id', 'string', '项目唯一 ID（UUID）'),
                                 ResponseFieldSpec('name', 'string', '项目名称'),
                                 ResponseFieldSpec('app_id', 'string', 'APPID（公开标识）'),
                                 ResponseFieldSpec('token_expire_days', 'int', 'Token 默认有效期（天）'),
                                 ResponseFieldSpec('status', 'bool', '项目启用状态'),
                             ],
                             response_example="""{
  "project_id": "1f2e3d4c-5b6a-7c8d-9e0f-1a2b3c4d5e6f",
  "name": "Demo Project",
  "app_id": "app_0123456789abcdef0123456789abcd",
  "token_expire_days": 7,
  "status": true
}"""),
            ],
        ),
    ],
)
