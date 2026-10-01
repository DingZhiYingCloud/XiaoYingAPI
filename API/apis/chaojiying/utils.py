"""超级鹰 验证码识别 服务层封装

对 SpiderServices.Chaojiying.home.ChaojiyingService 做统一异常处理，
返回平台口径的 {code, message, data} 字典（code=0 为成功），由视图层映射为统一响应。

图片外链的下载（download_image）也在此层完成：视图层先做 url_safety 校验，
本层只负责取回字节。
"""
import requests

from SpiderServices.Chaojiying.home import ChaojiyingService
from SpiderServices.Chaojiying.utils import response_dict

# 外链图片下载超时（秒）
_DOWNLOAD_TIMEOUT = 15


def _call(method_name, **kwargs):
    """通用爬虫调用包装：异常统一转成 {code, message, data}"""
    try:
        return getattr(ChaojiyingService(), method_name)(**kwargs)
    except Exception as e:
        return response_dict(1, f'{method_name} 调用异常: {e}')


def download_image(url):
    """下载外链图片（调用方须先用 API/common/url_safety 校验地址，S-09）

    :return: (True, 图片字节) 或 (False, 错误信息)
    """
    try:
        resp = requests.get(url, timeout=_DOWNLOAD_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        return False, f'图片下载失败: {e}'
    return True, resp.content


def recognize(image_bytes, codetype, str_debug=''):
    """上传图片识别

    :param image_bytes: 图片二进制内容（bmp / jpg / png，不超过 2MB）
    :param codetype: 识别类型，取值见 SpiderServices.Chaojiying.utils.CODETYPES
    :param str_debug: 附加信息（如 9801 类型的指令），可为空
    :return: {code, message, data}；成功时 data = {pic_id, pic_str, md5}
    """
    return _call('recognize', image_bytes=image_bytes, codetype=codetype, str_debug=str_debug)


def report_error(pic_id):
    """报错返分

    :param pic_id: 识别接口返回的图片标识号
    :return: {code, message, data}
    """
    return _call('report_error', pic_id=pic_id)


def get_score():
    """查询题分余额

    :return: {code, message, data}；成功时 data = {tifen, tifen_lock}
    """
    return _call('get_score')
