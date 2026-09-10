"""AI 服务 - 接口文档与在线调试数据

数据与 API/apis/ai/ 实际实现对齐（分类树 /api/ai/ 为需签名）：
- BuiltInModel：内置模型能力，当前为 DeepSeek 对话（支持多轮/系统提示词/流式/前缀续写）。
后续接入更多模型厂商时在 channels 追加即可。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ServiceSpec

_BOOL_OPT = [
    {'value': 'false', 'label': 'false（默认）'},
    {'value': 'true', 'label': 'true'},
]

_MODEL_OPT = [
    {'value': '', 'label': '不传（默认 deepseek-v4-flash）'},
    {'value': 'deepseek-v4-flash', 'label': 'deepseek-v4-flash（快速版）'},
    {'value': 'deepseek-v4-pro', 'label': 'deepseek-v4-pro（专业版）'},
]

_MESSAGES_EG = ('[{"role": "user", "content": "你好"},'
                '{"role": "assistant", "content": "你好！"},'
                '{"role": "user", "content": "今天天气怎么样？"}]')

SERVICE = ServiceSpec(
    slug='ai',
    name='AI 服务',
    prefix='/api/ai/',
    summary='内置模型能力，开箱即用的 AI 对话接口。当前接入 DeepSeek 内置模型（含多轮对话、流式、前缀续写）。',
    channels=[
        ChannelSpec(
            slug='builtin_model',
            name='DeepSeek 内置模型',
            provider='DeepSeek（平台内置 API Key）',
            auth_note='auth',
            note='一个接口覆盖单轮/多轮对话；不传 api_key 时使用平台 .env 配置的 DeepSeek Key。',
            endpoints=[
                EndpointSpec('deepseek', 'DeepSeek AI 对话', 'POST', '/api/ai/BuiltInModel/deepseek',
                             summary='与 DeepSeek 对话：支持单条消息、完整消息列表、系统提示词、流式/前缀续写。',
                             params=[
                                 ParamSpec('content', '单条消息内容', kind='textarea',
                                           placeholder='你好，介绍一下你自己',
                                           desc='选填：发起简单单轮对话时的消息内容（与 messages 至少提供一个）'),
                                 ParamSpec('messages', '完整对话消息(JSON)', kind='textarea',
                                           placeholder=_MESSAGES_EG,
                                           desc='选填：多轮对话用，格式为 JSON 数组，role 取 user/assistant；优先级高于 content'),
                                 ParamSpec('system_prompt', '系统提示词(JSON)', kind='textarea',
                                           placeholder='[{"role": "system", "content": "你是数学老师，只回答数学问题"}]',
                                           desc='选填：设定 AI 角色；不传=平台默认提示词；空字符串=不使用系统提示词'),
                                 ParamSpec('api_key', '自定义 DeepSeek Key', kind='password',
                                           placeholder='sk-…', desc='选填：不传则用平台 .env 的 DEEPSEEK_API_KEY'),
                                 ParamSpec('stream', '流式输出(SSE)', kind='select', options=_BOOL_OPT,
                                           default='false', desc='选填：true 时响应为 SSE(text/event-stream)，逐块推送'),
                                 ParamSpec('prefix', '前缀续写(Beta)', kind='select', options=_BOOL_OPT,
                                           default='false',
                                           desc='选填：true 时自动切 Beta 接口，从 prefix_content 继续续写'),
                                 ParamSpec('prefix_content', '续写起点文本', kind='textarea',
                                           placeholder='例如：```python\n',
                                           desc='选填：prefix=true 时必填，模型会从该文本继续输出'),
                                 ParamSpec('stop', '停止词', kind='text',
                                           placeholder='["```"] 或 ```',
                                           desc='选填：JSON 字符串数组或纯文本；前缀续写常用来限定输出边界'),
                                 ParamSpec('model', '模型名称', kind='select', options=_MODEL_OPT,
                                           desc='选填：deepseek-v4-flash（默认）/ deepseek-v4-pro'),
                             ],
                             notes=['请求体为 application/x-www-form-urlencoded 表单；本服务需项目签名。',
                                    'content 与 messages 至少提供一个，否则返回参数缺失。',
                                    '流式模式返回 SSE（data: {...} … data: [DONE]），在线调试会以原文展示，无法在结果区逐字流式播放。',
                                    '在线调用会真实消耗平台 DeepSeek 额度，请确认 Key/额度可用后再调试。']),
            ],
        ),
    ],
)
