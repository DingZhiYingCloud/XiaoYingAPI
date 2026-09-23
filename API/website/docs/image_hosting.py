"""图床服务 - 接口文档与在线调试数据

数据与 API/apis/ImageHosting/ 实际实现对齐（分类树 /api/ImageHosting/ 为需签名）：
- scdn： scdn.io 图床（上传图片，返回 CDN 直链）
- picui：PicUI 图床（上传图片 + 服务端 Token 池管理）
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ServiceSpec

SERVICE = ServiceSpec(
    slug='image_hosting',
    name='图床服务',
    prefix='/api/ImageHosting/',
    summary='图片外链托管：上传图片（或 ≤10 秒短视频）返回可直链访问的 CDN 地址，支持输出格式、加密与存储位置选择。当前接入 2 条线路。',
    channels=[
        ChannelSpec(
            slug='scdn',
            name='scdn.io 图床',
            provider='scdn.io（img.scdn.io）图片托管',
            auth_note='auth',
            note='上传图片返回外链；服务端按 SHA-256 秒传，重复图片直接返回已有链接。需项目签名调用。',
            endpoints=[
                EndpointSpec('upload', '上传图片', 'POST', '/api/ImageHosting/scdn/upload',
                             summary='上传一张图片，返回可直接引用的 CDN 外链。',
                             params=[
                                 ParamSpec('image', '图片文件', kind='file', required=False, accept='image/*',
                                           desc='本地图片文件（multipart 字段 image，支持 jpg/png/webp/gif/bmp/tiff）；与 image_url 二选一'),
                                 ParamSpec('image_url', '远程图片 URL', kind='text', required=False,
                                           placeholder='https://example.com/a.jpg',
                                           desc='远程图片地址（http/https），服务端代理拉取；与 image 二选一'),
                                 ParamSpec('output_format', '输出格式', kind='select', default='auto',
                                           options=[{'value': 'auto', 'label': 'auto（默认，静态图转 webp）'},
                                                    {'value': 'jpg', 'label': 'jpg'},
                                                    {'value': 'png', 'label': 'png'},
                                                    {'value': 'webp', 'label': 'webp'},
                                                    {'value': 'gif', 'label': 'gif'},
                                                    {'value': 'webp_animated', 'label': 'webp_animated（动图）'}],
                                           desc='选填：输出格式，默认 auto'),
                                 ParamSpec('cdn_domain', 'CDN 域名', kind='text',
                                           placeholder='留空由服务端自动选择',
                                           desc='选填：指定外链 CDN 域名（如 img.scdn.io），留空自动选择'),
                                 ParamSpec('storage_destination', '存储位置', kind='select',
                                           options=[{'value': '', 'label': '不传（默认 local）'},
                                                    {'value': 'local', 'label': 'local'},
                                                    {'value': 'telegram', 'label': 'telegram'},
                                                    {'value': 'r2', 'label': 'r2（Cloudflare R2）'}],
                                           desc='选填：存储位置'),
                                 ParamSpec('password_enabled', '启用密码', kind='select', default='false',
                                           options=[{'value': 'false', 'label': 'false（默认）'},
                                                    {'value': 'true', 'label': 'true（加密上传）'}],
                                           desc='选填：加密上传（加密图永不参与秒传）'),
                                 ParamSpec('image_password', '访问密码', kind='text',
                                           desc='选填：password_enabled=true 时必填'),
                                 ParamSpec('password_type', '密码模式', kind='select', default='plain',
                                           options=[{'value': 'plain', 'label': 'plain（普通密码）'},
                                                    {'value': 'qa', 'label': 'qa（问答式）'}],
                                           desc='选填：密码模式，默认 plain'),
                                 ParamSpec('password_question', '问题文本', kind='text',
                                           desc='选填：password_type=qa 时必填'),
                             ],
                             notes=['请求体为 multipart/form-data（文件字段 image，可直接用下方“选择文件”上传）；'
                                    '用 image_url 时也可用 application/x-www-form-urlencoded。',
                                    '返回 data 含 url / filename / storage_backend / 压缩统计 / deduped（是否秒传） / password_protected。',
                                    '服务端按 SHA-256 秒传：命中时 message 为「图片已存在，秒传成功！」，deduped=true。',
                                    '本服务需项目签名（app_id/timestamp/nonce/sign）；在线调试由服务端自动代签。']),
            ],
        ),
        ChannelSpec(
            slug='picui',
            name='PicUI 图床',
            provider='PicUI（v2.picui.cn）图片托管',
            auth_note='auth',
            note='上传图片返回外链；PicUI 账号 Token 由服务端 Token 池统一持有并记账，容量用尽自动切换，调用方无需提供账号。需项目签名调用。',
            endpoints=[
                EndpointSpec('upload', '上传图片', 'POST', '/api/ImageHosting/picui/upload',
                             summary='上传一张图片，返回可直接引用的外链地址（含 html / markdown 等多种引用格式）。',
                             params=[
                                 ParamSpec('image', '图片文件', kind='file', required=True, accept='image/*',
                                           desc='本地图片文件（multipart 字段 image），必需'),
                                 ParamSpec('permission', '图片权限', kind='select',
                                           options=[{'value': '', 'label': '不传（PicUI 默认公开）'},
                                                    {'value': '1', 'label': '1（公开）'},
                                                    {'value': '0', 'label': '0（私有）'}],
                                           desc='选填：图片权限，留空使用 PicUI 默认值'),
                                 ParamSpec('strategy_id', '储存策略ID', kind='text', default='1',
                                           placeholder='默认 1',
                                           desc='选填：PicUI 储存策略 ID，默认 1（「普通用户」策略）'),
                                 ParamSpec('album_id', '相册ID', kind='text',
                                           desc='选填：目标相册 ID'),
                                 ParamSpec('expired_at', '过期时间', kind='text',
                                           placeholder='2026-12-31 23:59:59',
                                           desc='选填：图片过期时间，格式 yyyy-MM-dd HH:mm:ss'),
                                 ParamSpec('upload_token', '临时上传Token', kind='text',
                                           desc='选填：PicUI 临时上传 Token（对应其 token 字段），一般不传'),
                             ],
                             notes=['请求体为 multipart/form-data（文件字段 image，可直接用下方“选择文件”上传）。',
                                    'PicUI 账号 Token 由服务端 Token 池自动选取，调用方无需（也无法）指定；'
                                    '上传成功后按 PicUI 返回的图片大小扣减该 Token 容量，容量用尽自动删除并切换下一个。',
                                    '返回 data 含 url / size_kb / size_bytes / mimetype / extension / md5 / sha1 /'
                                    ' links（html、bbcode、markdown、markdown_with_link、thumbnail_url 等）。',
                                    '令牌池告警：上传后若池内剩余容量跌破 50MB，系统会自动向管理员邮箱'
                                    '（环境变量 QQ_MAIL_ACCOUNT，未配置则不发送）发送一封补货提醒邮件；'
                                    '该告警只在「跌破」的那一次发送，补货回到 50MB 以上后再次跌破才会重新告警。',
                                    'Token 池为空或容量均已用尽时返回 50002，请先调用「导入 Token」接口补充。',
                                    '本服务需项目签名（app_id/timestamp/nonce/sign）；在线调试由服务端自动代签。']),
                EndpointSpec('list_tokens', '查询 Token 池', 'GET', '/api/ImageHosting/picui/tokens',
                             summary='查看 Token 池整体容量与每个 Token 的已用 / 剩余容量（Token 已脱敏）。',
                             params=[],
                             notes=['返回 data 顶层字段：',
                                    'count：当前池内可用的 Token 数量',
                                    'total_capacity_mb：全部 Token 的总容量合计（MB）',
                                    'total_used_mb：全部 Token 的已用容量合计（MB）',
                                    'total_remaining_mb：全部 Token 的剩余容量合计（MB）'
                                    '—— 即系统当前还能上传的总容量，看这个字段判断是否要补货',
                                    'total_capacity_bytes / total_used_bytes / total_remaining_bytes：'
                                    '与上面三项一一对应的字节值，便于程序精确计算',
                                    'items：池内每个 Token 的明细，字段如下：',
                                    'items[].token：Token 脱敏值（保留首 6 位与末 4 位，如 657|uN****afdb）',
                                    'items[].capacity_mb / items[].capacity_bytes：该 Token 的总容量',
                                    'items[].used_mb / items[].used_bytes：该 Token 的已用容量',
                                    'items[].remaining_mb / items[].remaining_bytes：该 Token 的剩余容量'
                                    '（= 容量 − 已用，最小为 0）',
                                    'items[].create_time：该 Token 的入库时间',
                                    '单位说明：容量同时提供 MB（保留 2 位小数，便于阅读）与字节（便于计算）两种单位。',
                                    '容量用尽（已用 ≥ 容量）的 Token 会被自动删除，因此 items 中出现的 Token 均可继续使用；'
                                    '服务器只做容量记账，不参与图片存储。']),
                EndpointSpec('add_tokens', '导入 Token', 'POST', '/api/ImageHosting/picui/tokens',
                             summary='向 Token 池新增一个或多个 Token（支持直接输入，也支持上传按行存放的 Token 文件）。',
                             params=[
                                 ParamSpec('tokens', 'Token', kind='textarea', repeatable=True,
                                           repeat_hint='可重复传参，或用逗号、换行分隔一次提交多个',
                                           placeholder='657|xxxxxxxxxxxxxxxx',
                                           desc='选填：待新增的 Token，可多个（与 token_file 至少传一项）'),
                                 ParamSpec('token_file', 'Token 文件', kind='file', accept='.txt,text/plain',
                                           desc='选填：文本文件，按行存放 Token（一行一个，UTF-8）'),
                                 ParamSpec('capacity_mb', '单个容量(MB)', kind='number', default='50',
                                           desc='选填：每个 Token 的容量（MB），默认 50'),
                             ],
                             notes=['Token 唯一：同一个 Token 只会入库一条，重复导入不会重复写入'
                                    '（库中已存在、或同一批请求里重复出现的，都计入 duplicated 跳过）。',
                                    'tokens 支持重复字段、逗号或换行分隔，一次可提交多个 Token；'
                                    'Token 内不能含空格等空白字符（文件里若带注释/多余列会被拒绝，避免导入无效 Token）。',
                                    'token_file 为按行存放 Token 的文本文件（一行一个），可与 tokens 同时使用。',
                                    '返回 data 字段：submitted 本次提交的 Token 数（已按行/逗号拆分并去重）；'
                                    'created 实际新增数量；duplicated 因已存在而跳过的数量；'
                                    'duplicated_tokens 被跳过的 Token 脱敏列表；'
                                    'capacity_bytes / capacity_mb 每个新 Token 的容量。',
                                    '单次最多导入 1000 个 Token；本服务需项目签名（app_id/timestamp/nonce/sign）。']),
            ],
        ),
    ],
)
