"""
红果短剧 - spade_a 密钥解包（还原 CENC content key）

红果把 content key 用自定义的 spade 包装下发，端上由 libttmplayer.so 的一段纯字节变换
解出（无 AES、无 KEK、无设备绑定）。下面 `spade_to_key` 是该变换的纯 Python 复现
（已用公开真值样本校验）。

本模块只做这一件事，供「网页直出」链路使用：转码时要拿 content key 交给 ffmpeg 解密
源站下发的加密 H.265（见 transcode.py）。
"""
import base64


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

