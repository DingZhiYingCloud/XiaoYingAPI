"""AI 服务 - 接口文档与在线调试数据

数据与 API/apis/ai/ 实际实现对齐（服务策略 /api/ai/ 默认需签名）：
- BuiltInModel：平台内置模型（平台 Key、系统提示词、采样参数全部由后台
  /console/ai/models/ 维护），用一个 chat 端点覆盖多家厂商，调用方只改 model 参数
  即可无缝切换。

注意：`model` 的候选项**不写死在这里**，而是用 dynamic_options='ai_models' 在渲染前
从数据库取（见 docs/OPTION_LOADERS），后台加模型后文档下拉立即跟着变。
新增厂商 / 模型 / 提示词属于后台配置操作，不需要改本文件。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ServiceSpec

_BOOL_OPT = [
    {'value': 'false', 'label': 'false（默认）'},
    {'value': 'true', 'label': 'true'},
]

_MESSAGES_EG = ('[{"role": "user", "content": "你好"},'
                '{"role": "assistant", "content": "你好！"},'
                '{"role": "user", "content": "今天天气怎么样？"}]')

SERVICE = ServiceSpec(
    slug='ai',
    name='AI 服务',
    prefix='/api/ai/',
    summary='多模型 AI 对话接口：用 model 参数在多家厂商的模型间切换，'
            '单轮 / 多轮、流式、图片理解（部分模型）一应俱全。',
    keywords='AI API,免费AI接口,大模型API,AI对话接口,DeepSeek API,Kimi API,豆包API,千问API',
    intro=[
        'AI 服务提供开箱即用的对话能力，已接入多家厂商的模型（当前含 DeepSeek）；'
        '平台侧统一持有各厂商密钥，调用方无需自行申请与配置，适合做内容生成、摘要、'
        '问答等功能的快速验证。',
        '切换模型只需改 model 一个参数，接口地址、鉴权方式与响应结构完全不变：'
        '候选模型见下方「模型清单」接口，或直接看 chat 端点的 model 下拉。'
        '新增模型由超管在后台添加，对大模型厂商的差异（上游地址、密钥、能力）'
        '全部在服务端收口。',
        '同一个接口覆盖单轮与多轮对话：传 content 发起简单单轮问答，传 messages'
        '（JSON 数组，含 role 与 content）则进行多轮对话；同时支持流式输出。',
        '系统提示词由平台按模型统一配置（超管在后台维护，可设多套并指定某个模型用哪一套），'
        '调用方不需要、也不能改生成策略——采样温度、最大回复长度、停止词同样由平台控制，'
        '接口不接受这些参数，从而保证所有接入方拿到的行为一致、可控。',
        '标记了「支持视觉」的模型可以额外传 images（公网图片地址）让它看图回答；'
        '未标记的模型传图片会返回参数值非法，避免把参数静默丢掉。',
        '本服务需项目签名。开启流式（stream=true）后返回的是逐段推送的 SSE 内容，'
        '与普通 JSON 响应的呈现方式不同，在文档页在线调试时会逐字打印出来。',
    ],
    channels=[
        ChannelSpec(
            slug='builtin_model',
            name='内置模型',
            provider='平台内置密钥（DeepSeek / 月之暗面 / 火山方舟 / 阿里云百炼等，均可后台扩展）',
            auth_note='auth',
            note='一个 chat 端点覆盖全部模型：换模型只改 model 参数；平台密钥、上游地址、系统提示词与采样参数由超管在后台维护。',
            endpoints=[
                EndpointSpec('chat', 'AI 对话（统一入口）', 'POST', '/api/ai/BuiltInModel/chat',
                             summary='用 model 选择模型发起对话：支持单条消息、完整消息列表、'
                                     '系统提示词覆盖、图片理解与流式输出。',
                             params=[
                                 ParamSpec('model', '模型', kind='select', default='',
                                           dynamic_options='ai_models',
                                           desc='选填：不传则使用平台默认模型；候选清单来自平台（见「模型清单」接口）'),
                                 ParamSpec('content', '单条消息内容', kind='textarea',
                                           placeholder='你好，介绍一下你自己',
                                           desc='选填：发起简单单轮对话时的消息内容（与 messages 至少提供一个）'),
                                 ParamSpec('messages', '完整对话消息(JSON)', kind='textarea',
                                           placeholder=_MESSAGES_EG,
                                           desc='选填：多轮对话用，格式为 JSON 数组，role 取 user/assistant；优先级高于 content'),
                                 ParamSpec('system_prompt', '系统提示词(JSON)', kind='textarea',
                                           placeholder='[{"role": "system", "content": "你是数学老师，只回答数学问题"}]',
                                           desc='选填：临时覆盖平台设定；不传=用平台按模型配置的提示词；空字符串=不使用系统提示词'),
                                 ParamSpec('images', '图片地址', kind='textarea',
                                           placeholder='["https://xxx.com/a.jpg"]',
                                           desc='选填：仅「支持视觉」的模型可传；JSON 数组或纯文本（换行/逗号分隔）的公网图片地址，张数上限由平台按模型配置（后台可调）'),
                                 ParamSpec('api_key', '自定义模型 Key', kind='password',
                                           placeholder='sk-…',
                                           desc='选填：传了就用调用方自己的 Key（须与所选模型所属厂商一致），不传则用平台密钥'),
                                 ParamSpec('stream', '流式输出(SSE)', kind='select', options=_BOOL_OPT,
                                           default='false', desc='选填：true 时响应为 SSE(text/event-stream)，逐块推送'),
                             ],
                             notes=['请求体为 application/x-www-form-urlencoded 表单；本服务需项目签名。',
                                    'content 与 messages 至少提供一个，否则返回参数缺失。',
                                    'images 仅对「支持视觉」的模型有效，其它模型传了返回参数值非法（20003）；'
                                    '张数上限由平台按模型配置（后台可调），超限同样返回参数值非法。',
                                    '采样温度 / 最大回复长度 / 停止词由平台按模型统一配置，不接受调用方传入，'
                                    '传了会返回参数值非法（20003）。',
                                    '流式模式返回 SSE：每帧形如 data: {"content": "片段"}（答案正文）或'
                                    ' data: {"reasoning": "片段"}（推理模型的思考过程，仅这类模型有，'
                                    '与答案分开下发、只关心答案可忽略），结束标记 data: [DONE]；'
                                    '在线调试会逐字打印，推理模型在给出答案前会先流一段思考内容。',
                                    '在线调用会真实消耗上游额度，请确认平台密钥可用后再调试。',
                                    '原「前缀续写（prefix / prefix_content）」能力已下线，传入会返回参数值非法。']),
                EndpointSpec('models', '模型清单', 'GET', '/api/ai/BuiltInModel/models',
                             summary='列出平台当前可用的模型（标识、展示名、是否支持视觉、是否为默认模型）。',
                             notes=['用于让调用方动态发现可选模型，避免把模型名写死在客户端。',
                                    '只返回模型自身信息：不含厂商、上游地址与密钥。',
                                    '请求不传 model 时使用 is_default 为 true 的那个模型。']),
            ],
        ),
    ],
)
