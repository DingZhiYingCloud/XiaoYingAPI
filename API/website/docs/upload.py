"""文件上传服务 - 接口文档与在线调试数据

数据与 API/apis/uploads/ 实际实现对齐（服务策略 /api/upload/ 默认需签名）：
- 本地上传：图片 / 视频 / 通用文件三类，白名单 + 校验文件头，落盘 /media/uploads/...。
后续新增存储后端（OSS 等）时在 channels 追加即可。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ResponseFieldSpec, ServiceSpec

# 页面在线调试现支持真实文件上传（multipart，字段名 file）
_FILE_HINT = 'multipart/form-data 文件字段 file：直接用下方“选择文件”上传即可。'


def _file_param(label, accept=''):
    return ParamSpec('file', label, kind='file', required=True, accept=accept,
                     desc=_FILE_HINT)


# 三类上传端点返回同一套字段（仅 type 取值不同），共用一份字段表
_RESP_FIELDS = [
    ResponseFieldSpec('filename', 'string', '存储后的文件名'),
    ResponseFieldSpec('original_name', 'string', '原始文件名'),
    ResponseFieldSpec('size', 'int', '文件大小（字节）'),
    ResponseFieldSpec('size_mb', 'float', '文件大小（MB，2 位小数）'),
    ResponseFieldSpec('ext', 'string', '扩展名'),
    ResponseFieldSpec('type', 'string', '类型：image/video/file'),
    ResponseFieldSpec('relative_path', 'string', '相对 media 的路径'),
    ResponseFieldSpec('url', 'string', '可访问地址（/media/...）'),
]


SERVICE = ServiceSpec(
    slug='upload',
    name='文件上传',
    prefix='/api/upload/',
    summary='通用文件上传能力：图片/视频/普通文件，白名单校验并存储到本地 /media，返回可访问 URL。',
    keywords='文件上传API,图片上传接口',
    intro=[
        '文件上传服务提供图片、视频与通用文件三类上传入口，文件落盘到站点 /media 目录并返回可直接引用的 URL，'
        '适合作为业务系统的统一附件通道。',
        '全部接口使用 multipart/form-data，文件字段名固定为 file。服务端按白名单校验扩展名并校验文件头'
        '（magic bytes），可内联渲染或执行的文件类型（如 svg、html、脚本）一律拒绝，'
        '避免上传文件被当作存储型 XSS 利用。',
        '体积限制：图片最大 20MB，视频与通用文件最大 100MB。本服务需项目签名。',
    ],
    channels=[
        ChannelSpec(
            slug='local',
            name='本地文件上传',
            provider='本地存储（/media/uploads/…）',
            auth_note='auth',
            note='全部使用 multipart/form-data，文件字段固定为 file；仅支持白名单类型并校验文件头（防伪装/防脚本上传）。',
            endpoints=[
                EndpointSpec('image', '上传图片', 'POST', '/api/upload/image',
                             summary='上传图片，返回可直接引用的图片 URL。',
                             params=[_file_param('图片文件', accept='image/*')],
                             notes=['支持类型：jpg/jpeg/png/gif/bmp/webp/ico/tiff；最大 20MB。',
                                    'svg 因可内嵌脚本已禁用。'],
                             response_fields=_RESP_FIELDS,
                             response_example='{"filename": "a1b2c3d4_20260627120000.jpg", "original_name": "photo.jpg", "size": 123456, "size_mb": 0.12, "ext": "jpg", "type": "image", "relative_path": "uploads/images/a1b2c3d4_20260627120000.jpg", "url": "/media/uploads/images/a1b2c3d4_20260627120000.jpg"}'),
                EndpointSpec('video', '上传视频', 'POST', '/api/upload/video',
                             summary='上传视频文件。',
                             params=[_file_param('视频文件', accept='video/*')],
                             notes=['最大 100MB；返回 type=video。'],
                             response_fields=_RESP_FIELDS,
                             response_example='{"filename": "a1b2c3d4_20260627120000.mp4", "original_name": "clip.mp4", "size": 5242880, "size_mb": 5.0, "ext": "mp4", "type": "video", "relative_path": "uploads/videos/a1b2c3d4_20260627120000.mp4", "url": "/media/uploads/videos/a1b2c3d4_20260627120000.mp4"}'),
                EndpointSpec('file', '上传通用文件', 'POST', '/api/upload/file',
                             summary='上传通用文件（白名单：zip/pdf/docx/xlsx/txt 等）。',
                             params=[_file_param('通用文件')],
                             notes=['最大 100MB；白名单制并校验文件头；返回 type=file。'],
                             response_fields=_RESP_FIELDS,
                             response_example='{"filename": "a1b2c3d4_20260627120000.pdf", "original_name": "report.pdf", "size": 204800, "size_mb": 0.2, "ext": "pdf", "type": "file", "relative_path": "uploads/files/a1b2c3d4_20260627120000.pdf", "url": "/media/uploads/files/a1b2c3d4_20260627120000.pdf"}'),
            ],
        ),
    ],
)
