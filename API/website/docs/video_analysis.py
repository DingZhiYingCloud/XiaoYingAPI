"""视频分析服务 - 接口文档与在线调试数据

数据与 API/apis/VideoAnalysis/ 实际实现对齐（分类树 /api/video_analysis/ 为需签名）：
- 抖音 Douyin：解析抖音视频/图文（分享文本/链接/aweme_id 三种输入）
后续接入更多平台（如其他短视频平台）时在 channels 追加即可。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ServiceSpec

SERVICE = ServiceSpec(
    slug='video_analysis',
    name='视频分析',
    prefix='/api/video_analysis/',
    summary='短视频解析能力，提取无水印视频/图文内容。当前接入抖音线路，后续可继续扩展平台。',
    channels=[
        ChannelSpec(
            slug='douyin',
            name='抖音',
            provider='抖音视频/图文解析',
            auth_note='auth',
            note='把抖音分享内容解析为可直接下载的视频/图文数据。',
            endpoints=[
                EndpointSpec('parse', '解析抖音内容', 'POST',
                             '/api/video_analysis/douyin/parse',
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
    ],
)
