"""文件上传服务 - 声音上传业务逻辑

流程：
    1. 复用 FileUploader（白名单 + 文件头魔数校验）落盘到 /media/uploads/voices/；
    2. 调 ffprobe 读取「第一个音频流」的真实时长（不是文件大小估算）；
    3. 时长不在 3-60 秒区间 → 删除刚写入的文件并返回原因，不留垃圾；
    4. 合格则返回时长与公网可访问的完整在线链接。

ffprobe 取值顺序：settings.VOICE_FFPROBE_BIN（环境变量 XYAPI_FFPROBE_BIN）
→ ffmpeg 同目录下的 ffprobe → PATH 上的 ffprobe。
"""
import json
import logging
import os
import shutil
import subprocess

from django.conf import settings

from API.apis.uploads.utils import FileUploader

logger = logging.getLogger('api.uploads')

# 时长限制（秒）：需求口径为「最少 3 秒、最多 60 秒」
MIN_DURATION = 3.0
MAX_DURATION = 60.0
# 编码 / 容器的时间戳误差（MP3 帧对齐、WebM 头等）：录满 3 秒可能被读成 2.99，
# 故边界判断留 0.05 秒容差，避免正常录音被误杀。
_DURATION_TOLERANCE = 0.05
_PROBE_TIMEOUT = 20
_TRANSCODE_TIMEOUT = 60

# 这些格式浏览器 / 微信内嵌播放器支持不全（WebM+Opus、OGG、AMR、WMA 在 Safari / 微信里
# 经常直接无声或不能播），统一转成 mp3 再返回链接；mp3 / m4a / wav / aac 原样保留。
_TRANSCODE_EXTS = {'webm', 'ogg', 'flac', 'amr', 'wma'}


def _resolve_bin(value):
    """把配置值解析成真实可执行路径（支持 PATH 上的名字与绝对路径）"""
    value = (value or '').strip()
    if not value:
        return ''
    found = shutil.which(value)
    if found:
        return found
    return value if os.path.isfile(value) else ''


def _ffprobe_bin():
    """按「专用配置 → ffmpeg 同目录 → PATH」顺序找 ffprobe"""
    configured = _resolve_bin(getattr(settings, 'VOICE_FFPROBE_BIN', ''))
    if configured:
        return configured

    ffmpeg = (getattr(settings, 'HONGGUO_FFMPEG_BIN', '') or '').strip()
    if ffmpeg:
        directory = os.path.dirname(ffmpeg)
        if directory:
            name = 'ffprobe.exe' if os.name == 'nt' else 'ffprobe'
            sibling = _resolve_bin(os.path.join(directory, name))
            if sibling:
                return sibling

    return _resolve_bin('ffprobe')


def _to_seconds(value):
    """把 ffprobe 的时长字段转成秒；空值 / N/A / 非正数返回 None"""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    return seconds if seconds > 0 else None


def _packet_duration(binary, path):
    """兜底：用音频包时间戳算时长

    浏览器 MediaRecorder 录的 WebM 通常在写完时来不及回填 Duration / SeekHead，
    ffprobe 对 stream / format 的 duration 都返回 N/A。这类文件本身是完整可播的，
    只是没有总时长字段，因此改为读每个音频包的 pts + duration，取最大值。

    :return: 秒数；读不到返回 None
    """
    cmd = [
        binary, '-v', 'error',
        '-select_streams', 'a:0',
        '-show_entries', 'packet=pts_time,duration_time',
        '-of', 'csv=p=0',
        path,
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=_PROBE_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        logger.exception('ffprobe 读取音频包时间戳失败: %s', path)
        return None
    if proc.returncode != 0:
        return None

    longest = 0.0
    for line in (proc.stdout or '').splitlines():
        parts = line.strip().split(',')
        if not parts or not parts[0]:
            continue
        try:
            start = float(parts[0])
            length = float(parts[1]) if len(parts) > 1 and parts[1] else 0.0
        except ValueError:
            continue
        longest = max(longest, start + length)
    return longest if longest > 0 else None


def probe_audio_duration(path):
    """读取音频真实时长

    :return: (duration, error) —— 成功时 duration 为秒数、error 为空串；
             失败时 duration 为 None、error 为面向调用方的人话原因。
    """
    binary = _ffprobe_bin()
    if not binary:
        logger.error('未找到 ffprobe，无法校验音频时长（请安装 ffmpeg 或配置 XYAPI_FFPROBE_BIN）')
        return None, '服务器缺少音频解析组件 ffprobe，暂时无法校验时长'

    cmd = [
        binary, '-v', 'error',
        '-select_streams', 'a:0',
        # 一次取到音频流时长与容器时长：前者更准，后者兜底（部分 MP3 无流时长）
        '-show_entries', 'stream=codec_name,duration:format=duration',
        '-of', 'json',
        path,
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=_PROBE_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        logger.exception('ffprobe 调用失败: %s', path)
        return None, '音频解析失败，请稍后重试'

    if proc.returncode != 0:
        logger.warning('ffprobe 无法解析文件: %s | %s', path, (proc.stderr or '').strip()[:300])
        return None, '无法解析该音频文件，请确认文件未损坏'

    try:
        info = json.loads(proc.stdout or '{}')
    except ValueError:
        logger.warning('ffprobe 输出无法解析: %s', (proc.stdout or '')[:300])
        return None, '无法解析该音频文件，请确认文件未损坏'

    streams = info.get('streams') or []
    if not streams:
        # 画面有、声音没有（如无声视频改名成 .webm）也走这里
        return None, '文件中没有音频流，请上传有效的声音文件'

    duration = _to_seconds(streams[0].get('duration'))
    if duration is None:
        duration = _to_seconds((info.get('format') or {}).get('duration'))
    if duration is None:
        # 浏览器录制的 WebM 常见：容器没有总时长字段
        duration = _packet_duration(binary, path)
    if duration is None:
        return None, '无法读取音频时长，请确认文件未损坏'
    return duration, ''


def _ffmpeg_bin():
    """ffmpeg 可执行文件：复用项目既有的 HONGGUO_FFMPEG_BIN，留空则取 PATH"""
    return _resolve_bin(getattr(settings, 'HONGGUO_FFMPEG_BIN', '') or 'ffmpeg')


def _transcode_to_mp3(source_path):
    """把浏览器录音容器转成 mp3（统一 128kbps / 44.1kHz，兼顾兼容与体积）

    :return: (target_path, error)；失败时 target_path 为 None
    """
    binary = _ffmpeg_bin()
    if not binary:
        return None, '未找到 ffmpeg'

    target = os.path.splitext(source_path)[0] + '.mp3'
    cmd = [
        binary, '-y', '-v', 'error',
        '-i', source_path,
        '-vn',
        '-acodec', 'libmp3lame', '-b:a', '128k', '-ar', '44100',
        target,
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=_TRANSCODE_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        logger.exception('ffmpeg 转码失败: %s', source_path)
        return None, 'ffmpeg 调用失败'

    if proc.returncode != 0 or not os.path.isfile(target) or os.path.getsize(target) == 0:
        logger.warning('ffmpeg 转码未产出有效文件: %s | %s',
                       source_path, (proc.stderr or '').strip()[:300])
        if os.path.isfile(target):
            _remove_quietly(target)
        return None, '转码失败'
    return target, ''


def _apply_transcoded(result, target_path):
    """转码成功后同步返回体里的文件字段（链接、大小、扩展名都换成 mp3）"""
    size = os.path.getsize(target_path)
    relative = os.path.splitext(result['relative_path'])[0] + '.mp3'
    result.update({
        'filename': os.path.basename(target_path),
        'size': size,
        'size_mb': round(size / (1024 * 1024), 2),
        'ext': 'mp3',
        'relative_path': relative,
        'url': f"{settings.MEDIA_URL}{relative}",
    })


def _remove_quietly(path):
    """删除文件；失败只记日志（不能让清理动作把正常错误响应变成 500）"""
    try:
        os.remove(path)
    except OSError:
        logger.warning('清理不合格音频失败: %s', path, exc_info=True)


def save_voice(uploaded_file, base_url=''):
    """保存并校验声音文件

    :param uploaded_file: Django UploadedFile
    :param base_url: 站点对外基础地址（如 https://example.com），用于拼在线链接；
                     为空时返回 /media/ 相对地址。
    :return: (True, data) 成功； (False, message) 失败（message 为面向调用方的原因）
    """
    ok, result = FileUploader.save_file('audio', uploaded_file)
    if not ok:
        return False, result

    save_path = os.path.join(settings.MEDIA_ROOT, result['relative_path'].replace('/', os.sep))
    duration, error = probe_audio_duration(save_path)
    if error:
        _remove_quietly(save_path)
        return False, error

    duration = round(duration, 2)
    if duration + _DURATION_TOLERANCE < MIN_DURATION:
        _remove_quietly(save_path)
        return False, f'声音时长 {duration:.2f} 秒，少于最短 {MIN_DURATION:g} 秒'
    if duration - _DURATION_TOLERANCE > MAX_DURATION:
        _remove_quietly(save_path)
        return False, f'声音时长 {duration:.2f} 秒，超过最长 {MAX_DURATION:g} 秒'

    result['duration'] = duration

    # 浏览器录音容器（WebM/OGG 等）在微信、Safari 里经常无声或不可播，
    # 统一转成 mp3；转码失败时保留原文件并降级返回原链接，不让整次上传失败。
    if result['ext'] in _TRANSCODE_EXTS:
        target_path, transcode_error = _transcode_to_mp3(save_path)
        if target_path:
            _remove_quietly(save_path)
            _apply_transcoded(result, target_path)
        else:
            logger.warning('声音转 mp3 失败，保留原文件: %s（%s）', save_path, transcode_error)

    if base_url:
        result['url'] = f"{base_url.rstrip('/')}{result['url']}"
    return True, result
