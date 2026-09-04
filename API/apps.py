from django.apps import AppConfig
from django.db.models.signals import post_delete, post_save


class ApiConfig(AppConfig):
    name = 'API'
    verbose_name = 'API服务'

    def ready(self):
        # A-02：分类树查询缓存失效钩子 —— 后台保存/删除 ApiCategory 后立即失效，
        # 保证认证模式/启用状态改动即时生效，无需等待 TTL（默认 60s）
        from API.common.middleware import invalidate_api_category_cache
        from API.models.Auth.category import ApiCategory

        def _invalidate_cache(sender, instance, **kwargs):
            invalidate_api_category_cache()

        post_save.connect(_invalidate_cache, sender=ApiCategory, weak=False)
        post_delete.connect(_invalidate_cache, sender=ApiCategory, weak=False)
