# 数据迁移：把红果短剧「网页直出」端点设为开放（免项目签名）
#
# 为什么必须开放：该地址是给 <video> 标签直接播放的，浏览器带不了
# app_id/timestamp/nonce/sign，其鉴权改由 play 接口下发的**时效令牌**承担
# （见 API/apis/dramas/hongguo/utils.py 的 make_stream_token / parse_stream_token）。
#
# 与 0028 的开放节点同源：服务级 /api/dramas/hongguo/ 仍是「需要签名」，
# 只有这一个端点显式开放（端点级优先于服务级）。

from django.db import migrations

OPEN_ENDPOINT = ('/api/dramas/hongguo/stream', '红果短剧-网页直出流')


def open_stream_endpoint(apps, schema_editor):
    ApiServicePolicy = apps.get_model('API', 'ApiServicePolicy')
    prefix, name = OPEN_ENDPOINT
    ApiServicePolicy.objects.update_or_create(
        path_prefix=prefix,
        defaults={'name': name, 'level': 'endpoint', 'auth_mode': 'open',
                  'status': 'inherit', 'app_scope': 'inherit'},
    )


def revert_stream_endpoint(apps, schema_editor):
    ApiServicePolicy = apps.get_model('API', 'ApiServicePolicy')
    ApiServicePolicy.objects.filter(path_prefix=OPEN_ENDPOINT[0]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('API', '0034_haijiao_sign_in_date'),
    ]

    operations = [
        migrations.RunPython(open_stream_endpoint, revert_stream_endpoint),
    ]
