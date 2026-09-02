# API路由
from django.urls import path, include

# 域名前缀: /api/
urlpatterns = [
    path('email/', include('API.apis.emails.urls')), # 邮箱服务路由
    path('music/', include('API.apis.musics.urls')), # 音乐服务路由
    path('upload/', include('API.apis.uploads.urls')), # 文件上传服务路由
    path('video_analysis/', include('API.apis.VideoAnalysis.urls')), # 视频分析服务路由
    path('ai/', include('API.apis.ai.urls')), # AI服务路由
    path('spider_verification/', include('API.apis.SpiderVerification.urls')), # 爬虫验证服务路由
    path('bing/', include('API.apis.bing.urls')), # Bing服务路由
    path('dlt/', include('API.apis.DaiLianTong.urls')), # 代练通服务路由
    path('dlwz/', include('API.apis.DaiLianWanZi.urls')), # 代练丸子服务路由
    path('ddddocr/', include('API.apis.DdddocrRecognizer.urls')), # ddddocr 验证码识别服务路由
    path('ProxyIp/', include('API.apis.ProxyIp.urls')), # 代理IP服务路由
    path('seo/', include('API.apis.seo.urls')),         # SEO服务路由(友情链接等)
    path('user_center/', include('API.apis.user_center.urls')), # 用户中心服务路由
    path('sms_verify/', include('API.apis.sms_verify.urls')),   # 验证码认证服务路由
    path('captcha_auth/', include('API.apis.captcha_auth.urls')), # 图形认证集成服务路由
    path('feedback/', include('API.apis.feedback.urls')),       # 问题反馈中心服务路由
]

