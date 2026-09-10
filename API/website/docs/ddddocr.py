"""验证码识别服务 - 接口文档与在线调试数据

数据与 API/apis/DdddocrRecognizer/ 实际实现对齐（分类树 /api/ddddocr/ 为需签名）：
- ddddocr：本地 Python ddddocr 模型，OCR 识别 / 目标检测 / 滑块缺口匹配。
后续接入更多识别引擎时在 channels 追加即可。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ServiceSpec

# 图片来源：页面在线调试支持 ①直接上传图片文件 ②填图片 URL / base64 字符串
_IMG_NOTE = '文件字段与 URL/base64 字段至少提供一个；同时提供时文件优先。'

_FILE_ACCEPT = 'image/*'


def _img_file_param(name, label):
    """图片文件上传参数（multipart 字段）"""
    return ParamSpec(name, label, kind='file', required=False, accept=_FILE_ACCEPT,
                     desc='上传本地图片（页面调试现支持真实文件上传）')


def _url_param(name, label):
    """图片字符串参数（URL / base64）"""
    return ParamSpec(name, label, kind='text', required=False,
                     placeholder='https://example.com/captcha.png',
                     desc='或填写图片 URL / base64（无需本地文件时使用）')


def _bool_sel(name, label, default='false', desc=''):
    return ParamSpec(name, label, kind='select',
                     options=[{'value': 'false', 'label': 'false（默认）'},
                              {'value': 'true', 'label': 'true'}],
                     default=default, desc=desc)


SERVICE = ServiceSpec(
    slug='ddddocr',
    name='验证码识别',
    prefix='/api/ddddocr/',
    summary='基于 ddddocr 的通用验证码识别：OCR 文字识别、目标检测、滑块验证码缺口匹配。当前接入 ddddocr 单线路。',
    channels=[
        ChannelSpec(
            slug='ddddocr',
            name='ddddocr 通用识别',
            provider='Python ddddocr（本地模型）',
            auth_note='auth',
            note='纯本地模型识别，无第三方依赖回调。首次调用会加载模型、响应偏慢属正常。',
            endpoints=[
                EndpointSpec('ocr', 'OCR 文字识别', 'POST', '/api/ddddocr/ocr',
                             summary='识别图片中的文字内容，返回识别文本；可返回概率、按颜色过滤等。',
                             params=[
                                 _img_file_param('image', '图片文件(上传)'),
                                 _url_param('image_url', '或 图片URL/base64'),
                                 _bool_sel('probability', '返回概率分布',
                                           desc='true 时返回 data={text, probability}；false 时 data 为文本'),
                                 _bool_sel('png_fix', '修复透明 PNG', desc='true 时对透明通道图片做白底修复'),
                                 ParamSpec('colors', '颜色过滤(JSON 数组)', kind='textarea',
                                           placeholder='["red","blue"]',
                                           desc='选填：仅识别指定颜色文字，如 ["red","blue","green"]'),
                                 ParamSpec('custom_color_ranges', '自定义颜色范围(JSON 对象)', kind='textarea',
                                           placeholder='{"red": [[0,0,0],[10,255,255]]}',
                                           desc='选填：HSV 区间字典，需与 colors 配合使用'),
                                 _bool_sel('beta', 'Beta 模型', desc='true 时使用 Beta 版 OCR 模型（对部分验证码更准）'),
                             ],
                             notes=['本服务需项目签名；上传文件时请求体为 multipart/form-data。',
                                    _IMG_NOTE]),
                EndpointSpec('set_ranges', '设置 OCR 字符范围', 'POST', '/api/ddddocr/set-ranges',
                             summary='设置本次识别实例的字符范围（预定义编号或自定义字符集）。',
                             params=[
                                 ParamSpec('ranges', '字符范围', kind='text', required=True,
                                           placeholder='如 0 或 0123456789+-x/=',
                                           desc='必填：预定义 0=数字/1=小写/2=大写/3=大小写/4=小写+数字/5=大写+数字/6=大小写+数字/7=默认；或自定义字符串，如 "0123456789"'),
                                 _bool_sel('beta', 'Beta 模型', desc='选填：配合 Beta 模型使用'),
                             ],
                             notes=['注意：后端每次调用都会新建识别实例，此接口只对“该次调用”的实例生效，不会改变之后 /ocr 请求的字符集。']),
                EndpointSpec('detect', '目标检测', 'POST', '/api/ddddocr/detect',
                             summary='检测图片中的目标位置，返回各目标的边界框与置信度。',
                             params=[
                                 _img_file_param('image', '图片文件(上传)'),
                                 _url_param('image_url', '或 图片URL/base64'),
                             ],
                             notes=[_IMG_NOTE]),
                EndpointSpec('slide_match', '滑块匹配（边缘匹配法）', 'POST', '/api/ddddocr/slide-match',
                             summary='通过边缘检测匹配滑块小图在背景大图中的缺口位置（算法一）。',
                             params=[
                                 _img_file_param('slide_image', '滑块图片(上传)'),
                                 _url_param('slide_image_url', '或 滑块图片URL/base64'),
                                 _img_file_param('bg_image', '背景图片(上传)'),
                                 _url_param('bg_image_url', '或 背景图片URL/base64'),
                                 _bool_sel('simple_target', '简单目标模式', desc='选填：默认 false'),
                             ],
                             notes=['滑块（slide_image / slide_image_url）与背景（bg_image / bg_image_url）各至少提供其一；同时提供时文件优先。',
                                    '成功返回 data={target_x, target_y}，即缺口左上角坐标。']),
                EndpointSpec('slide_comparison', '滑块匹配（差异比较法）', 'POST', '/api/ddddocr/slide-comparison',
                             summary='直接比较滑块图与背景图差异定位缺口（算法二）。',
                             params=[
                                 _img_file_param('slide_image', '滑块图片(上传)'),
                                 _url_param('slide_image_url', '或 滑块图片URL/base64'),
                                 _img_file_param('bg_image', '背景图片(上传)'),
                                 _url_param('bg_image_url', '或 背景图片URL/base64'),
                             ],
                             notes=['滑块（slide_image / slide_image_url）与背景（bg_image / bg_image_url）各至少提供其一；同时提供时文件优先。',
                                    '成功返回 data={target_x, target_y}。']),
            ],
        ),
    ],
)
