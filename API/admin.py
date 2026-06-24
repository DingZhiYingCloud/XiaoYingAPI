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

from django.apps import apps
from django.contrib import admin
from django.db import models
from django.http import HttpResponse
from django.template import Context, Template
from django.urls import path

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
