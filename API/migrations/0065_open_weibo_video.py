# 数据迁移：把微博「视频代理播放」端点设为开放（免项目签名）
#
# 为什么必须开放：该地址是给 <video> 标签直接播放的，浏览器带不了
# app_id/timestamp/nonce/sign；而且播放器为拖动进度条会发**多次 Range 请求**，
# 项目签名的 nonce 是一次性的（重放会被拒），签名认证这条路根本走不通。
# 其鉴权改由 feed 接口下发的**时效令牌**承担
# （见 API/apis/weibo/utils.py 的 make_video_token / parse_video_token）。
#
# 与 0035 的开放节点同源：服务级 /api/weibo/ 仍是「需要签名」，
# 只有这一个端点显式开放（端点级优先于服务级）。

from django.db import migrations

OPEN_ENDPOINT = ('/api/weibo/video', '微博-视频代理播放')


def open_video_endpoint(apps, schema_editor):
    ApiServicePolicy = apps.get_model('API', 'ApiServicePolicy')
    prefix, name = OPEN_ENDPOINT
    ApiServicePolicy.objects.update_or_create(
        path_prefix=prefix,
        defaults={'name': name, 'level': 'endpoint', 'auth_mode': 'open',
                  'status': 'inherit'},
    )


def revert_video_endpoint(apps, schema_editor):
    ApiServicePolicy = apps.get_model('API', 'ApiServicePolicy')
    ApiServicePolicy.objects.filter(path_prefix=OPEN_ENDPOINT[0]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('API', '0064_platformaccount'),
    ]

    operations = [
        migrations.RunPython(open_video_endpoint, revert_video_endpoint),
    ]
