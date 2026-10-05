# 代练搬单 order_migration API路由
from django.urls import path

from . import request

# 域名前缀: /api/order_migration/
urlpatterns = [
    # 预览代练通订单 -> 代练丸子发单参数的映射（不真实发单）
    path('preview', request.preview_view, name='order_migration_preview'),
]
