"""API 统一响应封装（全站唯一实现）

各服务原先在各自的 `request.py` 里各写一份完全相同的 `_json_response`，
这里是唯一实现；各服务改为 `from API.common.responses import json_response as _json_response`，
保持调用点不变（`_json_response(...)` 照旧可用）。

外层信封固定为 `{"code", "msg", "data"}`，`msg` 未传时取 `StatusCode` 的默认描述。
业务码定义见 `API/common/status_code.py`。
"""
from django.http import JsonResponse

from API.common import StatusCode


def json_response(code, data=None, msg=None):
    """构建统一的 JSON 响应体

    :param code: 状态码（参见 StatusCode）
    :param data: 业务数据，默认为 None
    :param msg:  自定义消息，未传则使用状态码对应的默认描述
    """
    return JsonResponse({
        'code': code,
        'msg': msg or StatusCode.get_message(code),
        'data': data,
    })
