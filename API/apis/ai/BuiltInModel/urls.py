# DeepSeek 内置模型 API路由
from django.urls import path

from . import request

# 域名前缀: /api/ai/BuiltInModel/
urlpatterns = [
    path('deepseek', request.deepseek_view, name='ai_builtin_deepseek'),  # DeepSeek AI对话
]
