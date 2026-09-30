"""问题反馈中心 · API 视图

反馈中心主体是**我们托管的反馈页**（`/feedback/<app_id>/`），子项目零代码接入；
这里只放两个「子项目前端可以直接调」的端点（均免签名，理由见 utils 模块说明）：

    POST /api/feedback/ticket    用用户 UAC Token 换一张一次性票据
    GET  /api/feedback/contacts  查某个接入项目的开发者联系方式

数据隔离：反馈数据按接入项目（UserApp）隔离；本模块不涉及反馈读写，
提交 / 查看 / 回复都在反馈页里完成。
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from API.common import StatusCode

from . import utils


def _json_response(code, data=None, msg=None):
    """统一响应格式: {"code", "msg", "data"}"""
    return JsonResponse({
        'code': code,
        'msg': msg or StatusCode.get_message(code),
        'data': data,
    })


@require_http_methods(['POST'])
def ticket_view(request):
    """用用户 Token 换一次性反馈票据（免签名）

    表单参数：token(必填，用户中心签发的登录 Token)
    返回：{ticket, expire_in, app_id, app_name}
    子项目前端拿到 ticket 后拼到反馈页地址上：`/feedback/<app_id>/?ticket=<ticket>`。
    """
    ok, data = utils.issue_ticket(request.POST.get('token'),
                                  ip=utils.client_ip(request))
    if not ok:
        return _json_response(utils.fail_code(data), msg=data)
    return _json_response(StatusCode.SUCCESS, data=data, msg='票据签发成功')


@require_http_methods(['GET'])
def contacts_view(request):
    """查某个接入项目的开发者联系方式（免签名）

    query 参数：app_id(必填，接入项目的 APPID)
    返回：{app_id, app_name, contacts:[{platform, name, icon, label, value, url}]}
    """
    ok, data = utils.list_contacts(request.GET.get('app_id'))
    if not ok:
        return _json_response(utils.fail_code(data, fallback=StatusCode.NOT_FOUND), msg=data)
    return _json_response(StatusCode.SUCCESS, data=data, msg='查询成功')
