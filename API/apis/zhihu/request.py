"""知乎 API 请求处理视图

提供 5 个接口（**GET 与 POST 都接受**，POST 时参数走表单体，便于传较长的 Cookie）:
    /api/zhihu/hot       知乎热榜（排名 / 标题 / 链接 / 摘要 / 热度 / 回答数）
    /api/zhihu/question  问题详情（问题正文与图片 / 回答 / 评论 / 相关问题 / 大家都在搜）
    /api/zhihu/article   专栏文章详情（文章正文与图片 / 评论 / 大家都在搜）
    /api/zhihu/search    综合搜索（结果自带完整正文与图片 / 大家都在搜）
    /api/zhihu/check     校验知乎登录凭据是否有效

凭据说明：五个接口都接受可选参数 `cookie`（调用方自带的知乎登录 Cookie）——
**传了就用它，只本次生效、不落库**；没传则回落到平台统一托管的账号
（后台「账号管理」`/console/accounts/` 维护，加密落库）。
文档页 `/docs/zhihu/` 右侧栏「本机凭据」可粘贴并保存到本机，调试时自动带上。
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from API.common import StatusCode
from SpiderServices.zhihu.utils import (
    MAX_ANSWERS,
    MAX_COMMENTS,
    MAX_SEARCH_LIMIT,
    MAX_SEARCH_OFFSET,
    article_id_of,
    question_id_of,
)

from . import utils


def _json_response(code, data=None, msg=None):
    return JsonResponse({
        'code': code,
        'msg': msg or StatusCode.get_message(code),
        'data': data,
    })


def _param(request, name):
    """取请求参数：POST 表单体优先，其次 GET query（同一请求只会落在其中一处）"""
    if request.method == 'POST':
        value = request.POST.get(name)
        if value not in (None, ''):
            return value
    return request.GET.get(name)


def _error_response(msg):
    """业务层的中文失败说明 → 统一响应码

    区分两类，避免把「平台自己没配账号」误报成「上游调用失败」：
        · 未配置账号 → 50002 服务不可用（平台侧问题，接入方重试无意义）
        · 其它（凭据过期 / 上游异常）→ 40001 外部服务调用失败
    """
    if '尚未配置' in msg or '未提供 Cookie' in msg:
        return _json_response(StatusCode.SERVICE_UNAVAILABLE, msg=msg)
    return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=msg)


def _optional_int(raw, name, default, minimum, maximum):
    """可选整数参数校验

    :return: (值, 错误响应)；错误响应非 None 表示参数非法
    """
    if raw is None or str(raw).strip() == '':
        return default, None
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None, _json_response(StatusCode.PARAM_FORMAT_ERROR,
                                    msg=f'参数格式错误: {name} 必须为整数')
    if value < minimum or value > maximum:
        return None, _json_response(
            StatusCode.PARAM_VALUE_INVALID,
            msg=f'参数值非法: {name} 必须在 {minimum}~{maximum} 之间')
    return value, None


@require_http_methods(['GET', 'POST'])
def hot_view(request):
    """知乎热榜

    :param limit:  可选，返回条数，1~50（默认 50）
    :param cookie: 可选，调用方自带的知乎登录 Cookie；留空用平台托管的账号
    """
    limit, error = _optional_int(_param(request, 'limit'), 'limit', 50, 1, 50)
    if error:
        return error

    cookie = (_param(request, 'cookie') or '').strip()
    ok, result = utils.get_hot(limit, cookie=cookie)
    if not ok:
        return _error_response(result)
    return _json_response(StatusCode.SUCCESS, data={
        'count': len(result),
        'list': result,
    })


@require_http_methods(['GET', 'POST'])
def check_view(request):
    """校验知乎登录凭据是否有效

    :param cookie: 可选，调用方自带的知乎登录 Cookie；留空则校验平台托管的账号
    :return: data = {valid: bool, account: 账号标识（自带 Cookie 时为空）, message: 说明}
    """
    cookie = (_param(request, 'cookie') or '').strip()
    ok, result = utils.check_credential(cookie=cookie)
    if not ok:
        return _error_response(result)
    # 凭据无效不是「请求失败」——接口本身调通了，所以仍返回成功码，
    # 把 valid / message 放在 data 里，由调用方决定怎么处理。
    return _json_response(StatusCode.SUCCESS, data=result,
                          msg=result.get('message') or None)


@require_http_methods(['GET', 'POST'])
def question_view(request):
    """知乎问题详情

    :param question_id:            必填，知乎问题 ID（纯数字）或问题网页地址
    :param answer_limit:           可选，返回多少条回答，1~20（默认 5）
    :param comment_limit:          可选，每条回答的评论数，0~20（默认 3）
    :param question_comment_limit: 可选，问题本身的评论数，0~20（默认 10）
    :param cookie:                 可选，调用方自带的知乎登录 Cookie
    """
    question_id = question_id_of(_param(request, 'question_id'))
    if not question_id:
        return _json_response(
            StatusCode.PARAM_VALUE_INVALID,
            msg='参数值非法: question_id 必填，需为知乎问题 ID（纯数字）或问题网页地址')

    answer_limit, error = _optional_int(_param(request, 'answer_limit'),
                                        'answer_limit', 5, 1, MAX_ANSWERS)
    if error:
        return error
    comment_limit, error = _optional_int(_param(request, 'comment_limit'),
                                         'comment_limit', 3, 0, MAX_COMMENTS)
    if error:
        return error
    question_comment_limit, error = _optional_int(_param(request, 'question_comment_limit'),
                                                  'question_comment_limit', 10,
                                                  0, MAX_COMMENTS)
    if error:
        return error

    cookie = (_param(request, 'cookie') or '').strip()
    ok, result = utils.get_question(question_id, answer_limit, comment_limit,
                                    question_comment_limit, cookie=cookie)
    if not ok:
        return _error_response(result)
    return _json_response(StatusCode.SUCCESS, data=result)


@require_http_methods(['GET', 'POST'])
def article_view(request):
    """知乎专栏文章详情（文章正文与图片 / 评论 / 大家都在搜）

    注意：文章页没有「回答列表」与「相关问题」两个模块，故只返回上述三块。

    :param article_id:    必填，知乎文章 ID（纯数字）或文章网页地址
    :param comment_limit: 可选，返回多少条评论，0~20（默认 10）
    :param cookie:        可选，调用方自带的知乎登录 Cookie
    """
    article_id = article_id_of(_param(request, 'article_id'))
    if not article_id:
        return _json_response(
            StatusCode.PARAM_VALUE_INVALID,
            msg='参数值非法: article_id 必填，需为知乎文章 ID（纯数字）或文章网页地址')

    comment_limit, error = _optional_int(_param(request, 'comment_limit'),
                                         'comment_limit', 10, 0, MAX_COMMENTS)
    if error:
        return error

    cookie = (_param(request, 'cookie') or '').strip()
    ok, result = utils.get_article(article_id, comment_limit, cookie=cookie)
    if not ok:
        return _error_response(result)
    return _json_response(StatusCode.SUCCESS, data=result)


@require_http_methods(['GET', 'POST'])
def search_view(request):
    """知乎综合搜索（结果自带完整正文与图片 / 大家都在搜）

    :param q:      必填，搜索关键词
    :param limit:  可选，返回多少条，1~20（默认 20，知乎单页上限）
    :param offset: 可选，翻页偏移，0~1000（默认 0）
    :param cookie: 可选，调用方自带的知乎登录 Cookie
    """
    keyword = (_param(request, 'q') or '').strip()
    if not keyword:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg='参数值非法: q 必填，为搜索关键词')

    limit, error = _optional_int(_param(request, 'limit'), 'limit',
                                 MAX_SEARCH_LIMIT, 1, MAX_SEARCH_LIMIT)
    if error:
        return error
    offset, error = _optional_int(_param(request, 'offset'), 'offset', 0,
                                  0, MAX_SEARCH_OFFSET)
    if error:
        return error

    cookie = (_param(request, 'cookie') or '').strip()
    ok, result = utils.get_search(keyword, limit, offset, cookie=cookie)
    if not ok:
        return _error_response(result)
    return _json_response(StatusCode.SUCCESS, data=result)
