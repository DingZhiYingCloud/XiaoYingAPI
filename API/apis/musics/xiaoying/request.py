"""小影音乐 API 视图函数

提供 Music / MusicSource 的 RESTful CRUD 接口:
    GET    /api/music/xiaoying/musics            音乐列表查询(搜索/在线过滤)
    POST   /api/music/xiaoying/musics            创建音乐（返回 music_id=UUID）
    GET    /api/music/xiaoying/musics/<uuid>     获取音乐详情（含其全部播放源）
    PATCH  /api/music/xiaoying/musics/<uuid>     更新音乐(部分字段)
    DELETE /api/music/xiaoying/musics/<uuid>     删除音乐

    POST   /api/music/xiaoying/music_sources            创建播放源（music_id 为音乐 UUID）
    PATCH  /api/music/xiaoying/music_sources/<uuid>     更新播放源(部分字段)
    DELETE /api/music/xiaoying/music_sources/<uuid>     删除播放源

说明: 播放源不提供独立列表/详情查询接口，通过「获取音乐详情」接口返回指定音乐的播放源。
"""
import uuid

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
    singer 支持重复 key 传多值（singer=周杰伦&singer=蔡依林），返回列表。
    """
    if request.method == 'POST':
        qd = request.POST
    elif request.body:
        try:
            qd = QueryDict(request.body.decode('utf-8'))
        except Exception as e:
            return None, f'表单解析失败: {e}'
    else:
        return {}, None

    data = qd.dict()
    # 多值字段：singer 支持重复 key（singer=周杰伦&singer=蔡依林），保留为列表。
    # 注意：qd.dict() 会残留重复 key 的最后一个值，这里显式覆盖为过滤后的列表；
    # 传了空值（singer= 或全空格）时保留空列表，便于视图区分"未传"与"传了空值"。
    if 'singer' in qd:
        data['singer'] = [s.strip() for s in qd.getlist('singer') if s.strip()]
    return data, None


# ==================== Music 接口 ====================

@require_http_methods(['GET', 'POST'])
def musics_view(request):
    """音乐列表/创建

    GET  - 查询音乐列表，支持 keyword 搜索(名称/歌手)、online 过滤
           online 不传时默认只返回在线音乐（离线音乐不返回）
    POST - 创建新音乐，返回的 id 为 UUID，可凭此访问音乐详情
    """
    if request.method == 'GET':
        # ── 参数解析 ──
        keyword = request.GET.get('keyword', '').strip()
        online = request.GET.get('online', '').strip().lower()
        page = request.GET.get('page', '1').strip()
        page_size = request.GET.get('page_size', '10').strip()

        # 分页参数校验（page >= 1，1 <= page_size <= 100）
        try:
            page = int(page)
        except ValueError:
            return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg='参数格式错误: page 必须为整数')
        try:
            page_size = int(page_size)
        except ValueError:
            return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg='参数格式错误: page_size 必须为整数')
        if page < 1:
            return _json_response(StatusCode.PARAM_VALUE_INVALID, msg='参数值非法: page 必须大于等于 1')
        if page_size < 1:
            return _json_response(StatusCode.PARAM_VALUE_INVALID, msg='参数值非法: page_size 必须大于等于 1')
        if page_size > 100:
            return _json_response(StatusCode.PARAM_VALUE_INVALID, msg='参数值非法: page_size 最大为 100')

        ok, data = utils.list_musics(keyword=keyword, online=online, page=page, page_size=page_size)
        if not ok:
            return _json_response(StatusCode.INTERNAL_ERROR, msg=data)
        return _json_response(StatusCode.SUCCESS, data=data, msg=f'查询成功，共 {data["total"]} 条')

    # POST - 创建
    data, err = _parse_body(request)
    if err:
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg=err)
    if not data:
        return _json_response(StatusCode.PARAM_MISSING, msg='请求体不能为空')

    ok, result = utils.create_music(data)
    if not ok:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg=result)
    return _json_response(StatusCode.SUCCESS, data=result, msg='创建成功')


@require_http_methods(['GET', 'PATCH', 'DELETE'])
def music_detail_view(request, music_id: uuid.UUID):
    """音乐详情/更新/删除

    GET    - 获取音乐详情，同时返回其全部播放源（music_sources 字段）
    PATCH  - 部分字段更新
    DELETE - 删除（关联播放源级联删除）
    """
    if request.method == 'GET':
        ok, data = utils.get_music(music_id)
        if not ok:
            return _json_response(StatusCode.NOT_FOUND, msg=data)
        return _json_response(StatusCode.SUCCESS, data=data, msg='查询成功')

    if request.method == 'PATCH':
        body, err = _parse_body(request)
        if err:
            return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg=err)
        if not body:
            return _json_response(StatusCode.PARAM_MISSING, msg='请求体不能为空')
        ok, data = utils.update_music(music_id, body)
        if not ok:
            return _json_response(StatusCode.PARAM_VALUE_INVALID, msg=data)
        return _json_response(StatusCode.SUCCESS, data=data, msg='更新成功')

    # DELETE
    ok, msg = utils.delete_music(music_id)
    if not ok:
        return _json_response(StatusCode.NOT_FOUND, msg=msg)
    return _json_response(StatusCode.SUCCESS, data=None, msg='删除成功')


# ==================== MusicSource 接口 ====================

@require_http_methods(['POST'])
def music_source_create_view(request):
    """创建播放源（music_id + url 必填）

    music_id 为创建音乐接口返回的 UUID。
    播放源创建后，可通过「获取音乐详情」接口查到。
    """
    data, err = _parse_body(request)
    if err:
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg=err)
    if not data:
        return _json_response(StatusCode.PARAM_MISSING, msg='请求体不能为空')

    ok, result = utils.create_music_source(data)
    if not ok:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg=result)
    return _json_response(StatusCode.SUCCESS, data=result, msg='创建成功')


@require_http_methods(['PATCH', 'DELETE'])
def music_source_detail_view(request, source_id: uuid.UUID):
    """播放源更新/删除

    PATCH  - 部分字段更新
    DELETE - 删除
    """
    if request.method == 'PATCH':
        body, err = _parse_body(request)
        if err:
            return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg=err)
        if not body:
            return _json_response(StatusCode.PARAM_MISSING, msg='请求体不能为空')
        ok, data = utils.update_music_source(source_id, body)
        if not ok:
            return _json_response(StatusCode.PARAM_VALUE_INVALID, msg=data)
        return _json_response(StatusCode.SUCCESS, data=data, msg='更新成功')

    # DELETE
    ok, msg = utils.delete_music_source(source_id)
    if not ok:
        return _json_response(StatusCode.NOT_FOUND, msg=msg)
    return _json_response(StatusCode.SUCCESS, data=None, msg='删除成功')
