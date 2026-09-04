"""用户中心 API 签名工具（HMAC-SHA256）

接入项目（子项目）调用用户中心接口时，必须携带签名公共参数：
    app_id    - 项目 APPID（公开标识）
    timestamp - 10 位时间戳（秒），校验 ±5 分钟窗口，防重放
    nonce     - 随机字符串（每次请求唯一）
    sign      - HMAC-SHA256 签名

签名算法：
1. 取除 sign 外的所有参数（含 app_id/timestamp/nonce/业务参数），
   按键名 ASCII 升序排序；
2. 拼接为 `key=value&key=value...`；
3. 以 app_secret 为密钥做 HMAC-SHA256，输出小写 hex 即为签名。
"""
import hashlib
import hmac
import time

from API.common.security_guard import nonce_replayed
from API.models.Projects.app import UserApp

# 时间戳有效窗口（秒），超出即拒绝，防重放攻击
SIGN_TIMESTAMP_WINDOW = 300


def build_sign(params: dict, app_secret: str) -> str:
    """根据参数与密钥生成签名（小写 hex）"""
    items = sorted(
        (k, str(v)) for k, v in params.items()
        if k != 'sign' and v not in (None, '')
    )
    raw = '&'.join(f'{k}={v}' for k, v in items)
    return hmac.new(
        app_secret.encode('utf-8'),
        raw.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()


def verify_sign(params: dict):
    """校验请求签名

    :param params: 请求参数字典（含 app_id/timestamp/nonce/sign）
    :return: (True, UserApp) 校验通过；或 (False, err_msg) 失败原因
    """
    app_id = (params.get('app_id') or '').strip()
    timestamp = (params.get('timestamp') or '').strip()
    nonce = (params.get('nonce') or '').strip()
    sign = (params.get('sign') or '').strip()

    if not (app_id and timestamp and nonce and sign):
        return False, '签名参数缺失: app_id / timestamp / nonce / sign 必须同时提供'

    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        return False, '参数格式错误: timestamp 必须为 10 位时间戳(秒)'

    if abs(time.time() - ts) > SIGN_TIMESTAMP_WINDOW:
        return False, '签名过期: timestamp 超出有效窗口(±5分钟)'

    try:
        app = UserApp.objects.get(app_id=app_id)
    except UserApp.DoesNotExist:
        return False, '未注册的接入项目: app_id 不存在'
    except Exception as e:
        return False, f'查询接入项目失败: {e}'

    if not app.status:
        return False, '接入项目已被停用'

    expect = build_sign(params, app.app_secret)
    if not hmac.compare_digest(expect, sign.lower()):
        return False, '签名校验失败: sign 不匹配'

    # S-05: nonce 服务端去重（仅对签名合法的请求登记；窗口内重复即视为重放）
    if nonce_replayed(app.app_id, nonce):
        return False, '签名重放: nonce 在有效窗口内重复使用，请更换 nonce 后重试'

    return True, app
