"""抖音服务 - 接口文档与在线调试数据

数据与 API/apis/Douyin/ 实际实现对齐（服务策略 /api/douyin/ 默认需签名）：
- Video   视频/图文解析（自研解析源，原「视频分析」服务迁移而来）
- Comment 评论发布（纯服务端补环境签名，原「自动评论」服务迁移而来）
后续接入更多抖音能力时在 channels 追加即可。
"""
from .schema import (ChannelSpec, EndpointSpec, ParamSpec, ResponseFieldSpec,
                     ServiceSpec)

SERVICE = ServiceSpec(
    slug='douyin',
    name='抖音',
    prefix='/api/douyin/',
    summary='抖音平台能力聚合：视频/图文解析（无水印提取）与评论自动发布（纯服务端签名，无需浏览器）。',
    keywords='抖音API,抖音视频解析,抖音去水印,抖音图文解析',
    intro=[
        '抖音服务提供两类能力：视频 / 图文解析——传入分享链接即可拿到无水印的视频或图集地址等信息；'
        '评论发布——在指定视频下发布一条一级纯文本评论。',
        '两条线路均需项目签名。抖音的风控参数全部由服务端处理：视频解析走匿名 ttwid 加重试策略，'
        '评论发布在服务端补环境执行抖音官方 JS 生成所需签名，调用方既不需要浏览器，'
        '也不需要自行实现签名算法。',
        '评论接口风控较严，建议低频调用并对失败做退避重试，避免短时间内对同一视频重复提交。',
    ],
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
                                    '请使用真实可访问的分享内容测试；解析失败返回外部服务错误。'],
                             response_fields=[
                                 ResponseFieldSpec('title', 'string', '视频/图文标题'),
                                 ResponseFieldSpec('cover', 'string', '封面图地址'),
                                 ResponseFieldSpec('duration', 'float', '时长（秒）；图文为 null'),
                                 ResponseFieldSpec('medias', 'array', '视频下载列表；图文为空数组'),
                                 ResponseFieldSpec('medias[].format', 'string', '画质描述（如 1080P）'),
                                 ResponseFieldSpec('medias[].url', 'string', '无水印视频地址'),
                                 ResponseFieldSpec('medias[].file_size', 'int', '文件大小（字节，可能为 null）'),
                                 ResponseFieldSpec('images', 'array', '图片下载列表；视频为空数组'),
                                 ResponseFieldSpec('images[].format', 'string', '图片描述（如 图片1）'),
                                 ResponseFieldSpec('images[].url', 'string', '图片原图地址'),
                                 ResponseFieldSpec('images[].file_size', 'int', '文件大小（通常为 null）'),
                             ],
                             response_example='''{
  "title": "示例视频标题",
  "cover": "https://p3-sign.douyinpic.com/cover.jpg",
  "duration": 15.0,
  "medias": [
    {"format": "1080P", "url": "https://v3-dy.douyinvod.com/xxx.mp4", "file_size": 1234567}
  ],
  "images": []
}'''),
            ],
        ),
        ChannelSpec(
            slug='comment',
            name='评论发布',
            provider='抖音评论发布',
            auth_note='auth',
            note='在指定视频下发布一级纯文本评论。登录 Cookie 在右侧栏「本机凭据」填写并保存到本机，调试时自动带上。',
            endpoints=[
                EndpointSpec('publish', '发布抖音评论', 'POST',
                             '/api/douyin/comment/publish',
                             summary='在指定视频下发布一条一级纯文本评论，返回评论 ID、内容与发布时间。',
                             params=[
                                 # local=True：不在参数表单里填，改由右侧栏「本机凭据」卡片提供
                                 # （存浏览器本机，调试时自动带上），免得每次调试重新粘贴
                                 ParamSpec('cookie', '抖音登录 Cookie', kind='textarea', required=True,
                                           local=True,
                                           placeholder='浏览器登录抖音后，从开发者工具「网络」面板复制完整 Cookie',
                                           desc='必填：抖音登录 Cookie 完整字符串（含 sessionid 等）。在右侧栏「本机凭据」填写并保存到本机浏览器，调试时自动带上（换设备 / 清缓存需重新粘贴）；不落库、不上传，仅透传给抖音。Cookie 失效会返回外部服务错误。'),
                                 ParamSpec('aweme_id', '视频 ID', required=True,
                                           placeholder='7622798120358923583',
                                           desc='必填：目标视频 ID，纯数字，取自视频页 URL 的 /video/<aweme_id> 部分。'),
                                 ParamSpec('text', '评论内容', kind='textarea', required=True,
                                           placeholder='一级纯文本评论内容',
                                           desc='必填：评论内容。当前仅支持一级纯文本评论，不支持 @ / 话题 / 图片。'),
                             ],
                             notes=['请求体为 application/x-www-form-urlencoded 表单；参数放表单字段，不要放 URL 查询串。',
                                    '登录 Cookie 只填一次：在右侧栏「本机凭据」粘贴并点「保存到本机浏览器」，之后调试会自动带上（仅本机保存，换设备需重新粘贴）。',
                                    '该账号需有权限评论目标视频（视频需存在且公开）。',
                                    '抖音风控严格：高频调用会导致账号被限流，请低频调用并对失败做退避。',
                                    '被风控拦截时抖音返回空响应，此处统一映射为「外部API调用失败」。'],
                             response_fields=[
                                 ResponseFieldSpec('cid', 'string', '评论 ID'),
                                 ResponseFieldSpec('text', 'string', '评论内容'),
                                 ResponseFieldSpec('create_time', 'int', '发布时间（Unix 秒级时间戳）'),
                             ],
                             response_example='''{
  "cid": "7684103483653391114",
  "text": "示例评论",
  "create_time": 1789095055
}'''),
            ],
        ),
    ],
)
