# 手工数据迁移：反馈中心初始数据
#
# 建表（0041 / 0042）之后必须补齐的最小可用数据：
#   1. 预置 5 个反馈类型（功能建议 / 功能升级 / 使用问题 / BUG 反馈 / 其他）
#   2. 建出反馈中心设置单例（不建的话后台设置页第一次访问才创建，配置项会「看起来没保存」）
#   3. 预置常用联系方式平台（QQ / QQ 邮箱 / 微信 / Telegram / 邮箱 / WhatsApp / Discord）
#      —— 只建平台字典，**不预置任何项目的值**，因此前台在管理员填值前不会展示联系方式
#   4. 服务策略：反馈中心服务本身仍需项目签名；但两个「给子项目前端直接用」的端点必须开放
#      —— `POST /api/feedback/ticket`（用用户 Token 换一次性票据）
#         与 `GET /api/feedback/contacts?app_id=xxx`（查某项目的开发者联系方式）
#      这两个端点如果不设 open，子项目前端就得持有 AppSecret 才能调用，与「零代码接入」冲突。
from django.db import migrations

FEEDBACK_TYPES = (
    # code, name, desc, icon, is_default, sort
    ('suggestion', '功能建议', '希望增加或改进某个功能', 'lightbulb', True, 10),
    ('upgrade', '功能升级', '已有功能需要增强或调整', 'trending-up', False, 20),
    ('issue', '使用问题', '使用过程中遇到疑问或异常', 'circle-help', False, 30),
    ('bug', 'BUG 反馈', '功能与文档描述不一致、报错或数据错误', 'bug', False, 40),
    ('other', '其他', '不属于以上任何类型', 'message-square', False, 50),
)

CONTACT_PLATFORMS = (
    # code, name, icon, value_label, url_template, sort
    ('qq', 'QQ', 'message-circle', 'QQ 号', '', 10),
    ('qqmail', 'QQ 邮箱', 'mail', 'QQ 邮箱地址', 'mailto:{value}', 20),
    ('wechat', '微信', 'message-square', '微信号', '', 30),
    ('telegram', 'Telegram', 'send', '用户名（不含 @）', 'https://t.me/{value}', 40),
    ('email', '邮箱', 'mail', '邮箱地址', 'mailto:{value}', 50),
    ('whatsapp', 'WhatsApp', 'phone', '手机号（含国家区号）', 'https://wa.me/{value}', 60),
    ('discord', 'Discord', 'gamepad-2', '用户名', '', 70),
)

# 服务策略：(路径前缀, 名称, 级别, 认证方式)
SERVICE_POLICIES = (
    ('/api/feedback/', '问题反馈中心', 'service', 'auth'),
    ('/api/feedback/ticket', '问题反馈中心 · 换一次性票据（子项目前端直调）', 'endpoint', 'open'),
    ('/api/feedback/contacts', '问题反馈中心 · 查开发者联系方式（子项目直调）', 'endpoint', 'open'),
)


def seed(apps, schema_editor):
    FeedbackType = apps.get_model('API', 'FeedbackType')
    FeedbackSetting = apps.get_model('API', 'FeedbackSetting')
    ContactPlatform = apps.get_model('API', 'ContactPlatform')
    ApiServicePolicy = apps.get_model('API', 'ApiServicePolicy')

    for code, name, desc, icon, is_default, sort in FEEDBACK_TYPES:
        FeedbackType.objects.update_or_create(
            code=code,
            defaults={'name': name, 'desc': desc, 'icon': icon,
                      'is_default': is_default, 'sort': sort, 'enabled': True},
        )

    # 单例：pk 固定为 1（与 FeedbackSetting.SINGLETON_PK 一致；迁移里的历史模型
    # 不携带自定义类属性，故这里直接写字面量）
    FeedbackSetting.objects.get_or_create(pk=1)

    for code, name, icon, value_label, url_template, sort in CONTACT_PLATFORMS:
        ContactPlatform.objects.update_or_create(
            code=code,
            defaults={'name': name, 'icon': icon, 'value_label': value_label,
                      'url_template': url_template, 'sort': sort, 'enabled': True},
        )

    for prefix, name, level, auth_mode in SERVICE_POLICIES:
        ApiServicePolicy.objects.update_or_create(
            path_prefix=prefix,
            defaults={'name': name, 'level': level, 'auth_mode': auth_mode, 'status': 'normal'},
        )


def unseed(apps, schema_editor):
    FeedbackType = apps.get_model('API', 'FeedbackType')
    ContactPlatform = apps.get_model('API', 'ContactPlatform')
    ApiServicePolicy = apps.get_model('API', 'ApiServicePolicy')

    FeedbackType.objects.filter(code__in=[row[0] for row in FEEDBACK_TYPES]).delete()
    ContactPlatform.objects.filter(code__in=[row[0] for row in CONTACT_PLATFORMS]).delete()
    ApiServicePolicy.objects.filter(path_prefix__in=[row[0] for row in SERVICE_POLICIES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('API', '0042_feedback_ticket'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
