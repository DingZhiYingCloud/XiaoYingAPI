# -*- coding: utf-8 -*-
"""安全相关：请求签名校验、RSA 签名/验签、摘要。

两个方向：
  1) 子 agent → 大脑：每个请求带 HMAC 签名（令牌+时间戳+随机数+body 摘要），防伪造/防重放
  2) 大脑 → 子 agent：升级包用 RSA 私钥签名，子 agent 用内置公钥验签
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import subprocess

from . import conf as C
from .store import q, x
from .util import is_num, now


# ==================== 请求体解析 ====================
def body_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def parse_body(raw: bytes):
    """宽松解析请求体。

    子 agent 传来的「命令输出 / 日志」可能含非法 UTF-8 字节（例如按字节截断时把一个
    多字节汉字切成两半）。这里用 errors='replace' 解码，**绝不因为脏字节丢掉整条上报**；
    真的不是 JSON 才返回 None。
    """
    if not raw:
        return {}
    try:
        return json.loads(raw.decode('utf-8', 'replace'))
    except ValueError:
        return None


# ==================== 子 agent 请求签名 ====================
def sign_message(method, path, ts, nonce, bhash) -> str:
    """约定的待签名字符串（子 agent 侧用 openssl 算同样的串）。"""
    return f'{method}\n{path}\n{ts}\n{nonce}\n{bhash}'


def verify_agent(handler, body: bytes):
    """校验子 agent 的请求签名。返回 (agent_row, None) 或 (None, 错误原因)。"""
    agent_id = handler.headers.get('X-Agent-Id', '')
    ts = handler.headers.get('X-Ts', '')
    nonce = handler.headers.get('X-Nonce', '')
    sign = handler.headers.get('X-Sign', '')
    if not (agent_id and ts and nonce and sign):
        return None, '缺少签名头'
    row = q('SELECT * FROM agents WHERE agent_id=?', (agent_id,), one=True)
    if not row:
        return None, '未注册的 agent'
    if not is_num(ts) or abs(now() - int(ts)) > 300:
        return None, '时间戳超窗（请校准服务器时间）'
    if q('SELECT 1 FROM nonces WHERE nonce=?', (nonce,), one=True):
        return None, 'nonce 重复（疑似重放）'
    expect = hmac.new(row['token'].encode(), sign_message(
        handler.command, handler.path, ts, nonce, body_hash(body)).encode(),
        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, sign):
        return None, '签名不符'
    x('INSERT OR IGNORE INTO nonces(nonce,ts) VALUES(?,?)', (nonce, now()))
    return row, None


def verify_admin(handler):
    """校验本机 CLI 的管理令牌。"""
    token = q("SELECT v FROM meta WHERE k='admin_token'", one=True)
    if not token:
        return False, '大脑尚未初始化'
    if handler.headers.get('X-Admin-Token', '') != token['v']:
        return False, '管理令牌不正确（内部接口仅供本机 CLI 使用）'
    return True, None


# ==================== RSA 签名（走 openssl 命令行，免第三方库） ====================
def _openssl(*args):
    return subprocess.run(['openssl', *args], capture_output=True, timeout=60)


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def sign_file(path) -> bytes:
    """用大脑私钥给文件签名（返回二进制签名）。"""
    p = _openssl('dgst', '-sha256', '-sign', str(C.SIGN_KEY), str(path))
    if p.returncode != 0:
        raise RuntimeError(f'签名失败：{p.stderr.decode("utf-8", "replace")[:300]}')
    return p.stdout


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode('ascii')


def gen_signing_key() -> bool:
    """生成一对签名密钥（私钥 600，公钥给子 agent）。"""
    if C.SIGN_KEY.exists():
        return True
    C.ensure_home()
    p = _openssl('genrsa', '-out', str(C.SIGN_KEY), '2048')
    if p.returncode != 0:
        return False
    try:
        os.chmod(C.SIGN_KEY, 0o600)
    except OSError:
        pass
    _openssl('rsa', '-in', str(C.SIGN_KEY), '-pubout', '-out', str(C.SIGN_PUB))
    return True


def pubkey_text() -> str:
    """给用户看的公钥文本（拷到每台子 agent）。"""
    if C.SIGN_PUB.exists():
        return C.SIGN_PUB.read_text(encoding='utf-8', errors='replace')
    if C.SIGN_KEY.exists():
        return _openssl('rsa', '-in', str(C.SIGN_KEY), '-pubout').stdout.decode()
    return ''
