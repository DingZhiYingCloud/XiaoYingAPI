"""限流固定窗口行为测试

锁住两件事：
  ① 窗口内累计超过上限即拒绝；
  ② 窗口**到点会自动放行** —— 曾经用缓存后端的自增计数实现，它会按后端默认 TTL 续期，
     把 60 秒窗口越拖越长（实测拖到 300 秒），限流实际失效；本测试防止回归。
"""
import time

from django.core.cache import caches
from django.test import SimpleTestCase

from API.common.ratelimit import allow


class RateLimitTests(SimpleTestCase):
    """固定窗口计数：超限拒绝、过期恢复"""

    def setUp(self):
        self.cache = caches['ratelimit']
        self.cache.clear()

    def test_blocks_after_limit(self):
        """同一窗口内第 limit+1 次开始拒绝"""
        results = [allow('test:block', 3, 60) for _ in range(5)]
        self.assertEqual(results, [True, True, True, False, False])

    def test_window_recovers(self):
        """窗口结束后自动恢复放行（窗口长度 1 秒）"""
        for _ in range(3):
            allow('test:recover', 3, 1)
        self.assertFalse(allow('test:recover', 3, 1))
        time.sleep(1.2)
        self.assertTrue(allow('test:recover', 3, 1))

    def test_keys_are_independent(self):
        """不同 key 各自计数，互不影响"""
        for _ in range(3):
            allow('test:a', 3, 60)
        self.assertFalse(allow('test:a', 3, 60))
        self.assertTrue(allow('test:b', 3, 60))
