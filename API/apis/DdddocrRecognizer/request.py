"""DdddocrRecognizer API 请求处理视图

提供 7 个接口:
    POST /api/ddddocr/ocr              OCR 文字识别
    POST /api/ddddocr/set-ranges       设置 OCR 字符范围
    POST /api/ddddocr/detect           目标检测
    POST /api/ddddocr/slide-match      滑块匹配（边缘匹配法）
    POST /api/ddddocr/slide-comparison 滑块匹配（差异比较法）
    POST /api/ddddocr/batch-ocr        批量 OCR 识别
    POST /api/ddddocr/save-debug       保存调试图片
"""
import json

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


def _spider_json(result):
    """将爬虫 dict 结果转为 JsonResponse"""
    if not isinstance(result, dict):
        return _json_response(StatusCode.UNKNOWN_ERROR, msg=str(result))
    if result.get("code") == 0:
        return _json_response(StatusCode.SUCCESS, data=result.get("data"),
                              msg=result.get("message", "成功"))
    else:
        return _json_response(StatusCode.EXTERNAL_API_FAILED,
                              msg=result.get("message", "识别失败"))


def _resolve_image(request, field_name, param_name):
    """从请求中解析图片：文件上传 → bytes；表单参数 → 原样字符串"""
    uploaded = request.FILES.get(field_name)
    if uploaded:
        return uploaded.read()
    src = request.POST.get(param_name or field_name, "").strip()
    if not src:
        return None
    return src


def _parse_init_kwargs(request):
    """解析可选的 ddddocr 初始化参数（beta/use_gpu/import_onnx_path/charsets_path 等）"""
    kwargs = {}
    for key in ("beta", "use_gpu", "old"):
        val = request.POST.get(key, "").strip().lower()
        if val == "true":
            kwargs[key] = True
        elif val == "false":
            kwargs[key] = False
    for key in ("device_id",):
        val = request.POST.get(key, "").strip()
        if val.isdigit():
            kwargs[key] = int(val)
    for key in ("import_onnx_path", "charsets_path"):
        val = request.POST.get(key, "").strip()
        if val:
            kwargs[key] = val
    return kwargs


# ==================== 1. OCR 文字识别 ====================


@require_http_methods(["POST"])
def ocr_view(request):
    """OCR 文字识别

    识别图片中的文字内容。

    参数:
        image               (二选一,file/表单): 上传图片文件 或 图片URL 或 base64 字符串
        image_url           (二选一,表单): 图片URL（与 image 二选一）
        probability         (选填,表单): true/false，是否返回概率分布，默认 false
        png_fix             (选填,表单): true/false，是否修复透明 PNG，默认 false
        colors              (选填,表单): JSON 数组，如 ["red","blue"]；颜色过滤
        custom_color_ranges (选填,表单): JSON 对象，自定义颜色范围
        beta                (选填,表单): true/false，是否启用 Beta 模型
    """
    image = _resolve_image(request, "image", "image_url")
    if image is None:
        return _json_response(StatusCode.PARAM_MISSING,
                              msg="参数缺失: image(图片文件/URL/base64)")

    probability = request.POST.get("probability", "").strip().lower() == "true"
    png_fix = request.POST.get("png_fix", "").strip().lower() == "true"

    colors = None
    colors_raw = request.POST.get("colors", "").strip()
    if colors_raw:
        try:
            colors = json.loads(colors_raw)
            if not isinstance(colors, list):
                return _json_response(StatusCode.PARAM_FORMAT_ERROR,
                                      msg="参数格式错误: colors 必须为 JSON 数组")
        except json.JSONDecodeError:
            return _json_response(StatusCode.PARAM_FORMAT_ERROR,
                                  msg="参数格式错误: colors 不是合法的 JSON")

    custom_color_ranges = None
    ccr_raw = request.POST.get("custom_color_ranges", "").strip()
    if ccr_raw:
        try:
            custom_color_ranges = json.loads(ccr_raw)
            if not isinstance(custom_color_ranges, dict):
                return _json_response(StatusCode.PARAM_FORMAT_ERROR,
                                      msg="参数格式错误: custom_color_ranges 必须为 JSON 对象")
        except json.JSONDecodeError:
            return _json_response(StatusCode.PARAM_FORMAT_ERROR,
                                  msg="参数格式错误: custom_color_ranges 不是合法的 JSON")

    init_kwargs = _parse_init_kwargs(request)
    result = utils.ocr(image, probability=probability, png_fix=png_fix,
                       colors=colors, custom_color_ranges=custom_color_ranges,
                       **init_kwargs)
    return _spider_json(result)


# ==================== 2. 设置字符范围 ====================


@require_http_methods(["POST"])
def set_ranges_view(request):
    """设置 OCR 字符范围

    参数:
        ranges (必填,表单): 字符范围。
            预定义数字: 0(数字), 1(小写), 2(大写), 3(大小写),
                        4(小写+数字), 5(大写+数字), 6(大小写+数字), 7(默认)
            自定义: 如 "0123456789+-x/="
        beta (选填): true/false，是否启用 Beta 模型
    """
    ranges = request.POST.get("ranges", "").strip()
    if not ranges:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: ranges(字符范围)")

    init_kwargs = _parse_init_kwargs(request)
    result = utils.set_ranges(ranges, **init_kwargs)
    return _spider_json(result)


# ==================== 3. 目标检测 ====================


@require_http_methods(["POST"])
def detect_view(request):
    """目标检测

    检测图片中的目标位置，返回边界框坐标。

    参数:
        image     (必填,file/表单): 上传图片文件 或 图片URL 或 base64 字符串
        image_url (选填,表单): 图片URL（与 image 二选一）
    """
    image = _resolve_image(request, "image", "image_url")
    if image is None:
        return _json_response(StatusCode.PARAM_MISSING,
                              msg="参数缺失: image(图片文件/URL/base64)")

    init_kwargs = _parse_init_kwargs(request)
    result = utils.detect(image, **init_kwargs)
    return _spider_json(result)


# ==================== 4. 滑块匹配（边缘匹配法）====================


@require_http_methods(["POST"])
def slide_match_view(request):
    """滑块验证码匹配（算法1：边缘匹配法）

    通过边缘检测匹配滑块在背景图中的缺口位置。

    参数:
        slide_image       (必填,file/表单): 滑块图片文件/URL/base64
        slide_image_url   (选填,表单): 滑块图片URL
        bg_image          (必填,file/表单): 背景图片文件/URL/base64
        bg_image_url      (选填,表单): 背景图片URL
        simple_target     (选填,表单): true/false，是否使用简单目标模式，默认 false
    """
    slide = _resolve_image(request, "slide_image", "slide_image_url")
    bg = _resolve_image(request, "bg_image", "bg_image_url")

    if slide is None:
        return _json_response(StatusCode.PARAM_MISSING,
                              msg="参数缺失: slide_image(滑块图片文件/URL/base64)")
    if bg is None:
        return _json_response(StatusCode.PARAM_MISSING,
                              msg="参数缺失: bg_image(背景图片文件/URL/base64)")

    simple_target = request.POST.get("simple_target", "").strip().lower() == "true"
    init_kwargs = _parse_init_kwargs(request)
    result = utils.slide_match(slide, bg, simple_target=simple_target, **init_kwargs)
    return _spider_json(result)


# ==================== 5. 滑块匹配（差异比较法）====================


@require_http_methods(["POST"])
def slide_comparison_view(request):
    """滑块验证码匹配（算法2：图像差异比较法）

    通过直接比较背景图与滑块图的位置差异来确定缺口位置。

    参数:
        slide_image     (必填,file/表单): 滑块图片文件/URL/base64
        slide_image_url (选填,表单): 滑块图片URL
        bg_image        (必填,file/表单): 背景图片文件/URL/base64
        bg_image_url    (选填,表单): 背景图片URL
    """
    slide = _resolve_image(request, "slide_image", "slide_image_url")
    bg = _resolve_image(request, "bg_image", "bg_image_url")

    if slide is None:
        return _json_response(StatusCode.PARAM_MISSING,
                              msg="参数缺失: slide_image(滑块图片文件/URL/base64)")
    if bg is None:
        return _json_response(StatusCode.PARAM_MISSING,
                              msg="参数缺失: bg_image(背景图片文件/URL/base64)")

    init_kwargs = _parse_init_kwargs(request)
    result = utils.slide_comparison(slide, bg, **init_kwargs)
    return _spider_json(result)


# ==================== 6. 批量 OCR ====================


@require_http_methods(["POST"])
def batch_ocr_view(request):
    """批量 OCR 识别

    识别指定服务器目录下所有匹配的图片文件。

    参数:
        image_dir   (必填,表单): 服务器上的图片目录路径
        pattern     (选填,表单): 文件匹配模式，默认 "*.jpg"。
                    支持分号分隔多个模式，如 "*.jpg;*.png"
        probability (选填,表单): true/false，是否返回概率分布，默认 false
        png_fix     (选填,表单): true/false，是否修复透明 PNG，默认 false
        colors      (选填,表单): JSON 数组，颜色过滤
        beta        (选填,表单): true/false，是否启用 Beta 模型
    """
    image_dir = request.POST.get("image_dir", "").strip()
    if not image_dir:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: image_dir(图片目录路径)")

    pattern = request.POST.get("pattern", "*.jpg").strip()
    probability = request.POST.get("probability", "").strip().lower() == "true"
    png_fix = request.POST.get("png_fix", "").strip().lower() == "true"

    colors = None
    colors_raw = request.POST.get("colors", "").strip()
    if colors_raw:
        try:
            colors = json.loads(colors_raw)
            if not isinstance(colors, list):
                return _json_response(StatusCode.PARAM_FORMAT_ERROR,
                                      msg="参数格式错误: colors 必须为 JSON 数组")
        except json.JSONDecodeError:
            return _json_response(StatusCode.PARAM_FORMAT_ERROR,
                                  msg="参数格式错误: colors 不是合法的 JSON")

    init_kwargs = _parse_init_kwargs(request)
    result = utils.batch_ocr(image_dir, pattern=pattern, probability=probability,
                             png_fix=png_fix, colors=colors, **init_kwargs)
    return _spider_json(result)


# ==================== 7. 保存调试图片 ====================


@require_http_methods(["POST"])
def save_debug_view(request):
    """保存调试图片到服务器本地

    将图片保存到服务器本地文件系统，便于人工验证识别结果。

    参数:
        image     (必填,file/表单): 图片文件/URL/base64
        image_url (选填,表单): 图片URL
        filename  (选填,表单): 保存的文件名，不传则自动生成
        save_dir  (选填,表单): 保存目录，不传则使用默认目录
    """
    image = _resolve_image(request, "image", "image_url")
    if image is None:
        return _json_response(StatusCode.PARAM_MISSING,
                              msg="参数缺失: image(图片文件/URL/base64)")

    filename = request.POST.get("filename", "").strip() or None
    save_dir = request.POST.get("save_dir", "").strip() or None

    init_kwargs = _parse_init_kwargs(request)
    result = utils.save_debug_image(image, filename=filename,
                                    save_dir=save_dir, **init_kwargs)
    return _spider_json(result)
