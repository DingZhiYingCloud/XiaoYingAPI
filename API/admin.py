"""
API 应用管理后台配置

功能特性：
1. 智能自动配置 —— 根据模型字段类型自动生成 list_display / search_fields / list_filter 等
2. 自定义管理站点品牌 —— 站点标题、头部、名称定制
3. 增强稳定性与日志 —— 完善异常捕获与日志记录，避免静默失败
4. 模型统计仪表盘 —— 可视化展示各模型数据量与最近更新（访问 /admin/dashboard/）

所有功能均在本文件内实现，无需修改其它文件。
仪表盘访问地址：/admin/dashboard/
"""

import logging
import os

from django import forms
from django.apps import apps
from django.conf import settings
from django.contrib import admin, messages
from django.db import models
from django.forms import Media
from django.http import HttpResponse
from django.middleware.csrf import get_token
from django.shortcuts import redirect
from django.template import Context, Template
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from API.models import Feedback, FeedbackReply
from API.models.Auth.category import ApiCategory

logger = logging.getLogger(__name__)


# ============================================================
# 配置常量 —— 集中管理，避免重复定义（遵循"定义一次"原则）
# ============================================================

# 站点品牌配置
SITE_HEADER = '小影API管理后台'
SITE_TITLE = '小影API管理后台'
INDEX_TITLE = '欢迎使用小影API管理系统'

# 可加入搜索的字段类型（文本类字段）
SEARCH_FIELD_TYPES = (
    models.CharField,
    models.TextField,
    models.EmailField,
    models.URLField,
    models.SlugField,
    models.GenericIPAddressField,
)

# 可加入过滤器的字段类型
FILTER_FIELD_TYPES = (
    models.BooleanField,
    models.DateField,
    models.DateTimeField,
    models.ForeignKey,
)

# 可作为 date_hierarchy 的字段类型
DATE_HIERARCHY_TYPES = (
    models.DateField,
    models.DateTimeField,
)

# 不适合显示在 list_display 中的字段类型（大字段或多值字段）
HIDDEN_LIST_FIELD_TYPES = (
    models.ManyToManyField,
    models.TextField,
)

# BaseModel 中的时间字段（见 common/base.py），自动设为只读
TIME_FIELDS = ('create_time', 'updated_time')

# 分页配置：每页显示条数，避免一次加载过多数据
LIST_PER_PAGE = 20

# 仪表盘最近记录显示数量
DASHBOARD_RECENT_LIMIT = 5


def static_mtime_version(rel_path):
    """计算静态文件修改时间戳作为版本号（秒级），实现缓存破击强制刷新。

    文件更新后 mtime 自动变化，CSS/JS URL 的 ?v= 参数随之改变，
    浏览器将重新拉取最新资源，避免线上/本地样式不一致的缓存问题。
    文件缺失时返回 0，不阻断页面加载。
    """
    abs_path = os.path.join(apps.get_app_config('API').path, 'static', rel_path)
    try:
        return int(os.path.getmtime(abs_path))
    except OSError:
        return 0


# ============================================================
# 1. 管理站点品牌定制
# ============================================================

admin.site.site_header = SITE_HEADER
admin.site.site_title = SITE_TITLE
admin.site.index_title = INDEX_TITLE


# ============================================================
# 2. 智能 ModelAdmin 基类
# ============================================================

class SmartModelAdmin(admin.ModelAdmin):
    """
    智能 ModelAdmin 基类

    通用优化：
    - list_per_page: 合理分页，避免大表加载缓慢
    - show_full_result_count: 关闭全量计数（大表 COUNT(*) 较慢），提升搜索性能
    - 时间字段自动只读：防止误改创建/更新时间
    """

    list_per_page = LIST_PER_PAGE
    show_full_result_count = False

    def get_readonly_fields(self, request, obj=None):
        """时间字段自动只读，同时保留用户自定义的只读字段"""
        readonly = list(super().get_readonly_fields(request, obj))
        for field in TIME_FIELDS:
            if field not in readonly:
                readonly.append(field)
        return readonly


def create_smart_admin_class(model):
    """
    根据模型字段类型自动生成 ModelAdmin 子类

    自动配置项：
    - list_display: 显示所有合适字段（跳过 TextField / ManyToManyField 等大字段）
    - search_fields: 文本类字段加入搜索
    - list_filter: 布尔 / 日期 / 外键字段加入过滤器
    - list_select_related: 外键字段预加载，减少 N+1 查询
    - date_hierarchy: 优先使用 create_time 作为层级导航

    Args:
        model: Django 模型类

    Returns:
        配置好的 ModelAdmin 子类
    """
    meta = model._meta
    fields = meta.get_fields()

    list_display = ['__str__']
    search_fields = []
    list_filter = []
    select_related = []
    date_hierarchy = None

    for field in fields:
        # 跳过反向关系字段（非 concrete），只处理真实列
        if not getattr(field, 'concrete', False):
            continue

        field_name = field.name

        # list_display: 跳过不适合显示的大字段
        if not isinstance(field, HIDDEN_LIST_FIELD_TYPES):
            if field_name not in list_display:
                list_display.append(field_name)

        # search_fields: 文本类字段可搜索
        if isinstance(field, SEARCH_FIELD_TYPES):
            search_fields.append(field_name)

        # list_filter: 布尔 / 日期 / 外键字段可过滤
        if isinstance(field, FILTER_FIELD_TYPES):
            list_filter.append(field_name)
        # 带 choices 的字段也加入过滤器
        elif getattr(field, 'choices', None):
            list_filter.append(field_name)

        # list_select_related: 外键预加载，消除 N+1 查询
        if isinstance(field, models.ForeignKey):
            select_related.append(field_name)

        # date_hierarchy: 优先用 create_time
        if date_hierarchy is None and isinstance(field, DATE_HIERARCHY_TYPES):
            if field_name == 'create_time':
                date_hierarchy = field_name

    # 若未找到 create_time，回退到第一个日期字段
    if date_hierarchy is None:
        for field in fields:
            if getattr(field, 'concrete', False) and isinstance(field, DATE_HIERARCHY_TYPES):
                date_hierarchy = field.name
                break

    # 动态创建 ModelAdmin 子类
    attrs = {
        '__module__': __name__,
        'list_display': list_display,
        'search_fields': search_fields,
        'list_filter': list_filter,
        'list_select_related': select_related,
        'date_hierarchy': date_hierarchy,
    }
    return type(
        f'{model.__name__}Admin',
        (SmartModelAdmin,),
        attrs,
    )


# ============================================================
# 3. 模型统计仪表盘
# ============================================================

# 仪表盘内联模板（避免依赖外部模板文件，全部在 admin.py 内完成）
DASHBOARD_TEMPLATE = Template("""
<!DOCTYPE html>
<html lang="zh-hans">
<head>
    <meta charset="UTF-8">
    <title>数据仪表盘 - {{ site_header }}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, "Microsoft YaHei", sans-serif;
            background: #f5f5f5; padding: 20px; color: #333;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { margin-bottom: 20px; }
        .summary { display: flex; gap: 20px; margin-bottom: 30px; }
        .summary-card {
            background: #fff; padding: 24px; border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.08); flex: 1; text-align: center;
        }
        .summary-card .num { font-size: 32px; color: #417690; font-weight: bold; }
        .summary-card .label { color: #666; margin-top: 8px; }
        .section {
            background: #fff; border-radius: 8px; padding: 20px; margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.08);
        }
        .section h2 { margin-bottom: 16px; font-size: 18px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #eee; }
        th { color: #666; font-weight: 600; }
        .back-link {
            display: inline-block; margin-bottom: 20px;
            color: #417690; text-decoration: none;
        }
        .badge {
            background: #417690; color: #fff; padding: 2px 8px;
            border-radius: 10px; font-size: 12px; margin-left: 6px;
        }
        .empty { color: #999; text-align: center; padding: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <a href="/admin/" class="back-link">← 返回管理后台</a>
        <h1>数据仪表盘</h1>

        <div class="summary">
            <div class="summary-card">
                <div class="num">{{ model_count }}</div>
                <div class="label">模型总数</div>
            </div>
            <div class="summary-card">
                <div class="num">{{ total_records }}</div>
                <div class="label">记录总数</div>
            </div>
        </div>

        <div class="section">
            <h2>各模型数据量统计</h2>
            <table>
                <thead>
                    <tr><th>模型名称</th><th>记录数</th></tr>
                </thead>
                <tbody>
                    {% for item in stats %}
                    <tr>
                        <td>{{ item.name }}<span class="badge">{{ item.object_name }}</span></td>
                        <td>{{ item.count }}</td>
                    </tr>
                    {% empty %}
                    <tr><td colspan="2" class="empty">暂无模型数据</td></tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>

        {% if recent_records %}
        <div class="section">
            <h2>最近更新记录</h2>
            <table>
                <thead>
                    <tr><th>模型</th><th>对象</th><th>更新时间</th></tr>
                </thead>
                <tbody>
                    {% for record in recent_records %}
                    <tr>
                        <td>{{ record.model }}</td>
                        <td>{{ record.object }}</td>
                        <td>{{ record.time|date:"Y-m-d H:i:s" }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% endif %}
    </div>
</body>
</html>
""")


def dashboard_view(request):
    """
    模型统计仪表盘视图

    展示内容：
    - 各已注册模型的数据量统计
    - 最近更新的记录（针对有 updated_time 字段的模型）
    - 模型总数、记录总数汇总

    性能优化：
    - 使用 count() 而非 len() 统计（COUNT 查询）
    - 限制最近记录查询数量（[:DASHBOARD_RECENT_LIMIT]）
    - 仅查询有 updated_time 字段的模型
    """
    # 权限校验：仅 staff 用户可访问（admin_view 装饰器已校验登录，这里补充 staff 校验）
    if not request.user.is_staff:
        return HttpResponse('权限不足', status=403)

    stats = []
    total_records = 0
    recent_records = []

    try:
        app_config = apps.get_app_config('API')
    except LookupError:
        logger.error('仪表盘: API 应用未找到')
        return HttpResponse('应用未找到', status=500)

    for model in app_config.get_models():
        model_name = model.__name__
        try:
            meta = model._meta
            # 使用 count() 而非 len()，走数据库 COUNT 聚合
            count = model._default_manager.count()
            total_records += count

            stats.append({
                'name': str(meta.verbose_name),
                'object_name': meta.object_name,
                'count': count,
            })

            # 查询最近更新的记录（仅针对有 updated_time 字段的模型）
            if hasattr(model, 'updated_time'):
                recent = model._default_manager.order_by('-updated_time')[:DASHBOARD_RECENT_LIMIT]
                for obj in recent:
                    recent_records.append({
                        'model': str(meta.verbose_name),
                        'object': str(obj),
                        'time': getattr(obj, 'updated_time', None),
                    })
        except Exception as e:
            logger.warning('仪表盘统计模型 %s 失败: %s', model_name, e, exc_info=True)

    # 按更新时间倒序排列（None 值排到末尾），取前 N 条
    recent_records.sort(
        key=lambda x: x['time'] if x['time'] is not None else 0,
        reverse=True,
    )
    recent_records = recent_records[:DASHBOARD_RECENT_LIMIT * 2]

    context = Context({
        'site_header': SITE_HEADER,
        'model_count': len(stats),
        'total_records': total_records,
        'stats': stats,
        'recent_records': recent_records,
    })

    return HttpResponse(DASHBOARD_TEMPLATE.render(context))


# 为默认 admin.site 添加仪表盘 URL（monkey-patch get_urls，无需修改 urls.py）
_original_get_urls = admin.site.get_urls


def _custom_get_urls():
    """扩展 admin 站点 URL，添加仪表盘路由"""
    urls = _original_get_urls()
    custom_urls = [
        path('dashboard/', admin.site.admin_view(dashboard_view), name='dashboard'),
    ]
    return custom_urls + urls


admin.site.get_urls = _custom_get_urls


# ============================================================
# 3.5 API 服务分类（分类树）专属后台
# ============================================================

class ApiCategoryAdmin(SmartModelAdmin):
    """API 服务分类：树形层级展示 + 认证模式醒目显示

    层级与后端 API/apis/ 目录一致（同 Apifox 文件夹）；认证模式三态：
    inherit=跟随上级 / auth=需要认证 / open=开放。

    样式固化在应用内 static（API/admin/apicategory_admin.css），
    collectstatic 自动收集，不依赖 simpleui 包内文件，重装 UI 后效果不丢失。
    """

    list_display = ('indented_name', 'path_prefix', 'auth_mode_tag', 'status_tag', 'create_time')
    list_filter = ('auth_mode', 'status')
    search_fields = ('name', 'path_prefix')
    ordering = ('path_prefix',)

    @property
    def media(self):
        """CSS/JS 动态注入：URL 附加文件 mtime 版本号，更新后强制浏览器刷新"""
        css_url = f'{settings.STATIC_URL}API/admin/apicategory_admin.css?v={static_mtime_version("API/admin/apicategory_admin.css")}'
        js_url = f'{settings.STATIC_URL}API/admin/apicategory_admin.js?v={static_mtime_version("API/admin/apicategory_admin.js")}'
        return super().media + Media(css={'all': (css_url,)}, js=(js_url,))

    @staticmethod
    def _depth(obj):
        """计算分类节点的层级深度（一级=0）"""
        depth = 0
        node = obj
        while node.parent_id:
            depth += 1
            node = node.parent
        return depth

    @admin.display(description='分类名称')
    def indented_name(self, obj):
        """按层级输出树形结构：缩进 + 引导线 + 层级底色"""
        depth = self._depth(obj)
        guide = mark_safe('<span class="tree-guide">└─</span>') if depth else ''
        return format_html(
            '<span class="apicat-tree depth-{depth}">{guide}{name}</span>',
            depth=depth, guide=guide, name=obj.name,
        )

    @admin.display(description='认证模式')
    def auth_mode_tag(self, obj):
        """认证模式彩色标签：inherit=灰 / auth=红 / open=绿"""
        label = dict(ApiCategory.AUTH_MODE_CHOICES).get(obj.auth_mode, obj.auth_mode)
        return format_html(
            '<span class="apicat-mode mode-{mode}">{label}</span>',
            mode=obj.auth_mode, label=label,
        )

    @admin.display(description='启用')
    def status_tag(self, obj):
        """启用状态圆点：绿=启用 / 灰=停用"""
        return format_html(
            '<span class="apicat-status status-{state}"></span>',
            state='on' if obj.status else 'off',
        )


admin.site.register(ApiCategory, ApiCategoryAdmin)


# ============================================================
# 3.6 问题反馈中心专属后台（站长统一广场）
# ============================================================

# 反馈状态彩色标签样式（与 Feedback.STATUS_CHOICES 对应）
FEEDBACK_STATUS_STYLE = {
    'pending': '#e6a23c',    # 待处理：橙
    'processing': '#409eff', # 处理中：蓝
    'resolved': '#67c23a',   # 已解决：绿
    'closed': '#909399',     # 已关闭：灰
}

# 评论展示配置（评论树预览 + 分页，防止海量评论撑爆详情页）
FEEDBACK_PREVIEW_LIMIT = 10       # 详情页评论树预览条数，超出折叠至评论管理页
FEEDBACK_REPLIES_PAGE_SIZE = 20   # 评论管理页每页条数（默认 20 / 页）


def _fb_display_name(reply):
    """评论者展示名（用户名 / 站长）"""
    return reply.user.username if reply.user else '站长'


def _fb_role_badge(reply):
    """身份徽章：admin=站长（红）/ user=子项目用户（蓝）"""
    label = '站长' if reply.author_role == 'admin' else '用户'
    return format_html('<span class="fb-badge role-{role}">{label}</span>',
                       role=reply.author_role, label=label)


def _fb_comment_card(reply, reply_to_name=None, extra_actions=''):
    """单条评论卡片（统一样式；content 经 format_html 自动转义，防 XSS）

    reply_to_name: 被回复者展示名（None=不展示回复关系，用于详情页评论树；
                   空字符串=回复问题本身）
    extra_actions: 额外操作区 HTML（如删除按钮，由调用方保证安全）
    """
    time_str = timezone.localtime(reply.create_time).strftime('%Y-%m-%d %H:%M')
    reply_to = ''
    if reply_to_name is not None:
        target = f'@{reply_to_name}' if reply_to_name else '问题本身'
        reply_to = format_html('<span class="fb-reply-to">回复 {}</span>', target)
    return format_html(
        '<div class="fb-comment role-{role}">'
        '<div class="fb-head">{badge}<span class="fb-name">{name}</span>{reply_to}'
        '<span class="fb-time">{time}</span></div>'
        '<div class="fb-content">{content}</div>'
        '<div class="fb-actions">{extra}</div>'
        '</div>',
        role=reply.author_role,
        badge=_fb_role_badge(reply),
        name=_fb_display_name(reply),
        reply_to=reply_to,
        time=time_str,
        content=reply.content,
        extra=mark_safe(extra_actions),
    )


def _fb_tree_preview_html(replies):
    """评论树预览：按嵌套缩进渲染前 N 条（时间正序，与 API「二级评论=全部子孙」
    语义一致），超出 FEEDBACK_PREVIEW_LIMIT 截断"""
    children = {}
    for r in replies:
        children.setdefault(r.parent_id, []).append(r)

    parts = []
    count = 0

    def render(parent_id):
        nonlocal count
        for r in children.get(parent_id, ()):
            if count >= FEEDBACK_PREVIEW_LIMIT:
                return
            count += 1
            parts.append(_fb_comment_card(r))
            if children.get(r.id):
                parts.append(mark_safe('<div class="fb-children">'))
                render(r.id)
                parts.append(mark_safe('</div>'))

    render(None)
    return mark_safe(''.join(str(p) for p in parts))


class FeedbackAdmin(SmartModelAdmin):
    """问题反馈管理（站长统一广场：集中查看所有子项目反馈）

    支持：按项目 / 状态 / 时间筛选、按标题内容用户搜索、状态流转、
    详情页评论树预览（前 N 条）、独立评论管理页（分页 + 站长回复 + 删除）。
    """

    list_display = ('title', 'app', 'status_tag', 'user', 'reply_count', 'create_time')
    list_filter = ('app', 'status', 'create_time')
    search_fields = ('title', 'content', 'user__username', 'user__account')
    list_select_related = ('app', 'user')
    date_hierarchy = 'create_time'
    readonly_fields = ('app', 'user', 'create_time', 'updated_time', 'replies_preview')
    fieldsets = (
        (None, {
            'fields': ('app', 'user', 'title', 'content', 'status', 'replies_preview'),
        }),
        ('时间信息', {
            'classes': ('collapse',),
            'fields': ('create_time', 'updated_time'),
        }),
    )

    @property
    def media(self):
        """评论样式注入：URL 附加文件 mtime 版本号，更新后强制浏览器刷新"""
        css_url = f'{settings.STATIC_URL}API/admin/feedback_admin.css?v={static_mtime_version("API/admin/feedback_admin.css")}'
        return super().media + Media(css={'all': (css_url,)})

    # ---------- 列表展示 ----------

    @admin.display(description='状态')
    def status_tag(self, obj):
        """状态彩色标签：待处理=橙 / 处理中=蓝 / 已解决=绿 / 已关闭=灰"""
        color = FEEDBACK_STATUS_STYLE.get(obj.status, '#909399')
        return format_html(
            '<span style="color:#fff;background:{color};padding:2px 10px;'
            'border-radius:10px;font-size:12px;">{label}</span>',
            color=color, label=obj.get_status_display(),
        )

    @admin.display(description='追加数')
    def reply_count(self, obj):
        """追加数量（含站长回复）"""
        return obj.reply_count

    # ---------- 详情页评论树预览（只读，替代原内联表格） ----------

    @admin.display(description='评论')
    def replies_preview(self, obj):
        """详情页只读评论树：嵌套缩进 + 身份徽章，只渲染前 N 条防止撑爆页面；
        全部评论通过「评论管理页」分页查看与回复"""
        if obj is None or obj.pk is None:
            return '反馈保存后可在此查看评论树'
        replies = list(obj.replies.select_related('user'))
        if not replies:
            return '暂无评论'
        link = reverse('admin:feedback_replies', args=[obj.pk])
        head = format_html(
            '<div class="fb-comments-head"><span>评论树（时间正序，前 {} 条）</span>'
            '<a class="fb-more" href="{}">评论管理 / 站长回复 →</a></div>',
            min(len(replies), FEEDBACK_PREVIEW_LIMIT), link)
        more = ''
        if len(replies) > FEEDBACK_PREVIEW_LIMIT:
            more = format_html(
                '<div class="fb-preview-more">…其余 {} 条未展示，'
                '请进入 <a href="{}">评论管理</a> 分页查看</div>',
                len(replies) - FEEDBACK_PREVIEW_LIMIT, link)
        return format_html('<div class="fb-comments">{}{}{}</div>',
                           head, _fb_tree_preview_html(replies), more)

    # ---------- 评论管理页（分页 + 站长回复 + 删除） ----------

    def get_urls(self):
        """扩展反馈管理路由：/admin/API/feedback/<id>/replies/ 评论管理页"""
        urls = super().get_urls()
        custom = [
            path('<uuid:object_id>/replies/', self.admin_site.admin_view(self.replies_page),
                 name='feedback_replies'),
        ]
        return custom + urls

    @staticmethod
    def _normalize_page(raw, total_pages=1):
        """页码归一化：非数字 → 1，越界 → 边界值，不报错"""
        try:
            page = int(raw)
        except (TypeError, ValueError):
            page = 1
        return max(1, min(page, total_pages))

    def replies_page(self, request, object_id):
        """评论管理页：全部评论按时间正序分页（一级+二级平铺，标注"回复了谁"，
        与 API 二级评论语义一致）；站长可回复问题本身或任意评论（含深层），
        仅 superuser 可删除（级联删除其全部子孙回复）"""
        obj = self.get_object(request, str(object_id))
        if obj is None:
            return HttpResponse('反馈不存在', status=404)
        base_url = reverse('admin:feedback_replies', args=[obj.pk])

        # ---- POST：发布回复 / 删除评论 ----
        if request.method == 'POST':
            page = self._normalize_page(request.POST.get('page'))
            action = request.POST.get('action')
            if action == 'reply':
                content = (request.POST.get('content') or '').strip()
                parent_id = request.POST.get('parent_id') or ''
                parent = None
                if parent_id:
                    parent = FeedbackReply.objects.filter(id=parent_id, feedback=obj).first()
                if not content:
                    messages.error(request, '回复内容不能为空')
                elif parent_id and parent is None:
                    messages.error(request, '父评论不存在或不属于当前反馈')
                else:
                    FeedbackReply.objects.create(
                        feedback=obj, parent=parent,
                        author_role='admin', user=None, content=content)
                    messages.success(request, '回复已发布')
            elif action == 'delete':
                if not request.user.is_superuser:
                    messages.error(request, '仅站长（superuser）可删除评论')
                    return redirect(f'{base_url}?page={page}')
                target = FeedbackReply.objects.filter(
                    id=request.POST.get('reply_id'), feedback=obj).first()
                if target is None:
                    messages.error(request, '评论不存在或不属于当前反馈')
                else:
                    target.delete()  # 级联删除其全部子孙回复
                    messages.success(request, '评论已删除（含其全部子孙回复）')
            return redirect(f'{base_url}?page={page}')

        # ---- GET：渲染评论管理页 ----
        replies = list(obj.replies.select_related('user'))
        total = len(replies)
        total_pages = max(1, (total + FEEDBACK_REPLIES_PAGE_SIZE - 1) // FEEDBACK_REPLIES_PAGE_SIZE)
        page = self._normalize_page(request.GET.get('page'), total_pages)
        page_replies = replies[(page - 1) * FEEDBACK_REPLIES_PAGE_SIZE: page * FEEDBACK_REPLIES_PAGE_SIZE]

        # 评论者名称映射（当前页"回复了谁"标注用）
        name_map = {str(r.id): _fb_display_name(r) for r in replies}
        csrf = get_token(request)

        parts = []
        parts.append(format_html(
            '<!DOCTYPE html><html lang="zh-hans"><head><meta charset="UTF-8">'
            '<title>评论管理 - {title}</title>'
            '<link rel="stylesheet" href="{css}"></head><body><div class="fb-page">',
            title=obj.title,
            css=f'{settings.STATIC_URL}API/admin/feedback_admin.css?v={static_mtime_version("API/admin/feedback_admin.css")}',
        ))
        parts.append(format_html('<a class="fb-back" href="{}">← 返回反馈详情</a>',
                                 reverse('admin:API_feedback_change', args=[obj.pk])))
        parts.append(format_html('<h1 class="fb-title">{}</h1>', obj.title))
        parts.append(format_html('<div class="fb-sub">{} · 状态：{} · 共 {} 条评论</div>',
                                 obj.app, obj.get_status_display(), total))

        # 操作结果提示
        for m in messages.get_messages(request):
            parts.append(format_html('<div class="fb-msg {}">{}</div>', m.tags, m))

        # 站长回复表单（父评论下拉 = 当前反馈全部评论，按时间正序）
        options = ['<option value="">回复问题本身（一级评论）</option>']
        for r in replies:
            options.append(format_html('<option value="{}">回复 @{}：{}</option>',
                                       r.id, _fb_display_name(r), r.content[:20]))
        parts.append(format_html(
            '<form method="post" action="{}" class="fb-form">'
            '<input type="hidden" name="csrfmiddlewaretoken" value="{}">'
            '<input type="hidden" name="action" value="reply">'
            '<input type="hidden" name="page" value="{}">'
            '<h3>站长回复</h3>'
            '<select name="parent_id">{}</select>'
            '<textarea name="content" placeholder="回复内容（纯文本）"></textarea>'
            '<button type="submit">发布回复</button>'
            '</form>',
            base_url, csrf, page, mark_safe(''.join(str(o) for o in options)),
        ))

        # 当前页评论列表
        if page_replies:
            for r in page_replies:
                actions = ''
                if request.user.is_superuser:
                    actions = format_html(
                        '<form method="post" action="{}" class="fb-del" '
                        'onsubmit="return confirm(\'删除该评论及其全部子孙回复？\')">'
                        '<input type="hidden" name="csrfmiddlewaretoken" value="{}">'
                        '<input type="hidden" name="action" value="delete">'
                        '<input type="hidden" name="reply_id" value="{}">'
                        '<input type="hidden" name="page" value="{}">'
                        '<button type="submit">删除</button></form>',
                        base_url, csrf, r.id, page)
                parent_name = name_map.get(str(r.parent_id), '') if r.parent_id else ''
                parts.append(_fb_comment_card(r, reply_to_name=parent_name, extra_actions=actions))
        else:
            parts.append(mark_safe('<div class="fb-empty">暂无评论</div>'))

        # 分页条
        prev = format_html('<a href="{}?page={}">← 上一页</a>', base_url, page - 1) if page > 1 \
            else mark_safe('<span class="fb-disabled">← 上一页</span>')
        nxt = format_html('<a href="{}?page={}">下一页 →</a>', base_url, page + 1) if page < total_pages \
            else mark_safe('<span class="fb-disabled">下一页 →</span>')
        parts.append(format_html('<div class="fb-pager">{}<span>第 {} / {} 页（共 {} 条）</span>{}</div>',
                                 prev, page, total_pages, total, nxt))

        parts.append(mark_safe('</div></body></html>'))
        return HttpResponse(''.join(str(p) for p in parts))

    def has_delete_permission(self, request, obj=None):
        """仅站长（superuser）可删除反馈与追加"""
        return request.user.is_superuser


admin.site.register(Feedback, FeedbackAdmin)


# ============================================================
# 4. 自动注册模型 —— 带异常处理与日志
# ============================================================

def _register_models():
    """
    自动注册 API 应用下所有模型到 admin 站点

    策略：
    - 为每个模型自动生成 SmartModelAdmin 配置
    - 已注册的模型跳过（避免 AlreadyRegistered 异常）
    - 捕获并记录所有异常，避免单个模型注册失败影响整体

    日志级别：
    - 成功注册：DEBUG
    - 跳过已注册：INFO
    - 注册失败：ERROR
    """
    try:
        app_config = apps.get_app_config('API')
    except LookupError:
        logger.error('自动注册: API 应用未找到，跳过注册')
        return

    registered_count = 0
    skipped_count = 0
    failed_count = 0

    for model in app_config.get_models():
        model_name = model.__name__
        try:
            # 检查是否已注册（避免依赖异常控制流）
            if model in admin.site._registry:
                logger.info('模型 %s 已注册，跳过', model_name)
                skipped_count += 1
                continue

            # 创建智能 Admin 类并注册
            admin_class = create_smart_admin_class(model)
            admin.site.register(model, admin_class)
            logger.debug('模型 %s 注册成功', model_name)
            registered_count += 1

        except admin.sites.AlreadyRegistered:
            logger.info('模型 %s 已被注册，跳过', model_name)
            skipped_count += 1
        except Exception as e:
            # 捕获所有异常，避免单个模型失败影响其它模型注册
            logger.error('模型 %s 注册失败: %s', model_name, e, exc_info=True)
            failed_count += 1

    logger.info(
        '模型注册完成: 成功 %d, 跳过 %d, 失败 %d',
        registered_count, skipped_count, failed_count,
    )


# 执行自动注册
_register_models()
