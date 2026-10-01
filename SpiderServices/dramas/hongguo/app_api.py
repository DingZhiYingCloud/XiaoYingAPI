"""
红果短剧 App 线路 - fqnovel 内部接口客户端

用途：H5 站点只对每部剧前若干集下发直链，超出的集数（第 4 集起）由本模块通过
App 使用的 fqnovel 内部接口取流，交给「网页直出」转码链路（见 transcode.py）。
该接口强制校验 metasec 安全头，签名由本机常驻的 unidbg 签名服务生成
（settings.HONGGUO_SIGN_URL，见 sign_service.py）。

对外能力:
    get_episode_vids(series_id) -> {集号: vid}
    get_video_tracks(vids)      -> {vid: [轨道, ...]}

约定：网络/签名/业务码异常统一抛 RuntimeError，由上层 API 层捕获转成错误码。
"""
import hashlib
import json
import time
from urllib.parse import quote

import requests
from django.conf import settings

from . import sign_service
from . import utils as U

try:  # 与 H5 线路一致：可用时用 curl_cffi 伪装 TLS 指纹
    from curl_cffi import requests as creq
except Exception:  # noqa: BLE001 - 缺失时退回原生 requests
    creq = None

# 签名服务地址（与 API 服务同机常驻）
_SIGN_URL = getattr(settings, "HONGGUO_SIGN_URL", "http://127.0.0.1:9099")
# 签名服务是单模拟器串行处理，签名本身很快；取流/下载另有超时
_SIGN_TIMEOUT = int(getattr(settings, "HONGGUO_SIGN_TIMEOUT", 30))
# App 接口单次请求超时（秒）
_API_TIMEOUT = int(getattr(settings, "HONGGUO_APP_TIMEOUT", 20))


def _ext_session():
    """外部请求会话（每次新建：调用频率很低，换取与并发无关的简单性）"""
    if creq is not None:
        return creq.Session(impersonate="chrome")
    return requests.Session()


def _build_url(path: str) -> str:
    """拼 App 接口完整 URL：域名 + 路径 + 设备参数（含毫秒时间戳 _rticket）"""
    q = dict(U.APP_QUERY)
    q["_rticket"] = str(int(time.time() * 1000))
    qs = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in q.items())
    return f"{U.APP_API_BASE}{path}?{qs}"


def _sign(url: str, headers: dict) -> dict:
    """调本机 unidbg 签名服务，返回需追加的安全头（X-Argus / X-Gorgon / ...）"""
    # 签名服务未在运行时由本项目拉起（本机地址；指向远端签名服务时只做客户端）
    if not sign_service.ensure_started():
        raise RuntimeError(f"签名服务不可用（{_SIGN_URL}）")
    try:
        r = requests.post(f"{_SIGN_URL.rstrip('/')}/sign",
                          json={"url": url, "headers": headers}, timeout=_SIGN_TIMEOUT)
        r.raise_for_status()
        sig = r.json()
    except Exception as e:  # noqa: BLE001 - 连接失败/超时等统一上抛
        raise RuntimeError(f"签名服务不可用（{_SIGN_URL}）: {e}") from e
    if "error" in sig:
        raise RuntimeError(f"签名失败: {sig['error']}")
    return sig


def _post(path: str, body: dict) -> dict:
    """
    带签名的 POST 调用，返回响应 JSON 的 data 字段。

    请求体经紧凑 JSON 序列化后算 md5 作为 x-ss-stub（App 一致的报文指纹），
    再把签名头并入后发出；业务码非 0 时抛 RuntimeError。
    """
    url = _build_url(path)
    headers = dict(U.APP_HEADERS)
    headers["content-type"] = "application/json; charset=utf-8"
    data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers["x-ss-stub"] = hashlib.md5(data).hexdigest().upper()
    headers.update(_sign(url, headers))

    try:
        r = _ext_session().post(url, data=data, headers=headers, timeout=_API_TIMEOUT)
        r.raise_for_status()
        result = r.json()
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"调用 App 接口失败（{path}）: {e}") from e

    if not result:
        raise RuntimeError(f"App 接口返回空响应（{path}），签名可能已被拒绝")
    code = result.get("code")
    if code != 0:
        raise RuntimeError(f"App 接口返回异常（{path}）: code={code} msg={result.get('message') or result.get('msg')}")
    return result.get("data") or {}


# ==================== 对外能力 ====================


def get_episode_vids(series_id):
    """
    取某剧全部集号对应 vid。

    :param series_id: 剧集 id（与 H5 站点同一套 id）
    :return: {集号(int): vid(str)}
    """
    series_id = str(series_id)
    body = {"biz_param": U.APP_EPISODES_BIZ_PARAM, "series_id": series_id}
    data = _post(U.APP_PATH_EPISODES, body)
    video_list = ((data.get(series_id) or {}).get("video_data") or {}).get("video_list") or []
    vids = {}
    for item in video_list:
        index, vid = item.get("vid_index"), item.get("vid")
        if index and vid:
            vids[int(index)] = str(vid)
    if not vids:
        raise RuntimeError(f"App 接口未返回剧集列表: series_id={series_id}")
    return vids


def get_video_tracks(vids):
    """
    批量取视频轨道（含加密直链与 encrypt_info.spade_a / kid）。

    :param vids: vid 可迭代对象
    :return: {vid(str): [轨道 dict, ...]}；接口未返回的 vid 不在结果里
    """
    out = {}
    vids = [str(v) for v in vids]
    batch = max(1, int(U.APP_VID_BATCH))
    for i in range(0, len(vids), batch):
        body = {"biz_param": U.APP_MODEL_BIZ_PARAM,
                "mixed_video_id_map": {"1": vids[i:i + batch]}}
        data = _post(U.APP_PATH_VIDEO_MODEL, body)
        for vid, item in data.items():
            raw = (item or {}).get("video_model")
            if not raw:
                continue
            tracks = (json.loads(raw).get("video_list") or [])
            if tracks:
                out[str(vid)] = tracks
    return out
