# -*- coding: utf-8 -*-
"""零散小工具：时间、随机 ID、数字判断、系统信息。

放这里的原则：跟业务无关、哪个模块都可能用到的纯函数。
"""
from __future__ import annotations

import secrets
import time


def now() -> float:
    """当前 unix 时间戳（秒，浮点）"""
    return time.time()


def new_id(n: int = 12) -> str:
    """随机十六进制串（默认 12 个字符，用于 enroll_id / task_id / nonce 等）"""
    return secrets.token_hex(max(1, n) // 2)


def is_num(s) -> bool:
    """是不是纯数字字符串"""
    return bool(s) and str(s).isdigit()


def os_pretty() -> str:
    """尽量拿到一个好读的系统名称"""
    try:
        with open('/etc/os-release', encoding='utf-8', errors='replace') as fh:
            for line in fh:
                if line.startswith('PRETTY_NAME='):
                    return line.split('=', 1)[1].strip().strip('"')
    except OSError:
        pass
    import platform
    return platform.platform()
