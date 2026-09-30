"""
红果短剧 App 线路 - 离线取流与解密（H5 未下发直链的集数走这里）

链路:
    series_id + 集号
      -> app_api.get_episode_vids()  取 vid
      -> app_api.get_video_tracks()  取加密直链 + encrypt_info.spade_a + kid
      -> spade_to_key()              本地把 spade_a(37 字节) 解成 content key(32 位 hex)
      -> ffmpeg -decryption_key      原生 CENC(AES-128-CTR) 解密 -> 明文 mp4（写到调用方指定的路径）

关于签名：fqnovel 接口强制校验 metasec 安全头，签名由本机常驻的 unidbg 签名服务提供
（settings.HONGGUO_SIGN_URL，默认 http://127.0.0.1:9099）。该服务是桌面 JVM 里跑
libmetasec_ml.so 的离线签名器，部署物与启动方式见项目部署说明；不依赖模拟器 / frida。

关于 spade_a：红果把 content key 用自定义的 spade 包装下发，端上由
libttmplayer.so 的一段纯字节变换解出（无 AES、无 KEK、无设备绑定）。
下面 spade_to_key 是该变换的纯 Python 复现（已用公开真值样本校验）。

注意：本模块只负责「取流 + 解密 + 原子落盘」；输出路径由调用方（预处理命令）决定，
产物默认约 10~40MB/集。
"""
import base64
import os
import subprocess
import urllib.request

from django.conf import settings

from . import app_api
from . import utils as U

# ffmpeg 可执行文件（解密必需）
_FFMPEG = getattr(settings, "HONGGUO_FFMPEG_BIN", "ffmpeg")
# 期望清晰度高度（0 = 自动取最高可解清晰度）
_WANT_HEIGHT = int(getattr(settings, "HONGGUO_PREPROCESS_HEIGHT", 1080))
# 下载超时（秒）
_DL_TIMEOUT = int(getattr(settings, "HONGGUO_APP_TIMEOUT", 20)) * 6

# ffmpeg 解码能力排序：bytevc2 无开源解码器，排最后
_CODEC_RANK = {"hevc": 3, "h265": 3, "hvc1": 3, "bytevc1": 3, "h264": 2, "avc": 2, "bytevc2": 0}


# ==================== spade_a -> content key ====================


def _popcount(x):
    return bin(x & 0xffffffff).count("1")


def _s8(v):
    v &= 0xff
    return v - 256 if v >= 128 else v


def _strncmp0(a, b, n):
    for k in range(n):
        ca = a[k] if k < len(a) else 0
        cb = b[k] if k < len(b) else 0
        if ca != cb:
            return False
        if ca == 0:
            return True
    return True


def spade_to_key(spade, flag=0):
    """
    spade_a(37 字节原始数据，或 52 字符 base64) -> content key(32 位 hex 字符串)。

    ver2 包装（app_v2 / web_v2）走 AES-GCM，本实现不处理，返回 None。
    """
    if isinstance(spade, str):
        spade = base64.b64decode(spade)
    length = len(spade)
    if length < 3:
        return None
    b_var5 = spade[0] ^ spade[1] ^ spade[2]
    i_var9 = b_var5 - 0x30                      # type 字符串长度
    if i_var9 < 1:
        return None
    u_var1 = (length - b_var5) + 0x2f           # 工作缓冲长度
    if u_var1 < 1 or 1 + u_var1 > length:
        return None
    dest = bytearray(spade[1:1 + u_var1])
    # 解出 type 字符串，判断 ver1 / ver2
    s1 = bytearray(i_var9)
    b16 = spade[length - i_var9 - 2]
    b14 = spade[length - i_var9 - 1]
    for i in range(i_var9):
        s1[i] = b14 ^ b16 ^ spade[i + (length - i_var9)]
    if _strncmp0(s1, b"app_v2", i_var9) or _strncmp0(s1, b"web_v2", i_var9):
        return None
    # ver1：逐字节变换（异或 + popcount + 位置相关）
    b14, b16 = 0x55, 0xfa
    for i in range(u_var1):
        b6 = dest[i]
        u18 = _popcount(i)
        b3, b7 = b6, b14
        if i & 1:
            b3, b7, b16 = b16, b6, b14
        c_var4 = (u18 + 0x15) if flag else _s8(-0x15 - u18)
        dest[i] = (c_var4 + (b16 ^ b6)) & 0xff
        b14, b16 = b7, b3
    b0 = dest[0]
    if 0x30 <= b0 <= 0x39:
        u11 = b0 - 0x30
    elif 0x61 <= b0 <= 0x7a:
        u11 = b0 - 0x57
    else:
        return None
    iv9 = u_var1 - (u11 & 0xff)
    if iv9 < 2:
        return None
    return bytes(dest[1:iv9]).decode("latin1", "replace")


# ==================== 轨道选择 / 下载 / 解密 ====================


def _pick_track(tracks):
    """挑 ffmpeg 可解的最高清晰度轨道；_WANT_HEIGHT 非 0 时优先取该高度"""
    decodable = [t for t in tracks
                 if _CODEC_RANK.get(str((t.get("video_meta") or {}).get("codec_type")), 0) >= 2]
    pool = decodable or tracks

    def height(t):
        return int((t.get("video_meta") or {}).get("vheight") or 0)

    if _WANT_HEIGHT:
        for t in pool:
            if height(t) == _WANT_HEIGHT:
                return t
    return max(pool, key=height)


def _download(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": U.APP_HEADERS["user-agent"]})
    with urllib.request.urlopen(req, timeout=_DL_TIMEOUT) as resp, open(path, "wb") as f:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    return os.path.getsize(path)


def _verify_decoded(path):
    """
    轻校验：能干净解出至少一帧才算解密成功。
    content key 错误时数据是随机字节，解码器会直接报 NAL 相关错误（stderr 非空）。
    """
    proc = subprocess.run([_FFMPEG, "-v", "error", "-i", path, "-frames:v", "1",
                           "-f", "null", "-"], capture_output=True, timeout=120)
    return proc.returncode == 0 and not proc.stderr.strip()


def decrypt_episode(series_id, ep, out_path, vids=None):
    """
    取流 + CENC 解密，把明文 mp4 写到 out_path（原子落盘、+faststart）。

    :param series_id: 剧集 id
    :param ep: 集号（从 1 开始）
    :param out_path: 目标文件路径（父目录不存在时自动创建）
    :param vids: 可选的 {集号: vid}；批量处理时传入可省掉每集一次取流（每次都要签名）
    :return: {path, size, quality, codec, height}
    """
    series_id, ep = str(series_id), int(ep)
    if vids is None:
        vids = app_api.get_episode_vids(series_id)
    vid = vids.get(ep)
    if not vid:
        raise RuntimeError(f"App 接口未返回第 {ep} 集（该剧共 {len(vids)} 集）")
    tracks = app_api.get_video_tracks([vid]).get(vid) or []
    if not tracks:
        raise RuntimeError(f"App 接口未返回第 {ep} 集的视频轨道")

    track = _pick_track(tracks)
    meta = track.get("video_meta") or {}
    encrypt = track.get("encrypt_info") or {}
    if not encrypt.get("encrypt"):
        raise RuntimeError(f"第 {ep} 集未标记加密，取流结果与预期不符")
    key = spade_to_key(encrypt.get("spade_a") or "")
    if not key:
        raise RuntimeError(f"第 {ep} 集 spade_a 解包失败（可能为新的包装版本）")

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    tmp_enc = out_path + ".enc.tmp"
    tmp_plain = out_path + ".tmp"
    try:
        size = 0
        for url in (track.get("main_url"), track.get("backup_url")):
            if not url:
                continue
            try:
                size = _download(url, tmp_enc)
                break
            except Exception:  # noqa: BLE001 - 主链失败自动试备链
                continue
        if not size:
            raise RuntimeError(f"第 {ep} 集视频流下载失败")

        # 临时名不带 .mp4 后缀，故显式指定输出容器格式；
        # +faststart 把 moov 挪到文件头，播放器起播时不必先取文件尾部
        proc = subprocess.run([_FFMPEG, "-y", "-loglevel", "error", "-decryption_key", key,
                               "-i", tmp_enc, "-c", "copy", "-movflags", "+faststart",
                               "-f", "mp4", tmp_plain],
                              capture_output=True, timeout=600)
        if proc.returncode != 0:
            raise RuntimeError(f"第 {ep} 集解密失败: "
                               f"{proc.stderr.decode('utf-8', 'replace')[:200]}")
        if not _verify_decoded(tmp_plain):
            raise RuntimeError(f"第 {ep} 集解密结果校验未通过（content key 可能不匹配）")
        os.replace(tmp_plain, out_path)   # 原子落盘，避免读到半成品
    finally:
        for p in (tmp_enc, tmp_plain):
            if os.path.exists(p):
                os.remove(p)

    return {"path": out_path, "size": os.path.getsize(out_path),
            "quality": meta.get("definition"), "codec": meta.get("codec_type"),
            "height": int(meta.get("vheight") or 0)}
