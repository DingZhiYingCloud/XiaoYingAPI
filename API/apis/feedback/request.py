"""问题反馈中心 - API 视图

接口清单（全部需项目签名；create/reply 另需用户 Token 校验真实性）：
    POST /api/feedback/create  提交反馈（title, content, token + 签名参数）
    POST /api/feedback/reply   追加/回复评论（feedback_id, content, parent_id?, token + 签名参数）
    GET  /api/feedback/list    项目内反馈列表（status?, page?, page_size? + 签名参数）
    GET  /api/feedback/detail  反馈详情+评论树（feedback_id, page?, page_size? + 签名参数）
    GET  /api/feedback/replies 某条评论的二级评论列表（feedback_id, parent_id, page?, page_size? + 签名参数）

说明：
- 数据按项目隔离：所有查询以签名确定的 app 为租户维度，子项目之间互不可见
- 项目内公开：同一子项目所有用户可查看全部反馈与评论（类似 GitHub Issues）
- 评论语义：一级评论=直接评论问题的评论（parent 为空）；二级评论=所有回复在别人
  评论底下的评论（parent 非空），**无论嵌套多深**（B 回复 A、C 回复 B……全部算二级评论）
- 评论分页：详情接口一级评论分页，每条内嵌二级评论首页（SUB_REPLY_FIRST_PAGE_SIZE 条，
  取该一级评论全部子孙按时间正序前 N 条）；某条评论的全部二级评论通过 /replies 接口
  按 parent_id 分页获取（返回其全部子孙，不分层级，防海量评论撑爆响应）
- 身份真实性：create/reply 携带用户登录 Token，由反馈中心校验，
  评论人身份以 Token 校验结果为准（子项目无法伪造用户 ID）
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


def _parse_params(request):
    """合并 form body 与 query 参数（签名参数可能在 body 或 query）"""
    params = request.POST.dict()
    params.update({k: v for k, v in request.GET.items() if k not in params})
    return params


def _fail_response(msg, fallback_code=StatusCode.PARAM_VALUE_INVALID):
    """根据业务错误消息映射状态码：参数缺失→20001，格式错误→20002，其余→fallback"""
    if msg.startswith('参数缺失'):
        return _json_response(StatusCode.PARAM_MISSING, msg=msg)
    if msg.startswith('参数格式错误'):
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg=msg)
    if msg.startswith('Token') or 'token' in msg:
        return _json_response(StatusCode.UNAUTHORIZED, msg=msg)
    return _json_response(fallback_code, msg=msg)


def _require_app(request):
    """校验项目签名上下文，返回 (app, None) 或 (None, response)"""
    # 项目签名已由 ApiAuthMiddleware 统一校验；若后台将该接口配置为开放则无 auth_app，
    # 业务强依赖项目上下文（数据隔离维度）故仍拒绝
    app = getattr(request, 'auth_app', None)
    if app is None:
        return None, _json_response(StatusCode.AUTH_FAILED, msg='接口未配置项目认证，无法识别接入项目')
    return app, None


@require_http_methods(['POST'])
def create_view(request):
    """提交反馈

    表单参数：title(必填), content(必填), token(必填，用户登录Token) + 签名参数
    数据按项目隔离，反馈人身份由 Token 校验确定。
    """
    params = _parse_params(request)
    app, resp = _require_app(request)
    if app is None:
        return resp
    ok, data = utils.create_feedback(
        app, params.get('token'), params.get('title'), params.get('content'),
    )
    if not ok:
        return _fail_response(data)
    return _json_response(StatusCode.SUCCESS, data=data, msg='反馈已提交')


@require_http_methods(['POST'])
def reply_view(request):
    """追加 / 回复评论

    表单参数：feedback_id(必填), content(必填), parent_id?(可选), token(必填，用户登录Token) + 签名参数
    parent_id 为空=一级评论；非空=回复指定评论（须属于当前反馈，支持无限嵌套）。
    同一反馈下所有评论组成评论树，项目内全部人可见。
    """
    params = _parse_params(request)
    app, resp = _require_app(request)
    if app is None:
        return resp
    ok, data = utils.create_reply(
        app, params.get('token'), params.get('feedback_id'), params.get('content'),
        parent_id=params.get('parent_id', ''),
    )
    if not ok:
        return _fail_response(data, fallback_code=StatusCode.NOT_FOUND)
    return _json_response(StatusCode.SUCCESS, data=data, msg='追加成功')


@require_http_methods(['GET'])
def list_view(request):
    """项目内反馈列表

    query 参数：status?(筛选状态), page?(页码，默认1), page_size?(每页条数，默认10) + 签名参数
    只返回当前项目（签名确定）下的反馈，子项目之间互不可见。
    """
    params = _parse_params(request)
    app, resp = _require_app(request)
    if app is None:
        return resp
    ok, data = utils.list_feedbacks(
        app,
        status=params.get('status', ''),
        page=params.get('page', 1),
        page_size=params.get('page_size', 10),
    )
    if not ok:
        return _fail_response(data)
    return _json_response(StatusCode.SUCCESS, data=data, msg='查询成功')


@require_http_methods(['GET'])
def detail_view(request):
    """反馈详情 + 评论树

    query 参数：feedback_id(必填), page?(一级评论页码，默认1), page_size?(每页条数，默认20，最大100) + 签名参数
    一级评论分页返回，每条内嵌二级首页（默认5条），全部人可见；
    更多/更深层回复通过 /replies 接口按 parent_id 分页获取。
    """
    params = _parse_params(request)
    app, resp = _require_app(request)
    if app is None:
        return resp
    ok, data = utils.get_feedback_detail(
        app,
        params.get('feedback_id'),
        page=params.get('page', 1),
        page_size=params.get('page_size', None),
    )
    if not ok:
        return _fail_response(data, fallback_code=StatusCode.NOT_FOUND)
    return _json_response(StatusCode.SUCCESS, data=data, msg='查询成功')


@require_http_methods(['GET'])
def replies_view(request):
    """某条评论的二级评论列表（分页，返回其全部子孙，不分层级）

    query 参数：feedback_id(必填), parent_id(必填，被查看的评论 ID), page?(页码，默认1),
                page_size?(每页条数，默认20，最大100) + 签名参数
    语义：二级评论=所有回复在别人评论底下的评论（无论嵌套多深），
    本接口返回 parent 的**全部子孙回复**（扁平列表，按时间正序分页），
    每条含 parent_id（标明回复了谁）/ reply_total / children_total。
    """
    params = _parse_params(request)
    app, resp = _require_app(request)
    if app is None:
        return resp
    ok, data = utils.list_replies(
        app,
        params.get('feedback_id'),
        params.get('parent_id'),
        page=params.get('page', 1),
        page_size=params.get('page_size', None),
    )
    if not ok:
        return _fail_response(data, fallback_code=StatusCode.NOT_FOUND)
    return _json_response(StatusCode.SUCCESS, data=data, msg='查询成功')
