"""文件上传API请求处理视图

提供三个接口，分别用于上传图片、视频和通用文件：
    POST /api/upload/image    上传图片
    POST /api/upload/video    上传视频（最大100MB）
    POST /api/upload/file     上传通用文件（最大100MB）

注意：所有接口均使用 multipart/form-data 格式，文件字段名为 'file'。
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from API.common import StatusCode
from API.apis.uploads.utils import FileUploader


def _json_response(code, data=None, msg=None):
    """构建统一的 JSON 响应体。"""
    return JsonResponse({
        'code': code,
        'msg': msg or StatusCode.get_message(code),
        'data': data,
    })


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
        file: 图片文件 (支持 jpg/jpeg/png/gif/bmp/webp/svg/ico/tiff，最大20MB)

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
        file: 任意文件 (最大100MB，无扩展名限制)

    返回字段同 image_upload_view，type 为 'file'。
    """
    return _handle_upload(request, 'file')
