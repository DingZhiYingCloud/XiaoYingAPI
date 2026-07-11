# DdddocrRecognizer API路由
from django.urls import path

from . import request

# 域名前缀: /api/ddddocr/
urlpatterns = [
    path('ocr', request.ocr_view, name='ddddocr_ocr'),
    path('set-ranges', request.set_ranges_view, name='ddddocr_set_ranges'),
    path('detect', request.detect_view, name='ddddocr_detect'),
    path('slide-match', request.slide_match_view, name='ddddocr_slide_match'),
    path('slide-comparison', request.slide_comparison_view, name='ddddocr_slide_comparison'),
    path('batch-ocr', request.batch_ocr_view, name='ddddocr_batch_ocr'),
    path('save-debug', request.save_debug_view, name='ddddocr_save_debug'),
]
