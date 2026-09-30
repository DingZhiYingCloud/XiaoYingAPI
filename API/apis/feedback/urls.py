# 问题反馈中心 API 路由
from django.urls import path

from . import request

# 域名前缀: /api/feedback/
# 两个端点均免签名（服务策略见迁移 0043_feedback_seed），供子项目前端直接调用；
# 反馈的提交 / 查看 / 回复都在托管的反馈页 /feedback/<app_id>/ 上完成。
urlpatterns = [
    path('ticket', request.ticket_view, name='feedback_ticket'),      # 用用户 Token 换一次性票据
    path('contacts', request.contacts_view, name='feedback_contacts'),  # 查开发者联系方式
]
