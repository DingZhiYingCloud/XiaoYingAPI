# 自研图形验证码 API 路由
from django.urls import path

from . import request

# 域名前缀: /api/captcha_self/
urlpatterns = [
    path('generate', request.generate_view, name='captcha_self_generate'),  # 生成验证码
    path('verify', request.verify_view, name='captcha_self_verify'),        # 校验验证码
    path('slider/generate', request.slider_generate_view, name='captcha_self_slider_generate'),  # 生成滑块
    path('slider/verify', request.slider_verify_view, name='captcha_self_slider_verify'),        # 校验滑块
    path('click/generate', request.click_generate_view, name='captcha_self_click_generate'),     # 生成汉字点选
    path('click/verify', request.click_verify_view, name='captcha_self_click_verify'),           # 校验汉字点选
    path('behavior', request.behavior_view, name='captcha_self_behavior'),                       # 行为验证影子采集
]
