"""
555电影 线路 - 缓存封装

基于 Django 文件缓存后端（settings.CACHES['movie_555']），
缓存目录按「服务 + 线路」区分：cache/movies/movie_555/
后续新增线路（如 movie_iqiyi）时，在 settings 中新增一个同结构的 CACHES 项即可，
各线路缓存互不干扰。

TTL 双档（均在 settings 中配置，可由 .env 覆盖）:
    数据类（列表/详情/首页）: MOVIE_555_DATA_CACHE_TTL，默认 1440 分钟
        —— 片名、简介、集数等固定信息，可长期缓存
    媒体类（m3u8 播放地址）: MOVIE_555_MEDIA_CACHE_TTL，默认 30 分钟
        —— 播放地址带时效，需较短缓存以便及时刷新
"""

from django.conf import settings
from django.core.cache import caches

# 当前线路的缓存实例（线路区分由 settings.CACHES 的 LOCATION 保证）
_cache = caches["movie_555"]

# 数据类缓存 TTL（秒）
DATA_TTL = int(getattr(settings, "MOVIE_555_DATA_CACHE_TTL", 1440)) * 60
# 媒体类缓存 TTL（秒）
MEDIA_TTL = int(getattr(settings, "MOVIE_555_MEDIA_CACHE_TTL", 30)) * 60


def get_or_fetch(key: str, fetch_fn, ttl: int):
    """
    缓存读取或回源。

    命中缓存直接返回；未命中则调用 fetch_fn 拉取并写入缓存。

    :param key: 缓存键（线路已由缓存目录区分，key 无需含线路名）
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
