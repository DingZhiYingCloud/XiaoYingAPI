"""API 调用统计服务 - 请求处理视图（公开口径）

接口清单：
    GET /api/statistics/api_calls  查询某个接口的累计 / 今日调用次数
    GET /api/statistics/services   各服务的累计 / 今日调用次数排行

鉴权：服务策略将 /api/statistics/ 配置为开放（open），无需项目签名——调用量属公开信息，
      未登录也能查看某个接口一共被调用了多少次。
口径：**仅返回调用次数**，不含接入项目、失败率、耗时等敏感维度（那些只在超管看板可见）。
"""
from django.views.decorators.http import require_http_methods

from API.common import StatusCode
from API.common.ip_guard import client_ip
from API.common.ratelimit import allow
from API.common.responses import json_response as _json_response
from API.website.docs import ALL_ENDPOINTS

from . import utils

# 公开统计接口的频率上限（同一来源 IP）：60 次 / 分钟
# 目的：本服务匿名可访问且要做历史聚合查询，不限频时被反复刷新会持续消耗数据库。
RATE_LIMIT = 60
RATE_WINDOW = 60


def _rate_limited(request) -> bool:
    """本次请求是否应因频率超限被拒"""
    return not allow(f'statistics:{client_ip(request)}', RATE_LIMIT, RATE_WINDOW)


@require_http_methods(['GET'])
def api_calls_view(request):
    """查询某个接口的调用量（公开）

    query 参数：
        path (必填): 接口路径，须为文档中心已登记的路径；带路径参数的接口按文档写法
                     传占位符，如 /api/music/xiaoying/musics/<uuid>

    返回 data = {path, total_calls, today_calls}。
    """
    if _rate_limited(request):
        return _json_response(StatusCode.RATE_LIMITED, msg='请求过于频繁，请稍后重试')
    path = (request.GET.get('path') or '').strip()
    if not path:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: path')
    if path not in ALL_ENDPOINTS:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg='参数值非法: path 不是文档中心已登记的接口路径')
    return _json_response(StatusCode.SUCCESS, data=utils.api_calls(path), msg='查询成功')


@require_http_methods(['GET'])
def services_view(request):
    """各服务的调用量排行（公开）

    返回 data = {services: [{service, name, total_calls, today_calls}, ...]}，按累计调用量降序。
    """
    if _rate_limited(request):
        return _json_response(StatusCode.RATE_LIMITED, msg='请求过于频繁，请稍后重试')
    return _json_response(StatusCode.SUCCESS, data={'services': utils.service_calls()}, msg='查询成功')
