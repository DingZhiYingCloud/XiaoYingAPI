"""超级鹰 验证码识别 API 请求处理视图

提供 3 个接口:
    POST /api/chaojiying/ocr           图片识别
    POST /api/chaojiying/report-error  报错返分
    GET  /api/chaojiying/score         查询题分余额

平台说明见 https://www.chaojiying.com/api-5.html；识别按题分计费（上传即扣费）。
"""
import base64

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from API.common import StatusCode
from API.common.url_safety import check_public_http_url
from SpiderServices.Chaojiying.utils import CODETYPES, MAX_IMAGE_BYTES
from . import utils


def _json_response(code, data=None, msg=None):
    return JsonResponse({
        "code": code,
        "msg": msg or StatusCode.get_message(code),
        "data": data,
    })


def _spider_result(result):
    """将服务层的 {code, message, data} 映射为项目统一响应

    失败信息来自超级鹰平台（非本站业务文案），一律按「外部服务调用失败」返回，
    平台的中文说明原样放进 msg（不走 StatusCode.from_message 的关键词映射，
    否则「用户不存在」这类平台文案会被误判成 20030 资源不存在）。
    """
    if not isinstance(result, dict):
        return _json_response(StatusCode.UNKNOWN_ERROR, msg=str(result))
    if result.get("code") == 0:
        return _json_response(StatusCode.SUCCESS, data=result.get("data"),
                              msg=result.get("message"))
    return _json_response(StatusCode.EXTERNAL_API_FAILED,
                          msg=result.get("message") or "识别失败")


def _decode_base64_image(raw):
    """解析 base64 图片字符串（兼容 data URI 前缀与换行）

    :return: (图片字节, 错误提示)；错误提示非空表示解析失败
    """
    if raw.startswith('data:'):
        _, _, raw = raw.partition(',')
    raw = ''.join(raw.split())  # 去掉换行等空白，兼容按行折行的 base64
    try:
        return base64.b64decode(raw, validate=True), None
    except (ValueError, TypeError):
        return None, '参数格式错误: image 不是合法的 base64 字符串'


def _resolve_image(request):
    """解析图片入参 → 二进制

    三种来源任选其一：file（上传文件）/ image（http(s) 外链）/ image（base64）。
    外链下载前先做公网地址校验（S-09，拒绝内网 / 回环 / 保留地址）。

    :return: (图片字节, 错误响应)；错误响应非 None 时直接返回
    """
    uploaded = request.FILES.get('file')
    if uploaded is not None:
        image_bytes = uploaded.read()
    else:
        raw = request.POST.get('image', '').strip()
        if not raw:
            return None, _json_response(
                StatusCode.PARAM_MISSING, msg='参数缺失: file(图片文件) 或 image(base64/图片URL)')
        if raw.startswith(('http://', 'https://')):
            ok, reason = check_public_http_url(raw)
            if not ok:
                return None, _json_response(StatusCode.PARAM_VALUE_INVALID,
                                            msg=f'参数值非法: {reason}')
            ok, image_bytes = utils.download_image(raw)
            if not ok:
                return None, _json_response(StatusCode.EXTERNAL_API_FAILED, msg=image_bytes)
        else:
            image_bytes, err = _decode_base64_image(raw)
            if err:
                return None, _json_response(StatusCode.PARAM_FORMAT_ERROR, msg=err)

    if not image_bytes:
        return None, _json_response(StatusCode.PARAM_VALUE_INVALID, msg='参数值非法: 图片内容为空')
    if len(image_bytes) > MAX_IMAGE_BYTES:
        return None, _json_response(
            StatusCode.PARAM_VALUE_INVALID,
            msg=f'参数值非法: 图片不得超过 {MAX_IMAGE_BYTES // 1024 // 1024}MB')
    return image_bytes, None


@require_http_methods(["POST"])
def ocr_view(request):
    """图片识别

    表单参数:
        file      (二选一, 文件): 上传图片文件（bmp / jpg / png，不超过 2MB）
        image     (二选一, 文本): 图片 base64 字符串，或 http(s) 图片地址
        codetype  (必填, 文本): 识别类型（官方类型表，见文档下拉）
        str_debug (选填, 文本): 附加信息，如 9801 定位类的指令
    """
    codetype = request.POST.get('codetype', '').strip()
    if not codetype:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: codetype(识别类型)')
    if codetype not in CODETYPES:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg='参数值非法: codetype 不在支持的识别类型内')

    image_bytes, error = _resolve_image(request)
    if error is not None:
        return error

    str_debug = request.POST.get('str_debug', '').strip()
    return _spider_result(utils.recognize(image_bytes, codetype, str_debug))


@require_http_methods(["POST"])
def report_error_view(request):
    """报错返分

    仅在识别结果确实错误时调用（官方：恶意报错会被评估信用），
    且必须在拿到 pic_id 后 3 分钟内、部分识别类型不支持。

    表单参数:
        pic_id (必填, 文本): 识别接口返回的图片标识号
    """
    pic_id = request.POST.get('pic_id', '').strip()
    if not pic_id:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: pic_id(图片标识号)')
    return _spider_result(utils.report_error(pic_id))


@require_http_methods(["GET"])
def score_view(request):
    """查询题分余额（无参数）"""
    return _spider_result(utils.get_score())
