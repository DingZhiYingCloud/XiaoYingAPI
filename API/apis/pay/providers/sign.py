"""易支付 V2 签名工具（RSA / SHA256WithRSA，PKCS#1 v1.5）

文档口径（https://www.ezfp.cn/doc/index.html）：签名算法 `SHA256WithRSA`。
待签名串与 V1 的 MD5 规则一致，只是算法换成了 RSA：

    1. 除 `sign`、`sign_type` 与**空值**外，把全部参数按参数名 ASCII 升序排序；
    2. 拼成 URL 键值对 `a=b&c=d&e=f`，**参数值不做 urlencode**；
    3. 用**商户私钥**对 UTF-8 字节做 SHA256WithRSA 签名，结果 Base64 即 sign；
    4. 校验平台返回 / 异步通知时，用**平台公钥**验签。

注意：空值只剔除「None / 空字符串」，`0` 与 `"0"` 都是有效值，不能丢。
"""
import base64

from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15

#: 不参与签名的字段（文档规定）
_EXCLUDE_KEYS = frozenset({'sign', 'sign_type'})


def build_sign_content(params: dict) -> str:
    """拼出待签名字符串（参数名 ASCII 升序，值不 urlencode）"""
    items = []
    for key, value in params.items():
        if key in _EXCLUDE_KEYS:
            continue
        if value is None or value == '':
            continue
        items.append((str(key), str(value)))
    items.sort(key=lambda kv: kv[0])
    return '&'.join(f'{k}={v}' for k, v in items)


def normalize_key(key_text: str) -> str:
    """把 PEM（带 -----BEGIN----- 头尾、换行）或裸 Base64 统一成裸 Base64 串

    商户后台复制出来的密钥可能是两种形态，这里都兼容：去掉头尾行与所有空白字符。
    """
    if not key_text:
        return ''
    lines = [ln.strip() for ln in (key_text or '').splitlines()]
    kept = [ln for ln in lines if ln and not ln.startswith('-----')]
    return ''.join(kept).replace(' ', '')


def load_private_key(private_key_b64: str) -> RSA.RsaKey:
    """载入商户私钥（支持 PKCS#8 / PKCS#1 DER 的裸 Base64 或 PEM）"""
    return RSA.import_key(base64.b64decode(normalize_key(private_key_b64)))


def load_public_key(public_key_b64: str) -> RSA.RsaKey:
    """载入公钥（支持 X.509 SPKI 的裸 Base64 或 PEM）"""
    return RSA.import_key(base64.b64decode(normalize_key(public_key_b64)))


def sign_content(content: str, private_key_b64: str) -> str:
    """对待签名字符串做 SHA256WithRSA 签名，返回 Base64（表单传输时注意 + 别被解析成空格）"""
    signature = pkcs1_15.new(load_private_key(private_key_b64)).sign(
        SHA256.new(content.encode('utf-8'))
    )
    return base64.b64encode(signature).decode('ascii')


def verify_content(content: str, sign_b64: str, public_key_b64: str) -> bool:
    """用公钥校验签名；任何异常（密钥/签名格式问题）都视为验签失败"""
    if not content or not sign_b64 or not public_key_b64:
        return False
    try:
        pkcs1_15.new(load_public_key(public_key_b64)).verify(
            SHA256.new(content.encode('utf-8')),
            base64.b64decode(sign_b64),
        )
        return True
    except (ValueError, TypeError, KeyError):
        return False
