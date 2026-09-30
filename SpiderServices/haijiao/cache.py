"""海角社区 爬虫 - 缓存封装

基于 Django 文件缓存后端（settings.CACHES['haijiao']），缓存目录：cache/haijiao/。

TTL：HAIJIAO_DATA_CACHE_TTL（分钟，默认 60，可由 .env 覆盖）——
热门帖按热度排序、会随时间变动，缓存不宜过长。
"""
from django.conf import settings
from django.core.cache import caches

# 当前服务的缓存实例（目录由 settings.CACHES 的 LOCATION 保证）
_cache = caches['haijiao']

# 数据类缓存 TTL（秒）
DATA_TTL = int(getattr(settings, 'HAIJIAO_DATA_CACHE_TTL', 60)) * 60
# 媒体类缓存 TTL（秒）：视频播放列表派生开销较大（多次请求 + node），缓存稍长
MEDIA_TTL = int(getattr(settings, 'HAIJIAO_MEDIA_CACHE_TTL', 30)) * 60


def get_or_fetch(key: str, fetch_fn, ttl: int):
    """
    缓存读取或回源。

    命中缓存直接返回；未命中则调用 fetch_fn 拉取并写入缓存。

    :param key: 缓存键
    :param fetch_fn: 回源函数，返回可序列化对象
    :param ttl: 缓存有效期（秒）
    :return: 缓存值或回源结果
    """
    cached = _cache.get(key)
    if cached is not None:
        return cached

    value = fetch_fn()
    if value is not None:
        _cache.set(key, value, ttl)
    return value
