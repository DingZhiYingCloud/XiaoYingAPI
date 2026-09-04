"""凭据存储安全工具（S-06 整改）

提供两类能力：
1. 对称加密（app_secret 落库加密）：
   - encrypt_credential / decrypt_credential —— AES-256-GCM，密钥由 SECRET_KEY
     派生（随机 nonce，密文带认证标签），输出带 enc:v1: 前缀便于识别与幂等。
2. 不可逆哈希（登录 Token / 邮箱激活 token 落库哈希）：
   - hash_token —— SHA-256 hex，校验时对客户端提交的明文做同样哈希后查询。
   存量回填由 management 命令 security_backfill 一次性完成（带迁移标记，防重复执行）。

选型说明：密钥不单独新增配置，直接从 SECRET_KEY 派生——更换 SECRET_KEY 等价于
轮换全部密文，部署手册须提示「备份 SECRET_KEY」。
"""
import base64
import hashlib

from django.conf import settings

try:
    from Crypto.Cipher import AES
except ImportError:  # pragma: no cover
    AES = None

# 加密值前缀：识别"已加密"，同时兼容历史明文（无前缀 → 视为明文直读）
ENC_PREFIX = 'enc:v1:'


def _enc_key() -> bytes:
    """由 SECRET_KEY 派生 32 字节 AES 密钥（独立盐，避免与签名用途混用）"""
    return hashlib.sha256(
        f'{settings.SECRET_KEY}:xyapi_credential_enc_v1'.encode('utf-8')
    ).digest()


def encrypt_credential(plaintext: str) -> str:
    """AES-256-GCM 加密明文，返回带 enc:v1: 前缀的 base64 密文"""
    if AES is None:  # pragma: no cover
        raise RuntimeError('缺少 pycryptodome 依赖，无法加密存储凭据')
    plaintext = (plaintext or '')
    cipher = AES.new(_enc_key(), AES.MODE_GCM)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode('utf-8'))
    payload = cipher.nonce + tag + ciphertext
    return ENC_PREFIX + base64.urlsafe_b64encode(payload).decode('ascii')


def decrypt_credential(value: str) -> str:
    """解密 enc:v1: 密文；无前缀的历史明文原样返回"""
    if not value or not value.startswith(ENC_PREFIX):
        return value
    if AES is None:  # pragma: no cover
        raise RuntimeError('缺少 pycryptodome 依赖，无法解密存储凭据')
    data = base64.urlsafe_b64decode(value[len(ENC_PREFIX):].encode('ascii'))
    nonce, tag, ciphertext = data[:16], data[16:32], data[32:]
    cipher = AES.new(_enc_key(), AES.MODE_GCM, nonce=nonce)
    return cipher.decrypt_and_verify(ciphertext, tag).decode('utf-8')


def hash_token(plaintext: str) -> str:
    """Token 单向哈希（SHA-256 hex，64 位），校验时哈希后查询"""
    return hashlib.sha256((plaintext or '').encode('utf-8')).hexdigest()
