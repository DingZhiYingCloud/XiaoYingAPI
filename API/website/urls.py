"""官网前台路由（挂载在站点根路径下）"""
from django.urls import path
from django.views.i18n import JavaScriptCatalog

from . import console, docs_views, views

app_name = 'website'

urlpatterns = [
    path('', views.index, name='index'),                       # 官网首页
    path('guide/', views.guide_view, name='guide'),            # 接入向导
    path('login/', views.login_view, name='login'),            # 登录页 / 登录动作
    path('login/send-code/', views.login_send_code_view, name='login_send_code'),
    path('register/', views.register_view, name='register'),   # 注册页 / 两步注册第一步
    path('register/verify/', views.register_verify_view, name='register_verify'),
    path('register/resend/', views.register_resend_view, name='register_resend'),
    path('reset-password/', views.reset_password_view, name='reset_password'),            # 忘记密码：页面 / 发送重置验证码
    path('reset-password/submit/', views.reset_password_submit_view, name='reset_password_submit'),  # 重置密码提交
    path('logout/', views.logout_view, name='logout'),         # 退出
    path('lang/', views.set_language, name='set_language'),    # 语言切换（?lang=xx&next=...）
    # JS 端多语言目录：提供 window.gettext() 等函数，文案取自 locale/*/LC_MESSAGES/djangojs.mo
    # （仅下发前端 JS 用到的词条，不把整份服务端词条目录发给浏览器）
    path('jsi18n/', JavaScriptCatalog.as_view(), name='javascript-catalog'),

    # API 文档中心
    path('docs/', docs_views.index, name='docs_index'),        # 文档目录
    path('docs/_call/', docs_views.call, name='docs_call'),    # 在线调试代调（白名单）
    path('docs/<str:slug>/', docs_views.service, name='docs_service'),  # 单服务文档页

    # 超级管理员控制台（服务端 is_superuser 二次鉴权；超管在 /login/ 登录后即可访问）
    path('console/projects/', console.projects_view, name='console_projects'),   # 接入项目管理
    path('console/categories/', console.categories_view, name='console_categories'),  # API 服务分类认证模式
    path('console/stats/', console.stats_view, name='console_stats'),           # API 调用统计看板
    path('console/services/api/', console.services_api, name='console_services_api'),  # 侧栏“服务设置”弹窗 API
]
