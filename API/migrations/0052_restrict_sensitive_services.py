# 数据迁移：把「敏感服务」收敛为「仅白名单项目可调用」（app_scope=whitelist）
#
# 背景（安全审计发现）：接入鉴权只回答「这是不是一个有效的接入项目」，而任何注册用户
# 都能在 /my/projects/ 自助建项目并当场拿到 app_id / app_secret（status 默认启用）。
# 服务策略的 app_scope 默认是 all（不限项目），于是**刚注册的账号**就能签名调用下列服务：
#   - 读取库内共享的海角账号与**密码明文**（/api/haijiao/accounts?with_password=true）
#   - 群发邮件（/api/email/v1/send）、短信（/api/sms_verify/）
#   - 消耗平台付费能力：超级鹰题分（/api/ddddocr/、/api/chaojiying/）、
#     图床容量（/api/ImageHosting/ 的 Token 池）、平台 AI Key（/api/ai/）
#   - 删改共享音乐数据（/api/music/）
#
# 改法：把这几个**服务级**节点设为 app_scope=whitelist —— 只有被超管显式加入该项目白名单
# （控制台 /console/services/ 的「项目白名单」）的项目才能调用，其余一律 20020 无权限。
# 其余常规服务保持「任意项目可用」，客户自助体验不变。
#
# 「预先放行既有项目」：迁移时把当前**已存在且启用**的项目加入白名单，否则上线瞬间所有
# 既有接入方会一起被拒。此后新建的项目（含自助创建的）默认不在名单里，需超管逐个授权。
#
# 回滚：本迁移不可逆（无法区分「原本就是 whitelist」的节点）。如需恢复，到控制台把这些
# 服务的「项目范围」改回「不限项目」即可。

from django.db import migrations

# 敏感服务的前缀 -> 新建策略节点的名称（一个服务可能横跨多个前缀，如邮箱含 VMEmail 线路）
SENSITIVE_SERVICES = (
    ('/api/haijiao/', '海角社区-仅白名单'),
    ('/api/music/', '音乐服务-仅白名单'),
    ('/api/email/', '邮箱服务-仅白名单'),
    ('/api/VMEmail_mailcx/', 'VMEmail 临时邮箱-仅白名单'),
    ('/api/sms_verify/', '短信验证-仅白名单'),
    ('/api/ddddocr/', '验证码识别-仅白名单'),
    ('/api/chaojiying/', '超级鹰打码-仅白名单'),
    ('/api/ImageHosting/', '图床服务-仅白名单'),
    ('/api/ai/', 'AI 服务-仅白名单'),
)


def restrict_sensitive_services(apps, schema_editor):
    """幂等地把这些服务设为「仅白名单项目」，并预先放行既有项目"""
    ApiServicePolicy = apps.get_model('API', 'ApiServicePolicy')
    UserApp = apps.get_model('API', 'UserApp')
    existing_apps = list(UserApp.objects.filter(status=True))

    for prefix, name in SENSITIVE_SERVICES:
        policy = ApiServicePolicy.objects.filter(path_prefix=prefix).first()
        if policy is None:
            # 只写 app_scope，其余项留「跟随上级」→ 取全局兜底：正常 / 需签名 / 文档展示 / 对外可用
            policy = ApiServicePolicy.objects.create(
                path_prefix=prefix, name=name, level='service', app_scope='whitelist')
        elif policy.app_scope != 'whitelist':
            # 已有节点（超管可能配过状态 / 文档可见性等）：只改项目范围，其余字段原样保留
            policy.app_scope = 'whitelist'
            policy.save(update_fields=['app_scope', 'updated_time'])
        if existing_apps:
            policy.apps.add(*existing_apps)


class Migration(migrations.Migration):

    dependencies = [
        ('API', '0051_user_app_owner_quota'),
    ]

    operations = [
        migrations.RunPython(restrict_sensitive_services, migrations.RunPython.noop),
    ]
