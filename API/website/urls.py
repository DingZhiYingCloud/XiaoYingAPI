"""官网前台路由（挂载在站点根路径下）"""
from django.urls import path
from django.views.generic import TemplateView
from django.views.i18n import JavaScriptCatalog

from . import console, console_users, docs_views, programs_views, views

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

    # SEO：robots.txt 与站点地图（robots.txt 内声明的 Sitemap 地址即 /sitemap.xml）
    path('robots.txt', TemplateView.as_view(template_name='robots.txt', content_type='text/plain'),
         name='robots_txt'),
    path('sitemap.xml', views.sitemap_view, name='sitemap'),

    # API 文档中心
    path('docs/', docs_views.index, name='docs_index'),        # 文档目录
    path('docs/_call/', docs_views.call, name='docs_call'),    # 在线调试代调（白名单）
    path('docs/<str:slug>/', docs_views.service, name='docs_service'),  # 单服务文档页

    # 计算程序模块（内容取自 settings.PROGRAMS_ROOT 目录树）
    # 注意：download / content 必须排在 <path:rel> 之前，否则会被详情路由抢先匹配
    path('programs/', programs_views.index, name='programs_index'),          # 程序列表
    path('programs/download/', programs_views.download, name='programs_download'),  # 文件 / 整包下载
    path('programs/content/', programs_views.content, name='programs_content'),     # 文件在线预览
    path('programs/<path:rel>/', programs_views.detail, name='programs_detail'),    # 程序详情

    # 超级管理员控制台（服务端 is_superuser 二次鉴权；超管在 /login/ 登录后即可访问）
    path('console/', console.home_view, name='console_home'),                    # 控制台首页（侧栏导航 + 概览）
    path('console/projects/', console.projects_view, name='console_projects'),   # 接入项目管理
    path('console/services/', console.services_view, name='console_services'),   # API 服务策略（服务/线路/端点三级继承）
    path('console/stats/', console.stats_view, name='console_stats'),           # API 调用统计看板
    # 用户管理（超管专属）
    path('console/users/', console_users.users_view, name='console_users'),     # 用户列表（搜索/筛选/分页/写操作）
    path('console/users/<uuid:user_id>/', console_users.user_detail_view,
         name='console_user_detail'),                                           # 用户详情（登录明细）
    # 调用统计详情页（服务前缀 / APPID 作为路径参数，必须排在 console/stats/ 之后）
    path('console/stats/service/<path:service>/', console.stats_service_view,
         name='console_stats_service'),                                          # 单服务统计详情
    path('console/stats/app/<str:app_id>/', console.stats_app_view,
         name='console_stats_app'),                                              # 单项目统计详情
]
