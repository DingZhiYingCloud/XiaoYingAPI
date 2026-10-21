"""自研图形验证码 - 公共防护

四条线路（字符 / 算术、滑块、汉字点选）共用同一套：
    - 按客户端 IP 的固定窗口限流
    - 连续失败 N 次后的短时冷却
    - 验证码响应禁止缓存
    - 过期记录限批清理

集中在这里，避免每新增一种验证码就把限流 / 冷却 / 清理代码复制一遍。
"""
from functools import wraps

from django.utils import timezone

from API.common import StatusCode
from API.common import ratelimit as _rl
from API.common.ip_guard import client_ip
from API.common.responses import json_response

# 固定窗口长度（秒）；所有线路一致
RATE_WINDOW = 60
# 单次清理的最大条数：避免极端情况下一次 DELETE 锁表太久
CLEANUP_BATCH = 500


def no_store(view):
    """给验证码响应统一加禁止缓存头（GET 生成的图片绝不能被缓存复用）"""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        response = view(request, *args, **kwargs)
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response['Pragma'] = 'no-cache'
        return response
    return wrapper


def rate_limited(request, scope, limit):
    """按 IP 限流；限流组件自身故障时放行（见 API/common/ratelimit.py）"""
    return not _rl.allow(f'captcha_self:{scope}:{client_ip(request)}', limit, RATE_WINDOW)


def fail_keys(request, scope):
    """连续失败冷却用的一对缓存键（失败计数 + 封禁标记）"""
    ip = client_ip(request)
    return (f'captcha_self:{scope}:fail:{ip}',
            f'captcha_self:{scope}:block:{ip}')


def blocked(block_key):
    return _rl.blocked(block_key)


def too_many_failures(block_seconds):
    """冷却期内的统一响应"""
    minutes = max(1, int(block_seconds) // 60)
    return json_response(
        StatusCode.RATE_LIMITED, data={'passed': False},
        msg=f'验证失败次数过多，请 {minutes} 分钟后再试')


def record_failure(fail_key, block_key, fail_limit, fail_window, block_seconds):
    """记一次失败；达到阈值即封禁并清零计数。

    :return: True 表示本次已进入冷却（调用方应返回 20040）
    """
    if _rl.hit(fail_key, fail_window) >= fail_limit:
        _rl.block(block_key, block_seconds)
        _rl.reset(fail_key)
        return True
    return False


def reset_failure(fail_key):
    """校验成功后清零失败计数"""
    _rl.reset(fail_key)


def cleanup_expired(model, batch=CLEANUP_BATCH):
    """限批清理过期挑战记录（生成接口顺带调用，无需定时任务）"""
    now = timezone.now()
    ids = list(
        model.objects.filter(expire_time__lt=now)
        .values_list('id', flat=True)[:batch]
    )
    if ids:
        model.objects.filter(id__in=ids).delete()
