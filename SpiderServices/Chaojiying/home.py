"""超级鹰图像识别爬虫 - ChaojiyingService

封装平台三个 HTTP 接口，各方法返回统一字典 {code, message, data}
（code=0 为成功，非 0 为平台错误码；message 为平台返回的中文说明）。

    识别     recognize(image_bytes, codetype, str_debug='')  扣费接口，上传即扣题分
    报错返分 report_error(pic_id)                            仅识别结果确实错误时调用
    查询题分 get_score()

使用示例:
    spider = ChaojiyingService()
    spider.get_score()
    spider.recognize(open('captcha.jpg', 'rb').read(), '1902')
    spider.report_error('9160109360600112681')
"""
import requests

from .utils import (
    PASSWORD,
    REPORT_URL,
    REQUEST_TIMEOUT,
    SCORE_URL,
    SOFT_ID,
    SOFT_KEY,
    UPLOAD_URL,
    USER,
    error_message,
    image_upload_part,
    md5_hex,
    response_dict,
)


class ChaojiyingService:
    def __init__(self):
        if not USER or not PASSWORD:
            raise RuntimeError('CHAOJIYING_USER / CHAOJIYING_PASS 未配置，请在 .env 中设置')
        # 账号密码每个请求都要带；密码以 pass2（md5）发送，不在请求中出现明文
        self.credentials = {'user': USER, 'pass2': md5_hex(PASSWORD)}
        if SOFT_ID:
            self.credentials['softid'] = SOFT_ID

    @staticmethod
    def _post_json(url, **kwargs):
        """POST 并解析 JSON

        :return: (True, dict) 或 (False, 错误信息)
        """
        try:
            resp = requests.post(url, timeout=REQUEST_TIMEOUT, **kwargs)
        except requests.RequestException as e:
            return False, f'请求超级鹰接口失败: {e}'
        try:
            return True, resp.json()
        except ValueError:
            return False, '超级鹰返回内容不是合法 JSON'

    @staticmethod
    def _parse(result, success_fields):
        """解析平台返回的 JSON，转为统一响应字典

        :param result: 平台返回字典，形如 {"err_no":0,"err_str":"OK",...}
        :param success_fields: 成功时要从返回里摘出的业务字段
        :return: {code, message, data}；成功时 data 为业务字段子集，失败时为 None
        """
        err_no = result.get('err_no')
        if err_no == 0:
            return response_dict(0, result.get('err_str') or 'OK',
                                 {f: result.get(f) for f in success_fields})
        # 失败的 code 即平台 err_no；说明优先取平台文案，平台没给就查本地对照表
        return response_dict(err_no or 1, error_message(err_no, result.get('err_str')))

    @staticmethod
    def _verify_md5(data):
        """按官方算法校验识别结果未被篡改

        算法（见 https://www.chaojiying.com/api-29.html）：把「软件ID,软件KEY,图片ID,图片结果」
        **按逗号拼接**后取 32 位小写 MD5，与返回的 md5 字段比对。
        注意分隔符是半角逗号（官方原文括号内的逗号即字面量，实测确认），漏掉逗号会全部校验失败。

        未配置软件ID 或 软件KEY 时跳过校验（平台此时也不返回有效校验值）。

        :param data: _parse 摘出的成功数据，含 pic_id / pic_str / md5
        :return: True 表示校验通过或已跳过
        """
        if not (SOFT_ID and SOFT_KEY):
            return True
        raw = f"{SOFT_ID},{SOFT_KEY},{data.get('pic_id')},{data.get('pic_str')}"
        return md5_hex(raw) == (data.get('md5') or '').lower()

    def recognize(self, image_bytes, codetype, str_debug=''):
        """上传图片识别（成功即扣费）

        :param image_bytes: 图片二进制内容（bmp / jpg / png，不超过 2M）
        :param codetype: 识别类型，取值见 utils.CODETYPES
        :param str_debug: 附加信息（如 9801 类型的 8a 指令），可为空
        :return: {code, message, data}；成功时 data = {pic_id, pic_str, md5}
        """
        data = {**self.credentials, 'codetype': codetype}
        if str_debug:
            data['str_debug'] = str_debug
        # 文件名与 Content-Type 必须与图片真实格式一致（见 image_upload_part）
        filename, mime = image_upload_part(image_bytes)
        files = {'userfile': (filename, image_bytes, mime)}
        ok, result = self._post_json(UPLOAD_URL, data=data, files=files)
        if not ok:
            return response_dict(1, result)
        parsed = self._parse(result, ['pic_id', 'pic_str', 'md5'])
        if parsed['code'] == 0 and not self._verify_md5(parsed['data']):
            return response_dict(2, '识别结果 md5 校验不通过，返回内容可能已被篡改')
        return parsed

    def report_error(self, pic_id):
        """报错返分

        官方限制：仅限识别结果确实错误时调用（恶意报错会被评估信用），
        且必须在拿到 pic_id 后 3 分钟内、部分识别类型不支持。

        :param pic_id: 识别接口返回的图片标识号
        :return: {code, message, data}
        """
        data = {**self.credentials, 'id': pic_id}
        ok, result = self._post_json(REPORT_URL, data=data)
        if not ok:
            return response_dict(1, result)
        return self._parse(result, [])

    def get_score(self):
        """查询题分余额

        :return: {code, message, data}；成功时 data = {tifen, tifen_lock}
        """
        ok, result = self._post_json(SCORE_URL, data=self.credentials)
        if not ok:
            return response_dict(1, result)
        return self._parse(result, ['tifen', 'tifen_lock'])
