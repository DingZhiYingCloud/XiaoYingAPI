"""超级鹰（chaojiying）图像识别平台 - 常量与凭据

平台文档：
    识别     https://upload.chaojiying.net/Upload/Processing.php   （api-5）
    报错返分 https://upload.chaojiying.net/Upload/ReportError.php
    查询题分 https://upload.chaojiying.net/Upload/GetScore.php
    识别类型与价格 https://www.chaojiying.com/price.html

凭据从项目根目录的 .env 读取（禁止硬编码进代码库）：
    CHAOJIYING_USER     超级鹰账号
    CHAOJIYING_PASS     超级鹰密码（请求时以 md5 值 pass2 发送，不传明文）
    CHAOJIYING_SOFT_ID  软件ID（用户中心-软件ID 处生成，可为空）
    CHAOJIYING_SOFT_KEY 软件KEY（与软件ID 成对，用于识别结果 md5 防篡改校验，可为空）
"""
import hashlib
import os

from dotenv import load_dotenv

load_dotenv()

# 三个接口地址（官方说明：接口主机为多 IP 轮询，勿固定 IP）
UPLOAD_URL = 'https://upload.chaojiying.net/Upload/Processing.php'
REPORT_URL = 'https://upload.chaojiying.net/Upload/ReportError.php'
SCORE_URL = 'https://upload.chaojiying.net/Upload/GetScore.php'

USER = os.getenv('CHAOJIYING_USER', '') or ''
PASSWORD = os.getenv('CHAOJIYING_PASS', '') or ''
SOFT_ID = os.getenv('CHAOJIYING_SOFT_ID', '') or ''
SOFT_KEY = os.getenv('CHAOJIYING_SOFT_KEY', '') or ''

# 平台硬要求：单张图片不能超过 2M，推荐 bmp / jpg / jpeg
MAX_IMAGE_BYTES = 2 * 1024 * 1024
# 官方说明「HTTP 请求超时 60 秒（人工识别时会更慢）」
REQUEST_TIMEOUT = 60

# 识别类型（codetype）→ (说明, 官方单价-题分)，取自 https://www.chaojiying.com/price.html
# 精确匹配类型可提高识别速度与正确率；官方新增类型时在此追加即可（视图白名单与文档下拉都由本表派生）
CODETYPES = {
    # 英文数字
    '1902': ('4~6位英文数字', '10/12/15'),
    '1004': ('1~4位英文数字', '10'),
    '1005': ('1~5位英文数字', '12'),
    '1006': ('1~6位英文数字', '15'),
    '1007': ('1~7位英文数字', '17.5'),
    '1008': ('1~8位英文数字', '20'),
    '1009': ('1~9位英文数字', '22.5'),
    '1010': ('1~10位英文数字', '25'),
    '1012': ('1~12位英文数字', '30'),
    '1020': ('1~20位英文数字', '50'),
    # 中文汉字
    '2001': ('1位纯汉字', '10'),
    '2002': ('1~2位纯汉字', '20'),
    '2003': ('1~3位纯汉字', '30'),
    '2004': ('1~4位纯汉字', '40'),
    '2005': ('1~5位纯汉字', '50'),
    '2006': ('1~6位纯汉字', '60'),
    '2007': ('1~7位纯汉字', '70'),
    # 纯英文
    '3004': ('1~4位纯英文', '10'),
    '3005': ('1~5位纯英文', '12'),
    '3006': ('1~6位纯英文', '15'),
    '3007': ('1~7位纯英文', '17.5'),
    '3008': ('1~8位纯英文', '20'),
    '3012': ('1~12位纯英文', '30'),
    # 纯数字
    '4004': ('1~4位纯数字', '10'),
    '4005': ('1~5位纯数字', '12'),
    '4006': ('1~6位纯数字', '15'),
    '4007': ('1~7位纯数字', '17.5'),
    '4008': ('1~8位纯数字', '20'),
    # 任意特殊字符
    '5000': ('不定长汉字英文数字', '2.5/英文, 10/汉字(基础10)'),
    '5108': ('8位英文数字(含特殊字符)', '22'),
    '5201': ('拼音首字母 / 计算题 / 成语混合', '首字母20, 计算20, 成语40'),
    # 问答类型
    '6001': ('计算题(返回计算结果)', '15'),
    '6004': ('问答题 / 智能回答题', '15'),
    '6900': ('中英数混合(配合8f指令取特定色彩)', '基础10'),
    # 坐标点击类
    '9602': ('水平拼图的两个坐标', '36'),
    '9801': ('按指定字符定位(返回指定字坐标)', '9/定位, 最低28'),
    '9800': ('文字定位(返回所有字及坐标)', '6/定位, 最低28'),
    '9901': ('定位图上有且仅有的一个图形块中心点坐标', '16'),
    '9902': ('定位图上有且仅有的两个图形块中心点坐标', '24'),
    '9900': ('定位各种滑块 / 缺口 / 色块', '8/定位+8'),
    '9101': ('按操作提示返回固定1个坐标', '16'),
    '9102': ('按操作提示返回固定2个坐标', '24'),
    '9103': ('按操作提示返回固定3个坐标', '32'),
    '9104': ('按操作提示返回固定4个坐标', '40'),
    '9004': ('按操作提示返回1~4个坐标', '40'),
    '9005': ('按操作提示返回1~5个坐标', '48'),
    '9006': ('按操作提示返回1~6个坐标', '56'),
    '9008': ('按操作提示返回1~8个坐标', '72'),
    '9009': ('按操作提示返回1~9个坐标', '80'),
}


def md5_hex(text: str) -> str:
    """32 位小写 md5（平台 pass2 参数用）"""
    return hashlib.md5(text.encode('utf-8')).hexdigest()


# 平台错误码对照表（官方 https://www.chaojiying.com/api-23.html）
# 多数错误平台会在 err_str 里给中文说明，但**少数不给**（实测 -1013 就只回一个数字），
# 日志里只剩「识别失败」这种没法排查的兜底文案，故本地存一份对照。
ERROR_CODES = {
    -1001: '用户参数异常',
    -1002: '无此用户名',
    -1004: '类型参数错误',
    -1005: '无可用题分',
    -1011: '图片ID异常',
    -1013: '错误率太高',
    -10132: '此图片ID已报过',
    -10133: '该识别类型不支持调用报错接口',
    -10012: 'access_token异常',
    -10023: '用户名的密码出错',
    -10052: '无可用资源包',
    -10061: '不是有效的图片文件',
    -10062: '文件超大 1024k',
    -10064: '图片无法被识别',
    -10071: 'IP受限（白名单）',
    -10072: 'IP受限（黑名单）',
    -100612: 'base64字符解析异常',
    -2001: '上传图片出错',
    -429: '请求过于频繁',
}


def error_message(err_no, err_str: str = '') -> str:
    """错误的可读说明：优先平台给的中文，其次本地对照表，最后兜底带上错误码"""
    return (err_str or '').strip() or ERROR_CODES.get(err_no) or f'平台返回错误码 {err_no}'


# 图片格式探测表（按文件头，顺序敏感：GIF / BM 这类弱特征放最后）
_IMAGE_SIGNATURES = (
    (b'\x89PNG\r\n\x1a\n', 'png', 'image/png'),
    (b'\xff\xd8\xff', 'jpg', 'image/jpeg'),
    (b'GIF8', 'gif', 'image/gif'),
    (b'BM', 'bmp', 'image/bmp'),
)


def image_upload_part(image_bytes: bytes, default_name: str = 'captcha'):
    """按文件头判断图片真实格式，返回上传给平台用的 (文件名, Content-Type)

    必须与图片真实格式一致：平台按扩展名/类型选解码器，把 PNG 声明成 jpg 会解码出
    乱码（实测表现为识别结果完全不对，或平台直接判为识别失败）。

    :param image_bytes: 图片二进制内容
    :param default_name: 文件名主体（不含扩展名）
    :return: (文件名, Content-Type)；格式未识别时按 jpg 处理
    """
    for magic, ext, mime in _IMAGE_SIGNATURES:
        if image_bytes.startswith(magic):
            return f'{default_name}.{ext}', mime
    return f'{default_name}.jpg', 'image/jpeg'


def response_dict(code: int = 0, message: str = '', data=None) -> dict:
    """统一响应字典（与其它爬虫一致：code=0 表示成功）"""
    return {'code': code, 'message': message, 'data': data}
