# -*- coding: utf-8 -*-
"""本机 CLI ↔ 本机服务 之间的小客户端。

为什么绕一圈走 HTTP 而不是直接读数据库？因为所有业务逻辑集中在服务里，
CLI 只是“另一个调用方”，这样两边行为完全一致，也不会出现两个进程同时改库的问题。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

from . import conf as C
from . import ui
from .store import get_meta


def _local_pid_alive() -> bool:
    """本机那个 brain serve 进程还在不在（读 brain.pid，不发任何 HTTP）。"""
    try:
        pid = int(C.PID_FILE.read_text().strip())
    except (OSError, ValueError):
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, ValueError):
        return False
    except PermissionError:
        return True


def api(conf, method, path, body=None, admin=True, timeout=30):
    """调大脑服务。只经 https://域名（PUBLIC_URL），http/IP 一律不用。

    返回 (响应dict, 错误字符串)。
    """
    base = C.public_base(conf)
    if not base:
        return None, '未配置大脑对外地址（PUBLIC_URL 必须是 https://域名）'
    url = f'{base}{path}'
    data = json.dumps(body or {}, ensure_ascii=False).encode() if body is not None else None
    headers = {'Content-Type': 'application/json'}
    if admin:
        headers['X-Admin-Token'] = get_meta('admin_token') or ''
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8', 'replace')), None
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode('utf-8', 'replace')), None
        except Exception:                            # noqa: BLE001
            return None, f'HTTP {e.code}'
    except Exception as e:                           # noqa: BLE001
        return None, str(e)


def server_alive(conf) -> bool:
    base = C.public_base(conf)
    if not base:
        return False
    try:
        with urllib.request.urlopen(f'{base}/health', timeout=3) as r:
            return bool(json.loads(r.read().decode())['ok'])
    except Exception:                                # noqa: BLE001
        return False


def ensure_server(conf) -> bool:
    """确保大脑服务可用（对外地址 https://域名 能访问）。本机进程没起就后台拉起。"""
    base = C.public_base(conf)
    if not base:
        ui.err('还没配置大脑的对外地址，无法使用。')
        ui.dim('  请在 brain.conf 里设置：PUBLIC_URL=https://你的域名')
        ui.dim('  必须是 https + 域名（http:// 或 IP 一律不认）。')
        return False
    if server_alive(conf):
        return True
    if _local_pid_alive():
        ui.err(f'本机大脑服务在跑，但通过 {base} 访问不到。')
        ui.dim('  多半是：域名没解析到本机 / nginx 没配好 / 证书无效。修好后重试。')
        return False
    ui.warn('大脑服务未运行，正在后台启动…')
    C.ensure_home()
    entry = C.script_dir() / 'brain'
    with open(C.HOME / 'serve.out', 'ab') as fh:
        subprocess.Popen([sys.executable, str(entry), 'serve'],
                         stdout=fh, stderr=fh, stdin=subprocess.DEVNULL,
                         start_new_session=True)
    for _ in range(40):
        time.sleep(0.5)
        if server_alive(conf):
            ui.good('大脑服务已启动。')
            return True
    ui.err(f'启动后仍无法通过 {base} 访问。')
    ui.dim(f'  请检查域名解析 / nginx 反代 / 证书，或看 {C.HOME / "serve.out"}')
    return False
