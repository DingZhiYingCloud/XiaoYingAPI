"""文件上传服务 - 接口文档与在线调试数据

数据与 API/apis/uploads/ 实际实现对齐（分类树 /api/upload/ 为需签名）：
- 本地上传：图片 / 视频 / 通用文件三类，白名单 + 校验文件头，落盘 /media/uploads/...。
后续新增存储后端（OSS 等）时在 channels 追加即可。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ServiceSpec

# 页面在线调试现支持真实文件上传（multipart，字段名 file）
_FILE_HINT = 'multipart/form-data 文件字段 file：直接用下方“选择文件”上传即可。'


def _file_param(label, accept=''):
    return ParamSpec('file', label, kind='file', required=True, accept=accept,
                     desc=_FILE_HINT)


_RESP_NOTES = ['成功返回 data 字段：filename / original_name / size / size_mb / ext / type / relative_path / url。',
               '返回的 url 为站点媒体访问地址（/media/...），可直接引用。']


SERVICE = ServiceSpec(
    slug='upload',
    name='文件上传',
    prefix='/api/upload/',
    summary='通用文件上传能力：图片/视频/普通文件，白名单校验并存储到本地 /media，返回可访问 URL。',
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
                                    'svg 因可内嵌脚本已禁用。'] + _RESP_NOTES),
                EndpointSpec('video', '上传视频', 'POST', '/api/upload/video',
                             summary='上传视频文件。',
                             params=[_file_param('视频文件', accept='video/*')],
                             notes=['最大 100MB；返回 type=video。'] + _RESP_NOTES),
                EndpointSpec('file', '上传通用文件', 'POST', '/api/upload/file',
                             summary='上传通用文件（白名单：zip/pdf/docx/xlsx/txt 等）。',
                             params=[_file_param('通用文件')],
                             notes=['最大 100MB；白名单制并校验文件头；返回 type=file。'] + _RESP_NOTES),
            ],
        ),
    ],
)
