"""用户中心服务 - 接口文档与在线调试数据

数据与 API/apis/user_center/ 实际实现对齐（分类树 /api/user_center/ 需项目签名）：
- users：账号体系（注册/登录/Token/两步注册验证）；
- projects：接入项目自身信息。
说明：本文档面向「接入项目开发者」；管理后台能力不在此暴露。
除标注「公开」的接口外，全部需要项目签名；返回的 token 绑定调用它的接入项目。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ServiceSpec

_TOKEN_DESC = '必填：用户在该项目下持有的登录 Token（login 成功返回）'


def _token():
    return ParamSpec('token', '用户 Token', kind='password', required=True, desc=_TOKEN_DESC)


SERVICE = ServiceSpec(
    slug='user_center',
    name='用户中心',
    prefix='/api/user_center/',
    summary='统一账号中心（UAC）：全局用户池，多方式注册/登录、Token 签发与验证、两步注册邮箱/手机号校验。',
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
                             notes=['返回 data={methods:[email,phone], username:true}；客户端先查此接口再渲染表单。']),
                EndpointSpec('register', '注册', 'POST', '/api/user_center/users/register',
                             summary='注册：username+password 直接建号；email 或 phone+password 走两步注册（先发验证码）。',
                             params=[
                                 ParamSpec('username', '用户名', kind='text',
                                           desc='提供 username+password → 直接注册成功'),
                                 ParamSpec('email', '邮箱', kind='email',
                                           desc='提供 email → 两步注册第一步，需再验证邮箱'),
                                 ParamSpec('phone', '手机号', kind='text', placeholder='13800138000',
                                           desc='提供 phone → 两步注册第一步，需再验证手机号'),
                                 ParamSpec('password', '密码', kind='password', required=True),
                             ],
                             notes=['username/email/phone 按后台可用方式组合；两步注册时 data.need_verify=true。']),
                EndpointSpec('send_login_code', '发送登录验证码', 'POST', '/api/user_center/users/login/send',
                             summary='邮箱/手机号验证码登录第一步：校验已注册后发码（60 秒冷却）。',
                             params=[
                                 ParamSpec('email', '邮箱', kind='email'),
                                 ParamSpec('phone', '手机号', kind='text'),
                             ]),
                EndpointSpec('login', '登录', 'POST', '/api/user_center/users/login',
                             summary='登录：账号+密码，或邮箱/手机号+验证码；成功返回绑定项目的 Token。',
                             params=[
                                 ParamSpec('account', '账号', kind='text',
                                           desc='账号+密码登录时使用（username）'),
                                 ParamSpec('email', '邮箱', kind='email'),
                                 ParamSpec('phone', '手机号', kind='text'),
                                 ParamSpec('password', '密码', kind='password'),
                                 ParamSpec('code', '验证码', kind='text', desc='邮箱/手机号登录时用'),
                             ],
                             notes=['同一项目+凭证+IP 连续失败 5 次锁定 15 分钟（返回 20040）。']),
                EndpointSpec('send_reset_code', '发送重置密码验证码', 'POST', '/api/user_center/users/password/send',
                             summary='忘记密码第一步：校验邮箱/手机号已注册后发码（60 秒冷却）。',
                             params=[
                                 ParamSpec('email', '邮箱', kind='email'),
                                 ParamSpec('phone', '手机号', kind='text'),
                             ],
                             notes=['仅支持已绑定邮箱/手机号的账号；纯用户名账号没有可验证通道，无法自助重置。']),
                EndpointSpec('reset_password', '重置密码', 'POST', '/api/user_center/users/password/reset',
                             summary='忘记密码第二步：校验验证码通过后设置新密码。',
                             params=[
                                 ParamSpec('email', '邮箱', kind='email'),
                                 ParamSpec('phone', '手机号', kind='text'),
                                 ParamSpec('code', '验证码', kind='text', required=True),
                                 ParamSpec('password', '新密码', kind='password', required=True,
                                           desc='8-64 位，需同时包含字母和数字'),
                             ],
                             notes=['重置成功会作废该用户全部已签发 Token（所有已登录设备需重新登录）。']),
                EndpointSpec('verify_token', '验证 Token', 'POST', '/api/user_center/users/verify',
                             summary='供子项目确认用户身份：校验 token 有效性。',
                             params=[_token()],
                             notes=['成功返回 data={valid, user_id, account, username}。']),
                EndpointSpec('logout', '退出登录', 'POST', '/api/user_center/users/logout',
                             summary='删除当前项目下该 Token。', params=[_token()]),
                EndpointSpec('info', '用户信息', 'GET', '/api/user_center/users/info',
                             summary='按 token 查询用户信息。', params=[_token()]),
                EndpointSpec('verify_email', '邮箱两步验证(验证码)', 'POST', '/api/user_center/users/verify/email',
                             summary='邮箱验证码校验，通过后创建账号并发放。',
                             params=[
                                 ParamSpec('email', '邮箱', kind='email', required=True),
                                 ParamSpec('code', '验证码', kind='text', required=True),
                             ]),
                EndpointSpec('verify_email_resend', '重发验证邮件', 'POST', '/api/user_center/users/verify/email/resend',
                             summary='重发两步注册验证邮件（60 秒冷却）。',
                             params=[ParamSpec('email', '邮箱', kind='email', required=True)]),
                EndpointSpec('verify_phone', '手机号两步验证', 'POST', '/api/user_center/users/verify/phone',
                             summary='手机验证码校验，通过后创建账号并发放。',
                             params=[
                                 ParamSpec('phone', '手机号', kind='text', required=True),
                                 ParamSpec('code', '验证码', kind='text', required=True),
                             ]),
                EndpointSpec('verify_phone_send', '发送注册短信', 'POST', '/api/user_center/users/verify/phone/send',
                             summary='发送两步注册的手机短信验证码（60 秒冷却）。',
                             params=[ParamSpec('phone', '手机号', kind='text', required=True)]),
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
                             notes=['返回 HTML 结果页；在线调试会得到 HTML 原文，属正常。']),
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
                             params=[], notes=['仅需项目签名参数，无需业务参数。']),
            ],
        ),
    ],
)
