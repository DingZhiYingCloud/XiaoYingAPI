"""消息推送服务 - 接口文档与在线调试数据

数据与 API/apis/push/serverchan/ 实际实现对齐：POST /api/push/serverchan/send（默认需签名）。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ResponseFieldSpec, ServiceSpec

# Server酱 channel 参数取值（来源：登录 Server酱 后「Key&API」页的「API 详细说明」）
# 空值 = 不指定，使用 Server酱 后台「通道配置」页设置的默认通道。
CHANNEL_OPTIONS = [
    {'value': '', 'label': '不指定（用后台设置的默认通道）'},
    {'value': '9', 'label': '方糖服务号（微信）'},
    {'value': '66', 'label': '企业微信应用消息'},
    {'value': '1', 'label': '企业微信群机器人'},
    {'value': '2', 'label': '钉钉群机器人'},
    {'value': '3', 'label': '飞书群机器人'},
    {'value': '8', 'label': 'Bark iOS'},
    {'value': '18', 'label': 'PushDeer'},
    {'value': '98', 'label': '官方 Android 版·β'},
    {'value': '0', 'label': '测试号'},
    {'value': '88', 'label': '自定义 Webhook'},
]

SERVICE = ServiceSpec(
    slug='push',
    name='消息推送服务',
    prefix='/api/push/',
    summary='把消息推送到手机的通知服务。当前接入 Server酱 1 条线路，后续可继续扩展更多推送平台/线路。',
    keywords='消息推送API,微信推送接口,Server酱API,ServerChan,服务器告警推送,通知接口',
    intro=[
        '消息推送服务把「服务器 / 脚本 / 设备上发生的事」发送到手机，适合告警、任务完成通知、'
        '定时任务结果汇总等场景。当前接入 Server酱（sct.ftqq.com）一条线路：调用本服务的发送接口，'
        '消息经由 Server酱 推送到你手机。',
        '**消息实际推送到哪个通道**（微信服务号、企业微信应用消息、企业微信/钉钉/飞书群机器人、Bark、'
        'PushDeer 或自定义 Webhook）由 Server酱 后台的通道配置决定 —— 换通道不用改调用代码。',
        '**SendKey 由服务端托管**：在超管控制台「账号管理」里新增一个平台为「Server酱」的账号，'
        '把 SendKey 填进「登录凭据」字段即可（凭据加密落库、页面不回显）。调用方无需、也不应传递 SendKey。',
        '本服务接口需项目签名调用；每次推送都会在控制台「推送日志」留痕（成功与失败都记）。',
    ],
    channels=[
        ChannelSpec(
            slug='serverchan',
            name='Server酱',
            provider='Server酱（sct.ftqq.com）微信推送',
            auth_note='auth',
            note='通过 Server酱 的 SendKey 推送消息；SendKey 由服务端托管（控制台「账号管理」）。需项目签名调用。',
            endpoints=[
                EndpointSpec(
                    slug='send',
                    name='发送消息',
                    method='POST',
                    path='/api/push/serverchan/send',
                    summary='发送一条消息，经由 Server酱 推送到微信（或你在 Server酱 后台配置的其它通道）。',
                    params=[
                        ParamSpec('title', '消息标题', kind='text', required=True,
                                  placeholder='如 服务器磁盘告警',
                                  desc='必填：消息标题，最长 32 个字符，不能包含换行'),
                        ParamSpec('desp', '消息正文', kind='textarea', required=False,
                                  placeholder='支持 Markdown 的正文，如：\n## 告警详情\n\n磁盘使用率 **92%**，请及时清理。',
                                  desc='选填：消息正文，支持 Markdown（订阅会员的卡片可显示全文）'),
                        ParamSpec('channel', '指定通道', kind='select', required=False, default='',
                                  desc='选填：本次推送使用的消息通道；不选则用 Server酱 后台「通道配置」页设置的默认通道。'
                                       '需要同时推送到两个通道时，可直接传组合值用 | 分隔（如 9|66）。'
                                       '通道值：方糖服务号=9、企业微信应用消息=66、企业微信群机器人=1、'
                                       '钉钉群机器人=2、飞书群机器人=3、Bark iOS=8、PushDeer=18、'
                                       '官方 Android 版=98、测试号=0、自定义=88。',
                                  options=CHANNEL_OPTIONS),
                        ParamSpec('short', '短链标题', kind='text', required=False,
                                  placeholder='留空则不发送短链',
                                  desc='选填：卡片消息的短链标题'),
                        ParamSpec('tags', '标签', kind='text', required=False,
                                  placeholder='多个用 | 分隔',
                                  desc='选填：消息标签，多个用 | 分隔'),
                        ParamSpec('openid', '企微成员', kind='text', required=False,
                                  placeholder='多个用 | 分隔',
                                  desc='选填：企业微信通道抄送的成员 openid，多个用 | 分隔'),
                        ParamSpec('noip', '隐藏调用 IP', kind='select', required=False, default='',
                                  desc='选填：是否隐藏本次调用的来源 IP；选「隐藏」后 Server酱 不记录调用方 IP。',
                                  options=[{'value': '', 'label': '显示调用 IP（默认）'},
                                           {'value': '1', 'label': '隐藏调用 IP'}]),
                        ParamSpec('encrypt_password', '阅读密码', kind='password', required=False,
                                  placeholder='留空则不加密',
                                  desc='选填：填了即对 desp 做端对端加密后再推送，消息在 Server酱 / 微信 侧都是密文；'
                                       '收件人需在消息详情页输入同一密码才能查看内容。密码请另行告知收件人，平台不保存。'),
                    ],
                    notes=[
                        'title 最长 32 个字符且不能含换行；desp 支持 Markdown。',
                        'SendKey 由服务端托管（控制台「账号管理」→ 平台选「Server酱」、凭据填 SendKey），调用方不传。',
                        'Server酱 免费账号限制每日 5 条、每分钟 50 条，超限时上游会返回错误码（本接口按外部服务错误返回）。',
                        '上游返回非 0 时，本接口返回 40001，msg 即上游给的原因。',
                        '发送是**异步入队**：返回成功只代表已入队，实际是否送达请用「查询推送状态」接口看 wxstatus。',
                        '传了 encrypt_password 即为端对端加密：推送日志里记录的是密文，不是明文正文。',
                    ],
                    response_fields=[
                        ResponseFieldSpec('pushid', 'string', '本次推送的消息标识，用于「查询推送状态」'),
                        ResponseFieldSpec('readkey', 'string', '阅读密钥，用于「查询推送状态」与阅读页地址'),
                        ResponseFieldSpec('encrypted', 'bool', '本次是否为端对端加密推送（传了 encrypt_password 为 true）'),
                    ],
                    response_example='{"pushid": "11223344", "readkey": "abcdef123456", "encrypted": false}',
                ),
                EndpointSpec(
                    slug='status',
                    name='查询推送状态',
                    method='GET',
                    path='/api/push/serverchan/status',
                    summary='用「发送消息」返回的 pushid + readkey，查询这条消息的实际送达结果（wxstatus）。',
                    params=[
                        ParamSpec('pushid', '推送 ID', kind='text', required=True,
                                  placeholder='来自「发送消息」返回的 pushid',
                                  desc='必填：发送消息返回的 pushid'),
                        ParamSpec('readkey', '阅读密钥', kind='text', required=True,
                                  placeholder='来自「发送消息」返回的 readkey',
                                  desc='必填：发送消息返回的 readkey'),
                    ],
                    notes=[
                        'Server酱 的发送是异步入队，发送接口返回成功只代表「已入队」；实际是否送达微信要看本接口的 wxstatus。',
                        'wxstatus 为空表示该任务可能还没执行，稍后重试即可。',
                    ],
                    response_note='data 为上游的推送详情 JSON，其中 wxstatus 即微信接口返回的内容（为空表示可能还未执行），'
                                  '以实际返回为准。',
                ),
            ],
        ),
    ],
)
