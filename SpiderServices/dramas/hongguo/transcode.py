"""红果短剧「网页直出」产物：服务端解密 + H.264 转码（第 4 集及以后）

为什么必须转码
    源站第 4 集及以后只下发 DRM 加密的 H.265。浏览器在多数机器上完全解不了 HEVC
    —— 实测 Chrome：`canPlayType('hvc1')` 为空、`MediaSource.isTypeSupported('hvc1')`
    为 false、`VideoDecoder.isConfigSupported('hvc1')` 也为 false（原生 / MSE / WebCodecs
    三条路全断）。所以「网页能播」只能是 H.264，必须转码。

链路（每集只做一次，产物永久复用，不需要全量预处理）
    App 接口取流（需 unidbg 签名）→ CENC 密文 → ffmpeg 解密 + 缩放 + H.264 编码
      → +faststart 原子落盘 → 由 API 的 stream 端点按 HTTP Range 出流

并发
    同一集可能被多个请求同时触发：用「进程内锁 + 锁文件」保证只转一次，
    后来者直接拿到「准备中」状态去轮询，不会重复消耗算力。
"""
import logging
import os
import subprocess
import threading
import time

from django.conf import settings

from . import app_api
from .offline import spade_to_key

logger = logging.getLogger('api.request')

_FFMPEG = getattr(settings, 'HONGGUO_FFMPEG_BIN', 'ffmpeg')
_STREAM_DIR = getattr(settings, 'HONGGUO_STREAM_DIR', '')
_HW_ENCODERS = list(getattr(settings, 'HONGGUO_STREAM_HW_ENCODERS', []))
_X264_PRESET = getattr(settings, 'HONGGUO_STREAM_X264_PRESET', 'veryfast')
_X264_CRF = int(getattr(settings, 'HONGGUO_STREAM_X264_CRF', 20))
# 转码单集的最长耗时（秒）：超过即判失败，避免僵尸进程
_TRANSCODE_TIMEOUT = int(getattr(settings, 'HONGGUO_STREAM_TIMEOUT', 900))
# 锁文件超过该秒数视为陈旧锁（进程被杀留下的），自动接管
_STALE_LOCK_SECONDS = 1800

# ============ 画质档位 ============
# key = 输出**宽度**上限（短剧是竖屏 1080×1920，日常说的「1080p / 720p」就指宽度），
# value = 该档的码率上限（kbps）。档位与源站轨道一一对应（源站提供 1080/720/540/480/360）。
#
# 为什么给到 3000k：源站 1080p 本身只有 ~540 kbps，重编码定 CRF/码率的意义不是「加细节」
# （加不出来），而是**别在二次编码时再掉一层画质**，所以给足上限、由编码器按需取用。
# 要统一调高/调低，改这张表即可（每档上限就是这个档位的画质旋钮）。
_RATE_BY_WIDTH = {
    1080: 3000,
    720: 1800,
    540: 1200,
    480: 900,
    360: 600,
}
# 未登记宽度的兜底上限（正常走不到：宽度来自 API 层的白名单）
_RATE_FALLBACK = 3000

# 转码任务状态：key = "series_id:ep:宽度" -> {state, started, error}
# state: running（转码中）/ failed（失败）；就绪与否以产物文件是否存在为准
_JOBS = {}
_JOBS_LOCK = threading.Lock()
_LOCAL_LOCKS = {}
_LOCAL_LOCKS_LOCK = threading.Lock()


def stream_path(series_id, ep, width):
    """该集某画质档的产物流盘路径（一集一档一份，各档互不影响）"""
    return os.path.join(_STREAM_DIR, str(series_id), str(int(width)), f'{int(ep):03d}.mp4')


def is_ready(series_id, ep, width):
    """该画质的产物是否已就绪（存在且非空）"""
    path = stream_path(series_id, ep, width)
    return os.path.exists(path) and os.path.getsize(path) > 0


def job_status(series_id, ep, width):
    """该集该画质的转码状态：ready / running / failed / pending"""
    if is_ready(series_id, ep, width):
        return {'state': 'ready'}
    with _JOBS_LOCK:
        job = dict(_JOBS.get(f'{series_id}:{int(ep)}:{int(width)}') or {})
    if not job:
        return {'state': 'pending'}
    state = job.get('state') or 'running'
    payload = {'state': state}
    if state == 'running':
        payload['elapsed'] = int(time.time() - (job.get('started') or time.time()))
    if state == 'failed':
        payload['error'] = job.get('error') or '转码失败'
    return payload


def _local_lock(key):
    with _LOCAL_LOCKS_LOCK:
        return _LOCAL_LOCKS.setdefault(key, threading.Lock())


def _acquire_lock_file(path):
    """抢占锁文件；返回 True 表示抢到（陈旧锁会被接管）"""
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        try:
            if time.time() - os.path.getmtime(path) > _STALE_LOCK_SECONDS:
                os.remove(path)
                return _acquire_lock_file(path)
        except OSError:
            pass
        return False


def ensure(series_id, ep, width):
    """确保该集该画质有可播产物。

    :return: True = 已就绪可直接出流；False = 正在转码 / 已失败（看 job_status）
    """
    if is_ready(series_id, ep, width):
        return True
    key = f'{series_id}:{int(ep)}:{int(width)}'
    with _local_lock(key):
        with _JOBS_LOCK:
            job = _JOBS.get(key)
            if job and job.get('state') == 'running':
                return False
        path = stream_path(series_id, ep, width)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not _acquire_lock_file(path + '.lock'):
            # 别的进程在转：标记为 running，避免本进程重复启动
            with _JOBS_LOCK:
                _JOBS.setdefault(key, {'state': 'running', 'started': time.time()})
            return False
        _start(series_id, ep, width, key)
        return False


def _start(series_id, ep, width, key):
    """启动后台转码线程"""
    record = {'state': 'running', 'started': time.time(), 'error': None}
    with _JOBS_LOCK:
        _JOBS[key] = record

    def worker():
        try:
            _transcode(series_id, ep, width)
            with _JOBS_LOCK:
                _JOBS.pop(key, None)          # 就绪状态由产物文件表达
        except Exception as exc:  # noqa: BLE001 - 失败要落到状态里给前端看
            with _JOBS_LOCK:
                _JOBS[key] = {'state': 'failed', 'started': record['started'],
                              'error': str(exc)[:300]}

    threading.Thread(target=worker, name=f'hongguo-transcode-{key}',
                     daemon=True).start()


def _pick_track(tracks):
    """挑最高清晰度轨道（解密+转码与源编码无关，不需要按可解性过滤）"""
    def height(t):
        return int((t.get('video_meta') or {}).get('vheight') or 0)
    return max(tracks, key=height)


def _encoder_candidates(width):
    """该画质档的编码器候选（硬件优先，libx264 兜底）

    硬件编码器走码率模式（目标 = 上限的 75%）；libx264 走 CRF（让它按画面复杂度取码率，
    只是拿上限兜住峰值）。上限低到一定程度时该糊还是会糊 —— 那就是这一档的取舍。
    """
    cap = _RATE_BY_WIDTH.get(int(width), _RATE_FALLBACK)
    target = int(cap * 0.75)
    hw_opts = {
        'h264_nvenc': ['-preset', 'p4', '-rc', 'vbr',
                       '-b:v', f'{target}k', '-maxrate', f'{cap}k', '-bufsize', f'{cap}k'],
        'h264_qsv': ['-preset', 'veryfast',
                     '-b:v', f'{target}k', '-maxrate', f'{cap}k', '-bufsize', f'{cap}k'],
        'h264_amf': ['-quality', 'speed', '-rc', 'cbr',
                     '-b:v', f'{target}k', '-maxrate', f'{cap}k', '-bufsize', f'{cap}k'],
    }
    cands = [(enc, hw_opts[enc]) for enc in _HW_ENCODERS if enc in hw_opts]
    cands.append(('libx264', ['-preset', _X264_PRESET, '-crf', str(_X264_CRF),
                              '-maxrate', f'{cap}k', '-bufsize', f'{cap}k']))
    return cands


def _run_ffmpeg(enc, opts, key, source, out_path, width, user_agent=None):
    """跑一次「解密 + 转码」；source 可为远端 URL 或本地密文文件"""
    cmd = [_FFMPEG, '-y', '-loglevel', 'error']
    if source.startswith(('http://', 'https://')) and user_agent:
        cmd += ['-user_agent', user_agent]
    cmd += ['-decryption_key', key,
            '-i', source,
            # 按**宽度**封顶（短剧是竖屏，宽度才是观感瓶颈）；源更小则不放大
            '-vf', f'scale=min({int(width)}\\,iw):-2',
            '-c:v', enc, *opts,
            '-c:a', 'aac', '-b:a', '96k',
            '-movflags', '+faststart',
            '-f', 'mp4', out_path]
    proc = subprocess.run(cmd, capture_output=True, timeout=_TRANSCODE_TIMEOUT)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode('utf-8', 'replace')[:300])


def _verify_decoded(path):
    """输出能干净解出至少一帧才算成功（防止产出坏文件被永久缓存）"""
    proc = subprocess.run([_FFMPEG, '-v', 'error', '-i', path, '-frames:v', '1',
                           '-f', 'null', '-'], capture_output=True, timeout=180)
    return proc.returncode == 0 and not proc.stderr.strip()


def _transcode(series_id, ep, width):
    """同步执行：取流 → 解密 + 转码 → 原子落盘（供后台线程调用）"""
    series_id, ep, width = str(series_id), int(ep), int(width)
    out_path = stream_path(series_id, ep, width)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp_path = out_path + '.tmp.mp4'

    vids = app_api.get_episode_vids(series_id)
    vid = vids.get(ep)
    if not vid:
        raise RuntimeError(f'App 接口未返回第 {ep} 集')
    tracks = app_api.get_video_tracks([vid]).get(vid) or []
    if not tracks:
        raise RuntimeError(f'App 接口未返回第 {ep} 集的视频轨道')
    track = _pick_track(tracks)
    encrypt = track.get('encrypt_info') or {}
    key = spade_to_key(encrypt.get('spade_a') or '')
    if not key:
        raise RuntimeError(f'第 {ep} 集 spade_a 解包失败（可能为新包装版本）')

    from .utils import APP_HEADERS
    ua = APP_HEADERS.get('user-agent')
    sources = [u for u in (track.get('main_url'), track.get('backup_url')) if u]
    if not sources:
        raise RuntimeError(f'第 {ep} 集未返回可用地址')

    started = time.time()
    errors = []
    try:
        for enc, opts in _encoder_candidates(width):
            for source in sources:
                attempt = time.time()
                try:
                    _run_ffmpeg(enc, opts, key, source, tmp_path, width, ua)
                except Exception as exc:  # noqa: BLE001 - 换编码器 / 换线路继续试
                    errors.append(f'{enc}: {exc}')
                    logger.warning(f'hongguo transcode {series_id}#{ep}@{width} 编码器 {enc} 失败: {exc}')
                    continue
                if not _verify_decoded(tmp_path):
                    errors.append(f'{enc}: 转码结果校验未通过')
                    continue
                os.replace(tmp_path, out_path)   # 原子落盘，避免读到半成品
                logger.info(f'hongguo transcode {series_id}#{ep}@{width} 完成 '
                            f'encoder={enc} 耗时={time.time() - started:.1f}s '
                            f'单片={time.time() - attempt:.1f}s '
                            f'体积={os.path.getsize(out_path) / 1e6:.1f}MB')
                return
        raise RuntimeError('；'.join(errors[-3:]) or '转码失败')
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        lock = out_path + '.lock'
        if os.path.exists(lock):
            os.remove(lock)
