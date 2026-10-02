"""官网前台路由（挂载在站点根路径下）"""
from django.urls import path
from django.views.generic import TemplateView
from django.views.i18n import JavaScriptCatalog

from . import (console, console_ai, console_announcements, console_appearance,
               console_audit, console_credits, console_feedback, console_haijiao,
               console_pay, console_prices, console_quota, console_security,
               console_upstream, console_users, docs_views, feedback_views,
               my_projects, my_wallet, programs_views, views)
# 第三方支付的异步通知：必须挂在 /api/ 之外（平台回调带不了我们的项目签名，靠平台公钥验签）
from API.apis.pay.notify import notify_view as pay_notify_view

app_name = 'website'

urlpatterns = [
    path('', views.index, name='index'),                       # 官网首页
    path('pay/notify/<str:code>/', pay_notify_view, name='pay_notify'),  # 第三方支付异步通知（免签名）
    path('guide/', views.guide_view, name='guide'),            # 接入向导
    # 服务配套工具页：按「/<服务>/post/」归到所属服务命名空间，避免各服务的工具页在根路径上撞车
    path('haijiao/post/', views.haijiao_post_view, name='haijiao_post'),  # 海角社区发帖页
    path('login/', views.login_view, name='login'),            # 登录页 / 登录动作
    path('login/send-code/', views.login_send_code_view, name='login_send_code'),
    path('register/', views.register_view, name='register'),   # 注册页 / 两步注册第一步
    path('register/verify/', views.register_verify_view, name='register_verify'),
    path('register/resend/', views.register_resend_view, name='register_resend'),
    path('reset-password/', views.reset_password_view, name='reset_password'),            # 忘记密码：页面 / 发送重置验证码
    path('reset-password/submit/', views.reset_password_submit_view, name='reset_password_submit'),  # 重置密码提交
    path('logout/', views.logout_view, name='logout'),         # 退出
    # 我的项目（接入方自助）：登录后管理自己名下的接入项目（列表 / 详情 / 自助建项目 / 重置密钥）
    path('my/projects/', my_projects.projects_view, name='my_projects'),
    path('my/projects/<uuid:app_id>/', my_projects.project_detail_view,
         name='my_project_detail'),
    # 充值中心（登录用户）：在线充值到账户余额 + 余额兑换成项目点数
    path('my/wallet/', my_wallet.wallet_view, name='my_wallet'),
    path('lang/', views.set_language, name='set_language'),    # 语言切换（?lang=xx&next=...）
    # JS 端多语言目录：提供 window.gettext() 等函数，文案取自 locale/*/LC_MESSAGES/djangojs.mo
    # （仅下发前端 JS 用到的词条，不把整份服务端词条目录发给浏览器）
    path('jsi18n/', JavaScriptCatalog.as_view(), name='javascript-catalog'),

    # SEO：robots.txt 与站点地图（robots.txt 内声明的 Sitemap 地址即 /sitemap.xml）
    path('robots.txt', TemplateView.as_view(template_name='robots.txt', content_type='text/plain'),
         name='robots_txt'),
    path('sitemap.xml', views.sitemap_view, name='sitemap'),

    # 问题反馈中心（我们托管，子项目放链接 / iframe 即可接入；详见 feedback_views 模块说明）
    # /feedback/ 是本站自用入口：重定向到官网接入项目那条反馈页（APPID 不写进模板）
    path('feedback/', feedback_views.feedback_self, name='feedback_self'),
    path('feedback/<str:app_id>/', feedback_views.feedback_home, name='feedback'),
    path('feedback/<str:app_id>/public/', feedback_views.feedback_public, name='feedback_public'),
    path('feedback/<str:app_id>/my/', feedback_views.feedback_mine, name='feedback_mine'),
    path('feedback/<str:app_id>/detail/<uuid:feedback_id>/', feedback_views.feedback_detail,
         name='feedback_detail'),

    # API 文档中心
    path('docs/', docs_views.index, name='docs_index'),        # 文档目录
    path('docs/_call/', docs_views.call, name='docs_call'),    # 在线调试代调（白名单）
    path('docs/errors/', docs_views.errors, name='docs_errors'),  # 错误码总表（须排在 <slug> 之前）
    # 「鉴权设置」下拉的数据源（当前访客名下 / 超管可见的接入项目，含密钥；须排在 <slug> 之前）
    path('docs/_projects/', docs_views.my_projects, name='docs_my_projects'),
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
    # 线路价格（超管专属）：按服务 / 线路 / 端点三级设置调用单价（点/次），与服务策略解耦
    path('console/prices/', console_prices.prices_view, name='console_prices'),
    # 项目额度（超管专属）：按项目查看余额 / 充值（含充值流水）；目前无支付，只能手动充
    path('console/credits/', console_credits.credits_view, name='console_credits'),
    # 支付设置（超管专属）：在线支付开关与汇率、各渠道商户配置、订单查单 / 退款
    path('console/pay/', console_pay.pay_view, name='console_pay'),
    path('console/stats/', console.stats_view, name='console_stats'),           # API 调用统计看板
    # 接口公告（超管专属）：给服务 / 线路 / 端点三级发布公告，前台文档中心展示
    path('console/announcements/', console_announcements.announcements_view,
         name='console_announcements'),
    # AI 模型（超管专属）：AI 厂商与模型维护，驱动 /api/ai/ 的模型切换
    path('console/ai/models/', console_ai.ai_models_view, name='console_ai_models'),
    # 官网外观（超管专属）：切换首页 / 文档中心的视觉气质与首页 Hero 文案
    path('console/appearance/', console_appearance.appearance_view,
         name='console_appearance'),
    # 安全设置（超管专属）：控制台自身的安全开关（后台入口隐身等）
    path('console/security/', console_security.security_view, name='console_security'),
    # 操作日志（超管专属）：控制台写操作的审计留痕（采集见 admin_auth.superadmin_required）
    path('console/audit/', console_audit.audit_view, name='console_audit'),
    # 问题反馈中心（超管专属）：反馈处理（筛选/回复/AI 送审）与全局设置（含类型字典）
    path('console/feedback/settings/', console_feedback.feedback_settings_view,
         name='console_feedback_settings'),
    path('console/feedback/', console_feedback.feedback_view, name='console_feedback'),
    # 开发者联系方式（超管专属）：联系方式平台字典 + 各项目联系方式，供反馈页与 /api/feedback/contacts 使用
    path('console/contacts/', console_feedback.contacts_view, name='console_contacts'),
    # 用户管理（超管专属）
    path('console/users/', console_users.users_view, name='console_users'),     # 用户列表（搜索/筛选/分页/写操作）
    path('console/users/<uuid:user_id>/', console_users.user_detail_view,
         name='console_user_detail'),                                           # 用户详情（登录明细）
    # 调用统计详情页（服务前缀 / APPID 作为路径参数，必须排在 console/stats/ 之后）
    path('console/stats/service/<path:service>/', console.stats_service_view,
         name='console_stats_service'),                                          # 单服务统计详情
    path('console/stats/app/<str:app_id>/', console.stats_app_view,
         name='console_stats_app'),                                              # 单项目统计详情
    path('console/haijiao/register/', console_haijiao.haijiao_register_view,
         name='console_haijiao_register'),                                       # 海角自动注册（超管）
    path('console/haijiao/register/ticket/', console_haijiao.haijiao_register_ticket_view,
         name='console_haijiao_register_ticket'),                                # 领一次性运行票据
    path('console/haijiao/register/refresh-domain/',
         console_haijiao.haijiao_register_domain_refresh_view,
         name='console_haijiao_register_refresh_domain'),                        # 更新今日域名（超管）
    path('console/haijiao/register/stream/', console_haijiao.haijiao_register_stream_view,
         name='console_haijiao_register_stream'),                                # 自动注册进度流（SSE）
    # 服务余量（超管专属）：上游服务账号余量监控 + 低量邮件告警配置
    path('console/quotas/', console_quota.quotas_view, name='console_quotas'),
    # 上游故障告警（超管专属）：按服务监控上游调用失败率（4xxxx 错误码）+ 超阈值邮件告警
    path('console/upstreams/', console_upstream.upstreams_view, name='console_upstreams'),
]
