"""友情链接 API 视图函数

提供 RESTful CRUD 接口:
    GET    /api/seo/friend_links           列表查询(分页/搜索/筛选)
    POST   /api/seo/friend_links           创建友情链接
    GET    /api/seo/friend_links/<id>      获取单条详情
    PATCH  /api/seo/friend_links/<id>      更新(部分字段)
    DELETE /api/seo/friend_links/<id>      删除
"""
from django.http import JsonResponse, QueryDict
from django.views.decorators.http import require_http_methods

from API.common import StatusCode
from . import utils


def _json_response(code, data=None, msg=None):
    """统一响应格式: {"code, msg, data}"""
    return JsonResponse({
        'code': code,
        'msg': msg or StatusCode.get_message(code),
        'data': data,
    })


def _parse_body(request):
    """解析 x-www-form-urlencoded 表单请求体

    注意: Django 的 request.POST 仅自动解析 POST 方法的表单数据，
    PATCH 等其它方法需手动从 request.body 解析。
    """
    if request.method == 'POST':
        return request.POST.dict(), None
    if request.body:
        try:
            return QueryDict(request.body.decode('utf-8')).dict(), None
        except Exception as e:
            return None, f'表单解析失败: {e}'
    return {}, None


@require_http_methods(['GET', 'POST'])
def friend_links_view(request):
    """友情链接列表/创建

    GET  - 查询全部友情链接,支持 keyword/category/status 筛选
    POST - 创建新友情链接
    """
    if request.method == 'GET':
        # ── 参数解析（返回全部，支持 keyword/category/status 筛选）──
        keyword = request.GET.get('keyword', '').strip()
        category = request.GET.get('category', '').strip()
        status = request.GET.get('status', '').strip().lower()

        ok, data = utils.list_friend_links(
            keyword=keyword, category=category, status=status,
        )
        if not ok:
            return _json_response(StatusCode.INTERNAL_ERROR, msg=data)
        return _json_response(StatusCode.SUCCESS, data=data, msg=f'查询成功，共 {data["total"]} 条')

    # POST - 创建
    data, err = _parse_body(request)
    if err:
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg=err)
    if not data:
        return _json_response(StatusCode.PARAM_MISSING, msg='请求体不能为空')

    ok, result = utils.create_friend_link(data)
    if not ok:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg=result)
    return _json_response(StatusCode.SUCCESS, data=result, msg='创建成功')


@require_http_methods(['GET', 'PATCH', 'DELETE'])
def friend_link_detail_view(request, link_id: int):
    """友情链接详情/更新/删除

    GET    - 获取单条详情
    PATCH  - 部分字段更新
    DELETE - 删除
    """
    if request.method == 'GET':
        ok, data = utils.get_friend_link(link_id)
        if not ok:
            return _json_response(StatusCode.NOT_FOUND, msg=data)
        return _json_response(StatusCode.SUCCESS, data=data, msg='查询成功')

    if request.method == 'PATCH':
        body, err = _parse_body(request)
        if err:
            return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg=err)
        if not body:
            return _json_response(StatusCode.PARAM_MISSING, msg='请求体不能为空')
        ok, data = utils.update_friend_link(link_id, body)
        if not ok:
            return _json_response(StatusCode.PARAM_VALUE_INVALID, msg=data)
        return _json_response(StatusCode.SUCCESS, data=data, msg='更新成功')

    # DELETE
    ok, msg = utils.delete_friend_link(link_id)
    if not ok:
        return _json_response(StatusCode.NOT_FOUND, msg=msg)
    return _json_response(StatusCode.SUCCESS, data=None, msg='删除成功')
