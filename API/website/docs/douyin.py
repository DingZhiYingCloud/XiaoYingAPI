"""抖音服务 - 接口文档与在线调试数据

数据与 API/apis/Douyin/ 实际实现对齐（分类树 /api/douyin/ 为需签名）：
- Video   视频/图文解析（自研解析源，原「视频分析」服务迁移而来）
- Comment 评论发布（纯服务端补环境签名，原「自动评论」服务迁移而来）
后续接入更多抖音能力时在 channels 追加即可。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ServiceSpec

SERVICE = ServiceSpec(
    slug='douyin',
    name='抖音',
    prefix='/api/douyin/',
    summary='抖音平台能力聚合：视频/图文解析（无水印提取）与评论自动发布（纯服务端签名，无需浏览器）。',
    channels=[
        ChannelSpec(
            slug='video',
            name='视频解析',
            provider='抖音视频/图文解析',
            auth_note='auth',
            note='把抖音分享内容解析为可直接下载的视频/图文数据。',
            endpoints=[
                EndpointSpec('parse', '解析抖音内容', 'POST',
                             '/api/douyin/video/parse',
                             summary='解析抖音视频或图文，返回无水印地址等信息。',
                             params=[
                                 ParamSpec('share_text', '抖音分享文本', kind='textarea', required=True,
                                           placeholder='5.89 dAT:/ ... https://v.douyin.com/xxxxx/ 复制此链接...\n或直接粘贴链接 / aweme_id',
                                           desc='必填：支持三种输入 —— ①完整分享文本 ②链接（v.douyin.com 短链 或 www.douyin.com/video/xxx）③纯数字 aweme_id'),
                             ],
                             notes=['请求体为 application/x-www-form-urlencoded 表单。',
                                    '请使用真实可访问的分享内容测试；解析失败返回外部服务错误。']),
            ],
        ),
        ChannelSpec(
            slug='comment',
            name='评论发布',
            provider='抖音评论发布',
            auth_note='auth',
            note='在指定视频下发布一级纯文本评论，需携带真实抖音登录 Cookie。',
            endpoints=[
                EndpointSpec('publish', '发布抖音评论', 'POST',
                             '/api/douyin/comment/publish',
                             summary='在指定视频下发布一条一级纯文本评论，返回评论 ID、内容与发布时间。',
                             params=[
                                 ParamSpec('cookie', '抖音登录 Cookie', kind='textarea', required=True,
                                           placeholder='浏览器登录抖音后，从开发者工具「网络」面板复制完整 Cookie',
                                           desc='必填：抖音登录 Cookie 完整字符串（含 sessionid 等）。仅透传给抖音，服务端不落盘；Cookie 失效会返回外部服务错误。'),
                                 ParamSpec('aweme_id', '视频 ID', required=True,
                                           placeholder='7622798120358923583',
                                           desc='必填：目标视频 ID，纯数字，取自视频页 URL 的 /video/<aweme_id> 部分。'),
                                 ParamSpec('text', '评论内容', kind='textarea', required=True,
                                           placeholder='一级纯文本评论内容',
                                           desc='必填：评论内容。当前仅支持一级纯文本评论，不支持 @ / 话题 / 图片。'),
                             ],
                             notes=['请求体为 application/x-www-form-urlencoded 表单；参数放表单字段，不要放 URL 查询串。',
                                    '需先准备真实抖音登录 Cookie，且该账号有权限评论目标视频（视频需存在且公开）。',
                                    '抖音风控严格：高频调用会导致账号被限流，请低频调用并对失败做退避。',
                                    '被风控拦截时抖音返回空响应，此处统一映射为「外部API调用失败」。']),
            ],
        ),
    ],
)
