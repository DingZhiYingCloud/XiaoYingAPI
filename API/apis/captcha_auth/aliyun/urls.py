# 阿里云图形认证集成服务路由
from django.urls import path

from . import request

# 域名前缀: /api/captcha_auth/aliyun/
urlpatterns = [
    path('config', request.config_view, name='captcha_auth_aliyun_config'),  # 获取图形认证配置（appId）
    path('verify', request.verify_view, name='captcha_auth_aliyun_verify'),  # 二次校验
]
