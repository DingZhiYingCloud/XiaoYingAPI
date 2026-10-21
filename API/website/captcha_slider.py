"""自研图形验证码 - 滑块验证演示页

页面：
    GET /captcha_self/slider/   公开演示页（无需登录）

页面只做交互与展示，生成 / 校验都调用开放接口：
    GET  /api/captcha_self/slider/generate
    POST /api/captcha_self/slider/verify
"""
from django.shortcuts import render


def slider_demo_view(request):
    return render(request, 'captcha_self/slider.html', {})
