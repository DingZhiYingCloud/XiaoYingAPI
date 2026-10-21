"""自研图形验证码 - 汉字点选演示页

页面：
    GET /captcha_self/click/   公开演示页（无需登录）

页面只做交互与展示，生成 / 校验都调用开放接口：
    GET  /api/captcha_self/click/generate
    POST /api/captcha_self/click/verify
"""
from django.shortcuts import render


def click_demo_view(request):
    return render(request, 'captcha_self/click.html', {})
