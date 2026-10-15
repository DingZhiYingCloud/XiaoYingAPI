"""用户中心 API 签名工具（HMAC-SHA256）

接入项目（子项目）调用用户中心接口时，必须携带签名公共参数：
    app_id    - 项目 APPID（公开标识）
    timestamp - 10 位时间戳（秒），校验 ±5 分钟窗口，防重放
    nonce     - 随机字符串（每次请求唯一）
    sign      - HMAC-SHA256 签名

签名算法（签名绑定「请求方法 + 请求路径」）：
1. 取除 sign 外的所有参数（含 app_id/timestamp/nonce/业务参数），过滤空值，
   按键名 ASCII 升序排序，拼接为 `key=value&key=value...`；
2. 与「方法（大写）+ 路径」拼成待签串：`METHOD\nPATH\n<上一步的串>`；
   PATH 取**最终请求路径**（含结尾斜杠、不含查询串，如 /api/music/xiaoying/search/）；
3. 以 app_secret 为密钥对该待签串做 HMAC-SHA256，输出小写 hex 即为签名。

为什么要绑方法与路径：只签参数、不签目标时，同一条签名可被搬到另一个「参数名兼容」
的端点上复用（截获一次有效请求即可触发非预期动作）。绑上方法 + 路径后，签名只对
它当初签的那个端点有效。
"""
import hashlib
import hmac
import logging
import time

from API.common.security_guard import nonce_replayed
from API.models.Projects.app import UserApp

# 时间戳有效窗口（秒），超出即拒绝，防重放攻击
SIGN_TIMESTAMP_WINDOW = 300

logger = logging.getLogger('api.request')


def build_sign(params: dict, app_secret: str, method: str, path: str) -> str:
    """根据参数、请求方法与路径生成签名（小写 hex）

    :param method: HTTP 方法（大小写不敏感，内部统一转大写）
    :param path:   最终请求路径（含结尾斜杠、不含查询串）
    """
    items = sorted(
        (k, str(v)) for k, v in params.items()
        if k != 'sign' and v not in (None, '')
    )
    raw = f'{method.upper()}\n{path}\n' + '&'.join(f'{k}={v}' for k, v in items)
    return hmac.new(
        app_secret.encode('utf-8'),
        raw.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()


def verify_sign(params: dict, method: str, path: str):
    """校验请求签名

    :param params: 请求参数字典（含 app_id/timestamp/nonce/sign）
    :param method: 本次请求的 HTTP 方法（中间件传入 request.method）
    :param path:   本次请求路径（中间件传入 request.path：含结尾斜杠、不含查询串）
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
    except Exception:
        # 数据库异常也会走到这里：对外仍是 20011（fail-closed），但必须留日志 ——
        # 否则「DB 故障」会被当成「密钥不对」，监控与排查看不出真实原因。
        # 对外只回一句可读的话，不把 DB 异常细节（表名 / SQL）回显给调用方。
        logger.exception('查询接入项目失败: app_id=%s', app_id)
        return False, '查询接入项目失败，请稍后重试'

    if not app.status:
        return False, '接入项目已被停用'

    expect = build_sign(params, app.app_secret, method, path)
    if not hmac.compare_digest(expect, sign.lower()):
        return False, '签名校验失败: sign 不匹配'

    # S-05: nonce 服务端去重（仅对签名合法的请求登记；窗口内重复即视为重放）
    if nonce_replayed(app.app_id, nonce):
        return False, '签名重放: nonce 在有效窗口内重复使用，请更换 nonce 后重试'

    return True, app
