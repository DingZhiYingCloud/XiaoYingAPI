"""代练搬单 order_migration 视图层

把代练通订单映射为代练丸子发单参数（预览用，不真实发单）。
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from API.common import StatusCode

from . import utils


def _json_response(code, data=None, msg=None):
    return JsonResponse({
        "code": code,
        "msg": msg or StatusCode.get_message(code),
        "data": data,
    })


@require_http_methods(["POST"])
def preview_view(request):
    """预览映射：代练通订单字段 → 代练丸子发单参数（不真实发单）

    参数:
        title      (必填): 代练通订单标题（原样照搬）
        price      (必填): 代练通订单金额（元）
        zone       (必填): 代练通大区，如 安卓QQ / 苹果QQ / 安卓WX / 苹果WX
        time_limit (必填): 代练通订单时限（小时）

    返回 data 为映射后的代练丸子发单业务参数（game_id / leveling_type_name /
    region_name / title / hour / amount / security_deposit / efficiency_deposit）。
    """
    fields = {
        'title': request.POST.get("title", "").strip(),
        'price': request.POST.get("price", "").strip(),
        'zone': request.POST.get("zone", "").strip(),
        'time_limit': request.POST.get("time_limit", "").strip(),
    }
    missing = [name for name, value in fields.items() if not value]
    if missing:
        return _json_response(StatusCode.PARAM_MISSING, msg=f"参数缺失: {'、'.join(missing)}")

    ok, data = utils.map_order(**fields)
    if not ok:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)
