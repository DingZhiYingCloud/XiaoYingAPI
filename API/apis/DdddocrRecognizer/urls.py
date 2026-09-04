# DdddocrRecognizer API路由
from django.urls import path

from . import request

# 域名前缀: /api/ddddocr/
# 说明: batch-ocr / save-debug 两个高危接口（任意目录扫描/任意路径写文件）已下线（S-01 整改）
urlpatterns = [
    path('ocr', request.ocr_view, name='ddddocr_ocr'),
    path('set-ranges', request.set_ranges_view, name='ddddocr_set_ranges'),
    path('detect', request.detect_view, name='ddddocr_detect'),
    path('slide-match', request.slide_match_view, name='ddddocr_slide_match'),
    path('slide-comparison', request.slide_comparison_view, name='ddddocr_slide_comparison'),
]
