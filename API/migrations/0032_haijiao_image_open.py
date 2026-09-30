# 数据迁移：把海角社区「图片解码」端点固定为「开放」
#
# 原因：该端点返回真实图片二进制，供 <img src> 直接引用；图片标签无法为请求附带签名参数，
# 若按全局兜底走「需要签名」会一律返回 20011、图片显示不出来。
# 端点自身已做严格约束（仅 http/https 公网地址、拒绝内网/回环、不跟随重定向、限制体积、
# 且只接受能解出 data:image/* 的内容），开放不构成通用代理风险。

from django.db import migrations

# 必须保留为「开放」的端点级节点：(URL前缀, 策略名称)
OPEN_ENDPOINTS = (
    ('/api/haijiao/image', '海角社区-图片解码'),
)


def open_image_endpoint(apps, schema_editor):
    """幂等地把已知端点写成「开放」策略（端点级，精确匹配单个接口路径）"""
    ApiServicePolicy = apps.get_model('API', 'ApiServicePolicy')
    for prefix, name in OPEN_ENDPOINTS:
        ApiServicePolicy.objects.update_or_create(
            path_prefix=prefix,
            defaults={'name': name, 'level': 'endpoint', 'auth_mode': 'open',
                      'status': 'inherit', 'app_scope': 'inherit'},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('API', '0031_haijiao_video_open'),
    ]

    operations = [
        migrations.RunPython(open_image_endpoint, migrations.RunPython.noop),
    ]
