# 超级鹰 验证码识别服务路由
from django.urls import path

from . import request

# 域名前缀: /api/chaojiying/
urlpatterns = [
    path('ocr', request.ocr_view, name='chaojiying_ocr'),
    path('report-error', request.report_error_view, name='chaojiying_report_error'),
    path('score', request.score_view, name='chaojiying_score'),
]
