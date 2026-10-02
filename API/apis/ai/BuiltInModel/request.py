"""AI 服务 · 统一对话接口

提供 2 个接口：
    POST /api/ai/BuiltInModel/chat      统一对话：用 model 参数在多个模型间切换
    GET  /api/ai/BuiltInModel/models    可用模型清单（供调用方动态发现可选模型）

可用的模型、所属厂商、上游地址、平台 Key、系统提示词与采样参数（temperature /
max_tokens / stop）全部由后台「AI 模型」页（/console/ai/models/）维护，本文件不做
任何厂商判断 —— 厂商差异统一在 utils 里收口。**采样参数不接受调用方传入**：生成
行为由平台按模型统一控制，请求里带了会直接报参数值非法（避免静默失效）。

参数约定见各视图的 docstring；响应统一为 {"code", "msg", "data"}。
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


def _error_code(msg):
    """按《API开发规范》4.3 的约定，由错误文案前缀决定状态码"""
    if msg.startswith('参数缺失'):
        return StatusCode.PARAM_MISSING
    if msg.startswith('参数格式错误'):
        return StatusCode.PARAM_FORMAT_ERROR
    return StatusCode.PARAM_VALUE_INVALID


def _sampling(target):
    """这次调用使用的采样参数（由超管在后台按模型配置，调用方不可干预）

    留空的项不下发，交给上游默认值，因此后台没配任何项时行为与「不带这些参数」一致。
    """
    return {
        'temperature': target['temperature'],
        'max_tokens': target['max_tokens'],
        'stop': target['stop_list'],
    }


@require_http_methods(['POST'])
def chat_view(request):
    """统一对话接口：用 model 参数在多个模型间无缝切换

    表单参数(application/x-www-form-urlencoded):
        model         (选填): 模型标识，取值见 GET /api/ai/BuiltInModel/models
                               不传则使用后台设置的默认模型
        content       (选填): 单条用户消息内容，发起简单单轮对话时使用
        messages      (选填): 完整对话消息的 JSON 字符串，用于多轮对话
                               格式: [{"role": "user", "content": "你好"},
                                      {"role": "assistant", "content": "你好！"},
                                      {"role": "user", "content": "今天天气怎么样？"}]
                               优先级高于 content，两者同时提供时 messages 生效
        system_prompt (选填): 系统提示词，JSON 数组字符串，用于临时覆盖平台的设定
                               格式: [{"role": "system", "content": "你是数学老师，只回答数学问题"}]
                               - 不传 → 使用超管在后台按该模型配置的系统提示词
                               - 传入 JSON 数组 → 使用调用方自己的系统消息
                               - 传入空字符串 → 不使用任何系统提示词
        images        (选填): 图片地址，JSON 数组字符串或纯文本（按换行 / 逗号拆分）
                               仅支持视觉的模型可传，其余模型传了返回参数值非法
                               张数上限由平台按模型配置（后台可调），超限返回参数值非法
                               例: ["https://xxx.com/a.jpg"]
        videos        (选填): 视频地址，JSON 数组字符串或纯文本（按换行 / 逗号拆分）
                               仅支持视频理解的模型可传（如豆包 Seed 2.0 全模态），
                               其余模型传了返回参数值非法；数量上限同样由后台按模型配置
                               例: ["https://xxx.com/a.mp4"]
        audios        (选填): 音频地址，JSON 数组字符串或纯文本（按换行 / 逗号拆分）
                               仅支持音频理解的模型可传（如豆包 Seed 2.0 全模态），
                               其余模型传了返回参数值非法；个数上限同样由后台按模型配置
                               例: ["https://xxx.com/a.mp3"]
                               注：只接受可公网访问的 http/https 地址；音频文件可先经
                               平台的「文件上传」服务上传，再把返回的地址传到这里
        api_key       (选填): 调用方自带的 API Key（须与所选模型所属厂商一致）
                               不传则使用平台在后台配置的该厂商密钥
        stream        (选填): 是否开启流式对话，接受 "true" / "false"，默认 "false"
                               开启后响应格式变为 SSE(text/event-stream)

    注意:
        - content 和 messages 至少提供一个，否则返回参数缺失错误
        - temperature / max_tokens / stop 由平台按模型统一配置，**不接受调用方传入**，
          传了返回参数值非法（调整请到后台 /console/ai/models/ 改对应模型）
        - prefix / prefix_content（前缀续写）能力已下线，传 prefix=true 会返回参数值非法
    """
    return _handle_chat(request)


@require_http_methods(['GET'])
def models_view(request):
    """可用模型清单：供调用方动态发现可选模型（不含上游地址、厂商与密钥）

    返回 data.models 为数组，每项含:
        model            模型标识（即请求参数 model 的取值）
        name             展示名
        supports_vision  是否支持视觉（为 true 时才能传 images）
        supports_video   是否支持视频理解（为 true 时才能传 videos）
        supports_audio   是否支持音频理解（为 true 时才能传 audios）
        context_window   上下文长度（可为 null）
        is_default       是否为默认模型（请求不传 model 时使用）
    """
    return _json_response(StatusCode.SUCCESS, data={'models': utils.public_models()})


def _handle_chat(request):
    """统一对话处理：参数解析 / 校验 → 解析调用目标 → 调上游（流式或一次性返回）"""
    # ---------- 1. 参数获取 ----------
    content = request.POST.get('content', '').strip()
    messages_json = request.POST.get('messages', '').strip() or None
    system_prompt = request.POST.get('system_prompt', None)
    if system_prompt is not None:
        system_prompt = system_prompt.strip()
    api_key = request.POST.get('api_key', '').strip() or None
    model = request.POST.get('model', '').strip() or None
    stream_str = request.POST.get('stream', 'false').strip().lower()

    # ---------- 2. 参数校验 ----------
    # 已下线 / 已收归平台的参数：命中即明确报错，避免老客户端静默失效
    if (request.POST.get('prefix') or '').strip().lower() in ('true', '1', 'yes'):
        return _json_response(
            StatusCode.PARAM_VALUE_INVALID,
            msg='参数值非法: 前缀续写（prefix）能力已下线，请移除该参数',
        )
    for name in ('temperature', 'max_tokens', 'stop'):
        if (request.POST.get(name) or '').strip():
            return _json_response(
                StatusCode.PARAM_VALUE_INVALID,
                msg=f'参数值非法: {name} 已改由平台按模型统一配置，请移除该参数',
            )

    if stream_str not in ('true', 'false'):
        return _json_response(
            StatusCode.PARAM_FORMAT_ERROR,
            msg='参数格式错误: stream 仅接受 true 或 false',
        )
    stream = stream_str == 'true'

    images, error = utils.parse_images(request.POST.get('images'))
    if error:
        return _json_response(_error_code(error), msg=error)

    videos, error = utils.parse_videos(request.POST.get('videos'))
    if error:
        return _json_response(_error_code(error), msg=error)

    audios, error = utils.parse_audios(request.POST.get('audios'))
    if error:
        return _json_response(_error_code(error), msg=error)

    # ---------- 3. 解析调用目标（模型 → 厂商 → 地址与 Key / 提示词 / 采样参数） ----------
    target, error = utils.resolve_target(model_key=model, user_key=api_key)
    if error:
        return _json_response(error[0], msg=error[1])

    if images:
        if not target['supports_vision']:
            return _json_response(
                StatusCode.PARAM_VALUE_INVALID,
                msg=f'参数值非法: 模型「{target["key"]}」不支持视觉（images），请改用支持视觉的模型',
            )
        if len(images) > target['max_images']:
            return _json_response(
                StatusCode.PARAM_VALUE_INVALID,
                msg=f'参数值非法: 模型「{target["key"]}」最多支持 {target["max_images"]} 张图片',
            )

    if videos:
        if not target['supports_video']:
            return _json_response(
                StatusCode.PARAM_VALUE_INVALID,
                msg=f'参数值非法: 模型「{target["key"]}」不支持视频理解（videos），'
                    '请改用支持视频的模型',
            )
        if len(videos) > target['max_videos']:
            return _json_response(
                StatusCode.PARAM_VALUE_INVALID,
                msg=f'参数值非法: 模型「{target["key"]}」最多支持 {target["max_videos"]} 个视频',
            )

    if audios:
        if not target['supports_audio']:
            return _json_response(
                StatusCode.PARAM_VALUE_INVALID,
                msg=f'参数值非法: 模型「{target["key"]}」不支持音频理解（audios），'
                    '请改用支持音频的模型',
            )
        if len(audios) > target['max_audios']:
            return _json_response(
                StatusCode.PARAM_VALUE_INVALID,
                msg=f'参数值非法: 模型「{target["key"]}」最多支持 {target["max_audios"]} 个音频',
            )

    # ---------- 4. 构建 messages ----------
    try:
        messages = utils.build_messages(content, messages_json,
                                        system_prompt=system_prompt, images=images,
                                        videos=videos, audios=audios,
                                        platform_prompt=target['platform_prompt'])
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

    # ---------- 5. 调用上游 ----------
    if stream:
        return _stream_response(target, messages)
    return _normal_response(target, messages)


def _normal_response(target, messages):
    """非流式：等待完整回复后一次性返回统一 JSON"""
    ok, result = utils.chat_completion(target, messages, **_sampling(target))
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=result)
    return _json_response(StatusCode.SUCCESS, data=result)


def _stream_response(target, messages):
    """流式：返回 SSE(Server-Sent Events) 流

    每帧格式 data: {"content": "部分回复内容"}（答案正文）或
    data: {"reasoning": "…"}（推理模型的思考过程），结束标记 data: [DONE]。
    客户端按 SSE 标准解析并拼接所有 content 片段即得到完整回复。
    """
    def sse_generator():
        try:
            yield from utils.stream_chat_completion(target, messages, **_sampling(target))
        except ValueError as e:
            # 流启动阶段出错（Key 无效 / 地址不通 / 上游返回错误）
            yield f"data: {json.dumps({'code': StatusCode.EXTERNAL_API_FAILED, 'msg': str(e)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    response = StreamingHttpResponse(streaming_content=sse_generator(),
                                     content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'  # 禁用 nginx 缓冲，保证逐块推送
    return response
