"""自研图形验证码 - 接口文档与在线调试数据

数据与 API/apis/captcha_self/ 实际实现对齐（服务策略 /api/captcha_self/ 为开放，无需签名）：
- self：自研生成引擎（Pillow 绘制），支持字符图片 / 算术两类，服务端生成 + 一次性校验。
后续新增验证码类型（如滑块）时在 channels / endpoints 追加即可。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ResponseFieldSpec, ServiceSpec

SERVICE = ServiceSpec(
    slug='captcha_self',
    name='自研图形验证码',
    prefix='/api/captcha_self/',
    summary='自研图形验证码（字符图片 / 算术），Pillow 本地绘制、无第三方依赖，答案一次性校验。',
    keywords='图形验证码API,字符验证码,算术验证码',
    intro=[
        '自研图形验证码不依赖任何第三方服务，由平台用 Pillow 在本地绘制字符图片或算术题，'
        '适合对数据外发敏感、或希望零成本自建验证码的场景。',
        '接入为两步：先调用生成接口拿到 captcha_id 与 base64 图片（带有效期），用户作答后调用校验接口提交答案。'
        '答案是「一次性」的——无论校验成功还是失败都会立即失效，失败后需重新生成再试。'
        '服务端只保存答案的 HMAC-SHA256 摘要，不落明文。',
        '该线路为开放接口，无需项目签名；服务端已按客户端 IP 限流（生成 60 次/分、校验 120 次/分），'
        '并在响应上禁用缓存，避免图片被浏览器 / 代理复用。',
        '同一服务下另有「滑块验证」与「汉字点选」线路：前者拖动拼图块对齐缺口，后者按提示依次点击 2-4 个汉字；'
        '两者的答案坐标都不下发，只存服务端用于校验。',
        '三条线路怎么选：表单防刷优先字符 / 算术（生成快、体积小）；想要拖动体验用滑块；'
        '面向中文用户、希望更直观可以用汉字点选。',
    ],
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
                                    'captcha_id 必须与答案一起回传给 verify；image 可直接用作 <img src>。',
                                    '响应头带 Cache-Control: no-store，图片不会被浏览器 / 代理缓存复用。',
                                    '同一 IP 每分钟最多生成 60 张，超出返回 20040。'],
                             response_fields=[
                                 ResponseFieldSpec('captcha_id', 'string', '验证码ID，校验时回传'),
                                 ResponseFieldSpec('kind', 'string', '类型：char/arithmetic'),
                                 ResponseFieldSpec('image', 'string', 'base64 图片（data URI）'),
                                 ResponseFieldSpec('expire_in', 'int', '有效期（秒）'),
                             ],
                             response_example='{"captcha_id": "9f1c1f14-6b0a-4a3e-9c31-2c9b6f0d1a55", "kind": "char", "image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg...", "expire_in": 300}'),
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
                                    '答案一次性：同一条验证码重复提交只会成功一次，失败后需重新调用 generate。',
                                    '同一 IP 每分钟最多校验 120 次，超出返回 20040；答案用恒定时间比较，库中只存摘要。'],
                             response_fields=[
                                 ResponseFieldSpec('passed', 'bool', '是否校验通过'),
                             ],
                             response_example='{"passed": true}'),
            ],
        ),
        ChannelSpec(
            slug='slider',
            name='滑块验证',
            provider='Pillow 本地合成（背景图 + 拼图块）',
            auth_note='open',
            note='拖动拼图块对齐缺口；缺口横坐标不下发，服务端按 ±8px 容差比对摘要，'
                 '并校验拖动轨迹（点数 / 时长 / 时间单调 / 终点一致）。',
            endpoints=[
                EndpointSpec('slider_generate', '生成滑块', 'GET',
                             '/api/captcha_self/slider/generate',
                             summary='生成背景图与拼图块，返回 slider_id、纵坐标与画布尺寸。',
                             notes=['请求方式 GET，公开接口，无需项目签名。',
                                    'background 为 JPEG、piece 为 PNG（均为 data URI）；'
                                    '**缺口横坐标不在响应里**，必须由用户拖动拼图块对齐。',
                                    '同一 IP 每分钟最多生成 30 张，超出返回 20040；响应禁止缓存。'],
                             tool_path='/captcha_self/slider/',
                             tool_label='拖动体验',
                             response_fields=[
                                 ResponseFieldSpec('slider_id', 'string', '滑块ID，校验时回传'),
                                 ResponseFieldSpec('background', 'string', '背景图（JPEG data URI）'),
                                 ResponseFieldSpec('piece', 'string', '拼图块（PNG data URI，透明背景）'),
                                 ResponseFieldSpec('piece_y', 'int', '拼图块纵向位置（像素）'),
                                 ResponseFieldSpec('piece_size', 'int', '拼图块边长（像素）'),
                                 ResponseFieldSpec('width', 'int', '画布宽度（像素，320）'),
                                 ResponseFieldSpec('height', 'int', '画布高度（像素，160）'),
                                 ResponseFieldSpec('expire_in', 'int', '有效期（秒）'),
                             ],
                             response_example='{"slider_id": "9f1c1f14-6b0a-4a3e-9c31-2c9b6f0d1a55", "background": "data:image/jpeg;base64,/9j/4AAQ…", "piece": "data:image/png;base64,iVBORw0KGgo…", "piece_y": 42, "piece_size": 52, "width": 320, "height": 160, "expire_in": 180}'),
                EndpointSpec('slider_verify', '校验滑块', 'POST',
                             '/api/captcha_self/slider/verify',
                             summary='提交拼图块位置与拖动轨迹，一次性校验。',
                             params=[
                                 ParamSpec('slider_id', '滑块ID', kind='text', required=True,
                                           placeholder='9f1c1f14-6b0a-4a3e-9c31-2c9b6f0d1a55',
                                           desc='必填：生成接口返回的 slider_id（UUID）'),
                                 ParamSpec('x', '横向位置', kind='number', required=True,
                                           placeholder='128.5',
                                           desc='必填：拼图块左边缘的画布横坐标（可带小数）'),
                                 ParamSpec('track', '拖动轨迹', kind='textarea', required=True,
                                           placeholder='[{"x":0,"t":0},{"x":30,"t":120}]',
                                           desc='必填：JSON 数组，元素为 {"x": 画布坐标, "t": 相对毫秒}；'
                                                '至少 5 个点，总时长 200ms-60s，终点须与 x 一致'),
                             ],
                             notes=['请求体为 application/x-www-form-urlencoded 表单；公开接口，无需项目签名。',
                                    '位置误差 ±8px 内视为对齐；缺口横坐标不下发，库中只存摘要。',
                                    '轨迹点数不足 / 用时过短 / 时间倒退 / 终点与 x 不一致都会被拒绝。',
                                    '一次性：无论成功失败，同一 slider_id 只能校验一次。',
                                    '同一 IP 每分钟最多校验 60 次；连续失败 10 次冷却 10 分钟，'
                                    '两种拦截都返回 20040。'],
                             response_fields=[ResponseFieldSpec('passed', 'bool', '是否校验通过')],
                             response_example='{"passed": true}'),
            ],
        ),
        ChannelSpec(
            slug='click',
            name='汉字点选',
            provider='Pillow + 内置中文字体（8 个候选汉字，点选 2-4 个）',
            auth_note='open',
            note='按提示依次点击目标汉字；目标坐标不下发，服务端校验点击顺序、命中位置与总用时。',
            endpoints=[
                EndpointSpec('click_generate', '生成点选验证码', 'GET',
                             '/api/captcha_self/click/generate',
                             summary='生成一张含 8 个候选汉字的图片，返回挑战ID、图片与目标字顺序。',
                             notes=['请求方式 GET，公开接口，无需项目签名。',
                                    'chars 是**按顺序**需要点击的目标字（2-4 个）；'
                                    '每个字的坐标不在响应里，服务端只落库用于命中判断。',
                                    '同一 IP 每分钟最多生成 30 张，超出返回 20040；响应禁止缓存。'],
                             tool_path='/captcha_self/click/',
                             tool_label='点选体验',
                             response_fields=[
                                 ResponseFieldSpec('challenge_id', 'string', '挑战ID，校验时回传'),
                                 ResponseFieldSpec('image', 'string', '验证码图片（PNG data URI）'),
                                 ResponseFieldSpec('chars', 'array', '按顺序需要点击的目标汉字'),
                                 ResponseFieldSpec('count', 'int', '目标字个数（2-4）'),
                                 ResponseFieldSpec('width', 'int', '画布宽度（像素，360）'),
                                 ResponseFieldSpec('height', 'int', '画布高度（像素，200）'),
                                 ResponseFieldSpec('expire_in', 'int', '有效期（秒）'),
                             ],
                             response_example='{"challenge_id": "9f1c1f14-6b0a-4a3e-9c31-2c9b6f0d1a55", "image": "data:image/png;base64,iVBORw0KGgo…", "chars": ["山", "河", "云"], "count": 3, "width": 360, "height": 200, "expire_in": 180}'),
                EndpointSpec('click_verify', '校验点选', 'POST',
                             '/api/captcha_self/click/verify',
                             summary='提交按顺序的点击点，校验顺序、命中位置与总用时。',
                             params=[
                                 ParamSpec('challenge_id', '挑战ID', kind='text', required=True,
                                           placeholder='9f1c1f14-6b0a-4a3e-9c31-2c9b6f0d1a55',
                                           desc='必填：生成接口返回的 challenge_id（UUID）'),
                                 ParamSpec('points', '点击点', kind='textarea', required=True,
                                           placeholder='[{"x":120,"y":66,"t":0},{"x":210,"y":80,"t":520}]',
                                           desc='必填：JSON 数组，元素为 {"x": 画布横坐标, "y": 画布纵坐标, '
                                                '"t": 相对毫秒}；点数须等于 count，总时长不少于 300ms'),
                             ],
                             notes=['请求体为 application/x-www-form-urlencoded 表单；公开接口，无需项目签名。',
                                    '点击顺序必须与 chars 一致；每个点需落在对应目标字半径 26px 内。',
                                    '点数不符 / 顺序错 / 点偏 / 总用时不足 300ms 都会被拒绝。',
                                    '一次性：无论成功失败，同一 challenge_id 只能校验一次。',
                                    '同一 IP 每分钟最多校验 60 次；连续失败 10 次冷却 10 分钟，'
                                    '两种拦截都返回 20040。'],
                             response_fields=[ResponseFieldSpec('passed', 'bool', '是否校验通过')],
                             response_example='{"passed": true}'),
            ],
        ),
    ],
)
