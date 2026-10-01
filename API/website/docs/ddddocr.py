"""验证码识别服务 - 接口文档与在线调试数据

数据与 API/apis/ 下实际实现对齐（服务策略默认需签名）：
- ddddocr：本地 Python ddddocr 模型，OCR 识别 / 目标检测 / 滑块缺口匹配（/api/ddddocr/）；
- 超级鹰：第三方打码平台，通用图片识别 / 报错返分 / 查询题分（/api/chaojiying/）。

两者是同一业务域（验证码识别）的两条线路，故合并在本服务文档下作为两个「线路」Tab 展示；
新增识别引擎时在 channels 追加即可。
"""
from SpiderServices.Chaojiying.utils import CODETYPES

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


# ==================== 超级鹰：题分 → 人民币 ====================

# 官方标准价：1 元 = 1000 题分（充值有赠送，实际单价低于此）
TIFEN_PER_YUAN = 1000

# 复合计费类型：单价随用量 / 题型变化，无法用单一数字表示，人民币说明单独给出
_COMPOSITE_YUAN = {
    '5000': '每英文 0.0025 元、每汉字 0.01 元（基础 0.01 元）',
    '5201': '首字母 0.02 元 / 计算 0.02 元 / 成语 0.04 元',
    '6900': '每英文 0.0025 元、每汉字 0.01 元（基础 0.01 元）',
    '9801': '每定位 0.009 元（最低 0.028 元）',
    '9800': '每定位 0.006 元（最低 0.028 元）',
    '9900': '每定位 0.008 元 + 基础 0.008 元',
}


def _to_yuan(tifen):
    """题分单价 → 人民币文案（1 元 = 1000 题分）

    题分串以 '/' 并列多个价位（如 '10/12/15'，对应不同位数）时用区间表示；
    含中文说明的复合写法返回空串（其人民币说明见 _COMPOSITE_YUAN）。
    """
    parts = [p.strip() for p in tifen.split('/')]
    if not all(p.replace('.', '', 1).isdigit() for p in parts):
        return ''
    values = [float(p) / TIFEN_PER_YUAN for p in parts]
    low, high = min(values), max(values)
    return f'{low:g} 元' if low == high else f'{low:g}~{high:g} 元'


def _yuan_of(code, tifen):
    """某识别类型的人民币说明"""
    return _COMPOSITE_YUAN.get(code) or _to_yuan(tifen)


def _build_price_table():
    """按官方价格表生成 Markdown 价格表（类型 / 说明 / 题分 / 折合人民币）

    数据源是爬虫层的 CODETYPES（唯一出处），官方调价时只改那一处。
    """
    rows = ['| 识别类型 | 说明 | 题分 | 折合人民币（约） |',
            '| --- | --- | --- | --- |']
    for code, (desc, tifen) in CODETYPES.items():
        rows.append(f'| `{code}` | {desc} | {tifen} | {_yuan_of(code, tifen)} |')
    return '\n'.join(rows)


def _short_tifen(tifen):
    """题分单价的短式（供下拉选项用）

    下拉标签必须短：原生 `<select>` 的弹层宽度由**最长选项**决定，标签过长会在窄屏上
    溢出屏幕。故这里只给一个紧凑的题分范围，完整的题分与折合人民币见
    「服务说明」里的价格表（由 _build_price_table 生成）。
    """
    parts = [p.strip() for p in tifen.split('/')]
    if not all(p.replace('.', '', 1).isdigit() for p in parts):
        return '按量计费'
    values = [float(p) for p in parts]
    low, high = min(values), max(values)
    return f'{low:g} 题分' if low == high else f'{low:g}~{high:g} 题分'


# 识别类型下拉：值即 codetype；标签保持简短（详见 _short_tifen）
CODETYPE_OPTIONS = [
    {'value': code, 'label': f'{code} · {desc}（{_short_tifen(tifen)}）'}
    for code, (desc, tifen) in CODETYPES.items()
]


def _codetype_param():
    return ParamSpec('codetype', '识别类型(codetype)', kind='select', required=True,
                     options=CODETYPE_OPTIONS,
                     desc='必填：按图片内容精确匹配类型（如 1902 = 4~6 位英文数字），'
                          '可提高识别速度与正确率。各类型的题分与折合人民币见本页「服务说明」的价格表。')


SERVICE = ServiceSpec(
    slug='ddddocr',
    name='验证码识别',
    prefix='/api/ddddocr/',
    summary='多引擎验证码识别：ddddocr 本地模型（OCR 文字识别 / 目标检测 / 滑块缺口匹配）'
            '与超级鹰打码平台（通用图片识别 / 报错返分 / 查询题分）。',
    keywords='验证码识别API,ddddocr,超级鹰,OCR识别接口,滑块验证码识别,打码平台,题分价格',
    intro=[
        '验证码识别服务按「线路」聚合多种识别引擎：当前接入 **ddddocr**（本地模型）与 **超级鹰**（第三方打码平台），'
        '在上方线路 Tab 之间切换即可查看各自的接口与调试面板。',
        '**ddddocr 线路**（`/api/ddddocr/`）：纯本地模型，无需第三方账号、无额外费用。'
        '识别图片中的文字、检测图片内的目标位置，以及匹配滑块验证码的缺口位置（两种算法）。'
        '识别实例的字符范围可配置（预定义编号或自定义字符集），识别特定站点的验证码前先设置字符集通常能明显提升准确率。',
        '**超级鹰线路**（`/api/chaojiying/`）：第三方人工 + 智能打码平台，通用图片识别，账号由本站统一配置、'
        '调用方无需自备。按题分计费，**上传即扣费**（无论最终识别对错）；官方标准价 **1 元 = 1000 题分**'
        '（充值有赠送，实际单价低于此）。调用前请用 `codetype` 精确匹配图片内容 —— 类型选得越准，识别越快越准，'
        '花费也越低。各识别类型的官方单价与折合人民币如下：',
        _build_price_table(),
        '**超级鹰结果校验**：平台会随识别结果返回 `md5`，本站按官方算法 '
        '`md5("软件ID,软件KEY,图片ID,图片结果")` 逐条核验，校验不通过会以 4xxxx 拒绝返回，避免结果被中途篡改。',
        '**超级鹰报错返分**：识别结果确实错误时，可凭识别接口返回的 `pic_id` 调「报错返分」退回题分。'
        '官方限制：须在拿到 pic_id 后 **3 分钟内**、部分类型不支持；'
        '**仅允许在确认结果错误时调用**，对正确结果报错会被评估信用。',
        '本服务需项目签名。识别准确率受图片质量与干扰强度影响，建议对失败结果做重试或人工兜底。',
    ],
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
        ChannelSpec(
            slug='chaojiying',
            name='超级鹰打码平台',
            provider='超级鹰（chaojiying.com）',
            auth_note='auth',
            note='第三方打码平台，按题分计费（上传即扣费）；账号由本站统一配置，调用方无需自备。'
                 '各识别类型的题分单价与折合人民币见本页「服务说明」。',
            endpoints=[
                EndpointSpec('ocr', '图片识别', 'POST', '/api/chaojiying/ocr',
                             summary='上传验证码图片，返回识别结果与图片标识号（成功即扣题分）。',
                             params=[
                                 ParamSpec('file', '图片文件(上传)', kind='file', required=False,
                                           accept='image/*',
                                           desc='上传本地图片（不超过 2MB，推荐 bmp / jpg / png）'),
                                 ParamSpec('image', '或 图片 base64 / 图片地址', kind='textarea',
                                           required=False,
                                           placeholder='data:image/png;base64,iVBORw0... 或 https://.../captcha.jpg',
                                           desc='或填图片 base64 字符串、http(s) 图片地址（与 file 二选一，file 优先）'),
                                 _codetype_param(),
                                 ParamSpec('str_debug', '附加信息(str_debug)', kind='text', required=False,
                                           desc='选填：定位类类型（如 9801）的附加指令，普通类型留空'),
                             ],
                             notes=['图片来源三选一：上传 file 文件、填 image(base64)、填 image(http 图片地址)；'
                                    '图片不超过 2MB，推荐 bmp / jpg / png，分辨率比例要正常。',
                                    '成功返回 data = {pic_id(图片标识号，报错返分时用), pic_str(识别结果), md5(校验值)}；'
                                    '平台业务错误（如账号密码错误、题分不足）返回 4xxxx，msg 为平台中文说明。',
                                    '识别结果的大小写以平台为准（英文数字类通常返回**小写**），比对时请自行做大小写归一。',
                                    '各类型的题分单价与折合人民币见本页「服务说明」中的价格表。']),
                EndpointSpec('report_error', '报错返分', 'POST', '/api/chaojiying/report-error',
                             summary='识别结果确实错误时退回题分（须在拿到 pic_id 后 3 分钟内调用）。',
                             params=[
                                 ParamSpec('pic_id', '图片标识号', kind='text', required=True,
                                           placeholder='9160109360600112681',
                                           desc='必填：识别接口返回的 pic_id'),
                             ],
                             notes=['平台限制：**仅限识别结果确实错误时调用**，对正确结果报错会被评估信用；'
                                    '部分识别类型不支持返分；超过 3 分钟失效。']),
                EndpointSpec('score', '查询题分余额', 'GET', '/api/chaojiying/score',
                             summary='查询本站平台账号的题分余额（用于确认可用额度）。',
                             params=[],
                             notes=['成功返回 data = {tifen(题分), tifen_lock(锁定题分)}；'
                                    '按官方标准价换算，1000 题分 ≈ 1 元。']),
            ],
        ),
    ],
)
