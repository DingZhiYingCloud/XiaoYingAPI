"""文件上传 API 请求处理视图

提供四个接口，统一归在「文件上传」服务下：
    POST /api/upload/image    上传图片
    POST /api/upload/video    上传视频（最大100MB）
    POST /api/upload/file     上传通用文件（最大100MB）
    POST /api/upload/voice    上传声音（3-60 秒，返回在线播放链接）

注意：所有接口均使用 multipart/form-data 格式，文件字段名为 'file'。
"""
from django.conf import settings
from django.views.decorators.http import require_http_methods

from API.common import StatusCode
from API.common.responses import json_response as _json_response

from . import voice
from .utils import FileUploader


def absolute_base_url(request):
    """站点对外基础地址：优先显式配置的 SITE_URL，否则按当前请求推导

    声音的上传接口与网页录音工具页（/upload/record/）的服务端上传都复用它，
    保证两条链路的在线链接口径完全一致。
    """
    site_url = (getattr(settings, 'SITE_URL', '') or '').strip().rstrip('/')
    if site_url:
        return site_url
    return request.build_absolute_uri('/').rstrip('/')


def _handle_upload(request, upload_type):
    """通用文件上传处理函数。

    :param request: Django 请求对象
    :param upload_type: 上传类型 ('image'/'video'/'file')
    :return: JsonResponse
    """
    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        return _json_response(
            StatusCode.PARAM_MISSING,
            msg='参数缺失: file(上传文件，使用 multipart/form-data)',
        )

    success, result = FileUploader.save_file(upload_type, uploaded_file)
    if not success:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg=result)

    return _json_response(StatusCode.SUCCESS, data=result)


@require_http_methods(['POST'])
def image_upload_view(request):
    """上传图片接口

    请求方式: POST (multipart/form-data)
    表单字段:
        file: 图片文件 (支持 jpg/jpeg/png/gif/bmp/webp/ico/tiff，最大20MB；
              svg 因可内嵌脚本已移除，S-02 整改)

    返回示例 (成功):
        {
            "code": 10000,
            "msg": "成功",
            "data": {
                "filename": "a1b2c3d4_20260627120000.jpg",
                "original_name": "photo.jpg",
                "size": 123456,
                "size_mb": 0.12,
                "ext": "jpg",
                "type": "image",
                "relative_path": "uploads/images/a1b2c3d4_20260627120000.jpg",
                "url": "/media/uploads/images/a1b2c3d4_20260627120000.jpg"
            }
        }
    """
    return _handle_upload(request, 'image')


@require_http_methods(['POST'])
def video_upload_view(request):
    """上传视频接口

    请求方式: POST (multipart/form-data)
    表单字段:
        file: 视频文件 (最大100MB)

    返回字段同 image_upload_view，type 为 'video'。
    """
    return _handle_upload(request, 'video')


@require_http_methods(['POST'])
def file_upload_view(request):
    """上传通用文件接口

    请求方式: POST (multipart/form-data)
    表单字段:
        file: 通用文件 (支持 zip/pdf/docx/xlsx/txt，最大100MB；
              白名单制并校验文件头，S-02 整改)

    返回字段同 image_upload_view，type 为 'file'。
    """
    return _handle_upload(request, 'file')


@require_http_methods(['POST'])
def voice_upload_view(request):
    """上传声音接口（3-60 秒）

    请求方式: POST (multipart/form-data)
    表单字段:
        file: 音频文件（mp3/wav/m4a/aac/ogg/flac/webm/amr/wma，最大 20MB）

    时长限制: 3-60 秒（服务端用 ffprobe 读取真实音频流时长，不靠文件大小估算）；
    WebM / OGG / FLAC / AMR / WMA 会转成 mp3 后再返回，保证微信 / Safari 能直接播放。

    返回示例 (成功):
        {
            "code": 10000,
            "msg": "上传成功",
            "data": {
                "filename": "a1b2c3d4_20260627120000.m4a",
                "original_name": "my_voice.m4a",
                "size": 204800,
                "size_mb": 0.2,
                "ext": "m4a",
                "type": "audio",
                "duration": 12.35,
                "relative_path": "uploads/voices/a1b2c3d4_20260627120000.m4a",
                "url": "https://example.com/media/uploads/voices/a1b2c3d4_20260627120000.m4a"
            }
        }
    """
    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        return _json_response(
            StatusCode.PARAM_MISSING,
            msg='参数缺失: file(声音文件，使用 multipart/form-data)',
        )

    ok, result = voice.save_voice(uploaded_file, absolute_base_url(request))
    if not ok:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg=f'参数值非法: {result}')

    return _json_response(StatusCode.SUCCESS, data=result, msg='上传成功')
