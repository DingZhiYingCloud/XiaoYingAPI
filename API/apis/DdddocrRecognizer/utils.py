"""DdddocrRecognizer 爬虫调用封装

本模块通过 importlib 按文件路径加载爬虫及其依赖模块，
避免与同目录下其他 spider 的 home.py / utils.py 模块名冲突。
"""
import sys
import os
import importlib.util

_SPIDER_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..',
                 'SpiderServices', 'DdddocrRecognizer')
)

# 加载 spider 的 utils.py → sys.modules['utils']（暂存后替换，确保 home.py 能导入）
_orig_utils = sys.modules.pop('utils', None)

_utils_path = os.path.join(_SPIDER_DIR, "utils.py")
_utils_spec = importlib.util.spec_from_file_location("utils", _utils_path)
_utils_module = importlib.util.module_from_spec(_utils_spec)
sys.modules['utils'] = _utils_module
_utils_spec.loader.exec_module(_utils_module)

# 加载 spider 的 home.py（from utils import ... 会走 sys.modules['utils']）
_home_path = os.path.join(_SPIDER_DIR, "home.py")
_home_spec = importlib.util.spec_from_file_location("ddddocr_home", _home_path)
_home_module = importlib.util.module_from_spec(_home_spec)
_home_module.__package__ = ""
sys.modules['ddddocr_home'] = _home_module
_home_spec.loader.exec_module(_home_module)

DdddocrRecognizer = _home_module.DdddocrRecognizer

# 恢复原始 utils（如果有的话），避免影响其他模块
if _orig_utils is not None:
    sys.modules['utils'] = _orig_utils
else:
    # 如果 pop 之前 utils 不存在，则清理我们留下的
    sys.modules.pop('utils', None)


def _make_recognizer(ocr=True, det=False, **init_kwargs):
    """创建 DdddocrRecognizer 实例"""
    try:
        return DdddocrRecognizer(ocr=ocr, det=det, show_ad=False, **init_kwargs)
    except Exception as e:
        return None


def _spider_result(result):
    """将爬虫的 {code, message, data} 映射为项目统一 JsonResponse"""
    from django.http import JsonResponse
    from API.common import StatusCode

    if not isinstance(result, dict):
        return JsonResponse({"code": StatusCode.UNKNOWN_ERROR, "msg": str(result), "data": None})
    if result.get("code") == 0:
        return JsonResponse({"code": StatusCode.SUCCESS, "msg": result.get("message", "成功"), "data": result.get("data")})
    else:
        return JsonResponse({"code": StatusCode.EXTERNAL_API_FAILED, "msg": result.get("message", "识别失败"), "data": None})


# ---------- 封装函数 ----------

def ocr(image_source, probability=False, png_fix=False, colors=None,
        custom_color_ranges=None, **init_kwargs):
    r = _make_recognizer(ocr=True, det=False, **init_kwargs)
    return (r or DdddocrRecognizer(ocr=True, det=False, show_ad=False)).ocr(
        image_source, probability=probability, png_fix=png_fix,
        colors=colors, custom_color_ranges=custom_color_ranges)


def set_ranges(ranges, **init_kwargs):
    r = _make_recognizer(ocr=True, det=False, **init_kwargs)
    return (r or DdddocrRecognizer(ocr=True, det=False, show_ad=False)).set_ranges(ranges)


def detect(image_source, **init_kwargs):
    r = _make_recognizer(ocr=False, det=True, **init_kwargs)
    return (r or DdddocrRecognizer(ocr=False, det=True, show_ad=False)).detect(image_source)


def slide_match(slide_image, background_image, simple_target=False, **init_kwargs):
    r = _make_recognizer(ocr=False, det=False, **init_kwargs)
    return (r or DdddocrRecognizer(ocr=False, det=False, show_ad=False)).slide_match(
        slide_image, background_image, simple_target=simple_target)


def slide_comparison(slide_image, background_image, **init_kwargs):
    r = _make_recognizer(ocr=False, det=False, **init_kwargs)
    return (r or DdddocrRecognizer(ocr=False, det=False, show_ad=False)).slide_comparison(
        slide_image, background_image)


def batch_ocr(image_dir, pattern="*.jpg", probability=False, png_fix=False,
              colors=None, **init_kwargs):
    r = _make_recognizer(ocr=True, det=False, **init_kwargs)
    return (r or DdddocrRecognizer(ocr=True, det=False, show_ad=False)).batch_ocr(
        image_dir, pattern=pattern, probability=probability,
        png_fix=png_fix, colors=colors)


def save_debug_image(image_source, filename=None, save_dir=None, **init_kwargs):
    r = _make_recognizer(ocr=True, det=False, **init_kwargs)
    return (r or DdddocrRecognizer(ocr=True, det=False, show_ad=False)).save_debug_image(
        image_source, filename=filename, save_dir=save_dir)
