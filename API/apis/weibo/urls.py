"""微博服务路由

域名前缀: /api/weibo/
"""
from django.urls import path

from . import request

urlpatterns = [
    path('channels', request.channels_view, name='weibo_channels'),  # 频道分类
    path('feed', request.feed_view, name='weibo_feed'),             # 按频道取内容
    path('check', request.check_view, name='weibo_check'),          # 校验登录凭据是否有效
    path('video', request.video_view, name='weibo_video'),          # 视频代理播放（免签名，令牌自证）
]
