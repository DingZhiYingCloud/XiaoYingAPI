# -*- coding: utf-8 -*-
"""调用大模型（OpenAI 兼容端点）。

对外只有一个函数 call()：按配置决定**流式**还是**整段**，并把增量交给回调，
这样上层渲染代码不用关心两种模式的差别。

需要流式的场景（STREAM=1，默认）：边生成边显示，首字很快就出来。
需要整段（STREAM=0）：有些中转站/模型不支持 SSE，或者你就是想一次显示完整段。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request


class LLMError(Exception):
    """调用大模型失败（网络、鉴权、限流等），消息可直接展示给用户。"""


def _endpoint(conf) -> str:
    return conf['AI_BASE_URL'].rstrip('/') + '/chat/completions'


def _http_error(e: urllib.error.HTTPError) -> LLMError:
    body = e.read().decode('utf-8', 'replace')
    try:
        msg = json.loads(body)['error']['message']
    except Exception:                      # noqa: BLE001
        msg = body[:300]
    return LLMError(f'模型接口返回 HTTP {e.code}：{msg}')


def call(conf, messages, on_think=None, on_content=None):
    """向模型要一次回复。

    on_think(text)   思维链增量（只有支持思维链的模型 + 开启了才会调用）
    on_content(text) 正式内容增量（STREAM=0 时是一次性给整段）
    """
    if conf.get('STREAM', '1') == '0':
        text = _call_once(conf, messages)
        if text and on_content:
            on_content(text)
        return
    _call_stream(conf, messages, on_think, on_content)


def _post(conf, messages, stream: bool):
    payload = json.dumps({'model': conf['AI_MODEL'], 'stream': stream,
                          'messages': messages}, ensure_ascii=False).encode()
    headers = {'Authorization': f'Bearer {conf["AI_API_KEY"]}',
               'Content-Type': 'application/json'}
    if stream:
        headers['Accept'] = 'text/event-stream'
    req = urllib.request.Request(_endpoint(conf), data=payload, method='POST',
                                 headers=headers)
    timeout = int(conf['AI_API_TIMEOUT'])
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        raise _http_error(e) from None
    except Exception as e:                  # noqa: BLE001
        raise LLMError(f'调用模型失败：{e}') from None


def _call_once(conf, messages) -> str:
    """非流式：一次拿完整段。"""
    with _post(conf, messages, stream=False) as resp:
        raw = resp.read().decode('utf-8', 'replace')
    try:
        data = json.loads(raw)
    except ValueError:
        raise LLMError(f'模型返回的不是合法 JSON（前 200 字：{raw[:200]}）') from None
    try:
        return data['choices'][0]['message'].get('content') or ''
    except (KeyError, IndexError, TypeError):
        raise LLMError('模型返回结构异常') from None


def _call_stream(conf, messages, on_think, on_content):
    """流式：逐块吐出。SSE 每行形如 `data: {...}`，以 `data: [DONE]` 结束。"""
    try:
        with _post(conf, messages, stream=True) as resp:
            for raw in resp:
                line = raw.decode('utf-8', 'replace').strip()
                if not line.startswith('data:'):
                    continue
                data = line[5:].strip()
                if data == '[DONE]':
                    break
                try:
                    obj = json.loads(data)
                except ValueError:
                    continue
                try:
                    delta = obj['choices'][0].get('delta') or {}
                except (KeyError, IndexError, TypeError):
                    continue
                if delta.get('reasoning_content') and on_think:
                    on_think(delta['reasoning_content'])
                if delta.get('content') and on_content:
                    on_content(delta['content'])
    except (LLMError, BrokenPipeError):
        raise                                        # 已经是人话 / 管道断了，原样往上抛
    except Exception as e:                           # noqa: BLE001
        raise LLMError(f'流式连接中断：{type(e).__name__}: {e}') from e
