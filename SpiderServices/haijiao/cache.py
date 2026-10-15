"""海角社区 爬虫 - 缓存封装

基于 Django 文件缓存后端（settings.CACHES['haijiao']），缓存目录：cache/haijiao/。

TTL：HAIJIAO_DATA_CACHE_TTL（分钟，默认 60，可由 .env 覆盖）——
热门帖按热度排序、会随时间变动，缓存不宜过长。
"""
from django.conf import settings
from django.core.cache import caches

from SpiderServices.common.cache import get_or_fetch as _get_or_fetch

# 当前服务的缓存实例（目录由 settings.CACHES 的 LOCATION 保证）
_cache = caches['haijiao']

# 数据类缓存 TTL（秒）
DATA_TTL = int(getattr(settings, 'HAIJIAO_DATA_CACHE_TTL', 60)) * 60
# 媒体类缓存 TTL（秒）：视频播放列表派生开销较大（多次请求 + node），缓存稍长
MEDIA_TTL = int(getattr(settings, 'HAIJIAO_MEDIA_CACHE_TTL', 30)) * 60


def get_or_fetch(key: str, fetch_fn, ttl: int):
    """缓存读取或回源（实现见 SpiderServices/common/cache.py，各线路共用）"""
    return _get_or_fetch(_cache, key, fetch_fn, ttl)
