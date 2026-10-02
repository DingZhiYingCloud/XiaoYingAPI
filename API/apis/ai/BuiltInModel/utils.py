"""AI 服务 · 厂商无关的对话调用门面

对外只暴露「统一对话」能力：调用方用请求参数 `model` 选模型，本模块负责
查模型注册表（`ai_provider` / `ai_model` / `ai_system_prompt` 三张表）→ 解开该厂商的
平台 Key → 组装 OpenAI 兼容请求（系统提示词与采样参数由后台按模型配置）→
把响应与流归一化成统一结构。

为什么一套客户端就能覆盖多家厂商：DeepSeek / 月之暗面（Kimi）/ 火山方舟（豆包）/
阿里云百炼（千问）都提供 **OpenAI 兼容**的 `/chat/completions`，请求体、响应体、
SSE 分片格式一致；厂商差异只体现在「地址 + Key + 模型名」三项，全部由数据库驱动。
真出现非 OpenAI 兼容的厂商时，再在这一层加分支或抽出适配器。

模型清单带进程内 TTL 缓存（默认 60 秒，与 API 服务策略缓存的风格一致）；
后台增删改厂商 / 模型 / 系统提示词后由 API/apps.py 的信号调用 `invalidate_models_cache()`
立即失效，改动即时生效、无需等 TTL。**缓存的只有模型元信息与提示词正文，不含任何 Key**
——平台 Key 在每次调用时按需查库并解密，避免密钥长期驻留在进程缓存里。
"""
import json
import re
import time

import requests

from API.common import StatusCode
from API.common.url_safety import check_public_http_url

# ==================== 模型清单缓存 ====================
MODELS_CACHE_TTL = 60
"""模型清单进程内缓存时长（秒）；后台改动由信号即时失效，故 TTL 只用于兜底"""

_cache = {'at': 0.0, 'items': None}


def invalidate_models_cache():
    """清空模型清单缓存（后台保存 / 删除厂商与模型后由信号调用）"""
    _cache['at'] = 0.0
    _cache['items'] = None


def _platform_prompt(mode, content, prompt_enabled, global_prompt):
    """按模型的三态选择解析平台系统提示词（调用方没自带 system_prompt 时使用）

    - none                            → 不使用
    - custom 且指定的那条仍启用        → 用指定的那条
    - inherit / 指定的那条已停用或已删除 → 回落「全局共享」那条（可能也是空）
    """
    if mode == 'none':
        return ''
    if mode == 'custom' and prompt_enabled:
        return (content or '').strip()
    return (global_prompt or '').strip()


def _catalog():
    """可用模型清单（上架模型 + 启用厂商），带 TTL 缓存；不含密钥

    顺带把「这次调用要用的系统提示词」、采样参数与图片张数上限一并解析好，调用侧不必再查库：
    这几项都是超管在后台按模型维护的，调用方无法干预。
    """
    now = time.monotonic()
    if _cache['items'] is not None and now - _cache['at'] < MODELS_CACHE_TTL:
        return _cache['items']

    from API.models import AiModel, AiSystemPrompt
    from API.models.AI.provider import parse_stop
    # 「全局共享」那条：全库只保留一条，所有 prompt_mode='inherit' 的模型都用它
    global_prompt = (AiSystemPrompt.objects
                     .filter(is_global=True, enabled=True)
                     .values_list('content', flat=True).first() or '')
    rows = (AiModel.objects
            .filter(enabled=True, provider__enabled=True)
            .order_by('sort', 'key')
            .values('key', 'name', 'upstream_name', 'supports_vision', 'max_images',
                    'context_window', 'is_default', 'provider_id', 'provider__base_url',
                    'prompt_mode', 'temperature', 'max_tokens', 'stop',
                    'system_prompt__content', 'system_prompt__enabled'))
    items = []
    for r in rows:
        base_url = (r['provider__base_url'] or '').strip().rstrip('/')
        items.append({
            'key': r['key'],
            'name': r['name'],
            'upstream': (r['upstream_name'] or r['key'] or '').strip(),
            'supports_vision': r['supports_vision'],
            'max_images': r['max_images'],
            'context_window': r['context_window'],
            'is_default': r['is_default'],
            'provider_id': r['provider_id'],
            'url': f'{base_url}/chat/completions',
            'platform_prompt': _platform_prompt(r['prompt_mode'], r['system_prompt__content'],
                                                r['system_prompt__enabled'], global_prompt),
            'temperature': r['temperature'],
            'max_tokens': r['max_tokens'],
            'stop_list': parse_stop(r['stop']),
        })
    _cache['items'] = items
    _cache['at'] = now
    return items


def public_models():
    """对外暴露的模型清单（白名单字段）

    只给「选模型」需要的信息：字段名刻意用 `model` 与请求参数 `model` 对齐。
    不含上游地址、厂商标识与密钥——真正的敏感项一个都不出网。
    """
    return [{
        'model': m['key'],
        'name': m['name'],
        'supports_vision': m['supports_vision'],
        'context_window': m['context_window'],
        'is_default': m['is_default'],
    } for m in _catalog()]


def _provider_key(provider_id):
    """按需取厂商平台 Key（查库即解密；不进缓存，避免密钥常驻内存）"""
    from API.models import AiProvider
    value = AiProvider.objects.filter(pk=provider_id).values_list('api_key', flat=True).first()
    return (value or '').strip()


def resolve_target(model_key=None, user_key=None):
    """解析一次对话调用的目标。

    :param model_key: 请求里的 model（留空取后台设置的默认模型）
    :param user_key:  调用方自带的 API Key（留空则用后台配置的平台 Key）
    :return: (target, None) 成功；target 含 key/name/upstream/url/supports_vision/
             max_images（后台按模型配置的图片张数上限）/ platform_prompt（后台配置的
             系统提示词）/ temperature / max_tokens / stop_list / api_key；
             (None, (状态码, 错误文案)) 失败
    """
    items = _catalog()
    if not items:
        return None, (StatusCode.SERVICE_UNAVAILABLE,
                      '平台尚未配置可用的 AI 模型（超管可在 /console/ai/models/ 添加）')

    wanted = (model_key or '').strip()
    if wanted:
        target = next((m for m in items if m['key'] == wanted), None)
        if target is None:
            return None, (StatusCode.PARAM_VALUE_INVALID,
                          f'参数值非法: 模型「{wanted}」不存在或未上架')
    else:
        target = next((m for m in items if m['is_default']), None)
        if target is None:
            # 不传 model 且没有默认模型：明确报错，绝不静默挑一个（避免调用方拿到意料之外的模型）
            return None, (StatusCode.SERVICE_UNAVAILABLE,
                          '平台未设置默认 AI 模型（超管可在 /console/ai/models/ 设为默认）')

    key = (user_key or '').strip() or _provider_key(target['provider_id'])
    if not key:
        return None, (StatusCode.EXTERNAL_API_FAILED,
                      f'模型「{target["key"]}」所属厂商尚未配置 API Key，'
                      '请在后台补填，或在请求时传入 api_key')
    return {**target, 'api_key': key}, None


# ==================== 参数辅助 ====================
MAX_IMAGE_URL_LEN = 2048
"""单张图片地址的最大长度"""


def parse_images(raw):
    """解析并校验 images 参数（张数上限由调用方按模型配置校验，见 request._handle_chat）。

    接受 JSON 数组字符串（``["https://…/a.jpg"]``）或纯文本（按换行 / 逗号拆分）。
    每个地址都必须是可安全访问的 http/https 公网地址——复用 ``url_safety`` 的判定，
    拒绝内网 / 回环 / 保留地址（避免有人拿本接口当内网探测的跳板）。

    :return: (urls, error_msg)；error_msg 非空表示参数非法
    """
    raw = (raw or '').strip()
    if not raw:
        return [], None

    urls = None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        urls = [str(u).strip() for u in parsed if str(u).strip()]
    elif isinstance(parsed, str) and parsed.strip():
        urls = [parsed.strip()]
    elif parsed is None:
        urls = [u.strip() for u in re.split(r'[\n,]+', raw) if u.strip()]

    if not urls:
        return [], '参数格式错误: images 不能为空'

    for url in urls:
        if len(url) > MAX_IMAGE_URL_LEN:
            return [], f'参数值非法: 单张图片地址不得超过 {MAX_IMAGE_URL_LEN} 个字符'
        ok, err = check_public_http_url(url)
        if not ok:
            return [], f'参数值非法: 图片地址不可用（{err}）'
    return urls, None


def _resolve_system_messages(system_prompt, platform_prompt):
    """解析最终使用的系统消息列表

    :param system_prompt: 调用方传入的 system_prompt
                          - None（没传） → 用平台配置（platform_prompt）
                          - ''（显式空串）→ 不使用系统提示词
                          - JSON 数组字符串 → 用调用方自己的
    :param platform_prompt: 后台按模型解析出的系统提示词正文（可为空）
    :return: list[dict] 系统消息列表；若无需插入则返回 None
    :raises ValueError: JSON 解析失败或含非 system role 时抛出
    """
    if system_prompt is None:
        # 调用方没表态 → 用超管在后台配置的提示词；后台没配就不插系统消息
        text = (platform_prompt or '').strip()
        return [{"role": "system", "content": text}] if text else None
    if system_prompt == '':
        # 显式传入空字符串 → 不使用系统提示词
        return None

    try:
        msgs = json.loads(system_prompt)
    except json.JSONDecodeError:
        raise ValueError("system_prompt 不是合法的 JSON 数组")

    if not isinstance(msgs, list):
        raise ValueError("system_prompt 必须为 JSON 数组")
    if not msgs:
        raise ValueError("system_prompt 不能为空数组")

    for item in msgs:
        if not isinstance(item, dict) or item.get("role") != "system":
            raise ValueError(
                f'system_prompt 仅支持 role 为 "system" 的消息, 不支持 role="{item.get("role")}"'
            )
    return msgs


def _attach_images(messages, images):
    """把图片挂到最后一条 user 消息上（OpenAI 多模态 content 数组格式）

    :raises ValueError: messages 里没有 user 消息时
    """
    for msg in reversed(messages):
        if msg.get('role') != 'user':
            continue
        original = msg.get('content')
        parts = list(original) if isinstance(original, list) else []
        if isinstance(original, str) and original.strip():
            parts.insert(0, {'type': 'text', 'text': original})
        for url in images:
            parts.append({'type': 'image_url', 'image_url': {'url': url}})
        msg['content'] = parts
        return
    raise ValueError('传 images 时，messages 中必须有一条 user 消息')


def build_messages(content, messages_json=None, system_prompt=None, images=None,
                   platform_prompt=None):
    """构建发给上游的 messages，自动在首位插入系统消息。

    :param content: 单条用户消息内容
    :param messages_json: 完整对话消息的 JSON 字符串，可选（优先级高于 content）
    :param system_prompt: 调用方传入的系统提示词（JSON 数组字符串）
                          - None/不传 → 用后台按模型配置的 platform_prompt
                          - '"[{...}]"' → 使用调用方自定义
                          - ''（空字符串） → 不使用系统提示词
    :param images: 图片地址列表（仅视觉模型），挂到最后一条 user 消息上
    :param platform_prompt: 后台解析出的系统提示词正文（见 resolve_target 的返回值）
    :return: messages 列表
    :raises ValueError: JSON 格式错误、role 校验失败或没有 user 消息时抛出
    """
    if messages_json:
        messages = json.loads(messages_json)
        if not isinstance(messages, list):
            raise ValueError("messages 必须为 JSON 数组")
        if not messages:
            raise ValueError("messages 不能为空")
    else:
        if not content:
            raise ValueError("content 或 messages 至少提供一个")
        messages = [{"role": "user", "content": content}]

    system_msgs = _resolve_system_messages(system_prompt, platform_prompt)
    if system_msgs:
        messages = system_msgs + messages

    if images:
        _attach_images(messages, images)
    return messages


# ==================== HTTP 调用 ====================
REQUEST_TIMEOUT = 120
"""**后台线程**（反馈审核线程等）的对话超时（秒）；后台不怕慢，给足时间"""
SYNC_TIMEOUT = 55
"""**同步**调用（跑在 web 请求线程里）的对话超时（秒）

为什么比后台短：同步调用每一秒都占着 uwsgi worker，而线上 Nginx 的
`proxy_read_timeout` 默认只有 60s —— 非流式接口一旦超过约 60s，客户端拿到的已经是
网关超时，worker 再跑下去纯属白占（而且服务端日志还会多出一条「其实是客户端早已走了」
的慢请求）。压到 55s 让服务端的失败**早于**网关，错误对调用方也更可读。
"""
TEST_TIMEOUT = 20
"""后台「测试连通性」的超时（秒），只发一条极短请求"""

# ── 重试配置 ──
_MAX_RETRIES = 3
"""**后台线程**调用的最大请求次数（含首次），即最多实际发 _MAX_RETRIES 次"""
SYNC_MAX_ATTEMPTS = 1
"""**同步**调用的最大请求次数（含首次）—— 即**不重试**

为什么同步不重试：每多一次重试就多占 worker 一整个 timeout，最坏（3 次 × 120s
加上 2/4/8s 退避）单个请求能把 worker 占住约 6 分钟，几个并发就能把 prefork 的
worker 打满、整站不可用；而且走到重试时上游往往整体不可用，重试多半还是失败，
只是把「快速失败」变成「慢慢失败」。后台线程不怕慢，重试能提高成功率，故仍保留。
"""
_RETRY_DELAYS = [2, 4, 8]
"""指数退避间隔（秒），依次为 2s、4s、8s"""
_RETRYABLE_STATUSES = {502, 503, 504}
"""可重试的 HTTP 状态码（网关/服务暂时不可用）"""


def _call_params(background, timeout, attempts):
    """把 (超时, 尝试次数) 归一：未显式指定时按 background 取对应口径"""
    if timeout is None:
        timeout = REQUEST_TIMEOUT if background else SYNC_TIMEOUT
    if attempts is None:
        attempts = _MAX_RETRIES if background else SYNC_MAX_ATTEMPTS
    return timeout, max(1, attempts)


def _handle_api_error(resp):
    """提取上游错误响应里的可读信息（各家的错误体都兼容 OpenAI 的 {error:{message}}）"""
    try:
        data = resp.json()
        error = data.get("error", {})
        if isinstance(error, dict):
            return error.get("message", str(data))
        return str(data)
    except (ValueError, AttributeError):
        return resp.text or f"HTTP {resp.status_code}"


def _request_with_retry(method, url, attempts=_MAX_RETRIES, **kwargs):
    """带指数退避重试的 HTTP 请求

    仅在以下情况重试：
        - 网络异常 (requests.RequestException)
        - 服务端 5xx 临时错误 (502/503/504)
    业务错误 (4xx) 不重试，直接返回。

    :param attempts: 最多实际发送几次（含首次）。同步路径传 1（不重试），
        后台路径用默认的 _MAX_RETRIES。口径见 SYNC_MAX_ATTEMPTS 的说明。
    :return: (resp, None) — 拿到响应；(None, error_msg) — 所有尝试耗尽
    """
    attempts = max(1, attempts)
    last_error, resp = None, None
    for attempt in range(attempts):
        try:
            resp = requests.request(method, url, **kwargs)
            if resp.status_code not in _RETRYABLE_STATUSES:
                return resp, None
            last_error = f"HTTP {resp.status_code}"
        except requests.RequestException as e:
            last_error = str(e)
            resp = None

        if attempt < attempts - 1:
            # 退避表比尝试次数短时取最后一项，避免 attempts 调大后越界
            time.sleep(_RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)])

    return resp, last_error


def _upstream_fail_msg(err, attempts):
    """上游彻底失败时的文案：说清「实际发了几次」，与真实重试口径一致"""
    attempts = max(1, attempts)
    if attempts > 1:
        return f'上游请求失败（已尝试 {attempts} 次）: {err}'
    return f'上游请求失败: {err}'


def _headers(target):
    return {
        'Authorization': f'Bearer {target["api_key"]}',
        'Content-Type': 'application/json',
    }


def _build_payload(target, messages, stream, temperature=None, max_tokens=None, stop=None):
    """组装 OpenAI 兼容的请求体"""
    payload = {
        'model': target['upstream'],
        'messages': messages,
        'stream': stream,
    }
    if stop:
        payload['stop'] = stop
    if temperature is not None:
        payload['temperature'] = temperature
    if max_tokens is not None:
        payload['max_tokens'] = max_tokens
    return payload


def chat_completion(target, messages, timeout=None, attempts=None, background=False,
                    temperature=None, max_tokens=None, stop=None):
    """非流式对话，返回完整回复。

    :param target: resolve_target() 的返回值
    :param messages: build_messages() 的返回值
    :param background: True=后台线程调用（保留多次重试与更长超时）；
        False（默认）= web 请求线程里的同步调用，只发一次且超时更短。
        取舍见 SYNC_MAX_ATTEMPTS / SYNC_TIMEOUT 的说明。
    :return: (True, {'reply', 'model', 'usage', 'finish_reason'}) / (False, 错误信息)
    """
    timeout, attempts = _call_params(background, timeout, attempts)
    payload = _build_payload(target, messages, False, temperature, max_tokens, stop)
    resp, err = _request_with_retry('POST', target['url'], attempts=attempts, json=payload,
                                   headers=_headers(target), timeout=timeout)
    if resp is None:
        return False, _upstream_fail_msg(err, attempts)
    if resp.status_code != 200:
        return False, f'上游返回错误 ({resp.status_code}): {_handle_api_error(resp)}'

    try:
        data = resp.json()
    except ValueError as e:
        return False, f'解析上游响应失败: {e}'

    choices = data.get('choices') or []
    if not choices:
        return False, '上游返回异常: choices 为空'
    first = choices[0]
    return True, {
        'reply': (first.get('message') or {}).get('content', ''),
        # 回给调用方的一律是「对外模型标识」，不透出上游真实模型名
        'model': target['key'],
        'usage': data.get('usage'),
        'finish_reason': first.get('finish_reason'),
    }


def stream_chat_completion(target, messages, timeout=None, attempts=None, background=False,
                           temperature=None, max_tokens=None, stop=None):
    """流式对话，生成器逐块 yield SSE 数据行。

    每个 yield 输出一条 SSE 格式文本::
        data: {"content": "部分回复内容"}       # 答案正文
        data: {"reasoning": "思考过程片段"}     # 仅推理模型有，思考过程，与答案分开
    结束标记::
        data: [DONE]

    两个字段互不重叠：只关心答案的调用方只取 content（忽略 reasoning 即可）；
    推理模型在吐出答案前会先流一串 reasoning，这段时间里 content 一帧都没有。

    错误处理：首次 yield 前出错 → 抛 ValueError（由视图转成错误 SSE 行）；
    流中出错 → 记录后结束。

    :param background: 同 chat_completion —— 默认按**同步**口径（只发一次、超时更短），
        后台线程调用时显式传 True
    :raises ValueError: 上游请求失败或返回非 200
    """
    timeout, attempts = _call_params(background, timeout, attempts)
    payload = _build_payload(target, messages, True, temperature, max_tokens, stop)
    resp, err = _request_with_retry('POST', target['url'], attempts=attempts, json=payload,
                                   headers=_headers(target), stream=True, timeout=timeout)
    if resp is None:
        raise ValueError(_upstream_fail_msg(err, attempts))
    if resp.status_code != 200:
        raise ValueError(f'上游返回错误 ({resp.status_code}): {_handle_api_error(resp)}')

    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        if not line.startswith("data: "):
            continue
        chunk_data = line[6:]
        if chunk_data == "[DONE]":
            yield "data: [DONE]\n\n"
            return
        try:
            chunk = json.loads(chunk_data)
        except json.JSONDecodeError:
            # 非 JSON 行直接透传（极少发生，做安全兜底）
            yield f"data: {chunk_data}\n\n"
            continue
        choices = chunk.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        # 推理模型（DeepSeek 的 flash 等）会先流思考过程、再流答案；两者分字段下发，
        # 调用方要展示思考过程就取 reasoning，只关心答案就只取 content。
        reasoning = delta.get("reasoning_content")
        if reasoning:
            yield f"data: {json.dumps({'reasoning': reasoning}, ensure_ascii=False)}\n\n"
        piece = delta.get("content")
        if piece:
            yield f"data: {json.dumps({'content': piece}, ensure_ascii=False)}\n\n"


def test_provider(provider, timeout=TEST_TIMEOUT):
    """后台「测试连通性」：用该厂商的地址与 Key 发一条极短请求。

    目的：Key 写错 / 地址写错 / 额度用尽，在后台当场就能发现，不必等到线上调用失败。

    :param provider: AiProvider 实例
    :return: (ok, 说明文案)
    """
    if not provider.has_key:
        return False, '未配置 API Key'
    first = (provider.models.order_by('sort', 'key')
             .values_list('upstream_name', 'key').first())
    if not first:
        return False, '该厂商下还没有模型，请先添加模型再测试'
    upstream = (first[0] or first[1]).strip()

    started = time.monotonic()
    try:
        resp = requests.post(
            provider.chat_url,
            json={'model': upstream,
                  'messages': [{'role': 'user', 'content': 'ping'}],
                  'stream': False, 'max_tokens': 1},
            headers={'Authorization': f'Bearer {provider.api_key}',
                     'Content-Type': 'application/json'},
            timeout=timeout,
        )
    except requests.RequestException as e:
        return False, f'请求失败: {e}'
    cost_ms = int((time.monotonic() - started) * 1000)

    if resp.status_code != 200:
        return False, f'HTTP {resp.status_code}（{cost_ms} ms）: {_handle_api_error(resp)}'
    return True, f'连接正常（{cost_ms} ms，测试模型 {upstream}）'
