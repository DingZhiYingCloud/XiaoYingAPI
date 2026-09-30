# AI 内置模型 API路由
from django.urls import path

from . import request

# 域名前缀: /api/ai/BuiltInModel/
urlpatterns = [
    path('chat', request.chat_view, name='ai_builtin_chat'),          # 统一对话（model 参数切换模型）
    path('models', request.models_view, name='ai_builtin_models'),    # 可用模型清单
]
