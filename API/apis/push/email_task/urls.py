# 推送服务 · 邮件定时推送线路 API 路由
from django.urls import path

from . import request

# 域名前缀: /api/push/email_task/
urlpatterns = [
    path('create', request.create_view, name='push_email_task_create'),  # 新建任务
    path('list', request.list_view, name='push_email_task_list'),        # 分页列出本项目的任务
    path('detail', request.detail_view, name='push_email_task_detail'),  # 查询单个任务
    path('update', request.update_view, name='push_email_task_update'),  # 修改任务（含启停）
    path('delete', request.delete_view, name='push_email_task_delete'),  # 删除任务（支持批量）
]
