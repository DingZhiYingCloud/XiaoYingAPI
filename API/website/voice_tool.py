"""文件上传 - 网页录音工具页（声音上传归属文件上传模块）

页面：
    GET  /upload/record/          在浏览器里录制声音（需官网登录）
    POST /upload/record/upload/   页面内上传录音（需官网登录 + CSRF）

为什么上传不直接调 /api/upload/voice：
    /api/ 由服务策略统一鉴权（默认需项目签名），网页端不能持有 APP_SECRET；
    这里改用官网会话 + CSRF 鉴权，服务端直接调用同一份 save_voice ——
    格式白名单、魔数校验、3-60 秒时长判定与 API 链路完全一致。

浏览器侧只负责录制与试听，最终时长以服务端 ffprobe 读取的音频流为准。
"""
import logging

from django.shortcuts import render
from django.views.decorators.http import require_POST

from API.apis.uploads import voice as voice_utils
from API.apis.uploads.request import absolute_base_url
from API.apis.uploads.utils import FileUploader
from API.common import StatusCode
from API.common.responses import json_response

from .views import login_required

logger = logging.getLogger(__name__)


@login_required
def record_view(request, user):
    """录音页面：时长上下限直接取业务层常量，避免前端写死一份"""
    return render(request, 'voice/record.html', {
        'min_seconds': int(voice_utils.MIN_DURATION),
        'max_seconds': int(voice_utils.MAX_DURATION),
        'max_size_mb': FileUploader.TYPE_CONFIG['audio']['max_size'] // (1024 * 1024),
    })


@require_POST
@login_required
def record_upload_view(request, user):
    """页面内上传：请求体为 multipart，字段名与 API 一致（file）"""
    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        return json_response(StatusCode.PARAM_MISSING,
                             msg='参数缺失: file(录音文件，使用 multipart/form-data)')

    ok, result = voice_utils.save_voice(uploaded_file, absolute_base_url(request))
    if not ok:
        return json_response(StatusCode.PARAM_VALUE_INVALID, msg=f'参数值非法: {result}')

    return json_response(StatusCode.SUCCESS, data=result, msg='上传成功')
