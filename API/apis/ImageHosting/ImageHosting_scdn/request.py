"""ImageHosting 图床 API 请求处理视图

提供图床服务接口:
    POST /api/ImageHosting/scdn/upload  上传图片（scdn.io 线路），返回可直链访问的 CDN 地址
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
    """按爬虫返回的错误消息前缀映射状态码（统一口径，见 StatusCode.from_message）"""
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
    """上传图片（scdn.io 图床）

    请求体: multipart/form-data（推荐，带文件）或 application/x-www-form-urlencoded（走 image_url）

    参数:
        image               (选填, file): 本地图片文件，字段名 image；与 image_url 二选一
        image_url           (选填, str):  远程图片地址（http/https），服务端代理拉取；与 image 二选一
        output_format       (选填, str):  输出格式 auto/jpg/jpeg/png/webp/gif/webp_animated，默认 auto
        cdn_domain          (选填, str):  指定外链 CDN 域名，留空由服务端自动选择
        storage_destination (选填, str):  存储位置 local/telegram/r2，默认 local
        password_enabled    (选填, bool): 是否加密上传，默认 false（加密图永不秒传）
        image_password      (选填, str):  访问密码/答案，password_enabled=true 时必填
        password_type       (选填, str):  密码模式 plain/qa，默认 plain
        password_question   (选填, str):  问答式密码的问题文本，password_type=qa 时必填
    """
    uploaded = request.FILES.get("image")
    image_url = (request.POST.get("image_url") or "").strip() or None

    ok, result = utils.upload_image(
        image=uploaded,
        image_url=image_url,
        output_format=(request.POST.get("output_format") or "auto").strip(),
        password_enabled=(request.POST.get("password_enabled") or "false").strip(),
        image_password=(request.POST.get("image_password") or "").strip() or None,
        password_type=(request.POST.get("password_type") or "plain").strip(),
        password_question=(request.POST.get("password_question") or "").strip() or None,
        cdn_domain=(request.POST.get("cdn_domain") or "").strip() or None,
        storage_destination=(request.POST.get("storage_destination") or "").strip() or None,
    )
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=result)
    return _spider_result(result)
