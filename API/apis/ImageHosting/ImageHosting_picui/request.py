"""PicUI 图床 API 请求处理视图

提供图床服务接口（PicUI 线路）:
    POST /api/ImageHosting/picui/upload  上传图片，返回可直链访问的外链地址
    GET  /api/ImageHosting/picui/tokens  查询服务端 Token 池容量情况
    POST /api/ImageHosting/picui/tokens  上传/导入 Token（支持多个 Token 或按行存放的 Token 文件）

鉴权说明：上传使用的 PicUI 账号 Token 由服务端 Token 池统一管理，
调用方无需提供；Token 池容量用尽时自动删除该 Token 并切换下一个。
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


def _fail_response(msg):
    """按错误消息映射状态码（统一口径见 StatusCode.from_message；池空为服务暂不可用）"""
    if msg.startswith("无可用 Token"):
        return _json_response(StatusCode.SERVICE_UNAVAILABLE, msg=msg)
    return _json_response(StatusCode.from_message(msg, fallback=StatusCode.EXTERNAL_API_FAILED), msg=msg)


def _spider_result(result):
    """将爬虫的 {code, message, data} 映射为项目统一响应"""
    if not isinstance(result, dict):
        return _json_response(StatusCode.UNKNOWN_ERROR, msg=str(result))
    if result.get("code") == 0:
        return _json_response(StatusCode.SUCCESS, data=result.get("data"), msg=result.get("message"))
    return _fail_response(result.get("message") or "上传失败")


@require_http_methods(["POST"])
def upload_view(request):
    """上传图片（PicUI 图床）

    请求体: multipart/form-data

    参数:
        image        (必填, file): 本地图片文件，字段名 image
        permission   (选填, int):  图片权限 1=公开（默认）/ 0=私有
        strategy_id  (选填, str):  储存策略 ID，默认 1
        album_id     (选填, str):  相册 ID
        expired_at   (选填, str):  图片过期时间，格式 yyyy-MM-dd HH:mm:ss
        upload_token (选填, str):  临时上传 Token（对应 PicUI 的 token 字段），一般不传
    """
    uploaded = request.FILES.get("image")

    ok, result = utils.upload_image(
        image=uploaded,
        permission=(request.POST.get("permission") or "").strip() or None,
        strategy_id=(request.POST.get("strategy_id") or "").strip() or None,
        album_id=(request.POST.get("album_id") or "").strip() or None,
        expired_at=(request.POST.get("expired_at") or "").strip() or None,
        upload_token=(request.POST.get("upload_token") or "").strip() or None,
    )
    if not ok:
        return _fail_response(result)
    return _spider_result(result)


@require_http_methods(["GET", "POST"])
def tokens_view(request):
    """Token 池管理

    GET : 查询 Token 池（数量 / 总容量 / 已用 / 剩余，Token 已脱敏，容量含 MB 字段）
    POST: 新增 Token 到池中，支持三种传法（可组合）:
        tokens      (选填, 可重复): 一个或多个 Token，可用重复字段、逗号或换行分隔
        token_file  (选填, file):  文本文件，按行存放 Token（一行一个）
        capacity_mb (选填, number): 每个 Token 的容量（MB），默认 50
    """
    if request.method == "GET":
        ok, result = utils.list_tokens()
    else:
        raw_tokens = list(request.POST.getlist("tokens"))
        token_file = request.FILES.get("token_file")
        if token_file:
            try:
                raw_tokens.append(token_file.read().decode("utf-8"))
            except UnicodeDecodeError:
                return _json_response(StatusCode.PARAM_FORMAT_ERROR,
                                      msg="参数格式错误: Token 文件必须为 UTF-8 编码")
        ok, result = utils.add_tokens(
            raw_tokens, capacity_mb=(request.POST.get("capacity_mb") or "").strip() or None)

    if not ok:
        return _fail_response(result)
    if request.method == "POST":
        # 明确告知新增/重复数量：相同 Token 不会重复导入
        return _json_response(
            StatusCode.SUCCESS, data=result,
            msg=f"导入完成：新增 {result['created']} 个，重复跳过 {result['duplicated']} 个")
    return _json_response(StatusCode.SUCCESS, data=result)
