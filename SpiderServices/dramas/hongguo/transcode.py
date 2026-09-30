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
    同一集可能被多个请求同时触发：用「进程内锁 + 锁文件」保证只转一次，后来者直接拿到
    「准备中」状态去轮询，不会重复消耗算力。**锁文件同时是「是否正在转」的唯一真相**
    （内容是属主 pid，mtime 是开工时间）：多 worker 各读同一份文件，状态天然一致；
    属主进程已死（部署重启留下的僵尸锁）会被下一次点播立刻接管，不会把某集永久卡住。
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

# 转码失败记录：key = "series_id:ep:宽度" -> {state, error}
#
# 「是否正在转」**不放在内存里**，而是以锁文件为唯一真相（见 _lock_state）。原因（线上事故）：
#   · uwsgi 多 worker（尤其 lazy-apps）下每个进程各有一份内存字典，状态会分裂：
#     真正在转的 worker 说 running、别的 worker 说 pending；
#   · 进程被 kill（部署重启 uwsgi）时内存态直接蒸发，锁文件却还留着 ——
#     于是谁也不敢接管，界面永远停在「正在生成播放地址，请稍候重试」。
# 内存里只保留「失败原因」：失败不必跨进程共享（语义见 job_status 注释）。
_JOBS = {}
_JOBS_LOCK = threading.Lock()
_LOCAL_LOCKS = {}
_LOCAL_LOCKS_LOCK = threading.Lock()


def stream_path(series_id, ep, width):
    """该集某画质档的产物流盘路径（一集一档一份，各档互不影响）"""
    return os.path.join(_STREAM_DIR, str(series_id), str(int(width)), f'{int(ep):03d}.mp4')


def _lock_path(series_id, ep, width):
    """锁文件路径：与产物同目录同名，加 .lock 后缀"""
    return stream_path(series_id, ep, width) + '.lock'


def _job_key(series_id, ep, width):
    return f'{series_id}:{int(ep)}:{int(width)}'


def is_ready(series_id, ep, width):
    """该画质的产物是否已就绪（存在且非空）"""
    path = stream_path(series_id, ep, width)
    return os.path.exists(path) and os.path.getsize(path) > 0


def _pid_alive(pid):
    """该 pid 是否仍存活（判不出来时按存活处理：宁可多等，也不并发重复转码）

    注意 Windows 上不能用 `os.kill(pid, 0)` 探活 —— CPython 在那里会用
    TerminateProcess 真的把进程杀掉（官方文档明确说明），只能走 OpenProcess 查询。
    """
    if not pid or pid <= 0:
        return False
    if os.name == 'nt':
        import ctypes

        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(process_query_limited_information, False, int(pid))
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return code.value == still_active
            return True
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _lock_state(path):
    """解读锁文件：None=没锁；'stale'=僵尸锁；{'elapsed': 秒}=确实有人在转

    锁文件里写的是属主 pid（见 _acquire_lock_file），文件 mtime 即开工时间，
    所以 elapsed 可以直接从文件推算 —— 不依赖任何进程的内存状态，多 worker 天然一致。
    两种情形都算僵尸锁：属主进程已死（部署重启留下的），或已超过 _STALE_LOCK_SECONDS
    （兜底 pid 被复用、以及单次转码意外超长的情况）。
    """
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    age = time.time() - mtime
    if age > _STALE_LOCK_SECONDS:
        return 'stale'
    try:
        with open(path, encoding='ascii', errors='replace') as fh:
            pid = int((fh.read().strip() or '0').split()[0])
    except (OSError, ValueError, IndexError):
        return {'elapsed': int(age)}        # 内容坏了：按有人在转处理，交给超时兜底
    if pid and not _pid_alive(pid):
        return 'stale'
    return {'elapsed': int(age)}


def job_status(series_id, ep, width):
    """该集该画质的转码状态：ready / running / failed / pending

    running / pending 由**锁文件**判定，因此各 worker 看到的一致；failed 来自本进程内存
    —— 其余 worker 此时看到 pending 会各自重试一次：偶发失败下这正是想要的，
    而对「必失败」的集也只是多试几次，不影响正确性。
    """
    if is_ready(series_id, ep, width):
        return {'state': 'ready'}
    lock_state = _lock_state(_lock_path(series_id, ep, width))
    if lock_state == 'stale':
        # 僵尸锁按「等待中」上报（不能报 running 骗前端）；清锁与接管由 ensure() 执行
        return {'state': 'pending'}
    if lock_state:
        return {'state': 'running', 'elapsed': lock_state['elapsed']}
    with _JOBS_LOCK:
        job = dict(_JOBS.get(_job_key(series_id, ep, width)) or {})
    if job.get('state') == 'failed':
        return {'state': 'failed', 'error': job.get('error') or '转码失败'}
    return {'state': 'pending'}


def _local_lock(key):
    with _LOCAL_LOCKS_LOCK:
        return _LOCAL_LOCKS.setdefault(key, threading.Lock())


def _release_lock_file(path):
    """释放锁文件 —— 只删**自己**的锁

    若已被判超时并被别的进程接管，这里不能删（那是别人的锁），否则会把对方变成无锁状态。
    """
    try:
        with open(path, encoding='ascii', errors='replace') as fh:
            owner = int((fh.read().strip() or '0').split()[0])
    except (OSError, ValueError, IndexError):
        owner = None
    if owner is not None and owner != os.getpid():
        return
    try:
        os.remove(path)
    except OSError:
        pass


def _acquire_lock_file(path):
    """抢占锁文件；返回 True 表示抢到

    同一集只放一个人：文件已存在时，属主还活着就让给它（返回 False）；属主已死或已超时
    则视为僵尸锁，删掉重抢 —— 这样部署重启留下的锁会在**下一次点播时立刻被接管**，
    不必再干等 _STALE_LOCK_SECONDS。
    """
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        state = _lock_state(path)
        if state is None:                   # 文件刚被删掉，再抢一次
            return _acquire_lock_file(path)
        if state != 'stale':
            return False
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError:
            return False
        return _acquire_lock_file(path)
    try:
        os.write(fd, str(os.getpid()).encode())
    finally:
        os.close(fd)
    return True


def ensure(series_id, ep, width):
    """确保该集该画质有可播产物。

    :return: True = 已就绪可直接出流；False = 正在转码 / 已失败（看 job_status）
    """
    if is_ready(series_id, ep, width):
        return True
    key = _job_key(series_id, ep, width)
    with _local_lock(key):
        if is_ready(series_id, ep, width):   # 等锁期间可能已被转完
            return True
        os.makedirs(os.path.dirname(stream_path(series_id, ep, width)), exist_ok=True)
        if not _acquire_lock_file(_lock_path(series_id, ep, width)):
            return False                     # 有活着的属主在转（状态见 job_status）
        _start(series_id, ep, width, key)
        return False


def _start(series_id, ep, width, key):
    """启动后台转码线程"""
    def worker():
        try:
            _transcode(series_id, ep, width)
            with _JOBS_LOCK:
                _JOBS.pop(key, None)          # 就绪状态由产物文件表达
        except Exception as exc:  # noqa: BLE001 - 失败要落到状态里给前端看
            with _JOBS_LOCK:
                _JOBS[key] = {'state': 'failed', 'error': str(exc)[:300]}

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
        _release_lock_file(out_path + '.lock')
