"""DeepSeek AI 对话 API 请求处理视图

提供 1 个接口:
    POST /api/ai/BuiltInModel/deepseek  与 DeepSeek AI 对话

支持两种模式:
    - 非流式（默认）: 等待完整回复后一同返回
    - 流式: 通过 SSE(Server-Sent Events) 逐块推送回复内容
"""
import json

from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_http_methods

from API.common import StatusCode
from . import utils


def _json_response(code, data=None, msg=None):
    """构建统一的 JSON 响应体

    :param code: 状态码(参见 StatusCode)
    :param data: 业务数据,默认为 None
    :param msg:  自定义消息,未传则使用状态码对应的默认描述
    """
    return JsonResponse({
        'code': code,
        'msg': msg or StatusCode.get_message(code),
        'data': data,
    })


@require_http_methods(['POST'])
def deepseek_view(request):
    """
    与 DeepSeek AI 对话接口

    表单参数(application/x-www-form-urlencoded):
        content       (选填): 单条用户消息内容，发起简单单轮对话时使用
        messages      (选填): 完整对话消息的 JSON 字符串，用于多轮对话
                               格式: [{"role": "user", "content": "你好"},
                                      {"role": "assistant", "content": "你好！"},
                                      {"role": "user", "content": "今天天气怎么样？"}]
                               优先级高于 content，两者同时提供时 messages 生效
        system_prompt (选填): 系统消息的 JSON 数组字符串，用于设定 AI 角色行为
                               格式: [{"role": "system", "content": "你是数学老师，只回答数学问题"}]
                               - 不传 → 使用默认提示词（标识由 XiaoYingAPI 发起）
                               - 传入 JSON 数组 → 使用用户自定义的系统消息
                               - 传入空字符串 → 不使用任何系统提示词
                               注意: 数组内每项的 role 必须为 "system"，不支持其他 role
        api_key       (选填): 用户自定义 DeepSeek API Key
                               不传则使用 .env 中的 DEEPSEEK_API_KEY
        stream        (选填): 是否开启流式对话，接受 "true" / "false"，默认 "false"
                               开启后响应格式变为 SSE(text/event-stream)
        prefix        (选填): 是否开启前缀续写模式(Beta)，接受 "true" / "false"，默认 "false"
                               开启后:
                                 1. 自动切换到 DeepSeek Beta 接口
                                 2. 在 messages 末尾追加一条 assistant 消息，
                                    content 取自 prefix_content，并标记 prefix=True
                                 3. 模型会从该前缀内容继续续写
        prefix_content(选填): 前缀续写的起点文本，prefix=true 时必填
                               例如 "```python\n" 可强制模型续写 Python 代码
        stop          (选填): 停止词，JSON 数组字符串或纯文本，可选
                               前缀续写常用 stop 避免模型输出多余内容
                               例如 ["```"] 让模型输出到代码块结束符即停止
                               - JSON 数组: "[\"```\", \"END\"]"
                               - 单个字符串: "```" (会自动包装为单元素数组)

    注意:
        - content 和 messages 至少提供一个，否则返回参数缺失错误
        - prefix=true 时 prefix_content 必填
    """
    # ---------- 1. 参数获取与校验 ----------
    content = request.POST.get('content', '').strip()
    messages_json = request.POST.get('messages', '').strip() or None
    system_prompt = request.POST.get('system_prompt', None)
    if system_prompt is not None:
        system_prompt = system_prompt.strip()
    api_key = request.POST.get('api_key', '').strip() or None
    stream_str = request.POST.get('stream', 'false').strip().lower()
    prefix_str = request.POST.get('prefix', 'false').strip().lower()
    prefix_content = request.POST.get('prefix_content', '').strip()
    stop_raw = request.POST.get('stop', '').strip()

    # stream 参数校验
    if stream_str not in ('true', 'false'):
        return _json_response(
            StatusCode.PARAM_FORMAT_ERROR,
            msg='参数格式错误: stream 仅接受 true 或 false',
        )
    stream = stream_str == 'true'

    # prefix 参数校验
    if prefix_str not in ('true', 'false'):
        return _json_response(
            StatusCode.PARAM_FORMAT_ERROR,
            msg='参数格式错误: prefix 仅接受 true 或 false',
        )
    prefix = prefix_str == 'true'

    # 前缀续写模式必填 prefix_content
    if prefix and not prefix_content:
        return _json_response(
            StatusCode.PARAM_MISSING,
            msg='参数缺失: prefix_content(前缀续写内容，prefix=true 时必填)',
        )

    # 解析 stop 参数: 兼容 JSON 数组字符串与纯文本
    stop_list = None
    if stop_raw:
        try:
            parsed = json.loads(stop_raw)
            if isinstance(parsed, list):
                # 校验数组元素必须为字符串
                if not all(isinstance(s, str) for s in parsed):
                    return _json_response(
                        StatusCode.PARAM_FORMAT_ERROR,
                        msg='参数格式错误: stop 数组内所有元素必须为字符串',
                    )
                stop_list = parsed
            elif isinstance(parsed, str):
                # JSON 字符串（如 "\"```\""），自动包装为单元素数组
                stop_list = [parsed]
            else:
                return _json_response(
                    StatusCode.PARAM_FORMAT_ERROR,
                    msg='参数格式错误: stop 必须为字符串或字符串数组',
                )
        except json.JSONDecodeError:
            # 不是合法 JSON，当作纯字符串处理
            stop_list = [stop_raw]

    # ---------- 2. 构建 messages ----------
    try:
        messages = utils._build_messages(content, messages_json, system_prompt=system_prompt)
    except json.JSONDecodeError:
        return _json_response(
            StatusCode.PARAM_FORMAT_ERROR,
            msg='参数格式错误: messages 不是合法的 JSON',
        )
    except ValueError as e:
        return _json_response(
            StatusCode.PARAM_VALUE_INVALID,
            msg=f'参数值非法: {e}',
        )

    # 前缀续写模式: 在 messages 末尾追加 assistant 前缀消息
    # DeepSeek 要求最后一条消息 role 为 assistant 且 prefix=True
    if prefix:
        messages.append({
            "role": "assistant",
            "content": prefix_content,
            "prefix": True,
        })

    # ---------- 3. 调用 DeepSeek API ----------
    if stream:
        # 流式模式: 返回 StreamingHttpResponse
        return _handle_stream_response(messages, api_key, prefix=prefix, stop=stop_list)
    else:
        # 非流式模式: 返回 JsonResponse
        return _handle_normal_response(messages, api_key, prefix=prefix, stop=stop_list)


def _handle_normal_response(messages, api_key, prefix=False, stop=None):
    """非流式对话: 调用 API 获取完整回复，返回统一 JSON 响应。"""
    success, result = utils.chat_completion(messages, api_key=api_key, prefix=prefix, stop=stop)
    if not success:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=result)
    return _json_response(StatusCode.SUCCESS, data=result)


def _handle_stream_response(messages, api_key, prefix=False, stop=None):
    """
    流式对话: 返回 SSE(Server-Sent Events) 流。

    响应格式为 text/event-stream，每行格式:
        data: {"content": "部分回复内容"}

    流结束标记:
        data: [DONE]

    客户端需按 SSE 标准解析，拼接所有 content 片段得到完整回复。
    """
    def sse_generator():
        try:
            yield from utils.stream_chat_completion(messages, api_key=api_key, prefix=prefix, stop=stop)
        except ValueError as e:
            # 流启动阶段出错（Key 未配置/网络不通/API 返回错误）
            yield f"data: {json.dumps({'code': StatusCode.EXTERNAL_API_FAILED, 'msg': str(e)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    response = StreamingHttpResponse(
        streaming_content=sse_generator(),
        content_type='text/event-stream',
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'  # 禁用 nginx 缓冲
    return response
