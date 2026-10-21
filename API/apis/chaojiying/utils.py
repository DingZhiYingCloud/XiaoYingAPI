"""超级鹰 验证码识别 服务层封装

对 SpiderServices.Chaojiying.home.ChaojiyingService 做统一异常处理，
返回平台口径的 {code, message, data} 字典（code=0 为成功），由视图层映射为统一响应。

图片外链的下载（download_image）也在此层完成：视图层先做 url_safety 校验，
本层对**每一跳重定向**都重新校验，防止公网 URL 302 到内网（SSRF）。
"""
from urllib.parse import urljoin

import requests

from API.common.errors import safe_error
from API.common.url_safety import check_public_http_url
from SpiderServices.Chaojiying.home import ChaojiyingService
from SpiderServices.Chaojiying.utils import response_dict

# 外链图片下载超时（秒）
_DOWNLOAD_TIMEOUT = 15
# 最多跟随的重定向跳数
_MAX_REDIRECTS = 3
# 下载体积上限（识别图片本身有 2MB 限制，这里再兜一层，防止被塞超大文件）
_MAX_DOWNLOAD_BYTES = 5 * 1024 * 1024


def _call(method_name, **kwargs):
    """通用爬虫调用包装：异常统一转成 {code, message, data}"""
    try:
        return getattr(ChaojiyingService(), method_name)(**kwargs)
    except Exception as e:
        return response_dict(1, safe_error(f'{method_name} 调用', e))


def download_image(url):
    """下载外链图片（逐跳校验重定向，防 SSRF）

    视图层已做过一次校验，但 requests 默认会跟随 302；攻击者可让公网地址 302 到
    `http://127.0.0.1:...`，只校验第一跳等于没校验。这里禁用自动重定向，
    每一跳都重新 check_public_http_url。

    :return: (True, 图片字节) 或 (False, 错误信息)
    """
    current = url
    for _hop in range(_MAX_REDIRECTS + 1):
        ok, reason = check_public_http_url(current)
        if not ok:
            return False, f'图片地址不可访问: {reason}'

        try:
            resp = requests.get(current, timeout=_DOWNLOAD_TIMEOUT,
                                allow_redirects=False, stream=True)
        except requests.RequestException as e:
            return False, safe_error('图片下载', e)

        try:
            if resp.is_redirect:
                location = (resp.headers.get('Location') or '').strip()
                if not location:
                    return False, '图片地址重定向缺少 Location'
                current = urljoin(current, location)
                continue

            resp.raise_for_status()
            buffer = bytearray()
            for chunk in resp.iter_content(64 * 1024):
                buffer.extend(chunk)
                if len(buffer) > _MAX_DOWNLOAD_BYTES:
                    return False, '图片超过下载大小上限'
            return True, bytes(buffer)
        except requests.RequestException as e:
            return False, safe_error('图片下载', e)
        finally:
            resp.close()

    return False, '图片地址重定向次数过多'


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
