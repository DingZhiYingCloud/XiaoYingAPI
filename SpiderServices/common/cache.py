"""爬虫缓存公共实现（各线路的 cache.py 复用同一段读写逻辑）

各线路仍各自持有自己的 Django 缓存实例与 TTL（见 settings.CACHES 与各线路 cache.py），
只有「命中返回 / 未命中回源 / 回源结果非 None 才写缓存」这段逻辑收敛到此处，
避免三份逐字复制（曾出现 haijiao / movie_555 / hongguo 各一份完全相同实现）。
"""


def get_or_fetch(cache, key: str, fetch_fn, ttl: int):
    """缓存读取或回源

    命中缓存直接返回；未命中则调用 fetch_fn 拉取并写入缓存。
    回源结果为 None 时不写缓存，避免把「不存在」负缓存。

    :param cache: Django 缓存实例（各线路用 caches['<线路>'] 取得）
    :param key: 缓存键（线路已由缓存目录区分，key 无需含线路名）
    :param fetch_fn: 回源函数，返回可序列化对象
    :param ttl: 缓存有效期（秒）
    :return: 缓存值或回源结果
    """
    cached = cache.get(key)
    if cached is not None:
        return cached

    value = fetch_fn()
    if value is not None:
        cache.set(key, value, ttl)
    return value
