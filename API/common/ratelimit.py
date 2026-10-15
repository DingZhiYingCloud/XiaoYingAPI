"""轻量接口限流（固定窗口计数）

背景：公开接口（如 `/api/statistics/`，匿名可访问）原先没有任何频率约束，被反复刷新时会
持续触发数据库聚合查询，属于「匿名可放大的」资源消耗面。

为什么用文件缓存而不是默认的进程内存缓存：限流必须**跨 uwsgi worker 共享计数** ——
用 locmem 时每个 worker 各算一份，实际放行量会变成 `limit × worker 数`，限流形同虚设。

局限（有意为之，够用即可）：固定窗口在窗口边界可能出现短时约两倍放行；不处理多机部署
（本项目是单机多 worker）。若将来需要更严，再换滑动窗口 / Redis 实现。
"""
import logging
import time

from django.core.cache import caches

logger = logging.getLogger('api.request')

_RL = caches['ratelimit']


def allow(key: str, limit: int, window: int) -> bool:
    """记一次访问并判断是否放行（窗口内累计超过 limit 即返回 False）

    :param key:    计数维度，如 f'statistics:{ip}'
    :param limit:  窗口内允许的最大次数
    :param window: 窗口长度（秒）

    实现要点：把「窗口起点 + 计数」一起存进缓存，并在每次写入时把 TTL 设成**本窗口的剩余
    时间**。不能直接依赖缓存后端的自增计数 —— 它的实现是按后端默认 TTL 续期的，窗口会被
    一次次请求越拖越长（实测：60 秒窗口在持续请求后被拖成 300 秒，限流形同失效）。
    """
    cache_key = f'rl:{key}'
    now = time.time()
    try:
        state = _RL.get(cache_key)
        if state is None:                      # 新窗口
            _RL.set(cache_key, (now, 1), window)
            return True
        start, count = state
        count += 1
        # 距窗口结束至少留 1 秒，避免 TTL 算成 0 时键立刻过期、窗口被无限延长
        remaining = max(1, int(round(window - (now - start))))
        _RL.set(cache_key, (start, count), remaining)
        return count <= limit
    except Exception:
        # 限流是「附加保护」而不是业务前提：缓存不可用（磁盘满等）时放行，
        # 不能因为限流组件本身故障把正常接口一起拖挂。
        logger.exception('限流计数失败，本次放行: key=%s', key)
        return True
