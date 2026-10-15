"""爬虫 / 上游服务返回结果的统一映射（全站唯一实现）

各服务的 `request.py` 原先各写一份逐字相同的 `_spider_result`，把爬虫层返回的
`{code, message, data}` 映射为项目统一响应 `{code, msg, data}`（共 7 份副本）。
此处收敛为唯一实现，各服务改为 `from API.common.spider import spider_result as _spider_result`，
保持调用点不变（与 `API/common/responses.py` 的收口方式一致）。

口径：上游 `code == 0` 视为成功，其 message 作为成功提示（可为空）；
否则一律按「外部服务调用失败」返回，并把上游的中文说明原样放进 msg ——
上游文案属于业务信息，不能走 `StatusCode.from_message` 的关键词映射，
否则「用户不存在」这类平台文案会被误判成 20030 资源不存在。
"""
from API.common import StatusCode
from API.common.responses import json_response as _json_response


def spider_result(result, fail_default='未知错误'):
    """把爬虫层的 {code, message, data} 映射为统一响应

    :param result:       爬虫层返回值，应为 dict；非 dict 视为未知错误
    :param fail_default: 上游未给出失败说明时的兜底文案
    """
    if not isinstance(result, dict):
        return _json_response(StatusCode.UNKNOWN_ERROR, msg=str(result))
    if result.get("code") == 0:
        return _json_response(StatusCode.SUCCESS, data=result.get("data"),
                              msg=result.get("message"))
    return _json_response(StatusCode.EXTERNAL_API_FAILED,
                          msg=result.get("message") or fail_default)
