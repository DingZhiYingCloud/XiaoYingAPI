"""问题反馈服务 - 接口文档、接入说明与在线调试数据

与 `API/apis/feedback/` 的实际实现对齐：`/api/feedback/` 只保留两个「子项目可直接调用」
的**免签名**端点：

    ticket   —— 用用户 UAC Token 换一张一次性票据，交给反馈页完成登录态传递
    contacts —— 查某个接入项目的开发者联系方式

反馈中心的主体能力（提交 / 附件 / 公开区 / 回复）都在**我们托管的反馈页**上完成，
子项目零代码接入（详见 intro 的接入说明），后台管理入口在 `/console/feedback/`。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ResponseFieldSpec, ServiceSpec

SERVICE = ServiceSpec(
    slug='feedback',
    name='问题反馈',
    prefix='/api/feedback/',
    summary='统一的问题反馈调度中心：任何接入项目放一个链接或 iframe 即可接入（零代码），'
            '用户提交建议 / 升级 / 问题 / BUG 并可带图片与视频，AI 先审内容、管理员后台回复。',
    keywords='反馈API,工单接口,问题反馈中心,用户反馈系统,接入即用',
    intro=[
        '「问题反馈中心」是一套**统一的、所有接入项目共用**的反馈调度中心。接入非常简单——'
        '子项目零代码：只要在页面上放一个指向 /feedback/<你的 APPID>/ 的链接（或把它塞进 iframe）'
        '即可，反馈表单、附件上传、AI 审核、公开区与开发者联系方式都由本服务托管，'
        '你不需要写任何提交逻辑，也不需要保存任何反馈数据。',

        '用户侧流程：选择反馈类型（功能建议 / 功能升级 / 使用问题 / BUG 反馈 / 其他）→ 填写内容'
        '（无需标题）→ 选填图片与视频（张数、大小上限由后台统一配置）→ 提交。'
        '游客可直接匿名提交（需先通过图形验证码，并受同 IP 频率限制）；'
        '已登录用户提交会带上用户身份，登录后可查看「我的反馈」并继续追问。'
        '提交后状态为「待审核」，AI 审核通过后进入「待处理」，管理员回复后变为「已回复」。',

        '登录态怎么传给反馈页：子项目前端用用户自己的 UAC Token 调 POST /api/feedback/ticket'
        '换一张**一次性、5 分钟过期**的票据，把票据拼进反馈页地址（?ticket=xxx）作为链接或 iframe 地址；'
        '反馈页消费票据后建立会话，并 303 重定向到不带票据的干净地址。'
        '这样 UAC Token 不会落在 URL、浏览器历史与服务器访问日志里。游客无需票据，直接打开反馈页即可。',

        '**开发者联系方式的查看位置（三处）**：① 反馈页底部（/feedback/<app_id>/ 的「开发者联系方式」卡片）；'
        '② 公开区页面同样展示同一份联系方式；③ 子项目也可以在自己的页面上调用本服务的 '
        'GET /api/feedback/contacts?app_id=<APPID>（免签名）拿到这份数据，自行渲染。'
        '联系方式由超管在后台「问题反馈 → 反馈中心设置 → 各项目开发者联系方式」按项目分别维护，'
        '展示平台（QQ / QQ 邮箱 / 微信 / Telegram / WhatsApp / Discord 等）与具体值都可自定义，'
        '不同项目可以填不同的值。',

        'AI 审核说明：开关与两套提示词都在后台「反馈中心设置 → AI 审核」里配置（留空则使用内置通用规则）。'
        '**规则就是提示词**——后台写的规则会与反馈正文、提交者信息一起发给 AI，由 AI 判定是否驳回。'
        '提交内容的审核在后台线程里逐条慢慢审，不占用你的接口调用；平台没有配置可用 AI 模型时自动跳过审核，'
        '提交直接进入「待处理」。管理员回复前 AI 也会审一遍语气，但**只提醒、不阻断**，'
        '管理员可以修改后重发，也可以强制发送（强制发送会记入审核留痕）。'
        '若某条反馈因故没审到（例如审核调用失败），后台可以直接对它点「立即送审」优先补审。',

        '数据隔离与公开区：反馈数据按接入项目隔离，后台可按项目 / 状态 / 类型 / AI 审核状态筛选与搜索。'
        '每个项目还有一个「公开区」——只展示**游客提交且已通过审查**的反馈（不展示任何附件与提交者身份），'
        '供访客搜索是否已经有人提过同样的问题；管理员可随时把某条从公开区撤下。',
    ],
    channels=[
        ChannelSpec(
            slug='center',
            name='反馈中心（托管反馈页接入）',
            provider='站内反馈库（数据按接入项目隔离）',
            auth_note='open',
            note='两个端点都免签名（服务策略里配成 open）：ticket 的凭证是调用方本来就持有的'
                 '用户 UAC Token，contacts 是公开信息。提交、查看与回复都不走 /api/，'
                 '而是在 /feedback/<app_id>/ 反馈页上由本站直接处理。',
            endpoints=[
                EndpointSpec(
                    'ticket', '换取反馈页一次性票据', 'POST', '/api/feedback/ticket',
                    summary='用用户的 UAC Token 换一张一次性票据（5 分钟过期），'
                            '子项目把它拼进反馈页地址即可让用户以登录身份提交反馈。',
                    params=[
                        ParamSpec('token', '用户登录 Token', kind='text', required=True,
                                  placeholder='用户中心登录后获取',
                                  desc='用户在**你项目下**的 UAC Token（Token 绑定项目，跨项目的 Token 无效）'),
                    ],
                    notes=[
                        '票据一次性且 5 分钟过期：用完或过期即废，重复使用会被忽略（反馈页按游客处理）。',
                        '拼接方式：/feedback/<app_id>/?ticket=<ticket>，作为链接或 iframe 地址交浏览器打开。',
                    ],
                    response_fields=[
                        ResponseFieldSpec('ticket', 'string', '一次性票据'),
                        ResponseFieldSpec('expire_in', 'int', '有效期（秒）'),
                        ResponseFieldSpec('app_id', 'string', '接入项目 APPID'),
                        ResponseFieldSpec('app_name', 'string', '接入项目名称'),
                    ],
                    response_example='{"ticket": "b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6", "expire_in": 300, "app_id": "app_xxxxxxxx", "app_name": "Example App"}',
                ),
                EndpointSpec(
                    'contacts', '查询项目开发者联系方式', 'GET', '/api/feedback/contacts',
                    summary='查询某个接入项目已启用的开发者联系方式（平台名 / 值 / 可点击链接），'
                            '与反馈页底部展示的是同一份数据。',
                    params=[
                        ParamSpec('app_id', '接入项目 APPID', kind='text', required=True,
                                  placeholder='app_xxxxxxxx',
                                  desc='在后台「接入项目」里查到的 APPID'),
                    ],
                    notes=[
                        'contacts[].url 为空串表示该平台未配置跳转模板，此时按纯文本展示。',
                        '平台被停用或该项目的该项被清空后，对应条目不再返回。',
                    ],
                    response_fields=[
                        ResponseFieldSpec('app_id', 'string', '接入项目 APPID'),
                        ResponseFieldSpec('app_name', 'string', '接入项目名称'),
                        ResponseFieldSpec('contacts', 'array', '开发者联系方式列表'),
                        ResponseFieldSpec('contacts[].platform', 'string', '平台代码'),
                        ResponseFieldSpec('contacts[].name', 'string', '平台名称'),
                        ResponseFieldSpec('contacts[].icon', 'string', '平台图标'),
                        ResponseFieldSpec('contacts[].label', 'string', '值标签'),
                        ResponseFieldSpec('contacts[].value', 'string', '联系方式值'),
                        ResponseFieldSpec('contacts[].url', 'string', '可点击链接（空串为纯文本）'),
                    ],
                    response_example='{"app_id": "app_xxxxxxxx", "app_name": "Example App", "contacts": [{"platform": "qq", "name": "QQ", "icon": "https://cdn.example.com/qq.svg", "label": "QQ", "value": "12345678", "url": "https://wpa.qq.com/msgrd?v=3&uin=12345678"}]}',
                ),
            ],
        ),
    ],
)
