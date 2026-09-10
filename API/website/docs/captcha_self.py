"""自研图形验证码 - 接口文档与在线调试数据

数据与 API/apis/captcha_self/ 实际实现对齐（分类树 /api/captcha_self/ 为开放，无需签名）：
- self：自研生成引擎（Pillow 绘制），支持字符图片 / 算术两类，服务端生成 + 一次性校验。
后续新增验证码类型（如滑块）时在 channels / endpoints 追加即可。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ServiceSpec

SERVICE = ServiceSpec(
    slug='captcha_self',
    name='自研图形验证码',
    prefix='/api/captcha_self/',
    summary='自研图形验证码（字符图片 / 算术），Pillow 本地绘制、无第三方依赖，答案一次性校验。',
    channels=[
        ChannelSpec(
            slug='self',
            name='自研验证码',
            provider='SpiderServices/Captcha 自研生成引擎（Pillow 绘制）',
            auth_note='open',
            note='两步接入：先 generate 拿 captcha_id 与图片（base64），用户作答后 POST verify 校验；'
                 '答案一次性，校验后无论对错立即失效，需配合前端换新图。',
            endpoints=[
                EndpointSpec('generate', '生成验证码', 'GET', '/api/captcha_self/generate',
                             summary='生成一张验证码，返回 captcha_id、base64 图片与有效期。',
                             params=[
                                 ParamSpec('kind', '验证码类型', kind='select',
                                           options=[{'value': 'char', 'label': 'char（字符图片，默认）'},
                                                    {'value': 'arithmetic', 'label': 'arithmetic（算术）'}],
                                           default='char',
                                           desc='选填：char=字符图片（数字+大写字母）；arithmetic=算术加减法'),
                                 ParamSpec('length', '字符个数', kind='number', default='4',
                                           placeholder='4',
                                           desc='选填：仅 kind=char 生效，取值 4-6（默认 4）'),
                             ],
                             notes=['请求方式 GET，参数放 query string；公开接口，无需项目签名。',
                                    '返回 data.captcha_id 必须与答案一起回传给 verify；'
                                    'data.image 为 base64 data URI，可直接用于 <img src>；'
                                    'data.expire_in 为有效期（秒，默认 300）。']),
                EndpointSpec('verify', '校验验证码', 'POST', '/api/captcha_self/verify',
                             summary='提交用户答案校验，一次性消费（校验后立即失效）。',
                             params=[
                                 ParamSpec('captcha_id', '验证码ID', kind='text', required=True,
                                           placeholder='9f1c1f14-6b0a-4a3e-9c31-2c9b6f0d1a55',
                                           desc='必填：生成接口返回的 captcha_id（UUID）'),
                                 ParamSpec('answer', '用户答案', kind='text', required=True,
                                           placeholder='7H4K',
                                           desc='必填：用户填写的答案（字符不区分大小写；算术填计算结果）'),
                             ],
                             notes=['请求体为 application/x-www-form-urlencoded 表单；开放接口，无需项目签名。',
                                    '校验通过：code=10000 且 data.passed=true；',
                                    '未通过（答案错误 / 已过期 / 已使用 / 不存在）：code=20003 且 data.passed=false，原因见 msg；',
                                    'captcha_id 非 UUID 时返回 code=20002，参数缺失时返回 code=20001。',
                                    '答案一次性：同一条验证码重复提交只会成功一次，失败后需重新调用 generate。']),
            ],
        ),
    ],
)
