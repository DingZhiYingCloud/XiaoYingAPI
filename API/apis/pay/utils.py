"""支付模块公共工具（渠道层与业务层共用，不依赖任何支付渠道实现）"""
import random
import time
from decimal import Decimal, InvalidOperation

from django.conf import settings

#: 金额统一小数位（元）
MONEY_PLACES = Decimal('0.01')


def format_money(value) -> str:
    """把金额统一成「元、两位小数字符串」——传给支付平台与签名都用这个形态

    绝不用 float：`Decimal(str(value))` 保证 `1` / `1.0` / `1.00` 都变成 `'1.00'`。
    """
    return str(Decimal(str(value)).quantize(MONEY_PLACES))


def parse_money(text):
    """把外部传入的金额字符串解析成 Decimal（非法返回 None）"""
    try:
        return Decimal(str(text)).quantize(MONEY_PLACES)
    except (InvalidOperation, TypeError, ValueError):
        return None


def gen_out_trade_no(prefix: str = 'XY') -> str:
    """生成商户订单号：前缀 + 年月日时分秒 + 6 位随机数（够用且可读，唯一性由 DB 唯一约束兜底）"""
    stamp = time.strftime('%Y%m%d%H%M%S')
    return f'{prefix}{stamp}{random.randint(100000, 999999)}'


def client_ip(request) -> str:
    """取客户端真实 IP（优先 X-Forwarded-For 首段，取不到回落到 REMOTE_ADDR）"""
    if request is None:
        return ''
    forwarded = (request.META.get('HTTP_X_FORWARDED_FOR') or '').split(',')[0].strip()
    return forwarded or (request.META.get('REMOTE_ADDR') or '')


def absolute_url(request, path: str) -> str:
    """拼公网绝对地址（支付平台的 notify_url / return_url 必须绝对地址且不带参数）

    有 request 时用它的 host（线上经 nginx 透传 X-Forwarded-Proto，即站点真实域名）；
    没有 request（脚本 / 定时查单）时回落到 ALLOWED_HOSTS 的第一个非通配域名。
    """
    if not path.startswith('/'):
        path = '/' + path
    if request is not None:
        return request.build_absolute_uri(path)
    hosts = [h for h in getattr(settings, 'ALLOWED_HOSTS', []) if h and h not in ('*', 'localhost', '127.0.0.1')]
    host = hosts[0] if hosts else 'localhost'
    return f'https://{host}{path}'
