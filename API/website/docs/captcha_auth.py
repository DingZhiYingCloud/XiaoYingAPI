"""图形验证服务 - 接口文档与在线调试数据

数据与 API/apis/captcha_auth/ 实际实现对齐（分类树 /api/captcha_auth/ 开放，无需签名）：
- 阿里云 aliyun：阿里云图形认证（滑块/点选等）——下发前端配置 + 服务端二次校验。
后续接入更多图形验证渠道时在 channels 追加即可。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ServiceSpec

SERVICE = ServiceSpec(
    slug='captcha_auth',
    name='图形验证',
    prefix='/api/captcha_auth/',
    summary='阿里云图形验证码集成（滑块/点选等），服务端下发配置并二次校验，防机器流量。当前接入阿里云线路。',
    channels=[
        ChannelSpec(
            slug='aliyun',
            name='阿里云图形认证',
            provider='阿里云图形认证服务（滑块/点选验证）',
            auth_note='open',
            note='两步接入：先用 config 拿 appId 初始化前端 SDK，用户验证通过后再用 verify 做服务端二次校验。',
            endpoints=[
                EndpointSpec('config', '获取图形认证配置', 'GET', '/api/captcha_auth/aliyun/config',
                             summary='返回图形认证 appId（captchaId），供 H5 前端 SDK 初始化。公开接口，无需签名。',
                             notes=['响应 data.app_id 即前端 initAlicom4({ captchaId: app_id, product: "bind" }, ...) 所需的 captchaId。']),
                EndpointSpec('verify', '二次校验', 'POST', '/api/captcha_auth/aliyun/verify',
                             summary='上传客户端验证参数，确认用户本次图形验证有效（防绕过）。',
                             params=[
                                 ParamSpec('lot_number', '验证流水号', kind='text', required=True,
                                           placeholder='4dc3cfc2cdff448cad8d13107198d473',
                                           desc='必填：前端 SDK 验证通过后回调返回的流水号，32 位小写 hex'),
                                 ParamSpec('captcha_output', '验证输出信息', kind='textarea', required=True,
                                           desc='必填：前端 SDK 验证通过后回调返回的 captchaOutput'),
                                 ParamSpec('pass_token', '验证通过标识', kind='textarea', required=True,
                                           desc='必填：前端 SDK 验证通过后回调返回的 passToken'),
                                 ParamSpec('gen_time', '验证通过时间戳', kind='text', required=True,
                                           desc='必填：前端 SDK 验证通过后回调返回的 genTime'),
                             ],
                             notes=['请求体为 application/x-www-form-urlencoded 表单；公开接口，无需项目签名。',
                                    '接口请求成功统一返回 code=10000；业务结果以 data.result 判断：',
                                    'success=验证有效，fail=验证无效（pass_token 过期/流水号已用等），原因见 data.reason。']),
            ],
        ),
    ],
)
