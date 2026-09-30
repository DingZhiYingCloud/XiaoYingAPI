# 数据迁移：把海角社区「视频播放列表」端点固定为「开放」
#
# 原因：该端点返回的是 m3u8 播放列表文本，供浏览器里的播放器（hls.js / DPlayer / VLC 等）
# 直接加载；播放器无法为请求附带签名参数，若按全局兜底走「需要签名」会一律返回 20011、
# 导致视频播不了。源站视频本身在 CDN 上就是公开可取的，开放该端点不涉及敏感数据。

from django.db import migrations

# 必须保留为「开放」的端点级节点：(URL前缀, 策略名称)
OPEN_ENDPOINTS = (
    ('/api/haijiao/video/m3u8', '海角社区-视频播放列表'),
)


def open_video_endpoint(apps, schema_editor):
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
        ('API', '0030_policy_docs_visible_audience'),
    ]

    operations = [
        migrations.RunPython(open_video_endpoint, migrations.RunPython.noop),
    ]
