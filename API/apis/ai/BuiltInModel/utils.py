"""DeepSeek AI 对话 API 调用封装

本模块封装对 DeepSeek Chat API 的调用，支持流式与非流式两种模式。
API Key 优先级：用户传入 > .env 配置的默认密钥。
"""
import json
import os

import requests

# DeepSeek Chat API 基础地址（标准 OpenAI 兼容接口）
DEEPSEEK_CHAT_URL = "https://api.deepseek.com/chat/completions"
# 默认模型
DEFAULT_MODEL = "deepseek-chat"

# ==================== 系统提示词 ====================
# 当用户未提供自定义 system_prompt 时，使用此默认值
# 用于在对话开始时设定 AI 的角色与行为边界
DEFAULT_SYSTEM_PROMPT = "你正在被 XiaoYingAPI 调用，当前用户为 API 的调用方。请提供准确、简洁、有用的回答。在涉及代码、配置等内容时，以清晰的结构化方式输出。"


def _get_api_key(user_key=None):
    """
    获取 API Key。
    优先级: 用户传入 > .env 环境变量。

    :param user_key: 用户提供的 API Key，可选
    :return: API Key 字符串；未配置时返回空字符串
    """
    return (user_key or os.getenv('DEEPSEEK_API_KEY', '')).strip()


def _build_messages(content, messages_json=None, system_prompt=None):
    """
    构建 messages 参数，自动在首位插入系统消息。

    系统提示词逻辑:
        - 若传入了 system_prompt 且为合法的 JSON 数组，使用该数组
        - 若未传入(None)，使用 DEFAULT_SYSTEM_PROMPT
        - 若传入空字符串("")，不使用系统提示词
        - system_prompt 数组中每项 role 必须为 "system"，否则抛出 ValueError

    :param content: 单条用户消息内容
    :param messages_json: 完整对话消息的 JSON 字符串，可选
    :param system_prompt: 系统消息的 JSON 数组字符串，可选
                          - None/不传 → 使用默认 DEFAULT_SYSTEM_PROMPT
                          - "[{"role":"system","content":"..."}]" → 使用用户自定义
                          - ""(空字符串) → 不使用系统提示词
    :return: messages 列表
    :raises ValueError: JSON 格式错误或 role 校验失败时抛出
    """
    if messages_json:
        # 用户提供了完整 messages，优先使用
        messages = json.loads(messages_json)
        if not isinstance(messages, list):
            raise ValueError("messages 必须为 JSON 数组")
        if not messages:
            raise ValueError("messages 不能为空")
    else:
        # 退回到单条 content
        if not content:
            raise ValueError("content 或 messages 至少提供一个")
        messages = [{"role": "user", "content": content}]

    # 在首位插入系统消息
    system_msgs = _resolve_system_messages(system_prompt)
    if system_msgs:
        messages = system_msgs + messages

    return messages


def _resolve_system_messages(system_prompt):
    """
    解析最终使用的系统消息列表。

    :param system_prompt: 用户传入的 system_prompt 值
    :return: list[dict] 系统消息列表；若无需插入则返回 None
    :raises ValueError: JSON 解析失败或含非 system role 时抛出
    """
    if system_prompt is None:
        # 未传入 → 使用默认
        return [{"role": "system", "content": DEFAULT_SYSTEM_PROMPT}]
    if system_prompt == '':
        # 显式传入空字符串 → 不使用系统提示词
        return None

    # 解析用户传入的 JSON 数组
    try:
        msgs = json.loads(system_prompt)
    except json.JSONDecodeError:
        raise ValueError("system_prompt 不是合法的 JSON 数组")

    if not isinstance(msgs, list):
        raise ValueError("system_prompt 必须为 JSON 数组")
    if not msgs:
        raise ValueError("system_prompt 不能为空数组")

    # 校验每项 role 必须为 "system"
    for item in msgs:
        if not isinstance(item, dict) or item.get("role") != "system":
            raise ValueError(
                f'system_prompt 仅支持 role 为 "system" 的消息, 不支持 role="{item.get("role")}"'
            )

    return msgs


def _handle_api_error(resp):
    """
    处理 DeepSeek API 的错误响应，提取可读的错误信息。

    :param resp: requests.Response 对象
    :return: 错误信息字符串
    """
    try:
        data = resp.json()
        error = data.get("error", {})
        if isinstance(error, dict):
            return error.get("message", str(data))
        return str(data)
    except (ValueError, AttributeError):
        return resp.text or f"HTTP {resp.status_code}"


def chat_completion(messages, api_key=None, model=DEFAULT_MODEL, timeout=120):
    """
    非流式调用 DeepSeek Chat API，返回完整响应。

    :param messages: 消息列表 [{"role": "user", "content": "..."}]
    :param api_key: 用户自定义 API Key，可选
    :param model: 模型名称，默认 deepseek-chat
    :param timeout: 请求超时时间（秒），默认 120（AI 生成较慢）
    :return: tuple[bool, Any]
        - 成功: (True, {"reply": str, "model": str, "usage": dict})
        - 失败: (False, 错误信息str)
    """
    key = _get_api_key(api_key)
    if not key:
        return False, 'DeepSeek API Key 未配置，请在 .env 中设置 DEEPSEEK_API_KEY 或在请求时传入 api_key'

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
    }

    try:
        resp = requests.post(
            DEEPSEEK_CHAT_URL, json=payload, headers=headers, timeout=timeout
        )
    except requests.RequestException as e:
        return False, f'请求 DeepSeek API 失败: {e}'

    if resp.status_code != 200:
        return False, f'DeepSeek API 返回错误 ({resp.status_code}): {_handle_api_error(resp)}'

    try:
        data = resp.json()
    except ValueError as e:
        return False, f'解析 DeepSeek API 响应失败: {e}'

    # 提取助手回复
    choices = data.get("choices", [])
    if not choices:
        return False, 'DeepSeek API 返回异常: choices 为空'

    reply = choices[0].get("message", {}).get("content", "")
    return True, {
        "reply": reply,
        "model": data.get("model", model),
        "usage": data.get("usage"),
    }


def stream_chat_completion(messages, api_key=None, model=DEFAULT_MODEL, timeout=120):
    """
    流式调用 DeepSeek Chat API，生成器逐块 yield SSE 格式数据。

    每个 yield 输出一条 SSE 格式的文本行:
        data: {"content": "部分回复内容"}

    流结束标记:
        data: [DONE]

    错误处理:
        首次 yield 前出错 → 抛出异常（由调用方处理）
        流中出错 → yield 错误 SSE 行后结束

    :param messages: 消息列表
    :param api_key: 用户自定义 API Key，可选
    :param model: 模型名称，默认 deepseek-chat
    :param timeout: 请求超时时间（秒），默认 120
    :yield: SSE 格式字符串
    :raises ValueError: API Key 未配置时抛出
    """
    key = _get_api_key(api_key)
    if not key:
        raise ValueError('DeepSeek API Key 未配置')

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
    }

    try:
        resp = requests.post(
            DEEPSEEK_CHAT_URL,
            json=payload,
            headers=headers,
            stream=True,
            timeout=timeout,
        )
    except requests.RequestException as e:
        raise ValueError(f'请求 DeepSeek API 失败: {e}')

    if resp.status_code != 200:
        error_msg = _handle_api_error(resp)
        raise ValueError(f'DeepSeek API 返回错误 ({resp.status_code}): {error_msg}')

    # 逐行读取 SSE 流
    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        # SSE 格式: "data: {...}"
        if line.startswith("data: "):
            chunk_data = line[6:]  # 去掉 "data: " 前缀

            # 流结束标记
            if chunk_data == "[DONE]":
                yield "data: [DONE]\n\n"
                return

            # 解析 delta 内容
            try:
                chunk = json.loads(chunk_data)
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    yield f"data: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"
            except json.JSONDecodeError:
                # 非 JSON 行直接透传（极少发生，做安全兜底）
                yield f"data: {chunk_data}\n\n"
