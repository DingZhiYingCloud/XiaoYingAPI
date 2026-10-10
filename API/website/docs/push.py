"""消息推送服务 - 接口文档与在线调试数据

数据与 API/apis/push/serverchan/ 实际实现对齐：POST /api/push/serverchan/send（默认需签名）。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ResponseFieldSpec, ServiceSpec
from API.apis.push.email_task import utils as email_task_utils

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


def _task_response_fields():
    """「邮件定时推送」任务对象的响应字段表（create / detail / update 共用）

    每次返回新列表：多个端点不共享同一批 ResponseFieldSpec 对象
    （渲染时会写入 indent，共享会互相干扰）。
    """
    return [
        ResponseFieldSpec('id', 'string', '任务 ID（UUID）'),
        ResponseFieldSpec('recipients', 'array', '收件人邮箱列表'),
        ResponseFieldSpec('subject', 'string', '邮件标题'),
        ResponseFieldSpec('body', 'string', '邮件正文'),
        ResponseFieldSpec('repeat', 'bool', '是否重复发送（由 interval_minutes 推导）'),
        ResponseFieldSpec('interval_minutes', 'int', '发送间隔（分钟）；0 表示只发一次'),
        ResponseFieldSpec('enabled', 'bool', '是否启用（停用后不再调度）'),
        ResponseFieldSpec('next_run_at', 'string', '下次发送时间；为空表示不再调度'),
        ResponseFieldSpec('last_sent_at', 'string', '上次发送时间'),
        ResponseFieldSpec('sent_count', 'int', '累计发送次数'),
        ResponseFieldSpec('last_ok', 'bool', '上次是否发送成功（从未发送时为空）'),
        ResponseFieldSpec('last_message', 'string', '上次结果说明'),
        ResponseFieldSpec('create_time', 'string', '创建时间'),
        ResponseFieldSpec('updated_time', 'string', '更新时间'),
    ]

SERVICE = ServiceSpec(
    slug='push',
    name='消息推送服务',
    prefix='/api/push/',
    summary='把消息推送到手机或邮箱的通知服务。当前接入 Server酱（微信推送）、邮件、邮件定时推送 3 条线路，后续可继续扩展更多推送平台/线路。',
    keywords='消息推送API,微信推送接口,Server酱API,ServerChan,邮件发送接口,通知接口,定时邮件,循环发邮件,邮件定时任务',
    intro=[
        '消息推送服务把「服务器 / 脚本 / 设备上发生的事」发送到手机或邮箱，适合告警、任务完成通知、'
        '定时任务结果汇总等场景。当前有 3 条线路：**Server酱**（微信推送）、**邮件** 与 **邮件定时推送**。',
        '**消息实际推送到哪个通道**（微信服务号、企业微信应用消息、企业微信/钉钉/飞书群机器人、Bark、'
        'PushDeer 或自定义 Webhook）由 Server酱 后台的通道配置决定 —— 换通道不用改调用代码。',
        '**SendKey 由服务端托管**：在超管控制台「账号管理」里新增一个平台为「Server酱」的账号，'
        '把 SendKey 填进「登录凭据」字段即可（凭据加密落库、页面不回显）。调用方无需、也不应传递 SendKey。',
        '**邮件线路**由原「邮箱服务」的发送邮件并入：`POST /api/push/email/send` 与原 `/api/email/v1/send` '
        '是同一实现、同一参数与响应，老路由继续可用。',
        '**邮件定时推送线路**用于「不守着也要按时发」的场景：创建一份推送计划，由站内常驻调度线程到点自动发送 —— '
        '可只发一次，也可每 N 分钟重复发送；停机后再启动会自动补发，不会漏发。任务按接入项目隔离。',
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
        ChannelSpec(
            slug='email',
            name='邮件',
            provider='站内邮件（Django 邮件后端 / SMTP）',
            auth_note='auth',
            note='把消息以邮件形式发送出去（原「邮箱服务」的发送邮件能力，已并入本服务）；'
                 '与 `/api/email/v1/send` 是同一实现，参数与响应完全一致。需项目签名调用。',
            endpoints=[
                EndpointSpec(
                    slug='send',
                    name='发送邮件',
                    method='POST',
                    path='/api/push/email/send',
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
                        '老入口 `/api/email/v1/send` 仍可用，与本端点等价（同一实现）。',
                    ],
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
            slug='email_task',
            name='邮件定时推送',
            provider='站内邮件（Django 邮件后端 / SMTP）+ 站内常驻调度',
            auth_note='auth',
            note='创建一份邮件推送计划：可「只发一次」或「每 N 分钟重复发送」，由站内常驻调度线程'
                 '到点自动发送，调用方无需保持在线。任务按接入项目隔离，仅能操作本项目的任务。需项目签名调用。',
            endpoints=[
                EndpointSpec(
                    slug='create',
                    name='新建任务',
                    method='POST',
                    path='/api/push/email_task/create',
                    summary='创建一个邮件定时推送任务（只发一次或按间隔重复发送）。',
                    params=[
                        ParamSpec('recipients', '收件人邮箱', kind='textarea', required=True,
                                  repeatable=True,
                                  repeat_hint='多个邮箱用逗号或换行分隔，也可通过同一字段多次传递',
                                  placeholder='a@example.com\nb@example.com',
                                  desc=f'收件人邮箱（必填，最多 {email_task_utils.MAX_RECIPIENTS} 个）'),
                        ParamSpec('subject', '邮件标题', kind='text', required=True,
                                  placeholder='邮件标题', desc='邮件标题（必填，最长 255 个字符）'),
                        ParamSpec('body', '邮件正文', kind='textarea', required=True,
                                  placeholder='邮件正文内容', desc='邮件正文（必填）'),
                        ParamSpec('repeat', '是否重复', kind='select', required=False, default='',
                                  desc='是否重复发送。选「仅发送一次」时 interval_minutes 必须为 0；'
                                       '选「重复发送」时 interval_minutes 必须 ≥ 1。不指定则由 interval_minutes 推导（>0 即重复）。',
                                  options=[{'value': '', 'label': '不指定（按间隔推导）'},
                                           {'value': 'false', 'label': '仅发送一次'},
                                           {'value': 'true', 'label': '重复发送'}]),
                        ParamSpec('interval_minutes', '发送间隔(分钟)', kind='number', required=False,
                                  placeholder='如 30；只发一次填 0',
                                  desc=f'发送间隔，单位分钟。0（或不填）= 只发一次；大于 0 = 每隔该分钟数重复发送'
                                       f'（范围 1-{email_task_utils.MAX_INTERVAL_MINUTES}）。'),
                        ParamSpec('first_send_at', '首次发送时间', kind='text', required=False,
                                  placeholder='如 2026-10-09 15:30（不填=立即）',
                                  desc='首次发送时间，格式 2026-10-09 15:30 或 2026-10-09 15:30:00（按站点时区）。'
                                       '不填则创建后立即进入调度（下一个调度周期即发送）。'),
                    ],
                    notes=[
                        '「只发一次」= repeat 选 false 或 interval_minutes 为 0，发送完成后任务自动停用。',
                        '「重复发送」= interval_minutes ≥ 1，会一直按间隔发送，直到调用「修改任务」停用或「删除任务」删除。',
                        '任务不需要调用方保持在线：由站内常驻调度线程到点自动发送。',
                        '停机 / 重启后会自动补发：发现已逾期即补发一次，并把下一次按「当前时间 + 间隔」重排'
                        '（**只补发一次**，不会把停机期间欠的多个周期一次性补齐）。',
                        '发送失败**不自动重试**：重复任务等下一周期、一次性任务就此结束；失败原因可在响应字段'
                        ' last_message 或控制台「推送日志」查看。',
                        '任务按接入项目（APPID）隔离，只能查看 / 操作自己创建的任务。',
                    ],
                    response_fields=_task_response_fields(),
                    response_example='{"id": "3f0c...", "recipients": ["a@example.com"], "subject": "日报",'
                                     ' "repeat": true, "interval_minutes": 30, "enabled": true,'
                                     ' "next_run_at": "2026-10-09 15:30:00", "sent_count": 0, "last_ok": null}',
                ),
                EndpointSpec(
                    slug='list',
                    name='任务列表',
                    method='GET',
                    path='/api/push/email_task/list',
                    summary='分页列出本项目创建的邮件定时推送任务。',
                    params=[
                        ParamSpec('page', '页码', kind='number', required=False, default='1',
                                  desc='页码，从 1 开始，默认 1'),
                        ParamSpec('page_size', '每页数量', kind='number', required=False, default='20',
                                  desc='每页数量，默认 20，范围 1-100'),
                        ParamSpec('enabled', '启用状态', kind='select', required=False, default='',
                                  desc='筛选任务启用状态；不指定则返回全部。',
                                  options=[{'value': '', 'label': '全部'},
                                           {'value': 'true', 'label': '仅启用的任务'},
                                           {'value': 'false', 'label': '仅停用的任务'}]),
                    ],
                    notes=[
                        '仅返回本项目的任务（按 APPID 隔离）。',
                        '按创建时间倒序返回。',
                    ],
                    response_note='data 为分页对象：total（总数）/ page / page_size / total_pages / '
                                  'items（任务对象数组，字段同「新建任务」的响应）。',
                    response_example='{"total": 1, "page": 1, "page_size": 20, "total_pages": 1,'
                                     ' "items": [{"id": "3f0c...", "subject": "日报", "repeat": true, "interval_minutes": 30}]}',
                ),
                EndpointSpec(
                    slug='detail',
                    name='任务详情',
                    method='GET',
                    path='/api/push/email_task/detail',
                    summary='查询单个任务的完整信息。',
                    params=[
                        ParamSpec('id', '任务 ID', kind='text', required=True,
                                  placeholder='任务 ID（UUID）', desc='必填：任务 ID'),
                    ],
                    notes=['只能查询本项目的任务；他人的任务与不存在的 ID 同样返回「资源不存在」。'],
                    response_fields=_task_response_fields(),
                ),
                EndpointSpec(
                    slug='update',
                    name='修改任务',
                    method='POST',
                    path='/api/push/email_task/update',
                    summary='修改任务（只改传入的字段，未传的保持不变），可用于启停。',
                    params=[
                        ParamSpec('id', '任务 ID', kind='text', required=True,
                                  placeholder='任务 ID（UUID）', desc='必填：要修改的任务 ID'),
                        ParamSpec('recipients', '收件人邮箱', kind='textarea', required=False,
                                  repeatable=True,
                                  repeat_hint='多个邮箱用逗号或换行分隔',
                                  placeholder='留空则不改',
                                  desc='新的收件人邮箱（选填，最多 20 个）'),
                        ParamSpec('subject', '邮件标题', kind='text', required=False,
                                  placeholder='留空则不改', desc='新的邮件标题（选填）'),
                        ParamSpec('body', '邮件正文', kind='textarea', required=False,
                                  placeholder='留空则不改', desc='新的邮件正文（选填）'),
                        ParamSpec('repeat', '是否重复', kind='select', required=False, default='',
                                  desc='修改发送方式（与 interval_minutes 配套，规则同「新建任务」）；不指定则不修改。',
                                  options=[{'value': '', 'label': '不修改'},
                                           {'value': 'false', 'label': '仅发送一次'},
                                           {'value': 'true', 'label': '重复发送'}]),
                        ParamSpec('interval_minutes', '发送间隔(分钟)', kind='number', required=False,
                                  placeholder='留空则不改',
                                  desc=f'新的发送间隔（分钟，1-{email_task_utils.MAX_INTERVAL_MINUTES}）；'
                                       '修改后会按当前时间重排下一次发送。'),
                        ParamSpec('enabled', '启用状态', kind='select', required=False, default='',
                                  desc='启用 / 停用任务；不指定则不修改。',
                                  options=[{'value': '', 'label': '不修改'},
                                           {'value': 'true', 'label': '启用'},
                                           {'value': 'false', 'label': '停用'}]),
                    ],
                    notes=[
                        '至少提供一个要修改的字段。',
                        '修改 interval_minutes 会按「当前时间 + 新间隔」重排下一次发送，不会沿用旧节奏。',
                        '重新启用一个已结束的一次性任务，会立即重新进入调度。',
                    ],
                    response_fields=_task_response_fields(),
                ),
                EndpointSpec(
                    slug='delete',
                    name='删除任务',
                    method='POST',
                    path='/api/push/email_task/delete',
                    summary='删除任务（支持一次删除多个）。',
                    params=[
                        ParamSpec('id', '任务 ID', kind='text', required=True, repeatable=True,
                                  repeat_hint='多个 ID 用逗号分隔，或用同一字段多次传递',
                                  placeholder='任务 ID（UUID）', desc='必填：要删除的任务 ID（支持多个）'),
                    ],
                    notes=['只能删除本项目的任务；返回 data.deleted 为实际删除的条数。'],
                    response_fields=[
                        ResponseFieldSpec('deleted', 'int', '实际删除的任务条数'),
                    ],
                    response_example='{"deleted": 2}',
                ),
            ],
        ),
    ],
)
