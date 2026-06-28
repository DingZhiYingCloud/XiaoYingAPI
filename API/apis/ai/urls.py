# AI 服务 API 路由
from django.urls import path, include

# 域名前缀: /api/ai/
urlpatterns = [
    path('BuiltInModel/', include('API.apis.ai.BuiltInModel.urls')),  # 内置模型服务路由
]
